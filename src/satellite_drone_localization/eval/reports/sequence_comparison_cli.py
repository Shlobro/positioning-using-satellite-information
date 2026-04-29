"""CLI for comparing sequence-search scenario summaries."""

from __future__ import annotations

import argparse
from pathlib import Path

from .sequence_comparison import (
    DEFAULT_BASELINE_SCENARIO,
    DEFAULT_CANDIDATE_SCENARIO,
    compare_sequence_summary,
    load_sequence_summary,
    write_sequence_comparison,
    write_sequence_comparison_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two scenarios from a sequence_search_summary.json artifact."
    )
    parser.add_argument(
        "--summary-file",
        required=True,
        help="Path to a sequence_search_summary.json artifact.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for comparison outputs. Defaults to the summary file directory.",
    )
    parser.add_argument(
        "--baseline-scenario",
        default=DEFAULT_BASELINE_SCENARIO,
        help=f"Scenario to treat as the baseline. Defaults to {DEFAULT_BASELINE_SCENARIO}.",
    )
    parser.add_argument(
        "--candidate-scenario",
        default=DEFAULT_CANDIDATE_SCENARIO,
        help=f"Scenario to compare against the baseline. Defaults to {DEFAULT_CANDIDATE_SCENARIO}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    summary_path = Path(args.summary_file).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else summary_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison = compare_sequence_summary(
        load_sequence_summary(summary_path),
        baseline_name=args.baseline_scenario,
        candidate_name=args.candidate_scenario,
    )
    json_path = output_dir / "sequence_search_comparison.json"
    csv_path = output_dir / "sequence_search_comparison.csv"
    write_sequence_comparison(json_path, comparison)
    write_sequence_comparison_csv(csv_path, comparison)

    print(f"Session: {comparison.session_id}")
    print(f"Baseline: {comparison.baseline.scenario_name}")
    print(f"Candidate: {comparison.candidate.scenario_name}")
    print(f"Mean error delta: {comparison.mean_error_delta_m:.2f} m")
    print(f"Max error delta: {comparison.max_error_delta_m:.2f} m")
    print(f"Final error delta: {comparison.final_error_delta_m:.2f} m")
    print(f"Matched frame delta: {comparison.matched_frame_delta}")
    print(f"Low-likelihood fallbacks: {comparison.sequence_low_likelihood_fallback_count}")
    print(f"Recommendation: {comparison.recommendation}")
    print(f"Comparison JSON: {json_path}")
    print(f"Comparison CSV: {csv_path}")
    return 0
