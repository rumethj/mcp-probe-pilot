"""Integration tests: Discoverer -> Planner.

Verifies that a DiscoveryResult feeds correctly into the Planner,
producing proportional ScenarioPlan entries that cover every
discovered primitive.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mcp_probe_pilot.core.models.discover import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)
from mcp_probe_pilot.core.models.plan import (
    IntegrationTestPlanResult,
    ScenarioPlan,
    UnitTestPlanResult,
)
from mcp_probe_pilot.plan.planner import Planner, _ScenarioListOutput


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_planner(return_value: object) -> tuple[Planner, MagicMock, MagicMock]:
    chain_mock = MagicMock()
    chain_mock.invoke.return_value = return_value

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain_mock)

    mock_llm = MagicMock()
    return Planner(mock_llm), mock_prompt, mock_llm


def _server_info() -> ServerInfo:
    return ServerInfo(
        name="test-server",
        version="1.0.0",
        protocol_version="2024-11-05",
        capabilities=ServerCapabilities(tools=True, resources=True, prompts=True),
    )


# ------------------------------------------------------------------
# Rich discovery yields proportional scenarios covering all primitives
# ------------------------------------------------------------------


class TestRichDiscoveryProportionalPlans:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_many_primitives_yield_proportional_plans(
        self, mock_cpt: MagicMock
    ) -> None:
        """A DiscoveryResult with many tools/resources/prompts produces a
        proportional number of ScenarioPlan entries, and every discovered
        primitive appears in at least one plan."""

        tools = [
            ToolInfo(name=f"tool_{i}", description=f"Tool {i}", input_schema={})
            for i in range(5)
        ]
        resources = [
            ResourceInfo(
                uri=f"res://{i}",
                name=f"res_{i}",
                description=f"Resource {i}",
                mime_type="text/plain",
                is_template=False,
            )
            for i in range(3)
        ]
        prompts = [
            PromptInfo(
                name=f"prompt_{i}",
                description=f"Prompt {i}",
                arguments=[
                    PromptArgument(name="arg", description="an arg", required=True),
                ],
            )
            for i in range(2)
        ]

        discovery = DiscoveryResult(
            server_info=_server_info(),
            tools=tools,
            resources=resources,
            prompts=prompts,
        )

        titles_2 = _ScenarioListOutput(scenarios=["Scenario A", "Scenario B"])
        planner, mock_prompt, _ = _make_planner(titles_2)
        mock_cpt.from_messages.return_value = mock_prompt

        tool_scenarios = []
        for t in discovery.tools:
            tool_scenarios.extend(planner.plan_tool_unit_tests(t))

        resource_scenarios = []
        for r in discovery.resources:
            resource_scenarios.extend(planner.plan_resource_unit_tests(r))

        prompt_scenarios = []
        for p in discovery.prompts:
            prompt_scenarios.extend(planner.plan_prompt_unit_tests(p))

        unit_plan = UnitTestPlanResult(
            tool_scenarios=tool_scenarios,
            resource_scenarios=resource_scenarios,
            prompt_scenarios=prompt_scenarios,
        )

        assert unit_plan.num_scenarios == 2 * (5 + 3 + 2)

        all_primitives_in_plans = set()
        for sp in tool_scenarios + resource_scenarios + prompt_scenarios:
            all_primitives_in_plans.update(sp.primitives)

        discovered_names = (
            {t.name for t in tools}
            | {r.name for r in resources}
            | {p.name for p in prompts}
        )
        assert discovered_names == all_primitives_in_plans


# ------------------------------------------------------------------
# Zero capabilities discovery
# ------------------------------------------------------------------


class TestZeroCapabilitiesDiscovery:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_empty_discovery_yields_empty_plans(
        self, mock_cpt: MagicMock
    ) -> None:
        """A discovery with zero capabilities results in empty plans
        without errors."""

        discovery = DiscoveryResult(
            server_info=ServerInfo(
                name="logging-only-server",
                version="1.0.0",
                protocol_version="2024-11-05",
                capabilities=ServerCapabilities(
                    tools=False, resources=False, prompts=False, logging=True,
                ),
            ),
            tools=[],
            resources=[],
            prompts=[],
        )

        expected_integration = IntegrationTestPlanResult(integration_scenarios=[])
        planner, mock_prompt, _ = _make_planner(expected_integration)
        mock_cpt.from_messages.return_value = mock_prompt

        tool_scenarios = []
        for t in discovery.tools:
            tool_scenarios.extend(planner.plan_tool_unit_tests(t))

        resource_scenarios = []
        for r in discovery.resources:
            resource_scenarios.extend(planner.plan_resource_unit_tests(r))

        prompt_scenarios = []
        for p in discovery.prompts:
            prompt_scenarios.extend(planner.plan_prompt_unit_tests(p))

        unit_plan = UnitTestPlanResult(
            tool_scenarios=tool_scenarios,
            resource_scenarios=resource_scenarios,
            prompt_scenarios=prompt_scenarios,
        )

        assert unit_plan.num_scenarios == 0
        assert tool_scenarios == []
        assert resource_scenarios == []
        assert prompt_scenarios == []

        integration_plan = planner.plan_integration_tests(discovery)
        assert integration_plan.num_scenarios == 0
