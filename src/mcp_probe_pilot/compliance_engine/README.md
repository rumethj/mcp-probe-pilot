# Compliance Engine

Validates captured MCP JSON-RPC traffic against the **MCP 2025-11-25** specification.

## Purpose

After tests execute, the behave environment hooks write every request/response exchange to `mcp-traffic.json`. The compliance engine reads that file and checks each server response for protocol violations, producing a structured `ComplianceReport`.

## Key Concepts

- **Rule Registry** – Rules are organised into sets (`ENVELOPE_RULES`, `ERROR_RULES`, `NOTIFICATION_RULES`, `METHOD_RULES`) so the validator knows exactly which checks apply to a given exchange context. Rules that pass are tracked alongside violations for full auditability.
- **Exchange-level Granularity** – Each request/response pair gets its own `ExchangeComplianceResult` containing both passed rules and violations. This lets the report builder attach compliance detail to individual test scenarios.
- **Severity Levels** – Violations carry a severity of `"error"` (for MUST-level spec requirements) or `"warning"` (for SHOULD-level). Only errors cause a scenario to be marked non-compliant.
- **Method Dispatch** – A `_METHOD_VALIDATORS` dict maps MCP method names (e.g. `"tools/list"`, `"prompts/get"`) to dedicated validation methods, keeping each method's checks isolated and testable.

## Modules

| File | Description |
|------|-------------|
| `models.py` | Pydantic models: `ExchangeViolation`, `ExchangeComplianceResult`, `ScenarioComplianceResult`, `ComplianceReport`. |
| `validator.py` | `ComplianceValidator` – the stateless validator that processes a traffic file or dict. |
