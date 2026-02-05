# TradingDataForAIAgents

Database-first trading data pipeline using **BigQuery** as the single source of truth. Scrapers perform upserts (MERGE), writing only changed rows. AI agents query BigQuery directly for 24/7 financial monitoring.

## Architecture

```
Data Sources                Pipeline              Storage            Consumers
─────────────              ────────              ───────            ─────────
AlphaVantage  ─┐                                BigQuery
NASDAQ API    ─┤                                  ├── stock_loan
Fed Reserve   ─┼──► Scrapers ──► Orchestrator ──► ├── earnings_calendar
SEC EDGAR     ─┤       │           │              ├── nasdaq_earnings
FINRA API     ─┤       │        Validate          ├── ats_otc        ──► AI Agents
IBKR TWS      ─┘    Retry +    + MERGE            ├── edgar_filings       (SQL)
                     Logging                      ├── fomc_meetings
                                                  └── pipeline_runs
```

## Project Structure

```
├── scrapers/
│   ├── base.py              # Abstract base scraper class
│   ├── alpha_earnings.py    # AlphaVantage earnings calendar
│   ├── nasdaq_earnings.py   # NASDAQ earnings calendar
│   ├── fomc.py              # Federal Reserve FOMC meetings
│   ├── edgar.py             # SEC EDGAR filings
│   ├── finra_ats.py         # FINRA ATS/OTC weekly data
│   └── ibkr_short.py        # IBKR stock loan / short borrow
├── pipeline/
│   ├── config.py            # Config from environment variables
│   ├── bigquery.py          # BigQuery client with MERGE upsert
│   ├── orchestrator.py      # Scrape → validate → upsert
│   ├── archive.py           # Optional GCS Parquet snapshots
│   └── __main__.py          # CLI entry point
├── tests/
│   ├── test_scrapers.py     # Scraper unit tests (mocked HTTP)
│   ├── test_bigquery.py     # BigQuery schema and client tests
│   └── test_data_quality.py # Data validation tests
├── .github/workflows/
│   ├── scheduled_scrapers.yml  # Cron-triggered scraper jobs
│   ├── realtime_ibkr.yml       # IBKR high-frequency worker
│   └── tests.yml               # Test suite on push/PR
├── requirements.txt
└── .env.example
```

## Setup

### 1. GCP Service Account

Create a service account with these roles:
- `BigQuery Data Editor`
- `BigQuery Job User`
- `Storage Object Admin` (only if using GCS archive)

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required:
- `GCP_PROJECT_ID` -- your GCP project
- `GCP_SA_KEY` -- path to service account JSON key, or the JSON content itself
- `ALPHA_API_KEY` -- AlphaVantage API key
- `FINRA_CLIENT_ID` / `FINRA_CLIENT_SECRET` -- FINRA OAuth2 credentials

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create BigQuery Tables

```bash
python -m pipeline setup
```

## Usage

### Run a single scraper

```bash
python -m pipeline run alpha_earnings
python -m pipeline run nasdaq_earnings
python -m pipeline run fomc
python -m pipeline run edgar
python -m pipeline run finra_ats
python -m pipeline run ibkr_short
```

### Run all scrapers

```bash
python -m pipeline run-all
```

### Check table info

```bash
python -m pipeline info stock_loan
```

### Archive to GCS

```bash
python -m pipeline archive              # all tables
python -m pipeline archive stock_loan   # single table
```

## Schedules

| Scraper | Frequency | Cron |
|---|---|---|
| alpha_earnings | Daily | `0 4 * * *` |
| nasdaq_earnings | Daily | `0 5 * * *` |
| fomc | Weekly (Monday) | `0 6 * * 1` |
| finra_ats | Weekly (Monday) | `0 18 * * 1` |
| edgar | Quarterly | `0 8 1 */3 *` |
| ibkr_short | Every 5 min | Cloud Scheduler / self-hosted |

## AI Agent Queries

Agents authenticate with the same service account and query BigQuery directly:

```sql
-- Fee rate spikes in the last hour
SELECT SYM, NAME, FEERATE, AVAILABLE, _last_updated
FROM trading_data.stock_loan
WHERE _last_updated > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
  AND FEERATE > 50
ORDER BY FEERATE DESC;

-- Earnings announcements tomorrow
SELECT Symbol, Company_Name, EPS_Forecast, Market_Cap
FROM trading_data.nasdaq_earnings
WHERE Date = CAST(DATE_ADD(CURRENT_DATE(), INTERVAL 1 DAY) AS STRING);

-- Pipeline health
SELECT scraper, status, rows_scraped, duration_seconds, timestamp
FROM trading_data.pipeline_runs
ORDER BY timestamp DESC
LIMIT 20;
```

## Tests

```bash
pytest tests/ -v
```
