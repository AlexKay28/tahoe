# Canonical results

Schema `canonical-results/1`. Deterministic: no wall-clock timestamps; statistics recomputed offline from immutable trial inputs — no model evaluations.

## Inputs

| input | sha-256 | trials | trials by arm | task-set sha-256 |
|---|---|---|---|---|
| `benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-gsm8k-derived.json` | `b18b2819b2909cb5f955f6b008421861ef8c735d5239505345e7e74441b1ed64` | 7914 | classic: 3957, tahoe: 3957 | `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd` |

Total trials: 7914.

### Available manifest metadata (recorded as available; never fabricated)

- **`benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/oss-gsm8k-derived.json`**
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
| classic | 3957 | 1319 | 3685 | 0.9313 | 0.9313 | 504360 | 1261097 | 1765457 | 479.09 | 0 | 0 | 6 | 3951 | 0.9327 |
| tahoe | 3957 | 1319 | 3746 | 0.9467 | 0.9467 | 864447 | 509083 | 1373530 | 366.67 | 0 | 0 | 1 | 3956 | 0.9469 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| overall (all benchmarks pooled) | 1.7139 | 0.4037 | 0.7780 | 479.09 | 366.67 | +0.0154 | +0.0154 |

## Benchmarks

### `gsm8k`

Task-set sha-256: `ca2a3f8cb793961b93fd76620ffe8ef1ee2c2ee2216d07f9a180c9d6d152accd`.

| arm | trials | tasks | successes | micro acc (trial-pooled) | macro acc (task-eq-wt) | input tok | output tok | total tok | total spend/success | truncated | cap-exhausted | empty | completed | completed acc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| classic | 3957 | 1319 | 3685 | 0.9313 | 0.9313 | 504360 | 1261097 | 1765457 | 479.09 | 0 | 0 | 6 | 3951 | 0.9327 |
| tahoe | 3957 | 1319 | 3746 | 0.9467 | 0.9467 | 864447 | 509083 | 1373530 | 366.67 | 0 | 0 | 1 | 3956 | 0.9469 |

| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) | total tok ratio (tahoe/classic) | total spend/success classic | total spend/success tahoe | micro acc Δ (tahoe−classic) | macro acc Δ (tahoe−classic) |
|---|---|---|---|---|---|---|---|
| gsm8k | 1.7139 | 0.4037 | 0.7780 | 479.09 | 366.67 | +0.0154 | +0.0154 |

## Paired task-cluster comparisons (Holm-corrected)

| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) | pass diff | mean token diff | perm p | perm p (Holm) | pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gsm8k/classic_vs_tahoe | 1319 | 3957 | 0.9313 | 0.9467 | -0.0154 | +99.0 | 0.0001 | 0.0001 | 0.0003 | 0.0002 | 0.0000 |

Multiplicity: holm step-down correction over 1 comparisons (family: comparisons); pairing key: (benchmark, task_id, trial).

Notes: "—" marks undefined values (JSON null): zero successes for total spend/success, zero classic spend for ratios, no completed responses for completed accuracy. Micro and macro accuracy are distinct estimands and are never mixed; see Estimands above.
