"""Tests for the IntegrationTestGenerator module."""

import json

import pytest
from unittest.mock import AsyncMock

from mcp_probe_pilot.discovery.models import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)
from mcp_probe_pilot.generators.base_generator import GeneratorError
from mcp_probe_pilot.generators.integration_test_generator import IntegrationTestGenerator
from mcp_probe_pilot.generators.llm_client import MockLLMClient
from mcp_probe_pilot.generators.models import WorkflowType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def search_tool():
    """Create a search tool for testing."""
    return ToolInfo(
        name="search_docs",
        description="Search documents and return resource URIs for matching files",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )


@pytest.fixture
def summarize_tool():
    """Create a summarize tool for testing."""
    return ToolInfo(
        name="summarize_text",
        description="Summarize the given text content from search results",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to summarize"},
                "query": {"type": "string", "description": "Original query context"},
            },
            "required": ["text"],
        },
    )


@pytest.fixture
def analyze_tool():
    """Create an analyze tool for testing."""
    return ToolInfo(
        name="analyze_code",
        description="Analyze code quality and provide review feedback",
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["code"],
        },
    )


@pytest.fixture
def doc_resource():
    """Create a document resource for testing."""
    return ResourceInfo(
        uri="docs://readme",
        name="readme",
        description="Project documentation",
        mime_type="text/markdown",
    )


@pytest.fixture
def code_review_prompt():
    """Create a code review prompt for testing."""
    return PromptInfo(
        name="code_review",
        description="Review code using analyze_code tool",
        arguments=[
            PromptArgument(name="language", description="Programming language", required=True),
        ],
    )


@pytest.fixture
def discovery_result_with_workflows(
    search_tool, summarize_tool, analyze_tool, doc_resource, code_review_prompt
):
    """Create a discovery result with identifiable workflow patterns."""
    return DiscoveryResult(
        server_info=ServerInfo(
            name="test-server",
            version="1.0.0",
            capabilities=ServerCapabilities(tools=True, resources=True, prompts=True),
        ),
        tools=[search_tool, summarize_tool, analyze_tool],
        resources=[doc_resource],
        prompts=[code_review_prompt],
    )


@pytest.fixture
def minimal_discovery_result():
    """Create a minimal discovery result with a single tool."""
    return DiscoveryResult(
        server_info=ServerInfo(name="minimal-server"),
        tools=[
            ToolInfo(
                name="echo",
                description="Echo input back",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            )
        ],
        resources=[],
        prompts=[],
    )


# =============================================================================
# Heuristic Workflow Identification Tests
# =============================================================================


class TestPromptDrivenWorkflows:
    """Tests for prompt-driven workflow identification."""

    def test_identifies_prompt_tool_link(self, discovery_result_with_workflows):
        """Test identification of prompt referencing a tool."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_prompt_driven_scenarios(
            discovery_result_with_workflows
        )

        assert len(workflows) >= 1
        assert any(
            w["type"] == WorkflowType.PROMPT_DRIVEN.value for w in workflows
        )
        assert any("code_review" in w["prompts"] for w in workflows)

    def test_no_prompts_returns_empty(self, minimal_discovery_result):
        """Test no workflows when no prompts available."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_prompt_driven_scenarios(
            minimal_discovery_result
        )
        assert workflows == []


class TestResourceAugmentedWorkflows:
    """Tests for resource-augmented workflow identification."""

    def test_identifies_tool_resource_link(self, discovery_result_with_workflows):
        """Test identification of tool that references resources."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_resource_augmented_scenarios(
            discovery_result_with_workflows
        )

        assert len(workflows) >= 1
        assert any(
            w["type"] == WorkflowType.RESOURCE_AUGMENTED.value for w in workflows
        )

    def test_no_resources_returns_empty(self, minimal_discovery_result):
        """Test no workflows when no resources available."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_resource_augmented_scenarios(
            minimal_discovery_result
        )
        assert workflows == []


class TestChainOfThoughtWorkflows:
    """Tests for chain-of-thought workflow identification."""

    def test_identifies_tool_chaining(self, discovery_result_with_workflows):
        """Test identification of tools whose outputs chain to inputs."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_chain_of_thought_scenarios(
            discovery_result_with_workflows
        )

        # search_docs and summarize_text share "query" parameter
        has_chain = any(
            w["type"] == WorkflowType.CHAIN_OF_THOUGHT.value for w in workflows
        )
        assert has_chain

    def test_single_tool_returns_empty(self, minimal_discovery_result):
        """Test no chaining with fewer than 2 tools."""
        generator = IntegrationTestGenerator(llm_client=MockLLMClient())
        workflows = generator._generate_chain_of_thought_scenarios(
            minimal_discovery_result
        )
        assert workflows == []


# =============================================================================
# LLM Workflow Identification Tests
# =============================================================================


class TestLLMWorkflowIdentification:
    """Tests for LLM-based workflow identification."""

    @pytest.mark.asyncio
    async def test_identify_workflows_success(self, discovery_result_with_workflows):
        """Test successful LLM-based workflow identification."""
        workflow_json = json.dumps([
            {
                "type": "chain-of-thought",
                "name": "Search then summarize",
                "description": "Search docs then summarize results",
                "steps": ["Search", "Summarize"],
                "tools": ["search_docs", "summarize_text"],
                "resources": [],
                "prompts": [],
            }
        ])
        mock_llm = MockLLMClient(responses=[workflow_json])
        generator = IntegrationTestGenerator(llm_client=mock_llm)

        workflows = await generator._identify_workflows(
            discovery_result_with_workflows, "code context"
        )

        assert len(workflows) == 1
        assert workflows[0]["type"] == "chain-of-thought"

    @pytest.mark.asyncio
    async def test_identify_workflows_dict_response(self, discovery_result_with_workflows):
        """Test workflow identification when LLM returns dict with 'workflows' key."""
        workflow_json = json.dumps({
            "workflows": [
                {
                    "type": "prompt-driven",
                    "name": "Code review flow",
                    "description": "Use prompt to trigger code analysis",
                    "steps": ["Get prompt", "Call tool"],
                    "tools": ["analyze_code"],
                    "resources": [],
                    "prompts": ["code_review"],
                }
            ]
        })
        mock_llm = MockLLMClient(responses=[workflow_json])
        generator = IntegrationTestGenerator(llm_client=mock_llm)

        workflows = await generator._identify_workflows(
            discovery_result_with_workflows, "code context"
        )

        assert len(workflows) == 1
        assert workflows[0]["type"] == "prompt-driven"


# =============================================================================
# Integration Feature Generation Tests
# =============================================================================


class TestIntegrationTestGenerator:
    """Tests for the full integration test generator."""

    @pytest.mark.asyncio
    async def test_generate_all_produces_feature_file(
        self, discovery_result_with_workflows
    ):
        """Test that generate_all produces a single integration feature file."""
        workflow_json = json.dumps([{
            "type": "chain-of-thought",
            "name": "Search and summarize",
            "description": "Chain search into summarize",
            "steps": ["Search", "Summarize"],
            "tools": ["search_docs", "summarize_text"],
            "resources": [],
            "prompts": [],
        }])
        integration_gherkin = (
            "Feature: Integration - Workflow Scenarios\n"
            "\n"
            "  @chain-of-thought\n"
            "  Scenario: Search and summarize\n"
            '    Given the MCP server is running\n'
            '    When I call tool "search_docs" with arguments {"query": "test"}\n'
            '    And I pass the result to tool "summarize_text"\n'
            '    Then the response should be semantically relevant to "search summary"\n'
        )
        mock_llm = MockLLMClient(responses=[workflow_json, integration_gherkin])
        generator = IntegrationTestGenerator(llm_client=mock_llm)

        result = await generator.generate_all(discovery_result_with_workflows)

        assert result.total_feature_files == 1
        assert result.workflows_identified >= 1
        feature = result.feature_files[0]
        assert feature.filename == "integration_workflows.feature"
        assert feature.target_type == "integration"

    @pytest.mark.asyncio
    async def test_generate_all_no_workflows(self, minimal_discovery_result):
        """Test generate_all with no identifiable workflows."""
        # LLM returns empty array for workflow identification
        mock_llm = MockLLMClient(responses=["[]"])
        generator = IntegrationTestGenerator(llm_client=mock_llm)

        result = await generator.generate_all(minimal_discovery_result)

        assert result.total_feature_files == 0
        assert result.workflows_identified == 0

    @pytest.mark.asyncio
    async def test_generate_all_llm_failure_falls_back_to_heuristics(
        self, discovery_result_with_workflows
    ):
        """Test that LLM failure falls back to heuristic workflow identification."""
        integration_gherkin = (
            "Feature: Integration - Workflow Scenarios\n"
            "\n"
            "  @chain-of-thought\n"
            "  Scenario: Chained tools\n"
            '    Given the MCP server is running\n'
            '    When I call tool "search_docs" with arguments {"query": "test"}\n'
            '    And I pass the result to tool "summarize_text"\n'
            '    Then the response should be semantically relevant to "test"\n'
        )
        # First call (workflow ID) returns invalid JSON, second call returns feature
        mock_llm = MockLLMClient(
            responses=["This is not valid JSON at all", integration_gherkin]
        )
        generator = IntegrationTestGenerator(llm_client=mock_llm)

        result = await generator.generate_all(discovery_result_with_workflows)

        # Should still produce results via heuristic fallback
        assert result.workflows_identified >= 1

    @pytest.mark.asyncio
    async def test_generate_all_with_code_context(
        self, discovery_result_with_workflows
    ):
        """Test integration generation with ChromaDB code context."""
        workflow_json = json.dumps([{
            "type": "chain-of-thought",
            "name": "Test workflow",
            "description": "Test",
            "steps": ["A", "B"],
            "tools": ["search_docs"],
            "resources": [],
            "prompts": [],
        }])
        integration_gherkin = (
            "Feature: Integration\n  Scenario: Test\n    Given the MCP server is running"
        )
        mock_llm = MockLLMClient(responses=[workflow_json, integration_gherkin])

        mock_service = AsyncMock()
        mock_service.query_codebase = AsyncMock(return_value=[
            {"name": "handler", "entity_type": "function", "code": "def handler(): pass"},
        ])

        generator = IntegrationTestGenerator(
            llm_client=mock_llm,
            service_client=mock_service,
            project_code="test-project",
        )
        result = await generator.generate_all(discovery_result_with_workflows)

        mock_service.query_codebase.assert_called_once()


# =============================================================================
# Summary Formatting Tests
# =============================================================================


class TestSummaryFormatting:
    """Tests for capability summary formatting methods."""

    def test_format_tools_summary(self, discovery_result_with_workflows):
        """Test tools summary formatting."""
        result = IntegrationTestGenerator._format_tools_summary(
            discovery_result_with_workflows
        )
        assert "search_docs" in result
        assert "summarize_text" in result
        assert "analyze_code" in result

    def test_format_tools_summary_empty(self):
        """Test tools summary with no tools."""
        empty = DiscoveryResult(
            server_info=ServerInfo(name="empty"), tools=[], resources=[], prompts=[]
        )
        result = IntegrationTestGenerator._format_tools_summary(empty)
        assert result == "No tools available."

    def test_format_resources_summary(self, discovery_result_with_workflows):
        """Test resources summary formatting."""
        result = IntegrationTestGenerator._format_resources_summary(
            discovery_result_with_workflows
        )
        assert "readme" in result
        assert "docs://readme" in result

    def test_format_resources_summary_empty(self):
        """Test resources summary with no resources."""
        empty = DiscoveryResult(
            server_info=ServerInfo(name="empty"), tools=[], resources=[], prompts=[]
        )
        result = IntegrationTestGenerator._format_resources_summary(empty)
        assert result == "No resources available."

    def test_format_prompts_summary(self, discovery_result_with_workflows):
        """Test prompts summary formatting."""
        result = IntegrationTestGenerator._format_prompts_summary(
            discovery_result_with_workflows
        )
        assert "code_review" in result
        assert "language" in result

    def test_format_prompts_summary_empty(self):
        """Test prompts summary with no prompts."""
        empty = DiscoveryResult(
            server_info=ServerInfo(name="empty"), tools=[], resources=[], prompts=[]
        )
        result = IntegrationTestGenerator._format_prompts_summary(empty)
        assert result == "No prompts available."
