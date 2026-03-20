# Sequence Diagram — Test Generation (including Validation and Formatting)

Minimum actors: **MCPProbeOrchestrator**, **GherkinFeatureGenerator**, **MCPProbeServiceClient**, **GherkinFormatter**, **FeatureValidator**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Gen as GherkinFeatureGenerator
    participant Service as MCPProbeServiceClient
    participant Formatter as GherkinFormatter
    participant Validator as FeatureValidator

    rect rgb(248, 248, 255)
        Note over Orch, Service: 1. Feature file generation
        Orch ->> Gen: GherkinFeatureGenerator(llm, service_client, output_dir, discovery_result, server_command)
        Orch ->> Gen: generate_all(unit_plan, integration_plan, on_progress)
        loop for each primitive (tool / resource / prompt) and integration
            Gen ->> Service: query_codebase(primitive context)
            Service -->> Gen: code context (results)
            Note right of Gen: LLM generates Gherkin,<br/>parse & validate, write .feature
            Gen -->> Orch: (per-file progress)
        end
        Gen -->> Orch: GenerationResult(files_generated, files_failed, validation_warnings)
    end

    rect rgb(245, 252, 245)
        Note over Orch, Validator: 2. Validation and formatting
        Orch ->> Formatter: GherkinFormatter()
        Orch ->> Formatter: format_directory(features_dir)
        Formatter ->> Formatter: parse_feature_files(), normalize_all_steps(), write_feature_files()
        Formatter -->> Orch: GherkinFeatureCollection

        Orch ->> Validator: FeatureValidator()
        Orch ->> Validator: validate_collection(feature_collection, auto_fix=True)
        Validator -->> Orch: ValidationResult(compliant, normalised, rejected)
        alt normalised > 0
            Orch ->> Formatter: write_feature_files(feature_collection)
        end
        Orch ->> Orch: store feature_collection
    end
```

## Summary

| Phase | Orchestrator action | Main interaction |
|-------|---------------------|-------------------|
| **Generation** | Requires discovery_result, unit_test_plan, integration_test_plan. Creates Generator with LLM and Service; calls `generate_all()`. | Generator iterates over primitives and integration scenarios; calls Service `query_codebase()` for code context; uses LLM to produce Gherkin, then parses, validates, and writes `.feature` files. Returns `GenerationResult`. |
| **Validation & formatting** | Creates GherkinFormatter; calls `format_directory(features_dir)` to parse, normalize step text, and write. Creates FeatureValidator; calls `validate_collection(collection, auto_fix=True)`. If any steps were normalised, calls Formatter `write_feature_files()` again. | Formatter returns `GherkinFeatureCollection`. Validator checks steps against canonical step library, auto-fixes where possible, returns counts (compliant / normalised / rejected). |
