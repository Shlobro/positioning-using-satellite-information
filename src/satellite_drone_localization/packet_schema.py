"""Phase 1 packet schema definitions and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCHEMA_VERSION = "dev-packet-v1"
DEFAULT_ALTITUDE_REFERENCE = "agl"
ALLOWED_ALTITUDE_REFERENCES = {"agl", "relative_takeoff", "unknown"}


@dataclass(frozen=True)
class SessionDefaults:
    """Shared packet defaults declared once per replay file."""

    session_id: str | None
    frame_directory: Path | None
    altitude_reference: str
    camera_hfov_deg: float | None
    camera_vfov_deg: float | None
    prior_search_radius_m: float | None


@dataclass(frozen=True)
class ReplayFramePacket:
    """Validated replay packet with resolved defaults."""

    timestamp_utc: str
    image_name: str
    image_path: Path
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    altitude_reference: str
    heading_deg: float
    camera_hfov_deg: float
    camera_vfov_deg: float | None
    frame_width_px: int | None
    frame_height_px: int | None
    prior_latitude_deg: float | None
    prior_longitude_deg: float | None
    prior_search_radius_m: float | None
    source_line_number: int


def parse_session_defaults(payload: dict[str, object], replay_path: Path) -> SessionDefaults:
    """Validate and normalize an optional session header packet."""
    packet_type = _require_string(payload, "packet_type")
    if packet_type != "session_start":
        raise ValueError("session header must have packet_type='session_start'")

    schema_version = _require_string(payload, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version '{schema_version}'")

    frame_directory_value = _optional_string(payload, "frame_directory")
    frame_directory = None
    if frame_directory_value:
        candidate = Path(frame_directory_value)
        frame_directory = candidate if candidate.is_absolute() else (replay_path.parent / candidate).resolve()

    altitude_reference = _normalize_altitude_reference(
        _optional_string(payload, "altitude_reference") or DEFAULT_ALTITUDE_REFERENCE
    )
    return SessionDefaults(
        session_id=_optional_string(payload, "session_id"),
        frame_directory=frame_directory,
        altitude_reference=altitude_reference,
        camera_hfov_deg=_optional_fov_deg(payload),
        camera_vfov_deg=_optional_float(payload, ("camera_vfov_deg",)),
        prior_search_radius_m=_optional_positive_float(payload, ("prior_search_radius_m",)),
    )


def parse_frame_packet(
    payload: dict[str, object],
    defaults: SessionDefaults,
    replay_path: Path,
    line_number: int,
) -> ReplayFramePacket:
    """Validate and normalize a single frame packet."""
    packet_type = _require_string(payload, "packet_type")
    if packet_type != "frame":
        raise ValueError("frame packets must have packet_type='frame'")

    schema_version = _optional_string(payload, "schema_version")
    if schema_version and schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version '{schema_version}'")

    timestamp_utc = _require_string(payload, "timestamp_utc", "timestamp")
    _validate_timestamp(timestamp_utc)

    image_name = _require_string(payload, "image_name")
    image_path = _resolve_image_path(
        image_name=image_name,
        frame_directory=defaults.frame_directory,
        replay_path=replay_path,
    )
    latitude_deg = _require_float(payload, ("latitude_deg", "lat"))
    longitude_deg = _require_float(payload, ("longitude_deg", "lon"))
    altitude_m = _require_float(payload, ("altitude_m", "altitude"))
    heading_deg = _require_float(payload, ("heading_deg", "heading"))
    altitude_reference = _normalize_altitude_reference(
        _optional_string(payload, "altitude_reference") or defaults.altitude_reference
    )

    camera_hfov_deg = _optional_fov_deg(payload)
    if camera_hfov_deg is None:
        camera_hfov_deg = defaults.camera_hfov_deg
    if camera_hfov_deg is None:
        raise ValueError("frame packet requires camera_hfov_deg or session default fov")

    camera_vfov_deg = _optional_float(payload, ("camera_vfov_deg",))
    if camera_vfov_deg is None:
        camera_vfov_deg = defaults.camera_vfov_deg

    _validate_latitude(latitude_deg)
    _validate_longitude(longitude_deg)
    _validate_positive("altitude_m", altitude_m)
    _validate_heading(heading_deg)
    _validate_fov("camera_hfov_deg", camera_hfov_deg)
    if camera_vfov_deg is not None:
        _validate_fov("camera_vfov_deg", camera_vfov_deg)

    prior_latitude_deg = _optional_float(payload, ("prior_latitude_deg",))
    if prior_latitude_deg is not None:
        _validate_latitude(prior_latitude_deg)

    prior_longitude_deg = _optional_float(payload, ("prior_longitude_deg",))
    if prior_longitude_deg is not None:
        _validate_longitude(prior_longitude_deg)

    if (prior_latitude_deg is None) != (prior_longitude_deg is None):
        raise ValueError("prior_latitude_deg and prior_longitude_deg must be provided together")

    prior_search_radius_m = _optional_positive_float(payload, ("prior_search_radius_m",))
    if prior_search_radius_m is None:
        prior_search_radius_m = defaults.prior_search_radius_m

    return ReplayFramePacket(
        timestamp_utc=timestamp_utc,
        image_name=image_name,
        image_path=image_path,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=altitude_m,
        altitude_reference=altitude_reference,
        heading_deg=heading_deg,
        camera_hfov_deg=camera_hfov_deg,
        camera_vfov_deg=camera_vfov_deg,
        frame_width_px=_optional_int(payload, ("frame_width_px",)),
        frame_height_px=_optional_int(payload, ("frame_height_px",)),
        prior_latitude_deg=prior_latitude_deg,
        prior_longitude_deg=prior_longitude_deg,
        prior_search_radius_m=prior_search_radius_m,
        source_line_number=line_number,
    )


def _resolve_image_path(image_name: str, frame_directory: Path | None, replay_path: Path) -> Path:
    candidate = Path(image_name)
    if candidate.is_absolute():
        return candidate
    if frame_directory is not None:
        return (frame_directory / candidate).resolve()
    return (replay_path.parent / candidate).resolve()


def _validate_timestamp(value: str) -> None:
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp '{value}'") from exc


def _validate_latitude(value: float) -> None:
    if not -90.0 <= value <= 90.0:
        raise ValueError(f"latitude_deg out of range: {value}")


def _validate_longitude(value: float) -> None:
    if not -180.0 <= value <= 180.0:
        raise ValueError(f"longitude_deg out of range: {value}")


def _validate_positive(field_name: str, value: float) -> None:
    if value <= 0.0:
        raise ValueError(f"{field_name} must be positive")


def _validate_heading(value: float) -> None:
    if not 0.0 <= value < 360.0:
        raise ValueError(f"heading_deg out of range: {value}")


def _validate_fov(field_name: str, value: float) -> None:
    if not 0.0 < value < 180.0:
        raise ValueError(f"{field_name} out of range: {value}")


def _normalize_altitude_reference(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_ALTITUDE_REFERENCES:
        raise ValueError(
            f"altitude_reference must be one of {sorted(ALLOWED_ALTITUDE_REFERENCES)}, got '{value}'"
        )
    return normalized


def _optional_string(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        if key in payload:
            value = payload[key]
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
            value = value.strip()
            if not value:
                raise ValueError(f"{key} must not be empty")
            return value
    return None


def _require_string(payload: dict[str, object], *keys: str) -> str:
    value = _optional_string(payload, *keys)
    if value is None:
        raise ValueError(f"missing required field: {keys[0]}")
    return value


def _optional_float(payload: dict[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in payload:
            value = payload[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{key} must be numeric")
            return float(value)
    return None


def _require_float(payload: dict[str, object], keys: tuple[str, ...]) -> float:
    value = _optional_float(payload, keys)
    if value is None:
        raise ValueError(f"missing required field: {keys[0]}")
    return value


def _optional_int(payload: dict[str, object], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in payload:
            value = payload[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{key} must be an integer")
            if value <= 0:
                raise ValueError(f"{key} must be positive")
            return value
    return None


def _optional_fov_deg(payload: dict[str, object]) -> float | None:
    return _optional_float(payload, ("camera_hfov_deg", "fov_deg", "fov"))


def _optional_positive_float(payload: dict[str, object], keys: tuple[str, ...]) -> float | None:
    value = _optional_float(payload, keys)
    if value is not None:
        _validate_positive(keys[0], value)
    return value
