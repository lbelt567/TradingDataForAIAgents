"""
SEC EDGAR Filings scraper.

Fetches recent filings for a watchlist of tickers using the
SEC EDGAR full-text search API.
"""

from __future__ import annotations

import logging

import pandas as pd

from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_SEARCH_API = "https://efts.sec.gov/LATEST/search-index"

# SEC requires a descriptive User-Agent with contact info
SEC_HEADERS = {
    "User-Agent": "TradingDataPipeline/2.0 (contact@example.com)",
    "Accept": "application/json",
}

# Default watchlist -- can be overridden
DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "META", "NVDA", "JPM", "V", "JNJ",
]

# Filing types of interest
FILING_TYPES = ["10-K", "10-Q", "8-K", "DEF 14A", "13F-HR"]


class EdgarScraper(BaseScraper):
    """Scrape SEC EDGAR filings for a list of tickers."""

    def __init__(
        self,
        tickers: list[str] | None = None,
        filing_types: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.tickers = tickers or DEFAULT_TICKERS
        self.filing_types = filing_types or FILING_TYPES

    def table_name(self) -> str:
        return "edgar_filings"

    def key_columns(self) -> list[str]:
        return ["ticker", "accessionNumber"]

    def scrape(self) -> pd.DataFrame:
        all_filings: list[dict] = []

        for ticker in self.tickers:
            self.logger.info("Fetching EDGAR filings for %s", ticker)
            try:
                filings = self._fetch_filings(ticker)
                all_filings.extend(filings)
            except Exception:
                self.logger.exception(
                    "Failed to fetch filings for %s", ticker
                )
                continue

        if not all_filings:
            self.logger.warning("No EDGAR filings found")
            return pd.DataFrame()

        df = pd.DataFrame(all_filings)
        expected = [
            "ticker", "accessionNumber", "filingType", "filedAt",
            "filing_link",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = None
        return df[expected]

    def _fetch_filings(self, ticker: str) -> list[dict]:
        """Fetch recent filings for a single ticker via EDGAR full-text search."""
        url = "https://efts.sec.gov/LATEST/search-index"
        filings = []

        # Use the EDGAR full-text search API
        search_url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f"\"{ticker}\"",
            "dateRange": "custom",
            "startdt": "2024-01-01",
            "enddt": "2026-12-31",
            "forms": ",".join(self.filing_types),
        }

        # Try the EDGAR company search endpoint (more reliable)
        company_url = (
            f"https://data.sec.gov/submissions/"
        )
        # First, resolve ticker to CIK via company tickers file
        cik = self._resolve_cik(ticker)
        if cik is None:
            self.logger.warning("Could not resolve CIK for %s", ticker)
            return []

        submissions_url = (
            f"https://data.sec.gov/submissions/CIK{cik}.json"
        )
        resp = self.session.get(
            submissions_url, headers=SEC_HEADERS, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form not in self.filing_types:
                continue

            accession = accessions[i] if i < len(accessions) else ""
            filed_at = dates[i] if i < len(dates) else ""
            doc = primary_docs[i] if i < len(primary_docs) else ""

            accession_path = accession.replace("-", "")
            link = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik}/{accession_path}/{doc}"
            )

            filings.append({
                "ticker": ticker,
                "accessionNumber": accession,
                "filingType": form,
                "filedAt": filed_at,
                "filing_link": link,
            })

        return filings

    def _resolve_cik(self, ticker: str) -> str | None:
        """Resolve a ticker symbol to a CIK number."""
        url = "https://www.sec.gov/files/company_tickers.json"
        resp = self.session.get(url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                return cik
        return None
