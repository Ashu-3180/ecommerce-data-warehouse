"""Focused tests for store date validation dtype handling."""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.etl.validate import validate_stores


def test_validate_stores_opening_date_string_dtype_converts_without_typeerror() -> None:
    """Regression: assigning date into a pandas string column must not raise TypeError."""
    df = pd.DataFrame(
        {
            "store_id": pd.Series(["STR-0001", "STR-0002", "STR-0003"], dtype="string"),
            "store_name": pd.Series(
                ["ShopSphere Retail - A", "ShopSphere Dark - B", "ShopSphere FC - C"],
                dtype="string",
            ),
            "store_type": pd.Series(["RETAIL_STORE", "DARK_STORE", "FULFILLMENT_CENTER"], dtype="string"),
            "country": pd.Series(["India", "India", "India"], dtype="string"),
            "region": pd.Series(["Maharashtra", "Karnataka", "Delhi"], dtype="string"),
            "city": pd.Series(["Mumbai", "Bengaluru", "Delhi"], dtype="string"),
            "latitude": pd.Series(["19.0760", "12.9716", "28.6139"], dtype="string"),
            "longitude": pd.Series(["72.8777", "77.5946", "77.2090"], dtype="string"),
            "opening_date": pd.Series(["2020-01-15", "not-a-date", "2018-06-01"], dtype="string"),
        }
    )

    result = validate_stores(df)

    assert result.total_count == 3
    assert result.valid_count == 2
    assert result.rejected_count == 1
    assert result.rule_failures.get("invalid_opening_date") == 1
    assert result.rejected.iloc[0]["failed_rule"] == "invalid_opening_date"

    opening_dates = list(result.valid["opening_date"])
    assert opening_dates == [date(2020, 1, 15), date(2018, 6, 1)]
    assert all(isinstance(value, date) for value in opening_dates)
