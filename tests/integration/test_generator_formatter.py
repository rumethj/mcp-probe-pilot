"""Integration tests: GherkinFeatureGenerator -> GherkinFormatter.

Verifies that feature files produced by the generator can be parsed
by the formatter into a valid GherkinFeatureCollection, and that
batched scenarios merge correctly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_probe_pilot.core.models.discover import (
    DiscoveryResult,
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
from mcp_probe_pilot.generate.gherkin_feature_generator import (
    GherkinFeatureGenerator,
    MAX_SCENARIOS_PER_BATCH,
)
from mcp_probe_pilot.generate.gherkin_formatter import GherkinFormatter


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


VALID_FEATURE = """\
```gherkin
Feature: tool_search tool
  As an MCP client
  I want to test the tool_search tool

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test"

  @happy-path
  Scenario: Search with valid keyword
    When the MCP Client calls the tool "tool_search" with parameters
      | parameter | value   |
      | query     | meeting |
    Then the response should be successful

  @error-case
  Scenario: Search with empty string
    When the MCP Client calls the tool "tool_search" with parameters
      | parameter | value |
      | query     |       |
    Then the response should be successful
```

[END_OF_FEATURE]
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


def _make_generator_llm(response_text: str) -> MagicMock:
    response = MagicMock()
    response.content = response_text
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


def _make_service_client() -> AsyncMock:
    client = AsyncMock()
    client.query_codebase = AsyncMock(return_value=[])
    return client


# ------------------------------------------------------------------
# Generated files are parseable by GherkinFormatter
# ------------------------------------------------------------------


class TestGeneratorOutputIsParseable:
    @pytest.mark.asyncio
    async def test_generated_file_parseable_by_formatter(
        self, tmp_path: Path
    ) -> None:
        """Feature files written by the generator are parseable by the
        GherkinFormatter into a valid GherkinFeatureCollection with correct
        scenario names, step types, and data tables intact."""

        discovery = _make_discovery()
        gen_llm = _make_generator_llm(VALID_FEATURE)
        service = _make_service_client()

        scenarios = [
            ScenarioPlan(scenario="Search with valid keyword", primitives=["tool_search"]),
            ScenarioPlan(scenario="Search with empty string", primitives=["tool_search"]),
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
        result = await generator.generate_all(unit_plan, integration_plan)
        assert result.files_generated >= 1

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        assert len(collection.features) >= 1
        feature = collection.features[0]

        scenario_names = {s.name for s in feature.scenarios}
        assert "Search with valid keyword" in scenario_names
        assert "Search with empty string" in scenario_names

        for scenario in feature.scenarios:
            assert len(scenario.when_steps) >= 1
            assert len(scenario.then_steps) >= 1

        when_step = feature.scenarios[0].when_steps[0]
        assert when_step.data_table is not None
        assert "parameter" in when_step.data_table.headers


# ------------------------------------------------------------------
# Batched scenarios merge cleanly
# ------------------------------------------------------------------


class TestBatchedScenariosMerge:
    @pytest.mark.asyncio
    async def test_batched_scenarios_merge_into_one_feature(
        self, tmp_path: Path
    ) -> None:
        """A feature file with batched scenarios (> MAX_SCENARIOS_PER_BATCH)
        merges cleanly and the formatter produces one GherkinFeature with
        all scenarios present."""

        discovery = _make_discovery()
        num_scenarios = MAX_SCENARIOS_PER_BATCH + 5

        scenario_titles = [f"Scenario {i}" for i in range(num_scenarios)]
        scenarios = [
            ScenarioPlan(scenario=title, primitives=["tool_search"])
            for title in scenario_titles
        ]

        batch_feature_template = """\
```gherkin
Feature: tool_search tool
  As an MCP client
  I want to test the tool_search tool

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test"

{scenarios}```

[END_OF_FEATURE]
"""
        call_count = [0]
        total_calls = (num_scenarios + MAX_SCENARIOS_PER_BATCH - 1) // MAX_SCENARIOS_PER_BATCH

        def make_response(*args, **kwargs):
            batch_idx = call_count[0]
            call_count[0] += 1
            start = batch_idx * MAX_SCENARIOS_PER_BATCH
            end = min(start + MAX_SCENARIOS_PER_BATCH, num_scenarios)
            scenario_blocks = []
            for i in range(start, end):
                scenario_blocks.append(
                    f"  @test\n"
                    f"  Scenario: Scenario {i}\n"
                    f'    When the MCP Client calls the tool "tool_search"\n'
                    f"    Then the response should be successful\n"
                )
            scenarios_text = "\n".join(scenario_blocks)
            content = batch_feature_template.format(scenarios=scenarios_text)

            resp = MagicMock()
            resp.content = content
            return resp

        gen_llm = MagicMock()
        gen_llm.ainvoke = AsyncMock(side_effect=make_response)
        service = _make_service_client()

        unit_plan = UnitTestPlanResult(tool_scenarios=scenarios)
        integration_plan = IntegrationTestPlanResult()

        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=service,
            output_dir=tmp_path,
            discovery_result=discovery,
            server_command="test",
        )
        result = await generator.generate_all(unit_plan, integration_plan)
        assert result.files_generated >= 1

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        assert len(collection.features) == 1
        feature = collection.features[0]
        assert len(feature.scenarios) == num_scenarios
