# Live Developer Guide

This folder contains the minimal Phase 1 live receiver stub.

Current scope:

- `receiver.py` accepts one `live_frame` JSON payload, resolves session defaults, and routes it through the existing single-frame geometry and crop logic.

Guidelines:

- Keep the live transport contract as close as possible to `dev-packet-v1` so replay and live parsing do not diverge unnecessarily.
- Keep this layer thin: transport parsing belongs here, while geometry and crop logic should stay in their existing modules.
- Prefer returning parsed metadata and deterministic status fields before adding sockets, servers, or concurrency.
