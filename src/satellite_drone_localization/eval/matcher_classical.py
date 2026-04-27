"""Classical feature-based matcher for recursive sequence experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


MIN_TEMPLATE_SIDE_PX = 12
MIN_TEMPLATE_TEXTURE_STDDEV = 4.0
MIN_TEMPLATE_KEYPOINTS = 8
MIN_GOOD_MATCHES = 6
MIN_INLIER_COUNT = 4
MIN_INLIER_RATIO = 0.45
MAX_INLIER_MEAN_DISTANCE = 48.0


@dataclass(frozen=True)
class ClassicalMatchDecision:
    """Outcome of one classical feature-based measurement update."""

    accepted: bool
    estimate_source: str
    confidence_radius_m: float
    estimated_pixel_x: float
    estimated_pixel_y: float
    match_score: float | None
    runner_up_match_score: float | None


class ClassicalFeatureMatcher:
    """Match a normalized frame against the calibrated map crop with local features."""

    def __init__(self, map_image_path: Path) -> None:
        self.map_image_path = map_image_path
        self._map_gray = _load_grayscale_array(map_image_path)
        self._akaze = cv2.AKAZE_create()
        self._orb = cv2.ORB_create(nfeatures=800, edgeThreshold=5, fastThreshold=5)

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
    ) -> ClassicalMatchDecision:
        """Return the best feature-supported center inside the provided map crop."""
        if measurement_update_radius_m < 0.0:
            raise ValueError("measurement_update_radius_m must be non-negative")

        if not crop_inside_image:
            return _build_fallback("fallback_classical_crop_outside_map", measurement_update_radius_m)

        template_width_px = max(1, int(round(ground_width_px)))
        template_height_px = max(1, int(round(ground_height_px)))
        if template_width_px < MIN_TEMPLATE_SIDE_PX or template_height_px < MIN_TEMPLATE_SIDE_PX:
            return _build_fallback("fallback_classical_template_too_small", measurement_update_radius_m)

        search_left = int(round(crop_min_x))
        search_top = int(round(crop_min_y))
        search_right = int(round(crop_max_x))
        search_bottom = int(round(crop_max_y))
        search_width_px = search_right - search_left
        search_height_px = search_bottom - search_top
        if search_width_px < template_width_px or search_height_px < template_height_px:
            return _build_fallback("fallback_classical_crop_smaller_than_template", measurement_update_radius_m)

        try:
            frame_template, texture_stddev = _load_frame_template(
                frame_image_path=frame_image_path,
                normalization_rotation_deg=normalization_rotation_deg,
                width_px=template_width_px,
                height_px=template_height_px,
            )
        except OSError:
            return _build_fallback("fallback_classical_frame_load_error", measurement_update_radius_m)

        if texture_stddev < MIN_TEMPLATE_TEXTURE_STDDEV:
            return _build_fallback("fallback_classical_low_texture", measurement_update_radius_m)

        crop_array = self._map_gray[search_top:search_bottom, search_left:search_right]
        if crop_array.size == 0:
            return _build_fallback("fallback_classical_empty_crop", measurement_update_radius_m)

        decision = self._match_with_detector(
            detector=self._akaze,
            frame_template=frame_template,
            crop_array=crop_array,
            search_left=search_left,
            search_top=search_top,
            template_width_px=template_width_px,
            template_height_px=template_height_px,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference_max_residual_m,
        )
        if decision.accepted:
            return decision
        if decision.estimate_source not in {
            "fallback_classical_insufficient_features",
            "fallback_classical_insufficient_matches",
            "fallback_classical_transform_failed",
            "fallback_classical_weak_inlier_support",
        }:
            return decision

        return self._match_with_detector(
            detector=self._orb,
            frame_template=frame_template,
            crop_array=crop_array,
            search_left=search_left,
            search_top=search_top,
            template_width_px=template_width_px,
            template_height_px=template_height_px,
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference_max_residual_m,
        )

    def _match_with_detector(
        self,
        *,
        detector,
        frame_template: np.ndarray,
        crop_array: np.ndarray,
        search_left: int,
        search_top: int,
        template_width_px: int,
        template_height_px: int,
        measurement_update_radius_m: float,
        georeference_max_residual_m: float,
    ) -> ClassicalMatchDecision:
        if detector is self._orb:
            frame_keypoints, frame_descriptors = _extract_orb_features(self._orb, frame_template)
            crop_keypoints, crop_descriptors = _extract_orb_features(self._orb, crop_array)
        else:
            frame_keypoints, frame_descriptors = detector.detectAndCompute(frame_template, None)
            crop_keypoints, crop_descriptors = detector.detectAndCompute(crop_array, None)
        if (
            frame_descriptors is None
            or crop_descriptors is None
            or len(frame_keypoints) < MIN_TEMPLATE_KEYPOINTS
            or len(crop_keypoints) < MIN_TEMPLATE_KEYPOINTS
        ):
            return _build_fallback("fallback_classical_insufficient_features", measurement_update_radius_m)

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        raw_matches = matcher.knnMatch(frame_descriptors, crop_descriptors, k=2)
        good_matches: list[cv2.DMatch] = []
        for pair in raw_matches:
            if len(pair) < 2:
                continue
            best_match, runner_up = pair
            if best_match.distance < 0.82 * runner_up.distance:
                good_matches.append(best_match)

        if len(good_matches) < MIN_GOOD_MATCHES:
            return _build_fallback("fallback_classical_insufficient_matches", measurement_update_radius_m)

        template_points = np.float32([frame_keypoints[match.queryIdx].pt for match in good_matches]).reshape(-1, 1, 2)
        crop_points = np.float32([crop_keypoints[match.trainIdx].pt for match in good_matches]).reshape(-1, 1, 2)
        affine_matrix, inlier_mask = cv2.estimateAffinePartial2D(
            template_points,
            crop_points,
            method=cv2.RANSAC,
            ransacReprojThreshold=6.0,
            maxIters=2000,
            confidence=0.99,
            refineIters=10,
        )
        if affine_matrix is None or inlier_mask is None:
            return _build_fallback("fallback_classical_transform_failed", measurement_update_radius_m)

        inlier_flags = inlier_mask.ravel().astype(bool)
        inlier_count = int(inlier_flags.sum())
        inlier_ratio = inlier_count / len(good_matches)
        if inlier_count < MIN_INLIER_COUNT or inlier_ratio < MIN_INLIER_RATIO:
            return _build_fallback("fallback_classical_weak_inlier_support", measurement_update_radius_m)

        inlier_distances = [good_matches[index].distance for index, flag in enumerate(inlier_flags) if flag]
        mean_inlier_distance = sum(inlier_distances) / len(inlier_distances)
        if mean_inlier_distance > MAX_INLIER_MEAN_DISTANCE:
            return _build_fallback("fallback_classical_weak_inlier_support", measurement_update_radius_m)

        center_point = np.array([[[template_width_px / 2.0, template_height_px / 2.0]]], dtype=np.float32)
        transformed_center = cv2.transform(center_point, affine_matrix)[0][0]
        center_x = float(search_left + transformed_center[0])
        center_y = float(search_top + transformed_center[1])
        if center_x < search_left or center_y < search_top:
            return _build_fallback("fallback_classical_center_outside_crop", measurement_update_radius_m)
        if center_x > (search_left + crop_array.shape[1]) or center_y > (search_top + crop_array.shape[0]):
            return _build_fallback("fallback_classical_center_outside_crop", measurement_update_radius_m)

        match_score = _score_match(
            inlier_ratio=inlier_ratio,
            mean_inlier_distance=mean_inlier_distance,
            inlier_count=inlier_count,
        )
        confidence_radius_m = _derive_confidence_radius_m(
            measurement_update_radius_m=measurement_update_radius_m,
            georeference_max_residual_m=georeference_max_residual_m,
            match_score=match_score,
        )
        return ClassicalMatchDecision(
            accepted=True,
            estimate_source="matched_classical_feature",
            confidence_radius_m=confidence_radius_m,
            estimated_pixel_x=center_x,
            estimated_pixel_y=center_y,
            match_score=match_score,
            runner_up_match_score=None,
        )


def _build_fallback(estimate_source: str, confidence_radius_m: float) -> ClassicalMatchDecision:
    return ClassicalMatchDecision(
        accepted=False,
        estimate_source=estimate_source,
        confidence_radius_m=confidence_radius_m,
        estimated_pixel_x=0.0,
        estimated_pixel_y=0.0,
        match_score=None,
        runner_up_match_score=None,
    )


def _load_grayscale_array(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as image:
        grayscale = ImageOps.autocontrast(image.convert("L"))
        return np.array(grayscale, dtype=np.uint8)


def _load_frame_template(
    *,
    frame_image_path: Path,
    normalization_rotation_deg: float,
    width_px: int,
    height_px: int,
) -> tuple[np.ndarray, float]:
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
        resized = rotated.resize((width_px, height_px), resample=Image.Resampling.BILINEAR)
        prepared = ImageOps.autocontrast(resized)
        array = np.array(prepared, dtype=np.uint8)
        equalized = cv2.equalizeHist(array)
        return equalized, texture_stddev


def _score_match(*, inlier_ratio: float, mean_inlier_distance: float, inlier_count: int) -> float:
    ratio_component = min(1.0, max(0.0, inlier_ratio))
    distance_component = max(0.0, 1.0 - (mean_inlier_distance / 80.0))
    count_component = min(1.0, inlier_count / 24.0)
    return (0.5 * ratio_component) + (0.3 * distance_component) + (0.2 * count_component)


def _extract_orb_features(
    detector,
    image_array: np.ndarray,
) -> tuple[list[cv2.KeyPoint], np.ndarray | None]:
    keypoints, descriptors = detector.detectAndCompute(image_array, None)
    if descriptors is not None and len(keypoints) >= MIN_TEMPLATE_KEYPOINTS:
        return keypoints, descriptors

    corner_points = cv2.goodFeaturesToTrack(
        image_array,
        maxCorners=160,
        qualityLevel=0.01,
        minDistance=6,
        blockSize=5,
        useHarrisDetector=False,
    )
    if corner_points is None:
        return keypoints, descriptors

    forced_keypoints = [
        cv2.KeyPoint(float(point[0][0]), float(point[0][1]), 16.0)
        for point in corner_points
    ]
    computed_keypoints, computed_descriptors = detector.compute(image_array, forced_keypoints)
    if computed_descriptors is None:
        return keypoints, descriptors
    return computed_keypoints, computed_descriptors


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
