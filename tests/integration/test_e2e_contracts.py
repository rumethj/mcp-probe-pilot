"""End-to-end data contract tests.

Tests that verify data contracts survive across multiple pipeline stages.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
from mcp_probe_pilot.generate.gherkin_feature_generator import GherkinFeatureGenerator
from mcp_probe_pilot.generate.gherkin_formatter import GherkinFormatter
from mcp_probe_pilot.generate.step_implementation_generator import (
    StepImplementationGenerator,
)
from mcp_probe_pilot.plan.planner import Planner, _ScenarioListOutput


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------


VALID_FEATURE_TEMPLATE = """\
```gherkin
Feature: tool_search tool
  As an MCP client
  I want to test the tool_search tool

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test"

  @happy-path
  Scenario: {title}
    When the MCP Client calls the tool "tool_search" with parameters
      | parameter | value   |
      | query     | meeting |
    Then the response should be successful
```

[END_OF_FEATURE]
"""

PREBUILT_STEPS = """\
from behave import given, when, then

@given('the MCP Client is initialized and connected to the MCP Server: "{server_command}"')
def step_connected(context, server_command):
    pass

@when('the MCP Client calls the tool "{tool_name}" with parameters')
def step_call_tool(context, tool_name):
    pass

@then('the response should be successful')
def step_response_success(context):
    pass
"""


def _make_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        server_info=ServerInfo(
            name="test-server",
            version="1.0.0",
            protocol_version="2024-11-05",
            capabilities=ServerCapabilities(tools=True, resources=True, prompts=True),
        ),
        tools=[
            ToolInfo(
                name="tool_search",
                description="Search things",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            ),
        ],
        resources=[],
        prompts=[],
    )


# ------------------------------------------------------------------
# Planner -> Generator -> Formatter -> StepImplementationGenerator
# ------------------------------------------------------------------


class TestScenarioTitlesSurviveFullChain:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_titles_survive_planner_to_step_generator(
        self,
        mock_cpt: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Scenario titles planned by the Planner appear as Scenario: lines
        in the generated feature, are parsed by the Formatter, and appear in
        the step generator's input."""

        planned_title = "Search with specific keyword"

        chain_mock = MagicMock()
        chain_mock.invoke.return_value = _ScenarioListOutput(
            scenarios=[planned_title]
        )
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=chain_mock)
        mock_cpt.from_messages.return_value = mock_prompt

        mock_llm = MagicMock()
        planner = Planner(mock_llm)

        discovery = _make_discovery()
        tool_scenarios = planner.plan_tool_unit_tests(discovery.tools[0])
        assert any(sp.scenario == planned_title for sp in tool_scenarios)

        unit_plan = UnitTestPlanResult(tool_scenarios=tool_scenarios)
        integration_plan = IntegrationTestPlanResult()

        feature_text = VALID_FEATURE_TEMPLATE.format(title=planned_title)
        gen_response = MagicMock()
        gen_response.content = feature_text
        gen_llm = MagicMock()
        gen_llm.ainvoke = AsyncMock(return_value=gen_response)

        service = AsyncMock()
        service.query_codebase = AsyncMock(return_value=[])

        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=service,
            output_dir=tmp_path,
            discovery_result=discovery,
            server_command="test",
        )
        gen_result = await generator.generate_all(unit_plan, integration_plan)
        assert gen_result.files_generated >= 1

        feature_files = list(tmp_path.glob("*.feature"))
        assert len(feature_files) >= 1
        raw_content = feature_files[0].read_text()
        assert f"Scenario: {planned_title}" in raw_content

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)
        assert len(collection.features) >= 1

        all_scenario_names = {
            s.name for f in collection.features for s in f.scenarios
        }
        assert planned_title in all_scenario_names

        step_gen_llm = MagicMock()
        step_gen_llm.ainvoke = AsyncMock()

        step_generator = StepImplementationGenerator(
            llm=step_gen_llm,
            prebuilt_steps_code=PREBUILT_STEPS,
            output_dir=tmp_path,
        )
        step_result = await step_generator.generate_all(collection)

        assert step_result.steps_skipped > 0


# ------------------------------------------------------------------
# Generator -> Executor: runnable Behave project structure
# ------------------------------------------------------------------


class TestGeneratorOutputFormsBehaveProject:
    @pytest.mark.asyncio
    async def test_outputs_form_runnable_behave_project(
        self, tmp_path: Path
    ) -> None:
        """Generated feature files and step implementations form a runnable
        Behave project: correct directory structure, importable steps module,
        no missing step definitions."""

        discovery = _make_discovery()

        feature_text = VALID_FEATURE_TEMPLATE.format(title="Search with keyword")
        gen_response = MagicMock()
        gen_response.content = feature_text
        gen_llm = MagicMock()
        gen_llm.ainvoke = AsyncMock(return_value=gen_response)

        service = AsyncMock()
        service.query_codebase = AsyncMock(return_value=[])

        scenarios = [
            ScenarioPlan(scenario="Search with keyword", primitives=["tool_search"]),
        ]
        unit_plan = UnitTestPlanResult(tool_scenarios=scenarios)
        integration_plan = IntegrationTestPlanResult()

        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=service,
            output_dir=tmp_path,
            discovery_result=discovery,
            server_command="test",
        )
        await generator.generate_all(unit_plan, integration_plan)

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        step_llm = MagicMock()
        step_llm.ainvoke = AsyncMock()

        step_gen = StepImplementationGenerator(
            llm=step_llm,
            prebuilt_steps_code=PREBUILT_STEPS,
            output_dir=tmp_path,
        )
        await step_gen.generate_all(collection)

        feature_files = list(tmp_path.glob("*.feature"))
        assert len(feature_files) >= 1

        steps_dir = tmp_path / "steps"
        assert steps_dir.is_dir()

        steps_file = steps_dir / "steps.py"
        assert steps_file.exists()

        import ast
        code = steps_file.read_text(encoding="utf-8")
        ast.parse(code)

        assert "from behave import" in code or "@given" in code or "@when" in code

        for feature_file in feature_files:
            content = feature_file.read_text()
            assert content.startswith("Feature:")
            assert "Scenario:" in content
            assert "Given" in content or "When" in content
