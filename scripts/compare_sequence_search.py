"""Repository command for sequence-search scenario comparison."""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from satellite_drone_localization.eval.reports.sequence_comparison_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
