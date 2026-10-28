"""``feynman``: Feynman diagrams in standard notation (Phase Y, Step 238; DESIGN §99.6) — fermion
lines with arrows on the fermion-number flow (an antifermion's against time), photons and W / Z
wavy, gluons curly, the Higgs boson dashed, vertices as dots, every external line labelled, the
time direction stated. The diagram comes from a preset or from lines written by id; its layout
(``particle_physics.feynman_layout``) is automatic, and every vertex is checked against the
Standard Model before anything is drawn (``particle_physics.feynman``). Lines appear in time
order over the beats; the actions ``travel``, ``vertex_rule`` and ``swap_channel`` are in
``feynman_actions.py``."""

import logging
import re
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from . import feynman_draw as fd

log = logging.getLogger("vidgen.scenes")

pp = particle_physics
fy = particle_physics.feynman
PresetName = Literal["ee_to_mumu", "compton", "bhabha", "moller", "beta_decay", "muon_decay", "pion_decay", "drell_yan", "gg_to_h",
                     "h_to_gammagamma", "h_to_zz_4l", "top_decay"]
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LINE_TEXT = re.compile(r"^\s*(?:(?P<id>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*)?(?P<particle>\S+)\s+(?P<start>\S+)\s*->\s*(?P<end>\S+)\s*$")
#: Space between a line's open end and its label, and between labels and a hadron bracket.
LABEL_GAP = 0.14
BRACKET_GAP = 0.12
#: Largest size of one transverse unit of the layout (scene units) and the widest time / transverse
#: ratio of the drawing.
MAX_UNIT = 3.0
MAX_STRETCH = 2.8
#: How much taller than wide the drawing may grow in a portrait frame (time left → right).
PORTRAIT_STRETCH = 1.8
#: Particle labels, the reaction line and the vertex-rule text, relative to the readable size;
#: lines reserved for a vertex rule in a portrait band.
LABEL_SCALE = 1.6
PROCESS_SCALE = 1.35
NOTE_SCALE = 1.3
NOTE_LINES = 8
NOTE_BAND_SHARE = 0.3
#: Width of the vertex-rule column in wide frames (scene units, at most this share of the width).
NOTE_WIDTH = 5.0
NOTE_SHARE = 0.36
#: The last part of a ``travel`` in which its dots fade out.
TRAVEL_FADE = 0.12


class FeynmanLine(SceneParams):
    """A line: ``{id, particle, from, to, label}`` or ``"id: particle from -> to"`` (``"photon: gamma
    v1 -> v2"``, ``"e- in -> v1"``). ``from`` / ``to`` are vertex ids, ``in`` (an incoming line
    starts there) or ``out`` (an outgoing one ends there); the particle is what runs forward in
    time (an incoming positron: ``e+ in -> v1``, drawn with its arrow against time)."""

    also_accepts = (str,)

    id: str | None = None
    """Its id (target ``line:<id>``; default l1, l2… in order)."""
    particle: str
    """The particle (e-, e+, nu_e, anti-nu_e, u, anti-d, gamma, g, W+, W-, Z, H; Unicode works: ν̄ₑ); a trailing * marks it off-shell (Z*, γ*)."""
    start: str = Field(alias="from")
    """Where it starts: a vertex id or in."""
    to: str
    """Where it ends: a vertex id or out."""
    label: bool = True
    """Show its name beside it."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            m = _LINE_TEXT.match(data)
            if m is None:
                raise ValueError(f"{data!r}: write a line as 'id: particle from -> to' ('photon: gamma v1 -> v2', 'e- in -> v1')")
            return {"id": m["id"], "particle": m["particle"], "from": m["start"], "to": m["end"]}
        return data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "string", "pattern": "->"}, handler(core_schema)]}

    @field_validator("id")
    @classmethod
    def _id(cls, value: str | None) -> str | None:
        if value is not None and not _ID.match(value):
            raise ValueError(f"line id '{value}': use letters, digits and _ (starting with a letter)")
        return value

    @field_validator("start", "to")
    @classmethod
    def _end(cls, value: str) -> str:
        value = value.strip()
        if not _ID.match(value):
            raise ValueError(f"'{value}': a line end is a vertex id (v1), in or out")
        return value


class FeynmanGroup(SceneParams):
    """A hadron drawn as its quark lines: ``{particle, side, lines}`` (``{particle: n, side:
    initial, lines: [d1, u1, d2]}``); a bracket and its name beside the lines."""

    particle: str
    """The hadron (n, p, pi+, K-...); its quark content must match the lines."""
    side: Literal["initial", "final"] = "initial"
    """Which end of the lines it brackets."""
    lines: list[str] = Field(min_length=1)
    """The ids of its quark lines (incoming for initial, outgoing for final; spectators are lines from in to out)."""


class FeynmanDiagram(SceneParams):
    """One diagram written by its lines: ``{name, label, lines, groups}``."""

    name: str = ""
    """Its name (swap_channel to: <name>; default d1, d2…)."""
    label: str = ""
    """What to call it on screen after the process (s-channel, t-channel, W loop)."""
    lines: list[FeynmanLine] = Field(min_length=3)
    """Its lines (vertices are the ends other than in and out)."""
    groups: list[FeynmanGroup] = Field(default_factory=list)
    """Hadrons drawn as their quark lines."""


def build_diagrams(params: Any) -> tuple[Any, ...]:
    """The diagrams of the params: the preset's or those written out."""
    if params.preset:
        return fy.preset_diagrams(params.preset, params.spectators)
    out = []
    for i, d in enumerate(params.diagrams, start=1):
        lines = [{"id": ln.id, "particle": ln.particle, "from": ln.start, "to": ln.to, "label": ln.label} for ln in d.lines]
        groups = [{"particle": g.particle, "side": g.side, "lines": g.lines} for g in d.groups]
        out.append(fy.build_diagram(d.name or f"d{i}", lines, groups, d.label))
    return tuple(out)


def _union(diagrams: tuple[Any, ...], what: str) -> list[str]:
    found: dict[str, None] = {}
    for d in diagrams:
        items = [ln.id for ln in d.lines] if what == "lines" else (list(d.vertices) if what == "vertices" else [g.particle.key for g in d.groups])
        for x in items:
            found.setdefault(x, None)
    return list(found)


@scene("feynman")
class Feynman(NarratedScene):
    """A Feynman diagram from a ``preset`` (ee_to_mumu, compton, bhabha, moller, beta_decay,
    muon_decay, pion_decay, drell_yan, gg_to_h, h_to_gammagamma, h_to_zz_4l, top_decay) or
    ``diagrams`` written by their lines; checked vertex by vertex against the Standard Model.
    ``reveal: time`` (default) draws the incoming lines, then each vertex and the lines leaving
    it, in time order over the beats; ``all`` draws everything in the first beat.

    Action targets: ``title``, ``caption``, ``process`` (the reaction line), ``diagram``,
    ``time_axis``, ``line:<id>``, ``vertex:<id>``, ``hadron:<particle>`` (a group's bracket).
    """

    outro = 0.5
    feynman_actions = True
    target_patterns = ("title", "caption", "process", "diagram", "time_axis", "line:<id>", "vertex:<id>", "hadron:<particle>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title above the diagram."""
        caption: TranslatableStr = ""
        """Note under the diagram."""
        preset: PresetName | None = None
        """A standard diagram: ee_to_mumu (s-channel γ or Z), compton (s, u), bhabha (s, t), moller (t, u), beta_decay (d → u e⁻ ν̄ₑ), muon_decay, pion_decay (π⁺ → μ⁺ ν_μ), drell_yan (γ* or Z), gg_to_h (top loop), h_to_gammagamma (top or W loop), h_to_zz_4l, top_decay (t → W⁺ b; leptonic)."""
        diagrams: list[FeynmanDiagram] = Field(default_factory=list)
        """Diagrams written by their lines (instead of a preset); several for swap_channel."""
        diagram: str | None = None
        """Which of the preset's (or written) diagrams to show first: e.g. s or t (bhabha), photon or Z (ee_to_mumu, drell_yan), top or W (h_to_gammagamma), leptonic (top_decay)."""
        spectators: bool = False
        """beta_decay: draw the neutron and proton with their spectator quarks."""
        time: Literal["right", "up"] = "right"
        """Direction of time: left → right (the usual convention) or bottom → top."""
        time_axis: bool = True
        """State the time direction with an arrow."""
        process: bool = True
        """Write the reaction (with the diagram's label) under the title."""
        labels: bool = True
        """Name the lines (external lines always carry their names unless false)."""
        reveal: Literal["time", "all"] = "time"
        """time: lines drawn in time order over the beats; all: the whole diagram in beat 1."""
        fermion_color: ThemeColor = "text"
        """Colour of quark and lepton lines."""
        boson_color: ThemeColor = "accent"
        """Colour of photon, gluon, W and Z lines."""
        higgs_color: ThemeColor = "secondary"
        """Colour of Higgs lines."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""

        @model_validator(mode="after")
        def _diagrams(self) -> "Feynman.Params":
            if bool(self.preset) == bool(self.diagrams):
                raise ValueError("give a preset or diagrams (written by their lines), one of the two")
            try:
                diagrams = build_diagrams(self)
            except VidgenError as exc:
                raise ValueError(str(exc)) from None
            names = [d.name for d in diagrams]
            if len(set(names)) != len(names):
                raise ValueError(f"diagram names must differ: {', '.join(names)}")
            if self.diagram is not None and self.diagram not in names:
                raise ValueError(f"diagram '{self.diagram}' is not one of {', '.join(names)}{did_you_mean(self.diagram, names)}")
            for d in diagrams:
                checked = fy.check_diagram(d)
                if not checked.ok:
                    raise ValueError(f"diagram '{d.name}' breaks the Standard Model's rules: " + "; ".join(checked.problems))
            return self

    # ----- names -------------------------------------------------------------------------------

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        diagrams = build_diagrams(params)
        names = ["title"] if params.title else []
        names += ["caption"] if params.caption else []
        names += ["process"] if params.process else []
        names += ["diagram"] + (["time_axis"] if params.time_axis else [])
        names += [f"line:{i}" for i in _union(diagrams, "lines")]
        names += [f"vertex:{v}" for v in _union(diagrams, "vertices")]
        names += [f"hadron:{h}" for h in _union(diagrams, "groups")]
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """The name of a line's particle or a hadron (for the narration lint)."""
        kind, _, label = name.partition(":")
        if kind == "line":
            for d in build_diagrams(params):
                for ln in d.lines:
                    if ln.id == label:
                        return ln.particle.name
        if kind == "hadron":
            return pp.PARTICLES[label].name if label in pp.PARTICLES else None
        if name == "title":
            return params.title or None
        return None

    @classmethod
    def diagram_list(cls, params: Any) -> tuple[Any, ...]:
        """The diagrams of validated params (for the actions' checks)."""
        return build_diagrams(params)

    def diagram_names(self) -> list[str]:
        return [d.name for d in self._diagrams]

    @property
    def current(self) -> Any:
        """The diagram on screen."""
        return self._diagrams[self._now]

    # ----- building ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._diagrams = build_diagrams(p)
        self._checks = {d.name: fy.check_diagram(d) for d in self._diagrams}
        self._layouts = {d.name: pp.feynman_layout.layout(d) for d in self._diagrams}
        for d in self._diagrams:
            if self._layouts[d.name].crossings:
                log.warning("scene '%s': diagram '%s' is drawn with %d crossing(s) of its lines", self.spec.id, d.name, self._layouts[d.name].crossings)
        self._now = self.diagram_names().index(p.diagram) if p.diagram else 0
        self._small = readable_size(margin=1.08)
        self._label_size = self._small * LABEL_SCALE
        self._colors = {"fermion": self.theme.color(p.fermion_color), "higgs": self.theme.color(p.higgs_color)}
        for kind in ("photon", "gluon", "W", "Z"):
            self._colors[kind] = self.theme.color(p.boson_color)
        area = self.safe_area
        self._title = None
        if p.title:
            self._title = chart_title(p.title, size=p.title_size, color=p.title_color, area=area)
            area = area.below(self._title, gap=0.25)
        self._process = None
        if p.process:
            self._process = self._process_line(self.current)
            self._process.move_to(np.array([area.center[0], area.y1 - self._process.height / 2, 0]))
            area = area.below(self._process, gap=0.3)
        self._caption = None
        if p.caption:
            self._caption = chart_caption(p.caption, area, color=p.caption_color)
            area = area.above(self._caption, gap=0.2)
        self._note_region = None
        self._offset = self._centred = np.zeros(3)   # the diagram's shift from its area (centred in the frame without a rule card)
        self._rules_hidden = 0
        if self.action_uses("vertex_rule"):
            if self.is_portrait:   # a band under the diagram
                line_h = self.text("Hg", size=self._small * NOTE_SCALE).height
                band = min(NOTE_LINES * line_h + (NOTE_LINES - 1) * 0.1, NOTE_BAND_SHARE * area.height)
                self._note_region = Region(area.x0, area.y0, area.x1, area.y0 + band)
                area = area.above(area.y0 + band, gap=0.25)
            else:   # a column on the right; the diagram stays centred until the first rule card
                width = min(NOTE_WIDTH, NOTE_SHARE * area.width)
                self._note_region = Region(area.x1 - width, area.y0, area.x1, area.y1)
                area = Region(area.x0, area.y0, area.x1 - width - 0.3, area.y1)
                self._offset = self._centred = np.array([(width + 0.3) / 2, 0.0, 0.0])
        self._time_axis = None
        if p.time_axis:
            area = self._place_time_axis(area)
        self._area = area
        self._containers = {f"line:{i}": VGroup() for i in _union(self._diagrams, "lines")}
        self._containers.update({f"vertex:{v}": VGroup() for v in _union(self._diagrams, "vertices")})
        self._containers.update({f"hadron:{h}": VGroup() for h in _union(self._diagrams, "groups")})
        self._parts: dict[str, dict[str, Mobject]] = {}
        self._drawn = self._build(self.current)
        for name, parts in self._drawn["parts"].items():
            self._parts[name] = dict(parts)
            self._containers[name].add(*parts.values())
        self._time_axis_beside()
        self._register()
        self.reveal(self._steps(), fraction=0.7, cap=1.0)
        self.finish()

    def _place_time_axis(self, area: Region) -> Region:
        """The ``time`` arrow: under the diagram on the left (time right), or left of it (up)."""
        size = self._small
        if self.params.time == "right":
            arrow = fd.time_arrow(self, np.array([0.0, 0.0, 0.0]), RIGHT, 1.3, size)
            arrow.move_to(np.array([area.x0 + arrow.width / 2, area.y0 + arrow.height / 2, 0]))
            self._time_axis = arrow
            return area.above(arrow, gap=0.1)
        arrow = fd.time_arrow(self, np.array([0.0, 0.0, 0.0]), UP, 1.3, size)
        arrow.move_to(np.array([area.x0 + arrow.width / 2, area.y0 + arrow.height / 2 + 0.2, 0]))
        self._time_axis = arrow
        return Region(area.x0 + arrow.width + 0.15, area.y0, area.x1, area.y1)

    def _time_axis_beside(self) -> None:
        """Bring the time arrow next to the drawn diagram (under its left end, or left of its
        bottom), out of the corner of the frame."""
        arrow = self._time_axis
        mobs = [m for parts in self._drawn["parts"].values() for m in parts.values()]
        if arrow is None or not mobs:
            return
        left = min(m.get_left()[0] for m in mobs)
        bottom = min(m.get_bottom()[1] for m in mobs)
        if self.params.time == "right":
            arrow.set_y(max(arrow.get_y(), bottom - 0.3 - arrow.height / 2))
            arrow.align_to(np.array([max(left, self.safe_area.x0), 0, 0]), LEFT)
        else:
            arrow.set_x(max(arrow.get_x(), left - 0.35 - arrow.width / 2))
            arrow.align_to(np.array([0, bottom, 0]), DOWN)

    def _process_line(self, d: Any) -> VGroup:
        """``e⁻ e⁺ → μ⁻ μ⁺ · s-channel`` (hadrons where the diagram groups its quarks)."""
        proc = d.hadron_process() or d.process()
        size = self._small * PROCESS_SCALE
        parts: list[Mobject] = []
        for k, legs in enumerate((proc.initial, proc.final)):
            if k:
                parts.append(self.text("→", size=size, color="text"))
            parts += [fd.particle_label(self, leg.particle, leg.off_shell, size, self.theme.color("text")) for leg in legs]
        line = VGroup(*parts).arrange(RIGHT, buff=0.16)
        label = self.text(f"·  {d.label}", size=size, color="dim") if d.label else VGroup()
        group = VGroup(line, label)
        if d.label:
            label.next_to(line, RIGHT, buff=0.22).align_to(line, DOWN)
        width = self.safe_area.width
        if group.width > width:
            group.scale(width / group.width)
        return group

    # ----- geometry ----------------------------------------------------------------------------

    def _ends_labels(self, d: Any) -> dict[str, VGroup]:
        """The label of every external and spectator line (and internal ones when labels are on)."""
        out = {}
        for ln in d.lines:
            if not (self.params.labels and ln.label):
                continue
            out[ln.id] = fd.particle_label(self, ln.particle, ln.off_shell, self._label_size, self._colors[ln.kind])
            if ln.spectator:   # named at both ends
                out[ln.id + "@out"] = fd.particle_label(self, ln.particle, ln.off_shell, self._label_size, self._colors[ln.kind])
        return out

    def _mapping(self, d: Any, labels: dict[str, VGroup]) -> Any:
        """The map from layout coordinates (t, y) onto the screen for ``d``, fitted into the
        diagram area with room for the end labels and hadron brackets."""
        lay = self._layouts[d.name]
        area = self._area
        t0, y0, t1, y1 = lay.bounds
        span_y = max(y1 - y0, 1e-6)
        right = self.params.time == "right"
        ext = [ln for ln in d.lines if not ln.internal]

        def size_of(ids: list[str], horizontal: bool) -> float:
            return max([(labels[i].width if horizontal else labels[i].height) for i in ids if i in labels], default=0.0)

        initial_ids = [ln.id for ln in ext if ln.start == "in"]
        final_ids = [ln.id for ln in ext if ln.end == "out"]
        group_room = {"initial": 0.0, "final": 0.0}
        for g in d.groups:
            name = fd.particle_label(self, g.particle, False, self._label_size, self.theme.color("text"))
            room = BRACKET_GAP + fd.BRACKET_TICK + BRACKET_GAP + (name.width if right else name.height)
            group_room[g.side] = max(group_room[g.side], room)
        lead_in = size_of(initial_ids, right) + LABEL_GAP + group_room["initial"] + 0.05
        lead_out = size_of(final_ids, right) + LABEL_GAP + group_room["final"] + 0.05
        cross = size_of(initial_ids + final_ids, not right) / 2 + 0.08
        if right:
            x0, x1, yb, yt = area.x0 + lead_in, area.x1 - lead_out, area.y0 + cross, area.y1 - cross
            width, height = x1 - x0, yt - yb
            height = min(height, MAX_UNIT * span_y)
            width = min(width, MAX_STRETCH * height)
            if self.is_portrait:   # a narrow frame: the drawing may grow taller, up to a little more than square
                height = min(yt - yb, max(height, PORTRAIT_STRETCH * width))
            cx = (x0 + x1) / 2
            cy = (yb + yt) / 2
        else:
            yb, yt, x0, x1 = area.y0 + lead_in, area.y1 - lead_out, area.x0 + cross, area.x1 - cross
            width, height = x1 - x0, yt - yb
            width = min(width, MAX_UNIT * span_y)
            height = min(height, MAX_STRETCH * width)
            cx = (x0 + x1) / 2
            cy = (yb + yt) / 2
        tspan = max(t1 - t0, 1e-6)

        def to_screen(point: tuple[float, float]) -> np.ndarray:
            t, y = point
            u, v = (t - t0) / tspan - 0.5, (y - y0) / span_y - 0.5
            if right:
                return np.array([cx + u * width, cy + v * height, 0.0]) + self._offset
            return np.array([cx - v * width, cy + u * height, 0.0]) + self._offset

        return to_screen

    def _build(self, d: Any) -> dict[str, Any]:
        """Every mobject of diagram ``d``: per target name its parts (``path``, ``arrow``,
        ``label`` of a line; ``dot`` of a vertex; ``bracket``, ``name`` of a hadron), the paths
        on screen (time-ordered) and the times of the lines."""
        lay = self._layouts[d.name]
        labels = self._ends_labels(d)
        to_screen = self._mapping(d, labels)
        right = self.params.time == "right"
        parts: dict[str, dict[str, Mobject]] = {}
        paths: dict[str, Any] = {}
        times: dict[str, tuple[float, float]] = {}
        drawn_paths: list[Any] = []
        for ln in d.lines:
            geo = lay.lines[ln.id]
            a, b = to_screen(geo.start), to_screen(geo.end)
            path = fd.straight_or_arc(a, b, geo.bend)
            forward_in_time = geo.start[0] <= geo.end[0] + 1e-9
            timed = path if forward_in_time else fd.reversed_path(path)
            paths[ln.id] = timed
            times[ln.id] = lay.times(ln.id)
            color = self._colors[ln.kind]
            mob = fd.path_mobject(timed, ln.kind, color)
            item: dict[str, Mobject] = {"path": mob}
            if ln.kind == "fermion":
                item["arrow"] = fd.arrowhead(path, 0.5 if ln.internal else 0.55 if ln.start == "in" else 0.45, ln.flow > 0, color)
            parts[f"line:{ln.id}"] = item
            drawn_paths.append((ln, path))
        for v, point in lay.vertices.items():
            parts[f"vertex:{v}"] = {"dot": fd.dot(to_screen(point), self.theme.color("text"))}
        self._place_labels(d, lay, labels, drawn_paths, parts, to_screen)
        for k, side, low, high in lay.groups:
            g = d.groups[k]
            t = 0.0 if side == "initial" else 1.0
            ids = list(g.lines)
            name = fd.particle_label(self, g.particle, False, self._label_size, self.theme.color("text"))
            ends = [to_screen((t, lay.lines[i].start[1] if side == "initial" else lay.lines[i].end[1])) for i in ids]
            key_of = {i: "label_out" if side == "final" and d.line(i).spectator else "label" for i in ids}
            label_boxes = [parts[f"line:{i}"][key_of[i]] for i in ids if key_of[i] in parts[f"line:{i}"]]
            outward = (LEFT if side == "initial" else RIGHT) if right else (DOWN if side == "initial" else UP)
            if right:
                edge = min(m.get_left()[0] for m in label_boxes) if side == "initial" and label_boxes else (
                    max(m.get_right()[0] for m in label_boxes) if label_boxes else ends[0][0])
                x = edge + outward[0] * (BRACKET_GAP + fd.BRACKET_TICK)
                lo, hi = to_screen((t, low))[1] - 0.18, to_screen((t, high))[1] + 0.18
                br = fd.bracket(np.array([x, lo, 0]), np.array([x, hi, 0]), -outward, self.theme.color("dim"))
                name.next_to(br, outward, buff=BRACKET_GAP)
            else:
                edge = min(m.get_bottom()[1] for m in label_boxes) if side == "initial" and label_boxes else (
                    max(m.get_top()[1] for m in label_boxes) if label_boxes else ends[0][1])
                y = edge + outward[1] * (BRACKET_GAP + fd.BRACKET_TICK)
                xs = [to_screen((t, low))[0], to_screen((t, high))[0]]
                br = fd.bracket(np.array([min(xs) - 0.18, y, 0]), np.array([max(xs) + 0.18, y, 0]), -outward, self.theme.color("dim"))
                name.next_to(br, outward, buff=BRACKET_GAP)
            parts[f"hadron:{g.particle.key}"] = {"bracket": br, "name": name}
        return {"diagram": d, "parts": parts, "paths": paths, "times": times}

    def _place_labels(self, d: Any, lay: Any, labels: dict[str, VGroup], drawn: list[Any], parts: dict[str, dict[str, Mobject]],
                      to_screen: Any) -> None:
        """External labels beyond the open ends; internal ones beside the line's middle, on the
        side away from the diagram's centre unless that side collides with another line."""
        right = self.params.time == "right"
        centre = np.mean([to_screen(p) for p in lay.vertices.values()], axis=0)
        samples = {ln.id: [path(k / 40) for k in range(41)] for ln, path in drawn}
        for ln, path in drawn:
            label = labels.get(ln.id)
            if label is None:
                continue
            if not ln.internal:
                spots = [("label", label, ln.start == "in")]
                if ln.spectator:
                    spots.append(("label_out", labels[ln.id + "@out"], False))
                for key, mob, incoming in spots:
                    end = path(0.0) if incoming else path(1.0)
                    if right:
                        mob.move_to(end + (LEFT if incoming else RIGHT) * (LABEL_GAP + mob.width / 2))
                    else:
                        mob.move_to(end + (DOWN if incoming else UP) * (LABEL_GAP + mob.height / 2))
                    parts[f"line:{ln.id}"][key] = mob
                continue
            mid = path(0.5)
            t = fd.tangent(path, 0.5)
            normal = np.array([-t[1], t[0], 0.0])
            if np.dot(normal, mid - centre) < -1e-6 or (abs(np.dot(normal, mid - centre)) <= 1e-6 and (normal[1] < -1e-6 or (abs(normal[1]) <= 1e-6 and normal[0] < 0))):
                normal = -normal
            reach = fd.REACH[ln.kind] + 0.1
            best = None
            for sign in (1, -1):
                n = normal * sign
                extent = abs(n[0]) * label.width / 2 + abs(n[1]) * label.height / 2
                spot = mid + n * (reach + extent)
                trial = label.copy().move_to(spot)
                lo, hi = trial.get_corner(DL) - 0.05, trial.get_corner(UR) + 0.05
                hits = sum(1 for other, pts in samples.items() if other != ln.id for q in pts if lo[0] <= q[0] <= hi[0] and lo[1] <= q[1] <= hi[1])
                if best is None or hits < best[0]:
                    best = (hits, spot)
                if hits == 0:
                    break
            assert best is not None
            label.move_to(best[1])
            parts[f"line:{ln.id}"]["label"] = label

    # ----- targets and steps -------------------------------------------------------------------

    def _register(self) -> None:
        if self._title is not None:
            self.target("title", self._title, entrance=lambda: [FadeIn(self._title, shift=DOWN * 0.15)])
        if self._caption is not None:
            self.target("caption", self._caption, entrance=lambda: [FadeIn(self._caption)])
        if self._process is not None:
            self.target("process", self._process, entrance=lambda: [FadeIn(self._process, shift=DOWN * 0.1)])
        everything = list(self._containers.values())
        self.target("diagram", VGroup(*everything), entrance=lambda: [a for name in self._containers for a in self._enter(name)])
        if self._time_axis is not None:
            self.target("time_axis", self._time_axis, entrance=lambda: [FadeIn(self._time_axis)])
        for name, box in self._containers.items():
            parts = self._parts.get(name, {})
            outline = parts["path"] if "path" in parts else (parts["dot"] if "dot" in parts else None)
            self.target(name, box, outline=outline, entrance=lambda name=name: self._enter(name))

    def _enter(self, name: str) -> list[Animation]:
        """The entrance of one target's parts not on screen yet: a line is drawn in time order
        (its arrow and label fade in), a vertex dot grows."""
        anims: list[Animation] = []
        present = {id(m) for m in self.get_mobject_family_members()}
        for key, m in self._parts.get(name, {}).items():
            if id(m) in present:
                continue
            if key == "path" or key == "bracket":
                anims.append(Create(m))
            elif key == "dot":
                anims.append(GrowFromCenter(m))
            else:
                anims.append(FadeIn(m))
        return anims

    def _steps(self) -> list[Any]:
        """Time order: the incoming lines (with the title, the reaction and the time arrow), then
        for each column of vertices the dots and the lines that begin there."""
        d = self.current
        lay = self._layouts[d.name]
        frame = [name for name in ("title", "process", "time_axis") if getattr(self, f"_{name}", None) is not None]
        first = [f"line:{ln.id}" for ln in d.lines if ln.start == "in"] + [f"hadron:{g.particle.key}" for g in d.groups if g.side == "initial"]
        columns = sorted(set(lay.columns.values()))
        later: list[list[str]] = []
        for c in columns:
            names = [f"vertex:{v}" for v in d.vertices if lay.columns[v] == c]
            for ln in d.lines:
                if ln.start == "in":
                    continue
                begin = min((lay.columns[x] for x in ln.ends() if x not in ("in", "out")), default=c)
                if begin == c:
                    names.append(f"line:{ln.id}")
            if c == columns[-1]:
                names += [f"hadron:{g.particle.key}" for g in d.groups if g.side == "final"]
            later.append(names)
        if self._caption is not None:
            later[-1].append("caption")
        steps = [frame + first] + later

        def play(names: list[str]) -> list[Animation]:
            anims: list[Animation] = []
            for n in names:
                anims += self.entrance(n) if n in ("title", "process", "time_axis", "caption") else self._enter(n)
            return anims

        if self.params.reveal == "all":
            return [lambda: play([n for s in steps for n in s])]
        return [lambda names=names: play(names) for names in steps]

    # ----- the actions' drawing ----------------------------------------------------------------

    def line_ids(self, targets: list[Any]) -> list[str]:
        """The line ids of the current diagram inside ``targets`` (``diagram``: all of them)."""
        if not targets:
            return [ln.id for ln in self.current.lines]
        wanted: list[str] = []
        for t in targets:
            for n in t.names:
                if n == "diagram":
                    wanted += [ln.id for ln in self.current.lines]
                elif n.startswith("line:"):
                    wanted.append(n[5:])
        present = {ln.id for ln in self.current.lines}
        return [i for i in dict.fromkeys(wanted) if i in present]

    def travel(self, line_ids: list[str], color: str) -> list[Animation]:
        """A dot running along each line in time order (several lines: one clock, each dot on
        its line while the clock is within the line's times; a line at one time — an exchange
        drawn across — is crossed in a short moment then)."""
        paths, times = self._drawn["paths"], self._drawn["times"]
        if not line_ids:
            return []
        spans = {}
        for i in line_ids:
            a, b = times[i]
            if b - a < 1e-6:
                a, b = a - 0.08, a + 0.08
            spans[i] = (a, b)
        start = min(a for a, _ in spans.values())
        end = max(b for _, b in spans.values())
        total = max(end - start, 1e-6)
        dots = VGroup(*[Dot(paths[i](0.0), radius=0.11, color=color).set_z_index(6) for i in line_ids])
        for m in dots:
            m.set_opacity(0)

        def update(group: VGroup, alpha: float) -> None:
            clock = start + alpha * total
            fade = min(1.0, (1.0 - alpha) / TRAVEL_FADE)   # the dots leave the picture at the end
            for m, i in zip(group, line_ids):
                a, b = spans[i]
                if a - 1e-9 <= clock <= b + 1e-9 and (len(line_ids) == 1 or b - a > 0):
                    s = 0.0 if b - a < 1e-9 else (clock - a) / (b - a)
                    m.move_to(paths[i](min(1.0, max(0.0, s))))
                    m.set_opacity(fade)
                else:
                    m.set_opacity(0)

        return [UpdateFromAlphaFunc(dots, update, rate_func=linear, remover=True)]

    def show_rule(self, vertex: str, show: list[str], color: str) -> tuple[list[Animation], dict[str, Any]]:
        """Ring vertex ``vertex`` and write its rule in the note band: the vertex type and the
        lines meeting there, the coupling, the conservation checks (``show``)."""
        state: dict[str, Any] = {"ring": None, "note": None}
        checked = self._checks[self.current.name]
        if vertex not in self.current.vertices:
            return [], state
        vc = checked.vertex(vertex)
        anims: list[Animation] = self._dock() if show else []
        parts = self._drawn["parts"].get(f"vertex:{vertex}", {})   # where the dot ends (after docking)
        if "dot" in parts:
            ring = Circle(radius=0.24, color=color, stroke_width=5).move_to(parts["dot"].get_center()).set_z_index(5)
            state["ring"] = ring
            anims.append(Create(ring))
        rule = vc.rule
        lines = []
        if "rule" in show:
            lines.append(f"{rule.name if rule else 'vertex'}:  {vc.text()}")
        if "coupling" in show and rule is not None:
            lines.append(rule.coupling)
        if "checks" in show:
            lines += vc.conservation_text().split(" · ")
        region = self._note_region
        if lines and region is not None:
            side = not self.is_portrait
            size = self._small * NOTE_SCALE
            rows = [fit_text(text, region.width, region.height, size=size, color="text" if k == 0 else "dim", min_size=self._small,
                             align="left" if side else "center") for k, text in enumerate(lines)]
            note = VGroup(*rows).arrange(DOWN, buff=0.22 if side else 0.1, aligned_edge=LEFT if side else ORIGIN)
            if note.height > region.height:
                note.scale(region.height / note.height)
            note.move_to(region.center)
            if side:
                note.align_to(np.array([region.x0, 0, 0]), LEFT)
            state["note"] = note
            anims.append(FadeIn(note))
        return anims, state

    def _dock(self, offset: np.ndarray | None = None) -> list[Animation]:
        """Move the diagram to ``offset`` from its area (default none: left, beside the rule
        column; it is centred in the frame before the first rule card and after the last): the
        parts on screen glide, those still to come are swapped silently."""
        offset = np.zeros(3) if offset is None else offset
        if np.allclose(offset, self._offset):
            return []
        shift = offset - self._offset
        self._offset = offset
        drawn = self._build(self.current)
        present = {id(m) for m in self.get_mobject_family_members()}
        anims: list[Animation] = []
        for name, box in self._containers.items():
            new = drawn["parts"].get(name, {})
            keep: dict[str, Mobject] = {}
            for key, m in self._parts.get(name, {}).items():
                if key in new and id(m) in present:
                    anims.append(Transform(m, new[key]))
                    keep[key] = m
                else:
                    box.remove(m)
                    if key in new:
                        box.add(new[key])
                        keep[key] = new[key]
            self._parts[name] = keep
        self._drawn = drawn
        if self._time_axis is not None:
            if id(self._time_axis) in present:
                anims.append(self._time_axis.animate.shift(shift))
            else:
                self._time_axis.shift(shift)
        return anims

    def hide_rule(self, state: dict[str, Any]) -> list[Animation]:
        anims: list[Animation] = [FadeOut(m) for m in (state.get("ring"), state.get("note")) if m is not None and m in self.mobjects]
        self._rules_hidden += 1
        if self._rules_hidden >= len(self.action_uses("vertex_rule")):   # the last card: the diagram back to the centre
            anims += self._dock(self._centred)
        return anims

    def swap(self, to: str | None) -> list[Animation]:
        """Morph into another diagram of the scene (``to``; default the next one): lines and
        vertices with the same id move, the others are drawn or fade, the reaction line takes
        the new label."""
        names = self.diagram_names()
        target = names.index(to) if to is not None else (self._now + 1) % len(names)
        if target == self._now:
            return []
        self._now = target
        drawn = self._build(self.current)
        anims: list[Animation] = []
        present = {id(m) for m in self.get_mobject_family_members()}
        for name, box in self._containers.items():
            old = self._parts.get(name, {})
            new = drawn["parts"].get(name, {})
            keep: dict[str, Mobject] = {}
            for key, m in old.items():
                if key in new and id(m) in present:
                    anims.append(Transform(m, new[key]))
                    keep[key] = m
                elif id(m) in present:
                    anims.append(FadeOut(m))
                    box.remove(m)
                else:
                    box.remove(m)
            for key, m in new.items():
                if key not in keep:
                    box.add(m)
                    keep[key] = m
                    anims.append(Create(m) if key in ("path", "bracket") else FadeIn(m))
            self._parts[name] = keep
        self._drawn = drawn
        if self._process is not None and self._process in self.mobjects:
            new_line = self._process_line(self.current).move_to(self._process)
            anims.append(Transform(self._process, new_line))
        return anims
