#!/usr/bin/env python3
"""Preregistered TAHOE-structure x answer-only factorial experiment.

STATUS: PREPARED, NOT RUN. This module is an isolated, preregistered
experiment; it never runs on import. Launch it explicitly with:

    PYTHONPATH=src python3 benchmarks/run_structure_ablation.py

Preregistration: docs/PREREGISTRATION-structure-answer.md
Configuration:    benchmarks/structure-answer.yaml
Prompt artifacts: benchmarks/prompts/structure-answer/
Task loader:      benchmarks/structure_answer_tasks.py (honors configured
                  per-benchmark sample counts; run_public_bench untouched)
Power analysis:   benchmarks/structure_answer_power.py
                  (artifact: benchmarks/structure-answer-power.json)

Research question: is TAHOE-93's measured benefit caused by its STRUCTURE
(the typed-ref reasoning scaffold) or by its final answer-only OUTPUT
CONTRACT? A factorial design crossed with two output-budget regimes separates
the two factors. Confirmatory strength is calibrated, not assumed: the
700-task plan (70 per benchmark, 25,200 planned trials) supports Holm-
corrected confirmatory claims — computed at the Bonferroni/Holm-first-step
per-comparison alpha of the actual multiplicity families — for every paired
task-difference SD up to and including the independent-arm sensitivity bound
sqrt(1/(2*3)) = 0.408 (>= 80% one-sided power for the 0.05 non-inferiority
margin, >= 80% two-sided power for the pooled H2 bbh-family cluster at
delta = 0.10). The valid distribution-free PAIRED worst case sqrt(1/3) =
0.577 (perfectly anti-correlated arm outcomes) is NOT covered for
non-inferiority or cluster power — a preregistered, explicit downgrade.
See benchmarks/structure-answer-power.json for the transparent calculation.

Arms (6), all differences confined to the system prompt:
  classic           — no system prompt
  answer_only       — the canonical TAHOE-93 final output-contract sentence
                      alone (verified byte-equal to answer-only.txt)
  generic_structure — TAHOE-free structured outline + the same contract
  tahoe_structure   — canonical TAHOE-93 with ONLY its final output-contract
                      sentence removed (derived in code; recomposition guard)
  tahoe_full        — canonical TAHOE-93 text, byte-exact, unmodified
  cod               — concise-CoT / Chain-of-Draft control

Regimes (2), differing only in max_tokens:
  constrained — max_tokens 256 (tight budget: truncation pressure is the
               treatment)
  adequate    — max_tokens 4096, a LARGER budget expected to make truncation
               rare but NOT a guarantee that answers are never truncated.
               Residual truncation under the adequate regime is measured per
               arm (finish_reason="length" counts and rates, empty-response
               counts) and reported as a mandatory outcome; adequate-regime
               accuracy is interpreted together with the measured truncation
               rate, never presented as truncation-free.

EVALUATION INVARIANT: the grader and answer extraction are IDENTICAL for
all arms and regimes. The ONLY difference between arms is the system prompt;
the ONLY difference between regimes is max_tokens. Grading is composed
UNMODIFIED from run_public_bench.grade_task and never branches on arm.

Primary endpoints (preregistered):
  1. fixed-budget task success — per-arm TASK-MACRO success under
     `constrained`: repeated trials are aggregated to per-task means first
     and tasks are weighted EQUALLY (success_rate_macro, the primary
     estimand, matching the paired tests). The trial-pooled micro rate is
     reported as descriptive only (success_rate_micro).
  2. adequate-budget accuracy — the same task-macro estimand under
     `adequate`.
  3. total tokens and cost per success — total_tokens / cost summed over ALL
     trials of the cell (failures included in the numerator) divided by the
     number of passed trials; reported as null when an arm passes nothing.
  4. residual truncation measurement (mandatory reported outcome) — per
     arm x regime, the count and rate of finish_reason="length" trials and
     the empty-response count. The adequate regime is a larger budget, not
     a truncation-free guarantee; accuracy claims are interpreted together
     with these measured rates.

Analysis plan (preregistered): trials are paired by exact
(benchmark, task_id, trial) identity via stats.pair_trials; repeated trials
are aggregated to per-task means (the task-macro estimand); two-sided
paired permutation tests on success and total_tokens; Holm step-down
correction within each (regime, endpoint) family over the CONFIRMATORY
comparisons; one-sided paired non-inferiority tests of each candidate arm
vs tahoe_full with an explicit quality margin, Holm-corrected within each
regime. H2 is tested on the POOLED reasoning cluster (bbh + bbh_track +
bbh_arith) via the scoped confirmatory comparison
[tahoe_full, answer_only, [bbh, bbh_track, bbh_arith]]; the same pair over
all benchmarks is a labeled EXPLORATORY global counterpart with no Holm
membership and no confirmatory standing.

Outputs: an immutable, timestamped run directory (refuses to overwrite any
existing directory or file) containing trials.json, analysis.json,
manifest.json and RUN.md. The manifest pins sha256 hashes of every prompt,
config, grader, runner and dataset artifact plus the model and generation
settings. Trial records carry the truthful outcome metadata captured by
runner_classic (finish_reason, empty_response, retries, runner-level
failure_class) — outcomes are never relabeled: a truncated or empty response
stays distinguishable from a graded wrong answer.

Host task prompt contract: task["description"] is passed through verbatim;
this experiment never edits the host task prompt or output contract. The
only intentional manipulation is the answer-only sentence in the system
prompt.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import stats
from outdir import RESULTS_ROOT
from prompt_paths import resolve_prompt

# Composed UNMODIFIED from the existing evaluation stack (read-only reuse):
# - grade_task: the arm-invariant public grader (from run_public_bench)
# - load_experiment_tasks: the isolated loader that honors the configured
#   per-benchmark sample counts (structure_answer_tasks.py; run_public_bench
#   itself is untouched)
# - run_classic: the single-call chat-completions runner with truthful
#   outcome capture (finish_reason, empty_response, retry_history, ...)
from run_public_bench import grade_task
from structure_answer_tasks import load_experiment_tasks, planned_task_count
from runner_classic import run as run_classic

# -- Experiment identity -------------------------------------------------

EXPERIMENT = "structure-answer"
CONFIG_PATH = Path(__file__).resolve().parent / "structure-answer.yaml"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "structure-answer"
ANSWER_ONLY_FILE = PROMPT_DIR / "answer-only.txt"
GENERIC_STRUCTURE_FILE = PROMPT_DIR / "generic-structure.txt"
PREREG_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "PREREGISTRATION-structure-answer.md"
)

# The arm list and regime list are mirrored here and validated against the
# config at load time, so the config cannot silently drift from the design.
ARMS = [
    "classic",
    "answer_only",
    "generic_structure",
    "tahoe_structure",
    "tahoe_full",
    "cod",
]
REGIMES = ["constrained", "adequate"]

# Arms whose system prompt must never contain TAHOE vocabulary.
TAHOE_FREE_ARMS = ("generic_structure",)

PROMPT_SOURCES = {
    "classic": "none (empty system prompt)",
    "answer_only": "canonical TAHOE-93 final output-contract sentence "
    "(benchmarks/prompts/structure-answer/answer-only.txt, verified)",
    "generic_structure": "benchmarks/prompts/structure-answer/generic-structure.txt",
    "tahoe_structure": "derived: canonical TAHOE-93 minus its final "
    "output-contract sentence only (recomposition-guarded)",
    "tahoe_full": "canonical TAHOE-93 file, byte-exact (language/skills/tahoe-93.txt)",
    "cod": "baseline cod.txt, byte-exact (language/baselines/cod.txt)",
}


# -- Prompt construction and exact-relationship guards -------------------


def load_canonical_tahoe() -> str:
    """Return the canonical TAHOE-93 text byte-exactly (no stripping)."""
    return resolve_prompt("tahoe").read_text(encoding="utf-8")


def answer_only_sentence(canonical: str) -> str:
    """The final output-contract sentence of the canonical TAHOE-93 text."""
    body = canonical.rstrip("\n")
    lines = [line for line in body.split("\n") if line.strip()]
    if not lines:
        raise ValueError("canonical TAHOE-93 text is empty")
    sentence = lines[-1].strip()
    if not sentence.startswith("Output only the answer"):
        raise ValueError(
            "canonical TAHOE-93 does not end with the expected output-contract "
            f"sentence; last line was: {sentence!r}"
        )
    return sentence


def derive_tahoe_structure(canonical: str) -> str:
    """Canonical TAHOE-93 with ONLY its final output-contract sentence removed.

    The derived text is everything before the sentence, with the blank
    separator line that preceded it dropped, so that

        derived + "\\n\\n" + sentence == canonical.rstrip("\\n")

    holds exactly. Any drift in the canonical file breaks this guard loudly
    instead of silently changing the arm.
    """
    sentence = answer_only_sentence(canonical)
    body = canonical.rstrip("\n")
    idx = body.rfind(sentence)
    if idx == -1:
        raise ValueError("output-contract sentence not found in canonical text")
    structure = body[:idx].rstrip("\n")
    if structure + "\n\n" + sentence != body:
        raise ValueError(
            "tahoe_structure derivation is not exact: recomposition mismatch"
        )
    return structure


def load_arm_prompts() -> dict[str, str]:
    """Load all six arm prompts and verify every exact relationship.

    Verified before any trial can run:
    - answer_only equals the canonical final sentence and answer-only.txt
    - tahoe_full is the canonical file text byte-exactly
    - tahoe_structure recomposes to the canonical with the contract sentence
    - generic_structure ends with the same contract sentence and contains
      no TAHOE vocabulary
    - cod is the existing baseline file byte-exactly
    """
    canonical = load_canonical_tahoe()
    sentence = answer_only_sentence(canonical)

    artifact = ANSWER_ONLY_FILE.read_text(encoding="utf-8").strip()
    if artifact != sentence:
        raise ValueError(
            "answer-only.txt drifted from the canonical TAHOE-93 output "
            f"contract sentence: artifact={artifact!r}, canonical={sentence!r}"
        )

    generic = GENERIC_STRUCTURE_FILE.read_text(encoding="utf-8")
    if not generic.rstrip("\n").endswith(sentence):
        raise ValueError("generic-structure.txt must end with the output-contract sentence")
    if "tahoe" in generic.lower():
        raise ValueError(
            "generic_structure arm must be TAHOE-free but its prompt "
            "mentions TAHOE"
        )

    cod = resolve_prompt("cod").read_text(encoding="utf-8")

    prompts = {
        "classic": "",
        "answer_only": sentence,
        "generic_structure": generic,
        "tahoe_structure": derive_tahoe_structure(canonical),
        "tahoe_full": canonical,
        "cod": cod,
    }
    verify_prompt_relationships(prompts, canonical)
    return prompts


def verify_prompt_relationships(prompts: dict[str, str], canonical: str) -> None:
    """Assert the exact pairwise relationships the design requires."""
    if set(prompts) != set(ARMS):
        raise ValueError(f"prompt arms {sorted(prompts)} != design arms {ARMS}")
    if prompts["tahoe_full"] != canonical:
        raise ValueError("tahoe_full must be the canonical TAHOE-93 text byte-exactly")
    if prompts["classic"] != "":
        raise ValueError("classic arm must use an empty system prompt")
    sentence = answer_only_sentence(canonical)
    if prompts["answer_only"] != sentence:
        raise ValueError("answer_only arm must be exactly the output-contract sentence")
    structure = prompts["tahoe_structure"]
    if structure + "\n\n" + sentence != canonical.rstrip("\n"):
        raise ValueError(
            "tahoe_structure + sentence must recompose the canonical text exactly"
        )
    if "Output only the answer" in structure:
        raise ValueError("tahoe_structure must not contain the output-contract sentence")
    if not prompts["generic_structure"].rstrip("\n").endswith(sentence):
        raise ValueError("generic_structure must end with the output-contract sentence")
    if prompts["generic_structure"] == structure:
        raise ValueError("generic_structure must differ from tahoe_structure")
    cod_text = resolve_prompt("cod").read_text(encoding="utf-8")
    if prompts["cod"] != cod_text:
        raise ValueError("cod arm must be the existing cod.txt baseline byte-exactly")


# -- Configuration --------------------------------------------------------


def load_config(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    """Load and validate the experiment configuration."""
    import yaml

    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict[str, Any]) -> None:
    """Validate the configuration against the preregistered design."""
    if list(cfg.get("arms", [])) != ARMS:
        raise ValueError(f"config arms {cfg.get('arms')!r} must equal {ARMS}")
    regimes = cfg.get("regimes", {})
    if set(regimes) != set(REGIMES):
        raise ValueError(f"config regimes {sorted(regimes)} must equal {REGIMES}")
    constrained = regimes["constrained"].get("max_tokens")
    adequate = regimes["adequate"].get("max_tokens")
    for name, value in (("constrained", constrained), ("adequate", adequate)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"regimes.{name}.max_tokens must be a positive int")
    if constrained >= adequate:
        raise ValueError(
            f"constrained max_tokens ({constrained}) must be < adequate ({adequate})"
        )
    # Regimes may differ ONLY in max_tokens.
    if regimes["constrained"] != {"max_tokens": constrained} or regimes[
        "adequate"
    ] != {"max_tokens": adequate}:
        raise ValueError("regimes may configure max_tokens and nothing else")

    generation = cfg.get("generation", {})
    for key in ("max_turns", "timeout_seconds", "temperature", "top_p"):
        if key not in generation:
            raise ValueError(f"generation.{key} is required (shared across all arms)")
    # Arms are plain names: no per-arm generation overrides can exist.
    if not all(isinstance(arm, str) for arm in cfg["arms"]):
        raise ValueError("arms must be plain names; per-arm overrides are forbidden")

    # Comparisons: 2-element global entries or 3-element scoped entries.
    # The scoped entry is the pooled H2 reasoning-cluster comparison and must
    # match power.h2_cluster exactly (the runner analysis and the power
    # calculation must describe the SAME test).
    benchmarks_list = cfg.get("benchmarks", [])
    parsed_comparisons = []
    for entry in cfg.get("comparisons", []):
        arm_a, arm_b, scope = _parse_comparison_entry(entry)
        for arm in (arm_a, arm_b):
            if arm not in ARMS:
                raise ValueError(f"comparison {entry!r} must name two known arms")
        if scope is not None and any(b not in benchmarks_list for b in scope):
            raise ValueError(
                f"comparison {entry!r} scopes to benchmarks outside the "
                "primary set"
            )
        parsed_comparisons.append((arm_a, arm_b, scope))
    confirmatory_pairs = {(a, b) for a, b, _ in parsed_comparisons}
    if len(confirmatory_pairs) != len(parsed_comparisons):
        raise ValueError("confirmatory comparisons must be unique pairs")
    scoped = [(a, b, s) for a, b, s in parsed_comparisons if s is not None]
    if len(scoped) != 1:
        raise ValueError(
            "exactly one scoped (cluster) comparison is expected: the pooled "
            "H2 reasoning-cluster test; got "
            f"{[(a, b, list(s)) for a, b, s in scoped]}"
        )
    h2 = cfg.get("power", {}).get("h2_cluster", {})
    h2_pair = tuple(h2.get("comparison", []))
    h2_scope = tuple(h2.get("benchmarks", []))
    h2_scoped = scoped[0]
    if h2_scoped != (h2_pair[0], h2_pair[1], h2_scope):
        raise ValueError(
            "the scoped confirmatory comparison "
            f"{(h2_scoped[0], h2_scoped[1], list(h2_scoped[2]))} must equal "
            f"power.h2_cluster comparison/benchmarks {h2_pair} / {list(h2_scope)} "
            "— the preregistered H2 test and its power calculation must match"
        )
    # Exploratory comparisons: global counterparts of scoped confirmatory
    # comparisons ONLY (anything else would smuggle a confirmatory claim
    # past the Holm families).
    scoped_pairs = {(a, b) for a, b, _ in scoped}
    for entry in cfg.get("exploratory_comparisons", []):
        arm_a, arm_b, scope = _parse_comparison_entry(entry)
        for arm in (arm_a, arm_b):
            if arm not in ARMS:
                raise ValueError(
                    f"exploratory comparison {entry!r} must name two known arms"
                )
        if scope is not None:
            raise ValueError(
                f"exploratory comparison {entry!r} must be global (unscoped)"
            )
        if (arm_a, arm_b) not in scoped_pairs:
            raise ValueError(
                f"exploratory comparison {entry!r} is only permitted as the "
                "global counterpart of a scoped confirmatory comparison"
            )
    ni = cfg.get("noninferiority", {})
    if ni.get("reference_arm") not in ARMS:
        raise ValueError("noninferiority.reference_arm must be a known arm")
    if not all(cand in ARMS for cand in ni.get("candidates", [])):
        raise ValueError("noninferiority.candidates must be known arms")
    margin = ni.get("margin")
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not (
        0.0 < margin < 1.0
    ):
        raise ValueError(f"non-inferiority margin must be in (0, 1), got {margin!r}")
    alpha = ni.get("alpha")
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not (
        0.0 < alpha < 1.0
    ):
        raise ValueError(f"non-inferiority alpha must be in (0, 1), got {alpha!r}")
    cost = cfg.get("cost", {})
    for key in ("input_per_mtok", "output_per_mtok"):
        rate = cost.get(key)
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate <= 0:
            raise ValueError(f"cost.{key} must be a positive number")
    benchmarks = cfg.get("benchmarks", [])
    for bench in benchmarks:
        if not isinstance(bench, str) or not bench:
            raise ValueError("benchmarks entries must be non-empty strings")

    # Per-benchmark sample counts must cover exactly the primary set; the
    # isolated loader honors them (this is what fixes the underpowered
    # 10-sample default of run_public_bench without editing that file).
    samples = cfg.get("samples_per_benchmark", {})
    if not isinstance(samples, dict):
        raise ValueError("samples_per_benchmark must be a mapping")
    for bench in benchmarks:
        k = samples.get(bench)
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError(
                f"samples_per_benchmark[{bench!r}] must be a positive int, got {k!r}"
            )
    for bench in samples:
        if bench not in benchmarks:
            raise ValueError(
                f"samples_per_benchmark has {bench!r} which is not in the "
                "primary benchmark list"
            )
    planned = sum(int(k) for k in samples.values())
    if planned < 100:
        raise ValueError(
            f"planned task count {planned} is below the 100-task floor; the "
            "power analysis must justify any reduction (see "
            "structure_answer_power.py)"
        )

    power_cfg = cfg.get("power", {})
    planning_sd = power_cfg.get("planning_sd")
    if not isinstance(planning_sd, (int, float)) or isinstance(planning_sd, bool) or not (
        0.0 < planning_sd <= 1.0
    ):
        raise ValueError(f"power.planning_sd must be in (0, 1], got {planning_sd!r}")
    target_power = power_cfg.get("target_power")
    if not isinstance(target_power, (int, float)) or isinstance(target_power, bool) or not (
        0.0 < target_power < 1.0
    ):
        raise ValueError(f"power.target_power must be in (0, 1), got {target_power!r}")
    for key in ("sensitivity_delta",):
        value = power_cfg.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"power.{key} must be a positive number")
    cluster = power_cfg.get("h2_cluster", {})
    for bench in cluster.get("benchmarks", []):
        if bench not in benchmarks:
            raise ValueError(f"power.h2_cluster has unknown benchmark {bench!r}")
    if not isinstance(cluster.get("delta", 0.10), (int, float)) or cluster.get(
        "delta", 0.10
    ) <= 0:
        raise ValueError("power.h2_cluster.delta must be a positive number")
    if not power_cfg.get("archive_sources"):
        raise ValueError(
            "power.archive_sources is required: the planning SD must be "
            "traceable to archived data or stated assumptions"
        )


# -- Trial plan -----------------------------------------------------------


def build_trial_plan(
    tasks: list[dict],
    arms: list[str],
    regimes: list[str],
    trials_per_task: int,
    seed: int,
) -> list[dict]:
    """Build the full factorial task x arm x regime x trial plan, shuffled.

    Every (task, arm, regime, trial) cell appears exactly once, so all arms
    share identical (benchmark, task_id, trial) coverage and stats.pair_trials
    finds complete keyed pairs between any two arms within a regime.
    """
    plan = []
    for task in tasks:
        for arm in arms:
            for regime in regimes:
                for trial in range(trials_per_task):
                    plan.append(
                        {
                            "task": task,
                            "arm": arm,
                            "regime": regime,
                            "trial": trial,
                        }
                    )
    rng = random.Random(seed)
    rng.shuffle(plan)
    return plan


def trial_cost_usd(
    input_tokens: int, output_tokens: int, config: dict[str, Any]
) -> float:
    """Cost of one trial under the configured USD-per-1M-token rates."""
    cost = config["cost"]
    return (
        input_tokens / 1_000_000.0 * float(cost["input_per_mtok"])
        + output_tokens / 1_000_000.0 * float(cost["output_per_mtok"])
    )


# -- Trial execution ------------------------------------------------------


def run_trial(
    task: dict,
    arm: str,
    regime: str,
    system_prompt: str,
    trial_idx: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Run one trial. Generation settings come from the config and are
    identical across arms; only the system prompt varies by arm and only
    max_tokens varies by regime. The host task prompt is passed verbatim.
    """
    generation = config["generation"]
    max_tokens = config["regimes"][regime]["max_tokens"]
    model = os.environ.get("TAHOE_MODEL", ".")
    result = run_classic(
        task_id=f"{task['task_id']}-{arm}-{regime}-t{trial_idx}",
        task_prompt=task["description"],
        model=model,
        api_base=os.environ.get("TAHOE_API_BASE", ""),
        api_key=os.environ.get("TAHOE_API_KEY", ""),
        max_turns=generation["max_turns"],
        max_tokens=max_tokens,
        timeout_seconds=generation["timeout_seconds"],
        system_prompt=system_prompt,
        extra_body={
            "temperature": generation["temperature"],
            "top_p": generation["top_p"],
        },
    )
    passed, detail = grade_task(task, result.final_answer)
    # Truthful failure classification, never relabeled:
    #  - runner-level failures (timeout / api_error / empty_response / max_turns)
    #    keep the runner's own class;
    #  - only a produced answer that graded wrong is "wrong_answer".
    if passed:
        failure_class = "none"
    elif result.failure_class == "none":
        failure_class = "wrong_answer"
    else:
        failure_class = result.failure_class
    return {
        "task_id": task["task_id"],
        "benchmark": task["benchmark"],
        "arm": arm,
        "regime": regime,
        "trial": trial_idx,
        "model": model,
        "max_tokens": max_tokens,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "wall_seconds": result.wall_seconds,
        "passed": passed,
        "failure_class": failure_class,
        "runner_failure_class": result.failure_class,
        "finish_reason": result.finish_reason,
        "empty_response": result.empty_response,
        "retries": result.retries,
        "cost_usd": trial_cost_usd(
            result.input_tokens, result.output_tokens, config
        ),
        "final_answer": result.final_answer,
        "quality_score": 1.0 if passed else 0.0,
        "grader_detail": detail,
    }


def error_trial_record(
    task: dict, arm: str, regime: str, trial_idx: int, exc: Exception
) -> dict[str, Any]:
    """Record for a trial that failed before producing any outcome.

    Kept in the trial log (never dropped) with failure_class="error" so the
    trial count stays truthful; it grades as a failure like any runner-level
    failure and is reported separately in the failure breakdown.
    """
    return {
        "task_id": task["task_id"],
        "benchmark": task["benchmark"],
        "arm": arm,
        "regime": regime,
        "trial": trial_idx,
        "model": os.environ.get("TAHOE_MODEL", "."),
        "max_tokens": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "wall_seconds": 0.0,
        "passed": False,
        "failure_class": "error",
        "runner_failure_class": "error",
        "finish_reason": "",
        "empty_response": False,
        "retries": 0,
        "cost_usd": 0.0,
        "final_answer": f"ERROR: {exc}",
        "quality_score": 0.0,
        "grader_detail": str(exc),
    }


# -- Preregistered endpoints ----------------------------------------------


def arm_endpoints(trials: list[dict]) -> list[dict[str, Any]]:
    """Per (regime, arm) endpoints.

    Primary estimand — TASK-MACRO success: every task's repeated trials are
    aggregated to a per-task mean first, and tasks are weighted EQUALLY.
    This matches the confirmatory paired tests, which operate on the same
    per-task means. The trial-pooled (micro) rate is reported as
    DESCRIPTIVE ONLY (success_rate_micro).

      success_rate_macro   — PRIMARY: mean over tasks of per-task mean success
      success_rate_micro   — descriptive: n_passed / n_trials
      tokens_per_success   — sum(total_tokens over ALL trials, failures
                              included) / n_passed; null when n_passed == 0
      cost_per_success     — sum(cost_usd over ALL trials) / n_passed; null
                              when n_passed == 0
    Mandatory truncation outcome: the adequate regime is a LARGER budget, not
    a truncation-free guarantee, so every cell reports the count and rate of
    finish_reason="length" trials. Accuracy claims for the adequate regime
    are interpreted together with truncation_rate, never alone.
    Truthful metadata: n per failure_class, empty-response count, and
    finish_reason counts so truncation stays visible.
    """
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for trial in trials:
        cells.setdefault((trial["regime"], trial["arm"]), []).append(trial)

    rows = []
    for regime in REGIMES:
        for arm in ARMS:
            cell = cells.get((regime, arm), [])
            n = len(cell)
            n_passed = sum(1 for t in cell if t.get("passed"))
            # task-macro (primary estimand): per-task mean success, tasks
            # equally weighted; keyed by (benchmark, task_id), never positional.
            # A trial with no task identity (only possible in synthetic/test
            # data) counts as its own task so macro degrades to micro rather
            # than crashing or silently merging distinct trials.
            by_task: dict[tuple[str, str], list[float]] = defaultdict(list)
            for i, t in enumerate(cell):
                task_key = (t.get("benchmark", ""), t.get("task_id") or f"__trial_{i}")
                by_task[task_key].append(1.0 if t.get("passed") else 0.0)
            task_means = [statistics.fmean(v) for v in by_task.values()]
            total_tokens = sum(t.get("total_tokens", 0) for t in cell)
            total_cost = sum(t.get("cost_usd", 0.0) for t in cell)
            failures: dict[str, int] = defaultdict(int)
            for t in cell:
                if not t.get("passed"):
                    failures[t.get("failure_class", "unknown")] += 1
            finish_reasons: dict[str, int] = defaultdict(int)
            for t in cell:
                reason = t.get("finish_reason") or "none"
                finish_reasons[reason] += 1
            truncated = sum(1 for t in cell if t.get("finish_reason") == "length")
            rows.append(
                {
                    "regime": regime,
                    "arm": arm,
                    "n_trials": n,
                    "n_passed": n_passed,
                    "success_estimand": "task-macro (per-task mean, equally weighted tasks)",
                    "success_rate_macro": (
                        statistics.fmean(task_means) if task_means else 0.0
                    ),
                    "success_rate_micro": (n_passed / n) if n else 0.0,
                    "n_tasks": len(task_means),
                    "total_tokens": total_tokens,
                    "tokens_per_success": (
                        total_tokens / n_passed if n_passed else None
                    ),
                    "total_cost_usd": total_cost,
                    "cost_per_success_usd": (
                        total_cost / n_passed if n_passed else None
                    ),
                    "mean_output_tokens": (
                        statistics.fmean(
                            t.get("output_tokens", 0) for t in cell
                        )
                        if cell
                        else 0.0
                    ),
                    "truncated_count": truncated,
                    "truncation_rate": (truncated / n) if n else 0.0,
                    "failures_by_class": dict(sorted(failures.items())),
                    "finish_reasons": dict(sorted(finish_reasons.items())),
                    "empty_response_count": sum(
                        1 for t in cell if t.get("empty_response")
                    ),
                }
            )
    return rows


def _numeric_trial_value(trial: dict, field: str) -> float:
    if field == "passed":
        return 1.0 if trial.get("passed") else 0.0
    value = trial.get(field, 0)
    return float(value)


def paired_task_means(
    pairs: list[tuple[dict, dict]], field: str
) -> tuple[list[tuple[str, str]], list[float], list[float]]:
    """Aggregate paired trials to equally weighted per-task means.

    Mirrors stats.aggregate_trials_by_task over the explicitly keyed
    pair_trials output, keeping both arms aligned on the same task set.
    """
    grouped_a: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_b: dict[tuple[str, str], list[float]] = defaultdict(list)
    for trial_a, trial_b in pairs:
        key = (trial_a["benchmark"], trial_a["task_id"])
        grouped_a[key].append(_numeric_trial_value(trial_a, field))
        grouped_b[key].append(_numeric_trial_value(trial_b, field))
    keys = sorted(grouped_a)
    return (
        keys,
        [statistics.fmean(grouped_a[key]) for key in keys],
        [statistics.fmean(grouped_b[key]) for key in keys],
    )


def _family_seed(config: dict[str, Any], *parts: Any) -> int:
    digest = hashlib.sha256(
        json.dumps([config["seed"], *parts], sort_keys=True, default=str).encode()
    ).hexdigest()
    return int(digest[:8], 16)


def _parse_comparison_entry(entry: Any) -> tuple[str, str, tuple[str, ...] | None]:
    """Parse a comparison entry: [arm_a, arm_b] or [arm_a, arm_b, [benchmarks]].

    The optional third element scopes the comparison to a subset of the
    primary benchmarks (the pooled H2 reasoning cluster). Returns
    (arm_a, arm_b, scope) with scope = None for global comparisons.
    """
    if not isinstance(entry, (list, tuple)) or len(entry) not in (2, 3):
        raise ValueError(
            "each comparison must be [arm_a, arm_b] or "
            f"[arm_a, arm_b, [benchmarks]], got {entry!r}"
        )
    arm_a, arm_b = entry[0], entry[1]
    scope: tuple[str, ...] | None = None
    if len(entry) == 3:
        raw = entry[2]
        if not isinstance(raw, list) or not raw:
            raise ValueError(
                f"comparison scope must be a non-empty list of benchmarks, got {raw!r}"
            )
        scope = tuple(raw)
    return arm_a, arm_b, scope


def paired_comparisons(trials: list[dict], config: dict[str, Any]) -> list[dict]:
    """Confirmatory paired comparisons, Holm-corrected per family — plus the
    preregistered EXPLORATORY global counterpart of the H2 cluster test.

    For each regime and each preregistered comparison (global or scoped to
    the pooled H2 reasoning cluster):
    - pair by exact (benchmark, task_id, trial) identity (stats.pair_trials)
    - aggregate repeated trials to per-task means (task-macro estimand)
    - two-sided paired permutation test on `passed` (endpoint: success) and
      on `total_tokens` (endpoint: total_tokens)
    - task-cluster bootstrap CI on the per-task mean difference
    Holm correction (stats.holm_adjust_pvalues) is applied within each
    (regime, endpoint) family over the CONFIRMATORY comparisons only
    (rows with confirmatory=True). Exploratory rows carry unadjusted
    p-values, no Holm membership, and confirmatory=False.
    """
    n_permutations = config.get("stats", {}).get("n_permutations", 10_000)
    n_resamples = config.get("stats", {}).get("n_resamples", 10_000)
    confirmatory = [
        _parse_comparison_entry(entry) for entry in config["comparisons"]
    ]
    exploratory = [
        _parse_comparison_entry(entry)
        for entry in config.get("exploratory_comparisons", [])
    ]

    def _key(arm_a: str, arm_b: str, scope: tuple[str, ...] | None) -> str:
        suffix = "|" + ",".join(sorted(scope)) if scope else ""
        return f"{arm_a}|{arm_b}{suffix}"

    records: dict[tuple[str, str, str], dict] = {}
    for regime in REGIMES:
        for arm_a, arm_b, scope in confirmatory + exploratory:
            is_confirmatory = (arm_a, arm_b, scope) in confirmatory
            regime_trials = [t for t in trials if t["regime"] == regime]
            if scope is not None:
                regime_trials = [
                    t for t in regime_trials if t["benchmark"] in scope
                ]
            trials_a = [t for t in regime_trials if t["arm"] == arm_a]
            trials_b = [t for t in regime_trials if t["arm"] == arm_b]
            pairs = stats.pair_trials(trials_a, trials_b)
            if not pairs:
                raise ValueError(
                    f"no keyed pairs for ({arm_a}, {arm_b}) scope="
                    f"{scope or 'global'} in regime {regime}; the trial plan "
                    "guarantees pairing — data is incomplete"
                )
            keys, means_a, means_b = paired_task_means(pairs, "passed")
            base = {
                "regime": regime,
                "arm_a": arm_a,
                "arm_b": arm_b,
                "benchmarks": sorted(scope) if scope else None,
                "confirmatory": is_confirmatory,
                "role": "confirmatory" if is_confirmatory else "exploratory",
                "n_tasks": len(keys),
                "n_paired_trials": len(pairs),
            }
            base["mean_success_a"] = statistics.fmean(means_a) if means_a else 0.0
            base["mean_success_b"] = statistics.fmean(means_b) if means_b else 0.0
            base["mean_success_difference"] = base["mean_success_a"] - base[
                "mean_success_b"
            ]
            base["success_permutation_p"] = stats.paired_permutation_test(
                means_a,
                means_b,
                n_permutations=n_permutations,
                seed=_family_seed(
                    config, regime, arm_a, arm_b, sorted(scope or []), "success"
                ),
            )
            _, toks_a, toks_b = paired_task_means(pairs, "total_tokens")
            base["mean_total_tokens_a"] = statistics.fmean(toks_a) if toks_a else 0.0
            base["mean_total_tokens_b"] = statistics.fmean(toks_b) if toks_b else 0.0
            base["total_tokens_permutation_p"] = stats.paired_permutation_test(
                toks_a,
                toks_b,
                n_permutations=n_permutations,
                seed=_family_seed(
                    config, regime, arm_a, arm_b, sorted(scope or []), "total_tokens"
                ),
            )
            ci = stats.task_cluster_bootstrap_ci(
                trials_a,
                trials_b,
                field="total_tokens",
                n_resamples=n_resamples,
                seed=_family_seed(
                    config, regime, arm_a, arm_b, sorted(scope or []), "tokens_ci"
                ),
            )
            base["total_tokens_mean_difference"] = ci[0]
            base["total_tokens_ci_low"] = ci[1]
            base["total_tokens_ci_high"] = ci[2]
            for endpoint in ("success", "total_tokens"):
                records[(regime, _key(arm_a, arm_b, scope), endpoint)] = {
                    **base,
                    "endpoint": endpoint,
                    "permutation_p": base[
                        "success_permutation_p"
                        if endpoint == "success"
                        else "total_tokens_permutation_p"
                    ],
                }

    out: list[dict] = []
    for endpoint in ("success", "total_tokens"):
        for regime in REGIMES:
            # Holm families contain CONFIRMATORY comparisons only.
            family = sorted(
                key
                for key, record in records.items()
                if key[0] == regime
                and key[2] == endpoint
                and record["confirmatory"]
            )
            adjusted = stats.holm_adjust_pvalues(
                [records[key]["permutation_p"] for key in family]
            )
            for key, p_holm in zip(family, adjusted):
                records[key]["permutation_p_holm"] = p_holm
            # exploratory records get no Holm membership at all
            for key, record in records.items():
                if key[0] == regime and key[2] == endpoint and not record["confirmatory"]:
                    record["permutation_p_holm"] = None
    for key in sorted(records):
        out.append(records[key])
    return out


def noninferiority_tests(trials: list[dict], config: dict[str, Any]) -> list[dict]:
    """One-sided paired non-inferiority tests vs the reference arm.

    For each candidate arm and regime: pair trials with the reference arm,
    aggregate to per-task mean success, and test H0: mean(candidate -
    reference) <= -margin with the preregistered margin (stats.
    non_inferiority_test). P-values are Holm-corrected within each
    (regime, noninferiority) family.
    """
    ni = config["noninferiority"]
    reference = ni["reference_arm"]
    margin = float(ni["margin"])
    alpha = float(ni["alpha"])

    records: dict[tuple[str, str], dict] = {}
    for regime in REGIMES:
        ref_trials = [
            t for t in trials if t["arm"] == reference and t["regime"] == regime
        ]
        for candidate in ni["candidates"]:
            cand_trials = [
                t for t in trials if t["arm"] == candidate and t["regime"] == regime
            ]
            pairs = stats.pair_trials(cand_trials, ref_trials)
            if not pairs:
                raise ValueError(
                    f"no keyed pairs for ({candidate}, {reference}) in regime "
                    f"{regime}; the trial plan guarantees pairing — data is "
                    "incomplete"
                )
            _, means_cand, means_ref = paired_task_means(pairs, "passed")
            result = stats.non_inferiority_test(
                means_cand, means_ref, margin=margin, alpha=alpha
            )
            records[(regime, candidate)] = {
                "regime": regime,
                "endpoint": "noninferiority",
                "candidate_arm": candidate,
                "reference_arm": reference,
                "margin": margin,
                "alpha": alpha,
                "n_tasks": len(means_cand),
                **result,
            }

    out: list[dict] = []
    for regime in REGIMES:
        family = sorted(key for key in records if key[0] == regime)
        adjusted = stats.holm_adjust_pvalues(
            [records[key]["p_value"] for key in family]
        )
        for key, p_holm in zip(family, adjusted):
            records[key]["p_value_holm"] = p_holm
            records[key]["non_inferior_holm"] = p_holm < alpha
            out.append(records[key])
    return out


def analyze(trials: list[dict], config: dict[str, Any]) -> dict[str, Any]:
    """Full preregistered analysis: endpoints, comparisons, non-inferiority."""
    if not trials:
        return {
            "experiment": EXPERIMENT,
            "endpoints": [],
            "comparisons": [],
            "noninferiority": [],
            "note": "no trials",
        }
    return {
        "experiment": EXPERIMENT,
        "endpoints": arm_endpoints(trials),
        "comparisons": paired_comparisons(trials, config),
        "noninferiority": noninferiority_tests(trials, config),
    }


# -- Immutable output creation --------------------------------------------


def make_immutable_run_dir(
    name: str = EXPERIMENT,
    results_root: Path | str | None = None,
    *,
    stamp: str | None = None,
) -> Path:
    """Create and return a NEW timestamped run directory; never overwrite.

    Unlike outdir.make_run_dir (which tolerates collisions), this helper
    REFUSES to reuse an existing directory: a second run in the same second
    must set RUN_TAG (or RESULTS_ROOT) rather than silently merging with or
    clobbering the earlier run's raw data.
    """
    root = Path(results_root) if results_root else RESULTS_ROOT
    ts = stamp if stamp is not None else datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H%M%S"
    )
    tag = os.environ.get("RUN_TAG", "")
    dirname = f"{ts}_{name}" + (f"_{tag}" if tag else "")
    run_dir = root / "runs" / dirname
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RuntimeError(
            f"refusing to overwrite existing run directory {run_dir}; "
            "set RUN_TAG or RESULTS_ROOT to create a distinct run"
        ) from exc
    return run_dir


def write_immutable(path: Path | str, text: str) -> Path:
    """Write *text* to *path* creating the file exclusively ('x' mode).

    Refuses to overwrite: an existing file raises RuntimeError instead of
    silently destroying earlier results.
    """
    path = Path(path)
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise RuntimeError(
            f"refusing to overwrite existing file {path}"
        ) from exc
    return path


# -- Manifest -------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    return sha256_bytes(Path(path).read_bytes())


def task_set_fingerprint(tasks: list[dict]) -> str:
    """Stable fingerprint of the exact evaluated task set.

    Hashes the task identity fields (not model outputs), pinning dataset
    content even for remote HF datasets whose files are not on disk.
    """
    payload = json.dumps(
        sorted(
            (
                {
                    "task_id": t["task_id"],
                    "benchmark": t["benchmark"],
                    "description": t["description"],
                    "expected": str(t["expected"]),
                    "grader": t["grader"],
                }
                for t in tasks
            ),
            key=lambda item: item["task_id"],
        ),
        sort_keys=True,
    )
    return sha256_bytes(payload.encode("utf-8"))


def _manifest_file_entry(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(Path(__file__).resolve().parent.parent)),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def build_manifest(
    config: dict[str, Any],
    prompts: dict[str, str],
    tasks: list[dict],
    model: str,
) -> dict[str, Any]:
    """Provenance manifest: hashes of every prompt/config/grader/runner
    artifact, dataset fingerprints, model and generation settings, plus the
    sample plan and the power-analysis provenance behind it."""
    import run_public_bench
    import runner_classic
    import structure_answer_power
    import structure_answer_tasks

    repo_files = [
        CONFIG_PATH,
        PREREG_PATH,
        Path(__file__),
        Path(run_public_bench.__file__),
        Path(runner_classic.__file__),
        Path(stats.__file__),
        Path(structure_answer_tasks.__file__),
        Path(structure_answer_power.__file__),
        Path(structure_answer_power.DEFAULT_OUTPUT),
        Path(resolve_prompt("tahoe")),
        ANSWER_ONLY_FILE,
        GENERIC_STRUCTURE_FILE,
        resolve_prompt("cod"),
    ]
    local_datasets = sorted(
        (Path(__file__).resolve().parent / "data").glob("*.jsonl")
    )
    return {
        "schema_version": 1,
        "experiment": EXPERIMENT,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preregistration": {
            "path": str(PREREG_PATH.relative_to(Path(__file__).resolve().parent.parent)),
            "sha256": sha256_file(PREREG_PATH),
        },
        "files": [_manifest_file_entry(path) for path in repo_files],
        "local_dataset_files": [_manifest_file_entry(p) for p in local_datasets],
        "hf_benchmarks": list(config["benchmarks"]),
        "samples_per_benchmark": {
            bench: int(k) for bench, k in config["samples_per_benchmark"].items()
        },
        "planned_task_count": planned_task_count(config),
        "drawn_per_benchmark": {
            bench: sum(1 for t in tasks if t["benchmark"] == bench)
            for bench in config["benchmarks"]
        },
        "n_tasks": len(tasks),
        "power": {
            "planning_sd": config["power"]["planning_sd"],
            "target_power": config["power"]["target_power"],
            "justification_artifact": str(
                structure_answer_power.DEFAULT_OUTPUT.relative_to(
                    Path(__file__).resolve().parent.parent
                )
            ),
            "justification_sha256": sha256_file(structure_answer_power.DEFAULT_OUTPUT),
            "multiplicity_convention": (
                "confirmatory power planned at Bonferroni/Holm-first-step "
                "alpha/m of the actual families (m=4 non-inferiority, "
                "m=6 comparisons per regime)"
            ),
        },
        "task_set_fingerprint": task_set_fingerprint(tasks),
        "prompts": {
            arm: {
                "sha256": sha256_bytes(prompts[arm].encode("utf-8")),
                "chars": len(prompts[arm]),
                "source": PROMPT_SOURCES[arm],
            }
            for arm in ARMS
        },
        "model": {
            "name": model,
            "sha256": sha256_bytes(model.encode("utf-8")),
            "api_base_configured": bool(os.environ.get("TAHOE_API_BASE")),
        },
        "generation": dict(config["generation"]),
        "regimes": {name: dict(params) for name, params in config["regimes"].items()},
        "seed": config["seed"],
        "trials_per_task": config["trials_per_task"],
        "arms": list(config["arms"]),
        "comparisons": [list(entry) for entry in config["comparisons"]],
        "exploratory_comparisons": [
            list(entry) for entry in config.get("exploratory_comparisons", [])
        ],
        "h2_cluster": {
            "comparison": list(config["power"]["h2_cluster"]["comparison"]),
            "benchmarks": list(config["power"]["h2_cluster"]["benchmarks"]),
            "delta": config["power"]["h2_cluster"]["delta"],
            "role": "confirmatory (scoped comparison in the success family); "
            "global counterpart exploratory",
        },
        "noninferiority": dict(config["noninferiority"]),
        "holm_families": [dict(f) for f in config["holm_families"]],
        "cost": dict(config["cost"]),
        "prompt_relationships_verified": True,
    }


# -- Report ---------------------------------------------------------------


def format_endpoint_table(endpoints: list[dict]) -> str:
    header = (
        f"{'regime':11s} | {'arm':17s} | {'pass':>9s} | {'macro':>7s} | "
        f"{'micro':>7s} | {'tok/succ':>9s} | {'$/succ':>8s} | "
        f"{'mean_out':>8s} | {'trunc':>9s} | {'n':>5s}"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for row in endpoints:
        tok = f"{row['tokens_per_success']:.0f}" if row["tokens_per_success"] is not None else "--"
        cost = f"{row['cost_per_success_usd']:.4f}" if row["cost_per_success_usd"] is not None else "--"
        trunc = f"{row['truncated_count']} ({row['truncation_rate']:.1%})"
        lines.append(
            f"{row['regime']:11s} | {row['arm']:17s} | "
            f"{row['n_passed']:>4d}/{row['n_trials']:<4d} | "
            f"{row['success_rate_macro']:>6.1%} | {row['success_rate_micro']:>6.1%} | "
            f"{tok:>9s} | {cost:>8s} | "
            f"{row['mean_output_tokens']:>8.0f} | {trunc:>9s} | {row['n_trials']:>5d}"
        )
    return "\n".join(lines)


def format_run_doc(manifest: dict, analysis: dict) -> str:
    lines = [
        f"# Run: {EXPERIMENT} — {manifest['created_at']}",
        "",
        "Preregistered experiment. Preregistration:",
        f"`{manifest['preregistration']['path']}` "
        f"(sha256 {manifest['preregistration']['sha256']}).",
        "",
        "This run is immutable: created with exclusive-write directories and",
        "files; nothing here may be overwritten or edited post hoc.",
        "",
        "## Endpoints (primary estimand: TASK-MACRO success — per-task means,",
        "equally weighted tasks; micro is the descriptive trial-pooled rate.",
        "Also tokens/cost per success including failures; trunc is a mandatory",
        "reported outcome — finish_reason=\"length\" count and rate per cell)",
        "",
        "```",
        format_endpoint_table(analysis.get("endpoints", [])),
        "```",
        "",
        "Interpretation rule: the adequate regime (max_tokens=4096) is a larger",
        "budget expected to make truncation rare, NOT a guarantee. Wherever",
        "trunc > 0 under `adequate`, the accuracy for that arm is interpreted",
        "together with the measured truncation rate and never presented as",
        "truncation-free.",
        "",
        "## Comparisons (paired permutation on per-task means, task-macro;",
        "Holm per regime x endpoint over confirmatory rows only)",
        "",
        "| regime | comparison | scope | role | endpoint | mean diff | p | p_holm |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in analysis.get("comparisons", []):
        diff_key = (
            "mean_success_difference"
            if row["endpoint"] == "success"
            else "total_tokens_mean_difference"
        )
        scope = (
            "+".join(row["benchmarks"]) if row.get("benchmarks") else "global"
        )
        p_holm = (
            f"{row['permutation_p_holm']:.4f}"
            if row.get("permutation_p_holm") is not None
            else "— (exploratory)"
        )
        lines.append(
            f"| {row['regime']} | {row['arm_a']} vs {row['arm_b']} | "
            f"{scope} | {row['role']} | {row['endpoint']} | "
            f"{row[diff_key]:.4f} | {row['permutation_p']:.4f} | {p_holm} |"
        )
    lines += [
        "",
        "## Quality non-inferiority vs "
        f"{manifest['noninferiority']['reference_arm']} "
        f"(margin {manifest['noninferiority']['margin']}, one-sided, Holm per regime)",
        "",
        "| regime | candidate | mean diff | p | p_holm | non-inferior (Holm) |",
        "|---|---|---|---|---|---|",
    ]
    for row in analysis.get("noninferiority", []):
        lines.append(
            f"| {row['regime']} | {row['candidate_arm']} | "
            f"{row['mean_difference']:.4f} | {row['p_value']:.4f} | "
            f"{row['p_value_holm']:.4f} | {row['non_inferior_holm']} |"
        )
    lines += [
        "",
        "## Provenance",
        "",
        f"- task set fingerprint: `{manifest['task_set_fingerprint']}` "
        f"({manifest['n_tasks']} tasks; planned "
        f"{manifest['planned_task_count']}, per-benchmark sample counts in "
        "`manifest.json`)",
        f"- model: `{manifest['model']['name']}`",
        f"- power justification: `{manifest['power']['justification_artifact']}` "
        f"(sha256 {manifest['power']['justification_sha256'][:12]}…; "
        "confirmatory power planned at the Bonferroni/Holm-first-step "
        "alpha/m of the actual multiplicity families)",
        "- full hashes: see `manifest.json`",
        "",
        "Interpretation rules, endpoints and families are fixed by the",
        "preregistration document; any deviation must be reported as such.",
        "",
    ]
    return "\n".join(lines)


# -- Main -----------------------------------------------------------------


def main() -> None:
    print(f"[{EXPERIMENT}] preregistered experiment — launching (results are immutable)")
    config = load_config()
    prompts = load_arm_prompts()
    for arm in ARMS:
        digest = sha256_bytes(prompts[arm].encode("utf-8"))[:12]
        print(f"  arm={arm:17s} chars={len(prompts[arm]):4d} sha256[:12]={digest}")

    print("Loading tasks (isolated loader honoring configured samples_per_benchmark)...")
    tasks = load_experiment_tasks(config)
    planned = planned_task_count(config)
    primary = set(config["benchmarks"])
    smoke_env = [b for b in os.environ.get("BENCHES", "").split(",") if b.strip()]
    smoke_run = False
    if smoke_env:
        allowed = set(smoke_env) & primary
        tasks = [t for t in tasks if t["benchmark"] in allowed]
        smoke_run = True
    print(f"  {len(tasks)} tasks loaded (planned {planned} at the configured "
          "per-benchmark counts)")
    if not smoke_run and len(tasks) != planned:
        # Truthful, loud shortfall report: dataset caps are possible by
        # design (min(k, dataset_size)) but must never pass silently.
        by_bench = defaultdict(int)
        for t in tasks:
            by_bench[t["benchmark"]] += 1
        shortfalls = {
            bench: (by_bench.get(bench, 0), config["samples_per_benchmark"][bench])
            for bench in config["benchmarks"]
            if by_bench.get(bench, 0) != config["samples_per_benchmark"][bench]
        }
        print(f"  WARNING: drawn != planned for {shortfalls} — dataset caps "
              "reduced the task set; the manifest records actual counts and "
              "the effective power is below the planned justification")
    if smoke_run:
        print("  WARNING: BENCHES filter active — this is a smoke run, NOT the "
              "preregistered primary analysis")

    plan = build_trial_plan(
        tasks, ARMS, REGIMES, config["trials_per_task"], config["seed"]
    )
    print(
        f"Running {len(plan)} trials "
        f"({len(tasks)} tasks x {len(ARMS)} arms x {len(REGIMES)} regimes "
        f"x {config['trials_per_task']} trials, shuffled, seed={config['seed']})..."
    )

    all_trials: list[dict] = []
    t0 = time.time()
    for done, entry in enumerate(plan, start=1):
        task, arm, regime, trial_idx = (
            entry["task"],
            entry["arm"],
            entry["regime"],
            entry["trial"],
        )
        try:
            record = run_trial(
                task, arm, regime, prompts[arm], trial_idx, config
            )
        except Exception as exc:  # keep every failure in the log, truthfully
            record = error_trial_record(task, arm, regime, trial_idx, exc)
        all_trials.append(record)
        if done % 25 == 0 or done == len(plan):
            rate = done / max(time.time() - t0, 1e-9)
            print(
                f"  [{done}/{len(plan)}] {task['task_id']} / {arm} / {regime} / "
                f"t{trial_idx} ({rate:.1f}/s)",
                flush=True,
            )

    analysis = analyze(all_trials, config)
    run_dir = make_immutable_run_dir()
    manifest = build_manifest(config, prompts, tasks, os.environ.get("TAHOE_MODEL", "."))
    if smoke_run:
        manifest["smoke_run"] = True

    write_immutable(run_dir / "trials.json", json.dumps(all_trials, indent=2, sort_keys=True))
    write_immutable(run_dir / "analysis.json", json.dumps(analysis, indent=2, sort_keys=True))
    write_immutable(run_dir / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    write_immutable(run_dir / "RUN.md", format_run_doc(manifest, analysis))

    print("\n=== ENDPOINTS ===\n")
    print(format_endpoint_table(analysis["endpoints"]))
    print(f"\nResults written to {run_dir} (immutable, refuses overwrite)")


if __name__ == "__main__":
    main()
