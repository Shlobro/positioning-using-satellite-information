"""Optional RoMa-backed neural matcher for recursive sequence experiments."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps


MIN_TEMPLATE_SIDE_PX = 12
MIN_TEMPLATE_TEXTURE_STDDEV = 4.0
MIN_SAMPLED_MATCHES = 256
MIN_INLIER_COUNT = 48
MIN_INLIER_RATIO = 0.12
MIN_INLIER_MEAN_CERTAINTY = 0.60
MAX_INLIER_MEAN_REPROJECTION_ERROR_PX = 10.0
DEFAULT_SAMPLE_COUNT = 5000


@dataclass(frozen=True)
class RoMaMatchDecision:
    """Outcome of one RoMa-backed measurement update."""

    accepted: bool
    estimate_source: str
    confidence_radius_m: float
    estimated_pixel_x: float
    estimated_pixel_y: float
    match_score: float | None
    runner_up_match_score: float | None


class RoMaBackend(Protocol):
    """Minimal backend protocol needed from a RoMa model object."""

    def match(self, image_a, image_b, *args, device=None): ...

    def sample(self, matches, certainty, num=DEFAULT_SAMPLE_COUNT): ...

    def to_pixel_coordinates(self, coords, height_a, width_a, height_b=None, width_b=None): ...


class RoMaRegressionMatcher:
    """Match a normalized frame against the calibrated map crop with RoMa."""

    def __init__(
        self,
        map_image_path: Path,
        *,
        model_name: str = "roma_outdoor",
        device: str = "auto",
        backend: RoMaBackend | None = None,
        sample_count: int = DEFAULT_SAMPLE_COUNT,
    ) -> None:
        self.map_image_path = map_image_path
        self.model_name = model_name
        self.device = _resolve_device(device)
        self.sample_count = sample_count
        self._map_image = _load_map_image(map_image_path)
        self._backend = backend if backend is not None else _load_backend(model_name=model_name, device=self.device)

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
    ) -> RoMaMatchDecision:
        """Return the best RoMa-supported center inside the provided map crop."""
        if measurement_update_radius_m < 0.0:
            raise ValueError("measurement_update_radius_m must be non-negative")

        if not crop_inside_image:
            return _build_fallback("fallback_roma_crop_outside_map", measurement_update_radius_m)

        template_width_px = max(1, int(round(ground_width_px)))
        template_height_px = max(1, int(round(ground_height_px)))
        if template_width_px < MIN_TEMPLATE_SIDE_PX or template_height_px < MIN_TEMPLATE_SIDE_PX:
            return _build_fallback("fallback_roma_template_too_small", measurement_update_radius_m)

        search_left = int(round(crop_min_x))
        search_top = int(round(crop_min_y))
        search_right = int(round(crop_max_x))
        search_bottom = int(round(crop_max_y))
        search_width_px = search_right - search_left
        search_height_px = search_bottom - search_top
        if search_width_px < template_width_px or search_height_px < template_height_px:
            return _build_fallback("fallback_roma_crop_smaller_than_template", measurement_update_radius_m)

        try:
            frame_template, texture_stddev = _load_frame_template(
                frame_image_path=frame_image_path,
                normalization_rotation_deg=normalization_rotation_deg,
                width_px=template_width_px,
                height_px=template_height_px,
            )
        except OSError:
            return _build_fallback("fallback_roma_frame_load_error", measurement_update_radius_m)

        if texture_stddev < MIN_TEMPLATE_TEXTURE_STDDEV:
            return _build_fallback("fallback_roma_low_texture", measurement_update_radius_m)

        map_crop = self._map_image.crop((search_left, search_top, search_right, search_bottom))
        matches, certainty = self._backend.match(frame_template, map_crop, device=self.device)
        sampled_matches, sampled_certainty = self._backend.sample(matches, certainty, num=self.sample_count)
        match_count = int(sampled_matches.shape[0])
        if match_count < MIN_SAMPLED_MATCHES:
            return _build_fallback("fallback_roma_insufficient_matches", measurement_update_radius_m)

        frame_points, crop_points = self._backend.to_pixel_coordinates(
            sampled_matches,
            template_height_px,
            template_width_px,
            search_height_px,
            search_width_px,
        )
        frame_points_np = _to_numpy_points(frame_points)
        crop_points_np = _to_numpy_points(crop_points)
        certainty_np = _to_numpy_certainty(sampled_certainty)

        affine_matrix, inlier_mask = cv2.estimateAffinePartial2D(
            frame_points_np,
            crop_points_np,
            method=cv2.RANSAC,
            ransacReprojThreshold=5.0,
            maxIters=4000,
            confidence=0.999,
            refineIters=10,
        )
        if affine_matrix is None or inlier_mask is None:
            return _build_fallback("fallback_roma_transform_failed", measurement_update_radius_m)

        inlier_flags = inlier_mask.ravel().astype(bool)
        inlier_count = int(inlier_flags.sum())
        inlier_ratio = inlier_count / match_count
        if inlier_count < MIN_INLIER_COUNT or inlier_ratio < MIN_INLIER_RATIO:
            return _build_fallback("fallback_roma_weak_inlier_support", measurement_update_radius_m)

        inlier_certainty = certainty_np[inlier_flags]
        mean_inlier_certainty = float(inlier_certainty.mean())
        if mean_inlier_certainty < MIN_INLIER_MEAN_CERTAINTY:
            return _build_fallback("fallback_roma_low_certainty", measurement_update_radius_m)

        inlier_frame_points = frame_points_np[inlier_flags]
        inlier_crop_points = crop_points_np[inlier_flags]
        reprojected_points = cv2.transform(inlier_frame_points.reshape(-1, 1, 2), affine_matrix).reshape(-1, 2)
        reprojection_errors = np.linalg.norm(reprojected_points - inlier_crop_points, axis=1)
        mean_reprojection_error = float(reprojection_errors.mean())
        if mean_reprojection_error > MAX_INLIER_MEAN_REPROJECTION_ERROR_PX:
            return _build_fallback("fallback_roma_high_reprojection_error", measurement_update_radius_m)

        center_point = np.array([[[template_width_px / 2.0, template_height_px / 2.0]]], dtype=np.float32)
        transformed_center = cv2.transform(center_point, affine_matrix)[0][0]
        center_x = float(search_left + transformed_center[0])
        center_y = float(search_top + transformed_center[1])
        if center_x < search_left or center_y < search_top:
            return _build_fallback("fallback_roma_center_outside_crop", measurement_update_radius_m)
        if center_x > search_right or center_y > search_bottom:
            return _build_fallback("fallback_roma_center_outside_crop", measurement_update_radius_m)

        match_score = _score_match(
            inlier_ratio=inlier_ratio,
            mean_inlier_certainty=mean_inlier_certainty,
            mean_reprojection_error=mean_reprojection_error,
        )
        confidence_radius_m = _derive_confidence_radius_m(
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference_max_residual_m,
            match_score=match_score,
        )
        return RoMaMatchDecision(
            accepted=True,
            estimate_source="matched_roma",
            confidence_radius_m=confidence_radius_m,
            estimated_pixel_x=center_x,
            estimated_pixel_y=center_y,
            match_score=match_score,
            runner_up_match_score=None,
        )


def _load_backend(*, model_name: str, device: str) -> RoMaBackend:
    from romatch import roma_outdoor, tiny_roma_v1_outdoor

    if model_name == "roma_outdoor":
        return roma_outdoor(device=device)
    if model_name == "tiny_roma_v1_outdoor":
        return tiny_roma_v1_outdoor(device=device)
    raise ValueError(f"unsupported model_name '{model_name}'")


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_map_image(image_path: Path) -> Image.Image:
    with Image.open(image_path) as image:
        return image.convert("RGB").copy()


def _load_frame_template(
    *,
    frame_image_path: Path,
    normalization_rotation_deg: float,
    width_px: int,
    height_px: int,
) -> tuple[Image.Image, float]:
    with Image.open(frame_image_path) as image:
        grayscale = ImageOps.autocontrast(image.convert("L"))
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
        texture_stddev = float(np.asarray(rotated, dtype=np.float32).std())
        rgb_rotated = Image.merge("RGB", (rotated, rotated, rotated))
        resized = rgb_rotated.resize((width_px, height_px), resample=Image.Resampling.BILINEAR)
        return resized, texture_stddev


def _to_numpy_points(points) -> np.ndarray:
    points_np = points.detach().cpu().numpy() if hasattr(points, "detach") else np.asarray(points)
    return np.asarray(points_np, dtype=np.float32)


def _to_numpy_certainty(certainty) -> np.ndarray:
    certainty_np = certainty.detach().cpu().numpy() if hasattr(certainty, "detach") else np.asarray(certainty)
    return np.asarray(certainty_np, dtype=np.float32)


def _score_match(
    *,
    inlier_ratio: float,
    mean_inlier_certainty: float,
    mean_reprojection_error: float,
) -> float:
    ratio_component = min(1.0, max(0.0, inlier_ratio / 0.50))
    certainty_component = min(1.0, max(0.0, mean_inlier_certainty))
    reprojection_component = max(0.0, 1.0 - (mean_reprojection_error / 12.0))
    return (0.35 * ratio_component) + (0.45 * certainty_component) + (0.20 * reprojection_component)


def _derive_confidence_radius_m(
    *,
    measurement_update_radius_m: float,
    georeference_max_residual_m: float,
    match_score: float,
) -> float:
    floor_radius_m = max(georeference_max_residual_m, 1.0)
    if measurement_update_radius_m == 0.0:
        return floor_radius_m
    score_penalty = max(0.0, 1.0 - match_score)
    confidence_radius_m = floor_radius_m + (score_penalty * measurement_update_radius_m)
    return min(max(floor_radius_m, confidence_radius_m), measurement_update_radius_m)


def _build_fallback(estimate_source: str, confidence_radius_m: float) -> RoMaMatchDecision:
    return RoMaMatchDecision(
        accepted=False,
        estimate_source=estimate_source,
        confidence_radius_m=confidence_radius_m,
        estimated_pixel_x=0.0,
        estimated_pixel_y=0.0,
        match_score=None,
        runner_up_match_score=None,
    )
