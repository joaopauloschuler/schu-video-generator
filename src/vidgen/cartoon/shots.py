"""Shots within a stage scene: the camera framings of the ``shot:`` beat key (DESIGN.md §69.29).
No manim.

A *shot* frames characters where they stand when it starts: ``wide`` (everyone on stage, no
zoom), ``two_shot`` (two characters, whole), ``medium`` (one from the hips up), ``closeup`` (one's
head and shoulders) and ``over_shoulder`` (one character seen past another, the *near* one, who
stands cut by the frame's edge on the other side). :func:`frame_shot` turns the figures into a
camera view (centre and magnification), kept inside the stage like every camera move;
:func:`shot_figures` picks the figures a shot frames when the author named fewer.

Characters are flat and seen from the side, so a shot is a view of the stage: the near
character of an over-the-shoulder shot is as large as the subject (both magnified), at the edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vidgen.camera import Bounds, view_center_within
from vidgen.cartoon.stage import MAX_ZOOM, facing_sign
from vidgen.config import SHOT_NAMES

#: The framings, from the widest (the keys of :data:`~vidgen.config.SHOT_NAMES`: how many
#: characters each names).
SHOT_KINDS: tuple[str, ...] = tuple(SHOT_NAMES)
#: The part of a character a one-character framing shows, in its heights from the top of its
#: head: (below the top, above the top). A close-up shows the head and shoulders, a medium shot
#: the figure from about the hips up; an over-the-shoulder shot frames its subject like a medium.
SHOT_SPANS: dict[str, tuple[float, float]] = {"closeup": (0.62, 0.1), "medium": (1.0, 0.12), "over_shoulder": (1.0, 0.12)}
#: The narrowest view (in the subject's heights) a one-character framing keeps: in a portrait
#: frame a close-up framed by height alone was narrower than the head with its snout or beak
#: (the face cut in half; Step 155). A landscape frame's views are wider anyway.
SHOT_MIN_WIDTHS: dict[str, float] = {"closeup": 0.55, "medium": 0.7, "over_shoulder": 0.7}
#: Share of the view's width a one-character framing leaves more in front of the face than
#: behind it (the subject is moved this much away from the side it faces).
LOOK_ROOM = 0.1
#: Where the subject of an over-the-shoulder shot stands, as a share of the view's width from
#: the near character's edge (the near character's middle is on that edge, unless the shot
#: would be wider than the frame or tighter than a close-up).
SUBJECT_AT = 0.66
#: Share of the view kept free on each side of the figures of a two-shot.
TWO_SHOT_PADDING = 0.1
#: Half a generated figure's width in its heights (also the planner's predicted stills, DESIGN.md §69.24).
FIGURE_HALF_WIDTH = 0.21
#: The tightest framing (the layers are sized for zooms up to :data:`MAX_ZOOM`).
MAX_SHOT_SCALE = MAX_ZOOM
#: Seconds a ``shot`` with ``move: true`` eases to its framing (a cut takes no time).
SHOT_MOVE_SECONDS = 1.0
#: A tall frame on an iso place (:func:`portrait_shot`): a character wholly in the view keeps
#: this share of the view's width off its edges; the figures are centred up and down when the
#: view is this many times their height.
PORTRAIT_EDGE = 0.04
PORTRAIT_ROOM = 1.6


@dataclass(frozen=True)
class ShotFigure:
    """A character as a shot frames it (Manim units): the middle ``x`` of its figure, its feet's
    ``feet_y``, the ``top`` of its head (``feet_y + height`` while it stands; lower while it
    sits), its standing ``height`` and its ``facing``."""

    name: str
    x: float
    feet_y: float
    height: float
    facing: str = "right"
    top: float | None = None

    @property
    def head_top(self) -> float:
        """The top of its head (``top``, else its feet plus its height)."""
        return self.top if self.top is not None else self.feet_y + self.height

    def box(self) -> tuple[float, float, float, float]:
        """``(left, bottom, right, top)`` of the figure."""
        half = FIGURE_HALF_WIDTH * self.height
        return (self.x - half, self.feet_y, self.x + half, self.head_top)


@dataclass(frozen=True)
class ShotView:
    """A camera view: its centre and its magnification (1 = the whole frame's height)."""

    center_x: float
    center_y: float
    scale: float

    def size(self, frame_width: float, frame_height: float) -> tuple[float, float]:
        """The view's width and height in Manim units."""
        return frame_width / self.scale, frame_height / self.scale


@dataclass(frozen=True)
class Shot:
    """A framing to show: its ``kind``, the characters it frames (``subjects``) and, for an
    over-the-shoulder shot, the ``near`` one."""

    kind: str
    subjects: tuple[str, ...]
    near: str | None = None

    def layout(self) -> dict[str, object]:
        """The layout dump's ``shot`` key of a frame (read by lint ``off_stage``)."""
        return {"kind": self.kind, "subjects": list(self.subjects), **({"near": self.near} if self.near else {})}


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _sign(facing: str) -> float:
    return facing_sign(facing, front=0.0)


def _one(subject: ShotFigure, kind: str, frame_width: float, frame_height: float) -> tuple[float, float, float]:
    """``(scale, centre y, view width)`` framing ``subject`` by its span (:data:`SHOT_SPANS`), no
    narrower than :data:`SHOT_MIN_WIDTHS`."""
    below, above = SHOT_SPANS[kind]
    tightest = min(frame_height / ((below + above) * subject.height), frame_width / (SHOT_MIN_WIDTHS[kind] * subject.height))
    scale = _clamp(tightest, 1.0, MAX_SHOT_SCALE)
    view_height = frame_height / scale
    return scale, subject.head_top + above * subject.height - view_height / 2, frame_width / scale


def frame_shot(
    kind: str, subjects: Sequence[ShotFigure], *, frame_width: float, frame_height: float, bounds: Bounds,
    near: ShotFigure | None = None,
) -> ShotView:
    """The camera view of a ``kind`` shot (:data:`SHOT_KINDS`) of ``subjects`` (and the ``near``
    character of an over-the-shoulder shot), kept inside ``bounds`` (``view_center_within``):

    - ``wide``: no zoom, centred on the middle of the subjects (the stage's middle without any);
    - ``two_shot``: the subjects' figures, whole, with :data:`TWO_SHOT_PADDING` around them;
    - ``medium`` / ``closeup``: the first subject's :data:`SHOT_SPANS`, with :data:`LOOK_ROOM`
      in front of its face;
    - ``over_shoulder``: the subject framed as ``medium`` across, at :data:`SUBJECT_AT` of the
      width from the near character's side, zoomed so the near one's middle is on that edge (no
      more than a close-up; without a ``near`` character it is a ``medium``).
    """
    if kind not in SHOT_KINDS:
        raise ValueError(f"unknown shot '{kind}' (shots: {', '.join(SHOT_KINDS)})")
    if kind != "wide" and not subjects:
        raise ValueError(f"a {kind} shot needs a character to frame")
    if kind == "wide":
        left, right = bounds[:2]
        xs = [b for s in subjects for b in s.box()[::2]]
        x = (min(xs) + max(xs)) / 2 if xs else (left + right) / 2
        return _within(bounds, x, 0.0, 1.0, frame_width, frame_height)
    if kind == "two_shot":
        boxes = [s.box() for s in subjects]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        room = 1 - 2 * TWO_SHOT_PADDING
        scale = min(room * frame_width / max(x1 - x0, 1e-6), room * frame_height / max(y1 - y0, 1e-6))
        return _within(bounds, (x0 + x1) / 2, (y0 + y1) / 2, _clamp(scale, 1.0, MAX_SHOT_SCALE), frame_width, frame_height)
    subject = subjects[0]
    if kind == "over_shoulder" and near is not None:
        scale, _, _ = _one(subject, "over_shoulder", frame_width, frame_height)
        closest = _one(subject, "closeup", frame_width, frame_height)[0]
        apart = abs(subject.x - near.x)
        if apart > 1e-6:
            scale = _clamp(SUBJECT_AT * frame_width / apart, 1.0, closest)
        view_width, view_height = frame_width / scale, frame_height / scale
        side = 1.0 if subject.x > near.x or (apart <= 1e-6 and subject.facing == "left") else -1.0
        x = subject.x - side * (SUBJECT_AT - 0.5) * view_width
        top = subject.head_top + SHOT_SPANS["over_shoulder"][1] * subject.height
        return _within(bounds, x, top - view_height / 2, scale, frame_width, frame_height)
    framing = "medium" if kind == "over_shoulder" else kind
    scale, y, view_width = _one(subject, framing, frame_width, frame_height)
    return _within(bounds, subject.x + _sign(subject.facing) * LOOK_ROOM * view_width, y, scale, frame_width, frame_height)


def _within(bounds: Bounds, x: float, y: float, scale: float, frame_width: float, frame_height: float) -> ShotView:
    cx, cy = view_center_within(bounds, (x, y), frame_width / scale, frame_height / scale)
    return ShotView(cx, cy, scale)


def shot_figures(
    kind: str, named: Sequence[str], present: Mapping[str, ShotFigure], *, speakers: Sequence[str] = (),
    looked_at: Mapping[str, str | None] | None = None,
) -> Shot:
    """The characters a ``kind`` shot frames, from the ones ``named`` (in the config) and the
    ``present`` ones (on stage, in the stage's order): ``wide`` frames every present one; a
    ``two_shot`` without names the beat's first speaker (else the first present one) and the
    present character nearest it; an ``over_shoulder`` without a second name looks past the
    character the subject last looked at, else the one nearest it. Named characters not present
    are left out (a framing of no one is a ``wide``)."""
    looked_at = looked_at or {}
    if kind == "wide":
        return Shot("wide", tuple(present))
    chosen = [n for n in named if n in present]
    if kind == "two_shot" and not named:
        first = next((s for s in speakers if s in present), next(iter(present), None))
        chosen = [first] if first is not None else []
    if not chosen:
        return Shot("wide", tuple(present))
    subject = present[chosen[0]]
    others = [f for name, f in present.items() if name != subject.name]
    nearest = min(others, key=lambda f: abs(f.x - subject.x)).name if others else None
    if kind == "two_shot":
        pair = chosen[:2] if len(chosen) >= 2 else [chosen[0], *([nearest] if nearest else [])]
        return Shot("two_shot", tuple(pair))
    if kind == "over_shoulder":
        if len(named) > 1:
            near = named[1] if named[1] in present and named[1] != subject.name else None
        else:
            looked = looked_at.get(subject.name)
            near = looked if looked in present and looked != subject.name else nearest
        return Shot("over_shoulder", (subject.name,), near)
    return Shot(kind, (subject.name,))


def shot_view(shot: Shot, present: Mapping[str, ShotFigure], *, frame_width: float, frame_height: float, bounds: Bounds) -> ShotView:
    """:func:`frame_shot` of ``shot`` (from :func:`shot_figures`) with the ``present`` figures."""
    subjects = [present[n] for n in shot.subjects if n in present]
    near = present.get(shot.near) if shot.near else None
    return frame_shot(shot.kind, subjects, frame_width=frame_width, frame_height=frame_height, bounds=bounds, near=near)


def portrait_shot(view: ShotView, shot: Shot, present: Mapping[str, ShotFigure], *, frame_width: float, frame_height: float,
                  bounds: Bounds) -> ShotView:
    """``view`` (:func:`shot_view` of ``shot``) reframed for a tall frame where it is wider than
    the framing asked for (a close-up held back by :data:`MAX_SHOT_SCALE`: on an iso place the
    characters are small, and a 9:16 view at the tightest zoom is about three of them tall):

    - across: the nearest centre at which every other character ``present`` is either wholly in
      the view (:data:`PORTRAIT_EDGE` of its width inside each edge) or wholly out of it, the
      subjects staying wholly in, so nobody stands cut in half at the frame's edge;
    - up and down: when the view is :data:`PORTRAIT_ROOM` times taller than the characters in it,
      their figures are centred (a close-up's head at the top left the lower two thirds to the
      ground).

    ``wide`` and ``over_shoulder`` (whose near character is cut on purpose) are kept as they are."""
    if shot.kind in ("wide", "over_shoulder"):
        return view
    subjects = [present[n] for n in shot.subjects if n in present]
    if not subjects:
        return view
    width, height = frame_width / view.scale, frame_height / view.scale
    edge = PORTRAIT_EDGE * width
    others = [f.box() for name, f in present.items() if name not in shot.subjects]
    mine = [s.box() for s in subjects]

    def fine(cx: float) -> bool:
        left, right = cx - width / 2, cx + width / 2
        if any(b[0] < left + edge - 1e-9 or b[2] > right - edge + 1e-9 for b in mine):
            return False
        return all(b[2] <= left + 1e-9 or b[0] >= right - 1e-9 or (b[0] >= left + edge - 1e-9 and b[2] <= right - edge + 1e-9) for b in others)

    x = view.center_x
    if not fine(x):
        candidates = [c for b in [*others, *mine] for c in (b[0] - edge + width / 2, b[2] + edge - width / 2, b[2] + width / 2, b[0] - width / 2)]
        found = sorted((c for c in candidates if fine(c)), key=lambda c: abs(c - x))
        x = found[0] if found else x
    left, right = x - width / 2, x + width / 2
    shown = mine + [b for b in others if b[0] >= left + edge - 1e-9 and b[2] <= right - edge + 1e-9]
    low, high = min(b[1] for b in shown), max(b[3] for b in shown)
    y = (low + high) / 2 if height >= PORTRAIT_ROOM * (high - low) else view.center_y
    return _within(bounds, x, y, view.scale, frame_width, frame_height)


__all__ = [
    "LOOK_ROOM",
    "PORTRAIT_EDGE",
    "PORTRAIT_ROOM",
    "portrait_shot",
    "MAX_SHOT_SCALE",
    "SHOT_KINDS",
    "SHOT_MIN_WIDTHS",
    "SHOT_MOVE_SECONDS",
    "SHOT_SPANS",
    "SUBJECT_AT",
    "TWO_SHOT_PADDING",
    "Shot",
    "ShotFigure",
    "ShotView",
    "frame_shot",
    "shot_figures",
    "shot_view",
]
