# Sequence Diagram — Compliance Validation

Minimum actors: **MCPProbeOrchestrator**, **ComplianceValidator**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Validator as ComplianceValidator

    rect rgb(252, 248, 252)
        Note over Orch, Validator: MCP spec compliance check
        Orch ->> Orch: traffic_path = features_dir / "mcp-traffic.json"
        alt traffic file missing
            Orch ->> Orch: return ComplianceReport() [empty]
        else traffic file exists
            Orch ->> Validator: ComplianceValidator()
            Orch ->> Validator: validate_file(traffic_path)
            activate Validator
            Validator ->> Validator: load JSON, validate_traffic(data)
            loop for each scenario in traffic
                Validator ->> Validator: _validate_scenario(scenario_data)
                loop for each exchange
                    Validator ->> Validator: _validate_exchange(idx, exchange)
                    Note right of Validator: initialize, tools/list, tools/call,<br/>resources/list, resources/read,<br/>prompts/list, prompts/get
                end
            end
            Validator -->> Orch: ComplianceReport(scenarios, spec_version)
            deactivate Validator
        end
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|-------------------|
| **Validate** | Resolves `features/mcp-traffic.json` (written by behave hooks during test run). If missing, returns empty `ComplianceReport`. Otherwise creates `ComplianceValidator()` and calls `validate_file(traffic_path)`. | Validator loads the traffic JSON, validates each scenario’s exchanges against the MCP 2025-11-25 spec (request/response shapes, notifications, etc.), and returns a `ComplianceReport` with per-scenario results and violation details. |
