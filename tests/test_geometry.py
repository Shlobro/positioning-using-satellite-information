from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pytest

from satellite_drone_localization.geometry import (
    build_replay_geometry_report,
    normalize_frame_geometry,
    write_geometry_debug_svg,
    write_geometry_summary,
)
from satellite_drone_localization.geometry_cli import main as geometry_main
from satellite_drone_localization.packet_replay import load_replay_session


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_jsonl(path: Path, packets: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(packet) for packet in packets) + "\n", encoding="utf-8")


def test_normalize_frame_geometry_infers_vertical_fov_from_aspect_ratio() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        write_jsonl(
            replay_path,
            [
                {
                    "packet_type": "session_start",
                    "schema_version": "dev-packet-v1",
                    "camera_hfov_deg": 84.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.0853,
                    "longitude_deg": 34.7818,
                    "altitude_m": 52.4,
                    "heading_deg": 90.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )
        session = load_replay_session(replay_path)

        geometry = normalize_frame_geometry(session.frames[0])

        assert geometry.vfov_source == "inferred_from_aspect_ratio"
        assert geometry.camera_vfov_deg == pytest.approx(68.1566, rel=1e-4)
        assert geometry.ground_width_m == pytest.approx(94.3814, rel=1e-4)
        assert geometry.ground_height_m == pytest.approx(70.7861, rel=1e-4)
        assert geometry.normalization_rotation_deg == pytest.approx(270.0)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_geometry_cli_writes_summary_and_svg() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        output_dir = repo_root / "outputs"
        write_jsonl(
            replay_path,
            [
                {
                    "packet_type": "session_start",
                    "schema_version": "dev-packet-v1",
                    "session_id": "DEV-SESSION-001",
                    "camera_hfov_deg": 84.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.0853,
                    "longitude_deg": 34.7818,
                    "altitude_m": 52.4,
                    "heading_deg": 91.2,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.jpg",
                    "latitude_deg": 32.08531,
                    "longitude_deg": 34.78182,
                    "altitude_m": 52.2,
                    "heading_deg": 90.8,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        exit_code = geometry_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])

        summary_path = output_dir / "geometry_summary.json"
        svg_path = output_dir / "geometry_debug.svg"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        assert exit_code == 0
        assert summary["frame_count"] == 2
        assert summary["frames"][0]["vfov_source"] == "inferred_from_aspect_ratio"
        assert svg_path.exists()
        assert "<svg" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_write_geometry_artifacts_from_report() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        summary_path = repo_root / "summary.json"
        svg_path = repo_root / "debug.svg"
        write_jsonl(
            replay_path,
            [
                {
                    "packet_type": "session_start",
                    "schema_version": "dev-packet-v1",
                    "camera_hfov_deg": 84.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.0853,
                    "longitude_deg": 34.7818,
                    "altitude_m": 52.4,
                    "heading_deg": 45.0,
                },
            ],
        )

        report = build_replay_geometry_report(load_replay_session(replay_path))
        write_geometry_summary(summary_path, report)
        write_geometry_debug_svg(svg_path, report)

        assert json.loads(summary_path.read_text(encoding="utf-8"))["frames"][0]["vfov_source"] == "fallback_equal_to_hfov"
        assert "rotation to north-up" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
