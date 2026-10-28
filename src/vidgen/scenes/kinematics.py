"""``kinematics``: momentum-vector pictures of relativistic kinematics (Phase Y, Step 239; DESIGN
§99.8). A two-body decay (``decay: "pi+ -> mu+ nu_mu"``) in the parent's rest frame — the products
back to back with p* from the Källén function — and in the lab where the parent moves
(``momentum: 10 GeV/c``), side by side (16:9) or stacked (9:16); or particles given in the lab
(``particles:``) with their sum and the system's rest frame. Arrows to scale with their
momenta written at their tips, the sum vector, and the numbers each frame shows: p*, the
energies, β and γ, the opening angle, the invariant mass √((ΣE)² − |Σp|²) — the same in both
frames —, the decay length βγcτ, SI conversions. The physics is ``particle_physics.kinematics``
(no manim); the action ``boost`` (``kinematics_actions.py``) moves a frame continuously."""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from . import feynman_draw as fd
from .orbit_text import LiveText

pp = particle_physics
kin = particle_physics.kinematics

#: Arrow labels, the frame headers and the numbers, relative to the readable size.
LABEL_SCALE = 1.35
HEADER_SCALE = 1.25
VALUE_SCALE = 1.15
#: The numbers with ``readout: key`` (fewer lines, larger).
KEY_VALUE_SCALE = 1.3
#: Arrow stroke, the gap between an arrow's tip and its label, between panels (scene units).
ARROW_STROKE = 7
LABEL_GAP = 0.14
PANEL_GAP = 0.6
#: Panels share one arrow scale unless their best fits differ more than this (then each panel
#: fills its half and the larger one says ``arrows ×N``).
SHARED_SCALE_LIMIT = 1.25
#: Rapidities sampled when a frame is boosted, to keep every arrow inside its panel.
BOOST_SAMPLES = 16


class KinParticle(SceneParams):
    """A particle of a system given in the lab: ``{particle, momentum, angle}``."""

    particle: str
    """The particle (gamma, e-, mu+, pi0, p, Z; Unicode works: π⁰)."""
    momentum: str
    """Its momentum with the unit: 62.6 GeV/c, 200 MeV/c."""
    angle: float = 0.0
    """Its direction in degrees from the x axis (counter-clockwise)."""


def picture(params: Any) -> Any:
    """The ``particle_physics.kinematics.MomentumPicture`` of the params."""
    if params.decay:
        lab = None
        given = {k: getattr(params, k) for k in ("momentum", "energy", "kinetic", "beta", "gamma") if getattr(params, k) is not None}
        if given:
            d = kin.two_body(params.decay)
            values = {k: (kin.natural_value(v, "momentum" if k == "momentum" else "energy") if k in ("momentum", "energy", "kinetic") else float(v))
                      for k, v in given.items()}
            lab = kin.motion(d.parent.mass_mev, **values)
            return kin.decay_picture(d, params.angle, lab)
        return kin.decay_picture(params.decay, params.angle, lab)
    items = [(pp.particle(x.particle), kin.natural_value(x.momentum, "momentum"), x.angle) for x in params.particles]
    return kin.system_picture(items)


@dataclass
class _Panel:
    """One frame of the picture on screen."""

    name: str   # rest | lab
    eta: float
    region: Any = None   # where the arrows go
    width: float = 0.0   # of the whole panel (headers and numbers)
    magnify: float = 1.0   # its arrow scale over the smallest panel's
    quiet: bool = False   # no β / γ readout
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    scale: float = 1.0
    header: VGroup = field(default_factory=VGroup)
    readout: VGroup = field(default_factory=VGroup)
    arrows: list[VGroup] = field(default_factory=list)
    labels: list[VGroup] = field(default_factory=list)
    sum_arrow: VGroup = field(default_factory=VGroup)
    sum_label: VGroup = field(default_factory=VGroup)
    values: VGroup = field(default_factory=VGroup)

    @property
    def drawing(self) -> VGroup:
        return VGroup(*self.arrows, *self.labels)

    @property
    def whole(self) -> VGroup:
        return VGroup(self.header, self.readout, self.drawing, self.sum_arrow, self.sum_label, self.values)


@scene("kinematics")
class Kinematics(NarratedScene):
    """Momentum vectors in two frames: a two-body ``decay`` (``"pi+ -> mu+ nu_mu"``) in the
    parent's rest frame and in the lab (``momentum: 10 GeV/c`` of the parent, or ``energy``,
    ``kinetic``, ``beta``, ``gamma``), or ``particles`` given in the lab with the system's rest
    frame; ``frames: both`` (side by side in 16:9, stacked in 9:16), ``rest`` or ``lab``. Each
    frame shows its arrows to scale (momenta at the tips), the sum vector and its numbers:
    p*, energies, β, γ, the opening angle, the invariant mass (the same in both), the decay
    length βγcτ, SI conversions (``si: true``). Values from PDG 2024.

    Action targets: ``title``, ``caption``, ``process``, ``panel:rest``, ``panel:lab``,
    ``arrow:<n>`` (1, 2… in order) and ``arrow:<particle>``, ``sum``, ``values``.
    """

    outro = 0.5
    kinematics_actions = True
    target_patterns = ("title", "caption", "process", "panel:rest", "panel:lab", "arrow:<n>", "arrow:<particle>", "sum", "values")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title above the picture."""
        caption: TranslatableStr = ""
        """Note under the picture."""
        decay: str | None = None
        """A two-body decay: "pi+ -> mu+ nu_mu", "K+ -> pi+ pi0", "Lambda -> p pi-", "H -> gamma gamma" (checked: allowed and above threshold)."""
        particles: list[KinParticle] = Field(default_factory=list)
        """Particles given in the lab instead of a decay: [{particle: gamma, momentum: 62.6 GeV/c, angle: 30}, ...]."""
        momentum: str | None = None
        """The decaying particle's momentum in the lab: 10 GeV/c, 200 MeV/c."""
        energy: str | None = None
        """…or its total energy in the lab: 4 GeV."""
        kinetic: str | None = None
        """…or its kinetic energy in the lab: 1 GeV."""
        beta: float | None = None
        """…or its speed β = v/c (0 ≤ β < 1)."""
        gamma: float | None = None
        """…or its Lorentz factor γ (≥ 1)."""
        angle: float = 60.0
        """Decay: the first product's direction in the rest frame, degrees from the flight direction (the second goes opposite)."""
        frames: Literal["both", "rest", "lab"] = "both"
        """both: the rest frame and the lab side by side (stacked in 9:16); rest or lab: one frame (boost moves it)."""
        values: bool = True
        """Write each frame's numbers (p*, energies, β, γ, opening angle, invariant mass, decay length)."""
        readout: Literal["key", "all"] = "key"
        """key: each frame's main numbers, large (p*, the invariant mass, the parent's p and E, βγcτ or the opening angle; the SI line with si); all: every number, smaller (the energies too)."""
        sum: bool = True
        """Draw the sum of the momenta (Σp; zero in the rest frame)."""
        decay_length: bool = True
        """Decay: the parent's mean decay length L = βγcτ in the lab (when it has a lifetime)."""
        si: bool = False
        """Add the SI conversion of the main value (p* in kg·m/s, the parent's energy in J, the invariant mass in kg)."""
        process: bool = True
        """Write the decay or the particles under the title."""
        reveal: Literal["steps", "all"] = "steps"
        """steps: the first frame, then the second, then the sums and numbers over the beats; all: everything in beat 1."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""

        @model_validator(mode="after")
        def _picture(self) -> "Kinematics.Params":
            if bool(self.decay) == bool(self.particles):
                raise ValueError("give a decay (decay: \"pi+ -> mu+ nu_mu\") or particles (particles: [{particle: gamma, momentum: 62.6 GeV/c}]), one of the two")
            given = [k for k in ("momentum", "energy", "kinetic", "beta", "gamma") if getattr(self, k) is not None]
            if self.particles and given:
                raise ValueError(f"{', '.join(given)}: for a decay only (particles carry their own momenta)")
            if len(given) > 1:
                raise ValueError(f"give one of momentum, energy, kinetic, beta or gamma (got {', '.join(given)})")
            if self.decay and not given and self.frames != "rest":
                raise ValueError(f"frames: {self.frames} shows the lab: give the decaying particle's momentum (momentum: 10 GeV/c), energy, kinetic, beta "
                                 "or gamma, or use frames: rest")
            try:
                picture(self)
            except VidgenError as exc:
                raise ValueError(str(exc)) from None
            return self

    # ----- names -------------------------------------------------------------------------------

    @classmethod
    def frame_names(cls, params: Any) -> list[str]:
        return ["rest", "lab"] if params.frames == "both" else [params.frames]

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        pic = picture(params)
        names = (["title"] if params.title else []) + (["caption"] if params.caption else []) + (["process"] if params.process else [])
        names += [f"panel:{f}" for f in cls.frame_names(params)]
        names += [f"arrow:{k}" for k in range(1, len(pic.particles) + 1)]
        keys = [p.key for p in pic.particles]
        names += [f"arrow:{k}" for k in dict.fromkeys(keys) if keys.count(k) == 1]
        names += (["sum"] if params.sum else []) + (["values"] if params.values else [])
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """An arrow's particle name, the title (for the narration lint)."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        if kind == "arrow":
            parts = picture(params).particles
            if key.isdigit() and 1 <= int(key) <= len(parts):
                return parts[int(key) - 1].name
            return next((p.name for p in parts if p.key == key), None)
        return None

    @classmethod
    def calc_values(cls, params: Any) -> dict[str, tuple[float, str]]:
        """What a ``calculation`` may take (``from_scene: <id>.p_star``): name → (SI value, unit
        shown). A decay: ``M``, ``p_star``, ``E1``, ``E2``, ``Q``; with the lab: ``beta``,
        ``gamma``, ``beta_gamma``, ``p_lab``, ``E_lab``, ``opening_angle``, ``decay_length``.
        Particles: ``m_inv``, ``E_total``, ``p_total``, and ``opening_angle`` for two."""
        pic = picture(params)

        def energy(mev: float, kind: str = "energy") -> tuple[float, str]:
            unit = "GeV" if abs(mev) >= 1000 else "MeV"
            return kin.to_si(mev, kind), unit + {"energy": "", "momentum": "/c", "mass": "/c^2"}[kind]

        out: dict[str, tuple[float, str]] = {}
        d = pic.decay
        if d is not None:
            e1, e2 = d.energies
            out.update(M=energy(d.parent.mass_mev, "mass"), p_star=energy(d.p_star, "momentum"), E1=energy(e1), E2=energy(e2), Q=energy(d.q_value))
            if pic.eta_lab > 0:
                b = pic.motion(pic.eta_lab)
                parent = d.parent_vector(b)
                out.update(beta=(b.beta, ""), gamma=(b.gamma, ""), beta_gamma=(b.beta_gamma, ""), p_lab=energy(parent.p, "momentum"),
                           E_lab=energy(parent.energy))
                lab = pic.lab
                if lab[0].p > 0 and lab[1].p > 0:
                    out["opening_angle"] = (math.radians(kin.opening_angle(*lab)), "deg")
                if d.parent.lifetime is not None and not d.parent.stable:
                    length = kin.DecayLength(d.parent, b).length
                    out["decay_length"] = (length, next((u for u, s in kin.LENGTH_UNITS if length >= s), "m").replace("µm", "um"))
            return out
        lab = pic.lab
        t = kin.total(lab)
        out.update(m_inv=energy(pic.mass, "mass"), E_total=energy(t.energy), p_total=energy(t.p, "momentum"))
        if len(lab) == 2 and lab[0].p > 0 and lab[1].p > 0:
            out["opening_angle"] = (math.radians(kin.opening_angle(*lab)), "deg")
        return out

    # ----- building ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._pic = picture(p)
        self._small = readable_size(margin=1.08)
        self._colors = [self.theme.palette_color(k) for k in range(len(self._pic.particles))]
        # one decay frame in a tall picture: the flight direction points up, along the frame's length
        self._turn = self.is_portrait and p.decay is not None and p.frames != "both"
        self._sum_color = self.theme.color("dim")
        self._number_text = LiveText(self.theme, self._small * LABEL_SCALE * 0.82, self.theme.color("dim"))
        self._readout_text = LiveText(self.theme, self._small * VALUE_SCALE, self.theme.color("dim"))
        area = self.safe_area
        self._title = None
        if p.title:
            self._title = chart_title(p.title, size=p.title_size, color=p.title_color, area=area)
            area = area.below(self._title, gap=0.25)
        self._process = None
        if p.process:
            self._process = self._process_line()
            self._process.move_to(np.array([area.center[0], area.y1 - self._process.height / 2, 0]))
            area = area.below(self._process, gap=0.3)
        self._caption = None
        if p.caption:
            self._caption = chart_caption(p.caption, area, color=p.caption_color)
            area = area.above(self._caption, gap=0.2)
        lab_eta = self._pic.eta_lab
        self._panels = [_Panel(name, 0.0 if name == "rest" else lab_eta) for name in self.frame_names(p)]
        self._lay_out(area)
        for panel in self._panels:
            self._place(panel, panel.eta)
        self._register()
        self.reveal(self._steps(), fraction=0.7, cap=1.0)
        self.finish()

    def _process_line(self) -> VGroup:
        """``π⁺ → μ⁺ ν_μ · p* = 29.79 MeV/c`` or the particles of a system."""
        pic = self._pic
        size = self._small * 1.35
        color = self.theme.color("text")
        parts: list[Mobject] = []
        if pic.decay is not None:
            parts.append(fd.particle_label(self, pic.decay.parent, False, size, color))
            parts.append(self.text("→", size=size, color="text"))
        parts += [fd.particle_label(self, x, False, size, color) for x in pic.particles]
        line = VGroup(*parts).arrange(RIGHT, buff=0.16)
        if line.width > self.safe_area.width:
            line.scale(self.safe_area.width / line.width)
        return line

    def _states(self, panel: _Panel) -> list[float]:
        """The rapidities this panel shows: its own and those the ``boost`` actions move it to
        (and between)."""
        etas = [panel.eta]
        if panel is self._panels[-1]:
            for use in self.action_uses("boost"):
                etas.append(self.eta_of(use.options.to, panel.eta))
        lo, hi = min(etas), max(etas)
        if hi - lo > 1e-9:
            etas += [lo + (hi - lo) * k / BOOST_SAMPLES for k in range(BOOST_SAMPLES + 1)]
        return etas

    def eta_of(self, to: Any, current: float) -> float:
        """The rapidity of a boost's ``to``: lab, rest or a β."""
        if to is None:
            return self._pic.eta_lab if abs(current) < 1e-12 else 0.0
        if to == "lab":
            return self._pic.eta_lab
        if to == "rest":
            return 0.0
        return self._pic.eta_of(float(to))

    def _xy(self, v: Any) -> np.ndarray:
        """A momentum's direction on screen (MeV/c): x right, y up; turned a quarter (the flight
        direction up) for one decay frame in a tall picture."""
        return np.array([-v.py, v.px, 0.0]) if self._turn else np.array([v.px, v.py, 0.0])

    def _extent(self, etas: list[float]) -> tuple[float, float, float, float]:
        """The box (MeV/c) holding the origin, every arrow tip and the sum over ``etas``."""
        xs, ys = [0.0], [0.0]
        for eta in etas:
            vs = self._pic.vectors(eta)
            for v in vs + [kin.total(vs)]:
                x, y, _ = self._xy(v)
                xs.append(x)
                ys.append(y)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        span = max(x1 - x0, y1 - y0, 1e-9)
        if x1 - x0 < 0.3 * span:   # a picture along one line: give it some room across
            c = (x0 + x1) / 2
            x0, x1 = c - 0.15 * span, c + 0.15 * span
        if y1 - y0 < 0.3 * span:
            c = (y0 + y1) / 2
            y0, y1 = c - 0.15 * span, c + 0.15 * span
        return x0, x1, y0, y1

    def _lay_out(self, area: Any) -> None:
        """Split the area into the panels, put each one's header and numbers, and fit its arrows
        (one scale for both frames unless their momenta differ too much)."""
        p = self.params
        n = len(self._panels)
        portrait = self.is_portrait
        boxes = []
        for k in range(n):
            if n == 1:
                boxes.append(area)
            elif portrait:
                h = (area.height - PANEL_GAP) / 2
                top = area.y1 - k * (h + PANEL_GAP)
                boxes.append(Region(area.x0, top - h, area.x1, top))
            else:
                w = (area.width - PANEL_GAP) / 2
                left = area.x0 + k * (w + PANEL_GAP)
                boxes.append(Region(left, area.y0, left + w, area.y1))
        scales = []
        for panel, box in zip(self._panels, boxes):
            panel.width = box.width
            panel.header = self.text(self._header_text(panel.eta, panel), size=self._small * HEADER_SCALE, color="text")
            panel.header.move_to(np.array([box.center[0], box.y1 - panel.header.height / 2, 0]))
            if panel.header.width > box.width:
                panel.header.scale_to_fit_width(box.width)
            panel.quiet = n == 2 and panel is self._panels[0]   # a rest frame beside the lab: β = 0 goes without saying
            if panel.quiet:
                inner = box.below(panel.header, gap=0.15)
            else:
                panel.readout = self._readout(panel.eta)
                panel.readout.move_to(np.array([box.center[0], panel.header.get_bottom()[1] - 0.12 - panel.readout.height / 2, 0]))
                inner = box.below(panel.readout, gap=0.15)
            if p.values:
                panel.values = self._values(panel.eta, box.width)
                ends = {round(e, 9) for e in self._states(panel)[:1 + len(self.action_uses("boost"))]}   # the frames it rests in
                tallest = max(self._values(e, box.width).height for e in ends) if len(ends) > 1 else panel.values.height
                panel.values.move_to(np.array([box.center[0], inner.y0 + tallest - panel.values.height / 2, 0]))
                inner = inner.above(inner.y0 + tallest, gap=0.2)
            panel.region = inner
            scales.append(self._fit_scale(self._states(panel), inner))
        shared = min(scales)
        if max(scales) / shared <= SHARED_SCALE_LIMIT:
            scales = [shared] * n
        for panel, s in zip(self._panels, scales):
            panel.magnify = s / min(scales)
            if panel.magnify > 1.0001:   # said in the header: these arrows are drawn larger
                header = self.text(self._header_text(panel.eta, panel), size=self._small * HEADER_SCALE, color="text").move_to(panel.header)
                panel.header = header.scale_to_fit_width(panel.width) if header.width > panel.width else header
            bx0, bx1, by0, by1 = self._bounds(self._states(panel), s)
            panel.scale = s
            panel.origin = panel.region.center - np.array([(bx0 + bx1) / 2, (by0 + by1) / 2, 0.0])
            k = len(self._pic.particles)
            panel.arrows = [VGroup() for _ in range(k)]
            panel.labels = [self._label(i) for i in range(k)]
            panel.sum_arrow, panel.sum_label = VGroup(), self._sum_label()

    def _label_size(self) -> tuple[float, float]:
        """The largest label (name and momentum) an arrow carries in any frame."""
        if not hasattr(self, "_label_box"):
            etas = [eta for panel in self._panels for eta in self._states(panel)]
            top = max((v.p for eta in etas for v in [*self._pic.vectors(eta), kin.total(self._pic.vectors(eta))]), default=0.0)
            number_w, number_h = self._number_text.size_of(kin.value_text(top, "momentum", 3).translate(str.maketrans("123456789", "888888888")))
            names = [self._label(i)[0] for i in range(len(self._pic.particles))] + [self._sum_label()[0]]
            self._label_box = (max(m.width for m in names) + 0.12 + number_w, max(max(m.height for m in names), number_h))
        return self._label_box

    def _bounds(self, etas: list[float], scale: float) -> tuple[float, float, float, float]:
        """The box (scene units, relative to the origin) of the arrows and their labels over
        ``etas`` at ``scale``."""
        w, h = self._label_size()
        xs, ys = [0.0], [0.0]
        for eta in etas:
            vs = self._pic.vectors(eta)
            for v in vs + ([kin.total(vs)] if self.params.sum else []):
                tip = self._xy(v)[:2] * scale
                n = float(np.hypot(*tip))
                xs.append(tip[0])
                ys.append(tip[1])
                if n < 1e-9:
                    continue
                u = tip / n
                reach = min(w / 2 / max(abs(u[0]), 1e-9), h / 2 / max(abs(u[1]), 1e-9)) + LABEL_GAP
                c = tip + u * reach
                xs += [c[0] - w / 2, c[0] + w / 2]
                ys += [c[1] - h / 2, c[1] + h / 2]
        return min(xs), max(xs), min(ys), max(ys)

    def _fit_scale(self, etas: list[float], inner: Any) -> float:
        """The arrow scale (scene units per MeV/c) at which the arrows and their labels fill
        ``inner`` (labels do not scale, so a few rounds)."""
        x0, x1, y0, y1 = self._extent(etas)
        s = s0 = min(inner.width / (x1 - x0), inner.height / (y1 - y0))
        for _ in range(8):
            bx0, bx1, by0, by1 = self._bounds(etas, s)
            f = min(inner.width / max(bx1 - bx0, 1e-9), inner.height / max(by1 - by0, 1e-9))
            if abs(f - 1) < 0.01:
                break
            s *= f if f < 1 else min(f, 1.5)
        while True:   # make sure it fits (labels wider than the panel: arrows at a fifth of the plain fit)
            bx0, bx1, by0, by1 = self._bounds(etas, s)
            if bx1 - bx0 <= inner.width + 1e-6 and by1 - by0 <= inner.height + 1e-6 or s < 0.2 * s0:
                return s
            s *= 0.95

    def _header_text(self, eta: float, panel: _Panel) -> str:
        """``rest frame of π⁺``, ``lab frame``, ``boosted frame``; ``· arrows ×6.2`` when this
        frame's arrows are drawn larger than the other's."""
        pic = self._pic
        if abs(eta) < 1e-12:
            text = f"rest frame of {pic.decay.parent.symbol}" if pic.decay is not None else "rest frame (Σp = 0)"
        elif abs(eta - pic.eta_lab) < 1e-9:
            text = "lab frame"
        else:
            text = "boosted frame"
        return text + (f"  ·  arrows ×{panel.magnify:.2g}" if panel.magnify > 1.0001 else "")

    def _readout_string(self, eta: float) -> str:
        b = self._pic.motion(eta)
        who = self._pic.decay.parent.symbol if self._pic.decay is not None else "system"
        return f"{who}: β = {b.beta:.3f}   γ = {_gamma_text(b.gamma)}"

    def _readout(self, eta: float) -> VGroup:
        return VGroup(*self._readout_text.text(self._readout_string(eta)))

    def _label(self, i: int) -> VGroup:
        symbol = fd.particle_label(self, self._pic.particles[i], False, self._small * LABEL_SCALE, self._colors[i])
        return VGroup(symbol, VGroup())

    def _sum_label(self) -> VGroup:
        symbol = self.text("Σp", size=self._small * LABEL_SCALE, color=self._sum_color)
        return VGroup(symbol, VGroup())

    def _values(self, eta: float, width: float) -> VGroup:
        scale = VALUE_SCALE if self.params.readout == "all" else KEY_VALUE_SCALE
        rows = [fit_text(line, width, None, size=self._small * scale, color="text" if k == 0 else "dim", min_size=self._small)
                for k, line in enumerate(self.value_lines(eta))]
        return VGroup(*rows).arrange(DOWN, buff=0.12)

    def value_lines(self, eta: float) -> list[str]:
        """The numbers a frame at rapidity ``eta`` shows: with ``readout: key`` its main ones
        (at most three, written large), with ``readout: all`` every one."""
        every = self.params.readout == "all"
        return [text for key, text in self._value_items(eta) if every or key]

    def _value_items(self, eta: float) -> list[tuple[bool, str]]:
        """Every number of a frame, each marked whether it is a key number."""
        p, pic = self.params, self._pic
        vs = pic.vectors(eta)
        t = kin.total(vs)
        mass = f"√((ΣE)² − |Σp|²) = {kin.value_text(pic.mass, 'mass')}"
        d = pic.decay
        key = p.readout == "key"
        if d is not None and abs(eta) < 1e-12:
            e1, e2 = d.energies
            items = [(True, f"p* = {kin.value_text(d.p_star, 'momentum')}"),
                     (False, f"E: {_plain(d.first.symbol)} {kin.value_text(e1)} · {_plain(d.second.symbol)} {kin.value_text(e2)}"), (True, mass)]
            if p.si:   # key: the SI value alone, short enough for one large line
                items.append((True, "p* = " + (kin.si_text(d.p_star, "momentum").split(" = ", 1)[1] if key else kin.si_text(d.p_star, "momentum"))))
            return items
        if d is not None:
            b = pic.motion(eta)
            parent = d.parent_vector(b)
            p_text, e_text = kin.value_text(parent.p, "momentum"), kin.value_text(parent.energy)
            items = [(True, f"{d.parent.symbol}: p = {p_text}")] + [(False, f"E = {e_text}")] if key else [(True, f"{d.parent.symbol}: p = {p_text}, E = {e_text}")]
            long_lived = p.decay_length and d.parent.lifetime is not None and not d.parent.stable
            if vs[0].p > 0 and vs[1].p > 0:
                items.append((not long_lived, f"opening angle {kin.opening_angle(*vs):.1f}°"))
            items.append((True, mass))
            if long_lived:
                items.append((True, f"βγcτ = {kin.length_text(kin.DecayLength(d.parent, b).length)}"))
            if p.si:
                items.append((False, "E = " + kin.si_text(parent.energy, "energy")))
            return items
        items = [(True, f"ΣE = {kin.value_text(t.energy)} · |Σp| = {kin.value_text(t.p, 'momentum') if t.p > 1e-6 * t.energy else '0'}")]
        if len(vs) == 2 and vs[0].p > 0 and vs[1].p > 0:
            items.append((True, f"opening angle {kin.opening_angle(*vs):.1f}°"))
        items.append((True, mass))
        if p.si:
            items.append((False, "m = " + kin.si_text(pic.mass, "mass")))
        return items

    # ----- the arrows in a frame -------------------------------------------------------------

    def _arrow(self, start: np.ndarray, end: np.ndarray, color: Any, opacity: float = 1.0) -> Mobject:
        length = float(np.linalg.norm(end - start))
        if length < 0.02:
            return VMobject()
        arrow = Arrow(start, end, buff=0, stroke_width=ARROW_STROKE, max_tip_length_to_length_ratio=0.3, max_stroke_width_to_length_ratio=12)
        arrow.set_color(color)
        if opacity < 1:
            arrow.set_opacity(opacity)
        return arrow

    def _place(self, panel: _Panel, eta: float) -> None:
        """Draw ``panel``'s arrows, labels and sum for the frame at ``eta`` (rebuilt in place:
        the containers keep their identity, so targets and a ``boost`` follow them)."""
        vs = self._pic.vectors(eta)
        o = panel.origin
        tips = [o + self._xy(v) * panel.scale for v in vs]
        for i, (v, tip) in enumerate(zip(vs, tips)):
            _replace(panel.arrows[i], [self._arrow(o, tip, self._colors[i])])
            self._put_label(panel.labels[i], o, tip, kin.value_text(v.p, "momentum", 3) if v.p > 0 else "at rest")
        t = kin.total(vs)
        if self.params.sum:
            tip = o + self._xy(t) * panel.scale
            shown = t.p > 1e-6 * max(t.energy, 1e-12) and float(np.linalg.norm(tip - o)) >= 0.02
            _replace(panel.sum_arrow, [self._arrow(o, tip, self._sum_color, 0.75)] if shown else [])
            self._put_label(panel.sum_label, o, tip if shown else o + np.array([0.0, -0.01, 0.0]), kin.value_text(t.p, "momentum", 3) if shown else "0")
            panel.sum_label.set_opacity(1.0 if shown else 0.0)
        self._separate(panel)
        if panel.quiet:
            return
        _replace(panel.readout, list(self._readout_text.text(self._readout_string(eta)).submobjects))
        panel.readout.move_to(np.array([panel.header.get_center()[0], panel.header.get_bottom()[1] - 0.12 - panel.readout.height / 2, 0]))

    def _put_label(self, label: VGroup, origin: np.ndarray, tip: np.ndarray, number: str) -> None:
        """The particle's name and momentum beyond the arrow's tip."""
        symbol = label[0]
        num = self._number_text.text(number)
        _replace(label, [symbol, VGroup(*num.submobjects)])
        label[1].next_to(symbol, RIGHT, buff=0.12).align_to(symbol, DOWN)
        d = tip - origin
        n = float(np.linalg.norm(d))
        u = d / n if n > 1e-9 else np.array([0.0, -1.0, 0.0])
        # the centre goes along the arrow just far enough for the box to clear the tip
        reach = min(label.width / 2 / max(abs(u[0]), 1e-9), label.height / 2 / max(abs(u[1]), 1e-9))
        label.move_to(tip + u * (reach + LABEL_GAP))

    def _separate(self, panel: _Panel) -> None:
        """Move a label that overlaps an earlier one up or down (away from it) until it is clear."""
        placed: list[VGroup] = []
        items = list(zip(panel.labels, panel.arrows)) + ([(panel.sum_label, panel.sum_arrow)] if self.params.sum else [])
        for label, arrow in items:
            if not label.submobjects or (label is panel.sum_label and not arrow.submobjects):
                continue
            for _ in range(4):
                hit = next((other for other in placed if _overlap(label, other) > 0), None)
                if hit is None:
                    break
                dy = label.get_center()[1] - hit.get_center()[1]
                step = (hit.height + label.height) / 2 - abs(dy) + 0.06
                label.shift(np.array([0.0, step if dy >= 0 else -step, 0.0]))
            placed.append(label)

    # ----- targets and reveal ----------------------------------------------------------------

    def _register(self) -> None:
        if self._title is not None:
            self.target("title", self._title, entrance=lambda: [FadeIn(self._title, shift=DOWN * 0.15)])
        if self._caption is not None:
            self.target("caption", self._caption, entrance=lambda: [FadeIn(self._caption)])
        if self._process is not None:
            self.target("process", self._process, entrance=lambda: [FadeIn(self._process, shift=DOWN * 0.1)])
        for panel in self._panels:
            self.target(f"panel:{panel.name}", panel.whole, entrance=lambda panel=panel: self._panel_entrance(panel) + self._sum_entrance(panel)
                        + self._values_entrance(panel))
        keys = [x.key for x in self._pic.particles]
        for i, key in enumerate(keys):
            names = [f"arrow:{i + 1}"] + ([f"arrow:{key}"] if keys.count(key) == 1 else [])
            group = VGroup(*[m for panel in self._panels for m in (panel.arrows[i], panel.labels[i])])
            self.target(names, group, entrance=lambda i=i: [a for panel in self._panels for a in self._arrow_entrance(panel, i)])
        if self.params.sum:
            self.target("sum", VGroup(*[m for panel in self._panels for m in (panel.sum_arrow, panel.sum_label)]),
                        entrance=lambda: [a for panel in self._panels for a in self._sum_entrance(panel)])
        if self.params.values:
            self.target("values", VGroup(*[panel.values for panel in self._panels]),
                        entrance=lambda: [a for panel in self._panels for a in self._values_entrance(panel)])

    def _new(self, m: Mobject) -> bool:
        """``m`` has something to draw and is not on screen yet."""
        return bool(m.family_members_with_points()) and id(m) not in {id(x) for x in self.get_mobject_family_members()}

    def _panel_entrance(self, panel: _Panel) -> list[Animation]:
        anims: list[Animation] = [FadeIn(m) for m in (panel.header, panel.readout) if self._new(m)]
        for i in range(len(panel.arrows)):
            anims += self._arrow_entrance(panel, i)
        return anims

    def _arrow_entrance(self, panel: _Panel, i: int) -> list[Animation]:
        """An arrow grows from the origin, its label fades in."""
        anims: list[Animation] = []
        if self._new(panel.arrows[i]):
            anims.append(GrowFromPoint(panel.arrows[i], panel.origin))
        elif id(panel.arrows[i]) not in {id(x) for x in self.get_mobject_family_members()}:
            self.add(panel.arrows[i])   # empty (a particle at rest): on screen, so a boost can grow it
        if self._new(panel.labels[i]):
            anims.append(FadeIn(panel.labels[i]))
        return anims

    def _sum_entrance(self, panel: _Panel) -> list[Animation]:
        if not self.params.sum:
            return []
        on_screen = {id(x) for x in self.get_mobject_family_members()}
        if not panel.sum_arrow.submobjects:   # Σp = 0: on screen empty, so a boost can grow it
            self.add(*[m for m in (panel.sum_arrow, panel.sum_label) if id(m) not in on_screen])
            return []
        return [GrowFromPoint(panel.sum_arrow, panel.origin)] * self._new(panel.sum_arrow) + [FadeIn(panel.sum_label)] * self._new(panel.sum_label)

    def _values_entrance(self, panel: _Panel) -> list[Animation]:
        if self.params.values and self._new(panel.values):
            return [FadeIn(panel.values)]
        return []

    def _steps(self) -> list[Any]:
        """The first frame (with title, reaction and headers), the second frame, then the sums
        and numbers (and caption)."""
        frame = [n for n in ("title", "process") if getattr(self, f"_{n}") is not None]

        def first() -> list[Animation]:
            anims = [a for n in frame for a in self.entrance(n)] + self._panel_entrance(self._panels[0])
            for panel in self._panels[1:]:   # the other frames' headers (their arrows come next)
                anims += [FadeIn(m) for m in (panel.header, panel.readout) if self._new(m)]
            return anims

        def second() -> list[Animation]:
            return [a for panel in self._panels[1:] for a in self._panel_entrance(panel)]

        def last() -> list[Animation]:
            anims = [a for panel in self._panels for a in self._sum_entrance(panel) + self._values_entrance(panel)]
            return anims + (self.entrance("caption") if self._caption is not None else [])

        steps = [first] + ([second] if len(self._panels) > 1 else []) + [last]
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

    # ----- the boost action ------------------------------------------------------------------

    def boost(self, to: Any) -> tuple[list[Animation], float]:
        """Move the last frame continuously (rapidity linear in time) to ``to`` (lab, rest or a
        β); its header and numbers morph into the new frame's. Returns the animations and the
        rapidity it started from (for undoing)."""
        panel = self._panels[-1]
        start = panel.eta
        end = self.eta_of(to, start)
        if abs(end - start) < 1e-12:
            return [], start
        on_screen = {id(x) for x in self.get_mobject_family_members()}
        self.add(*[m for m in (*panel.arrows, *panel.labels, panel.sum_arrow, panel.sum_label, panel.readout) if id(m) not in on_screen])

        def update(_m: Mobject, alpha: float) -> None:
            self._place(panel, start + (end - start) * alpha)

        # the readout is on screen: the update redraws the panel's arrows, labels and sum too
        anims: list[Animation] = [UpdateFromAlphaFunc(panel.readout, update)]
        header = self.text(self._header_text(end, panel), size=self._small * HEADER_SCALE, color="text").move_to(panel.header)
        if header.width > panel.width:
            header.scale_to_fit_width(panel.width)
        anims.append(Transform(panel.header, header))
        if self.params.values and len(panel.values.submobjects):
            new = self._values(end, panel.width)
            new.move_to(panel.values.get_center()).align_to(panel.values, UP)
            anims.append(Transform(panel.values, new))
        panel.eta = end
        return anims, start


def _replace(container: Mobject, parts: list[Mobject]) -> None:
    """Give ``container`` new ``parts``. The parts it drops are made invisible: while an
    animation runs, the renderer keeps drawing the family it saw when the animation began."""
    keep = {id(m) for m in parts}
    for old in container.submobjects:
        if id(old) not in keep:
            old.set_opacity(0)
    container.submobjects = list(parts)


def _overlap(a: Mobject, b: Mobject) -> float:
    """The area two mobjects' boxes share."""
    w = min(a.get_right()[0], b.get_right()[0]) - max(a.get_left()[0], b.get_left()[0])
    h = min(a.get_top()[1], b.get_top()[1]) - max(a.get_bottom()[1], b.get_bottom()[1])
    return w * h if w > 0 and h > 0 else 0.0


def _plain(symbol: str) -> str:
    """A particle symbol for plain text: ``ν_μ`` → ``νμ`` (the subscript is set apart in the
    arrow labels, not in a line of numbers)."""
    return symbol.replace("_", "")


def _gamma_text(gamma: float) -> str:
    """γ with four significant figures (1.000, 37.86, 1068)."""
    return quantities.decimal_text(gamma, 4, "plain").plain if gamma < 1e5 else f"{gamma:.3g}"


__all__ = ["Kinematics", "KinParticle", "picture"]
