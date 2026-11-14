"""Tests for the directory scanner module."""
import pathlib
import pytest

from zerorot.scanner import scan_directory, select_core_files

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class TestScanDirectory:
    def test_node_sample_finds_files(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        assert len(result["files"]) > 0
        assert result["root"].name == "node_sample"

    def test_node_sample_detects_entry_point(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        entry_names = [f.name for f in result["entry_points"]]
        assert "index.js" in entry_names

    def test_python_sample_finds_files(self):
        result = scan_directory(str(FIXTURES / "python_sample"))
        assert len(result["files"]) > 0

    def test_python_sample_detects_entry_point(self):
        result = scan_directory(str(FIXTURES / "python_sample"))
        entry_names = [f.name for f in result["entry_points"]]
        assert "main.py" in entry_names

    def test_tree_str_is_string(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        assert isinstance(result["tree_str"], str)
        assert "node_sample" in result["tree_str"]

    def test_skips_lock_files(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        file_names = [f.name for f in result["files"]]
        assert "package-lock.json" not in file_names
        assert "yarn.lock" not in file_names

    def test_env_example_included_in_config_files(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        config_names = [f.name for f in result["config_files"]]
        assert ".env.example" in config_names


class TestSelectCoreFiles:
    def test_respects_max_files(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        selected = select_core_files(result, max_files=2)
        assert len(selected) <= 2

    def test_entry_points_have_priority(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        selected = select_core_files(result, max_files=10)
        selected_names = [f.name for f in selected]
        assert "index.js" in selected_names
