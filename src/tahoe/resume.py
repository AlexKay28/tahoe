"""Crash-window recovery: resume an interrupted TAHOE run (issue #10).

Implements the pragmatic subset of the deterministic resume algorithm
from ``demo/runs/crash-recovery-glm52/solution.md`` (crash-window table
W0a-W12) that is correct-by-construction with the current event schema:

- A run with a RUN_FINISHED event is terminal: the recorded status is
  returned without appending anything (``"already_terminal": true``).
  This covers W4, W10, W11 and W12 — no resume is possible or needed.
- Otherwise the first plan entry without a terminal SUCCEEDED event is
  re-executed through the coordinator's own machinery
  (:meth:`SequentialCoordinator._resume_existing_run`).  Committed
  lifecycle events (task_started / INVOCATION_READY /
  INVOCATION_DISPATCHED) are never re-emitted, but the worker call IS
  re-executed: dispatch never implies success (at-least-once for the
  worker call; the ``run_id:invocation_id`` idempotency key carried by
  INVOCATION_DISPATCHED payloads since wave 4 is the dedup contract for
  effectful workers).  RESULT_RECEIVED, VALIDATION_PASSED and the atomic
  SUCCEEDED batch are appended fresh.
- Tasks missing because the crash predated the task-creation batch (W0a)
  are created first with the same text/mapping rule as a normal start.
- Tasks for already-completed steps are COMPLETED; the resumed step's
  task is IN_PROGRESS (started before the crash) — ``start_task``
  requires PENDING, so the coordinator skips the start when the task is
  already IN_PROGRESS and raises only on impossible states.
- Append-only: resume appends new events with the continuing gapless
  seq the EventStore guarantees, and a second SUCCEEDED terminal for the
  same invocation is impossible by the store's duplicate guard.

Child runs (issue #20): a parent crash during a CALL resumes through the
CALL entry itself.  ``_execute_call`` finds the child run under the
deterministic id ``"<parent_run_id>:<invocation_id>"`` and either adopts
an already-terminal child without re-executing it (crash after child
completion, before parent adoption) or re-drives a non-terminal child
through the same resume core (at-least-once; the child's own
idempotency keys cover its effectful steps).  Adoption commits in the
same atomic batch as the CALL's SUCCEEDED delta, so crashes before/after
adoption never duplicate output commits.

Deferred windows (see solution.md): W5 result adoption without a worker
re-call (the resume path re-executes instead — at-least-once), and the
idempotency-key external-effect query for W3 (needs external system
cooperation that does not exist yet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tahoe.budgets import BudgetGate, ExecutionBudget
from tahoe.runtime.coordinator import SequentialCoordinator, _uses_kb_refs
from tahoe.runtime.events import EventStore, EventType, StateVersionConflict
from tahoe.syntax import seal_digest, validate_program
from tahoe.syntax.model import (
    Conditional,
    First,
    Loop,
    Return,
    Stop,
    Try,
)

if TYPE_CHECKING:
    from tahoe.memory import KnowledgeBase
    from tahoe.syntax.model import Program

__all__ = ["resume_run"]


def _sole_return_refs(program: "Program") -> tuple[str, ...] | None:
    """Refs of the program's sole RETURN when a legacy replay is exact.

    A terminal RUN_FINISHED recorded before outputs were persisted (a
    legacy run) carries only its status, so the original outputs must be
    reconstructed by replaying the committed deltas.  That replay is
    exact only when the RETURN is the program's single terminal of any
    kind (no STOP, no nested RETURN, no LOOP EXHAUSTED terminal): then
    a ``succeeded`` legacy run can only have finished through that
    RETURN, and its refs' replayed values are the original outputs.
    Any other terminal shape makes the terminating statement
    undecidable from the event history, so ``None`` keeps the safe
    empty output mapping.
    """
    returns: list[Return] = []
    stops: list[Stop] = []

    def walk(statements: tuple[object, ...]) -> None:
        for statement in statements:
            if isinstance(statement, Return):
                returns.append(statement)
            elif isinstance(statement, Stop):
                stops.append(statement)
            elif isinstance(statement, Conditional):
                walk((statement.statement,))
                walk(statement.if_branch_extra)
                walk(statement.else_branch or ())
            elif isinstance(statement, Loop):
                walk(statement.body)
                if isinstance(statement.exhausted, Stop):
                    stops.append(statement.exhausted)
            elif isinstance(statement, First):
                walk(statement.body)
            elif isinstance(statement, Try):
                for branch in statement.branches:
                    walk(branch)

    walk(program.statements)
    if len(returns) != 1 or stops:
        return None
    sole = returns[0]
    for statement in program.statements:
        if statement is sole:
            return sole.refs
    return None


def resume_run(
    store: EventStore,
    worker: Any,
    run_id: str,
    program: "Program",
    memory: "KnowledgeBase | None" = None,
    protocols_dir: str | None = None,
    workspace_root: str | None = None,
    budget: "ExecutionBudget | None" = None,
    max_workers: int | None = None,
    allow_unsealed_legacy: bool = False,
) -> dict[str, Any]:
    """Resume an interrupted run; same result shape as ``execute``.

    Loads the run's events; returns the recorded terminal status when a
    RUN_FINISHED exists, otherwise verifies the run's identity and hands
    the remaining plan to the coordinator's
    :meth:`SequentialCoordinator._resume_existing_run` with the same
    ledger/event invariants as a fresh start.

    Every resumed run verifies the original program seal recorded in its
    RUN_STARTED payload: a run whose recorded seal does not match
    ``seal_digest(program)`` is refused, and so is a run with *no*
    recorded seal (recorded before seals were persisted, or with no
    RUN_STARTED payload at all) — its original program cannot be
    verified, so resuming it is refused by default.  Such a legacy run
    resumes only through the explicitly unsafe ``allow_unsealed_legacy``
    opt-in, which never excuses a *mismatched* seal.

    ``allow_unsealed_legacy`` (default ``False``) names that unsafe
    behavior deliberately: passing ``True`` resumes an unsealed legacy
    run without any program-seal verification.

    ``workspace_root`` mirrors the coordinator's WorkspacePolicy hook so
    a resumed run dispatches effectful commands exactly like ``run``.

    ``budget`` (issue #41) installs an :class:`ExecutionBudget` on the
    resumed run.  The gate's wall-clock start is shifted backwards by the
    pre-crash elapsed time (derived from the run's first event timestamp)
    so the resumed run enforces the *remaining* global deadline.

    ``max_workers`` (issue #41) selects the execution strategy, mirroring
    ``execute``.  ``None`` defaults to 1 (sequential), matching the
    historical resume behavior.
    """
    validate_program(
        program,
        known_commands=worker.commands,
        protocols_dir=protocols_dir,
    )
    if memory is None and _uses_kb_refs(program):
        raise ValueError(
            "program uses KB.* references but no knowledge base was"
            " provided: pass memory=KnowledgeBase(path) to resume_run"
        )

    events = store.events(run_id)

    # -- identity: the run must exist and belong to this program ------
    # (store.run raises KeyError for an unknown run; the RUN_STARTED
    # payload records the sealed program a fresh start committed.)
    store.run(run_id)
    run_started = next(
        (event for event in events if event.event_type is EventType.RUN_STARTED),
        None,
    )
    started_payload = (
        run_started.payload
        if run_started is not None and isinstance(run_started.payload, dict)
        else {}
    )
    if started_payload.get("program") is not None:
        recorded = (
            started_payload.get("program"),
            started_payload.get("version"),
        )
        if recorded != (program.name, program.version):
            raise ValueError(
                f"program {program.name}@{program.version} does not match"
                f" the run's recorded program {recorded[0]}@{recorded[1]};"
                " refusing to resume with a mismatched program"
            )
    recorded_seal = started_payload.get("seal_digest")
    if recorded_seal is None and not allow_unsealed_legacy:
        # Every resumed run verifies the original program seal.  A run
        # with no recorded seal (recorded before seal_digest joined the
        # RUN_STARTED payload, or with no RUN_STARTED at all) cannot be
        # verified against the presented program, so resuming it is
        # refused by default — before any event is appended — unless the
        # explicitly unsafe legacy opt-in is passed.
        raise ValueError(
            f"run {run_id!r} records no program seal digest (no"
            " RUN_STARTED payload, or one recorded before seals were"
            " persisted); the original program cannot be verified."
            " Refusing to resume an unsealed legacy run; pass"
            " allow_unsealed_legacy=True to resume it anyway"
        )
    if recorded_seal is not None and recorded_seal != seal_digest(program):
        raise ValueError(
            "program seal digest does not match the run's recorded"
            " seal; refusing to resume with a mismatched program"
        )

    # -- terminal runs are never resumed (W4/W10/W11/W12) -------------
    # Issue #77: an AWAIT-blocked run has no RUN_FINISHED — it is
    # non-terminal and resumes naturally through _resume_existing_run.
    run_finished = [
        event for event in events if event.event_type is EventType.RUN_FINISHED
    ]
    terminal_finished = []
    for event in run_finished:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if not (
            payload.get("status") == "blocked"
            and payload.get("reason") == "approve"
        ):
            terminal_finished.append(event)
    if terminal_finished:
        payload = (
            terminal_finished[-1].payload
            if isinstance(terminal_finished[-1].payload, dict)
            else {}
        )
        outputs = payload.get("outputs")
        if not isinstance(outputs, dict):
            # Legacy terminal run (recorded before outputs joined the
            # RUN_FINISHED payload): reconstruct the original RETURN
            # outputs only when a single-RETURN program makes the
            # replay exact (see _sole_return_refs).
            outputs = {}
            if payload.get("status") == "succeeded":
                refs = _sole_return_refs(program)
                if refs is not None:
                    values = {
                        declaration.ref: declaration.value
                        for declaration in program.declarations
                    }
                    SequentialCoordinator._apply_committed_deltas(
                        values, events
                    )
                    outputs = {ref: values.get(ref) for ref in refs}
        result: dict[str, Any] = {
            "run_id": run_id,
            "status": payload.get("status", "unknown"),
            "outputs": outputs,
            "already_terminal": True,
        }
        if "error" in payload:
            result["error"] = payload["error"]
        return result

    coordinator = SequentialCoordinator(
        store,
        worker,
        memory=memory,
        workspace_root=workspace_root,
        protocols_dir=protocols_dir,
    )

    # Issue #41: build a gate from the budget, shifting the wall-clock
    # start backwards by the pre-crash elapsed time so the resumed run
    # enforces the *remaining* global deadline.  The offset is derived
    # from the run's first event timestamp (occurred_at) relative to now.
    gate: BudgetGate | None = None
    if budget is not None:
        if not isinstance(budget, ExecutionBudget):
            raise TypeError(
                f"budget must be an ExecutionBudget or None,"
                f" got {type(budget).__name__}"
            )
        elapsed_offset = 0.0
        if budget.global_deadline_seconds is not None and events:
            first_ts = events[0].occurred_at
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            elapsed_offset = (now - first_ts).total_seconds()
            elapsed_offset = max(0.0, elapsed_offset)
        gate = BudgetGate(budget, elapsed_offset=elapsed_offset)

    workers = max_workers if max_workers is not None else 1
    try:
        return coordinator._resume_existing_run(
            program,
            run_id,
            gate=gate,
            max_workers=workers,
        )
    except StateVersionConflict as exc:
        return {
            "run_id": run_id,
            "status": "conflict",
            "error": (
                f"concurrent resume detected for run {run_id!r}:"
                f" another process may have already resumed it"
                f" ({exc})"
            ),
            "outputs": {},
        }
