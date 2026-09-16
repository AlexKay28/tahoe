#!/usr/bin/env python3
"""Build benchmarks/data/aime60.jsonl — AIME 2024 + 2025 (60 problems).

Source: the corp Harbor adapter's exact problem URLs
(ml/zeliboba/alignment/tool_calling/harbor_bench/src/adapters/aime),
which pulls from GAIR-NLP/AIME-Preview:
  test2024.jsonl (30) + test2025-I.jsonl (15) + test2025-II.jsonl (15).

Usage:
    python3 benchmarks/data/build_aime60.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

JSON_URLS = [
    "https://raw.githubusercontent.com/GAIR-NLP/AIME-Preview/main/eval/data/aime/test2024.jsonl",
    "https://raw.githubusercontent.com/GAIR-NLP/AIME-Preview/main/eval/data/aime/test2025-I.jsonl",
    "https://raw.githubusercontent.com/GAIR-NLP/AIME-Preview/main/eval/data/aime/test2025-II.jsonl",
]
OUT = Path(__file__).parent / "aime60.jsonl"


def main():
    records = []
    with tempfile.TemporaryDirectory() as tmp:
        for url in JSON_URLS:
            name = url.split("/")[-1]
            path = Path(tmp) / name
            subprocess.run(["curl", "-sL", url, "-o", str(path)], check=True)
            rows = [json.loads(l) for l in path.read_text().split("\n") if l.strip()]
            records.extend(rows)

    assert len(records) == 60, f"expected 60 problems, got {len(records)}"
    for r in records:
        r["expected"] = str(int(r["answer"]))  # normalize to integer string 0-999

    with OUT.open("w") as f:
        for i, r in enumerate(records):
            f.write(json.dumps({
                "task_id": f"aime-{i:04d}",
                "source_id": r.get("id"),
                "problem": r["problem"],
                "expected": r["expected"],
            }, ensure_ascii=True) + "\n")
    print(f"wrote {len(records)} records to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
