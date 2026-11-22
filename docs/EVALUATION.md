# TAHOE Evaluation Results

> Canonical record of all evaluation runs. Updated: 2026-11-18.
>
> **How to read these numbers.** Stage-1 accuracy figures are the
> **current-grader derived results** from the completed full Stage-1 derived
> pipeline (`benchmarks/results/derived/2026-11-18-stage1-full-v3/` — all
> ten benchmarks, both models, GSM8K graded by the current numeric-v6
> extractor; index:
> `benchmarks/results/derived/README.md`): the raw 2026-09-13 archives were
> re-graded offline (read-only; CLI `benchmarks/fix_stage1_extraction.py`,
> helper `benchmarks/stage1_regrade.py`) and per-model canonical statistics
> computed with `benchmarks/canonical_results.py` — deterministic, refuses
> to overwrite, never mixes trial-pooled (micro) with task-equal-weighted
> (macro) estimands, and derives truncation/cap/empty outcomes only from
> fields actually recorded. Expectations are reconstructed from archived
> grader details, not independently validated gold data. The doc tables
> are generated blocks from the canonical payloads
> (`benchmarks/render_canonical_docs.py` `--update`/`--check`); the
> generated per-model documents are
> `2026-11-18-stage1-full-v3/{glm,oss}-canonical/canonical_results.md`.
> The harder-benchmark slate sections below remain **stored-grade,
> fixed-cap-endpoint** results from their raw 2026-09-16/17 studies and are
> unchanged.

## Harder-Benchmark Slate (2026-09-16, issues #96/#97)

**Endpoint note.** All slate runs used `max_tokens=2048` for both arms, so
every accuracy below is **fixed-2048-output-token task success**: a trial
passes only if the graded answer is correct within the 2048-output-token
budget. This endpoint conflates *completion* (finishing within the cap)
with *correctness* (the completed answer being right); both are reported
below. Exact-cap responses with empty final answers exist in every slate
archive — 313/480 AIME, 187/396 GPQA, 228/1,600 MMLU-Pro, and 207/300 LCB
trials sit at exactly the 2048 output-token cap, nearly all of them with
empty final answers — and the archived `failure_class` labels them
`wrong_answer`.

**Inference note (2026-11-18).** The inferential numbers below come from the
repaired keyed task-cluster analysis (`benchmarks/difficulty_curve.py`
`compute_curve`, run offline in memory on the archived trials): trials
paired by exact `(benchmark, task_id, trial)` identity, repeated trials
averaged within tasks, **paired task-macro delta** with a 95% task-cluster
bootstrap CI, and a two-sided paired permutation test **Holm-adjusted across
the 14-benchmark family**. The earlier unpaired z tests and ±binomial
per-arm CIs that appeared here are retired — treat any surviving per-arm
"±" values as descriptive point summaries only, not inferential claims.

**GPQA Diamond** (198 PhD-level science MC, GLM-5.3-Flash, 1 seed, 396 trials):

| Arm | Fixed-cap task success | Avg total tokens | Empty answers | Completed | Completed-acc |
|---|---|---|---|---|---|
| classic | 49.5% (98/198) | 1560 | 97 | 101 | 97.0% |
| tahoe-93 | 51.0% (101/198) | 1565 | 90 | 108 | 93.5% |

Paired task-macro delta **+1.52pp, 95% task-cluster bootstrap CI
[−3.5, +7.1], paired permutation p=0.72 (Holm-adjusted p=1.00 across the
14-benchmark family) — not significant**; total tokens 1.00×, output 0.94×.
**Reading**: under the fixed cap, tahoe completed more responses (108 vs
101) while classic was, if anything, more accurate among completed
responses (97.0% vs 93.5%) — the small n.s. delta mixes both channels. This
says nothing about the (unmeasured) search-bounding mechanism. Contrast
anchor for the difficulty-response curve (#102): gsm8k stored-grade delta
(grader-sensitive; superseded by the current-grader derived regrade —
see the Stage-1 Derived Results section) vs GPQA-D +1.5pp
n.s. @ 1.00×.
Data: `benchmarks/results/2026-09-16-gpqa-diamond/`, slice in
`benchmarks/data/gpqa_diamond.jsonl` (from corp YT raw table — the processed
`gpqa_diamond_gpt_202` table drops 2 rows, issue #104).

**AIME 2024+2025** (60 competition problems, integer answers, 4 seeds, 480 trials):

| Arm | Fixed-cap task success | Avg total tokens | Empty answers | Completed | Completed-acc |
|---|---|---|---|---|---|
| classic | 30.8% (74/240) | 1895 | 147 | 93 | 79.6% |
| tahoe-93 | 37.1% (89/240) | 1830 | 144 | 96 | 92.7% |

Paired task-macro delta **+6.25pp, 95% task-cluster bootstrap CI
[+1.7, +11.7]; raw paired permutation p=0.024, but Holm-adjusted
p=0.26 across the 14-benchmark family — not significant family-wise** (the
4/4 seed-direction consistency is a descriptive observation); total tokens
0.97×, output 0.91×. **Correction (2026-11-18):**
the earlier "zero truncation in both arms — the delta is genuine answer
quality, not budget survival" reading is **retracted**. The archive shows
163/240 classic and 150/240 tahoe trials at exactly the 2048 output-token
cap (147/144 with empty final answers), all stored as wrong answers. Under
the fixed-cap endpoint, budget survival (completion) and answer correctness
cannot be separated; both remain live explanations for the +6.25pp, and the
output-compression/finish-within-budget hypothesis remains open. Recorded
as **null-trending-positive** per the predeclared H0 discipline (issue #97).
Curve anchor #2 (classic-acc ~31%).
Data: `benchmarks/results/2026-09-16-aime-24-25/`, slice in
`benchmarks/data/aime60.jsonl` (corp Harbor adapter's source URLs).

**MMLU-Pro stratified-800** (10-option discrimination, 14 categories, 1,600 trials):

| Arm | Fixed-cap task success | Avg total tokens | Empty answers | Completed | Completed-acc |
|---|---|---|---|---|---|
| classic | 75.1% (601/800) | 855 | 142 | 658 | 91.3% |
| tahoe-93 | 79.4% (635/800) | 750 | 86 | 714 | 88.9% |

Paired task-macro delta **+4.25pp, 95% task-cluster bootstrap CI
[+2.1, +6.5], paired permutation p=0.0002, Holm-adjusted p=0.0026 across
the 14-benchmark family — significant family-wise** on the fixed-cap
endpoint, at **0.70× output tokens and 0.88× total tokens** — the slate's
only family-wise-significant fixed-cap result, at lower spend on both token
axes.
**Correction (2026-11-18):** the earlier "mechanism held — high distractor
density rewards structured error-correction" reading is **retracted**: the
delta is dominated by the completion channel (tahoe completed 714/800 vs
classic 658/800 — 56 fewer cap-exhausted responses), while among completed
responses classic was *more* accurate (91.3% vs 88.9%). This is consistent
with output compression helping finish within the fixed budget, not with a
demonstrated correctness gain. Curve anchor #3 (classic-acc 75%). Slate
pattern is task-type-driven, not difficulty-monotonic — as fixed-cap task
success. Data: `benchmarks/results/2026-09-16-mmlu-pro-800/`,
slice in `benchmarks/data/mmlu_pro_800.jsonl` (proportional stratified, seed 42).

**LiveCodeBench v6-150** (execution-verified code gen, 150 newest problems of
the Jan-Apr 2025 window, 300 trials):

| Arm | Fixed-cap task success | Avg total tokens | Empty answers | Completed | Completed-acc |
|---|---|---|---|---|---|
| classic | 28.7% (43/150) | 2192 | 103 | 47 | 91.5% |
| tahoe-93 | 33.3% (50/150) | 2182 | 99 | 51 | 98.0% |

Paired task-macro delta **+4.67pp, 95% task-cluster bootstrap CI
[+0.7, +9.3], paired permutation p=0.066 (Holm-adjusted p=0.66 across the
14-benchmark family) — not significant family-wise**; total tokens 0.995×.
**Correction (2026-11-18):** the earlier "all failures genuine wrong
answers" claim is **retracted** — 107/150 classic and 100/150 tahoe trials
sit at exactly the 2048 output-token cap, 103/99 of them with empty final
answers, all stored as wrong answers. Sandbox: corp-parity verifier
(`benchmarks/verifiers/lcb/final_test.py` verbatim) under `unshare -n` isolation — no docker needed.
Recorded as **null-trending-positive**. Curve anchor #4 (classic-acc 29%).
Data: `benchmarks/results/2026-09-17-lcb-v6-150/`, slice in
`benchmarks/data/lcb_v6_150.jsonl`.

**Slate pattern (4 harder benchmarks, 2026-09-16/17):** under the repaired
paired task-cluster analysis, only MMLU-Pro clears the family-wise bar
(+4.25pp, Holm p=0.0026) on the fixed-cap endpoint; AIME (+6.25pp, raw
p=0.024 but Holm p=0.26), LCB (+4.67pp, Holm p=0.66), GPQA (+1.52pp,
Holm p=1.00) trend positive without clearing it — 4/4 direction-consistent
as fixed-2048-token task success, each needing more trials for a
verdict-grade claim. All four deltas are consistent with the
output-compression/finish-within-budget hypothesis; correctness-gain
interpretations are not supported by the completed-response accuracies.

**7-task ablation (#55, 2026-09-17)** — classic vs tahoe-93 on agentic-style
tasks (routing ×2, code-fix ×2, plan, recover, search; 5 trials each):
tokens-per-solved-task lower on **all 7 tasks** (0.54–0.90×, aggregate
**0.65×**); no quality drop detected on 6 well-posed tasks incl. a +40pp win
on routing-02 at 0.54× tokens (5 trials per task — no statistical parity
claim; no equivalence margin was prespecified). The only quality drop
(plan-01, 0.20) is a task defect — ill-posed grader, filed as #110. Data:
`benchmarks/results/2026-09-17-ablation-7tasks/`.

## Stage-1 Derived Results — current publication evidence (2026-11-18)

Two models, 10 benchmark slices, 3 trials per sample, 2 arms (classic vs
tahoe), max_turns=1, max_tokens=2048, timeout=60s for both arms. The
accuracy and inferential figures below are the **current-grader derived
results**: the completed full Stage-1 derived pipeline re-graded all
63,348 trials of both raw archives offline and computed per-model
canonical statistics. All tables are generated blocks rendered from the
canonical payloads by `benchmarks/render_canonical_docs.py`.

**Exact task slices** (not all "full test sets"): GSM8K test (1,319 — full);
ARC-Challenge test (1,172 — full); BBH `logical_deduction_seven_objects`
(250 — full); BBH `tracking_shuffled_objects_seven_objects` (250 — full);
BBH `multistep_arithmetic_two` (**200-sample slice in the GLM run; all 250
in the gpt-oss run — the two runs' BBH-arith rows are not comparable**); MMLU
`college_mathematics` (100), `formal_logic` (126), `professional_accounting`
(282) — each subject's full test split; AGIEval LSAT-LR (510 — full); RACE
high-school split — **the first question of each of 1,045 sampled articles**
(not the full RACE test set).

**Inference framing.** The overall micro-accuracy deltas (+0.49pp GLM,
−0.19pp gpt-oss) are **not** called significant or null-tested: the
canonical paired inferential family is per benchmark (keyed on exact
`(benchmark, task_id, trial)` identity; Holm step-down over the 10
Stage-1 comparisons per model); there is no overall confirmatory test and
no prespecified equivalence margin. Derived significant pass-rate
permutation results (Holm): **GLM GSM8K — tahoe higher** (+2.1pp,
p=0.0010); **gpt-oss GSM8K — tahoe higher** (+1.4pp, p=0.0060);
**gpt-oss RACE — classic higher** (+1.1pp, p=0.0162). These are
current-grader derived results, not independent gold validation.

### GLM-5.3-Flash (derived, current graders)

<!-- CANONICAL_RESULTS:BEGIN summary@glm -->
## Overall

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | completed | completed acc | grader err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 15762 | 5254 | 15125 | 0.9596 | 0.9596 | 3159995 | 3886451 | 7046446 | 465.88 | 0 | 88 | 128 | 15630 | 0.9676 | 6 |
| tahoe | 15762 | 5254 | 15203 | 0.9645 | 0.9645 | 4575877 | 1984221 | 6560098 | 431.50 | 0 | 49 | 54 | 15706 | 0.9679 | 6 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc diff (tahoe-classic) | macro acc diff (tahoe-classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.4481 | 0.5105 | 0.9310 | 465.88 | 431.50 | +0.0049 | +0.0049 |
<!-- CANONICAL_RESULTS:END summary@glm -->

Verdict changes vs archived: fail→pass 1,853, pass→fail 13. Derived
significant per-benchmark result: **GSM8K — tahoe higher** (task-mean pass
0.9484 → 0.9699, p=0.0010); no other GLM comparison clears Holm (lsat
+1.4pp toward tahoe, p=0.208; mmlu_logic 2.4pp toward classic, p=0.448;
all others n.s.). Derived `truncated` failure-class count: 3 (per-arm
split 2/1: 2 classic gsm8k, 1 tahoe race); canonical `truncated`
counters are 0 because no truncated bool/finish_reason was recorded.

<details>
<summary>GLM per-benchmark pair ratios and paired inferential statistics
(generated)</summary>

<!-- CANONICAL_RESULTS:BEGIN pair@glm -->
## classic vs tahoe

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc diff (tahoe-classic) | macro acc diff (tahoe-classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.4481 | 0.5105 | 0.9310 | 465.88 | 431.50 | +0.0049 | +0.0049 |
| arc | 1.9682 | 0.4784 | 1.1229 | 217.39 | 244.67 | -0.0023 | -0.0023 |
| bbh | 1.4389 | 0.6110 | 0.8605 | 678.69 | 587.97 | -0.0067 | -0.0067 |
| bbh_arith | 3.0227 | 0.8284 | 1.4272 | 161.24 | 230.50 | -0.0017 | -0.0017 |
| bbh_track | 1.3924 | 0.5179 | 0.7830 | 749.21 | 588.99 | -0.0040 | -0.0040 |
| gsm8k | 2.2546 | 0.3760 | 0.8027 | 329.42 | 258.56 | +0.0215 | +0.0215 |
| lsat | 1.2507 | 0.4858 | 0.8437 | 868.03 | 721.24 | +0.0144 | +0.0144 |
| mmlu_acct | 1.7407 | 0.5824 | 0.9732 | 373.19 | 362.30 | +0.0024 | +0.0024 |
| mmlu_logic | 1.6894 | 0.8446 | 1.0919 | 461.76 | 517.10 | -0.0238 | -0.0238 |
| mmlu_math | 1.8515 | 0.7972 | 1.0161 | 533.79 | 538.55 | +0.0067 | +0.0067 |
| race | 1.1951 | 0.5268 | 1.0006 | 690.05 | 692.11 | -0.0022 | -0.0022 |
<!-- CANONICAL_RESULTS:END pair@glm -->

<!-- CANONICAL_RESULTS:BEGIN paired@glm -->
## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff (a-b) | mean token diff (a-b) | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arc/classic_vs_tahoe | 1172 | 3516 | 0.9784 | 0.9761 | +0.0023 | -26.1 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh/classic_vs_tahoe | 250 | 750 | 0.9947 | 0.9880 | +0.0067 | +94.1 | 0.0001 | 0.0010 | 1.0000 | 0.6608 | 0.0000 |
| bbh_arith/classic_vs_tahoe | 200 | 600 | 1.0000 | 0.9983 | +0.0017 | -68.9 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh_track/classic_vs_tahoe | 250 | 750 | 0.9987 | 0.9947 | +0.0040 | +162.4 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9484 | 0.9699 | -0.0215 | +61.6 | 0.0001 | 0.0010 | 0.0010 | 0.0000 | 0.0000 |
| lsat/classic_vs_tahoe | 510 | 1530 | 0.9346 | 0.9490 | -0.0144 | +126.8 | 0.0001 | 0.0010 | 0.2079 | 0.1664 | 0.0000 |
| mmlu_acct/classic_vs_tahoe | 282 | 846 | 0.9610 | 0.9634 | -0.0024 | +9.6 | 0.2088 | 0.6263 | 1.0000 | 1.0000 | 0.1620 |
| mmlu_logic/classic_vs_tahoe | 126 | 378 | 0.9550 | 0.9312 | +0.0238 | -40.5 | 0.0009 | 0.0036 | 0.4480 | 0.2913 | 0.0001 |
| mmlu_math/classic_vs_tahoe | 100 | 300 | 0.9433 | 0.9500 | -0.0067 | -8.1 | 0.7096 | 1.0000 | 1.0000 | 1.0000 | 0.1620 |
| race/classic_vs_tahoe | 1045 | 3135 | 0.9410 | 0.9388 | +0.0022 | -0.4 | 0.9372 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

Multiplicity: holm step-down correction over 10 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).
<!-- CANONICAL_RESULTS:END paired@glm -->

</details>

### gpt-oss-120b (derived, current graders)

<!-- CANONICAL_RESULTS:BEGIN summary@oss -->
## Overall

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | completed | completed acc | grader err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 15912 | 5304 | 14865 | 0.9342 | 0.9342 | 4063215 | 4278233 | 8341448 | 561.15 | 0 | 32 | 32 | 15880 | 0.9361 | 6 |
| tahoe | 15912 | 5304 | 14835 | 0.9323 | 0.9323 | 5511207 | 2919526 | 8430733 | 568.30 | 0 | 9 | 10 | 15902 | 0.9329 | 6 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc diff (tahoe-classic) | macro acc diff (tahoe-classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.3564 | 0.6824 | 1.0107 | 561.15 | 568.30 | -0.0019 | -0.0019 |
<!-- CANONICAL_RESULTS:END summary@oss -->

Verdict changes vs archived: fail→pass 1,395, pass→fail 20. Derived
significant per-benchmark results: **GSM8K — tahoe higher** (task-mean
pass 0.9366 → 0.9505, p=0.0060) and **RACE — classic higher** (0.8982 →
0.8871, p=0.0162); lsat runs 2.3pp toward classic but is n.s. (p=0.203);
all others n.s. Derived `truncated` failure-class count: 0.

<details>
<summary>gpt-oss per-benchmark pair ratios and paired inferential statistics
(generated)</summary>

<!-- CANONICAL_RESULTS:BEGIN pair@oss -->
## classic vs tahoe

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc diff (tahoe-classic) | macro acc diff (tahoe-classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.3564 | 0.6824 | 1.0107 | 561.15 | 568.30 | -0.0019 | -0.0019 |
| arc | 1.6119 | 0.7118 | 1.2531 | 256.82 | 323.05 | -0.0037 | -0.0037 |
| bbh | 1.3534 | 0.8311 | 0.9713 | 968.20 | 934.18 | +0.0067 | +0.0067 |
| bbh_arith | 1.8922 | 0.8828 | 1.1976 | 327.48 | 393.25 | -0.0027 | -0.0027 |
| bbh_track | 1.3218 | 0.8343 | 1.0065 | 800.37 | 808.84 | -0.0040 | -0.0040 |
| gsm8k | 1.7139 | 0.4037 | 0.7780 | 476.38 | 365.20 | +0.0139 | +0.0139 |
| lsat | 1.2065 | 0.7247 | 0.9681 | 1021.87 | 1016.51 | -0.0229 | -0.0229 |
| mmlu_acct | 1.5104 | 0.8162 | 1.0971 | 491.77 | 539.50 | +0.0000 | +0.0000 |
| mmlu_logic | 1.4869 | 0.8413 | 1.0684 | 556.41 | 597.77 | -0.0053 | -0.0053 |
| mmlu_math | 1.5633 | 0.8337 | 1.0123 | 682.92 | 691.30 | +0.0000 | +0.0000 |
| race | 1.1772 | 0.8455 | 1.1079 | 722.73 | 810.79 | -0.0112 | -0.0112 |
<!-- CANONICAL_RESULTS:END pair@oss -->

<!-- CANONICAL_RESULTS:BEGIN paired@oss -->
## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff (a-b) | mean token diff (a-b) | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arc/classic_vs_tahoe | 1172 | 3516 | 0.9630 | 0.9593 | +0.0037 | -62.6 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh/classic_vs_tahoe | 250 | 750 | 0.9907 | 0.9973 | -0.0067 | +27.5 | 0.0098 | 0.0294 | 1.0000 | 0.5742 | 0.1583 |
| bbh_arith/classic_vs_tahoe | 250 | 750 | 0.9987 | 0.9960 | +0.0027 | -64.6 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh_track/classic_vs_tahoe | 250 | 750 | 1.0000 | 0.9960 | +0.0040 | -5.2 | 0.3292 | 0.6583 | 1.0000 | 0.5742 | 0.1669 |
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9366 | 0.9505 | -0.0139 | +99.0 | 0.0001 | 0.0010 | 0.0060 | 0.0060 | 0.0000 |
| lsat/classic_vs_tahoe | 510 | 1530 | 0.8536 | 0.8307 | +0.0229 | +27.8 | 0.0001 | 0.0010 | 0.2032 | 0.1659 | 0.0008 |
| mmlu_acct/classic_vs_tahoe | 282 | 846 | 0.8960 | 0.8960 | -0.0000 | -42.8 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| mmlu_logic/classic_vs_tahoe | 126 | 378 | 0.9550 | 0.9497 | +0.0053 | -36.3 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| mmlu_math/classic_vs_tahoe | 100 | 300 | 0.9667 | 0.9667 | +0.0000 | -8.1 | 0.6593 | 0.6593 | 1.0000 | 1.0000 | 0.0550 |
| race/classic_vs_tahoe | 1045 | 3135 | 0.8982 | 0.8871 | +0.0112 | -70.0 | 0.0001 | 0.0010 | 0.0162 | 0.0150 | 0.0000 |

Multiplicity: holm step-down correction over 10 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).
<!-- CANONICAL_RESULTS:END paired@oss -->

</details>

### Input and analysis lineage (generated)

<details>
<summary>Lineage: derived-artifact inputs, hashes, and analysis
implementation</summary>

<!-- CANONICAL_RESULTS:BEGIN inputs@glm -->
## Input lineage

| input | sha-256 | trials | trials by arm | task-set sha-256 | grader(s) | model(s) |
|---|---|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-full-v3/glm-stage1-derived.json` | `ba953dfdcb9cf19ccdd1a762e4e8db8b4dd72c979e0281b783766bff79e1c381` | 31524 | classic: 15762, tahoe: 15762 | `a9a71f2fc94a3566b5c6a6cc73ef6f191cc9743fbe4fc6702fedda31f1eaffd5` | run_public_bench.stage1 run_public_bench-numeric-v6 (benchmarks/run_public_bench.py, sha-256 bdbc5208675883e8f45806246345a0e81cd430e70415a7150fba882eabbb2d8e) | not recorded |

Total trials: 31524.

Grader-error outcomes: 12 recorded (classic: 6, tahoe: 6); they are reported as their own outcome class and never silently dropped.
<!-- CANONICAL_RESULTS:END inputs@glm -->

<!-- CANONICAL_RESULTS:BEGIN inputs@oss -->
## Input lineage

| input | sha-256 | trials | trials by arm | task-set sha-256 | grader(s) | model(s) |
|---|---|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-full-v3/oss-stage1-derived.json` | `0d98f4905cf9fc606c0f12db6e24ea08d866e1bef3e3e7604fa033e3a388212e` | 31824 | classic: 15912, tahoe: 15912 | `2699bb71e699c9acff5b280f6018e9c2f1a5ee8b7fdf9b0d8bd382de54b0051c` | run_public_bench.stage1 run_public_bench-numeric-v6 (benchmarks/run_public_bench.py, sha-256 bdbc5208675883e8f45806246345a0e81cd430e70415a7150fba882eabbb2d8e) | not recorded |

Total trials: 31824.

Grader-error outcomes: 12 recorded (classic: 6, tahoe: 6); they are reported as their own outcome class and never silently dropped.
<!-- CANONICAL_RESULTS:END inputs@oss -->

<!-- CANONICAL_RESULTS:BEGIN analysis -->
## Analysis implementation

| source file | sha-256 |
|---|---|
| `benchmarks/canonical_results.py` | `9a7ca4b6ad08e965652d833d711e84fdf01a697cd2e925c65732b94bc244d31c` |
| `benchmarks/report.py` | `be7ac408bfe0c592e6d7d7ae6152f1f7dd75cdde5818728fd008e1d62cef9975` |
| `benchmarks/stats.py` | `d497684839594a1264e615be8d8440ee27210adf6e732026ea32bb649cb308b8` |

Options: seed 42, 10000 bootstrap resamples, 10000 permutation draws; payload schema `canonical-results/1`, analysis schema `canonical-analysis/1`.
<!-- CANONICAL_RESULTS:END analysis -->

</details>

### Superseded stored grades (2026-09-13 archives — historical)

The 2026-09-13 stored grades are **superseded** by the derived results
above and are retained only as history: stored overall GLM 88.9% → 91.8%
(+2.9pp stored) and gpt-oss 89.1% → 88.9% (−0.2pp stored); stored GSM8K
(GLM) 68.5% → 80.3% (+11.8pp stored). The stored grades were
grader-version-specific (see the Grader Format Lesson); under the
current-grader derived regrade the GSM8K rows are 94.8% → 97.0% (GLM) and
93.7% → 95.0% (gpt-oss). Do not cite stored values as current results;
the raw archives remain the immutable inputs and are the provenance
source for every derived artifact.

## Evaluation History

| Date | Run | Trials | Key result |
|---|---|---|---|
| 2026-09-13 | Pilot (10 samples) | 600 | output-token ratio ~0.60×, +1pp quality |
| 2026-09-13 | 200-sample run | 10,956 | output-token ratio ~0.57×, quality delta ≈ 0 (no equivalence margin) |
| 2026-09-14 | GLM stage-1 slices | 31,524 | output ratio 0.511×, total ratio 0.931×, stored-grade delta +2.9pp |
| 2026-09-14 | gpt-oss-120b stage-1 slices | 31,824 | output ratio 0.682×, total ratio 1.011×, stored-grade delta −0.2pp (n.s.; parity not established) |
| 2026-09-14 | BBH grader fix + re-grade of stored answers | — | BBH-track "regression" was a grader artifact; modern practice writes derived artifacts (CLI: `benchmarks/fix_gsm8k_extraction.py --input … --output …`), never mutating archives |
| 2026-11-18 | Full Stage-1 derived regrade + canonical statistics (v1, numeric-v4 GSM8K) | — | all 63,348 trials re-graded with current graders into derived artifacts; derived overall GLM +0.56pp / gpt-oss −0.15pp; superseded by the v2 extractor-v5 regrade below |
| 2026-11-18 | Full Stage-1 derived regrade v2 (GSM8K numeric-v5) + canonical statistics | — | re-graded with the restatement-corrected extractor (only GSM8K rows changed); derived overall GLM +0.49pp / gpt-oss −0.19pp; superseded by the v3 extractor-v6 regrade below |
| 2026-11-18 | Full Stage-1 derived regrade v3 (GSM8K numeric-v6) + canonical statistics | — | re-graded with the clock-form-corrected extractor (only GSM8K rows changed; six trials per model, all on gsm8k-1001); derived overall GLM +0.49pp / gpt-oss −0.19pp; derived GSM8K deltas significant on both models (GLM p=0.0010, gpt-oss p=0.0060), gpt-oss RACE favors classic (p=0.0162) — current publication evidence |

## Grader Format Lesson (important)

The original BBH grader only accepted answers in "(X)" format. Models answering
with bare letters ("E") were failed despite being correct. This produced a fake
"BBH-track quality regression" in earlier GLM results (-13.8% that vanished after
the fix — actual: classic 99.9%, tahoe 99.5%).

**Rule**: graders must accept every reasonable answer format (parenthesized,
bare letter, letter-in-text). Test graders against actual model output
distributions before trusting cross-arm comparisons. Grader fix applied in
commit 0645918; stored results re-graded offline.

**GSM8K grader sensitivity — resolution (2026-11-18).** The GSM8K numeric
extractor went through several versions (v1 → v3 → v4 → current **v5**), and
the archived grades reflected whichever version was live. The same study
directory contains **two different
GSM8K grade sets**: `full_test_eval.json` stores classic 68.5% / tahoe
80.3%, while `single_gsm8k.json` — a *separate run* with different model
responses — stores 83.0% / 95.2%. A >10pp swing on identical tasks showed
the stored GSM8K grades were grader-sensitive. **The regrade has now been
run at full scale**: `benchmarks/fix_stage1_extraction.py` (helper
`benchmarks/stage1_regrade.py`) re-graded **all ten Stage-1 benchmarks** of
both raw archives into derived artifacts (read-only input, exclusive-create
output, original verdicts preserved as `archived_*` fields, grader sha-256
pinned), and `benchmarks/canonical_results.py` computed per-model canonical
statistics. A final audit found the v4 extractor lost correct stated
answers carrying unit-conversion restatements or trailing context
(`'**Answer: 160 minutes (2 hours 40 minutes).**'` → 40), so the GSM8K rows
were re-graded with the **numeric-v5** extractor (explicit Answer-marker
priority ladder; only GSM8K rows changed); a second audit found v5 still
mangled correct answers stated in explicit clock form (H:MM am/pm — the
time separator let the numeric heuristics grab the wrong fragment, e.g.
`4:30 pm` → 30), so the GSM8K rows were re-graded again with the
**numeric-v6** extractor (recognizes clock-form answers in plain, bold,
and `\boxed{}` LaTeX forms before the v5 ladder; only GSM8K rows changed —
six trials per model, all on `gsm8k-1001`). Current derived GSM8K
(expectations reconstructed from archived grader details — not independent
gold): GLM 94.8% → 97.0% (+2.1pp, pass-permutation Holm p=0.0010 — tahoe
higher); gpt-oss 93.7% → 95.0% (+1.4pp, p=0.0060 — tahoe higher). The
interim GSM8K-only regrade
(`benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/`), the v1 full
regrade (`2026-11-18-stage1-full-v1/`, v4-extractor GSM8K rows), and the v2
full regrade (`2026-11-18-stage1-full-v2/`, v5-extractor GSM8K rows) are
all superseded by v3 and preserved unchanged. Publication evidence:
`benchmarks/results/derived/2026-11-18-stage1-full-v3/` (index:
`benchmarks/results/derived/README.md`).

## Key Findings

1. **The measured manipulation is the 93-token prompt.** The archived
   comparisons measure TAHOE-93 as a whole system prompt vs none. Typed
   refs, protocols, and the runtime are design artifacts; their individual
   mechanisms were not isolated (archived tahoe-arm trials record zero
   emitted typed refs). The preregistered factorial experiment that would
   separate structure from the answer-only contract —
   `docs/PREREGISTRATION-structure-answer.md` — is prepared but **has not
   been run**.
2. **Output compression transfers across models**: output-token ratio
   0.511× (GLM) / 0.682× (gpt-oss), savings in all 20 model-benchmark pairs
   (~12–62% of output tokens). Total-token ratio 0.931× / 1.011× — the
   prompt overhead offsets most of the output saving.
3. **Quality deltas are derived, current-grader, and small**: overall
   +0.49pp (GLM) / −0.19pp (gpt-oss) — **not** called significant or
   null-tested (per-benchmark Holm family only; no overall confirmatory
   test, no equivalence margin). Per-benchmark derived significance:
   GSM8K favors tahoe on both models (GLM +2.1pp p=0.0010, gpt-oss +1.4pp
   p=0.0060); RACE favors classic on gpt-oss (+1.1pp p=0.0162).
4. **Reasoning-heavy models compress less** (gpt-oss-120b output ratio
   0.682 vs GLM 0.511) — their CoT is already lean.
5. **Fixed 2048-token cap effects are real**: derived stage-1
   cap-exhausted counts (classic/tahoe) are 88/49 (GLM) and 32/9
   (gpt-oss), with 128/54 and 32/10 empty responses; the harder slate runs
   hit the cap far more often (up to 68% of trials). Fixed-cap task
   success conflates completion and correctness; the
   output-compression/finish-within-budget hypothesis remains the best
   supported explanation of the slate deltas. Archives carry no
   `finish_reason`: the canonical zero `truncated` counters are
   absence-of-field, not zero truncation (derived truncated-class counts:
   3 GLM, 0 gpt-oss).

## Infrastructure

- Runners: `benchmarks/run_skill_compare.py` (canonical arm comparison), `run_single_bench.py` (per-benchmark), `run_parallel_bench.py` (all + CIs) — see `benchmarks/README.md`
- **Full Stage-1 regrade CLI**: `benchmarks/fix_stage1_extraction.py` (required `--input`/`--output`) — re-grades all ten archived Stage-1 benchmarks into a separate derived artifact (never mutates the archive; refuses overwrite; pins grader sha-256); helper pipeline module: `benchmarks/stage1_regrade.py`
- **GSM8K-only regrade CLI**: `benchmarks/fix_gsm8k_extraction.py` (required `--input`/`--output`); helper pipeline module: `benchmarks/gsm8k_regrade.py`
- **Canonical offline stats**: `benchmarks/canonical_results.py` — deterministic JSON+Markdown from derived artifacts; no model evaluations; labeled micro/macro estimands; truncation/cap/empty outcomes from recorded fields only; keyed task-cluster paired comparisons with Holm correction; refuses to overwrite
- **Doc rendering**: `benchmarks/render_canonical_docs.py` — renders Markdown/LaTeX blocks from a canonical payload and updates (`--update PATH --block NAME`) / verifies (`--check`) marked generated blocks in docs
- **Runs never overwrite**: active runners write to `results/runs/<timestamp>_<name>/` via `outdir.py`
- Stats: `benchmarks/stats.py` — bootstrap CIs, permutation tests, Wilcoxon, Cohen's h
- Protocol: `benchmarks/EVAL_PROTOCOL.md` — frozen invariants
- Preregistration: `docs/PREREGISTRATION-structure-answer.md` — structure × answer-only factorial experiment, frozen before any trial; **prepared, not run**
- Rate-limit retry: worker_fn backs off on 429/inflight errors, retries empty 0-token answers

## Raw Data

Results are frozen into dated study directories (see
`benchmarks/results/README.md` for the index); derived artifacts live under
`benchmarks/results/derived/` (index: `benchmarks/results/derived/README.md`):

- **Current Stage-1 publication evidence**:
  `benchmarks/results/derived/2026-11-18-stage1-full-v3/` — derived
  artifacts (`glm-stage1-derived.json`, `oss-stage1-derived.json`) and
  per-model canonical statistics
  (`{glm,oss}-canonical/canonical_results.{json,md}`), with run-metadata
  sidecars and its own README of exact commands, versions, and SHA-256 pins
- Superseded full regrades (preserved unchanged):
  `benchmarks/results/derived/2026-11-18-stage1-full-v2/` (numeric-v5
  GSM8K extractor) and
  `benchmarks/results/derived/2026-11-18-stage1-full-v1/` (numeric-v4)
- Interim GSM8K-only regrade (superseded):
  `benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/`
- Raw Stage-1 archives (immutable inputs; stored grades superseded):
  `benchmarks/results/2026-09-13-stage1-full/full_test_eval.json` (GLM),
  `oss_full_eval.json` (gpt-oss-120b), plus per-benchmark
  `single_{benchmark}.json` (note: `single_gsm8k.json` is a *separate run*,
  not a regrade of the same responses)
- Skill comparisons: `benchmarks/results/2026-09-14-skill-study/skill_cmp_*.json`
- Legacy summaries: same directory (`FULL_TEST_SET_EVAL.md`, `FULL_EVAL_SUMMARY.md`)

**Note**: cite Stage-1 accuracies from the derived artifacts (current
graders); the raw archives' stored grades and the legacy summaries are
grader-version-specific history.

## Model Endpoints

- GLM-5.3-Flash: `https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1`
- gpt-oss-120b: `https://api.eliza.yandex.net/raw/internal/gpt-oss-120b/v1` (note: NO /v2)
- Auth: `Authorization: Bearer $TOKEN`, pool header `Ya-Pool` (quota: 5 inflight per family)
