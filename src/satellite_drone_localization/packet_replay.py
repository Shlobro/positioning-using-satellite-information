"""Replay loading for Phase 1 packet streams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from .packet_schema import (
    DEFAULT_ALTITUDE_REFERENCE,
    ReplayFramePacket,
    SCHEMA_VERSION,
    SessionDefaults,
    parse_frame_packet,
    parse_session_defaults,
)


@dataclass(frozen=True)
class ReplaySession:
    """A replay file with normalized packet metadata."""

    schema_version: str
    source_path: Path
    session_id: str | None
    defaults: SessionDefaults
    frames: list[ReplayFramePacket]


def load_replay_session(replay_path: Path) -> ReplaySession:
    """Load a JSON-lines replay file and validate all packets."""
    resolved_path = replay_path.resolve()
    lines = resolved_path.read_text(encoding="utf-8").splitlines()
    entries: list[tuple[int, dict[str, object]]] = []

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{resolved_path}:{line_number} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{resolved_path}:{line_number} must be a JSON object")
        entries.append((line_number, payload))

    if not entries:
        raise ValueError(f"{resolved_path} does not contain any packets")

    defaults = SessionDefaults(
        session_id=None,
        frame_directory=None,
        altitude_reference=DEFAULT_ALTITUDE_REFERENCE,
        camera_hfov_deg=None,
        camera_vfov_deg=None,
        prior_search_radius_m=None,
    )
    frames: list[ReplayFramePacket] = []
    session_id: str | None = None
    start_index = 0

    first_line_number, first_payload = entries[0]
    packet_type = first_payload.get("packet_type")
    if packet_type == "session_start":
        try:
            defaults = parse_session_defaults(first_payload, resolved_path)
        except ValueError as exc:
            raise ValueError(f"{resolved_path}:{first_line_number} {exc}") from exc
        session_id = defaults.session_id
        start_index = 1

    for line_number, payload in entries[start_index:]:
        try:
            frames.append(parse_frame_packet(payload, defaults, resolved_path, line_number))
        except ValueError as exc:
            raise ValueError(f"{resolved_path}:{line_number} {exc}") from exc

    if not frames:
        raise ValueError(f"{resolved_path} does not contain any frame packets")

    return ReplaySession(
        schema_version=SCHEMA_VERSION,
        source_path=resolved_path,
        session_id=session_id,
        defaults=defaults,
        frames=frames,
    )
