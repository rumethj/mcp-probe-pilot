# MCP-Probe: Project Specification

> **One-liner:** An automated testing framework that validates MCP server correctness, treating the server as the system under test with deterministic, reproducible test execution.

---

## Problem

LLMs connect to external tools/data via the **Model Context Protocol (MCP)** — a client-server architecture where AI apps (clients) connect to MCP servers exposing data/services.

**The gap:** MCP adoption has outpaced testing tooling.

| Existing Tool | Limitation |
|---------------|------------|
| MCP Inspector | Manual debugging — no automation |
| MCP Eval | No CI/CD integration |
| MCP-RADAR, MCPBench, etc. | Test the *LLM/Agent*, not the *server* |

**No framework exists to validate MCP server correctness.**

---

## What Makes This Different

Existing frameworks treat the server as static ground truth and evaluate the agent:
- Task fails → blame the Agent

**This project inverts that relationship:**
- Agent/input = static fixture (deterministic)
- Server = system under test (SUT)
- Task fails → blame the Server

---

## MCP Primitives to Validate

### Server-Side
| Primitive | Function |
|-----------|----------|
| **Tools** | Functions LLM can call (write DB, call APIs, modify files) |
| **Resources** | Read-only data sources for context |
| **Prompts** | Pre-built instruction templates |

### Client-Side (framework must support)
| Primitive | Function |
|-----------|----------|
| **Sampling** | Server requests LLM completions through client |
| **Roots** | Client specifies accessible directories |
| **Elicitation** | Server requests structured user information |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP-Probe Framework                      │
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
│  │              (CI-compatible, human-readable)             ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   MCP Server    │
                    │ (Python - SUT)  │
                    └─────────────────┘
```

**Scope:** Python MCP servers only

---

## Components to Build

### 1. Compliance Engine
Middleware interceptor validating payloads against MCP/JSON-RPC schema.

**Must:**
- Auto-flag any response deviating from schema
- Achieve 100% detection for injected schema errors (missing fields, malformed URIs)
- Ensure interoperability across different MCP client implementations

---

### 2. Test Case Generator
AI-driven system that synthesizes executable test cases.

**Must:**
- Infer tool dependencies (`auth_login` → `get_data`)
- Generate single-turn and multi-turn test cases
- Produce deterministic, re-executable tests

---

### 3. Fuzz Testing Module
Boundary condition and error handling validation.

**Techniques:**
- Invalid data types
- Boundary values (empty strings, integer overflows)
- Malformed JSON

**Must:**
- Generate permutations of valid/invalid arguments
- Distinguish "Graceful Failures" (correct error codes) vs. "Critical Failures" (crash/timeout)

---

### 4. Test Executor
Deterministic execution engine acting as MCP client.

**Must:**
- Zero stochastic variation across runs
- Identical pass/fail results on re-execution

---

### 5. Report Generator
Cloud-native, CI-compatible output with human-readable summaries.

**Must:**
- Run in headless CI environment (e.g., Tekton, GitHub Actions)
- Output Test Incident Reports
- Compatible with visualization dashboards
- Standard output formats for pipeline integration

---

## Technical Approach

| Technique | Application |
|-----------|-------------|
| **Grey-box testing** | Partial knowledge of server internals — best results |
| **Property-based testing** | Schema/protocol validation |
| **Fuzzing** | Boundary conditions, error handling |
| **Dependency inference** | Tool chaining order (via Operation Dependency Graph construction) |
| **LLM Oracle** | Generate expected outputs for correctness validation (optional) |

---

## Build Phases

| Phase | Deliverable |
|-------|-------------|
| **1. Foundation** | Project architecture + MCP connection handling |
| **2. Compliance** | Schema Validation Engine |
| **3. Generation & Execution** | Test case generator + deterministic executor |
| **4. Integration** | CI/CD pipeline + reporting |

---

## Evaluation Strategy

### Test Targets
1. **Custom Server:** Python MCP server with injected defects (logic errors, broken schemas, unhandled exceptions)
2. **Reference Implementation:** Existing open-source MCP server

### Success Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| **Fault Detection Ratio** | % of bugs (injected or existing) successfully identified | High |
| **Answer Relevance** | Similarity to expected ground truth | High |
| **Answer Format Compliance** | Can output be parsed correctly? | 100% |
| **Reproducibility** | Same results across runs | 100% |
| **Operational Coverage** | % of server operations successfully exercised | High |
| **Code Coverage** *(optional)* | % of server source code executed by tests | Measured |

---

## Acceptance Criteria Summary

- [ ] Schema violations auto-detected (100% for injected errors)
- [ ] Tool dependencies correctly inferred
- [ ] Test cases are deterministic and re-executable
- [ ] Graceful vs. critical failures distinguished
- [ ] Runs in headless CI environment
- [ ] Human-readable test reports generated
- [ ] Zero stochastic variation in test results

---

## Fault Categories to Detect

| Category | Examples |
|----------|----------|
| **Schema Violations** | Missing required fields, wrong types, malformed URIs |
| **Transport Errors** | Connection failures, timeout handling |
| **Logic Errors** | Incorrect tool behavior, wrong return values |
| **Error Handling Failures** | Crashes instead of JSON-RPC error codes (-32700 Parse Error, -32602 Invalid Params), exposed stack traces |
| **Boundary Failures** | Integer overflow, empty string handling |

---

## Out of Scope (Explicit)

- **Security posture testing** (e.g., injection attacks, auth bypass) — mentioned in research objectives but deprioritized for initial implementation
- **Non-Python MCP servers** — framework targets Python implementations only

