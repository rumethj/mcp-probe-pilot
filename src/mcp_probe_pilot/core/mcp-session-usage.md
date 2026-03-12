# MCPSession Usage Guide

`MCPSession` is the low-level session for **all** direct communication with MCP servers in mcp-probe-pilot. It lives in `mcp_probe_pilot.core.mcp_session` and wraps the official `modelcontextprotocol/python-sdk`.

> **Naming convention:** `MCPSession` handles the protocol-level connection and operations. The name `MCPClient` is reserved for a future higher-level class that pairs an `MCPSession` with an LLM to do agentic query processing.

---

## 1. Basics — Connection Lifecycle

`MCPSession` takes a shell command string that launches the MCP server over stdio. Use it as an async context manager:

```python
import asyncio
from mcp_probe_pilot.core.mcp_session import MCPSession

async def main():
    async with MCPSession("uv run my-mcp-server") as session:
        # session is connected and ready
        tools = await session.list_tools()
        print(tools)
    # session is disconnected automatically

asyncio.run(main())
```

### Constructor parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `server_command` | `str` | *required* | Shell command to start the server (e.g. `"python -m my_server"`) |
| `env` | `dict[str, str] \| None` | `None` | Extra environment variables for the subprocess |
| `timeout` | `float` | `30.0` | Seconds to wait for any single operation |

### Manual connect / disconnect

If you cannot use `async with`, call `connect()` and `disconnect()` explicitly:

```python
session = MCPSession("uv run my-mcp-server")
await session.connect()
try:
    tools = await session.list_tools()
finally:
    await session.disconnect()
```

### Server info

After connecting, the handshake result is available:

```python
async with MCPSession("uv run my-mcp-server") as session:
    info = session.server_info
    print(info.serverInfo.name, info.serverInfo.version)
    print(info.capabilities)
```

---

## 2. Discovery — Listing Server Capabilities

Discovery is the act of asking an MCP server what it can do. `MCPSession` provides three listing methods, one per MCP primitive.

### List tools

```python
async with MCPSession(server_command) as session:
    result = await session.list_tools()
    for tool in result.tools:
        print(f"Tool: {tool.name}")
        print(f"  Description: {tool.description}")
        print(f"  Input schema: {tool.inputSchema}")
```

### List resources and resource templates

```python
async with MCPSession(server_command) as session:
    # Static resources (concrete URIs)
    resources = await session.list_resources()
    for r in resources.resources:
        print(f"Resource: {r.uri}  ({r.mimeType})")

    # URI-template resources (contain placeholders like {id})
    templates = await session.list_resource_templates()
    for t in templates.resourceTemplates:
        print(f"Template: {t.uriTemplate}")
```

### List prompts

```python
async with MCPSession(server_command) as session:
    result = await session.list_prompts()
    for prompt in result.prompts:
        args = [a.name for a in (prompt.arguments or [])]
        print(f"Prompt: {prompt.name}  args={args}")
```

### Putting it together for a discovery module

```python
from mcp_probe_pilot.core.mcp_session import MCPSession

async def discover_server(server_command: str) -> dict:
    """Run full capability discovery on an MCP server."""
    async with MCPSession(server_command) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        prompts = await session.list_prompts()

    return {
        "tools": tools.tools,
        "resources": resources.resources,
        "resource_templates": templates.resourceTemplates,
        "prompts": prompts.prompts,
    }
```

---

## 3. Direct Tool / Resource / Prompt Calls

Use these when you know exactly which tool to call, which resource to read, or which prompt to retrieve — for example inside a test step.

### Call a tool

```python
async with MCPSession(server_command) as session:
    result = await session.call_tool("auth_login", {
        "username": "admin",
        "password": "secret",
    })

    # result.content is a list of content blocks (TextContent, ImageContent, …)
    for block in result.content:
        print(block.text)

    # result.isError is True if the server reported a tool-level error
    if result.isError:
        print("Tool reported an error")
```

### Read a resource

```python
async with MCPSession(server_command) as session:
    result = await session.read_resource("file:///config.json")

    for content in result.contents:
        print(content.text)
```

### Get a prompt

```python
async with MCPSession(server_command) as session:
    result = await session.get_prompt("code_review", {
        "language": "python",
        "style": "concise",
    })

    for message in result.messages:
        print(f"[{message.role}] {message.content}")
```

### Example: Behave step using the session

```python
from behave import when, then
from behave.runner import Context

@when('I call tool "{tool_name}" with arguments {args_json}')
def step_call_tool(context: Context, tool_name: str, args_json: str):
    import json, asyncio
    args = json.loads(args_json)
    context.tool_result = asyncio.run(
        context.mcp_session.call_tool(tool_name, args)
    )

@then('the response should be successful')
def step_check_success(context: Context):
    assert not context.tool_result.isError
```

---

## 4. Raw Session Access

For anything not covered by the high-level methods, access the underlying SDK `ClientSession` directly:

```python
async with MCPSession(server_command) as session:
    raw = session.raw_session  # mcp.client.session.ClientSession

    # Example: completion requests
    result = await raw.complete(...)
```

The `raw_session` property raises `MCPSessionError` if not connected.

---

## 5. LLM-Driven Agentic Tool Calling

This section describes a pattern for building an `MCPClient` that **autonomously discovers, selects, and chains MCP tool calls** to accomplish a task. The `MCPClient` would own an `MCPSession` and pair it with an LLM.

### Architecture

```
MCPClient  (LLM + query processing + tool orchestration)
   └── MCPSession  (protocol connection + raw MCP operations)
          └── MCP Server subprocess (over stdio)
```

```
┌──────────────┐     tool schemas      ┌───────────────┐
│  MCP Server  │◄─────────────────────►│  MCPSession   │
│  (under test)│     call_tool()       │               │
└──────────────┘                       └───────┬───────┘
                                               │
                                       tool results & schemas
                                               │
                                       ┌───────▼────────┐
                                       │   MCPClient    │
                                       │ (agentic loop) │
                                       └───────┬────────┘
                                               │
                                          LLM API calls
                                               │
                                       ┌───────▼────────┐
                                       │  OpenAI / etc  │
                                       └────────────────┘
```

### Step 1: Convert MCP tool schemas to LLM function-calling format

MCP tools already carry a JSON Schema for their inputs. Most LLM APIs (OpenAI, Anthropic) accept this format directly:

```python
from mcp_probe_pilot.core.mcp_session import MCPSession

async def get_llm_tools(session: MCPSession) -> list[dict]:
    """Fetch MCP tools and convert to OpenAI function-calling format."""
    result = await session.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in result.tools
    ]
```

### Step 2: The agentic loop

The core pattern is a loop: send a message to the LLM, check if it wants to call a tool, execute the tool, feed the result back, and repeat until the LLM produces a final answer.

```python
import json
from openai import AsyncOpenAI

async def run_agent(
    task: str,
    session: MCPSession,
    llm: AsyncOpenAI,
    model: str = "gpt-4o",
    max_iterations: int = 10,
) -> str:
    """Execute a task using LLM-driven tool calling against an MCP server.

    The LLM autonomously decides which tools to call and in what order.
    It can chain multiple calls (e.g. search -> summarise -> format).

    Args:
        task: Natural-language description of what to accomplish.
        session: A connected MCPSession instance.
        llm: An async OpenAI client (or compatible).
        model: LLM model identifier.
        max_iterations: Safety cap on tool-call rounds.

    Returns:
        The LLM's final text response after all tool calls complete.
    """
    tools = await get_llm_tools(session)

    messages = [
        {"role": "system", "content": (
            "You are an assistant that completes tasks by calling tools "
            "exposed by an MCP server. Call as many tools as needed, in "
            "whatever order makes sense, to fulfil the user's request."
        )},
        {"role": "user", "content": task},
    ]

    for _ in range(max_iterations):
        response = await llm.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        choice = response.choices[0]

        # If the LLM is done — no more tool calls
        if choice.finish_reason != "tool_calls":
            return choice.message.content or ""

        # Process each tool call the LLM requested
        messages.append(choice.message)

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            # Execute the tool via MCP
            result = await session.call_tool(fn_name, fn_args)

            # Extract text content from the result
            text_parts = [
                block.text
                for block in result.content
                if hasattr(block, "text")
            ]
            tool_output = "\n".join(text_parts)

            # Feed the result back to the LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_output,
            })

    return "Max iterations reached without a final answer."
```

### Step 3: Using the agent

```python
import asyncio
from openai import AsyncOpenAI
from mcp_probe_pilot.core.mcp_session import MCPSession

async def main():
    llm = AsyncOpenAI()

    async with MCPSession("uv run my-mcp-server") as session:
        answer = await run_agent(
            task="Search for documents about authentication and summarise the results.",
            session=session,
            llm=llm,
        )
        print(answer)

asyncio.run(main())
```

### How the LLM chains calls

The LLM sees every prior tool result in its message history. This means it can naturally chain calls:

1. **Call tool A** (e.g. `search_docs`) -> receives results
2. **Decide to call tool B** (e.g. `summarize_text`) with tool A's output
3. **Decide to call tool C** or return a final answer

The developer does not pre-program the sequence — the LLM decides based on the task, the available tools, and the intermediate results.

### Adapting for Anthropic

The pattern is identical; only the API shape changes:

```python
import anthropic

async def get_anthropic_tools(session: MCPSession) -> list[dict]:
    result = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in result.tools
    ]
```

The agentic loop checks for `stop_reason == "tool_use"` instead of `finish_reason == "tool_calls"`, and tool results are returned as `tool_result` content blocks. The core idea — loop until the LLM stops requesting tools — remains the same.

### Including resources and prompts

The agent can also use resources and prompts if the LLM knows about them. One approach is to list them upfront and include them in the system prompt:

```python
async def build_system_prompt(session: MCPSession) -> str:
    resources = await session.list_resources()
    prompts = await session.list_prompts()

    lines = ["You have access to the following MCP resources and prompts:\n"]

    lines.append("## Resources")
    for r in resources.resources:
        lines.append(f"- {r.uri}: {r.description or 'no description'}")

    lines.append("\n## Prompts")
    for p in prompts.prompts:
        args = ", ".join(a.name for a in (p.arguments or []))
        lines.append(f"- {p.name}({args}): {p.description or 'no description'}")

    lines.append(
        "\nTo read a resource, call the `_read_resource` tool with a `uri` argument."
        "\nTo use a prompt, call the `_get_prompt` tool with `name` and `arguments`."
    )
    return "\n".join(lines)
```

You can then register `_read_resource` and `_get_prompt` as synthetic tool definitions that the agent loop dispatches to `session.read_resource()` and `session.get_prompt()` respectively.
