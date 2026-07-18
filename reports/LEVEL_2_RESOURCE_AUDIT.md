# ELSPR Level 2 Resource Audit

Audit date: 2026-07-18.

## Current host

| Resource | Verified state |
|---|---|
| Architecture | Apple Silicon `arm64` |
| GPU | Apple M4, 8 cores, Metal 4 |
| Unified memory | 16 GiB |
| NVIDIA CUDA | unavailable |
| Free data-volume disk | approximately 4.3 GiB |

The checks did not inspect or print secret values. The following expected
environment variables were all unset:

- `DASHSCOPE_API_KEY`;
- `QWEN_API_KEY`;
- `HF_TOKEN`;
- `HUGGING_FACE_HUB_TOKEN`;
- `WANDB_API_KEY`.

## Judge execution gate

The 10-request canary has an approximate worst-case cost of CNY 0.123161 under
the price snapshot and output cap recorded in `LEVEL_2_DRY_RUN.md`. No canary
was run because:

1. `DASHSCOPE_API_KEY` is not set;
2. no paid canary budget has been explicitly authorized.

The API key must be set locally as an environment variable and must not be
pasted into chat, configuration, Git, or a command whose output is recorded.

## Training gate

The pinned official model revision is:

```text
Qwen/Qwen2.5-7B-Instruct
a09a35458c702b33eeacc393d103063234e8bc28
```

The official Hugging Face repository reports approximately 15.2 GB of model
files:

`https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/tree/a09a35458c702b33eeacc393d103063234e8bc28`

The model weights alone exceed current free disk by more than 10 GB. The host
also has no CUDA device, while the guarded reproduction runner requires one
24-GiB-or-larger CUDA device and at least 25 GiB free disk. Therefore the
paper-shaped LoRA runs cannot execute on this host.

No remote or paid GPU has been authorized. Training remains gated until a
suitable CUDA environment is provided or explicitly approved.

## Implemented portable path

The repository can already:

- freeze a 40-question training and 10-question unseen split;
- generate raw, cleaned, and deterministic size-matched random SFT variants;
- validate that cleaned data is an unchanged subset of raw data;
- write hashed data manifests;
- plan pinned LoRA runs without downloading model assets;
- enforce global batch size 16 from per-device batch, accumulation, and device
  count;
- capture Git commit, config, input hash, hardware, disk, and dependency
  provenance;
- explicitly execute or resume Transformers + PEFT LoRA only after resource
  gates pass;
- strictly evaluate three returned model variants on only the frozen unseen
  questions.

These capabilities are code readiness, not evidence that the three required
models were trained.

## Unblocking inputs

To continue empirical execution, two separate approvals are needed:

1. locally set `DASHSCOPE_API_KEY` plus explicit authorization for a CNY 0.13
   maximum, 10-request canary;
2. after judgment/filter validation, access to an authorized CUDA training
   environment with at least 24 GiB GPU memory and 25 GiB free disk.

The full 1,000-request batch and any paid GPU run require their own later
approval; canary authorization does not imply either.
