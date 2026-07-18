# Upstream Asset Audit

## Verified sources

Audit date: 2026-07-18.

- AAAI-26 article:
  `https://ojs.aaai.org/index.php/AAAI/article/view/38857`
- arXiv v3:
  `https://arxiv.org/abs/2505.17691v3`
- arXiv v3 PDF SHA-256:
  `513d35266957129e79c42eb6517b88181ecb85d6d50f751042b2b391ba1e4810`
- Author repository: `https://github.com/yy0525/ELSPR`
- Audited author-repository commit:
  `e9886b3a96f71cee654e1c758d03a026f3cbc32f`
- Author-repository license: Apache-2.0

The local 10-page submission PDF predates the current 15-page arXiv v3 and
AAAI-26 publication. Current upstream sources supersede it for prompt,
appendix, and public-asset availability claims.

## Assets now available

- Appendix A filtering pseudocode.
- Appendix B additional prompt, base-model, and unseen-question results.
- Appendix C exact standard and tie-allowed CoT prompts.
- Author implementations for response selection, dual-order API judgment,
  tournament analysis, reconstruction/export, and training-set conversion.
- AlpacaEval response files under `data/selected_models/`.

The author repository contains 228 model directories and approximately
369,697,526 bytes of response JSON at the audited commit. It should be consumed
selectively or by a versioned downloader rather than vendored into this
repository.

## Assets still missing

The audited author repository does not contain:

- the raw Qwen2.5-Max judgment JSONL used for paper results;
- generated DAG result files;
- the exact raw/cleaned/random training datasets used for fine-tuning;
- the paper's exact 14 training-model and 7 testing-model partition;
- LoRA training code, optimizer/scheduler details, or complete distributed
  training configuration;
- trained checkpoints or per-run manifests;
- scripts reproducing MT-Bench, human agreement, Spearman, Self-BLEU, or all
  paper tables from raw artifacts.

Level 3 is therefore only partially unblocked. The public assets are enough to
remove the old "prompt unavailable" assumption and to ground Level 2 data
preparation, but not enough to reproduce every paper number.

## Paper-code discrepancies

The audited author code is valuable evidence but is not treated as an
unquestioned reference implementation:

1. The paper defines edges from worse to better. The author
   `TournamentGraph.add_edge(..., "win")` stores winner-to-loser edges.
2. The paper's entropy formula uses `log2` in both terms. The author code uses
   natural log for the internal term and `log2` for the external term.
3. The author entropy code increments `d_in[u]` for stored edge `u -> v`,
   effectively using stored out-degree as a win score.
4. The paper requires non-transitive SCC size greater than two. The author
   filtering helper excludes all-tie SCCs but does not explicitly apply the
   size condition.
5. The paper says SCC-external edges are preserved. The author
   `resolve_cycles` implementation rewrites adjacency lists for processed
   nodes, which can remove external outgoing edges.
6. The author non-transitivity denominator is hard-coded as
   `7 * question_count`, whereas this reproduction derives actual node counts.

This project continues to follow the published mathematical definitions and
keeps compatibility comparisons as a separate future audit, rather than
silently inheriting implementation inconsistencies.
