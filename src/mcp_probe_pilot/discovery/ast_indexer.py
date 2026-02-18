"""AST-based codebase indexer for extracting code entities from Python source files.

This module provides the ASTIndexer class which parses Python source code using
the `ast` stdlib module to extract functions, classes, methods, decorators, and
docstrings. The extracted entities can be sent to ChromaDB via the mcp-probe-service
REST API for semantic search during test generation.

The indexer supports incremental indexing via SHA-256 file hash change detection,
only re-indexing files whose content has changed since the last run.
"""

import ast
import hashlib
import logging
from pathlib import Path
from typing import Any, Optional

from .models import CodebaseIndex, CodeEntity

logger = logging.getLogger(__name__)

# Directories and file patterns to skip during indexing
DEFAULT_EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
}

DEFAULT_EXCLUDE_FILES = {
    "__init__.py",
}


class ASTIndexerError(Exception):
    """Exception raised when AST indexing fails."""

    pass


class ASTIndexer:
    """AST-based codebase indexer for Python source files.

    Parses Python files using the `ast` stdlib to extract code entities
    (functions, classes, methods) with their metadata. Supports incremental
    indexing using SHA-256 file hash change detection.

    Example:
        ```python
        indexer = ASTIndexer()
        index = indexer.index_directory(Path("/path/to/server/src"))
        print(f"Found {index.total_entities} entities in {index.total_files} files")

        # Send to ChromaDB via service
        await indexer.index_to_chromadb(service_client, "my-project", index)
        ```

    Attributes:
        exclude_dirs: Set of directory names to exclude from indexing.
        exclude_files: Set of file names to exclude from indexing.
        previous_hashes: Mapping of file paths to their previous SHA-256 hashes.
    """

    def __init__(
        self,
        exclude_dirs: Optional[set[str]] = None,
        exclude_files: Optional[set[str]] = None,
        include_init_files: bool = False,
    ):
        """Initialize the AST indexer.

        Args:
            exclude_dirs: Directory names to exclude. Defaults to common non-source dirs.
            exclude_files: File names to exclude. Defaults to __init__.py files.
            include_init_files: If True, include __init__.py files in indexing.
        """
        self.exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS.copy()
        self.exclude_files = exclude_files if exclude_files is not None else (
            set() if include_init_files else DEFAULT_EXCLUDE_FILES.copy()
        )
        self.previous_hashes: dict[str, str] = {}

    def index_directory(self, path: Path) -> CodebaseIndex:
        """Recursively find and parse all Python files in a directory.

        Args:
            path: Root directory to index.

        Returns:
            CodebaseIndex containing all extracted entities and file hashes.

        Raises:
            ASTIndexerError: If the path does not exist or is not a directory.
        """
        if not path.exists():
            raise ASTIndexerError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise ASTIndexerError(f"Path is not a directory: {path}")

        entities: list[CodeEntity] = []
        file_hashes: dict[str, str] = {}
        files_processed = 0

        python_files = self._find_python_files(path)
        logger.info(f"Found {len(python_files)} Python files to index in {path}")

        for py_file in python_files:
            relative_path = str(py_file.relative_to(path))
            file_hash = self._compute_file_hash(py_file)
            file_hashes[relative_path] = file_hash

            # Incremental indexing: skip unchanged files
            if self.previous_hashes.get(relative_path) == file_hash:
                logger.debug(f"Skipping unchanged file: {relative_path}")
                continue

            try:
                file_entities = self._parse_file(py_file, relative_path)
                entities.extend(file_entities)
                files_processed += 1
                logger.debug(
                    f"Parsed {relative_path}: {len(file_entities)} entities"
                )
            except Exception as e:
                logger.warning(f"Failed to parse {relative_path}: {e}")

        index = CodebaseIndex(
            entities=entities,
            file_hashes=file_hashes,
            total_files=files_processed,
            total_entities=len(entities),
        )

        logger.info(
            f"Indexing complete: {index.total_entities} entities "
            f"from {index.total_files} files"
        )

        return index

    def _find_python_files(self, root: Path) -> list[Path]:
        """Find all Python files in a directory tree, excluding configured paths.

        Args:
            root: Root directory to search.

        Returns:
            Sorted list of Python file paths.
        """
        python_files: list[Path] = []

        for py_file in sorted(root.rglob("*.py")):
            # Check if any parent directory should be excluded
            should_exclude = False
            for parent in py_file.relative_to(root).parents:
                if parent.name in self.exclude_dirs:
                    should_exclude = True
                    break
            if should_exclude:
                continue

            # Check if the file name should be excluded
            if py_file.name in self.exclude_files:
                continue

            python_files.append(py_file)

        return python_files

    def _parse_file(self, file_path: Path, relative_path: str) -> list[CodeEntity]:
        """Parse a Python file to extract functions, classes, and methods.

        Uses the `ast` stdlib to parse the file and extract code entities
        including their docstrings and decorators.

        Args:
            file_path: Absolute path to the Python file.
            relative_path: Relative path from the index root.

        Returns:
            List of CodeEntity objects extracted from the file.

        Raises:
            SyntaxError: If the file contains invalid Python syntax.
        """
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        source_lines = source.splitlines()

        entities: list[CodeEntity] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Determine if this is a method (inside a class) or a top-level function
                parent_class = self._find_parent_class(tree, node)
                entity_type = "method" if parent_class else "function"

                entity = self._extract_entity(
                    node=node,
                    entity_type=entity_type,
                    source_lines=source_lines,
                    relative_path=relative_path,
                    parent_class=parent_class,
                )
                entities.append(entity)

            elif isinstance(node, ast.ClassDef):
                entity = self._extract_entity(
                    node=node,
                    entity_type="class",
                    source_lines=source_lines,
                    relative_path=relative_path,
                )
                entities.append(entity)

        return entities

    def _extract_entity(
        self,
        node: ast.AST,
        entity_type: str,
        source_lines: list[str],
        relative_path: str,
        parent_class: Optional[str] = None,
    ) -> CodeEntity:
        """Extract a CodeEntity from an AST node.

        Args:
            node: The AST node (FunctionDef, AsyncFunctionDef, or ClassDef).
            entity_type: The type of entity ('function', 'class', 'method').
            source_lines: The source code split into lines.
            relative_path: Relative file path.
            parent_class: Parent class name if this is a method.

        Returns:
            A CodeEntity with all extracted metadata.
        """
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno

        # Extract the source code for this entity
        code = "\n".join(source_lines[start_line - 1 : end_line])

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract decorator names
        decorators = self._extract_decorators(node)

        return CodeEntity(
            file_path=relative_path,
            entity_type=entity_type,
            name=node.name,
            code=code,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            decorators=decorators,
            parent_class=parent_class,
        )

    def _extract_decorators(self, node: ast.AST) -> list[str]:
        """Extract decorator names from an AST node.

        Args:
            node: An AST node that may have decorator_list attribute.

        Returns:
            List of decorator name strings.
        """
        decorators: list[str] = []
        decorator_list = getattr(node, "decorator_list", [])

        for decorator in decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                decorators.append(ast.dump(decorator))
            elif isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Name):
                    decorators.append(func.id)
                elif isinstance(func, ast.Attribute):
                    decorators.append(ast.dump(func))

        return decorators

    def _find_parent_class(self, tree: ast.Module, target_node: ast.AST) -> Optional[str]:
        """Find the parent class of a function/method node.

        Args:
            tree: The AST module tree.
            target_node: The function/method node to find the parent of.

        Returns:
            The parent class name if the node is a method, None otherwise.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if child is target_node:
                        return node.name
        return None

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute the SHA-256 hash of a file for change detection.

        Args:
            file_path: Path to the file to hash.

        Returns:
            Hex string of the SHA-256 hash.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def compute_file_hashes(self, path: Path) -> dict[str, str]:
        """Compute SHA-256 hashes for all Python files in a directory.

        Args:
            path: Root directory to scan.

        Returns:
            Dictionary mapping relative file paths to their SHA-256 hashes.

        Raises:
            ASTIndexerError: If the path does not exist or is not a directory.
        """
        if not path.exists():
            raise ASTIndexerError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise ASTIndexerError(f"Path is not a directory: {path}")

        hashes: dict[str, str] = {}
        for py_file in self._find_python_files(path):
            relative_path = str(py_file.relative_to(path))
            hashes[relative_path] = self._compute_file_hash(py_file)

        return hashes

    def get_changed_files(
        self,
        current_hashes: dict[str, str],
        previous_hashes: dict[str, str],
    ) -> tuple[set[str], set[str], set[str]]:
        """Determine which files have changed between two hash snapshots.

        Args:
            current_hashes: Current file hash mapping.
            previous_hashes: Previous file hash mapping.

        Returns:
            Tuple of (added_files, modified_files, deleted_files).
        """
        current_files = set(current_hashes.keys())
        previous_files = set(previous_hashes.keys())

        added = current_files - previous_files
        deleted = previous_files - current_files
        common = current_files & previous_files

        modified = {
            f for f in common if current_hashes[f] != previous_hashes[f]
        }

        return added, modified, deleted

    async def index_to_chromadb(
        self,
        service_client: Any,
        project_code: str,
        index: Optional[CodebaseIndex] = None,
        source_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Send indexed code entities to ChromaDB via the mcp-probe-service API.

        Either an existing index or a source_path (to index first) must be provided.

        Args:
            service_client: An MCPProbeServiceClient instance.
            project_code: The project code for ChromaDB collection.
            index: Pre-computed CodebaseIndex. If None, source_path must be provided.
            source_path: Path to source directory to index. Used if index is None.

        Returns:
            Result from the service API with indexing counts.

        Raises:
            ASTIndexerError: If neither index nor source_path is provided.
            ServiceClientError: If the API call fails.
        """
        if index is None and source_path is None:
            raise ASTIndexerError(
                "Either 'index' or 'source_path' must be provided"
            )

        if index is None:
            index = self.index_directory(source_path)

        if not index.entities:
            logger.warning("No entities to index into ChromaDB")
            return {"indexed_count": 0, "project_code": project_code}

        # Convert entities to dicts for the API
        entities_data = [entity.model_dump() for entity in index.entities]

        logger.info(
            f"Sending {len(entities_data)} entities to ChromaDB "
            f"for project '{project_code}'"
        )

        result = await service_client.index_codebase(
            project_code=project_code,
            entities=entities_data,
        )

        # Update previous hashes for incremental indexing
        self.previous_hashes = index.file_hashes.copy()

        return result
