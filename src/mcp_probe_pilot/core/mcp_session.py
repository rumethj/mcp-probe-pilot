"""Generic MCP session for all MCP server interaction.

Wraps the official modelcontextprotocol/python-sdk to provide a single,
reusable session for discovery, test execution, and any other operation
that requires communication with an MCP server over stdio.
"""

import asyncio
import shlex
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    ReadResourceResult,
)


class MCPSessionError(Exception):
    """Base exception for MCP session operations."""


class MCPConnectionError(MCPSessionError):
    """Raised when the session cannot connect to the MCP server."""


class MCPSession:
    """A generic async MCP session that communicates over stdio.

    Usage::

        async with MCPSession("uv run my-mcp-server") as session:
            tools = await session.list_tools()
            result = await session.call_tool("add", {"a": 1, "b": 2})

    Args:
        server_command: Shell command string to launch the MCP server
            (e.g. ``"python -m my_server"`` or ``"uv run my-server"``).
        env: Optional environment variables for the server subprocess.
        timeout: Seconds to wait for any single operation before raising
            ``asyncio.TimeoutError``. Defaults to 30.
    """

    def __init__(
        self,
        server_command: str,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        parsed = shlex.split(server_command)
        self._command = parsed[0]
        self._args = parsed[1:] if len(parsed) > 1 else []
        self._env = env
        self._timeout = timeout

        self._stdio_ctx: Any | None = None
        self._session_ctx: Any | None = None
        self._session: ClientSession | None = None
        self._init_result: Any | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the server subprocess and initialise the MCP session.

        Raises:
            MCPConnectionError: If the server cannot be started or the
                handshake fails.
        """
        if self._session is not None:
            return

        try:
            params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=self._env,
            )

            self._stdio_ctx = stdio_client(params)
            read, write = await asyncio.wait_for(
                self._stdio_ctx.__aenter__(),
                timeout=self._timeout,
            )

            self._session_ctx = ClientSession(read, write)
            self._session = await asyncio.wait_for(
                self._session_ctx.__aenter__(),
                timeout=self._timeout,
            )

            self._init_result = await asyncio.wait_for(
                self._session.initialize(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            await self.disconnect()
            raise MCPConnectionError(
                f"Timed out connecting to MCP server after {self._timeout}s"
            ) from exc
        except MCPConnectionError:
            raise
        except Exception as exc:
            await self.disconnect()
            raise MCPConnectionError(
                f"Failed to connect to MCP server: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Shut down the session and server subprocess."""
        if self._session_ctx is not None:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_ctx = None
            self._session = None

        if self._stdio_ctx is not None:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._stdio_ctx = None

        self._init_result = None

    async def __aenter__(self) -> "MCPSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> ClientSession:
        if self._session is None:
            raise MCPSessionError(
                "Not connected. Call connect() or use 'async with MCPSession(...)'."
            )
        return self._session

    async def _run(self, coro: Any) -> Any:
        """Run *coro* with the configured timeout."""
        return await asyncio.wait_for(coro, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def raw_session(self) -> ClientSession:
        """The underlying ``ClientSession`` for advanced / direct use."""
        return self._ensure_connected()

    @property
    def server_info(self) -> Any:
        """Server metadata returned during the initialisation handshake."""
        if self._init_result is None:
            raise MCPSessionError("Not connected — no server info available.")
        return self._init_result

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def list_tools(self) -> ListToolsResult:
        """List all tools exposed by the server."""
        session = self._ensure_connected()
        return await self._run(session.list_tools())

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> CallToolResult:
        """Invoke a tool by name.

        Args:
            name: Tool name as returned by :meth:`list_tools`.
            arguments: Keyword arguments matching the tool's input schema.
        """
        session = self._ensure_connected()
        return await self._run(session.call_tool(name, arguments or {}))

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def list_resources(self) -> ListResourcesResult:
        """List static resources exposed by the server."""
        session = self._ensure_connected()
        return await self._run(session.list_resources())

    async def list_resource_templates(self) -> ListResourceTemplatesResult:
        """List URI-template resources exposed by the server."""
        session = self._ensure_connected()
        return await self._run(session.list_resource_templates())

    async def read_resource(self, uri: str) -> ReadResourceResult:
        """Read a resource by URI.

        Args:
            uri: Exact resource URI (or a filled-in template).
        """
        session = self._ensure_connected()
        return await self._run(session.read_resource(uri))

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    async def list_prompts(self) -> ListPromptsResult:
        """List prompts exposed by the server."""
        session = self._ensure_connected()
        return await self._run(session.list_prompts())

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> GetPromptResult:
        """Retrieve a prompt by name.

        Args:
            name: Prompt name as returned by :meth:`list_prompts`.
            arguments: Values for the prompt's declared arguments.
        """
        session = self._ensure_connected()
        return await self._run(session.get_prompt(name, arguments))
