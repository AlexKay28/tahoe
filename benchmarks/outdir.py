"""Run-directory helper: every experiment writes into its own directory.

Lesson from the 2026-09-14 session (twice): a later run overwrote an earlier
run's raw data, destroying comparability. Runners must never write to a fixed
filename at the results root.

Usage:
    from outdir import make_run_dir, write_manifest
    out_dir = make_run_dir("skill-cmp-gsm8k")
    # -> benchmarks/results/runs/2026-09-14T2259_skill-cmp-gsm8k/
    write_manifest(out_dir, config={...}, source_files=[...])
    (out_dir / "trials.json").write_text(...)

``make_run_dir`` is exclusive: if the timestamped name already exists, a
``-2``, ``-3``, ... suffix is appended and the directory is created with
``exist_ok=False``, so a run can never silently overwrite an earlier run.
``write_manifest`` records the run's configuration and sha256 hashes of the
source files that produced it (never secrets) via an exclusive create.

Set RESULTS_ROOT to relocate; set RUN_TAG to label the directory.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

RESULTS_ROOT = Path(
    os.environ.get(
        "RESULTS_ROOT",
        Path(__file__).resolve().parent / "results",
    )
)


def make_run_dir(name: str, results_root: Path | None = None) -> Path:
    """Create and return a unique run directory under results/runs/.

    The base name is ``<UTC-stamp>_<name>[_<RUN_TAG>]``; when that name
    already exists (e.g. two runs started within the same minute), a
    ``-2``, ``-3``, ... suffix is appended. Creation is exclusive, so the
    returned directory is always freshly created and can never overwrite
    an earlier run's directory.
    """
    root = Path(results_root) if results_root else RESULTS_ROOT
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    tag = os.environ.get("RUN_TAG", "")
    base = f"{stamp}_{name}" + (f"_{tag}" if tag else "")
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    run_dir = runs / base
    suffix = 1
    while True:
        try:
            run_dir.mkdir(exist_ok=False)
            return run_dir
        except FileExistsError:
            run_dir = runs / f"{base}-{suffix}"
            suffix += 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    run_dir: Path | str,
    config: dict | None = None,
    source_files: list[str | Path] | None = None,
) -> Path:
    """Write an exclusive ``manifest.json`` into a run directory.

    The manifest records when the run directory was created, the caller's
    configuration dict (callers must never put secrets such as API keys
    in it) and sha256 hashes of the given source files (the runner
    script, the inference runner, graders, ...). The file is opened
    exclusively (mode ``"x"``): writing into an existing manifest path
    raises ``FileExistsError`` instead of overwriting it.
    """
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": dict(config or {}),
        "source_hashes": {
            str(Path(p).name): _sha256_file(Path(p))
            for p in (source_files or [])
        },
    }
    manifest_path = Path(run_dir) / "manifest.json"
    with open(manifest_path, "x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest_path
