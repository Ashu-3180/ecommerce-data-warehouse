# ShopSphere — E-Commerce Data Warehouse

ShopSphere is a fictional large-scale omnichannel retailer used as a data-engineering portfolio project. It combines:

- broad online retail (similar to Amazon / Flipkart)
- physical retail stores (similar to D-Mart)
- quick-commerce fulfillment (similar to Blinkit / Zepto)

This repository is **Project A** of a larger portfolio. The goal is to show a complete, production-style path from messy source files to an analytics-ready warehouse and dashboard.

## Planned architecture

CSV-based batch ingestion → Python ETL → PostgreSQL raw/staging layers → data-quality validation → transformation → dimensional data warehouse → analytics SQL → Power BI → pipeline monitoring.

## Current status

**Implemented**

- Project folder layout and synthetic source-data generator
- PostgreSQL schemas (`raw`, `staging`, `warehouse`, `analytics`, `monitoring`)
- Star-schema warehouse + analytics views
- Full batch ETL: extract → validate → reject → monitor → quality gate → stage → transform → warehouse load
- Idempotent dimension/fact upserts
- Focused pytest coverage for validation and transform math

**Not implemented yet**

- Power BI dashboard
- Pipeline scheduling (Airflow / similar)
- Docker

## Technology stack

- Python 3.10+
- pandas, numpy, Faker, python-dotenv
- PostgreSQL 18
- SQLAlchemy 2.x + psycopg (v3)
- pytest

## Project layout

```text
data/raw/              source CSVs (generator output)
data/rejected/         rejected rows from validation
src/config.py          paths, sizes, quality threshold, DB settings
src/generate_data.py   synthetic source generator
src/database.py        SQLAlchemy engine + connection test
src/etl/               extract, validate, rejects, transform, load, pipeline
sql/                   schemas, warehouse, analytics
tests/                 focused pytest suite
logs/                  generator and ETL logs
```

## PostgreSQL architecture

**source CSV → `raw` → validate → `staging` → transform → `warehouse` → `analytics`**

`monitoring` records pipeline runs and data-quality results.

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

### Transformation responsibilities

- Normalize dates and numerics on validated rows
- Calculate line metrics in the **transaction currency**:
  - `gross_amount = quantity × unit_price`
  - `discount_amount = gross_amount × discount_percent / 100`
  - `net_amount = gross_amount − discount_amount`
  - `cost_amount = quantity × product unit_cost`
  - `profit_amount = net_amount − cost_amount`
- Join `exchange_rates` by currency + order date to compute INR equivalents for reporting/tests
- Preserve original currency on warehouse fact amounts (`currency_key` = transaction currency)
- Do **not** copy `order_total` onto every order-item row
- Build `fact_delivery` separately at delivery grain

### Currency conversion approach

- FX rates come only from the `exchange_rates` source table (no hardcoded rate table in transform)
- Exact date match first; otherwise latest available rate for that currency
- `dim_currency.rate_to_inr` is refreshed from the latest exchange-rate row per code so analytics views can report in INR
- Warehouse `fact_sales` stores **original-currency** amounts; analytics multiplies by `dim_currency.rate_to_inr`

### Warehouse loading responsibilities

- Upsert `dim_date`, `dim_customer`, `dim_product`, `dim_store`
- Refresh `dim_currency` rates from exchange rates
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

## Setup

```powershell
cd E:\Projects\ecommerce-data-warehouse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set your real `POSTGRES_PASSWORD`. Apply SQL once:

```powershell
psql -U postgres -d postgres -c "CREATE DATABASE shopsphere;"
psql -U postgres -d shopsphere -f sql/schemas.sql
psql -U postgres -d shopsphere -f sql/warehouse.sql
psql -U postgres -d shopsphere -f sql/analytics.sql
```

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
