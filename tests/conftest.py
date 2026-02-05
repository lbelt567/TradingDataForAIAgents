"""
Shared pytest fixtures and configuration.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def mock_config():
    """Return a MagicMock PipelineConfig with sensible defaults."""
    config = MagicMock()
    config.gcp_project_id = "test-project"
    config.bq_dataset = "trading_data"
    config.sa_credentials_info = {"type": "service_account"}
    config.alpha_api_key = "test-alpha-key"
    config.finra_client_id = "test-finra-id"
    config.finra_client_secret = "test-finra-secret"
    config.gcs_archive_bucket = None
    config.ibkr_host = "127.0.0.1"
    config.ibkr_port = 7496
    config.ibkr_client_id = 1
    return config


@pytest.fixture
def sample_stock_loan_df():
    """Sample stock loan DataFrame for testing."""
    return pd.DataFrame({
        "SYM": ["AAPL", "MSFT", "TSLA"],
        "CURRENCY": ["USD", "USD", "USD"],
        "NAME": ["Apple Inc", "Microsoft", "Tesla Inc"],
        "FEERATE": [0.25, 0.30, 15.5],
        "REBATERATE": [5.0, 4.95, -10.25],
        "AVAILABLE": [10_000_000, 8_000_000, 500_000],
        "COUNTRY": ["US", "US", "US"],
    })


@pytest.fixture
def sample_earnings_df():
    """Sample earnings calendar DataFrame for testing."""
    return pd.DataFrame({
        "symbol": ["AAPL", "MSFT"],
        "reportDate": ["2025-01-30", "2025-01-28"],
        "name": ["Apple Inc", "Microsoft Corp"],
        "fiscalDateEnding": ["2024-12-31", "2024-12-31"],
        "estimate": [2.35, 3.11],
        "currency": ["USD", "USD"],
    })
