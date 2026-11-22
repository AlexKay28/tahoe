# Derived GSM8K v4 regrade — 2026-11-18 (stage1, derived-only)

Immutable derived GSM8K results re-graded offline from the two raw
2026-09-13 stage1-full archives with the current
`grade_gsm8k` (numeric-v4) implementation. No model evaluations were run
and no raw archive was modified (verified by SHA-256 before/after).
Models are never pooled: one derived artifact and one canonical pair per
model.

## Exact commands (run from the repo root)

```bash
PYTHONPATH=src python3 benchmarks/fix_gsm8k_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-gsm8k-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-gsm8k-derived.run.json

PYTHONPATH=src python3 benchmarks/fix_gsm8k_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-gsm8k-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-gsm8k-derived.run.json

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-gsm8k-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-gsm8k-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000
```

Determinism check: both canonical generations were repeated to a
temporary path with identical options; all four files were
byte-identical (`cmp`), and the temporary duplicates were then removed.

## Grader

- `grade_gsm8k` version: `grade_gsm8k-numeric-v4`; regrader version `2`;
  derived schema `tahoe/gsm8k-derived-results/1`.
- Grader source: `benchmarks/run_public_bench.py`,
  SHA-256 `5153620db7c0632d5c094315c4fe76e2592cae762f5b8371a8836b00ae3190b3`.

## Inputs and outputs (SHA-256)

| role | file | SHA-256 |
|---|---|---|
| raw input (GLM, read-only, unchanged) | `benchmarks/results/2026-09-13-stage1-full/full_test_eval.json` | `43ca713f08acc2c72bfed10d74eab4943ea4d128933dc67da9ca0344347deacf` |
| raw input (gpt-oss, read-only, unchanged) | `benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json` | `771be2ee59da30df186df2c73d64931fbf32c7d772f6a5afe313bbb58160eff9` |
| derived output (GLM) | `glm-gsm8k-derived.json` | `b0fff755493a006b062bcd9f05b2ed6758673649df3fdf504162625f1ea601b6` |
| derived output (gpt-oss) | `oss-gsm8k-derived.json` | `b18b2819b2909cb5f955f6b008421861ef8c735d5239505345e7e74441b1ed64` |
| run sidecar (GLM) | `glm-gsm8k-derived.run.json` | `076a089ec0cef584968c00b38cdabb9da5b35528e88e735a9ebb908c1a894a05` |
| run sidecar (gpt-oss) | `oss-gsm8k-derived.run.json` | `246675a67b08385b81b57c986fbb87a99dabf065ae09dd366df12b20326c5f6e` |
| canonical JSON (GLM) | `glm-canonical/canonical_results.json` | `c360e751ac77b879af8a11cc8de3a984ff1b6c2bcb94b5cfc68ff4fe703c2d65` |
| canonical MD (GLM) | `glm-canonical/canonical_results.md` | `aac5bf804518841ace6b60cd8beaa88b9a10834ffe3a01d1d436312a0a0e8be7` |
| canonical JSON (gpt-oss) | `oss-canonical/canonical_results.json` | `99b3b1c093e044046ff29a071d9360e22d7f03a09265bebe0c340ce39631972b` |
| canonical MD (gpt-oss) | `oss-canonical/canonical_results.md` | `92a347e4873040e7a0af3800e19df88e340f20db9792cb038c674ce07285213f` |

## Regrade summary (per derived artifact)

Each archive contributes 7,914 GSM8K trials (1,319 tasks × 3 trials × 2
arms; classic/tahoe 3,957 each); non-GSM8K trials are skipped.

| model | passed | wrong_answer | grader_errors | fail→pass | pass→fail |
|---|---|---|---|---|---|
| GLM | 7,572 | 330 | 12 (6 classic / 6 tahoe) | 1,702 | 18 |
| gpt-oss | 7,431 | 471 | 12 (6 classic / 6 tahoe) | 1,247 | 40 |

## Canonical statistics (seed 42, 10,000 resamples / 10,000 permutations)

### GLM (`glm-canonical/`)

| arm | trials | micro acc | macro acc | total tokens | spend/success |
|---|---|---|---|---|---|
| classic | 3,957 | 0.9447 | 0.9447 | 1,236,303 | 330.74 |
| tahoe | 3,957 | 0.9689 | 0.9689 | 992,359 | 258.83 |

Paired `gsm8k/classic_vs_tahoe`: 1,319 tasks / 3,957 pairs; pass rate
classic 0.94466 vs tahoe 0.96892 (difference classic−tahoe −0.02426);
mean token difference classic−tahoe +61.65; permutation p = 9.999e-05
(Holm 9.999e-05); pass-rate permutation p (Holm) 9.999e-05; paired z
p (Holm) 5.57e-09; Wilcoxon p (Holm) 0.0.

### gpt-oss (`oss-canonical/`)

| arm | trials | micro acc | macro acc | total tokens | spend/success |
|---|---|---|---|---|---|
| classic | 3,957 | 0.9313 | 0.9313 | 1,765,457 | 479.09 |
| tahoe | 3,957 | 0.9467 | 0.9467 | 1,373,530 | 366.67 |

Paired `gsm8k/classic_vs_tahoe`: 1,319 tasks / 3,957 pairs; pass rate
classic 0.93126 vs tahoe 0.94668 (difference classic−tahoe −0.01542);
mean token difference classic−tahoe +99.05; permutation p = 9.999e-05
(Holm 9.999e-05); pass-rate permutation p (Holm) 2.9997e-04; paired z
p (Holm) 2.31e-04; Wilcoxon p (Holm) 0.0.

Micro = trial-pooled accuracy; macro = task-equal-weighted accuracy
(one trial per task per arm here, so the two coincide). Token
differences are per paired task-trial means (arm_a classic − arm_b
tahoe). Full per-benchmark detail, estimand definitions, and Holm
family corrections are in the canonical JSON/MD pair for each model.
