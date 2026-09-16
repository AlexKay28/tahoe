#!/usr/bin/env python3
"""Build benchmarks/data/gpqa_diamond.jsonl from the corp YT table.

Source: //home/instruboba/quality/benchmarks/exam_A/GPQA/gpqa_diamond (hahn)
        — the raw official table with all 198 questions. The processed
        gpqa_diamond_gpt_202 table drops 2 rows (196) and is NOT used.

Options are shuffled deterministically with seed 42 (same convention as the
corp Harbor adapter), letters A-D assigned, correct letter recorded.

Usage:
    YT_PROXY=hahn python3 benchmarks/data/build_gpqa_diamond.py
"""
import json
import random
import subprocess
import sys
from pathlib import Path

YT_TABLE = "//home/instruboba/quality/benchmarks/exam_A/GPQA/gpqa_diamond"
OUT = Path(__file__).parent / "gpqa_diamond.jsonl"
SEED = 42


def read_yt_table(path):
    out = subprocess.run(
        ["yt", "read", path, "--format", "json"],
        capture_output=True, check=True,
    )
    # split on \n only: str.splitlines() would also split on U+2028/U+2029
    # line separators that occur inside GPQA question text
    text = out.stdout.decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line.strip()]


def main():
    rows = read_yt_table(YT_TABLE)
    assert len(rows) == 198, f"expected 198 rows, got {len(rows)}"

    rng = random.Random(SEED)
    records = []
    for i, r in enumerate(rows):
        options = [r["Correct Answer"], r["Incorrect Answer 1"],
                   r["Incorrect Answer 2"], r["Incorrect Answer 3"]]
        correct_text = options[0]
        order = list(range(4))
        rng.shuffle(order)
        shuffled = [options[j] for j in order]
        letter = chr(ord("A") + shuffled.index(correct_text))
        records.append({
            "task_id": f"gpqa-{i:04d}",
            "record_id": r.get("Record ID", ""),
            "subject": r.get("High-level domain", ""),
            "question": r["Question"],
            "options": shuffled,
            "expected": letter,
            "answer_text": correct_text,
        })

    OUT.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in records))
    dist = {}
    for rec in records:
        dist[rec["expected"]] = dist.get(rec["expected"], 0) + 1
    print(f"wrote {len(records)} records to {OUT}")
    print(f"answer letter distribution: {dist}")


if __name__ == "__main__":
    sys.exit(main())
