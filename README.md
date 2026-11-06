# ShopSphere — E-Commerce Data Warehouse

ShopSphere is a fictional large-scale omnichannel retailer used as a data-engineering portfolio project. It combines:

- broad online retail (similar to Amazon / Flipkart)
- physical retail stores (similar to D-Mart)
- quick-commerce fulfillment (similar to Blinkit / Zepto)

This repository is **Project A** of a larger portfolio. The goal is to show a complete, production-style path from messy source files to an analytics-ready warehouse and dashboard.

## Architecture

CSV-based batch ingestion → Python ETL → PostgreSQL raw/staging layers → data-quality validation → transformation → dimensional data warehouse → analytics SQL → Power BI → pipeline monitoring.

**Flow:** source CSV → `raw` → validate → `staging` → transform → `warehouse` → `analytics`  
`monitoring` records pipeline runs and data-quality results.

## Current status

**Implemented**

- Project folder layout and synthetic source-data generator
- PostgreSQL schemas (`raw`, `staging`, `warehouse`, `analytics`, `monitoring`)
- Star-schema warehouse + analytics views
- Full batch ETL: extract → validate → reject → monitor → quality gate → stage → transform → warehouse load
- Idempotent dimension/fact upserts
- Focused pytest coverage for validation and transform math
- Power BI dashboard (`ShopSphere_Analytics.pbix`) with **Executive Overview** and **Sales Analytics** pages

**Not implemented yet**

- Pipeline scheduling (Airflow / similar)
- Docker

## Technology stack

- Python 3.10+
- pandas, numpy, Faker, python-dotenv
- PostgreSQL (local developer instance; `psql` client required)
- SQLAlchemy 2.x + psycopg (v3)
- pytest
- Power BI Desktop (for the committed `.pbix` dashboard)

## Project layout

```text
.env.example                 environment variable template (copy to .env)
requirements.txt             Python dependencies
ShopSphere_Analytics.pbix    Power BI dashboard
data/raw/                    source CSVs (generator output)
data/rejected/               rejected rows from validation
src/config.py                paths, sizes, quality threshold, DB settings
src/generate_data.py         synthetic source generator
src/database.py              SQLAlchemy engine + connection test
src/etl/                     extract, validate, rejects, transform, load, pipeline
sql/schemas.sql              schemas, raw, staging, monitoring tables
sql/warehouse.sql            star-schema dimensions and facts
sql/analytics.sql            BI views over warehouse facts
sql/README.md                SQL apply order and schema notes
tests/                       focused pytest suite
logs/                        generator and ETL logs
```

## PostgreSQL layers

- **raw** — landing zone; loose types; dirty rows allowed; no FKs
- **staging** — typed validated rows only
- **warehouse** — star schema (dimensions + facts)
- **analytics** — BI views over warehouse facts

**Grain of `fact_sales`:** one row = one product line within one customer order.  
**Grain of `fact_delivery`:** one row = one delivery event for one order.

Surrogate keys (`customer_key`, `product_key`, …) are warehouse-generated; business keys (`customer_id`, …) come from the source.

## ETL pipeline flow

```text
Extract CSVs
  → Load raw.*
  → Validate (record-level rules)
  → Write rejected rows to data/rejected/
  → Record data-quality results in monitoring.*
  → Quality gate (per-table score must be ≥ QUALITY_THRESHOLD, default 95%)
  → Load staging.* (valid rows only)
  → Transform (metrics, FX, dimension/fact frames)
  → Load warehouse dims + facts (upsert)
  → Mark pipeline run SUCCESS / FAILED
```

If the quality gate fails, **staging / transform / warehouse load are skipped**. Rejected records never enter warehouse facts.

Keep `QUALITY_THRESHOLD=95`. Do not lower the gate to force a load; for a clean demo, set `DIRTY_DATA_RATE=0`, regenerate source CSVs, and re-run ETL.

### Transformation responsibilities

- Normalize dates and numerics on validated rows
- Calculate line metrics in the **transaction currency**:
  - `gross_amount = quantity × unit_price`
  - `discount_amount = gross_amount × discount_percent / 100`
  - `net_amount = gross_amount − discount_amount`
  - `cost_amount = quantity × product unit_cost`
  - `profit_amount = net_amount − cost_amount`
- Join `exchange_rates` by currency + order date to compute historical INR equivalents
- Persist both original-currency amounts and `*_amount_inr` columns on `warehouse.fact_sales`
- Preserve original currency on warehouse fact amounts (`currency_key` = transaction currency)
- Do **not** copy `order_total` onto every order-item row
- Build `fact_delivery` separately at delivery grain

### Currency conversion approach

- FX rates come only from the `exchange_rates` source table (no hardcoded rate table in transform)
- Exact date match first; otherwise latest available rate for that currency on or before the order date
- ETL persists historical INR reporting measures on `warehouse.fact_sales` (`gross_amount_inr`, `discount_amount_inr`, `net_amount_inr`, `cost_amount_inr`, `profit_amount_inr`)
- Analytics views report INR by summing those persisted `*_amount_inr` columns
- `dim_currency.rate_to_inr` is refreshed from the latest exchange-rate row per currency as a **reference** rate only — it is not the historical conversion source used by analytics

### Warehouse loading responsibilities

- Upsert `dim_date`, `dim_customer`, `dim_product`, `dim_store`
- Refresh `dim_currency` reference rates from exchange rates
- Use seeded `dim_channel` / `dim_payment_method` (from `sql/warehouse.sql`)
- Upsert `fact_sales` on `source_order_item_id`
- Upsert `fact_delivery` on `delivery_id`

### Rejected-record strategy

Invalid rows are written under `data/rejected/` as `{table}_rejected.csv` with:

- `pipeline_run_id`, `source_table`, `record_identifier`
- `failed_rule`, `rejection_reason`, `original_record` (JSON)

They are also summarized in `monitoring.data_quality_results`.

### Idempotency approach

- Dimensions: `INSERT … ON CONFLICT (business_key) DO UPDATE`
- `fact_sales`: conflict on `source_order_item_id`
- `fact_delivery`: conflict on `delivery_id`
- Raw/staging tables are truncated and reloaded each successful pass through those stages
- A second successful run updates existing warehouse rows instead of blindly duplicating them

## Analytics views and Power BI

After a successful ETL run, query the views in schema `analytics` (see `sql/analytics.sql`):

| View | Purpose |
|---|---|
| `monthly_sales` | Monthly sales, orders, units, profit (INR) |
| `category_performance` | Sales by product category (INR) |
| `product_performance` | Sales by product (INR) |
| `store_performance` | Sales by store / fulfillment location (INR) |
| `channel_performance` | Sales by sales channel (INR) |
| `customer_performance` | Sales by customer (INR) |
| `delivery_performance` | Delivery counts and averages by type, status, channel group |

The committed dashboard `ShopSphere_Analytics.pbix` has two pages:

- **Executive Overview** — high-level KPIs and trends from analytics views such as `monthly_sales`, `category_performance`, and `channel_performance`
- **Sales Analytics** — deeper sales breakdowns using views such as `monthly_sales`, `category_performance`, and `product_performance`

Open the `.pbix` in Power BI Desktop and point the data source at your local `shopsphere` PostgreSQL database (credentials stay in your local Power BI / `.env` setup — never commit secrets).

## Prerequisites

- Python 3.10+
- PostgreSQL server with a local database you can create and connect to
- `psql` on your PATH (or invoke `psql` with its full install path)
- Power BI Desktop if you want to open `ShopSphere_Analytics.pbix`

## First-run checklist

1. **Environment** — create a venv, install dependencies, copy `.env.example` to `.env`, set `POSTGRES_PASSWORD`.
2. **Database** — create the `shopsphere` database.
3. **SQL init** — apply `sql/schemas.sql`, then `sql/warehouse.sql`, then `sql/analytics.sql` (connected to `shopsphere`).
4. **Connection test** — `python -m src.database`.
5. **Generate data** — `python src/generate_data.py` (use `DIRTY_DATA_RATE=0` for a clean demo load).
6. **Run ETL** — `python -m src.etl` (quality gate remains 95%).
7. **Verify analytics** — query `analytics.monthly_sales` (or open `ShopSphere_Analytics.pbix`).

## Setup

```powershell
cd E:\Projects\ecommerce-data-warehouse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set your real `POSTGRES_PASSWORD`. Ensure `psql` is on PATH, then create the database and apply SQL once:

```powershell
psql -U postgres -d postgres -c "CREATE DATABASE shopsphere;"
psql -U postgres -d shopsphere -f sql/schemas.sql
psql -U postgres -d shopsphere -f sql/warehouse.sql
psql -U postgres -d shopsphere -f sql/analytics.sql
```

If `psql` is not on PATH, call it with the full path to `psql.exe` on your machine (same `-U` / `-d` / `-f` arguments). You will be prompted for the Postgres password unless you use a local credential helper such as `.pgpass`.

For older databases that pre-date the historical INR columns, re-apply `sql/warehouse.sql` (safe `ADD COLUMN IF NOT EXISTS` upgrades) and then `sql/analytics.sql`. Details are in `sql/README.md`.

## Run the data generator

```powershell
python src/generate_data.py
```

Development defaults keep the extract small. Intentional dirty rows (~2–3%) will often push **dependent** tables (orders, items, payments, deliveries) below the 95% quality gate because of orphan cascades. For a clean end-to-end warehouse load demo, set `DIRTY_DATA_RATE=0` in `.env`, regenerate, then run ETL — **without changing the 95% gate**.

## Run the ETL

```powershell
python -m src.database
python -m src.etl
```

## Run tests

```powershell
python -m pytest tests/ -v
```

## Connection test

```powershell
python -m src.database
```

Successful output includes `Connection successful.` and the PostgreSQL version string.
