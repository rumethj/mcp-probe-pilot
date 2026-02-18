"""LLM prompt templates for Gherkin test generation.

This module provides prompt templates used by the unit and integration
test generators to produce BDD Gherkin feature files from MCP discovery
results and codebase context.

All templates use Python string.Template syntax (${variable}) for
substitution to avoid conflicts with JSON braces in examples.
"""

# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPT = """You are an expert BDD test engineer specializing in MCP (Model Context Protocol) \
server testing. You generate Gherkin feature files that validate MCP server correctness, protocol \
compliance, and functional behavior.

Rules:
- Output ONLY valid Gherkin syntax (Feature, Scenario, Given/When/Then/And).
- Do NOT include any markdown formatting, code fences, or explanations.
- Every scenario MUST start with: Given the MCP server is running
- Use realistic but safe test data in examples.
- Each scenario should test ONE specific behavior.
- Include tags (@happy-path, @error-case, @edge-case) on each scenario.
- For semantic assertions, use: Then the response should be semantically relevant to "<description>"
- For error cases, test with missing, invalid, and boundary values.
"""

# =============================================================================
# Unit Test Prompt Templates
# =============================================================================

UNIT_TEST_TOOL_PROMPT = """Generate a Gherkin feature file for testing the MCP tool "${tool_name}".

## Tool Schema
- Name: ${tool_name}
- Description: ${tool_description}
- Input Schema: ${input_schema}

## Relevant Source Code Context
${code_context}

## Requirements
Generate scenarios that cover:
1. **Happy Path** (@happy-path): Valid invocations with correct parameters that should succeed.
2. **Error Cases** (@error-case): Invocations with missing required parameters, invalid types, \
or out-of-range values that should return proper JSON-RPC errors.
3. **Edge Cases** (@edge-case): Boundary values, empty strings, very long inputs, special \
characters, and null values.

Use this format for tool calls:
  When I call tool "${tool_name}" with arguments {<json_arguments>}
  Then the response should be successful
  And the response should contain a "<field>" field

For error cases:
  When I call tool "${tool_name}" with arguments {<invalid_json_arguments>}
  Then the response should contain an error

Generate at least 3 scenarios (1 happy path, 1 error case, 1 edge case).
"""

UNIT_TEST_RESOURCE_PROMPT = """Generate a Gherkin feature file for testing the MCP resource \
"${resource_name}".

## Resource Schema
- URI: ${resource_uri}
- Name: ${resource_name}
- Description: ${resource_description}
- MIME Type: ${mime_type}
- Is Template: ${is_template}

## Relevant Source Code Context
${code_context}

## Requirements
Generate scenarios that cover:
1. **Happy Path** (@happy-path): Successfully reading the resource with valid URI.
2. **Error Cases** (@error-case): Accessing with invalid URI, missing template parameters.
3. **Edge Cases** (@edge-case): Special characters in URI parameters, boundary values for \
template arguments.

Use this format for resource access:
  When I read resource "${resource_uri}"
  Then the response should be successful
  And the response content type should be "${mime_type}"

For template resources, include parameter substitution:
  When I read resource "<uri_with_params>"

Generate at least 3 scenarios (1 happy path, 1 error case, 1 edge case).
"""

UNIT_TEST_PROMPT_PROMPT = """Generate a Gherkin feature file for testing the MCP prompt \
"${prompt_name}".

## Prompt Schema
- Name: ${prompt_name}
- Description: ${prompt_description}
- Arguments: ${arguments}

## Relevant Source Code Context
${code_context}

## Requirements
Generate scenarios that cover:
1. **Happy Path** (@happy-path): Getting the prompt with all required arguments filled correctly.
2. **Error Cases** (@error-case): Missing required arguments, invalid argument values.
3. **Edge Cases** (@edge-case): Optional arguments omitted, empty string arguments, very long \
argument values.

Use this format for prompt retrieval:
  When I get prompt "${prompt_name}" with arguments {<json_arguments>}
  Then the response should be successful
  And the response should contain prompt messages

For error cases:
  When I get prompt "${prompt_name}" with arguments {<invalid_arguments>}
  Then the response should contain an error

Generate at least 3 scenarios (1 happy path, 1 error case, 1 edge case).
"""

# =============================================================================
# Integration Test Prompt Templates
# =============================================================================

WORKFLOW_IDENTIFICATION_PROMPT = """Analyze the following MCP server capabilities and source code \
context to identify integration test workflow patterns.

## Discovered MCP Capabilities

### Tools
${tools_summary}

### Resources
${resources_summary}

### Prompts
${prompts_summary}

## Source Code Context
${code_context}

## Workflow Patterns to Identify

1. **Prompt-Driven** (prompt-driven): A Prompt is retrieved, the user fills arguments, the LLM \
uses the prompt, then the LLM calls a Tool.
   - Look for: prompts that reference tool names, prompts with arguments that match tool inputs.

2. **Resource-Augmented** (resource-augmented): A Tool is called, it returns a Resource URI, \
then the client reads the Resource.
   - Look for: tools whose output includes URIs, tools that create/reference resources.

3. **Chain-of-Thought** (chain-of-thought): Tool A output becomes Tool B input.
   - Look for: tools whose output fields match other tools' input parameters.

## Output Format
Return a JSON array of identified workflows. Each workflow should have:
- "type": one of "prompt-driven", "resource-augmented", "chain-of-thought"
- "name": a descriptive name for the workflow
- "description": brief description of what the workflow tests
- "steps": array of step descriptions
- "tools": array of tool names involved
- "resources": array of resource URIs involved (if any)
- "prompts": array of prompt names involved (if any)

Return ONLY the JSON array, no other text.
"""

INTEGRATION_TEST_PROMPT = """Generate a single Gherkin feature file containing integration test \
scenarios for the following identified workflows.

## Identified Workflows
${workflows_json}

## MCP Server Capabilities

### Tools
${tools_summary}

### Resources
${resources_summary}

### Prompts
${prompts_summary}

## Source Code Context
${code_context}

## Requirements
- Create ONE feature file named "Integration - Workflow Scenarios"
- Each workflow becomes one scenario
- Tag each scenario with its workflow type (@prompt-driven, @resource-augmented, @chain-of-thought)
- Each scenario should exercise a multi-step workflow
- Use semantic assertions for workflow completion checks

### Gherkin Patterns

For Prompt-Driven workflows:
  @prompt-driven
  Scenario: <workflow_name>
    Given the MCP server is running
    When I get prompt "<prompt_name>" with arguments {<args>}
    And the LLM uses the prompt to call tool "<tool_name>"
    Then the workflow should complete successfully

For Resource-Augmented workflows:
  @resource-augmented
  Scenario: <workflow_name>
    Given the MCP server is running
    When I call tool "<tool_name>" with arguments {<args>}
    And I read the resource URI from the result
    Then the resource content should be semantically relevant to "<description>"

For Chain-of-Thought workflows:
  @chain-of-thought
  Scenario: <workflow_name>
    Given the MCP server is running
    When I call tool "<tool_a>" with arguments {<args>}
    And I pass the result to tool "<tool_b>"
    Then the response should be semantically relevant to "<description>"

Generate the complete feature file content.
"""
