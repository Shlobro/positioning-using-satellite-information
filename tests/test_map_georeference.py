from __future__ import annotations

import json
from pathlib import Path

import pytest

from satellite_drone_localization.map_georeference import (
    load_map_georeference,
    parse_calibration_point,
)


def test_load_map_georeference_fits_affine_roundtrip(tmp_path: Path) -> None:
    calibration_path = tmp_path / "calibration.json"
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
