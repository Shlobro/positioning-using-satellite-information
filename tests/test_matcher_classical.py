from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from satellite_drone_localization.eval.matcher_classical import ClassicalFeatureMatcher


def write_synthetic_map_image(path: Path) -> None:
    image = Image.new("L", (240, 220), color=96)
    draw = ImageDraw.Draw(image)
    draw.rectangle((18, 20, 84, 74), fill=186)
    draw.rectangle((110, 22, 174, 88), fill=224)
    draw.rectangle((26, 104, 84, 176), fill=148)
    draw.rectangle((116, 114, 182, 176), fill=204)
    draw.line((98, 0, 98, 220), fill=28, width=6)
    draw.line((0, 150, 240, 150), fill=36, width=8)
    draw.ellipse((188, 24, 228, 64), fill=172)
    draw.polygon([(196, 112), (220, 132), (208, 176), (184, 160)], fill=214)
    draw.line((150, 184, 232, 202), fill=20, width=5)
    image.save(path)


def write_frame_from_map(
    *,
    map_path: Path,
    frame_path: Path,
    center_x: int,
    center_y: int,
    width_px: int = 78,
    height_px: int = 46,
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


def test_classical_feature_matcher_matches_synthetic_frame_on_map(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=149, center_y=140)

    matcher = ClassicalFeatureMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=78.0,
        ground_height_px=46.0,
        crop_min_x=80.0,
        crop_min_y=92.0,
        crop_max_x=212.0,
        crop_max_y=188.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is True
    assert decision.estimate_source == "matched_classical_feature"
    assert decision.match_score is not None
    assert decision.match_score > 0.55
    assert abs(decision.estimated_pixel_x - 149.0) <= 4.0
    assert abs(decision.estimated_pixel_y - 140.0) <= 4.0


def test_classical_feature_matcher_falls_back_for_low_texture(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    Image.new("L", (240, 220), color=128).save(map_path)
    Image.new("L", (192, 108), color=128).save(frame_path)

    matcher = ClassicalFeatureMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=78.0,
        ground_height_px=46.0,
        crop_min_x=80.0,
        crop_min_y=92.0,
        crop_max_x=212.0,
        crop_max_y=188.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_classical_low_texture"


def test_classical_feature_matcher_falls_back_for_off_map_crop(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=149, center_y=140)

    matcher = ClassicalFeatureMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=78.0,
        ground_height_px=46.0,
        crop_min_x=80.0,
        crop_min_y=92.0,
        crop_max_x=212.0,
        crop_max_y=188.0,
        crop_inside_image=False,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_classical_crop_outside_map"
