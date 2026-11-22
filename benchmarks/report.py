"""Token distribution and solution quality report for the ablation study.

Truthful cost-per-success semantics
-----------------------------------
``cost_per_success`` (and its legacy alias ``tokens_per_success``) is

    sum(total_tokens over ALL attempts) / number of successes

Tokens from *failed* attempts are included in the numerator, so the
metric reflects the real spend of producing each success instead of the
mean of the successful trials only.  With zero successes the value is
``None`` (JSON-safe ``null``) — a division by zero is not a free success
— and never ``0.0``.

Outcome reporting (truncation, cap exhaustion, empty responses,
completed-response accuracy, latency) uses only fields actually present
on each trial.  ``finish_reason`` is NEVER fabricated for old archives:
when the relevant fields are absent, the counts fall back to 0 and the
rates to 0.0 (documented backward-compatible defaults).
"""

import json
import statistics
from collections import defaultdict

try:
    from metrics import compute_all_metrics
except ImportError:
    from benchmarks.metrics import compute_all_metrics

STAT_FIELDS = (
    "pass_rate",
    "mean_tokens",
    "p25_tokens",
    "p50_tokens",
    "p75_tokens",
    "mean_wall",
    "mean_input_tokens",
    "mean_output_tokens",
    "mean_authoring_tokens",
    "mean_quality",
    "p25_quality",
    "p75_quality",
    "tokens_per_success",
    # --- truthful spend / outcome reporting ---
    "successes",
    "input_token_spend",
    "output_token_spend",
    "total_token_spend",
    "truncation_count",
    "truncation_rate",
    "cap_exhausted_count",
    "cap_exhausted_rate",
    "empty_response_count",
    "empty_response_rate",
    "completed_response_count",
    "completed_response_rate",
    "completed_response_accuracy",
    "mean_latency",
    "cost_per_success",
)

REASONING_METRIC_FIELDS = (
    "re_reasoning_efficiency",
    "rc_reasoning_concentration",
    "rr_redundancy_rate",
)

COMPARISON_METRICS = (
    "pass_rate",
    "mean_tokens",
    "p25_tokens",
    "p75_tokens",
    "mean_wall",
    "mean_quality",
    "tokens_per_success",
    "total_token_spend",
    "truncation_rate",
    "cap_exhausted_rate",
    "empty_response_rate",
    "completed_response_accuracy",
    "mean_latency",
    "re_reasoning_efficiency",
    "rc_reasoning_concentration",
    "rr_redundancy_rate",
)

# finish_reason values (OpenAI-style) that mean the response was cut
# short before it was complete.  Only consulted when the trial actually
# records a finish_reason — never inferred for old archives.
TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens", "content_filter"})

# Trial keys that may carry the exact configured output-token cap.
OUTPUT_CAP_KEYS = ("output_token_cap", "max_output_tokens")


def _percentiles(values):
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        only = float(values[0])
        return only, only, only
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return quartiles[0], quartiles[1], quartiles[2]


def _fmt(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _is_truncated(trial):
    """True when the trial's model response was cut short before completion.

    Uses only information actually recorded on the trial; finish_reason is
    never fabricated for old archives.  Priority:

      1. explicit ``truncated`` boolean flag
      2. explicit ``finish_reason`` string — "length", "max_tokens" or
         "content_filter" mean the response is incomplete
      3. default False (absent/unknown fields are not counted)
    """
    if "truncated" in trial:
        return bool(trial["truncated"])
    finish_reason = trial.get("finish_reason")
    if isinstance(finish_reason, str):
        return finish_reason.strip().lower() in TRUNCATED_FINISH_REASONS
    return False


def _is_cap_exhausted(trial):
    """True when the trial hit its exact configured output-token cap.

    Reported separately from truncation because a response can be cut
    short for other reasons (content filter, dropped stream), and a cap
    hit can only be confirmed when the cap itself is recorded.  Only
    uses information actually configured/available on the trial:

      1. explicit ``cap_exhausted`` boolean flag
      2. explicit output cap (``output_token_cap`` / ``max_output_tokens``)
         with ``output_tokens >= cap`` — at the cap the response cannot
         be confirmed complete, so it is conservatively exhausted
      3. default False (no cap recorded ⇒ not counted)
    """
    if "cap_exhausted" in trial:
        return bool(trial["cap_exhausted"])
    for key in OUTPUT_CAP_KEYS:
        cap = trial.get(key)
        if cap is not None and cap > 0:
            return trial.get("output_tokens", 0) >= cap
    return False


def _is_empty_response(trial):
    """True when the model produced no response text at all.

      1. explicit ``empty_response`` boolean flag
      2. derived from ``final_answer`` when the key is present: a blank
         answer means no response text was produced (matches the retry
         heuristic the runners already use)
      3. default False (no answer recorded ⇒ not counted)
    """
    if "empty_response" in trial:
        return bool(trial["empty_response"])
    if "final_answer" in trial:
        answer = trial.get("final_answer")
        return not (answer.strip() if isinstance(answer, str) else answer)
    return False


def _is_completed_response(trial):
    """A completed response: not truncated, cap not exhausted, not empty."""
    return not (
        _is_truncated(trial)
        or _is_cap_exhausted(trial)
        or _is_empty_response(trial)
    )


def group_trials(trials):
    groups = defaultdict(list)
    for trial in trials:
        groups[(trial["task_id"], trial["arm"])].append(trial)
    return dict(groups)


def compute_reasoning_metrics(run_data) -> dict:
    """Compute RE, RC, RR reasoning metrics from run results.

    Accepts either a list of trial dicts (as used by compute_stats) or a
    single run-summary dict.  When trial-level ref/token counts are
    absent (e.g. classic-arm public-bench trials), the metrics are 0.0.
    """
    if isinstance(run_data, dict):
        return compute_all_metrics(run_data)

    if not run_data:
        return {field: 0.0 for field in REASONING_METRIC_FIELDS}

    totals = {
        "verified_logical_steps": sum(t.get("verified_logical_steps", 0) for t in run_data),
        "total_tokens": sum(t.get("total_tokens", 0) for t in run_data),
        "typed_refs_produced": sum(t.get("typed_refs_produced", 0) for t in run_data),
        "output_tokens": sum(t.get("output_tokens", 0) for t in run_data),
        "repeated_refs": sum(t.get("repeated_refs", 0) for t in run_data),
        "retired_refs": sum(t.get("retired_refs", 0) for t in run_data),
        "total_refs_produced": sum(t.get("total_refs_produced", 0) for t in run_data),
    }
    return compute_all_metrics(totals)


def compute_stats(trials):
    """Compute per-group statistics from a list of trial dicts.

    Cost per success (``cost_per_success``, legacy alias
    ``tokens_per_success``) is the truthful metric:

        sum(total_tokens over ALL attempts) / number of successes

    Failed attempts count toward the spend, so a group of 10 attempts
    with 2 successes reports the full token spend divided by 2 — not the
    mean of the 2 successful attempts.  With zero successes the value is
    ``None`` (JSON-safe ``null``), never ``0.0``: an undefined cost must
    not masquerade as a free success.

    ``completed_response_accuracy`` is pass rate restricted to trials
    whose response completed (not truncated, cap not exhausted, not
    empty); it is ``None`` when no trial completed a response.
    """
    if not trials:
        result = {field: 0.0 for field in STAT_FIELDS + REASONING_METRIC_FIELDS}
        result["successes"] = 0
        result["tokens_per_success"] = None
        result["cost_per_success"] = None
        result["completed_response_accuracy"] = None
        return result

    n = len(trials)
    totals = [trial["total_tokens"] for trial in trials]
    inputs = [trial["input_tokens"] for trial in trials]
    outputs = [trial["output_tokens"] for trial in trials]
    walls = [trial["wall_seconds"] for trial in trials]
    authoring = [trial.get("authoring_tokens") or 0 for trial in trials]
    # Latency defaults to wall time; a dedicated latency_seconds field
    # wins when a runner records one.
    latencies = [
        trial.get("latency_seconds", trial.get("wall_seconds")) for trial in trials
    ]
    p25, p50, p75 = _percentiles(totals)
    passed = sum(1 for trial in trials if trial["passed"])
    successes = passed

    qualities = [
        trial.get("quality_score") for trial in trials
        if trial.get("quality_score") is not None
    ]
    if qualities:
        q_p25, q_p50, q_p75 = _percentiles(qualities)
        mean_quality = statistics.fmean(qualities)
    else:
        q_p25 = q_p50 = q_p75 = 0.0
        mean_quality = 0.0

    total_token_spend = sum(totals)
    # Truthful cost per success: every attempt's tokens count toward the
    # spend, and zero successes means the cost is undefined (None), not 0.
    cost_per_success = total_token_spend / successes if successes else None
    tokens_per_success = cost_per_success

    truncation_count = sum(1 for t in trials if _is_truncated(t))
    cap_exhausted_count = sum(1 for t in trials if _is_cap_exhausted(t))
    empty_response_count = sum(1 for t in trials if _is_empty_response(t))
    completed = [t for t in trials if _is_completed_response(t)]
    completed_response_count = len(completed)
    completed_passed = sum(1 for t in completed if t["passed"])
    completed_response_accuracy = (
        completed_passed / completed_response_count
        if completed_response_count
        else None
    )

    result = {
        "pass_rate": passed / n,
        "mean_tokens": statistics.fmean(totals),
        "p25_tokens": p25,
        "p50_tokens": p50,
        "p75_tokens": p75,
        "mean_wall": statistics.fmean(walls),
        "mean_input_tokens": statistics.fmean(inputs),
        "mean_output_tokens": statistics.fmean(outputs),
        "mean_authoring_tokens": statistics.fmean(authoring),
        "mean_quality": mean_quality,
        "p25_quality": q_p25,
        "p75_quality": q_p75,
        "tokens_per_success": tokens_per_success,
        "successes": successes,
        "input_token_spend": sum(inputs),
        "output_token_spend": sum(outputs),
        "total_token_spend": total_token_spend,
        "truncation_count": truncation_count,
        "truncation_rate": truncation_count / n,
        "cap_exhausted_count": cap_exhausted_count,
        "cap_exhausted_rate": cap_exhausted_count / n,
        "empty_response_count": empty_response_count,
        "empty_response_rate": empty_response_count / n,
        "completed_response_count": completed_response_count,
        "completed_response_rate": completed_response_count / n,
        "completed_response_accuracy": completed_response_accuracy,
        "mean_latency": statistics.fmean(latencies),
        "cost_per_success": cost_per_success,
    }
    result.update(compute_reasoning_metrics(trials))
    return result


def generate_markdown_table(trials):
    groups = group_trials(trials)
    lines = [
        "| task_id | arm | trials | pass_rate | mean_quality | mean_tokens | p25 | p50 | p75 | mean_wall | tokens/success | spend | trunc_rate | cap_rate | empty_rate | compl_acc | latency | RE | RC | RR |",
        "|" + "---|" * 20,
    ]
    for task_id, arm in sorted(groups):
        group = groups[(task_id, arm)]
        stats = compute_stats(group)
        lines.append(
            "| {task} | {arm} | {n} | {pr} | {mq} | {mt} | {p25} | {p50} | {p75} | {mw} | {tps} | {spend} | {tr} | {capr} | {er} | {ca} | {lat} | {re_:.4f} | {rc:.4f} | {rr:.4f} |".format(
                task=task_id,
                arm=arm,
                n=len(group),
                pr=_fmt(stats["pass_rate"]),
                mq=_fmt(stats["mean_quality"]),
                mt=_fmt(stats["mean_tokens"]),
                p25=_fmt(stats["p25_tokens"]),
                p50=_fmt(stats["p50_tokens"]),
                p75=_fmt(stats["p75_tokens"]),
                mw=_fmt(stats["mean_wall"]),
                tps=_fmt(stats["tokens_per_success"]),
                spend=_fmt(stats["total_token_spend"]),
                tr=_fmt(stats["truncation_rate"]),
                capr=_fmt(stats["cap_exhausted_rate"]),
                er=_fmt(stats["empty_response_rate"]),
                ca=_fmt(stats["completed_response_accuracy"]),
                lat=_fmt(stats["mean_latency"]),
                re_=stats["re_reasoning_efficiency"],
                rc=stats["rc_reasoning_concentration"],
                rr=stats["rr_redundancy_rate"],
            )
        )
    return "\n".join(lines)


def generate_json_report(trials):
    groups = group_trials(trials)
    entries = []
    for task_id, arm in sorted(groups):
        group = groups[(task_id, arm)]
        entry = {"task_id": task_id, "arm": arm, "trials": len(group)}
        entry.update(compute_stats(group))
        entries.append(entry)
    return json.dumps({"groups": entries}, indent=2, sort_keys=True)


def generate_per_task_comparison(trials):
    groups = group_trials(trials)
    arms = sorted({arm for _, arm in groups})
    tasks = sorted({task for task, _ in groups})
    tables = []
    for task in tasks:
        stats_by_arm = {
            arm: compute_stats(groups[(task, arm)])
            for arm in arms
            if (task, arm) in groups
        }
        lines = [
            "| task_id | metric | " + " | ".join(arms) + " |",
            "|" + "---|" * (2 + len(arms)),
        ]
        for metric in COMPARISON_METRICS:
            cells = [
                _fmt(stats_by_arm[arm][metric]) if arm in stats_by_arm else "-"
                for arm in arms
            ]
            lines.append("| {} | {} | {} |".format(task, metric, " | ".join(cells)))
        tables.append("\n".join(lines))
    return "\n\n".join(tables)
