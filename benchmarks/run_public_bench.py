#!/usr/bin/env python3
"""Run public benchmark eval: GSM8K, ARC-Challenge, BBH.

Same ablation design: classic (Q -> answer) vs tahoe (Q + skill -> answer).
Single API call per trial. Numeric/exact graders.

EVALUATION INVARIANT: The grader and answer extraction logic must be IDENTICAL
for both arms. The ONLY difference between arms is the system prompt (TAHOE
thinking skill vs nothing). Never branch grading logic on arm identity.

Usage:
  export TAHOE_API_BASE="https://your-api-endpoint/v1"
  export TAHOE_API_KEY="your-api-key"
  export TAHOE_MODEL="."
  # export SSL_CERT_FILE if your endpoint uses a custom CA
  PYTHONPATH=src python3 benchmarks/run_public_bench.py
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from runner_classic import (
    grading_outcome,
    outcome_fields,
    run as run_classic,
)
from report import generate_markdown_table, generate_json_report, generate_per_task_comparison
from metrics import compute_all_metrics, count_typed_refs

from prompt_paths import resolve_prompt

SKILL_PATH = str(resolve_prompt("tahoe"))

# Baseline prompt file paths — each arm maps to a prompt file in benchmarks/
ARM_PROMPT_FILES = {
    "classic": None,  # no system prompt
    "tahoe": "tahoe-93.txt",
    "cot": "cot.txt",
    "cod": "cod.txt",
    "tot": "tot.txt",
    "react": "react.txt",
}

DEFAULT_ARMS = ["classic", "tahoe"]
ALL_ARMS = list(ARM_PROMPT_FILES.keys())

# ARMS is configurable via env var BENCH_ARMS (comma-separated) or defaults to DEFAULT_ARMS
_arms_env = os.environ.get("BENCH_ARMS", "")
if _arms_env:
    ARMS = [a.strip() for a in _arms_env.split(",") if a.strip()]
else:
    ARMS = list(DEFAULT_ARMS)

TRIALS_PER_TASK = int(os.environ.get("BENCH_TRIALS", "3"))
SEED = 42
MAX_SAMPLES_PER_BENCH = 10  # 10 samples per benchmark for paper

# Run only these benchmarks (comma-separated benchmark names). Empty = all.
BENCHES = [b.strip() for b in os.environ.get("BENCHES", "").split(",") if b.strip()]
# GPQA Diamond subset limit for smoke runs (0 = full 198)
GPQA_LIMIT = int(os.environ.get("GPQA_LIMIT", "0"))


def load_arm_prompt(arm, prompt_cache=None):
    """Load the system prompt for a given arm.

    Returns the prompt text, or "" if the arm has no prompt file.
    Uses prompt_cache dict if provided to avoid re-reading files.
    """
    if prompt_cache and arm in prompt_cache:
        return prompt_cache[arm]
    prompt_file = ARM_PROMPT_FILES.get(arm)
    if prompt_file is None:
        text = ""
    else:
        from prompt_paths import resolve_prompt
        path = resolve_prompt(prompt_file)
        with open(path) as f:
            text = f.read()
    if prompt_cache is not None:
        prompt_cache[arm] = text
    return text

# MATH grader: extract \boxed{} answer
def grade_math(model_answer, expected_answer):
    """MATH: extract \\boxed{} from both, compare numerically when possible."""
    def extract_boxed(text):
        match = re.search(r'\\boxed\{([^}]+)\}', text)
        return match.group(1).strip() if match else ""
    model_boxed = extract_boxed(model_answer)
    expected_boxed = extract_boxed(expected_answer)
    if not model_boxed:
        # Fallback: last number
        nums = re.findall(r'-?\d+\.?\d*', model_answer)
        model_boxed = nums[-1] if nums else model_answer.strip()[:50]
    if not expected_boxed:
        nums = re.findall(r'-?\d+\.?\d*', expected_answer)
        expected_boxed = nums[-1] if nums else expected_answer.strip()
    # Try numeric comparison
    try:
        return float(model_boxed) == float(expected_boxed), f"expected={expected_boxed}, got={model_boxed}"
    except (ValueError, TypeError):
        return model_boxed == expected_boxed, f"expected={expected_boxed}, got={model_boxed}"

# RACE grader: answer is A/B/C/D
def grade_race(model_answer, expected_answer):
    """RACE: match answer letter (A/B/C/D)."""
    model_letter = extract_choice_letter(model_answer, "ABCD")
    expected = expected_answer.strip().upper()
    return model_letter == expected, f"expected={expected}, got={model_letter}"

# MMLU grader: answer is index (0-3), choices are A-D
def grade_mmlu(model_answer, expected_answer, choices=None):
    """MMLU: answer is an index 0-3, model outputs a letter."""
    model_letter = extract_choice_letter(model_answer, "ABCD")
    expected_idx = int(expected_answer)
    expected_letter = chr(ord("A") + expected_idx)
    return model_letter == expected_letter, f"expected={expected_letter}, got={model_letter}"


def load_skill():
    """Load the TAHOE skill prompt — backward compat for existing callers."""
    return load_arm_prompt("tahoe")


def _numeric_equal(a, b, rel_tol=1e-6):
    """Numeric answer equality: 42 == '42.00', '16,000' == 16000, '$5' == 5.

    Falls back to exact string comparison when either side is not a number.
    Arm-agnostic: used identically for every arm.
    """
    def to_float(x):
        s = str(x).replace(",", "").replace("\u202f", "").replace(" ", "")
        try:
            return float(s)
        except ValueError:
            return None
    fa, fb = to_float(a), to_float(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) <= rel_tol * max(1.0, abs(fa), abs(fb))
    return str(a).strip() == str(b).strip()


# Final-answer letter marker: 'Answer: D', 'the answer is E', 'FINAL ANSWER: B'.
# A separator ('is' or ':'/'-') is REQUIRED so option discussion like
# 'Answer (E) makes the common mistake...' is not mistaken for a declaration.
_ANSWER_MARKER_TEMPLATE = (
    r"(?:final\s+)?answer\b\s*(?:is\b\s*[:\-]?|[:\-])\s*\(?([{letters}])\)?\b"
)


def extract_choice_letter(model_answer, letters="ABCD"):
    """Extract the model's final multiple-choice letter (arm-agnostic).

    Priority (regression fix: an explicit final-answer marker must win over
    earlier discussed options):
    1. the whole (markdown-stripped) answer is a bare letter or '(X)';
    2. the LAST explicit marker ('Answer: D', 'the answer is B', ...);
    3. the last non-empty line is a bare letter or '(X)';
    4. fallback: first standalone letter anywhere (legacy behavior).
    """
    clean = re.sub(r'\*+', '', str(model_answer)).strip()
    marker = re.compile(_ANSWER_MARKER_TEMPLATE.format(letters=letters), re.I)
    m = re.fullmatch(rf"\(?([{letters}])\)?[\s.,:!]*", clean, re.I)
    if m:
        return m.group(1).upper()
    marks = marker.findall(clean)
    if marks:
        return marks[-1].upper()
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if lines:
        m = re.fullmatch(rf"\(?([{letters}])\)?[\s.,:!]*", lines[-1], re.I)
        if m:
            return m.group(1).upper()
    m = re.search(rf"\b([{letters}])\b", clean.upper())
    if m:
        return m.group(1)
    return clean[:1].upper() if clean else ""


def extract_gsm8k_gold(answer_text):
    """GSM8K official: extract the number after #### in the gold answer.

    Separator-aware (commas, thin spaces, decimals) so '#### 43,200' and
    '#### 42.00' are extracted whole; markdown headings ('#### Section')
    match nothing, same as before.
    """
    match = re.search(rf"####\s*\$?\s*({_SEP_NUM_RE})", answer_text)
    if not match:
        return ""
    return (match.group(1)
            .replace(",", "")
            .replace("\u202f", "")
            .replace(" ", ""))


_SEP_NUM_RE = r"-?\d{1,3}(?:[,\u202f ]\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?"

# Explicit numeric final-answer marker: 'Answer: N' — the number must
# follow the marker immediately (only '$'/whitespace between), so the
# marker states the answer rather than discussing it ('Answer: After 3
# hours the trains are 270 miles apart' does NOT declare 3). The colon
# keeps option discussion ('Answer (E) makes...') out, and the LAST
# occurrence wins, matching the marker semantics of the choice graders.
_ANSWER_MARKER_RE = re.compile(
    r"\banswer\s*:\s*\$?\s*(" + _SEP_NUM_RE + r")", re.I
)

# A same-quantity restatement connector: after a number and its unit,
# '(' starts a parenthetical restatement, ', or' / 'which is' / 'i.e.' /
# 'aka' / an em-dash starts a verbal one. The gap before the connector
# stays on one line and is free of digits, so the FIRST number is the
# one being restated; '\(' (LaTeX inline math) is not a restatement.
_RESTATEMENT_CONNECTOR_RE = re.compile(
    r"(?P<gap>[^\d()\n]{0,40}?)"
    r"(?P<connector>(?<!\\)\(|,?\s*(?:which\s+is|i\.e\.|aka|or)\b|[—–])"
)

# A trailing 'NUM unit (...digits...)' parenthetical that restates the
# stated answer in other units or as a breakdown.
_TRAILING_PAREN_RESTATE_RE = re.compile(
    "(" + _SEP_NUM_RE + r")[^\d()\n]{0,40}(?<!\\)\(([^()]*)\)\s*[.!]*\s*$"
)

# Words that explicitly mark a parenthetical as a restatement.
_PAREN_KEYWORD_RE = re.compile(r"\b(?:which\s+is|i\.?e\.|aka)\b", re.I)

# A clock-form answer: H:MM with an explicit am/pm marker. The minutes
# must be exactly two digits, the marker may be upper-case, dotted
# ('a.m.', 'P.M.') or separated by a plain/thin space ('2:00\u202fpm'),
# and the whole time must END the span. Ratios ('3:1' — one-digit
# minute, no marker), plain times ('at 2:00'), decimals ('2.50'), colon
# labels ('Part 2: 00') and clock mentions with later numeric context
# ('... at 2:00 pm and walks 5 miles') therefore never match.
_CLOCK_TIME_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})[ \u202f]*([ap])\.?[ \u202f]*m\.?(?![A-Za-z])"
    r"[\s.,;:!)*\]}]*$",
    re.I,
)

# LaTeX text-mode wrappers and thin spacing that may appear inside a
# \boxed{...} clock answer ('\text{:}', '\text{ pm}', '2\!:\!00').
# Unwrapped ONLY for the boxed clock-form check; the generic number
# extraction of boxed content is untouched.
_BOXED_TEXT_WRAP_RE = re.compile(r"\\(?:text|mathrm)\s*\{([^{}]*)\}")
_BOXED_SPACING_TOKENS = ("\\!", "\\,", "\\;", "\\ ", "\\:")


def _clean_number(token):
    """Normalize an extracted numeric token: drop thousands separators."""
    return token.replace(",", "").replace("\u202f", "").replace(" ", "")


def _paren_restates(content):
    """Does a parenthetical restate a same-quantity answer?

    Real restatements carry words (units) and either an explicit
    'which is' or more than one number ('2 hours 40 minutes', '3 onions
    and 1 potato'), so bare number lists ('1, 3, 6') and single-total
    asides ('13 letters altogether') are left alone.
    """
    if not re.search(r"[A-Za-z]", content) or not re.search(r"\d", content):
        return False
    return bool(
        _PAREN_KEYWORD_RE.search(content)
        or len(re.findall(_SEP_NUM_RE, content)) > 1
    )


def _clock_hour(text):
    """Stated hour when the text ENDS with an H:MM am/pm clock time.

    A clock-form answer states the hour ('2:00 pm' -> '2',
    '12:30pm' -> '12'): the H:MM pair is not a number, and the broad
    last-number heuristic would otherwise return the minutes ('00').
    The end anchor and the required am/pm marker keep every
    non-clock colon form (ratios, plain times, decimals, colon labels)
    and clock mentions followed by later numeric context untouched.
    """
    m = _CLOCK_TIME_RE.search(text)
    return m.group(1) if m else None


def _boxed_clock_hour(inner):
    """Stated hour when a \\boxed{...} answer is a LaTeX clock time.

    '\\boxed{2\\text{:}00 \\text{ pm}}' states the hour 2: the text-mode
    wrappers and thin LaTeX spacing are unwrapped for the clock-form
    check only ('2\\text{:}00 \\text{ pm}' reads as '2:00 pm'), so every
    other boxed form — plain numbers, thousands separators, units,
    ratios without an am/pm marker — keeps the generic last-number
    extraction unchanged.
    """
    plain = _BOXED_TEXT_WRAP_RE.sub(r"\1", inner)
    for token in _BOXED_SPACING_TOKENS:
        plain = plain.replace(token, "")
    return _clock_hour(plain)


def _marker_number(norm):
    """Number stated by an explicit final-answer marker, if any.

    The LAST 'Answer:' wins and the answer number must follow the marker
    immediately ('Answer: 448 mL of medicine in 8 doses.' -> 448), so
    trailing context can no longer steal the extraction while a marker
    discussing its answer ('Answer: After 3 hours ... 270 miles apart')
    is left to the later heuristics.
    """
    last = None
    for last in _ANSWER_MARKER_RE.finditer(norm):
        pass
    return _clean_number(last.group(1)) if last else None


def _span_number(span):
    """Answer number of a short final-answer span (a bold span).

    Same-quantity restatements resolve to their FIRST number: in
    '225 minutes, or 3 hours and 45 minutes' (or '160 minutes (2 hours 40
    minutes)') the leading number is the stated answer and the rest merely
    restates it in other units. Anything else keeps the last-number
    semantics ('Count: 3 routes' -> 3). A parenthetical restatement must
    carry words and digits, so number lists like '(1, 3, 6)' do not
    trigger it; a verbal connector requires a unit word in the gap, so
    '3 or 4' does not either. A span ending in an H:MM am/pm clock
    time states its hour ('**2:00 pm**' -> 2).
    """
    clock = _clock_hour(span)
    if clock is not None:
        return clock
    nums = list(re.finditer(_SEP_NUM_RE, span))
    if not nums:
        return None
    first = nums[0]
    m = _RESTATEMENT_CONNECTOR_RE.match(span[first.end():])
    if m:
        tail = span[first.end() + m.end():]
        if m.group("connector") == "(":
            close = tail.find(")")
            content = tail[: close if close != -1 else len(tail)]
            restates = bool(
                re.search(r"[A-Za-z]", content) and re.search(r"\d", content)
            )
        else:
            restates = bool(
                re.search(r"[A-Za-z]", m.group("gap"))
                and re.search(r"\d", tail)
            )
        if restates:
            return first.group(0)
    return nums[-1].group(0)


def _last_number(norm):
    r"""Last separator-aware number, with a trailing-restatement guard.

    A final 'NUM unit (...digits...)' parenthetical that restates the
    stated answer in other units or as a breakdown ('216 seconds (which
    is 3 minutes 36 seconds)' -> 216, '4 (3 onions and 1 potato)' -> 4)
    hands the extraction to the number before the parenthesis instead of
    the broad last-number heuristic. The guard is end-anchored, stays on
    one line and skips LaTeX '\(...\)' math, so ordinary trailing text
    keeps the last-number behavior. A trailing H:MM am/pm clock time
    states its hour instead ('2:00 pm' -> 2, '12:30pm' -> 12).
    """
    m = _TRAILING_PAREN_RESTATE_RE.search(norm)
    if m and _paren_restates(m.group(2)):
        return m.group(1)
    clock = _clock_hour(norm)
    if clock is not None:
        return clock
    nums = re.findall(_SEP_NUM_RE, norm)
    return nums[-1] if nums else None


def extract_model_number(text):
    """Extract a number from model output — same for both arms.

    v6 (OSS-audit LOW: clock-form answers state their hour). Priority:
    1. #### N          (official GSM8K marker; decimals and '$' handled,
                        so '#### 42.50' is not truncated to '42')
    2. \\boxed{...}    (nested-brace tolerant; LaTeX thousands separators
                        normalized first: '43{,}200' -> 43200; a boxed
                        LaTeX clock time states its hour:
                        '\\boxed{2\\text{:}00 \\text{ pm}}' -> 2)
    3. 'Answer: N'     (LAST marker; N follows the marker immediately, so
                        trailing context like 'in 8 doses' no longer wins
                        while 'Answer: After 3 hours ... 270 miles apart'
                        still falls through to the bold span)
    4. LAST bold span  (**Answer: $12** / **It takes 5 hours**), with
                        same-quantity restatements resolved to their
                        first number (**225 minutes, or 3 hours and 45
                        minutes** -> 225)
    5. 'answer is N' / 'total = N' (last occurrence)
    6. last separator-aware number, with an end-anchored unit-restatement
       guard ('216 seconds (which is 3 minutes 36 seconds)' -> 216);
       bold spans and the bare-text fallback also resolve a TRAILING
       H:MM am/pm clock time to its stated hour ('2:00 pm' -> 2,
       '**12:30pm**' -> 12, thin-space/upper-case/dotted markers too)
       instead of the minutes ('00'). End-anchored on the am/pm marker,
       so ratios ('3:1'), plain times ('at 2:00'), decimals ('2.50'),
       colon labels ('Part 2: 00') and clock mentions followed by later
       numeric context ('... 2:00 pm and walks 5 miles' -> 5) are not
       touched.
    Handles '1,430', '2\\,000', '$2,180', thin spaces, negatives, and
    decimals at every step. v4 lost correct stated answers to the broad
    last-bold/last-number heuristics when the answer sentence carried a
    unit-conversion restatement ('**Answer: 160 minutes (2 hours 40
    minutes).**' -> 40) or trailing context ('**Answer: 448 mL of
    medicine in 8 doses.**' -> 8); v5 then lost clock-form answers to
    the same heuristics ('2:00 pm' -> '00' vs gold hour 2).
    """
    text = str(text).strip()
    match = re.search(rf"####\s*\$?\s*({_SEP_NUM_RE})", text)
    if match:
        return _clean_number(match.group(1))
    sep = _SEP_NUM_RE
    boxed = re.search(r"\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}", text)
    if boxed:
        inner = (
            boxed.group(1)
            .replace("{,}", ",")
            .replace("\\,", "")
            .replace("\\ ", "")
        )
        clock = _boxed_clock_hour(inner)
        if clock is not None:
            return clock
        nums = re.findall(sep, inner)
        if nums:
            return _clean_number(nums[-1])
    norm = (
        text.replace("\\,", "")
        .replace("\\ ", "")
        .replace("\u202f", " ")
        .replace("$", "")
    )
    marker = _marker_number(norm)
    if marker is not None:
        return marker
    bolds = re.findall(r"\*\*([^*]+)\*\*", norm)
    if bolds:
        span_num = _span_number(bolds[-1])
        if span_num is not None:
            return _clean_number(span_num)
    matches = re.findall(
        r"(?:answer|result|total)\s*(?:is|=|:)\s*(" + sep + r")", norm, re.I)
    if matches:
        return _clean_number(matches[-1])
    last = _last_number(norm)
    if last is not None:
        return _clean_number(last)
    return norm[:50]


def grade_gsm8k(model_answer, expected_answer):
    """GSM8K: extract number from model output, compare to gold number.

    Numeric comparison (42 == 42.00, '16,000' == 16000, '$5' == 5) — the
    string comparison under-credited correct answers that spelled the
    number differently from the gold ('#### 42' vs '42.00').
    """
    model_num = extract_model_number(model_answer)
    expected_num = extract_gsm8k_gold(expected_answer)
    ok = _numeric_equal(model_num, expected_num)
    return ok, f"expected={expected_num}, got={model_num}"


def grade_mmlu_pro(model_answer, expected_answer):
    """MMLU-Pro: up to 10 options, answer letter A-J. Official eval = letter match."""
    model_letter = extract_choice_letter(model_answer, "ABCDEFGHIJ")
    expected = expected_answer.strip().upper()
    return model_letter == expected, f"expected={expected}, got={model_letter}"


def grade_aime(model_answer, expected_answer):
    """AIME: integer answer 0-999. Gold is a bare integer (no #### marker),
    so both sides go through the same arm-agnostic v6 extractor."""
    model_num = extract_model_number(model_answer)
    gold_num = extract_model_number(expected_answer)
    ok = model_num != "" and _numeric_equal(model_num, gold_num)
    return ok, f"expected={gold_num}, got={model_num}"


def _arc_expected_letters(expected_answer, labels=None):
    """Normalize an ARC answerKey to the letter scheme the prompt requests.

    ARC-Challenge items mix letter answerKeys ('A'-'D') with numeric labels
    ('1'-'4'). The prompt always asks 'Answer with just the letter (A, B, C,
    or D)', so a numeric key maps positionally to its letter ('3' -> 'C').
    With ``labels`` (the dataset's choice labels) the mapping uses the actual
    label position; otherwise digits 1-4 map directly.
    """
    expected = str(expected_answer).strip()
    if labels:
        for idx, label in enumerate(labels):
            if str(label).strip().upper() == expected.upper():
                return chr(ord("A") + idx), expected.upper()
    if expected.upper() in ("A", "B", "C", "D"):
        return expected.upper(), expected.upper()
    try:
        idx = int(expected)
    except ValueError:
        return expected.upper(), expected.upper()
    letter = chr(ord("A") + idx - 1) if 1 <= idx <= 4 else expected.upper()
    return letter, expected.upper()


def grade_arc(model_answer, expected_answer, labels=None):
    """ARC: match answerKey (A/B/C/D). Official eval = exact letter match.

    Numeric answerKeys ('1'-'4') are mapped to the requested letter scheme
    (regression: expected=3, model answered 'C' for the third choice and was
    marked wrong). The model may answer with either the letter or the raw
    numeric label of the correct choice.
    """
    model_letter = extract_choice_letter(model_answer, "ABCD")
    expected_letter, expected_raw = _arc_expected_letters(expected_answer, labels)
    ok = model_letter == expected_letter or model_letter == expected_raw
    return ok, f"expected={expected_letter}, got={model_letter}"


def grade_bbh(model_answer, expected_answer):
    """BBH: match the correct option letter. Official eval = letter equality.

    Accepts '(X)', 'X', or any text containing the letter as a word/paren.
    An explicit final-answer marker ('Answer: (E)', 'the answer is G') wins
    over earlier discussed options; otherwise the legacy '(X)'-first and
    bare-letter-first behavior is preserved.
    """
    model_clean = re.sub(r'\*+', '', model_answer.strip())
    expected_clean = expected_answer.strip()
    expected_match = re.search(r'\(([A-Z])\)', expected_clean)
    expected_letter = expected_match.group(1) if expected_match else expected_clean

    # 0. explicit final-answer marker (last one wins)
    marker = re.compile(_ANSWER_MARKER_TEMPLATE.format(letters="A-Z"), re.I)
    marks = marker.findall(model_clean)
    if marks:
        return marks[-1].upper() == expected_letter, (
            f"expected={expected_letter}, got={marks[-1].upper()}"
        )
    # 1. (X) pattern
    model_match = re.search(r'\(([A-Z])\)', model_clean)
    if model_match:
        return model_match.group(1) == expected_letter, (
            f"expected={expected_letter}, got={model_match.group(1)}"
        )
    # 2. bare letter
    m = re.search(r'\b([A-Z])\b', model_clean.upper())
    if m:
        return m.group(1) == expected_letter, (
            f"expected={expected_letter}, got={m.group(1)}"
        )
    return model_clean == expected_clean, f"expected={expected_letter}, got={model_clean[:50]}"


def grade_bbh_arith(model_answer, expected_answer):
    """BBH multistep arithmetic: compare final number (numeric equality,
    so '1,080' == 1080 and '42.00' == 42)."""
    model_num = extract_model_number(model_answer)
    expected_num = extract_model_number(expected_answer)
    ok = _numeric_equal(model_num, expected_num)
    return ok, f"expected={expected_num}, got={model_num}"


def grade_lsat(model_answer, expected_answer):
    """LSAT: answer is a letter (A-E)."""
    model_letter = extract_choice_letter(model_answer, "ABCDE")
    expected = expected_answer.strip().upper()
    return model_letter == expected, f"expected={expected}, got={model_letter}"


def load_tasks():
    """Load tasks from 3 public benchmarks."""
    from datasets import load_dataset
    tasks = []

    # GSM8K — grade school math word problems
    gsm8k = load_dataset('gsm8k', 'main', split='test')
    rng = random.Random(SEED)
    indices = rng.sample(range(len(gsm8k)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = gsm8k[i]
        tasks.append({
            "task_id": f"gsm8k-{i:04d}",
            "benchmark": "gsm8k",
            "description": ex["question"],
            "expected": ex["answer"],
            "grader": "gsm8k",
            "difficulty": "medium",
        })

    # ARC-Challenge — science multiple choice
    arc = load_dataset('allenai/ai2_arc', 'ARC-Challenge', split='test')
    indices = rng.sample(range(len(arc)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = arc[i]
        choices = " ".join(f"({k}) {v}" for k, v in zip(ex["choices"]["label"], ex["choices"]["text"]))
        tasks.append({
            "task_id": f"arc-{i:04d}",
            "benchmark": "arc",
            "description": f"{ex['question']}\n\nChoices: {choices}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": ex["answerKey"],
            "labels": ex["choices"]["label"],
            "grader": "arc",
            "difficulty": "hard",
        })

    # BBH — logical deduction 7 objects (hard)
    bbh = load_dataset('lukaemon/bbh', 'logical_deduction_seven_objects', split='test')
    indices = rng.sample(range(len(bbh)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = bbh[i]
        tasks.append({
            "task_id": f"bbh-{i:04d}",
            "benchmark": "bbh",
            "description": f"{ex['input']}\n\nAnswer with the letter of the correct option.",
            "expected": ex["target"],
            "grader": "bbh",
            "difficulty": "hard",
        })

    # BBH — tracking shuffled objects 7 (hard — state tracking across shuffles)
    bbh_track = load_dataset('lukaemon/bbh', 'tracking_shuffled_objects_seven_objects', split='test')
    indices = rng.sample(range(len(bbh_track)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = bbh_track[i]
        tasks.append({
            "task_id": f"bbh-track-{i:04d}",
            "benchmark": "bbh_track",
            "description": f"{ex['input']}\n\nAnswer with the letter of the correct option.",
            "expected": ex["target"],
            "grader": "bbh",
            "difficulty": "hard",
        })

    # BBH — multistep arithmetic (hard — 3+ step computation)
    bbh_arith = load_dataset('lukaemon/bbh', 'multistep_arithmetic_two', split='test')
    indices = rng.sample(range(len(bbh_arith)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = bbh_arith[i]
        tasks.append({
            "task_id": f"bbh-arith-{i:04d}",
            "benchmark": "bbh_arith",
            "description": f"{ex['input']}\n\nAnswer with just the number.",
            "expected": ex["target"],
            "grader": "bbh_arith",
            "difficulty": "hard",
        })

    # MMLU — college mathematics (hard — university-level math)
    mmlu_math = load_dataset('hails/mmlu_no_train', 'college_mathematics', split='test')
    indices = rng.sample(range(len(mmlu_math)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = mmlu_math[i]
        choices = "\n".join(f"({chr(ord('A')+j)}) {c}" for j, c in enumerate(ex["choices"]))
        tasks.append({
            "task_id": f"mmlu-math-{i:04d}",
            "benchmark": "mmlu_math",
            "description": f"{ex['question']}\n\n{choices}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": str(ex["answer"]),
            "choices": ex["choices"],
            "grader": "mmlu",
            "difficulty": "hard",
        })

    # MMLU — formal logic (hard — logical reasoning)
    mmlu_logic = load_dataset('hails/mmlu_no_train', 'formal_logic', split='test')
    indices = rng.sample(range(len(mmlu_logic)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = mmlu_logic[i]
        choices = "\n".join(f"({chr(ord('A')+j)}) {c}" for j, c in enumerate(ex["choices"]))
        tasks.append({
            "task_id": f"mmlu-logic-{i:04d}",
            "benchmark": "mmlu_logic",
            "description": f"{ex['question']}\n\n{choices}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": str(ex["answer"]),
            "choices": ex["choices"],
            "grader": "mmlu",
            "difficulty": "hard",
        })

    # MMLU — professional accounting (hard — finance reasoning)
    mmlu_acct = load_dataset('hails/mmlu_no_train', 'professional_accounting', split='test')
    indices = rng.sample(range(len(mmlu_acct)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = mmlu_acct[i]
        choices = "\n".join(f"({chr(ord('A')+j)}) {c}" for j, c in enumerate(ex["choices"]))
        tasks.append({
            "task_id": f"mmlu-acct-{i:04d}",
            "benchmark": "mmlu_acct",
            "description": f"{ex['question']}\n\n{choices}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": str(ex["answer"]),
            "choices": ex["choices"],
            "grader": "mmlu",
            "difficulty": "hard",
        })

    # LSAT-LR — logical reasoning (hard — law school)
    lsat = load_dataset('hails/agieval-lsat-lr', split="test")
    indices = rng.sample(range(len(lsat)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = lsat[i]
        choices = "\n".join(ex["choices"])
        gold_idx = ex["gold"][0] if isinstance(ex["gold"], list) else ex["gold"]
        gold_letter = chr(ord("A") + gold_idx)
        tasks.append({
            "task_id": f"lsat-{i:04d}",
            "benchmark": "lsat",
            "description": f"{ex['query']}\n\n{choices}\n\nAnswer with just the letter (A, B, C, D, or E).",
            "expected": gold_letter,
            "grader": "lsat",
            "difficulty": "hard",
        })

    # RACE — long reading comprehension (hard — 1500+ char passages)
    import ast as _ast
    race = load_dataset("EleutherAI/race", "high", split="test")
    indices = rng.sample(range(len(race)), MAX_SAMPLES_PER_BENCH)
    for i in indices:
        ex = race[i]
        probs = _ast.literal_eval(ex['problems'])
        prob = probs[0]  # Take first question from each article
        choices = "\n".join(f"({chr(ord('A')+j)}) {opt}" for j, opt in enumerate(prob['options']))
        tasks.append({
            "task_id": f"race-{i:04d}",
            "benchmark": "race",
            "description": f"Read the following passage and answer the question.\n\n{ex['article']}\n\nQuestion: {prob['question']}\n\n{choices}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": prob['answer'],
            "grader": "race",
            "difficulty": "hard",
        })

    # LiveCodeBench release_v6 subset — execution-verified code generation
    lcb_path = Path(__file__).parent / "data" / "lcb_v6_150.jsonl"
    lcb = [json.loads(l) for l in lcb_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    for ex in lcb:
        starter = ex["starter_code"].strip()
        instruction = (
            "Write a Python solution as a single ```python code block. "
            "If the starter code defines a Solution class, provide the complete class with the required method; "
            "otherwise write a script that reads from standard input and prints the answer. "
            "No test code, no I/O beyond what the problem requires."
        )
        tasks.append({
            "task_id": ex["task_id"],
            "benchmark": "lcb",
            "description": f"{ex['question_content']}\n\n{starter}\n\n{instruction}",
            "expected": "execution-verified",
            "grader": "lcb",
            "difficulty": ex["difficulty"],
            "problem": ex,
        })

    # GPQA Diamond — PhD-level science MC (198 questions, full set from YT)
    gpqa_path = Path(__file__).parent / "data" / "gpqa_diamond.jsonl"
    # split on \n only: question text may contain Unicode line separators
    gpqa = [json.loads(l) for l in gpqa_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    if GPQA_LIMIT:
        gpqa = gpqa[:GPQA_LIMIT]
    for ex in gpqa:
        opts = "\n".join(f"({chr(ord('A')+j)}) {o}" for j, o in enumerate(ex["options"]))
        tasks.append({
            "task_id": ex["task_id"],
            "benchmark": "gpqa",
            "description": f"{ex['question']}\n\n{opts}\n\nAnswer with just the letter (A, B, C, or D).",
            "expected": ex["expected"],
            "grader": "gpqa",
            "difficulty": "hard",
        })

    # AIME 2024+2025 — competition math, integer answers 0-999 (60 problems)
    aime_path = Path(__file__).parent / "data" / "aime60.jsonl"
    aime = [json.loads(l) for l in aime_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    for ex in aime:
        tasks.append({
            "task_id": ex["task_id"],
            "benchmark": "aime",
            "description": f"{ex['problem']}\n\nGive your final answer as a single integer between 0 and 999.",
            "expected": ex["expected"],
            "grader": "aime",
            "difficulty": "hard",
        })

    # MMLU-Pro — stratified 800-question subset, 10-option discrimination
    mmlupro_path = Path(__file__).parent / "data" / "mmlu_pro_800.jsonl"
    mmlupro = [json.loads(l) for l in mmlupro_path.read_text(encoding="utf-8").split("\n") if l.strip()]
    for ex in mmlupro:
        opts = "\n".join(f"({chr(ord('A')+j)}) {o}" for j, o in enumerate(ex["options"]))
        tasks.append({
            "task_id": ex["task_id"],
            "benchmark": "mmlu_pro",
            "description": f"{ex['question']}\n\n{opts}\n\nAnswer with just the letter of the correct option.",
            "expected": ex["expected"],
            "grader": "mmlu_pro",
            "difficulty": "hard",
        })

    return tasks


def grade_task(task, model_answer):
    grader = task["grader"]
    if grader == "gsm8k":
        return grade_gsm8k(model_answer, task["expected"])
    elif grader == "arc":
        return grade_arc(model_answer, task["expected"], labels=task.get("labels"))
    elif grader == "bbh":
        return grade_bbh(model_answer, task["expected"])
    elif grader == "bbh_arith":
        return grade_bbh_arith(model_answer, task["expected"])
    elif grader == "lsat":
        return grade_lsat(model_answer, task["expected"])
    elif grader == "mmlu":
        return grade_mmlu(model_answer, task["expected"], task.get("choices"))
    elif grader == "math":
        return grade_math(model_answer, task["expected"])
    elif grader == "race":
        return grade_race(model_answer, task["expected"])
    elif grader == "gpqa":
        return grade_arc(model_answer, task["expected"], labels=task.get("labels"))
    elif grader == "aime":
        return grade_aime(model_answer, task["expected"])
    elif grader == "mmlu_pro":
        return grade_mmlu_pro(model_answer, task["expected"])
    elif grader == "lcb":
        from lcb_sandbox import run_lcb_trial
        r = run_lcb_trial(task["problem"], model_answer)
        return r["passed"], f"{r['failure_class']}: {r['summary']}"
    return False, "unknown grader"


def run_trial(task, arm, skill_prompt, trial_idx):
    # Determine system prompt: tahoe arm uses the passed skill_prompt;
    # baseline arms load their own prompt from ARM_PROMPT_FILES.
    if arm == "tahoe":
        system_prompt = skill_prompt
    else:
        system_prompt = load_arm_prompt(arm)
    result = run_classic(
        task_id=f"{task['task_id']}-{arm}-t{trial_idx}",
        task_prompt=task["description"],
        model=os.environ.get("TAHOE_MODEL", "."),
        api_base=os.environ.get("TAHOE_API_BASE", ""),
        api_key=os.environ.get("TAHOE_API_KEY", ""),
        max_turns=1,
        max_tokens=2048,  # increased for hard reasoning tasks
        timeout_seconds=60,
        system_prompt=system_prompt,
    )
    passed, detail = grade_task(task, result.final_answer)
    # Truthful outcome capture (shared policy from runner_classic): the
    # runner's failure class is preserved verbatim and can never grade
    # into a pass; a token-limit-capped answer that fails grading is
    # "truncated", not an ordinary wrong_answer. The grader itself is
    # untouched and stays arm-agnostic.
    passed, failure_class = grading_outcome(
        getattr(result, "failure_class", "none"),
        passed,
        getattr(result, "finish_reason", ""),
    )

    ref_counts = count_typed_refs(result.final_answer)
    verified_steps = ref_counts["verified_logical_steps"]
    typed_refs = ref_counts["typed_refs_produced"]
    repeated_refs = ref_counts["repeated_refs"]
    retired_refs = ref_counts["retired_refs"]
    total_refs = ref_counts["total_refs_produced"]

    return {
        "task_id": task["task_id"],
        "benchmark": task["benchmark"],
        "arm": arm,
        "trial": trial_idx,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "wall_seconds": result.wall_seconds,
        "passed": passed,
        "failure_class": failure_class,
        "authoring_tokens": 0,
        "final_answer": result.final_answer,
        "quality_score": 1.0 if passed else 0.0,
        "grader_detail": detail,
        # Preserve the runner's truthful trial outcome: finish reason,
        # truncation, empty-response status, retry history/count and the
        # complete first-request generation parameters.
        **outcome_fields(result),
        "verified_logical_steps": verified_steps,
        "typed_refs_produced": typed_refs,
        "repeated_refs": repeated_refs,
        "retired_refs": retired_refs,
        "total_refs_produced": total_refs,
    }


def main():
    print("Loading public benchmarks...")
    tasks = load_tasks()
    if BENCHES:
        tasks = [t for t in tasks if t["benchmark"] in BENCHES]
    print(f"  {len(tasks)} tasks loaded")

    skill_prompt = load_skill()

    trial_plan = []
    for task in tasks:
        for arm in ARMS:
            for t in range(TRIALS_PER_TASK):
                trial_plan.append((task, arm, t))

    rng = random.Random(SEED)
    rng.shuffle(trial_plan)

    print(f"Running {len(trial_plan)} trials (shuffled, seed={SEED})...")
    all_trials = []
    for i, (task, arm, trial_idx) in enumerate(trial_plan):
        print(f"  [{i+1}/{len(trial_plan)}] {task['task_id']} / {arm} / t{trial_idx} ...", end=" ", flush=True)
        try:
            result = run_trial(task, arm, skill_prompt, trial_idx)
            all_trials.append(result)
            print(f"passed={result['passed']} tokens={result['total_tokens']}")
        except Exception as e:
            print(f"ERROR: {e}")
            all_trials.append({
                "task_id": task["task_id"],
                "benchmark": task["benchmark"],
                "arm": arm,
                "trial": trial_idx,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "wall_seconds": 0.0,
                "passed": False,
                "failure_class": "error",
                "final_answer": f"ERROR: {e}",
                "quality_score": 0.0,
                "grader_detail": str(e),
                "authoring_tokens": 0,
                # Same truthful-outcome keys as run_trial, zeroed out: the
                # schema of a serialized trial stays identical either way.
                "finish_reason": "",
                "truncated": False,
                "cap_exhausted": False,
                "output_token_cap": 0,
                "empty_response": False,
                "retries": 0,
                "retry_history": [],
                "request_params": {},
                "verified_logical_steps": 0,
                "typed_refs_produced": 0,
                "repeated_refs": 0,
                "retired_refs": 0,
                "total_refs_produced": 0,
            })

    print("\n=== RESULTS (per benchmark) ===\n")

    # Group by benchmark + arm
    from collections import defaultdict
    groups = defaultdict(list)
    for t in all_trials:
        groups[(t["benchmark"], t["arm"])].append(t)

    print("\n=== PAPER RESULTS TABLE ===\n")

    # Dynamic table header: one column per arm
    arm_names = sorted(set(t['arm'] for t in all_trials))
    header_arm_cols = " | ".join(f"{a:>8s}" for a in arm_names)
    pass_arm_cols = " | ".join(f"{a+' pass':>8s}" for a in arm_names)
    print(f"{'benchmark':14s} | {header_arm_cols} | {pass_arm_cols}")
    print("-" * (16 + len(arm_names) * 19))

    for bench in sorted(set(t['benchmark'] for t in all_trials)):
        parts = [f"{bench:14s}"]
        for a in arm_names:
            arm_trials = [t for t in all_trials if t['benchmark']==bench and t['arm']==a]
            cp = sum(1 for x in arm_trials if x['passed'])
            parts.append(f"{cp:>3d}/{len(arm_trials):<4d}" if arm_trials else f"{'--':>8s}")
        for a in arm_names:
            arm_trials = [t for t in all_trials if t['benchmark']==bench and t['arm']==a]
            if arm_trials:
                cp = sum(1 for x in arm_trials if x['passed'])
                parts.append(f"{100*cp/len(arm_trials):>7.0f}%")
            else:
                parts.append(f"{'--':>8s}")
        print(" | ".join(parts))

    # Overall per arm
    print("-" * (16 + len(arm_names) * 19))
    parts = [f"{'OVERALL':14s}"]
    for a in arm_names:
        arm_trials = [t for t in all_trials if t['arm']==a]
        cp = sum(1 for x in arm_trials if x['passed'])
        parts.append(f"{cp:>3d}/{len(arm_trials):<4d}" if arm_trials else f"{'--':>8s}")
    for a in arm_names:
        arm_trials = [t for t in all_trials if t['arm']==a]
        if arm_trials:
            cp = sum(1 for x in arm_trials if x['passed'])
            parts.append(f"{100*cp/len(arm_trials):>7.0f}%")
        else:
            parts.append(f"{'--':>8s}")
    print(" | ".join(parts))

    # Save into a fresh, exclusive run directory (never a fixed path at
    # the results root) with a configuration/source manifest.
    from outdir import make_run_dir, write_manifest
    results_dir = make_run_dir("public-bench")
    write_manifest(
        results_dir,
        config={
            "runner": "run_public_bench.py",
            "model": os.environ.get("TAHOE_MODEL", "."),
            "arms": list(ARMS),
            "trials_per_task": TRIALS_PER_TASK,
            "max_turns": 1,
            "max_tokens": 2048,
            "timeout_seconds": 60,
            "seed": SEED,
            "benches": list(BENCHES),
            "max_samples_per_bench": MAX_SAMPLES_PER_BENCH,
        },
        source_files=[
            __file__,
            Path(__file__).parent / "runner_classic.py",
            Path(__file__).parent / "metrics.py",
        ],
    )
    with open(results_dir / "public_benchmarks.json", "w") as f:
        json.dump(all_trials, f, indent=2, sort_keys=True)

    print(f"\nResults saved to {results_dir}/public_benchmarks.json")


if __name__ == "__main__":
    main()
