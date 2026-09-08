"""Transform validated ShopSphere data into warehouse-ready frames.

Responsibilities
----------------
- Normalize types on already-validated rows.
- Calculate order-line sales metrics in the **transaction currency**.
- Join ``exchange_rates`` to produce INR reporting equivalents (not hardcoded).
- Build dimension upsert frames and fact frames for warehouse load.

Grain
-----
- ``fact_sales``: one row = one product line within one customer order
- ``fact_delivery``: one row = one delivery event for one order

Order header totals are **not** copied onto every order-item row. Order-level
attributes needed for slicing (customer, store, channel, status, currency)
are carried on the line; ``order_total`` stays on the order/staging layer only.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.etl.constants import (
    CHANNEL_KEY_BY_CODE,
    CURRENCY_KEY_BY_CODE,
    PAYMENT_METHOD_KEY_BY_CODE,
)
from src.etl.load import (
    replace_fact_delivery,
    replace_fact_sales,
    upsert_dataframe,
)

logger = logging.getLogger("shopsphere.etl.transform")

FACT_SALES_LOAD_COLUMNS: tuple[str, ...] = (
    "date_key",
    "customer_key",
    "product_key",
    "store_key",
    "channel_key",
    "currency_key",
    "payment_method_key",
    "source_order_id",
    "source_order_item_id",
    "quantity",
    "unit_price",
    "gross_amount",
    "discount_amount",
    "net_amount",
    "cost_amount",
    "profit_amount",
    "order_status",
)

FACT_DELIVERY_LOAD_COLUMNS: tuple[str, ...] = (
    "date_key",
    "customer_key",
    "store_key",
    "channel_key",
    "source_order_id",
    "delivery_id",
    "delivery_type",
    "delivery_status",
    "delivery_distance_km",
    "delivery_time_minutes",
    "delivery_fee",
)


def _to_date_series(series: pd.Series) -> pd.Series:
    """Convert values to Python ``date`` objects (invalid → NaT/None-safe)."""
    return pd.to_datetime(series, errors="coerce").dt.date


def _date_key(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        value = value.date()
    if not isinstance(value, date):
        return None
    return int(value.strftime("%Y%m%d"))


def calculate_line_amounts(
    quantity: pd.Series,
    unit_price: pd.Series,
    discount_percent: pd.Series,
    unit_cost: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Calculate order-line metrics in the transaction currency.

    gross_amount     = quantity * unit_price
    discount_amount  = gross_amount * discount_percent / 100
    net_amount       = gross_amount - discount_amount
    cost_amount      = quantity * unit_cost (0 when cost missing)
    profit_amount    = net_amount - cost_amount
    """
    qty = pd.to_numeric(quantity, errors="coerce")
    price = pd.to_numeric(unit_price, errors="coerce")
    discount_pct = pd.to_numeric(discount_percent, errors="coerce").fillna(0.0)
    cost_each = (
        pd.to_numeric(unit_cost, errors="coerce").fillna(0.0)
        if unit_cost is not None
        else pd.Series(0.0, index=qty.index)
    )

    gross = (qty * price).round(2)
    discount = (gross * discount_pct / 100.0).round(2)
    net = (gross - discount).round(2)
    cost = (qty * cost_each).round(2)
    profit = (net - cost).round(2)

    return pd.DataFrame(
        {
            "quantity": qty,
            "unit_price": price.round(2),
            "discount_percent": discount_pct,
            "gross_amount": gross,
            "discount_amount": discount,
            "net_amount": net,
            "cost_amount": cost,
            "profit_amount": profit,
        },
        index=qty.index,
    )


def convert_amounts_to_inr(amounts: pd.DataFrame, fx_rate: pd.Series) -> pd.DataFrame:
    """Multiply monetary columns by FX rate (rate_to_inr from exchange_rates)."""
    rate = pd.to_numeric(fx_rate, errors="coerce")
    money_cols = [
        "unit_price",
        "gross_amount",
        "discount_amount",
        "net_amount",
        "cost_amount",
        "profit_amount",
    ]
    out = amounts.copy()
    for col in money_cols:
        if col in out.columns:
            out[f"{col}_inr"] = (pd.to_numeric(out[col], errors="coerce") * rate).round(2)
    out["fx_rate_to_inr"] = rate
    return out


def attach_exchange_rates(
    frame: pd.DataFrame,
    exchange_rates: pd.DataFrame,
    *,
    currency_col: str = "currency",
    date_col: str = "order_date",
) -> pd.DataFrame:
    """
    Attach ``fx_rate`` from ``exchange_rates`` (rate_to_inr) by currency + date.

    Falls back to the latest available rate for that currency when the exact
    date is missing. Never uses hardcoded FX constants.
    """
    if frame.empty:
        out = frame.copy()
        out["fx_rate"] = pd.Series(dtype=float)
        return out

    rates = exchange_rates.copy()
    rates["rate_date"] = _to_date_series(rates["rate_date"])
    rates["rate_to_inr"] = pd.to_numeric(rates["rate_to_inr"], errors="coerce")
    rates["currency_code"] = rates["currency_code"].astype(str).str.strip().str.upper()
    rates = rates.dropna(subset=["rate_date", "rate_to_inr", "currency_code"])
    rates = rates.rename(columns={"currency_code": currency_col, "rate_to_inr": "fx_rate"})
    rates = rates[[currency_col, "rate_date", "fx_rate"]].drop_duplicates(
        [currency_col, "rate_date"], keep="last"
    )

    merged = frame.copy()
    merged[currency_col] = merged[currency_col].astype(str).str.strip().str.upper()
    merged[date_col] = _to_date_series(merged[date_col])

    merged = merged.merge(
        rates,
        left_on=[currency_col, date_col],
        right_on=[currency_col, "rate_date"],
        how="left",
    )

    latest = (
        rates.sort_values("rate_date")
        .drop_duplicates(currency_col, keep="last")
        .rename(columns={"fx_rate": "fx_rate_latest"})[[currency_col, "fx_rate_latest"]]
    )
    merged = merged.merge(latest, on=currency_col, how="left")
    merged["fx_rate"] = merged["fx_rate"].fillna(merged["fx_rate_latest"])
    inr_mask = merged[currency_col].eq("INR") & merged["fx_rate"].isna()
    merged.loc[inr_mask, "fx_rate"] = 1.0
    return merged.drop(columns=["rate_date", "fx_rate_latest"], errors="ignore")


def ensure_dim_dates(engine: Engine, dates: pd.Series) -> int:
    """Insert any missing calendar dates into warehouse.dim_date."""
    unique_dates = sorted({d for d in dates.dropna().tolist()})
    if not unique_dates:
        return 0

    rows = []
    for d in unique_dates:
        if isinstance(d, pd.Timestamp):
            d = d.date()
        ts = pd.Timestamp(d)
        rows.append(
            {
                "date_key": int(ts.strftime("%Y%m%d")),
                "full_date": d,
                "day_of_month": int(ts.day),
                "day_name": ts.strftime("%A"),
                "week_number": int(ts.isocalendar().week),
                "month_number": int(ts.month),
                "month_name": ts.strftime("%B"),
                "quarter_number": int((ts.month - 1) // 3 + 1),
                "year": int(ts.year),
                "is_weekend": bool(ts.dayofweek >= 5),
            }
        )
    frame = pd.DataFrame(rows).drop_duplicates(subset=["date_key"])
    return upsert_dataframe(
        engine,
        frame,
        schema="warehouse",
        table="dim_date",
        conflict_column="date_key",
        update_columns=[
            "full_date",
            "day_of_month",
            "day_name",
            "week_number",
            "month_number",
            "month_name",
            "quarter_number",
            "year",
            "is_weekend",
        ],
    )


def refresh_dim_currency_rates(engine: Engine, exchange_rates: pd.DataFrame) -> int:
    """Update dim_currency.rate_to_inr from the latest exchange_rates row per code."""
    if exchange_rates.empty:
        return 0
    rates = exchange_rates.copy()
    rates["rate_date"] = _to_date_series(rates["rate_date"])
    rates["rate_to_inr"] = pd.to_numeric(rates["rate_to_inr"], errors="coerce")
    rates["currency_code"] = rates["currency_code"].astype(str).str.strip().str.upper()
    rates = rates.dropna(subset=["rate_date", "rate_to_inr", "currency_code"])
    rates = rates.sort_values("rate_date").drop_duplicates("currency_code", keep="last")

    updated = 0
    with engine.begin() as conn:
        for row in rates.itertuples(index=False):
            result = conn.execute(
                text(
                    """
                    UPDATE warehouse.dim_currency
                    SET rate_to_inr = :rate_to_inr
                    WHERE currency_code = :currency_code
                    """
                ),
                {"rate_to_inr": float(row.rate_to_inr), "currency_code": str(row.currency_code)},
            )
            updated += int(result.rowcount or 0)
    logger.info("Updated %s dim_currency reference rates from exchange_rates", updated)
    return updated


def _payment_method_by_order(payments: pd.DataFrame) -> pd.DataFrame:
    """Pick one payment method per order (prefer SUCCESS)."""
    if payments.empty:
        return pd.DataFrame(columns=["order_id", "payment_method"])
    ranked = payments.copy()
    ranked["payment_method"] = ranked["payment_method"].astype(str).str.strip().str.upper()
    ranked["_pref"] = ranked["payment_status"].eq("SUCCESS").astype(int)
    ranked = ranked.sort_values(["order_id", "_pref"], ascending=[True, False])
    return ranked.drop_duplicates("order_id", keep="first")[["order_id", "payment_method"]]


def build_dim_customer_frame(customers: pd.DataFrame) -> pd.DataFrame:
    frame = customers.copy()
    frame["signup_date"] = _to_date_series(frame["signup_date"])
    cols = [
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
    ]
    return frame.loc[:, cols].drop_duplicates(subset=["customer_id"], keep="first")


def build_dim_product_frame(products: pd.DataFrame) -> pd.DataFrame:
    frame = products.copy()
    frame["unit_cost"] = pd.to_numeric(frame["unit_cost"], errors="coerce")
    frame["selling_price"] = pd.to_numeric(frame["selling_price"], errors="coerce")
    frame["product_rating"] = pd.to_numeric(frame["product_rating"], errors="coerce")
    cols = [
        "product_id",
        "product_name",
        "category",
        "subcategory",
        "brand",
        "supplier",
        "unit_cost",
        "selling_price",
        "product_rating",
    ]
    return frame.loc[:, cols].drop_duplicates(subset=["product_id"], keep="first")


def build_dim_store_frame(stores: pd.DataFrame) -> pd.DataFrame:
    frame = stores.copy()
    frame["opening_date"] = _to_date_series(frame["opening_date"])
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    cols = [
        "store_id",
        "store_name",
        "store_type",
        "country",
        "region",
        "city",
        "latitude",
        "longitude",
        "opening_date",
    ]
    return frame.loc[:, cols].drop_duplicates(subset=["store_id"], keep="first")


def build_fact_sales(
    valid: dict[str, pd.DataFrame],
    dim_lookups: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Build order-line sales facts (plus INR helper columns for reporting/tests).

    Warehouse load columns keep **original currency** amounts and ``currency_key``.
    INR equivalents (``*_inr``) are derived from ``exchange_rates`` and are not
    written to ``fact_sales`` (analytics converts via ``dim_currency.rate_to_inr``).
    """
    items = valid["order_items"].copy()
    orders = valid["orders"].copy()
    products = dim_lookups["dim_product"].copy()

    orders["order_date"] = _to_date_series(orders["order_date"])
    orders["currency"] = orders["currency"].astype(str).str.strip().str.upper()
    orders["sales_channel"] = orders["sales_channel"].astype(str).str.strip().str.upper()
    orders["order_status"] = orders["order_status"].astype(str).str.strip().str.upper()

    # Order header only — never explode order_total onto each line.
    order_cols = [
        "order_id",
        "customer_id",
        "store_id",
        "order_date",
        "sales_channel",
        "order_status",
        "currency",
    ]
    merged = items.merge(orders.loc[:, order_cols], on="order_id", how="inner")
    merged = merged.merge(dim_lookups["dim_customer"], on="customer_id", how="inner")
    merged = merged.merge(products, on="product_id", how="inner")
    merged = merged.merge(dim_lookups["dim_store"], on="store_id", how="inner")
    merged = merged.merge(_payment_method_by_order(valid["payments"]), on="order_id", how="left")

    amounts = calculate_line_amounts(
        merged["quantity"],
        merged["unit_price"],
        merged["discount_percent"],
        merged["unit_cost"],
    )
    for col in amounts.columns:
        merged[col] = amounts[col]

    merged = attach_exchange_rates(
        merged,
        valid["exchange_rates"],
        currency_col="currency",
        date_col="order_date",
    )
    inr = convert_amounts_to_inr(amounts, merged["fx_rate"])

    currency_keys = merged["currency"].map(CURRENCY_KEY_BY_CODE)
    channel_keys = merged["sales_channel"].map(CHANNEL_KEY_BY_CODE)
    payment_keys = merged["payment_method"].map(PAYMENT_METHOD_KEY_BY_CODE)

    fact = pd.DataFrame(
        {
            "date_key": merged["order_date"].map(_date_key),
            "customer_key": merged["customer_key"].astype("int64"),
            "product_key": merged["product_key"].astype("int64"),
            "store_key": merged["store_key"].astype("int64"),
            "channel_key": channel_keys,
            "currency_key": currency_keys,
            "payment_method_key": payment_keys,
            "source_order_id": merged["order_id"].astype(str),
            "source_order_item_id": merged["order_item_id"].astype(str),
            "quantity": merged["quantity"].astype(int),
            "unit_price": merged["unit_price"],
            "gross_amount": merged["gross_amount"],
            "discount_amount": merged["discount_amount"],
            "net_amount": merged["net_amount"],
            "cost_amount": merged["cost_amount"],
            "profit_amount": merged["profit_amount"],
            "order_status": merged["order_status"].astype(str),
            # Reporting helpers (stripped before warehouse INSERT).
            "currency_code": merged["currency"].astype(str),
            "fx_rate_to_inr": inr["fx_rate_to_inr"],
            "unit_price_inr": inr["unit_price_inr"],
            "gross_amount_inr": inr["gross_amount_inr"],
            "discount_amount_inr": inr["discount_amount_inr"],
            "net_amount_inr": inr["net_amount_inr"],
            "cost_amount_inr": inr["cost_amount_inr"],
            "profit_amount_inr": inr["profit_amount_inr"],
        }
    )

    fact = fact.dropna(
        subset=["date_key", "customer_key", "product_key", "store_key", "channel_key", "currency_key"]
    )
    fact["date_key"] = fact["date_key"].astype(int)
    fact["channel_key"] = fact["channel_key"].astype(int)
    fact["currency_key"] = fact["currency_key"].astype(int)
    fact["payment_method_key"] = fact["payment_method_key"].astype("Int64")

    logger.info("Built fact_sales with %s order-line rows", len(fact))
    return fact.reset_index(drop=True)


def build_fact_delivery(
    valid: dict[str, pd.DataFrame],
    dim_lookups: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build delivery facts at order/delivery grain (separate from sales lines)."""
    deliveries = valid["deliveries"].copy()
    if deliveries.empty:
        return pd.DataFrame(columns=list(FACT_DELIVERY_LOAD_COLUMNS))

    orders = valid["orders"][["order_id", "customer_id", "sales_channel", "order_date"]].copy()
    orders["sales_channel"] = orders["sales_channel"].astype(str).str.strip().str.upper()
    orders["order_date"] = _to_date_series(orders["order_date"])

    merged = deliveries.merge(orders, on="order_id", how="inner")
    merged = merged.merge(dim_lookups["dim_customer"], on="customer_id", how="inner")
    merged = merged.merge(dim_lookups["dim_store"], on="store_id", how="inner")

    fact = pd.DataFrame(
        {
            "date_key": merged["order_date"].map(_date_key),
            "customer_key": merged["customer_key"].astype("int64"),
            "store_key": merged["store_key"].astype("int64"),
            "channel_key": merged["sales_channel"].map(CHANNEL_KEY_BY_CODE),
            "source_order_id": merged["order_id"].astype(str),
            "delivery_id": merged["delivery_id"].astype(str),
            "delivery_type": merged["delivery_type"].astype(str).str.strip().str.upper(),
            "delivery_status": merged["delivery_status"].astype(str).str.strip().str.upper(),
            "delivery_distance_km": pd.to_numeric(merged["delivery_distance_km"], errors="coerce").round(2),
            "delivery_time_minutes": pd.to_numeric(merged["delivery_time_minutes"], errors="coerce")
            .round()
            .astype("Int64"),
            "delivery_fee": pd.to_numeric(merged["delivery_fee"], errors="coerce").round(2),
        }
    )
    fact = fact.dropna(
        subset=["date_key", "customer_key", "store_key", "channel_key", "delivery_time_minutes"]
    )
    fact["date_key"] = fact["date_key"].astype(int)
    fact["channel_key"] = fact["channel_key"].astype(int)
    fact["delivery_time_minutes"] = fact["delivery_time_minutes"].astype(int)

    logger.info("Built fact_delivery with %s rows", len(fact))
    return fact.reset_index(drop=True)


def transform_all(
    valid: dict[str, pd.DataFrame],
    dim_lookups: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Pure transform step (no database writes).

    When ``dim_lookups`` is omitted, surrogate keys are synthesized from the
    validated business keys so unit tests can exercise amount/FX logic without
    PostgreSQL. Production passes lookups loaded from the warehouse.
    """
    customers = build_dim_customer_frame(valid["customers"])
    products = build_dim_product_frame(valid["products"])
    stores = build_dim_store_frame(valid["stores"])

    if dim_lookups is None:
        # Synthetic keys for offline/unit tests only — production passes DB lookups.
        cust_keys = customers[["customer_id"]].copy()
        cust_keys.insert(0, "customer_key", range(1, len(cust_keys) + 1))
        prod_keys = products[["product_id", "unit_cost"]].copy()
        prod_keys.insert(0, "product_key", range(1, len(prod_keys) + 1))
        store_keys = stores[["store_id"]].copy()
        store_keys.insert(0, "store_key", range(1, len(store_keys) + 1))
        dim_lookups = {
            "dim_customer": cust_keys,
            "dim_product": prod_keys,
            "dim_store": store_keys,
        }

    fact_sales = build_fact_sales(valid, dim_lookups)
    fact_delivery = build_fact_delivery(valid, dim_lookups)

    return {
        "dim_customer": customers,
        "dim_product": products,
        "dim_store": stores,
        "fact_sales": fact_sales,
        "fact_delivery": fact_delivery,
        "exchange_rates": valid["exchange_rates"].copy(),
        "orders": valid["orders"].copy(),
        "payments": valid["payments"].copy(),
    }


def load_dimensions(engine: Engine, valid: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Upsert customer/product/store dims and return key lookup frames from PostgreSQL."""
    customers = build_dim_customer_frame(valid["customers"])
    products = build_dim_product_frame(valid["products"])
    stores = build_dim_store_frame(valid["stores"])

    ensure_dim_dates(
        engine,
        pd.concat(
            [
                customers["signup_date"],
                stores["opening_date"],
                _to_date_series(valid["orders"]["order_date"]),
                _to_date_series(valid["payments"]["payment_date"]),
                _to_date_series(valid["exchange_rates"]["rate_date"]),
            ],
            ignore_index=True,
        ),
    )

    upsert_dataframe(
        engine,
        customers,
        schema="warehouse",
        table="dim_customer",
        conflict_column="customer_id",
        update_columns=[
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
    )
    upsert_dataframe(
        engine,
        products,
        schema="warehouse",
        table="dim_product",
        conflict_column="product_id",
        update_columns=[
            "product_name",
            "category",
            "subcategory",
            "brand",
            "supplier",
            "unit_cost",
            "selling_price",
            "product_rating",
        ],
    )
    upsert_dataframe(
        engine,
        stores,
        schema="warehouse",
        table="dim_store",
        conflict_column="store_id",
        update_columns=[
            "store_name",
            "store_type",
            "country",
            "region",
            "city",
            "latitude",
            "longitude",
            "opening_date",
        ],
    )

    # Reference dims (channel / currency / payment_method) are seeded in SQL.
    refresh_dim_currency_rates(engine, valid["exchange_rates"])

    with engine.connect() as conn:
        dim_customer = pd.read_sql(
            text("SELECT customer_key, customer_id FROM warehouse.dim_customer"),
            conn,
        )
        dim_product = pd.read_sql(
            text("SELECT product_key, product_id, unit_cost FROM warehouse.dim_product"),
            conn,
        )
        dim_store = pd.read_sql(
            text("SELECT store_key, store_id FROM warehouse.dim_store"),
            conn,
        )

    return {
        "dim_customer": dim_customer,
        "dim_product": dim_product,
        "dim_store": dim_store,
    }


def fact_sales_for_load(fact_sales: pd.DataFrame) -> pd.DataFrame:
    """Strip INR helper columns before inserting into warehouse.fact_sales."""
    cols = [c for c in FACT_SALES_LOAD_COLUMNS if c in fact_sales.columns]
    return fact_sales.loc[:, cols].copy()


def fact_delivery_for_load(fact_delivery: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in FACT_DELIVERY_LOAD_COLUMNS if c in fact_delivery.columns]
    return fact_delivery.loc[:, cols].copy()


def load_transformed_warehouse(engine: Engine, transformed: dict[str, pd.DataFrame]) -> int:
    """Idempotent warehouse load from frames produced by ``transform_all``."""
    loaded = 0
    loaded += upsert_dataframe(
        engine,
        transformed["dim_customer"],
        schema="warehouse",
        table="dim_customer",
        conflict_column="customer_id",
        update_columns=[
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
    )
    loaded += upsert_dataframe(
        engine,
        transformed["dim_product"],
        schema="warehouse",
        table="dim_product",
        conflict_column="product_id",
        update_columns=[
            "product_name",
            "category",
            "subcategory",
            "brand",
            "supplier",
            "unit_cost",
            "selling_price",
            "product_rating",
        ],
    )
    loaded += upsert_dataframe(
        engine,
        transformed["dim_store"],
        schema="warehouse",
        table="dim_store",
        conflict_column="store_id",
        update_columns=[
            "store_name",
            "store_type",
            "country",
            "region",
            "city",
            "latitude",
            "longitude",
            "opening_date",
        ],
    )
    refresh_dim_currency_rates(engine, transformed["exchange_rates"])

    sales = fact_sales_for_load(transformed["fact_sales"])
    delivery = fact_delivery_for_load(transformed["fact_delivery"])
    loaded += replace_fact_sales(engine, sales)
    loaded += replace_fact_delivery(engine, delivery)
    return loaded


def load_warehouse(engine: Engine, valid: dict[str, pd.DataFrame]) -> int:
    """
    Transform validated data, then upsert warehouse dimensions and facts.

    Production orchestrator prefers: load_dimensions → transform_all → fact load
    for clearer stage boundaries (see pipeline.py).
    """
    dim_lookups = load_dimensions(engine, valid)
    transformed = transform_all(valid, dim_lookups=dim_lookups)
    sales = fact_sales_for_load(transformed["fact_sales"])
    delivery = fact_delivery_for_load(transformed["fact_delivery"])
    loaded = (
        len(dim_lookups["dim_customer"])
        + len(dim_lookups["dim_product"])
        + len(dim_lookups["dim_store"])
        + replace_fact_sales(engine, sales)
        + replace_fact_delivery(engine, delivery)
    )
    return loaded
