"""The Solar System on a date (Phase X, Step 233, DESIGN §98.7): the ``orbit`` scene's ``date``
(the Table 1 planets placed by JPL's approximate elements and rates on that day, the readout a
calendar), ``event`` (the next opposition / conjunction found by root finding, its alignment
drawn), ``radial: log`` (distances compressed, labelled rings instead of axes), ``inset`` (the
inner Solar System to scale in a box beside the picture) and ``sizes`` (radii to scale side by
side: a picture of its own). Params and resolution here; the drawing is the mixin
:class:`OrbitSky`. The ephemeris is :mod:`vidgen.orbits.ephemeris`."""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .orbit_overlays import DIRECTIONS, Slot, mob_rect, place

#: The inset box (16:9 width × height; 9:16 height), Manim units.
INSET_BOX = (3.7, 3.7)
INSET_BOX_PORTRAIT_H = 3.4
#: Candidate ring distances of the log view (AU).
LOG_RINGS = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0)
#: The log view's distance scale: D = log10(1 + r / r0), r0 this share of the smallest periapsis.
LOG_R0_SHARE = 1 / 3
#: Gap between discs in the sizes picture.
SIZE_GAP = 0.3
#: The Sun's limb takes at most this share of the sizes picture's length.
SUN_LIMB = 0.12


class OrbitEvent(SceneParams):
    """The next conjunction or opposition after the date: ``{kind, of, observer}``."""

    kind: Literal["opposition", "conjunction", "inferior_conjunction", "superior_conjunction", "aligned"] = "opposition"
    """opposition (the outer planet opposite the Sun, seen from the observer), conjunction (behind the Sun), inferior_conjunction / superior_conjunction (an inner planet between / beyond), aligned (equal heliocentric longitudes)."""
    of: str
    """The planet (a body of the scene: Mars)."""
    observer: str = "Earth"
    """Where it is seen from (a body of the scene; default Earth)."""


class OrbitSizes(SceneParams):
    """Radii to scale side by side: ``{bodies, sun}``."""

    bodies: list[str] | None = None
    """Body presets to compare (mercury … neptune, pluto, moon, io…); default: the scene's bodies, or the eight planets."""
    sun: bool = True
    """Show the Sun's edge (to the same scale) when the central body is the Sun."""


@dataclass
class SkySpec:
    """The Step 233 params of an ``orbit`` scene, passed to :func:`resolve_model`."""

    date: Any = None
    radial: str = "linear"
    inset: Any = None
    sizes: "OrbitSizes | None" = None
    event: "OrbitEvent | None" = None

    def wanted(self) -> bool:
        return self.date is not None or self.radial != "linear" or self.inset not in (None, False) or self.sizes is not None or self.event is not None


@dataclass
class SkyInfo:
    """A resolved :class:`SkySpec`: the start's Julian date (``None`` without a date), the log
    view and its r0 (m), the inset's radius (m), the event and its time from the start (s), the
    sizes picture's bodies (``None`` without one) and the Sun for it."""

    jd0: float | None = None
    log: bool = False
    r0: float = 0.0
    inset: float | None = None
    event: Any = None
    event_t: float | None = None
    sizes: list[Any] | None = None
    sun: Any = None
    inner: list[str] = field(default_factory=list)


def date_jd(date: Any) -> float:
    """The Julian date of the scene's ``date`` param (checked against Table 1's validity)."""
    jd = orbits.julian_date(date, "date")
    orbits.check_valid(jd, where="date")
    return jd


def dated_preset(preset: Any, jd: float | None, spec: Any, where: str) -> Any:
    """With a date, a Table 1 planet's preset on that date; another preset (the Moon, the ISS, a
    comet…) must be placed by ``nu`` or ``mean_anomaly`` (its position on a date is not modelled)."""
    if jd is None or preset is None:
        return preset
    if preset.key in orbits.TABLE1:
        return orbits.preset_on(preset.key, jd)
    if spec.nu is None and spec.mean_anomaly is None:
        raise VidgenError(f"{where}: with a date, '{preset.key}' has no position on that date here (only the planets and Pluto of JPL's Table 1 have); "
                          "place it yourself with nu or mean_anomaly")
    return preset


def sizes_model(central: Any, bodies: list[Any], spec: OrbitSizes) -> SkyInfo:
    """The sizes picture's bodies (presets with a radius) and the Sun when wanted."""
    if spec.bodies is not None:
        keys = list(spec.bodies)
    elif bodies:
        keys = [b.preset or b.name or "" for b in bodies]
    else:
        keys = ["mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]
    if not keys:
        raise VidgenError("sizes: name at least one body (sizes: {bodies: [earth, mars]})")
    out = []
    for n, k in enumerate(keys, start=1):
        body = orbits.body_preset(k, f"sizes.bodies[{n}]")
        if body.radius <= 0:
            raise VidgenError(f"sizes.bodies[{n}]: {body.name} has no known radius")
        out.append(body)
    centre = (central if isinstance(central, str) else (central.preset or "")).strip().lower()
    sun = orbits.BODIES["sun"] if spec.sun and centre in ("sun", "sol") else None
    return SkyInfo(sizes=out, sun=sun)


def check_sky(sky: SkySpec, *, bodies: list[Any], follow: Any, cannon: Any, transfer: Any, flyby: Any, many: Any, dynamics: str) -> None:
    """Refuse what the log view and the inset cannot show honestly."""
    others = [name for name, given in (("follow", follow), ("cannonball", cannon), ("transfer", transfer), ("flyby", flyby),
                                       ("system / resonance / tides", many is not None and many.wanted(bodies))) if given]
    if sky.radial == "log":
        overlays = [f"bodies[{k}].{what}" for k, b in enumerate(bodies, start=1)
                    for what, on in (("geometry", b.geometry_parts()), ("sectors", b.sector_spec()), ("velocity", b.velocity_spec()), ("burns", b.burns)) if on]
        if others or overlays:
            raise VidgenError(f"radial: log compresses distances, so {', '.join(others + overlays)} would be drawn wrongly on it; use radial: linear "
                              "(with an inset for the inner planets)")
        if dynamics == "nbody":
            raise VidgenError("radial: log shows Kepler orbits; leave out dynamics: nbody")
    if sky.inset not in (None, False):
        if sky.radial == "log":
            raise VidgenError("inset: the log view already shows the inner planets; give radial: log or an inset, not both")
        if others:
            raise VidgenError(f"inset: the inner Solar System's box goes with plain bodies around the central body; leave out {', '.join(others)}")


def inset_radius(inset: Any, system: Any) -> tuple[float, list[str]]:
    """The inset's radius (m) and the bodies whose whole orbits lie in it (around the central
    body). ``true``: just beyond the farthest aphelion below 2 AU (the inner planets)."""
    closed = [o for o in system.orbiters if o.parent is None and o.elements.closed]
    if inset is True:
        inner = [o for o in closed if o.elements.apoapsis < 2 * orbits.AU]
        if not inner:
            raise VidgenError("inset: no body's orbit lies within 2 AU of the central body; give its radius ('1.8 AU')")
        radius = 1.08 * max(o.elements.apoapsis for o in inner)
    else:
        radius = orbits.value_si(inset, "length", "inset")
        if radius <= 0:
            raise VidgenError("inset: give a positive radius ('1.8 AU')")
    names = [o.name for o in closed if o.elements.apoapsis <= radius]
    if not names:
        raise VidgenError(f"inset: no body's whole orbit lies within {radius / orbits.AU:.3g} AU; give a larger radius")
    if len(names) == len(system.orbiters):
        raise VidgenError("inset: every body fits in it; the main picture already shows them (leave out inset or give a smaller radius)")
    return radius, names


def resolve_event(spec: OrbitEvent, jd0: float | None, system: Any) -> tuple[Any, float]:
    """The scene's event (the first after the date) and its time from the start (s)."""
    if jd0 is None:
        raise VidgenError("event: give the scene a date (date: '2020-01-01'); the event is the first one after it")
    names = {o.name.lower(): o.name for o in system.orbiters}
    for role, who in (("of", spec.of), ("observer", spec.observer)):
        if who.strip().lower() not in names:
            raise VidgenError(f"event.{role}: '{who}' is not a body of the scene (bodies: {', '.join(names.values())}); list it with its preset"
                              + did_you_mean(who, list(names.values())))
    ev = orbits.next_event(spec.kind, spec.observer, spec.of, jd0)
    return ev, (ev.jd - jd0) * orbits.DAY


def log_r0(system: Any) -> float:
    """The log view's r0: a third of the smallest periapsis around the central body."""
    qs = [o.elements.periapsis for o in system.orbiters if o.parent is None]
    return LOG_R0_SHARE * min(qs) if qs else orbits.AU / 10


def sky_target_names(params: Any) -> tuple[list[str], bool]:
    """The Step 233 targets of an ``orbit`` scene and whether it is the sizes picture."""
    model = params.model()
    info = getattr(model, "sky", None)
    if info is None:
        return [], False
    if info.sizes is not None:
        return [f"body:{b.name}" for b in info.sizes], True
    names = []
    if info.event is not None:
        names.append("event")
    if info.inset is not None:
        names.append("inset")
    if info.log:
        names.append("rings")
    return names, False


class OrbitSky:
    """Dates, events, the log view, the inset and the sizes picture of an ``orbit`` scene."""

    _log = False   # the log view (set by the scene once it knows)

    # ----- the view's distances ------------------------------------------------------------------

    def _sky(self) -> Any:
        return getattr(self._model, "sky", None)

    def _radial(self, pts: Any) -> np.ndarray:
        """Positions (m) as drawn: unchanged, or in the log view D = log10(1 + r/r0) along the
        same direction (dimensionless)."""
        info = self._sky()
        pts = np.asarray(pts, dtype=float)
        if info is None or not info.log:
            return pts
        r = np.linalg.norm(pts[..., :2], axis=-1)
        d = np.log10(1.0 + r / info.r0)
        with np.errstate(invalid="ignore", divide="ignore"):
            k = np.where(r > 0, d / np.where(r > 0, r, 1.0), 0.0)
        out = pts.copy()
        out[..., 0] = pts[..., 0] * k
        out[..., 1] = pts[..., 1] * k
        return out

    def _log_d(self, metres: float) -> float:
        return math.log10(1.0 + metres / self._sky().r0)

    # ----- the panel -------------------------------------------------------------------------------

    def _sky_head(self) -> list[Slot]:
        """The date row (the panel's first)."""
        info = self._sky()
        if info is None or info.jd0 is None:
            return []
        jd0, span = info.jd0, self._model.span
        probes = sorted({orbits.date_text(jd0 + span / orbits.DAY * k / 40) for k in range(41)}, key=len)[-3:]
        return [Slot(probes, value=lambda t: orbits.date_text(jd0 + t / orbits.DAY), name="date", rank=0)]

    def _sky_slots(self) -> list[Slot]:
        """The event's rows: its name and date, the distance now, the synodic period."""
        info = self._sky()
        if info is None or info.jd0 is None:
            return []
        model = self._model
        slots: list[Slot] = []
        ev = info.event
        if ev is not None:
            slots.append(Slot([ev.text()], color="highlight", name="event", rank=0))
            a, b = ev.observer.capitalize(), ev.target.capitalize()
            obs, tgt = self._body_name(ev.observer), self._body_name(ev.target)
            far = max(float(np.linalg.norm(model.position(obs, t) - model.position(tgt, t))) for t in np.linspace(0, model.span, 60))

            def value(t: float) -> str:
                return f"{a}–{b} {self._length_text(float(np.linalg.norm(model.position(obs, t) - model.position(tgt, t))))}"
            slots.append(Slot([f"{a}–{b} {self._length_text(far * 1.01)}"], value=value, name="distance", rank=1))
            syn = orbits.planet_synodic_period(ev.observer, ev.target)
            slots.append(Slot([f"every {self._time_text(syn)} (synodic period)"], color="dim", scale=0.85, name="synodic", rank=2))
        return slots

    def _body_name(self, key: str) -> str:
        for o in self._model.system.orbiters:
            if o.name.lower() == key.lower():
                return o.name
        return key

    def _time_rank(self) -> int:
        info = self._sky()
        return 2 if info is not None and info.jd0 is not None else 0   # the date says it

    def _sky_notes(self) -> list[Slot]:
        """The log view's own note row (always shown: the distances are not true)."""
        info = self._sky()
        if info is None or not info.log:
            return []
        return [Slot(["distances compressed (log)"], color="dim", name="note", rank=0)]

    # ----- the side box (inset) --------------------------------------------------------------------

    def _vector_box_size(self) -> tuple[float, float]:
        info = self._sky()
        if info is not None and info.inset is not None:
            return (INSET_BOX[0], INSET_BOX_PORTRAIT_H) if self.is_portrait else INSET_BOX
        return super()._vector_box_size()

    # ----- building --------------------------------------------------------------------------------

    def _build_sky(self) -> None:
        info = self._sky()
        self._sky_parts: dict[str, Any] = {}
        if info is None:
            return
        if info.log:
            self._build_rings()
        if info.inset is not None and self._vector_box is not None:
            self._build_inset()
        if info.event is not None:
            self._build_event()

    def _build_rings(self) -> None:
        """The log view's frame: dashed circles at round distances, each labelled."""
        lay = self._lay
        centre = self._frame_point(np.zeros(3))
        per = lay.plot.width / (lay.x.hi - lay.x.lo)
        reach = min(lay.plot.x1 - centre[0], centre[0] - lay.plot.x0, lay.plot.y1 - centre[1], centre[1] - lay.plot.y0)
        dim = self.theme.color("dim")
        group = VGroup()
        radii = []
        for d in LOG_RINGS:
            r = self._log_d(d * orbits.AU) * per
            if r <= reach * 1.02 and r >= 0.5 and (not radii or r - radii[-1][1] >= 0.35):
                radii.append((d, r))
        # the labels along the ray the bodies cross least over the span
        paths = self._paths_in_frame()[:, :2] - centre[:2]
        angles = np.arctan2(paths[:, 1], paths[:, 0])

        def crowd(a: float) -> int:
            return int(np.count_nonzero(np.abs((angles - a + math.pi) % (2 * math.pi) - math.pi) < 0.25))
        ang = min((math.radians(x) for x in (-62, -118, 62, 118, -90, 90, -30, -150)), key=crowd)
        for d, r in radii:
            ring = DashedVMobject(Circle(radius=r), num_dashes=max(16, int(r * 18))).set_stroke(dim, width=1.5, opacity=0.5).move_to(centre)
            lab = self._small_label(f"{d:g} AU", "dim", 1.0)
            side = 1.0 if math.cos(ang) >= 0 else -1.0
            lab.move_to(centre + np.array([math.cos(ang), math.sin(ang), 0.0]) * r + np.array([side * (lab.width / 2 + 0.05), 0.0, 0.0]))
            self._static_boxes.append(mob_rect(lab, 0.04))
            plate = Rectangle(width=lab.width + 0.1, height=lab.height + 0.06).set_fill(self.theme.background, opacity=0.85).set_stroke(width=0)
            plate.move_to(lab.get_center())
            group.add(ring.set_z_index(0.5), plate.set_z_index(2.62), lab.set_z_index(2.65))   # the labels over the orbits and trails
        self._held_target(["rings"], group)

    def _build_inset(self) -> None:
        """The inner Solar System to scale in the side box: the Sun, the inner bodies' orbits and
        dots (moved each frame), a title; the region it shows dashed in the main picture."""
        info = self._sky()
        box = self._vector_box
        model = self._model
        title = self._small_label(f"within {info.inset / orbits.AU:.2g} AU (dashed circle)", "dim", 0.9)
        pad = 0.22
        inner = plotcore.Rect(box.x0 + pad, box.y0 + pad, box.x1 - pad, box.y1 - pad - title.height - 0.1)
        half = min(inner.width, inner.height) / 2
        s = half / info.inset
        c = np.array([(inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2, 0.0])
        title.move_to([box.center[0], box.y1 - pad / 2 - title.height / 2 - 0.04, 0])
        plate = RoundedRectangle(width=box.width, height=box.height, corner_radius=0.08)
        plate.set_fill(self.theme.background, opacity=0.88).set_stroke(self.theme.color("dim"), width=1, opacity=0.5)
        plate.move_to([box.center[0], box.center[1], 0])
        sun = Circle(radius=0.07).set_fill(self._central_color, opacity=1).set_stroke(width=0).move_to(c)
        group = VGroup(plate.set_z_index(6), title.set_z_index(6.5), sun.set_z_index(6.6))
        dots, labels = {}, {}
        for name in info.inner:
            o = model.system.orbiter(name)
            pts = c + o.elements.conic(180) * np.array([s, s, 0.0])
            line = VMobject().set_points_as_corners(pts).set_stroke(self._colors[name], width=2, opacity=0.6).set_z_index(6.55)
            dot = Circle(radius=0.06).set_fill(self._colors[name], opacity=1).set_stroke(self.theme.background, width=1.5).set_z_index(6.8)
            lab = self._small_label(name, "text", 0.9).set_z_index(6.9)
            dots[name], labels[name] = dot, lab
            group.add(line, dot, lab)
            main_dot, _ = self._bodies[name]
            self._bodies[name] = (main_dot, VGroup())   # named in the inset (the main picture's labels would pile up at the Sun)
        sun_label = self._small_label(model.system.central.name, "text", 0.9).set_z_index(6.9)   # the Sun named in the inset too
        sun_label.next_to(sun, DOWN, buff=0.06)
        labels[model.system.central.name] = sun_label
        dots[model.system.central.name] = sun
        group.add(sun_label)
        self._central = (self._central[0], VGroup())
        ring = DashedVMobject(Circle(radius=max(info.inset * self._scale, 0.05)), num_dashes=24).set_stroke(self.theme.color("dim"), width=1.5, opacity=0.8)
        ring.move_to(self._frame_point(np.zeros(3))).set_z_index(2.7)
        group.add(ring)
        self._sky_parts["inset"] = {"c": c, "s": s, "dots": dots, "labels": labels, "rect": inner, "sun": sun, "sides": {}}
        self._held_target(["inset"], group)

    def _build_event(self) -> None:
        """The event's alignment: a dashed line from the Sun through both planets where they will
        be (or were) at the event, with its name and date."""
        info = self._sky()
        ev = info.event
        model = self._model
        t = info.event_t
        obs, tgt = self._body_name(ev.observer), self._body_name(ev.target)
        sun = self._frame_point(np.zeros(3))
        ends = [self._frame_point(model.view(n, t)) for n in (obs, tgt)]
        far = max(ends, key=lambda p: float(np.linalg.norm(p - sun)))
        u = (far - sun) / max(float(np.linalg.norm(far - sun)), 1e-9)
        tip = far + u * 0.35
        if ev.kind in ("conjunction", "superior_conjunction"):   # the planets on either side of the Sun
            near = min(ends, key=lambda p: float(np.linalg.norm(p - sun)))
            v = (near - sun) / max(float(np.linalg.norm(near - sun)), 1e-9)
            start = near + v * 0.35
        else:
            start = sun
        line = DashedLine(start, tip, dash_length=0.1, dashed_ratio=0.5).set_stroke(self.theme.color("highlight"), width=2.5, opacity=0.8).set_z_index(1.2)
        marks = VGroup(*[Circle(radius=0.11).set_stroke(self.theme.color("highlight"), width=2.5).set_fill(opacity=0).move_to(p) for p in ends]).set_z_index(3.9)
        lab = self._small_label(ev.kind.replace("_", " "), "highlight", 1.0)   # its date is in the panel
        lines = np.array([start + (tip - start) * k for k in np.linspace(0, 1, 30)])[:, :2]
        _, box, _ = place(tip, 0.05, lab.width, lab.height, obstacles=self._fixed_obstacles() + [mob_rect(m, 0.03) for m in marks], plot=self._picture_area,
                          points=np.concatenate([lines, self._paths_in_frame()[:, :2]]), line_weight=0.05,
                          directions=((float(u[0]), float(u[1])), *DIRECTIONS))
        lab.move_to([box.center[0], box.center[1], 0]).set_z_index(5)
        self._static_boxes.append(box)
        self._held_target(["event"], VGroup(line, marks, lab))

    # ----- drawing ---------------------------------------------------------------------------------

    def _draw_sky(self, t: float) -> None:
        part = getattr(self, "_sky_parts", {}).get("inset")
        if part is None:
            return
        model = self._model
        c, s = part["c"], part["s"]
        taken = [mob_rect(part["sun"], 0.03)]
        at = {}
        for name, dot in part["dots"].items():
            p = model.view(name, t)
            at[name] = c + np.array([float(p[0]) * s, float(p[1]) * s, 0.0])
            dot.move_to(at[name])
        for name, lab in part["labels"].items():
            others = [mob_rect(d, 0.02) for n, d in part["dots"].items() if n != name]
            k, box, _ = place(at[name], 0.06, lab.width, lab.height, obstacles=taken + others, plot=part["rect"], rings=(0.0, 0.12, 0.25),
                              prev=part["sides"].get(name))
            part["sides"][name] = k
            lab.move_to([box.center[0], box.center[1], 0])
            taken.append(box)

    # ----- the sizes picture -------------------------------------------------------------------------

    def _construct_sizes(self, begin: float) -> None:
        """Radii to one scale side by side (in a column in 9:16), the Sun's edge first, each
        disc's name and radius under it (beside it in 9:16); "sizes to scale; distances not"."""
        p = self.params
        info = self._sky()
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
        note = self._small_label("radii to scale (distances are not)", "dim", 1.0)
        if portrait:   # the note under the title; the Sun's edge at the bottom, running off the frame
            note.move_to([(body.x0 + body.x1) / 2, body.y1 - note.height / 2, 0])
            area = plotcore.Rect(body.x0, body.y0, body.x1, body.y1 - note.height - 0.25)
        else:
            note.move_to([(body.x0 + body.x1) / 2, body.y0 + note.height / 2, 0])
            area = plotcore.Rect(body.x0, body.y0 + note.height + 0.25, body.x1, body.y1)
        fw, fh = self.camera.frame_width, self.camera.frame_height
        names = [self._label(b.name, size) for b in info.sizes]
        radii = [self._small_label(_radius_text(b.radius), "dim", 1.0) for b in info.sizes]
        rs = np.array([b.radius for b in info.sizes])
        length = area.height if portrait else area.width
        across = area.width if portrait else area.height
        limb = SUN_LIMB * length if info.sun is not None else 0.0

        def need(s: float) -> list[float]:   # the room each body takes along the row (or column)
            if portrait:
                return [max(2 * r * s, n.height + m.height + 0.08) for r, n, m in zip(rs, names, radii)]
            # labels in two staggered rows; the row's ends keep their whole label inside
            last = len(rs) - 1
            return [max(2 * r * s, (1.0 if k == last or (k == 0 and info.sun is None) else 0.55) * max(n.width, m.width))
                    for k, (r, n, m) in enumerate(zip(rs, names, radii))]

        text_across = max(max(n.width, m.width) for n, m in zip(names, radii)) + 0.2 if portrait else 2 * (max(n.height + m.height for n, m in zip(names, radii)) + 0.12) + 0.2
        lo, hi = 0.0, (across - text_across) / (2 * float(rs.max()))
        for _ in range(60):   # the largest scale at which every disc and its text fit
            mid = (lo + hi) / 2
            if sum(need(mid)) + SIZE_GAP * (len(rs) - 1) + limb + (SIZE_GAP if limb else 0.0) <= length:
                lo = mid
            else:
                hi = mid
        s = lo
        if s * float(rs.max()) < 0.05:
            raise VidgenError(f"scene '{self.spec.id}': sizes: {len(rs)} bodies and their names do not fit one {'column' if portrait else 'row'}; compare fewer")
        rooms = need(s)
        used = sum(rooms) + SIZE_GAP * (len(rs) - 1) + limb + (SIZE_GAP if limb else 0.0)
        line_c = (area.y0 + area.y1) / 2 + text_across / 2   # the discs' centres (16:9)
        sun_group = VGroup()
        if info.sun is not None:   # the Sun's edge: a circle of the same scale, its centre off the picture, at the start of the row (16:9) or the column's foot (9:16)
            R = info.sun.radius * s
            sun_color = self.theme.color(info.sun.color or "highlight")
            sun_label = self._label(f"Sun {_radius_text(info.sun.radius)}", size).set_color(self.theme.background)
            if portrait:
                edge = area.y0 + limb   # the limb's top
                cx, cy = (area.x0 + area.x1) / 2, edge - R
                window = plotcore.Rect(-fw / 2, area.y0 if caption is not None else -fh / 2, fw / 2, edge + 0.01)   # to the frame's edge, not past it
                sun_label.move_to([cx, edge - sun_label.height / 2 - 0.15, 0])
                pos = area.y0 + used   # the planets above it, from the top down
            else:
                edge = area.x0 + limb   # the limb's right edge
                cx, cy = edge - R, line_c
                window = plotcore.Rect(-fw / 2, area.y0, edge + 0.01, area.y1)
                sun_label.rotate(math.pi / 2).move_to([edge - sun_label.width / 2 - 0.15, cy, 0])
                pos = edge + SIZE_GAP
            disc = Circle(radius=R, num_components=240).move_to([cx, cy, 0])
            frame = Rectangle(width=window.width, height=window.height).move_to([window.center[0], window.center[1], 0])
            clip = Intersection(disc, frame).set_fill(sun_color, opacity=1).set_stroke(width=0)
            sun_group = VGroup(clip, sun_label)
        else:
            pos = (area.y1 - (length - used) / 2) if portrait else (area.x0 + (length - used) / 2)
        discs = VGroup()
        groups = []
        # the discs' column and the text beside it, centred across the picture (9:16)
        col_x = (area.x0 + area.x1) / 2 - (2 * float(rs.max()) * s + text_across) / 2 + float(rs.max()) * s
        for b, r, room, n, m in zip(info.sizes, rs, rooms, names, radii):
            color = self.theme.color(b.color or "primary")
            d = Circle(radius=max(r * s, 0.012)).set_fill(color, opacity=1).set_stroke(width=0)
            if portrait:
                cy = pos - room / 2
                d.move_to([col_x, cy, 0])
                x = col_x + rs.max() * s + 0.2
                n.move_to([x + n.width / 2, cy + n.height / 2 + 0.04, 0])
                m.move_to([x + m.width / 2, cy - m.height / 2 - 0.04, 0])
                pos -= room + SIZE_GAP
            else:
                cx = pos + room / 2
                d.move_to([cx, line_c, 0])
                bottom = line_c - rs.max() * s
                drop = 0.0 if len(groups) % 2 == 0 else max(x.height + y.height for x, y in zip(names, radii)) + 0.12
                n.move_to([cx, bottom - 0.15 - drop - n.height / 2, 0])
                m.move_to([cx, n.get_bottom()[1] - 0.06 - m.height / 2, 0])
                pos += room + SIZE_GAP
            discs.add(d)
            groups.append(VGroup(d, n, m))
        self._readout = VGroup()
        if title is not None:
            self.target("title", title)
        self.target("frame", VGroup(note, *([caption] if caption is not None else [])))
        if info.sun is not None:
            self.target("central", sun_group)
        for b, g in zip(info.sizes, groups):
            self.target(f"body:{b.name}", g)
        held = self._held_patterns()
        intro = [g for b, g in zip(info.sizes, groups) if f"body:{b.name}" not in held]

        def entrance(d: float) -> list[Animation]:
            anims = [FadeIn(m) for m in (title, caption, note) if m is not None]
            if info.sun is not None and "central" not in held:
                anims.append(FadeIn(sun_group))
            anims += [FadeIn(g) for g in intro]
            self.play(*anims, run_time=min(1.2, max(0.3 * d, 1 / config.frame_rate)))
            return []

        for i, dur in self.timeline():
            if i == 0:
                self.play_steps(dur, [lambda: entrance(dur)], fraction=0.8, cap=1.5)
        self.finish()


def _radius_text(metres: float) -> str:
    return f"{metres / 1000:,.0f} km"


__all__ = ["INSET_BOX", "LOG_RINGS", "OrbitEvent", "OrbitSizes", "OrbitSky", "SkyInfo", "SkySpec", "check_sky", "date_jd", "dated_preset", "inset_radius",
           "log_r0", "resolve_event", "sizes_model", "sky_target_names"]
