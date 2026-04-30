"""Tests for tools/localization_gui/single_image_input.py.

These tests exercise the headless logic only — no Qt, no display.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

import pytest


# Make the tools/localization_gui package importable without launching the GUI.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from localization_gui.single_image_input import (  # noqa: E402
    SIDECAR_SUFFIX,
    load_single_image_packet,
    sidecar_path_for_image,
    write_single_image_packet_template,
)


def _make_temp_dir() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def _write_solid_png(path: Path, color: int = 128) -> None:
    Image.new("L", (32, 24), color=color).save(path)


def test_sidecar_path_uses_image_stem_plus_packet_json() -> None:
    image_path = Path("/tmp/foo/bar.png")
    assert sidecar_path_for_image(image_path) == Path("/tmp/foo/bar" + SIDECAR_SUFFIX)


def test_load_single_image_packet_rejects_missing_sidecar() -> None:
    repo_root = _make_temp_dir()
    image_path = repo_root / "frame.png"
    _write_solid_png(image_path)

    with pytest.raises(FileNotFoundError):
        load_single_image_packet(image_path)


def test_load_single_image_packet_rejects_multiple_frames() -> None:
    repo_root = _make_temp_dir()
    image_path = repo_root / "frame.png"
    _write_solid_png(image_path)

    sidecar = sidecar_path_for_image(image_path)
    sidecar.write_text(
        "\n".join(
            [
                json.dumps({"packet_type": "session_start", "schema_version": "dev-packet-v1", "camera_hfov_deg": 76.0}),
                json.dumps(
                    {
                        "packet_type": "frame",
                        "timestamp_utc": "2026-04-30T10:00:00Z",
                        "image_name": "frame.png",
                        "latitude_deg": 31.0,
                        "longitude_deg": 35.0,
                        "altitude_m": 30.0,
                        "heading_deg": 90.0,
                    }
                ),
                json.dumps(
                    {
                        "packet_type": "frame",
                        "timestamp_utc": "2026-04-30T10:00:01Z",
                        "image_name": "frame.png",
                        "latitude_deg": 31.0,
                        "longitude_deg": 35.0,
                        "altitude_m": 30.0,
                        "heading_deg": 90.0,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one frame packet"):
        load_single_image_packet(image_path)


def test_write_and_load_single_image_packet_roundtrip() -> None:
    repo_root = _make_temp_dir()
    image_path = repo_root / "drone_001.png"
    _write_solid_png(image_path)

    sidecar = write_single_image_packet_template(
        image_path,
        latitude_deg=31.769,
        longitude_deg=35.193,
        altitude_m=30.0,
        heading_deg=120.0,
        camera_hfov_deg=76.0,
        camera_vfov_deg=60.8,
        frame_width_px=1920,
        frame_height_px=1088,
        timestamp_utc="2026-04-30T10:00:00Z",
        prior_search_radius_m=25.0,
    )
    assert sidecar == sidecar_path_for_image(image_path)
    assert sidecar.is_file()

    packet = load_single_image_packet(image_path)
    assert len(packet.session.frames) == 1
    frame = packet.session.frames[0]
    assert frame.image_name == "drone_001.png"
    assert frame.latitude_deg == 31.769
    assert frame.longitude_deg == 35.193
    assert frame.altitude_m == 30.0
    assert frame.heading_deg == 120.0
    assert frame.camera_hfov_deg == 76.0
    assert frame.camera_vfov_deg == 60.8
    assert frame.frame_width_px == 1920
    assert frame.frame_height_px == 1088
    assert frame.prior_search_radius_m == 25.0


def test_load_single_image_packet_rejects_filename_mismatch() -> None:
    repo_root = _make_temp_dir()
    image_path = repo_root / "drone_a.png"
    _write_solid_png(image_path)

    sidecar = sidecar_path_for_image(image_path)
    sidecar.write_text(
        "\n".join(
            [
                json.dumps({"packet_type": "session_start", "schema_version": "dev-packet-v1", "camera_hfov_deg": 76.0}),
                json.dumps(
                    {
                        "packet_type": "frame",
                        "timestamp_utc": "2026-04-30T10:00:00Z",
                        "image_name": "drone_b.png",
                        "latitude_deg": 31.0,
                        "longitude_deg": 35.0,
                        "altitude_m": 30.0,
                        "heading_deg": 90.0,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match image filename"):
        load_single_image_packet(image_path)
