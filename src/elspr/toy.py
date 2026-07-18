"""Deterministic toy cases spanning the complete Level 1 method."""

from dataclasses import dataclass
from datetime import UTC, datetime

from elspr.filtering import FilterResult, filter_question_judgments
from elspr.graph import (
    EntropyAnalysis,
    QuestionGraph,
    ReconstructionResult,
    SCCAnalysis,
    analyze_scc,
    build_question_graph,
    reconstruct_sccs,
    structural_entropy,
)
from elspr.judging import aggregate_pair_judgments
from elspr.schemas import JudgmentRecord, Outcome, PairRelationLabel

TOY_CASES = ("linear", "cycle", "all_tie", "position_bias", "reconstruction")


@dataclass(frozen=True, slots=True)
class ToyRun:
    """All auditable outputs for a toy case."""

    case: str
    judgments: tuple[JudgmentRecord, ...]
    question_graph: QuestionGraph
    scc: SCCAnalysis
    entropy: EntropyAnalysis
    reconstruction: ReconstructionResult
    filtering: FilterResult


def _judgment(
    left: str,
    right: str,
    outcome: Outcome,
    *,
    question_id: str,
) -> JudgmentRecord:
    return JudgmentRecord(
        question_id=question_id,
        left_model=left,
        right_model=right,
        left_response=f"{left} response",
        right_response=f"{right} response",
        verdict=outcome.value,
        normalized_left_outcome=outcome,
        judge_model="toy-judge",
        prompt_template_id="toy-v1",
        raw_output=outcome.value,
        status="ok",
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


def _dual_order(
    model_a: str,
    model_b: str,
    relation: PairRelationLabel,
    *,
    question_id: str,
) -> tuple[JudgmentRecord, JudgmentRecord]:
    outcomes = {
        PairRelationLabel.A_OVER_B: (Outcome.WIN, Outcome.LOSE),
        PairRelationLabel.B_OVER_A: (Outcome.LOSE, Outcome.WIN),
        PairRelationLabel.TIE: (Outcome.WIN, Outcome.WIN),
    }
    j_ab, j_ba = outcomes[relation]
    return (
        _judgment(model_a, model_b, j_ab, question_id=question_id),
        _judgment(model_b, model_a, j_ba, question_id=question_id),
    )


def toy_judgments(case: str) -> tuple[JudgmentRecord, ...]:
    """Return fixed dual-order judgments for one named toy case."""

    definitions: dict[
        str,
        tuple[tuple[str, str, PairRelationLabel], ...],
    ] = {
        "linear": (
            ("a", "b", PairRelationLabel.A_OVER_B),
            ("a", "c", PairRelationLabel.A_OVER_B),
            ("b", "c", PairRelationLabel.A_OVER_B),
        ),
        "cycle": (
            ("a", "b", PairRelationLabel.A_OVER_B),
            ("a", "c", PairRelationLabel.B_OVER_A),
            ("b", "c", PairRelationLabel.A_OVER_B),
        ),
        "all_tie": (
            ("a", "b", PairRelationLabel.TIE),
            ("a", "c", PairRelationLabel.TIE),
            ("b", "c", PairRelationLabel.TIE),
        ),
        "position_bias": (
            ("a", "b", PairRelationLabel.TIE),
            ("a", "c", PairRelationLabel.A_OVER_B),
            ("b", "c", PairRelationLabel.A_OVER_B),
        ),
        "reconstruction": (
            ("a", "b", PairRelationLabel.B_OVER_A),
            ("a", "c", PairRelationLabel.A_OVER_B),
            ("a", "d", PairRelationLabel.A_OVER_B),
            ("b", "c", PairRelationLabel.B_OVER_A),
            ("b", "d", PairRelationLabel.B_OVER_A),
            ("c", "d", PairRelationLabel.A_OVER_B),
        ),
    }
    if case not in definitions:
        raise ValueError(f"unknown toy case {case!r}; expected one of {TOY_CASES}")

    question_id = f"toy_{case}"
    return tuple(
        judgment
        for model_a, model_b, relation in definitions[case]
        for judgment in _dual_order(
            model_a,
            model_b,
            relation,
            question_id=question_id,
        )
    )


def run_toy_case(case: str) -> ToyRun:
    """Run one deterministic case through the complete Level 1 method."""

    judgments = toy_judgments(case)
    relations = aggregate_pair_judgments(judgments)
    question_graph = build_question_graph(relations)
    scc = analyze_scc(question_graph.graph)
    entropy = structural_entropy(question_graph.graph)
    reconstruction = reconstruct_sccs(question_graph.graph)
    filtering = filter_question_judgments(
        reconstruction.graph,
        judgments,
        question_id=question_graph.question_id,
    )
    return ToyRun(
        case=case,
        judgments=judgments,
        question_graph=question_graph,
        scc=scc,
        entropy=entropy,
        reconstruction=reconstruction,
        filtering=filtering,
    )
