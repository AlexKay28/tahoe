# Stage-1 full derived artifacts — 2026-11-18 (v3, GSM8K extractor v6)

Offline regrade of both raw 2026-09-13 stage1-full archives over **all ten
Stage-1 benchmarks** with the current graders, plus per-model canonical
statistics. This directory supersedes
`results/derived/2026-11-18-stage1-full-v2/` (same pipelines, but v2's
GSM8K rows were graded by the earlier **numeric-v5** extractor; v3 re-grades
them with the current **numeric-v6** extractor — the "plain and boxed
clock-time fix"). No model evaluations, no API calls, no network; the raw
archives are read-only and were verified byte-unchanged (SHA-256 before and
after all generation). Models are **never pooled**: every artifact below is
per model.

## Why v3: GSM8K extractor v5 → v6 (rationale and exact changes)

`grade_gsm8k` extracts the model's number with
`extract_model_number` (`benchmarks/run_public_bench.py`). A final audit
(OSS-audit LOW) found that **v5 lost clock-form answers**: when a model's
stated answer is an H:MM am/pm clock time (`'2:00 pm'`, gold hour 2), the
H:MM pair is not a number, and the broad last-bold/last-number heuristics
returned the **minutes** (`'2:00 pm'` → `'00'`), failing every such trial
against the gold hour.

**v6 (clock-form answers state their hour)** makes exactly these changes to
the model-side extraction:

1. a new end-anchored clock-form regex `_CLOCK_TIME_RE` — H:MM with an
   **explicit am/pm marker** (upper-case, dotted `'a.m.'`, thin-space
   `'2:00\u202fpm'` all handled), exactly two minute digits, and the whole
   time must END the span. Ratios (`'3:1'` — one-digit minute, no marker),
   plain times (`'at 2:00'`), decimals (`'2.50'`), colon labels
   (`'Part 2: 00'`) and clock mentions followed by later numeric context
   (`'... at 2:00 pm and walks 5 miles'`) therefore never match;
2. a new `_clock_hour` helper, applied at three points of the v5 priority
   ladder:
   - **step 2 (boxed)**: `_boxed_clock_hour` unwraps LaTeX text-mode
     wrappers and thin spacing (`'\boxed{2\text{:}00 \text{ pm}}'` → 2)
     **for the clock-form check only**; every other boxed form keeps the
     generic last-number extraction unchanged;
   - **step 4 (last bold span)**: a span ending in an H:MM am/pm time
     states its hour (`'**2:00 pm**'` → 2), checked before the
     same-quantity restatement analysis;
   - **step 6 (bare-text last-number fallback)**: after the
     trailing-parenthetical restatement guard, a trailing clock time
     states its hour (`'2:00 pm'` → 2, `'12:30pm'` → 12).

The gold-side extractor (`extract_gsm8k_gold`, after `####`) and the numeric
comparison are unchanged from v5. `extract_model_number` is also used by
`grade_aime`, but AIME is not part of the Stage-1 archives, so **only GSM8K
rows could change between v2 and v3** — verified trial-by-trial: across all
63,348 trials the verdicts that changed are exactly the `gsm8k-1001` rows
below, and the other nine benchmarks' per-arm success counts are identical
in both directories.

### Measured v5 → v6 impact (all on one task: `gsm8k-1001`, gold `#### 2`)

All 12 changed trials (6 per model) state the answer as a clock time
(`'2:00 pm'`, `'2:00\u202fpm'`, or `'**2:00 pm**'`); v5 extracted `'00'`
(wrong_answer), v6 extracts `'2'` (pass):

| model | trials changed (per arm) | v2 → v3 verdict |
|---|---|---|
| GLM | 6 (classic 3, tahoe 3) | all archived-fail → fail→pass (GLM gsm8k fail_to_pass 1,710 → 1,716) |
| gpt-oss | 6 (classic 3, tahoe 3) | classic: fail→pass; tahoe: the 3 trials v5 had flipped pass→fail are restored to their archived pass (OSS gsm8k pass_to_fail 23 → 20, fail_to_pass 1,260 → 1,263) |

| model | gsm8k classic succ | gsm8k tahoe succ | gsm8k passed (of 7,914) | gsm8k wrong_answer | gsm8k verdict changes (fail→pass / pass→fail) |
|---|---|---|---|---|---|
| GLM v2 (v5) | 3,750 | 3,835 | 7,585 | 305 | 1,710 / 13 |
| GLM v3 (v6) | **3,753** (+3) | **3,838** (+3) | **7,591** (+6) | 299 | 1,716 / 13 |
| gpt-oss v2 (v5) | 3,703 | 3,758 | 7,461 | 434 | 1,260 / 23 |
| gpt-oss v3 (v6) | **3,706** (+3) | **3,761** (+3) | **7,467** (+6) | 428 | 1,263 / 20 |

Because each model's two arms gained exactly 3 GSM8K passes, the paired
GSM8K pass-rate differences and their CIs are unchanged from v2; v6 removes
the v5 under-credit on both arms.

## Commands (exact, run from the repo root)

### Regrade (benchmarks/fix_stage1_extraction.py)

```bash
PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.run.json

PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \
  --input  benchmarks/results/2026-09-13-stage1-full/oss_full_eval.json \
  --output benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.json \
  --run-metadata benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.run.json
```

### Canonical statistics (benchmarks/canonical_results.py)

```bash
python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000

python3 benchmarks/canonical_results.py \
  benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.json \
  -o benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-canonical \
  --seed 42 --n-resamples 10000 --n-permutations 10000
```

No `--include-raw-trials`, no `--include-per-task` (per-task comparisons
are skipped by default). Python 3.12.3. Run metadata (timestamps, absolute
paths, python version) is in the two `.run.json` sidecars only; the
derived artifacts themselves carry no timestamps or host paths.

### Determinism verification (done once, temp removed)

Each derived artifact was regenerated from the same raw archive to a
temporary path under `/place/vartmp/opencode/` and byte-compared (`cmp`);
each canonical pair was regenerated with identical options from the
**same** derived input path to a temporary output directory and
byte-compared. All six files (2 derived JSONs + 4 canonical files) are
byte-identical across runs. The temporary duplicates were then removed
(only those two temp directories; nothing else under
`/place/vartmp/opencode/` was touched). (The canonical payload records its
input file path as metadata, so the canonical re-runs must read the same
derived-input path to be byte-comparable — that is why the canonical
re-run only varies the output directory.)

## Versions and spec

- Derived schema `tahoe/stage1-derived-results/1`; spec version
  `stage1-archived-results/2026-09-13`; regrader version `1`; grader
  version tag `run_public_bench-numeric-v6` (**changed since v2**, which
  recorded `run_public_bench-current`; the GSM8K grader inside it is
  `grade_gsm8k` numeric-v6; the GSM8K-only pipeline module tags it
  `grade_gsm8k-numeric-v6`). The grader-source SHA-256 below is the
  authoritative pin.
- Grader source `benchmarks/run_public_bench.py`,
  SHA-256 `bdbc5208675883e8f45806246345a0e81cd430e70415a7150fba882eabbb2d8e`
  (**changed since v2**: v2 pinned
  `db38b33e1adcff0fe0e76d1ae063bd7fd59a4ad53eed499c417dfad1b154e04e`,
  the v5-extractor source).
- Regrade pipeline `benchmarks/stage1_regrade.py`,
  SHA-256 `a45761341f872ee1644693ce793131969f147237a607ac2b489cb11ac7101f3b`
  (changed since v2's
  `cc14fc8f35e712fd195c23bae620541c20a1deb8ae27be97b8fb9f8f7fa30699`;
  the module's grader tag now reads `numeric-v6`). CLI
  `benchmarks/fix_stage1_extraction.py`,
  SHA-256 `12e26ab583a5699b6c500f5778c1b80ff1855cdbd5ee0e81048c43068cfae485`
  (unchanged since v1 and v2).
- GSM8K-only lineage (not used to build this directory; for provenance):
  `benchmarks/gsm8k_regrade.py`
  `0e77614d8ac0705a14fdf77766fb32fe5138a02b896775c8e70888a5ef822e47`
  (changed since v2's
  `2f8da2cbce22d2a0a7119ad1f52c1ab0b48c0b60ec19d2410a56c70d6b011e86`),
  `benchmarks/fix_gsm8k_extraction.py`
  `57101481630c99955defa853449efe1a55748f9b9c2ff9bce6dbe5c3b653f0ee`
  (unchanged since v2).

## SHA-256 (all inputs verified before AND after generation)

| file | SHA-256 |
|---|---|
| raw input (GLM, read-only, unchanged) `results/2026-09-13-stage1-full/full_test_eval.json` | `43ca713f08acc2c72bfed10d74eab4943ea4d128933dc67da9ca0344347deacf` |
| raw input (gpt-oss, read-only, unchanged) `results/2026-09-13-stage1-full/oss_full_eval.json` | `771be2ee59da30df186df2c73d64931fbf32c7d772f6a5afe313bbb58160eff9` |
| `glm-stage1-derived.json` | `ba953dfdcb9cf19ccdd1a762e4e8db8b4dd72c979e0281b783766bff79e1c381` |
| `oss-stage1-derived.json` | `0d98f4905cf9fc606c0f12db6e24ea08d866e1bef3e3e7604fa033e3a388212e` |
| `glm-stage1-derived.run.json` | `87af53bfc166bd37dd552ce01261733a46a3ed6ad38e999f5d751d45eaba4858` |
| `oss-stage1-derived.run.json` | `cb4f9b4fc4cb40ce1ed6aefddfab0046f0b75b693a8311585361e2ac7e9b6de1` |
| `glm-canonical/canonical_results.json` | `7b55602cdca26b652c6d0ea061c52a96603ec32695fff58580f78ab6c53dbdaa` |
| `glm-canonical/canonical_results.md` | `28be9859507609f5692830d3361912cd1686301afdc7838a3c3c3470bb86387f` |
| `oss-canonical/canonical_results.json` | `c212ad8fde68601d3a3ee340b00f8271d33c52f93329ba9e7b33f17d58dd8ac4` |
| `oss-canonical/canonical_results.md` | `58ee7a2facb2986e678b7a8c673020f891030add5399c353f6253d4dc063ac21` |

## Analysis provenance and options

`analysis_provenance` (schema `canonical-analysis/1`, recorded inside each
canonical JSON) pins the analysis implementation (all unchanged since v1
and v2): `benchmarks/canonical_results.py`
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
split 2/1), gpt-oss 0 (every OSS cap-exhausted trial was empty).

## Known data limitations

- **Two malformed GSM8K tasks / 12 grader errors per model**: archived
  details for `gsm8k-0489` (`expected=, got=-10`) and `gsm8k-1113`
  (`expected=, got=3`) have an empty expected value; each task × 3 trials
  × 2 arms = **12 explicit `grader_error` rows per model — 6 per arm**
  (24 across both models; both models, same two tasks), counted as
  failures. (Carried over unchanged from v1/v2; the v6 extractor does not
  touch malformed-expected handling.)
- **ARC numeric positional fallback limitation**: 22 of 1,172 ARC tasks
  (per model; re-verified from the v3 artifacts) have numeric answerKeys
  ('1'–'4'); the regrade passes them raw to `grade_arc`, whose fallback
  maps positionally 1→A … 4→D. This assumes a four-option question with
  the archived choice order; a numeric key outside 1–4 (or a different
  option order) cannot be handled and becomes a `grader_error`.
- **Unequal GLM/OSS bbh_arith task sets**: GLM bbh_arith has 200 tasks
  (600 trials); OSS has 250 tasks (750 trials). The bbh_arith task sets
  are not identical across models — cross-model bbh_arith comparisons
  are not apples-to-apples.

## Per-model overall results

### GLM (glm-stage1-derived.json → glm-canonical/)

31,524 trials (15,762 per arm; 5,254 tasks per arm). Verdict changes vs
archived: fail→pass 1,853, pass→fail 13 (v2: 1,847/13; the +6 is gsm8k-1001).

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 15,125/15,762 = 95.9586% | 0.959586 | 0.959586 | 3,159,995 | 3,886,451 | 7,046,446 | 465.88 |
| tahoe | 15,203/15,762 = 96.4535% | 0.964535 | 0.964535 | 4,575,877 | 1,984,221 | 6,560,098 | 431.50 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
88/49, empty responses 128/54, derived truncated-class 2/1 (2 classic
gsm8k, 1 tahoe race; canonical truncated counters 0/0), completed
15,630/15,706. Overall pair: token ratios tahoe/classic — input 1.4481,
output 0.5105, total 0.9310; micro/macro Δ (tahoe−classic) +0.0049486
(+0.4949pp; unchanged from v2 — both arms gained the same 3 passes).

### gpt-oss (oss-stage1-derived.json → oss-canonical/)

31,824 trials (15,912 per arm; 5,304 tasks per arm). Verdict changes vs
archived: fail→pass 1,395, pass→fail 20 (v2: 1,392/23; +3 classic
fail→pass and −3 tahoe pass→fail, all on gsm8k-1001).

| arm | successes/trials | micro acc | macro acc | input tok | output tok | total tok | spend/success |
|---|---|---|---|---|---|---|---|
| classic | 14,865/15,912 = 93.4201% | 0.934201 | 0.934201 | 4,063,215 | 4,278,233 | 8,341,448 | 561.15 |
| tahoe | 14,835/15,912 = 93.2315% | 0.932315 | 0.932315 | 5,511,207 | 2,919,526 | 8,430,733 | 568.30 |

Overall outcomes (classic / tahoe): grader errors 6/6, cap-exhausted
32/9, empty responses 32/10, derived truncated-class 0/0 (canonical
truncated counters 0/0), completed 15,880/15,902. Overall pair: token
ratios tahoe/classic — input 1.3564, output 0.6824, total 1.0107;
micro/macro Δ (tahoe−classic) −0.0018854 (−0.1885pp; unchanged from v2).

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
| gsm8k | 3,753/3,957 | 3,838/3,957 | 0.9484 / 0.9699 | −0.0215 | **0.0010** | 0.0010 | 4.57e-07 | 5.73e-152 | +61.65 |
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
| gsm8k | 3,706/3,957 | 3,761/3,957 | 0.9366 / 0.9505 | −0.0139 | **0.0060** | 0.0010 | 0.0060 | 3.16e-179 | +99.05 |
| lsat | 1,306/1,530 | 1,271/1,530 | 0.8536 / 0.8307 | +0.0229 | 0.2032 | 0.0010 | 0.1659 | 0.0008 | +27.83 |
| mmlu_acct | 758/846 | 758/846 | 0.8960 / 0.8960 | +0.0000 | 1.000 | 0.0010 | 1.000 | 5.66e-21 | −42.77 |
| mmlu_logic | 361/378 | 359/378 | 0.9550 / 0.9497 | +0.0053 | 1.000 | 0.0010 | 1.000 | 8.48e-07 | −36.34 |
| mmlu_math | 290/300 | 290/300 | 0.9667 / 0.9667 | +0.0000 | 1.000 | 0.6593 | 1.000 | 0.0550 | −8.10 |
| race | 2,816/3,135 | 2,781/3,135 | 0.8982 / 0.8871 | +0.0112 | **0.0162** | 0.0010 | 0.0150 | 1.83e-145 | −70.05 |

### Significant paired pass-rate results (Holm-corrected, α=0.05)

- **GLM GSM8K — tahoe higher**, pass-perm p (Holm) = 0.00099990
  (pass rate classic 0.94845 vs tahoe 0.96993, diff −0.021481, 95% CI
  [−0.029315, −0.013899]; unchanged from v2 — both arms gained the same
  3 passes; v1/v2 values were computed on 6 fewer total passes).
- **gpt-oss GSM8K — tahoe higher**, pass-perm p (Holm) = 0.0059994
  (pass rate classic 0.93657 vs tahoe 0.95047, diff −0.013899, 95% CI
  [−0.021986, −0.006065]; unchanged from v2).
- **gpt-oss RACE — classic higher**, pass-perm p (Holm) = 0.016198
  (pass rate classic 0.89825 vs tahoe 0.88708, diff +0.011164, 95% CI
  [+0.004147, +0.018182]; unchanged from v1/v2 — RACE grading did not
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
verdict-change totals; the v5-era expected numbers were updated to the v6
values above (and only those expected numbers — no pipeline logic
changed): GLM classic/tahoe 15,125/15,203; gpt-oss classic/tahoe
14,865/14,835 (93.42% / 93.23%); GLM gsm8k passed 7,591, verdict changes
1,716/13. Verified green: `TAHOE_STAGE1_SMOKE=1 python3 -m pytest
tests/test_stage1_regrade.py` and the focused suites
`tests/test_fix_gsm8k_extraction.py tests/test_public_bench_graders.py
tests/test_canonical_results.py tests/test_graders.py`.

## Untouched inputs

The raw archives (`results/2026-09-13-stage1-full/`, SHA-256 verified
before and after), the superseded `2026-11-18-stage1-full-v1/`,
`2026-11-18-stage1-full-v2/` and `2026-11-18-stage1-gsm8k-v4/` derived
directories, all pipeline code, all docs, the paper, and the derived index
were not modified by this work; only this new directory (plus the
smoke-test expected-number update noted above) was created. No model
evaluations were run.
