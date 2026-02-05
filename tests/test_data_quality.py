"""
Tests for data quality validation logic.

These tests verify that the orchestrator's validation catches
bad data before it reaches BigQuery.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.orchestrator import DataQualityError, validate


class TestValidation:
    """Test the validate() function used by the orchestrator."""

    def test_valid_data_passes(self):
        df = pd.DataFrame({
            "symbol": ["AAPL", "MSFT"],
            "reportDate": ["2025-01-30", "2025-01-28"],
            "estimate": [2.35, 3.11],
        })
        # Should not raise
        validate(df, ["symbol", "reportDate"])

    def test_empty_dataframe_raises(self):
        df = pd.DataFrame()
        with pytest.raises(DataQualityError, match="empty"):
            validate(df, ["symbol"])

    def test_missing_key_column_raises(self):
        df = pd.DataFrame({"symbol": ["AAPL"], "value": [1]})
        with pytest.raises(DataQualityError, match="missing"):
            validate(df, ["symbol", "reportDate"])

    def test_null_key_column_raises(self):
        df = pd.DataFrame({
            "symbol": ["AAPL", None],
            "reportDate": ["2025-01-30", "2025-01-28"],
        })
        with pytest.raises(DataQualityError, match="null"):
            validate(df, ["symbol", "reportDate"])

    def test_duplicate_keys_raises(self):
        df = pd.DataFrame({
            "symbol": ["AAPL", "AAPL"],
            "reportDate": ["2025-01-30", "2025-01-30"],
            "estimate": [2.35, 2.40],
        })
        with pytest.raises(DataQualityError, match="duplicate"):
            validate(df, ["symbol", "reportDate"])

    def test_single_row_passes(self):
        df = pd.DataFrame({
            "symbol": ["AAPL"],
            "reportDate": ["2025-01-30"],
        })
        validate(df, ["symbol", "reportDate"])

    def test_non_duplicate_similar_keys_pass(self):
        df = pd.DataFrame({
            "symbol": ["AAPL", "AAPL"],
            "reportDate": ["2025-01-30", "2025-01-31"],
        })
        validate(df, ["symbol", "reportDate"])

    def test_multiple_null_keys_raises(self):
        df = pd.DataFrame({
            "symbol": [None, None],
            "reportDate": ["2025-01-30", "2025-01-28"],
        })
        with pytest.raises(DataQualityError, match="null"):
            validate(df, ["symbol", "reportDate"])
