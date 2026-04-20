"""CLI entry point for repository smoke runs."""

from __future__ import annotations

from pathlib import Path
import argparse

from .smoke_pipeline import run_smoke


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser."""
    parser = argparse.ArgumentParser(description="Run the Phase 0 smoke scaffold.")
    parser.add_argument(
        "--config",
        default="configs/eval/run_000.json",
        help="Path to the smoke run config file relative to the repository root.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional repository root override. Defaults to the current working directory.",
    )
    return parser


def main() -> int:
    """Run the smoke pipeline from the command line."""
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path

    result = run_smoke(config_path=config_path, repo_root=repo_root)
    print(f"Created {result.run_id} in {result.run_directory}")
    print(f"Metrics: {result.metrics_path}")
    print(f"Predictions: {result.predictions_path}")
    print(f"Overlay: {result.overlay_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
