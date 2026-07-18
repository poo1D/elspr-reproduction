import json
from pathlib import Path

import pytest

from elspr.io import read_jsonl, write_jsonl
from elspr.judging import (
    HttpResult,
    JudgeConfig,
    JudgeExecutionError,
    JudgeRequest,
    execute_judgments,
)
from elspr.schemas import JudgmentRecord, Outcome


def _request() -> JudgeRequest:
    return JudgeRequest(
        request_id="1" * 64,
        pair_id="2" * 64,
        question_id="q1",
        order_index=0,
        left_model="a",
        right_model="b",
        instruction="question",
        left_response="answer a",
        right_response="answer b",
        judge_model="qwen-max",
        prompt_template_id="cot_v1:123456789abc",
        system_prompt="judge",
        user_prompt="compare",
        estimated_input_tokens=100,
    )


def _config(tmp_path: Path, *, max_retries: int = 3) -> JudgeConfig:
    output_dir = tmp_path / "output"
    write_jsonl(output_dir / "judge_requests.jsonl", [_request()])
    return JudgeConfig(
        provider="dashscope",
        model="qwen-max",
        api_url="https://example.test/compatible-mode/v1/chat/completions",
        api_key_env="TEST_DASHSCOPE_KEY",
        responses=tmp_path / "responses.jsonl",
        prompt_template=tmp_path / "prompt.txt",
        system_prompt_template=tmp_path / "system.txt",
        temperature=0,
        seed=1234,
        max_output_tokens=100,
        max_retries=max_retries,
        requests_per_minute=30,
        cache_dir=tmp_path / "cache",
        output_dir=output_dir,
        expected_responses_sha256="0" * 64,
        input_price_cny_per_million=2.4,
        output_price_cny_per_million=9.6,
        pricing_checked_at="2026-07-18",
        pricing_url="https://example.test/pricing",
    )


def _valid_result(*, winner: str = "m") -> HttpResult:
    return HttpResult(
        status_code=200,
        headers={"x-request-id": "provider-1"},
        body=json.dumps(
            {
                "id": "chatcmpl-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"Explanation\n{winner}",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        ),
    )


def test_execution_requires_explicit_paid_flag_and_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.delenv("TEST_DASHSCOPE_KEY", raising=False)

    with pytest.raises(JudgeExecutionError, match="--execute-paid"):
        execute_judgments(
            config,
            execute_paid=False,
            approved_budget_cny=1,
            max_new_requests=1,
        )
    with pytest.raises(JudgeExecutionError, match="missing API key"):
        execute_judgments(
            config,
            execute_paid=True,
            approved_budget_cny=1,
            max_new_requests=1,
        )


def test_execution_enforces_approved_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("TEST_DASHSCOPE_KEY", "secret")

    with pytest.raises(JudgeExecutionError, match="above approved budget"):
        execute_judgments(
            config,
            execute_paid=True,
            approved_budget_cny=0.000001,
            max_new_requests=1,
            transport=lambda *_: _valid_result(),
        )


def test_execution_retries_caches_raw_output_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("TEST_DASHSCOPE_KEY", "super-secret")
    responses = [
        HttpResult(
            status_code=429,
            headers={"retry-after": "0.25"},
            body='{"error":{"code":"Throttling.RateQuota"}}',
        ),
        _valid_result(winner="m"),
    ]
    calls: list[tuple[str, dict[str, str], dict[str, object], float]] = []
    sleeps: list[float] = []

    def transport(
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> HttpResult:
        calls.append((url, headers, payload, timeout))
        return responses.pop(0)

    result = execute_judgments(
        config,
        execute_paid=True,
        approved_budget_cny=1,
        max_new_requests=1,
        transport=transport,
        sleep=sleeps.append,
    )

    assert result.cached_count == 0
    assert result.new_count == 1
    assert result.failed_count == 0
    assert result.pending_count == 0
    assert result.actual_cost_cny == pytest.approx(0.000072)
    assert len(calls) == 2
    assert calls[0][1]["Authorization"] == "Bearer super-secret"
    assert calls[0][2]["seed"] == 1234
    assert calls[0][2]["max_tokens"] == 100
    assert 1.0 in sleeps
    assert 2.0 in sleeps
    request_dir = config.cache_dir / _request().request_id
    assert (request_dir / "attempt-001.json").exists()
    assert (request_dir / "attempt-002.json").exists()
    assert (request_dir / "result.json").exists()
    assert "Throttling.RateQuota" in (request_dir / "attempt-001.json").read_text(
        encoding="utf-8"
    )
    assert "super-secret" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in request_dir.iterdir()
        if path.is_file()
    )
    judgments = read_jsonl(result.judgments_path, JudgmentRecord)
    assert judgments[0].normalized_left_outcome is Outcome.WIN

    def unexpected_transport(*_: object) -> HttpResult:
        raise AssertionError("resume must not call the provider")

    resumed = execute_judgments(
        config,
        execute_paid=True,
        approved_budget_cny=1,
        max_new_requests=1,
        transport=unexpected_transport,
        sleep=sleeps.append,
    )

    assert resumed.cached_count == 1
    assert resumed.new_count == 0
    assert resumed.failed_count == 0
    assert resumed.actual_cost_cny == pytest.approx(result.actual_cost_cny)


def test_execution_retries_invalid_success_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, max_retries=1)
    monkeypatch.setenv("TEST_DASHSCOPE_KEY", "secret")
    responses = [_valid_result(winner="?"), _valid_result(winner="M")]

    result = execute_judgments(
        config,
        execute_paid=True,
        approved_budget_cny=1,
        max_new_requests=1,
        transport=lambda *_: responses.pop(0),
        sleep=lambda _: None,
    )

    judgments = read_jsonl(result.judgments_path, JudgmentRecord)
    assert result.new_count == 1
    assert judgments[0].normalized_left_outcome is Outcome.LOSE
    first_attempt = json.loads(
        (config.cache_dir / _request().request_id / "attempt-001.json").read_text(
            encoding="utf-8"
        )
    )
    assert "must end in m or M" in first_attempt["error"]


def test_permanent_http_failure_is_recorded_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setenv("TEST_DASHSCOPE_KEY", "secret")
    calls = 0

    def transport(*_: object) -> HttpResult:
        nonlocal calls
        calls += 1
        return HttpResult(status_code=400, headers={}, body='{"error":"bad request"}')

    result = execute_judgments(
        config,
        execute_paid=True,
        approved_budget_cny=1,
        max_new_requests=1,
        transport=transport,
        sleep=lambda _: None,
    )

    assert calls == 1
    assert result.new_count == 0
    assert result.failed_count == 1
    assert result.pending_count == 0
    failure = json.loads(result.failures_path.read_text(encoding="utf-8"))
    assert failure["attempts"] == 1
    assert "provider HTTP 400" in failure["error"]

    resumed = execute_judgments(
        config,
        execute_paid=True,
        approved_budget_cny=1,
        max_new_requests=1,
        transport=lambda *_: _valid_result(),
        sleep=lambda _: None,
    )
    request_dir = config.cache_dir / _request().request_id
    assert resumed.new_count == 1
    assert (request_dir / "attempt-001.json").exists()
    assert (request_dir / "attempt-002.json").exists()
    assert "bad request" in (request_dir / "attempt-001.json").read_text(
        encoding="utf-8"
    )
