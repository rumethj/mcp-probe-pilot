"""Tests for the ground truth store module."""

import json
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from mcp_probe_pilot.generators.models import TargetType
from mcp_probe_pilot.ground_truth import (
    GroundTruthCollection,
    GroundTruthSpec,
    GroundTruthStore,
    GroundTruthStoreError,
    WorkflowGroundTruth,
)


@pytest.fixture
def sample_ground_truth() -> GroundTruthSpec:
    """Create a sample ground truth spec for testing."""
    return GroundTruthSpec(
        id="gt_tool_auth_login",
        target_type=TargetType.TOOL,
        target_name="auth_login",
        expected_behavior="Authenticates user with credentials and returns a session token",
        expected_output_schema={
            "type": "object",
            "properties": {
                "token": {"type": "string"},
                "expires_at": {"type": "string", "format": "date-time"},
            },
            "required": ["token"],
        },
        valid_input_examples=[
            {"input": {"username": "user", "password": "pass"}, "expected": "success"},
        ],
        invalid_input_examples=[
            {"input": {"username": ""}, "expected_error": "Invalid credentials"},
        ],
        semantic_reference="Returns authentication token for valid user credentials",
    )


@pytest.fixture
def sample_workflow_ground_truth() -> WorkflowGroundTruth:
    """Create a sample workflow ground truth for testing."""
    return WorkflowGroundTruth(
        id="gt_workflow_auth_flow",
        workflow_name="auth_flow",
        expected_flow="Login, then access protected resource, then logout",
        step_expectations=[
            {"step": 1, "action": "login", "expected": "token returned"},
            {"step": 2, "action": "access_resource", "expected": "resource data"},
            {"step": 3, "action": "logout", "expected": "session invalidated"},
        ],
        final_outcome="User successfully authenticates, accesses resource, and logs out",
        error_scenarios=[
            {"scenario": "invalid_credentials", "expected": "login fails gracefully"},
        ],
    )


@pytest.fixture
def ground_truth_store(temp_dir: Path) -> GroundTruthStore:
    """Create a ground truth store for testing."""
    return GroundTruthStore("test-project", str(temp_dir))


class TestGroundTruthCollection:
    """Tests for GroundTruthCollection model."""

    def test_create_empty_collection(self) -> None:
        """Test creating an empty collection."""
        collection = GroundTruthCollection(project_code="test-project")

        assert collection.project_code == "test-project"
        assert collection.version == 1
        assert collection.total_count == 0
        assert collection.capability_count == 0
        assert collection.workflow_count == 0

    def test_add_ground_truth(
        self,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test adding a capability ground truth."""
        collection = GroundTruthCollection(project_code="test-project")
        collection.add_ground_truth(sample_ground_truth)

        assert collection.total_count == 1
        assert collection.capability_count == 1
        assert "gt_tool_auth_login" in collection.ground_truths

    def test_add_workflow_ground_truth(
        self,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test adding a workflow ground truth."""
        collection = GroundTruthCollection(project_code="test-project")
        collection.add_workflow_ground_truth(sample_workflow_ground_truth)

        assert collection.total_count == 1
        assert collection.workflow_count == 1
        assert "gt_workflow_auth_flow" in collection.workflow_ground_truths

    def test_get_ground_truth(
        self,
        sample_ground_truth: GroundTruthSpec,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test getting ground truths by ID."""
        collection = GroundTruthCollection(project_code="test-project")
        collection.add_ground_truth(sample_ground_truth)
        collection.add_workflow_ground_truth(sample_workflow_ground_truth)

        # Get capability ground truth
        gt = collection.get("gt_tool_auth_login")
        assert gt is not None
        assert isinstance(gt, GroundTruthSpec)
        assert gt.target_name == "auth_login"

        # Get workflow ground truth
        wgt = collection.get("gt_workflow_auth_flow")
        assert wgt is not None
        assert isinstance(wgt, WorkflowGroundTruth)
        assert wgt.workflow_name == "auth_flow"

        # Get non-existent
        assert collection.get("nonexistent") is None

    def test_remove_ground_truth(
        self,
        sample_ground_truth: GroundTruthSpec,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test removing ground truths."""
        collection = GroundTruthCollection(project_code="test-project")
        collection.add_ground_truth(sample_ground_truth)
        collection.add_workflow_ground_truth(sample_workflow_ground_truth)

        assert collection.total_count == 2

        # Remove capability ground truth
        assert collection.remove("gt_tool_auth_login") is True
        assert collection.total_count == 1
        assert collection.capability_count == 0

        # Remove workflow ground truth
        assert collection.remove("gt_workflow_auth_flow") is True
        assert collection.total_count == 0

        # Remove non-existent
        assert collection.remove("nonexistent") is False

    def test_to_dict_and_from_dict(
        self,
        sample_ground_truth: GroundTruthSpec,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test serialization and deserialization."""
        collection = GroundTruthCollection(project_code="test-project", version=2)
        collection.add_ground_truth(sample_ground_truth)
        collection.add_workflow_ground_truth(sample_workflow_ground_truth)

        # Serialize
        data = collection.to_dict()
        assert data["project_code"] == "test-project"
        assert data["version"] == 2
        assert "gt_tool_auth_login" in data["ground_truths"]
        assert "gt_workflow_auth_flow" in data["workflow_ground_truths"]

        # Deserialize
        restored = GroundTruthCollection.from_dict(data)
        assert restored.project_code == "test-project"
        assert restored.version == 2
        assert restored.total_count == 2

        gt = restored.get("gt_tool_auth_login")
        assert gt is not None
        assert isinstance(gt, GroundTruthSpec)
        assert gt.target_name == "auth_login"


class TestGroundTruthStore:
    """Tests for GroundTruthStore class."""

    def test_storage_path(self, ground_truth_store: GroundTruthStore) -> None:
        """Test storage path construction."""
        assert ground_truth_store.storage_path.name == "ground_truths.json"
        assert "test-project" in str(ground_truth_store.storage_path)

    def test_exists_when_no_file(self, ground_truth_store: GroundTruthStore) -> None:
        """Test exists() when no file exists."""
        assert ground_truth_store.exists() is False

    def test_save_and_load(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test saving and loading ground truths."""
        # Save
        collection = ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
            workflow_ground_truths={sample_workflow_ground_truth.id: sample_workflow_ground_truth},
        )

        assert collection.total_count == 2
        assert collection.version == 1
        assert ground_truth_store.exists()

        # Load
        loaded = ground_truth_store.load()
        assert loaded.total_count == 2
        assert loaded.project_code == "test-project"

        gt = loaded.get("gt_tool_auth_login")
        assert gt is not None
        assert isinstance(gt, GroundTruthSpec)

    def test_save_increments_version(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test that save increments version number."""
        # First save
        collection1 = ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )
        assert collection1.version == 1

        # Second save
        collection2 = ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )
        assert collection2.version == 2

    def test_load_nonexistent_raises_error(
        self,
        ground_truth_store: GroundTruthStore,
    ) -> None:
        """Test that loading non-existent file raises error."""
        with pytest.raises(GroundTruthStoreError, match="not found"):
            ground_truth_store.load()

    def test_load_by_id(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
        sample_workflow_ground_truth: WorkflowGroundTruth,
    ) -> None:
        """Test loading specific ground truth by ID."""
        ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
            workflow_ground_truths={sample_workflow_ground_truth.id: sample_workflow_ground_truth},
        )

        # Load capability ground truth
        gt = ground_truth_store.load_by_id("gt_tool_auth_login")
        assert gt is not None
        assert isinstance(gt, GroundTruthSpec)
        assert gt.target_name == "auth_login"

        # Load workflow ground truth
        wgt = ground_truth_store.load_by_id("gt_workflow_auth_flow")
        assert wgt is not None
        assert isinstance(wgt, WorkflowGroundTruth)

        # Load non-existent
        assert ground_truth_store.load_by_id("nonexistent") is None

    def test_update_ground_truth(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test updating an existing ground truth."""
        ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )

        # Create updated version
        updated_gt = GroundTruthSpec(
            id="gt_tool_auth_login",
            target_type=TargetType.TOOL,
            target_name="auth_login",
            expected_behavior="UPDATED: Authenticates user",
            expected_output_schema={},
            semantic_reference="UPDATED reference",
        )

        # Update
        result = ground_truth_store.update("gt_tool_auth_login", updated_gt)
        assert result is True

        # Verify update
        loaded = ground_truth_store.load_by_id("gt_tool_auth_login")
        assert loaded is not None
        assert loaded.expected_behavior == "UPDATED: Authenticates user"
        assert loaded.semantic_reference == "UPDATED reference"

    def test_update_nonexistent_returns_false(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test updating non-existent ground truth returns False."""
        ground_truth_store.save(ground_truths={})

        result = ground_truth_store.update("nonexistent", sample_ground_truth)
        assert result is False

    def test_delete_ground_truth(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test deleting a ground truth."""
        ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )

        # Delete
        result = ground_truth_store.delete("gt_tool_auth_login")
        assert result is True

        # Verify deletion
        loaded = ground_truth_store.load()
        assert loaded.total_count == 0

    def test_delete_nonexistent_returns_false(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test deleting non-existent ground truth returns False."""
        ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )

        result = ground_truth_store.delete("nonexistent")
        assert result is False

    def test_clear(
        self,
        ground_truth_store: GroundTruthStore,
        sample_ground_truth: GroundTruthSpec,
    ) -> None:
        """Test clearing all ground truths."""
        ground_truth_store.save(
            ground_truths={sample_ground_truth.id: sample_ground_truth},
        )

        assert ground_truth_store.exists()

        result = ground_truth_store.clear()
        assert result is True
        assert ground_truth_store.exists() is False

    def test_clear_nonexistent_returns_false(
        self,
        ground_truth_store: GroundTruthStore,
    ) -> None:
        """Test clearing when no file exists returns False."""
        result = ground_truth_store.clear()
        assert result is False

    def test_load_corrupted_json_raises_error(
        self,
        ground_truth_store: GroundTruthStore,
    ) -> None:
        """Test that loading corrupted JSON raises error."""
        ground_truth_store._ensure_directory()
        with open(ground_truth_store.storage_path, "w") as f:
            f.write("{ invalid json }")

        with pytest.raises(GroundTruthStoreError, match="Invalid JSON"):
            ground_truth_store.load()

    def test_creates_directory_structure(
        self,
        temp_dir: Path,
    ) -> None:
        """Test that save creates necessary directory structure."""
        store = GroundTruthStore("nested/project", str(temp_dir))

        gt = GroundTruthSpec(
            id="gt_tool_test",
            target_type=TargetType.TOOL,
            target_name="test",
            expected_behavior="Test behavior",
            semantic_reference="Test reference",
        )

        store.save(ground_truths={gt.id: gt})

        assert store.storage_path.exists()
        assert "nested" in str(store.storage_path)
