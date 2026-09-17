# Results Archive

**Rule: runs append to dated study directories — never overwrite.** Active
runners write to `results/runs/<UTC-timestamp>_<name>/` (created automatically);
at the end of a study, freeze its data into a dated directory below and index
it here.

| Directory | Study | Key files | Doc |
|---|---|---|---|
| `2026-09-13-pilot/` | 600-trial pilot (10 samples x 10 benches), legacy eval results | `public_benchmarks.json`, `trials.json`, `report.json` | `FULL_EVAL_SUMMARY.md` (in stage1-full) |
| `2026-09-13-stage1-full/` | Stage-1 full-test-set eval, both models (63,348 trials), grader-corrected | `full_test_eval.json` (GLM), `oss_full_eval.json`, `single_*.json`, `CROSS_MODEL_EVAL.md` | `docs/EVALUATION.md` |
| `2026-09-14-skill-study/` | Skill comparisons (GLM 200-sample, v3 grader) + prompt-size ablation + E1 notation | `skill_cmp_*.json`, `prompt_ablation.json`, `e1_notation.json` | `insights/compact-language.md` |
| `2026-09-14-vm-pilot/` | TAHOE-VM pilot (shelved branch) + oss-overwrite artifacts | `vm_pilot_*.json`, `full_200_eval.json` | `docs/TAHOE_VM.md` |
| `2026-09-16-gpqa-diamond/` | GPQA Diamond, 198 Qs, tahoe vs classic (#96) | `public_benchmarks.json` | `RUN.md` |
| `2026-09-16-aime-24-25/` | AIME 2024+2025, 4 seeds, truncation analysis (#97) | `public_benchmarks.json` | `RUN.md` |
| `2026-09-16-mmlu-pro-800/` | MMLU-Pro stratified-800 (#98) | `public_benchmarks.json` | `RUN.md` |
| `2026-09-17-lcb-v6-150/` | LiveCodeBench v6-150, docker-free sandbox (#99) | `public_benchmarks.json` | `RUN.md` |
| `2026-09-16-difficulty-curve/` | 14-benchmark difficulty-response curve (#102) | `curve.json` | `RUN.md` |

Note: files in `2026-09-14-vm-pilot/` include data whose gsm8k rows were
produced under the v1 grader; see the correction in
`insights/compact-language.md` before citing numbers from that directory.

## Current runners

- `run_skill_compare.py` — canonical single-call arm comparison (writes
  `results/runs/...`)
- `run_single_bench.py` — one benchmark, two arms, parallel
- `run_parallel_bench.py` — all benchmarks + bootstrap CIs
- `run_public_bench.py` — frozen-protocol runner; now covers 13 benches
  (`BENCHES=...` filter, `BENCH_TRIALS=N`, `GPQA_LIMIT` for smoke)
- `difficulty_curve.py` — aggregates all studies into the difficulty-response
  curve (`curve.json` + `paper/figures/difficulty_response.pdf`)
- `make_results_table.py` — generates `paper/results_slate.md` (consolidated
  14-benchmark table) from committed trials; regenerate, never hand-edit

## Harder-benchmark slate headline (2026-09-16/17)

4/4 additions trend positive (GPQA +1.5, AIME +6.2, LCB +4.7, MMLU-Pro
+4.2*); 2/14 slate deltas significant at 95% (gsm8k +11.8 @ 0.80×, mmlu_pro
+4.2 @ 0.88×). Consolidated table: `paper/results_slate.md`.
