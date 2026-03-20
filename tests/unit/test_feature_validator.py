"""Unit tests for the FeatureValidator."""

from __future__ import annotations

import pytest

from mcp_probe_pilot.core.models.gherkin_feature import (
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinScenario,
    GherkinStep,
    GherkinStepType,
)
from mcp_probe_pilot.validate.validator import (
    CanonicalStepRegistry,
    FeatureValidator,
    StepNormaliser,
    StepStatus,
    ValidationResult,
)


# ------------------------------------------------------------------
# CanonicalStepRegistry
# ------------------------------------------------------------------


class TestCanonicalStepRegistry:
    def test_matches_canonical_step(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match('the MCP Client calls the tool "search" with parameters')
        assert result is not None

    def test_no_match_for_unknown_step(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match("this step does not exist at all")
        assert result is None

    def test_case_insensitive_match(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match("the response should be successful")
        assert result is not None

    def test_match_for_keyword(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match_for_keyword(
            'the MCP Client calls the tool "search" with parameters',
            "when",
        )
        assert result is not None

    def test_no_match_wrong_keyword(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match_for_keyword(
            'the MCP Client calls the tool "search" with parameters',
            "then",
        )
        assert result is None

    def test_placeholder_matching(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match('the response should contain "task_id"')
        assert result is not None

    def test_integer_placeholder(self) -> None:
        registry = CanonicalStepRegistry()
        result = registry.match('the response field "count" should be 42')
        assert result is not None


# ------------------------------------------------------------------
# StepNormaliser
# ------------------------------------------------------------------


class TestStepNormaliser:
    def test_normalizes_contains_variation(self) -> None:
        normaliser = StepNormaliser()
        result = normaliser.normalise("the response contains data")
        assert result == "the response should contain data"

    def test_normalizes_error_variation(self) -> None:
        normaliser = StepNormaliser()
        result = normaliser.normalise("the response should be an error")
        assert result == "the response should be a failure"

    def test_no_change_for_canonical(self) -> None:
        normaliser = StepNormaliser()
        text = "the response should be successful"
        assert normaliser.normalise(text) == text


# ------------------------------------------------------------------
# FeatureValidator
# ------------------------------------------------------------------


class TestFeatureValidator:
    def test_compliant_steps_pass(self) -> None:
        validator = FeatureValidator()
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                scenarios=[
                    GherkinScenario(
                        name="s1",
                        steps=[
                            GherkinStep(
                                text="the response should be successful",
                                step_type=GherkinStepType.THEN,
                            ),
                        ],
                    ),
                ],
            ),
        ])
        result = validator.validate_collection(collection)

        assert result.is_valid
        assert result.compliant == 1
        assert result.rejected == 0

    def test_normalizable_step_is_fixed(self) -> None:
        validator = FeatureValidator()
        step = GherkinStep(
            text="the response should be unsuccessful",
            step_type=GherkinStepType.THEN,
        )
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                scenarios=[
                    GherkinScenario(name="s1", steps=[step]),
                ],
            ),
        ])
        result = validator.validate_collection(collection, auto_fix=True)

        assert result.normalised >= 1

    def test_unknown_step_is_rejected(self) -> None:
        validator = FeatureValidator()
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                scenarios=[
                    GherkinScenario(
                        name="s1",
                        steps=[
                            GherkinStep(
                                text="I do something completely unknown and weird",
                                step_type=GherkinStepType.WHEN,
                            ),
                        ],
                    ),
                ],
            ),
        ])
        result = validator.validate_collection(collection)

        assert not result.is_valid
        assert result.rejected >= 1
        assert len(result.rejected_steps) >= 1

    def test_empty_collection(self) -> None:
        validator = FeatureValidator()
        collection = GherkinFeatureCollection(features=[])
        result = validator.validate_collection(collection)

        assert result.is_valid
        assert result.total_steps == 0

    def test_background_steps_validated(self) -> None:
        validator = FeatureValidator()
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                background=[
                    GherkinStep(
                        text='the MCP Client is initialized and connected to the MCP Server: "test"',
                        step_type=GherkinStepType.GIVEN,
                    ),
                ],
                scenarios=[
                    GherkinScenario(
                        name="s1",
                        steps=[
                            GherkinStep(
                                text="the response should be successful",
                                step_type=GherkinStepType.THEN,
                            ),
                        ],
                    ),
                ],
            ),
        ])
        result = validator.validate_collection(collection)

        assert result.total_steps == 2
        assert result.compliant == 2

    def test_auto_fix_false_does_not_mutate(self) -> None:
        validator = FeatureValidator()
        step = GherkinStep(
            text="the response should be unsuccessful",
            step_type=GherkinStepType.THEN,
        )
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                scenarios=[
                    GherkinScenario(name="s1", steps=[step]),
                ],
            ),
        ])
        validator.validate_collection(collection, auto_fix=False)
        assert step.text == "the response should be unsuccessful"

    def test_validate_feature(self) -> None:
        validator = FeatureValidator()
        feature = GherkinFeature(
            name="test",
            scenarios=[
                GherkinScenario(
                    name="s1",
                    steps=[
                        GherkinStep(
                            text="the response should be successful",
                            step_type=GherkinStepType.THEN,
                        ),
                    ],
                ),
            ],
        )
        result = validator.validate_feature(feature)
        assert result.total_steps == 1
        assert result.compliant == 1
