# ------------------------------------------------------------
# Prompt Templates for Gherkin Feature File Generation
# ------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert BDD test engineer specializing in MCP (Model Context Protocol) \
server testing. You generate Gherkin feature files that validate MCP server correctness and functional behavior.

Rules:
- Output ONLY valid Gherkin syntax (Feature, Scenario, Given/When/Then/And).
- Every Scenario must contain at least one When, and one Then step.
- Do NOT include any markdown formatting, code fences, or explanations.
- Use realistic but safe test data in examples.
- Each scenario should test ONE specific behavior.
- Do not leave any Scenario incomplete. If you are running out of space, complete the current scenario and stop.
- Include tags (@happy-path, @error-case, @edge-case) on each scenario.
- For semantic assertions, use: Then the response should be semantically relevant to "<description>"
- For error cases, test with missing, invalid, and boundary values.
- The feature should have this for the Background: Given the MCP Client is initialized and connected to the MCP Server: "${server_command}"
- CRITICAL: Re-use the EXACT same step wording across all scenarios. Use steps from the Canonical Step Library.
- IMPORTANT: All data tables must have consistent column counts. Every row in a table must have the same number of cells. And the table row should end with a "|" character.

When you have completely finished writing the entire feature file, you MUST output the exact string [END_OF_FEATURE] on a new line outside the code block.
"""

# ------------------------------------------------------------
# Canonical Step Library for Step Reuse
# ------------------------------------------------------------

CANONICAL_STEP_LIBRARY = """
## Canonical Step Patterns (USE THESE EXACTLY - do not create variations)

### Setup Steps (Given)
- Given the MCP Client is initialized and connected to the MCP Server: "{server_command}"

### Action Steps (When)
- When the MCP Client calls the tool "{tool_name}" with parameters
- When the MCP Client calls the tool "{tool_name}"
- When the MCP Client reads the resource "{resource_uri}"
- When the MCP Client reads the resource "{resource_uri}" with header "{header}"
- When the MCP Client gets the prompt "{prompt_name}" with arguments
- When the MCP Client gets the prompt "{prompt_name}"
- When the MCP Client queries "{query}"

### Response Assertion Steps (Then/And)
- Then the response should be successful
- Then the response should be a failure
- Then the response should contain "{key}"
- Then the response should contain "{key}" with value "{value}"
- Then the response should contain "{key}" with value {value:d}
- Then the response field "{field}" should be "{expected_value}"
- Then the response field "{field}" should be {expected_value:d}
- Then the response field "{field}" should be null
- Then the response field "{field}" should be {json_value}
- Then the response content type should be "{content_type}"
- Then the response should be semantically relevant to "{description}"
- Then the response should contain an error
- Then the error message should indicate "{expected_message}"
- Then the response should contain prompt messages

### Integration Workflow Steps (For multi-step workflows)
- Then the MCP Client calls the tool "{tool_name}" with parameters
- Then the MCP Client gets the prompt "{prompt_name}" with arguments
- And the MCP Client calls the tool "{tool_name}" with the result
- And the MCP Client uses the prompt to call tool "{tool_name}"
- And the workflow should complete successfully
"""

TOOL_UNIT_HUMAN = """\
Generate a Gherkin feature file for testing the MCP tool "${tool_name}". The scenarios should be based on the following scenarios:


## Scenarios
${scenarios}

## Tool Schema
- Name: ${tool_name}
- Description: ${tool_description}
- Input Schema: ${input_schema}

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

For template resources, include parameter substitution:
  When the MCP Client reads the resource "<uri_with_params>"

For specific header and body, use the following format:
  When the MCP Client reads the resource "<uri_with_params>" with header "{<header>}"
  Then the response should be successful
  And the response content type should be "${mime_type}"

  When the MCP Client reads the resource "<uri_with_params>" with body "{<body>}"
  Then the response should be successful
  And the response content type should be "${mime_type}"
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
- Tag each scenario with its workflow type (@prompt-driven, @resource-augmented, @chain-of-thought)
- Each scenario should exercise a multi-step workflow
- If it is more suitable you may use semantic assertions for workflow completion checks
- The "When" statement should use the MCP Client and be based on a MCP Client query. And there should be only a single When statement per scenario(Additional And statements not allowed).
- The "Then" statement should validate that the MCP Client called the required primitive/s and recieved an expected response.

### Gherkin Patterns

For Prompt-Driven scenarios:
  @prompt-driven
  Scenario: <workflow_name>
    When the MCP Client queries "<query>"
    Then the MCP Client gets the prompt "<prompt_name>" with arguments
    And the MCP Client uses the prompt to call tool "<tool_name>"
    And the workflow should complete successfully

For Resource-Augmented scenarios:
  @resource-augmented
  Scenario: <workflow_name>
    When the MCP Client queries "<query>"
    Then the MCP Client reads the resource "<resource_uri>"
    And the response should be semantically relevant to "<description>"

For Chain-of-Thought scenarios:
  @chain-of-thought
  Scenario: <workflow_name>
    When the MCP Client queries "<query>"
    Then the MCP Client calls the tool "<tool_name>" with the result
    And the response should be semantically relevant to "<description>"
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
   - For agentic queries: `context.response = context.loop.run_until_complete(context.mcp_client.process_query(query_string))`
   - For direct tool calls: `context.response = context.loop.run_until_complete(context.mcp_client.call_tool(tool_name, params))`
   - For prompt retrieval: `context.response = context.loop.run_until_complete(context.mcp_client.get_prompt(prompt_name, args))`
   - For resource reads: `context.response = context.loop.run_until_complete(context.mcp_client.read_resource(resource_uri))`
3. Context Management: Assume `context.mcp_client` and `context.loop` are already instantiated. Do not instantiate or close them.
4. Assertions: Parse `context.response` to perform standard Python `assert` statements.
5. Strict Output Format: 
   - Output ONLY valid Python code enclosed in a ```python ... ``` markdown block.
   - No conversational text before or after the code block.
   - The final line of the code MUST be an `# EOF` comment.
6. Deduplication: Do NOT generate python functions for steps that are ALREADY IMPLEMENTED. Only generate code for steps that are missing.

ALREADY IMPLEMENTED STEPS (DO NOT GENERATE THESE):
${existing_steps_list}

EXAMPLE:
```python
from behave import given, when, then

@when('the user queries "{query}"')
def step_when_user_queries(context, query):
    context.response = context.loop.run_until_complete(
        context.mcp_client.process_query(query)
    )

@then('the response should contain "{expected}"')
def step_then_response_contains(context, expected):
    assert expected in str(context.response), f"Expected '{expected}' in response: {context.response}"
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
3. For steps with data tables, access them via `context.table`.
4. Ensure each function has a unique, descriptive name.
5. Store results in `context.response` so subsequent steps can access them.
6. End with `# EOF` on the last line.
"""
