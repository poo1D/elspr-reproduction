"""Build reproducible raw, cleaned, and size-matched random SFT variants."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field

from elspr.io import read_jsonl, write_jsonl
from elspr.judging import JudgeRequest
from elspr.schemas import JudgmentRecord, StrictModel


class TrainingDataError(ValueError):
    """Raised when training variants cannot be traced or aligned."""


class TrainingDataConfig(StrictModel):
    """Inputs and output for deterministic SFT variant preparation."""

    data_manifest: Path
    judge_requests: Path
    raw_judgments: Path
    cleaned_judgments: Path
    output_dir: Path
    random_seed: int = Field(ge=0)


class TrainingExample(StrictModel):
    """One traceable evaluator SFT conversation."""

    request_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_id: str = Field(min_length=1)
    left_model: str = Field(min_length=1)
    right_model: str = Field(min_length=1)
    variant: Literal["raw", "cleaned", "random"]
    system_prompt: str
    user_prompt: str
    assistant_response: str


class TrainingVariantsResult(StrictModel):
    """Paths and counts for one variant build."""

    raw_path: Path
    cleaned_path: Path
    random_path: Path
    manifest_path: Path
    raw_count: int
    cleaned_count: int
    random_count: int


def load_training_data_config(path: Path) -> TrainingDataConfig:
    """Load a strict YAML variant-preparation config."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TrainingDataError("training data config must be a YAML mapping")
    return TrainingDataConfig.model_validate(payload)


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _judgment_key(record: JudgmentRecord) -> tuple[str, str, str]:
    return record.question_id, record.left_model, record.right_model


def _request_key(record: JudgeRequest) -> tuple[str, str, str]:
    return record.question_id, record.left_model, record.right_model


def _unique_by_key(
    records: list[JudgmentRecord],
    *,
    label: str,
) -> dict[tuple[str, str, str], JudgmentRecord]:
    indexed: dict[tuple[str, str, str], JudgmentRecord] = {}
    for record in records:
        key = _judgment_key(record)
        if key in indexed:
            raise TrainingDataError(f"{label} has duplicate judgment {key}")
        indexed[key] = record
    return indexed


def _load_split(path: Path) -> tuple[set[str], set[str], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        train_ids = set(payload["split"]["train_question_ids"])
        evaluation_ids = set(payload["split"]["evaluation_question_ids"])
        model_count = int(payload["model_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise TrainingDataError(f"invalid data manifest split: {error}") from error
    if not train_ids or not evaluation_ids:
        raise TrainingDataError("train and evaluation question sets must be non-empty")
    if train_ids & evaluation_ids:
        raise TrainingDataError("train and evaluation question sets overlap")
    if model_count < 2:
        raise TrainingDataError("data manifest requires at least two models")
    return train_ids, evaluation_ids, model_count


def _to_example(
    request: JudgeRequest,
    judgment: JudgmentRecord,
    *,
    variant: Literal["raw", "cleaned", "random"],
) -> TrainingExample:
    return TrainingExample(
        request_id=request.request_id,
        question_id=request.question_id,
        left_model=request.left_model,
        right_model=request.right_model,
        variant=variant,
        system_prompt=request.system_prompt,
        user_prompt=request.user_prompt,
        assistant_response=judgment.raw_output,
    )


def _artifact(path: Path) -> dict[str, Any]:
    size, digest = _sha256_file(path)
    with path.open(encoding="utf-8") as handle:
        rows = sum(1 for _ in handle)
    return {
        "path": path.name,
        "bytes": size,
        "sha256": digest,
        "rows": rows,
    }


def build_training_variants(
    config: TrainingDataConfig,
) -> TrainingVariantsResult:
    """Join prompts and judgments, enforce split isolation, and write variants."""

    train_ids, evaluation_ids, model_count = _load_split(config.data_manifest)
    requests = read_jsonl(config.judge_requests, JudgeRequest)
    unknown_request_ids = {
        request.question_id
        for request in requests
        if request.question_id not in train_ids | evaluation_ids
    }
    if unknown_request_ids:
        raise TrainingDataError(
            f"judge requests contain {len(unknown_request_ids)} unknown questions"
        )
    train_requests = [
        request for request in requests if request.question_id in train_ids
    ]
    expected_per_question = model_count * (model_count - 1)
    expected_raw_count = len(train_ids) * expected_per_question
    if len(train_requests) != expected_raw_count:
        raise TrainingDataError(
            f"expected {expected_raw_count} train requests, got {len(train_requests)}"
        )
    request_by_key: dict[tuple[str, str, str], JudgeRequest] = {}
    for request in train_requests:
        key = _request_key(request)
        if key in request_by_key:
            raise TrainingDataError(f"duplicate train request {key}")
        request_by_key[key] = request

    raw_all = read_jsonl(config.raw_judgments, JudgmentRecord)
    cleaned_all = read_jsonl(config.cleaned_judgments, JudgmentRecord)
    raw = [record for record in raw_all if record.question_id in train_ids]
    cleaned = [record for record in cleaned_all if record.question_id in train_ids]
    raw_by_key = _unique_by_key(raw, label="raw")
    cleaned_by_key = _unique_by_key(cleaned, label="cleaned")
    if set(raw_by_key) != set(request_by_key):
        missing = sorted(set(request_by_key) - set(raw_by_key))
        extra = sorted(set(raw_by_key) - set(request_by_key))
        raise TrainingDataError(
            f"raw judgments do not cover train requests; "
            f"missing={len(missing)} extra={len(extra)}"
        )
    if not set(cleaned_by_key) <= set(raw_by_key):
        raise TrainingDataError("cleaned judgments must be a subset of raw judgments")
    for key, cleaned_record in cleaned_by_key.items():
        if cleaned_record != raw_by_key[key]:
            raise TrainingDataError(f"cleaned judgment changed raw record {key}")

    ordered_keys = [_request_key(request) for request in train_requests]
    raw_examples = [
        _to_example(request_by_key[key], raw_by_key[key], variant="raw")
        for key in ordered_keys
    ]
    cleaned_examples = [
        _to_example(request_by_key[key], cleaned_by_key[key], variant="cleaned")
        for key in ordered_keys
        if key in cleaned_by_key
    ]
    randomizer = random.Random(config.random_seed)
    sampled_indices = sorted(
        randomizer.sample(range(len(raw_examples)), len(cleaned_examples))
    )
    random_examples = [
        raw_examples[index].model_copy(update={"variant": "random"})
        for index in sampled_indices
    ]

    config.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = config.output_dir / "raw.jsonl"
    cleaned_path = config.output_dir / "cleaned.jsonl"
    random_path = config.output_dir / "random.jsonl"
    manifest_path = config.output_dir / "manifest.json"
    write_jsonl(raw_path, raw_examples)
    write_jsonl(cleaned_path, cleaned_examples)
    write_jsonl(random_path, random_examples)
    manifest = {
        "schema_version": 1,
        "random_seed": config.random_seed,
        "train_question_count": len(train_ids),
        "evaluation_question_count": len(evaluation_ids),
        "model_count": model_count,
        "raw_count": len(raw_examples),
        "cleaned_count": len(cleaned_examples),
        "random_count": len(random_examples),
        "cleaned_retention": (
            len(cleaned_examples) / len(raw_examples) if raw_examples else 0.0
        ),
        "data_manifest_sha256": _sha256_file(config.data_manifest)[1],
        "judge_requests_sha256": _sha256_file(config.judge_requests)[1],
        "raw_judgments_sha256": _sha256_file(config.raw_judgments)[1],
        "cleaned_judgments_sha256": _sha256_file(config.cleaned_judgments)[1],
        "artifacts": {
            "raw": _artifact(raw_path),
            "cleaned": _artifact(cleaned_path),
            "random": _artifact(random_path),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return TrainingVariantsResult(
        raw_path=raw_path,
        cleaned_path=cleaned_path,
        random_path=random_path,
        manifest_path=manifest_path,
        raw_count=len(raw_examples),
        cleaned_count=len(cleaned_examples),
        random_count=len(random_examples),
    )
