"""CLI entry point for the combined Phase 1 replay pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .replay_pipeline import build_replay_pipeline_artifacts, write_pipeline_debug_svg, write_pipeline_summary
from .packet_replay import load_replay_session


def build_parser() -> argparse.ArgumentParser:
    """Construct the replay pipeline CLI parser."""
    parser = argparse.ArgumentParser(
        description="Build combined replay pipeline artifacts from dev-packet-v1 packets."
    )
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Path to a JSON-lines replay file using the dev-packet-v1 schema.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to artifacts/replay-pipeline/<replay-stem> under the current working directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load a replay file, build the combined pipeline, and write artifacts."""
    parser = build_parser()
    args = parser.parse_args(argv)

    replay_path = Path(args.replay_file).resolve()
    session = load_replay_session(replay_path)
    artifacts = build_replay_pipeline_artifacts(session)

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = Path.cwd().resolve() / "artifacts" / "replay-pipeline" / replay_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "pipeline_summary.json"
    svg_path = output_dir / "pipeline_debug.svg"
    write_pipeline_summary(summary_path, artifacts)
    write_pipeline_debug_svg(svg_path, artifacts)

    print(f"Frames: {artifacts.geometry_report.frame_count}")
    print(f"Average altitude: {artifacts.geometry_report.average_altitude_m:.2f} m")
    print(f"Average crop side: {artifacts.crop_plan.average_crop_side_m:.2f} m")
    print(f"Sensitivity cases: {len(artifacts.sensitivity_cases)}")
    print(f"Summary: {summary_path}")
    print(f"Debug SVG: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
