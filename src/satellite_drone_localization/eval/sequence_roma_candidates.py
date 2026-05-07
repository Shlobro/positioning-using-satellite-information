"""RoMa multicandidate crop evaluation helpers for sequence search."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from ..crop import meters_offset_between
from ..map_georeference import MapGeoreference
from .matcher_roma import RoMaMatchDecision, RoMaRegressionMatcher
from .sequence_policy import (
    build_crop_pixel_bounds,
    constrain_prior_to_image,
    evaluate_roma_temporal_consistency,
    offset_latlon_by_meters,
)


@dataclass(frozen=True)
class CandidateAttempt:
    """One prior-centered RoMa crop candidate and its gated outcome."""

    rank_index: int
    offset_east_m: float
    offset_north_m: float
    latitude_deg: float
    longitude_deg: float
    crop_inside_image: bool
    was_map_constrained: bool
    update_distance_m: float | None
    temporal_accepted: bool
    fallback_source: str | None
    decision: RoMaMatchDecision


def evaluate_roma_multicandidate_update(
    *,
    frame_image_path: Path,
    normalization_rotation_deg: float,
    ground_width_m: float,
    ground_height_m: float,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
    fallback_latitude_deg: float,
    fallback_longitude_deg: float,
    prior_search_radius_m: float,
    crop_side_m: float,
    georeference: MapGeoreference,
    roma_matcher: RoMaRegressionMatcher,
    measurement_update_radius_m: float,
) -> tuple[str, float, float, float, float | None, float | None, dict[str, float | int] | None]:
    """Evaluate a deterministic center-plus-ring set of RoMa crop candidates."""
    attempts: list[CandidateAttempt] = []
    for rank_index, (offset_east_m, offset_north_m) in enumerate(
        build_multicandidate_offsets(prior_search_radius_m, measurement_update_radius_m)
    ):
        candidate_latitude_deg, candidate_longitude_deg = offset_latlon_by_meters(
            prior_latitude_deg,
            prior_longitude_deg,
            east_m=offset_east_m,
            north_m=offset_north_m,
        )
        half_side_m = crop_side_m / 2.0
        candidate_latitude_deg, candidate_longitude_deg, was_map_constrained = constrain_prior_to_image(
            georeference=georeference,
            prior_latitude_deg=candidate_latitude_deg,
            prior_longitude_deg=candidate_longitude_deg,
            half_side_m=half_side_m,
            build_crop_pixel_bounds=build_crop_pixel_bounds,
        )
        crop_min_x, crop_min_y, crop_max_x, crop_max_y = build_crop_pixel_bounds(
            georeference=georeference,
            prior_latitude_deg=candidate_latitude_deg,
            prior_longitude_deg=candidate_longitude_deg,
            half_side_m=half_side_m,
        )
        crop_inside_image = (
            crop_min_x >= 0.0
            and crop_min_y >= 0.0
            and crop_max_x <= georeference.image_width_px
            and crop_max_y <= georeference.image_height_px
        )
        crop_width_px = max(1.0, crop_max_x - crop_min_x)
        crop_height_px = max(1.0, crop_max_y - crop_min_y)
        decision = roma_matcher.match_frame(
            frame_image_path=frame_image_path,
            normalization_rotation_deg=normalization_rotation_deg,
            ground_width_px=ground_width_m * (crop_width_px / crop_side_m),
            ground_height_px=ground_height_m * (crop_height_px / crop_side_m),
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
            crop_inside_image=crop_inside_image,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference.max_residual_m,
        )
        attempts.append(
            _gate_candidate_attempt(
                rank_index=rank_index,
                offset_east_m=offset_east_m,
                offset_north_m=offset_north_m,
                candidate_latitude_deg=candidate_latitude_deg,
                candidate_longitude_deg=candidate_longitude_deg,
                crop_inside_image=crop_inside_image,
                was_map_constrained=was_map_constrained,
                decision=decision,
                fallback_latitude_deg=fallback_latitude_deg,
                fallback_longitude_deg=fallback_longitude_deg,
                prior_search_radius_m=prior_search_radius_m,
                measurement_update_radius_m=measurement_update_radius_m,
                georeference=georeference,
            )
        )

    selected_attempt = _select_multicandidate_attempt(attempts)
    diagnostics = _summarize_candidate_attempts(attempts, selected_attempt)
    selected_decision = selected_attempt.decision
    diagnostics.update(dict(selected_decision.diagnostics or {}))
    if selected_attempt.temporal_accepted:
        estimate_latitude_deg, estimate_longitude_deg = georeference.pixel_to_latlon(
            selected_decision.estimated_pixel_x,
            selected_decision.estimated_pixel_y,
        )
        return (
            selected_decision.estimate_source,
            estimate_latitude_deg,
            estimate_longitude_deg,
            selected_decision.confidence_radius_m,
            selected_decision.match_score,
            selected_decision.runner_up_match_score,
            diagnostics,
        )

    fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
    return (
        selected_attempt.fallback_source or selected_decision.estimate_source,
        fallback_latitude_deg,
        fallback_longitude_deg,
        fallback_confidence_radius_m,
        selected_decision.match_score,
        selected_decision.runner_up_match_score,
        diagnostics,
    )


def build_multicandidate_offsets(
    prior_search_radius_m: float,
    measurement_update_radius_m: float,
) -> tuple[tuple[float, float], ...]:
    """Return center plus a deterministic 8-neighbor ring inside the motion radius."""
    candidate_radius_m = min(
        prior_search_radius_m,
        max(measurement_update_radius_m * 2.0, prior_search_radius_m * 0.5),
    )
    if candidate_radius_m <= 0.0:
        return ((0.0, 0.0),)
    diagonal_m = candidate_radius_m / math.sqrt(2.0)
    return (
        (0.0, 0.0),
        (candidate_radius_m, 0.0),
        (-candidate_radius_m, 0.0),
        (0.0, candidate_radius_m),
        (0.0, -candidate_radius_m),
        (diagonal_m, diagonal_m),
        (diagonal_m, -diagonal_m),
        (-diagonal_m, diagonal_m),
        (-diagonal_m, -diagonal_m),
    )


def _gate_candidate_attempt(
    *,
    rank_index: int,
    offset_east_m: float,
    offset_north_m: float,
    candidate_latitude_deg: float,
    candidate_longitude_deg: float,
    crop_inside_image: bool,
    was_map_constrained: bool,
    decision: RoMaMatchDecision,
    fallback_latitude_deg: float,
    fallback_longitude_deg: float,
    prior_search_radius_m: float,
    measurement_update_radius_m: float,
    georeference: MapGeoreference,
) -> CandidateAttempt:
    if not decision.accepted:
        return CandidateAttempt(
            rank_index=rank_index,
            offset_east_m=offset_east_m,
            offset_north_m=offset_north_m,
            latitude_deg=candidate_latitude_deg,
            longitude_deg=candidate_longitude_deg,
            crop_inside_image=crop_inside_image,
            was_map_constrained=was_map_constrained,
            update_distance_m=None,
            temporal_accepted=False,
            fallback_source=decision.estimate_source,
            decision=decision,
        )
    estimate_latitude_deg, estimate_longitude_deg = georeference.pixel_to_latlon(
        decision.estimated_pixel_x,
        decision.estimated_pixel_y,
    )
    update_east_m, update_north_m = meters_offset_between(
        origin_latitude_deg=fallback_latitude_deg,
        origin_longitude_deg=fallback_longitude_deg,
        target_latitude_deg=estimate_latitude_deg,
        target_longitude_deg=estimate_longitude_deg,
    )
    diagnostics = dict(decision.diagnostics or {})
    temporal_accepted, fallback_source = evaluate_roma_temporal_consistency(
        update_distance_m=math.hypot(update_east_m, update_north_m),
        prior_search_radius_m=prior_search_radius_m,
        measurement_update_radius_m=measurement_update_radius_m,
        match_score=decision.match_score,
        diagnostics=diagnostics,
    )
    decision = RoMaMatchDecision(
        accepted=decision.accepted,
        estimate_source=decision.estimate_source,
        confidence_radius_m=decision.confidence_radius_m,
        estimated_pixel_x=decision.estimated_pixel_x,
        estimated_pixel_y=decision.estimated_pixel_y,
        match_score=decision.match_score,
        runner_up_match_score=decision.runner_up_match_score,
        diagnostics=diagnostics,
    )
    return CandidateAttempt(
        rank_index=rank_index,
        offset_east_m=offset_east_m,
        offset_north_m=offset_north_m,
        latitude_deg=candidate_latitude_deg,
        longitude_deg=candidate_longitude_deg,
        crop_inside_image=crop_inside_image,
        was_map_constrained=was_map_constrained,
        update_distance_m=math.hypot(update_east_m, update_north_m),
        temporal_accepted=temporal_accepted,
        fallback_source=fallback_source,
        decision=decision,
    )


def _select_multicandidate_attempt(attempts: list[CandidateAttempt]) -> CandidateAttempt:
    accepted_attempts = [attempt for attempt in attempts if attempt.temporal_accepted]
    if accepted_attempts:
        return max(accepted_attempts, key=_candidate_sort_key)
    return max(attempts, key=_candidate_sort_key)


def _candidate_sort_key(attempt: CandidateAttempt) -> tuple[float, float, float]:
    score = -1.0 if attempt.decision.match_score is None else attempt.decision.match_score
    inlier_count = 0.0
    if attempt.decision.diagnostics is not None:
        inlier_count = float(attempt.decision.diagnostics.get("inlier_count", 0.0))
    distance_penalty = -(attempt.update_distance_m or 0.0)
    return score, inlier_count, distance_penalty


def _summarize_candidate_attempts(
    attempts: list[CandidateAttempt],
    selected_attempt: CandidateAttempt,
) -> dict[str, float | int]:
    return {
        "candidate_count": len(attempts),
        "candidate_crop_inside_count": sum(1 for attempt in attempts if attempt.crop_inside_image),
        "candidate_map_constrained_count": sum(1 for attempt in attempts if attempt.was_map_constrained),
        "candidate_raw_accepted_count": sum(1 for attempt in attempts if attempt.decision.accepted),
        "candidate_temporal_accepted_count": sum(1 for attempt in attempts if attempt.temporal_accepted),
        "selected_candidate_rank_index": selected_attempt.rank_index,
        "selected_candidate_offset_east_m": selected_attempt.offset_east_m,
        "selected_candidate_offset_north_m": selected_attempt.offset_north_m,
        "selected_candidate_update_distance_m": selected_attempt.update_distance_m or 0.0,
        "selected_candidate_temporal_accepted": int(selected_attempt.temporal_accepted),
    }
