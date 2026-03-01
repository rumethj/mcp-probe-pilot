"""Pydantic models for MCP server discovery and codebase indexing."""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MCP Server Discovery Models
# ---------------------------------------------------------------------------


class PromptArgument(BaseModel):
    name: str = Field(..., description="Argument name")
    description: Optional[str] = Field(None, description="Argument description")
    required: bool = Field(False, description="Whether the argument is required")


class ToolInfo(BaseModel):
    name: str = Field(..., description="Tool name for invocation")
    description: Optional[str] = Field(None, description="Tool description")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool input parameters",
    )


class ResourceInfo(BaseModel):
    uri: str = Field(..., description="Resource URI or URI template")
    name: Optional[str] = Field(None, description="Resource name")
    description: Optional[str] = Field(None, description="Resource description")
    mime_type: Optional[str] = Field(None, description="MIME type of resource content")
    is_template: bool = Field(False, description="Whether this is a URI template")


class PromptInfo(BaseModel):
    name: str = Field(..., description="Prompt name")
    description: Optional[str] = Field(None, description="Prompt description")
    arguments: list[PromptArgument] = Field(
        default_factory=list,
        description="Arguments accepted by the prompt",
    )


class ServerCapabilities(BaseModel):
    tools: bool = Field(False, description="Server supports tools")
    resources: bool = Field(False, description="Server supports resources")
    prompts: bool = Field(False, description="Server supports prompts")
    sampling: bool = Field(False, description="Server supports sampling")
    logging: bool = Field(False, description="Server supports logging")


class ServerInfo(BaseModel):
    name: str = Field(..., description="Server name")
    version: Optional[str] = Field(None, description="Server version")
    protocol_version: Optional[str] = Field(None, description="MCP protocol version")
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)


class DiscoveryResult(BaseModel):
    server_info: ServerInfo = Field(..., description="Server information")
    tools: list[ToolInfo] = Field(default_factory=list)
    resources: list[ResourceInfo] = Field(default_factory=list)
    prompts: list[PromptInfo] = Field(default_factory=list)

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def resource_count(self) -> int:
        return len(self.resources)

    @property
    def prompt_count(self) -> int:
        return len(self.prompts)

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_resource(self, uri: str) -> Optional[ResourceInfo]:
        for resource in self.resources:
            if resource.uri == uri:
                return resource
        return None

    def get_prompt(self, name: str) -> Optional[PromptInfo]:
        for prompt in self.prompts:
            if prompt.name == name:
                return prompt
        return None


# ---------------------------------------------------------------------------
# AST Codebase Indexing Models
# ---------------------------------------------------------------------------


class CodeEntity(BaseModel):
    """A code entity (function, class, or method) extracted via AST parsing."""

    file_path: str = Field(..., description="Relative path to the source file")
    entity_type: str = Field(
        ..., description="Type of entity: 'function', 'class', or 'method'"
    )
    name: str = Field(..., description="Name of the code entity")
    code: str = Field(..., description="Full source code text")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    docstring: Optional[str] = Field(None, description="Extracted docstring")
    decorators: list[str] = Field(default_factory=list)
    parent_class: Optional[str] = Field(
        None, description="Parent class name (for methods)"
    )

    @property
    def qualified_name(self) -> str:
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name

    @property
    def summary(self) -> str:
        parts = [f"{self.entity_type}: {self.qualified_name}"]
        if self.docstring:
            parts.append(self.docstring.split("\n")[0])
        return " - ".join(parts)


class CodebaseIndex(BaseModel):
    """Complete result of AST-based source code indexing."""

    entities: list[CodeEntity] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of file paths to SHA-256 hashes",
    )
    total_files: int = Field(0, description="Total number of files processed")
    total_entities: int = Field(0, description="Total number of entities extracted")

    def get_entities_for_file(self, file_path: str) -> list[CodeEntity]:
        return [e for e in self.entities if e.file_path == file_path]

    def get_entities_by_type(self, entity_type: str) -> list[CodeEntity]:
        return [e for e in self.entities if e.entity_type == entity_type]
