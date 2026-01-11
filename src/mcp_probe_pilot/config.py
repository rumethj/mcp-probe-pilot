"""Configuration management for MCP-Probe-Pilot.

This module provides configuration models and loading utilities for the
mcp-probe-service-properties.json configuration file.
"""

import json
import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Load environment variables from .env file if present
load_dotenv()

# Supported LLM providers
LLMProvider = Literal["openai", "anthropic", "gemini"]

# Environment variable names for each provider
PROVIDER_API_KEY_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# Default models for each provider
DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4",
    "anthropic": "claude-3-5-sonnet-20241022",
    "gemini": "gemini-2.0-flash",
}


class LLMConfig(BaseModel):
    """Configuration for LLM provider settings.

    Attributes:
        provider: The LLM provider to use (openai, anthropic, or gemini).
        model: The model identifier to use for generation and oracle.
        api_key: Optional API key (can be set via environment variable).
        temperature: Temperature for LLM responses (0.0 to 1.0).
        max_tokens: Maximum tokens for LLM responses.
    """

    provider: LLMProvider = Field(
        default="openai",
        description="LLM provider to use for test generation and oracle",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model identifier for the selected provider (uses provider default if not set)",
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

    def get_model(self) -> str:
        """Get the model name, using provider default if not specified.

        Returns:
            The model identifier string.
        """
        if self.model:
            return self.model
        return DEFAULT_MODELS.get(self.provider, "gpt-4")

    def get_api_key(self) -> str:
        """Get the API key from config or environment variable.

        Returns:
            The API key string.

        Raises:
            ValueError: If no API key is found in config or environment.
        """
        if self.api_key:
            return self.api_key

        env_var = PROVIDER_API_KEY_ENV_VARS.get(self.provider, "OPENAI_API_KEY")
        api_key = os.environ.get(env_var)

        if not api_key:
            raise ValueError(
                f"No API key found. Set {env_var} environment variable "
                f"or provide api_key in configuration."
            )

        return api_key


class ComponentLLMConfig(BaseModel):
    """Per-component LLM configuration overrides.

    Allows different LLM settings for different components (generator, oracle, etc.).

    Attributes:
        provider: Override the LLM provider for this component.
        model: Override the model for this component.
        temperature: Override the temperature for this component.
        max_tokens: Override the max tokens for this component.
    """

    provider: Optional[LLMProvider] = Field(
        default=None,
        description="Override LLM provider for this component",
    )
    model: Optional[str] = Field(
        default=None,
        description="Override model for this component",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override temperature for this component",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Override max tokens for this component",
    )

    def apply_to(self, base_config: LLMConfig) -> LLMConfig:
        """Apply this component's overrides to a base LLM config.

        Args:
            base_config: The base LLM configuration to override.

        Returns:
            A new LLMConfig with overrides applied.
        """
        return LLMConfig(
            provider=self.provider if self.provider is not None else base_config.provider,
            model=self.model if self.model is not None else base_config.model,
            temperature=self.temperature if self.temperature is not None else base_config.temperature,
            max_tokens=self.max_tokens if self.max_tokens is not None else base_config.max_tokens,
        )


class MCPProbeConfig(BaseModel):
    """Main configuration for MCP-Probe-Pilot.

    This model represents the mcp-probe-service-properties.json configuration file.

    Attributes:
        project_code: Unique identifier for the MCP server project.
        server_command: Command to start the MCP server.
        transport: Transport protocol (currently only stdio supported).
        regenerate_tests: Whether to force regeneration of test cases.
        service_url: URL of the mcp-probe-service API.
        llm_provider: Default LLM provider for all components.
        llm_model: Default model to use for LLM operations.
        llm_temperature: Default temperature for LLM responses.
        llm_max_tokens: Default maximum tokens for LLM responses.
        generator_llm: Optional LLM config overrides for test generator.
        oracle_llm: Optional LLM config overrides for oracle.
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
    service_url: str = Field(
        default="http://localhost:8080",
        description="URL of the mcp-probe-service API",
    )
    llm_provider: LLMProvider = Field(
        default="gemini",
        description="Default LLM provider for all components",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Default model to use for LLM operations (uses provider default if not set)",
    )
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Default temperature for LLM responses",
    )
    llm_max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Default maximum tokens for LLM responses",
    )
    generator_llm: Optional[ComponentLLMConfig] = Field(
        default=None,
        description="LLM configuration overrides for test generator component",
    )
    oracle_llm: Optional[ComponentLLMConfig] = Field(
        default=None,
        description="LLM configuration overrides for oracle component",
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
    max_test_cases: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum number of test cases to generate",
    )
    max_ground_truths: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum number of ground truths to generate",
    )
    mcp_source_code_path: Optional[str] = Field(
        default=None,
        description="Path to the MCP server source code",
    )

    @field_validator("service_url")
    @classmethod
    def validate_service_url(cls, v: str) -> str:
        """Validate service_url is a valid URL.

        Args:
            v: The service URL value.

        Returns:
            The validated service URL.

        Raises:
            ValueError: If service URL is not valid.
        """
        if not v.startswith(("http://", "https://")):
            raise ValueError("service_url must start with http:// or https://")
        return v.rstrip("/")

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
        """Create a base LLMConfig instance from this configuration.

        Returns:
            LLMConfig with default settings from this configuration.
        """
        return LLMConfig(
            provider=self.llm_provider,
            model=self.llm_model,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
        )

    def get_generator_llm_config(self) -> LLMConfig:
        """Get LLM config for the test generator component.

        Returns:
            LLMConfig with generator-specific overrides applied.
        """
        base_config = self.get_llm_config()
        if self.generator_llm:
            return self.generator_llm.apply_to(base_config)
        return base_config

    def get_oracle_llm_config(self) -> LLMConfig:
        """Get LLM config for the oracle component.

        Returns:
            LLMConfig with oracle-specific overrides applied.
        """
        base_config = self.get_llm_config()
        if self.oracle_llm:
            return self.oracle_llm.apply_to(base_config)
        return base_config

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

    # Override from environment variables
    env_overrides = {
        "service_url": os.environ.get("MCP_PROBE_SERVICE_URL"),
        "project_code": os.environ.get("MCP_PROBE_PROJECT_CODE"),
        "server_command": os.environ.get("MCP_SERVER_COMMAND"),
        "mcp_source_code_path": os.environ.get("MCP_SOURCE_CODE_PATH"),
    }
    
    # Remove None values
    env_overrides = {k: v for k, v in env_overrides.items() if v is not None}
    
    # Update config data with overrides
    config_data.update(env_overrides)

    # Auto-inject --directory if using uv and source path is present
    server_cmd = config_data.get("server_command", "")
    source_path = config_data.get("mcp_source_code_path")
    
    if source_path and server_cmd.startswith("uv"):
        # If it already has --directory, it might be complex to replace. 
        # For simplicity, if it's "uv run ...", make it "uv --directory <path> run ..."
        # If it already has --directory, we skip to avoid messing up.
        if "--directory" not in server_cmd:
            parts = server_cmd.split(None, 1) # Split at first whitespace
            if len(parts) > 1:
                config_data["server_command"] = f"uv --directory {source_path} {parts[1]}"
            else:
                config_data["server_command"] = f"uv --directory {source_path}"

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
