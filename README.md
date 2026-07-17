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

## License

Code in this repository is released under the MIT License. The source paper,
datasets, model outputs, and model weights retain their original licenses and
are not redistributed by this repository.
