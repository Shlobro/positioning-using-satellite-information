# Map Calibrator Developer Guide

Interactive GUI tool for collecting pixel-to-GPS ground control points (GCPs)
from a map or satellite image.

## Purpose

Given a reference image (satellite orthophoto, map tile, etc.) you click four
known locations and enter their real-world GPS coordinates.  The tool saves a
JSON calibration file that downstream code can use to interpolate any pixel
position to a GPS coordinate via a projective (homography) transform.

## Running the tool

```
python tools/map_calibrator/map_calibrator.py [path/to/image.png]
```

If no image path is provided a file-open dialog appears on launch.

Supported image formats: PNG, JPEG, TIFF, BMP (anything Pillow can open).

## Interaction

| Action | Effect |
|---|---|
| Left-click on image | Opens a small popup to enter GPS coordinates for that pixel |
| Scroll wheel | Zoom in / out centred on cursor |
| Right-mouse drag | Pan the image |
| Reset Points button | Clears all collected points so you can start over |
| Save button | Writes `<image_stem>_calibration.json` next to the image |
| Save As… button | File dialog to choose output path |

## Output format

`<image_stem>_calibration.json`:

```json
{
  "image": "/absolute/path/to/image.png",
  "calibration_points": [
    { "pixel": [x, y], "gps": { "lat": 35.194956, "lng": 31.767811 } },
    { "pixel": [x, y], "gps": { "lat": 35.200000, "lng": 31.780000 } },
    { "pixel": [x, y], "gps": { "lat": 35.185000, "lng": 31.790000 } },
    { "pixel": [x, y], "gps": { "lat": 35.175000, "lng": 31.760000 } }
  ]
}
```

Four points are always required.  With four non-collinear GCPs a full
perspective homography can be estimated (`cv2.findHomography` or
`skimage.transform.ProjectiveTransform`).

## GPS input format

The popup accepts coordinates in the format `35.194956°, 31.767811°`.  The
degree symbol is optional and whitespace is ignored.  Latitude must be in
`[-90, 90]` and longitude in `[-180, 180]`.

## Architecture

```
map_calibrator.py          — single-file application, ~330 lines
  MapCalibratorApp         — main tk.Tk wrapper
    _build_ui()            — top bar, canvas, sidebar, status bar
    _render()              — redraws canvas at current zoom/pan
    _show_coord_popup()    — transient tk.Toplevel for GPS entry
    parse_gps()            — module-level pure function, testable without display
    _build_payload()       — assembles JSON dict from collected points
    _write(path)           — serialises payload to disk

test_map_calibrator.py     — headless tests (stubs tkinter + PIL)
```

All GUI state lives in `MapCalibratorApp`.  `parse_gps` and `_build_payload` /
`_write` are pure or near-pure and are tested without a display.

## Dependencies

| Package | Purpose | Install |
|---|---|---|
| `tkinter` | GUI framework | Built into Python 3 |
| `Pillow` | Image loading and resampling | `pip install Pillow` |

No other dependencies are required.  Pillow is not currently listed in
`pyproject.toml` because this is a standalone utility tool; add it to
`[project.dependencies]` if it becomes part of the main package.

## Testing

Tests are headless and stub both `tkinter` and `PIL` so they run in any
environment, including CI without a display.

Run via the repository verification harness:
```
scripts/run_pytest_isolation.bat
```

Or directly:
```
python tools/map_calibrator/test_map_calibrator.py
```
