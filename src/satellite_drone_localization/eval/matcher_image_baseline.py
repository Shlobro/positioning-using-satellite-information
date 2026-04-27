"""Simple image-based matcher baseline for recursive sequence experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


COMPARISON_SIZE_PX = (32, 32)


@dataclass(frozen=True)
class ImageBaselineMatchDecision:
    """Outcome of one simple image-baseline measurement update."""

    accepted: bool
    estimate_source: str
    confidence_radius_m: float
    estimated_pixel_x: float
    estimated_pixel_y: float
    match_score: float | None
    runner_up_match_score: float | None


class ImageBaselineMatcher:
    """Match a north-up frame template against a calibrated map crop."""

    def __init__(self, map_image_path: Path) -> None:
        self.map_image_path = map_image_path
        self._map_edge_image = _load_edge_image(map_image_path)

    def match_frame(
        self,
        *,
        frame_image_path: Path,
        normalization_rotation_deg: float,
        ground_width_px: float,
        ground_height_px: float,
        crop_min_x: float,
        crop_min_y: float,
        crop_max_x: float,
        crop_max_y: float,
        crop_inside_image: bool,
        measurement_update_radius_m: float,
        georeference_max_residual_m: float,
    ) -> ImageBaselineMatchDecision:
        """Return the best template-match center inside the provided map crop."""
        if measurement_update_radius_m < 0.0:
            raise ValueError("measurement_update_radius_m must be non-negative")

        if not crop_inside_image:
            return ImageBaselineMatchDecision(
                accepted=False,
                estimate_source="fallback_image_crop_outside_map",
                confidence_radius_m=measurement_update_radius_m,
                estimated_pixel_x=0.0,
                estimated_pixel_y=0.0,
                match_score=None,
                runner_up_match_score=None,
            )

        template_width_px = max(1, int(round(ground_width_px)))
        template_height_px = max(1, int(round(ground_height_px)))
        if template_width_px < 12 or template_height_px < 12:
            return ImageBaselineMatchDecision(
                accepted=False,
                estimate_source="fallback_image_template_too_small",
                confidence_radius_m=measurement_update_radius_m,
                estimated_pixel_x=0.0,
                estimated_pixel_y=0.0,
                match_score=None,
                runner_up_match_score=None,
            )

        search_left = int(round(crop_min_x))
        search_top = int(round(crop_min_y))
        search_right = int(round(crop_max_x))
        search_bottom = int(round(crop_max_y))
        search_width_px = search_right - search_left
        search_height_px = search_bottom - search_top
        if search_width_px < template_width_px or search_height_px < template_height_px:
            return ImageBaselineMatchDecision(
                accepted=False,
                estimate_source="fallback_image_crop_smaller_than_template",
                confidence_radius_m=measurement_update_radius_m,
                estimated_pixel_x=0.0,
                estimated_pixel_y=0.0,
                match_score=None,
                runner_up_match_score=None,
            )

        try:
            frame_template = _load_frame_template(
                frame_image_path=frame_image_path,
                normalization_rotation_deg=normalization_rotation_deg,
                width_px=template_width_px,
                height_px=template_height_px,
            )
        except OSError:
            return ImageBaselineMatchDecision(
                accepted=False,
                estimate_source="fallback_image_frame_load_error",
                confidence_radius_m=measurement_update_radius_m,
                estimated_pixel_x=0.0,
                estimated_pixel_y=0.0,
                match_score=None,
                runner_up_match_score=None,
            )

        map_crop = self._map_edge_image.crop((search_left, search_top, search_right, search_bottom))
        best_score = -1.0
        runner_up_score = -1.0
        best_position = None

        step_x = max(1, min(8, template_width_px // 6 or 1))
        step_y = max(1, min(8, template_height_px // 6 or 1))
        candidate_xs = _build_candidate_positions(search_width_px - template_width_px, step_x)
        candidate_ys = _build_candidate_positions(search_height_px - template_height_px, step_y)

        for local_y in candidate_ys:
            for local_x in candidate_xs:
                candidate = map_crop.crop(
                    (
                        local_x,
                        local_y,
                        local_x + template_width_px,
                        local_y + template_height_px,
                    )
                )
                candidate = _prepare_match_image(candidate)
                score = _score_images(frame_template, candidate)
                if score > best_score:
                    runner_up_score = best_score
                    best_score = score
                    best_position = (local_x, local_y)
                elif score > runner_up_score:
                    runner_up_score = score

        if best_position is None:
            return ImageBaselineMatchDecision(
                accepted=False,
                estimate_source="fallback_image_no_candidates",
                confidence_radius_m=measurement_update_radius_m,
                estimated_pixel_x=0.0,
                estimated_pixel_y=0.0,
                match_score=None,
                runner_up_match_score=None,
            )

        best_local_x, best_local_y = best_position
        center_x = search_left + best_local_x + (template_width_px / 2.0)
        center_y = search_top + best_local_y + (template_height_px / 2.0)
        confidence_radius_m = _derive_confidence_radius_m(
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference_max_residual_m,
            best_score=best_score,
        )
        return ImageBaselineMatchDecision(
            accepted=True,
            estimate_source="matched_image_baseline",
            confidence_radius_m=confidence_radius_m,
            estimated_pixel_x=center_x,
            estimated_pixel_y=center_y,
            match_score=best_score,
            runner_up_match_score=runner_up_score if runner_up_score >= 0.0 else None,
        )


def _build_candidate_positions(max_offset_px: int, step_px: int) -> list[int]:
    positions = list(range(0, max_offset_px + 1, step_px))
    if not positions or positions[-1] != max_offset_px:
        positions.append(max_offset_px)
    return positions


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
) -> Image.Image:
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
        resized = rotated.resize((width_px, height_px), resample=Image.Resampling.BILINEAR)
        return _prepare_match_image(resized)


def _prepare_match_image(image: Image.Image) -> Image.Image:
    prepared = image.resize(COMPARISON_SIZE_PX, resample=Image.Resampling.BILINEAR)
    prepared = ImageOps.autocontrast(prepared)
    return prepared.filter(ImageFilter.FIND_EDGES)


def _score_images(left: Image.Image, right: Image.Image) -> float:
    diff = ImageChops.difference(left, right)
    mean_diff = ImageStat.Stat(diff).mean[0]
    return max(0.0, 1.0 - (mean_diff / 255.0))


def _derive_confidence_radius_m(
    *,
    measurement_update_radius_m: float,
    georeference_max_residual_m: float,
    best_score: float,
) -> float:
    floor_radius_m = max(georeference_max_residual_m, 1.0)
    if measurement_update_radius_m == 0.0:
        return floor_radius_m
    score_penalty = max(0.0, 1.0 - best_score)
    confidence_radius_m = floor_radius_m + (score_penalty * measurement_update_radius_m)
    return min(max(floor_radius_m, confidence_radius_m), measurement_update_radius_m)
