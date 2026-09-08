"""ShopSphere project configuration.

Runtime dataset sizes come from environment variables (or a local .env file)
so you can generate a small development extract without changing generator logic.

TARGET_* constants document the final portfolio scale. They are reference values
only and are not used unless you set the matching environment variables.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to default."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to default."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _env_date(name: str, default: date) -> date:
    """Read an ISO date (YYYY-MM-DD) environment variable."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return date.fromisoformat(value.strip())


def _env_path(name: str, default: Path) -> Path:
    """Read a filesystem path from the environment."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return Path(value)


# ---------------------------------------------------------------------------
# Final target scale (documentation / future full runs)
# ---------------------------------------------------------------------------
TARGET_NUM_CUSTOMERS = 50_000
TARGET_NUM_PRODUCTS = 10_000
TARGET_NUM_STORES = 250
TARGET_NUM_ORDERS = 500_000
# Approximately 1.5 million items when AVG_ITEMS_PER_ORDER is about 3.
TARGET_APPROX_ORDER_ITEMS = 1_500_000
TARGET_APPROX_PAYMENTS = 500_000
TARGET_APPROX_DELIVERIES = 400_000

# ---------------------------------------------------------------------------
# Development defaults — small enough to generate in a few seconds
# Override any of these in .env without editing generate_data.py
# ---------------------------------------------------------------------------
NUM_CUSTOMERS = _env_int("NUM_CUSTOMERS", 500)
NUM_PRODUCTS = _env_int("NUM_PRODUCTS", 200)
NUM_STORES = _env_int("NUM_STORES", 30)
NUM_ORDERS = _env_int("NUM_ORDERS", 1_000)
AVG_ITEMS_PER_ORDER = _env_float("AVG_ITEMS_PER_ORDER", 3.0)
MAX_ITEMS_PER_ORDER = _env_int("MAX_ITEMS_PER_ORDER", 12)

RANDOM_SEED = _env_int("RANDOM_SEED", 42)

# Roughly 2–3% of records receive data-quality problems.
DIRTY_DATA_RATE = _env_float("DIRTY_DATA_RATE", 0.025)

HISTORICAL_START_DATE = _env_date("HISTORICAL_START_DATE", date(2023, 1, 1))
HISTORICAL_END_DATE = _env_date("HISTORICAL_END_DATE", date(2025, 12, 31))

RAW_DATA_DIR = _env_path("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw")
REJECTED_DATA_DIR = _env_path("REJECTED_DATA_DIR", PROJECT_ROOT / "data" / "rejected")
LOG_DIR = _env_path("LOG_DIR", PROJECT_ROOT / "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# ETL / data-quality settings
# ---------------------------------------------------------------------------
# Minimum valid_records / total_records * 100 required per source table.
# Below this threshold the run fails and warehouse loading is skipped.
QUALITY_THRESHOLD = _env_float("QUALITY_THRESHOLD", 95.0)
PIPELINE_NAME = os.getenv("PIPELINE_NAME", "shopsphere_batch_etl")

# ---------------------------------------------------------------------------
# PostgreSQL (used by src/database.py and the ETL pipeline)
# Do not put real passwords in this file. Set them in a local .env instead.
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = _env_int("POSTGRES_PORT", 5432)
POSTGRES_DB = os.getenv("POSTGRES_DB", "shopsphere")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
