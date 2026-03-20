# Sequence Diagram — Report Generation and Transmission

Minimum actors: **MCPProbeOrchestrator**, **ReportBuilder** (module: `build_report` / `build_and_push_report`), **MCPProbeServiceClient**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Builder as ReportBuilder
    participant Service as MCPProbeServiceClient

    rect rgb(250, 252, 250)
        Note over Orch, Service: Build and push probe report
        Orch ->> Builder: build_and_push_report(project_code, features_dir, compliance_report, service_url)
        activate Builder

        Builder ->> Builder: build_report(project_code, features_dir, compliance_report)
        Note right of Builder: Load test-results.json (behave),<br/>index compliance by (feature, scenario),<br/>build FeatureReport / ScenarioReport,<br/>assemble ProbeReport
        Builder -->> Builder: ProbeReport

        Builder ->> Service: async with MCPProbeServiceClient(service_url)
        activate Service
        Builder ->> Service: POST /api/reports/{project_code} (report JSON)
        alt success
            Service -->> Builder: {report_id, …}
        else failure
            Service -->> Builder: (HTTP error; logged as warning)
        end
        deactivate Service

        Builder -->> Orch: ProbeReport
        deactivate Builder
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|-------------------|
| **Build** | Calls `build_and_push_report(project_code, features_dir, compliance_report, service_url)`. | ReportBuilder runs `build_report()`: reads `features/test-results.json` and compliance data, builds per-scenario and per-feature reports, returns a `ProbeReport`. |
| **Transmit** | (Inside same call.) ReportBuilder uses `MCPProbeServiceClient` to POST the report to `/api/reports/{project_code}`. | Service stores the report; push failures are logged as warnings and the built `ProbeReport` is still returned to the orchestrator. |
