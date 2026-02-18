"""Unit test Gherkin generator for individual MCP capabilities.

This module generates one .feature file per tool, resource, and prompt
discovered on an MCP server, combining MCP discovery schemas with
AST-indexed codebase context from ChromaDB.
"""

import json
import logging
import re
from typing import Optional

from ..discovery.models import (
    DiscoveryResult,
    PromptInfo,
    ResourceInfo,
    ToolInfo,
)
from ..service_client import MCPProbeServiceClient
from .base_generator import BaseTestGenerator, GeneratorError
from .llm_client import BaseLLMClient
from .models import GeneratedFeatureFile, GenerationResult
from .prompts import (
    UNIT_TEST_PROMPT_PROMPT,
    UNIT_TEST_RESOURCE_PROMPT,
    UNIT_TEST_TOOL_PROMPT,
)

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Sanitize a name for use as a filename.

    Args:
        name: The raw name string.

    Returns:
        A filesystem-safe filename component.
    """
    return re.sub(r"[^\w\-]", "_", name).lower()


class UnitTestGenerator(BaseTestGenerator):
    """Generator for unit test Gherkin feature files.

    Produces one .feature file per tool, resource, and prompt, each containing
    happy-path, error-case, and edge-case scenarios.

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
        """Initialize the unit test generator.

        Args:
            llm_client: LLM client for text generation.
            service_client: Optional service client for ChromaDB queries.
            project_code: Project code for ChromaDB queries.
        """
        super().__init__(llm_client, service_client, project_code)

    async def generate_tool_tests(self, tool: ToolInfo) -> GeneratedFeatureFile:
        """Generate a Gherkin feature file for a single MCP tool.

        Queries ChromaDB for relevant source code context, builds a prompt
        combining the tool schema with code context, and generates a feature
        file with happy-path, error, and edge-case scenarios.

        Args:
            tool: The tool information from MCP discovery.

        Returns:
            A GeneratedFeatureFile for the tool.

        Raises:
            GeneratorError: If generation fails.
        """
        logger.info(f"Generating unit tests for tool: {tool.name}")

        code_entities = await self._query_codebase(
            f"tool {tool.name} {tool.description or ''}",
        )
        code_context = self._format_code_context(code_entities)

        prompt = self._build_prompt(
            UNIT_TEST_TOOL_PROMPT,
            {
                "tool_name": tool.name,
                "tool_description": tool.description or "No description provided",
                "input_schema": json.dumps(tool.input_schema, indent=2),
                "code_context": code_context,
            },
        )

        gherkin_content = await self._generate_gherkin(prompt)
        scenario_count = self._count_scenarios(gherkin_content)

        filename = f"tool_{_sanitize_filename(tool.name)}.feature"

        logger.info(
            f"Generated {scenario_count} scenarios for tool '{tool.name}'"
        )

        return GeneratedFeatureFile(
            filename=filename,
            content=gherkin_content,
            target_name=tool.name,
            target_type="tool",
            scenario_count=scenario_count,
        )

    async def generate_resource_tests(self, resource: ResourceInfo) -> GeneratedFeatureFile:
        """Generate a Gherkin feature file for a single MCP resource.

        Queries ChromaDB for relevant source code context, builds a prompt
        combining the resource schema with code context, and generates a feature
        file with access validation, URI format, and content type scenarios.

        Args:
            resource: The resource information from MCP discovery.

        Returns:
            A GeneratedFeatureFile for the resource.

        Raises:
            GeneratorError: If generation fails.
        """
        resource_name = resource.name or resource.uri
        logger.info(f"Generating unit tests for resource: {resource_name}")

        code_entities = await self._query_codebase(
            f"resource {resource_name} {resource.description or ''}",
        )
        code_context = self._format_code_context(code_entities)

        prompt = self._build_prompt(
            UNIT_TEST_RESOURCE_PROMPT,
            {
                "resource_name": resource_name,
                "resource_uri": resource.uri,
                "resource_description": resource.description or "No description provided",
                "mime_type": resource.mime_type or "application/json",
                "is_template": str(resource.is_template),
                "code_context": code_context,
            },
        )

        gherkin_content = await self._generate_gherkin(prompt)
        scenario_count = self._count_scenarios(gherkin_content)

        safe_name = _sanitize_filename(resource_name)
        filename = f"resource_{safe_name}.feature"

        logger.info(
            f"Generated {scenario_count} scenarios for resource '{resource_name}'"
        )

        return GeneratedFeatureFile(
            filename=filename,
            content=gherkin_content,
            target_name=resource_name,
            target_type="resource",
            scenario_count=scenario_count,
        )

    async def generate_prompt_tests(self, prompt_info: PromptInfo) -> GeneratedFeatureFile:
        """Generate a Gherkin feature file for a single MCP prompt.

        Queries ChromaDB for relevant source code context, builds a prompt
        combining the prompt schema with code context, and generates a feature
        file with template validation and argument handling scenarios.

        Args:
            prompt_info: The prompt information from MCP discovery.

        Returns:
            A GeneratedFeatureFile for the prompt.

        Raises:
            GeneratorError: If generation fails.
        """
        logger.info(f"Generating unit tests for prompt: {prompt_info.name}")

        code_entities = await self._query_codebase(
            f"prompt {prompt_info.name} {prompt_info.description or ''}",
        )
        code_context = self._format_code_context(code_entities)

        arguments_desc = []
        for arg in prompt_info.arguments:
            arg_str = f"  - {arg.name}"
            if arg.description:
                arg_str += f": {arg.description}"
            arg_str += f" (required: {arg.required})"
            arguments_desc.append(arg_str)

        prompt = self._build_prompt(
            UNIT_TEST_PROMPT_PROMPT,
            {
                "prompt_name": prompt_info.name,
                "prompt_description": prompt_info.description or "No description provided",
                "arguments": "\n".join(arguments_desc) if arguments_desc else "No arguments",
                "code_context": code_context,
            },
        )

        gherkin_content = await self._generate_gherkin(prompt)
        scenario_count = self._count_scenarios(gherkin_content)

        filename = f"prompt_{_sanitize_filename(prompt_info.name)}.feature"

        logger.info(
            f"Generated {scenario_count} scenarios for prompt '{prompt_info.name}'"
        )

        return GeneratedFeatureFile(
            filename=filename,
            content=gherkin_content,
            target_name=prompt_info.name,
            target_type="prompt",
            scenario_count=scenario_count,
        )

    async def generate_all(
        self,
        discovery_result: DiscoveryResult,
    ) -> GenerationResult:
        """Generate unit test feature files for all discovered MCP capabilities.

        Produces one .feature file per tool, resource, and prompt found in the
        discovery result. Generation errors for individual capabilities are
        collected rather than halting the entire process.

        Args:
            discovery_result: The MCP server discovery result containing tools,
                resources, and prompts.

        Returns:
            GenerationResult with all generated feature files and metadata.
        """
        result = GenerationResult()
        feature_files: list[GeneratedFeatureFile] = []

        # Generate tool tests
        for tool in discovery_result.tools:
            try:
                feature = await self.generate_tool_tests(tool)
                feature_files.append(feature)
                result.tools_covered += 1
            except GeneratorError as e:
                error_msg = f"Failed to generate tests for tool '{tool.name}': {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Generate resource tests
        for resource in discovery_result.resources:
            try:
                feature = await self.generate_resource_tests(resource)
                feature_files.append(feature)
                result.resources_covered += 1
            except GeneratorError as e:
                resource_name = resource.name or resource.uri
                error_msg = f"Failed to generate tests for resource '{resource_name}': {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Generate prompt tests
        for prompt_info in discovery_result.prompts:
            try:
                feature = await self.generate_prompt_tests(prompt_info)
                feature_files.append(feature)
                result.prompts_covered += 1
            except GeneratorError as e:
                error_msg = f"Failed to generate tests for prompt '{prompt_info.name}': {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        result.feature_files = feature_files
        result.total_scenarios = sum(f.scenario_count for f in feature_files)

        logger.info(
            f"Unit test generation complete: {len(feature_files)} feature files, "
            f"{result.total_scenarios} scenarios "
            f"({result.tools_covered} tools, {result.resources_covered} resources, "
            f"{result.prompts_covered} prompts)"
        )

        return result
