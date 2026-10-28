"""Overlays of the ``orbit`` scene (Phase X, Step 230, DESIGN §98.4): the ellipse's geometry
(the empty focus and the centre, a and b, the apsides with their names), equal-time sectors
(Kepler's second law, each area computed), velocity vectors with a key and the speed from
vis-viva, Newton's cannonball, the side panel (readout and legend) and label placement without
overlaps (labels move with their bodies, with a leader line when pushed away). A mixin of
:class:`~vidgen.scenes.orbit.Orbit`; the physics is in :mod:`vidgen.orbits.laws`."""

import math
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Callable

import numpy as np

from vidgen.api import *

#: Extra distances (Manim units) a label may stand from its anchor, nearest first.
LABEL_RINGS = (0.0, 0.3, 0.65, 1.1)
#: Gap between a label and what it names.
LABEL_GAP = 0.06
#: The eight directions a label may take (right-up first, as before Step 230).
_SIDES = ((1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))
DIRECTIONS = tuple((x / math.hypot(x, y), y / math.hypot(x, y)) for x, y in _SIDES)
#: Width kept in the side panel for the velocity key's arrow.
KEY_WIDTH = 1.1
#: The longest velocity arrow as a share of the plot's shorter side.
ARROW_SHARE = 0.2
#: Sector fill opacities (two tints alternate with show: all).
SECTOR_OPACITY = (0.42, 0.2)
#: Samples along a sector's arc and a shot's path.
SECTOR_SAMPLES = 48
SHOT_SAMPLES = 220
#: At most this many sector areas are listed in the panel (the latest ones).
AREA_ROWS = 4
#: Subscript digits for A₁, A₂...
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


@dataclass
class Slot:
    """A row of the side panel: text (``probes`` size it; ``value`` gives it at a time), a
    colour ``swatch`` before it, or the velocity ``key`` (an arrow) before it."""

    probes: list[str]
    value: Callable[[float], str] | None = None
    color: str = "text"
    scale: float = 1.0
    swatch: str | None = None
    key: bool = False

    def text(self, t: float) -> str:
        return self.value(t) if self.value is not None else self.probes[0]


@dataclass
class Pinned:
    """A drawing fixed relative to a point that may move in the view (a satellite's orbit
    around a moving planet): its points are re-set from the ones it had at ``anchor``."""

    group: Any
    anchor: np.ndarray
    base: list[tuple[Any, np.ndarray]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base = [(m, m.points.copy()) for m in self.group.get_family() if len(m.points)]

    def move(self, anchor: np.ndarray) -> None:
        d = np.asarray(anchor, dtype=float) - self.anchor
        if not np.any(d):
            return
        for m, pts in self.base:
            if len(m.points) == len(pts):
                m.points = pts + d


def rect_at(center: Any, w: float, h: float) -> Any:
    return plotcore.Rect(center[0] - w / 2, center[1] - h / 2, center[0] + w / 2, center[1] + h / 2)


def overlap(a: Any, b: Any) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def mob_rect(m: Any, pad: float = 0.0) -> Any:
    return plotcore.Rect(m.get_left()[0] - pad, m.get_bottom()[1] - pad, m.get_right()[0] + pad, m.get_top()[1] + pad)


def place(anchor: Any, radius: float, w: float, h: float, *, obstacles: list[Any], plot: Any, points: np.ndarray | None = None,
          directions: tuple[tuple[float, float], ...] = DIRECTIONS, rings: tuple[float, ...] = LABEL_RINGS, prev: int | None = None,
          line_weight: float = 0.004) -> tuple[int, Any, float]:
    """The best place for a ``w`` × ``h`` label naming ``anchor`` (a dot of ``radius``): one of
    ``directions`` at one of ``rings`` further out, covering no obstacle (rectangles), staying
    in ``plot`` and covering few ``points`` (lines drawn there), nearest first; the candidate
    it had (``prev``) is kept while it is about as good (no jumping). Returns the candidate's
    index, its box and its ring."""
    cands = []
    for ring in rings:
        for dx, dy in directions:
            dist = radius + LABEL_GAP + ring
            c = (anchor[0] + dx * dist + dx * w / 2, anchor[1] + dy * dist + dy * h / 2)
            cands.append((rect_at(c, w, h), ring))
    pts = points if points is not None and len(points) else None
    best, best_cost, costs = 0, math.inf, []
    for k, (box, ring) in enumerate(cands):
        cost = 10 * sum(overlap(box, o) for o in obstacles) + 20 * (w * h - overlap(box, plot)) + 0.12 * ring + 0.002 * (k % len(directions))
        if pts is not None:
            inside = (pts[:, 0] > box.x0) & (pts[:, 0] < box.x1) & (pts[:, 1] > box.y0) & (pts[:, 1] < box.y1)
            cost += line_weight * float(np.count_nonzero(inside))
        costs.append(cost)
        if cost < best_cost:
            best, best_cost = k, cost
    if prev is not None and 0 <= prev < len(cands) and costs[prev] <= best_cost + 0.03:
        best = prev
    return best, cands[best][0], cands[best][1]


def leader_points(anchor: Any, radius: float, box: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """A leader from the edge of a dot at ``anchor`` to the nearest point of a label's ``box``
    (``None`` when they nearly touch)."""
    nx = min(max(anchor[0], box.x0), box.x1)
    ny = min(max(anchor[1], box.y0), box.y1)
    d = np.array([nx - anchor[0], ny - anchor[1]])
    length = float(np.hypot(*d))
    if length <= radius + 0.12:
        return None
    u = d / length
    start = np.array([anchor[0] + u[0] * (radius + 0.03), anchor[1] + u[1] * (radius + 0.03), 0.0])
    return start, np.array([nx - u[0] * 0.04, ny - u[1] * 0.04, 0.0])


def arrow_shape(shaft: Any, tip: Any, start: np.ndarray, vec: np.ndarray, width: float) -> None:
    """Make ``shaft`` (a line) and ``tip`` (a filled triangle) an arrow from ``start`` along
    ``vec`` (frame units); empty when it is too short to see."""
    length = float(np.hypot(vec[0], vec[1]))
    if length < 0.02:
        shaft.clear_points()
        tip.clear_points()
        return
    u = np.array([vec[0], vec[1], 0.0]) / length
    n = np.array([-u[1], u[0], 0.0])
    tip_len = min(0.16, 0.45 * length) * width / 4
    end = np.array([start[0] + vec[0], start[1] + vec[1], 0.0])
    base = end - u * tip_len
    shaft.set_points_as_corners(np.array([np.asarray(start, dtype=float), base]))
    tip.set_points_as_corners(np.array([end, base + n * tip_len * 0.55, base - n * tip_len * 0.55, end]))


def new_arrow(color: str, width: float = 4.0, z: float = 3.5) -> VGroup:
    shaft = VMobject().set_stroke(color, width=width, opacity=1.0)
    tip = VMobject().set_fill(color, opacity=1.0).set_stroke(color, width=1, opacity=1.0)
    return VGroup(shaft, tip).set_z_index(z)


def round_speed(limit: float) -> float:
    """The largest 1-2-5 × 10ⁿ speed (m/s) not above ``limit``."""
    k = math.floor(math.log10(limit))
    return max(m * 10.0**k for m in (1, 2, 5) if m * 10.0**k <= limit * (1 + 1e-12))


def speed_text(v: float) -> str:
    return plotcore.readout_number(v / 1000, 3) + " km/s"


class OrbitOverlays:
    """The overlays of an ``orbit`` scene (mixed into the scene class)."""

    # ----- text ---------------------------------------------------------------------------------

    def _length_text(self, metres: float) -> str:
        if self._unit_name == "AU":
            return plotcore.readout_number(metres / orbits.AU, 3) + " AU"
        km = metres / 1000
        return f"{km:,.0f} km" if km < 1e7 else plotcore.readout_number(km, 3) + " km"

    def _area_text(self, m2: float) -> str:
        if self._unit_name == "AU":
            return plotcore.readout_number(m2 / orbits.AU**2, 4) + " AU²"
        return plotcore.readout_number(m2 / 1e6, 4) + " km²"

    def _time_text(self, seconds: float) -> str:
        unit, scale = orbits.time_unit(seconds)
        return plotcore.readout_number(seconds / scale, 3) + f" {unit}"

    def _small_label(self, text: str, color: str = "text", scale: float = 0.9) -> Mobject:
        return plot_draw.label_text(text, size=self._size * scale, color=color, theme=self.theme).set_z_index(5)

    def _shot_palette(self) -> list[str]:
        """A colour per shot by its kind (falling back red, circular, elliptical, parabolic,
        hyperbolic), later shots of a kind lighter."""
        theme = self.theme
        base = {"suborbital": theme.color("accent"), "circular": theme.palette_color(0), "elliptical": theme.palette_color(2),
                "parabolic": theme.palette_color(3), "hyperbolic": theme.color("highlight")}
        seen: dict[str, int] = {}
        out = []
        for shot in self._model.shots:
            j = seen.get(shot.kind, 0)
            seen[shot.kind] = j + 1
            out.append(interpolate_color(ManimColor(base[shot.kind]), ManimColor(theme.color("text")), min(0.3 * j, 0.6)).to_hex())
        return out

    # ----- what is held back for an action ------------------------------------------------------

    def _held_patterns(self) -> set[str]:
        """Target names a ``reveal``, ``sweep`` or ``launch`` of this scene brings on screen
        (they start hidden; everything else enters with the first beat)."""
        return {t for kind in ("reveal", "sweep", "launch") for use in self.action_uses(kind) for t in use.config.targets()}

    def _is_held(self, names: list[str]) -> bool:
        return any(fnmatchcase(n, pat) for n in names for pat in self._held)

    # ----- the side panel -----------------------------------------------------------------------

    def _overlay_slots(self) -> list[Slot]:
        """Panel rows of the overlays: e and the speeds of each body, the velocity key, the
        sectors' Δt and areas, the cannon's speeds and shots, the bodies' legend."""
        p, model = self.params, self._model
        slots: list[Slot] = []
        bodies = list(zip(p.body_specs(), model.system.orbiters))
        many = len(bodies) > 1
        for spec, o in bodies:
            el = o.elements
            prefix = f"{o.name}: " if many else ""
            if spec.geometry_parts():
                slots.append(Slot([f"{prefix}e = {plotcore.readout_number(el.e, 3) if el.e else '0'}"]))
            vel = spec.velocity_spec()
            if vel is not None and vel.readout:
                peri, apo = orbits.apsis_names(model.system.parent_body(o).name)
                fast = el.speed_at(0.0)
                slots.append(Slot([f"{prefix}v = {speed_text(fast)}", f"{prefix}v = {speed_text(fast * 0.999)}"], value=self._speed_value(o, prefix)))
                slots.append(Slot([f"max {speed_text(fast)} at {peri}"], color="dim", scale=0.85))
                if el.closed:
                    slots.append(Slot([f"min {speed_text(el.speed_at(math.pi))} at {apo}"], color="dim", scale=0.85))
            sec = spec.sector_spec()
            if sec is not None:
                dt = el.period / sec.count
                slots.append(Slot([f"{prefix}Δt = {self._time_text(dt)} each"]))
                area = math.pi * el.a * el.b / sec.count
                rows = min(sec.count if sec.show == "all" else math.ceil(sec.count / 2), AREA_ROWS)
                widest = f"A{str(sec.count).translate(_SUB)} = {self._area_text(area * 1.0001)}"
                for row in range(rows):
                    slots.append(Slot([widest], value=self._area_value(o.name, row, rows), scale=0.9))
        if any(spec.velocity_spec() is not None for spec, _ in bodies):
            slots.append(Slot(["10 km/s"], value=lambda t: speed_text(self._key_speed), key=True, color="dim", scale=0.85))
        if model.shots:
            r0 = float(np.linalg.norm(model.cannon_at))
            mu = model.system.central.gm
            slots.append(Slot([f"circular {speed_text(orbits.circular_speed(mu, r0))}"], color="dim", scale=0.85))
            slots.append(Slot([f"escape {speed_text(orbits.escape_speed(mu, r0))} = √2 × circular"], color="dim", scale=0.85))
            for k, shot in enumerate(model.shots):
                slots.append(Slot([f"{speed_text(shot.speed)}  {shot.kind}"], swatch=self._shot_colors[k], scale=0.9))
        if self._legend_wanted():
            for text, color in self._many_legend_first():
                slots.append(Slot([text], swatch=color, scale=0.9))
            for spec, o in bodies:
                el = o.elements
                many = self._many_legend(o)   # Step 232: a body of a three-body system or the figure-eight
                if many is not None:
                    text = many
                elif o.trajectory is not None:   # its orbit changes with its burns
                    count = len(o.trajectory.burns)
                    text = f"{o.name}  {count} burn{'s' if count > 1 else ''}"
                else:
                    text = f"{o.name}  T = {self._time_text(el.period)}" if el.closed else f"{o.name}  {el.kind}, e = {el.e:.3g}"
                slots.append(Slot([text], swatch=self._colors[o.name], scale=0.9))
        return slots

    def _many_legend(self, o: Any) -> str | None:
        """A legend row of the many-body mixin (``None``: the usual one)."""
        return None

    def _many_legend_first(self) -> list[tuple[str, str]]:
        """Legend rows (text, colour) the many-body mixin puts before the bodies' (the central body
        when it moves too)."""
        return []

    def _legend_wanted(self) -> bool:
        legend = self.params.legend
        if legend == "auto":   # a vertical frame with a manoeuvre keeps its rows for the numbers (labels name the bodies)
            many = self._model.many is not None and (self._model.many.restricted is not None or self._model.many.resonance is not None)
            busy = self.is_portrait and (self._model.transfer is not None or bool(self._model.burns()) or many)
            return len(self._model.system.orbiters) >= 2 and not busy
        return bool(legend)

    def _speed_value(self, o: Any, prefix: str) -> Callable[[float], str]:
        def value(t: float) -> str:
            v = float(np.linalg.norm(o.states(t)[1]))
            return f"{prefix}v = {speed_text(v)}"
        return value

    def _area_value(self, name: str, row: int, rows: int) -> Callable[[float], str]:
        def value(t: float) -> str:
            done = self._areas_done(name, t)
            shown = done[-rows:]
            if row >= len(shown):
                return ""
            n, area = shown[row]
            return f"A{str(n).translate(_SUB)} = {self._area_text(area)}"
        return value

    # ----- building -----------------------------------------------------------------------------

    def _build_orbit_overlays(self) -> None:
        """Geometry, sectors, velocity arrows and the cannon, registered as targets (held back
        when an action brings them in)."""
        p, model = self.params, self._model
        self._held = self._held_patterns()
        self._pins: list[tuple[str | None, Pinned]] = []
        self._static_boxes: list[Any] = []
        self._geometry: dict[str, dict[str, VGroup]] = {}
        self._sectors: dict[str, dict[str, Any]] = {}
        self._velocity: dict[str, dict[str, Any]] = {}
        self._sweep_video: dict[str, float] = {}
        self._launch_video: dict[int, float] = {}
        self._intro_parts: list[Mobject] = []
        speeds = [o.elements.speed_at(0.0) for spec, o in zip(p.body_specs(), model.system.orbiters) if spec.velocity_spec() is not None]
        plot = self._lay.plot
        if speeds:
            self._speed_scale = ARROW_SHARE * min(plot.width, plot.height) / max(speeds)   # frame units per m/s
            self._key_speed = round_speed(min(KEY_WIDTH / self._speed_scale, 0.6 * max(speeds)))
        for spec, o in zip(p.body_specs(), model.system.orbiters):
            if spec.geometry_parts():
                self._build_geometry(spec, o)
            if spec.sector_spec() is not None:
                self._build_sectors(spec, o)
            if spec.velocity_spec() is not None:
                self._build_velocity(spec, o)
        if model.shots:
            self._build_cannon()

    def _anchor(self, parent: str | None, t: float = 0.0) -> np.ndarray:
        model = self._model
        name = parent if parent is not None else model.system.central.name
        return self._frame_point(model.view(name, t))

    def _offsets(self, metres: np.ndarray) -> np.ndarray:
        """Frame offsets of points given in metres relative to a parent (x, y projected)."""
        pts = np.atleast_2d(np.asarray(metres, dtype=float))
        return np.column_stack([pts[:, 0] * self._scale, pts[:, 1] * self._scale, np.zeros(len(pts))])

    def _moving(self, parent: str | None) -> bool:
        """Whether a body's parent moves in the view (its overlays then move with it)."""
        model = self._model
        return model.run is not None or parent != model.follow

    def _register_overlay(self, names: list[str], group: Mobject, parent: str | None, *, pin: bool = True) -> None:
        self.target(names, group)
        if not self._is_held(names):
            self._intro_parts.append(group)
        if pin and self._moving(parent):
            self._pins.append((parent, Pinned(group, self._anchor(parent))))

    def _build_geometry(self, spec: Any, o: Any) -> None:
        geo = orbits.ellipse_geometry(o.elements)
        parent_body = self._model.system.parent_body(o)
        anchor = self._anchor(o.parent)
        pt = lambda m: anchor + self._offsets(m)[0]   # noqa: E731
        dim = self.theme.color("dim")
        color = self._colors[o.name]
        u = np.array([geo.p_hat[0], geo.p_hat[1]])
        u = u / np.hypot(*u) if np.hypot(*u) > 1e-9 else np.array([1.0, 0.0])
        n = np.array([-u[1], u[0]])
        obstacles = [self._panel_rect()] if self._readout_box is not None else []
        obstacles.append(mob_rect(self._central[0], 0.04))
        lay = self._lay   # the axes' labels; the labels may stand outside the plot, within the picture's area
        obstacles += [rect_at((lab.x, lab.y), lab.width + 0.08, lab.height + 0.08)
                      for lab in (*lay.x_labels, *lay.y_labels, *[t for t in (lay.x_title, lay.y_title) if t is not None])]
        parts: dict[str, VGroup] = {}
        # the lines a label should not sit on: the ellipse, its major axis and the semi-minor axis
        s = np.linspace(0.0, 1.0, 80)[:, None]
        lines = [anchor + self._offsets(o.elements.conic(240))]
        lines.append(pt(geo.periapsis_point) + s * (pt(geo.apoapsis_point) - pt(geo.periapsis_point)))
        lines.append(pt(geo.centre) + s * (pt(geo.minor_point) - pt(geo.centre)))
        line_pts = np.concatenate(lines)[:, :2]

        def label(text: str, at: np.ndarray, dirs: list[np.ndarray], colour: str = "text", radius: float = 0.05) -> Mobject:
            lab = self._small_label(text, colour)
            _, box, _ = place(at, radius, lab.width, lab.height, obstacles=obstacles, plot=self._picture_area, points=line_pts, line_weight=0.05,
                              directions=tuple((float(d[0]), float(d[1])) for d in dirs) + DIRECTIONS, rings=(0.0, 0.25, 0.55))
            lab.move_to([box.center[0], box.center[1], 0])
            obstacles.append(box)
            self._static_boxes.append(box)
            return lab

        if "axes" in spec.geometry_parts():
            peri, apo, centre, minor = pt(geo.periapsis_point), pt(geo.apoapsis_point), pt(geo.centre), pt(geo.minor_point)
            major = DashedLine(peri, apo, dash_length=0.1, dashed_ratio=0.5).set_stroke(dim, width=2, opacity=0.8)
            semi_a = Line(centre, apo).set_stroke(color, width=3.5, opacity=0.95)
            semi_b = Line(centre, minor).set_stroke(color, width=3.5, opacity=0.95)
            ticks = VGroup(*[Line(q - np.array([*n * 0.06, 0]), q + np.array([*n * 0.06, 0])).set_stroke(color, width=2.5) for q in (centre, apo)])
            mid_a, mid_b = (centre + apo) / 2, (centre + minor) / 2
            v = np.array([geo.q_hat[0], geo.q_hat[1]])
            v = v / np.hypot(*v) if np.hypot(*v) > 1e-9 else n
            la = label(f"a = {self._length_text(geo.a)}", mid_a, [n, -n, u, -u])
            lb = label(f"b = {self._length_text(geo.b)}", mid_b, [-u, u, v, -v])
            parts["axes"] = VGroup(major, semi_a, semi_b, ticks, la, lb).set_z_index(1.5)
        if "foci" in spec.geometry_parts():
            f2, centre = pt(geo.empty_focus), pt(geo.centre)
            ring = Circle(radius=0.06).set_stroke(color, width=3).set_fill(opacity=0).move_to(f2)
            cross = VGroup(Line(centre + [-0.07, -0.07, 0], centre + [0.07, 0.07, 0]), Line(centre + [-0.07, 0.07, 0], centre + [0.07, -0.07, 0]))
            cross.set_stroke(dim, width=3)
            lf = label("F′ (empty focus)" if geo.e > 0.05 else "F′", f2, [n, -n, -u, u])
            lc = label("C", centre, [-n, n, u, -u], "dim")
            parts["foci"] = VGroup(ring, cross, lf, lc).set_z_index(1.6)
        if "apsides" in spec.geometry_parts():
            names = orbits.apsis_names(parent_body.name)
            marks = VGroup()
            for k, (where, dist, sign) in enumerate(((geo.periapsis_point, geo.q, 1.0), (geo.apoapsis_point, geo.big_q, -1.0))):
                at = pt(where)
                text = f"{names[k]} {self._length_text(dist)}"
                if self._unit_name == "km" and parent_body.radius > 0:
                    text += f" ({self._length_text(dist - parent_body.radius)} up)"
                dot = Dot(at, radius=0.055, color=self.theme.color("highlight")).set_z_index(3.8)
                lab = label(text, at, [sign * u, n, -n, -sign * u], radius=0.07)
                group = VGroup(dot, lab)
                marks.add(group)
                names_k = [f"{'periapsis' if k == 0 else 'apoapsis'}:{o.name}"]
                self._register_overlay(names_k, group, o.parent)
            parts["apsides"] = marks
        for key, group in parts.items():
            if key != "apsides":
                self._register_overlay([f"{key}:{o.name}"], group, o.parent)
        whole = VGroup(*parts.values())
        self.target(f"geometry:{o.name}", whole)
        self._geometry[o.name] = parts

    def _build_sectors(self, spec: Any, o: Any) -> None:
        sec = spec.sector_spec()
        color = self._colors[o.name]
        polys = []
        for k in range(sec.count):
            if sec.show == "alternate" and k % 2:
                continue
            poly = VMobject().set_fill(color, opacity=SECTOR_OPACITY[k % 2 if sec.show == "all" else 0]).set_stroke(color, width=1.2, opacity=0.6)
            polys.append((k, poly.set_z_index(0.5)))
        group = VGroup(*[m for _, m in polys])
        self._sectors[o.name] = {"spec": sec, "polys": polys, "group": group}
        self.target(f"sectors:{o.name}", group)
        if not self._is_held([f"sectors:{o.name}"]):
            self._intro_parts.append(group)
            self._sweep_video[o.name] = None   # swept from the start of the motion

    def _build_velocity(self, spec: Any, o: Any) -> None:
        vel = spec.velocity_spec()
        color = self.theme.color("text")   # arrows in the text colour: they stand out from the orbit and trail
        live = new_arrow(color) if vel.live else None
        along = VGroup()
        if vel.along and o.elements.closed:
            anchor = self._anchor(o.parent)
            ts = np.linspace(0.0, o.elements.period, vel.along, endpoint=False)
            pos, v = o.elements.states(ts)
            for r, vv in zip(np.atleast_2d(pos), np.atleast_2d(v)):
                arrow = new_arrow(color, width=3.0, z=1.8)
                arrow.set_opacity(0.7)
                start = anchor + self._offsets(r)[0]
                arrow_shape(arrow[0], arrow[1], start, np.array([vv[0], vv[1]]) * self._speed_scale, 3.0)
                along.add(arrow)
        group = VGroup(*([live] if live is not None else []), along)
        self._velocity[o.name] = {"live": live, "along": along}
        self.target(f"velocity:{o.name}", group)
        if not self._is_held([f"velocity:{o.name}"]):
            self._intro_parts.append(group)
        if len(along) and o.parent is not None and self._moving(o.parent):
            self._pins.append((o.parent, Pinned(along, self._anchor(o.parent))))

    def _build_cannon(self) -> None:
        model = self._model
        centre = self._anchor(None)
        at = model.cannon_at
        r0 = float(np.linalg.norm(at))
        radius = model.system.central.radius
        u = at / r0
        n = np.array([-u[1], u[0], 0.0])
        top = centre + self._offsets(at)[0]
        base = centre + self._offsets(u * radius * 0.995)[0]
        half = max(0.6 * float(np.linalg.norm(top - base)), 0.08)
        mountain = Polygon(base + n * half, top, base - n * half).set_fill(self.theme.color("dim"), opacity=0.75).set_stroke(width=0).set_z_index(3.2)
        aim = np.array([u[1], -u[0], 0.0]) if self.params.cannonball.clockwise else -np.array([u[1], -u[0], 0.0])
        barrel = Line(top, top + aim * 0.22).set_stroke(self.theme.color("text"), width=6).set_z_index(3.3)
        cannon = VGroup(mountain, barrel)
        self._static_boxes.append(mob_rect(cannon, 0.05))   # labels keep off the cannon
        self._shot_parts = []
        for k, shot in enumerate(model.shots):
            color = self._shot_colors[k]
            path = VMobject().set_stroke(color, width=3.5, opacity=0.95).set_z_index(2)
            ball = Circle(radius=0.055).set_fill(color, opacity=1).set_stroke(self.theme.background, width=1.5).set_z_index(4).move_to(top)
            hit = VGroup(Line([-0.08, -0.08, 0], [0.08, 0.08, 0]), Line([-0.08, 0.08, 0], [0.08, -0.08, 0])).set_stroke(color, width=4).set_z_index(4)
            hit.set_opacity(0)
            if self.params.cannonball.show_paths:   # the paths to come, faint, with the cannon
                end = shot.impact if shot.impact is not None else (shot.elements.period if shot.elements.closed else None)
                ts = np.linspace(0.0, end, SHOT_SAMPLES) if end is not None else None
                pts = shot.elements.positions(ts) if ts is not None else shot.elements.conic(SHOT_SAMPLES, r_max=4 * r0)
                if ts is None:   # an open shot from the cannon outwards
                    pts = pts[len(pts) // 2:]
                preview = plot_draw.series_line(centre + self._offsets(pts), self._lay.plot, color, width=2, dashed=True)
                cannon.add(preview.set_stroke(opacity=0.35).set_z_index(1))
            group = VGroup(path, ball, hit)
            self._shot_parts.append({"path": path, "ball": ball, "hit": hit})
            self.target(f"shot:{k + 1}", group)
            if not self._is_held([f"shot:{k + 1}"]):
                self._intro_parts.append(group)
                self._launch_video[k] = None   # fired as the motion starts
        self.target("cannon", cannon)
        self._intro_parts.append(cannon)

    # ----- actions --------------------------------------------------------------------------------

    def start_sweep(self, names: list[str], video_time: float) -> None:
        """``sweep``: the named bodies' sectors start being swept at scene time ``video_time``."""
        for name in names:
            self._sweep_video[name] = video_time

    def launch(self, shots: list[int], video_time: float) -> None:
        """``launch``: the shots (0-based) are fired at scene time ``video_time``."""
        for k in shots:
            self._launch_video[k] = video_time

    def _sim_at(self, video_time: float | None) -> float:
        """The simulated time at scene time ``video_time`` (``None``: when the motion starts)."""
        if video_time is None or self._playback is None:
            return 0.0
        return self._playback.sim_time(video_time)

    def _sweep_start(self, name: str) -> float | None:
        """When ``name``'s sectors start (simulated s), ``None`` before its ``sweep``."""
        return self._sim_at(self._sweep_video[name]) if name in self._sweep_video else None

    def _launch_time(self, k: int) -> float | None:
        """When shot ``k`` is fired (simulated s), ``None`` before its ``launch``."""
        return self._sim_at(self._launch_video[k]) if k in self._launch_video else None

    # ----- per frame -------------------------------------------------------------------------------

    def _draw_orbit_overlays(self, t: float, anchors: dict[str, np.ndarray]) -> None:
        model = self._model
        centre = model.system.central.name
        for parent, pin in self._pins:
            pin.move(self._frame_point(anchors[parent if parent is not None else centre]))
        for name, info in self._sectors.items():
            o = model.system.orbiter(name)
            focus = self._frame_point(anchors[o.parent if o.parent is not None else centre])
            start = self._sweep_start(name)
            el = o.elements
            dt = el.period / info["spec"].count
            for k, poly in info["polys"]:
                a = None if start is None else start + k * dt
                if a is None or t <= a + 1e-9 * dt:
                    poly.clear_points()
                    continue
                b = min(t, a + dt)
                ts = np.linspace(a, b, SECTOR_SAMPLES + 1)
                arc = focus + self._offsets(el.positions(ts))
                poly.set_points_as_corners(np.vstack([focus, arc, focus]))
        for name, info in self._velocity.items():
            live = info["live"]
            if live is None:
                continue
            o = model.system.orbiter(name)
            v = o.states(t)[1]
            start = self._frame_point(anchors[name])
            arrow_shape(live[0], live[1], start, np.array([v[0], v[1]]) * self._speed_scale, 4.0)
        for k, parts in enumerate(getattr(self, "_shot_parts", [])):
            self._draw_shot(k, parts, t, anchors)

    def _areas_done(self, name: str, t: float) -> list[tuple[int, float]]:
        """The sectors of ``name`` swept completely by time ``t``: (number, area)."""
        info = self._sectors[name]
        o = self._model.system.orbiter(name)
        start = self._sweep_start(name)
        if start is None:
            return []
        dt = o.elements.period / info["spec"].count
        if info.get("start") != start:   # the areas of the sectors swept from this start, from the geometry
            info["start"], info["areas"] = start, orbits.sector_areas(o.elements, info["spec"].count, start)
        return [(k + 1, float(info["areas"][k])) for k, _ in info["polys"] if t >= start + (k + 1) * dt - 1e-9 * dt]

    def _draw_shot(self, k: int, parts: dict[str, Any], t: float, anchors: dict[str, np.ndarray]) -> None:
        model = self._model
        shot = model.shots[k]
        plot = self._lay.plot
        launch = self._launch_time(k)
        path, ball, hit = parts["path"], parts["ball"], parts["hit"]
        if launch is None or t < launch:
            path.clear_points()
            ball.set_opacity(0)
            return
        end = t - launch if shot.impact is None else min(t - launch, shot.impact)
        ts = launch + np.linspace(0.0, end, SHOT_SAMPLES)
        pts = self._frame_points(model.shot_view(k, ts, launch))
        path.clear_points()
        for run in plotcore.clip_polyline(pts, plot):
            if len(run) >= 2:
                path.start_new_path(run[0])
                path.add_points_as_corners(run[1:])
        head = pts[-1]
        inside = plot.contains(float(head[0]), float(head[1]), 1e-6)
        ball.move_to(head)
        ball.set_opacity(1.0 if inside else 0.0)
        landed = shot.impact is not None and t - launch >= shot.impact
        hit.move_to(head)
        hit.set_stroke(opacity=1.0 if landed else 0.0)

    def _panel_rect(self) -> Any:
        box = self._readout_box
        return plotcore.Rect(box.x0, box.y0, box.x1, box.y1)


__all__ = ["DIRECTIONS", "LABEL_RINGS", "OrbitOverlays", "Pinned", "Slot", "arrow_shape", "leader_points", "place", "round_speed"]
