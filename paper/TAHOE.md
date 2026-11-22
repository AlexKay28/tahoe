# TAHOE: Task-Aware Language Harness for Orchestrated Execution

> A structured reasoning language whose 93-token prompt form cuts output
> tokens ~49% on GLM-5.3-Flash and ~32% on gpt-oss-120b; quality deltas are
> current-grader derived results with per-benchmark inferential family only.

## Abstract

TAHOE is a structured reasoning language that teaches LLMs to think in typed
protocols — Compute, Select, Deduce — rather than free-form chain-of-thought.
We evaluate TAHOE as a thinking skill (system prompt) against classic inference
on 10 public-benchmark slices (GSM8K, ARC, BBH, MMLU subjects, LSAT, RACE —
exact slices in §3.3), 3 trials per sample, across two models: GLM-5.3-Flash
(31,524 trials) and gpt-oss-120b (31,824 trials). TAHOE reduces output tokens
to 0.511× on GLM-5.3-Flash and 0.682× on gpt-oss-120b (total-token ratios
0.931× and 1.011× — the prompt overhead offsets much of the output saving).
Accuracies are the **current-grader derived results** of the completed full
Stage-1 offline regrade (expectations reconstructed from archived grader
details, not independent gold): overall micro accuracy 95.96% → 96.45% on
GLM (+0.49pp) and 93.42% → 93.23% on gpt-oss (−0.19pp) — the overall deltas
are not themselves tested for significance or equivalence (the inferential
family is per benchmark, Holm-corrected); the significant per-benchmark
results are GSM8K favoring TAHOE on both models (+2.1pp GLM p=0.0010;
+1.4pp gpt-oss p=0.0060) and RACE favoring classic on gpt-oss (p=0.0162).
The measured manipulation
is the 93-token prompt as a whole; typed refs, protocols, and the runtime are
design artifacts whose individual mechanisms were not isolated by these
comparisons.

## 1. Introduction

LLM reasoning quality varies with problem structure. Free-form chain-of-thought
helps but produces verbose, unstructured output that wastes tokens. TAHOE
addresses this by providing a language for structured reasoning that the model
applies internally as a thinking skill.

Key insight: the system prompt (93 tokens) is a fixed infrastructure cost.
The model's actual reasoning (output tokens) is where TAHOE delivers value:
structured reasoning is more compact than free-form narrative (~49% fewer
output tokens on GLM, ~32% on gpt-oss; total spend −7% and +1% respectively).
Quality deltas under the archived stored grades are small and
grader-sensitive.

## 2. TAHOE Language

### 2.1 Typed Refs

TAHOE distinguishes knowledge states: G (goal), C (constraint), E (evidence),
H (hypothesis), U (unknown), O (option), K (criteria), D (decision), P (result),
V (verified), OUT (output). This prevents assumptions from silently becoming
facts and forces the model to commit to intermediate values.

### 2.2 Protocols

Three core protocols map task types to reasoning patterns:
- **Compute**: E.givens → steps with concrete numbers → verify → answer
- **Select**: options → eliminate wrong → pick → answer
- **Deduce**: constraints → assign positions explicitly (1..N) → verify all → answer

### 2.3 Need-Trigger

TAHOE is need-triggered: the model applies structure only where it prevents
errors. Simple tasks get direct answers; multi-step tasks get protocol
structure. Rule 15 defines when to use Fast, Standard, or Critical mode.

Full specification: `src/spec/` · Thinking rules: `textbook/`

## 3. Evaluation

### 3.1 Method

Two arms, same model per study (GLM-5.3-Flash and gpt-oss-120b), same API call:
- Classic: Q → answer (no system prompt)
- TAHOE: Q + skill → answer (93-token system prompt)

The manipulation is the presence of the 93-token prompt as a whole. No
typed-ref output contract is imposed, and archived tahoe-arm trials record
zero emitted typed refs — the typed refs, protocols, and runtime described
in §2 are the language's design, not something these comparisons isolate. A
preregistered factorial experiment separating the structure scaffold from
the answer-only output contract is prepared but has not been run
(`docs/PREREGISTRATION-structure-answer.md`).

Evaluation is frozen: identical graders, extraction, and parameters for both
arms. See `benchmarks/EVAL_PROTOCOL.md`.

### 3.2 Token Accounting

We separate:
- **Input tokens**: system prompt (fixed, ~93 tokens) + task text (same for both)
- **Output tokens**: model reasoning (variable — this is what we measure)

The system prompt is infrastructure. The reasoning tokens are the model's
actual work. TAHOE's value is reducing output tokens (total spend drops less
because of the prompt overhead); quality figures are current-grader derived
results (§3.4).

### 3.3 Results

10 benchmark slices, 3 trials per sample, two models. All tables below are
**generated blocks** from the canonical payloads of the completed full
Stage-1 derived regrade (current graders, GSM8K numeric-v6 extractor;
offline, raw archives untouched):
artifacts in `benchmarks/results/derived/2026-11-18-stage1-full-v3/`,
rendered by `benchmarks/render_canonical_docs.py`. Expectations are
reconstructed from archived grader details — current-grader derived
results, not independent gold validation. Slices: GSM8K test (1,319 —
full); ARC-Challenge test (1,172 — full); BBH
`logical_deduction_seven_objects` (250 — full); BBH
`tracking_shuffled_objects_seven_objects` (250 — full); BBH
`multistep_arithmetic_two` (200 in the GLM run; all 250 in the gpt-oss
run — the BBH-arith rows are not comparable across models); MMLU
`college_mathematics` (100), `formal_logic` (126), `professional_accounting`
(282) — each subject's full test split; AGIEval LSAT-LR (510 — full); RACE
high-school split, the **first question of each of 1,045 sampled articles**
(not the full RACE test set).

**GLM-5.3-Flash** (31,524 trials), derived overall: classic
15,125/15,762 = 95.96% vs tahoe 15,203/15,762 = 96.45% (+0.49pp micro
accuracy; not itself tested for significance — the inferential family is
per benchmark):

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

**gpt-oss-120b** (31,824 trials), derived overall: classic
14,865/15,912 = 93.42% vs tahoe 14,835/15,912 = 93.23% (−0.19pp micro
accuracy; not itself tested for significance):

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

The overall deltas are **not** called significant or null-tested: the
canonical paired inferential family is per benchmark (Holm step-down over
the 10 Stage-1 comparisons per model); there is no overall confirmatory
test and no prespecified equivalence margin. Derived significant
pass-rate permutation results: GSM8K — tahoe higher on both models
(GLM +2.1pp, p=0.0010; gpt-oss +1.4pp, p=0.0060); RACE — **classic**
higher on gpt-oss (+1.1pp, p=0.0162).

### 3.4 Key Findings

1. **Output-token savings across models**: ratio 0.511× on GLM-5.3-Flash
   (−49% of output tokens), 0.682× on gpt-oss-120b (−32%); total-token
   ratios 0.931× and 1.011× respectively; all-attempt total spend per
   success 465.88 → 431.50 (GLM) and 561.15 → 568.30 (gpt-oss)
2. **Quality (derived, current graders)**: overall +0.49pp on GLM-5.3-Flash
   (96.45% vs 95.96%), −0.19pp on gpt-oss-120b (93.23% vs 93.42%) — the
   overall deltas are **not** called significant or null-tested (per-
   benchmark Holm family only; no overall confirmatory test, no
   equivalence margin)
3. **HM metric retired**: the previously reported harmonic-mean values
   (1.247, 1.107, …) exceed 1 and cannot be reproduced from a bounded
   quality/efficiency definition; the metric is dropped until
   reproducibly defined
4. **GSM8K (derived)**: tahoe higher on both models — GLM 94.8% → 97.0%
   (+2.1pp, pass-permutation Holm p=0.0010), gpt-oss 93.7% → 95.0% (+1.4pp,
   p=0.0060). Derived results with expectations reconstructed from archived
   grader details — not independent gold validation
5. **RACE (derived)**: classic higher on gpt-oss (89.8% → 88.7%,
   p=0.0162) — the one significant benchmark-level regression
6. **Cross-model generality**: the 93-token prompt transfers — gpt-oss-120b
   was never tuned on TAHOE
7. **Grader sensitivity, resolved by the derived pipeline**: BBH graders
   initially under-credited classic-arm bare-letter answers; the GSM8K
   grader went through several versions, and the raw archives held
   multiple inconsistent grade sets (stored GSM8K 68.5%→80.3% in the main
   GLM archive; 83.0%→95.2% for a separate run). The completed full
   Stage-1 derived regrade (CLI `benchmarks/fix_stage1_extraction.py`,
   helper `benchmarks/stage1_regrade.py`; current-grader derived artifacts,
   immutable input, exclusive-create output, grader sha-256 pinned) plus
   `benchmarks/canonical_results.py` now provide the publication numbers;
   two malformed GSM8K tasks yield 12 `grader_error` trials per model
   (counted as failures), and archives carry no `finish_reason`, so zero
   canonical `truncated` counters mean absence-of-field, not zero
   truncation.

### 3.5 Why TAHOE Saves Tokens

Classic reasoning produces verbose narrative:
```
"Well, let me think about this. The question asks about Europa's surface
cracks. I know that Europa is an icy moon... [300 tokens of narrative]...
so the answer is tectonic movements, which is option B."
```

TAHOE reasoning produces compact structure:
```
G.goal: Which process causes Europa's surface cracks?
E.options: A) volcanic B) tectonic C) impacts D) flares
P.eliminate_A: No active volcanoes — eliminate
P.eliminate_C: Impact cracks would be radial — eliminate
P.eliminate_D: Solar flares don't affect ice — eliminate
D.choice: B
```

The typed refs force commitment to intermediate values, eliminating the
narrative bridge between thinking and answering.

## 4. Completeness: Counterfactual Reasoning

Counterfactual reasoning (Pearl's do-calculus) is a canonical test for whether
a reasoning language can express interventions without adding new primitives.
TAHOE handles this through protocol composition: the `do(X)` operator is the
act of feeding a hypothetical premise into `hypothesize` instead of the
factual one. The counterfactual protocol reduces to three existing commands:

```text
Q.counterfactual + H.causal_model + E.observed
  -> DO hypothesize(question = Q.counterfactual, evidence = [E.observed, H.causal_model]) -> H.counterfactual
  -> DO challenge(claim = H.counterfactual, evidence = E.observed) -> R.cf_result
  -> DO verify(goal = Q.counterfactual, evidence = [R.cf_result]) -> V.cf_verdict
```

No new syntax or grammar change is required. The typed-ref system (`H.*` vs
`E.*` vs `V.*`) enforces the distinction between counterfactual hypothesis,
factual evidence, and verified verdict — preventing the silent substitution
that Pearl's do-calculus was designed to expose. See
`textbook/09-counterfactual-reasoning.md` for the full protocol specification
and worked examples.

## 5. Related Work

- Chain-of-Thought (Wei et al., 2022) — unstructured reasoning
- Tree of Thoughts (Yao et al., 2023) — search-based reasoning
- CoALA (Sumers et al., 2023) — cognitive architecture for agents
- Pearl, Causality (2009) — do-calculus and counterfactual reasoning
- arxiv:2606.03883 — "Reasoning Efficiency Metrics for Structured LLM Output"
  Defines three metrics that measure reasoning quality beyond pass-rate:
  **RE** (Reasoning Efficiency) = verified_logical_steps / total_tokens,
  **RC** (Reasoning Concentration) = typed_refs_produced / output_tokens,
  **RR** (Redundancy Rate) = (repeated_refs + retired_refs) / total_refs_produced.
  TAHOE's typed-ref structure maps directly to these metrics: V.* refs are
  verified logical steps, all typed refs (G., C., E., H., D., V., …) count
  toward typed_refs_produced, and refs that are REVISEd or RETIREd count
  as repeated or retired.  For free-form CoT (classic) arms, these metrics
  are 0.0 (N/A) since no typed refs are produced.

TAHOE differs by providing a typed, protocol-based reasoning language that
the model applies as a thinking skill, reducing output-token consumption at
comparable overall quality (with family-wise significant GSM8K gains on
both models).

## 6. Limitations

- Two models evaluated (GLM-5.3-Flash, gpt-oss-120b); stronger/smaller models untested
- Exact benchmark slices, not all full test sets (RACE: first question of
  1,045 sampled articles; BBH-arith: 200 vs 250 tasks across the two runs);
  3 trials each (63,348 trials total across both models)
- Output-token savings smaller on gpt-oss-120b (0.682× vs 0.511×) —
  reasoning-heavy models may compress less; total spend on gpt-oss is ~1%
  *higher* with the skill
- Derived results use expectations reconstructed from archived grader
  details — not independently validated gold data; two malformed GSM8K
  tasks yield 12 `grader_error` trials per model (counted as failures);
  ARC's 22 numeric answerKeys per model use a positional fallback
- Archives carry no `finish_reason`: the zero canonical `truncated`
  counters are absence-of-field, not zero truncation (derived
  truncated-class counts: 3 GLM, 0 gpt-oss); fixed 2048-output-token cap
  effects exist in both arms (stage-1 cap-exhausted: 88/49 GLM, 32/9
  gpt-oss), so fixed-cap task success conflates completion with
  correctness
- The overall micro-accuracy deltas are not tested for significance or
  equivalence; the per-benchmark Holm family yields GSM8K favoring tahoe
  on both models and RACE favoring classic on gpt-oss (−1.1pp) — small
  significant effects, with LSAT (−2.3pp toward classic on gpt-oss)
  n.s.
- The measured effect is the prompt bundle: typed refs, protocols, and the
  runtime were not isolated (the preregistered structure × answer-only
  factorial has not been run)
- System prompt adds ~93 input tokens per call (fixed infrastructure cost)

## 7. Future Work

- Run the preregistered structure × answer-only factorial experiment
  (`docs/PREREGISTRATION-structure-answer.md`) to separate the reasoning
  scaffold from the output contract
- Independently validate the reconstructed expected answers against
  upstream gold data (the derived regrade reuses archived grader details)
- RL integration: use TAHOE trajectory scoring as reward signal
- Larger sample sizes and stronger models (GLM-5.2, GPT-4)
- Protocol learning: mine successful trajectories into new protocols
- Measure pass^k reliability, not just pass@1

## References

See `paper/research-related-systems.md` for the full related work survey.

## Data

All evaluation code, data, and results: `benchmarks/` directory. Current
publication evidence: `benchmarks/results/derived/2026-11-18-stage1-full-v3/`
(full Stage-1 derived regrade, both models, current graders incl. the
GSM8K numeric-v6 extractor; index:
`benchmarks/results/derived/README.md`; v2 is superseded by the
extractor-v6 clock-form correction, v1 by the v5 restatement fix — both
preserved unchanged). Pipeline: regrade CLI
`benchmarks/fix_stage1_extraction.py` (helper `stage1_regrade.py`) →
canonical statistics `benchmarks/canonical_results.py` → doc blocks
`benchmarks/render_canonical_docs.py` (`--update`/`--check`; the tables in
§3.3 are its generated blocks). Reasoning trajectory analysis:
`analysis/trajectory_score.py`.
