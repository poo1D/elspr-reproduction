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

The `elspr` command is installed by the package. Stage 8 will expose the full
toy pipeline and the data, graph, filtering, training, evaluation, and report
commands defined by the project specification.

## License

Code in this repository is released under the MIT License. The source paper,
datasets, model outputs, and model weights retain their original licenses and
are not redistributed by this repository.
