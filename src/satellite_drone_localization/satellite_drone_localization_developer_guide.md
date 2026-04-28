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
- support a simple grayscale image-template matcher in the `eval/` subpackage
  so recursive sequence updates can be driven by real pixel comparisons against
  the calibrated GIS image
- support a classical local-feature matcher in the `eval/` subpackage so the
  recursive loop can also be measured with AKAZE/ORB-style correspondences
  before neural matchers are introduced
- support an optional RoMa matcher in the `eval/` subpackage so the first
  pretrained neural benchmark can run inside the same recursive crop and
  prior-update interface without becoming mandatory for the default repo
  verification path
- reject RoMa updates whose fitted transform is geometrically implausible or
  whose inlier support is spatially degenerate, so false positives fail with
  explicit fallback reasons instead of becoming confident recursive state
  updates

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
- Calibration sidecars should store portable relative image paths. The loader
  still tolerates a stale absolute path by falling back to a sibling image with
  the same filename, which makes repo moves and machine changes less brittle.
- The live stub intentionally reuses the replay field names and lowers transport risk by accepting `packet_type: "live_frame"` and converting it into the existing single-frame parsing path.
- The recursive sequence evaluator still uses hidden truth as an oracle stand-in
  for an accepted localization result, but it now does so through an explicit
  state update loop instead of a one-off prior branch. This keeps the control
  logic measurable before a real matcher exists.
- The placeholder matcher is intentionally not a real perception model. It uses
  crop geometry plus calibrated-map residuals to synthesize bounded update
  error and fallback cases, which is useful for measuring control-loop behavior
  without introducing external image-processing dependencies yet.
- The first real image baseline intentionally stays simple: Pillow-backed
  grayscale edge images, north-up frame rotation, projected footprint sizing,
  and exhaustive crop-local template search. It is a sanity-check baseline, not
  the intended production matcher.
- The image baseline now rejects very low-texture templates and uses a small
  prior-center ranking bias when visual scores are close. This makes recursive
  feedback less likely to jump far from the current prior on ambiguous crops,
  but it remains a simple diagnostic baseline.
- The image baseline now also refines the strongest coarse candidates at
  per-pixel resolution and scores candidates with blended edge and grayscale
  evidence. This keeps the baseline lightweight while reducing stride-induced
  quantization error and making repeated-pattern ambiguity visible through the
  acceptance gate.
- The ambiguity gate now looks for a runner-up that is meaningfully separated
  from the best location before declaring the match ambiguous. Nearby pixels on
  the same peak are treated as one local optimum rather than as evidence of a
  repeated-pattern failure.
- The classical matcher is intentionally measured as a separate baseline rather
  than replacing the raster matcher immediately. It uses a calibrated local
  crop plus OpenCV feature correspondences so negative results still teach us
  whether close-range frames are failing because of representation, geometry,
  or simple lack of matchable structure.
- The RoMa matcher follows the same measurement philosophy: it is an optional
  benchmark path, not a silent replacement of earlier baselines. It converts
  dense correspondences into a robust affine center estimate and keeps explicit
  fallback reasons so neural failures remain inspectable rather than being
  treated as oracle-quality localization.
- RoMa acceptance now includes spatial-coverage and affine-scale checks in
  addition to inlier count, inlier ratio, certainty, and reprojection error.
  This is a first confidence-calibration step aimed at rejecting dense-match
  false positives before they enter the recursive prior state.
- RoMa decisions now carry diagnostic gate values when the matcher reaches
  correspondence fitting, and sequence summaries aggregate estimate-source and
  fallback-source counts for every scenario. These fields are intended for
  threshold tuning and confidence calibration, not for replacing the recorded
  per-frame rows.
- The map-constrained sequence policy is measured as a separate scenario. It
  caps search crops to the available calibrated reference extent, shifts the
  crop center back into the tile when possible, keeps failed measurements from
  replacing the previous state with an artificial clamped center, and rejects
  accepted constrained updates that violate the motion envelope.
