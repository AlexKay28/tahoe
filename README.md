# TAHOE — a structured reasoning language for LLMs

*Logic-level pseudocode for how a model should think.*

TAHOE is a compact reasoning language: typed epistemic references
(`G` goal, `E` evidence, `H` hypothesis, `V` verified, `OUT` answer), named
protocols (`Compute`, `Select`, `Deduce`), and economy rules. Delivered to an
LLM as a 93-token thinking skill (system prompt), it disciplines the model's
reasoning. **The skill's final rule explicitly constrains output** ("Output
only the answer") — so the archived comparisons measure structure scaffold
and answer-only output contract as one bundle, and the two are confounded
until the preregistered factorial experiment runs.

```
classic:  Q → {wandering narrative} → answer        (247 output tokens avg)
tahoe:    Q + skill → {bounded derivation} → answer            (126 avg)
```

## Headline results (63,348 archived trials, two models, 10 benchmark slices)

Current-grader **derived** results — the completed full Stage-1 offline
regrade of both raw archives with the current graders
(`benchmarks/results/derived/2026-11-18-stage1-full-v3/`, index:
`benchmarks/results/derived/README.md`). Generated from the canonical
payloads by `benchmarks/render_canonical_docs.py`; the JSON payloads are the
source of truth.

GLM-5.3-Flash (31,524 trials):

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

gpt-oss-120b (31,824 trials):

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

What is measured is the 93-token prompt as a whole (structure scaffold and
answer-only output contract confounded): it cuts output tokens ~49% on GLM
and ~32% on gpt-oss, while total spend drops only ~7% on GLM and rises ~1%
on gpt-oss (prompt overhead); all-attempt total spend per success drops on
GLM (465.88 → 431.50) and rises on gpt-oss (561.15 → 568.30). The overall
micro-accuracy deltas (+0.49pp GLM, −0.19pp gpt-oss) are **not** called
significant or null-tested: the canonical paired inferential family is per
benchmark (Holm over the 10 Stage-1 comparisons per model); there is no
overall confirmatory test and no prespecified equivalence margin. Derived
significant per-benchmark results (pass-rate permutation, Holm): GSM8K —
TAHOE higher on both models (GLM +2.1pp, p=0.0010; gpt-oss +1.4pp,
p=0.0060); RACE — **classic** higher on gpt-oss (+1.1pp, p=0.0162).
Caveats: expectations are reconstructed from archived grader details (not
independent gold); two malformed GSM8K tasks yield 12 `grader_error` trials
per model, 6 per arm (counted as failures); no `finish_reason` was
recorded, so the zero canonical `truncated` counters are
absence-of-field, not evidence of zero truncation. Small skill-size
ablations (33–162 words) detected no large quality difference, but had no
prespecified equivalence margin.

Recompute every figure offline — no model evaluations. The completed
derived pipeline: regrade with `benchmarks/fix_stage1_extraction.py`
(required `--input <raw archive> --output <fresh derived artifact>`;
helper `benchmarks/stage1_regrade.py`), canonical statistics with
`benchmarks/canonical_results.py`, doc blocks rendered/verified with
`benchmarks/render_canonical_docs.py` (index and SHA-256 pins:
`benchmarks/results/derived/README.md`). The structure × answer-only
factorial experiment is preregistered but **has not been run**:
`docs/PREREGISTRATION-structure-answer.md`. Full data: `docs/EVALUATION.md`;
paper source: `paper/tahoe.tex` (the committed PDF predates the 2026-11
truth-in-evidence corrections).

## The design principle (hypothesis, not established law)

> **A reasoning language should shape thought, not require visible notation.**

Visible notation taxes every token; internalized notation taxes nothing.
This is the design **motivation** behind TAHOE-93, supported by
observations (explicit notation collapsed LSAT to 23%; a protocol-execution
VM lost 40+ points at 2–35× tokens; the skill's median visible output is the
answer alone) — but the archived prompt comparisons do not establish it as a
law: TAHOE-93 itself constrains output ("Output only the answer"), so the
answer-only contract is confounded with the structure scaffold in every
archived arm comparison. Separating them is exactly what the preregistered
factorial (`docs/PREREGISTRATION-structure-answer.md`, prepared not run) is
for. Details: `insights/compact-language.md`, `docs/TAHOE_VM.md`.

## Repository structure

```
language/          THE LANGUAGE AS ARTIFACT
├── README.md              what the language is, skill catalog, design principle
├── skills/
│   ├── tahoe-93.txt       canonical thinking skill (93 tokens)
│   ├── triz-implicit.txt  variant: ideal-first search bounding
│   └── variants/          size ablations + the explicit-notation negative artifact
└── baselines/             cot / cod / tot / react prompts

src/               THE LANGUAGE RUNTIME
├── tahoe/                 grammar, parser, type-checker, coordinator, events
│   └── vm_mode/           SHELVED: step-by-step execution protocol (STATUS.md)
└── spec/                  formal language specification

benchmarks/        EVALUATION INFRA
├── README.md              runner catalog, offline derived-results tooling, grading rules
├── run_skill_compare.py   canonical arm-comparison runner
├── run_single_bench.py    one benchmark, parallel, full-test-set support
├── run_parallel_bench.py  all benchmarks + bootstrap CIs
├── fix_stage1_extraction.py  full Stage-1 regrade CLI (--input/--output → derived artifact)
├── stage1_regrade.py      Stage-1 regrade pipeline helper module
├── fix_gsm8k_extraction.py   GSM8K-only regrade CLI (--input/--output → derived artifact)
├── gsm8k_regrade.py       GSM8K regrade pipeline helper module
├── canonical_results.py   canonical offline stats generator (deterministic, refuses overwrite)
├── render_canonical_docs.py  renders/verifies generated doc blocks from canonical payloads
├── results/               frozen study archives + derived/ (dated dirs — never overwrite)
└── EVAL_PROTOCOL.md       frozen invariants

textbook/          thinking recipes — the language, rules, protocols (human-facing)
analysis/          trajectory scoring, protocol discovery
programs/          experiment plans as TAHOE programs (.think) + RUN.md repro guides
paper/             tahoe.pdf + LaTeX source + figures
docs/              EVALUATION.md (results record), TAHOE_VM.md (shelved branch)
insights/          research journal — findings, corrections, landscape surveys
tests/             test suite (pytest)
examples/ demo/ protocols/ archive/
```

## Quick start

```bash
pip install -e .

# evaluate a skill on a benchmark
export TAHOE_API_BASE=... TAHOE_API_KEY=... TAHOE_MODEL="."
PYTHONPATH=src python3 benchmarks/run_skill_compare.py gsm8k 100 \
    tahoe-93.txt triz-implicit.txt
```

## For researchers

- **Paper**: `paper/tahoe.tex` — language, mechanism, semantics, proofs
  (the committed `paper/tahoe.pdf` predates the 2026-11 truth-in-evidence
  corrections)
- **Current publication evidence**:
  `benchmarks/results/derived/2026-11-18-stage1-full-v3/` — full Stage-1
  derived regrade (all 10 benchmarks, both models, current graders incl. the
  GSM8K numeric-v6 extractor) + per-model canonical statistics; index:
  `benchmarks/results/derived/README.md` (v2 is superseded by the
  extractor-v6 clock-form correction, v1 by the v5 restatement fix — both
  preserved unchanged)
- **Results record**: `docs/EVALUATION.md` + `benchmarks/results/` (per-study)
- **Offline tooling**: `benchmarks/fix_stage1_extraction.py` (regrade CLI,
  helper `stage1_regrade.py`) → `benchmarks/canonical_results.py` (canonical
  stats) → `benchmarks/render_canonical_docs.py` (generated doc blocks,
  `--update`/`--check`) — regenerate any figure with no model calls
- **Preregistration**: `docs/PREREGISTRATION-structure-answer.md` — the
  controlled structure × answer-only factorial experiment; prepared, not run
- **Research journal**: `insights/` — including the grader-format lessons and
  the correction history
- **Experiment programs**: `programs/` — every study's plan as a parser-valid
  TAHOE program + reproduction commands (enforced by `tests/test_programs.py`)
- **Skills**: `language/skills/` — the deployable artifact

## License

MIT. See [CHANGELOG.md](CHANGELOG.md).
