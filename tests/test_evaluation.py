import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from elspr.cli import app
from elspr.evaluation import EvaluationConfig, EvaluationError, evaluate_variants
from elspr.io import write_jsonl
from elspr.schemas import JudgmentRecord
from elspr.toy import toy_judgments

runner = CliRunner()


def _case(case: str, question_id: str = "q_eval") -> list[JudgmentRecord]:
    return [
        record.model_copy(update={"question_id": question_id})
        for record in toy_judgments(case)
    ]


def _config(tmp_path: Path) -> EvaluationConfig:
    data_manifest = tmp_path / "data-manifest.json"
    data_manifest.write_text(
        json.dumps(
            {
                "model_count": 3,
                "split": {
                    "train_question_ids": ["q_train"],
                    "evaluation_question_ids": ["q_eval"],
                },
            }
        ),
        encoding="utf-8",
    )
    training_manifest = tmp_path / "training-manifest.json"
    training_manifest.write_text(
        json.dumps(
            {
                "raw_count": 100,
                "cleaned_count": 80,
                "random_count": 80,
            }
        ),
        encoding="utf-8",
    )
    raw = tmp_path / "raw.jsonl"
    cleaned = tmp_path / "cleaned.jsonl"
    random = tmp_path / "random.jsonl"
    write_jsonl(raw, _case("cycle"))
    write_jsonl(cleaned, _case("linear"))
    write_jsonl(random, _case("all_tie"))
    return EvaluationConfig(
        data_manifest=data_manifest,
        training_manifest=training_manifest,
        raw_judgments=raw,
        cleaned_judgments=cleaned,
        random_judgments=random,
        output_dir=tmp_path / "evaluation",
    )


def test_evaluate_variants_writes_per_question_and_direction_report(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    result = evaluate_variants(config)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    report = result.report_path.read_text(encoding="utf-8")

    assert result.question_count == 1
    assert result.cleaned_improves_rho is True
    assert result.cleaned_improves_tau is True
    assert summary["variants"]["raw"]["rho_non_trans"] == 1.0
    assert summary["variants"]["raw"]["tau_avg"] == 1.0
    assert summary["variants"]["cleaned"]["rho_non_trans"] == 0.0
    assert summary["variants"]["cleaned"]["tau_avg"] == 0.0
    assert summary["conclusion"]["random_matches_or_beats_cleaned_both"] is False
    assert summary["training_counts"] == {
        "raw_count": 100,
        "cleaned_count": 80,
        "random_count": 80,
    }
    assert (config.output_dir / "raw" / "graphs" / "q_eval.json").exists()
    assert (config.output_dir / "raw" / "graphs" / "q_eval.svg").exists()
    assert "cleaned improves both required metrics: True" in report


def test_evaluation_rejects_training_question_leakage(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_jsonl(config.raw_judgments, _case("cycle", "q_train"))

    with pytest.raises(EvaluationError, match="training questions"):
        evaluate_variants(config)


def test_evaluation_rejects_incomplete_ordered_pairs(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_jsonl(config.random_judgments, _case("all_tie")[:-1])

    with pytest.raises(EvaluationError, match="expected 6 judgments"):
        evaluate_variants(config)


def test_evaluate_cli(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config_path = tmp_path / "eval.yaml"
    config_path.write_text(
        "\n".join(
            [
                f"data_manifest: {config.data_manifest}",
                f"training_manifest: {config.training_manifest}",
                f"raw_judgments: {config.raw_judgments}",
                f"cleaned_judgments: {config.cleaned_judgments}",
                f"random_judgments: {config.random_judgments}",
                f"output_dir: {config.output_dir}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["evaluate", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "questions=1" in result.output
    assert "cleaned_improves_rho=True" in result.output
    assert "cleaned_improves_tau=True" in result.output
