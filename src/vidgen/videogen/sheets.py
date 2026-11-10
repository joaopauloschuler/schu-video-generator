"""Reference sheets for generated video shots (DESIGN.md §113.3): pictures of each character
(``characters[].reference_sheet``) and style frames (``style_sheet``), made by the project's
image provider (``imagegen:``) and stored in ``assets/sheets/``.

Each picture is an :class:`~vidgen.imagegen.ImageRequest` (the same prompt, style and cache key
rules as ``generate:`` pictures) stored as ``assets/sheets/<owner>_<label>_<key>.png`` with a
``.json`` sidecar, so a changed prompt is a new file. A sheet is used by video jobs only once its
``approved: true`` is set, and an approved sheet is never made again (its pictures are what was
approved): with a changed prompt it is blocked until ``approved: false``.

Making pictures costs money: :func:`run_sheets` is a dry run (pictures, estimated price) unless
``pay``; paying needs ``videogen.budget_usd`` (checked against the estimate before paying) and
records each picture in the video ledger (``image-<key>`` jobs, with the cost OpenRouter reported
in ``usage.cost`` or, without one, counted at the estimate: ``cost_source``), so the cap covers
sheets and clips together.
"""

from __future__ import annotations

import dataclasses
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen.config import ReferenceSheet, StyleSheet
from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic, write_text_atomic
from vidgen.imagegen import GenerateImage, ImageProvider, ImageRequest, get_image_provider, image_request, style_words
from vidgen.imagegen.run import ImagegenPlan, cost_words, price_plan, sidecar_document
from vidgen.project import Project
from vidgen.videogen import MOCK_PROVIDER, did_you_mean
from vidgen.videogen.ledger import BudgetState, Ledger, refusal
from vidgen.videogen.models import money

#: Where sheet pictures are stored, relative to the project.
SHEETS_DIR = Path("assets") / "sheets"
#: The owner name of the style sheet's pictures.
STYLE = "style"
#: Words of each view in a character picture's prompt (strict: models drift to three-quarter).
VIEW_WORDS: dict[str, str] = {
    "front": "front view: facing the camera squarely, body and face straight on",
    "three_quarter": "three-quarter view: body and face turned 45 degrees to the left, both eyes visible",
    "side": "side view: strict 90-degree profile, facing left, only one eye visible",
    "back": "back view: seen straight from behind, the face not visible",
}
#: How every character picture is set up: a clean model-sheet picture, one figure, nothing else.
CHARACTER_SETUP = "Character model sheet picture of one person"
#: The backdrop of every character picture.
BACKDROP = "standing on a plain seamless light grey studio backdrop, even soft studio light, nothing else in the picture"
#: How a character's description is introduced: who the person is, so a job is not drawn as props.
WHO = "Who the person is (draw only the person and their clothes): "
#: Always excluded from character pictures (added as "Avoid: ...").
CHARACTER_EXCLUDE = (
    "text, letters, words, numbers, signs, signage, logos, labels, captions, watermarks, props, objects in the hands, "
    "furniture, counters, booths, lamps, scenery, buildings, other people, cropped head or feet"
)
#: Always excluded from style frames.
FRAME_EXCLUDE = "text, letters, words, numbers, signs, signage, logos, labels, captions, watermarks"
#: How the palette is phrased: colours, never things to draw ("warm lamp orange" drew lamps).
PALETTE_WORDS = "colour palette: {colours} (colours only, not objects{where})"
#: What the palette colours in a character picture.
PALETTE_WHERE = ": the colours of the clothing and the lighting tint"
#: Look words that suit a film shot but fight a studio reference (left out of character pictures):
#: lens, depth of field, camera movement, and scene lighting ("soft overcast morning light").
_SHOT_ONLY = re.compile(
    r"\b(\d+\s*mm|lens|depth of field|bokeh|hand-?held|focal|aperture|camera|close-?up|wide[- ]angle|dolly|tracking|telephoto)\b"
    r"|\b(light|lighting|sunlight|daylight|moonlight|glow)$",
    re.IGNORECASE,
)
DEFAULT_FRAME = "a representative still of the film"


@dataclass(frozen=True)
class SheetPicture:
    """One picture of a sheet: its ``label`` (a view, an expression, ``frame1``...) and request."""

    label: str
    request: ImageRequest


@dataclass(frozen=True)
class Sheet:
    """A character's reference sheet or the style sheet (``owner`` ``style``): where it is
    written in the config, whether it is approved and its pictures."""

    owner: str
    location: str
    approved: bool
    pictures: tuple[SheetPicture, ...]
    notes: str = ""

    @property
    def missing(self) -> list[SheetPicture]:
        """Pictures not made yet."""
        return [p for p in self.pictures if not p.request.exists]

    @property
    def ready(self) -> bool:
        """Approved and every picture made: video jobs may use it."""
        return self.approved and not self.missing

    @property
    def paths(self) -> list[Path]:
        """The pictures' files (made or not), in order."""
        return [p.request.path for p in self.pictures]

    def status(self) -> str:
        """``approved``, ``made, not approved yet``, ``2 of 3 pictures not made yet``..."""
        missing = len(self.missing)
        if not self.pictures:
            return "no pictures (frames: 0)"
        if missing and self.approved:
            return f"approved, but {missing} of {len(self.pictures)} pictures are missing (the prompt changed?): set approved: false and make them again"
        if missing:
            return f"{missing} of {len(self.pictures)} pictures not made yet (`vidgen generate sheets --pay`)"
        return "approved" if self.approved else f"made, not approved yet: look at them, then set {self.location}.approved: true"

    def problem(self) -> str | None:
        """Why video jobs may not use the sheet yet (``None``: ready)."""
        return None if self.ready else f"{self.owner} sheet: {self.status()}"


def _request(project: Project, owner: str, label: str, prompt: str, style: str, negative: str, aspect: str, seed: int | None) -> ImageRequest:
    """The picture's request, stored under ``assets/sheets/`` instead of ``assets/generated/``."""
    generate = GenerateImage(prompt=prompt, negative=negative, style=style or "none", aspect=aspect, seed=seed)  # type: ignore[arg-type]
    request = image_request(project, generate)
    folder = project.root / SHEETS_DIR
    stem = f"{owner}_{label}_{request.key}"
    return dataclasses.replace(request, path=folder / f"{stem}.png", sidecar=folder / f"{stem}.json")


def _clean(text: str | None) -> str:
    return " ".join((text or "").split()).rstrip(".")


def _look_words(project: Project, *, reference: bool) -> str:
    """The style words of sheet pictures: ``imagegen.style`` and the style sheet's, the palette
    phrased as colours only. ``reference`` (character pictures): only the palette, the era and the
    rendering words (realism, film grain); lens, camera and scene-lighting words are left out."""
    cfg = project.config
    sheet = cfg.style_sheet
    parts: list[str] = []
    if sheet is not None:
        colours = ", ".join(sheet.palette) if isinstance(sheet.palette, list) else _clean(sheet.palette)
        if colours:
            parts.append(PALETTE_WORDS.format(colours=colours, where=PALETTE_WHERE if reference else ""))
        if sheet.era:
            parts.append(f"era: {_clean(sheet.era)}")
    rest = [style_words(cfg.imagegen.style)]
    if sheet is not None:
        rest += [sheet.notes or ""] if reference else [sheet.lens or "", sheet.notes or ""]
    for words in rest:
        clauses = [c.strip() for c in _clean(words).split(",") if c.strip()]
        if reference:
            clauses = [c for c in clauses if not _SHOT_ONLY.search(c)]
        if clauses:
            parts.append(", ".join(clauses))
    return "; ".join(dict.fromkeys(parts))


def character_sheet(project: Project, name: str) -> Sheet | None:
    """The reference sheet of character ``name`` (``None``: it has none)."""
    for i, entry in enumerate(project.config.characters):
        if entry.name == name and entry.reference_sheet is not None:
            return _character_sheet(project, i, name, entry.reference_sheet)
    return None


def _character_sheet(project: Project, index: int, name: str, sheet: ReferenceSheet) -> Sheet:
    look = _look_words(project, reference=True)
    who = f"{WHO}{_clean(sheet.prompt)}. No props"
    pictures = []
    for view in sheet.views:
        prompt = (
            f"{CHARACTER_SETUP}: full body from head to toe, whole figure in frame, {VIEW_WORDS[view]}, neutral expression, "
            f"arms relaxed at the sides, empty hands, {BACKDROP}. {who}"
        )
        pictures.append(SheetPicture(view, _request(project, name, view, prompt, look, CHARACTER_EXCLUDE, "portrait", sheet.seed)))
    for expression in sheet.expressions:
        label = "_".join(expression.lower().split())
        prompt = f"{CHARACTER_SETUP}: head and shoulders, {VIEW_WORDS['front']}, {expression} expression, {BACKDROP}. {who}"
        pictures.append(SheetPicture(label, _request(project, name, label, prompt, look, CHARACTER_EXCLUDE, "portrait", sheet.seed)))
    notes = "; ".join(_clean(p) for p in (sheet.prompt, sheet.notes or "") if p)
    return Sheet(name, f"characters[{index}].reference_sheet", sheet.approved, tuple(pictures), notes)


def style_sheet(project: Project) -> Sheet | None:
    """The style sheet's frames (``None`` without ``style_sheet:``)."""
    sheet: StyleSheet | None = project.config.style_sheet
    if sheet is None:
        return None
    look = _look_words(project, reference=False)
    shows = _clean(sheet.frame_prompt or DEFAULT_FRAME)
    def seed(n: int) -> int | None:  # frames after the first need their own seed to differ
        return None if sheet.seed is None and n == 1 else (sheet.seed or 0) + n - 1

    pictures = tuple(
        SheetPicture(f"frame{n}", _request(project, STYLE, f"frame{n}", f"Style frame, a still of the film with no writing anywhere: {shows}", look, FRAME_EXCLUDE, "auto", seed(n)))
        for n in range(1, sheet.frames + 1)
    )
    return Sheet(STYLE, "style_sheet", sheet.approved, pictures, sheet.words())


def project_sheets(project: Project) -> list[Sheet]:
    """Every sheet of the project: the characters' (in order), then the style sheet."""
    sheets = [character_sheet(project, e.name) for e in project.config.characters if e.reference_sheet is not None]
    style = style_sheet(project)
    return [s for s in sheets if s is not None] + ([style] if style is not None else [])


def _select(sheets: list[Sheet], owners: Sequence[str]) -> list[Sheet]:
    names = [s.owner for s in sheets]
    unknown = [o for o in owners if o not in names]
    if unknown:
        hint = did_you_mean(unknown[0], names)
        raise VidgenError(f"no sheet {unknown[0]!r}{hint}; sheets: {', '.join(names) or 'none (add characters[].reference_sheet or style_sheet:)'}")
    return [s for s in sheets if not owners or s.owner in owners]


@dataclass
class SheetsPlan:
    """What :func:`run_sheets` does: the pictures to make (``plan.todo``), the sheets skipped
    because they are approved (``blocked``), the budget, and what was paid."""

    sheets: list[Sheet]
    plan: ImagegenPlan
    blocked: list[Sheet]
    budget: BudgetState
    paid: float = 0.0

    @property
    def cost(self) -> tuple[float, int]:
        """Estimated US dollars of the pictures to make and how many have no known price."""
        return self.plan.cost


def plan_sheets(
    project: Project, owners: Sequence[str] = (), *, lookup: Callable[[list[str]], dict[str, Any]] | None = None, ledger: Ledger | None = None,
) -> SheetsPlan:
    """The pictures missing from the selected sheets (``owners``; default all), priced (a free
    public lookup for OpenRouter models; ``lookup`` replaces it in tests)."""
    from vidgen.videogen.run import ledger_path

    sheets = _select(project_sheets(project), owners)
    plan = ImagegenPlan()
    blocked = []
    for sheet in sheets:
        if sheet.approved and sheet.missing:
            blocked.append(sheet)
            continue
        for picture in sheet.pictures:
            plan.scenes.setdefault(picture.request.key, []).append(f"{sheet.owner} {picture.label}")
            if picture.request.exists:
                plan.up_to_date.append(picture.request.key)
            elif picture.request.key not in [r.key for r in plan.todo]:
                plan.todo.append(picture.request)
    if plan.todo:
        price_plan(plan, lookup=lookup)
    ledger = ledger or Ledger(ledger_path(project.root, project.config.videogen.provider))
    return SheetsPlan(sheets, plan, blocked, BudgetState(project.config.videogen.budget_usd, ledger.spent()))


def sheet_lines(result: SheetsPlan, root: Path, *, prompts: bool = True) -> list[str]:
    """The dry-run text of :func:`plan_sheets` (``prompts``: with each picture's prompt)."""
    lines = []
    for sheet in result.sheets:
        lines.append(f"{sheet.owner} sheet ({sheet.location}): {sheet.status()}")
        for picture in sheet.pictures:
            req = picture.request
            state = "made" if req.exists else "to make"
            lines.append(f"  {picture.label}: {req.path.relative_to(root).as_posix()} ({state})")
    plan = result.plan
    for request in plan.todo:
        quote = plan.quote(request)
        price = money(quote.cost) if quote.cost is not None else "price unknown"
        lines.append(f"would make {request.path.name}: {request.shape}, {request.provider} {request.model}, {price}")
        lines += [f"    note: {n}" for n in plan.notes.get(request.key, [])]
        lines += [f"    problem: {p}" for p in plan.problems.get(request.key, [])]
        if prompts:
            lines.append(f"    prompt: {request.text}")
    total, unknown = plan.cost
    extra = f" + {unknown} of unknown price" if unknown else ""
    lines.append(f"sheets: {len(plan.todo)} picture(s) to make, estimated {money(total)}{extra} ({plan.price_note}); {len(plan.up_to_date)} made")
    lines.append(f"  {result.budget.text()} (pictures count against videogen.budget_usd)")
    return lines


def run_sheets(
    project: Project, owners: Sequence[str] = (), *, pay: bool = False, provider: ImageProvider | None = None,
    out: Callable[[str], None] = print, lookup: Callable[[list[str]], dict[str, Any]] | None = None,
) -> SheetsPlan:
    """Plan the selected sheets and, with ``pay``, make their missing pictures (one request
    each, no retries), each recorded in the video ledger. Refuses (:class:`VidgenError`) without
    a budget, with a price unknown or above what the budget has left, or with a problem."""
    from vidgen.videogen.run import ledger_path

    name = provider.name if provider is not None else "openrouter"
    ledger = Ledger(ledger_path(project.root, MOCK_PROVIDER if name == MOCK_PROVIDER else "openrouter"))
    result = plan_sheets(project, owners, lookup=lookup, ledger=ledger)
    for line in sheet_lines(result, project.root):
        out(line)
    if not pay or not result.plan.todo:
        return result
    plan = result.plan
    chosen = provider if provider is not None else get_image_provider(project)
    if project.config.videogen.key_via_proxy and hasattr(chosen, "key_via_proxy"):
        chosen.key_via_proxy = True   # the proxy adds the OpenRouter key for the sheets too (§113.4)
    result.paid = pay_for_pictures(plan, result.budget, chosen, ledger, out, what="sheet picture", then="look at them, then set approved: true")
    return result


def pay_for_pictures(
    plan: ImagegenPlan, budget: BudgetState, chosen: ImageProvider, ledger: Ledger, out: Callable[[str], None], *, what: str, then: str,
) -> float:
    """Make every picture of ``plan.todo`` (one request each), each recorded in the video ledger
    and written beside its sidecar; returns the US dollars counted (reported, else estimated).
    Refuses (:class:`VidgenError`) with a problem, with no budget, or with a price unknown or above
    what ``budget`` has left. ``what`` names one picture in messages; ``then`` ends the last line."""
    problems = [p for r in plan.todo for p in plan.problems.get(r.key, [])]
    if problems:
        raise VidgenError("cannot make these pictures:\n  " + "\n  ".join(problems))
    total, unknown = plan.cost
    why = refusal(budget, None if unknown else total, plan.todo[0].model)
    if why:
        raise VidgenError(f"not paying for the {what}s: {why}")
    chosen.check_credentials()
    check_requests = getattr(chosen, "check_requests", None)
    if callable(check_requests):
        check_requests(plan.todo)
    reported = estimated = 0.0
    for n, request in enumerate(plan.todo, start=1):
        estimate = plan.quote(request).cost
        job = f"image-{request.key}"
        ledger.append("submit", job_id=job, provider=chosen.name, model=request.model, request_hash=request.key, estimate_usd=estimate)
        started = time.monotonic()
        try:
            picture = chosen.generate(request)
        except VidgenError as exc:
            ledger.append("failed", job_id=job, cost_usd=None, cost_source="estimate")
            raise VidgenError(f"{what} {request.path.name}: {exc}\n({n - 1} of {len(plan.todo)} made before the error; run again to continue)") from None
        source = "reported" if picture.cost is not None else "estimate"
        ledger.append("completed", job_id=job, cost_usd=picture.cost, cost_source=source)
        write_bytes_atomic(request.path, picture.data)
        doc = sidecar_document(request, picture.revised_prompt, plan.scenes[request.key], picture.cost, estimate=estimate, usage=picture.usage)
        write_text_atomic(request.sidecar, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        if picture.cost is not None:
            reported += picture.cost
        else:
            estimated += estimate or 0.0
        out(f"[{n}/{len(plan.todo)}] made {request.path.name} ({time.monotonic() - started:.1f} s, {cost_words(picture.cost, estimate, chosen.name)})")
    counted = [f"{money(reported)} reported by {chosen.name}"] if reported or not estimated else []
    if estimated:
        counted.append(f"{money(estimated)} estimated (not reported)")
    out(f"done: {len(plan.todo)} picture(s) made ({' + '.join(counted)}); {then}")
    return reported + estimated


__all__ = ["SHEETS_DIR", "STYLE", "Sheet", "SheetPicture", "SheetsPlan", "character_sheet", "plan_sheets", "project_sheets", "run_sheets", "sheet_lines", "style_sheet"]
