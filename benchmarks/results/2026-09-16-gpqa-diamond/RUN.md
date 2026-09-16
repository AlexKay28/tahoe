# GPQA Diamond — tahoe-93 vs classic (issue #96)

Run date: 2026-09-16 · Model: GLM-5.3-Flash_alexkay28/. · 396 trials, 0 errors, 0 truncations

## Result

| Arm | Pass@1 (95% CI) | Avg tokens/trial | Avg output tokens |
|---|---|---|---|
| classic | 49.5% ± 7.0 (98/198) | 1560 | 1323 |
| tahoe-93 | 51.0% ± 7.0 (101/198) | 1565 | 1239 |

Delta: **+1.5pp, z=0.30** (two-proportion z-test) — **not significant**.
Token ratio (total): 1.00× · (output only): 0.94×.

## Interpretation

Quality-neutral on PhD-level knowledge retrieval. This is the H2-adjacent
outcome predeclared in the issue: typed bounding neither helps nor fights
knowledge lookup. Contrast with search-heavy benchmarks — gsm8k +11.8pp at
0.38× tokens — supports the mechanism claim: TAHOE's gains come from bounding
multi-step *search*, not from knowledge *retrieval*, which has no search space
to bound. Data point for the difficulty-response curve (#102): at classic-acc
~49%, delta ≈ 0.

## Env + commands

```bash
export TAHOE_API_BASE="https://api.eliza.yandex.net/raw/internal/v2/models/GLM-5.3-Flash_alexkay28/v1"
export TAHOE_API_KEY="$(cat ~/.soy/token)"
export TAHOE_MODEL="."
export SSL_CERT_FILE=/etc/ssl/certs/yandex-ca.pem

# dataset (198 questions, corp YT raw table, seed-42 option shuffle)
YT_PROXY=hahn python3 benchmarks/data/build_gpqa_diamond.py

# full run: 198 tasks x 2 arms x 1 trial, shuffled seed 42
BENCHES=gpqa BENCH_TRIALS=1 PYTHONPATH=src \
  python3 benchmarks/run_public_bench.py
```

## Data

- `benchmarks/data/gpqa_diamond.jsonl` — committed slice + `build_gpqa_diamond.py` (provenance: YT `//home/instruboba/quality/benchmarks/exam_A/GPQA/gpqa_diamond`, 198 rows; the processed `gpqa_diamond_gpt_202` table has 196 — see issue #104)
- Raw trials: `public_benchmarks.json` (this directory)
- Grader: arm-agnostic letter A–D (`grade_arc` logic); identical extraction both arms

## Caveats

- Single seed; CI ±7pp means only |delta| > ~10pp would be detectable — a 3-seed rerun only if a follow-up needs the precision.
- Output tokens compressed 0.94× while total is flat: GPQA prompts are long (question+4 options) relative to short letter answers, so input dominates.
