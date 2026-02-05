"""Tests for the CLI entry point."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from pipeline.__main__ import main


class TestCLI:
    """Test pipeline CLI commands."""

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.orchestrator.run_scraper")
    def test_run_command(self, mock_run, mock_from_env):
        mock_from_env.return_value = MagicMock()
        mock_run.return_value = {"status": "success"}

        with patch("sys.argv", ["pipeline", "run", "alpha_earnings"]):
            main()

        mock_run.assert_called_once()

    @patch("pipeline.config.PipelineConfig.from_env")
    def test_run_unknown_scraper_exits(self, mock_from_env):
        mock_from_env.return_value = MagicMock()

        with patch("sys.argv", ["pipeline", "run", "nonexistent"]):
            with pytest.raises(SystemExit):
                main()

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.orchestrator.run_scraper")
    def test_run_all_command(self, mock_run, mock_from_env):
        mock_from_env.return_value = MagicMock()
        mock_run.return_value = {"status": "success"}

        with patch("sys.argv", ["pipeline", "run-all"]):
            main()

        # Should run for each scraper in SCRAPERS
        assert mock_run.call_count >= 6

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.bigquery.BigQueryClient")
    def test_setup_command(self, mock_bq_cls, mock_from_env):
        mock_from_env.return_value = MagicMock()
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        with patch("sys.argv", ["pipeline", "setup"]):
            main()

        mock_bq.ensure_all_tables.assert_called_once()

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.bigquery.BigQueryClient")
    def test_info_command(self, mock_bq_cls, mock_from_env):
        mock_from_env.return_value = MagicMock()
        mock_bq = MagicMock()
        mock_bq.table_info.return_value = {
            "num_rows": 100,
            "modified": "2025-01-30T12:00:00Z",
            "schema": [
                {"name": "SYM", "type": "STRING", "mode": "REQUIRED"}
            ],
        }
        mock_bq_cls.return_value = mock_bq

        with patch("sys.argv", ["pipeline", "info", "stock_loan"]):
            main()

        mock_bq.table_info.assert_called_once_with("stock_loan")

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.archive.archive_all")
    def test_archive_all_command(self, mock_archive_all, mock_from_env):
        mock_from_env.return_value = MagicMock()
        mock_archive_all.return_value = ["gs://bucket/file.parquet"]

        with patch("sys.argv", ["pipeline", "archive"]):
            main()

        mock_archive_all.assert_called_once()

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.archive.archive_table")
    def test_archive_single_command(self, mock_archive_table, mock_from_env):
        mock_config = MagicMock()
        mock_from_env.return_value = mock_config
        mock_archive_table.return_value = "gs://bucket/stock_loan.parquet"

        with patch("sys.argv", ["pipeline", "archive", "stock_loan"]):
            main()

        mock_archive_table.assert_called_once()

    def test_no_command_exits(self):
        with patch("sys.argv", ["pipeline"]):
            with pytest.raises(SystemExit):
                main()

    @patch("pipeline.config.PipelineConfig.from_env")
    @patch("pipeline.orchestrator.run_scraper")
    def test_run_all_continues_on_error(self, mock_run, mock_from_env):
        mock_from_env.return_value = MagicMock()
        # Simulate one failure among several calls
        mock_run.side_effect = [
            {"status": "success"},
            RuntimeError("boom"),
            {"status": "success"},
            {"status": "success"},
            {"status": "success"},
            {"status": "success"},
        ]

        with patch("sys.argv", ["pipeline", "run-all"]):
            main()  # Should not raise despite one failure
