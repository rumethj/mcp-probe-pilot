# Report

Builds a `ProbeReport` from test execution artefacts and pushes it to the mcp-probe-service.

## Purpose

The report builder is the final stage of the pipeline. It correlates three data sources by `(feature_name, scenario_name)`:
1. `test-results.json` – behave JSON output (step statuses, durations)
2. `mcp-traffic.json` – recorded MCP request/response exchanges
3. `ComplianceReport` – per-scenario compliance validation results

The resulting `ProbeReport` is a single JSON document containing per-feature, per-scenario test results with compliance details and exchange-level violation tracking.

## Key Concepts

- **Three-Way Correlation** – Behave results, traffic recordings, and compliance results are joined by the composite key `(feature_name, scenario_name)`. This ensures each scenario's test status, MCP exchanges, and compliance verdicts are unified in one place.
- **Status Derivation** – Scenario status is derived from individual step results: any `failed`/`error` step makes the scenario `failed`, all-`skipped` makes it `skipped`, otherwise `passed`.
- **Compliance Merging** – Each scenario gets a `ScenarioComplianceDetail` with `mcp_compliant`, violation details, and per-exchange passed/failed rules.
- **Service Push** – After building the report, it is POSTed to `/api/reports/{project_code}`. Push failures are logged as warnings rather than raised, so the report is always available locally.

## Modules

| File | Description |
|------|-------------|
| `report_builder.py` | `ReportHandler` – report assembly and service push logic. |
