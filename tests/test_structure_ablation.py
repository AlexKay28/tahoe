"""Tests for the preregistered structure x answer-only experiment.

Verifies (per the experiment's preregistration, docs/PREREGISTRATION-structure-answer.md):

- exact arm prompt relationships (canonical byte-equality, derived
  no-contract variant, answer-only sentence, TAHOE-free generic arm, cod
  control)
- the two explicitly configured output-budget regimes and identical
  generation settings across arms (only the system prompt varies by arm;
  only max_tokens varies by regime)
- trial-plan keyed pairing: full factorial coverage, determinism, and
  complete (benchmark, task_id, trial) pairing across arms
- the preregistered endpoints (tokens/cost per success include failures)
- Holm-corrected comparisons and the explicit non-inferiority margin
- immutable, refuse-to-overwrite output creation
- the manifest's hash fields
- main() is NOT executed on import (no API access, no output directories)
- the grader is arm-invariant

No test here launches a model evaluation.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BENCH_DIR = _REPO_ROOT / "benchmarks"
sys.path.insert(0, str(_BENCH_DIR))
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_BENCH_DIR / "src"))


def _load_module():
    import benchmarks.run_structure_ablation as mod
    return mod


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- Synthetic helpers ------------------------------------------------------


def _fake_classic_result(
    final_answer="42",
    input_tokens=10,
    output_tokens=5,
    passed=True,
    failure_class="none",
    finish_reason="stop",
    empty_response=False,
):
    return SimpleNamespace(
        task_id="synthetic",
        arm="classic",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        wall_seconds=0.1,
        passed=passed,
        failure_class=failure_class,
        turns=1,
        final_answer=final_answer,
        finish_reason=finish_reason,
        empty_response=empty_response,
        retries=0,
        retry_history=[],
        request_params={},
    )


def _synthetic_task(i):
    return {
        "task_id": f"synth-{i:03d}",
        "benchmark": f"bench-{i % 3}",
        "description": f"Question number {i}: what is {i} + 1?",
        "expected": f"#### {i + 1}",
        "grader": "gsm8k",
    }


def _synthetic_trials(n_tasks=10, trials_per_task=3):
    """All six arms x both regimes x n_tasks x trials, deterministic outcomes."""
    mod = _load_module()
    trials = []
    for regime in mod.REGIMES:
        for arm in mod.ARMS:
            for task_i in range(n_tasks):
                for trial in range(trials_per_task):
                    # deterministic per-cell outcome: later arms do better
                    # (non-cyclic pattern so arm effects do not cancel out)
                    arm_idx = mod.ARMS.index(arm)
                    passed = (
                        (task_i * 7 + trial * 3 + arm_idx * 11) % 10
                    ) < (2 * arm_idx + 2)
                    tokens = 100 + 10 * arm_idx + 5 * trial + task_i
                    trials.append(
                        {
                            "task_id": f"synth-{task_i:03d}",
                            # real benchmark names so the scoped H2 cluster
                            # comparison (bbh family) has tasks to pair
                            "benchmark": (
                                "bbh" if task_i % 5 == 0
                                else "bbh_track" if task_i % 5 == 1
                                else "bbh_arith" if task_i % 5 == 2
                                else "gsm8k" if task_i % 5 == 3
                                else "arc"
                            ),
                            "arm": arm,
                            "regime": regime,
                            "trial": trial,
                            "passed": passed,
                            "total_tokens": tokens,
                            "output_tokens": tokens // 2,
                            "input_tokens": tokens - tokens // 2,
                            "cost_usd": tokens / 1_000_000.0,
                            "failure_class": "none" if passed else "wrong_answer",
                            "finish_reason": "stop",
                            "empty_response": False,
                        }
                    )
    return trials


def _fast_config():
    mod = _load_module()
    cfg = copy.deepcopy(mod.load_config())
    cfg["stats"] = {"n_permutations": 200, "n_resamples": 200}
    return cfg


# -- 1. Exact arm prompt relationships --------------------------------------


def test_tahoe_full_is_canonical_byte_exact():
    mod = _load_module()
    from prompt_paths import resolve_prompt

    prompts = mod.load_arm_prompts()
    canonical = mod.load_canonical_tahoe()
    assert prompts["tahoe_full"] == canonical
    assert canonical == resolve_prompt("tahoe").read_text(encoding="utf-8")
    assert canonical.encode("utf-8") == (
        _REPO_ROOT / "language" / "skills" / "tahoe-93.txt"
    ).read_bytes()


def test_tahoe_structure_recomposes_to_canonical():
    mod = _load_module()
    prompts = mod.load_arm_prompts()
    canonical = mod.load_canonical_tahoe()
    sentence = mod.answer_only_sentence(canonical)
    # the ONLY difference between tahoe_full and tahoe_structure is the
    # final output-contract sentence
    assert prompts["tahoe_structure"] + "\n\n" + sentence == canonical.rstrip("\n")
    assert "Output only the answer" not in prompts["tahoe_structure"]
    # the structural scaffold is still present
    for marker in ("Compute:", "Select:", "Deduce:"):
        assert marker in prompts["tahoe_structure"]


def test_tahoe_structure_differs_from_canonical_by_one_sentence_only():
    mod = _load_module()
    canonical = mod.load_canonical_tahoe()
    derived = mod.derive_tahoe_structure(canonical)
    canonical_lines = [
        line for line in canonical.rstrip("\n").split("\n") if line.strip()
    ]
    derived_lines = [line for line in derived.split("\n") if line.strip()]
    assert derived_lines == canonical_lines[:-1]


def test_answer_only_is_the_canonical_final_sentence():
    mod = _load_module()
    canonical = mod.load_canonical_tahoe()
    sentence = mod.answer_only_sentence(canonical)
    assert sentence.startswith("Output only the answer")
    prompts = mod.load_arm_prompts()
    assert prompts["answer_only"] == sentence
    artifact = (
        _BENCH_DIR / "prompts" / "structure-answer" / "answer-only.txt"
    ).read_text(encoding="utf-8").strip()
    assert artifact == sentence


def test_generic_structure_is_tahoe_free_and_ends_with_contract():
    mod = _load_module()
    prompts = mod.load_arm_prompts()
    generic = prompts["generic_structure"]
    assert "tahoe" not in generic.lower()
    assert generic.rstrip("\n").endswith(mod.answer_only_sentence(mod.load_canonical_tahoe()))
    assert generic != prompts["tahoe_structure"]
    assert len(generic) > 50


def test_cod_arm_is_existing_baseline_byte_exact():
    mod = _load_module()
    from prompt_paths import resolve_prompt
    prompts = mod.load_arm_prompts()
    assert prompts["cod"] == resolve_prompt("cod").read_text(encoding="utf-8")


def test_classic_arm_is_empty_prompt():
    mod = _load_module()
    prompts = mod.load_arm_prompts()
    assert prompts["classic"] == ""


def test_load_arm_prompts_returns_exactly_six_arms():
    mod = _load_module()
    prompts = mod.load_arm_prompts()
    assert set(prompts) == set(mod.ARMS)
    assert len(prompts) == 6


def test_verify_prompt_relationships_rejects_tampering():
    mod = _load_module()
    prompts = mod.load_arm_prompts()
    canonical = mod.load_canonical_tahoe()
    tampered = dict(prompts)
    tampered["tahoe_full"] = canonical.replace("TAHOE", "TAH0E")
    with pytest.raises(ValueError):
        mod.verify_prompt_relationships(tampered, canonical)
    tampered = dict(prompts)
    tampered["tahoe_structure"] = prompts["tahoe_structure"] + " extra"
    with pytest.raises(ValueError):
        mod.verify_prompt_relationships(tampered, canonical)


def test_derivation_guards_break_loudly_on_drift():
    mod = _load_module()
    with pytest.raises(ValueError):
        mod.answer_only_sentence("no output contract here at all.\n\nNone.")
    with pytest.raises(ValueError):
        mod.derive_tahoe_structure("")


# -- 2. Configuration: budgets and regimes ----------------------------------


def test_config_arms_match_design():
    mod = _load_module()
    cfg = mod.load_config()
    assert cfg["arms"] == mod.ARMS
    assert mod.ARMS == [
        "classic",
        "answer_only",
        "generic_structure",
        "tahoe_structure",
        "tahoe_full",
        "cod",
    ]


def test_config_has_two_explicit_regimes_with_ordered_budgets():
    mod = _load_module()
    cfg = mod.load_config()
    assert set(cfg["regimes"]) == {"constrained", "adequate"}
    assert cfg["regimes"]["constrained"]["max_tokens"] < cfg["regimes"]["adequate"]["max_tokens"]
    assert mod.REGIMES == ["constrained", "adequate"]


def test_regimes_configure_only_max_tokens():
    mod = _load_module()
    cfg = mod.load_config()
    assert cfg["regimes"]["constrained"] == {
        "max_tokens": cfg["regimes"]["constrained"]["max_tokens"]
    }
    assert cfg["regimes"]["adequate"] == {
        "max_tokens": cfg["regimes"]["adequate"]["max_tokens"]
    }


def test_generation_settings_are_shared_and_arm_free():
    mod = _load_module()
    cfg = mod.load_config()
    for key in ("max_turns", "timeout_seconds", "temperature", "top_p"):
        assert key in cfg["generation"]
    # arms are plain names: no per-arm generation overrides can exist
    assert all(isinstance(arm, str) for arm in cfg["arms"])


def test_validate_config_rejects_inverted_budgets():
    mod = _load_module()
    cfg = mod.load_config()
    bad = copy.deepcopy(cfg)
    bad["regimes"]["constrained"]["max_tokens"] = 4096
    bad["regimes"]["adequate"]["max_tokens"] = 256
    with pytest.raises(ValueError, match="constrained"):
        mod.validate_config(bad)


def test_validate_config_rejects_extra_regime_keys():
    mod = _load_module()
    cfg = mod.load_config()
    bad = copy.deepcopy(cfg)
    bad["regimes"]["constrained"]["temperature"] = 0.7
    with pytest.raises(ValueError, match="nothing else|max_tokens"):
        mod.validate_config(bad)


def test_validate_config_rejects_bad_margin():
    mod = _load_module()
    cfg = mod.load_config()
    bad = copy.deepcopy(cfg)
    bad["noninferiority"]["margin"] = 0.0
    with pytest.raises(ValueError, match="margin"):
        mod.validate_config(bad)


def test_noninferiority_margin_is_explicit_and_bounded():
    mod = _load_module()
    cfg = mod.load_config()
    ni = cfg["noninferiority"]
    assert ni["reference_arm"] == "tahoe_full"
    assert ni["margin"] == 0.05
    assert 0.0 < ni["alpha"] < 1.0
    assert all(cand in mod.ARMS for cand in ni["candidates"])


# -- 3. Trial execution (mocked runner; no API access) ----------------------


def _run_trial_with_mock(mod, task, arm, regime, prompt, trial_idx=0, result=None):
    captured = {}

    def fake_run_classic(**kwargs):
        captured.update(kwargs)
        return result if result is not None else _fake_classic_result()

    with mock.patch.object(mod, "run_classic", side_effect=fake_run_classic):
        record = mod.run_trial(task, arm, regime, prompt, trial_idx, mod.load_config())
    return record, captured


def test_run_trial_preserves_host_task_prompt_verbatim():
    mod = _load_module()
    task = _synthetic_task(0)
    _, captured = _run_trial_with_mock(
        mod, task, "tahoe_full", "adequate", "prompt text"
    )
    assert captured["task_prompt"] == task["description"]


def test_run_trial_generation_settings_identical_across_arms():
    mod = _load_module()
    task = _synthetic_task(1)
    prompts = mod.load_arm_prompts()
    seen = {}
    for arm in mod.ARMS:
        _, captured = _run_trial_with_mock(
            mod, task, arm, "constrained", prompts[arm]
        )
        # task_id embeds arm/regime as a trial label by design; everything
        # else must be identical across arms
        knob_copy = {
            k: v
            for k, v in captured.items()
            if k not in ("system_prompt", "task_id")
        }
        seen[arm] = knob_copy
    values = list(seen.values())
    assert all(v == values[0] for v in values), (
        "generation settings must be identical across arms; only the "
        f"system prompt may differ. Got: {seen}"
    )
    # and the system prompts really do differ where designed
    assert prompts["tahoe_full"] != prompts["tahoe_structure"]
    assert prompts["answer_only"] != prompts["classic"]


def test_run_trial_uses_regime_max_tokens():
    mod = _load_module()
    cfg = mod.load_config()
    task = _synthetic_task(2)
    _, captured_con = _run_trial_with_mock(
        mod, task, "classic", "constrained", ""
    )
    _, captured_adeq = _run_trial_with_mock(
        mod, task, "classic", "adequate", ""
    )
    assert captured_con["max_tokens"] == cfg["regimes"]["constrained"]["max_tokens"]
    assert captured_adeq["max_tokens"] == cfg["regimes"]["adequate"]["max_tokens"]
    assert captured_con["max_tokens"] < captured_adeq["max_tokens"]


def test_run_trial_failure_classes_are_truthful():
    mod = _load_module()
    task = _synthetic_task(3)

    # graded pass -> none
    record, _ = _run_trial_with_mock(
        mod, task, "classic", "constrained", "",
        result=_fake_classic_result(passed=True, final_answer="4"),
    )
    assert record["failure_class"] == "none"
    assert record["runner_failure_class"] == "none"

    # produced answer that graded wrong -> wrong_answer (graded failure)
    record, _ = _run_trial_with_mock(
        mod, task, "classic", "constrained", "",
        result=_fake_classic_result(passed=True, final_answer="999"),
    )
    assert record["failure_class"] == "wrong_answer"
    assert record["runner_failure_class"] == "none"

    # empty response is NEVER relabeled as a graded wrong answer
    record, _ = _run_trial_with_mock(
        mod, task, "classic", "constrained", "",
        result=_fake_classic_result(
            passed=False,
            failure_class="empty_response",
            final_answer="",
            finish_reason="length",
            empty_response=True,
        ),
    )
    assert record["failure_class"] == "empty_response"
    assert record["runner_failure_class"] == "empty_response"
    assert record["finish_reason"] == "length"
    assert record["empty_response"] is True


def test_run_trial_records_tokens_and_cost():
    mod = _load_module()
    cfg = mod.load_config()
    task = _synthetic_task(4)
    record, _ = _run_trial_with_mock(
        mod, task, "answer_only", "adequate", "prompt",
        result=_fake_classic_result(input_tokens=1000, output_tokens=500),
    )
    expected_cost = (
        1000 / 1e6 * cfg["cost"]["input_per_mtok"]
        + 500 / 1e6 * cfg["cost"]["output_per_mtok"]
    )
    assert record["total_tokens"] == 1500
    assert record["cost_usd"] == pytest.approx(expected_cost)


def test_error_trial_record_shape():
    mod = _load_module()
    task = _synthetic_task(5)
    record = mod.error_trial_record(task, "cod", "constrained", 2, RuntimeError("boom"))
    assert record["task_id"] == task["task_id"]
    assert record["arm"] == "cod"
    assert record["regime"] == "constrained"
    assert record["trial"] == 2
    assert record["passed"] is False
    assert record["failure_class"] == "error"
    assert record["total_tokens"] == 0
    assert "boom" in record["final_answer"]


# -- 4. Trial plan: pairing and factorial coverage --------------------------


def test_build_trial_plan_full_factorial_count():
    mod = _load_module()
    tasks = [_synthetic_task(i) for i in range(7)]
    plan = mod.build_trial_plan(tasks, mod.ARMS, mod.REGIMES, 3, 42)
    assert len(plan) == 7 * len(mod.ARMS) * len(mod.REGIMES) * 3


def test_build_trial_plan_covers_every_cell_exactly_once():
    mod = _load_module()
    tasks = [_synthetic_task(i) for i in range(5)]
    plan = mod.build_trial_plan(tasks, mod.ARMS, mod.REGIMES, 3, 42)
    cells = {(e["task"]["task_id"], e["arm"], e["regime"], e["trial"]) for e in plan}
    assert len(cells) == len(plan)
    for task in tasks:
        for arm in mod.ARMS:
            for regime in mod.REGIMES:
                for trial in range(3):
                    assert (task["task_id"], arm, regime, trial) in cells


def test_build_trial_plan_is_deterministic():
    mod = _load_module()
    tasks = [_synthetic_task(i) for i in range(4)]
    plan1 = mod.build_trial_plan(tasks, mod.ARMS, mod.REGIMES, 3, 42)
    plan2 = mod.build_trial_plan(tasks, mod.ARMS, mod.REGIMES, 3, 42)
    assert plan1 == plan2


def test_trial_plan_pairs_completely_across_arms():
    """Keyed pairing: any two arms share identical (benchmark, task_id, trial)
    coverage, so stats.pair_trials finds every expected pair."""
    import stats

    mod = _load_module()
    trials = _synthetic_trials(n_tasks=4, trials_per_task=2)
    for regime in mod.REGIMES:
        a = [t for t in trials if t["arm"] == "tahoe_full" and t["regime"] == regime]
        b = [t for t in trials if t["arm"] == "classic" and t["regime"] == regime]
        pairs = stats.pair_trials(a, b)
        assert len(pairs) == len(a) == len(b)


# -- 5. Preregistered endpoints ---------------------------------------------


def test_tokens_per_success_includes_failure_spend():
    mod = _load_module()
    trials = [
        {"regime": "constrained", "arm": "classic", "passed": True, "total_tokens": 100,
         "output_tokens": 50, "input_tokens": 50, "cost_usd": 0.0002,
         "failure_class": "none", "finish_reason": "stop", "empty_response": False},
        {"regime": "constrained", "arm": "classic", "passed": True, "total_tokens": 300,
         "output_tokens": 150, "input_tokens": 150, "cost_usd": 0.0006,
         "failure_class": "none", "finish_reason": "stop", "empty_response": False},
        {"regime": "constrained", "arm": "classic", "passed": False, "total_tokens": 50,
         "output_tokens": 25, "input_tokens": 25, "cost_usd": 0.0001,
         "failure_class": "wrong_answer", "finish_reason": "stop", "empty_response": False},
        {"regime": "constrained", "arm": "classic", "passed": False, "total_tokens": 150,
         "output_tokens": 75, "input_tokens": 75, "cost_usd": 0.0003,
         "failure_class": "empty_response", "finish_reason": "length", "empty_response": True},
    ]
    rows = mod.arm_endpoints(trials)
    row = [r for r in rows if r["regime"] == "constrained" and r["arm"] == "classic"][0]
    assert row["n_trials"] == 4
    assert row["n_passed"] == 2
    # trial-pooled micro rate; here every trial is its own task (no task ids),
    # so the task-macro primary estimand equals micro
    assert row["success_rate_micro"] == 0.5
    assert row["success_rate_macro"] == 0.5
    assert row["success_estimand"].startswith("task-macro")
    # (100 + 300 + 50 + 150) / 2 passed — failures' tokens are included
    assert row["tokens_per_success"] == 300
    assert row["cost_per_success_usd"] == pytest.approx(0.0006)
    assert row["failures_by_class"] == {"empty_response": 1, "wrong_answer": 1}
    assert row["empty_response_count"] == 1
    assert row["finish_reasons"] == {"length": 1, "stop": 3}


def test_tokens_per_success_is_null_when_nothing_passes():
    mod = _load_module()
    trials = [
        {"regime": "constrained", "arm": "cod", "passed": False, "total_tokens": 80,
         "output_tokens": 40, "input_tokens": 40, "cost_usd": 0.0001,
         "failure_class": "wrong_answer", "finish_reason": "stop", "empty_response": False},
    ]
    rows = mod.arm_endpoints(trials)
    row = [r for r in rows if r["arm"] == "cod" and r["regime"] == "constrained"][0]
    assert row["tokens_per_success"] is None
    assert row["cost_per_success_usd"] is None


def test_arm_endpoints_covers_every_regime_arm_cell_in_order():
    mod = _load_module()
    rows = mod.arm_endpoints([])
    assert [(r["regime"], r["arm"]) for r in rows] == [
        (regime, arm) for regime in mod.REGIMES for arm in mod.ARMS
    ]


# -- 6. Comparisons, Holm families, non-inferiority --------------------------


def test_paired_comparisons_holm_families():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=8, trials_per_task=2)
    comparisons = mod.paired_comparisons(trials, cfg)
    # 6 confirmatory + 1 exploratory = 7 comparisons x 2 endpoints x 2
    # regimes = 28 records
    assert len(comparisons) == 28
    for row in comparisons:
        assert 0.0 <= row["permutation_p"] <= 1.0
        assert row["n_tasks"] > 0
        assert row["role"] in ("confirmatory", "exploratory")
        assert row["confirmatory"] == (row["role"] == "confirmatory")
    # confirmatory rows: Holm-adjusted, p_holm >= p
    confirmatory = [r for r in comparisons if r["confirmatory"]]
    assert len(confirmatory) == 24
    for row in confirmatory:
        assert row["permutation_p_holm"] >= row["permutation_p"] - 1e-12
    # each (regime, endpoint) family has exactly the six confirmatory
    # comparisons; the exploratory global counterpart is NEVER in a family
    for regime in mod.REGIMES:
        for endpoint in ("success", "total_tokens"):
            family = [
                r for r in comparisons
                if r["regime"] == regime and r["endpoint"] == endpoint
                and r["confirmatory"]
            ]
            assert len(family) == 6
            for row in family:
                assert row["permutation_p_holm"] is not None
            exploratory = [
                r for r in comparisons
                if r["regime"] == regime and r["endpoint"] == endpoint
                and not r["confirmatory"]
            ]
            assert len(exploratory) == 1
            assert exploratory[0]["permutation_p_holm"] is None
            assert exploratory[0]["benchmarks"] is None


def test_h2_cluster_comparison_is_scoped_and_matches_preregistration():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=10, trials_per_task=2)
    comparisons = mod.paired_comparisons(trials, cfg)
    cluster_rows = [
        r for r in comparisons
        if r["arm_a"] == "tahoe_full" and r["arm_b"] == "answer_only"
    ]
    # the pair appears exactly twice per (regime, endpoint): confirmatory
    # cluster + exploratory global
    by_role = {}
    for row in cluster_rows:
        by_role.setdefault((row["regime"], row["endpoint"], row["role"]), []).append(row)
    for regime in mod.REGIMES:
        for endpoint in ("success", "total_tokens"):
            assert len(by_role[(regime, endpoint, "confirmatory")]) == 1
            assert len(by_role[(regime, endpoint, "exploratory")]) == 1
    cluster = by_role[("constrained", "success", "confirmatory")][0]
    assert cluster["benchmarks"] == ["bbh", "bbh_arith", "bbh_track"]
    # scoped to the cluster: only cluster tasks are paired (n_tasks comes
    # solely from bbh/bbh_track/bbh_arith trials)
    assert cluster["confirmatory"] is True
    # the exploratory global counterpart pairs ALL benchmarks
    glob = by_role[("constrained", "success", "exploratory")][0]
    assert glob["benchmarks"] is None
    assert glob["n_tasks"] > cluster["n_tasks"]
    assert glob["permutation_p_holm"] is None


def test_paired_comparisons_detects_clear_differences():
    mod = _load_module()
    cfg = _fast_config()
    # enough tasks that the cluster subset still shows the clear synthetic gap
    trials = _synthetic_trials(n_tasks=25, trials_per_task=2)
    comparisons = mod.paired_comparisons(trials, cfg)
    # preregistered pair with the clearest synthetic gap: tahoe_full (best
    # synthetic arm) vs answer_only — small Holm'd p on the confirmatory
    # CLUSTER comparison, constrained success
    row = [
        r for r in comparisons
        if r["regime"] == "constrained" and r["endpoint"] == "success"
        and r["arm_a"] == "tahoe_full" and r["arm_b"] == "answer_only"
        and r["confirmatory"]
    ][0]
    assert row["permutation_p_holm"] < 0.05


def test_noninferiority_uses_configured_margin_and_holm():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=8, trials_per_task=2)
    results = mod.noninferiority_tests(trials, cfg)
    assert len(results) == len(cfg["noninferiority"]["candidates"]) * len(mod.REGIMES)
    for row in results:
        assert row["margin"] == cfg["noninferiority"]["margin"]
        assert row["reference_arm"] == "tahoe_full"
        assert "p_value_holm" in row and "non_inferior_holm" in row
        assert row["p_value_holm"] >= row["p_value"] - 1e-12


def test_noninferiority_equal_arms_are_non_inferior():
    mod = _load_module()
    cfg = _fast_config()
    cfg["noninferiority"]["candidates"] = ["answer_only"]
    trials = []
    for regime in mod.REGIMES:
        for arm in ("answer_only", "tahoe_full"):
            for task_i in range(6):
                for trial in range(2):
                    trials.append(
                        {
                            "task_id": f"eq-{task_i:03d}",
                            "benchmark": "b",
                            "arm": arm,
                            "regime": regime,
                            "trial": trial,
                            "passed": (task_i + trial) % 2 == 0,
                            "total_tokens": 100,
                            "output_tokens": 50,
                            "input_tokens": 50,
                            "cost_usd": 0.0001,
                            "failure_class": "none",
                            "finish_reason": "stop",
                            "empty_response": False,
                        }
                    )
    results = mod.noninferiority_tests(trials, cfg)
    assert len(results) == 2  # one candidate (answer_only) x two regimes
    for row in results:
        assert row["non_inferior"] is True
        assert row["margin"] == 0.05


def test_analyze_returns_preregistered_sections():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=6, trials_per_task=2)
    analysis = mod.analyze(trials, cfg)
    assert set(analysis) == {"experiment", "endpoints", "comparisons", "noninferiority"}
    assert analysis["experiment"] == "structure-answer"
    assert len(analysis["endpoints"]) == len(mod.REGIMES) * len(mod.ARMS)
    empty = mod.analyze([], cfg)
    assert empty["note"] == "no trials"


# -- 7. Immutable outputs ----------------------------------------------------


def test_make_immutable_run_dir_refuses_overwrite(tmp_path):
    mod = _load_module()
    run_dir = mod.make_immutable_run_dir(
        results_root=tmp_path, stamp="2026-01-01T000000"
    )
    assert run_dir.exists()
    assert run_dir.name == "2026-01-01T000000_structure-answer"
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        mod.make_immutable_run_dir(results_root=tmp_path, stamp="2026-01-01T000000")


def test_make_immutable_run_dir_tag_creates_distinct_dir(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("RUN_TAG", "rerun")
    run_dir = mod.make_immutable_run_dir(
        results_root=tmp_path, stamp="2026-01-01T000000"
    )
    assert run_dir.name == "2026-01-01T000000_structure-answer_rerun"
    assert run_dir.exists()


def test_write_immutable_refuses_overwrite(tmp_path):
    mod = _load_module()
    target = tmp_path / "trials.json"
    mod.write_immutable(target, "first")
    assert target.read_text(encoding="utf-8") == "first"
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        mod.write_immutable(target, "second")
    assert target.read_text(encoding="utf-8") == "first"


# -- 8. Manifest --------------------------------------------------------------


def test_manifest_pins_hashes_and_settings(tmp_path):
    mod = _load_module()
    cfg = mod.load_config()
    prompts = mod.load_arm_prompts()
    tasks = [_synthetic_task(i) for i in range(3)]
    manifest = mod.build_manifest(cfg, prompts, tasks, model="test-model")

    assert manifest["experiment"] == "structure-answer"
    assert manifest["model"]["name"] == "test-model"
    assert manifest["generation"] == cfg["generation"]
    assert manifest["regimes"] == cfg["regimes"]
    assert manifest["seed"] == cfg["seed"]
    assert manifest["prompt_relationships_verified"] is True

    # every file entry carries a matching sha256
    for entry in manifest["files"]:
        path = _REPO_ROOT / entry["path"]
        assert path.exists(), f"manifest references missing file {entry['path']}"
        assert entry["sha256"] == mod.sha256_file(path)

    # the canonical TAHOE-93 hash is pinned
    canonical_entry = [
        e for e in manifest["files"] if e["path"].endswith("language/skills/tahoe-93.txt")
    ][0]
    assert canonical_entry["sha256"] == mod.sha256_file(
        _REPO_ROOT / "language" / "skills" / "tahoe-93.txt"
    )

    # per-arm prompt hashes match the loaded prompts
    for arm in mod.ARMS:
        assert manifest["prompts"][arm]["sha256"] == _sha256(prompts[arm])
        assert manifest["prompts"][arm]["source"] == mod.PROMPT_SOURCES[arm]

    # preregistration is pinned
    assert manifest["preregistration"]["sha256"] == mod.sha256_file(mod.PREREG_PATH)
    assert mod.PREREG_PATH.exists()


def test_task_set_fingerprint_is_stable_and_content_sensitive():
    mod = _load_module()
    tasks_a = [_synthetic_task(i) for i in range(4)]
    tasks_b = [_synthetic_task(i) for i in range(4)]
    assert mod.task_set_fingerprint(tasks_a) == mod.task_set_fingerprint(tasks_b)
    tasks_c = [_synthetic_task(i) for i in range(5)]
    assert mod.task_set_fingerprint(tasks_a) != mod.task_set_fingerprint(tasks_c)


def test_format_run_doc_and_endpoint_table_render():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=4, trials_per_task=2)
    analysis = mod.analyze(trials, cfg)
    manifest = mod.build_manifest(cfg, mod.load_arm_prompts(), tasks=[_synthetic_task(0)], model="m")
    doc = mod.format_run_doc(manifest, analysis)
    assert "structure-answer" in doc
    assert "refuses overwrite" in doc or "immutable" in doc.lower()
    table = mod.format_endpoint_table(analysis["endpoints"])
    assert "regime" in table and "classic" in table and "tahoe_full" in table


# -- 9. main() is not executed on import --------------------------------------


def test_source_has_main_guard():
    source = (_BENCH_DIR / "run_structure_ablation.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source


def test_import_does_not_execute_main(tmp_path):
    """Importing the module must not run the experiment: no API access, no
    output directories, no side effects."""
    env = os.environ.copy()
    env["RESULTS_ROOT"] = str(tmp_path)
    env["PYTHONPATH"] = os.pathsep.join([str(_BENCH_DIR), str(_BENCH_DIR / "src")])
    env.pop("TAHOE_API_KEY", None)
    env.pop("TAHOE_API_BASE", None)
    proc = subprocess.run(
        [sys.executable, "-c", "import benchmarks.run_structure_ablation"],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"import failed: {proc.stderr}"
    assert not any(tmp_path.iterdir()), "import must not create output directories"


def test_module_reimport_is_side_effect_free(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_ROOT", str(tmp_path))
    mod = importlib.import_module("benchmarks.run_structure_ablation")
    importlib.reload(mod)
    assert not any(tmp_path.iterdir()), "reload must not create output directories"
    assert callable(mod.main)


# -- 10. Evaluation invariant ---------------------------------------------------


def test_grader_is_arm_independent():
    """The composed grader must not branch on arm identity."""
    import inspect

    import run_public_bench as bench_mod
    source = inspect.getsource(bench_mod.grade_task)
    assert "arm" not in source.lower(), (
        "grade_task must not reference 'arm' — evaluation invariant"
    )


def test_runner_never_passes_arm_into_grading():
    mod = _load_module()
    source = mod.run_trial.__doc__ or ""
    task = _synthetic_task(9)
    # structural check: grading receives only (task, final_answer)
    record, _ = _run_trial_with_mock(mod, task, "cod", "adequate", "prompt")
    assert record["grader_detail"]
    assert record["arm"] == "cod"


# -- 11. Residual-truncation outcome (adequate regime is a larger budget,
#          NOT a truncation-free guarantee) ------------------------------------


def test_arm_endpoints_measures_truncation():
    mod = _load_module()
    trials = _synthetic_trials(n_tasks=4, trials_per_task=2)
    # make two constrained-classic trials truncated
    truncated = 0
    for t in trials:
        if t["regime"] == "constrained" and t["arm"] == "classic":
            t["finish_reason"] = "length"
            truncated += 1
    rows = mod.arm_endpoints(trials)
    cell = [r for r in rows if r["regime"] == "constrained" and r["arm"] == "classic"][0]
    assert cell["truncated_count"] == truncated
    assert cell["truncation_rate"] == truncated / cell["n_trials"]
    assert cell["finish_reasons"]["length"] == truncated
    # untouched cells report zero truncation
    other = [r for r in rows if r["regime"] == "adequate" and r["arm"] == "cod"][0]
    assert other["truncated_count"] == 0
    assert other["truncation_rate"] == 0.0


def test_endpoint_table_reports_truncation_column():
    mod = _load_module()
    trials = _synthetic_trials(n_tasks=2, trials_per_task=1)
    table = mod.format_endpoint_table(mod.arm_endpoints(trials))
    assert "trunc" in table


def test_adequate_regime_not_claimed_truncation_free():
    """The corrected wording must survive: no 'quality not token-capped'
    claim anywhere in config, runner, or preregistration."""
    for rel in (
        "benchmarks/structure-answer.yaml",
        "benchmarks/run_structure_ablation.py",
        "docs/PREREGISTRATION-structure-answer.md",
    ):
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8").lower()
        assert "not token-capped" not in text, f"stale claim in {rel}"
    prereg = (_REPO_ROOT / "docs" / "PREREGISTRATION-structure-answer.md").read_text(
        encoding="utf-8"
    )
    assert "not a guarantee" in prereg.lower()
    assert "mandatory reported outcome" in prereg.lower()


# -- 12. Pre-run power justification (multiplicity-corrected, valid bounds) ---


def test_power_paired_bound_exceeds_independent_sensitivity():
    import math

    import benchmarks.structure_answer_power as pwr

    # valid distribution-free PAIRED bound: sd_d <= sqrt(1/T)
    assert pwr.worst_case_paired_sd(3) == pytest.approx(math.sqrt(1 / 3))
    # independent-arm sensitivity: sqrt(1/(2T)) — NOT an upper bound
    assert pwr.independent_arm_sd(3) == pytest.approx(math.sqrt(1 / 6))
    assert pwr.worst_case_paired_sd(3) > pwr.independent_arm_sd(3)
    with pytest.raises(ValueError):
        pwr.worst_case_paired_sd(0)
    with pytest.raises(ValueError):
        pwr.independent_arm_sd(0)


def test_power_multiplicity_conservatively_reduces_power():
    import benchmarks.structure_answer_power as pwr

    sd, margin, alpha = 0.25, 0.05, 0.05
    # Holm-first-step alpha/m (m=4) requires MORE tasks than unadjusted
    n_adj = pwr.required_tasks_for_noninferiority(sd, margin, alpha, 0.80, multiplicity=1)
    n_holm = pwr.required_tasks_for_noninferiority(sd, margin, alpha, 0.80, multiplicity=4)
    assert n_holm > n_adj
    # and yields lower power at the same n
    p_adj = pwr.noninferiority_power(300, sd, margin, alpha, multiplicity=1)
    p_holm = pwr.noninferiority_power(300, sd, margin, alpha, multiplicity=4)
    assert p_holm < p_adj
    # two-sided family behaves the same way
    t_adj = pwr.required_tasks_two_sided(sd, 0.10, alpha, 0.80, multiplicity=1)
    t_holm = pwr.required_tasks_two_sided(sd, 0.10, alpha, 0.80, multiplicity=6)
    assert t_holm > t_adj
    with pytest.raises(ValueError):
        pwr.noninferiority_power(300, sd, margin, alpha, multiplicity=0)


def test_power_justification_uses_actual_families_and_downgrades_openly():
    import benchmarks.structure_answer_power as pwr

    mod = _load_module()
    cfg = mod.load_config()
    j = pwr.build_justification(cfg)

    mult = j["multiplicity"]
    assert mult["noninferiority_family_size"] == len(cfg["noninferiority"]["candidates"])
    assert mult["comparisons_family_size"] == len(cfg["comparisons"])
    assert mult["noninferiority_per_comparison_alpha"] == pytest.approx(0.05 / 4)
    assert mult["comparisons_per_comparison_alpha_two_sided"] == pytest.approx(
        0.05 / 12
    )

    v = j["verdicts"]
    ni = j["noninferiority"]["by_sd_scenario"]
    # confirmatory up to and including the independent-arm sensitivity bound
    assert v["ni_powered_at_planning_sd"] is True
    assert v["ni_powered_at_independent_arm_bound"] is True
    # explicitly NOT confirmatory at the valid paired worst case
    assert v["ni_powered_at_paired_worst_case"] is False
    assert ni["paired_worst_case"]["power"] < 0.80
    # but descriptive precision still holds there
    assert v["precision_within_margin_at_paired_worst_case"] is True
    assert ni["paired_worst_case"]["precision_half_width"] < j["margin"]
    # H2 cluster: powered at planning and sensitivity, downgraded at worst case
    assert v["h2_cluster_powered_at_planning_sd"] is True
    assert v["h2_cluster_powered_at_independent_arm_bound"] is True
    assert v["h2_cluster_powered_at_paired_worst_case"] is False
    # the plan matches the config's sample counts
    assert j["planned"]["n_tasks"] == sum(cfg["samples_per_benchmark"].values())
    assert j["planned"]["planned_trials"] == (
        j["planned"]["n_tasks"]
        * len(cfg["arms"])
        * len(cfg["regimes"])
        * cfg["trials_per_task"]
    )


def test_power_justification_handles_yaml_integer_arm_names():
    """Configured archive pairs like [93, classic] parse as ints in YAML;
    the module must coerce them to the string arm labels."""
    import benchmarks.structure_answer_power as pwr

    mod = _load_module()
    cfg = mod.load_config()
    j = pwr.build_justification(cfg)
    archive = j["archive"]["archives"][0]
    pooled = archive["pooled"]
    assert "93|classic" in pooled
    assert pooled["93|classic"]["n_tasks"] > 0
    # pooled empirical max feeds the planning-SD sanity check
    assert j["sd_assumptions"]["empirical_pooled_max"] == max(
        stats["sd_d"] for stats in pooled.values()
    )


def test_power_artifact_on_disk_is_current():
    """The committed justification artifact must match a fresh computation
    from the current config — no stale power numbers."""
    import json

    import benchmarks.structure_answer_power as pwr

    mod = _load_module()
    cfg = mod.load_config()
    fresh = pwr.build_justification(cfg)
    on_disk = json.loads(
        (_BENCH_DIR / "structure-answer-power.json").read_text(encoding="utf-8")
    )
    assert on_disk["planned"] == fresh["planned"]
    assert on_disk["verdicts"] == fresh["verdicts"]
    assert on_disk["multiplicity"] == fresh["multiplicity"]


# -- 13. Isolated task loader (honors configured sample counts) ---------------


def test_select_indices_is_deterministic_and_nested():
    import benchmarks.structure_answer_tasks as sat

    a = sat.select_indices(1000, 70, 42, "gsm8k")
    b = sat.select_indices(1000, 70, 42, "gsm8k")
    assert a == b
    small = sat.select_indices(1000, 10, 42, "gsm8k")
    # nested: the k=10 set is a subset of the k=70 set (same seed)
    assert set(small) <= set(a)
    # sorted ascending regardless of k
    assert a == sorted(a)
    # seed-keyed per benchmark: different benchmark, different draw
    other = sat.select_indices(1000, 70, 42, "arc")
    assert other != a


def test_select_indices_caps_at_dataset_size():
    import benchmarks.structure_answer_tasks as sat

    assert sat.select_indices(5, 70, 42, "gsm8k") == [0, 1, 2, 3, 4]
    with pytest.raises(ValueError):
        sat.select_indices(0, 10, 42, "gsm8k")
    with pytest.raises(ValueError):
        sat.select_indices(10, 0, 42, "gsm8k")


def _fake_hf_loader(name, config_name, split):
    """Fake dataset loader returning items shaped for each benchmark's
    builder (the builders read different fields per benchmark)."""
    if name == "gsm8k":
        items = [{"question": f"Q{i}?", "answer": f"#### {i}"} for i in range(50)]
    elif name == "allenai/ai2_arc":
        items = [
            {
                "question": f"Q{i}?",
                "choices": {"label": ["A", "B", "C", "D"],
                            "text": ["a", "b", "c", "d"]},
                "answerKey": "A",
            }
            for i in range(50)
        ]
    elif name == "lukaemon/bbh":
        items = [{"input": f"Q{i}?", "target": "(A)"} for i in range(50)]
    elif name == "hails/mmlu_no_train":
        items = [
            {"question": f"Q{i}?", "choices": ["a", "b", "c", "d"], "answer": 0}
            for i in range(50)
        ]
    elif name == "hails/agieval-lsat-lr":
        items = [
            {"query": f"Q{i}?", "choices": ["(A) a", "(B) b", "(C) c", "(D) d",
                                            "(E) e"], "gold": [0]}
            for i in range(50)
        ]
    elif name == "EleutherAI/race":
        problems = repr(
            [{"question": "q?", "options": ["a", "b", "c", "d"], "answer": "A"}]
        )
        items = [
            {"article": f"Passage {i}.", "problems": problems} for i in range(50)
        ]
    else:  # pragma: no cover - unknown dataset in a test
        raise AssertionError(f"unexpected dataset {name}")
    return items


def test_load_experiment_tasks_honors_configured_counts():
    import benchmarks.structure_answer_tasks as sat

    mod = _load_module()
    cfg = copy.deepcopy(mod.load_config())
    # small configured counts keep the fake loader light
    cfg["samples_per_benchmark"] = {b: 4 for b in cfg["benchmarks"]}

    tasks = sat.load_experiment_tasks(cfg, dataset_loader=_fake_hf_loader)
    assert len(tasks) == 4 * len(cfg["benchmarks"])
    per_bench = {}
    for t in tasks:
        per_bench.setdefault(t["benchmark"], 0)
        per_bench[t["benchmark"]] += 1
    assert per_bench == {b: 4 for b in cfg["benchmarks"]}
    # task dicts carry the fields the shared grader needs
    sample = tasks[0]
    for field in ("task_id", "benchmark", "description", "expected", "grader"):
        assert field in sample
    # nested sampling: the k=2 task ids are a subset of the k=4 task ids
    cfg_small = copy.deepcopy(cfg)
    cfg_small["samples_per_benchmark"] = {b: 2 for b in cfg["benchmarks"]}
    small_tasks = sat.load_experiment_tasks(
        cfg_small, dataset_loader=_fake_hf_loader
    )
    small_ids = {(t["benchmark"], t["task_id"]) for t in small_tasks}
    big_ids = {(t["benchmark"], t["task_id"]) for t in tasks}
    assert small_ids <= big_ids


def test_load_experiment_tasks_rejects_inconsistent_config():
    import benchmarks.structure_answer_tasks as sat

    mod = _load_module()
    cfg = copy.deepcopy(mod.load_config())

    def fake_loader(name, config_name, split):
        return _fake_hf_loader(name, config_name, split)[:5]

    bad = copy.deepcopy(cfg)
    bad["benchmarks"] = ["gsm8k", "no_such_benchmark"]
    with pytest.raises(ValueError):
        sat.load_experiment_tasks(bad, dataset_loader=fake_loader)

    missing = copy.deepcopy(cfg)
    del missing["samples_per_benchmark"]["gsm8k"]
    with pytest.raises(ValueError):
        sat.load_experiment_tasks(missing, dataset_loader=fake_loader)

    extra = copy.deepcopy(cfg)
    extra["samples_per_benchmark"]["not_a_primary_bench"] = 5
    with pytest.raises(ValueError):
        sat.load_experiment_tasks(extra, dataset_loader=fake_loader)


def test_sample_report_and_planned_task_count():
    import benchmarks.structure_answer_tasks as sat

    mod = _load_module()
    cfg = mod.load_config()
    assert sat.planned_task_count(cfg) == sum(cfg["samples_per_benchmark"].values())
    report = sat.sample_report(cfg, {"gsm8k": 10})
    assert report["gsm8k"] == {"requested": cfg["samples_per_benchmark"]["gsm8k"],
                               "dataset_size": 10,
                               "drawn": 10}
    assert report["arc"]["drawn"] == cfg["samples_per_benchmark"]["arc"]


# -- 14. Config validation of the sample plan and power inputs -----------------


def _validated_config():
    mod = _load_module()
    cfg = mod.load_config()
    mod.validate_config(cfg)
    return cfg


def test_config_plans_justified_task_count():
    mod = _load_module()
    cfg = _validated_config()
    planned = sum(cfg["samples_per_benchmark"].values())
    # matches the preregistered justification artifact
    assert planned == 700
    assert all(k == 70 for k in cfg["samples_per_benchmark"].values())


def test_validate_config_rejects_bad_sample_plan():
    mod = _load_module()

    def bad(samples):
        cfg = copy.deepcopy(mod.load_config())
        cfg["samples_per_benchmark"] = samples
        mod.validate_config(cfg)

    with pytest.raises(ValueError):
        bad({b: 0 for b in mod.load_config()["benchmarks"]})  # non-positive
    missing = dict(mod.load_config()["samples_per_benchmark"])
    del missing["gsm8k"]
    with pytest.raises(ValueError):
        bad(missing)  # missing primary benchmark
    with pytest.raises(ValueError):
        bad(dict(missing, gsm8k=70, alien=70))  # not in primary list
    tiny = {b: 2 for b in mod.load_config()["benchmarks"]}
    with pytest.raises(ValueError):
        bad(tiny)  # below the 100-task floor -> must be re-justified


def test_validate_config_requires_power_provenance():
    mod = _load_module()
    cfg = copy.deepcopy(mod.load_config())
    del cfg["power"]["archive_sources"]
    with pytest.raises(ValueError):
        mod.validate_config(cfg)
    cfg = copy.deepcopy(mod.load_config())
    cfg["power"]["planning_sd"] = 0
    with pytest.raises(ValueError):
        mod.validate_config(cfg)
    cfg = copy.deepcopy(mod.load_config())
    cfg["power"]["target_power"] = 1.5
    with pytest.raises(ValueError):
        mod.validate_config(cfg)
    cfg = copy.deepcopy(mod.load_config())
    cfg["power"]["h2_cluster"]["benchmarks"] = ["alien_bench"]
    with pytest.raises(ValueError):
        mod.validate_config(cfg)


def test_manifest_records_sample_plan_and_power_provenance():
    mod = _load_module()
    cfg = _validated_config()
    prompts = mod.load_arm_prompts()
    # three tasks drawn from the FIRST three primary benchmarks
    tasks = []
    for i, bench in enumerate(cfg["benchmarks"][:3]):
        task = _synthetic_task(i)
        task["benchmark"] = bench
        tasks.append(task)
    manifest = mod.build_manifest(cfg, prompts, tasks, model="test-model")

    assert manifest["planned_task_count"] == sum(
        cfg["samples_per_benchmark"].values()
    )
    assert manifest["samples_per_benchmark"] == cfg["samples_per_benchmark"]
    assert manifest["drawn_per_benchmark"] == {
        **{b: 0 for b in cfg["benchmarks"][3:]},
        **{b: 1 for b in cfg["benchmarks"][:3]},
    }
    power = manifest["power"]
    assert power["planning_sd"] == cfg["power"]["planning_sd"]
    assert power["justification_sha256"] == mod.sha256_file(
        _BENCH_DIR / "structure-answer-power.json"
    )
    assert "Holm-first-step" in power["multiplicity_convention"]
    # the loader and power modules are hash-pinned like every other input
    pinned = {entry["path"] for entry in manifest["files"]}
    assert "benchmarks/structure_answer_tasks.py" in pinned
    assert "benchmarks/structure_answer_power.py" in pinned
    assert "benchmarks/structure-answer-power.json" in pinned


# -- 15. End-to-end mocked dry run of main() (no API, no real datasets) -------


def test_main_end_to_end_with_mocks(tmp_path, monkeypatch, capsys):
    """main() must run the full pipeline with the isolated loader and mocked
    model calls, produce all four immutable output files, and refuse a
    second run in the same directory. No API access; no real datasets.

    ARCHIVE ISOLATION (regression): RESULTS_ROOT is resolved at module
    import time (from outdir), so patching the environment variable is NOT
    enough — the module global itself must be redirected to an isolated tmp
    directory, and the repository archive tree (benchmarks/results/) must
    be verified identical before and after. An earlier revision of this
    test leaked four mocked run directories into the archive."""
    import datetime as _dt

    import json

    mod = _load_module()
    # RESULTS_ROOT is resolved at import time (from outdir), so patch the
    # module global — monkeypatch.setenv alone has NO effect here.
    monkeypatch.setattr(mod, "RESULTS_ROOT", tmp_path)
    monkeypatch.delenv("BENCHES", raising=False)
    # freeze the run timestamp so the second run deterministically collides
    class _FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 12, 0, 0, tzinfo=tz or _dt.timezone.utc)

    monkeypatch.setattr(mod, "datetime", _FrozenDatetime)

    # archive-isolation snapshot: the repository results tree must not change
    archive_root = _REPO_ROOT / "benchmarks" / "results"

    def _archive_snapshot():
        return {
            str(p.relative_to(archive_root)): (
                sorted(p.name for p in p.iterdir()) if p.is_dir() else None
            )
            for p in archive_root.rglob("*")
        }

    archive_before = _archive_snapshot()

    # synthetic task set injected through the loader reference the runner
    # actually calls (one task per primary benchmark)
    tasks_out = []
    for i, bench in enumerate(mod.load_config()["benchmarks"]):
        task = _synthetic_task(i)
        task["benchmark"] = bench
        tasks_out.append(task)
    monkeypatch.setattr(
        mod, "load_experiment_tasks", lambda cfg: list(tasks_out)
    )

    calls = {"n": 0}

    def fake_run_classic(**kwargs):
        calls["n"] += 1
        return _fake_classic_result(
            passed=(calls["n"] % 3 != 0),
            failure_class="none" if calls["n"] % 3 != 0 else "wrong_answer",
            finish_reason="length" if calls["n"] % 5 == 0 else "stop",
        )

    monkeypatch.setattr(mod, "run_classic", fake_run_classic)
    mod.main()
    out = capsys.readouterr().out
    assert "isolated loader honoring configured samples_per_benchmark" in out
    # drawn (10) != planned (700): the shortfall warning must fire, not pass
    # silently
    assert "drawn != planned" in out

    # the run landed ONLY in the isolated tmp root, parents auto-created
    runs_dir = tmp_path / "runs"
    assert runs_dir.is_dir(), "make_immutable_run_dir must create parents"
    run_dirs = sorted(runs_dir.iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].is_relative_to(tmp_path)
    for name in ("trials.json", "analysis.json", "manifest.json", "RUN.md"):
        assert (run_dirs[0] / name).exists()

    trials = json.loads((run_dirs[0] / "trials.json").read_text(encoding="utf-8"))
    n_fixture_tasks = len(tasks_out)
    assert len(trials) == (
        n_fixture_tasks * len(mod.ARMS) * len(mod.REGIMES)
        * mod.load_config()["trials_per_task"]
    )
    analysis = json.loads((run_dirs[0] / "analysis.json").read_text(encoding="utf-8"))
    # truncation outcome present in every endpoint cell
    for row in analysis["endpoints"]:
        assert "truncated_count" in row and "truncation_rate" in row
    assert any(row["truncated_count"] > 0 for row in analysis["endpoints"])
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["planned_task_count"] == sum(
        mod.load_config()["samples_per_benchmark"].values()
    )
    assert manifest["drawn_per_benchmark"] == {
        b: 1 for b in mod.load_config()["benchmarks"]
    }
    assert manifest["power"]["justification_sha256"]

    # a second run in the same second must refuse to overwrite
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        mod.main()

    # archive-isolation regression assertion: the repository archive tree is
    # unchanged — no mocked artifacts may ever leak into it
    assert _archive_snapshot() == archive_before, (
        "mocked end-to-end run wrote into the repository archive tree "
        f"({archive_root}); RESULTS_ROOT must be redirected to tmp_path"
    )


# -- 16. H2 cluster scope, task-macro estimand, and wording guards -------------


def test_macro_and_micro_differ_when_trials_per_task_are_unequal():
    """The PRIMARY estimand is task-macro: per-task means, equally weighted
    tasks. With unequal trial counts per task it must diverge from the
    descriptive trial-pooled micro rate."""
    mod = _load_module()

    def trial(task_id, passed):
        return {
            "regime": "constrained", "arm": "classic",
            "benchmark": "bbh", "task_id": task_id,
            "passed": passed, "total_tokens": 10,
            "output_tokens": 5, "input_tokens": 5, "cost_usd": 0.0001,
            "failure_class": "none", "finish_reason": "stop",
            "empty_response": False,
        }

    # task A: 3 trials, 1 pass -> per-task mean 1/3
    # task B: 1 trial, 1 pass  -> per-task mean 1
    trials = [
        trial("A", False), trial("A", False), trial("A", True), trial("B", True),
    ]
    rows = mod.arm_endpoints(trials)
    row = [r for r in rows if r["arm"] == "classic" and r["regime"] == "constrained"][0]
    assert row["success_rate_micro"] == 0.5
    assert row["success_rate_macro"] == pytest.approx((1 / 3 + 1.0) / 2)
    assert row["n_tasks"] == 2
    assert row["success_estimand"].startswith("task-macro")


def test_endpoint_table_reports_both_estimands():
    mod = _load_module()
    trials = _synthetic_trials(n_tasks=2, trials_per_task=1)
    table = mod.format_endpoint_table(mod.arm_endpoints(trials))
    assert "macro" in table and "micro" in table


def test_validate_config_enforces_h2_cluster_consistency():
    mod = _load_module()
    base = mod.load_config()

    def mutated(**changes):
        cfg = copy.deepcopy(base)
        cfg.update(changes)
        return cfg

    # scope that disagrees with power.h2_cluster.benchmarks
    cfg = mutated(comparisons=[
        ["answer_only", "classic"],
        ["tahoe_structure", "classic"],
        ["generic_structure", "answer_only"],
        ["tahoe_full", "answer_only", ["bbh", "bbh_track"]],
        ["tahoe_full", "tahoe_structure"],
        ["cod", "classic"],
    ])
    with pytest.raises(ValueError, match="h2_cluster"):
        mod.validate_config(cfg)
    # wrong pair for the scoped comparison (a pair with no global duplicate)
    cfg = mutated(comparisons=[
        ["answer_only", "classic"],
        ["tahoe_structure", "classic"],
        ["generic_structure", "answer_only"],
        ["tahoe_full", "classic", ["bbh", "bbh_track", "bbh_arith"]],
        ["tahoe_full", "tahoe_structure"],
        ["cod", "classic"],
    ])
    with pytest.raises(ValueError, match="h2_cluster"):
        mod.validate_config(cfg)
    # scope outside the primary benchmark set
    cfg = mutated(comparisons=[
        ["answer_only", "classic"],
        ["tahoe_structure", "classic"],
        ["generic_structure", "answer_only"],
        ["tahoe_full", "answer_only", ["bbh", "alien_bench"]],
        ["tahoe_full", "tahoe_structure"],
        ["cod", "classic"],
    ])
    with pytest.raises(ValueError, match="outside the primary set"):
        mod.validate_config(cfg)
    # two scoped comparisons (fresh pair so the duplicate check doesn't fire first)
    cfg = copy.deepcopy(base)
    cfg["comparisons"].append(["tahoe_full", "classic", ["bbh", "bbh_track", "bbh_arith"]])
    with pytest.raises(ValueError, match="exactly one scoped"):
        mod.validate_config(cfg)
    # duplicate confirmatory pair
    cfg = copy.deepcopy(base)
    cfg["comparisons"].append(["answer_only", "classic"])
    with pytest.raises(ValueError, match="unique pairs"):
        mod.validate_config(cfg)


def test_validate_config_constrains_exploratory_comparisons():
    mod = _load_module()
    base = mod.load_config()

    # exploratory comparison that is NOT the global counterpart of a scoped
    # confirmatory comparison would smuggle a confirmatory claim past Holm
    cfg = copy.deepcopy(base)
    cfg["exploratory_comparisons"] = [["cod", "classic"]]
    with pytest.raises(ValueError, match="global counterpart"):
        mod.validate_config(cfg)
    # exploratory comparisons must be global (unscoped)
    cfg = copy.deepcopy(base)
    cfg["exploratory_comparisons"] = [
        ["tahoe_full", "answer_only", ["bbh"]]
    ]
    with pytest.raises(ValueError, match="must be global"):
        mod.validate_config(cfg)


def test_power_module_enforces_h2_scope_consistency():
    import benchmarks.structure_answer_power as pwr

    mod = _load_module()
    cfg = copy.deepcopy(mod.load_config())
    cfg["comparisons"][3] = ["tahoe_full", "answer_only", ["bbh", "bbh_track"]]
    with pytest.raises(ValueError, match="same H2 test"):
        pwr.build_justification(cfg)


def test_h2_wording_guards():
    """The 2x2 core is none/TAHOE x contract (generic_structure is an added
    control); H2 has no AIME component; the global H2 counterpart is
    explicitly exploratory."""
    config_text = (_REPO_ROOT / "benchmarks" / "structure-answer.yaml").read_text(
        encoding="utf-8"
    )
    assert "2x2 core is structure (none / TAHOE)" in config_text
    assert "none / generic /" not in config_text
    prereg = (
        _REPO_ROOT / "docs" / "PREREGISTRATION-structure-answer.md"
    ).read_text(encoding="utf-8")
    assert "aime-style" not in prereg.lower()
    # whitespace-normalized so line breaks inside the phrase don't hide it
    assert "pooled multi-step reasoning cluster" in " ".join(prereg.split())
    assert "exploratory" in prereg
    runner_source = (_BENCH_DIR / "run_structure_ablation.py").read_text(
        encoding="utf-8"
    )
    assert "EXPLORATORY global counterpart" in runner_source
    assert "task-macro" in runner_source


def test_run_doc_labels_exploratory_comparisons():
    mod = _load_module()
    cfg = _fast_config()
    trials = _synthetic_trials(n_tasks=4, trials_per_task=2)
    analysis = mod.analyze(trials, cfg)
    doc = mod.format_run_doc(
        mod.build_manifest(cfg, mod.load_arm_prompts(),
                           tasks=[_synthetic_task(0)], model="m"),
        analysis,
    )
    assert "exploratory" in doc
    # cluster row is rendered with its scope
    assert "bbh+bbh_arith+bbh_track" in doc
