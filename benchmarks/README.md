# Benchmarks & Evaluation

Evaluation infrastructure for the TAHOE language. Protocol invariants and
token-accounting rules: `EVAL_PROTOCOL.md`. Research journal: `../insights/`.
Durable results summary: `../docs/EVALUATION.md`.

## Canonical entry points

| Runner | Purpose | Writes to |
|---|---|---|
| `run_skill_compare.py` | **Canonical** single-call arm comparison (any prompt arms, one benchmark, parallel). Prompts resolve by name via `prompt_paths.py` from `language/`. | `results/runs/<ts>_skill-cmp-<bench>/trials.json` |
| `run_single_bench.py` | One benchmark, classic-vs-tahoe, parallel; supports full test sets (`all` or N). | `results/runs/<ts>_single-<bench>/trials.json` |
| `run_parallel_bench.py` | All benchmarks + bootstrap CIs + permutation tests (`MAX_SAMPLES`, `BENCH_ARMS` env). | `results/runs/<ts>_public-bench/` |
| `run_public_bench.py` | Original frozen-protocol runner (sequential). | `results/runs/<ts>_public-bench/` |
| `run_prompt_ablation.py` | Skill-size ablation (5 arms). | `results/` |
| `run_vm_bench.py` | TAHOE-VM pilot (shelved branch — see `../docs/TAHOE_VM.md`). | `results/` |
| `run_e1_notation.py`, `run_e13_cod_parity.py`, `run_multiturn_bench.py`, `run_trials.py` | Earlier experiments (frozen, reference). | `results/` |

**Never write to a fixed filename at the results root.** Active runners use
`outdir.make_run_dir()` (timestamped `results/runs/<UTC-stamp>_<name>/`); set
`RUN_TAG` to label, `RESULTS_ROOT` to relocate. At the end of a study, freeze
its directory into a dated study folder under `results/` (see
`results/README.md` for the index).

## Shared modules

- `prompt_paths.py` — resolves prompts from `language/skills` (+ `variants/`)
  and `language/baselines`; legacy filenames alias to canonical names.
- `runner_classic.py` — the single-call inference arm (OpenAI-compatible,
  `extra_body` passthrough for `reasoning_effort` etc.).
- `graders.py`, `stats.py`, `metrics.py`, `report.py`, `token_proxy.py`
- `outdir.py` — run-directory helper.

## Offline derived-results tooling (no model calls)

The Stage-1 publication evidence is produced offline from the frozen raw
archives by a three-stage pipeline — **current publication evidence:
`results/derived/2026-11-18-stage1-full-v3/`** (index:
`results/derived/README.md`; v2 is superseded by its GSM8K extractor-v6
clock-form correction and v1 by the v5 restatement fix — both preserved
unchanged):

1. **Regrade** — `fix_stage1_extraction.py` (CLI, required
   `--input <raw archive> --output <fresh derived artifact>`;
   helper pipeline `stage1_regrade.py`): re-grades all ten Stage-1
   benchmarks with the current graders, into a separate derived artifact.
   Read-only input, exclusive-create output, grader sha-256 pinned.
   GSM8K-only variant: `fix_gsm8k_extraction.py` (helper `gsm8k_regrade.py`).
2. **Canonical statistics** — `canonical_results.py`: deterministic
   per-model JSON+Markdown from a derived artifact; labeled micro/macro
   estimands; truncation/cap/empty outcomes from recorded fields only;
   keyed task-cluster paired comparisons with Holm correction; refuses
   overwrite.
3. **Doc rendering** — `render_canonical_docs.py`: renders Markdown/LaTeX
   blocks from a canonical payload; updates marked generated blocks in docs
   (`--update PATH`) and verifies them (`--check PATH`). Docs never
   hand-maintain numbers that a payload can generate.

## Environment

```bash
export TAHOE_API_BASE=...   # OpenAI-compatible endpoint
export TAHOE_API_KEY=...
export TAHOE_MODEL="."      # model id as required by the endpoint
export SSL_CERT_FILE=...    # if corporate CA
export TAHOE_API_POOL=...   # quota pool header
export N_WORKERS=6          # parallel workers (respect endpoint inflight quota!)
```

## Grading rules (hard-won, three incidents)

1. Graders must accept every reasonable answer format for the task
   (parenthesized/bare letters; thousands-separated and LaTeX numbers).
2. Audit extraction on raw outputs from **every arm** before trusting
   cross-arm deltas — format differences between arms masquerade as quality
   differences.
3. Grading logic never branches on arm identity (frozen invariant).
