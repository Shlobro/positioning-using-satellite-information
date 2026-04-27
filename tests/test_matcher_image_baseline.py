from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from satellite_drone_localization.eval.matcher_image_baseline import ImageBaselineMatcher


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


def test_image_baseline_matcher_matches_synthetic_frame_on_map(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=112, center_y=100)

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=60.0,
        ground_height_px=34.0,
        crop_min_x=60.0,
        crop_min_y=70.0,
        crop_max_x=160.0,
        crop_max_y=130.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is True
    assert decision.estimate_source == "matched_image_baseline"
    assert decision.match_score is not None
    assert decision.match_score > 0.70
    assert abs(decision.estimated_pixel_x - 112.0) <= 6.0
    assert abs(decision.estimated_pixel_y - 100.0) <= 6.0


def test_image_baseline_matcher_refines_beyond_coarse_stride(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(
        map_path=map_path,
        frame_path=frame_path,
        center_x=111,
        center_y=101,
        width_px=78,
        height_px=46,
    )

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=78.0,
        ground_height_px=46.0,
        crop_min_x=40.0,
        crop_min_y=55.0,
        crop_max_x=175.0,
        crop_max_y=150.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is True
    assert decision.estimate_source == "matched_image_baseline"
    assert abs(decision.estimated_pixel_x - 111.0) <= 2.0
    assert abs(decision.estimated_pixel_y - 101.0) <= 2.0


def test_image_baseline_matcher_falls_back_for_off_map_crop(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(map_path=map_path, frame_path=frame_path, center_x=112, center_y=100)

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=60.0,
        ground_height_px=34.0,
        crop_min_x=60.0,
        crop_min_y=70.0,
        crop_max_x=160.0,
        crop_max_y=130.0,
        crop_inside_image=False,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_image_crop_outside_map"


def test_image_baseline_matcher_rejects_low_texture_match(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    Image.new("L", (200, 200), color=128).save(map_path)
    Image.new("L", (192, 108), color=128).save(frame_path)

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=60.0,
        ground_height_px=34.0,
        crop_min_x=60.0,
        crop_min_y=70.0,
        crop_max_x=160.0,
        crop_max_y=130.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_image_low_texture"
    assert decision.match_score is None
    assert decision.runner_up_match_score is None


def test_image_baseline_matcher_rejects_ambiguous_repeated_pattern(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    image = Image.new("L", (220, 160), color=64)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 80, 90), fill=220)
    draw.rectangle((120, 30, 180, 90), fill=220)
    draw.line((0, 120, 220, 120), fill=20, width=6)
    image.save(map_path)
    write_frame_from_map(
        map_path=map_path,
        frame_path=frame_path,
        center_x=50,
        center_y=60,
        width_px=60,
        height_px=34,
    )

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=60.0,
        ground_height_px=34.0,
        crop_min_x=10.0,
        crop_min_y=20.0,
        crop_max_x=190.0,
        crop_max_y=110.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is False
    assert decision.estimate_source == "fallback_image_ambiguous_match"
    assert decision.match_score is not None
    assert decision.runner_up_match_score is not None


def test_image_baseline_matcher_accepts_local_near_tie_around_true_peak(tmp_path: Path) -> None:
    map_path = tmp_path / "map.png"
    frame_path = tmp_path / "frame.png"
    write_synthetic_map_image(map_path)
    write_frame_from_map(
        map_path=map_path,
        frame_path=frame_path,
        center_x=112,
        center_y=100,
        width_px=74,
        height_px=42,
    )

    matcher = ImageBaselineMatcher(map_path)
    decision = matcher.match_frame(
        frame_image_path=frame_path,
        normalization_rotation_deg=0.0,
        ground_width_px=74.0,
        ground_height_px=42.0,
        crop_min_x=45.0,
        crop_min_y=58.0,
        crop_max_x=176.0,
        crop_max_y=146.0,
        crop_inside_image=True,
        measurement_update_radius_m=5.0,
        georeference_max_residual_m=0.25,
    )

    assert decision.accepted is True
    assert decision.estimate_source == "matched_image_baseline"
    assert abs(decision.estimated_pixel_x - 112.0) <= 3.0
    assert abs(decision.estimated_pixel_y - 100.0) <= 3.0
