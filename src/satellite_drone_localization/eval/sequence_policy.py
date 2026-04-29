"""Reusable sequence-search policy helpers."""

from __future__ import annotations

import math

from ..crop import meters_offset_between
from ..map_georeference import MapGeoreference

ROMA_TEMPORAL_LARGE_UPDATE_MIN_M = 20.0
ROMA_TEMPORAL_MIN_LARGE_UPDATE_SCORE = 0.75
ROMA_TEMPORAL_MIN_LARGE_UPDATE_INLIER_RATIO = 0.18
ROMA_TEMPORAL_MIN_LARGE_UPDATE_COVERAGE = 0.42
EARTH_RADIUS_M = 6_378_137.0


def offset_latlon_by_meters(
    latitude_deg: float,
    longitude_deg: float,
    *,
    east_m: float,
    north_m: float,
) -> tuple[float, float]:
    """Offset one nearby WGS84 point by east/north meters."""
    latitude_rad = math.radians(latitude_deg)
    latitude_out = latitude_deg + math.degrees(north_m / EARTH_RADIUS_M)
    longitude_out = longitude_deg + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(latitude_rad)))
    return latitude_out, longitude_out


def build_crop_pixel_bounds(
    *,
    georeference: MapGeoreference,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
    half_side_m: float,
) -> tuple[float, float, float, float]:
    """Project the four crop corners into image pixels and return their bounding box."""
    corners = [
        offset_latlon_by_meters(prior_latitude_deg, prior_longitude_deg, east_m=-half_side_m, north_m=half_side_m),
        offset_latlon_by_meters(prior_latitude_deg, prior_longitude_deg, east_m=half_side_m, north_m=half_side_m),
        offset_latlon_by_meters(prior_latitude_deg, prior_longitude_deg, east_m=half_side_m, north_m=-half_side_m),
        offset_latlon_by_meters(prior_latitude_deg, prior_longitude_deg, east_m=-half_side_m, north_m=-half_side_m),
    ]
    pixel_corners = [georeference.latlon_to_pixel(latitude_deg, longitude_deg) for latitude_deg, longitude_deg in corners]
    xs = [pixel_x for pixel_x, _ in pixel_corners]
    ys = [pixel_y for _, pixel_y in pixel_corners]
    return min(xs), min(ys), max(xs), max(ys)


def constrain_prior_to_image(
    *,
    georeference: MapGeoreference,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
    half_side_m: float,
    build_crop_pixel_bounds,
) -> tuple[float, float, bool]:
    """Shift a search center just enough for its crop to overlap the image bounds better."""
    crop_min_x, crop_min_y, crop_max_x, crop_max_y = build_crop_pixel_bounds(
        georeference=georeference,
        prior_latitude_deg=prior_latitude_deg,
        prior_longitude_deg=prior_longitude_deg,
        half_side_m=half_side_m,
    )
    crop_width_px = crop_max_x - crop_min_x
    crop_height_px = crop_max_y - crop_min_y
    prior_pixel_x, prior_pixel_y = georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg)

    if (
        crop_min_x >= 0.0
        and crop_min_y >= 0.0
        and crop_max_x <= georeference.image_width_px
        and crop_max_y <= georeference.image_height_px
    ):
        return prior_latitude_deg, prior_longitude_deg, False

    if crop_width_px <= georeference.image_width_px:
        shift_x = max(0.0 - crop_min_x, min(0.0, georeference.image_width_px - crop_max_x))
    else:
        shift_x = (georeference.image_width_px / 2.0) - prior_pixel_x

    if crop_height_px <= georeference.image_height_px:
        shift_y = max(0.0 - crop_min_y, min(0.0, georeference.image_height_px - crop_max_y))
    else:
        shift_y = (georeference.image_height_px / 2.0) - prior_pixel_y

    if abs(shift_x) < 1e-9 and abs(shift_y) < 1e-9:
        return prior_latitude_deg, prior_longitude_deg, False

    return (*georeference.pixel_to_latlon(prior_pixel_x + shift_x, prior_pixel_y + shift_y), True)


def estimate_map_limited_square_side_m(georeference: MapGeoreference) -> float:
    """Return the largest conservative square crop side that can fit in the calibrated image."""
    center_x = georeference.image_width_px / 2.0
    center_y = georeference.image_height_px / 2.0
    left_lat, left_lon = georeference.pixel_to_latlon(0.0, center_y)
    right_lat, right_lon = georeference.pixel_to_latlon(georeference.image_width_px, center_y)
    top_lat, top_lon = georeference.pixel_to_latlon(center_x, 0.0)
    bottom_lat, bottom_lon = georeference.pixel_to_latlon(center_x, georeference.image_height_px)
    width_east_m, width_north_m = meters_offset_between(
        origin_latitude_deg=left_lat,
        origin_longitude_deg=left_lon,
        target_latitude_deg=right_lat,
        target_longitude_deg=right_lon,
    )
    height_east_m, height_north_m = meters_offset_between(
        origin_latitude_deg=top_lat,
        origin_longitude_deg=top_lon,
        target_latitude_deg=bottom_lat,
        target_longitude_deg=bottom_lon,
    )
    image_width_m = math.hypot(width_east_m, width_north_m)
    image_height_m = math.hypot(height_east_m, height_north_m)
    return max(1.0, min(image_width_m, image_height_m) * 0.99)


def evaluate_roma_temporal_consistency(
    *,
    update_distance_m: float,
    prior_search_radius_m: float,
    measurement_update_radius_m: float,
    match_score: float | None,
    diagnostics: dict[str, float | int],
) -> tuple[bool, str | None]:
    """Return whether a RoMa update is consistent with prior motion and evidence quality."""
    motion_limit_m = max(prior_search_radius_m, measurement_update_radius_m)
    large_update_threshold_m = max(ROMA_TEMPORAL_LARGE_UPDATE_MIN_M, measurement_update_radius_m * 4.0)
    inlier_ratio = float(diagnostics.get("inlier_ratio", 0.0))
    spatial_coverage = float(diagnostics.get("inlier_spatial_coverage", 0.0))
    score = 0.0 if match_score is None else match_score
    weak_large_update_evidence = (
        score < ROMA_TEMPORAL_MIN_LARGE_UPDATE_SCORE
        or inlier_ratio < ROMA_TEMPORAL_MIN_LARGE_UPDATE_INLIER_RATIO
        or spatial_coverage < ROMA_TEMPORAL_MIN_LARGE_UPDATE_COVERAGE
    )
    diagnostics["temporal_update_distance_m"] = update_distance_m
    diagnostics["temporal_motion_limit_m"] = motion_limit_m
    diagnostics["temporal_large_update_threshold_m"] = large_update_threshold_m
    diagnostics["temporal_weak_large_update_evidence"] = int(weak_large_update_evidence)

    if update_distance_m > motion_limit_m:
        return False, "fallback_roma_temporal_motion_gate"
    if update_distance_m > large_update_threshold_m and weak_large_update_evidence:
        return False, "fallback_roma_temporal_weak_large_update"
    return True, None
