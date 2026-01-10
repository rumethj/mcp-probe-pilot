"""Tests for the TestImplementor class."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil

from mcp_probe_pilot.config import LLMConfig
from mcp_probe_pilot.generators import (
    FeatureFile,
    GeneratedScenario,
    GroundTruthSpec,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
    WorkflowGroundTruth,
    WorkflowScenario,
    WorkflowStep,
)
from mcp_probe_pilot.generators.test_implementor import (
    TestImplementation,
    TestImplementor,
    TestImplementorError,
)
from mcp_probe_pilot.generators.llm_client import LLMResponse, MockLLMClient


class TestTestImplementation:
    """Tests for TestImplementation model."""

    def test_feature_count(self, tmp_path):
        """Test feature count property."""
        impl = TestImplementation(
            output_dir=tmp_path,
            feature_files=[Path("a.feature"), Path("b.feature")],
        )
        assert impl.feature_count == 2

    def test_is_complete_true(self, tmp_path):
        """Test is_complete when all files present."""
        impl = TestImplementation(
            output_dir=tmp_path,
            feature_files=[Path("a.feature")],
            step_definitions_file=Path("steps.py"),
            environment_file=Path("environment.py"),
            ground_truth_client_file=Path("ground_truth_client.py"),
        )
        assert impl.is_complete is True

    def test_is_complete_false(self, tmp_path):
        """Test is_complete when files missing."""
        impl = TestImplementation(
            output_dir=tmp_path,
            feature_files=[],
        )
        assert impl.is_complete is False


class TestTestImplementor:
    """Tests for TestImplementor class."""

    @pytest.fixture
    def llm_config(self):
        """Create test LLM config."""
        return LLMConfig(provider="openai", model="gpt-4")

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = MockLLMClient()
        return client

    @pytest.fixture
    def implementor(self, llm_config, mock_llm_client):
        """Create TestImplementor with mock LLM client."""
        return TestImplementor(llm_config, llm_client=mock_llm_client)

    @pytest.fixture
    def sample_scenario_set(self):
        """Create a sample scenario set for testing."""
        # Create ground truth
        ground_truth = GroundTruthSpec(
            id="gt_tool_test_tool",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            expected_behavior="Test behavior",
            expected_output_schema={"type": "object"},
            valid_input_examples=[],
            invalid_input_examples=[],
            semantic_reference="Test reference",
        )

        # Create scenario
        scenario = GeneratedScenario(
            id="sc_tool_test_tool_happy_path_0",
            name="test_tool happy path",
            gherkin="""Scenario: Test tool happy path
  Given the MCP server is running
  When I call tool "test_tool" with arguments {}
  Then the response should be successful""",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_tool_test_tool",
        )

        # Create feature file
        feature = FeatureFile(
            name="Tool - test_tool",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            ground_truth_id="gt_tool_test_tool",
            scenarios=[scenario],
            gherkin="""Feature: Tool - test_tool
  # Ground Truth ID: gt_tool_test_tool

  Scenario: Test tool happy path
    Given the MCP server is running
    When I call tool "test_tool" with arguments {}
    Then the response should be successful
""",
        )

        scenario_set = ScenarioSet()
        scenario_set.add_ground_truth(ground_truth)
        scenario_set.add_feature(feature)

        return scenario_set

    @pytest.fixture
    def output_dir(self, tmp_path):
        """Create temporary output directory."""
        return tmp_path / "tests"

    def test_llm_client_property(self, llm_config):
        """Test llm_client property creates client when needed."""
        implementor = TestImplementor(llm_config)
        # First access creates client
        client = implementor.llm_client
        assert client is not None
        # Second access returns same client
        assert implementor.llm_client is client

    def test_create_directories(self, implementor, output_dir):
        """Test directory structure creation."""
        implementor._create_directories(output_dir)

        assert output_dir.exists()
        assert (output_dir / "features").exists()
        assert (output_dir / "features" / "steps").exists()

    @pytest.mark.asyncio
    async def test_generate_feature_files(
        self, implementor, sample_scenario_set, output_dir
    ):
        """Test feature file generation."""
        implementor._create_directories(output_dir)

        feature_files = await implementor.generate_feature_files(
            sample_scenario_set, output_dir
        )

        assert len(feature_files) == 1
        assert feature_files[0].exists()
        assert feature_files[0].suffix == ".feature"

        # Check content
        content = feature_files[0].read_text()
        assert "Feature: Tool - test_tool" in content
        assert "Scenario:" in content

    @pytest.mark.asyncio
    async def test_generate_environment(self, implementor, output_dir):
        """Test environment.py generation."""
        implementor._create_directories(output_dir)

        env_file = await implementor.generate_environment(
            project_code="test-project",
            service_url="http://localhost:8000",
            server_command="python -m test_server",
            output_dir=output_dir,
        )

        assert env_file.exists()
        assert env_file.name == "environment.py"

        content = env_file.read_text()
        assert "test-project" in content
        assert "http://localhost:8000" in content
        assert "python -m test_server" in content
        assert "def before_all" in content
        assert "def after_all" in content

    def test_generate_ground_truth_client(self, implementor, output_dir):
        """Test ground_truth_client.py generation."""
        implementor._create_directories(output_dir)

        client_file = implementor._generate_ground_truth_client(output_dir)

        assert client_file.exists()
        assert client_file.name == "ground_truth_client.py"

        content = client_file.read_text()
        assert "class GroundTruthClient" in content
        assert "async def get" in content

    def test_extract_python_code_with_markdown(self, implementor):
        """Test extracting Python code from markdown code block."""
        content = """Here is the code:

```python
def hello():
    print("Hello")
```

That's the code."""

        result = implementor._extract_python_code(content)
        assert 'def hello():' in result
        assert 'print("Hello")' in result
        assert "```" not in result

    def test_extract_python_code_without_markdown(self, implementor):
        """Test extracting code without markdown wrapper."""
        content = """def hello():
    print("Hello")
"""
        result = implementor._extract_python_code(content)
        assert content.strip() == result

    def test_extract_python_code_generic_code_block(self, implementor):
        """Test extracting code from generic code block."""
        content = """```
def hello():
    print("Hello")
```"""
        result = implementor._extract_python_code(content)
        assert 'def hello():' in result

    @pytest.mark.asyncio
    async def test_generate_step_definitions(
        self, implementor, sample_scenario_set, output_dir, mock_llm_client
    ):
        """Test step definition generation with mock LLM."""
        implementor._create_directories(output_dir)

        # The mock client will return a pre-defined response
        steps_file = await implementor.generate_step_definitions(
            sample_scenario_set, output_dir
        )

        assert steps_file.exists()
        assert steps_file.name == "mcp_steps.py"
        assert (output_dir / "features" / "steps" / "__init__.py").exists()

    @pytest.mark.asyncio
    async def test_implement_tests_complete(
        self, implementor, sample_scenario_set, output_dir
    ):
        """Test complete test implementation."""
        result = await implementor.implement_tests(
            scenario_set=sample_scenario_set,
            output_dir=output_dir,
            project_code="test-project",
            service_url="http://localhost:8000",
            server_command="python -m test_server",
        )

        assert isinstance(result, TestImplementation)
        assert result.output_dir == output_dir
        assert len(result.feature_files) > 0
        assert result.step_definitions_file is not None
        assert result.environment_file is not None
        assert result.ground_truth_client_file is not None

    @pytest.mark.asyncio
    async def test_write_feature_file(self, implementor, sample_scenario_set, output_dir):
        """Test writing a single feature file."""
        features_dir = output_dir / "features"
        features_dir.mkdir(parents=True)

        feature = sample_scenario_set.features[0]
        filepath = implementor._write_feature_file(feature, features_dir)

        assert filepath.exists()
        assert filepath.name == "tool_test_tool.feature"

    @pytest.mark.asyncio
    async def test_write_workflow_feature_file(self, implementor, output_dir):
        """Test writing a workflow feature file."""
        features_dir = output_dir / "features"
        features_dir.mkdir(parents=True)

        workflow = WorkflowScenario(
            id="sc_workflow_test_0",
            name="Test Workflow",
            description="A test workflow",
            steps=[
                WorkflowStep(
                    step_number=1,
                    action_type="tool_call",
                    target_name="test_tool",
                    description="Call test tool",
                )
            ],
            gherkin="""Scenario: Test workflow
  Given the MCP server is running
  When I call tool "test_tool" with arguments {}
  Then the workflow should complete successfully""",
            ground_truth_id="gt_workflow_test",
            involved_features=["tools"],
        )

        filepath = implementor._write_workflow_feature_file(workflow, features_dir)

        assert filepath.exists()
        assert "workflow_" in filepath.name
        assert filepath.suffix == ".feature"

        content = filepath.read_text()
        assert "Feature: Workflow - Test Workflow" in content
        assert "gt_workflow_test" in content


class TestTestImplementorError:
    """Tests for TestImplementorError."""

    def test_error_message(self):
        """Test error message is preserved."""
        error = TestImplementorError("Test failed")
        assert str(error) == "Test failed"
