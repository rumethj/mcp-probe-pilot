# MCP Discovery Module

The Discovery module provides functionality to connect to MCP (Model Context Protocol) servers and discover their capabilities, including tools, resources, and prompts.

## Overview

This module is the first step in the mcp-probe-pilot testing pipeline. Before generating tests for an MCP server, we need to understand what capabilities the server exposes. The discovery module:

1. **Connects** to an MCP server via stdio transport
2. **Discovers** all available tools, resources, and prompts
3. **Returns** structured data models that can be used for test generation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCPDiscoveryClient                        │
├─────────────────────────────────────────────────────────────┤
│  connect()          - Establish stdio connection             │
│  disconnect()       - Close connection                       │
│  discover_tools()   - List all tools with schemas            │
│  discover_resources() - List resources & templates           │
│  discover_prompts() - List prompts with arguments            │
│  get_server_info()  - Get server metadata                    │
│  discover_all()     - Complete discovery in one call         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     MCP SDK (stdio)                          │
│  StdioServerParameters → stdio_client → ClientSession        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server Process                        │
│  (Started as subprocess via server_command)                  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Data Models (`models.py`)

The module defines Pydantic models for representing discovered capabilities:

| Model | Description |
|-------|-------------|
| `ToolInfo` | Information about a tool: name, description, input JSON schema |
| `ResourceInfo` | Resource URI, name, description, MIME type, template flag |
| `PromptInfo` | Prompt name, description, and list of arguments |
| `PromptArgument` | Argument name, description, required flag |
| `ServerInfo` | Server name, version, protocol version, capabilities |
| `ServerCapabilities` | Boolean flags for tools, resources, prompts, sampling, logging |
| `DiscoveryResult` | Combined result with all discovered capabilities |

### Discovery Client (`client.py`)

The `MCPDiscoveryClient` class handles the connection and discovery process.

#### Key Features

- **Async Context Manager**: Use `async with` for automatic connection management
- **Configurable Timeout**: Set timeouts for connection and operations
- **Error Handling**: Custom exceptions for connection and discovery errors
- **Environment Variables**: Pass environment variables to the server process

## Usage

### Basic Discovery

```python
import asyncio
from mcp_probe_pilot.discovery import MCPDiscoveryClient

async def main():
    async with MCPDiscoveryClient("python -m my_server") as client:
        # Discover everything at once
        result = await client.discover_all()
        
        print(f"Server: {result.server_info.name}")
        print(f"Tools: {result.tool_count}")
        print(f"Resources: {result.resource_count}")
        print(f"Prompts: {result.prompt_count}")

asyncio.run(main())
```

### Discover Specific Capabilities

```python
async with MCPDiscoveryClient("uv run my-mcp-server") as client:
    # Discover tools only
    tools = await client.discover_tools()
    for tool in tools:
        print(f"Tool: {tool.name}")
        print(f"  Description: {tool.description}")
        print(f"  Schema: {tool.input_schema}")
    
    # Discover resources
    resources = await client.discover_resources()
    for resource in resources:
        prefix = "[Template]" if resource.is_template else "[Static]"
        print(f"{prefix} {resource.uri}: {resource.description}")
    
    # Discover prompts
    prompts = await client.discover_prompts()
    for prompt in prompts:
        args = ", ".join(a.name for a in prompt.arguments)
        print(f"Prompt: {prompt.name}({args})")
```

### Manual Connection Management

```python
client = MCPDiscoveryClient(
    server_command="python -m my_server",
    server_args=["--debug"],
    env={"API_KEY": "secret"},
    timeout=60.0
)

try:
    await client.connect()
    print(f"Connected: {client.is_connected}")
    
    tools = await client.discover_tools()
    # ... use tools
    
finally:
    await client.disconnect()
```

### Using the Convenience Function

```python
from mcp_probe_pilot.discovery import create_discovery_client

async with create_discovery_client("python -m my_server") as client:
    result = await client.discover_all()
```

## How It Works

### Connection Flow

1. **Parse Command**: The `server_command` string is parsed using `shlex.split()` to separate the command from its arguments.

2. **Create Server Parameters**: `StdioServerParameters` is created with the command, args, and environment variables.

3. **Start Server Process**: `stdio_client()` starts the MCP server as a subprocess and establishes stdio communication.

4. **Initialize Session**: `ClientSession` is created and `initialize()` is called to perform the MCP handshake.

5. **Store Server Info**: The initialization response contains server metadata and capabilities, which are parsed and stored.

### Discovery Methods

Each discovery method calls the corresponding MCP protocol method:

| Method | MCP Protocol Call | Returns |
|--------|-------------------|---------|
| `discover_tools()` | `list_tools` | List of `ToolInfo` |
| `discover_resources()` | `list_resources` + `list_resource_templates` | List of `ResourceInfo` |
| `discover_prompts()` | `list_prompts` | List of `PromptInfo` |
| `get_server_info()` | (from init response) | `ServerInfo` |

### Error Handling

The module defines two custom exceptions:

- **`MCPConnectionError`**: Raised when connection to the server fails (timeout, process error, etc.)
- **`MCPDiscoveryError`**: Raised when a discovery operation fails after connection is established

All operations have timeout protection using `asyncio.wait_for()`.

## Example Output

When discovering the `mcp-probe-test-server`:

```
Server: Task Management Server
Version: None
Protocol: 2024-11-05

Capabilities:
  - Tools: True
  - Resources: True
  - Prompts: True

Tools (10):
  - auth_login: Authenticate a user and return an authentication token.
  - create_project: Create a new project. Requires authentication.
  - add_task: Add a new task to a project.
  - assign_task: Assign a task to a user.
  - update_task_status: Update a task's status.
  - query_tasks: Query tasks with optional filters.
  - delete_task: Delete a task.
  - delete_project_with_confirmation: Delete a project with user confirmation.
  - generate_task_summary: Generate an AI-powered summary of a task.
  - reset_server_state: Reset the server state to initial seed data.

Resources (7):
  [Static] system://status: Get system status including available users and projects.
  [Static] user://user_1/profile: Get profile for admin user.
  [Static] user://user_2/profile: Get profile for developer user.
  [Static] user://user_3/profile: Get profile for tester user.
  [Template] user://{user_id}/profile: Get profile information for a user.
  [Template] project://{project_id}/tasks: Get all tasks for a specific project.
  [Template] project://{project_id}/metadata: Get metadata for a specific project.

Prompts (3):
  - create_task_template(project_name, task_type): Generate a template for creating a new task.
  - project_summary(project_id): Generate a prompt for creating a project status summary.
  - task_review(task_id): Generate a prompt for reviewing a task.
```

## Integration with Test Generation

The discovery results are used by the test generators to create comprehensive test scenarios:

```python
from mcp_probe_pilot.discovery import MCPDiscoveryClient
from mcp_probe_pilot.generators import ClientTestGenerator

async def generate_tests(server_command: str):
    # Step 1: Discover server capabilities
    async with MCPDiscoveryClient(server_command) as client:
        discovery_result = await client.discover_all()
    
    # Step 2: Generate tests from discovered capabilities
    generator = ClientTestGenerator(llm_config)
    scenarios = await generator.generate_scenarios(discovery_result)
    
    return scenarios
```

## API Reference

### MCPDiscoveryClient

```python
class MCPDiscoveryClient:
    def __init__(
        self,
        server_command: str,           # Command to start the MCP server
        server_args: list[str] = None, # Additional arguments
        env: dict[str, str] = None,    # Environment variables
        timeout: float = 30.0          # Timeout in seconds
    ): ...
    
    @property
    def is_connected(self) -> bool: ...
    
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    
    async def get_server_info(self) -> ServerInfo: ...
    async def discover_tools(self) -> list[ToolInfo]: ...
    async def discover_resources(self) -> list[ResourceInfo]: ...
    async def discover_prompts(self) -> list[PromptInfo]: ...
    async def discover_all(self) -> DiscoveryResult: ...
    
    # Async context manager
    async def __aenter__(self) -> MCPDiscoveryClient: ...
    async def __aexit__(self, *args) -> None: ...
```

### DiscoveryResult

```python
class DiscoveryResult(BaseModel):
    server_info: ServerInfo
    tools: list[ToolInfo]
    resources: list[ResourceInfo]
    prompts: list[PromptInfo]
    
    @property
    def tool_count(self) -> int: ...
    @property
    def resource_count(self) -> int: ...
    @property
    def prompt_count(self) -> int: ...
    
    def get_tool(self, name: str) -> ToolInfo | None: ...
    def get_resource(self, uri: str) -> ResourceInfo | None: ...
    def get_prompt(self, name: str) -> PromptInfo | None: ...
```

## Testing

Run unit tests:
```bash
uv run pytest tests/test_discovery.py -v -m "not integration"
```

Run integration tests (requires mcp-probe-test-server):
```bash
uv run pytest tests/test_discovery.py -v -m integration
```

Run all tests:
```bash
uv run pytest tests/test_discovery.py -v
```
