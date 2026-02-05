"""
Federal Reserve FOMC Meetings scraper.

Scrapes the Federal Reserve website for FOMC meeting dates and
whether the Summary of Economic Projections (SEP) was released.
"""

from __future__ import annotations

import logging
import re

import pandas as pd
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


class FOMCScraper(BaseScraper):
    """Scrape FOMC meeting calendar from the Federal Reserve website."""

    def table_name(self) -> str:
        return "fomc_meetings"

    def key_columns(self) -> list[str]:
        return ["Year", "Month", "Meeting_Dates"]

    def scrape(self) -> pd.DataFrame:
        resp = self.session.get(FOMC_URL, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        meetings: list[dict] = []

        # Parse each panel (year) on the FOMC calendar page
        panels = soup.find_all("div", class_="panel")
        if not panels:
            panels = soup.find_all("div", class_="panel-default")

        for panel in panels:
            # Extract year from panel heading
            heading = panel.find(
                "div", class_="panel-heading"
            ) or panel.find("h4")
            if heading is None:
                continue

            year_match = re.search(r"20\d{2}", heading.get_text())
            if year_match is None:
                continue
            year = year_match.group()

            # Each row in the panel body is a meeting
            rows = panel.find_all("div", class_="fomc-meeting")
            if not rows:
                rows = panel.find_all("div", class_="row")

            for row in rows:
                month_el = row.find("div", class_="fomc-meeting__month")
                date_el = row.find("div", class_="fomc-meeting__date")
                sep_el = row.find("div", class_="fomc-meeting__sep")

                if month_el is None or date_el is None:
                    continue

                month = month_el.get_text(strip=True)
                dates = date_el.get_text(strip=True)

                # SEP: check for asterisk or explicit text
                sep_text = ""
                if sep_el:
                    sep_text = sep_el.get_text(strip=True)
                has_sep = "*" in dates or "projection" in sep_text.lower()

                meetings.append({
                    "Year": year,
                    "Month": month,
                    "Meeting_Dates": dates.replace("*", "").strip(),
                    "Summary_of_Economic_Projections": (
                        "Yes" if has_sep else "No"
                    ),
                })

        if not meetings:
            # Fallback: try a simpler table-based parse
            meetings = self._fallback_parse(soup)

        if not meetings:
            self.logger.warning("No FOMC meetings parsed from page")
            return pd.DataFrame()

        return pd.DataFrame(meetings)

    def _fallback_parse(self, soup: BeautifulSoup) -> list[dict]:
        """Fallback parser for alternative page layouts."""
        meetings = []
        # Try to find any table-like structure
        for row in soup.select(".fomc-meeting, .panel-body .row"):
            text = row.get_text(" ", strip=True)
            # Try to extract year/month/dates from text
            year_match = re.search(r"(20\d{2})", text)
            month_match = re.search(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)",
                text,
            )
            date_match = re.search(r"(\d{1,2}(?:-\d{1,2})?)", text)
            if year_match and month_match and date_match:
                meetings.append({
                    "Year": year_match.group(1),
                    "Month": month_match.group(1),
                    "Meeting_Dates": date_match.group(1),
                    "Summary_of_Economic_Projections": (
                        "Yes" if "*" in text else "No"
                    ),
                })
        return meetings
