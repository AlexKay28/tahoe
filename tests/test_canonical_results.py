"""Tests for benchmarks/canonical_results.py — canonical offline results.

Fast by construction: CLI runs use small resample/permutation counts.
No model evaluations happen anywhere in this module or these tests.
"""

import json
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.canonical_results import (
    ANALYSIS_SCHEMA,
    CANONICAL_JSON_NAME,
    CANONICAL_MD_NAME,
    SCHEMA,
    build_payload,
    compute_arm_metrics,
    load_input,
    main,
    render_markdown,
)

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_trials.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
FAST = ("--seed", "123", "--n-resamples", "200", "--n-permutations", "200")


def _run(inputs, out, *flags):
    return main([str(i) for i in inputs] + ["-o", str(out)] + list(flags))


def _write_input(tmp_path, name, obj):
    path = tmp_path / name
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return path


def _payload_of(tmp_path, inputs, name="out", *flags):
    out = tmp_path / name
    assert _run(inputs, out, *FAST, *flags) == 0
    return out, json.loads((out / CANONICAL_JSON_NAME).read_text(encoding="utf-8"))


# -- determinism ----------------------------------------------------------


def test_same_input_produces_identical_outputs(tmp_path):
    out1, payload1 = _payload_of(tmp_path, [FIXTURE], "run1")
    out2, _ = _payload_of(tmp_path, [FIXTURE], "run2")
    assert (out1 / CANONICAL_JSON_NAME).read_bytes() == (
        out2 / CANONICAL_JSON_NAME
    ).read_bytes()
    assert (out1 / CANONICAL_MD_NAME).read_text() == (
        out2 / CANONICAL_MD_NAME
    ).read_text()
    # No wall-clock timestamps anywhere in the payload.
    assert "generated_at" not in json.dumps(payload1)
    assert "timestamp" not in json.dumps(payload1)


def test_shuffled_input_order_independent_metrics(tmp_path):
    trials = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shuffled = list(trials)
    random.Random(7).shuffle(shuffled)
    shuffled_file = _write_input(tmp_path, "shuffled.json", shuffled)

    _, payload1 = _payload_of(tmp_path, [FIXTURE], "run1")
    _, payload2 = _payload_of(tmp_path, [shuffled_file], "run2")

    # Provenance legitimately differs (different bytes/paths); metrics must not.
    stripped1 = {k: v for k, v in payload1.items() if k != "provenance"}
    stripped2 = {k: v for k, v in payload2.items() if k != "provenance"}
    assert stripped1 == stripped2

    md1 = (tmp_path / "run1" / CANONICAL_MD_NAME).read_text()
    md2 = (tmp_path / "run2" / CANONICAL_MD_NAME).read_text()
    # Everything from the Estimands section onward is order-independent.
    assert md1.split("\n## Estimands", 1)[1] == md2.split("\n## Estimands", 1)[1]


# -- repeated trials, micro vs macro --------------------------------------


def test_repeated_trials_counted_and_averaged(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    classic = payload["overall"]["arms"]["classic"]
    assert classic["trials"] == 6
    assert classic["tasks"] == 3
    assert classic["successes"] == 3
    assert classic["micro_accuracy"] == pytest.approx(0.5)
    assert classic["macro_accuracy"] == pytest.approx(0.5)

    comparison = payload["paired_comparisons"]["canonical-fixture/classic_vs_tahoe"]
    assert comparison["n_pairs"] == 6  # every (task_id, trial) key matched
    assert comparison["n_tasks"] == 3  # repeated trials collapse to 3 clusters


def test_micro_and_macro_are_distinct_labeled_estimands(tmp_path):
    # Unequal trial counts per task: micro pools trials, macro weights tasks.
    trials = []
    for k in range(4):  # heavy task: 4 trials, only the first passes
        trials.append({
            "arm": "classic", "benchmark": "b", "task_id": "heavy", "trial": k,
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
            "passed": k == 0,
        })
    trials.append({  # light task: single trial, passes
        "arm": "classic", "benchmark": "b", "task_id": "light", "trial": 0,
        "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "passed": True,
    })
    input_file = _write_input(tmp_path, "uneven.json", trials)

    metrics = compute_arm_metrics(trials)
    assert metrics["micro_accuracy"] == pytest.approx(2 / 5)  # 0.4
    assert metrics["macro_accuracy"] == pytest.approx((0.25 + 1.0) / 2)  # 0.625
    assert metrics["micro_accuracy"] != metrics["macro_accuracy"]

    _, payload = _payload_of(tmp_path, [input_file])
    classic = payload["overall"]["arms"]["classic"]
    assert classic["micro_accuracy"] == pytest.approx(0.4)
    assert classic["macro_accuracy"] == pytest.approx(0.625)

    # The estimand glossary labels both; the Markdown never mixes them.
    assert "micro_accuracy" in payload["estimands"]
    assert "macro_accuracy" in payload["estimands"]
    md = (tmp_path / "out" / CANONICAL_MD_NAME).read_text()
    assert "micro acc (trial-pooled)" in md
    assert "macro acc (task-eq-wt)" in md


# -- token sums, ratios, spend per success ---------------------------------


def test_exact_token_sums_and_classic_vs_tahoe_ratios(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    pair = payload["overall"]["classic_vs_tahoe"]

    assert pair["token_sums"]["classic"] == {
        "input_tokens": 700, "output_tokens": 370, "total_tokens": 1070,
    }
    assert pair["token_sums"]["tahoe"] == {
        "input_tokens": 780, "output_tokens": 214, "total_tokens": 994,
    }
    ratios = pair["token_ratio_tahoe_over_classic"]
    assert ratios["input_tokens"] == pytest.approx(780 / 700)
    assert ratios["output_tokens"] == pytest.approx(214 / 370)
    assert ratios["total_tokens"] == pytest.approx(994 / 1070)

    spend = pair["total_spend_per_success"]
    assert spend["classic"] == pytest.approx(1070 / 3)  # failures included
    assert spend["tahoe"] == pytest.approx(994 / 4)


def test_zero_successes_spend_is_null_and_failures_count(tmp_path):
    trials = [
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 60, "output_tokens": 40, "total_tokens": 100,
         "passed": True},
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 1,
         "input_tokens": 30, "output_tokens": 20, "total_tokens": 50,
         "passed": False},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 50, "output_tokens": 30, "total_tokens": 80,
         "passed": False},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 1,
         "input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
         "passed": False},
    ]
    input_file = _write_input(tmp_path, "spend.json", trials)
    out, payload = _payload_of(tmp_path, [input_file])

    classic = payload["overall"]["arms"]["classic"]
    tahoe = payload["overall"]["arms"]["tahoe"]
    # Failed attempts count toward the spend: (100 + 50) / 1 == 150.
    assert classic["total_spend_per_success"] == 150
    # Zero successes means undefined, not free: JSON null, never 0.0.
    assert payload["overall"]["arms"]["tahoe"]["total_spend_per_success"] is None
    assert "null" in (out / CANONICAL_JSON_NAME).read_text()
    md = (out / CANONICAL_MD_NAME).read_text()
    tahoe_row = next(
        line for line in md.splitlines() if line.startswith("| tahoe |")
    )
    assert "—" in tahoe_row  # undefined spend rendered as null marker


# -- outcomes use actual fields only --------------------------------------


def test_exact_cap_without_finish_reason_is_not_fabricated_truncation(tmp_path):
    # A trial that exactly hits its recorded output cap, with no finish_reason
    # and no explicit flags: cap-exhausted, but NOT truncated (finish_reason
    # is never inferred) and NOT a completed response.
    cap_trial = {
        "arm": "classic", "benchmark": "b", "task_id": "at-cap", "trial": 0,
        "input_tokens": 10, "output_token_cap": 100, "output_tokens": 100,
        "total_tokens": 110, "passed": False, "final_answer": "cut at cap",
    }
    tahoe_pair = {
        "arm": "tahoe", "benchmark": "b", "task_id": "at-cap", "trial": 0,
        "input_tokens": 10, "output_tokens": 50, "total_tokens": 60,
        "passed": True, "final_answer": "fine",
    }
    input_file = _write_input(tmp_path, "cap.json", [cap_trial, tahoe_pair])
    _, payload = _payload_of(tmp_path, [input_file])

    outcomes = payload["overall"]["arms"]["classic"]["outcomes"]
    assert outcomes["cap_exhausted"]["count"] == 1
    assert outcomes["truncated"]["count"] == 0  # not fabricated from the cap
    assert outcomes["empty_response"]["count"] == 0
    assert outcomes["completed_response"]["count"] == 0
    assert outcomes["completed_response"]["accuracy"] is None

    # finish_reason actually recorded as "length" DOES count as truncation.
    # (No cap recorded on this trial, so cap-exhausted stays at zero.)
    length_trial = {
        "arm": "classic", "benchmark": "b", "task_id": "explicit-length",
        "trial": 0, "input_tokens": 10, "output_tokens": 90,
        "total_tokens": 100, "passed": False, "final_answer": "cut by length",
        "finish_reason": "length",
    }
    tahoe_length_pair = dict(tahoe_pair, task_id="explicit-length", trial=0)
    input2 = _write_input(tmp_path, "length.json",
                          [length_trial, tahoe_length_pair])
    _, payload2 = _payload_of(tmp_path, [input2], "out2")
    outcomes2 = payload2["overall"]["arms"]["classic"]["outcomes"]
    assert outcomes2["truncated"]["count"] == 1
    assert outcomes2["cap_exhausted"]["count"] == 0


def test_fixture_outcomes_use_actual_fields(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    classic = payload["overall"]["arms"]["classic"]["outcomes"]
    tahoe = payload["overall"]["arms"]["tahoe"]["outcomes"]
    # classic: one finish_reason="length" trial; tahoe: one cap hit, one empty.
    assert classic["truncated"]["count"] == 1
    assert classic["empty_response"]["count"] == 0
    assert classic["completed_response"]["count"] == 5
    assert classic["completed_response"]["accuracy"] == pytest.approx(0.4)
    assert tahoe["truncated"]["count"] == 0
    assert tahoe["cap_exhausted"]["count"] == 1
    assert tahoe["empty_response"]["count"] == 1
    assert tahoe["completed_response"]["count"] == 4
    assert tahoe["completed_response"]["accuracy"] == pytest.approx(1.0)


# -- Holm-corrected paired comparisons --------------------------------------


def test_holm_fields_present_in_comparisons(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    comparisons = payload["paired_comparisons"]
    assert comparisons, "fixture has a classic-vs-tahoe pair"
    for comp in comparisons.values():
        assert "permutation_p" in comp
        assert "permutation_p_holm" in comp
        assert "pass_rate_permutation_p_holm" in comp
        assert comp["z_test"]["p_value_holm"] is not None
        assert comp["wilcoxon"]["p_value_holm"] is not None
        # Holm-adjusted p-values never shrink below their raw values.
        assert comp["permutation_p_holm"] >= comp["permutation_p"] - 1e-12
        assert comp["z_test"]["p_value_holm"] >= (
            comp["z_test"]["p_value"] - 1e-12
        )
    assert payload["multiplicity"]["method"] == "holm"
    assert payload["multiplicity"]["family"] == "comparisons"
    md = (tmp_path / "out" / CANONICAL_MD_NAME).read_text()
    assert "Holm" in md


# -- analysis provenance: implementation identity -------------------------

# The analysis implementation pinned by analysis_provenance, as repo-relative
# paths mapped to their on-disk locations (independent of the working dir).
ANALYSIS_FILES = {
    "benchmarks/canonical_results.py": REPO_ROOT / "benchmarks/canonical_results.py",
    "benchmarks/stats.py": REPO_ROOT / "benchmarks/stats.py",
    "benchmarks/report.py": REPO_ROOT / "benchmarks/report.py",
}


def test_analysis_provenance_pins_implementation_hashes(tmp_path):
    import hashlib

    _, payload = _payload_of(tmp_path, [FIXTURE])
    analysis = payload["analysis_provenance"]

    # Every analysis file is recorded by its repo-relative path, and each
    # hash matches the actual SHA-256 of that file on disk.
    assert set(analysis["files"]) == set(ANALYSIS_FILES)
    for repo_rel, path in ANALYSIS_FILES.items():
        assert analysis["files"][repo_rel] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

    # Relevant schema/version tags are recorded.
    assert analysis["schema"] == ANALYSIS_SCHEMA
    assert analysis["payload_schema"] == SCHEMA == payload["schema"]


def test_analysis_provenance_records_options(tmp_path):
    _, payload = _payload_of(
        tmp_path, [FIXTURE], "out-opts",
        "--seed", "7", "--n-resamples", "50", "--n-permutations", "60",
    )
    analysis = payload["analysis_provenance"]
    assert analysis["seed"] == 7
    assert analysis["n_resamples"] == 50
    assert analysis["n_permutations"] == 60
    # The stats options mirror the existing provenance.stats block.
    assert analysis["seed"] == payload["provenance"]["stats"]["seed"]
    assert analysis["n_resamples"] == payload["provenance"]["stats"]["n_resamples"]
    assert analysis["n_permutations"] == (
        payload["provenance"]["stats"]["n_permutations"]
    )


def test_analysis_provenance_deterministic_and_rendered(tmp_path):
    _, payload1 = _payload_of(tmp_path, [FIXTURE], "run1")
    _, payload2 = _payload_of(tmp_path, [FIXTURE], "run2")
    # Same implementation + options: identical provenance across runs.
    assert payload1["analysis_provenance"] == payload2["analysis_provenance"]

    # The Markdown summary surfaces the pinned implementation too.
    md = (tmp_path / "run1" / CANONICAL_MD_NAME).read_text()
    assert "### Analysis implementation" in md
    for repo_rel, digest in payload1["analysis_provenance"]["files"].items():
        assert repo_rel in md
        assert digest in md
    assert "seed 123" in md


def test_analysis_provenance_independent_of_input_order(tmp_path):
    trials = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shuffled = list(trials)
    random.Random(3).shuffle(shuffled)
    shuffled_file = _write_input(tmp_path, "shuffled.json", shuffled)

    _, payload1 = _payload_of(tmp_path, [FIXTURE], "run1")
    _, payload2 = _payload_of(tmp_path, [shuffled_file], "run2")
    # Input bytes differ, but the analysis implementation does not.
    assert payload1["analysis_provenance"] == payload2["analysis_provenance"]


# -- per-task comparison scalability --------------------------------------

# The fixture has 1 benchmark-level arm comparison and 3 tasks, so a full
# run performs 1 + 3 _compare_groups calls unless per-task work is skipped.


def _count_compare_groups(monkeypatch):
    import benchmarks.canonical_results as canonical_module

    # canonical_results supports both script (``stats``) and package
    # (``benchmarks.stats``) imports. Patch the module it actually bound;
    # test collection order can make those distinct module objects.
    stats_module = sys.modules[canonical_module.generate_stats_report.__module__]
    calls = []
    original = stats_module._compare_groups

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(stats_module, "_compare_groups", spy)
    return calls


def test_canonical_default_skips_per_task_comparisons(tmp_path, monkeypatch):
    calls = _count_compare_groups(monkeypatch)
    _, payload = _payload_of(tmp_path, [FIXTURE])

    # Default emission is unchanged: no per_task block in the payload.
    assert "per_task" not in payload
    # Only the benchmark-level comparison ran; the fixture's 3 per-task
    # comparisons were skipped entirely, not computed and discarded.
    assert len(calls) == 1


def test_canonical_include_per_task_computes_and_emits_per_task(tmp_path, monkeypatch):
    calls = _count_compare_groups(monkeypatch)
    _, payload = _payload_of(tmp_path, [FIXTURE], "out-per-task",
                             "--include-per-task")

    assert set(payload["per_task"]) == {
        "canonical-fixture/t-a/classic_vs_tahoe",
        "canonical-fixture/t-b/classic_vs_tahoe",
        "canonical-fixture/t-c/classic_vs_tahoe",
    }
    entry = payload["per_task"]["canonical-fixture/t-a/classic_vs_tahoe"]
    assert entry["benchmark"] == "canonical-fixture"
    assert entry["task_id"] == "t-a"
    # 1 benchmark-level call + 3 per-task calls.
    assert len(calls) == 4


# -- grader-error outcomes ---------------------------------------------------


def _grader_trials():
    """Trials covering every failure_class flavor, one actual grader error.

    classic: grader_error / wrong_answer / none / (field absent) — only the
    literal ``failure_class="grader_error"`` trial counts. tahoe: clean.
    """
    base = {"benchmark": "b", "task_id": "t",
            "input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    trials = [
        {**base, "arm": "classic", "trial": 0, "passed": False,
         "failure_class": "grader_error"},
        {**base, "arm": "classic", "trial": 1, "passed": False,
         "failure_class": "wrong_answer"},
        {**base, "arm": "classic", "trial": 2, "passed": True,
         "failure_class": "none"},
        {**base, "arm": "classic", "trial": 3, "passed": True},  # field absent
        {**base, "arm": "tahoe", "trial": 0, "passed": True,
         "failure_class": "none"},
        {**base, "arm": "tahoe", "trial": 1, "passed": False,
         "failure_class": "assert_failed"},
    ]
    return trials


def test_compute_arm_metrics_grader_error_counted():
    metrics = compute_arm_metrics(
        [t for t in _grader_trials() if t["arm"] == "classic"]
    )
    # Only the literal failure_class="grader_error" trial counts; other
    # classes and a missing failure_class field are never grader errors.
    assert metrics["outcomes"]["grader_error"] == {"count": 1, "rate": 0.25}
    # Existing outcome fields keep their meaning and counts.
    assert metrics["trials"] == 4
    assert metrics["successes"] == 2


def test_grader_error_outcomes_in_payload_without_raw_trials(tmp_path):
    input_file = _write_input(tmp_path, "grader.json", _grader_trials())
    out, payload = _payload_of(tmp_path, [input_file])

    # Additive outcomes block per arm, overall and per benchmark.
    classic = payload["overall"]["arms"]["classic"]["outcomes"]
    tahoe = payload["overall"]["arms"]["tahoe"]["outcomes"]
    assert classic["grader_error"] == {"count": 1, "rate": 0.25}
    assert tahoe["grader_error"] == {"count": 0, "rate": 0.0}
    assert payload["benchmarks"]["b"]["arms"]["classic"]["outcomes"][
        "grader_error"
    ] == {"count": 1, "rate": 0.25}

    # Known grader-error counts are available without the huge raw-response
    # payload: raw trials stay excluded by default and no per-trial
    # failure_class values leak into the output ("grader_error" appears
    # only as the aggregate outcomes key and in its glossary entry).
    assert payload["provenance"]["include_raw_trials"] is False
    assert "raw_trials" not in payload
    raw = json.dumps(payload)
    assert "wrong_answer" not in raw
    assert "assert_failed" not in raw


def test_grader_error_outcome_zero_when_none_recorded(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    # The fixture records failure_class values (none / assert_failed /
    # empty_response) but no grader errors: zero everywhere, never inferred.
    for scope, entry in [("overall", payload["overall"])] + [
        ("b", payload["benchmarks"]["canonical-fixture"])
    ]:
        for arm in ("classic", "tahoe"):
            outcomes = (
                entry["arms"][arm]["outcomes"]
            )
            assert outcomes["grader_error"] == {"count": 0, "rate": 0.0}


def test_grader_error_column_in_markdown_arm_table(tmp_path):
    input_file = _write_input(tmp_path, "grader.json", _grader_trials())
    out, payload = _payload_of(tmp_path, [input_file])
    md = (out / CANONICAL_MD_NAME).read_text()

    # The arm table gains an additive "grader err" column, between "empty"
    # and "completed", for overall and per-benchmark tables alike.
    assert "| grader err | completed |" in md
    header = next(line for line in md.splitlines() if line.startswith("| arm |"))
    columns = [cell.strip() for cell in header.split("|")]
    assert columns.index("grader err") == columns.index("empty") + 1

    rows = [line for line in md.splitlines() if line.startswith("| classic |")]
    assert rows  # overall + one benchmark table
    for row in rows:
        cells = [cell.strip() for cell in row.split("|")]
        assert cells[columns.index("grader err")] == "1"

    tahoe_rows = [line for line in md.splitlines() if line.startswith("| tahoe |")]
    for row in tahoe_rows:
        cells = [cell.strip() for cell in row.split("|")]
        assert cells[columns.index("grader err")] == "0"


# -- overwrite refusal / raw responses -------------------------------------


def test_output_refuses_to_overwrite(tmp_path, capsys):
    out = tmp_path / "out"
    assert _run([FIXTURE], out, *FAST) == 0
    snapshot = (out / CANONICAL_JSON_NAME).read_bytes()
    listing = sorted(p.name for p in out.iterdir())

    rc = _run([FIXTURE], out, *FAST)
    assert rc != 0
    stderr = capsys.readouterr().err.lower()
    assert "exist" in stderr or "refus" in stderr
    # Existing outputs are untouched, and nothing new was added.
    assert (out / CANONICAL_JSON_NAME).read_bytes() == snapshot
    assert sorted(p.name for p in out.iterdir()) == listing

    # Refusal also applies when the target path exists as a file.
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("occupied")
    assert _run([FIXTURE], blocker, *FAST) != 0
    assert blocker.read_text() == "occupied"


def test_raw_responses_excluded_unless_requested(tmp_path):
    _, payload = _payload_of(tmp_path, [FIXTURE])
    raw = json.dumps(payload)
    # Response CONTENT is never copied by default (field names may appear
    # in the estimand glossary, so check the actual recorded texts).
    assert "ANSWER-TEXT" not in raw
    assert "raw_trials" not in payload
    assert payload["provenance"]["include_raw_trials"] is False
    assert "raw_trials" not in payload

    _, payload_raw = _payload_of(tmp_path, [FIXTURE], "out-raw",
                                 "--include-raw-trials")
    assert payload_raw["provenance"]["include_raw_trials"] is True
    assert "final_answer" in json.dumps(payload_raw["raw_trials"][0])


# -- inputs, manifests, benchmark labels -----------------------------------


def test_input_sha256_counts_and_manifest_metadata(tmp_path):
    import hashlib

    _, payload = _payload_of(tmp_path, [FIXTURE])
    recorded = payload["provenance"]["inputs"][0]
    assert recorded["sha256"] == hashlib.sha256(
        FIXTURE.read_bytes()
    ).hexdigest()
    assert recorded["trial_count"] == 12
    assert recorded["trial_counts_by_arm"] == {"classic": 6, "tahoe": 6}
    assert recorded["task_set_sha256"]  # recorded, non-empty
    assert payload["provenance"]["total_trials"] == 12

    manifest = recorded["manifest"]
    assert manifest["trial_metadata"]["model"] == ['"test-model"']
    assert manifest["trial_metadata"]["grader"] == ['"contains"']
    assert manifest["trial_metadata"]["max_tokens"] == ["1024"]
    assert set(("model", "grader", "max_tokens")) <= set(
        manifest["available_metadata_keys"]
    )


def test_default_benchmark_label_from_input_metadata(tmp_path):
    # No benchmark field on trials: dict input default wins; a bare list
    # falls back to the file stem so task identities stay unambiguous.
    trials = [
        {"arm": "classic", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True},
        {"arm": "tahoe", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True},
    ]
    dict_input = _write_input(tmp_path, "dict.json",
                              {"benchmark": "from-dict", "trials": trials,
                               "model": "manifest-model"})
    stem_input = _write_input(tmp_path, "stemme.json", trials)

    _, payload = _payload_of(tmp_path, [dict_input])
    assert "from-dict" in payload["benchmarks"]
    assert "from-dict/classic_vs_tahoe" in payload["paired_comparisons"]
    entry = payload["provenance"]["inputs"][0]
    assert entry["benchmark_default"] == "from-dict"
    assert entry["manifest"]["top_level"]["model"] == "manifest-model"

    _, payload = _payload_of(tmp_path, [stem_input], "out2")
    assert "stemme" in payload["benchmarks"]
    assert payload["provenance"]["inputs"][0]["benchmark_default"] == "stemme"


def test_load_input_rejects_incomplete_trials(tmp_path):
    bad = [{"task_id": "t", "arm": "classic"}]  # missing "trial"
    path = _write_input(tmp_path, "bad.json", bad)
    with pytest.raises(ValueError, match="trial"):
        load_input(path)
    rc = _run([path], tmp_path / "out")
    assert rc != 0
    assert not (tmp_path / "out").exists()  # nothing created on failure


# -- request_params generation snapshots ----------------------------------


def _params_trials(request_params):
    return [
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "request_params": request_params},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "request_params": request_params},
    ]


def test_request_params_generation_settings_survive(tmp_path):
    request_params = {
        "model": "glm-5.3",
        "max_tokens": 1024,
        "generation": {"temperature": 0.0, "seed": 42},
    }
    input_file = _write_input(tmp_path, "params.json",
                               _params_trials(request_params))
    _, payload = _payload_of(tmp_path, [input_file])

    entry = payload["provenance"]["inputs"][0]
    assert "request_params" in entry["manifest"]["available_metadata_keys"]
    recorded = entry["manifest"]["trial_metadata"]["request_params"]
    assert len(recorded) == 1  # both arms share one identical snapshot
    # Distinct values are recorded as sorted JSON; the full generation
    # request snapshot survives intact.
    assert json.loads(recorded[0]) == request_params


def test_request_params_secrets_never_copied(tmp_path):
    request_params = {
        "model": "glm-5.3",
        "max_tokens": 1024,
        "generation": {"api_key": "sk-nested-secret", "temperature": 0.0},
        "api_key": "sk-top-level-secret",
    }
    input_file = _write_input(tmp_path, "params.json",
                               _params_trials(request_params))
    out, payload = _payload_of(tmp_path, [input_file])

    raw = json.dumps(payload)
    # No key material ever reaches the canonical payload...
    assert "sk-nested-secret" not in raw
    assert "sk-top-level-secret" not in raw
    # ...not even the Markdown summary.
    assert "sk-nested-secret" not in (
        out / CANONICAL_MD_NAME
    ).read_text()
    # The generation settings that matter still survive, masked alongside.
    recorded = json.loads(
        payload["provenance"]["inputs"][0]["manifest"]["trial_metadata"]
        ["request_params"][0]
    )
    assert recorded["model"] == "glm-5.3"
    assert recorded["max_tokens"] == 1024
    assert recorded["generation"] == {
        "api_key": "[redacted]", "temperature": 0.0,
    }
    assert recorded["api_key"] == "[redacted]"