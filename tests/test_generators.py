"""Tests for the base generator, models, and prompts modules."""

import pytest

from mcp_probe_pilot.generators.base_generator import BaseTestGenerator, GeneratorError
from mcp_probe_pilot.generators.llm_client import MockLLMClient
from mcp_probe_pilot.generators.models import (
    GeneratedFeatureFile,
    GenerationResult,
    WorkflowType,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestWorkflowType:
    """Tests for WorkflowType enum."""

    def test_values(self):
        """Test workflow type enum values."""
        assert WorkflowType.PROMPT_DRIVEN == "prompt-driven"
        assert WorkflowType.RESOURCE_AUGMENTED == "resource-augmented"
        assert WorkflowType.CHAIN_OF_THOUGHT == "chain-of-thought"

    def test_from_string(self):
        """Test creating workflow type from string."""
        assert WorkflowType("prompt-driven") == WorkflowType.PROMPT_DRIVEN
        assert WorkflowType("resource-augmented") == WorkflowType.RESOURCE_AUGMENTED
        assert WorkflowType("chain-of-thought") == WorkflowType.CHAIN_OF_THOUGHT


class TestGeneratedFeatureFile:
    """Tests for GeneratedFeatureFile model."""

    def test_basic_creation(self):
        """Test creating a basic feature file model."""
        feature = GeneratedFeatureFile(
            filename="tool_auth_login.feature",
            content="Feature: Tool - auth_login\n  Scenario: Test\n    Given the MCP server",
            target_name="auth_login",
            target_type="tool",
            scenario_count=1,
        )

        assert feature.filename == "tool_auth_login.feature"
        assert feature.target_name == "auth_login"
        assert feature.target_type == "tool"
        assert feature.scenario_count == 1
        assert feature.workflow_type is None

    def test_with_workflow_type(self):
        """Test feature file with integration workflow type."""
        feature = GeneratedFeatureFile(
            filename="integration_workflows.feature",
            content="Feature: Integration",
            target_name="workflows",
            target_type="integration",
            scenario_count=3,
            workflow_type=WorkflowType.CHAIN_OF_THOUGHT,
        )

        assert feature.workflow_type == WorkflowType.CHAIN_OF_THOUGHT


class TestGenerationResult:
    """Tests for GenerationResult model."""

    def test_empty_result(self):
        """Test empty generation result."""
        result = GenerationResult()

        assert result.total_feature_files == 0
        assert result.total_scenarios == 0
        assert result.tools_covered == 0
        assert result.resources_covered == 0
        assert result.prompts_covered == 0
        assert not result.has_errors

    def test_result_with_files(self):
        """Test result with feature files."""
        feature = GeneratedFeatureFile(
            filename="tool_test.feature",
            content="Feature: Test",
            target_name="test",
            target_type="tool",
            scenario_count=3,
        )
        result = GenerationResult(
            feature_files=[feature],
            total_scenarios=3,
            tools_covered=1,
        )

        assert result.total_feature_files == 1
        assert result.total_scenarios == 3
        assert result.tools_covered == 1

    def test_result_with_errors(self):
        """Test result with generation errors."""
        result = GenerationResult(errors=["Failed to generate tests for tool 'x'"])
        assert result.has_errors


# =============================================================================
# Base Generator Tests
# =============================================================================


class TestBaseGeneratorHelpers:
    """Tests for BaseTestGenerator static/helper methods."""

    def test_clean_gherkin_removes_code_fences(self):
        """Test that markdown code fences are removed."""
        content = '```gherkin\nFeature: Test\n  Scenario: S1\n    Given x\n```'
        cleaned = BaseTestGenerator._clean_gherkin_output(content)
        assert cleaned.startswith("Feature:")
        assert "```" not in cleaned

    def test_clean_gherkin_generic_fences(self):
        """Test that generic code fences are removed."""
        content = '```\nFeature: Test\n  Scenario: S1\n    Given x\n```'
        cleaned = BaseTestGenerator._clean_gherkin_output(content)
        assert cleaned.startswith("Feature:")

    def test_clean_gherkin_with_preamble(self):
        """Test extraction of Feature: from content with preamble text."""
        content = 'Here is the feature file:\n\nFeature: Test\n  Scenario: S1\n    Given x'
        cleaned = BaseTestGenerator._clean_gherkin_output(content)
        assert cleaned.startswith("Feature:")

    def test_clean_gherkin_already_clean(self):
        """Test that clean Gherkin passes through unchanged."""
        content = "Feature: Test\n  Scenario: S1\n    Given the MCP server is running"
        cleaned = BaseTestGenerator._clean_gherkin_output(content)
        assert cleaned == content

    def test_count_scenarios(self):
        """Test scenario counting."""
        gherkin = (
            "Feature: Test\n"
            "  Scenario: First\n"
            "    Given x\n"
            "  Scenario: Second\n"
            "    Given y\n"
            "  Scenario Outline: Third\n"
            "    Given z\n"
        )
        assert BaseTestGenerator._count_scenarios(gherkin) == 3

    def test_count_scenarios_empty(self):
        """Test scenario counting with no scenarios."""
        assert BaseTestGenerator._count_scenarios("Feature: Empty") == 0

    def test_format_code_context_empty(self):
        """Test formatting empty code context."""
        mock_llm = MockLLMClient()
        generator = _ConcreteGenerator(mock_llm)
        result = generator._format_code_context([])
        assert result == "No source code context available."

    def test_format_code_context_with_entities(self):
        """Test formatting code context with entities."""
        mock_llm = MockLLMClient()
        generator = _ConcreteGenerator(mock_llm)
        entities = [
            {
                "name": "my_function",
                "entity_type": "function",
                "code": "def my_function(): pass",
                "docstring": "Does something.",
                "file_path": "src/module.py",
            }
        ]
        result = generator._format_code_context(entities)
        assert "my_function" in result
        assert "function" in result
        assert "Does something." in result
        assert "src/module.py" in result

    def test_build_prompt(self):
        """Test prompt building from template."""
        mock_llm = MockLLMClient()
        generator = _ConcreteGenerator(mock_llm)
        template = "Test ${name} with ${value}"
        result = generator._build_prompt(template, {"name": "foo", "value": "bar"})
        assert result == "Test foo with bar"

    def test_build_prompt_missing_variable(self):
        """Test prompt building with missing variable uses safe_substitute."""
        mock_llm = MockLLMClient()
        generator = _ConcreteGenerator(mock_llm)
        template = "Test ${name} with ${missing}"
        result = generator._build_prompt(template, {"name": "foo"})
        assert "foo" in result
        assert "${missing}" in result

    @pytest.mark.asyncio
    async def test_query_codebase_no_client(self):
        """Test codebase query returns empty when no service client."""
        mock_llm = MockLLMClient()
        generator = _ConcreteGenerator(mock_llm)
        result = await generator._query_codebase("test query")
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_gherkin_success(self):
        """Test successful Gherkin generation via LLM."""
        gherkin_content = (
            "Feature: Test\n"
            "  Scenario: Happy path\n"
            "    Given the MCP server is running\n"
            "    When I call tool \"test\" with arguments {}\n"
            "    Then the response should be successful"
        )
        mock_llm = MockLLMClient(responses=[gherkin_content])
        generator = _ConcreteGenerator(mock_llm)
        result = await generator._generate_gherkin("Generate tests")
        assert "Feature:" in result
        assert "Scenario:" in result

    @pytest.mark.asyncio
    async def test_generate_gherkin_empty_response(self):
        """Test GeneratorError on empty LLM response."""
        mock_llm = MockLLMClient(responses=[""])
        generator = _ConcreteGenerator(mock_llm)
        with pytest.raises(GeneratorError, match="empty content"):
            await generator._generate_gherkin("Generate tests")


# Concrete subclass for testing abstract base class
class _ConcreteGenerator(BaseTestGenerator):
    """Concrete test generator for testing the abstract base class."""

    async def generate_all(self, discovery_result):
        return GenerationResult()
