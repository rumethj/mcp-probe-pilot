"""Prompt templates for unit and integration test planning.

All templates use {placeholder} syntax compatible with
langchain_core.prompts.ChatPromptTemplate.
"""

# ===================================================================
# Unit Test — Tool
# ===================================================================

TOOL_UNIT_SYSTEM = """\
You are a QA Lead creating a Test Plan for an Model Context Protocol (MCP) Server Tool.

Review the Tool Name, Description, and Input Schema.
Generate a list of unique BDD Scenario Titles that cover:
1. Happy Paths (Normal usage).
2. Edge Cases (Boundaries defined in schema).
3. Error States (Invalid types, missing required fields).

Output ONLY the titles (e.g., "Scenario: User provides valid email").
Do not write the steps yet."""

TOOL_UNIT_HUMAN = """\
## Tool Schema
- Name: {tool_name}
- Description: {tool_description}
- Input Schema: {input_schema}"""

# ===================================================================
# Unit Test — Resource
# ===================================================================

RESOURCE_UNIT_SYSTEM = """\
You are a QA Lead creating a Test Plan for an Model Context Protocol (MCP) Server Resource.

Review the Resource URI, Name, Description, MIME Type, and whether it is \
a URI template.
Generate a list of unique BDD Scenario Titles that cover:
1. Happy Paths (Successful resource reads).
2. Edge Cases (Boundary values in URI parameters, empty content).
3. Error States (Invalid URIs, missing template parameters, wrong MIME type).

Output ONLY the titles (e.g., "Scenario: Client reads resource with valid URI").
Do not write the steps yet."""

RESOURCE_UNIT_HUMAN = """\
## Resource Schema
- URI: {resource_uri}
- Name: {resource_name}
- Description: {resource_description}
- MIME Type: {mime_type}
- Is Template: {is_template}"""

# ===================================================================
# Unit Test — Prompt
# ===================================================================

PROMPT_UNIT_SYSTEM = """\
You are a QA Lead creating a Test Plan for an Model Context Protocol (MCP) Server Prompt.

Review the Prompt Name, Description, and Arguments.
Generate a list of unique BDD Scenario Titles that cover:
1. Happy Paths (All required arguments supplied correctly).
2. Edge Cases (Optional arguments omitted, boundary values).
3. Error States (Missing required arguments, invalid argument types).

Output ONLY the titles (e.g., "Scenario: User retrieves prompt with all required arguments").
Do not write the steps yet."""

PROMPT_UNIT_HUMAN = """\
## Prompt Schema
- Name: {prompt_name}
- Description: {prompt_description}
- Arguments: {arguments}"""

# ===================================================================
# Integration Test
# ===================================================================

INTEGRATION_SYSTEM = """\
You are a QA Lead identifying integration test workflow scenarios for \
an Model Context Protocol (MCP) server.

Analyze the discovered MCP capabilities and identify cross-primitive \
workflow patterns. For each workflow you identify, produce a BDD Scenario \
Title, the workflow pattern type, and the list of MCP primitives involved.

Do not write the Gherkin steps yet — only titles and metadata."""

INTEGRATION_HUMAN = """\
Analyze the following MCP server capabilities to identify integration \
test workflow patterns.

## Discovered MCP Capabilities

### Tools
{tools_summary}

### Resources
{resources_summary}

### Prompts
{prompts_summary}

## Workflow Patterns to Identify

1. **Prompt-Driven** (prompt-driven): A Prompt is retrieved, the user fills \
arguments, the LLM uses the prompt, then the LLM calls a Tool.
   - Look for: prompts that reference tool names, prompts with arguments \
that match tool inputs.

2. **Resource-Augmented** (resource-augmented): A Tool is called, it returns \
a Resource URI, then the client reads the Resource.
   - Look for: tools whose output includes URIs, tools that create/reference \
resources.

3. **Chain-of-Thought** (chain-of-thought): Tool A output becomes Tool B input.
   - Look for: tools whose output fields match other tools' input parameters."""
