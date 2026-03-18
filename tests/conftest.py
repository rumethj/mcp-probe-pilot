"""Shared fixtures for mcp-probe-pilot test suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_probe_pilot.core.models.discover import (
    DiscoveryResult,
    PromptArgument,
    PromptInfo,
    ResourceInfo,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)
from mcp_probe_pilot.core.models.plan import (
    IntegrationTestPlanResult,
    ScenarioPlan,
    UnitTestPlanResult,
)


# ------------------------------------------------------------------
# Sample MCP primitives
# ------------------------------------------------------------------


@pytest.fixture()
def sample_tool() -> ToolInfo:
    return ToolInfo(
        name="search_notes",
        description="Search notes by keyword query",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    )


@pytest.fixture()
def sample_tool_minimal() -> ToolInfo:
    """Tool with no description and empty schema."""
    return ToolInfo(name="ping", description=None, input_schema={})


@pytest.fixture()
def sample_resource() -> ResourceInfo:
    return ResourceInfo(
        uri="notes://all",
        name="all_notes",
        description="List of all notes",
        mime_type="application/json",
        is_template=False,
    )


@pytest.fixture()
def sample_resource_unnamed() -> ResourceInfo:
    """Resource with name=None; identifier should fall back to URI."""
    return ResourceInfo(
        uri="notes://archive",
        name=None,
        description="Archived notes",
        mime_type="text/plain",
        is_template=False,
    )


@pytest.fixture()
def sample_resource_template() -> ResourceInfo:
    return ResourceInfo(
        uri="notes://{note_id}",
        name="note_by_id",
        description="Single note by ID",
        mime_type="application/json",
        is_template=True,
    )


@pytest.fixture()
def sample_prompt() -> PromptInfo:
    return PromptInfo(
        name="summarize_note",
        description="Summarize a note using LLM",
        arguments=[
            PromptArgument(name="note_id", description="Note identifier", required=True),
            PromptArgument(name="style", description="Summary style", required=False),
        ],
    )


@pytest.fixture()
def sample_prompt_no_args() -> PromptInfo:
    return PromptInfo(
        name="list_commands",
        description="List available commands",
        arguments=[],
    )


@pytest.fixture()
def sample_server_info() -> ServerInfo:
    return ServerInfo(
        name="test-notes-server",
        version="1.0.0",
        protocol_version="2024-11-05",
        capabilities=ServerCapabilities(
            tools=True, resources=True, prompts=True
        ),
    )


@pytest.fixture()
def sample_discovery(
    sample_server_info: ServerInfo,
    sample_tool: ToolInfo,
    sample_resource: ResourceInfo,
    sample_prompt: PromptInfo,
) -> DiscoveryResult:
    return DiscoveryResult(
        server_info=sample_server_info,
        tools=[sample_tool],
        resources=[sample_resource],
        prompts=[sample_prompt],
    )


@pytest.fixture()
def empty_discovery(sample_server_info: ServerInfo) -> DiscoveryResult:
    return DiscoveryResult(
        server_info=sample_server_info,
        tools=[],
        resources=[],
        prompts=[],
    )


# ------------------------------------------------------------------
# Plan fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def empty_unit_plan() -> UnitTestPlanResult:
    return UnitTestPlanResult()


@pytest.fixture()
def empty_integration_plan() -> IntegrationTestPlanResult:
    return IntegrationTestPlanResult()


# ------------------------------------------------------------------
# Mock LLM
# ------------------------------------------------------------------


@pytest.fixture()
def mock_llm() -> MagicMock:
    """Mock ChatGoogleGenerativeAI that works with LangChain's pipe operator.

    The Planner builds chains as ``prompt | llm.with_structured_output(schema)``.
    ``ChatPromptTemplate | structured_llm`` ends up calling
    ``structured_llm.__ror__(prompt)``, which on a MagicMock returns another
    MagicMock.  We configure ``with_structured_output`` to return a mock whose
    ``__ror__`` yields a controllable chain stub.
    """
    llm = MagicMock()
    return llm


@pytest.fixture()
def mock_service_client() -> AsyncMock:
    """AsyncMock for MCPProbeServiceClient; query_codebase returns []."""
    client = AsyncMock()
    client.query_codebase = AsyncMock(return_value=[])
    return client
