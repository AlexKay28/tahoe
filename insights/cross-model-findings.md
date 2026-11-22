# Cross-Model Findings: GLM-5.3-Flash vs gpt-oss-120b

> 63,348 archived trials, 10 benchmark slices (not all full test sets), 3
> trials/sample, 2 arms. Frozen eval protocol (max_tokens=2048). Dated
> 2026-09-14, corrected 2026-11-18. Commit 0645918.
>
> **Evidence status (2026-11-18).** Stage-1 accuracies below are the
> **current-grader derived results** of the completed full Stage-1 offline
> regrade (`benchmarks/results/derived/2026-11-18-stage1-full-v3/`, GSM8K
> rows by the current numeric-v6 extractor; regrade
> CLI `benchmarks/fix_stage1_extraction.py`, helper
> `benchmarks/stage1_regrade.py`; canonical statistics
> `benchmarks/canonical_results.py`; v2 — whose GSM8K rows used the v5
> extractor — and v1 — v4 — are the superseded earlier full regrades,
> preserved unchanged).
> The old stored-grade tables are
> retained as superseded history. Expectations are reconstructed from
> archived grader details — not independently validated gold. Ratios are
> exact token-sum ratios from the archived trial records. The measured
> manipulation is the 93-token prompt as a whole; typed refs/protocols/
> runtime were not isolated (archived tahoe-arm trials record zero emitted
> typed refs). Archives carry no `finish_reason`: zero canonical
> `truncated` counters are absence-of-field, not zero truncation.

## Headline (derived, current graders)

| Model | Trials/arm | Classic | TAHOE | Δ micro | Output ratio | Total ratio | Spend/success |
|---|---|---|---|---|---|---|---|
| GLM-5.3-Flash | 15,762 | 95.96% | **96.45%** | +0.49pp | 0.511x | 0.931x | 465.88 → 431.50 |
| gpt-oss-120b | 15,912 | 93.42% | 93.23% | −0.19pp | 0.682x | 1.011x | 561.15 → 568.30 |

**What transfers is the output compression**, not a validated quality win:
output tokens drop ~49% / ~32%, while **total** spend drops only ~7% on GLM
and *rises* ~1% on gpt-oss (the +93-token prompt × ~16k calls offsets most
of the output saving). The overall deltas (+0.49pp / −0.19pp) are **not
tested for significance or equivalence**: the canonical inferential family
is per benchmark (Holm over 10 comparisons per model); there is no overall
confirmatory test and no equivalence margin. The previously reported
harmonic-mean "frontier win" (HM 1.247 / 1.107 etc.) is retracted: those
values exceed 1 and cannot be reproduced from a bounded quality/efficiency
definition. The prompt transfers with zero per-model tuning — that claim
survives; the frontier-win claim does not.

<details>
<summary>Generated per-model canonical summary blocks</summary>

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

</details>

## Superseded per-benchmark tables (stored grades — historical only)

The stored-grade tables below are **superseded** by the derived regrade
above; retained for history. (gpt-oss full stored table:
`benchmarks/results/2026-09-13-stage1-full/CROSS_MODEL_EVAL.md` — same caveats.)

GLM (`benchmarks/results/2026-09-13-stage1-full/full_test_eval.json`):

| Benchmark | N | Classic (stored) | TAHOE (stored) | Output ratio |
|---|---|---|---|---|
| GSM8K | 1319 | 68.5% | **80.3%** | 0.38x |
| ARC | 1172 | **96.0%** | 95.7% | 0.48x |
| BBH | 250 | **99.5%** | 98.8% | 0.61x |
| BBH-track | 250 | **99.9%** | 99.5% | 0.52x |
| BBH-arith | 200 | **100%** | 99.8% | 0.83x |
| MMLU-math | 100 | 94.3% | 94.3% | 0.80x |
| MMLU-logic | 126 | **95.2%** | 93.1% | 0.84x |
| MMLU-acct | 282 | 96.1% | **96.3%** | 0.58x |
| LSAT | 510 | 93.4% | **94.9%** | 0.49x |
| RACE | 1045 | **94.1%** | 93.8% | 0.53x |

Under the derived regrade the GSM8K rows are 94.8% → 97.0% (GLM) and
93.7% → 95.0% (gpt-oss). Slices differ between models on BBH-arith (GLM
200-sample slice vs gpt-oss all 250) — those rows are not comparable. RACE
is the first question of each of 1,045 sampled high-school articles, not
the full test set.

## Key findings

1. **Math benefits most from structure — now derived, not just stored.**
   GSM8K derived deltas: +2.1pp (GLM, Holm p=0.0010) / +1.4pp (gpt-oss,
   p=0.0060), tahoe higher on both — the only family-wise significant
   per-benchmark wins, with ~60% output-token savings. Attributing them to
   the typed Compute protocol is a hypothesis — the prompt was the only
   manipulation.
2. **RACE is the one significant regression**: classic higher on gpt-oss
   (89.8% → 88.7% of task-mean pass, Holm p=0.0162). LSAT trends toward
   classic on gpt-oss (−2.3pp, p=0.203, n.s.) and toward tahoe on GLM
   (+1.4pp, p=0.208, n.s.).
3. **Reasoning-native models compress less.** gpt-oss-120b is a reasoning
   model — its free-form CoT is already lean, so the output ratio is 0.682x
   vs GLM's 0.511x. **Interpretation: internalized reasoning (RL-trained
   CoT) and external reasoning prompts partially substitute.** As models
   internalize more, single-shot protocol advantage shrinks — but
   long-horizon state management (Stage 2/3 territory) remains.
4. **Output-token savings are universal**: 12-62% across all 20
   model-benchmark pairs, never negative. Total-token ratios are not:
   1.011x overall on gpt-oss, and >1x on several short-task benchmarks
   (ARC 1.25x, BBH-arith 1.20x on gpt-oss) where the prompt overhead
   dominates.
5. **Grader sensitivity is resolved by the derived pipeline.** The stored
   GSM8K swing (>10pp between two stored grade sets) showed archived grades
   were grader-version artifacts; the current-grader regrade (all ten
   benchmarks, both models; GSM8K by the numeric-v6 extractor, superseding
   the v5-extractor v2 and v4-extractor v1 regrades) replaces them.
   Remaining caveat:
   expectations reconstructed from archived grader details, two malformed
   GSM8K tasks yield 12 `grader_error` trials per model, 6 per arm (counted
   as failures).
6. **The controlled follow-up exists but has not run.**
   `docs/PREREGISTRATION-structure-answer.md` factorially separates the
   structure scaffold from the answer-only contract under explicit
   256/4096-token budget regimes; it is preregistered, not executed.

## Practical infrastructure notes (gpt-oss-120b on Eliza)

- Endpoint: `https://api.eliza.yandex.net/raw/internal/gpt-oss-120b/v1` (NO /v2!)
- Reasoning model: thinking arrives in `reasoning`/`reasoning_content`, answer
  in `content`; rate-limited calls return EMPTY content with 0 tokens.
- Pool quota: **5 inflight per model family** — 60 parallel workers cause 429
  thrashing. Solution: sequential benchmark chain, 5 workers, retry with
  exponential backoff + empty-answer retry in worker_fn (run_single_bench.py).
- GLM endpoint: `.../raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1` (HAS /v2).
