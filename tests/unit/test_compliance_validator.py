"""Unit tests for the ComplianceValidator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_probe_pilot.compliance_engine.models import (
    ComplianceReport,
    ExchangeViolation,
    ScenarioComplianceResult,
)
from mcp_probe_pilot.compliance_engine.validator import (
    ComplianceValidator,
    _applicable_rules,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_traffic(scenarios: list[dict]) -> dict:
    return {"scenarios": scenarios}


def _rr(method: str, request: dict, response: dict) -> dict:
    return {
        "type": "request_response",
        "method": method,
        "request": request,
        "response": response,
    }


def _valid_envelope(req_id: int = 1) -> tuple[dict, dict]:
    return (
        {"jsonrpc": "2.0", "id": req_id, "method": "test"},
        {"jsonrpc": "2.0", "id": req_id, "result": {}},
    )


# ------------------------------------------------------------------
# validate_traffic / validate_file
# ------------------------------------------------------------------


class TestValidateTraffic:
    def test_empty_traffic(self) -> None:
        validator = ComplianceValidator()
        report = validator.validate_traffic({"scenarios": []})

        assert isinstance(report, ComplianceReport)
        assert report.total_exchanges == 0
        assert report.passed

    def test_single_valid_initialize(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "init",
            "scenario_name": "handshake",
            "exchanges": [_rr("initialize",
                {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                {"jsonrpc": "2.0", "id": 1, "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "test", "version": "1.0"},
                }},
            )],
        }])
        report = validator.validate_traffic(data)

        assert report.passed
        assert report.total_exchanges == 1
        assert report.total_violations == 0

    def test_missing_jsonrpc_field(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"id": 1, "result": {"tools": []}},
            )],
        }])
        report = validator.validate_traffic(data)

        assert not report.passed
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "jsonrpc-version" in rules

    def test_missing_response_flagged(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [{
                "type": "request_response",
                "method": "tools/list",
                "request": {"jsonrpc": "2.0", "id": 1},
                "response": None,
            }],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "missing-response" in rules

    def test_result_xor_error(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {"code": -1, "message": "oops"}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "result-xor-error" in rules

    def test_id_mismatch(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 99, "result": {"tools": []}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "response-id-match" in rules


class TestValidateFile:
    def test_missing_file(self, tmp_path: Path) -> None:
        validator = ComplianceValidator()
        report = validator.validate_file(tmp_path / "nope.json")

        assert isinstance(report, ComplianceReport)
        assert report.total_exchanges == 0

    def test_reads_real_file(self, tmp_path: Path) -> None:
        traffic = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
            )],
        }])
        p = tmp_path / "traffic.json"
        p.write_text(json.dumps(traffic))

        report = ComplianceValidator().validate_file(p)
        assert report.passed
        assert report.total_exchanges == 1


# ------------------------------------------------------------------
# Error object validation
# ------------------------------------------------------------------


class TestErrorObjectValidation:
    def test_error_missing_code(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "error": {"message": "bad"}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "error-code-required" in rules

    def test_error_code_not_int(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "error": {"code": "abc", "message": "bad"}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "error-code-integer" in rules

    def test_error_missing_message(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "error-message-required" in rules

    def test_valid_error_passes(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid"}},
            )],
        }])
        report = validator.validate_traffic(data)
        error_violations = [
            v for v in report.scenarios[0].violations
            if v.rule.startswith("error-")
        ]
        assert error_violations == []


# ------------------------------------------------------------------
# Notification validation
# ------------------------------------------------------------------


class TestNotificationValidation:
    def test_valid_notification(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [{
                "type": "notification",
                "method": "notifications/initialized",
                "message": {"jsonrpc": "2.0", "method": "notifications/initialized"},
            }],
        }])
        report = validator.validate_traffic(data)
        assert report.scenarios[0].violations == []

    def test_notification_with_id_flagged(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [{
                "type": "notification",
                "method": "test",
                "message": {"jsonrpc": "2.0", "method": "test", "id": 1},
            }],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "notification-no-id" in rules

    def test_notification_missing_jsonrpc(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f",
            "scenario_name": "s",
            "exchanges": [{
                "type": "notification",
                "method": "test",
                "message": {"method": "test"},
            }],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "jsonrpc-version" in rules


# ------------------------------------------------------------------
# Method-specific validators
# ------------------------------------------------------------------


class TestToolsListValidation:
    def test_missing_tools_array(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "tools-list-tools-required" in rules

    def test_tool_missing_name(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {
                    "tools": [{"inputSchema": {}}],
                }},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "tool-name-required" in rules

    def test_tool_missing_input_schema(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {
                    "tools": [{"name": "foo"}],
                }},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "tool-inputSchema-required" in rules


class TestToolsCallValidation:
    def test_missing_content(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = [v.rule for v in report.scenarios[0].violations]
        assert "tools-call-content-required" in rules

    def test_valid_text_content(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/call",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {
                    "content": [{"type": "text", "text": "hello"}],
                }},
            )],
        }])
        report = validator.validate_traffic(data)
        method_violations = [
            v for v in report.scenarios[0].violations
            if v.rule.startswith("tools-call") or v.rule.startswith("content-") or v.rule.startswith("text-")
        ]
        assert method_violations == []


class TestInitializeValidation:
    def test_missing_required_fields(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("initialize",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {}},
            )],
        }])
        report = validator.validate_traffic(data)
        rules = {v.rule for v in report.scenarios[0].violations}
        assert "initialize-protocolVersion-required" in rules
        assert "initialize-capabilities-required" in rules
        assert "initialize-serverInfo-required" in rules


# ------------------------------------------------------------------
# Applicable rules helper
# ------------------------------------------------------------------


class TestApplicableRules:
    def test_notification_rules(self) -> None:
        rules = _applicable_rules("notification", "", False)
        assert "jsonrpc-version" in rules
        assert "notification-no-id" in rules
        assert "response-id-present" not in rules

    def test_request_response_with_error(self) -> None:
        rules = _applicable_rules("request_response", "tools/list", True)
        assert "error-code-required" in rules
        assert "tools-list-tools-required" not in rules

    def test_request_response_without_error(self) -> None:
        rules = _applicable_rules("request_response", "tools/list", False)
        assert "tools-list-tools-required" in rules
        assert "error-code-required" not in rules


# ------------------------------------------------------------------
# Exchange compliance results (passed rules tracking)
# ------------------------------------------------------------------


class TestExchangeComplianceResults:
    def test_passed_rules_tracked(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
            )],
        }])
        report = validator.validate_traffic(data)
        er = report.scenarios[0].exchange_results[0]
        assert len(er.passed_rules) > 0
        assert "jsonrpc-version" in er.passed_rules

    def test_violated_rules_not_in_passed(self) -> None:
        validator = ComplianceValidator()
        data = _make_traffic([{
            "feature_name": "f", "scenario_name": "s",
            "exchanges": [_rr("tools/list",
                {"jsonrpc": "2.0", "id": 1},
                {"id": 1, "result": {"tools": []}},
            )],
        }])
        report = validator.validate_traffic(data)
        er = report.scenarios[0].exchange_results[0]
        assert "jsonrpc-version" not in er.passed_rules
        violated = {v.rule for v in er.violations}
        assert "jsonrpc-version" in violated
