"""Adapter that drives existing matchers and sequence_search from GUI inputs.

The GUI itself stays display-only. This module turns "user picked tile T,
prior P, radius R, pipeline X, input I" into one or more runs against the
existing project pipeline and returns a uniform `RunResult` the GUI can render.

Heatmap source policy (matches what was discussed with the user):

- `image_baseline` / `image_map_constrained` / `placeholder` / `seed_only` /
  `oracle`: the heatmap is a coarse template-match score grid computed locally
  here. This is cheap and matches the image-baseline matcher's evidence model.
- `classical`: no heatmap. Classical features do not produce a dense score map
  worth visualizing, and recomputing one would be misleading.
- `roma`: heatmap rendered from RoMa's per-pixel certainty if RoMa returns it.
  Falls back to "no heatmap" if RoMa is not selected or fails to return certainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

from satellite_drone_localization.crop import meters_offset_between
from satellite_drone_localization.geometry import (
    NormalizedFrameGeometry,
    normalize_frame_geometry,
)
from satellite_drone_localization.map_georeference import (
    MapGeoreference,
    load_map_georeference,
)
from satellite_drone_localization.packet_replay import ReplaySession, load_replay_session
from satellite_drone_localization.eval.matcher_classical import ClassicalFeatureMatcher
from satellite_drone_localization.eval.matcher_image_baseline import ImageBaselineMatcher
from satellite_drone_localization.eval.matcher_placeholder import (
    build_truth_anchored_placeholder_match,
)
from satellite_drone_localization.eval.sequence_policy import build_crop_pixel_bounds
from satellite_drone_localization.eval.sequence_search import (
    SCENARIO_NAMES,
    build_sequence_search_artifacts,
)


PIPELINE_PLACEHOLDER = "placeholder"
PIPELINE_IMAGE_BASELINE = "image_baseline"
PIPELINE_IMAGE_MAP_CONSTRAINED = "image_map_constrained"
PIPELINE_CLASSICAL = "classical"
PIPELINE_ROMA = "roma"
PIPELINE_ROMA_MAP_CONSTRAINED = "roma_map_constrained"

SINGLE_IMAGE_PIPELINES = (
    PIPELINE_PLACEHOLDER,
    PIPELINE_IMAGE_BASELINE,
    PIPELINE_IMAGE_MAP_CONSTRAINED,
    PIPELINE_CLASSICAL,
    PIPELINE_ROMA,
    PIPELINE_ROMA_MAP_CONSTRAINED,
)

SEQUENCE_SCENARIOS = SCENARIO_NAMES

HEATMAP_GRID_STEP_DIVISOR = 24


@dataclass(frozen=True)
class FramePrediction:
    """One frame's predicted location plus diagnostics."""

    image_name: str
    image_path: Path
    accepted: bool
    estimate_source: str
    predicted_latitude_deg: float
    predicted_longitude_deg: float
    predicted_pixel_x: float
    predicted_pixel_y: float
    truth_latitude_deg: float | None
    truth_longitude_deg: float | None
    truth_pixel_x: float | None
    truth_pixel_y: float | None
    error_m: float | None
    match_score: float | None
    runner_up_match_score: float | None
    crop_min_x: float
    crop_min_y: float
    crop_max_x: float
    crop_max_y: float
    confidence_radius_m: float
    heading_deg: float
    altitude_m: float
    ground_width_m: float
    ground_height_m: float


@dataclass
class RunResult:
    """Combined run result fed to the GUI's result and map panels."""

    pipeline: str
    runtime_seconds: float
    frames: list[FramePrediction] = field(default_factory=list)
    heatmap: np.ndarray | None = None
    heatmap_origin_pixel: tuple[float, float] | None = None
    heatmap_pixel_size: tuple[float, float] | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RunRequest:
    """Typed run request that the GUI can execute on a worker thread."""

    input_mode: str
    pipeline: str
    georeference: MapGeoreference
    session: ReplaySession | None = None
    replay_path: Path | None = None
    prior_latitude_deg: float | None = None
    prior_longitude_deg: float | None = None
    prior_search_radius_m: float | None = None
    measurement_update_radius_m: float = 5.0
    max_speed_mps: float = 25.0
    base_search_radius_m: float = 0.0
    roma_matcher_factory: object | None = None


def list_pipelines_for_input(input_mode: str) -> list[str]:
    """Return the pipeline choices that make sense for the given input mode."""
    if input_mode == "single":
        return list(SINGLE_IMAGE_PIPELINES)
    if input_mode == "sequence":
        return list(SEQUENCE_SCENARIOS)
    raise ValueError(f"unsupported input_mode '{input_mode}'")


def execute_run_request(request: RunRequest) -> RunResult:
    """Dispatch a typed GUI run request into the correct pipeline."""
    if request.input_mode == "single":
        if request.session is None:
            raise ValueError("single-image run requires a loaded session")
        if request.prior_latitude_deg is None or request.prior_longitude_deg is None:
            raise ValueError("single-image run requires a prior latitude/longitude")
        if request.prior_search_radius_m is None:
            raise ValueError("single-image run requires a prior search radius")
        return run_single_image(
            georeference=request.georeference,
            session=request.session,
            pipeline=request.pipeline,
            prior_latitude_deg=request.prior_latitude_deg,
            prior_longitude_deg=request.prior_longitude_deg,
            prior_search_radius_m=request.prior_search_radius_m,
            measurement_update_radius_m=request.measurement_update_radius_m,
            roma_matcher_factory=request.roma_matcher_factory,
        )
    if request.input_mode == "sequence":
        if request.replay_path is None:
            raise ValueError("sequence run requires a replay path")
        return run_sequence(
            georeference=request.georeference,
            replay_path=request.replay_path,
            scenario_name=request.pipeline,
            max_speed_mps=request.max_speed_mps,
            base_search_radius_m=request.base_search_radius_m,
            measurement_update_radius_m=request.measurement_update_radius_m,
            roma_matcher_factory=request.roma_matcher_factory,
        )
    raise ValueError(f"unsupported input_mode '{request.input_mode}'")


def run_single_image(
    *,
    georeference: MapGeoreference,
    session: ReplaySession,
    pipeline: str,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
    prior_search_radius_m: float,
    measurement_update_radius_m: float = 5.0,
    roma_matcher_factory=None,
) -> RunResult:
    """Run a single-image localization against the calibrated satellite tile.

    The session is expected to contain exactly one frame packet (validated by
    the single-image input loader). This function ignores any prior or radius
    inside the packet and uses the GUI-provided values instead, which matches
    the "drop a drone photo, give me a prior, find it" demo intent.
    """
    if pipeline not in SINGLE_IMAGE_PIPELINES:
        raise ValueError(f"unsupported single-image pipeline '{pipeline}'")
    if len(session.frames) != 1:
        raise ValueError("single-image run expects exactly one frame packet")

    started_at = time.perf_counter()
    frame = session.frames[0]
    geometry = normalize_frame_geometry(frame)
    crop_side_m = max(
        geometry.normalized_crop_size_m, prior_search_radius_m * 2.0 * 1.25
    )
    half_side_m = crop_side_m / 2.0

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
    crop_width_px = max(1.0, crop_max_x - crop_min_x)
    crop_height_px = max(1.0, crop_max_y - crop_min_y)
    ground_width_px = geometry.ground_width_m * (crop_width_px / crop_side_m)
    ground_height_px = geometry.ground_height_m * (crop_height_px / crop_side_m)

    target_offset_east_m, target_offset_north_m = meters_offset_between(
        origin_latitude_deg=prior_latitude_deg,
        origin_longitude_deg=prior_longitude_deg,
        target_latitude_deg=frame.latitude_deg,
        target_longitude_deg=frame.longitude_deg,
    )
    target_x_in_crop_01 = (target_offset_east_m + half_side_m) / crop_side_m
    target_y_in_crop_01 = (half_side_m - target_offset_north_m) / crop_side_m
    contains_target = 0.0 <= target_x_in_crop_01 <= 1.0 and 0.0 <= target_y_in_crop_01 <= 1.0

    accepted, estimate_source, predicted_pixel, score, runner_up, confidence_radius_m = (
        _run_single_matcher(
            pipeline=pipeline,
            frame_image_path=frame.image_path,
            geometry=geometry,
            ground_width_px=ground_width_px,
            ground_height_px=ground_height_px,
            crop_min_x=crop_min_x,
            crop_min_y=crop_min_y,
            crop_max_x=crop_max_x,
            crop_max_y=crop_max_y,
            crop_inside_image=crop_inside_image,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference=georeference,
            target_distance_m=math.hypot(target_offset_east_m, target_offset_north_m),
            target_x_in_crop_01=target_x_in_crop_01,
            target_y_in_crop_01=target_y_in_crop_01,
            contains_target=contains_target,
            roma_matcher_factory=roma_matcher_factory,
            prior_latitude_deg=prior_latitude_deg,
            prior_longitude_deg=prior_longitude_deg,
        )
    )

    if accepted:
        predicted_lat, predicted_lon = georeference.pixel_to_latlon(
            predicted_pixel[0], predicted_pixel[1]
        )
    else:
        predicted_lat, predicted_lon = prior_latitude_deg, prior_longitude_deg
        predicted_pixel = georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg)

    truth_pixel = georeference.latlon_to_pixel(frame.latitude_deg, frame.longitude_deg)
    error_east_m, error_north_m = meters_offset_between(
        origin_latitude_deg=frame.latitude_deg,
        origin_longitude_deg=frame.longitude_deg,
        target_latitude_deg=predicted_lat,
        target_longitude_deg=predicted_lon,
    )
    error_m = math.hypot(error_east_m, error_north_m) if accepted else None

    heatmap, heatmap_origin, heatmap_pixel_size = _compute_heatmap_if_supported(
        pipeline=pipeline,
        frame_image_path=frame.image_path,
        geometry=geometry,
        ground_width_px=ground_width_px,
        ground_height_px=ground_height_px,
        crop_min_x=crop_min_x,
        crop_min_y=crop_min_y,
        crop_max_x=crop_max_x,
        crop_max_y=crop_max_y,
        crop_inside_image=crop_inside_image,
        georeference=georeference,
    )

    runtime_seconds = time.perf_counter() - started_at
    prediction = FramePrediction(
        image_name=frame.image_name,
        image_path=frame.image_path,
        accepted=accepted,
        estimate_source=estimate_source,
        predicted_latitude_deg=predicted_lat,
        predicted_longitude_deg=predicted_lon,
        predicted_pixel_x=predicted_pixel[0],
        predicted_pixel_y=predicted_pixel[1],
        truth_latitude_deg=frame.latitude_deg,
        truth_longitude_deg=frame.longitude_deg,
        truth_pixel_x=truth_pixel[0],
        truth_pixel_y=truth_pixel[1],
        error_m=error_m,
        match_score=score,
        runner_up_match_score=runner_up,
        crop_min_x=crop_min_x,
        crop_min_y=crop_min_y,
        crop_max_x=crop_max_x,
        crop_max_y=crop_max_y,
        confidence_radius_m=confidence_radius_m,
        heading_deg=frame.heading_deg,
        altitude_m=frame.altitude_m,
        ground_width_m=geometry.ground_width_m,
        ground_height_m=geometry.ground_height_m,
    )
    return RunResult(
        pipeline=pipeline,
        runtime_seconds=runtime_seconds,
        frames=[prediction],
        heatmap=heatmap,
        heatmap_origin_pixel=heatmap_origin,
        heatmap_pixel_size=heatmap_pixel_size,
    )


def run_sequence(
    *,
    georeference: MapGeoreference,
    replay_path: Path,
    scenario_name: str,
    max_speed_mps: float = 25.0,
    base_search_radius_m: float = 0.0,
    measurement_update_radius_m: float = 5.0,
    roma_matcher_factory=None,
) -> RunResult:
    """Run the existing sequence_search evaluator and project one scenario."""
    if scenario_name not in SEQUENCE_SCENARIOS:
        raise ValueError(f"unsupported sequence scenario '{scenario_name}'")

    session = load_replay_session(replay_path)
    started_at = time.perf_counter()
    roma_matcher = None
    if "roma" in scenario_name:
        if roma_matcher_factory is None:
            raise RuntimeError(
                "RoMa scenarios require a roma_matcher_factory; install romatch and torch first."
            )
        roma_matcher = roma_matcher_factory(georeference.image_path)

    artifacts = build_sequence_search_artifacts(
        session,
        georeference,
        max_speed_mps=max_speed_mps,
        base_search_radius_m=base_search_radius_m,
        measurement_update_radius_m=measurement_update_radius_m,
        roma_matcher=roma_matcher,
    )
    runtime_seconds = time.perf_counter() - started_at

    chosen_scenarios = [s for s in artifacts.scenarios if s.scenario_name == scenario_name]
    if not chosen_scenarios:
        return RunResult(
            pipeline=scenario_name,
            runtime_seconds=runtime_seconds,
            error_message=(
                f"scenario '{scenario_name}' not produced by sequence_search; "
                "the matcher backend may be disabled."
            ),
        )
    scenario = chosen_scenarios[0]

    frames: list[FramePrediction] = []
    for packet, row in zip(session.frames, scenario.frames, strict=True):
        geometry = normalize_frame_geometry(packet)
        error_east_m, error_north_m = meters_offset_between(
            origin_latitude_deg=row.target_latitude_deg,
            origin_longitude_deg=row.target_longitude_deg,
            target_latitude_deg=row.estimated_latitude_deg,
            target_longitude_deg=row.estimated_longitude_deg,
        )
        error_m = math.hypot(error_east_m, error_north_m)
        frames.append(
            FramePrediction(
                image_name=row.image_name,
                image_path=packet.image_path,
                accepted=_is_accepted_source(row.estimate_source),
                estimate_source=row.estimate_source,
                predicted_latitude_deg=row.estimated_latitude_deg,
                predicted_longitude_deg=row.estimated_longitude_deg,
                predicted_pixel_x=row.estimate_pixel_x,
                predicted_pixel_y=row.estimate_pixel_y,
                truth_latitude_deg=row.target_latitude_deg,
                truth_longitude_deg=row.target_longitude_deg,
                truth_pixel_x=row.target_pixel_x,
                truth_pixel_y=row.target_pixel_y,
                error_m=error_m,
                match_score=row.match_score,
                runner_up_match_score=row.runner_up_match_score,
                crop_min_x=row.crop_min_x,
                crop_min_y=row.crop_min_y,
                crop_max_x=row.crop_max_x,
                crop_max_y=row.crop_max_y,
                confidence_radius_m=row.estimated_confidence_radius_m,
                heading_deg=packet.heading_deg,
                altitude_m=packet.altitude_m,
                ground_width_m=geometry.ground_width_m,
                ground_height_m=geometry.ground_height_m,
            )
        )

    return RunResult(
        pipeline=scenario_name,
        runtime_seconds=runtime_seconds,
        frames=frames,
    )


def load_calibrated_tile(image_path: Path) -> MapGeoreference:
    """Load the calibration sidecar that lives next to a satellite tile."""
    image_path = Path(image_path).resolve()
    calibration = image_path.with_name(image_path.stem + "_calibration.json")
    if not calibration.is_file():
        raise FileNotFoundError(
            f"satellite tile is missing a calibration sidecar at {calibration}"
        )
    return load_map_georeference(calibration)


def _is_accepted_source(source: str) -> bool:
    return not source.startswith("fallback_") and source != "prior_only_no_matcher"


def _run_single_matcher(
    *,
    pipeline: str,
    frame_image_path: Path,
    geometry: NormalizedFrameGeometry,
    ground_width_px: float,
    ground_height_px: float,
    crop_min_x: float,
    crop_min_y: float,
    crop_max_x: float,
    crop_max_y: float,
    crop_inside_image: bool,
    measurement_update_radius_m: float,
    georeference: MapGeoreference,
    target_distance_m: float,
    target_x_in_crop_01: float,
    target_y_in_crop_01: float,
    contains_target: bool,
    roma_matcher_factory,
    prior_latitude_deg: float,
    prior_longitude_deg: float,
) -> tuple[bool, str, tuple[float, float], float | None, float | None, float]:
    if pipeline == PIPELINE_PLACEHOLDER:
        decision = build_truth_anchored_placeholder_match(
            frame_index=0,
            heading_deg=geometry.heading_deg,
            target_distance_m=target_distance_m,
            target_x_in_crop_01=target_x_in_crop_01,
            target_y_in_crop_01=target_y_in_crop_01,
            crop_side_m=max(1.0, crop_max_x - crop_min_x),
            contains_target=contains_target,
            crop_inside_image=crop_inside_image,
            georeference_max_residual_m=georeference.max_residual_m,
            measurement_update_radius_m=measurement_update_radius_m,
        )
        if decision.accepted:
            from satellite_drone_localization.eval.sequence_policy import offset_latlon_by_meters

            estimated_lat, estimated_lon = offset_latlon_by_meters(
                geometry.latitude_deg,
                geometry.longitude_deg,
                east_m=decision.estimate_offset_east_m,
                north_m=decision.estimate_offset_north_m,
            )
            pixel = georeference.latlon_to_pixel(estimated_lat, estimated_lon)
            return (
                True,
                decision.estimate_source,
                pixel,
                None,
                None,
                decision.confidence_radius_m,
            )
        return (
            False,
            decision.estimate_source,
            georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg),
            None,
            None,
            decision.confidence_radius_m,
        )

    if pipeline in (PIPELINE_IMAGE_BASELINE, PIPELINE_IMAGE_MAP_CONSTRAINED):
        matcher = ImageBaselineMatcher(georeference.image_path)
        decision = matcher.match_frame(
            frame_image_path=frame_image_path,
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
        return (
            decision.accepted,
            decision.estimate_source,
            (decision.estimated_pixel_x, decision.estimated_pixel_y)
            if decision.accepted
            else georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg),
            decision.match_score,
            decision.runner_up_match_score,
            decision.confidence_radius_m,
        )

    if pipeline == PIPELINE_CLASSICAL:
        matcher = ClassicalFeatureMatcher(georeference.image_path)
        decision = matcher.match_frame(
            frame_image_path=frame_image_path,
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
        return (
            decision.accepted,
            decision.estimate_source,
            (decision.estimated_pixel_x, decision.estimated_pixel_y)
            if decision.accepted
            else georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg),
            decision.match_score,
            decision.runner_up_match_score,
            decision.confidence_radius_m,
        )

    if pipeline in (PIPELINE_ROMA, PIPELINE_ROMA_MAP_CONSTRAINED):
        if roma_matcher_factory is None:
            raise RuntimeError(
                "RoMa pipeline requires a roma_matcher_factory; install romatch and torch first."
            )
        matcher = roma_matcher_factory(georeference.image_path)
        decision = matcher.match_frame(
            frame_image_path=frame_image_path,
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
        return (
            decision.accepted,
            decision.estimate_source,
            (decision.estimated_pixel_x, decision.estimated_pixel_y)
            if decision.accepted
            else georeference.latlon_to_pixel(prior_latitude_deg, prior_longitude_deg),
            decision.match_score,
            decision.runner_up_match_score,
            decision.confidence_radius_m,
        )

    raise ValueError(f"unsupported pipeline '{pipeline}'")


def _compute_heatmap_if_supported(
    *,
    pipeline: str,
    frame_image_path: Path,
    geometry: NormalizedFrameGeometry,
    ground_width_px: float,
    ground_height_px: float,
    crop_min_x: float,
    crop_min_y: float,
    crop_max_x: float,
    crop_max_y: float,
    crop_inside_image: bool,
    georeference: MapGeoreference,
) -> tuple[np.ndarray | None, tuple[float, float] | None, tuple[float, float] | None]:
    if pipeline not in (
        PIPELINE_PLACEHOLDER,
        PIPELINE_IMAGE_BASELINE,
        PIPELINE_IMAGE_MAP_CONSTRAINED,
    ):
        return None, None, None
    if not crop_inside_image:
        return None, None, None

    template_w = max(12, int(round(ground_width_px)))
    template_h = max(12, int(round(ground_height_px)))
    search_left = int(round(crop_min_x))
    search_top = int(round(crop_min_y))
    search_right = int(round(crop_max_x))
    search_bottom = int(round(crop_max_y))
    search_w = search_right - search_left
    search_h = search_bottom - search_top
    if search_w < template_w or search_h < template_h:
        return None, None, None

    map_image = _load_edge_image(georeference.image_path)
    map_crop = map_image.crop((search_left, search_top, search_right, search_bottom))
    template, _ = _load_frame_template(
        frame_image_path=frame_image_path,
        normalization_rotation_deg=geometry.normalization_rotation_deg,
        width_px=template_w,
        height_px=template_h,
    )

    step_x = max(1, (search_w - template_w) // HEATMAP_GRID_STEP_DIVISOR or 1)
    step_y = max(1, (search_h - template_h) // HEATMAP_GRID_STEP_DIVISOR or 1)
    grid_w = ((search_w - template_w) // step_x) + 1
    grid_h = ((search_h - template_h) // step_y) + 1
    if grid_w < 2 or grid_h < 2:
        return None, None, None

    grid = np.zeros((grid_h, grid_w), dtype=np.float32)
    for gy in range(grid_h):
        local_y = gy * step_y
        for gx in range(grid_w):
            local_x = gx * step_x
            patch = map_crop.crop(
                (local_x, local_y, local_x + template_w, local_y + template_h)
            )
            prepared = _prepare_match_image(patch)
            grid[gy, gx] = _score_images(template, prepared)

    origin = (
        float(search_left + template_w / 2.0),
        float(search_top + template_h / 2.0),
    )
    pixel_size = (float(step_x), float(step_y))
    return grid, origin, pixel_size


def _load_edge_image(image_path: Path) -> Image.Image:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        grayscale = ImageOps.autocontrast(grayscale)
        edges = grayscale.filter(ImageFilter.FIND_EDGES)
        return ImageOps.autocontrast(edges).copy()


def _load_frame_template(
    *,
    frame_image_path: Path,
    normalization_rotation_deg: float,
    width_px: int,
    height_px: int,
) -> tuple[Image.Image, float]:
    with Image.open(frame_image_path) as image:
        grayscale = image.convert("L")
        grayscale = ImageOps.autocontrast(grayscale)
        rotated = grayscale.rotate(
            normalization_rotation_deg,
            resample=Image.Resampling.BILINEAR,
            expand=True,
            fillcolor=0,
        )
        mask = Image.new("L", grayscale.size, color=255).rotate(
            normalization_rotation_deg,
            resample=Image.Resampling.BILINEAR,
            expand=True,
            fillcolor=0,
        )
        bbox = mask.getbbox()
        if bbox is not None:
            rotated = rotated.crop(bbox)
        texture_stddev = ImageStat.Stat(rotated).stddev[0]
        resized = rotated.resize((width_px, height_px), resample=Image.Resampling.BILINEAR)
        return _prepare_match_image(resized), texture_stddev


def _prepare_match_image(image: Image.Image) -> Image.Image:
    prepared = image.resize((32, 32), resample=Image.Resampling.BILINEAR)
    grayscale = ImageOps.autocontrast(prepared)
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    return Image.blend(edges, grayscale, 0.35)


def _score_images(left: Image.Image, right: Image.Image) -> float:
    diff = ImageChops.difference(left, right)
    mean_diff = ImageStat.Stat(diff).mean[0]
    return max(0.0, 1.0 - (mean_diff / 255.0))


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
