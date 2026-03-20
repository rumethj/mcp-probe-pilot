"""Unit tests for the ASTIndexer."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_probe_pilot.discover.ast_indexer import ASTIndexer, ASTIndexerError


# ------------------------------------------------------------------
# index_directory
# ------------------------------------------------------------------


class TestIndexDirectory:
    def test_indexes_python_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(
            'def hello():\n    """Say hello."""\n    return "hi"\n'
        )
        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)

        assert index.total_files == 1
        assert index.total_entities >= 1
        assert any(e.name == "hello" for e in index.entities)

    def test_extracts_classes_and_methods(self, tmp_path: Path) -> None:
        (tmp_path / "models.py").write_text(
            "class User:\n"
            '    """A user."""\n'
            "    def greet(self):\n"
            "        pass\n"
        )
        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)

        names = {e.name for e in index.entities}
        assert "User" in names
        assert "greet" in names

        greet = next(e for e in index.entities if e.name == "greet")
        assert greet.entity_type == "method"
        assert greet.parent_class == "User"

    def test_nonexistent_path_raises(self) -> None:
        indexer = ASTIndexer()
        with pytest.raises(ASTIndexerError, match="Path does not exist"):
            indexer.index_directory(Path("/nonexistent"))

    def test_file_path_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.py"
        f.write_text("x = 1\n")
        indexer = ASTIndexer()
        with pytest.raises(ASTIndexerError, match="not a directory"):
            indexer.index_directory(f)

    def test_excludes_default_dirs(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "mod.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("def f(): pass\n")

        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)
        assert all("__pycache__" not in e.file_path for e in index.entities)

    def test_excludes_init_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("x = 1\n")
        (tmp_path / "core.py").write_text("def f(): pass\n")

        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)
        assert all("__init__" not in e.file_path for e in index.entities)

    def test_include_init_files(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("def init(): pass\n")

        indexer = ASTIndexer(include_init_files=True)
        index = indexer.index_directory(tmp_path)
        assert any(e.name == "init" for e in index.entities)


# ------------------------------------------------------------------
# Incremental hashing
# ------------------------------------------------------------------


class TestIncrementalIndexing:
    def test_skip_unchanged_files(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("def f(): pass\n")

        indexer = ASTIndexer()
        index1 = indexer.index_directory(tmp_path)
        assert index1.total_files == 1

        indexer.previous_hashes = index1.file_hashes
        index2 = indexer.index_directory(tmp_path)
        assert index2.total_files == 0


# ------------------------------------------------------------------
# Decorator extraction
# ------------------------------------------------------------------


class TestDecoratorExtraction:
    def test_extracts_simple_decorator(self, tmp_path: Path) -> None:
        (tmp_path / "deco.py").write_text(
            "def my_decorator(f): return f\n"
            "@my_decorator\n"
            "def decorated(): pass\n"
        )
        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)

        decorated = next(e for e in index.entities if e.name == "decorated")
        assert "my_decorator" in decorated.decorators


# ------------------------------------------------------------------
# Docstring extraction
# ------------------------------------------------------------------


class TestDocstringExtraction:
    def test_extracts_docstring(self, tmp_path: Path) -> None:
        (tmp_path / "doc.py").write_text(
            'def documented():\n    """This is a docstring."""\n    pass\n'
        )
        indexer = ASTIndexer()
        index = indexer.index_directory(tmp_path)

        entity = next(e for e in index.entities if e.name == "documented")
        assert entity.docstring == "This is a docstring."
