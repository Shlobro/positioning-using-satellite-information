"""Deterministic Phase 0 smoke pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from .metrics import build_smoke_metrics
from .run_manager import RunManager


@dataclass(frozen=True)
class SmokeRunResult:
    """Summary of a completed smoke run."""

    run_id: str
    run_directory: Path
    metrics_path: Path
    predictions_path: Path
    overlay_path: Path


def load_config(config_path: Path) -> dict[str, object]:
    """Load a JSON config file for the smoke run."""
    return json.loads(config_path.read_text(encoding="utf-8"))


def run_smoke(config_path: Path, repo_root: Path) -> SmokeRunResult:
    """Execute the deterministic smoke run and materialize artifacts."""
    config = load_config(config_path)
    run_id = str(config["run_id"])
    manager = RunManager(repo_root / "artifacts")
    paths = manager.prepare_run(run_id)

    predictions = [
        {
            "frame_id": "frame-000",
            "latitude": 32.0853,
            "longitude": 34.7818,
            "confidence_m": 5.0,
            "match_score": 1.0,
            "localization_status": "ok",
        }
    ]
    metrics = build_smoke_metrics(predictions_count=len(predictions))

    manager.write_config_snapshot(paths.config_snapshot_path, config)
    manager.write_metrics(paths.metrics_path, metrics)
    manager.write_predictions(paths.predictions_path, predictions)
    manager.write_log(
        paths.log_path,
        [
            f"run_id={run_id}",
            "phase=0",
            "status=success",
            "note=deterministic smoke scaffold completed",
        ],
    )
    overlay_path = paths.overlays_dir / "smoke_alignment.svg"
    manager.write_overlay_plot(
        overlay_path,
        title="RUN-000 Smoke Alignment",
        prior_xy=(120, 120),
        estimate_xy=(190, 110),
    )
    return SmokeRunResult(
        run_id=run_id,
        run_directory=paths.root,
        metrics_path=paths.metrics_path,
        predictions_path=paths.predictions_path,
        overlay_path=overlay_path,
    )
