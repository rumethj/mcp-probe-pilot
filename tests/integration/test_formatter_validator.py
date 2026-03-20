"""Integration tests: GherkinFormatter -> FeatureValidator.

Verifies that formatted feature collections interact correctly with
the canonical step validator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_probe_pilot.core.models.gherkin_feature import (
    GherkinFeature,
    GherkinFeatureCollection,
    GherkinScenario,
    GherkinStep,
    GherkinStepType,
)
from mcp_probe_pilot.generate.gherkin_formatter import GherkinFormatter
from mcp_probe_pilot.validate.validator import FeatureValidator


# ------------------------------------------------------------------
# Canonical steps pass validation
# ------------------------------------------------------------------

CANONICAL_FEATURE = """\
Feature: Canonical steps test
  As an MCP client
  I want valid steps

  Background:
    Given the MCP Client is initialized and connected to the MCP Server: "test-server"

  Scenario: Call a tool
    When the MCP Client calls the tool "search" with parameters
      | parameter | value |
      | query     | test  |
    Then the response should be successful
    And the response should contain "results"

  Scenario: Read a resource
    When the MCP Client reads the resource "notes://all"
    Then the response should be successful

  Scenario: Get a prompt
    When the MCP Client gets the prompt "summarize"
    Then the response should contain prompt messages
"""


class TestCanonicalStepsPassValidation:
    def test_canonical_steps_zero_warnings(self, tmp_path: Path) -> None:
        """A GherkinFeatureCollection containing only canonical steps
        passes validation with zero warnings."""

        (tmp_path / "test.feature").write_text(CANONICAL_FEATURE)

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        validator = FeatureValidator()
        result = validator.validate_collection(collection)

        assert result.rejected == 0, (
            f"Expected 0 rejected steps, got {result.rejected}: "
            f"{[s.original_text for s in result.rejected_steps]}"
        )


# ------------------------------------------------------------------
# Non-canonical steps are flagged
# ------------------------------------------------------------------

HALLUCINATED_FEATURE = """\
Feature: Hallucinated steps test
  As an MCP client
  I want to test

  Scenario: Unknown steps
    When the MCP Client magically teleports to another dimension
    Then the quantum entanglement should resolve
    And the blockchain should validate the transaction
"""


class TestNonCanonicalStepsFlagged:
    def test_hallucinated_steps_flagged(self, tmp_path: Path) -> None:
        """A collection containing non-canonical or hallucinated step
        patterns is flagged by the validator."""

        (tmp_path / "bad.feature").write_text(HALLUCINATED_FEATURE)

        formatter = GherkinFormatter()
        collection = formatter.format_directory(tmp_path)

        validator = FeatureValidator()
        result = validator.validate_collection(collection)

        assert not result.is_valid
        assert result.rejected >= 3
        rejected_texts = {s.original_text for s in result.rejected_steps}
        assert any("teleports" in t for t in rejected_texts)
        assert any("quantum" in t for t in rejected_texts)
