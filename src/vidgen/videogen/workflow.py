"""``vidgen generate run | status | takes | pick`` (DESIGN.md §113.4).

:func:`run_shots` goes through the plan (:func:`vidgen.videogen.shots.plan_shots`) in video
order. Without ``pay`` it is a dry run (nothing sent, paid or written). With ``pay``:

- a budget is required (``videogen.budget_usd`` or ``budget_usd``; with both, the lower);
- a selected shot with problems refuses the whole run, and so does an estimate of the ready shots
  over what the budget has left, before anything is paid;
- each ready shot then goes through :func:`vidgen.videogen.run.generate_clip` (``pay=True``,
  ``duration=shot.priced_seconds``; the ledger keeps the running budget); blocked shots are
  skipped and named;
- every clip returned (paid now, cached, or an earlier job downloaded) becomes a take
  (:func:`vidgen.videogen.takes.add_take`: QA and contact sheet);
- the first failure stops the run (no automatic retry of a paid job; what was done is kept).

With ``videogen.host: quick_tunnel`` a shot with audio / video inputs gets its own quick tunnel
(one per shot, never one for the whole run: each tunnel shares only that shot's files and closes
when its job ends, so no file stays reachable while other shots are made); its progress lines go
to ``out``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen.models import Catalog, load_catalog, money
from vidgen.videogen.openrouter import OpenRouterVideoProvider
from vidgen.videogen.takes import Take, add_take, chosen_take, load_picks, takes_of

if TYPE_CHECKING:
    from vidgen.videogen.host import ShareOptions

#: The reminder printed wherever the film shows generated footage.
DISCLOSURE = (
    "publishing: this video shows AI-generated footage; mark it as altered or synthetic content where the platform asks "
    "(YouTube: 'Altered or synthetic content' when uploading; TikTok: the AI-generated content label)"
)


@dataclass
class ShotRun:
    """What happened to one shot: ``status`` is ``would_generate``, ``cached``, ``paid``,
    ``downloaded`` (an earlier job), ``blocked``, ``problems`` or ``failed``."""

    shot: str
    status: str
    model: str
    estimate_usd: float | None = None
    cost_usd: float | None = None
    take: Take | None = None
    new_take: bool = False
    message: str = ""

    def to_json(self, root: Path) -> dict[str, Any]:
        """The outcome as JSON."""
        take = self.take
        return {
            "shot": self.shot, "status": self.status, "model": self.model, "estimate_usd": self.estimate_usd, "cost_usd": self.cost_usd,
            "take": take.number if take else None, "take_path": take.path.relative_to(root).as_posix() if take else None,
            "new_take": self.new_take, "qa": take.qa if take else None, "contact_sheet": take.contact.relative_to(root).as_posix() if take else None,
            "message": self.message,
        }


@dataclass
class RunReport:
    """The outcome of :func:`run_shots`."""

    paid: bool
    shots: list[ShotRun] = field(default_factory=list)
    stopped: str | None = None

    @property
    def cost_usd(self) -> float:
        """What this run's jobs reported (US dollars)."""
        return sum(s.cost_usd or 0.0 for s in self.shots if s.status == "paid")


def run_shots(
    project: Project, *, pay: bool = False, budget_usd: float | None = None, shot_ids: Sequence[str] = (),
    out: Callable[[str], None] = print, provider: OpenRouterVideoProvider | None = None, catalog: Catalog | None = None,
    share: ShareOptions | None = None,
) -> RunReport:
    """Generate the project's shots (see the module docstring). ``share`` replaces how audio / video
    inputs are hosted (default: ``videogen.host``). Raises :class:`VidgenError` when a paid run is
    refused (nothing paid) or stopped by a failure (``details``: the outcomes)."""
    from vidgen.videogen.run import _cap, generate_clip
    from vidgen.videogen.shots import plan_shots

    root = project.root
    settings = project.config.videogen
    catalog = catalog if catalog is not None else load_catalog()
    if share is None and settings.host == "quick_tunnel":
        from vidgen.videogen.host import ShareOptions

        share = ShareOptions.from_config(settings, out=lambda line: out(f"  {line}"))
    plan = plan_shots(project, catalog=catalog, budget_usd=budget_usd, shot_ids=shot_ids)
    report = RunReport(paid=pay)
    if pay:
        if _cap(settings, budget_usd) is None:
            raise VidgenError("--pay needs a budget: set videogen: {budget_usd: 2.0} in video.yaml or pass --budget USD (a hard cap)")
        broken = [s for s in plan.shots if s.shot.problems or s.check.problems]
        if broken:
            text = "\n  ".join(f"{s.shot.id}: {p}" for s in broken for p in [*s.shot.problems, *s.check.problems])
            raise VidgenError(f"not paying: fix these shots first (nothing was paid):\n  {text}")
        ready = [s for s in plan.shots if not s.shot.blocked]
        due = sum(s.cost for s in ready)
        left = plan.budget.remaining_usd
        if left is not None and due > left + 1e-9:
            raise VidgenError(f"not paying: the ready shots are estimated at {money(due)}, more than the budget has left ({plan.budget.text()}); nothing was paid")
    fmt = project.config.format
    for item in plan.shots:
        shot = item.shot
        request = item.request
        model = shot.spec.model
        if shot.problems or item.check.problems or request is None:
            report.shots.append(ShotRun(shot.id, "problems", model, message="; ".join([*shot.problems, *item.check.problems])))
            out(f"shot {shot.id}: has problems (see `vidgen generate plan`): skipped")
            continue
        if shot.blocked:
            report.shots.append(ShotRun(shot.id, "blocked", model, item.cost, message="; ".join(shot.blocked)))
            out(f"shot {shot.id}: blocked ({'; '.join(shot.blocked)}): skipped")
            continue
        try:
            result = generate_clip(
                root, settings, request, pay=pay, provider=provider, catalog=catalog, budget_usd=budget_usd, duration=shot.priced_seconds,
                share=share,
            )
        except VidgenError as exc:
            report.shots.append(ShotRun(shot.id, "failed", model, item.cost, message=str(exc)))
            report.stopped = shot.id
            done = [s.to_json(root) for s in report.shots]
            raise VidgenError(f"shot {shot.id} failed, the run stopped (not retried; what was made is kept): {exc}", details={"shots": done}) from None
        if result.path is None:  # a dry run
            report.shots.append(ShotRun(shot.id, "would_generate", model, item.cost))
            out(f"shot {shot.id}: would generate ({model}, estimate {money(item.cost)})")
            continue
        status = "cached" if result.plan.cached else "paid" if result.job is not None and result.plan.previous_job is None else "downloaded"
        run = ShotRun(shot.id, status, model, item.estimate.cost if item.estimate else None, result.cost)
        if pay:
            run.take, run.new_take = add_take(
                root, shot.id, result.path, key=result.plan.key, model=model, provider=result.plan.provider,
                job_id=result.job.id if result.job else None, cost=result.cost, length=shot.length, width=fmt.width, height=fmt.height,
            )
            what = "new take" if run.new_take else "already take"
            cost = f", {money(result.cost)}" if result.cost is not None else ""
            out(f"shot {shot.id}: {status}{cost}: {what} {run.take.number} ({run.take.path.relative_to(root).as_posix()}, {run.take.qa.get('summary')})")
        else:
            out(f"shot {shot.id}: cached clip ({result.path.relative_to(root).as_posix()}); --pay keeps it as a take (free)")
        report.shots.append(run)
    if not pay:
        due = sum(s.estimate_usd or 0.0 for s in report.shots if s.status == "would_generate")
        out(f"dry run: nothing was sent or paid; `vidgen generate run --pay` would pay about {money(due)} ({plan.budget.text()})")
    else:
        from vidgen.videogen.ledger import BudgetState, Ledger
        from vidgen.videogen.run import ledger_path

        now = BudgetState(_cap(settings, budget_usd), Ledger(ledger_path(root, settings.provider)).spent())
        out(f"paid this run: {money(report.cost_usd)}; {now.text()} (`vidgen generate ledger` lists the jobs)")
    return report


def known_shots(project: Project, catalog: Catalog | None) -> list[str]:
    """Shot ids of the project (split parts included when the model list is at hand) and of the
    take folders."""
    from vidgen.videogen.shots import project_shots
    from vidgen.videogen.takes import TAKES_DIR

    ids = [s.id for s in project_shots(project, catalog)]
    folder = project.root / TAKES_DIR
    if folder.is_dir():
        ids += [p.name for p in sorted(folder.iterdir()) if p.is_dir() and p.name not in ids]
    return ids


def catalog_or_none() -> Catalog | None:
    """The video model list (cached; free), or ``None`` when it cannot be had (offline, no cache)."""
    try:
        return load_catalog()
    except VidgenError:
        return None


def status_lines(project: Project, catalog: Catalog | None) -> tuple[list[str], dict[str, Any]]:
    """``vidgen generate status``: per shot its takes and the one shown; the film's credit line
    and the disclosure reminder. Returns the text and its JSON."""
    from vidgen.videogen.compose import credit_line
    from vidgen.videogen.ledger import BudgetState, Ledger
    from vidgen.videogen.run import ledger_path
    from vidgen.videogen.shots import project_shots

    root = project.root
    picks = load_picks(root)
    lines: list[str] = []
    shots_json = []
    for shot in project_shots(project, catalog):
        takes = takes_of(root, shot.id)
        shown = chosen_take(root, shot.id) if shot.spec.place else None
        pick = picks.get(shot.id)
        how = "picked" if isinstance(pick, int) else "nothing picked: the newest without QA errors" if pick is None else "picked none"
        if not takes:
            state = "no takes yet" + ("; blocked: " + "; ".join(shot.blocked) if shot.blocked else "")
        elif shown is None:
            state = f"{len(takes)} take(s); vidgen's own picture is shown ({'place: false' if not shot.spec.place else how})"
        else:
            state = f"{len(takes)} take(s); shows take {shown.number} ({how}; {shown.qa.get('summary', 'not checked')})"
        lines.append(f"shot {shot.id} ({shot.spec.kind}, {shot.spec.model}, scene {shot.scene_id}): {state}")
        shots_json.append({"shot": shot.id, "kind": shot.spec.kind, "model": shot.spec.model, "takes": len(takes),
                           "shown": shown.number if shown else None, "picked": pick, "blocked": shot.blocked})
    if not shots_json:
        lines.append("no generated shots (add generated_shot: to a beat)")
    settings = project.config.videogen
    ledger = Ledger(ledger_path(root, settings.provider))
    budget = BudgetState(settings.budget_usd, ledger.spent())
    lines.append(budget.text())
    credit = credit_line(project)
    if credit:
        lines += [f"credits: {credit} (added to the description file <output>_chapters.txt)", DISCLOSURE]
    doc = {"shots": shots_json, "budget_usd": budget.cap_usd, "spent_usd": budget.spent_usd, "remaining_usd": budget.remaining_usd,
           "credit": credit or None, "disclosure": DISCLOSURE if credit else None}
    return lines, doc


__all__ = ["DISCLOSURE", "RunReport", "ShotRun", "catalog_or_none", "known_shots", "run_shots", "status_lines"]
