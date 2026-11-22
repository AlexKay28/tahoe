"""Tests for benchmarks/render_canonical_docs.py — canonical payload renderer.

The renderer consumes canonical-results JSON payloads (schema
canonical-results/1) emitted by ``benchmarks/canonical_results.py`` and
must render identical numbers into Markdown and LaTeX from the SAME
payload, update explicitly marked blocks in text files deterministically,
and never modify the canonical payload itself.

Payloads are generated offline from the committed fixture with fast
statistics counts.  No model evaluations run anywhere in this module.
"""

import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.canonical_results import main as canonical_main
from benchmarks.render_canonical_docs import (
    MD_BEGIN_TEMPLATE,
    MD_END_TEMPLATE,
    RenderError,
    TEX_BEGIN_TEMPLATE,
    TEX_END_TEMPLATE,
    main,
    render_block,
    render_latex_fragment,
    render_markdown_document,
    split_block_name,
    validate_payload,
)

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_trials.json"
ROOT = Path(__file__).resolve().parents[1]
FAST = ("--seed", "123", "--n-resamples", "200", "--n-permutations", "200")


# -- helpers --------------------------------------------------------------


def _make_payload(tmp_path, trials=FIXTURE, name="payload", flags=()):
    out = tmp_path / name
    assert canonical_main(
        [str(trials), "-o", str(out), *FAST, *flags]
    ) == 0
    return out / "canonical_results.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _md_rows(doc):
    rows = []
    for line in doc.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if set(stripped) <= {"|", "-", " ", ":"}:
            continue  # table rule line
        rows.append([cell.strip() for cell in stripped[1:-1].split("|")])
    return rows


def _tex_rows(fragment):
    rows = []
    for line in fragment.splitlines():
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        if not stripped.endswith("\\\\"):
            continue
        rows.append([cell.strip() for cell in stripped[:-2].split(" & ")])
    return rows


def _row(rows, first):
    for cells in rows:
        if cells and cells[0] == first:
            return cells
    raise AssertionError(f"no row starting with {first!r}")


def _tex_first(cell):
    cell = cell.replace(r"\_", "_").replace(r"\&", "&")
    if cell.startswith(r"\texttt{") and cell.endswith("}"):
        cell = cell[len(r"\texttt{"):-1]
    return cell


def _tex_row(rows, first):
    for cells in rows:
        if cells and _tex_first(cells[0]) == first:
            return cells
    raise AssertionError(f"no tex row starting with {first!r}")


def _norm_md_cell(cell):
    if cell == "—":
        return "---"
    if cell.startswith("`") and cell.endswith("`"):
        cell = cell[1:-1]
    return cell


def _norm_tex_cell(cell):
    return _tex_first(cell)


def _begin(fmt, name):
    return (MD_BEGIN_TEMPLATE if fmt == "md" else TEX_BEGIN_TEMPLATE).format(name=name)


def _end(fmt, name):
    return (MD_END_TEMPLATE if fmt == "md" else TEX_END_TEMPLATE).format(name=name)


# -- standalone documents from the same payload -----------------------------


def test_standalone_markdown_and_latex_from_same_payload(tmp_path):
    payload_path = _make_payload(tmp_path)
    md = tmp_path / "results.md"
    tex = tmp_path / "results.tex"
    assert main([str(payload_path), "--markdown", str(md), "--latex", str(tex)]) == 0
    md_doc = md.read_text(encoding="utf-8")
    tex_doc = tex.read_text(encoding="utf-8")
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

    for doc in (md_doc, tex_doc):
        assert "canonical-results/1" in doc
        assert sha in doc  # input lineage
        assert "contains" in doc  # grader lineage
        assert "test-model" in doc  # model lineage
        assert "micro acc (trial-pooled)" in doc
        assert "macro acc (task-eq-wt)" in doc
        assert "Holm" in doc
        assert "356.67" in doc  # classic total spend/success (1070/3)
        assert "248.50" in doc  # tahoe total spend/success (994/4)
        assert "1.1143" in doc  # input token ratio (780/700)
        assert "0.5784" in doc  # output token ratio (214/370)
        assert "Grader-error outcomes:" in doc  # never silently dropped
    assert "Total trials: 12." in md_doc
    assert r"\toprule" in tex_doc and r"\bottomrule" in tex_doc  # booktabs


def test_markdown_latex_cells_agree(tmp_path):
    """Same payload: every shared table row carries identical cells in both
    formats (modulo the per-format null marker and escaping)."""
    payload = _load(_make_payload(tmp_path))
    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    md_rows, tex_rows = _md_rows(md_doc), _tex_rows(tex_doc)

    for first in (
        "classic",
        "tahoe",
        "overall (all benchmarks pooled)",
        "canonical-fixture",
        "canonical-fixture/classic_vs_tahoe",
    ):
        assert [_norm_md_cell(c) for c in _row(md_rows, first)] == [
            _norm_tex_cell(c) for c in _tex_row(tex_rows, first)
        ], first

    # Pin exact fixture values (micro/macro, exact counts, spend, outcomes).
    classic = _row(md_rows, "classic")
    assert classic[:4] == ["classic", "6", "3", "3"]
    assert classic[4] == "0.5000"
    assert classic[5] == "0.5000"
    assert classic[9] == "356.67"
    assert classic[10:14] == ["1", "0", "0", "5"]  # trunc/cap/empty/completed
    assert classic[14] == "0.4000"  # completed accuracy
    assert classic[15] == "0"  # grader errors recorded: zero, not unknown
    tahoe = _row(md_rows, "tahoe")
    assert tahoe[9] == "248.50"
    assert tahoe[10:14] == ["0", "1", "1", "4"]
    assert tahoe[15] == "0"

    pair = _row(md_rows, "overall (all benchmarks pooled)")
    assert pair[1:4] == ["1.1143", "0.5784", "0.9290"]
    assert pair[6] == "+0.1667" and pair[7] == "+0.1667"

    comp = _row(md_rows, "canonical-fixture/classic_vs_tahoe")
    assert comp[1:7] == ["3", "6", "0.5000", "0.6667", "-0.1667", "+12.7"]
    # Holm-adjusted p-values come from the payload, formatted identically.
    comparison = payload["paired_comparisons"]["canonical-fixture/classic_vs_tahoe"]
    assert comp[7] == format(comparison["permutation_p"], ".4f")
    assert comp[8] == format(comparison["permutation_p_holm"], ".4f")
    assert comp[9] == format(comparison["pass_rate_permutation_p_holm"], ".4f")
    assert comp[10] == format(comparison["z_test"]["p_value_holm"], ".4f")
    assert comp[11] == format(comparison["wilcoxon"]["p_value_holm"], ".4f")


def test_full_block_matches_standalone_documents(tmp_path):
    payload = _load(_make_payload(tmp_path))
    assert "\n".join(render_block(payload, "full", "md")) + "\n" == (
        render_markdown_document(payload)
    )
    assert "\n".join(render_block(payload, "full", "tex")) + "\n" == (
        render_latex_fragment(payload)
    )


# -- analysis implementation lineage ----------------------------------------


def test_analysis_lineage_rendered_in_both_formats(tmp_path):
    payload = _load(_make_payload(tmp_path))
    analysis = payload["analysis_provenance"]
    assert analysis["schema"] == "canonical-analysis/1"
    assert set(analysis["files"]) == {
        "benchmarks/canonical_results.py",
        "benchmarks/report.py",
        "benchmarks/stats.py",
    }
    # Recorded hashes are the real sha-256 of the current analysis files.
    for repo_rel, recorded in analysis["files"].items():
        assert recorded == hashlib.sha256(
            (ROOT / repo_rel).read_bytes()
        ).hexdigest()

    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    for doc in (md_doc, tex_doc):
        assert "Analysis implementation" in doc
        for recorded in analysis["files"].values():
            assert recorded in doc
        assert "seed 123" in doc
        assert "200 bootstrap resamples" in doc
        assert "200 permutation draws" in doc
        assert "canonical-analysis/1" in doc
    # Repo-relative source paths survive; underscores escaped for LaTeX.
    assert "`benchmarks/canonical_results.py`" in md_doc
    assert "`benchmarks/stats.py`" in md_doc
    assert "benchmarks/canonical\\_results.py" in tex_doc
    assert "benchmarks/stats.py" in tex_doc  # no escape needed
    # Markdown and LaTeX agree cell-by-cell on the analysis table.
    for repo_rel in analysis["files"]:
        md_cells = _row(_md_rows(md_doc), f"`{repo_rel}`")
        tex_cells = _tex_row(_tex_rows(tex_doc), repo_rel)
        assert [_norm_md_cell(c) for c in md_cells] == [
            _norm_tex_cell(c) for c in tex_cells
        ]


def test_analysis_block_update_and_drift(tmp_path):
    payload_path = _make_payload(tmp_path)
    payload = _load(payload_path)
    doc = tmp_path / "ANALYSIS.md"
    doc.write_text(
        "Intro.\n\n"
        + _begin("md", "analysis") + "\nstale\n" + _end("md", "analysis") + "\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    updated = doc.read_text(encoding="utf-8")
    expected = "\n".join(render_block(payload, "analysis", "md"))
    assert updated == (
        "Intro.\n\n" + _begin("md", "analysis") + "\n"
        + expected + "\n" + _end("md", "analysis") + "\n"
    )
    assert "stale" not in updated
    assert "Analysis implementation" in updated
    assert main([str(payload_path), "--check", str(doc)]) == 0
    drifted = updated.replace("Analysis implementation", "tampered", 1)
    doc.write_text(drifted, encoding="utf-8")
    assert main([str(payload_path), "--check", str(doc)]) == 3


# -- nulls are explicit markers, never 0.0 ----------------------------------


def test_nulls_render_as_explicit_markers_never_zero(tmp_path):
    trials = [
        {  # cap-exhausted: not a completed response
            "arm": "classic", "benchmark": "b", "task_id": "at-cap", "trial": 0,
            "input_tokens": 10, "output_token_cap": 100, "output_tokens": 100,
            "total_tokens": 110, "passed": False, "final_answer": "cut at cap",
        },
        {  # zero tahoe successes: spend/success is undefined, not free
            "arm": "tahoe", "benchmark": "b", "task_id": "at-cap", "trial": 0,
            "input_tokens": 10, "output_tokens": 50, "total_tokens": 60,
            "passed": False, "final_answer": "fine",
        },
    ]
    input_file = tmp_path / "nulls.json"
    input_file.write_text(json.dumps(trials), encoding="utf-8")
    payload = _load(_make_payload(tmp_path, trials=input_file))
    assert payload["overall"]["arms"]["classic"]["total_spend_per_success"] is None
    assert (
        payload["overall"]["arms"]["classic"]["outcomes"]["completed_response"]
        ["accuracy"] is None
    )

    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    md_cells = _row(_md_rows(md_doc), "classic")
    tex_cells = _row(_tex_rows(tex_doc), "classic")
    assert md_cells[9] == "—"  # undefined spend rendered as null marker
    assert md_cells[14] == "—"  # no completed responses: accuracy undefined
    assert tex_cells[9] == "---"
    assert tex_cells[14] == "---"
    for fmt, cells in (("md", md_cells), ("tex", tex_cells)):
        marker = "—" if fmt == "md" else "---"
        assert "0.00" != cells[9]
        pair_row = _row(
            _md_rows(md_doc) if fmt == "md" else _tex_rows(tex_doc),
            "overall (all benchmarks pooled)",
        )
        assert pair_row[4] == marker and pair_row[5] == marker


# -- lineage and grader-error accounting -------------------------------------


def test_input_lineage_rows_carry_sha_and_graders(tmp_path):
    payload = _load(_make_payload(tmp_path))
    md_doc = render_markdown_document(payload)
    rows = _md_rows(md_doc)
    inputs_row = _row(rows, f"`{FIXTURE}`")
    assert inputs_row[1].strip("`") == hashlib.sha256(
        FIXTURE.read_bytes()
    ).hexdigest()
    assert inputs_row[2] == "12"
    assert inputs_row[3] == "classic: 6, tahoe: 6"
    assert "contains" in inputs_row[5]  # grader lineage
    assert "test-model" in inputs_row[6]
    assert "Total trials: 12." in md_doc


def _derived_manifest_input(tmp_path, grader_record):
    """A realistic derived canonical input: benchmark metadata plus a
    nested ``manifest`` block recording grader identity, and trials
    WITHOUT trial-level grader/model keys so the nested manifest is the
    only provenance source."""
    source_text = 'def grade(answer, expected):\n    return answer == expected\n'
    sha = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    grader = {
        "name": "exact-match",
        "version": "1.4.2",
        "source": "src/tahoe/graders.py",
        "sha256": sha,
        "function": {"grade": "bool equality over final answers"},
    }
    if grader_record is not None:
        grader.update(grader_record)
    derived = {
        "benchmark": "derived-bench",
        "manifest": {"grader": grader},
        "trials": [
            {"arm": "classic", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": True},
            {"arm": "tahoe", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": False},
        ],
    }
    input_file = tmp_path / "derived.json"
    input_file.write_text(json.dumps(derived), encoding="utf-8")
    return input_file, sha


def test_derived_manifest_grader_identity_renders(tmp_path):
    """manifest.top_level.manifest.grader (name/version/source/sha256) is
    surfaced compactly in the inputs table, Markdown and LaTeX alike."""
    input_file, sha = _derived_manifest_input(tmp_path, None)
    payload_path = _make_payload(tmp_path, trials=input_file)
    payload = _load(payload_path)
    # The nested provenance really is recorded in the canonical manifest.
    manifest = payload["provenance"]["inputs"][0]["manifest"]
    assert manifest["top_level"]["manifest"]["grader"]["sha256"] == sha

    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    identity = f"exact-match 1.4.2 (src/tahoe/graders.py, sha-256 {sha})"
    md_cells = _row(_md_rows(md_doc), f"`{input_file}`")
    tex_cells = _tex_row(_tex_rows(tex_doc), str(input_file))
    assert md_cells[5] == identity
    assert [_norm_md_cell(c) for c in md_cells] == [
        _norm_tex_cell(c) for c in tex_cells
    ]  # MD and LaTeX agree cell-by-cell, grader identity included
    for doc in (md_doc, tex_doc):
        assert identity in doc
    # Grader column shows the recorded identity, never a blanket
    # 'not recorded'; the unrecorded model column legitimately does.
    assert md_cells[5] == identity and tex_cells[5] == identity

    # Model lineage behavior is preserved: unrecorded model stays as-is.
    assert md_cells[6] == "not recorded"
    # The nested record never masks the input's own lineage columns.
    assert md_cells[1].strip("`") == hashlib.sha256(
        input_file.read_bytes()
    ).hexdigest()
    assert "Total trials: 2." in md_doc

    # Marker update surfaces the same identity (deterministic everywhere).
    doc = tmp_path / "README.md"
    doc.write_text(
        _begin("md", "inputs") + "\nold\n" + _end("md", "inputs") + "\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    assert identity in doc.read_text(encoding="utf-8")


def test_derived_manifest_identity_merges_with_trial_metadata(tmp_path):
    """Trial-level grader values and the nested identity are both shown —
    a deterministic, sorted union; neither masks the other."""
    input_file, sha = _derived_manifest_input(tmp_path, None)
    trials = json.loads(input_file.read_text(encoding="utf-8"))
    for trial in trials["trials"]:
        trial["grader"] = "contains"  # trial metadata records this one
    input_file.write_text(json.dumps(trials), encoding="utf-8")
    payload = _load(_make_payload(tmp_path, trials=input_file))
    identity = f"exact-match 1.4.2 (src/tahoe/graders.py, sha-256 {sha})"
    md_cells = _row(
        _md_rows(render_markdown_document(payload)), f"`{input_file}`"
    )
    assert md_cells[5] == f"contains, {identity}"
    tex_cells = _tex_row(
        _tex_rows(render_latex_fragment(payload)), str(input_file)
    )
    assert tex_cells[5] == f"contains, {identity}"


def test_absent_grader_provenance_never_invented(tmp_path):
    """No grader anywhere (plain trials input, nested manifest without a
    grader, and a degenerate grader record without identity fields):
    the column stays 'not recorded' — nothing is fabricated."""
    # Plain trials input: no manifest block at all.
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps([
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": False},
    ]), encoding="utf-8")
    payload = _load(_make_payload(tmp_path, trials=bare))
    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    assert _row(_md_rows(md_doc), f"`{bare}`")[5] == "not recorded"
    assert _tex_row(_tex_rows(tex_doc), str(bare))[5] == "not recorded"

    # Nested manifest present but without grader provenance, plus a
    # degenerate grader record with no identity fields: still not recorded.
    nested = {
        "benchmark": "derived-bench",
        "manifest": {
            "model": {"name": "test-model"},  # no grader key at all
            "grader": {"function": {"grade": "unlabeled"}},
        },
        "trials": [
            {"arm": "classic", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": True},
            {"arm": "tahoe", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": False},
        ],
    }
    input_file = tmp_path / "no-grader.json"
    input_file.write_text(json.dumps(nested), encoding="utf-8")
    payload = _load(
        _make_payload(tmp_path, trials=input_file, name="no-grader-payload")
    )
    md_cells = _row(
        _md_rows(render_markdown_document(payload)), f"`{input_file}`"
    )
    tex_cells = _tex_row(
        _tex_rows(render_latex_fragment(payload)), str(input_file)
    )
    assert md_cells[5] == "not recorded"
    assert tex_cells[5] == "not recorded"
    # The nested model record does not leak into the grader column; the
    # model column itself still reads only recorded model metadata.
    assert md_cells[6] == "not recorded"


def _derived_manifest_v3_input(tmp_path, grader, grader_version):
    """The ACTUAL derived-manifest layout: ``grader_version`` is a SIBLING
    of the ``grader`` record inside the nested manifest, and the grader
    record itself has no ``version`` — the tag is its version.  The grader
    sha-256 is the real hash of the recorded source file."""
    sha = hashlib.sha256(
        (ROOT / "benchmarks/run_public_bench.py").read_bytes()
    ).hexdigest()
    derived = {
        "benchmark": "public-bench",
        "manifest": {
            "grader": {
                "name": "run_public_bench.stage1",
                "source": "benchmarks/run_public_bench.py",
                "sha256": sha,
                "function": {"classify": "numeric equality after normalization"},
                **(grader or {}),
            },
            "grader_version": grader_version,
        },
        "trials": [
            {"arm": "classic", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": True},
            {"arm": "tahoe", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": False},
        ],
    }
    input_file = tmp_path / "derived-v3.json"
    input_file.write_text(json.dumps(derived), encoding="utf-8")
    return input_file, sha


def test_derived_manifest_sibling_grader_version_tag_renders(tmp_path):
    """manifest.grader_version (sibling of manifest.grader) is surfaced as
    the grader record's version in the inputs table — exact tag, in
    Markdown, LaTeX, and marker updates."""
    input_file, sha = _derived_manifest_v3_input(
        tmp_path, None, "run_public_bench-numeric-v6"
    )
    payload_path = _make_payload(tmp_path, trials=input_file, name="v3-payload")
    payload = _load(payload_path)
    # The sibling tag really is recorded in the canonical manifest.
    nested = payload["provenance"]["inputs"][0]["manifest"]["top_level"][
        "manifest"
    ]
    assert nested["grader_version"] == "run_public_bench-numeric-v6"
    assert "version" not in nested["grader"]

    identity = (
        "run_public_bench.stage1 run_public_bench-numeric-v6 "
        f"(benchmarks/run_public_bench.py, sha-256 {sha})"
    )
    md_cells = _row(
        _md_rows(render_markdown_document(payload)), f"`{input_file}`"
    )
    tex_cells = _tex_row(
        _tex_rows(render_latex_fragment(payload)), str(input_file)
    )
    assert md_cells[5] == identity  # sibling tag in the version slot
    assert _norm_tex_cell(tex_cells[5]) == identity  # tex: unescaped
    # MD and LaTeX agree cell-by-cell on the whole row.
    assert [_norm_md_cell(c) for c in md_cells] == [
        _norm_tex_cell(c) for c in tex_cells
    ]
    assert md_cells[6] == "not recorded"  # model lineage untouched

    # Marker updates surface the same exact tag, deterministically.
    doc = tmp_path / "README.md"
    doc.write_text(
        _begin("md", "inputs") + "\nold\n" + _end("md", "inputs") + "\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    updated = doc.read_text(encoding="utf-8")
    assert identity in updated
    assert "run_public_bench-numeric-v6" in updated
    assert main([str(payload_path), "--check", str(doc)]) == 0


def test_explicit_grader_version_keeps_rendering_sibling_tag_surfaced(tmp_path):
    """An explicit grader.version keeps its existing slot; the recorded
    sibling tag is still surfaced truthfully, never dropped or invented."""
    input_file, sha = _derived_manifest_v3_input(
        tmp_path, {"version": "6.0.1"}, "run_public_bench-numeric-v6"
    )
    payload = _load(
        _make_payload(tmp_path, trials=input_file, name="v3-both-payload")
    )
    expected = (
        "run_public_bench.stage1 6.0.1 (grader_version "
        f"run_public_bench-numeric-v6, benchmarks/run_public_bench.py, "
        f"sha-256 {sha})"
    )
    md_cells = _row(
        _md_rows(render_markdown_document(payload)), f"`{input_file}`"
    )
    tex_cells = _tex_row(
        _tex_rows(render_latex_fragment(payload)), str(input_file)
    )
    assert md_cells[5] == expected
    assert _norm_tex_cell(tex_cells[5]) == expected


def test_grader_version_tag_without_grader_record_shows_tag(tmp_path):
    """grader_version recorded with NO grader record: the tag itself is the
    provenance that exists — shown as recorded, both formats."""
    derived = {
        "benchmark": "public-bench",
        "manifest": {"grader_version": "run_public_bench-numeric-v6"},
        "trials": [
            {"arm": "classic", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": True},
            {"arm": "tahoe", "task_id": "t", "trial": 0,
             "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
             "passed": False},
        ],
    }
    input_file = tmp_path / "tag-only.json"
    input_file.write_text(json.dumps(derived), encoding="utf-8")
    payload = _load(
        _make_payload(tmp_path, trials=input_file, name="tag-only-payload")
    )
    assert _row(
        _md_rows(render_markdown_document(payload)), f"`{input_file}`"
    )[5] == "grader_version run_public_bench-numeric-v6"
    assert _norm_tex_cell(_tex_row(
        _tex_rows(render_latex_fragment(payload)), str(input_file)
    )[5]) == "grader_version run_public_bench-numeric-v6"


def test_absent_or_malformed_grader_version_tags_ignored(tmp_path):
    """Absent tags are never invented; malformed tag values (dict, list,
    bool, empty string) are ignored — the rendering stays exactly as it
    was without a tag."""
    untagged = (
        "run_public_bench.stage1 (benchmarks/run_public_bench.py, "
        "sha-256 {sha})"
    )
    for index, bad_tag in enumerate(
        (None, {}, [], True, False, "", {"version": "x"})
    ):
        input_file, sha = _derived_manifest_v3_input(
            tmp_path, None, bad_tag
        )
        payload = _load(
            _make_payload(
                tmp_path, trials=input_file, name=f"badtag-{index}"
            )
        )
        expected = untagged.format(sha=sha)
        md_cells = _row(
            _md_rows(render_markdown_document(payload)), f"`{input_file}`"
        )
        tex_cells = _tex_row(
            _tex_rows(render_latex_fragment(payload)), str(input_file)
        )
        assert md_cells[5] == expected, bad_tag
        assert _norm_tex_cell(tex_cells[5]) == expected, bad_tag


# -- grader-error aggregate rendering -------------------------------------


def _grader_error_input(tmp_path, *, raw=False):
    """A trial input whose classic arm carries one grader-error outcome.

    Recorded aggregates: classic 1 grader error, tahoe 0 — with or without
    raw trials, so the renderer's aggregate path is exercised exactly.
    """
    trials = [
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": False, "failure_class": "grader_error",
         "grader": "contains", "model": "test-model"},
        {"arm": "classic", "benchmark": "b", "task_id": "u", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "failure_class": "none", "grader": "contains",
         "model": "test-model"},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "failure_class": "none", "grader": "contains",
         "model": "test-model"},
        {"arm": "tahoe", "benchmark": "b", "task_id": "u", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "failure_class": "none", "grader": "contains",
         "model": "test-model"},
    ]
    input_file = tmp_path / "grader_err.json"
    input_file.write_text(json.dumps(trials), encoding="utf-8")
    flags = ("--include-raw-trials",) if raw else ()
    return _load(
        _make_payload(tmp_path, trials=input_file, name="grader", flags=flags)
    )


def _strip_grader_aggregates(payload, *arms):
    """Simulate a legacy payload: drop the grader_error outcome aggregate."""
    scopes = [payload["overall"]["arms"]] + [
        entry["arms"] for entry in payload["benchmarks"].values()
    ]
    for scope in scopes:
        for arm in scope:
            if not arms or arm in arms:
                scope[arm]["outcomes"].pop("grader_error", None)


def test_grader_error_nonzero_aggregate_without_raw_trials(tmp_path):
    """Exact grader-error counts render from the aggregate alone — the
    default canonical payload (no raw trials) never says 'not recorded'."""
    payload = _grader_error_input(tmp_path, raw=False)
    assert "raw_trials" not in payload
    classic = payload["overall"]["arms"]["classic"]["outcomes"]["grader_error"]
    assert classic["count"] == 1 and classic["rate"] == pytest.approx(0.5)

    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    note = (
        "Grader-error outcomes: 1 recorded (classic: 1, tahoe: 0); they are "
        "reported as their own outcome class and never silently dropped."
    )
    for doc in (md_doc, tex_doc):
        assert note in doc
        # No false 'not recorded' grader-error note anywhere.
        assert "Grader-error outcomes: not recorded" not in doc
    # Exact per-arm counts in the grader-err column, both formats.
    assert _row(_md_rows(md_doc), "classic")[15] == "1"
    assert _row(_md_rows(md_doc), "tahoe")[15] == "0"
    assert _tex_row(_tex_rows(tex_doc), "classic")[15] == "1"
    assert _tex_row(_tex_rows(tex_doc), "tahoe")[15] == "0"


def test_grader_error_zero_aggregate_default_fixture(tmp_path):
    """Zero grader errors render as a recorded, exact zero — never as
    'unknown', and never as a false 'not recorded' note."""
    payload = _load(_make_payload(tmp_path))
    assert payload["overall"]["arms"]["classic"]["outcomes"]["grader_error"] == {
        "count": 0, "rate": 0.0,
    }
    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    for doc in (md_doc, tex_doc):
        assert "Grader-error outcomes: 0 recorded (classic: 0, tahoe: 0)." in doc
        assert "Grader-error outcomes: not recorded" not in doc
        assert "grader err" in doc  # the column is present
    assert _row(_md_rows(md_doc), "classic")[15] == "0"
    assert _tex_row(_tex_rows(tex_doc), "classic")[15] == "0"


def test_grader_error_raw_trials_are_only_a_cross_check(tmp_path):
    """With raw trials included, the aggregate stays the rendered source;
    raw trials merely agree with it (contradicting payloads are refused)."""
    payload = _grader_error_input(tmp_path, raw=True)
    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    note = (
        "Grader-error outcomes: 1 recorded (classic: 1, tahoe: 0); they are "
        "reported as their own outcome class and never silently dropped."
    )
    for doc in (md_doc, tex_doc):
        assert note in doc
        assert "raw trial(s) carry failure_class" not in doc
    assert _row(_md_rows(md_doc), "classic")[15] == "1"

    # Tampered raw trials contradicting the aggregate are refused loudly.
    tampered = copy.deepcopy(payload)
    for trial in tampered["raw_trials"]:
        trial["failure_class"] = "none"
    with pytest.raises(RenderError) as excinfo:
        validate_payload(tampered)
    assert "grader_error counts disagree" in str(excinfo.value)


def test_legacy_payload_without_aggregate_renders_unknown_never_zero(tmp_path):
    """A legacy payload missing the aggregate is accepted, but its counts
    render as an explicit 'unknown' — never 0 — and the note says so."""
    payload = _grader_error_input(tmp_path, raw=False)
    _strip_grader_aggregates(payload)
    validate_payload(payload)  # legacy aggregate is accepted

    md_doc = render_markdown_document(payload)
    tex_doc = render_latex_fragment(payload)
    note = (
        "Grader-error outcomes: not recorded in this payload (grader_error "
        "outcome aggregate missing for arms: classic, tahoe); counts are "
        "unknown and are never reported as zero."
    )
    for doc in (md_doc, tex_doc):
        assert '"unknown" marks grader-error counts' in doc
    assert note in md_doc
    # The LaTeX fragment states the same fact with TeX-escaped underscores.
    assert note.replace("_", r"\_") in tex_doc
    assert _row(_md_rows(md_doc), "classic")[15] == "unknown"
    assert _row(_md_rows(md_doc), "tahoe")[15] == "unknown"
    assert _tex_row(_tex_rows(tex_doc), "classic")[15] == "unknown"
    assert _tex_row(_tex_rows(tex_doc), "tahoe")[15] == "unknown"


def test_legacy_payload_with_raw_trials_counts_from_raw(tmp_path):
    """Legacy + raw trials: exact counts come from the raw trials, while the
    arm-table column still marks the missing aggregate as unknown."""
    payload = _grader_error_input(tmp_path, raw=True)
    _strip_grader_aggregates(payload)
    validate_payload(payload)
    md_doc = render_markdown_document(payload)
    note = (
        'Grader-error outcomes: 1 raw trial(s) carry failure_class '
        '"grader_error" (classic: 1); they are reported as their own outcome '
        "class and never silently dropped."
    )
    assert note in md_doc
    # The aggregate — not raw trials — is the blessed column source.
    assert _row(_md_rows(md_doc), "classic")[15] == "unknown"


def test_legacy_partial_aggregate_reports_known_and_unknown(tmp_path):
    """Arms missing the aggregate are flagged unknown; arms that recorded it
    keep their exact counts — known and unknown are never conflated."""
    payload = _grader_error_input(tmp_path, raw=False)
    _strip_grader_aggregates(payload, "tahoe")  # only tahoe is legacy
    validate_payload(payload)
    md_doc = render_markdown_document(payload)
    note = (
        "Grader-error outcomes: 1 recorded (classic: 1); not recorded for "
        "arms: tahoe (counts unknown, never reported as zero)."
    )
    assert note in md_doc
    assert _row(_md_rows(md_doc), "classic")[15] == "1"
    assert _row(_md_rows(md_doc), "tahoe")[15] == "unknown"


# -- summary block (headline: overall only, no per-benchmark sections) -----


def test_summary_block_matches_full_overall_rows(tmp_path):
    """The summary block's tables are exactly the full render's overall
    arm table and overall pair table — same row builders, same values."""
    payload = _load(_make_payload(tmp_path))
    full_md = render_markdown_document(payload)
    summary_md = "\n".join(render_block(payload, "summary", "md")) + "\n"
    full_rows = _md_rows(full_md)
    summary_rows = _md_rows(summary_md)

    # Overall arm rows: identical cells in summary and full render.
    for arm in payload["overall"]["arms"]:
        assert _row(summary_rows, arm) == _row(full_rows, arm)

    # Overall pair row: identical cells; and it is the pair table's only row.
    scope = "overall (all benchmarks pooled)"
    assert _row(summary_rows, scope) == _row(full_rows, scope)
    pair_rows = [r for r in summary_rows if r and r[0] == scope]
    assert len(pair_rows) == 1
    # Both tables carry their full column sets: the arm table header is row 0.
    assert summary_rows[0][:2] == ["arm", "trials"]
    assert "micro acc (trial-pooled)" in summary_rows[0]
    # The pair table header keeps its full column set too.
    pair_header = _row(summary_rows, "scope")
    assert "total spend/success classic" in pair_header
    assert "micro acc diff (tahoe-classic)" in pair_header


def test_summary_excludes_per_benchmark_sections(tmp_path):
    payload = _load(_make_payload(tmp_path))
    benchmarks = list(payload["benchmarks"])  # e.g. canonical-fixture
    for fmt in ("md", "tex"):
        summary = "\n".join(render_block(payload, "summary", fmt))
        for benchmark in benchmarks:
            assert benchmark not in summary
        assert "Task-set sha-256" not in summary  # no per-benchmark metadata
        # Exactly one section heading (Overall); no per-benchmark headings.
        assert summary.count("## " if fmt == "md" else r"\subsection*{") == 1
        if fmt == "md":
            assert "###" not in summary


def test_summary_md_tex_values_agree(tmp_path):
    payload = _load(_make_payload(tmp_path))
    md_rows = _md_rows("\n".join(render_block(payload, "summary", "md")))
    tex_rows = _tex_rows("\n".join(render_block(payload, "summary", "tex")))
    # Header sets and every displayed value agree cell-by-cell.
    assert [_norm_md_cell(c) for c in md_rows[0]] == [
        _norm_tex_cell(c) for c in tex_rows[0]
    ]
    for arm in payload["overall"]["arms"]:
        assert [_norm_md_cell(c) for c in _row(md_rows, arm)] == [
            _norm_tex_cell(c) for c in _tex_row(tex_rows, arm)
        ]
    scope = "overall (all benchmarks pooled)"
    assert [_norm_md_cell(c) for c in _row(md_rows, scope)] == [
        _norm_tex_cell(c) for c in _tex_row(tex_rows, scope)
    ]


def test_summary_marker_update_check_and_idempotence(tmp_path):
    payload_path = _make_payload(tmp_path)
    payload = _load(payload_path)
    doc = tmp_path / "README.md"
    header = "# TAHOE results\n\nHeadline numbers:\n\n"
    doc.write_text(
        header + _begin("md", "summary") + "\nstale\n" + _end("md", "summary")
        + "\n\nSee full results below.\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    expected = "\n".join(render_block(payload, "summary", "md"))
    assert text == (
        header + _begin("md", "summary") + "\n"
        + expected + "\n" + _end("md", "summary") + "\n\nSee full results below.\n"
    )
    assert "stale" not in text
    assert "## Overall" in text
    assert "Headline numbers:" in text and "See full results below." in text

    # Idempotent, and check mode reports agreement without touching the file.
    before = doc.read_bytes()
    assert main([str(payload_path), "--update", str(doc)]) == 0
    assert doc.read_bytes() == before
    assert main([str(payload_path), "--check", str(doc)]) == 0
    assert doc.read_bytes() == before

    # Drift is detected and never repaired by check mode.
    doc.write_text(
        text.replace("## Overall", "## tampered", 1), encoding="utf-8"
    )
    drifted = doc.read_bytes()
    assert main([str(payload_path), "--check", str(doc)]) == 3
    assert doc.read_bytes() == drifted


def test_summary_pair_unavailable_note_when_no_pair(tmp_path):
    """No overall pair (single arm): the summary states it explicitly
    instead of inventing ratios — and stays per-benchmark-free."""
    trials = [
        {"arm": "classic", "benchmark": "solo-bench", "task_id": "t", "trial": 0,
         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
         "passed": True, "grader": "contains"},
    ]
    input_file = tmp_path / "one.json"
    input_file.write_text(json.dumps(trials), encoding="utf-8")
    payload = _load(_make_payload(tmp_path, trials=input_file))
    assert "classic_vs_tahoe" not in payload["overall"]
    for fmt in ("md", "tex"):
        summary = "\n".join(render_block(payload, "summary", fmt))
        assert "classic vs tahoe ratios unavailable (arms present: classic)" in (
            summary.replace("\\&", "&") if fmt == "tex" else summary
        )
        assert "overall (all benchmarks pooled)" not in summary
        # No per-benchmark section sneaks in: one heading, no task-set
        # metadata, and the payload's benchmark key renders nowhere.
        assert "Task-set sha-256" not in summary
        assert summary.count("## " if fmt == "md" else r"\subsection*{") == 1
        for benchmark in payload["benchmarks"]:
            assert benchmark not in summary.replace("\\&", "&")


# -- named instances: several payloads, one file -----------------------------

_INSTANCE_README = (
    "# Results\n"
    "\n"
    "## GLM\n"
    "\n"
    "{begin_glm}\n"
    "stale glm\n"
    "{end_glm}\n"
    "\n"
    "Between-blocks prose.\n"
    "\n"
    "## OSS\n"
    "\n"
    "{begin_oss}\n"
    "stale oss\n"
    "{end_oss}\n"
    "\n"
    "Tail.\n"
)


def _instance_readme(path):
    text = _INSTANCE_README.format(
        begin_glm=_begin("md", "summary@glm"),
        end_glm=_end("md", "summary@glm"),
        begin_oss=_begin("md", "summary@oss"),
        end_oss=_end("md", "summary@oss"),
    )
    path.write_text(text, encoding="utf-8")
    return text


def _instance_payload(tmp_path, name, classic_passed, classic_input):
    """A one-benchmark two-arm payload with distinctive values, so blocks
    rendered from different payloads are distinguishable in one file."""
    trials = [
        {"arm": "classic", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": classic_input, "output_tokens": 5,
         "total_tokens": classic_input + 5, "passed": classic_passed,
         "grader": "contains", "model": "m"},
        {"arm": "tahoe", "benchmark": "b", "task_id": "t", "trial": 0,
         "input_tokens": 30, "output_tokens": 5, "total_tokens": 35,
         "passed": True, "grader": "contains", "model": "m"},
    ]
    input_file = tmp_path / f"{name}-trials.json"
    input_file.write_text(json.dumps(trials), encoding="utf-8")
    return _make_payload(tmp_path, trials=input_file, name=name)


def _block_slice(text, fmt, name):
    """Content lines strictly between the markers for *name*."""
    lines = text.splitlines()
    begin, end = _begin(fmt, name), _end(fmt, name)
    try:
        start = lines.index(begin)
        stop = lines.index(end, start + 1)
    except ValueError as exc:
        raise AssertionError(f"markers for {name!r} not found") from exc
    return lines[start + 1 : stop]


def test_two_payloads_render_into_one_file_without_pooling(tmp_path):
    """summary@glm and summary@oss each carry their own payload's values in
    the same file; the suffix selects the block, never changes the content."""
    glm_path = _instance_payload(tmp_path, "glm", True, 10)
    oss_path = _instance_payload(tmp_path, "oss", False, 20)
    glm, oss = _load(glm_path), _load(oss_path)
    assert _row(_md_rows(render_markdown_document(glm)), "classic")[3] == "1"
    assert _row(_md_rows(render_markdown_document(oss)), "classic")[3] == "0"

    doc = tmp_path / "README.md"
    _instance_readme(doc)
    assert main([str(glm_path), "--update", str(doc), "--block", "summary@glm"]) == 0
    text = doc.read_text(encoding="utf-8")
    # The glm block now carries payload-glm values; the oss block is
    # untouched, and so is everything outside the markers.
    assert _block_slice(text, "md", "summary@glm") == render_block(
        glm, "summary@glm", "md"
    )
    assert _block_slice(text, "md", "summary@oss") == ["stale oss"]
    assert "Between-blocks prose." in text and "Tail." in text

    assert main([str(oss_path), "--update", str(doc), "--block", "summary@oss"]) == 0
    text = doc.read_text(encoding="utf-8")
    glm_block = _block_slice(text, "md", "summary@glm")
    oss_block = _block_slice(text, "md", "summary@oss")
    # Both payloads' values live in one file, each in its own block.
    assert glm_block == render_block(glm, "summary@glm", "md")
    assert oss_block == render_block(oss, "summary@oss", "md")
    assert glm_block != oss_block  # distinct payloads, no pooling
    # The suffix never changes the rendered content: same section render.
    assert glm_block == render_block(glm, "summary", "md")
    assert oss_block == render_block(oss, "summary", "md")

    # Idempotent: re-running both selected updates changes nothing.
    assert main([str(glm_path), "--update", str(doc), "--block", "summary@glm"]) == 0
    assert main([str(oss_path), "--update", str(doc), "--block", "summary@oss"]) == 0
    assert doc.read_text(encoding="utf-8") == text


def test_selected_update_leaves_every_other_block_byte_untouched(tmp_path):
    """--block touches exactly the named block: sibling instance blocks and
    plain-named blocks keep their bytes."""
    glm_path = _instance_payload(tmp_path, "glm", True, 10)
    oss_path = _instance_payload(tmp_path, "oss", False, 20)
    doc = tmp_path / "README.md"
    text = _instance_readme(doc)
    # Add a plain-named block too; it must survive instance updates.
    text = text.replace(
        "Tail.\n",
        _begin("md", "overall") + "\nstale overall\n"
        + _end("md", "overall") + "\n\nTail.\n",
    )
    doc.write_text(text, encoding="utf-8")

    assert main([str(glm_path), "--update", str(doc), "--block", "summary@glm"]) == 0
    updated = doc.read_text(encoding="utf-8")
    assert _block_slice(updated, "md", "summary@glm") == render_block(
        _load(glm_path), "summary@glm", "md"
    )
    assert _block_slice(updated, "md", "summary@oss") == ["stale oss"]
    assert _block_slice(updated, "md", "overall") == ["stale overall"]
    # Prose outside the markers survives unchanged.
    assert "Between-blocks prose." in updated
    assert updated.endswith("Tail.\n")


def test_selected_check_scopes_drift_to_named_blocks(tmp_path):
    glm_path = _instance_payload(tmp_path, "glm", True, 10)
    oss_path = _instance_payload(tmp_path, "oss", False, 20)
    doc = tmp_path / "README.md"
    _instance_readme(doc)
    assert main([str(glm_path), "--update", str(doc), "--block", "summary@glm"]) == 0

    # The stale oss block does NOT trip a glm-selected check...
    assert main([str(glm_path), "--check", str(doc), "--block", "summary@glm"]) == 0
    # ...but it does drift against the oss payload it belongs to.
    before = doc.read_bytes()
    assert main([str(oss_path), "--check", str(doc), "--block", "summary@oss"]) == 3
    assert doc.read_bytes() == before  # check never modifies anything
    # ...and without --block, the all-blocks behavior reports it (vs glm).
    assert main([str(glm_path), "--check", str(doc)]) == 3

    assert main([str(oss_path), "--update", str(doc), "--block", "summary@oss"]) == 0
    # Each instance matches its own payload; a file carrying two payloads
    # can only be fully verified with per-instance checks.
    assert main([str(glm_path), "--check", str(doc), "--block", "summary@glm"]) == 0
    assert main([str(oss_path), "--check", str(doc), "--block", "summary@oss"]) == 0

    # Tampering one block is detected exactly by its own selected check.
    good = doc.read_text(encoding="utf-8")
    doc.write_text(
        good.replace("## Overall", "## tampered", 1), encoding="utf-8"
    )
    tampered = doc.read_bytes()
    assert main([str(glm_path), "--check", str(doc), "--block", "summary@glm"]) == 3
    assert doc.read_bytes() == tampered
    assert main([str(oss_path), "--check", str(doc), "--block", "summary@oss"]) == 0


def test_repeatable_block_selection_updates_multiple_instances(tmp_path):
    glm_path = _instance_payload(tmp_path, "glm", True, 10)
    oss_path = _instance_payload(tmp_path, "oss", False, 20)
    doc = tmp_path / "README.md"
    _instance_readme(doc)
    assert main([
        str(glm_path), "--update", str(doc),
        "--block", "summary@glm", "--block", "summary@oss",
    ]) == 0
    text = doc.read_text(encoding="utf-8")
    # Both blocks now carry payload-glm values (one payload per invocation).
    assert _block_slice(text, "md", "summary@glm") == render_block(
        _load(glm_path), "summary@glm", "md"
    )
    assert _block_slice(text, "md", "summary@oss") == render_block(
        _load(glm_path), "summary@oss", "md"
    )


def test_render_block_accepts_plain_names_and_instances(tmp_path):
    payload = _load(_make_payload(tmp_path))
    # Instance suffix never changes the rendered content.
    assert render_block(payload, "summary@glm", "md") == render_block(
        payload, "summary", "md"
    )
    assert render_block(payload, "pair@glm", "tex") == render_block(
        payload, "pair", "tex"
    )
    assert render_block(payload, "inputs@glm", "md") == render_block(
        payload, "inputs", "md"
    )
    assert "\n".join(render_block(payload, "full@glm", "md")) + "\n" == (
        render_markdown_document(payload)
    )
    # split_block_name: plain, instance, and refusals.
    assert split_block_name("summary") == ("summary", None)
    assert split_block_name("summary@glm") == ("summary", "glm")
    assert split_block_name("pair@v2.1-beta_1") == ("pair", "v2.1-beta_1")
    for malformed in ("summary@", "@glm", "a@b@c", "a@b!c"):
        with pytest.raises(RenderError) as excinfo:
            split_block_name(malformed)
        assert "malformed block instance name" in str(excinfo.value)
        with pytest.raises(RenderError):
            render_block(payload, malformed, "md")
    with pytest.raises(RenderError) as excinfo:
        render_block(payload, "bogus@glm", "md")
    assert "unknown block name" in str(excinfo.value)


def test_latex_named_instances(tmp_path):
    """% CANONICAL_RESULTS:BEGIN pair@glm style markers in a .tex file."""
    glm_path = _instance_payload(tmp_path, "glm", True, 10)
    oss_path = _instance_payload(tmp_path, "oss", False, 20)
    doc = tmp_path / "results.tex"
    doc.write_text(
        "% paper\n\n"
        + _begin("tex", "pair@glm") + "\n% stale glm\n" + _end("tex", "pair@glm")
        + "\n\n"
        + _begin("tex", "pair@oss") + "\n% stale oss\n" + _end("tex", "pair@oss")
        + "\n",
        encoding="utf-8",
    )
    assert main([str(glm_path), "--update", str(doc), "--block", "pair@glm"]) == 0
    text = doc.read_text(encoding="utf-8")
    assert _block_slice(text, "tex", "pair@glm") == render_block(
        _load(glm_path), "pair@glm", "tex"
    )
    assert _block_slice(text, "tex", "pair@oss") == ["% stale oss"]
    assert r"\toprule" in text and r"\bottomrule" in text

    assert main([str(oss_path), "--update", str(doc), "--block", "pair@oss"]) == 0
    text = doc.read_text(encoding="utf-8")
    assert _block_slice(text, "tex", "pair@oss") == render_block(
        _load(oss_path), "pair@oss", "tex"
    )
    assert _block_slice(text, "tex", "pair@glm") == render_block(
        _load(glm_path), "pair@glm", "tex"
    )
    # Per-instance checks agree for both payloads.
    assert main([str(oss_path), "--check", str(doc), "--block", "pair@oss"]) == 0
    assert main([str(glm_path), "--check", str(doc), "--block", "pair@glm"]) == 0


BAD_INSTANCE_FILES = {
    "empty_suffix": (
        _begin("md", "summary@") + "\nx\n" + _end("md", "summary@") + "\n"
    ),
    "no_section": (
        _begin("md", "@glm") + "\nx\n" + _end("md", "@glm") + "\n"
    ),
    "double_at": (
        _begin("md", "summary@glm@x") + "\nx\n"
        + _end("md", "summary@glm@x") + "\n"
    ),
    "bad_suffix_char": (
        _begin("md", "summary@gl m") + "\nx\n" + _end("md", "summary@gl m") + "\n"
    ),
    "duplicate_plain_section": (
        _begin("md", "summary") + "\nx\n" + _end("md", "summary") + "\n"
        + _begin("md", "summary") + "\ny\n" + _end("md", "summary") + "\n"
    ),
    "duplicate_exact_instance": (
        _begin("md", "summary@glm") + "\nx\n" + _end("md", "summary@glm") + "\n"
        + _begin("md", "summary@glm") + "\ny\n" + _end("md", "summary@glm") + "\n"
    ),
    "unknown_instance_section": (
        _begin("md", "bogus@glm") + "\nx\n" + _end("md", "bogus@glm") + "\n"
    ),
    "nested_instances": (
        _begin("md", "summary@glm") + "\n" + _begin("md", "summary@oss")
        + "\nx\n" + _end("md", "summary@oss") + "\n"
        + _end("md", "summary@glm") + "\n"
    ),
    "instance_name_mismatch": (
        _begin("md", "summary@glm") + "\nx\n" + _end("md", "summary@oss") + "\n"
    ),
}


@pytest.mark.parametrize("case", sorted(BAD_INSTANCE_FILES))
def test_bad_instance_markers_refused(tmp_path, case):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(BAD_INSTANCE_FILES[case], encoding="utf-8")
    before = doc.read_bytes()
    assert main([str(payload_path), "--update", str(doc)]) == 1
    assert doc.read_bytes() == before
    assert main([str(payload_path), "--check", str(doc)]) == 1
    assert doc.read_bytes() == before


def test_distinct_instances_with_same_base_are_allowed(tmp_path):
    """summary, summary@glm, summary@oss coexist: distinct full names."""
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(
        _begin("md", "summary") + "\na\n" + _end("md", "summary") + "\n"
        + _begin("md", "summary@glm") + "\nb\n" + _end("md", "summary@glm") + "\n"
        + _begin("md", "summary@oss") + "\nc\n" + _end("md", "summary@oss") + "\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    payload = _load(payload_path)
    expected = render_block(payload, "summary", "md")
    for name in ("summary", "summary@glm", "summary@oss"):
        assert _block_slice(text, "md", name) == expected


def test_missing_or_unknown_block_selection_refused(tmp_path):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "README.md"
    _instance_readme(doc)
    before = doc.read_bytes()
    for argv in (
        [str(payload_path), "--update", str(doc), "--block", "summary@vue"],
        [str(payload_path), "--update", str(doc), "--block", "summary"],  # no plain block
        [str(payload_path), "--check", str(doc), "--block", "summary@vue"],
        [str(payload_path), "--update", str(doc), "--block", "bogus@glm"],
        [str(payload_path), "--update", str(doc), "--block", "summary@"],
    ):
        assert main(argv) == 1, argv
        assert doc.read_bytes() == before  # refused means untouched


def test_block_flag_requires_update_or_check(tmp_path):
    payload_path = _make_payload(tmp_path)
    with pytest.raises(SystemExit):
        main([str(payload_path), "--block", "summary@glm"])
    # It composes with standalone writes plus one selected update target.
    doc = tmp_path / "README.md"
    _instance_readme(doc)
    md = tmp_path / "standalone.md"
    assert main([
        str(payload_path), "--markdown", str(md),
        "--update", str(doc), "--block", "summary@glm",
    ]) == 0
    assert md.is_file()
    text = doc.read_text(encoding="utf-8")
    assert _block_slice(text, "md", "summary@oss") == ["stale oss"]


# -- marker update / check semantics -----------------------------------------


def test_update_replaces_only_marked_blocks(tmp_path):
    payload_path = _make_payload(tmp_path)
    payload = _load(payload_path)
    doc = tmp_path / "README.md"
    header = "# Readme\n\nintro\n\n"
    tail = "\nfooter\n"
    doc.write_text(
        header
        + _begin("md", "overall") + "\nstale content\n" + _end("md", "overall")
        + tail,
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    expected = "\n".join(render_block(payload, "overall", "md"))
    assert text == (
        header + _begin("md", "overall") + "\n"
        + expected + "\n" + _end("md", "overall") + tail
    )
    assert "stale content" not in text
    assert "## Overall" in text
    assert "intro" in text and "footer" in text


def test_update_preserves_missing_final_newline(tmp_path):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "no-newline.md"
    doc.write_text(
        "# T\n\n" + _begin("md", "estimands") + "\nold\n" + _end("md", "estimands"),
        encoding="utf-8",  # deliberately no trailing newline
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    assert text.endswith(_end("md", "estimands"))
    assert not text.endswith("\n")


def test_update_multiple_blocks_and_inter_block_text(tmp_path):
    payload_path = _make_payload(tmp_path)
    payload = _load(payload_path)
    doc = tmp_path / "doc.md"
    lines = [
        "# Doc", "",
        _begin("md", "inputs"), "stale1", _end("md", "inputs"), "",
        "middle prose", "",
        _begin("md", "paired"), "stale2", _end("md", "paired"), "",
        "tail",
    ]
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    assert "stale1" not in text and "stale2" not in text
    assert "middle prose" in text and "tail" in text
    expected = [
        "# Doc", "",
        _begin("md", "inputs"), *render_block(payload, "inputs", "md"),
        _end("md", "inputs"), "",
        "middle prose", "",
        _begin("md", "paired"), *render_block(payload, "paired", "md"),
        _end("md", "paired"), "",
        "tail",
    ]
    assert text == "\n".join(expected) + "\n"


def test_check_detects_drift_and_never_modifies(tmp_path):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(
        _begin("md", "pair") + "\nwrong\n" + _end("md", "pair") + "\n",
        encoding="utf-8",
    )
    before = doc.read_bytes()
    assert main([str(payload_path), "--check", str(doc)]) == 3
    assert doc.read_bytes() == before  # check never modifies anything

    assert main([str(payload_path), "--update", str(doc)]) == 0
    assert main([str(payload_path), "--check", str(doc)]) == 0
    good = doc.read_text(encoding="utf-8")
    doc.write_text(
        good.replace("## classic vs tahoe", "## tampered", 1), encoding="utf-8"
    )
    assert main([str(payload_path), "--check", str(doc)]) == 3


def test_latex_marked_blocks_update(tmp_path):
    payload_path = _make_payload(tmp_path)
    payload = _load(payload_path)
    doc = tmp_path / "results.tex"
    begin = _begin("tex", "pair") + "\n"
    end = _end("tex", "pair") + "\n"
    doc.write_text(
        "% paper fragment\n\n" + begin + "% old\n" + end + "% tail\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    expected = "\n".join(render_block(payload, "pair", "tex"))
    assert text == "% paper fragment\n\n" + begin + expected + "\n" + end + "% tail\n"
    assert r"\toprule" in text and r"\bottomrule" in text
    assert "% old" not in text
    # Idempotent: a second update changes nothing.
    assert main([str(payload_path), "--update", str(doc)]) == 0
    assert doc.read_text(encoding="utf-8") == text


BAD_MARKER_FILES = {
    "begin_without_end": _begin("md", "overall") + "\nstale\n",
    "end_without_begin": _end("md", "overall") + "\n",
    "name_mismatch": (
        _begin("md", "overall") + "\nx\n" + _end("md", "pair") + "\n"
    ),
    "duplicate_name": (
        _begin("md", "overall") + "\nx\n" + _end("md", "overall") + "\n"
        + _begin("md", "overall") + "\ny\n" + _end("md", "overall") + "\n"
    ),
    "nested_begin": (
        _begin("md", "overall") + "\n" + _begin("md", "pair") + "\nx\n"
        + _end("md", "pair") + "\n" + _end("md", "overall") + "\n"
    ),
    "unknown_name": _begin("md", "bogus") + "\nx\n" + _end("md", "bogus") + "\n",
    "no_markers": "just prose, nothing to update\n",
    "missing_name": (
        "<!-- CANONICAL_RESULTS:BEGIN -->\nx\n<!-- CANONICAL_RESULTS:END -->\n"
    ),
    "wrong_case": (
        "<!-- canonical_results:begin overall -->\nx\n"
        "<!-- canonical_results:end overall -->\n"
    ),
    "tex_markers_in_md_file": (
        "% CANONICAL_RESULTS:BEGIN overall\nx\n% CANONICAL_RESULTS:END overall\n"
    ),
}


@pytest.mark.parametrize("case", sorted(BAD_MARKER_FILES))
def test_malformed_or_ambiguous_markers_refused(tmp_path, case):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(BAD_MARKER_FILES[case], encoding="utf-8")
    before = doc.read_bytes()
    assert main([str(payload_path), "--update", str(doc)]) == 1
    assert doc.read_bytes() == before  # refused means untouched
    assert main([str(payload_path), "--check", str(doc)]) == 1
    assert doc.read_bytes() == before


def test_standalone_write_refuses_files_with_markers(tmp_path):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text(
        _begin("md", "overall") + "\n" + _end("md", "overall") + "\n",
        encoding="utf-8",
    )
    before = doc.read_bytes()
    assert main([str(payload_path), "--markdown", str(doc)]) == 1
    assert main([str(payload_path), "--latex", str(doc)]) == 1
    assert doc.read_bytes() == before


def test_cannot_infer_format_without_extension(tmp_path, capsys):
    payload_path = _make_payload(tmp_path)
    doc = tmp_path / "noext"
    doc.write_text("x\n", encoding="utf-8")
    assert main([str(payload_path), "--update", str(doc)]) == 1  # no format
    assert "infer" in capsys.readouterr().err
    # Explicit format on an unmarked file still refuses (nothing to update).
    assert main([str(payload_path), "--update", str(doc) + ":md"]) == 1
    assert "no canonical-results markers" in capsys.readouterr().err
    assert doc.read_text(encoding="utf-8") == "x\n"


# -- determinism, idempotence, read-only inputs ------------------------------


def test_renders_are_deterministic_and_idempotent(tmp_path):
    payload_path = _make_payload(tmp_path)
    md1, tex1 = tmp_path / "a.md", tmp_path / "a.tex"
    md2, tex2 = tmp_path / "b.md", tmp_path / "b.tex"
    assert main([str(payload_path), "--markdown", str(md1), "--latex", str(tex1)]) == 0
    assert main([str(payload_path), "--markdown", str(md2), "--latex", str(tex2)]) == 0
    assert md1.read_bytes() == md2.read_bytes()
    assert tex1.read_bytes() == tex2.read_bytes()
    for doc in (md1, tex1):
        text = doc.read_text(encoding="utf-8")
        assert "generated_at" not in text
        assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", text)  # no ISO dates

    doc = tmp_path / "idem.md"
    doc.write_text(
        _begin("md", "overall") + "\nold\n" + _end("md", "overall") + "\n",
        encoding="utf-8",
    )
    assert main([str(payload_path), "--update", str(doc)]) == 0
    first = doc.read_bytes()
    assert main([str(payload_path), "--update", str(doc)]) == 0
    assert doc.read_bytes() == first


def test_payload_is_read_only_and_never_a_target(tmp_path):
    payload_path = _make_payload(tmp_path)
    before = payload_path.read_bytes()
    fixture_before = FIXTURE.read_bytes()

    doc = tmp_path / "doc.md"
    doc.write_text(
        _begin("md", "overall") + "\nold\n" + _end("md", "overall") + "\n",
        encoding="utf-8",
    )
    md, tex = tmp_path / "out.md", tmp_path / "out.tex"
    assert main([
        str(payload_path), "--markdown", str(md), "--latex", str(tex),
        "--update", str(doc),
    ]) == 0
    assert payload_path.read_bytes() == before
    assert FIXTURE.read_bytes() == fixture_before

    # Every mode refuses the canonical payload as its target.
    for argv in (
        [str(payload_path), "--markdown", str(payload_path)],
        [str(payload_path), "--latex", str(payload_path)],
        [str(payload_path), "--update", str(payload_path) + ":md"],
        [str(payload_path), "--check", str(payload_path) + ":md"],
    ):
        assert main(argv) == 1
    assert payload_path.read_bytes() == before


# -- tampered or incomplete payloads are refused loudly -----------------------


def test_validate_payload_refuses_tampered_payloads(tmp_path):
    payload = _load(_make_payload(tmp_path))

    def _expect_failure(mutated, needle):
        with pytest.raises(RenderError) as excinfo:
            validate_payload(mutated)
        assert needle in str(excinfo.value)

    cases = []
    missing_micro = copy.deepcopy(payload)
    del missing_micro["overall"]["arms"]["classic"]["micro_accuracy"]
    cases.append((missing_micro, "micro_accuracy"))

    bad_schema = copy.deepcopy(payload)
    bad_schema["schema"] = "canonical-results/999"
    cases.append((bad_schema, "schema"))

    missing_analysis = copy.deepcopy(payload)
    del missing_analysis["analysis_provenance"]
    cases.append((missing_analysis, "analysis_provenance"))

    tampered_analysis = copy.deepcopy(payload)
    tampered_analysis["analysis_provenance"]["payload_schema"] = "canonical-results/9"
    cases.append((tampered_analysis, "payload_schema"))

    tampered_sha = copy.deepcopy(payload)
    tampered_sha["analysis_provenance"]["files"]["benchmarks/stats.py"] = 42
    cases.append((tampered_sha, "files']['benchmarks/stats.py']"))

    bad_lineage = copy.deepcopy(payload)
    bad_lineage["provenance"]["total_trials"] = 11
    cases.append((bad_lineage, "total_trials"))

    missing_input_sha = copy.deepcopy(payload)
    del missing_input_sha["provenance"]["inputs"][0]["sha256"]
    cases.append((missing_input_sha, "sha256"))

    for mutated, needle in cases:
        _expect_failure(mutated, needle)

    # The CLI refuses too and writes nothing.
    out = tmp_path / "out.md"
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(missing_analysis), encoding="utf-8")
    assert main([str(bad_path), "--markdown", str(out)]) == 1
    assert not out.exists()


def test_validate_payload_accepts_the_real_artifact(tmp_path):
    # The fixture-generated artifact must pass validation untouched.
    validate_payload(_load(_make_payload(tmp_path)))
