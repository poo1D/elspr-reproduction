"""Reproducible LoRA planning and guarded CUDA training execution."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from elspr.io import read_jsonl
from elspr.schemas import StrictModel
from elspr.training.variants import TrainingExample


class TrainingRunError(RuntimeError):
    """Raised when a training plan or execution violates provenance gates."""


class TrainingRunConfig(StrictModel):
    """Pinned model, LoRA, batch, and resource configuration."""

    model_id: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    seed: int = Field(ge=0)
    lora_rank: int = Field(gt=0)
    lora_alpha: int = Field(gt=0)
    lora_dropout: float = Field(ge=0, lt=1)
    lora_target_modules: list[str] = Field(min_length=1)
    epochs: float = Field(gt=0)
    learning_rate: float = Field(gt=0)
    per_device_batch_size: int = Field(gt=0)
    gradient_accumulation_steps: int = Field(gt=0)
    expected_device_count: int = Field(gt=0)
    expected_global_batch_size: int = Field(gt=0)
    max_sequence_length: int = Field(gt=0)
    bf16: bool
    gradient_checkpointing: bool
    variants_dir: Path
    output_dir: Path
    minimum_free_disk_gib: float = Field(gt=0)
    minimum_gpu_memory_gib: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_global_batch(self) -> TrainingRunConfig:
        calculated = (
            self.per_device_batch_size
            * self.gradient_accumulation_steps
            * self.expected_device_count
        )
        if calculated != self.expected_global_batch_size:
            raise ValueError(
                f"global batch mismatch: calculated {calculated}, "
                f"expected {self.expected_global_batch_size}"
            )
        return self


class TrainingResourceSnapshot(StrictModel):
    """Local resource evidence captured before training."""

    system: str
    machine: str
    total_memory_gib: float
    free_disk_gib: float
    torch_available: bool
    cuda_available: bool
    cuda_device_count: int
    cuda_devices: list[dict[str, Any]]


class TrainingPlanResult(StrictModel):
    """Written no-GPU plan for one variant."""

    plan_path: Path
    run_id: str
    variant: Literal["raw", "cleaned", "random"]
    example_count: int
    data_sha256: str
    resources: TrainingResourceSnapshot


def load_training_run_config(path: Path) -> TrainingRunConfig:
    """Load a strict YAML LoRA configuration."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TrainingRunError("training config must be a YAML mapping")
    return TrainingRunConfig.model_validate(payload)


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _total_memory_gib() -> float:
    if hasattr(platform, "system") and platform.system() == "Darwin":
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(result.stdout.strip()) / 1024**3
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / 1024**3
    except (OSError, ValueError):
        return 0.0


def inspect_training_resources(path: Path) -> TrainingResourceSnapshot:
    """Inspect disk, memory, and CUDA without downloading model assets."""

    disk = shutil.disk_usage(path)
    torch_available = importlib.util.find_spec("torch") is not None
    cuda_available = False
    device_count = 0
    devices: list[dict[str, Any]] = []
    if torch_available:
        import torch

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            device_count = torch.cuda.device_count()
            for index in range(device_count):
                properties = torch.cuda.get_device_properties(index)
                devices.append(
                    {
                        "index": index,
                        "name": properties.name,
                        "total_memory_gib": properties.total_memory / 1024**3,
                        "capability": list(torch.cuda.get_device_capability(index)),
                    }
                )
    return TrainingResourceSnapshot(
        system=platform.system(),
        machine=platform.machine(),
        total_memory_gib=_total_memory_gib(),
        free_disk_gib=disk.free / 1024**3,
        torch_available=torch_available,
        cuda_available=cuda_available,
        cuda_device_count=device_count,
        cuda_devices=devices,
    )


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _validate_variant_artifact(
    config: TrainingRunConfig,
    variant: Literal["raw", "cleaned", "random"],
) -> tuple[Path, int, int, str]:
    manifest_path = config.variants_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_path = config.variants_dir / f"{variant}.jsonl"
    size, digest = _sha256_file(data_path)
    try:
        expected = manifest["artifacts"][variant]
    except (KeyError, TypeError) as error:
        raise TrainingRunError(f"variant manifest is invalid: {error}") from error
    if (
        expected["bytes"] != size
        or expected["sha256"] != digest
        or expected["rows"] != sum(1 for _ in read_jsonl(data_path, TrainingExample))
    ):
        raise TrainingRunError(f"{variant} data does not match its manifest")
    examples = read_jsonl(data_path, TrainingExample)
    if not examples:
        raise TrainingRunError(f"{variant} training data is empty")
    return data_path, len(examples), size, digest


def plan_training(
    config: TrainingRunConfig,
    *,
    variant: Literal["raw", "cleaned", "random"],
    generated_at: datetime | None = None,
) -> TrainingPlanResult:
    """Validate one variant and write a complete no-GPU execution plan."""

    data_path, example_count, data_bytes, data_digest = _validate_variant_artifact(
        config,
        variant,
    )
    resources = inspect_training_resources(config.output_dir.parent)
    config_payload = config.model_dump(mode="json")
    run_id = hashlib.sha256(
        json.dumps(
            {
                "variant": variant,
                "data_sha256": data_digest,
                "config": config_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    run_dir = config.output_dir / f"{variant}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    plan_path = run_dir / "plan.json"
    plan = {
        "schema_version": 1,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "run_id": run_id,
        "status": "planned",
        "variant": variant,
        "git_commit": _git_commit(),
        "data": {
            "path": str(data_path),
            "rows": example_count,
            "bytes": data_bytes,
            "sha256": data_digest,
        },
        "config": config_payload,
        "resources": resources.model_dump(mode="json"),
    }
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return TrainingPlanResult(
        plan_path=plan_path,
        run_id=run_id,
        variant=variant,
        example_count=example_count,
        data_sha256=data_digest,
        resources=resources,
    )


def _assert_training_resources(
    config: TrainingRunConfig,
    resources: TrainingResourceSnapshot,
) -> None:
    if resources.free_disk_gib < config.minimum_free_disk_gib:
        raise TrainingRunError(
            f"free disk {resources.free_disk_gib:.2f} GiB is below required "
            f"{config.minimum_free_disk_gib:.2f} GiB"
        )
    if not resources.torch_available:
        raise TrainingRunError("training dependencies are not installed")
    if not resources.cuda_available:
        raise TrainingRunError("CUDA is required for this reproduction training run")
    if resources.cuda_device_count != config.expected_device_count:
        raise TrainingRunError(
            f"found {resources.cuda_device_count} CUDA devices, expected "
            f"{config.expected_device_count}"
        )
    insufficient = [
        device
        for device in resources.cuda_devices
        if device["total_memory_gib"] < config.minimum_gpu_memory_gib
    ]
    if insufficient:
        raise TrainingRunError(
            f"CUDA devices below {config.minimum_gpu_memory_gib:.2f} GiB: "
            f"{[device['index'] for device in insufficient]}"
        )


def train_lora(
    config: TrainingRunConfig,
    *,
    variant: Literal["raw", "cleaned", "random"],
    execute_training: bool,
    resume_from_checkpoint: Path | None = None,
) -> TrainingPlanResult:
    """Plan a run and, only when explicitly enabled, execute PEFT LoRA training."""

    plan = plan_training(config, variant=variant)
    if not execute_training:
        return plan
    _assert_training_resources(config, plan.resources)

    try:
        import torch
        from peft import LoraConfig, TaskType, get_peft_model
        from torch.utils.data import Dataset
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
            set_seed,
        )
    except ImportError as error:
        raise TrainingRunError(
            "install the training extra before execution: uv sync --extra training"
        ) from error

    examples = read_jsonl(
        config.variants_dir / f"{variant}.jsonl",
        TrainingExample,
    )
    set_seed(config.seed)
    tokenizer = AutoTokenizer.from_pretrained(
        config.model_id,
        revision=config.model_revision,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    class EvaluatorDataset(Dataset[Any]):
        def __init__(self, rows: list[TrainingExample]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int) -> dict[str, Any]:
            row = self.rows[index]
            prompt_messages = [
                {"role": "system", "content": row.system_prompt},
                {"role": "user", "content": row.user_prompt},
            ]
            full_messages = [
                *prompt_messages,
                {"role": "assistant", "content": row.assistant_response},
            ]
            prompt_text = tokenizer.apply_chat_template(
                prompt_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            full_text = tokenizer.apply_chat_template(
                full_messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            encoded = tokenizer(
                full_text,
                truncation=True,
                max_length=config.max_sequence_length,
                padding="max_length",
                return_tensors="pt",
            )
            prompt_ids = tokenizer(
                prompt_text,
                truncation=True,
                max_length=config.max_sequence_length,
                add_special_tokens=False,
            )["input_ids"]
            labels = encoded["input_ids"][0].clone()
            labels[: min(len(prompt_ids), len(labels))] = -100
            labels[encoded["attention_mask"][0] == 0] = -100
            return {
                "input_ids": encoded["input_ids"][0],
                "attention_mask": encoded["attention_mask"][0],
                "labels": labels,
            }

    model = AutoModelForCausalLM.from_pretrained(
        config.model_id,
        revision=config.model_revision,
        torch_dtype=torch.bfloat16 if config.bf16 else torch.float32,
    )
    if config.gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config.lora_rank,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            target_modules=config.lora_target_modules,
            bias="none",
        ),
    )
    run_dir = plan.plan_path.parent
    arguments = TrainingArguments(
        output_dir=str(run_dir / "checkpoints"),
        num_train_epochs=config.epochs,
        learning_rate=config.learning_rate,
        per_device_train_batch_size=config.per_device_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        bf16=config.bf16,
        gradient_checkpointing=config.gradient_checkpointing,
        save_strategy="epoch",
        logging_steps=1,
        seed=config.seed,
        data_seed=config.seed,
        report_to=[],
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=EvaluatorDataset(examples),
    )
    trainer.train(
        resume_from_checkpoint=(
            str(resume_from_checkpoint) if resume_from_checkpoint else None
        )
    )
    model.save_pretrained(run_dir / "adapter")
    tokenizer.save_pretrained(run_dir / "adapter")
    completed = json.loads(plan.plan_path.read_text(encoding="utf-8"))
    completed["status"] = "completed"
    completed["completed_at"] = datetime.now(UTC).isoformat()
    completed["metrics"] = trainer.state.log_history
    plan.plan_path.write_text(
        json.dumps(completed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return plan
