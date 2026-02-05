"""
Pipeline orchestrator.

Coordinates scraping, data validation, and BigQuery upserts.
Logs every run to the pipeline_runs table for monitoring.
"""

from __future__ import annotations

import logging
import time

import pandas as pd

from pipeline.bigquery import BigQueryClient
from pipeline.config import PipelineConfig
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when scraped data fails quality checks."""


def validate(df: pd.DataFrame, key_columns: list[str]) -> None:
    """Run data quality checks on a scraped DataFrame.

    Raises DataQualityError if any check fails.
    """
    if df.empty:
        raise DataQualityError("DataFrame is empty -- nothing to upsert")

    # Key columns must have no nulls
    for col in key_columns:
        if col not in df.columns:
            raise DataQualityError(f"Key column '{col}' missing from DataFrame")
        null_count = df[col].isna().sum()
        if null_count > 0:
            raise DataQualityError(
                f"Key column '{col}' has {null_count} null values"
            )

    # No duplicate keys
    dupes = df.duplicated(subset=key_columns, keep=False)
    dupe_count = dupes.sum()
    if dupe_count > 0:
        samples = df[dupes].head(3)[key_columns].to_dict("records")
        raise DataQualityError(
            f"{dupe_count} duplicate key rows detected. "
            f"Samples: {samples}"
        )


def run_scraper(
    scraper: BaseScraper,
    config: PipelineConfig | None = None,
) -> dict:
    """Execute a full scrape-validate-upsert cycle.

    Returns a summary dict with row counts and timing.
    """
    config = config or PipelineConfig.from_env()
    bq = BigQueryClient(config)
    table = scraper.table_name()
    start = time.monotonic()

    try:
        # Scrape
        logger.info("Running scraper: %s -> %s", scraper.__class__.__name__, table)
        df = scraper.run()

        if df.empty:
            elapsed = time.monotonic() - start
            summary = {
                "scraper": table,
                "status": "empty",
                "rows_scraped": 0,
                "rows_inserted": 0,
                "rows_updated": 0,
                "duration": elapsed,
            }
            bq.log_pipeline_run(
                scraper=table,
                status="empty",
                duration_seconds=elapsed,
            )
            logger.warning("Scraper %s returned 0 rows", table)
            return summary

        # Validate
        validate(df, scraper.key_columns())

        # Upsert
        stats = bq.upsert(table, df, scraper.key_columns())
        elapsed = time.monotonic() - start

        summary = {
            "scraper": table,
            "status": "success",
            "rows_scraped": len(df),
            "rows_inserted": stats.get("inserted", 0),
            "rows_updated": stats.get("updated", 0),
            "duration": elapsed,
        }

        bq.log_pipeline_run(
            scraper=table,
            status="success",
            rows_scraped=len(df),
            rows_inserted=stats.get("inserted", 0),
            rows_updated=stats.get("updated", 0),
            duration_seconds=elapsed,
        )

        logger.info(
            "Scraper %s complete: %d rows scraped, "
            "%d inserted, %d updated in %.2fs",
            table,
            len(df),
            stats.get("inserted", 0),
            stats.get("updated", 0),
            elapsed,
        )
        return summary

    except DataQualityError as e:
        elapsed = time.monotonic() - start
        logger.error("Data quality check failed for %s: %s", table, e)
        bq.log_pipeline_run(
            scraper=table,
            status="quality_error",
            duration_seconds=elapsed,
            error_message=str(e),
        )
        raise

    except Exception as e:
        elapsed = time.monotonic() - start
        logger.exception("Scraper %s failed", table)
        bq.log_pipeline_run(
            scraper=table,
            status="error",
            duration_seconds=elapsed,
            error_message=str(e),
        )
        raise
