"""Tests for the environment variable extractor."""
import pathlib
import pytest

from zerorot.env_extractor import extract_env_vars
from zerorot.scanner import scan_directory

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class TestExtractEnvVars:
    def test_node_sample_extracts_vars(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        assert len(env_vars) > 0

    def test_node_sample_finds_port(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        names = [v["name"] for v in env_vars]
        assert "PORT" in names

    def test_node_sample_finds_database_url(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        names = [v["name"] for v in env_vars]
        assert "DATABASE_URL" in names

    def test_node_sample_finds_jwt_secret(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        names = [v["name"] for v in env_vars]
        assert "JWT_SECRET" in names

    def test_python_sample_extracts_vars(self):
        result = scan_directory(str(FIXTURES / "python_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        assert len(env_vars) > 0

    def test_python_sample_finds_app_port(self):
        result = scan_directory(str(FIXTURES / "python_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        names = [v["name"] for v in env_vars]
        assert "APP_PORT" in names

    def test_env_example_defaults_are_read(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        port_var = next((v for v in env_vars if v["name"] == "PORT"), None)
        assert port_var is not None
        assert port_var.get("default") == "3000"

    def test_each_var_has_required_fields(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        for var in env_vars:
            assert "name" in var
            assert "type" in var
            assert "description" in var
            assert "required" in var

    def test_type_inference_integer(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        port_var = next((v for v in env_vars if v["name"] == "PORT"), None)
        if port_var:
            assert port_var["type"] == "integer"

    def test_type_inference_secret(self):
        result = scan_directory(str(FIXTURES / "node_sample"))
        env_vars = extract_env_vars(result["files"], result["root"])
        secret_var = next((v for v in env_vars if v["name"] == "JWT_SECRET"), None)
        if secret_var:
            assert "secret" in secret_var["type"].lower()
