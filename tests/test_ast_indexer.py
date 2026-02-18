"""Unit tests for the AST Indexer module."""

import textwrap
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_probe_pilot.discovery import (
    ASTIndexer,
    ASTIndexerError,
    CodebaseIndex,
    CodeEntity,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def sample_python_file(temp_dir: Path) -> Path:
    """Create a sample Python file for testing."""
    code = textwrap.dedent('''\
        """Sample module docstring."""

        import os


        def simple_function(x: int, y: int) -> int:
            """Add two numbers.

            Args:
                x: First number.
                y: Second number.

            Returns:
                The sum of x and y.
            """
            return x + y


        def no_docstring_function():
            pass


        class MyClass:
            """A sample class for testing."""

            def __init__(self, name: str):
                """Initialize MyClass.

                Args:
                    name: The name.
                """
                self.name = name

            def greet(self) -> str:
                """Return a greeting."""
                return f"Hello, {self.name}!"

            async def async_method(self) -> None:
                """An async method."""
                pass
    ''')
    file_path = temp_dir / "sample.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_project(temp_dir: Path) -> Path:
    """Create a sample project directory structure for testing."""
    # Create source directory
    src_dir = temp_dir / "src"
    src_dir.mkdir()

    # Create __init__.py (should be excluded by default)
    (src_dir / "__init__.py").write_text('"""Init."""\n')

    # Create main module
    main_code = textwrap.dedent('''\
        """Main module."""

        from typing import Optional


        def main() -> None:
            """Entry point."""
            print("Hello, world!")


        def helper(value: Optional[str] = None) -> str:
            """A helper function.

            Args:
                value: Optional input value.

            Returns:
                Processed string.
            """
            return value or "default"
    ''')
    (src_dir / "main.py").write_text(main_code)

    # Create utils module
    utils_code = textwrap.dedent('''\
        """Utilities module."""

        import hashlib


        class Hasher:
            """Utility class for hashing."""

            def hash_string(self, value: str) -> str:
                """Hash a string with SHA-256."""
                return hashlib.sha256(value.encode()).hexdigest()


        def format_output(data: dict) -> str:
            """Format output data."""
            return str(data)
    ''')
    (src_dir / "utils.py").write_text(utils_code)

    # Create a subdirectory with more files
    sub_dir = src_dir / "handlers"
    sub_dir.mkdir()
    (sub_dir / "__init__.py").write_text("")

    handler_code = textwrap.dedent('''\
        """Request handlers."""


        class RequestHandler:
            """Handle HTTP requests."""

            def get(self, path: str) -> dict:
                """Handle GET request."""
                return {"path": path}

            def post(self, path: str, body: dict) -> dict:
                """Handle POST request."""
                return {"path": path, "body": body}
    ''')
    (sub_dir / "handler.py").write_text(handler_code)

    # Create a venv directory that should be excluded
    venv_dir = temp_dir / ".venv"
    venv_dir.mkdir()
    (venv_dir / "some_file.py").write_text("# Should be excluded\n")

    return temp_dir


@pytest.fixture
def indexer() -> ASTIndexer:
    """Create a default ASTIndexer instance."""
    return ASTIndexer()


# =============================================================================
# CodeEntity Model Tests
# =============================================================================


class TestCodeEntity:
    """Tests for CodeEntity model."""

    def test_create_function_entity(self):
        """Test creating a function CodeEntity."""
        entity = CodeEntity(
            file_path="src/main.py",
            entity_type="function",
            name="my_function",
            code="def my_function():\n    pass",
            start_line=1,
            end_line=2,
            docstring="A sample function.",
            decorators=[],
        )
        assert entity.file_path == "src/main.py"
        assert entity.entity_type == "function"
        assert entity.name == "my_function"
        assert entity.qualified_name == "my_function"
        assert entity.parent_class is None

    def test_create_method_entity(self):
        """Test creating a method CodeEntity with parent_class."""
        entity = CodeEntity(
            file_path="src/main.py",
            entity_type="method",
            name="my_method",
            code="def my_method(self):\n    pass",
            start_line=10,
            end_line=11,
            parent_class="MyClass",
        )
        assert entity.entity_type == "method"
        assert entity.qualified_name == "MyClass.my_method"

    def test_create_class_entity(self):
        """Test creating a class CodeEntity."""
        entity = CodeEntity(
            file_path="src/main.py",
            entity_type="class",
            name="MyClass",
            code="class MyClass:\n    pass",
            start_line=5,
            end_line=6,
            decorators=["dataclass"],
        )
        assert entity.entity_type == "class"
        assert entity.qualified_name == "MyClass"
        assert entity.decorators == ["dataclass"]

    def test_summary_with_docstring(self):
        """Test summary property with docstring."""
        entity = CodeEntity(
            file_path="src/main.py",
            entity_type="function",
            name="helper",
            code="def helper():\n    pass",
            start_line=1,
            end_line=2,
            docstring="A helper function.\n\nDoes helpful things.",
        )
        assert "function: helper" in entity.summary
        assert "A helper function." in entity.summary

    def test_summary_without_docstring(self):
        """Test summary property without docstring."""
        entity = CodeEntity(
            file_path="src/main.py",
            entity_type="function",
            name="helper",
            code="def helper():\n    pass",
            start_line=1,
            end_line=2,
        )
        assert entity.summary == "function: helper"


# =============================================================================
# CodebaseIndex Model Tests
# =============================================================================


class TestCodebaseIndex:
    """Tests for CodebaseIndex model."""

    def test_empty_index(self):
        """Test creating an empty index."""
        index = CodebaseIndex()
        assert index.entities == []
        assert index.file_hashes == {}
        assert index.total_files == 0
        assert index.total_entities == 0

    def test_get_entities_for_file(self):
        """Test filtering entities by file."""
        entities = [
            CodeEntity(
                file_path="a.py", entity_type="function",
                name="f1", code="", start_line=1, end_line=1,
            ),
            CodeEntity(
                file_path="b.py", entity_type="function",
                name="f2", code="", start_line=1, end_line=1,
            ),
            CodeEntity(
                file_path="a.py", entity_type="class",
                name="C1", code="", start_line=5, end_line=5,
            ),
        ]
        index = CodebaseIndex(entities=entities)
        a_entities = index.get_entities_for_file("a.py")
        assert len(a_entities) == 2
        assert all(e.file_path == "a.py" for e in a_entities)

    def test_get_entities_by_type(self):
        """Test filtering entities by type."""
        entities = [
            CodeEntity(
                file_path="a.py", entity_type="function",
                name="f1", code="", start_line=1, end_line=1,
            ),
            CodeEntity(
                file_path="b.py", entity_type="class",
                name="C1", code="", start_line=1, end_line=1,
            ),
            CodeEntity(
                file_path="a.py", entity_type="function",
                name="f2", code="", start_line=5, end_line=5,
            ),
        ]
        index = CodebaseIndex(entities=entities)
        functions = index.get_entities_by_type("function")
        assert len(functions) == 2
        classes = index.get_entities_by_type("class")
        assert len(classes) == 1


# =============================================================================
# ASTIndexer Initialization Tests
# =============================================================================


class TestASTIndexerInit:
    """Tests for ASTIndexer initialization."""

    def test_default_init(self):
        """Test default initialization."""
        indexer = ASTIndexer()
        assert "__pycache__" in indexer.exclude_dirs
        assert ".venv" in indexer.exclude_dirs
        assert "__init__.py" in indexer.exclude_files
        assert indexer.previous_hashes == {}

    def test_custom_exclude_dirs(self):
        """Test initialization with custom exclude dirs."""
        indexer = ASTIndexer(exclude_dirs={"custom_dir"})
        assert "custom_dir" in indexer.exclude_dirs
        assert "__pycache__" not in indexer.exclude_dirs

    def test_include_init_files(self):
        """Test initialization with include_init_files=True."""
        indexer = ASTIndexer(include_init_files=True)
        assert "__init__.py" not in indexer.exclude_files


# =============================================================================
# ASTIndexer Parsing Tests
# =============================================================================


class TestASTIndexerParsing:
    """Tests for ASTIndexer file parsing."""

    def test_parse_single_file(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test parsing a single Python file."""
        entities = indexer._parse_file(sample_python_file, "sample.py")

        # Should find: simple_function, no_docstring_function, MyClass,
        # __init__, greet, async_method
        names = [e.name for e in entities]
        assert "simple_function" in names
        assert "no_docstring_function" in names
        assert "MyClass" in names
        assert "__init__" in names
        assert "greet" in names
        assert "async_method" in names

    def test_entity_types(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that entity types are correctly assigned."""
        entities = indexer._parse_file(sample_python_file, "sample.py")
        entity_map = {e.name: e for e in entities}

        assert entity_map["simple_function"].entity_type == "function"
        assert entity_map["MyClass"].entity_type == "class"
        assert entity_map["greet"].entity_type == "method"
        assert entity_map["async_method"].entity_type == "method"

    def test_docstrings_extracted(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that docstrings are correctly extracted."""
        entities = indexer._parse_file(sample_python_file, "sample.py")
        entity_map = {e.name: e for e in entities}

        assert "Add two numbers" in entity_map["simple_function"].docstring
        assert entity_map["no_docstring_function"].docstring is None
        assert "A sample class" in entity_map["MyClass"].docstring
        assert "Return a greeting" in entity_map["greet"].docstring

    def test_parent_class_for_methods(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that parent_class is set for methods."""
        entities = indexer._parse_file(sample_python_file, "sample.py")
        entity_map = {e.name: e for e in entities}

        assert entity_map["greet"].parent_class == "MyClass"
        assert entity_map["async_method"].parent_class == "MyClass"
        assert entity_map["simple_function"].parent_class is None

    def test_line_numbers(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that line numbers are correct."""
        entities = indexer._parse_file(sample_python_file, "sample.py")
        entity_map = {e.name: e for e in entities}

        assert entity_map["simple_function"].start_line > 0
        assert entity_map["simple_function"].end_line >= entity_map["simple_function"].start_line

    def test_code_extraction(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that source code is correctly extracted."""
        entities = indexer._parse_file(sample_python_file, "sample.py")
        entity_map = {e.name: e for e in entities}

        assert "def simple_function" in entity_map["simple_function"].code
        assert "return x + y" in entity_map["simple_function"].code
        assert "class MyClass" in entity_map["MyClass"].code

    def test_parse_syntax_error(self, indexer: ASTIndexer, temp_dir: Path):
        """Test parsing a file with syntax errors raises SyntaxError."""
        bad_file = temp_dir / "bad.py"
        bad_file.write_text("def broken(\n")
        with pytest.raises(SyntaxError):
            indexer._parse_file(bad_file, "bad.py")


# =============================================================================
# ASTIndexer Directory Indexing Tests
# =============================================================================


class TestASTIndexerDirectory:
    """Tests for ASTIndexer directory indexing."""

    def test_index_directory(self, indexer: ASTIndexer, sample_project: Path):
        """Test indexing a complete directory."""
        index = indexer.index_directory(sample_project)

        assert index.total_files > 0
        assert index.total_entities > 0
        assert len(index.entities) == index.total_entities
        assert len(index.file_hashes) > 0

    def test_excludes_venv(self, indexer: ASTIndexer, sample_project: Path):
        """Test that .venv directory is excluded."""
        index = indexer.index_directory(sample_project)

        for entity in index.entities:
            assert ".venv" not in entity.file_path

    def test_excludes_init_files(self, indexer: ASTIndexer, sample_project: Path):
        """Test that __init__.py files are excluded by default."""
        index = indexer.index_directory(sample_project)

        for entity in index.entities:
            assert entity.file_path != "__init__.py"

    def test_includes_init_files_when_configured(self, sample_project: Path):
        """Test that __init__.py files are included when configured."""
        indexer = ASTIndexer(include_init_files=True)
        index = indexer.index_directory(sample_project)

        init_entities = [
            e for e in index.entities if "__init__.py" in e.file_path
        ]
        # There may or may not be entities in __init__.py depending on content
        # But the file should be processed (check hashes)
        init_files = [
            f for f in index.file_hashes.keys() if "__init__.py" in f
        ]
        assert len(init_files) > 0

    def test_finds_all_entity_types(self, indexer: ASTIndexer, sample_project: Path):
        """Test that all entity types are found."""
        index = indexer.index_directory(sample_project)

        types = {e.entity_type for e in index.entities}
        assert "function" in types
        assert "class" in types
        assert "method" in types

    def test_nonexistent_path_raises(self, indexer: ASTIndexer):
        """Test that indexing a nonexistent path raises an error."""
        with pytest.raises(ASTIndexerError, match="does not exist"):
            indexer.index_directory(Path("/nonexistent/path"))

    def test_file_path_raises(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test that indexing a file (not directory) raises an error."""
        with pytest.raises(ASTIndexerError, match="not a directory"):
            indexer.index_directory(sample_python_file)

    def test_file_hashes_computed(self, indexer: ASTIndexer, sample_project: Path):
        """Test that file hashes are computed for all indexed files."""
        index = indexer.index_directory(sample_project)

        for file_path in index.file_hashes:
            assert len(index.file_hashes[file_path]) == 64  # SHA-256 hex length


# =============================================================================
# ASTIndexer Incremental Indexing Tests
# =============================================================================


class TestASTIndexerIncremental:
    """Tests for ASTIndexer incremental indexing."""

    def test_incremental_skips_unchanged(self, indexer: ASTIndexer, sample_project: Path):
        """Test that incremental indexing skips unchanged files."""
        # First index
        index1 = indexer.index_directory(sample_project)
        first_count = index1.total_entities

        # Store hashes for incremental check
        indexer.previous_hashes = index1.file_hashes.copy()

        # Second index should find no changed files
        index2 = indexer.index_directory(sample_project)
        assert index2.total_files == 0  # No files re-parsed
        assert index2.total_entities == 0  # No new entities

    def test_incremental_detects_changes(self, indexer: ASTIndexer, sample_project: Path):
        """Test that incremental indexing detects changed files."""
        # First index
        index1 = indexer.index_directory(sample_project)
        indexer.previous_hashes = index1.file_hashes.copy()

        # Modify a file
        main_file = sample_project / "src" / "main.py"
        content = main_file.read_text()
        main_file.write_text(content + "\n\ndef new_function():\n    pass\n")

        # Second index should detect the change
        index2 = indexer.index_directory(sample_project)
        assert index2.total_files == 1  # Only the changed file
        assert index2.total_entities > 0

    def test_get_changed_files(self, indexer: ASTIndexer):
        """Test change detection between hash snapshots."""
        old_hashes = {
            "a.py": "hash1",
            "b.py": "hash2",
            "c.py": "hash3",
        }
        new_hashes = {
            "a.py": "hash1",      # Unchanged
            "b.py": "hash_new",   # Modified
            "d.py": "hash4",      # Added
        }

        added, modified, deleted = indexer.get_changed_files(new_hashes, old_hashes)

        assert added == {"d.py"}
        assert modified == {"b.py"}
        assert deleted == {"c.py"}


# =============================================================================
# ASTIndexer File Hash Tests
# =============================================================================


class TestASTIndexerHashes:
    """Tests for ASTIndexer hash computation."""

    def test_compute_file_hash(self, indexer: ASTIndexer, sample_python_file: Path):
        """Test computing a file hash."""
        hash_val = indexer._compute_file_hash(sample_python_file)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA-256 hex

    def test_same_content_same_hash(self, indexer: ASTIndexer, temp_dir: Path):
        """Test that identical content produces identical hashes."""
        file1 = temp_dir / "a.py"
        file2 = temp_dir / "b.py"
        content = "def hello():\n    pass\n"
        file1.write_text(content)
        file2.write_text(content)

        assert indexer._compute_file_hash(file1) == indexer._compute_file_hash(file2)

    def test_different_content_different_hash(self, indexer: ASTIndexer, temp_dir: Path):
        """Test that different content produces different hashes."""
        file1 = temp_dir / "a.py"
        file2 = temp_dir / "b.py"
        file1.write_text("def hello():\n    pass\n")
        file2.write_text("def world():\n    pass\n")

        assert indexer._compute_file_hash(file1) != indexer._compute_file_hash(file2)

    def test_compute_file_hashes_directory(self, indexer: ASTIndexer, sample_project: Path):
        """Test computing hashes for all files in a directory."""
        hashes = indexer.compute_file_hashes(sample_project)
        assert len(hashes) > 0
        for path, hash_val in hashes.items():
            assert len(hash_val) == 64


# =============================================================================
# ASTIndexer ChromaDB Integration Tests
# =============================================================================


class TestASTIndexerChromaDB:
    """Tests for ASTIndexer ChromaDB integration."""

    @pytest.mark.asyncio
    async def test_index_to_chromadb_with_index(self, indexer: ASTIndexer, sample_project: Path):
        """Test sending a pre-computed index to ChromaDB."""
        index = indexer.index_directory(sample_project)

        # Mock the service client
        mock_client = AsyncMock()
        mock_client.index_codebase = AsyncMock(
            return_value={"indexed_count": index.total_entities}
        )

        result = await indexer.index_to_chromadb(
            service_client=mock_client,
            project_code="test-project",
            index=index,
        )

        mock_client.index_codebase.assert_called_once()
        call_args = mock_client.index_codebase.call_args
        assert call_args.kwargs["project_code"] == "test-project"
        assert len(call_args.kwargs["entities"]) == index.total_entities

    @pytest.mark.asyncio
    async def test_index_to_chromadb_with_source_path(
        self, indexer: ASTIndexer, sample_project: Path
    ):
        """Test indexing to ChromaDB from a source path."""
        mock_client = AsyncMock()
        mock_client.index_codebase = AsyncMock(
            return_value={"indexed_count": 5}
        )

        result = await indexer.index_to_chromadb(
            service_client=mock_client,
            project_code="test-project",
            source_path=sample_project,
        )

        mock_client.index_codebase.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_to_chromadb_no_args_raises(self, indexer: ASTIndexer):
        """Test that calling without index or source_path raises error."""
        mock_client = AsyncMock()

        with pytest.raises(ASTIndexerError, match="Either 'index' or 'source_path'"):
            await indexer.index_to_chromadb(
                service_client=mock_client,
                project_code="test-project",
            )

    @pytest.mark.asyncio
    async def test_index_to_chromadb_empty_index(self, indexer: ASTIndexer):
        """Test indexing an empty index to ChromaDB."""
        mock_client = AsyncMock()
        empty_index = CodebaseIndex()

        result = await indexer.index_to_chromadb(
            service_client=mock_client,
            project_code="test-project",
            index=empty_index,
        )

        # Should not call the service for empty index
        mock_client.index_codebase.assert_not_called()
        assert result["indexed_count"] == 0

    @pytest.mark.asyncio
    async def test_index_to_chromadb_updates_previous_hashes(
        self, indexer: ASTIndexer, sample_project: Path
    ):
        """Test that indexing updates previous_hashes for incremental tracking."""
        index = indexer.index_directory(sample_project)
        mock_client = AsyncMock()
        mock_client.index_codebase = AsyncMock(return_value={"indexed_count": 5})

        assert indexer.previous_hashes == {}

        await indexer.index_to_chromadb(
            service_client=mock_client,
            project_code="test-project",
            index=index,
        )

        assert indexer.previous_hashes == index.file_hashes


# =============================================================================
# ASTIndexer Decorator Extraction Tests
# =============================================================================


class TestASTIndexerDecorators:
    """Tests for decorator extraction."""

    def test_extract_decorators(self, indexer: ASTIndexer, temp_dir: Path):
        """Test extracting decorators from functions and classes."""
        code = textwrap.dedent('''\
            from functools import lru_cache


            @lru_cache
            def cached_function():
                """A cached function."""
                pass


            @staticmethod
            def static_func():
                pass
        ''')
        file_path = temp_dir / "decorated.py"
        file_path.write_text(code)

        entities = indexer._parse_file(file_path, "decorated.py")
        entity_map = {e.name: e for e in entities}

        assert "lru_cache" in entity_map["cached_function"].decorators
        assert "staticmethod" in entity_map["static_func"].decorators
