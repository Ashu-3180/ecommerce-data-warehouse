"""CLI entry point: python -m src.etl"""

from __future__ import annotations

import sys

from src.etl.pipeline import main

if __name__ == "__main__":
    sys.exit(main())
