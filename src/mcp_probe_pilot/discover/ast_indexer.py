"""AST-based codebase indexer for extracting code entities from Python source files.

Uses the ``ast`` stdlib module to parse Python source code and extract
functions, classes, and methods with their metadata.  Supports incremental
indexing via SHA-256 file hash change detection.
"""

import ast
import fnmatch
import hashlib
import logging
from pathlib import Path
from typing import Optional

from mcp_probe_pilot.core.models.discover import CodebaseIndex, CodeEntity

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDE_DIRS: set[str] = {
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
    "features",
    "tests",
    "test",
    "tests_files",
    "test_files",
    "tests_data",
    "test_data",
    "tests_results",
    "test_results",
    "tests_reports",
    "reports",
    "*mcp-probe*",
    "*.log",
}

DEFAULT_EXCLUDE_FILES: set[str] = {
    "__init__.py",
}


class ASTIndexerError(Exception):
    """Raised when AST indexing fails."""


class ASTIndexer:
    """Indexes Python source files by parsing their ASTs.

    Example::

        indexer = ASTIndexer()
        index = indexer.index_directory(Path("/path/to/server/src"))
        print(f"Found {index.total_entities} entities in {index.total_files} files")
    """

    def __init__(
        self,
        exclude_dirs: Optional[set[str]] = None,
        exclude_files: Optional[set[str]] = None,
        include_init_files: bool = False,
    ) -> None:
        self.exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS.copy()
        self.exclude_files = exclude_files if exclude_files is not None else (
            set() if include_init_files else DEFAULT_EXCLUDE_FILES.copy()
        )
        self.previous_hashes: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_directory(self, path: Path) -> CodebaseIndex:
        """Recursively parse all Python files under *path*.

        Returns a CodebaseIndex with every extracted entity and per-file
        SHA-256 hashes (for incremental re-indexing on subsequent runs).
        """
        if not path.exists():
            raise ASTIndexerError(f"Path does not exist: {path}")
        if not path.is_dir():
            raise ASTIndexerError(f"Path is not a directory: {path}")

        entities: list[CodeEntity] = []
        file_hashes: dict[str, str] = {}
        files_processed = 0

        python_files = self._find_python_files(path)
        logger.info("Found %d Python files to index in %s", len(python_files), path)

        for py_file in python_files:
            relative_path = str(py_file.relative_to(path))
            file_hash = self._compute_file_hash(py_file)
            file_hashes[relative_path] = file_hash

            if self.previous_hashes.get(relative_path) == file_hash:
                logger.debug("Skipping unchanged file: %s", relative_path)
                continue

            try:
                file_entities = self._parse_file(py_file, relative_path)
                entities.extend(file_entities)
                files_processed += 1
                logger.debug("Parsed %s: %d entities", relative_path, len(file_entities))
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", relative_path, exc)

        index = CodebaseIndex(
            entities=entities,
            file_hashes=file_hashes,
            total_files=files_processed,
            total_entities=len(entities),
        )
        logger.info(
            "Indexing complete: %d entities from %d files",
            index.total_entities,
            index.total_files,
        )
        return index

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_python_files(self, root: Path) -> list[Path]:
        python_files: list[Path] = []
        for py_file in sorted(root.rglob("*.py")):
            should_exclude = False
            for parent in py_file.relative_to(root).parents:
                if self._matches_exclude(parent.name, self.exclude_dirs):
                    should_exclude = True
                    break
            if should_exclude:
                continue
            if py_file.name in self.exclude_files:
                continue
            python_files.append(py_file)
        return python_files

    @staticmethod
    def _matches_exclude(name: str, patterns: set[str]) -> bool:
        """Check *name* against a set that may contain plain names or glob patterns."""
        if name in patterns:
            return True
        return any(fnmatch.fnmatch(name, p) for p in patterns if "*" in p or "?" in p)

    def _parse_file(self, file_path: Path, relative_path: str) -> list[CodeEntity]:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        source_lines = source.splitlines()

        entities: list[CodeEntity] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                parent_class = self._find_parent_class(tree, node)
                entity_type = "method" if parent_class else "function"
                entities.append(
                    self._extract_entity(
                        node, entity_type, source_lines, relative_path, parent_class
                    )
                )
            elif isinstance(node, ast.ClassDef):
                entities.append(
                    self._extract_entity(node, "class", source_lines, relative_path)
                )
        return entities

    def _extract_entity(
        self,
        node: ast.AST,
        entity_type: str,
        source_lines: list[str],
        relative_path: str,
        parent_class: Optional[str] = None,
    ) -> CodeEntity:
        start_line = node.lineno  # type: ignore[attr-defined]
        end_line = node.end_lineno or node.lineno  # type: ignore[attr-defined]
        code = "\n".join(source_lines[start_line - 1 : end_line])

        return CodeEntity(
            file_path=relative_path,
            entity_type=entity_type,
            name=node.name,  # type: ignore[attr-defined]
            code=code,
            start_line=start_line,
            end_line=end_line,
            docstring=ast.get_docstring(node),  # type: ignore[arg-type]
            decorators=self._extract_decorators(node),
            parent_class=parent_class,
        )

    def _extract_decorators(self, node: ast.AST) -> list[str]:
        decorators: list[str] = []
        for decorator in getattr(node, "decorator_list", []):
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

    def _find_parent_class(
        self, tree: ast.Module, target_node: ast.AST
    ) -> Optional[str]:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if child is target_node:
                        return node.name
        return None

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
