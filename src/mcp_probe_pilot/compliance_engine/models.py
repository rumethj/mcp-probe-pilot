"""Pydantic models for MCP compliance validation reports."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExchangeViolation(BaseModel):
    """A single schema violation found in one request/response exchange."""

    exchange_index: int = Field(
        description="Zero-based index of the exchange within the scenario.",
    )
    method: str = Field(
        description="JSON-RPC method that was called (e.g. 'initialize', 'tools/list').",
    )
    rule: str = Field(
        description="Short identifier for the rule that was violated.",
    )
    message: str = Field(
        description="Human-readable description of the violation.",
    )
    path: str = Field(
        default="",
        description="Dot-separated path within the response where the violation occurred.",
    )
    severity: str = Field(
        default="error",
        description="'error' for MUST violations, 'warning' for SHOULD violations.",
    )


class ScenarioComplianceResult(BaseModel):
    """Compliance result for a single BDD scenario."""

    feature_name: str
    scenario_name: str
    total_exchanges: int = 0
    violations: list[ExchangeViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(v.severity != "error" for v in self.violations)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


class ComplianceReport(BaseModel):
    """Top-level compliance report across all scenarios in a test run."""

    spec_version: str = Field(
        default="2025-11-25",
        description="MCP specification version validated against.",
    )
    scenarios: list[ScenarioComplianceResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.scenarios)

    @property
    def total_violations(self) -> int:
        return sum(len(s.violations) for s in self.scenarios)

    @property
    def total_errors(self) -> int:
        return sum(s.error_count for s in self.scenarios)

    @property
    def total_warnings(self) -> int:
        return sum(s.warning_count for s in self.scenarios)

    @property
    def total_exchanges(self) -> int:
        return sum(s.total_exchanges for s in self.scenarios)
