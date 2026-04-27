# Tests Developer Guide

This folder contains automated tests for importable project code.

Current scope:

- smoke-run tests verify the artifact layout and CLI wiring for Phase 0.
- replay tests verify the `dev-packet-v1` packet schema, session defaults, and replay CLI summary path.
- geometry tests verify footprint dimensions, north-up normalization angles, and geometry debug artifact generation.
- crop tests verify prior parsing, target offsets, crop sizing, and crop debug artifact generation.
- replay-pipeline tests verify the combined artifact set and the first telemetry sensitivity summaries.
- live-receiver tests verify one `live_frame` packet can be parsed into the existing single-frame geometry and crop path.
- map-georeference tests verify calibrated GIS control points can be turned into a deterministic pixel-to-lat/lon transform with stable inverse mapping.
- sequence-search tests verify both the strict seed-only baseline and the oracle previous-truth ceiling against a calibrated GIS reference image.
- sequence-search tests now also verify the first explicit recursive prior
  feedback scenario, including its carried confidence radius and prior-source
  labeling.
- matcher-placeholder tests verify the deterministic stand-in measurement model
  accepts centered on-map targets and falls back cleanly when the crop leaves
  the calibrated image.

Guidelines:

- Prefer deterministic tests with temporary directories.
- Test observable artifacts and outputs, not internal implementation details.
- Add tests alongside every new function or workflow introduced into `src/`.
- The repository may use `scripts/verify_repo.py` as the execution path for local verification even though `tests/` remains the source of truth for automated test intent.
