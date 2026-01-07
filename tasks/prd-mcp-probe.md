# Product Requirements Document: MCP-Probe-Pilot

> **Automated Testing Framework for MCP Server Validation**

---

## 1. Introduction / Overview

### Problem Statement

The Model Context Protocol (MCP) enables AI applications to connect to external tools and data sources through a standardized client-server architecture. However, MCP adoption has outpaced testing tooling—no systematic automated testing framework exists for validating MCP server correctness.

Existing tools have critical limitations:

| Tool | Limitation |
|------|------------|
| MCP Inspector | Manual debugging only—no automation |
| MCP Eval | No CI/CD integration |
| MCP-RADAR, MCPBench, etc. | Test the LLM/Agent, not the server |

### Solution

**MCP-Probe-Pilot** is an automated testing framework that validates MCP server correctness by treating the server as the System Under Test (SUT) with deterministic, reproducible test execution.

**Key Innovation:** Existing frameworks evaluate whether agents can *use* MCP servers correctly. MCP-Probe-Pilot inverts this—it evaluates whether servers *behave* correctly, using a deterministic client as the test fixture.

| Traditional Approach | MCP-Probe-Pilot Approach |
|---------------------|-------------------|
| Agent = SUT | Server = SUT |
| Server = static fixture | Agent/Client = static fixture |
| Task fails → blame Agent | Task fails → blame Server |

---

## 2. Goals

### Primary Goals

1. **Validate Protocol Compliance** — Automatically detect any MCP server response that deviates from the JSON-RPC or MCP schema specification
2. **Enable Deterministic Functional Testing** — Execute reproducible tests with identical pass/fail results across runs (zero stochastic variation)
3. **Test Error Handling** — Verify servers return proper JSON-RPC error codes for malformed inputs instead of crashes or stack traces
4. **Evaluate Boundary Conditions** — Test incorrect parameter types, missing arguments, and edge cases
5. **Provide CI/CD-Compatible Execution** — Run in any headless environment with human-readable HTML reports

### Secondary Goals

6. **Infer Tool Dependencies** — Automatically detect operation ordering requirements (e.g., `auth_login` → `get_data`)
7. **Support AI-Assisted Test Generation** — Use LLM to generate initial test cases, then save as deterministic fixtures
8. **Provide Development Velocity** — Enable developers to validate servers before connecting to live AI agents

---

## 3. User Stories

### As a MCP Server Developer

- **US-1:** I want to run automated tests against my server so that I can catch schema violations before deployment
- **US-2:** I want to see which of my tools have dependency requirements so that I can document them correctly
- **US-3:** I want to know if my error handling returns proper JSON-RPC codes so that clients receive meaningful errors
- **US-4:** I want human-readable reports showing exactly what failed so that I can fix issues quickly

### As a DevOps Engineer

- **US-5:** I want to integrate MCP server testing into our CI pipeline so that we catch regressions automatically
- **US-6:** I want CLI-based execution that works in any environment so that I'm not locked to specific platforms
- **US-7:** I want test results in a standard format so that I can integrate with existing dashboards

### As a QA Engineer

- **US-8:** I want to fuzz test server inputs so that I can find edge cases the developer didn't consider
- **US-9:** I want reproducible test cases so that I can reliably recreate failures
- **US-10:** I want to distinguish between graceful failures and critical failures so that I can prioritize bug fixes

---

## 4. Functional Requirements

### 4.1 Test MCP Server (Development Target)

| ID | Requirement |
|----|-------------|
| FR-1.1 | The system must include a custom Python MCP server for testing purposes |
| FR-1.2 | The test server must support injectable defects (schema violations, logic errors, unhandled exceptions) |
| FR-1.3 | The test server must implement all MCP server primitives: Tools, Resources, Prompts |
| FR-1.4 | The test server must have configurable defect modes that can be enabled/disabled per test run |
| FR-1.5 | Defect categories must include: missing required fields, wrong types, malformed URIs, incorrect return values, crashes, timeouts |

### 4.2 Discovery Stage

| ID | Requirement |
|----|-------------|
| FR-2.1 | The system must connect to any MCP server via stdio or HTTP transport |
| FR-2.2 | The system must discover all available tools, resources, and prompts from a server |
| FR-2.3 | The system must extract tool schemas (parameters, types, descriptions) |
| FR-2.4 | The system must infer tool dependencies by analyzing tool descriptions and parameter relationships |
| FR-2.5 | The system must construct an Operation Dependency Graph (ODG) representing tool execution order |

### 4.3 Compliance Engine

| ID | Requirement |
|----|-------------|
| FR-3.1 | The system must validate all server responses against JSON-RPC 2.0 specification |
| FR-3.2 | The system must validate all server responses against MCP schema specification |
| FR-3.3 | The system must auto-flag any response deviating from schema (missing fields, wrong types) |
| FR-3.4 | The system must achieve 100% detection rate for injected schema errors |
| FR-3.5 | The system must validate URI formats in resource identifiers |
| FR-3.6 | The system must operate as middleware, intercepting all request/response pairs |

### 4.4 Test Case Generator

| ID | Requirement |
|----|-------------|
| FR-4.1 | The system must generate test cases for each discovered tool |
| FR-4.2 | The system must generate single-turn test cases (one tool call) |
| FR-4.3 | The system must generate multi-turn test cases (tool chains based on ODG) |
| FR-4.4 | The system must support LLM-assisted test generation for initial case synthesis |
| FR-4.5 | The system must save LLM-generated tests as deterministic fixtures (JSON/YAML) |
| FR-4.6 | The system must allow manual test case definition |
| FR-4.7 | Test fixtures must be re-executable without LLM involvement |

### 4.5 Fuzz Testing Module

| ID | Requirement |
|----|-------------|
| FR-5.1 | The system must generate fuzzed inputs based on tool parameter schemas |
| FR-5.2 | The system must test invalid data types (string where int expected, etc.) |
| FR-5.3 | The system must test boundary values (empty strings, max integers, null values) |
| FR-5.4 | The system must test malformed JSON in tool arguments |
| FR-5.5 | The system must generate permutations of valid/invalid argument combinations |
| FR-5.6 | The system must classify results as "Graceful Failure" (proper error code) or "Critical Failure" (crash/timeout/stack trace) |

### 4.6 Test Executor

| ID | Requirement |
|----|-------------|
| FR-6.1 | The system must execute test cases as a proper MCP client |
| FR-6.2 | The system must produce identical pass/fail results across multiple runs |
| FR-6.3 | The system must support client-side MCP primitives: Sampling, Roots, Elicitation |
| FR-6.4 | The system must handle server timeouts with configurable thresholds |
| FR-6.5 | The system must capture full request/response pairs for debugging |
| FR-6.6 | The system must execute tests in deterministic order |

### 4.7 Report Generator

| ID | Requirement |
|----|-------------|
| FR-7.1 | The system must generate human-readable HTML test reports |
| FR-7.2 | Reports must include: pass/fail summary, failure details, timing information |
| FR-7.3 | Reports must categorize failures by type (schema violation, functional error, crash, timeout) |
| FR-7.4 | Reports must include the actual request/response data for failed tests |
| FR-7.5 | The system must support JSON output for programmatic consumption |
| FR-7.6 | Reports must be viewable without external dependencies (self-contained HTML) |

### 4.8 CLI Interface

| ID | Requirement |
|----|-------------|
| FR-8.1 | The system must provide a CLI for all operations |
| FR-8.2 | CLI must support: `discover`, `generate`, `run`, `report` commands |
| FR-8.3 | CLI must accept server connection parameters (transport type, address) |
| FR-8.4 | CLI must support configuration via file (YAML/TOML) |
| FR-8.5 | CLI must return appropriate exit codes (0 = all pass, non-zero = failures) |
| FR-8.6 | CLI must work in headless environments (no GUI dependencies) |

---

## 5. Non-Goals (Out of Scope)

The following are explicitly **not** part of this project:

| Non-Goal | Rationale |
|----------|-----------|
| Security testing (injection attacks, auth bypass) | Deprioritized for initial implementation; may be future work |
| Non-Python MCP servers | Framework targets Python implementations only |
| Testing the LLM/Agent | Existing tools cover this; MCP-Probe-Pilot tests the *server* |
| Real-time monitoring/alerting | This is a testing framework, not an observability tool |
| GUI-based test builder | CLI-first approach; visual tooling is future work |
| Performance/load testing | Focus is correctness, not throughput |

---

## 6. Design Considerations

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP-Probe-Pilot Framework                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  Discovery  │ →  │  Test Gen   │ →  │  Test Executor  │  │
│  │   Stage     │    │   Engine    │    │  (Deterministic)│  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│         │                  │                    │            │
│         ▼                  ▼                    ▼            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Compliance Engine (Middleware)              ││
│  │         Validates all payloads against MCP/JSON-RPC      ││
│  └─────────────────────────────────────────────────────────┘│
│                            │                                 │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Report Generator                      ││
│  │                  (HTML + JSON output)                    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### HTML Report Design

The HTML report should be:
- **Self-contained** — Single file with embedded CSS/JS
- **Scannable** — Summary at top, details expandable
- **Filterable** — Filter by pass/fail/category
- **Exportable** — Copy-friendly failure details

---

## 7. Technical Considerations

### Technology Stack

| Component | Recommended Technology |
|-----------|----------------------|
| Language | Python 3.10+ |
| MCP Client | `mcp` Python SDK |
| Schema Validation | `jsonschema` or `pydantic` |
| CLI Framework | `click` or `typer` |
| HTML Reports | `jinja2` templates |
| Test Fixtures | JSON or YAML files |
| LLM Integration | OpenAI API / Anthropic API (pluggable) |

### MCP Primitives to Support

**Server-Side (validate these):**
- Tools — Function calls
- Resources — Read-only data
- Prompts — Instruction templates

**Client-Side (framework must implement):**
- Sampling — Handle server requests for LLM completions
- Roots — Specify accessible directories
- Elicitation — Handle structured information requests

### Known Dependencies

- Official MCP schema definitions (for validation)
- JSON-RPC 2.0 specification
- Python MCP SDK for client implementation

---

## 8. Success Metrics

### Quantitative Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| **Fault Detection Ratio** | % of injected bugs successfully identified | ≥ 95% |
| **Schema Error Detection** | % of schema violations caught | 100% |
| **Reproducibility** | Same results across identical runs | 100% |
| **Operational Coverage** | % of server operations exercised | ≥ 90% |

### Qualitative Metrics

| Metric | Definition |
|--------|------------|
| **Report Clarity** | Developer can identify root cause from report alone |
| **Time to First Test** | < 5 minutes from install to first test run |
| **CI Integration Effort** | < 30 minutes to add to existing pipeline |

### Validation Strategy

1. **Phase 1-2:** Test against custom defect-injectable server
   - Inject known defects, verify detection rate
   - Confirm 100% schema error detection

2. **Phase 3-4:** Test against existing open-source MCP servers
   - Validate framework works with real-world implementations
   - Discover actual bugs (bonus validation)

---

## 9. Build Phases & Milestones

### Phase 1: Foundation (Weeks 1-2)

**Deliverables:**
- [ ] Project structure and dependency management
- [ ] MCP client connection handling (stdio + HTTP)
- [ ] Basic discovery stage (list tools/resources/prompts)
- [ ] Custom test MCP server with injectable defects
- [ ] CLI skeleton (`discover` command working)

**Exit Criteria:** Can connect to test server and list all primitives

---

### Phase 2: Compliance Engine (Weeks 3-4)

**Deliverables:**
- [ ] JSON-RPC 2.0 schema validation
- [ ] MCP specification schema validation
- [ ] Middleware interceptor architecture
- [ ] Fault categorization system
- [ ] Basic HTML report (compliance results only)

**Exit Criteria:** 100% detection rate for injected schema errors in test server

---

### Phase 3: Test Generation & Execution (Weeks 5-7)

**Deliverables:**
- [ ] Deterministic test executor
- [ ] Rule-based test case generator
- [ ] LLM-assisted test generation (with fixture export)
- [ ] Fuzz testing module
- [ ] Operation Dependency Graph construction
- [ ] Multi-turn test case support

**Exit Criteria:** Can generate and execute tests with 100% reproducibility

---

### Phase 4: Integration & Polish (Weeks 8-10)

**Deliverables:**
- [ ] Full CLI implementation
- [ ] Complete HTML report with filtering/export
- [ ] JSON output format
- [ ] Configuration file support
- [ ] Documentation and examples
- [ ] Testing against open-source MCP servers

**Exit Criteria:** Framework is CI-ready and documented

---

## 10. Open Questions

| ID | Question | Impact |
|----|----------|--------|
| OQ-1 | Which specific open-source MCP servers should be used for Phase 4 validation? | Test target selection |
| OQ-2 | Should the LLM provider be configurable, or should we pick one (OpenAI/Anthropic)? | Architecture decision |
| OQ-3 | What is the maximum acceptable test execution time before timeout? | Configuration defaults |
| OQ-4 | Should test fixtures be versioned separately from the framework? | Repository structure |
| OQ-5 | Is there a preference for the HTML report styling/theme? | UI design |

---

## Appendix A: Fault Categories

| Category | Examples | Detection Method |
|----------|----------|------------------|
| **Schema Violations** | Missing required fields, wrong types, malformed URIs | Compliance Engine |
| **Transport Errors** | Connection failures, timeout handling | Executor |
| **Logic Errors** | Incorrect tool behavior, wrong return values | Functional tests |
| **Error Handling Failures** | Crashes instead of error codes, exposed stack traces | Fuzz testing |
| **Boundary Failures** | Integer overflow, empty string handling | Fuzz testing |

## Appendix B: JSON-RPC Error Codes

The framework should verify servers return these standard codes:

| Code | Message | Meaning |
|------|---------|---------|
| -32700 | Parse Error | Invalid JSON |
| -32600 | Invalid Request | Not a valid request object |
| -32601 | Method Not Found | Method does not exist |
| -32602 | Invalid Params | Invalid method parameters |
| -32603 | Internal Error | Internal JSON-RPC error |

---

*Document Version: 1.0*  
*Created: January 2026*  
*Status: Draft - Pending Review*

