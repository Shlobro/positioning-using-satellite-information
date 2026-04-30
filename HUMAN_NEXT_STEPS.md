# Human Next Steps

This file describes the current human-facing state after measuring the optional
LoFTR-family sequence-localization benchmark path.

## 1. Current Decision

The optional non-RoMa dense matcher slice is implemented and measured once on
the DEV session.

- `recursive_roma_map_constrained_matcher` remains the current measured neural
  baseline at `4.60m` mean error from the latest relevant run
- `recursive_loftr_map_constrained_matcher` is now available behind explicit
  external checkout/checkpoint CLI flags
- the first real LoFTR run accepted `0/92` updates and reached `11.64m` mean
  error
- required local batch verification passed with `verification_ok` on Python
  `3.12.4`

Decision rule for the next real replay:

- `recursive_loftr_map_constrained_matcher` did not beat `4.60m`, so stop
  pretrained dense matcher swaps for now and move to a different improvement
  class

## 2. What This Means

The RoMa map-constrained temporal-gate scenario remains the neural baseline.
The LoFTR path remains available for future diagnostics, but it is not the next
baseline candidate.

## 3. Human Action

No additional LoFTR setup is needed right now. The next AI slice should choose
a non-dense-matcher-swap improvement class.
