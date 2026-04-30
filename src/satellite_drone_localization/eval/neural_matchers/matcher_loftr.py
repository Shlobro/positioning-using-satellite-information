"""Optional EfficientLoFTR-style matcher for sequence benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..matcher_roma import (
    MAX_AFFINE_SCALE,
    MAX_INLIER_MEAN_REPROJECTION_ERROR_PX,
    MIN_AFFINE_SCALE,
    MIN_INLIER_COUNT,
    MIN_INLIER_RATIO,
    MIN_INLIER_SPATIAL_COVERAGE,
    MIN_TEMPLATE_SIDE_PX,
    MIN_TEMPLATE_TEXTURE_STDDEV,
    _derive_confidence_radius_m,
    _estimate_affine_scale,
    _estimate_spatial_coverage,
)


MIN_LOFTR_MEAN_CONFIDENCE = 0.35
DEFAULT_LOFTR_MODEL_NAME = "efficientloftr_outdoor"


@dataclass(frozen=True)
class LoFTRMatchDecision:
    """Outcome of one LoFTR-style measurement update."""

    accepted: bool
    estimate_source: str
    confidence_radius_m: float
    estimated_pixel_x: float
    estimated_pixel_y: float
    match_score: float | None
    runner_up_match_score: float | None
    diagnostics: dict[str, float | int] | None


class LoFTRBackend(Protocol):
    """Backend protocol for LoFTR-family models."""

    def match_keypoints(self, image_a: Image.Image, image_b: Image.Image, *, device: str): ...


class LoFTRRegressionMatcher:
    """Match a normalized frame against the calibrated map crop with a LoFTR-style backend."""

    def __init__(
        self,
        map_image_path: Path,
        *,
        model_name: str = DEFAULT_LOFTR_MODEL_NAME,
        device: str = "auto",
        backend: LoFTRBackend | None = None,
        repo_path: Path | None = None,
        checkpoint_path: Path | None = None,
        model_type: str = "full",
        precision: str = "fp32",
    ) -> None:
        self.map_image_path = map_image_path
        self.model_name = model_name
        self.device = _resolve_device(device)
        self._map_image = _load_map_image(map_image_path)
        self._backend = backend if backend is not None else _load_backend(
            repo_path=repo_path,
            checkpoint_path=checkpoint_path,
            model_type=model_type,
            precision=precision,
            device=self.device,
        )

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
    ) -> LoFTRMatchDecision:
        """Return the best LoFTR-supported center inside the provided map crop."""
        if measurement_update_radius_m < 0.0:
            raise ValueError("measurement_update_radius_m must be non-negative")
        if not crop_inside_image:
            return _build_fallback("fallback_loftr_crop_outside_map", measurement_update_radius_m)

        template_width_px = max(1, int(round(ground_width_px)))
        template_height_px = max(1, int(round(ground_height_px)))
        if template_width_px < MIN_TEMPLATE_SIDE_PX or template_height_px < MIN_TEMPLATE_SIDE_PX:
            return _build_fallback("fallback_loftr_template_too_small", measurement_update_radius_m)

        search_left = int(round(crop_min_x))
        search_top = int(round(crop_min_y))
        search_right = int(round(crop_max_x))
        search_bottom = int(round(crop_max_y))
        search_width_px = search_right - search_left
        search_height_px = search_bottom - search_top
        if search_width_px < template_width_px or search_height_px < template_height_px:
            return _build_fallback("fallback_loftr_crop_smaller_than_template", measurement_update_radius_m)

        try:
            frame_template, texture_stddev = _load_frame_template(
                frame_image_path=frame_image_path,
                normalization_rotation_deg=normalization_rotation_deg,
                width_px=template_width_px,
                height_px=template_height_px,
            )
        except OSError:
            return _build_fallback("fallback_loftr_frame_load_error", measurement_update_radius_m)

        if texture_stddev < MIN_TEMPLATE_TEXTURE_STDDEV:
            return _build_fallback("fallback_loftr_low_texture", measurement_update_radius_m)

        map_crop = self._map_image.crop((search_left, search_top, search_right, search_bottom))
        frame_points, crop_points, confidences = self._backend.match_keypoints(
            frame_template,
            map_crop,
            device=self.device,
        )
        frame_points_np = _to_numpy_points(frame_points)
        crop_points_np = _to_numpy_points(crop_points)
        confidence_np = _to_numpy_confidence(confidences)
        match_count = int(min(frame_points_np.shape[0], crop_points_np.shape[0], confidence_np.shape[0]))
        if match_count < MIN_INLIER_COUNT:
            return _build_fallback(
                "fallback_loftr_insufficient_matches",
                measurement_update_radius_m,
                {"match_count": match_count},
            )

        frame_points_np = frame_points_np[:match_count]
        crop_points_np = crop_points_np[:match_count]
        confidence_np = confidence_np[:match_count]
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
            return _build_fallback("fallback_loftr_transform_failed", measurement_update_radius_m)

        inlier_flags = inlier_mask.ravel().astype(bool)
        inlier_count = int(inlier_flags.sum())
        inlier_ratio = inlier_count / match_count
        diagnostics: dict[str, float | int] = {
            "match_count": match_count,
            "inlier_count": inlier_count,
            "inlier_ratio": inlier_ratio,
        }
        if inlier_count < MIN_INLIER_COUNT or inlier_ratio < MIN_INLIER_RATIO:
            return _build_fallback("fallback_loftr_weak_inlier_support", measurement_update_radius_m, diagnostics)

        inlier_confidence = confidence_np[inlier_flags]
        mean_inlier_confidence = float(inlier_confidence.mean())
        diagnostics["mean_inlier_confidence"] = mean_inlier_confidence
        if mean_inlier_confidence < MIN_LOFTR_MEAN_CONFIDENCE:
            return _build_fallback("fallback_loftr_low_confidence", measurement_update_radius_m, diagnostics)

        inlier_frame_points = frame_points_np[inlier_flags]
        inlier_crop_points = crop_points_np[inlier_flags]
        reprojected_points = cv2.transform(inlier_frame_points.reshape(-1, 1, 2), affine_matrix).reshape(-1, 2)
        mean_reprojection_error = float(np.linalg.norm(reprojected_points - inlier_crop_points, axis=1).mean())
        diagnostics["mean_reprojection_error_px"] = mean_reprojection_error
        if mean_reprojection_error > MAX_INLIER_MEAN_REPROJECTION_ERROR_PX:
            return _build_fallback("fallback_loftr_high_reprojection_error", measurement_update_radius_m, diagnostics)

        spatial_coverage = _estimate_spatial_coverage(
            inlier_frame_points=inlier_frame_points,
            template_width_px=template_width_px,
            template_height_px=template_height_px,
        )
        diagnostics["inlier_spatial_coverage"] = spatial_coverage
        if spatial_coverage < MIN_INLIER_SPATIAL_COVERAGE:
            return _build_fallback("fallback_loftr_poor_spatial_coverage", measurement_update_radius_m, diagnostics)

        affine_scale = _estimate_affine_scale(affine_matrix)
        diagnostics["affine_scale"] = affine_scale
        if affine_scale < MIN_AFFINE_SCALE or affine_scale > MAX_AFFINE_SCALE:
            return _build_fallback("fallback_loftr_implausible_scale", measurement_update_radius_m, diagnostics)

        center_point = np.array([[[template_width_px / 2.0, template_height_px / 2.0]]], dtype=np.float32)
        transformed_center = cv2.transform(center_point, affine_matrix)[0][0]
        center_x = float(search_left + transformed_center[0])
        center_y = float(search_top + transformed_center[1])
        diagnostics["estimated_center_x_px"] = center_x
        diagnostics["estimated_center_y_px"] = center_y
        if center_x < search_left or center_y < search_top or center_x > search_right or center_y > search_bottom:
            return _build_fallback("fallback_loftr_center_outside_crop", measurement_update_radius_m, diagnostics)

        match_score = _score_match(
            inlier_ratio=inlier_ratio,
            mean_inlier_confidence=mean_inlier_confidence,
            mean_reprojection_error=mean_reprojection_error,
        )
        return LoFTRMatchDecision(
            accepted=True,
            estimate_source="matched_loftr",
            confidence_radius_m=_derive_confidence_radius_m(
                measurement_update_radius_m=measurement_update_radius_m,
                georeference_max_residual_m=georeference_max_residual_m,
                match_score=match_score,
            ),
            estimated_pixel_x=center_x,
            estimated_pixel_y=center_y,
            match_score=match_score,
            runner_up_match_score=None,
            diagnostics=diagnostics,
        )


class EfficientLoFTRBackend:
    """Thin adapter for an external zju3dv/EfficientLoFTR checkout."""

    def __init__(self, *, repo_path: Path, checkpoint_path: Path, model_type: str, precision: str, device: str) -> None:
        if model_type not in {"full", "opt"}:
            raise ValueError("model_type must be 'full' or 'opt'")
        if precision not in {"fp32", "mp", "fp16"}:
            raise ValueError("precision must be 'fp32', 'mp', or 'fp16'")
        if not repo_path.exists():
            raise FileNotFoundError(f"EfficientLoFTR repo path does not exist: {repo_path}")
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"EfficientLoFTR checkpoint does not exist: {checkpoint_path}")

        import torch
        from copy import deepcopy

        sys.path.insert(0, str(repo_path))
        try:
            from src.loftr import LoFTR, full_default_cfg, opt_default_cfg, reparameter
        finally:
            if sys.path[0] == str(repo_path):
                sys.path.pop(0)

        config = deepcopy(full_default_cfg if model_type == "full" else opt_default_cfg)
        config["mp"] = precision == "mp"
        config["half"] = precision == "fp16"
        matcher = LoFTR(config=config)
        # EfficientLoFTR checkpoints include PyTorch Lightning metadata, which
        # PyTorch 2.6+ rejects under the default weights-only loader. This path
        # is explicit opt-in and should only be used with trusted checkpoints.
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        state_dict = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        matcher.load_state_dict(state_dict)
        matcher = reparameter(matcher).eval().to(device)
        if precision == "fp16":
            matcher = matcher.half()
        self._matcher = matcher
        self._torch = torch
        self._precision = precision

    def match_keypoints(self, image_a: Image.Image, image_b: Image.Image, *, device: str):
        img0 = _pil_to_divisible_gray_array(image_a)
        img1 = _pil_to_divisible_gray_array(image_b)
        torch = self._torch
        tensor0 = torch.from_numpy(img0)[None][None].to(device) / 255.0
        tensor1 = torch.from_numpy(img1)[None][None].to(device) / 255.0
        if self._precision == "fp16":
            tensor0 = tensor0.half()
            tensor1 = tensor1.half()
        batch = {"image0": tensor0, "image1": tensor1}
        with torch.no_grad():
            if self._precision == "mp":
                with torch.autocast(enabled=True, device_type="cuda"):
                    self._matcher(batch)
            else:
                self._matcher(batch)
        return batch["mkpts0_f"], batch["mkpts1_f"], batch["mconf"]


def _load_backend(
    *,
    repo_path: Path | None,
    checkpoint_path: Path | None,
    model_type: str,
    precision: str,
    device: str,
) -> LoFTRBackend:
    if repo_path is None or checkpoint_path is None:
        raise ValueError(
            "LoFTR benchmarking requires --loftr-repo-path and --loftr-checkpoint, "
            "or an injected test backend."
        )
    return EfficientLoFTRBackend(
        repo_path=repo_path,
        checkpoint_path=checkpoint_path,
        model_type=model_type,
        precision=precision,
        device=device,
    )


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


def _pil_to_divisible_gray_array(image: Image.Image) -> np.ndarray:
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    height = max(32, int(gray.shape[0] // 32 * 32))
    width = max(32, int(gray.shape[1] // 32 * 32))
    if gray.shape[0] != height or gray.shape[1] != width:
        gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
    return gray.astype(np.float32)


def _to_numpy_points(points) -> np.ndarray:
    points_np = points.detach().cpu().numpy() if hasattr(points, "detach") else np.asarray(points)
    return np.asarray(points_np, dtype=np.float32).reshape(-1, 2)


def _to_numpy_confidence(confidence) -> np.ndarray:
    confidence_np = confidence.detach().cpu().numpy() if hasattr(confidence, "detach") else np.asarray(confidence)
    return np.asarray(confidence_np, dtype=np.float32).reshape(-1)


def _score_match(
    *,
    inlier_ratio: float,
    mean_inlier_confidence: float,
    mean_reprojection_error: float,
) -> float:
    ratio_component = min(1.0, max(0.0, inlier_ratio / 0.50))
    confidence_component = min(1.0, max(0.0, mean_inlier_confidence))
    reprojection_component = max(0.0, 1.0 - (mean_reprojection_error / 12.0))
    return (0.35 * ratio_component) + (0.45 * confidence_component) + (0.20 * reprojection_component)


def _build_fallback(
    estimate_source: str,
    confidence_radius_m: float,
    diagnostics: dict[str, float | int] | None = None,
) -> LoFTRMatchDecision:
    return LoFTRMatchDecision(
        accepted=False,
        estimate_source=estimate_source,
        confidence_radius_m=confidence_radius_m,
        estimated_pixel_x=0.0,
        estimated_pixel_y=0.0,
        match_score=None,
        runner_up_match_score=None,
        diagnostics=diagnostics,
    )
