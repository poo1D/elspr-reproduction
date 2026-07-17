# ELSPR Reproduction

An auditable Python reproduction of **ELSPR: Evaluator LLM Training Data
Self-Purification on Non-Transitive Preferences via Tournament Graph
Reconstruction**.

The project is intentionally staged:

- **Level 1:** algorithmic reproduction with deterministic toy data
- **Level 2:** small-scale empirical reproduction
- **Level 3:** paper-number reproduction when the missing supplementary assets
  are available

The implementation follows one critical edge convention: an edge points from
the worse response to the better response, so node in-degree is its win count.
Ties are represented by two directed edges.

## Level 1 method

For every unordered response pair, the pipeline requires judgments in both
presentation orders. Complementary `win/lose` outcomes produce one preference
edge; any other valid combination produces a bidirectional tie. Missing,
invalid, or duplicate orders reject the question rather than silently filling
the graph.

Tarjan SCC analysis marks a component non-transitive only when it has more than
two nodes and is not an all-pairs tie. The dataset metric is vertex-weighted:

```text
rho_non_trans =
  nodes in non-transitive SCCs across questions
  / all nodes across questions
```

The directed two-dimensional structural entropy implementation follows
Equation 4 of the paper. SCC volume is the sum of node in-degrees. The external
term excludes only edges between two singleton SCCs. Per-question entropy is
normalized as `tau = H2 / log2(|V|)`, and `tau_avg` is the unweighted question
mean. Empty graphs, single-node graphs, and zero-volume graphs return zero;
values are not clipped, and an out-of-range result emits a warning.

Reconstruction freezes each node's original global in-degree, replaces
internal SCC edges with degree-ranked edges, and preserves SCC-external edges.
Equal scores remain bidirectional ties. The raw reconstructed `DiGraph` can
therefore contain two-cycles; the graph obtained by contracting tie
equivalence classes is required to be a DAG.

## Development

Requirements: `uv` and Python 3.11 or newer.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

If editable imports fail on macOS because `.pth` files have the `UF_HIDDEN`
flag, use the audited workaround documented in `REPRODUCIBILITY.md`.

The complete target behavior is specified in [`GOAL.md`](GOAL.md), current
status in [`PROGRESS.md`](PROGRESS.md), and paper ambiguities in
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## CLI

Run all five deterministic cases and generate a Markdown report:

```bash
uv run elspr toy-pipeline --output-dir artifacts/toy
uv run elspr report --run-dir artifacts/toy
```

Run the Level 1 stages on validated judgment JSONL:

```bash
uv run elspr build-graphs \
  --judgments artifacts/judgments.jsonl \
  --output-dir artifacts/graphs
uv run elspr analyze \
  --graphs artifacts/graphs \
  --output artifacts/analysis.json
uv run elspr filter \
  --graphs artifacts/graphs \
  --judgments artifacts/judgments.jsonl \
  --output-dir artifacts/filtered
```

`build-graphs` rejects incomplete dual-order pairs. `filter` reconstructs every
graph before writing `cleaned.jsonl`, `discarded.jsonl`, and auditable decisions.
Judge API, training, and empirical evaluation commands belong to Level 2 and
are not represented as completed functionality in Level 1.

## Verified Level 1 result

Level 1 has 67 deterministic tests covering the five required toy cases and
the CLI pipeline. The detailed results and reproducibility boundaries are in
[`reports/LEVEL_1_REPORT.md`](reports/LEVEL_1_REPORT.md).

## License

Code in this repository is released under the MIT License. The source paper,
datasets, model outputs, and model weights retain their original licenses and
are not redistributed by this repository.
