"""Configuration management for MCP-Probe-Pilot.

This module provides configuration models and loading utilities for the
mcp-probe-service-properties.json configuration file.
"""

import json
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LLMConfig(BaseModel):
    """Configuration for LLM provider settings.

    Attributes:
        provider: The LLM provider to use (openai or anthropic).
        model: The model identifier to use for generation and oracle.
        api_key: Optional API key (can be set via environment variable).
        temperature: Temperature for LLM responses (0.0 to 1.0).
        max_tokens: Maximum tokens for LLM responses.
    """

    provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="LLM provider to use for test generation and oracle",
    )
    model: str = Field(
        default="gpt-4",
        description="Model identifier for the selected provider",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key (defaults to environment variable if not set)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Temperature for LLM responses",
    )
    max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens for LLM responses",
    )

    def get_api_key(self) -> str:
        """Get the API key from config or environment variable.

        Returns:
            The API key string.

        Raises:
            ValueError: If no API key is found in config or environment.
        """
        if self.api_key:
            return self.api_key

        env_var = "OPENAI_API_KEY" if self.provider == "openai" else "ANTHROPIC_API_KEY"
        api_key = os.environ.get(env_var)

        if not api_key:
            raise ValueError(
                f"No API key found. Set {env_var} environment variable "
                f"or provide api_key in configuration."
            )

        return api_key


class MCPProbeConfig(BaseModel):
    """Main configuration for MCP-Probe-Pilot.

    This model represents the mcp-probe-service-properties.json configuration file.

    Attributes:
        project_code: Unique identifier for the MCP server project.
        server_command: Command to start the MCP server.
        transport: Transport protocol (currently only stdio supported).
        regenerate_tests: Whether to force regeneration of test cases.
        llm_provider: LLM provider for test generation and oracle.
        llm_model: Model to use for LLM operations.
        llm_temperature: Temperature for LLM responses.
        llm_max_tokens: Maximum tokens for LLM responses.
        output_dir: Directory for generated tests and reports.
        timeout: Timeout in seconds for server operations.
        max_retries: Maximum retry attempts for test implementation errors.
    """

    project_code: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the MCP server project",
    )
    server_command: str = Field(
        ...,
        min_length=1,
        description="Command to start the MCP server (e.g., 'python -m my_server')",
    )
    transport: Literal["stdio"] = Field(
        default="stdio",
        description="Transport protocol for MCP communication",
    )
    regenerate_tests: bool = Field(
        default=False,
        description="Force regeneration of test cases",
    )
    llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="LLM provider for test generation and oracle",
    )
    llm_model: str = Field(
        default="gpt-4",
        description="Model to use for LLM operations",
    )
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Temperature for LLM responses",
    )
    llm_max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens for LLM responses",
    )
    output_dir: str = Field(
        default=".mcp-probe",
        description="Directory for generated tests and reports",
    )
    timeout: int = Field(
        default=30,
        gt=0,
        description="Timeout in seconds for server operations",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="Maximum retry attempts for test implementation errors",
    )

    @field_validator("project_code")
    @classmethod
    def validate_project_code(cls, v: str) -> str:
        """Validate project_code contains only valid characters.

        Args:
            v: The project code value.

        Returns:
            The validated project code.

        Raises:
            ValueError: If project code contains invalid characters.
        """
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "project_code must contain only alphanumeric characters, "
                "underscores, and hyphens"
            )
        return v

    def get_llm_config(self) -> LLMConfig:
        """Create an LLMConfig instance from this configuration.

        Returns:
            LLMConfig with settings from this configuration.
        """
        return LLMConfig(
            provider=self.llm_provider,
            model=self.llm_model,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
        )

    def get_output_path(self) -> Path:
        """Get the output directory path.

        Returns:
            Path object for the output directory.
        """
        return Path(self.output_dir)


def load_config(config_path: Optional[str | Path] = None) -> MCPProbeConfig:
    """Load MCP-Probe configuration from a JSON file.

    Args:
        config_path: Path to the configuration file. If None, searches for
            'mcp-probe-service-properties.json' in the current directory.

    Returns:
        MCPProbeConfig instance with loaded configuration.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        ValueError: If the configuration file contains invalid JSON or values.
    """
    if config_path is None:
        config_path = Path.cwd() / "mcp-probe-service-properties.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            "Run 'mcp-probe init' to create a configuration file."
        )

    try:
        with open(config_path) as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}") from e

    return MCPProbeConfig(**config_data)


def save_config(config: MCPProbeConfig, config_path: Optional[str | Path] = None) -> Path:
    """Save MCP-Probe configuration to a JSON file.

    Args:
        config: Configuration to save.
        config_path: Path to save the configuration file. If None, saves to
            'mcp-probe-service-properties.json' in the current directory.

    Returns:
        Path to the saved configuration file.
    """
    if config_path is None:
        config_path = Path.cwd() / "mcp-probe-service-properties.json"
    else:
        config_path = Path(config_path)

    config_data = config.model_dump(exclude_none=True)

    with open(config_path, "w") as f:
        json.dump(config_data, f, indent=2)

    return config_path


def create_default_config(
    project_code: str,
    server_command: str,
    **kwargs,
) -> MCPProbeConfig:
    """Create a default configuration with the given project code and server command.

    Args:
        project_code: Unique identifier for the MCP server project.
        server_command: Command to start the MCP server.
        **kwargs: Additional configuration options to override defaults.

    Returns:
        MCPProbeConfig instance with default values.
    """
    return MCPProbeConfig(
        project_code=project_code,
        server_command=server_command,
        **kwargs,
    )
