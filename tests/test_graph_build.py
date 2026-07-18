import networkx as nx
import pytest

from elspr.graph import IncompleteQuestionError, build_question_graph
from elspr.schemas import Outcome, PairRelation, PairRelationLabel


def pair(
    model_a: str,
    model_b: str,
    relation: PairRelationLabel,
    *,
    question_id: str = "q_1",
) -> PairRelation:
    outcomes = {
        PairRelationLabel.A_OVER_B: (Outcome.WIN, Outcome.LOSE),
        PairRelationLabel.B_OVER_A: (Outcome.LOSE, Outcome.WIN),
        PairRelationLabel.TIE: (Outcome.WIN, Outcome.WIN),
    }
    j_ab, j_ba = outcomes[relation]
    return PairRelation(
        question_id=question_id,
        model_a=model_a,
        model_b=model_b,
        j_ab=j_ab,
        j_ba=j_ba,
        relation=relation,
    )


def test_edges_point_from_worse_to_better() -> None:
    result = build_question_graph([pair("a", "b", PairRelationLabel.A_OVER_B)])

    assert set(result.graph.edges) == {("b", "a")}
    assert result.graph.in_degree("a") == 1
    assert result.graph.in_degree("b") == 0


def test_b_over_a_reverses_preference_edge() -> None:
    result = build_question_graph([pair("a", "b", PairRelationLabel.B_OVER_A)])

    assert set(result.graph.edges) == {("a", "b")}


def test_tie_uses_two_directed_edges() -> None:
    result = build_question_graph([pair("a", "b", PairRelationLabel.TIE)])

    assert set(result.graph.edges) == {("a", "b"), ("b", "a")}
    assert all(data["relation"] == "tie" for *_, data in result.graph.edges(data=True))


def test_complete_three_model_tournament() -> None:
    result = build_question_graph(
        [
            pair("a", "b", PairRelationLabel.A_OVER_B),
            pair("a", "c", PairRelationLabel.TIE),
            pair("b", "c", PairRelationLabel.B_OVER_A),
        ]
    )

    assert set(result.graph.nodes) == {"a", "b", "c"}
    assert result.graph.number_of_edges() == 4
    assert nx.is_weakly_connected(result.graph)
    assert result.graph.graph == {"question_id": "q_1", "complete": True}


def test_missing_pair_is_rejected() -> None:
    with pytest.raises(IncompleteQuestionError, match="missing=.*b.*,.*c"):
        build_question_graph(
            [
                pair("a", "b", PairRelationLabel.A_OVER_B),
                pair("a", "c", PairRelationLabel.A_OVER_B),
            ]
        )


def test_expected_models_detects_unobserved_response() -> None:
    with pytest.raises(IncompleteQuestionError, match="missing"):
        build_question_graph(
            [pair("a", "b", PairRelationLabel.A_OVER_B)],
            expected_models=["a", "b", "c"],
        )


def test_duplicate_pair_is_rejected() -> None:
    relation = pair("a", "b", PairRelationLabel.A_OVER_B)
    with pytest.raises(IncompleteQuestionError, match="duplicate relation"):
        build_question_graph([relation, relation])


def test_mixed_questions_are_rejected() -> None:
    with pytest.raises(IncompleteQuestionError, match="expected one question_id"):
        build_question_graph(
            [
                pair("a", "b", PairRelationLabel.A_OVER_B, question_id="q_1"),
                pair("a", "c", PairRelationLabel.A_OVER_B, question_id="q_2"),
            ]
        )


def test_empty_relations_are_rejected() -> None:
    with pytest.raises(IncompleteQuestionError, match="at least one"):
        build_question_graph([])
