"""MCP Client Discovery module.

This module provides functionality to connect to MCP servers and discover
their capabilities including tools, resources, and prompts. It also includes
an AST-based codebase indexer for extracting code entities from server source code.

Example:
    ```python
    from mcp_probe_pilot.discovery import MCPDiscoveryClient, ASTIndexer

    async with MCPDiscoveryClient("python -m my_server") as client:
        result = await client.discover_all()
        print(f"Found {result.tool_count} tools")

    indexer = ASTIndexer()
    index = indexer.index_directory(Path("/path/to/server/src"))
    print(f"Indexed {index.total_entities} code entities")
    ```
"""

from .ast_indexer import ASTIndexer, ASTIndexerError
from .client import (
    MCPConnectionError,
    MCPDiscoveryClient,
    MCPDiscoveryError,
    create_discovery_client,
)
from .models import (
    CodebaseIndex,
    CodeEntity,
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
    # AST Indexer
    "ASTIndexer",
    "ASTIndexerError",
    # Models
    "DiscoveryResult",
    "ToolInfo",
    "ResourceInfo",
    "PromptInfo",
    "PromptArgument",
    "ServerInfo",
    "ServerCapabilities",
    "CodeEntity",
    "CodebaseIndex",
]
