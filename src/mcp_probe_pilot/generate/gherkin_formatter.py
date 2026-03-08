"""Post-generation Gherkin normalization for step consistency.

Normalizes feature file step text to canonical forms, reducing the number of
unique step patterns that need implementations.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from mcp_probe_pilot.core.models.gherkin_feature import (
    DataTable,
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinScenario,
    GherkinStep,
    GherkinStepType,
)

logger = logging.getLogger(__name__)


# Text-only normalization rules (keywords are handled separately via step_type)
# Order matters - more specific patterns should come before general ones
NORMALIZATION_RULES: list[tuple[str, str]] = [
    # Response containment variations - order matters!
    # First normalize "contains a" to "should contain" (drop the "a")
    (r"the response contains a ", "the response should contain "),
    # Then normalize remaining "contains" without "a"
    (r"the response contains ", "the response should contain "),
    # Normalize "should contain a" to "should contain" (drop the "a")
    (r"the response should contain a ", "the response should contain "),
    # Handle "has" variations
    (r"the response has ", "the response should contain "),
    # Failure variations
    (r"the response should be unsuccessful", "the response should be a failure"),
    (r"the response should be an error", "the response should be a failure"),
    (r"the response has error", "the response should be a failure"),
    # Field assertion variations
    (
        r'the response field "([^"]+)" should equal',
        r'the response field "\1" should be',
    ),
    (r'the response "([^"]+)" should be', r'the response field "\1" should be'),
    # Error message variations
    (r"the error should indicate", "the error message should indicate"),
]

# Data table header normalization
TABLE_HEADER_RULES: list[tuple[str, str]] = [
    (r"parameter_name", "parameter"),
    (r"parameter_value", "value"),
]


class GherkinParser:
    """Parses Gherkin feature files into GherkinFeatureCollection model."""

    def __init__(self) -> None:
        self._parser = Parser()

    def parse_file(self, file_path: Path) -> Optional[GherkinFeature]:
        """Parse a single .feature file into a GherkinFeature model."""
        try:
            content = file_path.read_text(encoding="utf-8")
            scanner = TokenScanner(content)
            gherkin_doc = self._parser.parse(scanner)

            if not gherkin_doc or "feature" not in gherkin_doc:
                logger.warning("No feature found in %s", file_path)
                return None

            return self._convert_feature(gherkin_doc["feature"], file_path)
        except Exception as exc:
            logger.error("Failed to parse %s: %s", file_path, exc)
            return None

    def parse_directory(self, directory: Path) -> GherkinFeatureCollection:
        """Parse all .feature files in a directory."""
        features = []
        for feature_file in sorted(directory.glob("*.feature")):
            feature = self.parse_file(feature_file)
            if feature:
                features.append(feature)
                logger.debug("Parsed feature: %s", feature.name)

        return GherkinFeatureCollection(features=features)

    def _convert_feature(
        self, feature_data: dict, file_path: Path
    ) -> GherkinFeature:
        """Convert gherkin-official AST to our GherkinFeature model."""
        name = feature_data.get("name", "")
        description = feature_data.get("description", "").strip()

        # Parse background
        background = None
        scenarios = []

        for child in feature_data.get("children", []):
            if "background" in child:
                background = self._convert_steps(
                    child["background"].get("steps", [])
                )
            elif "scenario" in child:
                scenarios.append(self._convert_scenario(child["scenario"]))

        return GherkinFeature(
            name=name,
            description=description,
            file_path=file_path,
            background=background,
            scenarios=scenarios,
        )

    def _convert_scenario(self, scenario_data: dict) -> GherkinScenario:
        """Convert a scenario from gherkin AST to GherkinScenario model."""
        name = scenario_data.get("name", "")

        # Determine if it's an outline
        keyword = scenario_data.get("keyword", "").strip()
        scenario_type = "outline" if "Outline" in keyword else "scenario"

        # Extract tags
        tags = [
            tag["name"].lstrip("@") for tag in scenario_data.get("tags", [])
        ]

        # Parse steps
        steps = self._convert_steps(scenario_data.get("steps", []))

        # Separate steps by type
        given_steps = [s for s in steps if s.step_type == GherkinStepType.GIVEN]
        when_steps = [s for s in steps if s.step_type == GherkinStepType.WHEN]
        then_steps = [s for s in steps if s.step_type == GherkinStepType.THEN]

        # Parse examples (for Scenario Outline)
        examples = None
        if "examples" in scenario_data and scenario_data["examples"]:
            examples = self._convert_examples(scenario_data["examples"])

        return GherkinScenario(
            name=name,
            type=scenario_type,
            tags=tags if tags else None,
            given_steps=given_steps,
            when_steps=when_steps,
            then_steps=then_steps,
            examples=examples,
        )

    def _convert_steps(self, steps_data: list[dict]) -> list[GherkinStep]:
        """Convert step AST nodes to GherkinStep models."""
        steps = []
        current_type = GherkinStepType.GIVEN  # Default

        for step_data in steps_data:
            keyword = step_data.get("keyword", "").strip()
            text = step_data.get("text", "").strip()
            text = re.sub(r"\s*\|\s*$", "", text)

            # Determine step type - "And" and "*" inherit from previous
            if keyword in ("Given", "given"):
                current_type = GherkinStepType.GIVEN
            elif keyword in ("When", "when"):
                current_type = GherkinStepType.WHEN
            elif keyword in ("Then", "then"):
                current_type = GherkinStepType.THEN
            # "And", "But", "*" keep the current_type

            # Parse data table if present
            data_table = None
            if "dataTable" in step_data:
                data_table = self._convert_data_table(step_data["dataTable"])

            steps.append(
                GherkinStep(
                    text=text,
                    step_type=current_type,
                    data_table=data_table,
                )
            )

        return steps

    def _convert_data_table(self, table_data: dict) -> DataTable:
        """Convert a data table from gherkin AST."""
        rows = table_data.get("rows", [])
        if not rows:
            return DataTable()

        # First row is headers
        headers = [cell.get("value", "") for cell in rows[0].get("cells", [])]

        # Remaining rows are data
        data_rows = []
        for row in rows[1:]:
            data_rows.append(
                [cell.get("value", "") for cell in row.get("cells", [])]
            )

        return DataTable(headers=headers, rows=data_rows)

    def _convert_examples(
        self, examples_data: list[dict]
    ) -> Optional[list[list[str]]]:
        """Convert examples from Scenario Outline."""
        if not examples_data:
            return None

        result = []
        for example in examples_data:
            table_header = example.get("tableHeader", {})
            table_body = example.get("tableBody", [])

            # Add header row
            if table_header:
                header_row = [
                    cell.get("value", "")
                    for cell in table_header.get("cells", [])
                ]
                result.append(header_row)

            # Add data rows
            for row in table_body:
                data_row = [
                    cell.get("value", "") for cell in row.get("cells", [])
                ]
                result.append(data_row)

        return result if result else None


class StepNormalizer:
    """Normalizes step text to canonical forms."""

    def __init__(
        self,
        rules: Optional[list[tuple[str, str]]] = None,
        table_rules: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        self._rules = rules or NORMALIZATION_RULES
        self._table_rules = table_rules or TABLE_HEADER_RULES
        self._compiled_rules = [(re.compile(p), r) for p, r in self._rules]
        self._compiled_table_rules = [
            (re.compile(p), r) for p, r in self._table_rules
        ]

    def normalize_text(self, text: str) -> str:
        """Apply normalization rules to step text."""
        result = text
        for pattern, replacement in self._compiled_rules:
            result = pattern.sub(replacement, result)
        return result

    def normalize_table_header(self, header: str) -> str:
        """Normalize data table header text."""
        result = header
        for pattern, replacement in self._compiled_table_rules:
            result = pattern.sub(replacement, result)
        return result

    def normalize_step(self, step: GherkinStep) -> None:
        """Normalize a single step (mutates in place)."""
        # Normalize step text
        step.text = self.normalize_text(step.text)

        # Normalize data table headers if present
        if step.data_table and step.data_table.headers:
            step.data_table.headers = [
                self.normalize_table_header(h) for h in step.data_table.headers
            ]


class GherkinFormatter:
    """Main class for parsing, normalizing, and writing Gherkin feature files."""

    def __init__(
        self,
        normalizer: Optional[StepNormalizer] = None,
        parser: Optional[GherkinParser] = None,
    ) -> None:
        self._normalizer = normalizer or StepNormalizer()
        self._parser = parser or GherkinParser()

    def parse_feature_files(self, directory: Path) -> GherkinFeatureCollection:
        """Parse all .feature files in a directory into a collection."""
        logger.info("Parsing feature files from %s", directory)
        collection = self._parser.parse_directory(directory)
        logger.info("Parsed %d features", len(collection.features))
        return collection

    def normalize_all_steps(self, collection: GherkinFeatureCollection) -> int:
        """Normalize all steps in the collection. Returns count of steps normalized."""
        count = 0
        for feature in collection.features:
            # Normalize background steps
            if feature.background:
                for step in feature.background:
                    original = step.text
                    self._normalizer.normalize_step(step)
                    if step.text != original:
                        count += 1
                        logger.debug(
                            "Normalized: '%s' -> '%s'", original, step.text
                        )

            # Normalize scenario steps
            for scenario in feature.scenarios:
                for step in scenario.get_all_steps():
                    original = step.text
                    self._normalizer.normalize_step(step)
                    if step.text != original:
                        count += 1
                        logger.debug(
                            "Normalized: '%s' -> '%s'", original, step.text
                        )

        logger.info("Normalized %d steps", count)
        return count

    def write_feature_files(
        self, collection: GherkinFeatureCollection, output_dir: Optional[Path] = None
    ) -> None:
        """Write normalized feature files back to disk."""
        for feature in collection.features:
            if feature.file_path:
                logger.debug("Writing feature to %s", feature.file_path)
                feature.write_to_file()
            elif output_dir:
                # Generate filename from feature name
                safe_name = re.sub(
                    r"[^a-z0-9]+", "_", feature.name.lower()
                ).strip("_")
                file_path = output_dir / f"{safe_name}.feature"
                logger.debug("Writing feature to %s", file_path)
                feature.write_to_file(str(file_path))
            else:
                logger.warning(
                    "No file path for feature '%s', skipping write", feature.name
                )

        logger.info("Wrote %d feature files", len(collection.features))

    def format_directory(self, directory: Path) -> GherkinFeatureCollection:
        """
        Full pipeline: parse, normalize, and write feature files.
        
        This is the main entry point for the formatting stage.
        Returns the normalized GherkinFeatureCollection for use in subsequent stages.
        """
        # Parse all feature files
        collection = self.parse_feature_files(directory)

        if not collection.features:
            logger.warning("No feature files found in %s", directory)
            return collection

        # Get unique steps before normalization
        steps_before = collection.get_unique_step_texts()

        # Normalize all steps
        normalized_count = self.normalize_all_steps(collection)

        # Get unique steps after normalization
        steps_after = collection.get_unique_step_texts()

        logger.info(
            "Normalization reduced unique steps from %d to %d (normalized %d step instances)",
            len(steps_before),
            len(steps_after),
            normalized_count,
        )

        # Write normalized files back
        self.write_feature_files(collection)

        return collection
