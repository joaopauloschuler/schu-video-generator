"""The spending ledger and the budget cap of generated video (DESIGN.md §113).

``videogen-ledger.jsonl`` in the project: append-only JSON lines, one per event —
``submit_intent`` (``intent_id, provider, model, request_hash, estimate_usd``) just before a
paid job is sent (written to disk first: DESIGN.md §113.10), ``submit`` (``job_id, provider,
model, request_hash, estimate_usd``, and ``intent_id`` when one was recorded) when it is
accepted, then one terminal event (``completed | failed | cancelled | expired``, with the
reported ``cost_usd`` from ``usage.cost`` or ``null``, ``is_byok``). ``intent_resolved``
(``intent_id, outcome, cost_usd``) closes an intent that has no ``submit`` line. Every line has
a UTC ``time``. Lines are never rewritten; an unreadable line is an error (the ledger is the
spending record: it is not guessed around). Events a reader does not know are ignored, so older
vidgen versions can still read this file (they do not count intents).

Spent (conservative): each job counts its reported cost; a job without one (still running,
timed out, or finished without ``usage``) counts its estimate. An intent with no known outcome
counts its estimate, because the provider may have accepted and charged it; once resolved it
counts what was charged (0 when nothing was). The mock provider keeps its own ledger
(``videogen-ledger.mock.jsonl``), so its pretend costs never mix with real spending.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.videogen import TERMINAL_STATUSES
from vidgen.videogen.models import money
from vidgen.videogen.redaction import redact_shared_addresses, redact_value


def utc_now() -> str:
    """The current UTC time as ``2026-11-07T14:02:03Z``."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class LedgerJob:
    """One job of the ledger: its submit line and, once known, its terminal status and cost."""

    job_id: str
    provider: str
    model: str
    request_hash: str
    estimate_usd: float | None
    submitted: str
    status: str | None = None
    cost_usd: float | None = None

    @property
    def charged(self) -> float:
        """What the job counts against the budget (reported cost, else its estimate)."""
        if self.cost_usd is not None:
            return self.cost_usd
        return self.estimate_usd or 0.0


#: How an intent ended: the submit was refused (no job), the owner says it was not charged, the
#: owner says it was charged (no job to fetch), or a ``submit`` line names its job.
REFUSED, NOT_CHARGED, CHARGED, BECAME_JOB = "refused", "not_charged", "charged", "job"


@dataclass(frozen=True)
class SubmitIntent:
    """A paid submit about to be sent (``outcome`` ``None``: nothing is known of what happened)."""

    intent_id: str
    provider: str
    model: str
    request_hash: str
    estimate_usd: float | None
    time: str
    outcome: str | None = None
    cost_usd: float | None = None
    job_id: str | None = None

    @property
    def unresolved(self) -> bool:
        """Whether the outcome is unknown: the provider may have accepted (and charged) it."""
        return self.outcome is None

    @property
    def charged(self) -> float:
        """What the intent counts against the budget (see the module docstring)."""
        if self.outcome is None:
            return self.estimate_usd or 0.0
        if self.outcome == CHARGED:
            return self.cost_usd if self.cost_usd is not None else self.estimate_usd or 0.0
        return 0.0

    def to_json(self) -> dict[str, Any]:
        """The intent as JSON (``generate ledger``, ``generate status``, ``generate plan``)."""
        return {
            "intent_id": self.intent_id, "model": self.model, "request_hash": self.request_hash, "estimate_usd": self.estimate_usd,
            "time": self.time, "outcome": self.outcome, "cost_usd": self.cost_usd, "job_id": self.job_id, "charged_usd": self.charged,
        }


class Ledger:
    """The ledger file of a project (created on the first paid job)."""

    def __init__(self, path: Path, *, clock: Callable[[], str] | None = None) -> None:
        self.path = path
        self._clock = clock if clock is not None else utc_now

    def append(self, event: str, **fields: Any) -> None:
        """Append one event line (with its time; a quick tunnel address loses its secret path)."""
        line = json.dumps({"event": event, "time": self._clock(), **redact_value(fields, redact_shared_addresses)}, ensure_ascii=True, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def events(self) -> list[dict[str, Any]]:
        """Every event, oldest first ([] without a ledger)."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        out = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or "event" not in event:
                    raise ValueError
            except ValueError:
                raise VidgenError(f"{self.path} line {number} is not a ledger event; fix or restore the file (it records what was spent)") from None
            out.append(event)
        return out

    def jobs(self) -> list[LedgerJob]:
        """The jobs, in submit order, with their terminal events applied."""
        jobs: dict[str, LedgerJob] = {}
        for e in self.events():
            job_id = str(e.get("job_id"))
            if e["event"] == "submit":
                jobs[job_id] = LedgerJob(
                    job_id, str(e.get("provider", "openrouter")), str(e.get("model", "")), str(e.get("request_hash", "")),
                    _number(e.get("estimate_usd")), str(e.get("time", "")),
                )
            elif e["event"] in TERMINAL_STATUSES and job_id in jobs:
                old = jobs[job_id]
                jobs[job_id] = LedgerJob(
                    old.job_id, old.provider, old.model, old.request_hash, old.estimate_usd, old.submitted,
                    status=str(e["event"]), cost_usd=_number(e.get("cost_usd")),
                )
        return list(jobs.values())

    def spent(self) -> float:
        """What the jobs and intents count against the budget (see the module docstring)."""
        return sum(j.charged for j in self.jobs()) + sum(i.charged for i in self.intents())

    def record_intent(self, provider: str, model: str, request_hash: str, estimate_usd: float | None) -> SubmitIntent:
        """Write a new ``submit_intent`` line to disk and return it; call it before sending a paid
        job. A :class:`VidgenError` (and nothing sent) when the ledger cannot be written."""
        intent_id = f"intent-{secrets.token_hex(4)}"
        try:
            self.append("submit_intent", intent_id=intent_id, provider=provider, model=model, request_hash=request_hash, estimate_usd=estimate_usd)
        except OSError as exc:
            raise VidgenError(f"cannot write the ledger {self.path} ({exc.strerror or exc}); nothing was sent or paid") from None
        return SubmitIntent(intent_id, provider, model, request_hash, estimate_usd, self._clock())

    def intents(self) -> list[SubmitIntent]:
        """Every recorded intent, oldest first, with what is known of its outcome."""
        intents: dict[str, SubmitIntent] = {}
        for e in self.events():
            intent_id = str(e.get("intent_id"))
            if e["event"] == "submit_intent":
                intents[intent_id] = SubmitIntent(
                    intent_id, str(e.get("provider", "openrouter")), str(e.get("model", "")), str(e.get("request_hash", "")),
                    _number(e.get("estimate_usd")), str(e.get("time", "")),
                )
            elif e["event"] == "submit" and intent_id in intents:
                intents[intent_id] = replace(intents[intent_id], outcome=BECAME_JOB, job_id=str(e.get("job_id")))
            elif e["event"] == "intent_resolved" and intent_id in intents:
                intents[intent_id] = replace(intents[intent_id], outcome=str(e.get("outcome")), cost_usd=_number(e.get("cost_usd")))
        return list(intents.values())

    def unresolved_intents(self, request_hash: str | None = None) -> list[SubmitIntent]:
        """The intents with no known outcome (of ``request_hash`` when given), oldest first."""
        return [i for i in self.intents() if i.unresolved and (request_hash is None or i.request_hash == request_hash)]

    def resolve_intent(self, intent_id: str, outcome: str, *, cost_usd: float | None = None, job_id: str | None = None) -> SubmitIntent:
        """Record what happened to an unresolved intent: ``outcome`` is :data:`REFUSED`,
        :data:`NOT_CHARGED` or :data:`CHARGED` (``cost_usd``: what was charged, default its
        estimate), or with ``job_id`` the job it became (a later run polls that job, free)."""
        known = {i.intent_id: i for i in self.intents()}
        intent = known.get(intent_id)
        if intent is None:
            names = ", ".join(i.intent_id for i in known.values() if i.unresolved) or "none"
            raise VidgenError(f"no intent {intent_id!r} in {self.path} (unresolved: {names})")
        if not intent.unresolved:
            raise VidgenError(f"intent {intent_id} is already resolved ({intent.outcome})")
        if job_id is not None:
            if any(j.job_id == job_id for j in self.jobs()):
                raise VidgenError(f"job {job_id} is already in the ledger; resolve the intent as --not-charged or --charged instead")
            self.append(
                "submit", job_id=job_id, provider=intent.provider, model=intent.model, request_hash=intent.request_hash,
                estimate_usd=intent.estimate_usd, intent_id=intent_id,
            )
            return replace(intent, outcome=BECAME_JOB, job_id=job_id)
        self.append("intent_resolved", intent_id=intent_id, outcome=outcome, cost_usd=cost_usd)
        return replace(intent, outcome=outcome, cost_usd=cost_usd)

    def open_job(self, request_hash: str, provider: str) -> LedgerJob | None:
        """The latest job of ``request_hash`` that has no terminal event yet (to poll again
        instead of paying twice)."""
        for job in reversed(self.jobs()):
            if job.request_hash == request_hash and job.provider == provider and job.status is None:
                return job
        return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def intent_text(intent: SubmitIntent) -> str:
    """One line naming an intent (``generate ledger``, ``generate status``, ``generate plan``)."""
    return f"{intent.time} {intent.intent_id} {intent.model}: no known outcome, counted at the estimate {money(intent.estimate_usd or 0.0)} (see `vidgen generate resolve`)"


def intent_refusal(intent: SubmitIntent) -> str:
    """Why a request with an unresolved intent is not paid for again, and what the owner can do."""
    which = f"vidgen generate resolve --intent {intent.intent_id}"
    return (
        f"an earlier paid submit of this request has no known outcome (intent {intent.intent_id}, {intent.time}, {intent.model}, estimated {money(intent.estimate_usd or 0.0)}): "
        "vidgen was stopped, or the answer was lost, after the request was sent, so OpenRouter may have accepted and charged it. "
        "vidgen does not pay for it again by itself. Look at your OpenRouter account's activity, then say what happened: "
        f"`{which} --not-charged` (nothing was charged: the next run pays for it); "
        f"`{which} --job JOB_ID` (the job exists: the next run polls and downloads it, free); "
        f"`{which} --charged [--cost USD]` (charged, but no job to fetch: the next run pays again, knowingly)"
    )


@dataclass(frozen=True)
class BudgetState:
    """The cap (``None``: none set, so nothing may be paid), what is spent and what is left."""

    cap_usd: float | None
    spent_usd: float

    @property
    def remaining_usd(self) -> float | None:
        """The cap minus what is spent (never below 0); ``None`` without a cap."""
        return None if self.cap_usd is None else max(0.0, self.cap_usd - self.spent_usd)

    def text(self) -> str:
        """``budget $2.000, spent $0.520, left $1.480`` (or ``no budget set``)."""
        if self.cap_usd is None:
            return f"no budget set (videogen.budget_usd), spent {money(self.spent_usd)}"
        assert self.remaining_usd is not None
        return f"budget {money(self.cap_usd)}, spent {money(self.spent_usd)}, left {money(self.remaining_usd)}"


def refusal(budget: BudgetState, estimate_usd: float | None, model: str) -> str | None:
    """Why a paid job of ``estimate_usd`` may not be submitted now, else ``None``."""
    if budget.cap_usd is None:
        return "paying needs a budget: set videogen: {budget_usd: 2.0} in video.yaml (a hard cap on what vidgen may spend)"
    if estimate_usd is None:
        return f"the price of this {model} clip is unknown, so it cannot be checked against the budget: choose a model whose price vidgen can estimate"
    remaining = budget.remaining_usd
    assert remaining is not None
    if estimate_usd > remaining + 1e-9:
        return f"the estimate {money(estimate_usd)} is more than the budget has left ({budget.text()})"
    return None
