# The Three-Stage Arc: Teaching Models a Specialized Reasoning Language

> **Evidence correction (2026-11-18):** Stage 1 measured the TAHOE-93 prompt
> bundle, including its answer-only contract—not typed-ref/runtime execution.
> Output-token ratios were 0.511× (GLM) and 0.682× (gpt-oss), but total-token
> ratios were 0.931× and 1.011×. The current-grader derived regrade
> (`benchmarks/results/derived/2026-11-18-stage1-full-v3/`) supersedes the
> stored grades: overall +0.49pp / −0.19pp (not themselves tested; no
> equivalence margin supports a parity claim), with GSM8K significantly
> favoring tahoe on both models and RACE favoring classic on gpt-oss. Stage 1
> demonstrates portable output compression, not a proof of the language
> mechanism or a frontier win. See `docs/EVALUATION.md`; the
> structure-isolating factorial is prepared but has not been run.

> The thesis of the next paper: "How to teach a model to reason in a
> specialized language for token consumption reduction."
> Dated 2026-09-14.

## The arc

```
Stage 1: TEACH BY PROMPT       (DONE — 63,348 trials, 2 models)
  93-token system prompt teaches the language (typed refs, protocols)
  Evidence: −49% tokens (GLM-5.3-Flash), −32% (gpt-oss-120b);
  quality +1.9% / −0.2% (stored grades, superseded by the 2026-11-18
  derived regrade: +0.49pp / −0.19pp overall, not themselves tested;
  per-benchmark Holm: GSM8K tahoe-higher on both models, RACE
  classic-higher on gpt-oss); the "HM wins" claim is retracted
  Deliverable: benchmarks/results/2026-09-13-stage1-full/CROSS_MODEL_EVAL.md (stored) and
  benchmarks/results/derived/2026-11-18-stage1-full-v3/ (derived evidence)

Stage 2: PRACTICE BY EXECUTION (TAHOE-VM — in progress)
  Model compiles task → program.think, then EXECUTES it on itself:
  one atomic self-subcall per step, harness holds refs + validation,
  context grows O(refs) not O(history)
  Question: does OPERATING in the language beat IMITATING it?
  Deliverable: src/tahoe/vm_mode/ + 3-bench pilot with token gates

Stage 3: INTERNALIZE BY RL     (planned)
  GRPO over VM trajectories; reward = outcome grader + DONE-predicate
  process terms − λ·tokens
  The model learns the protocols AND when to use them (need-trigger as
  trained policy, not prompt text)
  Question: can the language become weights instead of text?
  Deliverable: prompted-VM vs RL-VM comparison
```

## Why each stage matters

- **Stage 1 is the transferability proof**: the same 93-token skill worked on two
  architecturally different models with zero per-model tuning. The language is
  a portable artifact, not a prompt hack.
- **Stage 2 is the execution proof**: refs are O(10) tokens vs O(100) CoT
  narration; subcall context is a state slice; pure-computation steps cost zero
  model tokens (deterministic executor). The harness adds fixed per-call
  overhead — see token-economics.md for why the language saves more than the
  harness spends.
- **Stage 3 is the internalization proof**: the deep-search finding is that
  reasoning length is directly RL-controllable (L1/LCPO). Need-trigger routing
  (when to enter VM mode) becomes a learned policy. The endpoint: the language
  stops being external text and becomes behavior.

## The unique asset across all three stages

**Machine-checkable process signals.** OpenAI's Let's Verify Step by Step used
human labels (PRM800K) for step-level supervision. TAHOE's DONE predicates,
parse validation, and typecheck provide computational signals without those
labels, but predicate/type conformance is not equivalent to human semantic
verification of reasoning. Their value as RL rewards remains an empirical
question; no RL result is claimed here.

## Positioning line

OpenAI internalizes reasoning (o-series: protocol into weights, not
inspectable). Anthropic externalizes orchestration (code-exec, context
engineering: program around the model). TAHOE externalizes *reasoning itself*
as a typed language the model learns, executes on itself, and finally
internalizes — with verifiable rewards at every stage.
