from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pytest

from satellite_drone_localization.packet_replay import load_replay_session
from satellite_drone_localization.replay_pipeline import build_replay_pipeline_artifacts, write_pipeline_debug_svg, write_pipeline_summary
from satellite_drone_localization.replay_pipeline_cli import main as replay_pipeline_main


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_jsonl(path: Path, packets: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(packet) for packet in packets) + "\n", encoding="utf-8")


def test_build_replay_pipeline_artifacts_includes_sensitivity_cases() -> None:
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
                    "prior_search_radius_m": 25.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.08530,
                    "longitude_deg": 34.78180,
                    "prior_latitude_deg": 32.08529,
                    "prior_longitude_deg": 34.78177,
                    "altitude_m": 52.4,
                    "heading_deg": 91.2,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        artifacts = build_replay_pipeline_artifacts(load_replay_session(replay_path))

        assert artifacts.geometry_report.frame_count == 1
        assert artifacts.crop_plan.frame_count == 1
        assert len(artifacts.sensitivity_cases) == 6
        assert artifacts.sensitivity_cases[0].average_ground_width_delta_m > 0.0
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_replay_pipeline_cli_writes_summary_and_svg() -> None:
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
                    "latitude_deg": 32.08530,
                    "longitude_deg": 34.78180,
                    "prior_latitude_deg": 32.08529,
                    "prior_longitude_deg": 34.78177,
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
                    "prior_latitude_deg": 32.08534,
                    "prior_longitude_deg": 34.78179,
                    "altitude_m": 52.2,
                    "heading_deg": 90.8,
                    "camera_hfov_deg": 82.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        exit_code = replay_pipeline_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])
        summary = json.loads((output_dir / "pipeline_summary.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert summary["frame_count"] == 2
        assert len(summary["sensitivity_cases"]) == 6
        assert (output_dir / "pipeline_debug.svg").exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_write_pipeline_artifacts_from_report() -> None:
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
                    "prior_search_radius_m": 25.0,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:30Z",
                    "image_name": "frame_0001.jpg",
                    "latitude_deg": 32.08530,
                    "longitude_deg": 34.78180,
                    "prior_latitude_deg": 32.08529,
                    "prior_longitude_deg": 34.78177,
                    "altitude_m": 52.4,
                    "heading_deg": 91.2,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )

        artifacts = build_replay_pipeline_artifacts(load_replay_session(replay_path))
        write_pipeline_summary(summary_path, artifacts)
        write_pipeline_debug_svg(svg_path, artifacts)

        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        assert loaded["frames"][0]["contains_target"] is True
        assert "Replay Pipeline Debug" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
