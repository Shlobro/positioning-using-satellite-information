# Human Next Steps

This file describes the current human-facing state after the latest RoMa
sequence-localization measurement.

## 1. Current Decision

The 2026-04-30 prediction-consistency replay is complete.

- verification passed with `verification_ok`
- `recursive_roma_map_constrained_matcher` stayed strongest
- `recursive_roma_velocity_likelihood_matcher` became clearly worse even after
  the stricter likelihood gate

Measured result from the latest replay:

- baseline: `53/92` matches, `4.60m` mean error
- candidate: `23/92` matches, `14.09m` mean error
- candidate low-likelihood fallbacks: `2`
- comparison recommendation: `keep_map_constrained_temporal_gate_as_baseline`

## 2. What This Means

The current Roma velocity-likelihood branch is closed as a negative result.
Do not spend more human time rerunning this branch unless a later code slice
reopens it for a specific reason.

## 3. Human Action

No additional human-run Roma replay is needed right now.

The next useful human action is to review the recorded artifacts if desired:

- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_summary.json`
- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_comparison.json`

Otherwise, wait for the next AI slice to define the post-Roma direction.
