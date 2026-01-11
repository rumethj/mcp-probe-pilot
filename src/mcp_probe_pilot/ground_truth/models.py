"""Ground truth data models for MCP-Probe-Pilot.

This module provides ground truth models for test assertions. It re-exports
the core models from generators.models and adds a collection model for
file-based storage with metadata.
"""

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# Re-export core ground truth models from generators
from ..generators.models import (
    GroundTruthSpec,
    TargetType,
    WorkflowGroundTruth,
)

__all__ = [
    "GroundTruthSpec",
    "WorkflowGroundTruth",
    "TargetType",
    "GroundTruthCollection",
]


class GroundTruthCollection(BaseModel):
    """Collection of ground truths with metadata for file storage.

    This model wraps both capability ground truths and workflow ground truths
    with project metadata for persistent storage.

    Attributes:
        project_code: Unique identifier for the project.
        version: Version number of this ground truth collection.
        created_at: Timestamp when the collection was created.
        updated_at: Timestamp when the collection was last updated.
        ground_truths: Dictionary of capability ground truths keyed by ID.
        workflow_ground_truths: Dictionary of workflow ground truths keyed by ID.
    """

    project_code: str = Field(..., description="Unique project identifier")
    version: int = Field(default=1, description="Version number of this collection")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the collection was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the collection was last updated",
    )
    ground_truths: dict[str, GroundTruthSpec] = Field(
        default_factory=dict,
        description="Capability ground truths keyed by ID",
    )
    workflow_ground_truths: dict[str, WorkflowGroundTruth] = Field(
        default_factory=dict,
        description="Workflow ground truths keyed by ID",
    )

    def add_ground_truth(self, ground_truth: GroundTruthSpec) -> None:
        """Add a capability ground truth to the collection.

        Args:
            ground_truth: The ground truth specification to add.
        """
        self.ground_truths[ground_truth.id] = ground_truth
        self.updated_at = datetime.utcnow()

    def add_workflow_ground_truth(self, ground_truth: WorkflowGroundTruth) -> None:
        """Add a workflow ground truth to the collection.

        Args:
            ground_truth: The workflow ground truth to add.
        """
        self.workflow_ground_truths[ground_truth.id] = ground_truth
        self.updated_at = datetime.utcnow()

    def get(self, ground_truth_id: str) -> Optional[Union[GroundTruthSpec, WorkflowGroundTruth]]:
        """Get a ground truth by ID.

        Searches both capability and workflow ground truths.

        Args:
            ground_truth_id: The ID to look up.

        Returns:
            The ground truth if found, None otherwise.
        """
        if ground_truth_id in self.ground_truths:
            return self.ground_truths[ground_truth_id]
        if ground_truth_id in self.workflow_ground_truths:
            return self.workflow_ground_truths[ground_truth_id]
        return None

    def remove(self, ground_truth_id: str) -> bool:
        """Remove a ground truth by ID.

        Args:
            ground_truth_id: The ID to remove.

        Returns:
            True if removed, False if not found.
        """
        if ground_truth_id in self.ground_truths:
            del self.ground_truths[ground_truth_id]
            self.updated_at = datetime.utcnow()
            return True
        if ground_truth_id in self.workflow_ground_truths:
            del self.workflow_ground_truths[ground_truth_id]
            self.updated_at = datetime.utcnow()
            return True
        return False

    @property
    def total_count(self) -> int:
        """Get the total number of ground truths in the collection."""
        return len(self.ground_truths) + len(self.workflow_ground_truths)

    @property
    def capability_count(self) -> int:
        """Get the number of capability ground truths."""
        return len(self.ground_truths)

    @property
    def workflow_count(self) -> int:
        """Get the number of workflow ground truths."""
        return len(self.workflow_ground_truths)

    def to_dict(self) -> dict[str, Any]:
        """Convert collection to a dictionary for JSON serialization.

        Returns:
            Dictionary representation of the collection.
        """
        return {
            "project_code": self.project_code,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ground_truths": {
                k: v.model_dump() for k, v in self.ground_truths.items()
            },
            "workflow_ground_truths": {
                k: v.model_dump() for k, v in self.workflow_ground_truths.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundTruthCollection":
        """Create a collection from a dictionary.

        Args:
            data: Dictionary representation of the collection.

        Returns:
            GroundTruthCollection instance.
        """
        ground_truths = {
            k: GroundTruthSpec(**v)
            for k, v in data.get("ground_truths", {}).items()
        }
        workflow_ground_truths = {
            k: WorkflowGroundTruth(**v)
            for k, v in data.get("workflow_ground_truths", {}).items()
        }

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            project_code=data["project_code"],
            version=data.get("version", 1),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
            ground_truths=ground_truths,
            workflow_ground_truths=workflow_ground_truths,
        )
