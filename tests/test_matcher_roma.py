from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image, ImageDraw

from satellite_drone_localization.eval.matcher_roma import RoMaRegressionMatcher


class FakeRoMaBackend:
    def __init__(self, center_x: float, center_y: float) -> None:
        self.center_x = center_x
        self.center_y = center_y

    def match(self, image_a, image_b, *args, device=None):
        return "matches", "certainty"

    def sample(self, matches, certainty, num=5000):
        coords = np.zeros((512, 4), dtype=np.float32)
        certainty_values = np.full((512,), 0.92, dtype=np.float32)
        return coords, certainty_values

    def to_pixel_coordinates(self, coords, height_a, width_a, height_b=None, width_b=None):
        frame_points: list[list[float]] = []
        crop_points: list[list[float]] = []
        scale_x = 60.0 / width_a
        scale_y = 34.0 / height_a
        offset_x = self.center_x - 30.0
        offset_y = self.center_y - 17.0
        for index in range(512):
            local_x = float((index * 17) % max(1, width_a - 1))
            local_y = float((index * 11) % max(1, height_a - 1))
            frame_points.append([local_x, local_y])
            crop_points.append([(local_x * scale_x) + offset_x, (local_y * scale_y) + offset_y])
        return np.asarray(frame_points, dtype=np.float32), np.asarray(crop_points, dtype=np.float32)


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


def write_frame_from_map(
    *,
    map_path: Path,
    frame_path: Path,
    center_x: int,
    center_y: int,
    width_px: int = 60,
    height_px: int = 34,
) -> None:
    with Image.open(map_path) as image:
        patch = image.crop(
            (
                center_x - (width_px // 2),
                center_y - (height_px // 2),
                center_x + (width_px // 2),
                center_y + (height_px // 2),
            )
        )
        frame = patch.resize((192, 108), resample=Image.Resampling.BILINEAR)
        frame.save(frame_path)


def test_roma_matcher_recovers_synthetic_center_from_fake_backend() -> None:
    repo_root = make_repo_root()
    try:
        map_path = repo_root / "map.png"
        frame_path = repo_root / "frame.png"
        write_synthetic_map_image(map_path)
        write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=112, center_y=100)
        matcher = RoMaRegressionMatcher(
            map_path,
            backend=FakeRoMaBackend(center_x=112.0, center_y=100.0),
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
        assert decision.estimate_source == "matched_roma"
        assert abs(decision.estimated_pixel_x - 112.0) < 3.0
        assert abs(decision.estimated_pixel_y - 100.0) < 3.0
        assert decision.match_score is not None
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_roma_matcher_rejects_low_texture_frame() -> None:
    repo_root = make_repo_root()
    try:
        map_path = repo_root / "map.png"
        frame_path = repo_root / "frame.png"
        Image.new("L", (200, 200), color=96).save(map_path)
        Image.new("L", (192, 108), color=128).save(frame_path)
        matcher = RoMaRegressionMatcher(
            map_path,
            backend=FakeRoMaBackend(center_x=100.0, center_y=100.0),
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
        assert decision.estimate_source == "fallback_roma_low_texture"
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
