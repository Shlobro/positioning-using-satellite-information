# Eval Developer Guide

This subpackage holds offline evaluation code that measures whether the current
assumptions are viable before matcher or live-loop complexity increases.

Current scope:

- `sequence_search.py` evaluates motion-bounded sequence priors against hidden
  GPS truth and a calibrated GIS reference image.
- `matcher_placeholder.py` holds the deterministic stand-in measurement model
  used before a real image matcher exists.
- `sequence_search_cli.py` writes replay-driven JSON and SVG artifacts for that
  sequence evaluation slice.
- The sequence evaluator now reports four explicit policies:
  `seed_only`, `oracle_previous_truth`, and
  `recursive_oracle_estimate`, plus `recursive_placeholder_matcher`.
- `recursive_oracle_estimate` is the first explicit stateful prior loop in the
  repo. It carries a previous accepted estimate forward and expands the next
  search radius from a configurable post-update confidence radius plus motion
  growth.
- `recursive_placeholder_matcher` keeps the same recursive control loop but
  replaces the perfect oracle update with a deterministic truth-anchored
  placeholder measurement so non-zero estimation error and fallback behavior
  can be measured.

Guidelines:

- Keep evaluation code deterministic and artifact-focused.
- Prefer multiple explicit scenarios when runtime behavior is not implemented
  yet, for example a strict seed-only baseline and an optimistic oracle ceiling.
- Use hidden ground truth only for scoring and diagnostic summaries unless a
  scenario is intentionally labeled as an oracle upper bound.
- When a runtime policy becomes stateful, encode that state transition
  explicitly in the evaluator instead of hiding it inside one special-case
  branch.
- When a placeholder is used in place of a real matcher, label it honestly in
  scenario names and estimate-source fields so artifacts do not imply image
  evidence that the code did not actually use.
