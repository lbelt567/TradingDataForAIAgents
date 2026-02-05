"""
CLI entry point for the trading data pipeline.

Usage:
    python -m pipeline run <scraper_name>
    python -m pipeline run-all
    python -m pipeline setup
    python -m pipeline archive [table]
    python -m pipeline info <table>
"""

from __future__ import annotations

import argparse
import logging
import sys

from pipeline.config import PipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")


def cmd_run(args: argparse.Namespace) -> None:
    """Run a single scraper."""
    from scrapers import SCRAPERS
    from pipeline.orchestrator import run_scraper

    name = args.scraper
    if name not in SCRAPERS:
        logger.error(
            "Unknown scraper '%s'. Available: %s",
            name,
            ", ".join(SCRAPERS.keys()),
        )
        sys.exit(1)

    config = PipelineConfig.from_env()
    scraper_cls = SCRAPERS[name]

    # Some scrapers accept a config argument
    try:
        scraper = scraper_cls(config=config)
    except TypeError:
        scraper = scraper_cls()

    summary = run_scraper(scraper, config)
    logger.info("Run summary: %s", summary)


def cmd_run_all(args: argparse.Namespace) -> None:
    """Run all scrapers sequentially."""
    from scrapers import SCRAPERS
    from pipeline.orchestrator import run_scraper

    config = PipelineConfig.from_env()
    results = []

    for name, scraper_cls in SCRAPERS.items():
        logger.info("=" * 60)
        logger.info("Running scraper: %s", name)
        try:
            try:
                scraper = scraper_cls(config=config)
            except TypeError:
                scraper = scraper_cls()
            summary = run_scraper(scraper, config)
            results.append(summary)
        except Exception:
            logger.exception("Scraper %s failed, continuing", name)
            results.append({"scraper": name, "status": "error"})

    logger.info("=" * 60)
    logger.info("All scrapers complete. Results:")
    for r in results:
        logger.info("  %s", r)


def cmd_setup(args: argparse.Namespace) -> None:
    """Create BigQuery dataset and all tables."""
    from pipeline.bigquery import BigQueryClient

    config = PipelineConfig.from_env()
    bq = BigQueryClient(config)
    bq.ensure_all_tables()
    logger.info("Setup complete. All tables created.")


def cmd_archive(args: argparse.Namespace) -> None:
    """Archive tables to GCS Parquet."""
    from pipeline.archive import archive_all, archive_table

    config = PipelineConfig.from_env()

    if args.table:
        uri = archive_table(args.table, config)
        logger.info("Archived: %s", uri)
    else:
        uris = archive_all(config)
        logger.info("Archived %d tables:", len(uris))
        for uri in uris:
            logger.info("  %s", uri)


def cmd_info(args: argparse.Namespace) -> None:
    """Show table info."""
    from pipeline.bigquery import BigQueryClient

    config = PipelineConfig.from_env()
    bq = BigQueryClient(config)
    info = bq.table_info(args.table)
    logger.info("Table: %s", args.table)
    logger.info("  Rows: %s", info["num_rows"])
    logger.info("  Modified: %s", info["modified"])
    logger.info("  Schema:")
    for field in info["schema"]:
        logger.info(
            "    %s (%s, %s)", field["name"], field["type"], field["mode"]
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Trading Data Pipeline v2",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Run a single scraper")
    p_run.add_argument("scraper", help="Scraper name (e.g. alpha_earnings)")
    p_run.set_defaults(func=cmd_run)

    # run-all
    p_all = subparsers.add_parser("run-all", help="Run all scrapers")
    p_all.set_defaults(func=cmd_run_all)

    # setup
    p_setup = subparsers.add_parser(
        "setup", help="Create BigQuery dataset and tables"
    )
    p_setup.set_defaults(func=cmd_setup)

    # archive
    p_archive = subparsers.add_parser(
        "archive", help="Archive tables to GCS Parquet"
    )
    p_archive.add_argument(
        "table", nargs="?", default=None, help="Table to archive (all if omitted)"
    )
    p_archive.set_defaults(func=cmd_archive)

    # info
    p_info = subparsers.add_parser("info", help="Show table info")
    p_info.add_argument("table", help="Table name")
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
