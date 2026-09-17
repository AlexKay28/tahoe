#!/usr/bin/env python3
"""Build benchmarks/data/lcb_v6_150.jsonl — LiveCodeBench release_v6 subset.

The 150 NEWEST problems by contest date (Jan-Apr 2025 window, closest to the
model's training cutoff — the newest the public artifact offers). Contamination
applies equally to both arms; the A/B delta remains internally valid.

Source: HF livecodebench/code_generation_lite, file test6.jsonl (same data the
corp Harbor adapter uses via its release_v6 config).

Usage:
    python3 benchmarks/data/build_lcb_v6_150.py
"""
import json
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

OUT = Path(__file__).parent / "lcb_v6_150.jsonl"
N = 150


def main():
    path = hf_hub_download("livecodebench/code_generation_lite", "test6.jsonl", repo_type="dataset")
    rows = [json.loads(l) for l in open(path) if l.strip()]

    rows.sort(key=lambda r: r["contest_date"], reverse=True)
    picked = rows[:N]

    # prefer problems whose test-type mix won't blow the wall-clock:
    # functional tests run in-process; stdin tests spawn a subprocess each
    for r in picked:
        public = json.loads(r["public_test_cases"])
        r["_n_public"] = len(public)
        r["_n_functional_public"] = sum(1 for t in public if t.get("testtype") == "functional")

    with OUT.open("w") as f:
        for i, r in enumerate(picked):
            f.write(json.dumps({
                "task_id": f"lcb-{i:04d}",
                "question_title": r["question_title"],
                "platform": r["platform"],
                "difficulty": r["difficulty"],
                "contest_date": r["contest_date"],
                "question_content": r["question_content"],
                "starter_code": r["starter_code"],
                "public_test_cases": r["public_test_cases"],
                "private_test_cases": r["private_test_cases"],
                "metadata": r["metadata"],
            }, ensure_ascii=True) + "\n")

    from collections import Counter
    print(f"wrote {len(picked)} records to {OUT}")
    print("difficulty:", dict(Counter(r["difficulty"] for r in picked)))
    print("date range:", picked[-1]["contest_date"], "->", picked[0]["contest_date"])


if __name__ == "__main__":
    sys.exit(main())
