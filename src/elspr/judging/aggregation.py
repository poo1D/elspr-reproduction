"""Aggregate position-swapped judgments into unordered pair relations."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from elspr.schemas import (
    JudgmentRecord,
    Outcome,
    PairRelation,
    PairRelationLabel,
)

PairKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class PairIssue:
    """Why an unordered pair could not be aggregated."""

    question_id: str
    model_a: str
    model_b: str
    reason: str


class IncompleteJudgmentsError(ValueError):
    """Raised when a pair is missing, invalid, or duplicated."""

    def __init__(self, issues: list[PairIssue]) -> None:
        self.issues = issues
        detail = "; ".join(
            f"{item.question_id}/{item.model_a}/{item.model_b}: {item.reason}"
            for item in issues
        )
        super().__init__(f"cannot aggregate incomplete judgments: {detail}")


def _relation(j_ab: Outcome, j_ba: Outcome) -> PairRelationLabel:
    if j_ab is Outcome.WIN and j_ba is Outcome.LOSE:
        return PairRelationLabel.A_OVER_B
    if j_ab is Outcome.LOSE and j_ba is Outcome.WIN:
        return PairRelationLabel.B_OVER_A
    return PairRelationLabel.TIE


def aggregate_pair_judgments(
    judgments: Iterable[JudgmentRecord],
) -> list[PairRelation]:
    """Aggregate exactly two valid opposite-order judgments per unordered pair.

    Canonical ``model_a`` and ``model_b`` order is lexicographic. ``j_ab`` is
    the outcome when A is on the left, while ``j_ba`` is the outcome when B is
    on the left. Any incomplete or invalid pair rejects the whole operation so
    callers cannot silently create a tie.
    """

    grouped: dict[PairKey, list[JudgmentRecord]] = defaultdict(list)
    for judgment in judgments:
        model_a, model_b = sorted((judgment.left_model, judgment.right_model))
        grouped[(judgment.question_id, model_a, model_b)].append(judgment)

    relations: list[PairRelation] = []
    issues: list[PairIssue] = []
    for (question_id, model_a, model_b), records in sorted(grouped.items()):
        a_left = [
            item
            for item in records
            if item.left_model == model_a and item.right_model == model_b
        ]
        b_left = [
            item
            for item in records
            if item.left_model == model_b and item.right_model == model_a
        ]

        reasons: list[str] = []
        if len(a_left) != 1:
            reasons.append(f"expected one A/B order, found {len(a_left)}")
        if len(b_left) != 1:
            reasons.append(f"expected one B/A order, found {len(b_left)}")
        if any(
            item.status == "invalid" or item.normalized_left_outcome is Outcome.INVALID
            for item in records
        ):
            reasons.append("contains invalid judgment")
        if reasons:
            issues.append(
                PairIssue(
                    question_id=question_id,
                    model_a=model_a,
                    model_b=model_b,
                    reason=", ".join(reasons),
                )
            )
            continue

        j_ab = a_left[0].normalized_left_outcome
        j_ba = b_left[0].normalized_left_outcome
        relations.append(
            PairRelation(
                question_id=question_id,
                model_a=model_a,
                model_b=model_b,
                j_ab=j_ab,
                j_ba=j_ba,
                relation=_relation(j_ab, j_ba),
            )
        )

    if issues:
        raise IncompleteJudgmentsError(issues)
    return relations
