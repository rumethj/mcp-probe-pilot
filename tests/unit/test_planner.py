"""Unit tests for the Planner class."""

from __future__ import annotations

import json
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
)
from mcp_probe_pilot.plan.planner import Planner, _ScenarioListOutput


# ------------------------------------------------------------------
# Helper: configure mock LLM so the LangChain chain works end-to-end
# ------------------------------------------------------------------


def _make_planner(return_value: object) -> tuple[Planner, MagicMock]:
    """Create a Planner with a fully mocked LLM chain.

    LangChain builds chains as ``prompt | llm.with_structured_output(schema)``.
    ``ChatPromptTemplate.__or__`` expects a Runnable-like object, which a bare
    MagicMock doesn't satisfy.  We sidestep this by patching
    ``ChatPromptTemplate.from_messages`` so that the prompt itself is a
    MagicMock; then ``mock_prompt | mock_structured_llm`` uses MagicMock's
    ``__or__``, which returns another MagicMock whose ``.invoke()`` we control.
    """
    chain_mock = MagicMock()
    chain_mock.invoke.return_value = return_value

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=chain_mock)

    mock_llm = MagicMock()

    return Planner(mock_llm), chain_mock, mock_prompt, mock_llm


# ===================================================================
# plan_tool_unit_tests
# ===================================================================


class TestPlanToolUnitTests:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_happy_path(
        self, mock_cpt: MagicMock, sample_tool: ToolInfo
    ) -> None:
        titles = ["Search with valid keyword", "Search with empty string"]
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_tool_unit_tests(sample_tool)

        assert len(result) == 2
        assert all(isinstance(sp, ScenarioPlan) for sp in result)
        assert result[0].scenario == titles[0]
        assert result[1].scenario == titles[1]
        assert all(sp.primitives == [sample_tool.name] for sp in result)
        chain.invoke.assert_called_once()

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_empty_description_and_schema(
        self, mock_cpt: MagicMock, sample_tool_minimal: ToolInfo
    ) -> None:
        titles = ["Ping returns pong"]
        planner, _, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_tool_unit_tests(sample_tool_minimal)

        assert len(result) == 1
        assert result[0].primitives == ["ping"]

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_invoke_receives_correct_variables(
        self, mock_cpt: MagicMock, sample_tool: ToolInfo
    ) -> None:
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=["Scenario A"])
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_tool_unit_tests(sample_tool)

        call_kwargs = chain.invoke.call_args[0][0]
        assert call_kwargs["tool_name"] == sample_tool.name
        assert call_kwargs["tool_description"] == sample_tool.description
        assert call_kwargs["input_schema"] == json.dumps(
            sample_tool.input_schema, indent=2
        )

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_single_scenario_has_no_pattern(
        self, mock_cpt: MagicMock, sample_tool: ToolInfo
    ) -> None:
        planner, _, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=["Only one"])
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_tool_unit_tests(sample_tool)

        assert len(result) == 1
        assert result[0].pattern is None

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_structured_output_called_with_schema(
        self, mock_cpt: MagicMock, sample_tool: ToolInfo
    ) -> None:
        planner, _, mock_prompt, mock_llm = _make_planner(
            _ScenarioListOutput(scenarios=["S1"])
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_tool_unit_tests(sample_tool)

        mock_llm.with_structured_output.assert_called_once_with(
            _ScenarioListOutput
        )


# ===================================================================
# plan_resource_unit_tests
# ===================================================================


class TestPlanResourceUnitTests:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_happy_path(
        self, mock_cpt: MagicMock, sample_resource: ResourceInfo
    ) -> None:
        titles = ["Read resource with valid URI", "Read empty resource"]
        planner, _, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_resource_unit_tests(sample_resource)

        assert len(result) == 2
        assert all(sp.primitives == ["all_notes"] for sp in result)

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_unnamed_resource_falls_back_to_uri(
        self, mock_cpt: MagicMock, sample_resource_unnamed: ResourceInfo
    ) -> None:
        titles = ["Read archived notes"]
        planner, _, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_resource_unit_tests(sample_resource_unnamed)

        assert result[0].primitives == ["notes://archive"]

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_template_resource_passes_is_template_true(
        self, mock_cpt: MagicMock, sample_resource_template: ResourceInfo
    ) -> None:
        titles = ["Read note by valid ID", "Read note with missing ID"]
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_resource_unit_tests(sample_resource_template)

        call_kwargs = chain.invoke.call_args[0][0]
        assert call_kwargs["is_template"] == "True"
        assert call_kwargs["resource_uri"] == "notes://{note_id}"

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_invoke_receives_mime_type(
        self, mock_cpt: MagicMock, sample_resource: ResourceInfo
    ) -> None:
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=["S1"])
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_resource_unit_tests(sample_resource)

        call_kwargs = chain.invoke.call_args[0][0]
        assert call_kwargs["mime_type"] == "application/json"
        assert call_kwargs["resource_name"] == "all_notes"


# ===================================================================
# plan_prompt_unit_tests
# ===================================================================


class TestPlanPromptUnitTests:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_happy_path(
        self, mock_cpt: MagicMock, sample_prompt: PromptInfo
    ) -> None:
        titles = ["Summarize with all args", "Summarize missing optional arg"]
        planner, _, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_prompt_unit_tests(sample_prompt)

        assert len(result) == 2
        assert all(sp.primitives == ["summarize_note"] for sp in result)

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_no_arguments_passes_none(
        self, mock_cpt: MagicMock, sample_prompt_no_args: PromptInfo
    ) -> None:
        titles = ["List commands successfully"]
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=titles)
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_prompt_unit_tests(sample_prompt_no_args)

        call_kwargs = chain.invoke.call_args[0][0]
        assert call_kwargs["arguments"] == "none"

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_invoke_receives_argument_repr(
        self, mock_cpt: MagicMock, sample_prompt: PromptInfo
    ) -> None:
        planner, chain, mock_prompt, _ = _make_planner(
            _ScenarioListOutput(scenarios=["Scenario X"])
        )
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_prompt_unit_tests(sample_prompt)

        call_kwargs = chain.invoke.call_args[0][0]
        assert "note_id (required)" in call_kwargs["arguments"]
        assert "style (optional)" in call_kwargs["arguments"]


# ===================================================================
# plan_integration_tests
# ===================================================================


class TestPlanIntegrationTests:
    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_happy_path(
        self, mock_cpt: MagicMock, sample_discovery: DiscoveryResult
    ) -> None:
        expected = IntegrationTestPlanResult(
            integration_scenarios=[
                ScenarioPlan(
                    scenario="Prompt-driven search and summarize",
                    primitives=["summarize_note", "search_notes"],
                    pattern="prompt-driven",
                ),
            ]
        )
        planner, _, mock_prompt, _ = _make_planner(expected)
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_integration_tests(sample_discovery)

        assert isinstance(result, IntegrationTestPlanResult)
        assert len(result.integration_scenarios) == 1
        assert result.integration_scenarios[0].pattern == "prompt-driven"

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_tools_only_discovery(
        self,
        mock_cpt: MagicMock,
        sample_tool: ToolInfo,
        sample_server_info: ServerInfo,
    ) -> None:
        discovery = DiscoveryResult(
            server_info=sample_server_info,
            tools=[sample_tool],
            resources=[],
            prompts=[],
        )
        expected = IntegrationTestPlanResult(
            integration_scenarios=[
                ScenarioPlan(
                    scenario="Chain search results",
                    primitives=["search_notes"],
                    pattern="chain-of-calls",
                ),
            ]
        )
        planner, chain, mock_prompt, _ = _make_planner(expected)
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_integration_tests(discovery)

        call_kwargs = chain.invoke.call_args[0][0]
        assert "No resources discovered" in call_kwargs["resources_summary"]
        assert "No prompts discovered" in call_kwargs["prompts_summary"]

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_empty_discovery(
        self, mock_cpt: MagicMock, empty_discovery: DiscoveryResult
    ) -> None:
        expected = IntegrationTestPlanResult(integration_scenarios=[])
        planner, chain, mock_prompt, _ = _make_planner(expected)
        mock_cpt.from_messages.return_value = mock_prompt

        result = planner.plan_integration_tests(empty_discovery)

        call_kwargs = chain.invoke.call_args[0][0]
        assert "No tools discovered" in call_kwargs["tools_summary"]
        assert result.num_scenarios == 0

    @patch("mcp_probe_pilot.plan.planner.ChatPromptTemplate")
    def test_structured_output_called_with_integration_schema(
        self, mock_cpt: MagicMock, sample_discovery: DiscoveryResult
    ) -> None:
        expected = IntegrationTestPlanResult(integration_scenarios=[])
        planner, _, mock_prompt, mock_llm = _make_planner(expected)
        mock_cpt.from_messages.return_value = mock_prompt

        planner.plan_integration_tests(sample_discovery)

        mock_llm.with_structured_output.assert_called_once_with(
            IntegrationTestPlanResult
        )


# ===================================================================
# Static helpers: _summarise_tools / _summarise_resources / _summarise_prompts
# ===================================================================


class TestSummariseTools:
    def test_with_tools(self, sample_discovery: DiscoveryResult) -> None:
        result = Planner._summarise_tools(sample_discovery)
        assert "**search_notes**" in result
        assert "Search notes by keyword query" in result
        assert '"query"' in result

    def test_empty(self, empty_discovery: DiscoveryResult) -> None:
        assert Planner._summarise_tools(empty_discovery) == "No tools discovered."


class TestSummariseResources:
    def test_with_resources(self, sample_discovery: DiscoveryResult) -> None:
        result = Planner._summarise_resources(sample_discovery)
        assert "**all_notes**" in result
        assert "application/json" in result

    def test_template_resource(
        self, sample_resource_template: ResourceInfo, sample_server_info: ServerInfo
    ) -> None:
        discovery = DiscoveryResult(
            server_info=sample_server_info,
            tools=[],
            resources=[sample_resource_template],
            prompts=[],
        )
        result = Planner._summarise_resources(discovery)
        assert "(template)" in result

    def test_empty(self, empty_discovery: DiscoveryResult) -> None:
        assert (
            Planner._summarise_resources(empty_discovery) == "No resources discovered."
        )


class TestSummarisePrompts:
    def test_with_prompts(self, sample_discovery: DiscoveryResult) -> None:
        result = Planner._summarise_prompts(sample_discovery)
        assert "**summarize_note**" in result
        assert "note_id (required)" in result
        assert "style (optional)" in result

    def test_prompt_no_args(
        self, sample_prompt_no_args: PromptInfo, sample_server_info: ServerInfo
    ) -> None:
        discovery = DiscoveryResult(
            server_info=sample_server_info,
            tools=[],
            resources=[],
            prompts=[sample_prompt_no_args],
        )
        result = Planner._summarise_prompts(discovery)
        assert "**list_commands**" in result
        assert "Arguments: none" in result

    def test_empty(self, empty_discovery: DiscoveryResult) -> None:
        assert (
            Planner._summarise_prompts(empty_discovery) == "No prompts discovered."
        )
