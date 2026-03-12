"""Pydantic models for the probe report.

A ProbeReport aggregates test execution results, MCP compliance validation,
and raw traffic recordings into a single serialisable structure that the
pilot pushes to the mcp-probe-service after each run.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Violation(BaseModel):
    exchange_index: int = Field(description="Zero-based index of the exchange within the scenario.")
    method: str = Field(description="JSON-RPC method that was called.")
    rule: str = Field(description="Short identifier for the violated rule.")
    message: str = Field(description="Human-readable description of the violation.")
    path: str = Field(default="", description="Dot-separated path where the violation occurred.")
    severity: str = Field(default="error", description="'error' for MUST violations, 'warning' for SHOULD.")


class Exchange(BaseModel):
    method: str
    type: str = Field(description="'request_response', 'notification', or 'server_notification'.")
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None
    message: Optional[dict[str, Any]] = Field(
        default=None, description="Notification payload (when type is not request_response).",
    )


class ScenarioComplianceDetail(BaseModel):
    mcp_compliant: bool
    total_exchanges: int = 0
    violations: list[Violation] = Field(default_factory=list)


class StepResult(BaseModel):
    name: str
    status: str = Field(description="passed, failed, skipped, undefined, or errored.")
    error_message: Optional[str] = None


class ScenarioReport(BaseModel):
    scenario_name: str
    status: str = Field(description="passed, failed, skipped, or errored.")
    steps: list[StepResult] = Field(default_factory=list)
    compliance: ScenarioComplianceDetail
    exchanges: list[Exchange] = Field(default_factory=list)


class FeatureReport(BaseModel):
    feature_name: str
    summary_test_passed: bool
    mcp_compliant: bool
    duration: float = Field(default=0.0, description="Total feature duration in seconds.")
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    scenarios: list[ScenarioReport] = Field(default_factory=list)


class ProbeReport(BaseModel):
    project_code: str
    timestamp: datetime
    summary_test_passed: bool
    mcp_compliant: bool
    code_coverage: Optional[float] = Field(
        default=None, description="Code coverage percentage (not yet implemented).",
    )
    spec_version: str = "2025-11-25"
    total_features: int = 0
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    feature_reports: list[FeatureReport] = Field(default_factory=list)
