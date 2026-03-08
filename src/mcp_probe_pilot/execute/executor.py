"""Test executor: creates an isolated venv via uv, installs deps, runs behave."""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp_probe_pilot.core.models.execution import TestExecutionResult

logger = logging.getLogger(__name__)

VENV_DIR_NAME = ".mcp-probe-venv"
RESULTS_FILENAME = "test-results.json"
DEFAULT_TIMEOUT_SECONDS = 300


class ExecutorError(Exception):
    """Raised when the executor encounters a fatal problem."""


class TestExecutor:
    """Creates an isolated venv, installs dependencies, and runs behave tests.

    Parameters
    ----------
    repo_root:
        Path to the target repository (working directory for behave).
    dependencies:
        Pre-merged list of pip packages to install into the venv.
    timeout:
        Maximum seconds for the behave run before it is killed.
    """

    def __init__(
        self,
        repo_root: Path,
        dependencies: list[str],
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.repo_root = repo_root
        self.dependencies = list(dict.fromkeys(dependencies))
        self.timeout = timeout

        self._venv_path = repo_root / VENV_DIR_NAME
        self._python = self._venv_path / "bin" / "python"
        self._features_dir = repo_root / "features"
        self._results_file = self._features_dir / RESULTS_FILENAME

    # ------------------------------------------------------------------
    # Environment setup
    # ------------------------------------------------------------------

    def setup_environment(self) -> None:
        """Create the venv (if needed) and install dependencies."""
        self._create_venv()
        self._install_dependencies()

    def _create_venv(self) -> None:
        if self._python.exists():
            logger.info("Venv already exists at %s, reusing", self._venv_path)
            return

        logger.info("Creating venv at %s", self._venv_path)
        result = subprocess.run(
            ["uv", "venv", str(self._venv_path), "--python", sys.executable],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ExecutorError(
                f"Failed to create venv: {result.stderr.strip()}"
            )
        logger.info("Venv created successfully")

    def _install_dependencies(self) -> None:
        if not self.dependencies:
            logger.warning("No dependencies to install")
            return

        logger.info(
            "Installing %d dependencies: %s",
            len(self.dependencies),
            self.dependencies,
        )
        result = subprocess.run(
            [
                "uv", "pip", "install",
                "--python", str(self._python),
                *self.dependencies,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ExecutorError(
                f"Failed to install dependencies: {result.stderr.strip()}"
            )
        logger.info("Dependencies installed successfully")

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def run_tests(self) -> TestExecutionResult:
        """Run ``behave`` inside the venv and return structured results."""
        if not self._python.exists():
            raise ExecutorError(
                f"Venv python not found at {self._python}. "
                "Call setup_environment() first."
            )

        if not self._features_dir.exists():
            raise ExecutorError(
                f"Features directory not found at {self._features_dir}"
            )

        self._results_file.unlink(missing_ok=True)

        logger.info(
            "Running behave in %s (timeout=%ds)", self.repo_root, self.timeout
        )

        try:
            proc = subprocess.run(
                [
                    str(self._python), "-m", "behave",
                    str(self._features_dir),
                    "--format", "json",
                    "--outfile", str(self._results_file),
                    "--no-capture",
                ],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._build_env(),
            )
        except subprocess.TimeoutExpired:
            logger.error("behave timed out after %ds", self.timeout)
            return TestExecutionResult(
                success=False,
                stderr=f"behave timed out after {self.timeout}s",
            )

        if proc.returncode != 0:
            logger.warning("behave exited with code %d", proc.returncode)
            if proc.stderr:
                logger.warning("behave stderr:\n%s", proc.stderr.strip())
            if proc.stdout:
                logger.info("behave stdout:\n%s", proc.stdout.strip())

        return self._parse_results(proc)

    def _build_env(self) -> dict[str, str]:
        """Build environment for the subprocess, inheriting current env."""
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(self._venv_path)
        env["PATH"] = f"{self._venv_path / 'bin'}:{env.get('PATH', '')}"
        return env

    def _parse_results(self, proc: subprocess.CompletedProcess) -> TestExecutionResult:
        """Parse the behave JSON output file into a TestExecutionResult."""
        raw_json: list[dict[str, Any]] = []

        if self._results_file.exists():
            try:
                raw_json = json.loads(
                    self._results_file.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to parse behave JSON output: %s", exc)

        passed = 0
        failed = 0
        errored = 0
        skipped = 0
        total_duration = 0.0

        for feature in raw_json:
            for element in feature.get("elements", []):
                if element.get("type") != "scenario":
                    continue

                scenario_status = "passed"
                for step in element.get("steps", []):
                    step_result = step.get("result", {})
                    status = step_result.get("status", "undefined")
                    total_duration += step_result.get("duration", 0.0)

                    if status == "failed":
                        scenario_status = "failed"
                    elif status in ("undefined", "error"):
                        scenario_status = "errored"
                    elif status == "skipped" and scenario_status == "passed":
                        scenario_status = "skipped"

                if scenario_status == "passed":
                    passed += 1
                elif scenario_status == "failed":
                    failed += 1
                elif scenario_status == "errored":
                    errored += 1
                else:
                    skipped += 1

        total = passed + failed + errored + skipped

        return TestExecutionResult(
            success=(proc.returncode == 0),
            total_scenarios=total,
            passed=passed,
            failed=failed,
            errored=errored,
            skipped=skipped,
            duration=total_duration,
            raw_json=raw_json,
            output_file=self._results_file if self._results_file.exists() else None,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove the venv directory."""
        if self._venv_path.exists():
            logger.info("Removing venv at %s", self._venv_path)
            shutil.rmtree(self._venv_path)
