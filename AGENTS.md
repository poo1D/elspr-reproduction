# ELSPR Reproduction Instructions

## Required context

Before implementation, modification, or review, read:

1. `GOAL.md` for the full reproduction specification, algorithm definitions, and completion criteria.
2. `PROGRESS.md` for the current stage, completed work, deviations, and next step.
3. `REPRODUCIBILITY.md` when it exists, for paper ambiguities, assumptions, and experimental deviations.

## Execution rules

- Work in Level 1, then Level 2, then Level 3 order.
- Only implement the current stage recorded in `PROGRESS.md`; do not silently skip validation gates.
- Do not hard-code paper results or present missing paper details as known facts.
- Implement core logic as typed, testable functions rather than notebook-only code.
- Treat raw data as read-only and keep derived outputs traceable to configs, seeds, hashes, and commits.
- Never commit API keys, tokens, private data, model weights, checkpoints, caches, or large run artifacts.
- Before completing a stage, run its tests, lint and formatting checks, and the relevant smoke test.
- Support experimental claims with saved outputs, configs, hashes, tests, or other auditable evidence.

## Git boundaries

- Follow the branch and stage structure in `GOAL.md`.
- Do not rewrite history that has already been pushed.
- Remote actions must stay within the repository and workflow explicitly authorized by the user and `GOAL.md`.
- Never merge a pull request, push directly to `main`, publish a release, or create a release tag without current explicit user approval.
- Update `PROGRESS.md` at each stage, but record a commit SHA only after the commit actually exists.
- If authentication, repository access, branch protection, or CI prevents synchronization, preserve local work and record the exact blocker.

## Source of truth

- For algorithm and experiment definitions, `GOAL.md` is authoritative.
- For current stage status, `PROGRESS.md` is authoritative.
- A current explicit user instruction overrides repository guidance when they conflict.
