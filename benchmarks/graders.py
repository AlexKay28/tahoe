"""Programmatic graders for the ablation study.

A grader is a callable that receives ``(result, expected_state)`` and returns
``(passed: bool, detail: str)`` where:

- ``result`` is the final answer/output produced by the arm runner;
- ``expected_state`` is the dict from the task manifest (grader-specific
  fields, optionally merged with ``grader.params`` by the runner).
"""

from __future__ import annotations

import json
import re
import subprocess

__all__ = [
    "ExactMatchGrader",
    "ContainsGrader",
    "JSONFieldGrader",
    "TestPassGrader",
    "CompositeGrader",
    "NumericGrader",
    "make_grader",
]

_TEST_CMD_TIMEOUT_SECONDS = 60


class ExactMatchGrader:
    """Passes when ``result == expected_state["answer"]`` (string match)."""

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        expected = expected_state.get("answer")
        if result == expected:
            return True, f"exact match: {expected!r}"
        return False, f"expected {expected!r}, got {result!r}"


class ContainsGrader:
    """Passes when ``expected_state["substring"]`` occurs in ``result``."""

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        substring = expected_state.get("substring")
        if substring is None:
            return False, "expected_state is missing 'substring'"
        text = result if isinstance(result, str) else str(result)
        if substring in text:
            return True, f"found substring {substring!r}"
        return False, f"substring {substring!r} not found in result"


class JSONFieldGrader:
    """Parses ``result`` as JSON and checks that the field named by
    ``expected_state["field"]`` equals ``expected_state["value"]``."""

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        field = expected_state.get("field")
        value = expected_state.get("value")
        if isinstance(result, dict):
            data = result
        else:
            text = result if isinstance(result, str) else str(result)
            try:
                data = json.loads(text)
            except ValueError as exc:
                return False, f"result is not valid JSON: {exc}"
        if not isinstance(data, dict):
            return False, f"parsed JSON is {type(data).__name__}, expected an object"
        if field not in data:
            return False, f"field {field!r} missing from JSON"
        if data[field] == value:
            return True, f"field {field!r} == {value!r}"
        return False, f"field {field!r}: expected {value!r}, got {data[field]!r}"


class TestPassGrader:
    """Runs the shell command ``expected_state["test_cmd"]`` and passes when
    it exits with code 0."""

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        cmd = expected_state.get("test_cmd")
        if not cmd:
            return False, "expected_state is missing 'test_cmd'"
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_TEST_CMD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, (
                f"test command timed out after {_TEST_CMD_TIMEOUT_SECONDS}s: {cmd}"
            )
        if proc.returncode == 0:
            return True, f"test command exited 0: {cmd}"
        detail = f"test command exited {proc.returncode}: {cmd}"
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if output:
            detail += f" | last output line: {output.splitlines()[-1]}"
        return False, detail


class CompositeGrader:
    """Runs multiple sub-graders; all must pass.

    Sub-graders come from the constructor (grader instances, type-name strings
    or ``{"type": ..., "params": {...}}`` dicts) or, when the constructor got
    nothing, from ``expected_state["graders"]`` in the same three forms. A
    dict spec's ``params`` are merged over a copy of ``expected_state`` for
    that sub-grader only.
    """

    def __init__(self, graders=None):
        if graders is not None and callable(graders):
            graders = [graders]
        self._graders = graders

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        try:
            resolved = list(self._resolve(expected_state))
        except ValueError as exc:
            return False, str(exc)
        if not resolved:
            return False, "composite grader has no sub-graders"
        details = []
        passed = True
        for name, grader, state in resolved:
            ok, detail = grader(result, state)
            passed = passed and ok
            details.append(f"{name}: {'PASS' if ok else 'FAIL'} ({detail})")
        return passed, "; ".join(details)

    def _resolve(self, expected_state: dict):
        specs = self._graders
        if specs is None:
            specs = expected_state.get("graders") or []
        for spec in specs:
            if callable(spec):
                yield type(spec).__name__, spec, expected_state
            elif isinstance(spec, str):
                grader = make_grader(spec)
                yield type(grader).__name__, grader, expected_state
            elif isinstance(spec, dict):
                grader = make_grader(spec.get("type", ""))
                merged = dict(expected_state)
                merged.update(spec.get("params") or {})
                yield type(grader).__name__, grader, merged
            else:
                raise ValueError(f"invalid sub-grader spec: {spec!r}")


# Separator-aware number token: thousands groups ('1,430', '1 430', thin
# space), optional decimals, optional leading minus.
_SEP_NUM = r"-?\d{1,3}(?:[,\u202f ]\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?"


def _normalize_number_text(text) -> str:
    """Normalize LaTeX/formatting artifacts so separator matching works."""
    return (
        str(text)
        .replace("\\,", "")
        .replace("\\ ", "")
        .replace("\u202f", " ")
        .replace("$", "")
    )


def _clean_number(token: str) -> str:
    """Strip separators from a matched number token ('1,430' -> '1430')."""
    return token.replace(",", "").replace("\u202f", "").replace(" ", "")


def _to_float(value):
    s = _clean_number(str(value))
    try:
        return float(s)
    except ValueError:
        return None


def _numbers_equal(a, b, rel_tol: float = 1e-9) -> bool:
    """Numeric equality with tolerance; 42 == 42.00 == '42,000'/16000-style."""
    fa, fb = _to_float(a), _to_float(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) <= rel_tol * max(1.0, abs(fa), abs(fb))
    return str(a).strip() == str(b).strip()


class NumericGrader:
    """Extracts the model's FINAL answer number and compares it to ``value``.

    The grader never passes merely because the expected number occurs
    somewhere in the result (regression: an 8-subtask plan answer used to
    pass because the digit '5' appeared in the numbered list). Exactly one
    number is extracted as the final answer and compared numerically, so
    42 == 42.00 and '16,000' == 16000.

    Task-specific extraction (any of these ``expected_state`` keys takes
    priority over the generic chain, so a manifest can pin exactly where
    the answer lives instead of relying on universal last-number behavior):

    - ``field``: read this key from a JSON-object result;
    - ``label``: match a ``Label: N`` / ``Label is N`` declaration
      (e.g. ``label: "Number of subtasks"``);
    - ``pattern``: task-supplied regex; the LAST match wins and capture
      group 1 (or the whole match) is the number.

    Generic chain when no task-specific source matches, in priority order:

    1. ``#### N`` official marker;
    2. ``\\boxed{...}`` (LaTeX thousands separators ``43{,}200`` handled);
    3. single-key JSON object (``{"subtask_count": 5}``);
    4. last bold span containing a number (``**Count: 3**``);
    5. last ``answer/result/total/count/number is|=: N`` declaration;
    6. last number on the last non-empty line.
    """

    def __call__(self, result, expected_state: dict) -> tuple[bool, str]:
        expected = expected_state.get("value")
        if expected is None:
            return False, "expected_state is missing 'value'"
        text = result if isinstance(result, str) else str(result)
        try:
            number, method = self._extract(result, text, expected_state)
        except re.error as exc:
            return False, f"invalid expected_state['pattern']: {exc}"
        if number is None:
            return False, (
                f"no final-answer number found in result "
                f"(nearest source: {method}): {text[:100]!r}"
            )
        if _numbers_equal(number, expected):
            return True, (
                f"final answer {number} (via {method}) matches expected {expected}"
            )
        return False, f"expected {expected}, final answer was {number} (via {method})"

    def _extract(self, result, text: str, state: dict):
        field = state.get("field")
        label = state.get("label")
        pattern = state.get("pattern")

        # Task-specific structured sources first.
        data = None
        if isinstance(result, dict):
            data = result
        else:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                data = parsed
        if data is not None:
            if field is not None:
                if field in data:
                    number = self._number_from_value(data[field])
                    if number is not None:
                        return number, f"JSON field {field!r}"
            elif len(data) == 1:
                number = self._number_from_value(next(iter(data.values())))
                if number is not None:
                    return number, "single-key JSON object"
        if label is not None:
            m = re.search(
                rf"{re.escape(str(label))}\s*(?:is|=|:)\s*({_SEP_NUM})",
                text,
                re.I,
            )
            if m:
                return _clean_number(m.group(1)), f"label {label!r}"
        if pattern is not None:
            matches = list(re.finditer(pattern, text))
            if matches:
                m = matches[-1]
                group = m.group(1) if m.groups() else m.group(0)
                number = self._number_from_value(group)
                if number is not None:
                    return number, f"pattern {pattern!r}"

        # Generic final-answer chain.
        m = re.search(rf"####\s*\$?\s*({_SEP_NUM})", text)
        if m:
            return _clean_number(m.group(1)), "'####' marker"
        m = re.search(r"\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}", text)
        if m:
            inner = (
                m.group(1)
                .replace("{,}", ",")
                .replace("\\,", "")
                .replace("\\ ", "")
            )
            nums = re.findall(_SEP_NUM, inner)
            if nums:
                return _clean_number(nums[-1]), "'\\boxed{}'"
        norm = _normalize_number_text(text)
        for span in reversed(re.findall(r"\*\*([^*]+)\*\*", norm)):
            nums = re.findall(_SEP_NUM, span)
            if nums:
                return _clean_number(nums[-1]), "bold span"
        ms = re.findall(
            rf"(?:answer|result|total|count|number)\s*(?:is|=|:)\s*({_SEP_NUM})",
            norm,
            re.I,
        )
        if ms:
            return _clean_number(ms[-1]), "answer declaration"
        lines = [line for line in norm.splitlines() if line.strip()]
        if lines:
            nums = re.findall(_SEP_NUM, lines[-1])
            if nums:
                return _clean_number(nums[-1]), "last line"
        return None, "no final-answer marker"

    @staticmethod
    def _number_from_value(value):
        """Extract the last number from a JSON field value or scalar."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return str(value)
        nums = re.findall(_SEP_NUM, _normalize_number_text(value))
        if nums:
            return _clean_number(nums[-1])
        return None


_GRADER_TYPES = {
    "exact_match": ExactMatchGrader,
    "contains": ContainsGrader,
    "json_field": JSONFieldGrader,
    "test_pass": TestPassGrader,
    "composite": CompositeGrader,
    "numeric": NumericGrader,
}


def make_grader(grader_type: str):
    """Build a grader instance from a manifest ``grader.type`` string."""
    try:
        return _GRADER_TYPES[grader_type]()
    except KeyError:
        known = ", ".join(sorted(_GRADER_TYPES))
        raise ValueError(
            f"unknown grader type: {grader_type!r} (known types: {known})"
        ) from None
