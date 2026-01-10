"""MCP Client Discovery module.

This module provides functionality to connect to MCP servers and discover
their capabilities including tools, resources, and prompts.

Example:
    ```python
    from mcp_probe_pilot.discovery import MCPDiscoveryClient

    async with MCPDiscoveryClient("python -m my_server") as client:
        result = await client.discover_all()
        print(f"Found {result.tool_count} tools")
        for tool in result.tools:
            print(f"  - {tool.name}: {tool.description}")
    ```
"""

from .client import (
    MCPConnectionError,
    MCPDiscoveryClient,
    MCPDiscoveryError,
    create_discovery_client,
)
from .models import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)

__all__ = [
    # Client
    "MCPDiscoveryClient",
    "MCPDiscoveryError",
    "MCPConnectionError",
    "create_discovery_client",
    # Models
    "DiscoveryResult",
    "ToolInfo",
    "ResourceInfo",
    "PromptInfo",
    "PromptArgument",
    "ServerInfo",
    "ServerCapabilities",
]
