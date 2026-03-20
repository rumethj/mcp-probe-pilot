"""Unit tests for the MCPDiscoverer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from mcp_probe_pilot.core.models.discover import (
    DiscoveryResult,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)
from mcp_probe_pilot.discover.discoverer import DiscoveryError, MCPDiscoverer


# ------------------------------------------------------------------
# Mock session factory
# ------------------------------------------------------------------


def _make_session(
    *,
    tools=None,
    resources=None,
    templates=None,
    prompts=None,
    server_info_attr=None,
    capabilities_attr=None,
) -> MagicMock:
    session = MagicMock()

    # list_tools
    tool_result = MagicMock()
    tool_result.tools = tools or []
    session.list_tools = AsyncMock(return_value=tool_result)

    # list_resources
    res_result = MagicMock()
    res_result.resources = resources or []
    session.list_resources = AsyncMock(return_value=res_result)

    # list_resource_templates
    tmpl_result = MagicMock()
    tmpl_result.resourceTemplates = templates or []
    session.list_resource_templates = AsyncMock(return_value=tmpl_result)

    # list_prompts
    prompt_result = MagicMock()
    prompt_result.prompts = prompts or []
    session.list_prompts = AsyncMock(return_value=prompt_result)

    # server_info (init result)
    init_result = MagicMock()
    init_result.serverInfo = server_info_attr
    init_result.capabilities = capabilities_attr
    init_result.protocolVersion = "2024-11-05"
    type(session).server_info = PropertyMock(return_value=init_result)

    return session


def _make_tool(name="search", description="Search things", input_schema=None):
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = input_schema or {}
    return t


def _make_resource(uri="notes://all", name="all_notes", description="All notes", mime="application/json"):
    r = MagicMock()
    r.uri = uri
    r.name = name
    r.description = description
    r.mimeType = mime
    return r


def _make_template(uri_template="notes://{id}", name="note_by_id", description="Single note", mime="application/json"):
    t = MagicMock()
    t.uriTemplate = uri_template
    t.name = name
    t.description = description
    t.mimeType = mime
    return t


def _make_prompt(name="summarize", description="Summarize", arguments=None):
    p = MagicMock()
    p.name = name
    p.description = description
    p.arguments = arguments or []
    return p


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestDiscoverTools:
    @pytest.mark.asyncio
    async def test_returns_tool_info_list(self) -> None:
        tool = _make_tool("search", "Search notes", {"type": "object"})
        session = _make_session(tools=[tool])
        discoverer = MCPDiscoverer(session)

        result = await discoverer.discover_tools()

        assert len(result) == 1
        assert isinstance(result[0], ToolInfo)
        assert result[0].name == "search"
        assert result[0].description == "Search notes"

    @pytest.mark.asyncio
    async def test_empty_tools(self) -> None:
        session = _make_session(tools=[])
        discoverer = MCPDiscoverer(session)
        result = await discoverer.discover_tools()
        assert result == []

    @pytest.mark.asyncio
    async def test_discovery_error_on_failure(self) -> None:
        session = _make_session()
        session.list_tools = AsyncMock(side_effect=RuntimeError("boom"))
        discoverer = MCPDiscoverer(session)

        with pytest.raises(DiscoveryError, match="Failed to discover tools"):
            await discoverer.discover_tools()


class TestDiscoverResources:
    @pytest.mark.asyncio
    async def test_static_and_templates(self) -> None:
        static = _make_resource()
        template = _make_template()
        session = _make_session(resources=[static], templates=[template])
        discoverer = MCPDiscoverer(session)

        result = await discoverer.discover_resources()

        assert len(result) == 2
        assert result[0].is_template is False
        assert result[1].is_template is True

    @pytest.mark.asyncio
    async def test_template_failure_is_silent(self) -> None:
        static = _make_resource()
        session = _make_session(resources=[static])
        session.list_resource_templates = AsyncMock(side_effect=RuntimeError("no templates"))
        discoverer = MCPDiscoverer(session)

        result = await discoverer.discover_resources()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_static_failure_raises(self) -> None:
        session = _make_session()
        session.list_resources = AsyncMock(side_effect=RuntimeError("boom"))
        discoverer = MCPDiscoverer(session)

        with pytest.raises(DiscoveryError, match="Failed to discover resources"):
            await discoverer.discover_resources()


class TestDiscoverPrompts:
    @pytest.mark.asyncio
    async def test_returns_prompt_info(self) -> None:
        arg = MagicMock()
        arg.name = "note_id"
        arg.description = "Note ID"
        arg.required = True
        prompt = _make_prompt("summarize", "Summarize a note", arguments=[arg])
        session = _make_session(prompts=[prompt])
        discoverer = MCPDiscoverer(session)

        result = await discoverer.discover_prompts()

        assert len(result) == 1
        assert isinstance(result[0], PromptInfo)
        assert result[0].name == "summarize"
        assert len(result[0].arguments) == 1
        assert result[0].arguments[0].required is True

    @pytest.mark.asyncio
    async def test_prompt_with_no_args(self) -> None:
        prompt = _make_prompt("list", "List things", arguments=None)
        session = _make_session(prompts=[prompt])
        discoverer = MCPDiscoverer(session)

        result = await discoverer.discover_prompts()
        assert result[0].arguments == []


class TestDiscoverAll:
    @pytest.mark.asyncio
    async def test_full_discovery(self) -> None:
        si = MagicMock()
        si.name = "test-server"
        si.version = "1.0.0"
        caps = MagicMock()
        caps.tools = True
        caps.resources = True
        caps.prompts = True
        caps.sampling = None
        caps.logging = None

        session = _make_session(
            tools=[_make_tool()],
            resources=[_make_resource()],
            prompts=[_make_prompt()],
            server_info_attr=si,
            capabilities_attr=caps,
        )
        discoverer = MCPDiscoverer(session)
        result = await discoverer.discover_all()

        assert isinstance(result, DiscoveryResult)
        assert result.server_info.name == "test-server"
        assert len(result.tools) == 1
        assert len(result.resources) == 1
        assert len(result.prompts) == 1


class TestParseServerInfo:
    def test_extracts_name_and_version(self) -> None:
        si = MagicMock()
        si.name = "my-server"
        si.version = "2.0"
        session = _make_session(server_info_attr=si)
        discoverer = MCPDiscoverer(session)

        info = discoverer.parse_server_info()
        assert info.name == "my-server"
        assert info.version == "2.0"

    def test_missing_server_info_attr(self) -> None:
        session = _make_session(server_info_attr=None)
        discoverer = MCPDiscoverer(session)

        info = discoverer.parse_server_info()
        assert info.name == "Unknown"
        assert info.version is None
