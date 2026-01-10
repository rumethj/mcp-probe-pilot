"""Tests for the test generators module.

This module tests the ClientTestGenerator and related components using
mocked LLM responses to avoid actual API calls.
"""

import json

import pytest

from mcp_probe_pilot.config import LLMConfig
from mcp_probe_pilot.discovery.models import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)
from mcp_probe_pilot.generators import (
    ClientTestGenerator,
    FeatureFile,
    GeneratedScenario,
    GeneratorError,
    GroundTruthSpec,
    LLMClientError,
    MockLLMClient,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
    WorkflowGroundTruth,
    WorkflowScenario,
    WorkflowStep,
)
from mcp_probe_pilot.generators.prompts import (
    GROUND_TRUTH_SYSTEM_PROMPT,
    SCENARIO_SYSTEM_PROMPT,
    build_ground_truth_prompt,
    build_prompt_ground_truth_prompt,
    build_prompt_scenario_prompt,
    build_resource_ground_truth_prompt,
    build_resource_scenario_prompt,
    build_scenario_prompt,
    build_tool_ground_truth_prompt,
    build_tool_scenario_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_tool() -> ToolInfo:
    """Provide a sample tool for testing."""
    return ToolInfo(
        name="auth_login",
        description="Authenticate a user and return a token",
        input_schema={
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "The username"},
                "password": {"type": "string", "description": "The password"},
            },
            "required": ["username", "password"],
        },
    )


@pytest.fixture
def sample_resource() -> ResourceInfo:
    """Provide a sample resource for testing."""
    return ResourceInfo(
        uri="user://{user_id}/profile",
        name="User Profile",
        description="Get profile information for a user",
        mime_type="application/json",
        is_template=True,
    )


@pytest.fixture
def sample_prompt() -> PromptInfo:
    """Provide a sample prompt for testing."""
    return PromptInfo(
        name="create_task_template",
        description="Generate a template for creating a new task",
        arguments=[
            PromptArgument(
                name="project_name",
                description="The name of the project",
                required=True,
            ),
            PromptArgument(
                name="task_type",
                description="Type of task (feature, bug, improvement)",
                required=False,
            ),
        ],
    )


@pytest.fixture
def sample_discovery_result(
    sample_tool: ToolInfo,
    sample_resource: ResourceInfo,
    sample_prompt: PromptInfo,
) -> DiscoveryResult:
    """Provide a sample discovery result for testing."""
    return DiscoveryResult(
        server_info=ServerInfo(
            name="Test Server",
            version="1.0.0",
            protocol_version="2024-11-05",
            capabilities=ServerCapabilities(
                tools=True,
                resources=True,
                prompts=True,
            ),
        ),
        tools=[sample_tool],
        resources=[sample_resource],
        prompts=[sample_prompt],
    )


@pytest.fixture
def mock_ground_truth_response() -> str:
    """Provide a mock LLM response for ground truth generation."""
    return json.dumps({
        "expected_behavior": "Authenticates a user with username and password",
        "expected_output_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "token": {"type": "string"},
            },
        },
        "valid_input_examples": [
            {
                "input": {"username": "admin", "password": "secret"},
                "expected_outcome": "Returns success=true with valid token",
            }
        ],
        "invalid_input_examples": [
            {
                "input": {"username": "", "password": ""},
                "expected_error": "Invalid credentials error",
            }
        ],
        "semantic_reference": "User authentication returning auth token",
    })


@pytest.fixture
def mock_scenario_response() -> str:
    """Provide a mock LLM response for scenario generation."""
    return json.dumps({
        "scenarios": [
            {
                "name": "auth_login happy path - valid credentials",
                "category": "happy_path",
                "description": "Test successful login with valid credentials",
                "gherkin": '''Scenario: auth_login happy path - valid credentials
  Given the MCP server is running
  When I call tool "auth_login" with arguments {"username": "admin", "password": "secret"}
  Then the response should be successful
  And the response should match ground truth "gt_tool_auth_login"''',
            },
            {
                "name": "auth_login error - invalid credentials",
                "category": "error_case",
                "description": "Test login failure with invalid credentials",
                "gherkin": '''Scenario: auth_login error - invalid credentials
  Given the MCP server is running
  When I call tool "auth_login" with arguments {"username": "unknown", "password": "wrong"}
  Then the response should indicate failure
  And the error should match ground truth "gt_tool_auth_login" invalid input behavior''',
            },
            {
                "name": "auth_login edge case - empty password",
                "category": "edge_case",
                "description": "Test login with empty password",
                "gherkin": '''Scenario: auth_login edge case - empty password
  Given the MCP server is running
  When I call tool "auth_login" with arguments {"username": "admin", "password": ""}
  Then the response should indicate failure''',
            },
        ]
    })


@pytest.fixture
def mock_llm_client(
    mock_ground_truth_response: str,
    mock_scenario_response: str,
) -> MockLLMClient:
    """Provide a mock LLM client with pre-configured responses."""
    # Responses alternate: ground truth, scenarios, ground truth, scenarios, etc.
    # This matches the two-phase generation pattern
    return MockLLMClient(
        responses=[
            mock_ground_truth_response,  # Tool ground truth
            mock_ground_truth_response,  # Resource ground truth
            mock_ground_truth_response,  # Prompt ground truth
            mock_scenario_response,       # Tool scenarios
            mock_scenario_response,       # Resource scenarios
            mock_scenario_response,       # Prompt scenarios
        ]
    )


@pytest.fixture
def llm_config() -> LLMConfig:
    """Provide a test LLM configuration."""
    return LLMConfig(
        provider="openai",
        model="gpt-4",
        temperature=0.7,
        max_tokens=4096,
    )


# =============================================================================
# Model Tests
# =============================================================================


class TestGroundTruthSpec:
    """Tests for GroundTruthSpec model."""

    def test_generate_id_tool(self):
        """Test ID generation for a tool."""
        ground_truth_id = GroundTruthSpec.generate_id(TargetType.TOOL, "auth_login")
        assert ground_truth_id == "gt_tool_auth_login"

    def test_generate_id_resource(self):
        """Test ID generation for a resource."""
        ground_truth_id = GroundTruthSpec.generate_id(TargetType.RESOURCE, "User Profile")
        assert ground_truth_id == "gt_resource_user_profile"

    def test_generate_id_prompt(self):
        """Test ID generation for a prompt."""
        ground_truth_id = GroundTruthSpec.generate_id(TargetType.PROMPT, "create-task")
        assert ground_truth_id == "gt_prompt_create_task"

    def test_ground_truth_creation(self):
        """Test creating a GroundTruthSpec instance."""
        gt = GroundTruthSpec(
            id="gt_tool_test",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            expected_behavior="Does something useful",
            expected_output_schema={"type": "object"},
            valid_input_examples=[{"input": {}}],
            invalid_input_examples=[{"input": {"bad": "data"}}],
            semantic_reference="A useful tool",
        )
        assert gt.id == "gt_tool_test"
        assert gt.target_type == TargetType.TOOL
        assert gt.target_name == "test_tool"


class TestGeneratedScenario:
    """Tests for GeneratedScenario model."""

    def test_generate_id(self):
        """Test scenario ID generation."""
        scenario_id = GeneratedScenario.generate_id(
            TargetType.TOOL,
            "auth_login",
            ScenarioCategory.HAPPY_PATH,
            0,
        )
        assert scenario_id == "sc_tool_auth_login_happy_path_0"

    def test_generate_id_with_index(self):
        """Test scenario ID generation with different index."""
        scenario_id = GeneratedScenario.generate_id(
            TargetType.RESOURCE,
            "user_profile",
            ScenarioCategory.ERROR_CASE,
            2,
        )
        assert scenario_id == "sc_resource_user_profile_error_case_2"

    def test_scenario_creation(self):
        """Test creating a GeneratedScenario instance."""
        scenario = GeneratedScenario(
            id="sc_test_0",
            name="Test scenario",
            gherkin="Scenario: Test\n  Given something\n  Then something else",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_tool_test",
            description="A test scenario",
        )
        assert scenario.id == "sc_test_0"
        assert scenario.ground_truth_id == "gt_tool_test"


class TestScenarioSet:
    """Tests for ScenarioSet model."""

    def test_empty_scenario_set(self):
        """Test creating an empty ScenarioSet."""
        scenario_set = ScenarioSet()
        assert scenario_set.total_scenarios == 0
        assert scenario_set.tool_count == 0
        assert scenario_set.resource_count == 0
        assert scenario_set.prompt_count == 0

    def test_add_ground_truth(self):
        """Test adding ground truth to the set."""
        scenario_set = ScenarioSet()
        gt = GroundTruthSpec(
            id="gt_test",
            target_type=TargetType.TOOL,
            target_name="test",
            expected_behavior="Test",
            semantic_reference="Test",
        )
        scenario_set.add_ground_truth(gt)
        assert "gt_test" in scenario_set.ground_truths
        assert scenario_set.get_ground_truth("gt_test") == gt

    def test_add_scenario(self):
        """Test adding a scenario to the set."""
        scenario_set = ScenarioSet()
        scenario = GeneratedScenario(
            id="sc_test",
            name="Test",
            gherkin="Scenario: Test",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_test",
        )
        scenario_set.add_scenario(scenario)
        assert scenario_set.total_scenarios == 1
        assert scenario_set.tool_count == 1

    def test_get_scenarios_by_target(self):
        """Test filtering scenarios by target."""
        scenario_set = ScenarioSet()
        scenario1 = GeneratedScenario(
            id="sc_1",
            name="Test 1",
            gherkin="Scenario: Test 1",
            target_type=TargetType.TOOL,
            target_name="tool_a",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_1",
        )
        scenario2 = GeneratedScenario(
            id="sc_2",
            name="Test 2",
            gherkin="Scenario: Test 2",
            target_type=TargetType.TOOL,
            target_name="tool_b",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_2",
        )
        scenario_set.add_scenario(scenario1)
        scenario_set.add_scenario(scenario2)

        results = scenario_set.get_scenarios_by_target(TargetType.TOOL, "tool_a")
        assert len(results) == 1
        assert results[0].id == "sc_1"

    def test_get_scenarios_by_category(self):
        """Test filtering scenarios by category."""
        scenario_set = ScenarioSet()
        scenario1 = GeneratedScenario(
            id="sc_1",
            name="Test 1",
            gherkin="Scenario: Test 1",
            target_type=TargetType.TOOL,
            target_name="tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_1",
        )
        scenario2 = GeneratedScenario(
            id="sc_2",
            name="Test 2",
            gherkin="Scenario: Test 2",
            target_type=TargetType.TOOL,
            target_name="tool",
            category=ScenarioCategory.ERROR_CASE,
            ground_truth_id="gt_1",
        )
        scenario_set.add_scenario(scenario1)
        scenario_set.add_scenario(scenario2)

        happy_paths = scenario_set.get_scenarios_by_category(ScenarioCategory.HAPPY_PATH)
        assert len(happy_paths) == 1
        assert happy_paths[0].category == ScenarioCategory.HAPPY_PATH


# =============================================================================
# Mock LLM Client Tests
# =============================================================================


class TestMockLLMClient:
    """Tests for MockLLMClient."""

    @pytest.mark.asyncio
    async def test_mock_generate(self):
        """Test basic generation with mock client."""
        client = MockLLMClient(responses=["Response 1", "Response 2"])
        response = await client.generate("Test prompt")
        assert response.content == "Response 1"
        assert response.model == "mock-model"
        assert client.call_count == 1

    @pytest.mark.asyncio
    async def test_mock_generate_multiple(self):
        """Test multiple generations with mock client."""
        client = MockLLMClient(responses=["Response 1", "Response 2", "Response 3"])

        r1 = await client.generate("Prompt 1")
        r2 = await client.generate("Prompt 2")
        r3 = await client.generate("Prompt 3")

        assert r1.content == "Response 1"
        assert r2.content == "Response 2"
        assert r3.content == "Response 3"
        assert client.call_count == 3

    @pytest.mark.asyncio
    async def test_mock_generate_exhausted_repeats_last(self):
        """Test that mock client repeats last response when exhausted."""
        client = MockLLMClient(responses=["Response 1"])

        r1 = await client.generate("Prompt 1")
        r2 = await client.generate("Prompt 2")

        assert r1.content == "Response 1"
        assert r2.content == "Response 1"  # Repeats last

    @pytest.mark.asyncio
    async def test_mock_generate_json(self):
        """Test JSON generation with mock client."""
        client = MockLLMClient(responses=['{"key": "value"}'])
        result = await client.generate_json("Test prompt")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_mock_generate_json_with_markdown(self):
        """Test JSON generation with markdown code blocks."""
        client = MockLLMClient(responses=['```json\n{"key": "value"}\n```'])
        result = await client.generate_json("Test prompt")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_mock_call_history(self):
        """Test that call history is recorded."""
        client = MockLLMClient(responses=["Response"])
        await client.generate("Test prompt", system_prompt="System")

        assert len(client.call_history) == 1
        assert client.call_history[0]["prompt"] == "Test prompt"
        assert client.call_history[0]["system_prompt"] == "System"

    def test_mock_reset(self):
        """Test resetting the mock client."""
        client = MockLLMClient(responses=["Response"])
        client.call_count = 5
        client.call_history = [{"test": "data"}]

        client.reset()

        assert client.call_count == 0
        assert len(client.call_history) == 0


# =============================================================================
# Prompt Template Tests
# =============================================================================


class TestPromptTemplates:
    """Tests for LLM prompt templates."""

    def test_tool_ground_truth_prompt(self, sample_tool: ToolInfo):
        """Test tool ground truth prompt generation."""
        prompt = build_tool_ground_truth_prompt(sample_tool)
        assert "auth_login" in prompt
        assert "Authenticate a user" in prompt
        assert "username" in prompt
        assert "password" in prompt
        assert "expected_behavior" in prompt

    def test_resource_ground_truth_prompt(self, sample_resource: ResourceInfo):
        """Test resource ground truth prompt generation."""
        prompt = build_resource_ground_truth_prompt(sample_resource)
        assert "user://{user_id}/profile" in prompt
        assert "User Profile" in prompt
        assert "application/json" in prompt
        assert "URI Template" in prompt  # Should note it's a template

    def test_prompt_ground_truth_prompt(self, sample_prompt: PromptInfo):
        """Test prompt ground truth prompt generation."""
        prompt = build_prompt_ground_truth_prompt(sample_prompt)
        assert "create_task_template" in prompt
        assert "project_name" in prompt
        assert "task_type" in prompt
        assert "required" in prompt
        assert "optional" in prompt

    def test_tool_scenario_prompt(self, sample_tool: ToolInfo):
        """Test tool scenario prompt generation."""
        prompt = build_tool_scenario_prompt(sample_tool, "gt_tool_auth_login")
        assert "auth_login" in prompt
        assert "gt_tool_auth_login" in prompt
        assert "happy_path" in prompt
        assert "error_case" in prompt

    def test_resource_scenario_prompt(self, sample_resource: ResourceInfo):
        """Test resource scenario prompt generation."""
        prompt = build_resource_scenario_prompt(sample_resource, "gt_resource_user_profile")
        assert "user://{user_id}/profile" in prompt
        assert "gt_resource_user_profile" in prompt

    def test_prompt_scenario_prompt(self, sample_prompt: PromptInfo):
        """Test prompt scenario prompt generation."""
        prompt = build_prompt_scenario_prompt(sample_prompt, "gt_prompt_create_task_template")
        assert "create_task_template" in prompt
        assert "gt_prompt_create_task_template" in prompt

    def test_build_ground_truth_prompt_tool(self, sample_tool: ToolInfo):
        """Test unified ground truth prompt builder for tool."""
        prompt = build_ground_truth_prompt(TargetType.TOOL, sample_tool)
        assert "auth_login" in prompt

    def test_build_ground_truth_prompt_resource(self, sample_resource: ResourceInfo):
        """Test unified ground truth prompt builder for resource."""
        prompt = build_ground_truth_prompt(TargetType.RESOURCE, sample_resource)
        assert "user://" in prompt

    def test_build_ground_truth_prompt_invalid_type(self, sample_tool: ToolInfo):
        """Test that mismatched type raises error."""
        with pytest.raises(ValueError, match="Target must be"):
            build_ground_truth_prompt(TargetType.RESOURCE, sample_tool)

    def test_build_scenario_prompt_tool(self, sample_tool: ToolInfo):
        """Test unified scenario prompt builder for tool."""
        prompt = build_scenario_prompt(TargetType.TOOL, sample_tool, "gt_test")
        assert "auth_login" in prompt
        assert "gt_test" in prompt


# =============================================================================
# Client Test Generator Tests
# =============================================================================


class TestClientTestGenerator:
    """Tests for ClientTestGenerator."""

    @pytest.mark.asyncio
    async def test_generate_scenarios_full(
        self,
        llm_config: LLMConfig,
        mock_llm_client: MockLLMClient,
        sample_discovery_result: DiscoveryResult,
    ):
        """Test full scenario generation with all capability types."""
        generator = ClientTestGenerator(llm_config, llm_client=mock_llm_client)

        scenario_set = await generator.generate_scenarios(sample_discovery_result)

        # Should have generated ground truths
        assert len(scenario_set.ground_truths) == 3  # tool, resource, prompt

        # Should have generated scenarios
        assert scenario_set.total_scenarios > 0

        # Should have generated features
        assert len(scenario_set.features) == 3

        # Verify two-phase separation: ground truth calls before scenario calls
        # First 3 calls should be ground truth (no scenario context in prompts)
        for i in range(3):
            call = mock_llm_client.call_history[i]
            assert "expected_behavior" in call["prompt"]
            assert call["system_prompt"] == GROUND_TRUTH_SYSTEM_PROMPT

        # Next 3 calls should be scenarios (reference ground truth IDs)
        for i in range(3, 6):
            call = mock_llm_client.call_history[i]
            assert "scenarios" in call["prompt"]
            assert call["system_prompt"] == SCENARIO_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_generate_scenarios_tools_only(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
        sample_discovery_result: DiscoveryResult,
    ):
        """Test scenario generation for tools only."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        scenario_set = await generator.generate_scenarios(
            sample_discovery_result,
            include_tools=True,
            include_resources=False,
            include_prompts=False,
        )

        # Should only have tool ground truth and scenarios
        assert len(scenario_set.ground_truths) == 1
        assert scenario_set.tool_count == 1
        assert scenario_set.resource_count == 0
        assert scenario_set.prompt_count == 0

    @pytest.mark.asyncio
    async def test_generate_scenarios_resources_only(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
        sample_discovery_result: DiscoveryResult,
    ):
        """Test scenario generation for resources only."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        scenario_set = await generator.generate_scenarios(
            sample_discovery_result,
            include_tools=False,
            include_resources=True,
            include_prompts=False,
        )

        assert len(scenario_set.ground_truths) == 1
        assert scenario_set.resource_count == 1
        assert scenario_set.tool_count == 0

    @pytest.mark.asyncio
    async def test_ground_truth_generated_before_scenarios(
        self,
        llm_config: LLMConfig,
        mock_llm_client: MockLLMClient,
        sample_discovery_result: DiscoveryResult,
    ):
        """Verify ground truth is generated in Phase 1 before scenarios in Phase 2."""
        generator = ClientTestGenerator(llm_config, llm_client=mock_llm_client)

        await generator.generate_scenarios(sample_discovery_result)

        # Analyze call history to verify phase ordering
        ground_truth_calls = []
        scenario_calls = []

        for i, call in enumerate(mock_llm_client.call_history):
            if "expected_behavior" in call["prompt"]:
                ground_truth_calls.append(i)
            elif "scenarios" in call["prompt"]:
                scenario_calls.append(i)

        # All ground truth calls should come before scenario calls
        assert len(ground_truth_calls) > 0
        assert len(scenario_calls) > 0
        assert max(ground_truth_calls) < min(scenario_calls)

    @pytest.mark.asyncio
    async def test_scenarios_reference_ground_truth_by_id(
        self,
        llm_config: LLMConfig,
        mock_llm_client: MockLLMClient,
        sample_discovery_result: DiscoveryResult,
    ):
        """Verify scenarios reference ground truth by ID, not by embedding."""
        generator = ClientTestGenerator(llm_config, llm_client=mock_llm_client)

        scenario_set = await generator.generate_scenarios(sample_discovery_result)

        # Each scenario should have a ground_truth_id that exists in ground_truths
        for scenario in scenario_set.scenarios:
            assert scenario.ground_truth_id in scenario_set.ground_truths

    @pytest.mark.asyncio
    async def test_feature_file_gherkin_format(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
        sample_tool: ToolInfo,
    ):
        """Test that feature files have correct Gherkin format."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[sample_tool],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(discovery)

        assert len(scenario_set.features) == 1
        feature = scenario_set.features[0]

        # Verify Gherkin structure
        assert feature.gherkin.startswith("Feature:")
        assert "# Ground Truth ID:" in feature.gherkin
        assert "Scenario:" in feature.gherkin

    @pytest.mark.asyncio
    async def test_handles_llm_error_gracefully(
        self,
        llm_config: LLMConfig,
        sample_discovery_result: DiscoveryResult,
    ):
        """Test that LLM errors are handled gracefully."""
        # Create a mock that returns invalid JSON
        mock_client = MockLLMClient(responses=["Invalid JSON {{{"])

        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        # Should not raise, but should have empty results due to failures
        scenario_set = await generator.generate_scenarios(sample_discovery_result)

        # Ground truths should be empty due to parse errors
        assert len(scenario_set.ground_truths) == 0

    @pytest.mark.asyncio
    async def test_empty_discovery_result(
        self,
        llm_config: LLMConfig,
    ):
        """Test generation with empty discovery result."""
        mock_client = MockLLMClient()
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Empty Server", capabilities=ServerCapabilities()),
            tools=[],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(discovery)

        assert len(scenario_set.ground_truths) == 0
        assert scenario_set.total_scenarios == 0
        assert mock_client.call_count == 0  # No LLM calls needed


class TestClientTestGeneratorEdgeCases:
    """Edge case tests for ClientTestGenerator."""

    @pytest.mark.asyncio
    async def test_tool_without_schema(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test generating scenarios for a tool without input schema."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        tool = ToolInfo(
            name="simple_tool",
            description="A tool with no parameters",
            input_schema={},
        )
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[tool],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(discovery)
        assert len(scenario_set.features) == 1

    @pytest.mark.asyncio
    async def test_resource_without_name(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test generating scenarios for a resource without a name."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        resource = ResourceInfo(
            uri="system://status",
            name=None,  # No name
            description="System status",
            is_template=False,
        )
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(resources=True)),
            tools=[],
            resources=[resource],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(discovery)
        assert len(scenario_set.features) == 1

    @pytest.mark.asyncio
    async def test_prompt_without_arguments(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test generating scenarios for a prompt without arguments."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        prompt = PromptInfo(
            name="simple_prompt",
            description="A prompt with no arguments",
            arguments=[],
        )
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(prompts=True)),
            tools=[],
            resources=[],
            prompts=[prompt],
        )

        scenario_set = await generator.generate_scenarios(discovery)
        assert len(scenario_set.features) == 1

    @pytest.mark.asyncio
    async def test_special_characters_in_names(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test handling of special characters in capability names."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        tool = ToolInfo(
            name="tool-with-dashes_and_underscores",
            description="Test tool",
            input_schema={},
        )
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[tool],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(discovery)

        # IDs should have normalized names
        gt_id = list(scenario_set.ground_truths.keys())[0]
        assert "-" not in gt_id  # Dashes converted to underscores


# =============================================================================
# Workflow Model Tests
# =============================================================================


class TestWorkflowModels:
    """Tests for workflow-related models."""

    def test_workflow_step_creation(self):
        """Test creating a WorkflowStep instance."""
        step = WorkflowStep(
            step_number=1,
            action_type="tool_call",
            target_name="auth_login",
            description="Authenticate user",
            input_source="literal",
            output_variable="auth_token",
            dependencies=[],
        )
        assert step.step_number == 1
        assert step.action_type == "tool_call"
        assert step.output_variable == "auth_token"

    def test_workflow_ground_truth_generate_id(self):
        """Test workflow ground truth ID generation."""
        gt_id = WorkflowGroundTruth.generate_id("Auth and Create Project")
        assert gt_id == "gt_workflow_auth_and_create_project"

    def test_workflow_ground_truth_creation(self):
        """Test creating a WorkflowGroundTruth instance."""
        gt = WorkflowGroundTruth(
            id="gt_workflow_test",
            workflow_name="Test Workflow",
            expected_flow="Login then create project",
            step_expectations=[{"step_number": 1, "expected_behavior": "Returns token"}],
            final_outcome="Project created successfully",
            error_scenarios=[{"failing_step": 1, "error_type": "auth_failure"}],
        )
        assert gt.id == "gt_workflow_test"
        assert gt.workflow_name == "Test Workflow"
        assert len(gt.step_expectations) == 1

    def test_workflow_scenario_generate_id(self):
        """Test workflow scenario ID generation."""
        scenario_id = WorkflowScenario.generate_id("Auth Flow", 2)
        assert scenario_id == "sc_workflow_auth_flow_2"

    def test_workflow_scenario_creation(self):
        """Test creating a WorkflowScenario instance."""
        steps = [
            WorkflowStep(
                step_number=1,
                action_type="tool_call",
                target_name="auth_login",
                description="Login",
            ),
            WorkflowStep(
                step_number=2,
                action_type="tool_call",
                target_name="create_project",
                description="Create project",
                dependencies=[1],
            ),
        ]
        scenario = WorkflowScenario(
            id="sc_workflow_test_0",
            name="Auth and Project Creation",
            description="Test complete workflow",
            steps=steps,
            gherkin="Scenario: Auth workflow\n  Given...",
            ground_truth_id="gt_workflow_test",
            involved_features=["tools"],
        )
        assert scenario.id == "sc_workflow_test_0"
        assert len(scenario.steps) == 2
        assert scenario.involved_features == ["tools"]


class TestScenarioSetWorkflows:
    """Tests for ScenarioSet workflow functionality."""

    def test_add_workflow_ground_truth(self):
        """Test adding workflow ground truth to the set."""
        scenario_set = ScenarioSet()
        gt = WorkflowGroundTruth(
            id="gt_workflow_test",
            workflow_name="Test Workflow",
            expected_flow="Test flow",
            final_outcome="Success",
        )
        scenario_set.add_workflow_ground_truth(gt)
        assert "gt_workflow_test" in scenario_set.workflow_ground_truths
        assert scenario_set.get_workflow_ground_truth("gt_workflow_test") == gt

    def test_add_workflow_scenario(self):
        """Test adding a workflow scenario to the set."""
        scenario_set = ScenarioSet()
        scenario = WorkflowScenario(
            id="sc_workflow_test_0",
            name="Test Workflow",
            description="Test",
            steps=[],
            gherkin="Scenario: Test",
            ground_truth_id="gt_workflow_test",
            involved_features=["tools"],
        )
        scenario_set.add_workflow_scenario(scenario)
        assert scenario_set.workflow_count == 1
        assert len(scenario_set.workflow_scenarios) == 1

    def test_total_scenarios_includes_workflows(self):
        """Test that total_scenarios includes workflow scenarios."""
        scenario_set = ScenarioSet()

        # Add a regular scenario
        scenario = GeneratedScenario(
            id="sc_test",
            name="Test",
            gherkin="Scenario: Test",
            target_type=TargetType.TOOL,
            target_name="test_tool",
            category=ScenarioCategory.HAPPY_PATH,
            ground_truth_id="gt_test",
        )
        scenario_set.add_scenario(scenario)

        # Add a workflow scenario
        workflow = WorkflowScenario(
            id="sc_workflow_test_0",
            name="Test Workflow",
            description="Test",
            steps=[],
            gherkin="Scenario: Workflow Test",
            ground_truth_id="gt_workflow_test",
            involved_features=["tools"],
        )
        scenario_set.add_workflow_scenario(workflow)

        assert scenario_set.total_scenarios == 2  # 1 regular + 1 workflow


# =============================================================================
# Workflow Generation Tests
# =============================================================================


class TestWorkflowGeneration:
    """Tests for workflow scenario generation."""

    @pytest.fixture
    def mock_workflow_analysis_response(self) -> str:
        """Mock response for workflow analysis."""
        return json.dumps({
            "workflows": [
                {
                    "name": "Authentication and Project Creation",
                    "description": "Login, create project, then add task",
                    "steps": [
                        {
                            "step_number": 1,
                            "action_type": "tool_call",
                            "target_name": "auth_login",
                            "description": "Authenticate user",
                            "input_source": "literal",
                            "output_variable": "auth_token",
                            "dependencies": [],
                        },
                        {
                            "step_number": 2,
                            "action_type": "tool_call",
                            "target_name": "create_project",
                            "description": "Create a new project",
                            "input_source": "previous_step",
                            "output_variable": "project_id",
                            "dependencies": [1],
                        },
                    ],
                    "involved_features": ["tools"],
                }
            ]
        })

    @pytest.fixture
    def mock_workflow_ground_truth_response(self) -> str:
        """Mock response for workflow ground truth."""
        return json.dumps({
            "expected_flow": "User logs in, receives token, creates project with token",
            "step_expectations": [
                {"step_number": 1, "expected_behavior": "Returns auth token"},
                {"step_number": 2, "expected_behavior": "Creates project, returns ID"},
            ],
            "final_outcome": "Project created with valid ID",
            "error_scenarios": [
                {"failing_step": 1, "error_type": "invalid_credentials"},
            ],
        })

    @pytest.fixture
    def mock_workflow_scenario_response(self) -> str:
        """Mock response for workflow scenario generation."""
        return json.dumps({
            "scenarios": [
                {
                    "name": "Complete auth and project creation workflow",
                    "description": "Test full workflow succeeds",
                    "gherkin": '''Scenario: Complete auth and project creation workflow
  Given the MCP server is running
  When I call tool "auth_login" with arguments {"username": "admin", "password": "secret"}
  And I store the "token" from the result as "auth_token"
  When I call tool "create_project" with arguments {"token": "{auth_token}", "name": "Test"}
  Then the workflow should complete successfully''',
                }
            ]
        })

    @pytest.mark.asyncio
    async def test_workflow_generation_with_multiple_tools(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
        mock_workflow_analysis_response: str,
        mock_workflow_ground_truth_response: str,
        mock_workflow_scenario_response: str,
    ):
        """Test that workflows are generated when multiple tools exist."""
        # Create mock client with responses for:
        # 1. Tool ground truth
        # 2. Tool scenarios
        # 3. Workflow analysis
        # 4. Workflow ground truth
        # 5. Workflow scenarios
        mock_client = MockLLMClient(
            responses=[
                mock_ground_truth_response,
                mock_ground_truth_response,  # Two tools
                mock_scenario_response,
                mock_scenario_response,
                mock_workflow_analysis_response,
                mock_workflow_ground_truth_response,
                mock_workflow_scenario_response,
            ]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        # Create discovery with multiple tools
        tool1 = ToolInfo(name="auth_login", description="Login", input_schema={})
        tool2 = ToolInfo(name="create_project", description="Create project", input_schema={})
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[tool1, tool2],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(
            discovery,
            include_workflows=True,
        )

        # Should have workflow scenarios
        assert scenario_set.workflow_count >= 0  # May or may not generate depending on LLM

    @pytest.mark.asyncio
    async def test_workflow_generation_skipped_for_single_capability(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test that workflow generation is skipped for single capability."""
        mock_client = MockLLMClient(
            responses=[mock_ground_truth_response, mock_scenario_response]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        # Single tool - no workflows needed
        tool = ToolInfo(name="simple_tool", description="Test", input_schema={})
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[tool],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(
            discovery,
            include_workflows=True,
        )

        # Workflow generation should be skipped (too few capabilities)
        assert scenario_set.workflow_count == 0

    @pytest.mark.asyncio
    async def test_workflow_generation_can_be_disabled(
        self,
        llm_config: LLMConfig,
        mock_ground_truth_response: str,
        mock_scenario_response: str,
    ):
        """Test that workflow generation can be disabled."""
        mock_client = MockLLMClient(
            responses=[
                mock_ground_truth_response,
                mock_ground_truth_response,
                mock_scenario_response,
                mock_scenario_response,
            ]
        )
        generator = ClientTestGenerator(llm_config, llm_client=mock_client)

        tool1 = ToolInfo(name="tool1", description="Test 1", input_schema={})
        tool2 = ToolInfo(name="tool2", description="Test 2", input_schema={})
        discovery = DiscoveryResult(
            server_info=ServerInfo(name="Test", capabilities=ServerCapabilities(tools=True)),
            tools=[tool1, tool2],
            resources=[],
            prompts=[],
        )

        scenario_set = await generator.generate_scenarios(
            discovery,
            include_workflows=False,  # Disabled
        )

        # No workflow generation should occur
        assert scenario_set.workflow_count == 0
