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
- map-georeference tests now also verify portable relative image references and
  fallback recovery from stale absolute paths in calibration sidecars.
- sequence-search tests verify both the strict seed-only baseline and the oracle previous-truth ceiling against a calibrated GIS reference image.
- sequence-search tests now also verify the first explicit recursive prior
  feedback scenario, including its carried confidence radius and prior-source
  labeling.
- matcher-placeholder tests verify the deterministic stand-in measurement model
  accepts centered on-map targets and falls back cleanly when the crop leaves
  the calibrated image.
- matcher-image-baseline tests verify the first simple real pixel matcher can
  recover a synthetic crop center from a synthetic GIS image and fall back when
  the search crop leaves the image.
- matcher-image-baseline tests also verify the low-texture rejection path so a
  blank or uninformative crop does not become a confident recursive update.
- matcher-image-baseline tests now also verify coarse-to-fine refinement and
  repeated-pattern ambiguity rejection, so acceptance changes remain
  measurable and deterministic.
- matcher-image-baseline tests now also verify that local near-ties around one
  true peak are accepted, while genuinely separate repeated-pattern peaks are
  still rejected.
- matcher-classical tests verify the OpenCV-backed local-feature matcher can
  recover a synthetic crop center, reject low-texture inputs, and fall back
  cleanly when the crop is off-map.
- matcher-roma tests verify the optional RoMa matcher can recover a synthetic
  crop center through an injected fake backend and reject low-texture inputs
  without requiring real model downloads during repo verification.
- matcher-roma tests now also verify false-positive rejection for spatially
  degenerate inlier support and implausible fitted scale using injected fake
  backends.
- matcher-roma tests now also verify that accepted and late-stage rejected
  decisions preserve diagnostic gate values used for future threshold tuning.
- sequence-search tests now also cover the map-constrained search policy,
  including crop-center clamping, map-size crop limiting, and rejection of
  constrained RoMa updates that violate the motion envelope.
- the sequence-search fixture currently expects the recursive classical
  scenario to fail honestly with feature-insufficient fallbacks on its tiny
  synthetic map, because that fixture is meant to verify bookkeeping and
  fallback behavior rather than prove strong feature richness.
- the sequence-search tests now also verify that an explicitly injected RoMa
  matcher adds both `recursive_roma_matcher` and
  `recursive_roma_map_constrained_matcher` while preserving the default
  verifier behavior when RoMa is disabled.
- sequence-search tests now also verify per-scenario estimate-source counts,
  fallback-source counts, and that RoMa diagnostics flow into frame artifacts.
- sequence-search tests now also verify the RoMa temporal gate rejects weak
  large jumps while preserving strong large recovery updates, and that
  map-constrained RoMa motion-gate fallbacks are counted explicitly.
- sequence-search tests now also verify the RoMa sequence-likelihood helper
  rejects low-probability updates, accepts supported motion updates, and that
  the optional RoMa artifact set includes the velocity-predicted likelihood
  scenario with recorded likelihood diagnostics.

Guidelines:

- Prefer deterministic tests with temporary directories.
- Test observable artifacts and outputs, not internal implementation details.
- Add tests alongside every new function or workflow introduced into `src/`.
- The repository may use `scripts/verify_repo.py` as the execution path for local verification even though `tests/` remains the source of truth for automated test intent.
