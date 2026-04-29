"""Artifact writers for sequence-search evaluation reports."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path


def write_sequence_search_summary(path: Path, artifacts) -> None:
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
        "measurement_update_radius_m": artifacts.measurement_update_radius_m,
        "neural_matcher_name": artifacts.neural_matcher_name,
        "scenarios": [
            {
                "scenario_name": scenario.scenario_name,
                "description": scenario.description,
                "frame_count": scenario.frame_count,
                "contained_frame_count": scenario.contained_frame_count,
                "matched_frame_count": scenario.matched_frame_count,
                "fallback_frame_count": scenario.fallback_frame_count,
                "estimate_source_counts": scenario.estimate_source_counts,
                "fallback_source_counts": scenario.fallback_source_counts,
                "crop_inside_image_count": scenario.crop_inside_image_count,
                "map_constrained_frame_count": scenario.map_constrained_frame_count,
                "map_limited_frame_count": scenario.map_limited_frame_count,
                "first_target_miss_frame_index": scenario.first_target_miss_frame_index,
                "first_crop_outside_image_frame_index": scenario.first_crop_outside_image_frame_index,
                "longest_inside_image_streak": scenario.longest_inside_image_streak,
                "containment_ratio": scenario.contained_frame_count / scenario.frame_count,
                "map_coverage_ratio": scenario.crop_inside_image_count / scenario.frame_count,
                "max_target_offset_m": scenario.max_target_offset_m,
                "average_crop_side_m": scenario.average_crop_side_m,
                "mean_estimate_error_m": scenario.mean_estimate_error_m,
                "max_estimate_error_m": scenario.max_estimate_error_m,
                "final_estimate_error_m": scenario.final_estimate_error_m,
                "mean_match_score": scenario.mean_match_score,
                "min_match_score": scenario.min_match_score,
                "frames": [asdict(frame) for frame in scenario.frames],
            }
            for scenario in artifacts.scenarios
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_sequence_search_debug_svg(path: Path, artifacts) -> None:
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
        "seed_only": ("#c05621", "#7d4e57"),
        "oracle_previous_truth": ("#0f4c5c", "#8ecae6"),
        "recursive_oracle_estimate": ("#2b9348", "#b7e4c7"),
        "recursive_placeholder_matcher": ("#6a4c93", "#d4b8f2"),
        "recursive_image_baseline_matcher": ("#8a5a44", "#f4d6c2"),
        "recursive_image_map_constrained_matcher": ("#9d4edd", "#ead7ff"),
        "recursive_classical_matcher": ("#1d3557", "#a8dadc"),
        "recursive_roma_matcher": ("#264653", "#bde0d8"),
        "recursive_roma_map_constrained_matcher": ("#006d77", "#caf0f8"),
        "recursive_roma_velocity_likelihood_matcher": ("#bc4749", "#ffd6d6"),
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
            f'<text x="40" y="{text_y:.0f}" font-family="monospace" font-size="12" fill="#213547">{scenario.scenario_name}: contains={scenario.contained_frame_count}/{scenario.frame_count} map={scenario.crop_inside_image_count}/{scenario.frame_count} constrained={scenario.map_constrained_frame_count} limited={scenario.map_limited_frame_count} matches={scenario.matched_frame_count} err_mean={scenario.mean_estimate_error_m:.1f}m err_max={scenario.max_estimate_error_m:.1f}m score_mean={format_optional_float(scenario.mean_match_score)} first_offmap={format_optional_index(scenario.first_crop_outside_image_frame_index)} streak={scenario.longest_inside_image_streak} avg_crop={scenario.average_crop_side_m:.1f}m</text>'
        )
        text_y += 16.0

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{int(canvas_width)}" height="{int(text_y + 24.0)}" viewBox="0 0 {int(canvas_width)} {int(text_y + 24.0)}">
  <rect width="{int(canvas_width)}" height="{int(text_y + 24.0)}" fill="#f4f1e8"/>
  <text x="40" y="24" font-family="monospace" font-size="16" fill="#213547">Sequence Search Debug</text>
  <text x="40" y="42" font-family="monospace" font-size="12" fill="#213547">seed=({artifacts.seed_latitude_deg:.6f}, {artifacts.seed_longitude_deg:.6f}) speed={artifacts.max_speed_mps:.1f}mps base_radius={artifacts.base_search_radius_m:.1f}m update_radius={artifacts.measurement_update_radius_m:.1f}m residual={artifacts.georeference_max_residual_m:.2f}m</text>
  <rect x="{origin_x}" y="{origin_y}" width="{map_width:.2f}" height="{map_height:.2f}" fill="#ffffff" stroke="#50623a" stroke-width="2"/>
  {' '.join(overlay_parts)}
  <polyline points="{truth_points}" fill="none" stroke="#213547" stroke-width="2"/>
  {''.join(summary_lines)}
</svg>
"""
    path.write_text(content, encoding="utf-8")


def format_optional_index(index: int | None) -> str:
    """Format an optional frame index for SVG summary text."""
    if index is None:
        return "none"
    return str(index)


def format_optional_float(value: float | None) -> str:
    """Format an optional float for SVG summary text."""
    if value is None:
        return "n/a"
    return f"{value:.2f}"
