"""Ground truth storage and retrieval for MCP-Probe-Pilot.

This module provides the GroundTruthStore class for persisting and retrieving
ground truth data using file-based JSON storage per project.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

import httpx

from .models import (
    GroundTruthCollection,
    GroundTruthSpec,
    WorkflowGroundTruth,
)

logger = logging.getLogger(__name__)


class GroundTruthStoreError(Exception):
    """Exception raised when ground truth store operations fail."""

    pass


class GroundTruthStore:
    """File-based storage for ground truth data.

    Stores ground truths in a JSON file at:
    `{output_dir}/{project_code}/ground_truths.json`

    Example:
        ```python
        store = GroundTruthStore("my-project", ".mcp-probe")

        # Save ground truths
        store.save(ground_truths, workflow_ground_truths)

        # Load all ground truths
        collection = store.load()

        # Load specific ground truth
        gt = store.load_by_id("gt_tool_auth_login")

        # Update a ground truth
        store.update("gt_tool_auth_login", updated_ground_truth)

        # Sync to service
        await store.sync_to_service("http://localhost:8000")
        ```

    Attributes:
        project_code: Unique identifier for the project.
        output_dir: Base directory for output files.
        storage_path: Full path to the ground truths JSON file.
    """

    FILENAME = "ground_truths.json"

    def __init__(
        self,
        project_code: str,
        output_dir: str = ".mcp-probe",
    ) -> None:
        """Initialize the ground truth store.

        Args:
            project_code: Unique identifier for the project.
            output_dir: Base directory for output files (default: .mcp-probe).
        """
        self.project_code = project_code
        self.output_dir = Path(output_dir)
        self._storage_path: Optional[Path] = None

    @property
    def storage_path(self) -> Path:
        """Get the full path to the ground truths JSON file."""
        if self._storage_path is None:
            self._storage_path = self.output_dir / self.project_code / self.FILENAME
        return self._storage_path

    def _ensure_directory(self) -> None:
        """Ensure the storage directory exists."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        ground_truths: dict[str, GroundTruthSpec],
        workflow_ground_truths: Optional[dict[str, WorkflowGroundTruth]] = None,
    ) -> GroundTruthCollection:
        """Save ground truths to file storage.

        Creates a new collection or increments the version of an existing one.

        Args:
            ground_truths: Dictionary of capability ground truths keyed by ID.
            workflow_ground_truths: Optional dictionary of workflow ground truths.

        Returns:
            The saved GroundTruthCollection.

        Raises:
            GroundTruthStoreError: If saving fails.
        """
        try:
            self._ensure_directory()

            # Check for existing collection to get version
            version = 1
            if self.storage_path.exists():
                existing = self.load()
                version = existing.version + 1

            collection = GroundTruthCollection(
                project_code=self.project_code,
                version=version,
                ground_truths=ground_truths,
                workflow_ground_truths=workflow_ground_truths or {},
            )

            with open(self.storage_path, "w") as f:
                json.dump(collection.to_dict(), f, indent=2)

            logger.info(
                f"Saved {collection.total_count} ground truths to {self.storage_path} "
                f"(version {version})"
            )

            return collection

        except Exception as e:
            raise GroundTruthStoreError(f"Failed to save ground truths: {e}") from e

    def load(self) -> GroundTruthCollection:
        """Load all ground truths from file storage.

        Returns:
            GroundTruthCollection containing all stored ground truths.

        Raises:
            GroundTruthStoreError: If loading fails or file doesn't exist.
        """
        if not self.storage_path.exists():
            raise GroundTruthStoreError(
                f"Ground truth file not found: {self.storage_path}. "
                f"Run test generation first."
            )

        try:
            with open(self.storage_path) as f:
                data = json.load(f)

            collection = GroundTruthCollection.from_dict(data)
            logger.debug(
                f"Loaded {collection.total_count} ground truths from {self.storage_path}"
            )

            return collection

        except json.JSONDecodeError as e:
            raise GroundTruthStoreError(
                f"Invalid JSON in ground truth file: {e}"
            ) from e
        except Exception as e:
            raise GroundTruthStoreError(f"Failed to load ground truths: {e}") from e

    def load_by_id(
        self,
        ground_truth_id: str,
    ) -> Optional[Union[GroundTruthSpec, WorkflowGroundTruth]]:
        """Load a specific ground truth by ID.

        Args:
            ground_truth_id: The ground truth ID to look up.

        Returns:
            The ground truth if found, None otherwise.

        Raises:
            GroundTruthStoreError: If loading fails.
        """
        collection = self.load()
        return collection.get(ground_truth_id)

    def update(
        self,
        ground_truth_id: str,
        ground_truth: Union[GroundTruthSpec, WorkflowGroundTruth],
    ) -> bool:
        """Update an existing ground truth.

        Args:
            ground_truth_id: The ID of the ground truth to update.
            ground_truth: The updated ground truth data.

        Returns:
            True if updated, False if not found.

        Raises:
            GroundTruthStoreError: If update fails.
        """
        try:
            collection = self.load()

            # Determine which collection to update
            if isinstance(ground_truth, WorkflowGroundTruth):
                if ground_truth_id not in collection.workflow_ground_truths:
                    return False
                collection.workflow_ground_truths[ground_truth_id] = ground_truth
            else:
                if ground_truth_id not in collection.ground_truths:
                    return False
                collection.ground_truths[ground_truth_id] = ground_truth

            # Save without incrementing version (it's an update, not a new save)
            with open(self.storage_path, "w") as f:
                json.dump(collection.to_dict(), f, indent=2)

            logger.debug(f"Updated ground truth: {ground_truth_id}")
            return True

        except GroundTruthStoreError:
            raise
        except Exception as e:
            raise GroundTruthStoreError(f"Failed to update ground truth: {e}") from e

    def delete(self, ground_truth_id: str) -> bool:
        """Delete a ground truth by ID.

        Args:
            ground_truth_id: The ID of the ground truth to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            GroundTruthStoreError: If deletion fails.
        """
        try:
            collection = self.load()

            if not collection.remove(ground_truth_id):
                return False

            # Save the updated collection
            with open(self.storage_path, "w") as f:
                json.dump(collection.to_dict(), f, indent=2)

            logger.debug(f"Deleted ground truth: {ground_truth_id}")
            return True

        except GroundTruthStoreError:
            raise
        except Exception as e:
            raise GroundTruthStoreError(f"Failed to delete ground truth: {e}") from e

    def exists(self) -> bool:
        """Check if ground truth storage exists for this project.

        Returns:
            True if storage file exists, False otherwise.
        """
        return self.storage_path.exists()

    def clear(self) -> bool:
        """Clear all ground truths for this project.

        Returns:
            True if cleared, False if file didn't exist.
        """
        if not self.storage_path.exists():
            return False

        self.storage_path.unlink()
        logger.info(f"Cleared ground truths for project: {self.project_code}")
        return True

    async def sync_to_service(
        self,
        service_url: str,
        timeout: float = 30.0,
    ) -> bool:
        """Sync ground truths to mcp-probe-service.

        Uploads all ground truths to the service for centralized storage.

        Args:
            service_url: Base URL of the mcp-probe-service API.
            timeout: Request timeout in seconds.

        Returns:
            True if sync successful, False otherwise.

        Raises:
            GroundTruthStoreError: If sync fails.
        """
        try:
            collection = self.load()

            # Prepare payload for bulk upload
            payload = {
                "ground_truths": [
                    gt.model_dump() for gt in collection.ground_truths.values()
                ],
                "workflow_ground_truths": [
                    gt.model_dump() for gt in collection.workflow_ground_truths.values()
                ],
            }

            url = f"{service_url.rstrip('/')}/api/projects/{self.project_code}/ground-truths"

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)

                if response.status_code in (200, 201):
                    logger.info(
                        f"Synced {collection.total_count} ground truths to service"
                    )
                    return True
                else:
                    logger.warning(
                        f"Failed to sync ground truths: {response.status_code} - "
                        f"{response.text}"
                    )
                    return False

        except httpx.RequestError as e:
            logger.warning(f"Failed to connect to service: {e}")
            return False
        except GroundTruthStoreError:
            raise
        except Exception as e:
            raise GroundTruthStoreError(f"Failed to sync ground truths: {e}") from e

    @classmethod
    def from_scenario_set(
        cls,
        project_code: str,
        scenario_set: "ScenarioSet",
        output_dir: str = ".mcp-probe",
    ) -> "GroundTruthStore":
        """Create a store and populate it from a ScenarioSet.

        This is a convenience method for saving ground truths extracted
        from test generation.

        Args:
            project_code: Unique identifier for the project.
            scenario_set: ScenarioSet containing ground truths.
            output_dir: Base directory for output files.

        Returns:
            GroundTruthStore with saved ground truths.
        """
        # Import here to avoid circular import
        from ..generators.models import ScenarioSet

        store = cls(project_code, output_dir)
        store.save(
            ground_truths=scenario_set.ground_truths,
            workflow_ground_truths=scenario_set.workflow_ground_truths,
        )
        return store
