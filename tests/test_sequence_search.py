from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from satellite_drone_localization.eval.sequence_search import (
    SCENARIO_ORACLE_PREVIOUS_TRUTH,
    SCENARIO_SEED_ONLY,
    build_sequence_search_artifacts,
    write_sequence_search_debug_svg,
    write_sequence_search_summary,
)
from satellite_drone_localization.eval.sequence_search_cli import main as sequence_search_main
from satellite_drone_localization.map_georeference import load_map_georeference
from satellite_drone_localization.packet_replay import load_replay_session


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_jsonl(path: Path, packets: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(packet) for packet in packets) + "\n", encoding="utf-8")


def write_calibration(path: Path, image_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "image": str(image_path),
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


def test_build_sequence_search_artifacts_reports_seed_and_oracle_modes() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
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
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0000,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.jpg",
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0002,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )
        write_calibration(calibration_path, repo_root / "map.png")

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
        )

        assert [scenario.scenario_name for scenario in artifacts.scenarios] == [
            SCENARIO_SEED_ONLY,
            SCENARIO_ORACLE_PREVIOUS_TRUTH,
        ]
        assert artifacts.scenarios[0].frame_count == 2
        assert artifacts.scenarios[0].frames[1].contains_target is True
        assert artifacts.scenarios[1].frames[1].target_distance_m == 0.0
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_sequence_search_cli_writes_summary_and_svg() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
        output_dir = repo_root / "outputs"
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
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0000,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.jpg",
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0002,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )
        write_calibration(calibration_path, repo_root / "map.png")

        exit_code = sequence_search_main(
            [
                "--replay-file",
                str(replay_path),
                "--calibration-file",
                str(calibration_path),
                "--output-dir",
                str(output_dir),
            ]
        )

        summary = json.loads((output_dir / "sequence_search_summary.json").read_text(encoding="utf-8"))
        assert exit_code == 0
        assert len(summary["scenarios"]) == 2
        assert (output_dir / "sequence_search_debug.svg").exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_write_sequence_search_artifacts_from_report() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
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
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0000,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.jpg",
                    "latitude_deg": 31.0000,
                    "longitude_deg": 35.0002,
                    "altitude_m": 20.0,
                    "heading_deg": 0.0,
                    "frame_width_px": 4000,
                    "frame_height_px": 3000,
                },
            ],
        )
        write_calibration(calibration_path, repo_root / "map.png")

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
        )
        write_sequence_search_summary(summary_path, artifacts)
        write_sequence_search_debug_svg(svg_path, artifacts)

        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        assert loaded["scenarios"][0]["scenario_name"] == SCENARIO_SEED_ONLY
        assert "Sequence Search Debug" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
