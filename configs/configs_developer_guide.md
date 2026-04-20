# Configs Developer Guide

This folder stores committed configuration files used by scripts and evaluations.

Current scope:

- `eval/` contains Phase 0 evaluation configs.

Guidelines:

- Commit small, readable configs that can be snapshotted into run artifacts.
- Split configs by workflow as the project grows.
- Keep generated snapshots out of this folder; they belong under `artifacts/runs/<run_id>/`.
