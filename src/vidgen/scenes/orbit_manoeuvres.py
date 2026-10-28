"""Manoeuvres and gravity assists on the ``orbit`` scene (Phase X, Step 231, DESIGN §98.5): a
body's burns (Δv arrows at the burn points, the orbits before faint and after drawn, a mission
line in the panel), a transfer (Hohmann, bi-elliptic, phasing: the planned path, the phase angle
live until departure, Δv₁, Δv₂, total, transfer time, synodic period), a flyby in the planet's
frame (asymptotes, v∞ in and out, the turning angle δ, the periapsis, the atmosphere, the
planet's motion) with the Sun-frame vector diagram (v_planet + v∞ before and after), and the
clock's stretches (a burn or the periapsis passage on its word, pauses). A mixin of
:class:`~vidgen.scenes.orbit.Orbit`; the physics is in :mod:`vidgen.orbits.manoeuvres` and
:mod:`vidgen.orbits.flyby`."""

import math
from fnmatch import fnmatchcase
from typing import Any

import numpy as np

from vidgen.api import *

from .orbit_overlays import DIRECTIONS, Slot, arrow_shape, mob_rect, new_arrow, place, rect_at, speed_text
from .orbit_overlays import overlap as overlap_area
from .orbit_parts import lead_angle

#: The longest Δv arrow as a share of the plot's shorter side, and the shortest drawn (units).
DV_SHARE = 0.16
DV_MIN = 0.12
#: Rings (extra distances) for the labels of burns, transfers and the phase angle: they may go further out.
WIDE_RINGS = (0.0, 0.3, 0.65, 1.1, 1.6, 2.2)
#: Faint opacity of an orbit left by a burn, and of the current one.
PAST_OPACITY = 0.2
NOW_OPACITY = 0.55
#: Size of the Sun-frame vector diagram (Manim units) beside (16:9) or under (9:16) the picture.
VECTOR_BOX = (3.6, 2.5)
VECTOR_BOX_PORTRAIT_H = 2.6
#: Gap between the panel and the vector diagram.
VECTOR_GAP = 0.3
#: Subscript digits for Δv₁, Δv₂...
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_KIND_NAMES = {"hohmann": "Hohmann transfer", "bielliptic": "bi-elliptic transfer", "phasing": "phasing"}


def dv_name(n: int) -> str:
    return "Δv" + str(n).translate(_SUB)


def burn_text(n: int, b: Any) -> str:
    """Burn ``n``'s label: its own, else "Δv₁ 2.43 km/s prograde"."""
    return getattr(b, "label", "") or f"{dv_name(n)} {speed_text(b.magnitude)} {b.direction}"


def _deg(rad: float) -> str:
    return f"{math.degrees(rad):.1f}°"


class OrbitManoeuvres:
    """Burns, transfers and flybys of an ``orbit`` scene (mixed into the scene class)."""

    # ----- text ------------------------------------------------------------------------------------

    def _burn_text(self, n: int, b: Any) -> str:
        return burn_text(n, b)

    # ----- the side panel ----------------------------------------------------------------------------

    def _manoeuvre_slots(self) -> list[Slot]:
        """Panel rows: a transfer's numbers (or each burn's), the mission line (the next burn or
        all done, the Δv spent), a flyby's numbers."""
        model = self._model
        slots: list[Slot] = []
        info = model.transfer
        burns = model.burns()
        if info is not None:
            slots += self._transfer_slots(info)
        elif burns:
            many = len({name for name, _ in burns}) > 1
            for n, (name, b) in enumerate(burns, start=1):
                text = (f"{name}: " if many else "") + f"{dv_name(n)} {speed_text(b.magnitude)} {b.direction}"
                slots.append(Slot([text], scale=0.9, name="burns", rank=0))   # the plan, from the start (the mission line says what comes next)
            total = sum(b.magnitude for _, b in burns)
            slots.append(Slot([f"Δv spent {speed_text(total)} of {speed_text(total)}"], value=self._spent(burns), color="dim", scale=0.85,
                              name="dv_spent", rank=1))
        if burns:
            probes = [self._next_text(burns, t) for t in np.linspace(0.0, model.span, 121)] + [f"next: {dv_name(len(burns))} now"]
            slots.append(Slot(probes, value=lambda t: self._next_text(burns, t), color="dim", scale=0.85, name="next", rank=2))
        if model.assist is not None:
            slots += self._assist_slots(model.assist)
        return slots

    def _transfer_slots(self, info: Any) -> list[Slot]:
        r = info.result
        slots = [Slot([_KIND_NAMES[info.kind] + (f" to {info.target}" if info.target else "")], color="dim", scale=0.85, name="transfer_kind", rank=2)]
        if info.kind == "phasing":
            ahead = "ahead" if r.angle > 0 else "behind"
            slots.append(Slot([f"{info.target} {_deg(abs(r.angle))} {ahead} at the burn"], scale=0.9, name="phasing", rank=0))
            slots.append(Slot([f"{r.revolutions} turn{'s' if r.revolutions > 1 else ''} of {self._time_text(r.period)}"], scale=0.9, name="phasing", rank=0))
            slots.append(Slot([f"{dv_name(1)} = {dv_name(2)} = {speed_text(r.dv)}"], scale=0.9, name="phasing", rank=0))
        else:
            dvs = [r.dv1, r.dv2] + ([r.dv3] if info.kind == "bielliptic" else [])
            for n, dv in enumerate(dvs, start=1):
                slots.append(Slot([f"{dv_name(n)} = {speed_text(dv)}"], scale=0.9, name="dv", rank=0))
        slots.append(Slot([f"total Δv = {speed_text(r.total)}"], name="total_dv", rank=0))
        slots.append(Slot([f"transfer {self._time_text(info.arrival - info.depart)}"], scale=0.9, name="transfer_time", rank=0))
        if info.phase_needed is not None:
            needed = info.phase_needed
            probes = [self._phase_text(info, x) for x in (-math.radians(179.9), math.radians(179.9))]
            slots.append(Slot(probes, value=lambda t: self._phase_text(info, self._lead_at(info, min(t, info.depart))), scale=0.9, name="phase", rank=0))
            every = f", every {self._time_text(2 * math.pi / abs(info.n_ship - info.n_target))}" if info.kind != "phasing" else ""
            slots.append(Slot([f"window at {_deg(needed)}{every}"], color="dim", scale=0.85, name="window", rank=2))
        if info.miss is not None and info.kind != "phasing" and info.miss > 1e-3 * info.r2:
            slots.append(Slot([f"misses {info.target} by {self._length_text(info.miss)}"], color="accent", scale=0.85, name="miss", rank=0))
        return slots

    def _lead_at(self, info: Any, t: float) -> float:
        """The target's lead angle over the ship at ``t`` (rad)."""
        return lead_angle(self._model.system, info.ship, info.target, t)

    def _phase_text(self, info: Any, lead: float) -> str:
        word = "leads by" if lead >= 0 else "trails by"
        return f"{info.target} {word} {_deg(abs(lead))}"

    def _spent(self, burns: list[tuple[str, Any]]) -> Any:
        total = sum(b.magnitude for _, b in burns)

        def value(t: float) -> str:
            done = sum(b.magnitude for n, (_, b) in enumerate(burns, start=1) if self._burn_done(n, b, t))
            return f"Δv spent {speed_text(done)} of {speed_text(total)}"
        return value

    def _next_text(self, burns: list[tuple[str, Any]], t: float) -> str:
        """The mission line at ``t``: the next burn and how long until it, or all burns done."""
        for n, (_, b) in enumerate(burns, start=1):
            if not self._burn_done(n, b, t):
                return f"next: {dv_name(n)} in {self._time_text(b.time - t)}" if b.time - t >= 1.0 else f"next: {dv_name(n)} now"
        return "all burns done" if len(burns) > 1 else "burn done"

    def _assist_slots(self, info: Any) -> list[Slot]:
        ga = info.assist
        fb = ga.flyby
        side = "behind" if ga.side == "behind" else "in front of"
        return [
            Slot([f"v∞ in = out = {speed_text(fb.v_inf)}"], name="v_inf", rank=0),
            Slot([f"δ = {_deg(fb.delta)}  (e = {fb.e:.3f})"], scale=0.9, name="turn_angle", rank=0),
            Slot([f"passes {side} {info.planet}"], color="dim", scale=0.85, name="side", rank=2),
            Slot([f"Sun: {speed_text(ga.speed_before)} → {speed_text(ga.speed_after)}"], scale=0.9, name="sun_speeds", rank=0),
            Slot([f"{'gains' if ga.gain >= 0 else 'loses'} {speed_text(abs(ga.gain))}"], color="highlight" if ga.gain >= 0 else "accent", name="gain", rank=0),
        ]

    # ----- building ----------------------------------------------------------------------------------

    def _build_manoeuvres(self) -> None:
        """The ships' orbits arc by arc, the Δv arrows, a transfer's planned path and phase
        angle, a flyby's overlays and vector diagram (registered as targets)."""
        model = self._model
        self._arc_conics: dict[str, list[tuple[VMobject, np.ndarray, Any]]] = {}
        self._arc_state: dict[str, tuple[int, bool]] = {}
        self._burn_video: dict[int, float] = {}   # burns on words: when (video s)
        for act, when, _ in self.action_times("burn", self._begin):
            for pattern in act.config.targets():
                for n in [f"burn:{k}" for k in range(1, len(model.burns()) + 1) if fnmatchcase(f"burn:{k}", pattern)]:
                    self._burn_video[int(n.partition(":")[2])] = when
        self._burn_parts: list[dict[str, Any]] = []
        self._phase_parts: dict[str, Any] | None = None
        plot = self._lay.plot
        for spec, o in zip(self.params.body_specs(), model.system.orbiters):
            if o.trajectory is None or not spec.orbit:
                continue
            diagonal = math.hypot(plot.width, plot.height) / self._scale
            arcs = [(VGroup(), arc.elements.conic(360, r_max=1.5 * diagonal), arc) for arc in o.trajectory.arcs]
            self._arc_conics[o.name] = arcs
            group = VGroup(*[c for c, _, _ in arcs])
            self.target(f"orbit:{o.name}", group)
            self.add(group)
        burns = model.burns()
        if burns:
            longest = max(float(np.hypot(*b.dv[:2])) for _, b in burns)
            self._dv_scale = DV_SHARE * min(plot.width, plot.height) / max(longest, 1e-9)
            for n, (name, b) in enumerate(burns, start=1):
                self._build_burn(n, name, b)
        if model.transfer is not None:
            self._build_transfer(model.transfer)
        if model.assist is not None:
            self._build_assist(model.assist)

    def _build_burn(self, n: int, name: str, b: Any) -> None:
        o = self._model.system.orbiter(name)
        color = self.theme.color("highlight")
        arrow = new_arrow(color, width=5.0, z=6.0)
        label = self._small_label(self._burn_text(n, b), "highlight")
        ring = Circle(radius=0.09).set_stroke(color, width=3).set_fill(opacity=0).set_z_index(5.9)
        group = VGroup(arrow, ring, label)
        self._burn_parts.append({"number": n, "burn": b, "name": name, "parent": o.parent, "arrow": arrow, "label": label, "ring": ring, "placed": False})
        self.target(f"burn:{n}", group)
        self.add(group)

    def _build_transfer(self, info: Any) -> None:
        """The planned path from the first burn to the last (dashed), the arrival point, and the
        phase angle (lines from the centre to ship and target, an arc, the angle)."""
        model = self._model
        o = model.system.orbiter(info.ship)
        anchor = self._anchor(o.parent)
        ts = np.linspace(info.depart, info.arrival, 240)
        pts = anchor + self._offsets(o.positions(ts))
        color = self._colors.get(info.ship, self.theme.color("highlight"))
        path = plot_draw.series_line(pts, self._lay.plot, color, width=3, dashed=True).set_stroke(opacity=0.8).set_z_index(1.2)
        end = pts[-1]
        mark = Circle(radius=0.08).set_stroke(color, width=3).set_fill(opacity=0).move_to(end).set_z_index(1.3)
        group = VGroup(path, mark)   # its time is in the panel
        self._register_overlay(["transfer"], group, o.parent)
        if info.target is not None:
            lines = VGroup(VMobject(), VMobject()).set_stroke(self.theme.color("dim"), width=2, opacity=0.9).set_z_index(1.4)
            arc = VMobject().set_stroke(self.theme.color("highlight"), width=3).set_z_index(1.5)
            text = VGroup()
            group = VGroup(lines, arc, text)
            self._phase_parts = {"info": info, "lines": lines, "arc": arc, "text": text, "key": None}
            self.target("phase", group)
            if not self._is_held(["phase"]):
                self._intro_parts.append(group)

    def _orbit_lines(self) -> np.ndarray:
        """Frame points along every body's starting orbit (labels placed once keep off them)."""
        if getattr(self, "_orbit_line_cache", None) is None:
            model = self._model
            pts = [np.zeros((0, 3))]
            for o in model.system.orbiters:
                anchor = self._anchor(o.parent)
                pts.append(anchor + self._offsets(o.elements.conic(120, r_max=4 * o.elements.periapsis)))
            self._orbit_line_cache = np.concatenate(pts)[:, :2]
        return self._orbit_line_cache

    def _fixed_obstacles(self) -> list[Any]:
        obstacles = [self._panel_rect()] if self._readout_box is not None else []
        obstacles += [mob_rect(self._central[0], 0.04)] * 3   # a planet drawn large weighs more than the plot edge
        lay = self._lay
        obstacles += [rect_at((lab.x, lab.y), lab.width + 0.08, lab.height + 0.08)
                      for lab in (*lay.x_labels, *lay.y_labels, *[t for t in (lay.x_title, lay.y_title) if t is not None])]
        return obstacles + list(self._static_boxes)

    # ----- the flyby -------------------------------------------------------------------------------

    def _vector_box_size(self) -> tuple[float, float]:
        """The vector diagram's size (0 without one)."""
        model = self._model
        if model.assist is None or not self.params.flyby.vectors:
            return 0.0, 0.0
        return (VECTOR_BOX[0], VECTOR_BOX_PORTRAIT_H) if self.is_portrait else VECTOR_BOX

    def _build_assist(self, info: Any) -> None:
        """In the planet's frame: the asymptotes, the turning angle at their crossing, v∞ in and
        out, the periapsis, the atmosphere, the planet's motion; the vector diagram."""
        ga = info.assist
        fb = ga.flyby
        plot = self._lay.plot
        centre = self._anchor(None)
        dim = self.theme.color("dim")
        text_c = self.theme.color("text")
        u_in = fb.v_in[:2] / fb.v_inf
        u_out = fb.v_out[:2] / fb.v_inf
        c = centre + self._offsets(fb.centre)[0]
        far = 2 * math.hypot(plot.width, plot.height)
        asym = VGroup()
        for u in (u_in, u_out):
            line = np.array([c - far * np.array([*u, 0.0]), c + far * np.array([*u, 0.0])])
            for run in plotcore.clip_polyline(line, plot):
                if len(run) >= 2:
                    asym.add(DashedLine(run[0], run[-1], dash_length=0.12, dashed_ratio=0.45).set_stroke(dim, width=2, opacity=0.7))
        asym.set_z_index(0.8)
        self._register_overlay(["asymptotes"], asym, None, pin=False)
        # the turning angle: from the incoming direction carried on to the outgoing one, at the crossing
        a0 = math.atan2(u_in[1], u_in[0])
        sweep = -fb.delta if fb.clockwise else fb.delta
        room = min(c[0] - plot.x0, plot.x1 - c[0], c[1] - plot.y0, plot.y1 - c[1])
        rad = max(0.2, min(0.55, room - 0.05))   # inside the plot where the asymptotes cross
        angles = np.linspace(a0, a0 + sweep, 48)
        arc = VMobject().set_points_as_corners(np.column_stack([c[0] + rad * np.cos(angles), c[1] + rad * np.sin(angles), np.zeros(48)]))
        arc.set_stroke(self.theme.color("highlight"), width=4).set_z_index(1.6)
        lab = self._small_label(f"δ = {_deg(fb.delta)}", "highlight")
        mid = a0 + sweep / 2
        at = c + np.array([math.cos(mid), math.sin(mid), 0.0]) * (rad + 0.05)
        _, box, _ = place(at, 0.02, lab.width, lab.height, obstacles=self._fixed_obstacles(), plot=self._picture_area,
                          directions=((math.cos(mid), math.sin(mid)), *DIRECTIONS))
        lab.move_to([box.center[0], box.center[1], 0])
        self._static_boxes.append(box)
        self._static_boxes.append(mob_rect(arc, 0.05))
        self._register_overlay(["turn"], VGroup(arc, lab), None, pin=False)
        o = self._model.system.orbiter(info.probe)
        span = self._model.span
        path = centre + self._offsets(o.positions(np.linspace(0.0, span, 200)))
        # the planet's motion (+x of the picture): an arrow in the corner of the plot the path keeps away from
        lab = self._small_label(f"{info.planet}'s motion", "dim", scale=0.8)   # its speed is in the vector diagram
        w, h = 0.6 + 0.1 + lab.width, max(lab.height, 0.2)
        corners = [(plot.x0 + 0.15, plot.y0 + 0.15), (plot.x1 - 0.15 - w, plot.y0 + 0.15), (plot.x0 + 0.15, plot.y1 - 0.15 - h), (plot.x1 - 0.15 - w, plot.y1 - 0.15 - h)]

        s = np.linspace(-far, far, 600)[:, None]
        drawn = np.concatenate([path[:, :2], c[:2] + s * u_in, c[:2] + s * u_out])   # the path and the asymptotes

        def crowd(x: float, y: float) -> float:
            box = plotcore.Rect(x, y, x + w, y + h)
            inside = (drawn[:, 0] > box.x0 - 0.2) & (drawn[:, 0] < box.x1 + 0.2) & (drawn[:, 1] > box.y0 - 0.2) & (drawn[:, 1] < box.y1 + 0.2)
            return float(np.count_nonzero(inside)) + 1000 * sum(overlap_area(box, b) for b in self._fixed_obstacles())

        x, y = min(corners, key=lambda c: crowd(*c))
        motion = new_arrow(dim, width=4.0, z=5.4)
        arrow_shape(motion[0], motion[1], np.array([x, y + h / 2, 0.0]), np.array([0.6, 0.0]), 4.0)
        lab.move_to([x + 0.7 + lab.width / 2, y + h / 2, 0])
        self._static_boxes.append(plotcore.Rect(x, y, x + w, y + h))
        self._register_overlay(["motion"], VGroup(motion, lab), None, pin=False)
        # v∞ in and out: arrows where the pass starts and ends, along the asymptotes
        length = 0.8
        arrows = VGroup()
        for k, (t, u) in enumerate(((0.1 * span, u_in), (0.9 * span, u_out))):
            arrow = new_arrow(text_c, width=4.0, z=5.5)
            where = centre + self._offsets(o.positions(t))[0]
            tail = where - np.array([*u, 0.0]) * (length / 2)
            arrow_shape(arrow[0], arrow[1], tail, np.array(u) * length, 4.0)
            word = "in" if k == 0 else "out"
            lab = self._small_label(f"v∞ {word} {speed_text(fb.v_inf)}", scale=0.85)
            _, box, _ = place(where, 0.12, lab.width, lab.height, obstacles=self._fixed_obstacles() + [mob_rect(arrow, 0.04)], plot=self._picture_area,
                              points=path[:, :2], line_weight=0.05)
            lab.move_to([box.center[0], box.center[1], 0])
            self._static_boxes.append(box)
            arrows.add(VGroup(arrow, lab))
        self._register_overlay(["v_inf"], arrows, None, pin=False)
        # the periapsis, and the atmosphere's top
        p = centre + self._offsets(fb.periapsis_point)[0]
        dot = Dot(p, radius=0.055, color=self.theme.color("highlight")).set_z_index(3.8)
        text = f"periapsis {self._length_text(fb.altitude)} up" if fb.radius > 0 else f"periapsis {self._length_text(fb.rp)}"
        lab = self._small_label(text)
        out = fb.periapsis_point[:2] / np.linalg.norm(fb.periapsis_point[:2])
        _, box, _ = place(p, 0.07, lab.width, lab.height, obstacles=self._fixed_obstacles(), plot=self._picture_area,
                          directions=((float(out[0]), float(out[1])), *DIRECTIONS))
        lab.move_to([box.center[0], box.center[1], 0])
        self._static_boxes.append(box)
        self._register_overlay([f"periapsis:{info.probe}"], VGroup(dot, lab), None, pin=False)
        if fb.atmosphere > 0:
            r = (fb.radius + fb.atmosphere) * self._scale
            ring = DashedVMobject(Circle(radius=max(r, self._central[0].width / 2 + 0.03)), num_dashes=40).set_stroke(dim, width=2, opacity=0.8)
            self._register_overlay(["atmosphere"], ring.move_to(centre).set_z_index(3.1), None, pin=False)
        if self._vector_box is not None:
            self._build_vectors(info)

    def _build_vectors(self, info: Any) -> None:
        """The Sun-frame diagram: the planet's velocity V from O, v∞ in and out from its tip
        (on a dashed circle of radius v∞: the same length), the probe's velocity before and
        after from O, with their speeds."""
        ga = info.assist
        box = self._vector_box
        V = ga.v_planet[:2]
        vin, vout = ga.flyby.v_in[:2], ga.flyby.v_out[:2]
        r = ga.flyby.v_inf
        pts = np.array([[0.0, 0.0], V, V + vin, V + vout, V + [r, 0], V - [r, 0], V + [0, r], V - [0, r]])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        title = self._small_label("in the Sun's frame", "dim", scale=0.8)
        pad = 0.3
        room_w, room_h = box.width - 2 * pad, box.height - 2 * pad - title.height - 0.1
        s = min(room_w / max(hi[0] - lo[0], 1e-9), room_h / max(hi[1] - lo[1], 1e-9))
        ox = box.x0 + pad + (room_w - s * (hi[0] - lo[0])) / 2 - s * lo[0]
        oy = box.y0 + pad + (room_h - s * (hi[1] - lo[1])) / 2 - s * lo[1]

        def at(v: Any) -> np.ndarray:
            return np.array([ox + s * v[0], oy + s * v[1], 0.0])

        title.move_to([box.center[0], box.y1 - pad / 2 - title.height / 2, 0])
        text_c, dim = self.theme.color("text"), self.theme.color("dim")
        before_c, after_c = self.theme.palette_color(0), self.theme.color("highlight")
        circle = DashedVMobject(Circle(radius=r * s), num_dashes=36).set_stroke(dim, width=1.5, opacity=0.7).move_to(at(V))

        def arrow(a: Any, b: Any, color: str, width: float = 4.0) -> VGroup:
            m = new_arrow(color, width=width, z=6.6)
            arrow_shape(m[0], m[1], at(a), at(b) - at(a), width)
            return m

        planet = VGroup(arrow([0, 0], V, text_c), self._small_label(f"{info.planet} {speed_text(float(np.linalg.norm(V)))}", scale=0.8))
        before = VGroup(arrow(V, V + vin, before_c, 3.0), arrow([0, 0], V + vin, before_c),
                        self._small_label(f"before {speed_text(ga.speed_before)}", before_c, scale=0.8))
        after = VGroup(arrow(V, V + vout, after_c, 3.0), arrow([0, 0], V + vout, after_c),
                       self._small_label(f"after {speed_text(ga.speed_after)}", after_c, scale=0.8))
        # the labels where they cover no arrow: each arrow sampled as points to keep off
        steps = np.linspace(0.0, 1.0, 24)[:, None]
        segments = [([0, 0], V), (V, V + vin), (V, V + vout), ([0, 0], V + vin), ([0, 0], V + vout)]
        line = np.concatenate([at(a) + steps * (at(b) - at(a)) for a, b in segments])[:, :2]
        inner = plotcore.Rect(box.x0 + 0.05, box.y0 + 0.05, box.x1 - 0.05, box.y1 - title.height - 0.15)
        taken = [mob_rect(title, 0.03)]
        for lab, a, b in ((planet[1], [0, 0], V), (before[2], [0, 0], V + vin), (after[2], [0, 0], V + vout)):
            mid = (at(a) + at(b)) / 2
            _, spot, _ = place(mid, 0.04, lab.width, lab.height, obstacles=taken, plot=inner, points=line, line_weight=0.08,
                               rings=(0.0, 0.15, 0.3, 0.5, 0.8))
            lab.move_to([spot.center[0], spot.center[1], 0])
            taken.append(spot)
        plate = RoundedRectangle(width=box.width, height=box.height, corner_radius=0.08)
        plate.set_fill(self.theme.background, opacity=0.88).set_stroke(dim, width=1, opacity=0.5).move_to([box.center[0], box.center[1], 0])
        whole = VGroup(plate.set_z_index(6), title.set_z_index(6.5), circle.set_z_index(6.4), planet, before, after)
        for part in (planet, before, after):
            part.set_z_index(6.6)
        self.target("vectors", whole)
        self.target("v_before", before)
        self.target("v_after", after)
        self._register_held(whole, ["vectors", "v_before", "v_after"])

    def _register_held(self, whole: Mobject, names: list[str]) -> None:
        if not self._is_held(names):
            self._intro_parts.append(whole)
        else:   # parts a reveal brings in start hidden; the rest enters with the first beat
            for name in names:
                if not self._is_held([name]):
                    self._intro_parts.append(self.find_targets(name)[0].mobject)

    # ----- per frame ----------------------------------------------------------------------------------

    def _draw_manoeuvres(self, t: float, anchors: dict[str, np.ndarray]) -> None:
        model = self._model
        centre = model.system.central.name
        plot = self._lay.plot
        for name, arcs in self._arc_conics.items():
            o = model.system.orbiter(name)
            now = sum(self._burn_done(n, b, t) for n, (name_n, b) in enumerate(model.burns(), start=1) if name_n == name)
            moves = self._moving(o.parent)
            if self._arc_state.get(name) == (now, moves) and not moves:
                continue
            self._arc_state[name] = (now, moves)
            parent = anchors[o.parent if o.parent is not None else centre]
            for k, (container, rel, arc) in enumerate(arcs):
                if k > now:
                    plot_draw.morph_into(container, None)
                    continue
                line = plot_draw.series_line(self._frame_points(rel + parent), plot, self._colors[name], width=2.5, dashed=not arc.elements.closed or k < now)
                line.set_stroke(opacity=NOW_OPACITY if k == now else PAST_OPACITY).set_z_index(1)
                plot_draw.morph_into(container, line)
        for part in self._burn_parts:
            self._draw_burn(part, t, anchors)
        if self._phase_parts is not None:
            self._draw_phase(t)

    def _draw_burn(self, part: dict[str, Any], t: float, anchors: dict[str, np.ndarray]) -> None:
        b = part["burn"]
        arrow, label, ring = part["arrow"], part["label"], part["ring"]
        if not self._burn_done(part["number"], b, t):
            arrow_shape(arrow[0], arrow[1], np.zeros(3), np.zeros(2), 5.0)
            label.set_opacity(0)
            ring.set_stroke(opacity=0)
            return
        parent = self._frame_point(anchors[part["parent"] if part["parent"] is not None else self._model.system.central.name])
        at = parent + self._offsets(b.position)[0]
        vec = np.array(b.dv[:2]) * self._dv_scale
        length = float(np.hypot(*vec))
        if 0 < length < DV_MIN:
            vec = vec / length * DV_MIN
        arrow_shape(arrow[0], arrow[1], at, vec, 5.0)
        ring.move_to(at).set_stroke(opacity=1)
        if not part["placed"] or self._moving(part["parent"]):
            end = at + np.array([*vec, 0.0])
            obstacles = self._fixed_obstacles() + [mob_rect(p["label"], 0.03) for p in self._burn_parts if p is not part and p["placed"]]
            obstacles += [mob_rect(p[k], 0.03) for p in self._burn_parts if p is part or p["placed"] for k in ("arrow", "ring") if p[k].has_points() or len(p[k].family_members_with_points())]
            pts = np.concatenate(list(self._conic_points.values()))[:, :2] if self._conic_points else None
            _, box, _ = place(end, 0.05, label.width, label.height, obstacles=obstacles, plot=self._picture_area, points=self._orbit_lines() if pts is None else np.concatenate([pts, self._orbit_lines()]), rings=WIDE_RINGS, line_weight=0.01)
            label.move_to([box.center[0], box.center[1], 0])
            part["placed"] = True
        label.set_opacity(1)

    def _draw_phase(self, t: float) -> None:
        """The phase angle: lines from the centre to the ship and the target, live until the
        departure, then held there; the arc between them and the angle."""
        parts = self._phase_parts
        info = parts["info"]
        tp = min(t, info.depart)
        key = round(tp / max(self._model.span, 1e-9) * 2000)
        if parts["key"] == key:
            return
        parts["key"] = key
        model = self._model
        o = model.system.orbiter(info.ship)
        centre = self._anchor(o.parent, tp)
        ship = centre + self._offsets(o.positions(tp))[0]
        target = centre + self._offsets(model.system.orbiter(info.target).positions(tp))[0]
        lines, arc = parts["lines"], parts["arc"]
        for line, end in ((lines[0], ship), (lines[1], target)):   # stopping short of the body: its label stands near it
            d = end - centre
            n = float(np.linalg.norm(d))
            line.set_points_as_corners(np.array([centre, end - d / n * min(0.3, 0.4 * n) if n > 0 else end]))
        lead = self._lead_at(info, tp)
        r_s, v_s = o.states(tp)
        sense = 1.0 if np.cross(r_s, v_s)[2] >= 0 else -1.0
        a0 = math.atan2(ship[1] - centre[1], ship[0] - centre[0])
        rad = 0.35 * min(np.linalg.norm(ship - centre), np.linalg.norm(target - centre))
        angles = a0 + sense * lead * np.linspace(0.0, 1.0, 40)
        arc.set_points_as_corners(np.column_stack([centre[0] + rad * np.cos(angles), centre[1] + rad * np.sin(angles), np.zeros(40)]))
        mid = a0 + sense * lead / 2
        word = "θ" if t < info.depart else "θ at departure"
        lab = self._cached(f"{word} = {_deg(lead)}", self._size * 0.85, "highlight").set_z_index(5)
        at = centre + np.array([math.cos(mid), math.sin(mid), 0.0]) * (rad + 0.08)
        obstacles = ([self._panel_rect()] if self._readout_box is not None else []) + [mob_rect(self._central[0], 0.04)] * 3
        _, box, _ = place(at, 0.02, lab.width, lab.height, obstacles=obstacles, plot=self._lay.plot, rings=WIDE_RINGS,
                          directions=((math.cos(mid), math.sin(mid)), *DIRECTIONS))
        lab.move_to([box.center[0], box.center[1], 0])
        plot_draw.morph_into(parts["text"], VGroup(lab))

    def _manoeuvre_lines(self) -> list[np.ndarray]:
        """Points along the phase angle's two lines (body labels keep off them: densely sampled,
        so a label across one costs more than one across an orbit)."""
        parts = self._phase_parts
        if parts is None:
            return []
        out = []
        for line in parts["lines"]:
            if line.has_points():
                a, b = line.get_start(), line.get_end()
                out.append(a + np.linspace(0.0, 1.0, 400)[:, None] * (b - a))
        return out

    def _burn_done(self, n: int, b: Any, t: float) -> bool:
        """Whether burn n has happened at simulated time t: once the clock passed it, or
        — a burn on a word, which the clock waits for when it falls at the start — once its word
        came."""
        when = getattr(self, "_burn_video", {}).get(n)
        if when is not None and t <= b.time:
            return self._video_now >= when - 1e-9
        return t >= b.time

    def _manoeuvre_boxes(self) -> list[Any]:
        """Where the burns' labels and the phase angle's stand now (body labels keep off them)."""
        boxes = [mob_rect(p[k], 0.03) for p in self._burn_parts if p["placed"] and p["label"].get_fill_opacity() > 0 for k in ("label", "arrow")]
        if self._phase_parts is not None and len(self._phase_parts["text"]):
            boxes += [mob_rect(m, 0.03) for m in self._phase_parts["text"] if m.has_points() or len(m)]
        return boxes

    # ----- the clock -----------------------------------------------------------------------------------

    def _clock_plan(self, start: float, seconds: float) -> Any:
        """The playback: one speed-up, or stretches through a ``burn`` / ``flyby`` on its word
        and the clock held by ``pause`` (until a ``coast`` or the end of the pause's beat)."""
        model = self._model
        burns = model.burns()
        events = [(when, burns[k - 1][1].time, f"burn:{k}") for k, when in self._burn_video.items()]
        for act, when, _ in self.action_times("flyby", self._begin):
            if model.assist is not None:
                events.append((when, model.assist.t_periapsis, "flyby"))
        coasts = sorted(when for _, when, _ in self.action_times("coast", self._begin))
        holds = []
        for _, when, beat_end in self.action_times("pause", self._begin):
            later = [c for c in coasts if c > when]
            holds.append((when, later[0] if later else beat_end, "pause"))
        if not events and not holds:
            return orbits.Playback(start, seconds, model.span)
        try:
            return orbits.Playback.timed(start, seconds, model.span, sorted(set(events)), holds)
        except VidgenError as error:
            raise VidgenError(f"scene '{self.spec.id}': {error}") from None

    def _rate_text(self) -> str:
        play = self._playback
        if play is None:
            return self._lines_static[0] if self._lines_static else ""
        rate = play.rate(self._video_now)
        return "clock paused" if rate == 0 else orbits.speedup_text(rate)


__all__ = ["DV_SHARE", "OrbitManoeuvres", "VECTOR_BOX", "dv_name"]
