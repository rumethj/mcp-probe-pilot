"""Integration tests: ComplianceValidator -> ReportBuilder.

Verifies that compliance results merge correctly with behave test
results into a ProbeReport.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_probe_pilot.compliance_engine.models import (
    ComplianceReport,
    ExchangeComplianceResult,
    ExchangeViolation,
    ScenarioComplianceResult,
)
from mcp_probe_pilot.compliance_engine.validator import ComplianceValidator
from mcp_probe_pilot.core.models.report import ProbeReport
from mcp_probe_pilot.report.report_builder import (
    RESULTS_FILENAME,
    TRAFFIC_FILENAME,
    ReportHandler,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _write_behave_results(features_dir: Path, features: list[dict]) -> None:
    (features_dir / RESULTS_FILENAME).write_text(json.dumps(features))


def _write_traffic(features_dir: Path, scenarios: list[dict]) -> None:
    (features_dir / TRAFFIC_FILENAME).write_text(json.dumps({"scenarios": scenarios}))


PASSING_BEHAVE = [{
    "name": "Test Feature",
    "elements": [{
        "type": "scenario",
        "name": "Passing Scenario",
        "steps": [
            {"name": "given", "result": {"status": "passed", "duration": 0.1}},
            {"name": "when", "result": {"status": "passed", "duration": 0.2}},
            {"name": "then", "result": {"status": "passed", "duration": 0.1}},
        ],
    }],
}]


# ------------------------------------------------------------------
# Violations merged into ProbeReport
# ------------------------------------------------------------------


class TestViolationsMergedIntoReport:
    def test_violations_reflected_in_per_scenario_compliance(
        self, tmp_path: Path
    ) -> None:
        """A ComplianceReport with violations is correctly merged with
        Behave test results into a ProbeReport where per-scenario compliance
        details reflect the violations."""

        _write_behave_results(tmp_path, PASSING_BEHAVE)
        _write_traffic(tmp_path, [{
            "feature_name": "Test Feature",
            "scenario_name": "Passing Scenario",
            "exchanges": [
                {
                    "type": "request_response",
                    "method": "tools/call",
                    "request": {"jsonrpc": "2.0", "id": 1},
                    "response": {"id": 1, "result": {"content": [{"type": "text", "text": "ok"}]}},
                },
            ],
        }])

        traffic_path = tmp_path / TRAFFIC_FILENAME
        compliance_validator = ComplianceValidator()
        compliance_report = compliance_validator.validate_file(traffic_path)

        assert not compliance_report.passed
        assert compliance_report.total_errors > 0

        handler = ReportHandler(
            project_code="test",
            features_dir=tmp_path,
            service_url="http://localhost:8080",
        )
        report = handler.build_report(compliance_report)

        assert isinstance(report, ProbeReport)

        scenario = report.feature_reports[0].scenarios[0]
        assert not scenario.compliance.mcp_compliant
        assert len(scenario.compliance.violations) > 0

        violation_rules = {v.rule for v in scenario.compliance.violations}
        assert "jsonrpc-version" in violation_rules

        assert not report.feature_reports[0].mcp_compliant
        assert not report.mcp_compliant


# ------------------------------------------------------------------
# Fully compliant run
# ------------------------------------------------------------------


class TestFullyCompliantRun:
    def test_compliant_run_produces_passing_report(
        self, tmp_path: Path
    ) -> None:
        """A fully compliant run produces a ProbeReport with
        mcp_compliant = True and summary_test_passed = True."""

        _write_behave_results(tmp_path, PASSING_BEHAVE)
        _write_traffic(tmp_path, [{
            "feature_name": "Test Feature",
            "scenario_name": "Passing Scenario",
            "exchanges": [
                {
                    "type": "request_response",
                    "method": "tools/call",
                    "request": {"jsonrpc": "2.0", "id": 1},
                    "response": {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"content": [{"type": "text", "text": "ok"}]},
                    },
                },
            ],
        }])

        traffic_path = tmp_path / TRAFFIC_FILENAME
        compliance_validator = ComplianceValidator()
        compliance_report = compliance_validator.validate_file(traffic_path)

        assert compliance_report.passed

        handler = ReportHandler(
            project_code="test",
            features_dir=tmp_path,
            service_url="http://localhost:8080",
        )
        report = handler.build_report(compliance_report)

        assert report.summary_test_passed is True
        assert report.mcp_compliant is True
        assert report.passed_scenarios == 1
        assert report.failed_scenarios == 0
