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

- Project folder layout
- Environment-based configuration
- Deterministic synthetic source-data generator
- Intentional (small) data-quality issues in the raw CSVs
- PostgreSQL schemas, raw/staging tables, star-schema warehouse, analytics views
- SQLAlchemy connection helper (`src/database.py`)

**Not implemented yet**

- ETL jobs (`extract`, `validate`, `transform`, `load`)
- Loading CSVs into PostgreSQL
- Data-quality validation logic
- Power BI dashboard
- Pipeline scheduling
- Docker

## Technology stack (this stage)

- Python 3.10+
- pandas, numpy, Faker, python-dotenv
- PostgreSQL 18
- SQLAlchemy 2.x + psycopg (v3)

Power BI, Airflow, and Docker will be added in later stages.

## Project layout

```text
data/raw/          generated source CSVs
data/rejected/     reserved for future rejected-record output
src/config.py      paths, dataset sizes, dates, random seed, database settings
src/generate_data.py
src/database.py    SQLAlchemy engine and connection test
sql/schemas.sql    schemas, raw, staging, monitoring
sql/warehouse.sql  star schema (dimensions and facts)
sql/analytics.sql  BI views
tests/             reserved for future tests
logs/              generator and (later) ETL logs
```

## PostgreSQL architecture

Data is intended to move through layers:

**source CSV → `raw` schema → `staging` schema → validation → `warehouse` schema → `analytics` views**

`monitoring` sits beside the pipeline and records run status and data-quality results. It is not part of the sales star schema.

**Why raw and staging are separated.**  
`raw` is a landing zone. It keeps source-oriented columns, uses loose types, and has no foreign keys, so intentionally dirty CSV rows can still be loaded. `staging` is the typed, cleaned copy (dates as `DATE`, prices as `NUMERIC`, and so on) plus placeholder columns such as `_is_valid` for the future validation step. Keeping them apart means a bad source extract does not overwrite the cleaned layer, and you can always re-read what the source actually sent.

**Why the warehouse uses a star schema.**  
A star schema puts measurable events in **fact** tables and descriptive attributes in **dimension** tables. Facts stay narrow and numeric; dimensions hold the labels used to slice reports (customer, product, store, date). That shape is easy for SQL and Power BI: join a fact to the dimensions you need, then `SUM` / `COUNT`.

**What a fact table is.**  
A fact table stores events at a declared **grain** (what one row means) plus foreign keys to dimensions and additive measures (quantity, amounts, fees).

**What a dimension table is.**  
A dimension table stores the “who / what / where / when” attributes. Examples: `dim_customer`, `dim_product`, `dim_date`.

**Why surrogate keys are used.**  
`customer_key` / `product_key` (and similar) are warehouse-generated integers. `customer_id` is the source business key. Surrogate keys keep facts stable if a source ID is reused or a type-2 history is added later, and they make fact-table joins compact.

**Grain of `fact_sales`.**  
One row = one product line within one customer order. There is no separate fact row for the order header. Order-level attributes (channel, customer, status) are repeated on each line.

**Grain of `fact_delivery`.**  
One row = one delivery event for one order. In-store walk-out purchases often have no delivery row.

Apply SQL in this order after you create the database: `sql/schemas.sql`, then `sql/warehouse.sql`, then `sql/analytics.sql`. See `sql/README.md`.

Test the database login (after you have a local `.env` with a real password):

```powershell
pip install -r requirements.txt
python -m src.database
```

## Setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

On macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to change dataset size. Development defaults are small (500 customers, 200 products, 30 stores, 1,000 orders) so generation is fast. Final-scale quantities are documented in `src/config.py` as `TARGET_*` constants and in `.env.example` as comments.

## Run the data generator

```powershell
python src/generate_data.py
```

Equivalent:

```powershell
python -m src.generate_data
```

Output files are written to `data/raw/`:

- `customers.csv`
- `products.csv`
- `stores.csv`
- `orders.csv`
- `order_items.csv`
- `payments.csv`
- `deliveries.csv`
- `exchange_rates.csv`

Most rows are valid and relationally consistent. About 2–3% of records (configurable via `DIRTY_DATA_RATE`) contain realistic source-system problems such as missing emails, orphan foreign keys, invalid quantities, or messy category text. Those issues are intentional and will be handled by a later validation layer. Do not load them into `warehouse` tables until that ETL exists.
