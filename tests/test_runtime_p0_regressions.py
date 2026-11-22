"""Focused regressions for runtime safety invariants."""

from __future__ import annotations

import hashlib
import threading

import pytest

from tahoe.budgets import ExecutionBudget
from tahoe.resume import resume_run
from tahoe.runtime import EventStore, EventType
from tahoe.runtime.coordinator import (
    CrashInterrupt,
    DeterministicWorker,
    SequentialCoordinator,
)
from tahoe.runtime.events import StateVersionConflict
from tahoe.runtime.tasks import TaskStatus
from tahoe.state import StateDelta
from tahoe.syntax import parse_program


def _worker(handlers=None):
    return DeterministicWorker(handlers or {"define": lambda goal: goal})


def test_task_ledger_default_read_serializes_with_the_store_lock(tmp_path):
    # Intermittent par-heterogeneous-4 'failed' regression: the
    # cache-aware default path of EventStore.task_ledger once skipped
    # the store lock, so a ledger read on one PAR branch thread could
    # interleave with a sibling branch's append_batch transaction on
    # the shared sqlite connection — torn row reads (JSONDecodeError
    # on an empty payload) and stale ledger-cache entries whose max-seq
    # water mark skipped committed task rows, so later replays dropped
    # them ("unknown task: task-1" child-run failures).  The default
    # ledger read must hold the store lock across the whole replay, so
    # a writer holding the lock (a sibling branch's append_batch) can
    # never observe — or race — the reader's SELECT and cache write.
    with EventStore(tmp_path / "events.db") as store:
        store.create_run("run", "prog@1.0")
        store.append("run", EventType.RUN_STARTED, payload={})
        store.append_task_event(
            "run",
            {
                "kind": "task_created",
                "id": "task-1",
                "text": "step.one: DO define",
                "priority": 0,
                "parent": None,
                "dependencies": (),
                "creator": "coordinator",
            },
        )

        # Park the reader between the run-metadata preflight and the
        # ledger replay — the exact window the pre-fix code ran
        # unlocked.
        at_preflight = threading.Event()
        past_preflight = threading.Event()
        orig_preflight = store._run_allows_concurrent

        def gated_preflight(run_id):
            concurrent = orig_preflight(run_id)
            at_preflight.set()
            past_preflight.wait(timeout=5)
            return concurrent

        store._run_allows_concurrent = gated_preflight

        read_done = threading.Event()
        outcome: dict[str, object] = {}

        def default_ledger_read():
            ledger = store.task_ledger("run")  # default allow_concurrent
            outcome["tasks"] = sorted(ledger.tasks)
            read_done.set()

        reader = threading.Thread(target=default_ledger_read)
        reader.start()
        assert at_preflight.wait(timeout=5)

        # While the reader sits between preflight and replay, the
        # store lock must be held by the reader: acquiring it from
        # this thread must fail until the read completes.  Pre-fix,
        # the reader held nothing in this window, so this acquire
        # succeeded AND the reader finished its replay while the lock
        # was held here — the exact append_batch interleave that
        # corrupted ledger replays nondeterministically.
        acquired = store._lock.acquire(timeout=1.0)
        try:
            past_preflight.set()
            if acquired:
                assert not read_done.wait(timeout=0.3), (
                    "task_ledger's default path completed its ledger"
                    " replay while another thread held the store lock:"
                    " the cache-aware replay must serialize with"
                    " append_batch transactions"
                )
        finally:
            if acquired:
                store._lock.release()
        assert read_done.wait(timeout=5)
        reader.join(timeout=5)
        assert outcome["tasks"] == ["task-1"]


@pytest.mark.parametrize(
    ("status", "selected", "excluded"),
    [("passed", "step.if_step", "step.else_step"),
     ("failed", "step.else_step", "step.if_step")],
)
def test_concurrent_else_waits_for_condition_and_only_creates_selected_task(
    tmp_path, status, selected, excluded
):
    source = f"""\
PROGRAM concurrent_else VERSION 1.0
INPUT
    V.status = "{status}"
step.test: DO define(goal = V.status) -> V.tests
IF V.tests == "passed"
  step.if_step: DO define(goal = V.tests) -> OUT.if_result
ELSE
  step.else_step: DO define(goal = V.tests) -> OUT.else_result
RETURN V.tests
"""
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(store, _worker()).execute(
            parse_program(source), "run", max_workers=2
        )
        assert result["status"] == "succeeded"
        ready = [
            event.instruction_id
            for event in store.events("run")
            if event.event_type is EventType.INVOCATION_READY
        ]
        assert ready == ["step.test", selected]
        texts = [task.text for task in store.task_ledger("run").tasks.values()]
        assert not any(text.startswith(excluded + ":") for text in texts)


def test_concurrent_else_waits_for_condition_producer_via_condition_refs(tmp_path):
    # The ELSE branch's arguments are literals, so only its inherited
    # condition refs create the dependency on the IF condition's
    # producer: without that edge the ELSE would dispatch in the first
    # frontier cycle, evaluate ``V.tests == "passed"`` before step.test
    # committed, and fail the run on a missing condition operand.
    source = """\
PROGRAM concurrent_else_dep VERSION 1.0
INPUT
    V.status = "failed"
step.test: DO define(goal = V.status) -> V.tests
IF V.tests == "passed"
  step.if_step: DO define(goal = "via-if") -> OUT.if_result
ELSE
  step.else_step: DO define(goal = "via-else") -> OUT.else_result
RETURN V.tests
"""
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(store, _worker()).execute(
            parse_program(source), "run", max_workers=2
        )
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"V.tests": "failed"}
        events = store.events("run")
        ready = [
            event.instruction_id
            for event in events
            if event.event_type is EventType.INVOCATION_READY
        ]
        assert ready == ["step.test", "step.else_step"]
        else_delta = next(
            event.payload["delta"] for event in events
            if event.event_type is EventType.SUCCEEDED
            and event.instruction_id == "step.else_step"
        )
        assert else_delta["add_nodes"][0]["id"] == "OUT.else_result"
        assert else_delta["add_nodes"][0]["value"] == "via-else"
        test_succeeded = next(
            event.seq for event in events
            if event.event_type is EventType.SUCCEEDED
            and event.invocation_id == "inv-1"
        )
        else_ready = next(
            event.seq for event in events
            if event.event_type is EventType.INVOCATION_READY
            and event.instruction_id == "step.else_step"
        )
        assert else_ready > test_succeeded


@pytest.mark.parametrize(
    ("status", "crash_idx", "selected", "excluded"),
    [("passed", 1, "step.if_step", "step.else_step"),
     ("failed", 2, "step.else_step", "step.if_step")],
)
def test_concurrent_else_crash_resume_does_not_dispatch_unselected_branch(
    tmp_path, status, crash_idx, selected, excluded
):
    source = f"""\
PROGRAM concurrent_else_crash VERSION 1.0
INPUT
    V.status = "{status}"
step.test: DO define(goal = V.status) -> V.tests
IF V.tests == "passed"
  step.if_step: DO define(goal = V.tests) -> OUT.if_result
ELSE
  step.else_step: DO define(goal = V.tests) -> OUT.else_result
RETURN V.tests
"""
    calls = []

    def define(goal):
        calls.append(goal)
        return goal

    def crash(idx):
        if idx == crash_idx:
            raise CrashInterrupt("after selected branch result")

    worker = DeterministicWorker({"define": define})
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        with pytest.raises(CrashInterrupt):
            SequentialCoordinator(store, worker).execute(
                program, "run", max_workers=2, crash_hook=crash
            )
        assert calls == [status, status]  # test + selected branch
        result = resume_run(store, worker, "run", program, max_workers=2)
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"V.tests": status}
        # at-least-once: only the in-flight selected branch re-ran
        assert calls == [status, status, status]
        events = store.events("run")
        ready = [
            event.instruction_id
            for event in events
            if event.event_type is EventType.INVOCATION_READY
        ]
        assert ready == ["step.test", selected]
        texts = [task.text for task in store.task_ledger("run").tasks.values()]
        assert not any(text.startswith(excluded + ":") for text in texts)


def test_resume_refuses_legacy_run_without_recorded_seal_unless_opted_in(tmp_path):
    # Backward compatibility: a run recorded before seal_digest joined
    # the RUN_STARTED payload (no recorded seal) still resumes through
    # the identity checks it does carry (program name and version).
    source = """\
PROGRAM legacy_seal VERSION 1.0
INPUT
    G.value = 7
step.one: DO define(goal = G.value) -> OUT.value
RETURN OUT.value
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        store.create_run("run", f"{program.name}@{program.version}")
        store.append(
            "run",
            EventType.RUN_STARTED,
            payload={"program": program.name, "version": program.version},
        )
        # Default: an unsealed legacy run is refused before appending
        # any events — its original program cannot be verified.
        before = len(store.events("run"))
        with pytest.raises(ValueError, match="allow_unsealed_legacy"):
            resume_run(store, _worker(), "run", program)
        assert len(store.events("run")) == before

        # Explicit opt-in names the unsafe behavior and resumes.
        result = resume_run(
            store, _worker(), "run", program, allow_unsealed_legacy=True
        )
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"OUT.value": 7}


def test_resume_refuses_run_without_run_started_by_default(tmp_path):
    source = """\
PROGRAM no_started VERSION 1.0
INPUT
    G.value = 7
step.one: DO define(goal = G.value) -> OUT.value
RETURN OUT.value
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        store.create_run("run", f"{program.name}@{program.version}")
        with pytest.raises(ValueError, match="allow_unsealed_legacy"):
            resume_run(store, _worker(), "run", program)
        result = resume_run(
            store, _worker(), "run", program, allow_unsealed_legacy=True
        )
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"OUT.value": 7}


def test_resume_verifies_canonical_seal_not_only_name_and_version(tmp_path):
    source = """\
PROGRAM sealed VERSION 1.0
INPUT
    G.value = 1
step.one: DO define(goal = G.value) -> OUT.value
RETURN OUT.value
"""
    program = parse_program(source)

    def crash(idx):
        raise CrashInterrupt("crash")

    with EventStore(tmp_path / "events.db") as store:
        with pytest.raises(CrashInterrupt):
            SequentialCoordinator(store, _worker()).execute(
                program, "run", crash_hook=crash
            )
        started = next(
            event for event in store.events("run")
            if event.event_type is EventType.RUN_STARTED
        )
        assert started.payload["seal_digest"]
        before = len(store.events("run"))
        changed = parse_program(source.replace("G.value = 1", "G.value = 2"))
        with pytest.raises(ValueError, match="seal digest"):
            resume_run(store, _worker(), "run", changed)
        # The unsafe legacy opt-in excuses a MISSING seal, never a
        # MISMATCHED one — the program identity is provably wrong.
        with pytest.raises(ValueError, match="seal digest"):
            resume_run(
                store, _worker(), "run", changed, allow_unsealed_legacy=True
            )
        assert len(store.events("run")) == before


def test_terminal_resume_returns_original_return_outputs(tmp_path):
    source = """\
PROGRAM outputs VERSION 1.0
INPUT
    G.value = 42
step.one: DO define(goal = G.value) -> OUT.value
RETURN OUT.value, G.value
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        original = SequentialCoordinator(store, _worker()).execute(program, "run")
        before = len(store.events("run"))
        resumed = resume_run(store, _worker(), "run", program)
        assert resumed["already_terminal"] is True
        assert resumed["outputs"] == original["outputs"] == {
            "OUT.value": 42,
            "G.value": 42,
        }
        assert len(store.events("run")) == before


def test_terminal_resume_reconstructs_outputs_for_legacy_single_return_run(
    tmp_path,
):
    # Backward compatibility: a terminal run recorded before outputs
    # joined the RUN_FINISHED payload still returns its original RETURN
    # outputs — replaying the committed deltas reproduces them exactly
    # for a single-RETURN program.
    source = """\
PROGRAM legacy_outputs VERSION 1.0
INPUT
    G.value = 42
step.one: DO define(goal = G.value) -> OUT.value
RETURN OUT.value
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        store.create_run("run", f"{program.name}@{program.version}")
        store.append(
            "run",
            EventType.RUN_STARTED,
            payload={"program": program.name, "version": program.version},
        )
        store.append(
            "run",
            EventType.SUCCEEDED,
            invocation_id="inv-1",
            payload={
                "delta": {"add_nodes": [{"id": "OUT.value", "value": 42}]}
            },
        )
        store.append(
            "run", EventType.RUN_FINISHED, payload={"status": "succeeded"}
        )
        # The crafted RUN_STARTED predates seal persistence, so the
        # legacy terminal replay needs the explicit unsafe opt-in.
        result = resume_run(
            store, _worker(), "run", program, allow_unsealed_legacy=True
        )
        assert result["already_terminal"] is True
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"OUT.value": 42}


def test_terminal_resume_does_not_reconstruct_ambiguous_legacy_outputs(
    tmp_path,
):
    # A legacy run with more than one possible terminal keeps the safe
    # empty outputs: the event history does not record which RETURN
    # fired, so replaying any particular one could fabricate outputs.
    source = """\
PROGRAM ambiguous_outputs VERSION 1.0
INPUT
    V.flag = 1
step.one: DO define(goal = V.flag) -> V.mid
IF V.mid == 2
    RETURN V.mid
RETURN V.mid
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        store.create_run("run", f"{program.name}@{program.version}")
        store.append(
            "run",
            EventType.RUN_STARTED,
            payload={"program": program.name, "version": program.version},
        )
        store.append(
            "run",
            EventType.SUCCEEDED,
            invocation_id="inv-1",
            payload={
                "delta": {"add_nodes": [{"id": "V.mid", "value": 1}]}
            },
        )
        store.append(
            "run", EventType.RUN_FINISHED, payload={"status": "succeeded"}
        )
        result = resume_run(
            store, _worker(), "run", program, allow_unsealed_legacy=True
        )
        assert result["already_terminal"] is True
        assert result["status"] == "succeeded"
        assert result["outputs"] == {}


def test_public_resume_observes_approval_after_blocked_run_finished(tmp_path):
    source = """\
PROGRAM approve_resume VERSION 1.0
INPUT
    G.value = 42
step.one: DO define(goal = G.value) -> G.goal
APPROVE PF.safety INTENT deploy to production
step.two: DO define(goal = G.goal) -> OUT.result
RETURN OUT.result
"""
    program = parse_program(source)
    with EventStore(tmp_path / "events.db") as store:
        coordinator = SequentialCoordinator(store, _worker())
        assert coordinator.execute(program, "run")["status"] == "blocked"
        store.append(
            "run",
            EventType.APPROVAL_GRANTED,
            invocation_id="inv-2",
            payload={
                "intent_digest": hashlib.sha256(
                    b"deploy to production"
                ).hexdigest()
            },
        )
        result = resume_run(store, _worker(), "run", program)
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"OUT.result": 42}
        assert store.events("run")[-1].payload["status"] == "succeeded"


def test_resume_without_grant_reblocks_and_denied_run_stays_terminal(tmp_path):
    program = parse_program("""\
PROGRAM approve_lifecycle VERSION 1.0
INPUT
    G.value = 42
step.one: DO define(goal = G.value) -> G.goal
APPROVE PF.safety INTENT deploy to production
step.two: DO define(goal = G.goal) -> OUT.result
RETURN OUT.result
""")
    with EventStore(tmp_path / "events.db") as store:
        coordinator = SequentialCoordinator(store, _worker())
        assert coordinator.execute(program, "run")["status"] == "blocked"

        # Resume without a grant decision: the run re-blocks (it is
        # still resumable, never already_terminal).
        reblocked = resume_run(store, _worker(), "run", program)
        assert reblocked["status"] == "blocked"
        assert reblocked.get("reason") == "approve"
        assert "already_terminal" not in reblocked

        # A denial is a true terminal: resume observes it once, then the
        # run stays terminal.
        store.append(
            "run",
            EventType.APPROVAL_DENIED,
            invocation_id="inv-2",
            payload={},
        )
        denied = resume_run(store, _worker(), "run", program)
        assert denied["status"] == "denied"
        assert "already_terminal" not in denied
        again = resume_run(store, _worker(), "run", program)
        assert again["already_terminal"] is True
        assert again["status"] == "denied"
        assert again["outputs"] == {}


LOOP_RESUME_PROGRAM = """\
PROGRAM loop_resume VERSION 1.0
INPUT
    V.result = "initial"
    U.issues = ["gap"]
LOOP refine
  ENTRY V.result == "initial"
  WHILE count(U.issues) > 0
  PROGRESS count(R.work) decreases
  MAX 2
  EXIT V.result == "passed"
  EXHAUSTED STOP unresolved(U.issues)
  step.work: DO define(goal = V.result) -> R.work
  step.update: DO echo(goal = V.result) -> V.result
RETURN V.result
"""


def test_loop_resume_reuses_committed_and_in_flight_body_work(tmp_path):
    calls = {"define": 0, "echo": 0}

    def define(goal):
        calls["define"] += 1
        return [1]

    def echo(goal):
        calls["echo"] += 1
        return "passed"

    class CrashOnSecondBodyResult:
        def __init__(self):
            self.calls = 0

        def __call__(self, idx):
            self.calls += 1
            if self.calls == 2:
                raise CrashInterrupt("after second body result")

    worker = DeterministicWorker({"define": define, "echo": echo})
    program = parse_program(LOOP_RESUME_PROGRAM)
    with EventStore(tmp_path / "events.db") as store:
        with pytest.raises(CrashInterrupt):
            SequentialCoordinator(store, worker).execute(
                program, "run", crash_hook=CrashOnSecondBodyResult()
            )
        result = resume_run(store, worker, "run", program)
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"V.result": "passed"}
        assert calls == {"define": 1, "echo": 2}
        events = store.events("run")
        assert len([
            event for event in events
            if event.event_type is EventType.LOOP_STARTED
        ]) == 1
        assert len([
            event for event in events
            if event.event_type is EventType.LOOP_ITERATION
        ]) == 1
        ready = [
            event.invocation_id for event in events
            if event.event_type is EventType.INVOCATION_READY
        ]
        assert ready == [
            "inv-1.iter1.step.work",
            "inv-1.iter1.step.update",
        ]
        assert all(
            task.status is TaskStatus.COMPLETED
            for task in store.task_ledger("run").tasks.values()
        )


SCATTER_ANY_PROGRAM = """\
PROGRAM scatter_resume VERSION 1.0
INPUT
    Q.parts = ["bad", "good", "spare"]
SCATTER X.part IN Q.parts MAX 3
  step.draft: DO define(goal = X.part) -> E.draft
GATHER draft AS E.pick USING any
RETURN E.pick
"""


def test_scatter_resume_does_not_redispatch_cancelled_loser(tmp_path):
    calls = []

    def crashing_define(goal):
        calls.append(goal)
        if goal == "bad":
            raise RuntimeError("bad candidate")
        if goal == "good":
            raise KeyboardInterrupt("crash with a cancelled earlier loser")
        return goal

    program = parse_program(SCATTER_ANY_PROGRAM)
    with EventStore(tmp_path / "events.db") as store:
        with pytest.raises(KeyboardInterrupt):
            SequentialCoordinator(
                store, DeterministicWorker({"define": crashing_define})
            ).execute(program, "run")
        resumed_calls = []

        def resumed_define(goal):
            resumed_calls.append(goal)
            return goal

        result = resume_run(
            store,
            DeterministicWorker({"define": resumed_define}),
            "run",
            program,
        )
        assert result["status"] == "succeeded"
        assert result["outputs"] == {"E.pick": "good"}
        assert calls == ["bad", "good"]
        assert resumed_calls == ["good"]


@pytest.mark.parametrize(
    ("budget", "usage", "error"),
    [
        (
            ExecutionBudget(max_total_tokens=2000),
            {"tokens": 2001},
            "token budget exceeded",
        ),
        (
            ExecutionBudget(max_total_cost=0.1),
            {"cost": 0.2},
            "cost budget exceeded",
        ),
    ],
)
def test_scatter_receipt_budget_exhaustion_is_run_fatal(
    tmp_path, budget, usage, error
):
    calls = []

    def define(goal):
        calls.append(goal)
        return {"goal": goal, "_receipt": {"usage": usage}}

    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store, DeterministicWorker({"define": define})
        ).execute(parse_program(SCATTER_ANY_PROGRAM), "run", budget=budget)
        assert result["status"] == "failed"
        assert result["error"] == f"candidate 1 failed: {error}"
        assert calls == ["bad"]


def test_scatter_pre_dispatch_token_exhaustion_does_not_call_worker(tmp_path):
    calls = []

    def define(goal):
        calls.append(goal)
        return goal

    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store, DeterministicWorker({"define": define})
        ).execute(
            parse_program(SCATTER_ANY_PROGRAM),
            "run",
            budget=ExecutionBudget(max_total_tokens=1999),
        )
        assert result["status"] == "failed"
        assert "insufficient_token_budget" in result["error"]
        assert calls == []


def test_first_selects_earliest_event_not_first_selector():
    program = parse_program("""\
PROGRAM first_order VERSION 1.0
INPUT
    G.value = "ok"
FIRST approval.granted OR approval.denied
    RETURN G.value
""")
    store = EventStore(":memory:")

    class InjectingCoordinator(SequentialCoordinator):
        def _drive_plan(self, *args, **kwargs):
            store.append("run", EventType.APPROVAL_DENIED, payload={"n": 1})
            store.append("run", EventType.APPROVAL_GRANTED, payload={"n": 2})
            return super()._drive_plan(*args, **kwargs)

    result = InjectingCoordinator(store, _worker()).execute(program, "run")
    assert result["status"] == "succeeded"
    matched = next(
        event for event in store.events("run")
        if event.event_type is EventType.FIRST_EVENT_MATCHED
    )
    assert matched.payload["selector"] == "approval.denied"
    assert matched.payload["selector_index"] == 1


def test_failed_invocation_cannot_later_succeed():
    with EventStore(":memory:") as store:
        store.create_run("run", "terminal@1.0")
        store.append("run", EventType.RUN_STARTED)
        store.append(
            "run", EventType.FAILED, invocation_id="inv-1",
            payload={"error": "failed"},
        )
        with pytest.raises(StateVersionConflict, match="FAILED terminal"):
            store.append(
                "run",
                EventType.SUCCEEDED,
                invocation_id="inv-1",
                expected_state_version=0,
                payload={"delta": StateDelta()},
            )
        assert not any(
            event.event_type is EventType.SUCCEEDED
            for event in store.events("run")
        )


@pytest.mark.parametrize(
    "field",
    [
        "global_deadline_seconds",
        "per_invocation_deadline_seconds",
        "max_total_cost",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_execution_budget_rejects_non_finite_numbers(field, value):
    with pytest.raises(ValueError, match=field):
        ExecutionBudget(**{field: value})


def test_empty_ranked_gather_fails_cleanly_without_calling_judge(tmp_path):
    source = """\
PROGRAM empty_ranked VERSION 1.0
INPUT
    Q.parts = []
SCATTER X.part IN Q.parts MAX 3
  step.draft: DO define(goal = X.part) -> E.draft
GATHER draft AS E.best USING ranked JUDGE step.judge
  step.judge: DO check(artifact = E.draft) -> V.score
RETURN E.best
"""
    judge_calls = []

    def check(artifact):
        judge_calls.append(artifact)
        return 1

    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store,
            DeterministicWorker({"define": lambda goal: goal, "check": check}),
        ).execute(parse_program(source), "run")
        assert result["status"] == "failed"
        assert "no candidates to rank" in result["error"]
        assert "Traceback" not in result["error"]
        assert judge_calls == []


# ---------------------------------------------------------------------------
# Audit HIGH1: the concurrent frontier must enforce the cost cap with the
# same terminal/error semantics as the sequential loop (no silent
# overspend success).
# ---------------------------------------------------------------------------

CONCURRENT_COST_FAN = """\
PROGRAM cost_fan VERSION 1.0
INPUT
    G.a = "a"
    G.b = "b"
    G.c = "c"
    G.d = "d"
step.a: DO define(goal = G.a) -> OUT.a
step.b: DO define(goal = G.b) -> OUT.b
step.c: DO define(goal = G.c) -> OUT.c
step.d: DO define(goal = G.d) -> OUT.d
RETURN OUT.a, OUT.b, OUT.c, OUT.d
"""


def _costly_worker(calls=None):
    """Worker whose receipts each report cost 50.0 (over the 10.0 cap)."""
    def define(goal):
        if calls is not None:
            calls.append(goal)
        return {"goal": goal, "_receipt": {"usage": {"tokens": 10, "cost": 50.0}}}
    return DeterministicWorker({"define": define})


def test_concurrent_receipt_cost_exhaustion_is_run_fatal(tmp_path):
    # Pre-fix, the concurrent frontier only accumulated tokens and checked
    # the token cap: receipt cost was dropped and gate.add_cost /
    # cost_cap_exceeded were never called, so this exact program silently
    # succeeded with max_workers=2 while failing with max_workers=1.
    calls: list[str] = []
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(store, _costly_worker(calls)).execute(
            parse_program(CONCURRENT_COST_FAN),
            "run",
            max_workers=2,
            budget=ExecutionBudget(max_total_cost=10.0),
        )
        assert result["status"] == "failed"
        assert result["error"] == "cost budget exceeded"
        assert "Traceback" not in result["error"]
        assert calls, "the frontier must have actually executed worker calls"
        assert store._run_allows_concurrent("run"), (
            "this regression must exercise the concurrent frontier,"
            " not the sequential loop"
        )
        events = list(store.events("run"))
        failed_events = [
            event for event in events if event.event_type is EventType.FAILED
        ]
        # The tripping invocation and any in-flight siblings it takes down
        # (issue #31) all fail with the same cost-cap reason.
        assert failed_events, "the trip must record a FAILED event"
        assert all(
            "cost budget exceeded" in event.payload["error"]
            for event in failed_events
        )
        finished = [
            event for event in events
            if event.event_type is EventType.RUN_FINISHED
        ]
        assert len(finished) == 1
        assert finished[0].payload["status"] == "failed"
        # Completed in-flight work is accounted and dropped uncommitted:
        # nothing commits after the terminal RUN_FINISHED (the failure
        # batch is the run's last write).
        for event in events:
            if event.event_type is EventType.SUCCEEDED:
                assert event.seq < finished[0].seq


def test_concurrent_cost_failure_matches_sequential_terminal_semantics(tmp_path):
    # Same program, worker and budget on both drive loops: the concurrent
    # frontier must fail with the identical status and error the
    # sequential loop produces.
    with EventStore(tmp_path / "seq.db") as seq_store:
        seq_result = SequentialCoordinator(seq_store, _costly_worker()).execute(
            parse_program(CONCURRENT_COST_FAN),
            "run",
            max_workers=1,
            budget=ExecutionBudget(max_total_cost=10.0),
        )
    with EventStore(tmp_path / "conc.db") as conc_store:
        conc_result = SequentialCoordinator(
            conc_store, _costly_worker()
        ).execute(
            parse_program(CONCURRENT_COST_FAN),
            "run",
            max_workers=2,
            budget=ExecutionBudget(max_total_cost=10.0),
        )
    assert seq_result["status"] == conc_result["status"] == "failed"
    assert (
        seq_result["error"] == conc_result["error"] == "cost budget exceeded"
    )


def test_concurrent_per_command_cost_ceiling_fails_run(tmp_path):
    # Issue #85 parity: the sequential loop fails a run with
    # "cost_exceeded" when a receipt's cost tops the command's registered
    # max_cost; the concurrent frontier must too.  estimate's registered
    # max_cost is 0.02 and the receipt reports 0.10.
    from tahoe.registry.registry import builtin_registry

    assert builtin_registry().resolve("estimate").budget.max_cost == 0.02

    def estimate_handler(**kwargs):
        return {
            "result": "ok",
            "_receipt": {
                "usage": {
                    "tokens": 100,
                    "input_tokens": 50,
                    "output_tokens": 50,
                    "cost": 0.10,
                },
            },
        }

    source = """\
PROGRAM concurrent_costceil VERSION 1.0
INPUT
    G.a = "a"
    G.b = "b"
step.one: DO estimate(evidence = G.a) -> OUT.one
step.two: DO estimate(evidence = G.b) -> OUT.two
RETURN OUT.one, OUT.two
"""
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store, DeterministicWorker({"estimate": estimate_handler})
        ).execute(parse_program(source), "run", max_workers=2)
        assert result["status"] == "failed"
        assert result["error"] == "cost_exceeded"
        assert "Traceback" not in result["error"]


# ---------------------------------------------------------------------------
# Audit HIGH2: FIRST/AWAIT/APPROVE programs with max_workers > 1 must use
# the supported sequential semantics, never a frontier crash relabeled as
# a failed run with a traceback summary.
# ---------------------------------------------------------------------------

FIRST_CONCURRENT = """\
PROGRAM first_concurrent VERSION 1.0
INPUT
    G.goal = "g"
step.prep: DO define(goal = G.goal) -> G.prepared
FIRST approval.granted OR approval.denied
    step.respond: DO define(text = G.prepared) -> OUT.result
    RETURN OUT.result
"""

AWAIT_CONCURRENT = """\
PROGRAM await_concurrent VERSION 1.0
INPUT
    G.goal = "done"
step.setup: DO define(goal = G.goal) -> G.prepared
AWAIT event.ready
step.finish: DO define(goal = G.prepared) -> OUT.result
RETURN OUT.result
"""

APPROVE_CONCURRENT = """\
PROGRAM approve_concurrent VERSION 1.0
INPUT
    G.goal = "g"
step.a: DO define(goal = G.goal) -> G.goal2
APPROVE PF.safety INTENT deploy
step.b: DO define(goal = G.goal2) -> OUT.result
RETURN OUT.result
"""


def test_first_program_with_max_workers_2_drives_sequential_and_executes_body(
    tmp_path,
):
    # Functional assertion: with an injected matching event, the FIRST
    # program executes its body and returns its result even though
    # max_workers=2 was requested — the sequential fallback keeps the
    # supported semantics (pre-fix this crashed on the frontier's
    # dependency DAG and was relabeled as a failed run with a traceback
    # summary).
    program = parse_program(FIRST_CONCURRENT)

    with EventStore(tmp_path / "events.db") as store:
        class InjectingCoordinator(SequentialCoordinator):
            def _drive_plan(self, *args, **kwargs):
                store.append(
                    "run", EventType.APPROVAL_GRANTED, payload={"injected": True}
                )
                return super()._drive_plan(*args, **kwargs)

        result = InjectingCoordinator(
            store, DeterministicWorker({"define": lambda **kwargs: "g"})
        ).execute(program, "run", max_workers=2)

        assert result["status"] == "succeeded"
        assert result["outputs"]["OUT.result"] == "g"
        assert "Traceback" not in str(result.get("error", ""))
        assert not store._run_allows_concurrent("run"), (
            "FIRST programs must keep the sequential plan loop semantics"
            " (width recorded only)"
        )
        matched = [
            event
            for event in store.events("run")
            if event.event_type is EventType.FIRST_EVENT_MATCHED
        ]
        assert len(matched) == 1
        assert matched[0].payload["selector"] == "approval.granted"


def test_await_program_with_max_workers_2_blocks_without_traceback(tmp_path):
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store, DeterministicWorker({"define": lambda goal: goal})
        ).execute(parse_program(AWAIT_CONCURRENT), "run", max_workers=2)

        assert result["status"] == "blocked"
        assert "Traceback" not in str(result.get("error", ""))
        assert not store._run_allows_concurrent("run"), (
            "AWAIT programs must keep the sequential plan loop semantics"
            " (width recorded only)"
        )
        suspended = [
            event
            for event in store.events("run")
            if event.event_type is EventType.AWAIT_SUSPENDED
        ]
        assert len(suspended) == 1


def test_approve_program_with_max_workers_2_blocks_without_traceback(tmp_path):
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(
            store, DeterministicWorker({"define": lambda goal: goal})
        ).execute(parse_program(APPROVE_CONCURRENT), "run", max_workers=2)

        assert result["status"] == "blocked"
        assert "Traceback" not in str(result.get("error", ""))
        assert not store._run_allows_concurrent("run"), (
            "APPROVE programs must keep the sequential plan loop semantics"
            " (width recorded only)"
        )
        requested = [
            event
            for event in store.events("run")
            if event.event_type is EventType.APPROVAL_REQUESTED
        ]
        assert len(requested) == 1


# ---------------------------------------------------------------------------
# Audit MEDIUM2: a multi-conditional program must attach the ELSE-branch
# terminal of the MATCHING conditional, never another conditional's.
# ---------------------------------------------------------------------------


def test_two_conditional_else_stop_attaches_the_matching_conditionals_terminal(
    tmp_path,
):
    # First conditional fires its IF branch (its ELSE STOP must not run);
    # second conditional is false, so ITS else STOP fires.  The removed
    # dead else-terminal scan iterated every conditional and attached the
    # first else terminal it found — the WRONG conditional's — if a
    # planner change ever routed such an entry there.
    source = """\
PROGRAM two_else_stops VERSION 1.0
INPUT
    V.pick = "second"
    V.first_else = "FIRST_ELSE"
    V.second_else = "SECOND_ELSE"
IF V.pick == "second"
  step.on_first: DO define(goal = V.pick) -> OUT.first_result
ELSE
  STOP failed(V.first_else)
IF V.pick == "third"
  step.on_second: DO define(goal = V.pick) -> OUT.second_result
ELSE
  STOP failed(V.second_else)
RETURN V.pick
"""
    with EventStore(tmp_path / "events.db") as store:
        result = SequentialCoordinator(store, _worker()).execute(
            parse_program(source), "run"
        )
        assert result["status"] == "failed"
        finished = [
            event
            for event in store.events("run")
            if event.event_type is EventType.RUN_FINISHED
        ]
        assert len(finished) == 1
        assert finished[0].payload["reason"] == "SECOND_ELSE"
