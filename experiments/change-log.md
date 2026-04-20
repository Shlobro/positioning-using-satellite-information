# Change Log

## 2026-04-20

- owner: Codex
- files changed: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`
- intent: Clarify that each non-root folder is limited to one developer guide markdown file, while operational markdown files such as changelogs remain allowed.
- linked run_ids: none
- actual result: Rule wording now distinguishes developer guides from operational project records, removing the ambiguity that blocked creating `experiments/change-log.md`.

- owner: Codex
- files changed: `.gitignore`, `pyproject.toml`, `src/`, `scripts/`, `configs/`, `artifacts/`, `tests/`, `experiments/change-log.md`, `experiments/experiment-log.csv`, `final-grand-plan.md`
- intent: Create the Phase 0 Python scaffold, add the deterministic `RUN-000` smoke path, and establish reproducible artifact and test structure for future phases.
- linked run_ids: `RUN-000`
- actual result: The repository now has a minimal importable package, repository script, evaluation config, deterministic artifact writer, and smoke-run tests. `RUN-000` was generated successfully with the required config snapshot, metrics, predictions, run log, and overlay artifact. Direct Python verification passed, while `pytest` remains blocked by this environment and needs separate isolation before it can be treated as a completed verification path.

- owner: Codex
- files changed: `scripts/run_pytest_isolation.bat`, `scripts/scripts_developer_guide.md`, `experiments/change-log.md`, `final-grand-plan.md`
- intent: Add a user-run Windows verification harness that executes the smoke path and isolates pytest hangs with explicit per-step timeouts and log capture.
- linked run_ids: none
- actual result: A manual `.bat` workflow now exists for local verification outside the agent tool wrapper, allowing the user to observe exactly which pytest step hangs without risking another runaway tool invocation in-session.
