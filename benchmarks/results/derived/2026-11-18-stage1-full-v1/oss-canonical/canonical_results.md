# Canonical results

Schema `canonical-results/1`. Deterministic: no wall-clock timestamps; statistics recomputed offline from immutable trial inputs — no model evaluations.

## Inputs

| input | sha-256 | trials | trials by arm | task-set sha-256 |
|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-stage1-derived.json` | `c3bab585fe9168fa84f976ba97804ea362204f15ccb1861dbfc5d6984c64ee8b` | 31824 | classic: 15912, tahoe: 15912 | `2699bb71e699c9acff5b280f6018e9c2f1a5ee8b7fdf9b0d8bd382de54b0051c` |

Total trials: 31824.

### Available manifest metadata (recorded as available; never fabricated)

- **`benchmarks/results/derived/2026-11-18-stage1-full-v1/oss-stage1-derived.json`**
  - `manifest`: {"benchmarks": {"arc": {"cap_exhausted": {"empty_response": 0, "passed": 0, "trials": 0, "truncated": 0}, "failure_classes": {"none": 6759, "wrong_answer": 273…
  - trial field `output_token_cap`: ["2048"]

### Analysis implementation

| source file | sha-256 |
|---|---|
| `benchmarks/canonical_results.py` | `9a7ca4b6ad08e965652d833d711e84fdf01a697cd2e925c65732b94bc244d31c` |
| `benchmarks/report.py` | `be7ac408bfe0c592e6d7d7ae6152f1f7dd75cdde5818728fd008e1d62cef9975` |
| `benchmarks/stats.py` | `d497684839594a1264e615be8d8440ee27210adf6e732026ea32bb649cb308b8` |

Options: seed 42, 10000 bootstrap resamples, 10000 permutation draws; payload schema `canonical-results/1`, analysis schema `canonical-analysis/1`.

## Estimands

- **macro_accuracy** — Task-equal-weighted (macro) accuracy: the mean over tasks of each task's trial-mean pass rate; every task weighs the same regardless of how many trials it has.
- **micro_accuracy** — Trial-pooled (micro) accuracy within a benchmark/arm: successes / trials. Tasks with more repeated trials weigh proportionally more.
- **outcomes** — Truncation / cap-exhausted / empty / grader-error / completed counts derived only from fields actually present on each trial (explicit flags, finish_reason, recorded output caps, final_answer, failure_class); finish_reason and failure_class are never fabricated for archives that do not record them, and grader_error is counted only when failure_class literally equals "grader_error".
- **paired_comparisons** — Keyed task-cluster paired comparisons on exact (benchmark, task_id, trial) identity; repeated matched trials are averaged within tasks; Holm step-down correction over the comparison family.
- **token_ratio_tahoe_over_classic** — tahoe token spend / classic token spend for the same scope; null when the classic spend is zero.
- **token_sums** — Exact sums of recorded input/output/total token counts over all trials in scope.
- **total_spend_per_success** — sum(total_tokens over ALL attempts, failures included) / number of successes; null (undefined) when there are zero successes.

## Overall

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 15912 | 5304 | 14844 | 0.9329 | 0.9329 | 4063215 | 4278233 | 8341448 | 561.94 | 0 | 32 | 32 | 6 | 15880 | 0.9348 |
| tahoe | 15912 | 5304 | 14820 | 0.9314 | 0.9314 | 5511207 | 2919526 | 8430733 | 568.88 | 0 | 9 | 10 | 6 | 15902 | 0.9320 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.3564 | 0.6824 | 1.0107 | 561.94 | 568.88 | -0.0015 | -0.0015 |

## Benchmarks

### `arc`

Task-set sha-256: `ad12160c9dc9f09087c57503de65bdd0d253beee3f083efa9c127278deda236c`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3516 | 1172 | 3386 | 0.9630 | 0.9630 | 522906 | 346696 | 869602 | 256.82 | 0 | 0 | 0 | 0 | 3516 | 0.9630 |
| tahoe | 3516 | 1172 | 3373 | 0.9593 | 0.9593 | 842862 | 246795 | 1089657 | 323.05 | 0 | 0 | 0 | 0 | 3516 | 0.9593 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| arc | 1.6119 | 0.7118 | 1.2531 | 256.82 | 323.05 | -0.0037 | -0.0037 |


### `bbh`

Task-set sha-256: `434d96b0084eb22d3202b9ea8fc1678f0d6a631af3f8d477d8336ef9188b5934`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 750 | 250 | 743 | 0.9907 | 0.9907 | 193116 | 526260 | 719376 | 968.20 | 0 | 7 | 7 | 0 | 743 | 1.0000 |
| tahoe | 750 | 250 | 748 | 0.9973 | 0.9973 | 261366 | 437397 | 698763 | 934.18 | 0 | 2 | 2 | 0 | 748 | 1.0000 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh | 1.3534 | 0.8311 | 0.9713 | 968.20 | 934.18 | +0.0067 | +0.0067 |


### `bbh_arith`

Task-set sha-256: `ced92befbed632de491ad47da7c2c865efa4b1cf7d514f544595b49a94338beb`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 750 | 250 | 749 | 0.9987 | 0.9987 | 76500 | 168783 | 245283 | 327.48 | 0 | 0 | 0 | 0 | 750 | 0.9987 |
| tahoe | 750 | 250 | 747 | 0.9960 | 0.9960 | 144750 | 149010 | 293760 | 393.25 | 0 | 0 | 0 | 0 | 750 | 0.9960 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh_arith | 1.8922 | 0.8828 | 1.1976 | 327.48 | 393.25 | -0.0027 | -0.0027 |


### `bbh_track`

Task-set sha-256: `a6776126c8ed43b7ffeb36d23a2847daa2446574249ba1ebe5952b3c69b291dd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 750 | 250 | 750 | 1.0000 | 1.0000 | 212091 | 388188 | 600279 | 800.37 | 0 | 0 | 0 | 0 | 750 | 1.0000 |
| tahoe | 750 | 250 | 747 | 0.9960 | 0.9960 | 280341 | 323861 | 604202 | 808.84 | 0 | 0 | 0 | 0 | 750 | 0.9960 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh_track | 1.3218 | 0.8343 | 1.0065 | 800.37 | 808.84 | -0.0040 | -0.0040 |


### `gsm8k`

Task-set sha-256: `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3957 | 1319 | 3685 | 0.9313 | 0.9313 | 504360 | 1261097 | 1765457 | 479.09 | 0 | 6 | 6 | 6 | 3951 | 0.9327 |
| tahoe | 3957 | 1319 | 3746 | 0.9467 | 0.9467 | 864447 | 509083 | 1373530 | 366.67 | 0 | 0 | 1 | 6 | 3956 | 0.9469 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| gsm8k | 1.7139 | 0.4037 | 0.7780 | 479.09 | 366.67 | +0.0154 | +0.0154 |


### `lsat`

Task-set sha-256: `be1fda68a61d453312b74d0b829885e2211383dc27956e871429c9362ef4c44b`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 1530 | 510 | 1306 | 0.8536 | 0.8536 | 674271 | 660293 | 1334564 | 1021.87 | 0 | 6 | 6 | 0 | 1524 | 0.8570 |
| tahoe | 1530 | 510 | 1271 | 0.8307 | 0.8307 | 813501 | 478483 | 1291984 | 1016.51 | 0 | 3 | 3 | 0 | 1527 | 0.8324 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| lsat | 1.2065 | 0.7247 | 0.9681 | 1021.87 | 1016.51 | -0.0229 | -0.0229 |


### `mmlu_acct`

Task-set sha-256: `5a218759fc66ea39795411dc89e74b6c8ea83286901a9b5303582d843c163d54`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 846 | 282 | 758 | 0.8960 | 0.8960 | 150825 | 221933 | 372758 | 491.77 | 0 | 4 | 4 | 0 | 842 | 0.9002 |
| tahoe | 846 | 282 | 758 | 0.8960 | 0.8960 | 227811 | 181133 | 408944 | 539.50 | 0 | 2 | 2 | 0 | 844 | 0.8981 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_acct | 1.5104 | 0.8162 | 1.0971 | 491.77 | 539.50 | +0.0000 | +0.0000 |


### `mmlu_logic`

Task-set sha-256: `a3256e35e1481a6a0f4c93159ee5fa2abb58710889673e1de225a8b2b60f0caa`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 378 | 126 | 361 | 0.9550 | 0.9550 | 70644 | 130219 | 200863 | 556.41 | 0 | 1 | 1 | 0 | 377 | 0.9576 |
| tahoe | 378 | 126 | 359 | 0.9497 | 0.9497 | 105042 | 109558 | 214600 | 597.77 | 0 | 0 | 0 | 0 | 378 | 0.9497 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_logic | 1.4869 | 0.8413 | 1.0684 | 556.41 | 597.77 | -0.0053 | -0.0053 |


### `mmlu_math`

Task-set sha-256: `6f72e4896a4d650b6079c71539ff157f826d6f78f966d054c7d37654cbed497c`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 300 | 100 | 290 | 0.9667 | 0.9667 | 48465 | 149583 | 198048 | 682.92 | 0 | 8 | 8 | 0 | 292 | 0.9932 |
| tahoe | 300 | 100 | 290 | 0.9667 | 0.9667 | 75765 | 124712 | 200477 | 691.30 | 0 | 2 | 2 | 0 | 298 | 0.9732 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_math | 1.5633 | 0.8337 | 1.0123 | 682.92 | 691.30 | +0.0000 | +0.0000 |


### `race`

Task-set sha-256: `98bf131827e12e6724e1d21999035e08a7ce94e2ffc79b2cbb57d91a7c4edf33`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3135 | 1045 | 2816 | 0.8982 | 0.8982 | 1610037 | 425181 | 2035218 | 722.73 | 0 | 0 | 0 | 0 | 3135 | 0.8982 |
| tahoe | 3135 | 1045 | 2781 | 0.8871 | 0.8871 | 1895322 | 359494 | 2254816 | 810.79 | 0 | 0 | 0 | 0 | 3135 | 0.8871 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| race | 1.1772 | 0.8455 | 1.1079 | 722.73 | 810.79 | -0.0112 | -0.0112 |

## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff | mean token diff | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arc/classic_vs_tahoe | 1172 | 3516 | 0.9630 | 0.9593 | +0.0037 | -62.6 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh/classic_vs_tahoe | 250 | 750 | 0.9907 | 0.9973 | -0.0067 | +27.5 | 0.0098 | 0.0294 | 1.0000 | 0.5742 | 0.1583 |
| bbh_arith/classic_vs_tahoe | 250 | 750 | 0.9987 | 0.9960 | +0.0027 | -64.6 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh_track/classic_vs_tahoe | 250 | 750 | 1.0000 | 0.9960 | +0.0040 | -5.2 | 0.3292 | 0.6583 | 1.0000 | 0.5742 | 0.1669 |
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9313 | 0.9467 | -0.0154 | +99.0 | 0.0001 | 0.0010 | 0.0030 | 0.0023 | 0.0000 |
| lsat/classic_vs_tahoe | 510 | 1530 | 0.8536 | 0.8307 | +0.0229 | +27.8 | 0.0001 | 0.0010 | 0.2032 | 0.1659 | 0.0008 |
| mmlu_acct/classic_vs_tahoe | 282 | 846 | 0.8960 | 0.8960 | -0.0000 | -42.8 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| mmlu_logic/classic_vs_tahoe | 126 | 378 | 0.9550 | 0.9497 | +0.0053 | -36.3 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| mmlu_math/classic_vs_tahoe | 100 | 300 | 0.9667 | 0.9667 | +0.0000 | -8.1 | 0.6593 | 0.6593 | 1.0000 | 1.0000 | 0.0550 |
| race/classic_vs_tahoe | 1045 | 3135 | 0.8982 | 0.8871 | +0.0112 | -70.0 | 0.0001 | 0.0010 | 0.0162 | 0.0150 | 0.0000 |

Multiplicity: holm step-down correction over 10 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).

Notes: "—" marks undefined values (JSON null): zero successes for total spend/success, zero classic spend for ratios, no completed responses for completed accuracy. Micro and macro accuracy are distinct estimands and are never mixed; see Estimands above.
