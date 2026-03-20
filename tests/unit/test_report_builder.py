"""Unit tests for the ReportHandler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_probe_pilot.compliance_engine.models import (
    ComplianceReport,
    ExchangeComplianceResult,
    ExchangeViolation,
    ScenarioComplianceResult,
)
from mcp_probe_pilot.core.models.report import ProbeReport
from mcp_probe_pilot.report.report_builder import (
    RESULTS_FILENAME,
    TRAFFIC_FILENAME,
    ReportHandler,
    _build_compliance_detail,
    _build_exchanges,
    _build_step_results,
    _derive_scenario_status,
    _feature_duration,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_handler(tmp_path: Path) -> ReportHandler:
    return ReportHandler(
        project_code="test-project",
        features_dir=tmp_path,
        service_url="http://localhost:8080",
    )


def _write_behave_results(tmp_path: Path, features: list[dict]) -> None:
    (tmp_path / RESULTS_FILENAME).write_text(json.dumps(features))


def _write_traffic(tmp_path: Path, scenarios: list[dict]) -> None:
    (tmp_path / TRAFFIC_FILENAME).write_text(json.dumps({"scenarios": scenarios}))


PASSING_FEATURE = [{
    "name": "Test Feature",
    "elements": [{
        "type": "scenario",
        "name": "Passing Scenario",
        "steps": [
            {"name": "step 1", "result": {"status": "passed", "duration": 0.1}},
            {"name": "step 2", "result": {"status": "passed", "duration": 0.2}},
        ],
    }],
}]

FAILING_FEATURE = [{
    "name": "Test Feature",
    "elements": [{
        "type": "scenario",
        "name": "Failing Scenario",
        "steps": [
            {"name": "step 1", "result": {"status": "passed", "duration": 0.1}},
            {"name": "step 2", "result": {"status": "failed", "duration": 0.2, "error_message": "boom"}},
        ],
    }],
}]


# ------------------------------------------------------------------
# _derive_scenario_status
# ------------------------------------------------------------------


class TestDeriveScenarioStatus:
    def test_all_passed(self) -> None:
        steps = [
            {"result": {"status": "passed"}},
            {"result": {"status": "passed"}},
        ]
        assert _derive_scenario_status(steps) == "passed"

    def test_one_failed(self) -> None:
        steps = [
            {"result": {"status": "passed"}},
            {"result": {"status": "failed"}},
        ]
        assert _derive_scenario_status(steps) == "failed"

    def test_undefined(self) -> None:
        steps = [{"result": {"status": "undefined"}}]
        assert _derive_scenario_status(steps) == "errored"

    def test_all_skipped(self) -> None:
        steps = [
            {"result": {"status": "skipped"}},
            {"result": {"status": "skipped"}},
        ]
        assert _derive_scenario_status(steps) == "skipped"

    def test_empty_steps(self) -> None:
        assert _derive_scenario_status([]) == "skipped"


# ------------------------------------------------------------------
# _build_step_results
# ------------------------------------------------------------------


class TestBuildStepResults:
    def test_builds_results(self) -> None:
        steps = [
            {"name": "step A", "result": {"status": "passed"}},
            {"name": "step B", "result": {"status": "failed", "error_message": "oops"}},
        ]
        results = _build_step_results(steps)
        assert len(results) == 2
        assert results[0].name == "step A"
        assert results[0].status == "passed"
        assert results[1].error_message == "oops"

    def test_error_message_list(self) -> None:
        steps = [{"name": "s", "result": {"status": "failed", "error_message": ["line1", "line2"]}}]
        results = _build_step_results(steps)
        assert "line1" in results[0].error_message
        assert "line2" in results[0].error_message

    def test_data_table(self) -> None:
        steps = [{
            "name": "s",
            "result": {"status": "passed"},
            "table": {"headings": ["a", "b"], "rows": [["1", "2"]]},
        }]
        results = _build_step_results(steps)
        assert results[0].data_table is not None
        assert results[0].data_table.headings == ["a", "b"]


# ------------------------------------------------------------------
# _feature_duration
# ------------------------------------------------------------------


class TestFeatureDuration:
    def test_sums_step_durations(self) -> None:
        feature = {
            "elements": [{
                "steps": [
                    {"result": {"duration": 0.1}},
                    {"result": {"duration": 0.2}},
                ],
            }],
        }
        assert _feature_duration(feature) == pytest.approx(0.3, abs=0.01)


# ------------------------------------------------------------------
# _build_compliance_detail
# ------------------------------------------------------------------


class TestBuildComplianceDetail:
    def test_none_returns_compliant(self) -> None:
        detail = _build_compliance_detail(None)
        assert detail.mcp_compliant is True
        assert detail.total_exchanges == 0

    def test_with_violations(self) -> None:
        result = ScenarioComplianceResult(
            feature_name="f",
            scenario_name="s",
            total_exchanges=1,
            violations=[
                ExchangeViolation(
                    exchange_index=0,
                    method="tools/call",
                    rule="jsonrpc-version",
                    message="Missing jsonrpc",
                ),
            ],
        )
        detail = _build_compliance_detail(result)
        assert detail.mcp_compliant is False
        assert len(detail.violations) == 1


# ------------------------------------------------------------------
# build_report
# ------------------------------------------------------------------


class TestBuildReport:
    def test_passing_report(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, PASSING_FEATURE)
        _write_traffic(tmp_path, [])
        handler = _make_handler(tmp_path)

        report = handler.build_report(ComplianceReport())

        assert isinstance(report, ProbeReport)
        assert report.summary_test_passed
        assert report.mcp_compliant
        assert report.total_scenarios == 1
        assert report.passed_scenarios == 1

    def test_failing_report(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, FAILING_FEATURE)
        _write_traffic(tmp_path, [])
        handler = _make_handler(tmp_path)

        report = handler.build_report(ComplianceReport())

        assert not report.summary_test_passed
        assert report.failed_scenarios == 1

    def test_missing_results_file(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        report = handler.build_report(ComplianceReport())

        assert report.total_scenarios == 0
        assert report.total_features == 0

    def test_compliance_violations_merged(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, PASSING_FEATURE)
        _write_traffic(tmp_path, [])
        compliance = ComplianceReport(scenarios=[
            ScenarioComplianceResult(
                feature_name="Test Feature",
                scenario_name="Passing Scenario",
                total_exchanges=1,
                violations=[
                    ExchangeViolation(
                        exchange_index=0,
                        method="tools/call",
                        rule="jsonrpc-version",
                        message="Missing",
                    ),
                ],
            ),
        ])
        handler = _make_handler(tmp_path)
        report = handler.build_report(compliance)

        scenario_report = report.feature_reports[0].scenarios[0]
        assert not scenario_report.compliance.mcp_compliant
        assert len(scenario_report.compliance.violations) == 1

    def test_project_code_propagated(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, PASSING_FEATURE)
        handler = _make_handler(tmp_path)
        report = handler.build_report(ComplianceReport())
        assert report.project_code == "test-project"


# ------------------------------------------------------------------
# build_and_push_report
# ------------------------------------------------------------------


class TestBuildAndPushReport:
    @pytest.mark.asyncio
    async def test_push_success(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, PASSING_FEATURE)
        _write_traffic(tmp_path, [])
        handler = _make_handler(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"report_id": "abc-123"}

        with patch(
            "mcp_probe_pilot.report.report_builder.MCPProbeServiceClient"
        ) as MockClient:
            ctx = AsyncMock()
            ctx.client = MagicMock()
            ctx.client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            report, report_id = await handler.build_and_push_report(ComplianceReport())

        assert isinstance(report, ProbeReport)
        assert report_id == "abc-123"

    @pytest.mark.asyncio
    async def test_push_failure_logs_warning(self, tmp_path: Path) -> None:
        _write_behave_results(tmp_path, PASSING_FEATURE)
        _write_traffic(tmp_path, [])
        handler = _make_handler(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch(
            "mcp_probe_pilot.report.report_builder.MCPProbeServiceClient"
        ) as MockClient:
            ctx = AsyncMock()
            ctx.client = MagicMock()
            ctx.client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=ctx)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            report, report_id = await handler.build_and_push_report(ComplianceReport())

        assert isinstance(report, ProbeReport)
        assert report_id is None
