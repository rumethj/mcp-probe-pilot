"""Tests for the MCPProbeServiceClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_probe_pilot.service_client import (
    GroundTruthResponse,
    MCPProbeServiceClient,
    ServiceAPIError,
    ServiceClientError,
    ServiceConnectionError,
    WorkflowGroundTruthResponse,
)


# Rename to avoid pytest collection warning
class TestCaseResponseModel:
    """Tests for TestCaseResponse model (renamed to avoid pytest collection)."""
    pass


class TestMCPProbeServiceClient:
    """Tests for MCPProbeServiceClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return MCPProbeServiceClient("http://localhost:8000")

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx client."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.aclose = AsyncMock()
        return mock_client

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test client works as context manager."""
        async with MCPProbeServiceClient("http://localhost:8000") as client:
            assert client._client is not None

    def test_client_not_in_context_raises(self, client):
        """Test accessing client property outside context raises."""
        with pytest.raises(ServiceClientError) as exc_info:
            _ = client.client
        assert "not initialized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_httpx_client):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "version": "0.1.0"}
        mock_httpx_client.get.return_value = mock_response

        # Manually set the client
        client._client = mock_httpx_client

        result = await client.health_check()

        assert result["status"] == "healthy"
        mock_httpx_client.get.assert_called_once_with("/health")

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, client, mock_httpx_client):
        """Test health check raises on connection error."""
        import httpx

        mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")
        client._client = mock_httpx_client

        with pytest.raises(ServiceConnectionError) as exc_info:
            await client.health_check()

        assert "Unable to connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_project(self, client, mock_httpx_client):
        """Test project creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 1,
            "project_code": "test-project",
            "name": "Test Project",
        }
        mock_httpx_client.post.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.create_project(
            project_code="test-project",
            name="Test Project",
        )

        assert result["project_code"] == "test-project"

    @pytest.mark.asyncio
    async def test_get_project_found(self, client, mock_httpx_client):
        """Test getting an existing project."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "project_code": "test-project",
            "name": "Test Project",
        }
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_project("test-project")

        assert result is not None
        assert result["project_code"] == "test-project"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client, mock_httpx_client):
        """Test getting a non-existent project returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_project("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_store_scenario_set(self, client, mock_httpx_client):
        """Test storing a scenario set."""
        from mcp_probe_pilot.service_client import TestCaseResponse as TCResponse

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 1,
            "project_id": 1,
            "version": 1,
            "scenario_count": 5,
            "ground_truth_count": 3,
            "created_at": "2024-01-01T00:00:00",
        }
        mock_httpx_client.post.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.store_scenario_set(
            project_code="test-project",
            scenario_set={"scenarios": [], "ground_truths": {}},
        )

        assert isinstance(result, TCResponse)
        assert result.version == 1
        assert result.scenario_count == 5

    @pytest.mark.asyncio
    async def test_get_ground_truth_found(self, client, mock_httpx_client):
        """Test getting an existing ground truth."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "gt_tool_auth_login",
            "target_type": "tool",
            "target_name": "auth_login",
            "expected_behavior": "Authenticates user",
            "expected_output_schema": {},
            "valid_input_examples": [],
            "invalid_input_examples": [],
            "semantic_reference": "User authentication",
        }
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_ground_truth("test-project", "gt_tool_auth_login")

        assert isinstance(result, GroundTruthResponse)
        assert result.id == "gt_tool_auth_login"
        assert result.target_name == "auth_login"

    @pytest.mark.asyncio
    async def test_get_ground_truth_not_found(self, client, mock_httpx_client):
        """Test getting non-existent ground truth returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_ground_truth("test-project", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_ground_truths(self, client, mock_httpx_client):
        """Test listing all ground truths."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ground_truths": {"gt_tool_test": {"id": "gt_tool_test"}},
            "workflow_ground_truths": {},
        }
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.list_ground_truths("test-project")

        assert "ground_truths" in result
        assert "gt_tool_test" in result["ground_truths"]

    @pytest.mark.asyncio
    async def test_handle_api_error(self, client, mock_httpx_client):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Bad request"}
        mock_response.text = "Bad request"
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        with pytest.raises(ServiceAPIError) as exc_info:
            await client.list_ground_truths("test-project")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Bad request"

    @pytest.mark.asyncio
    async def test_ensure_project_exists_creates_new(self, client, mock_httpx_client):
        """Test ensure_project_exists creates project when not found."""
        # First call returns 404 (project doesn't exist)
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404

        # Second call creates project
        mock_post_response = MagicMock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = {
            "id": 1,
            "project_code": "test-project",
            "name": "test-project",
        }

        mock_httpx_client.get.return_value = mock_get_response
        mock_httpx_client.post.return_value = mock_post_response
        client._client = mock_httpx_client

        result = await client.ensure_project_exists("test-project")

        assert result["project_code"] == "test-project"
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_project_exists_returns_existing(self, client, mock_httpx_client):
        """Test ensure_project_exists returns existing project."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "project_code": "test-project",
            "name": "Test Project",
        }
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.ensure_project_exists("test-project")

        assert result["project_code"] == "test-project"
        mock_httpx_client.post.assert_not_called()


class TestResponseModels:
    """Tests for response model classes."""

    def test_ground_truth_response(self):
        """Test GroundTruthResponse model."""
        data = {
            "id": "gt_tool_test",
            "target_type": "tool",
            "target_name": "test",
            "expected_behavior": "Test behavior",
            "expected_output_schema": {"type": "object"},
            "valid_input_examples": [{"input": {}}],
            "invalid_input_examples": [],
            "semantic_reference": "Test reference",
        }
        response = GroundTruthResponse(**data)

        assert response.id == "gt_tool_test"
        assert response.target_type == "tool"
        assert response.expected_output_schema == {"type": "object"}

    def test_workflow_ground_truth_response(self):
        """Test WorkflowGroundTruthResponse model."""
        data = {
            "id": "gt_workflow_test",
            "workflow_name": "test workflow",
            "expected_flow": "Step 1 -> Step 2",
            "step_expectations": [{"step": 1}],
            "final_outcome": "Success",
            "error_scenarios": [],
        }
        response = WorkflowGroundTruthResponse(**data)

        assert response.id == "gt_workflow_test"
        assert response.workflow_name == "test workflow"

    def test_test_case_response(self):
        """Test TestCaseResponse model."""
        from mcp_probe_pilot.service_client import TestCaseResponse as TCResponse

        data = {
            "id": 1,
            "project_id": 1,
            "version": 2,
            "scenario_count": 10,
            "ground_truth_count": 5,
            "created_at": "2024-01-01T00:00:00",
        }
        response = TCResponse(**data)

        assert response.version == 2
        assert response.scenario_count == 10
