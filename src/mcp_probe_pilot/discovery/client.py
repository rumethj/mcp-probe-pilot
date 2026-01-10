"""MCP Discovery Client for connecting to and discovering MCP server capabilities.

This module provides the MCPDiscoveryClient class which connects to MCP servers
via stdio transport and discovers their tools, resources, and prompts.
"""

import asyncio
import shlex
from contextlib import asynccontextmanager
from typing import Any, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .models import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)


class MCPDiscoveryError(Exception):
    """Exception raised when MCP discovery fails."""

    pass


class MCPConnectionError(MCPDiscoveryError):
    """Exception raised when connection to MCP server fails."""

    pass


class MCPDiscoveryClient:
    """Client for discovering MCP server capabilities.

    This client connects to an MCP server via stdio transport and discovers
    its available tools, resources, and prompts.

    Example:
        ```python
        async with MCPDiscoveryClient("python -m my_server") as client:
            result = await client.discover_all()
            print(f"Found {result.tool_count} tools")
        ```

    Attributes:
        command: The base command to run the server.
        args: Additional arguments for the server command.
        env: Environment variables for the server process.
    """

    def __init__(
        self,
        server_command: str,
        server_args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
    ):
        """Initialize the discovery client.

        Args:
            server_command: Command to start the MCP server. Can include arguments
                (e.g., "python -m my_server") which will be parsed.
            server_args: Additional arguments to append to the command.
            env: Environment variables to set for the server process.
            timeout: Timeout in seconds for connection and operations.
        """
        # Parse the command string to separate command and args
        parsed = shlex.split(server_command)
        self.command = parsed[0]
        self.args = parsed[1:] if len(parsed) > 1 else []

        if server_args:
            self.args.extend(server_args)

        self.env = env
        self.timeout = timeout

        # Connection state
        self._stdio_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self._session: Optional[ClientSession] = None
        self._server_info: Optional[ServerInfo] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to the server."""
        return self._connected and self._session is not None

    async def connect(self) -> None:
        """Establish stdio connection to the MCP server.

        This method starts the MCP server process and initializes the
        client session. After calling this method, discovery methods
        can be used.

        Raises:
            MCPConnectionError: If connection to the server fails.
            asyncio.TimeoutError: If connection times out.
        """
        if self._connected:
            return

        try:
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )

            # Enter the stdio client context
            self._stdio_context = stdio_client(server_params)
            read, write = await asyncio.wait_for(
                self._stdio_context.__aenter__(),
                timeout=self.timeout,
            )

            # Enter the session context
            self._session_context = ClientSession(read, write)
            self._session = await asyncio.wait_for(
                self._session_context.__aenter__(),
                timeout=self.timeout,
            )

            # Initialize the connection
            init_result = await asyncio.wait_for(
                self._session.initialize(),
                timeout=self.timeout,
            )

            # Store server info from initialization
            self._server_info = self._parse_server_info(init_result)
            self._connected = True

        except asyncio.TimeoutError:
            await self._cleanup()
            raise MCPConnectionError(
                f"Connection to MCP server timed out after {self.timeout}s"
            )
        except Exception as e:
            await self._cleanup()
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def disconnect(self) -> None:
        """Close the connection to the MCP server.

        This method cleanly shuts down the session and server process.
        """
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        self._connected = False

        if self._session_context is not None:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_context = None
            self._session = None

        if self._stdio_context is not None:
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._stdio_context = None

    async def __aenter__(self) -> "MCPDiscoveryClient":
        """Async context manager entry - connects to the server.

        Returns:
            The connected client instance.
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - disconnects from the server."""
        await self.disconnect()

    def _ensure_connected(self) -> None:
        """Ensure the client is connected before operations.

        Raises:
            MCPDiscoveryError: If not connected.
        """
        if not self.is_connected:
            raise MCPDiscoveryError(
                "Not connected to MCP server. Call connect() first or use as context manager."
            )

    def _parse_server_info(self, init_result: Any) -> ServerInfo:
        """Parse server information from initialization result.

        Args:
            init_result: The initialization result from the MCP session.

        Returns:
            ServerInfo with parsed server details.
        """
        server_info = getattr(init_result, "serverInfo", None)
        capabilities = getattr(init_result, "capabilities", None)

        name = "Unknown"
        version = None

        if server_info:
            name = getattr(server_info, "name", "Unknown")
            version = getattr(server_info, "version", None)

        # Parse capabilities
        caps = ServerCapabilities()
        if capabilities:
            caps = ServerCapabilities(
                tools=getattr(capabilities, "tools", None) is not None,
                resources=getattr(capabilities, "resources", None) is not None,
                prompts=getattr(capabilities, "prompts", None) is not None,
                sampling=getattr(capabilities, "sampling", None) is not None,
                logging=getattr(capabilities, "logging", None) is not None,
            )

        return ServerInfo(
            name=name,
            version=version,
            protocol_version=getattr(init_result, "protocolVersion", None),
            capabilities=caps,
        )

    async def get_server_info(self) -> ServerInfo:
        """Retrieve server metadata.

        Returns:
            ServerInfo containing server name, version, and capabilities.

        Raises:
            MCPDiscoveryError: If not connected.
        """
        self._ensure_connected()

        if self._server_info is None:
            raise MCPDiscoveryError("Server info not available")

        return self._server_info

    async def discover_tools(self) -> list[ToolInfo]:
        """Discover all available tools on the MCP server.

        Returns:
            List of ToolInfo objects describing each tool.

        Raises:
            MCPDiscoveryError: If not connected or discovery fails.
        """
        self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                self._session.list_tools(),
                timeout=self.timeout,
            )

            tools = []
            for tool in result.tools:
                tools.append(
                    ToolInfo(
                        name=tool.name,
                        description=getattr(tool, "description", None),
                        input_schema=getattr(tool, "inputSchema", {}) or {},
                    )
                )

            return tools

        except asyncio.TimeoutError:
            raise MCPDiscoveryError("Tool discovery timed out")
        except Exception as e:
            raise MCPDiscoveryError(f"Failed to discover tools: {e}") from e

    async def discover_resources(self) -> list[ResourceInfo]:
        """Discover all available resources and resource templates.

        This method retrieves both static resources and resource templates
        (URI patterns with placeholders).

        Returns:
            List of ResourceInfo objects describing each resource.

        Raises:
            MCPDiscoveryError: If not connected or discovery fails.
        """
        self._ensure_connected()

        resources: list[ResourceInfo] = []

        # Get static resources
        try:
            result = await asyncio.wait_for(
                self._session.list_resources(),
                timeout=self.timeout,
            )

            for resource in result.resources:
                resources.append(
                    ResourceInfo(
                        uri=str(resource.uri),
                        name=getattr(resource, "name", None),
                        description=getattr(resource, "description", None),
                        mime_type=getattr(resource, "mimeType", None),
                        is_template=False,
                    )
                )

        except asyncio.TimeoutError:
            raise MCPDiscoveryError("Resource discovery timed out")
        except Exception as e:
            raise MCPDiscoveryError(f"Failed to discover resources: {e}") from e

        # Get resource templates
        try:
            result = await asyncio.wait_for(
                self._session.list_resource_templates(),
                timeout=self.timeout,
            )

            for template in result.resourceTemplates:
                resources.append(
                    ResourceInfo(
                        uri=template.uriTemplate,
                        name=getattr(template, "name", None),
                        description=getattr(template, "description", None),
                        mime_type=getattr(template, "mimeType", None),
                        is_template=True,
                    )
                )

        except Exception:
            # Resource templates might not be supported by all servers
            pass

        return resources

    async def discover_prompts(self) -> list[PromptInfo]:
        """Discover all available prompts on the MCP server.

        Returns:
            List of PromptInfo objects describing each prompt.

        Raises:
            MCPDiscoveryError: If not connected or discovery fails.
        """
        self._ensure_connected()

        try:
            result = await asyncio.wait_for(
                self._session.list_prompts(),
                timeout=self.timeout,
            )

            prompts = []
            for prompt in result.prompts:
                # Parse arguments
                arguments = []
                prompt_args = getattr(prompt, "arguments", None)
                if prompt_args:
                    for arg in prompt_args:
                        arguments.append(
                            PromptArgument(
                                name=arg.name,
                                description=getattr(arg, "description", None),
                                required=getattr(arg, "required", False),
                            )
                        )

                prompts.append(
                    PromptInfo(
                        name=prompt.name,
                        description=getattr(prompt, "description", None),
                        arguments=arguments,
                    )
                )

            return prompts

        except asyncio.TimeoutError:
            raise MCPDiscoveryError("Prompt discovery timed out")
        except Exception as e:
            raise MCPDiscoveryError(f"Failed to discover prompts: {e}") from e

    async def discover_all(self) -> DiscoveryResult:
        """Discover all server capabilities at once.

        This is a convenience method that calls all discovery methods
        and returns a combined result.

        Returns:
            DiscoveryResult containing all discovered capabilities.

        Raises:
            MCPDiscoveryError: If not connected or discovery fails.
        """
        self._ensure_connected()

        server_info = await self.get_server_info()
        tools = await self.discover_tools()
        resources = await self.discover_resources()
        prompts = await self.discover_prompts()

        return DiscoveryResult(
            server_info=server_info,
            tools=tools,
            resources=resources,
            prompts=prompts,
        )


@asynccontextmanager
async def create_discovery_client(
    server_command: str,
    server_args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
):
    """Create and connect a discovery client as an async context manager.

    This is a convenience function for creating a connected discovery client.

    Args:
        server_command: Command to start the MCP server.
        server_args: Additional arguments for the server command.
        env: Environment variables for the server process.
        timeout: Timeout in seconds for connection and operations.

    Yields:
        A connected MCPDiscoveryClient instance.

    Example:
        ```python
        async with create_discovery_client("python -m my_server") as client:
            tools = await client.discover_tools()
        ```
    """
    client = MCPDiscoveryClient(
        server_command=server_command,
        server_args=server_args,
        env=env,
        timeout=timeout,
    )
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()
