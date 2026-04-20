# Src Developer Guide

This folder contains importable Python source for the project.

Current scope:

- `satellite_drone_localization/` holds the Phase 0 smoke-test implementation.

Guidelines:

- Keep runnable logic in importable modules, not in ad hoc scripts.
- Add new subpackages when responsibilities diverge, for example `geo/`, `eval/`, or `server/`.
- Keep file sizes well below the repository limit and split modules before they become broad.
