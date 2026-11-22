#!/usr/bin/env python3
"""Offline deterministic renderer for canonical-results JSON payloads.

Reads an existing canonical-results artifact (schema ``canonical-results/1``,
as emitted by ``benchmarks/canonical_results.py``) and renders, from the
SAME payload:

  * a standalone Markdown results document, and
  * a LaTeX booktabs table fragment,

so README/docs and the paper never maintain conflicting hand-calculated
values.  No model evaluations and no wall-clock timestamps: the render is a
pure function of the payload bytes.

Integrity rules
---------------
* The canonical JSON input is read-only; the tool refuses to write to it.
* Nothing is invented: every displayed number is copied from the payload.
  Undefined values (JSON null — e.g. total spend/success at zero successes,
  token ratios over zero classic spend, completed accuracy with no
  completed responses) render as an explicit null marker, never ``0.0``.
* A payload missing required fields is refused loudly (the error names the
  JSON path) instead of being rendered partially.
* Grader-error outcomes are never dropped silently: the per-arm
  ``grader_error`` outcome aggregate is rendered directly (a grader-error
  column in every arm table plus an exact per-arm count in the lineage
  note).  When a legacy payload lacks the aggregate, the count renders as
  an explicit "unknown" — never 0 — and raw trials, when present, act only
  as a cross-check that must agree with the recorded aggregate.
* The analysis implementation lineage (``analysis_provenance``: the
  SHA-256 of the generator/statistics/predicates modules and the stats
  options) is rendered in both formats, so a rendered document always
  states which analysis implementation produced its numbers.
* Grader lineage is surfaced wherever it is recorded: trial-level grader
  metadata, a direct top-level grader value, or the grader provenance
  that derived manifests nest under ``manifest.top_level.manifest`` —
  the ``grader`` identity record (name, version, source, and its
  sha-256) plus its sibling ``grader_version`` tag, which fills the
  version slot when the record carries none (e.g. ``name tag (source,
  sha-256 ...)``).  Absent provenance stays "not recorded" — never
  invented; malformed tags are ignored.

Generated blocks in existing text files
---------------------------------------
Text files can carry explicitly marked generated blocks that this tool
updates (``--update``) or verifies (``--check``).  Markdown:

    <!-- CANONICAL_RESULTS:BEGIN overall -->
    ...generated content...
    <!-- CANONICAL_RESULTS:END overall -->

LaTeX:

    % CANONICAL_RESULTS:BEGIN overall
    ...generated content...
    % CANONICAL_RESULTS:END overall

The block name selects a section renderer: ``full``, ``inputs``,
``analysis``, ``estimands``, ``overall``, ``pair``, ``summary``,
``benchmarks``, ``paired``.  A name is either a plain section name
(``overall``) or a named instance ``SECTION@INSTANCE`` (``summary@glm``,
``pair@oss``), so several canonical payloads can carry their own blocks in
the SAME text file without pooling their models.  The section must be a
valid block name and the nonempty instance suffix (letters, digits, ``.``,
``_``, ``-``) only distinguishes blocks: it never changes the rendered
content.  Exact duplicate marker names remain refused (ambiguous); the
same section with distinct suffixes is allowed.

Only the content between the markers changes; everything outside the
markers is preserved byte-for-byte, updates are idempotent, and check mode
never modifies anything.  The scanner is deliberately strict: missing,
unbalanced, duplicated (ambiguous), nested, name-mismatched, malformed,
or unknown-name markers fail the run with a nonzero exit status and the
target untouched.

CLI:
    python3 benchmarks/render_canonical_docs.py PAYLOAD \
        --markdown DOC.md --latex TABLES.tex \
        --update README.md --check paper/results.tex \
        --block summary@glm

``--block NAME`` (repeatable) restricts ``--update``/``--check`` to the
named full marker name(s) — plain (``overall``) or instance
(``summary@glm``) — leaving every other block byte-untouched; a selected
name missing from the file is refused.  Without ``--block`` every marked
block in each target is updated/checked, as before.

Exit codes: 0 success; 1 error; 3 drift detected by --check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCHEMA = "canonical-results/1"

# Null markers per format: undefined (JSON null) values are never rendered
# as 0.0 — they get an explicit dash marker.
_NULL_MARK = {"md": "—", "tex": "---"}

# ---------------------------------------------------------------------------
# Payload validation (strict: refuse instead of inventing or dropping)
# ---------------------------------------------------------------------------


class RenderError(ValueError):
    """User-facing failure: bad payload, markers, or usage."""


def _fail(path: str, message: str) -> None:
    raise RenderError(f"canonical payload field {path}: {message}")


def _get(container: Any, container_path: str, key: str) -> Any:
    if not isinstance(container, dict):
        _fail(container_path, "must be a JSON object")
    if key not in container:
        _fail(f"{container_path}[{key!r}]", "is missing")
    return container[key]


def _check_str(value: Any, path: str) -> None:
    if not isinstance(value, str):
        _fail(path, "must be a string")


def _check_int(value: Any, path: str, *, minimum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer")
    if minimum is not None and value < minimum:
        _fail(path, f"must be >= {minimum}")


def _check_num(value: Any, path: str, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        suffix = " or null" if allow_none else ""
        _fail(path, f"must be a JSON number{suffix}")


def _validate_arm_metrics(metrics: Any, path: str) -> None:
    if not isinstance(metrics, dict):
        _fail(path, "must be a JSON object")
    _check_int(_get(metrics, path, "trials"), f"{path}['trials']", minimum=1)
    _check_int(_get(metrics, path, "tasks"), f"{path}['tasks']", minimum=1)
    _check_int(
        _get(metrics, path, "successes"), f"{path}['successes']", minimum=0
    )
    for name in ("micro_accuracy", "macro_accuracy"):
        _check_num(_get(metrics, path, name), f"{path}[{name!r}]")
    sums = _get(metrics, path, "token_sums")
    sums_path = f"{path}['token_sums']"
    if not isinstance(sums, dict):
        _fail(sums_path, "must be a JSON object")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        _check_num(_get(sums, sums_path, field), f"{sums_path}[{field!r}]")
    _check_num(
        _get(metrics, path, "total_spend_per_success"),
        f"{path}['total_spend_per_success']",
        allow_none=True,
    )
    outcomes = _get(metrics, path, "outcomes")
    outcomes_path = f"{path}['outcomes']"
    if not isinstance(outcomes, dict):
        _fail(outcomes_path, "must be a JSON object")
    for name in ("truncated", "cap_exhausted", "empty_response"):
        outcome = _get(outcomes, outcomes_path, name)
        outcome_path = f"{outcomes_path}[{name!r}]"
        if not isinstance(outcome, dict):
            _fail(outcome_path, "must be a JSON object")
        _check_int(
            _get(outcome, outcome_path, "count"),
            f"{outcome_path}['count']",
            minimum=0,
        )
        _check_num(_get(outcome, outcome_path, "rate"), f"{outcome_path}['rate']")
    # Legacy payloads predate the grader_error aggregate: absent is
    # accepted, but it is then never rendered as zero (see _arm_row).
    if "grader_error" in outcomes:
        outcome = outcomes["grader_error"]
        outcome_path = f"{outcomes_path}['grader_error']"
        if not isinstance(outcome, dict):
            _fail(outcome_path, "must be a JSON object")
        _check_int(
            _get(outcome, outcome_path, "count"),
            f"{outcome_path}['count']",
            minimum=0,
        )
        _check_num(_get(outcome, outcome_path, "rate"), f"{outcome_path}['rate']")
    completed = _get(outcomes, outcomes_path, "completed_response")
    completed_path = f"{outcomes_path}['completed_response']"
    if not isinstance(completed, dict):
        _fail(completed_path, "must be a JSON object")
    _check_int(
        _get(completed, completed_path, "count"),
        f"{completed_path}['count']",
        minimum=0,
    )
    _check_num(_get(completed, completed_path, "rate"), f"{completed_path}['rate']")
    _check_num(
        _get(completed, completed_path, "accuracy"),
        f"{completed_path}['accuracy']",
        allow_none=True,
    )


def _validate_pair_block(pair: Any, path: str) -> None:
    if not isinstance(pair, dict):
        _fail(path, "must be a JSON object")
    sums = _get(pair, path, "token_sums")
    sums_path = f"{path}['token_sums']"
    if not isinstance(sums, dict):
        _fail(sums_path, "must be a JSON object")
    for arm in ("classic", "tahoe"):
        arm_sums = _get(sums, sums_path, arm)
        arm_path = f"{sums_path}[{arm!r}]"
        if not isinstance(arm_sums, dict):
            _fail(arm_path, "must be a JSON object")
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            _check_num(
                _get(arm_sums, arm_path, field), f"{arm_path}[{field!r}]"
            )
    ratios = _get(pair, path, "token_ratio_tahoe_over_classic")
    ratios_path = f"{path}['token_ratio_tahoe_over_classic']"
    if not isinstance(ratios, dict):
        _fail(ratios_path, "must be a JSON object")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        _check_num(
            _get(ratios, ratios_path, field),
            f"{ratios_path}[{field!r}]",
            allow_none=True,
        )
    spend = _get(pair, path, "total_spend_per_success")
    spend_path = f"{path}['total_spend_per_success']"
    if not isinstance(spend, dict):
        _fail(spend_path, "must be a JSON object")
    for arm in ("classic", "tahoe"):
        _check_num(
            _get(spend, spend_path, arm),
            f"{spend_path}[{arm!r}]",
            allow_none=True,
        )
    for name in (
        "micro_accuracy_difference_tahoe_minus_classic",
        "macro_accuracy_difference_tahoe_minus_classic",
    ):
        _check_num(_get(pair, path, name), f"{path}[{name!r}]")


def validate_payload(payload: Any) -> None:
    """Validate a canonical-results payload strictly, or raise RenderError.

    Everything this renderer displays must already be present in the
    payload: nothing is invented, and a payload that cannot support the
    full render is refused loudly instead of rendered partially.
    """
    if not isinstance(payload, dict):
        raise RenderError("canonical payload must be a JSON object")
    if payload.get("schema") != SCHEMA:
        raise RenderError(
            f"unsupported schema {payload.get('schema')!r}; expected {SCHEMA!r}"
        )

    estimands = _get(payload, "payload", "estimands")
    if not isinstance(estimands, dict) or not estimands:
        _fail("payload['estimands']", "must be a non-empty object")
    for name, text in estimands.items():
        if not isinstance(text, str):
            _fail(f"payload['estimands'][{name!r}]", "must be a string")

    provenance = _get(payload, "payload", "provenance")
    prov_path = "payload['provenance']"
    inputs = _get(provenance, prov_path, "inputs")
    if not isinstance(inputs, list) or not inputs:
        _fail(f"{prov_path}['inputs']", "must be a non-empty list")
    total_trials = 0
    for index, entry in enumerate(inputs):
        path = f"{prov_path}['inputs'][{index}]"
        if not isinstance(entry, dict):
            _fail(path, "must be a JSON object")
        for key in ("path", "sha256", "task_set_sha256", "benchmark_default"):
            _check_str(_get(entry, path, key), f"{path}[{key!r}]")
        _check_int(
            _get(entry, path, "trial_count"),
            f"{path}['trial_count']",
            minimum=0,
        )
        total_trials += entry["trial_count"]
        counts = _get(entry, path, "trial_counts_by_arm")
        counts_path = f"{path}['trial_counts_by_arm']"
        if not isinstance(counts, dict):
            _fail(counts_path, "must be a JSON object")
        for arm, count in counts.items():
            _check_int(count, f"{counts_path}[{arm!r}]", minimum=0)
        benchmarks_seen = _get(entry, path, "benchmarks")
        if not isinstance(benchmarks_seen, list):
            _fail(f"{path}['benchmarks']", "must be a list")
        manifest = _get(entry, path, "manifest")
        manifest_path = f"{path}['manifest']"
        if not isinstance(manifest, dict):
            _fail(manifest_path, "must be a JSON object")
        for key in ("top_level", "trial_metadata"):
            block = _get(manifest, manifest_path, key)
            if not isinstance(block, dict):
                _fail(f"{manifest_path}[{key!r}]", "must be a JSON object")
        for field, values in manifest["trial_metadata"].items():
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                _fail(
                    f"{manifest_path}['trial_metadata'][{field!r}]",
                    "must be a list of strings",
                )
        available = _get(manifest, manifest_path, "available_metadata_keys")
        if not isinstance(available, list):
            _fail(f"{manifest_path}['available_metadata_keys']", "must be a list")
    _check_int(
        _get(provenance, prov_path, "total_trials"),
        f"{prov_path}['total_trials']",
        minimum=0,
    )
    if provenance["total_trials"] != total_trials:
        _fail(
            f"{prov_path}['total_trials']",
            f"does not match the sum of input trial_count values ({total_trials})",
        )
    include_raw = _get(provenance, prov_path, "include_raw_trials")
    if not isinstance(include_raw, bool):
        _fail(f"{prov_path}['include_raw_trials']", "must be a boolean")
    stats = _get(provenance, prov_path, "stats")
    if not isinstance(stats, dict):
        _fail(f"{prov_path}['stats']", "must be a JSON object")
    if include_raw and "raw_trials" not in payload:
        _fail(
            "payload['raw_trials']",
            "include_raw_trials is true but raw trials are missing",
        )
    if "raw_trials" in payload:
        raw = payload["raw_trials"]
        if not isinstance(raw, list) or any(
            not isinstance(trial, dict) for trial in raw
        ):
            _fail("payload['raw_trials']", "must be a list of trial objects")

    # Analysis implementation lineage: what produced these numbers.
    analysis = _get(payload, "payload", "analysis_provenance")
    analysis_path = "payload['analysis_provenance']"
    if not isinstance(analysis, dict):
        _fail(analysis_path, "must be a JSON object")
    for name in ("schema", "payload_schema"):
        _check_str(_get(analysis, analysis_path, name), f"{analysis_path}[{name!r}]")
    if analysis["payload_schema"] != payload["schema"]:
        _fail(
            f"{analysis_path}['payload_schema']",
            f"does not match the payload schema {payload['schema']!r}",
        )
    files = _get(analysis, analysis_path, "files")
    files_path = f"{analysis_path}['files']"
    if not isinstance(files, dict) or not files:
        _fail(files_path, "must be a non-empty object")
    for repo_rel, sha in files.items():
        _check_str(sha, f"{files_path}[{repo_rel!r}]")
    for name in ("seed", "n_resamples", "n_permutations"):
        _check_int(_get(analysis, analysis_path, name), f"{analysis_path}[{name!r}]", minimum=0)

    overall = _get(payload, "payload", "overall")
    overall_path = "payload['overall']"
    arms = _get(overall, overall_path, "arms")
    if not isinstance(arms, dict) or not arms:
        _fail(f"{overall_path}['arms']", "must be a non-empty object")
    for arm, metrics in arms.items():
        _validate_arm_metrics(metrics, f"{overall_path}['arms'][{arm!r}]")
    if "classic_vs_tahoe" in overall:
        _validate_pair_block(
            overall["classic_vs_tahoe"], f"{overall_path}['classic_vs_tahoe']"
        )

    benchmarks = _get(payload, "payload", "benchmarks")
    if not isinstance(benchmarks, dict):
        _fail("payload['benchmarks']", "must be a JSON object")
    for benchmark, entry in benchmarks.items():
        path = f"payload['benchmarks'][{benchmark!r}]"
        if not isinstance(entry, dict):
            _fail(path, "must be a JSON object")
        bench_arms = _get(entry, path, "arms")
        if not isinstance(bench_arms, dict) or not bench_arms:
            _fail(f"{path}['arms']", "must be a non-empty object")
        for arm, metrics in bench_arms.items():
            _validate_arm_metrics(metrics, f"{path}['arms'][{arm!r}]")
        _check_str(
            _get(entry, path, "task_set_sha256"), f"{path}['task_set_sha256']"
        )
        if "classic_vs_tahoe" in entry:
            _validate_pair_block(
                entry["classic_vs_tahoe"], f"{path}['classic_vs_tahoe']"
            )

    comparisons = _get(payload, "payload", "paired_comparisons")
    if not isinstance(comparisons, dict):
        _fail("payload['paired_comparisons']", "must be a JSON object")
    for key, comp in comparisons.items():
        path = f"payload['paired_comparisons'][{key!r}]"
        if not isinstance(comp, dict):
            _fail(path, "must be a JSON object")
        for name in ("arm_a", "arm_b"):
            _check_str(_get(comp, path, name), f"{path}[{name!r}]")
        for name in ("n_a", "n_b", "n_pairs", "n_tasks"):
            _check_int(_get(comp, path, name), f"{path}[{name!r}]", minimum=0)
        for name in (
            "pass_rate_a",
            "pass_rate_b",
            "pass_rate_difference",
            "mean_token_difference",
            "permutation_p",
        ):
            _check_num(_get(comp, path, name), f"{path}[{name!r}]")
        for name in ("permutation_p_holm", "pass_rate_permutation_p_holm"):
            _check_num(
                _get(comp, path, name), f"{path}[{name!r}]", allow_none=True
            )
        for name in ("z_test", "wilcoxon"):
            block = _get(comp, path, name)
            if not isinstance(block, dict):
                _fail(f"{path}[{name!r}]", "must be a JSON object")
            _check_num(
                _get(block, f"{path}[{name!r}]", "p_value_holm"),
                f"{path}[{name!r}]['p_value_holm']",
                allow_none=True,
            )

    multiplicity = _get(payload, "payload", "multiplicity")
    multi_path = "payload['multiplicity']"
    _check_str(_get(multiplicity, multi_path, "method"), f"{multi_path}['method']")
    _check_str(_get(multiplicity, multi_path, "family"), f"{multi_path}['family']")

    _cross_check_grader_errors(payload)


def _cross_check_grader_errors(payload: dict) -> None:
    """Raw trials, when present, must agree with the recorded aggregates.

    The aggregate is the blessed source; a payload whose raw trials
    contradict it is refused loudly rather than rendered inconsistently.
    """
    raw = payload.get("raw_trials")
    if not isinstance(raw, list):
        return
    from_raw = _raw_grader_error_counts(raw)
    mismatches = []
    for arm, metrics in payload["overall"]["arms"].items():
        aggregate = metrics.get("outcomes", {}).get("grader_error")
        if aggregate is None:
            continue  # legacy: nothing recorded to contradict
        if aggregate["count"] != from_raw.get(arm, 0):
            mismatches.append(
                f"grader_error counts disagree for arm {arm!r}: recorded "
                f"{aggregate['count']}, raw trials show {from_raw.get(arm, 0)}"
            )
    if mismatches:
        raise RenderError("; ".join(mismatches))


# ---------------------------------------------------------------------------
# Shared value formatting (identical numbers in both formats)
# ---------------------------------------------------------------------------


def _fmt_value(value: Any, spec: str = ".4f") -> str | None:
    """Format a payload number; None (JSON null) stays None (never 0.0)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    return format(float(value), spec)


def _fmt_signed(value: Any, spec: str = ".4f") -> str | None:
    if value is None:
        return None
    return format(float(value), "+" + spec)


def _md_escape(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


_TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_TEX_ESCAPE_RE = re.compile("|".join(re.escape(ch) for ch in _TEX_ESCAPES))


def _tex_escape(text: Any) -> str:
    # Single pass: earlier replacements are never re-escaped.
    return _TEX_ESCAPE_RE.sub(lambda m: _TEX_ESCAPES[m.group(0)], str(text))


def _cell_text(text: Any, fmt: str) -> str:
    return _md_escape(text) if fmt == "md" else _tex_escape(text)


def _cell_num(
    value: Any, fmt: str, spec: str = ".4f", *, signed: bool = False
) -> str:
    formatted = _fmt_signed(value, spec) if signed else _fmt_value(value, spec)
    return _NULL_MARK[fmt] if formatted is None else formatted


def _cell_mono(text: Any, fmt: str) -> str:
    inner = _md_escape(text) if fmt == "md" else _tex_escape(text)
    return f"`{inner}`" if fmt == "md" else rf"\texttt{{{inner}}}"


def _md_table(lines: list[str], header: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")


def _tex_table(lines: list[str], spec: str, header: list[str], rows: list[list[str]]) -> None:
    lines.append(r"\begin{tabular}{" + spec + "}")
    lines.append(r"\toprule")
    lines.append(" & ".join(header) + r" \\")
    lines.append(r"\midrule")
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")


def _tex_spec(columns: int, first: str = "l", rest: str = "r") -> str:
    return "@{}" + first + (" " + rest) * (columns - 1) + "@{}"


def _table(lines: list[str], fmt: str, spec: str, header: list[str], rows: list[list[str]]) -> None:
    if fmt == "md":
        _md_table(lines, header, rows)
    else:
        _tex_table(lines, spec, header, rows)


def _heading(text: str, fmt: str) -> str:
    return f"## {_md_escape(text)}" if fmt == "md" else rf"\subsection*{{{_tex_escape(text)}}}"


# ---------------------------------------------------------------------------
# Table layouts (column sets shared by both formats)
# ---------------------------------------------------------------------------

_ARM_HEADER = (
    "arm",
    "trials",
    "tasks",
    "successes",
    "micro acc (trial-pooled)",
    "macro acc (task-eq-wt)",
    "input tok",
    "output tok",
    "total tok",
    "total spend/success",
    "truncated",
    "cap-exhausted",
    "empty",
    "completed",
    "completed acc",
    "grader err",
)

_PAIR_HEADER = (
    "scope",
    "input tok ratio (tahoe/classic)",
    "output tok ratio (tahoe/classic)",
    "total tok ratio (tahoe/classic)",
    "total spend/success classic",
    "total spend/success tahoe",
    "micro acc diff (tahoe-classic)",
    "macro acc diff (tahoe-classic)",
)

_COMPARISON_HEADER = (
    "comparison",
    "tasks",
    "pairs",
    "task-mean pass (a)",
    "task-mean pass (b)",
    "pass diff (a-b)",
    "mean token diff (a-b)",
    "perm p",
    "perm p (Holm)",
    "pass perm p (Holm)",
    "z p (Holm)",
    "wilcoxon p (Holm)",
)


# Marker for grader-error counts a legacy payload does not record.  Absent
# aggregates are unknown — never rendered as 0.
_UNKNOWN_MARK = "unknown"


def _grader_error_cell(outcomes: dict, fmt: str) -> str:
    """Recorded grader-error count from the aggregate, or an explicit
    unknown marker for legacy payloads that lack it — never 0."""
    aggregate = outcomes.get("grader_error")
    if aggregate is None:
        return _UNKNOWN_MARK
    return _cell_num(aggregate["count"], fmt)


def _arm_row(arm: str, metrics: dict, fmt: str) -> list[str]:
    sums = metrics["token_sums"]
    outcomes = metrics["outcomes"]
    completed = outcomes["completed_response"]
    return [
        _cell_text(arm, fmt),
        _cell_num(metrics["trials"], fmt),
        _cell_num(metrics["tasks"], fmt),
        _cell_num(metrics["successes"], fmt),
        _cell_num(metrics["micro_accuracy"], fmt),
        _cell_num(metrics["macro_accuracy"], fmt),
        _cell_num(sums["input_tokens"], fmt, ".1f"),
        _cell_num(sums["output_tokens"], fmt, ".1f"),
        _cell_num(sums["total_tokens"], fmt, ".1f"),
        _cell_num(metrics["total_spend_per_success"], fmt, ".2f"),
        _cell_num(outcomes["truncated"]["count"], fmt),
        _cell_num(outcomes["cap_exhausted"]["count"], fmt),
        _cell_num(outcomes["empty_response"]["count"], fmt),
        _cell_num(completed["count"], fmt),
        _cell_num(completed["accuracy"], fmt),
        _grader_error_cell(outcomes, fmt),
    ]


def _arm_table(lines: list[str], arms: dict, fmt: str) -> None:
    header = [_cell_text(text, fmt) for text in _ARM_HEADER]
    rows = [_arm_row(arm, arms[arm], fmt) for arm in sorted(arms, key=str)]
    _table(lines, fmt, _tex_spec(len(header)), header, rows)


def _pair_row(scope: str, pair: dict, fmt: str) -> list[str]:
    ratios = pair["token_ratio_tahoe_over_classic"]
    spend = pair["total_spend_per_success"]
    return [
        _cell_text(scope, fmt),
        _cell_num(ratios["input_tokens"], fmt),
        _cell_num(ratios["output_tokens"], fmt),
        _cell_num(ratios["total_tokens"], fmt),
        _cell_num(spend["classic"], fmt, ".2f"),
        _cell_num(spend["tahoe"], fmt, ".2f"),
        _cell_num(
            pair["micro_accuracy_difference_tahoe_minus_classic"], fmt, signed=True
        ),
        _cell_num(
            pair["macro_accuracy_difference_tahoe_minus_classic"], fmt, signed=True
        ),
    ]


def _pair_table(lines: list[str], scopes: list[tuple[str, dict]], fmt: str) -> None:
    header = [_cell_text(text, fmt) for text in _PAIR_HEADER]
    rows = [_pair_row(scope, pair, fmt) for scope, pair in scopes]
    _table(lines, fmt, _tex_spec(len(header)), header, rows)


def _comparison_row(key: str, comp: dict, fmt: str) -> list[str]:
    return [
        _cell_text(key, fmt),
        _cell_num(comp["n_tasks"], fmt),
        _cell_num(comp["n_pairs"], fmt),
        _cell_num(comp["pass_rate_a"], fmt),
        _cell_num(comp["pass_rate_b"], fmt),
        _cell_num(comp["pass_rate_difference"], fmt, signed=True),
        _cell_num(comp["mean_token_difference"], fmt, ".1f", signed=True),
        _cell_num(comp["permutation_p"], fmt),
        _cell_num(comp["permutation_p_holm"], fmt),
        _cell_num(comp["pass_rate_permutation_p_holm"], fmt),
        _cell_num(comp["z_test"].get("p_value_holm"), fmt),
        _cell_num(comp["wilcoxon"].get("p_value_holm"), fmt),
    ]


# ---------------------------------------------------------------------------
# Lineage (input + grader) and grader-error accounting
# ---------------------------------------------------------------------------


def _decode_metadata(entry: str) -> Any:
    try:
        return json.loads(entry)
    except (TypeError, ValueError):
        return entry


def _lineage_values(entry: dict, field: str) -> list[str]:
    """Distinct observed values of a metadata field, as recorded only."""
    manifest = entry["manifest"]
    values: set[str] = set()
    for recorded in manifest.get("trial_metadata", {}).get(field, []):
        values.add(str(_decode_metadata(recorded)))
    top = manifest.get("top_level", {}).get(field)
    if isinstance(top, (str, int, float)) and not isinstance(top, bool):
        values.add(str(top))
    return sorted(values)


def _recorded_tag(value: Any) -> str | None:
    """A recorded ``grader_version`` tag as a string; malformed → None.

    Empty strings, booleans, dicts, lists and None are ignored — a
    malformed tag is never invented into a rendering.
    """
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _format_grader_identity(
    grader: dict, version_tag: str | None = None
) -> str | None:
    """Compact deterministic rendering of one recorded grader identity.

    *version_tag* is the recorded sibling ``grader_version`` tag of the
    derived-manifest layout (``manifest.grader_version`` next to
    ``manifest.grader``): it fills the version slot when the record
    carries no explicit ``version``, and is appended to the provenance
    parenthetical otherwise, so an explicit ``version`` keeps its
    existing rendering while a recorded tag is never silently dropped.

    Only recorded fields appear — nothing is invented.  Typical derived
    manifests record ``name``, ``source`` and ``sha256`` (with the
    version in the sibling tag) or ``name``/``version``/``source``/
    ``sha256``; a record with none of these contributes nothing
    (rendered as absent, never fabricated).
    """
    head: list[str] = []
    name = grader.get("name")
    if isinstance(name, str) and name:
        head.append(name)
    version = grader.get("version")
    has_version = isinstance(version, str) and bool(version)
    if has_version:
        head.append(version)
    elif version_tag is not None:
        head.append(version_tag)
    tail: list[str] = []
    if version_tag is not None and has_version:
        tail.append(f"grader_version {version_tag}")
    source = grader.get("source")
    if isinstance(source, str) and source:
        tail.append(source)
    sha256 = grader.get("sha256")
    if isinstance(sha256, str) and sha256:
        tail.append(f"sha-256 {sha256}")
    if not head and not tail:
        return None
    return " ".join(head) + (f" ({', '.join(tail)})" if tail else "")


def _grader_lineage(entry: dict) -> list[str]:
    """Grader lineage: trial metadata, direct top-level value, and the
    grader provenance that derived manifests nest under
    ``manifest.top_level.manifest`` — the ``grader`` identity record(s)
    plus their sibling ``grader_version`` tag.  The tag fills the version
    slot of an identity record that has none; with no grader record at
    all it is still surfaced on its own, truthfully.  Absent provenance
    stays "not recorded" and malformed values are ignored — nothing is
    ever invented.
    """
    values = _lineage_values(entry, "grader")
    manifest = entry["manifest"]
    top = manifest.get("top_level")
    nested = top.get("manifest") if isinstance(top, dict) else None
    if not isinstance(nested, dict):
        return values
    version_tag = _recorded_tag(nested.get("grader_version"))
    grader = nested.get("grader")
    records = grader if isinstance(grader, list) else [grader]
    rendered_any = False
    for record in records:
        if isinstance(record, dict):
            identity = _format_grader_identity(record, version_tag)
            if identity is not None:
                values.append(identity)
                rendered_any = True
        elif isinstance(record, (str, int, float)) and not isinstance(record, bool):
            values.append(str(record))
            rendered_any = True
    if version_tag is not None and not rendered_any:
        # Recorded tag without a renderable grader record: the tag is the
        # provenance that exists — shown as recorded, never dropped.
        values.append(f"grader_version {version_tag}")
    return sorted(set(values))


def _join_lineage(values: list[str]) -> str:
    return ", ".join(values) if values else "not recorded"


def _raw_grader_error_counts(raw: list) -> dict[str, int]:
    """Count raw trials with failure_class == "grader_error", per arm."""
    by_arm: dict[str, int] = {}
    for trial in raw:
        if (
            isinstance(trial, dict)
            and trial.get("failure_class") == "grader_error"
        ):
            arm = str(trial.get("arm", "unknown"))
            by_arm[arm] = by_arm.get(arm, 0) + 1
    return by_arm


def _grader_error_note(payload: dict) -> str:
    """Exact grader-error accounting from the recorded per-arm aggregates.

    The ``grader_error`` outcome aggregate is the primary source; exact
    per-arm counts and the total are always reported.  A legacy payload
    without the aggregate falls back to exact raw-trial counting when raw
    trials are included, and otherwise states that the counts are unknown
    — never zero.
    """
    arms = payload["overall"]["arms"]
    recorded: dict[str, int | None] = {}
    for arm in sorted(arms, key=str):
        aggregate = arms[arm].get("outcomes", {}).get("grader_error")
        recorded[arm] = None if aggregate is None else aggregate["count"]
    known = {arm: count for arm, count in recorded.items() if count is not None}
    unknown = [arm for arm, count in recorded.items() if count is None]

    if not unknown:
        joined = ", ".join(f"{arm}: {count}" for arm, count in known.items())
        total = sum(known.values())
        if total == 0:
            return f"Grader-error outcomes: 0 recorded ({joined})."
        return (
            f"Grader-error outcomes: {total} recorded ({joined}); they are "
            "reported as their own outcome class and never silently dropped."
        )

    # Legacy payload without the recorded aggregate: exact raw-trial
    # counting when raw trials are included.
    raw = payload.get("raw_trials")
    if isinstance(raw, list):
        from_raw = _raw_grader_error_counts(raw)
        if not from_raw:
            return (
                'Grader-error outcomes: 0 raw trials carry failure_class '
                '"grader_error" (raw trials were inspected; none found).'
            )
        parts = ", ".join(
            f"{arm}: {count}" for arm, count in sorted(from_raw.items())
        )
        return (
            f'Grader-error outcomes: {sum(from_raw.values())} raw trial(s) '
            f'carry failure_class "grader_error" ({parts}); they are '
            "reported as their own outcome class and never silently dropped."
        )
    if known:
        joined = ", ".join(f"{arm}: {count}" for arm, count in known.items())
        return (
            f"Grader-error outcomes: {sum(known.values())} recorded "
            f"({joined}); not recorded for arms: {', '.join(unknown)} "
            "(counts unknown, never reported as zero)."
        )
    return (
        "Grader-error outcomes: not recorded in this payload (grader_error "
        f"outcome aggregate missing for arms: {', '.join(unknown)}); counts "
        "are unknown and are never reported as zero."
    )


# ---------------------------------------------------------------------------
# Section renderers (each available as a named block)
# ---------------------------------------------------------------------------


def _section_inputs(payload: dict, fmt: str) -> list[str]:
    provenance = payload["provenance"]
    lines = [_heading("Input lineage", fmt), ""]
    header = [
        _cell_text(text, fmt)
        for text in (
            "input",
            "sha-256",
            "trials",
            "trials by arm",
            "task-set sha-256",
            "grader(s)",
            "model(s)",
        )
    ]
    rows = []
    for entry in provenance["inputs"]:
        by_arm = ", ".join(
            f"{arm}: {count}"
            for arm, count in entry["trial_counts_by_arm"].items()
        )
        rows.append(
            [
                _cell_mono(entry["path"], fmt),
                _cell_mono(entry["sha256"], fmt),
                _cell_num(entry["trial_count"], fmt),
                _cell_text(by_arm, fmt),
                _cell_mono(entry["task_set_sha256"], fmt),
                _cell_text(_join_lineage(_grader_lineage(entry)), fmt),
                _cell_text(_join_lineage(_lineage_values(entry, "model")), fmt),
            ]
        )
    _table(lines, fmt, _tex_spec(len(header), first="l", rest="l"), header, rows)
    lines.append("")
    lines.append(f"Total trials: {provenance['total_trials']}.")
    lines.append("")
    lines.append(_cell_text(_grader_error_note(payload), fmt))
    return lines


def _section_analysis(payload: dict, fmt: str) -> list[str]:
    """Analysis implementation lineage: which code and options made these
    numbers (compact table + options line, in both formats)."""
    analysis = payload["analysis_provenance"]
    lines = [_heading("Analysis implementation", fmt), ""]
    header = [_cell_text("source file", fmt), _cell_text("sha-256", fmt)]
    rows = [
        [_cell_mono(repo_rel, fmt), _cell_mono(analysis["files"][repo_rel], fmt)]
        for repo_rel in sorted(analysis["files"], key=str)
    ]
    _table(lines, fmt, _tex_spec(len(header), first="l", rest="l"), header, rows)
    lines.append("")
    lines.append(
        f"Options: seed {analysis['seed']}, {analysis['n_resamples']} "
        f"bootstrap resamples, {analysis['n_permutations']} permutation "
        f"draws; payload schema {_cell_mono(analysis['payload_schema'], fmt)}, "
        f"analysis schema {_cell_mono(analysis['schema'], fmt)}."
    )
    return lines


def _section_estimands(payload: dict, fmt: str) -> list[str]:
    lines = [_heading("Estimands", fmt), ""]
    if fmt == "md":
        for name in sorted(payload["estimands"]):
            lines.append(
                f"- **{_md_escape(name)}** — {_md_escape(payload['estimands'][name])}"
            )
    else:
        lines.append(r"\begin{itemize}")
        for name in sorted(payload["estimands"]):
            lines.append(
                rf"\item \textbf{{{_tex_escape(name)}}} --- "
                f"{_tex_escape(payload['estimands'][name])}"
            )
        lines.append(r"\end{itemize}")
    return lines


def _section_overall(payload: dict, fmt: str) -> list[str]:
    lines = [_heading("Overall", fmt), ""]
    _arm_table(lines, payload["overall"]["arms"], fmt)
    return lines


def _pair_scopes(payload: dict) -> list[tuple[str, dict]]:
    scopes: list[tuple[str, dict]] = []
    pair = payload["overall"].get("classic_vs_tahoe")
    if pair is not None:
        scopes.append(("overall (all benchmarks pooled)", pair))
    for benchmark in sorted(payload["benchmarks"], key=str):
        bench_pair = payload["benchmarks"][benchmark].get("classic_vs_tahoe")
        if bench_pair is not None:
            scopes.append((benchmark, bench_pair))
    return scopes


def _section_summary(payload: dict, fmt: str) -> list[str]:
    """Headline block: only the overall arm table plus the overall
    classic-vs-tahoe pair table — no per-benchmark sections.

    Compact enough to embed in a README or paper headline; the full
    per-benchmark detail lives in the ``pair``/``benchmarks`` blocks.
    Rows come from the same row builders as every other block, so the
    values cannot drift from the full render.
    """
    lines = [_heading("Overall", fmt), ""]
    _arm_table(lines, payload["overall"]["arms"], fmt)
    lines.append("")
    pair = payload["overall"].get("classic_vs_tahoe")
    if pair is not None:
        _pair_table(
            lines, [("overall (all benchmarks pooled)", pair)], fmt
        )
    else:
        present = ", ".join(sorted(payload["overall"]["arms"], key=str)) or "none"
        lines.append(
            _cell_text(
                "classic vs tahoe ratios unavailable (arms present: "
                f"{present}); no ratios are invented.",
                fmt,
            )
        )
    return lines


def _section_pair(payload: dict, fmt: str) -> list[str]:
    lines = [_heading("classic vs tahoe", fmt), ""]
    scopes = _pair_scopes(payload)
    if not scopes:
        lines.append(
            _cell_text(
                "classic vs tahoe ratios unavailable (no scope records both "
                "arms); no ratios are invented.",
                fmt,
            )
        )
        return lines
    _pair_table(lines, scopes, fmt)
    return lines


def _section_benchmarks(payload: dict, fmt: str) -> list[str]:
    lines = [_heading("Benchmarks", fmt)]
    for benchmark in sorted(payload["benchmarks"], key=str):
        entry = payload["benchmarks"][benchmark]
        lines.append("")
        task_set_line = (
            f"Task-set sha-256: {_cell_mono(entry['task_set_sha256'], fmt)}."
        )
        if fmt == "md":
            lines.append(f"### `{_md_escape(benchmark)}`")
            lines.append("")
            lines.append(task_set_line)
        else:
            lines.append(rf"\subsection*{{{_tex_escape(benchmark)}}}")
            lines.append("")
            lines.append(task_set_line)
        lines.append("")
        _arm_table(lines, entry["arms"], fmt)
        lines.append("")
        pair = entry.get("classic_vs_tahoe")
        if pair is not None:
            _pair_table(lines, [(benchmark, pair)], fmt)
        else:
            present = ", ".join(sorted(entry["arms"], key=str)) or "none"
            lines.append(
                _cell_text(
                    "classic vs tahoe ratios unavailable for this benchmark "
                    f"(arms present: {present}).",
                    fmt,
                )
            )
    return lines


def _section_paired(payload: dict, fmt: str) -> list[str]:
    lines = [_heading("Paired task-cluster comparisons (Holm-corrected)", fmt), ""]
    comparisons = payload["paired_comparisons"]
    if not comparisons:
        lines.append(
            _cell_text(
                "No arm pair had matched (benchmark, task_id, trial) keys.",
                fmt,
            )
        )
        return lines
    header = [_cell_text(text, fmt) for text in _COMPARISON_HEADER]
    rows = [
        _comparison_row(key, comparisons[key], fmt)
        for key in sorted(comparisons, key=str)
    ]
    _table(lines, fmt, _tex_spec(len(header)), header, rows)
    lines.append("")
    multiplicity = payload["multiplicity"]
    lines.append(
        _cell_text(
            f"Multiplicity: {multiplicity['method']} step-down correction "
            f"over {len(comparisons)} comparisons "
            f"(family: {multiplicity['family']}); pairing key: "
            "(benchmark, task_id, trial).",
            fmt,
        )
    )
    return lines


_SECTION_RENDERERS: dict[str, Callable[[dict, str], list[str]]] = {
    "inputs": _section_inputs,
    "analysis": _section_analysis,
    "estimands": _section_estimands,
    "overall": _section_overall,
    "pair": _section_pair,
    "summary": _section_summary,
    "benchmarks": _section_benchmarks,
    "paired": _section_paired,
}

# The ``full`` document and the standalone renders keep their existing
# section order; ``summary`` is a standalone named block only.
_DOCUMENT_SECTIONS = (
    "inputs",
    "analysis",
    "estimands",
    "overall",
    "pair",
    "benchmarks",
    "paired",
)

# Named instances: ``SECTION@INSTANCE`` (e.g. ``summary@glm``).  The suffix
# distinguishes blocks of different payloads in one file; it never changes
# what the section renders.
_INSTANCE_SEP = "@"
_INSTANCE_SUFFIX_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def split_block_name(full: str) -> tuple[str, str | None]:
    """Split a marker name into (section, instance suffix or None).

    ``summary`` -> ``("summary", None)``; ``summary@glm`` ->
    ``("summary", "glm")``.  Refuses malformed instances: empty section,
    empty suffix, a second ``@``, or suffix characters outside
    ``[A-Za-z0-9_.-]``.
    """
    section, sep, suffix = full.partition(_INSTANCE_SEP)
    if not sep:
        return full, None
    if not section or not suffix or not _INSTANCE_SUFFIX_RE.match(suffix):
        raise RenderError(
            f"malformed block instance name {full!r}: expected "
            "SECTION@INSTANCE with a nonempty INSTANCE of letters, "
            "digits, '.', '_', '-'"
        )
    return section, suffix

BLOCK_NAMES = ("full", *_SECTION_RENDERERS)


# ---------------------------------------------------------------------------
# Documents and blocks
# ---------------------------------------------------------------------------


def _notes_lines(fmt: str) -> list[str]:
    text = (
        f'"{_NULL_MARK[fmt]}" marks undefined values (JSON null): zero '
        "successes for total spend/success, zero classic spend for ratios, "
        "no completed responses for completed accuracy. Micro and macro "
        "accuracy are distinct estimands and are never mixed; see Estimands. "
        f'"{_UNKNOWN_MARK}" marks grader-error counts a legacy payload does '
        "not record (the grader_error outcome aggregate is missing); they "
        "are never reported as zero."
    )
    if fmt == "md":
        return ["", f"Notes: {text}"]
    return ["", "%% " + text]


def _document(payload: dict, fmt: str) -> list[str]:
    validate_payload(payload)
    if fmt == "md":
        head = [
            "# Canonical results",
            "",
            f"Schema `{SCHEMA}`. Deterministic render of the canonical payload: "
            "no timestamps, no model evaluations. The canonical JSON artifact "
            "is the source of truth; do not hand-edit these numbers.",
        ]
    else:
        head = [
            "%% Canonical results (rendered from the canonical payload).",
            f"%% Schema: {SCHEMA}. Deterministic render: no timestamps; no "
            "model evaluations. The canonical JSON artifact is the",
            "%% source of truth; do not hand-edit these numbers. "
            "Requires booktabs (\\usepackage{booktabs}).",
        ]
    parts: list[list[str]] = [head]
    for name in _DOCUMENT_SECTIONS:
        parts.append(_SECTION_RENDERERS[name](payload, fmt))
    lines: list[str] = []
    for position, part in enumerate(parts):
        if position:
            lines.append("")
        lines.extend(part)
    lines.extend(_notes_lines(fmt))
    return lines


def render_markdown_document(payload: dict) -> str:
    """Standalone Markdown results document (deterministic; ends in \\n)."""
    return "\n".join(_document(payload, "md")) + "\n"


def render_latex_fragment(payload: dict) -> str:
    """Standalone LaTeX booktabs fragment (deterministic; ends in \\n)."""
    return "\n".join(_document(payload, "tex")) + "\n"


def render_block(payload: dict, name: str, fmt: str) -> list[str]:
    """Render one named block's content lines from the same payload.

    *name* is either a plain section name (``overall``) or a named instance
    ``SECTION@INSTANCE`` (``summary@glm``).  The instance suffix selects
    which marked block the content belongs to; the section always renders
    identically from the same payload either way.
    """
    validate_payload(payload)
    section, _suffix = split_block_name(name)
    if section not in BLOCK_NAMES:
        raise RenderError(
            f"unknown block name {name!r}; valid names: "
            f"{', '.join(BLOCK_NAMES)}"
        )
    if section == "full":
        return _document(payload, fmt)
    return _SECTION_RENDERERS[section](payload, fmt)


# ---------------------------------------------------------------------------
# Marker scanning (strict: refuse ambiguous/missing/malformed markers)
# ---------------------------------------------------------------------------

MD_BEGIN_TEMPLATE = "<!-- CANONICAL_RESULTS:BEGIN {name} -->"
MD_END_TEMPLATE = "<!-- CANONICAL_RESULTS:END {name} -->"
TEX_BEGIN_TEMPLATE = "% CANONICAL_RESULTS:BEGIN {name}"
TEX_END_TEMPLATE = "% CANONICAL_RESULTS:END {name}"

# Marker names: a plain section, or SECTION@INSTANCE with a nonempty
# suffix of the same character class.
_MARKER_NAME = r"[A-Za-z0-9_.-]+(?:@[A-Za-z0-9_.-]+)?"
_MD_BEGIN_RE = re.compile(
    rf"^[ \t]*<!--[ \t]*CANONICAL_RESULTS:BEGIN[ \t]+(?P<name>{_MARKER_NAME})[ \t]*-->[ \t]*$"
)
_MD_END_RE = re.compile(
    rf"^[ \t]*<!--[ \t]*CANONICAL_RESULTS:END[ \t]+(?P<name>{_MARKER_NAME})[ \t]*-->[ \t]*$"
)
_TEX_BEGIN_RE = re.compile(
    rf"^[ \t]*%[ \t]*CANONICAL_RESULTS:BEGIN[ \t]+(?P<name>{_MARKER_NAME})[ \t]*$"
)
_TEX_END_RE = re.compile(
    rf"^[ \t]*%[ \t]*CANONICAL_RESULTS:END[ \t]+(?P<name>{_MARKER_NAME})[ \t]*$"
)
# Any line mentioning the marker family must be a well-formed marker of the
# file's format — anything else (missing name, wrong wrapper, stray text)
# is a malformed marker and the run is refused.
_MARKER_HINT_RE = re.compile(r"CANONICAL_RESULTS:", re.IGNORECASE)


@dataclass
class _Block:
    name: str
    begin: int  # line index of the BEGIN marker
    end: int  # line index of the END marker
    content: list[str]  # original lines strictly between the markers


def scan_blocks(lines: list[str], fmt: str, filename: str) -> list[_Block]:
    """Strictly scan marked blocks; raise RenderError on anything ambiguous.

    Refuses: no markers, malformed marker lines, malformed instance names,
    BEGIN without END, END without BEGIN, name mismatches, nested BEGINs,
    and exact duplicate full names (plain or instance).  The same section
    with distinct instance suffixes (``summary@glm``, ``summary@oss``) is
    allowed.
    """
    if fmt == "md":
        begin_re, end_re = _MD_BEGIN_RE, _MD_END_RE
        begin_tpl, end_tpl = MD_BEGIN_TEMPLATE, MD_END_TEMPLATE
    else:
        begin_re, end_re = _TEX_BEGIN_RE, _TEX_END_RE
        begin_tpl, end_tpl = TEX_BEGIN_TEMPLATE, TEX_END_TEMPLATE
    blocks: list[_Block] = []
    seen: set[str] = set()
    open_name: str | None = None
    open_begin: int | None = None
    for index, line in enumerate(lines):
        if not _MARKER_HINT_RE.search(line):
            continue
        begin_match = begin_re.match(line)
        end_match = end_re.match(line)
        if begin_match is None and end_match is None:
            raise RenderError(
                f"{filename}: line {index + 1}: malformed canonical-results "
                "marker (expected "
                f"{begin_tpl.format(name='NAME')} / {end_tpl.format(name='NAME')}); refusing"
            )
        if begin_match is not None:
            name = begin_match.group("name")
            if open_name is not None:
                raise RenderError(
                    f"{filename}: line {index + 1}: nested BEGIN marker while "
                    f"{open_name!r} is still open; refusing"
                )
            if name in seen:
                raise RenderError(
                    f"{filename}: line {index + 1}: duplicate block name "
                    f"{name!r} (ambiguous); refusing"
                )
            open_name, open_begin = name, index
        else:
            name = end_match.group("name")
            if open_name is None:
                raise RenderError(
                    f"{filename}: line {index + 1}: END marker without a "
                    "matching BEGIN; refusing"
                )
            if name != open_name:
                raise RenderError(
                    f"{filename}: line {index + 1}: END marker name {name!r} "
                    f"does not match open BEGIN {open_name!r}; refusing"
                )
            blocks.append(
                _Block(name, open_begin, index, lines[open_begin + 1 : index])
            )
            seen.add(name)
            open_name, open_begin = None, None
    if open_name is not None:
        raise RenderError(
            f"{filename}: BEGIN marker for {open_name!r} has no matching END; "
            "refusing"
        )
    if not blocks:
        raise RenderError(
            f"{filename}: no canonical-results markers found; refusing"
        )
    unknown = sorted(
        {
            block.name
            for block in blocks
            if split_block_name(block.name)[0] not in BLOCK_NAMES
        }
    )
    if unknown:
        raise RenderError(
            f"{filename}: unknown block name(s) {', '.join(unknown)}; "
            f"valid names: {', '.join(BLOCK_NAMES)}"
        )
    return blocks


# ---------------------------------------------------------------------------
# File targets: read, update (in place), check (read-only)
# ---------------------------------------------------------------------------


def _read_lines(path: Path) -> tuple[list[str], str, bool]:
    text = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    ends_with_newline = text.endswith(newline)
    body = text[: -len(newline)] if ends_with_newline else text
    return body.split(newline), newline, ends_with_newline


def _select_blocks(
    blocks: list[_Block], selected: list[str] | None, filename: str
) -> list[_Block]:
    """Blocks matching the --block selection, in file order.

    *selected* is None for "every block" (the default all-blocks behavior).
    Each selected name must be a well-formed full marker name that exists
    in the file; anything missing is refused so a typo can never silently
    leave a stale block behind.
    """
    if selected is None:
        return list(blocks)
    present = {block.name: block for block in blocks}
    wanted: list[str] = []
    for name in selected:
        section, _suffix = split_block_name(name)
        if section not in BLOCK_NAMES:
            raise RenderError(
                f"--block {name!r}: unknown section {section!r}; "
                f"valid names: {', '.join(BLOCK_NAMES)}"
            )
        if name not in present:
            raise RenderError(
                f"{filename}: --block {name!r}: no such marked block "
                f"(found: {', '.join(sorted(present)) or 'none'})"
            )
        if name not in wanted:
            wanted.append(name)
    chosen = set(wanted)
    return [block for block in blocks if block.name in chosen]


def _update_file_text(
    payload: dict, path: Path, fmt: str, selected: list[str] | None = None
) -> str:
    """New full text for *path*: block contents replaced, everything else
    (including newline style and final-newline presence) preserved exactly.

    With *selected*, only the named block(s) are regenerated; every other
    marked block keeps its existing content byte-for-byte.
    """
    lines, newline, ends_with_newline = _read_lines(path)
    blocks = scan_blocks(lines, fmt, str(path))
    chosen = {block.name for block in _select_blocks(blocks, selected, str(path))}
    out: list[str] = []
    cursor = 0
    for block in blocks:
        out.extend(lines[cursor : block.begin + 1])
        if block.name in chosen:
            out.extend(render_block(payload, block.name, fmt))
        else:
            out.extend(block.content)  # untouched, byte-for-byte
        cursor = block.end
    out.extend(lines[cursor:])
    body = newline.join(out)
    return body + (newline if ends_with_newline else "")


def _check_file(
    payload: dict, path: Path, fmt: str, selected: list[str] | None = None
) -> list[str]:
    """Names of blocks in *path* whose content drifted from the payload."""
    lines, _, _ = _read_lines(path)
    blocks = scan_blocks(lines, fmt, str(path))
    chosen = _select_blocks(blocks, selected, str(path))
    return [
        block.name
        for block in chosen
        if block.content != render_block(payload, block.name, fmt)
    ]


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".render-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _parse_target_spec(spec: str) -> tuple[Path, str]:
    """Parse ``PATH`` or ``PATH:FMT`` into (path, format); infer from suffix."""
    text = spec
    fmt: str | None = None
    if ":" in text:
        path_part, _, suffix = text.rpartition(":")
        alias = suffix.strip().lower()
        if alias in ("md", "markdown"):
            fmt, text = "md", path_part
        elif alias in ("tex", "latex"):
            fmt, text = "tex", path_part
    if not text:
        raise RenderError(f"invalid target {spec!r}")
    path = Path(text)
    if fmt is None:
        extension = path.suffix.lower()
        if extension in (".md", ".markdown"):
            fmt = "md"
        elif extension in (".tex", ".latex"):
            fmt = "tex"
        else:
            raise RenderError(
                f"cannot infer block format for {spec!r}; pass 'PATH:md' "
                "or 'PATH:tex'"
            )
    return path, fmt


def _refuse_payload_target(target: Path, payload_path: Path, action: str) -> None:
    if os.path.realpath(target) == os.path.realpath(payload_path):
        raise RenderError(
            f"refusing to {action} the canonical payload itself: {target}"
        )


def _refuse_marker_standalone(target: Path) -> None:
    """A standalone document write would erase marked blocks; refuse."""
    if target.is_file() and _MARKER_HINT_RE.search(
        target.read_text(encoding="utf-8")
    ):
        raise RenderError(
            f"{target}: file already contains canonical-results markers; "
            "use --update instead of a standalone --markdown/--latex write"
        )


def load_payload(path: Path) -> dict:
    """Read and validate the canonical payload; never writes to it."""
    if not path.is_file():
        raise RenderError(f"canonical payload not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RenderError(f"{path}: invalid JSON ({exc})") from exc
    validate_payload(payload)
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render_canonical_docs.py",
        description=(
            "Render an existing canonical-results JSON payload into a "
            "deterministic Markdown document and/or a LaTeX booktabs "
            "fragment, and update or check explicitly marked generated "
            "blocks in text files. No model evaluations; no timestamps. "
            "The canonical JSON input is read-only."
        ),
        epilog=(
            "markers: Markdown "
            f"{MD_BEGIN_TEMPLATE.format(name='NAME')} / "
            f"{MD_END_TEMPLATE.format(name='NAME')}; LaTeX "
            f"{TEX_BEGIN_TEMPLATE.format(name='NAME')} / "
            f"{TEX_END_TEMPLATE.format(name='NAME')}. NAME is a section "
            f"({', '.join(BLOCK_NAMES)}) or a named instance "
            "SECTION@INSTANCE (e.g. summary@glm), letting several payloads "
            "carry blocks in the same file. "
            "--block NAME (repeatable) restricts --update/--check to the "
            "named full marker name(s), leaving every other block "
            "byte-untouched; without it every marked block is updated/"
            "checked. exit codes: 0 ok, 1 error, 3 drift in --check."
        ),
    )
    parser.add_argument(
        "payload",
        type=Path,
        help="canonical results JSON (schema canonical-results/1); read-only",
    )
    parser.add_argument(
        "--markdown",
        action="append",
        type=Path,
        metavar="PATH",
        default=[],
        help="write a standalone Markdown results document (repeatable)",
    )
    parser.add_argument(
        "--latex",
        action="append",
        type=Path,
        metavar="PATH",
        default=[],
        help="write a standalone LaTeX booktabs fragment (repeatable)",
    )
    parser.add_argument(
        "--update",
        action="append",
        type=str,
        metavar="PATH[:FMT]",
        default=[],
        help=(
            "update marked generated blocks in PATH in place, preserving "
            "everything outside the markers (repeatable; FMT: md or tex, "
            "default from the file extension)"
        ),
    )
    parser.add_argument(
        "--check",
        action="append",
        type=str,
        metavar="PATH[:FMT]",
        default=[],
        help=(
            "check marked blocks in PATH against the payload without "
            "modifying anything (repeatable; exit 3 on drift)"
        ),
    )
    parser.add_argument(
        "--block",
        action="append",
        type=str,
        metavar="NAME",
        default=[],
        help=(
            "with --update/--check: full marker name of the block(s) to "
            "touch — plain section (overall) or named instance "
            "(summary@glm); repeatable; default: every marked block"
        ),
    )
    args = parser.parse_args(argv)
    if not (args.markdown or args.latex or args.update or args.check):
        parser.error(
            "nothing to do: pass --markdown, --latex, --update and/or --check"
        )
    selected: list[str] | None = args.block or None
    if selected is not None and not (args.update or args.check):
        parser.error(
            "--block applies to --update/--check targets; pass one of them"
        )

    payload_path = args.payload
    try:
        payload = load_payload(payload_path)
        writes: list[tuple[Path, str]] = []
        drift: list[tuple[Path, str]] = []
        for path in args.markdown:
            _refuse_payload_target(path, payload_path, "overwrite")
            _refuse_marker_standalone(path)
            writes.append((path, render_markdown_document(payload)))
        for path in args.latex:
            _refuse_payload_target(path, payload_path, "overwrite")
            _refuse_marker_standalone(path)
            writes.append((path, render_latex_fragment(payload)))
        for spec in args.update:
            target, fmt = _parse_target_spec(spec)
            _refuse_payload_target(target, payload_path, "update")
            if not target.is_file():
                raise RenderError(f"update target not found: {target}")
            writes.append(
                (target, _update_file_text(payload, target, fmt, selected))
            )
        for spec in args.check:
            target, fmt = _parse_target_spec(spec)
            _refuse_payload_target(target, payload_path, "check")
            if not target.is_file():
                raise RenderError(f"check target not found: {target}")
            drifted = _check_file(payload, target, fmt, selected)
            if drifted:
                drift.extend((target, name) for name in drifted)
            else:
                print(f"checked {target}: no drift")
        # Every target parsed and rendered before anything is written, so a
        # failure in a later target leaves all earlier targets untouched.
        for path, text in writes:
            _write_atomic(path, text)
            print(f"wrote {path}")
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if drift:
        for target, name in drift:
            print(
                f"drift: {target}: block {name!r} does not match the "
                "canonical payload",
                file=sys.stderr,
            )
        print(
            f"error: {len(drift)} block(s) drifted from the canonical payload",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
