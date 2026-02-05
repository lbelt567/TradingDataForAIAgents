"""
Tests for scraper implementations.

These tests verify scraper interfaces without making real API calls.
External HTTP calls are mocked.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scrapers.base import BaseScraper


# ── Base scraper contract tests ─────────────────────────────────────


class DummyScraper(BaseScraper):
    """Concrete scraper for testing the base class."""

    def __init__(self, data: pd.DataFrame | None = None):
        super().__init__()
        self._data = data if data is not None else pd.DataFrame(
            {"id": [1, 2], "value": ["a", "b"]}
        )

    def scrape(self) -> pd.DataFrame:
        return self._data

    def key_columns(self) -> list[str]:
        return ["id"]

    def table_name(self) -> str:
        return "test_table"


class TestBaseScraper:
    def test_run_adds_scraped_at(self):
        scraper = DummyScraper()
        df = scraper.run()
        assert "_scraped_at" in df.columns
        assert df["_scraped_at"].dtype.name.startswith("datetime")

    def test_run_returns_all_rows(self):
        scraper = DummyScraper()
        df = scraper.run()
        assert len(df) == 2

    def test_run_empty_dataframe(self):
        scraper = DummyScraper(data=pd.DataFrame())
        df = scraper.run()
        assert df.empty

    def test_key_columns_returns_list(self):
        scraper = DummyScraper()
        keys = scraper.key_columns()
        assert isinstance(keys, list)
        assert len(keys) > 0

    def test_table_name_returns_string(self):
        scraper = DummyScraper()
        assert isinstance(scraper.table_name(), str)
        assert len(scraper.table_name()) > 0

    def test_session_has_retry(self):
        scraper = DummyScraper()
        session = scraper.session
        adapter = session.get_adapter("https://")
        assert adapter.max_retries.total == scraper.MAX_RETRIES


# ── AlphaVantage Earnings tests ─────────────────────────────────────


class TestAlphaEarningsScraper:
    @patch("scrapers.alpha_earnings.PipelineConfig")
    def test_scrape_parses_csv(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config.alpha_api_key = "test_key"
        mock_config_cls.from_env.return_value = mock_config

        from scrapers.alpha_earnings import AlphaEarningsScraper

        scraper = AlphaEarningsScraper(config=mock_config)

        csv_content = (
            "symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
            "AAPL,Apple Inc,2025-01-30,2024-12-31,2.35,USD\n"
            "MSFT,Microsoft,2025-01-28,2024-12-31,3.11,USD\n"
        )

        mock_resp = MagicMock()
        mock_resp.text = csv_content
        mock_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        scraper._session = mock_session

        df = scraper.scrape()

        assert len(df) == 2
        assert list(df.columns) == [
            "symbol", "name", "reportDate", "fiscalDateEnding",
            "estimate", "currency",
        ]
        assert df["symbol"].iloc[0] == "AAPL"
        assert df["estimate"].iloc[0] == 2.35


# ── NASDAQ Earnings tests ──────────────────────────────────────────


class TestNasdaqEarningsScraper:
    def test_scrape_parses_json(self):
        from scrapers.nasdaq_earnings import NasdaqEarningsScraper

        scraper = NasdaqEarningsScraper(days_ahead=1)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "rows": [
                    {
                        "symbol": "AAPL",
                        "name": "Apple Inc",
                        "epsForecast": "2.35",
                        "noOfEsts": "30",
                        "lastYearRptDt": "01/28/2024",
                        "lastYearEPS": "2.18",
                        "marketCap": "3,500,000,000,000",
                        "fiscalQuarterEnding": "Dec/2024",
                    }
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        scraper._session = mock_session

        df = scraper.scrape()

        assert len(df) == 1
        assert "Symbol" in df.columns
        assert "Date" in df.columns
        assert df["Symbol"].iloc[0] == "AAPL"


# ── FOMC tests ──────────────────────────────────────────────────────


class TestFOMCScraper:
    def test_scrape_parses_html(self):
        from scrapers.fomc import FOMCScraper

        scraper = FOMCScraper()

        html = """
        <html><body>
        <div class="panel panel-default">
          <div class="panel-heading"><h4>2025</h4></div>
          <div class="panel-body">
            <div class="fomc-meeting row">
              <div class="fomc-meeting__month">January</div>
              <div class="fomc-meeting__date">28-29*</div>
              <div class="fomc-meeting__sep"></div>
            </div>
            <div class="fomc-meeting row">
              <div class="fomc-meeting__month">March</div>
              <div class="fomc-meeting__date">18-19</div>
              <div class="fomc-meeting__sep"></div>
            </div>
          </div>
        </div>
        </body></html>
        """

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        scraper._session = mock_session

        df = scraper.scrape()

        assert len(df) == 2
        assert df["Year"].iloc[0] == "2025"
        assert df["Month"].iloc[0] == "January"
        assert df["Summary_of_Economic_Projections"].iloc[0] == "Yes"
        assert df["Summary_of_Economic_Projections"].iloc[1] == "No"


# ── EDGAR tests ─────────────────────────────────────────────────────


class TestEdgarScraper:
    def test_scrape_parses_submissions(self):
        from scrapers.edgar import EdgarScraper

        scraper = EdgarScraper(tickers=["AAPL"], filing_types=["10-K"])

        # Mock CIK resolution
        tickers_json = {"0": {"cik_str": 320193, "ticker": "AAPL"}}

        # Mock submissions response
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "accessionNumber": [
                        "0000320193-24-000001",
                        "0000320193-24-000002",
                        "0000320193-24-000003",
                    ],
                    "filingDate": ["2024-11-01", "2024-08-01", "2024-06-01"],
                    "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
                }
            }
        }

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "company_tickers" in url:
                resp.json.return_value = tickers_json
            elif "submissions" in url:
                resp.json.return_value = submissions
            return resp

        mock_session = MagicMock()
        mock_session.get.side_effect = mock_get
        scraper._session = mock_session

        df = scraper.scrape()

        assert len(df) == 1  # Only 10-K, not 10-Q or 8-K
        assert df["ticker"].iloc[0] == "AAPL"
        assert df["filingType"].iloc[0] == "10-K"


# ── FINRA ATS tests ─────────────────────────────────────────────────


class TestFinraAtsScraper:
    @patch("scrapers.finra_ats.PipelineConfig")
    def test_scrape_parses_json(self, mock_config_cls):
        mock_config = MagicMock()
        mock_config.finra_client_id = "test_id"
        mock_config.finra_client_secret = "test_secret"
        mock_config_cls.from_env.return_value = mock_config

        from scrapers.finra_ats import FinraAtsScraper

        scraper = FinraAtsScraper(config=mock_config)

        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "test_token"}
        token_resp.raise_for_status = MagicMock()

        data_resp = MagicMock()
        data_resp.json.return_value = [
            {
                "issueSymbolIdentifier": "AAPL",
                "totalWeeklyShareQuantity": 1000000,
                "totalWeeklyTradeCount": 5000,
                "lastUpdateDate": "2025-01-27",
                "initialPublishedDate": "2025-01-27",
            }
        ]
        data_resp.raise_for_status = MagicMock()

        def mock_post(url, **kwargs):
            if "oauth2" in url:
                return token_resp
            return data_resp

        mock_session = MagicMock()
        mock_session.post.side_effect = mock_post
        scraper._session = mock_session

        df = scraper.scrape()

        assert len(df) == 1
        assert df["issueSymbolIdentifier"].iloc[0] == "AAPL"
        assert df["totalWeeklyShareQuantity"].iloc[0] == 1000000
