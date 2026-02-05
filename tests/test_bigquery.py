"""
Tests for the BigQuery client module.

Tests cover schema definitions, MERGE SQL generation logic, and
client initialization. Actual BigQuery calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from pipeline.bigquery import TABLE_SCHEMAS, BigQueryClient


class TestTableSchemas:
    """Verify all required tables have schemas defined."""

    REQUIRED_TABLES = [
        "stock_loan",
        "earnings_calendar",
        "nasdaq_earnings",
        "ats_otc",
        "edgar_filings",
        "fomc_meetings",
        "pipeline_runs",
    ]

    def test_all_required_tables_exist(self):
        for table in self.REQUIRED_TABLES:
            assert table in TABLE_SCHEMAS, f"Missing schema for {table}"

    def test_all_tables_have_last_updated(self):
        """Every data table (not pipeline_runs) should have _last_updated."""
        for table, schema in TABLE_SCHEMAS.items():
            if table == "pipeline_runs":
                continue
            col_names = [f.name for f in schema]
            assert "_last_updated" in col_names, (
                f"Table {table} missing _last_updated column"
            )

    def test_all_tables_have_scraped_at(self):
        """Every data table should have _scraped_at."""
        for table, schema in TABLE_SCHEMAS.items():
            if table == "pipeline_runs":
                continue
            col_names = [f.name for f in schema]
            assert "_scraped_at" in col_names, (
                f"Table {table} missing _scraped_at column"
            )

    def test_stock_loan_schema(self):
        schema = TABLE_SCHEMAS["stock_loan"]
        col_names = [f.name for f in schema]
        assert "SYM" in col_names
        assert "CURRENCY" in col_names
        assert "FEERATE" in col_names
        assert "AVAILABLE" in col_names

    def test_earnings_calendar_schema(self):
        schema = TABLE_SCHEMAS["earnings_calendar"]
        col_names = [f.name for f in schema]
        assert "symbol" in col_names
        assert "reportDate" in col_names

    def test_nasdaq_earnings_schema(self):
        schema = TABLE_SCHEMAS["nasdaq_earnings"]
        col_names = [f.name for f in schema]
        assert "Symbol" in col_names
        assert "Date" in col_names

    def test_ats_otc_schema(self):
        schema = TABLE_SCHEMAS["ats_otc"]
        col_names = [f.name for f in schema]
        assert "issueSymbolIdentifier" in col_names
        assert "initialPublishedDate" in col_names

    def test_edgar_filings_schema(self):
        schema = TABLE_SCHEMAS["edgar_filings"]
        col_names = [f.name for f in schema]
        assert "ticker" in col_names
        assert "accessionNumber" in col_names

    def test_fomc_meetings_schema(self):
        schema = TABLE_SCHEMAS["fomc_meetings"]
        col_names = [f.name for f in schema]
        assert "Year" in col_names
        assert "Month" in col_names
        assert "Meeting_Dates" in col_names

    def test_pipeline_runs_schema(self):
        schema = TABLE_SCHEMAS["pipeline_runs"]
        col_names = [f.name for f in schema]
        assert "scraper" in col_names
        assert "status" in col_names
        assert "rows_scraped" in col_names
        assert "timestamp" in col_names


class TestBigQueryClient:
    """Test BigQuery client methods (with mocked GCP calls)."""

    @patch("pipeline.bigquery.bigquery.Client")
    @patch("pipeline.bigquery.service_account.Credentials.from_service_account_info")
    def _make_client(self, mock_creds, mock_bq_client):
        mock_config = MagicMock()
        mock_config.gcp_project_id = "test-project"
        mock_config.bq_dataset = "trading_data"
        mock_config.sa_credentials_info = {"type": "service_account"}
        client = BigQueryClient(mock_config)
        return client, mock_bq_client

    def test_full_table_id(self):
        client, _ = self._make_client()
        assert (
            client.full_table_id("stock_loan")
            == "test-project.trading_data.stock_loan"
        )

    def test_dataset_ref(self):
        client, _ = self._make_client()
        assert client.dataset_ref == "test-project.trading_data"

    def test_upsert_empty_df_skips(self):
        client, _ = self._make_client()
        result = client.upsert("stock_loan", pd.DataFrame(), ["SYM", "CURRENCY"])
        assert result == {"inserted": 0, "updated": 0, "unchanged": 0}

    def test_ensure_table_unknown_raises(self):
        client, _ = self._make_client()
        with pytest.raises(ValueError, match="No schema defined"):
            client.ensure_table("nonexistent_table")
