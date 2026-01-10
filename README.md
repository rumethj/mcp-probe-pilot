# MCP-Probe-Pilot

Automated testing framework for validating MCP (Model Context Protocol) server correctness, protocol compliance, and functional behavior.

## Overview

MCP-Probe-Pilot is the core component of the MCP-Probe framework. It provides:

- **Test Generation**: LLM-powered generation of BDD test scenarios from server discovery and source code analysis
- **Fuzzing**: Automated generation of edge case and invalid input tests
- **Test Execution**: BDD Behave test runner with MCP protocol compliance validation
- **LLM Oracle**: Semantic assertion evaluation for complex output validation
- **Failure Classification**: Intelligent categorization of test failures
- **Report Generation**: HTML reports with detailed test results and compliance metrics

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install from source

```bash
cd mcp-probe-pilot
uv sync
```

### Install with dev dependencies

```bash
uv sync --dev
```

## Configuration

Create a `mcp-probe-service-properties.json` file in your MCP server's root directory:

```json
{
  "project_code": "my-mcp-server",
  "server_command": "python -m my_server",
  "transport": "stdio",
  "regenerate_tests": false,
  "llm_provider": "openai",
  "llm_model": "gpt-4"
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `project_code` | string | *required* | Unique identifier for the MCP server project |
| `server_command` | string | *required* | Command to start the MCP server |
| `transport` | string | `"stdio"` | Transport protocol (currently only `stdio` supported) |
| `regenerate_tests` | boolean | `false` | Force regeneration of test cases |
| `llm_provider` | string | `"openai"` | LLM provider (`openai` or `anthropic`) |
| `llm_model` | string | `"gpt-4"` | Model to use for test generation and oracle |

### Environment Variables

Set your LLM API keys as environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY="your-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-api-key"
```

## Quick Start

### 1. Initialize configuration

```bash
mcp-probe init
```

This creates a `mcp-probe-service-properties.json` template in the current directory.

### 2. Generate tests

```bash
mcp-probe generate
```

Connects to your MCP server, discovers capabilities, and generates BDD test scenarios.

### 3. Run tests

```bash
mcp-probe run
```

Executes the generated tests against your MCP server.

### 4. Generate report

```bash
mcp-probe report
```

Creates an HTML report with test results and compliance metrics.

### Full pipeline

```bash
mcp-probe full
```

Runs the complete pipeline: generate → run → report.

## CLI Commands

| Command | Description |
|---------|-------------|
| `mcp-probe init` | Create configuration file template |
| `mcp-probe generate` | Generate test cases from server discovery |
| `mcp-probe run` | Execute generated tests |
| `mcp-probe report` | Generate HTML test report |
| `mcp-probe full` | Run complete test pipeline |

### Common Options

- `--config, -c`: Path to configuration file (default: `./mcp-probe-service-properties.json`)
- `--verbose, -v`: Enable verbose output
- `--regenerate`: Force test regeneration (overrides config)

## Project Structure

```
mcp-probe-pilot/
├── src/mcp_probe_pilot/
│   ├── cli.py              # CLI entry point
│   ├── config.py           # Configuration management
│   ├── discovery/          # MCP client discovery
│   ├── generators/         # LLM-based test generators
│   ├── fuzzing/            # Fuzzing strategies
│   ├── ground_truth/       # Ground truth storage
│   ├── compliance/         # Protocol validation
│   ├── runner/             # BDD test executor
│   ├── oracle/             # LLM oracle for assertions
│   ├── results/            # Result classification
│   └── reporting/          # HTML report generation
└── tests/                  # Unit tests
```

## Development

### Running tests

```bash
uv run pytest
```

### Code formatting

```bash
uv run black src tests
uv run ruff check --fix src tests
```

### Type checking

```bash
uv run mypy src
```

## License

MIT License - see LICENSE file for details.
