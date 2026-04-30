from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image, ImageDraw

from satellite_drone_localization.eval.neural_matchers.matcher_loftr import LoFTRRegressionMatcher


class FakeLoFTRBackend:
    def __init__(
        self,
        center_x: float,
        center_y: float,
        *,
        scale: float = 1.0,
        coverage_fraction: float = 1.0,
        confidence: float = 0.82,
    ) -> None:
        self.center_x = center_x
        self.center_y = center_y
        self.scale = scale
        self.coverage_fraction = coverage_fraction
        self.confidence = confidence

    def match_keypoints(self, image_a, image_b, *, device: str):
        width_a, height_a = image_a.size
        frame_points: list[list[float]] = []
        crop_points: list[list[float]] = []
        span_x = max(2, int((width_a - 1) * self.coverage_fraction))
        span_y = max(2, int((height_a - 1) * self.coverage_fraction))
        start_x = (width_a - span_x) / 2.0
        start_y = (height_a - span_y) / 2.0
        offset_x = self.center_x - ((width_a / 2.0) * self.scale)
        offset_y = self.center_y - ((height_a / 2.0) * self.scale)
        for index in range(128):
            local_x = start_x + float((index * 17) % span_x)
            local_y = start_y + float((index * 11) % span_y)
            frame_points.append([local_x, local_y])
            crop_points.append([(local_x * self.scale) + offset_x, (local_y * self.scale) + offset_y])
        return (
            np.asarray(frame_points, dtype=np.float32),
            np.asarray(crop_points, dtype=np.float32),
            np.full((128,), self.confidence, dtype=np.float32),
        )


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_synthetic_map_image(path: Path) -> None:
    image = Image.new("L", (200, 200), color=96)
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 20, 84, 74), fill=186)
    draw.rectangle((110, 22, 174, 88), fill=224)
    draw.rectangle((26, 104, 84, 176), fill=148)
    draw.rectangle((116, 114, 182, 176), fill=204)
    draw.line((98, 0, 98, 200), fill=28, width=6)
    draw.line((0, 150, 200, 150), fill=36, width=8)
    image.save(path)


def write_frame_from_map(*, map_path: Path, frame_path: Path, center_x: int, center_y: int) -> None:
    with Image.open(map_path) as image:
        patch = image.crop((center_x - 30, center_y - 17, center_x + 30, center_y + 17))
        frame = patch.resize((192, 108), resample=Image.Resampling.BILINEAR)
        frame.save(frame_path)


def test_loftr_matcher_recovers_synthetic_center_from_fake_backend() -> None:
    repo_root = make_repo_root()
    try:
        map_path = repo_root / "map.png"
        frame_path = repo_root / "frame.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=112, center_y=100)
        matcher = LoFTRRegressionMatcher(
            map_path,
            backend=FakeLoFTRBackend(center_x=112.0, center_y=100.0),
            device="cpu",
        )

        decision = matcher.match_frame(
            frame_image_path=frame_path,
            normalization_rotation_deg=0.0,
            ground_width_px=60.0,
            ground_height_px=34.0,
            crop_min_x=0.0,
            crop_min_y=0.0,
            crop_max_x=200.0,
            crop_max_y=200.0,
            crop_inside_image=True,
            measurement_update_radius_m=5.0,
            georeference_max_residual_m=1.0,
        )

        assert decision.accepted is True
        assert decision.estimate_source == "matched_loftr"
        assert abs(decision.estimated_pixel_x - 112.0) < 3.0
        assert abs(decision.estimated_pixel_y - 100.0) < 3.0
        assert decision.match_score is not None
        assert decision.diagnostics is not None
        assert decision.diagnostics["match_count"] == 128
        assert decision.diagnostics["inlier_count"] >= 48
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_loftr_matcher_rejects_low_confidence_backend() -> None:
    repo_root = make_repo_root()
    try:
        map_path = repo_root / "map.png"
        frame_path = repo_root / "frame.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=112, center_y=100)
        matcher = LoFTRRegressionMatcher(
            map_path,
            backend=FakeLoFTRBackend(center_x=112.0, center_y=100.0, confidence=0.20),
            device="cpu",
        )

        decision = matcher.match_frame(
            frame_image_path=frame_path,
            normalization_rotation_deg=0.0,
            ground_width_px=60.0,
            ground_height_px=34.0,
            crop_min_x=0.0,
            crop_min_y=0.0,
            crop_max_x=200.0,
            crop_max_y=200.0,
            crop_inside_image=True,
            measurement_update_radius_m=5.0,
            georeference_max_residual_m=1.0,
        )

        assert decision.accepted is False
        assert decision.estimate_source == "fallback_loftr_low_confidence"
        assert decision.diagnostics is not None
        assert decision.diagnostics["mean_inlier_confidence"] < 0.35
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
