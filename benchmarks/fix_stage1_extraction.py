#!/usr/bin/env python3
"""Re-grade all ten archived Stage-1 benchmarks into a fresh derived artifact.

The 2026-09-13 stage1-full archives were graded with graders that
under-credited correct answers: GSM8K string-compared the gold ('42.00' vs
'42', '1{,}430' split as '430'), ARC compared model letters against raw
numeric answerKeys ('C' vs '3'), BBH expected values kept their '(G)' parens,
and MMLU trials were graded as letters where the CURRENT grader expects the
integer choice index. This tool re-grades every trial of an archived
results file with the CURRENT grader functions from
``benchmarks/run_public_bench.py``, using the expected answers recorded in
the archived ``grader_detail`` strings.

Outcome preservation: the archives document max_tokens=2048 but carry no
finish_reason. The derived artifact records ``output_token_cap=2048`` and a
``cap_exhausted`` flag derived from ``output_tokens >= 2048``; it never
invents a finish_reason and never sets a truncated flag from the exact cap
alone. Empty/missing final answers fail as ``empty_response``; nonempty
cap-exhausted answers that fail grading are classified ``truncated`` with
an explicit outcome provenance.

Safety model (this workflow is derived-only; nothing runs in place):

- ``--input`` and ``--output`` are explicit and required. There are no
  hardcoded result paths and a no-argument invocation refuses to run
  instead of mutating old locations.
- The raw input archive is opened read-only and is NEVER modified; raw
  ``final_answer`` values are carried through unchanged.
- An existing ``--output`` is refused (atomic exclusive create); the output
  parent directory is created if missing.
- Original verdicts are preserved as ``archived_passed`` /
  ``archived_failure_class`` / ``archived_grader_detail`` next to the derived
  ``passed`` / ``failure_class`` / ``grader_detail`` / ``quality_score``.
- Missing, malformed or inconsistent expected values — and grader
  exceptions — become explicit ``grader_error`` results, never silent
  passes.
- The derived artifact is byte-deterministic and records the spec and
  regrader versions plus SHA-256 hashes of the source archive and grader
  source; timestamps/paths go to the optional ``--run-metadata`` sidecar.

Usage:
  PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \\
      --input  benchmarks/results/2026-09-13-stage1-full/full_test_eval.json \\
      --output benchmarks/results/derived/<fresh>.json \\
      [--run-metadata <sidecar .json>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from benchmarks.stage1_regrade import RegradeError, run_pipeline
except ImportError:
    from stage1_regrade import RegradeError, run_pipeline

EXIT_USAGE = 2
EXIT_ERROR = 1

_LEGACY_MESSAGE = """\
This tool re-grades archived Stage-1 trials only into NEW derived files.

There are no hardcoded result paths: mutating raw archives destroys the
provenance of every published number derived from them, and this tool
refuses to run without explicit paths.

Derived-results usage (the raw input archive is never modified):

    PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py \\
        --input  <archived results .json> \\
        --output <fresh derived .json> [--run-metadata <sidecar .json>]

Existing --output files are refused; pick a new path for each run.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fix_stage1_extraction.py",
        description=(
            "Re-grade all ten archived Stage-1 benchmarks with the current "
            "graders into a new derived artifact (the input archive is "
            "never modified)."
        ),
        epilog=(
            "Example: PYTHONPATH=src python3 benchmarks/fix_stage1_extraction.py "
            "--input benchmarks/results/<archive>.json --output <derived>.json"
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="ARCHIVE_JSON",
        help="existing archived results JSON file (read-only, never modified)",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="DERIVED_JSON",
        help="fresh path for the derived artifact; must not already exist",
    )
    parser.add_argument(
        "--run-metadata",
        metavar="SIDECAR_JSON",
        help=(
            "optional sidecar for run metadata (timestamps, absolute paths); "
            "kept out of the deterministic derived artifact"
        ),
    )
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(_LEGACY_MESSAGE, file=sys.stderr, end="")
        return EXIT_USAGE

    args = build_parser().parse_args(argv)
    try:
        manifest = run_pipeline(
            Path(args.input),
            Path(args.output),
            Path(args.run_metadata) if args.run_metadata else None,
        )
    except RegradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    summary = manifest["summary"]
    changes = summary["verdict_changes"]
    print(
        f"stage-1 trials re-graded: {summary['trials']} "
        f"(passed={summary['passed']})"
    )
    print(
        "failure classes: "
        + ", ".join(
            f"{name}={count}"
            for name, count in sorted(summary["failure_classes"].items())
        )
    )
    for bench in sorted(manifest["benchmarks"]):
        bench_summary = manifest["benchmarks"][bench]
        print(
            f"  {bench}: trials={bench_summary['trials']} "
            f"passed={bench_summary['passed']} "
            f"classes={ {k: v for k, v in sorted(bench_summary['failure_classes'].items())} }"
        )
    print(
        f"verdict changes: fail_to_pass={changes['fail_to_pass']} "
        f"pass_to_fail={changes['pass_to_fail']}"
    )
    print(f"wrote derived artifact: {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
