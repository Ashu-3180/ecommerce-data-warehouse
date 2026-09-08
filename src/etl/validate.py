"""Record-level data-quality validation for ShopSphere source tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.etl.constants import (
    VALID_CHANNELS,
    VALID_CURRENCIES,
    VALID_CUSTOMER_SEGMENTS,
    VALID_DELIVERY_STATUSES,
    VALID_DELIVERY_TYPES,
    VALID_ORDER_STATUSES,
    VALID_PAYMENT_METHODS,
    VALID_PAYMENT_STATUSES,
    VALID_STORE_TYPES,
)

logger = logging.getLogger("shopsphere.etl.validate")


@dataclass
class TableValidationResult:
    """Valid rows, rejected rows, and rule-level failure counts."""

    table_name: str
    valid: pd.DataFrame
    rejected: pd.DataFrame
    rule_failures: dict[str, int] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        return len(self.valid) + len(self.rejected)

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def quality_score(self) -> float:
        if self.total_count == 0:
            return 0.0
        return (self.valid_count / self.total_count) * 100.0


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def _parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", format="mixed")


def _parse_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _normalize_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.upper()


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


def _mark_reject(
    reject_flags: pd.Series,
    reject_rules: pd.Series,
    reject_reasons: pd.Series,
    mask: pd.Series,
    rule: str,
    reason: str,
) -> None:
    """Keep the first failing rule for each row."""
    new_hits = mask & ~reject_flags
    reject_flags.loc[new_hits] = True
    reject_rules.loc[new_hits] = rule
    reject_reasons.loc[new_hits] = reason


def _split_result(
    table_name: str,
    df: pd.DataFrame,
    reject_flags: pd.Series,
    reject_rules: pd.Series,
    reject_reasons: pd.Series,
    id_column: str,
    rule_failures: dict[str, int],
) -> TableValidationResult:
    rejected = df.loc[reject_flags].copy()
    valid = df.loc[~reject_flags].copy()

    if not rejected.empty:
        rejected = rejected.copy()
        rejected["failed_rule"] = reject_rules.loc[reject_flags].values
        rejected["rejection_reason"] = reject_reasons.loc[reject_flags].values
        if id_column in rejected.columns:
            rejected["record_identifier"] = rejected[id_column].astype(str)
        else:
            rejected["record_identifier"] = rejected.index.astype(str)

    logger.info(
        "%s validation: valid=%s rejected=%s quality=%.2f%%",
        table_name,
        len(valid),
        len(rejected),
        (len(valid) / len(df) * 100.0) if len(df) else 0.0,
    )
    return TableValidationResult(
        table_name=table_name,
        valid=valid.reset_index(drop=True),
        rejected=rejected.reset_index(drop=True),
        rule_failures=rule_failures,
    )


def _count_rule(rule_failures: dict[str, int], rule: str, mask: pd.Series) -> None:
    failed = int(mask.sum())
    if failed:
        rule_failures[rule] = rule_failures.get(rule, 0) + failed


def validate_customers(df: pd.DataFrame) -> TableValidationResult:
    work = df.copy()
    n = len(work)
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["customer_id"] = _normalize_text(work["customer_id"])
    work["email"] = _normalize_text(work["email"])
    work["phone"] = _normalize_text(work["phone"])
    work["city"] = _normalize_text(work["city"])
    work["state"] = _normalize_text(work["state"])
    work["country"] = _normalize_text(work["country"])
    work["customer_segment"] = _normalize_code(work["customer_segment"])
    work["first_name"] = _normalize_text(work["first_name"])
    work["last_name"] = _normalize_text(work["last_name"])

    mask = _blank_mask(work["customer_id"])
    _count_rule(rules, "required_customer_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_customer_id", "customer_id is missing")

    dup = work["customer_id"].duplicated(keep="first") & ~_blank_mask(work["customer_id"])
    _count_rule(rules, "duplicate_customer_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_customer_id", "duplicate customer_id")

    mask = _blank_mask(work["email"])
    _count_rule(rules, "required_email", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_email", "email is missing")

    mask = ~_blank_mask(work["email"]) & ~work["email"].str.contains("@", regex=False)
    _count_rule(rules, "invalid_email_format", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_email_format", "email must contain @")

    dates = _parse_dates(work["signup_date"])
    mask = dates.isna()
    _count_rule(rules, "invalid_signup_date", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_signup_date", "signup_date is not a valid date")
    work["signup_date"] = dates.dt.date

    blank_seg = _blank_mask(work["customer_segment"])
    mask = blank_seg | ~work["customer_segment"].isin(VALID_CUSTOMER_SEGMENTS)
    _count_rule(rules, "invalid_customer_segment", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "invalid_customer_segment",
        "customer_segment is missing or not in the allowed set",
    )

    return _split_result("customers", work, reject_flags, reject_rules, reject_reasons, "customer_id", rules)


def validate_products(df: pd.DataFrame) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["product_id"] = _normalize_text(work["product_id"])
    work["product_name"] = _normalize_text(work["product_name"])
    work["category"] = _normalize_text(work["category"])
    work["subcategory"] = _normalize_text(work["subcategory"])
    work["brand"] = _normalize_text(work["brand"])
    work["supplier"] = _normalize_text(work["supplier"])

    mask = _blank_mask(work["product_id"])
    _count_rule(rules, "required_product_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_product_id", "product_id is missing")

    dup = work["product_id"].duplicated(keep="first") & ~_blank_mask(work["product_id"])
    _count_rule(rules, "duplicate_product_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_product_id", "duplicate product_id")

    mask = _blank_mask(work["product_name"])
    _count_rule(rules, "required_product_name", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_product_name", "product_name is missing")

    mask = _blank_mask(work["category"])
    _count_rule(rules, "required_category", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_category", "category is missing")

    unit_cost = _parse_numeric(work["unit_cost"])
    selling_price = _parse_numeric(work["selling_price"])
    rating = _parse_numeric(work["product_rating"])

    mask = unit_cost.isna()
    _count_rule(rules, "invalid_unit_cost", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_unit_cost", "unit_cost is not numeric")

    mask = selling_price.isna()
    _count_rule(rules, "invalid_selling_price", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_selling_price", "selling_price is not numeric")

    mask = unit_cost.notna() & (unit_cost < 0)
    _count_rule(rules, "negative_unit_cost", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "negative_unit_cost", "unit_cost must be >= 0")

    mask = selling_price.notna() & (selling_price < 0)
    _count_rule(rules, "negative_selling_price", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "negative_selling_price", "selling_price must be >= 0")

    mask = unit_cost.notna() & selling_price.notna() & (unit_cost > selling_price)
    _count_rule(rules, "unit_cost_exceeds_selling_price", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "unit_cost_exceeds_selling_price",
        "unit_cost must be <= selling_price",
    )

    mask = rating.isna() | (rating < 0) | (rating > 5)
    _count_rule(rules, "invalid_product_rating", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "invalid_product_rating",
        "product_rating must be a number between 0 and 5",
    )

    work["unit_cost"] = unit_cost
    work["selling_price"] = selling_price
    work["product_rating"] = rating

    return _split_result("products", work, reject_flags, reject_rules, reject_reasons, "product_id", rules)


def validate_stores(df: pd.DataFrame) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["store_id"] = _normalize_text(work["store_id"])
    work["store_name"] = _normalize_text(work["store_name"])
    work["store_type"] = _normalize_code(work["store_type"])
    work["country"] = _normalize_text(work["country"])
    work["region"] = _normalize_text(work["region"])
    work["city"] = _normalize_text(work["city"])

    mask = _blank_mask(work["store_id"])
    _count_rule(rules, "required_store_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_store_id", "store_id is missing")

    dup = work["store_id"].duplicated(keep="first") & ~_blank_mask(work["store_id"])
    _count_rule(rules, "duplicate_store_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_store_id", "duplicate store_id")

    mask = ~work["store_type"].isin(VALID_STORE_TYPES)
    _count_rule(rules, "invalid_store_type", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_store_type", "store_type is invalid")

    lat = _parse_numeric(work["latitude"])
    lon = _parse_numeric(work["longitude"])
    mask = lat.isna() | (lat < -90) | (lat > 90)
    _count_rule(rules, "invalid_latitude", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_latitude", "latitude must be between -90 and 90")

    mask = lon.isna() | (lon < -180) | (lon > 180)
    _count_rule(rules, "invalid_longitude", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_longitude", "longitude must be between -180 and 180")

    opening = _parse_dates(work["opening_date"])
    mask = opening.isna()
    _count_rule(rules, "invalid_opening_date", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_opening_date", "opening_date is not a valid date")

    work["latitude"] = lat
    work["longitude"] = lon
    # Full-column assign: partial .loc into a pandas string dtype rejects datetime.date.
    work["opening_date"] = opening.dt.date

    return _split_result("stores", work, reject_flags, reject_rules, reject_reasons, "store_id", rules)


def validate_orders(
    df: pd.DataFrame,
    valid_customer_ids: set[str],
    valid_store_ids: set[str],
) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["order_id"] = _normalize_text(work["order_id"])
    work["customer_id"] = _normalize_text(work["customer_id"])
    work["store_id"] = _normalize_text(work["store_id"])
    work["sales_channel"] = _normalize_code(work["sales_channel"])
    work["order_status"] = _normalize_code(work["order_status"])
    work["currency"] = _normalize_code(work["currency"])

    mask = _blank_mask(work["order_id"])
    _count_rule(rules, "required_order_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_order_id", "order_id is missing")

    dup = work["order_id"].duplicated(keep="first") & ~_blank_mask(work["order_id"])
    _count_rule(rules, "duplicate_order_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_order_id", "duplicate order_id")

    order_dates = _parse_dates(work["order_date"])
    mask = order_dates.isna()
    _count_rule(rules, "invalid_order_date", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_order_date", "order_date is not a valid date")

    mask = ~work["sales_channel"].isin(VALID_CHANNELS)
    _count_rule(rules, "invalid_sales_channel", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_sales_channel", "sales_channel is invalid")

    mask = ~work["order_status"].isin(VALID_ORDER_STATUSES)
    _count_rule(rules, "invalid_order_status", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_order_status", "order_status is invalid")

    mask = ~work["currency"].isin(VALID_CURRENCIES)
    _count_rule(rules, "invalid_currency", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_currency", "currency code is invalid")

    totals = _parse_numeric(work["order_total"])
    mask = totals.isna() | (totals < 0)
    _count_rule(rules, "invalid_order_total", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_order_total", "order_total must be a number >= 0")

    mask = ~work["customer_id"].isin(valid_customer_ids)
    _count_rule(rules, "orphan_customer_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_customer_id", "customer_id not found in valid customers")

    mask = ~work["store_id"].isin(valid_store_ids)
    _count_rule(rules, "orphan_store_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_store_id", "store_id not found in valid stores")

    work["order_total"] = totals
    work["order_date"] = order_dates.dt.date

    return _split_result("orders", work, reject_flags, reject_rules, reject_reasons, "order_id", rules)


def validate_order_items(
    df: pd.DataFrame,
    valid_order_ids: set[str],
    valid_product_ids: set[str],
) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["order_item_id"] = _normalize_text(work["order_item_id"])
    work["order_id"] = _normalize_text(work["order_id"])
    work["product_id"] = _normalize_text(work["product_id"])

    mask = _blank_mask(work["order_item_id"])
    _count_rule(rules, "required_order_item_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_order_item_id", "order_item_id is missing")

    dup = work["order_item_id"].duplicated(keep="first") & ~_blank_mask(work["order_item_id"])
    _count_rule(rules, "duplicate_order_item_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_order_item_id", "duplicate order_item_id")

    qty = _parse_numeric(work["quantity"])
    price = _parse_numeric(work["unit_price"])
    discount = _parse_numeric(work["discount_percent"])

    mask = qty.isna() | (qty <= 0) | (qty != qty.round(0))
    _count_rule(rules, "invalid_quantity", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_quantity", "quantity must be an integer > 0")

    mask = price.isna() | (price < 0)
    _count_rule(rules, "invalid_unit_price", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_unit_price", "unit_price must be a number >= 0")

    mask = discount.isna() | (discount < 0) | (discount > 100)
    _count_rule(rules, "invalid_discount_percent", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "invalid_discount_percent",
        "discount_percent must be between 0 and 100",
    )

    mask = ~work["order_id"].isin(valid_order_ids)
    _count_rule(rules, "orphan_order_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_order_id", "order_id not found in valid orders")

    mask = ~work["product_id"].isin(valid_product_ids)
    _count_rule(rules, "orphan_product_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_product_id", "product_id not found in valid products")

    work["quantity"] = qty.round().astype("Int64")
    work["unit_price"] = price
    work["discount_percent"] = discount

    return _split_result("order_items", work, reject_flags, reject_rules, reject_reasons, "order_item_id", rules)


def validate_payments(df: pd.DataFrame, valid_order_ids: set[str]) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["payment_id"] = _normalize_text(work["payment_id"])
    work["order_id"] = _normalize_text(work["order_id"])
    work["payment_method"] = _normalize_code(work["payment_method"])
    work["payment_status"] = _normalize_code(work["payment_status"])
    work["currency"] = _normalize_code(work["currency"])

    mask = _blank_mask(work["payment_id"])
    _count_rule(rules, "required_payment_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_payment_id", "payment_id is missing")

    dup = work["payment_id"].duplicated(keep="first") & ~_blank_mask(work["payment_id"])
    _count_rule(rules, "duplicate_payment_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_payment_id", "duplicate payment_id")

    mask = ~work["payment_method"].isin(VALID_PAYMENT_METHODS)
    _count_rule(rules, "invalid_payment_method", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_payment_method", "payment_method is invalid")

    mask = ~work["payment_status"].isin(VALID_PAYMENT_STATUSES)
    _count_rule(rules, "invalid_payment_status", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_payment_status", "payment_status is invalid")

    amount = _parse_numeric(work["payment_amount"])
    mask = amount.isna() | (amount < 0)
    _count_rule(rules, "invalid_payment_amount", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_payment_amount", "payment_amount must be >= 0")

    pay_dates = _parse_dates(work["payment_date"])
    mask = pay_dates.isna()
    _count_rule(rules, "invalid_payment_date", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_payment_date", "payment_date is not a valid date")

    mask = ~work["currency"].isin(VALID_CURRENCIES)
    _count_rule(rules, "invalid_currency", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_currency", "currency code is invalid")

    mask = ~work["order_id"].isin(valid_order_ids)
    _count_rule(rules, "orphan_order_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_order_id", "order_id not found in valid orders")

    work["payment_amount"] = amount
    work["payment_date"] = pay_dates.dt.date

    return _split_result("payments", work, reject_flags, reject_rules, reject_reasons, "payment_id", rules)


def validate_deliveries(
    df: pd.DataFrame,
    valid_order_ids: set[str],
    valid_store_ids: set[str],
) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["delivery_id"] = _normalize_text(work["delivery_id"])
    work["order_id"] = _normalize_text(work["order_id"])
    work["store_id"] = _normalize_text(work["store_id"])
    work["delivery_type"] = _normalize_code(work["delivery_type"])
    work["delivery_status"] = _normalize_code(work["delivery_status"])

    mask = _blank_mask(work["delivery_id"])
    _count_rule(rules, "required_delivery_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "required_delivery_id", "delivery_id is missing")

    dup = work["delivery_id"].duplicated(keep="first") & ~_blank_mask(work["delivery_id"])
    _count_rule(rules, "duplicate_delivery_id", dup)
    _mark_reject(reject_flags, reject_rules, reject_reasons, dup, "duplicate_delivery_id", "duplicate delivery_id")

    mask = ~work["delivery_type"].isin(VALID_DELIVERY_TYPES)
    _count_rule(rules, "invalid_delivery_type", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_delivery_type", "delivery_type is invalid")

    mask = ~work["delivery_status"].isin(VALID_DELIVERY_STATUSES)
    _count_rule(rules, "invalid_delivery_status", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_delivery_status", "delivery_status is invalid")

    distance = _parse_numeric(work["delivery_distance_km"])
    minutes = _parse_numeric(work["delivery_time_minutes"])
    fee = _parse_numeric(work["delivery_fee"])

    mask = distance.isna() | (distance < 0)
    _count_rule(rules, "invalid_delivery_distance", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "invalid_delivery_distance",
        "delivery_distance_km must be >= 0",
    )

    mask = minutes.isna() | (minutes < 0) | (minutes > 200000)
    _count_rule(rules, "invalid_delivery_time", mask)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        mask,
        "invalid_delivery_time",
        "delivery_time_minutes must be a realistic non-negative number",
    )

    mask = fee.isna() | (fee < 0)
    _count_rule(rules, "invalid_delivery_fee", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_delivery_fee", "delivery_fee must be >= 0")

    mask = ~work["order_id"].isin(valid_order_ids)
    _count_rule(rules, "orphan_order_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_order_id", "order_id not found in valid orders")

    mask = ~work["store_id"].isin(valid_store_ids)
    _count_rule(rules, "orphan_store_id", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "orphan_store_id", "store_id not found in valid stores")

    work["delivery_distance_km"] = distance
    work["delivery_time_minutes"] = minutes.round().astype("Int64")
    work["delivery_fee"] = fee

    return _split_result("deliveries", work, reject_flags, reject_rules, reject_reasons, "delivery_id", rules)


def validate_exchange_rates(df: pd.DataFrame) -> TableValidationResult:
    work = df.copy()
    reject_flags = pd.Series(False, index=work.index)
    reject_rules = pd.Series("", index=work.index, dtype=object)
    reject_reasons = pd.Series("", index=work.index, dtype=object)
    rules: dict[str, int] = {}

    work["currency_code"] = _normalize_code(work["currency_code"])
    rate_dates = _parse_dates(work["rate_date"])
    rates = _parse_numeric(work["rate_to_inr"])

    mask = rate_dates.isna()
    _count_rule(rules, "invalid_rate_date", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_rate_date", "rate_date is not a valid date")

    mask = ~work["currency_code"].isin(VALID_CURRENCIES)
    _count_rule(rules, "invalid_currency_code", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_currency_code", "currency_code is invalid")

    mask = rates.isna() | (rates <= 0)
    _count_rule(rules, "invalid_rate_to_inr", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_rate_to_inr", "rate_to_inr must be > 0")

    # INR must be 1 when present and valid enough to parse
    mask = (work["currency_code"] == "INR") & rates.notna() & (rates != 1)
    _count_rule(rules, "invalid_inr_rate", mask)
    _mark_reject(reject_flags, reject_rules, reject_reasons, mask, "invalid_inr_rate", "INR rate_to_inr must equal 1")

    key = work["currency_code"] + "|" + rate_dates.dt.strftime("%Y-%m-%d").fillna("")
    dup = key.duplicated(keep="first") & ~rate_dates.isna()
    _count_rule(rules, "duplicate_exchange_rate", dup)
    _mark_reject(
        reject_flags,
        reject_rules,
        reject_reasons,
        dup,
        "duplicate_exchange_rate",
        "duplicate currency_code + rate_date",
    )

    work["rate_to_inr"] = rates
    work["rate_date"] = rate_dates.dt.date
    work["record_identifier"] = key

    result = _split_result(
        "exchange_rates",
        work.drop(columns=["record_identifier"], errors="ignore"),
        reject_flags,
        reject_rules,
        reject_reasons,
        "currency_code",
        rules,
    )
    # Prefer composite identifier on rejects
    if not result.rejected.empty:
        result.rejected["record_identifier"] = (
            result.rejected["currency_code"].astype(str)
            + "|"
            + result.rejected["rate_date"].astype(str)
        )
    return result


def validate_all(extracted: dict[str, pd.DataFrame]) -> dict[str, TableValidationResult]:
    """Validate tables in dependency order and return per-table results."""
    customers = validate_customers(extracted["customers"])
    products = validate_products(extracted["products"])
    stores = validate_stores(extracted["stores"])

    valid_customer_ids = set(customers.valid["customer_id"].astype(str))
    valid_product_ids = set(products.valid["product_id"].astype(str))
    valid_store_ids = set(stores.valid["store_id"].astype(str))

    orders = validate_orders(extracted["orders"], valid_customer_ids, valid_store_ids)
    valid_order_ids = set(orders.valid["order_id"].astype(str))

    order_items = validate_order_items(extracted["order_items"], valid_order_ids, valid_product_ids)
    payments = validate_payments(extracted["payments"], valid_order_ids)
    deliveries = validate_deliveries(extracted["deliveries"], valid_order_ids, valid_store_ids)
    exchange_rates = validate_exchange_rates(extracted["exchange_rates"])

    return {
        "customers": customers,
        "products": products,
        "stores": stores,
        "orders": orders,
        "order_items": order_items,
        "payments": payments,
        "deliveries": deliveries,
        "exchange_rates": exchange_rates,
    }


def evaluate_quality_gate(
    results: dict[str, TableValidationResult],
    threshold: float,
    required_tables: tuple[str, ...],
) -> tuple[bool, float, list[str]]:
    """Return (passed, overall_score, failure_messages)."""
    total_valid = sum(r.valid_count for r in results.values())
    total_rows = sum(r.total_count for r in results.values())
    overall = (total_valid / total_rows * 100.0) if total_rows else 0.0

    failures: list[str] = []
    for table in required_tables:
        result = results[table]
        score = result.quality_score
        if result.total_count == 0:
            failures.append(f"{table}: no records extracted (quality 0%)")
        elif score < threshold:
            failures.append(
                f"{table}: quality {score:.2f}% is below threshold {threshold:.2f}% "
                f"(valid={result.valid_count}, total={result.total_count})"
            )

    return (len(failures) == 0, overall, failures)
