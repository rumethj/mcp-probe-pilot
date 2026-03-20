# Sequence Diagram — Step Implementation Generation

Minimum actors: **MCPProbeOrchestrator**, **MCPProbeServiceClient**, **StepImplementationGenerator**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Service as MCPProbeServiceClient
    participant Gen as StepImplementationGenerator

    rect rgb(248, 252, 248)
        Note over Orch, Gen: Prebuilts and generator setup
        Orch ->> Service: async with MCPProbeServiceClient(service_url)
        activate Service
        Orch ->> Service: download_prebuilts(output_dir)
        Service -->> Orch: list[Path] (written files)
        Orch ->> Service: get_prebuilts()
        Service -->> Orch: {files, dependencies}
        deactivate Service

        Note right of Orch: Extract prebuilt steps.py content,<br/>store test_dependencies
        Orch ->> Gen: StepImplementationGenerator(llm, prebuilt_steps_code, output_dir)
        activate Gen
        Orch ->> Gen: generate_all(feature_collection)
    end

    rect rgb(245, 250, 248)
        Note over Gen: Per-scenario step generation
        loop for each feature, then each scenario
            Gen ->> Gen: _get_missing_steps(scenario)
            Note right of Gen: Compare scenario steps to<br/>implemented patterns (prebuilt + generated)
            alt missing steps
                Gen ->> Gen: _generate_for_scenario(…) [LLM]
                Gen ->> Gen: _filter_duplicate_steps(), merge, write steps.py
            else no missing steps
                Gen ->> Gen: steps_skipped += count
            end
        end
        Gen ->> Gen: _validate_final_output(feature_collection)
        Gen -->> Orch: StepImplementationResult(steps_generated, steps_skipped, validation_errors, …)
        deactivate Gen
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|-------------------|
| **Fetch prebuilts** | Uses `MCPProbeServiceClient`: `download_prebuilts(output_dir)` then `get_prebuilts()`. | Service returns prebuilt files (e.g. steps.py) and dependencies; orchestrator stores them and passes steps code to the generator. |
| **Generate implementations** | Creates `StepImplementationGenerator(llm, prebuilt_steps_code, output_dir)`; calls `generate_all(feature_collection)`. | Generator parses prebuilt steps for existing patterns; for each scenario finds missing steps, calls LLM to generate code, deduplicates, appends to steps.py, then runs final validation. Returns `StepImplementationResult`. |
