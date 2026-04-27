# Eval Developer Guide

This subpackage holds offline evaluation code that measures whether the current
assumptions are viable before matcher or live-loop complexity increases.

Current scope:

- `sequence_search.py` evaluates motion-bounded sequence priors against hidden
  GPS truth and a calibrated GIS reference image.
- `matcher_placeholder.py` holds the deterministic stand-in measurement model
  used before a real image matcher exists.
- `matcher_image_baseline.py` holds the first simple real image-template
  baseline used to compare recursive tracking against placeholder and oracle
  scenarios.
- `sequence_search_cli.py` writes replay-driven JSON and SVG artifacts for that
  sequence evaluation slice.
- The sequence evaluator now reports four explicit policies:
  `seed_only`, `oracle_previous_truth`,
  `recursive_oracle_estimate`, `recursive_placeholder_matcher`, and
  `recursive_image_baseline_matcher`.
- `recursive_oracle_estimate` is the first explicit stateful prior loop in the
  repo. It carries a previous accepted estimate forward and expands the next
  search radius from a configurable post-update confidence radius plus motion
  growth.
- `recursive_placeholder_matcher` keeps the same recursive control loop but
  replaces the perfect oracle update with a deterministic truth-anchored
  placeholder measurement so non-zero estimation error and fallback behavior
  can be measured.
- `recursive_image_baseline_matcher` keeps the same recursive control loop but
  replaces the placeholder update with a simple grayscale template match inside
  the calibrated GIS crop, so real pixel evidence can be compared against the
  oracle and placeholder ceilings.
- The image baseline now applies a low-texture fallback and a prior-center
  ranking bias before accepting a template match. This keeps ambiguous visual
  evidence from jumping as aggressively across the crop while preserving the
  same scenario and artifact schema.
- The image baseline now also uses a coarse-to-fine search. It scores a coarse
  grid first, then refines the best candidates at per-pixel resolution with a
  blended edge-plus-grayscale score and a small winner-over-runner-up margin
  check. This keeps the baseline simple while making sub-stride corrections
  and repeated-pattern ambiguity measurable.
- The winner-over-runner-up ambiguity check now ignores neighboring pixels that
  belong to the same local peak. Only a materially separated second location is
  treated as a true ambiguous alternative.

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
- Keep image baselines explicit about their simplicity. Record match-score
  diagnostics so weak image evidence is visible instead of silently treated as
  oracle-quality localization.
- When adding image-matcher gates, measure both error and map persistence on a
  real replay. A stricter gate is only useful if it improves recursive behavior
  or makes failure more honest in the artifact summaries.
