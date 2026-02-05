"""
Abstract base class for all scrapers in the trading data pipeline.

Every scraper must inherit from BaseScraper and implement:
  - scrape() -> pd.DataFrame
  - key_columns() -> list[str]
  - table_name() -> str
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when a scraper encounters an unrecoverable error."""


class BaseScraper(ABC):
    """Abstract base class for trading data scrapers."""

    # Subclasses can override these for retry tuning
    MAX_RETRIES: int = 3
    BACKOFF_FACTOR: float = 1.0
    RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __init__(self) -> None:
        self._session: requests.Session | None = None
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}"
        )

    # ── Abstract interface ──────────────────────────────────────────

    @abstractmethod
    def scrape(self) -> pd.DataFrame:
        """Fetch data from the source and return a clean DataFrame.

        The returned DataFrame should contain only the columns relevant
        to the target BigQuery table. The orchestrator handles upserting.
        """

    @abstractmethod
    def key_columns(self) -> list[str]:
        """Return the columns that define a unique row (used for MERGE)."""

    @abstractmethod
    def table_name(self) -> str:
        """Return the target BigQuery table name (without dataset prefix)."""

    # ── Built-in helpers ────────────────────────────────────────────

    @property
    def session(self) -> requests.Session:
        """Lazily create a requests session with retry logic."""
        if self._session is None:
            self._session = requests.Session()
            retry = Retry(
                total=self.MAX_RETRIES,
                backoff_factor=self.BACKOFF_FACTOR,
                status_forcelist=list(self.RETRY_STATUS_CODES),
                allowed_methods=["GET", "POST"],
            )
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        return self._session

    def inject_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add _scraped_at timestamp column to the DataFrame."""
        df = df.copy()
        df["_scraped_at"] = datetime.now(timezone.utc)
        return df

    def run(self) -> pd.DataFrame:
        """Execute the scraper with logging and metadata injection.

        This is the method the orchestrator calls. It wraps scrape()
        with timing, logging, and metadata injection.
        """
        self.logger.info("Starting scrape for %s", self.table_name())
        start = time.monotonic()

        try:
            df = self.scrape()
        except Exception:
            self.logger.exception("Scrape failed for %s", self.table_name())
            raise

        if df.empty:
            self.logger.warning(
                "Scrape returned 0 rows for %s", self.table_name()
            )
            return df

        df = self.inject_metadata(df)
        elapsed = time.monotonic() - start
        self.logger.info(
            "Scrape complete for %s: %d rows in %.2fs",
            self.table_name(),
            len(df),
            elapsed,
        )
        return df
