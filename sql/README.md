# ShopSphere SQL

PostgreSQL objects for the ShopSphere data warehouse. Scripts are idempotent (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING` / `CREATE OR REPLACE VIEW` / `ADD COLUMN IF NOT EXISTS`) and do **not** drop databases, schemas, or data.

## Prerequisites

- A running PostgreSQL server
- The `psql` client available on your PATH (or invoke `psql` with its full install path)
- A database named `shopsphere` (create it once before applying these scripts)

Do not run the SQL files against the `postgres` maintenance database. Connect to `shopsphere`.

## Initialization order

1. Create the database once (PostgreSQL superuser / admin):

   ```sql
   CREATE DATABASE shopsphere;
   ```

2. `schemas.sql` — schemas plus `raw`, `staging`, and `monitoring` tables
3. `warehouse.sql` — star-schema dimensions and facts (also seeds `dim_date`, `dim_channel`, `dim_currency`, `dim_payment_method`)
4. `analytics.sql` — BI views over the warehouse

## Exact apply commands (Windows PowerShell)

From the project root, after `shopsphere` exists and with `psql` on PATH:

```powershell
psql -U postgres -d shopsphere -f sql/schemas.sql
psql -U postgres -d shopsphere -f sql/warehouse.sql
psql -U postgres -d shopsphere -f sql/analytics.sql
```

If `psql` is not on PATH, use the full path to your local `psql.exe` with the same `-U`, `-d`, and `-f` arguments.

You will be prompted for the `postgres` user password unless you set `PGPASSWORD` or use a local `.pgpass` file.

## Upgrading an older warehouse

If `shopsphere` was created before historical INR reporting columns existed:

1. Re-apply `warehouse.sql` while connected to `shopsphere`. It adds missing `*_amount_inr` columns on `fact_sales` with `ADD COLUMN IF NOT EXISTS` and attaches matching CHECKs without dropping data.
2. Re-apply `analytics.sql` so views that read those INR columns are current (`CREATE OR REPLACE VIEW`).

Fresh databases only need the normal schemas → warehouse → analytics order once.

## Files

| File | Purpose |
|---|---|
| `schemas.sql` | Creates `raw`, `staging`, `warehouse`, `analytics`, `monitoring`. Defines source landing tables, typed staging tables, and ETL metadata tables. |
| `warehouse.sql` | Star schema: date/customer/product/store/channel/currency/payment-method dimensions plus `fact_sales` and `fact_delivery`. Seeds calendar and small reference dimensions. Includes safe INR column upgrades for older databases. |
| `analytics.sql` | Reporting views over warehouse facts for BI (Power BI and ad-hoc SQL). |

## Schema roles

- **raw** — CSV as received. Loose types, no foreign keys, no strict CHECKs, so dirty rows can load. ETL truncates and reloads these tables each run.
- **staging** — Typed validated rows only, plus `_is_valid` / `_dq_status` metadata. Loaded only after the quality gate passes.
- **warehouse** — Conformed star schema used for analytics.
- **analytics** — Views that Power BI and SQL consumers query.
- **monitoring** — Pipeline run log and data-quality result rows.

## ETL relationship

The Python ETL (`python -m src.etl`) expects these objects to exist:

1. Extract CSVs → load `raw.*`
2. Validate → write rejects → record DQ in `monitoring.*`
3. Quality gate (default 95% per source table)
4. Load `staging.*` → transform → upsert warehouse dims/facts

Rejected rows never enter warehouse facts. See the root `README.md` for runtime commands.

## Grain

- `warehouse.fact_sales`: one row = one product line on one customer order
- `warehouse.fact_delivery`: one row = one delivery event for one order

## Historical INR reporting

- Transaction-currency amounts stay on `fact_sales` (`unit_price`, `gross_amount`, `discount_amount`, `net_amount`, `cost_amount`, `profit_amount`) with `currency_key` = the order currency.
- ETL also persists historical FX reporting measures from `exchange_rates` on the order date: `gross_amount_inr`, `discount_amount_inr`, `net_amount_inr`, `cost_amount_inr`, `profit_amount_inr`.
- Analytics sales/profit measures use those persisted `*_amount_inr` columns.
- `dim_currency.rate_to_inr` is a latest-known **reference** rate refreshed by ETL; it is not the historical conversion source for analytics.

## Analytics views

Defined in `analytics.sql`:

| View | Intended use |
|---|---|
| `analytics.monthly_sales` | Monthly sales, distinct orders, units, and profit (INR) |
| `analytics.category_performance` | Sales, units, orders, and profit by product category (INR) |
| `analytics.product_performance` | Sales, units, orders, and profit by product (INR) |
| `analytics.store_performance` | Sales, orders, units, and profit by store / fulfillment location (INR) |
| `analytics.channel_performance` | Sales, orders, units, and profit by sales channel (INR) |
| `analytics.customer_performance` | Sales, orders, units, and profit by customer (INR) |
| `analytics.delivery_performance` | Delivery counts and averages by type, status, and channel group |

Views return no rows until ETL loads the warehouse. They do not hard-code figures.

## Seeded reference data

Applied by `warehouse.sql` (safe to re-run):

- `dim_date` (2015-01-01 through 2030-12-31)
- `dim_channel`
- `dim_currency`
- `dim_payment_method`

After SQL init but before ETL, business dimensions (`dim_customer`, `dim_product`, `dim_store`) and facts are empty; analytics views therefore return zero rows until a successful warehouse load.
