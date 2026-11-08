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
6. with ``pay``: a ``submit_intent`` line on disk, the submit (one attempt; local pictures as
   their smaller copies, :mod:`vidgen.videogen.pictures`), ``submit`` line in the ledger, poll,
   the terminal line with ``usage.cost``, download, sidecar ``<hash>.json``. A request with an
   intent of no known outcome is refused until the owner runs ``vidgen generate resolve``
   (:func:`vidgen.videogen.ledger.intent_refusal`): it is never paid again by itself.

Local audio / video inputs (a shot's voice, its guide render) are shared through a Cloudflare
quick tunnel (:mod:`vidgen.videogen.host`, ``videogen.host: quick_tunnel`` or ``share=``): one
tunnel for this one job, opened (and checked through its public address) after every other check
and before the submit, which is refused unless the tunnel is still open with room for the wait
(:meth:`~vidgen.videogen.host.QuickTunnelHost.ensure_time_for_job`). It closes as soon as the job
reaches a final state (completed, failed, ...), before the download, or at the maximum lifetime
(a provider may fetch again after queueing, so a finished fetch does not close it); also on an
error or Ctrl+C. A job resumed from the ledger is only polled: no tunnel is opened again.
Without a host such inputs stop the submit with a clear error. Whatever the provider says with
the shared address in it is redacted before it leaves this module (:mod:`vidgen.videogen.redaction`).

The mock provider (``videogen.provider: mock``) keeps its own ledger,
``videogen-ledger.mock.jsonl``, so trying the flow never touches the real spending record, and
never opens a tunnel: its local audio / video inputs get fake addresses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.videogen import CLIPS_DIR, LEDGER_NAME, MOCK_PROVIDER, JobState, VideoRequest, canonical_request, request_hash
from vidgen.videogen.ledger import BudgetState, Ledger, LedgerJob, SubmitIntent, intent_refusal, refusal, utc_now
from vidgen.videogen.models import Catalog, Estimate, RequestCheck, VideoModel, check_request, estimate, load_catalog, money
from vidgen.videogen.openrouter import OpenRouterVideoProvider, SubmitRefused, job_failure
from vidgen.videogen.pictures import sendable_request
from vidgen.videogen.redaction import redact_value

if TYPE_CHECKING:
    from vidgen.config import VideogenConfig
    from vidgen.videogen.host import QuickTunnelHost, ShareOptions

log = logging.getLogger("vidgen.videogen")


def ledger_path(root: Path, provider: str) -> Path:
    """The project's ledger (the mock provider's own for ``mock``)."""
    return root / (LEDGER_NAME.replace(".jsonl", ".mock.jsonl") if provider == MOCK_PROVIDER else LEDGER_NAME)


def clip_path(root: Path, key: str) -> Path:
    """Where the clip of cache key ``key`` is stored."""
    return root / CLIPS_DIR / f"{key}.mp4"


def get_provider(settings: VideogenConfig) -> OpenRouterVideoProvider:
    """The provider ``settings`` name (``openrouter`` or ``mock``)."""
    if settings.provider == MOCK_PROVIDER:
        from vidgen.videogen.mock import MockVideoProvider

        return MockVideoProvider(poll_timeout=settings.poll_timeout)
    return OpenRouterVideoProvider(key_via_proxy=settings.key_via_proxy, poll_timeout=settings.poll_timeout)


@dataclass
class ClipPlan:
    """What a run would do for one request (or did: see :class:`ClipResult`)."""

    request: VideoRequest
    key: str
    path: Path
    provider: str
    cached: bool = False
    previous_job: LedgerJob | None = None
    unresolved_intent: SubmitIntent | None = None
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


def hosted_inputs(request: VideoRequest) -> list[Path]:
    """The local audio / video files of ``request`` (what a host must share; pictures go inline)."""
    return [m.path for m in (*request.frame_images, *request.references) if m.kind != "image" and m.url is None and m.path is not None]


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
    unresolved = ledger.unresolved_intents(key) if plan.previous_job is None else []
    plan.unresolved_intent = unresolved[-1] if unresolved else None
    plan.budget = BudgetState(_cap(settings, budget_usd), ledger.spent())
    model = (catalog or load_catalog()).find(request.model)
    plan.model = model
    plan.check = check_request(request, model)
    plan.estimate = estimate(request, model, duration=duration)
    if plan.check.problems:
        plan.refusal = "the model does not take these settings (see the problems)"
    elif plan.unresolved_intent is not None:
        plan.refusal = intent_refusal(plan.unresolved_intent)
    elif plan.previous_job is None:
        plan.refusal = refusal(plan.budget, plan.estimate.cost, request.model)
    return plan


def generate_clip(
    root: Path, settings: VideogenConfig, request: VideoRequest, *, pay: bool = False,
    provider: OpenRouterVideoProvider | None = None, catalog: Catalog | None = None,
    budget_usd: float | None = None, duration: float | None = None, again: bool = False, share: ShareOptions | None = None,
) -> ClipResult:
    """Plan ``request`` and, with ``pay``, generate it (see the module docstring). ``share``: how
    local audio / video inputs are hosted (default: ``videogen.host``). Raises
    :class:`VidgenError` when a paid run is refused or the job fails. The mock provider ignores
    ``share`` and ``videogen.host``: it never shares anything."""
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
    sendable = sendable_request(request, root)
    local = hosted_inputs(sendable)
    if share is None and local and settings.host == "quick_tunnel":
        from vidgen.videogen.host import ShareOptions

        share = ShareOptions.from_config(settings)
    if not local or share is None or chosen.name == MOCK_PROVIDER:
        job = _submit(ledger, chosen, plan, sendable)
        return _finish(root, ledger, chosen, plan, job, recorded=False)
    problem = share.settings.lifetime_problem(chosen.poll_timeout)
    if problem:
        raise VidgenError(f"not paying for {request.model}: {problem}")
    host = share.host(local, root, ledger)
    with host:   # closed when the block ends: the job reached a final state (or an error / Ctrl+C)
        previous = chosen.uploader
        chosen.uploader = host.url_of
        try:
            host.ensure_time_for_job(chosen.poll_timeout)
            job = _submit(ledger, chosen, plan, sendable)
            job = chosen.wait(job)
        except VidgenError as exc:   # a provider's error may quote a URL: never pass the secret on
            raise _without_secret(exc, host) from None
        finally:
            chosen.uploader = previous
    try:
        return _finish(root, ledger, chosen, plan, job, recorded=False)
    except VidgenError as exc:   # a failed job's error, raised after the tunnel closed
        raise _without_secret(exc, host) from None


def _without_secret(exc: VidgenError, host: QuickTunnelHost) -> VidgenError:
    """``exc`` with the host's shared addresses taken out of its message and details."""
    return VidgenError(host.redact(str(exc)), details=redact_value(exc.details, host.redact))


def _submit(ledger: Ledger, provider: OpenRouterVideoProvider, plan: ClipPlan, request: VideoRequest) -> JobState:
    """Submit the paid job and record it: the intent goes to disk before the POST, the ``submit``
    line (which resolves it) after. Any other failure than a refused submit leaves the intent
    open, so a later run cannot pay for this request again by itself."""
    assert plan.estimate is not None
    estimate_usd = plan.estimate.cost
    intent: SubmitIntent | None = None

    def record_intent() -> None:
        nonlocal intent
        intent = ledger.record_intent(provider.name, plan.request.model, plan.key, estimate_usd)

    try:
        job = provider.submit(request, plan.check.drop, on_sending=record_intent)
    except SubmitRefused:
        assert intent is not None
        ledger.resolve_intent(intent.intent_id, "refused")
        raise
    except VidgenError as exc:
        if intent is None:   # stopped before anything was sent (a request too large, say)
            raise
        raise VidgenError(f"{exc}\n{intent_refusal(intent)}", details=exc.details) from None
    assert intent is not None
    ledger.append(
        "submit", job_id=job.id, provider=provider.name, model=plan.request.model, request_hash=plan.key,
        estimate_usd=estimate_usd, intent_id=intent.intent_id,
    )
    return job


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
