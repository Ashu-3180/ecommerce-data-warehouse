"""ShopSphere batch ETL orchestrator.

Stages:
EXTRACT → RAW LOAD → VALIDATE → REJECT INVALID → RECORD DQ → QUALITY GATE
→ STAGE → TRANSFORM → WAREHOUSE LOAD → MONITORING

If the quality gate fails, staging/transform/warehouse load are skipped.
Rejected rows never enter warehouse facts.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from pathlib import Path

# Allow `python -m src.etl` from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import (  # noqa: E402
    PIPELINE_NAME,
    QUALITY_THRESHOLD,
    REJECTED_DATA_DIR,
)
from src.database import get_engine  # noqa: E402
from src.etl.constants import REQUIRED_QUALITY_TABLES  # noqa: E402
from src.etl.extract import extract_all  # noqa: E402
from src.etl.load import (  # noqa: E402
    load_raw_tables,
    load_staging_tables,
    replace_fact_delivery,
    replace_fact_sales,
)
from src.etl.logging_utils import setup_etl_logging  # noqa: E402
from src.etl.monitoring import (  # noqa: E402
    ensure_quality_score_column,
    finish_pipeline_run,
    record_data_quality_results,
    start_pipeline_run,
)
from src.etl.rejects import write_rejected_records  # noqa: E402
from src.etl.transform import (  # noqa: E402
    fact_delivery_for_load,
    fact_sales_for_load,
    load_dimensions,
    transform_all,
)
from src.etl.validate import evaluate_quality_gate, validate_all  # noqa: E402

logger = logging.getLogger("shopsphere.etl")


class QualityGateError(RuntimeError):
    """Raised when one or more required tables fall below QUALITY_THRESHOLD."""


def run_etl() -> int:
    """Run the full batch pipeline. Returns 0 on success, 1 on failure."""
    setup_etl_logging()
    started = time.perf_counter()
    engine = get_engine()
    run_id: int | None = None

    records_extracted = 0
    records_validated = 0
    records_rejected = 0
    records_loaded = 0
    quality_score = 0.0

    try:
        with engine.begin() as conn:
            ensure_quality_score_column(conn)

        run_id = start_pipeline_run(engine, PIPELINE_NAME)
        logger.info(
            "ShopSphere ETL started (run_id=%s, quality_threshold=%.2f)",
            run_id,
            QUALITY_THRESHOLD,
        )

        # 1) EXTRACT
        extracted = extract_all()
        records_extracted = sum(len(df) for df in extracted.values())

        # 2) RAW LOAD (preserves source-oriented dirty data)
        load_raw_tables(engine, extracted)

        # 3) VALIDATE
        results = validate_all(extracted)
        records_validated = sum(r.valid_count for r in results.values())
        records_rejected = sum(r.rejected_count for r in results.values())

        # 4) REJECT INVALID → CSV + monitoring DQ results
        REJECTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_rejected_records(results, pipeline_run_id=run_id)
        record_data_quality_results(engine, run_id, results)

        passed, quality_score, failures = evaluate_quality_gate(
            results,
            threshold=QUALITY_THRESHOLD,
            required_tables=REQUIRED_QUALITY_TABLES,
        )
        logger.info("Overall data-quality score: %.2f%%", quality_score)
        for table, result in results.items():
            logger.info(
                "Quality %-15s valid=%s rejected=%s score=%.2f%%",
                table,
                result.valid_count,
                result.rejected_count,
                result.quality_score,
            )

        if not passed:
            message = "Quality gate failed: " + "; ".join(failures)
            logger.error(message)
            finish_pipeline_run(
                engine,
                run_id,
                status="FAILED",
                records_extracted=records_extracted,
                records_validated=records_validated,
                records_rejected=records_rejected,
                records_loaded=0,
                quality_score=quality_score,
                error_message=message,
            )
            print("\nShopSphere ETL failed quality gate.")
            print(f"Overall quality score: {quality_score:.2f}%")
            for line in failures:
                print(f"  - {line}")
            print(f"Rejected files: {REJECTED_DATA_DIR}")
            return 1

        valid_tables = {name: result.valid for name, result in results.items()}

        # 5) STAGE (validated rows only)
        load_staging_tables(engine, valid_tables)

        # 6) TRANSFORM — upsert dims, resolve surrogate keys, build facts
        logger.info("Transforming validated records for warehouse load")
        dim_lookups = load_dimensions(engine, valid_tables)
        transformed = transform_all(valid_tables, dim_lookups=dim_lookups)
        sales = fact_sales_for_load(transformed["fact_sales"])
        delivery = fact_delivery_for_load(transformed["fact_delivery"])
        logger.info(
            "Transform complete: fact_sales=%s fact_delivery=%s",
            len(sales),
            len(delivery),
        )

        # 7) WAREHOUSE LOAD (idempotent upserts; rejected rows never included)
        records_loaded = (
            len(dim_lookups["dim_customer"])
            + len(dim_lookups["dim_product"])
            + len(dim_lookups["dim_store"])
            + replace_fact_sales(engine, sales)
            + replace_fact_delivery(engine, delivery)
        )

        finish_pipeline_run(
            engine,
            run_id,
            status="SUCCESS",
            records_extracted=records_extracted,
            records_validated=records_validated,
            records_rejected=records_rejected,
            records_loaded=records_loaded,
            quality_score=quality_score,
            error_message=None,
        )

        elapsed = time.perf_counter() - started
        summary = f"""
ShopSphere ETL completed successfully.

Run ID:            {run_id}
Extracted:         {records_extracted:,}
Validated (kept):  {records_validated:,}
Rejected:          {records_rejected:,}
Warehouse loaded:  {records_loaded:,}
Quality score:     {quality_score:.2f}%
Rejected files:    {REJECTED_DATA_DIR}
Duration:          {elapsed:.2f} seconds
"""
        print(summary)
        logger.info("ETL finished successfully in %.2f seconds", elapsed)
        return 0

    except Exception as exc:
        logger.exception("ETL failed")
        if run_id is not None:
            try:
                finish_pipeline_run(
                    engine,
                    run_id,
                    status="FAILED",
                    records_extracted=records_extracted,
                    records_validated=records_validated,
                    records_rejected=records_rejected,
                    records_loaded=records_loaded,
                    quality_score=quality_score,
                    error_message=f"{exc}\n{traceback.format_exc()[-2000:]}",
                )
            except Exception:
                logger.exception("Could not update monitoring row for failed run")
        print(f"\nShopSphere ETL failed: {exc}")
        return 1
    finally:
        engine.dispose()


def main() -> int:
    """CLI entry used by python -m src.etl."""
    return run_etl()


if __name__ == "__main__":
    sys.exit(main())
