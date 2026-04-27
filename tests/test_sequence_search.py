from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageDraw

from satellite_drone_localization.eval.sequence_search import (
    SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
    SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
    SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
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


def write_synthetic_map_image(path: Path) -> None:
    image = Image.new("L", (200, 200), color=96)
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 20, 84, 74), fill=186)
    draw.rectangle((110, 22, 174, 88), fill=224)
    draw.rectangle((26, 104, 84, 176), fill=148)
    draw.rectangle((116, 114, 182, 176), fill=204)
    draw.line((98, 0, 98, 200), fill=28, width=6)
    draw.line((0, 150, 200, 150), fill=36, width=8)
    image.save(path)


def write_frame_from_map(
    *,
    map_path: Path,
    frame_path: Path,
    center_x: int,
    center_y: int,
    width_px: int = 60,
    height_px: int = 34,
) -> None:
    with Image.open(map_path) as image:
        patch = image.crop(
            (
                center_x - (width_px // 2),
                center_y - (height_px // 2),
                center_x + (width_px // 2),
                center_y + (height_px // 2),
            )
        )
        frame = patch.resize((192, 108), resample=Image.Resampling.BILINEAR)
        frame.save(frame_path)


def test_build_sequence_search_artifacts_reports_seed_oracle_and_recursive_modes() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
        map_path = repo_root / "map.png"
        frame_0001 = repo_root / "frame_0001.png"
        frame_0002 = repo_root / "frame_0002.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_0001, center_x=100, center_y=100)
        write_frame_from_map(map_path=map_path, frame_path=frame_0002, center_x=112, center_y=100)
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
                    "image_name": "frame_0001.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.0010,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.00112,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
            ],
        )
        write_calibration(calibration_path, map_path)

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
            measurement_update_radius_m=5.0,
        )

        assert [scenario.scenario_name for scenario in artifacts.scenarios] == [
            SCENARIO_SEED_ONLY,
            SCENARIO_ORACLE_PREVIOUS_TRUTH,
            SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
            SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
            SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
        ]
        assert artifacts.scenarios[0].frame_count == 2
        assert artifacts.scenarios[0].frames[1].contains_target is True
        assert artifacts.scenarios[1].frames[1].target_distance_m > 0.0
        assert artifacts.scenarios[2].frames[1].prior_source == "previous_estimate_recursive_oracle"
        assert round(artifacts.scenarios[2].frames[1].prior_search_radius_m, 2) == 30.0
        assert artifacts.scenarios[3].frames[1].prior_source == "previous_estimate_recursive_placeholder"
        assert artifacts.scenarios[3].frames[1].estimate_source == "matched_placeholder_truth_anchored"
        assert artifacts.scenarios[3].matched_frame_count == 2
        assert artifacts.scenarios[3].max_estimate_error_m > 0.0
        assert artifacts.scenarios[4].frames[1].prior_source == "previous_estimate_recursive_image_baseline"
        assert artifacts.scenarios[4].frames[1].estimate_source == "matched_image_baseline"
        assert artifacts.scenarios[4].matched_frame_count == 2
        assert artifacts.scenarios[4].mean_match_score is not None
        assert artifacts.scenarios[4].frames[1].runner_up_match_score is not None
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_sequence_search_cli_writes_summary_and_svg() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        calibration_path = repo_root / "map_calibration.json"
        output_dir = repo_root / "outputs"
        map_path = repo_root / "map.png"
        frame_0001 = repo_root / "frame_0001.png"
        frame_0002 = repo_root / "frame_0002.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_0001, center_x=100, center_y=100)
        write_frame_from_map(map_path=map_path, frame_path=frame_0002, center_x=112, center_y=100)
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
                    "image_name": "frame_0001.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.0010,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.00112,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
            ],
        )
        write_calibration(calibration_path, map_path)

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
        assert len(summary["scenarios"]) == 5
        assert summary["measurement_update_radius_m"] == 5.0
        assert summary["scenarios"][3]["scenario_name"] == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER
        assert summary["scenarios"][4]["scenario_name"] == SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER
        assert summary["scenarios"][4]["mean_match_score"] is not None
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
        map_path = repo_root / "map.png"
        frame_0001 = repo_root / "frame_0001.png"
        frame_0002 = repo_root / "frame_0002.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_0001, center_x=100, center_y=100)
        write_frame_from_map(map_path=map_path, frame_path=frame_0002, center_x=112, center_y=100)
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
                    "image_name": "frame_0001.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.0010,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
                {
                    "packet_type": "frame",
                    "timestamp_utc": "2026-04-20T10:15:31Z",
                    "image_name": "frame_0002.png",
                    "latitude_deg": 30.9990,
                    "longitude_deg": 35.00112,
                    "altitude_m": 16.66,
                    "heading_deg": 0.0,
                    "frame_width_px": 192,
                    "frame_height_px": 108,
                },
            ],
        )
        write_calibration(calibration_path, map_path)

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
        )
        write_sequence_search_summary(summary_path, artifacts)
        write_sequence_search_debug_svg(svg_path, artifacts)

        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        assert loaded["scenarios"][0]["scenario_name"] == SCENARIO_SEED_ONLY
        assert loaded["scenarios"][2]["scenario_name"] == SCENARIO_RECURSIVE_ORACLE_ESTIMATE
        assert loaded["scenarios"][3]["scenario_name"] == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER
        assert loaded["scenarios"][4]["scenario_name"] == SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER
        assert "Sequence Search Debug" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
