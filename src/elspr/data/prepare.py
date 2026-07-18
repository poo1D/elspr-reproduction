"""Selective, checksum-verified preparation of public response data."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import AnyUrl, Field, model_validator

from elspr.io import write_jsonl
from elspr.schemas import ResponseRecord, StrictModel


class DataPreparationError(ValueError):
    """Raised when upstream data or its provenance does not match the config."""


class UpstreamResponseFile(StrictModel):
    """One pinned public response file."""

    model_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    url: AnyUrl
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_url_scheme(self) -> UpstreamResponseFile:
        if self.url.scheme not in {"https", "file"}:
            raise ValueError("url scheme must be https (or file for local tests)")
        return self


class DataPreparationConfig(StrictModel):
    """Validated selective-download and question-selection configuration."""

    dataset: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    question_limit: int = Field(ge=1)
    output_dir: Path
    files: list[UpstreamResponseFile] = Field(min_length=2)
    expected_manifest: Path | None = None

    @model_validator(mode="after")
    def validate_unique_models(self) -> DataPreparationConfig:
        model_ids = [item.model_id for item in self.files]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("files must contain unique model_id values")
        return self


class PreparedData(StrictModel):
    """Paths and counts produced by one preparation run."""

    responses_path: Path
    manifest_path: Path
    question_count: int
    model_count: int
    response_count: int


def load_data_config(path: Path) -> DataPreparationConfig:
    """Load a strict YAML data-preparation config."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DataPreparationError("data config must be a YAML mapping")
    return DataPreparationConfig.model_validate(payload)


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _verify_file(path: Path, expected: UpstreamResponseFile) -> None:
    size, digest = _sha256_file(path)
    if size != expected.bytes:
        raise DataPreparationError(
            f"{expected.model_id}: expected {expected.bytes} bytes, got {size}"
        )
    if digest != expected.sha256:
        raise DataPreparationError(
            f"{expected.model_id}: expected SHA-256 {expected.sha256}, got {digest}"
        )


def _download(expected: UpstreamResponseFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _verify_file(destination, expected)
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".part",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    request = urllib.request.Request(
        str(expected.url),
        headers={"User-Agent": "elspr-reproduction/0.1"},
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,  # noqa: S310
            temporary.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        _verify_file(temporary, expected)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_upstream_records(
    path: Path,
    *,
    expected_model: str,
    expected_dataset: str,
    expected_source: str,
) -> dict[str, ResponseRecord]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataPreparationError(f"cannot parse {path}: {error}") from error
    if not isinstance(payload, list):
        raise DataPreparationError(f"{path} must contain a JSON array")

    records: dict[str, ResponseRecord] = {}
    required_keys = {"dataset", "generator", "instruction", "output"}
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or set(item) != required_keys:
            raise DataPreparationError(
                f"{path} record {index} must have exactly {sorted(required_keys)}"
            )
        if item["dataset"] != expected_dataset:
            raise DataPreparationError(
                f"{path} record {index} has dataset {item['dataset']!r}, "
                f"expected {expected_dataset!r}"
            )
        if item["generator"] != expected_model:
            raise DataPreparationError(
                f"{path} record {index} has generator {item['generator']!r}, "
                f"expected {expected_model!r}"
            )
        instruction = item["instruction"]
        output = item["output"]
        if not isinstance(instruction, str) or not isinstance(output, str):
            raise DataPreparationError(
                f"{path} record {index} instruction/output must be strings"
            )
        question_id = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
        if question_id in records:
            raise DataPreparationError(
                f"{path} has duplicate instruction {question_id}"
            )
        records[question_id] = ResponseRecord(
            question_id=question_id,
            dataset=expected_dataset,
            instruction=instruction,
            model_id=expected_model,
            response=output,
            generation_config={},
            source=expected_source,
        )
    return records


def _manifest_payload(
    config: DataPreparationConfig,
    *,
    question_ids: list[str],
    generated_at: datetime,
    responses_bytes: int,
    responses_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "dataset": config.dataset,
        "source": config.source,
        "source_commit": config.source_commit,
        "selection": {
            "algorithm": "sha256_instruction_ascending",
            "question_limit": config.question_limit,
            "question_ids": question_ids,
        },
        "files": [
            {
                "model_id": item.model_id,
                "url": str(item.url),
                "bytes": item.bytes,
                "sha256": item.sha256,
            }
            for item in sorted(config.files, key=lambda value: value.model_id)
        ],
        "model_count": len(config.files),
        "question_count": len(question_ids),
        "response_count": len(config.files) * len(question_ids),
        "responses_artifact": {
            "path": "responses.jsonl",
            "bytes": responses_bytes,
            "sha256": responses_sha256,
        },
    }


def _verify_expected_manifest(
    path: Path,
    actual: dict[str, Any],
) -> None:
    expected = json.loads(path.read_text(encoding="utf-8"))
    comparable_actual = {
        key: value for key, value in actual.items() if key != "generated_at"
    }
    comparable_expected = {
        key: value for key, value in expected.items() if key != "generated_at"
    }
    if comparable_actual != comparable_expected:
        raise DataPreparationError(
            f"prepared data does not match expected manifest {path}"
        )


def prepare_data(
    config: DataPreparationConfig,
    *,
    generated_at: datetime | None = None,
) -> PreparedData:
    """Download, verify, align, select, and serialize the configured subset."""

    raw_dir = config.output_dir / "downloads"
    records_by_model: dict[str, dict[str, ResponseRecord]] = {}
    for expected in sorted(config.files, key=lambda value: value.model_id):
        destination = raw_dir / f"{expected.model_id}.json"
        _download(expected, destination)
        records_by_model[expected.model_id] = _read_upstream_records(
            destination,
            expected_model=expected.model_id,
            expected_dataset=config.dataset,
            expected_source=f"{config.source}@{config.source_commit}",
        )

    instruction_sets = {
        model_id: set(records) for model_id, records in records_by_model.items()
    }
    first_model = min(instruction_sets)
    shared_ids = instruction_sets[first_model]
    mismatched = [
        model_id
        for model_id, question_ids in instruction_sets.items()
        if question_ids != shared_ids
    ]
    if mismatched:
        raise DataPreparationError(
            f"instruction sets differ for models {sorted(mismatched)}"
        )
    if config.question_limit > len(shared_ids):
        raise DataPreparationError(
            f"question_limit={config.question_limit} exceeds {len(shared_ids)} "
            "shared instructions"
        )

    selected_ids = sorted(shared_ids)[: config.question_limit]
    responses = [
        records_by_model[model_id][question_id]
        for question_id in selected_ids
        for model_id in sorted(records_by_model)
    ]
    responses_path = config.output_dir / "responses.jsonl"
    manifest_path = config.output_dir / "manifest.json"
    write_jsonl(responses_path, responses)
    responses_bytes, responses_sha256 = _sha256_file(responses_path)
    manifest = _manifest_payload(
        config,
        question_ids=selected_ids,
        generated_at=generated_at or datetime.now(UTC),
        responses_bytes=responses_bytes,
        responses_sha256=responses_sha256,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if config.expected_manifest is not None:
        _verify_expected_manifest(config.expected_manifest, manifest)

    return PreparedData(
        responses_path=responses_path,
        manifest_path=manifest_path,
        question_count=len(selected_ids),
        model_count=len(records_by_model),
        response_count=len(responses),
    )
