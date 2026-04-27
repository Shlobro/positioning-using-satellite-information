# Frame from satellite Developer Guide

This folder stores the GIS reference image for the 2026-04-27 session and the
ground-control-point calibration used to georeference it.

Current contents:

- `GIS system roof next to labs in college.png` is the north-up GIS export that
  covers the full flight path.
- `GIS system roof next to labs in college_calibration.json` stores four
  pixel-to-geographic control points.

Calibration rules:

- Calibration points must use explicit pixel coordinates in image space and
  geographic coordinates in true `lat` then `lng` order.
- Control points should be spread across the usable map area and attached to
  fixed landmarks such as roof or pavement corners.
- If calibration coordinates were copied from a web map in `lng, lat` order,
  convert them before saving the JSON sidecar.
