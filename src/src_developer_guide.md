# Src Developer Guide

This folder contains importable Python source for the project.

Current scope:

- `satellite_drone_localization/` holds the Phase 0 smoke-test implementation.
- `satellite_drone_localization/` now also holds the first Phase 1 packet schema and replay-loading code.
- `satellite_drone_localization/` now also holds the first Phase 1 geometry normalization and debug-report code.
- `satellite_drone_localization/` now also holds the first Phase 1 prior-based crop planning code.
- `satellite_drone_localization/` now also holds the combined replay pipeline and sensitivity-report code.
- `satellite_drone_localization/` now also holds a `live/` subpackage for the minimal live receiver stub.
- `satellite_drone_localization/` now also holds deterministic map georeferencing code that fits a pixel-to-world transform from manually calibrated GIS control points.
- The map georeference loader now resolves calibration image paths relative to
  the calibration file when possible, and falls back from stale absolute paths
  to a sibling image with the same filename.
- `satellite_drone_localization/eval/` now holds offline sequence-evaluation code that tests motion-bounded search windows against calibrated GIS imagery.
- `satellite_drone_localization/eval/` now also holds the first explicit
  recursive prior-propagation experiment, so sequence policy changes can be
  measured before a real image matcher exists.
- `satellite_drone_localization/eval/` now also holds a deterministic
  placeholder matcher module so recursive sequence updates can be scored with
  non-zero localization error before a real perception stack lands.
- `satellite_drone_localization/eval/` now also holds a simple Pillow-backed
  image matcher baseline so the recursive loop can be measured with real pixel
  evidence before heavier matchers are introduced.
- `satellite_drone_localization/eval/` now also applies first-pass acceptance
  safeguards to that image baseline, including low-texture fallback and
  prior-centered candidate ranking.
- `satellite_drone_localization/eval/` now also uses a coarse-to-fine local
  search and a blended edge-plus-grayscale comparison score so the simple
  image matcher can refine within the crop more accurately and reject repeated
  visual patterns more honestly.
- The matcher ambiguity gate now distinguishes between a genuinely different
  second location and a near-duplicate pixel around the same local optimum, so
  verification fixtures do not reject good peaks just because the response
  surface is smooth.
- `satellite_drone_localization/eval/` now also holds a classical
  OpenCV-backed local-feature matcher baseline so recursive sequence updates
  can be compared against a stronger non-neural measurement model before the
  project moves to pretrained neural matchers.
- `satellite_drone_localization/eval/` now also holds an optional
  RoMa-backed neural matcher path that is enabled only when the caller asks
  for it, so pretrained benchmarking does not bloat the default verification
  flow.
- The optional RoMa matcher now rejects geometrically weak dense matches when
  the fitted footprint scale is implausible or the inlier support covers only a
  tiny patch of the frame.
- `satellite_drone_localization/eval/` now also holds sequence policy helpers
  for map-constrained search crops, so boundary-aware bootstrap experiments do
  not bloat the main sequence evaluator.

Guidelines:

- Keep runnable logic in importable modules, not in ad hoc scripts.
- Add new subpackages when responsibilities diverge, for example `geo/`, `eval/`, or `server/`.
- Keep file sizes well below the repository limit and split modules before they become broad.
