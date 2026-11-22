# Canonical results

Schema `canonical-results/1`. Deterministic: no wall-clock timestamps; statistics recomputed offline from immutable trial inputs — no model evaluations.

## Inputs

| input | sha-256 | trials | trials by arm | task-set sha-256 |
|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-stage1-derived.json` | `27d177fbd02e620adf452a3874695109410e71f435ff458249a29d254064bd77` | 31524 | classic: 15762, tahoe: 15762 | `a9a71f2fc94a3566b5c6a6cc73ef6f191cc9743fbe4fc6702fedda31f1eaffd5` |

Total trials: 31524.

### Available manifest metadata (recorded as available; never fabricated)

- **`benchmarks/results/derived/2026-11-18-stage1-full-v1/glm-stage1-derived.json`**
  - `manifest`: {"benchmarks": {"arc": {"cap_exhausted": {"empty_response": 7, "passed": 0, "trials": 7, "truncated": 0}, "failure_classes": {"empty_response": 11, "none": 687…
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
| classic | 15762 | 5254 | 15110 | 0.9586 | 0.9586 | 3159995 | 3886451 | 7046446 | 466.34 | 0 | 88 | 128 | 6 | 15630 | 0.9666 |
| tahoe | 15762 | 5254 | 15199 | 0.9643 | 0.9643 | 4575877 | 1984221 | 6560098 | 431.61 | 0 | 49 | 54 | 6 | 15706 | 0.9677 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.4481 | 0.5105 | 0.9310 | 466.34 | 431.61 | +0.0056 | +0.0056 |

## Benchmarks

### `arc`

Task-set sha-256: `ad12160c9dc9f09087c57503de65bdd0d253beee3f083efa9c127278deda236c`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3516 | 1172 | 3440 | 0.9784 | 0.9784 | 323518 | 424314 | 747832 | 217.39 | 0 | 4 | 8 | 0 | 3508 | 0.9806 |
| tahoe | 3516 | 1172 | 3432 | 0.9761 | 0.9761 | 636732 | 202980 | 839712 | 244.67 | 0 | 3 | 3 | 0 | 3513 | 0.9769 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| arc | 1.9682 | 0.4784 | 1.1229 | 217.39 | 244.67 | -0.0023 | -0.0023 |


### `bbh`

Task-set sha-256: `434d96b0084eb22d3202b9ea8fc1678f0d6a631af3f8d477d8336ef9188b5934`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 750 | 250 | 746 | 0.9947 | 0.9947 | 152608 | 353692 | 506300 | 678.69 | 0 | 0 | 1 | 0 | 749 | 0.9960 |
| tahoe | 750 | 250 | 741 | 0.9880 | 0.9880 | 219585 | 216103 | 435688 | 587.97 | 0 | 1 | 0 | 0 | 749 | 0.9880 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh | 1.4389 | 0.6110 | 0.8605 | 678.69 | 587.97 | -0.0067 | -0.0067 |


### `bbh_arith`

Task-set sha-256: `7e4640631e19fadc275ff786d54a70db9c0e28e3d7486fa8baa9bdfdaee13fab`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 600 | 200 | 600 | 1.0000 | 1.0000 | 26400 | 70344 | 96744 | 161.24 | 0 | 0 | 0 | 0 | 600 | 1.0000 |
| tahoe | 600 | 200 | 599 | 0.9983 | 0.9983 | 79800 | 58271 | 138071 | 230.50 | 0 | 0 | 0 | 0 | 600 | 0.9983 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh_arith | 3.0227 | 0.8284 | 1.4272 | 161.24 | 230.50 | -0.0017 | -0.0017 |


### `bbh_track`

Task-set sha-256: `a6776126c8ed43b7ffeb36d23a2847daa2446574249ba1ebe5952b3c69b291dd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 750 | 250 | 749 | 0.9987 | 0.9987 | 170109 | 391051 | 561160 | 749.21 | 0 | 0 | 0 | 0 | 750 | 0.9987 |
| tahoe | 750 | 250 | 746 | 0.9947 | 0.9947 | 236859 | 202528 | 439387 | 588.99 | 0 | 0 | 0 | 0 | 750 | 0.9947 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| bbh_track | 1.3924 | 0.5179 | 0.7830 | 749.21 | 588.99 | -0.0040 | -0.0040 |


### `gsm8k`

Task-set sha-256: `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3957 | 1319 | 3738 | 0.9447 | 0.9447 | 280788 | 955515 | 1236303 | 330.74 | 0 | 9 | 8 | 6 | 3947 | 0.9470 |
| tahoe | 3957 | 1319 | 3834 | 0.9689 | 0.9689 | 633051 | 359308 | 992359 | 258.83 | 0 | 2 | 2 | 6 | 3955 | 0.9694 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| gsm8k | 2.2546 | 0.3760 | 0.8027 | 330.74 | 258.83 | +0.0243 | +0.0243 |


### `lsat`

Task-set sha-256: `be1fda68a61d453312b74d0b829885e2211383dc27956e871429c9362ef4c44b`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 1530 | 510 | 1430 | 0.9346 | 0.9346 | 580752 | 660532 | 1241284 | 868.03 | 0 | 39 | 59 | 0 | 1469 | 0.9721 |
| tahoe | 1530 | 510 | 1452 | 0.9490 | 0.9490 | 726340 | 320894 | 1047234 | 721.24 | 0 | 15 | 17 | 0 | 1513 | 0.9597 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| lsat | 1.2507 | 0.4858 | 0.8437 | 868.03 | 721.24 | +0.0144 | +0.0144 |


### `mmlu_acct`

Task-set sha-256: `5a218759fc66ea39795411dc89e74b6c8ea83286901a9b5303582d843c163d54`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 846 | 282 | 813 | 0.9610 | 0.9610 | 102370 | 201036 | 303406 | 373.19 | 0 | 0 | 6 | 0 | 840 | 0.9679 |
| tahoe | 846 | 282 | 815 | 0.9634 | 0.9634 | 178196 | 117076 | 295272 | 362.30 | 0 | 0 | 1 | 0 | 845 | 0.9645 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_acct | 1.7407 | 0.5824 | 0.9732 | 373.19 | 362.30 | +0.0024 | +0.0024 |


### `mmlu_logic`

Task-set sha-256: `a3256e35e1481a6a0f4c93159ee5fa2abb58710889673e1de225a8b2b60f0caa`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 378 | 126 | 361 | 0.9550 | 0.9550 | 48798 | 117899 | 166697 | 461.76 | 0 | 9 | 9 | 0 | 369 | 0.9783 |
| tahoe | 378 | 126 | 352 | 0.9312 | 0.9312 | 82440 | 99578 | 182018 | 517.10 | 0 | 13 | 13 | 0 | 365 | 0.9644 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_logic | 1.6894 | 0.8446 | 1.0919 | 461.76 | 517.10 | -0.0238 | -0.0238 |


### `mmlu_math`

Task-set sha-256: `6f72e4896a4d650b6079c71539ff157f826d6f78f966d054c7d37654cbed497c`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 300 | 100 | 283 | 0.9433 | 0.9433 | 31356 | 119706 | 151062 | 533.79 | 0 | 13 | 13 | 0 | 287 | 0.9861 |
| tahoe | 300 | 100 | 285 | 0.9500 | 0.9500 | 58056 | 95432 | 153488 | 538.55 | 0 | 9 | 9 | 0 | 291 | 0.9794 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| mmlu_math | 1.8515 | 0.7972 | 1.0161 | 533.79 | 538.55 | +0.0067 | +0.0067 |


### `race`

Task-set sha-256: `98bf131827e12e6724e1d21999035e08a7ce94e2ffc79b2cbb57d91a7c4edf33`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | grader err | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3135 | 1045 | 2950 | 0.9410 | 0.9410 | 1443296 | 592362 | 2035658 | 690.05 | 0 | 14 | 24 | 0 | 3111 | 0.9482 |
| tahoe | 3135 | 1045 | 2943 | 0.9388 | 0.9388 | 1724818 | 312051 | 2036869 | 692.11 | 0 | 6 | 9 | 0 | 3125 | 0.9418 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| race | 1.1951 | 0.5268 | 1.0006 | 690.05 | 692.11 | -0.0022 | -0.0022 |

## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff | mean token diff | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| arc/classic_vs_tahoe | 1172 | 3516 | 0.9784 | 0.9761 | +0.0023 | -26.1 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh/classic_vs_tahoe | 250 | 750 | 0.9947 | 0.9880 | +0.0067 | +94.1 | 0.0001 | 0.0010 | 1.0000 | 0.6608 | 0.0000 |
| bbh_arith/classic_vs_tahoe | 200 | 600 | 1.0000 | 0.9983 | +0.0017 | -68.9 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| bbh_track/classic_vs_tahoe | 250 | 750 | 0.9987 | 0.9947 | +0.0040 | +162.4 | 0.0001 | 0.0010 | 1.0000 | 1.0000 | 0.0000 |
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9447 | 0.9689 | -0.0243 | +61.6 | 0.0001 | 0.0010 | 0.0010 | 0.0000 | 0.0000 |
| lsat/classic_vs_tahoe | 510 | 1530 | 0.9346 | 0.9490 | -0.0144 | +126.8 | 0.0001 | 0.0010 | 0.2079 | 0.1664 | 0.0000 |
| mmlu_acct/classic_vs_tahoe | 282 | 846 | 0.9610 | 0.9634 | -0.0024 | +9.6 | 0.2088 | 0.6263 | 1.0000 | 1.0000 | 0.1620 |
| mmlu_logic/classic_vs_tahoe | 126 | 378 | 0.9550 | 0.9312 | +0.0238 | -40.5 | 0.0009 | 0.0036 | 0.4480 | 0.2913 | 0.0001 |
| mmlu_math/classic_vs_tahoe | 100 | 300 | 0.9433 | 0.9500 | -0.0067 | -8.1 | 0.7096 | 1.0000 | 1.0000 | 1.0000 | 0.1620 |
| race/classic_vs_tahoe | 1045 | 3135 | 0.9410 | 0.9388 | +0.0022 | -0.4 | 0.9372 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

Multiplicity: holm step-down correction over 10 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).

Notes: "—" marks undefined values (JSON null): zero successes for total spend/success, zero classic spend for ratios, no completed responses for completed accuracy. Micro and macro accuracy are distinct estimands and are never mixed; see Estimands above.
