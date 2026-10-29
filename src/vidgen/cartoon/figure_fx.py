"""Effects on a whole character, drawn with manim (DESIGN.md §100.9, §100.10); the maths is in
:mod:`vidgen.cartoon.apparition`.

- :class:`FigureAlpha`: a character's opacities as drawn and named factors on them (a shot that
  clears the others, a hologram's flicker, a materialise), applied together.
- :class:`Materialise`: the ``materialise`` / ``dematerialise`` animation.
- :class:`Iridescence`: an oil-on-water colour shift over its skin and clothes.
- :class:`Afterimages`: faint copies left behind while it moves, fading.
- :class:`HandHold`: two characters' hands meeting between them, wherever they stand or walk.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from manim import Animation, Mobject, VGroup, VMobject

from vidgen.cartoon.apparition import flicker_level, iridescent_rgb, materialise_levels
from vidgen.cartoon.character import Character, CharacterState, PartPose

#: The attribute holding a character's :class:`FigureAlpha`.
FIGURE_ALPHA = "figure_alpha"


class FigureAlpha:
    """The fill and stroke opacities of every member of ``figure`` as drawn now, and factors on
    them by name (``set``); :meth:`apply` draws the product. Made once per character
    (:func:`figure_alpha`)."""

    def __init__(self, figure: Mobject) -> None:
        self.figure = figure
        self.members = [m for m in figure.get_family() if isinstance(m, VMobject)]
        self.fill = [m.fill_rgbas[:, 3].copy() for m in self.members]
        self.stroke = [m.stroke_rgbas[:, 3].copy() for m in self.members]
        self.factors: dict[str, tuple[float, float]] = {}

    def set(self, key: str, fill: float, stroke: float | None = None) -> FigureAlpha:
        """Set the factor ``key`` (fill, and stroke: default the fill's); 1 for both removes it."""
        stroke = fill if stroke is None else stroke
        if fill >= 1.0 and stroke >= 1.0:
            self.factors.pop(key, None)
        else:
            self.factors[key] = (max(float(fill), 0.0), max(float(stroke), 0.0))
        return self

    def level(self) -> tuple[float, float]:
        """The product of the factors: (fill, stroke)."""
        fill = math.prod(f for f, _ in self.factors.values()) if self.factors else 1.0
        stroke = math.prod(s for _, s in self.factors.values()) if self.factors else 1.0
        return fill, stroke

    def apply(self) -> None:
        """Draw every member at its drawn opacities times the factors."""
        fill, stroke = self.level()
        for member, f, s in zip(self.members, self.fill, self.stroke):
            _scaled(member.fill_rgbas, f, fill)
            _scaled(member.stroke_rgbas, s, stroke)
        self.figure.shown = min(fill, 1.0) if hasattr(self.figure, "shown") else 1.0


def _scaled(rgbas: np.ndarray, base: np.ndarray, factor: float) -> None:
    if len(rgbas) == len(base):
        rgbas[:, 3] = base * factor
    elif len(base):
        rgbas[:, 3] = float(base[0]) * factor


def figure_alpha(figure: Mobject) -> FigureAlpha:
    """``figure``'s :class:`FigureAlpha`, made the first time it is asked for."""
    found = getattr(figure, FIGURE_ALPHA, None)
    if found is None:
        found = FigureAlpha(figure)
        setattr(figure, FIGURE_ALPHA, found)
    return found


class Materialise(Animation):
    """``figure`` materialising (``out``: dematerialising) over the animation: a flickering
    wireframe, then solid (:func:`~vidgen.cartoon.apparition.materialise_levels`); its factor
    ``appear`` is 1 (none) at the end of a materialise, 0 at the end of a dematerialise.
    ``clock``: the scene time now (the flicker)."""

    def __init__(self, figure: Mobject, *, out: bool = False, seed: int = 0, clock: Any = None, **kwargs: Any) -> None:
        self.out = out
        self.seed = seed
        self.clock = clock
        self.alpha = figure_alpha(figure)
        super().__init__(figure, **kwargs)

    def interpolate_mobject(self, alpha: float) -> None:
        share = 1.0 - alpha if self.out else alpha
        now = float(self.clock()) if self.clock is not None else alpha
        outline, fill = materialise_levels(share, now, self.seed)
        if self.out and alpha >= 1.0:
            outline, fill = 0.0, 0.0
        self.alpha.set("appear", fill, outline).apply()


class Iridescence:
    """``figure``'s skin and clothes shifting colours like oil on water (DESIGN.md §100.9):
    :meth:`update` recolours every filled member from the colour it was drawn with
    (:func:`~vidgen.cartoon.apparition.iridescent_rgb`) by its height on the figure."""

    def __init__(self, figure: Character, *, strength: float = 1.0, seconds: float = 12.0) -> None:
        self.figure = figure
        self.strength = strength
        self.seconds = seconds
        self.members = [m for m in figure.get_family() if isinstance(m, VMobject) and len(m.fill_rgbas) and m.fill_rgbas[0, 3] > 0]
        self.colors = [tuple(float(c) for c in m.fill_rgbas[0, :3]) for m in self.members]

    def update(self, now: float) -> None:
        """Recolour the members for scene time ``now``."""
        feet = float(self.figure.feet()[1])
        height = max(float(self.figure.standing_height), 1e-6)
        for member, rgb in zip(self.members, self.colors):
            if not len(member.points):
                continue
            up = (float(member.get_center()[1]) - feet) / height
            member.fill_rgbas[:, :3] = iridescent_rgb(rgb, up, now, strength=self.strength, seconds=self.seconds)  # type: ignore[arg-type]


#: Afterimages: seconds between copies while it moves, how long each fades, its starting opacity
#: (a share of the figure's) and how far (in its heights) it must have moved for a new copy.
AFTERIMAGE_SPACING = 0.12
AFTERIMAGE_LIFE = 0.6
AFTERIMAGE_OPACITY = 0.35
AFTERIMAGE_MOVE = 0.03


class Afterimages:
    """Faint copies of ``figure`` left where it was while it moves (DESIGN.md §100.9), each
    fading over ``life`` seconds; ``place(ghost)`` puts a new copy in the scene (right behind the
    figure), ``remove(ghost)`` takes one away."""

    def __init__(self, figure: Character, *, place: Any, remove: Any, spacing: float = AFTERIMAGE_SPACING,
                 life: float = AFTERIMAGE_LIFE, opacity: float = AFTERIMAGE_OPACITY) -> None:
        self.figure = figure
        self.place = place
        self.remove = remove
        self.spacing, self.life, self.opacity = spacing, life, opacity
        self.ghosts: list[tuple[float, VGroup, list[tuple[VMobject, np.ndarray, np.ndarray]]]] = []
        self._last: tuple[float, np.ndarray] | None = None

    def update(self, now: float) -> None:
        """Fade the copies for scene time ``now``, drop the faded ones, leave a new one when the
        figure has moved since the last."""
        for born, ghost, members in list(self.ghosts):
            age = (now - born) / self.life
            if age >= 1.0 or age < 0.0:
                self.remove(ghost)
                self.ghosts.remove((born, ghost, members))
                continue
            level = self.opacity * (1.0 - age) ** 1.5
            for member, fill, stroke in members:
                member.fill_rgbas[:, 3] = fill * level
                member.stroke_rgbas[:, 3] = stroke * level
        feet = np.asarray(self.figure.feet(), dtype=float)
        shown = float(getattr(self.figure, "shown", 1.0))
        if self._last is None:
            self._last = (now, feet)
            return
        moved = float(np.linalg.norm(feet[:2] - self._last[1][:2])) / max(float(self.figure.standing_height), 1e-6)
        if now - self._last[0] >= self.spacing and moved >= AFTERIMAGE_MOVE and shown > 0.5:
            leaves = [m.copy() for m in self.figure.family_members_with_points() if isinstance(m, VMobject)]
            for leaf in leaves:
                leaf.clear_updaters()
            ghost = VGroup(*leaves)
            ghost.name = f"{self.figure.name}_afterimage"
            members = [(m, m.fill_rgbas[:, 3].copy(), m.stroke_rgbas[:, 3].copy()) for m in leaves]
            for member, fill, stroke in members:
                member.fill_rgbas[:, 3] = fill * self.opacity
                member.stroke_rgbas[:, 3] = stroke * self.opacity
            self.place(ghost)
            self.ghosts.append((now, ghost, members))
            self._last = (now, feet)
        elif moved < AFTERIMAGE_MOVE:
            self._last = (now, self._last[1])

    def clear(self) -> None:
        """Take every copy away."""
        for _, ghost, _ in self.ghosts:
            self.remove(ghost)
        self.ghosts = []


#: A glowing pendant (DESIGN.md §102.14): its halo's light pulses between ``1 - PENDANT_PULSE``
#: and 1 of its drawn opacity every ``PENDANT_SECONDS``, the stone brightening with it.
PENDANT_PULSE = 0.65
PENDANT_SECONDS = 1.6


def pendant_level(now: float) -> float:
    """How bright a glowing pendant is at scene time ``now`` (1 - PENDANT_PULSE .. 1): a soft
    pulse, quick to rise and slow to fade, like a heartbeat of light."""
    phase = (now / PENDANT_SECONDS) % 1.0
    rise = min(phase / 0.2, 1.0) if phase < 0.2 else max(1.0 - (phase - 0.2) / 0.8, 0.0)
    return 1.0 - PENDANT_PULSE * (1.0 - rise * rise * (3.0 - 2.0 * rise))


class PendantPulse:
    """``figure``'s glowing pendant pulsing (DESIGN.md §102.14): its halo's opacity follows
    :func:`pendant_level`, its stone a little (members marked by the clothes'
    ``PENDANT_GLOW``), times the figure's own opacity factors (a flicker, a materialise)."""

    def __init__(self, figure: Character, members: list[tuple[VMobject, str]]) -> None:
        self.figure = figure
        self.members = [(m, role, m.fill_rgbas[:, 3].copy()) for m, role in members]

    def update(self, now: float) -> None:
        level = pendant_level(now)
        alpha = getattr(self.figure, FIGURE_ALPHA, None)
        shown = alpha.level()[0] if alpha is not None else 1.0
        for member, role, base in self.members:
            if len(member.fill_rgbas) != len(base):
                continue
            factor = level if role == "halo" else 0.75 + 0.25 * level
            member.fill_rgbas[:, 3] = base * factor * shown


#: A kiss's hearts and sparkles by default (DESIGN.md §102.15).
KISS_COLOR = "#FF5C8A"
KISS_SPARKLE = "#FFF1B8"
#: The legs a lean turns back, so the feet stay on the ground.
LEG_PARTS: tuple[str, ...] = ("legs", "leg_left", "leg_right")
#: How far up or down (head heights) each steps to bring their heads level, at most.
KISS_RISE = 0.6


def head_box(figure: Character) -> tuple[float, float, float, float]:
    """The box (left, bottom, right, top) of ``figure``'s head on screen (Manim units)."""
    points = [m.points for m in figure.parts["head"].get_family() if len(m.points)]
    xy = np.concatenate(points)[:, :2]
    return float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())


class KissPlan:
    """Two characters kissing over ``seconds`` (DESIGN.md §102.15): on its first frame they turn
    to each other and the plan measures how far each leans (:func:`~vidgen.cartoon.kiss.lean_angles`)
    and steps in across the picture for their faces to touch at full lean
    (:func:`~vidgen.cartoon.kiss.step_in`); :meth:`update` poses both for a time into the kiss
    (:func:`~vidgen.cartoon.kiss.kiss_share`): bodies tilted forward at the waist (the legs
    turned back, the feet on the ground), eyes closed while close, stepped in, and back to how
    they stood at its end. Both characters' animations call it; it acts once per time."""

    def __init__(self, a: Character, b: Character, seconds: float) -> None:
        self.a, self.b, self.seconds = a, b, float(seconds)
        self.ready = False
        self._last: float | None = None
        self.offsets: dict[str, np.ndarray] = {}
        self.drawn: dict[str, np.ndarray] = {}

    def _prepare(self) -> None:
        from vidgen.cartoon.kiss import lean_angles, step_in

        self.ready = True
        ax, bx = float(self.a.feet()[0]), float(self.b.feet()[0])
        for figure, other_x, own_x in ((self.a, bx, ax), (self.b, ax, bx)):
            want = "right" if other_x >= own_x else "left"
            if figure.facing != want:
                figure.face(want)
        self.before = {f.name: dict(f.state().parts) for f in (self.a, self.b)}
        ha, hb = head_box(self.a), head_box(self.b)
        height = max(ha[3] - ha[1], hb[3] - hb[1])
        self.lean = dict(zip((self.a.name, self.b.name), lean_angles((ha[1] + ha[3]) / 2, (hb[1] + hb[3]) / 2, height)))
        self._pose(1.0)
        ha, hb = head_box(self.a), head_box(self.b)
        left, right = (ha, hb) if ax <= bx else (hb, ha)
        step = step_in(right[0] - left[2], min(ha[2] - ha[0], hb[2] - hb[0]))
        # their heads level too, as far as a step towards each other takes them (on an iso place
        # two side by side on the map stand on a slant across the picture)
        rise = ((hb[1] + hb[3]) - (ha[1] + ha[3])) / 4.0
        rise = min(max(rise, -KISS_RISE * height), KISS_RISE * height)
        sign = 1.0 if ax <= bx else -1.0
        self.moves = {self.a.name: (sign * step, rise), self.b.name: (-sign * step, -rise)}
        self._pose(0.0)

    def _pose(self, share: float) -> None:
        from vidgen.cartoon.kiss import EYES_CLOSE

        for figure in (self.a, self.b):
            before = self.before[figure.name]
            lean = self.lean[figure.name] * share
            parts: dict[str, PartPose] = {}
            body = before.get("body", PartPose())
            parts["body"] = PartPose(body.angle - lean, body.scale, body.shift, body.shape)
            for leg in LEG_PARTS:
                if figure.has_part(leg):
                    pose = before.get(leg, PartPose())
                    parts[leg] = PartPose(pose.angle + lean, pose.scale, pose.shift, pose.shape)
            if figure.has_part("eyes") and "closed" in figure.shape_names("eyes"):
                eyes = before.get("eyes", PartPose())
                parts["eyes"] = PartPose(eyes.angle, eyes.scale, eyes.shift, "closed") if share >= EYES_CLOSE else eyes
            figure.set_state(CharacterState(figure.facing, {**figure.state().parts, **parts}))

    def update(self, t: float) -> None:
        """Pose both for ``t`` seconds into the kiss (once per time)."""
        from vidgen.cartoon.kiss import kiss_share

        if not self.ready:
            self._prepare()
        if self._last is not None and abs(self._last - t) < 1e-9:
            return
        self._last = t
        share = kiss_share(t, self.seconds)
        self._pose(share)
        for figure in (self.a, self.b):
            feet = np.asarray(figure.feet(), dtype=float)[:2]
            last, offset = self.drawn.get(figure.name), self.offsets.get(figure.name, np.zeros(2))
            own = feet if last is None or float(np.linalg.norm(feet - last)) > 1e-9 else feet - offset   # moved by the stage since: that is its place
            new = np.array(self.moves[figure.name]) * share
            figure.shift(np.array([*(own + new - feet), 0.0]))
            self.offsets[figure.name] = new
            self.drawn[figure.name] = np.asarray(figure.feet(), dtype=float)[:2]
            figure.kissing = (self.b if figure is self.a else self.a).name if share > 0.0 else None   # the layout dump: lint lets them stand close

    def meeting(self) -> tuple[float, float, float]:
        """Where their faces meet now (x, y on screen) and a head's height."""
        ha, hb = head_box(self.a), head_box(self.b)
        left, right = (ha, hb) if ha[0] <= hb[0] else (hb, ha)
        x = (left[2] + right[0]) / 2
        y = (ha[1] + ha[3] + hb[1] + hb[3]) / 4
        return x, y, max(ha[3] - ha[1], hb[3] - hb[1])


class KissMotion(Animation):
    """One character's side of a kiss: each frame asks the shared :class:`KissPlan` to pose
    both for the time into the action (a linear clock)."""

    def __init__(self, figure: Character, plan: KissPlan, **kwargs: Any) -> None:
        self.plan = plan
        kwargs.setdefault("rate_func", lambda t: t)
        super().__init__(figure, **kwargs)

    def create_starting_mobject(self) -> Mobject:
        """No copy of the character: nothing interpolates from it."""
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        self.plan.update(alpha * self.plan.seconds)   # the kiss's own clock, whatever run time the scene plays it in


def _heart_points(cx: float, cy: float, size: float) -> np.ndarray:
    """A heart ``size`` wide about (cx, cy), as corners."""
    points = []
    for k in range(25):
        a = 2.0 * math.pi * k / 24
        x = 16 * math.sin(a) ** 3
        y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
        points.append([cx + x / 34 * size, cy + y / 34 * size, 0.0])
    return np.array(points)


class KissBurst(Animation):
    """The small burst of hearts and sparkles of a kiss (:func:`~vidgen.cartoon.kiss.burst`),
    rising from where the faces meet (``plan``) from ``contact`` seconds into the action; added
    over the scene for the action and removed at its end. Never graded by the stage's light."""

    def __init__(self, plan: KissPlan, contact: float, *, color: str = KISS_COLOR, seed: int = 0, **kwargs: Any) -> None:
        from vidgen.cartoon.kiss import BURST_HEARTS, BURST_SPARKLES

        self.plan, self.contact, self.seed = plan, float(contact), seed
        self.hearts = [VMobject().set_fill(color, opacity=0.0).set_stroke("#FFFFFF", width=1.5, opacity=0.0) for _ in range(BURST_HEARTS)]
        self.sparkles = [VMobject().set_fill(KISS_SPARKLE, opacity=0.0).set_stroke(width=0.0, opacity=0.0) for _ in range(BURST_SPARKLES)]
        group = VGroup(*self.hearts, *self.sparkles)
        group.name = "kiss_burst"
        kwargs.setdefault("rate_func", lambda t: t)
        super().__init__(group, introducer=True, remover=True, **kwargs)

    def create_starting_mobject(self) -> Mobject:
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        from vidgen.cartoon.kiss import burst

        found = burst(alpha * self.plan.seconds - self.contact, self.seed) if self.plan.ready else []
        hearts = [f for f in found if f[0] == "heart"]
        sparkles = [f for f in found if f[0] == "sparkle"]
        x, y, h = self.plan.meeting() if found else (0.0, 0.0, 1.0)
        for members, shapes in ((self.hearts, hearts), (self.sparkles, sparkles)):
            for k, member in enumerate(members):
                if k >= len(shapes) or shapes[k][3] <= 1e-4:
                    member.points = np.zeros((0, 3))
                    continue
                kind, dx, dy, size, opacity = shapes[k]
                cx, cy, s = x + dx * h, y + dy * h, size * h
                if kind == "heart":
                    member.set_points_as_corners(_heart_points(cx, cy, s))
                    member.set_fill(opacity=opacity).set_stroke(opacity=0.8 * opacity)
                else:
                    member.set_points_as_corners([[cx + s * math.cos(a) * (1.0 if j % 2 == 0 else 0.25), cy + s * math.sin(a) * (1.0 if j % 2 == 0 else 0.25), 0.0]
                                                  for j, a in enumerate(np.linspace(0.0, 2.0 * math.pi, 9))])
                    member.set_fill(opacity=opacity)


#: Holding hands: seconds the hands take to reach each other, and how far below the shoulders
#: they meet (a share of the taller one's height).
HAND_REACH_SECONDS = 0.4
HAND_DROP = 0.3
#: Two holding hands stand close enough for their hands to meet (DESIGN.md §100.15): each arm
#: reaches at most this share of its length, their shoulders stay at least :data:`HAND_MIN_GAP`
#: of the taller one's height apart and their feet :data:`HAND_MIN_APART` (side by side, not
#: one in front of the other, whichever way they turn).
HAND_REACH = 0.92
HAND_MIN_GAP = 0.22
HAND_MIN_APART = 0.42


class HandHold:
    """Two characters holding hands (DESIGN.md §100.10): from ``start`` (scene time) each one's
    hand nearer the other reaches for the point between their shoulders, a little lower
    (:data:`HAND_DROP`), wherever they stand or walk, until the hold ends. Standing further
    apart than their arms reach, they step in towards each other across the picture as the
    hands reach; walking together (both moved by their walks on a frame), the second keeps its
    place beside the first, so they go side by side instead of one behind the other
    (:meth:`_keep_close`, §100.15)."""

    def __init__(self, a: Character, b: Character, start: float) -> None:
        self.a, self.b, self.start = a, b, float(start)
        self.hands = (_nearer_hand(a, b), _nearer_hand(b, a))
        self.rest = {figure.name: _arm_poses(figure, hand) for figure, hand in zip((a, b), self.hands)}
        #: each arm's length (shoulder to hand, as it hangs at the start)
        self.arm = [float(np.linalg.norm(np.asarray(f.hand_point(h))[:2] - np.asarray(f.shoulder_point(h))[:2]))
                    for f, h in zip((a, b), self.hands)]
        #: each one's offset from where the stage or its walk puts it, and where its feet were
        #: drawn after the last frame (an animation that places it anew moved them since)
        self.offsets: dict[str, np.ndarray] = {}
        self.drawn: dict[str, np.ndarray] = {}
        #: where the second stands from the first while they walk together
        self.formation: np.ndarray | None = None

    def _keep_close(self, share: float) -> None:
        """Place both for this frame: each at its own place (where the stage or its walk puts
        it) plus its offset. Standing, the offsets step them ``share`` of the way in towards
        each other across the picture until their hands can meet; both walking, the first keeps
        its offset and the second its place beside the first."""
        own: dict[str, np.ndarray] = {}
        moved: dict[str, bool] = {}
        for figure in (self.a, self.b):
            feet = np.asarray(figure.feet(), dtype=float)[:2]
            last, offset = self.drawn.get(figure.name), self.offsets.get(figure.name, np.zeros(2))
            moved[figure.name] = last is None or float(np.linalg.norm(feet - last)) > 1e-9
            own[figure.name] = feet if moved[figure.name] else feet - offset
            figure.shift(np.array([*(own[figure.name] - feet), 0.0]))
        walking = all(moved.values()) and self.formation is not None and self.drawn
        if walking:
            first = self.offsets.get(self.a.name, np.zeros(2))
            offsets = {self.a.name: first, self.b.name: own[self.a.name] + first + self.formation - own[self.b.name]}
        else:
            sa, sb = self.a.shoulder_point(self.hands[0]), self.b.shoulder_point(self.hands[1])
            height = max(self.a.standing_height, self.b.standing_height)
            drop = HAND_DROP * height
            reach = HAND_REACH * min(self.arm)
            want = max(2.0 * math.sqrt(max(reach * reach - drop * drop, 0.0)), HAND_MIN_GAP * height)
            gap = float(sb[0] - sa[0])
            across = float(own[self.b.name][0] - own[self.a.name][0])
            step = min(max(abs(gap) - want, 0.0), max(abs(across) - HAND_MIN_APART * height, 0.0)) / 2.0 * share
            side = 1.0 if across >= 0 else -1.0
            offsets = {self.a.name: np.array([side * step, 0.0]), self.b.name: np.array([-side * step, 0.0])}
        for figure in (self.a, self.b):
            offset = offsets[figure.name]
            if float(np.linalg.norm(offset)) > 1e-12:
                figure.shift(np.array([*offset, 0.0]))
            self.offsets[figure.name] = offset
            self.drawn[figure.name] = np.asarray(figure.feet(), dtype=float)[:2]
        if not walking:
            self.formation = self.drawn[self.b.name] - self.drawn[self.a.name]

    def update(self, now: float) -> None:
        """Pose both arms for scene time ``now`` (stepping in close enough first)."""
        share = min(max((now - self.start) / HAND_REACH_SECONDS, 0.0), 1.0)
        share = share * share * (3.0 - 2.0 * share)
        self._keep_close(share)
        sa, sb = self.a.shoulder_point(self.hands[0]), self.b.shoulder_point(self.hands[1])
        drop = HAND_DROP * max(self.a.standing_height, self.b.standing_height)
        meet = (np.asarray(sa) + np.asarray(sb)) / 2 - np.array([0.0, drop, 0.0])
        for figure, hand in zip((self.a, self.b), self.hands):
            target = figure.reached_parts(hand, meet)
            rest = self.rest[figure.name]
            parts = {name: _blend(rest.get(name, PartPose()), pose, share) for name, pose in target.items()}
            state = figure.state()
            figure.set_state(CharacterState(state.facing, {**state.parts, **parts}))

    def arms(self) -> list[tuple[Character, str]]:
        """Each character with the hand it holds with."""
        return [(self.a, self.hands[0]), (self.b, self.hands[1])]


def _nearer_hand(figure: Character, other: Character) -> str:
    """``figure``'s hand nearer ``other`` (``left`` or ``right``)."""
    there = np.asarray(other.feet(), dtype=float)[:2]
    found = [(float(np.linalg.norm(np.asarray(figure.hand_point(hand))[:2] - there)), hand) for hand in ("left", "right")]
    return min(found)[1]


def _arm_poses(figure: Character, hand: str) -> dict[str, PartPose]:
    """The poses of ``figure``'s arm of ``hand`` now (its upper and lower parts)."""
    names = figure.reached_parts(hand, figure.hand_point(hand)).keys()
    state = figure.state()
    return {name: state.parts.get(name, PartPose()) for name in names}


def _blend(a: PartPose, b: PartPose, share: float) -> PartPose:
    """``share`` of the way from pose ``a`` to ``b`` (angles; the rest of ``b``)."""
    return PartPose(a.angle + (b.angle - a.angle) * share, b.scale, b.shift, b.shape)


__all__ = [
    "AFTERIMAGE_LIFE",
    "AFTERIMAGE_OPACITY",
    "AFTERIMAGE_SPACING",
    "FIGURE_ALPHA",
    "HAND_DROP",
    "HAND_MIN_APART",
    "HAND_MIN_GAP",
    "HAND_REACH",
    "HAND_REACH_SECONDS",
    "Afterimages",
    "FigureAlpha",
    "HandHold",
    "Iridescence",
    "KISS_COLOR",
    "KissBurst",
    "KissMotion",
    "KissPlan",
    "Materialise",
    "PENDANT_PULSE",
    "PENDANT_SECONDS",
    "PendantPulse",
    "figure_alpha",
    "head_box",
    "pendant_level",
]
