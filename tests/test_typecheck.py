"""Tests for the formal type checker with the substitutability lattice (issue #71).

The lattice separates safe type substitutability (τ ⊑ σ: a τ value may
fill a σ slot) from epistemic promotion (warrant growth through command
work — never through the type system).  Assumptions, goals, and
hypotheses must not implicitly become evidence, facts, or verifications;
the warrant chain runs V ⊑ F ⊑ E (verified ⊑ fact ⊑ evidence) with no
edge in the reverse direction, and D stays incomparable with V.
"""

import os
import subprocess
import sys
import tempfile

from tahoe.typecheck import (
    ALL_TYPES,
    LATTICE_AXIOMS,
    ORTHOGONAL,
    SUBLATTICE,
    check_program_types,
    is_subtype,
)
from tahoe.syntax import parse_program, validate_program, get_type_warnings
from tahoe.registry import builtin_registry


class TestSubstitutabilityLattice:
    """Tests for the 7 axiomatic edges and their reflexive-transitive closure."""

    def test_v_is_subtype_of_f(self):
        """V ⊑ F: a verified result carries its verification, so it is a fact."""
        assert is_subtype("V", "F") is True

    def test_f_is_subtype_of_e(self):
        """F ⊑ E: a fact is usable where evidence is expected."""
        assert is_subtype("F", "E") is True

    def test_v_is_subtype_of_e_transitive(self):
        """V ⊑ F ⊑ E, so a verified result is usable as evidence."""
        assert is_subtype("V", "E") is True

    def test_a_is_subtype_of_h(self):
        """A ⊑ H: an assumption is a posit taken as granted; it fills a
        hypothesis slot without inflating warrant (testing an assumption
        is coherent).  The converse is unsafe: a hypothesis is under active
        test and must not be silently taken as given."""
        assert is_subtype("A", "H") is True
        assert is_subtype("H", "A") is False

    def test_g_is_subtype_of_q(self):
        """G ⊑ Q: a goal is an open question of the form "how to achieve X"."""
        assert is_subtype("G", "Q") is True

    def test_q_is_subtype_of_u(self):
        """Q ⊑ U: a question marks a specific known unknown."""
        assert is_subtype("Q", "U") is True

    def test_g_is_subtype_of_u_transitive(self):
        """G ⊑ Q ⊑ U."""
        assert is_subtype("G", "U") is True

    def test_c_is_subtype_of_pf(self):
        """C ⊑ PF: a constraint is a strict preference."""
        assert is_subtype("C", "PF") is True

    def test_d_is_subtype_of_o(self):
        """D ⊑ O: a decision commits to one specific option, so it fills an
        option slot.  The converse is promotion (choose commits an option
        into a decision) and is not subtyping."""
        assert is_subtype("D", "O") is True
        assert is_subtype("O", "D") is False

    def test_reflexivity(self):
        for t in ALL_TYPES:
            assert is_subtype(t, t) is True, f"{t} should be a subtype of itself"

    def test_no_axiom_is_symmetric(self):
        """No axiom may be reversed: reversing would let a weaker-warrant
        slot silently stand in for a stronger one."""
        for sub, sup in LATTICE_AXIOMS:
            assert is_subtype(sup, sub) is False, (
                f"axiom {sup} ⊑ {sub} must not hold"
            )

    def test_evidence_never_implicitly_becomes_fact_or_verified(self):
        """E ⋢ F and E ⋢ V: evidence must be promoted by command work
        (e.g. estimate commits F, verify commits V), never by subtyping."""
        assert is_subtype("E", "F") is False
        assert is_subtype("E", "V") is False

    def test_fact_never_implicitly_becomes_verified(self):
        """F ⋢ V: verification is command work, not subtyping."""
        assert is_subtype("F", "V") is False

    def test_assumptions_never_become_evidence_fact_or_verified(self):
        """A ⋢ E, A ⋢ F, A ⋢ V (the old lattice derived all three)."""
        assert is_subtype("A", "E") is False
        assert is_subtype("A", "F") is False
        assert is_subtype("A", "V") is False

    def test_goals_never_become_claims_or_commitments(self):
        """G ⋢ E, G ⋢ F, G ⋢ V, G ⋢ H, G ⋢ D."""
        for other in ("E", "F", "V", "H", "D"):
            assert is_subtype("G", other) is False, (
                f"G ⊑ {other} must not hold"
            )

    def test_hypotheses_never_become_evidence_fact_verified_or_decisions(self):
        """H ⋢ E, H ⋢ F, H ⋢ V, H ⋢ D (all were derivable before)."""
        for other in ("E", "F", "V", "D"):
            assert is_subtype("H", other) is False, (
                f"H ⊑ {other} must not hold"
            )

    def test_d_and_v_incomparable(self):
        """A decision is a commitment; a verification is a test.  Neither
        subsumes the other, in either direction."""
        assert is_subtype("D", "V") is False
        assert is_subtype("V", "D") is False

    def test_d_and_e_incomparable(self):
        assert is_subtype("D", "E") is False
        assert is_subtype("E", "D") is False

    def test_e_and_d_not_confused_with_posits(self):
        """Claims (E) are not hypotheses or assumptions; posits are not claims."""
        assert is_subtype("E", "H") is False
        assert is_subtype("E", "A") is False
        assert is_subtype("F", "H") is False

    def test_question_never_becomes_assumption(self):
        """Q ⋢ A: assuming is command work, not subtyping."""
        assert is_subtype("Q", "A") is False

    def test_unknown_never_becomes_hypothesis(self):
        """U ⋢ H: hypothesizing is command work, not subtyping."""
        assert is_subtype("U", "H") is False

    def test_preference_not_an_option_and_option_not_a_preference(self):
        assert is_subtype("PF", "O") is False
        assert is_subtype("O", "PF") is False

    def test_goal_is_not_a_constraint(self):
        """G ⋢ C: framing a goal as a constraint is a role conversion done
        by the define command's node_schema, not subtyping."""
        assert is_subtype("G", "C") is False

    def test_no_cross_family_edges(self):
        """The five chains are disjoint: no derivation across families, so
        no role substitution between warrant, posit, openness, commitment,
        and preference types."""
        families = {
            "warrant": ("V", "F", "E"),
            "posit": ("A", "H"),
            "openness": ("G", "Q", "U"),
            "commitment": ("D", "O"),
            "preference": ("C", "PF"),
        }
        for t1 in ALL_TYPES - ORTHOGONAL:
            for t2 in ALL_TYPES - ORTHOGONAL:
                same = any(t1 in fam and t2 in fam for fam in families.values())
                if same:
                    continue
                assert is_subtype(t1, t2) is False, (
                    f"cross-family edge {t1} ⊑ {t2} must not exist"
                )

    def test_ctx_same_type(self):
        assert is_subtype("CTX", "CTX") is True

    def test_ctx_not_subtype_of_g(self):
        assert is_subtype("CTX", "G") is False

    def test_pr_same_type(self):
        assert is_subtype("PR", "PR") is True

    def test_pr_not_subtype_of_f(self):
        assert is_subtype("PR", "F") is False

    def test_orthogonal_types_only_match_themselves(self):
        for t in ORTHOGONAL:
            for other in ALL_TYPES:
                if other == t:
                    continue
                assert is_subtype(t, other) is False, (
                    f"orthogonal type {t} should not be subtype of {other}"
                )


class TestLatticeMatchesDoc:
    """Ensure the lattice in code matches the 7 axioms in formal-semantics.md §3.2."""

    def test_lattice_axioms_present(self):
        for sub, sup in LATTICE_AXIOMS:
            assert sub in SUBLATTICE, f"{sub} missing from SUBLATTICE"
            assert sup in SUBLATTICE[sub], (
                f"{sup} missing from SUBLATTICE[{sub}]"
            )

    def test_no_extra_edges(self):
        for src, dsts in SUBLATTICE.items():
            for dst in dsts:
                assert (src, dst) in LATTICE_AXIOMS, (
                    f"extra edge {src} -> {dst} not in axioms"
                )

    def test_7_axioms(self):
        assert len(LATTICE_AXIOMS) == 7

    def test_lattice_is_a_forest_of_five_chains(self):
        """Every lattice type reaches exactly the axioms' supertypes and
        nothing more: the closure adds V ⊑ E and G ⊑ U transitively."""
        reachable = {
            "V": {"V", "F", "E"},
            "F": {"F", "E"},
            "E": {"E"},
            "A": {"A", "H"},
            "H": {"H"},
            "G": {"G", "Q", "U"},
            "Q": {"Q", "U"},
            "U": {"U"},
            "C": {"C", "PF"},
            "PF": {"PF"},
            "D": {"D", "O"},
            "O": {"O"},
        }
        for src, expected in reachable.items():
            for other in ALL_TYPES - ORTHOGONAL:
                assert is_subtype(src, other) is (other in expected), (
                    f"closure of {src} must be {sorted(expected)},"
                    f" got {'+' if other in expected else '-'}{other}"
                )

    def test_orthogonal_types_complete(self):
        expected = {"CTX", "K", "X", "R", "OUT", "ART", "PR", "P"}
        assert expected <= ORTHOGONAL

    def test_pf_d_o_not_orthogonal(self):
        assert "PF" not in ORTHOGONAL
        assert "D" not in ORTHOGONAL
        assert "O" not in ORTHOGONAL


class TestProgramTypeChecking:
    """Test that check_program_types produces warnings for ill-typed programs
    and no warnings for well-typed programs."""

    WELL_TYPED = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = {"request": "ship"}

step.one: DO define(request = G.goal) -> G.typed

RETURN G.typed
"""

    ILL_TYPED_OUTPUT = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = {"request": "ship"}

step.one: DO define(request = G.goal) -> V.result

RETURN V.result
"""

    def test_well_typed_program_no_warnings(self):
        program = parse_program(self.WELL_TYPED)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_ill_typed_program_produces_warnings(self):
        program = parse_program(self.ILL_TYPED_OUTPUT)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert len(errors) > 0

    def test_validate_program_collects_type_warnings(self):
        program = parse_program(self.ILL_TYPED_OUTPUT)
        validate_program(program)
        warnings = get_type_warnings()
        assert len(warnings) > 0

    def test_validate_program_no_warnings_for_well_typed(self):
        program = parse_program(self.WELL_TYPED)
        validate_program(program)
        warnings = get_type_warnings()
        assert warnings == []

    def test_goal_usable_where_question_expected(self):
        """G ⊑ Q, so a G ref is valid where the contract expects Q:
        induce expects target_pattern:Q."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "what is the answer?"
  F.fact = "observed regularity"

step.one: DO induce(observations = F.fact, target_pattern = G.goal) -> H.rules

RETURN H.rules
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_fact_usable_where_evidence_expected(self):
        """F ⊑ E: a fact ref is valid where the contract expects E
        (induce expects observations:E)."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  F.fact = "observed regularity"
  Q.question = "what is the answer?"

step.one: DO induce(observations = F.fact, target_pattern = Q.question) -> H.rules

RETURN H.rules
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_verified_usable_where_fact_expected(self):
        """V ⊑ F: verify produces verdict:V, so targeting F is valid —
        a verified result can fill a fact slot."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO verify(goal = G.goal, evidence = "ev") -> F.verdict

RETURN F.verdict
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_verified_usable_where_evidence_expected(self):
        """V ⊑ E transitively: verify produces V, and the result may fill
        an evidence-typed target."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO verify(goal = G.goal, evidence = "ev") -> E.verdict

RETURN E.verdict
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_goal_rejected_where_evidence_expected(self):
        """G ⋢ E: a goal must never implicitly become evidence.  The old
        lattice accepted this program (G ⊑ Q ⊑ A ⊑ E); it must be rejected."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "what is the answer?"

step.one: DO induce(observations = G.goal, target_pattern = Q.question) -> H.rules

RETURN H.rules
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: argument observations expects E but got G"
        ]

    def test_hypothesis_rejected_where_evidence_expected(self):
        """H ⋢ E: a hypothesis must never implicitly become evidence."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  H.hyp = "conjecture"
  Q.question = "what is the answer?"

step.one: DO induce(observations = H.hyp, target_pattern = Q.question) -> H.rules

RETURN H.rules
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: argument observations expects E but got H"
        ]

    def test_assumption_rejected_where_evidence_expected(self):
        """A ⋢ E: an assumption must never implicitly become evidence."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  A.assumption = "taken as granted"
  Q.question = "what is the answer?"

step.one: DO induce(observations = A.assumption, target_pattern = Q.question) -> H.rules

RETURN H.rules
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: argument observations expects E but got A"
        ]

    def test_assumption_rejected_where_goal_expected(self):
        """A ⋢ G: verify expects goal:G; an assumption does not fill it."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  A.assumption = "taken as granted"

step.one: DO verify(goal = A.assumption, evidence = "ev") -> V.verdict

RETURN V.verdict
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: argument goal expects G but got A"
        ]

    def test_fact_rejected_where_verified_expected(self):
        """F ⋢ V (output direction): estimate produces estimate:F; a fact
        value must not fill a verification slot — promotion to V is
        verify's job, not the type system's."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  E.evidence = "some data"

step.one: DO estimate(evidence = E.evidence) -> V.est

RETURN V.est
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: output estimate produces F but target V.est expects V"
        ]

    def test_fact_rejected_where_goal_expected(self):
        """F ⋢ G (output direction): a fact value does not fill a goal slot."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  E.evidence = "some data"

step.one: DO estimate(evidence = E.evidence) -> G.est

RETURN G.est
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: output estimate produces F but target G.est expects G"
        ]

    def test_unknown_command_reported(self):
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO frobnicate(x = "y") -> E.result

RETURN E.result
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == ["unknown command: frobnicate"]


class TestInvocationOutputMapping:
    """Output targets are checked against the positionally-paired contract
    output, never all against the first output; compound outputs stay
    unions; the check runs produced-to-target (produced ⊑ target)."""

    def test_multi_target_positional_pairing(self):
        """define declares two outputs: typed_nodes:G/C/P/K/OUT and
        ambiguities:Q/U.  Positionally, target 0 pairs with typed_nodes and
        target 1 with ambiguities, so this well-typed program is clean."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO define(request = G.goal) -> G.nodes, Q.amb

RETURN G.nodes
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_multi_target_positional_error_names_paired_output(self):
        """The error for target 1 must cite ambiguities (the output it is
        paired with), not typed_nodes — the old checker compared every
        target against only the first command output."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO define(request = G.goal) -> G.nodes, V.bad

RETURN G.nodes
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == [
            "type mismatch: output ambiguities produces Q/U"
            " but target V.bad expects V"
        ]

    def test_compound_outputs_preserved_as_unions(self):
        """typed_nodes:G/C/P/K/OUT is a union: a Q-typed first target passes
        because G ⊑ Q is one of its members.  The compound is not collapsed
        to its first member."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO define(request = G.goal) -> Q.amb

RETURN Q.amb
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []

    def test_single_target_pairs_with_primary_output(self):
        """estimate declares estimate:F then posterior:PR.  A single F
        target pairs with estimate (F ⊑ F ✓); a single PR target also
        pairs with estimate (no node types), so challenge's PR target stays
        unchecked and only the DONE-orthogonality rule governs it."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  E.evidence = "some data"

step.one: DO estimate(evidence = E.evidence) -> F.est

RETURN F.est
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors == []


class TestDonePredicateTypeChecking:
    """Test DONE predicate type checking (issue #71 step 4)."""

    def test_done_on_valid_lattice_target_no_error(self):
        """A DONE predicate on a lattice target should not produce type errors."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = {"request": "ship"}

step.one: DO define(request = G.goal) -> G.typed
  DONE G.typed == {"request": "ship"}

RETURN G.typed
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        done_errors = [e for e in errors if "DONE" in e]
        assert done_errors == []

    def test_done_on_orthogonal_type_produces_error(self):
        """A DONE predicate on an orthogonal type (e.g. PR) should warn.
        The challenge command's contradiction output is the third declared
        output; positionally the single PR target pairs with the first
        output (artifacts — not node-typed), so the output check stays
        quiet and only the DONE-orthogonality rule fires."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

step.one: DO challenge(claim = "claim", evidence = "ev") -> PR.contradiction
  DONE PR.contradiction == 0.5

RETURN PR.contradiction
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        done_errors = [e for e in errors if "DONE" in e and "orthogonal" in e]
        assert len(done_errors) > 0


class TestTryBlockTypeChecking:
    """Test TRY block type checking (issue #71 step 5)."""

    def test_try_compatible_types_no_error(self):
        """TRY branches producing the same target type should not warn."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO define(request = G.goal) -> V.result
OR
  step.b: DO define(request = G.goal) -> V.result

RETURN V.result
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        try_errors = [e for e in errors if "TRY" in e]
        assert try_errors == []

    def test_try_incompatible_types_produces_error(self):
        """TRY branches producing incomparable types for the same target
        should warn. E and D are incomparable under ⊑."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO define(request = G.goal) -> E.result
OR
  step.b: DO define(request = G.goal) -> D.result

RETURN E.result
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        try_errors = [e for e in errors if "TRY" in e and "incompatible" in e]
        assert len(try_errors) > 0

    def test_try_reports_unknown_command_in_branch(self):
        """An unknown command inside a TRY branch must be reported.  The
        old checker called _collect_statement_errors on each branch
        statement but discarded its result, so unknown commands (and any
        other branch error) vanished inside TRY blocks."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO frobnicate(x = "y") -> E.r
OR
  step.b: DO define(request = G.goal) -> G.t

RETURN G.t
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert "unknown command: frobnicate" in errors

    def test_try_reports_argument_mismatch_in_branch(self):
        """An input type mismatch inside a TRY branch must be reported —
        goals never become evidence, not even speculatively."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO induce(observations = G.goal, target_pattern = G.goal) -> H.r
OR
  step.b: DO define(request = G.goal) -> G.t

RETURN G.t
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert "type mismatch: argument observations expects E but got G" in errors

    def test_try_reports_output_mismatch_in_branch(self):
        """An output mismatch inside a TRY branch must be reported: a
        fact-producing step may not target a verification slot."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO estimate(evidence = "ev") -> V.bad
OR
  step.b: DO define(request = G.goal) -> G.t

RETURN G.t
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert (
            "type mismatch: output estimate produces F"
            " but target V.bad expects V" in errors
        )

    def test_try_branch_errors_and_incompatibilities_both_reported(self):
        """A branch statement error and branch-target incompatibilities are
        distinct findings and all get reported: the unknown command once,
        plus one pairwise incompatibility message per incomparable branch
        pair (E/D across branches a,b and b,c)."""
        program_text = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = "test"

TRY MAX 3
  step.a: DO define(request = G.goal) -> E.result
OR
  step.b: DO define(request = G.goal) -> D.result
OR
  step.c: DO frobnicate(x = "y") -> E.result

RETURN E.result
"""
        program = parse_program(program_text)
        registry = builtin_registry()
        errors = check_program_types(program, registry)
        assert errors.count("unknown command: frobnicate") == 1
        incompat = [e for e in errors if "incompatible" in e]
        assert len(incompat) == 2
        assert {msg for msg in incompat} == {
            "type mismatch: TRY branch target *.result"
            " has incompatible types: E and D",
            "type mismatch: TRY branch target *.result"
            " has incompatible types: D and E",
        }


class TestCLITypecheck:
    """Test the `tahoe typecheck` CLI command."""

    def test_typecheck_valid_program(self):
        source = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = {"request": "ship"}

step.one: DO define(request = G.goal) -> G.typed

RETURN G.typed
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".think", delete=False
        ) as f:
            f.write(source)
            f.flush()
            path = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "tahoe.cli", "typecheck", path],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": "src"},
            )
            assert result.returncode == 0
            assert "no type errors" in result.stdout
        finally:
            os.unlink(path)

    def test_typecheck_ill_typed_program(self):
        source = """\
PROGRAM demo VERSION 0.1

INPUT
  G.goal = {"request": "ship"}

step.one: DO define(request = G.goal) -> V.result

RETURN V.result
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".think", delete=False
        ) as f:
            f.write(source)
            f.flush()
            path = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "tahoe.cli", "typecheck", path],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": "src"},
            )
            assert result.returncode == 0
            assert "type warning" in result.stderr
        finally:
            os.unlink(path)

    def test_typecheck_missing_file(self):
        result = subprocess.run(
            [sys.executable, "-m", "tahoe.cli", "typecheck", "/nonexistent.think"],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert result.returncode == 1