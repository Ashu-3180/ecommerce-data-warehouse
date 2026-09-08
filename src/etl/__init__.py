"""ShopSphere batch ETL package.

Run from the project root:

    python -m src.etl
"""

from __future__ import annotations

__all__ = ["run_pipeline"]


def run_pipeline() -> int:
    """Execute the full batch ETL and return a process exit code."""
    from src.etl.pipeline import main

    return main()
