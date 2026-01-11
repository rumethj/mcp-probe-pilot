"""Ground Truth Store module.

This module provides storage and retrieval of ground truth data
for test assertions:
- Expected output schemas
- Expected value ranges
- Semantic reference descriptions
- Sample valid outputs

Example:
    ```python
    from mcp_probe_pilot.ground_truth import (
        GroundTruthStore,
        GroundTruthSpec,
        WorkflowGroundTruth,
        GroundTruthCollection,
    )

    # Create a store for a project
    store = GroundTruthStore("my-project", ".mcp-probe")

    # Save ground truths from test generation
    collection = store.save(ground_truths, workflow_ground_truths)

    # Load a specific ground truth
    gt = store.load_by_id("gt_tool_auth_login")

    # Sync to service
    await store.sync_to_service("http://localhost:8000")
    ```
"""

from .models import (
    GroundTruthCollection,
    GroundTruthSpec,
    TargetType,
    WorkflowGroundTruth,
)
from .store import GroundTruthStore, GroundTruthStoreError

__all__ = [
    "GroundTruthStore",
    "GroundTruthStoreError",
    "GroundTruthSpec",
    "WorkflowGroundTruth",
    "GroundTruthCollection",
    "TargetType",
]
