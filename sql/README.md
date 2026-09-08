# ShopSphere SQL

PostgreSQL objects for the ShopSphere data warehouse. Scripts are idempotent (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING` / `CREATE OR REPLACE VIEW`) and do **not** drop databases, schemas, or data.

## Run order

1. Create the database once (you run this manually as a PostgreSQL superuser):

   ```sql
   CREATE DATABASE shopsphere;
   ```

2. `schemas.sql` — schemas, raw tables, staging tables, monitoring tables
3. `warehouse.sql` — star-schema dimensions and facts (also seeds `dim_date`, `dim_channel`, `dim_currency`, `dim_payment_method`)
4. `analytics.sql` — BI views over the warehouse

Do not run steps 2–4 against the `postgres` maintenance database. Connect to `shopsphere`.

## Exact apply commands (Windows PowerShell)

From the project root, after `shopsphere` exists:

```powershell
& "E:\softwares\postgresql\bin\psql.exe" -U postgres -d shopsphere -f sql\schemas.sql
& "E:\softwares\postgresql\bin\psql.exe" -U postgres -d shopsphere -f sql\warehouse.sql
& "E:\softwares\postgresql\bin\psql.exe" -U postgres -d shopsphere -f sql\analytics.sql
```

If `psql` is already on your PATH:

```powershell
psql -U postgres -d shopsphere -f sql/schemas.sql
psql -U postgres -d shopsphere -f sql/warehouse.sql
psql -U postgres -d shopsphere -f sql/analytics.sql
```

You will be prompted for the `postgres` user password unless you set `PGPASSWORD` or use a local `.pgpass` file.

## Files

| File | Purpose |
|---|---|
| `schemas.sql` | Creates `raw`, `staging`, `warehouse`, `analytics`, `monitoring`. Defines source landing tables, typed staging tables, and ETL metadata tables. |
| `warehouse.sql` | Star schema: date/customer/product/store/channel/currency/payment-method dimensions plus `fact_sales` and `fact_delivery`. Seeds calendar and small reference dimensions. |
| `analytics.sql` | Reporting views such as monthly sales and category / store / channel performance. |

## Schema roles

- **raw** — CSV as received. Loose types, no foreign keys, no strict CHECKs, so dirty rows can load.
- **staging** — Typed copy plus `_is_valid` / `_dq_status` columns for a future validation step.
- **warehouse** — Conformed star schema used for analytics.
- **analytics** — Views Power BI (later) will query.
- **monitoring** — Pipeline run log and data-quality result rows.

## Grain

- `warehouse.fact_sales`: one row = one product line on one customer order
- `warehouse.fact_delivery`: one row = one delivery event for one order

## What is intentionally empty

Until ETL is built:

- `raw.*` and `staging.*` tables have no CSV data loaded
- `dim_customer`, `dim_product`, `dim_store` are empty
- `fact_sales` and `fact_delivery` are empty
- analytics views return zero rows

Seeded now (safe reference data only):

- `dim_date` (2015-01-01 through 2030-12-31)
- `dim_channel`
- `dim_currency`
- `dim_payment_method`
