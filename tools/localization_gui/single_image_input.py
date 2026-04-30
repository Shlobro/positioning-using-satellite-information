"""Single-image input for the localization GUI.

A single drone image is only valid if a sidecar `<image>_packet.json` lives next
to it. The sidecar is a `dev-packet-v1` shaped document with one optional
`session_start` packet plus exactly one `frame` packet, so single-image runs
share the same metadata contract as full replay sequences.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

# Re-use the main package validators so the sidecar is treated identically to a
# replay file. tools/ scripts are launched directly so we extend sys.path inside
# localization_gui.py before importing this module.
from satellite_drone_localization.packet_replay import ReplaySession, load_replay_session


SIDECAR_SUFFIX = "_packet.json"


@dataclass(frozen=True)
class SingleImagePacket:
    """One image plus its dev-packet-v1 sidecar resolved into a replay session."""

    image_path: Path
    sidecar_path: Path
    session: ReplaySession


def sidecar_path_for_image(image_path: Path) -> Path:
    """Return the expected sidecar path next to the given image."""
    return image_path.with_name(image_path.stem + SIDECAR_SUFFIX)


def load_single_image_packet(image_path: Path) -> SingleImagePacket:
    """Load and validate a single-image packet sidecar.

    Raises FileNotFoundError when the sidecar is missing.
    Raises ValueError when the sidecar is not a valid one-frame replay.
    """
    image_path = Path(image_path).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    sidecar = sidecar_path_for_image(image_path)
    if not sidecar.is_file():
        raise FileNotFoundError(
            f"single-image input requires a dev-packet-v1 sidecar at {sidecar}"
        )

    session = load_replay_session(sidecar)
    if len(session.frames) != 1:
        raise ValueError(
            f"single-image sidecar must contain exactly one frame packet, found {len(session.frames)}"
        )

    frame = session.frames[0]
    if frame.image_path.name != image_path.name:
        raise ValueError(
            f"sidecar frame image_name '{frame.image_name}' does not match image filename '{image_path.name}'"
        )

    return SingleImagePacket(
        image_path=image_path,
        sidecar_path=sidecar,
        session=session,
    )


def write_single_image_packet_template(
    image_path: Path,
    *,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
    heading_deg: float,
    camera_hfov_deg: float,
    camera_vfov_deg: float | None,
    frame_width_px: int | None,
    frame_height_px: int | None,
    timestamp_utc: str,
    altitude_reference: str = "agl",
    prior_search_radius_m: float | None = None,
) -> Path:
    """Write a one-frame `dev-packet-v1` sidecar for a single drone image.

    Returns the sidecar path. Provided as a small authoring helper so the GUI's
    "create packet for this image" workflow stays in one place. Numeric inputs
    are written verbatim; downstream loaders enforce range validation.
    """
    image_path = Path(image_path).resolve()
    sidecar = sidecar_path_for_image(image_path)

    session_start = {
        "packet_type": "session_start",
        "schema_version": "dev-packet-v1",
        "altitude_reference": altitude_reference,
        "camera_hfov_deg": camera_hfov_deg,
    }
    if camera_vfov_deg is not None:
        session_start["camera_vfov_deg"] = camera_vfov_deg
    if prior_search_radius_m is not None:
        session_start["prior_search_radius_m"] = prior_search_radius_m

    frame: dict[str, object] = {
        "packet_type": "frame",
        "timestamp_utc": timestamp_utc,
        "image_name": image_path.name,
        "latitude_deg": latitude_deg,
        "longitude_deg": longitude_deg,
        "altitude_m": altitude_m,
        "altitude_reference": altitude_reference,
        "heading_deg": heading_deg,
        "camera_hfov_deg": camera_hfov_deg,
    }
    if camera_vfov_deg is not None:
        frame["camera_vfov_deg"] = camera_vfov_deg
    if frame_width_px is not None:
        frame["frame_width_px"] = frame_width_px
    if frame_height_px is not None:
        frame["frame_height_px"] = frame_height_px
    if prior_search_radius_m is not None:
        frame["prior_search_radius_m"] = prior_search_radius_m

    sidecar.write_text(
        json.dumps(session_start) + "\n" + json.dumps(frame) + "\n",
        encoding="utf-8",
    )
    return sidecar
