# Scripts Developer Guide

This folder contains thin repository-facing wrappers around importable Python modules.

Guidelines:

- Keep scripts minimal and delegate real logic into `src/`.
- Use scripts for stable commands a human or CI can run directly.
- Prefer one script per top-level workflow instead of embedding multiple modes in one file.
- Windows helper scripts are allowed here when they improve reproducible local verification or debugging.
- `replay_packets.py` is the Phase 1 schema-validation entry point for local packet captures and committed examples.
- `geometry_replay.py` is the Phase 1 geometry-debug entry point that turns replay packets into summary JSON and an SVG footprint visualization.
- `crop_replay.py` is the Phase 1 crop-debug entry point that turns replay packets plus priors into crop summaries and an SVG overlay.
- `replay_pipeline.py` is the Phase 1 combined replay entry point that writes one artifact set spanning geometry, crop planning, and sensitivity summaries.
- `sequence_search_replay.py` is the Phase 1 hidden-GPS sequence entry point that compares motion-bounded search windows against a calibrated GIS reference image.
- `sequence_search_replay.py` now also exposes
  `--measurement-update-radius-m` so the first recursive prior-feedback policy
  can be measured from the command line.
- `live_receiver_stub.py` is the Phase 1 minimal live intake entry point for one `live_frame` packet.
- Repository-facing Python scripts should bootstrap `src/` explicitly so `python scripts/<tool>.py` works on a fresh checkout without installing the package first.
- `verify_repo.py` is the deterministic repository verification path when direct `pytest` execution is not trustworthy in the local shell wrapper.
- `run_pytest_isolation.bat` is the required user-run repository verification entry point. The agent should ask the user to run it and paste the output instead of relying on in-session execution.
- `run_pytest_isolation.bat` should pause before exit on both success and failure so the user can copy terminal output without reopening logs.
- `verify_repo.py` now also exercises the map calibrator headless tests as a seventh verification slice.
- `verify_repo.py` now also exercises the main-package map georeference transform as an eighth verification slice.
- `verify_repo.py` now also exercises the sequence-search evaluator as a ninth verification slice.
- If in-session execution of `verify_repo.py` stalls, treat the user-run local output as authoritative instead of retrying repeatedly inside the agent wrapper.
