"""Unit tests for the TestExecutor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_probe_pilot.execute.executor import (
    DEFAULT_TIMEOUT_SECONDS,
    ExecutorError,
    TestExecutor,
    VENV_DIR_NAME,
)


# ------------------------------------------------------------------
# Construction and paths
# ------------------------------------------------------------------


class TestExecutorInit:
    def test_default_paths(self, tmp_path: Path) -> None:
        executor = TestExecutor(repo_root=tmp_path, dependencies=["behave"])

        assert executor.repo_root == tmp_path
        assert executor.dependencies == ["behave"]
        assert executor.timeout == DEFAULT_TIMEOUT_SECONDS
        assert executor._venv_path == tmp_path / VENV_DIR_NAME

    def test_deduplicates_dependencies(self, tmp_path: Path) -> None:
        executor = TestExecutor(
            repo_root=tmp_path,
            dependencies=["behave", "mcp", "behave"],
        )
        assert executor.dependencies == ["behave", "mcp"]


# ------------------------------------------------------------------
# setup_environment
# ------------------------------------------------------------------


class TestSetupEnvironment:
    @patch("mcp_probe_pilot.execute.executor.subprocess.run")
    def test_creates_venv_and_installs(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        executor = TestExecutor(repo_root=tmp_path, dependencies=["behave"])
        executor.setup_environment()

        assert mock_run.call_count >= 2

    @patch("mcp_probe_pilot.execute.executor.subprocess.run")
    def test_venv_creation_failure_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="uv not found")
        executor = TestExecutor(repo_root=tmp_path, dependencies=["behave"])

        with pytest.raises(ExecutorError, match="Failed to create venv"):
            executor.setup_environment()

    @patch("mcp_probe_pilot.execute.executor.subprocess.run")
    def test_reuses_existing_venv(self, mock_run: MagicMock, tmp_path: Path) -> None:
        venv = tmp_path / VENV_DIR_NAME / "bin"
        venv.mkdir(parents=True)
        (venv / "python").touch()

        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        executor = TestExecutor(repo_root=tmp_path, dependencies=["behave"])
        executor.setup_environment()

        calls = [str(c) for c in mock_run.call_args_list]
        assert not any("uv venv" in c for c in calls)


# ------------------------------------------------------------------
# run_tests
# ------------------------------------------------------------------


class TestRunTests:
    def test_missing_python_raises(self, tmp_path: Path) -> None:
        executor = TestExecutor(repo_root=tmp_path, dependencies=[])
        with pytest.raises(ExecutorError, match="Venv python not found"):
            executor.run_tests()

    def test_missing_features_dir_raises(self, tmp_path: Path) -> None:
        venv = tmp_path / VENV_DIR_NAME / "bin"
        venv.mkdir(parents=True)
        (venv / "python").touch()

        executor = TestExecutor(repo_root=tmp_path, dependencies=[])
        with pytest.raises(ExecutorError, match="Features directory not found"):
            executor.run_tests()

    @patch("mcp_probe_pilot.execute.executor.subprocess.run")
    def test_successful_run_parses_results(self, mock_run: MagicMock, tmp_path: Path) -> None:
        venv = tmp_path / VENV_DIR_NAME / "bin"
        venv.mkdir(parents=True)
        (venv / "python").touch()
        features = tmp_path / "features"
        features.mkdir()

        behave_json = [{
            "name": "test feature",
            "elements": [{
                "type": "scenario",
                "name": "test scenario",
                "steps": [{
                    "result": {"status": "passed", "duration": 0.1},
                }],
            }],
        }]
        results_file = features / "test-results.json"

        def _fake_run(*args, **kwargs):
            results_file.write_text(json.dumps(behave_json))
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _fake_run

        executor = TestExecutor(repo_root=tmp_path, dependencies=[])
        result = executor.run_tests()

        assert result.success
        assert result.passed == 1
        assert result.total_scenarios == 1

    @patch("mcp_probe_pilot.execute.executor.subprocess.run")
    def test_timeout_returns_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        import subprocess
        venv = tmp_path / VENV_DIR_NAME / "bin"
        venv.mkdir(parents=True)
        (venv / "python").touch()
        features = tmp_path / "features"
        features.mkdir()

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="behave", timeout=5)

        executor = TestExecutor(repo_root=tmp_path, dependencies=[], timeout=5)
        result = executor.run_tests()

        assert not result.success
        assert "timed out" in result.stderr


# ------------------------------------------------------------------
# cleanup
# ------------------------------------------------------------------


class TestCleanup:
    def test_removes_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / VENV_DIR_NAME
        venv.mkdir()
        (venv / "file.txt").write_text("x")

        executor = TestExecutor(repo_root=tmp_path, dependencies=[])
        executor.cleanup()

        assert not venv.exists()

    def test_no_error_if_no_venv(self, tmp_path: Path) -> None:
        executor = TestExecutor(repo_root=tmp_path, dependencies=[])
        executor.cleanup()
