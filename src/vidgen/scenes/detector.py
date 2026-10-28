"""``detector``: event displays in a schematic cylindrical detector (Phase Y, Step 240; DESIGN
§99.10). The transverse (x–y) or longitudinal (r–z) view of a generic general-purpose detector —
tracker, solenoid, ECAL, HCAL, iron yoke, muon chambers; labelled schematic — with a simulated
event: tracks bending in the field with the right sign and radius (p_T = 0.3 B R), calorimeter
towers proportional to the energy, muon-chamber hits, jets as cones, the missing transverse
momentum, a readout of the objects (p_T, η) and a signature legend. Built layer by layer over the
beats: the detector, the tracks growing out of the collision point, the calorimeter deposits, the
muons, the missing p_T. The physics is ``particle_physics.detector`` (no manim); the action
``switch_view`` (``detector_actions.py``) turns x–y into r–z and back."""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from . import feynman_draw as fd

pp = particle_physics
dt = particle_physics.detector

#: Readout and legend text, object labels, the label line — relative to the readable size.
READOUT_SCALE = 1.1
LEGEND_SCALE = 1.05
LABEL_SCALE = 1.2
NOTE_SCALE = 1.0
#: Strokes (pixels at 1080p-ish): tracks, tracker layers, layer outlines.
TRACK_STROKE = 3.2
LAYER_STROKE = 1.2
#: Gap between the drawing and the columns / label ring (scene units).
GAP = 0.35
#: Points per drawn track at most.
TRACK_POINTS = 160
#: Missing p_T arrow: at most this share of the HCAL's outer radius.
MET_REACH = 0.95
#: Object labels sit this share of the way to the detector's edge (in the muon system).
LABEL_REACH = 0.8

#: Colour of each kind of particle (its track, label and readout row) and of the parts.
KIND_COLORS = {"electron": "primary", "muon": "accent", "charged_hadron": "text", "photon": "tertiary", "neutral_hadron": "secondary"}
LAYER_COLORS = {"tracker": "dim", "solenoid": "dim", "ecal": "tertiary", "hcal": "secondary", "iron": "dim", "muon": "accent"}
LAYER_NAMES = {"tracker": "tracker", "solenoid": "solenoid", "ecal": "ECAL", "hcal": "HCAL", "iron": "iron yoke", "muon": "muon chambers"}
LEGEND = (("e", "electron", "track + ECAL"), ("γ", "photon", "ECAL, no track"), ("μ", "muon", "track + muon hits"),
          ("h±", "charged_hadron", "track + HCAL"), ("h⁰", "neutral_hadron", "HCAL, no track"), ("ν", "neutrino", "missing pT"))


class DetParticle(SceneParams):
    """A particle of a listed event: ``{particle, pt, eta, phi}``."""

    particle: str
    """The particle (e-, mu+, gamma, pi+, K0_L, n, nu_e…) or jet (a cone of hadrons and photons)."""
    pt: float
    """Transverse momentum in GeV/c."""
    eta: float = 0.0
    """Pseudorapidity η (0: perpendicular to the beam; |η| ≤ 3)."""
    phi: float = 0.0
    """Azimuth in degrees, counter-clockwise from +x (the x–y view's right)."""
    leaves: list[str] | None = None
    """What you say it leaves (track, ecal, hcal, muon, missing): checked against the particle (a photon leaves no track)."""


class DetEvent(SceneParams):
    """``event:`` a preset with a seed, or listed particles."""

    preset: str | None = None
    """z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu or dijet."""
    seed: int = 1
    """The simulation's seed: the same seed, the same event."""
    particles: list[DetParticle] = Field(default_factory=list)
    """Listed particles instead of a preset."""
    soft: int | None = None
    """Soft charged pions in back-to-back pairs (low p_T: they curl up in the tracker); default 4 with a preset, 0 with listed particles."""
    products: list[int] = Field(default_factory=list)
    """Listed particles (1, 2… in order) whose invariant mass the readout states."""


def event_of(params: Any) -> Any:
    """The ``particle_physics.detector.Event`` of the params (deterministic)."""
    e = params.event
    if isinstance(e, str):
        return dt.generate(e, 1)
    if e.preset:
        return dt.generate(e.preset, e.seed, e.soft)
    return dt.custom_event([x.model_dump() for x in e.particles], e.seed, e.soft or 0, e.products)


def object_names(ev: Any) -> list[tuple[str, str, Any]]:
    """The readout's objects in order: (target suffix ``1``…, kind ``particle`` / ``jet``, item)."""
    return [(str(k), kind, item) for k, (kind, item) in enumerate(ev.objects(), start=1)]


def owner_of(ev: Any, i: int) -> str:
    """Which object a particle's towers belong to: ``p<i>``, a jet's name, or ``soft``."""
    group = ev.particles[i].group
    if group.startswith("jet"):
        return group
    return "soft" if group in ("soft", "recoil") else f"p{i}"


@dataclass
class _View:
    """Everything drawn in one view (fresh for each switch): parts by container name."""

    parts: dict[str, Mobject] = field(default_factory=dict)
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    scale: float = 1.0
    inner: dict[str, np.ndarray] = field(default_factory=dict)   # where a tower grows from


@scene("detector")
class Detector(NarratedScene):
    """An event display in a schematic cylindrical detector: ``event: z_to_mumu`` (presets
    z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu, dijet; ``{preset, seed}`` for another
    event) or listed particles (``{particles: [{particle: mu+, pt: 40, eta: 0.5, phi: 30}]}``)
    seen in the transverse (``view: xy``) or longitudinal (``rz``) view. Tracks bend in the
    solenoid field (``field``, tesla) with the radius p_T = 0.3 B R and the sign of their charge;
    electrons and photons shower in the ECAL, hadrons in the HCAL, muons cross everything and
    hit the muon chambers; neutrinos show as missing p_T. Built layer by layer over the beats.

    Action targets: ``title``, ``caption``, ``detector``, ``layer:<tracker|solenoid|ecal|hcal|iron|muon>``,
    ``layers`` (the layer key), ``tracks``, ``ecal``, ``hcal``, ``muon_hits``, ``missing_pt``,
    ``readout``, ``legend``, ``label``, ``particle:<n>`` / ``particle:<particle>`` (the readout's
    objects), ``jet:<n>``, ``soft``.
    """

    outro = 0.5
    detector_actions = True
    target_patterns = ("title", "caption", "detector", "layer:<name>", "layers", "tracks", "ecal", "hcal", "muon_hits", "missing_pt",
                       "readout", "legend", "label", "particle:<n>", "particle:<particle>", "jet:<n>", "soft")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title above the display."""
        caption: TranslatableStr = ""
        """Note under the display."""
        event: str | DetEvent = "z_to_mumu"
        """A preset (z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu, dijet), {preset, seed, soft} or {particles: [...], seed, products}."""
        view: Literal["xy", "rz"] = "xy"
        """xy: across the beam (transverse; B out of the screen); rz: along it (longitudinal). switch_view changes it."""
        field: float = 2.0
        """The solenoid's field in tesla (> 0): R [m] = p_T [GeV/c] / (0.3 B)."""
        return_field: float | None = None
        """The return field in the barrel iron (T, opposite; schematic): default half the solenoid's."""
        energy_scale: Literal["linear", "log"] = "log"
        """Tower length: linear (E / tower_max) or log (log(1 + E/GeV) / log(1 + tower_max/GeV)); stated under the legend."""
        tower_max: float = Field(default=100.0, gt=0)
        """The energy (GeV) that fills a calorimeter's whole depth (larger deposits are cut at it)."""
        readout: bool = True
        """List the objects (p_T, η), the missing p_T and the decay products' invariant mass."""
        legend: bool = True
        """The signature legend (what each kind of particle leaves)."""
        layers: bool = True
        """The layer key (tracker, solenoid, ECAL, HCAL, iron yoke, muon chambers)."""
        labels: bool = True
        """Name the objects (μ⁺, γ, jet 1) beside the detector."""
        reveal: Literal["layers", "all"] = "layers"
        """layers: the detector, then the tracks, the calorimeters, the muons, the missing p_T over the beats; all: everything in beat 1."""
        label: TranslatableStr = "schematic detector · simulated event"
        """The line under the display (say what is schematic and what is simulated)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""

        @model_validator(mode="after")
        def _check(self) -> "Detector.Params":
            e = self.event
            if isinstance(e, DetEvent):
                if bool(e.preset) == bool(e.particles):
                    raise ValueError("event: give a preset ({preset: z_to_mumu, seed: 3}) or particles ({particles: [{particle: mu+, pt: 40}]}), one of the two")
                if e.products and e.preset:
                    raise ValueError("event.products: for listed particles (a preset knows its decay products)")
                if e.products and any(not 1 <= k <= len(e.particles) for k in e.products):
                    raise ValueError(f"event.products: particles are numbered 1–{len(e.particles)}")
                if e.soft is not None and not 0 <= e.soft <= 40:
                    raise ValueError(f"event.soft: {e.soft} — give 0 to 40 soft pions")
                for k, x in enumerate(e.particles, start=1):
                    if x.leaves is not None and x.particle.strip().lower() != "jet":
                        try:
                            problem = dt.signature_problem(x.particle, x.leaves)
                        except VidgenError as exc:
                            raise ValueError(f"event.particles[{k}]: {exc}") from None
                        if problem:
                            raise ValueError(f"event.particles[{k}]: {problem}")
            try:
                dt.Detector(self.field, self.return_field)
                event_of(self)
            except VidgenError as exc:
                raise ValueError(str(exc)) from None
            return self

    # ----- names -------------------------------------------------------------------------------

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        ev = event_of(params)
        names = (["title"] if params.title else []) + (["caption"] if params.caption else [])
        names += ["detector"] + [f"layer:{k}" for k in LAYER_NAMES] + (["layers"] if params.layers else [])
        names += ["tracks", "ecal", "hcal", "muon_hits", "missing_pt"] + (["readout"] if params.readout else []) + (["legend"] if params.legend else [])
        names += ["label"] if params.label else []
        objs = object_names(ev)
        names += [f"particle:{n}" for n, _, _ in objs]
        keys = [ev.particles[item].particle.key for _, kind, item in objs if kind == "particle"]
        names += [f"particle:{k}" for k in dict.fromkeys(keys) if keys.count(k) == 1]
        names += [f"jet:{j.name[3:]}" for j in ev.jets]
        names += ["soft"] if any(q.group in ("soft", "recoil") for q in ev.particles) else []
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """An object's particle name (for the narration lint), the title."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        if kind == "particle":
            ev = event_of(params)
            for n, k, item in object_names(ev):
                if k == "particle" and key in (n, ev.particles[item].particle.key):
                    return ev.particles[item].particle.name
        return None

    # ----- building ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._event = event_of(p)
        self._det = dt.Detector(p.field, p.return_field)
        self._paths = [dt.trajectory(q, self._det) for q in self._event.particles]
        self._deposits = dt.deposits(self._event, self._paths)
        self._small = readable_size(margin=1.08)
        self._view = p.view
        area = self.safe_area
        self._title = None
        if p.title:
            self._title = chart_title(p.title, size=p.title_size, color=p.title_color, area=area)
            area = area.below(self._title, gap=0.2)
        self._caption = None
        if p.caption:
            self._caption = chart_caption(p.caption, area, color=p.caption_color)
            area = area.above(self._caption, gap=0.15)
        self._label = None
        if p.label and self.is_portrait:   # a line at the bottom (in 16:9 under the layer key)
            self._label = self._label_block(area.width)
            self._label.move_to(np.array([area.center[0], area.y0 + self._label.height / 2, 0]))
            area = area.above(self._label, gap=0.15)
        elif p.label:
            self._label = self._label_block(None)
        self._layout(area)
        self._containers: dict[str, VGroup] = {}
        self._drawn = self._build_view(self._view)
        for name, m in self._drawn.parts.items():
            self._containers[name] = VGroup(m)
        self._register()
        self.reveal(self._steps(), fraction=0.7, cap=1.0)
        self.finish()

    def _label_block(self, width: float | None) -> VGroup:
        """``schematic detector · simulated event · B = 2 T out of the screen``: one line under
        the display (``width``), or one part per line in the 16:9 side column (``None``)."""
        b = f"B = {self._det.field:g} T " + ("out of the screen" if self._view == "xy" else "along the beam (z)")
        size = self._small * NOTE_SCALE
        if width is not None:
            lines = [self.text(s, size=size, color="dim") for s in (str(self.params.label), b)]
            return VGroup(*[m.scale_to_fit_width(width) if m.width > width else m for m in lines]).arrange(DOWN, buff=0.1)
        # the field on two lines so the column stays as narrow as the layer key (a larger drawing)
        parts = [s.strip() for s in str(self.params.label).split("·") if s.strip()] + [f"B = {self._det.field:g} T", b.split(" T ", 1)[1]]
        return VGroup(*[self.text(s, size=size, color="dim") for s in parts]).arrange(DOWN, buff=0.1, aligned_edge=LEFT)

    # ----- layout ------------------------------------------------------------------------------

    def _layout(self, area: Any) -> None:
        """The drawing's box (with room for the object labels around it) and the columns: left
        the layer key, right the readout and the legend (16:9); under the drawing in 9:16."""
        p = self.params
        self._key = self._layer_key() if p.layers else None
        self._readout = self._readout_table() if p.readout else None
        self._legend = self._legend_block() if p.legend else None
        self._label_sizes = {n: (m.width, m.height) for n, kind, item in object_names(self._event)
                             for m in [self._symbol(kind, item, self._small * LABEL_SCALE)]} if p.labels else {}
        if self.is_portrait:   # under the drawing: the readout beside the layer key, then the legend
            cols = [m for m in (self._readout, self._key) if m is not None]
            if cols:
                total = sum(m.width for m in cols) + GAP * (len(cols) - 1)
                if total > area.width:
                    for m in cols:
                        m.scale(area.width / total)
            if self._legend is not None and self._legend.width > area.width:
                self._legend.scale_to_fit_width(area.width)
            row_h = max((m.height for m in cols), default=0.0)
            legend_h = self._legend.height + GAP if self._legend is not None else 0.0
            room = min(area.width, area.height - row_h - legend_h - GAP)
            top = area.y1 - max(0.0, area.height - room - GAP - row_h - legend_h) / 2   # the whole stack centred
            self._room = Region(area.x0, top - room, area.x1, top)
            y = self._room.y0 - GAP
            if cols:
                total = sum(m.width for m in cols) + GAP * (len(cols) - 1)
                x = area.center[0] - total / 2
                for m in cols:
                    m.move_to(np.array([x + m.width / 2, y - m.height / 2, 0]))
                    x += m.width + GAP
                y -= row_h + GAP
            if self._legend is not None:
                self._legend.move_to(np.array([area.center[0], y - self._legend.height / 2, 0]))
        else:
            column = [m for m in (self._key, self._label) if m is not None]
            left = max((m.width for m in column), default=0.0)
            right = max((m.width for m in (self._readout, self._legend) if m is not None), default=0.0)
            side_gap = GAP * 0.6   # the drawing's labels sit inside it, so the columns may come closer
            self._room = Region(area.x0 + left + side_gap * (left > 0), area.y0, area.x1 - right - side_gap * (right > 0), area.y1)
            if column:
                y = area.center[1] + (sum(m.height for m in column) + 2 * GAP * (len(column) - 1)) / 2
                for m in column:
                    m.move_to(np.array([area.x0 + m.width / 2, y - m.height / 2, 0]))
                    y -= m.height + 2 * GAP
            stack = [m for m in (self._readout, self._legend) if m is not None]
            if stack:
                heights = sum(m.height for m in stack) + GAP * (len(stack) - 1)
                if heights > area.height:
                    for m in stack:
                        m.scale(area.height / heights)
                    heights = area.height
                y = area.center[1] + heights / 2
                for m in stack:
                    m.move_to(np.array([area.x1 - right / 2, y - m.height / 2, 0]))
                    m.align_to(np.array([area.x1 - right, 0, 0]), LEFT)
                    y -= m.height + GAP
        self._frames: dict[str, tuple[np.ndarray, float]] = {}

    # ----- the side blocks ---------------------------------------------------------------------

    def _swatch(self, key: str) -> Mobject:
        color = self.theme.color(LAYER_COLORS[key])
        if key == "tracker":
            return VGroup(*[Line(LEFT * 0.17, RIGHT * 0.17, stroke_width=2, color=color).shift(UP * dy) for dy in (-0.08, 0, 0.08)])
        return Rectangle(width=0.34, height=0.22, stroke_width=1.5, stroke_color=color, fill_color=color, fill_opacity=self._fill(key) * 2.2)

    @staticmethod
    def _fill(key: str) -> float:
        return {"tracker": 0.05, "solenoid": 0.35, "ecal": 0.14, "hcal": 0.14, "iron": 0.22, "muon": 0.3}[key]

    def _layer_key(self) -> VGroup:
        size = self._small * READOUT_SCALE
        rows = []
        for key, name in LAYER_NAMES.items():
            word = self.text(name, size=size, color="dim")
            rows.append(VGroup(self._swatch(key), word).arrange(RIGHT, buff=0.18))
        return VGroup(*rows).arrange(DOWN, buff=0.16, aligned_edge=LEFT)

    def _symbol(self, kind: str, item: Any, size: float) -> Mobject:
        if kind == "jet":
            return self.text(f"jet {item.name[3:]}", size=size, color="text")
        q = self._event.particles[item]
        return fd.particle_label(self, q.particle, False, size, self.theme.color(KIND_COLORS[q.kind]))

    def _readout_table(self) -> VGroup:
        """object · p_T (GeV/c) · η, then p_T^miss and the products' mass."""
        ev = self._event
        size = self._small * READOUT_SCALE
        dim = self.theme.color("dim")
        head = [VGroup(), self.markup("p<sub>T</sub> (GeV/c)", size=size, color=dim), self.markup("η", size=size, color=dim)]
        rows = [head]
        self._rows: dict[str, VGroup] = {}
        for n, kind, item in object_names(ev):
            obj = ev.particles[item] if kind == "particle" else item
            cells = [self._symbol(kind, item, size), self.text(f"{obj.pt:.1f}", size=size, color="text"), self.text(f"{obj.eta:+.2f}", size=size, color="text")]
            rows.append(cells)
        met = self.markup("p<sub>T</sub> miss", size=size, color=self.theme.palette_color(2))
        rows.append([met, self.text(f"{ev.met:.1f}", size=size, color="text"), VGroup()])
        lines = _grid(rows, [False, True, True], col_gap=0.3, row_gap=0.14)
        out = VGroup(*lines)
        mass = self._mass_text()
        if mass:
            m = self.text(mass, size=size, color="text")
            m.next_to(out, DOWN, buff=0.22).align_to(out, LEFT)
            out.add(m)
        for (n, _, _), line in zip(object_names(ev), lines[1:]):
            self._rows[n] = line
        self._met_row = lines[-1]
        return out

    def _mass_text(self) -> str:
        ev = self._event
        m = ev.products_mass()
        if m is not None:
            names = [ev.particles[i].particle.symbol for i in ev.products]
            inside = "4ℓ" if len(names) == 4 and all(ev.particles[i].kind in ("electron", "muon") for i in ev.products) else "".join(names)
            if len(inside) > 8:
                inside = "products"
            return f"m({inside}) = {m:.1f} GeV/c²"
        mt = ev.transverse_mass()
        if mt is not None:
            return f"transverse mass {mt:.1f} GeV/c²"
        return ""

    def _legend_block(self) -> VGroup:
        size = self._small * LEGEND_SCALE
        rows = []
        for symbol, kind, text in LEGEND:
            icon = self._legend_icon(kind)
            sym = self.text(symbol, size=size, color=self.theme.color(KIND_COLORS.get(kind, "text")) if kind != "neutrino" else self.theme.palette_color(2))
            words = self.text(text, size=size, color="dim") if kind != "neutrino" else self.markup("missing p<sub>T</sub>", size=size, color=self.theme.color("dim"))
            rows.append([icon, sym, words])
        if self.is_portrait:   # two columns of three under the drawing
            halves = [VGroup(*_grid(rows[:3], [False] * 3, col_gap=0.2, row_gap=0.14)), VGroup(*_grid(rows[3:], [False] * 3, col_gap=0.2, row_gap=0.14))]
            halves[1].next_to(halves[0], RIGHT, buff=0.35).align_to(halves[0], UP)
            block = VGroup(*halves)
        else:
            block = VGroup(*_grid(rows, [False, False, False], col_gap=0.2, row_gap=0.14))
        how = "towers ∝ E" if self.params.energy_scale == "linear" else "towers ∝ log(1 + E)"
        note = VGroup(*[self.text(s, size=self._small, color="dim") for s in (how, f"full depth = {self.params.tower_max:g} GeV")])
        if self.is_portrait:
            note.arrange(RIGHT, buff=0.3)
        else:
            note.arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        note.next_to(block, DOWN, buff=0.2).align_to(block, LEFT)
        return VGroup(*block, note)

    def _legend_icon(self, kind: str) -> VGroup:
        """A small sketch of the signature: a track, an ECAL / HCAL block, a muon hit, a dashed arrow."""
        parts = VGroup()
        x = 0.0
        if kind in ("electron", "muon", "charged_hadron"):
            parts.add(Line(np.array([x, 0, 0]), np.array([x + 0.32, 0, 0]), stroke_width=TRACK_STROKE, color=self.theme.color(KIND_COLORS[kind])))
            x += 0.38
        for layer in [s for s in ("ecal", "hcal") if s in dt.SIGNATURES[kind][0] | dt.SIGNATURES[kind][1]]:
            c = self.theme.color(LAYER_COLORS[layer])
            parts.add(Rectangle(width=0.16, height=0.22, stroke_width=0, fill_color=c, fill_opacity=0.9).move_to(np.array([x + 0.08, 0, 0])))
            x += 0.22
        if kind == "muon":
            parts.add(Rectangle(width=0.08, height=0.22, stroke_width=0, fill_color=self.theme.color("accent"), fill_opacity=1).move_to(np.array([x + 0.04, 0, 0])))
        if kind == "neutrino":
            c = self.theme.palette_color(2)
            parts.add(DashedLine(np.array([0, 0, 0]), np.array([0.34, 0, 0]), dash_length=0.06, stroke_width=TRACK_STROKE, color=c))
            parts.add(Triangle(color=c, fill_opacity=1, stroke_width=0).scale(0.06).rotate(-PI / 2).move_to(np.array([0.38, 0, 0])))
        return parts

    # ----- the drawing -------------------------------------------------------------------------

    def _frame(self, view: str) -> tuple[np.ndarray, float]:
        """The origin and scale (units per metre) of a view: as large as the room allows with
        the object labels around the drawing."""
        if view in self._frames:
            return self._frames[view]
        box = self._room
        half_w, half_h = (dt.OUTER_R, dt.OUTER_R) if view == "xy" else (dt.OUTER_Z, dt.OUTER_R)
        origin = np.array([box.center[0], box.center[1], 0.0])
        s = min(box.width / (2 * half_w), box.height / (2 * half_h))
        for _ in range(12):
            x0, x1, y0, y1 = origin[0] - half_w * s, origin[0] + half_w * s, origin[1] - half_h * s, origin[1] + half_h * s
            for _n, c, w, h in self._label_spots(view, origin, s):
                x0, x1 = min(x0, c[0] - w / 2), max(x1, c[0] + w / 2)
                y0, y1 = min(y0, c[1] - h / 2), max(y1, c[1] + h / 2)
            f = min(box.width / (x1 - x0), box.height / (y1 - y0))
            # centre what is drawn (labels may stick out on one side only)
            origin = origin + np.array([box.center[0] - (x0 + x1) / 2, box.center[1] - (y0 + y1) / 2, 0.0])
            if f >= 1 - 1e-3:
                break
            s *= f * 0.995
        self._frames[view] = (origin, s)
        return origin, s

    def _label_spots(self, view: str, origin: np.ndarray, s: float) -> list[tuple[str, np.ndarray, float, float]]:
        """Each object label's centre and size: in the muon system along the object's direction
        (:data:`LABEL_REACH` of the way out), beside its line (counter-clockwise of it)."""
        ev = self._event
        out = []
        for n, kind, item in object_names(ev):
            if n not in self._label_sizes:
                continue
            w, h = self._label_sizes[n]
            obj = ev.particles[item] if kind == "particle" else item
            if view == "xy":
                u = np.array([math.cos(obj.phi), math.sin(obj.phi), 0.0])
                k = dt.OUTER_R
            else:
                side = 1 if math.sin(obj.phi) >= 0 else -1
                th = 2 * math.atan(math.exp(-obj.eta))
                u = np.array([math.cos(th), side * math.sin(th), 0.0])
                k = min(dt.OUTER_Z / max(abs(u[0]), 1e-9), dt.OUTER_R / max(abs(u[1]), 1e-9))
            spot = origin + u * k * LABEL_REACH * s
            normal = np.array([-u[1], u[0], 0.0])
            across = abs(normal[0]) * w / 2 + abs(normal[1]) * h / 2
            out.append((n, spot + normal * (across + 0.1), w, h))
        return out

    def _to(self, v: _View, a: float, b: float) -> np.ndarray:
        return v.origin + np.array([a, b, 0.0]) * v.scale

    def _rz(self, x: float, y: float, z: float, side: int) -> tuple[float, float]:
        return z, side * math.hypot(x, y)

    def _build_view(self, view: str) -> _View:
        v = _View()
        v.origin, v.scale = self._frame(view)
        self._layers_of(v, view)
        self._tracks_of(v, view)
        self._towers_of(v, view)
        self._cones_of(v, view)
        self._met_of(v, view)
        self._labels_of(v, view)
        return v

    def _layers_of(self, v: _View, view: str) -> None:
        theme = self.theme
        groups: dict[str, VGroup] = {k: VGroup() for k in LAYER_NAMES}
        for layer in self._det.layers:
            key = layer.key
            color = theme.color(LAYER_COLORS[key])
            fill = self._fill(key)
            if view == "xy":
                if key == "tracker":
                    groups[key].add(Circle(radius=layer.r1 * v.scale, stroke_width=LAYER_STROKE, color=color, fill_color=color, fill_opacity=fill)
                                    .set_stroke(opacity=0.5).move_to(v.origin))
                    for r, _ in dt.TRACKER_LAYERS:
                        groups[key].add(Circle(radius=r * v.scale, stroke_width=LAYER_STROKE, color=color).set_stroke(opacity=0.7).move_to(v.origin))
                    continue
                ring = Annulus(inner_radius=layer.r0 * v.scale, outer_radius=layer.r1 * v.scale, fill_color=color, fill_opacity=fill,
                               stroke_width=LAYER_STROKE, stroke_color=color).set_stroke(opacity=0.55).move_to(v.origin)
                groups[key].add(ring)
                continue
            boxes = []
            if key == "tracker":
                boxes.append((-layer.z_half, layer.z_half, -layer.r1, layer.r1))
            else:
                boxes += [(-layer.z_half, layer.z_half, layer.r0, layer.r1), (-layer.z_half, layer.z_half, -layer.r1, -layer.r0)]
                if layer.endcap is not None:
                    z0, z1, rmin = layer.endcap
                    for sz in (1, -1):
                        for sr in (1, -1):
                            a, b = sorted((sz * z0, sz * z1))
                            c, d = sorted((sr * rmin, sr * layer.r1))
                            boxes.append((a, b, c, d))
            for z0, z1, r0, r1 in boxes:
                rect = Polygon(self._to(v, z0, r0), self._to(v, z1, r0), self._to(v, z1, r1), self._to(v, z0, r1),
                               stroke_width=LAYER_STROKE, color=color, fill_color=color, fill_opacity=fill).set_stroke(opacity=0.55)
                groups[key].add(rect)
            if key == "tracker":
                for r, zh in dt.TRACKER_LAYERS:
                    for sr in (1, -1):
                        groups[key].add(Line(self._to(v, -zh, sr * r), self._to(v, zh, sr * r), stroke_width=LAYER_STROKE, color=color).set_stroke(opacity=0.7))
        if view == "rz":   # the beam line
            groups["tracker"].add(DashedLine(self._to(v, -dt.OUTER_Z, 0), self._to(v, dt.OUTER_Z, 0), dash_length=0.08, stroke_width=1.2,
                                             color=theme.color("dim")).set_stroke(opacity=0.6))
        for key, g in groups.items():
            v.parts[f"layer:{key}"] = g

    def _side(self, q: Any) -> int:
        return 1 if math.sin(q.phi) >= 0 else -1

    def _point(self, v: _View, view: str, pt: Any, side: int) -> np.ndarray:
        x, y, z = pt
        if view == "xy":
            return self._to(v, x, y)
        return self._to(v, *self._rz(x, y, z, side))

    def _polyline(self, v: _View, view: str, pts: np.ndarray, side: int, color: Any) -> VMobject:
        if len(pts) < 2:
            return VMobject()
        step = max(1, len(pts) // TRACK_POINTS)
        idx = list(range(0, len(pts), step))
        if idx[-1] != len(pts) - 1:
            idx.append(len(pts) - 1)
        screen = [self._point(v, view, pts[i], side) for i in idx]
        line = VMobject(stroke_width=TRACK_STROKE, stroke_color=color)
        line.set_points_as_corners(screen)
        return line

    def _tracks_of(self, v: _View, view: str) -> None:
        for i, (q, path) in enumerate(zip(self._event.particles, self._paths)):
            if q.kind not in ("electron", "muon", "charged_hadron"):
                continue
            color = self.theme.color(KIND_COLORS[q.kind])
            side = self._side(q)
            end = path.tracker_end + 1
            inner = self._polyline(v, view, path.points[:end], side, color)
            if q.group in ("soft", "recoil"):
                inner.set_stroke(opacity=0.6, width=TRACK_STROKE * 0.75)
            v.parts[f"track:{i}"] = inner
            hits = VGroup(*[Dot(self._point(v, view, h, side), radius=0.028, color=color) for h in path.tracker_hits])
            v.parts[f"hits:{i}"] = hits
            if q.kind == "muon":
                v.parts[f"outer:{i}"] = self._polyline(v, view, path.points[end - 1:], side, color)
                marks = VGroup()
                for h in path.muon_hits:
                    c = self._point(v, view, h, side)
                    mark = Rectangle(width=0.22, height=0.09, stroke_width=0, fill_color=color, fill_opacity=1).move_to(c)
                    if view == "xy":
                        mark.rotate(math.atan2(h[1], h[0]) + PI / 2)
                    else:
                        x, y, z = h
                        r = math.hypot(x, y)
                        in_endcap = any(st.in_endcap(r, z) and not st.in_barrel(r, z) for st in dt.MUON)
                        if in_endcap:
                            mark.rotate(PI / 2)
                    marks.add(mark)
                v.parts[f"muhits:{i}"] = marks

    def _towers_of(self, v: _View, view: str) -> None:
        ev = self._event
        full = self.params.tower_max
        owners: dict[str, list[Any]] = {}
        for d in self._deposits:
            owners.setdefault(owner_of(ev, d.index), []).append(d)
        for owner, deps in owners.items():
            for layer in ("ecal", "hcal"):
                group = VGroup()
                for t in dt.towers(ev, [d for d in deps if d.layer == layer], view):
                    f = dt.tower_fraction(t.energy, full, self.params.energy_scale)
                    group.add(self._tower(v, view, t, f))
                v.parts[f"towers:{owner}:{layer}"] = group

    def _tower(self, v: _View, view: str, t: Any, f: float) -> Mobject:
        layer = dt.ECAL if t.layer == "ecal" else dt.HCAL
        color = self.theme.color(LAYER_COLORS[t.layer])
        style = dict(stroke_width=0.8, stroke_color=color, fill_color=color, fill_opacity=0.88)
        a0, a1 = t.angle - t.width / 2 * 0.86, t.angle + t.width / 2 * 0.86
        if view == "xy":
            r0, r1 = layer.r0, layer.r0 + f * (layer.r1 - layer.r0)
            sector = AnnularSector(inner_radius=r0 * v.scale, outer_radius=r1 * v.scale, angle=a1 - a0, start_angle=a0, **style)
            sector.shift(v.origin - np.array([0.0, 0.0, 0.0]))
            return sector
        corners = []   # clipped to the barrel's length or the endcap's radii (a neighbouring cell may point past them)
        if not t.endcap:
            r0, r1 = layer.r0, layer.r0 + f * (layer.r1 - layer.r0)
            for r, (a, b) in ((r0, (a0, a1)), (r1, (a1, a0))):
                for th in (a, b):
                    z = r * math.cos(th) / max(math.sin(th), 1e-9)
                    corners.append(self._to(v, max(-layer.z_half, min(layer.z_half, z)), t.side * r))
        else:
            z0, z1, rmin = layer.endcap
            sz = 1 if math.cos(t.angle) >= 0 else -1
            za, zb = sz * z0, sz * (z0 + f * (z1 - z0))
            for z, (a, b) in ((za, (a0, a1)), (zb, (a1, a0))):
                for th in (a, b):
                    corners.append(self._to(v, z, t.side * max(rmin, min(layer.r1, abs(z * math.tan(th))))))
        return Polygon(*corners, **style)

    def _cones_of(self, v: _View, view: str) -> None:
        ev = self._event
        color = self.theme.color("text")
        for j in ev.jets:
            reach = dt.HCAL.r1
            if view == "xy":
                half = 0.4
                cone = AnnularSector(inner_radius=0.0, outer_radius=reach * v.scale, angle=2 * half, start_angle=j.phi - half,
                                     fill_color=color, fill_opacity=0.07, stroke_width=1.2, stroke_color=color).set_stroke(opacity=0.45)
                cone.shift(v.origin)
            else:
                side = 1 if math.sin(j.phi) >= 0 else -1
                th = 2 * math.atan(math.exp(-j.eta))
                lo, hi = 2 * math.atan(math.exp(-(j.eta + 0.4))), 2 * math.atan(math.exp(-(j.eta - 0.4)))
                pts = [v.origin]
                for a in (lo, th, hi):
                    d = np.array([math.cos(a), side * math.sin(a)])
                    k = min(dt.HCAL.endcap[1] / max(abs(d[0]), 1e-9), reach / max(abs(d[1]), 1e-9))
                    pts.append(self._to(v, d[0] * k, d[1] * k))
                cone = Polygon(*pts, fill_color=color, fill_opacity=0.07, stroke_width=1.2, stroke_color=color).set_stroke(opacity=0.45)
            v.parts[f"cone:{j.name}"] = cone

    def _met_of(self, v: _View, view: str) -> None:
        ev = self._event
        mx, my = ev.missing_pt()
        met = ev.met
        color = self.theme.palette_color(2)
        objs = [ev.particles[i].pt if k == "particle" else i.pt for k, i in ev.objects()]
        ref = max([met] + objs)
        if view != "xy" or met < 1.0:
            v.parts["met"] = VGroup()
            return
        length = MET_REACH * dt.HCAL.r1 * met / ref
        u = np.array([mx / met, my / met, 0.0])
        start, end = v.origin, v.origin + u * length * v.scale
        line = DashedLine(start, end - u * 0.12, dash_length=0.12, stroke_width=TRACK_STROKE + 1, color=color)
        tip = Triangle(color=color, fill_opacity=1, stroke_width=0).scale(0.11).rotate(math.atan2(my, mx) - PI / 2).move_to(end - u * 0.06)
        v.parts["met"] = VGroup(line, tip)

    def _labels_of(self, v: _View, view: str) -> None:
        """Each object's name just outside the detector, along its direction."""
        if not self.params.labels:
            return
        items = {n: (kind, item) for n, kind, item in object_names(self._event)}
        placed: list[Mobject] = []
        for n, centre, _w, _h in self._label_spots(view, v.origin, v.scale):
            label = self._symbol(*items[n], self._small * LABEL_SCALE).move_to(centre)
            # a halo of the background: the name reads over the layers it sits on
            label.set_stroke(self.theme.background, width=7, background=True)
            for other in placed:   # two objects close in direction: move the later one aside
                dx = min(label.get_right()[0], other.get_right()[0]) - max(label.get_left()[0], other.get_left()[0]) + 0.12
                dy = min(label.get_top()[1], other.get_top()[1]) - max(label.get_bottom()[1], other.get_bottom()[1])
                if dx > 0 and dy > 0:
                    label.shift(RIGHT * dx if label.get_x() >= other.get_x() else LEFT * dx)
            placed.append(label)
            v.parts[f"label:{n}"] = label

    # ----- targets and reveal ----------------------------------------------------------------

    def _c(self, *names: str) -> list[VGroup]:
        return [self._containers[n] for n in names if n in self._containers]

    def _matching(self, prefix: str) -> list[VGroup]:
        return [c for n, c in self._containers.items() if n.startswith(prefix)]

    def _register(self) -> None:
        ev = self._event
        for name, m in (("title", self._title), ("caption", self._caption), ("label", self._label)):
            if m is not None:
                self.target(name, m, entrance=lambda m=m: [FadeIn(m)])
        layers = self._matching("layer:")
        self.target("detector", VGroup(*layers), entrance=lambda: [FadeIn(c) for c in self._matching("layer:") if self._new(c)])
        for key in LAYER_NAMES:
            box = self._containers[f"layer:{key}"]
            self.target(f"layer:{key}", box, entrance=lambda box=box: [FadeIn(box)])
        for name, block in (("layers", self._key), ("readout", self._readout), ("legend", self._legend)):
            if block is not None:
                self.target(name, block, entrance=lambda block=block: [FadeIn(block)])
        self.target("tracks", VGroup(*self._matching("track:"), *self._matching("hits:")), entrance=self._tracks_entrance)
        for layer in ("ecal", "hcal"):
            self.target(layer, VGroup(*[c for n, c in self._containers.items() if n.startswith("towers:") and n.endswith(layer)]),
                        entrance=lambda layer=layer: self._towers_entrance([layer]))
        self.target("muon_hits", VGroup(*self._matching("outer:"), *self._matching("muhits:")), entrance=self._muons_entrance)
        self.target("missing_pt", VGroup(*self._c("met"), *([self._met_row] if self._readout is not None else [])), entrance=self._met_entrance)
        objs = object_names(ev)
        keys = [ev.particles[item].particle.key for _, kind, item in objs if kind == "particle"]
        for n, kind, item in objs:
            members = [item] if kind == "particle" else list(item.members)
            owner = owner_of(ev, item) if kind == "particle" else item.name
            parts = [c for i in members for c in self._c(f"track:{i}", f"hits:{i}", f"outer:{i}", f"muhits:{i}")]
            parts += self._matching(f"towers:{owner}:") + self._c(f"label:{n}") + ([self._rows[n]] if self._readout is not None else [])
            if kind == "jet":
                parts += self._c(f"cone:{item.name}")
            names = [f"particle:{n}"]
            if kind == "particle" and keys.count(ev.particles[item].particle.key) == 1:
                names.append(f"particle:{ev.particles[item].particle.key}")
            if kind == "jet":
                names.append(f"jet:{item.name[3:]}")
            self.target(names, VGroup(*parts), entrance=lambda parts=parts: [FadeIn(m) for m in parts if self._new(m)])
        soft = [i for i, q in enumerate(ev.particles) if q.group in ("soft", "recoil")]
        if soft:
            parts = [c for i in soft for c in self._c(f"track:{i}", f"hits:{i}")] + self._matching("towers:soft:")
            self.target("soft", VGroup(*parts), entrance=lambda parts=parts: [FadeIn(m) for m in parts if self._new(m)])

    def _new(self, m: Mobject) -> bool:
        """``m`` has something to draw and is not on screen yet."""
        return bool(m.family_members_with_points()) and id(m) not in {id(x) for x in self.get_mobject_family_members()}

    def _tracks_entrance(self) -> list[Animation]:
        """Tracks grow out of the collision point, their tracker hits appear."""
        anims: list[Animation] = []
        for name, box in self._containers.items():
            if name.startswith("track:") and self._new(box):
                anims.append(Create(box, rate_func=linear))
            elif name.startswith("hits:") and self._new(box):
                anims.append(FadeIn(box, lag_ratio=0.05))
        return anims

    def _towers_entrance(self, layers: list[str]) -> list[Animation]:
        """Towers grow outward from the calorimeter's inner face; jet cones fade in."""
        anims: list[Animation] = []
        for name, box in self._containers.items():
            if name.startswith("towers:") and name.split(":")[-1] in layers and self._new(box):
                anims.append(self._grow(box))
            elif name.startswith("cone:") and self._new(box):
                anims.append(FadeIn(box))
        return anims

    def _grow(self, box: VGroup) -> Animation:
        """Each tower grows outward from its point nearest the collision point (one animation on
        the container, so the container is what the scene holds — a view switch morphs it)."""
        towers = box.submobjects[0].submobjects if box.submobjects else []
        if not towers:
            return FadeIn(box)
        o = self._drawn.origin
        finals = [t.copy() for t in towers]
        roots = [self._inner_point(t, o) for t in towers]

        def update(_m: Mobject, alpha: float) -> None:
            for t, final, root in zip(towers, finals, roots):
                t.become(final.copy().scale(max(alpha, 1e-3), about_point=root))

        return UpdateFromAlphaFunc(box, update)

    @staticmethod
    def _inner_point(t: Mobject, origin: np.ndarray) -> np.ndarray:
        pts = t.get_all_points()
        if not len(pts):
            return t.get_center()
        d = np.linalg.norm(pts - origin, axis=1)
        return pts[int(np.argmin(d))]

    def _muons_entrance(self) -> list[Animation]:
        anims: list[Animation] = []
        for name, box in self._containers.items():
            if name.startswith("outer:") and self._new(box):
                anims.append(Create(box, rate_func=linear))
            elif name.startswith("muhits:") and self._new(box):
                anims.append(FadeIn(box, scale=1.6, lag_ratio=0.3))
        return anims

    def _met_entrance(self) -> list[Animation]:
        anims: list[Animation] = []
        met = self._containers.get("met")
        if met is not None and self._new(met):
            anims.append(Create(met))
        elif met is not None and not met.family_members_with_points():
            self.add(met)   # none in this view: on screen empty, so a switch to x–y draws it
        return anims

    def _steps(self) -> list[Any]:
        """The detector (with the title, the layer key, the legend, the label), the tracks, the
        calorimeters, the muons, then the missing p_T, the names and the readout."""
        def frame() -> list[Animation]:
            anims = [a for n in ("title", "label") if getattr(self, f"_{n}") is not None for a in self.entrance(n)]
            anims += self.entrance("detector") + (self.entrance("layers") if self._key is not None else [])
            return anims + (self.entrance("legend") if self._legend is not None else [])

        def last() -> list[Animation]:
            anims = self._met_entrance() + [FadeIn(c) for n, c in self._containers.items() if n.startswith("label:") and self._new(c)]
            for block in (self._readout, self._legend):
                if block is not None and self._new(block):
                    anims.append(FadeIn(block))
            if self._caption is not None:
                anims += self.entrance("caption")
            return anims

        steps = [frame, self._tracks_entrance, lambda: self._towers_entrance(["ecal", "hcal"]), self._muons_entrance, last]
        if not any(n.startswith("outer:") for n in self._containers):
            steps.remove(self._muons_entrance)
        if self.params.reveal == "all":
            def everything() -> list[Animation]:
                seen: set[int] = set()
                out = []
                for a in (a for s in steps for a in s()):
                    if id(a.mobject) not in seen:   # one entrance per mobject
                        seen.add(id(a.mobject))
                        out.append(a)
                return out

            return [everything]
        return steps

    # ----- the switch_view action ------------------------------------------------------------

    def switch_view(self, to: str | None) -> list[Animation]:
        """Morph into the other view (``to``: xy or rz; default the other one): each part on
        screen turns into its counterpart, those still to come are swapped silently; the
        missing p_T (transverse) shows only in x–y."""
        target = to or ("rz" if self._view == "xy" else "xy")
        if target == self._view:
            return []
        self._view = target
        drawn = self._build_view(target)
        present = {id(m) for m in self.get_mobject_family_members()}
        anims: list[Animation] = []
        for name, box in self._containers.items():
            new = drawn.parts.get(name, VGroup())
            old = box.submobjects[0] if box.submobjects else None
            if old is not None and id(old) in present and old.family_members_with_points():
                if new.family_members_with_points():
                    anims.append(Transform(old, new))
                else:
                    anims.append(FadeOut(old))
                    box.submobjects = [new]
            else:
                box.submobjects = [new]
                if id(box) in present and new.family_members_with_points():
                    anims.append(FadeIn(new))
        self._drawn = drawn
        if self._label is not None:   # the field's direction in words
            old = self._label[-1]
            line = self._label_block(self._room.width if self.is_portrait else None)[-1]
            line.move_to(old)
            if not self.is_portrait:
                line.align_to(old, LEFT)
            anims.append(Transform(old, line))
        return anims

    def current_view(self) -> str:
        return self._view


def _grid(rows: list[list[Mobject]], right: list[bool], col_gap: float, row_gap: float) -> list[VGroup]:
    """Lay ``rows`` of cells out as a table (columns left- or right-aligned, rows centred on
    their line): one VGroup per row, the first row's top at y = 0."""
    widths = [max(r[c].width for r in rows) for c in range(len(right))]
    heights = [max([m.height for m in r if m.family_members_with_points()] or [0.2]) for r in rows]
    out = []
    y = 0.0
    for r, h in zip(rows, heights):
        y -= h / 2
        x = 0.0
        for c, cell in enumerate(r):
            if cell.family_members_with_points():
                cx = x + widths[c] - cell.width / 2 if right[c] else x + cell.width / 2
                cell.move_to(np.array([cx, y, 0]))
            x += widths[c] + col_gap
        out.append(VGroup(*r))
        y -= h / 2 + row_gap
    return out


__all__ = ["DetEvent", "DetParticle", "Detector", "event_of", "object_names"]
