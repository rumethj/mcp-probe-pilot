"""Unit tests for the GherkinFormatter, GherkinParser, and StepNormalizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_probe_pilot.core.models.gherkin_feature import (
    DataTable,
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinScenario,
    GherkinStep,
    GherkinStepType,
)
from mcp_probe_pilot.generate.gherkin_formatter import (
    GherkinFormatter,
    GherkinParser,
    StepNormalizer,
)


SAMPLE_FEATURE = """\
Feature: Sample feature
  As a tester
  I want to test

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test"

  Scenario: Happy path
    When the MCP Client calls the tool "search" with parameters
      | parameter | value |
      | query     | test  |
    Then the response should be successful
"""


# ------------------------------------------------------------------
# GherkinParser
# ------------------------------------------------------------------


class TestGherkinParser:
    def test_parse_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.feature"
        f.write_text(SAMPLE_FEATURE)

        parser = GherkinParser()
        feature = parser.parse_file(f)

        assert feature is not None
        assert feature.name == "Sample feature"
        assert len(feature.scenarios) == 1
        assert feature.scenarios[0].name == "Happy path"

    def test_parse_background(self, tmp_path: Path) -> None:
        f = tmp_path / "test.feature"
        f.write_text(SAMPLE_FEATURE)

        parser = GherkinParser()
        feature = parser.parse_file(f)

        assert feature.background is not None
        assert len(feature.background) == 1
        assert feature.background[0].step_type == GherkinStepType.GIVEN

    def test_parse_data_table(self, tmp_path: Path) -> None:
        f = tmp_path / "test.feature"
        f.write_text(SAMPLE_FEATURE)

        parser = GherkinParser()
        feature = parser.parse_file(f)

        when_step = feature.scenarios[0].when_steps[0]
        assert when_step.data_table is not None
        assert when_step.data_table.headers == ["parameter", "value"]
        assert when_step.data_table.rows == [["query", "test"]]

    def test_parse_tags(self, tmp_path: Path) -> None:
        content = """\
Feature: Tags test

  @happy-path @smoke
  Scenario: Tagged scenario
    Given the MCP Client is initialized and connected to the MCP Server: "test"
    Then the response should be successful
"""
        f = tmp_path / "tags.feature"
        f.write_text(content)

        parser = GherkinParser()
        feature = parser.parse_file(f)
        assert feature.scenarios[0].tags == ["happy-path", "smoke"]

    def test_parse_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.feature").write_text(SAMPLE_FEATURE)
        (tmp_path / "b.feature").write_text(SAMPLE_FEATURE.replace("Sample feature", "Another feature"))

        parser = GherkinParser()
        collection = parser.parse_directory(tmp_path)

        assert len(collection.features) == 2

    def test_parse_invalid_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.feature"
        f.write_text("this is not gherkin at all")

        parser = GherkinParser()
        result = parser.parse_file(f)
        assert result is None

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        parser = GherkinParser()
        result = parser.parse_file(tmp_path / "nope.feature")
        assert result is None


# ------------------------------------------------------------------
# StepNormalizer
# ------------------------------------------------------------------


class TestStepNormalizer:
    def test_response_contains_normalization(self) -> None:
        normalizer = StepNormalizer()
        assert normalizer.normalize_text("the response contains a key") == "the response should contain key"

    def test_response_has_normalization(self) -> None:
        normalizer = StepNormalizer()
        assert normalizer.normalize_text("the response has result") == "the response should contain result"

    def test_failure_normalization(self) -> None:
        normalizer = StepNormalizer()
        assert normalizer.normalize_text("the response should be unsuccessful") == "the response should be a failure"

    def test_boolean_quoting(self) -> None:
        normalizer = StepNormalizer()
        assert normalizer.normalize_text('with value True') == 'with value "True"'
        assert normalizer.normalize_text('with value False') == 'with value "False"'

    def test_table_header_normalization(self) -> None:
        normalizer = StepNormalizer()
        assert normalizer.normalize_table_header("parameter_name") == "parameter"
        assert normalizer.normalize_table_header("parameter_value") == "value"

    def test_normalize_step_mutates_in_place(self) -> None:
        normalizer = StepNormalizer()
        step = GherkinStep(
            text="the response contains a result",
            step_type=GherkinStepType.THEN,
        )
        normalizer.normalize_step(step)
        assert step.text == "the response should contain result"

    def test_normalize_step_with_data_table(self) -> None:
        normalizer = StepNormalizer()
        step = GherkinStep(
            text="call with parameters",
            step_type=GherkinStepType.WHEN,
            data_table=DataTable(
                headers=["parameter_name", "parameter_value"],
                rows=[["query", "test"]],
            ),
        )
        normalizer.normalize_step(step)
        assert step.data_table.headers == ["parameter", "value"]

    def test_fixup_saved_param_table(self) -> None:
        normalizer = StepNormalizer()
        step = GherkinStep(
            text='the MCP Client calls the tool "search" with parameters',
            step_type=GherkinStepType.WHEN,
            data_table=DataTable(
                headers=["parameter", "value"],
                rows=[["query", "{saved_query}"]],
            ),
        )
        normalizer.normalize_step(step)
        assert "with saved parameters" in step.text
        assert step.data_table.headers[1] == "saved_variable"
        assert step.data_table.rows[0][1] == "saved_query"


# ------------------------------------------------------------------
# GherkinFormatter
# ------------------------------------------------------------------


class TestGherkinFormatter:
    def test_format_directory(self, tmp_path: Path) -> None:
        (tmp_path / "test.feature").write_text(SAMPLE_FEATURE)

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        assert isinstance(collection, GherkinFeatureCollection)
        assert len(collection.features) == 1

    def test_normalize_all_steps_counts(self) -> None:
        formatter = GherkinFormatter()
        collection = GherkinFeatureCollection(features=[
            GherkinFeature(
                name="test",
                scenarios=[
                    GherkinScenario(
                        name="s1",
                        steps=[
                            GherkinStep(text="the response contains a result", step_type=GherkinStepType.THEN),
                        ],
                    ),
                ],
            ),
        ])
        count = formatter.normalize_all_steps(collection)
        assert count == 1

    def test_write_feature_files(self, tmp_path: Path) -> None:
        feature = GherkinFeature(
            name="test",
            file_path=tmp_path / "test.feature",
            scenarios=[
                GherkinScenario(
                    name="s1",
                    steps=[
                        GherkinStep(text="the response should be successful", step_type=GherkinStepType.THEN),
                    ],
                ),
            ],
        )
        collection = GherkinFeatureCollection(features=[feature])

        formatter = GherkinFormatter()
        formatter.write_feature_files(collection)

        assert (tmp_path / "test.feature").exists()
        content = (tmp_path / "test.feature").read_text()
        assert "Feature: test" in content

    def test_empty_directory(self, tmp_path: Path) -> None:
        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)
        assert collection.features == []
