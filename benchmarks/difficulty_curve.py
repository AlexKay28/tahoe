#!/usr/bin/env python3
"""Difficulty-response curve: does the tahoe−classic delta grow with difficulty?

Aggregates GLM-5.3-Flash arm-agnostic results across the stage-1 full-test-set
study (v3-graded) and the harder-benchmark slate (GPQA-D, AIME, MMLU-Pro,
LiveCodeBench). Difficulty is anchored to OUR classic arm — never to published
leaderboards.

Statistics — paired and task-level, via benchmarks/stats.py (this replaces the
old unpaired pooled two-proportion z test):

  - Trials are paired by exact (benchmark, task_id, trial) identity; unmatched
    trials never form pairs, and duplicate keys are rejected loudly.
  - Repeated trials are averaged within each (benchmark, task_id) task, so
    tasks — not repeated trials — are the unit of analysis.
  - delta is the *task macro* paired difference (tahoe − classic) of task-mean
    pass indicators, with a 95% paired task-cluster bootstrap (percentile) CI.
  - Significance is a two-sided paired permutation test on the task-macro
    values, then Holm-adjusted across the whole benchmark family (every
    benchmark in the curve).

Output schema — benchmarks/results/2026-09-16-difficulty-curve/curve.json
(one row per benchmark, a plain list as before):

  benchmark           benchmark name
  n_classic/n_tahoe   paired trials per arm (unpaired trials are dropped)
  n_tasks             paired (benchmark, task_id) tasks behind the estimate
  n_unpaired_classic  classic trials dropped for lack of a tahoe counterpart
  n_unpaired_tahoe    tahoe trials dropped for lack of a classic counterpart
  classic_acc         task-macro accuracy, classic arm (the difficulty axis)
  tahoe_acc           task-macro accuracy, tahoe arm
  classic_acc_micro   trial-level pooled pass fraction (classic); differs from
  tahoe_acc_micro     the macro value when tasks carry unequal trial counts
  delta_pp            paired task-macro delta, tahoe − classic, in pp
  delta_ci95_pp_lo    percentile bootstrap CI lower bound for delta_pp, in pp
  delta_ci95_pp_hi    percentile bootstrap CI upper bound for delta_pp, in pp
  delta_ci95_pp       conservative symmetric half-width
                      max(point − lo, hi − point), in pp — kept so "±"
                      renderings stay truthful (they always cover the CI)
  p_paired            raw two-sided paired permutation p-value (task macro)
  p_paired_holm       p_paired Holm-adjusted across the benchmark family
  significant_95      COMPATIBILITY ALIAS consumed by
                      benchmarks/make_results_table.py: True iff
                      p_paired_holm < 0.05 (family-wise, paired permutation).
                      The archived curve.json used the unpaired z ≥ 1.96 rule,
                      so archived values are not comparable.
  token_ratio         sum(total_tokens) over paired trials, tahoe / classic —
                      explicitly *total*-token based (never output-token based)
  pairing_key         ["benchmark", "task_id", "trial"] — how pairs were formed

The unpaired "z" field is gone: it had no truthful meaning once pairing became
keyed and task-level.

Outputs (no hand-copied numbers):
  - benchmarks/results/2026-09-16-difficulty-curve/curve.json  (the dataset)
  - paper/figures/difficulty_response.pdf                      (vector figure)

Usage:
    python3 benchmarks/difficulty_curve.py
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stats import (  # noqa: E402  benchmarks/stats.py — keyed task-level machinery
    aggregate_trials_by_task,
    holm_adjust_pvalues,
    pair_trials,
    paired_bootstrap_ci,
    paired_permutation_test,
)

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

ARM_CLASSIC = "classic"
ARM_TAHOE = "tahoe"
CONFIDENCE = 0.95
ALPHA = 0.05
SEED = 42
N_RESAMPLES = 10_000
N_PERMUTATIONS = 10_000


def load_trials(path):
    data = json.loads(Path(path).read_text())
    return data["trials"] if isinstance(data, dict) and "trials" in data else data


def _task_sort_key(key):
    # Deterministic order independent of dict insertion order (mirrors stats.py).
    return tuple(f"{type(value).__name__}:{value!r}" for value in key)


def paired_task_means(pairs, field):
    """Average repeated trials within each (benchmark, task_id) task.

    Pure. Returns (task_keys, values_a, values_b): one equally weighted mean
    per arm for every paired task, in deterministic key order.
    """
    if not pairs:
        return [], [], []
    values_a = aggregate_trials_by_task([a for a, _ in pairs], field)
    values_b = aggregate_trials_by_task([b for _, b in pairs], field)
    keys = sorted(values_a, key=_task_sort_key)
    return keys, [values_a[key] for key in keys], [values_b[key] for key in keys]


def benchmark_row(
    benchmark,
    trials_classic,
    trials_tahoe,
    *,
    seed=SEED,
    n_resamples=N_RESAMPLES,
    n_permutations=N_PERMUTATIONS,
    confidence=CONFIDENCE,
):
    """Build one curve row from the two arms of a single benchmark.

    Pure: no I/O. Returns None when no (benchmark, task_id, trial) key exists
    in both arms — there is no paired estimate to anchor, and the benchmark is
    skipped rather than reported with unpaired numbers.
    """
    pairs = pair_trials(trials_classic, trials_tahoe)
    if not pairs:
        return None

    task_keys, passed_c, passed_t = paired_task_means(pairs, "passed")
    n_pairs = len(pairs)

    # Paired task-macro estimate: mean over tasks of (task-mean tahoe − classic).
    point, lo, hi = paired_bootstrap_ci(
        passed_t, passed_c, n_resamples=n_resamples, confidence=confidence, seed=seed,
    )
    p_raw = paired_permutation_test(
        passed_t, passed_c, n_permutations=n_permutations, seed=seed,
    )

    # Micro (trial-level pooled) accuracy over the *paired* trials only.
    micro_c = sum(1 for a, _ in pairs if a.get("passed", False)) / n_pairs
    micro_t = sum(1 for _, b in pairs if b.get("passed", False)) / n_pairs

    # Token ratio stays explicitly total-token based: sums over paired trials.
    tokens_c = sum(a.get("total_tokens", 0) for a, _ in pairs)
    tokens_t = sum(b.get("total_tokens", 0) for _, b in pairs)

    return {
        "benchmark": benchmark,
        "n_classic": n_pairs,
        "n_tahoe": n_pairs,
        "n_tasks": len(task_keys),
        "n_unpaired_classic": len(trials_classic) - n_pairs,
        "n_unpaired_tahoe": len(trials_tahoe) - n_pairs,
        "classic_acc": round(statistics.fmean(passed_c), 4),
        "tahoe_acc": round(statistics.fmean(passed_t), 4),
        "classic_acc_micro": round(micro_c, 4),
        "tahoe_acc_micro": round(micro_t, 4),
        "delta_pp": round(100 * point, 2),
        "delta_ci95_pp_lo": round(100 * lo, 2),
        "delta_ci95_pp_hi": round(100 * hi, 2),
        "delta_ci95_pp": round(100 * max(point - lo, hi - point), 2),
        "p_paired": round(p_raw, 5),
        "token_ratio": round(tokens_t / tokens_c, 4) if tokens_c else None,
        "pairing_key": ["benchmark", "task_id", "trial"],
    }


def apply_holm(rows, alpha=ALPHA):
    """Holm-adjust p_paired across the benchmark family, in place.

    The family is every benchmark row in the curve. Also sets the
    significant_95 compatibility alias (family-wise: p_paired_holm < alpha).
    """
    adjusted = holm_adjust_pvalues([row["p_paired"] for row in rows]) if rows else []
    for row, p_holm in zip(rows, adjusted):
        row["p_paired_holm"] = round(p_holm, 5)
        row["significant_95"] = bool(p_holm < alpha)
    return rows


def compute_curve(
    trials,
    *,
    seed=SEED,
    n_resamples=N_RESAMPLES,
    n_permutations=N_PERMUTATIONS,
    confidence=CONFIDENCE,
    alpha=ALPHA,
):
    """Build all curve rows; pure and independent of input order.

    Trials are grouped by benchmark, paired by exact
    (benchmark, task_id, trial) identity, aggregated to task means, then
    Holm-adjusted across the benchmark family. Benchmarks without both arms,
    or without a single paired trial, are skipped (never reported unpaired).
    """
    by_bench = defaultdict(lambda: {ARM_CLASSIC: [], ARM_TAHOE: []})
    for t in trials:
        arms = by_bench[t["benchmark"]]
        if t.get("arm") in (ARM_CLASSIC, ARM_TAHOE):
            arms[t["arm"]].append(t)

    rows = []
    for bench in sorted(by_bench, key=str):
        arms = by_bench[bench]
        if not arms[ARM_CLASSIC] or not arms[ARM_TAHOE]:
            continue
        row = benchmark_row(
            bench, arms[ARM_CLASSIC], arms[ARM_TAHOE],
            seed=seed, n_resamples=n_resamples,
            n_permutations=n_permutations, confidence=confidence,
        )
        if row is not None:
            rows.append(row)
    return apply_holm(rows, alpha=alpha)


def write_figure(curve, fig_path):
    """Render the two-panel vector figure (delta vs difficulty, token ratio)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 6.4), sharex=True)
    xs = [100 * r["classic_acc"] for r in curve]

    for ax, ys, ylabel in (
        (ax1, [r["delta_pp"] for r in curve], "quality delta, tahoe − classic (pp)"),
        (ax2, [r["token_ratio"] for r in curve if r["token_ratio"] is not None],
         "token ratio, tahoe / classic"),
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
    fig.savefig(fig_path)


def main():
    trials = []
    for _label, path in SOURCES:
        trials.extend(load_trials(path))

    curve = compute_curve(trials)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "curve.json").write_text(json.dumps(curve, indent=2) + "\n")
    print(f"wrote {len(curve)} benchmarks to {OUT_DIR / 'curve.json'}")
    for row in sorted(curve, key=lambda r: r["classic_acc"]):
        star = "*" if row["significant_95"] else " "
        tok = f"{row['token_ratio']:.3f}" if row["token_ratio"] is not None else "  n/a"
        print(f"  {row['benchmark']:12s} classic={100*row['classic_acc']:5.1f}%  "
              f"delta={row['delta_pp']:+6.2f}±{row['delta_ci95_pp']:.2f}{star}  "
              f"p_holm={row['p_paired_holm']:.3f}  tok_ratio={tok}")

    write_figure(curve, FIG_PATH)
    print(f"figure written to {FIG_PATH}")


if __name__ == "__main__":
    main()