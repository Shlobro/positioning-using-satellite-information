"""Reusable sequence-search policy helpers."""

from __future__ import annotations

import math

from ..crop import meters_offset_between
from ..map_georeference import MapGeoreference


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
