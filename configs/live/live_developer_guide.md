# Live Configs Developer Guide

This folder stores committed example payloads for the minimal Phase 1 live receiver stub.

Current file:

- `dev_live_packet_v1.json` is the example one-packet live payload for the receiver stub.

Guidelines:

- Keep live example payloads as single JSON objects, not JSON-lines files.
- Use `packet_type: "live_frame"` for the transport wrapper while keeping the remaining field names aligned with `dev-packet-v1`.
- Include enough metadata to exercise geometry and crop planning from a single packet.
