# Methodology (Distilled)

## Core Design Philosophy

- **SUT (System Under Test)**: MCP Server
- **Test Fixture**: Deterministic client (minimal/no stochastic variation)
- **Scope**: Python MCP servers only
- **Architecture**: Two-stage process (discovery → test execution)

---

## Requirements (Objectives + Acceptance Criteria)

### 1. Define Functional Correctness

**Build:** Fault categorization system

**Acceptance Criteria:**
- [ ] Identify specific, measurable fault categories (schema violations, functional failures, etc.)
- [ ] Define attributes for each fault category

---

### 2. Specification-Based Compliance Engine

**Build:** Middleware interceptor that validates payloads against official MCP/JSON-RPC schema

**Acceptance Criteria:**
- [ ] Auto-flag any response deviating from JSON-RPC or MCP schema
- [ ] 100% detection rate for injected schema errors (missing required fields, malformed URIs)

---

### 3. Deterministic Functional Testing

**Build:** Hybrid testing system for test case synthesis and execution

**Acceptance Criteria:**
- [ ] Infer tool dependencies (e.g., `auth_login` must precede `get_data`)
- [ ] Autonomously generate re-executable test cases (single-turn and multi-turn)
- [ ] Produce identical pass/fail results across multiple runs (zero stochastic variation)

---

### 4. Error Handling & Boundary Condition Testing

**Build:** Fuzz testing module

**Techniques:**
- Inject invalid data types
- Boundary values (empty strings, integer overflows)
- Malformed JSON in tool arguments

**Acceptance Criteria:**
- [ ] Generate test cases with permutations of valid/invalid arguments
- [ ] Distinguish "Graceful Failures" (correct error codes) vs. "Critical Failures" (crash/timeout)
- [ ] Verify servers return standard error codes, not stack traces or crashes

---

### 5. CI/CD Integration

**Build:** Cloud-native test runner with reporting

**Acceptance Criteria:**
- [ ] Execute in headless CI environment
- [ ] Output human-readable Test Incident Reports (pass/fail summaries)
- [ ] Compatible with standard visualization dashboards

---

## Build Iterations

| Phase | Deliverable |
|-------|-------------|
| **1. Foundation** | Project architecture + connection handling |
| **2. Compliance** | Schema Validation Engine |
| **3. Generation & Execution** | AI-driven test case generator |
| **4. Integration** | CI/CD pipeline + reporting |

---

## Evaluation Strategy

### Test Targets

1. **Custom Server**: Python MCP server with intentional defects injected (logic errors, broken schemas, unhandled exceptions)
2. **Reference Implementation**: Existing open-source MCP server

### Success Metrics

| Metric | Definition |
|--------|------------|
| **Fault Detection Ratio** | % of actual bugs (injected or existing) successfully identified |
| **Answer Relevance** | Similarity between server output and expected "ground truth" |
| **Answer Format Compliance** | Binary: Can LLM parse the output structure correctly? |

