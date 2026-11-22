import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.report import (
    compute_stats,
    generate_json_report,
    generate_markdown_table,
    generate_per_task_comparison,
    group_trials,
)

TASKS = ["t1", "t2", "t3"]
ARMS = ["classic", "opencode", "tahoe"]


def build_trials():
    """Trials shaped like old archives: no truncation/finish/cap fields."""
    trials = []
    for ti, task in enumerate(TASKS):
        for ai, arm in enumerate(ARMS):
            for k in range(5):
                total = 100 * (k + 1) + 10 * ti + 5 * ai
                passed = (k + ti + ai) % 3 != 0
                quality = 0.5 + 0.1 * (k + ti + ai) if passed else 0.0
                trials.append({
                    "task_id": task,
                    "arm": arm,
                    "trial": k,
                    "input_tokens": total // 2,
                    "output_tokens": total - total // 2,
                    "total_tokens": total,
                    "wall_seconds": 10.0 + k,
                    "passed": passed,
                    "failure_class": "none" if passed else "assert_failed",
                    "authoring_tokens": total if arm == "tahoe" else 0,
                    "quality_score": quality,
                })
    return trials


def make_trial(task_id="t1", arm="classic", total=100, passed=True, **extra):
    """Single trial dict; extra kwargs add optional outcome fields."""
    trial = {
        "task_id": task_id,
        "arm": arm,
        "trial": 0,
        "input_tokens": total // 2,
        "output_tokens": total - total // 2,
        "total_tokens": total,
        "wall_seconds": 10.0,
        "passed": passed,
        "failure_class": "none" if passed else "assert_failed",
        "authoring_tokens": 0,
        "quality_score": 1.0 if passed else 0.0,
    }
    trial.update(extra)
    return trial


def test_group_trials_groups_by_task_and_arm():
    trials = build_trials()
    groups = group_trials(trials)

    assert len(groups) == 9
    assert sum(len(group) for group in groups.values()) == len(trials)

    for (task_id, arm), group in groups.items():
        assert task_id in TASKS
        assert arm in ARMS
        assert len(group) == 5
        assert all(trial["task_id"] == task_id for trial in group)
        assert all(trial["arm"] == arm for trial in group)
        assert [trial["trial"] for trial in group] == [0, 1, 2, 3, 4]

    assert set(groups) == {(task, arm) for task in TASKS for arm in ARMS}


def test_compute_stats_mean_and_percentiles():
    trials = build_trials()
    stats = compute_stats(group_trials(trials)[("t1", "classic")])

    assert stats["mean_tokens"] == pytest.approx(300.0)
    assert stats["p25_tokens"] == pytest.approx(200.0)
    assert stats["p50_tokens"] == pytest.approx(300.0)
    assert stats["p75_tokens"] == pytest.approx(400.0)
    assert stats["mean_wall"] == pytest.approx(12.0)
    assert stats["mean_input_tokens"] == pytest.approx(150.0)
    assert stats["mean_output_tokens"] == pytest.approx(150.0)
    assert stats["mean_authoring_tokens"] == pytest.approx(0.0)
    assert stats["pass_rate"] == pytest.approx(0.6)
    assert stats["mean_quality"] > 0.0

    # Truthful cost per success: all 5 attempts' tokens (1500) divided
    # by the 3 successes — not the mean of the successful attempts.
    assert stats["successes"] == 3
    assert stats["total_token_spend"] == 1500
    assert stats["input_token_spend"] == 750
    assert stats["output_token_spend"] == 750
    assert stats["tokens_per_success"] == pytest.approx(500.0)
    assert stats["cost_per_success"] == pytest.approx(500.0)


def test_compute_stats_authoring_tokens_only_for_tahoe():
    groups = group_trials(build_trials())

    tahoe_stats = compute_stats(groups[("t1", "tahoe")])
    assert tahoe_stats["mean_authoring_tokens"] == pytest.approx(310.0)

    classic_stats = compute_stats(groups[("t2", "classic")])
    assert classic_stats["mean_authoring_tokens"] == pytest.approx(0.0)
    assert classic_stats["mean_tokens"] == pytest.approx(310.0)


def test_compute_stats_single_trial_percentiles():
    single = dict(build_trials()[1])
    stats = compute_stats([single])

    assert stats["mean_tokens"] == pytest.approx(single["total_tokens"])
    assert stats["p25_tokens"] == pytest.approx(single["total_tokens"])
    assert stats["p50_tokens"] == pytest.approx(single["total_tokens"])
    assert stats["p75_tokens"] == pytest.approx(single["total_tokens"])
    assert stats["pass_rate"] == pytest.approx(1.0)
    assert stats["cost_per_success"] == pytest.approx(single["total_tokens"])


# -- truthful cost per success ------------------------------------------


def test_cost_per_success_counts_failed_attempts():
    """Regression: failed attempts' tokens must count toward cost per success.

    The old successful-trials-only mean would report 100.0 here (the one
    successful trial's tokens); the truthful value is 900/1.
    """
    trials = [
        make_trial(total=100, passed=True),
        make_trial(total=500, passed=False),
        make_trial(total=300, passed=False),
    ]
    stats = compute_stats(trials)

    assert stats["successes"] == 1
    assert stats["total_token_spend"] == 900
    assert stats["cost_per_success"] == pytest.approx(900.0)
    assert stats["tokens_per_success"] == pytest.approx(900.0)


def test_cost_per_success_zero_successes_is_none():
    """Regression: zero successes must yield None (JSON-safe), never 0.0."""
    trials = [
        make_trial(total=100, passed=False),
        make_trial(total=200, passed=False),
    ]
    stats = compute_stats(trials)

    assert stats["successes"] == 0
    assert stats["pass_rate"] == 0.0
    assert stats["total_token_spend"] == 300
    assert stats["cost_per_success"] is None
    assert stats["tokens_per_success"] is None


def test_compute_stats_empty_trials_none_not_zero():
    stats = compute_stats([])

    assert stats["pass_rate"] == 0.0
    assert stats["total_token_spend"] == 0.0
    assert stats["cost_per_success"] is None
    assert stats["tokens_per_success"] is None
    assert stats["completed_response_accuracy"] is None


def test_zero_successes_is_json_safe_and_markdown_dash():
    trials = [make_trial(task_id="t9", total=100, passed=False)
              for _ in range(3)]

    raw = generate_json_report(trials)
    assert '"cost_per_success": null' in raw
    assert '"tokens_per_success": null' in raw
    report = json.loads(raw)
    entry = report["groups"][0]
    assert entry["cost_per_success"] is None
    assert entry["tokens_per_success"] is None

    table = generate_markdown_table(trials)
    row = next(line for line in table.split("\n") if line.startswith("| t9"))
    cells = [c.strip() for c in row.split("|")[1:-1]]
    header = [c.strip() for c in table.split("\n")[0].split("|")[1:-1]]
    tokens_cell = cells[header.index("tokens/success")]
    compl_cell = cells[header.index("compl_acc")]
    assert tokens_cell == "-"
    assert compl_cell == "0.00"


# -- truncation / cap exhaustion / empty responses -----------------------


def test_truncation_counted_from_explicit_flag_and_finish_reason():
    trials = [
        make_trial(truncated=True),
        make_trial(finish_reason="length"),
        make_trial(finish_reason="stop"),
        make_trial(),
    ]
    stats = compute_stats(trials)

    assert stats["truncation_count"] == 2
    assert stats["truncation_rate"] == pytest.approx(0.5)


def test_old_archive_never_fabricates_truncation_or_cap():
    """Regression: finish_reason is not fabricated for old archives."""
    stats = compute_stats([make_trial()])

    assert stats["truncation_count"] == 0
    assert stats["truncation_rate"] == 0.0
    assert stats["cap_exhausted_count"] == 0
    assert stats["cap_exhausted_rate"] == 0.0


def test_cap_exhaustion_reported_separately_from_truncation():
    trials = [
        make_trial(cap_exhausted=True, truncated=True),
        make_trial(output_token_cap=100, output_tokens=100, truncated=False),
        make_trial(output_token_cap=100, output_tokens=99),
        make_trial(truncated=True),
    ]
    stats = compute_stats(trials)

    # Trial 2 hit the exact cap without a truncation flag; trial 3 did not.
    assert stats["cap_exhausted_count"] == 2
    assert stats["cap_exhausted_rate"] == pytest.approx(0.5)
    # Truncation only counts explicitly truncated/finish-reason trials.
    assert stats["truncation_count"] == 2


def test_empty_response_counted_from_flag_and_blank_answer():
    trials = [
        make_trial(empty_response=True),
        make_trial(final_answer=""),
        make_trial(final_answer="42"),
        make_trial(),  # old archive: no final_answer key, not counted
    ]
    stats = compute_stats(trials)

    assert stats["empty_response_count"] == 2
    assert stats["empty_response_rate"] == pytest.approx(0.5)


def test_completed_response_accuracy_excludes_incomplete():
    trials = [
        make_trial(total=100, passed=True),
        make_trial(total=100, passed=False, final_answer="A"),
        make_trial(total=100, passed=True, truncated=True),
        make_trial(total=100, passed=False, final_answer=""),
    ]
    stats = compute_stats(trials)

    # Only the first two trials produced a completed response.
    assert stats["completed_response_count"] == 2
    assert stats["completed_response_rate"] == pytest.approx(0.5)
    assert stats["completed_response_accuracy"] == pytest.approx(0.5)
    assert stats["pass_rate"] == pytest.approx(0.5)
    # Cost per success still spends all 400 tokens over both successes.
    assert stats["cost_per_success"] == pytest.approx(200.0)


def test_completed_response_accuracy_none_when_nothing_completed():
    trials = [make_trial(truncated=True, passed=False)]
    stats = compute_stats(trials)

    assert stats["completed_response_count"] == 0
    assert stats["completed_response_accuracy"] is None


def test_old_archive_completed_accuracy_equals_pass_rate():
    stats = compute_stats(group_trials(build_trials())[("t1", "classic")])

    assert stats["completed_response_count"] == 5
    assert stats["completed_response_rate"] == 1.0
    assert stats["completed_response_accuracy"] == pytest.approx(stats["pass_rate"])


def test_latency_defaults_to_wall_seconds():
    trials = build_trials()[:5]
    stats = compute_stats(trials)
    assert stats["mean_latency"] == pytest.approx(stats["mean_wall"])


def test_latency_prefers_recorded_latency_field():
    trials = [
        make_trial(latency_seconds=5.0),
        make_trial(latency_seconds=15.0),
    ]
    stats = compute_stats(trials)
    assert stats["mean_latency"] == pytest.approx(10.0)
    assert stats["mean_wall"] == pytest.approx(10.0)


# -- output formats -------------------------------------------------------


def test_generate_markdown_table_format():
    table = generate_markdown_table(build_trials())
    lines = table.split("\n")

    assert lines[0] == ("| task_id | arm | trials | pass_rate | mean_quality | "
                        "mean_tokens | p25 | p50 | p75 | mean_wall | tokens/success | "
                        "spend | trunc_rate | cap_rate | empty_rate | compl_acc | "
                        "latency | RE | RC | RR |")
    assert lines[1] == "|" + "---|" * 20
    assert len(lines) == 11

    assert "| t1 | classic | 5 | 0.60 | 0.44 | 300.00 | 200.00 | 300.00 | 400.00 | 12.00 | 500.00 | 1500.00 | 0.00 | 0.00 | 0.00 | 0.60 | 12.00 | 0.0000 | 0.0000 | 0.0000 |" in lines
    assert "| t1 | tahoe | 5 | 0.60 | 0.52 | 310.00 | 210.00 | 310.00 | 410.00 | 12.00 | 516.67 | 1550.00 | 0.00 | 0.00 | 0.00 | 0.60 | 12.00 | 0.0000 | 0.0000 | 0.0000 |" in lines

    data_rows = lines[2:]
    assert all(row.startswith("| t") and row.endswith("|") for row in data_rows)
    assert [tuple(part.strip() for part in row.split("|")[1:3]) for row in data_rows] == [
        ("t1", "classic"), ("t1", "opencode"), ("t1", "tahoe"),
        ("t2", "classic"), ("t2", "opencode"), ("t2", "tahoe"),
        ("t3", "classic"), ("t3", "opencode"), ("t3", "tahoe"),
    ]


def test_generate_markdown_table_mixed_success_groups():
    """Markdown must stay robust when one group has zero successes."""
    trials = build_trials()[:10]  # t1 classic (3 successes) + t1 opencode (4)
    trials += [make_trial(task_id="t1", arm="tahoe", total=50, passed=False)
               for _ in range(5)]
    table = generate_markdown_table(trials)
    rows = {
        tuple(cell.strip() for cell in line.split("|")[1:3]): line
        for line in table.split("\n")[2:]
    }

    classic_cells = [c.strip() for c in rows[("t1", "classic")].split("|")[1:-1]]
    tahoe_cells = [c.strip() for c in rows[("t1", "tahoe")].split("|")[1:-1]]
    assert classic_cells[10] == "500.00"
    assert tahoe_cells[10] == "-"


def test_generate_json_report_structure():
    report = json.loads(generate_json_report(build_trials()))

    assert set(report) == {"groups"}
    assert len(report["groups"]) == 9

    entry = next(
        g for g in report["groups"]
        if g["task_id"] == "t1" and g["arm"] == "classic"
    )
    assert entry["trials"] == 5
    assert entry["pass_rate"] == pytest.approx(0.6)
    assert entry["successes"] == 3
    assert entry["mean_tokens"] == pytest.approx(300.0)
    assert entry["p25_tokens"] == pytest.approx(200.0)
    assert entry["p50_tokens"] == pytest.approx(300.0)
    assert entry["p75_tokens"] == pytest.approx(400.0)
    assert entry["mean_wall"] == pytest.approx(12.0)
    assert entry["mean_input_tokens"] == pytest.approx(150.0)
    assert entry["mean_output_tokens"] == pytest.approx(150.0)
    assert entry["mean_authoring_tokens"] == pytest.approx(0.0)
    assert entry["input_token_spend"] == 750
    assert entry["output_token_spend"] == 750
    assert entry["total_token_spend"] == 1500
    assert entry["tokens_per_success"] == pytest.approx(500.0)
    assert entry["cost_per_success"] == pytest.approx(500.0)
    assert entry["truncation_count"] == 0
    assert entry["truncation_rate"] == pytest.approx(0.0)
    assert entry["cap_exhausted_count"] == 0
    assert entry["cap_exhausted_rate"] == pytest.approx(0.0)
    assert entry["empty_response_count"] == 0
    assert entry["empty_response_rate"] == pytest.approx(0.0)
    assert entry["completed_response_count"] == 5
    assert entry["completed_response_accuracy"] == pytest.approx(0.6)
    assert entry["mean_latency"] == pytest.approx(12.0)

    for group in report["groups"]:
        assert {"task_id", "arm", "trials", "pass_rate", "mean_tokens",
                "p25_tokens", "p50_tokens", "p75_tokens", "mean_wall",
                "mean_input_tokens", "mean_output_tokens",
                "mean_authoring_tokens", "mean_quality",
                "p25_quality", "p75_quality",
                "tokens_per_success",
                "successes",
                "input_token_spend", "output_token_spend",
                "total_token_spend",
                "truncation_count", "truncation_rate",
                "cap_exhausted_count", "cap_exhausted_rate",
                "empty_response_count", "empty_response_rate",
                "completed_response_count", "completed_response_rate",
                "completed_response_accuracy",
                "mean_latency",
                "cost_per_success",
                "re_reasoning_efficiency",
                "rc_reasoning_concentration",
                "rr_redundancy_rate"} <= set(group)


def test_generate_per_task_comparison_format():
    report = generate_per_task_comparison(build_trials())
    tables = report.split("\n\n")

    assert len(tables) == 3
    for table, task in zip(tables, TASKS):
        assert table.startswith("| task_id | metric | classic | opencode | tahoe |")
        assert f"| {task} | pass_rate |" in table

    first = tables[0].split("\n")
    assert first[0] == "| task_id | metric | classic | opencode | tahoe |"
    assert first[1] == "|---|---|---|---|---|"

    metrics = [line.split("|")[2].strip() for line in first[2:]]
    assert metrics == [
        "pass_rate", "mean_tokens", "p25_tokens", "p75_tokens", "mean_wall",
        "mean_quality", "tokens_per_success", "total_token_spend",
        "truncation_rate", "cap_exhausted_rate", "empty_response_rate",
        "completed_response_accuracy", "mean_latency",
        "re_reasoning_efficiency", "rc_reasoning_concentration",
        "rr_redundancy_rate",
    ]

    assert "| t1 | pass_rate | 0.60 | 0.80 | 0.60 |" in first
    assert "| t1 | mean_tokens | 300.00 | 305.00 | 310.00 |" in first
    # Truthful cost per success: full spend over successes, per arm.
    assert "| t1 | tokens_per_success | 500.00 | 381.25 | 516.67 |" in first
    assert "| t1 | total_token_spend | 1500.00 | 1525.00 | 1550.00 |" in first
    assert "| t1 | completed_response_accuracy | 0.60 | 0.80 | 0.60 |" in first

    second = tables[1].split("\n")
    assert "| t2 | pass_rate | 0.80 | 0.60 | 0.60 |" in second
    assert any("| t2 | mean_quality |" in line for line in second)
    assert "| t2 | tokens_per_success | 387.50 | 525.00 | 533.33 |" in second


def test_generate_per_task_comparison_zero_successes_dash():
    trials = [
        make_trial(task_id="t1", arm="classic", total=100, passed=True),
        make_trial(task_id="t1", arm="opencode", total=100, passed=False),
    ]
    report = generate_per_task_comparison(trials)
    assert "| t1 | tokens_per_success | 100.00 | - |" in report
