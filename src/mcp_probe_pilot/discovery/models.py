"""Data models for MCP server discovery results.

This module defines Pydantic models for representing discovered MCP server
capabilities including tools, resources, prompts, server information,
and AST-based code entity models for codebase indexing.
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


# =============================================================================
# AST Indexer Models
# =============================================================================


class CodeEntity(BaseModel):
    """A code entity extracted from source code via AST parsing.

    Represents a function, class, or method found in the server source code,
    used for codebase indexing and context-aware test generation.

    Attributes:
        file_path: Relative path to the source file.
        entity_type: Type of entity: 'function', 'class', or 'method'.
        name: Name of the code entity.
        code: Full source code text of the entity.
        start_line: Starting line number in the source file.
        end_line: Ending line number in the source file.
        docstring: Extracted docstring (if any).
        decorators: List of decorator names applied to the entity.
        parent_class: Name of the parent class (for methods only).
    """

    file_path: str = Field(..., description="Relative path to the source file")
    entity_type: str = Field(
        ...,
        description="Type of entity: 'function', 'class', or 'method'",
    )
    name: str = Field(..., description="Name of the code entity")
    code: str = Field(..., description="Full source code text")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    docstring: Optional[str] = Field(None, description="Extracted docstring")
    decorators: list[str] = Field(
        default_factory=list,
        description="List of decorator names",
    )
    parent_class: Optional[str] = Field(
        None,
        description="Parent class name (for methods)",
    )

    @property
    def qualified_name(self) -> str:
        """Get the fully qualified name of the entity.

        Returns:
            For methods: 'ClassName.method_name', otherwise just the name.
        """
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name

    @property
    def summary(self) -> str:
        """Get a brief summary of the entity for embedding.

        Returns:
            A string combining the entity type, name, and docstring.
        """
        parts = [f"{self.entity_type}: {self.qualified_name}"]
        if self.docstring:
            parts.append(self.docstring.split("\n")[0])
        return " - ".join(parts)


class CodebaseIndex(BaseModel):
    """Index of all code entities extracted from a codebase.

    Represents the complete result of AST-based source code indexing,
    including all discovered entities and file hash information for
    incremental re-indexing.

    Attributes:
        entities: List of all extracted code entities.
        file_hashes: Mapping of file paths to their SHA-256 hashes.
        total_files: Total number of Python files processed.
        total_entities: Total number of code entities extracted.
    """

    entities: list[CodeEntity] = Field(
        default_factory=list,
        description="List of all extracted code entities",
    )
    file_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file paths to SHA-256 hashes",
    )
    total_files: int = Field(0, description="Total number of files processed")
    total_entities: int = Field(0, description="Total number of entities extracted")

    def get_entities_for_file(self, file_path: str) -> list[CodeEntity]:
        """Get all entities from a specific file.

        Args:
            file_path: The file path to filter by.

        Returns:
            List of CodeEntity objects from the specified file.
        """
        return [e for e in self.entities if e.file_path == file_path]

    def get_entities_by_type(self, entity_type: str) -> list[CodeEntity]:
        """Get all entities of a specific type.

        Args:
            entity_type: The entity type to filter by ('function', 'class', 'method').

        Returns:
            List of CodeEntity objects of the specified type.
        """
        return [e for e in self.entities if e.entity_type == entity_type]
