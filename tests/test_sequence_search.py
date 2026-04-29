from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageDraw

from satellite_drone_localization.eval.sequence_search import (
    SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
    SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
    SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
    SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
    SCENARIO_ORACLE_PREVIOUS_TRUTH,
    SCENARIO_SEED_ONLY,
    build_sequence_search_artifacts,
    build_crop_pixel_bounds,
    write_sequence_search_debug_svg,
    write_sequence_search_summary,
)
from satellite_drone_localization.eval.matcher_roma import RoMaRegressionMatcher
from satellite_drone_localization.eval.sequence_policy import (
    constrain_prior_to_image,
    estimate_map_limited_square_side_m,
    evaluate_roma_sequence_likelihood,
    evaluate_roma_temporal_consistency,
)


class FakeRoMaBackend:
    def __init__(self, center_x: float, center_y: float) -> None:
        self.center_x = center_x
        self.center_y = center_y

    def match(self, image_a, image_b, *args, device=None):
        return "matches", "certainty"

    def sample(self, matches, certainty, num=5000):
        import numpy as np

        coords = np.zeros((512, 4), dtype=np.float32)
        certainty_values = np.full((512,), 0.92, dtype=np.float32)
        return coords, certainty_values

    def to_pixel_coordinates(self, coords, height_a, width_a, height_b=None, width_b=None):
        import numpy as np

        frame_points: list[list[float]] = []
        crop_points: list[list[float]] = []
        offset_x = self.center_x - (width_a / 2.0)
        offset_y = self.center_y - (height_a / 2.0)
        for index in range(512):
            local_x = float((index * 17) % max(1, width_a - 1))
            local_y = float((index * 11) % max(1, height_a - 1))
            frame_points.append([local_x, local_y])
            crop_points.append([local_x + offset_x, local_y + offset_y])
        return np.asarray(frame_points, dtype=np.float32), np.asarray(crop_points, dtype=np.float32)


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
            SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
            SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
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
        assert artifacts.scenarios[5].frames[1].prior_source == "previous_estimate_recursive_image_map_constrained"
        assert artifacts.scenarios[5].matched_frame_count == 2
        assert artifacts.scenarios[5].map_constrained_frame_count == 0
        assert artifacts.scenarios[5].map_limited_frame_count == 0
        assert artifacts.scenarios[6].frames[1].prior_source == "previous_estimate_recursive_classical"
        assert artifacts.scenarios[6].frames[0].estimate_source == "fallback_classical_insufficient_features"
        assert artifacts.scenarios[6].frames[1].estimate_source == "fallback_classical_insufficient_features"
        assert artifacts.scenarios[6].matched_frame_count == 0
        assert artifacts.scenarios[6].mean_match_score is None
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_build_sequence_search_artifacts_adds_optional_roma_scenario() -> None:
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
        roma_matcher = RoMaRegressionMatcher(
            map_path,
            backend=FakeRoMaBackend(center_x=112.0, center_y=100.0),
            device="cpu",
            model_name="roma_outdoor",
        )

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
            measurement_update_radius_m=5.0,
            roma_matcher=roma_matcher,
        )

        assert artifacts.neural_matcher_name == "roma_outdoor"
        assert artifacts.scenarios[-3].scenario_name == SCENARIO_RECURSIVE_ROMA_MATCHER
        assert artifacts.scenarios[-2].scenario_name == SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER
        assert artifacts.scenarios[-1].scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER
        assert artifacts.scenarios[-3].frames[1].prior_source == "previous_estimate_recursive_roma"
        assert artifacts.scenarios[-3].frames[1].estimate_source == "matched_roma"
        assert artifacts.scenarios[-3].matched_frame_count == 2
        assert artifacts.scenarios[-3].mean_match_score is not None
        assert artifacts.scenarios[-3].estimate_source_counts["matched_roma"] == 2
        assert artifacts.scenarios[-3].fallback_source_counts == {}
        assert artifacts.scenarios[-3].frames[1].matcher_diagnostics is not None
        assert artifacts.scenarios[-3].frames[1].matcher_diagnostics["inlier_count"] >= 48
        assert artifacts.scenarios[-2].frames[1].prior_source == "previous_estimate_recursive_roma_map_constrained"
        assert artifacts.scenarios[-2].frames[1].estimate_source == "matched_roma"
        assert artifacts.scenarios[-2].matched_frame_count == 2
        assert artifacts.scenarios[-1].frames[1].prior_source == "velocity_prediction_recursive_roma_likelihood"
        assert artifacts.scenarios[-1].matched_frame_count == 2
        assert artifacts.scenarios[-1].frames[1].matcher_diagnostics is not None
        assert "sequence_update_likelihood" in artifacts.scenarios[-1].frames[1].matcher_diagnostics
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_map_constrained_roma_scenario_rejects_updates_outside_motion_gate() -> None:
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
                {"packet_type": "session_start", "schema_version": "dev-packet-v1", "camera_hfov_deg": 84.0},
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
        roma_matcher = RoMaRegressionMatcher(
            map_path,
            backend=FakeRoMaBackend(center_x=180.0, center_y=100.0),
            device="cpu",
            model_name="roma_outdoor",
        )

        artifacts = build_sequence_search_artifacts(
            load_replay_session(replay_path),
            load_map_georeference(calibration_path),
            max_speed_mps=25.0,
            measurement_update_radius_m=5.0,
            roma_matcher=roma_matcher,
        )

        assert artifacts.scenarios[-2].scenario_name == SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER
        assert artifacts.scenarios[-2].frames[0].estimate_source == "fallback_roma_temporal_motion_gate"
        assert artifacts.scenarios[-2].matched_frame_count == 0
        assert artifacts.scenarios[-2].fallback_source_counts["fallback_roma_temporal_motion_gate"] == 2
        assert artifacts.scenarios[-2].frames[0].matcher_diagnostics is not None
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_roma_temporal_gate_rejects_weak_large_update() -> None:
    diagnostics = {"inlier_ratio": 0.13, "inlier_spatial_coverage": 0.36}

    accepted, fallback_source = evaluate_roma_temporal_consistency(
        update_distance_m=41.0,
        prior_search_radius_m=52.0,
        measurement_update_radius_m=5.0,
        match_score=0.67,
        diagnostics=diagnostics,
    )

    assert accepted is False
    assert fallback_source == "fallback_roma_temporal_weak_large_update"
    assert diagnostics["temporal_update_distance_m"] == 41.0
    assert diagnostics["temporal_weak_large_update_evidence"] == 1


def test_roma_temporal_gate_accepts_strong_large_recovery() -> None:
    diagnostics = {"inlier_ratio": 0.30, "inlier_spatial_coverage": 0.50}

    accepted, fallback_source = evaluate_roma_temporal_consistency(
        update_distance_m=42.0,
        prior_search_radius_m=128.0,
        measurement_update_radius_m=5.0,
        match_score=0.81,
        diagnostics=diagnostics,
    )

    assert accepted is True
    assert fallback_source is None
    assert diagnostics["temporal_weak_large_update_evidence"] == 0


def test_roma_sequence_likelihood_rejects_low_probability_update() -> None:
    diagnostics = {"inlier_ratio": 0.20, "inlier_spatial_coverage": 0.50}

    accepted, fallback_source = evaluate_roma_sequence_likelihood(
        update_distance_m=85.0,
        prior_search_radius_m=28.0,
        measurement_update_radius_m=5.0,
        match_score=0.86,
        diagnostics=diagnostics,
    )

    assert accepted is False
    assert fallback_source == "fallback_roma_sequence_low_likelihood"
    assert diagnostics["sequence_update_likelihood"] < diagnostics["sequence_min_likelihood"]


def test_roma_sequence_likelihood_accepts_supported_motion_update() -> None:
    diagnostics = {"inlier_ratio": 0.22, "inlier_spatial_coverage": 0.52}

    accepted, fallback_source = evaluate_roma_sequence_likelihood(
        update_distance_m=12.0,
        prior_search_radius_m=28.0,
        measurement_update_radius_m=5.0,
        match_score=0.83,
        diagnostics=diagnostics,
    )

    assert accepted is True
    assert fallback_source is None
    assert diagnostics["sequence_update_likelihood"] >= diagnostics["sequence_min_likelihood"]


def test_constrain_prior_to_image_moves_offmap_crop_center() -> None:
    repo_root = make_repo_root()
    try:
        calibration_path = repo_root / "map_calibration.json"
        map_path = repo_root / "map.png"
        write_synthetic_map_image(map_path)
        write_calibration(calibration_path, map_path)
        georeference = load_map_georeference(calibration_path)
        latitude_deg, longitude_deg = georeference.pixel_to_latlon(8.0, 100.0)

        constrained_latitude_deg, constrained_longitude_deg, was_constrained = constrain_prior_to_image(
            georeference=georeference,
            prior_latitude_deg=latitude_deg,
            prior_longitude_deg=longitude_deg,
            half_side_m=20.0,
            build_crop_pixel_bounds=build_crop_pixel_bounds,
        )

        constrained_x, _ = georeference.latlon_to_pixel(constrained_latitude_deg, constrained_longitude_deg)
        assert was_constrained is True
        assert constrained_x > 8.0
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_estimate_map_limited_square_side_uses_shorter_map_extent() -> None:
    repo_root = make_repo_root()
    try:
        calibration_path = repo_root / "map_calibration.json"
        map_path = repo_root / "map.png"
        write_synthetic_map_image(map_path)
        write_calibration(calibration_path, map_path)
        georeference = load_map_georeference(calibration_path)

        limited_side_m = estimate_map_limited_square_side_m(georeference)

        assert 180.0 < limited_side_m < 200.0
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
        assert len(summary["scenarios"]) == 7
        assert summary["measurement_update_radius_m"] == 5.0
        assert summary["neural_matcher_name"] is None
        assert summary["scenarios"][3]["scenario_name"] == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER
        assert summary["scenarios"][4]["scenario_name"] == SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER
        assert summary["scenarios"][5]["scenario_name"] == SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER
        assert summary["scenarios"][6]["scenario_name"] == SCENARIO_RECURSIVE_CLASSICAL_MATCHER
        assert "map_constrained_frame_count" in summary["scenarios"][5]
        assert "map_limited_frame_count" in summary["scenarios"][5]
        assert summary["scenarios"][6]["fallback_source_counts"]["fallback_classical_insufficient_features"] == 2
        assert summary["scenarios"][4]["estimate_source_counts"]["matched_image_baseline"] == 2
        assert summary["scenarios"][4]["frames"][0]["matcher_diagnostics"] is None
        assert summary["scenarios"][4]["mean_match_score"] is not None
        assert summary["scenarios"][6]["mean_match_score"] is None
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
        assert loaded["scenarios"][5]["scenario_name"] == SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER
        assert loaded["scenarios"][6]["scenario_name"] == SCENARIO_RECURSIVE_CLASSICAL_MATCHER
        assert loaded["neural_matcher_name"] is None
        assert "Sequence Search Debug" in svg_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
