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
- Non-pytest repository Python commands may still be worth running from the
  agent when they are directly relevant to the task, but if the shell cannot
  reach the user's interpreter or hits sandbox restrictions, the agent should
  request escalation instead of assuming Python is unavailable.
- Dependency choices in this repository must stay compatible with closed-source
  commercial use. Before adding or installing a new library, check the license
  from primary sources and avoid dependencies that would require the project to
  be open sourced or trigger copyleft disclosure obligations.
- Once a vertical slice has the necessary code and documentation updates plus
  pasted verification evidence from the required workflow, that is the right
  time for the agent to suggest a commit and ask whether the user wants one.
- The verification script now checks nine vertical slices: Phase 0 smoke artifacts, Phase 1 replay schema parsing, Phase 1 geometry-report generation, Phase 1 crop-plan generation, the combined Phase 1 replay pipeline, the minimal Phase 1 live receiver stub, the main-package map georeference transform, the sequence-search evaluator, and the standalone map calibrator tool tests.
- The sequence-search slice now includes the first explicit recursive
  prior-recentering policy, not just fixed-seed and oracle-baseline comparisons.
- The sequence-search slice now also includes a deterministic placeholder
  matcher scenario, so recursive tracking drift can be measured before any
  heavy image-matching dependency is introduced.
- The sequence-search slice now also includes a first simple real
  image-template baseline that uses Pillow for grayscale raster matching
  against the calibrated GIS image.
- The sequence-search slice now also includes a classical local-feature
  matcher scenario so the project can measure a stronger non-neural baseline
  before moving to pretrained neural matchers.
- The sequence-search CLI now also supports an optional RoMa benchmark
  scenario behind explicit `--roma-model` flags, so the repo can measure a
  pretrained neural matcher without making the default local verification path
  download or initialize heavy model weights.
- The sequence-search evaluator now also includes a map-constrained recursive
  image scenario, and the optional RoMa path adds a matching map-constrained
  neural scenario. These policies cap oversized crops to the calibrated image
  extent, shift the search center back into the tile when possible, and report
  how often that happened.
- RoMa matching now has first-pass false-positive rejection for spatially
  degenerate inlier support and implausible fitted footprint scale. These
  failures remain visible as explicit fallback sources in sequence artifacts.

Guidelines:

- Keep project-level workflow decisions documented here and in `final-grand-plan.md`.
- Keep operational records in `experiments/`.
- Prefer repository-facing scripts under `scripts/` rather than ad hoc shell snippets.
- Generated verification outputs under `artifacts/manual-verification/` should
  stay ignored, and one-off local helper wrappers or backup files in `scripts/`
  should not be committed unless they are deliberately promoted into supported
  repository tooling.
