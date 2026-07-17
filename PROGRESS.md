# Reproduction Progress

| Stage | Status | Branch | Commit | Tests | Main result | Deviations |
|---|---|---|---|---|---|---|
| 0. Bootstrap | done | `main` | `f7701cdac473aad2632f1d6eac2ed0cfa050f556` | passed | Reproducible Python 3.11 project initialized | Missing supplementary assets documented |
| 1. Pair aggregation | done | `repro/level-1` | `2b8c3854f416491b3974699d9412f82b543e161a` | 11 passed | Strict schemas and deterministic dual-order aggregation | Invalid, missing, and duplicate orders are rejected |
| 2. Graph construction | done | `repro/level-1` | pending post-push record | 20 passed | Complete tie-aware tournament graph builder | Incomplete questions are rejected |
| 3. SCC analysis | in_progress | `repro/level-1` | - | not run | Implementing Tarjan SCC metrics | - |
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
- Commit: `f7701cdac473aad2632f1d6eac2ed0cfa050f556`
- Scope: repository skeleton, packaging, configuration, CI, and baseline documentation
- Tests: `uv run pytest`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run elspr version`; `uv lock --check`
- Result: all checks pass with Python 3.11.13; project installs through the uv build backend
- Paper assumptions/deviations: Equation 3 numerator semantics, tie-aware quotient DAG, `g_j` edge selection, and missing supplementary assets are documented in `REPRODUCIBILITY.md`
- Next: implement stable JSONL schemas and dual-order pair aggregation

## Stage 1 - Pair aggregation

- Status: `done`
- Completed: 2026-07-18
- Commit: `2b8c3854f416491b3974699d9412f82b543e161a`
- Tests: `.venv/bin/pytest tests/test_pair_aggregation.py tests/test_package.py`
- Result: 11 tests pass; canonical pair ordering, position-bias ties, explicit ties, invalid judgments, missing swapped orders, and duplicate orders are covered
- Paper assumptions/deviations: unlike the paper's binary judge notation, the stable schema retains explicit `tie` and `invalid` states so failures remain auditable
- Next: build complete tie-aware tournament graphs and reject incomplete questions

## Stage 2 - Graph construction

- Status: `done`
- Completed: 2026-07-18
- Commit: pending post-push record
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 20 tests pass; strict preference direction, reverse preference, bidirectional tie, completeness, expected response models, duplicates, and question isolation are covered
- Paper assumptions/deviations: graph completeness is enforced before analysis instead of silently filling missing judge results
- Next: implement Tarjan SCC decomposition and vertex-weighted non-transitivity metrics
