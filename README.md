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
  "llm_provider": "gemini",
  "llm_model": "gemini-2.0-flash"
}
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `project_code` | string | *required* | Unique identifier for the MCP server project |
| `server_command` | string | *required* | Command to start the MCP server |
| `transport` | string | `"stdio"` | Transport protocol (currently only `stdio` supported) |
| `regenerate_tests` | boolean | `false` | Force regeneration of test cases |
| `llm_provider` | string | `"gemini"` | Default LLM provider (`openai`, `anthropic`, or `gemini`) |
| `llm_model` | string | *provider default* | Default model (defaults vary by provider) |
| `llm_temperature` | number | `0.7` | Temperature for LLM responses (0.0 to 1.0) |
| `llm_max_tokens` | number | `4096` | Maximum tokens for LLM responses |
| `generator_llm` | object | `null` | LLM config overrides for test generator component |
| `oracle_llm` | object | `null` | LLM config overrides for oracle component |

### Default Models by Provider

| Provider | Default Model |
|----------|---------------|
| `gemini` | `gemini-2.0-flash` |
| `openai` | `gpt-4` |
| `anthropic` | `claude-3-5-sonnet-20241022` |

### Component-Specific LLM Configuration

By default, all components use the top-level `llm_provider` and `llm_model` settings. You can override specific components when you need different LLM providers/models (e.g., use a faster model for test generation and a more capable model for the oracle):

```json
{
  "project_code": "my-mcp-server",
  "server_command": "python -m my_server",
  "generator_llm": {
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "temperature": 0.8
  },
  "oracle_llm": {
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.3
  }
}
```

Component LLM config options:

| Option | Type | Description |
|--------|------|-------------|
| `provider` | string | Override LLM provider for this component |
| `model` | string | Override model for this component |
| `temperature` | number | Override temperature for this component |
| `max_tokens` | number | Override max tokens for this component |

### Environment Variables

Set your LLM API keys as environment variables or in a `.env` file:

```bash
# For Gemini (Google AI)
export GEMINI_API_KEY="your-api-key"

# For OpenAI
export OPENAI_API_KEY="your-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-api-key"
```

#### Using a `.env` File

Create a `.env` file in your project root:

```env
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
```

The framework will automatically load environment variables from the `.env` file.

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
