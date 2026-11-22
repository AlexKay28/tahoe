"""Focused tests for the generic Stage-1 derived-results regrade pipeline.

The pipeline (benchmarks/stage1_regrade.py, CLI benchmarks/
fix_stage1_extraction.py) re-grades all ten archived Stage-1 benchmarks
with the CURRENT ``run_public_bench`` graders into a fresh derived
artifact. Pinned here against regressions:

- the raw input archive is never modified (byte-for-byte);
- ``--input``/``--output`` are explicit and required;
- an existing output is refused via atomic exclusive create;
- every benchmark adapter (gsm8k #### reconstruction, arc positional
  numeric fallback, bbh paren stripping, bbh_arith numeric, lsat/race
  letters, mmlu letter->index inversion) uses the CURRENT grader;
- missing/malformed/inconsistent expected values and grader exceptions
  become explicit ``grader_error`` results, never silent passes;
- empty/missing final answers fail as ``empty_response`` (a runner-level
  primary class, even alongside grader problems) and never grade into a
  pass;
- cap preservation: ``output_token_cap=2048`` and ``cap_exhausted`` are
  derived from ``output_tokens``; no ``finish_reason`` is fabricated and
  no ``truncated`` flag is set from the exact cap alone — only nonempty
  cap-exhausted FAILING answers are ``truncated``, with an explicit
  outcome provenance;
- original verdicts are preserved as ``archived_*`` and raw
  ``final_answer`` values are carried through unchanged;
- the derived artifact is byte-deterministic and records spec/regrader
  versions, input/grader hashes, per-benchmark summaries and verdict
  changes.

An opt-in smoke test (set ``TAHOE_STAGE1_SMOKE=1``) re-grades the real
2026-09-13 stage1-full archives read-only and pins the derived success
counts.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "src"))

import benchmarks.stage1_regrade as rg  # noqa: E402

SCRIPT = ROOT / "benchmarks" / "fix_stage1_extraction.py"

STAGE1_DIR = ROOT / "benchmarks" / "results" / "2026-09-13-stage1-full"
GLM_ARCHIVE = STAGE1_DIR / "full_test_eval.json"
OSS_ARCHIVE = STAGE1_DIR / "oss_full_eval.json"


def run_cli(*args, cwd=ROOT):
    """Run the regrade CLI exactly as a user would (subprocess, no imports)."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_DEFAULT_DETAIL = object()


def trial(benchmark, task_id, final_answer, expected_token, archived_passed,
           output_tokens=100, archived_failure_class=None,
           archived_detail=_DEFAULT_DETAIL):
    """Build a minimal archived trial for the regrade tests.

    Pass ``archived_detail=None`` to record a genuinely missing
    ``grader_detail`` (as the real archives sometimes do).
    """
    if archived_failure_class is None:
        archived_failure_class = "none" if archived_passed else "wrong_answer"
    if archived_detail is _DEFAULT_DETAIL:
        archived_detail = f"expected={expected_token}, got=<old>"
    return {
        "benchmark": benchmark,
        "task_id": task_id,
        "arm": "classic",
        "trial": 0,
        "input_tokens": 10,
        "output_tokens": output_tokens,
        "total_tokens": 10 + output_tokens,
        "passed": archived_passed,
        "failure_class": archived_failure_class,
        "grader_detail": archived_detail,
        "final_answer": final_answer,
        "quality_score": 1.0 if archived_passed else 0.0,
    }


def sample_archive() -> list:
    """A small archived results list covering every adapter and outcome."""
    return [
        # gsm8k: old string comparison failed '42.00' vs gold '42'; the
        # current numeric grade_gsm8k corrects this to a pass.
        trial("gsm8k", "gsm8k-0001", "She has 42.00 dollars left.\n#### 42.00",
              "42", False, output_tokens=120,
              archived_detail="expected=42, got=42.00"),
        # gsm8k: genuinely wrong answer stays wrong.
        trial("gsm8k", "gsm8k-0002", "#### 41", "42", False, output_tokens=30,
              archived_detail="expected=42, got=41"),
        # gsm8k: malformed (empty) expected value -> explicit grader_error.
        trial("gsm8k", "gsm8k-0003", "#### 3", "", True, output_tokens=30,
              archived_detail="expected=, got=3"),
        # gsm8k: empty answer, zero output tokens -> empty_response, no cap.
        trial("gsm8k", "gsm8k-0004", "", "19", False, output_tokens=0,
              archived_detail="expected=19, got="),
        # gsm8k: empty answer with exhausted cap -> empty_response wins over
        # truncated (most specific runner-level label), cap flag recorded.
        trial("gsm8k", "gsm8k-0005", "", "5", False, output_tokens=2048,
              archived_detail="expected=5, got="),
        # gsm8k: nonempty, cap-exhausted, failing grade -> truncated with
        # explicit cap-derived outcome provenance.
        trial("gsm8k", "gsm8k-0006",
              "After a very long derivation the answer is 200.\n#### 200",
              "100", False, output_tokens=2048,
              archived_detail="expected=100, got=200"),
        # gsm8k: archived false pass -> derived wrong_answer (verdict flip).
        trial("gsm8k", "gsm8k-0007",
              "The total is 1,430 but he paid 1,300.\n#### 1300",
              "1430", True, output_tokens=90,
              archived_detail="expected=1430, got=1430"),
        # bbh: cap-exhausted answer that still passes keeps the pass; the
        # cap stays visible through cap_exhausted (no truncation invented).
        trial("bbh", "bbh-0001", "Answer: (G)", "(G)", True, output_tokens=2048,
              archived_detail="expected=(G), got=G"),
        # arc: letter answerKey passes as before.
        trial("arc", "arc-0001", "D", "D", True, output_tokens=20,
              archived_detail="expected=D, got=D"),
        # arc: numeric answerKey ('3' -> 'C') with the model answering 'C';
        # the old grader failed it, the positional fallback passes it.
        trial("arc", "arc-0002", "C", "3", False, output_tokens=25,
              archived_detail="expected=3, got=C"),
        # arc: plain wrong letter stays wrong_answer.
        trial("arc", "arc-0003", "A", "B", False, output_tokens=20,
              archived_detail="expected=B, got=A"),
        # bbh: expected parens stripped; '(X)'-style answer passes via the
        # current grade_bbh.
        trial("bbh", "bbh-0002", "The answer is (G)", "(G)", False,
              output_tokens=200,
              archived_detail="expected=(G), got=G\n\nPosition 1: orange"),
        # bbh: wrong option letter stays wrong_answer.
        trial("bbh", "bbh-0003", "B", "E", False, output_tokens=150,
              archived_detail="expected=E, got=B"),
        # bbh_track: paren expected, bare-letter answer.
        trial("bbh_track", "bbh-track-0001", "A", "(A)", True, output_tokens=40,
              archived_detail="expected=(A), got=A"),
        # bbh_arith: numeric equality fixes formatted model numbers.
        trial("bbh_arith", "bbh-arith-0001", "The result is 1,080.", "1080",
              False, output_tokens=60,
              archived_detail="expected=1080, got=1,080"),
        # bbh_arith: wrong number stays wrong.
        trial("bbh_arith", "bbh-arith-0002", "-5", "-6", False, output_tokens=10,
              archived_detail="expected=-6, got=-5"),
        # lsat: letter match passes.
        trial("lsat", "lsat-0001", "E", "E", True, output_tokens=30,
              archived_detail="expected=E, got=E"),
        # lsat: wrong letter stays wrong_answer.
        trial("lsat", "lsat-0002", "E", "B", False, output_tokens=30,
              archived_detail="expected=B, got=E"),
        # race: letter match passes.
        trial("race", "race-0001", "B", "B", True, output_tokens=15,
              archived_detail="expected=B, got=B"),
        # mmlu_math: archived letter 'D' inverted to index 3 for the current
        # grade_mmlu; the 'D' answer passes.
        trial("mmlu_math", "mmlu-math-0001", "D", "D", True, output_tokens=15,
              archived_detail="expected=D, got=D"),
        # mmlu_logic: inversion then letter mismatch -> wrong_answer.
        trial("mmlu_logic", "mmlu-logic-0001", "B", "A", False, output_tokens=15,
              archived_detail="expected=A, got=B"),
        # mmlu_acct: archived letter 'C' inverted to index 2; answer passes.
        trial("mmlu_acct", "mmlu-acct-0001", "C", "C", True, output_tokens=15,
              archived_detail="expected=C, got=C"),
        # lsat: inconsistent expected letter (out of A-E) -> grader_error.
        trial("lsat", "lsat-0003", "B", "F", False, output_tokens=30,
              archived_detail="expected=F, got=B"),
        # gsm8k: empty answer AND a grader problem -> empty_response stays
        # the runner-level primary class, the detail explains both.
        trial("gsm8k", "gsm8k-0008", "", "42", False, output_tokens=0,
              archived_failure_class="wrong_answer", archived_detail=None),
        # unhandled benchmark: explicit grader_error row, never dropped.
        trial("mmlu_pro", "mmlu-pro-0001", "D", "D", True, output_tokens=15,
              archived_detail="expected=D, got=D"),
    ]


class TestExtractExpectedToken:
    def test_plain_number(self):
        token, reason = rg.extract_expected_token("expected=42, got=42.00")
        assert token == "42"
        assert reason == ""

    def test_thousands_separator_kept(self):
        token, _ = rg.extract_expected_token("expected=43,200, got=43200")
        assert token == "43,200"

    def test_paren_option(self):
        token, _ = rg.extract_expected_token("expected=(G), got=G")
        assert token == "(G)"

    def test_multiline_got_part(self):
        token, _ = rg.extract_expected_token(
            "expected=(D), got=D\n\nSetting up the order from cheapest (1)"
        )
        assert token == "(D)"

    def test_missing_detail(self):
        token, reason = rg.extract_expected_token(None)
        assert token is None
        assert "missing" in reason

    def test_no_expected_field(self):
        token, reason = rg.extract_expected_token("grader exploded")
        assert token is None
        assert "expected=" in reason

    def test_empty_expected_is_malformed(self):
        token, reason = rg.extract_expected_token("expected=, got=3")
        assert token is None
        assert "empty" in reason


class TestNormalizeExpected:
    def test_gsm8k_reconstructs_hash_marker(self):
        expected, reason = rg.normalize_expected("gsm8k", "42")
        assert expected == "#### 42"
        assert reason == ""

    def test_gsm8k_thousands_and_decimals(self):
        assert rg.normalize_expected("gsm8k", "43,200")[0] == "#### 43200"
        assert rg.normalize_expected("gsm8k", "1,430.50")[0] == "#### 1430.50"
        assert rg.normalize_expected("gsm8k", "$-10")[0] == "#### -10"

    def test_gsm8k_malformed_number(self):
        expected, reason = rg.normalize_expected("gsm8k", "abc")
        assert expected is None
        assert "malformed" in reason

    def test_arc_letters_pass_through(self):
        assert rg.normalize_expected("arc", "D") == ("D", "")

    def test_arc_digits_pass_through_for_positional_fallback(self):
        assert rg.normalize_expected("arc", "3") == ("3", "")

    def test_arc_out_of_scheme_key_is_inconsistent(self):
        expected, reason = rg.normalize_expected("arc", "5")
        assert expected is None
        assert "inconsistent" in reason

    def test_bbh_paren_stripped(self):
        assert rg.normalize_expected("bbh", "(G)") == ("G", "")
        assert rg.normalize_expected("bbh_track", "(A)") == ("A", "")
        assert rg.normalize_expected("bbh", "E") == ("E", "")

    def test_bbh_non_letter_is_inconsistent(self):
        expected, reason = rg.normalize_expected("bbh", "42")
        assert expected is None
        assert "inconsistent" in reason

    def test_bbh_arith_number(self):
        assert rg.normalize_expected("bbh_arith", "-1343") == ("-1343", "")
        expected, reason = rg.normalize_expected("bbh_arith", "x")
        assert expected is None
        assert "malformed" in reason

    def test_lsat_letters(self):
        assert rg.normalize_expected("lsat", "E") == ("E", "")
        expected, reason = rg.normalize_expected("lsat", "F")
        assert expected is None
        assert "inconsistent" in reason

    def test_race_letters(self):
        assert rg.normalize_expected("race", "B") == ("B", "")
        expected, reason = rg.normalize_expected("race", "E")
        assert expected is None
        assert "inconsistent" in reason

    def test_mmlu_inverts_letters_to_integer_index(self):
        assert rg.normalize_expected("mmlu_math", "A") == ("0", "")
        assert rg.normalize_expected("mmlu_logic", "B") == ("1", "")
        assert rg.normalize_expected("mmlu_acct", "C") == ("2", "")
        assert rg.normalize_expected("mmlu_math", "D") == ("3", "")
        expected, reason = rg.normalize_expected("mmlu_logic", "E")
        assert expected is None
        assert "inconsistent" in reason

    def test_unhandled_benchmark(self):
        expected, reason = rg.normalize_expected("mmlu_pro", "D")
        assert expected is None
        assert "unhandled benchmark" in reason


class TestAdapters:
    """Every Stage-1 benchmark adapter re-grades with the CURRENT grader."""

    def test_gsm8k_numeric_normalization_flips_to_pass(self):
        out = rg.regrade_trial(sample_archive()[0])
        assert out["passed"] is True
        assert out["failure_class"] == "none"
        assert out["grader_detail"] == "expected=42, got=42.00"
        assert out["archived_passed"] is False

    def test_gsm8k_wrong_answer_stays_wrong(self):
        out = rg.regrade_trial(sample_archive()[1])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_arc_letter_match(self):
        out = rg.regrade_trial(sample_archive()[8])
        assert out["passed"] is True
        assert out["failure_class"] == "none"

    def test_arc_numeric_answer_key_positional_fallback(self):
        out = rg.regrade_trial(sample_archive()[9])
        assert out["passed"] is True  # 'C' vs numeric key '3' -> 'C'
        assert out["grader_detail"] == "expected=C, got=C"
        assert out["archived_passed"] is False

    def test_arc_wrong_letter(self):
        out = rg.regrade_trial(sample_archive()[10])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_bbh_paren_expected_with_paren_answer(self):
        out = rg.regrade_trial(sample_archive()[11])
        assert out["passed"] is True
        assert out["grader_detail"] == "expected=G, got=G"

    def test_bbh_wrong_letter(self):
        out = rg.regrade_trial(sample_archive()[12])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_bbh_track_paren_expected(self):
        out = rg.regrade_trial(sample_archive()[13])
        assert out["passed"] is True
        assert out["failure_class"] == "none"

    def test_bbh_arith_numeric_equality(self):
        out = rg.regrade_trial(sample_archive()[14])
        assert out["passed"] is True
        assert out["grader_detail"] == "expected=1080, got=1080"

    def test_bbh_arith_wrong_number(self):
        out = rg.regrade_trial(sample_archive()[15])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_lsat_letter_match(self):
        out = rg.regrade_trial(sample_archive()[16])
        assert out["passed"] is True
        assert out["failure_class"] == "none"

    def test_lsat_wrong_letter(self):
        out = rg.regrade_trial(sample_archive()[17])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_race_letter_match(self):
        out = rg.regrade_trial(sample_archive()[18])
        assert out["passed"] is True
        assert out["failure_class"] == "none"

    def test_mmlu_math_letter_inversion(self):
        out = rg.regrade_trial(sample_archive()[19])
        assert out["passed"] is True
        assert out["grader_detail"] == "expected=D, got=D"

    def test_mmlu_logic_inversion_then_mismatch(self):
        out = rg.regrade_trial(sample_archive()[20])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"

    def test_mmlu_acct_letter_inversion(self):
        out = rg.regrade_trial(sample_archive()[21])
        assert out["passed"] is True
        assert out["grader_detail"] == "expected=C, got=C"


class TestGraderErrors:
    def test_malformed_expected_is_explicit_grader_error(self):
        out = rg.regrade_trial(sample_archive()[2])
        assert out["passed"] is False  # never a silent pass
        assert out["failure_class"] == "grader_error"
        assert out["grader_detail"].startswith("grader_error: ")
        assert out["quality_score"] == 0.0

    def test_inconsistent_expected_is_explicit_grader_error(self):
        out = rg.regrade_trial(sample_archive()[22])
        assert out["passed"] is False
        assert out["failure_class"] == "grader_error"
        assert "inconsistent" in out["grader_detail"]

    def test_missing_grader_detail_is_explicit_grader_error(self):
        bad = trial("race", "race-0002", "B", "B", True, archived_detail=None)
        out = rg.regrade_trial(bad)
        assert out["passed"] is False
        assert out["failure_class"] == "grader_error"
        assert "missing" in out["grader_detail"]

    def test_unhandled_benchmark_is_explicit_grader_error(self):
        out = rg.regrade_trial(sample_archive()[24])
        assert out["passed"] is False
        assert out["failure_class"] == "grader_error"
        assert "unhandled benchmark" in out["grader_detail"]

    def test_grader_exception_is_explicit_grader_error(self, monkeypatch):
        def boom(answer, expected):
            raise ValueError("grader exploded")

        monkeypatch.setattr(rg, "grade_gsm8k", boom)
        out = rg.regrade_trial(sample_archive()[1])
        assert out["passed"] is False
        assert out["failure_class"] == "grader_error"
        assert "grade_gsm8k" in out["grader_detail"]
        assert "ValueError: grader exploded" in out["grader_detail"]

    def test_grader_exception_on_empty_answer_keeps_empty_response(
        self, monkeypatch
    ):
        def boom(answer, expected):
            raise ValueError("grader exploded")

        monkeypatch.setattr(rg, "grade_gsm8k", boom)
        empty = trial("gsm8k", "gsm8k-0009", "", "42", False, output_tokens=0,
                      archived_detail="expected=42, got=")
        out = rg.regrade_trial(empty)
        assert out["passed"] is False
        assert out["failure_class"] == "empty_response"  # runner-level primary
        assert "grader_error" in out["grader_detail"]


class TestOutcomePreservation:
    def test_empty_zero_token_answer_is_empty_response(self):
        out = rg.regrade_trial(sample_archive()[3])
        assert out["passed"] is False
        assert out["failure_class"] == "empty_response"
        assert out["cap_exhausted"] is False
        assert out["output_token_cap"] == 2048
        assert "never graded into a pass" in out["grader_detail"]

    def test_empty_cap_exhausted_answer_is_empty_response_not_truncated(self):
        out = rg.regrade_trial(sample_archive()[4])
        assert out["passed"] is False
        assert out["failure_class"] == "empty_response"
        assert out["cap_exhausted"] is True  # cap flag still recorded
        assert "outcome_provenance" not in out

    def test_empty_answer_with_grader_problem_keeps_empty_response(self):
        out = rg.regrade_trial(sample_archive()[23])
        assert out["passed"] is False
        assert out["failure_class"] == "empty_response"
        assert "empty_response" in out["grader_detail"]
        assert "grader_error" in out["grader_detail"]
        assert out["archived_grader_detail"] is None

    def test_nonempty_cap_exhausted_fail_is_truncated(self):
        out = rg.regrade_trial(sample_archive()[5])
        assert out["passed"] is False
        assert out["failure_class"] == "truncated"
        assert out["cap_exhausted"] is True
        provenance = out["outcome_provenance"]
        assert "cap-derived" in provenance
        assert "finish_reason" in provenance
        assert "none is fabricated" in provenance
        assert "2048" in provenance

    def test_nonempty_cap_exhausted_pass_keeps_pass_with_cap_flag(self):
        out = rg.regrade_trial(sample_archive()[7])
        assert out["passed"] is True
        assert out["failure_class"] == "none"
        assert out["cap_exhausted"] is True
        assert "outcome_provenance" not in out

    def test_no_fabricated_finish_reason_or_truncated_flag(self):
        for t in sample_archive():
            out = rg.regrade_trial(t)
            assert "finish_reason" not in out
            assert "truncated" not in out
            assert out["cap_exhausted"] == (
                int(t.get("output_tokens") or 0) >= rg.OUTPUT_TOKEN_CAP
            )

    def test_missing_output_tokens_treated_as_zero(self):
        t = trial("gsm8k", "gsm8k-0010", "#### 42", "42", True, output_tokens=50)
        del t["output_tokens"]
        out = rg.regrade_trial(t)
        assert out["cap_exhausted"] is False
        assert out["passed"] is True


class TestPreservation:
    def test_original_verdicts_and_raw_answer_preserved(self):
        for t in sample_archive():
            out = rg.regrade_trial(t)
            assert out["archived_passed"] == t["passed"]
            assert out["archived_failure_class"] == t["failure_class"]
            assert out["archived_grader_detail"] == t["grader_detail"]
            assert out["final_answer"] == t["final_answer"]
            assert out["benchmark"] == t["benchmark"]
            assert out["task_id"] == t["task_id"]
            assert out["output_tokens"] == t["output_tokens"]

    def test_input_trial_not_mutated(self):
        for t in sample_archive():
            snapshot = dict(t)
            rg.regrade_trial(t)
            assert t == snapshot

    def test_verdict_flip_pass_to_fail(self):
        out = rg.regrade_trial(sample_archive()[6])
        assert out["archived_passed"] is True
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"


class TestPayload:
    def _payload(self):
        with open(ROOT / "benchmarks" / "run_public_bench.py", "rb") as f:
            grader_sha = rg.sha256_bytes(f.read())
        return rg.build_payload(
            sample_archive(),
            source_sha256="a" * 64,
            grader_sha256=grader_sha,
        ), grader_sha

    def test_manifest_records_versions_and_hashes(self):
        payload, grader_sha = self._payload()
        manifest = payload["manifest"]
        assert manifest["schema"] == rg.SCHEMA
        assert manifest["spec_version"] == rg.SPEC_VERSION
        assert manifest["regrader_version"] == rg.REGRADER_VERSION
        assert manifest["grader_version"] == rg.GRADER_VERSION
        assert manifest["grader"]["sha256"] == grader_sha
        assert manifest["grader"]["source"] == "benchmarks/run_public_bench.py"
        assert manifest["source_archive_sha256"] == "a" * 64
        assert manifest["grader"]["functions"] == rg.GRADER_FUNCTIONS
        assert manifest["output_token_cap"] == 2048
        assert "finish_reason" in manifest["finish_reason_policy"]

    def test_trials_in_input_order(self):
        payload, _ = self._payload()
        assert [t["task_id"] for t in payload["trials"]] == [
            t["task_id"] for t in sample_archive()
        ]

    def test_per_benchmark_summaries(self):
        payload, _ = self._payload()
        benchmarks = payload["manifest"]["benchmarks"]
        assert set(benchmarks) == {
            t["benchmark"] for t in sample_archive()
        }
        gsm8k = benchmarks["gsm8k"]
        assert gsm8k["trials"] == 8
        assert gsm8k["passed"] == 1  # only 0001 (numeric correction) passes
        assert gsm8k["failure_classes"]["grader_error"] == 1
        assert gsm8k["failure_classes"]["empty_response"] == 3
        assert gsm8k["failure_classes"]["truncated"] == 1
        # cap breakdown for gsm8k: 0005 empty, 0006 truncated (2048 each)
        assert gsm8k["cap_exhausted"] == {
            "trials": 2, "passed": 0, "truncated": 1, "empty_response": 1,
        }
        bbh = benchmarks["bbh"]
        assert bbh["cap_exhausted"] == {
            "trials": 1, "passed": 1, "truncated": 0, "empty_response": 0,
        }
        assert benchmarks["arc"]["passed"] == 2
        assert benchmarks["bbh_track"]["passed"] == 1
        assert benchmarks["bbh_arith"]["passed"] == 1
        assert benchmarks["lsat"]["passed"] == 1
        assert benchmarks["race"]["passed"] == 1
        assert benchmarks["mmlu_math"]["passed"] == 1
        assert benchmarks["mmlu_logic"]["passed"] == 0
        assert benchmarks["mmlu_acct"]["passed"] == 1
        assert benchmarks["mmlu_pro"]["failure_classes"]["grader_error"] == 1

    def test_verdict_changes_summary(self):
        payload, _ = self._payload()
        changes = payload["manifest"]["summary"]["verdict_changes"]
        # fail->pass: gsm8k-0001 (numeric), arc-0002 (positional key),
        # bbh-0002 (parens), bbh-arith-0001 (formatted number) = 4.
        assert changes["fail_to_pass"] == 4
        # pass->fail: gsm8k-0007 (archived false pass) = 1.
        assert changes["pass_to_fail"] == 1
        # grader errors and empty responses are not verdict changes.

    def test_overall_summary_counts(self):
        payload, _ = self._payload()
        summary = payload["manifest"]["summary"]
        assert summary["trials"] == len(sample_archive())
        classes = summary["failure_classes"]
        assert classes["none"] == sum(
            1 for t in payload["trials"] if t["failure_class"] == "none"
        )
        assert classes["empty_response"] == 3
        # malformed expected, inconsistent expected, unhandled benchmark
        assert classes["grader_error"] == 3
        assert classes["truncated"] == 1
        assert summary["passed"] == classes["none"]

    def test_deterministic_rendering(self):
        payload, _ = self._payload()
        text = rg.render_payload(payload)
        assert text == rg.render_payload(payload)
        assert text.endswith("\n")
        assert "timestamp" not in text
        assert str(ROOT) not in text  # no host-absolute paths


class TestWriteExclusive:
    def test_creates_parents_and_file(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "derived.json"
        rg.write_exclusive(out, "{}\n")
        assert out.read_text() == "{}\n"

    def test_refuses_existing_file(self, tmp_path):
        out = tmp_path / "derived.json"
        out.write_text("sentinel")
        with pytest.raises(rg.RegradeError, match="refusing to overwrite"):
            rg.write_exclusive(out, "{}\n")
        assert out.read_text() == "sentinel"  # existing bytes untouched


class TestCliSafety:
    """The end-to-end CLI contract: explicit paths, immutable input."""

    def _archive(self, tmp_path) -> Path:
        path = tmp_path / "archive.json"
        path.write_text(json.dumps(sample_archive(), indent=2) + "\n")
        return path

    def test_legacy_invocation_fails_helpfully(self):
        result = run_cli()
        assert result.returncode != 0
        assert "--input" in result.stderr
        assert "--output" in result.stderr

    def test_missing_explicit_paths_is_a_usage_error(self):
        result = run_cli("--input", "x.json")  # --output omitted
        assert result.returncode != 0
        assert "--output" in result.stderr

    def test_input_archive_bytes_unchanged(self, tmp_path):
        archive = self._archive(tmp_path)
        before = archive.read_bytes()
        out = tmp_path / "sub" / "derived.json"
        result = run_cli("--input", str(archive), "--output", str(out))
        assert result.returncode == 0, result.stderr
        assert archive.read_bytes() == before
        assert out.exists()
        payload = json.loads(out.read_text())
        # raw final answers carried through unchanged
        originals = {t["task_id"]: t["final_answer"] for t in sample_archive()}
        derived = {t["task_id"]: t["final_answer"] for t in payload["trials"]}
        assert derived == originals
        # verdicts preserved alongside the derived ones
        by_id = {t["task_id"]: t for t in payload["trials"]}
        assert by_id["gsm8k-0001"]["archived_passed"] is False
        assert by_id["gsm8k-0001"]["passed"] is True
        assert by_id["arc-0002"]["failure_class"] == "none"

    def test_refuses_existing_output(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        out.write_text("do not clobber\n")
        result = run_cli("--input", str(archive), "--output", str(out))
        assert result.returncode != 0
        assert "refusing to overwrite" in result.stderr
        assert out.read_text() == "do not clobber\n"

    def test_missing_input_is_an_error(self, tmp_path):
        result = run_cli(
            "--input", str(tmp_path / "nope.json"),
            "--output", str(tmp_path / "out.json"),
        )
        assert result.returncode != 0
        assert "input archive not found" in result.stderr
        assert not (tmp_path / "out.json").exists()

    def test_output_equal_to_input_refused(self, tmp_path):
        archive = self._archive(tmp_path)
        result = run_cli("--input", str(archive), "--output", str(archive))
        assert result.returncode != 0
        assert "never modified" in result.stderr

    def test_deterministic_output_bytes(self, tmp_path):
        archive = self._archive(tmp_path)
        out1 = tmp_path / "run1.json"
        out2 = tmp_path / "run2.json"
        assert run_cli("--input", str(archive), "--output", str(out1)).returncode == 0
        assert run_cli("--input", str(archive), "--output", str(out2)).returncode == 0
        assert out1.read_bytes() == out2.read_bytes()

    def test_manifest_hashes_match_real_files(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        assert run_cli("--input", str(archive), "--output", str(out)).returncode == 0
        manifest = json.loads(out.read_text())["manifest"]
        assert manifest["source_archive_sha256"] == sha256_of(archive)
        assert manifest["grader"]["sha256"] == sha256_of(
            ROOT / "benchmarks" / "run_public_bench.py"
        )

    def test_run_metadata_sidecar_separate_from_payload(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        meta = tmp_path / "meta.json"
        result = run_cli(
            "--input", str(archive), "--output", str(out), "--run-metadata", str(meta)
        )
        assert result.returncode == 0, result.stderr
        payload_text = out.read_text()
        assert "generated_at_utc" not in payload_text  # deterministic payload
        assert str(archive) not in payload_text
        run_meta = json.loads(meta.read_text())
        assert "generated_at_utc" in run_meta
        assert run_meta["input"].endswith("archive.json")
        assert run_meta["input_sha256"] == sha256_of(archive)

    def test_no_fabricated_finish_reason_in_cli_output(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        assert run_cli("--input", str(archive), "--output", str(out)).returncode == 0
        payload = json.loads(out.read_text())
        for t in payload["trials"]:
            assert "finish_reason" not in t
            assert "truncated" not in t
            assert t["output_token_cap"] == 2048


@pytest.mark.skipif(
    os.environ.get("TAHOE_STAGE1_SMOKE") != "1",
    reason="real-archive smoke test; set TAHOE_STAGE1_SMOKE=1 to run",
)
class TestRealArchiveSmoke:
    """Re-grade the real 2026-09-13 stage1-full archives (read-only).

    The archives are only read (sha-256 verified against the published
    values in benchmarks/results/derived/2026-11-18-stage1-gsm8k-v4/README.md);
    nothing is written. Derived success counts are pinned per arm
    (GSM8K extractor v6):
    GLM classic/tahoe 15125/15203; gpt-oss classic/tahoe 14865/14835
    (93.42% / 93.23% of 15,912 trials per arm — computed exactly by the
    pipeline, not from the rounded percentages).
    """

    GLM_INPUT_SHA256 = (
        "43ca713f08acc2c72bfed10d74eab4943ea4d128933dc67da9ca0344347deacf"
    )
    OSS_INPUT_SHA256 = (
        "771be2ee59da30df186df2c73d64931fbf32c7d772f6a5afe313bbb58160eff9"
    )

    @staticmethod
    def _successes_by_arm(archive_path):
        archive = json.loads(archive_path.read_text())
        trials, benchmarks, summary = rg.regrade_archive(
            archive, source_name=str(archive_path)
        )
        successes = {"classic": 0, "tahoe": 0}
        totals = {"classic": 0, "tahoe": 0}
        for t in trials:
            arm = t.get("arm")
            if arm in successes:
                totals[arm] += 1
                if t["passed"]:
                    successes[arm] += 1
        for t in trials:
            assert "finish_reason" not in t
            assert "truncated" not in t
        return successes, totals, benchmarks, summary

    def test_glm_derived_success_counts(self):
        assert sha256_of(GLM_ARCHIVE) == self.GLM_INPUT_SHA256
        successes, totals, benchmarks, summary = self._successes_by_arm(
            GLM_ARCHIVE
        )
        assert totals == {"classic": 15762, "tahoe": 15762}
        assert successes == {"classic": 15125, "tahoe": 15203}
        # gsm8k subset must match the published GSM8K-only derived artifact.
        gsm8k = benchmarks["gsm8k"]
        assert gsm8k["passed"] == 7591
        assert gsm8k["failure_classes"]["grader_error"] == 12
        assert gsm8k["verdict_changes"] == {
            "fail_to_pass": 1716, "pass_to_fail": 13,
        }
        # outcome preservation on the real archive
        classes = summary["failure_classes"]
        assert classes["empty_response"] == 182
        assert classes["truncated"] == 3
        assert classes["grader_error"] == 12

    def test_oss_derived_success_counts(self):
        assert sha256_of(OSS_ARCHIVE) == self.OSS_INPUT_SHA256
        successes, totals, benchmarks, summary = self._successes_by_arm(
            OSS_ARCHIVE
        )
        assert totals == {"classic": 15912, "tahoe": 15912}
        # exact counts behind the 93.42 / 93.23 percent figures
        assert successes == {"classic": 14865, "tahoe": 14835}
        assert round(14865 / 15912 * 100, 2) == 93.42
        assert round(14835 / 15912 * 100, 2) == 93.23
        classes = summary["failure_classes"]
        assert classes["empty_response"] == 42
        assert classes["grader_error"] == 12
        assert "truncated" not in classes  # every oss cap trial was empty
