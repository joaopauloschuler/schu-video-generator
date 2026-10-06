"""``code_walkthrough``: a long listing in a fixed-height window that scrolls to the lines each
step talks about, highlights them, and can show a note beside (or below) them and enlarge them."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .actions import MoveCamera
from .code import (
    MIN_COLUMNS,
    NUMBER_GAP,
    TARGET_COLUMNS,
    line_centers,
    line_runs,
    mono_metrics,
    renumber,
    size_for_columns,
    style_names,
    text_canvas,
    wrap_code,
)

log = logging.getLogger("vidgen.scenes")

#: Opacity of the lines outside the selection (as in ``code``).
DIMMED = 0.35
#: Contrast every syntax colour keeps with the window (lint's 4.5:1 for text, plus room for the
#: highlight band).
INK_RATIO = 4.6
#: Largest and smallest opacity of the highlight band (less when the syntax colours would lose
#: contrast over it, as on light themes). A bar in the highlight colour marks its left edge.
BAND, BAND_MIN = 0.12, 0.07
#: Listings of at most this many lines get a ``lines:<a-b>`` target for every range; longer ones
#: get the ranges their steps select.
ALL_RANGES_UP_TO = 40
#: Window geometry (units): side padding, padding above / below the lines, title bar height,
#: room for the scroll indicator.
PAD_X, PAD_Y, BAR, SCROLLBAR = 0.3, 0.2, 0.4, 0.22
#: Space between the window and the notes, and padding inside a note.
NOTE_GAP, NOTE_PAD = 0.4, 0.22
#: While scrolling, a line fades out over this many line pitches beyond the window's edge.
FADE = 0.75

LinesSpec = int | str | list[int | str]
_END = r"(\d+|/(?:[^/\\]|\\.)+/)"
_ITEM = re.compile(rf"\s*{_END}\s*(?:-\s*{_END}\s*)?(?:,|$)")


def _endpoint(text: str) -> int | str:
    if text.isdigit():
        return int(text)
    pattern = text[1:-1]
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regular expression /{pattern}/: {exc}") from None
    return pattern


def parse_lines(spec: LinesSpec) -> list[tuple[int | str, int | str | None]]:
    """The items of a line spec as ``(start, end)`` endpoints: a line number or a regular
    expression (``/def train/``); ``end`` is ``None`` for a single line. Checks the syntax only."""
    if isinstance(spec, bool):
        raise ValueError(f"invalid line spec {spec!r}")
    if isinstance(spec, int):
        items: list[tuple[int | str, int | str | None]] = [(spec, None)]
    elif isinstance(spec, list):
        if not spec:
            raise ValueError("an empty list selects no lines")
        items = [item for part in spec for item in parse_lines(part)]
    else:
        items, pos = [], 0
        while pos < len(spec):
            m = _ITEM.match(spec, pos)
            if m is None or m.end() == pos:
                raise ValueError(f"invalid line spec {spec!r} (use e.g. 3, \"2-4\", \"1, 5-6\", \"/def train/\" or \"/def train/-/return/\")")
            items.append((_endpoint(m.group(1)), None if m.group(2) is None else _endpoint(m.group(2))))
            pos = m.end()
        if not items:
            raise ValueError(f"invalid line spec {spec!r}")
    if any(isinstance(n, int) and n < 1 for item in items for n in item):
        raise ValueError(f"line numbers start at 1 (got {spec!r})")
    return items


def resolve_lines(spec: LinesSpec, source: list[str], first: int = 1) -> list[int]:
    """The line numbers (sorted, unique) ``spec`` selects in ``source``, whose first line is
    number ``first``. A regular expression selects the first line it matches (an end
    expression: the first match from the start line on)."""
    last = first + len(source) - 1

    def find(end: int | str, start: int) -> int:
        if isinstance(end, int):
            if not first <= end <= last:
                shown = f"only {len(source)} lines" if first == 1 else f"lines {first}-{last}"
                raise ValueError(f"line {end}: the code has {shown}")
            return end
        rx = re.compile(end)
        for k in range(start - first, len(source)):
            if rx.search(source[k]):
                return first + k
        raise ValueError(f"no line matches /{end}/" + (f" from line {start} on" if start > first else ""))

    chosen: set[int] = set()
    for a, b in parse_lines(spec):
        lo = find(a, first)
        hi = lo if b is None else find(b, lo)
        if hi < lo:
            raise ValueError(f"invalid line range in {spec!r}: {hi} comes before {lo}")
        chosen.update(range(lo, hi + 1))
    return sorted(chosen)


def _luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[k : k + 2], 16) / 255 for k in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two ``#RRGGBB`` colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class WalkStep(SceneParams):
    """A step of the walkthrough: ``{lines, note, focus}``; a line spec alone (``"3-7"``, ``12``,
    ``"/def train/"``) is read as ``{lines: ...}``."""

    also_accepts = (str, int, list)

    lines: LinesSpec | None = None
    """Lines to highlight and scroll into view: 12, '3-7', '1, 5-6', [3, 4], '/regex/' (the first
    line it matches), '/def fit/-/return/' (a range), or 'all' (no highlight). None: keep the
    previous step's lines and view."""
    note: str = ""
    """A short annotation shown with this step (beside the lines, or below the window)."""
    focus: bool | float = False
    """Enlarge: the camera moves in on the lines (and the note) during this step; a number is the
    magnification (more than 1, up to 4), true: as close as they fit, up to focus_scale."""

    @model_validator(mode="before")
    @classmethod
    def _from_lines(cls, data: Any) -> Any:
        return {"lines": data} if isinstance(data, (str, int, list)) and not isinstance(data, bool) else data

    @field_validator("lines")
    @classmethod
    def _check_lines(cls, value: Any) -> Any:
        if value is not None and value != "all":
            parse_lines(value)
        return value

    @field_validator("focus")
    @classmethod
    def _check_focus(cls, value: bool | float) -> bool | float:
        if not isinstance(value, bool) and not 1 < value <= 4:
            raise ValueError("a focus magnification is more than 1 and at most 4 (or true: as close as fits)")
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A line spec alone is also a step (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "array", "items": {"type": ["integer", "string"]}}, handler(core_schema)]}


@dataclass(frozen=True)
class _View:
    """What the window shows: the first visible (physical) line, the highlighted rows (``None``:
    no highlight), the step whose note is shown, and the camera of a focus (width and centre;
    ``None``: the whole frame)."""

    offset: int
    chosen: frozenset[int] | None
    note: int | None
    camera: tuple[float, tuple[float, float]] | None = None


class _ViewChange(Animation):
    """Scroll the listing to another offset and/or move the highlight, fading lines at the
    window's edges. Interpolates only the rows that can be visible on the way."""

    def __init__(self, walk: "CodeWalkthrough", old: _View, new: _View, **kwargs: Any) -> None:
        self.walk, self.old, self.new = walk, old, new
        n, view = walk._rows, walk._visible
        lo = max(0, min(old.offset, new.offset) - 1)
        hi = min(n, max(old.offset, new.offset) + view + 1)
        self.rows = range(lo, hi)
        self.old_bands = walk._bands(old.chosen)
        self.new_bands = walk._bands(new.chosen)
        for i in self.rows:  # rows that may come into view: in place, and in the listing
            walk._place_row(i, walk._s)
        walk._include(walk._included() | set(self.rows))
        parts = [walk._listing, self.new_bands]
        if self.old_bands is not self.new_bands:
            parts.append(self.old_bands)
        if walk._thumb is not None:
            parts.append(walk._thumb)
        super().__init__(VGroup(*parts), **kwargs)

    def create_starting_mobject(self) -> Mobject:
        return Mobject()  # nothing to interpolate from: every frame is computed from the views

    def interpolate_mobject(self, alpha: float) -> None:
        a = self.rate_func(alpha)
        w = self.walk
        s = self.old.offset + (self.new.offset - self.old.offset) * a
        w._scroll_to(s, self.rows)
        for i in self.rows:
            e = w._emphasis(self.old, i) * (1 - a) + w._emphasis(self.new, i) * a
            w._set_row_opacity(i, e * w._shown(i, s))
        if self.old_bands is self.new_bands:
            w._shape_bands(self.new.chosen, s, w._band)
        else:
            w._shape_bands(self.old.chosen, s, w._band * (1 - a))
            w._shape_bands(self.new.chosen, s, w._band * a)

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        self.walk._sync_rows(self.new, self.old_bands if self.old_bands is not self.new_bands else None)


@scene("code_walkthrough")
class CodeWalkthrough(NarratedScene):
    """A long listing in a window of fixed height. Step *i* (an entry of ``steps``) plays at beat
    *i* (step 1 with the window): it scrolls so its ``lines`` are in view, highlights them (the
    others dim, a band marks them), shows its ``note`` and, with ``focus``, moves the camera in.
    A step without ``lines`` keeps the view. More steps than beats are spread evenly; later beats
    hold.

    Action targets: ``title``, ``listing`` (the window), ``line<N>`` (a line by its number, with
    its number label; all its pieces when wrapped), ``lines:<a-b>`` and ``note<N>`` (the note of
    step N). Revealing a line scrolls it into view; revealing a note plays its step.
    """

    outro = 0.5
    target_patterns = ("title", "listing", "line<N>", "lines:<a-b>", "note<N>")

    class Params(SceneParams):
        code: str | None = None
        """Inline code; give exactly one of code / path."""
        path: str | None = None
        """Code file in the project; give exactly one of code / path."""
        language: str | None = None
        """Pygments lexer name; default: from the file name, else python."""
        excerpt: str | None = None
        """Show only lines 'a-b' of the code (they keep their numbers; steps use them too)."""
        title: str = ""
        """Window title, above it."""
        steps: list[WalkStep] = []
        """Step i plays at beat i: {lines, note, focus}, or just a line spec ('3-7')."""
        visible: int | None = Field(default=None, ge=3)
        """Lines the window shows at once (default: as many as fit at size)."""
        line_numbers: bool = True
        """Show line numbers."""
        style: str | None = None
        """Pygments style (monokai, dracula, xcode, ...); default: the theme's code_style."""
        font: str | None = None
        """Font family of the listing; default: the theme's font for the `code` role (font_mono)."""
        size: ThemeSize = "caption"
        """Font size of the listing (smaller only to fit the width, never below the readable size: long lines wrap)."""
        wrap: bool = True
        """Wrap long lines (hanging indent) instead of shrinking the listing below size / the readable size."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlight band, the notes' frame and the scroll target."""
        note_position: Literal["auto", "side", "bottom"] = "auto"
        """Where notes go: side (a callout beside the window), bottom (a bar below it; always in a vertical frame), auto (side in 16:9 when the code fits beside them without wrapping, else bottom)."""
        note_size: ThemeSize = "body"
        """Note text size."""
        note_color: ThemeColor = "text"
        """Note text color."""
        focus_scale: float = Field(default=2.0, gt=1, le=4)
        """Largest magnification of focus: true."""
        scrollbar: bool = True
        """Show a scroll indicator when the code is longer than the window."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if (self.code is None) == (self.path is None):
                raise ValueError("give exactly one of 'code' (inline text) or 'path' (a file in the project)")
            if self.style is not None and self.style not in style_names():
                raise ValueError(f"unknown style {self.style!r}; available: {', '.join(style_names())}")
            if self.language is not None:
                from pygments.lexers import get_lexer_by_name
                from pygments.util import ClassNotFound

                try:
                    get_lexer_by_name(self.language)
                except ClassNotFound:
                    raise ValueError(f"unknown language {self.language!r} (a Pygments lexer name, e.g. python)") from None
            if self.excerpt is not None:
                self._excerpt_range()
            if self.code is not None:
                self.check_source(self.code)
            return self

        def _excerpt_range(self) -> tuple[int, int] | None:
            if self.excerpt is None:
                return None
            m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", self.excerpt)
            if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
                raise ValueError(f"excerpt {self.excerpt!r}: use 'a-b' with 1 <= a <= b (e.g. '40-120')")
            return int(m.group(1)), int(m.group(2))

        def source(self, text: str) -> tuple[list[str], int]:
            """The shown lines (tabs expanded, the excerpt applied) and the number of the first."""
            lines = text.rstrip("\n").expandtabs(4).split("\n")
            span = self._excerpt_range()
            if span is None:
                return lines, 1
            a, b = span
            if b > len(lines):
                raise ValueError(f"excerpt {self.excerpt!r}: the code has only {len(lines)} lines")
            return lines[a - 1 : b], a

        def selections(self, text: str) -> list[list[int] | Literal["all"] | None]:
            """Per step: the line numbers it selects, ``"all"`` or ``None`` (keep)."""
            source, first = self.source(text)
            out: list[list[int] | Literal["all"] | None] = []
            for k, step in enumerate(self.steps):
                if step.lines is None or step.lines == "all":
                    out.append(step.lines)
                    continue
                try:
                    out.append(resolve_lines(step.lines, source, first))
                except ValueError as exc:
                    raise ValueError(f"steps[{k}].lines {step.lines!r}: {exc}") from None
            return out

        def check_source(self, text: str) -> None:
            """Raise ``ValueError`` when the excerpt or a step's lines do not fit ``text``."""
            self.selections(text)

    @classmethod
    def _text(cls, params: Any) -> str | None:
        """The code (``None`` when its file cannot be read here)."""
        if params.code is not None:
            return params.code
        try:
            return current_project().asset(params.path).read_text(encoding="utf-8")
        except (VidgenError, OSError, UnicodeDecodeError):
            return None

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``listing``, ``line<N>`` per shown line, ``lines:<a-b>`` (every
        range up to :data:`ALL_RANGES_UP_TO` lines, else the ranges of the steps) and ``note<N>``
        per step with a note. A ``path`` file is read in the active project (no lines without)."""
        text = cls._text(params)
        try:
            source, first = params.source(text) if text is not None else ([], 1)
            picks = params.selections(text) if text is not None else []
        except ValueError:
            source, first, picks = [], 1, []
        names = (["title"] if params.title else []) + ["listing"] + [f"line{n}" for n in range(first, first + len(source))]
        names += [f"lines:{a}-{b}" for a, b in cls._ranges(len(source), first, picks)]
        return names + [f"note{k + 1}" for k, step in enumerate(params.steps) if step.note]

    @staticmethod
    def _ranges(count: int, first: int, picks: list[Any]) -> list[tuple[int, int]]:
        """The ``lines:<a-b>`` ranges: all of them for short listings, else those of the steps."""
        numbers = range(first, first + count)
        if count <= ALL_RANGES_UP_TO:
            return [(a, b) for a in numbers for b in numbers if b > a]
        runs = [(run[0], run[-1]) for pick in picks if isinstance(pick, list) for run in line_runs(pick) if len(run) > 1]
        return list(dict.fromkeys(runs))

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        if params.path is not None:
            path = project.root / params.path
            if not path.is_file():
                return problems + [f"path: file not found: {params.path} (looked for {path})"]
            try:
                params.check_source(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append(f"path: {exc}")
        return problems

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        text = p.code if p.code is not None else self.project.asset(p.path).read_text(encoding="utf-8")
        source, first = p.source(text)
        picks = p.selections(text)
        body = self.safe_area
        title = None
        if p.title:
            header = self.region("header")
            title = fit_text(p.title, header.width, header.height, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
            place(title, header, fit="none", align="center")
            body = body.below(title, gap=0.45)
        notes = [step.note for step in p.steps]
        self._build(source, first, body, notes)
        self._register(source, first, title, picks)
        self._views = self._place_notes(self._plan(picks, first))
        heading = self.find_targets("title")[0] if title is not None else None

        def step(k: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                anims = self._go(self._views[k])
                return anims + (self.entrance(heading) if k == 0 and heading is not None else [])

            return build

        self.reveal([step(k) for k in range(len(self._views))], fraction=0.6, cap=1.0)
        self.finish()

    @property
    def _font(self) -> str:
        """The listing's font family."""
        return self.params.font or self.theme.font_for("code")

    # ----- layout ------------------------------------------------------------------------------

    def _fit(self, source: list[str], width: float, digits: int) -> tuple[float, int | None]:
        """Font size and wrap columns (``None``: no wrapping) for a window ``width`` units wide:
        the requested size if it fits, else smaller down to the target (the readable size, or the
        size giving :data:`TARGET_COLUMNS` columns if larger), else wrapped at the target."""
        p, font = self.params, self._font
        size = float(self.theme.size(p.size))
        floor = readable_size(font) * 1.05  # code is mostly lowercase: as diagram/pie labels
        chrome = 2 * PAD_X + (SCROLLBAR if p.scrollbar else 0.0)
        longest = max((len(line) for line in source), default=1) or 1
        fits = size_for_columns(font, longest, width, digits, chrome)
        if fits >= size:
            return size, None
        target = max(floor, min(size, size_for_columns(font, TARGET_COLUMNS, width, digits, chrome)))
        if fits >= target * 0.999 or not p.wrap or longest <= MIN_COLUMNS:
            return fits, None
        advance = mono_metrics(font)[0]
        columns = int((width - chrome - (NUMBER_GAP if digits else 0.0)) / (advance * target)) - digits
        if columns < MIN_COLUMNS:
            return size_for_columns(font, MIN_COLUMNS, width, digits, chrome), MIN_COLUMNS
        return target, columns

    def _content_width(self, source: list[str], size: float, columns: int | None, digits: int) -> float:
        advance = mono_metrics(self._font)[0]
        longest = max((len(line) for line in source), default=1)
        chars = min(longest, columns) if columns else longest
        return (chars + digits) * advance * size + (NUMBER_GAP if digits else 0.0) + 2 * PAD_X

    def _build(self, source: list[str], first: int, body: Region, notes: list[str]) -> None:
        """Choose size, wrapping and note placement, build the listing, the window and the notes'
        text, and put the lines at offset 0."""
        p, font = self.params, self._font
        digits = len(str(first + len(source) - 1)) if p.line_numbers else 0
        self._mode: Literal["side", "bottom"] | None = None
        area = body
        side_w = min(max(0.3 * body.width, 3.4), 4.8)
        size, columns = self._fit(source, body.width, digits)
        if any(notes):
            side = self._fit(source, body.width - side_w - NOTE_GAP, digits)
            if not self.is_portrait and (p.note_position == "side" or (p.note_position == "auto" and side[1] is None)):
                self._mode = "side"
                size, columns = side
                area = Region(body.x0, body.y0, body.x1 - side_w - NOTE_GAP, body.y1)
            else:
                self._mode = "bottom"
        # the notes' text first: a bottom bar takes height from the window
        estimate = self._content_width(source, size, columns, digits) + (SCROLLBAR if p.scrollbar else 0.0)
        note_w = side_w if self._mode == "side" else max(min(estimate, body.width), min(body.width, 7.0))
        inner_w = note_w - 2 * NOTE_PAD - (0.0 if self._mode == "side" else 0.25)
        max_h = body.height * (0.8 if self._mode == "side" else 0.3)
        self._note_texts = {
            k: readable_text(note, Region(0, 0, inner_w, max_h), size=p.note_size, color=p.note_color, align="left")
            for k, note in enumerate(notes)
            if note
        }
        bar_h = max((t.height for t in self._note_texts.values()), default=0.0) + 2 * NOTE_PAD
        if self._mode == "bottom":
            area = Region(body.x0, body.y0 + bar_h + NOTE_GAP, body.x1, body.y1)
        self._note_w, self._bar_h = note_w, bar_h

        # the listing, built once at its final size
        shown, groups = wrap_code(source, columns) if columns else (source, [[i] for i in range(len(source))])
        language = p.language
        if language is None and p.path is not None:
            from pygments.lexers import get_lexer_for_filename
            from pygments.util import ClassNotFound

            try:
                language = get_lexer_for_filename(p.path).aliases[0]
            except ClassNotFound:
                language = "text"
        with text_canvas(shown, size):
            listing = Code(
                code_string="\n".join(shown),
                language=language or "python",
                formatter_style=p.style or self.theme.code_style,
                add_line_numbers=p.line_numbers,
                line_numbers_from=first,
                background="rectangle",
                paragraph_config={"font": font, "font_size": size},
            )
        wrapped = len(shown) != len(source)
        if wrapped and p.line_numbers:
            renumber(self, listing, groups, size, font, first)
        listing.remove(listing.background)  # the window is drawn separately, of the view's height
        lines = listing.code_lines
        numbers = listing.line_numbers if p.line_numbers else None
        content = listing
        room = area.width - 2 * PAD_X - (SCROLLBAR if p.scrollbar else 0.0)
        if content.width > room:  # the size estimate was a little off: never overflow
            content.scale(room / content.width)
        ys = line_centers(lines, None if wrapped else numbers)
        rows = len(lines)
        pitch = ys[0] - ys[1] if rows > 1 else mono_metrics(font)[1] * size
        fit_rows = max(1, int((area.height - BAR - 2 * PAD_Y) / pitch + 1e-6))
        visible = min(rows, fit_rows, p.visible or rows)
        if p.visible is not None and p.visible > fit_rows and rows > fit_rows:
            log.warning("scene '%s': only %d lines fit the window (visible: %d)", self.spec.id, fit_rows, p.visible)
        if fit_rows < 3:
            log.warning("scene '%s': the window shows only %d lines; shorten the notes or the title", self.spec.id, fit_rows)
        scrolls = p.scrollbar and rows > visible
        w = content.width + 2 * PAD_X + (SCROLLBAR if scrolls else 0.0)
        h = BAR + 2 * PAD_Y + visible * pitch
        if self._mode == "side":
            total = w + NOTE_GAP + side_w
            x0 = max(body.x0, body.center[0] - total / 2)
            cy = body.center[1]
            window = Region(x0, cy - h / 2, x0 + w, cy + h / 2)
        elif self._mode == "bottom":
            top = body.center[1] + (h + NOTE_GAP + bar_h) / 2
            window = Region(body.center[0] - w / 2, top - h, body.center[0] + w / 2, top)
        else:
            window = Region(area.center[0] - w / 2, area.center[1] - h / 2, area.center[0] + w / 2, area.center[1] + h / 2)

        frame = RoundedRectangle(width=w, height=h, corner_radius=0.15)
        frame.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color("dim"), width=1)
        frame.move_to(window.center)
        dots = VGroup(*[
            Dot(radius=0.06, color=self.theme.color(token)).move_to([window.x0 + 0.3 + 0.22 * k, window.y1 - BAR / 2, 0])
            for k, token in enumerate(("accent", "highlight", "tertiary"))
        ])
        view_top = window.y1 - BAR - PAD_Y
        content.shift(UP * (view_top - pitch / 2 - ys[0]) + RIGHT * (window.x0 + PAD_X - content.get_left()[0]))
        shift = view_top - pitch / 2 - ys[0]
        content.set_z_index(2)
        # the listing stays in the scene as one Code (the layout dump reads it as code); rows out of
        # view are taken out of its paragraphs, so they are not drawn and targets know it
        self._window, self._frame, self._dots, self._listing = window, frame, dots, listing
        self._content_left = float(content.get_left()[0])
        self._lines = list(lines.submobjects)
        self._numbers = list(numbers.submobjects) if numbers is not None else None
        labels = [str(first + k) if j == group[0] else "" for k, group in enumerate(groups) for j in group]
        self._paragraphs = [(lines, self._lines, shown)] + ([(numbers, self._numbers, labels)] if numbers is not None else [])
        self._groups = groups
        self._row_s = [0.0] * len(ys)
        self._y0 = [y + shift for y in ys]
        self._pitch, self._rows, self._visible = pitch, rows, visible
        self._view_top, self._view_bottom = view_top, view_top - visible * pitch
        self._s = 0.0
        self._band_x = (self._content_left - 0.12, window.x1 - (SCROLLBAR if scrolls else PAD_X / 2))
        self._band_groups: dict[frozenset[int] | None, VGroup] = {}
        self._readable_colors()
        self._band = self._band_opacity()
        self._track = self._thumb = None
        if scrolls:
            x = window.x1 - SCROLLBAR / 2 - 0.04
            self._track = Line([x, view_top, 0], [x, self._view_bottom, 0], stroke_width=2, color=self.theme.color("dim"))
            self._track.set_stroke(opacity=0.35)
            length = view_top - self._view_bottom
            self._thumb_h = max(0.3, length * visible / rows)
            self._thumb = RoundedRectangle(width=0.07, height=self._thumb_h, corner_radius=0.035, stroke_width=0)
            self._thumb.set_fill(self.theme.color("dim"), opacity=0.9).set_x(x)
            VGroup(self._track, self._thumb).set_z_index(2)
            self._move_thumb(0.0)

    def _readable_colors(self) -> None:
        """Syntax colours that would contrast less than :data:`INK_RATIO` with the window or with
        the faintest highlight band (a Pygments style that does not suit the theme) are mixed
        towards the theme's text colour."""
        surface, text = self.theme.color("surface"), self.theme.color("text")
        behind = (surface, mix_colors(self.theme.color(self.params.highlight_color), surface, BAND_MIN))

        def readable(ink: str) -> bool:
            return all(_contrast(ink, b) >= INK_RATIO for b in behind)

        fixed: dict[str, str] = {}
        for row in self._lines:
            for m in row.family_members_with_points():
                ink = m.get_fill_color().to_hex()
                if ink not in fixed:
                    mixes = (mix_colors(text, ink, t) for t in (0.2, 0.4, 0.6, 0.8))
                    fixed[ink] = ink if readable(ink) else next((c for c in mixes if readable(c)), text)
                if fixed[ink] != ink:
                    m.set_fill(fixed[ink])

    def _band_opacity(self) -> float:
        """The band's opacity: :data:`BAND`, or less (down to :data:`BAND_MIN`) while a colour of
        the listing would contrast less than 4.5:1 with it (light themes)."""
        surface = self.theme.color("surface")
        color = self.theme.color(self.params.highlight_color)
        inks = {m.get_fill_color().to_hex() for row in self._lines for m in row.family_members_with_points()}
        for opacity in (BAND, 0.1, 0.085):
            band = mix_colors(color, surface, opacity)
            if all(_contrast(ink, band) >= 4.5 for ink in inks):
                return opacity
        return BAND_MIN

    def _register(self, source: list[str], first: int, title: Mobject | None, picks: list[Any]) -> None:
        """Targets, registered at full opacity (before any dimming)."""
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=UP * 0.12)])
        chrome = [self._frame, self._dots] + ([self._track, self._thumb] if self._track is not None else [])
        self._window_target = self.target("listing", VGroup(*chrome, self._listing), entrance=lambda: self._go(self._views[0]))
        numbers = range(first, first + len(source))

        def rows_of(a: int, b: int) -> list[int]:
            return [j for n in range(a, b + 1) for j in self._groups[n - first]]

        def parts(rows: list[int]) -> VGroup:
            return VGroup(*[m for j in rows for m in self._row_parts(j)])

        def bring(rows: list[int]) -> Callable[[], list[Animation]]:
            return lambda: self._bring(rows)

        for n in numbers:
            self.target(f"line{n}", parts(rows_of(n, n)), entrance=bring(rows_of(n, n)))
        for a, b in self._ranges(len(source), first, picks):
            self.target(f"lines:{a}-{b}", parts(rows_of(a, b)), entrance=bring(rows_of(a, b)))

    def _plan(self, picks: list[list[int] | Literal["all"] | None], first: int) -> list[_View]:
        """The view of every step (offsets chosen so each step's lines are in view; cameras are
        added with the notes)."""
        views: list[_View] = []
        now = _View(0, None, None)
        for k, (step, pick) in enumerate(zip(self.params.steps, picks, strict=True)):
            chosen, offset = now.chosen, now.offset
            if pick == "all":
                chosen = None
            elif pick is not None:
                chosen = frozenset(j for n in pick for j in self._groups[n - first])
                offset = self._offset_for(sorted(chosen), now.offset)
            now = _View(offset, chosen, k if step.note else None)
            views.append(now)
        return views or [now]

    def _offset_for(self, rows: list[int], current: int) -> int:
        """The offset that shows ``rows``: the current one if they are in view (with a line of
        context when there is room), else one that centres them (their start, if they are longer
        than the window)."""
        lo, hi, view = rows[0], rows[-1], self._visible
        span = hi - lo + 1
        margin = 1 if span + 2 <= view else 0
        top = max(0, self._rows - view)
        if current <= max(0, lo - margin) and min(self._rows - 1, hi + margin) <= current + view - 1:
            return current
        offset = lo - (view - span) // 2 if span <= view else lo
        return min(max(offset, 0), top)

    def _place_notes(self, views: list[_View]) -> list[_View]:
        """Build every step's note and the camera of its focus; returns the views with cameras.
        A note goes beside the window at its lines (side) or in a bar below it (bottom); in a
        focus step it is a card under the enlarged lines instead."""
        self._notes: dict[int, VGroup] = {}
        out: list[_View] = []
        for k, view in enumerate(views):
            step = self.params.steps[k] if k < len(self.params.steps) else None
            text = self._note_texts.get(k)
            if step is not None and step.focus is not False:
                camera, card = self._focus(view, step.focus, text)
                if camera is not None:
                    view = replace(view, camera=camera)
                    if card is not None:
                        self._notes[k] = card
            if text is not None and k not in self._notes:
                self._notes[k] = self._side_note(view, text) if self._mode == "side" else self._bottom_note(text)
            if k in self._notes:
                self.target(f"note{k + 1}", self._notes[k], entrance=lambda k=k: self._go(self._views[k]))
            out.append(view)
        return out

    def _card(self, text: Mobject, width: float, height: float) -> VGroup:
        """A note card around ``text`` (left aligned), with an accent bar on its left."""
        color = self.theme.color(self.params.highlight_color)
        box = RoundedRectangle(width=width, height=height, corner_radius=0.12)
        box.set_fill(self.theme.color("surface"), opacity=1).set_stroke(color, width=2)
        accent = RoundedRectangle(width=0.08, height=height - 2 * NOTE_PAD, corner_radius=0.04, stroke_width=0)
        accent.set_fill(color, opacity=1).move_to([box.get_left()[0] + NOTE_PAD + 0.04, 0, 0])
        left = accent.get_right()[0] + 0.17
        place(text, Region(left, -height / 2 + NOTE_PAD, width / 2 - NOTE_PAD, height / 2 - NOTE_PAD), fit="none", align="left")
        return VGroup(box, accent, text)

    def _bottom_note(self, text: Mobject) -> VGroup:
        win = self._window
        card = self._card(text, self._note_w, self._bar_h)
        return card.move_to([win.center[0], win.y0 - NOTE_GAP - self._bar_h / 2, 0])

    def _side_note(self, view: _View, text: Mobject) -> VGroup:
        """A callout beside the window, level with the view's highlighted lines, with a pointer."""
        color = self.theme.color(self.params.highlight_color)
        win = self._window
        band = self._band_center(view)
        h = text.height + 2 * NOTE_PAD
        y = win.center[1] if band is None or h > win.height else min(max(band, win.y0 + h / 2), win.y1 - h / 2)
        box = RoundedRectangle(width=self._note_w, height=h, corner_radius=0.12)
        box.set_fill(self.theme.color("surface"), opacity=1).set_stroke(color, width=2)
        box.move_to([win.x1 + NOTE_GAP + self._note_w / 2, y, 0])
        place(text, Region(box.get_left()[0] + NOTE_PAD, y - h / 2, box.get_right()[0] - NOTE_PAD, y + h / 2), fit="none", align="left")
        group = VGroup(box, text)
        if band is not None:
            joint = min(max(band, y - h / 2 + 0.2), y + h / 2 - 0.2)
            group.add(Line([win.x1, band, 0], [box.get_left()[0], joint, 0], stroke_width=2, color=color), Dot([win.x1, band, 0], radius=0.05, color=color))
        return group

    # ----- state ---------------------------------------------------------------------------------

    def _row_parts(self, i: int) -> list[Mobject]:
        """The mobjects of physical row ``i``: its code and its number label."""
        return [self._lines[i]] + ([self._numbers[i]] if self._numbers is not None else [])

    def _showing(self, view: _View) -> set[int]:
        """The rows ``view`` shows (in the window, and not hidden around a focus)."""
        return {i for i in range(self._rows) if self._shown(i, view.offset) > 0 and self._emphasis(view, i) > 0}

    def _included(self) -> set[int]:
        present = {id(m) for m in self._paragraphs[0][0].submobjects}
        return {i for i, row in enumerate(self._lines) if id(row) in present}

    @staticmethod
    def _emphasis(view: _View, i: int) -> float:
        """Opacity of row ``i`` in ``view``: full when highlighted (or nothing is), else dimmed;
        hidden around a focus (the note card may sit over those rows)."""
        if view.chosen is None or i in view.chosen:
            return 1.0
        return 0.0 if view.camera is not None else DIMMED

    def _shown(self, i: int, offset: float) -> float:
        """How much of row ``i`` shows at ``offset``: 1 inside the window, fading beyond it."""
        p = i - offset
        beyond = max(-p, p - (self._visible - 1), 0.0)
        return max(0.0, 1.0 - beyond / FADE)

    def _set_row_opacity(self, i: int, opacity: float) -> None:
        for m in self._row_parts(i):
            m.set_opacity(opacity)

    def _row_y(self, i: int, offset: float) -> float:
        return self._y0[i] + offset * self._pitch

    def _scroll_to(self, offset: float, rows: range) -> None:
        """Move ``rows`` (those that can show) to ``offset``, and the scroll indicator with them."""
        for i in rows:
            self._place_row(i, offset)
        self._s = offset
        self._move_thumb(offset)

    def _place_row(self, i: int, offset: float) -> None:
        """Put row ``i`` where it is at ``offset`` (rows move only when they can be seen)."""
        if offset != self._row_s[i]:
            for m in self._row_parts(i):
                m.shift(UP * (offset - self._row_s[i]) * self._pitch)
            self._row_s[i] = offset

    def _include(self, rows: set[int]) -> None:
        """Make ``rows`` the rows of the listing in the scene (in order)."""
        order = sorted(rows)
        for paragraph, all_rows, texts in self._paragraphs:
            paragraph.submobjects = [all_rows[i] for i in order]
            # what the layout dump reports as its text (lint sizes text by its characters)
            paragraph.lines_text.original_text = "\n".join(texts[i] for i in order)

    def _move_thumb(self, offset: float) -> None:
        if self._thumb is None:
            return
        travel = self._view_top - self._view_bottom - self._thumb_h
        top = self._view_top - travel * offset / max(1, self._rows - self._visible)
        self._thumb.move_to([self._thumb.get_x(), top - self._thumb_h / 2, 0])

    def _bands(self, chosen: frozenset[int] | None) -> VGroup:
        """The band shapes of a selection (one per run of rows), made once per selection."""
        if chosen not in self._band_groups:
            runs = line_runs(sorted(chosen)) if chosen else []
            group = VGroup(*[VGroup(VMobject(stroke_width=0), VMobject(stroke_width=0)) for _ in runs]).set_z_index(1)
            self._band_groups[chosen] = group
            self._shape_bands(chosen, self._s, 0.0)
        return self._band_groups[chosen]

    def _shape_bands(self, chosen: frozenset[int] | None, offset: float, opacity: float) -> None:
        """Lay the bands of ``chosen`` over their rows at ``offset``, cut at the window's edges
        (``opacity``: of the band; its edge bar is opaque at the full band opacity)."""
        group = self._bands(chosen)
        x0, x1 = self._band_x
        color = self.theme.color(self.params.highlight_color)
        for (band, bar), run in zip(group, line_runs(sorted(chosen)) if chosen else [], strict=True):
            hi = min(self._row_y(run[0], offset) + self._pitch / 2, self._view_top)
            lo = max(self._row_y(run[-1], offset) - self._pitch / 2, self._view_bottom)
            visible = hi - lo > 0.01
            hi = max(hi, lo + 0.001)
            band.set_points_as_corners([[x0, hi, 0], [x1, hi, 0], [x1, lo, 0], [x0, lo, 0], [x0, hi, 0]])
            band.set_fill(color, opacity=opacity if visible else 0.0)
            bar.set_points_as_corners([[x0, hi, 0], [x0 + 0.05, hi, 0], [x0 + 0.05, lo, 0], [x0, lo, 0], [x0, hi, 0]])
            bar.set_fill(color, opacity=opacity / self._band if visible else 0.0)

    def _band_center(self, view: _View) -> float | None:
        """Middle of the highlighted rows in view (``None`` without any)."""
        rows = self._rows_in_view(view)
        if not rows:
            return None
        return (self._row_y(rows[0], view.offset) + self._row_y(rows[-1], view.offset)) / 2

    def _rows_in_view(self, view: _View) -> list[int]:
        if not view.chosen:
            return []
        return [i for i in sorted(view.chosen) if view.offset <= i < view.offset + self._visible]

    def _apply(self, view: _View) -> None:
        """Jump to ``view`` without animation (before the window appears)."""
        self._scroll_to(float(view.offset), range(self._rows))
        self._include(self._showing(view))
        for i in range(self._rows):
            self._set_row_opacity(i, self._emphasis(view, i) * self._shown(i, view.offset))
        self._shape_bands(view.chosen, view.offset, self._band)

    def _sync_rows(self, view: _View, old_bands: VGroup | None) -> None:
        """After a change: only rows that show stay in the listing; replaced bands go."""
        self._include(self._showing(view))
        if old_bands is not None and id(old_bands) in {id(m) for m in self.get_mobject_family_members()}:
            self.remove(old_bands)

    def _bring(self, rows: list[int]) -> list[Animation]:
        """Scroll so ``rows`` are in view (an action revealing a line)."""
        base = self._now if self.is_shown(self._window_target) else self._views[0]
        if base.camera is not None:  # leave the focus: its card belongs to its own lines
            base = replace(base, camera=None, note=None)
        return self._go(replace(base, offset=self._offset_for(rows, base.offset)))

    def _go(self, view: _View) -> list[Animation]:
        """The animations from the current view to ``view`` (the window's entrance first)."""
        anims: list[Animation] = []
        now = getattr(self, "_now", None)
        if now is None or not self.is_shown(self._window_target):
            self._apply(view)
            chrome = [self._frame, self._dots] + ([self._track, self._thumb] if self._track is not None else [])
            anims.append(FadeIn(VGroup(*chrome, self._bands(view.chosen), self._listing), shift=UP * 0.12))
            now = _View(view.offset, view.chosen, None, view.camera)
        elif (view.offset, view.chosen, view.camera is None) != (now.offset, now.chosen, now.camera is None):
            anims.append(_ViewChange(self, now, view))
        if view.note != now.note:
            old, new = self._notes.get(now.note), self._notes.get(view.note)
            if old is not None and self.on_screen_parts(old):
                anims.append(FadeOut(old))
            if new is not None and not self.on_screen_parts(new):
                anims.append(FadeIn(new, shift=(LEFT if self._mode == "side" else UP) * 0.12))
        if view.camera != getattr(self, "_camera_at", None):
            width, center = view.camera or (float(config.frame_width), (0.0, 0.0))
            anims.append(MoveCamera(self, width, np.array([*center, 0.0])))
            self._camera_at = view.camera
        self._now = view
        return anims

    def _focus(self, view: _View, focus: bool | float, text: Mobject | None) -> tuple[tuple[float, tuple[float, float]] | None, VGroup | None]:
        """Camera (width, centre) that enlarges the view's highlighted lines, leaving room under
        them for the note card (built at 1/magnification, so it reads at its normal size), and
        that card. ``(None, None)`` when there is nothing to enlarge."""
        rows = self._rows_in_view(view)
        if not rows:
            log.warning("scene '%s': focus without highlighted lines in view; the camera stays", self.spec.id)
            return None, None
        inked = [self._lines[i] for i in rows if len(self._lines[i])]  # the code itself, not the numbers
        x0 = min((m.get_left()[0] for m in inked), default=self._content_left) - 0.25
        x1 = max((m.get_right()[0] for m in inked), default=x0 + 1.0) + 0.25
        y1 = self._row_y(rows[0], view.offset) + self._pitch / 2
        y0 = self._row_y(rows[-1], view.offset) - self._pitch / 2
        fw, fh = float(config.frame_width), float(config.frame_height)
        limit = self.params.focus_scale if focus is True else float(focus)
        card_w = card_h = gap = 0.0
        if text is not None:
            card_w, card_h, gap = text.width + 2 * NOTE_PAD + 0.25, text.height + 2 * NOTE_PAD, 0.3
        # the card takes card_h / mag of the view's fh / mag: mag <= (0.84 fh - card_h - gap) / lines
        mag = min(limit, 0.84 * fw / (x1 - x0), (0.84 * fh - card_h - gap) / (y1 - y0))
        if mag < 1.05:
            log.warning("scene '%s': focus: the lines already fill the frame; the camera stays", self.spec.id)
            return None, None
        w, h = fw / mag, fh / mag
        stack = (y1 - y0) + (card_h + gap) / mag
        cx = min(max((x0 + x1) / 2, -fw / 2 + w / 2), fw / 2 - w / 2)
        cy = min(max(y1 - stack / 2, -fh / 2 + h / 2), fh / 2 - h / 2)
        titles = self.find_targets("title")
        if titles:  # never cut through the title: below it if the lines still fit, else all of it
            bottom, top = titles[0].mobject.get_bottom()[1] - 0.1, titles[0].mobject.get_top()[1] + 0.1
            if bottom < cy + h / 2 < top:
                cy = bottom - h / 2 if bottom - h <= y1 - stack else min(top - h / 2, fh / 2 - h / 2)
        card = None
        if text is not None:
            card = self._card(text, card_w, card_h).scale(1 / mag)
            left = min(max(x0, cx - w / 2 + 0.1 * w), cx + w / 2 - 0.05 * w - card.width)
            card.move_to([left + card.width / 2, y0 - gap / mag - card.height / 2, 0])
        return (round(w, 6), (round(cx, 6), round(cy, 6))), card
