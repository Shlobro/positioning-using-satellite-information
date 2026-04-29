# Eval Reports Developer Guide

This folder contains small report generators that read completed evaluation
artifacts and write derived decision-support outputs.

Current responsibilities:

- `sequence_comparison.py` compares two scenarios from a
  `sequence_search_summary.json` artifact.
- `sequence_comparison_cli.py` exposes that comparison as a command-line
  workflow through `scripts/compare_sequence_search.py`.

Guidelines:

- Do not run heavy matchers or mutate source replay artifacts from this folder.
- Keep report inputs explicit and file-based so results can be reproduced from
  recorded artifacts.
- Add new report modules here when they reduce large evaluation outputs into
  smaller decision artifacts.
