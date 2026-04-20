# Tests Developer Guide

This folder contains automated tests for importable project code.

Current scope:

- smoke-run tests verify the artifact layout and CLI wiring for Phase 0.

Guidelines:

- Prefer deterministic tests with temporary directories.
- Test observable artifacts and outputs, not internal implementation details.
- Add tests alongside every new function or workflow introduced into `src/`.
