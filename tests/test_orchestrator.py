"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from pipeline.orchestrator import DataQualityError, run_scraper, validate
from scrapers.base import BaseScraper


class MockScraper(BaseScraper):
    """Test scraper that returns controlled data."""

    def __init__(self, data=None, error=None):
        super().__init__()
        self._data = data
        self._error = error

    def scrape(self) -> pd.DataFrame:
        if self._error:
            raise self._error
        return self._data if self._data is not None else pd.DataFrame()

    def key_columns(self) -> list[str]:
        return ["id"]

    def table_name(self) -> str:
        return "test_table"


class TestRunScraper:
    """Test the full scrape-validate-upsert cycle."""

    @patch("pipeline.orchestrator.BigQueryClient")
    @patch("pipeline.orchestrator.PipelineConfig")
    def test_success_flow(self, mock_config_cls, mock_bq_cls):
        mock_config = MagicMock()
        mock_config_cls.from_env.return_value = mock_config
        mock_bq = MagicMock()
        mock_bq.upsert.return_value = {"inserted": 2, "updated": 0, "unchanged": 0}
        mock_bq_cls.return_value = mock_bq

        df = pd.DataFrame({"id": [1, 2], "value": ["a", "b"]})
        scraper = MockScraper(data=df)

        result = run_scraper(scraper, mock_config)

        assert result["status"] == "success"
        assert result["rows_scraped"] == 2
        assert result["rows_inserted"] == 2
        mock_bq.upsert.assert_called_once()
        mock_bq.log_pipeline_run.assert_called_once()

    @patch("pipeline.orchestrator.BigQueryClient")
    @patch("pipeline.orchestrator.PipelineConfig")
    def test_empty_scrape(self, mock_config_cls, mock_bq_cls):
        mock_config = MagicMock()
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        scraper = MockScraper(data=pd.DataFrame())

        result = run_scraper(scraper, mock_config)

        assert result["status"] == "empty"
        assert result["rows_scraped"] == 0
        mock_bq.upsert.assert_not_called()

    @patch("pipeline.orchestrator.BigQueryClient")
    @patch("pipeline.orchestrator.PipelineConfig")
    def test_quality_error_raises(self, mock_config_cls, mock_bq_cls):
        mock_config = MagicMock()
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        # Data with null key
        df = pd.DataFrame({"id": [1, None], "value": ["a", "b"]})
        scraper = MockScraper(data=df)

        with pytest.raises(DataQualityError, match="null"):
            run_scraper(scraper, mock_config)

        mock_bq.log_pipeline_run.assert_called_once()
        call_kwargs = mock_bq.log_pipeline_run.call_args
        assert call_kwargs.kwargs["status"] == "quality_error"

    @patch("pipeline.orchestrator.BigQueryClient")
    @patch("pipeline.orchestrator.PipelineConfig")
    def test_scraper_exception_raises(self, mock_config_cls, mock_bq_cls):
        mock_config = MagicMock()
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        scraper = MockScraper(error=RuntimeError("API down"))

        with pytest.raises(RuntimeError, match="API down"):
            run_scraper(scraper, mock_config)

        mock_bq.log_pipeline_run.assert_called_once()
        call_kwargs = mock_bq.log_pipeline_run.call_args
        assert call_kwargs.kwargs["status"] == "error"

    @patch("pipeline.orchestrator.BigQueryClient")
    @patch("pipeline.orchestrator.PipelineConfig")
    def test_duplicate_keys_raises(self, mock_config_cls, mock_bq_cls):
        mock_config = MagicMock()
        mock_bq = MagicMock()
        mock_bq_cls.return_value = mock_bq

        df = pd.DataFrame({"id": [1, 1], "value": ["a", "b"]})
        scraper = MockScraper(data=df)

        with pytest.raises(DataQualityError, match="duplicate"):
            run_scraper(scraper, mock_config)

    @patch("pipeline.orchestrator.BigQueryClient")
    def test_uses_provided_config(self, mock_bq_cls):
        mock_config = MagicMock()
        mock_bq = MagicMock()
        mock_bq.upsert.return_value = {"inserted": 1, "updated": 0}
        mock_bq_cls.return_value = mock_bq

        df = pd.DataFrame({"id": [1], "value": ["a"]})
        scraper = MockScraper(data=df)

        run_scraper(scraper, mock_config)

        mock_bq_cls.assert_called_once_with(mock_config)
