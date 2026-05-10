# Human Next Steps

This file describes the current human-facing state after measuring the optional
RoMa multicandidate map-constrained sequence-localization path.

## 1. Current Decision

The optional non-RoMa dense matcher slice and the multicandidate RoMa
candidate-generation slice were both negative results.

- `recursive_roma_map_constrained_matcher` remains the current measured neural
  baseline at `4.60m` mean error from the latest relevant run.
- `recursive_roma_multicandidate_map_constrained_matcher` accepted more
  updates (`65/92` versus `53/92`) but degraded mean error to `21.26m` and max
  offset to `71.31m`.
- the comparison report recommended
  `keep_map_constrained_temporal_gate_as_baseline`.

Decision rule for the next implementation slice:

- do not expand multicandidate RoMa search unless new diagnostics show a
  specific false-positive rejection rule that would prevent the bad accepted
  updates.
- focus on confidence and false-positive calibration for
  `recursive_roma_map_constrained_matcher`, targeting reduced max error and bad
  accepted updates without regressing the `4.60m` mean-error baseline.

## 2. What This Means

The RoMa map-constrained temporal-gate scenario remains the baseline. The LoFTR
and multicandidate paths remain available for diagnostics, but neither is the
next baseline candidate.

## 3. Human Action

No immediate human replay is needed before the next code slice. The next AI
task is to inspect the recorded RoMa diagnostics and add a measurable
confidence/false-positive calibration change for the current baseline.
