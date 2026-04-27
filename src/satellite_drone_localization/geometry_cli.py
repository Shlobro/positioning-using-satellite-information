"""CLI entry point for replay geometry normalization reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from .geometry import build_replay_geometry_report, write_geometry_debug_svg, write_geometry_summary
from .packet_replay import load_replay_session


def build_parser() -> argparse.ArgumentParser:
    """Construct the geometry CLI parser."""
    parser = argparse.ArgumentParser(description="Build a Phase 1 geometry normalization report from replay packets.")
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Path to a JSON-lines replay file using the dev-packet-v1 schema.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to artifacts/geometry-debug/<replay-stem> under the current working directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load a replay file, compute geometry, and write debug artifacts."""
    parser = build_parser()
    args = parser.parse_args(argv)

    replay_path = Path(args.replay_file).resolve()
    session = load_replay_session(replay_path)
    report = build_replay_geometry_report(session)

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = Path.cwd().resolve() / "artifacts" / "geometry-debug" / replay_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "geometry_summary.json"
    svg_path = output_dir / "geometry_debug.svg"
    write_geometry_summary(summary_path, report)
    write_geometry_debug_svg(svg_path, report)

    print(f"Frames: {report.frame_count}")
    print(f"Average altitude: {report.average_altitude_m:.2f} m")
    print(f"Width range: {report.min_ground_width_m:.2f} m .. {report.max_ground_width_m:.2f} m")
    print(f"Height range: {report.min_ground_height_m:.2f} m .. {report.max_ground_height_m:.2f} m")
    print(f"Summary: {summary_path}")
    print(f"Debug SVG: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
