"""Split ordered judgments into cleaned and discarded records."""

from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

from elspr.schemas import JudgmentRecord, Outcome


class FilteringError(ValueError):
    """Raised when a reconstructed graph cannot label a judgment."""


@dataclass(frozen=True, slots=True)
class FilterDecision:
    """Auditable decision for one ordered judgment."""

    judgment: JudgmentRecord
    target: Outcome
    kept: bool
    reason: str


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Conservative split of all input judgments."""

    cleaned: tuple[JudgmentRecord, ...]
    discarded: tuple[JudgmentRecord, ...]
    decisions: tuple[FilterDecision, ...]


def target_outcome(
    graph: nx.DiGraph,
    *,
    left_model: str,
    right_model: str,
) -> Outcome:
    """Derive the ordered left-model label from a reconstructed graph."""

    if left_model not in graph or right_model not in graph:
        raise FilteringError(
            f"models absent from graph: left={left_model}, right={right_model}"
        )
    left_to_right = graph.has_edge(left_model, right_model)
    right_to_left = graph.has_edge(right_model, left_model)
    if left_to_right and right_to_left:
        return Outcome.TIE
    if right_to_left:
        return Outcome.WIN
    if left_to_right:
        return Outcome.LOSE
    raise FilteringError(f"no reconstructed relation for {left_model}/{right_model}")


def filter_question_judgments(
    graph: nx.DiGraph,
    judgments: Iterable[JudgmentRecord],
    *,
    question_id: str | None = None,
) -> FilterResult:
    """Keep judgments matching reconstructed targets and discard the rest."""

    records = list(judgments)
    expected_question = question_id or graph.graph.get("question_id")
    if expected_question is None and records:
        expected_question = records[0].question_id

    decisions: list[FilterDecision] = []
    cleaned: list[JudgmentRecord] = []
    discarded: list[JudgmentRecord] = []
    for judgment in records:
        if judgment.question_id != expected_question:
            raise FilteringError(
                f"expected question_id={expected_question}, "
                f"found {judgment.question_id}"
            )
        target = target_outcome(
            graph,
            left_model=judgment.left_model,
            right_model=judgment.right_model,
        )
        kept = judgment.status == "ok" and judgment.normalized_left_outcome is target
        reason = "matches_reconstruction" if kept else "label_mismatch"
        decision = FilterDecision(
            judgment=judgment,
            target=target,
            kept=kept,
            reason=reason,
        )
        decisions.append(decision)
        (cleaned if kept else discarded).append(judgment)

    if len(cleaned) + len(discarded) != len(records):
        raise AssertionError("filtering conservation invariant failed")
    return FilterResult(
        cleaned=tuple(cleaned),
        discarded=tuple(discarded),
        decisions=tuple(decisions),
    )
