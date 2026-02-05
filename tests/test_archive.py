"""Tests for the GCS archive module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.archive import ARCHIVABLE_TABLES, archive_all, archive_table


class TestArchivableTables:
    def test_excludes_pipeline_runs(self):
        assert "pipeline_runs" not in ARCHIVABLE_TABLES

    def test_includes_data_tables(self):
        expected = {
            "stock_loan", "earnings_calendar", "nasdaq_earnings",
            "ats_otc", "edgar_filings", "fomc_meetings",
        }
        assert expected == set(ARCHIVABLE_TABLES)


class TestArchiveTable:
    @patch("pipeline.archive.BigQueryClient")
    def test_raises_without_bucket(self, mock_bq_cls):
        config = MagicMock()
        config.gcs_archive_bucket = None
        with pytest.raises(ValueError, match="GCS_ARCHIVE_BUCKET"):
            archive_table("stock_loan", config)

    @patch("pipeline.archive.BigQueryClient")
    def test_exports_to_gcs(self, mock_bq_cls):
        config = MagicMock()
        config.gcs_archive_bucket = "my-bucket"
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        uri = archive_table("stock_loan", config)

        assert uri.startswith("gs://my-bucket/archive/stock_loan/")
        assert uri.endswith(".parquet")
        mock_bq.export_parquet.assert_called_once()


class TestArchiveAll:
    @patch("pipeline.archive.archive_table")
    def test_archives_all_data_tables(self, mock_archive_table):
        config = MagicMock()
        mock_archive_table.return_value = "gs://bucket/file.parquet"

        uris = archive_all(config)

        assert len(uris) == len(ARCHIVABLE_TABLES)
        assert mock_archive_table.call_count == len(ARCHIVABLE_TABLES)

    @patch("pipeline.archive.archive_table")
    def test_continues_on_failure(self, mock_archive_table):
        config = MagicMock()
        mock_archive_table.side_effect = [
            "gs://bucket/ok.parquet",
            Exception("export failed"),
            "gs://bucket/ok2.parquet",
            "gs://bucket/ok3.parquet",
            "gs://bucket/ok4.parquet",
            "gs://bucket/ok5.parquet",
        ]

        uris = archive_all(config)

        # One failed, so 5 succeeded
        assert len(uris) == 5
