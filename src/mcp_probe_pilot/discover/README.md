# Discover

Connects to an MCP server and discovers its capabilities; optionally indexes the server's codebase via AST parsing.

## Purpose

The discover stage is the first step in the pipeline. It produces a `DiscoveryResult` containing the server's tools, resources, and prompts, which all downstream stages depend on.

## Key Concepts

- **MCPDiscoverer** – Takes an already-connected `MCPSession` and calls `list_tools`, `list_resources`, `list_resource_templates`, and `list_prompts`, converting raw SDK types into the Pydantic models defined in `core.models.discover`. Connection lifecycle is not managed here; the orchestrator owns that.
- **ServerInfo Parsing** – Extracts server name, version, protocol version, and capability flags from the MCP initialisation result.
- **ASTIndexer** – Recursively walks a directory tree, parses every Python file via the `ast` stdlib module, and extracts functions, classes, and methods with metadata (docstrings, decorators, line ranges). Uses SHA-256 hashing for incremental re-indexing.
- **Exclusion Patterns** – Configurable directory and file exclusion sets (with glob support) prevent indexing of test directories, build artefacts, and caches.

## Modules

| File | Description |
|------|-------------|
| `discoverer.py` | `MCPDiscoverer` – MCP capability discovery over an active session. |
| `ast_indexer.py` | `ASTIndexer` – Python source code entity extraction. |
