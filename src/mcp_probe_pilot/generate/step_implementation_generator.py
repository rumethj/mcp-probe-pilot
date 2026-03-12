"""Step implementation generator using LLM with AST-based deduplication.

Generates Python step definitions for behave BDD tests by:
1. Parsing existing steps.py to identify already-implemented step patterns
2. Processing each scenario and generating missing step implementations via LLM
3. Appending new implementations to steps.py
4. Validating the final output for syntax and completeness
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from mcp_probe_pilot.core.models.step_implementation import StepImplementationResult
from mcp_probe_pilot.generate.prompts import (
    STEP_IMPL_HUMAN_TEMPLATE,
    STEP_IMPL_SYSTEM_TEMPLATE,
)

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI

    from mcp_probe_pilot.core.models.gherkin_feature import (
        GherkinFeatureCollection,
        GherkinScenario,
        GherkinStep,
    )

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BEHAVE_DECORATORS = {"given", "when", "then"}


class StepImplementationError(Exception):
    """Raised when step implementation generation fails."""


class StepImplementationGenerator:
    """Generates step implementations for Gherkin scenarios via LLM."""

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        prebuilt_steps_code: str,
        output_dir: Path,
    ) -> None:
        self._llm = llm
        self._prebuilt_steps_code = prebuilt_steps_code
        self._output_dir = output_dir
        self._steps_file = output_dir / "steps" / "steps.py"
        self._implemented_patterns: dict[str, set[str]] = {}
        self._generated_code_blocks: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_all(
        self, feature_collection: GherkinFeatureCollection
    ) -> StepImplementationResult:
        """Generate step implementations for all scenarios in the collection.

        Processes each scenario sequentially, updating the implemented patterns
        as new steps are generated to avoid duplication.

        Returns:
            StepImplementationResult with generation statistics and any errors.
        """
        result = StepImplementationResult(output_file=self._steps_file)

        self._implemented_patterns = extract_implemented_steps(
            self._prebuilt_steps_code
        )
        logger.info(
            "Found %d prebuilt step patterns:", len(self._implemented_patterns)
        )
        
        for pattern, decorators in self._implemented_patterns.items():
            normalized = normalize_step_to_pattern(pattern)
            dec_str = ", ".join(f"@{d}" for d in sorted(decorators))
            logger.info("  %s('%s')", dec_str, pattern)
            logger.info("    -> normalized: '%s'", normalized)

        for feature in feature_collection.features:
            logger.info("Processing feature: %s", feature.name)
            for scenario in feature.scenarios:
                logger.info("  Checking scenario: %s", scenario.name)
                missing_steps = self._get_missing_steps(scenario)

                if not missing_steps:
                    logger.info(
                        "    -> No missing steps, skipping (%d steps all implemented)",
                        len(scenario.get_all_steps()),
                    )
                    result.steps_skipped += len(scenario.get_all_steps())
                    continue
                
                logger.info(
                    "    -> Found %d missing steps out of %d total",
                    len(missing_steps),
                    len(scenario.get_all_steps()),
                )

                try:
                    generated_code = await self._generate_for_scenario(
                        scenario=scenario,
                        feature_name=feature.name,
                        missing_steps=missing_steps,
                    )

                    if generated_code and generated_code.strip():
                        filtered_code = self._filter_duplicate_steps(
                            generated_code
                        )
                        if not filtered_code or not filtered_code.strip():
                            logger.info(
                                "    All LLM-generated steps were duplicates, "
                                "nothing to add"
                            )
                            continue

                        self._generated_code_blocks.append(filtered_code)
                        new_patterns = extract_implemented_steps(filtered_code)
                        if new_patterns:
                            for pattern, decorators in new_patterns.items():
                                normalized = normalize_step_to_pattern(pattern)
                                dec_str = ", ".join(
                                    f"@{d}" for d in sorted(decorators)
                                )
                                logger.debug(
                                    "  Generated: %s('%s') -> normalized: '%s'",
                                    dec_str, pattern, normalized
                                )
                        else:
                            logger.warning(
                                "  LLM generated code but no step patterns "
                                "extracted! Code:\n%s",
                                filtered_code[:500]
                            )
                        _merge_pattern_dicts(
                            self._implemented_patterns, new_patterns
                        )
                        result.steps_generated += len(new_patterns)
                        logger.info(
                            "Generated %d new steps for scenario '%s'",
                            len(new_patterns),
                            scenario.name,
                        )
                    else:
                        logger.warning(
                            "  LLM returned empty code for scenario '%s'",
                            scenario.name
                        )
                        result.steps_skipped += len(missing_steps)

                except StepImplementationError as exc:
                    error_msg = f"Scenario '{scenario.name}': {exc}"
                    result.validation_errors.append(error_msg)
                    logger.warning("Generation failed: %s", error_msg)

        self._write_final_steps_file()

        validation_errors = self._validate_final_output(feature_collection)
        result.validation_errors.extend(validation_errors)

        return result

    # ------------------------------------------------------------------
    # Step Analysis
    # ------------------------------------------------------------------

    def _get_missing_steps(self, scenario: GherkinScenario) -> list[GherkinStep]:
        """Identify steps in the scenario that don't have implementations."""
        missing = []
        for step in scenario.get_all_steps():
            pattern = normalize_step_to_pattern(step.text)
            is_implemented = self._pattern_is_implemented(pattern)
            if not is_implemented:
                missing.append(step)
                logger.info(
                    "      MISSING: '%s' -> '%s'",
                    step.text[:60], pattern
                )
        return missing

    def _pattern_is_implemented(self, normalized_pattern: str) -> bool:
        """Check if a normalized pattern matches any implemented step.
        
        Uses flexible matching where:
        - {placeholder} can match {number} (untyped behave placeholders accept any value)
        - {json_value} is treated distinctly (structured data)
        """
        for impl_pattern in self._implemented_patterns:
            impl_normalized = normalize_step_to_pattern(impl_pattern)
            if patterns_match(impl_normalized, normalized_pattern):
                logger.debug(
                    "Pattern match: '%s' ~= '%s' (impl: '%s')",
                    normalized_pattern, impl_normalized, impl_pattern
                )
                return True
        return False

    # ------------------------------------------------------------------
    # LLM Generation
    # ------------------------------------------------------------------

    async def _generate_for_scenario(
        self,
        scenario: GherkinScenario,
        feature_name: str,
        missing_steps: list[GherkinStep],
    ) -> str:
        """Generate step implementations for a single scenario via LLM.

        Retries up to MAX_RETRIES times on failure before raising.
        """
        scenario_text = self._format_scenario_text(scenario)
        existing_steps_list = self._format_existing_steps_list()

        system_content = Template(STEP_IMPL_SYSTEM_TEMPLATE).safe_substitute(
            existing_steps_list=existing_steps_list,
        )
        human_content = Template(STEP_IMPL_HUMAN_TEMPLATE).safe_substitute(
            feature_name=feature_name,
            scenario_name=scenario.name,
            scenario_text=scenario_text,
        )

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._call_llm(system_content, human_content)
                code = self._extract_python_code(response)

                ast.parse(code)
                return code

            except SyntaxError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d for scenario '%s': syntax error - %s",
                        attempt + 1,
                        MAX_RETRIES,
                        scenario.name,
                        exc,
                    )
            except StepImplementationError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d for scenario '%s': %s",
                        attempt + 1,
                        MAX_RETRIES,
                        scenario.name,
                        exc,
                    )

        raise StepImplementationError(
            f"Failed after {MAX_RETRIES + 1} attempts: {last_error}"
        )

    async def _call_llm(self, system_content: str, human_content: str) -> str:
        """Send messages to the LLM and return the response text."""
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=human_content),
        ]
        response = await self._llm.ainvoke(messages)
        return response.content

    # ------------------------------------------------------------------
    # Text Formatting
    # ------------------------------------------------------------------

    def _format_scenario_text(self, scenario: GherkinScenario) -> str:
        """Format a scenario as Gherkin text for the prompt."""
        lines = [f"Scenario: {scenario.name}"]

        for step in scenario.get_all_steps():
            lines.append(f"  {step.step_type.value} {step.text}")
            if step.data_table:
                for table_line in step.data_table.format(indent="    "):
                    lines.append(table_line)

        return "\n".join(lines)

    def _format_existing_steps_list(self) -> str:
        """Format the list of already-implemented step patterns."""
        if not self._implemented_patterns:
            return "(none)"

        lines = []
        for pattern, decorators in sorted(self._implemented_patterns.items()):
            for dec in sorted(decorators):
                lines.append(f"- @{dec}('{pattern}')")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Code Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_python_code(llm_response: str) -> str:
        """Extract Python code from the LLM's markdown response.

        Expects code in a ```python ... ``` block ending with # EOF.
        """
        match = re.search(r"```python\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            code = match.group(1).strip()
            code = re.sub(r"#\s*EOF\s*$", "", code).strip()
            return code

        match = re.search(r"```\s*\n(.*?)```", llm_response, re.DOTALL)
        if match:
            code = match.group(1).strip()
            code = re.sub(r"#\s*EOF\s*$", "", code).strip()
            return code

        raise StepImplementationError(
            "LLM response does not contain a valid Python code block"
        )

    # ------------------------------------------------------------------
    # Duplicate Filtering
    # ------------------------------------------------------------------

    def _filter_duplicate_steps(self, code: str) -> str:
        """Remove step functions whose patterns already exist.

        When the LLM over-generates and returns implementations for steps
        that are already present in the prebuilts or previously generated
        code, this strips them out so behave doesn't raise AmbiguousStep.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        lines = code.split("\n")
        lines_to_remove: set[int] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue

            step_decorators: list[tuple[str, str]] = []
            for dec in node.decorator_list:
                pattern, dec_name = _extract_pattern_from_decorator(dec)
                if pattern and dec_name:
                    step_decorators.append((pattern, dec_name))

            if not step_decorators:
                continue

            all_implemented = all(
                self._pattern_is_implemented(normalize_step_to_pattern(p))
                for p, _ in step_decorators
            )

            if all_implemented:
                start = node.decorator_list[0].lineno - 1
                end = node.end_lineno
                for i in range(start, end):
                    lines_to_remove.add(i)

                logger.info(
                    "  Filtering duplicate step from LLM output: %s",
                    ", ".join(
                        f"@{d}('{p}')" for p, d in step_decorators
                    ),
                )

        if not lines_to_remove:
            return code

        filtered = [
            line for i, line in enumerate(lines) if i not in lines_to_remove
        ]
        return "\n".join(filtered)

    # ------------------------------------------------------------------
    # File Output
    # ------------------------------------------------------------------

    def _write_final_steps_file(self) -> None:
        """Write the combined prebuilt + generated code to steps.py."""
        self._steps_file.parent.mkdir(parents=True, exist_ok=True)

        parts = [self._prebuilt_steps_code.rstrip()]

        if self._generated_code_blocks:
            parts.append("\n\n# " + "=" * 42)
            parts.append("# Auto-generated step implementations")
            parts.append("# " + "=" * 42 + "\n")

            for block in self._generated_code_blocks:
                clean_block = self._clean_generated_block(block)
                if clean_block:
                    parts.append(clean_block)

        final_code = "\n".join(parts)
        if not final_code.endswith("\n"):
            final_code += "\n"

        self._steps_file.write_text(final_code, encoding="utf-8")
        logger.info("Wrote final steps file: %s", self._steps_file)

    @staticmethod
    def _clean_generated_block(code: str) -> str:
        """Remove duplicate imports and clean up generated code block."""
        lines = code.split("\n")
        cleaned = []
        for line in lines:
            if line.strip().startswith("from behave import"):
                continue
            if line.strip().startswith("import json") and not cleaned:
                continue
            cleaned.append(line)

        result = "\n".join(cleaned).strip()
        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_final_output(
        self, feature_collection: GherkinFeatureCollection
    ) -> list[str]:
        """Validate the final steps.py file.

        Checks:
        1. Valid Python syntax
        2. All required step patterns have implementations
        """
        errors: list[str] = []

        try:
            final_code = self._steps_file.read_text(encoding="utf-8")
            ast.parse(final_code)
        except SyntaxError as exc:
            errors.append(f"Final steps.py has invalid syntax: {exc}")
            return errors

        final_patterns = extract_implemented_steps(final_code)
        logger.info("Final steps.py has %d step patterns", len(final_patterns))

        required_patterns: dict[str, str] = {}
        for step_text in feature_collection.get_unique_step_texts():
            normalized = normalize_step_to_pattern(step_text)
            required_patterns[normalized] = step_text
        
        logger.info("Feature collection requires %d unique normalized patterns", len(required_patterns))

        implemented_normalized: dict[str, str] = {}
        for impl_pattern in final_patterns:
            normalized = normalize_step_to_pattern(impl_pattern)
            implemented_normalized[normalized] = impl_pattern

        logger.info("Implemented patterns (normalized): %d", len(implemented_normalized))

        missing_patterns = []
        for required_norm, original_step in required_patterns.items():
            found = False
            for impl_norm in implemented_normalized.keys():
                if patterns_match(impl_norm, required_norm):
                    found = True
                    break
            if not found:
                missing_patterns.append((required_norm, original_step))
        
        if missing_patterns:
            logger.warning("Found %d missing patterns:", len(missing_patterns))
            for pattern, original_step in missing_patterns:
                logger.warning(
                    "  MISSING: '%s' (original: '%s')",
                    pattern, original_step
                )
                errors.append(f"Missing step implementation for pattern: {pattern}")

        return errors


# ------------------------------------------------------------------
# Module-level utilities
# ------------------------------------------------------------------


def extract_implemented_steps(code: str) -> dict[str, set[str]]:
    """Parse Python code and extract behave step decorator patterns.

    Returns a dict mapping step pattern strings to the set of decorator
    names (given, when, then) that use that pattern.  A single function
    decorated with both ``@when`` and ``@given`` will have both entries
    in the set.

    Args:
        code: Python source code containing behave step definitions.

    Returns:
        Dict mapping pattern strings to sets of decorator names.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        logger.warning("Failed to parse code for step extraction")
        return {}

    steps: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        for decorator in node.decorator_list:
            pattern, decorator_name = _extract_pattern_from_decorator(decorator)
            if pattern and decorator_name:
                if pattern not in steps:
                    steps[pattern] = set()
                steps[pattern].add(decorator_name)

    return steps


def _merge_pattern_dicts(
    target: dict[str, set[str]],
    source: dict[str, set[str]],
) -> None:
    """Merge *source* into *target*, unioning decorator sets."""
    for pattern, decorators in source.items():
        if pattern in target:
            target[pattern].update(decorators)
        else:
            target[pattern] = set(decorators)


def _extract_pattern_from_decorator(
    decorator: ast.expr,
) -> tuple[str | None, str | None]:
    """Extract the step pattern and decorator name from an AST decorator node.

    Handles both @given('pattern') and @given(u'pattern') forms.
    """
    if isinstance(decorator, ast.Call):
        func = decorator.func
        decorator_name: str | None = None

        if isinstance(func, ast.Name) and func.id in BEHAVE_DECORATORS:
            decorator_name = func.id
        elif isinstance(func, ast.Attribute) and func.attr in BEHAVE_DECORATORS:
            decorator_name = func.attr

        if decorator_name and decorator.args:
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(
                first_arg.value, str
            ):
                return first_arg.value, decorator_name

    return None, None


def patterns_match(impl_pattern: str, required_pattern: str) -> bool:
    """Check if an implemented pattern can satisfy a required pattern.
    
    Flexible matching rules:
    - Exact match is always valid
    - {placeholder} in impl can match {number} in required (untyped placeholders accept numbers)
    - {placeholder} can match "{placeholder}" (quoted vs unquoted behave placeholders)
    - {json_value} matches {placeholder} (a generic behave placeholder captures any string,
      including a JSON array literal like '["a","b"]')
    - Comparison is case-insensitive (behave step matching ignores case)
    
    Args:
        impl_pattern: Normalized pattern from implemented step
        required_pattern: Normalized pattern from feature file
        
    Returns:
        True if the impl_pattern can satisfy the required_pattern
    """
    # Behave's step matcher is case-insensitive, so we must be too.
    # e.g. "Connected" in a feature file matches "connected" in a step decorator.
    if impl_pattern.lower() == required_pattern.lower():
        return True
    
    impl_generic = _to_generic_pattern(impl_pattern)
    req_generic = _to_generic_pattern(required_pattern)
    
    return impl_generic.lower() == req_generic.lower()


def _to_generic_pattern(pattern: str) -> str:
    """Convert a pattern to generic form for flexible matching.
    
    Normalizes:
    - {number} -> {placeholder}
    - "{placeholder}" -> {placeholder} (removes quote distinction)
    - {json_value} -> {placeholder} (an untyped behave placeholder like {expected_list}
      captures any string at runtime, including JSON arrays such as '["a","b"]',
      so the normalizer must treat them as equivalent)
    """
    result = pattern.replace("{number}", "{placeholder}")
    result = result.replace('"{placeholder}"', "{placeholder}")
    result = result.replace("{json_value}", "{placeholder}")
    return result


def normalize_step_to_pattern(step_text: str) -> str:
    """Convert a concrete step text to a normalized pattern for matching.

    Replaces (in order):
    - JSON arrays [...] with {json_value}
    - Behave type converters like {name:int} or {name:d} with {number}
    - Quoted string values with "{placeholder}"
    - Unquoted behave placeholders like {name} with {placeholder} (except reserved ones)
    - Standalone integers with {number}

    Examples:
        'the response should contain "task_id"' -> 'the response should contain "{placeholder}"'
        'the response field "count" should be 42' -> 'the response field "{placeholder}" should be {number}'
        'the response field "tags" should be ["a", "b"]' -> 'the response field "{placeholder}" should be {json_value}'
        'value {expected:int}' -> 'value {number}'
        'has field {field}' -> 'has field {placeholder}'
    """
    step_text = re.sub(r"\s*\|\s*$", "", step_text)
    pattern = re.sub(r"\[.*?\]", "{json_value}", step_text)
    pattern = re.sub(r"\{[^}]+:d\}", "{number}", pattern)
    pattern = re.sub(r"\{[^}]+:int\}", "{number}", pattern)
    pattern = re.sub(r'"[^"]*"', '"{placeholder}"', pattern)

    def replace_placeholder(match: re.Match) -> str:
        name = match.group(1)
        if name in ("json_value", "number", "placeholder"):
            return match.group(0)
        return "{placeholder}"

    pattern = re.sub(r"\{([^}:]+)\}", replace_placeholder, pattern)
    pattern = re.sub(r"(?<![\"{}])\b\d+\b(?![\"{}])", "{number}", pattern)
    return pattern
