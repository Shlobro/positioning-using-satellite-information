"""Tests for tools/localization_gui/pipeline_runner.py.

These tests exercise the headless adapter only — no Qt, no display. They run
the placeholder pipeline against a synthetic calibrated tile, plus the simple
image-baseline pipeline to confirm wiring of the heatmap path.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from localization_gui.pipeline_runner import (  # noqa: E402
    PIPELINE_IMAGE_BASELINE,
    PIPELINE_PLACEHOLDER,
    RunRequest,
    SEQUENCE_SCENARIOS,
    SINGLE_IMAGE_PIPELINES,
    execute_run_request,
    list_pipelines_for_input,
    load_calibrated_tile,
    run_single_image,
)
from localization_gui.single_image_input import write_single_image_packet_template  # noqa: E402

from satellite_drone_localization.packet_replay import load_replay_session  # noqa: E402


def _make_temp_dir() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def _write_synthetic_map(path: Path) -> None:
    image = Image.new("L", (240, 240), color=96)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 90, 80), fill=200)
    draw.rectangle((140, 30, 210, 90), fill=232)
    draw.rectangle((30, 130, 100, 200), fill=148)
    draw.rectangle((150, 140, 220, 210), fill=180)
    draw.line((120, 0, 120, 240), fill=28, width=6)
    draw.line((0, 110, 240, 110), fill=36, width=6)
    image.save(path)


def _write_calibration(calibration_path: Path, map_path: Path) -> None:
    calibration_path.write_text(
        json.dumps(
            {
                "image": map_path.name,
                "image_size_px": [240, 240],
                "calibration_points": [
                    {"pixel": [0, 0], "gps": {"lat": 31.0, "lng": 35.0}},
                    {"pixel": [240, 0], "gps": {"lat": 31.0, "lng": 35.0024}},
                    {"pixel": [0, 240], "gps": {"lat": 30.9976, "lng": 35.0}},
                    {"pixel": [240, 240], "gps": {"lat": 30.9976, "lng": 35.0024}},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_frame_from_map(
    map_path: Path, frame_path: Path, center_x: int, center_y: int
) -> None:
    with Image.open(map_path) as image:
        patch = image.crop((center_x - 30, center_y - 17, center_x + 30, center_y + 17))
        frame = patch.resize((192, 108), resample=Image.Resampling.BILINEAR)
        frame.save(frame_path)


def _write_single_frame_replay(replay_path: Path, frame_path: Path) -> None:
    sidecar_path = frame_path.with_name(frame_path.stem + "_packet.json")
    replay_path.write_text(sidecar_path.read_text(encoding="utf-8"), encoding="utf-8")


def test_list_pipelines_for_input_returns_known_choices() -> None:
    single = list_pipelines_for_input("single")
    sequence = list_pipelines_for_input("sequence")
    assert single == list(SINGLE_IMAGE_PIPELINES)
    assert sequence == list(SEQUENCE_SCENARIOS)
    assert PIPELINE_PLACEHOLDER in single
    assert PIPELINE_IMAGE_BASELINE in single


def test_load_calibrated_tile_requires_sidecar() -> None:
    repo_root = _make_temp_dir()
    map_path = repo_root / "map.png"
    _write_synthetic_map(map_path)
    try:
        load_calibrated_tile(map_path)
    except FileNotFoundError as exc:
        assert "calibration" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError when sidecar is missing")


def test_run_single_image_placeholder_returns_one_frame_with_truth_metrics() -> None:
    repo_root = _make_temp_dir()
    map_path = repo_root / "map.png"
    calibration_path = repo_root / "map_calibration.json"
    frame_path = repo_root / "frame.png"
    _write_synthetic_map(map_path)
    _write_calibration(calibration_path, map_path)
    _write_frame_from_map(map_path, frame_path, center_x=120, center_y=120)

    write_single_image_packet_template(
        frame_path,
        latitude_deg=30.9988,
        longitude_deg=35.0012,
        altitude_m=16.0,
        heading_deg=0.0,
        camera_hfov_deg=84.0,
        camera_vfov_deg=None,
        frame_width_px=192,
        frame_height_px=108,
        timestamp_utc="2026-04-30T10:00:00Z",
    )

    georeference = load_calibrated_tile(map_path)
    sidecar_session = load_replay_session(frame_path.with_name(frame_path.stem + "_packet.json"))

    result = run_single_image(
        georeference=georeference,
        session=sidecar_session,
        pipeline=PIPELINE_PLACEHOLDER,
        prior_latitude_deg=30.9988,
        prior_longitude_deg=35.0012,
        prior_search_radius_m=25.0,
    )
    assert result.pipeline == PIPELINE_PLACEHOLDER
    assert len(result.frames) == 1
    frame = result.frames[0]
    assert frame.truth_latitude_deg is not None
    assert frame.truth_longitude_deg is not None
    assert frame.predicted_pixel_x >= 0.0
    assert frame.predicted_pixel_y >= 0.0
    assert frame.confidence_radius_m > 0.0


def test_run_single_image_image_baseline_produces_heatmap() -> None:
    repo_root = _make_temp_dir()
    map_path = repo_root / "map.png"
    calibration_path = repo_root / "map_calibration.json"
    frame_path = repo_root / "frame.png"
    _write_synthetic_map(map_path)
    _write_calibration(calibration_path, map_path)
    _write_frame_from_map(map_path, frame_path, center_x=120, center_y=120)

    write_single_image_packet_template(
        frame_path,
        latitude_deg=30.9988,
        longitude_deg=35.0012,
        altitude_m=16.0,
        heading_deg=0.0,
        camera_hfov_deg=84.0,
        camera_vfov_deg=None,
        frame_width_px=192,
        frame_height_px=108,
        timestamp_utc="2026-04-30T10:00:00Z",
    )

    georeference = load_calibrated_tile(map_path)
    sidecar_session = load_replay_session(frame_path.with_name(frame_path.stem + "_packet.json"))
    result = run_single_image(
        georeference=georeference,
        session=sidecar_session,
        pipeline=PIPELINE_IMAGE_BASELINE,
        prior_latitude_deg=30.9988,
        prior_longitude_deg=35.0012,
        prior_search_radius_m=30.0,
    )
    assert len(result.frames) == 1
    # Heatmap may be None if the synthetic crop is degenerate, but normal-case
    # synthetic templates here are big enough for the grid to populate.
    assert result.heatmap is not None
    assert result.heatmap.ndim == 2
    assert result.heatmap_origin_pixel is not None
    assert result.heatmap_pixel_size is not None


def test_execute_run_request_dispatches_single_and_sequence_modes() -> None:
    repo_root = _make_temp_dir()
    map_path = repo_root / "map.png"
    calibration_path = repo_root / "map_calibration.json"
    frame_path = repo_root / "frame.png"
    replay_path = repo_root / "replay.jsonl"
    _write_synthetic_map(map_path)
    _write_calibration(calibration_path, map_path)
    _write_frame_from_map(map_path, frame_path, center_x=120, center_y=120)

    write_single_image_packet_template(
        frame_path,
        latitude_deg=30.9988,
        longitude_deg=35.0012,
        altitude_m=16.0,
        heading_deg=0.0,
        camera_hfov_deg=84.0,
        camera_vfov_deg=None,
        frame_width_px=192,
        frame_height_px=108,
        timestamp_utc="2026-04-30T10:00:00Z",
    )
    _write_single_frame_replay(replay_path, frame_path)

    georeference = load_calibrated_tile(map_path)
    sidecar_session = load_replay_session(frame_path.with_name(frame_path.stem + "_packet.json"))

    single_result = execute_run_request(
        RunRequest(
            input_mode="single",
            pipeline=PIPELINE_PLACEHOLDER,
            georeference=georeference,
            session=sidecar_session,
            prior_latitude_deg=30.9988,
            prior_longitude_deg=35.0012,
            prior_search_radius_m=25.0,
        )
    )
    assert len(single_result.frames) == 1
    assert single_result.pipeline == PIPELINE_PLACEHOLDER

    sequence_result = execute_run_request(
        RunRequest(
            input_mode="sequence",
            pipeline=SEQUENCE_SCENARIOS[0],
            georeference=georeference,
            replay_path=replay_path,
        )
    )
    assert sequence_result.pipeline == SEQUENCE_SCENARIOS[0]
    assert len(sequence_result.frames) == 1
