# Sequence Diagram — Discovery Stage

This diagram shows the Discovery Stage flow using only: **MCPProbeOrchestrator**, **MCPDiscoverer**, **ASTIndexer**, **MCPSession**, and **MCPProbeServiceClient**.

```mermaid
sequenceDiagram
    autonumber
    participant Orch as MCPProbeOrchestrator
    participant Disc as MCPDiscoverer
    participant AST as ASTIndexer
    participant Session as MCPSession
    participant Service as MCPProbeServiceClient

    rect rgb(230, 245, 255)
        Note over Orch, Session: 1. MCP Server Discovery
        Orch ->> Session: MCPSession(server_command, cwd, …)
        activate Session
        Orch ->> Session: connect() [async with]
        Session ->> Session: stdio_client(), ClientSession, initialize()
        Session -->> Orch: session ready

        Orch ->> Disc: MCPDiscoverer(session)
        activate Disc
        Orch ->> Disc: discover_all()
        Disc ->> Session: server_info (from init result)
        Session -->> Disc: init result
        Disc ->> Session: list_tools()
        Session -->> Disc: ListToolsResult
        Disc ->> Session: list_resources()
        Session -->> Disc: ListResourcesResult
        Disc ->> Session: list_resource_templates()
        Session -->> Disc: ListResourceTemplatesResult
        Disc ->> Session: list_prompts()
        Session -->> Disc: ListPromptsResult
        Disc -->> Orch: DiscoveryResult(tools, resources, prompts)
        deactivate Disc

        Orch ->> Session: disconnect() [exit context]
        deactivate Session
    end

    rect rgb(240, 248, 240)
        Note over Orch, AST: 2. AST Codebase Indexing
        Orch ->> AST: ASTIndexer()
        activate AST
        Orch ->> AST: index_directory(repository_root)
        Note right of AST: Walk .py files, parse AST,<br/>extract functions, classes, methods
        AST -->> Orch: CodebaseIndex(entities, file_hashes)
        deactivate AST
    end

    rect rgb(255, 248, 240)
        Note over Orch, Service: 3. Codebase Index Upload
        Orch ->> Service: MCPProbeServiceClient(service_url)
        activate Service
        Orch ->> Service: index_codebase(entities)
        Note right of Service: POST /api/codebase/index,<br/>store in ChromaDB
        Service -->> Orch: {indexed_count: N}
        deactivate Service
    end
```

## Summary

| Step | Orchestrator action | Main interaction |
|------|---------------------|------------------|
| **1. MCP Server Discovery** | `async with MCPSession(...)` then `MCPDiscoverer(session).discover_all()` | Session: connect → list_tools, list_resources, list_resource_templates, list_prompts → disconnect. Discoverer maps MCP types to `DiscoveryResult`. |
| **2. AST Codebase Indexing** | `ASTIndexer().index_directory(repository_root)` | Indexer scans repo, parses Python ASTs, returns `CodebaseIndex`. |
| **3. Codebase Index Upload** | `async with MCPProbeServiceClient(...)` then `client.index_codebase(entities)` | Client POSTs entities to mcp-probe-service for ChromaDB indexing. |
