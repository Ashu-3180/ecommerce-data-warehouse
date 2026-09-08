"""Load helpers for raw, staging, and warehouse schemas."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.etl.constants import SOURCE_TABLES

logger = logging.getLogger("shopsphere.etl.load")

RAW_COLUMNS: dict[str, list[str]] = {
    "customers": [
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "state",
        "country",
        "customer_segment",
        "signup_date",
    ],
    "products": [
        "product_id",
        "product_name",
        "category",
        "subcategory",
        "brand",
        "supplier",
        "unit_cost",
        "selling_price",
        "product_rating",
    ],
    "stores": [
        "store_id",
        "store_name",
        "store_type",
        "country",
        "region",
        "city",
        "latitude",
        "longitude",
        "opening_date",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "store_id",
        "order_date",
        "sales_channel",
        "order_status",
        "currency",
        "order_total",
    ],
    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
        "discount_percent",
    ],
    "payments": [
        "payment_id",
        "order_id",
        "payment_method",
        "payment_status",
        "payment_amount",
        "payment_date",
        "currency",
    ],
    "deliveries": [
        "delivery_id",
        "order_id",
        "store_id",
        "delivery_type",
        "delivery_status",
        "delivery_distance_km",
        "delivery_time_minutes",
        "delivery_fee",
    ],
    "exchange_rates": ["rate_date", "currency_code", "rate_to_inr"],
}


def _as_raw_strings(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.reindex(columns=columns).copy()
    for col in columns:
        out[col] = out[col].map(lambda value: "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value))
    return out


def load_raw_tables(engine: Engine, extracted: dict[str, pd.DataFrame]) -> int:
    """Truncate and reload raw.* tables from extracted CSVs. Returns row count loaded."""
    loaded = 0
    with engine.begin() as conn:
        for table in SOURCE_TABLES:
            conn.execute(text(f"TRUNCATE TABLE raw.{table} RESTART IDENTITY"))
            frame = _as_raw_strings(extracted[table], RAW_COLUMNS[table])
            frame.to_sql(
                table,
                con=conn,
                schema="raw",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
            loaded += len(frame)
            logger.info("Loaded raw.%s (%s rows)", table, len(frame))
    return loaded


def _prepare_staging_frame(table: str, valid_df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    frame = valid_df.copy()
    # Drop validation helper columns if present.
    frame = frame.drop(
        columns=["failed_rule", "rejection_reason", "record_identifier"],
        errors="ignore",
    )
    frame["_is_valid"] = True
    frame["_dq_status"] = "PASSED"
    frame["_rejection_reason"] = None
    frame["_processed_at"] = now
    return frame


def load_staging_tables(engine: Engine, valid_tables: dict[str, pd.DataFrame]) -> int:
    """Truncate and load validated rows into staging.*. Returns row count loaded."""
    loaded = 0
    with engine.begin() as conn:
        for table in SOURCE_TABLES:
            conn.execute(text(f"TRUNCATE TABLE staging.{table} RESTART IDENTITY"))
            frame = _prepare_staging_frame(table, valid_tables[table])
            # Keep only columns that exist on the staging table.
            staging_cols = list(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'staging' AND table_name = :table
                        ORDER BY ordinal_position
                        """
                    ),
                    {"table": table},
                ).scalars()
            )
            usable = [c for c in frame.columns if c in staging_cols and c != "_staging_id"]
            out = frame.loc[:, usable].copy()
            out.to_sql(
                table,
                con=conn,
                schema="staging",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
            loaded += len(out)
            logger.info("Loaded staging.%s (%s rows)", table, len(out))
    return loaded


def upsert_dataframe(
    engine: Engine,
    df: pd.DataFrame,
    *,
    schema: str,
    table: str,
    conflict_column: str,
    update_columns: list[str],
) -> int:
    """Insert rows with ON CONFLICT DO UPDATE for idempotent warehouse loads."""
    if df.empty:
        return 0

    cols = list(df.columns)
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    sql = f"""
        INSERT INTO {schema}.{table} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_column}) DO UPDATE
        SET {set_clause}
    """
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    with engine.begin() as conn:
        conn.execute(text(sql), records)
    logger.info("Upserted %s rows into %s.%s", len(df), schema, table)
    return len(df)


def replace_fact_sales(engine: Engine, df: pd.DataFrame) -> int:
    """Idempotent fact_sales load keyed by source_order_item_id."""
    if df.empty:
        logger.info("No fact_sales rows to load")
        return 0
    update_cols = [
        c
        for c in df.columns
        if c
        not in {
            "sales_key",
            "source_order_item_id",
        }
    ]
    return upsert_dataframe(
        engine,
        df,
        schema="warehouse",
        table="fact_sales",
        conflict_column="source_order_item_id",
        update_columns=update_cols,
    )


def replace_fact_delivery(engine: Engine, df: pd.DataFrame) -> int:
    """Idempotent fact_delivery load keyed by delivery_id."""
    if df.empty:
        logger.info("No fact_delivery rows to load")
        return 0
    update_cols = [c for c in df.columns if c not in {"delivery_key", "delivery_id"}]
    return upsert_dataframe(
        engine,
        df,
        schema="warehouse",
        table="fact_delivery",
        conflict_column="delivery_id",
        update_columns=update_cols,
    )
