"""Statistical significance tests and effect sizes for benchmark comparisons.

Provides:
  - Bootstrap confidence intervals, including paired task-cluster intervals
  - Paired permutation and Wilcoxon signed-rank tests
  - Cohen's h effect size for proportion comparisons
  - Holm multiplicity correction and margin-based equivalence tests
  - generate_stats_report() — full stats report from trial data

Paired analyses use explicit (benchmark, task_id, trial) keys. Repeated
matched trials are averaged within each task, and tasks are the independent
units for resampling and significance tests. Input order is never used to
establish pairs.

Designed to work with trial dicts that have at minimum:
  task_id, benchmark, arm, passed, total_tokens, output_tokens, trial

No external dependencies beyond the standard library.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Bootstrap confidence interval
# ---------------------------------------------------------------------------

def bootstrap_ci(
    data: list[float],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Bootstrap confidence interval for the mean of *data*.

    Returns (point_estimate, lower_bound, upper_bound).

    Uses percentile method: sort the bootstrap means and take the
    alpha/2 and 1-alpha/2 percentiles.
    """
    if not data:
        return 0.0, 0.0, 0.0
    if len(data) == 1:
        v = float(data[0])
        return v, v, v

    rng = random.Random(seed)
    n = len(data)
    means = []
    for _ in range(n_resamples):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))

    means.sort()
    alpha = 1.0 - confidence
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples)
    hi_idx = min(hi_idx, n_resamples - 1)

    point = statistics.fmean(data)
    return point, means[lo_idx], means[hi_idx]


def bootstrap_ci_pass_rate(
    passed: list[bool],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Bootstrap CI for the pass rate (proportion) of boolean *passed* list."""
    data = [1.0 if p else 0.0 for p in passed]
    point, lo, hi = bootstrap_ci(data, n_resamples, confidence, seed)
    return point, lo, hi


def paired_bootstrap_ci(
    a: list[float],
    b: list[float],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Bootstrap CI for the mean paired difference ``a - b``.

    Pairs, rather than individual values, are resampled. When ``a`` and ``b``
    contain one aggregate per task, this is a task-cluster bootstrap.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Paired bootstrap requires equal-length sequences: len(a)={len(a)}, len(b)={len(b)}"
        )
    differences = [float(ai) - float(bi) for ai, bi in zip(a, b)]
    return bootstrap_ci(differences, n_resamples, confidence, seed)


# ---------------------------------------------------------------------------
# Explicit trial pairing and task aggregation
# ---------------------------------------------------------------------------

TrialKey = tuple[Any, Any, Any]
TaskKey = tuple[Any, Any]


def _trial_key(trial: dict) -> TrialKey:
    """Return the identity of a trial, rejecting incomplete identities."""
    missing = [key for key in ("benchmark", "task_id", "trial") if key not in trial]
    if missing:
        raise ValueError(f"Paired analysis requires trial key fields; missing {missing}")
    key = (trial["benchmark"], trial["task_id"], trial["trial"])
    if any(value is None for value in key):
        raise ValueError(f"Paired analysis key fields cannot be None: {key!r}")
    try:
        hash(key)
    except TypeError as exc:
        raise ValueError(f"Paired analysis key fields must be hashable: {key!r}") from exc
    return key


def _key_sort_key(key: tuple[Any, ...]) -> tuple[str, ...]:
    # Trial numbers are normally ints and IDs strings. Sorting their typed
    # representations also gives deterministic behavior for mixed ID types.
    return tuple(f"{type(value).__name__}:{value!r}" for value in key)


def pair_trials(
    trials_a: list[dict],
    trials_b: list[dict],
) -> list[tuple[dict, dict]]:
    """Pair trials by exact ``(benchmark, task_id, trial)`` identity.

    Only complete pairs are returned, sorted by key for order-independent
    analysis. Unmatched trials are deliberately excluded. Duplicate keys in
    either arm are ambiguous and raise ``ValueError`` instead of being paired
    positionally or forming a Cartesian product.
    """
    def index(trials: list[dict], arm: str) -> dict[TrialKey, dict]:
        indexed: dict[TrialKey, dict] = {}
        for trial in trials:
            key = _trial_key(trial)
            if key in indexed:
                raise ValueError(f"Duplicate trial key in {arm}: {key!r}")
            indexed[key] = trial
        return indexed

    indexed_a = index(trials_a, "arm_a")
    indexed_b = index(trials_b, "arm_b")
    common_keys = sorted(indexed_a.keys() & indexed_b.keys(), key=_key_sort_key)
    return [(indexed_a[key], indexed_b[key]) for key in common_keys]


def _trial_value(trial: dict, field: str) -> float:
    if field == "passed":
        return 1.0 if trial.get("passed", False) else 0.0
    value = trial.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Trial field {field!r} must be numeric, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"Trial field {field!r} must be finite, got {value!r}")
    return float(value)


def aggregate_trials_by_task(trials: list[dict], field: str) -> dict[TaskKey, float]:
    """Aggregate a numeric trial field to equally weighted task means."""
    grouped: dict[TaskKey, list[float]] = defaultdict(list)
    for trial in trials:
        benchmark, task_id, _ = _trial_key(trial)
        grouped[(benchmark, task_id)].append(_trial_value(trial, field))
    return {key: statistics.fmean(values) for key, values in grouped.items()}


def _paired_task_values(
    pairs: list[tuple[dict, dict]],
    field: str,
) -> tuple[list[TaskKey], list[float], list[float]]:
    grouped_a: dict[TaskKey, list[float]] = defaultdict(list)
    grouped_b: dict[TaskKey, list[float]] = defaultdict(list)
    for trial_a, trial_b in pairs:
        benchmark, task_id, _ = _trial_key(trial_a)
        task_key = (benchmark, task_id)
        grouped_a[task_key].append(_trial_value(trial_a, field))
        grouped_b[task_key].append(_trial_value(trial_b, field))
    keys = sorted(grouped_a, key=_key_sort_key)
    return (
        keys,
        [statistics.fmean(grouped_a[key]) for key in keys],
        [statistics.fmean(grouped_b[key]) for key in keys],
    )


def task_cluster_bootstrap_ci(
    trials_a: list[dict],
    trials_b: list[dict],
    field: str = "total_tokens",
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """CI for a paired task-mean difference from explicitly matched trials."""
    _, values_a, values_b = _paired_task_values(pair_trials(trials_a, trials_b), field)
    return paired_bootstrap_ci(values_a, values_b, n_resamples, confidence, seed)


# ---------------------------------------------------------------------------
# Paired permutation test
# ---------------------------------------------------------------------------

def paired_permutation_test(
    a: list[float],
    b: list[float],
    n_permutations: int = 10_000,
    seed: int | None = None,
) -> float:
    """Two-sided paired permutation test.

    Tests whether the mean difference (a - b) is significantly
    different from zero by randomly swapping pairs.

    *a* and *b* must have the same length — they are paired observations.

    Returns a p-value in [0, 1].
    """
    if len(a) != len(b):
        raise ValueError(
            f"Paired test requires equal-length sequences: len(a)={len(a)}, len(b)={len(b)}"
        )
    n = len(a)
    if n == 0:
        return 1.0
    if n == 1:
        return 1.0

    diffs = [ai - bi for ai, bi in zip(a, b)]
    observed = abs(sum(diffs))

    rng = random.Random(seed)
    count = 0
    for _ in range(n_permutations):
        flipped = sum(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(flipped) >= observed - 1e-12:
            count += 1

    return (count + 1) / (n_permutations + 1)


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank test
# ---------------------------------------------------------------------------

def wilcoxon_signed_rank(
    a: list[float],
    b: list[float],
) -> dict[str, Any]:
    """Wilcoxon signed-rank test for paired data.

    Tests whether the median difference (a - b) is significantly
    different from zero.  Uses the normal approximation for the
    test statistic when n >= 10 (with continuity correction),
    and an exact small-n fallback otherwise.

    Returns a dict with keys:
        w_stat   — Wilcoxon W statistic (sum of positive ranks)
        z_stat   — normal approximation z-score (None for tiny n)
        p_value  — two-sided p-value
        n        — number of non-zero differences
    """
    if len(a) != len(b):
        raise ValueError(
            f"Paired test requires equal-length sequences: len(a)={len(a)}, len(b)={len(b)}"
        )

    diffs = [ai - bi for ai, bi in zip(a, b)]
    nonzero = [(abs(d), d) for d in diffs if d != 0]
    n = len(nonzero)

    if n == 0:
        return {"w_stat": 0.0, "z_stat": None, "p_value": 1.0, "n": 0}

    nonzero.sort(key=lambda x: x[0])

    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and nonzero[j + 1][0] == nonzero[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    w_plus = sum(ranks[k] for k in range(n) if nonzero[k][1] > 0)
    w_minus = sum(ranks[k] for k in range(n) if nonzero[k][1] < 0)
    w_stat = min(w_plus, w_minus)

    if n < 10:
        from itertools import combinations

        total = 2 ** n
        count = 0
        for mask in range(total):
            s = 0.0
            for bit in range(n):
                if mask & (1 << bit):
                    s += ranks[bit]
            if s <= w_stat + 1e-12 or s >= w_plus - 1e-12:
                if s <= w_stat + 1e-12:
                    count += 1
        p_value = min(1.0, 2.0 * count / total)
        return {"w_stat": w_stat, "z_stat": None, "p_value": p_value, "n": n}

    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)

    if sigma == 0:
        return {"w_stat": w_stat, "z_stat": 0.0, "p_value": 1.0, "n": n}

    z = (w_stat - mu) / sigma
    p_value = _two_sided_normal_pvalue(z)

    return {
        "w_stat": w_stat,
        "z_stat": z,
        "p_value": p_value,
        "n": n,
    }


def _standard_normal_cdf(x: float) -> float:
    """Approximate the standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_sided_normal_pvalue(z: float) -> float:
    """Stable two-sided p-value for a standard-normal z statistic.

    Mathematically equal to ``2 * (1 - Phi(|z|))``, but computed in the
    survival-function form ``erfc(|z| / sqrt(2))``.  Evaluating
    ``2 * (1 - Phi(|z|))`` directly catastrophically cancels for large
    |z|: ``Phi(|z|)`` rounds to 1.0 and the p-value collapses to an
    impossible exact 0.0.  The erfc form keeps full relative precision
    in the far tail, so an asymptotic normal p-value is never exactly
    zero for any finite z.
    """
    return math.erfc(abs(z) / math.sqrt(2.0))


# ---------------------------------------------------------------------------
# Cohen's h effect size
# ---------------------------------------------------------------------------

def cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for the difference between two proportions.

    h = |2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))|

    Interpretation (Cohen 1988):
        0.2  — small effect
        0.5  — medium effect
        0.8  — large effect
    """
    if not (0.0 <= p1 <= 1.0) or not (0.0 <= p2 <= 1.0):
        raise ValueError(f"Proportions must be in [0, 1]: p1={p1}, p2={p2}")
    phi1 = 2.0 * math.asin(math.sqrt(p1))
    phi2 = 2.0 * math.asin(math.sqrt(p2))
    return abs(phi1 - phi2)


# ---------------------------------------------------------------------------
# Two-proportion z-test
# ---------------------------------------------------------------------------

def two_proportion_z_test(
    successes1: int,
    n1: int,
    successes2: int,
    n2: int,
) -> dict[str, float]:
    """Two-proportion z-test (pooled).

    Tests H0: p1 == p2 vs H1: p1 != p2.

    Returns a dict with z_stat and p_value (two-sided).
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("Sample sizes must be positive")
    p1 = successes1 / n1
    p2 = successes2 / n2
    pooled = (successes1 + successes2) / (n1 + n2)

    if pooled == 0 or pooled == 1:
        return {"z_stat": 0.0, "p_value": 1.0}

    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return {"z_stat": 0.0, "p_value": 1.0}

    z = (p1 - p2) / se
    # Survival form: 2*(1-Phi(|z|)) cancels to 0.0 for large |z|.
    p_value = _two_sided_normal_pvalue(z)

    return {"z_stat": z, "p_value": p_value}


# ---------------------------------------------------------------------------
# Multiplicity correction
# ---------------------------------------------------------------------------


def holm_adjust_pvalues(p_values: list[float]) -> list[float]:
    """Return Holm step-down adjusted p-values in the original order.

    Holm's correction controls the family-wise error rate without assuming
    independent tests. The adjusted values are monotone in the ordered raw
    p-values and never smaller than their corresponding raw values.
    """
    m = len(p_values)
    if m == 0:
        return []
    for p_value in p_values:
        if not math.isfinite(p_value) or not 0.0 <= p_value <= 1.0:
            raise ValueError(f"P-values must be finite and in [0, 1], got {p_value!r}")

    order = sorted(range(m), key=lambda index: p_values[index])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (m - rank) * p_values[index])
        running_max = max(running_max, value)
        adjusted[index] = running_max
    return adjusted


# ---------------------------------------------------------------------------
# Paired equivalence and non-inferiority tests
# ---------------------------------------------------------------------------


def _beta_continued_fraction(x: float, a: float, b: float) -> float:
    """Continued fraction used by the regularized incomplete beta function."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    result = d
    for m in range(1, 201):
        m2 = 2 * m
        numerator = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + numerator * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + numerator / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        result *= d * c

        numerator = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + numerator * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + numerator / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return result


def _regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(x, a, b) / a
    return 1.0 - front * _beta_continued_fraction(1.0 - x, b, a) / b


def _student_t_cdf(t_stat: float, df: int) -> float:
    """CDF of Student's t distribution using only the standard library."""
    x = df / (df + t_stat * t_stat)
    tail = 0.5 * _regularized_beta(x, df / 2.0, 0.5)
    return 1.0 - tail if t_stat >= 0.0 else tail


def _paired_mean_and_se(a: list[float], b: list[float]) -> tuple[list[float], float, float]:
    if len(a) != len(b):
        raise ValueError(
            f"Paired test requires equal-length sequences: len(a)={len(a)}, len(b)={len(b)}"
        )
    if len(a) < 2:
        raise ValueError("Margin tests require at least two paired observations")
    differences = [float(ai) - float(bi) for ai, bi in zip(a, b)]
    if not all(math.isfinite(value) for value in differences):
        raise ValueError("Paired observations must be finite")
    mean_difference = statistics.fmean(differences)
    std_error = statistics.stdev(differences) / math.sqrt(len(differences))
    return differences, mean_difference, std_error


def equivalence_test(
    a: list[float],
    b: list[float],
    margin: float,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Paired two-one-sided-tests (TOST) equivalence test.

    The estimand is ``mean(a - b)`` and the equivalence region is
    ``(-margin, +margin)``. ``margin`` is required and must be positive.
    The inputs should contain one independent aggregate per task.
    """
    if not math.isfinite(margin) or margin <= 0.0:
        raise ValueError("Equivalence margin must be finite and positive")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    differences, mean_difference, std_error = _paired_mean_and_se(a, b)
    df = len(differences) - 1

    if std_error == 0.0:
        p_lower = 0.0 if mean_difference > -margin else 1.0
        p_upper = 0.0 if mean_difference < margin else 1.0
        t_lower = None
        t_upper = None
    else:
        t_lower = (mean_difference + margin) / std_error
        t_upper = (mean_difference - margin) / std_error
        p_lower = 1.0 - _student_t_cdf(t_lower, df)
        p_upper = _student_t_cdf(t_upper, df)
    p_value = min(1.0, max(p_lower, p_upper))

    return {
        "mean_difference": mean_difference,
        "std_error": std_error,
        "df": df,
        "margin": margin,
        "t_lower": t_lower,
        "t_upper": t_upper,
        "p_lower": p_lower,
        "p_upper": p_upper,
        "p_value": p_value,
        "equivalent": p_value < alpha,
    }


def non_inferiority_test(
    a: list[float],
    b: list[float],
    margin: float,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """One-sided paired non-inferiority test with an explicit margin.

    Tests the null ``mean(a - b) <= -margin`` against the alternative that
    ``a`` is no worse than ``b`` by more than ``margin``. Inputs should
    contain one independent aggregate per task.
    """
    if not math.isfinite(margin) or margin < 0.0:
        raise ValueError("Non-inferiority margin must be finite and non-negative")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    differences, mean_difference, std_error = _paired_mean_and_se(a, b)
    df = len(differences) - 1

    if std_error == 0.0:
        p_value = 0.0 if mean_difference > -margin else 1.0
        t_stat = None
    else:
        t_stat = (mean_difference + margin) / std_error
        p_value = 1.0 - _student_t_cdf(t_stat, df)

    return {
        "mean_difference": mean_difference,
        "std_error": std_error,
        "df": df,
        "margin": margin,
        "t_stat": t_stat,
        "p_value": p_value,
        "non_inferior": p_value < alpha,
    }


# ---------------------------------------------------------------------------
# Full stats report
# ---------------------------------------------------------------------------

def generate_stats_report(
    trials: list[dict],
    n_resamples: int = 10_000,
    n_permutations: int = 10_000,
    seed: int = 42,
    include_per_task: bool = True,
) -> dict[str, Any]:
    """Generate an order-independent statistical report from trial data.

    Expects trial dicts with keys:
        task_id, benchmark, arm, passed, trial, total_tokens, output_tokens

    Comparisons retain only exact ``(benchmark, task_id, trial)`` matches.
    Matched repeated trials are averaged within tasks before paired tests and
    task-cluster bootstrap CIs are calculated. Holm-adjusted p-values correct
    each test family across the benchmark/arm comparisons.

    ``include_per_task`` (default True) controls whether the keyed per-task
    comparisons are computed at all.  Each task triggers a full paired
    comparison (bootstraps, permutations, Wilcoxon), which dominates the
    runtime on large archives — tens of thousands of tasks — so callers
    that discard ``per_task`` should pass False and skip the work instead
    of paying for it and throwing it away.

    Returns a nested dict suitable for JSON serialization.
    """
    if not trials:
        return {"groups": {}, "comparisons": {}, "per_task": {}}

    groups: dict[tuple[Any, str], list[dict]] = defaultdict(list)
    task_groups: dict[tuple[Any, Any, str], list[dict]] = defaultdict(list)
    for trial in trials:
        benchmark, task_id, _ = _trial_key(trial)
        arm = trial.get("arm", "unknown")
        groups[(benchmark, arm)].append(trial)
        task_groups[(benchmark, task_id, arm)].append(trial)

    arms = sorted({arm for _, arm in groups})
    benchmarks = sorted({benchmark for benchmark, _ in groups}, key=lambda value: str(value))

    # Group estimates and CIs treat tasks, not repeated trials, as clusters.
    group_stats: dict[str, dict] = {}
    for (benchmark, arm) in sorted(groups, key=lambda key: (str(key[0]), key[1])):
        group_trials = groups[(benchmark, arm)]
        passed_by_task = aggregate_trials_by_task(group_trials, "passed")
        tokens_by_task = aggregate_trials_by_task(group_trials, "total_tokens")
        output_by_task = aggregate_trials_by_task(group_trials, "output_tokens")
        task_keys = sorted(passed_by_task, key=_key_sort_key)
        passed = [passed_by_task[key] for key in task_keys]
        tokens = [tokens_by_task[key] for key in task_keys]
        output_tokens = [output_by_task[key] for key in task_keys]

        pr_point, pr_lo, pr_hi = bootstrap_ci(
            passed, n_resamples=n_resamples, seed=seed,
        )
        tok_point, tok_lo, tok_hi = bootstrap_ci(
            tokens, n_resamples=n_resamples, seed=seed,
        )
        group_stats[f"{benchmark}/{arm}"] = {
            "n": len(group_trials),
            "n_tasks": len(passed),
            "pass_rate": pr_point,
            "pass_rate_ci": [pr_lo, pr_hi],
            "mean_tokens": tok_point,
            "mean_tokens_ci": [tok_lo, tok_hi],
            "mean_output_tokens": statistics.fmean(output_tokens) if output_tokens else 0.0,
            "n_passed": sum(1 for trial in group_trials if trial.get("passed", False)),
        }

    comparisons: dict[str, dict] = {}
    for benchmark in benchmarks:
        for index, arm_a in enumerate(arms):
            for arm_b in arms[index + 1:]:
                trials_a = groups.get((benchmark, arm_a), [])
                trials_b = groups.get((benchmark, arm_b), [])
                if not trials_a or not trials_b:
                    continue
                key = f"{benchmark}/{arm_a}_vs_{arm_b}"
                comparisons[key] = _compare_groups(
                    trials_a, trials_b, arm_a, arm_b,
                    n_resamples, n_permutations, seed,
                )

    # Correct each inferential family across all reported arm comparisons.
    for field, adjusted_field in (
        ("permutation_p", "permutation_p_holm"),
        ("pass_rate_permutation_p", "pass_rate_permutation_p_holm"),
    ):
        keys = list(comparisons)
        adjusted = holm_adjust_pvalues([comparisons[key][field] for key in keys])
        for key, p_value in zip(keys, adjusted):
            comparisons[key][adjusted_field] = p_value
    for test_name in ("z_test", "wilcoxon"):
        keys = list(comparisons)
        adjusted = holm_adjust_pvalues([
            comparisons[key][test_name]["p_value"] for key in keys
        ])
        for key, p_value in zip(keys, adjusted):
            comparisons[key][test_name]["p_value_holm"] = p_value

    # Include the benchmark in per-task keys so equal task IDs in different
    # benchmarks cannot overwrite one another or be paired across benchmarks.
    # Skippable: one full paired comparison per task dominates the runtime on
    # large archives, so callers that discard per_task skip the work here.
    per_task: dict[str, dict] = {}
    if include_per_task:
        task_ids = sorted(
            {(benchmark, task_id) for benchmark, task_id, _ in task_groups},
            key=_key_sort_key,
        )
        for benchmark, task_id in task_ids:
            for index, arm_a in enumerate(arms):
                for arm_b in arms[index + 1:]:
                    trials_a = task_groups.get((benchmark, task_id, arm_a), [])
                    trials_b = task_groups.get((benchmark, task_id, arm_b), [])
                    if not trials_a or not trials_b:
                        continue
                    key = f"{benchmark}/{task_id}/{arm_a}_vs_{arm_b}"
                    comparison = _compare_groups(
                        trials_a, trials_b, arm_a, arm_b,
                        n_resamples, n_permutations, seed,
                    )
                    comparison["benchmark"] = benchmark
                    comparison["task_id"] = task_id
                    per_task[key] = comparison

    return {
        "groups": group_stats,
        "comparisons": comparisons,
        "per_task": per_task,
        "multiplicity": {
            "method": "holm",
            "family": "comparisons",
            "corrected_fields": [
                "permutation_p_holm",
                "pass_rate_permutation_p_holm",
                "z_test.p_value_holm",
                "wilcoxon.p_value_holm",
            ],
        },
    }


def _paired_task_z_test(a: list[float], b: list[float]) -> dict[str, Any]:
    """Normal approximation for a task-level paired mean difference."""
    if len(a) != len(b):
        raise ValueError("Paired task values must have equal lengths")
    n = len(a)
    if n < 2:
        return {"z_stat": None, "p_value": 1.0, "n": n, "method": "paired_task_mean_z"}
    differences = [ai - bi for ai, bi in zip(a, b)]
    mean_difference = statistics.fmean(differences)
    std_error = statistics.stdev(differences) / math.sqrt(n)
    if std_error == 0.0:
        return {
            "z_stat": None,
            "p_value": 1.0 if mean_difference == 0.0 else 0.0,
            "n": n,
            "method": "paired_task_mean_z",
        }
    z_stat = mean_difference / std_error
    # Survival form: 2*(1-Phi(|z|)) cancels to 0.0 for large |z|.
    p_value = _two_sided_normal_pvalue(z_stat)
    return {
        "z_stat": z_stat,
        "p_value": p_value,
        "n": n,
        "method": "paired_task_mean_z",
    }


def _compare_groups(
    ga: list[dict],
    gb: list[dict],
    arm_a: str,
    arm_b: str,
    n_resamples: int,
    n_permutations: int,
    seed: int,
) -> dict[str, Any]:
    """Compare explicitly paired trials after within-task aggregation."""
    pairs = pair_trials(ga, gb)
    task_keys, passed_a, passed_b = _paired_task_values(pairs, "passed")
    _, tokens_a, tokens_b = _paired_task_values(pairs, "total_tokens")

    p_a = statistics.fmean(passed_a) if passed_a else 0.0
    p_b = statistics.fmean(passed_b) if passed_b else 0.0
    token_difference = paired_bootstrap_ci(
        tokens_a, tokens_b, n_resamples=n_resamples, seed=seed,
    )
    pass_difference = paired_bootstrap_ci(
        passed_a, passed_b, n_resamples=n_resamples, seed=seed,
    )
    permutation_p = paired_permutation_test(
        tokens_a, tokens_b, n_permutations=n_permutations, seed=seed,
    )
    pass_permutation_p = paired_permutation_test(
        passed_a, passed_b, n_permutations=n_permutations, seed=seed,
    )

    return {
        "arm_a": arm_a,
        "arm_b": arm_b,
        "n_a": len(ga),
        "n_b": len(gb),
        "n_pairs": len(pairs),
        "n_tasks": len(task_keys),
        "n_unmatched_a": len(ga) - len(pairs),
        "n_unmatched_b": len(gb) - len(pairs),
        "pairing_key": ["benchmark", "task_id", "trial"],
        "pass_rate_a": p_a,
        "pass_rate_b": p_b,
        "pass_rate_difference": pass_difference[0],
        "pass_rate_difference_ci": [pass_difference[1], pass_difference[2]],
        "mean_token_difference": token_difference[0],
        "mean_token_difference_ci": [token_difference[1], token_difference[2]],
        "cohens_h": cohens_h(p_a, p_b),
        "z_test": _paired_task_z_test(passed_a, passed_b),
        "permutation_p": permutation_p,
        "pass_rate_permutation_p": pass_permutation_p,
        "wilcoxon": wilcoxon_signed_rank(tokens_a, tokens_b),
    }
