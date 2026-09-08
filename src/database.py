"""PostgreSQL connectivity for ShopSphere.

Credentials come from environment variables (see .env.example).
Nothing in this module creates, drops, or alters database objects.

Run a connection test from the project root:

    python -m src.database
    python src/database.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import (  # noqa: E402
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)


def get_database_url() -> str:
    """Build a SQLAlchemy URL for PostgreSQL using psycopg (v3)."""
    if not POSTGRES_USER:
        raise ValueError("POSTGRES_USER is not set.")
    if not POSTGRES_DB:
        raise ValueError("POSTGRES_DB is not set.")
    if not POSTGRES_PASSWORD:
        raise ValueError(
            "POSTGRES_PASSWORD is not set. Copy .env.example to .env and set your local password."
        )

    user = quote_plus(POSTGRES_USER)
    password = quote_plus(POSTGRES_PASSWORD)
    host = POSTGRES_HOST
    port = POSTGRES_PORT
    database = POSTGRES_DB
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def get_engine(echo: bool = False) -> Engine:
    """Return a SQLAlchemy engine for the ShopSphere database."""
    return create_engine(
        get_database_url(),
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


def test_connection() -> None:
    """Connect, run SELECT 1, and print a short success or failure message."""
    print(f"Connecting to {POSTGRES_HOST}:{POSTGRES_PORT} database '{POSTGRES_DB}' as '{POSTGRES_USER}'...")
    engine = get_engine()
    try:
        with engine.connect() as connection:
            one = connection.execute(text("SELECT 1")).scalar_one()
            version = connection.execute(text("SELECT version()")).scalar_one()
            current_db = connection.execute(text("SELECT current_database()")).scalar_one()
            current_user = connection.execute(text("SELECT current_user")).scalar_one()
        print("Connection successful.")
        print(f"SELECT 1 returned: {one}")
        print(f"Database: {current_db}")
        print(f"User: {current_user}")
        print(f"Server: {version}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        test_connection()
    except Exception as exc:
        print(f"Connection failed: {exc}")
        sys.exit(1)
