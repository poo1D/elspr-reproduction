# Reproducibility Notes

## Source artifact

The original local source reviewed for Level 1 is:

- Title: *ELSPR: Evaluator LLM Training Data Self-Purification on
  Non-Transitive Preferences via Tournament Graph Reconstruction*
- Local filename: `paper-submission-26547 2.pdf`
- SHA-256:
  `45df5c6a4fa46cce2b9d2189a86b82b0b6bb5b97709de08cfaa3f2502848cfcb`
- PDF metadata: 10 pages, created 2025-08-02

The PDF is not committed because the repository does not establish a
redistribution license for it.

On 2026-07-18, the current AAAI-26 article, 15-page arXiv v3, and author
repository became available during the reproduction audit. The current source
inventory, pinned hashes, available assets, missing artifacts, and paper-code
discrepancies are recorded in [`UPSTREAM_AUDIT.md`](UPSTREAM_AUDIT.md).

## Confirmed method details

- Edges point from the worse response to the better response.
- Each response pair is judged in both presentation orders.
- Inconsistent order results become a bidirectional tie.
- Non-transitive SCCs contain more than two vertices and are not all-pairs ties.
- SCC reconstruction ranks vertices by in-degree in the original global graph.
- Reported LoRA settings are rank 8, 3 epochs, learning rate `1e-4`, batch size
  16, and two A100 GPUs.

## Assumptions and deviations

1. Equation 3 writes `|S_n-t(G_i)|` while its prose says the numerator is the
   number of vertices in non-transitive SCCs. The implementation follows the
   prose and sums SCC sizes.
2. Section 3.3 calls the reconstructed graph a DAG while retaining
   bidirectional ties. The implementation treats tied vertices as equivalence
   classes and requires the quotient graph to be acyclic.
3. Section 3.2 describes `g_j` in prose. The implementation excludes only
   edges whose source and target SCCs are both singletons, matching that prose.
4. The original 10-page PDF lacked its referenced appendices. arXiv v3 now
   supplies filtering pseudocode, additional results, and exact prompt text.
5. The author repository now supplies code and model-response data, but not
   paper judgment outputs, training datasets, the exact 14/7 model partition,
   training code/configuration, checkpoints, or complete evaluation scripts.
6. Level 3 remains partially blocked by the missing run artifacts and training
   provenance listed in `UPSTREAM_AUDIT.md`; Level 2 can now use the pinned
   public response data and exact prompt instead of placeholders.

## Local environment note

On the development Mac (macOS 26.3), files inside a repository-local `.venv`
under Desktop can inherit `UF_HIDDEN` and provenance metadata. Python 3.11.13
then skips editable-install `.pth` files or reads copied packages very slowly.
The verified local workaround is to keep the disposable environment in `/tmp`:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/elspr-reproduction-venv \
  uv sync --all-groups --no-editable --link-mode=copy
PYTHONPATH=src /tmp/elspr-reproduction-venv/bin/pytest
```

This installs the package directory outside the affected Desktop tree and uses
the current source checkout explicitly. Ubuntu GitHub Actions does not use this
macOS filesystem behavior.
