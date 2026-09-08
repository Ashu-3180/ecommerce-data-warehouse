# ShopSphere SQL

PostgreSQL objects for the ShopSphere data warehouse. Scripts are idempotent (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING`) and do **not** drop databases, schemas, or data.

## Run order

1. Create the database once (you run this manually):

   ```sql
   CREATE DATABASE shopsphere;
   ```

2. `schemas.sql` — schemas, raw tables, staging tables, monitoring tables
3. `warehouse.sql` — star-schema dimensions and facts (also seeds `dim_date`, `dim_channel`, `dim_currency`, `dim_payment_method`)
4. `analytics.sql` — BI views over the warehouse

Do not run these files against the `postgres` maintenance database except for `CREATE DATABASE`.

## Files

| File | Purpose |
|---|---|
| `schemas.sql` | Creates `raw`, `staging`, `warehouse`, `analytics`, `monitoring`. Defines source landing tables, typed staging tables, and ETL metadata tables. |
| `warehouse.sql` | Star schema: date/customer/product/store/channel/currency/payment-method dimensions plus `fact_sales` and `fact_delivery`. |
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
