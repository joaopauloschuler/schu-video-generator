"""``orbit``: bodies on their orbits, moving in correct timing (Phase X, DESIGN §98). A central
body, bodies from presets, orbital elements or a position and velocity, their orbits drawn as
conics, the bodies moving along them by Kepler's equation (or by n-body integration with
leapfrog / RK45), fading trails, an equal-aspect frame on the plot core (AU or km ticks, or a
scale bar), a readout of the simulated time and the speed-up, and a view that can follow a
body. The bodies move from the end of the first beat's entrance to the scene's end at one
constant speed-up, so equal video times are equal simulated times and Kepler's second law shows
as it is. The params and the model are in ``orbit_parts.py``; the physics in ``vidgen.orbits``."""

import math
from dataclasses import replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .orbit_parts import OrbitBody, OrbitCentral, OrbitModel, Value, resolve_model

#: Smallest drawn radius (Manim units) of the central body and of an orbiting body: smaller
#: bodies are enlarged to it (and the readout says "sizes not to scale").
MIN_CENTRAL_RADIUS = 0.12
MIN_BODY_RADIUS = 0.075
#: A trail is drawn as this many pieces, fading towards its tail.
TRAIL_PIECES = 8
TRAIL_SAMPLES = 64
#: Points along a drawn conic.
CONIC_SAMPLES = 360
#: A margin around the data, as a share of its span (as the plot scene's equal aspect).
MARGIN = 0.06
#: Space between the plot and the readout box.
BOX_GAP = 0.45
#: The sides a body's label may take (x, y signs), in order of preference, and its gap.
LABEL_SIDES = ((1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))
LABEL_GAP = 0.06
#: Resolved models by the params' JSON (validation, vidgen validate and the render resolve a
#: scene more than once; an n-body run takes a moment).
_MODELS: dict[str, OrbitModel] = {}
MODEL_CACHE = 32


@scene("orbit")
class Orbit(NarratedScene):
    """Orbits in correct timing: a central body (``central``: a preset or your own) and
    ``bodies`` on Kepler orbits (presets, elements, or a position and velocity), drawn as conics
    with the bodies moving along them through the whole scene at one speed-up (``span`` or
    ``orbits`` of simulated time), fading trails, an equal-aspect frame in AU or km (``frame``:
    axes, a scale bar or none), a readout of the time and speed-up, ``follow`` to move with a
    body, ``dynamics: nbody`` for mutual gravity (leapfrog, with the energy error shown).

    Action targets: ``title``, ``frame``, ``central``, ``body:<name>``, ``orbit:<name>``,
    ``readout``.
    """

    outro = 0.5
    target_patterns = ("title", "frame", "central", "body:<name>", "orbit:<name>", "readout")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        central: str | OrbitCentral = "sun"
        """The central body: a preset (sun, earth, mars, jupiter, moon...) or {name, gm or mass, radius}."""
        bodies: list[OrbitBody] = Field(min_length=1)
        """The orbiting bodies: [{preset: earth}, {name: Probe, a: '1.5 AU', e: 0.4}, {name: Ship, r: ['7000 km', 0], v: [0, '8 km/s']}]."""
        span: Value | None = None
        """Simulated time the scene shows ('1 yr', '92 min', '30 d'); or orbits."""
        orbits: float | None = Field(default=None, gt=0)
        """Simulated time in periods of the first body (default 1 when span is not given; a closed orbit)."""
        dynamics: Literal["kepler", "nbody"] = "kepler"
        """kepler: each body on its two-body orbit (exact, Kepler's equation); nbody: every body with mass pulls on every other (integrated)."""
        method: str = "leapfrog"
        """n-body method: leapfrog (velocity Verlet, symplectic: energy error bounded) or rk45 (adaptive; drifts over long runs)."""
        step: Value | None = None
        """n-body leapfrog step ('1 h'); default 1/1000 of the shortest orbital time scale."""
        frame: Literal["axes", "scale_bar", "none"] = "axes"
        """axes: x and y axes with AU or km ticks (equal aspect); scale_bar: a bar of a round length; none."""
        unit: Literal["auto", "AU", "km"] = "auto"
        """Unit of the axes and scale bar; auto: AU when the view spans more than 0.05 AU, else km."""
        extent: Value | None = None
        """Half-width of the view around its centre ('2 AU'); default: every orbit with a margin."""
        follow: str | None = None
        """A body the view moves with (its satellites' orbits stay still around it); default: the central body stays at the centre."""
        readout: bool = True
        """Show the simulated time and the speed-up (and the energy error with nbody)."""
        energy: bool | None = None
        """Show the n-body energy error ΔE/E (default: on with dynamics: nbody)."""
        label_size: ThemeSize | None = None
        """Size of tick labels, body labels and the readout (never below the readable minimum); default: caption (the picture gets the room)."""
        caption: TranslatableStr = ""
        """Note under the picture (e.g. the source of the elements)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title color."""

        @model_validator(mode="after")
        def _consistent(self) -> "Orbit.Params":
            if self.energy and self.dynamics != "nbody":
                raise ValueError("energy: the energy error is shown for dynamics: nbody (Kepler orbits conserve it exactly)")
            if self.method != "leapfrog" and self.dynamics != "nbody":
                raise ValueError("method is the n-body integrator; it needs dynamics: nbody")
            try:
                self.model()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

        def model(self) -> OrbitModel:
            """The resolved system, span, n-body run and trails (cached)."""
            key = self.model_dump_json()
            if key not in _MODELS:
                if len(_MODELS) >= MODEL_CACHE:   # a long-running process (the MCP server) keeps the recent ones
                    del _MODELS[next(iter(_MODELS))]
                _MODELS[key] = resolve_model(self.central, self.bodies, span=self.span, orbit_count=self.orbits, dynamics=self.dynamics,
                                             method=self.method, step=self.step, follow=self.follow)
            return _MODELS[key]

        def shows_energy(self) -> bool:
            return self.dynamics == "nbody" and self.energy is not False

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        names = (["title"] if params.title else []) + ["frame", "central"]
        model = params.model()
        for spec, o in zip(params.bodies, model.system.orbiters):
            names.append(f"body:{o.name}")
            if spec.orbit:
                names.append(f"orbit:{o.name}")
        if params.readout or params.shows_energy():
            names.append("readout")
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """What a target is called on screen (for the narration lint): a body's label, the title."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        if kind == "body":
            for spec in params.bodies:
                if spec.display_name() == key:
                    return str(spec.label) or key
        if kind == "central":
            central = params.central
            return (str(central.label) or central.name or central.preset) if isinstance(central, OrbitCentral) else central.capitalize()
        return None

    # ----- building ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._clock_mob = Mobject().set_z_index(-1000)   # first in the scene: while it updates, every frame is redrawn
        self.add(self._clock_mob)
        begin = float(self.renderer.time)
        model = p.model()
        self._model = model
        portrait = self.is_portrait
        size = chart_label_size(p.label_size if p.label_size is not None else "caption", self.theme)
        self._size = size
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, color=p.title_color, area=self.safe_area)
            body = body.below(title, gap=0.35)
        caption = None
        if p.caption:
            caption = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(caption, gap=0.25)

        # the extent of what the view must show, in metres, and the unit it is shown in
        xs, ys = self._extent_points(model)
        fixed = orbits.value_si(p.extent, "length", "extent") if p.extent is not None else None
        if fixed is not None and fixed <= 0:
            raise VidgenError(f"scene '{self.spec.id}': extent must be positive")
        reach = fixed if fixed is not None else max(np.max(np.abs(xs)), np.max(np.abs(ys)))
        unit_name, unit_m = orbits.length_unit(reach, p.unit)
        self._unit_m = unit_m

        # the readout box (time, speed-up, energy, "sizes not to scale"), beside (16:9) or above (9:16)
        self._begin = begin
        # provisional (the motion starts after the entrance; _intro writes the exact one)
        self._lines_static = [orbits.speedup_text(model.span / self._motion_seconds())] if p.readout else []
        t_unit, t_scale = orbits.time_unit(model.span)
        self._t_unit = (t_unit, t_scale)
        probe = [self._time_line(model.span * k / 200) for k in range(201)] if p.readout else []
        energy_probe = [self._energy_line(-1.23e-10), self._energy_line(-9.99e-9)] if p.shows_energy() else []
        side_w = side_h = 0.0
        measure = plot_draw.text_measure(size, self.theme)
        widest = [max(probe, key=lambda t: measure(t)[0])] if probe else []
        widest += self._lines_static + energy_probe[:1]
        self._note = ""   # "sizes not to scale", known once the drawing scale is
        note_measure = plot_draw.text_measure(size * 0.85, self.theme, "dim")
        note_w, note_h = note_measure("sizes not to scale")
        if widest:
            dims = [measure(t) for t in widest]
            side_w = max(max(d[0] for d in dims), note_w) + 0.1 + 2 * plot_draw.PLATE_PAD
            side_h = sum(d[1] for d in dims) + note_h + 0.14 * len(dims) * size / 24 + 2 * plot_draw.PLATE_PAD
        right, top = (0.0, side_h + BOX_GAP) if portrait and widest else ((side_w + BOX_GAP, 0.0) if widest else (0.0, 0.0))
        area = plotcore.Rect(body.x0, body.y0, body.x1 - right, body.y1)
        lay = self._layout(area, xs / unit_m, ys / unit_m, None if fixed is None else fixed / unit_m, unit_name, measure, top)
        # the readout box beside the plot (16:9) or above it (9:16), then both centred in the body
        box = None
        if widest:
            if portrait:
                mid = (lay.plot.x0 + lay.plot.x1) / 2
                box = plotcore.Rect(mid - side_w / 2, area.y1 - side_h, mid + side_w / 2, area.y1)
            else:
                box = plotcore.Rect(lay.plot.x1 + BOX_GAP, lay.plot.y1 - side_h, lay.plot.x1 + BOX_GAP + side_w, lay.plot.y1)
        x0, y0, x1, y1 = _bounds(lay, box)
        dx, dy = (body.x0 + body.x1 - x0 - x1) / 2, (body.y0 + body.y1 - y0 - y1) / 2
        lay = _shifted(lay, dx, dy)
        if box is not None:
            box = plotcore.Rect(box.x0 + dx, box.y0 + dy, box.x1 + dx, box.y1 + dy)
        self._lay = lay
        self._scale = lay.plot.width / (lay.x.hi - lay.x.lo) / unit_m   # Manim units per metre

        frame_parts = self._frame(lay, unit_name, size)
        colors = {o.name: self.theme.color(spec.color) if spec.color else self.theme.palette_color(k) for k, (spec, o) in enumerate(zip(p.bodies, model.system.orbiters))}
        self._colors = colors
        central_spec = p.central if isinstance(p.central, OrbitCentral) else OrbitCentral(preset=p.central)
        centre = model.system.central
        central_color = self.theme.color(central_spec.color or centre.color or "highlight")
        enlarged = False
        true_r = centre.radius * self._scale
        central_dot = Circle(radius=max(true_r, MIN_CENTRAL_RADIUS)).set_fill(central_color, opacity=1).set_stroke(width=0).set_z_index(3)
        enlarged |= centre.radius > 0 and true_r < MIN_CENTRAL_RADIUS
        central_label = self._label(str(central_spec.label) or centre.name, size) if central_spec.show_label else VGroup()
        self._central = (central_dot, central_label)

        self._bodies: dict[str, tuple[Any, Any]] = {}
        for spec, o in zip(p.bodies, model.system.orbiters):
            r = o.body.radius * self._scale
            enlarged |= o.body.radius > 0 and r < MIN_BODY_RADIUS
            dot = Circle(radius=max(r, MIN_BODY_RADIUS)).set_fill(colors[o.name], opacity=1)
            dot.set_stroke(self.theme.background, width=2).set_z_index(4)
            label = self._label(str(spec.label) or o.name, size) if spec.show_label else VGroup()
            self._bodies[o.name] = (dot, label)
        self._note = "sizes not to scale" if enlarged else ""

        # orbits (conics around each body's parent; moved with the parent when it moves in the view)
        self._conics: dict[str, tuple[VGroup, Any, bool]] = {}
        diagonal = math.hypot(lay.plot.width, lay.plot.height) / self._scale
        for spec, o in zip(p.bodies, model.system.orbiters):
            if not spec.orbit:
                continue
            rel = o.elements.conic(CONIC_SAMPLES, r_max=1.5 * diagonal)
            moves = model.run is not None or not (o.parent == model.follow)
            container = VGroup()
            self._conics[o.name] = (container, rel, moves)
        # trails: TRAIL_PIECES pieces fading to the tail
        self._trails = {name: VGroup(*[VMobject() for _ in range(TRAIL_PIECES)]) for name, seconds in model.trails.items() if seconds > 0}
        for name, group in self._trails.items():
            for k, piece in enumerate(group):
                piece.set_stroke(colors[name], width=4, opacity=0.08 + 0.8 * (k + 1) / TRAIL_PIECES)
            group.set_z_index(2)

        self._readout = VGroup()
        self._readout_box = box
        self._label_sides: dict[int, int] = {}
        self._last_lines: tuple[str, ...] | None = None
        self._label_cache: dict[str, Any] = {}

        self._t = 0.0
        self._draw(0.0)
        self._register(title, caption, frame_parts)

        self._playback = None
        for i, d in self.timeline():
            if i == 0:
                self.play_steps(d, [lambda: self._intro(d)], fraction=0.8, cap=1.5)
            elif self.capture is not None and self._current_beat is not None:
                fps = config.frame_rate
                self.capture.add_mid_still(self._current_beat, round(float(self.renderer.time) * fps), round(d * fps), "orbit")
        self.finish()
        self._stop()

    def _motion_seconds(self) -> float:
        """Video seconds the scene lasts before its outro (each beat in whole frames, as
        :meth:`narrate` waits them)."""
        if self.beats:
            fps = config.frame_rate
            return sum(round(self.beat_window(b).window * fps) for b in self.beats) / fps
        return max((self.spec.duration or 0.0) - self.outro, 1 / config.frame_rate)

    def _extent_points(self, model: OrbitModel) -> tuple[np.ndarray, np.ndarray]:
        """x and y (m) of what the view must show: every body over the span in the view's
        frame and the whole closed orbits around a still centre; an open orbit only out to three
        times the size of the rest."""
        ts = np.linspace(0.0, model.span, 400)
        system = model.system
        follow = model.follow
        shown = [o for o in system.orbiters if follow is None or follow in [c.name for c in system.chain(o.name)[1:]]]
        if not shown:
            shown = [o for o in system.orbiters if o.name != follow]
        points = [np.zeros((1, 3))]
        open_points = []
        for o in shown:
            path = model.view(o.name, ts)
            still = o.parent == follow and model.run is None
            if o.elements.closed:
                points.append(path)
                if still:
                    points.append(o.elements.conic(120))
            else:
                open_points.append(path)
        if not shown and follow is not None:
            points.append(model.view(system.central.name, ts))
        closed = np.concatenate(points)
        reach = float(np.max(np.linalg.norm(closed[:, :2], axis=1)))
        if open_points:
            peri = max(o.elements.periapsis for o in shown if not o.elements.closed)
            cap = 3 * max(reach, peri)
            if follow is None:   # the open conics out to that distance (a flyby is seen whole)
                open_points += [o.elements.conic(120, r_max=cap) for o in shown if not o.elements.closed and o.parent is None]
            pts = np.concatenate(open_points)
            pts = pts[np.linalg.norm(pts[:, :2], axis=1) <= cap * (1 + 1e-9)]
            closed = np.concatenate([closed, pts]) if len(pts) else closed
        return closed[:, 0], closed[:, 1]

    def _layout(self, area: Any, xs: np.ndarray, ys: np.ndarray, extent: float | None, unit: str, measure: Any, top: float) -> Any:
        """The plot rectangle and its axes at an equal aspect: through the plot core with
        ``frame: axes``, else the data's box widened to the area's shape."""
        p = self.params
        portrait = self.is_portrait
        if extent is not None:
            x_lo, x_hi, y_lo, y_hi = -extent, extent, -extent, extent
        else:   # the data's box with a margin: the plot hugs the orbits (no axis runs on past them)
            x_lo, x_hi, y_lo, y_hi = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
            span = max(x_hi - x_lo, y_hi - y_lo, 1e-12)
            x_lo, x_hi = x_lo - MARGIN * span, x_hi + MARGIN * span
            y_lo, y_hi = y_lo - MARGIN * span, y_hi + MARGIN * span
        if p.frame == "axes":
            def spec(label: str, lo: float, hi: float, ticks: int) -> Any:
                return plotcore.AxisSpec(lo=lo, hi=hi, unit=unit, label=label, max_ticks=ticks, exact=True)
            panel = plotcore.PanelInput((), (), spec("x", x_lo, x_hi, 4 if portrait else 6), spec("y", y_lo, y_hi, 6 if portrait else 5))
            try:
                return plotcore.layout_figure(area, [panel], measure, top=top, aspect="equal")[0]
            except VidgenError as error:
                raise VidgenError(f"scene '{self.spec.id}': {error}") from None
        free = plotcore.Rect(area.x0, area.y0, area.x1, area.y1 - top)
        s = min(free.width / (x_hi - x_lo), free.height / (y_hi - y_lo))
        w, h = s * (x_hi - x_lo), s * (y_hi - y_lo)
        cx, cy = free.center
        plot = plotcore.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return plotcore.PanelLayout(plot, plotcore.Axis("linear", x_lo, x_hi, (), ()), plotcore.Axis("linear", y_lo, y_hi, (), ()), (), (), None, None, (), ())

    def _frame(self, lay: Any, unit: str, size: float) -> VGroup:
        """The axes (``frame: axes``), a scale bar (``scale_bar``) or nothing."""
        p = self.params
        if p.frame == "axes":
            return plot_draw.draw_panel(lay, size=size, grid="major", theme=self.theme).group
        if p.frame == "none":
            return VGroup()
        span = (lay.x.hi - lay.x.lo) / 4
        k = math.floor(math.log10(span))
        length = max(m * 10**k for m in (1, 2, 5) if m * 10**k <= span)
        per_unit = lay.plot.width / (lay.x.hi - lay.x.lo)
        x0, y0 = lay.plot.x0 + 0.25, lay.plot.y0 + 0.3
        x1 = x0 + length * per_unit
        dim = self.theme.color("dim")
        bar = VGroup(Line([x0, y0, 0], [x1, y0, 0]), Line([x0, y0 - 0.07, 0], [x0, y0 + 0.07, 0]), Line([x1, y0 - 0.07, 0], [x1, y0 + 0.07, 0]))
        bar.set_stroke(dim, width=3)
        text = plotcore.plain_number(length, max(0, -k)) if length < 1e5 else plotcore.sci_number(length, 1)
        label = plot_draw.label_text(f"{text} {unit}", size=size, color="dim", theme=self.theme)
        label.next_to(bar, UP, buff=0.1).align_to(bar, LEFT)
        return VGroup(bar, label)

    def _label(self, text: str, size: float) -> Mobject:
        return plot_draw.label_text(text, size=size, theme=self.theme).set_z_index(5)

    def _register(self, title: Any, caption: Any, frame_parts: VGroup) -> None:
        p = self.params
        if title is not None:
            self.target("title", title)
        self._title, self._caption = title, caption
        self._frame_parts = frame_parts
        self.target("frame", VGroup(frame_parts, *([caption] if caption is not None else [])))
        self.target("central", VGroup(*self._central))
        for spec, o in zip(p.bodies, self._model.system.orbiters):
            dot, label = self._bodies[o.name]
            parts = [dot, label] + ([self._trails[o.name]] if o.name in self._trails else [])
            self.target(f"body:{o.name}", VGroup(*parts))
            if o.name in self._conics:
                self.target(f"orbit:{o.name}", self._conics[o.name][0])
        if self._readout_box is not None:
            self.target("readout", self._readout)

    # ----- motion -----------------------------------------------------------------------------

    def _intro(self, d: float) -> list[Animation]:
        """The first beat's entrance (frame, title, central body, orbits drawn, bodies), then the
        motion starts and runs in every wait and play to the scene's end."""
        anims: list[Animation] = []
        if self._title is not None:
            anims.append(FadeIn(self._title))
        if self._caption is not None:
            anims.append(FadeIn(self._caption))
        if len(self._frame_parts):
            anims.append(FadeIn(self._frame_parts))
        dot, label = self._central
        anims.append(GrowFromCenter(dot))
        if len(label):
            anims.append(FadeIn(label))
        for container, _, _ in self._conics.values():
            if len(container):
                anims.append(Create(container))
        for dot, label in self._bodies.values():
            anims.append(FadeIn(dot))
            if len(label):
                anims.append(FadeIn(label))
        if len(self._readout):
            anims.append(FadeIn(self._readout))
        self.play(*anims, run_time=min(1.2, max(0.3 * d, 1 / config.frame_rate)))
        for group in self._trails.values():
            self.add(group)
        start = float(self.renderer.time)
        end = self._begin + self._motion_seconds()
        self._playback = orbits.Playback(start, max(end - start, 1 / config.frame_rate), self._model.span)
        if self.params.readout:
            self._lines_static = [orbits.speedup_text(self._playback.speedup)]
        def update(_: Mobject, dt: float) -> None:
            # the scene's clock (the frame about to be written), not a sum of dt: manim gives the
            # first frame of every play and wait a dt of 0
            self._draw(self._playback.sim_time(float(self.renderer.time)))

        self._update = update
        self._clock_mob.add_updater(update)
        if self.capture is not None and self._current_beat is not None:
            fps = config.frame_rate
            left = max(d - (start - self._beat_start), 1 / fps)
            self.capture.add_mid_still(self._current_beat, round(start * fps), round(left * fps), "orbit")
        return []

    def _stop(self) -> None:
        update = getattr(self, "_update", None)
        if update is not None:
            self._clock_mob.remove_updater(update)

    def _frame_point(self, metres: np.ndarray) -> np.ndarray:
        lay, u = self._lay, self._unit_m
        return np.array([lay.frame_x(float(metres[0]) / u), lay.frame_y(float(metres[1]) / u), 0.0])

    def _frame_points(self, metres: np.ndarray) -> np.ndarray:
        lay, u = self._lay, self._unit_m
        x = lay.plot.x0 + (metres[:, 0] / u - lay.x.lo) / (lay.x.hi - lay.x.lo) * lay.plot.width
        y = lay.plot.y0 + (metres[:, 1] / u - lay.y.lo) / (lay.y.hi - lay.y.lo) * lay.plot.height
        return np.column_stack([x, y, np.zeros(len(x))])

    def _draw(self, t: float) -> None:
        """Put everything where it is at simulated time ``t`` (s)."""
        self._t = t
        model = self._model
        plot = self._lay.plot
        centre = model.system.central.name
        anchors = {centre: model.view(centre, t)}
        items = [(centre, *self._central)]
        self._show(*self._central, self._frame_point(anchors[centre]), plot)
        for o in model.system.orbiters:
            anchors[o.name] = model.view(o.name, t)
            dot, label = self._bodies[o.name]
            self._show(dot, label, self._frame_point(anchors[o.name]), plot)
            items.append((o.name, dot, label))
        self._place_labels(items, plot)
        for name, (container, rel, moves) in self._conics.items():
            if not moves and len(container):
                continue
            o = model.system.orbiter(name)
            parent = anchors[o.parent if o.parent is not None else centre]
            pts = self._frame_points(rel + parent)
            line = plot_draw.series_line(pts, plot, self._colors[name], width=2.5, dashed=not o.elements.closed)
            line.set_stroke(opacity=0.55).set_z_index(1)
            plot_draw.morph_into(container, line)
        for name, group in self._trails.items():
            length = model.trails[name]
            ts = np.linspace(max(0.0, t - length), t, TRAIL_SAMPLES + 1)
            if ts[-1] - ts[0] <= 0:
                for piece in group:
                    piece.clear_points()
                continue
            pts = self._frame_points(model.view(name, ts))
            # a trail starts where the motion started: its pieces cover the length it has
            share = (ts[-1] - ts[0]) / length
            first = TRAIL_PIECES - max(1, math.ceil(share * TRAIL_PIECES - 1e-9))
            bounds = np.linspace(0, TRAIL_SAMPLES, TRAIL_PIECES - first + 1).round().astype(int)
            for k, piece in enumerate(group):
                piece.clear_points()
                if k < first:
                    continue
                a, b = bounds[k - first], bounds[k - first + 1]
                for run in plotcore.clip_polyline(pts[a:b + 1], plot):
                    if len(run) >= 2:
                        piece.start_new_path(run[0])
                        piece.add_points_as_corners(run[1:])
        self._draw_readout(t)

    def _show(self, dot: Mobject, label: Mobject, at: np.ndarray, plot: Any) -> None:
        """Move a body to ``at``; hide it and its label while it is outside the plot."""
        inside = plot.contains(float(at[0]), float(at[1]), 1e-6)
        dot.move_to(at)
        if inside != getattr(dot, "_orbit_shown", True):
            for m in (dot, label):
                m.set_opacity(1.0 if inside else 0.0)
            dot._orbit_shown = inside

    def _place_labels(self, items: list[tuple[str, Mobject, Mobject]], plot: Any) -> None:
        """Put each label beside its body on the first of eight sides (the side it had last,
        then up-right, up-left…) where it covers no other body, label or the readout and stays
        in the plot; else on the side covering least (it keeps its side while that is free, so
        labels do not jump about)."""
        dots = [(name, dot, _rect(dot, 0.03)) for name, dot, _ in items if getattr(dot, "_orbit_shown", True)]
        taken = [self._readout_box] if self._readout_box is not None else []
        for name, dot, label in items:
            if not label.has_points() and not len(label):
                continue
            w, h = label.width, label.height
            c = dot.get_center()
            r = dot.width / 2
            best, best_cost = None, math.inf
            prev = self._label_sides.get(name, 0)
            for k in [prev] + [k for k in range(len(LABEL_SIDES)) if k != prev]:
                sx, sy = LABEL_SIDES[k]
                diag = 0.75 if sx and sy else 1.0
                cx = c[0] + sx * (r * diag + LABEL_GAP + w / 2)
                cy = c[1] + sy * (r * diag + LABEL_GAP + h / 2)
                box = plotcore.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                cost = sum(_overlap(box, other) for other in taken) + sum(_overlap(box, d) for n, _, d in dots if n != name)
                cost += 2 * (w * h - _overlap(box, plot))   # outside the plot
                if cost < best_cost - 1e-9:
                    best, best_cost = (k, box), cost
                if cost <= 1e-9:
                    break
            k, box = best
            self._label_sides[name] = k
            label.move_to([box.center[0], box.center[1], 0])
            taken.append(box)

    def _time_line(self, t: float) -> str:
        unit, scale = self._t_unit
        return plotcore.readout_text("t", t / scale, unit)

    @staticmethod
    def _energy_line(error: float) -> str:
        return "ΔE/E = " + plotcore.readout_number(error, 2)

    def _draw_readout(self, t: float) -> None:
        box = self._readout_box
        if box is None:
            return
        lines = ([self._time_line(t)] + self._lines_static) if self.params.readout else []
        if self.params.shows_energy():
            lines.append(self._energy_line(self._model.energy_error(t)))
        key = tuple(lines)
        if key == self._last_lines:
            return
        self._last_lines = key
        texts = [self._cached(text, self._size, "text") for text in lines]
        if self._note:
            texts.append(self._cached(self._note, self._size * 0.85, "dim"))
        group = VGroup(*texts).arrange(DOWN, buff=0.12 * self._size / 24, aligned_edge=LEFT)
        pad = plot_draw.PLATE_PAD
        if group.width > box.width - 2 * pad:
            group.scale((box.width - 2 * pad) / group.width)
        group.move_to([box.x0 + pad + group.width / 2, box.y1 - pad - group.height / 2, 0])
        plate = RoundedRectangle(width=box.width, height=box.height, corner_radius=0.08)
        plate.set_fill(self.theme.background, opacity=0.88).set_stroke(self.theme.color("dim"), width=1, opacity=0.5)
        plate.move_to([box.center[0], box.center[1], 0])
        plot_draw.morph_into(self._readout, VGroup(plate.set_z_index(6), group.set_z_index(6.5)))

    def _cached(self, text: str, size: float, color: str) -> Mobject:
        key = f"{color}|{size}|{text}"
        if key not in self._label_cache:
            self._label_cache[key] = plot_draw.label_text(text, size=size, color=color, theme=self.theme)
        return self._label_cache[key].copy()


def _rect(m: Mobject, pad: float = 0.0) -> Any:
    return plotcore.Rect(m.get_left()[0] - pad, m.get_bottom()[1] - pad, m.get_right()[0] + pad, m.get_top()[1] + pad)


def _overlap(a: Any, b: Any) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def _bounds(lay: Any, box: Any) -> tuple[float, float, float, float]:
    """The box around a laid-out panel (plot, tick labels, titles) and the readout ``box``."""
    xs, ys = [lay.plot.x0, lay.plot.x1], [lay.plot.y0, lay.plot.y1]
    labels = [*lay.x_labels, *lay.y_labels, *[t for t in (lay.x_title, lay.y_title) if t is not None]]
    for lab in labels:
        xs += [lab.x - lab.width / 2, lab.x + lab.width / 2]
        ys += [lab.y - lab.height / 2, lab.y + lab.height / 2]
    if box is not None:
        xs += [box.x0, box.x1]
        ys += [box.y0, box.y1]
    return min(xs), min(ys), max(xs), max(ys)


def _shifted(lay: Any, dx: float, dy: float) -> Any:
    """A laid-out panel moved by ``(dx, dy)``."""
    def label(lab: Any) -> Any:
        return None if lab is None else replace(lab, x=lab.x + dx, y=lab.y + dy)

    plot = plotcore.Rect(lay.plot.x0 + dx, lay.plot.y0 + dy, lay.plot.x1 + dx, lay.plot.y1 + dy)
    return replace(lay, plot=plot, x_labels=tuple(label(lab) for lab in lay.x_labels), y_labels=tuple(label(lab) for lab in lay.y_labels),
                   x_title=label(lay.x_title), y_title=label(lay.y_title))


__all__ = ["BOX_GAP", "CONIC_SAMPLES", "MIN_BODY_RADIUS", "MIN_CENTRAL_RADIUS", "Orbit", "TRAIL_PIECES"]
