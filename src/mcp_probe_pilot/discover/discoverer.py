"""MCP server capability discovery using an existing MCPSession.

Converts raw MCP SDK types into the Pydantic models defined in
core.models.discovery, without managing its own connection lifecycle.
"""

import logging
from typing import Any

from mcp_probe_pilot.core.mcp_session import MCPSession
from mcp_probe_pilot.core.models.discover import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)

logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """Raised when a discovery operation fails."""


class MCPDiscoverer:
    """Discovers MCP server capabilities via an already-connected MCPSession.

    Example::

        async with MCPSession("uv run my-server") as session:
            discoverer = MCPDiscoverer(session)
            result = await discoverer.discover_all()
            print(result.tool_count)
    """

    def __init__(self, session: MCPSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public discovery methods
    # ------------------------------------------------------------------

    async def discover_all(self) -> DiscoveryResult:
        """Run full discovery: server info, tools, resources, and prompts."""
        server_info = self.parse_server_info()
        tools = await self.discover_tools()
        resources = await self.discover_resources()
        prompts = await self.discover_prompts()

        return DiscoveryResult(
            server_info=server_info,
            tools=tools,
            resources=resources,
            prompts=prompts,
        )

    async def discover_tools(self) -> list[ToolInfo]:
        """List all tools and convert to ToolInfo models."""
        try:
            result = await self._session.list_tools()
            return [
                ToolInfo(
                    name=t.name,
                    description=getattr(t, "description", None),
                    input_schema=getattr(t, "inputSchema", {}) or {},
                )
                for t in result.tools
            ]
        except Exception as exc:
            raise DiscoveryError(f"Failed to discover tools: {exc}") from exc

    async def discover_resources(self) -> list[ResourceInfo]:
        """List static resources and resource templates."""
        resources: list[ResourceInfo] = []

        try:
            static = await self._session.list_resources()
            for r in static.resources:
                resources.append(
                    ResourceInfo(
                        uri=str(r.uri),
                        name=getattr(r, "name", None),
                        description=getattr(r, "description", None),
                        mime_type=getattr(r, "mimeType", None),
                        is_template=False,
                    )
                )
        except Exception as exc:
            raise DiscoveryError(f"Failed to discover resources: {exc}") from exc

        try:
            templates = await self._session.list_resource_templates()
            for t in templates.resourceTemplates:
                resources.append(
                    ResourceInfo(
                        uri=t.uriTemplate,
                        name=getattr(t, "name", None),
                        description=getattr(t, "description", None),
                        mime_type=getattr(t, "mimeType", None),
                        is_template=True,
                    )
                )
        except Exception:
            # Resource templates are optional; not all servers support them.
            pass

        return resources

    async def discover_prompts(self) -> list[PromptInfo]:
        """List all prompts and convert to PromptInfo models."""
        try:
            result = await self._session.list_prompts()
            prompts: list[PromptInfo] = []
            for p in result.prompts:
                arguments: list[PromptArgument] = []
                raw_args = getattr(p, "arguments", None)
                if raw_args:
                    for a in raw_args:
                        arguments.append(
                            PromptArgument(
                                name=a.name,
                                description=getattr(a, "description", None),
                                required=getattr(a, "required", False),
                            )
                        )
                prompts.append(
                    PromptInfo(
                        name=p.name,
                        description=getattr(p, "description", None),
                        arguments=arguments,
                    )
                )
            return prompts
        except Exception as exc:
            raise DiscoveryError(f"Failed to discover prompts: {exc}") from exc

    # ------------------------------------------------------------------
    # Server info parsing
    # ------------------------------------------------------------------

    def parse_server_info(self) -> ServerInfo:
        """Extract ServerInfo from the MCPSession's initialisation result."""
        init_result: Any = self._session.server_info

        server_info_attr = getattr(init_result, "serverInfo", None)
        capabilities_attr = getattr(init_result, "capabilities", None)

        name = "Unknown"
        version = None
        if server_info_attr:
            name = getattr(server_info_attr, "name", "Unknown")
            version = getattr(server_info_attr, "version", None)

        caps = ServerCapabilities()
        if capabilities_attr:
            caps = ServerCapabilities(
                tools=getattr(capabilities_attr, "tools", None) is not None,
                resources=getattr(capabilities_attr, "resources", None) is not None,
                prompts=getattr(capabilities_attr, "prompts", None) is not None,
                sampling=getattr(capabilities_attr, "sampling", None) is not None,
                logging=getattr(capabilities_attr, "logging", None) is not None,
            )

        return ServerInfo(
            name=name,
            version=version,
            protocol_version=getattr(init_result, "protocolVersion", None),
            capabilities=caps,
        )
