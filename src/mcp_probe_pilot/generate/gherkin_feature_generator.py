"""Gherkin feature file generator with async LLM generation and validation.

Produces validated .feature files from test plans by:
1. Rendering prompt templates with primitive metadata and code context
2. Calling the LLM asynchronously (bounded by a semaphore)
3. Extracting Gherkin from the markdown response
4. Validating via [END_OF_FEATURE] marker and gherkin-official parser
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any

from gherkin.parser import Parser as GherkinParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from mcp_probe_pilot.generate.prompts import (
    INTEGRATION_HUMAN,
    PROMPT_UNIT_HUMAN,
    RESOURCE_UNIT_HUMAN,
    SYSTEM_PROMPT,
    TOOL_UNIT_HUMAN,
)

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from mcp_probe_pilot.core.models.discovery import (
        DiscoveryResult,
        ResourceInfo,
    )
    from mcp_probe_pilot.core.models.plan import (
        IntegrationTestPlanResult,
        ScenarioPlan,
        UnitTestPlanResult,
    )
    from mcp_probe_pilot.core.service_client import MCPProbeServiceClient

logger = logging.getLogger(__name__)

CONCURRENCY_LIMIT = 3


class GenerationResult(BaseModel):
    """Summary of a feature-file generation run."""

    files_generated: int = 0
    files_failed: int = 0
    validation_warnings: list[str] = Field(default_factory=list)


class GherkinFeatureGenerator:
    """Generates validated Gherkin .feature files from test plans via LLM."""

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        service_client: MCPProbeServiceClient,
        output_dir: Path,
        discovery_result: DiscoveryResult,
    ) -> None:
        self._llm = llm
        self._service_client = service_client
        self._output_dir = output_dir
        self._discovery = discovery_result
        self._semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_all(
        self,
        unit_plan: UnitTestPlanResult,
        integration_plan: IntegrationTestPlanResult,
    ) -> GenerationResult:
        """Generate all feature files concurrently (semaphore-bounded)."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        tasks: list[asyncio.Task] = []

        for tool in self._discovery.tools:
            scenarios = unit_plan.get_scenario_plans("tool", tool.name)
            if scenarios:
                tasks.append(
                    asyncio.create_task(
                        self._generate_unit_feature("tool", tool.name, scenarios)
                    )
                )

        for resource in self._discovery.resources:
            identifier = resource.name or resource.uri
            scenarios = unit_plan.get_scenario_plans("resource", identifier)
            if scenarios:
                tasks.append(
                    asyncio.create_task(
                        self._generate_unit_feature(
                            "resource", identifier, scenarios
                        )
                    )
                )

        for prompt in self._discovery.prompts:
            scenarios = unit_plan.get_scenario_plans("prompt", prompt.name)
            if scenarios:
                tasks.append(
                    asyncio.create_task(
                        self._generate_unit_feature(
                            "prompt", prompt.name, scenarios
                        )
                    )
                )

        if integration_plan.integration_scenarios:
            tasks.append(
                asyncio.create_task(
                    self._generate_integration_feature(integration_plan)
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        summary = GenerationResult()
        for result in results:
            if isinstance(result, Exception):
                summary.files_failed += 1
                summary.validation_warnings.append(str(result))
                logger.error("Feature generation task failed: %s", result)
            elif isinstance(result, dict):
                summary.files_generated += 1
                if result.get("warning"):
                    summary.validation_warnings.append(result["warning"])

        return summary

    # ------------------------------------------------------------------
    # Unit feature generation
    # ------------------------------------------------------------------

    async def _generate_unit_feature(
        self,
        prim_type: str,
        prim_name: str,
        scenarios: list[ScenarioPlan],
    ) -> dict[str, Any]:
        """Generate a single .feature file for one MCP primitive."""
        async with self._semaphore:
            logger.info("Generating %s unit feature: %s", prim_type, prim_name)

            code_context = await self._query_code_context(prim_name)
            human_content = self._render_unit_prompt(
                prim_type, prim_name, scenarios, code_context
            )

            raw_response = await self._call_llm(human_content)
            gherkin_content, warning = self._process_llm_output(
                raw_response, f"{prim_type}/{prim_name}"
            )

            safe_name = re.sub(r"[^\w]", "_", prim_name).lower()
            filename = f"{prim_type}_{safe_name}.feature"
            filepath = self._output_dir / filename
            filepath.write_text(gherkin_content, encoding="utf-8")
            logger.info("Wrote feature file: %s", filepath)

            return {"file": str(filepath), "warning": warning}

    # ------------------------------------------------------------------
    # Integration feature generation
    # ------------------------------------------------------------------

    async def _generate_integration_feature(
        self,
        integration_plan: IntegrationTestPlanResult,
    ) -> dict[str, Any]:
        """Generate the single integration .feature file."""
        async with self._semaphore:
            logger.info("Generating integration feature file")

            all_primitives: set[str] = set()
            for scenario in integration_plan.integration_scenarios:
                all_primitives.update(scenario.primitives)

            query = ", ".join(sorted(all_primitives))
            code_context = await self._query_code_context(query)
            primitives_summary = self._build_primitives_summary(all_primitives)

            scenarios_text = "\n".join(
                f"- [{s.pattern or 'general'}] {s.scenario} "
                f"(primitives: {', '.join(s.primitives)})"
                for s in integration_plan.integration_scenarios
            )

            human_content = Template(INTEGRATION_HUMAN).safe_substitute(
                scenarios=scenarios_text,
                primitives_summary=primitives_summary,
                code_context=code_context,
            )

            raw_response = await self._call_llm(human_content)
            gherkin_content, warning = self._process_llm_output(
                raw_response, "integration"
            )

            filepath = self._output_dir / "integration_workflows.feature"
            filepath.write_text(gherkin_content, encoding="utf-8")
            logger.info("Wrote feature file: %s", filepath)

            return {"file": str(filepath), "warning": warning}

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------

    def _render_unit_prompt(
        self,
        prim_type: str,
        prim_name: str,
        scenarios: list[ScenarioPlan],
        code_context: str,
    ) -> str:
        """Render the human-message template for a unit-test feature."""
        scenarios_text = "\n".join(f"- {s.scenario}" for s in scenarios)

        if prim_type == "tool":
            tool = self._discovery.get_tool(prim_name)
            if tool is None:
                raise ValueError(f"Tool '{prim_name}' not found in discovery result")
            return Template(TOOL_UNIT_HUMAN).safe_substitute(
                tool_name=tool.name,
                scenarios=scenarios_text,
                tool_description=tool.description or "No description",
                input_schema=json.dumps(tool.input_schema, indent=2),
                code_context=code_context,
            )

        if prim_type == "resource":
            resource = self._find_resource(prim_name)
            if resource is None:
                raise ValueError(
                    f"Resource '{prim_name}' not found in discovery result"
                )
            return Template(RESOURCE_UNIT_HUMAN).safe_substitute(
                resource_name=resource.name or resource.uri,
                scenarios=scenarios_text,
                resource_uri=resource.uri,
                resource_description=resource.description or "No description",
                mime_type=resource.mime_type or "unspecified",
                is_template=str(resource.is_template),
                code_context=code_context,
            )

        if prim_type == "prompt":
            prompt_info = self._discovery.get_prompt(prim_name)
            if prompt_info is None:
                raise ValueError(
                    f"Prompt '{prim_name}' not found in discovery result"
                )
            args_repr = (
                ", ".join(
                    f"{a.name} ({'required' if a.required else 'optional'})"
                    for a in prompt_info.arguments
                )
                or "none"
            )
            return Template(PROMPT_UNIT_HUMAN).safe_substitute(
                prompt_name=prompt_info.name,
                scenarios=scenarios_text,
                prompt_description=prompt_info.description or "No description",
                arguments=args_repr,
                code_context=code_context,
            )

        raise ValueError(f"Unknown primitive type: {prim_type}")

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(self, human_content: str) -> str:
        """Send system + human messages to the LLM and return the raw text."""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        response = await self._llm.ainvoke(messages)
        return response.content

    # ------------------------------------------------------------------
    # Code-context retrieval
    # ------------------------------------------------------------------

    async def _query_code_context(self, query: str) -> str:
        """Query ChromaDB for relevant source code snippets."""
        try:
            results = await self._service_client.query_codebase(query)
            if not results:
                return "No relevant source code found."

            parts: list[str] = []
            for r in results:
                lines = [
                    f"### {r.get('entity_type', 'code')}: "
                    f"{r.get('name', 'unknown')}"
                ]
                if r.get("file_path"):
                    lines.append(f"File: {r['file_path']}")
                if r.get("code"):
                    lines.append(f"```\n{r['code']}\n```")
                parts.append("\n".join(lines))

            return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("Failed to query code context: %s", exc)
            return "Code context unavailable."

    # ------------------------------------------------------------------
    # Output processing and validation
    # ------------------------------------------------------------------

    def _process_llm_output(
        self, raw_response: str, label: str
    ) -> tuple[str, str | None]:
        """Extract gherkin, validate, and return (content, optional_warning)."""
        gherkin_content, has_end_marker = self._extract_gherkin(raw_response)
        warning: str | None = None

        if not has_end_marker:
            logger.warning(
                "[%s] Missing [END_OF_FEATURE], trimming last scenario", label
            )
            gherkin_content = self._remove_last_scenario(gherkin_content)
            warning = f"{label}: [END_OF_FEATURE] missing — last scenario trimmed"

        is_valid = self._validate_gherkin(gherkin_content)
        if not is_valid:
            msg = f"{label}: Gherkin syntax validation failed"
            logger.warning(msg)
            warning = msg

        if not gherkin_content.endswith("\n"):
            gherkin_content += "\n"

        return gherkin_content, warning

    @staticmethod
    def _extract_gherkin(llm_response: str) -> tuple[str, bool]:
        """Pull the Gherkin text out of the LLM's markdown response.

        Returns (gherkin_text, end_of_feature_found).
        """
        has_end_marker = "[END_OF_FEATURE]" in llm_response

        match = re.search(r"```gherkin\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip(), has_end_marker

        match = re.search(r"```\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip(), has_end_marker

        content = llm_response.replace("[END_OF_FEATURE]", "").strip()
        return content, has_end_marker

    @staticmethod
    def _remove_last_scenario(gherkin_text: str) -> str:
        """Drop the final Scenario block (assumed incomplete)."""
        lines = gherkin_text.split("\n")
        last_scenario_idx: int | None = None

        for i, line in enumerate(lines):
            if re.match(r"\s*(Scenario|Scenario Outline):", line):
                last_scenario_idx = i

        if last_scenario_idx is None:
            return gherkin_text

        cut_idx = last_scenario_idx
        while cut_idx > 0 and re.match(r"\s*@", lines[cut_idx - 1]):
            cut_idx -= 1
        while cut_idx > 0 and lines[cut_idx - 1].strip() == "":
            cut_idx -= 1

        trimmed = "\n".join(lines[:cut_idx])
        return trimmed.rstrip() + "\n" if trimmed.strip() else gherkin_text

    @staticmethod
    def _validate_gherkin(content: str) -> bool:
        """Parse with the official Gherkin parser; return True when valid."""
        try:
            GherkinParser().parse(content)
            return True
        except Exception as exc:
            logger.warning("Gherkin parse error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_resource(self, identifier: str) -> ResourceInfo | None:
        """Look up a resource by URI first, then by name."""
        resource = self._discovery.get_resource(identifier)
        if resource is not None:
            return resource
        for r in self._discovery.resources:
            if r.name == identifier:
                return r
        return None

    def _build_primitives_summary(self, primitive_names: set[str]) -> str:
        """Build a human-readable summary of primitives for integration prompts."""
        parts: list[str] = []
        for name in sorted(primitive_names):
            tool = self._discovery.get_tool(name)
            if tool:
                parts.append(
                    f"- **Tool: {tool.name}**: "
                    f"{tool.description or 'No description'}\n"
                    f"  Input Schema: {json.dumps(tool.input_schema, indent=2)}"
                )
                continue

            resource = self._find_resource(name)
            if resource:
                tag = " (template)" if resource.is_template else ""
                parts.append(
                    f"- **Resource: {resource.name or resource.uri}**{tag}: "
                    f"{resource.description or 'No description'} "
                    f"[{resource.mime_type or 'unspecified'}]"
                )
                continue

            prompt_info = self._discovery.get_prompt(name)
            if prompt_info:
                args = (
                    ", ".join(
                        f"{a.name} ({'required' if a.required else 'optional'})"
                        for a in prompt_info.arguments
                    )
                    or "none"
                )
                parts.append(
                    f"- **Prompt: {prompt_info.name}**: "
                    f"{prompt_info.description or 'No description'}\n"
                    f"  Arguments: {args}"
                )
                continue

            parts.append(f"- **{name}**: (primitive details not found)")

        return "\n".join(parts) if parts else "No primitive details available."
