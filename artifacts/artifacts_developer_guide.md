# Artifacts Developer Guide

This folder stores generated outputs that should be inspectable after each run.

Current convention:

- committed guidance lives here
- generated run outputs go under `runs/<run_id>/`
- generated run outputs are ignored by git

Guidelines:

- Keep the folder structure stable so tooling can rely on it.
- Do not hand-edit generated run files after creation.
