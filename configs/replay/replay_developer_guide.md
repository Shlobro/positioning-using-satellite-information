# Replay Configs Developer Guide

This folder stores committed examples for the Phase 1 replay packet format.

Current file:

- `dev_packets_v1.jsonl` shows the append-friendly JSON-lines structure that field recording code should emit.

Guidelines:

- Keep the first packet as `session_start` when camera defaults are shared across the whole capture.
- Keep one `frame` packet per image in chronological order.
- Prefer explicit units in field names such as `_deg` and `_m`.
- If altitude is measured above the local ground under the drone, set `altitude_reference` to `agl`.
- If `camera_vfov_deg` is not available, include `frame_width_px` and `frame_height_px` on frame packets so the geometry pipeline can infer vertical FOV deterministically.
- If you have a navigation prior, include `prior_latitude_deg` and `prior_longitude_deg` together on the frame packet.
- If search uncertainty is stable across a session, put `prior_search_radius_m` on the `session_start` packet and override it per frame only when needed.
- Keep the example replay file realistic enough that the combined replay pipeline can surface meaningful geometry, crop, and sensitivity artifacts from it.
