"""``equation_derivation``: a sequence of equations, each step morphing into the next with its
matching parts moving into place, an optional note per step, earlier steps kept (stacked and
dimmed, aligned at ``=``) or replaced, and a box around the result.

Needs LaTeX (``latex`` and ``dvisvgm`` on PATH; MiKTeX on Windows), like ``equation``.

**Matching parts.** A part that should move from one step into the next is marked: written
``{{ ... }}`` in both steps (with a space or the start of the formula before ``{{``), listed in
the step's ``match`` (isolated in that step and the one before), or named in ``terms`` /
``colors`` (isolated in every step). Marked parts with the same TeX move into each other; the
rest of the glyphs move when their shapes match and fade otherwise. Parts are isolated by
wrapping them in dvisvgm groups (``\\special{dvisvgm:raw <g id=...>}``) at token boundaries,
so ``x`` is never split out of ``\\exp``.
"""

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from vidgen.api import *

log = logging.getLogger("vidgen.scenes")

#: One TeX token: a control word, a control symbol, a run of spaces, or one character.
_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|\s+|.", re.S)
#: Relation symbols a long step may be broken before (top level only).
RELATIONS = frozenset(
    {"=", "<", ">", r"\le", r"\leq", r"\ge", r"\geq", r"\ne", r"\neq", r"\approx", r"\equiv", r"\sim", r"\simeq", r"\cong",
     r"\propto", r"\to", r"\rightarrow", r"\Rightarrow", r"\implies", r"\iff", r"\Leftrightarrow", r"\longrightarrow",
     r"\Longrightarrow", r"\mapsto", r"\coloneqq", r"\leqslant", r"\geqslant"}
)
#: Delimiter commands: the token after them cannot be wrapped (``\left(``).
_DELIMITERS = frozenset({r"\left", r"\right", r"\middle", r"\big", r"\Big", r"\bigg", r"\Bigg", r"\bigl", r"\bigr", r"\Bigl",
                         r"\Bigr", r"\biggl", r"\biggr", r"\Biggl", r"\Biggr", r"\bigm", r"\Bigm"})
#: Commands taking an argument: a part right after one is wrapped in braces (``\vec{x}``).
_TAKES_ARGUMENT = frozenset({r"\frac", r"\dfrac", r"\tfrac", r"\sqrt", r"\vec", r"\hat", r"\bar", r"\tilde", r"\dot", r"\ddot",
                             r"\overline", r"\underline", r"\mathrm", r"\mathbf", r"\mathit", r"\mathcal", r"\mathbb", r"\mathsf",
                             r"\mathfrak", r"\boldsymbol", r"\bm", r"\text", r"\textbf", r"\textit", r"\operatorname", r"\widehat",
                             r"\widetilde", r"\overrightarrow", r"\binom", r"\not", r"\cancel", r"\underbrace", r"\overbrace"})
_OPEN = r"\special{dvisvgm:raw <g id='%s'>}"
_CLOSE = r"\special{dvisvgm:raw </g>}"
_SPECIAL = re.compile(r"(?:\\?[A-Za-z]*\s*)?\{dvisvgm:raw[^}]*\}|(?:\S*\s+)?<g id='[^']*'>\}|</g>\}")
#: Space between stacked steps, and padding of the result box (units).
ROW_GAP, BOX_PAD = 0.45, 0.18
#: Long steps are broken at their relations while they would be set below this multiple of the
#: readable size (lint's ``min_font``), when breaking makes them larger.
COMFORT = 1.5
#: Gap between the equations and the notes; the note's marker bar and its distance to the text.
NOTE_GAP, BAR_GAP = 0.5, 0.22


#: Contrast (WCAG) dimmed earlier steps and notes keep with the background: lint's 2:1 for
#: dimmed text, plus a margin.
DIMMED_RATIO = 2.3


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[k : k + 2], 16) / 255 for k in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _blend(color: str, background: str, alpha: float) -> str:
    a = [int(color.lstrip("#")[k : k + 2], 16) for k in (0, 2, 4)]
    b = [int(background.lstrip("#")[k : k + 2], 16) for k in (0, 2, 4)]
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(a, b))


def readable_opacity(colors: Sequence[str], background: str, opacity: float, ratio: float = DIMMED_RATIO) -> float:
    """The smallest opacity from ``opacity`` up at which every one of ``colors`` (``#RRGGBB``)
    keeps ``ratio`` contrast with ``background`` (at most 1)."""
    bg = _luminance(background)
    while opacity < 1.0:
        lums = [_luminance(_blend(c, background, opacity)) for c in colors]
        if all((max(lum, bg) + 0.05) / (min(lum, bg) + 0.05) >= ratio for lum in lums):
            return opacity
        opacity = min(1.0, opacity + 0.02)
    return 1.0


def tokens(tex: str) -> list[tuple[int, int, str]]:
    """``(start, end, text)`` of every TeX token in ``tex``."""
    return [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(tex)]


def _ink(tex: str) -> list[str]:
    return [t for _, _, t in tokens(tex) if not t.isspace()]


def term_key(tex: str) -> str:
    """The key two parts are matched by: their tokens, spaces ignored (``2 ab`` = ``2ab``)."""
    return " ".join(_ink(tex))


def brace_problem(tex: str) -> str | None:
    """Why the braces of ``tex`` do not balance, or ``None``."""
    depth = 0
    for _, _, t in tokens(tex):
        depth += 1 if t == "{" else -1 if t == "}" else 0
        if depth < 0:
            return "a '}' closes nothing"
    return "a '{' is not closed" if depth else None


def split_marked(tex: str) -> list[tuple[str, bool]]:
    """``tex`` cut into ``(text, marked)`` pieces at Manim's ``{{ ... }}`` notation (``{{`` at
    the start or after a space). Raises ``ValueError`` for an unclosed or empty mark."""
    segments = MathTex._split_double_braces(tex)
    if len(segments) % 2 == 0:
        raise ValueError("a '{{' is not closed with '}}'")
    pieces = [(s, k % 2 == 1) for k, s in enumerate(segments)]
    if any(marked and not s.strip() for s, marked in pieces):
        raise ValueError("an empty '{{ }}'")
    return [(s, marked) for s, marked in pieces if s]


def plain(tex: str) -> str:
    """``tex`` without its ``{{ }}`` marks."""
    try:
        return "".join(s for s, _ in split_marked(tex))
    except ValueError:
        return tex


def marked_terms(tex: str) -> list[str]:
    """The ``{{ ... }}`` parts of ``tex`` (stripped), in order."""
    try:
        return [s.strip() for s, marked in split_marked(tex) if marked]
    except ValueError:
        return []


def contains(tex: str, term: str) -> bool:
    """Whether ``term`` occurs in ``tex`` as whole tokens."""
    hay, needle = _ink(plain(tex)), _ink(term)
    return bool(needle) and any(hay[i : i + len(needle)] == needle for i in range(len(hay) - len(needle) + 1))


def break_lines(tex: str, every: bool) -> str | None:
    """``tex`` with line breaks before its top-level relations (``align*``: ``a &= b \\\\ &= c``):
    before every relation but the first, or (``every``) before the first too. ``None`` when
    there is nothing to break (no relation to break before, or the step has its own ``&`` /
    ``\\\\``)."""
    toks = tokens(tex)
    if any(t in ("&", "\\\\") for _, _, t in toks):
        return None
    depth, left, found, previous = 0, 0, [], ""
    for k, (start, _, t) in enumerate(toks):
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1
        elif t == r"\left":
            left += 1
        elif t == r"\right":
            left -= 1
        elif t in RELATIONS and depth == 0 and left == 0 and previous not in RELATIONS:
            if any(not s.isspace() for _, _, s in toks[:k]):
                found.append(start)
        if not t.isspace():
            previous = t
    if not found or (not every and len(found) < 2):
        return None
    out, last = [], 0
    for n, pos in enumerate(found):
        out.append(tex[last:pos])
        out.append("& " if n == 0 and not every else r"\\ & ")
        last = pos
    out.append(tex[last:])
    return "".join(out)


def _isolate(text: str, terms: list[tuple[str, list[str]]], gid: Callable[[str], str]) -> str:
    """``text`` with every whole-token occurrence of ``terms`` (``(key, tokens)``, longest
    first) wrapped in a dvisvgm group named by ``gid(key)``; braces are added where TeX needs
    one argument (after ``^``, ``_`` or a command such as ``\\vec``), and parts right after a
    delimiter command (``\\left``) are left alone."""
    toks = tokens(text)
    ink = [(k, t) for k, (_, _, t) in enumerate(toks) if not t.isspace()]
    out, pos, i = [], 0, 0
    while i < len(ink):
        hit = None
        for key, needle in terms:
            if [t for _, t in ink[i : i + len(needle)]] == needle:
                hit = (key, len(needle))
                break
        before = ink[i - 1][1] if i > 0 else ""
        if hit is None or before in _DELIMITERS:
            i += 1
            continue
        key, n = hit
        start, end = toks[ink[i][0]][0], toks[ink[i + n - 1][0]][1]
        wrap = before in ("^", "_") or before in _TAKES_ARGUMENT
        out.append(text[pos:start])
        out.append(("{" if wrap else "") + _OPEN % gid(key) + text[start:end] + _CLOSE + ("}" if wrap else ""))
        pos, i = end, i + n
    out.append(text[pos:])
    return "".join(out)


def isolated_source(tex: str, terms: Sequence[str]) -> tuple[str, list[tuple[str, str]]]:
    """The LaTeX to compile for ``tex`` and its parts as ``(key, group id)``: each ``{{ }}``
    mark and each whole-token occurrence of ``terms``."""
    wanted = sorted({term_key(t): _ink(t) for t in terms if _ink(t)}.items(), key=lambda kv: -len(kv[1]))
    parts: list[tuple[str, str]] = []

    def gid(key: str) -> str:
        parts.append((key, f"vgpart{len(parts):03d}"))
        return parts[-1][1]

    out = []
    for text, marked in split_marked(tex):
        if marked:
            group = gid(term_key(text))
            out.append(_OPEN % group + _isolate(text, wanted, gid) + _CLOSE)
        else:
            out.append(_isolate(text, wanted, gid))
    return "".join(out), parts


def tex_error_excerpt(exc: BaseException) -> str:
    """The TeX error message and where it happened, from the log file Manim names in ``exc``
    (dvisvgm markers removed), else the exception's first line."""
    text = str(exc).strip()
    m = re.search(r"log file: (\S+\.log)", text)
    lines: list[str] = []
    if m:
        try:
            lines = Path(m.group(1)).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    for k, line in enumerate(lines):
        if not line.startswith("! "):
            continue
        message = line[2:].strip().rstrip(".")
        # TeX's context: a line with what it read up to the error ("<argument> ..." or
        # "l.8 ..."), then the rest of the line
        at = next((j for j in range(k + 1, min(k + 14, len(lines) - 1)) if re.match(r"(<[^>]*>|l\.\d+) ", lines[j])), None)
        if at is None:
            return message
        read = re.sub(r"^(<[^>]*>|l\.\d+)\s*", "", lines[at]).lstrip(".")
        where = _SPECIAL.sub("", read + lines[at + 1].strip())
        where = re.sub(r"(?:\\?[A-Za-z]*\s*)?\{dvisvgm:raw.*$", "", where)  # one cut short by TeX
        where = " ".join(where.replace(r"\end{align*}", "").split())
        return message + (f" (at: {where[-60:]})" if where else "")
    return text.splitlines()[0] if text else type(exc).__name__


class DerivationStep(SceneParams):
    """A step of a derivation: ``{tex, note, match, transition}``; a string alone is ``tex``."""

    also_accepts = (str,)

    tex: str
    """Math-mode LaTeX (no $). Mark a part that moves into the same part of the next step as {{ ... }} (with a space or the start before {{)."""
    note: TranslatableStr = ""
    """A short justification shown with this step ('divide both sides by 2'): beside the equations (16:9) or below them (9:16)."""
    match: list[str] = []
    """TeX parts that move from the previous step into this one (isolated in both steps), as an alternative to marking them {{ }}."""
    transition: Literal["auto", "shapes", "fade"] = "auto"
    """How the previous step becomes this one: auto (marked parts move into each other, the other glyphs move when their shapes match, else fade), shapes (glyphs by shape only), fade (cross-fade)."""

    @model_validator(mode="before")
    @classmethod
    def _from_tex(cls, data: Any) -> Any:
        return {"tex": data} if isinstance(data, str) else data

    @field_validator("tex")
    @classmethod
    def _check_tex(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tex cannot be empty")
        problem = brace_problem(value)
        if problem:
            raise ValueError(f"unbalanced braces in {value!r}: {problem}")
        split_marked(value)
        return value

    @field_validator("match")
    @classmethod
    def _check_match(cls, value: list[str]) -> list[str]:
        for term in value:
            if not term.strip():
                raise ValueError("match: a part cannot be empty")
            if brace_problem(term):
                raise ValueError(f"match: {term!r} has unbalanced braces (a part is a complete TeX group)")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A string alone is also a step (JSON Schema ``anyOf`` string | object)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


@dataclass
class _Line:
    """A built step: its formula, the parts by key, where it is aligned (the x of its first
    alignment part, ``None``: centred), its note and its LaTeX."""

    formula: MathTex
    parts: list[tuple[str, VGroup]]
    anchor: float | None
    note: Mobject | None = None
    #: The LaTeX it was built from (the step's, maybe with line breaks).
    tex: str = ""


class _Swap(AnimationGroup):
    """Play ``animations`` with ``hide`` taken off screen first; at the end every mobject they
    used is removed and ``show`` (if any) is on screen, whole."""

    def __init__(self, *animations: Animation, hide: Sequence[Mobject] = (), show: Mobject | None = None, **kwargs: Any) -> None:
        self.hide, self.show = list(hide), show
        super().__init__(*animations, **kwargs)

    def _setup_scene(self, scene: Scene) -> None:
        if self.hide:
            scene.remove(*self.hide)
        super()._setup_scene(scene)

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        scene.remove(self.mobject, *[a.mobject for a in self.animations])
        if self.show is not None:
            scene.add(self.show)


def _leaves(mob: Mobject) -> list[Mobject]:
    return mob.family_members_with_points()


def morph(source: _Line, target: _Line, style: str) -> list[Animation]:
    """The animations that turn a copy of ``source`` (``source.formula`` must not be on screen
    or is hidden by the caller) into ``target``: marked parts with the same key move into each
    other (bigger parts first, occurrences in order), the remaining glyphs go through
    ``TransformMatchingShapes``."""
    src, dst = source.formula, target.formula
    if style == "fade":
        return [FadeOut(src), FadeIn(dst)]
    if style == "shapes":
        return [TransformMatchingShapes(src, dst)]
    used_s: set[int] = set()
    used_d: set[int] = set()
    pairs = []
    keys = dict.fromkeys(k for k, _ in source.parts)
    for key in keys:
        mine = [g for k, g in source.parts if k == key]
        theirs = [g for k, g in target.parts if k == key]
        pairs += list(zip(mine, theirs))
    pairs.sort(key=lambda pair: -len(_leaves(pair[0])))
    anims: list[Animation] = []
    for a, b in pairs:
        la, lb = _leaves(a), _leaves(b)
        if not la or not lb or any(id(m) in used_s for m in la) or any(id(m) in used_d for m in lb):
            continue
        used_s.update(id(m) for m in la)
        used_d.update(id(m) for m in lb)
        anims.append(Transform(VGroup(*la), VGroup(*lb)))
    rest_s = [m for m in _leaves(src) if id(m) not in used_s]
    rest_d = [m for m in _leaves(dst) if id(m) not in used_d]
    if rest_s and rest_d:
        anims.append(TransformMatchingShapes(VGroup(*rest_s), VGroup(*rest_d)))
    elif rest_s:
        anims.append(FadeOut(VGroup(*rest_s)))
    elif rest_d:
        anims.append(FadeIn(VGroup(*rest_d)))
    return anims


@scene("equation_derivation")
class EquationDerivation(NarratedScene):
    """Step *i* (an entry of ``steps``) arrives at beat *i*: the previous step morphs into it
    (its marked parts move into place) and its note appears. In ``history`` mode earlier steps
    stay, stacked above and dimmed, aligned at ``align_at``; in ``replace`` mode each step takes
    the place of the one before. The last step gets a box (``result``). More steps than beats
    are spread evenly; later beats hold.

    Action targets: ``title``, ``step<N>``, ``note<N>``, ``result`` (the last step with its box)
    and ``term:<tex>`` (a part named in ``terms``, ``colors``, ``match`` or marked ``{{ }}``, in
    the current step).
    """

    outro = 0.5
    target_patterns = ("title", "step<N>", "note<N>", "result", "term:<tex>")
    #: In a vertical frame the formulas may grow by this factor (they are still fitted to the width).
    portrait_growth = 1.25

    class Params(SceneParams):
        steps: list[DerivationStep] = Field(min_length=1)
        """Step i arrives at beat i: {tex, note, match, transition}, or just the LaTeX."""
        title: TranslatableStr = ""
        """Heading above the derivation."""
        mode: Literal["history", "replace"] = "history"
        """history: earlier steps stay, stacked above the current one and dimmed; replace: each step takes the place of the previous one."""
        keep: int | None = Field(default=None, ge=1)
        """history: the most steps on screen at once (the oldest scroll away); default: as many as fit at a readable size."""
        align_at: str = "="
        """Steps are aligned at the first occurrence of this TeX (a relation such as '=' or '\\le'); '' centres every step."""
        colors: dict[str, ThemeColor] = {}
        """Parts coloured in every step, TeX -> color: {x: accent, '\\lambda': highlight}."""
        terms: list[str] = []
        """More TeX parts to isolate in every step (they move into each other and are targets term:<tex>)."""
        result: Literal["box", "highlight", "none"] = "box"
        """Marks the last step: a box around it, a highlight band behind it, or nothing."""
        result_color: ThemeColor = "highlight"
        """Color of the result box / band."""
        size: ThemeSize = 80
        """Formula size (the largest; smaller to fit the width and the stacked steps, not below the readable size)."""
        color: ThemeColor = "text"
        """Formula color."""
        dim_opacity: float = Field(default=0.45, ge=0.15, le=1.0)
        """history: opacity of the earlier steps and their notes (raised where a colour would fall below 2.3:1 contrast with the background)."""
        note_position: Literal["auto", "side", "bottom"] = "auto"
        """Where notes go: side (beside the equations, level with their step), bottom (below them, one at a time), auto (side in 16:9, bottom in a vertical frame)."""
        note_size: ThemeSize = "body"
        """Note text size."""
        note_color: ThemeColor = "dim"
        """Note text color."""
        note_mark_color: ThemeColor = "accent"
        """Color of the bar beside each note."""

        @field_validator("terms")
        @classmethod
        def _check_terms(cls, value: list[str]) -> list[str]:
            for term in value:
                if not term.strip():
                    raise ValueError("terms: a term cannot be empty")
                if brace_problem(term):
                    raise ValueError(f"terms: {term!r} has unbalanced braces (a term is a complete TeX group)")
            return value

        @model_validator(mode="after")
        def _parts_in_steps(self) -> SceneParams:
            for where, names in (("terms", self.terms), ("colors", list(self.colors))):
                for term in names:
                    if not term.strip() or brace_problem(term):
                        raise ValueError(f"{where}: {term!r} is not a complete TeX group")
                    if not any(contains(s.tex, term) for s in self.steps):
                        raise ValueError(f"{where}: {term!r} is not part of any step (whole TeX tokens: 'x' is not part of '\\exp')")
            if self.steps[0].match:
                raise ValueError("steps[0].match: the first step has no step before it to match")
            for k, step in enumerate(self.steps[1:], start=1):
                for term in step.match:
                    for j in (k - 1, k):
                        if not contains(self.steps[j].tex, term):
                            raise ValueError(f"steps[{k}].match: {term!r} is not part of step {j + 1} ({plain(self.steps[j].tex)!r})")
            if self.align_at.strip() and brace_problem(self.align_at):
                raise ValueError("align_at: unbalanced braces")
            return self

        def term_names(self) -> list[str]:
            """The ``term:`` target names: ``terms``, ``colors``, ``match`` and the marked parts."""
            names = list(self.terms) + list(self.colors)
            names += [t for s in self.steps for t in s.match]
            names += [t for s in self.steps for t in marked_terms(s.tex)]
            return list(dict.fromkeys(n.strip() for n in names))

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``step<N>`` per step, ``note<N>`` per step with a note,
        ``result`` (the last step, with its box) and ``term:<tex>`` per isolated part."""
        n = len(params.steps)
        names = (["title"] if params.title else []) + [f"step{k}" for k in range(1, n + 1)]
        names += [f"note{k + 1}" for k, s in enumerate(params.steps) if s.note.strip()]
        return names + ["result"] + [f"term:{t}" for t in params.term_names()]

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        if not latex_available():
            log.warning("equation_derivation scenes need LaTeX, which was not found on PATH; rendering them will fail")
        return super().validate_project(params, project)

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        require_latex(f"scene '{self.spec.id}' (type equation_derivation)")
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)   # header band, 1.3x in a vertical frame
            body = body.below(title, gap=0.45)
        self._layout(body)
        self._register(title)
        title_t = self.find_targets("title")[0] if title is not None else None

        def first() -> list[Animation]:
            return self.entrance(self._steps_t[0]) + (self.entrance(title_t) if title_t is not None else [])

        def advance(k: int) -> list[Animation]:  # skipped once a later step is on screen (transform)
            if not any(self.is_shown(t) for t in self._steps_t[k:]):
                return self.entrance(self._steps_t[k])
            last = self._steps_t[-1]
            if k == len(self._lines) - 1 and self._box is not None and self.is_shown(last) and not self.on_screen_parts(self._box):
                return [self._mark(self._box)]  # the last step came early (transform): its box now
            return []

        steps: list[Callable[[], list[Animation]]] = [first] + [(lambda k=k: advance(k)) for k in range(1, len(p.steps))]
        self.reveal(steps, fraction=0.6, cap=1.6)
        self.finish()

    # ----- building ----------------------------------------------------------------------------

    def _isolated_terms(self, k: int) -> list[str]:
        p = self.params
        terms = list(p.terms) + list(p.colors) + list(p.steps[k].match)
        if k + 1 < len(p.steps):
            terms += p.steps[k + 1].match
        if p.align_at.strip():
            terms.append(p.align_at)
        return terms

    def _build(self, k: int, tex: str, size: float) -> _Line:
        """Step ``k`` (0-based) typeset at ``size`` from ``tex`` (its own LaTeX, maybe with line
        breaks), parts isolated and coloured."""
        p = self.params
        source, groups = isolated_source(tex, self._isolated_terms(k))
        try:
            formula = MathTex(source, font_size=size, color=resolve_color(p.color, self.theme))
        except Exception as exc:  # Manim raises plain exceptions for LaTeX errors
            raise VidgenError(
                f"scene '{self.spec.id}': step {k + 1} does not compile: {tex_error_excerpt(exc)}; the step is "
                f"'{plain(p.steps[k].tex)}' (math-mode LaTeX; in YAML write backslashes in single quotes)"
            ) from None
        formula.tex_string = plain(p.steps[k].tex)  # what the layout dump and lint show: the step as written
        parts = [(key, formula.id_to_vgroup_dict[g]) for key, g in groups if g in formula.id_to_vgroup_dict]
        colors = {term_key(t): resolve_color(c, self.theme) for t, c in p.colors.items()}
        for key, group in parts:
            if key in colors:
                group.set_color(colors[key])
        return _Line(formula, parts, None, tex=tex)

    def _anchor(self, line: _Line) -> float | None:
        if not self.params.align_at.strip():
            return None
        key = term_key(self.params.align_at)
        for k, group in line.parts:
            if k == key and _leaves(group):
                return float(group.get_center()[0])
        return None

    @staticmethod
    def _glyph_size(line: _Line) -> float:
        """The formula's text size as lint measures it: the 75th percentile of glyph heights."""
        heights = [m.height for m in _leaves(line.formula) if m.height > 1e-3]
        return float(np.percentile(heights, 75)) if heights else 1.0

    def _extent(self, lines: list[_Line]) -> tuple[float, float, float]:
        """Left and right reach from the alignment point of aligned lines, and the widest
        centred line."""
        left = right = centred = 0.0
        for line in lines:
            a = self._anchor(line)
            f = line.formula
            if a is None:
                centred = max(centred, f.width)
            else:
                left, right = max(left, a - f.get_left()[0]), max(right, f.get_right()[0] - a)
        return left, right, centred

    def _width_scale(self, lines: list[_Line], width: float) -> float:
        left, right, centred = self._extent(lines)
        needed = max(left + right, centred, 1e-6)
        return width / needed

    def _layout(self, body: Region) -> None:
        """Notes, sizes, line breaks and positions of every step."""
        p = self.params
        notes = [s.note.strip() for s in p.steps]
        self._mode: Literal["side", "bottom"] | None = None
        if any(notes):  # a vertical frame has no room beside the equations
            self._mode = "bottom" if self.is_portrait or p.note_position == "bottom" else "side"
        eq = body
        note_texts: dict[int, Mobject] = {}
        if self._mode == "side":
            note_w = min(max(0.3 * body.width, 3.0), 4.6)
            for k, note in enumerate(notes):
                if note:
                    note_texts[k] = readable_text(note, Region(0, 0, note_w - BAR_GAP - 0.06, body.height * 0.4), size=p.note_size,
                                                  color=p.note_color, align="left")
            eq = Region(body.x0, body.y0, body.x1 - note_w - NOTE_GAP, body.y1)
        elif self._mode == "bottom":
            for k, note in enumerate(notes):
                if note:
                    note_texts[k] = readable_text(note, Region(0, 0, body.width - 0.4, body.height * 0.25), size=p.note_size,
                                                  color=p.note_color)
            band = max(t.height for t in note_texts.values())
            eq = Region(body.x0, body.y0 + band + NOTE_GAP, body.x1, body.y1)
        self._eq = eq

        # sizes: the largest that fits the width (lines broken at relations if that keeps them
        # readable) and the stacked rows, never above `size`
        size = float(self.theme.size(p.size)) * (self.portrait_growth if self.is_portrait else 1.0)
        room_w = eq.width - (2 * BOX_PAD + 0.1 if p.result == "box" else 0.0)
        lines = [self._build(k, s.tex, size) for k, s in enumerate(p.steps)]
        floor = Text("H", font=self.theme.font, font_size=readable_size()).height * 1.04
        f_min = floor / min(self._glyph_size(line) for line in lines)
        comfortable = min(1.0, COMFORT * f_min)
        for k, line in enumerate(lines):
            for every in (False, True):
                if self._width_scale([line], room_w) >= comfortable:
                    break
                broken = break_lines(p.steps[k].tex, every)
                if broken is not None:
                    candidate = self._build(k, broken, size)
                    if self._width_scale([candidate], room_w) > self._width_scale([line], room_w):
                        line = candidate
            lines[k] = line
        f_w = min(1.0, self._width_scale(lines, room_w))
        heights = [line.formula.height for line in lines]
        n = len(lines)
        # a side note sets its row's height when it is taller than the formula (it is not scaled)
        self._note_h = [note_texts[k].height if self._mode == "side" and k in note_texts else 0.0 for k in range(n)]
        room_h = eq.height - (2 * BOX_PAD if p.result == "box" else 0.0)

        def need(f: float, r: int) -> float:
            """Height of the tallest run of ``r`` consecutive rows at scale ``f``."""
            rows_h = [max(f * h, nh) for h, nh in zip(heights, self._note_h)]
            return max(sum(rows_h[j : j + r]) for j in range(n - r + 1)) + (r - 1) * ROW_GAP

        def fits(r: int) -> float:
            """The largest scale (up to the width's) at which ``r`` rows fit the height; 0: none."""
            lo, hi = 0.0, f_w
            if need(hi, r) <= room_h:
                return hi
            for _ in range(30):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if need(mid, r) <= room_h else (lo, mid)
            return lo if need(lo, r) <= room_h else 0.0

        rows = 1 if p.mode == "replace" else min(n, p.keep or n)
        while p.keep is None and rows > 1 and fits(rows) < min(f_w, f_min):
            rows -= 1
        f_h = fits(rows) or room_h / max(heights)
        scale = min(f_w, f_h)
        if scale < f_min * 0.999:
            log.warning(
                "scene '%s': the formulas are set %.0f%% below the readable size to fit; shorten the longest step%s",
                self.spec.id, 100 * (1 - scale / f_min), "" if p.mode == "replace" or p.keep else " or set keep:",
            )
        self._rows = rows
        inks = [p.color, p.note_color, *p.colors.values()]
        self._dim = readable_opacity([resolve_color(c, self.theme) for c in inks], self.theme.background, p.dim_opacity)
        for line in lines:
            line.formula.scale(scale)
        # horizontal: aligned lines share the alignment point; the block (and the notes beside
        # it) centred in the body
        left, right, centred = self._extent(lines)
        block = max(left + right, centred)
        mark = resolve_color(p.note_mark_color, self.theme)
        for k, note in note_texts.items():
            if self._mode == "side":
                bar = Line(UP * note.height / 2, DOWN * note.height / 2, stroke_width=4, color=mark)
                note_texts[k] = VGroup(bar, note.next_to(bar, RIGHT, buff=BAR_GAP))
        pad = BOX_PAD if p.result == "box" else 0.0
        beside = max((t.width for t in note_texts.values()), default=0.0) + NOTE_GAP if self._mode == "side" else 0.0
        x0 = max(body.x0, body.center[0] - (block + 2 * pad + beside) / 2) + pad
        middle = x0 + block / 2
        x_align = middle - (left + right) / 2 + left
        for line in lines:
            a = self._anchor(line)
            if a is None:
                line.formula.set_x(middle)
            else:
                line.formula.shift(RIGHT * (x_align - a))
            line.anchor = self._anchor(line)
        self._lines = lines
        if self._mode == "bottom":  # the notes' band right under the tallest block, the two centred
            tallest = max(self._block_height(self._window(k)) for k in range(n))
            gap = NOTE_GAP + (BOX_PAD if p.result != "none" else 0.0)
            top = min(body.y1, body.center[1] + (tallest + gap + band) / 2)
            self._eq = Region(eq.x0, top - tallest, eq.x1, top)
            self._band = Region(body.x0, top - tallest - gap - band, body.x1, top - tallest - gap)
        for k, line in enumerate(lines):
            note = note_texts.get(k)
            if note is None:
                continue
            if self._mode == "side":
                note.move_to([x0 + block + pad + NOTE_GAP, 0, 0], aligned_edge=LEFT)
            else:
                note.move_to(self._band.center)
            line.note = note
        for k in range(n):  # each step where it arrives
            self._place(self._window(k), k)

    def _window(self, k: int) -> list[int]:
        """The steps on screen once step ``k`` has arrived (oldest first)."""
        if self.params.mode == "replace":
            return [k]
        return list(range(max(0, k - self._rows + 1), k + 1))

    def _row_heights(self, window: list[int]) -> list[float]:
        """Height of each row of ``window``: its formula, or its side note when taller."""
        return [max(self._lines[j].formula.height, self._note_h[j]) for j in window]

    def _block_height(self, window: list[int]) -> float:
        hs = self._row_heights(window)
        return sum(hs) + ROW_GAP * (len(hs) - 1)

    def _slots(self, window: list[int]) -> dict[int, float]:
        """The y of each step of ``window``: stacked ``ROW_GAP`` apart, the block centred in the
        equations' area."""
        top = self._eq.center[1] + self._block_height(window) / 2
        out = {}
        for j, h in zip(window, self._row_heights(window)):
            out[j] = top - h / 2
            top -= h + ROW_GAP
        return out

    def _place(self, window: list[int], k: int) -> None:
        """Put step ``k`` (and its side note) where it goes in ``window``."""
        y = self._slots(window)[k]
        line = self._lines[k]
        line.formula.set_y(y)
        if self._mode == "side" and line.note is not None:
            line.note.set_y(y)

    # ----- targets -----------------------------------------------------------------------------

    def _register(self, title: Mobject | None) -> None:
        p = self.params
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=DOWN * 0.1)])
        self._archive: list[MathTex | None] = []
        self._archive_notes: list[Mobject | None] = []
        self._steps_t = []
        for k, line in enumerate(self._lines):
            if p.mode == "history":
                copy = line.formula.copy()
                self._archive.append(copy)
                mob: Mobject = VGroup(line.formula, copy)
            else:
                self._archive.append(None)
                mob = line.formula
            self._steps_t.append(self.target(f"step{k + 1}", mob, entrance=lambda k=k: self._arrive(k)))
        last = self._lines[-1].formula
        self._box: Mobject | None = None
        if p.result == "box":
            self._box = SurroundingRectangle(last, buff=BOX_PAD, corner_radius=0.12, color=resolve_color(p.result_color, self.theme), stroke_width=3)
        elif p.result == "highlight":
            band = SurroundingRectangle(last, buff=BOX_PAD, corner_radius=0.12, stroke_width=0)
            band.set_fill(resolve_color(p.result_color, self.theme), opacity=0.16)
            band.set_z_index(-1)
            self._box = band
        result = VGroup(last, self._box) if self._box is not None else last
        self.target("result", result, outline=last, entrance=self._result_entrance)
        for k, line in enumerate(self._lines):
            if line.note is not None:
                note = line.note
                if p.mode == "history" and self._mode == "side":
                    self._archive_notes.append(note.copy())
                    mob = VGroup(note, self._archive_notes[-1])
                else:
                    self._archive_notes.append(None)
                    mob = note
                self.target(f"note{k + 1}", mob, entrance=lambda k=k: self._note_entrance(k))
            else:
                self._archive_notes.append(None)
        names = p.term_names()
        for line in self._lines:
            for name in names:
                key = term_key(name)
                parts = [m for k, g in line.parts if k == key for m in _leaves(g)]
                if parts:  # a term is no step of its own: not revealed alone
                    self.target(f"term:{name}", VGroup(*parts), entrance=lambda: [])

    def _result_entrance(self) -> list[Animation]:
        """The last step (with its box), or just the box when the step is on screen."""
        if not self.is_shown(self._steps_t[-1]):
            return self._arrive(len(self._lines) - 1)
        return [self._mark(self._box)] if self._box is not None else []

    def _note_entrance(self, k: int) -> list[Animation]:
        """A note comes with its step (which plays it), or alone when the step is on screen."""
        note = self._lines[k].note
        return self._arrive(k) if not self.is_shown(self._steps_t[k]) else [FadeIn(note)]

    @staticmethod
    def _mark(box: Mobject) -> Animation:
        """Draw the result box (or fade in the band)."""
        return Create(box) if box.get_stroke_width() > 0 else FadeIn(box)

    # ----- animation ---------------------------------------------------------------------------

    def _shown_lines(self) -> list[tuple[int, Mobject]]:
        """The steps on screen (oldest first) and the mobject showing each (live or archived)."""
        out = []
        for j, line in enumerate(self._lines):
            archive = self._archive[j]
            if self.on_screen_parts(line.formula):
                out.append((j, line.formula))
            elif archive is not None and self.on_screen_parts(archive):
                out.append((j, archive))
        return out

    def _arrive(self, k: int) -> list[Animation]:
        """Step ``k`` comes on screen: the step before morphs into it, earlier steps move to
        their rows (dimmed, the oldest scrolling away) or leave, notes follow."""
        p = self.params
        line = self._lines[k]
        window = self._window(k)
        slots = self._slots(window)
        shown = self._shown_lines()
        anims: list[Animation] = []
        source = next((mob for j, mob in shown if j == k - 1), None)
        row_h = line.formula.height + ROW_GAP
        for j, mob in shown:
            if j == k:
                continue
            old = self._lines[j]
            archive, archived_note = self._archive[j], self._archive_notes[j]
            note_mob = next((n for n in (old.note, archived_note) if n is not None and self.on_screen_parts(n)), None)
            if j in slots and archive is not None:  # history: the step stays, in its new row, dimmed
                y = slots[j]
                anims.append(self._settle(mob, archive, y))
                if note_mob is not None and self._mode == "side":
                    anims.append(self._settle(note_mob, archived_note, y))
                elif note_mob is not None:  # one note at a time below the equations
                    anims.append(FadeOut(note_mob, shift=UP * 0.15))
                continue
            if not (j == k - 1 and p.mode == "replace"):  # the step before morphs into this one
                anims.append(FadeOut(mob, shift=UP * row_h * 0.5))
            if note_mob is not None:
                anims.append(FadeOut(note_mob, shift=UP * (0.15 if self._mode == "bottom" else row_h * 0.5)))
        self._place(window, k)
        if source is not None:
            prev = self._lines[k - 1]
            copy = source.copy()
            ghost = _Line(copy, self._parts_of(prev, source, copy), None)
            hide = [source] if p.mode == "replace" else []
            anims.append(_Swap(*morph(ghost, line, p.steps[k].transition), hide=hide, show=line.formula))
        else:
            anims.append(Write(line.formula))
        if line.note is not None:
            anims.append(FadeIn(line.note, shift=UP * 0.12 if self._mode == "bottom" else LEFT * 0.15))
        if k == len(self._lines) - 1 and self._box is not None:
            self._box.move_to(line.formula)
            return [AnimationGroup(AnimationGroup(*anims), self._mark(self._box), lag_ratio=0.7)]
        return anims

    def _settle(self, mob: Mobject, archive: Mobject | None, y: float) -> Animation:
        """Move a kept step (or its note) to row ``y``: the live one hands over to its dimmed
        archived copy (so ``term:`` targets mean the current step), an archived one moves."""
        if archive is None or mob is archive:
            return mob.animate.set_y(y)
        archive.match_x(mob).set_y(y).set_opacity(self._dim)
        return _Swap(ReplacementTransform(mob.copy(), archive), hide=[mob], show=archive)

    @staticmethod
    def _parts_of(line: _Line, shown: Mobject, copy: Mobject) -> list[tuple[str, VGroup]]:
        """``line.parts`` mapped onto ``copy`` (a copy of ``shown``, which is ``line.formula`` or
        its archived copy: same structure), by leaf position."""
        index = {id(m): i for i, m in enumerate(_leaves(line.formula))}
        mine = _leaves(copy)
        return [(key, VGroup(*[mine[index[id(m)]] for m in _leaves(group) if id(m) in index])) for key, group in line.parts]
