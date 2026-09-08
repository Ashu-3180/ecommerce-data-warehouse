"""Write rejected ETL records to data/rejected/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.config import REJECTED_DATA_DIR
from src.etl.constants import REJECT_METADATA_COLUMNS
from src.etl.validate import TableValidationResult

logger = logging.getLogger("shopsphere.etl.rejects")


def _serialize_original_record(row: pd.Series, exclude: set[str]) -> str:
    payload = {
        key: (None if pd.isna(value) else value)
        for key, value in row.items()
        if key not in exclude
    }
    return json.dumps(payload, default=str)


def write_rejected_records(
    results: dict[str, TableValidationResult],
    pipeline_run_id: int,
    rejected_dir: Path | None = None,
) -> dict[str, Path]:
    """Persist rejected rows as CSV files with rejection metadata."""
    directory = Path(rejected_dir) if rejected_dir is not None else Path(REJECTED_DATA_DIR)
    directory.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    meta_cols = set(REJECT_METADATA_COLUMNS) | {"failed_rule", "rejection_reason", "record_identifier"}

    for table_name, result in results.items():
        path = directory / f"{table_name}_rejected.csv"
        if result.rejected.empty:
            # Always refresh the file so a prior run's rejects are not mistaken for this run.
            empty = pd.DataFrame(
                columns=[
                    "pipeline_run_id",
                    "source_table",
                    "record_identifier",
                    "rejection_reason",
                    "failed_rule",
                    "original_record",
                ]
            )
            empty.to_csv(path, index=False)
            written[table_name] = path
            continue

        out = result.rejected.copy()
        out.insert(0, "pipeline_run_id", pipeline_run_id)
        out.insert(1, "source_table", table_name)
        if "record_identifier" not in out.columns:
            out["record_identifier"] = ""
        out["original_record"] = out.apply(
            lambda row: _serialize_original_record(row, meta_cols | {"original_record"}),
            axis=1,
        )

        export_cols = [
            "pipeline_run_id",
            "source_table",
            "record_identifier",
            "rejection_reason",
            "failed_rule",
            "original_record",
        ]
        # Keep useful business columns after metadata for easier inspection.
        extra_cols = [c for c in out.columns if c not in export_cols and c not in meta_cols]
        out[export_cols + extra_cols].to_csv(path, index=False)
        written[table_name] = path
        logger.info("Wrote %s rejected %s rows to %s", len(result.rejected), table_name, path)

    return written
