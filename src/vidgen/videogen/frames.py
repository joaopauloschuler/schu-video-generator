"""Painted starting pictures of generated shots (DESIGN.md §113.15): ``vidgen generate frames``.

``paint_first_frame:`` on a shot says what its starting picture shows. The first input picture
sent to the image model (OpenRouter ``input_references``) is the **layout**: the first frame of
the beat's draft render (``build/videogen/<shot>/layout.png``), whose composition, camera and
positions the model is told to keep; the shot's reference pictures follow, each named in the
prompt by what it shows. The result is stored as ``assets/frames/<shot>_<key>.png`` with a
``.json`` sidecar, so a changed prompt, layout or reference picture is a new file and the same
request is never paid twice.

Painting costs money: :func:`run_frames` is a dry run (the requests, an estimated price, what the
budget has left) unless ``pay``; paying needs ``videogen.budget_usd`` and records each picture in
the video ledger (``image-<key>`` jobs), like :func:`~vidgen.videogen.sheets.run_sheets`.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.config import ImagegenConfig
from vidgen.errors import VidgenError
from vidgen.imagegen import GenerateImage, ImageProvider, ImageRequest, image_request, video_aspect
from vidgen.imagegen.openrouter import OpenRouterImageProvider
from vidgen.imagegen.run import ImagegenPlan, price_plan
from vidgen.project import Project
from vidgen.videogen import did_you_mean
from vidgen.videogen.inputs import SceneRender, layout_picture
from vidgen.videogen.ledger import BudgetState, Ledger
from vidgen.videogen.models import money
from vidgen.videogen.pictures import sendable_picture
from vidgen.videogen.sheets import Sheet, pay_for_pictures
from vidgen.videogen.shots import INPUTS_DIR, Shot, ShotInput, _default_refs, project_sheet_map, reference_inputs

#: Where painted pictures are stored, relative to the project.
FRAMES_DIR = Path("assets") / "frames"
#: The layout picture of a shot, in its input folder.
LAYOUT_NAME = "layout.png"
#: Word used for the picture's shape in the prompt, by the video's shape.
_SHAPE_WORDS = {"portrait": "tall portrait", "landscape": "wide landscape", "square": "square"}
#: What the prompt says about the layout, the first input picture.
LAYOUT_INSTRUCTION = (
    "Paint one finished frame of a film, a {shape} picture. Reference picture 1 is a plain layout: keep its composition, "
    "camera height and the positions and sizes of everything in it exactly; its plain shapes and coloured capsules only "
    "stand for the things and people described here, they are not how they look"
)
NO_TEXT_IN_PICTURE = "No text, letters, signs, logos, labels or watermarks anywhere"


def layout_path(project: Project, shot: Shot) -> Path:
    """The layout picture of ``shot`` (it may not exist yet)."""
    return project.root / INPUTS_DIR / shot.id / LAYOUT_NAME


def paint_references(project: Project, shot: Shot, sheets: dict[str, Sheet | None]) -> tuple[list[ShotInput], list[str], list[str]]:
    """The references sent after the layout (``paint_first_frame.refs``, else the shot's own, in
    order), the problems of the bad entries, and why a sheet they use is not usable yet."""
    paint = shot.spec.paint_first_frame
    if paint is None:
        return [], [], []
    values = paint.refs if paint.refs is not None else shot.spec.refs if shot.spec.refs is not None else _default_refs(project, shot)
    problems: list[str] = []
    needs: set[str] = set()
    found = reference_inputs(project, values, sheets, set(), needs, f"{shot.location}.paint_first_frame.refs", problems)
    blocked = [s for s in (sheets[o].problem() for o in sorted(needs) if o in sheets and sheets[o] is not None) if s]
    return found, problems, blocked


def _name_tag_notes(project: Project, shot: Shot) -> list[str]:
    """A note when the layout shows stand-ins' name tags, which a model can paint as text."""
    objects = project.scene(shot.scene_id).params.get("objects") or []
    named = [str(o["name"]) for o in objects if isinstance(o, dict) and o.get("shape") == "standin" and o.get("name")]
    if not named:
        return []
    return [f"the layout shows the name tags of {', '.join(named)}: they can turn into text in the painted picture; leave name: off these stand-ins before paying"]


def paint_prompt(project: Project, shot: Shot, references: Sequence[ShotInput]) -> str:
    """The prompt sent to the image model: the layout instruction, which reference picture shows
    what (numbered by actual order, the layout being picture 1), the author's prompt, the
    setting and the style sheet's words, and no text in the picture."""
    paint = shot.spec.paint_first_frame
    assert paint is not None
    parts = [LAYOUT_INSTRUCTION.format(shape=_SHAPE_WORDS[video_aspect(project)])]
    numbers: dict[str, list[int]] = {}
    for number, item in enumerate(references, start=2):
        label = item.label or ("the look and colours of the film" if item.style else None)
        if label is not None:
            numbers.setdefault(label, []).append(number)
    parts += [f"Reference picture{'s' if len(found) > 1 else ''} {_joined_numbers(found)} show{'' if len(found) > 1 else 's'} {who}" for who, found in numbers.items()]
    parts.append(" ".join(paint.prompt.split()).rstrip("."))
    if shot.spec.setting:
        parts.append(f"Setting: {' '.join(shot.spec.setting.split()).rstrip('.')}")
    style = project.config.style_sheet
    if style is not None and style.words():
        parts.append(f"Style: {style.words()}")
    parts.append(NO_TEXT_IN_PICTURE)
    return " ".join(part + "." for part in parts)


def _joined_numbers(numbers: list[int]) -> str:
    return " and ".join(map(str, numbers)) if len(numbers) < 3 else f"{', '.join(map(str, numbers[:-1]))} and {numbers[-1]}"


def paint_request(project: Project, shot: Shot, references: Sequence[ShotInput]) -> ImageRequest | None:
    """The request that paints ``shot`` (``None``: its layout is not cut yet). Its key covers the
    prompt, the model options and the contents of the layout and of each reference picture."""
    paint = shot.spec.paint_first_frame
    assert paint is not None
    layout = layout_path(project, shot)
    if not layout.is_file():
        return None
    settings = ImagegenConfig(provider="openrouter", model=paint.model, resolution=paint.resolution)
    base = image_request(project, GenerateImage(prompt=paint_prompt(project, shot, references), style="none", seed=paint.seed), settings=settings)
    pictures = [layout, *(item.path for item in references)]
    digest = hashlib.sha1("|".join([base.key, *(hashlib.sha256(p.read_bytes()).hexdigest() for p in pictures)]).encode("ascii"))
    key = digest.hexdigest()[:16]
    folder = project.root / FRAMES_DIR
    stem = f"{shot.id}_{key}"
    return dataclasses.replace(
        base, key=key, path=folder / f"{stem}.png", sidecar=folder / f"{stem}.json", prompt=base.text,
        input_references=tuple(sendable_picture(p, project.root) for p in pictures),
    )


def painted_picture(project: Project, shot: Shot, sheets: dict[str, Sheet | None]) -> Path | None:
    """The painted picture of ``shot``'s current request, when it exists (``None``: none yet)."""
    references, problems, _ = paint_references(project, shot, sheets)
    request = paint_request(project, shot, references) if not problems else None
    return request.path if request is not None and request.exists else None


@dataclass
class PaintedFrame:
    """One shot of :func:`run_frames`: its request (``None``: bad references) and why it cannot be
    made yet (bad references or an unapproved sheet)."""

    shot: Shot
    references: list[ShotInput]
    request: ImageRequest | None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class FramesPlan:
    """What :func:`run_frames` does: the shots, the pictures to make, the budget, what was paid."""

    frames: list[PaintedFrame]
    plan: ImagegenPlan
    budget: BudgetState
    paid: float = 0.0

    @property
    def cost(self) -> tuple[float, int]:
        """Estimated US dollars of the pictures to make and how many have no known price."""
        return self.plan.cost


def plan_frames(
    project: Project, shots: Sequence[Shot], *, ledger: Ledger | None = None, lookup: Callable[[list[str]], dict[str, Any]] | None = None,
    render: Callable[[Project, str, tuple[str, ...]], SceneRender] | None = None, out: Callable[[str], None] = print,
) -> FramesPlan:
    """The painted pictures of ``shots`` still to make, priced (a free public lookup; ``lookup``
    replaces it in tests); cuts each shot's layout (a draft render, free; ``render`` replaces it)."""
    from vidgen.videogen.run import ledger_path

    sheets = project_sheet_map(project)
    plan = ImagegenPlan()
    frames: list[PaintedFrame] = []
    for shot in shots:
        layout = layout_picture(project, shot, render=render)
        out(f"{shot.id}: layout {layout.relative_to(project.root).as_posix()} (the first frame of the beat's draft render)")
        references, problems, blocked = paint_references(project, shot, sheets)
        request = paint_request(project, shot, references)
        frames.append(PaintedFrame(shot, references, request, [*problems, *blocked], _name_tag_notes(project, shot)))
        if request is None:
            continue
        plan.scenes.setdefault(request.key, []).append(shot.id)
        if request.exists:
            plan.up_to_date.append(request.key)
        elif request.key not in [r.key for r in plan.todo]:
            plan.todo.append(request)
    if plan.todo:
        price_plan(plan, lookup=lookup)
        for frame in frames:
            if frame.request is not None and frame.problems and frame.request in plan.todo:
                plan.problems.setdefault(frame.request.key, []).extend(frame.problems)
    ledger = ledger or Ledger(ledger_path(project.root, "openrouter"))
    return FramesPlan(frames, plan, BudgetState(project.config.videogen.budget_usd, ledger.spent()))


def frame_lines(result: FramesPlan, root: Path) -> list[str]:
    """The dry-run text of :func:`plan_frames`."""
    lines: list[str] = []
    plan = result.plan
    for frame in result.frames:
        shot, request = frame.shot, frame.request
        if request is None:
            lines.append(f"{shot.id}: not requested: {'; '.join(frame.problems) or 'no layout'}")
            continue
        state = "already painted, not paid again" if request.exists else "to paint"
        lines.append(f"{shot.id}: {request.path.relative_to(root).as_posix()} ({state})")
        lines.append(f"  input 1: {(INPUTS_DIR / shot.id / LAYOUT_NAME).as_posix()} (the layout)")
        lines += [f"  note: {n}" for n in frame.notes]
        for number, item in enumerate(frame.references, start=2):
            lines.append(f"  input {number}: {item.path.relative_to(root).as_posix() if item.path.is_relative_to(root) else item.path} ({item.what}{'' if item.ready else '; missing'})")
        if request.exists:
            continue
        quote = plan.quote(request)
        price = money(quote.cost) if quote.cost is not None else "price unknown"
        lines.append(f"  would make {request.path.name}: {request.shape}, {request.provider} {request.model}, {price} ({quote.basis})")
        lines += [f"  note: {n}" for n in plan.notes.get(request.key, [])]
        lines += [f"  problem: {p}" for p in plan.problems.get(request.key, [])]
        lines.append(f"  prompt: {request.prompt}")
    total, unknown = plan.cost
    extra = f" + {unknown} of unknown price" if unknown else ""
    lines.append(f"frames: {len(plan.todo)} picture(s) to paint, estimated {money(total)}{extra}; {len(plan.up_to_date)} already painted")
    lines.append(f"  {result.budget.text()} (pictures count against videogen.budget_usd)")
    return lines


def select_paint_shots(shots: Sequence[Shot], wanted: Sequence[str]) -> list[Shot]:
    """The shots with ``paint_first_frame:``, among ``wanted`` (shot or beat ids) when given."""
    with_paint = [s for s in shots if s.spec.paint_first_frame is not None]
    if not wanted:
        if not with_paint:
            raise VidgenError("no generated shot has paint_first_frame: {prompt: ...}: add one to the shot whose starting picture you want painted")
        return with_paint
    known = [s.id for s in shots]
    chosen: list[Shot] = []
    for name in wanted:
        matches = [s for s in shots if s.id == name or s.beat.id == name]
        if not matches:
            raise VidgenError(f"no generated shot {name!r}{did_you_mean(name, known)}; shots: {', '.join(known) or 'none'}")
        lacking = [s.id for s in matches if s.spec.paint_first_frame is None]
        if lacking:
            raise VidgenError(f"shot {lacking[0]} has no paint_first_frame: add {{prompt: ...}} to its generated_shot")
        chosen += matches
    return chosen


def run_frames(
    project: Project, shots: Sequence[Shot], *, pay: bool = False, provider: ImageProvider | None = None, out: Callable[[str], None] = print,
    lookup: Callable[[list[str]], dict[str, Any]] | None = None, render: Callable[[Project, str, tuple[str, ...]], SceneRender] | None = None,
) -> FramesPlan:
    """Plan the painted pictures of ``shots`` and, with ``pay``, make the missing ones (one request
    each, no automatic retries), each in the video ledger. Refuses (:class:`VidgenError`) without a
    budget, with a price unknown or above what the budget has left, or with a problem."""
    from vidgen.videogen.run import ledger_path

    name = provider.name if provider is not None else "openrouter"
    ledger = Ledger(ledger_path(project.root, name))
    result = plan_frames(project, shots, ledger=ledger, lookup=lookup, render=render, out=out)
    for line in frame_lines(result, project.root):
        out(line)
    painted = [r.path.relative_to(project.root).as_posix() for r in (f.request for f in result.frames) if r is not None]
    if not pay or not result.plan.todo:
        if result.plan.todo:
            out("dry run: nothing was sent or paid; `--pay` paints these pictures. Look at each picture before paying for a clip.")
        else:
            out(f"nothing to paint; a shot uses its picture with first_frame: painted ({', '.join(painted) or 'none'}). Look at it before paying for a clip.")
        return result
    chosen: ImageProvider
    if provider is not None:
        chosen = provider
    else:
        chosen = OpenRouterImageProvider(retries=0)   # a retry of a dropped paid request could pay twice
        chosen.key_via_proxy = project.config.videogen.key_via_proxy
    then = "LOOK at each picture before paying for a clip. A shot uses it with first_frame: painted, or first_frame: <its file>"
    result.paid = pay_for_pictures(result.plan, result.budget, chosen, ledger, out, what="painted frame", then=then)
    return result


__all__ = ["FRAMES_DIR", "LAYOUT_INSTRUCTION", "LAYOUT_NAME", "NO_TEXT_IN_PICTURE", "FramesPlan", "PaintedFrame", "frame_lines", "layout_path", "paint_prompt", "paint_references", "paint_request", "painted_picture", "plan_frames", "run_frames", "select_paint_shots"]
