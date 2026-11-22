"""Static type checker with the substitutability lattice (issue #71).

The node types form a partial order under ⊑ (read "is a subtype of",
meaning *safely substitutable for*): ``τ1 ⊑ τ2`` holds exactly when a
``τ1`` value may be supplied where a ``τ2`` value is declared/expected,
because the subtype carries at least the epistemic warrant or commitment
the supertype slot requires.

⊑ captures *safe substitutability only*.  It deliberately does NOT
capture epistemic promotion: an assumption, goal, or hypothesis must
never implicitly become evidence, a fact, or a verification, and
evidence must never implicitly become a fact.  The checker never
derives a higher-warrant type from a lower one; converting an
existing node to a higher-warrant type is command work (e.g.
``verify`` commits V, ``estimate`` commits F, ``choose`` commits D).
High-warrant nodes may also be introduced by explicit INPUT
declarations (which assert a node's type directly) — what is excluded
is implicit conversion through the type system, not command-free
introduction of freshly declared nodes.  Hence the warrant chain runs
``V ⊑ F ⊑ E`` (a verified result is a fact; a fact is evidence), and
there is no edge in the reverse direction.

The lattice is implemented here and specified in
``paper/design/formal-semantics.md`` §3.1–3.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .syntax.model import (
    Call,
    Conditional,
    Declaration,
    DonePredicate,
    Gather,
    Invocation,
    Loop,
    Par,
    Program,
    Reformulate,
    Return,
    Scatter,
    Stop,
    Try,
)

if TYPE_CHECKING:
    from .registry.registry import Registry

#: Substitutability edges from the 7 axioms in formal-semantics.md §3.2.
#: Each entry ``src: [dst1, dst2, ...]`` means ``src ⊑ dst`` (src is a
#: subtype of dst, i.e. a src value safely fills a dst slot).  The
#: order is a forest of five disjoint chains — one per role family —
#: with no global top or bottom:
#:
#: - warrant chain:   V ⊑ F ⊑ E  (verified ⊑ fact ⊑ evidence)
#: - posit chain:     A ⊑ H      (assumption ⊑ hypothesis)
#: - openness chain:  G ⊑ Q ⊑ U  (goal ⊑ question ⊑ unknown)
#: - commitment:      D ⊑ O      (decision ⊑ option)
#: - preference:      C ⊑ PF     (constraint ⊑ preference)
#:
#: Every old "promotion" edge (Q⊑A, U⊑H, A⊑E, H⊑F, H⊑D, O⊑D, D⊑V,
#: F⊑V, and G⊑C as a role conversion) is gone: promotions are performed
#: by commands at runtime, never by the type system.
SUBLATTICE: dict[str, list[str]] = {
    "V": ["F"],
    "F": ["E"],
    "A": ["H"],
    "G": ["Q"],
    "Q": ["U"],
    "C": ["PF"],
    "D": ["O"],
}

#: Types orthogonal to the main lattice — no subtyping with lattice
#: types (or each other) beyond reflexivity.
ORTHOGONAL: frozenset[str] = frozenset({
    "CTX", "K", "X", "R", "OUT", "ART", "PR", "P",
})

ALL_TYPES: frozenset[str] = frozenset(
    set(SUBLATTICE.keys()) | {d for dsts in SUBLATTICE.values() for d in dsts} | ORTHOGONAL
)

#: The 7 axiomatic edges from formal-semantics.md §3.2, as (subtype, supertype) pairs.
LATTICE_AXIOMS: frozenset[tuple[str, str]] = frozenset({
    ("V", "F"), ("F", "E"), ("A", "H"), ("G", "Q"),
    ("Q", "U"), ("C", "PF"), ("D", "O"),
})


def is_subtype(t1: str, t2: str) -> bool:
    """True if t1 ⊑ t2 (a t1 value can fill a slot expecting t2).

    Computes the reflexive-transitive closure of SUBLATTICE via BFS.
    Orthogonal types are subtypes only of themselves.  Families are
    disjoint: there is no derivation across chains, so a goal,
    assumption, or hypothesis is never a subtype of evidence, a fact,
    or a verification, and a decision is incomparable with a
    verification.
    """
    if t1 == t2:
        return True
    if t1 in ORTHOGONAL or t2 in ORTHOGONAL:
        return t1 == t2
    visited: set[str] = set()
    queue: list[str] = [t1]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for parent in SUBLATTICE.get(current, []):
            if parent == t2:
                return True
            queue.append(parent)
    return False


def _ref_type(ref: str) -> str:
    """Extract the type prefix from a typed reference like 'E.result'."""
    return ref.split(".")[0]


def _parse_type_spec(type_str: str) -> str | None:
    """Parse a contract type string and return its node-type prefix.

    Contract entries use ``name:type`` where ``type`` may be:
    - a node-type prefix (single uppercase letter or ``OUT``)
    - a slash compound like ``G/C/P/K/OUT``
    - a primitive like ``text``, ``json``, ``refs``, etc.

    Returns the first node-type prefix found, or ``None`` for non-node types.
    """
    if not type_str:
        return None
    if "/" in type_str:
        for seg in type_str.split("/"):
            if seg in ALL_TYPES:
                return seg
        return None
    if type_str in ALL_TYPES:
        return type_str
    return None


def _parse_type_specs(type_str: str) -> list[str]:
    """Parse a contract type string and return all node-type prefixes.

    For slash compounds like ``G/C/P/K/OUT`` returns ``["G", "C", "P", "K", "OUT"]``.
    For single node types returns ``[type]``.
    For non-node types returns ``[]``.
    """
    if not type_str:
        return []
    if "/" in type_str:
        return [seg for seg in type_str.split("/") if seg in ALL_TYPES]
    if type_str in ALL_TYPES:
        return [type_str]
    return []


def _parse_input_spec(entry: str) -> tuple[str, str | None]:
    """Parse ``name:type`` from a contract input/parameter entry."""
    if ":" not in entry:
        return entry, None
    name, type_part = entry.split(":", 1)
    return name.strip(), _parse_type_spec(type_part.strip())


def _parse_input_spec_full(entry: str) -> tuple[str, str | None, str]:
    """Parse ``name:type`` returning (name, first_node_type, raw_type_str)."""
    if ":" not in entry:
        return entry, None, ""
    name, type_part = entry.split(":", 1)
    type_part = type_part.strip()
    return name.strip(), _parse_type_spec(type_part), type_part


def _collect_invocation_errors(
    command: str,
    args: tuple,
    targets: tuple[str, ...],
    state: dict[str, str],
    registry: Registry | None,
) -> list[str]:
    """Check that a DO invocation matches its command contract.

    Two judgments are made (formal-semantics.md §3.3):

    - Input compatibility: each typed argument's actual node type must
      be a subtype of the contract's accepted type for that argument
      (compound accepted types like ``Q/U`` are a union — actual ⊑ some
      member).
    - Output assignment: contract outputs map to invocation targets
      positionally (target i ↔ declared output i); the produced type
      must be a subtype of the target's declared type (produced ⊑
      target).  Compound outputs like ``G/C/P/K/OUT`` stay unions —
      some member must be a subtype of the target type.
    """
    if registry is None:
        return []
    try:
        spec = registry.resolve(command)
    except Exception:
        return [f"unknown command: {command}"]

    errors: list[str] = []
    input_types: dict[str, list[str]] = {}
    for entry in spec.inputs:
        name, _, type_part = _parse_input_spec_full(entry)
        input_types[name] = _parse_type_specs(type_part)

    for arg in args:
        expected_types = input_types.get(arg.name, [])
        if not expected_types:
            continue
        if not isinstance(arg.value, str):
            continue
        actual_type = _ref_type(arg.value)
        if actual_type not in ALL_TYPES:
            continue
        if not any(is_subtype(actual_type, e) for e in expected_types):
            errors.append(
                f"type mismatch: argument {arg.name} expects"
                f" {'/'.join(expected_types)}"
                f" but got {actual_type}"
            )

    # Output check: contract outputs map to invocation targets
    # positionally (target i is filled by declared output i; targets
    # beyond the declared outputs have no contract type to check
    # against).  Compound outputs like ``G/C/P/K/OUT`` stay unions: the
    # check passes when at least one member is a subtype of the
    # target's declared type.  The direction is produced-to-target —
    # the value the command produces must be safely substitutable for
    # the target slot's declared type (produced ⊑ target), never the
    # other way around.
    output_specs: list[tuple[str, list[str]]] = []
    for entry in spec.outputs:
        name, _, type_part = _parse_input_spec_full(entry)
        output_specs.append((name, _parse_type_specs(type_part)))

    for target, (out_name, out_types) in zip(targets, output_specs):
        if target.startswith("KB."):
            continue
        target_type = _ref_type(target)
        if out_types and not any(is_subtype(ot, target_type) for ot in out_types):
            errors.append(
                f"type mismatch: output {out_name} produces"
                f" {'/'.join(out_types)}"
                f" but target {target} expects {target_type}"
            )

    return errors


def _collect_done_errors(
    invocation: Invocation,
    state: dict[str, str],
) -> list[str]:
    """Check that a DONE predicate references a valid target ref type.

    A DONE predicate's ``ref`` must be one of the invocation's own targets
    (or a previously committed ref).  The ref's type must be a lattice
    type (not orthogonal) — DONE tests epistemic properties, not artifacts
    or context.
    """
    if invocation.done is None:
        return []
    errors: list[str] = []
    done: DonePredicate = invocation.done
    done_ref = done.ref

    target_set = set(invocation.targets)
    if done_ref not in target_set and done_ref not in state:
        errors.append(
            f"type error: DONE predicate references {done_ref}"
            f" which is not a target of step {invocation.step_id}"
            f" or a previously committed ref"
        )
        return errors

    done_type = _ref_type(done_ref)
    if done_type in ORTHOGONAL:
        errors.append(
            f"type error: DONE predicate on {done_ref} has orthogonal type {done_type};"
            f" DONE tests epistemic properties, not orthogonal types"
        )

    return errors


def _collect_try_errors(
    statement: Try,
    state: dict[str, str],
    registry: Registry | None,
) -> list[str]:
    """Check that TRY branch statements are well-typed and branch
    targets have compatible types.

    Errors from nested branch statements (unknown commands, argument
    mismatches, output mismatches, DONE errors) are collected and
    reported, so nothing can hide inside a speculative branch.

    All branches in a TRY block should produce compatible target types.
    If one branch produces V.result and another produces H.guess, the
    type mismatch is reported as a warning.  Comparison is by leaf name
    (the part after the dot) — if two branches target the same leaf name
    with different type prefixes, those types must be compatible under ⊑.
    """
    errors: list[str] = []

    branch_target_types: list[dict[str, str]] = []
    for branch in statement.branches:
        branch_state = dict(state)
        branch_types: dict[str, str] = {}
        for stmt in branch:
            # Nested statement errors (unknown commands, argument
            # mismatches, output mismatches) are reported, not
            # discarded — a TRY branch is not a place where an
            # ill-typed step can hide.
            errors.extend(_collect_statement_errors(stmt, branch_state, registry))
            if isinstance(stmt, Invocation):
                for target in stmt.targets:
                    if not target.startswith("KB."):
                        leaf = target.split(".", 1)[1] if "." in target else target
                        branch_types[leaf] = _ref_type(target)
            elif isinstance(stmt, Call):
                for target in stmt.targets:
                    if not target.startswith("KB."):
                        leaf = target.split(".", 1)[1] if "." in target else target
                        branch_types[leaf] = _ref_type(target)
        branch_target_types.append(branch_types)

    if len(branch_target_types) < 2:
        return errors

    all_leaves: set[str] = set()
    for bt in branch_target_types:
        all_leaves |= set(bt.keys())

    for leaf in sorted(all_leaves):
        types_seen = []
        for bt in branch_target_types:
            if leaf in bt:
                types_seen.append(bt[leaf])
        if len(types_seen) < 2:
            continue
        for i in range(len(types_seen)):
            for j in range(i + 1, len(types_seen)):
                if (
                    not is_subtype(types_seen[i], types_seen[j])
                    and not is_subtype(types_seen[j], types_seen[i])
                ):
                    errors.append(
                        f"type mismatch: TRY branch target *.{leaf}"
                        f" has incompatible types: {types_seen[i]}"
                        f" and {types_seen[j]}"
                    )

    return errors


def _collect_statement_errors(
    statement: object,
    state: dict[str, str],
    registry: Registry | None,
) -> list[str]:
    """Collect type errors from a single statement, mutating ``state``."""
    errors: list[str] = []

    if isinstance(statement, Invocation):
        errors.extend(
            _collect_invocation_errors(
                statement.command,
                statement.args,
                statement.targets,
                state,
                registry,
            )
        )
        errors.extend(_collect_done_errors(statement, state))
        for target in statement.targets:
            if not target.startswith("KB."):
                state[target] = _ref_type(target)
    elif isinstance(statement, Call):
        for target in statement.targets:
            if not target.startswith("KB."):
                state[target] = _ref_type(target)
    elif isinstance(statement, Return):
        pass
    elif isinstance(statement, Stop):
        pass
    elif isinstance(statement, Conditional):
        errors.extend(
            _collect_statement_errors(statement.statement, state, registry)
        )
        if statement.else_branch is not None:
            for else_stmt in statement.else_branch:
                errors.extend(
                    _collect_statement_errors(else_stmt, state, registry)
                )
        if statement.if_branch_extra:
            for extra_stmt in statement.if_branch_extra:
                errors.extend(
                    _collect_statement_errors(extra_stmt, state, registry)
                )
    elif isinstance(statement, Scatter):
        errors.extend(
            _collect_statement_errors(statement.body, state, registry)
        )
    elif isinstance(statement, Gather):
        if not statement.alias_ref.startswith("KB."):
            state[statement.alias_ref] = _ref_type(statement.alias_ref)
    elif isinstance(statement, Par):
        for branch in statement.branches:
            if branch.invocation is not None:
                errors.extend(
                    _collect_statement_errors(
                        branch.invocation, state, registry
                    )
                )
            elif branch.call is not None:
                for target in branch.call.targets:
                    if not target.startswith("KB."):
                        state[target] = _ref_type(target)
        for target in statement.barrier_targets:
            if not target.startswith("KB."):
                state[target] = _ref_type(target)
    elif isinstance(statement, Loop):
        for body_stmt in statement.body:
            errors.extend(
                _collect_statement_errors(body_stmt, state, registry)
            )
    elif isinstance(statement, Try):
        errors.extend(_collect_try_errors(statement, state, registry))
        for branch in statement.branches:
            for stmt in branch:
                if isinstance(stmt, Invocation):
                    for target in stmt.targets:
                        if not target.startswith("KB."):
                            state[target] = _ref_type(target)
                elif isinstance(stmt, Call):
                    for target in stmt.targets:
                        if not target.startswith("KB."):
                            state[target] = _ref_type(target)
    elif isinstance(statement, Reformulate):
        errors.extend(
            _collect_statement_errors(statement.diagnose, state, registry)
        )
        errors.extend(
            _collect_statement_errors(statement.replan, state, registry)
        )
        continue_type = _ref_type(statement.continue_ref)
        replan_targets = statement.replan.targets
        if replan_targets:
            replan_output_type = _ref_type(replan_targets[0])
            if not is_subtype(replan_output_type, continue_type):
                errors.append(
                    f"type mismatch: REPLAN output {replan_targets[0]}"
                    f" has type {replan_output_type} but CONTINUE ref"
                    f" {statement.continue_ref} expects {continue_type}"
                )
        state[statement.continue_ref] = continue_type

    return errors


def check_program_types(
    program: Program,
    registry: Registry | None = None,
) -> list[str]:
    """Type-check an entire program. Returns list of type error strings."""
    errors: list[str] = []
    state: dict[str, str] = {}

    for decl in program.declarations:
        state[decl.ref] = _ref_type(decl.ref)

    for stmt in program.statements:
        errors.extend(_collect_statement_errors(stmt, state, registry))

    return errors
