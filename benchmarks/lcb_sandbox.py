#!/usr/bin/env python3
"""LiveCodeBench execution sandbox (issue #99).

No docker needed: each trial gets a scratch dir with config.json (test cases)
+ solution.py (the model's emitted code), and the corp-parity verifier
(`verifiers/lcb/final_test.py`, copied verbatim) runs in a subprocess that is
- network-isolated (`unshare -n`, root has CAP_SYS_ADMIN here),
- hard-timeboxed (`timeout -k`),
- arm-agnostic: the ONLY input is the model's answer text.

The model answer is not trusted as a path or a shell argument — it is written
to solution.py and executed by the verifier, nothing else.
"""
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

VERIFIER = Path(__file__).parent / "verifiers" / "lcb" / "final_test.py"
PROBLEM_TIMEOUT_S = 300


def extract_code(model_answer: str) -> str:
    """Arm-agnostic code extraction: last ```python fenced block, else the
    whole answer."""
    blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", model_answer, re.S)
    if blocks:
        return blocks[-1].strip() + "\n"
    return model_answer.strip() + "\n"


def run_lcb_trial(problem: dict, model_answer: str, timeout_s: int = PROBLEM_TIMEOUT_S) -> dict:
    """Returns {passed, failure_class, summary, failed_tests}."""
    workdir = Path(tempfile.mkdtemp(prefix=f"lcb-{problem['task_id']}-{uuid.uuid4().hex[:6]}-"))
    result = {"passed": False, "failure_class": "none", "summary": "", "failed_tests": []}
    try:
        shutil.copy(VERIFIER, workdir / "final_test.py")
        (workdir / "config.json").write_text(json.dumps({
            "public_test_cases": problem["public_test_cases"],
            "private_test_cases": problem["private_test_cases"],
            "metadata": problem["metadata"],
        }))
        (workdir / "solution.py").write_text(extract_code(model_answer))

        proc = subprocess.run(
            ["sudo", "-n", "unshare", "-n", "timeout", "-k", "5", str(timeout_s),
             "python3", "final_test.py"],
            cwd=workdir, capture_output=True, text=True, timeout=timeout_s + 30,
        )
        out = proc.stdout
        result["summary"] = (out.splitlines()[-1] if out.strip() else "")[:200]

        if proc.returncode == 124 or "timeout" in proc.stderr.lower()[:200]:
            result["failure_class"] = "timeout"
        m = re.search(r"(\d+) failed, (\d+) passed", out)
        if "TASK PASSED" in out:
            result["passed"] = True
        elif m:
            failed_n = int(m.group(1))
            result["passed"] = failed_n == 0
            if failed_n:
                result["failure_class"] = "wrong_answer"
                result["failed_tests"] = re.findall(r"FAILED (\S+)", out)[:10]
        elif "ERROR" in out[:200]:
            result["failure_class"] = "verifier_error"
        elif proc.returncode != 0:
            result["failure_class"] = "verifier_error"
        return result
    except subprocess.TimeoutExpired:
        result["failure_class"] = "timeout"
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    # smoke: run the committed dataset's first problem against a deliberately
    # wrong solution (must fail) — real correctness validation lives in the
    # harness unit tests
    rows = [json.loads(l) for l in
            (Path(__file__).parent / "data" / "lcb_v6_150.jsonl").read_text().split("\n") if l.strip()]
    r = run_lcb_trial(rows[0], "def solve():\n    pass\n")
    print("known-bad ->", r)
