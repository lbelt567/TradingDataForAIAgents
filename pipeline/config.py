"""
Configuration module for the trading data pipeline.

All configuration is loaded from environment variables.
No hardcoded credentials or fallback values.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when a required configuration value is missing."""


def _require(var: str) -> str:
    """Return the value of an environment variable or raise ConfigError."""
    value = os.environ.get(var)
    if not value:
        raise ConfigError(
            f"Required environment variable '{var}' is not set. "
            f"Set it in your environment or in a .env file."
        )
    return value


def _optional(var: str) -> str | None:
    """Return the value of an environment variable or None."""
    return os.environ.get(var) or None


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration loaded from environment variables."""

    # GCP core
    gcp_project_id: str
    gcp_sa_key: str  # JSON string or file path
    bq_dataset: str

    # API keys
    alpha_api_key: str
    finra_client_id: str
    finra_client_secret: str

    # Optional
    gcs_archive_bucket: str | None = None

    # IBKR TWS connection (optional -- only needed for ibkr_short scraper)
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7496
    ibkr_client_id: int = 1

    # BigQuery table schemas keyed by table name
    table_schemas: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> PipelineConfig:
        """Build config from environment variables."""
        return cls(
            gcp_project_id=_require("GCP_PROJECT_ID"),
            gcp_sa_key=_require("GCP_SA_KEY"),
            bq_dataset=os.environ.get("BQ_DATASET", "trading_data"),
            alpha_api_key=_require("ALPHA_API_KEY"),
            finra_client_id=_require("FINRA_CLIENT_ID"),
            finra_client_secret=_require("FINRA_CLIENT_SECRET"),
            gcs_archive_bucket=_optional("GCS_ARCHIVE_BUCKET"),
            ibkr_host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            ibkr_port=int(os.environ.get("IBKR_PORT", "7496")),
            ibkr_client_id=int(os.environ.get("IBKR_CLIENT_ID", "1")),
        )

    @property
    def sa_credentials_path(self) -> str:
        """Return a file path to the service account JSON key.

        If GCP_SA_KEY is a JSON string (e.g. from GitHub Actions secret),
        write it to a temp file and return the path. If it's already a file
        path, return it directly.
        """
        key = self.gcp_sa_key
        # If it looks like a file path and exists, use it directly
        if not key.strip().startswith("{") and Path(key).is_file():
            return key
        # Otherwise treat as inline JSON -- write to temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="gcp_sa_"
        )
        tmp.write(key)
        tmp.close()
        return tmp.name

    @property
    def sa_credentials_info(self) -> dict:
        """Return the service account credentials as a dict."""
        key = self.gcp_sa_key
        if key.strip().startswith("{"):
            return json.loads(key)
        with open(key) as f:
            return json.load(f)
