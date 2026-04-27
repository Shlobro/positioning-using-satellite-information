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
- `matcher_classical.py` holds the stronger classical local-feature baseline
  used to compare recursive tracking against the raster matcher before moving
  to neural approaches.
- `matcher_roma.py` holds the optional pretrained RoMa benchmark path used to
  compare recursive tracking against the classical and raster baselines.
- `sequence_policy.py` holds reusable map-boundary policy helpers for
  boundary-aware recursive search experiments.
- `sequence_search_cli.py` writes replay-driven JSON and SVG artifacts for that
  sequence evaluation slice.
- The sequence evaluator now reports seven default explicit policies:
  `seed_only`, `oracle_previous_truth`, `recursive_oracle_estimate`,
  `recursive_placeholder_matcher`, `recursive_image_baseline_matcher`, and
  `recursive_image_map_constrained_matcher`, and
  `recursive_classical_matcher`.
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
- The sequence evaluator now also reports `recursive_classical_matcher`, which
  uses AKAZE first and ORB-with-forced-corners as a fallback inside the same
  bounded crop. This scenario is useful even when it fails, because the
  estimate-source breakdown shows whether the classical path is failing from
  off-map priors, low feature count, or weak geometric support.
- When explicitly enabled, the sequence evaluator now also reports
  `recursive_roma_matcher`, which uses a pretrained RoMa model to generate
  dense correspondences and then fits a robust affine center estimate inside
  the bounded crop. This neural scenario is opt-in so the default verifier
  does not download or initialize large model weights.
- RoMa acceptance now also requires enough spatial inlier coverage across the
  frame and a plausible affine footprint scale. Failures are reported as
  explicit fallback sources (`fallback_roma_poor_spatial_coverage` or
  `fallback_roma_implausible_scale`) so false-positive rejection stays
  measurable in replay summaries.
- When RoMa is enabled, the evaluator also reports
  `recursive_roma_map_constrained_matcher`, which applies the same
  map-limited crop and motion-envelope guard used by the constrained raster
  scenario. This keeps boundary-policy results separate from the original RoMa
  benchmark.

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
- When adding optional heavy matchers, keep the default repo verification path
  lightweight and deterministic. Use injected fake backends in tests and real
  replay measurements for the actual benchmark value.
