"""Pairwise judging and aggregation."""

from elspr.judging.aggregation import (
    IncompleteJudgmentsError,
    aggregate_pair_judgments,
)

__all__ = ["IncompleteJudgmentsError", "aggregate_pair_judgments"]
