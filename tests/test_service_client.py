"""Tests for the MCPProbeServiceClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_probe_pilot.service_client import (
    MCPProbeServiceClient,
    ServiceAPIError,
    ServiceClientError,
    ServiceConnectionError,
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
            "feature_file_count": 3,
            "created_at": "2024-01-01T00:00:00",
        }
        mock_httpx_client.post.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.store_scenario_set(
            project_code="test-project",
            scenario_set={"unit_features": [], "integration_feature": None},
        )

        assert isinstance(result, TCResponse)
        assert result.version == 1
        assert result.scenario_count == 5

    @pytest.mark.asyncio
    async def test_index_codebase(self, client, mock_httpx_client):
        """Test indexing codebase via ChromaDB."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "indexed": 15,
            "project_code": "test-project",
        }
        mock_httpx_client.post.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.index_codebase(
            project_code="test-project",
            entities=[{"name": "test_func", "code": "def test(): pass"}],
        )

        assert result["indexed"] == 15

    @pytest.mark.asyncio
    async def test_query_codebase(self, client, mock_httpx_client):
        """Test querying codebase via ChromaDB."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"name": "auth_handler", "code": "def auth_handler(): ..."}
            ]
        }
        mock_httpx_client.post.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.query_codebase(
            project_code="test-project",
            query="authentication handler",
            n_results=5,
        )

        assert len(result) == 1
        assert result[0]["name"] == "auth_handler"

    @pytest.mark.asyncio
    async def test_get_codebase_status(self, client, mock_httpx_client):
        """Test getting codebase indexing status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entity_count": 42,
            "last_indexed": "2024-01-01T00:00:00",
        }
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_codebase_status("test-project")

        assert result is not None
        assert result["entity_count"] == 42

    @pytest.mark.asyncio
    async def test_get_codebase_status_not_found(self, client, mock_httpx_client):
        """Test getting codebase status when not indexed returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        client._client = mock_httpx_client

        result = await client.get_codebase_status("test-project")

        assert result is None

    @pytest.mark.asyncio
    async def test_clear_codebase(self, client, mock_httpx_client):
        """Test clearing codebase index."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.json.return_value = {}
        mock_httpx_client.delete.return_value = mock_response
        client._client = mock_httpx_client

        await client.clear_codebase("test-project")

        mock_httpx_client.delete.assert_called_once_with(
            "/api/projects/test-project/codebase"
        )

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
            await client.health_check()

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Bad request"

    @pytest.mark.asyncio
    async def test_ensure_project_exists_creates_new(self, client, mock_httpx_client):
        """Test ensure_project_exists creates project when not found."""
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404

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

    def test_test_case_response(self):
        """Test TestCaseResponse model."""
        from mcp_probe_pilot.service_client import TestCaseResponse as TCResponse

        data = {
            "id": 1,
            "project_id": 1,
            "version": 2,
            "scenario_count": 10,
            "feature_file_count": 5,
            "created_at": "2024-01-01T00:00:00",
        }
        response = TCResponse(**data)

        assert response.version == 2
        assert response.scenario_count == 10
        assert response.feature_file_count == 5