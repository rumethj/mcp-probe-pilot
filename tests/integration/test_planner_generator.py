"""Integration tests: Planner -> GherkinFeatureGenerator pipeline.

These tests verify that the planner's output feeds correctly into the
generator, producing valid .feature files on disk.  Both the LLM and
the service client are mocked; the Gherkin parser is real.
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
from mcp_probe_pilot.generate.gherkin_feature_generator import (
    GenerationResult,
    GherkinFeatureGenerator,
)
from mcp_probe_pilot.plan.planner import Planner, _ScenarioListOutput


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

VALID_TOOL_FEATURE = """\
```gherkin
Feature: search_notes tool
  As an MCP client
  I want to test the search_notes tool

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test-server"

  @happy-path
  Scenario: Search with valid keyword
    When the MCP Client calls the tool "search_notes" with parameters
      | parameter | value   |
      | query     | meeting |
    Then the tool result should contain key "results"

  @error-case
  Scenario: Search with empty string
    When the MCP Client calls the tool "search_notes" with parameters
      | parameter | value |
      | query     |       |
    Then the tool result should contain key "results"
```

[END_OF_FEATURE]
"""

VALID_INTEGRATION_FEATURE = """\
```gherkin
Feature: Integration workflows
  As an MCP client
  I want to test cross-primitive workflows

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test-server"

  @happy-path
  Scenario: Prompt-driven search and summarize
    When the MCP Client gets the prompt "summarize_note"
    Then the prompt result should not be empty
    When the MCP Client calls the tool "search_notes" with parameters
      | parameter | value   |
      | query     | meeting |
    Then the tool result should contain key "results"
```

[END_OF_FEATURE]
"""

MALFORMED_LLM_RESPONSE = "Here is some text without any Gherkin content at all."


def _make_planner_with_mock(
    return_value: object,
) -> tuple[Planner, MagicMock, MagicMock]:
    """Create a Planner with mocked LLM chain, returning (planner, mock_prompt, mock_llm)."""
    chain_mock = MagicMock()
    chain_mock.invoke.return_value = return_value

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain_mock)

    mock_llm = MagicMock()
    return Planner(mock_llm), mock_prompt, mock_llm


def _make_generator_llm(response_text: str) -> MagicMock:
    """Create a mock LLM for the GherkinFeatureGenerator.

    The generator calls ``await self._llm.ainvoke(messages)`` and reads
    ``response.content``.
    """
    response = MagicMock()
    response.content = response_text

    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def rich_discovery() -> DiscoveryResult:
    """Discovery with a tool, resource, and prompt for integration scenarios."""
    return DiscoveryResult(
        server_info=ServerInfo(
            name="test-notes-server",
            version="1.0.0",
            protocol_version="2024-11-05",
            capabilities=ServerCapabilities(
                tools=True, resources=True, prompts=True
            ),
        ),
        tools=[
            ToolInfo(
                name="search_notes",
                description="Search notes by keyword query",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
        ],
        resources=[
            ResourceInfo(
                uri="notes://all",
                name="all_notes",
                description="List all notes",
                mime_type="application/json",
                is_template=False,
            ),
        ],
        prompts=[
            PromptInfo(
                name="summarize_note",
                description="Summarize a note",
                arguments=[
                    PromptArgument(
                        name="note_id",
                        description="Note ID",
                        required=True,
                    ),
                ],
            ),
        ],
    )


# ===================================================================
# End-to-end: Planner unit plans -> Generator -> .feature files
# ===================================================================


class TestUnitTestPipeline:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_planner_output_feeds_generator(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Plan unit tests for a tool, then generate a .feature file."""
        titles = ["Search with valid keyword", "Search with empty string"]
        planner, mock_prompt, _ = _make_planner_with_mock(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        tool = rich_discovery.tools[0]
        tool_scenarios = planner.plan_tool_unit_tests(tool)

        unit_plan = UnitTestPlanResult(
            tool_scenarios=tool_scenarios,
            resource_scenarios=[],
            prompt_scenarios=[],
        )
        integration_plan = IntegrationTestPlanResult()

        gen_llm = _make_generator_llm(VALID_TOOL_FEATURE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        result = await generator.generate_all(unit_plan, integration_plan)

        assert isinstance(result, GenerationResult)
        assert result.files_generated >= 1
        assert result.files_failed == 0

        feature_files = list(tmp_path.glob("*.feature"))
        assert len(feature_files) >= 1
        content = feature_files[0].read_text()
        assert content.startswith("Feature:")

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_generated_feature_contains_scenarios(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Verify the generated file has Scenario blocks."""
        titles = ["Search with valid keyword"]
        planner, mock_prompt, _ = _make_planner_with_mock(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        tool_scenarios = planner.plan_tool_unit_tests(rich_discovery.tools[0])
        unit_plan = UnitTestPlanResult(tool_scenarios=tool_scenarios)
        integration_plan = IntegrationTestPlanResult()

        gen_llm = _make_generator_llm(VALID_TOOL_FEATURE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        await generator.generate_all(unit_plan, integration_plan)

        content = list(tmp_path.glob("*.feature"))[0].read_text()
        assert "Scenario:" in content
        assert "Given" in content
        assert "When" in content
        assert "Then" in content


# ===================================================================
# End-to-end: Planner integration plans -> Generator -> .feature file
# ===================================================================


class TestIntegrationTestPipeline:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_integration_feature_written(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Plan integration tests, then generate integration_workflows.feature."""
        expected_plan = IntegrationTestPlanResult(
            integration_scenarios=[
                ScenarioPlan(
                    scenario="Prompt-driven search and summarize",
                    primitives=["summarize_note", "search_notes"],
                    pattern="prompt-driven",
                ),
            ]
        )
        planner, mock_prompt, _ = _make_planner_with_mock(expected_plan)
        mock_cpt.from_messages.return_value = mock_prompt

        integration_plan = planner.plan_integration_tests(rich_discovery)
        unit_plan = UnitTestPlanResult()

        gen_llm = _make_generator_llm(VALID_INTEGRATION_FEATURE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        result = await generator.generate_all(unit_plan, integration_plan)

        assert result.files_generated >= 1

        integration_file = tmp_path / "integration_workflows.feature"
        assert integration_file.exists()
        content = integration_file.read_text()
        assert "Feature:" in content
        assert "Scenario:" in content


# ===================================================================
# Plan shape propagation
# ===================================================================


class TestPlanShapePropagation:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_scenario_titles_reach_generator_prompt(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """The generator should pass planner scenario titles to its LLM prompt."""
        titles = ["Verify search with keyword", "Handle missing query param"]
        planner, mock_prompt, _ = _make_planner_with_mock(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        tool_scenarios = planner.plan_tool_unit_tests(rich_discovery.tools[0])
        unit_plan = UnitTestPlanResult(tool_scenarios=tool_scenarios)
        integration_plan = IntegrationTestPlanResult()

        gen_llm = _make_generator_llm(VALID_TOOL_FEATURE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        await generator.generate_all(unit_plan, integration_plan)

        gen_llm.ainvoke.assert_called()
        call_args = gen_llm.ainvoke.call_args[0][0]
        human_msg_content = call_args[1].content
        for title in titles:
            assert title in human_msg_content, (
                f"Scenario title '{title}' not found in generator prompt"
            )


# ===================================================================
# Error resilience
# ===================================================================


class TestErrorResilience:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_malformed_llm_output_increments_files_failed(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """When the generator LLM returns non-Gherkin text, files_failed increments."""
        titles = ["Some scenario"]
        planner, mock_prompt, _ = _make_planner_with_mock(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        tool_scenarios = planner.plan_tool_unit_tests(rich_discovery.tools[0])
        unit_plan = UnitTestPlanResult(tool_scenarios=tool_scenarios)
        integration_plan = IntegrationTestPlanResult()

        gen_llm = _make_generator_llm(MALFORMED_LLM_RESPONSE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        result = await generator.generate_all(unit_plan, integration_plan)

        assert result.files_failed >= 1
        assert result.files_generated == 0

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    @pytest.mark.asyncio
    async def test_empty_plan_produces_no_files(
        self,
        mock_cpt: MagicMock,
        rich_discovery: DiscoveryResult,
        mock_service_client: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """With no scenarios planned, the generator produces zero files."""
        unit_plan = UnitTestPlanResult()
        integration_plan = IntegrationTestPlanResult()

        gen_llm = _make_generator_llm(VALID_TOOL_FEATURE)
        generator = GherkinFeatureGenerator(
            llm=gen_llm,
            service_client=mock_service_client,
            output_dir=tmp_path,
            discovery_result=rich_discovery,
            server_command="test-server",
        )
        result = await generator.generate_all(unit_plan, integration_plan)

        assert result.files_generated == 0
        assert result.files_failed == 0
        assert list(tmp_path.glob("*.feature")) == []
