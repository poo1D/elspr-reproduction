# Reproduction Progress

| Stage | Status | Branch | Commit | Tests | Main result | Deviations |
|---|---|---|---|---|---|---|
| 0. Bootstrap | done | `main` | pending post-push record | passed | Reproducible Python 3.11 project initialized | Missing supplementary assets documented |
| 1. Pair aggregation | in_progress | `repro/level-1` | - | not run | Implementing stable JSONL schemas and dual-order aggregation | - |
| 2. Graph construction | not_started | `repro/level-1` | - | - | - | - |
| 3. SCC analysis | not_started | `repro/level-1` | - | - | - | - |
| 4. Structural entropy | not_started | `repro/level-1` | - | - | - | - |
| 5. SCC reconstruction | not_started | `repro/level-1` | - | - | - | - |
| 6. Data filtering | not_started | `repro/level-1` | - | - | - | - |
| 7. Toy test suite | not_started | `repro/level-1` | - | - | - | - |
| 8. CLI and toy pipeline | not_started | `repro/level-1` | - | - | - | - |
| 9. Level 1 report | not_started | `repro/level-1` | - | - | - | - |

## Stage 0 - Bootstrap

- Status: `done`
- Started: 2026-07-18
- Completed: 2026-07-18
- Commit: pending post-push record
- Scope: repository skeleton, packaging, configuration, CI, and baseline documentation
- Tests: `uv run pytest`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run elspr version`; `uv lock --check`
- Result: all checks pass with Python 3.11.13; project installs through the uv build backend
- Paper assumptions/deviations: Equation 3 numerator semantics, tie-aware quotient DAG, `g_j` edge selection, and missing supplementary assets are documented in `REPRODUCIBILITY.md`
- Next: implement stable JSONL schemas and dual-order pair aggregation
