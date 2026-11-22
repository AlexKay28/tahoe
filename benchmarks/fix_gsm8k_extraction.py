#!/usr/bin/env python3
"""Re-grade archived GSM8K trials into a fresh derived-results artifact.

The old extractor split comma/LaTeX-formatted numbers ('1{,}430', '2\\,000',
'$2,180' -> '430'/'000'/'180') and the old string comparison under-credited
verbose answers ('#### 42.00' vs gold '42'). This tool re-grades the GSM8K
trials of an archived results file with the CURRENT ``grade_gsm8k``
implementation (benchmarks/run_public_bench.py).

Safety model (this workflow is derived-only; nothing runs in place):

- ``--input`` and ``--output`` are explicit and required. There are no
  hardcoded result paths and the legacy no-argument invocation refuses to
  run instead of mutating old locations.
- The raw input archive is opened read-only and is NEVER modified; raw
  ``final_answer`` values are carried through unchanged.
- An existing ``--output`` is refused (atomic exclusive create); the output
  parent directory is created if missing.
- Original verdicts are preserved as ``archived_passed`` /
  ``archived_failure_class`` / ``archived_grader_detail`` next to the derived
  ``passed`` / ``failure_class`` / ``grader_detail`` / ``quality_score``.
- Missing or malformed archived ``expected=`` values become explicit
  ``grader_error`` results, never silent passes.
- The derived artifact is byte-deterministic and contains the grader
  version plus SHA-256 hashes of the source archive and grader source;
  timestamps/paths go to the optional ``--run-metadata`` sidecar.

Usage:
  PYTHONPATH=src python3 benchmarks/fix_gsm8k_extraction.py \\
      --input  benchmarks/results/2026-09-14-skill-study/skill_cmp_gsm8k.json \\
      --output benchmarks/results/derived/skill_cmp_gsm8k.regraded.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from benchmarks.gsm8k_regrade import RegradeError, run_pipeline
except ImportError:
    from gsm8k_regrade import RegradeError, run_pipeline

EXIT_USAGE = 2
EXIT_ERROR = 1

_LEGACY_MESSAGE = """\
This tool no longer re-grades results in place.

The legacy invocation (no arguments, rewriting hardcoded files under
benchmarks/results/) has been removed: mutating raw archives destroys the
provenance of every published number derived from them.

Derived-results usage (the raw input archive is never modified):

    PYTHONPATH=src python3 benchmarks/fix_gsm8k_extraction.py \\
        --input  <archived results .json> \\
        --output <fresh derived .json> [--run-metadata <sidecar .json>]

Existing --output files are refused; pick a new path for each run.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fix_gsm8k_extraction.py",
        description=(
            "Re-grade archived GSM8K trials with the current grader into a "
            "new derived artifact (the input archive is never modified)."
        ),
        epilog=(
            "Example: PYTHONPATH=src python3 benchmarks/fix_gsm8k_extraction.py "
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
        # Legacy invocation: fail loudly with the new usage rather than
        # touching any result file.
        print(_LEGACY_MESSAGE, file=sys.stderr, end="")
        return EXIT_USAGE

    args = build_parser().parse_args(argv)
    try:
        summary = run_pipeline(
            Path(args.input),
            Path(args.output),
            Path(args.run_metadata) if args.run_metadata else None,
        )
    except RegradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    changes = summary["verdict_changes"]
    print(
        f"gsm8k trials re-graded: {summary['gsm8k_trials']} "
        f"(skipped {summary['skipped_non_gsm8k']} non-gsm8k)"
    )
    print(
        f"derived verdicts: passed={summary['passed']} "
        f"wrong_answer={summary['wrong_answer']} "
        f"grader_errors={summary['grader_errors']}"
    )
    print(
        f"verdict changes: fail_to_pass={changes['fail_to_pass']} "
        f"pass_to_fail={changes['pass_to_fail']}"
    )
    print(f"wrote derived artifact: {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
