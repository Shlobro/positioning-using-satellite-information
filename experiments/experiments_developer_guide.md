# Experiments Developer Guide

This folder stores project tracking artifacts for research and evaluation work.

Files in this folder are operational records, not implementation code.

Required artifacts:

- `change-log.md` records significant code, config, and process changes before results are known.
- `experiment-log.csv` will store one row per recorded run.

Guidelines:

- Keep entries measurable and specific.
- Record intent before outcomes when possible.
- Link changes to run IDs once runs exist.
- Do not store generated large artifacts here; use `artifacts/` for run outputs.
