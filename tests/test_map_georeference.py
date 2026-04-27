from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

from satellite_drone_localization.map_georeference import (
    load_map_georeference,
    parse_calibration_point,
)


def test_load_map_georeference_fits_affine_roundtrip(tmp_path: Path) -> None:
    calibration_path = tmp_path / "calibration.json"
    Image.new("RGB", (100, 200), color=(32, 64, 96)).save(tmp_path / "map.png")
    calibration_path.write_text(
        json.dumps(
            {
                "image": str(tmp_path / "map.png"),
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
    assert latitude_deg == pytest.approx(30.9995, abs=1e-7)
    assert longitude_deg == pytest.approx(35.0005, abs=1e-7)

    pixel_x, pixel_y = georeference.latlon_to_pixel(latitude_deg, longitude_deg)
    assert pixel_x == pytest.approx(50.0, abs=1e-7)
    assert pixel_y == pytest.approx(100.0, abs=1e-7)
    assert georeference.max_residual_m == pytest.approx(0.0, abs=1e-6)


def test_parse_calibration_point_rejects_swapped_latitude_range() -> None:
    with pytest.raises(ValueError, match="gps.lat must be within \\[-90, 90\\]"):
        parse_calibration_point(
            {
                "pixel": [10, 20],
                "gps": {"lat": 135.0, "lng": 31.7},
            }
        )


def test_load_map_georeference_requires_three_points(tmp_path: Path) -> None:
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "image": str(tmp_path / "map.png"),
                "calibration_points": [
                    {"pixel": [0, 0], "gps": {"lat": 31.0, "lng": 35.0}},
                    {"pixel": [1, 1], "gps": {"lat": 31.0, "lng": 35.0}},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="at least three"):
        load_map_georeference(calibration_path)


def test_load_map_georeference_resolves_relative_image_path(tmp_path: Path) -> None:
    image_path = tmp_path / "portable_map.png"
    calibration_path = tmp_path / "portable_map_calibration.json"
    Image.new("RGB", (80, 60), color=(120, 80, 40)).save(image_path)
    calibration_path.write_text(
        json.dumps(
            {
                "image": "portable_map.png",
                "calibration_points": [
                    {"pixel": [0, 0], "gps": {"lat": 31.0, "lng": 35.0}},
                    {"pixel": [80, 0], "gps": {"lat": 31.0, "lng": 35.001}},
                    {"pixel": [0, 60], "gps": {"lat": 30.999, "lng": 35.0}},
                ],
            }
        ),
        encoding="utf-8",
    )

    georeference = load_map_georeference(calibration_path)

    assert georeference.image_path == image_path.resolve()
    assert georeference.image_width_px == 80
    assert georeference.image_height_px == 60


def test_load_map_georeference_falls_back_from_stale_absolute_path_to_sibling_image(tmp_path: Path) -> None:
    image_path = tmp_path / "portable_map.png"
    calibration_path = tmp_path / "portable_map_calibration.json"
    Image.new("RGB", (64, 48), color=(12, 24, 36)).save(image_path)
    calibration_path.write_text(
        json.dumps(
            {
                "image": "C:/old-machine/project/data/portable_map.png",
                "calibration_points": [
                    {"pixel": [0, 0], "gps": {"lat": 31.0, "lng": 35.0}},
                    {"pixel": [64, 0], "gps": {"lat": 31.0, "lng": 35.001}},
                    {"pixel": [0, 48], "gps": {"lat": 30.999, "lng": 35.0}},
                ],
            }
        ),
        encoding="utf-8",
    )

    georeference = load_map_georeference(calibration_path)

    assert georeference.image_path == image_path.resolve()
    assert georeference.image_width_px == 64
    assert georeference.image_height_px == 48
