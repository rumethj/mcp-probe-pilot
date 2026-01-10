"""Pytest configuration and shared fixtures for MCP-Probe-Pilot tests."""

import json
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files.

    Yields:
        Path to the temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config() -> dict:
    """Provide a sample MCP-Probe configuration dictionary.

    Returns:
        Dictionary with sample configuration values.
    """
    return {
        "project_code": "test-server",
        "server_command": "python -m test_server",
        "transport": "stdio",
        "regenerate_tests": False,
        "llm_provider": "openai",
        "llm_model": "gpt-4",
    }


@pytest.fixture
def config_file(temp_dir: Path, sample_config: dict) -> Path:
    """Create a temporary configuration file.

    Args:
        temp_dir: Temporary directory fixture.
        sample_config: Sample configuration fixture.

    Returns:
        Path to the created configuration file.
    """
    config_path = temp_dir / "mcp-probe-service-properties.json"
    config_path.write_text(json.dumps(sample_config, indent=2))
    return config_path


@pytest.fixture
def mock_env_vars() -> Generator[None, None, None]:
    """Set up mock environment variables for LLM API keys.

    Yields:
        None - environment is configured for the duration of the test.
    """
    original_openai = os.environ.get("OPENAI_API_KEY")
    original_anthropic = os.environ.get("ANTHROPIC_API_KEY")

    os.environ["OPENAI_API_KEY"] = "test-openai-key"
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"

    yield

    # Restore original values
    if original_openai is not None:
        os.environ["OPENAI_API_KEY"] = original_openai
    else:
        os.environ.pop("OPENAI_API_KEY", None)

    if original_anthropic is not None:
        os.environ["ANTHROPIC_API_KEY"] = original_anthropic
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
