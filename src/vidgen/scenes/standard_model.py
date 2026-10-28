"""``standard_model``: the chart of the Standard Model's particles (Phase Y, Step 237; DESIGN
§99.4) — quarks and leptons in three generations, the gauge bosons and the Higgs boson, each cell
with its mass, charge and spin (PDG 2024 values from ``vidgen.particle_physics``), in colour
groups. Wide frames show the classic grid; tall frames put the bosons in two rows under the
fermions. Every particle, generation, group and row is a target (``highlight``, ``dim``,
``reveal``); the actions ``antiparticles`` (turn cells into their antiparticles) and
``couplings`` (which particles a boson couples to) are in ``standard_model_actions.py``."""

import logging
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import Repaint, dim_to

log = logging.getLogger("vidgen.scenes")

pp = particle_physics
Shown = Literal["mass", "charge", "spin", "name"]
#: Group name -> the params field holding its colour.
GROUP_COLORS = {"quarks": "quark_color", "leptons": "lepton_color", "gauge_bosons": "gauge_color", "scalar_bosons": "higgs_color"}
GROUP_TARGETS = ("quarks", "leptons", "fermions", "gauge_bosons", "scalar_bosons", "bosons")
#: Space between cells, the extra space between the fermions and the bosons and between the
#: quark and lepton rows (Manim units).
CELL_GAP = 0.1
BLOCK_GAP = 0.28
FAMILY_GAP = 0.08
#: Largest width / height of a cell (wide cells hold the mass and charge on one line).
MAX_ASPECT = 1.9
#: Fill opacity of a cell (its outline is the group colour).
CELL_FILL = 0.1
#: Opacity of cells a ``couplings`` action dims.
COUPLING_DIM = 0.45
ROMAN = ("I", "II", "III")
#: Line pitch of the classic column (mass, charge, spin), in cap heights.
COLUMN_PITCH = 1.4


def source_note() -> str:
    """The values' source, as the chart prints it."""
    return f"{pp.EDITION} values. Quark masses: MS-bar (u, d, s at 2 GeV); t: direct measurements"


@scene("standard_model")
class StandardModel(NarratedScene):
    """The Standard Model chart. ``reveal: groups`` (default) brings in the quarks, the leptons,
    the gauge bosons and the Higgs boson one after another over the beats; ``all`` shows the
    whole chart in the first beat.

    Action targets: ``title``, ``chart``, ``header`` (generation numbers), ``labels`` (group
    names), ``key``, ``source``, ``caption``, ``particle:<name>`` (``particle:u`` or
    ``particle:up``, ``particle:e`` / ``electron``, ``particle:nu_mu``, ``particle:photon``,
    ``particle:W``, ``particle:H``...), ``generation:1`` … ``3``, ``group:quarks``, ``leptons``,
    ``fermions``, ``gauge_bosons``, ``scalar_bosons``, ``bosons``, ``row:up_type``,
    ``down_type``, ``charged_leptons``, ``neutrinos``.
    """

    outro = 0.5
    standard_model_actions = True
    target_patterns = ("title", "chart", "header", "labels", "key", "source", "caption", "particle:<name>", "generation:<N>",
                       "group:<group>", "row:<row>")

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title above the chart."""
        caption: TranslatableStr = ""
        """Note under the chart."""
        source: bool = True
        """Print where the values come from (PDG 2024, the quark-mass scheme)."""
        show: list[Shown] = Field(default_factory=lambda: ["mass", "charge", "spin", "name"], min_length=1)
        """What each cell shows besides the symbol: mass, charge, spin, name."""
        antiparticles: bool = False
        """Start with the quarks and leptons shown as their antiparticles."""
        reveal: Literal["groups", "all"] = "groups"
        """groups: quarks, leptons, gauge bosons, Higgs one after another over the beats; all: the whole chart in beat 1."""
        layout: Literal["auto", "wide", "tall"] = "auto"
        """wide: the classic grid (bosons in columns on the right); tall: the bosons in two rows under the fermions; auto: by the frame."""
        key: bool = True
        """A key cell naming what each position in a cell shows."""
        quark_color: ThemeColor | None = None
        """Colour of the quarks (default: the theme's third palette colour)."""
        lepton_color: ThemeColor = "tertiary"
        """Colour of the leptons."""
        gauge_color: ThemeColor = "accent"
        """Colour of the gauge bosons."""
        higgs_color: ThemeColor = "secondary"
        """Colour of the Higgs boson."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption and source note colour."""

        @field_validator("show")
        @classmethod
        def _unique(cls, value: list[str]) -> list[str]:
            return list(dict.fromkeys(value))

    # ----- names -------------------------------------------------------------------------------

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """Every target, in the order the scene registers them."""
        names = ["title"] if params.title else []
        names += ["chart", "header", "labels"] + (["key"] if params.key else []) + (["source"] if params.source else [])
        names += ["caption"] if params.caption else []
        for c in pp.CELLS:
            names += [f"particle:{n}" for n in (c.target, *c.names)]
        names += [f"generation:{g}" for g in (1, 2, 3)]
        names += [f"group:{g}" for g in GROUP_TARGETS]
        names += [f"row:{r}" for r in pp.ROWS]
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """The on-screen name of a target (for the narration lint)."""
        kind, _, label = name.partition(":")
        if kind == "particle":
            c = pp.cell(label)
            return c.label[1 if params.antiparticles and c.is_fermion else 0]
        if kind == "group":
            return label.replace("_", " ")
        if kind == "generation":
            return f"generation {ROMAN[int(label) - 1]}"
        if kind == "row":
            return label.replace("_", " ")
        if name == "title":
            return params.title or None
        return None

    def arrangement(self) -> str:
        """``wide`` or ``tall``."""
        p = self.params
        return p.layout if p.layout != "auto" else ("tall" if self.is_portrait else "wide")

    def group_color(self, group: str) -> str:
        p = self.params
        if group == "quarks" and p.quark_color is None:
            return self.theme.palette_color(2)
        return self.theme.color(getattr(p, GROUP_COLORS[group]))

    # ----- building ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._arr = self.arrangement()
        area = self.safe_area
        self._title = None
        if p.title:
            self._title = chart_title(p.title, size=p.title_size, color=p.title_color, area=area)
            area = area.below(self._title, gap=0.3)
        self._caption = None
        if p.caption:
            self._caption = chart_caption(p.caption, area, color=p.caption_color)
            area = area.above(self._caption, gap=0.2)
        self._small = readable_size(margin=1.08)
        self._source = None
        if p.source and self._arr == "tall":
            self._source = chart_caption(source_note(), area, size=self._small, color=p.caption_color)
            area = area.above(self._source, gap=0.2)
        self._grid(area)
        self._fit_mode()
        self._cells ={c.target: self._build_cell(c) for c in pp.CELLS}
        self._labels = self._build_labels()
        self._header = self._build_header()
        self._key = self._build_key() if p.key else None
        if p.source and self._arr == "wide":
            region = self._note_region()
            self._source = fit_text(source_note(), region.width, region.height, size=self._small, color=p.caption_color, min_size=self._small)
            self._source.move_to(region.center).align_to(np.array([0, region.y1, 0]), UP)
        self._anti = {t for t, c in self._cells.items() if p.antiparticles and c["cell"].is_fermion}
        self._coupling_parts: list[Mobject] = []
        self._register()
        self.reveal(self._steps(), fraction=0.7, cap=1.0)
        self.finish()

    def _grid(self, area: Region) -> None:
        """Cell size and the centre of each (column, row) for the arrangement, fitted to ``area``."""
        cols, rows = pp.GRID[self._arr]
        label_w = self.text("H", size=self._small * 1.1).height * 1.45 + 0.18
        head_h = self.text("Hg", size=self._small).height + 0.3
        extra_x = BLOCK_GAP if self._arr == "wide" else 0.0
        extra_y = FAMILY_GAP + (BLOCK_GAP if self._arr == "tall" else 0.0)
        w = (area.width - label_w - (cols - 1) * CELL_GAP - extra_x) / cols
        h = (area.height - head_h - (rows - 1) * CELL_GAP - extra_y) / rows
        w, h = min(w, MAX_ASPECT * h), min(h, w)
        total_w = label_w + cols * w + (cols - 1) * CELL_GAP + extra_x
        total_h = head_h + rows * h + (rows - 1) * CELL_GAP + extra_y
        left = area.center[0] - total_w / 2 + label_w
        top = area.center[1] + total_h / 2 - head_h
        self._w, self._h, self._label_w, self._head_h = w, h, label_w, head_h

        def x_of(col: int) -> float:
            return left + col * (w + CELL_GAP) + (extra_x if self._arr == "wide" and col >= 3 else 0.0) + w / 2

        def y_of(row: int) -> float:
            shift = (FAMILY_GAP if row >= 2 else 0.0) + (BLOCK_GAP if self._arr == "tall" and row >= 4 else 0.0)
            return top - row * (h + CELL_GAP) - shift - h / 2

        self._x_of, self._y_of = x_of, y_of
        self._top, self._left = top, left

    def _pos(self, c: Any) -> np.ndarray:
        col, row = c.wide if self._arr == "wide" else c.tall
        return np.array([self._x_of(col), self._y_of(row), 0.0])

    def _key_pos(self) -> np.ndarray:
        col, row = (4, 3) if self._arr == "wide" else (2, 5)
        return np.array([self._x_of(col), self._y_of(row), 0.0])

    def _note_region(self) -> Region:
        """The free cells under the Higgs boson in the wide grid (rows 1–2 of column 4)."""
        x, w, h = self._x_of(4), self._w, self._h
        return Region(x - w / 2, self._y_of(2) - h / 2, x + w / 2, self._y_of(1) + h / 2)

    def _look(self, values: dict[str, Any], color: str, *, key: bool = False) -> dict[str, Mobject]:
        """The texts of one cell, placed about the origin on common baselines. Row mode (wide
        cells): ``mass`` top left, ``charge`` top right, ``spin`` right of the middle, the
        ``symbol`` in the middle, the ``name`` at the bottom. Column mode (the classic chart):
        ``mass``, ``charge`` and ``spin`` down the left, the symbol beside them."""
        w, h = self._w, self._h
        size = self._cell_size
        pad = self._pad()
        ink = "dim" if key else "text"
        shown = set(self.params.show) | ({"mass", "charge", "spin", "name"} if key else set())
        parts: dict[str, Mobject] = {k: self.text(values[k], size=size, color=ink) for k in ("mass", "charge", "spin") if k in shown}
        top, bottom = h / 2 - pad, -h / 2 + pad
        left, right = -w / 2 + pad, w / 2 - pad
        cap = self.text("H", size=size).height
        descent = 0.3 * cap
        pitch = cap * (1.35 if self._row_mode else COLUMN_PITCH)
        first = top - cap
        if "mass" in parts:
            _set(parts["mass"], first, left=left)
        if "name" in shown:
            label = values["name"]
            level = self._short_names[label.endswith("antineutrino")]
            if level and label in pp.SHORT_LABELS:
                label = pp.SHORT_LABELS[label][level - 1]
            name = self.text(label, size=size, color=ink)
            if name.width > w - 2 * pad:
                log.warning("scene '%s': the name '%s' is wider than its cell at the readable size; scaled down", self.spec.id, label)
                name.scale((w - 2 * pad) / name.width)
            _set(name, bottom + descent, centre=0.0)
            parts["name"] = name
            band_bottom = bottom + descent + cap + 0.03
        else:
            band_bottom = bottom
        band_top = first - descent - 0.02 if ("mass" in parts or (self._row_mode and "charge" in parts)) else top
        middle = (band_top + band_bottom) / 2
        if self._row_mode:
            if self._squeeze < 1:
                for k in ("mass", "charge"):
                    if k in parts:
                        parts[k].scale(self._squeeze, about_edge=LEFT)
            if "charge" in parts:
                _set(parts["charge"], first, right=right)
            if "spin" in parts:
                _set(parts["spin"], middle - cap / 2, right=right)
                right = parts["spin"].get_left()[0] - 0.1
        else:
            y = first - pitch
            for k in ("charge", "spin"):
                if k in parts:
                    _set(parts[k], y, left=left)
                    y -= pitch
            column = [parts[k] for k in ("charge", "spin") if k in parts]
            if column:   # the key's word "symbol" is wider than a symbol: it may come closer
                left = max(m.get_right()[0] for m in column) + (0.04 if key else 0.12)
                right += 0.8 * pad if key else 0.0
        if key:
            symbol: Mobject = self.text(values["symbol"], size=size, color=ink)
        else:
            symbol = VGroup(self.markup(values["symbol"], size=size * 3, color=color, weight=BOLD))
        # a cell whose antiparticle is barred keeps room for the bar in both looks (no jump)
        symbol_h = min(max(band_top - band_bottom - 0.04, cap), 0.55 * h) * (0.86 if values.get("bar_cell") else 1.0)
        if symbol.height > symbol_h:
            symbol.scale(symbol_h / symbol.height)
        if symbol.width > right - left:
            symbol.scale((right - left) / symbol.width)
        if not key:
            # every symbol carries its bar (invisible without one), so turning a cell into its
            # antiparticle morphs bar into bar and letters into letters
            glyph = symbol[0][0]
            lift = 0.14 * glyph.height
            bar = Line(glyph.get_corner(UL) + UP * lift, glyph.get_corner(UR) + UP * lift)
            symbol.add(bar.set_stroke(color, width=max(2.0, 0.1 * glyph.height * 100), opacity=1.0 if values.get("bar") else 0.0))
        cx = min(max(0.0, left + symbol.width / 2), right - symbol.width / 2)
        symbol.move_to(np.array([cx, middle, 0]))
        parts["symbol"] = symbol
        return parts

    def _fit_mode(self) -> None:
        """Whether every cell's mass and charge fit on one line (``row`` mode, the wide grid),
        else the classic column; and whether the long neutrino names need their short form
        (decided for all cells, so the chart looks the same everywhere)."""
        w, size = self._w, self._small
        pad = self._pad()
        room = w - 2 * pad
        widths: dict[str, float] = {}

        def width(text: str) -> float:   # at the readable size
            if text not in widths:
                widths[text] = self.text(text, size=size).width
            return widths[text]

        need = max(width(c.mass_text()) + max(width(c.charge_text(False)), width(c.charge_text(True))) for c in pp.CELLS) + 0.12
        cap = self.text("H", size=size).height
        # the column: mass, charge and spin lines over the name (their ascenders and descenders included)
        column_fits = self._h - 2 * pad >= (2.6 + 2 * COLUMN_PITCH) * cap + 0.03
        self._row_mode = need <= room or not column_fits
        #: a top line squeezed to fit a cell too small for either arrangement (1: none)
        self._squeeze = min(1.0, room / need) if self._row_mode else 1.0
        if self._squeeze < 1:
            log.warning("scene '%s': the chart's cells are too small for the mass and charge at the readable size; scaled to %.0f %% "
                        "(fewer fields with show:, or another layout, helps)", self.spec.id, 100 * self._squeeze)
        # roomy wide cells take their texts up to 25 % above the readable size (three lines and
        # a symbol of two still fit the height)
        grow = min(1.25, room / need, (self._h - 2 * pad) / (cap * 5.6)) if self._row_mode else 1.0
        scale = max(1.0, grow)
        self._cell_size = size * scale
        #: per state (particle, antiparticle) 0: the full names; 1, 2: the shorter forms of SHORT_LABELS
        self._short_names = {}
        for anti in (False, True):
            labels = [c.label[anti] for c in pp.CELLS if c.label[anti] in pp.SHORT_LABELS]
            levels = [labels] + [[pp.SHORT_LABELS[label][i] for label in labels] for i in range(2)]
            self._short_names[anti] = next((i for i, names in enumerate(levels) if all(width(n) * scale <= room for n in names)), 2)

    def _pad(self) -> float:
        """The space inside a cell's outline."""
        return min(0.08, 0.06 * min(self._w, self._h)) + 0.02

    def _values(self, c: Any, anti: bool) -> dict[str, Any]:
        return {"mass": c.mass_text(), "charge": c.charge_text(anti), "spin": c.spin_text(),
                "name": c.label[1 if anti else 0], "symbol": c.symbol[1 if anti else 0], "bar": anti and c.bar, "bar_cell": c.bar}

    def _build_cell(self, c: Any) -> dict[str, Any]:
        color = self.group_color(c.group)
        box = RoundedRectangle(width=self._w, height=self._h, corner_radius=min(0.12, 0.1 * self._h))
        box.set_stroke(color, width=3, opacity=0.9).set_fill(color, opacity=CELL_FILL)
        looks = {False: self._look(self._values(c, False), color), True: self._look(self._values(c, True), color)}
        start = looks[self.params.antiparticles and c.is_fermion]
        shown = {k: m.copy() for k, m in start.items()}
        group = VGroup(box, *shown.values())
        centre = self._pos(c)
        group.shift(centre)
        for look in looks.values():
            for m in look.values():
                m.shift(centre)
        return {"cell": c, "box": box, "shown": shown, "looks": looks, "group": group}

    def _build_labels(self) -> dict[str, Mobject]:
        """Group names left of the rows (rotated): quarks, leptons and, tall, bosons."""
        labels: dict[str, Mobject] = {}
        spans = {"quarks": (0, 1), "leptons": (2, 3)} | ({"gauge_bosons": (4, 5)} if self._arr == "tall" else {})
        for group, (r0, r1) in spans.items():
            word = {"gauge_bosons": "bosons"}.get(group, group)
            anti = self.params.antiparticles and group != "gauge_bosons"
            label = self._label_text(("anti" if anti else "") + word, group)
            label.move_to(np.array([self._left - self._label_w / 2 - 0.02, (self._y_of(r0) + self._y_of(r1)) / 2, 0]))
            labels[group] = label
        return labels

    def _label_text(self, word: str, group: str) -> Mobject:
        label = self.text(word, size=self._small * 1.1, color=self.group_color(group), weight=BOLD)
        label.rotate(PI / 2)
        return label

    def _build_header(self) -> dict[str, Mobject]:
        """Generation numbers over the fermion columns; wide: the boson columns' names."""
        y = self._top + self._head_h / 2
        header: dict[str, Mobject] = {}
        for g, numeral in enumerate(ROMAN):
            header[f"generation:{g + 1}"] = self.text(numeral, size=self._small, color="dim", weight=BOLD).move_to(np.array([self._x_of(g), y, 0]))
        if self._arr == "wide":
            for col, group, text in ((3, "gauge_bosons", "gauge bosons"), (4, "scalar_bosons", "scalar boson")):
                label = self.text(text, size=self._small, color=self.group_color(group), weight=BOLD)
                if label.width > self._w:
                    label.scale(self._w / label.width)
                header[group] = label.move_to(np.array([self._x_of(col), y, 0]))
        return header

    def _build_key(self) -> Mobject:
        box = RoundedRectangle(width=self._w, height=self._h, corner_radius=min(0.12, 0.1 * self._h))
        box.set_stroke(self.theme.color("dim"), width=2, opacity=0.8)
        box = DashedVMobject(box, num_dashes=40)
        parts = self._look({"mass": "mass", "charge": "charge", "spin": "spin", "name": "name", "symbol": "symbol"}, "dim", key=True)
        key = VGroup(box, *parts.values())
        return key.shift(self._key_pos())

    # ----- targets and steps -------------------------------------------------------------------

    def _enter(self, parts: list[Mobject]) -> Any:
        def entrance() -> list[Animation]:
            return [FadeIn(m, shift=UP * 0.06) for m in parts if not self.on_screen_parts(m)]

        return entrance

    def _cells_of(self, test: Any) -> list[dict[str, Any]]:
        return [v for v in self._cells.values() if test(v["cell"])]

    def _register(self) -> None:
        if self._title is not None:
            self.target("title", self._title, entrance=lambda: [FadeIn(self._title, shift=DOWN * 0.15)])
        everything = [v["group"] for v in self._cells.values()] + list(self._labels.values()) + list(self._header.values())
        everything += [self._key] if self._key is not None else []
        self.target("chart", VGroup(*everything), entrance=self._enter(everything))
        heads = list(self._header.values())
        self.target("header", VGroup(*heads), entrance=self._enter(heads))
        labels = list(self._labels.values())
        self.target("labels", VGroup(*labels), entrance=self._enter(labels))
        if self._key is not None:
            self.target("key", self._key, entrance=self._enter([self._key]))
        if self._source is not None:
            self.target("source", self._source, entrance=self._enter([self._source]))
        if self._caption is not None:
            self.target("caption", self._caption, entrance=self._enter([self._caption]))
        for c in pp.CELLS:
            v = self._cells[c.target]
            self.target([f"particle:{n}" for n in (c.target, *c.names)], v["group"], outline=v["box"], entrance=self._enter([v["group"]]))
        for g in (1, 2, 3):
            parts = [v["group"] for v in self._cells_of(lambda c, g=g: c.generation == g)] + [self._header[f"generation:{g}"]]
            self.target(f"generation:{g}", VGroup(*parts), entrance=self._enter(parts))
        members = {
            "quarks": lambda c: c.group == "quarks", "leptons": lambda c: c.group == "leptons", "fermions": lambda c: c.is_fermion,
            "gauge_bosons": lambda c: c.group == "gauge_bosons", "scalar_bosons": lambda c: c.group == "scalar_bosons",
            "bosons": lambda c: not c.is_fermion,
        }
        for name in GROUP_TARGETS:
            parts = [v["group"] for v in self._cells_of(members[name])] + self._group_labels(name)
            self.target(f"group:{name}", VGroup(*parts), entrance=self._enter(parts))
        for row in pp.ROWS:
            parts = [v["group"] for v in self._cells_of(lambda c, row=row: c.row == row)]
            self.target(f"row:{row}", VGroup(*parts), entrance=self._enter(parts))

    def _group_labels(self, name: str) -> list[Mobject]:
        """The labels and headers that name a group (its target includes them)."""
        wanted = {"fermions": ("quarks", "leptons"), "bosons": ("gauge_bosons", "scalar_bosons")}.get(name, (name,))
        found = [self._labels[g] for g in wanted if g in self._labels] + [self._header[g] for g in wanted if g in self._header]
        return found

    def _steps(self) -> list[Any]:
        frame = ([self._title] if self._title is not None else []) + [self._header[f"generation:{g}"] for g in (1, 2, 3)]

        def group(name: str, extra: list[Mobject]) -> list[Mobject]:
            return [v["group"] for v in self._cells_of(lambda c: c.group == name)] + self._group_labels(name) + extra

        tail = ([self._key] if self._key is not None else []) + ([self._source] if self._source is not None else [])
        tail += [self._caption] if self._caption is not None else []
        if self.params.reveal == "all":
            everything = frame + group("quarks", []) + group("leptons", []) + group("gauge_bosons", []) + group("scalar_bosons", []) + tail
            return [lambda: self._lagged(everything)]
        parts = [frame + group("quarks", []), group("leptons", []), group("gauge_bosons", []), group("scalar_bosons", tail)]
        return [lambda ms=ms: self._lagged(ms) for ms in parts]

    def _lagged(self, mobs: list[Mobject]) -> list[Animation]:
        anims = self._enter(mobs)()
        return [LaggedStart(*anims, lag_ratio=0.06)] if anims else []

    # ----- the actions' drawing ----------------------------------------------------------------

    def fermion_cells(self, targets: list[Any]) -> list[str]:
        """Targets of the fermion cells inside ``targets`` (all fermions when empty)."""
        if not targets:
            return [t for t, v in self._cells.items() if v["cell"].is_fermion]
        family = {id(m) for t in targets for m in t.mobject.get_family()}
        return [t for t, v in self._cells.items() if v["cell"].is_fermion and id(v["group"]) in family]

    def flip(self, cells: list[str], anti: bool) -> list[Animation]:
        """Animations turning ``cells`` into their antiparticles (``anti``) or back; the group
        labels follow when all of a group's cells have turned."""
        anims: list[Animation] = []
        for t in cells:
            v = self._cells[t]
            if (t in self._anti) == anti:
                continue
            for k, m in v["shown"].items():
                target = v["looks"][anti][k]
                if self._text_of(m) != self._text_of(target) or k == "symbol":
                    anims.append(Transform(m, target.copy()))
            (self._anti.add if anti else self._anti.discard)(t)
        for group, word in (("quarks", "quarks"), ("leptons", "leptons")):
            label = self._labels.get(group)
            if label is None:
                continue
            all_anti = all(t in self._anti for t, v in self._cells.items() if v["cell"].group == group)
            text = ("anti" if all_anti else "") + word
            if getattr(label, "_word", group) != text:
                new = self._label_text(text, group).move_to(label)
                anims.append(Transform(label, new))
                label._word = text  # type: ignore[attr-defined]
        return anims

    @staticmethod
    def _text_of(m: Mobject) -> str:
        return getattr(m, "original_text", getattr(m, "text", ""))

    def couple(self, bosons: list[str], color: str, dim: bool, note: bool) -> tuple[list[Animation], dict[str, Any]]:
        """Outline the particles the bosons couple to, ring the boson cells, dim the rest and
        say why; returns the animations and what :meth:`uncouple` needs."""
        coupled: set[str] = set()
        outlines: list[Mobject] = []
        reasons = []
        for b in bosons:
            coupling = pp.COUPLINGS[b]
            coupled |= {b, *coupling.fermions, *coupling.bosons}
            fermions = [self._cells[t]["box"] for t in coupling.fermions]
            block = SurroundingRectangle(VGroup(*fermions), buff=0.07, corner_radius=0.14, stroke_width=6).set_stroke(color)
            outlines.append(block)
            for t in coupling.bosons:
                ring = SurroundingRectangle(self._cells[t]["box"], buff=0.05, corner_radius=0.12, stroke_width=4).set_stroke(color)
                outlines.append(DashedVMobject(ring, num_dashes=28) if t != b else ring)
            if b not in coupling.bosons:
                outlines.append(SurroundingRectangle(self._cells[b]["box"], buff=0.05, corner_radius=0.12, stroke_width=6).set_stroke(color))
            symbol = pp.cell(b).symbol[0]
            reasons.append(f"{_plain(symbol)} couples to {coupling.reason}")
        anims: list[Animation] = [Create(o) for o in outlines]
        state: dict[str, Any] = {"outlines": outlines, "saved": {}, "note": None}
        if dim:
            for t, v in self._cells.items():
                if t in coupled:
                    continue
                group = v["group"]
                state["saved"][t] = {id(m): (m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in group.get_family() if isinstance(m, VMobject)}
                found = self.find_targets(f"particle:{t}")
                if found:
                    anims.append(dim_to(found[0], group, COUPLING_DIM, own=False))
        if note:
            text = "; ".join(reasons)
            region = self._note_region() if self._arr == "wide" else None
            if region is not None:
                shown = fit_text(text, region.width, region.height, size=self._small, color="text", min_size=self._small)
                shown.move_to(region.center).align_to(np.array([0, region.y1, 0]), UP)
            else:
                bottom = (self._source or self._caption)
                width = self.safe_area.width
                shown = fit_text(text, width, 1.2, size=self._small, color="text", min_size=self._small)
                y = bottom.get_y() if bottom is not None else self._y_of(5) - self._h / 2 - 0.5
                shown.move_to(np.array([0, y, 0]))
            hide = [m for m in (self._source,) if m is not None and self.on_screen_parts(m)]
            if self._arr == "tall" and self._caption is not None and self.on_screen_parts(self._caption) and self._source is None:
                hide.append(self._caption)
            state["note"], state["hidden"] = shown, hide
            anims += [FadeOut(m) for m in hide] + [FadeIn(shown)]
        self._coupling_parts += outlines
        return anims, state

    def uncouple(self, state: dict[str, Any]) -> list[Animation]:
        """Undo :meth:`couple`."""
        anims: list[Animation] = [FadeOut(o) for o in state["outlines"] if o in self.mobjects]
        for t, saved in state["saved"].items():
            def paint(m: Any, fill: Any, stroke: Any, saved: dict[int, Any] = saved) -> Any:
                return saved.get(id(m), (fill, stroke))

            anims.append(Repaint(self._cells[t]["group"], paint))
        if state.get("note") is not None:
            anims.append(FadeOut(state["note"]))
            anims += [FadeIn(m) for m in state.get("hidden", [])]
        return anims


def _plain(markup: str) -> str:
    """Pango markup without its tags (``e<sup>+</sup>`` -> ``e+``)."""
    import re

    return re.sub(r"<[^>]+>", "", markup)


def _baseline(text: Mobject) -> float:
    """The baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in text.submobjects if g.has_points()] or [text]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))


def _set(text: Mobject, baseline: float, *, left: float | None = None, right: float | None = None, centre: float | None = None) -> Mobject:
    """Put a line of text on ``baseline``, its left or right edge or its centre at ``x``."""
    text.shift(UP * (baseline - _baseline(text)))
    if left is not None:
        text.shift(RIGHT * (left - text.get_left()[0]))
    elif right is not None:
        text.shift(RIGHT * (right - text.get_right()[0]))
    elif centre is not None:
        text.set_x(centre)
    return text
