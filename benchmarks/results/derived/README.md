# Derived Results Index

> Derived artifacts are **regenerated, never mutated**: every entry below was
> produced offline from an immutable raw archive (read-only, SHA-256 verified
> before/after) by a versioned regrade pipeline. Raw archives and canonical
> payloads are never edited in place; a new dated directory supersedes an old
> one, it does not replace it.

## Current publication evidence

| Directory | Scope | Status |
|---|---|---|
| `2026-11-18-stage1-full-v3/` | **Full Stage-1: all 10 benchmarks, both models**, current graders (GSM8K **numeric-v6** extractor), per-model canonical statistics | **Current** — the full 10-benchmark publication evidence for Stage-1 |
| `2026-11-18-stage1-full-v2/` | Full Stage-1 regrade, GSM8K rows graded by the earlier **numeric-v5** extractor | Superseded by v3's extractor-v6 correction (v2 preserved unchanged — read for provenance history only; only its GSM8K rows differ) |
| `2026-11-18-stage1-full-v1/` | Full Stage-1 regrade, GSM8K rows graded by the earlier **numeric-v4** extractor | Superseded by v2's extractor-v5 correction (v1 preserved unchanged) |
| `2026-11-18-stage1-gsm8k-v4/` | GSM8K only, both models, `grade_gsm8k-numeric-v4` | Interim — superseded (first by v1, then by v2, then by v3); contents untouched |

## Why v3 supersedes v2 (GSM8K extractor v5 → v6)

A final audit found the v5 extractor mangled correct stated answers given in
explicit clock form (H:MM am/pm) — the time separator let the numeric
heuristics grab the wrong fragment (e.g. `4:30 pm` → 30). **v6** recognizes
explicit clock-form answers in plain, bold, and `\boxed{}` LaTeX forms before
falling back to the v5 priority ladder (official `####` marker → `\boxed{}`
→ `Answer: N` with last-marker-wins → last bold span → `answer is` /
`total =` → last separator-aware number). The correction touches exactly
**six trials per model, all on task `gsm8k-1001`**. Only the GSM8K rows
changed between v2 and v3 — the other nine benchmarks' per-arm success
counts are identical in both directories. Full rationale and measured
impact: the v3 directory's own `README.md`. (v2 had superseded v1 for a
different GSM8K reason: the v4 extractor lost answers carrying
unit-conversion restatements or trailing context, e.g.
`'**Answer: 160 minutes (2 hours 40 minutes).**'` → 40.)

## What "current" means and what it does not

- `2026-11-18-stage1-full-v3` re-grades **all 63,348 archived Stage-1 trials**
  with the current graders (`benchmarks/run_public_bench.py`, grader
  version `run_public_bench-numeric-v6`, grader-source SHA-256
  `bdbc5208675883e8f45806246345a0e81cd430e70415a7150fba882eabbb2d8e`),
  producing per-model derived artifacts and per-model canonical statistics
  (`benchmarks/canonical_results.py`). Models are never pooled.
- **Expectations are reconstructed from the archived `grader_detail`
  strings**, not independently validated gold data. The archives carry no
  `expected` field; the regrade re-derives each expected value from the
  recorded `expected=` token. This is a current-grader derived result, not an
  independent gold validation.
- Two malformed GSM8K tasks (`gsm8k-0489`, `gsm8k-1113`) yield **12
  `grader_error` trials per model — 6 per arm** (24 across both models),
  counted as failures. ARC's 22 numeric answerKeys per model use a positional
  fallback (1→A … 4→D). GLM and gpt-oss bbh_arith slices are 200 vs 250 tasks
  — not comparable across models.
- Archives document `max_tokens=2048` but carry no `finish_reason`: cap/empty
  fields are reconstructed (`cap_exhausted = output_tokens >= 2048`; empty
  final answers fail as `empty_response`). The canonical `truncated` counters
  are zero **because no truncated bool / finish_reason was recorded** — this
  is not evidence of zero truncation; the derived `failure_class="truncated"`
  counts are 3 for GLM (per-arm split 2/1: 2 classic gsm8k, 1 tahoe race) and
  0 for gpt-oss.

## Headline (derived, current graders, all 10 Stage-1 benchmarks)

| Model | Classic | TAHOE | Δ micro (tahoe−classic) | Output ratio | Total ratio | Spend/success (cl → tah) |
|---|---|---|---|---|---|---|
| GLM-5.3-Flash | 15,125/15,762 = 95.9586% | 15,203/15,762 = 96.4535% | +0.4949pp | 0.5105 | 0.9310 | 465.88 → 431.50 |
| gpt-oss-120b | 14,865/15,912 = 93.4201% | 14,835/15,912 = 93.2315% | −0.1885pp | 0.6824 | 1.0107 | 561.15 → 568.30 |

The overall deltas are **not** called significant or null-tested anywhere:
the canonical paired inferential family is per benchmark (Holm over 10
comparisons per model); there is no overall confirmatory test and no
prespecified equivalence margin. Derived significant pass-rate permutation
results (Holm): GLM GSM8K — tahoe higher, p=0.0010; gpt-oss GSM8K — tahoe
higher, p=0.0060; gpt-oss RACE — **classic** higher, p=0.0162 (unchanged
since v1 — RACE grading did not change).

## Pipeline (completed; deterministic; repo-root)

```bash
# 1. Regrade each raw archive → derived artifact (CLI: fix_stage1_extraction.py)
PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.run.json

PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.run.json

# 2. Canonical statistics per model
python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000
```

Helper pipeline module: `benchmarks/stage1_regrade.py` (generalizes
`benchmarks/gsm8k_regrade.py` from one benchmark to all ten). Full commands,
SHA-256 pins (grader source, pipeline, CLI, derived and canonical artifacts),
determinism verification, and data-limitation notes: the v3 directory's own
`2026-11-18-stage1-full-v3/README.md`.

## Rendering docs from these payloads

`benchmarks/render_canonical_docs.py` renders Markdown/LaTeX blocks from a
canonical payload (read-only; blocks in docs are updated via
`--update PATH`, verified via `--check PATH`):

```bash
python3 benchmarks/render_canonical_docs.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-canonical/canonical_results.json \
  --check README.md --block summary@glm
```

Generated per-model documents:
`2026-11-18-stage1-full-v3/{glm,oss}-canonical/canonical_results.md`
(deterministic renders of the JSON payloads; the JSON artifacts are the
source of truth — do not hand-edit either).
