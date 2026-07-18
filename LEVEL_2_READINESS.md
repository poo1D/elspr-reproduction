# Level 2 Readiness

## Decision

Level 2 can begin with public response data and no local model inference. The
smallest paper-shaped run should use 5 models, 50 shared questions, and both
response orders for every model pair. It requires 1,000 judge requests:

```text
C(5, 2) * 50 questions * 2 orders = 1,000 requests
```

This document is a readiness record, not evidence that those requests or any
fine-tuning run have already been completed.

As of 2026-07-18, the selective downloader, frozen manifest, real data
preparation, request rendering, and zero-cost dry run described below have
been implemented. See `reports/LEVEL_2_DRY_RUN.md` for measured results.

## Pinned response subset

Source repository: `https://github.com/yy0525/ELSPR`

Source commit: `e9886b3a96f71cee654e1c758d03a026f3cbc32f`

Each pinned path is
`data/selected_models/<model-directory>/helpful_base.json` and contains 129
records. All five files have the same 129 unique instructions and use the keys
`dataset`, `generator`, `instruction`, and `output`.

| Model directory | Bytes | SHA-256 |
|---|---:|---|
| `Meta-Llama-3-8B-Instruct` | 312,528 | `5acf5abb6489a3e0f8aa1f7d6d7c061898562445db7caf6f901160e4a30baafc` |
| `Mixtral-8x7B-Instruct-v0.1` | 218,432 | `81a63f65975b70e3ac0badf487fc12ddf9654be75a8d52f8b287cfb4f4623ca2` |
| `alpaca-7b` | 71,584 | `610a1c73eb60715a48d32ca9c03bbc90781dd10a022c8dca10ded5ef2a6c1676` |
| `gpt-3.5-turbo-0613` | 195,514 | `3ab3c0b6a0a3a3265afb828b002d7ae4f0fde946d8fcd19c155583f205e33a58` |
| `vicuna-7b` | 154,366 | `8de7919443b541f9f33da8b1f73153ad194c4ddd22adc032f97ad851c12d145f` |

The Level 2 downloader should fetch only these files from the pinned commit,
verify byte length and SHA-256, and keep downloaded data out of Git. The
upstream repository's Apache-2.0 license does not by itself settle the
licenses or redistribution terms of every model response, so this project
should publish URLs, hashes, and derived manifests rather than re-vendoring
the response corpus.

## Deterministic 50-question manifest

The first Level 2 commit should generate the question manifest as follows:

1. Verify that all five instruction sets are identical.
2. Compute `question_id = sha256(instruction.encode("utf-8")).hexdigest()`.
3. Sort records by `(question_id, instruction)`.
4. Select the first 50 records.
5. Write the source commit, file hashes, selection rule, selected IDs, and
   generation timestamp to a versioned manifest.

This avoids relying on upstream JSON array order while making the subset
exactly reproducible.

## Resource gates

| Resource | Current state | Consequence |
|---|---|---|
| Public response data | available and sample-verified | downloader and manifest work can proceed |
| Exact CoT judge prompt | available and pinned in `configs/prompts/` | request rendering can proceed |
| Qwen/DashScope API credential | not detected on 2026-07-18 | paid judge requests cannot run |
| Approved API budget | not provided | no paid requests are authorized |
| NVIDIA GPU | unavailable on the current Apple Silicon host | local LoRA reproduction cannot run here |
| Free disk | approximately 2.8 GiB during audit | do not fetch the full approximately 370 MB corpus or model weights |
| Exact paper training split/checkpoints | not published in audited assets | exact Level 3 reproduction remains blocked |

Credential detection checked only whether the expected environment variables
were set; it did not inspect or print secret values.

## Safe next sequence

Completed:

1. PR #1 was merged and Level 1 was tagged `v0.1.0-level1`;
2. `repro/level-2` and Draft PR #2 were created;
3. a hash-verifying selective downloader and frozen manifest were implemented;
4. all 1,000 requests were rendered in a zero-cost dry run.

Next:

1. add the resumable, cached, rate-limited provider executor;
2. verify provider-side token counts and current official pricing;
3. request explicit authorization for the credential and budget;
4. run judgments, then reuse the validated Level 1 graph/filter pipeline.

No paid API call, full-corpus download, GPU training, merge, or tag is
authorized by this readiness record.
