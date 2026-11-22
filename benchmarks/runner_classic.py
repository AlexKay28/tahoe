"""Classic inference arm (A1) runner for the ablation study.

A thin OpenAI-compatible chat-completions loop with tool-schema support and
token tracking. No sealed program, no structured state.

Trial outcomes are captured truthfully so downstream consumers can tell
them apart instead of silently grading them as wrong answers:

- ``finish_reason`` preserves the API-reported finish reason of the last
  completion (``"stop"``, ``"length"``, ``"tool_calls"``, ...), so a
  length-capped trial stays distinguishable from a clean stop.
- ``empty_response`` marks a final assistant message with no text content;
  such runs get ``failure_class="empty_response"`` — the runner never
  relabels empty or capped outcomes as ``wrong_answer``.
- ``retries``/``retry_history`` record transient request failures that
  were retried before the run's final outcome.
- ``request_params`` snapshots the complete generation parameters sent in
  the first API request (model, messages, max_tokens, tools, extra_body).

The module also exposes the labeling policy shared by every classic-runner
benchmark (:func:`outcome_fields` and :func:`grading_outcome`): a
non-``"none"`` runner failure class is preserved verbatim and can never be
relabeled ``wrong_answer`` or graded into a pass, and a token-limit-capped
(``length``/``max_tokens``) answer that fails grading is labeled
``"truncated"`` — while a capped answer that the grader accepts keeps its
pass verdict with the truncation still visible in the metadata.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_MODEL = "GLM-5.3-Flash_alexkay28/."
ENV_API_BASE = "TAHOE_API_BASE"
ENV_API_KEY = "TAHOE_API_KEY"

FAILURE_NONE = "none"
FAILURE_API_ERROR = "api_error"
FAILURE_TIMEOUT = "timeout"
FAILURE_MAX_TURNS = "max_turns"
FAILURE_EMPTY_RESPONSE = "empty_response"

DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5

#: API finish reasons that mark a completion cut off by a token limit.
TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens", "max_output_tokens"})


def is_truncated(finish_reason: Any) -> bool:
    """True when ``finish_reason`` marks a token-limit-capped completion."""
    return str(finish_reason or "").strip().lower() in TRUNCATED_FINISH_REASONS


def outcome_fields(result: Any) -> dict[str, Any]:
    """Extract the truthful outcome fields from a ClassicResult-like object.

    Returns a JSON-safe dict with the fields every serialized benchmark
    trial must carry: ``finish_reason`` (API-reported finish reason of the
    last completion), ``truncated`` (token-limit cap flag derived from
    it), ``cap_exhausted`` (the same cap flag, named for what it means to
    reporting: the output token cap in ``request_params`` was exhausted),
    ``output_token_cap`` (the requested ``max_tokens`` when it is a
    positive integer, ``0`` otherwise), ``empty_response``, ``retries``,
    ``retry_history`` and the complete first-request ``request_params``.
    ``getattr`` defaults keep this working with pre-capture result shapes
    (e.g. older mocks in tests) and third-party duck-typed runners.
    """
    finish_reason = getattr(result, "finish_reason", "") or ""
    params = dict(getattr(result, "request_params", None) or {})
    max_tokens = params.get("max_tokens")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        max_tokens = 0
    return {
        "finish_reason": finish_reason,
        "truncated": is_truncated(finish_reason),
        "cap_exhausted": is_truncated(finish_reason),
        "output_token_cap": max_tokens,
        "empty_response": bool(getattr(result, "empty_response", False)),
        "retries": int(getattr(result, "retries", 0) or 0),
        "retry_history": list(getattr(result, "retry_history", None) or []),
        "request_params": params,
    }


def grading_outcome(
    runner_failure_class: Any,
    grader_passed: Any,
    finish_reason: Any = "",
) -> tuple[bool, str]:
    """Combine a runner outcome with a grading verdict, truthfully.

    Passed/failure semantics shared by every classic-runner benchmark:

    - A non-``"none"`` runner ``failure_class`` (``api_error``,
      ``timeout``, ``empty_response``, ``max_turns``, ...) is preserved
      verbatim — never relabeled ``wrong_answer`` — and the trial cannot
      pass: grading an infrastructure failure must never convert it into
      a pass. (A length-capped *empty* answer therefore stays
      ``empty_response``, the most specific truthful label.)
    - A truncated completion (``finish_reason`` of ``length`` /
      ``max_tokens`` / ...) that fails grading is labeled
      ``"truncated"``, not ordinary ``wrong_answer``. If the grader
      accepts a truncated answer, the pass verdict is kept and the
      truncation stays visible through ``finish_reason``/``truncated``.
    - Otherwise the graded outcome is ``"none"`` on a pass and
      ``"wrong_answer"`` on a fail.

    Returns ``(passed, failure_class)``.
    """
    failure = str(runner_failure_class or "").strip() or "none"
    if failure != "none":
        return False, failure
    if grader_passed:
        return True, "none"
    if is_truncated(finish_reason):
        return False, "truncated"
    return False, "wrong_answer"


@dataclass
class ClassicResult:
    """Outcome of a single classic-arm run.

    The first ten fields are the historical shape and keep their order;
    the remaining fields extend the record with truthful outcome capture.

    New fields:

    - ``finish_reason``: the API-reported finish reason of the last
      completion received (``""`` when no request ever succeeded). A
      length-capped answer keeps ``finish_reason="length"``.
    - ``empty_response``: True when the final assistant message carried
      no text content (whitespace counts as empty). Such runs are marked
      ``failure_class="empty_response"`` and are never relabeled as
      ``wrong_answer`` by this module.
    - ``retries``: number of failed request attempts, mirroring
      ``len(retry_history)``.
    - ``retry_history``: one ``{turn, attempt, failure_class, error}``
      record per failed request attempt (transient failures that were
      retried as well as the terminal one).
    - ``request_params``: the complete generation parameters of the first
      API request (model, messages, max_tokens, tools, extra_body), kept
      as a snapshot so later turns do not mutate it.
    """

    task_id: str
    arm: str = "classic"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wall_seconds: float = 0.0
    passed: bool = False
    failure_class: str = "none"
    turns: int = 0
    final_answer: str = ""
    finish_reason: str = ""
    empty_response: bool = False
    retries: int = 0
    retry_history: list[dict[str, Any]] = field(default_factory=list)
    request_params: dict[str, Any] = field(default_factory=dict)


def _parse_tool_arguments(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _is_timeout(exc: BaseException, openai_module: Any) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    timeout_type = getattr(openai_module, "APITimeoutError", None)
    return isinstance(timeout_type, type) and isinstance(exc, timeout_type)


def run(
    task_id: str,
    task_prompt: str,
    model: str = DEFAULT_MODEL,
    api_base: str = "",
    api_key: str = "",
    max_turns: int = 10,
    max_tokens: int = 4096,
    timeout_seconds: int = 120,
    tools: list[dict] | None = None,
    tool_implementations: dict[str, Callable[..., Any]] | None = None,
    system_prompt: str = "",
    extra_body: dict[str, Any] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> ClassicResult:
    """Run one task through a plain chat-completions loop and return a ClassicResult.

    Each request is retried up to ``max_retries`` times on transient API
    failures (``max_retries=0`` restores the historical single-attempt
    behavior); every failed attempt is recorded in the result's
    ``retry_history``. The result preserves the API ``finish_reason`` of
    the last completion, flags an empty final answer as
    ``failure_class="empty_response"`` (never as a graded wrong answer),
    and snapshots the complete first-request generation parameters in
    ``request_params``.
    """
    resolved_key = api_key or os.environ.get(ENV_API_KEY, "")
    if not resolved_key:
        raise ValueError(
            "no API key available: pass api_key or set the TAHOE_API_KEY environment variable"
        )
    resolved_base = api_base or os.environ.get(ENV_API_BASE, "")

    import openai

    client_kwargs: dict[str, Any] = {"api_key": "dummy", "timeout": timeout_seconds}
    if resolved_base:
        client_kwargs["base_url"] = resolved_base
    client_kwargs["default_headers"] = {
        "Authorization": f"OAuth {resolved_key}",
        **({"Ya-Pool": os.environ["TAHOE_API_POOL"]} if os.environ.get("TAHOE_API_POOL") else {}),
    }
    client = openai.OpenAI(**client_kwargs)

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task_prompt})
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        request_kwargs["tools"] = tools
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    implementations = tool_implementations or {}
    # Snapshot of the complete generation parameters sent in the first
    # request: the live ``messages`` list keeps growing, so copy it here.
    request_params: dict[str, Any] = {
        **request_kwargs,
        "messages": list(request_kwargs["messages"]),
    }
    input_tokens = 0
    output_tokens = 0
    turns = 0
    started = time.monotonic()
    deadline = started + max(timeout_seconds, 0)
    failure_class = FAILURE_NONE
    final_answer = ""
    finish_reason = ""
    empty_response = False
    retry_history: list[dict[str, Any]] = []

    def finish(passed: bool) -> ClassicResult:
        return ClassicResult(
            task_id=task_id,
            arm="classic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            wall_seconds=time.monotonic() - started,
            passed=passed,
            failure_class=failure_class,
            turns=turns,
            final_answer=final_answer,
            finish_reason=finish_reason,
            empty_response=empty_response,
            retries=len(retry_history),
            retry_history=list(retry_history),
            request_params=request_params,
        )

    while turns < max_turns:
        if time.monotonic() >= deadline:
            failure_class = FAILURE_TIMEOUT
            return finish(False)
        attempt = 0
        while True:
            try:
                response = client.chat.completions.create(**request_kwargs)
                if attempt:
                    # A transient failure was retried successfully; the
                    # run's terminal failure class is back to none.
                    failure_class = FAILURE_NONE
                break
            except Exception as exc:
                attempt += 1
                exc_class = (
                    FAILURE_TIMEOUT if _is_timeout(exc, openai) else FAILURE_API_ERROR
                )
                failure_class = exc_class
                retry_history.append(
                    {
                        "turn": turns,
                        "attempt": attempt,
                        "failure_class": exc_class,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if attempt > max_retries:
                    return finish(False)
                now = time.monotonic()
                if now >= deadline:
                    failure_class = FAILURE_TIMEOUT
                    return finish(False)
                if retry_backoff_seconds > 0:
                    backoff = retry_backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(min(backoff, max(deadline - now, 0.0)))
        turns += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        finish_reason = getattr(response.choices[0], "finish_reason", None) or ""
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(message, "content", None) or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": getattr(call.function, "arguments", "") or "",
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                name = call.function.name
                arguments = _parse_tool_arguments(getattr(call.function, "arguments", None))
                implementation = implementations.get(name)
                if implementation is None:
                    output = f"error: no implementation registered for tool {name!r}"
                else:
                    try:
                        output = implementation(**arguments)
                    except Exception as exc:
                        output = f"error: tool {name!r} failed: {exc}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": name,
                        "content": str(output),
                    }
                )
            continue
        final_answer = getattr(message, "content", None) or ""
        if not final_answer.strip():
            # Truthful empty-response capture: the model produced no
            # answer text (e.g. all tokens went to reasoning under a
            # length cap). Mark it explicitly instead of letting an empty
            # string be graded as a wrong answer downstream; the API's
            # finish_reason (e.g. "length" vs "stop") stays preserved.
            empty_response = True
            failure_class = FAILURE_EMPTY_RESPONSE
            return finish(False)
        return finish(True)

    failure_class = FAILURE_MAX_TURNS
    return finish(False)
