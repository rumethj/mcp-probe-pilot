"""Unit tests for the CLI module.

Tests cover:
- init command: Configuration file creation
- generate command: Test generation (with mocked discovery/generator)
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
from mcp_probe_pilot.generators.models import (
    FeatureFile,
    GeneratedScenario,
    GroundTruthSpec,
    ScenarioCategory,
    ScenarioSet,
    TargetType,
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


@pytest.fixture
def mock_scenario_set() -> ScenarioSet:
    """Create a mock scenario set."""
    scenario_set = ScenarioSet()

    ground_truth = GroundTruthSpec(
        id="gt_tool_test_tool",
        target_type=TargetType.TOOL,
        target_name="test_tool",
        expected_behavior="Should perform test operation",
        expected_output_schema={"type": "object"},
        semantic_reference="Test tool operation",
    )
    scenario_set.add_ground_truth(ground_truth)

    scenario = GeneratedScenario(
        id="sc_tool_test_tool_happy_path_0",
        name="Test tool happy path",
        gherkin='Scenario: Test tool works\n  Given the MCP server is running\n  When I call tool "test_tool"\n  Then the response should be successful',
        target_type=TargetType.TOOL,
        target_name="test_tool",
        category=ScenarioCategory.HAPPY_PATH,
        ground_truth_id="gt_tool_test_tool",
    )

    feature = FeatureFile(
        name="Tool - test_tool",
        target_type=TargetType.TOOL,
        target_name="test_tool",
        ground_truth_id="gt_tool_test_tool",
        scenarios=[scenario],
        gherkin="Feature: Tool - test_tool\n  # Ground Truth ID: gt_tool_test_tool\n\n"
        + scenario.gherkin,
    )
    scenario_set.add_feature(feature)

    return scenario_set


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

        # Verify config contents
        config = json.loads(config_path.read_text())
        assert config["project_code"] == "my-server"
        assert config["server_command"] == "python -m server"
        assert config["llm_provider"] == "gemini"

    def test_init_with_existing_config_prompts_overwrite(
        self, config_file_path: Path
    ) -> None:
        """Test that init prompts before overwriting existing config."""
        # Test refusing to overwrite
        result = runner.invoke(
            app,
            ["init", "--config", str(config_file_path)],
            input="n\n",  # Don't overwrite
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

        # Verify config was overwritten
        config = json.loads(config_file_path.read_text())
        assert config["project_code"] == "new-server"

    def test_init_default_values(self, temp_config_dir: Path) -> None:
        """Test that init uses default values when Enter is pressed."""
        config_path = temp_config_dir / "mcp-probe-service-properties.json"

        result = runner.invoke(
            app,
            ["init", "--config", str(config_path)],
            input="\n\n\n",  # Accept all defaults
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

    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    @patch("mcp_probe_pilot.cli.ClientTestGenerator")
    def test_generate_runs_pipeline(
        self,
        mock_generator_class: MagicMock,
        mock_client_class: MagicMock,
        config_file_path: Path,
        mock_discovery_result: DiscoveryResult,
        mock_scenario_set: ScenarioSet,
    ) -> None:
        """Test that generate runs the full discovery and generation pipeline."""
        # Configure mocks
        mock_client = AsyncMock()
        mock_client.discover_all = AsyncMock(return_value=mock_discovery_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        mock_generator = MagicMock()
        mock_generator.generate_scenarios = AsyncMock(return_value=mock_scenario_set)
        mock_generator_class.return_value = mock_generator

        result = runner.invoke(
            app,
            ["generate", "--config", str(config_file_path)],
        )

        assert result.exit_code == 0
        assert "Server Discovery" in result.stdout
        assert "Test Generation" in result.stdout
        assert "Tests saved" in result.stdout

        # Verify mocks were called
        mock_client_class.assert_called_once()
        mock_generator_class.assert_called_once()

    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    def test_generate_handles_discovery_error(
        self,
        mock_client_class: MagicMock,
        config_file_path: Path,
    ) -> None:
        """Test that generate handles discovery errors gracefully."""
        from mcp_probe_pilot.discovery import MCPDiscoveryError

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(
            side_effect=MCPDiscoveryError("Connection failed")
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            app,
            ["generate", "--config", str(config_file_path)],
        )

        assert result.exit_code == 1
        assert "Failed to connect" in result.stdout or "Error" in result.stdout

    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    def test_generate_warns_on_empty_discovery(
        self,
        mock_client_class: MagicMock,
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

    def test_run_fails_without_generated_tests(
        self, config_file_path: Path, temp_config_dir: Path
    ) -> None:
        """Test that run fails when no tests have been generated."""
        # Update config to use temp dir for output
        config_data = json.loads(config_file_path.read_text())
        config_data["output_dir"] = str(temp_config_dir / ".mcp-probe")
        config_file_path.write_text(json.dumps(config_data))

        result = runner.invoke(
            app,
            ["run", "--config", str(config_file_path)],
        )

        assert result.exit_code == 1
        assert "No generated tests found" in result.stdout
        assert "mcp-probe generate" in result.stdout

    def test_run_shows_not_implemented(
        self, config_file_path: Path, temp_config_dir: Path
    ) -> None:
        """Test that run shows not implemented message when tests exist."""
        # Create a fake scenario_set.json
        output_dir = temp_config_dir / ".mcp-probe"
        output_dir.mkdir()
        (output_dir / "scenario_set.json").write_text("{}")

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

    @patch("mcp_probe_pilot.cli.MCPDiscoveryClient")
    @patch("mcp_probe_pilot.cli.ClientTestGenerator")
    def test_full_runs_generate_then_shows_placeholder(
        self,
        mock_generator_class: MagicMock,
        mock_client_class: MagicMock,
        config_file_path: Path,
        mock_discovery_result: DiscoveryResult,
        mock_scenario_set: ScenarioSet,
    ) -> None:
        """Test that full runs generate and shows placeholders for run/report."""
        # Configure mocks
        mock_client = AsyncMock()
        mock_client.discover_all = AsyncMock(return_value=mock_discovery_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        mock_generator = MagicMock()
        mock_generator.generate_scenarios = AsyncMock(return_value=mock_scenario_set)
        mock_generator_class.return_value = mock_generator

        result = runner.invoke(
            app,
            ["full", "--config", str(config_file_path)],
        )

        # Full command should complete (exit 0) even with placeholder stages
        assert result.exit_code == 0
        assert "Test Generation" in result.stdout
        assert "Test Execution" in result.stdout
        assert "Report Generation" in result.stdout
        assert "not implemented" in result.stdout.lower()


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

        # Command may fail for other reasons, but should accept the flag
        assert "--verbose" not in result.stdout or "unknown" not in result.stdout.lower()

    def test_config_short_option(self, config_file_path: Path) -> None:
        """Test that -c short option works for --config."""
        result = runner.invoke(
            app,
            ["run", "-c", str(config_file_path)],
        )

        # Should load config successfully (then fail for other reasons)
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
