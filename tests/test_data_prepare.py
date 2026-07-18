import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from elspr.cli import app
from elspr.data import (
    DataPreparationConfig,
    DataPreparationError,
    UpstreamResponseFile,
    prepare_data,
)
from elspr.io import read_jsonl
from elspr.schemas import ResponseRecord

runner = CliRunner()
COMMIT = "e9886b3a96f71cee654e1c758d03a026f3cbc32f"


def _write_upstream(
    path: Path,
    *,
    model_id: str,
    instructions: list[str],
) -> UpstreamResponseFile:
    payload = [
        {
            "dataset": "helpful_base",
            "generator": model_id,
            "instruction": instruction,
            "output": f"{model_id} answers {instruction}",
        }
        for instruction in instructions
    ]
    content = json.dumps(payload).encode()
    path.write_bytes(content)
    return UpstreamResponseFile(
        model_id=model_id,
        url=path.as_uri(),
        bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _config(
    tmp_path: Path,
    *,
    first_instructions: list[str],
    second_instructions: list[str] | None = None,
    question_limit: int = 2,
) -> DataPreparationConfig:
    first = _write_upstream(
        tmp_path / "first.json",
        model_id="model-a",
        instructions=first_instructions,
    )
    second = _write_upstream(
        tmp_path / "second.json",
        model_id="model-b",
        instructions=second_instructions or first_instructions,
    )
    return DataPreparationConfig(
        dataset="helpful_base",
        source="https://example.test/upstream",
        source_commit=COMMIT,
        question_limit=question_limit,
        output_dir=tmp_path / "output",
        files=[second, first],
    )


def test_prepare_data_verifies_aligns_and_selects_deterministically(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, first_instructions=["question z", "question a", "q"])
    generated_at = datetime(2026, 7, 18, tzinfo=UTC)

    result = prepare_data(config, generated_at=generated_at)
    responses = read_jsonl(result.responses_path, ResponseRecord)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    expected_ids = sorted(
        hashlib.sha256(value.encode()).hexdigest()
        for value in ["question z", "question a", "q"]
    )[:2]

    assert result.question_count == 2
    assert result.model_count == 2
    assert result.response_count == 4
    assert [record.question_id for record in responses] == [
        expected_ids[0],
        expected_ids[0],
        expected_ids[1],
        expected_ids[1],
    ]
    assert [record.model_id for record in responses] == [
        "model-a",
        "model-b",
        "model-a",
        "model-b",
    ]
    assert {record.source for record in responses} == {
        f"https://example.test/upstream@{COMMIT}"
    }
    assert manifest["selection"]["question_ids"] == expected_ids
    assert manifest["generated_at"] == "2026-07-18T00:00:00+00:00"
    assert (
        manifest["responses_artifact"]["bytes"] == result.responses_path.stat().st_size
    )
    assert (
        manifest["responses_artifact"]["sha256"]
        == hashlib.sha256(result.responses_path.read_bytes()).hexdigest()
    )


def test_prepare_data_rejects_cached_checksum_mismatch(tmp_path: Path) -> None:
    config = _config(tmp_path, first_instructions=["one", "two"])
    cached = config.output_dir / "downloads" / "model-a.json"
    cached.parent.mkdir(parents=True)
    cached.write_text("tampered", encoding="utf-8")

    with pytest.raises(DataPreparationError, match="expected .* bytes"):
        prepare_data(config)


def test_prepare_data_rejects_different_instruction_sets(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        first_instructions=["one", "two", "three"],
        second_instructions=["one", "two", "other"],
    )

    with pytest.raises(DataPreparationError, match="instruction sets differ"):
        prepare_data(config)


def test_prepare_data_rejects_limit_above_shared_questions(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        first_instructions=["one", "two"],
        question_limit=3,
    )

    with pytest.raises(DataPreparationError, match="question_limit=3 exceeds 2"):
        prepare_data(config)


def test_prepare_data_cli_writes_responses_and_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path, first_instructions=["one", "two"])
    config_path = tmp_path / "data.yaml"
    config_path.write_text(
        "\n".join(
            [
                "dataset: helpful_base",
                "source: https://example.test/upstream",
                f"source_commit: {COMMIT}",
                "question_limit: 1",
                f"output_dir: {config.output_dir}",
                "files:",
                *[
                    line
                    for item in config.files
                    for line in [
                        f"  - model_id: {item.model_id}",
                        f"    url: {item.url}",
                        f"    bytes: {item.bytes}",
                        f"    sha256: {item.sha256}",
                    ]
                ],
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["prepare-data", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "questions=1 models=2 responses=2" in result.output
    assert (config.output_dir / "responses.jsonl").exists()
    assert (config.output_dir / "manifest.json").exists()
