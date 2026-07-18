import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from elspr.cli import app
from elspr.io import read_jsonl, write_jsonl
from elspr.judging import JudgeRequest
from elspr.schemas import JudgmentRecord, Outcome
from elspr.training import (
    TrainingDataConfig,
    TrainingDataError,
    TrainingExample,
    build_training_variants,
)

runner = CliRunner()


def _request(question: str, left: str, right: str, index: int) -> JudgeRequest:
    return JudgeRequest(
        request_id=f"{index:064x}",
        pair_id=hashlib.sha256(f"{question}:a:b".encode()).hexdigest(),
        question_id=question,
        order_index=0 if left == "a" else 1,
        left_model=left,
        right_model=right,
        instruction=f"instruction {question}",
        left_response=f"response {left}",
        right_response=f"response {right}",
        judge_model="qwen-max",
        prompt_template_id="cot_v1:123456789abc",
        system_prompt="system",
        user_prompt=f"compare {left} and {right} for {question}",
        estimated_input_tokens=100,
    )


def _judgment(request: JudgeRequest, *, suffix: str = "") -> JudgmentRecord:
    return JudgmentRecord(
        question_id=request.question_id,
        left_model=request.left_model,
        right_model=request.right_model,
        left_response=request.left_response,
        right_response=request.right_response,
        verdict="left_win",
        normalized_left_outcome=Outcome.WIN,
        judge_model=request.judge_model,
        prompt_template_id=request.prompt_template_id,
        raw_output=f"reasoning {request.question_id} m{suffix}",
        status="ok",
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


def _fixture(
    tmp_path: Path,
) -> tuple[TrainingDataConfig, list[JudgeRequest], list[JudgmentRecord]]:
    requests = [
        _request(question, left, right, index)
        for index, (question, left, right) in enumerate(
            [
                ("q1", "a", "b"),
                ("q1", "b", "a"),
                ("q2", "a", "b"),
                ("q2", "b", "a"),
                ("q3", "a", "b"),
                ("q3", "b", "a"),
            ],
            start=1,
        )
    ]
    judgments = [_judgment(request) for request in requests]
    manifest_path = tmp_path / "data-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "model_count": 2,
                "split": {
                    "train_question_ids": ["q1", "q2"],
                    "evaluation_question_ids": ["q3"],
                },
            }
        ),
        encoding="utf-8",
    )
    requests_path = tmp_path / "requests.jsonl"
    raw_path = tmp_path / "judgments.jsonl"
    cleaned_path = tmp_path / "cleaned.jsonl"
    write_jsonl(requests_path, requests)
    write_jsonl(raw_path, judgments)
    write_jsonl(cleaned_path, [judgments[0], judgments[1], judgments[4]])
    return (
        TrainingDataConfig(
            data_manifest=manifest_path,
            judge_requests=requests_path,
            raw_judgments=raw_path,
            cleaned_judgments=cleaned_path,
            output_dir=tmp_path / "training",
            random_seed=20260718,
        ),
        requests,
        judgments,
    )


def test_build_variants_is_size_matched_traceable_and_split_safe(
    tmp_path: Path,
) -> None:
    config, _, _ = _fixture(tmp_path)

    result = build_training_variants(config)
    raw = read_jsonl(result.raw_path, TrainingExample)
    cleaned = read_jsonl(result.cleaned_path, TrainingExample)
    random = read_jsonl(result.random_path, TrainingExample)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert (result.raw_count, result.cleaned_count, result.random_count) == (4, 2, 2)
    assert {item.question_id for item in raw} == {"q1", "q2"}
    assert {item.question_id for item in cleaned} == {"q1"}
    assert "q3" not in {item.question_id for item in raw + cleaned + random}
    assert {item.request_id for item in random} <= {item.request_id for item in raw}
    assert {item.variant for item in raw} == {"raw"}
    assert {item.variant for item in cleaned} == {"cleaned"}
    assert {item.variant for item in random} == {"random"}
    assert manifest["cleaned_retention"] == 0.5
    assert manifest["artifacts"]["cleaned"]["rows"] == 2
    assert manifest["artifacts"]["random"]["rows"] == 2


def test_random_variant_is_deterministic(tmp_path: Path) -> None:
    config, _, _ = _fixture(tmp_path)
    first = build_training_variants(config)
    first_bytes = first.random_path.read_bytes()
    second = build_training_variants(
        config.model_copy(update={"output_dir": tmp_path / "second"})
    )

    assert second.random_path.read_bytes() == first_bytes


def test_build_variants_rejects_incomplete_raw_judgments(tmp_path: Path) -> None:
    config, _, judgments = _fixture(tmp_path)
    write_jsonl(config.raw_judgments, judgments[1:])

    with pytest.raises(TrainingDataError, match="do not cover train requests"):
        build_training_variants(config)


def test_build_variants_rejects_cleaned_relabeling(tmp_path: Path) -> None:
    config, _, judgments = _fixture(tmp_path)
    write_jsonl(
        config.cleaned_judgments,
        [judgments[0].model_copy(update={"raw_output": "changed m"})],
    )

    with pytest.raises(TrainingDataError, match="changed raw record"):
        build_training_variants(config)


def test_prepare_training_cli(tmp_path: Path) -> None:
    config, _, _ = _fixture(tmp_path)
    config_path = tmp_path / "training.yaml"
    config_path.write_text(
        "\n".join(
            [
                f"data_manifest: {config.data_manifest}",
                f"judge_requests: {config.judge_requests}",
                f"raw_judgments: {config.raw_judgments}",
                f"cleaned_judgments: {config.cleaned_judgments}",
                f"output_dir: {config.output_dir}",
                f"random_seed: {config.random_seed}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["prepare-training", "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    assert "raw=4 cleaned=2 random=2" in result.output
