# Difficulty-response curve (issue #102)

Built: 2026-09-16 · 13 benchmark–arm pairs, GLM-5.3-Flash only, all v3-graded arm-agnostic pipeline

## Outputs

- `curve.json` — the dataset (benchmark, n per arm, accs, delta ± CI95, z, significance flag, token ratio)
- `paper/figures/difficulty_response.pdf` — vector figure (two panels)
- `paper/tahoe.tex` → new subsection "Difficulty Response" (Results)

## The curve (sorted by classic-arm accuracy)

| classic acc | benchmark | delta (pp) | tok ratio |
|---|---|---|---|
| 30.8% | aime | +6.25 ± 8.47 | 0.965 |
| 49.5% | gpqa | +1.52 ± 9.85 | 1.004 |
| 68.5% | gsm8k | **+11.78 ± 1.92*** | 0.803 |
| 75.1% | mmlu_pro | **+4.25 ± 4.11*** | 0.877 |
| 93.4–100% | lsat, race, mmlu_math/logic/acct, arc, bbh, bbh_track, bbh_arith | −2.1 … +1.5, all n.s. | 0.78–1.43 |

(*) significant at 95%.

## Interpretation (honest)

**The delta is task-type-driven, not difficulty-monotonic.** It peaks in a
sweet band — solvable-but-not-trivial tasks needing multi-step search
(gsm8k) or discrimination under distractor density (mmlu_pro) — and compresses
to ~0 at both extremes: too-hard knowledge retrieval (gpqa: no search space to
bound) and the ceiling (>93%: nothing to gain). Token behavior mirrors it:
in-band TAHOE is better AND cheaper (0.80–0.88×); at the ceiling overhead can
dominate (bbh_arith 1.43× at Δ≈0).

## Regenerate

```bash
python3 benchmarks/difficulty_curve.py
```

Sources (committed trial files, zero hand-copied numbers):
`2026-09-13-stage1-full/full_test_eval.json`, `2026-09-16-gpqa-diamond/`,
`2026-09-16-aime-24-25/`, `2026-09-16-mmlu-pro-800/`.
