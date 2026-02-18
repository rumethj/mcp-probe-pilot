"""Abstract base class for Gherkin test generators.

This module provides the BaseTestGenerator ABC that defines the common
interface and shared functionality for unit and integration test generators.
"""

import logging
import re
from abc import ABC, abstractmethod
from string import Template
from typing import Any, Optional

from ..discovery.models import CodeEntity, DiscoveryResult
from ..service_client import MCPProbeServiceClient
from .llm_client import BaseLLMClient, LLMClientError
from .models import GeneratedFeatureFile, GenerationResult
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeneratorError(Exception):
    """Exception raised when test generation fails."""

    pass


class BaseTestGenerator(ABC):
    """Abstract base class for Gherkin test generators.

    Provides shared functionality for querying codebase context via ChromaDB,
    generating Gherkin content via LLM, and building prompts from templates.

    Args:
        llm_client: LLM client for generating test content.
        service_client: Optional service client for querying ChromaDB.
        project_code: Project code for ChromaDB queries.
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        service_client: Optional[MCPProbeServiceClient] = None,
        project_code: Optional[str] = None,
    ):
        """Initialize the base test generator.

        Args:
            llm_client: LLM client for text generation.
            service_client: Optional service client for ChromaDB queries.
            project_code: Project code for ChromaDB queries.
        """
        self.llm_client = llm_client
        self.service_client = service_client
        self.project_code = project_code

    async def _query_codebase(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Query ChromaDB for relevant code context via the service client.

        Args:
            query: Semantic search query string.
            n_results: Maximum number of results to return.

        Returns:
            List of code entity dictionaries from ChromaDB. Returns an empty
            list if no service client is configured.
        """
        if not self.service_client or not self.project_code:
            logger.debug("No service client or project code configured, skipping codebase query")
            return []

        try:
            results = await self.service_client.query_codebase(
                project_code=self.project_code,
                query=query,
                n_results=n_results,
            )
            logger.debug(f"ChromaDB query '{query}' returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Failed to query codebase: {e}")
            return []

    async def _generate_gherkin(self, prompt: str) -> str:
        """Generate Gherkin feature file content via the LLM.

        Sends the prompt to the LLM with the test generation system prompt
        and extracts clean Gherkin content from the response.

        Args:
            prompt: The fully assembled prompt for Gherkin generation.

        Returns:
            The generated Gherkin feature file content.

        Raises:
            GeneratorError: If the LLM fails to generate valid content.
        """
        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
            )
            content = response.content.strip()
            content = self._clean_gherkin_output(content)

            if not content:
                raise GeneratorError("LLM returned empty content")

            return content

        except LLMClientError as e:
            raise GeneratorError(f"LLM generation failed: {e}") from e

    def _build_prompt(self, template: str, context: dict[str, Any]) -> str:
        """Build a prompt string from a template and context variables.

        Uses Python's string Template for safe substitution, allowing
        template variables like ${tool_name} to be replaced with values.

        Args:
            template: The prompt template string with ${variable} placeholders.
            context: Dictionary of variable names to values.

        Returns:
            The assembled prompt string with all variables substituted.
        """
        tmpl = Template(template)
        return tmpl.safe_substitute(context)

    def _format_code_context(self, entities: list[dict[str, Any]]) -> str:
        """Format code entity results into a readable context string.

        Args:
            entities: List of code entity dictionaries from ChromaDB.

        Returns:
            Formatted string containing code context for prompt inclusion.
        """
        if not entities:
            return "No source code context available."

        parts = []
        for entity in entities:
            name = entity.get("name", "unknown")
            entity_type = entity.get("entity_type", "unknown")
            code = entity.get("code", "")
            docstring = entity.get("docstring", "")
            file_path = entity.get("file_path", "")

            header = f"### {entity_type}: {name}"
            if file_path:
                header += f" ({file_path})"

            part = [header]
            if docstring:
                part.append(f"Docstring: {docstring}")
            if code:
                part.append(f"```python\n{code}\n```")
            parts.append("\n".join(part))

        return "\n\n".join(parts)

    @staticmethod
    def _clean_gherkin_output(content: str) -> str:
        """Clean LLM output to extract pure Gherkin content.

        Removes markdown code fences and any preamble/postamble text
        that the LLM may have added around the Gherkin content.

        Args:
            content: Raw LLM output text.

        Returns:
            Cleaned Gherkin content.
        """
        # Remove markdown code fences
        if content.startswith("```gherkin"):
            content = content[len("```gherkin"):]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # If "Feature:" appears but not at the start, extract from Feature: onward
        if not content.startswith("Feature:"):
            match = re.search(r"^Feature:", content, re.MULTILINE)
            if match:
                content = content[match.start():]

        return content

    @staticmethod
    def _count_scenarios(gherkin_content: str) -> int:
        """Count the number of scenarios in a Gherkin feature file.

        Args:
            gherkin_content: The Gherkin feature file content.

        Returns:
            The number of Scenario/Scenario Outline occurrences.
        """
        return len(re.findall(r"^\s*Scenario(?:\s+Outline)?:", gherkin_content, re.MULTILINE))

    @abstractmethod
    async def generate_all(
        self,
        discovery_result: DiscoveryResult,
    ) -> GenerationResult:
        """Generate all test feature files for the discovered MCP server.

        Args:
            discovery_result: The MCP server discovery result.

        Returns:
            GenerationResult containing all generated feature files.
        """
        pass
