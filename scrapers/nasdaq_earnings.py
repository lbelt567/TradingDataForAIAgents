"""
NASDAQ Earnings Calendar scraper.

Fetches earnings announcements from the NASDAQ API for a configurable
date range.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

NASDAQ_API_URL = "https://api.nasdaq.com/api/calendar/earnings"

# NASDAQ requires a browser-like User-Agent or it returns 403
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class NasdaqEarningsScraper(BaseScraper):
    """Scrape NASDAQ earnings calendar."""

    def __init__(self, days_ahead: int = 7) -> None:
        super().__init__()
        self.days_ahead = days_ahead

    def table_name(self) -> str:
        return "nasdaq_earnings"

    def key_columns(self) -> list[str]:
        return ["Symbol", "Date"]

    def scrape(self) -> pd.DataFrame:
        today = datetime.now(timezone.utc).date()
        all_rows: list[dict] = []

        for offset in range(self.days_ahead):
            date = today + timedelta(days=offset)
            date_str = date.strftime("%Y-%m-%d")
            self.logger.info("Fetching NASDAQ earnings for %s", date_str)

            resp = self.session.get(
                NASDAQ_API_URL,
                params={"date": date_str},
                headers=_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()

            data = resp.json()
            rows = (
                data.get("data", {})
                .get("rows", [])
            )
            if rows is None:
                rows = []

            for row in rows:
                row["Date"] = date_str

            all_rows.extend(rows)

        if not all_rows:
            self.logger.warning("No NASDAQ earnings data found")
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)

        # Rename columns to match BigQuery schema (replace spaces)
        rename_map = {
            "symbol": "Symbol",
            "name": "Company_Name",
            "date": "Date",
            "epsForecast": "EPS_Forecast",
            "noOfEsts": "No_of_EPS_Est",
            "lastYearRptDt": "Last_Year_Report_Date",
            "lastYearEPS": "Last_Year_EPS",
            "marketCap": "Market_Cap",
            "fiscalQuarterEnding": "Fiscal_Quarter",
        }
        # Only rename columns that exist
        df = df.rename(
            columns={k: v for k, v in rename_map.items() if k in df.columns}
        )

        expected = [
            "Symbol", "Date", "Company_Name", "EPS_Forecast",
            "No_of_EPS_Est", "Last_Year_Report_Date", "Last_Year_EPS",
            "Market_Cap", "Fiscal_Quarter",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = None

        return df[expected]
