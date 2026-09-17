#!/usr/bin/env python3
"""Difficulty-response curve: does the tahoe−classic delta grow with difficulty?

Aggregates GLM-5.3-Flash arm-agnostic results across the stage-1 full-test-set
study (v3-graded) and the harder-benchmark slate (GPQA-D, AIME, MMLU-Pro).
Difficulty is anchored to OUR classic arm — never to published leaderboards.

Outputs (no hand-copied numbers):
  - benchmarks/results/2026-09-16-difficulty-curve/curve.json  (the dataset)
  - paper/figures/difficulty_response.pdf                      (vector figure)

Usage:
    python3 benchmarks/difficulty_curve.py
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent

SOURCES = [
    ("stage-1 (10 full test sets)", ROOT / "benchmarks/results/2026-09-13-stage1-full/full_test_eval.json"),
    ("GPQA Diamond", ROOT / "benchmarks/results/2026-09-16-gpqa-diamond/public_benchmarks.json"),
    ("AIME 2024+2025", ROOT / "benchmarks/results/2026-09-16-aime-24-25/public_benchmarks.json"),
    ("MMLU-Pro 800", ROOT / "benchmarks/results/2026-09-16-mmlu-pro-800/public_benchmarks.json"),
    ("LiveCodeBench v6-150", ROOT / "benchmarks/results/2026-09-17-lcb-v6-150/public_benchmarks.json"),
]
OUT_DIR = ROOT / "benchmarks/results/2026-09-16-difficulty-curve"
FIG_PATH = ROOT / "paper/figures/difficulty_response.pdf"


def load_trials(path):
    data = json.loads(Path(path).read_text())
    return data["trials"] if isinstance(data, dict) and "trials" in data else data


def two_prop_stats(passes_c, n_c, passes_t, n_t):
    acc_c, acc_t = passes_c / n_c, passes_t / n_t
    delta = acc_t - acc_c
    pooled = (passes_c + passes_t) / (n_c + n_t)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_t)) if pooled not in (0, 1) else 0.0
    # 95% CI on the delta (normal approx, same convention as the study RUN.mds)
    ci = 1.96 * se
    z = delta / se if se else 0.0
    return acc_c, acc_t, delta, ci, z


def main():
    agg = defaultdict(lambda: defaultdict(lambda: {"n": 0, "passes": 0, "tokens": 0}))
    for label, path in SOURCES:
        for t in load_trials(path):
            a = agg[t["benchmark"]][t["arm"]]
            a["n"] += 1
            a["passes"] += bool(t["passed"])
            a["tokens"] += t["total_tokens"]

    curve = []
    for bench, arms in sorted(agg.items()):
        if "classic" not in arms or "tahoe" not in arms:
            continue
        c, t = arms["classic"], arms["tahoe"]
        acc_c, acc_t, delta, ci, z = two_prop_stats(c["passes"], c["n"], t["passes"], t["n"])
        curve.append({
            "benchmark": bench,
            "n_classic": c["n"], "n_tahoe": t["n"],
            "classic_acc": round(acc_c, 4), "tahoe_acc": round(acc_t, 4),
            "delta_pp": round(100 * delta, 2),
            "delta_ci95_pp": round(100 * ci, 2),
            "z": round(z, 2),
            "significant_95": abs(z) >= 1.96,
            "token_ratio": round(t["tokens"] / c["tokens"], 4) if c["tokens"] else None,
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "curve.json").write_text(json.dumps(curve, indent=2) + "\n")
    print(f"wrote {len(curve)} benchmarks to {OUT_DIR / 'curve.json'}")
    for row in sorted(curve, key=lambda r: r["classic_acc"]):
        star = "*" if row["significant_95"] else " "
        print(f"  {row['benchmark']:12s} classic={100*row['classic_acc']:5.1f}%  "
              f"delta={row['delta_pp']:+6.2f}±{row['delta_ci95_pp']:.2f}{star}  "
              f"tok_ratio={row['token_ratio']:.3f}")

    # ---- figure: two panels ----
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 6.4), sharex=True)
    xs = [100 * r["classic_acc"] for r in curve]

    for ax, ys, ylabel in (
        (ax1, [r["delta_pp"] for r in curve], "quality delta, tahoe − classic (pp)"),
        (ax2, [r["token_ratio"] for r in curve], "token ratio, tahoe / classic"),
    ):
        ax.axhline(1.0 if "ratio" in ylabel else 0.0, color="gray", lw=0.8, ls="--")
        ax.scatter(xs, ys, s=42, zorder=3)
        for r, x, y in zip(curve, xs, ys):
            if "delta" in ylabel:
                ax.errorbar(x, y, yerr=r["delta_ci95_pp"], fmt="none",
                            ecolor="gray", elinewidth=0.9, capsize=2.5, zorder=2)
            ax.annotate(r["benchmark"], (x, y), textcoords="offset points",
                        xytext=(5, 4), fontsize=7.5)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(alpha=0.25, lw=0.5)

    ax1.set_title("Difficulty response: GLM-5.3-Flash, tahoe-93 vs classic",
                  fontsize=10)
    ax2.set_xlabel("classic-arm accuracy (%) — our arm, frozen protocol", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_PATH)
    print(f"figure written to {FIG_PATH}")


if __name__ == "__main__":
    main()
