"""Integration tests: Executor -> ComplianceValidator.

Verifies that MCP traffic JSON produced during test execution is
parseable by the ComplianceValidator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_probe_pilot.compliance_engine.models import ComplianceReport
from mcp_probe_pilot.compliance_engine.validator import ComplianceValidator


# ------------------------------------------------------------------
# Valid traffic produces compliant report
# ------------------------------------------------------------------


class TestValidTrafficCompliant:
    def test_valid_traffic_parseable_and_compliant(self, tmp_path: Path) -> None:
        """The MCP traffic JSON produced during test execution is parseable
        by the ComplianceValidator, and valid JSON-RPC exchanges produce a
        compliant ComplianceReport."""

        traffic = {
            "scenarios": [{
                "feature_name": "tool_search tool",
                "scenario_name": "Search with keyword",
                "exchanges": [
                    {
                        "type": "request_response",
                        "method": "initialize",
                        "request": {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                        "response": {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "result": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "serverInfo": {"name": "test", "version": "1.0"},
                            },
                        },
                    },
                    {
                        "type": "notification",
                        "method": "notifications/initialized",
                        "message": {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    },
                    {
                        "type": "request_response",
                        "method": "tools/call",
                        "request": {"jsonrpc": "2.0", "id": 2, "method": "tools/call"},
                        "response": {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "result": {
                                "content": [{"type": "text", "text": "results"}],
                            },
                        },
                    },
                ],
            }],
        }

        traffic_path = tmp_path / "mcp-traffic.json"
        traffic_path.write_text(json.dumps(traffic))

        validator = ComplianceValidator()
        report = validator.validate_file(traffic_path)

        assert isinstance(report, ComplianceReport)
        assert report.passed
        assert report.total_exchanges == 3
        assert report.total_errors == 0


# ------------------------------------------------------------------
# Protocol violations are correctly flagged
# ------------------------------------------------------------------


class TestProtocolViolationsFlagged:
    def test_violations_flagged_with_rule_and_severity(self, tmp_path: Path) -> None:
        """Traffic containing protocol violations (e.g. missing jsonrpc field,
        invalid error codes) is correctly flagged with the right rule and
        severity."""

        traffic = {
            "scenarios": [{
                "feature_name": "tool_search tool",
                "scenario_name": "Broken exchange",
                "exchanges": [
                    {
                        "type": "request_response",
                        "method": "tools/list",
                        "request": {"jsonrpc": "2.0", "id": 1},
                        "response": {
                            "id": 1,
                            "result": {"tools": []},
                        },
                    },
                    {
                        "type": "request_response",
                        "method": "tools/call",
                        "request": {"jsonrpc": "2.0", "id": 2},
                        "response": {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "error": {"code": "not-an-int", "message": "oops"},
                        },
                    },
                    {
                        "type": "notification",
                        "method": "test/notify",
                        "message": {"method": "test/notify", "id": 99},
                    },
                ],
            }],
        }

        traffic_path = tmp_path / "mcp-traffic.json"
        traffic_path.write_text(json.dumps(traffic))

        validator = ComplianceValidator()
        report = validator.validate_file(traffic_path)

        assert not report.passed

        all_violations = report.scenarios[0].violations
        rules = {v.rule for v in all_violations}
        severities = {v.severity for v in all_violations}

        assert "jsonrpc-version" in rules
        assert "error-code-integer" in rules
        assert "notification-no-id" in rules
        assert "error" in severities

        for v in all_violations:
            assert v.rule != ""
            assert v.message != ""
            assert v.method != ""
