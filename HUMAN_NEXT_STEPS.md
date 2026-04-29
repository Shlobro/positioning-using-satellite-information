# Human Next Steps

This file describes the current human-run measurement step for the RoMa sequence-localization work.

## 1. Goal

Measure whether `recursive_roma_velocity_likelihood_matcher` improves on the current strongest RoMa baseline:

- baseline: `recursive_roma_map_constrained_matcher`
- candidate: `recursive_roma_velocity_likelihood_matcher`

The decision should use recorded artifacts, not manual memory.

## 2. Run The CUDA RoMa Replay

Use the Windows machine with CUDA, PyTorch CUDA, and `romatch` already installed.

From the repository root, run:

```powershell
python scripts\sequence_search_replay.py `
  --replay-file data\DEV-SESSION-20260427T112451Z\dev_packets_v1.jsonl `
  --calibration-file "data\DEV-SESSION-20260427T112451Z\Frame from satellite\GIS system roof next to labs in college_calibration.json" `
  --roma-model roma_outdoor `
  --roma-device cuda `
  --output-dir artifacts\manual-verification\sequence-search-roma-velocity-likelihood
```

Expected output artifacts:

- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_summary.json`
- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_debug.svg`

## 3. Generate The Comparison Report

After the replay finishes, run:

```powershell
python scripts\compare_sequence_search.py `
  --summary-file artifacts\manual-verification\sequence-search-roma-velocity-likelihood\sequence_search_summary.json
```

Expected comparison artifacts:

- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_comparison.json`
- `artifacts/manual-verification/sequence-search-roma-velocity-likelihood/sequence_search_comparison.csv`

## 4. Paste Back The Evidence

Paste the terminal output from both commands, especially these fields:

- `recursive_roma_map_constrained_matcher`
- `recursive_roma_velocity_likelihood_matcher`
- mean error
- max error
- final error
- matched frame count
- fallback-source counts
- comparison recommendation

## 5. Required Repository Verification

After code changes, run the required local verification harness:

```powershell
.\scripts\run_pytest_isolation.bat
```

Paste the output back. Success ends with:

```text
verification_ok
```

## 6. Decision Rule

If velocity likelihood lowers mean error and max error without materially hurting final error or accepted updates, keep developing the sequence-state path.

If it only helps one metric or rejects many updates, tune the likelihood thresholds before adding a fuller particle filter.

If it is worse than the map-constrained temporal gate, keep the temporal-gate scenario as the baseline and investigate confidence calibration from the RoMa diagnostics.
