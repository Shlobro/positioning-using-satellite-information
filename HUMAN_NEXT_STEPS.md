# Human Next Steps

This file describes the current human-facing state after adding the optional
RoMa multicandidate map-constrained sequence-localization path.

## 1. Current Decision

The optional non-RoMa dense matcher slice was a negative result, so the next
code slice moved to candidate generation before neural matching.

- `recursive_roma_map_constrained_matcher` remains the current measured neural
  baseline at `4.60m` mean error from the latest relevant run
- `recursive_roma_multicandidate_map_constrained_matcher` is now available in
  RoMa-enabled sequence-search runs
- the new scenario evaluates the prior center plus an 8-neighbor ring of
  nearby map-constrained candidate crops and records candidate-selection
  diagnostics
- syntax compilation passed in the agent session
- required local batch verification passed with `verification_ok` on Python
  `3.12.4`

Decision rule for the next real replay:

- compare `recursive_roma_multicandidate_map_constrained_matcher` against
  `recursive_roma_map_constrained_matcher` on mean error, max error, accepted
  updates, temporal fallbacks, and candidate-rank diagnostics

## 2. What This Means

The RoMa map-constrained temporal-gate scenario remains the baseline until the
multicandidate replay shows a measurable win. The LoFTR path remains available
for future diagnostics, but it is not the next baseline candidate.

## 3. Human Action

Run one DEV-session CUDA RoMa replay and compare the new multicandidate scenario
against the current baseline in the generated `sequence_search_summary.json`.
