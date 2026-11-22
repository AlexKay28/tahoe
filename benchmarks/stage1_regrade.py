#!/usr/bin/env python3
"""Deterministic derived-results pipeline for re-grading archived Stage-1 trials.

This module generalizes ``benchmarks/gsm8k_regrade.py`` from one benchmark to
all ten archived Stage-1 benchmarks (gsm8k, arc, bbh, bbh_track, bbh_arith,
lsat, race, mmlu_math, mmlu_logic, mmlu_acct). The raw input archive is NEVER
modified. Given an archived results JSON file it produces a separate
*derived* artifact in which every Stage-1 trial has been re-graded with the
CURRENT grader functions from ``benchmarks/run_public_bench.py``.

Expected answers are recovered from the archived ``grader_detail`` strings
(``"expected=X, got=Y"``) — the archives carry no ``expected`` field — and
are adapted per benchmark:

- gsm8k: numeric gold reconstructed as the official ``"#### <gold>"`` form
  and graded with the CURRENT ``grade_gsm8k`` (numeric-v6);
- arc: letter or raw numeric answerKey passed to ``grade_arc``, whose
  positional fallback maps digits 1-4 to A-D;
- bbh / bbh_track: expected parens stripped ("(G)" -> "G") and graded with
  ``grade_bbh`` (accepts bare, "(X)" and explicit-marker answers);
- bbh_arith: numeric gold graded with ``grade_bbh_arith``;
- lsat / race: expected letters graded with ``grade_lsat`` / ``grade_race``;
- mmlu_math / mmlu_logic / mmlu_acct: archived A-D letters inverted to the
  integer index the CURRENT ``grade_mmlu`` expects (A->0, B->1, C->2, D->3).

Outcome preservation (the archives document max_tokens=2048 but do not carry
``finish_reason``):

- every derived trial records ``output_token_cap=2048`` and
  ``cap_exhausted`` derived from ``output_tokens >= 2048``;
- ``finish_reason`` is NEVER invented and no ``truncated`` flag is set from
  the exact cap alone;
- empty/missing final answers fail as ``failure_class="empty_response"``
  (a runner-level class that is never graded into a pass); an empty answer
  that also has a grader problem keeps ``empty_response`` as the primary
  class with an explanatory grader detail;
- a NONEMPTY cap-exhausted answer that fails grading is classified
  ``failure_class="truncated"`` with an explicit ``outcome_provenance``
  saying the truncation is cap-derived and that finish_reason is absent;
- a cap-exhausted answer that passes grading keeps ``passed=True`` /
  ``failure_class="none"`` with the cap flag visible in ``cap_exhausted``;
- every other failing grade stays ``wrong_answer``.

Safety properties (pinned by tests/test_stage1_regrade.py):

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
- A missing, malformed or inconsistent expected value — or a grader
  exception — becomes an explicit ``failure_class="grader_error"`` result,
  never a silent pass.
- The derived payload is byte-deterministic (sorted keys, fixed trial
  order, no timestamps, no host-absolute paths). Optional run metadata
  (timestamps, absolute paths) goes to a separate sidecar file only.
- The manifest records the spec and regrader versions, the grader function
  map, SHA-256 hashes of the source archive and of the grader source,
  per-benchmark summaries and verdict changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# The grader implementations live in run_public_bench.py. Import them the same
# way the sibling runners do (script mode adds benchmarks/ to sys.path;
# package mode imports it relatively).
try:
    from . import run_public_bench  # noqa: F401
    from .run_public_bench import (
        grade_arc,
        grade_bbh,
        grade_bbh_arith,
        grade_gsm8k,
        grade_lsat,
        grade_mmlu,
        grade_race,
    )
except ImportError:  # pragma: no cover - script/CLI path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import run_public_bench  # noqa: F401
    from run_public_bench import (
        grade_arc,
        grade_bbh,
        grade_bbh_arith,
        grade_gsm8k,
        grade_lsat,
        grade_mmlu,
        grade_race,
    )

__all__ = [
    "SCHEMA",
    "SPEC_VERSION",
    "REGRADER_VERSION",
    "GRADER_VERSION",
    "OUTPUT_TOKEN_CAP",
    "STAGE1_BENCHMARKS",
    "GRADER_FUNCTIONS",
    "RegradeError",
    "extract_expected_token",
    "normalize_expected",
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
SCHEMA = "tahoe/stage1-derived-results/1"
SPEC_VERSION = "stage1-archived-results/2026-09-13"
REGRADER_VERSION = "1"
GRADER_VERSION = "run_public_bench-numeric-v6"
GRADER_SOURCE = "benchmarks/run_public_bench.py"  # repo-relative grader file

# The 2026-09-13 stage1-full archives were run with max_tokens=2048
# (benchmarks/run_public_bench.py run_trial) but carry no finish_reason.
OUTPUT_TOKEN_CAP = 2048
FINISH_REASON_POLICY = (
    "archived stage-1 trials carry no finish_reason; none is fabricated; "
    "cap evidence is output_tokens-derived only"
)

STAGE1_BENCHMARKS = (
    "arc",
    "bbh",
    "bbh_arith",
    "bbh_track",
    "gsm8k",
    "lsat",
    "mmlu_acct",
    "mmlu_logic",
    "mmlu_math",
    "race",
)
_MMLU_BENCHMARKS = ("mmlu_acct", "mmlu_logic", "mmlu_math")

# Archived benchmark name -> CURRENT grader function in run_public_bench.py.
GRADER_FUNCTIONS = {
    "arc": "grade_arc",
    "bbh": "grade_bbh",
    "bbh_arith": "grade_bbh_arith",
    "bbh_track": "grade_bbh",
    "gsm8k": "grade_gsm8k",
    "lsat": "grade_lsat",
    "mmlu_acct": "grade_mmlu",
    "mmlu_logic": "grade_mmlu",
    "mmlu_math": "grade_mmlu",
    "race": "grade_race",
}

# 'expected=X' prefix of the archived grader detail strings
# ('expected=42, got=42.00', 'expected=(G), got=G\n\n...'). The captured
# token runs up to the first ', got=' (or end of string): the thousands
# separator in 'expected=43,200' is therefore preserved.
_EXPECTED_TOKEN_RE = re.compile(r"expected=(.*?)(?:, got=|$)", re.S)

# A cleaned gold value must be a plain number for numeric comparison
# (same acceptance as the GSM8K regrade pipeline).
_GOLD_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Expected letters after paren normalization ('(G)' -> 'G').
_BBH_LETTER_RE = re.compile(r"\(?([A-Z])\)?")
_PLAIN_LETTER_RE = re.compile(r"([A-Z])")

# Derived failure classes.
FAILURE_NONE = "none"
FAILURE_WRONG = "wrong_answer"
FAILURE_GRADER = "grader_error"
FAILURE_EMPTY = "empty_response"
FAILURE_TRUNCATED = "truncated"


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
    """SHA-256 of the file that provides the CURRENT graders."""
    return sha256_file(Path(run_public_bench.__file__).resolve())


def extract_expected_token(grader_detail) -> tuple[str | None, str]:
    """Extract the raw expected token from an archived ``grader_detail``.

    Archived details look like ``"expected=42, got=42.00"`` or
    ``"expected=(G), got=G"``. Returns ``(token, "")`` with the raw token
    (unnormalized, parens and thousands separators intact), or ``(None,
    reason)`` when the detail or the expected value is missing. Callers
    must turn the failure into an explicit grader error.
    """
    if not isinstance(grader_detail, str) or not grader_detail.strip():
        return None, "archived grader_detail is missing or empty"
    match = _EXPECTED_TOKEN_RE.search(grader_detail)
    if not match:
        return (
            None,
            "archived grader_detail has no parseable 'expected=' field: "
            + repr(grader_detail),
        )
    token = match.group(1).strip()
    if not token:
        return None, "archived expected value is empty: " + repr(grader_detail)
    return token, ""


def _clean_number(token: str) -> str:
    """Normalize an archived numeric expected token to a plain number.

    Strips '$', thin spaces and trailing punctuation, then removes
    thousands separators ('43,200' -> '43200', '1 430' -> '1430').
    """
    cleaned = (
        token.replace("$", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .rstrip(",.")
    )
    cleaned = re.sub(r"(?<=\d),(?=\d)", "", cleaned)
    return cleaned


def normalize_expected(benchmark, token: str) -> tuple[str | None, str]:
    """Adapt an archived expected token to the CURRENT grader's expected form.

    Returns ``(expected_arg, "")`` ready to be passed to the current grader
    function, or ``(None, reason)`` when the token is malformed or
    inconsistent with the benchmark's answer scheme (an explicit grader
    error, never a silent pass).
    """
    if benchmark == "gsm8k":
        cleaned = _clean_number(token)
        if not _GOLD_RE.fullmatch(cleaned):
            return None, (
                "malformed expected value " + repr(token)
                + " for benchmark gsm8k (expected a number)"
            )
        # Reconstruct the official '#### <gold>' gold-answer form so the
        # CURRENT grade_gsm8k applies its own gold extraction and numeric
        # comparison ('42' == '42.00', '43,200' == 43200) end to end.
        return f"#### {cleaned}", ""
    if benchmark == "bbh_arith":
        cleaned = _clean_number(token)
        if not _GOLD_RE.fullmatch(cleaned):
            return None, (
                "malformed expected value " + repr(token)
                + " for benchmark bbh_arith (expected a number)"
            )
        return cleaned, ""
    if benchmark == "arc":
        # Letter answerKeys pass through; numeric answerKeys ('1'-'4') are
        # kept raw so the CURRENT grade_arc applies its positional numeric
        # fallback ('3' -> 'C') exactly as live runs do.
        if token in ("A", "B", "C", "D") or token in ("1", "2", "3", "4"):
            return token, ""
        return None, (
            "inconsistent expected answerKey " + repr(token)
            + " for benchmark arc (not A-D or 1-4)"
        )
    if benchmark in ("bbh", "bbh_track"):
        match = _BBH_LETTER_RE.fullmatch(token)
        if match:
            return match.group(1), ""
        return None, (
            "inconsistent expected option " + repr(token)
            + " for benchmark " + benchmark + " (not a single letter)"
        )
    if benchmark == "lsat":
        match = _PLAIN_LETTER_RE.fullmatch(token)
        if match and match.group(1) in "ABCDE":
            return match.group(1), ""
        return None, (
            "inconsistent expected letter " + repr(token)
            + " for benchmark lsat (not A-E)"
        )
    if benchmark == "race":
        match = _PLAIN_LETTER_RE.fullmatch(token)
        if match and match.group(1) in "ABCD":
            return match.group(1), ""
        return None, (
            "inconsistent expected letter " + repr(token)
            + " for benchmark race (not A-D)"
        )
    if benchmark in _MMLU_BENCHMARKS:
        match = _PLAIN_LETTER_RE.fullmatch(token)
        if match and match.group(1) in "ABCD":
            # The archived MMLU grader recorded the letter; the CURRENT
            # grade_mmlu expects the integer choice index (A->0 .. D->3).
            return str(ord(match.group(1)) - ord("A")), ""
        return None, (
            "inconsistent expected letter " + repr(token)
            + " for benchmark " + benchmark + " (not A-D)"
        )
    return None, "unhandled benchmark " + repr(benchmark)


def _current_grade(benchmark, expected_arg, answer_text) -> tuple[bool, str]:
    """Call the CURRENT grader function for ``benchmark``.

    Resolves the grader through module globals at call time so tests can
    monkeypatch a grade_* function to simulate a grader exception.
    """
    if benchmark == "gsm8k":
        return grade_gsm8k(answer_text, expected_arg)
    if benchmark == "arc":
        return grade_arc(answer_text, expected_arg)
    if benchmark in ("bbh", "bbh_track"):
        return grade_bbh(answer_text, expected_arg)
    if benchmark == "bbh_arith":
        return grade_bbh_arith(answer_text, expected_arg)
    if benchmark == "lsat":
        return grade_lsat(answer_text, expected_arg)
    if benchmark == "race":
        return grade_race(answer_text, expected_arg)
    if benchmark in _MMLU_BENCHMARKS:
        return grade_mmlu(answer_text, expected_arg)
    raise RegradeError("unhandled benchmark " + repr(benchmark))


def _exc_reason(exc: BaseException) -> str:
    text = str(exc)
    name = type(exc).__name__
    return f"{name}: {text}" if text else name


_EMPTY_PREFIX = (
    "empty_response: final_answer is empty (never graded into a pass)"
)


def regrade_trial(trial: dict) -> dict:
    """Re-grade one archived Stage-1 trial with the CURRENT graders.

    Returns a new dict: every original field (including the raw
    ``final_answer``) is carried over unchanged, the original verdict is
    preserved as ``archived_*`` fields, and fresh
    ``passed``/``failure_class``/``grader_detail``/``quality_score`` values
    plus ``output_token_cap``/``cap_exhausted`` outcome fields are derived.
    The input dict is not mutated.
    """
    out = dict(trial)
    out["archived_passed"] = trial.get("passed")
    out["archived_failure_class"] = trial.get("failure_class")
    out["archived_grader_detail"] = trial.get("grader_detail")

    # Outcome preservation: the archives document max_tokens=2048 but carry
    # no finish_reason. cap_exhausted is derived from output_tokens alone;
    # finish_reason is never invented and no `truncated` flag is set from
    # the exact cap (see module docstring).
    output_tokens = trial.get("output_tokens")
    try:
        output_tokens = int(output_tokens)
    except (TypeError, ValueError):
        output_tokens = 0
    cap_exhausted = output_tokens >= OUTPUT_TOKEN_CAP
    out["output_token_cap"] = OUTPUT_TOKEN_CAP
    out["cap_exhausted"] = cap_exhausted

    benchmark = trial.get("benchmark")
    final_answer = trial.get("final_answer")
    if isinstance(final_answer, str):
        answer_text = final_answer
    elif final_answer is None:
        answer_text = ""
    else:
        answer_text = str(final_answer)
    empty = not answer_text.strip()

    token, token_reason = extract_expected_token(trial.get("grader_detail"))
    expected_arg = None
    grader_problem = token_reason
    if token is not None:
        expected_arg, norm_reason = normalize_expected(benchmark, token)
        if expected_arg is None:
            grader_problem = norm_reason

    if empty:
        # Runner-level primary class: an empty/missing final answer is an
        # empty_response and can never grade into a pass — even when the
        # grader also has a problem (the detail explains both).
        out["passed"] = False
        out["failure_class"] = FAILURE_EMPTY
        if grader_problem:
            out["grader_detail"] = f"{_EMPTY_PREFIX}; grader_error: {grader_problem}"
        else:
            try:
                _, detail = _current_grade(benchmark, expected_arg, answer_text)
            except Exception as exc:  # grader exception, explicit
                out["grader_detail"] = (
                    f"{_EMPTY_PREFIX}; grader_error: {_exc_reason(exc)}"
                )
            else:
                out["grader_detail"] = f"{_EMPTY_PREFIX}; grader detail: {detail}"
        out["quality_score"] = 0.0
        return out

    if grader_problem:
        # Missing/malformed/inconsistent expected values (or an unhandled
        # benchmark) are explicit grader errors — never a silent pass.
        out["passed"] = False
        out["failure_class"] = FAILURE_GRADER
        out["grader_detail"] = f"grader_error: {grader_problem}"
        out["quality_score"] = 0.0
        return out

    try:
        passed, detail = _current_grade(benchmark, expected_arg, answer_text)
    except Exception as exc:
        out["passed"] = False
        out["failure_class"] = FAILURE_GRADER
        out["grader_detail"] = (
            "grader_error: current grader "
            f"{GRADER_FUNCTIONS.get(benchmark, '?')} raised {_exc_reason(exc)}"
        )
        out["quality_score"] = 0.0
        return out

    out["grader_detail"] = detail
    out["passed"] = bool(passed)
    if passed:
        # A cap-exhausted answer that still passes keeps the pass; the cap
        # stays visible through cap_exhausted.
        out["failure_class"] = FAILURE_NONE
    elif cap_exhausted:
        # Nonempty, cap-exhausted and failing: cap-derived truncation with
        # explicit provenance (finish_reason absent in the archive, never
        # fabricated).
        out["failure_class"] = FAILURE_TRUNCATED
        out["outcome_provenance"] = (
            f"cap-derived: output_tokens={output_tokens} reached the "
            f"archived request cap max_tokens={OUTPUT_TOKEN_CAP}; classified "
            "truncated from cap exhaustion alone. Archived stage-1 trials "
            "carry no finish_reason; none is fabricated."
        )
    else:
        out["failure_class"] = FAILURE_WRONG
    out["quality_score"] = 1.0 if out["passed"] else 0.0
    return out


def _summarize(trials) -> dict:
    """Deterministic summary of derived trials: classes, caps, verdict flips."""
    failure_classes: dict[str, int] = {}
    passed = 0
    cap_trials = cap_passed = cap_truncated = cap_empty = 0
    fail_to_pass = pass_to_fail = 0
    for t in trials:
        failure_classes[t["failure_class"]] = (
            failure_classes.get(t["failure_class"], 0) + 1
        )
        if t["failure_class"] == FAILURE_NONE:
            passed += 1
        if t["cap_exhausted"]:
            cap_trials += 1
            if t["failure_class"] == FAILURE_NONE:
                cap_passed += 1
            elif t["failure_class"] == FAILURE_TRUNCATED:
                cap_truncated += 1
            elif t["failure_class"] == FAILURE_EMPTY:
                cap_empty += 1
        archived = t["archived_passed"]
        if t["failure_class"] == FAILURE_GRADER or not isinstance(archived, bool):
            continue  # grader errors and unknown archived verdicts are not changes
        if archived is False and t["passed"] is True:
            fail_to_pass += 1
        elif archived is True and t["passed"] is False:
            pass_to_fail += 1
    return {
        "trials": len(trials),
        "passed": passed,
        "failure_classes": failure_classes,
        "cap_exhausted": {
            "trials": cap_trials,
            "passed": cap_passed,
            "truncated": cap_truncated,
            "empty_response": cap_empty,
        },
        "verdict_changes": {
            "fail_to_pass": fail_to_pass,
            "pass_to_fail": pass_to_fail,
        },
    }


def regrade_archive(archive, source_name: str = "archive"):
    """Re-grade every Stage-1 trial in an archived results list.

    Returns ``(derived_trials, benchmarks_summary, overall_summary)``.
    Trial order is preserved from the input archive. Trials whose benchmark
    is not one of the ten archived Stage-1 benchmarks stay in the derived
    artifact as explicit ``grader_error`` rows (never silently dropped).
    """
    if not isinstance(archive, list):
        raise RegradeError(
            f"{source_name}: expected a JSON array of trial objects, "
            f"got {type(archive).__name__}"
        )
    derived = []
    for index, entry in enumerate(archive):
        if not isinstance(entry, dict):
            raise RegradeError(
                f"{source_name}: trial #{index} is "
                f"{type(entry).__name__}, expected a JSON object"
            )
        derived.append(regrade_trial(entry))

    benchmarks: dict[str, dict] = {}
    for bench in sorted({str(t.get("benchmark")) for t in derived}):
        rows = [t for t in derived if t.get("benchmark") == bench]
        benchmarks[bench] = _summarize(rows)
    return derived, benchmarks, _summarize(derived)


def build_payload(
    archive, source_sha256: str, grader_sha256: str, source_name: str = "archive"
) -> dict:
    """Build the full deterministic derived-results payload."""
    trials, benchmarks, summary = regrade_archive(archive, source_name=source_name)
    return {
        "manifest": {
            "schema": SCHEMA,
            "spec_version": SPEC_VERSION,
            "regrader_version": REGRADER_VERSION,
            "grader_version": GRADER_VERSION,
            "grader": {
                "name": "run_public_bench.stage1",
                "source": GRADER_SOURCE,
                "sha256": grader_sha256,
                "functions": dict(GRADER_FUNCTIONS),
            },
            "source_archive_sha256": source_sha256,
            "output_token_cap": OUTPUT_TOKEN_CAP,
            "finish_reason_policy": FINISH_REASON_POLICY,
            "benchmarks": benchmarks,
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
    payload manifest for callers to report. Run metadata (timestamps,
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
            "schema": "tahoe/stage1-derived-results-run/1",
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc)
            .isoformat(timespec="seconds"),
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "input_sha256": source_sha256,
            "spec_version": SPEC_VERSION,
            "regrader_version": REGRADER_VERSION,
            "grader_version": GRADER_VERSION,
            "grader_source": GRADER_SOURCE,
            "grader_source_sha256": payload["manifest"]["grader"]["sha256"],
            "summary": payload["manifest"]["summary"],
            "python_version": sys.version.split()[0],
        }
        write_exclusive(
            Path(metadata_path), json.dumps(meta, indent=2, sort_keys=True) + "\n"
        )

    return payload["manifest"]
