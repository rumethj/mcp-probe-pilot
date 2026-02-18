"""HTTP client for communicating with mcp-probe-service.

This module provides the MCPProbeServiceClient class which handles all
communication with the mcp-probe-service REST API for storing and
retrieving test scenarios, reports, and querying the ChromaDB-indexed codebase.
"""

import logging
from typing import Any, Optional
from pathlib import Path
import hashlib

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ServiceClientError(Exception):
    """Base exception for service client errors."""

    pass


class ServiceConnectionError(ServiceClientError):
    """Raised when unable to connect to the service."""

    pass


class ServiceAPIError(ServiceClientError):
    """Raised when the service returns an error response."""

    def __init__(self, message: str, status_code: int, detail: Optional[str] = None):
        """Initialize the error.

        Args:
            message: Error message.
            status_code: HTTP status code.
            detail: Optional detailed error message from the API.
        """
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class TestCaseResponse(BaseModel):
    """Response model for test case metadata."""

    id: int
    project_id: int
    version: int
    scenario_count: int
    feature_file_count: int
    created_at: str


class MCPProbeServiceClient:
    """HTTP client for mcp-probe-service API.

    This client handles all communication with the mcp-probe-service REST API,
    including storing and retrieving test scenarios, reports, and querying
    the ChromaDB-indexed codebase.

    Example:
        ```python
        async with MCPProbeServiceClient("http://localhost:8000") as client:
            # Check service health
            await client.health_check()

            # Store scenario set
            response = await client.store_scenario_set(
                project_code="my-project",
                scenario_set=scenario_set.model_dump()
            )

            # Query codebase from ChromaDB
            results = await client.query_codebase(
                project_code="my-project",
                query="authentication handler",
                n_results=5
            )
        ```

    Attributes:
        base_url: The base URL of the mcp-probe-service.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ):
        """Initialize the service client.

        Args:
            base_url: Base URL of the mcp-probe-service (e.g., "http://localhost:8000").
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "MCPProbeServiceClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not initialized.

        Returns:
            The httpx async client.

        Raises:
            ServiceClientError: If client not initialized (not in context manager).
        """
        if self._client is None:
            raise ServiceClientError(
                "Client not initialized. Use 'async with MCPProbeServiceClient(...) as client:'"
            )
        return self._client

    async def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle HTTP response, raising appropriate errors.

        Args:
            response: The HTTP response.

        Returns:
            The JSON response body.

        Raises:
            ServiceAPIError: If the response indicates an error.
        """
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text

            raise ServiceAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                detail=detail,
            )

        if response.status_code == 204:
            return {}

        return response.json()

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict[str, Any]:
        """Check if the service is healthy and reachable.

        Returns:
            Health check response containing status and version.

        Raises:
            ServiceConnectionError: If unable to connect to the service.
            ServiceAPIError: If the service returns an error.
        """
        try:
            response = await self.client.get("/health")
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(
                f"Unable to connect to mcp-probe-service at {self.base_url}: {e}"
            ) from e

    # =========================================================================
    # Project Management
    # =========================================================================

    async def create_project(
        self,
        project_code: str,
        name: str,
        description: Optional[str] = None,
        server_command: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new project.

        Args:
            project_code: Unique project identifier.
            name: Human-readable project name.
            description: Optional project description.
            server_command: Command to start the MCP server.

        Returns:
            The created project data.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project already exists or other error.
        """
        try:
            response = await self.client.post(
                "/api/projects",
                json={
                    "project_code": project_code,
                    "name": name,
                    "description": description,
                    "server_command": server_command,
                },
            )
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def get_project(self, project_code: str) -> Optional[dict[str, Any]]:
        """Get a project by its code.

        Args:
            project_code: The project code to look up.

        Returns:
            The project data if found, None otherwise.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: For non-404 errors.
        """
        try:
            response = await self.client.get(f"/api/projects/{project_code}")
            if response.status_code == 404:
                return None
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def ensure_project_exists(
        self,
        project_code: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        server_command: Optional[str] = None,
    ) -> dict[str, Any]:
        """Ensure a project exists, creating it if necessary.

        Args:
            project_code: Unique project identifier.
            name: Human-readable project name (defaults to project_code).
            description: Optional project description.
            server_command: Command to start the MCP server.

        Returns:
            The project data.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: On unexpected errors.
        """
        project = await self.get_project(project_code)
        if project:
            logger.debug(f"Project '{project_code}' already exists")
            return project

        logger.info(f"Creating project '{project_code}'")
        return await self.create_project(
            project_code=project_code,
            name=name or project_code,
            description=description,
            server_command=server_command,
        )

    # =========================================================================
    # Scenario Set / Test Case Management
    # =========================================================================

    async def store_scenario_set(
        self,
        project_code: str,
        scenario_set: dict[str, Any],
    ) -> TestCaseResponse:
        """Store a generated scenario set for a project.

        Args:
            project_code: The project code.
            scenario_set: The ScenarioSet data as a dictionary.

        Returns:
            Test case metadata including version number.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or other error.
        """
        try:
            response = await self.client.post(
                f"/api/projects/{project_code}/tests",
                json={"scenario_set": scenario_set},
            )
            data = await self._handle_response(response)
            return TestCaseResponse(**data)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def store_test_artifacts(
        self,
        project_code: str,
        version: int,
        artifacts_path: Path,
    ) -> dict[str, Any]:
        """Upload test artifacts (feature files, etc.) to the service.

        Args:
            project_code: The project code.
            version: The test case version.
            artifacts_path: Path to the zip file containing artifacts.

        Returns:
            Server response.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If upload fails.
        """
        if not artifacts_path.exists():
            raise FileNotFoundError(f"Artifacts file not found: {artifacts_path}")

        with open(artifacts_path, "rb") as f:
            file_content = f.read()

        md5_hash = hashlib.md5(file_content).hexdigest()
        size_bytes = len(file_content)
        logger.debug(
            f"Sending artifacts. Size: {size_bytes} bytes, MD5: {md5_hash}"
        )

        files = {"file": ("artifacts.zip", file_content, "application/zip")}
        try:
            response = await self.client.post(
                f"/api/projects/{project_code}/tests/{version}/artifacts",
                files=files,
                timeout=60.0,
            )
            return await self._handle_response(response)
        except Exception as e:
            logger.debug(f"Upload failed: {e}")
            raise

    async def get_scenario_set(self, project_code: str) -> Optional[dict[str, Any]]:
        """Get the latest scenario set for a project.

        Args:
            project_code: The project code.

        Returns:
            The scenario set data if found, None if no tests exist.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: For non-404 errors.
        """
        try:
            response = await self.client.get(f"/api/projects/{project_code}/tests")
            if response.status_code == 404:
                return None
            data = await self._handle_response(response)
            return data.get("scenario_set")
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def delete_scenario_sets(self, project_code: str) -> None:
        """Delete all scenario sets for a project.

        Args:
            project_code: The project code.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or other error.
        """
        try:
            response = await self.client.delete(
                f"/api/projects/{project_code}/tests"
            )
            await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    # =========================================================================
    # ChromaDB Codebase Indexing and Querying
    # =========================================================================

    async def index_codebase(
        self,
        project_code: str,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Index code entities into ChromaDB via the service.

        Args:
            project_code: The project code.
            entities: List of CodeEntity data as dictionaries.

        Returns:
            Indexing result with counts.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or indexing fails.
        """
        try:
            response = await self.client.post(
                f"/api/projects/{project_code}/codebase/index",
                json={"entities": entities},
                timeout=120.0,
            )
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def query_codebase(
        self,
        project_code: str,
        query: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Query the ChromaDB-indexed codebase for relevant code.

        Args:
            project_code: The project code.
            query: Semantic search query string.
            n_results: Number of results to return.

        Returns:
            List of matching code entity data.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or query fails.
        """
        try:
            response = await self.client.post(
                f"/api/projects/{project_code}/codebase/query",
                json={"query": query, "n_results": n_results},
            )
            data = await self._handle_response(response)
            return data.get("results", [])
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def get_codebase_status(
        self,
        project_code: str,
    ) -> Optional[dict[str, Any]]:
        """Get the indexing status of the codebase for a project.

        Args:
            project_code: The project code.

        Returns:
            Status data including entity count, last indexed timestamp, etc.
            None if no codebase has been indexed.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: For non-404 errors.
        """
        try:
            response = await self.client.get(
                f"/api/projects/{project_code}/codebase/status"
            )
            if response.status_code == 404:
                return None
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def clear_codebase(self, project_code: str) -> None:
        """Clear the indexed codebase for a project.

        Args:
            project_code: The project code.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or other error.
        """
        try:
            response = await self.client.delete(
                f"/api/projects/{project_code}/codebase"
            )
            await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    # =========================================================================
    # Report Management
    # =========================================================================

    async def store_report(
        self,
        project_code: str,
        report_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Store a test report for a project.

        Args:
            project_code: The project code.
            report_data: The report data containing summary, test results, etc.

        Returns:
            The created report metadata.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: If project not found or other error.
        """
        try:
            response = await self.client.post(
                f"/api/projects/{project_code}/reports",
                json={"report_data": report_data},
            )
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e

    async def get_latest_report(self, project_code: str) -> Optional[dict[str, Any]]:
        """Get the latest report for a project.

        Args:
            project_code: The project code.

        Returns:
            The report data if found, None if no reports exist.

        Raises:
            ServiceConnectionError: If unable to connect.
            ServiceAPIError: For non-404 errors.
        """
        try:
            response = await self.client.get(
                f"/api/projects/{project_code}/reports",
                params={"limit": 1},
            )
            if response.status_code == 404:
                return None
            data = await self._handle_response(response)
            reports = data.get("reports", [])
            return reports[0] if reports else None
        except httpx.ConnectError as e:
            raise ServiceConnectionError(f"Unable to connect to service: {e}") from e
