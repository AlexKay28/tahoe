"""Focused tests for truthful trial-outcome capture in the classic-runner
benchmark wrappers (phase 2).

Pinned regressions (archived evaluations used to relabel every
infrastructure failure as ``wrong_answer``):

- A non-``"none"`` runner ``failure_class`` (``api_error``, ``timeout``,
  ``empty_response``, ...) must be preserved verbatim in every wrapper
  and can never be graded into a pass.
- A token-limit-capped completion (``finish_reason`` of ``length`` /
  ``max_tokens``) that fails grading is ``"truncated"``, not an ordinary
  ``wrong_answer`` — including when the final answer is NONEMPTY. A
  capped answer the grader accepts keeps its pass verdict with the
  truncation still visible in ``finish_reason``/``truncated``.
- ``finish_reason`` / ``truncated`` / ``empty_response`` / ``retries`` /
  ``retry_history`` / ``request_params`` are preserved in every
  serialized trial, with ``getattr`` defaults so legacy result shapes
  (``SimpleNamespace`` without the new fields) keep working.
- ``outdir.make_run_dir`` is exclusive: a second run never overwrites an
  earlier run's directory, and ``write_manifest`` never overwrites an
  existing manifest.

All runs are mocked — no model evaluation, no network.
"""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_BENCH_DIR = Path(__file__).resolve().parent.parent / "benchmarks"
sys.path.insert(0, str(_BENCH_DIR))
sys.path.insert(0, str(_BENCH_DIR.parent / "src"))

import benchmarks.outdir as outdir_mod  # noqa: E402
import benchmarks.run_public_bench as public_bench  # noqa: E402
import benchmarks.run_trials as trials_mod  # noqa: E402
import benchmarks.runner_classic as runner_mod  # noqa: E402


# -- fakes -------------------------------------------------------------------

def _classic_result(
    final_answer="42",
    failure_class="none",
    finish_reason="stop",
    passed=True,
    empty_response=False,
    retries=0,
    retry_history=None,
    request_params=None,
    output_tokens=5,
):
    """A ClassicResult-shaped fake, including the phase-1 capture fields."""
    return SimpleNamespace(
        task_id="test-001",
        input_tokens=10,
        output_tokens=output_tokens,
        total_tokens=10 + output_tokens,
        wall_seconds=0.1,
        passed=passed,
        failure_class=failure_class,
        turns=1,
        final_answer=final_answer,
        finish_reason=finish_reason,
        empty_response=empty_response,
        retries=retries,
        retry_history=list(retry_history or []),
        request_params=dict(request_params or {}),
    )


def _public_task():
    return {
        "task_id": "test-001",
        "benchmark": "gsm8k",
        "description": "What is 6 x 7?",
        "expected": "#### 42",  # GSM8K gold format: grade_gsm8k extracts '#### N'
        "grader": "gsm8k",
    }


def _seven_task():
    # Shape mirrors benchmarks/tasks/routing-01.yaml (numeric grader).
    return {
        "task_id": "test-001",
        "description": "What is 6 x 7? Report the total.",
        "difficulty": "easy",
        "expected_state": {"value": 42},
        "grader": {"type": "numeric", "params": {"value": 42}},
    }


def _run_public_trial(result, arm="tahoe", task=None):
    """run_public_bench.run_trial with a mocked runner (no API call)."""
    task = task or _public_task()
    with mock.patch.object(public_bench, "run_classic", return_value=result):
        return public_bench.run_trial(task, arm, "tahoe skill text", 0)


def _run_seven_task_arm(result, task=None):
    """run_trials.run_classic_arm + apply_grading with a mocked runner."""
    task = task or _seven_task()
    with mock.patch.object(trials_mod, "run_classic", return_value=result):
        trial = trials_mod.run_classic_arm(task, 0)
    return trials_mod.apply_grading(trial, task)


# -- 1. shared labeling policy (runner_classic) -----------------------------

@pytest.mark.parametrize(
    "failure",
    ["api_error", "timeout", "max_turns", "empty_response", "error", "runner_error", "vm_error"],
)
def test_grading_outcome_preserves_runner_failure_class(failure):
    # Even a grader verdict of "pass" must not convert an infrastructure
    # failure into a pass, and the failure class is never relabeled.
    passed, failure_class = runner_mod.grading_outcome(failure, grader_passed=True)
    assert passed is False
    assert failure_class == failure


def test_grading_outcome_clean_answers():
    assert runner_mod.grading_outcome("none", True) == (True, "none")
    assert runner_mod.grading_outcome("none", False, "stop") == (False, "wrong_answer")
    assert runner_mod.grading_outcome(None, False) == (False, "wrong_answer")


@pytest.mark.parametrize("reason", ["length", "max_tokens", "max_output_tokens"])
def test_grading_outcome_truncated_semantics(reason):
    # A capped answer that fails grading is "truncated", not wrong_answer;
    # a capped answer the grader accepts keeps its pass verdict.
    assert runner_mod.grading_outcome("none", False, reason) == (False, "truncated")
    assert runner_mod.grading_outcome("none", True, reason) == (True, "none")


def test_is_truncated():
    for reason in ("length", "max_tokens", "max_output_tokens", " LENGTH "):
        assert runner_mod.is_truncated(reason) is True
    for reason in ("stop", "tool_calls", "", None):
        assert runner_mod.is_truncated(reason) is False


def test_outcome_fields_legacy_shape_defaults():
    # Wrappers must keep working with pre-capture result shapes
    # (test_baseline_arms / test_prompt_ablation fakes).
    legacy = SimpleNamespace(
        task_id="test-001",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        wall_seconds=0.0,
        passed=True,
        failure_class="none",
        turns=1,
        final_answer="42",
    )
    fields = runner_mod.outcome_fields(legacy)
    assert fields == {
        "finish_reason": "",
        "truncated": False,
        "cap_exhausted": False,
        "output_token_cap": 0,
        "empty_response": False,
        "retries": 0,
        "retry_history": [],
        "request_params": {},
    }
    json.dumps(fields)  # JSON-safe


def test_outcome_fields_capture_full_metadata():
    params = {
        "model": ".",
        "messages": [{"role": "user", "content": "What is 6 x 7?"}],
        "max_tokens": 2048,
        "tools": None,
        "extra_body": {},
    }
    history = [{"turn": 1, "attempt": 0, "failure_class": "api_error", "error": "503"}]
    fields = runner_mod.outcome_fields(
        _classic_result(
            finish_reason="length",
            empty_response=True,
            retries=1,
            retry_history=history,
            request_params=params,
        )
    )
    assert fields == {
        "finish_reason": "length",
        "truncated": True,
        "cap_exhausted": True,
        "output_token_cap": 2048,
        "empty_response": True,
        "retries": 1,
        "retry_history": history,
        "request_params": params,
    }
    json.dumps(fields)


def test_outcome_fields_cap_exhaustion_length_vs_clean_stop():
    # Clean stop: no cap exhaustion; the requested cap is still recorded.
    clean = runner_mod.outcome_fields(
        _classic_result(finish_reason="stop", request_params={"max_tokens": 2048})
    )
    assert clean["truncated"] is False
    assert clean["cap_exhausted"] is False
    assert clean["output_token_cap"] == 2048

    # Length-capped: the output token cap was exhausted.
    capped = runner_mod.outcome_fields(
        _classic_result(finish_reason="length", request_params={"max_tokens": 2048})
    )
    assert capped["truncated"] is True
    assert capped["cap_exhausted"] is True
    assert capped["output_token_cap"] == 2048


@pytest.mark.parametrize("bad", [0, -5, "2048", 2.5, True, None])
def test_outcome_fields_output_token_cap_requires_positive_int(bad):
    # Only a positive integer max_tokens is copied; anything else is 0 so
    # reporting can never mistake a malformed/missing cap for a real one.
    fields = runner_mod.outcome_fields(_classic_result(request_params={"max_tokens": bad}))
    assert fields["output_token_cap"] == 0
    assert fields["cap_exhausted"] is False


def test_outcome_fields_legacy_result_missing_request_params():
    # A result object without any capture fields (older mocks): the
    # derived fields fall back to "unknown cap", never to a fabricated one.
    legacy = SimpleNamespace(
        final_answer="42",
        passed=True,
        failure_class="none",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        wall_seconds=0.0,
        turns=1,
    )
    fields = runner_mod.outcome_fields(legacy)
    assert fields["request_params"] == {}
    assert fields["cap_exhausted"] is False
    assert fields["output_token_cap"] == 0


# -- 2. run_public_bench.run_trial ------------------------------------------

def test_public_trial_success_preserves_metadata():
    params = {
        "model": ".",
        "messages": [{"role": "user", "content": "What is 6 x 7?"}],
        "max_tokens": 2048,
        "tools": None,
        "extra_body": {},
    }
    trial = _run_public_trial(_classic_result(finish_reason="stop", request_params=params))
    assert trial["passed"] is True
    assert trial["failure_class"] == "none"
    assert trial["finish_reason"] == "stop"
    assert trial["truncated"] is False
    assert trial["cap_exhausted"] is False
    assert trial["output_token_cap"] == 2048
    assert trial["empty_response"] is False
    assert trial["retries"] == 0
    assert trial["retry_history"] == []
    assert trial["request_params"] == params
    assert json.loads(json.dumps(trial)) == trial  # JSON round-trip


def test_public_trial_empty_capped_answer_stays_empty_response():
    # Length-capped EMPTY answer: the most specific truthful label wins —
    # never wrong_answer, never a pass.
    trial = _run_public_trial(
        _classic_result(
            final_answer="",
            failure_class="empty_response",
            passed=False,
            finish_reason="length",
            empty_response=True,
            output_tokens=2048,
        )
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "empty_response"
    assert trial["finish_reason"] == "length"
    assert trial["truncated"] is True
    assert trial["cap_exhausted"] is True
    assert trial["empty_response"] is True
    json.dumps(trial)


def test_public_trial_nonempty_capped_wrong_answer_is_truncated():
    # Nonempty answer, hit the token limit, failed grading: "truncated",
    # not ordinary wrong_answer.
    trial = _run_public_trial(
        _classic_result(final_answer="41", finish_reason="length", output_tokens=2048)
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "truncated"
    assert trial["finish_reason"] == "length"
    assert trial["truncated"] is True
    assert trial["cap_exhausted"] is True
    assert trial["grader_detail"]  # grader still ran and said why
    json.dumps(trial)


def test_public_trial_nonempty_capped_correct_answer_still_passes():
    # A truncated answer the grader accepts keeps its pass verdict, with
    # the truncation preserved in the metadata.
    trial = _run_public_trial(
        _classic_result(final_answer="42", finish_reason="length", output_tokens=2048)
    )
    assert trial["passed"] is True
    assert trial["failure_class"] == "none"
    assert trial["finish_reason"] == "length"
    assert trial["truncated"] is True
    assert trial["cap_exhausted"] is True
    json.dumps(trial)


def test_public_trial_api_error_after_retries_not_wrong_answer_nor_pass():
    # The runner recovered nothing: two retries, then an API error. The
    # answer happens to be correct, but grading must not convert the
    # infrastructure failure into a pass.
    history = [
        {"turn": 1, "attempt": 0, "failure_class": "api_error", "error": "503"},
        {"turn": 1, "attempt": 1, "failure_class": "api_error", "error": "503"},
    ]
    trial = _run_public_trial(
        _classic_result(
            final_answer="42",
            failure_class="api_error",
            passed=False,
            retries=2,
            retry_history=history,
        )
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "api_error"
    assert trial["retries"] == 2
    assert trial["retry_history"] == history
    json.dumps(trial)


def test_public_trial_wrong_answer_only_when_runner_failure_is_none():
    trial = _run_public_trial(
        _classic_result(final_answer="41", finish_reason="stop", passed=False)
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "wrong_answer"
    assert trial["truncated"] is False
    json.dumps(trial)


def test_public_trial_legacy_result_shape_defaults():
    # run_trial must tolerate pre-capture result objects (getattr defaults).
    legacy = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        wall_seconds=0.1,
        passed=True,
        failure_class="none",
        turns=1,
        final_answer="42",
    )
    trial = _run_public_trial(legacy)
    assert trial["passed"] is True
    assert trial["failure_class"] == "none"
    assert trial["finish_reason"] == ""
    assert trial["truncated"] is False
    assert trial["cap_exhausted"] is False
    assert trial["output_token_cap"] == 0
    assert trial["empty_response"] is False
    assert trial["retries"] == 0
    assert trial["retry_history"] == []
    assert trial["request_params"] == {}
    json.dumps(trial)


# -- 3. run_trials (seven-task ablation) serialization ----------------------

def test_seven_task_arm_serializes_length_capped_empty_outcome():
    trial = _run_seven_task_arm(
        _classic_result(
            final_answer="",
            failure_class="empty_response",
            passed=False,
            finish_reason="length",
            empty_response=True,
            output_tokens=1024,
        )
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "empty_response"  # preserved, not wrong_answer
    assert trial["finish_reason"] == "length"
    assert trial["truncated"] is True
    assert trial["cap_exhausted"] is True
    assert trial["empty_response"] is True
    assert trial["arm"] == "classic"
    assert json.loads(json.dumps(trial)) == trial


def test_seven_task_arm_preserves_api_failure_over_grader():
    # Grader accepts the answer ("42" vs value 42) — must still not pass.
    trial = _run_seven_task_arm(
        _classic_result(
            final_answer="42",
            failure_class="api_error",
            passed=False,
            retries=2,
            retry_history=[
                {"turn": 1, "attempt": 0, "failure_class": "api_error", "error": "503"},
            ],
        )
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "api_error"
    assert trial["quality_score"] == 0.0
    assert trial["retries"] == 2
    assert len(trial["retry_history"]) == 1
    json.dumps(trial)


def test_seven_task_arm_nonempty_capped_wrong_answer_is_truncated():
    trial = _run_seven_task_arm(
        _classic_result(final_answer="41", finish_reason="length", output_tokens=1024)
    )
    assert trial["passed"] is False
    assert trial["failure_class"] == "truncated"
    assert trial["truncated"] is True
    json.dumps(trial)


def test_seven_task_runner_error_trial_schema_matches_arm_trial():
    task = _seven_task()
    with mock.patch.object(trials_mod, "run_classic", return_value=_classic_result(final_answer="42")):
        arm_trial = trials_mod.apply_grading(trials_mod.run_classic_arm(task, 0), task)
    error_trial = trials_mod.runner_error_trial("test-001", "classic", 0, RuntimeError("boom"))
    # Identical serialized schema, so consumers never see two shapes.
    assert set(error_trial.keys()) == set(arm_trial.keys())
    assert error_trial["failure_class"] == "runner_error"
    assert error_trial["passed"] is False
    assert error_trial["finish_reason"] == ""
    assert error_trial["truncated"] is False
    assert error_trial["cap_exhausted"] is False
    assert error_trial["output_token_cap"] == 0
    assert error_trial["empty_response"] is False
    assert error_trial["retries"] == 0
    assert error_trial["retry_history"] == []
    assert error_trial["request_params"] == {}
    assert "boom" in error_trial["final_answer"]
    assert json.loads(json.dumps(error_trial)) == error_trial


# -- 4. outdir: exclusive run directories and manifests ---------------------

def test_make_run_dir_is_exclusive_and_unique(tmp_path):
    first = outdir_mod.make_run_dir("unit-test", results_root=tmp_path)
    assert first.is_dir()
    assert (tmp_path / "runs") in first.parents
    second = outdir_mod.make_run_dir("unit-test", results_root=tmp_path)
    assert second.is_dir()
    assert second != first  # never the same directory twice
    assert first.exists() and second.exists()


def test_make_run_dir_never_overwrites_earlier_run(tmp_path):
    first = outdir_mod.make_run_dir("unit-test-keep", results_root=tmp_path)
    sentinel = first / "trials.json"
    sentinel.write_text("earlier run's raw data")
    second = outdir_mod.make_run_dir("unit-test-keep", results_root=tmp_path)
    assert sentinel.read_text() == "earlier run's raw data"
    assert second.parent == first.parent


def test_write_manifest_is_exclusive_and_hashes_sources(tmp_path):
    run_dir = outdir_mod.make_run_dir("unit-test-manifest", results_root=tmp_path)
    src = tmp_path / "runner.py"
    src.write_text("print('hi')\n")
    manifest_path = outdir_mod.write_manifest(
        run_dir, config={"runner": "unit", "n": 3}, source_files=[src]
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["config"] == {"runner": "unit", "n": 3}
    assert manifest["source_hashes"]["runner.py"] == hashlib.sha256(
        b"print('hi')\n"
    ).hexdigest()
    assert manifest["created_utc"]
    # A second manifest write must never overwrite the first (exclusive).
    with pytest.raises(FileExistsError):
        outdir_mod.write_manifest(run_dir, config={"other": 1}, source_files=[])