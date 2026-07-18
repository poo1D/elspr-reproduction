"""Deterministic judge-request rendering and zero-cost dry-run estimation."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from elspr.io import read_jsonl, write_jsonl
from elspr.schemas import ResponseRecord, StrictModel

TOKEN_ESTIMATOR = "utf8_bytes_div4_ceil_v1"


class JudgePreparationError(ValueError):
    """Raised when responses or judge configuration are not reproducible."""


class JudgeConfig(StrictModel):
    """Configuration for rendering or executing ordered judge requests."""

    provider: Literal["dry_run", "dashscope"]
    model: str = Field(min_length=1)
    responses: Path
    prompt_template: Path
    system_prompt_template: Path
    temperature: float = Field(ge=0)
    max_output_tokens: int = Field(gt=0)
    max_retries: int = Field(ge=0)
    requests_per_minute: int = Field(gt=0)
    cache_dir: Path
    output_dir: Path
    expected_responses_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class JudgeRequest(StrictModel):
    """One fully rendered, ordered, idempotent judge request."""

    request_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    pair_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_id: str = Field(min_length=1)
    order_index: Literal[0, 1]
    left_model: str = Field(min_length=1)
    right_model: str = Field(min_length=1)
    instruction: str
    left_response: str
    right_response: str
    judge_model: str = Field(min_length=1)
    prompt_template_id: str = Field(min_length=1)
    system_prompt: str
    user_prompt: str
    estimated_input_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_distinct_models(self) -> JudgeRequest:
        if self.left_model == self.right_model:
            raise ValueError("left_model and right_model must differ")
        return self


class JudgeDryRunResult(StrictModel):
    """Paths and counts from one zero-cost request-rendering run."""

    requests_path: Path
    report_path: Path
    question_count: int
    model_count: int
    request_count: int
    estimated_input_tokens: int
    maximum_output_tokens: int


def load_judge_config(path: Path) -> JudgeConfig:
    """Load a strict YAML judge configuration."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise JudgePreparationError("judge config must be a YAML mapping")
    return JudgeConfig.model_validate(payload)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_tokens(text: str) -> int:
    """Estimate tokens as ceil(UTF-8 bytes / 4), with a one-token minimum."""

    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def _response_matrix(
    responses: list[ResponseRecord],
) -> tuple[list[str], list[str], dict[tuple[str, str], ResponseRecord]]:
    by_question: dict[str, list[ResponseRecord]] = defaultdict(list)
    for response in responses:
        by_question[response.question_id].append(response)
    if not by_question:
        raise JudgePreparationError("responses file is empty")

    matrix: dict[tuple[str, str], ResponseRecord] = {}
    expected_models: set[str] | None = None
    for question_id, question_responses in sorted(by_question.items()):
        models = [response.model_id for response in question_responses]
        if len(models) != len(set(models)):
            raise JudgePreparationError(
                f"question {question_id} has duplicate model responses"
            )
        model_set = set(models)
        if expected_models is None:
            expected_models = model_set
        elif model_set != expected_models:
            raise JudgePreparationError(
                f"question {question_id} has model set {sorted(model_set)}, "
                f"expected {sorted(expected_models)}"
            )
        instructions = {response.instruction for response in question_responses}
        if len(instructions) != 1:
            raise JudgePreparationError(
                f"question {question_id} has inconsistent instructions"
            )
        for response in question_responses:
            matrix[(question_id, response.model_id)] = response

    assert expected_models is not None
    if len(expected_models) < 2:
        raise JudgePreparationError("at least two response models are required")
    return sorted(by_question), sorted(expected_models), matrix


def _render_request(
    *,
    question_id: str,
    order_index: Literal[0, 1],
    left: ResponseRecord,
    right: ResponseRecord,
    config: JudgeConfig,
    system_prompt: str,
    prompt_template: str,
    prompt_template_id: str,
) -> JudgeRequest:
    user_prompt = prompt_template.format(
        instruction=left.instruction,
        left_response=left.response,
        right_response=right.response,
    )
    canonical_models = sorted((left.model_id, right.model_id))
    pair_id = _sha256_bytes(
        json.dumps(
            [question_id, *canonical_models],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    request_payload = {
        "pair_id": pair_id,
        "order_index": order_index,
        "left_model": left.model_id,
        "right_model": right.model_id,
        "judge_model": config.model,
        "temperature": config.temperature,
        "max_output_tokens": config.max_output_tokens,
        "system_prompt_sha256": _sha256_bytes(system_prompt.encode("utf-8")),
        "user_prompt_sha256": _sha256_bytes(user_prompt.encode("utf-8")),
    }
    request_id = _sha256_bytes(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return JudgeRequest(
        request_id=request_id,
        pair_id=pair_id,
        question_id=question_id,
        order_index=order_index,
        left_model=left.model_id,
        right_model=right.model_id,
        instruction=left.instruction,
        left_response=left.response,
        right_response=right.response,
        judge_model=config.model,
        prompt_template_id=prompt_template_id,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        estimated_input_tokens=estimate_tokens(system_prompt)
        + estimate_tokens(user_prompt),
    )


def render_judge_requests(config: JudgeConfig) -> list[JudgeRequest]:
    """Render both presentation orders for every model pair and question."""

    responses_digest = _sha256_file(config.responses)
    if responses_digest != config.expected_responses_sha256:
        raise JudgePreparationError(
            f"responses SHA-256 mismatch: expected "
            f"{config.expected_responses_sha256}, got {responses_digest}"
        )
    responses = read_jsonl(config.responses, ResponseRecord)
    question_ids, model_ids, matrix = _response_matrix(responses)
    prompt_template = config.prompt_template.read_text(encoding="utf-8")
    system_prompt = config.system_prompt_template.read_text(encoding="utf-8").strip()
    prompt_digest = _sha256_bytes(prompt_template.encode("utf-8"))
    prompt_template_id = f"{config.prompt_template.stem}:{prompt_digest[:12]}"

    requests: list[JudgeRequest] = []
    for question_id in question_ids:
        for model_a, model_b in itertools.combinations(model_ids, 2):
            first = matrix[(question_id, model_a)]
            second = matrix[(question_id, model_b)]
            requests.append(
                _render_request(
                    question_id=question_id,
                    order_index=0,
                    left=first,
                    right=second,
                    config=config,
                    system_prompt=system_prompt,
                    prompt_template=prompt_template,
                    prompt_template_id=prompt_template_id,
                )
            )
            requests.append(
                _render_request(
                    question_id=question_id,
                    order_index=1,
                    left=second,
                    right=first,
                    config=config,
                    system_prompt=system_prompt,
                    prompt_template=prompt_template,
                    prompt_template_id=prompt_template_id,
                )
            )
    return requests


def _dry_run_report(
    config: JudgeConfig,
    requests: list[JudgeRequest],
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    question_ids = {request.question_id for request in requests}
    model_ids = {
        model_id
        for request in requests
        for model_id in (request.left_model, request.right_model)
    }
    input_tokens = [request.estimated_input_tokens for request in requests]
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "mode": "dry_run",
        "provider": config.provider,
        "judge_model": config.model,
        "paid_requests_executed": 0,
        "question_count": len(question_ids),
        "model_count": len(model_ids),
        "request_count": len(requests),
        "ordered_requests_per_pair": 2,
        "token_estimator": TOKEN_ESTIMATOR,
        "estimated_input_tokens": {
            "total": sum(input_tokens),
            "minimum": min(input_tokens),
            "maximum": max(input_tokens),
            "mean": sum(input_tokens) / len(input_tokens),
        },
        "maximum_output_tokens": {
            "per_request": config.max_output_tokens,
            "total": len(requests) * config.max_output_tokens,
        },
        "requests_sha256": _sha256_file(config.output_dir / "judge_requests.jsonl"),
        "prompt_sha256": _sha256_file(config.prompt_template),
        "system_prompt_sha256": _sha256_file(config.system_prompt_template),
        "responses_sha256": _sha256_file(config.responses),
    }


def judge_dry_run(
    config: JudgeConfig,
    *,
    generated_at: datetime | None = None,
) -> JudgeDryRunResult:
    """Write all requests and an estimate report without provider calls."""

    if config.provider != "dry_run":
        raise JudgePreparationError(
            "only provider='dry_run' is implemented; no paid call was attempted"
        )
    requests = render_judge_requests(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    requests_path = config.output_dir / "judge_requests.jsonl"
    report_path = config.output_dir / "dry_run_report.json"
    write_jsonl(requests_path, requests)
    report = _dry_run_report(
        config,
        requests,
        generated_at=generated_at or datetime.now(UTC),
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return JudgeDryRunResult(
        requests_path=requests_path,
        report_path=report_path,
        question_count=report["question_count"],
        model_count=report["model_count"],
        request_count=report["request_count"],
        estimated_input_tokens=report["estimated_input_tokens"]["total"],
        maximum_output_tokens=report["maximum_output_tokens"]["total"],
    )
