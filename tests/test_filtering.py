from datetime import UTC, datetime

import networkx as nx
import pytest

from elspr.filtering import (
    FilteringError,
    filter_question_judgments,
    target_outcome,
)
from elspr.schemas import JudgmentRecord, Outcome


def judgment(
    left: str,
    right: str,
    outcome: Outcome,
    *,
    question_id: str = "q_1",
    status: str = "ok",
) -> JudgmentRecord:
    return JudgmentRecord(
        question_id=question_id,
        left_model=left,
        right_model=right,
        left_response=left,
        right_response=right,
        verdict=outcome.value,
        normalized_left_outcome=outcome,
        judge_model="judge",
        prompt_template_id="cot_v1",
        raw_output=outcome.value,
        status=status,
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


def test_target_labels_follow_worse_to_better_edge_direction() -> None:
    graph = nx.DiGraph([("b", "a")])

    assert target_outcome(graph, left_model="a", right_model="b") is Outcome.WIN
    assert target_outcome(graph, left_model="b", right_model="a") is Outcome.LOSE


def test_matching_directional_judgments_are_cleaned() -> None:
    graph = nx.DiGraph([("b", "a")], question_id="q_1")
    records = [
        judgment("a", "b", Outcome.WIN),
        judgment("b", "a", Outcome.LOSE),
    ]

    result = filter_question_judgments(graph, records)

    assert result.cleaned == tuple(records)
    assert result.discarded == ()
    assert all(item.kept for item in result.decisions)


def test_mismatched_directional_judgments_are_discarded() -> None:
    graph = nx.DiGraph([("b", "a")], question_id="q_1")
    records = [
        judgment("a", "b", Outcome.LOSE),
        judgment("b", "a", Outcome.WIN),
    ]

    result = filter_question_judgments(graph, records)

    assert result.cleaned == ()
    assert result.discarded == tuple(records)


def test_binary_judgments_are_discarded_when_target_is_tie() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "a")], question_id="q_1")
    records = [
        judgment("a", "b", Outcome.WIN),
        judgment("b", "a", Outcome.LOSE),
    ]

    result = filter_question_judgments(graph, records)

    assert [item.target for item in result.decisions] == [Outcome.TIE, Outcome.TIE]
    assert result.discarded == tuple(records)


def test_explicit_tie_is_cleaned() -> None:
    graph = nx.DiGraph([("a", "b"), ("b", "a")], question_id="q_1")
    record = judgment("a", "b", Outcome.TIE)

    result = filter_question_judgments(graph, [record])

    assert result.cleaned == (record,)


def test_invalid_judgment_is_discarded() -> None:
    graph = nx.DiGraph([("b", "a")], question_id="q_1")
    record = judgment("a", "b", Outcome.INVALID, status="invalid")

    result = filter_question_judgments(graph, [record])

    assert result.discarded == (record,)
    assert not result.decisions[0].kept


def test_filtering_preserves_record_count() -> None:
    graph = nx.DiGraph(
        [("b", "a"), ("a", "c"), ("c", "a")],
        question_id="q_1",
    )
    records = [
        judgment("a", "b", Outcome.WIN),
        judgment("b", "a", Outcome.WIN),
        judgment("a", "c", Outcome.TIE),
    ]

    result = filter_question_judgments(graph, records)

    assert len(result.cleaned) + len(result.discarded) == len(records)
    assert len(result.decisions) == len(records)


def test_wrong_question_is_rejected() -> None:
    graph = nx.DiGraph([("b", "a")], question_id="q_1")

    with pytest.raises(FilteringError, match="expected question_id=q_1"):
        filter_question_judgments(
            graph,
            [judgment("a", "b", Outcome.WIN, question_id="q_2")],
        )


def test_absent_model_and_missing_relation_are_rejected() -> None:
    graph = nx.DiGraph()
    graph.add_nodes_from(["a", "b", "c"])

    with pytest.raises(FilteringError, match="absent"):
        target_outcome(graph, left_model="a", right_model="missing")
    with pytest.raises(FilteringError, match="no reconstructed relation"):
        target_outcome(graph, left_model="a", right_model="b")
