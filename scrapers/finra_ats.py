"""
FINRA ATS/OTC Transparency scraper.

Fetches weekly ATS (Alternative Trading System) and OTC trading
data from the FINRA Equity Weekly Summary API using OAuth2 auth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import holidays
import pandas as pd

from pipeline.config import PipelineConfig
from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

FINRA_TOKEN_URL = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
FINRA_ATS_URL = (
    "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
)
FINRA_OTC_NMS_URL = (
    "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
)


class FinraAtsScraper(BaseScraper):
    """Scrape FINRA ATS/OTC weekly summary data."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        super().__init__()
        self._config = config or PipelineConfig.from_env()
        self._token: str | None = None

    def table_name(self) -> str:
        return "ats_otc"

    def key_columns(self) -> list[str]:
        return ["issueSymbolIdentifier", "initialPublishedDate"]

    def _authenticate(self) -> str:
        """Get an OAuth2 bearer token from FINRA."""
        resp = self.session.post(
            FINRA_TOKEN_URL,
            params={"grant_type": "client_credentials"},
            auth=(
                self._config.finra_client_id,
                self._config.finra_client_secret,
            ),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ScraperError(
                f"FINRA OAuth2 did not return access_token: {data}"
            )
        return token

    def _get_last_business_day(self) -> str:
        """Get the most recent FINRA reporting date (previous business day)."""
        us_holidays = holidays.US()
        today = datetime.now(timezone.utc).date()
        day = today - timedelta(days=1)
        while day.weekday() >= 5 or day in us_holidays:
            day -= timedelta(days=1)
        return day.strftime("%Y-%m-%d")

    def scrape(self) -> pd.DataFrame:
        token = self._authenticate()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        report_date = self._get_last_business_day()
        self.logger.info("Fetching FINRA ATS data for week of %s", report_date)

        # The FINRA API uses POST with a JSON body for filtering
        payload = {
            "fields": [
                "issueSymbolIdentifier",
                "totalWeeklyShareQuantity",
                "totalWeeklyTradeCount",
                "lastUpdateDate",
                "initialPublishedDate",
            ],
            "limit": 5000,
            "offset": 0,
            "compareFilters": [
                {
                    "fieldName": "initialPublishedDate",
                    "fieldValue": report_date,
                    "compareType": "EQUAL",
                }
            ],
        }

        all_rows: list[dict] = []
        offset = 0

        while True:
            payload["offset"] = offset
            resp = self.session.post(
                FINRA_ATS_URL,
                json=payload,
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            all_rows.extend(data)
            if len(data) < 5000:
                break
            offset += 5000

        if not all_rows:
            self.logger.warning("No FINRA ATS data returned for %s", report_date)
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)

        expected = [
            "issueSymbolIdentifier",
            "initialPublishedDate",
            "totalWeeklyShareQuantity",
            "totalWeeklyTradeCount",
            "lastUpdateDate",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = None

        # Coerce numeric types
        df["totalWeeklyShareQuantity"] = pd.to_numeric(
            df["totalWeeklyShareQuantity"], errors="coerce"
        ).astype("Int64")
        df["totalWeeklyTradeCount"] = pd.to_numeric(
            df["totalWeeklyTradeCount"], errors="coerce"
        ).astype("Int64")

        return df[expected]
