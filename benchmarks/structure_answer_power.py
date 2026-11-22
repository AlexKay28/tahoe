#!/usr/bin/env python3
"""Pre-run precision and power justification for the structure-answer experiment.

STATUS: analysis code only — this module performs arithmetic on archived trial
data and stated variance assumptions. It launches no model evaluations and
never runs on import (see the ``__main__`` guard).

Why this module exists: the preregistered quality non-inferiority margin is
0.05 absolute success-rate points, and every confirmatory decision is
Holm-corrected within a multiplicity family. Whether the planned task count
can support those CONFIRMATORY claims must be shown BEFORE the experiment
runs, at the family-wise worst-case per-comparison alpha. This module makes
that calculation transparent and reproducible from (a) archived trial data
(empirical paired task-difference variance) and (b) explicit analytic bounds.

Multiplicity convention (conservative by design)
-------------------------------------------------
Holm's step-down procedure rejects its most significant hypothesis at
alpha/m; subsequent steps get progressively larger effective thresholds.
Planning at the FIRST-STEP alpha/m (the Bonferroni bound) is therefore the
conservative worst case for every comparison in a family of size m:
the achieved power at actual Holm thresholds is at least as high as computed
here. Confirmatory power in this module is ALWAYS computed at alpha/m;
unadjusted (m=1) numbers, where shown, are labeled non-confirmatory.

Estimand and notation
---------------------
- Per task i and arm a, the per-task mean success is
  ``s_ia = mean over repeated trials of 1[passed]`` (T trials per task).
- For a comparison (candidate c vs reference r) the per-task paired
  difference is ``d_i = s_ic - s_ir`` with sample SD ``sd_d``.
- Non-inferiority (one-sided, H0: mean(d) <= -margin), true mean difference 0,
  normal approximation, family size m:
  ``power = Phi( margin / (sd_d/sqrt(n)) - z_{1-alpha/m} )`` and
  ``n_required = ceil( ((z_{1-alpha/m} + z_{power}) * sd_d / margin)^2 )``.
- Two-sided comparison of effect delta at family size m:
  ``power = Phi( delta / (sd_d/sqrt(n)) - z_{1-alpha/(2m)} )`` and
  ``n_required = ceil( ((z_{1-alpha/(2m)} + z_{power}) * sd_d / delta)^2 )``.
- The 95% CI half-width of the paired mean difference is
  ``z_{0.975} * sd_d / sqrt(n)`` (multiplicity does not apply to the
  descriptive CI); a precision target is half-width < margin.

Bounds on sd_d (per-task paired difference SD, T trials per task)
------------------------------------------------------------------
- VALID DISTRIBUTION-FREE PAIRED BOUND: ``sd_d <= sqrt(1/T)``.
  Each per-task arm mean has variance p(1-p)/T <= 1/(4T). The DIFFERENCE of
  two perfectly anti-correlated arm outcomes (reference passes exactly when
  the candidate fails, p = 1/2 for both) has per-trial variance 1, so the
  per-task mean difference has variance 1/T and sd_d = sqrt(1/T) = 0.5774
  for T = 3. This is the adversarial extreme: it requires the two arms'
  outcomes to be maximally opposed per task, which contradicts both the
  archived data (pooled sd_d <= 0.187) and the structural similarity of the
  arms being compared. It is reported, not assumed away — and the design
  explicitly does NOT claim confirmatory power at this bound (see the
  generated justification artifact).
- INDEPENDENT-ARM SENSITIVITY BOUND: ``sd_d = sqrt(1/(2T))`` = 0.4082 for
  T = 3. This assumes the two arms' per-task means are INDEPENDENT (zero
  pairing benefit) with p = 1/2. It is a sensitivity value, NOT an upper
  bound for paired data — the valid bound above is larger.
- PLANNING SD (preregistered): 0.25 — rounded up ~34% above the archived
  pooled empirical maximum (0.187), below the archived per-benchmark
  maximum (0.351) and below the independent-arm sensitivity bound.
- EMPIRICAL: sd_d estimated from archived ablation trials
  (benchmarks/results/2026-09-14-skill-study/prompt_ablation.json,
  5 prompt arms x 10 benchmarks x 10 tasks x 3 trials, per-task success).
  Read-only: archives are never edited.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from statistics import NormalDist

_NORMAL = NormalDist()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE_SOURCES = [
    REPO_ROOT / "benchmarks" / "results" / "2026-09-14-skill-study" / "prompt_ablation.json",
]
DEFAULT_OUTPUT = REPO_ROOT / "benchmarks" / "structure-answer-power.json"


def z_quantile(q: float) -> float:
    """The standard-normal q-th quantile."""
    return _NORMAL.inv_cdf(q)


# -- Empirical variance from trial records --------------------------------


def paired_difference_stats(
    trials: list[dict], arm_a: str, arm_b: str
) -> dict[str, Any]:
    """Per-task paired success-difference statistics for (arm_a, arm_b).

    Returns ``n_tasks``, ``mean_difference`` and the sample SD of the
    per-task paired differences (``sd_d``). Requires the standard trial
    key fields (benchmark, task_id, trial, arm, passed) so the pairing is
    keyed, never positional.
    """
    def index(arm: str) -> dict[tuple, float]:
        grouped: dict[tuple, list[float]] = defaultdict(list)
        for t in trials:
            if t["arm"] == arm:
                grouped[(t["benchmark"], t["task_id"])].append(
                    1.0 if t.get("passed") else 0.0
                )
        return {k: statistics.fmean(v) for k, v in grouped.items()}

    means_a = index(arm_a)
    means_b = index(arm_b)
    keys = sorted(set(means_a) & set(means_b))
    if len(keys) < 2:
        raise ValueError(
            f"need at least two shared tasks for a variance estimate, got {len(keys)}"
        )
    diffs = [means_a[k] - means_b[k] for k in keys]
    return {
        "n_tasks": len(keys),
        "mean_difference": statistics.fmean(diffs),
        "sd_d": statistics.stdev(diffs),
    }


def _resolve_repo_path(path: Path | str) -> Path:
    """Resolve a configured path against the repo root, always absolute."""
    path = Path(path)
    if not path.is_absolute():
        candidate = REPO_ROOT / path
        path = candidate if candidate.exists() else path
    return path.resolve()


def archive_paired_sds(
    paths: list[Path],
    pairs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Empirical paired-difference SDs from archived trial files.

    For each archive file (hash-pinned in the result) and each arm pair,
    reports the pooled per-task SD plus the largest per-benchmark SD. Only
    archived files are read; nothing is modified.
    """
    out: dict[str, Any] = {"archives": [], "pairs": [list(p) for p in (pairs or [])]}
    for path in paths:
        path = _resolve_repo_path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        trials = payload["trials"] if isinstance(payload, dict) else payload
        entry: dict[str, Any] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "n_trials": len(trials),
            "arms": sorted({t["arm"] for t in trials}),
            "pooled": {},
            "per_benchmark_max": {},
        }
        evaluated_pairs = pairs
        if not evaluated_pairs:
            arms = entry["arms"]
            evaluated_pairs = [
                (a, b) for i, a in enumerate(arms) for b in arms[i + 1:]
            ]
        for arm_a, arm_b in evaluated_pairs:
            stats = paired_difference_stats(trials, arm_a, arm_b)
            entry["pooled"][f"{arm_a}|{arm_b}"] = {
                "sd_d": round(stats["sd_d"], 6),
                "mean_difference": round(stats["mean_difference"], 6),
                "n_tasks": stats["n_tasks"],
            }
            by_bench: dict[str, list[float]] = defaultdict(list)
            means_a: dict[tuple, list[float]] = {}
            means_b: dict[tuple, list[float]] = {}
            for t in trials:
                if t["arm"] == arm_a:
                    means_a.setdefault((t["benchmark"], t["task_id"]), []).append(
                        1.0 if t.get("passed") else 0.0
                    )
                elif t["arm"] == arm_b:
                    means_b.setdefault((t["benchmark"], t["task_id"]), []).append(
                        1.0 if t.get("passed") else 0.0
                    )
            means_a = {k: statistics.fmean(v) for k, v in means_a.items()}
            means_b = {k: statistics.fmean(v) for k, v in means_b.items()}
            for key in set(means_a) & set(means_b):
                by_bench[key[0]].append(means_a[key] - means_b[key])
            worst = max(
                (
                    {"benchmark": bench, "sd_d": statistics.stdev(d)}
                    for bench, d in by_bench.items()
                    if len(d) >= 2
                ),
                key=lambda item: item["sd_d"],
                default={"benchmark": None, "sd_d": 0.0},
            )
            entry["per_benchmark_max"][f"{arm_a}|{arm_b}"] = {
                "benchmark": worst["benchmark"],
                "sd_d": round(worst["sd_d"], 6),
            }
        out["archives"].append(entry)
    return out


# -- Analytic bounds and sample-size algebra --------------------------------


def worst_case_paired_sd(trials_per_task: int) -> float:
    """VALID distribution-free bound on the per-task paired-difference SD.

    ``sd_d <= sqrt(1/T)``: with per-trial perfectly anti-correlated arm
    outcomes (reference passes exactly when the candidate fails, p = 1/2 for
    both arms), the per-trial difference has variance 1 and the per-task mean
    difference over T trials has variance 1/T. For T=3 this is 0.5774 — the
    adversarial extreme; the design reports it and does NOT claim
    confirmatory non-inferiority power at this bound.
    """
    if trials_per_task < 1:
        raise ValueError("trials_per_task must be >= 1")
    return math.sqrt(1.0 / trials_per_task)


def independent_arm_sd(trials_per_task: int) -> float:
    """INDEPENDENT-ARM SENSITIVITY bound on the per-task paired SD (NOT an
    upper bound for paired data).

    Assumes the two arms' per-task means are independent with p = 1/2:
    variance 1/(4T) + 1/(4T) = 1/(2T), so sd = sqrt(1/(2T)) = 0.4082 for
    T=3. Any real pairing benefit makes the true sd smaller; the valid
    paired bound (worst_case_paired_sd) is larger.
    """
    if trials_per_task < 1:
        raise ValueError("trials_per_task must be >= 1")
    return math.sqrt(1.0 / (2.0 * trials_per_task))


def noninferiority_power(
    n_tasks: int,
    sd_d: float,
    margin: float,
    alpha: float = 0.05,
    true_difference: float = 0.0,
    multiplicity: int = 1,
) -> float:
    """One-sided paired non-inferiority power (normal approximation).

    ``multiplicity`` is the Holm family size m; planning uses the
    Bonferroni/Holm-first-step per-comparison alpha ``alpha/m``, which is
    conservative for every step of the actual Holm procedure. Power is
    computed under a true mean paired difference of ``true_difference``.
    """
    if n_tasks < 1 or sd_d <= 0 or margin <= 0:
        raise ValueError("need n_tasks >= 1, sd_d > 0, margin > 0")
    if multiplicity < 1:
        raise ValueError("multiplicity (family size) must be >= 1")
    effective_alpha = alpha / multiplicity
    se = sd_d / math.sqrt(n_tasks)
    return _NORMAL.cdf(
        (margin + true_difference) / se - z_quantile(1 - effective_alpha)
    )


def required_tasks_for_noninferiority(
    sd_d: float,
    margin: float,
    alpha: float = 0.05,
    power: float = 0.80,
    multiplicity: int = 1,
) -> int:
    """Tasks needed for one-sided non-inferiority at the target power.

    Uses the Bonferroni/Holm-first-step alpha/m per comparison — the
    family-wise worst case, conservative for the actual Holm procedure.
    """
    if not 0 < power < 1:
        raise ValueError("power must be in (0, 1)")
    if multiplicity < 1:
        raise ValueError("multiplicity (family size) must be >= 1")
    effective_alpha = alpha / multiplicity
    n = ((z_quantile(1 - effective_alpha) + z_quantile(power)) * sd_d / margin) ** 2
    return math.ceil(n)


def precision_half_width(
    sd_d: float, n_tasks: int, confidence: float = 0.95
) -> float:
    """Half-width of the normal-approx CI for the paired mean difference.

    Descriptive precision — multiplicity corrections do not apply to the
    reported CI itself.
    """
    if n_tasks < 1 or sd_d <= 0:
        raise ValueError("need n_tasks >= 1, sd_d > 0")
    tail = 1.0 - (1.0 - confidence) / 2.0
    return z_quantile(tail) * sd_d / math.sqrt(n_tasks)


def required_tasks_for_precision(
    sd_d: float, half_width: float, confidence: float = 0.95
) -> int:
    """Tasks needed to shrink the CI half-width below ``half_width``."""
    if half_width <= 0:
        raise ValueError("half_width must be positive")
    tail = 1.0 - (1.0 - confidence) / 2.0
    return math.ceil((z_quantile(tail) * sd_d / half_width) ** 2)


def required_tasks_two_sided(
    sd_d: float, delta: float, alpha: float = 0.05, power: float = 0.80,
    multiplicity: int = 1,
) -> int:
    """Tasks needed for a two-sided paired test of effect ``delta``.

    Uses the Bonferroni/Holm-first-step per-comparison alpha of
    ``alpha/(2m)`` (two-sided), conservative for the actual Holm procedure.
    """
    if delta <= 0:
        raise ValueError("delta must be positive")
    if multiplicity < 1:
        raise ValueError("multiplicity (family size) must be >= 1")
    effective_alpha = alpha / (2.0 * multiplicity)
    n = ((z_quantile(1 - effective_alpha) + z_quantile(power)) * sd_d / delta) ** 2
    return math.ceil(n)


def two_sided_power(
    n_tasks: int, sd_d: float, delta: float, alpha: float = 0.05,
    multiplicity: int = 1,
) -> float:
    """Approximate two-sided paired power for a true effect of ``delta``.

    Per-comparison alpha is Bonferroni/Holm-first-step ``alpha/(2m)``.
    """
    if n_tasks < 1 or sd_d <= 0:
        raise ValueError("need n_tasks >= 1, sd_d > 0")
    if multiplicity < 1:
        raise ValueError("multiplicity (family size) must be >= 1")
    effective_alpha = alpha / (2.0 * multiplicity)
    se = sd_d / math.sqrt(n_tasks)
    return _NORMAL.cdf(delta / se - z_quantile(1 - effective_alpha))


# -- Justification assembly ------------------------------------------------


def _planned_n_tasks(config: dict[str, Any]) -> int:
    samples = config.get("samples_per_benchmark", {})
    return sum(int(k) for k in samples.values())


def build_justification(
    config: dict[str, Any],
    archive_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """The transparent pre-run precision/power calculation.

    Combines (a) archived empirical paired-difference SDs, (b) a
    preregistered planning SD, (c) the independent-arm sensitivity bound and
    (d) the valid distribution-free paired bound, and reports — for the
    ACTUAL multiplicity families — the task counts the design requires vs the
    counts it plans. Confirmatory power is always computed at the
    Bonferroni/Holm-first-step alpha/m. Every quantity and formula is
    reported so a reviewer can recompute it.
    """
    power_cfg = config.get("power", {})
    ni_cfg = config["noninferiority"]
    margin = float(ni_cfg["margin"])
    alpha = float(ni_cfg["alpha"])
    target_power = float(power_cfg.get("target_power", 0.80))
    planning_sd = float(power_cfg["planning_sd"])
    trials_per_task = int(config["trials_per_task"])
    sensitivity_delta = float(power_cfg.get("sensitivity_delta", 0.10))

    paired_bound = worst_case_paired_sd(trials_per_task)
    independent_bound = independent_arm_sd(trials_per_task)

    # Multiplicity families, taken from the design itself:
    ni_m = len(ni_cfg["candidates"])            # Holm family per (regime, noninferiority)
    comparisons_m = len(config["comparisons"])   # Holm family per (regime, endpoint):
                                                # five global comparisons plus the
                                                # scoped H2 cluster comparison
    # The H2 cluster power calculation must describe the SAME test the runner
    # executes: the single scoped confirmatory comparison must equal
    # power.h2_cluster (comparison, benchmarks). Exploratory comparisons are
    # not part of any family and contribute nothing to m.
    scoped = [
        (tuple(entry[0:2]), tuple(entry[2]))
        for entry in config["comparisons"]
        if len(entry) == 3
    ]
    if len(scoped) != 1:
        raise ValueError(
            f"expected exactly one scoped (cluster) comparison, got {scoped}"
        )
    h2_cfg = power_cfg.get("h2_cluster", {})
    h2_pair = tuple(h2_cfg.get("comparison", []))
    h2_bench = tuple(h2_cfg.get("benchmarks", []))
    if scoped[0] != (h2_pair, h2_bench):
        raise ValueError(
            f"scoped comparison {scoped[0]} does not match power.h2_cluster "
            f"({h2_pair}, {list(h2_bench)}); the power calculation and the "
            "runner analysis must describe the same H2 test"
        )

    archive = archive_paired_sds(
        archive_paths or [Path(p) for p in power_cfg.get("archive_sources", [])]
        or DEFAULT_ARCHIVE_SOURCES,
        pairs=[tuple(str(part) for part in pair) for pair in power_cfg.get("archive_pairs", [])]
        or None,
    )
    pooled_sds = [
        pair_stats["sd_d"]
        for entry in archive["archives"]
        for pair_stats in entry["pooled"].values()
    ]
    per_bench_sds = [
        pair_stats["sd_d"]
        for entry in archive["archives"]
        for pair_stats in entry["per_benchmark_max"].values()
    ]
    empirical_pooled_max = max(pooled_sds) if pooled_sds else None
    empirical_benchmark_max = max(per_bench_sds) if per_bench_sds else None

    n_planned = _planned_n_tasks(config)
    cluster_cfg = power_cfg.get("h2_cluster", {})
    cluster_n = sum(
        int(config["samples_per_benchmark"][b]) for b in cluster_cfg.get("benchmarks", [])
    )
    cluster_delta = float(cluster_cfg.get("delta", 0.10))

    sd_scenarios = {
        "planning": planning_sd,
        "empirical_pooled_max": empirical_pooled_max,
        "empirical_benchmark_max": empirical_benchmark_max,
        "independent_arm_sensitivity": independent_bound,
        "paired_worst_case": paired_bound,
    }

    def _ni_block(sd_value):
        if sd_value is None:
            return None
        return {
            "sd_d": round(sd_value, 6),
            "required_n": required_tasks_for_noninferiority(
                sd_value, margin, alpha, target_power, multiplicity=ni_m
            ),
            "power": noninferiority_power(
                n_planned, sd_value, margin, alpha, multiplicity=ni_m
            ),
            "precision_half_width": precision_half_width(sd_value, n_planned),
            "precision_within_margin": precision_half_width(sd_value, n_planned) < margin,
        }

    def _two_sided_block(sd_value, n_tasks, delta, m):
        if sd_value is None:
            return None
        return {
            "sd_d": round(sd_value, 6),
            "required_n": required_tasks_two_sided(
                sd_value, delta, alpha, target_power, multiplicity=m
            ),
            "power": two_sided_power(n_tasks, sd_value, delta, alpha, multiplicity=m),
        }

    justification: dict[str, Any] = {
        "margin": margin,
        "alpha": alpha,
        "target_power": target_power,
        "trials_per_task": trials_per_task,
        "multiplicity": {
            "noninferiority_family_size": ni_m,
            "noninferiority_per_comparison_alpha": alpha / ni_m,
            "comparisons_family_size": comparisons_m,
            "comparisons_per_comparison_alpha_two_sided": alpha / (2 * comparisons_m),
            "comparisons_family_composition": (
                "five global comparisons + one scoped H2 cluster comparison "
                "(tahoe_full vs answer_only on the pooled bbh family); the "
                "global counterpart of the cluster test is exploratory and "
                "not in any family"
            ),
            "convention": "Bonferroni / Holm first step (alpha/m per comparison); "
            "conservative for the actual Holm step-down procedure",
        },
        "formulas": {
            "noninferiority_power": "Phi(margin / (sd_d/sqrt(n)) - z_{1-alpha/m})",
            "required_n_noninferiority": "ceil(((z_{1-alpha/m}+z_{power}) * sd_d / margin)^2)",
            "two_sided_power": "Phi(delta / (sd_d/sqrt(n)) - z_{1-alpha/(2m)})",
            "required_n_two_sided": "ceil(((z_{1-alpha/(2m)}+z_{power}) * sd_d / delta)^2)",
            "precision_half_width": "z_{1-(1-c)/2} * sd_d / sqrt(n)",
            "paired_worst_case_sd": "sqrt(1/trials_per_task)",
            "independent_arm_sd": "sqrt(1/(2*trials_per_task))",
        },
        "sd_assumptions": {
            "paired_worst_case": paired_bound,
            "independent_arm_sensitivity": independent_bound,
            "planning": planning_sd,
            "empirical_pooled_max": empirical_pooled_max,
            "empirical_benchmark_max": empirical_benchmark_max,
        },
        "planned": {
            "n_tasks": n_planned,
            "planned_trials": n_planned
            * len(config["arms"])
            * len(config["regimes"])
            * trials_per_task,
        },
        "noninferiority": {
            "by_sd_scenario": {
                name: _ni_block(sd) for name, sd in sd_scenarios.items()
            },
        },
        "comparisons_two_sided": {
            "delta": sensitivity_delta,
            "family_size": comparisons_m,
            "by_sd_scenario": {
                name: _two_sided_block(sd, n_planned, sensitivity_delta, comparisons_m)
                for name, sd in sd_scenarios.items()
            },
        },
        "h2_cluster": {
            "comparison": list(h2_pair),
            "benchmarks": cluster_cfg.get("benchmarks", []),
            "n_tasks": cluster_n,
            "delta": cluster_delta,
            "family_size": comparisons_m,
            "family": (
                "the scoped cluster comparison is one of the "
                f"{comparisons_m} confirmatory comparisons in each "
                "(regime, success) and (regime, total_tokens) family; its "
                "global counterpart is exploratory"
            ),
            "by_sd_scenario": {
                name: _two_sided_block(sd, cluster_n, cluster_delta, comparisons_m)
                for name, sd in sd_scenarios.items()
            },
        },
        "archive": archive,
    }

    ni_by = justification["noninferiority"]["by_sd_scenario"]
    cmp_by = justification["comparisons_two_sided"]["by_sd_scenario"]
    cl_by = justification["h2_cluster"]["by_sd_scenario"]

    justification["verdicts"] = {
        # Confirmatory scope under each SD scenario, at Holm-first-step alpha:
        "ni_powered_at_planning_sd": ni_by["planning"]["power"] >= target_power,
        "ni_powered_at_empirical_pooled_max": (
            ni_by["empirical_pooled_max"]["power"] >= target_power
            if ni_by["empirical_pooled_max"] else None
        ),
        "ni_powered_at_independent_arm_bound": ni_by[
            "independent_arm_sensitivity"
        ]["power"] >= target_power,
        "ni_powered_at_paired_worst_case": ni_by["paired_worst_case"][
            "power"
        ] >= target_power,
        "precision_within_margin_at_paired_worst_case": ni_by["paired_worst_case"][
            "precision_within_margin"
        ],
        "comparisons_powered_at_paired_worst_case": cmp_by["paired_worst_case"][
            "power"
        ] >= target_power,
        "h2_cluster_powered_at_planning_sd": cl_by["planning"]["power"] >= target_power,
        "h2_cluster_powered_at_independent_arm_bound": cl_by[
            "independent_arm_sensitivity"
        ]["power"] >= target_power,
        "h2_cluster_powered_at_paired_worst_case": cl_by["paired_worst_case"][
            "power"
        ] >= target_power,
    }
    return justification


def format_justification(j: dict[str, Any]) -> str:
    ni = j["noninferiority"]["by_sd_scenario"]
    cmp_by = j["comparisons_two_sided"]["by_sd_scenario"]
    cl = j["h2_cluster"]["by_sd_scenario"]
    mult = j["multiplicity"]
    lines = [
        "Precision / power justification for the structure-answer experiment",
        "=" * 72,
        f"margin={j['margin']}  one-sided alpha={j['alpha']}  target power="
        f"{j['target_power']}  trials/task={j['trials_per_task']}",
        f"multiplicity: NI family m={mult['noninferiority_family_size']} "
        f"(per-comparison alpha {mult['noninferiority_per_comparison_alpha']:.5f}); "
        f"comparisons family m={mult['comparisons_family_size']} "
        f"(two-sided per-comparison alpha {mult['comparisons_per_comparison_alpha_two_sided']:.5f})",
        f"convention: {mult['convention']}",
        "",
        "SD scenarios for the per-task paired success difference:",
        f"  planning SD                       : {j['sd_assumptions']['planning']:.4f}",
        f"  archived pooled empirical max     : {j['sd_assumptions']['empirical_pooled_max']}",
        f"  archived per-benchmark empirical max: {j['sd_assumptions']['empirical_benchmark_max']}",
        f"  independent-arm sensitivity       : {j['sd_assumptions']['independent_arm_sensitivity']:.4f} (NOT an upper bound)",
        f"  paired worst case sqrt(1/T)       : {j['sd_assumptions']['paired_worst_case']:.4f} (valid bound)",
        "",
        f"planned: {j['planned']['n_tasks']} tasks -> {j['planned']['planned_trials']} trials",
        "",
        f"non-inferiority (margin {j['margin']}, Holm-first-step alpha, "
        f"n={j['planned']['n_tasks']}):",
        f"{'scenario':34s} {'required_n':>10s} {'power':>8s} {'CI half':>8s}",
    ]
    for name, block in ni.items():
        lines.append(
            f"{name:34s} {block['required_n']:>10d} {block['power']:>8.3f} "
            f"{block['precision_half_width']:>8.4f}"
        )
    lines += [
        "",
        f"two-sided comparisons (delta={j['comparisons_two_sided']['delta']}, "
        f"m={j['comparisons_two_sided']['family_size']}, n={j['planned']['n_tasks']}):",
        f"{'scenario':34s} {'required_n':>10s} {'power':>8s}",
    ]
    for name, block in cmp_by.items():
        lines.append(
            f"{name:34s} {block['required_n']:>10d} {block['power']:>8.3f}"
        )
    lines += [
        "",
        f"H2 pooled cluster {j['h2_cluster']['benchmarks']} "
        f"(n={j['h2_cluster']['n_tasks']}, delta={j['h2_cluster']['delta']}, "
        f"m={j['h2_cluster']['family_size']}):",
        f"{'scenario':34s} {'required_n':>10s} {'power':>8s}",
    ]
    for name, block in cl.items():
        lines.append(
            f"{name:34s} {block['required_n']:>10d} {block['power']:>8.3f}"
        )
    lines += ["", "verdicts (confirmatory scope at Holm-first-step alpha):"]
    for key, value in j["verdicts"].items():
        lines.append(f"  {key}: {value}")
    lines += [
        "",
        "Explicit downgrade: non-inferiority and H2-cluster power are NOT",
        "claimed under the paired worst-case (anti-correlated) SD; the design",
        "is powered there only for precision and for two-sided comparisons.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print (and optionally write) the justification. No model calls."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUTPUT),
        help="path for the JSON justification artifact (empty string: print only)",
    )
    args = parser.parse_args(argv)

    import yaml

    config_path = Path(__file__).resolve().parent / "structure-answer.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    justification = build_justification(config)
    text = format_justification(justification)
    print(text)
    if args.out:
        out_path = Path(args.out)
        payload = json.dumps(justification, indent=2, sort_keys=True)
        # Derived design artifact (not an experiment result): regenerated
        # whenever the assumptions change, and the note makes that visible.
        if out_path.exists():
            out_path.write_text(payload, encoding="utf-8")
            print(f"\nupdated existing justification artifact: {out_path}")
        else:
            out_path.write_text(payload, encoding="utf-8")
            print(f"\nwrote justification artifact: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
