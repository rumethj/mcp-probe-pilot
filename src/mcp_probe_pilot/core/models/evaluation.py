"""Models for test evaluation results."""

from __future__ import annotations

from typing import List, Optional, Set

from pydantic import BaseModel, Field

from mcp_probe_pilot.core.models.gherkin_feature import GherkinStep


class StepVerdict(BaseModel):
    """Classification of a single step across all scenarios."""

    step: GherkinStep
    failure_logs: Set[str] = Field(default_factory=set)
    is_false_negative: Optional[bool] = None


class EvaluationResults(BaseModel):
    """Aggregated evaluation verdicts for a test run."""

    verdicts: List[StepVerdict] = Field(default_factory=list)

    @property
    def true_negatives(self) -> list[StepVerdict]:
        return [
            v for v in self.verdicts
            if len(v.failure_logs) > 0 and v.is_false_negative is False
        ]

    @property
    def false_negatives(self) -> list[StepVerdict]:
        return [
            v for v in self.verdicts
            if len(v.failure_logs) > 0 and v.is_false_negative is True
        ]

    @property
    def unevaluated(self) -> list[StepVerdict]:
        return [
            v for v in self.verdicts
            if len(v.failure_logs) > 0 and v.is_false_negative is None
        ]

    @property
    def succeeded(self) -> list[StepVerdict]:
        return [v for v in self.verdicts if len(v.failure_logs) == 0]
