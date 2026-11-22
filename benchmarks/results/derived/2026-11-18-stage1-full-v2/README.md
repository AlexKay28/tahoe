# Stage-1 full derived artifacts — 2026-11-18 (v2, GSM8K extractor v5)

Offline regrade of both raw 2026-09-13 stage1-full archives over **all ten
Stage-1 benchmarks** with the current graders, plus per-model canonical
statistics. This directory supersedes
`results/derived/2026-11-18-stage1-full-v1/` (same pipelines, but v1's
GSM8K rows were graded by the earlier **numeric-v4** extractor; v2 re-grades
them with the current **numeric-v5** extractor). No model evaluations, no
API calls, no network; the raw archives are read-only and were verified
byte-unchanged (SHA-256 before and after all generation). Models are
**never pooled**: every artifact below is per model.

## Why v2: GSM8K extractor v4 → v5 (rationale and exact changes)

`grade_gsm8k` extracts the model's number with
`extract_model_number` (`benchmarks/run_public_bench.py`). A final audit
(MEDIUM1) found that **v4 lost correct stated answers** whenever the
answer sentence carried a unit-conversion restatement or trailing context,
because the broad last-bold-span / last-number heuristics let a later
number steal the extraction:

- `'**Answer: 160 minutes (2 hours 40 minutes).**'` → v4 extracted **40**;
- `'**Answer: 448 mL of medicine in 8 doses.**'` → v4 extracted **8**.

**v5 (final-audit MEDIUM1: explicit Answer-marker priority)** re-orders the
extraction into an explicit priority ladder:

1. `#### N` — official GSM8K marker; decimals and `$` handled whole (so
   `'#### 42.50'` is not truncated to `'42'`);
2. `\boxed{...}` — nested-brace tolerant, with LaTeX thousands separators
   normalized first (`'43{,}200'` → 43200);
3. `'Answer: N'` — the number must follow the marker immediately (only
   `$`/whitespace between), and the LAST marker wins, so trailing context
   like `'in 8 doses'` can no longer steal the extraction while a marker
   that discusses its answer (`'Answer: After 3 hours ... 270 miles
   apart'`) still falls through to the bold span;
4. LAST bold span (`**Answer: $12**` / `**It takes 5 hours**`), with
   same-quantity restatements now resolved to their **first** number
   (`**225 minutes, or 3 hours and 45 minutes**` → 225) via a new
   restatement-connector/parenthetical analysis;
5. `'answer is N'` / `'total = N'` (last occurrence);
6. last separator-aware number, now guarded by an end-anchored
   trailing-parenthetical restatement check (`'216 seconds (which is 3
   minutes 36 seconds)'` → 216).

All steps handle `'1,430'`, `'2\,000'`, `'$2,180'`, thin spaces, negatives
and decimals. The gold-side extractor (`extract_gsm8k_gold`, after `####`)
and the numeric comparison are unchanged from v4. `extract_model_number` is
also used by `grade_aime`, but AIME is not part of the Stage-1 archives, so
**only GSM8K rows changed between v1 and v2** (verified: the other nine
benchmarks' per-arm success counts are identical in both directories).

### Measured v4 → v5 impact (GSM8K only; all other rows unchanged)

| model | gsm8k classic succ | gsm8k tahoe succ | gsm8k passed (of 7,914) | gsm8k wrong_answer | gsm8k verdict changes (fail→pass / pass→fail) |
|---|---|---|---|---|---|
| GLM v1 (v4) | 3,738 | 3,834 | 7,572 | 330 | 1,702 / 18 |
| GLM v2 (v5) | **3,750** (+12) | **3,835** (+1) | **7,585** (+13) | 305 | 1,710 / 13 |
| gpt-oss v1 (v4) | 3,685 | 3,746 | 7,431 | 471 | 1,247 / 40 |
| gpt-oss v2 (v5) | **3,703** (+18) | **3,758** (+12) | **7,461** (+30) | 434 | 1,260 / 23 |

Both arms gain passes (fail→pass) and v5 also reverts spurious v4
pass→fail flips (GLM 18→13, gpt-oss 40→23 overall).

## Commands (exact, run from the repo root)

### Regrade (benchmarks/fix_stage1_extraction.py)

```bash
PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v2/glm-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v2/glm-stage1-derived.run.json

PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v2/oss-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v2/oss-stage1-derived.run.json
```

### Canonical statistics (benchmarks/canonical_results.py)

```bash
python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v2/glm-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v2/glm-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v2/oss-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v2/oss-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000
```

No `--include-raw-trials`, no `--include-per-task` (per-task comparisons
are skipped by default). Python 3.12.3. Run metadata (timestamps, absolute
paths, python version) is in the two `.run.json` sidecars only; the
derived artifacts themselves carry no timestamps or host paths.

### Determinism verification (done once, temp removed)

Each derived artifact was regenerated from the same raw archive to a
temporary path under `/place/vartmp/opencode/` and byte-compared
(`cmp`); each canonical pair was regenerated with identical options from
the **same** derived input path to a temporary output directory and
byte-compared. All six files (2 derived JSONs + 4 canonical files) are
byte-identical across runs. The temporary duplicates were then removed.
(The canonical payload records its input file path as metadata, so the
canonical re-runs must read the same derived-input path to be
byte-comparable — that is why the canonical re-run only varies the output
directory.)

## Versions and spec

- Derived schema `tahoe/stage1-derived-results/1`; spec version
  `stage1-archived-results/2026-09-13`; regrader version `1`; grader
  version tag `run_public_bench-current` (the GSM8K grader inside it is
  `grade_gsm8k` numeric-v5; the GSM8K-only pipeline module tags it
  `grade_gsm8k-numeric-v5`, regrader `2`). The grader-source SHA-256
  below is the authoritative pin.
- Grader source `benchmarks/run_public_bench.py`,
  SHA-256 `db38b33e1adcff0fe0e76d1ae063bd7fd59a4ad53eed499c417dfad1b154e04e`
  (**changed since v1**: v1 pinned
  `5153620db7c0632d5c094315c4fe76e2592cae762f5b8371a8836b00ae3190b3`,
  the v4-extractor source).
- Regrade pipeline `benchmarks/stage1_regrade.py`,
  SHA-256 `cc14fc8f35e712fd195c23bae620541c20a1deb8ae27be97b8fb9f8f7fa30699`
  (changed since v1's
  `9adb385c2c6bbb1dcf6e86bdb2d0a3d426d0b2c6b85ceccc405effcd47b3479d`;
  the module's grader tag now reads `numeric-v5`). CLI
  `benchmarks/fix_stage1_extraction.py`,
  SHA-256 `12e26ab583a5699b6c500f5778c1b80ff1855cdbd5ee0e81048c43068cfae485`
  (unchanged since v1).
- GSM8K-only lineage (not used to build this directory; for provenance):
  `benchmarks/gsm8k_regrade.py`
  `2f8da2cbce22d2a0a7119ad1f52c1ab0b48c0b60ec19d2410a56c70d6b011e86`,
  `benchmarks/fix_gsm8k_extraction.py`
  `57101481630c99955defa853449efe1a55748f9b9c2ff9bce6dbe5c3b653f0ee`.

## SHA-256 (all inputs verified before AND after generation)

| file | SHA-256 |
|---|---|
| raw input (GLM, read-only, unchanged) `results/2026-09-13-stage1-full/full_test_eval.json` | `43ca713f08acc2c72bfed10d74eab4943ea4d128933dc67da9ca0344347deacf` |
| raw input (gpt-oss, read-only, unchanged) `results/2026-09-13-stage1-full/oss_full_eval.json` | `771be2ee59da30df186df2c73d64931fbf32c7d772f6a5afe313bbb58160eff9` |
| `glm-stage1-derived.json` | `48e405e5243b1a7ed1a7a707d95269a9ec963b3bbcf97ea0aa2d3620425739a6` |
| `oss-stage1-derived.json` | `b339cf3c04354fcc33fa5f7c87cd7f1aa38e351ffd241b5316bb64c1d79d9c8a` |
| `glm-stage1-derived.run.json` | `c1a4912e01b05c7529993c0ef8a7966620422502de0e34e3d8be202968d9ebcc` |
| `oss-stage1-derived.run.json` | `5e5ecafc6733180febb7c3e1dc44fe6ebaa4275bdb90c50927e3955d40eff836` |
| `glm-canonical/canonical_results.json` | `8293b53d565b67be7634631943e9ef6621140bdf9c33cf0fb3dc26c7c62514c3` |
| `glm-canonical/canonical_results.md` | `591a7bfe28ac381f40e6ed2ffbdcc9a36e4e36d51956cce247cd6d8a34b0d262` |
| `oss-canonical/canonical_results.json` | `b3836ce4f5a4e57690d77540e740023b102084eab9067fc5c2346d32067eddfb` |
| `oss-canonical/canonical_results.md` | `78885342f8840406a5707b7a28593b5676e844283c2ee79fb43fdd222f6ff911` |

## Analysis provenance and options

`analysis_provenance` (schema `canonical-analysis/1`, recorded inside each
canonical JSON) pins the analysis implementation (all unchanged since v1):
`benchmarks/canonical_results.py`
`9a7ca4b6ad08e965652d833d711e84fdf01a697cd2e925c65732b94bc244d31c`,
`benchmarks/report.py`
`be7ac408bfe0c592e6d7d7ae6152f1f7dd75cdde5818728fd008e1d62cef9975`,
`benchmarks/stats.py`
`d497684839594a1264e615be8d8440ee27210adf6e732026ea32bb649cb308b8`.
Options: seed 42, 10,000 bootstrap resamples, 10,000 permutation draws;
raw trials and per-task blocks excluded. Arm outcomes count `grader_error`
as a first-class outcome (`failure_class == "grader_error"` literally).
Multiplicity: Holm step-down over the 10-comparison family per model,
corrected fields `permutation_p_holm`, `pass_rate_permutation_p_holm`,
`z_test.p_value_holm`, `wilcoxon.p_value_holm`.

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
`finish_reason` and never sets a truncated flag from the exact cap alone.
Empty/missing final answers fail as `empty_response` (never graded into a
pass); nonempty cap-exhausted answers that fail grading are classified
`truncated` with explicit `outcome_provenance`; all other failing grades
are `wrong_answer`. The canonical `outcomes.truncated` counters use the
`report.py` predicates over fields actually present and are therefore
**0 for both arms of both models** — this is not evidence of zero
truncation; the derived `failure_class="truncated"` counts are the
cap-derived ones: GLM 3 (2 classic gsm8k, 1 tahoe race; i.e. per-arm
split 2/1), gpt-oss 0.

## Known data limitations

- **Two malformed GSM8K tasks / 12 grader errors per model**: archived
  details for `gsm8k-0489` (`expected=, got=-10`) and `gsm8k-1113`
  (`expected=, got=3`) have an empty expected value; each task × 3 trials
  × 2 arms = **12 explicit `grader_error` rows per model — 6 per arm**
  (24 across both models; both models, same two tasks), counted as
  failures. *This corrects a typo in the v1 README, which wrote "6
  explicit grader_error rows per model": the 6 is per arm, and the
  per-model total is 12.* (v1's counts themselves were correct — only the
  prose was wrong.)
- **ARC numeric positional fallback limitation**: 22 of 1,172 ARC tasks
  (per model) have numeric answerKeys ('1'–'4'); the regrade passes them
  raw to `grade_arc`, whose fallback maps positionally 1→A … 4→D. This
  assumes a four-option question with the archived choice order; a
  numeric key outside 1–4 (or a different option order) cannot be handled
  and becomes a `grader_error`.
- **Unequal GLM/OSS bbh_arith task sets**: GLM bbh_arith has 200 tasks
  (600 trials); OSS has 250 tasks (750 trials). The bbh_arith task sets
  are not identical across models — cross-model bbh_arith comparisons
  are not apples-to-apples.

## Per-model overall results

### GLM (glm-stage1-derived.json → glm-canonical/)

31,524 trials (15,762 per arm; 5,254 tasks per arm). Verdict changes vs
archived: fail→pass 1,847, pass→fail 13 (v1: 1,839/18).

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 15,122/15,762 = 95.9396% | 0.959396 | 0.959396 | 3,159,995 | 3,886,451 | 7,046,446 | 465.97 |
| tahoe | 15,200/15,762 = 96.4345% | 0.964345 | 0.964345 | 4,575,877 | 1,984,221 | 6,560,098 | 431.59 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
88/49, empty responses 128/54, derived truncated-class 2/1 (2 classic
gsm8k, 1 tahoe race; canonical truncated counters 0/0), completed
15,630/15,706. Overall pair: token ratios tahoe/classic — input 1.4481,
output 0.5105, total 0.9310; micro/macro Δ (tahoe−classic) +0.004949
(+0.4949pp; v1 was +0.5646pp).

### gpt-oss (oss-stage1-derived.json → oss-canonical/)

31,824 trials (15,912 per arm; 5,304 tasks per arm). Verdict changes vs
archived: fail→pass 1,392, pass→fail 23 (v1: 1,379/40).

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 14,862/15,912 = 93.4012% | 0.934012 | 0.934012 | 4,063,215 | 4,278,233 | 8,341,448 | 561.26 |
| tahoe | 14,832/15,912 = 93.2127% | 0.932127 | 0.932127 | 5,511,207 | 2,919,526 | 8,430,733 | 568.42 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
32/9, empty responses 32/10, derived truncated-class 0/0 (canonical
truncated counters 0/0), completed 15,880/15,902. Overall pair: token
ratios tahoe/classic — input 1.3564, output 0.6824, total 1.0107;
micro/macro Δ (tahoe−classic) −0.001885 (−0.1885pp; v1 was −0.1508pp).

The overall deltas are **not** called significant or null-tested
anywhere: the canonical paired inferential family is per benchmark (Holm
over 10 comparisons per model); there is no overall confirmatory test and
no prespecified equivalence margin.

## Per-benchmark paired results (classic vs tahoe)

Pass diff = pass-rate difference classic − tahoe (paired
benchmark/task/trial); `pass-perm` = pass-rate permutation p (Holm);
`tok-perm` = mean-total-token permutation p (Holm); `z` = paired z p
(Holm); `Wilcoxon` p (Holm); tok diff = mean per-pair total-token
difference classic − tahoe.

### GLM

| benchmark | classic succ/trials | tahoe succ/trials | pass rate c / t | pass diff (c−t) | pass-perm p (Holm) | tok-perm p (Holm) | z p (Holm) | Wilcoxon p (Holm) | tok diff |
|---|---|---|---|---|---|---|---|---|---|
| arc | 3,440/3,516 | 3,432/3,516 | 0.9784 / 0.9761 | +0.0023 | 1.000 | 0.0010 | 1.000 | 1.69e-72 | −26.13 |
| bbh | 746/750 | 741/750 | 0.9947 / 0.9880 | +0.0067 | 1.000 | 0.0010 | 0.6608 | 1.01e-26 | +94.15 |
| bbh_arith | 600/600 | 599/600 | 1.0000 / 0.9983 | +0.0017 | 1.000 | 0.0010 | 1.000 | 1.01e-33 | −68.88 |
| bbh_track | 749/750 | 746/750 | 0.9987 / 0.9947 | +0.0040 | 1.000 | 0.0010 | 1.000 | 5.73e-39 | +162.36 |
| gsm8k | 3,750/3,957 | 3,835/3,957 | 0.9477 / 0.9692 | −0.0215 | **0.0010** | 0.0010 | 4.57e-07 | 5.73e-152 | +61.65 |
| lsat | 1,430/1,530 | 1,452/1,530 | 0.9346 / 0.9490 | −0.0144 | 0.2079 | 0.0010 | 0.1664 | 5.76e-33 | +126.83 |
| mmlu_acct | 813/846 | 815/846 | 0.9610 / 0.9634 | −0.0024 | 1.000 | 0.6263 | 1.000 | 0.1620 | +9.61 |
| mmlu_logic | 361/378 | 352/378 | 0.9550 / 0.9312 | +0.0238 | 0.4480 | 0.0036 | 0.2913 | 0.0001 | −40.53 |
| mmlu_math | 283/300 | 285/300 | 0.9433 / 0.9500 | −0.0067 | 1.000 | 1.000 | 1.000 | 0.1620 | −8.09 |
| race | 2,950/3,135 | 2,943/3,135 | 0.9410 / 0.9388 | +0.0022 | 1.000 | 1.000 | 1.000 | 3.62e-13 | −0.39 |

### gpt-oss

| benchmark | classic succ/trials | tahoe succ/trials | pass rate c / t | pass diff (c−t) | pass-perm p (Holm) | tok-perm p (Holm) | z p (Holm) | Wilcoxon p (Holm) | tok diff |
|---|---|---|---|---|---|---|---|---|---|
| arc | 3,386/3,516 | 3,373/3,516 | 0.9630 / 0.9593 | +0.0037 | 1.000 | 0.0010 | 1.000 | 5.36e-180 | −62.59 |
| bbh | 743/750 | 748/750 | 0.9907 / 0.9973 | −0.0067 | 1.000 | 0.0294 | 0.5742 | 0.1583 | +27.48 |
| bbh_arith | 749/750 | 747/750 | 0.9987 / 0.9960 | +0.0027 | 1.000 | 0.0010 | 1.000 | 8.15e-36 | −64.64 |
| bbh_track | 750/750 | 747/750 | 1.0000 / 0.9960 | +0.0040 | 1.000 | 0.6583 | 0.5742 | 0.1669 | −5.23 |
| gsm8k | 3,703/3,957 | 3,758/3,957 | 0.9358 / 0.9497 | −0.0139 | **0.0060** | 0.0010 | 0.0060 | 3.16e-179 | +99.05 |
| lsat | 1,306/1,530 | 1,271/1,530 | 0.8536 / 0.8307 | +0.0229 | 0.2032 | 0.0010 | 0.1659 | 0.0008 | +27.83 |
| mmlu_acct | 758/846 | 758/846 | 0.8960 / 0.8960 | −0.0000 | 1.000 | 0.0010 | 1.000 | 5.66e-21 | −42.77 |
| mmlu_logic | 361/378 | 359/378 | 0.9550 / 0.9497 | +0.0053 | 1.000 | 0.0010 | 1.000 | 8.48e-07 | −36.34 |
| mmlu_math | 290/300 | 290/300 | 0.9667 / 0.9667 | +0.0000 | 1.000 | 0.6593 | 1.000 | 0.0550 | −8.10 |
| race | 2,816/3,135 | 2,781/3,135 | 0.8982 / 0.8871 | +0.0112 | **0.0162** | 0.0010 | 0.0150 | 1.83e-145 | −70.05 |

### Significant paired pass-rate results (Holm-corrected, α=0.05)

- **GLM GSM8K — tahoe higher**, pass-perm p (Holm) = 0.00099990
  (pass rate classic 0.94769 vs tahoe 0.96917, diff −0.021481, 95% CI
  [−0.029315, −0.013899]; v1: 0.0010).
- **gpt-oss GSM8K — tahoe higher**, pass-perm p (Holm) = 0.0059994
  (pass rate classic 0.93581 vs tahoe 0.94971, diff −0.013899, 95% CI
  [−0.021986, −0.006065]; v1: 0.0030).
- **gpt-oss RACE — classic higher**, pass-perm p (Holm) = 0.016198
  (pass rate classic 0.89825 vs tahoe 0.88708, diff +0.011164, 95% CI
  [+0.004147, +0.018182]; unchanged from v1 — RACE grading did not
  change).

No other benchmark reaches Holm significance on the paired pass-rate
permutation test for either model. The token-spend permutation family is
significant for most benchmarks (see tables) and is a distinct estimand
(mean total-token difference), not a pass-rate claim. Full paired detail
(token CIs, z, Wilcoxon, Holm steps over the 10-comparison family per
model) is in each model's `canonical_results.json`.

## Tests

`tests/test_stage1_regrade.py` real-archive smoke assertions
(opt-in via `TAHOE_STAGE1_SMOKE=1`) pin exact per-arm success and
verdict-change totals; the v4-era expected numbers were updated to the v5
values above (and only those expected numbers — no pipeline logic
changed): GLM classic/tahoe 15,122/15,200; gpt-oss classic/tahoe
14,862/14,832 (93.40% / 93.21%); GLM gsm8k passed 7,585, verdict changes
1,710/13. Verified green: `TAHOE_STAGE1_SMOKE=1 python3 -m pytest
tests/test_stage1_regrade.py` (72 passed, including both real-archive
smoke tests) and the focused suites `tests/test_fix_gsm8k_extraction.py
tests/test_public_bench_graders.py tests/test_canonical_results.py
tests/test_graders.py` (163 passed).

## Untouched inputs

The raw archives (`results/2026-09-13-stage1-full/`, SHA-256 verified
before and after), the superseded `2026-11-18-stage1-full-v1/` and
`2026-11-18-stage1-gsm8k-v4/` derived directories, all pipeline code, all
docs, the paper, and the derived index were not modified by this work;
only this new directory (plus the smoke-test expected-number update noted
above) was created. No model evaluations were run.
