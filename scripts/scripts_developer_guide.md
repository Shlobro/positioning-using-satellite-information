# Scripts Developer Guide

This folder contains thin repository-facing wrappers around importable Python modules.

Guidelines:

- Keep scripts minimal and delegate real logic into `src/`.
- Use scripts for stable commands a human or CI can run directly.
- Prefer one script per top-level workflow instead of embedding multiple modes in one file.
- Windows helper scripts are allowed here when they improve reproducible local verification or debugging.
