# ------------------------------------------------------------
# Prompt Templates for Gherkin Feature File Generation
# ------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert BDD test engineer specializing in MCP (Model Context Protocol) \
server testing. You generate Gherkin feature files that validate MCP server correctness and functional behavior.

Rules:
- Output ONLY valid Gherkin syntax (Feature, Scenario, Given/When/Then/And).
- Every Scenario must contain at least one When, and one Then step.
- Do NOT include any markdown formatting, code fences, or explanations.
- CRITICAL: Only use test data values (usernames, user IDs, enum values, etc.) that appear in the provided source code context or tool descriptions. Do NOT invent usernames, user IDs, or other domain-specific identifiers. If the tool description mentions pre-seeded users like 'admin' and 'developer', use those exact values — never invent names like 'testuser' or 'user1'.
- Each scenario should test ONE specific behavior.
- Do not leave any Scenario incomplete. If you are running out of space, complete the current scenario and stop.
- Include tags (@happy-path, @error-case, @edge-case) on each scenario.
- For error cases, test with missing, invalid, and boundary values.
- The feature should have this for the Background: Given the MCP Client is initialized and connected to the MCP Server: "${server_command}"
- CRITICAL: Re-use the EXACT same step wording across all scenarios. Use steps from the Canonical Step Library.
- CRITICAL: Only use deterministic assertion steps. Do NOT use LLM-based or semantic assertions.
- IMPORTANT: All data tables must have consistent column counts. Every row in a table must have the same number of cells. And the table row should end with a "|" character.
- IMPORTANT: Only use tool names, resource URIs, and prompt names that are explicitly listed in the provided schemas. Do NOT invent tools or primitives.
- NEVER use {variable_name} as a literal value in "with parameters" tables. To pass a previously saved variable, use the "with saved parameters" step with | parameter | saved_variable | format instead.
- Always quote boolean values in assertions: use 'with value "True"' not 'with value True'.
- For error cases where required parameters are missing, MCP servers using Pydantic validation return errors containing "Field required". For type errors (e.g., null where string expected), expect "Input should be a valid string". Use these exact substrings in your error message assertions rather than inventing error messages.
- When asserting error messages, prefer broad substrings (e.g., "Field required") over specific full messages.

When you have completely finished writing the entire feature file, you MUST output the exact string [END_OF_FEATURE] on a new line outside the code block.
"""

# ------------------------------------------------------------
# Canonical Step Library for Step Reuse
# (single source of truth lives in core.canonical_steps)
# ------------------------------------------------------------

from mcp_probe_pilot.core.canonical_steps import render_step_library_prompt

CANONICAL_STEP_LIBRARY = render_step_library_prompt()

TOOL_UNIT_HUMAN = """\
Generate a Gherkin feature file for testing the MCP tool "${tool_name}". The scenarios should be based on the following scenarios:


## Scenarios
${scenarios}

## Tool Schema
- Name: ${tool_name}
- Description: ${tool_description}
- Input Schema: ${input_schema}

${schema_hints}

## Relevant Source Code Context
${code_context}

## Additional rules
- The "When" statement should use the MCP Client. Example:

For tools that have parameters, use the following format:
  When the MCP Client calls the tool "{tool_name}" with parameters
      | parameter    | value             |
      | param_1      | value_1           |

For tools that do not have parameters, use the following format:
  When the MCP Client calls the tool "{tool_name}"
  Then the response should be successful
"""

RESOURCE_UNIT_HUMAN = """\
Generate a Gherkin feature file for testing the MCP resource "${resource_name}". The scenarios should be based on the following scenarios:

## Scenarios
${scenarios}

## Resource Schema
- URI: ${resource_uri}
- Name: ${resource_name}
- Description: ${resource_description}
- MIME Type: ${mime_type}
- Is Template: ${is_template}

## Relevant Source Code Context
${code_context}

## Additional rules
- The "When" statement should use the MCP Client. Example:

Use this format for resource access:
  When the MCP Client reads the resource "${resource_uri}"
  Then the response should be successful
  And the response content type should be "${mime_type}"

For template resources, construct the URI from saved variables:
  And I construct the value "<uri_template_with_{placeholders}>" and save as "dynamic_uri"
  When the MCP Client reads the resource with URI from saved "dynamic_uri"
  Then the response should be successful
"""

PROMPT_UNIT_HUMAN = """\
Generate a Gherkin feature file for testing the MCP prompt "${prompt_name}". The scenarios should be based on the following scenarios:

## Scenarios
${scenarios}

## Prompt Schema
- Name: ${prompt_name}
- Description: ${prompt_description}
- Arguments: ${arguments}

## Relevant Source Code Context
${code_context}

## Additional rules
- The "When" statement should use the MCP Client. Example:

Use this format for prompt retrieval:
  When the MCP Client gets the prompt "${prompt_name}" with arguments
    | argument    | value             |
    | arg_1       | value_1           |
  Then the response should be successful
  And the response should contain prompt messages

For prompts that do not have arguments, use the following format:
  When the MCP Client gets the prompt "${prompt_name}"
  Then the response should be successful
  And the response should contain prompt messages

For error cases:
  When the MCP Client gets the prompt "${prompt_name}" with arguments
    | argument    | value             |
    | arg_1       | value_1           |
  Then the response should contain an error
"""

INTEGRATION_HUMAN = """\
Generate a single Gherkin feature file containing integration test scenarios as follows:

## Scenarios
${scenarios}

## MCP Server Capabilities

### Summary of the MCP server's primitives used
${primitives_summary}

## Source Code Context
${code_context}

## Requirements
- Tag each scenario with its workflow type (@chain-of-calls, @resource-augmented, @prompt-driven)
- Each scenario should exercise a multi-step workflow that chains MCP primitives
- Use explicit, deterministic MCP calls — do NOT use agentic/LLM queries
- Multiple When/Then blocks are allowed to chain calls sequentially
- Use "I save the response field" to pass data between chained calls
- Use "with saved parameters" to feed saved data into subsequent calls
- Use ONLY steps from the Canonical Step Library

### Gherkin Patterns

For Chain-of-Calls scenarios (Tool A output feeds Tool B):
  @chain-of-calls
  Scenario: <workflow_name>
    When the MCP Client calls the tool "<tool_A>" with parameters
      | parameter | value     |
      | ...       | ...       |
    Then the response should be successful
    And I save the response field "<output_field>" as "<variable>"
    When the MCP Client calls the tool "<tool_B>" with saved parameters
      | parameter      | saved_variable |
      | <input_param>  | <variable>     |
    Then the response should be successful

  NOTE: The "with saved parameters" table can mix saved variables and literal
  values in the saved_variable column.  If a value matches a saved variable name
  it is resolved; otherwise it is treated as a literal:
    When the MCP Client calls the tool "<tool_B>" with saved parameters
      | parameter  | saved_variable  |
      | token      | auth_token      |
      | name       | MyProject       |

For Resource-Augmented scenarios (Tool creates, then read the resource):
  @resource-augmented
  Scenario: <workflow_name>
    When the MCP Client calls the tool "<tool_name>" with parameters
      | parameter | value |
      | ...       | ...   |
    Then the response should be successful
    And I save the response field "<id_field>" as "<id_variable>"
    And I construct the value "<uri_template>" and save as "resource_uri"
    When the MCP Client reads the resource with URI from saved "resource_uri"
    Then the response should be successful
    And the response content type should be "<mime_type>"

  Example — constructing a template URI from a saved ID:
    And I save the response field "project_id" as "pid"
    And I construct the value "project://{pid}/tasks" and save as "tasks_uri"
    When the MCP Client reads the resource with URI from saved "tasks_uri"

For Prompt-Driven scenarios (Get prompt, then call tool):
  @prompt-driven
  Scenario: <workflow_name>
    When the MCP Client gets the prompt "<prompt_name>" with arguments
      | argument | value |
      | ...      | ...   |
    Then the response should be successful
    And the response should contain prompt messages
    When the MCP Client calls the tool "<tool_name>" with parameters
      | parameter | value |
      | ...       | ...   |
    Then the response should be successful
"""


# ------------------------------------------------------------
# Prompt Templates for Step Implementation Generation
# ------------------------------------------------------------

STEP_IMPL_SYSTEM_TEMPLATE = """\
You are an Expert Python SDET and AI Test Automation Architect.
Your task is to generate Python step definition code for the `behave` BDD framework based on the provided Gherkin scenario.

ARCHITECTURAL RULES & CONSTRAINTS:
1. Framework: Use standard `behave` step decorators (`@given`, `@when`, `@then`).
2. Execution via MCP: The test framework uses an async MCP client. Use one of these patterns:
   - For direct tool calls: `context.response = context.loop.run_until_complete(context.mcp_client.call_tool(tool_name, params))`
   - For prompt retrieval: `context.response = context.loop.run_until_complete(context.mcp_client.get_prompt(prompt_name, args))`
   - For resource reads: `context.response = context.loop.run_until_complete(context.mcp_client.read_resource(resource_uri))`
3. Context Management: Assume `context.mcp_client` and `context.loop` are already instantiated. Do not instantiate or close them.
4. Error Capture: Every When step must wrap the MCP call in try/except, always setting:
   - `context.response` (string, even on exception)
   - `context.error` (Exception or None)
   - `context.is_error` (bool, from `context.mcp_client.last_is_error` or exception)
5. Saved Variables: For chaining steps, use `context.saved` (a dict) to pass data between calls.
6. Assertions: Parse `context.response` (a string) to perform standard Python `assert` statements.
7. Strict Output Format: 
   - Output ONLY valid Python code enclosed in a ```python ... ``` markdown block.
   - No conversational text before or after the code block.
   - The final line of the code MUST be an `# EOF` comment.
8. Deduplication: Do NOT generate python functions for steps that are ALREADY IMPLEMENTED. Only generate code for steps that are missing.
9. Parameter Naming: Use consistent parameter names for step patterns to enable pattern matching:
   - Use `{tool_name}` for tool names
   - Use `{resource_uri}` for resource URIs
   - Use `{prompt_name}` for prompt names
   - Use `{key}` or `{field}` for field/key names
   - Use `{value}` or `{expected_value}` for expected values
   - Use `{variable}` for saved variable names

ALREADY IMPLEMENTED STEPS (DO NOT GENERATE THESE):
${existing_steps_list}

EXAMPLE - Step with data table and error capture:
```python
import json
from behave import when

@when('the MCP Client calls the tool "{tool_name}" with parameters')
def step_when_call_tool_with_params(context, tool_name):
    context.error = None
    context.is_error = False
    try:
        params = {}
        for row in context.table:
            value = row["value"]
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
            params[row["parameter"]] = value
        context.response = context.loop.run_until_complete(
            context.mcp_client.call_tool(tool_name, params)
        )
        context.is_error = context.mcp_client.last_is_error
    except Exception as exc:
        context.response = str(exc)
        context.error = exc
        context.is_error = True
# EOF
```\
"""

STEP_IMPL_HUMAN_TEMPLATE = """\
Generate Python step implementations for the following Gherkin scenario.

## Feature: ${feature_name}
## Scenario: ${scenario_name}

### Full Scenario Context:
```gherkin
${scenario_text}
```

### Instructions:
1. Generate step implementations ONLY for steps that are NOT in the "ALREADY IMPLEMENTED" list.
2. Use parameterized step patterns where values are quoted (e.g., `@when('the MCP Client calls the tool "{tool_name}"')`).
3. For steps with data tables (rows starting with |), access them via `context.table`. Iterate with `for row in context.table`.
4. Ensure each function has a unique, descriptive name prefixed with `step_`.
5. Store results in `context.response` so subsequent steps can access them.
6. For assertions, parse `context.response` (which is a string) appropriately - use `json.loads()` if JSON is expected.
7. End with `# EOF` on the last line.
8. If all steps are already implemented, output an empty code block with just `# EOF`.
"""
