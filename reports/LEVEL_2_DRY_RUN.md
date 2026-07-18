# ELSPR Level 2 Data and Judge Dry-Run Report

## Outcome

The no-cost preparation portion of Level 2 is operational on real public
response data. It selectively downloads five pinned `helpful_base` files,
verifies their provenance, selects 50 shared questions, and renders every
ordered pairwise judge request.

No judge API request or model training was performed in this stage.

## Pinned data

- Upstream repository commit:
  `e9886b3a96f71cee654e1c758d03a026f3cbc32f`
- Response models: 5
- Shared upstream questions per model: 129
- Selected questions: 50
- Prepared responses: 250
- Selection: ascending SHA-256 of the UTF-8 instruction
- Prepared `responses.jsonl` bytes: 408,427
- Prepared `responses.jsonl` SHA-256:
  `6b18792d3df458d3f383d7e9c011dfa6cf836b605e25fbd0e0f24e8d45916116`
- Versioned manifest:
  `configs/manifests/level2_helpful_base_5x50.json`

The downloader reuses a cached source file only if both its byte length and
SHA-256 still match. It rejects schema changes, duplicate questions, differing
instruction sets, and an unexpected derived manifest.

## Judge request expansion

```text
50 questions * C(5 models, 2) * 2 presentation orders = 1,000 requests
```

Verified request invariants:

- 1,000 unique request IDs;
- 500 unique unordered pair IDs;
- exactly two request rows per pair ID;
- the two rows swap left/right models and responses;
- exactly 20 ordered requests per question;
- prompt, system prompt, response input, and request artifacts are hashed.

The rendered request JSONL is 7.1 MiB and remains under the ignored
`artifacts/raw/` tree. Its stable SHA-256 is:

`308dece526f571fe0f53273acc9fb3558787a2ca9da44a56235ee6e5bbbdca47`

## Token estimate

The dry run estimates:

- input tokens: 1,035,690 total;
- per-request input estimate: 424 minimum, 3,222 maximum, 1,035.69 mean;
- configured maximum output: 1,024 tokens per request, 1,024,000 total.

The estimator is explicitly approximate:

```text
utf8_bytes_div4_ceil_v1 = ceil(UTF-8 byte length / 4)
```

It is not a Qwen tokenizer result and must not be used as a final billing
quote. Provider-side token counting and current official pricing must be
checked before requesting budget approval.

## Validation

- Data stage commit:
  `1a920bd18992bef4317ec4b454ab15ab5f168bd9`
- Judge dry-run commit:
  `c3319b7eb0f54715898097ef79fc9517291b6b6c`
- Tests: 82 passed
- Ruff lint and format: passed
- Real selective download: passed
- Real 1,000-request dry run: passed twice with the same request artifact hash
- Paid requests executed: 0

## Remaining gates

Level 2 is not complete. It still requires:

1. a provider executor with cache, retries, rate limiting, idempotency, raw
   output retention, and resume;
2. explicit API credential and budget authorization before execution;
3. raw, cleaned, and size-matched random training sets;
4. three reproducible LoRA training variants;
5. unseen evaluation with `rho_non_trans` and `tau_avg`;
6. a conclusion-direction report with API cost, GPU time, and failure records.
