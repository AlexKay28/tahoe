# Canonical results

Schema `canonical-results/1`. Deterministic: no wall-clock timestamps; statistics recomputed offline from immutable trial inputs — no model evaluations.

## Inputs

| input | sha-256 | trials | trials by arm | task-set sha-256 |
|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-gsm8k-derived.json` | `b0fff755493a006b062bcd9f05b2ed6758673649df3fdf504162625f1ea601b6` | 7914 | classic: 3957, tahoe: 3957 | `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd` |

Total trials: 7914.

### Available manifest metadata (recorded as available; never fabricated)

- **`benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/glm-gsm8k-derived.json`**
  - `manifest`: {"grader": {"name": "grade_gsm8k", "sha256": "5153620db7c0632d5c094315c4fe76e2592cae762f5b8371a8836b00ae3190b3", "source": "benchmarks/run_public_bench.py"}, "…

## Estimands

- **macro_accuracy** — Task-equal-weighted (macro) accuracy: the mean over tasks of each task's trial-mean pass rate; every task weighs the same regardless of how many trials it has.
- **micro_accuracy** — Trial-pooled (micro) accuracy within a benchmark/arm: successes / trials. Tasks with more repeated trials weigh proportionally more.
- **outcomes** — Truncation / cap-exhausted / empty / completed counts derived only from fields actually present on each trial (explicit flags, finish_reason, recorded output caps, final_answer); finish_reason is never fabricated for archives that do not record it.
- **paired_comparisons** — Keyed task-cluster paired comparisons on exact (benchmark, task_id, trial) identity; repeated matched trials are averaged within tasks; Holm step-down correction over the comparison family.
- **token_ratio_tahoe_over_classic** — tahoe token spend / classic token spend for the same scope; null when the classic spend is zero.
- **token_sums** — Exact sums of recorded input/output/total token counts over all trials in scope.
- **total_spend_per_success** — sum(total_tokens over ALL attempts, failures included) / number of successes; null (undefined) when there are zero successes.

## Overall

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3957 | 1319 | 3738 | 0.9447 | 0.9447 | 280788 | 955515 | 1236303 | 330.74 | 0 | 0 | 8 | 3949 | 0.9466 |
| tahoe | 3957 | 1319 | 3834 | 0.9689 | 0.9689 | 633051 | 359308 | 992359 | 258.83 | 0 | 0 | 2 | 3955 | 0.9694 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 2.2546 | 0.3760 | 0.8027 | 330.74 | 258.83 | +0.0243 | +0.0243 |

## Benchmarks

### `gsm8k`

Task-set sha-256: `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3957 | 1319 | 3738 | 0.9447 | 0.9447 | 280788 | 955515 | 1236303 | 330.74 | 0 | 0 | 8 | 3949 | 0.9466 |
| tahoe | 3957 | 1319 | 3834 | 0.9689 | 0.9689 | 633051 | 359308 | 992359 | 258.83 | 0 | 0 | 2 | 3955 | 0.9694 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| gsm8k | 2.2546 | 0.3760 | 0.8027 | 330.74 | 258.83 | +0.0243 | +0.0243 |

## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff | mean token diff | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9447 | 0.9689 | -0.0243 | +61.6 | 0.0001 | 0.0001 | 0.0001 | 0.0000 | 0.0000 |

Multiplicity: holm step-down correction over 1 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).

Notes: "—" marks undefined values (JSON null): zero successes for total spend/success, zero classic spend for ratios, no completed responses for completed accuracy. Micro and macro accuracy are distinct estimands and are never mixed; see Estimands above.
