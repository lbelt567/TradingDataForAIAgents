"""Tests for pipeline configuration module."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from pipeline.config import ConfigError, PipelineConfig, _require, _optional


class TestRequireHelper:
    def test_returns_value_when_set(self):
        with patch.dict(os.environ, {"TEST_VAR": "value"}):
            assert _require("TEST_VAR") == "value"

    def test_raises_on_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError, match="TEST_VAR"):
                _require("TEST_VAR")

    def test_raises_on_empty(self):
        with patch.dict(os.environ, {"TEST_VAR": ""}):
            with pytest.raises(ConfigError, match="TEST_VAR"):
                _require("TEST_VAR")


class TestOptionalHelper:
    def test_returns_value_when_set(self):
        with patch.dict(os.environ, {"OPT_VAR": "value"}):
            assert _optional("OPT_VAR") == "value"

    def test_returns_none_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _optional("OPT_VAR") is None

    def test_returns_none_when_empty(self):
        with patch.dict(os.environ, {"OPT_VAR": ""}):
            assert _optional("OPT_VAR") is None


class TestPipelineConfig:
    @staticmethod
    def _env_vars():
        return {
            "GCP_PROJECT_ID": "my-project",
            "GCP_SA_KEY": '{"type": "service_account"}',
            "BQ_DATASET": "trading_data",
            "ALPHA_API_KEY": "alpha-key",
            "FINRA_CLIENT_ID": "finra-id",
            "FINRA_CLIENT_SECRET": "finra-secret",
        }

    def test_from_env_loads_all_required(self):
        with patch.dict(os.environ, self._env_vars(), clear=True):
            config = PipelineConfig.from_env()
            assert config.gcp_project_id == "my-project"
            assert config.alpha_api_key == "alpha-key"
            assert config.bq_dataset == "trading_data"

    def test_from_env_defaults(self):
        env = self._env_vars()
        del env["BQ_DATASET"]
        with patch.dict(os.environ, env, clear=True):
            config = PipelineConfig.from_env()
            assert config.bq_dataset == "trading_data"
            assert config.ibkr_host == "127.0.0.1"
            assert config.ibkr_port == 7496

    def test_from_env_missing_required_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError):
                PipelineConfig.from_env()

    def test_sa_credentials_info_from_json_string(self):
        env = self._env_vars()
        with patch.dict(os.environ, env, clear=True):
            config = PipelineConfig.from_env()
            info = config.sa_credentials_info
            assert info == {"type": "service_account"}

    def test_sa_credentials_info_from_file(self):
        creds = {"type": "service_account", "project_id": "test"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(creds, f)
            f.flush()
            env = self._env_vars()
            env["GCP_SA_KEY"] = f.name
            with patch.dict(os.environ, env, clear=True):
                config = PipelineConfig.from_env()
                info = config.sa_credentials_info
                assert info == creds
        os.unlink(f.name)

    def test_sa_credentials_path_from_json_string(self):
        env = self._env_vars()
        with patch.dict(os.environ, env, clear=True):
            config = PipelineConfig.from_env()
            path = config.sa_credentials_path
            assert path.endswith(".json")
            with open(path) as f:
                assert json.load(f) == {"type": "service_account"}
            os.unlink(path)

    def test_sa_credentials_path_from_file(self):
        creds = {"type": "service_account"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(creds, f)
            f.flush()
            env = self._env_vars()
            env["GCP_SA_KEY"] = f.name
            with patch.dict(os.environ, env, clear=True):
                config = PipelineConfig.from_env()
                assert config.sa_credentials_path == f.name
        os.unlink(f.name)

    def test_optional_gcs_bucket(self):
        env = self._env_vars()
        env["GCS_ARCHIVE_BUCKET"] = "my-bucket"
        with patch.dict(os.environ, env, clear=True):
            config = PipelineConfig.from_env()
            assert config.gcs_archive_bucket == "my-bucket"

    def test_ibkr_custom_values(self):
        env = self._env_vars()
        env["IBKR_HOST"] = "192.168.1.100"
        env["IBKR_PORT"] = "4002"
        env["IBKR_CLIENT_ID"] = "5"
        with patch.dict(os.environ, env, clear=True):
            config = PipelineConfig.from_env()
            assert config.ibkr_host == "192.168.1.100"
            assert config.ibkr_port == 4002
            assert config.ibkr_client_id == 5
