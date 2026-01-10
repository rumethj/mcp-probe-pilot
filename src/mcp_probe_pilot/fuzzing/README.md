# Fuzzing Module

The fuzzing module provides strategies and generators for creating fuzz test scenarios that test server robustness against invalid, malformed, and edge-case inputs.

## Overview

Fuzzing is applied **after** base test scenarios are generated, producing additional test cases that verify the server handles invalid inputs gracefully (returning proper JSON-RPC error codes) rather than crashing or exposing stack traces.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   FuzzScenarioGenerator                     │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │
│  │ InvalidType   │  │ BoundaryValue │  │ NullMissing   │   │
│  │   Strategy    │  │   Strategy    │  │   Strategy    │   │
│  └───────────────┘  └───────────────┘  └───────────────┘   │
│                                                             │
│  Input: ScenarioSet with base scenarios + ground truths    │
│  Output: ScenarioSet with fuzz scenarios + fuzz GTs added  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Fuzzing Strategies

#### InvalidTypeStrategy

Generates values of incorrect types to test server type validation.

| Expected Type | Fuzz Values Generated |
|---------------|----------------------|
| `string` | integer, float, boolean, array, object |
| `integer` | string, float, boolean, array, object |
| `number` | string, boolean, array, object |
| `boolean` | string "true", integer 1/0, array |
| `array` | string, integer, object, boolean |
| `object` | string, integer, array, boolean |

#### BoundaryValueStrategy

Tests boundary values and edge cases based on schema constraints.

| Type | Boundary Values |
|------|-----------------|
| `string` | empty "", whitespace-only, single char, strings violating minLength/maxLength, control characters |
| `integer` | 0, -1, MAX_INT, MIN_INT, values violating minimum/maximum |
| `number` | above plus: Infinity, -Infinity, NaN |
| `array` | empty [], arrays violating minItems/maxItems |
| `object` | empty {} |

#### NullMissingStrategy

Tests null values and missing required parameters.

| Scenario | Fuzz Value |
|----------|------------|
| Any parameter | `null` value |
| Required parameter | Omit from request entirely |

### FuzzScenarioGenerator

The main generator class that applies fuzzing strategies to existing scenarios.

## Usage

### Basic Usage

```python
from mcp_probe_pilot.fuzzing import FuzzScenarioGenerator

# Create generator with default settings
# (fuzzes HAPPY_PATH and EDGE_CASE scenarios)
generator = FuzzScenarioGenerator()

# Apply fuzzing to existing scenarios
fuzzed_set = generator.apply_fuzzing(scenario_set)

# Check statistics
stats = generator.get_fuzz_statistics(scenario_set, fuzzed_set)
print(f"Generated {stats['new_fuzz_scenarios']} fuzz scenarios")
```

### Custom Category Configuration

```python
from mcp_probe_pilot.fuzzing import FuzzScenarioGenerator
from mcp_probe_pilot.generators.models import ScenarioCategory

# Only fuzz happy path scenarios
generator = FuzzScenarioGenerator(
    categories=[ScenarioCategory.HAPPY_PATH]
)

fuzzed_set = generator.apply_fuzzing(scenario_set)
```

### Custom Strategy Configuration

```python
from mcp_probe_pilot.fuzzing import (
    FuzzScenarioGenerator,
    InvalidTypeStrategy,
    BoundaryValueStrategy,
)

# Only use specific strategies
generator = FuzzScenarioGenerator(
    strategies=[InvalidTypeStrategy(), BoundaryValueStrategy()]
)

fuzzed_set = generator.apply_fuzzing(scenario_set)
```

### Limiting Fuzz Scenarios

```python
# Limit fuzz values per parameter to prevent explosion
fuzzed_set = generator.apply_fuzzing(
    scenario_set,
    max_fuzz_per_param=3  # Max 3 fuzz values per parameter per strategy
)
```

## Fuzz Ground Truth

Each fuzz scenario includes a corresponding ground truth that expects:

1. **Graceful error response**: JSON-RPC error with proper format
2. **Appropriate error code**: Typically -32602 (Invalid params)
3. **No crashes or stack traces**: Server should handle gracefully

Example fuzz ground truth:

```python
GroundTruthSpec(
    id="gt_tool_auth_login_fuzz_1",
    expected_behavior="Server should gracefully handle invalid input: "
                      "Type mismatch: string instead of integer. "
                      "Expected to return JSON-RPC error code -32602...",
    expected_output_schema={
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "integer"},
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
            }
        },
    },
    semantic_reference="Graceful error handling for invalid_type input",
)
```

## Generated Gherkin

Fuzz scenarios generate Gherkin like:

```gherkin
Scenario: test_tool fuzz - Type mismatch: string instead of integer
  # Fuzz Category: invalid_type
  # Ground Truth ID: gt_tool_test_tool_fuzz_1
  Given the MCP server is running
  When I call tool "test_tool" with fuzz arguments {"count": "not_a_number"}
  Then the server should return a graceful error
  And the error code should be -32602
  And the response should match fuzz ground truth "gt_tool_test_tool_fuzz_1"
```

## Expected Outcomes

| Server Behavior | Classification |
|-----------------|----------------|
| Returns JSON-RPC error with proper code | **Graceful Failure** (PASS) |
| Returns JSON-RPC error without code | **Schema Violation** |
| Crashes or times out | **Critical Failure** |
| Returns stack trace | **Critical Failure** |
| Hangs indefinitely | **Critical Failure** |

## Module Structure

```
fuzzing/
├── __init__.py          # Package exports
├── strategies.py        # Fuzzing strategy classes
├── generators.py        # FuzzScenarioGenerator
└── README.md           # This file
```

## Testing

Run the fuzzing module tests:

```bash
cd mcp-probe-pilot
uv run python -m pytest tests/test_fuzzing.py -v
```

## Future Extensions (Not in MVP)

- **MalformedJsonStrategy**: Invalid JSON syntax fuzzing
- **OverflowStrategy**: Size limit testing (10MB strings, huge arrays)
- **SqlInjectionStrategy**: SQL injection pattern testing
- **PathTraversalStrategy**: Directory traversal patterns
