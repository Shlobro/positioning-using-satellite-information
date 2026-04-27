"""Combined replay pipeline artifacts for Phase 1 inspection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

from .crop import ReplayCropPlan, build_replay_crop_plan
from .geometry import ReplayGeometryReport, build_replay_geometry_report
from .packet_replay import ReplaySession


@dataclass(frozen=True)
class SensitivityCaseSummary:
    """Aggregate effect of a single telemetry perturbation."""

    case_name: str
    average_ground_width_delta_m: float
    average_ground_height_delta_m: float
    average_rotation_delta_deg: float
    average_crop_side_delta_m: float
    average_target_position_delta_01: float


@dataclass(frozen=True)
class ReplayPipelineArtifacts:
    """Combined pipeline outputs for one replay session."""

    session: ReplaySession
    geometry_report: ReplayGeometryReport
    crop_plan: ReplayCropPlan
    sensitivity_cases: list[SensitivityCaseSummary]


def build_replay_pipeline_artifacts(session: ReplaySession) -> ReplayPipelineArtifacts:
    """Build the combined replay pipeline artifact set."""
    geometry_report = build_replay_geometry_report(session)
    crop_plan = build_replay_crop_plan(session)
    sensitivity_cases = build_geometry_sensitivity_report(session)
    return ReplayPipelineArtifacts(
        session=session,
        geometry_report=geometry_report,
        crop_plan=crop_plan,
        sensitivity_cases=sensitivity_cases,
    )


def build_geometry_sensitivity_report(session: ReplaySession) -> list[SensitivityCaseSummary]:
    """Measure how geometry and crop planning react to bounded telemetry perturbations."""
    baseline_geometry = build_replay_geometry_report(session)
    baseline_crop = build_replay_crop_plan(session)
    perturbations = [
        ("altitude_minus_10pct", {"altitude_scale": 0.9}),
        ("altitude_plus_10pct", {"altitude_scale": 1.1}),
        ("hfov_minus_5deg", {"hfov_delta_deg": -5.0}),
        ("hfov_plus_5deg", {"hfov_delta_deg": 5.0}),
        ("heading_minus_10deg", {"heading_delta_deg": -10.0}),
        ("heading_plus_10deg", {"heading_delta_deg": 10.0}),
    ]

    summaries: list[SensitivityCaseSummary] = []
    for case_name, parameters in perturbations:
        perturbed_frames = [
            replace(
                frame,
                altitude_m=frame.altitude_m * parameters.get("altitude_scale", 1.0),
                camera_hfov_deg=frame.camera_hfov_deg + parameters.get("hfov_delta_deg", 0.0),
                heading_deg=(frame.heading_deg + parameters.get("heading_delta_deg", 0.0)) % 360.0,
            )
            for frame in session.frames
        ]
        perturbed_session = replace(session, frames=perturbed_frames)
        perturbed_geometry = build_replay_geometry_report(perturbed_session)
        perturbed_crop = build_replay_crop_plan(perturbed_session)

        geometry_pairs = zip(baseline_geometry.frames, perturbed_geometry.frames, strict=True)
        crop_pairs = zip(baseline_crop.frames, perturbed_crop.frames, strict=True)

        geometry_frame_count = len(baseline_geometry.frames)
        crop_frame_count = len(baseline_crop.frames)

        average_ground_width_delta_m = sum(
            abs(perturbed.ground_width_m - baseline.ground_width_m) for baseline, perturbed in geometry_pairs
        ) / geometry_frame_count
        geometry_pairs = zip(baseline_geometry.frames, perturbed_geometry.frames, strict=True)
        average_ground_height_delta_m = sum(
            abs(perturbed.ground_height_m - baseline.ground_height_m) for baseline, perturbed in geometry_pairs
        ) / geometry_frame_count
        geometry_pairs = zip(baseline_geometry.frames, perturbed_geometry.frames, strict=True)
        average_rotation_delta_deg = sum(
            _angular_difference_deg(perturbed.normalization_rotation_deg, baseline.normalization_rotation_deg)
            for baseline, perturbed in geometry_pairs
        ) / geometry_frame_count
        average_crop_side_delta_m = sum(
            abs(perturbed.crop_side_m - baseline.crop_side_m) for baseline, perturbed in crop_pairs
        ) / crop_frame_count
        crop_pairs = zip(baseline_crop.frames, perturbed_crop.frames, strict=True)
        average_target_position_delta_01 = sum(
            (
                abs(perturbed.target_x_in_crop_01 - baseline.target_x_in_crop_01)
                + abs(perturbed.target_y_in_crop_01 - baseline.target_y_in_crop_01)
            )
            / 2.0
            for baseline, perturbed in crop_pairs
        ) / crop_frame_count

        summaries.append(
            SensitivityCaseSummary(
                case_name=case_name,
                average_ground_width_delta_m=average_ground_width_delta_m,
                average_ground_height_delta_m=average_ground_height_delta_m,
                average_rotation_delta_deg=average_rotation_delta_deg,
                average_crop_side_delta_m=average_crop_side_delta_m,
                average_target_position_delta_01=average_target_position_delta_01,
            )
        )
    return summaries


def write_pipeline_summary(path: Path, artifacts: ReplayPipelineArtifacts) -> None:
    """Write a combined JSON summary for the replay pipeline."""
    payload = {
        "session_id": artifacts.session.session_id,
        "source_path": str(artifacts.session.source_path),
        "frame_count": artifacts.geometry_report.frame_count,
        "average_altitude_m": artifacts.geometry_report.average_altitude_m,
        "average_crop_side_m": artifacts.crop_plan.average_crop_side_m,
        "max_target_offset_m": artifacts.crop_plan.max_target_offset_m,
        "frames": [
            {
                "timestamp_utc": geometry.timestamp_utc,
                "image_name": geometry.image_name,
                "ground_width_m": geometry.ground_width_m,
                "ground_height_m": geometry.ground_height_m,
                "normalization_rotation_deg": geometry.normalization_rotation_deg,
                "crop_side_m": crop.crop_side_m,
                "target_offset_east_m": crop.target_offset_east_m,
                "target_offset_north_m": crop.target_offset_north_m,
                "contains_target": crop.contains_target,
            }
            for geometry, crop in zip(artifacts.geometry_report.frames, artifacts.crop_plan.frames, strict=True)
        ],
        "sensitivity_cases": [asdict(case) for case in artifacts.sensitivity_cases],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_pipeline_debug_svg(path: Path, artifacts: ReplayPipelineArtifacts) -> None:
    """Write a combined SVG showing geometry, crop, and sensitivity summaries."""
    geometry = artifacts.geometry_report.frames[0]
    crop = artifacts.crop_plan.frames[0]
    size_x = 720.0
    size_y = 340.0
    left_x = 24.0
    top_y = 48.0
    panel_size = 260.0
    crop_panel_x = 364.0
    center_x = left_x + panel_size / 2.0
    center_y = top_y + panel_size / 2.0
    footprint_scale = min(panel_size / geometry.normalized_crop_size_m, panel_size / geometry.normalized_crop_size_m)
    footprint_w = geometry.ground_width_m * footprint_scale
    footprint_h = geometry.ground_height_m * footprint_scale
    footprint_x = center_x - (footprint_w / 2.0)
    footprint_y = center_y - (footprint_h / 2.0)
    crop_center_x = crop_panel_x + (panel_size / 2.0)
    crop_center_y = center_y
    prior_radius_px = (crop.prior_search_radius_m / crop.crop_side_m) * panel_size
    target_x = crop_panel_x + (crop.target_x_in_crop_01 * panel_size)
    target_y = top_y + (crop.target_y_in_crop_01 * panel_size)
    sensitivity_lines = "\n".join(
        f'  <text x="24" y="{332 + (index * 14):.0f}" font-family="monospace" font-size="11" fill="#213547">{case.case_name}: dW={case.average_ground_width_delta_m:.1f} dCrop={case.average_crop_side_delta_m:.1f} dRot={case.average_rotation_delta_deg:.1f}</text>'
        for index, case in enumerate(artifacts.sensitivity_cases[:4])
    )

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{int(size_x)}" height="{int(size_y + 70)}" viewBox="0 0 {int(size_x)} {int(size_y + 70)}">
  <rect width="{int(size_x)}" height="{int(size_y + 70)}" fill="#f4f1e8"/>
  <text x="24" y="24" font-family="monospace" font-size="16" fill="#213547">Replay Pipeline Debug</text>
  <text x="24" y="40" font-family="monospace" font-size="12" fill="#213547">{geometry.image_name}  alt={geometry.altitude_m:.1f}m  crop={crop.crop_side_m:.1f}m</text>
  <rect x="{left_x}" y="{top_y}" width="{panel_size}" height="{panel_size}" fill="#dde7c7" stroke="#50623a" stroke-width="2"/>
  <text x="{left_x}" y="{top_y - 10}" font-family="monospace" font-size="12" fill="#213547">geometry footprint</text>
  <g transform="rotate({geometry.heading_deg:.2f} {center_x:.2f} {center_y:.2f})">
    <rect x="{footprint_x:.2f}" y="{footprint_y:.2f}" width="{footprint_w:.2f}" height="{footprint_h:.2f}" fill="#8ecae6" fill-opacity="0.55" stroke="#0f4c5c" stroke-width="2"/>
  </g>
  <rect x="{crop_panel_x}" y="{top_y}" width="{panel_size}" height="{panel_size}" fill="#dde7c7" stroke="#50623a" stroke-width="2"/>
  <text x="{crop_panel_x}" y="{top_y - 10}" font-family="monospace" font-size="12" fill="#213547">prior crop</text>
  <circle cx="{crop_center_x:.2f}" cy="{crop_center_y:.2f}" r="{prior_radius_px:.2f}" fill="#8ecae6" fill-opacity="0.25" stroke="#0f4c5c" stroke-width="2"/>
  <circle cx="{crop_center_x:.2f}" cy="{crop_center_y:.2f}" r="5" fill="#0f4c5c"/>
  <circle cx="{target_x:.2f}" cy="{target_y:.2f}" r="5" fill="#c05621"/>
  <line x1="{crop_center_x:.2f}" y1="{crop_center_y:.2f}" x2="{target_x:.2f}" y2="{target_y:.2f}" stroke="#7d4e57" stroke-width="2"/>
  <text x="24" y="324" font-family="monospace" font-size="12" fill="#213547">target offset=({crop.target_offset_east_m:.1f}m E, {crop.target_offset_north_m:.1f}m N)  contains={str(crop.contains_target).lower()}</text>
{sensitivity_lines}
</svg>
"""
    path.write_text(content, encoding="utf-8")


def _angular_difference_deg(first_deg: float, second_deg: float) -> float:
    raw = abs(first_deg - second_deg) % 360.0
    return min(raw, 360.0 - raw)
