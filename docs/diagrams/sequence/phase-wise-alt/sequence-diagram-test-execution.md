# Sequence Diagram — Test Execution

Minimum actors: **MCPProbeOrchestrator**, **TestExecutor**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Exec as TestExecutor

    rect rgb(240, 248, 248)
        Note over Orch, Exec: Environment setup and test run
        Orch ->> Orch: require test_dependencies (from step implementation stage)
        Orch ->> Exec: TestExecutor(repo_root, dependencies)
        activate Exec
        Orch ->> Exec: setup_environment()
        Exec ->> Exec: _create_venv() [uv venv]
        Exec ->> Exec: _install_dependencies() [uv pip install]
        Exec ->> Exec: _install_requirements() [features/requirements.txt]
        Exec -->> Orch: (void)

        Orch ->> Exec: run_tests(feature_file=None)
        Note right of Exec: subprocess: python -m behave<br/>--format json --outfile test-results.json
        Exec ->> Exec: _parse_results(proc) [read JSON]
        Exec -->> Orch: TestExecutionResult(features, scenarios, passed, failed, …)
        deactivate Exec
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|------------------|
| **Setup** | Builds `TestExecutor(repo_root, dependencies)` and calls `setup_environment()`. | Executor creates/uses `.mcp-probe-venv`, installs dependencies and `features/requirements.txt`. |
| **Run** | Calls `executor.run_tests(feature_file)`. | Executor runs `behave` in the venv with JSON output to `features/test-results.json`, parses the result into `TestExecutionResult`. |
