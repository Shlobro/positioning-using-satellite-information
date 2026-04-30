# Localization GUI Developer Guide

Interactive demo and research tool for satellite-based drone localization. The
window lets you load a calibrated satellite tile, drop a single drone image or
a full replay sequence, set a prior point and search radius, pick which
matcher pipeline to run, and visualize the predicted location, confidence
heatmap, and warped query overlay on top of the map.

## Why this exists

The global goal of this repository is GPS-denied drone localization by
matching drone imagery against satellite imagery. Most existing code in the
repo is offline batch evaluation. This GUI exposes the same machinery in a
form that is good for two things at once:

- demos for stakeholders who want to see localization work in real time
- in-loop research inspection so failures are easier to understand than from
  an artifact JSON

## Running the tool

```
tools\localization_gui\launch_localization_gui.bat
```

or

```
python tools/localization_gui/localization_gui.py
```

Dependencies: `PyQt6`, `pyqtgraph`, `numpy`, `Pillow`. RoMa scenarios also
require the optional `romatch` and `torch` extras already documented in
`pyproject.toml [project.optional-dependencies] neural`.

## What the user does

| Action | Result |
|---|---|
| Pick a satellite tile (file dialog) | Tile is loaded with its `<image>_calibration.json` sidecar so clicks map to lat/lon |
| Choose input mode | "Single image" or "Sequence (replay packet)" |
| Pick a query | Single mode: any drone image with a sibling `<image>_packet.json` sidecar. Sequence mode: a `dev-packet-v1` `.jsonl` replay file. |
| Click on the map *or* type lat/lon | Sets the prior; the search-radius circle updates live |
| Slide the radius | Adjusts the search radius in meters |
| Pick a pipeline | Single mode: `placeholder`, `image_baseline`, `image_map_constrained`, `classical`, `roma`, `roma_map_constrained`. Sequence mode: any scenario in `eval/sequence_search.py`. |
| Run | Executes the chosen pipeline on a background worker thread, shows a busy progress bar in the sidebar, and updates the map and result panel when finished |
| Toggle heatmap / overlay | Show/hide the confidence heatmap and the warped query overlay |

## Single-image input contract

A single drone image is only valid if it has a sidecar file named
`<image>_packet.json` in the same folder. The sidecar is a `dev-packet-v1`
shaped JSON-lines document with one optional `session_start` packet plus
exactly one `frame` packet. Same schema as our replay files, same parser, no
new format. The loader rejects images that do not have a sidecar with a clear
error message — this matches the project rule that single-image inputs must
carry full metadata.

`tools.localization_gui.single_image_input.write_single_image_packet_template`
provides a small helper for writing a sidecar from Python; the GUI itself does
not yet expose an authoring dialog.

## Heatmap source policy

- `placeholder` / `image_baseline` / `image_map_constrained`: confidence
  heatmap is a coarse template-match score grid recomputed locally inside the
  pipeline runner. This matches the image-baseline matcher's evidence model
  and is cheap.
- `classical`: no heatmap — classical features do not produce a dense score
  map worth visualizing, and recomputing one would be misleading.
- `roma`, `roma_map_constrained`: not surfaced in v1. Hooking RoMa's per-pixel
  certainty into the heatmap is a future improvement once we have a place to
  surface it from the matcher's diagnostics.

## File layout

```
tools/localization_gui/
  launch_localization_gui.bat   — Windows launcher
  localization_gui.py            — entry point, app shell, signal wiring
  map_view.py                    — pyqtgraph satellite tile + overlays
  controls_panel.py              — sidebar inputs and signals
  result_panel.py                — bottom result strip and frame navigator
  pipeline_runner.py             — adapter to existing matchers and sequence_search
  single_image_input.py          — single-image sidecar loader and writer
  __init__.py                    — package marker
  localization_gui_developer_guide.md
```

## Architecture

- `localization_gui.MainWindow` owns the application state: the loaded tile
  and georeference, the active query (single packet *or* replay path), and
  the latest run result.
- It wires `ControlsPanel` signals (tile picked, query picked, prior set,
  radius changed, pipeline changed, run requested) and `MapView` signals
  (prior moved by map click) to its own slots.
- Run requests are dispatched through `pipeline_runner.RunRequest` and
  `pipeline_runner.execute_run_request`. `MainWindow` executes that request on
  a `QThread` worker so expensive matchers do not block Qt repaints or make
  the window appear frozen.
- All actual localization runs happen inside `pipeline_runner.py`. That
  module imports the existing matchers and `build_sequence_search_artifacts`
  from `satellite_drone_localization.eval` directly, so adding a new scenario
  in the main package is enough — the GUI picks it up via
  `list_pipelines_for_input("sequence")`.
- `MapView` keeps Qt-specific overlay management (markers, radius circle,
  heatmap, warped query overlay) isolated from the pipeline.
- `ResultPanel` displays predicted lat/lon, error vs. truth (when available),
  match score, runtime, and the current frame thumbnail. It also exposes
  prev/next navigation for sequence runs.

## Running-state behavior

- While a run is active, the sidebar disables tile/query/prior/pipeline edits
  to avoid mutating GUI state underneath an in-flight worker.
- The sidebar shows an indeterminate progress bar and changes the run button
  text to `Running…`.
- This v1 progress indicator is intentionally honest: single-image and
  sequence paths now remain responsive, but they do not yet expose per-frame
  percentage completion from `sequence_search.py`.

## Coordinate system

The GUI uses the same calibration sidecar format as `tools/map_calibrator/`
(four pixel↔GPS control points fitted into an affine transform by
`satellite_drone_localization.map_georeference`). All click→lat/lon and
predicted-pixel↔lat/lon conversions go through that transform. Pixel
coordinates inside `MapView` are image-pixel coordinates with Y inverted so
the visual layout matches the satellite tile. The radius circle is sized in
meters by sampling the local meters-per-pixel from the georeference.

## Tests

GUI logic that is *not* Qt-bound is covered by:

- `tests/test_localization_gui_single_image.py`: single-image sidecar loader,
  template writer, validation of the one-frame-only constraint, and image
  filename matching.
- `tests/test_localization_gui_pipeline_runner.py`: pipeline list helpers,
  calibrated-tile loader, single-image placeholder run, single-image
  image-baseline run with heatmap, and typed run-request dispatch for both
  single-image and sequence modes.

These tests do not require a display; they synthesize a tiny calibrated map
and a derived frame in a temp directory.

GUI rendering itself is not tested automatically. Verify visually by running
the launcher.

## Where to extend

- Add a new pipeline by either adding a scenario in
  `src/satellite_drone_localization/eval/sequence_search.py` (sequence mode)
  or wiring a new branch in
  `tools/localization_gui/pipeline_runner.py::_run_single_matcher`
  (single-image mode).
- Surface RoMa per-pixel certainty as a heatmap by extending
  `RoMaRegressionMatcher` to expose it through diagnostics, then plumbing
  through `pipeline_runner._compute_heatmap_if_supported`.
- Add a single-image-packet authoring dialog by reusing
  `single_image_input.write_single_image_packet_template`.
