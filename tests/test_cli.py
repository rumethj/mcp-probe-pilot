"""Unit tests for the CLI module.

Tests cover:
- init command: Configuration file creation
- generate command: Discovery + placeholder behavior
- run command: Placeholder behavior
- report command: Placeholder behavior
- full command: Pipeline orchestration
- Common options: --config, --verbose
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_probe_pilot.cli import app
from mcp_probe_pilot.discovery.models import (
    DiscoveryResult,
    ServerCapabilities,
    ServerInfo,
    ToolInfo,
)

runner = CliRunner()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary directory and change to it for tests."""
    return tmp_path


@pytest.fixture
def sample_config_dict() -> dict:
    """Provide a sample configuration dictionary."""
    return {
        "project_code": "test-server",
        "server_command": "python -m test_server",
        "transport": "stdio",
        "llm_provider": "gemini",
    }


@pytest.fixture
def config_file_path(temp_config_dir: Path, sample_config_dict: dict) -> Path:
    """Create a configuration file for testing."""
    config_path = temp_config_dir / "mcp-probe-service-properties.json"
    config_path.write_text(json.dumps(sample_config_dict, indent=2))
    return config_path


@pytest.fixture
def mock_discovery_result() -> DiscoveryResult:
    """Create a mock discovery result."""
    return DiscoveryResult(
        tools=[
            ToolInfo(
                name="test_tool",
                description="A test tool",
                input_schema={"type": "object", "properties": {}},
            ),
        ],
        resources=[],
        prompts=[],
        server_info=ServerInfo(
            name="test-server",
            version="1.0.0",
            capabilities=ServerCapabilities(tools=True),
        ),
    )


# =============================================================================
# Init Command Tests
# =============================================================================


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_config_file(self, temp_config_dir: Path) -> None:
        """Test that init creates a configuration file with prompted values."""
        config_path = temp_config_dir / "mcp-probe-service-properties.json"

        result = runner.invoke(
            app,
            ["init", "--config", str(config_path)],
            input="my-server\npython -m server\ngemini\n",
        )

        assert result.exit_code == 0
        assert config_path.exists()
        assert "Configuration saved" in result.stdout

        config = json.loads(config_path.read_text())
        assert config["project_code"] == "my-server"
        assert config["server_command"] == "python -m server"
        assert config["llm_provider"] == "gemini"

    def test_init_with_existing_config_prompts_overwrite(
        self, config_file_path: Path
    ) -> None:
        """Test that init prompts before overwriting existing config."""
        result = runner.invoke(
            app,
            ["init", "--config", str(config_file_path)],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Aborted" in result.stdout

    def test_init_with_existing_config_can_overwrite(
        self, config_file_path: Path
    ) -> None:
        """Test that init can overwrite existing config when confirmed."""
        result = runner.invoke(
            app,
            ["init", "--config", str(config_file_path)],
            input="y\nnew-server\npython -m new_server\nopenai\n",
        )

        assert result.exit_code == 0

        config = json.loads(config_file_path.read_text())
        assert config["project_code"] == "new-server"

    def test_init_default_values(self, temp_config_dir: Path) -> None:
        """Test that init uses default values when Enter is pressed."""
        config_path = temp_config_dir / "mcp-probe-service-properties.json"

        result = runner.invoke(
            app,
            ["init", "--config", str(config_path)],
            input="\n\n\n",
        )

        assert result.exit_code == 0
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert config["project_code"] == "my-mcp-server"
        assert config["server_command"] == "python -m my_server"
        assert config["llm_provider"] == "gemini"


# =============================================================================
# Generate Command Tests
# =============================================================================


class TestGenerateCommand:
    """Tests for the generate command."""

    def test_generate_fails_without_config(self, temp_config_dir: Path) -> None:
        """Test that generate fails gracefully when config is missing."""
        config_path = temp_config_dir / "nonexistent.json"

        result = runner.invoke(
            app,
            ["generate", "--config", str(config_path)],
        )

        assert result.exit_code == 1
        assert "Configuration file not found" in result.stdout
        assert "mcp-probe init" in result.stdout

    @patch("mcp_probe_pilot.cli.MCPProbeServiceClient")
    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    def test_generate_runs_discovery(
        self,
        mock_client_class: MagicMock,
        mock_service_class: MagicMock,
        config_file_path: Path,
        mock_discovery_result: DiscoveryResult,
    ) -> None:
        """Test that generate runs discovery and shows placeholder for generation."""
        mock_client = AsyncMock()
        mock_client.discover_all = AsyncMock(return_value=mock_discovery_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        mock_service = AsyncMock()
        mock_service.health_check = AsyncMock(
            return_value={"status": "healthy", "version": "0.1.0"}
        )
        mock_service.ensure_project_exists = AsyncMock(
            return_value={"project_code": "test-server"}
        )
        mock_service.__aenter__ = AsyncMock(return_value=mock_service)
        mock_service.__aexit__ = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        result = runner.invoke(
            app,
            ["generate", "--config", str(config_file_path)],
        )

        assert "Server Discovery" in result.stdout
        mock_client_class.assert_called_once()

    @patch("mcp_probe_pilot.cli.MCPProbeServiceClient")
    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    def test_generate_warns_on_empty_discovery(
        self,
        mock_client_class: MagicMock,
        mock_service_class: MagicMock,
        config_file_path: Path,
    ) -> None:
        """Test that generate warns when no capabilities are discovered."""
        empty_result = DiscoveryResult(
            tools=[],
            resources=[],
            prompts=[],
            server_info=ServerInfo(
                name="empty-server",
                version="1.0.0",
                capabilities=ServerCapabilities(),
            ),
        )

        mock_client = AsyncMock()
        mock_client.discover_all = AsyncMock(return_value=empty_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        mock_service = AsyncMock()
        mock_service.health_check = AsyncMock(
            return_value={"status": "healthy", "version": "0.1.0"}
        )
        mock_service.ensure_project_exists = AsyncMock(
            return_value={"project_code": "test-server"}
        )
        mock_service.__aenter__ = AsyncMock(return_value=mock_service)
        mock_service.__aexit__ = AsyncMock(return_value=None)
        mock_service_class.return_value = mock_service

        result = runner.invoke(
            app,
            ["generate", "--config", str(config_file_path)],
        )

        assert result.exit_code == 1
        assert "No tools or resources discovered" in result.stdout


# =============================================================================
# Run Command Tests
# =============================================================================


class TestRunCommand:
    """Tests for the run command."""

    def test_run_fails_without_config(self, temp_config_dir: Path) -> None:
        """Test that run fails gracefully when config is missing."""
        config_path = temp_config_dir / "nonexistent.json"

        result = runner.invoke(
            app,
            ["run", "--config", str(config_path)],
        )

        assert result.exit_code == 1
        assert "Configuration file not found" in result.stdout

    def test_run_shows_not_implemented(self, config_file_path: Path) -> None:
        """Test that run shows not implemented message."""
        result = runner.invoke(
            app,
            ["run", "--config", str(config_file_path)],
        )

        assert result.exit_code == 1
        assert "Not Implemented" in result.stdout
        assert "Test Runner" in result.stdout


# =============================================================================
# Report Command Tests
# =============================================================================


class TestReportCommand:
    """Tests for the report command."""

    def test_report_fails_without_config(self, temp_config_dir: Path) -> None:
        """Test that report fails gracefully when config is missing."""
        config_path = temp_config_dir / "nonexistent.json"

        result = runner.invoke(
            app,
            ["report", "--config", str(config_path)],
        )

        assert result.exit_code == 1
        assert "Configuration file not found" in result.stdout

    def test_report_shows_not_implemented(self, config_file_path: Path) -> None:
        """Test that report shows not implemented message."""
        result = runner.invoke(
            app,
            ["report", "--config", str(config_file_path)],
        )

        assert result.exit_code == 1
        assert "Not Implemented" in result.stdout
        assert "Report Generator" in result.stdout


# =============================================================================
# Full Command Tests
# =============================================================================


class TestFullCommand:
    """Tests for the full command."""

    def test_full_fails_without_config(self, temp_config_dir: Path) -> None:
        """Test that full fails gracefully when config is missing."""
        config_path = temp_config_dir / "nonexistent.json"

        result = runner.invoke(
            app,
            ["full", "--config", str(config_path)],
        )

        assert result.exit_code == 1
        assert "Configuration file not found" in result.stdout


# =============================================================================
# Version Command Tests
# =============================================================================


class TestVersionCommand:
    """Tests for the version command."""

    def test_version_displays_version(self) -> None:
        """Test that version command displays version info."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "mcp-probe version" in result.stdout
        assert "0.1.0" in result.stdout


# =============================================================================
# Common Options Tests
# =============================================================================


class TestCommonOptions:
    """Tests for common CLI options."""

    def test_verbose_flag_accepted(self, config_file_path: Path) -> None:
        """Test that --verbose flag is accepted by commands."""
        result = runner.invoke(
            app,
            ["run", "--config", str(config_file_path), "--verbose"],
        )

        assert "--verbose" not in result.stdout or "unknown" not in result.stdout.lower()

    def test_config_short_option(self, config_file_path: Path) -> None:
        """Test that -c short option works for --config."""
        result = runner.invoke(
            app,
            ["run", "-c", str(config_file_path)],
        )

        assert "Configuration file not found" not in result.stdout

    def test_help_available(self) -> None:
        """Test that --help displays usage information."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "generate" in result.stdout
        assert "run" in result.stdout
        assert "report" in result.stdout
        assert "full" in result.stdout

    def test_command_help_available(self) -> None:
        """Test that command-specific --help works."""
        for cmd in ["init", "generate", "run", "report", "full"]:
            result = runner.invoke(app, [cmd, "--help"])
            assert result.exit_code == 0
            assert "Usage:" in result.stdout or "Options:" in result.stdout
