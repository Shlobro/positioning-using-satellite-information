from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

import pytest

from satellite_drone_localization.packet_replay import load_replay_session
from satellite_drone_localization.replay_cli import main as replay_main


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def write_jsonl(path: Path, packets: list[dict[str, object]]) -> None:
    lines = [json.dumps(packet) for packet in packets]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_replay_session_applies_session_defaults() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "session_start",
                "schema_version": "dev-packet-v1",
                "session_id": "DEV-SESSION-001",
                "frame_directory": "frames",
                "altitude_reference": "agl",
                "camera_hfov_deg": 84.0,
            },
            {
                "packet_type": "frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "lat": 32.0853,
                "lon": 34.7818,
                "altitude": 52.4,
                "heading": 91.2,
            },
        ]
        write_jsonl(replay_path, packets)

        session = load_replay_session(replay_path)

        assert session.schema_version == "dev-packet-v1"
        assert session.session_id == "DEV-SESSION-001"
        assert len(session.frames) == 1
        assert session.frames[0].camera_hfov_deg == pytest.approx(84.0)
        assert session.frames[0].altitude_reference == "agl"
        assert session.frames[0].prior_search_radius_m is None
        assert session.frames[0].image_path == (repo_root / "frames" / "frame_0001.jpg").resolve()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_load_replay_session_allows_frame_fov_override() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "session_start",
                "schema_version": "dev-packet-v1",
                "session_id": "DEV-SESSION-001",
                "camera_hfov_deg": 84.0,
            },
            {
                "packet_type": "frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "latitude_deg": 32.0853,
                "longitude_deg": 34.7818,
                "altitude_m": 52.4,
                "heading_deg": 91.2,
                "camera_hfov_deg": 82.0,
            },
        ]
        write_jsonl(replay_path, packets)

        session = load_replay_session(replay_path)

        assert session.frames[0].camera_hfov_deg == pytest.approx(82.0)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_load_replay_session_applies_prior_defaults_and_overrides() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "session_start",
                "schema_version": "dev-packet-v1",
                "camera_hfov_deg": 84.0,
                "prior_search_radius_m": 20.0,
            },
            {
                "packet_type": "frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "latitude_deg": 32.0853,
                "longitude_deg": 34.7818,
                "prior_latitude_deg": 32.0852,
                "prior_longitude_deg": 34.7817,
                "prior_search_radius_m": 12.5,
                "altitude_m": 52.4,
                "heading_deg": 91.2,
            },
        ]
        write_jsonl(replay_path, packets)

        session = load_replay_session(replay_path)

        assert session.defaults.prior_search_radius_m == pytest.approx(20.0)
        assert session.frames[0].prior_latitude_deg == pytest.approx(32.0852)
        assert session.frames[0].prior_longitude_deg == pytest.approx(34.7817)
        assert session.frames[0].prior_search_radius_m == pytest.approx(12.5)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_load_replay_session_requires_fov() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "frame",
                "timestamp": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "lat": 32.0853,
                "lon": 34.7818,
                "altitude": 52.4,
                "heading": 91.2,
            },
        ]
        write_jsonl(replay_path, packets)

        with pytest.raises(ValueError, match="requires camera_hfov_deg or session default fov"):
            load_replay_session(replay_path)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_load_replay_session_requires_full_prior_pair() -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "session_start",
                "schema_version": "dev-packet-v1",
                "camera_hfov_deg": 84.0,
            },
            {
                "packet_type": "frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "latitude_deg": 32.0853,
                "longitude_deg": 34.7818,
                "prior_latitude_deg": 32.0852,
                "altitude_m": 52.4,
                "heading_deg": 91.2,
            },
        ]
        write_jsonl(replay_path, packets)

        with pytest.raises(ValueError, match="prior_latitude_deg and prior_longitude_deg must be provided together"):
            load_replay_session(replay_path)
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_replay_cli_prints_summary(capsys) -> None:
    repo_root = make_repo_root()
    try:
        replay_path = repo_root / "capture.jsonl"
        packets = [
            {
                "packet_type": "session_start",
                "schema_version": "dev-packet-v1",
                "session_id": "DEV-SESSION-001",
                "frame_directory": "frames",
                "camera_hfov_deg": 84.0,
            },
            {
                "packet_type": "frame",
                "timestamp_utc": "2026-04-20T10:15:30Z",
                "image_name": "frame_0001.jpg",
                "latitude_deg": 32.0853,
                "longitude_deg": 34.7818,
                "altitude_m": 52.4,
                "heading_deg": 91.2,
            },
        ]
        write_jsonl(replay_path, packets)

        exit_code = replay_main(["--replay-file", str(replay_path)])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "Loaded 1 frame packets" in captured.out
        assert "Schema: dev-packet-v1" in captured.out
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
