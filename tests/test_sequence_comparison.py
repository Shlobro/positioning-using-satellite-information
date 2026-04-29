from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from satellite_drone_localization.eval.reports.sequence_comparison import compare_sequence_summary
from satellite_drone_localization.eval.reports.sequence_comparison_cli import main as comparison_main


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def make_summary() -> dict[str, object]:
    return {
        "session_id": "DEV-SESSION-TEST",
        "source_path": "data/session/dev_packets_v1.jsonl",
        "neural_matcher_name": "roma_outdoor",
        "scenarios": [
            make_scenario(
                "recursive_roma_map_constrained_matcher",
                matched=53,
                fallbacks=39,
                mean_error=4.60,
                max_error=21.51,
                final_error=2.30,
                fallback_counts={"fallback_roma_temporal_motion_gate": 1},
            ),
            make_scenario(
                "recursive_roma_velocity_likelihood_matcher",
                matched=51,
                fallbacks=41,
                mean_error=4.10,
                max_error=15.20,
                final_error=2.80,
                fallback_counts={"fallback_roma_sequence_low_likelihood": 2},
            ),
        ],
    }


def make_scenario(
    name: str,
    *,
    matched: int,
    fallbacks: int,
    mean_error: float,
    max_error: float,
    final_error: float,
    fallback_counts: dict[str, int],
) -> dict[str, object]:
    return {
        "scenario_name": name,
        "frame_count": 92,
        "matched_frame_count": matched,
        "fallback_frame_count": fallbacks,
        "crop_inside_image_count": 92,
        "mean_estimate_error_m": mean_error,
        "max_estimate_error_m": max_error,
        "final_estimate_error_m": final_error,
        "mean_match_score": 0.81,
        "fallback_source_counts": fallback_counts,
    }


def test_compare_sequence_summary_reports_metric_deltas() -> None:
    comparison = compare_sequence_summary(make_summary())

    assert comparison.session_id == "DEV-SESSION-TEST"
    assert comparison.mean_error_delta_m == 0.5
    assert round(comparison.max_error_delta_m, 2) == 6.31
    assert comparison.final_error_delta_m == -0.5
    assert comparison.matched_frame_delta == -2
    assert comparison.sequence_low_likelihood_fallback_count == 2
    assert comparison.recommendation == "velocity_likelihood_candidate_wins"


def test_compare_sequence_summary_requires_candidate_scenarios() -> None:
    summary = make_summary()
    summary["scenarios"] = summary["scenarios"][:1]

    try:
        compare_sequence_summary(summary)
    except ValueError as exc:
        assert "recursive_roma_velocity_likelihood_matcher" in str(exc)
        assert "--roma-model" in str(exc)
    else:
        raise AssertionError("comparison should fail when the velocity scenario is missing")


def test_sequence_comparison_cli_writes_json_and_csv() -> None:
    repo_root = make_repo_root()
    try:
        summary_path = repo_root / "sequence_search_summary.json"
        output_dir = repo_root / "comparison"
        summary_path.write_text(json.dumps(make_summary()), encoding="utf-8")

        exit_code = comparison_main(
            [
                "--summary-file",
                str(summary_path),
                "--output-dir",
                str(output_dir),
            ]
        )

        report = json.loads((output_dir / "sequence_search_comparison.json").read_text(encoding="utf-8"))
        csv_text = (output_dir / "sequence_search_comparison.csv").read_text(encoding="utf-8")
        assert exit_code == 0
        assert report["deltas"]["matched_frame_delta"] == -2
        assert report["recommendation"] == "velocity_likelihood_candidate_wins"
        assert "recursive_roma_velocity_likelihood_matcher" in csv_text
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
