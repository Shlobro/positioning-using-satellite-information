"""Metric helpers for the Phase 0 smoke pipeline."""

from __future__ import annotations

from typing import Any


def build_smoke_metrics(predictions_count: int) -> dict[str, Any]:
    """Return deterministic metrics for the scaffold smoke run."""
    return {
        "run_status": "success",
        "predictions_count": predictions_count,
        "mean_position_error_m": 0.0,
        "median_position_error_m": 0.0,
        "p90_position_error_m": 0.0,
    }
