"""``terminal``: a terminal window in which commands are typed and their output appears, step by
step with the beats. The commands and their output are the author's: schu-video-generator never runs anything."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.api import *

from .code import (
    BAND_OPACITIES,
    CodeListing,
    LineSpec,
    Run,
    lex_code,
    lexer_name,
    listing_bands,
    mono_metrics,
    parse_line_spec,
    readable_band,
    style_names,
    text_canvas,
)
from .pie import window as during

#: Seconds of the parts of a step: the window coming in, a ``clear``, the pause between a prompt
#: appearing and typing, the pause after Enter, and per output row (within the bounds).
INTRO, CLEAR, PROMPT_PAUSE, ENTER_PAUSE = 0.5, 0.3, 0.25, 0.3
ROW_TIME, OUTPUT_MIN, OUTPUT_MAX = 0.06, 0.1, 0.8
#: Shortest typing of a command (seconds), however short it is.
MIN_TYPING = 0.3
#: Share of a step's slot of the beat its animation may take (``play_steps``' fraction).
FRACTION = 0.9
#: Opacity of the block cursor (theme ``text`` colour).
CURSOR_OPACITY = 0.7
#: Space between the code and the terminal (units).
PANE_GAP = 0.4


def _text_lines(text: str) -> list[str]:
    """The lines of a command or an output as drawn (trailing newlines and spaces dropped, tabs
    expanded to 4)."""
    return [line.rstrip() for line in text.rstrip("\n").expandtabs(4).split("\n")]


class TerminalStep(SceneParams):
    """A step of the session: ``{command, output, clear, output_color}``; a string alone is a
    command."""

    also_accepts = (str,)

    command: str | None = None
    """What is typed at the prompt (several lines are typed one after the other)."""
    output: str | None = None
    """What the command prints, written by you (vidgen runs nothing); shown after the command."""
    clear: bool = False
    """Clear the screen before this step: it starts a new page at the top of the window."""
    output_color: ThemeColor | None = None
    """Colour of the output (e.g. an error); default: the style's colour for program output."""

    @model_validator(mode="before")
    @classmethod
    def _from_command(cls, data: Any) -> Any:
        return {"command": data} if isinstance(data, str) else data

    @model_validator(mode="after")
    def _check(self) -> "TerminalStep":
        if self.command is None and self.output is None:
            raise ValueError("give a command, an output (what a running program prints next) or both")
        for name in ("command", "output"):
            text = getattr(self, name)
            if text is not None and not text.strip():
                raise ValueError(f"{name} is empty (leave it out instead)")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A command alone is also a step (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


class TerminalCode(SceneParams):
    """The code beside the terminal: ``{code | path, language, highlight}``."""

    code: str | None = None
    """Inline code; give exactly one of code / path."""
    path: str | None = None
    """Code file in the project; give exactly one of code / path."""
    language: str | None = None
    """Pygments lexer name; default: from the file name, else python."""
    highlight: LineSpec | None = None
    """Lines to mark (the others dim): 3, '2-4', '1, 5-6' or [1, 4]."""

    @model_validator(mode="after")
    def _check(self) -> "TerminalCode":
        if (self.code is None) == (self.path is None):
            raise ValueError("give exactly one of 'code' (inline text) or 'path' (a file in the project)")
        _check_lexer(self.language)
        if self.highlight is not None:
            parse_line_spec(self.highlight)
            if self.code is not None:
                self.check_lines(self.code)
        return self

    def check_lines(self, text: str) -> None:
        """Raise ``ValueError`` when ``highlight`` names a line past the end of ``text``."""
        n = len(text.rstrip("\n").split("\n"))
        if self.highlight is not None and any(k > n for k in parse_line_spec(self.highlight)):
            raise ValueError(f"highlight {self.highlight!r}: the code has only {n} lines")


def _check_lexer(language: str | None) -> None:
    if language is None:
        return
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound

    try:
        get_lexer_by_name(language)
    except ClassNotFound:
        raise ValueError(f"unknown language {language!r} (a Pygments lexer name, e.g. bash or python)") from None


# ----- the session as rows (no manim) -------------------------------------------------------------


@dataclass(frozen=True)
class SessionRow:
    """A row of a terminal page as typed and printed: its text, its Pygments runs, what it is
    (``command``, ``output`` or ``end``: the prompt waiting after the last command), the step and
    the line of the command / output it is (0-based) and, for a command, where typing starts
    (after the prompt)."""

    text: str
    runs: list[Run]
    kind: str
    step: int
    line: int
    typed_from: int = 0


def session_pages(steps: Sequence[TerminalStep], prompt: str, language: str) -> list[list[SessionRow]]:
    """The rows of every page of the session (a step with ``clear`` starts a new page): a
    command's first line after the prompt, its other lines as typed, the output's lines, and the
    prompt again after the last step when it has a command (a last step with only output is a
    program still running)."""
    from pygments.token import Generic, Text

    pages: list[list[SessionRow]] = [[]]
    lead = f"{prompt} " if prompt else ""
    for k, step in enumerate(steps):
        if step.clear and k:
            pages.append([])
        rows = pages[-1]
        if step.command is not None:
            lines = _text_lines(step.command)
            for j, (line, runs) in enumerate(zip(lines, lex_code(lines, language))):
                head = [(prompt, Generic.Prompt), (" ", Text)] if j == 0 and prompt else []
                rows.append(SessionRow((lead if j == 0 else "") + line, head + runs, "command", k, j, len(lead) if j == 0 else 0))
        if step.output is not None:
            for j, line in enumerate(_text_lines(step.output)):
                rows.append(SessionRow(line, [(line, Generic.Output)] if line else [], "output", k, j))
    if steps[-1].command is not None:
        # a blank last line would be dropped by Manim's Code: the cursor's line keeps a space
        pages[-1].append(SessionRow(prompt or " ", [(prompt or " ", Generic.Prompt)], "end", len(steps) - 1, 0))
    return pages


def output_line_numbers(step: TerminalStep) -> list[int]:
    """The 1-based lines of a step's output that show something (a blank line is no target)."""
    return [j for j, line in enumerate(_text_lines(step.output), 1) if line.strip()] if step.output is not None else []


# ----- the scene -------------------------------------------------------------------------------------

#: An item of the session: ``("cmd", step)`` (the command typed) or ``("out", step)`` (its output).
Item = tuple[str, int]


@dataclass
class _Segment:
    """A piece of a page drawn as its own text (a prompt, a row of a command or of an output);
    it goes into the page's window once shown. ``cells``: the (row, column) of each glyph (empty
    when Pango drew the piece with another number of glyphs than characters)."""

    text: Mobject
    page: int
    glyphs: list[VMobject]
    cells: list[tuple[int, int]]


@dataclass
class _State:
    """What the terminal shows: the page in its window (``None``: none yet), the items done,
    the steps whose prompt shows, and whether the prompt after the last step does."""

    page: int | None = None
    done: set[Item] = field(default_factory=set)
    prompts: set[int] = field(default_factory=set)
    end: bool = False

    def copy(self) -> "_State":
        return _State(self.page, set(self.done), set(self.prompts), self.end)


@dataclass
class _Schedule:
    """A planned stretch of the session in seconds: glyphs that appear (``shows``), cursor
    ``moves`` (``None`` hides it), the ``segments`` shown, the window's opening (its start, when
    it opens here), the page cleared (``cleared``: its time and segments) and the state after."""

    seconds: float
    shows: list[tuple[float, list[VMobject]]]
    moves: list[tuple[float, np.ndarray | None]]
    segments: list[_Segment]
    state: _State
    opening: float | None = None
    cleared: tuple[float, list[_Segment]] | None = None


def _run_time(d: float, steps: int, cap: float) -> float:
    """The run time :meth:`NarratedScene.play_steps` gives each of ``steps`` steps in ``d``
    seconds with ``cap`` and :data:`FRACTION` (its formula)."""
    frame = 1 / config.frame_rate
    groups = min(max(steps, 1), max(1, int(d / frame + 1e-9)))
    return max(min(cap, FRACTION * d / groups), frame)


@scene("terminal")
class Terminal(CodeListing):
    """A terminal window: step *i* plays at beat *i*: its command is typed at the prompt (a block
    cursor moves along), then its output appears row by row and the prompt comes back. More
    steps than beats are spread evenly; later beats hold. ``{reveal: output2, at: "@passes"}``
    shows an output on a spoken word (``command2`` types a command on one): the scene then
    leaves it to the action. ``code`` puts a code listing beside the terminal (above it in a
    vertical frame); a ``code`` scene before can carry its listing into it (``carry: ["listing
    -> code"]``).

    Action targets: ``title``, ``terminal`` (the window), ``code`` and ``code.line<K>`` (the
    listing beside it), ``command<N>``, ``output<N>`` and ``output<N>.line<K>`` (step N's).
    """

    outro = 0.5
    target_patterns = ("title", "terminal", "code", "code.line<K>", "command<N>", "output<N>", "output<N>.line<K>")

    class Params(SceneParams):
        steps: list[TerminalStep] = Field(min_length=1)
        """The session in order: each a command (a string) or {command, output, clear, output_color}; step i plays at beat i."""
        prompt: str = "$"
        """The prompt before each command ('' for none), e.g. '>>>' or 'PS C:\\>'."""
        language: str = "bash"
        """Pygments lexer of the commands (bash, powershell, pycon, text, ...)."""
        typing_speed: float = Field(18.0, gt=0, le=200)
        """Characters typed per second (a command too long for its beat is typed faster)."""
        code: TerminalCode | None = None
        """A code listing beside the terminal (above it in a vertical frame): {code | path, language, highlight}."""
        title: TranslatableStr = ""
        """Title above the window(s)."""
        prompt_color: ThemeColor = "accent"
        """Colour of the prompt."""
        line_numbers: bool = True
        """Line numbers of the code beside the terminal."""
        style: str | None = None
        """Pygments style (monokai, dracula, xcode, ...) of the terminal and the code; default: the theme's code_style."""
        font: str | None = None
        """Font family; default: the theme's font for the `code` role (font_mono, JetBrains Mono NL)."""
        size: ThemeSize = "caption"
        """Starting font size (scaled to fill the frame, up to 1.5x); the terminal and the code share one size."""
        highlight_color: ThemeColor = "highlight"
        """Colour of the band behind the code's highlighted lines."""
        wrap: bool = True
        """Wrap long lines (hanging indent) instead of shrinking the text below size / the readable minimum."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if self.style is not None and self.style not in style_names():
                raise ValueError(f"unknown style {self.style!r}; available: {', '.join(style_names())}")
            _check_lexer(self.language)
            if "\n" in self.prompt:
                raise ValueError("prompt: one line only")
            if self.steps[0].clear:
                raise ValueError("steps[0].clear: the first step starts on an empty screen already (drop clear)")
            return self

    # ----- names, steps and checks (from the params) ------------------------------------------

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``terminal``, ``code`` and ``code.line<K>`` (with ``code``; a
        ``path`` file is read in the active project), then per step ``command<N>``, ``output<N>``
        and ``output<N>.line<K>`` (its lines that are not blank)."""
        names = (["title"] if params.title else []) + ["terminal"]
        if params.code is not None:
            names += ["code"] + [f"code.line{k}" for k in range(1, len(cls._pane_lines(params.code)) + 1)]
        for n, step in enumerate(params.steps, 1):
            names += [f"command{n}"] if step.command is not None else []
            if step.output is not None:
                names += [f"output{n}"] + [f"output{n}.line{k}" for k in output_line_numbers(step)]
        return names

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """One per step: its command (else its output), an error when its output shows one."""
        def result(step: TerminalStep) -> str | None:
            return "error" if step.output is not None and has_error_text(_text_lines(step.output)) else None

        return [RevealStep(f"command{n}" if s.command is not None else f"output{n}", result(s)) for n, s in enumerate(params.steps, 1)]

    @staticmethod
    def _pane_lines(pane: TerminalCode, project: Any = None) -> list[str]:
        """The lines of the code beside the terminal (none when its file cannot be read here)."""
        text = pane.code
        if text is None:
            try:
                text = (project or current_project()).asset(pane.path).read_text(encoding="utf-8")
            except (VidgenError, OSError, UnicodeDecodeError):
                return []
        return text.rstrip("\n").expandtabs(4).split("\n")

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super(CodeListing, cls).validate_project(params, project)   # not code's: no code / path here
        pane = params.code
        if pane is not None and pane.path is not None:
            path = project.root / pane.path
            if not path.is_file():
                return problems + [f"code.path: file not found: {pane.path} (looked for {path})"]
            try:
                pane.check_lines(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append(f"code.path: {exc}")
        return problems

    # ----- construct -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)   # header band, 1.3x in a vertical frame
            body = body.below(title, gap=0.45)
        rows = session_pages(p.steps, p.prompt, p.language)
        pane_lines = type(self)._pane_lines(p.code, self.project) if p.code is not None else []
        layouts = [False, True] if pane_lines and not self.is_portrait else [bool(pane_lines)]
        stacked, pages, groups, pane, pane_rows = max((self._fit(body, rows, pane_lines, s) for s in layouts), key=lambda fit: fit[1][0].fit_scale)
        self._frame = self._window(pages)
        self._place(pages, pane, stacked, *self._areas(body, rows, pane_lines, stacked))
        self._rows, self._groups, self._pages = rows, groups, pages
        self._page_of = {row.step: n for n, page in enumerate(rows) for row in page}
        self._segments = self._cut()
        self._grids: dict[int, tuple[float, float, Callable[[int], float]]] = {}
        self._glyph_at = {(s.page, *cell): g for s in self._all_segments() for g, cell in zip(s.glyphs, s.cells)}
        self._cursor = self._make_cursor()
        self._state = _State()
        self._items: list[Item] = [(kind, k) for k, step in enumerate(p.steps) for kind, text in (("cmd", step.command), ("out", step.output)) if text is not None]
        self._item_targets: dict[Item, list[Target]] = {}
        self._register(title, pane, pane_rows)
        for segment in self._all_segments():   # registered at full opacity: hidden until shown
            for glyph in segment.glyphs:
                glyph.set_fill(opacity=0.0)
        self._waiting = self._revealed_by_actions()
        plan = distribute(len(p.steps), len(self.beats))
        for i, d in self.timeline():
            cap = max((self._natural(k) for k in plan[i]), default=1.0)
            run_time = _run_time(d, len(plan[i]), cap)
            self.play_steps(d, [self._own_step(k, run_time) for k in plan[i]], fraction=FRACTION, cap=cap)
        self.finish()

    def _fit(self, body: Region, rows: list[list[SessionRow]], pane_lines: list[str], stacked: bool) -> tuple[bool, list[Code], list[list[list[int]]], Code | None, list[list[int]]]:
        """The pages and the code fitted to their regions (one font size for both): ``stacked``,
        the pages, the rows each page's rows became, the code and the rows its lines became."""
        p = self.params
        term_area, code_area = self._areas(body, rows, pane_lines, stacked)
        texts, runs = [[r.text for r in page] for page in rows], [[r.runs for r in page] for page in rows]
        pages, groups = self._fit_listings(texts, None, term_area, lexed=runs, numbered=False)
        if p.code is None:
            return stacked, pages, groups, None, []
        pane, pane_rows = self._fit_listing(pane_lines, lexer_name(p.code.language, p.code.path), code_area)
        scale = min(pages[0].fit_scale, pane.fit_scale)
        for listing in [*pages, pane]:
            listing.scale(scale / listing.fit_scale)
            listing.fit_scale = scale
        return stacked, pages, groups, pane, pane_rows

    @staticmethod
    def _areas(body: Region, rows: list[list[SessionRow]], pane_lines: list[str], stacked: bool) -> tuple[Region, Region]:
        """The terminal's region and the code's (both ``body`` without code): the code on the
        left, or above when ``stacked``, the two sharing ``body`` by their content (each 35 to
        65 %)."""
        if not pane_lines:
            return body, body
        if stacked:
            term, code = max(len(page) for page in rows), len(pane_lines)
        else:
            term, code = max(len(r.text) for page in rows for r in page), max(len(line) for line in pane_lines)
        share = min(max(code / max(code + term, 1), 0.35), 0.65)
        first, second = (body.rows if stacked else body.columns)([share, 1 - share], gap=PANE_GAP)
        return second, first

    def _window(self, pages: list[Code]) -> Code:
        """The terminal window: as wide as the widest page and as tall as the tallest (a
        listing of that size without its text), so it keeps its size when the screen clears."""
        columns = max(len(line) for page in pages for line in page.shown_lines)
        height = max(len(page.shown_lines) for page in pages)
        from pygments.token import Text

        shown = ["M" * columns] * height
        window = self._listing(shown, [[(line, Text)] for line in shown], float(self.theme.size(self.params.size)), numbered=False)
        window.scale(pages[0].fit_scale)
        window.remove(window.code_lines)
        return window

    def _place(self, pages: list[Code], pane: Code | None, stacked: bool, term_area: Region, code_area: Region) -> None:
        """The window centred in ``term_area`` and every page's text at its top-left corner;
        the code beside it with the same top, or above it, the two centred as one block."""
        frame = self._frame
        frame.move_to(term_area.center)
        if pane is not None and stacked:
            middle = (code_area.y1 + term_area.y0) / 2
            block_top = middle + (pane.height + PANE_GAP + frame.height) / 2
            pane.move_to([code_area.center[0], block_top - pane.height / 2, 0.0])
            frame.shift(UP * (block_top - pane.height - PANE_GAP - frame.get_top()[1]))
        elif pane is not None:
            pane.move_to(code_area.center)
            top = max(float(frame.get_top()[1]), float(pane.get_top()[1]))
            pane.shift(UP * (top - pane.get_top()[1]))
            frame.shift(UP * (top - frame.get_top()[1]))
        for page in pages:
            page.shift(RIGHT * (frame.get_left()[0] - page.get_left()[0]) + UP * (frame.get_top()[1] - page.get_top()[1]))

    # ----- the page's text as segments -----------------------------------------------------------

    def _cut(self) -> dict[tuple[str, int, int], list[_Segment]]:
        """Every page's text as segments by ``(kind, step, line)`` (kind ``prompt``, ``command``,
        ``output`` or ``end``), each its own text placed on the listing's glyphs and coloured
        like them (the prompt in ``prompt_color``, an output in its ``output_color``); colours
        that would read poorly on the window are mixed towards the theme's text colour. The
        listings keep only their windows."""
        p = self.params
        out: dict[tuple[str, int, int], list[_Segment]] = {}
        for n, (page, rows, groups) in enumerate(zip(self._pages, self._rows, self._groups)):
            shown = page.shown_lines
            for row, physical in zip(rows, groups):
                for piece, r in enumerate(physical):
                    text = shown[r]
                    start = row.typed_from if piece == 0 else len(text) - len(text.lstrip())
                    parts = [(("prompt", row.step, 0), 0, len(p.prompt))] if row.kind == "command" and piece == 0 and row.typed_from else []
                    parts.append(((row.kind, row.step, row.line), start, len(text)))
                    for key, a, b in parts:
                        segment = self._segment(n, r, text, a, b)
                        if segment is None:
                            continue
                        color = p.prompt_color if key[0] in ("prompt", "end") else p.steps[row.step].output_color if key[0] == "output" else None
                        if color is not None:
                            segment.text.set_color(self.theme.color(color))
                        out.setdefault(key, []).append(segment)
            page.remove(page.code_lines)
        readable_band(self, [s.text for segments in out.values() for s in segments], self.theme.color("surface"), (0.0,))
        return out

    def _segment(self, n: int, r: int, text: str, a: int, b: int) -> _Segment | None:
        """Columns ``a`` to ``b`` of row ``r`` of page ``n`` as their own text, or ``None`` when
        they show nothing."""
        piece = text[a:b]
        if not piece.strip():
            return None
        page = self._pages[n]
        size = float(self.theme.size(self.params.size))
        cols = [c for c in range(a, b) if not text[c].isspace()]
        before = sum(1 for c in range(a) if not text[c].isspace())
        under = page.code_lines[r].submobjects[before : before + len(cols)]
        with text_canvas([piece], size):
            drawn = Paragraph(piece.strip(), font=self._font, font_size=size, line_spacing=0.5, disable_ligatures=True)
        for line in drawn:   # Pango's spaces are dots (Manim's Code drops them the same way)
            line.submobjects = [m for m in line if not isinstance(m, Dot)]
        drawn.scale(page.fit_scale)
        glyphs = drawn.family_members_with_points()
        if under:
            drawn.move_to(VGroup(*under).get_center())
            if len(glyphs) == len(under):
                for glyph, ink in zip(glyphs, under):
                    glyph.set_fill(ink.get_fill_color())
            else:
                drawn.set_color(under[0].get_fill_color())
        drawn.set_z_index(2)   # over the window (which comes in with it)
        return _Segment(drawn, n, glyphs, [(r, c) for c in cols] if len(glyphs) == len(cols) else [])

    def _all_segments(self) -> list[_Segment]:
        return [s for segments in self._segments.values() for s in segments]

    def _metrics(self, page: int) -> tuple[float, float]:
        """``(advance, pitch)`` of a page's text in units: a character's width, a row's height."""
        size = float(self.theme.size(self.params.size))
        advance, pitch = mono_metrics(self._font)
        scale = self._pages[page].fit_scale
        return advance * size * scale, pitch * size * scale

    def _make_cursor(self) -> Rectangle:
        """The block cursor (hidden until the session places it): a character wide, nearly a row
        tall."""
        advance, pitch = self._metrics(0)
        cursor = Rectangle(width=advance, height=0.8 * pitch, stroke_width=0)
        cursor.set_fill(self.theme.color("text"), opacity=0.0)
        return cursor.set_z_index(3)

    def _cell(self, page: int, row: int, col: int) -> np.ndarray:
        """The centre of a character cell (wrapped row and column) of a page; rows past the
        page's last continue its spacing."""
        if page not in self._grids:
            self._grids[page] = self._grid(page)
        x0, advance, y_of = self._grids[page]
        return np.array([x0 + (col + 0.5) * advance, y_of(row), 0.0])

    def _grid(self, page: int) -> tuple[float, float, Callable[[int], float]]:
        """A page's character grid: the left edge of column 0, the advance, and a row's centre
        (fitted through the rows drawn)."""
        advance, pitch = self._metrics(page)
        segments = [s for s in self._all_segments() if s.page == page and s.cells]
        lefts = [float(s.glyphs[0].get_center()[0]) - (s.cells[0][1] + 0.5) * advance for s in segments]
        x0 = float(np.median(lefts)) if lefts else float(self._pages[page].background.get_left()[0]) + advance
        known = sorted({s.cells[0][0]: float(np.mean([g.get_center()[1] for g in s.glyphs])) for s in segments}.items())
        if len(known) >= 2:
            slope, icpt = np.polyfit(*zip(*known), 1)
            return x0, advance, lambda row: float(icpt + slope * row)
        r0, y0 = known[0] if known else (0, float(self._pages[page].get_center()[1]))
        return x0, advance, lambda row: y0 - (row - r0) * pitch

    # ----- targets ---------------------------------------------------------------------------------

    def _register(self, title: Mobject | None, pane: Code | None, pane_rows: list[list[int]]) -> None:
        """The targets, at full opacity; the code's highlight is applied after."""
        p = self.params
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=UP * 0.12)])
        self.target("terminal", self._frame, entrance=self._open)
        self._pane_bands = VGroup()
        if pane is not None:
            code = self.target("code", pane, entrance=lambda: [FadeIn(Group(pane, self._pane_bands), shift=UP * 0.12)])
            for k, rows in enumerate(pane_rows, 1):
                parts = [pane.code_lines[j] for j in rows] + ([pane.line_numbers[j] for j in rows] if p.line_numbers else [])
                self.target(f"code.line{k}", VGroup(*parts), entrance=lambda: self.entrance(code))
            if p.code.highlight is not None:
                self._mark(pane, pane_rows)

        def texts(kind: str, k: int, line: int | None = None) -> VGroup:
            return VGroup(*[s.text for (kd, st, ln), segs in self._segments.items() if kd == kind and st == k and line in (None, ln) for s in segs])

        for k, step in enumerate(p.steps):
            n = k + 1
            if step.command is not None:
                self._item_targets[("cmd", k)] = [self.target(f"command{n}", texts("command", k), entrance=lambda k=k: self._enter(self._command_items(k)))]
            if step.output is not None:
                show = lambda k=k: self._enter([("out", k)])
                own = [self.target(f"output{n}", texts("output", k), entrance=show)]
                own += [self.target(f"output{n}.line{j}", texts("output", k, j - 1), entrance=show) for j in output_line_numbers(step)]
                self._item_targets[("out", k)] = own

    def _mark(self, pane: Code, pane_rows: list[list[int]]) -> None:
        """The code's ``highlight``: the other lines dim, a band marks the chosen ones."""
        p = self.params
        chosen = {j for k in parse_line_spec(p.code.highlight) for j in pane_rows[k - 1]}
        color = self.theme.color(p.highlight_color)
        lines = pane.code_lines
        opacity = readable_band(self, list(lines), color, BAND_OPACITIES)
        lines.set_z_index(2)
        parts = [lines] + ([pane.line_numbers] if p.line_numbers else [])
        if p.line_numbers:
            pane.line_numbers.set_z_index(2)
        for paragraph in parts:
            for row, m in enumerate(paragraph):
                if row not in chosen:
                    m.set_opacity(0.35)
        wrapped = len(pane_rows) != len(lines)
        self._pane_bands = listing_bands(pane, chosen, color, opacity, numbered=p.line_numbers, wrapped=wrapped)

    def _revealed_by_actions(self) -> set[Item]:
        """The items a ``reveal`` action shows: the scene leaves them to it."""
        revealed = {id(t) for action in self.action_uses("reveal") for pattern in action.config.targets() for t in self.find_targets(pattern)}
        return {item for item, own in self._item_targets.items() if any(id(t) in revealed for t in own)}

    def _command_items(self, k: int) -> list[Item]:
        """What typing step ``k``'s command brings: the command, and its output unless an action
        shows that."""
        out = ("out", k)
        return [("cmd", k)] + ([out] if self.params.steps[k].output is not None and out not in self._waiting else [])

    def entrance_time(self, target: Target) -> float | None:
        """The seconds a command's typing (with its output) or an output takes from now, the
        window's opening for ``terminal``."""
        if target.name == "terminal":
            return INTRO
        for item, own in self._item_targets.items():
            if target in own:
                items = self._command_items(item[1]) if item[0] == "cmd" else [item]
                return self._schedule(items, self._state).seconds
        return None

    # ----- the session's timing ------------------------------------------------------------------

    def _natural(self, k: int) -> float:
        """About how long the scene's own step ``k`` takes (with the window's opening for the
        first; without what actions show)."""
        step = self.params.steps[k]
        seconds = INTRO + PROMPT_PAUSE if k == 0 else CLEAR + PROMPT_PAUSE if step.clear else 0.0
        typed = step.command is not None and ("cmd", k) not in self._waiting
        if typed:
            seconds += max(MIN_TYPING, len(step.command.strip()) / self.params.typing_speed) + ENTER_PAUSE
        if step.output is not None and ("out", k) not in self._waiting and (typed or step.command is None):
            seconds += min(max(len(_text_lines(step.output)) * ROW_TIME, OUTPUT_MIN), OUTPUT_MAX)
        return seconds

    def _own_step(self, k: int, run_time: float) -> Callable[[], list[Animation]]:
        """Step ``k`` as the scene plays it in a beat (``run_time``: what ``play_steps`` gives
        it): the title, the code and the window first if they are not on screen yet, then the
        command and its output, except what actions show."""
        def build() -> list[Animation]:
            step = self.params.steps[k]
            intro: list[Animation] = []
            if self._state.page is None:
                intro = [a for name in ("title", "code", "terminal") for t in self.find_targets(name) for a in self.entrance(t)]
                coming = {id(m) for a in intro for m in a.mobject.get_family()}
                if len(self._pane_bands) and id(self._pane_bands) not in coming:   # a carried listing moved in without them
                    intro.append(FadeIn(self._pane_bands))
            if step.command is not None:
                items = [] if ("cmd", k) in self._waiting else self._command_items(k)
            else:
                items = [] if ("out", k) in self._waiting else [("out", k)]
            start = INTRO if intro else 0.0
            schedule = self._schedule(items, self._state, start)
            if not items and k == 0 and step.command is not None and k not in schedule.state.prompts:   # waiting for the action
                self._show_prompt(schedule, k)
            self._state = schedule.state
            seconds = max(schedule.seconds, start)
            anims = self._animations(schedule, seconds, run_time)
            if intro:
                anims.append(AnimationGroup(*intro, rate_func=during(0.0, min(INTRO * min(1.0, run_time / seconds) / run_time, 1.0), linear)))
            return anims

        return build

    def _open(self) -> list[Animation]:
        """The ``terminal`` target's entrance: the window of the page the session is on."""
        if self._state.page is not None:
            return []
        undone = next((i for i in self._items if i not in self._state.done), None)
        self._state.page = self._page_of[undone[1]] if undone is not None else 0
        return [Fade(self._frame, shift=UP * 0.12)]

    def _enter(self, items: list[Item]) -> list[Animation]:
        """The entrance of a command or an output (``reveal`` actions): what comes before it on
        its page at once, then it, timed as :meth:`entrance_time` said."""
        schedule = self._schedule(items, self._state)
        self._state = schedule.state
        return self._animations(schedule, schedule.seconds, schedule.seconds)

    def _schedule(self, wanted: list[Item], state: _State, start: float = 0.0) -> _Schedule:
        """Plan ``wanted`` from ``state`` (nothing of it is changed) from ``start`` seconds: the
        window opens or the screen clears for a new page, what comes before on the page and is
        not shown yet appears at once, then each item in turn."""
        st = state.copy()
        wanted = [i for i in wanted if i not in st.done and (st.page is None or self._page_of[i[1]] >= st.page)]
        plan = _Schedule(start, [], [], [], st)
        if not wanted:
            return plan
        page = self._page_of[wanted[0][1]]
        if st.page is None:
            plan.opening = start
            plan.seconds += INTRO
        elif st.page != page:   # the screen clears at once, the next prompt comes a moment later
            plan.cleared = (start, [s for s in self._all_segments() if s.page == st.page])
            plan.moves.append((start, None))
            plan.seconds += CLEAR
        st.page = page
        first = self._items.index(wanted[0])
        for item in self._items[:first]:
            if item not in st.done and self._page_of[item[1]] == page:
                self._plan_item(plan, item, instant=True)
        previous: Item | None = None
        for item in wanted:
            self._plan_item(plan, item, after_typing=previous == ("cmd", item[1]))
            previous = item
        return plan

    def _plan_item(self, plan: _Schedule, item: Item, *, instant: bool = False, after_typing: bool = False) -> None:
        """Add ``item`` to ``plan`` (at once when ``instant``)."""
        kind, k = item
        st, step = plan.state, self.params.steps[k]
        if kind == "cmd":
            if k not in st.prompts:
                self._show_prompt(plan, k)
                plan.seconds += 0.0 if instant else PROMPT_PAUSE
            typed = self._typing(k)
            seconds = 0.0 if instant else max(MIN_TYPING, len(typed) / self.params.typing_speed)
            for i, (glyphs, point) in enumerate(typed):
                at = plan.seconds + seconds * i / len(typed)
                plan.shows.append((at, glyphs))
                plan.moves.append((at, point))
            plan.seconds += seconds
            plan.segments += self._segments_of("command", k)
            st.done.add(item)
            if step.output is None:
                plan.seconds += 0.0 if instant else ENTER_PAUSE
                self._after(plan, k)
            return
        plan.seconds += ENTER_PAUSE if after_typing and not instant else 0.0
        rows = self._output_rows(k)
        seconds = 0.0 if instant else min(max(len(rows) * ROW_TIME, OUTPUT_MIN), OUTPUT_MAX)
        for i, (glyphs, point) in enumerate(rows):
            at = plan.seconds + seconds * i / len(rows)
            plan.shows.append((at, glyphs))
            plan.moves.append((at, point))
        plan.seconds += seconds
        plan.segments += self._segments_of("output", k)
        st.done.add(item)
        self._after(plan, k)

    def _after(self, plan: _Schedule, k: int) -> None:
        """Step ``k`` has ended: the next step's prompt appears (on the same page), or the prompt
        after the last step."""
        st, steps = plan.state, self.params.steps
        nxt = k + 1
        if nxt < len(steps) and steps[nxt].command is not None and self._page_of[nxt] == self._page_of[k] and nxt not in st.prompts:
            self._show_prompt(plan, nxt)
        elif nxt == len(steps) and steps[k].command is not None and not st.end:
            st.end = True
            segments = self._segments.get(("end", k, 0), [])
            plan.shows.append((plan.seconds, [g for s in segments for g in s.glyphs]))
            plan.segments += segments
            page, rows = self._where("end", k, 0)
            plan.moves.append((plan.seconds, self._cell(page, rows[0], len(self.params.prompt) + 1 if self.params.prompt else 0)))

    def _show_prompt(self, plan: _Schedule, k: int) -> None:
        segments = self._segments.get(("prompt", k, 0), [])
        plan.state.prompts.add(k)
        plan.shows.append((plan.seconds, [g for s in segments for g in s.glyphs]))
        plan.segments += segments
        page, rows = self._where("command", k, 0)
        plan.moves.append((plan.seconds, self._cell(page, rows[0], self._rows[page][self._row_index("command", k, 0)].typed_from)))

    def _where(self, kind: str, k: int, line: int) -> tuple[int, list[int]]:
        """The page of a row and the wrapped rows it became."""
        page = self._page_of[k]
        return page, self._groups[page][self._row_index(kind, k, line)]

    def _row_index(self, kind: str, k: int, line: int) -> int:
        page = self._page_of[k]
        return next(i for i, r in enumerate(self._rows[page]) if (r.kind, r.step, r.line) == (kind, k, line))

    def _segments_of(self, kind: str, k: int) -> list[_Segment]:
        return [s for (kd, st, _), segs in self._segments.items() if kd == kind and st == k for s in segs]

    def _typing(self, k: int) -> list[tuple[list[VMobject], np.ndarray]]:
        """Step ``k``'s command as typed, one entry per character (spaces too): the glyphs that
        appear (none for a space) and where the cursor goes."""
        page = self._page_of[k]
        shown = self._pages[page].shown_lines
        keys = [(r.line, r) for r in self._rows[page] if r.kind == "command" and r.step == k]
        out: list[tuple[list[VMobject], np.ndarray]] = []
        for line, row in keys:
            for piece, r in enumerate(self._where("command", k, line)[1]):
                text = shown[r]
                start = row.typed_from if piece == 0 else len(text) - len(text.lstrip())
                loose = [g for s in self._segments.get(("command", k, line), []) if not s.cells and s.page == page for g in s.glyphs] if piece == 0 else []
                for c in range(start, len(text)):
                    glyph = self._glyph_at.get((page, r, c))
                    glyphs = ([glyph] if glyph is not None else []) + (loose if c == start else [])
                    out.append((glyphs, self._cell(page, r, c + 1)))
        return out

    def _output_rows(self, k: int) -> list[tuple[list[VMobject], np.ndarray]]:
        """Step ``k``'s output, one entry per wrapped row: its glyphs and where the cursor goes
        (the start of the row after it, else the end of the last)."""
        page = self._page_of[k]
        shown = self._pages[page].shown_lines
        rows = [r for row in self._rows[page] if row.kind == "output" and row.step == k for r in self._where("output", k, row.line)[1]]
        out = []
        for r in rows:
            glyphs = [g for s in self._all_segments() if s.page == page and s.cells and s.cells[0][0] == r for g in s.glyphs]
            glyphs += [g for (kd, st, _), segs in self._segments.items() if kd == "output" and st == k for s in segs if not s.cells and s.page == page and self._segment_row(s) == r for g in s.glyphs]
            point = self._cell(page, r + 1, 0) if r + 1 < len(shown) else self._cell(page, r, len(shown[r]))
            out.append((glyphs, point))
        return out

    def _segment_row(self, segment: _Segment) -> int:
        """The wrapped row a segment without cells sits on (the nearest row centre)."""
        y = float(segment.text.get_center()[1])
        n = len(self._pages[segment.page].shown_lines)
        return min(range(n), key=lambda r: abs(self._cell(segment.page, r, 0)[1] - y))

    # ----- animations ----------------------------------------------------------------------------

    def _animations(self, plan: _Schedule, seconds: float, run_time: float) -> list[Animation]:
        """``plan`` as animations played for ``run_time`` (``seconds`` long, shortened in
        proportion when ``run_time`` is shorter)."""
        if seconds <= 0 or run_time <= 0:
            seconds = run_time = 1.0
        share = min(1.0, run_time / seconds) / run_time

        def frac(t: float) -> float:
            return min(max(t * share, 0.0), 1.0)

        anims: list[Animation] = []
        if plan.opening is not None:
            anims.append(AnimationGroup(Fade(self._frame, shift=UP * 0.12), rate_func=during(frac(plan.opening), frac(plan.opening + INTRO), linear)))
        cleared = plan.cleared or (0.0, [])
        if plan.shows or plan.moves:
            hides = [(frac(cleared[0]), [g for s in cleared[1] for g in s.glyphs])] if cleared[1] else []
            shows = [(frac(t), g) for t, g in plan.shows]
            anims.append(_Show(shows, hides, [(frac(t), pt) for t, pt in plan.moves], self._cursor, self._frame, plan.segments, cleared[1]))
        return anims


class _Show(Animation):
    """Shows glyphs at set fractions of its run time (a terminal prints, it does not fade), hides
    a cleared page's at once and moves the block cursor; when it ends, the shown texts are in the
    window (a ``Code``, as the layout dump and lint read a listing), the cleared ones out of it,
    and the cursor stays."""

    def __init__(
        self,
        shows: list[tuple[float, list[VMobject]]],
        hides: list[tuple[float, list[VMobject]]],
        moves: list[tuple[float, np.ndarray | None]],
        cursor: Mobject,
        window: Mobject,
        shown: list[_Segment],
        cleared: list[_Segment],
        **kwargs: Any,
    ) -> None:
        # the cleared texts move out of the window into the animation: Manim redraws only what an
        # animation holds (the rest is a still), and adding a group whose members are inside the
        # window to the scene would break the window apart
        window.remove(*[s.text for s in cleared])
        super().__init__(Group(*[s.text for s in [*cleared, *shown]], cursor), rate_func=linear, **kwargs)
        self.shows, self.hides, self.moves = shows, hides, moves
        self.cursor, self.window, self.shown, self.cleared = cursor, window, shown, cleared

    def create_starting_mobject(self) -> Mobject:
        """No copy (nothing here reads it)."""
        return Mobject()

    def interpolate_mobject(self, alpha: float) -> None:
        for events, opacity in ((self.shows, 1.0), (self.hides, 0.0)):
            for at, glyphs in events:
                if alpha >= at - 1e-9:
                    for glyph in glyphs:
                        glyph.set_fill(opacity=opacity)
        due = [point for at, point in self.moves if alpha >= at - 1e-9]
        if due:
            if due[-1] is None:
                self.cursor.set_fill(opacity=0.0)
            else:
                self.cursor.move_to(due[-1]).set_fill(opacity=CURSOR_OPACITY)

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        scene.remove(self.mobject)
        self.window.add(*[s.text for s in self.shown])
        scene.add(self.cursor)
