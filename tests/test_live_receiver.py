from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pytest

from satellite_drone_localization.live import LivePacketReceiver, LiveReceiverConfig
from satellite_drone_localization.packet_schema import SCHEMA_VERSION


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def test_live_receiver_parses_json_string_and_builds_receipt() -> None:
    repo_root = make_repo_root()
    try:
        receiver = LivePacketReceiver(
            LiveReceiverConfig(
                session_id="LIVE-SESSION-001",
                source_path=repo_root / "live_dev_packet.json",
            )
        )
        payload = json.dumps(
            {
                "packet_type": "live_frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "latitude_deg": 32.0853,
                "longitude_deg": 34.7818,
                "prior_latitude_deg": 32.08529,
                "prior_longitude_deg": 34.78177,
                "altitude_m": 52.4,
                "heading_deg": 91.2,
                "camera_hfov_deg": 84.0,
                "frame_width_px": 4000,
                "frame_height_px": 3000,
                "prior_search_radius_m": 25.0,
            }
        )

        receipt = receiver.receive_packet(payload)

        assert receipt.session_id == "LIVE-SESSION-001"
        assert receipt.schema_version == SCHEMA_VERSION
        assert receipt.status == "ok"
        assert receipt.ground_width_m == pytest.approx(94.3568, rel=1e-4)
        assert receipt.contains_target is True
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_live_receiver_applies_default_hfov_when_packet_omits_it() -> None:
    repo_root = make_repo_root()
    try:
        receiver = LivePacketReceiver(
            LiveReceiverConfig(
                source_path=repo_root / "live_dev_packet.json",
                camera_hfov_deg=84.0,
                prior_search_radius_m=25.0,
            )
        )
        payload = {
            "packet_type": "live_frame",
            "timestamp_utc": "2026-04-20T10:15:30Z",
            "image_name": "frame_0001.jpg",
            "latitude_deg": 32.0853,
            "longitude_deg": 34.7818,
            "altitude_m": 52.4,
            "heading_deg": 91.2,
            "frame_width_px": 4000,
            "frame_height_px": 3000,
        }

        receipt = receiver.receive_packet(payload)

        assert receipt.ground_height_m == pytest.approx(70.7676, rel=1e-4)
        assert receipt.crop_side_m > 0.0
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_live_receiver_requires_live_packet_type() -> None:
    receiver = LivePacketReceiver(LiveReceiverConfig())
    with pytest.raises(ValueError, match="packet_type='live_frame'"):
        receiver.receive_packet({"packet_type": "frame"})
