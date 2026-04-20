# Eval Configs Developer Guide

This folder stores evaluation-oriented run configs.

Current file:

- `run_000.json` drives the deterministic Phase 0 smoke run.

Guidelines:

- Keep run IDs explicit.
- Prefer stable defaults that make runs reproducible.
- Add a new config file for materially different evaluation scenarios instead of mutating historical ones.
