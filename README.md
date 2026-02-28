# Getting Started

1. Set Gemini API Key

```env
GEMINI_API_KEY=<your-gemini-api-key>
```

2. Ensure that your python mcp server has mcp-probe-service-properties.json

```json
{
  "project_code": "mcp-test-server",
  "server_command": "uv run mcp-test-server",
  "transport": "stdio",
  "service_url": "http://localhost:4000"
}
```

3. Start MCP-PROBE-SERVICE

```bash
cd mcp-probe-service
docker compose up --build -d
```

4. Install mcp-probe-pilot

```bash
cd mcp-probe-pilot
pip install -e .
```

5. Run mcp-probe-pilot

```bash
mcp-probe-pilot /path/to/your/mcp/server/source/code/ --generate-new
```