# MMLU-Pro stratified-800 — tahoe-93 vs classic (issue #98)

Run date: 2026-09-16 · Model: GLM-5.3-Flash_alexkay28/. · 1,600 trials (800 × 2 arms), 0 errors, 0 truncations

## Result

| Arm | Pass@1 (95% CI) | Avg tokens |
|---|---|---|
| classic | 75.1% ± 3.0 (601/800) | 855 |
| tahoe-93 | 79.4% ± 2.8 (635/800) | 750 |

Delta **+4.2pp, z=2.03 — significant at 95%** (p≈0.042). Token ratio **0.877×**.

## Interpretation

**First statistically significant positive of the harder-benchmark slate —
and it dominates on both axes**: higher quality at ~12% fewer tokens. The
predeclared mechanism (10-option distractor density rewards structured
error-correction discipline) held. Curve anchor #3: classic-acc 75% →
+4.2pp*. The slate's picture so far is task-type-driven, not
difficulty-monotonic: multi-step computation (gsm8k +11.8pp) and
discrimination (MMLU-Pro +4.2pp*) gain; knowledge lookup (GPQA +1.5pp n.s.)
and frontier math (AIME +6.2pp n.s.) do not significantly move.

## Env + commands

```bash
export TAHOE_API_BASE="https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1"
export TAHOE_API_KEY="$(cat ~/.soy/token)"
export TAHOE_MODEL="."
export SSL_CERT_FILE=/etc/ssl/certs/yandex-ca.pem

# dataset (one-time, committed; never resampled)
python3 benchmarks/data/build_mmlu_pro_800.py

# full run: 800 tasks x 2 arms x 1 trial, shuffled seed 42
BENCHES=mmlu_pro BENCH_TRIALS=1 PYTHONPATH=src \
  python3 benchmarks/run_public_bench.py
```

## Data

- `benchmarks/data/mmlu_pro_800.jsonl` — proportional stratified sample across
  14 categories (largest-remainder, seed 42); option counts 3-10 as in the
  source dataset
- Grader: `grade_mmlu_pro` — letter A–J, arm-agnostic
- Raw trials: `public_benchmarks.json` (this directory)

## Caveats

- Single seed; the significance is over 800 paired-ish trials, adequate for
  ±3pp precision but not per-category claims (25-90 items/category).
- 4 records have 3 options, 39 have 4 — MMLU-Pro's own distribution, kept as-is.
