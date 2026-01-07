# Literature Review (Distilled)

## MCP Architecture

### Server Primitives

| Feature | What It Does | Who Controls |
|---------|--------------|--------------|
| **Tools** | Functions the LLM can call (write DB, call APIs, modify files) | Model decides when to invoke |
| **Resources** | Read-only data sources (files, schemas, docs) for context | Application controls access |
| **Prompts** | Pre-built instruction templates for specific workflows | User selects |

### Client Primitives

| Feature | What It Does |
|---------|--------------|
| **Sampling** | Server requests LLM completions through client (enables agentic workflows) |
| **Roots** | Client specifies which directories server can access |
| **Elicitation** | Server requests structured information from users during interactions |

### Existing MCP Tooling

- **MCP Inspector**: Manual interactive debugging tool. No automation, no test reports.

---

## Relevant Testing Methodologies (from Analogous Domains)

### From RESTful API Testing

**Testing Approaches:**
- **Black-box**: Test via external interface only
- **White-box**: Test with knowledge of internals
- **Grey-box**: Hybrid approach — yields best results

**Techniques:**
- **Property-based testing**: Validate against invariant properties (good for schema validation)
- **Search-based testing**: Use metaheuristic algorithms to optimize test case generation

**Evaluation Metrics:**
- **Code Coverage**: % of source code executed by tests
- **Operational Coverage**: % of operations successfully exercised
- **Fault Detection**: Ability to trigger internal errors (binary: did it crash or not)

### From LSP Testing

- **LSPFuzz**: Grey-box fuzzer using two-stage approach:
  1. Syntax-aware mutations to generate diverse input code
  2. Context-aware fuzzing dispatching editor operations targeting specific constructs

### Fuzzing for LLM Tools (ToolFuzz)

Two detection techniques:
1. **Runtime Failure Detection**: Generate "fuzzed" natural prompts using tool documentation/source code to find breaking inputs
2. **Correctness Failure Detection**: Generate synonymous prompts, apply consistency checks, use "LLM Oracle" to judge expected vs. actual output

**Key finding**: Grey-box and white-box outperform black-box approaches.

**Limitation for MCP**: ToolFuzz doesn't cover protocol specification adherence or server-specific primitives (sampling, etc.).

---

## Existing MCP Evaluation Frameworks (and Why They Don't Solve This Problem)

| Framework | What It Evaluates | Primary Metrics |
|-----------|-------------------|-----------------|
| **MCP-RADAR** | LLM utilization efficiency | Result Accuracy, Computational Resource Efficiency |
| **MCPToolBench++** | Agent's ability to handle 4000+ tool schemas | AST Accuracy, DAG Accuracy |
| **MCPBench** | Agent reasoning with fuzzy instructions | LLM-as-Judge planning scores |
| **MCP-Universe** | Agent adaptability to dynamic environments | Execution-based success rates |

### Critical Gap

**All existing frameworks evaluate the LLM/Agent, treating the MCP server as static ground truth.**

- If task fails → blame attributed to Agent (hallucination, bad planning)
- Server is the test fixture, Agent is the subject under test

**This project requires the inverse:**

- Agent/input pattern = static fixture
- Server = subject under test
- If task fails → blame attributed to Server (logic error, schema violation, crash)

No existing framework isolates server performance as the dependent variable.

---

## Key Takeaways for Implementation

1. Use **grey-box testing** (partial knowledge of server internals)
2. Apply **property-based testing** for schema/protocol validation
3. Implement **fuzzing** for boundary condition and error handling tests
4. Define **evaluation metrics**: code coverage, operational coverage, fault detection
5. **Staticize the agent** — deterministic inputs, no LLM variability
6. Validate **server primitives**: Tools, Resources, Prompts, Sampling, Roots, Elicitation

