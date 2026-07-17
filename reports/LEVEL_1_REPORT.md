# ELSPR Level 1 Reproduction Report

## Outcome

Level 1 of the ELSPR reproduction is complete. The repository implements and
tests the paper's core graph method without judge API calls, GPU training, or
hard-coded paper results.

The verified pipeline is:

```text
ordered judgments
  -> dual-order pair aggregation
  -> tie-aware tournament graph
  -> Tarjan SCC and structural entropy
  -> global-in-degree SCC reconstruction
  -> tie-class quotient DAG validation
  -> cleaned/discarded judgment split
```

## Environment and validation

- Date: 2026-07-18
- Python: 3.11.13
- Dependency manager: uv 0.7.19
- Tests: 67 passed
- Lint: Ruff passed
- Format: Ruff format check passed
- Lockfile: frozen sync and lock check passed
- Smoke test: all five toy cases and Markdown report generated successfully
- CI: GitHub Actions passed for both branch-push and Draft PR triggers at the
  Stage 8 implementation SHA

The clean local validation commands were:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/elspr-final-venv \
  uv sync --frozen --all-groups --no-editable --link-mode=copy
PYTHONPATH=src /tmp/elspr-final-venv/bin/ruff check .
PYTHONPATH=src /tmp/elspr-final-venv/bin/ruff format --check .
PYTHONPATH=src /tmp/elspr-final-venv/bin/pytest
PYTHONPATH=src /tmp/elspr-final-venv/bin/python -m elspr.cli \
  toy-pipeline --output-dir /tmp/elspr-level1-final
PYTHONPATH=src /tmp/elspr-final-venv/bin/python -m elspr.cli \
  report --run-dir /tmp/elspr-level1-final
uv lock --check
```

## Deterministic toy results

| Case | rho_non_trans | tau | Raw | Cleaned | Discarded |
|---|---:|---:|---:|---:|---:|
| Strict linear | 0.000000 | 0.000000 | 6 | 6 | 0 |
| Three-node cycle | 1.000000 | 1.000000 | 6 | 0 | 6 |
| All tie | 0.000000 | 1.000000 | 6 | 0 | 6 |
| Position bias | 0.000000 | 0.630930 | 6 | 4 | 2 |
| Unequal-score reconstruction | 1.000000 | 0.959148 | 12 | 6 | 6 |

These are synthetic verification values, not claims that the paper's empirical
tables were reproduced. The all-tie case demonstrates why SCC
non-transitivity and structural entropy are complementary: its
`rho_non_trans` is zero while `tau` is maximal.

## Required cases

### Case A - strict linear preference

All SCCs are singletons. Singleton-to-singleton external edges are excluded
from the entropy partition term, producing `rho_non_trans = 0` and `tau = 0`.
All six ordered judgments survive filtering.

### Case B - three-node cycle

Tarjan returns one three-node SCC containing non-reciprocal pairs. All three
nodes contribute to the numerator, producing `rho_non_trans = 1`. Equal
in-degrees reconstruct to one tie class, so the original binary labels are
discarded.

### Case C - all tie

The graph is one three-node SCC, but every pair is reciprocal and therefore is
not classified as non-transitive. Uniform in-degree yields maximal normalized
entropy.

### Case D - position bias

One pair receives the same left-side verdict in both presentation orders and
becomes a bidirectional tie. The two affected ordered labels are discarded;
the four stable labels are retained.

### Case E - reconstruction

The four-node SCC has original global in-degrees `{a: 2, b: 1, c: 2, d: 1}`.
Reconstruction produces tie classes `(a, c)` and `(b, d)`, with the sole
quotient edge `(b, d) -> (a, c)`. The quotient graph is a DAG, and exactly half
of the 12 raw ordered judgments match the reconstructed targets.

## Paper ambiguities resolved

1. Equation 3's numerator follows the prose: it sums vertices in qualifying
   SCCs rather than counting SCC objects.
2. A reconstructed graph with bidirectional ties is not a DAG in the ordinary
   `DiGraph` sense. Acyclicity is verified after contracting tie equivalence
   classes.
3. The entropy external-edge count excludes only singleton-to-singleton
   cross-SCC edges.
4. Zero-value conventions are explicit, and normalized entropy is not clipped.
5. Incomplete questions and invalid judgments are surfaced rather than
   silently imputed.

Further details and the source PDF checksum are recorded in
[`REPRODUCIBILITY.md`](../REPRODUCIBILITY.md).

## Scope boundary

This report establishes algorithm-level reproduction only. Level 2 still
requires a versioned AlpacaEval subset, judge execution or imported judgments,
and at least one raw/cleaned/random LoRA experiment.

After the original Level 1 implementation, the current AAAI-26 article, arXiv
v3 appendices, and author code/response repository were located. This removes
the prompt and public-code gaps, but Level 3 remains partially blocked because
the upstream repository does not publish the paper's judgment outputs,
raw/cleaned/random training artifacts, exact 14/7 model partition, training
implementation/configuration, checkpoints, or full evaluation provenance.
See [`UPSTREAM_AUDIT.md`](../UPSTREAM_AUDIT.md).
