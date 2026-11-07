"""The spending ledger and the budget cap of generated video (DESIGN.md §113).

``videogen-ledger.jsonl`` in the project: append-only JSON lines, one per event —
``submit`` (``job_id, provider, model, request_hash, estimate_usd``) when a paid job is
accepted, then one terminal event (``completed | failed | cancelled | expired``, with the
reported ``cost_usd`` from ``usage.cost`` or ``null``, ``is_byok``). Every line has a UTC
``time``. Lines are never rewritten; an unreadable line is an error (the ledger is the
spending record: it is not guessed around).

Spent (conservative): each job counts its reported cost; a job without one (still running,
timed out, or finished without ``usage``) counts its estimate. The mock provider keeps its own
ledger (``videogen-ledger.mock.jsonl``), so its pretend costs never mix with real spending.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.videogen import TERMINAL_STATUSES
from vidgen.videogen.models import money


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


class Ledger:
    """The ledger file of a project (created on the first paid job)."""

    def __init__(self, path: Path, *, clock: Callable[[], str] | None = None) -> None:
        self.path = path
        self._clock = clock if clock is not None else utc_now

    def append(self, event: str, **fields: Any) -> None:
        """Append one event line (with its time)."""
        line = json.dumps({"event": event, "time": self._clock(), **fields}, ensure_ascii=True, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()

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
        """What the jobs count against the budget (see the module docstring)."""
        return sum(j.charged for j in self.jobs())

    def open_job(self, request_hash: str, provider: str) -> LedgerJob | None:
        """The latest job of ``request_hash`` that has no terminal event yet (to poll again
        instead of paying twice)."""
        for job in reversed(self.jobs()):
            if job.request_hash == request_hash and job.provider == provider and job.status is None:
                return job
        return None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


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
