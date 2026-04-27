"""CLI entry point for motion-bounded sequence search evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..map_georeference import load_map_georeference
from ..packet_replay import load_replay_session
from .sequence_search import build_sequence_search_artifacts, write_sequence_search_debug_svg, write_sequence_search_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate hidden-GPS sequence search windows against a calibrated GIS reference image."
    )
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Path to a JSON-lines replay file using the dev-packet-v1 schema.",
    )
    parser.add_argument(
        "--calibration-file",
        required=True,
        help="Path to a calibration JSON sidecar for the reference GIS image.",
    )
    parser.add_argument(
        "--max-speed-mps",
        type=float,
        default=25.0,
        help="Assumed upper-bound platform speed in meters per second. Defaults to 25.0.",
    )
    parser.add_argument(
        "--base-search-radius-m",
        type=float,
        default=0.0,
        help="Optional non-negative starting search radius around the seed location. Defaults to 0.0.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to artifacts/sequence-search/<replay-stem> under the current working directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    replay_path = Path(args.replay_file).resolve()
    calibration_path = Path(args.calibration_file).resolve()
    session = load_replay_session(replay_path)
    georeference = load_map_georeference(calibration_path)
    artifacts = build_sequence_search_artifacts(
        session,
        georeference,
        max_speed_mps=args.max_speed_mps,
        base_search_radius_m=args.base_search_radius_m,
    )

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = Path.cwd().resolve() / "artifacts" / "sequence-search" / replay_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "sequence_search_summary.json"
    svg_path = output_dir / "sequence_search_debug.svg"
    write_sequence_search_summary(summary_path, artifacts)
    write_sequence_search_debug_svg(svg_path, artifacts)

    print(f"Frames: {artifacts.scenarios[0].frame_count}")
    print(f"Image size: {artifacts.image_width_px} x {artifacts.image_height_px}")
    print(f"Georeference max residual: {artifacts.georeference_max_residual_m:.2f} m")
    for scenario in artifacts.scenarios:
        print(
            f"{scenario.scenario_name}: contains={scenario.contained_frame_count}/{scenario.frame_count} "
            f"map={scenario.crop_inside_image_count}/{scenario.frame_count} "
            f"max_offset={scenario.max_target_offset_m:.2f}m"
        )
    print(f"Summary: {summary_path}")
    print(f"Debug SVG: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
