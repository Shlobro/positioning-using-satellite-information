# Satellite Drone Localization Developer Guide

This package currently implements the Phase 0 smoke path plus the first Phase 1 replay contract.

Current responsibilities:

- load a small run configuration
- create a versioned run directory
- write metrics, predictions, logs, and a simple overlay artifact
- expose a CLI entry point used by the repository script
- validate the `dev-packet-v1` replay packet format
- load replay files with session-level defaults and per-frame overrides
- compute deterministic footprint geometry from altitude, heading, and FOV
- generate replay-driven geometry summary artifacts for manual inspection
- compute deterministic crop windows around a per-frame or fallback prior
- generate replay-driven crop summary artifacts for manual inspection
- run a combined replay pipeline that writes one artifact set for geometry, crop, and sensitivity inspection
- fit an affine pixel-to-geographic transform from manually calibrated GIS control points
- expose a minimal live receiver stub via the `live/` subpackage
- delegate sequence-specific evaluation workflows to the `eval/` subpackage
- support an explicit recursive prior-update experiment where the next search
  center comes from the previous accepted estimate and carries forward a
  configurable confidence radius
- support a deterministic truth-anchored placeholder matcher in the `eval/`
  subpackage so recursive sequence updates can accumulate measurable estimation
  error before a real image matcher is integrated

Design notes:

- The implementation currently uses only the Python standard library so the scaffold stays easy to boot.
- Artifact writing is centralized in `run_manager.py`.
- The smoke path is deterministic so tests can verify exact outputs.
- Replay packets use JSON-lines so field recording code can append packets incrementally without rewriting a full file.
- Prefer explicit unit-bearing names such as `latitude_deg`, `altitude_m`, and `camera_hfov_deg`, but the parser currently accepts short aliases like `lat`, `lon`, `altitude`, `heading`, and `fov` for convenience.
- Geometry normalization is north-up by definition in this phase, so the reported normalization rotation is the negative of the drone heading modulo 360 degrees.
- If `camera_vfov_deg` is missing, geometry will infer it from `frame_width_px` and `frame_height_px` when available, otherwise it falls back to `camera_hfov_deg`.
- Crop planning accepts optional `prior_latitude_deg`, `prior_longitude_deg`, and `prior_search_radius_m` values. If no prior center is provided, the current frame position is used as a degenerate prior for deterministic fallback behavior.
- Crop side length is the larger of the normalized geometry footprint and a padded prior-search window, so the crop plan remains explicit about both sensor footprint and prior uncertainty.
- The replay pipeline composes replay parsing, geometry, crop planning, and telemetry sensitivity checks into one deterministic artifact set for manual review.
- `map_georeference.py` fits a least-squares affine transform from four or more calibration points and exposes pixel-to-lat/lon plus inverse lat/lon-to-pixel conversion for GIS reference imagery.
- The live stub intentionally reuses the replay field names and lowers transport risk by accepting `packet_type: "live_frame"` and converting it into the existing single-frame parsing path.
- The recursive sequence evaluator still uses hidden truth as an oracle stand-in
  for an accepted localization result, but it now does so through an explicit
  state update loop instead of a one-off prior branch. This keeps the control
  logic measurable before a real matcher exists.
- The placeholder matcher is intentionally not a real perception model. It uses
  crop geometry plus calibrated-map residuals to synthesize bounded update
  error and fallback cases, which is useful for measuring control-loop behavior
  without introducing external image-processing dependencies yet.
