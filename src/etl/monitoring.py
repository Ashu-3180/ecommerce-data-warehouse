"""Monitoring helpers for monitoring.pipeline_runs and data_quality_results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.etl.validate import TableValidationResult

logger = logging.getLogger("shopsphere.etl.monitoring")


def start_pipeline_run(engine: Engine, pipeline_name: str) -> int:
    """Insert a RUNNING row and return run_id."""
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                """
                INSERT INTO monitoring.pipeline_runs (pipeline_name, started_at, status)
                VALUES (:pipeline_name, :started_at, 'RUNNING')
                RETURNING run_id
                """
            ),
            {
                "pipeline_name": pipeline_name,
                "started_at": datetime.now(timezone.utc),
            },
        ).scalar_one()
    logger.info("Started pipeline run_id=%s (%s)", run_id, pipeline_name)
    return int(run_id)


def finish_pipeline_run(
    engine: Engine,
    run_id: int,
    *,
    status: str,
    records_extracted: int | None = None,
    records_validated: int | None = None,
    records_rejected: int | None = None,
    records_loaded: int | None = None,
    quality_score: float | None = None,
    error_message: str | None = None,
) -> None:
    """Update the monitoring row when a run completes or fails."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE monitoring.pipeline_runs
                SET completed_at = :completed_at,
                    status = :status,
                    records_extracted = :records_extracted,
                    records_validated = :records_validated,
                    records_rejected = :records_rejected,
                    records_loaded = :records_loaded,
                    quality_score = :quality_score,
                    error_message = :error_message
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "completed_at": datetime.now(timezone.utc),
                "status": status,
                "records_extracted": records_extracted,
                "records_validated": records_validated,
                "records_rejected": records_rejected,
                "records_loaded": records_loaded,
                "quality_score": quality_score,
                "error_message": error_message,
            },
        )
    logger.info("Finished pipeline run_id=%s status=%s", run_id, status)


def record_data_quality_results(
    engine: Engine,
    run_id: int,
    results: dict[str, TableValidationResult],
) -> None:
    """Insert per-rule quality metrics for the run."""
    rows: list[dict[str, Any]] = []
    for table_name, result in results.items():
        for rule_name, failed in result.rule_failures.items():
            checked = result.total_count
            failure_rate = (failed / checked) if checked else None
            rows.append(
                {
                    "run_id": run_id,
                    "table_name": table_name,
                    "rule_name": rule_name,
                    "records_checked": checked,
                    "records_failed": failed,
                    "failure_rate": failure_rate,
                }
            )
        # Always store an overall table summary rule.
        rows.append(
            {
                "run_id": run_id,
                "table_name": table_name,
                "rule_name": "overall_table_quality",
                "records_checked": result.total_count,
                "records_failed": result.rejected_count,
                "failure_rate": (result.rejected_count / result.total_count)
                if result.total_count
                else None,
            }
        )

    if not rows:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO monitoring.data_quality_results (
                    run_id, table_name, rule_name, records_checked, records_failed, failure_rate
                ) VALUES (
                    :run_id, :table_name, :rule_name, :records_checked, :records_failed, :failure_rate
                )
                """
            ),
            rows,
        )
    logger.info("Recorded %s data-quality result rows for run_id=%s", len(rows), run_id)


def ensure_quality_score_column(conn: Connection) -> None:
    """Add quality_score if an older database is missing the column."""
    conn.execute(
        text(
            """
            ALTER TABLE monitoring.pipeline_runs
            ADD COLUMN IF NOT EXISTS quality_score NUMERIC(5, 2)
            """
        )
    )
