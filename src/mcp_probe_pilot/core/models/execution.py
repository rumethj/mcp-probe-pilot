"""Models for test execution results."""

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class TestExecutionResult(BaseModel):
    """Structured result from a behave test run."""

    success: bool
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    duration: float = 0.0
    raw_json: list[dict[str, Any]] = Field(default_factory=list)
    output_file: Optional[Path] = None
    stdout: str = ""
    stderr: str = ""

    class Config:
        arbitrary_types_allowed = True
