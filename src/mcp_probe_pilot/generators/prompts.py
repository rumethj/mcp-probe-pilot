"""LLM prompt templates for test generation.

This module provides separate prompt templates for:
1. Ground truth generation (isolated context - no scenario information)
2. Scenario generation (references ground truth by ID only)
3. Workflow analysis and generation (multi-step chained scenarios)

The separation prevents ground truth poisoning by ensuring ground truth
is derived purely from capability definitions.
"""

import json
from typing import Any

from ..discovery.models import DiscoveryResult, PromptInfo, ResourceInfo, ToolInfo
from .models import TargetType

# =============================================================================
# GROUND TRUTH GENERATION PROMPTS (Phase 1 - Isolated Context)
# =============================================================================

GROUND_TRUTH_SYSTEM_PROMPT = """You are an expert MCP (Model Context Protocol) test engineer.
Your task is to analyze MCP capability definitions and generate ground truth specifications
that describe the EXPECTED behavior of the capability.

IMPORTANT:
- Base your analysis ONLY on the capability definition (name, description, schema)
- Do NOT generate test scenarios - only describe what the capability SHOULD do
- Be precise and comprehensive about expected behavior
- Include both success and error conditions

Output must be valid JSON matching the specified schema."""


def build_tool_ground_truth_prompt(tool: ToolInfo) -> str:
    """Build a prompt for generating tool ground truth.

    Args:
        tool: The tool information from discovery.

    Returns:
        Prompt string for ground truth generation.
    """
    schema_str = json.dumps(tool.input_schema, indent=2) if tool.input_schema else "{}"

    return f'''Analyze this MCP tool definition and generate ground truth specification.

TOOL DEFINITION:
- Name: {tool.name}
- Description: {tool.description or "No description provided"}
- Input Schema:
```json
{schema_str}
```

Generate a JSON object with the following structure:
{{
    "expected_behavior": "<detailed description of what this tool should do when called correctly>",
    "expected_output_schema": {{
        "type": "object",
        "properties": {{
            // Expected response fields based on the tool's purpose
        }}
    }},
    "valid_input_examples": [
        {{
            "input": {{}},  // Valid input arguments
            "expected_outcome": "<what should happen>"
        }}
    ],
    "invalid_input_examples": [
        {{
            "input": {{}},  // Invalid input arguments
            "expected_error": "<expected error behavior>"
        }}
    ],
    "semantic_reference": "<concise description for semantic validation>"
}}

Analyze the tool carefully and provide comprehensive ground truth.'''


def build_resource_ground_truth_prompt(resource: ResourceInfo) -> str:
    """Build a prompt for generating resource ground truth.

    Args:
        resource: The resource information from discovery.

    Returns:
        Prompt string for ground truth generation.
    """
    template_info = " (URI Template - contains placeholders)" if resource.is_template else ""

    return f'''Analyze this MCP resource definition and generate ground truth specification.

RESOURCE DEFINITION:
- URI: {resource.uri}{template_info}
- Name: {resource.name or "No name provided"}
- Description: {resource.description or "No description provided"}
- MIME Type: {resource.mime_type or "Not specified"}

Generate a JSON object with the following structure:
{{
    "expected_behavior": "<detailed description of what this resource should return>",
    "expected_output_schema": {{
        "type": "object",
        "properties": {{
            // Expected content structure based on MIME type and description
        }}
    }},
    "valid_input_examples": [
        {{
            "uri": "<valid URI or URI with valid placeholders filled>",
            "expected_outcome": "<what content should be returned>"
        }}
    ],
    "invalid_input_examples": [
        {{
            "uri": "<invalid URI or URI with invalid placeholders>",
            "expected_error": "<expected error behavior>"
        }}
    ],
    "semantic_reference": "<concise description for semantic validation>"
}}

Analyze the resource carefully and provide comprehensive ground truth.'''


def build_prompt_ground_truth_prompt(prompt: PromptInfo) -> str:
    """Build a prompt for generating prompt ground truth.

    Args:
        prompt: The prompt information from discovery.

    Returns:
        Prompt string for ground truth generation.
    """
    args_str = ""
    if prompt.arguments:
        args_list = []
        for arg in prompt.arguments:
            required = "required" if arg.required else "optional"
            args_list.append(f"  - {arg.name} ({required}): {arg.description or 'No description'}")
        args_str = "\n".join(args_list)
    else:
        args_str = "  No arguments"

    return f'''Analyze this MCP prompt definition and generate ground truth specification.

PROMPT DEFINITION:
- Name: {prompt.name}
- Description: {prompt.description or "No description provided"}
- Arguments:
{args_str}

Generate a JSON object with the following structure:
{{
    "expected_behavior": "<detailed description of what this prompt should return>",
    "expected_output_schema": {{
        "type": "object",
        "properties": {{
            // Expected prompt message structure
        }}
    }},
    "valid_input_examples": [
        {{
            "arguments": {{}},  // Valid argument values
            "expected_outcome": "<what messages should be returned>"
        }}
    ],
    "invalid_input_examples": [
        {{
            "arguments": {{}},  // Invalid/missing argument values
            "expected_error": "<expected error behavior>"
        }}
    ],
    "semantic_reference": "<concise description for semantic validation>"
}}

Analyze the prompt carefully and provide comprehensive ground truth.'''


# =============================================================================
# SCENARIO GENERATION PROMPTS (Phase 2 - References Ground Truth)
# =============================================================================

SCENARIO_SYSTEM_PROMPT = """You are an expert BDD (Behavior-Driven Development) test engineer.
Your task is to generate Gherkin test scenarios for MCP (Model Context Protocol) capabilities.

IMPORTANT:
- Generate scenarios that reference the provided ground truth ID
- Include happy path, error case, and edge case scenarios
- Use the standard Gherkin format (Given/When/Then)
- Scenarios should be executable and deterministic

Output must be valid JSON matching the specified schema."""


def build_tool_scenario_prompt(
    tool: ToolInfo,
    ground_truth_id: str,
) -> str:
    """Build a prompt for generating tool test scenarios.

    Args:
        tool: The tool information from discovery.
        ground_truth_id: The ID of the pre-generated ground truth.

    Returns:
        Prompt string for scenario generation.
    """
    schema_str = json.dumps(tool.input_schema, indent=2) if tool.input_schema else "{}"

    return f'''Generate Gherkin BDD test scenarios for this MCP tool.

TOOL DEFINITION:
- Name: {tool.name}
- Description: {tool.description or "No description provided"}
- Input Schema:
```json
{schema_str}
```

GROUND TRUTH REFERENCE: {ground_truth_id}

Generate a JSON object with test scenarios:
{{
    "scenarios": [
        {{
            "name": "<descriptive scenario name>",
            "category": "happy_path|error_case|edge_case",
            "description": "<what this scenario tests>",
            "gherkin": "<complete Gherkin scenario text>"
        }}
    ]
}}

GHERKIN FORMAT:
- Use: Given the MCP server is running
- Use: When I call tool "{tool.name}" with arguments {{...}}
- Use: Then the response should be successful / indicate failure
- Use: And the response should match ground truth "{ground_truth_id}"

Generate at least:
- 1-2 happy path scenarios (valid inputs)
- 2-3 error case scenarios (invalid inputs, missing required fields)
- 1-2 edge case scenarios (boundary values, optional parameters)'''


def build_resource_scenario_prompt(
    resource: ResourceInfo,
    ground_truth_id: str,
) -> str:
    """Build a prompt for generating resource test scenarios.

    Args:
        resource: The resource information from discovery.
        ground_truth_id: The ID of the pre-generated ground truth.

    Returns:
        Prompt string for scenario generation.
    """
    template_note = ""
    if resource.is_template:
        template_note = "\nNote: This is a URI template. Generate scenarios with various placeholder values."

    return f'''Generate Gherkin BDD test scenarios for this MCP resource.

RESOURCE DEFINITION:
- URI: {resource.uri}
- Name: {resource.name or "No name provided"}
- Description: {resource.description or "No description provided"}
- MIME Type: {resource.mime_type or "Not specified"}{template_note}

GROUND TRUTH REFERENCE: {ground_truth_id}

Generate a JSON object with test scenarios:
{{
    "scenarios": [
        {{
            "name": "<descriptive scenario name>",
            "category": "happy_path|error_case|edge_case",
            "description": "<what this scenario tests>",
            "gherkin": "<complete Gherkin scenario text>"
        }}
    ]
}}

GHERKIN FORMAT:
- Use: Given the MCP server is running
- Use: When I read resource "{resource.uri}"
- Use: Then the response should contain valid content
- Use: And the response should match ground truth "{ground_truth_id}"

Generate at least:
- 1 happy path scenario (valid resource access)
- 1-2 error case scenarios (invalid URI, missing resource)
- 1 edge case scenario (if applicable for templates)'''


def build_prompt_scenario_prompt(
    prompt: PromptInfo,
    ground_truth_id: str,
) -> str:
    """Build a prompt for generating prompt test scenarios.

    Args:
        prompt: The prompt information from discovery.
        ground_truth_id: The ID of the pre-generated ground truth.

    Returns:
        Prompt string for scenario generation.
    """
    args_str = ""
    if prompt.arguments:
        args_list = []
        for arg in prompt.arguments:
            required = "required" if arg.required else "optional"
            args_list.append(f"  - {arg.name} ({required}): {arg.description or 'No description'}")
        args_str = "\n".join(args_list)
    else:
        args_str = "  No arguments"

    return f'''Generate Gherkin BDD test scenarios for this MCP prompt.

PROMPT DEFINITION:
- Name: {prompt.name}
- Description: {prompt.description or "No description provided"}
- Arguments:
{args_str}

GROUND TRUTH REFERENCE: {ground_truth_id}

Generate a JSON object with test scenarios:
{{
    "scenarios": [
        {{
            "name": "<descriptive scenario name>",
            "category": "happy_path|error_case|edge_case",
            "description": "<what this scenario tests>",
            "gherkin": "<complete Gherkin scenario text>"
        }}
    ]
}}

GHERKIN FORMAT:
- Use: Given the MCP server is running
- Use: When I get prompt "{prompt.name}" with arguments {{...}}
- Use: Then the response should contain prompt messages
- Use: And the response should match ground truth "{ground_truth_id}"

Generate at least:
- 1-2 happy path scenarios (valid arguments)
- 1-2 error case scenarios (missing required arguments, invalid values)
- 1 edge case scenario (optional arguments, boundary values)'''


# =============================================================================
# PROMPT BUILDERS - Unified interface
# =============================================================================


def build_ground_truth_prompt(
    target_type: TargetType,
    target: ToolInfo | ResourceInfo | PromptInfo,
) -> str:
    """Build a ground truth generation prompt for any target type.

    Args:
        target_type: The type of capability.
        target: The capability information from discovery.

    Returns:
        Prompt string for ground truth generation.

    Raises:
        ValueError: If target type doesn't match target object.
    """
    if target_type == TargetType.TOOL:
        if not isinstance(target, ToolInfo):
            raise ValueError("Target must be ToolInfo for TOOL type")
        return build_tool_ground_truth_prompt(target)
    elif target_type == TargetType.RESOURCE:
        if not isinstance(target, ResourceInfo):
            raise ValueError("Target must be ResourceInfo for RESOURCE type")
        return build_resource_ground_truth_prompt(target)
    elif target_type == TargetType.PROMPT:
        if not isinstance(target, PromptInfo):
            raise ValueError("Target must be PromptInfo for PROMPT type")
        return build_prompt_ground_truth_prompt(target)
    else:
        raise ValueError(f"Unknown target type: {target_type}")


def build_scenario_prompt(
    target_type: TargetType,
    target: ToolInfo | ResourceInfo | PromptInfo,
    ground_truth_id: str,
) -> str:
    """Build a scenario generation prompt for any target type.

    Args:
        target_type: The type of capability.
        target: The capability information from discovery.
        ground_truth_id: The ID of the pre-generated ground truth.

    Returns:
        Prompt string for scenario generation.

    Raises:
        ValueError: If target type doesn't match target object.
    """
    if target_type == TargetType.TOOL:
        if not isinstance(target, ToolInfo):
            raise ValueError("Target must be ToolInfo for TOOL type")
        return build_tool_scenario_prompt(target, ground_truth_id)
    elif target_type == TargetType.RESOURCE:
        if not isinstance(target, ResourceInfo):
            raise ValueError("Target must be ResourceInfo for RESOURCE type")
        return build_resource_scenario_prompt(target, ground_truth_id)
    elif target_type == TargetType.PROMPT:
        if not isinstance(target, PromptInfo):
            raise ValueError("Target must be PromptInfo for PROMPT type")
        return build_prompt_scenario_prompt(target, ground_truth_id)
    else:
        raise ValueError(f"Unknown target type: {target_type}")


# =============================================================================
# WORKFLOW PROMPTS - Multi-step chained scenarios
# =============================================================================

WORKFLOW_ANALYSIS_SYSTEM_PROMPT = """You are an expert MCP (Model Context Protocol) test engineer.
Your task is to analyze MCP server capabilities and identify meaningful workflows
where multiple features must be chained together to achieve a goal.

Look for patterns such as:
- Authentication followed by authenticated operations
- Creating entities then performing operations on them
- Reading resources to get IDs for tool calls
- Operations that trigger sampling or elicitation
- Data dependencies between tools

Output must be valid JSON matching the specified schema."""


WORKFLOW_GROUND_TRUTH_SYSTEM_PROMPT = """You are an expert MCP (Model Context Protocol) test engineer.
Your task is to generate ground truth specifications for workflow scenarios.

IMPORTANT:
- Base your analysis ONLY on the workflow definition and involved capabilities
- Describe the expected behavior at each step and the final outcome
- Include expected error handling when intermediate steps fail
- Do NOT generate test scenarios - only describe what SHOULD happen

Output must be valid JSON matching the specified schema."""


WORKFLOW_SCENARIO_SYSTEM_PROMPT = """You are an expert BDD (Behavior-Driven Development) test engineer.
Your task is to generate Gherkin test scenarios for MCP workflow tests that chain
multiple features (tools, resources, prompts, sampling, elicitation).

IMPORTANT:
- Generate multi-step scenarios that test the complete workflow
- Include data passing between steps using variables
- Reference the provided ground truth ID
- Include both successful flow and error handling scenarios

Output must be valid JSON matching the specified schema."""


def build_workflow_analysis_prompt(discovery: DiscoveryResult) -> str:
    """Build a prompt for analyzing capabilities to identify workflows.

    Args:
        discovery: The complete discovery result from the server.

    Returns:
        Prompt string for workflow analysis.
    """
    # Summarize tools
    tools_summary = []
    for tool in discovery.tools:
        params = []
        if tool.input_schema and "properties" in tool.input_schema:
            for param, schema in tool.input_schema["properties"].items():
                params.append(f"{param}: {schema.get('type', 'any')}")
        params_str = ", ".join(params) if params else "none"
        tools_summary.append(
            f"  - {tool.name}({params_str}): {tool.description or 'No description'}"
        )
    tools_str = "\n".join(tools_summary) if tools_summary else "  No tools"

    # Summarize resources
    resources_summary = []
    for resource in discovery.resources:
        template_marker = " [TEMPLATE]" if resource.is_template else ""
        resources_summary.append(
            f"  - {resource.uri}{template_marker}: {resource.description or 'No description'}"
        )
    resources_str = "\n".join(resources_summary) if resources_summary else "  No resources"

    # Summarize prompts
    prompts_summary = []
    for prompt in discovery.prompts:
        args = [a.name for a in prompt.arguments] if prompt.arguments else []
        args_str = f"({', '.join(args)})" if args else "()"
        prompts_summary.append(
            f"  - {prompt.name}{args_str}: {prompt.description or 'No description'}"
        )
    prompts_str = "\n".join(prompts_summary) if prompts_summary else "  No prompts"

    # Check for sampling/elicitation support
    caps = discovery.server_info.capabilities
    special_features = []
    if caps.sampling:
        special_features.append("- Server supports SAMPLING (can request LLM completions)")
    if hasattr(caps, "elicitation") and caps.elicitation:
        special_features.append("- Server supports ELICITATION (can request user input)")
    special_str = "\n".join(special_features) if special_features else "- No special features"

    return f'''Analyze these MCP server capabilities and identify meaningful WORKFLOWS
where multiple features must be chained together.

SERVER: {discovery.server_info.name}

TOOLS:
{tools_str}

RESOURCES:
{resources_str}

PROMPTS:
{prompts_str}

SPECIAL CAPABILITIES:
{special_str}

Identify workflows by looking for:
1. Authentication patterns (login -> use token for subsequent calls)
2. Create-then-use patterns (create entity -> perform operations on it)
3. Read-then-act patterns (read resource -> use data in tool call)
4. Multi-step business processes
5. Operations involving sampling or elicitation

Generate a JSON object with identified workflows:
{{
    "workflows": [
        {{
            "name": "<workflow name>",
            "description": "<what this workflow accomplishes>",
            "steps": [
                {{
                    "step_number": 1,
                    "action_type": "tool_call|resource_read|prompt_get|sampling|elicitation",
                    "target_name": "<name of tool/resource/prompt>",
                    "description": "<what this step does>",
                    "input_source": "literal|previous_step|context",
                    "output_variable": "<variable name for result>",
                    "dependencies": []
                }}
            ],
            "involved_features": ["tools", "resources", "prompts", "sampling", "elicitation"]
        }}
    ]
}}

Identify 2-5 meaningful workflows that represent realistic usage patterns.'''


def build_workflow_ground_truth_prompt(
    workflow_name: str,
    workflow_description: str,
    steps: list[dict[str, Any]],
    involved_features: list[str],
) -> str:
    """Build a prompt for generating workflow ground truth.

    Args:
        workflow_name: Name of the workflow.
        workflow_description: Description of what the workflow does.
        steps: List of workflow steps.
        involved_features: List of feature types involved.

    Returns:
        Prompt string for workflow ground truth generation.
    """
    steps_str = json.dumps(steps, indent=2)
    features_str = ", ".join(involved_features)

    return f'''Generate ground truth specification for this MCP workflow.

WORKFLOW: {workflow_name}
DESCRIPTION: {workflow_description}
INVOLVED FEATURES: {features_str}

STEPS:
{steps_str}

Generate a JSON object with ground truth:
{{
    "expected_flow": "<description of expected execution flow>",
    "step_expectations": [
        {{
            "step_number": 1,
            "expected_behavior": "<what should happen>",
            "expected_output": "<expected output structure or value>",
            "success_criteria": "<how to verify success>"
        }}
    ],
    "final_outcome": "<expected final result of complete workflow>",
    "error_scenarios": [
        {{
            "failing_step": 1,
            "error_type": "<type of error>",
            "expected_behavior": "<how workflow should handle this>"
        }}
    ]
}}

Provide comprehensive ground truth for validating this workflow.'''


def build_workflow_scenario_prompt(
    workflow_name: str,
    workflow_description: str,
    steps: list[dict[str, Any]],
    ground_truth_id: str,
    involved_features: list[str],
) -> str:
    """Build a prompt for generating workflow test scenarios.

    Args:
        workflow_name: Name of the workflow.
        workflow_description: Description of what the workflow does.
        steps: List of workflow steps.
        ground_truth_id: ID of the pre-generated workflow ground truth.
        involved_features: List of feature types involved.

    Returns:
        Prompt string for workflow scenario generation.
    """
    steps_str = json.dumps(steps, indent=2)
    features_str = ", ".join(involved_features)

    return f'''Generate Gherkin BDD test scenarios for this MCP workflow.

WORKFLOW: {workflow_name}
DESCRIPTION: {workflow_description}
INVOLVED FEATURES: {features_str}
GROUND TRUTH REFERENCE: {ground_truth_id}

STEPS:
{steps_str}

Generate a JSON object with test scenarios:
{{
    "scenarios": [
        {{
            "name": "<descriptive scenario name>",
            "description": "<what this scenario tests>",
            "gherkin": "<complete Gherkin scenario text>"
        }}
    ]
}}

GHERKIN FORMAT FOR WORKFLOWS:
- Use: Given the MCP server is running
- For tool calls: When I call tool "<name>" with arguments {{...}}
- For resources: When I read resource "<uri>"
- For prompts: When I get prompt "<name>" with arguments {{...}}
- For data passing: And I store the result as "<variable>"
- For using stored data: When I call tool "<name>" with arguments using "<variable>"
- Use: Then the workflow should complete successfully
- Use: And the result should match ground truth "{ground_truth_id}"

Generate at least:
- 1 happy path scenario (complete workflow succeeds)
- 1-2 error scenarios (intermediate step fails, workflow handles gracefully)
- 1 edge case if applicable (optional steps, alternative paths)

Example workflow scenario:
```gherkin
Scenario: Complete authentication and project creation workflow
  Given the MCP server is running
  When I call tool "auth_login" with arguments {{"username": "admin", "password": "secret"}}
  And I store the "token" from the result as "auth_token"
  When I call tool "create_project" with arguments {{"token": "{{auth_token}}", "name": "Test Project"}}
  And I store the "project_id" from the result as "new_project_id"
  When I call tool "add_task" with arguments {{"token": "{{auth_token}}", "project_id": "{{new_project_id}}", "title": "First Task"}}
  Then the workflow should complete successfully
  And all steps should match ground truth "{ground_truth_id}"
```'''
