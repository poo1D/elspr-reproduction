import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from elspr.cli import app
from elspr.io import write_jsonl
from elspr.judging import (
    JudgeConfig,
    JudgePreparationError,
    estimate_tokens,
    judge_dry_run,
    render_judge_requests,
)
from elspr.schemas import ResponseRecord

runner = CliRunner()


def _response(question: str, model: str) -> ResponseRecord:
    return ResponseRecord(
        question_id=question,
        dataset="helpful_base",
        instruction=f"instruction {question}",
        model_id=model,
        response=f"response from {model} for {question}",
        source="fixture",
    )


def _config(
    tmp_path: Path,
    responses: list[ResponseRecord],
    *,
    provider: str = "dry_run",
) -> JudgeConfig:
    responses_path = tmp_path / "responses.jsonl"
    write_jsonl(responses_path, responses)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(
        "{instruction}\nLEFT={left_response}\nRIGHT={right_response}\n",
        encoding="utf-8",
    )
    system = tmp_path / "system.txt"
    system.write_text("judge carefully\n", encoding="utf-8")
    return JudgeConfig(
        provider=provider,
        model="judge-model",
        api_url="https://example.test/compatible-mode/v1/chat/completions",
        api_key_env="TEST_API_KEY",
        responses=responses_path,
        prompt_template=prompt,
        system_prompt_template=system,
        temperature=0,
        seed=1234,
        max_output_tokens=100,
        max_retries=3,
        requests_per_minute=30,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        expected_responses_sha256=hashlib.sha256(
            responses_path.read_bytes()
        ).hexdigest(),
        input_price_cny_per_million=2.4,
        output_price_cny_per_million=9.6,
        pricing_checked_at="2026-07-18",
        pricing_url="https://example.test/pricing",
    )


def test_render_judge_requests_creates_both_orders_with_stable_ids(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        [_response("q1", "model-b"), _response("q1", "model-a")],
    )

    first_run = render_judge_requests(config)
    second_run = render_judge_requests(config)

    assert first_run == second_run
    assert len(first_run) == 2
    first, swapped = first_run
    assert first.pair_id == swapped.pair_id
    assert first.request_id != swapped.request_id
    assert first.order_index == 0
    assert swapped.order_index == 1
    assert (first.left_model, first.right_model) == ("model-a", "model-b")
    assert (swapped.left_model, swapped.right_model) == ("model-b", "model-a")
    assert first.left_response == swapped.right_response
    assert first.right_response == swapped.left_response
    assert first.estimated_input_tokens == estimate_tokens("judge carefully") + (
        estimate_tokens(first.user_prompt)
    )


def test_render_request_count_matches_questions_pairs_and_orders(
    tmp_path: Path,
) -> None:
    responses = [
        _response(question, model)
        for question in ["q2", "q1"]
        for model in ["c", "a", "b"]
    ]

    requests = render_judge_requests(_config(tmp_path, responses))

    assert len(requests) == 2 * 3 * 2
    assert len({request.request_id for request in requests}) == len(requests)
    assert {request.question_id for request in requests} == {"q1", "q2"}


def test_dry_run_writes_requests_and_zero_paid_call_report(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        [
            _response(question, model)
            for question in ["q1", "q2"]
            for model in ["a", "b", "c"]
        ],
    )

    result = judge_dry_run(
        config,
        generated_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    report = json.loads(result.report_path.read_text(encoding="utf-8"))

    assert result.request_count == 12
    assert report["paid_requests_executed"] == 0
    assert report["generated_at"] == "2026-07-18T00:00:00+00:00"
    assert report["token_estimator"] == "utf8_bytes_div4_ceil_v1"
    assert report["maximum_output_tokens"]["total"] == 1200
    assert report["estimated_cost_cny"]["upper_bound"] > 0
    assert (
        report["requests_sha256"]
        == hashlib.sha256(result.requests_path.read_bytes()).hexdigest()
    )


def test_render_rejects_responses_checksum_mismatch(tmp_path: Path) -> None:
    config = _config(tmp_path, [_response("q1", "a"), _response("q1", "b")])
    config = config.model_copy(
        update={"expected_responses_sha256": "0" * 64},
    )

    with pytest.raises(JudgePreparationError, match="SHA-256 mismatch"):
        render_judge_requests(config)


def test_render_rejects_incomplete_model_matrix(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        [
            _response("q1", "a"),
            _response("q1", "b"),
            _response("q2", "a"),
        ],
    )

    with pytest.raises(JudgePreparationError, match="model set"):
        render_judge_requests(config)


def test_dry_run_refuses_paid_provider(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        [_response("q1", "a"), _response("q1", "b")],
        provider="dashscope",
    )

    with pytest.raises(JudgePreparationError, match="no paid call was attempted"):
        judge_dry_run(config)


def test_judge_cli_reports_dry_run_counts(tmp_path: Path) -> None:
    config = _config(tmp_path, [_response("q1", "a"), _response("q1", "b")])
    config_path = tmp_path / "judge.yaml"
    config_path.write_text(
        "\n".join(
            [
                "provider: dry_run",
                "model: judge-model",
                "api_url: https://example.test/compatible-mode/v1/chat/completions",
                "api_key_env: TEST_API_KEY",
                f"responses: {config.responses}",
                f"prompt_template: {config.prompt_template}",
                f"system_prompt_template: {config.system_prompt_template}",
                "temperature: 0",
                "seed: 1234",
                "max_output_tokens: 100",
                "max_retries: 3",
                "requests_per_minute: 30",
                f"cache_dir: {config.cache_dir}",
                f"output_dir: {config.output_dir}",
                f"expected_responses_sha256: {config.expected_responses_sha256}",
                "input_price_cny_per_million: 2.4",
                "output_price_cny_per_million: 9.6",
                "pricing_checked_at: '2026-07-18'",
                "pricing_url: https://example.test/pricing",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["judge", "--config", str(config_path), "--resume"],
    )

    assert result.exit_code == 0, result.output
    assert "questions=1 models=2 requests=2" in result.output
    assert "maximum_output_tokens=200" in result.output
