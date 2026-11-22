# Stage-1 full derived artifacts — 2026-11-18 (v1)

Offline regrade of both raw 2026-09-13 stage1-full archives over **all ten
Stage-1 benchmarks** with the current graders, plus per-model canonical
statistics. No model evaluations, no API calls; the raw archives are
read-only and were verified byte-unchanged (SHA-256 before/after).
Models are **never pooled**: every artifact below is per model.

## Commands (exact, run from the repo root)

### Regrade (benchmarks/fix_stage1_extraction.py)

```bash
PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-stage1-derived.run.json

PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-stage1-derived.run.json
```

### Canonical statistics (benchmarks/canonical_results.py)

```bash
python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000
```

No `--include-raw-trials`, no `--include-per-task` (per-task comparisons are
skipped by default). Each derived artifact was also regenerated to a
temporary path and byte-compared; both derived JSONs and all four canonical
files are byte-identical across runs (temporary duplicates removed).

## Versions and spec

- Derived schema `tahoe/stage1-derived-results/1`; spec version
  `stage1-archived-results/2026-09-13`; regrader version `1`; grader
  version `run_public_bench-current`.
- Grader source `benchmarks/run_public_bench.py`,
  SHA-256 `5153620db7c0632d5c094315c4fe76e2592cae762f5b8371a8836b00ae3190b3`.
- Regrade pipeline `benchmarks/stage1_regrade.py`,
  SHA-256 `9adb385c2c6bbb1dcf6e86bdb2d0a3d426d0b2c6b85ceccc405effcd47b3479d`;
  CLI `benchmarks/fix_stage1_extraction.py`,
  SHA-256 `12e26ab583a5699b6c500f5778c1b80ff1855cdbd5ee0e81048c43068cfae485`.

## SHA-256

| file | SHA-256 |
|---|---|
| raw input (GLM, read-only) `results/2026-09-13-stage1-full/full_test_eval.json` | `43ca713f08acc2c72bfed10d74eab4943ea4d128933dc67da9ca0344347deacf` |
| raw input (gpt-oss, read-only) `results/2026-09-13-stage1-full/oss_full_eval.json` | `771be2ee59da30df186df2c73d64931fbf32c7d772f6a5afe313bbb58160eff9` |
| `glm-stage1-derived.json` | `27d177fbd02e620adf452a3874695109410e71f435ff458249a29d254064bd77` |
| `oss-stage1-derived.json` | `c3bab585fe9168fa84f976ba97804ea362204f15ccb1861dbfc5d6984c64ee8b` |
| `glm-stage1-derived.run.json` | `2303e06a3c98972653bc3c637d72a445fe662802275ed110508510f651169da8` |
| `oss-stage1-derived.run.json` | `fc56879f352a46f34c4053e0c4ee16c08cd6948082a15545faebf897aabcd697` |
| `glm-canonical/canonical_results.json` | `9fc6c726f09f7ee2ea896799e42405232d211144a40b85fd1bc878b241011833` |
| `glm-canonical/canonical_results.md` | `80623f7e70717b34e7263b2a12bf1a4a65a3d09071104f63369d3746339e953f` |
| `oss-canonical/canonical_results.json` | `6d61939476a1772d4d89038ca5e54d307c7105a39c2d75afaee0b390ca1f2cff` |
| `oss-canonical/canonical_results.md` | `7dc31cf9e7bd6a513de17a82ea37efb48b80263ff2fb75dc0c0d310c71798304` |

## Analysis provenance and options

`analysis_provenance` (schema `canonical-analysis/1`) pins the analysis
implementation: `benchmarks/canonical_results.py`
`9a7ca4b6ad08e965652d833d711e84fdf01a697cd2e925c65732b94bc244d31c`,
`benchmarks/report.py`
`be7ac408bfe0c592e6d7d7ae6152f1f7dd75cdde5818728fd008e1d62cef9975`,
`benchmarks/stats.py`
`d497684839594a1264e615be8d8440ee27210adf6e732026ea32bb649cb308b8`.
Options: seed 42, 10,000 bootstrap resamples, 10,000 permutation draws;
raw trials and per-task blocks excluded. Arm outcomes count
`grader_error` as a first-class outcome (`failure_class == "grader_error"`
literally).

## Expected answers: provenance caveat

**Expectations are reconstructed from the archived `grader_detail`
strings, not independently validated gold data.** The archives carry no
`expected` field; the regrade re-derives each expected value from the
`expected=` token recorded by the archived grader (`grader_error` on any
missing/malformed/inconsistent value). Nothing here constitutes an
independent re-labeling of the underlying datasets.

## Outcome reconstruction policy

Archives document max_tokens=2048 but carry no `finish_reason`. The
regrade records `output_token_cap=2048` and
`cap_exhausted = output_tokens >= 2048`; it never invents a
`finish_reason` and never sets a truncated flag from the cap alone.
Empty/missing final answers fail as `empty_response` (never graded into a
pass); nonempty cap-exhausted answers that fail grading are classified
`truncated` with explicit `outcome_provenance`; all other failing grades
are `wrong_answer`. Note the canonical `outcomes.truncated` counters use
the `report.py` predicates over fields actually present (0 for both
models), while the derived `failure_class="truncated"` counts are 3 for
GLM (2 gsm8k, 1 race) and 0 for OSS.

## Known data limitations

- **Two malformed GSM8K tasks / 12 grader errors per model**: archived
  details for `gsm8k-0489` (`expected=, got=-10`) and `gsm8k-1113`
  (`expected=, got=3`) have an empty expected value; each task × 3 trials
  × 2 arms = 6 explicit `grader_error` rows per model (12 total, 6 per
  arm; both models, same two tasks).
- **ARC numeric positional fallback limitation**: 22 of 1,172 ARC tasks
  have numeric answerKeys ('1'–'4'); the regrade passes them raw to
  `grade_arc`, whose fallback maps positionally 1→A … 4→D. This assumes a
  four-option question with the archived choice order; a numeric key
  outside 1–4 (or a different option order) cannot be handled and becomes
  a `grader_error`.
- **Unequal GLM/OSS bbh_arith task sets**: GLM bbh_arith has 200 tasks
  (600 trials); OSS has 250 tasks (750 trials). The bbh_arith task sets
  are not identical across models — cross-model bbh_arith comparisons are
  not apples-to-apples.

## Per-model overall results

### GLM (glm-stage1-derived.json → glm-canonical/)

31,524 trials (15,762 per arm; 5,254 tasks per arm). Verdict changes vs
archived: fail→pass 1,839, pass→fail 18.

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 15,110/15,762 | 0.958635 | 0.958635 | 3,159,995 | 3,886,451 | 7,046,446 | 466.34 |
| tahoe | 15,199/15,762 | 0.964281 | 0.964281 | 4,575,877 | 1,984,221 | 6,560,098 | 431.61 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
88/49, empty responses 128/54, truncated-class 3/0 (derived classes),
completed 15,630/15,706. Overall pair: token ratios tahoe/classic —
input 1.4481, output 0.5105, total 0.9310; micro/macro Δ (tahoe−classic)
+0.005646.

### gpt-oss (oss-stage1-derived.json → oss-canonical/)

31,824 trials (15,912 per arm; 5,304 tasks per arm). Verdict changes vs
archived: fail→pass 1,379, pass→fail 40.

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 14,844/15,912 | 0.932881 | 0.932881 | 4,063,215 | 4,278,233 | 8,341,448 | 561.94 |
| tahoe | 14,820/15,912 | 0.931373 | 0.931373 | 5,511,207 | 2,919,526 | 8,430,733 | 568.88 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
32/9, empty responses 32/10, truncated-class 0/0, completed
15,880/15,902. Overall pair: token ratios tahoe/classic — input 1.3564,
output 0.6824, total 1.0107; micro/macro Δ (tahoe−classic) −0.001508.

## Per-benchmark paired results (classic vs tahoe; pass diff = classic − tahoe; pass-perm p = Holm-corrected pass-rate permutation p)

### GLM

| benchmark | classic succ/trials | tahoe succ/trials | micro c / t | pass diff (c−t) | pass-perm p (Holm) |
|---|---|---|---|---|---|
| arc | 3,440/3,516 | 3,432/3,516 | 0.9784 / 0.9761 | +0.0023 | 1.000 |
| bbh | 746/750 | 741/750 | 0.9947 / 0.9880 | +0.0067 | 1.000 |
| bbh_arith | 600/600 | 599/600 | 1.0000 / 0.9983 | +0.0017 | 1.000 |
| bbh_track | 749/750 | 746/750 | 0.9987 / 0.9947 | +0.0040 | 1.000 |
| gsm8k | 3,738/3,957 | 3,834/3,957 | 0.9447 / 0.9689 | −0.0243 | **0.0010** |
| lsat | 1,430/1,530 | 1,452/1,530 | 0.9346 / 0.9490 | −0.0144 | 0.208 |
| mmlu_acct | 813/846 | 815/846 | 0.9610 / 0.9634 | −0.0024 | 1.000 |
| mmlu_logic | 361/378 | 352/378 | 0.9550 / 0.9312 | +0.0238 | 0.448 |
| mmlu_math | 283/300 | 285/300 | 0.9433 / 0.9500 | −0.0067 | 1.000 |
| race | 2,950/3,135 | 2,943/3,135 | 0.9410 / 0.9388 | +0.0022 | 1.000 |

### gpt-oss

| benchmark | classic succ/trials | tahoe succ/trials | micro c / t | pass diff (c−t) | pass-perm p (Holm) |
|---|---|---|---|---|---|
| arc | 3,386/3,516 | 3,373/3,516 | 0.9630 / 0.9593 | +0.0037 | 1.000 |
| bbh | 743/750 | 748/750 | 0.9907 / 0.9973 | −0.0067 | 1.000 |
| bbh_arith | 749/750 | 747/750 | 0.9987 / 0.9960 | +0.0027 | 1.000 |
| bbh_track | 750/750 | 747/750 | 1.0000 / 0.9960 | +0.0040 | 1.000 |
| gsm8k | 3,685/3,957 | 3,746/3,957 | 0.9313 / 0.9467 | −0.0154 | **0.0030** |
| lsat | 1,306/1,530 | 1,271/1,530 | 0.8536 / 0.8307 | +0.0229 | 0.203 |
| mmlu_acct | 758/846 | 758/846 | 0.8960 / 0.8960 | 0.0000 | 1.000 |
| mmlu_logic | 361/378 | 359/378 | 0.9550 / 0.9497 | +0.0053 | 1.000 |
| mmlu_math | 290/300 | 290/300 | 0.9667 / 0.9667 | 0.0000 | 1.000 |
| race | 2,816/3,135 | 2,781/3,135 | 0.8982 / 0.8871 | +0.0112 | **0.0162** |

Full paired statistics (token permutation p, z-test, Wilcoxon, Holm
corrections over the 10-comparison family per model) are in each model's
`canonical_results.json`.

## Untouched inputs

The older GSM8K-only derived directory
(`results/derived/2026-11-18-stage1-gsm8k-v4/`), the raw archives, code,
tests, docs, and paper are unmodified. Git state is unchanged by this
work: only this new derived directory was created.
