"""Test evaluator: classifies test failures as SUT bugs or test implementation bugs."""

from __future__ import annotations

import logging
import re
from string import Template
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from mcp_probe_pilot.core.models.evaluation import EvaluationResults, StepVerdict
from mcp_probe_pilot.core.models.execution import TestExecutionResult
from mcp_probe_pilot.core.models.gherkin_feature import (
    GherkinFeatureCollection,
    GherkinStep,
)
from mcp_probe_pilot.evaluate.prompts import (
    EVALUATOR_SYSTEM_PROMPT,
    EVALUATOR_TEST_CONTEXT_PROMPT,
)

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from mcp_probe_pilot.core.service_client import MCPProbeServiceClient

logger = logging.getLogger(__name__)

_IMPORT_ERROR_RE = re.compile(
    r"(ImportError|ModuleNotFoundError|SyntaxError|IndentationError|TabError)"
    r".*?(?:steps\.py|steps/)",
    re.IGNORECASE | re.DOTALL,
)

_UNDEFINED_STEP_RE = re.compile(
    r"undefined",
    re.IGNORECASE,
)


class EvaluatorError(Exception):
    """Raised when the evaluator encounters a fatal problem."""


class TestEvaluator:
    """Classifies failed test scenarios via LLM as true negatives or false negatives."""

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        service_client: MCPProbeServiceClient,
    ) -> None:
        self._llm = llm
        self._service_client = service_client

    # ------------------------------------------------------------------
    # JSON parsing -> StepVerdicts
    # ------------------------------------------------------------------

    def parse_results(
        self,
        execution_result: TestExecutionResult,
        feature_collection: GherkinFeatureCollection,
    ) -> EvaluationResults:
        """Parse behave JSON output and build StepVerdicts for every step.

        Failed steps are deduplicated by text: if the same step text fails in
        multiple scenarios, their error messages are merged into one StepVerdict.
        """
        step_lookup = self._build_step_lookup(feature_collection)
        verdict_map: dict[str, StepVerdict] = {}

        for feature_json in execution_result.raw_json:
            for element in feature_json.get("elements", []):
                if element.get("type") != "scenario":
                    continue

                for step_json in element.get("steps", []):
                    step_result = step_json.get("result", {})
                    status = step_result.get("status", "undefined")

                    if status in ("passed",):
                        step_name = step_json.get("name", "")
                        if step_name and step_name not in verdict_map:
                            matched = step_lookup.get(step_name)
                            if matched:
                                verdict_map[step_name] = StepVerdict(step=matched)
                        continue

                    if status in ("failed", "undefined", "error"):
                        step_name = step_json.get("name", "")
                        raw_error = step_result.get("error_message", "")
                        if isinstance(raw_error, list):
                            error_msg = "\n".join(str(line) for line in raw_error)
                        else:
                            error_msg = str(raw_error) if raw_error else ""

                        if status == "undefined":
                            error_msg = error_msg or f"Step undefined: {step_name}"

                        matched = step_lookup.get(step_name)
                        if not matched:
                            matched = GherkinStep(
                                text=step_name,
                                step_type=self._infer_step_type(step_json),
                            )

                        if step_name in verdict_map:
                            if error_msg:
                                verdict_map[step_name].failure_logs.add(error_msg)
                        else:
                            logs = {error_msg} if error_msg else set()
                            verdict_map[step_name] = StepVerdict(
                                step=matched,
                                failure_logs=logs,
                            )

        verdicts = list(verdict_map.values())
        logger.info(
            "Parsed %d step verdicts (%d failed, %d passed)",
            len(verdicts),
            sum(1 for v in verdicts if len(v.failure_logs) > 0),
            sum(1 for v in verdicts if len(v.failure_logs) == 0),
        )
        return EvaluationResults(verdicts=verdicts)

    # ------------------------------------------------------------------
    # LLM-based classification
    # ------------------------------------------------------------------

    async def classify_verdicts(
        self,
        evaluation_results: EvaluationResults,
        steps_code: str,
    ) -> EvaluationResults:
        """Classify each failed step as true-negative or false-negative.

        Uses a regex fast-path for obvious import/syntax errors, then
        falls back to an LLM call for ambiguous failures.
        """
        for verdict in evaluation_results.verdicts:
            if len(verdict.failure_logs) == 0:
                continue

            combined_logs = "\n".join(verdict.failure_logs)

            if self._is_obvious_false_negative(combined_logs):
                verdict.is_false_negative = True
                logger.debug(
                    "Fast-path false_negative for step '%s'",
                    verdict.step.text,
                )
                continue

            verdict.is_false_negative = await self._classify_via_llm(
                verdict, steps_code
            )

        logger.info(
            "Classification complete: %d true negatives, %d false negatives",
            len(evaluation_results.true_negatives),
            len(evaluation_results.false_negatives),
        )
        return evaluation_results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_step_lookup(
        feature_collection: GherkinFeatureCollection,
    ) -> dict[str, GherkinStep]:
        """Build a text -> GherkinStep lookup from the feature collection."""
        lookup: dict[str, GherkinStep] = {}
        for step in feature_collection.get_all_steps():
            if step.text not in lookup:
                lookup[step.text] = step
        return lookup

    @staticmethod
    def _infer_step_type(step_json: dict):
        """Infer GherkinStepType from a behave JSON step entry."""
        from mcp_probe_pilot.core.models.gherkin_feature import GherkinStepType

        keyword = step_json.get("keyword", "").strip()
        mapping = {"Given": GherkinStepType.GIVEN, "When": GherkinStepType.WHEN, "Then": GherkinStepType.THEN}
        return mapping.get(keyword, GherkinStepType.GIVEN)

    @staticmethod
    def _is_obvious_false_negative(combined_logs: str) -> bool:
        """Check if the failure is an obvious test implementation bug."""
        if _IMPORT_ERROR_RE.search(combined_logs):
            return True
        if _UNDEFINED_STEP_RE.search(combined_logs):
            return True
        return False

    async def _classify_via_llm(
        self,
        verdict: StepVerdict,
        steps_code: str,
    ) -> bool:
        """Call the LLM to classify a single step failure.

        Returns True for false_negative, False for true_negative.
        """
        sut_context = await self._fetch_sut_context(verdict.step.text)

        human_content = Template(EVALUATOR_TEST_CONTEXT_PROMPT).safe_substitute(
            failed_step=f"{verdict.step.step_type.value} {verdict.step.text}",
            failed_step_log="\n".join(verdict.failure_logs),
            failed_scenarios="(see failure log above)",
            steps_code=steps_code,
            sut_context=sut_context,
        )

        messages = [
            SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        try:
            response = await self._llm.ainvoke(messages)
            answer = response.content.strip()
            is_false_negative = answer == "1"
            logger.debug(
                "LLM classified step '%s' as %s (raw: %s)",
                verdict.step.text,
                "false_negative" if is_false_negative else "true_negative",
                answer,
            )
            return is_false_negative
        except Exception as exc:
            logger.warning(
                "LLM classification failed for step '%s': %s — defaulting to false_negative",
                verdict.step.text,
                exc,
            )
            return True

    async def _fetch_sut_context(self, step_text: str) -> str:
        """Query the service for SUT source code relevant to a step."""
        try:
            results = await self._service_client.query_codebase(step_text)
            if not results:
                return "(no relevant SUT source code found)"
            sections = []
            for hit in results:
                code = hit.get("code", hit.get("document", ""))
                file_path = hit.get("file_path", "unknown")
                entity_name = hit.get("name", "")
                header = f"### {file_path}"
                if entity_name:
                    header += f" — {entity_name}"
                sections.append(f"{header}\n```python\n{code}\n```")
            return "\n\n".join(sections)
        except Exception as exc:
            logger.warning("Failed to fetch SUT context: %s", exc)
            return "(SUT context unavailable)"
