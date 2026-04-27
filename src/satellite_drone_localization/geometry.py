"""Phase 1 geometry normalization and debug reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

from .packet_replay import ReplaySession
from .packet_schema import ReplayFramePacket


@dataclass(frozen=True)
class NormalizedFrameGeometry:
    """Deterministic geometry interpretation for one replay frame."""

    timestamp_utc: str
    image_name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    altitude_reference: str
    heading_deg: float
    normalization_rotation_deg: float
    camera_hfov_deg: float
    camera_vfov_deg: float
    vfov_source: str
    ground_width_m: float
    ground_height_m: float
    normalized_crop_size_m: float
    meters_per_pixel_x: float | None
    meters_per_pixel_y: float | None
    frame_width_px: int | None
    frame_height_px: int | None


@dataclass(frozen=True)
class ReplayGeometryReport:
    """Summary geometry report for a replay session."""

    session_id: str | None
    source_path: Path
    frame_count: int
    average_altitude_m: float
    min_ground_width_m: float
    max_ground_width_m: float
    min_ground_height_m: float
    max_ground_height_m: float
    frames: list[NormalizedFrameGeometry]


def normalize_frame_geometry(packet: ReplayFramePacket) -> NormalizedFrameGeometry:
    """Convert a replay packet into a geometry interpretation."""
    vfov_deg, vfov_source = resolve_vertical_fov_deg(packet)
    ground_width_m = 2.0 * packet.altitude_m * math.tan(math.radians(packet.camera_hfov_deg) / 2.0)
    ground_height_m = 2.0 * packet.altitude_m * math.tan(math.radians(vfov_deg) / 2.0)
    normalized_crop_size_m = max(ground_width_m, ground_height_m)

    meters_per_pixel_x = None
    if packet.frame_width_px is not None:
        meters_per_pixel_x = ground_width_m / packet.frame_width_px

    meters_per_pixel_y = None
    if packet.frame_height_px is not None:
        meters_per_pixel_y = ground_height_m / packet.frame_height_px

    return NormalizedFrameGeometry(
        timestamp_utc=packet.timestamp_utc,
        image_name=packet.image_name,
        latitude_deg=packet.latitude_deg,
        longitude_deg=packet.longitude_deg,
        altitude_m=packet.altitude_m,
        altitude_reference=packet.altitude_reference,
        heading_deg=packet.heading_deg,
        normalization_rotation_deg=normalize_heading_to_north_up(packet.heading_deg),
        camera_hfov_deg=packet.camera_hfov_deg,
        camera_vfov_deg=vfov_deg,
        vfov_source=vfov_source,
        ground_width_m=ground_width_m,
        ground_height_m=ground_height_m,
        normalized_crop_size_m=normalized_crop_size_m,
        meters_per_pixel_x=meters_per_pixel_x,
        meters_per_pixel_y=meters_per_pixel_y,
        frame_width_px=packet.frame_width_px,
        frame_height_px=packet.frame_height_px,
    )


def resolve_vertical_fov_deg(packet: ReplayFramePacket) -> tuple[float, str]:
    """Resolve or infer the vertical field of view for a frame."""
    if packet.camera_vfov_deg is not None:
        return packet.camera_vfov_deg, "packet"
    if packet.frame_width_px is not None and packet.frame_height_px is not None:
        aspect_ratio = packet.frame_height_px / packet.frame_width_px
        half_hfov_rad = math.radians(packet.camera_hfov_deg) / 2.0
        half_vfov_rad = math.atan(math.tan(half_hfov_rad) * aspect_ratio)
        return math.degrees(half_vfov_rad * 2.0), "inferred_from_aspect_ratio"
    return packet.camera_hfov_deg, "fallback_equal_to_hfov"


def normalize_heading_to_north_up(heading_deg: float) -> float:
    """Return the rotation needed to make a frame north-up."""
    return (-heading_deg) % 360.0


def build_replay_geometry_report(session: ReplaySession) -> ReplayGeometryReport:
    """Build geometry interpretations and aggregate metrics for a replay session."""
    frames = [normalize_frame_geometry(packet) for packet in session.frames]
    average_altitude_m = sum(frame.altitude_m for frame in frames) / len(frames)

    return ReplayGeometryReport(
        session_id=session.session_id,
        source_path=session.source_path,
        frame_count=len(frames),
        average_altitude_m=average_altitude_m,
        min_ground_width_m=min(frame.ground_width_m for frame in frames),
        max_ground_width_m=max(frame.ground_width_m for frame in frames),
        min_ground_height_m=min(frame.ground_height_m for frame in frames),
        max_ground_height_m=max(frame.ground_height_m for frame in frames),
        frames=frames,
    )


def write_geometry_summary(path: Path, report: ReplayGeometryReport) -> None:
    """Write the geometry report as JSON for downstream inspection."""
    payload = {
        "session_id": report.session_id,
        "source_path": str(report.source_path),
        "frame_count": report.frame_count,
        "average_altitude_m": report.average_altitude_m,
        "min_ground_width_m": report.min_ground_width_m,
        "max_ground_width_m": report.max_ground_width_m,
        "min_ground_height_m": report.min_ground_height_m,
        "max_ground_height_m": report.max_ground_height_m,
        "frames": [asdict(frame) for frame in report.frames],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_geometry_debug_svg(path: Path, report: ReplayGeometryReport) -> None:
    """Write a simple SVG visualizing the first frame's interpreted footprint."""
    frame = report.frames[0]
    width_px = 420.0
    height_px = 280.0
    margin = 40.0
    available_width = width_px - (margin * 2.0)
    available_height = height_px - (margin * 2.0)
    scale = min(
        available_width / frame.normalized_crop_size_m,
        available_height / frame.normalized_crop_size_m,
    )
    footprint_width_px = frame.ground_width_m * scale
    footprint_height_px = frame.ground_height_m * scale
    x = (width_px - footprint_width_px) / 2.0
    y = (height_px - footprint_height_px) / 2.0
    center_x = width_px / 2.0
    center_y = height_px / 2.0
    rotation = frame.heading_deg

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{int(width_px)}" height="{int(height_px)}" viewBox="0 0 {int(width_px)} {int(height_px)}">
  <rect width="{int(width_px)}" height="{int(height_px)}" fill="#f4f1e8"/>
  <text x="20" y="28" font-family="monospace" font-size="16" fill="#213547">Geometry Debug</text>
  <text x="20" y="48" font-family="monospace" font-size="12" fill="#213547">{frame.image_name} alt={frame.altitude_m:.1f}m hfov={frame.camera_hfov_deg:.1f} vfov={frame.camera_vfov_deg:.1f}</text>
  <rect x="{margin}" y="{margin}" width="{available_width}" height="{available_height}" fill="#dde7c7" stroke="#50623a" stroke-width="2"/>
  <g transform="rotate({rotation:.2f} {center_x:.2f} {center_y:.2f})">
    <rect x="{x:.2f}" y="{y:.2f}" width="{footprint_width_px:.2f}" height="{footprint_height_px:.2f}" fill="#8ecae6" fill-opacity="0.55" stroke="#0f4c5c" stroke-width="2"/>
  </g>
  <line x1="{center_x:.2f}" y1="58" x2="{center_x:.2f}" y2="92" stroke="#c05621" stroke-width="3"/>
  <polygon points="{center_x - 6:.2f},68 {center_x + 6:.2f},68 {center_x:.2f},58" fill="#c05621"/>
  <text x="{center_x + 12:.2f}" y="76" font-family="monospace" font-size="12" fill="#7d4e57">north</text>
  <text x="20" y="248" font-family="monospace" font-size="12" fill="#213547">rotation to north-up: {frame.normalization_rotation_deg:.2f} deg</text>
  <text x="20" y="264" font-family="monospace" font-size="12" fill="#213547">footprint: {frame.ground_width_m:.1f}m x {frame.ground_height_m:.1f}m</text>
</svg>
"""
    path.write_text(content, encoding="utf-8")
