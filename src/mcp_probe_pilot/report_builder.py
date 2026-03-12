"""Build a ProbeReport from test execution artefacts and push it to the service.

Correlates three data sources by (feature_name, scenario_name):
  1. test-results.json  -- behave JSON output (step statuses, durations)
  2. mcp-traffic.json   -- recorded MCP request/response exchanges
  3. ComplianceReport   -- per-scenario compliance validation results
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_probe_pilot.compliance_engine.models import (
    ComplianceReport,
    ScenarioComplianceResult,
)
from mcp_probe_pilot.core.models.report import (
    Exchange,
    FeatureReport,
    ProbeReport,
    ScenarioComplianceDetail,
    ScenarioReport,
    StepResult,
    Violation,
)
from mcp_probe_pilot.core.service_client import MCPProbeServiceClient, ServiceClientError

logger = logging.getLogger(__name__)

RESULTS_FILENAME = "test-results.json"
TRAFFIC_FILENAME = "mcp-traffic.json"


class ReportBuildError(Exception):
    """Raised when the report cannot be assembled."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_scenario_status(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        status = step.get("result", {}).get("status", "")
        if status in ("failed", "error"):
            return "failed"
        if status == "undefined":
            return "errored"
    if all(
        step.get("result", {}).get("status") == "skipped" for step in steps
    ):
        return "skipped"
    return "passed"


def _build_step_results(steps: list[dict[str, Any]]) -> list[StepResult]:
    results: list[StepResult] = []
    for step in steps:
        result_block = step.get("result", {})
        status = result_block.get("status", "unknown")
        error_msg: str | None = None
        if status in ("failed", "error"):
            error_msg = result_block.get("error_message") or None
        results.append(StepResult(
            name=step.get("name", ""),
            status=status,
            error_message=error_msg,
        ))
    return results


def _feature_duration(feature_dict: dict[str, Any]) -> float:
    total = 0.0
    for element in feature_dict.get("elements", []):
        for step in element.get("steps", []):
            total += step.get("result", {}).get("duration", 0.0)
    return round(total, 4)


def _build_compliance_detail(
    compliance_result: ScenarioComplianceResult | None,
) -> ScenarioComplianceDetail:
    if compliance_result is None:
        return ScenarioComplianceDetail(mcp_compliant=True, total_exchanges=0)
    return ScenarioComplianceDetail(
        mcp_compliant=compliance_result.passed,
        total_exchanges=compliance_result.total_exchanges,
        violations=[
            Violation(
                exchange_index=v.exchange_index,
                method=v.method,
                rule=v.rule,
                message=v.message,
                path=v.path,
                severity=v.severity,
            )
            for v in compliance_result.violations
        ],
    )


def _build_exchanges(raw_exchanges: list[dict[str, Any]]) -> list[Exchange]:
    return [
        Exchange(
            method=ex.get("method", ""),
            type=ex.get("type", ""),
            request=ex.get("request"),
            response=ex.get("response"),
            message=ex.get("message"),
        )
        for ex in raw_exchanges
    ]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_report(
    project_code: str,
    features_dir: Path,
    compliance_report: ComplianceReport,
) -> ProbeReport:
    """Assemble a ProbeReport from on-disk artefacts and the compliance report."""

    results_path = features_dir / RESULTS_FILENAME
    traffic_path = features_dir / TRAFFIC_FILENAME

    # -- Load behave JSON results ------------------------------------------
    behave_features: list[dict[str, Any]] = []
    if results_path.exists():
        try:
            behave_features = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load %s: %s", results_path, exc)
    else:
        logger.warning("Test results file not found: %s", results_path)

    # -- Load traffic JSON -------------------------------------------------
    traffic_scenarios: list[dict[str, Any]] = []
    if traffic_path.exists():
        try:
            traffic_data = json.loads(traffic_path.read_text(encoding="utf-8"))
            traffic_scenarios = traffic_data.get("scenarios", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load %s: %s", traffic_path, exc)
    else:
        logger.warning("Traffic file not found: %s", traffic_path)

    # -- Index compliance results by (feature, scenario) -------------------
    compliance_map: dict[tuple[str, str], ScenarioComplianceResult] = {}
    for sc in compliance_report.scenarios:
        compliance_map[(sc.feature_name, sc.scenario_name)] = sc

    # -- Index traffic exchanges by (feature, scenario) --------------------
    traffic_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ts in traffic_scenarios:
        key = (ts.get("feature_name", ""), ts.get("scenario_name", ""))
        traffic_map[key] = ts.get("exchanges", [])

    # -- Build feature reports ---------------------------------------------
    feature_reports: list[FeatureReport] = []
    total_scenarios = 0
    total_passed = 0
    total_failed = 0

    for feat in behave_features:
        feature_name = feat.get("name", "")
        duration = _feature_duration(feat)

        scenario_reports: list[ScenarioReport] = []
        feat_passed = 0
        feat_failed = 0

        for element in feat.get("elements", []):
            if element.get("type") != "scenario":
                continue

            scenario_name = element.get("name", "")
            steps = element.get("steps", [])
            status = _derive_scenario_status(steps)
            step_results = _build_step_results(steps)

            key = (feature_name, scenario_name)
            compliance_detail = _build_compliance_detail(compliance_map.get(key))
            exchanges = _build_exchanges(traffic_map.get(key, []))

            scenario_reports.append(ScenarioReport(
                scenario_name=scenario_name,
                status=status,
                steps=step_results,
                compliance=compliance_detail,
                exchanges=exchanges,
            ))

            if status == "passed":
                feat_passed += 1
            else:
                feat_failed += 1

        feat_total = feat_passed + feat_failed
        all_compliant = all(s.compliance.mcp_compliant for s in scenario_reports)

        feature_reports.append(FeatureReport(
            feature_name=feature_name,
            summary_test_passed=(feat_failed == 0 and feat_total > 0),
            mcp_compliant=all_compliant,
            duration=duration,
            total_scenarios=feat_total,
            passed_scenarios=feat_passed,
            failed_scenarios=feat_failed,
            scenarios=scenario_reports,
        ))

        total_scenarios += feat_total
        total_passed += feat_passed
        total_failed += feat_failed

    all_tests_passed = total_failed == 0 and total_scenarios > 0
    all_compliant = all(fr.mcp_compliant for fr in feature_reports) if feature_reports else True

    return ProbeReport(
        project_code=project_code,
        timestamp=datetime.now(timezone.utc),
        summary_test_passed=all_tests_passed,
        mcp_compliant=all_compliant,
        code_coverage=None,
        spec_version=compliance_report.spec_version,
        total_features=len(feature_reports),
        total_scenarios=total_scenarios,
        passed_scenarios=total_passed,
        failed_scenarios=total_failed,
        feature_reports=feature_reports,
    )


async def build_and_push_report(
    project_code: str,
    features_dir: Path,
    compliance_report: ComplianceReport,
    service_url: str,
) -> ProbeReport:
    """Build a ProbeReport and POST it to the mcp-probe-service.

    Returns the built report regardless of whether the push succeeds
    (failures are logged as warnings, not raised).
    """
    report = build_report(project_code, features_dir, compliance_report)

    try:
        async with MCPProbeServiceClient(base_url=service_url) as client:
            response = await client.client.post(
                f"/api/reports/{project_code}",
                content=report.model_dump_json(),
                headers={"Content-Type": "application/json"},
                timeout=60.0,
            )
            if response.status_code >= 400:
                logger.warning(
                    "Failed to push report to service (HTTP %d): %s",
                    response.status_code,
                    response.text,
                )
            else:
                data = response.json()
                logger.info(
                    "Report pushed to service: report_id=%s",
                    data.get("report_id", "?"),
                )
    except ServiceClientError as exc:
        logger.warning("Could not push report to service: %s", exc)
    except Exception as exc:
        logger.warning("Unexpected error pushing report to service: %s", exc)

    return report
