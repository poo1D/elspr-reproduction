"""Guarded, resumable DashScope execution with permanent raw-response caching."""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import Field

from elspr.io import read_jsonl, write_jsonl
from elspr.judging.requests import JudgeConfig, JudgeRequest
from elspr.schemas import JudgmentRecord, Outcome, StrictModel

logger = structlog.get_logger()
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


class JudgeExecutionError(RuntimeError):
    """Raised when execution is unsafe or provider results are unusable."""


class HttpResult(StrictModel):
    """Raw HTTP result returned by the injectable transport."""

    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str]
    body: str


class ProviderAttempt(StrictModel):
    """Permanent record for one provider attempt."""

    request_id: str
    attempt: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime
    status_code: int | None
    response_headers: dict[str, str]
    raw_response: str
    error: str | None


class CachedJudgment(StrictModel):
    """Validated judgment and provider usage cached for resume."""

    request_id: str
    provider_call_id: str
    finish_reason: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    judgment: JudgmentRecord


class ExecutionFailure(StrictModel):
    """Unresolved request after all permitted attempts."""

    request_id: str
    attempts: int = Field(ge=0)
    last_status_code: int | None
    error: str


class JudgeExecutionResult(StrictModel):
    """Paths and counts produced by a guarded execution pass."""

    judgments_path: Path
    failures_path: Path
    report_path: Path
    cached_count: int
    new_count: int
    failed_count: int
    pending_count: int
    actual_cost_cny: float


Transport = Callable[[str, dict[str, str], dict[str, Any], float], HttpResult]
Sleep = Callable[[float], None]


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _http_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> HttpResult:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return HttpResult(
                status_code=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as error:
        return HttpResult(
            status_code=error.code,
            headers={key.lower(): value for key, value in error.headers.items()},
            body=error.read().decode("utf-8", errors="replace"),
        )


def _provider_payload(request: JudgeRequest, config: JudgeConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ],
        "temperature": config.temperature,
        "seed": config.seed,
        "max_tokens": config.max_output_tokens,
    }


def _retry_after(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _parse_provider_response(
    request: JudgeRequest,
    result: HttpResult,
    *,
    completed_at: datetime,
) -> CachedJudgment:
    if not 200 <= result.status_code < 300:
        raise JudgeExecutionError(f"provider HTTP {result.status_code}")
    try:
        payload = json.loads(result.body)
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
        usage = payload["usage"]
        provider_call_id = payload["id"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise JudgeExecutionError(
            f"invalid provider response schema: {error}"
        ) from error
    if not isinstance(content, str) or not content.strip():
        raise JudgeExecutionError("provider response content is empty")
    if finish_reason != "stop":
        raise JudgeExecutionError(f"provider finish_reason={finish_reason!r}")
    winner = content.strip()[-1]
    if winner == "m":
        outcome = Outcome.WIN
        verdict = "left_win"
    elif winner == "M":
        outcome = Outcome.LOSE
        verdict = "right_win"
    else:
        raise JudgeExecutionError(f"provider output must end in m or M, got {winner!r}")
    try:
        prompt_tokens = int(usage["prompt_tokens"])
        completion_tokens = int(usage["completion_tokens"])
    except (KeyError, TypeError, ValueError) as error:
        raise JudgeExecutionError(f"invalid provider usage: {error}") from error
    if prompt_tokens < 0 or completion_tokens < 0:
        raise JudgeExecutionError("provider token usage cannot be negative")

    return CachedJudgment(
        request_id=request.request_id,
        provider_call_id=str(provider_call_id),
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        judgment=JudgmentRecord(
            question_id=request.question_id,
            left_model=request.left_model,
            right_model=request.right_model,
            left_response=request.left_response,
            right_response=request.right_response,
            verdict=verdict,
            normalized_left_outcome=outcome,
            judge_model=request.judge_model,
            prompt_template_id=request.prompt_template_id,
            raw_output=content,
            status="ok",
            created_at=completed_at,
        ),
    )


def _load_cached(path: Path, *, request_id: str) -> CachedJudgment | None:
    if not path.exists():
        return None
    cached = CachedJudgment.model_validate_json(path.read_text(encoding="utf-8"))
    if cached.request_id != request_id:
        raise JudgeExecutionError(
            f"cache request ID mismatch at {path}: {cached.request_id}"
        )
    return cached


def _estimated_request_cost(request: JudgeRequest, config: JudgeConfig) -> float:
    return (
        request.estimated_input_tokens * config.input_price_cny_per_million
        + config.max_output_tokens * config.output_price_cny_per_million
    ) / 1_000_000


def _actual_cost(records: list[CachedJudgment], config: JudgeConfig) -> float:
    return sum(
        (
            record.prompt_tokens * config.input_price_cny_per_million
            + record.completion_tokens * config.output_price_cny_per_million
        )
        / 1_000_000
        for record in records
    )


def _attempt_request(
    request: JudgeRequest,
    config: JudgeConfig,
    *,
    api_key: str,
    transport: Transport,
    sleep: Sleep,
    timeout_seconds: float,
    rate_delay_seconds: float,
    call_already_made: bool,
) -> tuple[CachedJudgment | None, ExecutionFailure, bool]:
    request_dir = config.cache_dir / request.request_id
    result_path = request_dir / "result.json"
    previous_attempts = [
        int(path.stem.removeprefix("attempt-"))
        for path in request_dir.glob("attempt-*.json")
        if path.stem.removeprefix("attempt-").isdigit()
    ]
    attempt_offset = max(previous_attempts, default=0)
    last_error = "request was not attempted"
    last_status: int | None = None
    attempts = config.max_retries + 1
    last_attempt = 0

    for local_attempt in range(1, attempts + 1):
        attempt = attempt_offset + local_attempt
        last_attempt = attempt
        if call_already_made:
            sleep(rate_delay_seconds)
        call_already_made = True
        started_at = datetime.now(UTC)
        result: HttpResult | None = None
        try:
            result = transport(
                config.api_url,
                {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                _provider_payload(request, config),
                timeout_seconds,
            )
            last_status = result.status_code
            completed_at = datetime.now(UTC)
            attempt_record = ProviderAttempt(
                request_id=request.request_id,
                attempt=attempt,
                started_at=started_at,
                completed_at=completed_at,
                status_code=result.status_code,
                response_headers=result.headers,
                raw_response=result.body,
                error=None,
            )
            _atomic_write_json(
                request_dir / f"attempt-{attempt:03d}.json",
                attempt_record.model_dump(mode="json"),
            )
            cached = _parse_provider_response(
                request,
                result,
                completed_at=completed_at,
            )
            _atomic_write_json(result_path, cached.model_dump(mode="json"))
            logger.info(
                "judge_request_completed",
                request_id=request.request_id,
                attempt=attempt,
                status_code=result.status_code,
            )
            return (
                cached,
                ExecutionFailure(
                    request_id=request.request_id,
                    attempts=attempt,
                    last_status_code=result.status_code,
                    error="",
                ),
                call_already_made,
            )
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            completed_at = datetime.now(UTC)
            attempt_record = ProviderAttempt(
                request_id=request.request_id,
                attempt=attempt,
                started_at=started_at,
                completed_at=completed_at,
                status_code=result.status_code if result is not None else None,
                response_headers=result.headers if result is not None else {},
                raw_response=result.body if result is not None else "",
                error=last_error,
            )
            _atomic_write_json(
                request_dir / f"attempt-{attempt:03d}.json",
                attempt_record.model_dump(mode="json"),
            )
            retryable = (
                result is None
                or result.status_code in RETRYABLE_STATUS_CODES
                or 200 <= result.status_code < 300
            )
            if local_attempt >= attempts or not retryable:
                break
            backoff = min(60.0, float(2 ** (local_attempt - 1)))
            if result is not None:
                backoff = max(backoff, _retry_after(result.headers) or 0.0)
            logger.warning(
                "judge_request_retry",
                request_id=request.request_id,
                attempt=attempt,
                status_code=last_status,
                backoff_seconds=backoff,
            )
            sleep(backoff)

    return (
        None,
        ExecutionFailure(
            request_id=request.request_id,
            attempts=last_attempt,
            last_status_code=last_status,
            error=last_error,
        ),
        call_already_made,
    )


def execute_judgments(
    config: JudgeConfig,
    *,
    execute_paid: bool,
    approved_budget_cny: float,
    max_new_requests: int,
    timeout_seconds: float = 300,
    transport: Transport = _http_post_json,
    sleep: Sleep = time.sleep,
) -> JudgeExecutionResult:
    """Execute a budget-capped pass and resume from validated cached results."""

    if config.provider != "dashscope":
        raise JudgeExecutionError("provider must be 'dashscope' for execution")
    if not execute_paid:
        raise JudgeExecutionError("paid execution requires --execute-paid")
    if approved_budget_cny <= 0:
        raise JudgeExecutionError("approved budget must be positive")
    if max_new_requests <= 0:
        raise JudgeExecutionError("max_new_requests must be positive")
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise JudgeExecutionError(
            f"missing API key environment variable {config.api_key_env}"
        )

    requests_path = config.output_dir / "judge_requests.jsonl"
    requests = read_jsonl(requests_path, JudgeRequest)
    cached_by_id: dict[str, CachedJudgment] = {}
    uncached: list[JudgeRequest] = []
    for request in requests:
        cached = _load_cached(
            config.cache_dir / request.request_id / "result.json",
            request_id=request.request_id,
        )
        if cached is None:
            uncached.append(request)
        else:
            cached_by_id[request.request_id] = cached

    selected = uncached[:max_new_requests]
    estimated_cost = sum(
        _estimated_request_cost(request, config) for request in selected
    )
    if estimated_cost > approved_budget_cny:
        raise JudgeExecutionError(
            f"selected requests have estimated upper cost CNY {estimated_cost:.6f}, "
            f"above approved budget CNY {approved_budget_cny:.6f}"
        )

    failures: list[ExecutionFailure] = []
    call_already_made = False
    rate_delay_seconds = 60.0 / config.requests_per_minute
    for request in selected:
        cached, failure, call_already_made = _attempt_request(
            request,
            config,
            api_key=api_key,
            transport=transport,
            sleep=sleep,
            timeout_seconds=timeout_seconds,
            rate_delay_seconds=rate_delay_seconds,
            call_already_made=call_already_made,
        )
        if cached is None:
            failures.append(failure)
        else:
            cached_by_id[request.request_id] = cached

    completed = [
        cached_by_id[request.request_id]
        for request in requests
        if request.request_id in cached_by_id
    ]
    execution_dir = config.output_dir / "execution"
    judgments_path = execution_dir / "judgments.jsonl"
    failures_path = execution_dir / "failures.jsonl"
    report_path = execution_dir / "execution_report.json"
    write_jsonl(judgments_path, [record.judgment for record in completed])
    write_jsonl(failures_path, failures)
    actual_cost = _actual_cost(completed, config)
    pending_count = len(requests) - len(completed) - len(failures)
    report = {
        "schema_version": 1,
        "provider": config.provider,
        "model": config.model,
        "total_requests": len(requests),
        "cached_before_run": len(cached_by_id) - (len(selected) - len(failures)),
        "new_requests_selected": len(selected),
        "completed_total": len(completed),
        "failed_this_run": len(failures),
        "pending": pending_count,
        "actual_prompt_tokens": sum(record.prompt_tokens for record in completed),
        "actual_completion_tokens": sum(
            record.completion_tokens for record in completed
        ),
        "actual_cost_cny": actual_cost,
        "approved_budget_cny": approved_budget_cny,
        "pricing_checked_at": config.pricing_checked_at,
        "pricing_url": config.pricing_url,
    }
    _atomic_write_json(report_path, report)
    return JudgeExecutionResult(
        judgments_path=judgments_path,
        failures_path=failures_path,
        report_path=report_path,
        cached_count=report["cached_before_run"],
        new_count=len(selected) - len(failures),
        failed_count=len(failures),
        pending_count=pending_count,
        actual_cost_cny=actual_cost,
    )
