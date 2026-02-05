"""
BigQuery client wrapper providing upsert (MERGE) semantics.

Core workflow:
  1. Load a DataFrame into a temporary staging table.
  2. MERGE staging into the target table on key columns.
  3. Update rows where non-key columns differ.
  4. Insert rows that don't exist.
  5. Set _last_updated on every touched row.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

from pipeline.config import PipelineConfig

logger = logging.getLogger(__name__)

# ── Table schemas ───────────────────────────────────────────────────

TABLE_SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "stock_loan": [
        bigquery.SchemaField("SYM", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("CURRENCY", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("NAME", "STRING"),
        bigquery.SchemaField("FEERATE", "FLOAT64"),
        bigquery.SchemaField("REBATERATE", "FLOAT64"),
        bigquery.SchemaField("AVAILABLE", "INT64"),
        bigquery.SchemaField("COUNTRY", "STRING"),
        bigquery.SchemaField("TIMESTAMP", "TIMESTAMP"),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "earnings_calendar": [
        bigquery.SchemaField("symbol", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("reportDate", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("fiscalDateEnding", "STRING"),
        bigquery.SchemaField("estimate", "FLOAT64"),
        bigquery.SchemaField("currency", "STRING"),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "nasdaq_earnings": [
        bigquery.SchemaField("Symbol", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Date", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Company_Name", "STRING"),
        bigquery.SchemaField("EPS_Forecast", "STRING"),
        bigquery.SchemaField("No_of_EPS_Est", "STRING"),
        bigquery.SchemaField("Last_Year_Report_Date", "STRING"),
        bigquery.SchemaField("Last_Year_EPS", "STRING"),
        bigquery.SchemaField("Market_Cap", "STRING"),
        bigquery.SchemaField("Fiscal_Quarter", "STRING"),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "ats_otc": [
        bigquery.SchemaField(
            "issueSymbolIdentifier", "STRING", mode="REQUIRED"
        ),
        bigquery.SchemaField(
            "initialPublishedDate", "STRING", mode="REQUIRED"
        ),
        bigquery.SchemaField("totalWeeklyShareQuantity", "INT64"),
        bigquery.SchemaField("totalWeeklyTradeCount", "INT64"),
        bigquery.SchemaField("lastUpdateDate", "STRING"),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "edgar_filings": [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("accessionNumber", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("filingType", "STRING"),
        bigquery.SchemaField("filedAt", "STRING"),
        bigquery.SchemaField("filing_link", "STRING"),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "fomc_meetings": [
        bigquery.SchemaField("Year", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Month", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Meeting_Dates", "STRING", mode="REQUIRED"),
        bigquery.SchemaField(
            "Summary_of_Economic_Projections", "STRING"
        ),
        bigquery.SchemaField("_scraped_at", "TIMESTAMP"),
        bigquery.SchemaField("_last_updated", "TIMESTAMP"),
    ],
    "pipeline_runs": [
        bigquery.SchemaField("scraper", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("rows_scraped", "INT64"),
        bigquery.SchemaField("rows_inserted", "INT64"),
        bigquery.SchemaField("rows_updated", "INT64"),
        bigquery.SchemaField("duration_seconds", "FLOAT64"),
        bigquery.SchemaField("error_message", "STRING"),
        bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
    ],
}


class BigQueryClient:
    """Thin wrapper around the BigQuery Python client with MERGE logic."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.project = config.gcp_project_id
        self.dataset = config.bq_dataset
        credentials = service_account.Credentials.from_service_account_info(
            config.sa_credentials_info
        )
        self.client = bigquery.Client(
            project=self.project, credentials=credentials
        )

    # ── Public helpers ──────────────────────────────────────────────

    @property
    def dataset_ref(self) -> str:
        return f"{self.project}.{self.dataset}"

    def full_table_id(self, table: str) -> str:
        return f"{self.dataset_ref}.{table}"

    # ── Dataset / table provisioning ────────────────────────────────

    def ensure_dataset(self) -> None:
        """Create the dataset if it doesn't exist."""
        ds = bigquery.Dataset(self.dataset_ref)
        ds.location = "US"
        self.client.create_dataset(ds, exists_ok=True)
        logger.info("Dataset %s ready", self.dataset_ref)

    def ensure_table(self, table: str) -> None:
        """Create a table if it doesn't exist, using the predefined schema."""
        schema = TABLE_SCHEMAS.get(table)
        if schema is None:
            raise ValueError(
                f"No schema defined for table '{table}'. "
                f"Known tables: {list(TABLE_SCHEMAS.keys())}"
            )
        table_ref = bigquery.Table(self.full_table_id(table), schema=schema)
        self.client.create_table(table_ref, exists_ok=True)
        logger.info("Table %s ready", self.full_table_id(table))

    def ensure_all_tables(self) -> None:
        """Create the dataset and all tables."""
        self.ensure_dataset()
        for table in TABLE_SCHEMAS:
            self.ensure_table(table)

    # ── Core MERGE (upsert) ─────────────────────────────────────────

    def upsert(
        self,
        table: str,
        df: pd.DataFrame,
        key_columns: list[str],
    ) -> dict:
        """Upsert a DataFrame into a BigQuery table using MERGE.

        Returns a dict with keys: inserted, updated, unchanged.
        """
        if df.empty:
            logger.warning("Empty DataFrame, skipping upsert for %s", table)
            return {"inserted": 0, "updated": 0, "unchanged": 0}

        self.ensure_dataset()
        self.ensure_table(table)

        target = self.full_table_id(table)
        staging = f"{target}_staging_{uuid.uuid4().hex[:8]}"

        # Load DataFrame into staging table
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        load_job = self.client.load_table_from_dataframe(
            df, staging, job_config=job_config
        )
        load_job.result()  # wait for completion
        logger.info("Loaded %d rows into staging table %s", len(df), staging)

        # Build MERGE statement
        all_columns = [col for col in df.columns if col != "_last_updated"]
        non_key_columns = [c for c in all_columns if c not in key_columns]

        join_clause = " AND ".join(
            f"T.`{k}` = S.`{k}`" for k in key_columns
        )
        update_set = ", ".join(
            [f"T.`{c}` = S.`{c}`" for c in non_key_columns]
            + ["T.`_last_updated` = CURRENT_TIMESTAMP()"]
        )
        insert_cols = ", ".join(f"`{c}`" for c in all_columns) + ", `_last_updated`"
        insert_vals = ", ".join(f"S.`{c}`" for c in all_columns) + ", CURRENT_TIMESTAMP()"

        # Build a condition to only update when something actually changed
        update_condition_parts = [
            f"T.`{c}` IS DISTINCT FROM S.`{c}`" for c in non_key_columns
        ]
        update_condition = " OR ".join(update_condition_parts) if update_condition_parts else "FALSE"

        merge_sql = f"""
        MERGE `{target}` T
        USING `{staging}` S
        ON {join_clause}
        WHEN MATCHED AND ({update_condition}) THEN
            UPDATE SET {update_set}
        WHEN NOT MATCHED THEN
            INSERT ({insert_cols})
            VALUES ({insert_vals})
        """

        logger.debug("MERGE SQL:\n%s", merge_sql)
        result = self.client.query(merge_sql).result()

        # Get DML stats
        stats = {"inserted": 0, "updated": 0, "unchanged": 0}
        if hasattr(result, "num_dml_affected_rows"):
            stats["inserted"] = result.num_dml_affected_rows or 0

        # Clean up staging table
        self.client.delete_table(staging, not_found_ok=True)
        logger.info(
            "MERGE complete for %s: %s",
            table,
            stats,
        )
        return stats

    # ── Query ───────────────────────────────────────────────────────

    def query(self, sql: str) -> pd.DataFrame:
        """Run a SQL query and return results as a DataFrame."""
        return self.client.query(sql).to_dataframe()

    # ── Table info ──────────────────────────────────────────────────

    def table_info(self, table: str) -> dict:
        """Return row count, last updated time, and schema for a table."""
        full_id = self.full_table_id(table)
        tbl = self.client.get_table(full_id)
        return {
            "num_rows": tbl.num_rows,
            "modified": tbl.modified,
            "schema": [
                {"name": f.name, "type": f.field_type, "mode": f.mode}
                for f in tbl.schema
            ],
        }

    # ── Export to Parquet on GCS ─────────────────────────────────────

    def export_parquet(self, table: str, gcs_uri: str) -> None:
        """Export a table to a Parquet file on GCS."""
        full_id = self.full_table_id(table)
        job_config = bigquery.ExtractJobConfig(
            destination_format=bigquery.DestinationFormat.PARQUET
        )
        extract_job = self.client.extract_table(
            full_id, gcs_uri, job_config=job_config
        )
        extract_job.result()
        logger.info("Exported %s to %s", full_id, gcs_uri)

    # ── Pipeline run logging ────────────────────────────────────────

    def log_pipeline_run(
        self,
        scraper: str,
        status: str,
        rows_scraped: int = 0,
        rows_inserted: int = 0,
        rows_updated: int = 0,
        duration_seconds: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        """Insert a row into the pipeline_runs table."""
        self.ensure_table("pipeline_runs")
        row = {
            "scraper": scraper,
            "status": status,
            "rows_scraped": rows_scraped,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "duration_seconds": round(duration_seconds, 3),
            "error_message": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        table_ref = self.full_table_id("pipeline_runs")
        errors = self.client.insert_rows_json(table_ref, [row])
        if errors:
            logger.error("Failed to log pipeline run: %s", errors)
