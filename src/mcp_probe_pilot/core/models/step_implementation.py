"""Models for step implementation generation results."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class StepImplementationResult(BaseModel):
    """Summary of a step implementation generation run."""

    steps_generated: int = 0
    steps_skipped: int = 0
    output_file: Optional[Path] = None
    validation_errors: list[str] = Field(default_factory=list)
    discovered_dependencies: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
