"""Integration test Gherkin generator for multi-step MCP workflows.

This module generates a single .feature file containing integration test
scenarios that validate multi-step workflows combining tools, resources,
and prompts on an MCP server.
"""

import json
import logging
from typing import Any, Optional

from ..discovery.models import DiscoveryResult
from ..service_client import MCPProbeServiceClient
from .base_generator import BaseTestGenerator, GeneratorError
from .llm_client import BaseLLMClient, LLMClientError
from .models import GeneratedFeatureFile, GenerationResult, WorkflowType
from .prompts import (
    INTEGRATION_TEST_PROMPT,
    SYSTEM_PROMPT,
    WORKFLOW_IDENTIFICATION_PROMPT,
)

logger = logging.getLogger(__name__)


class IntegrationTestGenerator(BaseTestGenerator):
    """Generator for integration test Gherkin feature files.

    Identifies workflow patterns across MCP capabilities and generates a
    single .feature file with multi-step integration scenarios covering
    prompt-driven, resource-augmented, and chain-of-thought workflows.

    Args:
        llm_client: LLM client for generating test content.
        service_client: Optional service client for ChromaDB queries.
        project_code: Project code for ChromaDB queries.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        service_client: Optional[MCPProbeServiceClient] = None,
        project_code: Optional[str] = None,
    ):
        """Initialize the integration test generator.

        Args:
            llm_client: LLM client for text generation.
            service_client: Optional service client for ChromaDB queries.
            project_code: Project code for ChromaDB queries.
        """
        super().__init__(llm_client, service_client, project_code)

    async def _identify_workflows(
        self,
        discovery_result: DiscoveryResult,
        code_context: str,
    ) -> list[dict[str, Any]]:
        """Identify integration workflow patterns from discovery results.

        Uses the LLM to analyze MCP capabilities and source code context
        to identify prompt-driven, resource-augmented, and chain-of-thought
        workflow patterns.

        Args:
            discovery_result: The MCP server discovery result.
            code_context: Formatted source code context string.

        Returns:
            List of workflow dictionaries with type, name, steps, etc.

        Raises:
            GeneratorError: If workflow identification fails.
        """
        tools_summary = self._format_tools_summary(discovery_result)
        resources_summary = self._format_resources_summary(discovery_result)
        prompts_summary = self._format_prompts_summary(discovery_result)

        prompt = self._build_prompt(
            WORKFLOW_IDENTIFICATION_PROMPT,
            {
                "tools_summary": tools_summary,
                "resources_summary": resources_summary,
                "prompts_summary": prompts_summary,
                "code_context": code_context,
            },
        )

        try:
            response = await self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=(
                    "You are an expert at analyzing MCP server capabilities and "
                    "identifying integration workflow patterns. Return ONLY valid JSON."
                ),
            )

            if isinstance(response, list):
                workflows = response
            elif isinstance(response, dict) and "workflows" in response:
                workflows = response["workflows"]
            else:
                workflows = [response] if isinstance(response, dict) else []

            logger.info(f"Identified {len(workflows)} workflow patterns")
            return workflows

        except LLMClientError as e:
            raise GeneratorError(f"Workflow identification failed: {e}") from e

    def _generate_prompt_driven_scenarios(
        self,
        discovery_result: DiscoveryResult,
    ) -> list[dict[str, Any]]:
        """Generate prompt-driven workflow candidates from discovery result.

        Identifies workflows where a prompt references tools or has arguments
        that match tool input parameters.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            List of workflow dictionaries for prompt-driven patterns.
        """
        workflows = []
        tool_names = {t.name for t in discovery_result.tools}

        for prompt_info in discovery_result.prompts:
            related_tools = []
            prompt_text = (prompt_info.description or "").lower()
            prompt_arg_names = {a.name.lower() for a in prompt_info.arguments}

            for tool in discovery_result.tools:
                tool_lower = tool.name.lower()
                tool_desc = (tool.description or "").lower()

                # Check if tool is referenced in prompt description
                if tool_lower in prompt_text or tool.name in prompt_text:
                    related_tools.append(tool.name)
                    continue

                # Check if prompt arguments overlap with tool input
                tool_params = set()
                if "properties" in tool.input_schema:
                    tool_params = {
                        p.lower() for p in tool.input_schema["properties"]
                    }
                if prompt_arg_names & tool_params:
                    related_tools.append(tool.name)

            if related_tools:
                workflows.append({
                    "type": WorkflowType.PROMPT_DRIVEN.value,
                    "name": f"Prompt-driven workflow: {prompt_info.name}",
                    "description": (
                        f"Retrieve prompt '{prompt_info.name}', fill arguments, "
                        f"then invoke tool(s): {', '.join(related_tools)}"
                    ),
                    "steps": [
                        f"Get prompt '{prompt_info.name}'",
                        "Fill prompt arguments",
                        f"Use prompt to call tool '{related_tools[0]}'",
                    ],
                    "tools": related_tools,
                    "resources": [],
                    "prompts": [prompt_info.name],
                })

        return workflows

    def _generate_resource_augmented_scenarios(
        self,
        discovery_result: DiscoveryResult,
    ) -> list[dict[str, Any]]:
        """Generate resource-augmented workflow candidates from discovery result.

        Identifies workflows where a tool output may contain resource URIs
        that can be subsequently read.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            List of workflow dictionaries for resource-augmented patterns.
        """
        workflows = []

        if not discovery_result.resources:
            return workflows

        resource_uris = [r.uri for r in discovery_result.resources]

        for tool in discovery_result.tools:
            tool_desc = (tool.description or "").lower()

            # Check if tool description mentions resources, URIs, or files
            resource_keywords = ["resource", "uri", "url", "file", "document", "path"]
            if any(kw in tool_desc for kw in resource_keywords):
                matching_resources = []
                tool_name_parts = set(tool.name.lower().replace("_", " ").split())

                for resource in discovery_result.resources:
                    resource_name = (resource.name or resource.uri).lower()
                    resource_desc = (resource.description or "").lower()
                    # Check for keyword overlap
                    if tool_name_parts & set(resource_name.replace("_", " ").split()):
                        matching_resources.append(resource.uri)
                    elif any(part in resource_desc for part in tool_name_parts if len(part) > 2):
                        matching_resources.append(resource.uri)

                if not matching_resources:
                    matching_resources = [resource_uris[0]]

                workflows.append({
                    "type": WorkflowType.RESOURCE_AUGMENTED.value,
                    "name": f"Resource-augmented workflow: {tool.name}",
                    "description": (
                        f"Call tool '{tool.name}', extract resource URI from result, "
                        f"then read the resource"
                    ),
                    "steps": [
                        f"Call tool '{tool.name}'",
                        "Extract resource URI from result",
                        f"Read resource '{matching_resources[0]}'",
                    ],
                    "tools": [tool.name],
                    "resources": matching_resources[:1],
                    "prompts": [],
                })

        return workflows

    def _generate_chain_of_thought_scenarios(
        self,
        discovery_result: DiscoveryResult,
    ) -> list[dict[str, Any]]:
        """Generate chain-of-thought workflow candidates from discovery result.

        Identifies workflows where Tool A's output fields could serve as
        input to Tool B.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            List of workflow dictionaries for chain-of-thought patterns.
        """
        workflows = []
        tools = discovery_result.tools

        if len(tools) < 2:
            return workflows

        for i, tool_a in enumerate(tools):
            for tool_b in tools[i + 1:]:
                # Check for input/output compatibility by analyzing descriptions
                desc_a = (tool_a.description or "").lower()
                desc_b = (tool_b.description or "").lower()

                # Output keywords from tool A that match input context of tool B
                a_output_words = set(desc_a.split()) - {
                    "the", "a", "an", "is", "of", "to", "and", "in", "for",
                    "with", "on", "this", "that", "it",
                }
                b_input_words = set(desc_b.split()) - {
                    "the", "a", "an", "is", "of", "to", "and", "in", "for",
                    "with", "on", "this", "that", "it",
                }

                # Check for parameter name overlap
                a_params = set()
                if "properties" in tool_a.input_schema:
                    a_params = set(tool_a.input_schema["properties"].keys())

                b_params = set()
                if "properties" in tool_b.input_schema:
                    b_params = set(tool_b.input_schema["properties"].keys())

                # Significant word overlap or parameter name overlap
                common_words = a_output_words & b_input_words
                meaningful_overlap = {w for w in common_words if len(w) > 3}
                param_overlap = a_params & b_params

                if len(meaningful_overlap) >= 2 or param_overlap:
                    workflows.append({
                        "type": WorkflowType.CHAIN_OF_THOUGHT.value,
                        "name": (
                            f"Chain-of-thought: {tool_a.name} -> {tool_b.name}"
                        ),
                        "description": (
                            f"Call tool '{tool_a.name}', pass output to "
                            f"tool '{tool_b.name}'"
                        ),
                        "steps": [
                            f"Call tool '{tool_a.name}'",
                            f"Extract relevant output",
                            f"Pass result to tool '{tool_b.name}'",
                        ],
                        "tools": [tool_a.name, tool_b.name],
                        "resources": [],
                        "prompts": [],
                    })

        return workflows

    async def generate_all(
        self,
        discovery_result: DiscoveryResult,
    ) -> GenerationResult:
        """Generate integration test feature file for discovered MCP workflows.

        Identifies workflow patterns and generates a single .feature file
        with integration scenarios for all discovered patterns.

        Args:
            discovery_result: The MCP server discovery result containing tools,
                resources, and prompts.

        Returns:
            GenerationResult with the integration feature file.
        """
        result = GenerationResult()

        # Collect code context for workflow analysis
        code_entities = await self._query_codebase(
            "integration workflow tool resource prompt interaction",
        )
        code_context = self._format_code_context(code_entities)

        # Try LLM-based workflow identification first
        workflows: list[dict[str, Any]] = []
        try:
            workflows = await self._identify_workflows(
                discovery_result, code_context
            )
        except GeneratorError as e:
            logger.warning(
                f"LLM workflow identification failed, falling back to "
                f"heuristic analysis: {e}"
            )

        # Supplement with heuristic-based workflow identification
        heuristic_workflows = []
        heuristic_workflows.extend(
            self._generate_prompt_driven_scenarios(discovery_result)
        )
        heuristic_workflows.extend(
            self._generate_resource_augmented_scenarios(discovery_result)
        )
        heuristic_workflows.extend(
            self._generate_chain_of_thought_scenarios(discovery_result)
        )

        # Merge: add heuristic workflows if LLM didn't produce similar ones
        existing_names = {w.get("name", "").lower() for w in workflows}
        for hw in heuristic_workflows:
            if hw["name"].lower() not in existing_names:
                workflows.append(hw)

        if not workflows:
            logger.info(
                "No integration workflow patterns identified. "
                "Skipping integration test generation."
            )
            return result

        result.workflows_identified = len(workflows)

        # Generate the integration feature file
        try:
            feature = await self._generate_integration_feature(
                workflows, discovery_result, code_context
            )
            result.feature_files = [feature]
            result.total_scenarios = feature.scenario_count
        except GeneratorError as e:
            error_msg = f"Failed to generate integration tests: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        logger.info(
            f"Integration test generation complete: "
            f"{result.workflows_identified} workflows identified, "
            f"{result.total_scenarios} scenarios generated"
        )

        return result

    async def _generate_integration_feature(
        self,
        workflows: list[dict[str, Any]],
        discovery_result: DiscoveryResult,
        code_context: str,
    ) -> GeneratedFeatureFile:
        """Generate the integration feature file from identified workflows.

        Args:
            workflows: List of identified workflow patterns.
            discovery_result: The MCP server discovery result.
            code_context: Formatted source code context string.

        Returns:
            A GeneratedFeatureFile for integration tests.

        Raises:
            GeneratorError: If generation fails.
        """
        tools_summary = self._format_tools_summary(discovery_result)
        resources_summary = self._format_resources_summary(discovery_result)
        prompts_summary = self._format_prompts_summary(discovery_result)

        prompt = self._build_prompt(
            INTEGRATION_TEST_PROMPT,
            {
                "workflows_json": json.dumps(workflows, indent=2),
                "tools_summary": tools_summary,
                "resources_summary": resources_summary,
                "prompts_summary": prompts_summary,
                "code_context": code_context,
            },
        )

        gherkin_content = await self._generate_gherkin(prompt)
        scenario_count = self._count_scenarios(gherkin_content)

        return GeneratedFeatureFile(
            filename="integration_workflows.feature",
            content=gherkin_content,
            target_name="integration_workflows",
            target_type="integration",
            scenario_count=scenario_count,
        )

    @staticmethod
    def _format_tools_summary(discovery_result: DiscoveryResult) -> str:
        """Format tools into a summary string for prompts.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            Formatted string summarizing all tools.
        """
        if not discovery_result.tools:
            return "No tools available."

        parts = []
        for tool in discovery_result.tools:
            desc = tool.description or "No description"
            params = list(tool.input_schema.get("properties", {}).keys())
            param_str = ", ".join(params) if params else "none"
            parts.append(f"- **{tool.name}**: {desc} (params: {param_str})")
        return "\n".join(parts)

    @staticmethod
    def _format_resources_summary(discovery_result: DiscoveryResult) -> str:
        """Format resources into a summary string for prompts.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            Formatted string summarizing all resources.
        """
        if not discovery_result.resources:
            return "No resources available."

        parts = []
        for resource in discovery_result.resources:
            name = resource.name or resource.uri
            desc = resource.description or "No description"
            template_str = " (template)" if resource.is_template else ""
            parts.append(f"- **{name}** ({resource.uri}){template_str}: {desc}")
        return "\n".join(parts)

    @staticmethod
    def _format_prompts_summary(discovery_result: DiscoveryResult) -> str:
        """Format prompts into a summary string for prompts.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            Formatted string summarizing all prompts.
        """
        if not discovery_result.prompts:
            return "No prompts available."

        parts = []
        for prompt_info in discovery_result.prompts:
            desc = prompt_info.description or "No description"
            args = [a.name for a in prompt_info.arguments]
            args_str = ", ".join(args) if args else "none"
            parts.append(
                f"- **{prompt_info.name}**: {desc} (args: {args_str})"
            )
        return "\n".join(parts)
