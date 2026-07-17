# Reproducibility Notes

## Source artifact

The local source reviewed for this reproduction is:

- Title: *ELSPR: Evaluator LLM Training Data Self-Purification on
  Non-Transitive Preferences via Tournament Graph Reconstruction*
- Local filename: `paper-submission-26547 2.pdf`
- SHA-256:
  `45df5c6a4fa46cce2b9d2189a86b82b0b6bb5b97709de08cfaa3f2502848cfcb`
- PDF metadata: 10 pages, created 2025-08-02

The PDF is not committed because the repository does not establish a
redistribution license for it.

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
4. The provided 10-page PDF references Appendix C, Appendix D, Appendix G, and
   supplementary code/data that are not included. Exact model lists, prompt
   text, splits, and some evaluation details remain unavailable.
5. Until the supplementary assets are recovered, Level 3 is blocked and Level
   2 uses explicit, versioned substitute configurations.
