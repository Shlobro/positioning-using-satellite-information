"""Sequence prior evaluation against a calibrated GIS reference image."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path

from ..crop import DEFAULT_CROP_PADDING_FACTOR, meters_offset_between
from ..geometry import build_replay_geometry_report
from ..map_georeference import MapGeoreference
from ..packet_replay import ReplaySession
from .matcher_classical import ClassicalFeatureMatcher
from .matcher_image_baseline import ImageBaselineMatcher
from .matcher_roma import RoMaRegressionMatcher
from .matcher_placeholder import build_truth_anchored_placeholder_match
from .sequence_artifacts import write_sequence_search_debug_svg, write_sequence_search_summary
from .sequence_policy import (
    build_crop_pixel_bounds,
    constrain_prior_to_image,
    estimate_map_limited_square_side_m,
    evaluate_roma_sequence_likelihood,
    evaluate_roma_temporal_consistency,
    offset_latlon_by_meters,
)


SCENARIO_SEED_ONLY = "seed_only"
SCENARIO_ORACLE_PREVIOUS_TRUTH = "oracle_previous_truth"
SCENARIO_RECURSIVE_ORACLE_ESTIMATE = "recursive_oracle_estimate"
SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER = "recursive_placeholder_matcher"
SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER = "recursive_image_baseline_matcher"
SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER = "recursive_image_map_constrained_matcher"
SCENARIO_RECURSIVE_CLASSICAL_MATCHER = "recursive_classical_matcher"
SCENARIO_RECURSIVE_ROMA_MATCHER = "recursive_roma_matcher"
SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER = "recursive_roma_map_constrained_matcher"
SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER = "recursive_roma_velocity_likelihood_matcher"
SCENARIO_NAMES = (
    SCENARIO_SEED_ONLY,
    SCENARIO_ORACLE_PREVIOUS_TRUTH,
    SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
    SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
    SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
    SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
)


@dataclass(frozen=True)
class SequenceFrameResult:
    """Per-frame sequence-prior evaluation result."""

    timestamp_utc: str
    image_name: str
    elapsed_seconds: float
    delta_seconds: float
    scenario_name: str
    prior_source: str
    prior_latitude_deg: float
    prior_longitude_deg: float
    previous_estimated_latitude_deg: float
    previous_estimated_longitude_deg: float
    velocity_prior_offset_east_m: float
    velocity_prior_offset_north_m: float
    velocity_prior_distance_m: float
    fallback_latitude_deg: float
    fallback_longitude_deg: float
    fallback_distance_m: float
    target_latitude_deg: float
    target_longitude_deg: float
    prior_search_radius_m: float
    crop_side_m: float
    target_offset_east_m: float
    target_offset_north_m: float
    target_distance_m: float
    target_x_in_crop_01: float
    target_y_in_crop_01: float
    contains_target: bool
    estimate_source: str
    estimated_latitude_deg: float
    estimated_longitude_deg: float
    estimated_confidence_radius_m: float
    estimate_offset_east_m: float
    estimate_offset_north_m: float
    estimate_distance_m: float
    state_update_distance_m: float
    estimate_error_delta_from_fallback_m: float
    prior_pixel_x: float
    prior_pixel_y: float
    search_center_was_map_constrained: bool
    crop_was_map_limited: bool
    target_pixel_x: float
    target_pixel_y: float
    estimate_pixel_x: float
    estimate_pixel_y: float
    match_score: float | None
    runner_up_match_score: float | None
    matcher_diagnostics: dict[str, float | int] | None
    crop_min_x: float
    crop_min_y: float
    crop_max_x: float
    crop_max_y: float
    crop_inside_image: bool
    altitude_reference: str


@dataclass(frozen=True)
class SequenceScenarioReport:
    """Aggregate evaluation report for one prior-propagation scenario."""

    scenario_name: str
    description: str
    frame_count: int
    contained_frame_count: int
    matched_frame_count: int
    fallback_frame_count: int
    estimate_source_counts: dict[str, int]
    fallback_source_counts: dict[str, int]
    crop_inside_image_count: int
    map_constrained_frame_count: int
    map_limited_frame_count: int
    first_target_miss_frame_index: int | None
    first_crop_outside_image_frame_index: int | None
    longest_inside_image_streak: int
    max_target_offset_m: float
    average_crop_side_m: float
    mean_estimate_error_m: float
    max_estimate_error_m: float
    final_estimate_error_m: float
    mean_match_score: float | None
    min_match_score: float | None
    frames: list[SequenceFrameResult]


@dataclass(frozen=True)
class SequenceSearchArtifacts:
    """Combined sequence evaluation outputs for one replay session."""

    session_id: str | None
    source_path: Path
    image_path: Path
    image_width_px: int
    image_height_px: int
    georeference_max_residual_m: float
    seed_latitude_deg: float
    seed_longitude_deg: float
    max_speed_mps: float
    base_search_radius_m: float
    measurement_update_radius_m: float
    neural_matcher_name: str | None
    scenarios: list[SequenceScenarioReport]


def build_sequence_search_artifacts(
    session: ReplaySession,
    georeference: MapGeoreference,
    *,
    max_speed_mps: float,
    base_search_radius_m: float = 0.0,
    measurement_update_radius_m: float = 5.0,
    roma_matcher: RoMaRegressionMatcher | None = None,
) -> SequenceSearchArtifacts:
    """Evaluate multiple motion-bounded prior scenarios for one replay session."""
    if max_speed_mps <= 0.0:
        raise ValueError("max_speed_mps must be positive")
    if base_search_radius_m < 0.0:
        raise ValueError("base_search_radius_m must be non-negative")
    if measurement_update_radius_m < 0.0:
        raise ValueError("measurement_update_radius_m must be non-negative")

    geometry_report = build_replay_geometry_report(session)
    seed_frame = session.frames[0]
    timestamps = [_parse_timestamp(frame.timestamp_utc) for frame in session.frames]
    first_timestamp = timestamps[0]

    scenarios = [
        build_sequence_scenario_report(
            scenario_name=SCENARIO_SEED_ONLY,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_ORACLE_PREVIOUS_TRUTH,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
            image_baseline_matcher=ImageBaselineMatcher(georeference.image_path),
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
            image_baseline_matcher=ImageBaselineMatcher(georeference.image_path),
        ),
        build_sequence_scenario_report(
            scenario_name=SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
            session=session,
            georeference=georeference,
            timestamps=timestamps,
            first_timestamp=first_timestamp,
            geometry_report=geometry_report.frames,
            max_speed_mps=max_speed_mps,
            base_search_radius_m=base_search_radius_m,
            measurement_update_radius_m=measurement_update_radius_m,
            classical_feature_matcher=ClassicalFeatureMatcher(georeference.image_path),
        ),
    ]
    if roma_matcher is not None:
        scenarios.append(
            build_sequence_scenario_report(
                scenario_name=SCENARIO_RECURSIVE_ROMA_MATCHER,
                session=session,
                georeference=georeference,
                timestamps=timestamps,
                first_timestamp=first_timestamp,
                geometry_report=geometry_report.frames,
                max_speed_mps=max_speed_mps,
                base_search_radius_m=base_search_radius_m,
                measurement_update_radius_m=measurement_update_radius_m,
                roma_matcher=roma_matcher,
            )
        )
        scenarios.append(
            build_sequence_scenario_report(
                scenario_name=SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
                session=session,
                georeference=georeference,
                timestamps=timestamps,
                first_timestamp=first_timestamp,
                geometry_report=geometry_report.frames,
                max_speed_mps=max_speed_mps,
                base_search_radius_m=base_search_radius_m,
                measurement_update_radius_m=measurement_update_radius_m,
                roma_matcher=roma_matcher,
            )
        )
        scenarios.append(
            build_sequence_scenario_report(
                scenario_name=SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
                session=session,
                georeference=georeference,
                timestamps=timestamps,
                first_timestamp=first_timestamp,
                geometry_report=geometry_report.frames,
                max_speed_mps=max_speed_mps,
                base_search_radius_m=base_search_radius_m,
                measurement_update_radius_m=measurement_update_radius_m,
                roma_matcher=roma_matcher,
            )
        )

    return SequenceSearchArtifacts(
        session_id=session.session_id,
        source_path=session.source_path,
        image_path=georeference.image_path,
        image_width_px=georeference.image_width_px,
        image_height_px=georeference.image_height_px,
        georeference_max_residual_m=georeference.max_residual_m,
        seed_latitude_deg=seed_frame.latitude_deg,
        seed_longitude_deg=seed_frame.longitude_deg,
        max_speed_mps=max_speed_mps,
        base_search_radius_m=base_search_radius_m,
        measurement_update_radius_m=measurement_update_radius_m,
        neural_matcher_name=roma_matcher.model_name if roma_matcher is not None else None,
        scenarios=scenarios,
    )


def build_sequence_scenario_report(
    *,
    scenario_name: str,
    session: ReplaySession,
    georeference: MapGeoreference,
    timestamps: list[datetime],
    first_timestamp: datetime,
    geometry_report: list[object],
    max_speed_mps: float,
    base_search_radius_m: float,
    measurement_update_radius_m: float,
    image_baseline_matcher: ImageBaselineMatcher | None = None,
    classical_feature_matcher: ClassicalFeatureMatcher | None = None,
    roma_matcher: RoMaRegressionMatcher | None = None,
) -> SequenceScenarioReport:
    """Evaluate one sequence-prior scenario."""
    if scenario_name not in SCENARIO_NAMES:
        raise ValueError(f"unsupported scenario_name '{scenario_name}'")

    seed_frame = session.frames[0]
    results: list[SequenceFrameResult] = []
    estimated_latitude_deg = seed_frame.latitude_deg
    estimated_longitude_deg = seed_frame.longitude_deg
    estimated_confidence_radius_m = base_search_radius_m
    estimated_velocity_east_mps = 0.0
    estimated_velocity_north_mps = 0.0

    for index, (frame, geometry, timestamp) in enumerate(zip(session.frames, geometry_report, timestamps, strict=True)):
        previous_estimated_latitude_deg = estimated_latitude_deg
        previous_estimated_longitude_deg = estimated_longitude_deg
        elapsed_seconds = (timestamp - first_timestamp).total_seconds()
        if index == 0:
            delta_seconds = 0.0
            prior_latitude_deg = seed_frame.latitude_deg
            prior_longitude_deg = seed_frame.longitude_deg
            prior_source = "seed_frame_truth"
            prior_search_radius_m = base_search_radius_m
        elif scenario_name == SCENARIO_SEED_ONLY:
            delta_seconds = elapsed_seconds
            prior_latitude_deg = seed_frame.latitude_deg
            prior_longitude_deg = seed_frame.longitude_deg
            prior_source = "seed_frame_truth"
            prior_search_radius_m = base_search_radius_m + (max_speed_mps * delta_seconds)
        elif scenario_name == SCENARIO_ORACLE_PREVIOUS_TRUTH:
            previous_frame = session.frames[index - 1]
            previous_timestamp = timestamps[index - 1]
            delta_seconds = (timestamp - previous_timestamp).total_seconds()
            prior_latitude_deg = previous_frame.latitude_deg
            prior_longitude_deg = previous_frame.longitude_deg
            prior_source = "previous_frame_truth_oracle"
            prior_search_radius_m = base_search_radius_m + (max_speed_mps * delta_seconds)
        else:
            previous_timestamp = timestamps[index - 1]
            delta_seconds = (timestamp - previous_timestamp).total_seconds()
            prior_latitude_deg = estimated_latitude_deg
            prior_longitude_deg = estimated_longitude_deg
            if scenario_name == SCENARIO_RECURSIVE_ORACLE_ESTIMATE:
                prior_source = "previous_estimate_recursive_oracle"
            elif scenario_name == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER:
                prior_source = "previous_estimate_recursive_placeholder"
            elif scenario_name == SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER:
                prior_source = "previous_estimate_recursive_image_baseline"
            elif scenario_name == SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER:
                prior_source = "previous_estimate_recursive_image_map_constrained"
            elif scenario_name == SCENARIO_RECURSIVE_ROMA_MATCHER:
                prior_source = "previous_estimate_recursive_roma"
            elif scenario_name == SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER:
                prior_source = "previous_estimate_recursive_roma_map_constrained"
            elif scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER:
                prior_latitude_deg, prior_longitude_deg = offset_latlon_by_meters(
                    estimated_latitude_deg,
                    estimated_longitude_deg,
                    east_m=estimated_velocity_east_mps * delta_seconds,
                    north_m=estimated_velocity_north_mps * delta_seconds,
                )
                prior_source = "velocity_prediction_recursive_roma_likelihood"
            else:
                prior_source = "previous_estimate_recursive_classical"
            prior_search_radius_m = estimated_confidence_radius_m + (max_speed_mps * delta_seconds)
        crop_side_m = max(geometry.normalized_crop_size_m, prior_search_radius_m * 2.0 * DEFAULT_CROP_PADDING_FACTOR)
        crop_was_map_limited = False
        if is_map_constrained_scenario(scenario_name):
            map_limited_crop_side_m = estimate_map_limited_square_side_m(georeference)
            if crop_side_m > map_limited_crop_side_m:
                crop_side_m = map_limited_crop_side_m
                crop_was_map_limited = True
        half_side_m = crop_side_m / 2.0

        if scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER:
            fallback_latitude_deg = previous_estimated_latitude_deg
            fallback_longitude_deg = previous_estimated_longitude_deg
        else:
            fallback_latitude_deg = prior_latitude_deg
            fallback_longitude_deg = prior_longitude_deg
        search_center_was_map_constrained = False
        if is_map_constrained_scenario(scenario_name):
            (
                prior_latitude_deg,
                prior_longitude_deg,
                search_center_was_map_constrained,
            ) = constrain_prior_to_image(
                georeference=georeference,
                prior_latitude_deg=prior_latitude_deg,
                prior_longitude_deg=prior_longitude_deg,
                half_side_m=half_side_m,
                build_crop_pixel_bounds=build_crop_pixel_bounds,
            )

        velocity_prior_offset_east_m, velocity_prior_offset_north_m = meters_offset_between(
            origin_latitude_deg=previous_estimated_latitude_deg,
            origin_longitude_deg=previous_estimated_longitude_deg,
            target_latitude_deg=prior_latitude_deg,
            target_longitude_deg=prior_longitude_deg,
        )
        fallback_offset_east_m, fallback_offset_north_m = meters_offset_between(
            origin_latitude_deg=frame.latitude_deg,
            origin_longitude_deg=frame.longitude_deg,
            target_latitude_deg=fallback_latitude_deg,
            target_longitude_deg=fallback_longitude_deg,
        )
        target_offset_east_m, target_offset_north_m = meters_offset_between(
            origin_latitude_deg=prior_latitude_deg,
            origin_longitude_deg=prior_longitude_deg,
            target_latitude_deg=frame.latitude_deg,
            target_longitude_deg=frame.longitude_deg,
        )
        target_x_in_crop_01 = (target_offset_east_m + half_side_m) / crop_side_m
        target_y_in_crop_01 = (half_side_m - target_offset_north_m) / crop_side_m
        contains_target = 0.0 <= target_x_in_crop_01 <= 1.0 and 0.0 <= target_y_in_crop_01 <= 1.0

        prior_pixel_x, prior_pixel_y = georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg)
        target_pixel_x, target_pixel_y = georeference.latlon_to_pixel(frame.latitude_deg, frame.longitude_deg)
        crop_min_x, crop_min_y, crop_max_x, crop_max_y = build_crop_pixel_bounds(
            georeference=georeference,
            prior_latitude_deg=prior_latitude_deg,
            prior_longitude_deg=prior_longitude_deg,
            half_side_m=half_side_m,
        )
        crop_inside_image = (
            crop_min_x >= 0.0
            and crop_min_y >= 0.0
            and crop_max_x <= georeference.image_width_px
            and crop_max_y <= georeference.image_height_px
        )
        (
            estimate_source,
            estimate_latitude_deg,
            estimate_longitude_deg,
            estimate_confidence_radius_m,
            match_score,
            runner_up_match_score,
            matcher_diagnostics,
        ) = build_estimate_update(
            scenario_name=scenario_name,
            frame_index=index,
            frame=frame,
            geometry=geometry,
            prior_latitude_deg=prior_latitude_deg,
            prior_longitude_deg=prior_longitude_deg,
            fallback_latitude_deg=fallback_latitude_deg,
            fallback_longitude_deg=fallback_longitude_deg,
            prior_search_radius_m=prior_search_radius_m,
            crop_side_m=crop_side_m,
            target_distance_m=math.hypot(target_offset_east_m, target_offset_north_m),
            target_x_in_crop_01=target_x_in_crop_01,
            target_y_in_crop_01=target_y_in_crop_01,
            contains_target=contains_target,
            crop_inside_image=crop_inside_image,
            georeference=georeference,
            measurement_update_radius_m=measurement_update_radius_m,
            image_baseline_matcher=image_baseline_matcher,
            classical_feature_matcher=classical_feature_matcher,
            roma_matcher=roma_matcher,
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
        )
        estimate_offset_east_m, estimate_offset_north_m = meters_offset_between(
            origin_latitude_deg=frame.latitude_deg,
            origin_longitude_deg=frame.longitude_deg,
            target_latitude_deg=estimate_latitude_deg,
            target_longitude_deg=estimate_longitude_deg,
        )
        estimate_distance_m = math.hypot(estimate_offset_east_m, estimate_offset_north_m)
        state_update_east_m, state_update_north_m = meters_offset_between(
            origin_latitude_deg=previous_estimated_latitude_deg,
            origin_longitude_deg=previous_estimated_longitude_deg,
            target_latitude_deg=estimate_latitude_deg,
            target_longitude_deg=estimate_longitude_deg,
        )
        estimate_pixel_x, estimate_pixel_y = georeference.latlon_to_pixel(estimate_latitude_deg, estimate_longitude_deg)

        results.append(
            SequenceFrameResult(
                timestamp_utc=frame.timestamp_utc,
                image_name=frame.image_name,
                elapsed_seconds=elapsed_seconds,
                delta_seconds=delta_seconds,
                scenario_name=scenario_name,
                prior_source=prior_source,
                prior_latitude_deg=prior_latitude_deg,
                prior_longitude_deg=prior_longitude_deg,
                previous_estimated_latitude_deg=previous_estimated_latitude_deg,
                previous_estimated_longitude_deg=previous_estimated_longitude_deg,
                velocity_prior_offset_east_m=velocity_prior_offset_east_m,
                velocity_prior_offset_north_m=velocity_prior_offset_north_m,
                velocity_prior_distance_m=math.hypot(velocity_prior_offset_east_m, velocity_prior_offset_north_m),
                fallback_latitude_deg=fallback_latitude_deg,
                fallback_longitude_deg=fallback_longitude_deg,
                fallback_distance_m=math.hypot(fallback_offset_east_m, fallback_offset_north_m),
                target_latitude_deg=frame.latitude_deg,
                target_longitude_deg=frame.longitude_deg,
                prior_search_radius_m=prior_search_radius_m,
                crop_side_m=crop_side_m,
                target_offset_east_m=target_offset_east_m,
                target_offset_north_m=target_offset_north_m,
                target_distance_m=math.hypot(target_offset_east_m, target_offset_north_m),
                target_x_in_crop_01=target_x_in_crop_01,
                target_y_in_crop_01=target_y_in_crop_01,
                contains_target=contains_target,
                estimate_source=estimate_source,
                estimated_latitude_deg=estimate_latitude_deg,
                estimated_longitude_deg=estimate_longitude_deg,
                estimated_confidence_radius_m=estimate_confidence_radius_m,
                estimate_offset_east_m=estimate_offset_east_m,
                estimate_offset_north_m=estimate_offset_north_m,
                estimate_distance_m=estimate_distance_m,
                state_update_distance_m=math.hypot(state_update_east_m, state_update_north_m),
                estimate_error_delta_from_fallback_m=estimate_distance_m
                - math.hypot(fallback_offset_east_m, fallback_offset_north_m),
                prior_pixel_x=prior_pixel_x,
                prior_pixel_y=prior_pixel_y,
                target_pixel_x=target_pixel_x,
                target_pixel_y=target_pixel_y,
                estimate_pixel_x=estimate_pixel_x,
                estimate_pixel_y=estimate_pixel_y,
                match_score=match_score,
                runner_up_match_score=runner_up_match_score,
                matcher_diagnostics=matcher_diagnostics,
                search_center_was_map_constrained=search_center_was_map_constrained,
                crop_was_map_limited=crop_was_map_limited,
                crop_min_x=crop_min_x,
                crop_min_y=crop_min_y,
                crop_max_x=crop_max_x,
                crop_max_y=crop_max_y,
                crop_inside_image=crop_inside_image,
                altitude_reference=frame.altitude_reference,
            )
        )

        if scenario_name in (
            SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
            SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
            SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
            SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
            SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
            SCENARIO_RECURSIVE_ROMA_MATCHER,
            SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
            SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
        ):
            if (
                scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER
                and delta_seconds > 0.0
                and is_match_source(estimate_source)
            ):
                velocity_east_m, velocity_north_m = meters_offset_between(
                    origin_latitude_deg=previous_estimated_latitude_deg,
                    origin_longitude_deg=previous_estimated_longitude_deg,
                    target_latitude_deg=estimate_latitude_deg,
                    target_longitude_deg=estimate_longitude_deg,
                )
                estimated_velocity_east_mps = velocity_east_m / delta_seconds
                estimated_velocity_north_mps = velocity_north_m / delta_seconds
            estimated_latitude_deg = estimate_latitude_deg
            estimated_longitude_deg = estimate_longitude_deg
            estimated_confidence_radius_m = estimate_confidence_radius_m

    first_target_miss_frame_index = next((index for index, frame in enumerate(results) if not frame.contains_target), None)
    first_crop_outside_image_frame_index = next(
        (index for index, frame in enumerate(results) if not frame.crop_inside_image),
        None,
    )
    matched_frame_count = sum(1 for frame in results if is_match_source(frame.estimate_source))
    fallback_frame_count = sum(1 for frame in results if is_fallback_source(frame.estimate_source))
    match_scores = [frame.match_score for frame in results if frame.match_score is not None]
    estimate_source_counts = dict(Counter(frame.estimate_source for frame in results))

    return SequenceScenarioReport(
        scenario_name=scenario_name,
        description=describe_scenario(scenario_name),
        frame_count=len(results),
        contained_frame_count=sum(1 for frame in results if frame.contains_target),
        matched_frame_count=matched_frame_count,
        fallback_frame_count=fallback_frame_count,
        estimate_source_counts=estimate_source_counts,
        fallback_source_counts={
            source: count
            for source, count in estimate_source_counts.items()
            if is_fallback_source(source)
        },
        crop_inside_image_count=sum(1 for frame in results if frame.crop_inside_image),
        map_constrained_frame_count=sum(1 for frame in results if frame.search_center_was_map_constrained),
        map_limited_frame_count=sum(1 for frame in results if frame.crop_was_map_limited),
        first_target_miss_frame_index=first_target_miss_frame_index,
        first_crop_outside_image_frame_index=first_crop_outside_image_frame_index,
        longest_inside_image_streak=longest_true_streak(frame.crop_inside_image for frame in results),
        max_target_offset_m=max(frame.target_distance_m for frame in results),
        average_crop_side_m=sum(frame.crop_side_m for frame in results) / len(results),
        mean_estimate_error_m=sum(frame.estimate_distance_m for frame in results) / len(results),
        max_estimate_error_m=max(frame.estimate_distance_m for frame in results),
        final_estimate_error_m=results[-1].estimate_distance_m,
        mean_match_score=(sum(match_scores) / len(match_scores)) if match_scores else None,
        min_match_score=min(match_scores) if match_scores else None,
        frames=results,
    )


def build_estimate_update(
    *,
    scenario_name: str,
    frame_index: int,
    frame,
    geometry,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
    fallback_latitude_deg: float,
    fallback_longitude_deg: float,
    prior_search_radius_m: float,
    crop_side_m: float,
    target_distance_m: float,
    target_x_in_crop_01: float,
    target_y_in_crop_01: float,
    contains_target: bool,
    crop_inside_image: bool,
    georeference: MapGeoreference,
    measurement_update_radius_m: float,
    image_baseline_matcher: ImageBaselineMatcher | None,
    classical_feature_matcher: ClassicalFeatureMatcher | None,
    roma_matcher: RoMaRegressionMatcher | None,
    crop_min_x: float,
    crop_min_y: float,
    crop_max_x: float,
    crop_max_y: float,
) -> tuple[str, float, float, float, float | None, float | None, dict[str, float | int] | None]:
    """Resolve the per-frame localization estimate for one scenario."""
    if scenario_name == SCENARIO_SEED_ONLY:
        return "prior_only_no_matcher", prior_latitude_deg, prior_longitude_deg, prior_search_radius_m, None, None, None

    if scenario_name == SCENARIO_ORACLE_PREVIOUS_TRUTH:
        return (
            "oracle_current_truth_update",
            frame.latitude_deg,
            frame.longitude_deg,
            measurement_update_radius_m,
            None,
            None,
            None,
        )

    if scenario_name == SCENARIO_RECURSIVE_ORACLE_ESTIMATE:
        return (
            "oracle_current_truth_update",
            frame.latitude_deg,
            frame.longitude_deg,
            measurement_update_radius_m,
            None,
            None,
            None,
        )

    if scenario_name == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER:
        decision = build_truth_anchored_placeholder_match(
            frame_index=frame_index,
            heading_deg=frame.heading_deg,
            target_distance_m=target_distance_m,
            target_x_in_crop_01=target_x_in_crop_01,
            target_y_in_crop_01=target_y_in_crop_01,
            crop_side_m=crop_side_m,
            contains_target=contains_target,
            crop_inside_image=crop_inside_image,
            georeference_max_residual_m=georeference.max_residual_m,
            measurement_update_radius_m=measurement_update_radius_m,
        )
        if decision.accepted:
            estimated_latitude_deg, estimated_longitude_deg = offset_latlon_by_meters(
                frame.latitude_deg,
                frame.longitude_deg,
                east_m=decision.estimate_offset_east_m,
                north_m=decision.estimate_offset_north_m,
            )
            return (
                decision.estimate_source,
                estimated_latitude_deg,
                estimated_longitude_deg,
                decision.confidence_radius_m,
                None,
                None,
                None,
            )

        fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
        return (
            decision.estimate_source,
            fallback_latitude_deg,
            fallback_longitude_deg,
            fallback_confidence_radius_m,
            None,
            None,
            None,
        )

    crop_width_px = max(1.0, crop_max_x - crop_min_x)
    crop_height_px = max(1.0, crop_max_y - crop_min_y)
    ground_width_px = geometry.ground_width_m * (crop_width_px / crop_side_m)
    ground_height_px = geometry.ground_height_m * (crop_height_px / crop_side_m)
    if scenario_name in (SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER, SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER):
        if image_baseline_matcher is None:
            raise ValueError("image_baseline_matcher is required for recursive image baseline scenario")
        decision = image_baseline_matcher.match_frame(
            frame_image_path=frame.image_path,
            normalization_rotation_deg=geometry.normalization_rotation_deg,
            ground_width_px=ground_width_px,
            ground_height_px=ground_height_px,
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
            crop_inside_image=crop_inside_image,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference.max_residual_m,
        )
    elif scenario_name == SCENARIO_RECURSIVE_CLASSICAL_MATCHER:
        if classical_feature_matcher is None:
            raise ValueError("classical_feature_matcher is required for recursive classical scenario")
        decision = classical_feature_matcher.match_frame(
            frame_image_path=frame.image_path,
            normalization_rotation_deg=geometry.normalization_rotation_deg,
            ground_width_px=ground_width_px,
            ground_height_px=ground_height_px,
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
            crop_inside_image=crop_inside_image,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference.max_residual_m,
        )
    else:
        if roma_matcher is None:
            raise ValueError("roma_matcher is required for recursive RoMa scenario")
        decision = roma_matcher.match_frame(
            frame_image_path=frame.image_path,
            normalization_rotation_deg=geometry.normalization_rotation_deg,
            ground_width_px=ground_width_px,
            ground_height_px=ground_height_px,
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
            crop_inside_image=crop_inside_image,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference.max_residual_m,
        )
    if decision.accepted:
        estimated_latitude_deg, estimated_longitude_deg = georeference.pixel_to_latlon(
            decision.estimated_pixel_x,
            decision.estimated_pixel_y,
        )
        accepted_diagnostics = getattr(decision, "diagnostics", None)
        if is_map_constrained_scenario(scenario_name):
            update_east_m, update_north_m = meters_offset_between(
                origin_latitude_deg=fallback_latitude_deg,
                origin_longitude_deg=fallback_longitude_deg,
                target_latitude_deg=estimated_latitude_deg,
                target_longitude_deg=estimated_longitude_deg,
            )
            update_distance_m = math.hypot(update_east_m, update_north_m)
            decision_diagnostics = getattr(decision, "diagnostics", None)
            if scenario_name in (
                SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
                SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
            ):
                matcher_diagnostics = dict(decision_diagnostics or {})
                accepted_diagnostics = matcher_diagnostics
                is_consistent, fallback_source = evaluate_roma_temporal_consistency(
                    update_distance_m=update_distance_m,
                    prior_search_radius_m=prior_search_radius_m,
                    measurement_update_radius_m=measurement_update_radius_m,
                    match_score=decision.match_score,
                    diagnostics=matcher_diagnostics,
                )
                if not is_consistent:
                    fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
                    return (
                        fallback_source or "fallback_roma_temporal_inconsistent_update",
                        fallback_latitude_deg,
                        fallback_longitude_deg,
                        fallback_confidence_radius_m,
                        decision.match_score,
                        decision.runner_up_match_score,
                        matcher_diagnostics,
                    )
                if scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER:
                    is_likely, fallback_source = evaluate_roma_sequence_likelihood(
                        update_distance_m=update_distance_m,
                        prior_search_radius_m=prior_search_radius_m,
                        measurement_update_radius_m=measurement_update_radius_m,
                        match_score=decision.match_score,
                        diagnostics=matcher_diagnostics,
                    )
                    if not is_likely:
                        fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
                        return (
                            fallback_source or "fallback_roma_sequence_low_likelihood",
                            fallback_latitude_deg,
                            fallback_longitude_deg,
                            fallback_confidence_radius_m,
                            decision.match_score,
                            decision.runner_up_match_score,
                            matcher_diagnostics,
                        )
            elif update_distance_m > prior_search_radius_m + measurement_update_radius_m:
                fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
                return (
                    "fallback_map_constrained_update_outside_motion_gate",
                    fallback_latitude_deg,
                    fallback_longitude_deg,
                    fallback_confidence_radius_m,
                    decision.match_score,
                    decision.runner_up_match_score,
                    getattr(decision, "diagnostics", None),
                )
        return (
            decision.estimate_source,
            estimated_latitude_deg,
            estimated_longitude_deg,
            decision.confidence_radius_m,
            decision.match_score,
            decision.runner_up_match_score,
            accepted_diagnostics,
        )

    fallback_confidence_radius_m = max(prior_search_radius_m, measurement_update_radius_m)
    return (
        decision.estimate_source,
        fallback_latitude_deg,
        fallback_longitude_deg,
        fallback_confidence_radius_m,
        decision.match_score,
        decision.runner_up_match_score,
        getattr(decision, "diagnostics", None),
    )


def describe_scenario(scenario_name: str) -> str:
    """Return the human-readable scenario description."""
    if scenario_name == SCENARIO_SEED_ONLY:
        return "Use frame-0 truth as the only seed and grow the search radius over total elapsed time."
    if scenario_name == SCENARIO_ORACLE_PREVIOUS_TRUTH:
        return "Upper-bound ceiling that recenters on the previous frame truth and grows radius only over per-frame delta time."
    if scenario_name == SCENARIO_RECURSIVE_ORACLE_ESTIMATE:
        return (
            "Stateful prior loop that recenters on the previous accepted estimate "
            "(oracle stand-in uses hidden truth) and carries a configurable post-update confidence radius."
        )
    if scenario_name == SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER:
        return (
            "Stateful prior loop that feeds back a deterministic truth-anchored placeholder "
            "measurement instead of a perfect oracle update, so drift can be measured before a real matcher exists."
        )
    if scenario_name == SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER:
        return (
            "Stateful prior loop that feeds back a simple real image-template baseline "
            "measured inside the calibrated satellite crop, so recursive tracking can be compared against placeholder and oracle scenarios."
        )
    if scenario_name == SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER:
        return (
            "Stateful image-baseline loop that shifts the search center back into the calibrated map bounds when possible, "
            "so map-boundary persistence can be measured without changing the original raster baseline."
        )
    if scenario_name == SCENARIO_RECURSIVE_CLASSICAL_MATCHER:
        return (
            "Stateful prior loop that feeds back a classical local-feature matcher "
            "inside the calibrated satellite crop, so a stronger non-neural baseline can be compared against the raster baseline and oracle ceilings."
        )
    if scenario_name == SCENARIO_RECURSIVE_ROMA_MATCHER:
        return (
            "Stateful prior loop that feeds back a pretrained RoMa matcher "
            "inside the calibrated satellite crop, so the first neural baseline can be compared directly against the classical and raster baselines."
        )
    if scenario_name == SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER:
        return (
            "Stateful RoMa loop that shifts the search center back into the calibrated map bounds when possible, "
            "so the neural benchmark can test whether boundary-aware bootstrap policy improves persistence."
        )
    if scenario_name == SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER:
        return (
            "Stateful RoMa loop that predicts the next prior from the previous accepted velocity and rejects accepted "
            "updates with low combined motion and matcher-evidence likelihood."
        )
    raise ValueError(f"unsupported scenario_name '{scenario_name}'")


def longest_true_streak(values) -> int:
    """Return the longest consecutive streak of truthy values."""
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def is_match_source(source: str) -> bool:
    """Return whether the estimate source represents an accepted measurement update."""
    return source in {
        "oracle_current_truth_update",
        "matched_placeholder_truth_anchored",
        "matched_image_baseline",
        "matched_classical_feature",
        "matched_roma",
    }


def is_fallback_source(source: str) -> bool:
    """Return whether the estimate source represents a fallback instead of a measurement update."""
    return source.startswith("fallback_") or source == "prior_only_no_matcher"


def is_map_constrained_scenario(scenario_name: str) -> bool:
    """Return whether a scenario uses image-boundary-aware search-center adjustment."""
    return scenario_name in {
        SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
        SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
        SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
    }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
