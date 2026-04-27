"""Phase 1 crop planning around a replay prior."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

from .geometry import NormalizedFrameGeometry, build_replay_geometry_report
from .packet_replay import ReplaySession


EARTH_RADIUS_M = 6_378_137.0
DEFAULT_PRIOR_SEARCH_RADIUS_SCALE = 0.5
DEFAULT_CROP_PADDING_FACTOR = 1.25


@dataclass(frozen=True)
class PlannedFrameCrop:
    """A deterministic crop plan around a frame prior."""

    timestamp_utc: str
    image_name: str
    prior_latitude_deg: float
    prior_longitude_deg: float
    target_latitude_deg: float
    target_longitude_deg: float
    prior_search_radius_m: float
    crop_side_m: float
    target_offset_east_m: float
    target_offset_north_m: float
    target_x_in_crop_01: float
    target_y_in_crop_01: float
    contains_target: bool
    normalized_rotation_deg: float


@dataclass(frozen=True)
class ReplayCropPlan:
    """Crop planning summary for a replay session."""

    session_id: str | None
    source_path: Path
    frame_count: int
    average_crop_side_m: float
    max_target_offset_m: float
    frames: list[PlannedFrameCrop]


def build_replay_crop_plan(session: ReplaySession) -> ReplayCropPlan:
    """Plan one crop per frame around the provided or fallback prior."""
    geometry_report = build_replay_geometry_report(session)
    planned_frames: list[PlannedFrameCrop] = []

    for packet, geometry in zip(session.frames, geometry_report.frames, strict=True):
        prior_latitude_deg = packet.prior_latitude_deg if packet.prior_latitude_deg is not None else packet.latitude_deg
        prior_longitude_deg = packet.prior_longitude_deg if packet.prior_longitude_deg is not None else packet.longitude_deg
        prior_search_radius_m = packet.prior_search_radius_m
        if prior_search_radius_m is None:
            prior_search_radius_m = geometry.normalized_crop_size_m * DEFAULT_PRIOR_SEARCH_RADIUS_SCALE

        target_offset_east_m, target_offset_north_m = meters_offset_between(
            origin_latitude_deg=prior_latitude_deg,
            origin_longitude_deg=prior_longitude_deg,
            target_latitude_deg=packet.latitude_deg,
            target_longitude_deg=packet.longitude_deg,
        )
        crop_side_m = max(geometry.normalized_crop_size_m, prior_search_radius_m * 2.0 * DEFAULT_CROP_PADDING_FACTOR)
        half_side = crop_side_m / 2.0
        target_x_in_crop_01 = (target_offset_east_m + half_side) / crop_side_m
        target_y_in_crop_01 = (half_side - target_offset_north_m) / crop_side_m
        contains_target = 0.0 <= target_x_in_crop_01 <= 1.0 and 0.0 <= target_y_in_crop_01 <= 1.0

        planned_frames.append(
            PlannedFrameCrop(
                timestamp_utc=packet.timestamp_utc,
                image_name=packet.image_name,
                prior_latitude_deg=prior_latitude_deg,
                prior_longitude_deg=prior_longitude_deg,
                target_latitude_deg=packet.latitude_deg,
                target_longitude_deg=packet.longitude_deg,
                prior_search_radius_m=prior_search_radius_m,
                crop_side_m=crop_side_m,
                target_offset_east_m=target_offset_east_m,
                target_offset_north_m=target_offset_north_m,
                target_x_in_crop_01=target_x_in_crop_01,
                target_y_in_crop_01=target_y_in_crop_01,
                contains_target=contains_target,
                normalized_rotation_deg=geometry.normalization_rotation_deg,
            )
        )

    return ReplayCropPlan(
        session_id=session.session_id,
        source_path=session.source_path,
        frame_count=len(planned_frames),
        average_crop_side_m=sum(frame.crop_side_m for frame in planned_frames) / len(planned_frames),
        max_target_offset_m=max(
            math.hypot(frame.target_offset_east_m, frame.target_offset_north_m) for frame in planned_frames
        ),
        frames=planned_frames,
    )


def meters_offset_between(
    origin_latitude_deg: float,
    origin_longitude_deg: float,
    target_latitude_deg: float,
    target_longitude_deg: float,
) -> tuple[float, float]:
    """Approximate east/north meter offsets between two nearby WGS84 points."""
    origin_lat_rad = math.radians(origin_latitude_deg)
    delta_lat_rad = math.radians(target_latitude_deg - origin_latitude_deg)
    delta_lon_rad = math.radians(target_longitude_deg - origin_longitude_deg)
    east_m = delta_lon_rad * math.cos(origin_lat_rad) * EARTH_RADIUS_M
    north_m = delta_lat_rad * EARTH_RADIUS_M
    return east_m, north_m


def write_crop_summary(path: Path, plan: ReplayCropPlan) -> None:
    """Write the crop plan as JSON."""
    payload = {
        "session_id": plan.session_id,
        "source_path": str(plan.source_path),
        "frame_count": plan.frame_count,
        "average_crop_side_m": plan.average_crop_side_m,
        "max_target_offset_m": plan.max_target_offset_m,
        "frames": [asdict(frame) for frame in plan.frames],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_crop_debug_svg(path: Path, plan: ReplayCropPlan) -> None:
    """Write an SVG overlay showing the first crop plan."""
    frame = plan.frames[0]
    size_px = 360.0
    margin = 28.0
    crop_px = size_px - (margin * 2.0)
    center_x = size_px / 2.0
    center_y = size_px / 2.0
    prior_radius_px = (frame.prior_search_radius_m / frame.crop_side_m) * crop_px
    target_x = margin + (frame.target_x_in_crop_01 * crop_px)
    target_y = margin + (frame.target_y_in_crop_01 * crop_px)

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{int(size_px)}" height="{int(size_px + 52)}" viewBox="0 0 {int(size_px)} {int(size_px + 52)}">
  <rect width="{int(size_px)}" height="{int(size_px + 52)}" fill="#f4f1e8"/>
  <text x="20" y="24" font-family="monospace" font-size="15" fill="#213547">Crop Debug</text>
  <rect x="{margin}" y="{margin}" width="{crop_px}" height="{crop_px}" fill="#dde7c7" stroke="#50623a" stroke-width="2"/>
  <circle cx="{center_x:.2f}" cy="{center_y:.2f}" r="{prior_radius_px:.2f}" fill="#8ecae6" fill-opacity="0.25" stroke="#0f4c5c" stroke-width="2"/>
  <circle cx="{center_x:.2f}" cy="{center_y:.2f}" r="5" fill="#0f4c5c"/>
  <circle cx="{target_x:.2f}" cy="{target_y:.2f}" r="5" fill="#c05621"/>
  <line x1="{center_x:.2f}" y1="{center_y:.2f}" x2="{target_x:.2f}" y2="{target_y:.2f}" stroke="#7d4e57" stroke-width="2"/>
  <text x="20" y="{size_px + 16:.2f}" font-family="monospace" font-size="12" fill="#213547">crop_side={frame.crop_side_m:.1f}m prior_radius={frame.prior_search_radius_m:.1f}m</text>
  <text x="20" y="{size_px + 32:.2f}" font-family="monospace" font-size="12" fill="#213547">target_offset=({frame.target_offset_east_m:.1f}m E, {frame.target_offset_north_m:.1f}m N)</text>
  <text x="20" y="{size_px + 48:.2f}" font-family="monospace" font-size="12" fill="#213547">contains_target={str(frame.contains_target).lower()} rotation={frame.normalized_rotation_deg:.1f}</text>
</svg>
"""
    path.write_text(content, encoding="utf-8")
