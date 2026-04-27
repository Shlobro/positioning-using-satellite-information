# Configs Developer Guide

This folder stores committed configuration files used by scripts and evaluations.

Current scope:

- `eval/` contains Phase 0 evaluation configs.
- `replay/` contains Phase 1 replay packet examples.
- `live/` contains Phase 1 single-packet live stub examples.
- replay examples should now carry enough metadata to exercise geometry normalization, ideally including `frame_width_px` and `frame_height_px` when `camera_vfov_deg` is not recorded explicitly.
- replay examples should also carry prior metadata when available so crop planning can be exercised before field capture code is finalized.
- replay examples should remain small but representative enough to drive the combined replay pipeline and its sensitivity checks.

Guidelines:

- Commit small, readable configs that can be snapshotted into run artifacts.
- Split configs by workflow as the project grows.
- Keep generated snapshots out of this folder; they belong under `artifacts/runs/<run_id>/`.
