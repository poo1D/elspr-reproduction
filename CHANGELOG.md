# Changelog

All notable project changes are documented here.

## Unreleased

### Added

- Project specification, progress tracking, and reproducibility boundaries.
- Python package skeleton, configuration files, tests, and continuous
  integration.
- Strict response, judgment, pair-relation, and graph schemas with JSONL/JSON
  serialization.
- Dual-order aggregation, complete tournament construction, Tarjan SCC
  analysis, directed structural entropy, SCC reconstruction, and conservative
  data filtering.
- Artifact-producing `build-graphs`, `analyze`, `filter`, `toy-pipeline`, and
  `report` commands.
- Deterministic SVG visualizations for original and reconstructed graphs,
  including explicit worse-to-better and bidirectional-tie arrows.
- Per-question SCC partitions and reconstructed graph JSON/SVG artifacts in
  the general CLI pipeline.
- A 70-test Level 1 suite and public reproduction report.
- Selective checksum-verified preparation of a pinned five-model,
  50-question Level 2 response subset.
- A committed source/selection/derived-artifact manifest without vendored
  upstream responses.
- Deterministic rendering of all 1,000 ordered judge requests with stable
  pair/request IDs and a zero-paid-call token-estimate report.
- A budget-capped, cached, rate-limited, retrying, resumable DashScope executor
  that retains every raw attempt and never stores its API key.
- An 87-test suite covering Level 1 and the current Level 2 preparation path.
