# Reproduction Progress

| Stage | Status | Branch | Commit | Tests | Main result | Deviations |
|---|---|---|---|---|---|---|
| 0. Bootstrap | done | `main` | `f7701cdac473aad2632f1d6eac2ed0cfa050f556` | passed | Reproducible Python 3.11 project initialized | Missing supplementary assets documented |
| 1. Pair aggregation | done | `repro/level-1` | `2b8c3854f416491b3974699d9412f82b543e161a` | 11 passed | Strict schemas and deterministic dual-order aggregation | Invalid, missing, and duplicate orders are rejected |
| 2. Graph construction | done | `repro/level-1` | `a1f8c03305b041e283f1f2c83543a42159e46df2` | 20 passed | Complete tie-aware tournament graph builder | Incomplete questions are rejected |
| 3. SCC analysis | done | `repro/level-1` | `f887495acd72f55274e23818021d0185f1ad8405` | 29 passed | Deterministic Tarjan SCC and vertex-weighted non-transitivity | All-pairs tie SCCs are excluded |
| 4. Structural entropy | done | `repro/level-1` | `df5e56a55316386db3c5dbffa5faf3117a88d369` | 39 passed | Directed H2, tau, and unweighted tau_avg | Zero-volume cases return zero; out-of-range values warn |
| 5. SCC reconstruction | done | `repro/level-1` | `c05cb6d93bef95718a5ba07cb7bd1fc2cbdc89b8` | 45 passed | Original-in-degree SCC reconstruction and quotient DAG | Equal scores remain bidirectional tie classes |
| 6. Data filtering | done | `repro/level-1` | pending post-push record | 54 passed | Conservative cleaned/discarded split with decisions | Invalid and binary-to-tie judgments are discarded |
| 7. Toy test suite | in_progress | `repro/level-1` | - | not run | Consolidating five required cases and end-to-end invariants | - |
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
- Commit: `a1f8c03305b041e283f1f2c83543a42159e46df2`
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 20 tests pass; strict preference direction, reverse preference, bidirectional tie, completeness, expected response models, duplicates, and question isolation are covered
- Paper assumptions/deviations: graph completeness is enforced before analysis instead of silently filling missing judge results
- Next: implement Tarjan SCC decomposition and vertex-weighted non-transitivity metrics

## Stage 3 - SCC analysis

- Status: `done`
- Completed: 2026-07-18
- Commit: `f887495acd72f55274e23818021d0185f1ad8405`
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_scc_metrics.py tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 29 tests pass; deterministic Tarjan output matches NetworkX partitions and Cases A-C plus mixed position-bias and dataset weighting are covered
- Paper assumptions/deviations: Equation 3 is implemented as the number of vertices in qualifying SCCs divided by all vertices, following the paper's prose rather than counting SCC objects
- Next: implement directed two-dimensional structural entropy and normalization edge cases

## Stage 4 - Structural entropy

- Status: `done`
- Completed: 2026-07-18
- Commit: `df5e56a55316386db3c5dbffa5faf3117a88d369`
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_entropy.py tests/test_scc_metrics.py tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 39 tests pass; linear, cycle, all-tie, singleton-to-multi, multi-to-singleton, empty, zero-volume, and dataset-average cases are covered
- Paper assumptions/deviations: `g_j` excludes only singleton-to-singleton cross-SCC edges; tau is not clipped and emits a warning if numerical or formula behavior leaves [0, 1]
- Next: reconstruct SCC internals from original global in-degree and validate the tie-quotient DAG

## Stage 5 - SCC reconstruction

- Status: `done`
- Completed: 2026-07-18
- Commit: `c05cb6d93bef95718a5ba07cb7bd1fc2cbdc89b8`
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_reconstruction.py tests/test_entropy.py tests/test_scc_metrics.py tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 45 tests pass; unequal and equal in-degree cycles, preserved inter-SCC edges, immutability, isolated nodes, edge provenance, and quotient acyclicity are covered
- Paper assumptions/deviations: the reconstructed ordinary graph may contain reciprocal tie edges; the contracted tie-class quotient, not the raw DiGraph, is required to be a DAG
- Next: derive ordered target labels and split raw judgments into cleaned and discarded sets

## Stage 6 - Data filtering

- Status: `done`
- Completed: 2026-07-18
- Commit: pending post-push record
- Tests: `PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest tests/test_filtering.py tests/test_reconstruction.py tests/test_entropy.py tests/test_scc_metrics.py tests/test_graph_build.py tests/test_pair_aggregation.py tests/test_package.py`
- Result: 54 tests pass; ordered win/lose targets, explicit ties, binary-to-tie discard, invalid input, question isolation, missing relations, and count conservation are covered
- Paper assumptions/deviations: original records are never relabeled; every input appears exactly once in cleaned or discarded with an auditable decision
- Next: consolidate the five required toy cases and assert cross-module end-to-end invariants
