# Root Developer Guide

This repository is organized around measurable research slices for satellite-to-drone localization.

Root responsibilities:

- `final-grand-plan.md` is the long-lived research plan and must be updated when we learn something that changes execution details, verification strategy, or phase sequencing.
- `AGENTS.md` defines repository-specific working rules for AI agents in this workspace.
- `HUMAN_NEXT_STEPS.md` is the human-facing operational checklist for the current handoff point in the project.
- `pyproject.toml` defines the Python package and shared tool configuration.
- root markdown files are allowed because the repository root is the exception to the single-guide-per-folder rule.

Repository structure:

- `src/` — importable Python package (`satellite_drone_localization`)
- `scripts/` — thin CLI wrappers and the verification harness
- `tools/` — standalone utility applications (not part of the main package)
- `configs/` — committed example packets and configs
- `artifacts/` — run outputs and manual-verification logs (gitignored bulk data)
- `experiments/` — experiment log CSV and change log
- `data/` — local captured imagery (gitignored)

Current verification rule:

- For this project, the required verification entry point is `scripts/run_pytest_isolation.bat`, and it should be run by the user locally.
- The batch script delegates bounded checks to `scripts/verify_repo.py`.
- The batch script now pauses before closing so the user can copy the output directly from the terminal window.
- Direct `pytest`, `python -m pytest`, or targeted pytest invocation from the agent session is forbidden here because it repeatedly hangs under the agent wrapper.
- Long-running in-session verification commands such as `python scripts/verify_repo.py` may also stall under the agent wrapper, so the user-run local path remains the authoritative verification route.
- The verification script now checks nine vertical slices: Phase 0 smoke artifacts, Phase 1 replay schema parsing, Phase 1 geometry-report generation, Phase 1 crop-plan generation, the combined Phase 1 replay pipeline, the minimal Phase 1 live receiver stub, the main-package map georeference transform, the sequence-search evaluator, and the standalone map calibrator tool tests.
- The sequence-search slice now includes the first explicit recursive
  prior-recentering policy, not just fixed-seed and oracle-baseline comparisons.
- The sequence-search slice now also includes a deterministic placeholder
  matcher scenario, so recursive tracking drift can be measured before any
  heavy image-matching dependency is introduced.
- The sequence-search slice now also includes a first simple real
  image-template baseline that uses Pillow for grayscale raster matching
  against the calibrated GIS image.

Guidelines:

- Keep project-level workflow decisions documented here and in `final-grand-plan.md`.
- Keep operational records in `experiments/`.
- Prefer repository-facing scripts under `scripts/` rather than ad hoc shell snippets.
