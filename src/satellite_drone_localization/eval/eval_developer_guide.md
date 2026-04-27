# Eval Developer Guide

This subpackage holds offline evaluation code that measures whether the current
assumptions are viable before matcher or live-loop complexity increases.

Current scope:

- `sequence_search.py` evaluates motion-bounded sequence priors against hidden
  GPS truth and a calibrated GIS reference image.
- `sequence_search_cli.py` writes replay-driven JSON and SVG artifacts for that
  sequence evaluation slice.
- The sequence evaluator now reports three explicit policies:
  `seed_only`, `oracle_previous_truth`, and
  `recursive_oracle_estimate`.
- `recursive_oracle_estimate` is the first explicit stateful prior loop in the
  repo. It carries a previous accepted estimate forward and expands the next
  search radius from a configurable post-update confidence radius plus motion
  growth.

Guidelines:

- Keep evaluation code deterministic and artifact-focused.
- Prefer multiple explicit scenarios when runtime behavior is not implemented
  yet, for example a strict seed-only baseline and an optimistic oracle ceiling.
- Use hidden ground truth only for scoring and diagnostic summaries unless a
  scenario is intentionally labeled as an oracle upper bound.
- When a runtime policy becomes stateful, encode that state transition
  explicitly in the evaluator instead of hiding it inside one special-case
  branch.
