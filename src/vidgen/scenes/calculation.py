"""``calculation``: worked calculations with units (Phase W, DESIGN §97.9). A symbol table
(symbol, value with unit, meaning, source) and a chain of calculations, each shown step by
step: the formula, the values substituted with their units, an intermediate value, the result
with its significant figures (an exact fraction and its decimal when every input is exact), and
the result converted into other units. The arithmetic, units and significant figures are in
``vidgen.quantities`` (no manim); the actions ``substitute``, ``compute`` and ``convert`` are in
``calculation_actions.py``.

Needs LaTeX, like ``equation``.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .equation_derivation import term_key, tex_error_excerpt

log = logging.getLogger("vidgen.scenes.calculation")

_OPEN = r"\special{dvisvgm:raw <g id='%s'>}"
_CLOSE = r"\special{dvisvgm:raw </g>}"
_SPECIAL = re.compile(r"\\special\{dvisvgm:raw [^}]*\}")
#: The kinds of a calculation's steps, in order, and the target name of those that have one
#: (an intermediate comes with its result).
KINDS = ("formula", "substitute", "intermediate", "result", "convert")
TARGET_NAME = {"formula": "formula", "substitute": "substitution", "result": "result", "convert": "conversion"}
#: The step each action plays (with the steps before it that are not on screen yet).
ACTION_STEP = {"substitute": "substitute", "compute": "result", "convert": "convert"}
#: Actions whose targets the scene's own steps leave to them.
TIMED = ("reveal", "substitute", "compute", "convert")
#: A long substitution is written the most explicit way (with units, on one line) that is at
#: least :data:`NEARLY` as large as the largest way (units on two lines, SI numbers without
#: units...), or :data:`LARGE` times the readable size.
NEARLY, LARGE = 0.8, 2.0
ROW_GAP, BOX_PAD, TABLE_GAP = 0.34, 0.14, 0.22


class CalcSymbol(SceneParams):
    """A row of the symbol table: ``{name, value, unit, meaning, source}``, or ``{name,
    constant}``, or ``{name, from_scene}``."""

    name: str
    """The name formulas use (v, M_sun, t_half, lambda): letters, digits and _."""
    value: str | int | float | None = None
    """The value: 29.8, '6.674e-11', '2.5 × 10^3', a fraction '1/25', optionally with its unit ('29.8 km/s'); write a string to keep trailing zeros ('1.50')."""
    unit: str = ""
    """Its unit (m/s^2, km h^-1, GeV/c^2, µM, °C), if not written after the value; for a constant, the unit to show it in."""
    constant: str | None = None
    """A named constant instead of a value: c, G, h, hbar, k_B, N_A, e, R, sigma_SB, m_e, m_p, m_u, epsilon_0, mu_0, g, AU, GM_sun, GM_earth, M_sun, M_earth, R_earth."""
    from_scene: str | None = None
    """The result of a calculation scene of this video instead of a value: 'scene_id' (the result with this name) or 'scene_id.result'."""
    sig: int | None = None
    """Significant figures of the value (it is rounded to them); default: counted from its digits (decimals), exact for fractions and whole numbers without a unit."""
    exact: bool | None = None
    """true: an exact value (a count, a defined quantity) that never limits the result's significant figures."""
    digits: int | None = None
    """Significant figures to show it with (its full value is used); default: as written, constants with 4."""
    tex: str = ""
    """TeX of its symbol; default from the name (M_sun -> M_⊙, k_B -> k_B, lambda -> λ, t_half -> t_1/2) or the constant's."""
    meaning: TranslatableStr = ""
    """What it is ('distance from the Sun'), shown under it in the table; a constant's meaning by default."""
    source: str = ""
    """Where the value comes from ('NIST', 'measured'), shown after the meaning; a constant's source by default."""
    color: ThemeColor | None = None
    """Colour of the symbol in the table and in formulas; default: its concept colour (terms: with tex), else the formula colour."""
    show: bool = True
    """false: used in formulas but not listed in the table."""

    @model_validator(mode="after")
    def _one_source(self) -> "CalcSymbol":
        given = [k for k in ("value", "constant", "from_scene") if getattr(self, k) is not None]
        if len(given) != 1:
            raise ValueError(f"symbol '{self.name}': give exactly one of value, constant or from_scene" + (f" (got {', '.join(given)})" if given else
                             " (value: 29.8 km/s, constant: G, from_scene: scene_id)"))
        return self


class CalcStep(SceneParams):
    """A calculation: ``{name, expr, unit, convert, sig, ...}``."""

    name: str
    """Name of the result (later calculations, and other scenes with from_scene, use it)."""
    expr: str
    """The formula as an expression of the symbols: sqrt(G*M_sun/r), 2*p*q, ln(2)/k, h*c/lambda; numbers in it are exact, a unit in brackets: 9.81 [m/s^2]."""
    meaning: TranslatableStr = ""
    """What the result is ('orbital speed'), shown with it in the table."""
    unit: str = ""
    """Unit of the result (km/s, eV, h); default: SI, a named unit where one fits (kg·m²·s⁻² -> J)."""
    convert: str | list[str] = []
    """Units to convert the result into, shown as a last step (km/s, [eV, J])."""
    sig: int | None = None
    """Significant figures of the result; default: from the inputs (products: the fewest; sums: the coarsest decimal place)."""
    format: Literal["auto", "decimal", "sci", "fraction", "percent"] = "auto"
    """How the result is written: auto (an exact fraction as a fraction and its decimal, else decimals or scientific notation), decimal, sci, fraction, percent."""
    tex: str = ""
    """TeX of the formula's right side, if the one written from expr is not wanted (the substitution is still built from expr)."""
    symbol: str = ""
    """TeX of the result's symbol; default from the name."""
    substitute: bool = True
    """Show the values substituted into the formula."""
    intermediate: bool | None = None
    """Show the argument of an outer square root or power evaluated (default: when it helps)."""
    units: Literal["auto", "always", "never"] = "auto"
    """Units in the substitution: always, never (values in SI), auto (with units unless that makes the line too small)."""

    def converts(self) -> list[str]:
        return [self.convert] if isinstance(self.convert, str) else list(self.convert)


def _inputs(p: Any, imports: dict[str, Any] | None = None) -> tuple[list[Any], list[Any]]:
    """The symbols and calculations as ``quantities`` inputs."""
    symbols = [quantities.SymbolInput(s.name, s.value, s.unit, s.constant, s.sig, s.exact, s.tex, str(s.meaning), s.source, s.digits,
                                      (imports or {}).get(s.name)) for s in p.symbols]
    calcs = [quantities.CalcInput(c.name, c.expr, c.unit, c.converts(), c.sig, c.format, c.tex, str(c.meaning), c.symbol, c.intermediate, c.substitute)
             for c in p.calculations]
    return symbols, calcs


def _scene_ref(text: str) -> tuple[str, str | None]:
    scene_id, _, result = text.partition(".")
    return scene_id.strip(), (result.strip() or None)


def resolve_imports(params: Any, project: Any, seen: tuple[str, ...] = ()) -> dict[str, Any]:
    """The values of the symbols taken from other scenes (``from_scene``): ``{name: (quantity,
    unit, number, tex)}``, computing those scenes' calculations (refusing a loop)."""
    out: dict[str, Any] = {}
    for k, s in enumerate(params.symbols, start=1):
        if s.from_scene is None:
            continue
        scene_id, result = _scene_ref(s.from_scene)
        result = result or s.name
        where = f"symbols[{k}] ({s.name}): from_scene '{s.from_scene}'"
        specs = {spec.id: spec for spec in project.config.scenes}
        spec = specs.get(scene_id)
        if spec is None or spec.type != "calculation":
            calcs = [i for i, sp in specs.items() if sp.type == "calculation"]
            raise VidgenError(f"{where}: no calculation scene '{scene_id}'" + (f"; calculation scenes: {', '.join(calcs)}" if calcs else "")
                              + did_you_mean(scene_id, calcs))
        if scene_id in seen:
            raise VidgenError(f"{where}: the scenes {' -> '.join((*seen, scene_id))} take values from each other in a loop")
        other = Calculation.parse_params(spec.params, spec.id)
        worked = quantities.work(*_inputs(other, resolve_imports(other, project, (*seen, scene_id))))
        names = [r.name for r in worked.results]
        if result not in names:
            raise VidgenError(f"{where}: scene '{scene_id}' computes {', '.join(names)}, not '{result}'" + did_you_mean(result, names))
        v = worked.results[names.index(result)].value
        out[s.name] = (v.quantity, v.unit, v.number, v.tex)
    return out


@dataclass
class _Row:
    """A line of a worked calculation on screen: its step kind, formula and the x of its
    relation sign (for alignment)."""

    kind: str
    tex: MathTex
    rel_x: float = 0.0
    box: Mobject | None = None

    @property
    def mobject(self) -> Mobject:
        return VGroup(self.tex, self.box) if self.box is not None else self.tex


@dataclass
class _Calc:
    rows: list[_Row]
    table_row: Mobject | None = None
    targets: dict[str, Any] = field(default_factory=dict)


@scene("calculation")
class Calculation(NarratedScene):
    """A worked calculation with units: the symbol table (beside the work in 16:9, above it in
    9:16), then each calculation step by step — formula, values substituted with units, an
    intermediate value, the result with its significant figures (exact fractions when every
    input is exact), conversions — one calculation per beat (more beats: its steps spread over
    them). Each result joins the table, and later calculations (and other scenes, with
    ``from_scene``) can use it by name. The actions ``substitute``, ``compute`` and ``convert``
    (and ``reveal`` for a formula) time the steps to words; ``highlight`` marks a symbol.

    Action targets: ``title``, ``table``, ``symbol:<name>`` (the symbol in the table and in the
    formulas on screen), ``row:<name>`` (its table row), ``calc<N>`` / ``calc:<name>`` (a whole
    calculation), ``formula<N>``, ``substitution<N>``, ``result<N>`` / ``result:<name>``,
    ``conversion<N>``.
    """

    outro = 0.5
    calculation_actions = True
    target_patterns = ("title", "table", "symbol:<name>", "row:<name>", "calc<N>", "calc:<name>", "formula<N>", "substitution<N>",
                       "result<N>", "result:<name>", "conversion<N>")
    #: Formulas in a vertical frame may grow by this factor (they are still fitted to the width).
    portrait_growth = 1.15

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Heading above the calculation."""
        symbols: list[CalcSymbol] = []
        """The symbol table: [{name, value, unit, meaning, source}, {name: G, constant: G}, {name: v, from_scene: orbit}]."""
        calculations: list[CalcStep] = Field(min_length=1)
        """The calculations, in order: [{name, expr, unit, convert, sig, meaning}]; a later one may use an earlier result's name."""
        table: Literal["auto", "side", "top", "none"] = "auto"
        """Where the symbol table goes: auto (beside the work in 16:9, above it in a vertical frame), side, top, none."""
        results_in_table: bool = True
        """Add each result to the table when the next calculation starts."""
        size: ThemeSize = 72
        """Formula size (the largest; smaller to fit, not below the readable size)."""
        table_size: ThemeSize = 40
        """Size of the table's symbols and values (1.15x in a vertical frame)."""
        color: ThemeColor = "text"
        """Formula colour."""
        result_color: ThemeColor = "highlight"
        """Colour of the box around each result."""
        meaning_color: ThemeColor = "dim"
        """Colour of the meanings and sources in the table."""
        caption: TranslatableStr = ""
        """Note under the calculation."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""

        @model_validator(mode="after")
        def _work(self) -> "Calculation.Params":
            for k, s in enumerate(self.symbols, start=1):
                if s.from_scene is not None:
                    scene_id, result = _scene_ref(s.from_scene)
                    if not scene_id:
                        raise ValueError(f"symbols[{k}] ({s.name}): from_scene names a scene: 'scene_id' or 'scene_id.result'")
            try:
                self.worked(None, lenient=True)
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

        def worked(self, project: Any = None, *, lenient: bool = False, wrap: Any = None) -> Any:
            """The worked calculations (``quantities.Worked``); symbols from other scenes are
            resolved with ``project`` (without one and ``lenient``, calculations needing them
            are skipped)."""
            imports = resolve_imports(self, project) if project is not None else {}
            return quantities.work(*_inputs(self, imports), wrap=wrap, lenient=lenient)

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title``, ``table``, ``symbol:`` / ``row:`` per symbol and result, ``calc``,
        ``formula``, ``substitution``, ``result``, ``conversion`` per calculation."""
        names = (["title"] if params.title else []) + (["table"] if params.table != "none" else [])
        for s in params.symbols:
            names += [f"symbol:{s.name}"] + ([f"row:{s.name}"] if s.show and params.table != "none" else [])
        for k, c in enumerate(params.calculations, start=1):
            names += [f"calc{k}", f"calc:{c.name}", f"formula{k}"] + ([f"substitution{k}"] if c.substitute else [])
            names += [f"result{k}", f"result:{c.name}"] + ([f"conversion{k}"] if c.converts() else []) + [f"symbol:{c.name}"]
            if params.results_in_table and params.table != "none" and k < len(params.calculations):
                names.append(f"row:{c.name}")
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """What a target is called on screen (for the narration lint): a table row's note
        (meaning · source) for ``row:`` / ``symbol:``, the title; formulas are math, not text."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        if kind not in ("row", "symbol") or not key:
            return None
        worked = params.worked(None, lenient=True)
        try:
            v = worked.value(key)
        except KeyError:
            return None
        return " · ".join(x for x in (str(v.meaning), v.source) if x) or None

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        if not latex_available():
            log.warning("calculation scenes need LaTeX, which was not found on PATH; rendering them will fail")
        problems = super().validate_project(params, project)
        if any(s.from_scene for s in params.symbols):
            try:
                params.worked(project)
            except VidgenError as error:
                problems.append(str(error))
        return problems

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        require_latex(f"scene '{self.spec.id}' (type calculation)")
        self._groups: dict[str, str] = {}
        worked = p.worked(self.project, wrap=self._wrap)
        self.worked = worked
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)
            body = body.below(title, gap=0.4)
        caption = None
        if p.caption:
            caption = chart_caption(p.caption, body, size=p.caption_size, color=p.caption_color)
            body = body.above(caption, gap=0.3)
        mode = p.table if p.table != "auto" else ("top" if self.is_portrait else "side")
        listed = [s for s in p.symbols if s.show]
        results = [r for r in worked.results[:-1]] if p.results_in_table else []
        self._colors = self._symbol_colors()
        self._table: VGroup | None = None
        self._rows_by_name: dict[str, VGroup] = {}
        work_area = body
        if mode != "none" and (listed or results):
            if mode == "side":
                work_area, table_area = body.columns([0.6, 0.4], gap=0.5)
                self._table, self._rows_by_name = self._build_table(table_area.width, listed, results)
            else:   # above the work, as tall as it needs, up to half the body
                self._table, self._rows_by_name = self._build_table(body.width, listed, results)
                share = min(0.5, (self._table.height + 0.1) / body.height)
                table_area, work_area = body.rows([share, 1 - share], gap=0.45)
            self._place_table(self._table, table_area)
        self._calcs = [self._build_calc(k, r, work_area) for k, r in enumerate(worked.results)]
        self._register(title, caption)
        self._play()

    # ----- TeX ---------------------------------------------------------------------------------

    def _wrap(self, key: str, tex: str) -> str:
        """``tex`` in a dvisvgm group remembered as an occurrence of symbol ``key``."""
        gid = f"vgcalc{len(self._groups):04d}"
        self._groups[gid] = key
        return _OPEN % gid + tex + _CLOSE

    def _symbol_colors(self) -> dict[str, str]:
        """Symbol name -> colour: its own ``color``, else the concept colour whose TeX is the
        symbol's (``terms:`` with ``tex``)."""
        out: dict[str, str] = {}
        concepts = {term_key(part): term.color for term in active_terms() for part in term.tex}
        for name, value in self.worked.symbols.items():
            if term_key(value.tex) in concepts:
                out[name] = concepts[term_key(value.tex)]
        for r in self.worked.results:
            if term_key(r.value.tex) in concepts:
                out[r.name] = concepts[term_key(r.value.tex)]
        for s in self.params.symbols:
            if s.color is not None:
                out[s.name] = resolve_color(s.color, self.theme)
        return out

    def _math(self, tex: str, size: float, where: str) -> MathTex:
        """``tex`` typeset; symbol occurrences found by group (``symbol_parts``) and coloured."""
        try:
            m = MathTex(tex, font_size=size, color=resolve_color(self.params.color, self.theme))
        except Exception as exc:  # Manim raises plain exceptions for LaTeX errors
            raise VidgenError(f"scene '{self.spec.id}': {where} does not compile: {tex_error_excerpt(exc)}") from None
        m.symbol_parts = []
        for gid, group in m.id_to_vgroup_dict.items():
            key = self._groups.get(gid)
            if key is None or not group.family_members_with_points():
                continue
            m.symbol_parts.append((key, group))
            if key in self._colors:
                group.set_color(self._colors[key])
        m.tex_string = _SPECIAL.sub("", tex).strip()   # what the layout dump and lint show
        return m

    @staticmethod
    def _glyph(m: Mobject) -> float:
        heights = [x.height for x in m.family_members_with_points() if x.height > 1e-3]
        return float(np.percentile(heights, 75)) if heights else 1.0

    def _floor(self) -> float:
        return Text("H", font=self.theme.font, font_size=readable_size()).height * 1.04

    # ----- table -------------------------------------------------------------------------------

    def _table_line(self, value: Any, size: float) -> MathTex:
        tex, _ = value.value_tex()
        rel = r"\approx" if value.number.approx and value.quantity.sig is None else "="
        return self._math(self._wrap(value.name, "{" + value.tex + "}") + f" {rel} " + tex, size, f"the table row of '{value.name}'")

    def _build_table(self, width: float, listed: list[Any], results: list[Any]) -> tuple[VGroup, dict[str, VGroup]]:
        """The table's rows (``symbol = value unit`` over its meaning and source), stacked
        (two columns in a vertical frame when they fit), at their full size."""
        p = self.params
        size = float(self.theme.size(p.table_size)) * (self.portrait_growth if self.is_portrait else 1.0)
        entries: list[tuple[str, MathTex, str]] = []
        for s in listed:
            v = self.worked.symbols.get(s.name)
            if v is None:
                continue
            note = " · ".join(x for x in (v.meaning, v.source) if x)
            entries.append((s.name, self._table_line(v, size), note))
        for r in results:
            entries.append((r.name, self._table_line(r.value, size), r.value.meaning))
        rows: dict[str, VGroup] = {}
        self._table_lines = [line for _, line, _ in entries]
        for name, line, note in entries:
            if line.width > width:
                line.scale(width / line.width)
            parts: list[Mobject] = [line]
            if note:
                parts.append(readable_text(note, Region(0, 0, width, 1.2), size="caption", color=p.meaning_color, align="left"))
            rows[name] = VGroup(*parts).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        table = VGroup(*rows.values()).arrange(DOWN, buff=TABLE_GAP, aligned_edge=LEFT)
        if self.is_portrait and len(rows) > 3 and width > 2 * max(r.width for r in rows.values()) + 0.4:
            half = (len(rows) + 1) // 2
            items = list(rows.values())
            cols = [VGroup(*items[:half]).arrange(DOWN, buff=TABLE_GAP, aligned_edge=LEFT),
                    VGroup(*items[half:]).arrange(DOWN, buff=TABLE_GAP, aligned_edge=LEFT)]
            table = VGroup(*cols).arrange(RIGHT, buff=0.5, aligned_edge=UP)
        return table, rows

    def _place_table(self, table: VGroup, area: Region) -> None:
        """Fit the table into ``area`` (warning when that takes it below the readable size),
        at the area's top; left-aligned beside the work, centred above it."""
        scale = min(1.0, area.width / max(table.width, 1e-6), area.height / max(table.height, 1e-6))
        if scale < 1.0:
            table.scale(scale)
        glyph = min((self._glyph(line) for line in self._table_lines), default=1.0)
        if glyph < self._floor() * 0.98:
            log.warning("scene '%s': the symbol table is set below the readable size to fit; list fewer symbols (show: false), shorten "
                        "the meanings or set table_size", self.spec.id)
        table.move_to(area.center).align_to(np.array([0, area.y1, 0]), UP)
        if not self.is_portrait:
            table.align_to(np.array([area.x0, 0, 0]), LEFT)

    # ----- the steps of a calculation ----------------------------------------------------------

    @staticmethod
    def _row_tex(relation: str, tex: str, lhs: str) -> str:
        """A line: the left side (the first line only), the relation (a group, for alignment),
        the right side."""
        return f"{lhs} {_OPEN % 'vgrel'}{relation}{_CLOSE} {tex}"

    def _build_calc(self, k: int, r: Any, area: Region) -> _Calc:
        p = self.params
        spec = p.calculations[k]
        size = float(self.theme.size(p.size)) * (self.portrait_growth if self.is_portrait else 1.0)
        lhs = self._wrap(r.name, "{" + r.value.tex + "}")
        floor = self._floor()

        room_w = area.width - 2 * BOX_PAD - 0.1
        rows: list[_Row] = []
        smallest = float("inf")
        for j, step in enumerate(r.steps):
            options = [step.tex]
            if step.kind == "substitute":
                options = {"auto": step.variants(), "always": [t for t in (step.tex, step.stacked) if t],
                           "never": [t for t in (step.alt, step.alt_stacked) if t]}[spec.units] or [step.tex]
            where = f"calculations[{k + 1}] ({r.name}), the {step.kind} line"
            built = []
            for tex in options:   # sizes relative to the readable size, at the width's scale
                m = self._math(self._row_tex(step.relation, tex, lhs if j == 0 else ""), size, where)
                scale = min(1.0, room_w / max(m.width, 1e-6))
                built.append((scale * self._glyph(m) / floor, m, scale))
                if scale >= 1.0:
                    break
            # the most explicit way of writing it that is nearly as large as the largest
            top = max(b[0] for b in built)
            ratio, m, scale = next(b for b in built if b[0] >= min(LARGE, NEARLY * top))
            m.scale(scale)
            smallest = min(smallest, ratio)
            rows.append(_Row(step.kind, m))
        # aligned at the relation sign; shrunk together when the block is too wide or tall
        for row in rows:
            rel = row.tex.id_to_vgroup_dict.get("vgrel")
            row.rel_x = rel.get_left()[0] if rel is not None and rel.family_members_with_points() else row.tex.get_left()[0]
        left = max(row.rel_x - row.tex.get_left()[0] for row in rows)
        right = max(row.tex.get_right()[0] - row.rel_x for row in rows)
        heights = sum(row.tex.height for row in rows)
        gaps = ROW_GAP * (len(rows) - 1) + 2 * BOX_PAD   # the gaps do not shrink with the rows
        shrink = min(1.0, room_w / max(left + right, 1e-6), max(area.height - gaps, 0.2 * area.height) / max(heights, 1e-6))
        if shrink < 1.0:
            for row in rows:
                row.tex.scale(shrink)
                rel = row.tex.id_to_vgroup_dict.get("vgrel")
                row.rel_x = rel.get_left()[0] if rel is not None and rel.family_members_with_points() else row.tex.get_left()[0]
            left, right = left * shrink, right * shrink
        if smallest * shrink < 0.98:
            log.warning("scene '%s': calculation '%s' is set %.0f%% below the readable size to fit; shorten it (units: never, fewer symbols "
                        "in one formula, or split it into two calculations)", self.spec.id, r.name, 100 * (1 - smallest * shrink))
        x_rel = area.center[0] - (left + right) / 2 + left
        total = sum(row.tex.height for row in rows) + ROW_GAP * (len(rows) - 1)
        top = area.center[1] + total / 2
        color = resolve_color(p.result_color, self.theme)
        for row in rows:
            row.tex.shift(RIGHT * (x_rel - row.rel_x))
            row.rel_x = x_rel
            row.tex.set_y(top - row.tex.height / 2)
            top -= row.tex.height + ROW_GAP
            if row.kind == "result":
                row.box = SurroundingRectangle(row.tex, buff=BOX_PAD, corner_radius=0.1, color=color, stroke_width=3)
        table_row = self._rows_by_name.get(r.name)
        return _Calc(rows, table_row)

    # ----- targets -----------------------------------------------------------------------------

    def _register(self, title: Mobject | None, caption: Mobject | None) -> None:
        p = self.params
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=DOWN * 0.1)])
        if caption is not None:
            self._caption = caption
        self._symbol_rows = [self._rows_by_name[s.name] for s in p.symbols if s.name in self._rows_by_name]
        if self._table is not None:
            self.target("table", VGroup(*self._symbol_rows), entrance=self._table_entrance)
            for name, row in self._rows_by_name.items():
                result_k = next((k for k, r in enumerate(self.worked.results) if r.name == name), None)
                entrance = (lambda row=row: [FadeIn(row, shift=UP * 0.1)]) if result_k is None else (lambda k=result_k: self._to_table(k))
                self.target(f"row:{name}", row, entrance=entrance)
        occurrences: dict[str, list[Mobject]] = {}
        mobs = [row.tex for c in self._calcs for row in c.rows] + ([m for row in self._rows_by_name.values() for m in row] if self._table else [])
        for m in mobs:
            for key, group in getattr(m, "symbol_parts", []):
                occurrences.setdefault(key, []).append(group)
        for name in [s.name for s in p.symbols] + [r.name for r in self.worked.results]:
            parts = occurrences.get(name, [])
            if parts:
                self.target(f"symbol:{name}", VGroup(*parts), entrance=lambda: [])
        self._step_targets: list[dict[str, Any]] = []
        for k, (calc, spec) in enumerate(zip(self._calcs, p.calculations)):
            n = k + 1
            by_kind: dict[str, Any] = {}
            for j, row in enumerate(calc.rows):
                name = TARGET_NAME.get(row.kind)
                if name is None:
                    continue
                names = [f"{name}{n}"] + ([f"result:{spec.name}"] if row.kind == "result" else [])
                by_kind[row.kind] = self.target(names, row.mobject, outline=row.tex, entrance=lambda k=k, j=j: self._step(k, j))
            if spec.substitute and "substitute" not in by_kind:   # a formula of numbers only: nothing to substitute
                self.target(f"substitution{n}", calc.rows[0].tex, entrance=lambda k=k: self._step(k, 0))
            self.target([f"calc{n}", f"calc:{spec.name}"], VGroup(*[row.mobject for row in calc.rows]),
                        entrance=lambda k=k: self._step(k, len(self._calcs[k].rows) - 1))
            self._step_targets.append(by_kind)

    # ----- entrances ---------------------------------------------------------------------------

    def _table_entrance(self) -> list[Animation]:
        rows = [r for r in self._symbol_rows if not self.on_screen_parts(r)]
        return [LaggedStart(*[FadeIn(r, shift=UP * 0.1) for r in rows], lag_ratio=0.15)] if rows else []

    def _intro(self) -> list[Animation]:
        """Title, caption and the table's symbols, if not on screen yet."""
        anims: list[Animation] = []
        for name in ("title", "table"):
            if self.find_targets(name):
                anims += self.entrance(name)
        caption = getattr(self, "_caption", None)
        if caption is not None and not self.on_screen_parts(caption):
            anims.append(FadeIn(caption))
        return anims

    def _to_table(self, k: int) -> list[Animation]:
        """Result ``k`` joins the table (its calculation's rows leave)."""
        calc = self._calcs[k]
        anims: list[Animation] = []
        shown = [row.mobject for row in calc.rows if self.on_screen_parts(row.tex)]
        if shown:
            anims.append(FadeOut(VGroup(*shown), shift=UP * 0.2))
        row = calc.table_row
        if row is not None and not self.on_screen_parts(row):
            anims.append(FadeIn(row, shift=LEFT * 0.15))
        return anims

    def _enter_row(self, row: _Row) -> list[Animation]:
        if row.kind == "formula":
            anims: list[Animation] = [Write(row.tex)]
        else:
            anims = [FadeIn(row.tex, shift=DOWN * 0.12)]
        if row.box is not None:
            anims.append(Create(row.box))
        return anims

    def _step(self, k: int, j: int) -> list[Animation]:
        """Calculation ``k`` up to its row ``j`` (and the rows the actions leave to it after
        ``j``): the earlier calculation leaves (its result to the table), the intro comes first."""
        calc = self._calcs[k]
        upto = self._follow(k, j)
        todo = [row for row in calc.rows[: upto + 1] if not self.on_screen_parts(row.tex)]
        if not todo:
            return []
        before: list[Animation] = self._intro()
        for i in range(k):
            leaving = [row.mobject for row in self._calcs[i].rows if self.on_screen_parts(row.tex)]
            if leaving:
                before += self._to_table(i) if self.params.results_in_table else [FadeOut(VGroup(*leaving), shift=UP * 0.2)]
        stages = [AnimationGroup(*before)] if before else []
        stages += [AnimationGroup(*self._enter_row(row)) for row in todo]
        return [Succession(*stages)] if len(stages) > 1 else list(stages[0].animations)

    def _follow(self, k: int, j: int) -> int:
        """The last row an entrance of row ``j`` of calculation ``k`` brings: ``j`` itself, and
        the rows after it no action names and the scene's steps do not reach."""
        named = self._named.get(k, set())
        if not named or j not in named:
            return j
        last = j
        for i in range(j + 1, len(self._calcs[k].rows)):
            if i in named:
                break
            last = i
        return last

    # ----- playing -----------------------------------------------------------------------------

    def _action_rows(self) -> dict[int, set[int]]:
        """Per calculation, the rows the beat actions bring (``reveal``, ``substitute``,
        ``compute``, ``convert``)."""
        out: dict[int, set[int]] = {}
        for kind in TIMED:
            for use in self.action_uses(kind):
                for pattern in use.config.targets():
                    for t in self.find_targets(pattern):
                        for k in range(len(self._calcs)):
                            j = self._row_of(k, t, kind)
                            if j is not None:
                                out.setdefault(k, set()).add(j)
        return out

    def _row_of(self, k: int, target: Any, action: str) -> int | None:
        """The row of calculation ``k`` an action on ``target`` brings, if any."""
        calc = self._calcs[k]
        kinds = [row.kind for row in calc.rows]
        n = k + 1
        if action in ACTION_STEP and (f"calc{n}" in target.names):
            want = ACTION_STEP[action]
            return kinds.index(want) if want in kinds else (len(kinds) - 1 if want == "convert" else None)
        for j, row in enumerate(calc.rows):
            name = TARGET_NAME.get(row.kind)
            if name is not None and f"{name}{n}" in target.names:
                return j
        if f"calc{n}" in target.names:
            return len(kinds) - 1
        return None

    def calculation_step(self, target: Any, action: str) -> list[Animation]:
        """The entrance an action plays on a calculation target (``substitute``, ``compute``,
        ``convert``)."""
        for k in range(len(self._calcs)):
            j = self._row_of(k, target, action)
            if j is not None:
                return self._step(k, j)
        return []

    def _play(self) -> None:
        self._named = self._action_rows()
        auto: list[list[Callable[[], list[Animation]]]] = []
        for k, calc in enumerate(self._calcs):
            named = self._named.get(k, set())
            stop = min(named) if named else len(calc.rows)
            auto.append([(lambda k=k, j=j: self._step(k, j)) for j in range(stop)])
        n_beats = max(1, len(self.beats))
        beat_steps: list[list[Callable[[], list[Animation]]]] = [[] for _ in range(n_beats)]
        if len(self._calcs) >= n_beats:
            for b, ks in enumerate(distribute(len(self._calcs), n_beats)):
                beat_steps[b] = [s for k in ks for s in auto[k]]
        else:
            for k, beats in enumerate(distribute(n_beats, len(self._calcs))):
                if not beats:
                    continue
                plan = distribute(len(auto[k]), len(beats))
                for b, idx in zip(beats, plan):
                    beat_steps[b] = [auto[k][i] for i in idx]
        if not beat_steps[0]:
            beat_steps[0] = [self._intro]
        for i, d in self.timeline():
            self.play_steps(d, beat_steps[i] if i < len(beat_steps) else [], fraction=0.6, cap=1.6)
        self.finish()
