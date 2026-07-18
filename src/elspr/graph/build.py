"""Build complete tie-aware preference tournaments."""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

import networkx as nx

from elspr.schemas import PairRelation, PairRelationLabel


class IncompleteQuestionError(ValueError):
    """Raised when pair relations do not define one complete question graph."""


@dataclass(frozen=True, slots=True)
class QuestionGraph:
    """A validated preference graph for one question."""

    question_id: str
    graph: nx.DiGraph


def build_question_graph(
    relations: Iterable[PairRelation],
    *,
    expected_models: Iterable[str] | None = None,
) -> QuestionGraph:
    """Build a complete graph with edges directed from worse to better.

    A tie is represented with two directed edges. The function validates that
    exactly one relation exists for every unordered model pair.
    """

    relation_list = list(relations)
    if not relation_list:
        raise IncompleteQuestionError("at least one pair relation is required")

    question_ids = {item.question_id for item in relation_list}
    if len(question_ids) != 1:
        raise IncompleteQuestionError(
            f"expected one question_id, found {sorted(question_ids)}"
        )
    question_id = next(iter(question_ids))

    relation_by_pair: dict[tuple[str, str], PairRelation] = {}
    observed_models: set[str] = set()
    for relation in relation_list:
        pair = (relation.model_a, relation.model_b)
        if pair in relation_by_pair:
            pair_name = f"{relation.model_a}/{relation.model_b}"
            raise IncompleteQuestionError(
                f"{question_id}: duplicate relation for {pair_name}"
            )
        relation_by_pair[pair] = relation
        observed_models.update(pair)

    models = set(expected_models) if expected_models is not None else observed_models
    if not models:
        raise IncompleteQuestionError(f"{question_id}: expected_models is empty")
    unexpected = observed_models - models
    if unexpected:
        raise IncompleteQuestionError(
            f"{question_id}: unexpected models {sorted(unexpected)}"
        )

    required_pairs = set(combinations(sorted(models), 2))
    actual_pairs = set(relation_by_pair)
    missing_pairs = sorted(required_pairs - actual_pairs)
    extra_pairs = sorted(actual_pairs - required_pairs)
    if missing_pairs or extra_pairs:
        raise IncompleteQuestionError(
            f"{question_id}: incomplete tournament; "
            f"missing={missing_pairs}, extra={extra_pairs}"
        )

    graph = nx.DiGraph(question_id=question_id, complete=True)
    graph.add_nodes_from(sorted(models))
    for pair in sorted(required_pairs):
        relation = relation_by_pair[pair]
        model_a, model_b = pair
        if relation.relation is PairRelationLabel.A_OVER_B:
            graph.add_edge(model_b, model_a, relation="preference")
        elif relation.relation is PairRelationLabel.B_OVER_A:
            graph.add_edge(model_a, model_b, relation="preference")
        else:
            graph.add_edge(model_a, model_b, relation="tie")
            graph.add_edge(model_b, model_a, relation="tie")

    return QuestionGraph(question_id=question_id, graph=graph)
