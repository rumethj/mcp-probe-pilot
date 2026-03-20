# Report Builder — Internal Flowchart

## Overview

The Report Builder correlates three data sources by `(feature_name, scenario_name)` to produce a unified `ProbeReport`, then pushes it to the mcp-probe-service for persistent storage and visualization. No LLM calls are involved — this is pure data assembly.

## Report Build Flow

```mermaid
flowchart TD
    Start([Start: build_report]) --> LoadResults{"test-results.json\nexists?"}
    LoadResults -- Yes --> ParseResults["json.loads(test-results.json)\n→ behave_features list"]
    LoadResults -- No --> EmptyResults["behave_features = []\n(log warning)"]
    ParseResults --> LoadTraffic
    EmptyResults --> LoadTraffic

    LoadTraffic{"mcp-traffic.json\nexists?"}
    LoadTraffic -- Yes --> ParseTraffic["json.loads(mcp-traffic.json)\n→ traffic_scenarios list"]
    LoadTraffic -- No --> EmptyTraffic["traffic_scenarios = []\n(log warning)"]
    ParseTraffic --> IndexCompliance
    EmptyTraffic --> IndexCompliance

    IndexCompliance["Index ComplianceReport\nby (feature_name, scenario_name)\n→ compliance_map dict"]
    IndexCompliance --> IndexTraffic["Index traffic exchanges\nby (feature_name, scenario_name)\n→ traffic_map dict"]
    IndexTraffic --> IterFeatures

    IterFeatures["For each behave feature"]
    IterFeatures --> IterScenarios["For each element\nwhere type == 'scenario'"]

    IterScenarios --> DeriveStatus["_derive_scenario_status(steps)\n→ passed | failed | errored | skipped"]
    DeriveStatus --> BuildSteps["_build_step_results(steps)\n→ list of StepResult"]
    BuildSteps --> LookupCompliance["compliance_map.get(\nfeature_name, scenario_name)"]
    LookupCompliance --> BuildCompliance["_build_compliance_detail()\n→ ScenarioComplianceDetail"]
    BuildCompliance --> LookupTraffic["traffic_map.get(\nfeature_name, scenario_name)"]
    LookupTraffic --> BuildExchanges["_build_exchanges()\n→ list of Exchange"]
    BuildExchanges --> AppendScenario["Append ScenarioReport\n(status, steps, compliance, exchanges)"]

    AppendScenario --> MoreScenarios{More scenarios\nin this feature?}
    MoreScenarios -- Yes --> IterScenarios
    MoreScenarios -- No --> BuildFeature["Build FeatureReport\n(summary_test_passed, mcp_compliant,\nduration, passed/failed counts)"]

    BuildFeature --> MoreFeatures{More behave\nfeatures?}
    MoreFeatures -- Yes --> IterFeatures
    MoreFeatures -- No --> Aggregate["Aggregate totals:\ntotal_scenarios, passed, failed\nall_tests_passed, all_compliant"]

    Aggregate --> BuildReport["Build ProbeReport(\nproject_code, timestamp,\nsummary_test_passed, mcp_compliant,\nspec_version, feature_reports)"]
    BuildReport --> End([Output: ProbeReport])

    style Start fill:#e8f5e9
    style End fill:#e8f5e9
```

## Report Push Flow

```mermaid
flowchart TD
    Start([Start: build_and_push_report]) --> Build["build_report()\n→ ProbeReport"]
    Build --> OpenClient["async with MCPProbeServiceClient(service_url)"]
    OpenClient --> PostReport["POST /api/reports/{project_code}\nContent-Type: application/json\nbody = ProbeReport.model_dump_json()"]

    PostReport --> CheckStatus{"HTTP status\n< 400?"}
    CheckStatus -- Yes --> LogSuccess["Log: report_id = response.report_id"]
    CheckStatus -- No --> LogWarn["Log warning:\nHTTP {status}: {body}"]

    LogSuccess --> Return
    LogWarn --> Return

    PostReport -. "ServiceClientError\nor Exception" .-> CatchErr["Log warning:\ncould not push report"]
    CatchErr --> Return

    Return([Return: ProbeReport])

    style Start fill:#e8f5e9
    style Return fill:#e8f5e9
    style LogWarn fill:#fff9c4
    style CatchErr fill:#fff9c4
```

## Service-Side Report Storage & Visualization

```mermaid
flowchart TD
    Receive([POST /api/reports/project_code]) --> DeriveId["report_id = timestamp\n(ISO-8601, colons → dashes)"]
    DeriveId --> WriteDisk["Write JSON to\ndata/reports/{project_code}/{report_id}.json"]
    WriteDisk --> Respond["201 Created\n{report_id, stored: true}"]
    Respond --> Stored[(Report stored on disk)]

    Stored --> Dashboard["GET / → dashboard.html\nLists all projects with\nlatest ReportSummary"]
    Dashboard --> ProjectView["GET /project/{code} → project.html\nHistorical runs for project\n(list of ReportSummary)"]
    ProjectView --> ReportView["GET /project/{code}/report/{id}\n→ report.html\nFeature-level panels\n(pass/fail, compliance badges)"]
    ReportView --> FeatureView["GET /project/{code}/report/{id}/feature/{i}\n→ feature.html\nScenario details: steps,\ncompliance violations, MCP exchanges"]

    style Receive fill:#e8f5e9
    style Stored fill:#e3f2fd
    style Dashboard fill:#ede7f6
    style ProjectView fill:#ede7f6
    style ReportView fill:#ede7f6
    style FeatureView fill:#ede7f6
```
