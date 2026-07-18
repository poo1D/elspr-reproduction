from datetime import UTC, datetime

import pytest

from elspr.judging import IncompleteJudgmentsError, aggregate_pair_judgments
from elspr.schemas import (
    JudgmentRecord,
    Outcome,
    PairRelationLabel,
)


def judgment(
    left: str,
    right: str,
    outcome: Outcome,
    *,
    question_id: str = "q_0001",
    status: str = "ok",
) -> JudgmentRecord:
    return JudgmentRecord(
        question_id=question_id,
        left_model=left,
        right_model=right,
        left_response=f"{left} response",
        right_response=f"{right} response",
        verdict=outcome.value,
        normalized_left_outcome=outcome,
        judge_model="judge",
        prompt_template_id="cot_v1",
        raw_output=outcome.value,
        status=status,
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (Outcome.WIN, Outcome.LOSE, PairRelationLabel.A_OVER_B),
        (Outcome.LOSE, Outcome.WIN, PairRelationLabel.B_OVER_A),
        (Outcome.WIN, Outcome.WIN, PairRelationLabel.TIE),
        (Outcome.LOSE, Outcome.LOSE, PairRelationLabel.TIE),
        (Outcome.TIE, Outcome.TIE, PairRelationLabel.TIE),
    ],
)
def test_aggregate_dual_order_relation(
    first: Outcome,
    second: Outcome,
    expected: PairRelationLabel,
) -> None:
    relation = aggregate_pair_judgments(
        [judgment("model_a", "model_b", first), judgment("model_b", "model_a", second)]
    )[0]

    assert relation.model_a == "model_a"
    assert relation.model_b == "model_b"
    assert relation.j_ab is first
    assert relation.j_ba is second
    assert relation.relation is expected


def test_aggregation_is_deterministic_and_canonical() -> None:
    relations = aggregate_pair_judgments(
        [
            judgment("z_model", "a_model", Outcome.LOSE, question_id="q_2"),
            judgment("a_model", "z_model", Outcome.WIN, question_id="q_2"),
            judgment("b_model", "a_model", Outcome.LOSE, question_id="q_1"),
            judgment("a_model", "b_model", Outcome.WIN, question_id="q_1"),
        ]
    )

    assert [(item.question_id, item.model_a, item.model_b) for item in relations] == [
        ("q_1", "a_model", "b_model"),
        ("q_2", "a_model", "z_model"),
    ]


def test_missing_swapped_order_is_rejected() -> None:
    with pytest.raises(IncompleteJudgmentsError, match="expected one B/A order"):
        aggregate_pair_judgments([judgment("model_a", "model_b", Outcome.WIN)])


def test_duplicate_order_is_rejected() -> None:
    with pytest.raises(
        IncompleteJudgmentsError,
        match="expected one A/B order, found 2",
    ):
        aggregate_pair_judgments(
            [
                judgment("model_a", "model_b", Outcome.WIN),
                judgment("model_a", "model_b", Outcome.WIN),
                judgment("model_b", "model_a", Outcome.LOSE),
            ]
        )


def test_invalid_judgment_is_rejected() -> None:
    with pytest.raises(IncompleteJudgmentsError, match="contains invalid judgment"):
        aggregate_pair_judgments(
            [
                judgment(
                    "model_a",
                    "model_b",
                    Outcome.INVALID,
                    status="invalid",
                ),
                judgment("model_b", "model_a", Outcome.LOSE),
            ]
        )


def test_schema_rejects_inconsistent_invalid_status() -> None:
    with pytest.raises(ValueError, match="status='ok'"):
        judgment("model_a", "model_b", Outcome.INVALID)
