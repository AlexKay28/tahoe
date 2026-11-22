"""Tests for benchmarks/stats.py — bootstrap CIs, permutation tests,
Wilcoxon signed-rank, Cohen's h, and generate_stats_report.

Fast by construction: tests use small sample sizes and few resamples
to stay well under the suite's time budget.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.stats import (
    _standard_normal_cdf,
    _two_sided_normal_pvalue,
    bootstrap_ci,
    bootstrap_ci_pass_rate,
    aggregate_trials_by_task,
    cohens_h,
    equivalence_test,
    generate_stats_report,
    holm_adjust_pvalues,
    non_inferiority_test,
    paired_bootstrap_ci,
    paired_permutation_test,
    pair_trials,
    task_cluster_bootstrap_ci,
    two_proportion_z_test,
    wilcoxon_signed_rank,
)


# -- Bootstrap CI --------------------------------------------------------


def test_bootstrap_ci_returns_point_estimate():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    point, lo, hi = bootstrap_ci(data, n_resamples=1000, seed=42)
    assert point == pytest.approx(3.0)
    assert lo <= point <= hi


def test_bootstrap_ci_empty_returns_zeros():
    point, lo, hi = bootstrap_ci([])
    assert (point, lo, hi) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_single_element():
    point, lo, hi = bootstrap_ci([42.0])
    assert point == 42.0
    assert lo == 42.0
    assert hi == 42.0


def test_bootstrap_ci_brackets_mean():
    data = [10.0] * 50 + [20.0] * 50
    point, lo, hi = bootstrap_ci(data, n_resamples=5000, seed=42)
    assert point == pytest.approx(15.0)
    assert lo < 15.0
    assert hi > 15.0
    assert lo > 10.0
    assert hi < 20.0


def test_bootstrap_ci_is_deterministic_with_seed():
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    r1 = bootstrap_ci(data, n_resamples=1000, seed=123)
    r2 = bootstrap_ci(data, n_resamples=1000, seed=123)
    assert r1 == r2


def test_bootstrap_ci_confidence_level_widens_interval():
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    _, lo90, hi90 = bootstrap_ci(data, n_resamples=5000, seed=42, confidence=0.90)
    _, lo99, hi99 = bootstrap_ci(data, n_resamples=5000, seed=42, confidence=0.99)
    assert lo99 <= lo90
    assert hi99 >= hi90


# -- Bootstrap CI pass rate ---------------------------------------------


def test_bootstrap_ci_pass_rate_all_pass():
    point, lo, hi = bootstrap_ci_pass_rate([True] * 20, n_resamples=1000, seed=42)
    assert point == 1.0
    assert lo == 1.0
    assert hi == 1.0


def test_bootstrap_ci_pass_rate_all_fail():
    point, lo, hi = bootstrap_ci_pass_rate([False] * 20, n_resamples=1000, seed=42)
    assert point == 0.0
    assert lo == 0.0
    assert hi == 0.0


def test_bootstrap_ci_pass_rate_half():
    passed = [True] * 50 + [False] * 50
    point, lo, hi = bootstrap_ci_pass_rate(passed, n_resamples=5000, seed=42)
    assert point == pytest.approx(0.5)
    assert 0.3 < lo < 0.5
    assert 0.5 < hi < 0.7


# -- Paired permutation test --------------------------------------------


def test_permutation_test_identical_returns_high_p():
    a = [5.0, 6.0, 7.0, 8.0, 9.0]
    p = paired_permutation_test(a, a, n_permutations=2000, seed=42)
    assert p > 0.5


def test_permutation_test_large_effect_low_p():
    a = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p = paired_permutation_test(a, b, n_permutations=5000, seed=42)
    assert p < 0.05


def test_permutation_test_unequal_length_raises():
    with pytest.raises(ValueError, match="equal-length"):
        paired_permutation_test([1, 2, 3], [1, 2])


def test_permutation_test_empty_returns_one():
    assert paired_permutation_test([], []) == 1.0


def test_permutation_test_single_pair_returns_one():
    assert paired_permutation_test([5.0], [3.0]) == 1.0


def test_permutation_test_deterministic_with_seed():
    a = [5.0, 6.0, 7.0, 8.0]
    b = [1.0, 2.0, 3.0, 4.0]
    p1 = paired_permutation_test(a, b, n_permutations=1000, seed=99)
    p2 = paired_permutation_test(a, b, n_permutations=1000, seed=99)
    assert p1 == p2


# -- Wilcoxon signed-rank test ------------------------------------------


def test_wilcoxon_identical_returns_p_one():
    result = wilcoxon_signed_rank([5.0, 6.0, 7.0], [5.0, 6.0, 7.0])
    assert result["p_value"] == 1.0
    assert result["n"] == 0


def test_wilcoxon_large_effect_low_p():
    a = [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    result = wilcoxon_signed_rank(a, b)
    assert result["p_value"] < 0.05
    assert result["z_stat"] is not None
    assert result["n"] == 10


def test_wilcoxon_all_zero_diffs():
    result = wilcoxon_signed_rank([3.0, 3.0], [3.0, 3.0])
    assert result["p_value"] == 1.0
    assert result["n"] == 0


def test_wilcoxon_unequal_length_raises():
    with pytest.raises(ValueError, match="equal-length"):
        wilcoxon_signed_rank([1, 2, 3], [1, 2])


def test_wilcoxon_small_n_exact():
    result = wilcoxon_signed_rank([10.0, 20.0, 30.0], [1.0, 2.0, 3.0])
    assert result["n"] == 3
    assert 0.0 < result["p_value"] <= 1.0
    assert result["z_stat"] is None


def test_wilcoxon_returns_dict_with_expected_keys():
    result = wilcoxon_signed_rank([1.0, 2.0, 3.0, 4.0], [0.5, 1.0, 1.5, 2.0])
    assert set(result) == {"w_stat", "z_stat", "p_value", "n"}


def test_wilcoxon_ties_handled():
    a = [2.0, 2.0, 4.0, 6.0]
    b = [1.0, 1.0, 1.0, 1.0]
    result = wilcoxon_signed_rank(a, b)
    assert result["n"] == 4
    assert 0.0 < result["p_value"] <= 1.0


def test_wilcoxon_large_z_p_value_nonzero_and_accurate():
    # n=100 constant differences give |z| ~ 8.68, deep in the regime where
    # 2*(1-CDF) catastrophically cancels to an impossible exact 0.0.
    a = [100.0 + i for i in range(100)]
    b = [float(i) for i in range(100)]
    result = wilcoxon_signed_rank(a, b)
    z = result["z_stat"]
    assert z is not None
    assert abs(z) > 8.0
    # Guard that this really is the cancellation regime being exercised.
    assert 2.0 * (1.0 - _standard_normal_cdf(abs(z))) == 0.0
    p = result["p_value"]
    # Tiny, but never an impossible exact zero.
    assert 0.0 < p < 1e-15
    assert p == pytest.approx(math.erfc(abs(z) / math.sqrt(2.0)))
    assert p == pytest.approx(_two_sided_normal_pvalue(z))


def test_wilcoxon_moderate_z_agrees_with_cdf_form():
    # Normal regime preserved: the stable survival form matches the
    # textbook 2*(1-CDF) expression to full working precision.
    a = [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    result = wilcoxon_signed_rank(a, b)
    z = result["z_stat"]
    assert 0.0 < result["p_value"] < 1.0
    assert result["p_value"] == pytest.approx(
        2.0 * (1.0 - _standard_normal_cdf(abs(z))), rel=1e-12,
    )


# -- Cohen's h -----------------------------------------------------------


def test_cohens_h_zero_when_equal():
    assert cohens_h(0.5, 0.5) == pytest.approx(0.0, abs=1e-10)


def test_cohens_h_known_value():
    h = cohens_h(0.8, 0.6)
    expected = abs(2 * __import__("math").asin(__import__("math").sqrt(0.8))
                   - 2 * __import__("math").asin(__import__("math").sqrt(0.6)))
    assert h == pytest.approx(expected)


def test_cohens_h_extreme_proportions():
    h = cohens_h(0.0, 1.0)
    assert h == pytest.approx(__import__("math").pi, abs=1e-6)


def test_cohens_h_out_of_range_raises():
    with pytest.raises(ValueError):
        cohens_h(-0.1, 0.5)
    with pytest.raises(ValueError):
        cohens_h(0.5, 1.1)


def test_cohens_h_symmetric():
    assert cohens_h(0.9, 0.3) == pytest.approx(cohens_h(0.3, 0.9))


# -- Two-proportion z-test -----------------------------------------------


def test_z_test_identical_proportions():
    result = two_proportion_z_test(10, 20, 10, 20)
    assert result["z_stat"] == pytest.approx(0.0)
    assert result["p_value"] == pytest.approx(1.0)


def test_z_test_large_effect_significant():
    result = two_proportion_z_test(90, 100, 10, 100)
    assert result["p_value"] < 0.05
    assert result["z_stat"] > 0


def test_z_test_all_pass():
    result = two_proportion_z_test(20, 20, 20, 20)
    assert result["p_value"] == 1.0


def test_z_test_all_fail():
    result = two_proportion_z_test(0, 20, 0, 20)
    assert result["p_value"] == 1.0


def test_z_test_zero_n_raises():
    with pytest.raises(ValueError):
        two_proportion_z_test(1, 0, 1, 10)


def test_z_test_large_z_p_value_nonzero_and_accurate():
    # All-success vs all-failure: z = 20, where 2*(1-CDF) cancels to an
    # impossible exact 0.0 while the true two-sided tail is ~5.5e-89.
    result = two_proportion_z_test(200, 200, 0, 200)
    z = result["z_stat"]
    assert abs(z) > 8.0
    # Guard: this case sits squarely in the cancellation regime.
    assert 2.0 * (1.0 - _standard_normal_cdf(abs(z))) == 0.0
    p = result["p_value"]
    assert 0.0 < p < 1e-80  # tiny but never an impossible exact zero
    assert p == pytest.approx(math.erfc(abs(z) / math.sqrt(2.0)))
    assert p == pytest.approx(math.erfc(20.0 / math.sqrt(2.0)))


def test_z_test_moderate_z_agrees_with_cdf_form():
    # Normal regime preserved: 60% vs 40% gives z ~ 2.83, no cancellation.
    result = two_proportion_z_test(60, 100, 40, 100)
    z = result["z_stat"]
    assert 0.0 < result["p_value"] < 1.0
    assert result["p_value"] == pytest.approx(
        2.0 * (1.0 - _standard_normal_cdf(abs(z))), rel=1e-12,
    )


# -- _standard_normal_cdf ------------------------------------------------


def test_standard_normal_cdf_zero():
    assert _standard_normal_cdf(0.0) == pytest.approx(0.5)


def test_standard_normal_cdf_symmetry():
    for x in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        cdf_x = _standard_normal_cdf(x)
        cdf_neg = _standard_normal_cdf(-x)
        assert cdf_x + cdf_neg == pytest.approx(1.0)


def test_standard_normal_cdf_extremes():
    assert _standard_normal_cdf(-5.0) < 1e-6
    assert _standard_normal_cdf(5.0) > 1.0 - 1e-6


def test_two_sided_normal_pvalue_agrees_with_cdf_form_for_moderate_z():
    # For moderate |z| the stable survival form equals 2*(1-CDF(|z|)).
    for z in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0):
        assert _two_sided_normal_pvalue(z) == pytest.approx(
            2.0 * (1.0 - _standard_normal_cdf(abs(z))), rel=1e-9,
        )
        assert _two_sided_normal_pvalue(-z) == _two_sided_normal_pvalue(z)


def test_two_sided_normal_pvalue_nonzero_in_far_tail():
    # z = 10: 2*(1-CDF) cancels to exactly 0.0; the erfc form keeps
    # the known reference value ~1.524e-23 with full relative precision.
    p = _two_sided_normal_pvalue(10.0)
    assert 2.0 * (1.0 - _standard_normal_cdf(10.0)) == 0.0
    assert 0.0 < p < 1e-20
    assert p == pytest.approx(1.523970604832667e-23, rel=1e-9)


# -- generate_stats_report -----------------------------------------------


def _make_trials():
    """Build a small synthetic trial set with two arms."""
    trials = []
    for task_id in ["t1", "t2", "t3"]:
        for arm in ["classic", "tahoe"]:
            for k in range(10):
                if arm == "tahoe":
                    passed = k < 8
                    tokens = 100 + k * 10
                else:
                    passed = k < 5
                    tokens = 200 + k * 10
                trials.append({
                    "task_id": task_id,
                    "benchmark": "bench_a",
                    "arm": arm,
                    "trial": k,
                    "passed": passed,
                    "total_tokens": tokens,
                    "output_tokens": tokens // 2,
                    "input_tokens": tokens // 2,
                })
    return trials


def test_generate_stats_report_empty():
    report = generate_stats_report([])
    assert report == {"groups": {}, "comparisons": {}, "per_task": {}}


def test_generate_stats_report_has_groups():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=42)
    assert "bench_a/classic" in report["groups"]
    assert "bench_a/tahoe" in report["groups"]


def test_generate_stats_report_group_stats():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=42)
    g = report["groups"]["bench_a/tahoe"]
    assert g["n"] == 30
    assert g["pass_rate"] == pytest.approx(0.8)
    assert g["n_passed"] == 24
    assert g["pass_rate_ci"][0] <= g["pass_rate"] <= g["pass_rate_ci"][1]
    assert g["mean_tokens"] > 0
    assert g["mean_tokens_ci"][0] <= g["mean_tokens"] <= g["mean_tokens_ci"][1]


def test_generate_stats_report_has_comparisons():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=42)
    assert "bench_a/classic_vs_tahoe" in report["comparisons"]


def test_generate_stats_report_comparison_fields():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=42)
    comp = report["comparisons"]["bench_a/classic_vs_tahoe"]
    assert comp["arm_a"] == "classic"
    assert comp["arm_b"] == "tahoe"
    assert comp["pass_rate_a"] == pytest.approx(0.5)
    assert comp["pass_rate_b"] == pytest.approx(0.8)
    assert comp["cohens_h"] > 0
    assert "z_stat" in comp["z_test"]
    assert "p_value" in comp["z_test"]
    assert 0.0 < comp["permutation_p"] <= 1.0
    assert "p_value" in comp["wilcoxon"]


def test_generate_stats_report_per_task():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=42)
    assert "bench_a/t1/classic_vs_tahoe" in report["per_task"]
    assert "bench_a/t2/classic_vs_tahoe" in report["per_task"]
    assert "bench_a/t3/classic_vs_tahoe" in report["per_task"]


def test_generate_stats_report_default_includes_per_task():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=200, n_permutations=200, seed=42)
    # Public default is unchanged: per-task comparisons are computed.
    assert set(report["per_task"]) == {
        "bench_a/t1/classic_vs_tahoe",
        "bench_a/t2/classic_vs_tahoe",
        "bench_a/t3/classic_vs_tahoe",
    }


def test_generate_stats_report_include_per_task_false_matches_default():
    trials = _make_trials()
    options = dict(n_resamples=200, n_permutations=200, seed=42)
    on = generate_stats_report(trials, **options)
    off = generate_stats_report(trials, include_per_task=False, **options)
    # per_task is empty, but nothing else changes.
    assert off["per_task"] == {}
    assert {k: v for k, v in off.items() if k != "per_task"} == {
        k: v for k, v in on.items() if k != "per_task"
    }
    assert off["multiplicity"] == on["multiplicity"]


def test_generate_stats_report_false_skips_per_task_compare_calls(monkeypatch):
    import benchmarks.stats as stats_module

    calls = []
    original = stats_module._compare_groups

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(stats_module, "_compare_groups", spy)
    trials = _make_trials()
    options = dict(n_resamples=100, n_permutations=100, seed=42)

    generate_stats_report(trials, include_per_task=False, **options)
    # Only the single benchmark-level comparison runs; the 3 tasks would
    # otherwise add 3 per-task _compare_groups calls.
    assert len(calls) == 1

    generate_stats_report(trials, **options)  # default: include_per_task=True
    # 1 benchmark-level call from the first run + 1 benchmark-level and
    # 3 per-task calls from the second.
    assert len(calls) == 1 + 1 + 3


def test_generate_stats_report_large_effect_significant():
    trials = _make_trials()
    report = generate_stats_report(trials, n_resamples=1000, n_permutations=2000, seed=42)
    comp = report["comparisons"]["bench_a/classic_vs_tahoe"]
    assert comp["cohens_h"] > 0.2
    assert comp["z_test"]["p_value"] < 0.05


def test_generate_stats_report_deterministic():
    trials = _make_trials()
    r1 = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=77)
    r2 = generate_stats_report(trials, n_resamples=500, n_permutations=500, seed=77)
    assert r1 == r2


def test_generate_stats_report_three_arms():
    trials = []
    for task_id in ["t1"]:
        for arm in ["classic", "tahoe", "baseline"]:
            for k in range(10):
                passed = (k + hash(arm)) % 3 != 0
                tokens = 100 + k * 20
                trials.append({
                    "task_id": task_id,
                    "benchmark": "bench_x",
                    "arm": arm,
                    "trial": k,
                    "passed": passed,
                    "total_tokens": tokens,
                    "output_tokens": tokens // 2,
                    "input_tokens": tokens // 2,
                })
    report = generate_stats_report(trials, n_resamples=300, n_permutations=300, seed=42)
    assert len(report["comparisons"]) == 3
    assert "bench_x/baseline_vs_classic" in report["comparisons"]
    assert "bench_x/baseline_vs_tahoe" in report["comparisons"]
    assert "bench_x/classic_vs_tahoe" in report["comparisons"]


# -- Keyed pairing and task-cluster inference ------------------------------


def _trial(arm, trial, tokens, *, benchmark="bench", task_id="task", passed=True):
    return {
        "benchmark": benchmark,
        "task_id": task_id,
        "trial": trial,
        "arm": arm,
        "passed": passed,
        "total_tokens": tokens,
        "output_tokens": tokens // 2,
    }


def test_pair_trials_uses_full_key_not_input_position():
    trials_a = [
        _trial("a", 1, 100, task_id="t1"),
        _trial("a", 0, 200, task_id="t1"),
        _trial("a", 0, 300, task_id="t2"),
    ]
    trials_b = [
        _trial("b", 0, 30, task_id="t2"),
        _trial("b", 0, 20, task_id="t1"),
        _trial("b", 1, 10, task_id="t1"),
    ]
    pairs = pair_trials(trials_a, trials_b)
    assert [(a["task_id"], a["trial"], a["total_tokens"], b["total_tokens"])
            for a, b in pairs] == [
        ("t1", 0, 200, 20),
        ("t1", 1, 100, 10),
        ("t2", 0, 300, 30),
    ]


def test_pair_trials_excludes_missing_trials_and_rejects_duplicates():
    trials_a = [_trial("a", 0, 10), _trial("a", 1, 20)]
    assert len(pair_trials(trials_a, [_trial("b", 1, 25)])) == 1
    with pytest.raises(ValueError, match="Duplicate trial key"):
        pair_trials([trials_a[0], trials_a[0]], [_trial("b", 0, 10)])
    with pytest.raises(ValueError, match="missing.*trial"):
        pair_trials([{"benchmark": "bench", "task_id": "task"}], [])


def test_pair_trials_benchmark_is_part_of_identity():
    trials_a = [_trial("a", 0, 10, benchmark="bench_a")]
    trials_b = [_trial("b", 0, 20, benchmark="bench_b")]
    assert pair_trials(trials_a, trials_b) == []


def test_aggregate_trials_by_task_averages_repeated_trials():
    trials = [
        _trial("a", 0, 10, task_id="t1"),
        _trial("a", 1, 30, task_id="t1"),
        _trial("a", 0, 50, task_id="t2"),
    ]
    assert aggregate_trials_by_task(trials, "total_tokens") == {
        ("bench", "t1"): 20.0,
        ("bench", "t2"): 50.0,
    }


def test_paired_bootstrap_ci_resamples_differences():
    a = [10.0, 20.0, 30.0]
    b = [5.0, 15.0, 25.0]
    point, lo, hi = paired_bootstrap_ci(a, b, n_resamples=500, seed=42)
    assert (point, lo, hi) == (5.0, 5.0, 5.0)
    with pytest.raises(ValueError, match="equal-length"):
        paired_bootstrap_ci([1.0], [])


def test_task_cluster_bootstrap_uses_matched_within_task_means():
    trials_a = [
        _trial("a", 0, 100, task_id="t1"),
        _trial("a", 1, 200, task_id="t1"),
        _trial("a", 0, 300, task_id="t2"),
        _trial("a", 1, 1000, task_id="t2"),  # unmatched: excluded
    ]
    trials_b = [
        _trial("b", 1, 150, task_id="t1"),
        _trial("b", 0, 120, task_id="t1"),
        _trial("b", 0, 280, task_id="t2"),
    ]
    point, lo, hi = task_cluster_bootstrap_ci(
        trials_a, trials_b, n_resamples=500, seed=42,
    )
    # t1: mean(100, 200) - mean(120, 150) = 15; t2: 300 - 280 = 20.
    assert point == pytest.approx(17.5)
    assert lo <= point <= hi


def test_report_is_invariant_to_shuffled_asynchronous_input():
    trials = [
        _trial("a", 0, 100, task_id="t1", passed=True),
        _trial("a", 1, 200, task_id="t1", passed=False),
        _trial("a", 0, 300, task_id="t2", passed=True),
        _trial("a", 1, 1000, task_id="t2", passed=True),
        _trial("b", 1, 150, task_id="t1", passed=True),
        _trial("b", 0, 120, task_id="t1", passed=True),
        _trial("b", 0, 280, task_id="t2", passed=False),
    ]
    shuffled = trials.copy()
    random.Random(19).shuffle(shuffled)
    original_report = generate_stats_report(
        trials, n_resamples=500, n_permutations=500, seed=42,
    )
    shuffled_report = generate_stats_report(
        shuffled, n_resamples=500, n_permutations=500, seed=42,
    )
    assert shuffled_report == original_report

    comparison = original_report["comparisons"]["bench/a_vs_b"]
    assert comparison["n_a"] == 4
    assert comparison["n_b"] == 3
    assert comparison["n_pairs"] == 3
    assert comparison["n_tasks"] == 2
    assert comparison["n_unmatched_a"] == 1
    assert comparison["n_unmatched_b"] == 0
    assert comparison["mean_token_difference"] == pytest.approx(17.5)
    assert comparison["pass_rate_a"] == pytest.approx(0.75)
    assert comparison["pass_rate_b"] == pytest.approx(0.5)
    assert comparison["pass_rate_difference"] == pytest.approx(0.25)


def test_report_does_not_mix_equal_task_ids_across_benchmarks():
    trials = []
    for benchmark, difference in [("bench_a", 10), ("bench_b", 30)]:
        trials.extend([
            _trial("a", 0, 100, benchmark=benchmark, task_id="shared"),
            _trial("b", 0, 100 - difference, benchmark=benchmark, task_id="shared"),
        ])
    report = generate_stats_report(trials, n_resamples=100, n_permutations=100)
    assert report["comparisons"]["bench_a/a_vs_b"]["mean_token_difference"] == 10
    assert report["comparisons"]["bench_b/a_vs_b"]["mean_token_difference"] == 30
    assert set(report["per_task"]) == {
        "bench_a/shared/a_vs_b",
        "bench_b/shared/a_vs_b",
    }


def test_report_zero_differences_has_neutral_tests_and_zero_ci():
    trials = []
    for task_id in ["t1", "t2", "t3"]:
        for arm in ["a", "b"]:
            for trial_id in range(2):
                trials.append(_trial(arm, trial_id, 100, task_id=task_id))
    report = generate_stats_report(trials, n_resamples=500, n_permutations=500)
    comparison = report["comparisons"]["bench/a_vs_b"]
    assert comparison["mean_token_difference_ci"] == [0.0, 0.0]
    assert comparison["pass_rate_difference_ci"] == [0.0, 0.0]
    assert comparison["permutation_p"] == 1.0
    assert comparison["pass_rate_permutation_p"] == 1.0
    assert comparison["wilcoxon"]["p_value"] == 1.0
    assert comparison["z_test"]["p_value"] == 1.0


def test_report_far_tail_p_values_are_nonzero():
    # 100 tasks, one trial per arm. The constant -900 token difference
    # drives Wilcoxon |z| ~ 8.7 (normal-approximation branch) and the
    # 90/10 pass-rate split drives the paired z-test to |z| ~ 13.27 —
    # both regimes where the old 2*(1-CDF) form reported an impossible
    # exact 0.0 in the canonical artifacts.
    trials = []
    for k in range(100):
        task_id = f"t{k}"
        trials.append(_trial("classic", 0, 1000, task_id=task_id, passed=k % 10 == 0))
        trials.append(_trial("tahoe", 0, 100, task_id=task_id, passed=k % 10 != 0))
    report = generate_stats_report(trials, n_resamples=100, n_permutations=100, seed=42)
    comp = report["comparisons"]["bench/classic_vs_tahoe"]

    wilcoxon_z = comp["wilcoxon"]["z_stat"]
    wilcoxon_p = comp["wilcoxon"]["p_value"]
    assert wilcoxon_z is not None and abs(wilcoxon_z) > 8.0
    # Guard: this data sits in the regime where the old 2*(1-CDF) form
    # collapsed to an impossible exact 0.0 in the canonical artifacts.
    assert 2.0 * (1.0 - _standard_normal_cdf(abs(wilcoxon_z))) == 0.0
    assert 0.0 < wilcoxon_p < 1e-15  # tiny, never an impossible exact zero
    assert wilcoxon_p == pytest.approx(math.erfc(abs(wilcoxon_z) / math.sqrt(2.0)))

    z_stat = comp["z_test"]["z_stat"]
    z_p = comp["z_test"]["p_value"]
    assert z_stat is not None and abs(z_stat) > 13.0
    # Guard: this data sits in the regime where the old 2*(1-CDF) form
    # collapsed to an impossible exact 0.0 in the canonical artifacts.
    assert 2.0 * (1.0 - _standard_normal_cdf(abs(z_stat))) == 0.0
    # Reference for this construction: |z| ≈ 13.27 (paired task-mean z of
    # the ±1 pass-rate differences, mean 0.8 / SE ≈ 0.0603) ⇒ p ≈ 3.62e-40.
    # The pytest.approx(erfc(...)) check below is the precise guard.
    assert 0.0 < z_p < 1e-39
    assert z_p == pytest.approx(math.erfc(abs(z_stat) / math.sqrt(2.0)))


# -- Holm multiplicity correction -----------------------------------------


def test_holm_adjust_pvalues_known_step_down_result():
    raw = [0.01, 0.04, 0.03]
    assert holm_adjust_pvalues(raw) == pytest.approx([0.03, 0.06, 0.06])
    assert raw == [0.01, 0.04, 0.03]  # input is not mutated


def test_holm_adjust_pvalues_empty_and_degenerate():
    assert holm_adjust_pvalues([]) == []
    assert holm_adjust_pvalues([0.0, 1.0, 1.0]) == [0.0, 1.0, 1.0]
    with pytest.raises(ValueError, match="P-values"):
        holm_adjust_pvalues([0.2, float("nan")])


def test_report_applies_holm_to_each_comparison_family():
    report = generate_stats_report(
        _make_trials(), n_resamples=200, n_permutations=200, seed=42,
    )
    comparison = report["comparisons"]["bench_a/classic_vs_tahoe"]
    assert comparison["permutation_p_holm"] >= comparison["permutation_p"]
    assert (comparison["pass_rate_permutation_p_holm"]
            >= comparison["pass_rate_permutation_p"])
    assert comparison["z_test"]["p_value_holm"] >= comparison["z_test"]["p_value"]
    assert comparison["wilcoxon"]["p_value_holm"] >= comparison["wilcoxon"]["p_value"]
    assert report["multiplicity"]["method"] == "holm"


# -- Equivalence and non-inferiority --------------------------------------


def test_equivalence_test_zero_differences_within_margin():
    result = equivalence_test([1.0, 1.0, 1.0], [1.0, 1.0, 1.0], margin=0.05)
    assert result["mean_difference"] == 0.0
    assert result["p_value"] == 0.0
    assert result["equivalent"] is True


def test_equivalence_test_rejects_difference_outside_margin():
    result = equivalence_test([1.2, 1.2, 1.2], [1.0, 1.0, 1.0], margin=0.05)
    assert result["p_value"] == 1.0
    assert result["equivalent"] is False


def test_equivalence_test_nonconstant_differences_returns_valid_p_value():
    result = equivalence_test(
        [1.0, 1.1, 0.95, 1.05], [1.0, 1.0, 1.0, 1.0], margin=0.2,
    )
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["df"] == 3


def test_non_inferiority_test_respects_margin_and_direction():
    a = [0.96, 0.96, 0.96]
    b = [1.0, 1.0, 1.0]
    accepted = non_inferiority_test(a, b, margin=0.05)
    rejected = non_inferiority_test(a, b, margin=0.01)
    assert accepted["p_value"] == 0.0
    assert accepted["non_inferior"] is True
    assert rejected["p_value"] == 1.0
    assert rejected["non_inferior"] is False


def test_margin_tests_validate_inputs():
    with pytest.raises(ValueError, match="positive"):
        equivalence_test([1.0, 1.0], [1.0, 1.0], margin=0.0)
    with pytest.raises(ValueError, match="non-negative"):
        non_inferiority_test([1.0, 1.0], [1.0, 1.0], margin=-0.1)
    with pytest.raises(ValueError, match="at least two"):
        equivalence_test([1.0], [1.0], margin=0.1)
    with pytest.raises(ValueError, match="equal-length"):
        non_inferiority_test([1.0, 1.0], [1.0], margin=0.1)
