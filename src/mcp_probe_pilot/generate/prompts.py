# ------------------------------------------------------------
# Prompt Templates for Gherkin Feature File Generation
# ------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert BDD test engineer specializing in MCP (Model Context Protocol) \
server testing. You generate Gherkin feature files that validate MCP server correctness and functional behavior.

Rules:
- Output ONLY valid Gherkin syntax (Feature, Scenario, Given/When/Then/And).
- Every Scenario must contain at least one Given, one When, and one Then step.
- Do NOT include any markdown formatting, code fences, or explanations.
- Use realistic but safe test data in examples.
- Each scenario should test ONE specific behavior.
- Do not leave any Scenario incomplete. If you are running out of space, complete the current scenario and stop.
- Include tags (@happy-path, @error-case, @edge-case) on each scenario.
- For semantic assertions, use: Then the response should be semantically relevant to "<description>"
- For error cases, test with missing, invalid, and boundary values.
- The feature should have this for the Background: Given the MCP Client is running
- Re-use as much of the same steps in different scenarios as possible.

You must write the Gherkin feature file inside a single markdown code block (gherkin ...). When you have completely finished writing the entire feature file, you MUST output the exact string [END_OF_FEATURE] on a new line outside the code block.
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

Use this format for resource access:
  When I read resource "${resource_uri}"
  Then the response should be successful
  And the response content type should be "${mime_type}"

For template resources, include parameter substitution:
  When I read resource "<uri_with_params>"
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

Use this format for prompt retrieval:
  When I get prompt "${prompt_name}" with arguments {<json_arguments>}
  Then the response should be successful
  And the response should contain prompt messages

For error cases:
  When I get prompt "${prompt_name}" with arguments {<invalid_arguments>}
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

### Gherkin Patterns

For Prompt-Driven scenarios:
  @prompt-driven
  Scenario: <workflow_name>
    Given the MCP server is running
    When I get prompt "<prompt_name>" with arguments {<args>}
    And the LLM uses the prompt to call tool "<tool_name>"
    Then the workflow should complete successfully

For Resource-Augmented scenarios:
  @resource-augmented
  Scenario: <workflow_name>
    Given the MCP server is running
    When I call tool "<tool_name>" with arguments {<args>}
    And I read the resource URI from the result
    Then the resource content should be semantically relevant to "<description>"

For Chain-of-Thought scenarios:
  @chain-of-thought
  Scenario: <workflow_name>
    Given the MCP server is running
    When I call tool "<tool_a>" with arguments {<args>}
    And I pass the result to tool "<tool_b>"
    Then the response should be semantically relevant to "<description>"
"""


# ------------------------------------------------------------
# Prompt Templates for Step Implementation Generation
# ------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are an Expert Python SDET and AI Test Automation Architect.
Your task is to generate Python step definition code for the `behave` BDD framework based on the provided Gherkin `.feature` file.

ARCHITECTURAL RULES & CONSTRAINTS:
1. Framework: Use standard `behave` step decorators (`@given`, `@when`, `@then`).
2. Execution via MCP: Do NOT write traditional UI/API automation code. You MUST delegate all test actions to our MCP client by calling: `response = context.mcp_client.query(prompt_string)`
3. Context Management: Assume `context.mcp_client` is already instantiated. Do not instantiate or close it.
4. Assertions: Parse the `response` string returned by the MCP client to perform standard Python `assert` statements.
5. Strict Output Format: 
   - Output ONLY valid Python code enclosed in a ```python ... ``` markdown block.
   - No conversational text.
   - The final line of the code MUST be an `# EOF` comment.
6. Deduplication: Do NOT generate python functions for the following steps, as they are ALREADY IMPLEMENTED in the project. Only generate code for steps that are missing.

ALREADY IMPLEMENTED STEPS (DO NOT GENERATE THESE):
{existing_steps_list}

EXAMPLE:
```python
from behave import given, when, then

@when('the user logs in')
def step_impl(context):
    response = context.mcp_client.query("Log in. Return 'SUCCESS' if it worked.")
    assert "SUCCESS" in response.upper(), f"Login failed: {{response}}"
# EOF
```\
"""
