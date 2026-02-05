"""
AlphaVantage Earnings Calendar scraper.

Fetches upcoming and recent earnings announcements using the
AlphaVantage EARNINGS_CALENDAR endpoint.
"""

from __future__ import annotations

import io
import logging

import pandas as pd

from pipeline.config import PipelineConfig
from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

ALPHA_EARNINGS_URL = "https://www.alphavantage.co/query"


class AlphaEarningsScraper(BaseScraper):
    """Scrape earnings calendar data from AlphaVantage."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        super().__init__()
        self._config = config or PipelineConfig.from_env()

    def table_name(self) -> str:
        return "earnings_calendar"

    def key_columns(self) -> list[str]:
        return ["symbol", "reportDate"]

    def scrape(self) -> pd.DataFrame:
        params = {
            "function": "EARNINGS_CALENDAR",
            "horizon": "3month",
            "apikey": self._config.alpha_api_key,
        }
        resp = self.session.get(ALPHA_EARNINGS_URL, params=params, timeout=30)
        resp.raise_for_status()

        content = resp.text
        if "Thank you for using Alpha Vantage" in content:
            raise ScraperError(
                "AlphaVantage API rate limit or invalid key. "
                "Response: " + content[:200]
            )

        df = pd.read_csv(io.StringIO(content))

        if df.empty:
            self.logger.warning("AlphaVantage returned empty earnings calendar")
            return df

        # Normalize column names to match schema
        expected = ["symbol", "name", "reportDate", "fiscalDateEnding",
                     "estimate", "currency"]
        for col in expected:
            if col not in df.columns:
                df[col] = None

        # Convert estimate to float where possible
        df["estimate"] = pd.to_numeric(df["estimate"], errors="coerce")

        return df[expected]
