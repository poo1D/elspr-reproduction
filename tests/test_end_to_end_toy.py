import math
from pathlib import Path

import pytest

from elspr.io import read_jsonl, write_jsonl
from elspr.schemas import JudgmentRecord
from elspr.toy import TOY_CASES, run_toy_case, toy_judgments


@pytest.mark.parametrize(
    ("case", "rho", "tau", "cleaned", "discarded"),
    [
        ("linear", 0.0, 0.0, 6, 0),
        ("cycle", 1.0, 1.0, 0, 6),
        ("all_tie", 0.0, 1.0, 0, 6),
        ("position_bias", 0.0, 1 / math.log2(3), 4, 2),
        ("reconstruction", 1.0, None, 6, 6),
    ],
)
def test_required_toy_cases_end_to_end(
    case: str,
    rho: float,
    tau: float | None,
    cleaned: int,
    discarded: int,
) -> None:
    result = run_toy_case(case)

    assert result.scc.rho_non_trans == pytest.approx(rho)
    if tau is not None:
        assert result.entropy.tau == pytest.approx(tau)
    assert len(result.filtering.cleaned) == cleaned
    assert len(result.filtering.discarded) == discarded
    assert len(result.filtering.decisions) == len(result.judgments)


def test_case_e_has_expected_tie_quotient_order() -> None:
    result = run_toy_case("reconstruction")

    assert result.reconstruction.tie_classes == (("a", "c"), ("b", "d"))
    assert set(result.reconstruction.quotient_graph.edges) == {(("b", "d"), ("a", "c"))}


def test_all_declared_cases_run() -> None:
    assert {run_toy_case(case).case for case in TOY_CASES} == set(TOY_CASES)


def test_jsonl_round_trip_preserves_typed_judgments(tmp_path: Path) -> None:
    path = tmp_path / "judgments.jsonl"
    records = toy_judgments("linear")

    write_jsonl(path, records)
    loaded = read_jsonl(path, JudgmentRecord)

    assert loaded == list(records)
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(records)


def test_jsonl_error_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"question_id": "incomplete"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"broken\.jsonl:1:"):
        read_jsonl(path, JudgmentRecord)
