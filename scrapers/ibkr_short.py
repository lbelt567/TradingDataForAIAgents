"""
Interactive Brokers Stock Loan (Short Borrow) scraper.

Fetches real-time short borrow fee rates, rebate rates, and share
availability via the IBKR Client Portal API (or TWS API).

This replaces the v1 FTP-based pipeline with a direct API approach.
The scraper connects to IBKR's Client Portal Web API which provides
stock loan availability data.

Note: Requires either:
  1. IBKR Client Portal Gateway running locally, or
  2. IB Gateway / TWS with API enabled

If neither is available, falls back to the IBKR FTP public shortable
shares list.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.parse
from datetime import datetime, timezone

import pandas as pd

from pipeline.config import PipelineConfig
from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

# IBKR Client Portal API (runs on localhost when Gateway is active)
IBKR_CP_BASE = "https://localhost:5000/v1/api"

# Public FTP shortable shares list (fallback)
IBKR_FTP_URL = (
    "https://www.interactivebrokers.com/en/index.php"
    "?f=46377&conf=am"  # Shortable shares download page
)
IBKR_SHORTABLE_URL = (
    "ftp://ftp3.interactivebrokers.com/usa-shortable.txt"
)


class IbkrShortScraper(BaseScraper):
    """Scrape IBKR stock loan / short borrow data."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        super().__init__()
        self._config = config or PipelineConfig.from_env()

    def table_name(self) -> str:
        return "stock_loan"

    def key_columns(self) -> list[str]:
        return ["SYM", "CURRENCY"]

    def scrape(self) -> pd.DataFrame:
        """Try Client Portal API first, fall back to FTP shortable list."""
        try:
            return self._scrape_client_portal()
        except Exception as e:
            self.logger.warning(
                "Client Portal API unavailable (%s), falling back to "
                "public shortable shares list",
                e,
            )
            return self._scrape_ftp_shortable()

    def _scrape_client_portal(self) -> pd.DataFrame:
        """Fetch stock loan data from IBKR Client Portal API."""
        host = self._config.ibkr_host
        port = self._config.ibkr_port
        base_url = f"https://{host}:{port}/v1/api"

        # Verify gateway is authenticated
        auth_url = f"{base_url}/iserver/auth/status"
        resp = self.session.get(auth_url, verify=False, timeout=10)
        resp.raise_for_status()
        auth_data = resp.json()
        if not auth_data.get("authenticated"):
            raise ScraperError("IBKR Client Portal is not authenticated")

        # Search for shortable shares - the /iserver/secdef/search endpoint
        # For a broad scan we query known high-short-interest symbols
        # In production, this list would come from a watchlist
        symbols = self._get_watchlist()
        all_rows: list[dict] = []

        for symbol in symbols:
            try:
                row = self._fetch_borrow_data(base_url, symbol)
                if row:
                    all_rows.append(row)
            except Exception:
                self.logger.debug(
                    "Could not fetch borrow data for %s", symbol
                )
                continue

        if not all_rows:
            raise ScraperError("No data fetched from Client Portal API")

        return pd.DataFrame(all_rows)

    def _fetch_borrow_data(
        self, base_url: str, symbol: str
    ) -> dict | None:
        """Fetch borrow data for a single symbol from Client Portal."""
        # Search for the contract
        search_url = f"{base_url}/iserver/secdef/search"
        resp = self.session.post(
            search_url,
            json={"symbol": symbol, "secType": "STK"},
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None

        conid = results[0].get("conid")
        if not conid:
            return None

        # Fetch shortable shares info
        shortable_url = (
            f"{base_url}/iserver/contract/{conid}/info-and-rules"
        )
        resp = self.session.get(
            shortable_url,
            params={"isBuy": "false"},
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        rules = data.get("rules", {})
        return {
            "SYM": symbol,
            "CURRENCY": data.get("currency", "USD"),
            "NAME": data.get("companyName", ""),
            "FEERATE": rules.get("borrowFee"),
            "REBATERATE": rules.get("rebateRate"),
            "AVAILABLE": rules.get("shortableShares"),
            "COUNTRY": data.get("countryCode", "US"),
            "TIMESTAMP": datetime.now(timezone.utc),
        }

    def _scrape_ftp_shortable(self) -> pd.DataFrame:
        """Fallback: parse the IBKR public shortable shares text file."""
        # The public file is a pipe-delimited text file
        url = (
            "https://www.interactivebrokers.com/en/index.php"
            "?f=46377&conf=am"
        )

        # Try to fetch the shortable shares list via HTTPS
        # The actual data URL uses a redirect from the IB website
        resp = self.session.get(url, timeout=60, allow_redirects=True)
        resp.raise_for_status()

        # Parse the shortable shares file
        # Format: #BOF|SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|
        rows: list[dict] = []
        for line in resp.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 9:
                continue
            try:
                rows.append({
                    "SYM": parts[0],
                    "CURRENCY": parts[1],
                    "NAME": parts[2],
                    "FEERATE": float(parts[6]) if parts[6] else None,
                    "REBATERATE": float(parts[5]) if parts[5] else None,
                    "AVAILABLE": int(parts[7]) if parts[7] else None,
                    "COUNTRY": "US",
                    "TIMESTAMP": datetime.now(timezone.utc),
                })
            except (ValueError, IndexError):
                continue

        if not rows:
            self.logger.warning("No shortable shares parsed from IBKR FTP")
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def _get_watchlist(self) -> list[str]:
        """Return list of symbols to query for borrow data.

        In production, this would be loaded from a config file or database.
        """
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
            "META", "NVDA", "GME", "AMC", "BBBY",
            "PLTR", "SOFI", "NIO", "RIVN", "LCID",
            "SPY", "QQQ", "IWM", "DIA", "ARKK",
        ]
