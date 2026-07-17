## Summary

Implement Level 1 of the ELSPR reproduction: pair aggregation, tie-aware
tournament graphs, SCC analysis, directed structural entropy, reconstruction,
filtering, deterministic toy tests, and a runnable CLI pipeline.

## Why

This establishes the fully auditable algorithmic reproduction before any paid
judge API calls or GPU training.

## Validation

Each stage must pass its focused tests. The completed branch must also pass
Ruff, the full Pytest suite, and the toy pipeline smoke test.

## Boundaries

- No paper results are hard-coded.
- No credentials, private data, checkpoints, or generated run artifacts are
  committed.
- Missing supplementary details are recorded as deviations.
