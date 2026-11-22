# Preregistration — TAHOE structure × answer-only factorial experiment

- **Experiment ID:** `structure-answer`
- **Status:** PREREGISTERED — prepared and frozen before any trial was run.
  This experiment has NOT been executed. The runner refuses to overwrite
  results; any run produces a new immutable, timestamped directory.
- **Date of preregistration:** 2026-11-18
- **Configuration:** `benchmarks/structure-answer.yaml`
  (sha256 `afd7639c6e171c36519d84839a139e9972995589e84244b8db80aaf436c34394`;
  also pinned in every run manifest)
- **Runner:** `benchmarks/run_structure_ablation.py` (isolated; composes the
  unmodified grader/extractor from `run_public_bench` and the truthful-outcome
  capture from `runner_classic`; touches no existing runner, prompt, or
  archived result)
- **Task loader:** `benchmarks/structure_answer_tasks.py` (isolated; honors
  the configured per-benchmark sample counts; `run_public_bench.py`
  untouched)
- **Power analysis:** `benchmarks/structure_answer_power.py` →
  `benchmarks/structure-answer-power.json` (transparent pre-run
  precision/power justification; hash-pinned in every run manifest)

## 1. Research question and hypotheses

Prior ablations (#89, #55) show TAHOE-93 improving both accuracy and token
efficiency over a classic baseline, but TAHOE-93 bundles two manipulations:
a *structure* component (the typed-ref reasoning scaffold) and an
*answer-only output contract* (its final sentence). This experiment
factorially separates them.

- **H1 (contract effect):** Under a constrained output budget, the
  answer-only contract alone (`answer_only`) raises fixed-budget task
  success over `classic` by reducing token waste, because arms without the
  contract spend budget on prose and hit truncation.
- **H2 (structure effect, pooled reasoning cluster):** Holding the contract
  fixed, TAHOE structure (`tahoe_full`) improves adequate-budget accuracy
  over the contract alone (`answer_only`) on the **pooled multi-step
  reasoning cluster** — bbh + bbh_track + bbh_arith (bbh_arith is the
  arithmetic proxy; AIME is excluded from the primary task set and is not
  part of H2). The confirmatory H2 test is the cluster-scoped comparison
  `[tahoe_full, answer_only, [bbh, bbh_track, bbh_arith]]`; the same pair
  over ALL benchmarks is reported as a labeled **exploratory** global
  counterpart with no confirmatory standing.
- **H3 (generic-structure parity):** A TAHOE-free generic structure
  (`generic_structure`) with the same contract captures most of the effect
  of `tahoe_full`; i.e., the scaffold's *shape*, not its TAHOE vocabulary,
  does the work.
- **H4 (non-inferiority):** Each flatter arm (`answer_only`,
  `generic_structure`, `tahoe_structure`, `cod`) is non-inferior to
  `tahoe_full` on adequate-budget accuracy within an explicit margin of
  **0.05 absolute success-rate points**.

## 2. Arms (exact prompt relationships)

All arm differences are confined to the **system prompt**. The host task
prompt (`task["description"]`) and output/grader contract are **preserved
verbatim**; the only intentional manipulation of the output contract is the
answer-only sentence itself, delivered through the system prompt.

| arm | system prompt | sha256 |
|---|---|---|
| `classic` | none (empty) | — |
| `answer_only` | the canonical TAHOE-93 final output-contract sentence alone; byte-equal to `benchmarks/prompts/structure-answer/answer-only.txt` | `fb35e29b5255ea5d4c4395f01dd7c19a3a0aef49a62a6669e9727466cc3d88f5` |
| `generic_structure` | `benchmarks/prompts/structure-answer/generic-structure.txt` — TAHOE-free structured outline ending with the same contract sentence | `0ff68e6cc4d776fcf7bade88258cf181683009825d9e085d6b4423477be98e63` |
| `tahoe_structure` | canonical TAHOE-93 **minus only its final output-contract sentence**; derived in code with the exact recomposition guard `derived + "\n\n" + sentence == canonical` | derived at run time; guard in runner + tests |
| `tahoe_full` | canonical `language/skills/tahoe-93.txt`, byte-exact, unmodified | `3054b236325858e33945017282a1ad73dbede1276171983b0aaad308b20900db` |
| `cod` | `language/baselines/cod.txt`, byte-exact (concise-CoT / Chain-of-Draft control) | `1d29f89d52d966e3a22ad0b18bcc902dc3cd74e0c28dfb008c5b7d3dee4924da` |

Required relationships (enforced by `load_arm_prompts()` and by tests):

1. `tahoe_full` equals the canonical TAHOE-93 file byte-for-byte.
2. `tahoe_structure` + `"\n\n"` + `answer_only` recomposes the canonical text
   exactly; `tahoe_structure` contains no part of the contract sentence.
3. `answer_only` equals both the canonical final sentence and the
   `answer-only.txt` artifact.
4. `generic_structure` ends with the same contract sentence and contains no
   TAHOE vocabulary.
5. `cod` equals the existing baseline file byte-for-byte.

## 3. Regimes and generation settings

Two **explicitly configured output-budget regimes** (the only regime-level
difference is `max_tokens`):

- `constrained`: `max_tokens = 256` — tight budget: truncation pressure is
  the treatment.
- `adequate`: `max_tokens = 4096` — a **larger** budget, expected to make
  truncation *rare* but **not a guarantee** that answers are never
  truncated. Residual truncation under the adequate regime is **measured**
  per arm (count and rate of `finish_reason = "length"` trials, plus
  empty-response counts) and reported as a **mandatory outcome** in
  `endpoints`, `RUN.md`, and the endpoint table. Adequate-regime accuracy
  claims are interpreted together with the measured truncation rate and are
  never presented as truncation-free.

Generation settings, identical for **every arm in every regime**:
`max_turns = 1`, `timeout_seconds = 90`, `temperature = 0.0`, `top_p = 1.0`.
No per-arm generation overrides exist or are permitted. Grading is identical
across all cells (composed unmodified from `run_public_bench.grade_task`;
never branched on arm or regime).

## 4. Task set and pre-run power justification

### 4.1 Task set

The same ten HF benchmarks as the archived ablations — `gsm8k`, `arc`,
`bbh`, `bbh_track`, `bbh_arith`, `mmlu_math`, `mmlu_logic`, `mmlu_acct`,
`lsat`, `race` — loaded by the **isolated loader**
`benchmarks/structure_answer_tasks.py`, which honors the configured
`samples_per_benchmark` (**70 per benchmark**; `run_public_bench.py` is
untouched — its hardcoded 10-sample default was the underpowered design this
section replaces). Sampling is deterministic and **nested**: per benchmark,
indices come from `random.Random(f"{seed}|{benchmark}")` (seed = 42), the
shuffle is independent of k, so any smaller-k set is a subset of the k=70
set. Draws are capped at `min(k, dataset_size)`; all ten test splits have
≥ 100 items, so the cap never binds at k = 70. **700 tasks × 6 arms × 2
regimes × 3 trials = 25,200 planned trials.**

Note: the k=10 archived subsets used a different sampling procedure
(`rng.sample`) and are not reproduced by the nested scheme; the archived
data is used only for variance estimation, never as the task set.

File-backed benchmarks (lcb, gpqa, aime, mmlu_pro) are excluded from the
primary set; any run including them is labeled exploratory. A
`BENCHES`-filtered run is a smoke run, is marked `smoke_run: true` in its
manifest, and is never the primary analysis. Trial order is shuffled with
seed 42; every (task, arm, regime, trial) cell appears exactly once.

### 4.2 Pre-run precision and power justification

Full transparent calculation: `benchmarks/structure_answer_power.py` →
generated artifact `benchmarks/structure-answer-power.json` (hash-pinned in
every run manifest). Empirical input (read-only): archived trials
`benchmarks/results/2026-09-14-skill-study/prompt_ablation.json`
(1,500 trials; 5 arms × 10 benchmarks × 10 tasks × 3 trials).

**Multiplicity convention.** Confirmatory power is planned at the
**Bonferroni / Holm-first-step per-comparison alpha** of the actual
families: m = 4 non-inferiority candidates per regime (one-sided
α = 0.0125) and m = 6 comparisons per (regime, endpoint) family — five
global plus the scoped H2 cluster comparison; the exploratory global
counterpart belongs to no family (two-sided
α ≈ 0.00417). This is the family-wise worst case — conservative for every
step of the actual Holm procedure.

**SD scenarios for the per-task paired success difference** (T = 3 trials
per task):

| scenario | sd_d | status |
|---|---|---|
| preregistered planning SD | 0.25 | rounded up ~34% from archived pooled max |
| archived pooled empirical max | 0.187 | 93-vs-classic & related archived pairs, 100 tasks |
| archived per-benchmark empirical max | 0.351 | worst single-benchmark pair SD |
| independent-arm sensitivity | 0.408 = √(1/(2T)) | assumes zero pairing benefit; **not** an upper bound |
| **valid distribution-free paired bound** | **0.577 = √(1/T)** | perfectly anti-correlated arm outcomes |

The paired bound correction: √(1/(2T)) bounds the *independent*-arm case
only; with maximally opposed arm outcomes the per-task paired difference
has variance up to 1/T, so the valid distribution-free bound is **√(1/T)**.

**Non-inferiority (margin 0.05, one-sided, Holm-first-step α, n = 700):**

| scenario | required n | power | 95% CI half-width |
|---|---|---|---|
| planning SD 0.25 | 238 | 0.999 | 0.019 |
| empirical pooled max 0.187 | 133 | ~1.000 | 0.014 |
| per-benchmark max 0.351 | 470 | 0.936 | 0.026 |
| independent-arm 0.408 | 634 | **0.841** | 0.030 |
| paired worst case 0.577 | 1,268 | 0.520 | 0.043 |

**H2 pooled bbh-family cluster** (bbh + bbh_track + bbh_arith = 210 tasks,
two-sided δ = 0.10, m = 6): required n = 76 at the planning SD (power
0.999); power 0.819 at the independent-arm bound; 0.449 at the paired
worst case.

**Confirmatory scope and explicit downgrades.** The design is confirmatory
(≥ 80% power) for non-inferiority and for the pooled H2 cluster for every
sd_d up to and including the independent-arm sensitivity bound, and its
descriptive precision (95% CI half-width < 0.05) holds even at the paired
worst case. **Downgraded, stated openly:** if arm outcomes were perfectly
anti-correlated per task (sd_d = √(1/3) = 0.577 — an adversarial extreme
contradicted by all archived data and by the structural similarity of the
arms compared), non-inferiority power would be ~0.52 and H2 cluster power
~0.45; under that scenario H4 and H2 results are interpreted as
**underpowered/precision-limited, not confirmatory**, regardless of outcome.
No confirmatory claim in this experiment rests on unadjusted (m = 1) power;
numbers at m = 1, where reported by the module, are labeled
non-confirmatory.

## 5. Endpoints (predeclared)

**Primary endpoints:**

1. **Fixed-budget task success:** per-arm success in the `constrained`
   regime. A trial passes only if the graded final answer is correct;
   runner-level failures (timeout, api_error, empty_response, max_turns)
   count as failures and are additionally reported by class.
2. **Adequate-budget accuracy:** per-arm success in the `adequate` regime.

**Accuracy estimand (endpoints 1–2):** the **task-macro** rate is the
primary estimand — each task's repeated trials are first aggregated to a
per-task mean success, and tasks are weighted **equally**
(`success_rate_macro`), exactly matching the confirmatory paired tests.
The trial-pooled **micro** rate (`success_rate_micro`) is reported as
**descriptive only** and carries no confirmatory standing. Both are
reported side by side in `endpoints`, `analysis.json`, and `RUN.md`.
3. **Tokens and cost per success, including failures:** per arm × regime,
   `sum(total_tokens over all trials) / n_passed` and
   `sum(cost_usd over all trials) / n_passed`, where the numerator includes
   every failed trial's spend. Reported as `null` (never a fabricated
   number) when an arm passes nothing. Cost uses the configured rates
   ($0.60 / 1M input, $2.00 / 1M output tokens).
4. **Residual truncation measurement (mandatory reported outcome):** per
   arm × regime, the count and rate of `finish_reason = "length"` trials
   (`truncated_count`, `truncation_rate`) and the empty-response count.
   The adequate regime is a larger budget, **not** a truncation-free
   guarantee; adequate-regime accuracy claims are always interpreted
   together with these measured rates.

**Confirmatory comparison family** (two-sided, within each regime):

| comparison | scope | tests |
|---|---|---|
| `answer_only` vs `classic` | all | H1 — contract alone |
| `tahoe_structure` vs `classic` | all | structure alone |
| `generic_structure` vs `answer_only` | all | H3 — generic structure with contract fixed |
| `tahoe_full` vs `answer_only` | **pooled bbh + bbh_track + bbh_arith cluster** | H2 — TAHOE structure on top of the contract (cluster-scoped) |
| `tahoe_full` vs `tahoe_structure` | all | contract on top of TAHOE structure |
| `cod` vs `classic` | all | concise-CoT control |

**Exploratory comparison (labeled, never confirmatory):**
`tahoe_full` vs `answer_only` over **all** benchmarks — the global
counterpart of the H2 cluster test. Reported with unadjusted p-values, in
no Holm family, and excluded from all decision rules.

**Non-inferiority family:** `answer_only`, `generic_structure`,
`tahoe_structure`, `cod` each vs `tahoe_full`, one-sided, margin **0.05**
absolute success-rate points, alpha 0.05.

## 6. Analysis plan

- **Keyed task-cluster pairing:** trials pair by exact
  `(benchmark, task_id, trial)` identity via `stats.pair_trials`; input
  order is never used to pair, ambiguous duplicates raise errors.
- **Repeated-trial aggregation:** repeated matched trials are averaged to
  per-task means before any paired test or CI (tasks are the independent
  units); this per-task aggregation IS the task-macro estimand of
  endpoints 1–2.
- **Tests:** two-sided paired permutation tests (10,000 permutations,
  per-family derived seeds) on per-task mean `passed` (endpoint `success`)
  and per-task mean `total_tokens` (endpoint `total_tokens`); task-cluster
  bootstrap CIs (10,000 resamples) for mean token differences. The H2
  comparison is restricted to the pooled reasoning cluster (bbh, bbh_track,
  bbh_arith) before pairing; its exploratory global counterpart runs over
  all benchmarks with no Holm membership.
- **Holm family correction:** `stats.holm_adjust_pvalues` within each of six
  preregistered families: (regime × {success, total_tokens}) for the six
  confirmatory comparisons — five global plus the scoped H2 cluster
  comparison (m = 6 per family, matching the power calculation) — and
  (regime × noninferiority) for the four non-inferiority tests.
- **Decision rules:** H1/H2/H3 confirmed iff Holm-adjusted two-sided
  p < 0.05 in the predicted direction on the corresponding `success`
  endpoint — H2 specifically on its pooled-cluster comparison, never on
  the exploratory global counterpart. H4 holds for a candidate iff its
  Holm-adjusted one-sided non-inferiority p < 0.05 in the `adequate`
  regime.
- **Truthful outcome metadata:** every trial record preserves
  `finish_reason`, `empty_response`, `retries`, and both graded and
  runner-level failure classes; truncated or empty responses are never
  relabeled as graded wrong answers. Runner-level failures count as task
  failures in success endpoints and are reported separately per class.

## 7. Output immutability and provenance

- Every run writes to a fresh, timestamped directory
  `benchmarks/results/runs/<UTC-stamp>_structure-answer[_<RUN_TAG>]/`,
  created with `mkdir(exist_ok=False)` — a collision **refuses to overwrite**
  and fails loudly. Each output file is created in exclusive `x` mode.
- A `manifest.json` pins sha256 hashes of: the config, this document, the
  runner, the grader/extractor module (`run_public_bench.py`),
  `runner_classic.py`, `stats.py`, the isolated task loader
  (`structure_answer_tasks.py`), the power module
  (`structure_answer_power.py`) and its generated justification artifact
  (`structure-answer-power.json`), every prompt artifact (per arm, with
  source description), local dataset files, the model name, the complete
  generation and regime settings, the seeds, the per-benchmark sample plan
  (requested and actually drawn counts), and a fingerprint of the exact
  evaluated task set.
- Archived results are never edited; no run may overwrite an earlier run.

## 8. Stopping, exclusion, and deviation rules

- Run to completion: all 25,200 planned trials or none; no interim looks, no
  early stopping for benefit or futility.
- No data-driven exclusions. Trials are only excluded if they never ran
  (plan not executed); every executed trial stays in the analysis.
- A benchmark-wide API outage (all arms affected for a whole benchmark)
  invalidates that benchmark's comparison and must be reported as a
  deviation; it does not license re-running until significance.
- Any analysis not listed above (per-benchmark splits, other endpoints,
  post-hoc arm pairs) is **exploratory** and must be labeled as such.
- Any change to prompts, budgets, arms, graders, or this document after a
  run starts is a protocol deviation and must be documented in the run's
  `RUN.md`.
- If dataset caps reduce any benchmark below its configured sample count
  (drawn < planned), the run reports the shortfall loudly, records actual
  per-benchmark counts in the manifest, and the affected confirmatory
  claims are interpreted at the reduced effective power — never silently
  at the planned power.
