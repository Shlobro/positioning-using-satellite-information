# Artifacts Developer Guide

This folder stores generated outputs that should be inspectable after each run.

Current convention:

- committed guidance lives here
- generated run outputs go under `runs/<run_id>/`
- generated manual checks go under `manual-verification/`
- isolated pytest cache folders go under `pytest-cache/` or `pytest-cache-files-*/`
- generated run outputs are ignored by git

Guidelines:

- Keep the folder structure stable so tooling can rely on it.
- Do not hand-edit generated run files after creation.
- Keep generated evidence local unless a specific result is promoted into an
  operational record under `experiments/`.
