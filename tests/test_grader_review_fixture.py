"""Fixture-driven tests for the curated grader-review fixture.

tests/fixtures/grader_review_fixture.json is a CURATED REVIEW FIXTURE (not
independent human annotation): rows were hand-curated from archived
evaluation outputs (verbatim model answers, cited per row via ``archive_ref``)
and from the failure modes repaired alongside them. Every row carries a
``rationale`` so a reviewer can audit or challenge each label.

This module:

- validates fixture structure (ids, rationales, verdicts, archive pointers);
- re-verifies archive fidelity: every ``archive_ref`` must still point at a
  real archived trial whose final answer matches the fixture verbatim, so
  the fixture cannot silently drift from the record it cites;
- runs each row through the appropriate arm-agnostic grader (the grader
  never receives the arm; ``arm`` is provenance metadata only) and asserts
  the grader produces the row's ``expected_verdict``.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "src"))

import benchmarks.graders as graders_module  # noqa: E402
import benchmarks.run_public_bench as bench  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "grader_review_fixture.json"


def _load_fixture():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        fixture = json.load(f)
    assert fixture["kind"] == "curated-grader-review-fixture"
    assert "not independent human annotation" in fixture["curation_note"]
    return fixture


FIXTURE = _load_fixture()
ROWS = FIXTURE["rows"]


def _grade_row(row):
    """Run the row through the arm-agnostic grader it names.

    The arm is deliberately NOT passed anywhere: graders are arm-agnostic
    by design, so a row is graded identically no matter which arm produced
    the answer.
    """
    grader = row["grader"]
    if grader == "numeric":
        numeric = graders_module.NumericGrader()
        return numeric(row["model_answer"], row["expected_state"])
    if grader in ("gsm8k", "arc", "mmlu", "lsat", "bbh"):
        task = {"grader": grader, "expected": row["expected"]}
        if row.get("labels") is not None:
            task["labels"] = row["labels"]
        return bench.grade_task(task, row["model_answer"])
    raise ValueError(f"fixture row {row['id']!r} has unknown grader {grader!r}")


class TestFixtureStructure:
    def test_fixture_is_a_curated_review_fixture(self):
        assert FIXTURE["fixture_version"] == 1
        assert "CURATED REVIEW FIXTURE" in FIXTURE["curation_note"]
        assert set(FIXTURE["graded_by"]) == {
            "numeric", "gsm8k", "arc", "mmlu", "lsat", "bbh",
        }

    def test_every_row_is_fully_documented(self):
        ids = set()
        for row in ROWS:
            assert row["id"] not in ids, f"duplicate row id {row['id']!r}"
            ids.add(row["id"])
            assert row["grader"] in FIXTURE["graded_by"], row["id"]
            assert row["arm"] in ("classic", "tahoe"), row["id"]
            assert row["source"], f"{row['id']}: missing source"
            assert row["rationale"], f"{row['id']}: missing rationale"
            assert isinstance(row["expected_verdict"], bool), row["id"]
            assert row["model_answer"] is not None, row["id"]
            if row["grader"] == "numeric":
                assert "value" in row["expected_state"], row["id"]
            else:
                assert row["expected"] is not None, row["id"]

    def test_covers_both_arms_and_concise_and_verbose_answers(self):
        arms = {row["arm"] for row in ROWS}
        assert arms == {"classic", "tahoe"}
        # verbose = multi-line reasoning; concise = short/bare answer
        verbose = [r for r in ROWS if len(str(r["model_answer"]).splitlines()) > 2]
        concise = [r for r in ROWS if len(str(r["model_answer"]).splitlines()) <= 2]
        assert verbose and concise
        assert any(r["arm"] == "classic" for r in verbose)
        assert any(r["arm"] == "tahoe" for r in verbose)
        assert any(r["arm"] == "classic" for r in concise)
        assert any(r["arm"] == "tahoe" for r in concise)

    def test_includes_required_failure_modes(self):
        ids = {row["id"] for row in ROWS}
        # verbose plan ending in 8 but expected 5 must fail
        assert "plan-01-classic-verbose-eight-fail" in ids
        # GSM8K 42 vs 42.00 and normalized thousands pass
        assert "gsm8k-42-vs-42-00-pass" in ids
        assert "gsm8k-1026-classic-boxed-latex-thousands-pass" in ids
        assert "gsm8k-plain-comma-thousands-pass" in ids
        # explicit final Answer: D after earlier option A passes
        assert "mmlu-math-0005-final-answer-marker-pass" in ids
        # ARC numeric label 3 with displayed labels and answer C passes
        assert "arc-0313-numeric-label-c-pass" in ids
        # truncated/empty answer fails
        assert any("empty" in i and "fail" in i for i in ids)


class TestFixtureArchiveFidelity:
    """Every archive_ref must still resolve to the verbatim archived answer."""

    @pytest.mark.parametrize("row", [r for r in ROWS if r.get("archive_ref")],
                             ids=[r["id"] for r in ROWS if r.get("archive_ref")])
    def test_archived_answer_matches_fixture_verbatim(self, row):
        ref = row["archive_ref"]
        path = ROOT / ref["file"]
        assert path.exists(), f"{row['id']}: archive file {ref['file']} missing"
        trials = json.loads(path.read_text(encoding="utf-8"))
        matches = [
            t for t in trials
            if t.get("task_id") == ref["task_id"]
            and t.get("arm") == ref["arm"]
            and (ref.get("trial") is None or t.get("trial") == ref["trial"])
            and t.get("final_answer") == row["model_answer"]
        ]
        assert matches, (
            f"{row['id']}: fixture answer no longer matches the archived "
            f"record {ref['file']} ({ref['task_id']}, arm={ref['arm']}, "
            f"trial={ref.get('trial')})"
        )

    def test_synthetic_rows_do_not_cite_an_archive(self):
        for row in ROWS:
            has_ref = "archive_ref" in row
            assert "synthetic" in row["source"] or has_ref, row["id"]
            if not has_ref:
                assert "synthetic" in row["source"], row["id"]


class TestFixtureVerdicts:
    """Each row graded by the arm-agnostic grader must match its label."""

    @pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
    def test_row_verdict(self, row):
        passed, detail = _grade_row(row)
        assert passed is row["expected_verdict"], (
            f"{row['id']}: expected verdict {row['expected_verdict']}, "
            f"grader said {passed} ({detail!r}). "
            f"Rationale: {row['rationale']}"
        )

    def test_arm_provenance_is_never_sent_to_a_grader(self):
        # The fixture stores arm provenance for review coverage only; the
        # dispatch in _grade_row never forwards it, mirroring the runners
        # (pinned by tests/test_prompt_ablation.py for grade_task).
        for row in ROWS:
            assert "arm" not in row.get("expected_state", {})
            task = {"grader": row["grader"], "expected": row.get("expected")}
            if row.get("labels") is not None:
                task["labels"] = row["labels"]
            assert "arm" not in task
