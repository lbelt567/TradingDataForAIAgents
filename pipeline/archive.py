"""
Optional GCS Parquet archive module.

Exports BigQuery tables to Parquet files on Google Cloud Storage
for cold archival and compliance purposes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pipeline.bigquery import BigQueryClient, TABLE_SCHEMAS
from pipeline.config import PipelineConfig

logger = logging.getLogger(__name__)

# Tables to archive (excludes pipeline_runs)
ARCHIVABLE_TABLES = [
    t for t in TABLE_SCHEMAS if t != "pipeline_runs"
]


def archive_table(
    table: str,
    config: PipelineConfig | None = None,
) -> str:
    """Export a single BigQuery table to Parquet on GCS.

    Returns the GCS URI of the exported file.
    """
    config = config or PipelineConfig.from_env()
    if not config.gcs_archive_bucket:
        raise ValueError(
            "GCS_ARCHIVE_BUCKET is not set. Cannot archive without a bucket."
        )

    bq = BigQueryClient(config)
    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y/%m/%d")
    timestamp = now.strftime("%Y%m%dT%H%M%S")

    gcs_uri = (
        f"gs://{config.gcs_archive_bucket}/"
        f"archive/{table}/{date_prefix}/{table}_{timestamp}.parquet"
    )

    logger.info("Archiving %s to %s", table, gcs_uri)
    bq.export_parquet(table, gcs_uri)
    logger.info("Archive complete: %s", gcs_uri)
    return gcs_uri


def archive_all(config: PipelineConfig | None = None) -> list[str]:
    """Export all data tables to Parquet on GCS.

    Returns a list of GCS URIs.
    """
    config = config or PipelineConfig.from_env()
    uris: list[str] = []
    for table in ARCHIVABLE_TABLES:
        try:
            uri = archive_table(table, config)
            uris.append(uri)
        except Exception:
            logger.exception("Failed to archive %s", table)
            continue
    return uris
