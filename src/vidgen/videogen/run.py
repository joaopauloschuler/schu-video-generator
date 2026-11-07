"""One generated clip end to end: cache, checks, estimate, budget, then a dry run or a paid job
(DESIGN.md §113).

:func:`generate_clip` never pays unless ``pay=True`` and a budget is set (``videogen.budget_usd``
or ``budget_usd=``; with both, the lower). In order:

1. the cache: ``assets/generated_video/<hash>.mp4`` exists -> returned, nothing sent;
2. a job of the same request already in the ledger, still running or completed but not
   downloaded -> polled / downloaded again (free), never submitted twice;
3. the model's record (the public list; offline from its cache): unknown models and settings are
   refused with a did-you-mean, before anything is paid;
4. the estimate (:func:`vidgen.videogen.models.estimate`) against what the budget has left;
5. without ``pay``: the plan (a dry run; nothing is sent);
6. with ``pay``: submit (one attempt), ``submit`` line in the ledger, poll, the terminal line
   with ``usage.cost``, download, sidecar ``<hash>.json``.

The mock provider (``videogen.provider: mock``) keeps its own ledger,
``videogen-ledger.mock.jsonl``, so trying the flow never touches the real spending record.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.videogen import CLIPS_DIR, LEDGER_NAME, JobState, VideoRequest, canonical_request, request_hash
from vidgen.videogen.ledger import BudgetState, Ledger, LedgerJob, refusal, utc_now
from vidgen.videogen.models import Catalog, Estimate, RequestCheck, VideoModel, check_request, estimate, load_catalog, money
from vidgen.videogen.openrouter import OpenRouterVideoProvider, job_failure

if TYPE_CHECKING:
    from vidgen.config import VideogenConfig

log = logging.getLogger("vidgen.videogen")


def ledger_path(root: Path, provider: str) -> Path:
    """The project's ledger (the mock provider's own for ``mock``)."""
    return root / (LEDGER_NAME.replace(".jsonl", ".mock.jsonl") if provider == "mock" else LEDGER_NAME)


def clip_path(root: Path, key: str) -> Path:
    """Where the clip of cache key ``key`` is stored."""
    return root / CLIPS_DIR / f"{key}.mp4"


def get_provider(settings: VideogenConfig) -> OpenRouterVideoProvider:
    """The provider ``settings`` name (``openrouter`` or ``mock``)."""
    if settings.provider == "mock":
        from vidgen.videogen.mock import MockVideoProvider

        return MockVideoProvider(inline_media=settings.inline_media, poll_timeout=settings.poll_timeout)
    return OpenRouterVideoProvider(key_via_proxy=settings.key_via_proxy, inline_media=settings.inline_media, poll_timeout=settings.poll_timeout)


@dataclass
class ClipPlan:
    """What a run would do for one request (or did: see :class:`ClipResult`)."""

    request: VideoRequest
    key: str
    path: Path
    provider: str
    cached: bool = False
    previous_job: LedgerJob | None = None
    model: VideoModel | None = None
    check: RequestCheck = field(default_factory=RequestCheck)
    estimate: Estimate | None = None
    budget: BudgetState | None = None
    refusal: str | None = None

    def lines(self, root: Path | None = None) -> list[str]:
        """The dry-run text."""
        r = self.request
        shown = self.path.relative_to(root).as_posix() if root is not None and self.path.is_relative_to(root) else str(self.path)
        if self.cached:
            return [f"cached: {shown} ({r.model}; nothing to pay)"]
        what = [r.model, f"{r.duration} s" if r.duration else None, r.resolution or r.size, r.aspect_ratio]
        if r.frame_images:
            what.append(f"{len(r.frame_images)} frame image(s)")
        if r.references:
            what.append(f"{len(r.references)} reference(s)")
        lines = [f"would generate {shown}: {', '.join(w for w in what if w)} [{self.provider}]"]
        if self.previous_job is not None:
            lines.append(f"  job {self.previous_job.job_id} of this request is {self.previous_job.status or 'still open'}: --pay polls / downloads it (not paid again)")
        if self.estimate is not None:
            cost = money(self.estimate.cost) if self.estimate.cost is not None else "unknown"
            lines.append(f"  estimate: {cost} ({self.estimate.basis})")
        if self.budget is not None:
            lines.append(f"  {self.budget.text()}")
        lines += [f"  note: {n}" for n in self.check.notes]
        lines += [f"  problem: {p}" for p in self.check.problems]
        if self.refusal:
            lines.append(f"  refused: {self.refusal}")
        if r.prompt:
            lines.append(f"  prompt: {r.prompt}")
        return lines


@dataclass
class ClipResult:
    """The outcome: the plan, and for a paid run the job, its reported cost and the clip."""

    plan: ClipPlan
    path: Path | None = None
    job: JobState | None = None
    paid: bool = False

    @property
    def cost(self) -> float | None:
        """The reported cost (US dollars) of the job, if any."""
        return self.job.cost if self.job is not None else None


def _cap(settings: VideogenConfig, budget_usd: float | None) -> float | None:
    caps = [c for c in (settings.budget_usd, budget_usd) if c is not None]
    return min(caps) if caps else None


def plan_clip(
    root: Path, settings: VideogenConfig, request: VideoRequest, *, catalog: Catalog | None = None,
    budget_usd: float | None = None, duration: float | None = None, provider: str | None = None, again: bool = False,
) -> ClipPlan:
    """The plan of ``request`` (no paid request is made; the model list may be fetched, free).
    ``again``: ignore an earlier job of the same request (its output expired): a new paid job."""
    name = provider or settings.provider
    key = request_hash(request)
    plan = ClipPlan(request, key, clip_path(root, key), name)
    if plan.path.is_file():
        plan.cached = True
        return plan
    ledger = Ledger(ledger_path(root, name))
    jobs = [j for j in ledger.jobs() if j.request_hash == key]
    if jobs and jobs[-1].status in (None, "completed") and not again:
        plan.previous_job = jobs[-1]
    plan.budget = BudgetState(_cap(settings, budget_usd), ledger.spent())
    model = (catalog or load_catalog()).find(request.model)
    plan.model = model
    plan.check = check_request(request, model)
    plan.estimate = estimate(request, model, duration=duration)
    if plan.check.problems:
        plan.refusal = "the model does not take these settings (see the problems)"
    elif plan.previous_job is None:
        plan.refusal = refusal(plan.budget, plan.estimate.cost, request.model)
    return plan


def generate_clip(
    root: Path, settings: VideogenConfig, request: VideoRequest, *, pay: bool = False,
    provider: OpenRouterVideoProvider | None = None, catalog: Catalog | None = None,
    budget_usd: float | None = None, duration: float | None = None, again: bool = False,
) -> ClipResult:
    """Plan ``request`` and, with ``pay``, generate it (see the module docstring). Raises
    :class:`VidgenError` when a paid run is refused or the job fails."""
    chosen = provider if provider is not None else (get_provider(settings) if pay else None)
    name = chosen.name if chosen is not None else settings.provider
    plan = plan_clip(root, settings, request, catalog=catalog, budget_usd=budget_usd, duration=duration, provider=name, again=again)
    if plan.cached:
        return ClipResult(plan, plan.path)
    if not pay:
        return ClipResult(plan)
    assert chosen is not None
    if plan.check.problems:
        raise VidgenError("cannot generate with these settings:\n  " + "\n  ".join(plan.check.problems))
    ledger = Ledger(ledger_path(root, name))
    chosen.check_credentials()
    if plan.previous_job is not None:
        job = JobState(plan.previous_job.job_id, "pending" if plan.previous_job.status is None else "completed")
        if plan.previous_job.status is None:
            job = chosen.status(job.id)
        log.info("video job %s of this request was submitted earlier: polling it, not paying again", job.id)
        return _finish(root, ledger, chosen, plan, job, recorded=plan.previous_job.status is not None)
    if plan.refusal:
        raise VidgenError(f"not paying for {request.model}: {plan.refusal}")
    assert plan.estimate is not None
    job = chosen.submit(request, plan.check.drop)
    ledger.append(
        "submit", job_id=job.id, provider=name, model=request.model, request_hash=plan.key,
        estimate_usd=plan.estimate.cost,
    )
    return _finish(root, ledger, chosen, plan, job, recorded=False)


def _finish(root: Path, ledger: Ledger, provider: OpenRouterVideoProvider, plan: ClipPlan, job: JobState, *, recorded: bool) -> ClipResult:
    """Poll ``job`` to its end, record it, download and describe the clip."""
    if not job.done:
        job = provider.wait(job)
    if not recorded:
        ledger.append(job.status, job_id=job.id, cost_usd=job.cost, is_byok=job.is_byok)
    if job.status != "completed":
        raise job_failure(job)
    try:
        size = provider.download(job.id, plan.path)
    except VidgenError as exc:
        raise VidgenError(
            f"{exc}. Job {job.id} completed and was paid; a later run downloads it again while OpenRouter keeps it "
            "(once it has expired, only again=True submits a new paid job)"
        ) from None
    sidecar: dict[str, Any] = {
        "request": canonical_request(plan.request), "key": plan.key, "provider": provider.name, "job_id": job.id,
        "estimate_usd": plan.estimate.cost if plan.estimate is not None else None, "cost_usd": job.cost,
        "bytes": size, "time": utc_now(),
    }
    write_text_atomic(plan.path.with_suffix(".json"), json.dumps(sidecar, indent=1, ensure_ascii=True) + "\n")
    cost = money(job.cost) if job.cost is not None else "cost not reported"
    log.info("video job %s completed (%s): %s", job.id, cost, plan.path)
    return ClipResult(plan, plan.path, job, paid=True)
