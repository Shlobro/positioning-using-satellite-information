# Data Developer Guide

This folder stores local captured datasets and calibration assets that are too large
or too environment-specific to commit as mainline source artifacts.

Current scope:

- Each capture session should live in its own subfolder.
- Session folders may contain replay telemetry, extracted frames, reference map
  imagery, and local calibration files.
- Data here is for measurable local evaluation and should support replaying a
  concrete vertical slice end to end.

Guidelines:

- Keep one folder per capture session so telemetry, imagery, and notes stay
  aligned.
- Prefer machine-readable calibration sidecars such as JSON over ad hoc text.
- Record whether map imagery is north-up and how pixel coordinates were tied to
  geographic coordinates.
- Do not treat files in `data/` as implicitly trustworthy ground truth; document
  known issues such as mixed altitude references or calibration uncertainty.
