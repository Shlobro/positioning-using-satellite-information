from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pytest

from satellite_drone_localization.crop import build_replay_crop_plan, meters_offset_between, write_crop_debug_svg, write_crop_summary
from satellite_drone_localization.crop_cli import main as crop_main
from satellite_drone_localization.packet_replay import load_replay_session


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_jsonl(path: Path, packets: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(packet) for packet in packets) + "\n", encoding="utf-8")


def test_meters_offset_between_returns_small_local_offsets() -> None:
    east_m, north_m = meters_offset_between(32.0853, 34.7818, 32.08531, 34.78182)
    assert east_m == pytest.approx(1.8846, rel=1e-3)
    assert north_m == pytest.approx(1.1132, rel=1e-3)


def test_build_replay_crop_plan_uses_prior_and_contains_target() -> None:
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
                    "prior_search_radius_m": 20.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.08531,
                    "longitude_deg": 34.78182,
                    "prior_latitude_deg": 32.08530,
                    "prior_longitude_deg": 34.78180,
                    "altitude_m": 52.4,
                    "heading_deg": 91.2,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        plan = build_replay_crop_plan(load_replay_session(replay_path))

        assert plan.frame_count == 1
        frame = plan.frames[0]
        assert frame.prior_search_radius_m == pytest.approx(20.0)
        assert frame.contains_target is True
        assert frame.target_offset_east_m == pytest.approx(1.8846, rel=1e-3)
        assert frame.target_offset_north_m == pytest.approx(1.1132, rel=1e-3)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_crop_cli_writes_summary_and_svg() -> None:
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
                    "camera_hfov_deg": 84.0,
                    "prior_search_radius_m": 25.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.08531,
                    "longitude_deg": 34.78182,
                    "prior_latitude_deg": 32.08530,
                    "prior_longitude_deg": 34.78180,
                    "altitude_m": 52.4,
                    "heading_deg": 91.2,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        exit_code = crop_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])
        summary = json.loads((output_dir / "crop_summary.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert summary["frame_count"] == 1
        assert summary["frames"][0]["contains_target"] is True
        assert (output_dir / "crop_debug.svg").exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_write_crop_artifacts_from_plan() -> None:
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
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        plan = build_replay_crop_plan(load_replay_session(replay_path))
        write_crop_summary(summary_path, plan)
        write_crop_debug_svg(svg_path, plan)

        assert json.loads(summary_path.read_text(encoding="utf-8"))["frames"][0]["crop_side_m"] > 0.0
        assert "contains_target" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
