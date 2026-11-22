"""Focused tests for public benchmark grading in benchmarks/run_public_bench.py.

Regressions are pinned from archived evaluation failures
(benchmarks/results/):

- ARC: numeric answerKeys ('1'-'4') versus the prompt's requested 'A'-'D'
  (archived: expected=3, got=C, wrongly marked False for every arm).
- Multiple-choice: an explicit final-answer marker ('Answer: D') must win
  over earlier discussed options (archived: mmlu-math-0005 'expected=D,
  got=A' although the answer ended '**Answer: D**').
- GSM8K: numeric normalization ('42' gold vs '42.00' answer, thousands
  separators, thin spaces) and robust final-answer extraction ('#### 42.50'
  must not be truncated to '42'; '\\boxed{43{,}200}' must not split).

All graders stay arm-agnostic: the same code path grades every arm.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "src"))

import benchmarks.run_public_bench as bench  # noqa: E402


class TestArcNumericLabels:
    """ARC expected=3, model answered 'C' (the third choice): must pass."""

    def test_regression_expected_three_got_c(self):
        passed, detail = bench.grade_arc("C", "3")
        assert passed is True
        assert "got=C" in detail

    def test_numeric_key_with_labels(self):
        passed, _ = bench.grade_arc("C", "3", labels=["1", "2", "3", "4"])
        assert passed is True

    def test_numeric_key_model_echoes_label(self):
        # The model echoes the raw numeric label shown in the choices.
        passed, _ = bench.grade_arc("3", "3", labels=["1", "2", "3", "4"])
        assert passed is True

    def test_wrong_letter_for_numeric_key_fails(self):
        passed, _ = bench.grade_arc("D", "3", labels=["1", "2", "3", "4"])
        assert passed is False

    def test_letter_key_unchanged(self):
        passed, _ = bench.grade_arc("D", "D", labels=["A", "B", "C", "D"])
        assert passed is True
        passed, _ = bench.grade_arc("A", "D", labels=["A", "B", "C", "D"])
        assert passed is False

    def test_grade_task_passes_arc_labels(self):
        task = {
            "grader": "arc",
            "expected": "3",
            "labels": ["1", "2", "3", "4"],
        }
        passed, detail = bench.grade_task(task, "C")
        assert passed is True
        assert "got=C" in detail

    def test_grade_task_gpqa_letter_unchanged(self):
        task = {"grader": "gpqa", "expected": "B"}
        passed, _ = bench.grade_task(task, "B")
        assert passed is True
        passed, _ = bench.grade_task(task, "C")
        assert passed is False


class TestFinalAnswerMarkerPriority:
    """Explicit final-answer markers beat earlier discussed options."""

    def test_regression_answer_d_after_earlier_a(self):
        # Archived mmlu-math-0005: the reasoning works through options
        # (mentioning A first) but ends with '**Answer: D**'.
        answer = (
            "(A) would fail immediately. Testing e = 6 shows a multiplicative "
            "identity, so statement (D) is FALSE.\n\n**Answer: D**"
        )
        passed, detail = bench.grade_mmlu(answer, "3")  # index 3 == D
        assert passed is True
        assert "got=D" in detail

    def test_regression_the_answer_is_b_after_discussion(self):
        # Archived lsat-0063: option discussion ends '**The answer is B.**'.
        answer = (
            "(A) is too strong. (C) misreads the scope. (D) and (E) are "
            "out of scope.\n\n**The answer is B.**"
        )
        passed, detail = bench.grade_lsat(answer, "B")
        assert passed is True
        assert "got=B" in detail

    def test_regression_answer_e_after_earlier_a_lsat(self):
        # Archived lsat-0194: 'The answer is **E**.' after discussing A-D.
        answer = (
            "1. Pluto formed in orbit around Neptune\n"
            "2. A true planet must have formed around the sun (assumption E)\n\n"
            "The answer is **E**."
        )
        passed, detail = bench.grade_lsat(answer, "E")
        assert passed is True
        assert "got=E" in detail

    def test_marker_is_option_discussion_not_final_answer(self):
        # Archived lsat-0198: the final answer is stated first; 'Answer (E)
        # makes the common mistake...' is option discussion, not a marker.
        # A separator (is/:/-) is required, so this must NOT be taken as E.
        answer = (
            "**D**\n\nStaying within budget requires the sorting requirement. "
            "Answer (E) makes the common mistake of reversing a condition."
        )
        passed, detail = bench.grade_lsat(answer, "D")
        assert passed is True
        assert "got=D" in detail

    def test_last_marker_wins_over_earlier_marker(self):
        answer = "The answer is A at first glance, but reconsidering: the answer is B."
        passed, _ = bench.grade_arc(answer, "B")
        assert passed is True

    def test_bbh_marker_beats_parenthesized_option(self):
        # Archived bbh-style: options (A)-(E) are discussed, then declared.
        answer = (
            "(A) fails. (B) fails. Working through: Eli 1st, Mel 2nd, Ana 3rd. "
            "Mya is last, so the answer is (E)."
        )
        passed, detail = bench.grade_bbh(answer, "(E)")
        assert passed is True
        assert "got=E" in detail

    def test_bbh_paren_behavior_preserved_without_marker(self):
        # Legacy: '(X)' pattern wins when there is no explicit marker.
        answer = "The rightmost bird is the crow → **(G)**"
        passed, _ = bench.grade_bbh(answer, "(G)")
        assert passed is True

    def test_bare_letter_still_works(self):
        passed, _ = bench.grade_arc("D", "D")
        assert passed is True

    def test_last_line_bare_letter(self):
        passed, _ = bench.grade_arc("Reasoning about A and B at length.\n\nC", "C")
        assert passed is True

    def test_fallback_first_letter_unchanged(self):
        # No marker anywhere: legacy first-standalone-letter behavior.
        passed, _ = bench.grade_race("B because the passage says so.", "B")
        assert passed is True


class TestGsm8kNumericNormalization:
    """42 vs 42.00, commas/spaces, and robust final-answer extraction."""

    def test_regression_42_vs_42_00(self):
        # Archived gsm8k-0689: gold '#### 7', model answered '$7.00'.
        passed, detail = bench.grade_gsm8k(
            "So she pays $7.00 in total.", "He pays $6 and $1 more.\n#### 7"
        )
        assert passed is True
        assert "got=7.00" in detail

    def test_gold_thousands_separator(self):
        passed, _ = bench.grade_gsm8k("#### 1,430", "reasoning\n#### 1430")
        assert passed is True

    def test_model_thousands_separator(self):
        passed, _ = bench.grade_gsm8k(
            "**They earn 1,430 dollars.**", "#### 1430"
        )
        assert passed is True

    def test_hash_marker_decimal_not_truncated(self):
        # '#### 42.50' must not be read as '42' (which would pass vs 42).
        passed, _ = bench.grade_gsm8k("#### 42.50", "#### 42")
        assert passed is False

    def test_hash_marker_with_currency(self):
        passed, _ = bench.grade_gsm8k("#### $42", "#### 42")
        assert passed is True

    def test_markdown_heading_is_not_a_hash_marker(self):
        # '####' markdown headings must not be mistaken for the GSM8K marker.
        passed, _ = bench.grade_gsm8k(
            "#### Solution\nThe answer is 12.", "#### 12"
        )
        assert passed is True

    def test_boxed_latex_thousands_separator(self):
        # Archived gsm8k-1026: '\boxed{43{,}200}' split into '200' before.
        answer = "$$1{,}440 \\times 30 = \\boxed{43{,}200 \\text{ pounds}}$$"
        passed, detail = bench.grade_gsm8k(answer, "#### 43200")
        assert passed is True
        assert "got=43200" in detail

    def test_boxed_thin_latex_space_separator(self):
        passed, _ = bench.grade_gsm8k(r"total: \boxed{2\,000}", "#### 2000")
        assert passed is True

    def test_wrong_answer_fails(self):
        passed, _ = bench.grade_gsm8k("The answer is 41.", "#### 42")
        assert passed is False

    def test_extract_model_number_hash_marker(self):
        assert bench.extract_model_number("work\n#### 42") == "42"
        assert bench.extract_model_number("work\n#### 42.50") == "42.50"

    def test_extract_gsm8k_gold_separator_aware(self):
        assert bench.extract_gsm8k_gold("steps\n#### 42") == "42"
        assert bench.extract_gsm8k_gold("steps\n#### 42,000") == "42000"
        assert bench.extract_gsm8k_gold("steps\n#### 42.00") == "42.00"
        assert bench.extract_gsm8k_gold("#### Heading only") == ""


class TestGsm8kStatedAnswerPriority:
    """Final-audit MEDIUM1: an explicit Answer marker and a same-quantity
    restatement must not lose to the broad last-bold/last-number heuristics.

    Archived regressions: 'expected=160, got=40' for
    '**Answer: 160 minutes (2 hours 40 minutes).**' and 'expected=216,
    got=36' for '216 seconds (which is 3 minutes 36 seconds)' — the stated
    answers were correct but the trailing restatement numbers won.
    """

    def test_audit_regression_answer_marker_with_restatement(self):
        assert (
            bench.extract_model_number(
                "**Answer: 160 minutes (2 hours 40 minutes).**"
            )
            == "160"
        )

    def test_audit_regression_bare_seconds_with_restatement(self):
        assert (
            bench.extract_model_number(
                "216 seconds (which is 3 minutes 36 seconds)."
            )
            == "216"
        )

    def test_audit_regressions_via_grade_gsm8k(self):
        passed, detail = bench.grade_gsm8k(
            "**Answer: 160 minutes (2 hours 40 minutes).**", "#### 160"
        )
        assert passed is True
        assert "got=160" in detail
        passed, detail = bench.grade_gsm8k(
            "216 seconds (which is 3 minutes 36 seconds).", "#### 216"
        )
        assert passed is True
        assert "got=216" in detail

    def test_marker_beats_trailing_context(self):
        # Archived: 'Answer: 448 mL of medicine in 8 doses.' graded as 8.
        assert (
            bench.extract_model_number(
                "**Answer: 448 mL of medicine in 8 doses.**"
            )
            == "448"
        )
        # Archived: 'Answer: 2,000 gallons ... after 6 days.' graded as 6.
        assert (
            bench.extract_model_number(
                "**Answer: 2,000 gallons will be left in the tank after 6 days.**"
            )
            == "2000"
        )

    def test_last_marker_wins(self):
        assert (
            bench.extract_model_number(
                "Answer: 5 first, but reconsidering, the answer: 6."
            )
            == "6"
        )

    def test_bare_restatement_variants(self):
        assert (
            bench.extract_model_number("227 minutes (which is 3 hours 47 minutes).")
            == "227"
        )
        assert bench.extract_model_number("225 minutes (3 hours 45 minutes).") == "225"
        # Thin-space thousands inside the restatement must not leak in.
        assert (
            bench.extract_model_number("34 hours (which is 2\u202f040 minutes).")
            == "34"
        )
        # A breakdown restatement: the leading number is the stated answer.
        assert bench.extract_model_number("4 (3 onions and 1 potato).") == "4"

    def test_bold_restatement_resolved_to_first_number(self):
        assert (
            bench.extract_model_number(
                "**It will take 225 minutes, or 3 hours and 45 minutes, "
                "for everyone to try the escape room.**"
            )
            == "225"
        )
        assert (
            bench.extract_model_number(
                "**It will take 225 minutes \u2014 or 3 hours and 45 minutes "
                "\u2014 for everyone to try the escape room.**"
            )
            == "225"
        )

    def test_marker_preserves_numeric_formats(self):
        assert bench.extract_model_number("Answer: $42") == "42"
        assert bench.extract_model_number("Answer: 1,430 dollars.") == "1430"
        assert bench.extract_model_number("Answer: 42.50") == "42.50"
        assert bench.extract_model_number("Answer: -12 dollars.") == "-12"
        # '#### 42.50' still must not be truncated by an earlier marker.
        assert bench.extract_model_number("Answer: 41\n#### 42.50") == "42.50"

    def test_restatement_guard_preserves_last_answer_semantics(self):
        # No connector: the last number is still the answer.
        assert bench.extract_model_number("The slot is 4.") == "4"
        assert bench.extract_model_number("**Count: 3 routes**") == "3"
        # A parenthetical that is NOT the end of the text does not fire.
        assert (
            bench.extract_model_number(
                "He has 3 apples (2 red, 1 green). He ends with 6."
            )
            == "6"
        )
        # 'answer is' keeps last-occurrence semantics.
        assert (
            bench.extract_model_number(
                "The answer is 5 at first glance, but the answer is 6."
            )
            == "6"
        )

    def test_false_marker_is_not_a_marker(self):
        # Option discussion ('Answer (E) makes...') has no colon.
        assert (
            bench.extract_model_number(
                "D is right. Answer (E) makes a mistake with 3 items."
            )
            == "3"
        )
        # A number in a later sentence is not the marker's answer.
        assert (
            bench.extract_model_number(
                "Answer: see the table below.\nThe total is 12."
            )
            == "12"
        )

    def test_number_list_paren_is_not_a_restatement(self):
        # '(1, 3, 6)' is a bare number list, not a worded restatement.
        assert (
            bench.extract_model_number(
                "**The 3 routes (1, 3, 6) have total cost 16**"
            )
            == "16"
        )
        # A bare 'N or M' has no unit word, so the last number still wins.
        assert bench.extract_model_number("3 or 4") == "4"


class TestClockFormAnswers:
    """OSS-audit LOW: a trailing H:MM am/pm clock time states its hour.

    Archived regressions (gsm8k, 'expected=2, got=00'): final answers
    '2:00\u202fpm' and '**2:00 pm**' state the hour 2, but the broad
    last-number heuristic returned the minutes '00'. The rule is
    end-anchored on the am/pm marker, so every non-clock colon form
    keeps its old extraction.
    """

    def test_audit_regression_clock_forms_state_the_hour(self):
        assert bench.extract_model_number("2:00 pm") == "2"
        assert bench.extract_model_number("**2:00 pm**") == "2"
        assert bench.extract_model_number("2:00\u202fpm") == "2"
        assert bench.extract_model_number("12:30pm") == "12"

    def test_audit_regressions_via_grade_gsm8k(self):
        passed, detail = bench.grade_gsm8k("2:00\u202fpm", "#### 2")
        assert passed is True
        assert "got=2" in detail
        passed, detail = bench.grade_gsm8k(
            "Latest start time: **2:00 PM**.", "#### 2"
        )
        assert passed is True
        assert "got=2" in detail

    def test_marker_case_stays_the_hour(self):
        # The 'Answer:' marker already grabs the hour; it must not regress
        # to the minutes via any later heuristic.
        assert bench.extract_model_number("Answer: 2:00 pm") == "2"
        assert bench.extract_model_number("**Answer: 2:00 pm**") == "2"

    def test_marker_and_case_variants(self):
        assert bench.extract_model_number("2:00 PM") == "2"
        assert bench.extract_model_number("2:00 p.m.") == "2"
        assert bench.extract_model_number("2:00 P.M.") == "2"
        assert bench.extract_model_number("2:00am") == "2"
        assert bench.extract_model_number("The trains meet at 2:00 pm.") == "2"
        assert bench.extract_model_number("Start 10:30 am, end 12:30 pm.") == "12"

    def test_no_am_pm_marker_is_not_a_clock_answer(self):
        # A plain time carries no am/pm marker: last number stands.
        assert bench.extract_model_number("2:00") == "00"
        assert bench.extract_model_number("at 2:00 in the afternoon") == "00"

    def test_ratio_and_decimal_colons_are_not_clocks(self):
        assert bench.extract_model_number("The ratio is 3:1.") == "1"
        assert bench.extract_model_number("2.50") == "2.50"
        assert bench.extract_model_number("Answer: 2.50") == "2.50"
        assert bench.extract_model_number("Part 2: 00 items") == "00"

    def test_clock_with_later_numeric_context_is_untouched(self):
        # The clock is not the final number; the last number still wins.
        assert (
            bench.extract_model_number(
                "She arrives at 2:00 pm and walks 5 miles."
            )
            == "5"
        )

    def test_audit_regression_boxed_latex_clock(self):
        # Archived GLM classic gsm8k-1001 trial: the boxed fallback kept
        # extracting the minutes ('00') from the LaTeX clock form.
        assert bench.extract_model_number(r"\boxed{2\text{:}00 \text{ pm}}") == "2"
        assert (
            bench.extract_model_number(
                "$$5\\!:\\!00 \\text{ pm} - 3 \\text{ hours} "
                "= \\boxed{2\\text{:}00 \\text{ pm}}$$\n\n## Answer\n\n"
                "The latest time Jordan can start making the cake is "
                "**2:00 pm** at the latest."
            )
            == "2"
        )

    def test_audit_regression_boxed_clock_via_grade_gsm8k(self):
        passed, detail = bench.grade_gsm8k(
            r"The answer is $\boxed{2\text{:}00 \text{ pm}}$.", "#### 2"
        )
        assert passed is True
        assert "got=2" in detail

    def test_boxed_non_clock_forms_are_untouched(self):
        # The LaTeX unwrap serves the clock check only: every other
        # boxed form keeps the generic last-number extraction.
        assert bench.extract_model_number(r"\boxed{42.50}") == "42.50"
        assert bench.extract_model_number(r"\boxed{2{,}000 \text{ dollars}}") == "2000"
        assert bench.extract_model_number(r"\boxed{452 \text{ minutes}}") == "452"
        assert bench.extract_model_number(r"\boxed{43{,}200}") == "43200"
        # No am/pm marker: a plain boxed time or ratio is not a clock.
        assert bench.extract_model_number(r"\boxed{2\text{:}00}") == "00"
        assert bench.extract_model_number(r"\boxed{3\text{:}1}") == "1"

    def test_clock_rule_does_not_disturb_prior_guards(self):
        # The v5 restatement/priority guards all keep their verdicts.
        assert (
            bench.extract_model_number("216 seconds (which is 3 minutes 36 seconds).")
            == "216"
        )
        assert (
            bench.extract_model_number("**Answer: 160 minutes (2 hours 40 minutes).**")
            == "160"
        )
        assert bench.extract_model_number("3 or 4") == "4"
        assert bench.extract_model_number("**Count: 3 routes**") == "3"
        assert bench.extract_model_number("Answer: 41\n#### 42.50") == "42.50"


class TestAimeAndBbhArithNumericEquality:
    def test_aime_decimal_formatting(self):
        passed, _ = bench.grade_aime("The answer is 25.", "25")
        assert passed is True
        passed, _ = bench.grade_aime("The answer is 25.00.", "25")
        assert passed is True

    def test_bbh_arith_thousands_separator(self):
        passed, _ = bench.grade_bbh_arith("= 1,080", "1080")
        assert passed is True

    def test_bbh_arith_wrong_value_fails(self):
        passed, _ = bench.grade_bbh_arith("= 1,081", "1080")
        assert passed is False


class TestExtractChoiceLetter:
    def test_bare_letter(self):
        assert bench.extract_choice_letter("**D**") == "D"

    def test_paren_letter(self):
        assert bench.extract_choice_letter("(B)") == "B"

    def test_marker_last_occurrence(self):
        assert (
            bench.extract_choice_letter("the answer is A ... the answer is B")
            == "B"
        )

    def test_no_marker_falls_back_to_first_letter(self):
        assert (
            bench.extract_choice_letter("C because A and B are wrong") == "C"
        )

    def test_option_discussion_is_not_a_marker(self):
        # 'Answer (E) makes...' is option discussion: the earlier stated
        # standalone letter wins instead of being overridden by E.
        assert (
            bench.extract_choice_letter(
                "D is right. Answer (E) makes a mistake", "ABCDE"
            )
            == "D"
        )

    def test_last_line_bare(self):
        assert bench.extract_choice_letter("reasoning\n\nD.") == "D"
