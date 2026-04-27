"""Sequence prior evaluation against a calibrated GIS reference image."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math
from pathlib import Path

from ..crop import DEFAULT_CROP_PADDING_FACTOR, meters_offset_between
from ..geometry import build_replay_geometry_report
from ..map_georeference import MapGeoreference
from ..packet_replay import ReplaySession


SCENARIO_SEED_ONLY = "seed_only"
SCENARIO_ORACLE_PREVIOUS_TRUTH = "oracle_previous_truth"
SCENARIO_NAMES = (SCENARIO_SEED_ONLY, SCENARIO_ORACLE_PREVIOUS_TRUTH)
EARTH_RADIUS_M = 6_378_137.0


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
    prior_pixel_x: float
    prior_pixel_y: float
    target_pixel_x: float
    target_pixel_y: float
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
    crop_inside_image_count: int
    max_target_offset_m: float
    average_crop_side_m: float
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
    scenarios: list[SequenceScenarioReport]


def build_sequence_search_artifacts(
    session: ReplaySession,
    georeference: MapGeoreference,
    *,
    max_speed_mps: float,
    base_search_radius_m: float = 0.0,
) -> SequenceSearchArtifacts:
    """Evaluate multiple motion-bounded prior scenarios for one replay session."""
    if max_speed_mps <= 0.0:
        raise ValueError("max_speed_mps must be positive")
    if base_search_radius_m < 0.0:
        raise ValueError("base_search_radius_m must be non-negative")

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
        ),
    ]

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
) -> SequenceScenarioReport:
    """Evaluate one sequence-prior scenario."""
    if scenario_name not in SCENARIO_NAMES:
        raise ValueError(f"unsupported scenario_name '{scenario_name}'")

    seed_frame = session.frames[0]
    results: list[SequenceFrameResult] = []

    for index, (frame, geometry, timestamp) in enumerate(zip(session.frames, geometry_report, timestamps, strict=True)):
        elapsed_seconds = (timestamp - first_timestamp).total_seconds()
        if index == 0:
            delta_seconds = 0.0
            prior_latitude_deg = seed_frame.latitude_deg
            prior_longitude_deg = seed_frame.longitude_deg
            prior_source = "seed_frame_truth"
        elif scenario_name == SCENARIO_SEED_ONLY:
            delta_seconds = elapsed_seconds
            prior_latitude_deg = seed_frame.latitude_deg
            prior_longitude_deg = seed_frame.longitude_deg
            prior_source = "seed_frame_truth"
        else:
            previous_frame = session.frames[index - 1]
            previous_timestamp = timestamps[index - 1]
            delta_seconds = (timestamp - previous_timestamp).total_seconds()
            prior_latitude_deg = previous_frame.latitude_deg
            prior_longitude_deg = previous_frame.longitude_deg
            prior_source = "previous_frame_truth_oracle"

        prior_search_radius_m = base_search_radius_m + (max_speed_mps * delta_seconds)
        crop_side_m = max(geometry.normalized_crop_size_m, prior_search_radius_m * 2.0 * DEFAULT_CROP_PADDING_FACTOR)
        half_side_m = crop_side_m / 2.0

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
                prior_pixel_x=prior_pixel_x,
                prior_pixel_y=prior_pixel_y,
                target_pixel_x=target_pixel_x,
                target_pixel_y=target_pixel_y,
                crop_min_x=crop_min_x,
                crop_min_y=crop_min_y,
                crop_max_x=crop_max_x,
                crop_max_y=crop_max_y,
                crop_inside_image=crop_inside_image,
                altitude_reference=frame.altitude_reference,
            )
        )

    return SequenceScenarioReport(
        scenario_name=scenario_name,
        description=describe_scenario(scenario_name),
        frame_count=len(results),
        contained_frame_count=sum(1 for frame in results if frame.contains_target),
        crop_inside_image_count=sum(1 for frame in results if frame.crop_inside_image),
        max_target_offset_m=max(frame.target_distance_m for frame in results),
        average_crop_side_m=sum(frame.crop_side_m for frame in results) / len(results),
        frames=results,
    )


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


def write_sequence_search_summary(path: Path, artifacts: SequenceSearchArtifacts) -> None:
    """Write the sequence evaluation artifact set as JSON."""
    payload = {
        "session_id": artifacts.session_id,
        "source_path": str(artifacts.source_path),
        "image_path": str(artifacts.image_path),
        "image_width_px": artifacts.image_width_px,
        "image_height_px": artifacts.image_height_px,
        "georeference_max_residual_m": artifacts.georeference_max_residual_m,
        "seed_latitude_deg": artifacts.seed_latitude_deg,
        "seed_longitude_deg": artifacts.seed_longitude_deg,
        "max_speed_mps": artifacts.max_speed_mps,
        "base_search_radius_m": artifacts.base_search_radius_m,
        "scenarios": [
            {
                "scenario_name": scenario.scenario_name,
                "description": scenario.description,
                "frame_count": scenario.frame_count,
                "contained_frame_count": scenario.contained_frame_count,
                "crop_inside_image_count": scenario.crop_inside_image_count,
                "containment_ratio": scenario.contained_frame_count / scenario.frame_count,
                "map_coverage_ratio": scenario.crop_inside_image_count / scenario.frame_count,
                "max_target_offset_m": scenario.max_target_offset_m,
                "average_crop_side_m": scenario.average_crop_side_m,
                "frames": [asdict(frame) for frame in scenario.frames],
            }
            for scenario in artifacts.scenarios
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_sequence_search_debug_svg(path: Path, artifacts: SequenceSearchArtifacts) -> None:
    """Write an SVG overview of route truth and sequence search crops."""
    canvas_width = 900.0
    scale = min(
        (canvas_width - 80.0) / artifacts.image_width_px,
        520.0 / artifacts.image_height_px,
    )
    map_width = artifacts.image_width_px * scale
    map_height = artifacts.image_height_px * scale
    origin_x = 40.0
    origin_y = 56.0

    truth_points = " ".join(
        f"{origin_x + (frame.target_pixel_x * scale):.2f},{origin_y + (frame.target_pixel_y * scale):.2f}"
        for frame in artifacts.scenarios[0].frames
    )

    scenario_styles = {
        SCENARIO_SEED_ONLY: ("#c05621", "#7d4e57"),
        SCENARIO_ORACLE_PREVIOUS_TRUTH: ("#0f4c5c", "#8ecae6"),
    }
    overlay_parts: list[str] = []
    for scenario in artifacts.scenarios:
        stroke_color, fill_color = scenario_styles[scenario.scenario_name]
        step = max(1, len(scenario.frames) // 10)
        selected_indices = sorted({0, len(scenario.frames) - 1, *range(0, len(scenario.frames), step)})
        for index in selected_indices:
            frame = scenario.frames[index]
            rect_x = origin_x + (frame.crop_min_x * scale)
            rect_y = origin_y + (frame.crop_min_y * scale)
            rect_width = (frame.crop_max_x - frame.crop_min_x) * scale
            rect_height = (frame.crop_max_y - frame.crop_min_y) * scale
            overlay_parts.append(
                f'<rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{rect_width:.2f}" height="{rect_height:.2f}" fill="{fill_color}" fill-opacity="0.08" stroke="{stroke_color}" stroke-width="1.5"/>'
            )

    summary_lines = []
    text_y = origin_y + map_height + 24.0
    for scenario in artifacts.scenarios:
        summary_lines.append(
            f'<text x="40" y="{text_y:.0f}" font-family="monospace" font-size="12" fill="#213547">{scenario.scenario_name}: contains={scenario.contained_frame_count}/{scenario.frame_count} map={scenario.crop_inside_image_count}/{scenario.frame_count} max_offset={scenario.max_target_offset_m:.1f}m avg_crop={scenario.average_crop_side_m:.1f}m</text>'
        )
        text_y += 16.0

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{int(canvas_width)}" height="{int(text_y + 24.0)}" viewBox="0 0 {int(canvas_width)} {int(text_y + 24.0)}">
  <rect width="{int(canvas_width)}" height="{int(text_y + 24.0)}" fill="#f4f1e8"/>
  <text x="40" y="24" font-family="monospace" font-size="16" fill="#213547">Sequence Search Debug</text>
  <text x="40" y="42" font-family="monospace" font-size="12" fill="#213547">seed=({artifacts.seed_latitude_deg:.6f}, {artifacts.seed_longitude_deg:.6f}) speed={artifacts.max_speed_mps:.1f}mps base_radius={artifacts.base_search_radius_m:.1f}m residual={artifacts.georeference_max_residual_m:.2f}m</text>
  <rect x="{origin_x}" y="{origin_y}" width="{map_width:.2f}" height="{map_height:.2f}" fill="#ffffff" stroke="#50623a" stroke-width="2"/>
  {' '.join(overlay_parts)}
  <polyline points="{truth_points}" fill="none" stroke="#213547" stroke-width="2"/>
  {''.join(summary_lines)}
</svg>
"""
    path.write_text(content, encoding="utf-8")


def describe_scenario(scenario_name: str) -> str:
    """Return the human-readable scenario description."""
    if scenario_name == SCENARIO_SEED_ONLY:
        return "Use frame-0 truth as the only seed and grow the search radius over total elapsed time."
    if scenario_name == SCENARIO_ORACLE_PREVIOUS_TRUTH:
        return "Upper-bound ceiling that recenters on the previous frame truth and grows radius only over per-frame delta time."
    raise ValueError(f"unsupported scenario_name '{scenario_name}'")


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


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
