# Neural Matchers Developer Guide

This folder holds optional neural matcher adapters that are too heavyweight or
environment-specific for the default repository verification path.

Current scope:

- `matcher_loftr.py` adapts an external Apache-2.0 EfficientLoFTR checkout and
  checkpoint into the sequence evaluator's common `match_frame` contract.
- EfficientLoFTR checkpoint loading uses `torch.load(..., weights_only=False)`
  because the published checkpoint contains PyTorch Lightning metadata that
  PyTorch 2.6+ rejects in weights-only mode. Only use this opt-in path with a
  trusted checkpoint file.
- Tests inject fake backends, so this folder must not require model downloads
  or GPU initialization during default verification.

Guidelines:

- Keep external neural dependencies optional and behind explicit CLI flags.
- Prefer adapter modules here when a matcher needs model-specific loading,
  checkpoint handling, or CUDA inference setup.
- Do not vendor third-party model code or weights into this repository.
