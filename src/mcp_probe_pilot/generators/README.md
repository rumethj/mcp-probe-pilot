# Test Generators Module

The generators module provides LLM-powered test generation capabilities for MCP servers. It generates Gherkin BDD test scenarios from server discovery results using a multi-phase approach that prevents ground truth poisoning, and converts them into executable Behave tests.

**Key Features:**
- Two-phase generation for single-feature tests (ground truth → scenarios)
- **Workflow generation** for multi-step chained scenarios (tools + resources + prompts + sampling + elicitation)
- **Test implementation** - converts Gherkin scenarios into executable Behave tests
- **Service integration** - stores tests and ground truths in mcp-probe-service
- Support for OpenAI, Anthropic, and Gemini LLM providers
- Mock client for testing without API calls

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ClientTestGenerator                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     Phase 1: Ground Truth Generation                   │
│  │ DiscoveryResult │     (Isolated Context - No Scenario Info)              │
│  │  - Tools        │───────────────────────────────────────┐                │
│  │  - Resources    │                                       │                │
│  │  - Prompts      │     ┌──────────────────────┐          │                │
│  └─────────────────┘     │  Ground Truth Prompt │          │                │
│                          │  (schema + desc only)│          ▼                │
│                          └──────────┬───────────┘    ┌───────────┐          │
│                                     │                │ LLM Call  │          │
│                                     ▼                │   #1      │          │
│                          ┌──────────────────────┐    └─────┬─────┘          │
│                          │   GroundTruthSpec    │◄─────────┘                │
│                          │   - expected_behavior│                           │
│                          │   - output_schema    │                           │
│                          │   - valid_examples   │                           │
│                          │   - semantic_ref     │                           │
│                          └──────────┬───────────┘                           │
│                                     │                                       │
│                                     │ ID Reference Only                     │
│                                     ▼                                       │
│                          ┌──────────────────────┐                           │
│                          │   Scenario Prompt    │     Phase 2: Scenarios    │
│                          │ (schema + GT ID ref) │     (Separate Context)    │
│                          └──────────┬───────────┘                           │
│                                     │                                       │
│                                     ▼                ┌───────────┐          │
│                          ┌──────────────────────┐    │ LLM Call  │          │
│                          │  GeneratedScenario   │◄───│   #2      │          │
│                          │   - gherkin text     │    └───────────┘          │
│                          │   - ground_truth_id  │                           │
│                          │   - category         │                           │
│                          └──────────────────────┘                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Design Decision: Two-Phase Generation

Ground truth and Gherkin scenarios are generated in **separate LLM calls** to prevent ground truth poisoning:

1. **Phase 1 (Ground Truth)**: Input is ONLY the capability schema and description - no scenario context
2. **Phase 2 (Scenarios)**: References ground truth by ID only, doesn't embed or re-derive it

This ensures ground truth represents what the capability **should** do (from its definition), not what the test scenarios **expect** it to do.

## Components

### Models (`models.py`)

**Single-Feature Models:**

| Model | Description |
|-------|-------------|
| `TargetType` | Enum for capability types (TOOL, RESOURCE, PROMPT) |
| `ScenarioCategory` | Enum for scenario categories (HAPPY_PATH, ERROR_CASE, EDGE_CASE, WORKFLOW) |
| `GroundTruthSpec` | Ground truth specification with expected behavior and examples |
| `GeneratedScenario` | A single Gherkin scenario with ground truth reference |
| `FeatureFile` | A complete Gherkin feature file with multiple scenarios |
| `ScenarioSet` | Collection of all generated ground truths and scenarios |

**Workflow Models:**

| Model | Description |
|-------|-------------|
| `WorkflowStep` | A single step in a workflow (action type, target, dependencies) |
| `WorkflowGroundTruth` | Ground truth for multi-step workflows |
| `WorkflowScenario` | A complete workflow scenario with chained steps |

### LLM Client (`llm_client.py`)

| Class | Description |
|-------|-------------|
| `BaseLLMClient` | Abstract base class for LLM providers |
| `OpenAIClient` | OpenAI API implementation |
| `AnthropicClient` | Anthropic API implementation |
| `MockLLMClient` | Mock client for testing (no API calls) |
| `create_llm_client()` | Factory function to create appropriate client |

### Prompts (`prompts.py`)

Separate prompt templates for:
- **Ground Truth Generation**: `GROUND_TRUTH_SYSTEM_PROMPT`, `build_*_ground_truth_prompt()`
- **Scenario Generation**: `SCENARIO_SYSTEM_PROMPT`, `build_*_scenario_prompt()`

### Generator (`client_generator.py`)

Main class: `ClientTestGenerator`

```python
from mcp_probe_pilot.config import LLMConfig
from mcp_probe_pilot.generators import ClientTestGenerator

config = LLMConfig(provider="openai", model="gpt-4")
generator = ClientTestGenerator(config)

# discovery_result from MCPDiscoveryClient
scenario_set = await generator.generate_scenarios(discovery_result)

print(f"Generated {scenario_set.total_scenarios} scenarios")
print(f"Ground truths: {len(scenario_set.ground_truths)}")
```

## Usage Example

```python
import asyncio
from mcp_probe_pilot.config import LLMConfig
from mcp_probe_pilot.discovery import MCPDiscoveryClient
from mcp_probe_pilot.generators import ClientTestGenerator

async def generate_tests():
    # 1. Discover server capabilities
    async with MCPDiscoveryClient("python -m my_server") as client:
        discovery = await client.discover_all()
    
    # 2. Configure the generator
    config = LLMConfig(
        provider="openai",
        model="gpt-4",
        temperature=0.7,
    )
    generator = ClientTestGenerator(config)
    
    # 3. Generate scenarios (multi-phase process)
    scenario_set = await generator.generate_scenarios(
        discovery,
        include_tools=True,
        include_resources=True,
        include_prompts=True,
        include_workflows=True,  # Generate chained multi-step scenarios
    )
    
    # 4. Access single-feature results
    for feature in scenario_set.features:
        print(f"\n{feature.name}")
        print(feature.gherkin)
    
    # 5. Access workflow results
    print(f"\n=== Workflow Scenarios ({scenario_set.workflow_count}) ===")
    for workflow in scenario_set.workflow_scenarios:
        print(f"\n{workflow.name}")
        print(f"Features involved: {', '.join(workflow.involved_features)}")
        print(f"Steps: {len(workflow.steps)}")
        print(workflow.gherkin)
    
    # 6. Access ground truth separately
    for gt_id, gt in scenario_set.ground_truths.items():
        print(f"\n{gt_id}: {gt.semantic_reference}")

asyncio.run(generate_tests())
```

## Output Format

### Single-Feature Gherkin Scenarios

```gherkin
Feature: Tool - auth_login
  # Ground Truth ID: gt_tool_auth_login

  Scenario: auth_login happy path - valid credentials
    Given the MCP server is running
    When I call tool "auth_login" with arguments {"username": "admin", "password": "secret"}
    Then the response should be successful
    And the response should match ground truth "gt_tool_auth_login"

  Scenario: auth_login error - invalid credentials
    Given the MCP server is running
    When I call tool "auth_login" with arguments {"username": "unknown", "password": "wrong"}
    Then the response should indicate graceful failure
    And the error should match ground truth "gt_tool_auth_login" invalid input behavior
```

### Workflow Scenarios (Chained Multi-Step)

Workflow scenarios test realistic usage patterns where multiple MCP features must be chained together:

```gherkin
Feature: Workflow - Authentication and Project Creation
  # Ground Truth ID: gt_workflow_auth_and_project_creation

  Scenario: Complete authentication and project creation workflow
    Given the MCP server is running
    # Step 1: Authenticate
    When I call tool "auth_login" with arguments {"username": "admin", "password": "secret"}
    And I store the "token" from the result as "auth_token"
    # Step 2: Create project using auth token
    When I call tool "create_project" with arguments {"token": "{auth_token}", "name": "Test Project"}
    And I store the "project_id" from the result as "new_project_id"
    # Step 3: Add task to project
    When I call tool "add_task" with arguments {"token": "{auth_token}", "project_id": "{new_project_id}", "title": "First Task"}
    Then the workflow should complete successfully
    And all steps should match ground truth "gt_workflow_auth_and_project_creation"

  Scenario: Workflow fails gracefully on invalid authentication
    Given the MCP server is running
    When I call tool "auth_login" with arguments {"username": "invalid", "password": "wrong"}
    Then the workflow should fail at step 1
    And subsequent steps should not execute
```

### Workflow Types Detected

The generator analyzes server capabilities to identify:

| Pattern | Description | Example |
|---------|-------------|---------|
| **Authentication chains** | Login → use token for operations | auth_login → create_project |
| **Create-then-use** | Create entity → perform operations | create_project → add_task |
| **Read-then-act** | Read resource → use data in tool | read config → configure |
| **Sampling workflows** | Tools that trigger LLM sampling | generate_summary (with sampling) |
| **Elicitation workflows** | Tools requiring user confirmation | delete_project (with elicitation) |

### Ground Truth Structure

```json
{
  "id": "gt_tool_auth_login",
  "target_type": "tool",
  "target_name": "auth_login",
  "expected_behavior": "Authenticates a user with username and password credentials",
  "expected_output_schema": {
    "type": "object",
    "properties": {
      "success": {"type": "boolean"},
      "token": {"type": "string"}
    }
  },
  "valid_input_examples": [
    {
      "input": {"username": "admin", "password": "secret"},
      "expected_outcome": "Returns success=true with valid JWT token"
    }
  ],
  "invalid_input_examples": [
    {
      "input": {"username": "", "password": ""},
      "expected_error": "Returns error with invalid credentials message"
    }
  ],
  "semantic_reference": "User authentication returning authentication token"
}
```

## Testing

The module includes comprehensive tests using `MockLLMClient` to avoid actual API calls:

```bash
# Run all generator tests
pytest tests/test_generators.py -v

# Run specific test class
pytest tests/test_generators.py::TestClientTestGenerator -v
```

## Configuration

The generator uses `LLMConfig` from the config module:

```python
from mcp_probe_pilot.config import LLMConfig

config = LLMConfig(
    provider="openai",      # or "anthropic"
    model="gpt-4",          # model identifier
    temperature=0.7,        # 0.0 to 1.0
    max_tokens=4096,        # max response tokens
)
```

API keys are loaded from environment variables:
- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`

## Extending

### Custom LLM Client

Implement `BaseLLMClient` for other providers:

```python
from mcp_probe_pilot.generators.llm_client import BaseLLMClient, LLMResponse

class CustomLLMClient(BaseLLMClient):
    async def generate(self, prompt: str, system_prompt: str = None) -> LLMResponse:
        # Your implementation
        return LLMResponse(content="...", model="custom")
```

### Custom Prompt Templates

Modify prompts in `prompts.py` to customize generation behavior while maintaining the two-phase separation.

---

## Test Implementor

The `TestImplementor` class converts generated Gherkin scenarios into executable Behave BDD tests. It uses LLM to generate Python step definitions that implement the test logic.

### Components

| Component | Description |
|-----------|-------------|
| `TestImplementor` | Main class that generates executable Behave tests |
| `TestImplementation` | Result model containing paths to generated files |
| `TestImplementorError` | Exception for implementation failures |

### Generated Files

The TestImplementor generates the following structure:

```
output_dir/
├── features/
│   ├── tool_*.feature                 # Feature files for tools
│   ├── resource_*.feature             # Feature files for resources
│   ├── prompt_*.feature               # Feature files for prompts
│   ├── workflow_*.feature             # Workflow feature files
│   ├── environment.py                 # Behave hooks and setup
│   ├── ground_truth_client.py         # Runtime client for ground truths
│   └── steps/
│       ├── __init__.py
│       └── mcp_steps.py               # LLM-generated step definitions
└── scenario_set.json                  # Backup of generated scenarios
```

### Usage

```python
from mcp_probe_pilot.config import LLMConfig
from mcp_probe_pilot.generators import TestImplementor

config = LLMConfig(provider="openai", model="gpt-4")
implementor = TestImplementor(config)

# Generate executable Behave tests
result = await implementor.implement_tests(
    scenario_set=scenario_set,
    output_dir=Path(".mcp-probe"),
    project_code="my-project",
    service_url="http://localhost:8000",
    server_command="python -m my_server",
)

print(f"Generated {result.feature_count} feature files")
print(f"Step definitions: {result.step_definitions_file}")
print(f"Environment: {result.environment_file}")
```

### Service Integration

The generated tests access ground truths from mcp-probe-service at runtime:

1. **environment.py** - Sets up the test environment with:
   - MCP client for server communication
   - Ground truth client for fetching from mcp-probe-service
   - Shared context for storing values between steps

2. **ground_truth_client.py** - Fetches ground truths via HTTP:
   - Caches ground truths for efficiency
   - Provides async `get(ground_truth_id)` method

3. **Step definitions** - Use the context to:
   - Connect to the MCP server
   - Call tools, read resources, get prompts
   - Fetch and validate against ground truths

### Running Generated Tests

```bash
# Ensure mcp-probe-service is running
cd mcp-probe-service && docker-compose up -d

# Run Behave tests
cd .mcp-probe && behave

# Run specific feature
behave features/tool_auth_login.feature
```

### Environment Variables

The generated tests support these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PROBE_SERVICE_URL` | `http://localhost:8080` | URL of mcp-probe-service |
| `MCP_PROBE_PROJECT_CODE` | From config | Project code for ground truth lookups |
| `MCP_SERVER_COMMAND` | From config | Command to start MCP server |
