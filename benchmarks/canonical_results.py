#!/usr/bin/env python3
"""Canonical offline results generator for immutable trial archives.

Recomputes canonical result statistics from one or more explicit, immutable
trial-JSON inputs WITHOUT any model evaluations, and emits one deterministic
canonical JSON payload plus a deterministic Markdown summary suitable for
README/paper generation.

CLI:
    python3 benchmarks/canonical_results.py INPUT... -o OUTDIR [options]

Guarantees and semantics
------------------------
* Inputs are immutable: they are only read and hashed (SHA-256).  Raw
  responses (``final_answer`` and friends) are NEVER copied into the output
  unless ``--include-raw-trials`` is given.  Recorded manifest metadata
  (including ``request_params`` generation request snapshots) is screened:
  secret-bearing keys are masked, so no API key is ever copied.
* OUTDIR must not already exist; creation refuses to overwrite and is
  atomic-ish: the directory is created (with ``exist_ok=False``) only after
  every input parses and every statistic is computed, and each output file
  is written via temp file + rename.  A failed write removes the directory.
* The payload is deterministic for a given set of inputs and options; no
  wall-clock timestamps are recorded.  Source file paths are metadata.
  ``analysis_provenance`` additionally pins the analysis implementation
  (SHA-256 + repo-relative path of the canonical generator, the stats
  module, and the outcome predicates) together with the stats options.
* Accuracy is reported as two distinct, clearly labeled estimands:
  trial-pooled *micro* accuracy and task-equal-weighted *macro* accuracy.
  They are never mixed silently — every table and JSON field is labeled.
* ``total_spend_per_success`` includes failed attempts in the numerator and
  is ``null`` (undefined) at zero successes — never ``0.0``.
* Truncation / cap-exhausted / empty / grader-error / completed-response
  outcomes use only fields actually present on each trial
  (``benchmarks/report.py`` predicates; grader errors are the explicit
  ``failure_class="grader_error"`` marker); ``finish_reason`` and
  ``failure_class`` are never fabricated.
* Paired comparisons use ``benchmarks/stats.py``: explicit
  ``(benchmark, task_id, trial)`` pairing, within-task averaging over
  repeated trials, and Holm step-down multiplicity correction.

Trial JSON inputs may be a plain list of trial dicts or an object with a
``"trials"`` list (other top-level keys are recorded as available manifest
metadata).  Trials missing a ``benchmark`` field inherit the input's
default: the top-level ``benchmark`` value when present, else the file
stem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    # script mode: benchmarks/ is on sys.path
    from stats import generate_stats_report
    from report import (
        _is_cap_exhausted,
        _is_completed_response,
        _is_empty_response,
        _is_truncated,
    )
except ImportError:  # package mode (tests import benchmarks.canonical_results)
    from benchmarks.stats import generate_stats_report
    from benchmarks.report import (
        _is_cap_exhausted,
        _is_completed_response,
        _is_empty_response,
        _is_truncated,
    )

SCHEMA = "canonical-results/1"
ANALYSIS_SCHEMA = "canonical-analysis/1"
CANONICAL_JSON_NAME = "canonical_results.json"
CANONICAL_MD_NAME = "canonical_results.md"

# The analysis implementation whose identity is pinned in
# ``analysis_provenance``: the canonical generator itself, the statistics
# module behind every reported test, and the trial-outcome predicates it
# imports.  Keys are repo-relative paths; values are the module filenames
# resolved next to this file (independent of the working directory, so
# the recorded paths and hashes stay deterministic).
_ANALYSIS_FILES = (
    ("benchmarks/canonical_results.py", "canonical_results.py"),
    ("benchmarks/report.py", "report.py"),
    ("benchmarks/stats.py", "stats.py"),
)

CLASSIC_ARM = "classic"
TAHOE_ARM = "tahoe"

# Trial-level keys recognized as prompt/grader/model/generation metadata.
# Only keys actually present are recorded — metadata is never fabricated.
# ``request_params`` captures the new runners' complete generation request
# snapshots; recorded values are passed through _redact_secrets so no API key
# or other secret is ever copied into the canonical output.
TRIAL_METADATA_KEYS = (
    "model",
    "prompt",
    "prompt_path",
    "prompt_id",
    "system_prompt",
    "grader",
    "grader_type",
    "generation",
    "generation_params",
    "request_params",
    "max_tokens",
    "max_output_tokens",
    "output_token_cap",
    "temperature",
    "seed",
    "api_base",
    "experiment",
    "version",
)

ESTIMANDS = {
    "micro_accuracy": (
        "Trial-pooled (micro) accuracy within a benchmark/arm: successes / "
        "trials. Tasks with more repeated trials weigh proportionally more."
    ),
    "macro_accuracy": (
        "Task-equal-weighted (macro) accuracy: the mean over tasks of each "
        "task's trial-mean pass rate; every task weighs the same regardless "
        "of how many trials it has."
    ),
    "token_sums": (
        "Exact sums of recorded input/output/total token counts over all "
        "trials in scope."
    ),
    "total_spend_per_success": (
        "sum(total_tokens over ALL attempts, failures included) / number of "
        "successes; null (undefined) when there are zero successes."
    ),
    "token_ratio_tahoe_over_classic": (
        "tahoe token spend / classic token spend for the same scope; null "
        "when the classic spend is zero."
    ),
    "outcomes": (
        "Truncation / cap-exhausted / empty / grader-error / completed "
        "counts derived only from fields actually present on each trial "
        "(explicit flags, finish_reason, recorded output caps, final_answer, "
        "failure_class); finish_reason and failure_class are never "
        "fabricated for archives that do not record them, and "
        "grader_error is counted only when failure_class literally "
        "equals \"grader_error\"."
    ),
    "paired_comparisons": (
        "Keyed task-cluster paired comparisons on exact (benchmark, task_id, "
        "trial) identity; repeated matched trials are averaged within tasks; "
        "Holm step-down correction over the comparison family."
    ),
}


# ---------------------------------------------------------------------------
# Loading and hashing
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _task_set_hash(trials: list[dict]) -> str:
    """SHA-256 over the sorted set of (benchmark, task_id) identities."""
    digest = hashlib.sha256()
    for key in sorted({f"{t['benchmark']}\x1f{t['task_id']}" for t in trials}):
        digest.update(key.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _analysis_file_hashes() -> dict[str, str]:
    """SHA-256 of each analysis implementation file, by repo-relative path.

    Input hashes alone do not pin what the numbers mean: the same inputs
    analyzed by a different ``stats.py``/``canonical_results.py`` would
    yield different canonical results.  This records the implementation
    identity alongside them.  Nothing here depends on the working
    directory or the wall clock, so the block stays deterministic.
    """
    here = Path(__file__).resolve().parent
    return {
        repo_rel: _sha256_bytes((here / filename).read_bytes())
        for repo_rel, filename in _ANALYSIS_FILES
    }


# Substring markers for secret-bearing keys inside recorded metadata values.
# Deliberately narrow: they never match legitimate generation settings such
# as "max_tokens", "output_token_cap", "model", "temperature" or "seed".
_SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "password",
    "authorization",
    "auth_token",
    "access_token",
    "credential",
)


def _redact_secrets(value: Any) -> Any:
    """Recursively mask values of secret-bearing keys inside *value*.

    Defense in depth: request_params snapshots from the runners do not
    contain API keys, but if one ever appears its value is replaced with a
    ``[redacted]`` marker so no secret is copied into canonical output.
    """
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in _SECRET_KEY_MARKERS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _build_manifest(top_level: dict, trials: list[dict]) -> dict:
    """Record available prompt/grader/model/generation metadata.

    Nothing is invented: top-level metadata keys are copied as recorded,
    and per-trial metadata is reduced to the sorted set of distinct values
    actually observed for recognized metadata keys.  Recorded values pass
    through _redact_secrets so secrets are never copied.
    """
    observed: dict[str, set[str]] = defaultdict(set)
    for trial in trials:
        for key in TRIAL_METADATA_KEYS:
            if key in trial:
                try:
                    observed[key].add(
                        json.dumps(_redact_secrets(trial[key]), sort_keys=True)
                    )
                except (TypeError, ValueError):
                    observed[key].add(repr(trial[key]))
    return {
        "top_level": _redact_secrets(dict(top_level)),
        "trial_metadata": {key: sorted(observed[key]) for key in sorted(observed)},
        "available_metadata_keys": sorted(set(top_level) | set(observed)),
    }


def load_input(path: Path) -> dict[str, Any]:
    """Read one immutable trial JSON input; never writes to it."""
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    raw_bytes = path.read_bytes()
    sha256 = _sha256_bytes(raw_bytes)
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc

    if isinstance(raw, list):
        trial_list, top_level = raw, {}
    elif isinstance(raw, dict):
        trial_list = raw.get("trials")
        top_level = {k: v for k, v in raw.items() if k != "trials"}
        if not isinstance(trial_list, list):
            raise ValueError(f"{path}: dict input must contain a 'trials' list")
    else:
        raise ValueError(f"{path}: input must be a JSON list or an object with 'trials'")

    default_benchmark = top_level.get("benchmark") or path.stem
    trials: list[dict] = []
    for index, trial in enumerate(trial_list):
        if not isinstance(trial, dict):
            raise ValueError(f"{path}: trial #{index} is not an object")
        missing = [
            key for key in ("task_id", "arm", "trial")
            if key not in trial or trial[key] is None
        ]
        if missing:
            raise ValueError(f"{path}: trial #{index} missing key fields {missing}")
        normalized = dict(trial)
        normalized["benchmark"] = trial.get("benchmark") or default_benchmark
        trials.append(normalized)

    return {
        "path": str(path),
        "sha256": sha256,
        "trials": trials,
        "benchmark_default": default_benchmark,
        "manifest": _build_manifest(top_level, trials),
    }


# ---------------------------------------------------------------------------
# Metrics (estimands are always labeled; micro/macro are never mixed)
# ---------------------------------------------------------------------------


def _passed(trial: dict) -> bool:
    return bool(trial.get("passed", False))


def _token_value(trial: dict, field: str) -> int | float:
    value = trial.get(field)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"token field {field!r} must be numeric, got {value!r}")
    return value


def _is_grader_error(trial: dict) -> bool:
    """True when the trial is explicitly recorded as a grader failure.

    Derived archives relabel ungradeable trials as
    ``failure_class="grader_error"`` so they are never silently dropped
    or counted as wrong answers.  The field alone decides: a missing or
    non-``grader_error`` ``failure_class`` is never a grader error, and
    the class is never inferred from other fields.
    """
    return trial.get("failure_class") == "grader_error"


def compute_arm_metrics(trials: list[dict]) -> dict[str, Any]:
    """Exact counts plus micro and macro accuracy for one arm's trials."""
    n = len(trials)
    if n == 0:
        raise ValueError("arm metrics require at least one trial")

    by_task: dict[tuple[Any, Any], list[dict]] = defaultdict(list)
    for trial in trials:
        by_task[(trial["benchmark"], trial["task_id"])].append(trial)
    task_keys = sorted(by_task, key=lambda key: (str(key[0]), str(key[1])))

    successes = sum(1 for trial in trials if _passed(trial))
    task_rates = [
        statistics.fmean([1.0 if _passed(t) else 0.0 for t in by_task[key]])
        for key in task_keys
    ]

    input_sum = sum(_token_value(t, "input_tokens") for t in trials)
    output_sum = sum(_token_value(t, "output_tokens") for t in trials)
    total_sum = sum(_token_value(t, "total_tokens") for t in trials)
    # Total spend per success counts failed attempts; null at zero successes.
    spend_per_success = total_sum / successes if successes else None

    truncated = sum(1 for t in trials if _is_truncated(t))
    cap_exhausted = sum(1 for t in trials if _is_cap_exhausted(t))
    empty = sum(1 for t in trials if _is_empty_response(t))
    grader_error = sum(1 for t in trials if _is_grader_error(t))
    completed = [t for t in trials if _is_completed_response(t)]
    completed_passed = sum(1 for t in completed if _passed(t))

    return {
        "trials": n,
        "tasks": len(task_keys),
        "successes": successes,
        "micro_accuracy": successes / n,
        "macro_accuracy": statistics.fmean(task_rates),
        "token_sums": {
            "input_tokens": input_sum,
            "output_tokens": output_sum,
            "total_tokens": total_sum,
        },
        "total_spend_per_success": spend_per_success,
        "outcomes": {
            "truncated": {"count": truncated, "rate": truncated / n},
            "cap_exhausted": {"count": cap_exhausted, "rate": cap_exhausted / n},
            "empty_response": {"count": empty, "rate": empty / n},
            "grader_error": {"count": grader_error, "rate": grader_error / n},
            "completed_response": {
                "count": len(completed),
                "rate": len(completed) / n,
                "accuracy": (completed_passed / len(completed)) if completed else None,
            },
        },
    }


def _arm_pair_block(classic_metrics: dict, tahoe_metrics: dict) -> dict[str, Any]:
    """classic-vs-tahoe ratios and differences from labeled estimands."""
    classic_sums = classic_metrics["token_sums"]
    tahoe_sums = tahoe_metrics["token_sums"]

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    return {
        "token_sums": {"classic": classic_sums, "tahoe": tahoe_sums},
        "token_ratio_tahoe_over_classic": {
            field: ratio(tahoe_sums[field], classic_sums[field])
            for field in ("input_tokens", "output_tokens", "total_tokens")
        },
        "total_spend_per_success": {
            "classic": classic_metrics["total_spend_per_success"],
            "tahoe": tahoe_metrics["total_spend_per_success"],
        },
        "micro_accuracy_difference_tahoe_minus_classic": (
            tahoe_metrics["micro_accuracy"] - classic_metrics["micro_accuracy"]
        ),
        "macro_accuracy_difference_tahoe_minus_classic": (
            tahoe_metrics["macro_accuracy"] - classic_metrics["macro_accuracy"]
        ),
    }


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------


def build_analysis_provenance(
    seed: int,
    n_resamples: int,
    n_permutations: int,
) -> dict[str, Any]:
    """Deterministic provenance for the analysis implementation and options."""
    return {
        "schema": ANALYSIS_SCHEMA,
        "payload_schema": SCHEMA,
        "files": _analysis_file_hashes(),
        "seed": seed,
        "n_resamples": n_resamples,
        "n_permutations": n_permutations,
    }


def build_payload(
    inputs: list[dict[str, Any]],
    *,
    seed: int = 42,
    n_resamples: int = 2000,
    n_permutations: int = 2000,
    include_per_task: bool = False,
    include_raw_trials: bool = False,
) -> dict[str, Any]:
    """Build the deterministic canonical payload from loaded inputs.

    The payload pins three layers of provenance: the immutable inputs
    (``provenance.inputs``), the analysis implementation
    (``analysis_provenance`` — SHA-256 of the canonical generator, the
    statistics module, and the outcome predicates, plus the stats
    options), and the analysis options (``provenance.stats``).
    ``include_per_task`` gates both the computation and the emission of
    per-task comparisons; by default they are skipped entirely (one
    paired comparison per task dominates the runtime on large archives).
    """
    all_trials: list[dict] = []
    for inp in inputs:
        all_trials.extend(inp["trials"])
    if not all_trials:
        raise ValueError("no trials found in any input")

    arm_names = sorted({t["arm"] for t in all_trials}, key=str)

    def arm_subset(trials: list[dict], arm: str) -> list[dict]:
        return [t for t in trials if t["arm"] == arm]

    def arms_block_for(trials: list[dict]) -> dict[str, dict]:
        block = {}
        for arm in arm_names:
            subset = arm_subset(trials, arm)
            if subset:
                block[arm] = compute_arm_metrics(subset)
        return block

    def pair_block_for(trials: list[dict], arms: dict[str, dict]) -> dict | None:
        classic = arm_subset(trials, CLASSIC_ARM)
        tahoe = arm_subset(trials, TAHOE_ARM)
        if not classic or not tahoe:
            return None
        return _arm_pair_block(arms[CLASSIC_ARM], arms[TAHOE_ARM])

    benchmarks_block: dict[str, dict] = {}
    for benchmark in sorted({t["benchmark"] for t in all_trials}, key=str):
        bench_trials = [t for t in all_trials if t["benchmark"] == benchmark]
        arms = arms_block_for(bench_trials)
        entry: dict[str, Any] = {
            "arms": arms,
            "task_set_sha256": _task_set_hash(bench_trials),
        }
        pair = pair_block_for(bench_trials, arms)
        if pair is not None:
            entry["classic_vs_tahoe"] = pair
        benchmarks_block[benchmark] = entry

    overall_arms = arms_block_for(all_trials)
    overall: dict[str, Any] = {"arms": overall_arms}
    overall_pair = pair_block_for(all_trials, overall_arms)
    if overall_pair is not None:
        overall["classic_vs_tahoe"] = overall_pair

    stats_report = generate_stats_report(
        all_trials,
        n_resamples=n_resamples,
        n_permutations=n_permutations,
        seed=seed,
        include_per_task=include_per_task,
    )

    provenance_inputs = []
    for inp in inputs:
        counts: dict[str, int] = defaultdict(int)
        for trial in inp["trials"]:
            counts[trial["arm"]] += 1
        provenance_inputs.append({
            "path": inp["path"],
            "sha256": inp["sha256"],
            "trial_count": len(inp["trials"]),
            "trial_counts_by_arm": dict(sorted(counts.items())),
            "benchmark_default": inp["benchmark_default"],
            "benchmarks": sorted({t["benchmark"] for t in inp["trials"]}, key=str),
            "task_set_sha256": _task_set_hash(inp["trials"]),
            "manifest": inp["manifest"],
        })

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "estimands": ESTIMANDS,
        "analysis_provenance": build_analysis_provenance(
            seed, n_resamples, n_permutations,
        ),
        "provenance": {
            "inputs": provenance_inputs,
            "total_trials": len(all_trials),
            "include_raw_trials": bool(include_raw_trials),
            "stats": {
                "seed": seed,
                "n_resamples": n_resamples,
                "n_permutations": n_permutations,
            },
        },
        "overall": overall,
        "benchmarks": benchmarks_block,
        "paired_comparisons": stats_report["comparisons"],
        "multiplicity": stats_report["multiplicity"],
    }
    if include_per_task:
        payload["per_task"] = stats_report["per_task"]
    if include_raw_trials:
        payload["raw_trials"] = all_trials
    return payload


# ---------------------------------------------------------------------------
# Markdown rendering (deterministic; no wall-clock timestamps)
# ---------------------------------------------------------------------------

_ARM_HEADER = (
    "| arm | trials | tasks | successes | micro acc (trial-pooled) "
    "| macro acc (task-eq-wt) | input tok | output tok | total tok "
    "| total spend/success | truncated | cap-exhausted | empty "
    "| grader err | completed | completed acc |"
)
_ARM_RULE = "|" + "---|" * 16

_PAIR_HEADER = (
    "| scope | input tok ratio (tahoe/classic) | output tok ratio (tahoe/classic) "
    "| total tok ratio (tahoe/classic) | total spend/success classic "
    "| total spend/success tahoe | micro acc Δ (tahoe−classic) "
    "| macro acc Δ (tahoe−classic) |"
)
_PAIR_RULE = "|" + "---|" * 8

_COMPARISON_HEADER = (
    "| comparison | tasks | pairs | task-mean pass (a) | task-mean pass (b) "
    "| pass diff | mean token diff | perm p | perm p (Holm) "
    "| pass perm p (Holm) | z p (Holm) | wilcoxon p (Holm) |"
)
_COMPARISON_RULE = "|" + "---|" * 12


def _fmt(value, spec: str = ".4f") -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return format(float(value), spec)


def _fmt_signed(value, spec: str = ".4f") -> str:
    if value is None:
        return "—"
    return format(float(value), "+" + spec)


def _md_escape(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _short_json(value, limit: int = 160) -> str:
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _arm_row(arm: str, metrics: dict) -> str:
    sums = metrics["token_sums"]
    outcomes = metrics["outcomes"]
    completed = outcomes["completed_response"]
    return ("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} "
            "| {} | {} | {} | {} |").format(
        _md_escape(arm),
        metrics["trials"],
        metrics["tasks"],
        metrics["successes"],
        _fmt(metrics["micro_accuracy"]),
        _fmt(metrics["macro_accuracy"]),
        _fmt(sums["input_tokens"], ".1f"),
        _fmt(sums["output_tokens"], ".1f"),
        _fmt(sums["total_tokens"], ".1f"),
        _fmt(metrics["total_spend_per_success"], ".2f"),
        outcomes["truncated"]["count"],
        outcomes["cap_exhausted"]["count"],
        outcomes["empty_response"]["count"],
        outcomes["grader_error"]["count"],
        completed["count"],
        _fmt(completed["accuracy"]),
    )


def _pair_row(scope: str, pair: dict) -> str:
    ratios = pair["token_ratio_tahoe_over_classic"]
    spend = pair["total_spend_per_success"]
    return "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        _md_escape(scope),
        _fmt(ratios["input_tokens"]),
        _fmt(ratios["output_tokens"]),
        _fmt(ratios["total_tokens"]),
        _fmt(spend["classic"], ".2f"),
        _fmt(spend["tahoe"], ".2f"),
        _fmt_signed(pair["micro_accuracy_difference_tahoe_minus_classic"]),
        _fmt_signed(pair["macro_accuracy_difference_tahoe_minus_classic"]),
    )


def render_markdown(payload: dict) -> str:
    lines: list[str] = []
    w = lines.append

    w("# Canonical results")
    w("")
    w(
        f"Schema `{payload['schema']}`. Deterministic: no wall-clock "
        "timestamps; statistics recomputed offline from immutable trial "
        "inputs — no model evaluations."
    )
    w("")

    provenance = payload["provenance"]
    w("## Inputs")
    w("")
    w("| input | sha-256 | trials | trials by arm | task-set sha-256 |")
    w("|---|---|---|---|---|")
    for inp in provenance["inputs"]:
        by_arm = ", ".join(
            f"{arm}: {count}" for arm, count in inp["trial_counts_by_arm"].items()
        )
        w(
            f"| `{_md_escape(inp['path'])}` | `{inp['sha256']}` "
            f"| {inp['trial_count']} | {_md_escape(by_arm)} "
            f"| `{inp['task_set_sha256']}` |"
        )
    w("")
    w(f"Total trials: {provenance['total_trials']}.")
    w("")
    w("### Available manifest metadata (recorded as available; never fabricated)")
    w("")
    recorded_any = False
    for inp in provenance["inputs"]:
        manifest = inp["manifest"]
        top_level = manifest["top_level"]
        trial_metadata = manifest["trial_metadata"]
        if not top_level and not trial_metadata:
            continue
        recorded_any = True
        w(f"- **`{_md_escape(inp['path'])}`**")
        for key in sorted(top_level):
            w(f"  - `{_md_escape(key)}`: {_short_json(top_level[key])}")
        for key in sorted(trial_metadata):
            w(f"  - trial field `{_md_escape(key)}`: {_short_json(trial_metadata[key])}")
    if not recorded_any:
        w("- none recorded")
    w("")

    analysis = payload["analysis_provenance"]
    w("### Analysis implementation")
    w("")
    w("| source file | sha-256 |")
    w("|---|---|")
    for repo_rel in sorted(analysis["files"]):
        w(f"| `{_md_escape(repo_rel)}` | `{analysis['files'][repo_rel]}` |")
    w("")
    w(
        f"Options: seed {analysis['seed']}, {analysis['n_resamples']} "
        f"bootstrap resamples, {analysis['n_permutations']} permutation "
        f"draws; payload schema `{payload['schema']}`, analysis schema "
        f"`{analysis['schema']}`."
    )
    w("")

    w("## Estimands")
    w("")
    for name in sorted(payload["estimands"]):
        w(f"- **{name}** — {payload['estimands'][name]}")
    w("")

    w("## Overall")
    w("")
    w(_ARM_HEADER)
    w(_ARM_RULE)
    for arm in sorted(payload["overall"]["arms"], key=str):
        w(_arm_row(arm, payload["overall"]["arms"][arm]))
    w("")
    overall_pair = payload["overall"].get("classic_vs_tahoe")
    if overall_pair is not None:
        w(_PAIR_HEADER)
        w(_PAIR_RULE)
        w(_pair_row("overall (all benchmarks pooled)", overall_pair))
    else:
        present = ", ".join(sorted(payload["overall"]["arms"], key=str)) or "none"
        w(f"classic vs tahoe ratios unavailable (arms present: {present}).")
    w("")

    w("## Benchmarks")
    for benchmark in sorted(payload["benchmarks"], key=str):
        entry = payload["benchmarks"][benchmark]
        w("")
        w(f"### `{_md_escape(benchmark)}`")
        w("")
        w(f"Task-set sha-256: `{entry['task_set_sha256']}`.")
        w("")
        w(_ARM_HEADER)
        w(_ARM_RULE)
        for arm in sorted(entry["arms"], key=str):
            w(_arm_row(arm, entry["arms"][arm]))
        w("")
        pair = entry.get("classic_vs_tahoe")
        if pair is not None:
            w(_PAIR_HEADER)
            w(_PAIR_RULE)
            w(_pair_row(benchmark, pair))
        else:
            present = ", ".join(sorted(entry["arms"], key=str)) or "none"
            w(f"classic vs tahoe ratios unavailable (arms present: {present}).")
        w("")

    w("## Paired task-cluster comparisons (Holm-corrected)")
    w("")
    comparisons = payload["paired_comparisons"]
    if comparisons:
        w(_COMPARISON_HEADER)
        w(_COMPARISON_RULE)
        for key in sorted(comparisons):
            comp = comparisons[key]
            w(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    _md_escape(key),
                    comp["n_tasks"],
                    comp["n_pairs"],
                    _fmt(comp["pass_rate_a"]),
                    _fmt(comp["pass_rate_b"]),
                    _fmt_signed(comp["pass_rate_difference"]),
                    _fmt_signed(comp["mean_token_difference"], ".1f"),
                    _fmt(comp["permutation_p"]),
                    _fmt(comp["permutation_p_holm"]),
                    _fmt(comp["pass_rate_permutation_p_holm"]),
                    _fmt(comp["z_test"].get("p_value_holm")),
                    _fmt(comp["wilcoxon"].get("p_value_holm")),
                )
            )
        w("")
        w(
            f"Multiplicity: {payload['multiplicity']['method']} step-down "
            f"correction over {len(comparisons)} comparisons "
            f"(family: {payload['multiplicity']['family']}); pairing key: "
            "(benchmark, task_id, trial)."
        )
    else:
        w("No arm pair had matched (benchmark, task_id, trial) keys.")
    w("")
    w(
        'Notes: "—" marks undefined values (JSON null): zero successes for '
        "total spend/success, zero classic spend for ratios, no completed "
        "responses for completed accuracy. Micro and macro accuracy are "
        "distinct estimands and are never mixed; see Estimands above."
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Output writing (refuse overwrite; atomic-ish creation)
# ---------------------------------------------------------------------------


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _refusal_message(out: Path) -> str:
    return (
        f"error: output directory already exists, refusing to overwrite: {out}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="canonical_results.py",
        description=(
            "Build canonical, deterministic results (JSON + Markdown) from "
            "immutable trial JSON inputs. No model evaluations."
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help=(
            "one or more immutable trial JSON files (a list of trials, or an "
            "object with a 'trials' list)"
        ),
    )
    parser.add_argument(
        "-o",
        "--out",
        required=True,
        type=Path,
        help="output directory; must not already exist (overwrite is refused)",
    )
    parser.add_argument(
        "--include-raw-trials",
        action="store_true",
        help="copy raw trial records (including responses) into the JSON payload",
    )
    parser.add_argument(
        "--include-per-task",
        action="store_true",
        help="include the keyed per-task paired comparison block in the JSON",
    )
    parser.add_argument("--seed", type=int, default=42, help="stats RNG seed")
    parser.add_argument(
        "--n-resamples", type=int, default=2000, help="bootstrap resamples"
    )
    parser.add_argument(
        "--n-permutations", type=int, default=2000, help="permutation test draws"
    )
    args = parser.parse_args(argv)

    out = args.out
    if out.exists():
        print(_refusal_message(out), file=sys.stderr)
        return 2

    try:
        loaded = [load_input(path) for path in args.inputs]
        payload = build_payload(
            loaded,
            seed=args.seed,
            n_resamples=args.n_resamples,
            n_permutations=args.n_permutations,
            include_per_task=args.include_per_task,
            include_raw_trials=args.include_raw_trials,
        )
        markdown = render_markdown(payload)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(_refusal_message(out), file=sys.stderr)
        return 2

    try:
        _write_atomic(out / CANONICAL_JSON_NAME, _canonical_json(payload))
        _write_atomic(out / CANONICAL_MD_NAME, markdown)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        shutil.rmtree(out, ignore_errors=True)
        print(f"error: failed to write outputs: {exc}", file=sys.stderr)
        return 1

    print(
        f"wrote {out / CANONICAL_JSON_NAME} and {out / CANONICAL_MD_NAME} "
        f"({payload['provenance']['total_trials']} trials, "
        f"{len(loaded)} input(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
