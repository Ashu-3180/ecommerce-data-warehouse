"""CSV extraction for ShopSphere source files."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.config import RAW_DATA_DIR
from src.etl.constants import SOURCE_TABLES

logger = logging.getLogger("shopsphere.etl.extract")


def extract_all(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Read all eight source CSVs as strings so dirty values are preserved."""
    directory = Path(raw_dir) if raw_dir is not None else Path(RAW_DATA_DIR)
    if not directory.exists():
        raise FileNotFoundError(f"Raw data directory not found: {directory}")

    frames: dict[str, pd.DataFrame] = {}
    for table in SOURCE_TABLES:
        path = directory / f"{table}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing source CSV: {path}")
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        frames[table] = df
        logger.info("Extracted %s: %s rows from %s", table, len(df), path)

    total = sum(len(df) for df in frames.values())
    logger.info("Extraction complete. Total rows: %s", total)
    return frames
