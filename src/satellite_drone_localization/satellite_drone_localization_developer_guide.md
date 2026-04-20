# Satellite Drone Localization Developer Guide

This package currently implements the Phase 0 smoke path.

Current responsibilities:

- load a small run configuration
- create a versioned run directory
- write metrics, predictions, logs, and a simple overlay artifact
- expose a CLI entry point used by the repository script

Design notes:

- The implementation currently uses only the Python standard library so the scaffold stays easy to boot.
- Artifact writing is centralized in `run_manager.py`.
- The smoke path is deterministic so tests can verify exact outputs.
