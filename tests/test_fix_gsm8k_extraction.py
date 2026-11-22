"""Focused tests for the derived-results GSM8K regrade pipeline.

The legacy workflow (benchmarks/fix_gsm8k_extraction.py with no arguments,
mutating hardcoded files under benchmarks/results/ in place) is gone. Its
replacement is a derived-results pipeline in benchmarks/gsm8k_regrade.py,
pinned here against regressions:

- the raw input archive is never modified (byte-for-byte);
- ``--input``/``--output`` are explicit; a legacy no-argument invocation
  fails with a helpful message and does not touch old locations;
- an existing output is refused via atomic exclusive create;
- missing/malformed archived ``expected=`` values become explicit
  ``grader_error`` results, never silent passes;
- the corrected numeric behavior ('#### 42.00' answer vs gold '42') flips
  wrongly-failed archived trials to passed;
- original verdicts are preserved as ``archived_passed`` /
  ``archived_failure_class`` / ``archived_grader_detail`` and raw
  ``final_answer`` values are carried through unchanged;
- the derived artifact is byte-deterministic and records the grader
  version plus SHA-256 hashes of the source archive and grader source.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "src"))

import benchmarks.gsm8k_regrade as rg  # noqa: E402

SCRIPT = ROOT / "benchmarks" / "fix_gsm8k_extraction.py"


def run_cli(*args, cwd=ROOT):
    """Run the regrade CLI exactly as a user would (subprocess, no imports)."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_archive() -> list:
    """A small archived results list covering every derived-verdict case."""
    return [
        {
            # Old string comparison failed '42.00' vs gold '42'; the current
            # numeric grade_gsm8k must correct this to a pass.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0001",
            "arm": "classic",
            "final_answer": "She has 42.00 dollars left.\n#### 42.00",
            "passed": False,
            "failure_class": "wrong_answer",
            "grader_detail": "expected=42, got=42.00",
            "quality_score": 0.0,
        },
        {
            # Genuinely wrong answer stays wrong.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0002",
            "arm": "classic",
            "final_answer": "#### 41",
            "passed": False,
            "failure_class": "wrong_answer",
            "grader_detail": "expected=42, got=41",
            "quality_score": 0.0,
        },
        {
            # Archived false pass: the old extractor matched the wrong tail
            # of '1,430'; the current grader marks it wrong.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0003",
            "arm": "tahoe",
            "final_answer": "The total is 1,430 but he paid 1,300.\n#### 1300",
            "passed": True,
            "failure_class": "none",
            "grader_detail": "expected=1430, got=1430",
            "quality_score": 1.0,
        },
        {
            # Malformed expected value (present in real archives:
            # 'expected=, got=3') -> explicit grader_error, never a pass.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0004",
            "arm": "classic",
            "final_answer": "#### 3",
            "passed": True,
            "failure_class": "none",
            "grader_detail": "expected=, got=3",
            "quality_score": 1.0,
        },
        {
            # Missing grader_detail entirely -> explicit grader_error.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0005",
            "arm": "tahoe",
            "final_answer": "#### 100",
            "passed": True,
            "failure_class": "none",
            "grader_detail": None,
            "quality_score": 1.0,
        },
        {
            # Thousands-separated gold, still passing.
            "benchmark": "gsm8k",
            "task_id": "gsm8k-0006",
            "arm": "tahoe",
            "final_answer": r"The cost is \boxed{43{,}200} dollars.",
            "passed": True,
            "failure_class": "none",
            "grader_detail": "expected=43,200, got=43200",
            "quality_score": 1.0,
        },
        {
            # Non-GSM8K trial: filtered out of the derived artifact.
            "benchmark": "arc",
            "task_id": "arc-0001",
            "arm": "classic",
            "final_answer": "C",
            "passed": True,
            "failure_class": "none",
            "grader_detail": "expected=C, got=C",
            "quality_score": 1.0,
        },
    ]


class TestExtractExpectedGold:
    def test_plain_number(self):
        gold, reason = rg.extract_expected_gold("expected=42, got=42.00")
        assert gold == "42"
        assert reason == ""

    def test_decimal_and_thousands_separators(self):
        gold, _ = rg.extract_expected_gold("expected=43,200, got=43200")
        assert gold == "43200"
        gold, _ = rg.extract_expected_gold("expected=1,430.50, got=1430.5")
        assert gold == "1430.50"

    def test_negative_and_dollar(self):
        gold, _ = rg.extract_expected_gold("expected=$-10, got=-10")
        assert gold == "-10"

    def test_empty_expected_is_malformed(self):
        gold, reason = rg.extract_expected_gold("expected=, got=3")
        assert gold is None
        assert "malformed" in reason or "parseable" in reason

    def test_missing_detail_is_malformed(self):
        gold, reason = rg.extract_expected_gold(None)
        assert gold is None
        assert "missing" in reason

    def test_non_numeric_expected_is_malformed(self):
        gold, reason = rg.extract_expected_gold("expected=abc, got=3")
        assert gold is None
        assert reason


class TestRegradeTrial:
    def test_corrected_42_00_flips_to_pass(self):
        trial = sample_archive()[0]
        out = rg.regrade_trial(trial)
        assert out["passed"] is True
        assert out["failure_class"] == "none"
        assert out["quality_score"] == 1.0
        assert out["grader_detail"] == "expected=42, got=42.00"

    def test_wrong_answer_stays_wrong(self):
        out = rg.regrade_trial(sample_archive()[1])
        assert out["passed"] is False
        assert out["failure_class"] == "wrong_answer"
        assert out["quality_score"] == 0.0

    def test_malformed_expected_is_explicit_grader_error(self):
        out = rg.regrade_trial(sample_archive()[3])
        assert out["passed"] is False  # never a silent pass
        assert out["failure_class"] == "grader_error"
        assert out["grader_detail"].startswith("grader_error: ")
        assert out["quality_score"] == 0.0

    def test_missing_grader_detail_is_explicit_grader_error(self):
        out = rg.regrade_trial(sample_archive()[4])
        assert out["passed"] is False
        assert out["failure_class"] == "grader_error"

    def test_original_verdicts_preserved_final_answer_unchanged(self):
        for trial in sample_archive()[:6]:
            out = rg.regrade_trial(trial)
            assert out["archived_passed"] == trial["passed"]
            assert out["archived_failure_class"] == trial["failure_class"]
            assert out["archived_grader_detail"] == trial["grader_detail"]
            assert out["final_answer"] == trial["final_answer"]

    def test_input_trial_not_mutated(self):
        trial = sample_archive()[0]
        snapshot = dict(trial)
        rg.regrade_trial(trial)
        assert trial == snapshot

    def test_verdict_flip_pass_to_fail(self):
        out = rg.regrade_trial(sample_archive()[2])  # archived True, actually wrong
        assert out["passed"] is False
        assert out["archived_passed"] is True


class TestPayload:
    def _payload(self):
        with open(ROOT / "benchmarks" / "run_public_bench.py", "rb") as f:
            grader_sha = rg.sha256_bytes(f.read())
        return rg.build_payload(
            sample_archive(),
            source_sha256="a" * 64,
            grader_sha256=grader_sha,
        ), grader_sha

    def test_manifest_records_version_and_hashes(self):
        payload, grader_sha = self._payload()
        manifest = payload["manifest"]
        assert manifest["schema"] == rg.SCHEMA
        assert manifest["grader_version"] == rg.GRADER_VERSION
        assert manifest["grader"]["sha256"] == grader_sha
        assert manifest["grader"]["source"] == "benchmarks/run_public_bench.py"
        assert manifest["source_archive_sha256"] == "a" * 64

    def test_only_gsm8k_trials_kept_in_input_order(self):
        payload, _ = self._payload()
        trials = payload["trials"]
        assert [t["task_id"] for t in trials] == [
            "gsm8k-0001", "gsm8k-0002", "gsm8k-0003",
            "gsm8k-0004", "gsm8k-0005", "gsm8k-0006",
        ]
        assert all(t["benchmark"] == "gsm8k" for t in trials)

    def test_summary_counts(self):
        payload, _ = self._payload()
        summary = payload["manifest"]["summary"]
        assert summary["gsm8k_trials"] == 6
        assert summary["skipped_non_gsm8k"] == 1
        assert summary["passed"] == 2  # 0001 (corrected) and 0006
        assert summary["wrong_answer"] == 2  # 0002 and the flipped 0003
        assert summary["grader_errors"] == 2  # 0004 malformed, 0005 missing
        # 0001 flips to pass; 0003 flips to fail; the malformed 0004
        # (archived pass -> grader_error) is NOT counted as a verdict change.
        assert summary["verdict_changes"] == {
            "fail_to_pass": 1,
            "pass_to_fail": 1,
        }

    def test_deterministic_rendering(self):
        payload, _ = self._payload()
        assert rg.render_payload(payload) == rg.render_payload(payload)
        text = rg.render_payload(payload)
        assert text.endswith("\n")
        assert "timestamp" not in text
        assert str(ROOT) not in text  # no host-absolute paths


class TestWriteExclusive:
    def test_creates_parents_and_file(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "derived.json"
        rg.write_exclusive(out, "{}\n")
        assert out.read_text() == "{}\n"

    def test_refuses_existing_file(self, tmp_path):
        out = tmp_path / "derived.json"
        out.write_text("sentinel")
        with pytest.raises(rg.RegradeError, match="refusing to overwrite"):
            rg.write_exclusive(out, "{}\n")
        assert out.read_text() == "sentinel"  # existing bytes untouched


class TestCliSafety:
    """The end-to-end CLI contract: explicit paths, immutable input."""

    def _archive(self, tmp_path) -> Path:
        path = tmp_path / "archive.json"
        path.write_text(json.dumps(sample_archive(), indent=2) + "\n")
        return path

    def test_legacy_invocation_fails_helpfully(self):
        result = run_cli()
        assert result.returncode != 0
        assert "--input" in result.stderr
        assert "--output" in result.stderr
        assert "in place" in result.stderr

    def test_legacy_invocation_mutates_nothing(self):
        """No file under benchmarks/results/ may change on a legacy call."""
        results = ROOT / "benchmarks" / "results"
        before = {
            p: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in results.rglob("*")
            if p.is_file()
        }
        result = run_cli()
        assert result.returncode != 0
        after = {
            p: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in results.rglob("*")
            if p.is_file()
        }
        assert before == after

    def test_input_archive_bytes_unchanged(self, tmp_path):
        archive = self._archive(tmp_path)
        before = archive.read_bytes()
        out = tmp_path / "sub" / "derived.json"
        result = run_cli("--input", str(archive), "--output", str(out))
        assert result.returncode == 0, result.stderr
        assert archive.read_bytes() == before
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["manifest"]["summary"]["gsm8k_trials"] == 6
        # final answers carried through unchanged
        originals = {t["task_id"]: t["final_answer"] for t in sample_archive()}
        derived = {t["task_id"]: t["final_answer"] for t in payload["trials"]}
        assert derived == {k: v for k, v in originals.items() if k.startswith("gsm8k")}

    def test_refuses_existing_output(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        out.write_text("do not clobber\n")
        result = run_cli("--input", str(archive), "--output", str(out))
        assert result.returncode != 0
        assert "refusing to overwrite" in result.stderr
        assert out.read_text() == "do not clobber\n"

    def test_missing_input_is_an_error(self, tmp_path):
        result = run_cli(
            "--input", str(tmp_path / "nope.json"),
            "--output", str(tmp_path / "out.json"),
        )
        assert result.returncode != 0
        assert "input archive not found" in result.stderr
        assert not (tmp_path / "out.json").exists()

    def test_output_equal_to_input_refused(self, tmp_path):
        archive = self._archive(tmp_path)
        result = run_cli("--input", str(archive), "--output", str(archive))
        assert result.returncode != 0
        assert "never modified" in result.stderr

    def test_missing_explicit_paths_is_a_usage_error(self):
        result = run_cli("--input", "x.json")  # --output omitted
        assert result.returncode != 0
        assert "--output" in result.stderr

    def test_deterministic_output_bytes(self, tmp_path):
        archive = self._archive(tmp_path)
        out1 = tmp_path / "run1.json"
        out2 = tmp_path / "run2.json"
        assert run_cli("--input", str(archive), "--output", str(out1)).returncode == 0
        assert run_cli("--input", str(archive), "--output", str(out2)).returncode == 0
        assert out1.read_bytes() == out2.read_bytes()

    def test_manifest_hashes_match_real_files(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        assert run_cli("--input", str(archive), "--output", str(out)).returncode == 0
        payload = json.loads(out.read_text())
        manifest = payload["manifest"]
        assert manifest["source_archive_sha256"] == sha256_of(archive)
        assert manifest["grader"]["sha256"] == sha256_of(
            ROOT / "benchmarks" / "run_public_bench.py"
        )
        assert manifest["grader_version"] == rg.GRADER_VERSION

    def test_run_metadata_sidecar_separate_from_payload(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        meta = tmp_path / "meta.json"
        result = run_cli(
            "--input", str(archive), "--output", str(out), "--run-metadata", str(meta)
        )
        assert result.returncode == 0, result.stderr
        payload_text = out.read_text()
        assert "generated_at_utc" not in payload_text  # deterministic payload
        assert str(archive) not in payload_text
        run_meta = json.loads(meta.read_text())
        assert "generated_at_utc" in run_meta
        assert run_meta["input"].endswith("archive.json")

    def test_corrected_42_00_via_cli(self, tmp_path):
        archive = self._archive(tmp_path)
        out = tmp_path / "derived.json"
        assert run_cli("--input", str(archive), "--output", str(out)).returncode == 0
        by_id = {t["task_id"]: t for t in json.loads(out.read_text())["trials"]}
        fixed = by_id["gsm8k-0001"]
        assert fixed["passed"] is True
        assert fixed["failure_class"] == "none"
        assert fixed["quality_score"] == 1.0
        assert fixed["archived_passed"] is False
        assert fixed["archived_failure_class"] == "wrong_answer"
        assert fixed["archived_grader_detail"] == "expected=42, got=42.00"
        malformed = by_id["gsm8k-0004"]
        assert malformed["failure_class"] == "grader_error"
        assert malformed["passed"] is False
        assert malformed["grader_detail"].startswith("grader_error:")
