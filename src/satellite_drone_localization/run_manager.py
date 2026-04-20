"""Run artifact management for reproducible evaluations."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunPaths:
    """Resolved output paths for a single run."""

    root: Path
    plots_dir: Path
    overlays_dir: Path
    config_snapshot_path: Path
    metrics_path: Path
    predictions_path: Path
    log_path: Path


class RunManager:
    """Create and populate the standard artifact layout for a run."""

    def __init__(self, artifacts_root: Path) -> None:
        self._artifacts_root = artifacts_root

    def prepare_run(self, run_id: str) -> RunPaths:
        run_root = self._artifacts_root / "runs" / run_id
        plots_dir = run_root / "plots"
        overlays_dir = run_root / "overlays"
        for directory in (plots_dir, overlays_dir):
            directory.mkdir(parents=True, exist_ok=True)

        return RunPaths(
            root=run_root,
            plots_dir=plots_dir,
            overlays_dir=overlays_dir,
            config_snapshot_path=run_root / "config_snapshot.yaml",
            metrics_path=run_root / "metrics.json",
            predictions_path=run_root / "predictions.csv",
            log_path=run_root / "run.log",
        )

    def write_config_snapshot(self, path: Path, config: dict[str, Any]) -> None:
        lines = [f"{key}: {self._yaml_scalar(value)}" for key, value in config.items()]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_metrics(self, path: Path, metrics: dict[str, Any]) -> None:
        path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    def write_predictions(self, path: Path, predictions: list[dict[str, Any]]) -> None:
        if not predictions:
            raise ValueError("predictions must not be empty")

        fieldnames = list(predictions[0].keys())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(predictions)

    def write_log(self, path: Path, lines: list[str]) -> None:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_overlay_plot(self, path: Path, title: str, prior_xy: tuple[int, int], estimate_xy: tuple[int, int]) -> None:
        content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220" viewBox="0 0 320 220">
  <rect width="320" height="220" fill="#f5f1e8"/>
  <text x="20" y="28" font-family="monospace" font-size="18" fill="#1f2933">{title}</text>
  <rect x="40" y="50" width="240" height="140" fill="#dde7c7" stroke="#50623a" stroke-width="2"/>
  <circle cx="{prior_xy[0]}" cy="{prior_xy[1]}" r="8" fill="#0f4c5c"/>
  <circle cx="{estimate_xy[0]}" cy="{estimate_xy[1]}" r="8" fill="#c05621"/>
  <line x1="{prior_xy[0]}" y1="{prior_xy[1]}" x2="{estimate_xy[0]}" y2="{estimate_xy[1]}" stroke="#7d4e57" stroke-width="3"/>
  <text x="50" y="210" font-family="monospace" font-size="14" fill="#1f2933">blue=prior orange=estimate</text>
</svg>
"""
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _yaml_scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return f'"{value}"'
