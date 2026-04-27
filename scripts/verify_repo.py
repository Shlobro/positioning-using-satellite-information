"""Deterministic repository verification without direct pytest execution."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
import sys

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from satellite_drone_localization.packet_replay import load_replay_session
from satellite_drone_localization.replay_cli import main as replay_main
from satellite_drone_localization.crop_cli import main as crop_main
from satellite_drone_localization.geometry_cli import main as geometry_main
from satellite_drone_localization.replay_pipeline_cli import main as replay_pipeline_main
from satellite_drone_localization.eval import build_sequence_search_artifacts
from satellite_drone_localization.map_georeference import load_map_georeference
from satellite_drone_localization.live import LivePacketReceiver, LiveReceiverConfig
from satellite_drone_localization.smoke_pipeline import run_smoke


def make_repo_root() -> Path:
    base_dir = REPO_ROOT / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def verify_smoke_pipeline() -> None:
    repo_root = make_repo_root()
    try:
        config_dir = repo_root / "configs" / "eval"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "run_000.json"
        config_path.write_text(
            json.dumps(
                {
                    "run_id": "RUN-000",
                    "phase": "phase-0",
                    "dataset_version": "synthetic-smoke-v1",
                    "model_name": "deterministic-smoke-baseline",
                    "search_radius_m": 100,
                    "area_type": "synthetic",
                    "altitude_band": "50-60m",
                }
            ),
            encoding="utf-8",
        )

        result = run_smoke(config_path=config_path, repo_root=repo_root)

        metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
        assert metrics["run_status"] == "success"
        assert metrics["predictions_count"] == 1

        with result.predictions_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["localization_status"] == "ok"
        assert result.overlay_path.exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def verify_replay_schema() -> None:
    replay_path = REPO_ROOT / "configs" / "replay" / "dev_packets_v1.jsonl"
    session = load_replay_session(replay_path)
    assert session.schema_version == "dev-packet-v1"
    assert len(session.frames) == 2
    assert session.frames[0].altitude_reference == "agl"
    exit_code = replay_main(["--replay-file", str(replay_path)])
    assert exit_code == 0


def verify_geometry_report() -> None:
    replay_path = REPO_ROOT / "configs" / "replay" / "dev_packets_v1.jsonl"
    output_dir = REPO_ROOT / "artifacts" / "manual-verification" / "geometry-report"
    exit_code = geometry_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])
    assert exit_code == 0
    assert (output_dir / "geometry_summary.json").exists()
    assert (output_dir / "geometry_debug.svg").exists()


def verify_crop_plan() -> None:
    replay_path = REPO_ROOT / "configs" / "replay" / "dev_packets_v1.jsonl"
    output_dir = REPO_ROOT / "artifacts" / "manual-verification" / "crop-plan"
    exit_code = crop_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])
    assert exit_code == 0
    assert (output_dir / "crop_summary.json").exists()
    assert (output_dir / "crop_debug.svg").exists()


def verify_replay_pipeline() -> None:
    replay_path = REPO_ROOT / "configs" / "replay" / "dev_packets_v1.jsonl"
    output_dir = REPO_ROOT / "artifacts" / "manual-verification" / "replay-pipeline"
    exit_code = replay_pipeline_main(["--replay-file", str(replay_path), "--output-dir", str(output_dir)])
    assert exit_code == 0
    assert (output_dir / "pipeline_summary.json").exists()
    assert (output_dir / "pipeline_debug.svg").exists()


def verify_live_receiver() -> None:
    packet_path = REPO_ROOT / "configs" / "live" / "dev_live_packet_v1.json"
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    receiver = LivePacketReceiver(
        LiveReceiverConfig(
            session_id="LIVE-SESSION-001",
            source_path=packet_path,
            frame_directory=packet_path.parent / "frames",
        )
    )
    receipt = receiver.receive_packet(payload)
    assert receipt.status == "ok"
    assert receipt.contains_target is True


def verify_map_georeference() -> None:
    repo_root = make_repo_root()
    try:
        calibration_path = repo_root / "calibration.json"
        calibration_path.write_text(
            json.dumps(
                {
                    "image": str(repo_root / "map.png"),
                    "image_size_px": [200, 200],
                    "calibration_points": [
                        {"pixel": [0, 0], "gps": {"lat": 31.0, "lng": 35.0}},
                        {"pixel": [100, 0], "gps": {"lat": 31.0, "lng": 35.001}},
                        {"pixel": [0, 200], "gps": {"lat": 30.999, "lng": 35.0}},
                        {"pixel": [100, 200], "gps": {"lat": 30.999, "lng": 35.001}},
                    ],
                }
            ),
            encoding="utf-8",
        )

        georeference = load_map_georeference(calibration_path)
        latitude_deg, longitude_deg = georeference.pixel_to_latlon(50.0, 100.0)
        assert abs(latitude_deg - 30.9995) < 1e-7
        assert abs(longitude_deg - 35.0005) < 1e-7
        pixel_x, pixel_y = georeference.latlon_to_pixel(latitude_deg, longitude_deg)
        assert abs(pixel_x - 50.0) < 1e-7
        assert abs(pixel_y - 100.0) < 1e-7
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def verify_sequence_search() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
        replay_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "packet_type": "session_start",
                            "schema_version": "dev-packet-v1",
                            "camera_hfov_deg": 84.0,
                        }
                    ),
                    json.dumps(
                        {
                            "packet_type": "frame",
                            "timestamp_utc": "2026-04-20T10:15:30Z",
                            "image_name": "frame_0001.jpg",
                            "latitude_deg": 30.9990,
                            "longitude_deg": 35.0010,
                            "altitude_m": 20.0,
                            "heading_deg": 0.0,
                            "frame_width_px": 4000,
                            "frame_height_px": 3000,
                        }
                    ),
                    json.dumps(
                        {
                            "packet_type": "frame",
                            "timestamp_utc": "2026-04-20T10:15:31Z",
                            "image_name": "frame_0002.jpg",
                            "latitude_deg": 30.9990,
                            "longitude_deg": 35.0012,
                            "altitude_m": 20.0,
                            "heading_deg": 0.0,
                            "frame_width_px": 4000,
                            "frame_height_px": 3000,
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        calibration_path.write_text(
            json.dumps(
                {
                    "image": str(repo_root / "map.png"),
                    "image_size_px": [200, 200],
                    "calibration_points": [
                        {"pixel": [0, 0], "gps": {"lat": 31.0000, "lng": 35.0000}},
                        {"pixel": [200, 0], "gps": {"lat": 31.0000, "lng": 35.0020}},
                        {"pixel": [0, 200], "gps": {"lat": 30.9980, "lng": 35.0000}},
                        {"pixel": [200, 200], "gps": {"lat": 30.9980, "lng": 35.0020}},
                    ],
                }
            ),
            encoding="utf-8",
        )

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
            measurement_update_radius_m=5.0,
        )
        assert len(artifacts.scenarios) == 4
        assert artifacts.scenarios[0].contained_frame_count == 2
        assert artifacts.scenarios[1].contained_frame_count == 2
        assert artifacts.scenarios[2].contained_frame_count == 2
        assert artifacts.scenarios[3].contained_frame_count == 2
        assert artifacts.scenarios[1].frames[1].prior_source == "previous_frame_truth_oracle"
        assert artifacts.scenarios[1].frames[1].target_distance_m > 0.0
        assert artifacts.scenarios[2].frames[1].prior_source == "previous_estimate_recursive_oracle"
        assert artifacts.scenarios[2].frames[1].prior_search_radius_m == 30.0
        assert artifacts.scenarios[3].frames[1].prior_source == "previous_estimate_recursive_placeholder"
        assert artifacts.scenarios[3].frames[1].estimate_source == "matched_placeholder_truth_anchored"
        assert artifacts.scenarios[3].matched_frame_count == 2
        assert artifacts.scenarios[3].max_estimate_error_m > 0.0
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def verify_map_calibrator() -> None:
    tool_dir = REPO_ROOT / "tools" / "map_calibrator"
    test_script = tool_dir / "test_map_calibrator.py"
    assert test_script.exists(), "map_calibrator test not found"
    import subprocess
    result = subprocess.run(
        [sys.executable, str(test_script)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"map_calibrator tests failed:\n{result.stdout}\n{result.stderr}"
    )


def main() -> int:
    verify_smoke_pipeline()
    verify_replay_schema()
    verify_geometry_report()
    verify_crop_plan()
    verify_replay_pipeline()
    verify_live_receiver()
    verify_map_georeference()
    verify_sequence_search()
    verify_map_calibrator()
    print("verification_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
