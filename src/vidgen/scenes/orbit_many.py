"""Many bodies on the ``orbit`` scene (Phase X, Step 232, DESIGN §98.6): a restricted three-body
pair seen in the inertial or the rotating frame (switched on a word by ``corotate`` /
``inertial``), its Lagrange points, zero-velocity curves, the Jacobi constant and co-orbital
motion in the panel; the figure-eight and binary stars about their barycentre; resonances with
their conjunctions; which way a path bends; a close-up with an arrow to the central body; and the
tidal schematic. A mixin of :class:`~vidgen.scenes.orbit.Orbit`; the physics is in
:mod:`vidgen.orbits.threebody` and :mod:`vidgen.orbits.manybody`."""

import math
from typing import Any

import numpy as np

from vidgen.api import *

from .orbit_overlays import DIAGNOSTIC, DIRECTIONS, Slot, arrow_shape, choose_rows, mob_rect, new_arrow, place

#: Seconds a frame switch takes when its action gives no run_time.
SWITCH_SECONDS = 2.0
#: Grid cells of a zero-velocity curve along the longer side.
ZV_CELLS = 520
#: Where Lagrange labels stand from their mark (frame units) when the point sits on what it is
#: measured from (otherwise they stand away from it: L1 / L2 from the secondary, the rest from
#: the barycentre).
LAGRANGE_LABEL = {"L1": (0.0, -0.24), "L2": (0.0, -0.24), "L3": (0.0, -0.24), "L4": (0.0, 0.24), "L5": (0.0, -0.24)}
#: A conjunction's line is bright for this share of the pair's synodic period, then faint.
CONJUNCTION_BRIGHT = 0.25
#: The tidal schematic: the planet's radius, the satellite's orbit and radius as shares of the
#: canvas' shorter side; the longest pull and tidal arrows (units); the bulge's stretch.
TIDE_PLANET = 0.2
TIDE_ORBIT = 0.41
TIDE_MOON = 0.055
TIDE_PULL = 0.55
TIDE_ARROW = 0.5
TIDE_BULGE = 0.17


def many_target_names(params: Any) -> tuple[list[str], set[str]]:
    """The many-body targets of an ``orbit`` scene and the ``orbit:<name>`` targets it does not
    draw (in the barycentre's view a body's Kepler orbit is not its path)."""
    model = params.model()
    info = model.many
    if info is None:
        return [], set()
    if info.tides is not None:
        return ["pull", "mean", "tidal", "bulges"] + (["face"] if info.tides.locking else []), set()
    names: list[str] = []
    drop: set[str] = set()
    if info.origin == "barycentre":
        drop = {o.name for o in model.system.orbiters}
        keep = set(binary_names(model))
        r = info.restricted
        if r is not None:
            keep.add(r.secondary)
        drop -= keep
        if keep and model.system.central.name in keep:
            names.append(f"orbit:{model.system.central.name}")
        if info.eight is not None or binary_names(model):
            names.append("barycentre")
    if info.lagrange:
        names += ["lagrange", *[f"lagrange:{k}" for k in info.lagrange]]
    if info.zero_velocity is not None:
        names.append("zero_velocity")
    if info.restricted is not None:
        names.append("rotation")
    if info.resonance is not None and info.resonance.show:
        names.append("conjunctions")
    if info.center is not None:
        names.append("pointer")
    return names, drop


def binary_names(model: Any) -> list[str]:
    """The two stars of a binary (Kepler orbits about their barycentre: the central body and one
    massive orbiter), else nothing."""
    info = model.many
    if info is None or info.origin != "barycentre" or model.run is not None:
        return []
    massive = [o for o in model.system.orbiters if o.body.gm > 0]
    if len(massive) != 1 or massive[0].parent is not None:
        return []
    return [model.system.central.name, massive[0].name]


def _big_length(metres: float) -> str:
    km = metres / 1000
    if km < 1e6:
        return f"{km:,.0f} km"
    if km < 1e8:
        return f"{km / 1e6:#.3g}".rstrip(".") + " million km"
    return plotcore.readout_number(metres / orbits.AU, 3) + " AU"


def _deg(x: float) -> str:
    return f"{x:.1f}°".replace("-", "−")


class OrbitMany:
    """Many-body overlays of an ``orbit`` scene (mixed into the scene class)."""

    # ----- the view ------------------------------------------------------------------------------

    def _turn_plan(self) -> list[tuple[float, float, float]]:
        """The frame switches on words: (video start, seconds, turn to), in time order."""
        out = []
        for kind, target in (("corotate", 1.0), ("inertial", 0.0)):
            for act, when, _ in self.action_times(kind, self._begin):
                out.append((when, float(act.config.run_time or SWITCH_SECONDS), target))
        return sorted(out)

    def _turn_at(self, video: float) -> float:
        info = self._model.many
        turn = info.turn0
        for start, seconds, target in self._switches:
            if video < start:
                break
            s = min(1.0, (video - start) / max(seconds, 1e-9))
            s = s * s * (3 - 2 * s)   # smooth in and out
            turn = turn + (target - turn) * s if s < 1 else target
        return turn

    def _many_turns(self) -> list[float]:
        info = self._model.many
        return sorted({info.turn0, *[target for _, _, target in self._switches]})

    def _many_extent_points(self) -> tuple[np.ndarray, np.ndarray] | None:
        """What the view must show in the barycentre's view: every body's path in each view the
        scene uses (inertial, rotating), the Lagrange points shown; ``None``: the usual extent."""
        model = self._model
        info = model.many
        if info is None or info.origin != "barycentre":
            return None
        ts = np.linspace(0.0, model.span, 600)
        pts = [np.zeros((1, 3))]
        keep = model.turn
        for turn in self._many_turns():
            model.turn = turn
            for name in [model.system.central.name, *model.system.names]:
                pts.append(model.view(name, ts))
            if info.lagrange:
                pts.append(model.from_rotating(np.array([[*info.restricted.pair.points()[k], 0.0] for k in info.lagrange])[:, :2], 0.0))
        model.turn = keep
        for name in binary_names(model):   # a binary's ellipses whole
            pts.append(self._binary_points(name))
        allp = np.concatenate(pts)
        if info.restricted is not None and len(self._many_turns()) > 1:   # a switch: the disc both views fill
            reach = float(np.max(np.linalg.norm(allp[:, :2], axis=1)))
            ring = np.linspace(0, 2 * math.pi, 73)
            allp = np.column_stack([reach * np.cos(ring), reach * np.sin(ring), 0 * ring])
        return allp[:, 0], allp[:, 1]

    def _binary_points(self, name: str) -> np.ndarray:
        """A binary star's ellipse about the barycentre (m)."""
        model = self._model
        star = binary_names(model)[1]
        o = model.system.orbiter(star)
        rel = o.elements.conic(360)
        gm_a, gm_b = model.system.central.gm, o.body.gm
        share = gm_a / (gm_a + gm_b) if name == star else -gm_b / (gm_a + gm_b)
        return rel * share

    # ----- the panel ---------------------------------------------------------------------------------

    def _many_slots(self) -> list[Slot]:
        model = self._model
        info = model.many
        if info is None or info.tides is not None:
            return []
        slots: list[Slot] = []
        r = info.restricted
        if r is not None:
            pair = r.pair
            sec = r.secondary
            stable = orbits.routh_stable(pair.mu)
            slots.append(Slot([f"{r.primary}–{sec}: μ = {plotcore.readout_number(pair.mu, 3)}"], scale=0.9, name="mu", rank=0))
            trojan = any(k in info.lagrange for k in ("L4", "L5")) or any(v in ("L4", "L5") for v in info.near.values())
            slots.append(Slot([f"μ {'<' if stable else '>'} 0.0385: L4, L5 {'stable' if stable else 'unstable'} (Routh)"], color="dim", scale=0.85,
                              name="routh", rank=0 if trojan else 2))
            period = self._time_text(pair.period)
            probes = [f"rotating frame: one turn / {period}", "inertial frame (fixed stars)", "turning with the pair…"]
            slots.append(Slot(probes, value=lambda t: self._frame_text(period), color="highlight", scale=0.85, name="frame", rank=0))
            dist = pair.distances()
            shown = [k for k in ("L1", "L2") if k in info.lagrange]
            if shown:
                texts = [_big_length(dist[k]) for k in shown]
                unit = texts[0].split(" ", 1)[1]
                both = " / ".join(x.split(" ", 1)[0] for x in texts) + f" {unit}" if all(x.split(" ", 1)[1] == unit for x in texts) else " / ".join(texts)
                slots.append(Slot([f"{' / '.join(shown)}: {both} from {sec}"], scale=0.85, name="l1_l2", rank=0 if not trojan else 2))
            many = len(info.near) > 1
            for name in info.near:
                prefix = f"{name}: " if many else ""
                series = info.jacobi[name]
                probes = [f"{prefix}C = {series[0]:.6f}, ΔC/C = {plotcore.readout_number(-1.23e-10, 2)}"]
                slots.append(Slot(probes, value=self._jacobi_value(name, prefix), scale=0.85, name="jacobi", rank=DIAGNOSTIC))
                kind, lo, hi = info.coorbital[name]
                probes = [self._angle_text(name, a) for a in (-179.9, 179.9)]
                slots.append(Slot(probes, value=lambda t, n=name: self._angle_text(n, self._ahead(n, t)), scale=0.85, name="angle", rank=1))
                slots.append(Slot([self._kind_text(kind, lo, hi)], color="dim", scale=0.85, name="coorbital", rank=0))
        if info.eight is not None:
            slots.append(Slot([f"figure-eight: T = {self._time_text(info.eight.period)}"], scale=0.9, name="eight", rank=0))
            if info.closure is not None:
                slots.append(Slot([f"back at the start after T (± {plotcore.readout_number(info.closure, 1)})"], color="dim", scale=0.85,
                                  name="closure", rank=DIAGNOSTIC))
        stars = binary_names(model)
        if stars:
            a, b = stars
            gm_a, gm_b = model.system.central.gm, model.system.orbiter(b).body.gm
            share_a, _ = orbits.binary_shares(gm_a, gm_b)
            slots.append(Slot([f"mass ratio {b}/{a} = {plotcore.readout_number(gm_b / gm_a, 3)}"], scale=0.9, name="mass_ratio", rank=0))
            slots.append(Slot([f"barycentre {share_a:.0%} of the way from {a}"], color="dim", scale=0.85, name="barycentre", rank=0))
            slots.append(Slot([f"both go round it in T = {self._time_text(model.system.orbiter(b).elements.period)}"], color="dim", scale=0.85,
                              name="binary_period", rank=1))
        res = info.resonance
        if res is not None:
            for (a, ta), (b, tb) in zip(zip(res.bodies, res.periods), list(zip(res.bodies, res.periods))[1:]):
                ratio = tb / ta
                frac = orbits.nearest_ratio(ratio)
                slots.append(Slot([f"T {b} / T {a} = {ratio:.4f} ≈ {frac.numerator}:{frac.denominator}"], scale=0.85, name="ratios", rank=0))
            if len(res.bodies) == 3 and all(orbits.nearest_ratio(tb / ta) == 2 for ta, tb in zip(res.periods, res.periods[1:])):
                slots.append(Slot(["Laplace angle φ = 359.9°"], value=self._laplace_value(), scale=0.9, name="laplace", rank=0))
                b1, b2, b3 = res.bodies
                slots.append(Slot([f"φ = λ {b1} − 3 λ {b2} + 2 λ {b3}"], color="dim", scale=0.8, name="laplace_formula", rank=2))
            if res.show:
                for k, ((a, _), (b, _)) in enumerate(zip(zip(res.bodies, res.periods), list(zip(res.bodies, res.periods))[1:])):
                    n_max = len(res.conjunctions[k])
                    probes = [f"{a}–{b} conjunctions: {n_max}", f"{a}–{b} conjunctions: {max(n_max, 10)}"]
                    slots.append(Slot(probes, value=lambda t, k=k, a=a, b=b: f"{a}–{b} conjunctions: {self._conj_count(k, t)}", color="dim", scale=0.85,
                                      name="conjunctions", rank=1))
        central = model.system.central.name
        for name, (share, _) in info.curvature.items():
            when = "always" if share == 1.0 else f"{share:.0%} of the time"
            slots.append(Slot([f"{name}'s path bends toward {central}: {when}"], scale=0.85, name="curvature", rank=0))
        return slots

    def _angular_slot(self) -> list[Slot]:
        """The n-body run's angular-momentum error row (with the energy's; a diagnostic)."""
        if self._model.run is None or self._model.run.angular is None:
            return []
        return [Slot(["ΔL/L = " + plotcore.readout_number(-1.23e-10, 2), "ΔL/L = " + plotcore.readout_number(-9.99e-9, 2)],
                     value=lambda t: "ΔL/L = " + plotcore.readout_number(self._model.angular_error(t), 2), name="angular", rank=self._energy_rank())]

    def _frame_text(self, period: str) -> str:
        turn = self._model.turn
        if turn >= 1 - 1e-9:
            return f"rotating frame: one turn / {period}"
        if turn <= 1e-9:
            return "inertial frame (fixed stars)"
        return "turning with the pair…"

    def _jacobi_value(self, name: str, prefix: str) -> Any:
        series = self._model.many.jacobi[name]
        times = self._model.run.times

        def value(t: float) -> str:
            k = int(np.clip(np.searchsorted(times, t), 0, len(times) - 1))
            err = (series[k] - series[0]) / abs(series[0])
            return f"{prefix}C = {series[k]:.6f}, ΔC/C = {plotcore.readout_number(err, 2)}"
        return value

    def _ahead(self, name: str, t: float) -> float:
        model = self._model
        sec = model.many.restricted.secondary
        return float(orbits.coorbital_angles(model.position(name, t), model.position(sec, t)))

    def _angle_text(self, name: str, angle: float) -> str:
        sec = self._model.many.restricted.secondary
        side = "ahead of" if angle >= 0 else "behind"
        return f"{name} {abs(angle):.0f}° {side} {sec}"

    @staticmethod
    def _kind_text(kind: str, lo: float, hi: float) -> str:
        if kind.startswith("tadpole"):
            point = kind.split()[1]
            a, b = (lo, hi) if point == "L4" else (-hi, -lo)
            return f"tadpole about {point} ({a:.0f}° to {b:.0f}°)"
        if kind == "horseshoe":
            return "horseshoe: round past L3 and back"
        return "passes the secondary: not co-orbital"

    def _laplace_value(self) -> Any:
        res = self._model.many.resonance

        def value(t: float) -> str:
            ls = [self._longitude(n, t) for n in res.bodies]
            return f"Laplace angle φ = {float(orbits.laplace_angle(*ls)):.1f}°"
        return value

    def _longitude(self, name: str, t: float) -> float:
        o = self._model.system.orbiter(name)
        p = o.positions(t)
        return math.atan2(float(p[1]), float(p[0]))

    def _conj_count(self, k: int, t: float) -> int:
        return sum(1 for tc, _ in self._model.many.resonance.conjunctions[k] if tc <= t)

    def _many_legend_first(self) -> list[tuple[str, str]]:
        info = self._model.many
        if info is None or info.eight is None:
            return []
        centre = self._model.system.central
        return [(f"{centre.name}  T = {self._time_text(info.eight.period)}", self.theme.color(centre.color or "highlight"))]

    def _many_legend(self, o: Any) -> str | None:
        """A legend row for a body of a many-body system (``None``: the usual one)."""
        info = self._model.many
        if info is None:
            return None
        if info.eight is not None:
            return f"{o.name}  T = {self._time_text(info.eight.period)}"
        r = info.restricted
        if r is not None:
            if o.name == r.secondary:
                return f"{o.name}  T = {self._time_text(r.pair.period)}"
            if o.name in info.near:
                return f"{o.name}  from {info.near[o.name]}, massless"
        return None

    # ----- building --------------------------------------------------------------------------------

    def _build_many(self) -> None:
        """Lagrange points, the zero-velocity curve, the pair's circle, the rotating frame's badge,
        a binary's ellipses and barycentre, the figure-eight's barycentre, conjunction lines and
        the pointer to the central body."""
        model = self._model
        info = model.many
        self._many_parts: dict[str, Any] = {}
        self._many_static: list[Any] = []
        if info is None:
            return
        dim = self.theme.color("dim")
        if info.restricted is not None:
            self._build_pair_circle()
            self._build_rotation_badge()
        if info.lagrange:
            self._build_lagrange()
        if info.zero_velocity is not None:
            zv = VMobject().set_stroke(self.theme.color("accent"), width=2.5, opacity=0.85).set_z_index(1.1)
            self._many_parts["zv"] = {"mob": zv, "segs": self._zv_segments(), "key": None}
            self._held_target(["zero_velocity"], zv)
        stars = binary_names(model)
        for name in stars:
            pts = self._frame_points(self._binary_points(name))
            line = plot_draw.series_line(pts, self._lay.plot, self._colors.get(name, self._central_color), width=2.5, dashed=False)
            line.set_stroke(opacity=0.55).set_z_index(1)
            self._held_target([f"orbit:{name}"], line)
        if info.origin == "barycentre" and (stars or info.eight is not None):
            at = self._frame_point(np.zeros(3))
            mark = VGroup(Line(at + [-0.09, 0, 0], at + [0.09, 0, 0]), Line(at + [0, -0.09, 0], at + [0, 0.09, 0])).set_stroke(dim, width=3)
            lab = self._small_label("barycentre", "dim", 0.8)
            lines = self._crowd_points()[:, :2]
            if stars:
                lines = np.concatenate([lines, *[self._frame_points(self._binary_points(n))[:, :2] for n in stars]])
            _, box, _ = place(at, 0.1, lab.width, lab.height, obstacles=self._fixed_obstacles(), plot=self._lay.plot, points=lines, line_weight=0.02)
            lab.move_to([box.center[0], box.center[1], 0])
            self._static_boxes.append(box)
            self._held_target(["barycentre"], VGroup(mark, lab).set_z_index(3.5))
        if info.resonance is not None and info.resonance.show:
            self._build_conjunctions()
        if info.center is not None:
            arrow = new_arrow(dim, width=4.0, z=5.6)
            lab = self._small_label(model.system.central.name, "dim", 0.85)
            group = VGroup(arrow, lab)
            self._many_parts["pointer"] = {"arrow": arrow, "label": lab}
            self._held_target(["pointer"], group)

    def _held_target(self, names: list[str], group: Mobject) -> None:
        """Register ``group`` under ``names``; it enters with the first beat unless a reveal holds it."""
        for n in names:
            self.target(n, group)
        if not self._is_held(names):
            self._intro_parts.append(group)

    def _build_pair_circle(self) -> None:
        """The secondary's circle about the barycentre (dashed, clipped to the plot)."""
        r = self._model.many.restricted
        radius = (1 - r.pair.mu) * r.pair.separation
        ring = np.linspace(0, 2 * math.pi, 1441)
        pts = self._frame_points(np.column_stack([radius * np.cos(ring), radius * np.sin(ring), 0 * ring]))
        circle = plot_draw.series_line(pts, self._lay.plot, self._colors.get(r.secondary, self.theme.color("dim")), width=2, dashed=True)
        circle.set_stroke(opacity=0.45).set_z_index(0.9)
        self._held_target([f"orbit:{r.secondary}"], circle)

    def _crowd_points(self) -> np.ndarray:
        """Frame points of what the plot shows in each view (paths, Lagrange points): where
        something placed once should not stand."""
        model = self._model
        info = model.many
        ts = np.linspace(0.0, model.span, 300)
        keep = model.turn
        pts = [np.zeros((0, 3))]
        for turn in self._many_turns():
            model.turn = turn
            for name in [model.system.central.name, *model.system.names]:
                pts.append(self._frame_points(model.view(name, ts)))
            if info.lagrange:
                at = np.array([info.restricted.pair.points()[k] for k in info.lagrange])
                marks = self._frame_points(model.from_rotating(at, 0.0))
                labels = marks + np.array([[*LAGRANGE_LABEL[k], 0.0] for k in info.lagrange])
                pts.append(np.repeat(np.concatenate([marks, labels]), 40, axis=0))
        model.turn = keep
        return np.concatenate(pts)

    def _build_rotation_badge(self) -> None:
        """A turning arrow (the pair's sense of rotation) in the plot's least crowded corner, shown
        while the view turns with the pair; the panel says which frame is shown."""
        plot = self._lay.plot
        rad = 0.2
        w, h = 2 * rad + 0.1, 2 * rad + 0.1   # the words are in the panel ("rotating frame: one turn / …")
        crowd = self._crowd_points()

        def count(x: float, y: float) -> int:   # (x, y) the badge's top left corner
            inside = (crowd[:, 0] > x - 0.1) & (crowd[:, 0] < x + w + 0.1) & (crowd[:, 1] > y - h - 0.1) & (crowd[:, 1] < y + 0.1)
            return int(np.count_nonzero(inside))

        corners = [(plot.x0 + 0.2, plot.y1 - 0.2), (plot.x1 - 0.2 - w, plot.y1 - 0.2), (plot.x0 + 0.2, plot.y0 + 0.2 + h), (plot.x1 - 0.2 - w, plot.y0 + 0.2 + h)]
        x, y = min(corners, key=lambda c: count(*c))
        c = np.array([x + rad, y - h / 2, 0.0])
        angles = np.linspace(math.radians(-60), math.radians(220), 40)
        arc = VMobject().set_points_as_corners(np.column_stack([c[0] + rad * np.cos(angles), c[1] + rad * np.sin(angles), np.zeros(40)]))
        arc.set_stroke(self.theme.color("highlight"), width=3)
        end = np.array([c[0] + rad * math.cos(angles[-1]), c[1] + rad * math.sin(angles[-1]), 0.0])
        tangent = np.array([-math.sin(angles[-1]), math.cos(angles[-1]), 0.0])
        normal = np.array([-tangent[1], tangent[0], 0.0])
        tip = Polygon(end + tangent * 0.11, end + normal * 0.06, end - normal * 0.06).set_fill(self.theme.color("highlight"), opacity=1).set_stroke(width=0)
        badge = VGroup(arc, tip).set_z_index(5.5)
        self._many_parts["badge"] = badge
        self._static_boxes.append(mob_rect(badge, 0.05))
        self._held_target(["rotation"], badge)

    def _build_lagrange(self) -> None:
        info = self._model.many
        pts = info.restricted.pair.points()
        color = self.theme.color("highlight")
        marks = {}
        groups = []
        for name in info.lagrange:
            cross = VGroup(Line([-0.08, -0.08, 0], [0.08, 0.08, 0]), Line([-0.08, 0.08, 0], [0.08, -0.08, 0])).set_stroke(color, width=3.5)
            lab = self._small_label(name, "highlight", 0.85)
            group = VGroup(cross, lab).set_z_index(4.2)
            marks[name] = {"cross": cross, "label": lab, "at": np.array([*pts[name], 0.0])}
            self.target(f"lagrange:{name}", group)
            groups.append(group)
            if not self._is_held([f"lagrange:{name}", "lagrange"]):
                self._intro_parts.append(group)
        self.target("lagrange", VGroup(*groups))
        self._many_parts["lagrange"] = marks

    def _zv_segments(self) -> np.ndarray:
        """The zero-velocity curve (m, rotating frame from the barycentre) over the view."""
        info = self._model.many
        pair = info.restricted.pair
        lay = self._lay
        u = self._unit_m
        corners = np.array([[lay.x.lo, lay.y.lo], [lay.x.hi, lay.y.hi], [lay.x.lo, lay.y.hi], [lay.x.hi, lay.y.lo]]) * u / pair.separation
        if info.turn0 == 1.0 and len(self._many_turns()) == 1:   # the plot's own box
            xr = (float(corners[:, 0].min()), float(corners[:, 0].max()))
            yr = (float(corners[:, 1].min()), float(corners[:, 1].max()))
        else:   # the disc the view sees while the frame turns
            reach = float(np.max(np.linalg.norm(corners, axis=1)))
            xr = yr = (-reach, reach)
        c = float(info.jacobi[info.zero_velocity][0])
        return orbits.zero_velocity_segments(pair.mu, c, xr, yr, cells=ZV_CELLS) * pair.separation

    def _build_conjunctions(self) -> None:
        model = self._model
        res = model.many.resonance
        lines = []
        reach = 1.12 * max(model.system.orbiter(n).elements.apoapsis for n in res.bodies)
        for k, pair in enumerate(res.conjunctions):
            color = self._colors.get(res.bodies[k], self.theme.color("highlight"))
            synodic = 1 / (1 / res.periods[k] - 1 / res.periods[k + 1])
            for tc, angle in pair:
                line = VMobject().set_stroke(color, width=3).set_z_index(0.8)
                lines.append({"line": line, "time": tc, "angle": angle, "pair": k, "synodic": synodic})
        group = VGroup(*[d["line"] for d in lines])
        self._many_parts["conj"] = {"lines": lines, "reach": reach}
        self._held_target(["conjunctions"], group)

    # ----- per frame ---------------------------------------------------------------------------------

    def _draw_many(self, t: float, anchors: dict[str, np.ndarray]) -> None:
        model = self._model
        info = model.many
        if info is None or info.tides is not None:
            return
        parts = self._many_parts
        if "badge" in parts:   # the arc's stroke and the tip's fill (set_opacity would fill the arc)
            arc, tip = parts["badge"]
            arc.set_stroke(opacity=model.turn)
            tip.set_fill(opacity=model.turn)
        plot = self._lay.plot
        marks = parts.get("lagrange", {})
        where = {name: self._frame_point(model.from_rotating(m["at"][None, :2], t)[0]) for name, m in marks.items()}
        for name, m in marks.items():
            m["cross"].move_to(where[name])
            other = {"L1": "L2", "L2": "L1"}.get(name)
            away = where[name] - where[other] if other in where else None   # L1's and L2's labels on their far sides
            m["label"].move_to(self._lagrange_label_at(name, where[name], m["label"], plot, away))
        zv = parts.get("zv")
        if zv is not None:
            key = None if model.turn < 1 else "still"
            if key is None or zv["key"] != key:
                zv["key"] = key
                self._draw_zv(zv, t)
        conj = parts.get("conj")
        if conj is not None:
            self._draw_conjunctions(conj, t, anchors)
        pointer = parts.get("pointer")
        if pointer is not None:
            self._draw_pointer(pointer, anchors)

    @staticmethod
    def _lagrange_label_at(name: str, at: np.ndarray, lab: Mobject, plot: Any, away: np.ndarray | None = None) -> np.ndarray:
        """Where a Lagrange point's label stands: under the mark (L4 over it); L1's and L2's on
        the sides facing away from each other (``away``: from the other point) so the two never
        meet; kept in the plot (above the mark when there is no room under it)."""
        dx, dy = LAGRANGE_LABEL[name]
        w, h = lab.width, lab.height
        if away is not None and float(np.hypot(away[0], away[1])) > 1e-9:
            u = away / float(np.hypot(away[0], away[1]))
            reach = 0.1 + 0.5 * (abs(u[0]) * w + abs(u[1]) * h)
            x, y = at[0] + u[0] * reach, at[1] + u[1] * reach - (0.1 + h / 2) * (1 - abs(u[1]))
        else:
            x = at[0]
            y = at[1] + (dy / abs(dy)) * (0.1 + h / 2) if dy else at[1]
        x = min(max(x, plot.x0 + w / 2), plot.x1 - w / 2)   # kept in the plot (L1's and L2's still apart)
        if y - h / 2 < plot.y0 or y + h / 2 > plot.y1:
            y = 2 * at[1] - y
        return np.array([x + dx, y, 0.0])

    def _draw_zv(self, zv: dict[str, Any], t: float) -> None:
        segs = zv["segs"]
        mob = zv["mob"]
        plot = self._lay.plot
        empty = np.tile([plot.x0, plot.y0, 0.0], (4, 1))   # nothing to draw: a curve of no length (a reveal's fade keeps its shape)
        if not len(segs):
            mob.set_points(empty)
            return
        model = self._model
        flat = model.from_rotating(segs.reshape(-1, 2), t)
        pts = self._frame_points(flat).reshape(-1, 2, 3)
        inside = ((pts[:, :, 0] >= plot.x0) & (pts[:, :, 0] <= plot.x1) & (pts[:, :, 1] >= plot.y0) & (pts[:, :, 1] <= plot.y1)).all(axis=1)
        pts = pts[inside]
        if not len(pts):
            mob.set_points(empty)
            return
        a, b = pts[:, 0], pts[:, 1]
        curves = np.stack([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b], axis=1).reshape(-1, 3)
        mob.set_points(curves)

    def _draw_conjunctions(self, conj: dict[str, Any], t: float, anchors: dict[str, np.ndarray]) -> None:
        model = self._model
        res = model.many.resonance
        parent = res.parent if res.parent is not None else model.system.central.name
        centre = self._frame_point(anchors[parent])
        reach = conj["reach"] * self._scale
        shown: dict[int, int] = {}
        for d in reversed(conj["lines"]):   # the latest first: only the last few of each pair stay
            line = d["line"]
            u = np.array([math.cos(d["angle"]), math.sin(d["angle"]), 0.0])
            line.set_points_as_corners(np.array([centre, centre + u * reach]))   # always points: a reveal's fade keeps its shape
            count = shown.get(d["pair"], 0)
            if t < d["time"] or count >= res.keep:
                line.set_stroke(opacity=0.0)
                continue
            shown[d["pair"]] = count + 1
            age = (t - d["time"]) / d["synodic"]
            line.set_stroke(opacity=0.95 if age < CONJUNCTION_BRIGHT else 0.3)

    def _draw_pointer(self, pointer: dict[str, Any], anchors: dict[str, np.ndarray]) -> None:
        """An arrow at the plot's edge towards the central body when it is outside the plot."""
        plot = self._lay.plot
        target = self._frame_point(anchors[self._model.system.central.name])
        arrow, lab = pointer["arrow"], pointer["label"]
        if plot.contains(float(target[0]), float(target[1]), 1e-6):   # hidden (its points kept: a reveal's fade keeps its shape)
            if not arrow[0].has_points():
                arrow_shape(arrow[0], arrow[1], np.array([plot.x0 + 0.3, plot.y0 + 0.3, 0.0]), np.array([0.3, 0.0]), 4.0)
            arrow.set_opacity(0)
            lab.set_opacity(0)
            return
        arrow.set_opacity(1)
        c = np.array([(plot.x0 + plot.x1) / 2, (plot.y0 + plot.y1) / 2, 0.0])
        d = target - c
        u = d / float(np.linalg.norm(d))
        # where the line from the centre towards it leaves the plot, a little inside
        sx = (plot.width / 2 - 0.15) / abs(u[0]) if abs(u[0]) > 1e-9 else math.inf
        sy = (plot.height / 2 - 0.15) / abs(u[1]) if abs(u[1]) > 1e-9 else math.inf
        tip = c + u * min(sx, sy)
        n = np.array([u[1], -u[0], 0.0])   # beside the arrow, on the side away from the labels set below marks
        if n[1] < 0:
            n = -n
        marks = [m["cross"].get_center() for m in self._many_parts.get("lagrange", {}).values()]
        s = np.linspace(0.0, 1.0, 12)[:, None]
        if any(np.min(np.linalg.norm((tip - u * 0.6 * s - p)[:, :2], axis=1)) < 0.25 for p in marks):   # off a Lagrange mark, still pointing the same way
            tip = tip + n * 0.4
        arrow_shape(arrow[0], arrow[1], tip - u * 0.6, u[:2] * 0.6, 4.0)
        lab.set_opacity(1)
        lab.move_to(tip - u * 0.3 + n * (0.5 * (abs(n[0]) * lab.width + abs(n[1]) * lab.height) + 0.12))

    def _many_boxes(self) -> list[Any]:
        """Where the Lagrange labels stand now (body labels keep off them)."""
        out = []
        for m in getattr(self, "_many_parts", {}).get("lagrange", {}).values():
            if m["label"].get_fill_opacity() > 0:
                out += [mob_rect(m["label"], 0.03), mob_rect(m["cross"], 0.02)]
        return out

    # ----- the tidal schematic ---------------------------------------------------------------------

    def _construct_tides(self, begin: float) -> None:
        """The tidal schematic: the planet large, the satellite on a schematic circle moving in
        its real time, its pull at points of the planet (nearly equal and parallel), its pull at
        the centre, their difference (the tidal arrows, enlarged), the two bulges along the line
        to it, and its near side marked (tidal locking). Labelled schematic, not to scale."""
        p = self.params
        model = self._model
        spec = model.many.tides
        portrait = self.is_portrait
        size = self._size
        body = self.safe_area
        title = caption = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            body = body.below(title, gap=0.3)
        if p.caption:
            caption = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(caption, gap=0.2)
        planet = model.system.central
        o = model.system.orbiters[0]
        sat = o.body
        d = o.elements.a
        pull = sat.gm / d**2
        ring = np.linspace(0, 2 * math.pi, spec.points, endpoint=False)
        surface = np.column_stack([np.cos(ring), np.sin(ring), 0 * ring]) * planet.radius
        tidal = float(np.max(np.linalg.norm(orbits.tidal_acceleration(sat.gm, [d, 0.0, 0.0], surface), axis=1)))   # ≈ 2GMR/d³
        height = orbits.equilibrium_tide(sat.gm, planet.gm, planet.radius, d)
        self._t_unit = orbits.time_unit(model.span)
        self._lines_static = [orbits.speedup_text(model.span / self._motion_seconds())]
        slots = [
            Slot([self._time_line(model.span * k / 200) for k in range(201)], value=self._time_line, name="time", rank=0),
            Slot([*self._lines_static, "clock paused", "× 99 million"], value=lambda t: self._rate_text(), name="speedup", rank=2),
            Slot([f"{sat.name}'s pull: {plotcore.readout_number(pull, 3)} m/s²"], scale=0.85, name="pull", rank=0),
            Slot([f"tidal: up to {plotcore.readout_number(tidal, 3)} m/s² (1/{pull / tidal:.0f} of it)"], scale=0.85, name="tidal", rank=0),
            Slot([f"tidal arrows drawn ×{TIDE_ARROW / tidal / (TIDE_PULL / pull):.0f} longer"], color="dim", scale=0.8, name="arrows", rank=0),
            Slot([f"equilibrium tide: {plotcore.readout_number(height, 2)} m"], scale=0.85, name="tide", rank=1),
        ]
        if spec.locking:
            slots.append(Slot([f"{sat.name} spins once per orbit ({self._time_text(o.elements.period)}): locked"], scale=0.85, name="locked", rank=1))
        note = "schematic: sizes, distance and arrows not to scale" if self._panel_mode == "full" else "schematic: not to scale"
        slots.append(Slot([note], color="dim", scale=0.8, name="schematic", rank=0))
        slots = choose_rows(slots, self._panel_mode, self._panel_budget())
        self._slots = slots
        w, h = self._panel_size(slots)
        if w > body.width:
            h *= body.width / w
            w = body.width
        if portrait:
            box = plotcore.Rect((body.x0 + body.x1) / 2 - w / 2, body.y1 - h, (body.x0 + body.x1) / 2 + w / 2, body.y1)
            canvas = plotcore.Rect(body.x0, body.y0, body.x1, box.y0 - 0.3)
        else:
            box = plotcore.Rect(body.x1 - w, (body.y0 + body.y1) / 2 - h / 2, body.x1, (body.y0 + body.y1) / 2 + h / 2)
            canvas = plotcore.Rect(body.x0, body.y0, box.x0 - 0.4, body.y1)
        self._readout_box = box
        side = min(canvas.width, canvas.height)
        centre = np.array([(canvas.x0 + canvas.x1) / 2, (canvas.y0 + canvas.y1) / 2, 0.0])
        r_p, r_o, r_m = TIDE_PLANET * side, TIDE_ORBIT * side, TIDE_MOON * side
        planet_color = self.theme.color(planet.color or "primary")
        water = self.theme.palette_color(0)
        disc = Circle(radius=r_p).set_fill(planet_color, opacity=1).set_stroke(width=0).move_to(centre).set_z_index(2)
        bulge = Ellipse(width=2 * r_p * (1 + TIDE_BULGE), height=2 * r_p * (1 - TIDE_BULGE / 2)).set_fill(water, opacity=0.3)
        bulge.set_stroke(self.theme.color("text"), width=2.5, opacity=0.9).move_to(centre).set_z_index(2.5)   # over the planet: the water's outline
        planet_label = self._label(planet.name, size).set_color(self.theme.background).move_to(centre).set_z_index(5)
        orbit = DashedVMobject(Circle(radius=r_o), num_dashes=80).set_stroke(self.theme.color("dim"), width=2, opacity=0.5).move_to(centre)
        moon = Circle(radius=r_m).set_fill(self.theme.color(sat.color or "dim"), opacity=1).set_stroke(self.theme.background, width=2).set_z_index(4)
        face = Dot(radius=0.4 * r_m, color=self.theme.color("highlight")).set_z_index(4.5)
        moon_label = self._label(sat.name, size)
        face_label = self._small_label("near side", "highlight", 0.8)
        n = spec.points
        self._tide_parts = {
            "centre": centre, "r_p": r_p, "r_o": r_o, "r_m": r_m, "bulge": bulge, "moon": moon, "face": face, "moon_label": moon_label,
            "face_label": face_label, "pull": [new_arrow(self.theme.color("dim"), width=3.0, z=3.0) for _ in range(n)],
            "mean": new_arrow(self.theme.color("text"), width=4.0, z=3.2), "tidal": [new_arrow(self.theme.color("highlight"), width=4.0, z=3.4) for _ in range(n)],
            "angles": np.linspace(0, 2 * math.pi, n, endpoint=False), "planet": planet, "sat": sat, "d": d, "spec": spec, "canvas": canvas,
        }
        self._readout = VGroup()
        self._last_lines = None
        self._burn_video = {}   # the clock's plan takes pauses only here
        if title is not None:
            self.target("title", title)
        self.target("frame", VGroup(orbit, *([caption] if caption is not None else [])))
        self.target("central", VGroup(disc, planet_label))
        self.target(f"body:{sat.name}", VGroup(moon, moon_label))
        self.target("readout", self._readout)
        parts = {"pull": VGroup(*self._tide_parts["pull"]), "mean": self._tide_parts["mean"], "tidal": VGroup(*self._tide_parts["tidal"]), "bulges": bulge}
        if spec.locking:
            parts["face"] = VGroup(face, face_label)
        held = self._held_patterns()
        intro = [m for k, m in parts.items() if not any(k == pat for pat in held)]
        for k, m in parts.items():
            self.target(k, m)
        self._draw_tides(0.0)
        self._draw_readout(0.0)

        def entrance(d: float) -> list[Animation]:
            anims = [FadeIn(m) for m in (title, caption) if m is not None]
            anims += [FadeIn(orbit), GrowFromCenter(disc), FadeIn(planet_label), FadeIn(moon), FadeIn(moon_label), FadeIn(self._readout)]
            anims += [FadeIn(m) for m in intro]
            self.play(*anims, run_time=min(1.2, max(0.3 * d, 1 / config.frame_rate)))
            start = float(self.renderer.time)
            self._playback = self._clock_plan(start, max(begin + self._motion_seconds() - start, 1 / config.frame_rate))

            def update(_: Mobject, dt: float) -> None:
                self._video_now = float(self.renderer.time)
                t = self._playback.sim_time(self._video_now)
                self._draw_tides(t)
                self._draw_readout(t)

            self._update = update
            self._clock_mob.add_updater(update)
            return []

        for i, dur in self.timeline():
            if i == 0:
                self.play_steps(dur, [lambda: entrance(dur)], fraction=0.8, cap=1.5)
        self.finish()
        self._stop()

    def _draw_tides(self, t: float) -> None:
        parts = self._tide_parts
        model = self._model
        o = model.system.orbiters[0]
        pos = o.positions(t)
        phi = math.atan2(float(pos[1]), float(pos[0]))
        u = np.array([math.cos(phi), math.sin(phi), 0.0])
        c, r_p, r_o, r_m = parts["centre"], parts["r_p"], parts["r_o"], parts["r_m"]
        at = c + u * r_o
        parts["moon"].move_to(at)
        self._turn_bulge(parts["bulge"], phi)
        face_angle = phi + math.pi if parts["spec"].locking else math.pi   # locked: always towards the planet; else fixed in space
        f = np.array([math.cos(face_angle), math.sin(face_angle), 0.0])
        parts["face"].move_to(at + f * 0.62 * r_m)
        planet_box = plotcore.Rect(c[0] - r_p * 1.25, c[1] - r_p * 1.25, c[0] + r_p * 1.25, c[1] + r_p * 1.25)
        taken = [self._panel_rect(), planet_box]
        for key, lab, dirs in (("moon_label", parts["moon_label"], [(float(u[0]), float(u[1]))]),
                               ("face_label", parts["face_label"], [(float(-u[1]), float(u[0])), (float(u[1]), float(-u[0]))])):
            k, box, _ = place(at, r_m, lab.width, lab.height, obstacles=taken, plot=parts["canvas"], directions=(*dirs, *DIRECTIONS),
                              rings=(0.0, 0.15, 0.3), prev=parts.get(key + "_k"))
            parts[key + "_k"] = k
            lab.move_to([box.center[0], box.center[1], 0])
            taken.append(box)
        # the satellite's real pull at points of the surface (real geometry, d ≫ R), its pull at the centre, the difference
        sat_at = np.array([math.cos(phi), math.sin(phi), 0.0]) * parts["d"]
        R = parts["planet"].radius
        pts = np.column_stack([np.cos(parts["angles"]), np.sin(parts["angles"]), np.zeros(len(parts["angles"]))]) * R
        rel = sat_at[None, :] - pts
        acc = parts["sat"].gm * rel / np.linalg.norm(rel, axis=1)[:, None] ** 3
        mean = parts["sat"].gm * sat_at / np.linalg.norm(sat_at) ** 3
        tid = acc - mean
        scale_pull = TIDE_PULL / float(np.linalg.norm(mean))
        scale_tid = TIDE_ARROW / float(np.max(np.linalg.norm(tid, axis=1)))
        for k, (arrow_p, arrow_t) in enumerate(zip(parts["pull"], parts["tidal"])):
            base = c + np.array([math.cos(parts["angles"][k]), math.sin(parts["angles"][k]), 0.0]) * r_p * 1.02
            arrow_shape(arrow_p[0], arrow_p[1], base, acc[k, :2] * scale_pull, 3.0)
            arrow_shape(arrow_t[0], arrow_t[1], base, tid[k, :2] * scale_tid, 4.0)
        m = parts["mean"]
        arrow_shape(m[0], m[1], c, mean[:2] * scale_pull, 4.0)

    @staticmethod
    def _turn_bulge(bulge: Mobject, phi: float) -> None:
        """Point the bulge's long axis at angle ``phi`` (it turns by the difference from before)."""
        before = getattr(bulge, "_tide_angle", 0.0)
        if phi != before:
            bulge.rotate(phi - before)
            bulge._tide_angle = phi


__all__ = ["OrbitMany", "SWITCH_SECONDS", "binary_names", "many_target_names"]
