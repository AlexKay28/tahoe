"""Tests for benchmarks/graders.py: pass/fail cases per grader type, the factory,
and composite behavior with mixed pass/fail."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.graders import (
    CompositeGrader,
    ContainsGrader,
    ExactMatchGrader,
    JSONFieldGrader,
    NumericGrader,
    TestPassGrader,
    make_grader,
)


class TestExactMatchGrader:
    def test_pass(self):
        grader = ExactMatchGrader()
        passed, detail = grader("Route 3, total cost: 16", {"answer": "Route 3, total cost: 16"})
        assert passed is True
        assert "exact match" in detail

    def test_fail(self):
        grader = ExactMatchGrader()
        passed, detail = grader("Route 3, cost 16", {"answer": "Route 3, total cost: 16"})
        assert passed is False
        assert "Route 3, total cost: 16" in detail

    def test_missing_answer_key_fails(self):
        grader = ExactMatchGrader()
        passed, _ = grader("anything", {})
        assert passed is False

    def test_type_mismatch_fails(self):
        grader = ExactMatchGrader()
        passed, _ = grader(3, {"answer": "3"})
        assert passed is False


class TestContainsGrader:
    def test_pass(self):
        grader = ContainsGrader()
        passed, detail = grader("def add(a, b): return a + b", {"substring": "return a + b"})
        assert passed is True

    def test_fail(self):
        grader = ContainsGrader()
        passed, detail = grader("def add(a, b): return a - b", {"substring": "return a + b"})
        assert passed is False
        assert "return a + b" in detail

    def test_missing_substring_key_fails(self):
        grader = ContainsGrader()
        passed, _ = grader("some text", {})
        assert passed is False

    def test_non_string_result_is_coerced(self):
        grader = ContainsGrader()
        passed, _ = grader(12345, {"substring": "234"})
        assert passed is True


class TestJSONFieldGrader:
    def test_pass(self):
        grader = JSONFieldGrader()
        passed, _ = grader('{"subtask_count": 5}', {"field": "subtask_count", "value": 5})
        assert passed is True

    def test_wrong_value_fails(self):
        grader = JSONFieldGrader()
        passed, detail = grader('{"subtask_count": 4}', {"field": "subtask_count", "value": 5})
        assert passed is False
        assert "subtask_count" in detail

    def test_missing_field_fails(self):
        grader = JSONFieldGrader()
        passed, _ = grader('{"other": 5}', {"field": "subtask_count", "value": 5})
        assert passed is False

    def test_invalid_json_fails(self):
        grader = JSONFieldGrader()
        passed, detail = grader("not json at all", {"field": "subtask_count", "value": 5})
        assert passed is False
        assert "JSON" in detail

    def test_non_object_json_fails(self):
        grader = JSONFieldGrader()
        passed, _ = grader("[1, 2, 3]", {"field": "subtask_count", "value": 5})
        assert passed is False

    def test_pre_parsed_dict_result_passes(self):
        grader = JSONFieldGrader()
        passed, _ = grader({"subtask_count": 5}, {"field": "subtask_count", "value": 5})
        assert passed is True


class TestTestPassGrader:
    def test_pass(self):
        grader = TestPassGrader()
        passed, detail = grader("ignored result", {"test_cmd": "true"})
        assert passed is True
        assert "0" in detail

    def test_fail(self):
        grader = TestPassGrader()
        passed, detail = grader("ignored result", {"test_cmd": "exit 3"})
        assert passed is False
        assert "3" in detail

    def test_missing_test_cmd_fails(self):
        grader = TestPassGrader()
        passed, _ = grader("ignored result", {})
        assert passed is False

    def test_output_tail_included_on_failure(self):
        grader = TestPassGrader()
        passed, detail = grader("ignored result", {"test_cmd": "echo boom >&2; exit 1"})
        assert passed is False
        assert "boom" in detail


class TestCompositeGrader:
    def test_all_pass(self):
        grader = CompositeGrader([ContainsGrader(), ExactMatchGrader()])
        passed, detail = grader(
            "Route 3, total cost: 16",
            {"substring": "Route 3", "answer": "Route 3, total cost: 16"},
        )
        assert passed is True
        assert "FAIL" not in detail

    def test_mixed_pass_fail(self):
        grader = CompositeGrader([ContainsGrader(), ExactMatchGrader()])
        passed, detail = grader("the answer is 3", {"substring": "3", "answer": "3"})
        assert passed is False
        assert "ContainsGrader: PASS" in detail
        assert "ExactMatchGrader: FAIL" in detail

    def test_all_fail(self):
        grader = CompositeGrader([ExactMatchGrader(), ContainsGrader()])
        passed, _ = grader("nope", {"answer": "yes", "substring": "yes"})
        assert passed is False

    def test_sub_graders_from_expected_state_strings(self):
        grader = CompositeGrader()
        passed, detail = grader(
            "y = x * c",
            {"graders": ["contains"], "substring": "y = x * c"},
        )
        assert passed is True
        assert "ContainsGrader: PASS" in detail

    def test_sub_grader_dict_spec_merges_params(self):
        grader = CompositeGrader()
        passed, _ = grader(
            '{"subtask_count": 5}',
            {
                "graders": [
                    {"type": "json_field", "params": {"field": "subtask_count", "value": 5}}
                ],
                "field": "ignored_outer",
                "value": None,
            },
        )
        assert passed is True

    def test_single_callable_in_constructor(self):
        grader = CompositeGrader(ContainsGrader())
        passed, _ = grader("has Resume inside", {"substring": "Resume"})
        assert passed is True

    def test_no_sub_graders_fails(self):
        grader = CompositeGrader()
        passed, detail = grader("x", {})
        assert passed is False
        assert "no sub-graders" in detail

    def test_invalid_spec_fails(self):
        grader = CompositeGrader([42])
        passed, _ = grader("x", {})
        assert passed is False

    def test_unknown_sub_grader_type_fails(self):
        grader = CompositeGrader(["bogus_type"])
        passed, detail = grader("x", {})
        assert passed is False
        assert "bogus_type" in detail


class TestMakeGrader:
    @pytest.mark.parametrize(
        "name, cls",
        [
            ("exact_match", ExactMatchGrader),
            ("contains", ContainsGrader),
            ("json_field", JSONFieldGrader),
            ("test_pass", TestPassGrader),
            ("composite", CompositeGrader),
            ("numeric", NumericGrader),
        ],
    )
    def test_factory_builds_each_type(self, name, cls):
        grader = make_grader(name)
        assert isinstance(grader, cls)
        assert callable(grader)

    def test_factory_unknown_type_raises(self):
        with pytest.raises(ValueError, match="bogus"):
            make_grader("bogus")


class TestNumericGrader:
    """Regressions pinned from archived failures plus the generic chain."""

    def setup_method(self):
        self.grader = NumericGrader()

    # -- regression: expected number must not be found 'anywhere' -----------

    def test_regression_eight_subtasks_wrongly_accepted_as_five(self):
        # Archived plan-01 failure: the model returned 8 subtasks, but the
        # list contains the digit '5' as a list index ('5. Run database
        # migrations'), so the old grader passed it against expected value 5.
        answer = (
            "**Ordered subtasks for \"Deploy a web app to production\":**\n\n"
            "1. Finalize code and merge the release branch into main\n"
            "2. Run the full test suite (unit, integration, security scans)\n"
            "3. Build the production artifact (bundle/compile the app)\n"
            "4. Deploy to a staging environment and validate behavior\n"
            "5. Run database migrations\n"
            "6. Deploy the artifact to the production environment\n"
            "7. Run post-deployment smoke tests and health checks\n"
            "8. Monitor errors/performance and confirm stability\n\n"
            "**Number of subtasks: 8**"
        )
        passed, detail = self.grader(answer, {"value": 5})
        assert passed is False
        assert "8" in detail

    def test_regression_truncated_answer_with_expected_digit_only_fails(self):
        # Archived routing-02 failure: truncated table answer contains '3'
        # only as a table cell, never as the reported count.
        answer = (
            "| Route | Distance | Cost/km | Total cost | Under 50? |\n"
            "| 1 | 12 | 3 | 36 | yes |\n"
            "| 3 | 8 | 2 | 16 | yes |"
        )
        passed, _ = self.grader(answer, {"value": 3})
        assert passed is False

    def test_correct_declared_subtask_count_passes(self):
        passed, detail = self.grader(
            "**Ordered subtasks**\n\n1. A\n2. B\n3. C\n4. D\n5. E\n\n**Number of subtasks: 5**",
            {"value": 5},
        )
        assert passed is True
        assert "5" in detail

    def test_bare_correct_number_passes(self):
        passed, _ = self.grader("Route 3, total cost 16 units.", {"value": 16})
        assert passed is True

    def test_expected_in_reasoning_but_wrong_final_answer_fails(self):
        passed, _ = self.grader(
            "12 * 3 = 36, 8 * 2 = 16, so route 3 with 16 units is cheapest."
            "\nHmm, but actually the total is 18.",
            {"value": 16},
        )
        assert passed is False

    # -- numeric normalization ------------------------------------------------

    def test_decimal_formatting_matches(self):
        # 42 vs 42.00
        passed, _ = self.grader("The total is 42.00 dollars.", {"value": 42})
        assert passed is True

    def test_thousands_separator_matches(self):
        passed, _ = self.grader("**Total revenue: 8,916**", {"value": 8916})
        assert passed is True

    def test_latex_thousands_separator_in_boxed(self):
        passed, _ = self.grader(
            "$$1{,}440 \\times 30 = \\boxed{8{,}916}$$", {"value": 8916}
        )
        assert passed is True

    def test_negative_number_matches(self):
        passed, _ = self.grader("The balance is -12.", {"value": -12})
        assert passed is True

    def test_wrong_decimal_value_fails(self):
        # '#### 42.50' must not be truncated to '42' and pass against 42.
        passed, _ = self.grader("#### 42.50", {"value": 42})
        assert passed is False

    # -- task-specific structured extraction ----------------------------------

    def test_field_extraction_from_json_object(self):
        passed, detail = self.grader(
            '{"routes": [1, 3, 6], "count": 3}',
            {"value": 3, "field": "count"},
        )
        assert passed is True
        assert "count" in detail

    def test_field_missing_from_json_falls_through(self):
        passed, _ = self.grader('{"other": 99}', {"value": 3, "field": "count"})
        assert passed is False

    def test_single_key_json_object_extracted(self):
        passed, _ = self.grader('{"subtask_count": 5}', {"value": 5})
        assert passed is True

    def test_label_declaration_extraction(self):
        passed, detail = self.grader(
            "Here is the plan.\n\nNumber of subtasks: 5\n\nDone.",
            {"value": 5, "label": "Number of subtasks"},
        )
        assert passed is True
        assert "Number of subtasks" in detail

    def test_pattern_extraction_last_match_wins(self):
        passed, detail = self.grader(
            "Draft count: 7 then revised.\nFinal count: 5",
            {"value": 5, "pattern": r"count:\s*(\d+)"},
        )
        assert passed is True
        assert "pattern" in detail

    def test_invalid_pattern_fails_cleanly(self):
        passed, detail = self.grader("x", {"value": 5, "pattern": "(unclosed["})
        assert passed is False
        assert "pattern" in detail

    def test_field_extraction_from_pre_parsed_dict(self):
        passed, _ = self.grader({"count": 3}, {"value": 3, "field": "count"})
        assert passed is True

    # -- generic extraction chain ----------------------------------------------

    def test_hash_marker_extraction(self):
        passed, _ = self.grader("Reasoning 100 + 20\n#### 120", {"value": 120})
        assert passed is True

    def test_boxed_extraction(self):
        passed, _ = self.grader(
            "so the position is $\\boxed{1}$", {"value": 1}
        )
        assert passed is True

    def test_bold_span_extraction(self):
        passed, _ = self.grader(
            "Route 1: 36\nRoute 3: 16\n\n**Count: 3 routes**", {"value": 3}
        )
        assert passed is True

    def test_answer_declaration_extraction(self):
        passed, _ = self.grader(
            "After checking all routes, the count is 3.", {"value": 3}
        )
        assert passed is True

    def test_last_line_extraction(self):
        passed, _ = self.grader(
            "Long reasoning.\n\nSome tables with 12 and 25.\n\nThe slot is 4.", {"value": 4}
        )
        assert passed is True

    # -- failure modes -----------------------------------------------------------

    def test_missing_value_fails(self):
        passed, detail = self.grader("42", {})
        assert passed is False
        assert "value" in detail

    def test_no_number_fails(self):
        passed, detail = self.grader("no digits here at all", {"value": 5})
        assert passed is False
        assert "no final-answer number" in detail

    def test_non_numeric_expected_without_number_fails(self):
        # A non-numeric expected value cannot match: the grader's contract
        # is numeric extraction, so no extractable number means failure.
        passed, detail = self.grader("The answer is XI", {"value": "XI"})
        assert passed is False
        assert "no final-answer number" in detail
