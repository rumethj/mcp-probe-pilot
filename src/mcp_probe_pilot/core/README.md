# Core

Shared infrastructure used by every other module in mcp-probe-pilot.

## Purpose

Provides the foundational models, session management, LLM client wrapper, service client, and the canonical step vocabulary that tie the pipeline stages together.

## Key Concepts

- **Pydantic Models** – All inter-module data contracts live under `core/models/`. Each pipeline stage consumes and produces these models, making data flow explicit and type-safe.
- **MCPSession** – An async context manager wrapping the official `mcp` Python SDK's `ClientSession`. Handles subprocess lifecycle, timeouts, and provides typed methods for every MCP operation (list tools, call tool, read resource, get prompt, etc.).
- **LLMClient** – A thin context-managed wrapper around `ChatGoogleGenerativeAI` (LangChain). Centralises model configuration so callers just do `with LLMClient() as llm`.
- **MCPProbeServiceClient** – Async HTTP client for the companion `mcp-probe-service` REST API. Covers codebase indexing, prebuilt scaffolding retrieval, feature storage/download, and report submission.
- **Canonical Steps** – A single-source-of-truth list (`canonical_steps.py`) defining every valid Gherkin step pattern. Both the generator (via prompt rendering) and the validator (via regex matching) derive their behaviour from this list.

## Modules

| File | Description |
|------|-------------|
| `models/config.py` | `ProbeConfig` – project configuration loaded from `mcp-probe-service-properties.json`. |
| `models/discover.py` | `DiscoveryResult`, `ToolInfo`, `ResourceInfo`, `PromptInfo`, etc. |
| `models/plan.py` | `UnitTestPlanResult`, `IntegrationTestPlanResult`, `ScenarioPlan`. |
| `models/gherkin_feature.py` | `GherkinFeature`, `GherkinFeatureCollection`, `GherkinStep`, `GherkinScenario`. |
| `models/generation.py` | `GenerationResult` – file generation summary. |
| `models/step_implementation.py` | `StepImplementationResult` – step generation summary. |
| `models/execution.py` | `TestExecutionResult` – behave run summary. |
| `models/report.py` | `ProbeReport`, `FeatureReport`, `ScenarioReport` and related types. |
| `mcp_session.py` | `MCPSession` – async MCP server connection manager. |
| `llm_client.py` | `LLMClient` – Google Gemini LLM wrapper. |
| `service_client.py` | `MCPProbeServiceClient` – HTTP client for the probe service. |
| `canonical_steps.py` | Master step vocabulary and prompt rendering helper. |
