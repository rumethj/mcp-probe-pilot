"""HTTP client for communicating with mcp-probe-service.

Provides ``MCPProbeServiceClient``, an async context-manager that wraps
all REST calls to the service's codebase / ChromaDB endpoints.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ServiceClientError(Exception):
    """Base exception for service client errors."""


class ServiceConnectionError(ServiceClientError):
    """Raised when unable to connect to the service."""


class ServiceAPIError(ServiceClientError):
    """Raised when the service returns an error response."""

    def __init__(
        self, message: str, status_code: int, detail: Optional[str] = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class MCPProbeServiceClient:
    """Async HTTP client for the mcp-probe-service REST API.

    Example::

        async with MCPProbeServiceClient() as client:
            await client.health_check()
            await client.index_codebase(entities)
            results = await client.query_codebase("auth handler")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "MCPProbeServiceClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ServiceClientError(
                "Client not initialised. "
                "Use 'async with MCPProbeServiceClient() as client:'"
            )
        return self._client

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    async def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
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

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check whether the service is reachable."""
        try:
            response = await self.client.get("/health")
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to mcp-probe-service at {self.base_url}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Codebase indexing / querying
    # ------------------------------------------------------------------

    async def index_codebase(
        self,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send code entities to be indexed into ChromaDB."""
        try:
            response = await self.client.post(
                "/api/codebase/index",
                json={"entities": entities},
                timeout=120.0,
            )
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to service: {exc}"
            ) from exc

    async def query_codebase(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over the indexed codebase."""
        try:
            response = await self.client.post(
                "/api/codebase/query",
                json={"query": query, "n_results": n_results},
            )
            data = await self._handle_response(response)
            return data.get("results", [])
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to service: {exc}"
            ) from exc

    async def get_codebase_status(self) -> Optional[dict[str, Any]]:
        """Get indexing status (entity count)."""
        try:
            response = await self.client.get("/api/codebase/status")
            if response.status_code == 404:
                return None
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to service: {exc}"
            ) from exc

    async def clear_codebase(self) -> None:
        """Delete all indexed codebase data."""
        try:
            response = await self.client.delete("/api/codebase")
            if response.status_code != 404:
                await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to service: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Prebuilts
    # ------------------------------------------------------------------

    async def get_prebuilts(self) -> dict[str, Any]:
        """Fetch prebuilt scaffolding files and their dependencies.

        Returns the full response dict with ``files`` and ``dependencies`` keys.
        """
        try:
            response = await self.client.get("/api/prebuilts")
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to service: {exc}"
            ) from exc

    async def get_prebuilt_dependencies(self) -> list[str]:
        """Fetch the pip dependency list required by prebuilt scaffolding."""
        data = await self.get_prebuilts()
        return data.get("dependencies", [])

    async def download_prebuilts(self, target_dir: Path) -> list[Path]:
        """Fetch prebuilt files and write them into *target_dir*.

        Directory structure is preserved (e.g. ``helper/mcp_client.py``
        becomes ``target_dir/helper/mcp_client.py``).

        Returns the list of paths that were written.
        """
        data = await self.get_prebuilts()
        files = data.get("files", [])
        written: list[Path] = []
        for entry in files:
            dest = target_dir / entry["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry["content"], encoding="utf-8")
            written.append(dest)
            logger.debug("Wrote prebuilt file: %s", dest)
        return written

    # ------------------------------------------------------------------
    # Features storage
    # ------------------------------------------------------------------

    _STORABLE_EXTENSIONS = {
        ".feature", ".py", ".json", ".txt", ".cfg", ".ini", ".toml",
    }

    async def get_features(self, server_id: str) -> Optional[dict[str, Any]]:
        """Fetch previously stored features for *server_id*.

        Returns the full response dict with ``files`` and ``dependencies``
        keys, or ``None`` when no stored features exist (HTTP 404).
        """
        try:
            response = await self.client.get(f"/api/features/{server_id}")
            if response.status_code == 404:
                return None
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to mcp-probe-service: {exc}"
            ) from exc

    async def store_features(
        self, server_id: str, features_dir: Path
    ) -> dict[str, Any]:
        """Upload the entire *features_dir* tree to the service.

        Walks the directory, reads every file whose extension is in
        ``_STORABLE_EXTENSIONS`` (skipping ``__pycache__``), and PUTs
        them to ``/api/features/{server_id}``.
        """
        files: list[dict[str, str]] = []
        for file_path in sorted(features_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if "__pycache__" in file_path.parts:
                continue
            if file_path.suffix not in self._STORABLE_EXTENSIONS:
                continue
            relative = file_path.relative_to(features_dir).as_posix()
            content = file_path.read_text(encoding="utf-8")
            files.append({"path": relative, "content": content})

        req_file = features_dir / "requirements.txt"
        dependencies: list[str] = []
        if req_file.exists():
            dependencies = [
                line.strip()
                for line in req_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

        try:
            response = await self.client.put(
                f"/api/features/{server_id}",
                json={"files": files, "dependencies": dependencies},
                timeout=120.0,
            )
            return await self._handle_response(response)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                f"Unable to connect to mcp-probe-service: {exc}"
            ) from exc

    async def download_features(
        self, server_id: str, target_dir: Path
    ) -> list[Path]:
        """Fetch stored features and write them into *target_dir*.

        Returns the list of paths that were written, or an empty list
        when no stored features exist.
        """
        data = await self.get_features(server_id)
        if data is None:
            return []

        files = data.get("files", [])
        written: list[Path] = []
        for entry in files:
            dest = target_dir / entry["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry["content"], encoding="utf-8")
            written.append(dest)
            logger.debug("Wrote stored feature file: %s", dest)
        return written
