# MCP-Probe Architecture v4

> An automated, deterministic BDD testing and MCP compliance validation framework for any Model Context Protocol (MCP) server.

---

## Testing Philosophy

### Approach: Grey-Box Testing

MCP-Probe uses a **grey-box testing** approach that combines knowledge of server internals during test *generation* with pure black-box *execution*:

| Phase | Knowledge Used | Execution Method |
|-------|----------------|------------------|
| **Discovery** | MCP protocol handshake + AST source analysis | MCP client + Python AST parser |
| **Test Planning** | Discovered schemas + server capabilities | LLM-driven structured output |
| **Test Generation** | Scenario plans + ChromaDB code context + canonical step library + test data manifest | LLM-driven Gherkin synthesis |
| **Validation** | Canonical step registry + normalization rules | Programmatic regex matching + fuzzy match |
| **Step Implementation** | Prebuilt step library + AST deduplication | LLM-driven code synthesis |
| **Test Execution** | None (black-box) | MCP client interface only |
| **MCP Compliance** | MCP 2025-11-25 specification rules | Deterministic JSON-RPC traffic analysis |
| **Reporting** | Test results + traffic + compliance data | Correlation and aggregation |

### Determinism Guarantees

- All test **execution** is fully deterministic — no LLM calls at runtime
- Tests exercise the MCP server exclusively through the standard MCP client protocol
- Test cases are stored as static Gherkin `.feature` files (reproducible across runs)
- All assertion steps use deterministic checks (JSON field matching, error detection, content type verification)
- **LLM dependency removed from test runtime**: semantic assertions and agentic `process_query` workflows eliminated from prebuilt steps
- Integration tests use explicit MCP call chaining with saved context variables instead of LLM-driven tool selection
- MCP compliance validation is fully deterministic — rule-based JSON-RPC schema checks with no LLM involvement

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          mcp-probe-pilot                            │
│                       (CLI + Orchestrator)                          │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │
│  │ Discover  │→ │  Plan    │→ │ Generate │→ │   Validate   │       │
│  │          │  │          │  │          │  │              │        │
│  │ • MCP    │  │ • Unit   │  │ • Feature│  │ • Canonical  │       │
│  │ • AST    │  │ • Integ. │  │ • Steps  │  │   compliance │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘       │
│       │              │             │               │                │
│       │              │             │               ▼                │
│       │              │             │        ┌──────────────┐       │
│       │              │             │        │   Execute    │       │
│       │              │             │        │  (behave)    │       │
│       │              │             │        └──────┬───────┘       │
│       │              │             │               │                │
│       │              │             │               ▼                │
│       │              │             │        ┌──────────────┐       │
│       │              │             │        │  Compliance  │       │
│       │              │             │        │  (MCP spec)  │       │
│       │              │             │        └──────┬───────┘       │
│       │              │             │               │                │
│       │              │             │               ▼                │
│       │              │             │        ┌──────────────┐       │
│       │              │             │        │   Report &   │       │
│       │              │             │        │   Upload     │       │
│       │              │             │        └──────────────┘       │
│       │              │             │                                │
│       ▼              ▼             ▼                                │
│  ┌─────────────────────────────────────┐                           │
│  │        mcp-probe-service            │                           │
│  │  (ChromaDB + Prebuilt Scaffolding   │                           │
│  │   + Feature Caching + Reports)      │                           │
│  └─────────────────────────────────────┘                           │
│                                                                     │
│                    Target: Any MCP Server                            │
│                    (e.g. mcp-probe-test-server-library)              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Package and Distribution

MCP-Probe Pilot is distributed as a Python package via PyPI.

| Field | Value |
|-------|-------|
| Package name | `mcp-probe-pilot` |
| Version | `0.1.1` |
| License | MIT |
| Python | `>=3.12` |
| Entry point | `mcp-probe-pilot` CLI command |
| Build system | setuptools |
| Publishing | GitHub Actions → PyPI (OIDC trusted publishing) |

---

## Project Structure

```
mcp-probe-pilot/
├── src/mcp_probe_pilot/
│   ├── cli.py                          ← Typer CLI entry point
│   ├── orchestrator.py                 ← Pipeline orchestrator
│   ├── core/
│   │   ├── canonical_steps.py          ← Single source of truth for step vocabulary
│   │   ├── llm_client.py              ← LangChain Google Gemini wrapper
│   │   ├── mcp_session.py             ← Generic async MCP session (stdio)
│   │   ├── service_client.py          ← HTTP client for mcp-probe-service
│   │   └── models/
│   │       ├── config.py              ← ProbeConfig
│   │       ├── discover.py            ← ToolInfo, ResourceInfo, PromptInfo, etc.
│   │       ├── plan.py                ← ScenarioPlan, UnitTestPlanResult, etc.
│   │       ├── gherkin_feature.py     ← GherkinFeature, GherkinStep, etc.
│   │       ├── generation.py          ← GenerationResult
│   │       ├── step_implementation.py ← StepImplementationResult
│   │       ├── execution.py           ← TestExecutionResult
│   │       └── report.py             ← ProbeReport, FeatureReport, etc.
│   ├── discover/
│   │   ├── discoverer.py             ← MCPDiscoverer
│   │   └── ast_indexer.py            ← ASTIndexer
│   ├── plan/
│   │   ├── planner.py                ← Planner (LLM-driven test planning)
│   │   └── prompts.py                ← Planning prompt templates
│   ├── generate/
│   │   ├── gherkin_feature_generator.py ← GherkinFeatureGenerator
│   │   ├── gherkin_formatter.py        ← GherkinParser + StepNormalizer + GherkinFormatter
│   │   ├── step_implementation_generator.py ← StepImplementationGenerator
│   │   └── prompts.py                  ← Generation prompt templates + canonical step library
│   ├── validate/
│   │   └── validator.py               ← CanonicalStepRegistry + FeatureValidator
│   ├── execute/
│   │   └── executor.py                ← TestExecutor (uv venv + behave)
│   ├── compliance_engine/
│   │   ├── validator.py               ← ComplianceValidator (MCP spec rules)
│   │   ├── models.py                  ← ComplianceReport, ExchangeViolation, etc.
│   │   └── mcp_compliance_rules.md    ← Documented rule catalogue
│   └── report/
│       └── report_builder.py          ← ReportHandler (build + push)
├── tests/
│   ├── unit/                          ← Per-module unit tests
│   └── integration/                   ← Cross-module integration tests
├── ci-integration/                    ← Tekton CI/CD manifests
├── docs/                              ← Architecture docs, diagrams, usage guides
├── pyproject.toml                     ← Package metadata and dependencies
└── .github/workflows/publish.yaml     ← PyPI publishing workflow
```

---

## Pipeline Stages

The pipeline is orchestrated by `MCPProbeOrchestrator` and driven by the `mcp-probe-pilot` CLI. Each stage builds on the outputs of the previous one.

### Stage 0: Feature Caching (Skip-Generation Fast Path)

**Problem:** Regenerating tests for the same server on every run is wasteful when the server's API hasn't changed.

**Solution:** Before running the full pipeline, check the mcp-probe-service for previously stored feature files. If found, pull them and skip directly to execution.

| Component | File |
|-----------|------|
| `MCPProbeOrchestrator` | `orchestrator.py` |
| `MCPProbeServiceClient` | `core/service_client.py` |

**How it works:**
1. Query `GET /api/features/{server_id}` to check for stored features.
2. If found, download all files into `{repo_root}/features/` via `download_features()`.
3. Sync any requirements.txt dependencies from the stored files.
4. Skip directly to test execution (Stage 6).

**Bypass:** The `--generate-new` CLI flag forces full regeneration regardless of cached features.

---

### Stage 1: Discovery (3 sub-steps)

#### 1.1 MCP Server Discovery

**Problem:** We need to know what tools, resources, and prompts the target server exposes before generating any tests.

**Solution:** Connect to the server via MCP stdio transport, perform the protocol handshake, and enumerate all primitives.

| Component | File |
|-----------|------|
| `MCPSession` | `core/mcp_session.py` |
| `MCPDiscoverer` | `discover/discoverer.py` |
| `DiscoveryResult` | `core/models/discover.py` |

**How it works:**
1. `MCPSession` parses the `server_command` (e.g. `uv run server.py`) via `shlex.split()` into a `StdioServerParameters`, spawns the subprocess, establishes a `ClientSession` over stdio pipes, and calls `session.initialize()`.
2. `MCPDiscoverer` calls `list_tools()`, `list_resources()`, `list_resource_templates()`, and `list_prompts()` on the session.
3. `parse_server_info()` extracts `ServerInfo` including name, version, protocol version, and `ServerCapabilities` (tools, resources, prompts, sampling, logging).
4. Each MCP primitive is mapped to a Pydantic model:
   - `ToolInfo` — name, description, JSON input schema
   - `ResourceInfo` — URI, name, description, MIME type, is_template flag
   - `PromptInfo` — name, description, list of `PromptArgument` (name, description, required)
5. All primitives are aggregated into a `DiscoveryResult` with lookup helpers (`get_tool()`, `get_resource()`, `get_prompt()`).

**Environment variables:** The `test_env` config field is merged into the subprocess environment during discovery, allowing servers that require specific env vars (e.g. API keys, feature flags) to be probed correctly.

**Output:** `DiscoveryResult` with full primitive metadata and server info.

#### 1.2 AST Codebase Indexing

**Problem:** To generate meaningful tests, we need to understand the server's implementation — not just its public interface.

**Solution:** Parse all Python source files via the `ast` module and extract structural entities.

| Component | File |
|-----------|------|
| `ASTIndexer` | `discover/ast_indexer.py` |
| `CodeEntity`, `CodebaseIndex` | `core/models/discover.py` |

**How it works:**
1. Recursively discovers `.py` files, excluding a comprehensive set of directories: `__pycache__`, `.git`, `venv`, `.venv`, `features`, `tests`, `node_modules`, `dist`, `build`, `reports`, and any directory matching `*mcp-probe*` or `.*`.
2. Excludes `__init__.py` files by default.
3. For each file, parses the AST and extracts:
   - Functions and async functions (including decorators, docstrings, parameter signatures)
   - Classes and their methods
4. Each entity becomes a `CodeEntity` with `file_path`, `entity_type`, `name`, `code` (source text), `start_line`, `end_line`, `docstring`, `decorators`, `parent_class`.
5. SHA-256 hashes are computed per-file for incremental indexing — unchanged files are skipped on subsequent runs.

**Output:** `CodebaseIndex` with all entities and file hashes.

#### 1.3 Codebase Index Upload

**Problem:** Code context needs to be semantically searchable for the generation stage.

**Solution:** Upload all `CodeEntity` records to the mcp-probe-service, which stores them in ChromaDB for vector similarity search.

| Component | File |
|-----------|------|
| `MCPProbeServiceClient` | `core/service_client.py` |
| Codebase routes | `mcp-probe-service/routes/codebase.py` |

**How it works:**
1. The service client POSTs entities to `/api/codebase/index`.
2. The service creates ChromaDB documents with IDs like `file_path::name::start_line`.
3. ChromaDB's default embedding model indexes the code text for semantic search.

---

### Stage 2: Test Planning (2 sub-steps)

#### 2.1 Unit Test Planning

**Problem:** For each MCP primitive, we need a comprehensive set of test scenario titles covering happy paths, edge cases, and error states.

**Solution:** Use an LLM with structured output to generate scenario titles from primitive schemas.

| Component | File |
|-----------|------|
| `Planner` | `plan/planner.py` |
| Planning prompts | `plan/prompts.py` |
| `ScenarioPlan`, `UnitTestPlanResult` | `core/models/plan.py` |
| `LLMClient` | `core/llm_client.py` |

**How it works:**
1. For each discovered tool, resource, and prompt, the planner constructs a `ChatPromptTemplate` with the primitive's schema.
2. The LLM (Gemini 2.5 Flash) is invoked with `.with_structured_output(_ScenarioListOutput)` to return a validated list of scenario titles.
3. Each title becomes a `ScenarioPlan` containing the scenario description and the list of MCP primitives involved.
4. Results are grouped by primitive type in `UnitTestPlanResult` (with `get_scenario_plans(type, name)` for lookup).

**Prompt strategy:**
- System prompts instruct the LLM to act as a "QA Lead" creating test plans.
- Each primitive type has dedicated system/human prompt pairs (`TOOL_UNIT_SYSTEM/HUMAN`, `RESOURCE_UNIT_SYSTEM/HUMAN`, `PROMPT_UNIT_SYSTEM/HUMAN`).
- The LLM outputs only scenario titles, not full Gherkin — this separates planning from generation.

#### 2.2 Integration Test Planning

**Problem:** Real MCP client interactions chain multiple primitives together. We need scenarios that test cross-primitive workflows.

**Solution:** Present all discovered primitives to the LLM and ask it to identify workflow patterns.

**How it works:**
1. All tools, resources, and prompts are summarised into a capabilities overview using `_summarise_tools()`, `_summarise_resources()`, and `_summarise_prompts()`.
2. The LLM identifies three workflow patterns:
   - **Chain-of-Calls** — Tool A output feeds Tool B input
   - **Resource-Augmented** — Tool creates data, then a resource is read to verify
   - **Prompt-Driven** — Prompt is retrieved, then a tool is called with prompt context
3. The LLM returns `IntegrationTestPlanResult` with `integration_scenarios`, each containing a scenario title, pattern type, and list of involved primitives.

---

### Stage 3: Feature File Generation

**Problem:** Scenario titles need to be expanded into complete, executable Gherkin feature files using a constrained step vocabulary.

**Solution:** LLM-driven Gherkin synthesis constrained by the Canonical Step Library, with code context from ChromaDB and an optional test data manifest.

| Component | File |
|-----------|------|
| `GherkinFeatureGenerator` | `generate/gherkin_feature_generator.py` |
| Generation prompts | `generate/prompts.py` |
| `CANONICAL_STEP_LIBRARY` | `generate/prompts.py` (rendered from `core/canonical_steps.py`) |

**How it works:**
1. For each primitive, the generator:
   a. Queries ChromaDB for relevant source code context via `service_client.query_codebase()` — makes three queries per primitive (implementation, seed data/fixtures, validation/error handling) and deduplicates by entity name.
   b. Renders a prompt template (`TOOL_UNIT_HUMAN`, `RESOURCE_UNIT_HUMAN`, `PROMPT_UNIT_HUMAN`, or `INTEGRATION_HUMAN`) with the primitive schema, scenario plans, and code context.
   c. Extracts schema hints (enums, defaults, patterns, examples) from JSON Schema properties for tool primitives.
   d. Appends the test data manifest (if configured) to prevent the LLM from hallucinating test values.
   e. Appends the `CANONICAL_STEP_LIBRARY` — a strict vocabulary of allowed step patterns.
   f. Appends any step patterns already used in previously generated features (for step reuse encouragement).
2. The LLM generates a complete Gherkin feature file.
3. Post-processing:
   - Extracts Gherkin from markdown code blocks (`\`\`\`gherkin` or generic `\`\`\``).
   - Validates the `[END_OF_FEATURE]` termination marker (trims incomplete scenarios if missing).
   - Validates via the official `gherkin.parser.Parser`.
   - Validates primitive references — checks that tool/prompt names in the generated Gherkin exist in the discovery result, stripping scenarios with hallucinated names.
   - Retries on failure (up to `MAX_RETRIES = 1`).
4. Large scenario lists are batched (`MAX_SCENARIOS_PER_BATCH = 15`) and merged into a single feature file (keeping the Feature header from the first batch).
5. Features are processed **sequentially** (not concurrently) to enable step pattern tracking across features — extracted steps from each feature are fed into subsequent generation prompts.

**Output:** `.feature` files written to `{repo_root}/features/`.

#### The Canonical Step Library

The Canonical Step Library is the **central constraint** that makes the framework work. It is defined as a single source of truth in `core/canonical_steps.py` and exported as both flat patterns (for the validator) and a rendered markdown prompt (for the generator).

**Master step list:** Each step is defined as a `(keyword, section_tag, step_text)` tuple in `_CANONICAL_STEPS`. The section tag controls how the step is grouped in the LLM prompt. Two derived views are exported:
- `CANONICAL_PATTERNS` — flat `(keyword, text)` pairs consumed by `CanonicalStepRegistry`
- `render_step_library_prompt()` — markdown prompt fragment appended to every LLM generation request

**Step categories:**

| Category | Example Pattern | Purpose |
|----------|----------------|---------|
| Setup | `Given the MCP Client is initialized and connected to the MCP Server: "{server_command}"` | Starts server subprocess, establishes MCP session |
| Direct Actions | `When the MCP Client calls the tool "{tool_name}" with parameters` | Direct MCP primitive calls with literal values |
| Saved-Context Actions | `When the MCP Client calls the tool "{tool_name}" with saved parameters` | Chaining: uses values saved from previous call responses |
| Context Variables | `Then I save the response field "{field}" as "{variable}"` | Extract and save data from responses for chaining |
| Value Construction | `Then I construct the value "{template}" and save as "{variable}"` | Build composite values from saved variables |
| Response Assertions | `Then the response should be successful` | Deterministic checks on response content |
| Error Assertions | `Then the response should contain an error` | Verify error conditions |
| Field Assertions | `Then the response field "{field}" should be "{expected_value}"` | JSON field-level validation |
| Key Comparison | `Then the response key "{key}" should equal saved variable "{variable}"` | Compare response data against saved context |
| Elicitation | `Given the next elicitation response will accept with` | Client-side elicitation request handling |
| Sampling | `Then a sampling request should have been received` | Server-initiated sampling verification |
| Roots | `Given the MCP Client has roots` | Client filesystem roots support |

---

### Stage 4: Validation and Formatting

**Problem:** LLM-generated Gherkin may use step wording that deviates from the canonical patterns, causing "undefined step" errors at runtime.

**Solution:** A two-phase validation pipeline: text normalization followed by canonical compliance checking.

| Component | File |
|-----------|------|
| `GherkinParser` + `StepNormalizer` + `GherkinFormatter` | `generate/gherkin_formatter.py` |
| `CanonicalStepRegistry` + `StepNormaliser` + `FeatureValidator` | `validate/validator.py` |

#### Phase 1: Text Normalization (GherkinFormatter)

1. Parses all `.feature` files using the `gherkin-official` Python parser into `GherkinFeatureCollection` via the custom `GherkinParser` class (which converts the official AST into the Pydantic `GherkinFeature` / `GherkinScenario` / `GherkinStep` model hierarchy).
2. `StepNormalizer` applies `NORMALIZATION_RULES` — regex-based text transformations that map common LLM variations to canonical forms:
   - `"the response contains a"` → `"the response should contain"`
   - `"the response should be unsuccessful"` → `"the response should be a failure"`
   - `"the response field X should equal"` → `"the response field X should be"`
   - `"the error should indicate"` → `"the error message should indicate"`
   - Unquoted booleans: `with value True` → `with value "True"`
3. Normalizes data table headers (e.g. `parameter_name` → `parameter`, `parameter_value` → `value`).
4. Fixes `{variable}` literals in "with parameters" tables by converting them to "with saved parameters" tables with the `saved_variable` column header — a common LLM error where the generator uses curly-brace variable references in direct-parameter tables instead of the saved-parameter step pattern.
5. Handles corrupted step keyword chains (e.g. `And Then ...` → proper `Then ...`).
6. Writes the normalized `.feature` files back to disk.

#### Phase 2: Canonical Compliance Validation (FeatureValidator)

1. `CanonicalStepRegistry` converts each canonical step pattern (from `core/canonical_steps.py`) into a compiled regex:
   - `"{placeholder}"` → `"([^"]+)"` (quoted string capture)
   - `{value:d}` → `(\d+)` (integer capture)
   - `{name}` → `(.+)` (bare placeholder capture)
   - Literal `[]` is properly escaped
2. For each step in the feature collection:
   a. **Direct match** against all canonical regex patterns → `COMPLIANT`
   b. **Normalize** using the validator's own `NORMALIZATION_RULES`, then re-match → `NORMALISED` (step text is rewritten in place if `auto_fix=True`)
   c. Steps that normalize to empty text (LLM-dependent steps like semantic queries) are automatically `REJECTED`
   d. **Fuzzy match** via token overlap scoring (threshold ≥ 0.4) → provides diagnostic "closest pattern" info
   e. If all fail → `REJECTED` with diagnostic reason
3. Returns `ValidationResult` with per-feature and aggregate statistics:
   - `compliant` / `normalised` / `rejected` counts
   - List of `rejected_steps` with original text and diagnostic reasons
   - `is_valid` property (true when `rejected == 0`)

**Why two phases?** The formatter handles well-known textual variations and structural fixes (table headers, keyword chains, variable references). The validator handles structural compliance against the canonical library and catches novel deviations the formatter's rules don't cover. Running both maximizes the acceptance rate of LLM-generated steps.

---

### Stage 5: Step Implementation Generation

**Problem:** Even though the canonical step library covers most patterns, the LLM may generate scenarios using step wordings that fall outside the prebuilt implementations.

**Solution:** AST-based deduplication + LLM-driven code generation for missing steps only.

| Component | File |
|-----------|------|
| `StepImplementationGenerator` | `generate/step_implementation_generator.py` |
| Step impl prompts | `generate/prompts.py` |

**How it works:**
1. Download prebuilt scaffolding from mcp-probe-service (via `service_client.download_prebuilts()`):
   - `steps/steps.py` — canonical step implementations
   - `helper/mcp_client.py` — MCP client for BDD tests
   - `environment.py` — behave lifecycle hooks
   - `requirements.txt` — test dependencies
2. Parse the prebuilt `steps.py` via `ast.parse()` to extract all implemented step patterns using `extract_implemented_steps()` — builds `dict[pattern, set[decorator_name]]` from `@given`/`@when`/`@then` decorators.
3. For each scenario in the feature collection:
   a. Normalize each step text to a generic pattern using `normalize_step_to_pattern()`:
      - Replaces JSON arrays `[...]` with `{json_value}`
      - Replaces typed converters `{name:d}` / `{name:int}` with `{number}`
      - Replaces `"quoted strings"` with `"{placeholder}"`
      - Replaces bare `{name}` (non-reserved) with `{placeholder}`
      - Replaces standalone integers with `{number}`
   b. Check if the pattern is implemented using `patterns_match()` — flexible matching that handles `{placeholder}` ≈ `{number}`, `"{placeholder}"` ≈ `{placeholder}`, `{json_value}` ≈ `{placeholder}`, and case-insensitive comparison.
   c. If all steps are implemented → skip.
   d. If missing steps exist → send the scenario to the LLM.
4. LLM generates Python code for missing step definitions:
   - System prompt provides the list of already-implemented steps to prevent duplication.
   - Validates generated code via `ast.parse()`.
   - Retries up to `MAX_RETRIES = 2` on syntax errors.
5. **Duplicate filtering**: Before appending, `_filter_duplicate_steps()` parses the generated code via AST, identifies any step functions whose patterns already exist in the implemented set, and removes them to prevent `AmbiguousStep` errors.
6. Appends generated code to `steps.py` (after the prebuilt code, separated by an auto-generated header comment).
7. Final validation: re-parses the complete `steps.py` and checks all required patterns (from the feature collection) are covered.

**Pattern matching algorithm:**
```
normalize_step_to_pattern(step_text):
  1. Replace JSON arrays [...] → {json_value}
  2. Replace {name:d} and {name:int} → {number}
  3. Replace "quoted strings" → "{placeholder}"
  4. Replace bare {name} (non-reserved) → {placeholder}
  5. Replace standalone integers → {number}

patterns_match(impl, required):
  1. Case-insensitive exact match → True
  2. Generic form: {number} → {placeholder}, "{placeholder}" → {placeholder}, {json_value} → {placeholder}
  3. Compare generic forms case-insensitively → True/False
```

---

### Stage 6: Test Execution

**Problem:** Generated tests need to run in an isolated environment against the target MCP server.

**Solution:** Create a dedicated virtual environment, install dependencies, and run behave.

| Component | File |
|-----------|------|
| `TestExecutor` | `execute/executor.py` |
| `TestExecutionResult` | `core/models/execution.py` |

**How it works:**
1. Creates an isolated venv at `{repo_root}/.mcp-probe-venv/` using `uv venv` (with the same Python interpreter as the current process).
2. Installs accumulated test dependencies via `uv pip install`:
   - Prebuilt requirements (from mcp-probe-service)
   - Any additional dependencies discovered during step generation
   - Contents of `features/requirements.txt` if present
3. Runs `behave` inside the venv:
   - Uses `--format json --outfile test-results.json` for structured output
   - Uses `--no-capture` for full output visibility
   - Timeout: 300 seconds per feature
   - Environment variables are inherited; user-defined `test_env` variables are merged last (can override inherited values)
4. Parses the JSON results into `TestExecutionResult`:
   - Per-scenario status: passed / failed / errored / skipped
   - Aggregate counts and total duration
   - Raw JSON preserved for detailed inspection

**Execution per feature:** The CLI runs each `.feature` file independently, allowing per-feature progress reporting and isolated failure handling. Before execution, any existing `mcp-traffic.json` is cleared so compliance validation only sees exchanges from the current run.

---

### Stage 7: MCP Compliance Validation

**Problem:** Passing functional tests does not guarantee that the MCP server's JSON-RPC responses conform to the MCP specification. A server might return correct data but use wrong field types, omit required fields, or violate the JSON-RPC 2.0 envelope rules.

**Solution:** Capture all JSON-RPC traffic during test execution and validate every request/response exchange against the MCP 2025-11-25 specification.

| Component | File |
|-----------|------|
| `ComplianceValidator` | `compliance_engine/validator.py` |
| Compliance models | `compliance_engine/models.py` |
| Rule catalogue | `compliance_engine/mcp_compliance_rules.md` |

**How it works:**
1. During test execution, the behave environment hooks in the prebuilt scaffolding write a `mcp-traffic.json` file containing all JSON-RPC exchanges, grouped by scenario.
2. The `ComplianceValidator` reads this traffic file and validates each exchange:
   a. **Exchange classification**: Distinguishes `request_response` exchanges from `notification` and `server_notification` types.
   b. **Notification validation**: Checks `jsonrpc: "2.0"` and absence of `id` field.
   c. **JSON-RPC envelope validation**: Checks version, response ID presence and match, `result` XOR `error` constraint.
   d. **Error object validation**: When `error` is present, checks it's an object with integer `code` and string `message`.
   e. **Method-specific validation**: Dispatches to dedicated validators based on the JSON-RPC method.
3. Method-specific validators cover all MCP protocol methods:

| Method | Key Rules | Count |
|--------|-----------|-------|
| `initialize` | protocolVersion, capabilities, serverInfo (name, version) | 10 |
| `tools/list` | tools array, tool name, inputSchema | 8 |
| `tools/call` | content array, content block types (text, image, audio, resource, resource_link), isError | 12 |
| `resources/list` | resources array, resource uri, name | 8 |
| `resources/read` | contents array, content uri, text-or-blob | 6 |
| `prompts/list` | prompts array, prompt name, arguments | 8 |
| `prompts/get` | messages array, role (user/assistant), content | 6 |

4. Each violation includes:
   - `exchange_index` — zero-based position in the scenario
   - `method` — JSON-RPC method
   - `rule` — short identifier (e.g. `tool-name-required`)
   - `message` — human-readable description
   - `path` — dot-separated JSON path (e.g. `result.tools[0].name`)
   - `severity` — `error` (MUST violation) or `warning` (SHOULD violation)

5. Returns `ComplianceReport` with per-scenario results, tracking both **passed rules** and **violations** for each exchange.

**Rule applicability:** The set of rules checked for each exchange depends on context — notifications get notification rules, error responses get envelope + error rules, success responses get envelope + method-specific rules. The `_applicable_rules()` function computes this set so that both passed and violated rules are accurately reported.

---

### Stage 8: Report Generation and Push

**Problem:** Test execution results, MCP traffic, and compliance validation data exist as separate artefacts. We need a unified report that correlates all three by scenario for consumption by dashboards and CI systems.

**Solution:** The `ReportHandler` correlates three data sources by `(feature_name, scenario_name)` and pushes a structured `ProbeReport` to the service.

| Component | File |
|-----------|------|
| `ReportHandler` | `report/report_builder.py` |
| Report models | `core/models/report.py` |

**Data sources correlated:**
1. `test-results.json` — behave JSON output (step statuses, durations, error messages, data tables)
2. `mcp-traffic.json` — recorded MCP request/response exchanges
3. `ComplianceReport` — per-scenario compliance validation results with per-exchange passed rules and violations

**Report structure:**

```
ProbeReport
├── project_code, timestamp, spec_version
├── summary_test_passed (bool)
├── mcp_compliant (bool)
├── total_features, total_scenarios, passed_scenarios, failed_scenarios
└── feature_reports[]
    ├── feature_name, summary_test_passed, mcp_compliant, duration
    └── scenarios[]
        ├── scenario_name, status (passed/failed/skipped/errored)
        ├── steps[]
        │   ├── name, status, error_message
        │   └── data_table (headings, rows)
        ├── compliance
        │   ├── mcp_compliant (bool)
        │   ├── total_exchanges
        │   └── violations[]
        └── exchanges[]
            ├── method, type, request, response, message
            ├── passed_rules[]
            └── violations[]
```

**Push:** The report is POSTed to `POST /api/reports/{project_code}` on the mcp-probe-service. The service returns a `report_id` which is printed as a URL for viewing. Push failures are logged as warnings, not fatal errors.

---

### Stage 9: Feature Upload

**Problem:** Features should be cached for subsequent runs to avoid unnecessary regeneration.

**Solution:** Upload all storable files from the `features/` directory to the service, keyed by `server_id`.

| Storable extensions | `.feature`, `.py`, `.json`, `.txt`, `.cfg`, `.ini`, `.toml` |
|---------------------|------|
| Excluded files | `mcp-traffic.json`, `test-results.json`, `__pycache__/` |

The stored features can be retrieved on subsequent runs (Stage 0) to skip the entire generation phase.

---

## Prebuilt Test Scaffolding

The prebuilt scaffolding is the runtime component that actually executes the generated tests. It is served by `mcp-probe-service` and written into the target repository's `features/` directory.

### Architecture

```
{repo_root}/features/
├── environment.py          ← Behave lifecycle hooks + traffic recording
├── requirements.txt        ← Test dependencies
├── helper/
│   ├── __init__.py
│   └── mcp_client.py       ← MCP client for BDD tests (with traffic recording)
└── steps/
    └── steps.py             ← Prebuilt + auto-generated step implementations
```

### MCPClient (`helper/mcp_client.py`)

A self-contained MCP client designed specifically for BDD test environments.

**Design principles:**
- Uses the lower-level `mcp.client.session.ClientSession` approach (not FastMCP's `Client`) for maximum control over request/response capture
- No LLM dependencies — purely deterministic MCP protocol interactions
- Full call logging via `call_log` for integration test assertions
- Error state capture via `last_is_error` (from MCP `CallToolResult.isError`) and `last_content_type` (from resource MIME metadata)
- **Traffic recording**: Captures raw JSON-RPC request/response exchanges for compliance validation

**Lifecycle:**
1. `start()` — Parses server command, spawns subprocess via `StdioServerParameters`, establishes `ClientSession`, calls `initialize()`
2. MCP calls — `call_tool()`, `read_resource()`, `get_prompt()`, `list_resources()`, `list_prompts()`
3. `stop()` — Closes the `AsyncExitStack`, shutting down the subprocess

**Error handling strategy:**
- `call_tool()` captures `isError` from `CallToolResult` but does NOT raise on MCP-level tool errors — the response text is returned so assertion steps can inspect it
- Only transport/protocol errors raise exceptions
- Both success and error responses are logged in `call_log`

### Prebuilt Steps (`steps/steps.py`)

All steps follow the **dual error capture pattern**:

```python
@when('the MCP Client calls the tool "{tool_name}" with parameters')
def step_when_call_tool(context, tool_name):
    _reset_response_state(context)       # Clear previous response
    try:
        params = _parse_params_from_table(context.table)
        context.response = context.loop.run_until_complete(
            context.mcp_client.call_tool(tool_name, params)
        )
        context.is_error = context.mcp_client.last_is_error
    except Exception as exc:
        _capture_error(context, exc)      # Sets response, error, is_error
```

Every When step always sets:
- `context.response` — string (even on exception)
- `context.error` — `Exception` or `None`
- `context.is_error` — `bool` (from MCP `isError` flag or exception)
- `context.response_content_type` — string or `None` (resource reads only)

**Step categories implemented:**

| Category | Steps | Count |
|----------|-------|-------|
| Setup | `Given the MCP Client is initialized and connected...` | 1 |
| Direct Actions | `When ... calls the tool`, `reads the resource`, `gets the prompt` (with/without params) | 5 |
| Saved-Context Actions | `When ... with saved parameters`, `with URI from saved`, `with saved arguments` | 3 |
| Context Variables | `Then I save the response field`, `I save the full response`, `I construct the value` | 3 |
| Success/Failure | `response should be successful`, `should be a failure` | 2 |
| Error Assertions | `should contain an error`, `error message should indicate` | 2 |
| Key Assertions | `should contain "{key}"`, `should contain "{key}" with value` (str + int) | 3 |
| Key Comparison | `response key should equal saved variable` | 1 |
| Field Assertions | `field should be` (str, int, null, `[]`, json) | 5 |
| Other | `content type should be`, `should contain prompt messages` | 2 |
| Elicitation | `next elicitation response will accept/decline/cancel`, `elicitation request should have been received`, `elicitation message should contain` | 5 |
| Sampling | `sampling request should have been received` | 1 |
| Roots | `MCP Client has roots`, `sends roots list changed`, `roots list request should have been received` | 3 |
| **Total** | | **36** |

### Context Variable Chaining

For integration tests, the prebuilt steps support explicit data chaining between MCP calls via saved context variables:

```gherkin
@chain-of-calls
Scenario: Check out a book then verify inventory
  When the MCP Client calls the tool "checkout_book" with parameters
    | parameter | value       |
    | book_id   | B001        |
    | user_name | Alice       |
  Then the response should be successful
  And I save the response field "book_id" as "checked_out_id"
  When the MCP Client calls the tool "return_book" with saved parameters
    | parameter | saved_variable   |
    | book_id   | checked_out_id   |
  Then the response should be successful
```

The `context.saved` dictionary persists across steps within a scenario and is reset in `before_scenario`.

### Environment Hooks (`environment.py`)

| Hook | Purpose |
|------|---------|
| `before_all` | Creates `asyncio` event loop, sets `context.loop`, initializes traffic recording |
| `before_scenario` | Resets `context.response`, `context.error`, `context.is_error`, `context.response_content_type`, `context.saved` |
| `after_scenario` | Stops MCP client subprocess, records scenario traffic, clears `context.mcp_client` |
| `after_all` | Writes `mcp-traffic.json`, closes event loop |

---

## mcp-probe-service

A Dockerised FastAPI backend providing four services:

### 1. ChromaDB Code Search

Provides semantic search over the target server's codebase, used during feature generation to give the LLM relevant code context.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/codebase/index` | POST | Upsert code entities into ChromaDB |
| `/api/codebase/query` | POST | Semantic search (query text → nearest code entities) |
| `/api/codebase/status` | GET | Entity count |
| `/api/codebase` | DELETE | Clear all indexed data |

### 2. Prebuilt Test Scaffolding

Serves the prebuilt test framework files that are written into the target repository.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/prebuilts` | GET | Returns all `.py` files and `requirements.txt` dependencies |

### 3. Feature Storage

Persists generated feature files so subsequent runs can skip the generation phase.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/features/{server_id}` | GET | Retrieve stored features (returns `files` + `dependencies`) |
| `/api/features/{server_id}` | PUT | Store features (uploads all storable files + dependencies) |

### 4. Report Storage

Stores probe reports for viewing and historical tracking.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/reports/{project_code}` | POST | Store a probe report (returns `report_id`) |
| `/project/{project_code}/report/{report_id}` | GET | View a probe report |

### Infrastructure

- Docker image: `ghcr.io/rumethj/mcp-probe-service:latest`
- Port: 8080
- Persistent ChromaDB storage at `/app/data` (backed by PVC in Kubernetes)
- Prebuilt files served from `/app/prebuilts`

---

## Key Problems and Solutions

### Problem 1: LLM generates non-deterministic step wordings

**Challenge:** Even with the canonical step library in the prompt, LLMs often generate slight variations like "the response contains" instead of "the response should contain".

**Solution (multi-layered):**
1. **Single source of truth:** `core/canonical_steps.py` defines every step exactly once — both the validator patterns and the LLM prompt are derived from the same list.
2. **Prompt-level:** The canonical step library is rendered via `render_step_library_prompt()` and appended to every generation prompt with "USE THESE EXACTLY".
3. **Step reuse tracking:** As features are generated sequentially, extracted step patterns from each feature are fed into subsequent generation prompts.
4. **Text normalization:** The `GherkinFormatter` applies regex-based `NORMALIZATION_RULES` to fix known variations, plus structural fixes (table headers, keyword chains, `{variable}` → saved parameters).
5. **Canonical validation:** The `FeatureValidator` checks every step against compiled regex patterns and auto-fixes those that can be normalised.
6. **Step deduplication:** The `StepImplementationGenerator` uses AST-based pattern extraction and flexible `patterns_match()` to avoid generating duplicate implementations.
7. **Duplicate filtering:** Generated step code is AST-parsed and functions whose patterns already exist are removed before appending.

### Problem 2: Error-case scenarios fail silently

**Challenge:** When an MCP tool call raises an exception, `context.response` was never set, so subsequent `Then` assertion steps had nothing to check.

**Solution:** Dual error capture pattern. Every `When` step wraps the MCP call in `try/except`, always setting `context.response` (even to `str(exc)`), `context.error`, and `context.is_error`. MCP-level errors (`isError=True`) are captured without raising. This allows error-case scenarios to assert on error content:

```gherkin
When the MCP Client calls the tool "checkout_book" with parameters
  | parameter | value     |
  | book_id   | INVALID   |
  | user_name | Alice     |
Then the response should contain an error
And the error message should indicate "not found"
```

### Problem 3: Integration tests require LLM at runtime (non-deterministic)

**Challenge:** Integration tests used `process_query()` which routed through an LLM to decide which tools to call. This made tests flaky and required API keys during execution.

**Solution:** Replace LLM-driven workflows with explicit MCP call chaining via context variables. The `context.saved` dictionary allows passing data between sequential MCP calls deterministically. Step patterns:

- `Then I save the response field "{field}" as "{variable}"`
- `Then I save the full response as "{variable}"`
- `Then I construct the value "{template}" and save as "{variable}"`
- `When the MCP Client calls the tool "{tool_name}" with saved parameters`
- `When the MCP Client reads the resource with URI from saved "{variable}"`

### Problem 4: Content type assertions are unreliable

**Challenge:** The content type step guessed `application/json` vs `text/plain` by attempting `json.loads()`.

**Solution:** The `MCPClient.read_resource()` captures the actual MIME type from MCP content item metadata into `last_content_type`. The assertion step checks this metadata first, falling back to JSON inference only when metadata is unavailable.

### Problem 5: Ensuring universal MCP server coverage

**Challenge:** How do we ensure the step library covers test scenarios for *any* MCP server, not just the test server?

**Solution:** The step library is designed around MCP protocol primitives, not server-specific behavior:
- Every MCP tool call goes through `call_tool()` regardless of what the tool does
- Every resource read goes through `read_resource()` regardless of the content
- Assertions are generic (JSON field checks, error detection, content type) not domain-specific
- The LLM generates domain-specific parameter values during planning/generation, but the step patterns are server-agnostic
- The canonical step library includes MCP 2025-11-25 client features (elicitation, sampling, roots) for servers that use advanced protocol capabilities

### Problem 6: LLM hallucinates non-existent primitives

**Challenge:** The LLM sometimes generates scenarios that reference tools, prompts, or resources not discovered from the server.

**Solution:** Post-generation primitive reference validation. The `GherkinFeatureGenerator._validate_primitive_references()` method regex-scans the generated Gherkin for tool names, resource URIs, and prompt names, cross-references them against the discovery result, and strips scenarios with hallucinated primitives via `_strip_invalid_scenarios()`. Resource URI mismatches are excluded from stripping because the LLM legitimately generates non-existent URIs for negative/error-case test scenarios.

### Problem 7: LLM uses `{variable}` references in direct parameter tables

**Challenge:** When generating integration test scenarios, the LLM sometimes writes `{saved_var}` in a "with parameters" step's value column, mixing up direct and saved parameter patterns.

**Solution:** The `StepNormalizer._fixup_saved_param_table()` method detects `{variable}` patterns in parameter tables, converts the step text from "with parameters" to "with saved parameters", renames the `value` column header to `saved_variable`, and strips the curly braces from variable references.

### Problem 8: Test data hallucination

**Challenge:** The LLM generates test data (parameter values, IDs, etc.) that doesn't match the server's actual data model, leading to false test failures.

**Solution:** The `test_data` configuration field allows the server developer to provide a manifest of valid/invalid test values. When present, this manifest is injected into every generation prompt with the instruction "You MUST use these exact values instead of inventing your own."

---

## Data Flow Diagram

```
mcp-probe-service-properties.json
           │
           ▼
    ┌─────────────┐
    │  ProbeConfig │  server_command, transport, service_url,
    │              │  test_env, test_data, features_dir
    └──────┬──────┘
           │
           ├──────── Feature cache check (Stage 0) ──┐
           │         GET /api/features/{server_id}    │
           │                                          │ (if cached → skip to execution)
           ▼                                          │
    ┌─────────────┐     stdio      ┌─────────────────┐
    │  MCPSession  │ ◄──────────► │  Target MCP      │
    └──────┬──────┘               │  Server           │
           │                       └─────────────────┘
           ▼
    ┌─────────────┐                ┌─────────────────┐
    │ MCPDiscoverer│                │  ASTIndexer      │
    └──────┬──────┘                └────────┬────────┘
           │                                │
           ▼                                ▼
    DiscoveryResult                  CodebaseIndex
    (server_info, tools,             (entities, hashes)
     resources, prompts)                    │
           │         ┌──────────────┐       │
           │         │ mcp-probe-   │◄──────┘
           │         │ service      │  POST /api/codebase/index
           │         │ (ChromaDB)   │
           │         └──────┬───────┘
           │                │ POST /api/codebase/query
           ▼                ▼
    ┌─────────────┐   Code Context
    │   Planner   │        │
    │   (LLM)     │        │
    └──────┬──────┘        │
           │               │
           ▼               ▼
    ScenarioPlan[]   ┌──────────────────┐
           │         │ GherkinFeature   │
           │─────────│ Generator (LLM)  │◄── test_data manifest
                     └────────┬─────────┘
                              │
                              ▼
                     .feature files
                              │
                     ┌────────┴─────────┐
                     │  GherkinFormatter │  Normalization + structural fixes
                     └────────┬─────────┘
                              │
                     ┌────────┴─────────┐
                     │ FeatureValidator  │  Canonical compliance (auto-fix)
                     └────────┬─────────┘
                              │
                              ▼
                     GherkinFeatureCollection
                              │
               ┌──────────────┴──────────────┐
               │ StepImplementationGenerator  │
               │ (LLM + AST deduplication     │
               │  + duplicate filtering)      │
               └──────────────┬───────────────┘
                              │
                     Prebuilt steps + generated steps
                              │
                     ┌────────┴─────────┐
                     │   TestExecutor    │  uv venv + behave (per feature)
                     └────────┬─────────┘
                              │
                              ▼
                     TestExecutionResult + mcp-traffic.json
                              │
                     ┌────────┴─────────┐
                     │ ComplianceValid.  │  MCP 2025-11-25 spec rules
                     └────────┬─────────┘
                              │
                              ▼
                     ComplianceReport
                              │
                     ┌────────┴─────────┐
                     │  ReportHandler    │  Correlate + push to service
                     └────────┬─────────┘
                              │
                              ▼
                     ProbeReport → POST /api/reports/{project_code}
                              │
                     ┌────────┴─────────┐
                     │  Feature Upload   │  PUT /api/features/{server_id}
                     └──────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| CLI | Typer + Rich | Command-line interface with progress indicators, tables, and panels |
| Models | Pydantic v2 | Data validation and serialization throughout the pipeline |
| LLM | Gemini 2.5 Flash (via LangChain) | Test planning, feature generation, step generation |
| MCP SDK | `mcp` Python package | MCP client sessions and protocol handling |
| Gherkin Parsing | `gherkin-official` | Official Gherkin parser for validation and AST conversion |
| BDD Framework | `behave` | Test execution at runtime |
| Code Search | ChromaDB | Vector similarity search over indexed codebase |
| HTTP Client | `httpx` (async) | Communication with mcp-probe-service |
| HTTP Backend | FastAPI + Uvicorn | mcp-probe-service API |
| Package Mgmt | `uv` | Fast venv creation and package installation |
| Containerisation | Docker | mcp-probe-service deployment |
| CI/CD | Tekton Pipelines | Kubernetes-native pipeline integration |
| Publishing | GitHub Actions + PyPI | Package distribution via trusted OIDC publishing |

---

## Configuration

The target MCP server must provide a `mcp-probe-service-properties.json` file at its repository root:

```json
{
  "project_code": "library-server",
  "server_command": "uv run server.py",
  "transport": "stdio",
  "service_url": "http://localhost:8080",
  "test_env": {
    "INJECT_MCP_DEFECT": ""
  },
  "test_data": {
    "valid_book_ids": ["B001", "B002", "B003", "B004"],
    "invalid_book_id": "B999",
    "valid_genres": ["Classic", "Science Fiction", "Mystery", "Romance"]
  },
  "features_dir": null
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `project_code` | Yes | Identifier for the project (also used as `server_id` for feature caching) |
| `server_command` | Yes | Shell command to start the MCP server |
| `transport` | Yes | Transport type (`stdio`) |
| `service_url` | Yes | URL of the mcp-probe-service instance |
| `test_env` | No | Environment variables injected into the server process during discovery and test execution |
| `test_data` | No | Test data manifest — arbitrary key-value pairs injected into LLM prompts to provide valid/invalid test values and prevent hallucinated data |
| `features_dir` | No | Relative path override for the features output directory (defaults to `features` under the repository root) |

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--generate-new` | `False` | Force regeneration of test files, ignoring cached features |
| `--debug` | `False` | Enable verbose debug logging to `mcp-probe.log` |

---

## CI/CD Integration

### Tekton Pipeline (Kubernetes)

MCP-Probe provides ready-to-use Tekton manifests for Kubernetes-native CI integration:

```
ci-integration/
├── mcp-probe-service.yaml    ← Deployment + Service + PVC for mcp-probe-service
├── pipeline.yaml             ← Tekton Pipeline (clone → run-mcp-probe-pilot)
├── pipelinerun.yaml          ← PipelineRun trigger
├── tasks.yaml                ← Tekton Tasks (clone-repo, run-mcp-probe-pilot)
└── secrets.yaml              ← Kubernetes Secret for GEMINI_API_KEY
```

**Pipeline stages:**
1. `clone-repo` — Clones the target MCP server repository using `alpine/git`
2. `run-mcp-probe-pilot` — Installs `mcp-probe-pilot` from PyPI and runs the full pipeline against the cloned repo

**mcp-probe-service deployment:** A Kubernetes Deployment with a PVC-backed ChromaDB volume, exposed as an internal ClusterIP Service on port 8080.

### GitHub Actions (PyPI Publishing)

The `publish.yaml` workflow triggers on version tags (`v*.*.*`) or manual dispatch, builds the package with `python -m build`, and publishes to PyPI using OIDC trusted publishing (no API tokens needed).

---

## Test Target: mcp-probe-test-server-library

The reference MCP server used for development and validation of the framework.

**Domain:** Simple Library Manager with a hardcoded book catalog.

| Primitive | Name | Description |
|-----------|------|-------------|
| Tool | `checkout_book` | Check out a book (requires `book_id`, `user_name`; marks book unavailable) |
| Tool | `return_book` | Return a checked-out book (requires `book_id`; marks book available) |
| Resource | `library://catalog/inventory` | Returns the complete library catalog as formatted JSON |
| Prompt | `recommend_book_by_genre` | Multi-turn prompt for book recommendation by genre (requires `genre` argument) |

**Catalog data:** Four hardcoded books: The Great Gatsby (Classic), Dune (Sci-Fi), Murder on the Orient Express (Mystery, unavailable), Pride and Prejudice (Romance).

**Defect injection:** The `INJECT_MCP_DEFECT` environment variable activates intentional protocol-level faults via a `TransportWrapper` that intercepts every outgoing JSON-RPC `SessionMessage`, converts it to a plain dict, passes it through `defect_injector.apply_defect`, and writes the (possibly mutated) payload directly to stdout — bypassing the SDK's Pydantic serialisation so that deliberately invalid JSON-RPC can be emitted. This tests the compliance validator's ability to detect spec violations.

---

## Testing Strategy

### Unit Tests

Per-module unit tests in `tests/unit/`:

| Test File | Module Under Test |
|-----------|------------------|
| `test_discoverer.py` | `discover/discoverer.py` |
| `test_ast_indexer.py` | `discover/ast_indexer.py` |
| `test_planner.py` | `plan/planner.py` |
| `test_gherkin_formatter.py` | `generate/gherkin_formatter.py` |
| `test_feature_validator.py` | `validate/validator.py` |
| `test_step_implementation_generator.py` | `generate/step_implementation_generator.py` |
| `test_executor.py` | `execute/executor.py` |
| `test_compliance_validator.py` | `compliance_engine/validator.py` |
| `test_report_builder.py` | `report/report_builder.py` |

### Integration Tests

Cross-module integration tests in `tests/integration/`:

| Test File | Pipeline Stages Tested |
|-----------|----------------------|
| `test_discoverer_planner.py` | Discovery → Planning |
| `test_planner_generator.py` | Planning → Generation |
| `test_generator_formatter.py` | Generation → Formatting |
| `test_formatter_validator.py` | Formatting → Validation |
| `test_formatter_step_generator.py` | Formatting → Step Implementation |
| `test_executor_compliance.py` | Execution → Compliance Validation |
| `test_compliance_report.py` | Compliance → Report Building |
| `test_e2e_contracts.py` | End-to-end contract tests |

**Test framework:** pytest + pytest-asyncio with `asyncio_mode = "auto"`.

---
