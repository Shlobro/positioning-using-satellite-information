"""Repository command for the minimal Phase 1 live receiver stub."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from satellite_drone_localization.live import LivePacketReceiver, LiveReceiverConfig


def build_parser() -> argparse.ArgumentParser:
    """Construct the live receiver stub parser."""
    parser = argparse.ArgumentParser(description="Parse one dev-format live packet and print interpreted metadata.")
    parser.add_argument(
        "--packet-file",
        required=True,
        help="Path to a JSON file containing one live_frame packet.",
    )
    parser.add_argument(
        "--camera-hfov-deg",
        type=float,
        default=None,
        help="Optional default horizontal FOV if the packet does not include one.",
    )
    parser.add_argument(
        "--prior-search-radius-m",
        type=float,
        default=None,
        help="Optional default prior search radius if the packet does not include one.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Load one live packet file and print a parsed receipt."""
    parser = build_parser()
    args = parser.parse_args(argv)

    packet_path = Path(args.packet_file).resolve()
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    receiver = LivePacketReceiver(
        LiveReceiverConfig(
            session_id="LIVE-SESSION-001",
            source_path=packet_path,
            frame_directory=packet_path.parent / "frames",
            camera_hfov_deg=args.camera_hfov_deg,
            prior_search_radius_m=args.prior_search_radius_m,
        )
    )
    receipt = receiver.receive_packet(payload)
    print(f"Session: {receipt.session_id}")
    print(f"Status: {receipt.status}")
    print(f"Image: {receipt.image_name}")
    print(f"Position: {receipt.latitude_deg:.5f}, {receipt.longitude_deg:.5f}")
    print(f"Altitude: {receipt.altitude_m:.2f} m")
    print(f"Heading: {receipt.heading_deg:.2f} deg")
    print(f"Ground footprint: {receipt.ground_width_m:.2f} m x {receipt.ground_height_m:.2f} m")
    print(f"Crop side: {receipt.crop_side_m:.2f} m")
    print(f"Rotation to north-up: {receipt.normalized_rotation_deg:.2f} deg")
    print(f"Contains target: {str(receipt.contains_target).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
