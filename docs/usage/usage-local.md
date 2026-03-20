# Usage - Local

## Prerequisites

- Python
- Gemini API key(GEMINI_API_KEY) should be set in the environment variables.
- Prepared your MCP server source code for MCP Probe: [Preparing MCP Server Source Code](prepare-mcp-server.md)

## 1. Build & Start Up mcp-probe-service

```bash
cd mcp-probe-service
docker compose up --build mcp-probe-service
```

OR install from direct docker image

```bash
docker pull ghcr.io/rumethj/mcp-probe-service:latest
docker run -d --name mcp-probe-service -p 8080:8080 ghcr.io/rumethj/mcp-probe-service:latest
```

## 2. Install mcp-probe-pilot cli tool

First create a virtual environment
```bash
uv venv
```

Install the cli
```bash
uv pip install mcp-probe-pilot
```

## 3. Set Gemini API key

```bash
export GEMINI_API_KEY=<api_key>
```

## 4. Run mcp-probe-pilot

```bash
mcp-probe-pilot <mcp-server-source-code-path> [--generate-new]
```

- \<mcp-server-source-code-path\>: Path to the MCP server source code.
- --generate-new: Generate a new test suite. (Optional: If not provided, the pilot will use the prevoisly generated test suites if any)

Example:
```bash
mcp-probe-pilot /path/to/your/mcp/server/source/code/ --generate-new
```