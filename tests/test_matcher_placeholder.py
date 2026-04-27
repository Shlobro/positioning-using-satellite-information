from __future__ import annotations

from satellite_drone_localization.eval.matcher_placeholder import build_truth_anchored_placeholder_match


def test_placeholder_match_accepts_centered_target_inside_image() -> None:
    decision = build_truth_anchored_placeholder_match(
        frame_index=1,
        heading_deg=90.0,
        target_distance_m=3.0,
        target_x_in_crop_01=0.5,
        target_y_in_crop_01=0.5,
        crop_side_m=70.0,
        contains_target=True,
        crop_inside_image=True,
        georeference_max_residual_m=0.25,
        measurement_update_radius_m=5.0,
    )

    assert decision.accepted is True
    assert decision.estimate_source == "matched_placeholder_truth_anchored"
    assert decision.confidence_radius_m <= 5.0


def test_placeholder_match_falls_back_when_crop_is_off_image() -> None:
    decision = build_truth_anchored_placeholder_match(
        frame_index=1,
        heading_deg=90.0,
        target_distance_m=3.0,
        target_x_in_crop_01=0.5,
        target_y_in_crop_01=0.5,
        crop_side_m=70.0,
        contains_target=True,
        crop_inside_image=False,
        georeference_max_residual_m=0.25,
        measurement_update_radius_m=5.0,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_crop_outside_image"
