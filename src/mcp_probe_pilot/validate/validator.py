"""Validator for generated Gherkin scenarios.

Ensures every step in a generated feature file matches one of the canonical
step patterns defined in the step library.  Non-compliant steps are
auto-normalised where possible; unfixable ones are reported as rejections.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from mcp_probe_pilot.core.canonical_steps import CANONICAL_PATTERNS
from mcp_probe_pilot.core.models.gherkin_feature import (
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinStep,
    GherkinStepType,
)

logger = logging.getLogger(__name__)

# Text normalization rules applied before matching (pattern, replacement).
# More specific rules come first.
NORMALIZATION_RULES: list[tuple[str, str]] = [
    (r"the response contains a ", "the response should contain "),
    (r"the response contains ", "the response should contain "),
    (r"the response should contain a ", "the response should contain "),
    (r"the response has ", "the response should contain "),
    (r"the response should be unsuccessful", "the response should be a failure"),
    (r"the response should be an error", "the response should be a failure"),
    (r"the response has error", "the response should be a failure"),
    (r'the response field "([^"]+)" should equal', r'the response field "\1" should be'),
    (r'the response "([^"]+)" should be', r'the response field "\1" should be'),
    (r"the error should indicate", "the error message should indicate"),
    (r"the response should be semantically relevant to .+", "the response should be successful"),
    (r'the MCP Client queries ".+"', ""),
    # Unquoted boolean values
    (r'with value True\b', 'with value "True"'),
    (r'with value False\b', 'with value "False"'),
]


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

class StepStatus(Enum):
    COMPLIANT = "compliant"
    NORMALISED = "normalised"
    REJECTED = "rejected"


@dataclass
class StepComplianceResult:
    original_text: str
    status: StepStatus
    matched_pattern: Optional[str] = None
    normalised_text: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class FeatureValidationResult:
    feature_name: str
    total_steps: int = 0
    compliant: int = 0
    normalised: int = 0
    rejected: int = 0
    step_results: list[StepComplianceResult] = field(default_factory=list)


@dataclass
class ValidationResult:
    total_features: int = 0
    total_steps: int = 0
    compliant: int = 0
    normalised: int = 0
    rejected: int = 0
    feature_results: list[FeatureValidationResult] = field(default_factory=list)
    rejected_steps: list[StepComplianceResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.rejected == 0


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

class CanonicalStepRegistry:
    """Builds regex matchers from the canonical step patterns."""

    def __init__(
        self, patterns: list[tuple[str, str]] | None = None
    ) -> None:
        raw = patterns or CANONICAL_PATTERNS
        self._patterns: list[tuple[str, re.Pattern, str]] = []
        for keyword, text in raw:
            regex = self._pattern_to_regex(text)
            self._patterns.append((keyword, regex, text))

    @staticmethod
    def _pattern_to_regex(pattern_text: str) -> re.Pattern:
        """Convert a canonical step pattern to a compiled regex.

        Placeholders are turned into capture groups:
          "{...}"      -> "([^"]+)"
          {name:d}     -> (\\d+)
          {name}       -> (.+)
          []           -> \\[\\]  (literal empty list)
        """
        escaped = re.escape(pattern_text)

        # Restore placeholder tokens that re.escape mangled
        # "{placeholder}" -> quoted capture
        escaped = re.sub(
            r'\\"\\\{[^}]+\\\}\\"',
            r'"([^"]+)"',
            escaped,
        )
        # {name:d} -> integer capture
        escaped = re.sub(
            r'\\\{[^}]+\\:d\\\}',
            r'(\\d+)',
            escaped,
        )
        # {json_list} or other bare placeholders -> greedy capture
        escaped = re.sub(
            r'\\\{[^}]+\\\}',
            r'(.+)',
            escaped,
        )
        # literal [] (empty list assertion)
        escaped = escaped.replace(r'\[\]', r'\[\]')

        return re.compile(f"^{escaped}$", re.IGNORECASE)

    def match(self, step_text: str) -> Optional[str]:
        """Return the canonical pattern text if *step_text* matches, else None."""
        cleaned = step_text.strip()
        for _kw, regex, canonical_text in self._patterns:
            if regex.match(cleaned):
                return canonical_text
        return None

    def match_for_keyword(
        self, step_text: str, keyword: str
    ) -> Optional[str]:
        """Match against patterns filtered by keyword (given/when/then)."""
        cleaned = step_text.strip()
        kw_lower = keyword.lower()
        for pat_kw, regex, canonical_text in self._patterns:
            if pat_kw != kw_lower:
                continue
            if regex.match(cleaned):
                return canonical_text
        return None


# ------------------------------------------------------------------
# Normaliser
# ------------------------------------------------------------------

class StepNormaliser:
    """Apply text-level normalization rules to bring steps closer to canonical form."""

    def __init__(
        self, rules: list[tuple[str, str]] | None = None
    ) -> None:
        raw = rules or NORMALIZATION_RULES
        self._rules = [(re.compile(p), r) for p, r in raw]

    def normalise(self, text: str) -> str:
        result = text
        for pattern, replacement in self._rules:
            result = pattern.sub(replacement, result)
        return result


# ------------------------------------------------------------------
# Validator
# ------------------------------------------------------------------

class FeatureValidator:
    """Validate and normalise generated feature files against the canonical step library.

    Usage::

        validator = FeatureValidator()
        result = validator.validate_collection(feature_collection)
        if not result.is_valid:
            # handle rejected steps …
    """

    def __init__(
        self,
        registry: CanonicalStepRegistry | None = None,
        normaliser: StepNormaliser | None = None,
    ) -> None:
        self._registry = registry or CanonicalStepRegistry()
        self._normaliser = normaliser or StepNormaliser()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_collection(
        self,
        collection: GherkinFeatureCollection,
        *,
        auto_fix: bool = True,
    ) -> ValidationResult:
        """Validate every step in *collection*.

        When *auto_fix* is ``True`` (default), steps that can be normalised
        are rewritten in place so the collection is ready for step-impl
        generation.
        """
        result = ValidationResult(total_features=len(collection.features))

        for feature in collection.features:
            feat_result = self._validate_feature(feature, auto_fix=auto_fix)
            result.feature_results.append(feat_result)
            result.total_steps += feat_result.total_steps
            result.compliant += feat_result.compliant
            result.normalised += feat_result.normalised
            result.rejected += feat_result.rejected
            result.rejected_steps.extend(
                sr for sr in feat_result.step_results
                if sr.status == StepStatus.REJECTED
            )

        logger.info(
            "Validation complete: %d steps — %d compliant, %d normalised, %d rejected",
            result.total_steps,
            result.compliant,
            result.normalised,
            result.rejected,
        )
        return result

    def validate_feature(
        self,
        feature: GherkinFeature,
        *,
        auto_fix: bool = True,
    ) -> FeatureValidationResult:
        return self._validate_feature(feature, auto_fix=auto_fix)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _validate_feature(
        self, feature: GherkinFeature, *, auto_fix: bool
    ) -> FeatureValidationResult:
        feat_result = FeatureValidationResult(feature_name=feature.name)

        all_steps = feature.get_all_steps()
        feat_result.total_steps = len(all_steps)

        for step in all_steps:
            sr = self._validate_step(step, auto_fix=auto_fix)
            feat_result.step_results.append(sr)
            if sr.status == StepStatus.COMPLIANT:
                feat_result.compliant += 1
            elif sr.status == StepStatus.NORMALISED:
                feat_result.normalised += 1
            else:
                feat_result.rejected += 1

        return feat_result

    def _validate_step(
        self, step: GherkinStep, *, auto_fix: bool
    ) -> StepComplianceResult:
        text = step.text.strip()

        # 1) Direct match
        matched = self._registry.match(text)
        if matched:
            return StepComplianceResult(
                original_text=text,
                status=StepStatus.COMPLIANT,
                matched_pattern=matched,
            )

        # 2) Normalise, then re-match
        normalised = self._normaliser.normalise(text)

        if not normalised or not normalised.strip():
            logger.warning(
                "Step normalised to empty (likely LLM-dependent), removing: '%s'",
                text,
            )
            return StepComplianceResult(
                original_text=text,
                status=StepStatus.REJECTED,
                reason="Step resolved to empty after normalization (LLM-dependent step)",
            )

        if normalised != text:
            matched = self._registry.match(normalised)
            if matched:
                if auto_fix:
                    step.text = normalised
                    logger.debug(
                        "Normalised step: '%s' -> '%s'", text, normalised
                    )
                return StepComplianceResult(
                    original_text=text,
                    status=StepStatus.NORMALISED,
                    matched_pattern=matched,
                    normalised_text=normalised,
                )

        # 3) Fuzzy match via Levenshtein-like proximity
        best = self._fuzzy_match(normalised)
        if best:
            logger.warning(
                "Step '%s' did not match but is close to canonical '%s'",
                text,
                best,
            )

        return StepComplianceResult(
            original_text=text,
            status=StepStatus.REJECTED,
            reason=f"No canonical match found. Closest: '{best}'" if best else "No canonical match found",
        )

    def _fuzzy_match(self, text: str) -> Optional[str]:
        """Find the closest canonical pattern by simple token overlap."""
        text_tokens = set(text.lower().split())
        best_score = 0.0
        best_pattern = None

        for _kw, _regex, canonical in self._registry._patterns:
            canonical_generic = re.sub(r'\{[^}]+\}', '', canonical)
            canonical_generic = re.sub(r'"[^"]*"', '', canonical_generic)
            canon_tokens = set(canonical_generic.lower().split())

            if not canon_tokens:
                continue

            overlap = len(text_tokens & canon_tokens)
            score = overlap / max(len(canon_tokens), 1)

            if score > best_score:
                best_score = score
                best_pattern = canonical

        return best_pattern if best_score >= 0.4 else None
