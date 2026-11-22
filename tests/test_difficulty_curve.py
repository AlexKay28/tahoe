"""Tests for benchmarks/difficulty_curve.py — keyed paired task-level curve.

Covers the requirements of the paired rewrite:
  - pairing by (benchmark, task_id, trial) identity, never by input position
  - repeated trials averaged within tasks (task macro is the primary estimate)
  - micro vs macro accuracy reported separately
  - missing pairs dropped (and reported), unpairable benchmarks skipped
  - paired task-bootstrap CI + paired permutation p, Holm-adjusted across the
    benchmark family; the significant_95 alias follows the Holm-adjusted p
  - token_ratio stays explicitly total-token based (sums over paired trials)

Tests only touch pure functions; the script itself is never run and archived
results/figures are never read or written.
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks import difficulty_curve as dc
from benchmarks.stats import holm_adjust_pvalues


# Small resample counts keep these fast; determinism comes from the seed.
KW = {"n_resamples": 300, "n_permutations": 400}


def trial(benchmark, task_id, arm, passed, trial_no=0, total_tokens=100):
    return {
        "benchmark": benchmark,
        "task_id": task_id,
        "trial": trial_no,
        "arm": arm,
        "passed": bool(passed),
        "total_tokens": total_tokens,
    }


# -- pairing by key, not by position --------------------------------------


def test_paired_task_means_averages_and_sorts():
    pairs = [
        (trial("m", "B", "classic", 1, trial_no=1), trial("m", "B", "tahoe", 0, trial_no=1)),
        (trial("m", "A", "classic", 0), trial("m", "A", "tahoe", 1)),
        (trial("m", "B", "classic", 0, trial_no=0), trial("m", "B", "tahoe", 1, trial_no=0)),
    ]
    keys, va, vb = dc.paired_task_means(pairs, "passed")
    assert keys == [("m", "A"), ("m", "B")]
    assert va == [0.0, pytest.approx(0.5)]
    assert vb == [1.0, pytest.approx(0.5)]


def test_pairs_formed_by_key_not_position():
    classic = [
        trial("k", "A", "classic", 0, total_tokens=100),
        trial("k", "B", "classic", 1, total_tokens=200),
        trial("k", "C", "classic", 1, total_tokens=300),
    ]
    # shuffled order + an unpaired extra trial with a huge token count
    tahoe = [
        trial("k", "C", "tahoe", 1, total_tokens=30),
        trial("k", "D", "tahoe", 1, total_tokens=99_999),
        trial("k", "A", "tahoe", 1, total_tokens=10),
        trial("k", "B", "tahoe", 0, total_tokens=20),
    ]
    row = dc.benchmark_row("k", classic, tahoe, **KW)
    assert row is not None
    assert row["n_classic"] == 3 and row["n_tahoe"] == 3
    assert row["n_tasks"] == 3
    assert row["n_unpaired_classic"] == 0
    assert row["n_unpaired_tahoe"] == 1
    # per-task deltas: A +1, B −1, C 0 → mean 0
    assert row["delta_pp"] == 0.0
    assert row["classic_acc"] == pytest.approx(2 / 3, abs=1e-4)
    assert row["tahoe_acc"] == pytest.approx(2 / 3, abs=1e-4)
    # the unpaired D trial's tokens are excluded from the ratio
    assert row["token_ratio"] == pytest.approx(60 / 600, abs=1e-4)


def test_trial_number_mismatch_prevents_pairing():
    classic = [trial("k", "A", "classic", 1, trial_no=0)]
    tahoe = [trial("k", "A", "tahoe", 0, trial_no=1)]  # same task, wrong trial
    assert dc.benchmark_row("k", classic, tahoe, **KW) is None


def test_benchmarks_without_pairs_are_skipped():
    trials = [
        trial("solo_classic", "A", "classic", 1),
        trial("solo_classic", "B", "classic", 1),
        trial("disjoint_trials", "A", "classic", 1, trial_no=0),
        trial("disjoint_trials", "A", "tahoe", 0, trial_no=5),
    ]
    assert dc.compute_curve(trials, **KW) == []


# -- repeated trials aggregate within tasks; micro vs macro ----------------


def test_repeated_trials_averaged_within_task_macro_primary():
    classic = [
        # task X: single trial per arm
        trial("m", "X", "classic", 0),
        # task Y: three repeated trials per arm
        trial("m", "Y", "classic", 1, trial_no=0),
        trial("m", "Y", "classic", 1, trial_no=1),
        trial("m", "Y", "classic", 0, trial_no=2),
    ]
    tahoe = [
        trial("m", "X", "tahoe", 1),
        trial("m", "Y", "tahoe", 1, trial_no=0),
        trial("m", "Y", "tahoe", 0, trial_no=1),
        trial("m", "Y", "tahoe", 0, trial_no=2),
    ]
    row = dc.benchmark_row("m", classic, tahoe, **KW)
    assert row is not None
    assert row["n_tasks"] == 2
    assert row["n_classic"] == 4 and row["n_tahoe"] == 4
    # task macro: X 0 vs 1, Y 2/3 vs 1/3 → classic 1/3, tahoe 2/3, delta +1/3
    assert row["classic_acc"] == pytest.approx(1 / 3, abs=1e-4)
    assert row["tahoe_acc"] == pytest.approx(2 / 3, abs=1e-4)
    assert row["delta_pp"] == pytest.approx(100 / 3, abs=0.02)
    # micro (pooled over paired trials): 2/4 vs 2/4 — differs from macro
    assert row["classic_acc_micro"] == 0.5
    assert row["tahoe_acc_micro"] == 0.5
    assert row["classic_acc_micro"] != row["classic_acc"]


def test_micro_equals_macro_when_trials_per_task_uniform():
    trials = []
    for task in ("A", "B", "C", "D"):
        for tno in (0, 1, 2):
            trials.append(trial("u", task, "classic", 1, trial_no=tno))
            trials.append(trial("u", task, "tahoe", 0, trial_no=tno))
    (row,) = dc.compute_curve(trials, **KW)
    assert row["classic_acc"] == row["classic_acc_micro"] == 1.0
    assert row["tahoe_acc"] == row["tahoe_acc_micro"] == 0.0
    assert row["n_tasks"] == 4 and row["n_classic"] == 12


# -- input order never matters ---------------------------------------------


def test_curve_independent_of_input_order():
    rng = random.Random(7)
    trials = []
    for bench in ("b1", "b2", "b3"):
        for task in ("t1", "t2", "t3", "t4", "t5"):
            for tno in (0, 1):
                trials.append(trial(bench, task, "classic", rng.random() < 0.6,
                                    trial_no=tno, total_tokens=rng.randrange(50, 150)))
                trials.append(trial(bench, task, "tahoe", rng.random() < 0.4,
                                    trial_no=tno, total_tokens=rng.randrange(50, 150)))
    # an unmatched trial per benchmark, plus another arm that must be ignored
    trials.append(trial("b1", "t9", "classic", 1, total_tokens=1_000_000))
    trials.append({"benchmark": "b2", "task_id": "t1", "trial": 0,
                   "arm": "other", "passed": True, "total_tokens": 1})

    first = dc.compute_curve(list(trials), **KW)
    shuffled = list(trials)
    random.Random(123).shuffle(shuffled)
    second = dc.compute_curve(shuffled, **KW)
    assert first == second

    (b1, b2, b3) = first
    assert b1["n_unpaired_classic"] == 1 and b1["n_unpaired_tahoe"] == 0
    # the ignored arm contributed nothing
    assert b2["n_classic"] == 10 and b2["n_tahoe"] == 10


def test_curve_deterministic_given_seed():
    trials = []
    for task in ("t1", "t2", "t3", "t4"):
        trials.append(trial("d", task, "classic", 0, trial_no=0, total_tokens=90))
        trials.append(trial("d", task, "tahoe", 1, trial_no=0, total_tokens=110))
    assert dc.compute_curve(list(trials), **KW) == dc.compute_curve(list(trials), **KW)


# -- missing pairs ----------------------------------------------------------


def test_unpaired_counts_and_token_exclusion():
    classic = [
        trial("k", "A", "classic", 1, total_tokens=100),
        trial("k", "B", "classic", 1, total_tokens=100),
        trial("k", "N", "classic", 0, total_tokens=50_000),  # no tahoe counterpart
    ]
    tahoe = [
        trial("k", "A", "tahoe", 1, total_tokens=100),
        trial("k", "B", "tahoe", 0, total_tokens=100),
        trial("k", "M", "tahoe", 1, total_tokens=70_000),  # no classic counterpart
    ]
    row = dc.benchmark_row("k", classic, tahoe, **KW)
    assert row is not None
    assert row["n_tasks"] == 2
    assert row["n_unpaired_classic"] == 1
    assert row["n_unpaired_tahoe"] == 1
    assert row["token_ratio"] == 1.0  # 50k/70k unpaired tokens excluded


def test_zero_tokens_gives_null_ratio():
    classic = [trial("k", "A", "classic", 1, total_tokens=0)]
    tahoe = [trial("k", "A", "tahoe", 1, total_tokens=123)]
    row = dc.benchmark_row("k", classic, tahoe, **KW)
    assert row is not None
    assert row["token_ratio"] is None


# -- multiplicity: Holm across the benchmark family -------------------------


def test_holm_adjustment_across_benchmarks():
    trials = []
    # strong: consistent +1 per task over 20 tasks → tiny permutation p
    for i in range(20):
        tid = f"s{i:02d}"
        trials.append(trial("strong", tid, "classic", 0))
        trials.append(trial("strong", tid, "tahoe", 1))
    # weak1: all differences zero → p = 1
    for tid in ("w1a", "w1b"):
        trials.append(trial("weak1", tid, "classic", 1))
        trials.append(trial("weak1", tid, "tahoe", 1))
    # weak2: mixed-sign deltas that cancel → observed |sum| = 0, p = 1
    for passed_c, passed_t, tid in ((1, 0, "w2a"), (1, 0, "w2b"),
                                    (0, 1, "w2c"), (0, 1, "w2d")):
        trials.append(trial("weak2", tid, "classic", passed_c))
        trials.append(trial("weak2", tid, "tahoe", passed_t))

    rows = dc.compute_curve(trials, **KW)
    by_name = {r["benchmark"]: r for r in rows}
    assert set(by_name) == {"strong", "weak1", "weak2"}

    raw = [r["p_paired"] for r in rows]
    adjusted = holm_adjust_pvalues(raw)
    for r, p_raw, p_holm in zip(rows, raw, adjusted):
        assert r["p_paired_holm"] == p_holm  # exact recomputation
        assert r["p_paired_holm"] >= r["p_paired"]  # Holm never shrinks p
        assert r["significant_95"] == (r["p_paired_holm"] < 0.05)

    strong = by_name["strong"]
    assert strong["delta_pp"] == 100.0
    assert strong["p_paired"] < 0.01
    assert strong["p_paired_holm"] == pytest.approx(3 * strong["p_paired"], abs=1e-5)
    assert strong["significant_95"] is True
    for weak in ("weak1", "weak2"):
        assert by_name[weak]["p_paired_holm"] == 1.0
        assert by_name[weak]["significant_95"] is False


def test_family_wide_alpha_is_configurable():
    trials = []
    for i in range(12):
        tid = f"t{i:02d}"
        trials.append(trial("cfg", tid, "classic", 0))
        trials.append(trial("cfg", tid, "tahoe", 1))
    strict = dc.compute_curve(trials, n_resamples=300, n_permutations=400, alpha=0.001)
    loose = dc.compute_curve(trials, n_resamples=300, n_permutations=400, alpha=0.5)
    p_holm = strict[0]["p_paired_holm"]
    assert loose[0]["p_paired_holm"] == p_holm  # same data, only alpha differs
    assert 0 < p_holm < 0.05  # 12 consistent pairs: family-wise p is small…
    assert strict[0]["significant_95"] is False  # …but not < 0.001
    assert loose[0]["significant_95"] is True


# -- schema: compatibility aliases and replaced fields -----------------------


def test_row_schema_consumer_fields_and_no_z():
    trials = [
        trial("k", "A", "classic", 1, trial_no=0, total_tokens=80),
        trial("k", "A", "tahoe", 0, trial_no=0, total_tokens=120),
        trial("k", "B", "classic", 0, trial_no=0, total_tokens=80),
        trial("k", "B", "tahoe", 1, trial_no=0, total_tokens=120),
    ]
    (row,) = dc.compute_curve(trials, **KW)

    # fields consumed by benchmarks/make_results_table.py stay present
    for field in ("benchmark", "n_classic", "n_tahoe", "classic_acc", "tahoe_acc",
                  "delta_pp", "delta_ci95_pp", "significant_95", "token_ratio"):
        assert field in row, f"missing compatibility field {field}"
    # the unpaired z statistic is gone, replaced by paired p-values
    assert "z" not in row
    assert "p_paired" in row and "p_paired_holm" in row
    assert row["pairing_key"] == ["benchmark", "task_id", "trial"]


def test_delta_ci_fields_bracket_point_and_half_width_is_conservative():
    trials = []
    for i in range(10):
        tid = f"t{i:02d}"
        trials.append(trial("c", tid, "classic", i % 3 == 0))
        trials.append(trial("c", tid, "tahoe", i % 2 == 0))
    (row,) = dc.compute_curve(trials, **KW)
    lo, point, hi = row["delta_ci95_pp_lo"], row["delta_pp"], row["delta_ci95_pp_hi"]
    assert lo <= point <= hi
    half = row["delta_ci95_pp"]
    # the symmetric alias never under-reports the asymmetric percentile CI
    assert half + 0.02 >= max(point - lo, hi - point)
    assert half >= 0


def test_token_ratio_is_total_token_sum_ratio():
    trials = []
    for tid, c_tok, t_tok in (("A", 100, 300), ("B", 400, 100), ("C", 500, 100)):
        trials.append(trial("k", tid, "classic", 1, trial_no=0, total_tokens=c_tok))
        trials.append(trial("k", tid, "tahoe", 1, trial_no=0, total_tokens=t_tok))
    (row,) = dc.compute_curve(trials, **KW)
    assert row["token_ratio"] == pytest.approx(500 / 1000, abs=1e-4)


# -- loud failure on ambiguous or incomplete identities ---------------------


def test_duplicate_trial_key_rejected():
    trials = [
        trial("k", "A", "classic", 1, trial_no=0),
        trial("k", "A", "classic", 0, trial_no=0),  # duplicate key
        trial("k", "A", "tahoe", 1, trial_no=0),
    ]
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        dc.compute_curve(trials, **KW)


def test_missing_key_field_rejected():
    trials = [
        trial("k", "A", "classic", 1),
        {"benchmark": "k", "task_id": "A", "arm": "tahoe", "passed": True,
         "total_tokens": 10},  # no "trial" field
    ]
    with pytest.raises(ValueError, match="key fields"):
        dc.compute_curve(trials, **KW)


def test_non_numeric_field_rejected():
    pairs = [
        (trial("k", "A", "classic", 1),
         dict(trial("k", "A", "tahoe", 1), final_answer="A")),
    ]
    with pytest.raises(ValueError, match="numeric"):
        dc.paired_task_means(pairs, "final_answer")
