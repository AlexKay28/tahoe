# AIME 2024+2025 — tahoe-93 vs classic (issue #97)

Run date: 2026-09-16 · Model: GLM-5.3-Flash_alexkay28/. · 480 trials (60 × 2 arms × 4 seeds), 0 errors, 0 truncations

## Result

| Arm | Pass@1 (95% CI) | Per-seed (t0..t3) | Avg tokens |
|---|---|---|---|
| classic | 30.8% ± 5.8 (74/240) | 18, 18, 20, 18 /60 | 1895 |
| tahoe-93 | 37.1% ± 6.1 (89/240) | 27, 21, 21, 20 /60 | 1830 |

Delta **+6.2pp, z=1.45 — not significant** (p≈0.15). Direction consistent
across all 4 seeds (4/4 positive). Token ratio 0.97×.

## Interpretation (predeclared-bar discipline)

- **H1 (compression-as-quality) not confirmed**: the proposed channel — classic
  truncation at max_tokens=2048 — did not fire. **Zero truncation in both
  arms**; classic chains fit the budget on this model. The +6.2pp comes from
  genuine answer quality, not budget survival.
- **H0 honored**: trending positive (+6.2pp, 4/4 seeds) is NOT claimed as a
  win at n=240. Recorded as null-trending-positive.
- Curve anchor #2 for #102: classic-acc ~31% → delta +6.2pp (n.s.). Combined
  with GPQA-D (49% → +1.5pp n.s.) and gsm8k (68% → +11.8pp) the difficulty
  response is noisy so far; #98 adds the next point.

## Env + commands

```bash
export TAHOE_API_BASE="https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1"
export TAHOE_API_KEY="$(cat ~/.soy/token)"
export TAHOE_MODEL="."
export SSL_CERT_FILE=/etc/ssl/certs/yandex-ca.pem

# dataset (60 problems from the corp Harbor adapter's exact source URLs)
python3 benchmarks/data/build_aime60.py

# full run: 60 tasks x 2 arms x 4 seeds, shuffled seed 42
BENCHES=aime BENCH_TRIALS=4 PYTHONPATH=src \
  python3 benchmarks/run_public_bench.py
```

## Data

- `benchmarks/data/aime60.jsonl` — committed slice; source = GAIR-NLP/AIME-Preview jsonls
  (the same URLs as `ml/zeliboba/alignment/tool_calling/harbor_bench/src/adapters/aime`)
- Grader: `grade_aime` — bare-integer gold through the same arm-agnostic v3
  extractor as the model side; guarded against both-empty
- Raw trials: `public_benchmarks.json` (this directory)

## Caveats

- 4 seeds at n=60 still leaves ±6pp CI bands that overlap; a verdict-grade
  claim would need ~4× the trials for ±3pp.
- max_tokens=2048 kept for both arms per the frozen protocol — the wall is
  part of the measurement and simply did not bind here.
