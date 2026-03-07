"""
This module contains the models for the Gherkin feature files.

This will be used after Gherkin File generation and used to validate and format the Gherkin files.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GherkinStepType(Enum):
    GIVEN = "Given"
    WHEN = "When"
    THEN = "Then"


class DataTable(BaseModel):
    """Represents a data table attached to a Gherkin step."""

    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)

    def format(self, indent: str = "      ") -> List[str]:
        """Format the data table as Gherkin lines."""
        lines = []
        if self.headers:
            header_str = " | ".join(self.headers)
            lines.append(f"{indent}| {header_str} |")
        for row in self.rows:
            row_str = " | ".join(str(cell) for cell in row)
            lines.append(f"{indent}| {row_str} |")
        return lines


class GherkinStep(BaseModel):
    """Represents a single Gherkin step (Given/When/Then)."""

    text: str
    step_type: GherkinStepType
    data_table: Optional[DataTable] = None

    def format_data_table(self) -> str:
        """Legacy method for backwards compatibility."""
        if not self.data_table:
            return ""
        lines = self.data_table.format()
        return "\n".join(lines)


class GherkinScenario(BaseModel):
    """Represents a Gherkin Scenario."""

    name: str
    tags: Optional[List[str]] = None
    given_steps: List[GherkinStep] = Field(default_factory=list)
    when_steps: List[GherkinStep] = Field(default_factory=list)
    then_steps: List[GherkinStep] = Field(default_factory=list)

    def get_all_steps(self) -> List[GherkinStep]:
        """Utility to sequentially combine steps for file writing."""
        steps = []
        if self.given_steps:
            steps.extend(self.given_steps)
        if self.when_steps:
            steps.extend(self.when_steps)
        if self.then_steps:
            steps.extend(self.then_steps)
        return steps


class GherkinFeature(BaseModel):
    """Represents a complete Gherkin feature file."""

    name: str
    description: str = ""
    file_path: Optional[Path] = None  # Track source file for rewriting
    background: Optional[List[GherkinStep]] = None
    scenarios: List[GherkinScenario] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def get_all_steps(self) -> List[GherkinStep]:
        """Get all steps from background and all scenarios."""
        steps = []
        if self.background:
            steps.extend(self.background)
        for scenario in self.scenarios:
            steps.extend(scenario.get_all_steps())
        return steps

    def _format_step_list(self, steps: List[GherkinStep], indent_spaces: int = 4) -> List[str]:
        """
        Helper method to format steps and automatically inject 'And'
        when steps of the same type are chained sequentially.
        Also handles data tables attached to steps.
        """
        lines = []
        last_step_type = None
        indent = " " * indent_spaces
        table_indent = " " * (indent_spaces + 2)

        for step in steps:
            if step.step_type == last_step_type:
                keyword = "And"
            else:
                keyword = step.step_type.value
                last_step_type = step.step_type

            lines.append(f"{indent}{keyword} {step.text}")

            # Add data table if present
            if step.data_table:
                lines.extend(step.data_table.format(indent=table_indent))

        return lines

    def get_feature_doc_lines(self) -> List[str]:
        """Generate the Gherkin feature file content as lines."""
        lines = []

        # 1. Feature Name & Description
        lines.append(f"Feature: {self.name}")
        if self.description:
            for line in self.description.split("\n"):
                lines.append(f"  {line.strip()}")
        lines.append("")

        # 2. Background
        if self.background:
            lines.append("  Background:")
            lines.extend(self._format_step_list(self.background))
            lines.append("")

        # 3. Scenarios
        for scenario in self.scenarios:
            # Add tags if present
            if scenario.tags:
                tag_line = " ".join(f"@{tag}" if not tag.startswith("@") else tag for tag in scenario.tags)
                lines.append(f"  {tag_line}")

            prefix = "Scenario"
            lines.append(f"  {prefix}: {scenario.name}")

            # Use the auto-chaining helper for scenario steps
            lines.extend(self._format_step_list(scenario.get_all_steps()))

            lines.append("")

        return lines

    def write_to_file(self, file_path: Optional[str] = None) -> None:
        """Write the feature to a file."""
        target_path = file_path or self.file_path
        if not target_path:
            raise ValueError("No file path provided and no file_path set on feature")

        lines = self.get_feature_doc_lines()
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))



class GherkinFeatureCollection(BaseModel):
    """Collection of Gherkin features for batch processing."""

    features: List[GherkinFeature] = Field(default_factory=list)

    def create_feature_files(self, output_dir: str) -> None:
        """Write all features to files in the output directory."""
        os.makedirs(output_dir, exist_ok=True)

        for feature in self.features:
            if feature.file_path:
                # Use existing file path if set
                feature.write_to_file(str(feature.file_path))
            else:
                # Create a safe file name (slugify)
                safe_filename = re.sub(r"[^a-z0-9]+", "_", feature.name.lower()).strip("_")
                feature.write_to_file(os.path.join(output_dir, f"{safe_filename}.feature"))

    def get_all_steps(self) -> List[GherkinStep]:
        """Get all steps from all features."""
        steps = []
        for feature in self.features:
            steps.extend(feature.get_all_steps())
        return steps

    def get_unique_step_texts(self) -> set[str]:
        """Get all unique step texts across all features."""
        return {step.text for step in self.get_all_steps()}
