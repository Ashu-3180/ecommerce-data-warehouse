"""Shared constants and lookup sets for the ShopSphere ETL."""

from __future__ import annotations

SOURCE_TABLES: tuple[str, ...] = (
    "customers",
    "products",
    "stores",
    "orders",
    "order_items",
    "payments",
    "deliveries",
    "exchange_rates",
)

# Tables that must pass QUALITY_THRESHOLD before warehouse load.
REQUIRED_QUALITY_TABLES: tuple[str, ...] = SOURCE_TABLES

VALID_ORDER_STATUSES = frozenset(
    {
        "PENDING",
        "CONFIRMED",
        "PROCESSING",
        "SHIPPED",
        "DELIVERED",
        "CANCELLED",
        "RETURNED",
    }
)

VALID_PAYMENT_STATUSES = frozenset({"SUCCESS", "FAILED", "PENDING", "REFUNDED"})

VALID_PAYMENT_METHODS = frozenset(
    {
        "CREDIT_CARD",
        "DEBIT_CARD",
        "UPI",
        "NET_BANKING",
        "WALLET",
        "CASH",
        "PAYPAL",
    }
)

VALID_DELIVERY_TYPES = frozenset({"STANDARD", "EXPRESS", "QUICK"})
VALID_DELIVERY_STATUSES = frozenset(
    {"ASSIGNED", "IN_TRANSIT", "DELIVERED", "FAILED", "CANCELLED"}
)

VALID_STORE_TYPES = frozenset({"RETAIL_STORE", "DARK_STORE", "FULFILLMENT_CENTER"})

VALID_CHANNELS = frozenset(
    {"WEBSITE", "MOBILE_APP", "PHYSICAL_STORE", "QUICK_COMMERCE"}
)

VALID_CURRENCIES = frozenset(
    {
        "INR",
        "USD",
        "GBP",
        "EUR",
        "AED",
        "SGD",
        "AUD",
        "CAD",
        "JPY",
        "SAR",
        "MYR",
        "NZD",
    }
)

VALID_CUSTOMER_SEGMENTS = frozenset(
    {"NEW", "REGULAR", "PREMIUM", "VIP", "WHOLESALE"}
)

CHANNEL_KEY_BY_CODE = {
    "WEBSITE": 1,
    "MOBILE_APP": 2,
    "PHYSICAL_STORE": 3,
    "QUICK_COMMERCE": 4,
}

CURRENCY_KEY_BY_CODE = {
    "INR": 1,
    "USD": 2,
    "GBP": 3,
    "EUR": 4,
    "AED": 5,
    "SGD": 6,
    "AUD": 7,
    "CAD": 8,
    "JPY": 9,
    "SAR": 10,
    "MYR": 11,
    "NZD": 12,
}

PAYMENT_METHOD_KEY_BY_CODE = {
    "CREDIT_CARD": 1,
    "DEBIT_CARD": 2,
    "UPI": 3,
    "NET_BANKING": 4,
    "WALLET": 5,
    "CASH": 6,
    "PAYPAL": 7,
}

REJECT_METADATA_COLUMNS = (
    "pipeline_run_id",
    "source_table",
    "record_identifier",
    "rejection_reason",
    "failed_rule",
)
