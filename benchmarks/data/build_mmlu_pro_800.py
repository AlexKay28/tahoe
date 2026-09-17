#!/usr/bin/env python3
"""Build benchmarks/data/mmlu_pro_800.jsonl — stratified MMLU-Pro subset.

Proportional allocation across the 14 categories (largest-remainder method),
fixed seed 42, sampled ONCE and committed — never resampled per run.

Source: HF TIGER-Lab/MMLU-Pro (test split, 12,032 questions, 10 options).

Usage:
    python3 benchmarks/data/build_mmlu_pro_800.py
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from datasets import load_dataset

OUT = Path(__file__).parent / "mmlu_pro_800.jsonl"
N = 800
SEED = 42


def largest_remainder(counts, total):
    """Proportional allocation that sums exactly to total."""
    cat_total = sum(counts.values())
    raw = {c: counts[c] * total / cat_total for c in counts}
    base = {c: int(v) for c, v in raw.items()}
    leftover = total - sum(base.values())
    fracs = sorted(raw, key=lambda c: raw[c] - base[c], reverse=True)
    for c in fracs[:leftover]:
        base[c] += 1
    return base


def main():
    ds = load_dataset("TIGER-Lab/MMLU-Pro", split="test")
    by_cat = defaultdict(list)
    for i, ex in enumerate(ds):
        by_cat[ex["category"]].append(i)

    alloc = largest_remainder(Counter({c: len(v) for c, v in by_cat.items()}), N)
    rng = random.Random(SEED)

    records = []
    for cat in sorted(by_cat):
        picked = rng.sample(by_cat[cat], alloc[cat])
        for idx in picked:
            ex = ds[idx]
            records.append({
                "task_id": f"mmlupro-{ex['question_id']:05d}",
                "category": ex["category"],
                "question": ex["question"],
                "options": ex["options"],
                "expected": ex["answer"],
                "source_index": idx,
            })

    assert len(records) == N, f"expected {N}, got {len(records)}"
    n_opts = Counter(len(r["options"]) for r in records)
    assert all(3 <= k <= 10 for k in n_opts), f"unexpected option counts: {n_opts}"

    with OUT.open("w") as f:
        for r in sorted(records, key=lambda x: x["task_id"]):
            f.write(json.dumps(r, ensure_ascii=True) + "\n")

    dist = Counter(r["expected"] for r in records)
    print(f"wrote {len(records)} records to {OUT}")
    print("category allocation:", dict(sorted(alloc.items())))
    print(f"answer letter distribution: {dict(sorted(dist.items()))}")


if __name__ == "__main__":
    sys.exit(main())
