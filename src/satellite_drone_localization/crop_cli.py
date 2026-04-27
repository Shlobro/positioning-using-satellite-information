"""CLI entry point for replay crop planning."""

from __future__ import annotations

import argparse
from pathlib import Path

from .crop import build_replay_crop_plan, write_crop_debug_svg, write_crop_summary
from .packet_replay import load_replay_session


def build_parser() -> argparse.ArgumentParser:
    """Construct the crop CLI parser."""
    parser = argparse.ArgumentParser(description="Build a Phase 1 crop plan from replay packets and priors.")
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Path to a JSON-lines replay file using the dev-packet-v1 schema.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to artifacts/crop-debug/<replay-stem> under the current working directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load a replay file, plan crops, and write debug artifacts."""
    parser = build_parser()
    args = parser.parse_args(argv)

    replay_path = Path(args.replay_file).resolve()
    session = load_replay_session(replay_path)
    plan = build_replay_crop_plan(session)

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = Path.cwd().resolve() / "artifacts" / "crop-debug" / replay_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "crop_summary.json"
    svg_path = output_dir / "crop_debug.svg"
    write_crop_summary(summary_path, plan)
    write_crop_debug_svg(svg_path, plan)

    print(f"Frames: {plan.frame_count}")
    print(f"Average crop side: {plan.average_crop_side_m:.2f} m")
    print(f"Max target offset: {plan.max_target_offset_m:.2f} m")
    print(f"Summary: {summary_path}")
    print(f"Debug SVG: {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
