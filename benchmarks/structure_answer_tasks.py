#!/usr/bin/env python3
"""Task loader for the structure-answer experiment — honors configured counts.

STATUS: preparation code only. This module loads benchmark data; it never
calls a model, never runs on import, and does not modify run_public_bench.

Why this loader exists: run_public_bench.load_tasks() hardcodes 10 samples
per benchmark, which the pre-run power analysis showed to be underpowered for
the preregistered 0.05 non-inferiority margin. This isolated loader loads the
same ten benchmarks with a CONFIGURED number of samples per benchmark
(``samples_per_benchmark`` in structure-answer.yaml), while leaving
run_public_bench.py untouched. Grading stays composed from
run_public_bench.grade_task (arm-invariant, unmodified).

Sampling properties (preregistered):
- Deterministic: per benchmark, indices are drawn with
  ``random.Random(f"{seed}|{benchmark}")`` — stable across runs and machines.
- Nested: the shuffle is independent of k, so the k=10 task set is a subset
  of the k=45 task set for the same seed. (The exact 10-sample sets of the
  archived runs used rng.sample and are NOT reproduced; this is documented in
  the preregistration.)
- Capped: each benchmark draws ``min(k, len(dataset))`` tasks, so small test
  splits (college_mathematics: 100, formal_logic: 126) never crash the run;
  the actual drawn count is reported by ``load_experiment_tasks``.

Task dicts mirror run_public_bench's construction field-for-field (same
task_id patterns, description strings, expected values, grader names and
labels), so the shared arm-invariant grader works unchanged.
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from collections.abc import Sequence


def _load_dataset(name: str, config_name: str | None, split: str):
    """Default HF dataset loader (indirection point for tests)."""
    import datasets

    return datasets.load_dataset(name, config_name, split=split)


# -- Per-benchmark builders (mirror run_public_bench construction) ----------


def _build_gsm8k(index: int, ex: dict) -> dict:
    return {
        "task_id": f"gsm8k-{index:04d}",
        "benchmark": "gsm8k",
        "description": ex["question"],
        "expected": ex["answer"],
        "grader": "gsm8k",
        "difficulty": "medium",
    }


def _build_arc(index: int, ex: dict) -> dict:
    choices = " ".join(
        f"({k}) {v}"
        for k, v in zip(ex["choices"]["label"], ex["choices"]["text"])
    )
    return {
        "task_id": f"arc-{index:04d}",
        "benchmark": "arc",
        "description": (
            f"{ex['question']}\n\nChoices: {choices}\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        "expected": ex["answerKey"],
        "labels": ex["choices"]["label"],
        "grader": "arc",
        "difficulty": "hard",
    }


def _build_bbh_logical(index: int, ex: dict) -> dict:
    return {
        "task_id": f"bbh-{index:04d}",
        "benchmark": "bbh",
        "description": f"{ex['input']}\n\nAnswer with the letter of the correct option.",
        "expected": ex["target"],
        "grader": "bbh",
        "difficulty": "hard",
    }


def _build_bbh_track(index: int, ex: dict) -> dict:
    return {
        "task_id": f"bbh-track-{index:04d}",
        "benchmark": "bbh_track",
        "description": f"{ex['input']}\n\nAnswer with the letter of the correct option.",
        "expected": ex["target"],
        "grader": "bbh",
        "difficulty": "hard",
    }


def _build_bbh_arith(index: int, ex: dict) -> dict:
    return {
        "task_id": f"bbh-arith-{index:04d}",
        "benchmark": "bbh_arith",
        "description": f"{ex['input']}\n\nAnswer with just the number.",
        "expected": ex["target"],
        "grader": "bbh_arith",
        "difficulty": "hard",
    }


def _build_mmlu(benchmark: str, task_id_prefix: str):
    def build(index: int, ex: dict) -> dict:
        choices = "\n".join(
            f"({chr(ord('A') + j)}) {c}" for j, c in enumerate(ex["choices"])
        )
        return {
            "task_id": f"{task_id_prefix}-{index:04d}",
            "benchmark": benchmark,
            "description": (
                f"{ex['question']}\n\n{choices}\n\n"
                "Answer with just the letter (A, B, C, or D)."
            ),
            "expected": str(ex["answer"]),
            "choices": ex["choices"],
            "grader": "mmlu",
            "difficulty": "hard",
        }

    return build


def _build_lsat(index: int, ex: dict) -> dict:
    choices = "\n".join(ex["choices"])
    gold_idx = ex["gold"][0] if isinstance(ex["gold"], list) else ex["gold"]
    gold_letter = chr(ord("A") + gold_idx)
    return {
        "task_id": f"lsat-{index:04d}",
        "benchmark": "lsat",
        "description": (
            f"{ex['query']}\n\n{choices}\n\n"
            "Answer with just the letter (A, B, C, D, or E)."
        ),
        "expected": gold_letter,
        "grader": "lsat",
        "difficulty": "hard",
    }


def _build_race(index: int, ex: dict) -> dict:
    probs = ast.literal_eval(ex["problems"])
    prob = probs[0]
    choices = "\n".join(
        f"({chr(ord('A') + j)}) {opt}" for j, opt in enumerate(prob["options"])
    )
    return {
        "task_id": f"race-{index:04d}",
        "benchmark": "race",
        "description": (
            f"Read the following passage and answer the question.\n\n"
            f"{ex['article']}\n\nQuestion: {prob['question']}\n\n{choices}\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        "expected": prob["answer"],
        "grader": "race",
        "difficulty": "hard",
    }


@dataclass(frozen=True)
class BenchmarkSpec:
    benchmark: str
    dataset_args: tuple
    build: Callable[[int, dict], dict]


SPECS: dict[str, BenchmarkSpec] = {
    "gsm8k": BenchmarkSpec(
        "gsm8k", ("gsm8k", "main", "test"), _build_gsm8k
    ),
    "arc": BenchmarkSpec(
        "arc", ("allenai/ai2_arc", "ARC-Challenge", "test"), _build_arc
    ),
    "bbh": BenchmarkSpec(
        "bbh", ("lukaemon/bbh", "logical_deduction_seven_objects", "test"),
        _build_bbh_logical,
    ),
    "bbh_track": BenchmarkSpec(
        "bbh_track",
        ("lukaemon/bbh", "tracking_shuffled_objects_seven_objects", "test"),
        _build_bbh_track,
    ),
    "bbh_arith": BenchmarkSpec(
        "bbh_arith", ("lukaemon/bbh", "multistep_arithmetic_two", "test"),
        _build_bbh_arith,
    ),
    "mmlu_math": BenchmarkSpec(
        "mmlu_math", ("hails/mmlu_no_train", "college_mathematics", "test"),
        _build_mmlu("mmlu_math", "mmlu-math"),
    ),
    "mmlu_logic": BenchmarkSpec(
        "mmlu_logic", ("hails/mmlu_no_train", "formal_logic", "test"),
        _build_mmlu("mmlu_logic", "mmlu-logic"),
    ),
    "mmlu_acct": BenchmarkSpec(
        "mmlu_acct", ("hails/mmlu_no_train", "professional_accounting", "test"),
        _build_mmlu("mmlu_acct", "mmlu-acct"),
    ),
    "lsat": BenchmarkSpec(
        "lsat", ("hails/agieval-lsat-lr", None, "test"), _build_lsat
    ),
    "race": BenchmarkSpec(
        "race", ("EleutherAI/race", "high", "test"), _build_race
    ),
}


def select_indices(n_items: int, k: int, seed: int, benchmark: str) -> list[int]:
    """Deterministic, nested index selection for one benchmark.

    The shuffle never depends on k, so the selected set for k=10 is a subset
    of the selected set for k=45 under the same seed. Returns indices sorted
    ascending so task ids are stable regardless of k.
    """
    if k < 1:
        raise ValueError(f"samples for {benchmark!r} must be >= 1, got {k}")
    if n_items < 1:
        raise ValueError(f"dataset for {benchmark!r} is empty")
    rng = random.Random(f"{seed}|{benchmark}")
    order = list(range(n_items))
    rng.shuffle(order)
    return sorted(order[: min(k, n_items)])


def load_experiment_tasks(
    config: dict[str, Any],
    dataset_loader: Callable[..., Sequence] = _load_dataset,
) -> list[dict]:
    """Load the primary task set at the configured per-benchmark counts.

    Raises if a configured benchmark has no spec or no configured sample
    count, and caps the draw at the dataset size (reporting actual counts is
    the caller's job via the returned ``sample_report``-style metadata —
    see ``sample_plan``).
    """
    benchmarks = list(config["benchmarks"])
    samples = config["samples_per_benchmark"]
    seed = int(config["seed"])
    for benchmark in benchmarks:
        if benchmark not in SPECS:
            raise ValueError(f"no benchmark spec for {benchmark!r}")
        if benchmark not in samples:
            raise ValueError(f"samples_per_benchmark missing {benchmark!r}")
    for benchmark in samples:
        if benchmark not in benchmarks:
            raise ValueError(
                f"samples_per_benchmark has {benchmark!r} which is not in the "
                "primary benchmark list"
            )

    tasks: list[dict] = []
    for benchmark in benchmarks:
        spec = SPECS[benchmark]
        k = int(samples[benchmark])
        dataset = dataset_loader(*spec.dataset_args)
        indices = select_indices(len(dataset), k, seed, benchmark)
        # A capped draw (len(indices) < k on a small split) is intentional
        # and visible: callers compare len(tasks) against planned_task_count
        # and the manifest records requested counts per benchmark.
        for index in indices:
            tasks.append(spec.build(index, dataset[index]))
    return tasks


def sample_report(config: dict[str, Any], dataset_sizes: dict[str, int]) -> dict:
    """Requested vs dataset-capped sample counts, for the manifest."""
    samples = config["samples_per_benchmark"]
    return {
        benchmark: {
            "requested": int(k),
            "dataset_size": dataset_sizes.get(benchmark),
            "drawn": min(int(k), dataset_sizes.get(benchmark, int(k))),
        }
        for benchmark, k in samples.items()
    }


def planned_task_count(config: dict[str, Any]) -> int:
    """Total tasks planned = sum of configured per-benchmark samples."""
    return sum(int(k) for k in config["samples_per_benchmark"].values())
