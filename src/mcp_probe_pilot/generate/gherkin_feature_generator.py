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
from typing import TYPE_CHECKING, Any, Callable

from gherkin.parser import Parser as GherkinParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from mcp_probe_pilot.generate.prompts import (
    CANONICAL_STEP_LIBRARY,
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
MAX_SCENARIOS_PER_BATCH = 15
MAX_RETRIES = 1


class GherkinGenerationError(Exception):
    """Raised when generated content is not valid Gherkin."""


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
        server_command: str,
    ) -> None:
        self._llm = llm
        self._service_client = service_client
        self._output_dir = output_dir
        self._discovery = discovery_result
        self._server_command = server_command
        self._semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        self._generated_step_patterns: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_all(
        self,
        unit_plan: UnitTestPlanResult,
        integration_plan: IntegrationTestPlanResult,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> GenerationResult:
        """Generate all feature files sequentially to enable step reuse tracking.

        Features are processed one at a time so that steps extracted from each
        generated feature can be propagated to subsequent features, encouraging
        the LLM to reuse the same step patterns.

        Args:
            on_progress: Optional callback invoked with (event, prim_type, prim_name)
                where event is ``"start"``, ``"done"``, or ``"failed"``.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        summary = GenerationResult()

        generation_queue: list[tuple[str, str, list]] = []

        for tool in self._discovery.tools:
            scenarios = unit_plan.get_scenario_plans("tool", tool.name)
            if scenarios:
                generation_queue.append(("tool", tool.name, scenarios))

        for resource in self._discovery.resources:
            identifier = resource.name or resource.uri
            scenarios = unit_plan.get_scenario_plans("resource", identifier)
            if scenarios:
                generation_queue.append(("resource", identifier, scenarios))

        for prompt in self._discovery.prompts:
            scenarios = unit_plan.get_scenario_plans("prompt", prompt.name)
            if scenarios:
                generation_queue.append(("prompt", prompt.name, scenarios))

        for prim_type, prim_name, scenarios in generation_queue:
            if on_progress:
                on_progress("start", prim_type, prim_name)
            try:
                result = await self._generate_unit_feature(
                    prim_type, prim_name, scenarios
                )
                summary.files_generated += 1
                if result.get("warning"):
                    summary.validation_warnings.append(result["warning"])
                if on_progress:
                    on_progress("done", prim_type, prim_name)
            except Exception as exc:
                summary.files_failed += 1
                summary.validation_warnings.append(str(exc))
                logger.error("Feature generation failed for %s/%s: %s",
                           prim_type, prim_name, exc)
                if on_progress:
                    on_progress("failed", prim_type, prim_name)

        if integration_plan.integration_scenarios:
            if on_progress:
                on_progress("start", "integration", "integration_workflows")
            try:
                result = await self._generate_integration_feature(integration_plan)
                summary.files_generated += 1
                if result.get("warning"):
                    summary.validation_warnings.append(result["warning"])
                if on_progress:
                    on_progress("done", "integration", "integration_workflows")
            except Exception as exc:
                summary.files_failed += 1
                summary.validation_warnings.append(str(exc))
                logger.error("Integration feature generation failed: %s", exc)
                if on_progress:
                    on_progress("failed", "integration", "integration_workflows")

        logger.info(
            "Step reuse tracking: %d unique step patterns collected",
            len(self._generated_step_patterns)
        )

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
        """Generate a single .feature file for one MCP primitive.

        When the scenario count exceeds MAX_SCENARIOS_PER_BATCH the list is
        split into batches, each sent as an independent LLM call, and the
        resulting Gherkin blocks are merged into a single feature file.

        After generation, extracts step patterns and adds them to the shared
        step tracking set for reuse in subsequent features.
        """
        async with self._semaphore:
            logger.info("Generating %s unit feature: %s", prim_type, prim_name)

            code_context = await self._query_code_context(prim_name)

            batches = [
                scenarios[i : i + MAX_SCENARIOS_PER_BATCH]
                for i in range(0, len(scenarios), MAX_SCENARIOS_PER_BATCH)
            ]

            gherkin_parts: list[str] = []
            combined_warning: str | None = None

            for batch_idx, batch in enumerate(batches):
                label = f"{prim_type}/{prim_name}"
                if len(batches) > 1:
                    label += f" [batch {batch_idx + 1}/{len(batches)}]"

                human_content = self._render_unit_prompt(
                    prim_type, prim_name, batch, code_context
                )
                gherkin, warning = await self._generate_and_validate(
                    human_content, label
                )
                if warning:
                    combined_warning = warning
                gherkin_parts.append(gherkin)

            final = (
                self._merge_feature_batches(gherkin_parts)
                if len(gherkin_parts) > 1
                else gherkin_parts[0]
            )

            if not final.endswith("\n"):
                final += "\n"

            extracted_steps = self._extract_steps_from_gherkin(final)
            self._generated_step_patterns.update(extracted_steps)
            logger.debug(
                "Extracted %d steps from %s/%s, total tracked: %d",
                len(extracted_steps), prim_type, prim_name,
                len(self._generated_step_patterns)
            )

            safe_name = re.sub(r"[^\w]", "_", prim_name).lower()
            filename = f"{prim_type}_{safe_name}.feature"
            filepath = self._output_dir / filename
            filepath.write_text(final, encoding="utf-8")
            logger.info("Wrote feature file: %s", filepath)

            return {"file": str(filepath), "warning": combined_warning}

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

            base_content = Template(INTEGRATION_HUMAN).safe_substitute(
                scenarios=scenarios_text,
                primitives_summary=primitives_summary,
                code_context=code_context,
            )
            human_content = self._append_step_reuse_context(base_content)

            gherkin_content, warning = await self._generate_and_validate(
                human_content, "integration"
            )

            if not gherkin_content.endswith("\n"):
                gherkin_content += "\n"

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
        """Render the human-message template for a unit-test feature.

        Includes the canonical step library and any already-used steps from
        previously generated features to encourage step reuse.
        """
        scenarios_text = "\n".join(f"- {s.scenario}" for s in scenarios)
        base_content: str

        if prim_type == "tool":
            tool = self._discovery.get_tool(prim_name)
            if tool is None:
                raise ValueError(f"Tool '{prim_name}' not found in discovery result")
            schema_hints = self._extract_schema_hints(tool.input_schema or {})
            base_content = Template(TOOL_UNIT_HUMAN).safe_substitute(
                tool_name=tool.name,
                scenarios=scenarios_text,
                tool_description=tool.description or "No description",
                input_schema=json.dumps(tool.input_schema, indent=2),
                schema_hints=schema_hints,
                code_context=code_context,
            )

        elif prim_type == "resource":
            resource = self._find_resource(prim_name)
            if resource is None:
                raise ValueError(
                    f"Resource '{prim_name}' not found in discovery result"
                )
            base_content = Template(RESOURCE_UNIT_HUMAN).safe_substitute(
                resource_name=resource.name or resource.uri,
                scenarios=scenarios_text,
                resource_uri=resource.uri,
                resource_description=resource.description or "No description",
                mime_type=resource.mime_type or "unspecified",
                is_template=str(resource.is_template),
                code_context=code_context,
            )

        elif prim_type == "prompt":
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
            base_content = Template(PROMPT_UNIT_HUMAN).safe_substitute(
                prompt_name=prompt_info.name,
                scenarios=scenarios_text,
                prompt_description=prompt_info.description or "No description",
                arguments=args_repr,
                code_context=code_context,
            )

        else:
            raise ValueError(f"Unknown primitive type: {prim_type}")

        return self._append_step_reuse_context(base_content)

    @staticmethod
    def _extract_schema_hints(input_schema: dict) -> str:
        """Extract enum/default/pattern/examples from JSON schema properties."""
        hints: list[str] = []
        for prop, spec in input_schema.get("properties", {}).items():
            if not isinstance(spec, dict):
                continue
            parts: list[str] = []
            if "enum" in spec:
                parts.append(f"valid values: {spec['enum']}")
            if "default" in spec:
                parts.append(f"default: {spec['default']}")
            if "pattern" in spec:
                parts.append(f"format: {spec['pattern']}")
            if "examples" in spec:
                parts.append(f"examples: {spec['examples']}")
            if parts:
                hints.append(f"  - {prop}: {', '.join(parts)}")
        if not hints:
            return ""
        return "## Parameter Constraints\n" + "\n".join(hints)

    def _append_step_reuse_context(self, base_content: str) -> str:
        """Append canonical step library and used steps to prompt content."""
        parts = [base_content, CANONICAL_STEP_LIBRARY]

        if self._generated_step_patterns:
            used_steps_section = (
                "\n## Already Used Steps (MUST reuse these exact patterns):\n"
                + "\n".join(f"- {step}" for step in sorted(self._generated_step_patterns))
            )
            parts.append(used_steps_section)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _generate_and_validate(
        self, human_content: str, label: str
    ) -> tuple[str, str | None]:
        """Call the LLM, extract Gherkin, and validate.

        Retries up to MAX_RETRIES times on GherkinGenerationError before
        propagating the exception.
        """
        last_error: GherkinGenerationError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                raw_response = await self._call_llm(human_content)
                return self._process_llm_output(raw_response, label)
            except GherkinGenerationError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.info(
                        "[%s] Retrying generation (attempt %d/%d): %s",
                        label,
                        attempt + 2,
                        MAX_RETRIES + 1,
                        exc,
                    )
        raise last_error  # type: ignore[misc]

    async def _call_llm(self, human_content: str) -> str:
        """Send system + human messages to the LLM and return the raw text."""
        system_content = Template(SYSTEM_PROMPT).safe_substitute(
            server_command=self._server_command,
        )
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=human_content),
        ]
        response = await self._llm.ainvoke(messages)
        return response.content

    # ------------------------------------------------------------------
    # Code-context retrieval
    # ------------------------------------------------------------------

    async def _query_code_context(self, query: str) -> str:
        """Query ChromaDB for relevant source code snippets.

        Makes multiple queries to ensure the LLM sees not only the
        primitive implementation but also seed/fixture data and
        validation/error-handling logic from the same codebase.
        """
        queries = [
            query,
            f"{query} seed data initial state fixtures",
            f"{query} validation error handling",
        ]

        try:
            seen_names: set[str] = set()
            all_results: list = []
            for q in queries:
                results = await self._service_client.query_codebase(q, n_results=5)
                for r in results:
                    name = r.get("name", "") if isinstance(r, dict) else str(r)
                    if name not in seen_names:
                        seen_names.add(name)
                        all_results.append(r)

            if not all_results:
                return "No relevant source code found."

            parts: list[str] = []
            for r in all_results:
                if isinstance(r, str):
                    parts.append(f"```\n{r}\n```")
                    continue
                if not isinstance(r, dict):
                    continue
                lines = [
                    f"### {r.get('entity_type', 'code')}: "
                    f"{r.get('name', 'unknown')}"
                ]
                if r.get("file_path"):
                    lines.append(f"File: {r['file_path']}")
                code_text = r.get("code", r.get("document", r.get("text", "")))
                if code_text:
                    lines.append(f"```\n{code_text}\n```")
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
        """Extract gherkin, validate, and return (content, optional_warning).

        Raises GherkinGenerationError when the extracted content cannot be
        parsed as valid Gherkin syntax.
        """
        gherkin_content, has_end_marker = self._extract_gherkin(raw_response)
        warning: str | None = None

        if not has_end_marker:
            logger.warning(
                "[%s] Missing [END_OF_FEATURE], trimming last scenario", label
            )
            gherkin_content = self._remove_last_scenario(gherkin_content)
            warning = f"{label}: [END_OF_FEATURE] missing — last scenario trimmed"

        if not self._validate_gherkin(gherkin_content):
            raise GherkinGenerationError(
                f"{label}: Gherkin syntax validation failed"
            )

        ref_warnings = self._validate_primitive_references(gherkin_content)
        if ref_warnings:
            ref_msg = "; ".join(ref_warnings)
            logger.warning("[%s] Primitive reference issues: %s", label, ref_msg)
            warning = f"{warning}; {ref_msg}" if warning else ref_msg
            gherkin_content = self._strip_invalid_scenarios(gherkin_content)

        if not gherkin_content.endswith("\n"):
            gherkin_content += "\n"

        return gherkin_content, warning

    @staticmethod
    def _extract_gherkin(llm_response: str) -> tuple[str, bool]:
        """Pull the Gherkin text out of the LLM's markdown response.

        Returns (gherkin_text, end_of_feature_found).
        Raises GherkinGenerationError when no Gherkin content can be found.
        """
        has_end_marker = "[END_OF_FEATURE]" in llm_response

        match = re.search(r"```gherkin\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip(), has_end_marker

        match = re.search(r"```\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip(), has_end_marker

        content = llm_response.replace("[END_OF_FEATURE]", "").strip()
        if re.match(r"\s*(Feature:|@)", content):
            return content, has_end_marker

        raise GherkinGenerationError(
            "LLM response contains no recognizable Gherkin content"
        )

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

    _TOOL_REF_RE = re.compile(r'calls the tool "([^"]+)"')
    _RESOURCE_REF_RE = re.compile(r'reads the resource "([^"]+)"')
    _PROMPT_REF_RE = re.compile(r'gets the prompt "([^"]+)"')

    def _validate_primitive_references(self, gherkin_content: str) -> list[str]:
        """Check that tool/resource/prompt names in the Gherkin exist in discovery.

        Returns a list of warning strings (empty when all references are valid).
        """
        warnings: list[str] = []

        known_tools = {t.name for t in self._discovery.tools}
        for m in self._TOOL_REF_RE.finditer(gherkin_content):
            if m.group(1) not in known_tools:
                warnings.append(f"Unknown tool '{m.group(1)}'")

        known_resources = {r.uri for r in self._discovery.resources}
        known_resources |= {r.name for r in self._discovery.resources if r.name}
        for m in self._RESOURCE_REF_RE.finditer(gherkin_content):
            if m.group(1) not in known_resources:
                warnings.append(f"Unknown resource '{m.group(1)}'")

        known_prompts = {p.name for p in self._discovery.prompts}
        for m in self._PROMPT_REF_RE.finditer(gherkin_content):
            if m.group(1) not in known_prompts:
                warnings.append(f"Unknown prompt '{m.group(1)}'")

        return warnings

    def _strip_invalid_scenarios(self, gherkin_content: str) -> str:
        """Remove scenarios that reference unknown tools or prompts.

        Resource URI mismatches are excluded from stripping because the
        LLM legitimately generates non-existent URIs for negative /
        error-case test scenarios (e.g. ``user://non_existent_user/profile``).
        Only tool-name and prompt-name mismatches indicate true hallucinations.
        """
        known_tools = {t.name for t in self._discovery.tools}
        known_prompts = {p.name for p in self._discovery.prompts}

        scenario_re = re.compile(r"\s*(Scenario|Scenario Outline):")
        tag_re = re.compile(r"\s*@")

        lines = gherkin_content.split("\n")
        header_lines: list[str] = []
        blocks: list[list[str]] = []
        pending_tags: list[str] = []
        current_block: list[str] | None = None

        for line in lines:
            if scenario_re.match(line):
                if current_block is not None:
                    blocks.append(current_block)
                current_block = pending_tags + [line]
                pending_tags = []
            elif tag_re.match(line) and current_block is None:
                pending_tags.append(line)
            elif tag_re.match(line) and current_block is not None:
                blocks.append(current_block)
                current_block = None
                pending_tags = [line]
            elif current_block is not None:
                current_block.append(line)
            else:
                header_lines.extend(pending_tags)
                pending_tags = []
                header_lines.append(line)

        if current_block is not None:
            blocks.append(current_block)
        header_lines.extend(pending_tags)

        def _is_valid(block: list[str]) -> bool:
            text = "\n".join(block)
            for m in self._TOOL_REF_RE.finditer(text):
                if m.group(1) not in known_tools:
                    return False
            for m in self._PROMPT_REF_RE.finditer(text):
                if m.group(1) not in known_prompts:
                    return False
            return True

        kept = [b for b in blocks if _is_valid(b)]
        result = header_lines[:]
        for block in kept:
            result.extend(block)

        return "\n".join(result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_feature_batches(parts: list[str]) -> str:
        """Merge multiple feature-file outputs into one.

        Keeps the Feature header + Background from the first part and appends
        only the Scenario blocks extracted from subsequent parts.
        """
        if len(parts) <= 1:
            return parts[0] if parts else ""

        merged = parts[0].rstrip()

        for part in parts[1:]:
            scenarios = GherkinFeatureGenerator._extract_scenario_blocks(part)
            if scenarios:
                merged += "\n\n" + scenarios.rstrip()

        return merged + "\n"

    @staticmethod
    def _extract_scenario_blocks(gherkin_text: str) -> str:
        """Return everything from the first Scenario line onward.

        Includes any tag lines (``@...``) immediately preceding the first
        ``Scenario:`` or ``Scenario Outline:`` keyword.
        """
        lines = gherkin_text.split("\n")
        first_scenario: int | None = None

        for i, line in enumerate(lines):
            if re.match(r"\s*(Scenario|Scenario Outline):", line):
                first_scenario = i
                break

        if first_scenario is None:
            return ""

        start = first_scenario
        while start > 0 and lines[start - 1].strip().startswith("@"):
            start -= 1

        return "\n".join(lines[start:])

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

    @staticmethod
    def _extract_steps_from_gherkin(gherkin_text: str) -> set[str]:
        """Extract step patterns from generated Gherkin for reuse tracking.

        Returns a set of step text strings (without the Given/When/Then keyword)
        that can be used to inform subsequent feature generation.
        """
        steps: set[str] = set()
        for line in gherkin_text.split("\n"):
            match = re.match(r"\s*(Given|When|Then|And|But)\s+(.+)", line)
            if match:
                step_text = match.group(2).strip()
                if step_text and not step_text.startswith("|"):
                    steps.add(step_text)
        return steps
