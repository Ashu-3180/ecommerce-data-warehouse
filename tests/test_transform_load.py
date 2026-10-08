"""Focused tests for transform amount math, FX conversion, and load shaping."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.etl.load import replace_fact_delivery, replace_fact_sales
from src.etl.transform import (
    attach_exchange_rates,
    calculate_line_amounts,
    convert_amounts_to_inr,
    fact_sales_for_load,
    transform_all,
)


def test_calculate_line_amounts_and_discount() -> None:
    amounts = calculate_line_amounts(
        quantity=pd.Series([2, 1]),
        unit_price=pd.Series([100.0, 50.0]),
        discount_percent=pd.Series([10.0, 0.0]),
        unit_cost=pd.Series([40.0, 20.0]),
    )

    assert amounts.loc[0, "gross_amount"] == 200.0
    assert amounts.loc[0, "discount_amount"] == 20.0
    assert amounts.loc[0, "net_amount"] == 180.0
    assert amounts.loc[0, "cost_amount"] == 80.0
    assert amounts.loc[0, "profit_amount"] == 100.0
    assert amounts.loc[1, "discount_amount"] == 0.0
    assert amounts.loc[1, "net_amount"] == 50.0


def test_currency_conversion_uses_exchange_rate_not_hardcoded() -> None:
    amounts = calculate_line_amounts(
        quantity=pd.Series([1]),
        unit_price=pd.Series([10.0]),
        discount_percent=pd.Series([0.0]),
        unit_cost=pd.Series([4.0]),
    )
    # Synthetic FX from exchange_rates feed (not a constant in transform code).
    fx = pd.Series([83.5])
    inr = convert_amounts_to_inr(amounts, fx)

    assert inr.loc[0, "net_amount_inr"] == 835.0
    assert inr.loc[0, "unit_price_inr"] == 835.0
    assert inr.loc[0, "cost_amount_inr"] == 334.0
    assert inr.loc[0, "fx_rate_to_inr"] == 83.5


def test_attach_exchange_rates_prefers_order_date_then_latest() -> None:
    frame = pd.DataFrame(
        {
            "currency": ["USD", "USD"],
            "order_date": [date(2024, 1, 1), date(2024, 6, 1)],
            "amount": [1.0, 1.0],
        }
    )
    rates = pd.DataFrame(
        {
            "currency_code": ["USD", "USD"],
            "rate_date": ["2024-01-01", "2024-12-31"],
            "rate_to_inr": [80.0, 84.0],
        }
    )
    attached = attach_exchange_rates(frame, rates)
    assert attached.loc[0, "fx_rate"] == 80.0
    # 2024-06-01 missing → fall back to latest USD rate (84.0)
    assert attached.loc[1, "fx_rate"] == 84.0


def _sample_valid_tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.DataFrame(
            [
                {
                    "customer_id": "CUST-1",
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "email": "ada@example.com",
                    "phone": "+1-555",
                    "city": "London",
                    "state": "England",
                    "country": "United Kingdom",
                    "customer_segment": "PREMIUM",
                    "signup_date": "2023-01-01",
                }
            ]
        ),
        "products": pd.DataFrame(
            [
                {
                    "product_id": "PRD-1",
                    "product_name": "Widget",
                    "category": "Electronics",
                    "subcategory": "Gadgets",
                    "brand": "Acme",
                    "supplier": "SupplyCo",
                    "unit_cost": 40.0,
                    "selling_price": 100.0,
                    "product_rating": 4.5,
                }
            ]
        ),
        "stores": pd.DataFrame(
            [
                {
                    "store_id": "STR-1",
                    "store_name": "London FC",
                    "store_type": "FULFILLMENT_CENTER",
                    "country": "United Kingdom",
                    "region": "England",
                    "city": "London",
                    "latitude": 51.5,
                    "longitude": -0.1,
                    "opening_date": "2020-01-01",
                }
            ]
        ),
        "orders": pd.DataFrame(
            [
                {
                    "order_id": "ORD-1",
                    "customer_id": "CUST-1",
                    "store_id": "STR-1",
                    "order_date": "2024-01-01",
                    "sales_channel": "WEBSITE",
                    "order_status": "DELIVERED",
                    "currency": "USD",
                    "order_total": 180.0,
                }
            ]
        ),
        "order_items": pd.DataFrame(
            [
                {
                    "order_item_id": "ITEM-1",
                    "order_id": "ORD-1",
                    "product_id": "PRD-1",
                    "quantity": 2,
                    "unit_price": 100.0,
                    "discount_percent": 10.0,
                }
            ]
        ),
        "payments": pd.DataFrame(
            [
                {
                    "payment_id": "PAY-1",
                    "order_id": "ORD-1",
                    "payment_method": "CREDIT_CARD",
                    "payment_status": "SUCCESS",
                    "payment_amount": 180.0,
                    "payment_date": "2024-01-01",
                    "currency": "USD",
                }
            ]
        ),
        "deliveries": pd.DataFrame(
            [
                {
                    "delivery_id": "DEL-1",
                    "order_id": "ORD-1",
                    "store_id": "STR-1",
                    "delivery_type": "STANDARD",
                    "delivery_status": "DELIVERED",
                    "delivery_distance_km": 12.5,
                    "delivery_time_minutes": 1440,
                    "delivery_fee": 5.0,
                }
            ]
        ),
        "exchange_rates": pd.DataFrame(
            [
                {"rate_date": "2024-01-01", "currency_code": "USD", "rate_to_inr": 80.0},
                {"rate_date": "2024-01-01", "currency_code": "INR", "rate_to_inr": 1.0},
            ]
        ),
    }


def test_transform_output_preserves_original_currency_and_builds_inr() -> None:
    transformed = transform_all(_sample_valid_tables())
    sales = transformed["fact_sales"]

    assert len(sales) == 1
    row = sales.iloc[0]
    # Transaction-currency amounts preserved for warehouse.
    assert row["currency_code"] == "USD"
    assert row["currency_key"] == 2  # USD
    assert row["gross_amount"] == 200.0
    assert row["discount_amount"] == 20.0
    assert row["net_amount"] == 180.0
    # INR helpers from exchange_rates (80.0), not hardcoded in load columns.
    assert row["fx_rate_to_inr"] == 80.0
    assert row["net_amount_inr"] == 14400.0
    # Order total must not be duplicated onto the line.
    assert "order_total" not in sales.columns

    loadable = fact_sales_for_load(sales)
    assert "gross_amount_inr" in loadable.columns
    assert "discount_amount_inr" in loadable.columns
    assert "net_amount_inr" in loadable.columns
    assert "cost_amount_inr" in loadable.columns
    assert "profit_amount_inr" in loadable.columns
    assert "fx_rate_to_inr" not in loadable.columns
    assert loadable.iloc[0]["net_amount"] == 180.0

    delivery = transformed["fact_delivery"]
    assert len(delivery) == 1
    assert delivery.iloc[0]["delivery_id"] == "DEL-1"


def test_transform_is_deterministic() -> None:
    valid = _sample_valid_tables()
    first = transform_all(valid)["fact_sales"]
    second = transform_all(valid)["fact_sales"]
    pd.testing.assert_frame_equal(first, second)


def test_fact_sales_load_shape_is_idempotent_safe() -> None:
    """Load frame uses unique business keys expected by ON CONFLICT upserts."""
    sales = fact_sales_for_load(transform_all(_sample_valid_tables())["fact_sales"])
    assert sales["source_order_item_id"].is_unique
    assert set(sales.columns) <= {
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
        "gross_amount_inr",
        "discount_amount_inr",
        "net_amount_inr",
        "cost_amount_inr",
        "profit_amount_inr",
        "order_status",
    }
    # Documented upsert targets remain the load helpers used by the pipeline.
    assert "source_order_item_id" in (replace_fact_sales.__doc__ or "")
    assert "delivery_id" in (replace_fact_delivery.__doc__ or "")
