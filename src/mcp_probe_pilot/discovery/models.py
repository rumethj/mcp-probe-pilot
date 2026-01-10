"""Data models for MCP server discovery results.

This module defines Pydantic models for representing discovered MCP server
capabilities including tools, resources, prompts, and server information.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class PromptArgument(BaseModel):
    """Argument definition for an MCP prompt.

    Attributes:
        name: The argument name.
        description: Optional description of the argument.
        required: Whether this argument is required.
    """

    name: str = Field(..., description="Argument name")
    description: Optional[str] = Field(None, description="Argument description")
    required: bool = Field(False, description="Whether the argument is required")


class ToolInfo(BaseModel):
    """Information about a discovered MCP tool.

    Attributes:
        name: The tool name used for invocation.
        description: Human-readable description of the tool.
        input_schema: JSON Schema describing the tool's input parameters.
    """

    name: str = Field(..., description="Tool name for invocation")
    description: Optional[str] = Field(None, description="Tool description")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool input parameters",
    )


class ResourceInfo(BaseModel):
    """Information about a discovered MCP resource.

    Attributes:
        uri: The resource URI or URI template.
        name: Optional human-readable name.
        description: Optional description of the resource.
        mime_type: Optional MIME type of the resource content.
        is_template: Whether this is a URI template (contains placeholders).
    """

    uri: str = Field(..., description="Resource URI or URI template")
    name: Optional[str] = Field(None, description="Resource name")
    description: Optional[str] = Field(None, description="Resource description")
    mime_type: Optional[str] = Field(None, description="MIME type of resource content")
    is_template: bool = Field(False, description="Whether this is a URI template")


class PromptInfo(BaseModel):
    """Information about a discovered MCP prompt.

    Attributes:
        name: The prompt name for retrieval.
        description: Human-readable description of the prompt.
        arguments: List of arguments the prompt accepts.
    """

    name: str = Field(..., description="Prompt name")
    description: Optional[str] = Field(None, description="Prompt description")
    arguments: list[PromptArgument] = Field(
        default_factory=list,
        description="Arguments accepted by the prompt",
    )


class ServerCapabilities(BaseModel):
    """MCP server capability flags.

    Attributes:
        tools: Whether the server supports tools.
        resources: Whether the server supports resources.
        prompts: Whether the server supports prompts.
        sampling: Whether the server supports sampling requests.
        logging: Whether the server supports logging.
    """

    tools: bool = Field(False, description="Server supports tools")
    resources: bool = Field(False, description="Server supports resources")
    prompts: bool = Field(False, description="Server supports prompts")
    sampling: bool = Field(False, description="Server supports sampling")
    logging: bool = Field(False, description="Server supports logging")


class ServerInfo(BaseModel):
    """Information about the MCP server.

    Attributes:
        name: The server name.
        version: The server version string.
        protocol_version: The MCP protocol version supported.
        capabilities: Server capability flags.
    """

    name: str = Field(..., description="Server name")
    version: Optional[str] = Field(None, description="Server version")
    protocol_version: Optional[str] = Field(None, description="MCP protocol version")
    capabilities: ServerCapabilities = Field(
        default_factory=ServerCapabilities,
        description="Server capabilities",
    )


class DiscoveryResult(BaseModel):
    """Complete discovery result from an MCP server.

    Attributes:
        server_info: Information about the server.
        tools: List of discovered tools.
        resources: List of discovered resources.
        prompts: List of discovered prompts.
    """

    server_info: ServerInfo = Field(..., description="Server information")
    tools: list[ToolInfo] = Field(default_factory=list, description="Discovered tools")
    resources: list[ResourceInfo] = Field(
        default_factory=list,
        description="Discovered resources",
    )
    prompts: list[PromptInfo] = Field(
        default_factory=list,
        description="Discovered prompts",
    )

    @property
    def tool_count(self) -> int:
        """Get the number of discovered tools."""
        return len(self.tools)

    @property
    def resource_count(self) -> int:
        """Get the number of discovered resources."""
        return len(self.resources)

    @property
    def prompt_count(self) -> int:
        """Get the number of discovered prompts."""
        return len(self.prompts)

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        """Get a tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The ToolInfo if found, None otherwise.
        """
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_resource(self, uri: str) -> Optional[ResourceInfo]:
        """Get a resource by URI.

        Args:
            uri: The resource URI to look up.

        Returns:
            The ResourceInfo if found, None otherwise.
        """
        for resource in self.resources:
            if resource.uri == uri:
                return resource
        return None

    def get_prompt(self, name: str) -> Optional[PromptInfo]:
        """Get a prompt by name.

        Args:
            name: The prompt name to look up.

        Returns:
            The PromptInfo if found, None otherwise.
        """
        for prompt in self.prompts:
            if prompt.name == name:
                return prompt
        return None
