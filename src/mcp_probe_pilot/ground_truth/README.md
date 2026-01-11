# Ground Truth Store Module

This module provides storage and retrieval of ground truth data for test assertions in MCP-Probe-Pilot.

## Overview

Ground truths define the expected behavior and output specifications for MCP server capabilities. They are used by the LLM Oracle to evaluate test results semantically and by the test runner to perform structural assertions.

### Key Components

- **`GroundTruthSpec`**: Ground truth for individual capabilities (tools, resources, prompts)
- **`WorkflowGroundTruth`**: Ground truth for multi-step workflow scenarios
- **`GroundTruthCollection`**: Container for all ground truths with metadata
- **`GroundTruthStore`**: File-based storage manager with sync capabilities

## Architecture

```
.mcp-probe/
└── {project_code}/
    └── ground_truths.json    # Per-project ground truth storage
```

## Usage

### Creating a Store

```python
from mcp_probe_pilot.ground_truth import GroundTruthStore

# Initialize store for a project
store = GroundTruthStore(
    project_code="my-server",
    output_dir=".mcp-probe"  # default
)
```

### Saving Ground Truths

```python
from mcp_probe_pilot.ground_truth import GroundTruthSpec, TargetType

# Create a ground truth
gt = GroundTruthSpec(
    id="gt_tool_get_user",
    target_type=TargetType.TOOL,
    target_name="get_user",
    expected_behavior="Retrieves user details by ID",
    expected_output_schema={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string"}
        },
        "required": ["id", "name"]
    },
    valid_input_examples=[
        {"input": {"user_id": "123"}, "expected": "user object"}
    ],
    invalid_input_examples=[
        {"input": {}, "expected_error": "user_id required"}
    ],
    semantic_reference="Returns user object with id, name, and optional email"
)

# Save to storage
collection = store.save(
    ground_truths={gt.id: gt},
    workflow_ground_truths={}
)
```

### Loading Ground Truths

```python
# Load all ground truths
collection = store.load()
print(f"Loaded {collection.total_count} ground truths")

# Load specific ground truth by ID
gt = store.load_by_id("gt_tool_get_user")
if gt:
    print(f"Expected behavior: {gt.expected_behavior}")
```

### Updating Ground Truths

```python
# Update an existing ground truth
updated_gt = GroundTruthSpec(
    id="gt_tool_get_user",
    target_type=TargetType.TOOL,
    target_name="get_user",
    expected_behavior="UPDATED: Retrieves user details with profile",
    # ... other fields
)

success = store.update("gt_tool_get_user", updated_gt)
```

### Deleting Ground Truths

```python
# Delete a specific ground truth
success = store.delete("gt_tool_get_user")

# Clear all ground truths for the project
store.clear()
```

### Syncing to Service

```python
# Upload ground truths to mcp-probe-service
success = await store.sync_to_service("http://localhost:8000")
```

### Creating from ScenarioSet

After test generation, you can create a store directly from the scenario set:

```python
from mcp_probe_pilot.ground_truth import GroundTruthStore

# scenario_set is returned by ClientTestGenerator.generate_scenarios()
store = GroundTruthStore.from_scenario_set(
    project_code="my-server",
    scenario_set=scenario_set,
    output_dir=".mcp-probe"
)
```

## Data Models

### GroundTruthSpec

Ground truth for individual MCP capabilities:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier (e.g., "gt_tool_auth_login") |
| `target_type` | `TargetType` | Type: tool, resource, or prompt |
| `target_name` | `str` | Name of the capability |
| `expected_behavior` | `str` | Natural language description |
| `expected_output_schema` | `dict` | JSON Schema for response structure |
| `valid_input_examples` | `list[dict]` | Sample valid inputs |
| `invalid_input_examples` | `list[dict]` | Sample invalid inputs |
| `semantic_reference` | `str` | Concise description for LLM oracle |

### WorkflowGroundTruth

Ground truth for multi-step workflow scenarios:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier (e.g., "gt_workflow_auth_flow") |
| `workflow_name` | `str` | Descriptive workflow name |
| `expected_flow` | `str` | Description of execution flow |
| `step_expectations` | `list[dict]` | Expected behavior per step |
| `final_outcome` | `str` | Expected final result |
| `error_scenarios` | `list[dict]` | Expected error handling |

### GroundTruthCollection

Container with metadata for file storage:

| Field | Type | Description |
|-------|------|-------------|
| `project_code` | `str` | Project identifier |
| `version` | `int` | Incremented on each save |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |
| `ground_truths` | `dict[str, GroundTruthSpec]` | Capability ground truths |
| `workflow_ground_truths` | `dict[str, WorkflowGroundTruth]` | Workflow ground truths |

## File Format

Ground truths are stored as JSON:

```json
{
  "project_code": "my-server",
  "version": 1,
  "created_at": "2026-01-11T10:00:00",
  "updated_at": "2026-01-11T10:00:00",
  "ground_truths": {
    "gt_tool_get_user": {
      "id": "gt_tool_get_user",
      "target_type": "tool",
      "target_name": "get_user",
      "expected_behavior": "Retrieves user details by ID",
      "expected_output_schema": {...},
      "valid_input_examples": [...],
      "invalid_input_examples": [...],
      "semantic_reference": "Returns user object with id and name"
    }
  },
  "workflow_ground_truths": {
    "gt_workflow_auth_flow": {
      "id": "gt_workflow_auth_flow",
      "workflow_name": "auth_flow",
      "expected_flow": "Login -> Access Resource -> Logout",
      "step_expectations": [...],
      "final_outcome": "User authenticated and logged out",
      "error_scenarios": [...]
    }
  }
}
```

## Integration with Test Generation

Ground truths are generated during the test generation phase by `ClientTestGenerator`:

1. **Phase 1**: Ground truths are generated from capability definitions (isolated context)
2. **Phase 2**: Test scenarios reference ground truths by ID
3. **Storage**: Ground truths are saved for use during test execution

```python
from mcp_probe_pilot.generators import ClientTestGenerator
from mcp_probe_pilot.ground_truth import GroundTruthStore

# Generate tests (includes ground truth generation)
generator = ClientTestGenerator(llm_config)
scenario_set = await generator.generate_scenarios(discovery)

# Save ground truths separately for test execution
store = GroundTruthStore.from_scenario_set(
    project_code=config.project_code,
    scenario_set=scenario_set,
)
```

## Error Handling

The module raises `GroundTruthStoreError` for storage-related errors:

```python
from mcp_probe_pilot.ground_truth import GroundTruthStore, GroundTruthStoreError

try:
    collection = store.load()
except GroundTruthStoreError as e:
    print(f"Failed to load ground truths: {e}")
```

## Service Synchronization

Ground truths can be synced to `mcp-probe-service` for centralized storage:

```python
# Sync after generation
success = await store.sync_to_service(config.service_url)

if success:
    print("Ground truths synced to service")
else:
    print("Sync failed - check service availability")
```

The service stores ground truths in a dedicated database table for:
- Cross-project ground truth management
- Historical tracking
- Dashboard visualization
