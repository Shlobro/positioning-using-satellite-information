"""Deterministic placeholder matcher for sequence-localization experiments."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PlaceholderMatchDecision:
    """Outcome of one placeholder matcher update."""

    accepted: bool
    estimate_source: str
    confidence_radius_m: float
    estimate_offset_east_m: float
    estimate_offset_north_m: float


def build_truth_anchored_placeholder_match(
    *,
    frame_index: int,
    heading_deg: float,
    target_distance_m: float,
    target_x_in_crop_01: float,
    target_y_in_crop_01: float,
    crop_side_m: float,
    contains_target: bool,
    crop_inside_image: bool,
    georeference_max_residual_m: float,
    measurement_update_radius_m: float,
) -> PlaceholderMatchDecision:
    """Return a deterministic stand-in for a future image-matcher update."""
    if measurement_update_radius_m < 0.0:
        raise ValueError("measurement_update_radius_m must be non-negative")

    if not contains_target:
        return PlaceholderMatchDecision(
            accepted=False,
            estimate_source="fallback_target_outside_crop",
            confidence_radius_m=measurement_update_radius_m,
            estimate_offset_east_m=0.0,
            estimate_offset_north_m=0.0,
        )

    if not crop_inside_image:
        return PlaceholderMatchDecision(
            accepted=False,
            estimate_source="fallback_crop_outside_image",
            confidence_radius_m=measurement_update_radius_m,
            estimate_offset_east_m=0.0,
            estimate_offset_north_m=0.0,
        )

    edge_margin_ratio = min(
        target_x_in_crop_01,
        1.0 - target_x_in_crop_01,
        target_y_in_crop_01,
        1.0 - target_y_in_crop_01,
    )
    if edge_margin_ratio < 0.08:
        return PlaceholderMatchDecision(
            accepted=False,
            estimate_source="fallback_low_edge_margin",
            confidence_radius_m=measurement_update_radius_m,
            estimate_offset_east_m=0.0,
            estimate_offset_north_m=0.0,
        )

    base_error_m = max(1.0, georeference_max_residual_m * 2.0)
    distance_penalty_m = min(measurement_update_radius_m * 0.35, target_distance_m * 0.08)
    footprint_penalty_m = min(measurement_update_radius_m * 0.35, crop_side_m * 0.015)
    edge_penalty_m = min(
        measurement_update_radius_m * 0.2,
        max(0.0, 0.25 - edge_margin_ratio) * measurement_update_radius_m,
    )
    estimate_error_m = min(
        measurement_update_radius_m,
        base_error_m + distance_penalty_m + footprint_penalty_m + edge_penalty_m,
    )

    angle_deg = (frame_index * 53.0 + heading_deg * 0.5 + crop_side_m * 0.1) % 360.0
    angle_rad = math.radians(angle_deg)
    return PlaceholderMatchDecision(
        accepted=True,
        estimate_source="matched_placeholder_truth_anchored",
        confidence_radius_m=max(base_error_m, estimate_error_m),
        estimate_offset_east_m=estimate_error_m * math.cos(angle_rad),
        estimate_offset_north_m=estimate_error_m * math.sin(angle_rad),
    )
