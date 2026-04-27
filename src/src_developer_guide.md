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
- `satellite_drone_localization/eval/` now holds offline sequence-evaluation code that tests motion-bounded search windows against calibrated GIS imagery.
- `satellite_drone_localization/eval/` now also holds the first explicit
  recursive prior-propagation experiment, so sequence policy changes can be
  measured before a real image matcher exists.

Guidelines:

- Keep runnable logic in importable modules, not in ad hoc scripts.
- Add new subpackages when responsibilities diverge, for example `geo/`, `eval/`, or `server/`.
- Keep file sizes well below the repository limit and split modules before they become broad.
