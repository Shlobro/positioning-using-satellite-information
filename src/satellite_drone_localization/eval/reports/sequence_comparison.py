"""Comparison reports for sequence-search scenario summaries."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any

from ..sequence_search import (
    SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
)


DEFAULT_BASELINE_SCENARIO = SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER
DEFAULT_CANDIDATE_SCENARIO = SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER


@dataclass(frozen=True)
class ScenarioMetricSnapshot:
    """Small scenario metric set used for decision-gate comparison."""

    scenario_name: str
    frame_count: int
    matched_frame_count: int
    fallback_frame_count: int
    crop_inside_image_count: int
    mean_estimate_error_m: float
    max_estimate_error_m: float
    final_estimate_error_m: float
    mean_match_score: float | None
    fallback_source_counts: dict[str, int]


@dataclass(frozen=True)
class SequenceScenarioComparison:
    """Comparison between a baseline scenario and a candidate scenario."""

    session_id: str
    source_path: str
    neural_matcher_name: str | None
    baseline: ScenarioMetricSnapshot
    candidate: ScenarioMetricSnapshot
    mean_error_delta_m: float
    max_error_delta_m: float
    final_error_delta_m: float
    matched_frame_delta: int
    fallback_frame_delta: int
    crop_inside_image_delta: int
    sequence_low_likelihood_fallback_count: int
    recommendation: str


def load_sequence_summary(path: Path) -> dict[str, Any]:
    """Load a sequence-search summary artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def compare_sequence_summary(
    summary: dict[str, Any],
    *,
    baseline_name: str = DEFAULT_BASELINE_SCENARIO,
    candidate_name: str = DEFAULT_CANDIDATE_SCENARIO,
) -> SequenceScenarioComparison:
    """Compare two scenarios from a sequence-search summary artifact."""
    scenarios = {scenario["scenario_name"]: scenario for scenario in summary["scenarios"]}
    missing = [name for name in (baseline_name, candidate_name) if name not in scenarios]
    if missing:
        raise ValueError(
            "sequence summary is missing required scenario(s): "
            + ", ".join(missing)
            + ". Re-run sequence_search_replay.py with --roma-model enabled."
        )

    baseline = build_metric_snapshot(scenarios[baseline_name])
    candidate = build_metric_snapshot(scenarios[candidate_name])
    mean_delta = baseline.mean_estimate_error_m - candidate.mean_estimate_error_m
    max_delta = baseline.max_estimate_error_m - candidate.max_estimate_error_m
    final_delta = baseline.final_estimate_error_m - candidate.final_estimate_error_m
    matched_delta = candidate.matched_frame_count - baseline.matched_frame_count
    fallback_delta = candidate.fallback_frame_count - baseline.fallback_frame_count
    crop_delta = candidate.crop_inside_image_count - baseline.crop_inside_image_count
    low_likelihood_count = candidate.fallback_source_counts.get("fallback_roma_sequence_low_likelihood", 0)

    return SequenceScenarioComparison(
        session_id=str(summary.get("session_id", "")),
        source_path=str(summary.get("source_path", "")),
        neural_matcher_name=summary.get("neural_matcher_name"),
        baseline=baseline,
        candidate=candidate,
        mean_error_delta_m=mean_delta,
        max_error_delta_m=max_delta,
        final_error_delta_m=final_delta,
        matched_frame_delta=matched_delta,
        fallback_frame_delta=fallback_delta,
        crop_inside_image_delta=crop_delta,
        sequence_low_likelihood_fallback_count=low_likelihood_count,
        recommendation=build_recommendation(
            mean_error_delta_m=mean_delta,
            max_error_delta_m=max_delta,
            final_error_delta_m=final_delta,
            matched_frame_delta=matched_delta,
            low_likelihood_count=low_likelihood_count,
        ),
    )


def build_metric_snapshot(scenario: dict[str, Any]) -> ScenarioMetricSnapshot:
    """Extract stable comparison metrics from one scenario payload."""
    return ScenarioMetricSnapshot(
        scenario_name=str(scenario["scenario_name"]),
        frame_count=int(scenario["frame_count"]),
        matched_frame_count=int(scenario["matched_frame_count"]),
        fallback_frame_count=int(scenario["fallback_frame_count"]),
        crop_inside_image_count=int(scenario["crop_inside_image_count"]),
        mean_estimate_error_m=float(scenario["mean_estimate_error_m"]),
        max_estimate_error_m=float(scenario["max_estimate_error_m"]),
        final_estimate_error_m=float(scenario["final_estimate_error_m"]),
        mean_match_score=optional_float(scenario.get("mean_match_score")),
        fallback_source_counts={str(key): int(value) for key, value in scenario["fallback_source_counts"].items()},
    )


def build_recommendation(
    *,
    mean_error_delta_m: float,
    max_error_delta_m: float,
    final_error_delta_m: float,
    matched_frame_delta: int,
    low_likelihood_count: int,
) -> str:
    """Create a concise next-action recommendation from comparison deltas."""
    improves_mean = mean_error_delta_m > 0.0
    improves_max = max_error_delta_m > 0.0
    preserves_final = final_error_delta_m >= -1.0
    keeps_updates = matched_frame_delta >= -5
    if improves_mean and improves_max and preserves_final and keeps_updates:
        return "velocity_likelihood_candidate_wins"
    if low_likelihood_count > 0 and (improves_mean or improves_max):
        return "tune_velocity_likelihood_thresholds"
    return "keep_map_constrained_temporal_gate_as_baseline"


def write_sequence_comparison(path: Path, comparison: SequenceScenarioComparison) -> None:
    """Write a JSON comparison report."""
    payload = {
        "session_id": comparison.session_id,
        "source_path": comparison.source_path,
        "neural_matcher_name": comparison.neural_matcher_name,
        "baseline": snapshot_to_dict(comparison.baseline),
        "candidate": snapshot_to_dict(comparison.candidate),
        "deltas": {
            "mean_error_delta_m": comparison.mean_error_delta_m,
            "max_error_delta_m": comparison.max_error_delta_m,
            "final_error_delta_m": comparison.final_error_delta_m,
            "matched_frame_delta": comparison.matched_frame_delta,
            "fallback_frame_delta": comparison.fallback_frame_delta,
            "crop_inside_image_delta": comparison.crop_inside_image_delta,
            "sequence_low_likelihood_fallback_count": comparison.sequence_low_likelihood_fallback_count,
        },
        "recommendation": comparison.recommendation,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_sequence_comparison_csv(path: Path, comparison: SequenceScenarioComparison) -> None:
    """Write a two-row CSV for quick spreadsheet inspection."""
    fieldnames = [
        "scenario_name",
        "frame_count",
        "matched_frame_count",
        "fallback_frame_count",
        "crop_inside_image_count",
        "mean_estimate_error_m",
        "max_estimate_error_m",
        "final_estimate_error_m",
        "mean_match_score",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(snapshot_to_csv_row(comparison.baseline))
        writer.writerow(snapshot_to_csv_row(comparison.candidate))


def snapshot_to_dict(snapshot: ScenarioMetricSnapshot) -> dict[str, Any]:
    """Convert a metric snapshot to a JSON-friendly dictionary."""
    return {
        "scenario_name": snapshot.scenario_name,
        "frame_count": snapshot.frame_count,
        "matched_frame_count": snapshot.matched_frame_count,
        "fallback_frame_count": snapshot.fallback_frame_count,
        "crop_inside_image_count": snapshot.crop_inside_image_count,
        "mean_estimate_error_m": snapshot.mean_estimate_error_m,
        "max_estimate_error_m": snapshot.max_estimate_error_m,
        "final_estimate_error_m": snapshot.final_estimate_error_m,
        "mean_match_score": snapshot.mean_match_score,
        "fallback_source_counts": snapshot.fallback_source_counts,
    }


def snapshot_to_csv_row(snapshot: ScenarioMetricSnapshot) -> dict[str, object]:
    """Convert a metric snapshot to the compact CSV schema."""
    return {
        "scenario_name": snapshot.scenario_name,
        "frame_count": snapshot.frame_count,
        "matched_frame_count": snapshot.matched_frame_count,
        "fallback_frame_count": snapshot.fallback_frame_count,
        "crop_inside_image_count": snapshot.crop_inside_image_count,
        "mean_estimate_error_m": f"{snapshot.mean_estimate_error_m:.6f}",
        "max_estimate_error_m": f"{snapshot.max_estimate_error_m:.6f}",
        "final_estimate_error_m": f"{snapshot.final_estimate_error_m:.6f}",
        "mean_match_score": "" if snapshot.mean_match_score is None else f"{snapshot.mean_match_score:.6f}",
    }


def optional_float(value: object) -> float | None:
    """Return a float for numeric JSON values while preserving nulls."""
    if value is None:
        return None
    return float(value)
