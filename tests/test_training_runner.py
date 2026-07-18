import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import elspr.training.runner as runner_module
from elspr.cli import app
from elspr.io import write_jsonl
from elspr.training import (
    TrainingExample,
    TrainingResourceSnapshot,
    TrainingRunConfig,
    TrainingRunError,
    plan_training,
    train_lora,
)

runner = CliRunner()


def _variant_fixture(tmp_path: Path) -> Path:
    variants = tmp_path / "variants"
    example = TrainingExample(
        request_id="1" * 64,
        question_id="q1",
        left_model="a",
        right_model="b",
        variant="raw",
        system_prompt="system",
        user_prompt="user",
        assistant_response="reasoning m",
    )
    artifacts: dict[str, dict[str, object]] = {}
    for variant in ["raw", "cleaned", "random"]:
        path = variants / f"{variant}.jsonl"
        write_jsonl(
            path,
            [example.model_copy(update={"variant": variant})],
        )
        content = path.read_bytes()
        artifacts[variant] = {
            "path": path.name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "rows": 1,
        }
    (variants / "manifest.json").write_text(
        json.dumps({"artifacts": artifacts}),
        encoding="utf-8",
    )
    return variants


def _config(tmp_path: Path) -> TrainingRunConfig:
    return TrainingRunConfig(
        model_id="Qwen/Qwen2.5-7B-Instruct",
        model_revision="a09a35458c702b33eeacc393d103063234e8bc28",
        seed=20260718,
        lora_rank=8,
        lora_alpha=16,
        lora_dropout=0.05,
        lora_target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        epochs=3,
        learning_rate=0.0001,
        per_device_batch_size=4,
        gradient_accumulation_steps=4,
        expected_device_count=1,
        expected_global_batch_size=16,
        max_sequence_length=4096,
        bf16=True,
        gradient_checkpointing=True,
        variants_dir=_variant_fixture(tmp_path),
        output_dir=tmp_path / "runs",
        minimum_free_disk_gib=25,
        minimum_gpu_memory_gib=24,
    )


def test_training_config_rejects_global_batch_mismatch(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with pytest.raises(ValidationError, match="global batch mismatch"):
        TrainingRunConfig.model_validate(
            {
                **config.model_dump(),
                "expected_global_batch_size": 8,
            }
        )


def test_plan_training_is_hash_pinned_without_model_download(tmp_path: Path) -> None:
    config = _config(tmp_path)
    generated_at = datetime(2026, 7, 18, tzinfo=UTC)

    first = plan_training(config, variant="raw", generated_at=generated_at)
    second = plan_training(config, variant="raw", generated_at=generated_at)
    payload = json.loads(first.plan_path.read_text(encoding="utf-8"))

    assert first.run_id == second.run_id
    assert first.example_count == 1
    assert payload["status"] == "planned"
    assert payload["variant"] == "raw"
    assert payload["data"]["sha256"] == first.data_sha256
    assert payload["config"]["expected_global_batch_size"] == 16
    assert payload["generated_at"] == "2026-07-18T00:00:00+00:00"


def test_train_without_execute_flag_only_writes_plan(tmp_path: Path) -> None:
    result = train_lora(
        _config(tmp_path),
        variant="cleaned",
        execute_training=False,
    )

    assert result.plan_path.exists()
    assert json.loads(result.plan_path.read_text())["status"] == "planned"


def test_training_execution_refuses_non_cuda_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = TrainingResourceSnapshot(
        system="Darwin",
        machine="arm64",
        total_memory_gib=16,
        free_disk_gib=100,
        torch_available=True,
        cuda_available=False,
        cuda_device_count=0,
        cuda_devices=[],
    )
    monkeypatch.setattr(
        runner_module,
        "inspect_training_resources",
        lambda _: snapshot,
    )

    with pytest.raises(TrainingRunError, match="CUDA is required"):
        train_lora(
            _config(tmp_path),
            variant="random",
            execute_training=True,
        )


def test_train_cli_defaults_to_plan_only(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config_path = tmp_path / "train.yaml"
    payload = config.model_dump(mode="json")
    config_path.write_text(
        "\n".join(
            [
                f"model_id: {payload['model_id']}",
                f"model_revision: {payload['model_revision']}",
                f"seed: {payload['seed']}",
                f"lora_rank: {payload['lora_rank']}",
                f"lora_alpha: {payload['lora_alpha']}",
                f"lora_dropout: {payload['lora_dropout']}",
                "lora_target_modules: [q_proj, k_proj, v_proj, o_proj]",
                f"epochs: {payload['epochs']}",
                f"learning_rate: {payload['learning_rate']}",
                f"per_device_batch_size: {payload['per_device_batch_size']}",
                (
                    "gradient_accumulation_steps: "
                    f"{payload['gradient_accumulation_steps']}"
                ),
                f"expected_device_count: {payload['expected_device_count']}",
                (
                    "expected_global_batch_size: "
                    f"{payload['expected_global_batch_size']}"
                ),
                f"max_sequence_length: {payload['max_sequence_length']}",
                "bf16: true",
                "gradient_checkpointing: true",
                f"variants_dir: {payload['variants_dir']}",
                f"output_dir: {payload['output_dir']}",
                f"minimum_free_disk_gib: {payload['minimum_free_disk_gib']}",
                f"minimum_gpu_memory_gib: {payload['minimum_gpu_memory_gib']}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["train", "--variant", "raw", "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    assert "variant=raw" in result.output
    assert "executed=False" in result.output
