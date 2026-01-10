"""Unit tests for the MCP Client Discovery module."""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_probe_pilot.discovery import (
    DiscoveryResult,
    MCPConnectionError,
    MCPDiscoveryClient,
    MCPDiscoveryError,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestToolInfo:
    """Tests for ToolInfo model."""

    def test_create_with_all_fields(self):
        """Test creating ToolInfo with all fields."""
        tool = ToolInfo(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"arg1": {"type": "string"}}},
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema["type"] == "object"

    def test_create_minimal(self):
        """Test creating ToolInfo with minimal fields."""
        tool = ToolInfo(name="minimal_tool")
        assert tool.name == "minimal_tool"
        assert tool.description is None
        assert tool.input_schema == {}


class TestResourceInfo:
    """Tests for ResourceInfo model."""

    def test_create_static_resource(self):
        """Test creating a static resource."""
        resource = ResourceInfo(
            uri="file:///data.txt",
            name="Data File",
            description="A data file",
            mime_type="text/plain",
            is_template=False,
        )
        assert resource.uri == "file:///data.txt"
        assert resource.is_template is False

    def test_create_template_resource(self):
        """Test creating a resource template."""
        resource = ResourceInfo(
            uri="user://{user_id}/profile",
            name="User Profile",
            is_template=True,
        )
        assert resource.is_template is True


class TestPromptInfo:
    """Tests for PromptInfo model."""

    def test_create_with_arguments(self):
        """Test creating PromptInfo with arguments."""
        prompt = PromptInfo(
            name="greet",
            description="Greeting prompt",
            arguments=[
                PromptArgument(name="name", description="Name to greet", required=True),
                PromptArgument(name="style", required=False),
            ],
        )
        assert prompt.name == "greet"
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].required is True
        assert prompt.arguments[1].required is False


class TestServerInfo:
    """Tests for ServerInfo model."""

    def test_create_server_info(self):
        """Test creating ServerInfo."""
        info = ServerInfo(
            name="Test Server",
            version="1.0.0",
            protocol_version="2024-11-05",
            capabilities=ServerCapabilities(tools=True, resources=True, prompts=True),
        )
        assert info.name == "Test Server"
        assert info.capabilities.tools is True


class TestDiscoveryResult:
    """Tests for DiscoveryResult model."""

    def test_counts(self):
        """Test count properties."""
        result = DiscoveryResult(
            server_info=ServerInfo(name="Test"),
            tools=[ToolInfo(name="tool1"), ToolInfo(name="tool2")],
            resources=[ResourceInfo(uri="res://1")],
            prompts=[],
        )
        assert result.tool_count == 2
        assert result.resource_count == 1
        assert result.prompt_count == 0

    def test_get_tool(self):
        """Test getting a tool by name."""
        result = DiscoveryResult(
            server_info=ServerInfo(name="Test"),
            tools=[
                ToolInfo(name="tool1", description="First tool"),
                ToolInfo(name="tool2", description="Second tool"),
            ],
        )
        tool = result.get_tool("tool1")
        assert tool is not None
        assert tool.description == "First tool"
        assert result.get_tool("nonexistent") is None

    def test_get_resource(self):
        """Test getting a resource by URI."""
        result = DiscoveryResult(
            server_info=ServerInfo(name="Test"),
            resources=[
                ResourceInfo(uri="res://1", name="Resource 1"),
                ResourceInfo(uri="res://2", name="Resource 2"),
            ],
        )
        resource = result.get_resource("res://1")
        assert resource is not None
        assert resource.name == "Resource 1"

    def test_get_prompt(self):
        """Test getting a prompt by name."""
        result = DiscoveryResult(
            server_info=ServerInfo(name="Test"),
            prompts=[PromptInfo(name="prompt1", description="First prompt")],
        )
        prompt = result.get_prompt("prompt1")
        assert prompt is not None
        assert prompt.description == "First prompt"


# =============================================================================
# Client Tests
# =============================================================================


class TestMCPDiscoveryClientInit:
    """Tests for MCPDiscoveryClient initialization."""

    def test_init_simple_command(self):
        """Test initialization with a simple command."""
        client = MCPDiscoveryClient("python -m my_server")
        assert client.command == "python"
        assert client.args == ["-m", "my_server"]

    def test_init_with_extra_args(self):
        """Test initialization with extra arguments."""
        client = MCPDiscoveryClient(
            "python -m server",
            server_args=["--port", "8080"],
        )
        assert client.args == ["-m", "server", "--port", "8080"]

    def test_init_with_env(self):
        """Test initialization with environment variables."""
        client = MCPDiscoveryClient(
            "python server.py",
            env={"API_KEY": "test-key"},
        )
        assert client.env == {"API_KEY": "test-key"}

    def test_init_with_timeout(self):
        """Test initialization with custom timeout."""
        client = MCPDiscoveryClient("python server.py", timeout=60.0)
        assert client.timeout == 60.0

    def test_not_connected_initially(self):
        """Test client is not connected initially."""
        client = MCPDiscoveryClient("python server.py")
        assert client.is_connected is False


class TestMCPDiscoveryClientConnection:
    """Tests for MCPDiscoveryClient connection handling."""

    @pytest.mark.asyncio
    async def test_ensure_connected_raises_when_not_connected(self):
        """Test that operations raise error when not connected."""
        client = MCPDiscoveryClient("python server.py")
        with pytest.raises(MCPDiscoveryError, match="Not connected"):
            client._ensure_connected()

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        client = MCPDiscoveryClient("python server.py")

        # Mock the stdio_client and ClientSession
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_session = AsyncMock()

        # Mock init result with proper attribute values
        mock_server_info = MagicMock()
        mock_server_info.name = "Test Server"
        mock_server_info.version = "1.0"

        mock_capabilities = MagicMock()
        mock_capabilities.tools = True
        mock_capabilities.resources = True
        mock_capabilities.prompts = True
        mock_capabilities.sampling = None
        mock_capabilities.logging = None

        mock_init_result = MagicMock()
        mock_init_result.serverInfo = mock_server_info
        mock_init_result.capabilities = mock_capabilities
        mock_init_result.protocolVersion = "2024-11-05"
        mock_session.initialize = AsyncMock(return_value=mock_init_result)

        mock_stdio_ctx = AsyncMock()
        mock_stdio_ctx.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_stdio_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "mcp_probe_pilot.discovery.client.stdio_client",
            return_value=mock_stdio_ctx,
        ):
            with patch(
                "mcp_probe_pilot.discovery.client.ClientSession",
                return_value=mock_session_ctx,
            ):
                await client.connect()
                assert client.is_connected is True
                await client.disconnect()

    @pytest.mark.asyncio
    async def test_connect_timeout(self):
        """Test connection timeout."""
        client = MCPDiscoveryClient("python server.py", timeout=0.01)

        mock_stdio_ctx = AsyncMock()

        async def slow_enter(*args, **kwargs):
            await asyncio.sleep(1)
            return (AsyncMock(), AsyncMock())

        mock_stdio_ctx.__aenter__ = slow_enter
        mock_stdio_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "mcp_probe_pilot.discovery.client.stdio_client",
            return_value=mock_stdio_ctx,
        ):
            with pytest.raises(MCPConnectionError, match="timed out"):
                await client.connect()


@dataclass
class MockTool:
    """Mock tool for testing."""
    name: str
    description: Optional[str] = None
    inputSchema: Optional[dict] = None


@dataclass
class MockResource:
    """Mock resource for testing."""
    uri: str
    name: Optional[str] = None
    description: Optional[str] = None
    mimeType: Optional[str] = None


@dataclass
class MockResourceTemplate:
    """Mock resource template for testing."""
    uriTemplate: str
    name: Optional[str] = None
    description: Optional[str] = None
    mimeType: Optional[str] = None


@dataclass
class MockPromptArg:
    """Mock prompt argument for testing."""
    name: str
    description: Optional[str] = None
    required: bool = False


@dataclass
class MockPrompt:
    """Mock prompt for testing."""
    name: str
    description: Optional[str] = None
    arguments: Optional[list] = None


class TestMCPDiscoveryClientDiscovery:
    """Tests for MCPDiscoveryClient discovery methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session with discovery methods."""
        session = AsyncMock()

        # Mock list_tools response
        mock_tool = MockTool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object"},
        )
        tools_result = MagicMock()
        tools_result.tools = [mock_tool]
        session.list_tools = AsyncMock(return_value=tools_result)

        # Mock list_resources response
        mock_resource = MockResource(
            uri="file:///test.txt",
            name="Test File",
            description="A test file",
            mimeType="text/plain",
        )
        resources_result = MagicMock()
        resources_result.resources = [mock_resource]
        session.list_resources = AsyncMock(return_value=resources_result)

        # Mock list_resource_templates response
        mock_template = MockResourceTemplate(
            uriTemplate="user://{id}/profile",
            name="User Profile",
        )
        templates_result = MagicMock()
        templates_result.resourceTemplates = [mock_template]
        session.list_resource_templates = AsyncMock(return_value=templates_result)

        # Mock list_prompts response
        mock_arg = MockPromptArg(
            name="user_name",
            description="Name to greet",
            required=True,
        )
        mock_prompt = MockPrompt(
            name="greet",
            description="Greeting prompt",
            arguments=[mock_arg],
        )
        prompts_result = MagicMock()
        prompts_result.prompts = [mock_prompt]
        session.list_prompts = AsyncMock(return_value=prompts_result)

        return session

    @pytest.mark.asyncio
    async def test_discover_tools(self, mock_session):
        """Test tool discovery."""
        client = MCPDiscoveryClient("python server.py")
        client._session = mock_session
        client._connected = True
        client._server_info = ServerInfo(name="Test")

        tools = await client.discover_tools()

        assert len(tools) == 1
        assert tools[0].name == "test_tool"
        assert tools[0].description == "A test tool"
        assert tools[0].input_schema == {"type": "object"}

    @pytest.mark.asyncio
    async def test_discover_resources(self, mock_session):
        """Test resource discovery."""
        client = MCPDiscoveryClient("python server.py")
        client._session = mock_session
        client._connected = True
        client._server_info = ServerInfo(name="Test")

        resources = await client.discover_resources()

        assert len(resources) == 2  # 1 static + 1 template
        static = next(r for r in resources if not r.is_template)
        template = next(r for r in resources if r.is_template)

        assert static.uri == "file:///test.txt"
        assert static.is_template is False
        assert template.uri == "user://{id}/profile"
        assert template.is_template is True

    @pytest.mark.asyncio
    async def test_discover_prompts(self, mock_session):
        """Test prompt discovery."""
        client = MCPDiscoveryClient("python server.py")
        client._session = mock_session
        client._connected = True
        client._server_info = ServerInfo(name="Test")

        prompts = await client.discover_prompts()

        assert len(prompts) == 1
        assert prompts[0].name == "greet"
        assert prompts[0].description == "Greeting prompt"

    @pytest.mark.asyncio
    async def test_discover_all(self, mock_session):
        """Test complete discovery."""
        client = MCPDiscoveryClient("python server.py")
        client._session = mock_session
        client._connected = True
        client._server_info = ServerInfo(name="Test Server", version="1.0")

        result = await client.discover_all()

        assert result.server_info.name == "Test Server"
        assert result.tool_count == 1
        assert result.resource_count == 2
        assert result.prompt_count == 1


# =============================================================================
# Integration Test (marked to skip by default, run with real server)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_mcp_test_server():
    """Integration test: Discover capabilities from mcp-probe-test-server.

    This test requires the mcp-probe-test-server to be installed.
    Run with: pytest -m integration tests/test_discovery.py
    """
    import os
    from pathlib import Path

    # Get the path to mcp-probe-test-server relative to this test file
    test_dir = Path(__file__).parent
    project_root = test_dir.parent.parent  # mcp-probe/
    test_server_dir = project_root / "mcp-probe-test-server"

    # Run uv from the test server directory
    server_command = f"uv --directory {test_server_dir} run mcp-test-server"

    async with MCPDiscoveryClient(server_command, timeout=60.0) as client:
        result = await client.discover_all()

        # Verify server info
        assert result.server_info.name == "Task Management Server"

        # Verify tools (should have 11 tools)
        tool_names = [t.name for t in result.tools]
        expected_tools = [
            "auth_login",
            "create_project",
            "add_task",
            "assign_task",
            "update_task_status",
            "query_tasks",
            "delete_task",
            "delete_project_with_confirmation",
            "generate_task_summary",
            "reset_server_state",
        ]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

        # Verify resources
        resource_uris = [r.uri for r in result.resources]
        assert any("system://status" in uri for uri in resource_uris)

        # Verify prompts (should have 3 prompts)
        prompt_names = [p.name for p in result.prompts]
        expected_prompts = ["create_task_template", "project_summary", "task_review"]
        for expected in expected_prompts:
            assert expected in prompt_names, f"Missing prompt: {expected}"

        print(f"\nDiscovery successful!")
        print(f"  Server: {result.server_info.name}")
        print(f"  Tools: {result.tool_count}")
        print(f"  Resources: {result.resource_count}")
        print(f"  Prompts: {result.prompt_count}")
