"""Models for feature-file generation results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerationResult(BaseModel):
    """Summary of a feature-file generation run."""

    files_generated: int = 0
    files_failed: int = 0
    validation_warnings: list[str] = Field(default_factory=list)
