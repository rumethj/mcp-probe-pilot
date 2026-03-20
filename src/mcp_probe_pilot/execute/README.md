# Execute

Creates an isolated virtual environment, installs dependencies, and runs behave tests.

## Purpose

The executor takes the generated `.feature` files and step implementations, sets up a clean venv using `uv`, installs all accumulated dependencies, and invokes `behave` in JSON output mode. The structured `TestExecutionResult` is then available for the report builder.

## Key Concepts

- **Isolated Venv** – A dedicated `.mcp-probe-venv` is created in the target repository root using `uv venv`. This prevents pollution of the host environment and ensures reproducible test runs.
- **Dependency Merging** – Dependencies arrive from two sources: the prebuilt scaffolding (`requirements.txt`) and any packages discovered during step implementation generation. Both are de-duplicated and installed together.
- **JSON Output** – Behave is invoked with `--format json --outfile test-results.json`, producing structured results that can be parsed without screen-scraping.
- **Timeout Protection** – A configurable timeout (default 300s) prevents runaway tests from blocking the pipeline indefinitely.

## Modules

| File | Description |
|------|-------------|
| `executor.py` | `TestExecutor` – venv management, dependency installation, and behave execution. |
