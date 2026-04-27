"""Minimal live receiver stub built on top of the replay packet contract."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..crop import build_replay_crop_plan
from ..geometry import build_replay_geometry_report
from ..packet_replay import ReplaySession
from ..packet_schema import SCHEMA_VERSION, SessionDefaults, parse_frame_packet


@dataclass(frozen=True)
class LiveReceiverConfig:
    """Session defaults applied to incoming live packets."""

    session_id: str = "LIVE-SESSION-001"
    source_path: Path = Path("live_dev_packet.json")
    frame_directory: Path | None = None
    altitude_reference: str = "agl"
    camera_hfov_deg: float | None = None
    camera_vfov_deg: float | None = None
    prior_search_radius_m: float | None = None


@dataclass(frozen=True)
class LivePacketReceipt:
    """Parsed and interpreted result for a single live packet."""

    session_id: str
    schema_version: str
    status: str
    image_name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    heading_deg: float
    ground_width_m: float
    ground_height_m: float
    crop_side_m: float
    normalized_rotation_deg: float
    contains_target: bool


class LivePacketReceiver:
    """Validate one live packet and route it through the single-frame pipeline."""

    def __init__(self, config: LiveReceiverConfig) -> None:
        self._config = config

    def receive_packet(self, raw_message: str | dict[str, object]) -> LivePacketReceipt:
        """Parse one dev-format live packet and return interpreted metadata."""
        payload = self._load_payload(raw_message)
        packet_type = payload.get("packet_type")
        if packet_type != "live_frame":
            raise ValueError("live packet must have packet_type='live_frame'")

        normalized_payload = dict(payload)
        normalized_payload["packet_type"] = "frame"
        defaults = SessionDefaults(
            session_id=self._config.session_id,
            frame_directory=self._resolve_frame_directory(),
            altitude_reference=self._config.altitude_reference,
            camera_hfov_deg=self._config.camera_hfov_deg,
            camera_vfov_deg=self._config.camera_vfov_deg,
            prior_search_radius_m=self._config.prior_search_radius_m,
        )
        source_path = self._config.source_path.resolve()
        frame = parse_frame_packet(
            payload=normalized_payload,
            defaults=defaults,
            replay_path=source_path,
            line_number=1,
        )
        session = ReplaySession(
            schema_version=SCHEMA_VERSION,
            source_path=source_path,
            session_id=self._config.session_id,
            defaults=defaults,
            frames=[frame],
        )
        geometry = build_replay_geometry_report(session).frames[0]
        crop = build_replay_crop_plan(session).frames[0]
        return LivePacketReceipt(
            session_id=self._config.session_id,
            schema_version=SCHEMA_VERSION,
            status="ok",
            image_name=frame.image_name,
            latitude_deg=frame.latitude_deg,
            longitude_deg=frame.longitude_deg,
            altitude_m=frame.altitude_m,
            heading_deg=frame.heading_deg,
            ground_width_m=geometry.ground_width_m,
            ground_height_m=geometry.ground_height_m,
            crop_side_m=crop.crop_side_m,
            normalized_rotation_deg=geometry.normalization_rotation_deg,
            contains_target=crop.contains_target,
        )

    @staticmethod
    def _load_payload(raw_message: str | dict[str, object]) -> dict[str, object]:
        if isinstance(raw_message, dict):
            return raw_message
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            raise ValueError("live packet must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("live packet must decode to a JSON object")
        return payload

    def _resolve_frame_directory(self) -> Path | None:
        if self._config.frame_directory is None:
            return None
        return self._config.frame_directory.resolve()
