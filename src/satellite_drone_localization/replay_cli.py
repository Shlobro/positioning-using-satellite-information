"""CLI entry point for replay packet validation."""

from __future__ import annotations

from pathlib import Path
import argparse

from .packet_replay import load_replay_session


def build_parser() -> argparse.ArgumentParser:
    """Construct the replay CLI parser."""
    parser = argparse.ArgumentParser(description="Validate and summarize a Phase 1 replay packet file.")
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Path to a JSON-lines replay file using the dev-packet-v1 schema.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load a replay file and print a concise summary."""
    parser = build_parser()
    args = parser.parse_args(argv)

    replay_path = Path(args.replay_file)
    session = load_replay_session(replay_path)
    first_frame = session.frames[0]
    print(f"Loaded {len(session.frames)} frame packets from {session.source_path}")
    print(f"Schema: {session.schema_version}")
    print(f"Session: {session.session_id or 'none'}")
    print(f"Default altitude reference: {session.defaults.altitude_reference}")
    print(f"First frame: {first_frame.timestamp_utc} {first_frame.image_name}")
    print(f"First image path: {first_frame.image_path}")
    print(f"First frame hfov: {first_frame.camera_hfov_deg:.2f} deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
