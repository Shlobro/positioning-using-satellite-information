# DEV-SESSION-20260427T112451Z Developer Guide

This folder stores the 2026-04-27 local flight session currently used for Phase 1
real-data inspection.

Current contents:

- `dev_packets_v1.jsonl` is the replay telemetry stream for the whole flight.
- `frames/` contains extracted drone frames referenced by the replay file.
- `Frame from satellite/` contains the north-up GIS reference image plus its
  calibration sidecar.

Known caveats:

- The replay session mixes `agl` and `relative_takeoff` altitude references, so
  downstream geometry should treat altitude semantics cautiously.
- The replay packets currently expose full GPS truth and are suitable for offline
  evaluation, but future sequence experiments should hide post-start GPS from the
  runtime path and use it only for error analysis.

Guidelines:

- Keep session-specific supporting assets inside this folder rather than
  scattering them across the repo.
- If you regenerate calibration or telemetry files, preserve the filename stem so
  downstream tooling can continue to find related assets predictably.
