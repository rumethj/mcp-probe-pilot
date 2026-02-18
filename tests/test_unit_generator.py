"""Tests for the UnitTestGenerator module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
from mcp_probe_pilot.generators.llm_client import MockLLMClient
from mcp_probe_pilot.generators.models import GeneratedFeatureFile
from mcp_probe_pilot.generators.unit_test_generator import (
    UnitTestGenerator,
    _sanitize_filename,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm():
    """Create a mock LLM client with default Gherkin responses."""
    tool_gherkin = (
        "Feature: Tool - test_tool\n"
        "\n"
        "  @happy-path\n"
        "  Scenario: Successful invocation\n"
        '    Given the MCP server is running\n'
        '    When I call tool "test_tool" with arguments {"query": "hello"}\n'
        "    Then the response should be successful\n"
        "\n"
        "  @error-case\n"
        "  Scenario: Missing required parameter\n"
        '    Given the MCP server is running\n'
        '    When I call tool "test_tool" with arguments {}\n'
        "    Then the response should contain an error\n"
        "\n"
        "  @edge-case\n"
        "  Scenario: Empty string parameter\n"
        '    Given the MCP server is running\n'
        '    When I call tool "test_tool" with arguments {"query": ""}\n'
        "    Then the response should be successful\n"
    )
    return MockLLMClient(responses=[tool_gherkin])


@pytest.fixture
def sample_tool():
    """Create a sample ToolInfo for testing."""
    return ToolInfo(
        name="test_tool",
        description="A tool for testing queries",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    )


@pytest.fixture
def sample_resource():
    """Create a sample ResourceInfo for testing."""
    return ResourceInfo(
        uri="docs://readme",
        name="readme",
        description="Project README file",
        mime_type="text/markdown",
        is_template=False,
    )


@pytest.fixture
def sample_prompt():
    """Create a sample PromptInfo for testing."""
    return PromptInfo(
        name="code_review",
        description="Review code for best practices",
        arguments=[
            PromptArgument(name="language", description="Programming language", required=True),
            PromptArgument(name="style", description="Code style guide", required=False),
        ],
    )


@pytest.fixture
def sample_discovery_result(sample_tool, sample_resource, sample_prompt):
    """Create a sample DiscoveryResult for testing."""
    return DiscoveryResult(
        server_info=ServerInfo(
            name="test-server",
            version="1.0.0",
            protocol_version="2024-11-05",
            capabilities=ServerCapabilities(tools=True, resources=True, prompts=True),
        ),
        tools=[sample_tool],
        resources=[sample_resource],
        prompts=[sample_prompt],
    )


# =============================================================================
# Helper Tests
# =============================================================================


class TestSanitizeFilename:
    """Tests for _sanitize_filename helper."""

    def test_simple_name(self):
        """Test sanitizing a simple name."""
        assert _sanitize_filename("auth_login") == "auth_login"

    def test_name_with_special_chars(self):
        """Test sanitizing a name with special characters."""
        assert _sanitize_filename("my/tool.name") == "my_tool_name"

    def test_name_with_spaces(self):
        """Test sanitizing a name with spaces."""
        assert _sanitize_filename("my tool name") == "my_tool_name"

    def test_uppercase_name(self):
        """Test that names are lowercased."""
        assert _sanitize_filename("MyTool") == "mytool"


# =============================================================================
# Unit Test Generator Tests
# =============================================================================


class TestUnitTestGenerator:
    """Tests for UnitTestGenerator."""

    @pytest.mark.asyncio
    async def test_generate_tool_tests(self, mock_llm, sample_tool):
        """Test generating feature file for a tool."""
        generator = UnitTestGenerator(llm_client=mock_llm)
        feature = await generator.generate_tool_tests(sample_tool)

        assert isinstance(feature, GeneratedFeatureFile)
        assert feature.filename == "tool_test_tool.feature"
        assert feature.target_name == "test_tool"
        assert feature.target_type == "tool"
        assert feature.scenario_count == 3
        assert "Feature:" in feature.content

    @pytest.mark.asyncio
    async def test_generate_tool_tests_uses_correct_prompt(self, sample_tool):
        """Test that tool generation sends appropriate prompt to LLM."""
        mock_llm = MockLLMClient(responses=[
            "Feature: Tool - test_tool\n  Scenario: Test\n    Given x"
        ])
        generator = UnitTestGenerator(llm_client=mock_llm)
        await generator.generate_tool_tests(sample_tool)

        assert mock_llm.call_count == 1
        call = mock_llm.call_history[0]
        assert "test_tool" in call["prompt"]
        assert "query" in call["prompt"]

    @pytest.mark.asyncio
    async def test_generate_resource_tests(self, sample_resource):
        """Test generating feature file for a resource."""
        resource_gherkin = (
            "Feature: Resource - readme\n"
            "\n"
            "  @happy-path\n"
            "  Scenario: Read resource successfully\n"
            '    Given the MCP server is running\n'
            '    When I read resource "docs://readme"\n'
            "    Then the response should be successful\n"
            "\n"
            "  @error-case\n"
            "  Scenario: Invalid URI\n"
            '    Given the MCP server is running\n'
            '    When I read resource "invalid://uri"\n'
            "    Then the response should contain an error\n"
            "\n"
            "  @edge-case\n"
            "  Scenario: Special characters in URI\n"
            '    Given the MCP server is running\n'
            '    When I read resource "docs://special%20chars"\n'
            "    Then the response should be successful\n"
        )
        mock_llm = MockLLMClient(responses=[resource_gherkin])
        generator = UnitTestGenerator(llm_client=mock_llm)
        feature = await generator.generate_resource_tests(sample_resource)

        assert feature.filename == "resource_readme.feature"
        assert feature.target_name == "readme"
        assert feature.target_type == "resource"
        assert feature.scenario_count == 3

    @pytest.mark.asyncio
    async def test_generate_prompt_tests(self, sample_prompt):
        """Test generating feature file for a prompt."""
        prompt_gherkin = (
            "Feature: Prompt - code_review\n"
            "\n"
            "  @happy-path\n"
            "  Scenario: Get prompt with valid arguments\n"
            '    Given the MCP server is running\n'
            '    When I get prompt "code_review" with arguments {"language": "python"}\n'
            "    Then the response should be successful\n"
            "\n"
            "  @error-case\n"
            "  Scenario: Missing required argument\n"
            '    Given the MCP server is running\n'
            '    When I get prompt "code_review" with arguments {}\n'
            "    Then the response should contain an error\n"
            "\n"
            "  @edge-case\n"
            "  Scenario: Empty language argument\n"
            '    Given the MCP server is running\n'
            '    When I get prompt "code_review" with arguments {"language": ""}\n'
            "    Then the response should be successful\n"
        )
        mock_llm = MockLLMClient(responses=[prompt_gherkin])
        generator = UnitTestGenerator(llm_client=mock_llm)
        feature = await generator.generate_prompt_tests(sample_prompt)

        assert feature.filename == "prompt_code_review.feature"
        assert feature.target_name == "code_review"
        assert feature.target_type == "prompt"
        assert feature.scenario_count == 3

    @pytest.mark.asyncio
    async def test_generate_all(self, sample_discovery_result):
        """Test generating all unit test feature files."""
        tool_gherkin = (
            "Feature: Tool\n  Scenario: T1\n    Given x\n"
            "  Scenario: T2\n    Given x\n  Scenario: T3\n    Given x"
        )
        resource_gherkin = (
            "Feature: Resource\n  Scenario: R1\n    Given x\n"
            "  Scenario: R2\n    Given x\n  Scenario: R3\n    Given x"
        )
        prompt_gherkin = (
            "Feature: Prompt\n  Scenario: P1\n    Given x\n"
            "  Scenario: P2\n    Given x\n  Scenario: P3\n    Given x"
        )
        mock_llm = MockLLMClient(
            responses=[tool_gherkin, resource_gherkin, prompt_gherkin]
        )
        generator = UnitTestGenerator(llm_client=mock_llm)
        result = await generator.generate_all(sample_discovery_result)

        assert result.total_feature_files == 3
        assert result.total_scenarios == 9
        assert result.tools_covered == 1
        assert result.resources_covered == 1
        assert result.prompts_covered == 1
        assert not result.has_errors

    @pytest.mark.asyncio
    async def test_generate_all_with_failure(self, sample_discovery_result):
        """Test generate_all collects errors without stopping."""
        mock_llm = MockLLMClient(responses=[""])
        generator = UnitTestGenerator(llm_client=mock_llm)
        result = await generator.generate_all(sample_discovery_result)

        assert result.has_errors
        assert len(result.errors) == 3

    @pytest.mark.asyncio
    async def test_generate_all_empty_discovery(self):
        """Test generate_all with empty discovery result."""
        empty_result = DiscoveryResult(
            server_info=ServerInfo(name="empty-server"),
            tools=[],
            resources=[],
            prompts=[],
        )
        mock_llm = MockLLMClient()
        generator = UnitTestGenerator(llm_client=mock_llm)
        result = await generator.generate_all(empty_result)

        assert result.total_feature_files == 0
        assert result.total_scenarios == 0
        assert not result.has_errors

    @pytest.mark.asyncio
    async def test_generate_tool_tests_with_code_context(self, sample_tool):
        """Test tool generation queries ChromaDB when service client is configured."""
        tool_gherkin = (
            "Feature: Tool\n  Scenario: Test\n    Given the MCP server is running"
        )
        mock_llm = MockLLMClient(responses=[tool_gherkin])

        mock_service = AsyncMock()
        mock_service.query_codebase = AsyncMock(return_value=[
            {"name": "handler", "entity_type": "function", "code": "def handler(): pass"},
        ])

        generator = UnitTestGenerator(
            llm_client=mock_llm,
            service_client=mock_service,
            project_code="test-project",
        )
        feature = await generator.generate_tool_tests(sample_tool)

        assert feature is not None
        mock_service.query_codebase.assert_called_once()
        # Verify code context was included in the prompt
        prompt_sent = mock_llm.call_history[0]["prompt"]
        assert "handler" in prompt_sent
