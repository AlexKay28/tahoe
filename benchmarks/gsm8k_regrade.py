#!/usr/bin/env python3
"""Deterministic derived-results pipeline for re-grading archived GSM8K trials.

This module replaces the legacy in-place regrading workflow: the raw input
archive is NEVER modified. Instead, given an archived results JSON file it
produces a separate *derived* artifact in which every GSM8K trial has been
re-graded with the CURRENT ``grade_gsm8k`` implementation from
``benchmarks/run_public_bench.py``.

Safety properties (pinned by tests/test_fix_gsm8k_extraction.py):

- ``--input`` and ``--output`` are always explicit; nothing is inferred and
  there are no hardcoded result paths.
- The output parent directory is created, but an existing output file is
  refused via an atomic exclusive create (``O_CREAT | O_EXCL``) — never
  truncated, never overwritten.
- The input archive is opened read-only; its bytes are never written.
- Original verdicts are preserved on each derived trial as
  ``archived_passed`` / ``archived_failure_class`` / ``archived_grader_detail``
  before the derived ``passed`` / ``failure_class`` / ``grader_detail`` /
  ``quality_score`` are written.
- The raw ``final_answer`` of every trial is carried through unchanged.
- A missing or malformed ``expected=<number>`` in the archived
  ``grader_detail`` becomes an explicit ``failure_class="grader_error"``
  result — never a silent pass.
- The derived payload is byte-deterministic (sorted keys, fixed trial
  order, no timestamps, no host-absolute paths). Optional run metadata
  (timestamps, absolute paths) goes to a separate sidecar file only.
- The manifest records the grader version plus SHA-256 hashes of the source
  archive and of the grader source, so a derived artifact can always be
  audited against the exact inputs that produced it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# The grader implementation lives in run_public_bench.py. Import it the same
# way the sibling runners do (script mode adds benchmarks/ to sys.path; package
# mode imports it relatively).
try:
    from . import run_public_bench  # noqa: F401
    from .run_public_bench import grade_gsm8k
except ImportError:  # pragma: no cover - script/CLI path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import run_public_bench  # noqa: F401
    from run_public_bench import grade_gsm8k

__all__ = [
    "GRADER_VERSION",
    "REGRADER_VERSION",
    "SCHEMA",
    "RegradeError",
    "extract_expected_gold",
    "regrade_trial",
    "regrade_archive",
    "build_payload",
    "render_payload",
    "write_exclusive",
    "sha256_bytes",
    "sha256_file",
    "grader_source_sha256",
    "run_pipeline",
]

# Version tags recorded in the manifest. The SHA-256 of the grader source is
# the authoritative pin; these tags give humans something readable to diff.
GRADER_VERSION = "grade_gsm8k-numeric-v6"
REGRADER_VERSION = "2"
SCHEMA = "tahoe/gsm8k-derived-results/1"
GRADER_SOURCE = "benchmarks/run_public_bench.py"  # repo-relative grader file

# 'expected=<number>' as archived by the GSM8K grader detail strings
# ('expected=42, got=42.00'). The captured token may carry thousands
# separators ('43,200'), thin spaces, or a trailing comma before ' got='.
_EXPECTED_RE = re.compile(r"expected=\$?\s*(-?\d(?:[\d,\.\u202f ]*\d)?)")

# A cleaned gold value must be a plain number for numeric comparison.
_GOLD_RE = re.compile(r"-?\d+(?:\.\d+)?")


class RegradeError(Exception):
    """Fatal, user-facing regrade pipeline error (never a silent skip)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def grader_source_sha256() -> str:
    """SHA-256 of the file that provides the CURRENT grade_gsm8k."""
    return sha256_file(Path(run_public_bench.__file__).resolve())


def extract_expected_gold(grader_detail) -> tuple[str | None, str]:
    """Extract the expected GSM8K gold from an archived ``grader_detail``.

    Archived details look like ``"expected=42, got=42.00"``. Returns
    ``(gold, "")`` with the gold as a cleaned number token ('42', '43200',
    '42.00'), or ``(None, reason)`` when the expected value is missing or
    malformed. Callers must turn the failure into an explicit grader error.
    """
    if not isinstance(grader_detail, str) or not grader_detail.strip():
        return None, "archived grader_detail is missing or empty"
    match = _EXPECTED_RE.search(grader_detail)
    if not match:
        return (
            None,
            "archived grader_detail has no parseable 'expected=<number>': "
            + repr(grader_detail),
        )
    token = match.group(1).rstrip(" ,.\u202f")
    cleaned = token.replace(",", "").replace("\u202f", "").replace(" ", "")
    if not _GOLD_RE.fullmatch(cleaned):
        return (
            None,
            "malformed expected value "
            + repr(match.group(1))
            + " in archived grader_detail",
        )
    return cleaned, ""


def regrade_trial(trial: dict) -> dict:
    """Re-grade one archived GSM8K trial with the CURRENT ``grade_gsm8k``.

    Returns a new dict: every original field (including the raw
    ``final_answer``) is carried over unchanged, the original verdict is
    preserved as ``archived_*`` fields, and fresh
    ``passed``/``failure_class``/``grader_detail``/``quality_score`` values
    are derived. The input dict is not mutated.
    """
    out = dict(trial)
    out["archived_passed"] = trial.get("passed")
    out["archived_failure_class"] = trial.get("failure_class")
    out["archived_grader_detail"] = trial.get("grader_detail")

    gold, reason = extract_expected_gold(trial.get("grader_detail"))
    if gold is None:
        # Missing/malformed expected values are explicit grader errors —
        # never a silent pass (archived archives really contain these:
        # 'expected=, got=3').
        out["passed"] = False
        out["failure_class"] = "grader_error"
        out["grader_detail"] = f"grader_error: {reason}"
        out["quality_score"] = 0.0
        return out

    # Reconstruct the official '#### <gold>' gold-answer form so the CURRENT
    # grade_gsm8k applies its own gold extraction and numeric comparison
    # ('42' == '42.00', '43,200' == 43200) end to end.
    passed, detail = grade_gsm8k(
        str(trial.get("final_answer") or ""), f"#### {gold}"
    )
    out["passed"] = bool(passed)
    out["failure_class"] = "none" if passed else "wrong_answer"
    out["grader_detail"] = detail
    out["quality_score"] = 1.0 if passed else 0.0
    return out


def regrade_archive(archive, source_name: str = "archive"):
    """Re-grade every GSM8K trial in an archived results list.

    Returns ``(derived_trials, summary)``. Non-GSM8K trials are skipped (the
    derived artifact is a GSM8K result set; the manifest records how many
    were skipped). GSM8K trial order is preserved from the input archive.
    """
    if not isinstance(archive, list):
        raise RegradeError(
            f"{source_name}: expected a JSON array of trial objects, "
            f"got {type(archive).__name__}"
        )
    derived = []
    skipped = 0
    for index, entry in enumerate(archive):
        if not isinstance(entry, dict):
            raise RegradeError(
                f"{source_name}: trial #{index} is "
                f"{type(entry).__name__}, expected a JSON object"
            )
        if entry.get("benchmark") != "gsm8k":
            skipped += 1
            continue
        derived.append(regrade_trial(entry))

    passed = sum(1 for t in derived if t["failure_class"] == "none")
    wrong = sum(1 for t in derived if t["failure_class"] == "wrong_answer")
    errors = sum(1 for t in derived if t["failure_class"] == "grader_error")
    fail_to_pass = pass_to_fail = 0
    for t in derived:
        archived = t["archived_passed"]
        if t["failure_class"] == "grader_error" or not isinstance(archived, bool):
            continue  # errors and unknown archived verdicts are not verdict changes
        if archived is False and t["passed"] is True:
            fail_to_pass += 1
        elif archived is True and t["passed"] is False:
            pass_to_fail += 1

    summary = {
        "gsm8k_trials": len(derived),
        "skipped_non_gsm8k": skipped,
        "passed": passed,
        "wrong_answer": wrong,
        "grader_errors": errors,
        "verdict_changes": {
            "fail_to_pass": fail_to_pass,
            "pass_to_fail": pass_to_fail,
        },
    }
    return derived, summary


def build_payload(
    archive, source_sha256: str, grader_sha256: str, source_name: str = "archive"
) -> dict:
    """Build the full deterministic derived-results payload."""
    trials, summary = regrade_archive(archive, source_name=source_name)
    return {
        "manifest": {
            "schema": SCHEMA,
            "regrader_version": REGRADER_VERSION,
            "grader_version": GRADER_VERSION,
            "grader": {
                "name": "grade_gsm8k",
                "source": GRADER_SOURCE,
                "sha256": grader_sha256,
            },
            "source_archive_sha256": source_sha256,
            "summary": summary,
        },
        "trials": trials,
    }


def render_payload(payload: dict) -> str:
    """Deterministic JSON rendering: sorted keys, fixed indent, final newline.

    No timestamps, no host-absolute paths — byte-identical for the same
    input archive and grader source.
    """
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_exclusive(path: Path, text: str) -> None:
    """Atomically create ``path`` with ``text``; refuse any existing file.

    The file is opened with ``O_CREAT | O_EXCL`` so that creating over an
    existing output is impossible even in a race; a partial file from a
    failed write is unlinked rather than left behind.
    """
    path = Path(path)
    parent = path.parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RegradeError(
            f"refusing to overwrite existing output: {path}. "
            "The derived-results pipeline only creates new files; "
            "choose a fresh --output path."
        )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def run_pipeline(
    input_path: os.PathLike | str,
    output_path: os.PathLike | str,
    metadata_path: os.PathLike | str | None = None,
) -> dict:
    """End-to-end pipeline: read archive -> re-grade -> write derived artifact.

    The input file is read once (read-only) and never written. Returns the
    payload summary for callers to report. Run metadata (timestamps,
    absolute paths) is written to ``metadata_path`` only when requested, so
    the derived artifact itself stays deterministic.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise RegradeError(f"input archive not found: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise RegradeError(
            "--output must differ from --input: the raw input archive is "
            "never modified and cannot serve as its own derived artifact"
        )

    raw = input_path.read_bytes()
    source_sha256 = sha256_bytes(raw)
    try:
        archive = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RegradeError(
            f"{input_path}: not a readable JSON results archive: {exc}"
        ) from None

    payload = build_payload(
        archive,
        source_sha256=source_sha256,
        grader_sha256=grader_source_sha256(),
        source_name=str(input_path),
    )
    write_exclusive(output_path, render_payload(payload))

    if metadata_path is not None:
        import datetime

        meta = {
            "schema": "tahoe/gsm8k-derived-results-run/1",
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc)
            .isoformat(timespec="seconds"),
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "input_sha256": source_sha256,
            "grader_version": GRADER_VERSION,
            "grader_source": GRADER_SOURCE,
            "grader_source_sha256": payload["manifest"]["grader"]["sha256"],
            "summary": payload["manifest"]["summary"],
            "python_version": sys.version.split()[0],
        }
        write_exclusive(
            Path(metadata_path), json.dumps(meta, indent=2, sort_keys=True) + "\n"
        )

    return payload["manifest"]["summary"]
