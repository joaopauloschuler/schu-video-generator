"""``code``: a syntax-highlighted listing (Manim's ``Code``) with per-beat line highlights."""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

import numpy as np

from vidgen.api import *

LineSpec = int | str | list[int]


def parse_line_spec(spec: LineSpec) -> list[int]:
    """1-based line numbers from ``3``, ``"3-5"``, ``"1, 4-6"`` or ``[1, 4, 5]`` (sorted, unique)."""
    if isinstance(spec, bool):
        raise ValueError(f"invalid line spec {spec!r}")
    if isinstance(spec, int):
        items: list[int] = [spec]
    elif isinstance(spec, list):
        items = list(spec)
    else:
        items = []
        for part in spec.split(","):
            part = part.strip()
            m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", part)
            if not m:
                raise ValueError(f"invalid line spec {spec!r} (use e.g. 3, \"2-4\" or \"1, 5-6\")")
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            if b < a:
                raise ValueError(f"invalid line range {part!r}")
            items.extend(range(a, b + 1))
    if any(n < 1 for n in items):
        raise ValueError(f"line numbers start at 1 (got {spec!r})")
    return sorted(set(items))


#: Wrapped listings never get narrower than this many characters per line.
MIN_COLUMNS = 20
#: Extra indent (spaces) of the continuation lines of a wrapped code line.
HANGING_INDENT = 4
#: Wrapping aims to keep at least this many characters per line: when the requested size would
#: leave fewer (a vertical frame), the listing gets smaller instead, down to the readable minimum.
TARGET_COLUMNS = 32
#: Space between the line numbers and the code (Manim's ``Code`` layout), in units.
NUMBER_GAP = 0.25
#: Padding of Manim's ``Code`` background on each side, in units.
CODE_PADDING = 0.3


@lru_cache(maxsize=8)
def mono_metrics(font: str) -> tuple[float, float]:
    """``(advance, pitch)`` of a code listing in ``font`` per point of font size, in units: the
    width of one character and the distance between two lines (``Code``'s line spacing)."""
    sample = Paragraph("M" * 10, "M" * 30, font=font, font_size=48, line_spacing=0.5, disable_ligatures=True)
    advance = (sample[1].width - sample[0].width) / 20 / 48
    return float(advance), float(abs(sample[0].get_y() - sample[1].get_y()) / 48)


@contextmanager
def text_canvas(lines: list[str], size: float) -> Iterator[None]:
    """Manim draws text with Pango on a canvas of the output's pixel size and clips what does not
    fit (its glyph check then fails: about 60 lines of 24 pt code at 854x480, 9 at 160x90). This
    enlarges the canvas while a listing of ``lines`` at ``size`` points is built."""
    width, height = config.pixel_width, config.pixel_height
    longest = max((len(line) for line in lines), default=1)
    config.pixel_width = max(width, int(60 + 0.15 * size * longest))
    config.pixel_height = max(height, int(60 + 0.5 * size * (len(lines) + 2)))
    try:
        yield
    finally:
        config.pixel_width, config.pixel_height = width, height


def size_for_columns(font: str, columns: int, width: float, digits: int = 0, padding: float = 0.0) -> float:
    """The font size (points) at which ``columns`` characters of code (plus a line-number column
    of ``digits`` digits and :data:`NUMBER_GAP`, plus ``padding`` units) span ``width`` units."""
    advance = mono_metrics(font)[0]
    gap = NUMBER_GAP if digits else 0.0
    return max(width - gap - padding, 0.0) / ((columns + digits) * advance)


def wrap_code(lines: list[str], columns: int) -> tuple[list[str], list[list[int]]]:
    """Wrap code lines longer than ``columns`` characters; continuation lines are indented by
    :data:`HANGING_INDENT` more than the line. Returns the new lines and, for each original
    line, the indices of the lines it became (so highlights still address original lines)."""
    out: list[str] = []
    groups: list[list[int]] = []
    for line in lines:
        pieces = _wrap_code_line(line, columns)
        groups.append(list(range(len(out), len(out) + len(pieces))))
        out.extend(pieces)
    return out, groups


def _wrap_code_line(line: str, columns: int) -> list[str]:
    if len(line) <= columns:
        return [line]
    lead = len(line) - len(line.lstrip(" "))
    prefix = " " * min(lead + HANGING_INDENT, columns // 2)
    pieces: list[str] = []
    rest = line
    while len(rest) > columns:
        cut = _break_at(rest, columns)
        pieces.append(rest[:cut].rstrip())
        rest = prefix + rest[cut:].lstrip()
    return pieces + [rest]


def _break_at(text: str, columns: int) -> int:
    """Where to cut ``text`` (at most ``columns`` characters kept): after the last space or
    comma outside a string literal (if past half the line), else after the last opening
    bracket, else at any space, else hard at ``columns``."""
    start = len(text) - len(text.lstrip(" ")) + 1
    space = bracket = loose = 0
    quote = ""
    for k, ch in enumerate(text[:columns], start=1):
        if k > start and ch == " ":
            loose = k
        if quote:
            if ch == quote and text[k - 2 : k - 1] != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif k > start and ch in " ,":
            space = k
        elif k > start and ch in "([{":
            bracket = k
    if space >= columns / 2:
        return space
    return max(space, bracket) or loose or columns


def style_names() -> list[str]:
    """Names of the Pygments styles."""
    from pygments.styles import get_all_styles

    return sorted(get_all_styles())


@scene("code")
class CodeListing(NarratedScene):
    """Beat 1 shows the listing; ``highlight`` entry *i* is applied at beat *i* (entry 1
    together with the listing). More entries than beats are spread evenly; later beats hold.
    Highlighting dims the other lines and marks the selected ones with a soft band.

    Action targets: ``title``, ``listing`` (the window), ``line<N>`` (an original line, 1-based,
    with its number; all its pieces when wrapped) and ``lines:<a-b>`` (lines a to b).
    """

    outro = 0.5
    target_patterns = ("title", "listing", "line<N>", "lines:<a-b>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``listing``, ``line<N>`` per line and ``lines:<a-b>`` per range. The
        lines of a ``path`` file are counted in the active project (none without one)."""
        n = cls._line_count(params)
        names = (["title"] if params.title else []) + ["listing"] + [f"line{k}" for k in range(1, n + 1)]
        return names + [f"lines:{a}-{b}" for a in range(1, n + 1) for b in range(a + 1, n + 1)]

    @staticmethod
    def _line_count(params: Any) -> int:
        """Lines of the listing (0 when its file cannot be read here)."""
        text = params.code
        if text is None:
            try:
                text = current_project().asset(params.path).read_text(encoding="utf-8")
            except (VidgenError, OSError, UnicodeDecodeError):
                return 0
        return len(text.rstrip("\n").split("\n"))

    class Params(SceneParams):
        code: str | None = None
        """Inline code; give exactly one of code / path."""
        path: str | None = None
        """Code file in the project; give exactly one of code / path."""
        language: str | None = None
        """Pygments lexer name; default: from the file name, else python."""
        title: str = ""
        """Window title."""
        highlight: list[LineSpec] = []
        """Entry i applies at beat i: 3, '2-4', '1, 5-6' or [1, 4] (1-based lines)."""
        line_numbers: bool = True
        """Show line numbers."""
        style: str | None = None
        """Pygments style (monokai, dracula, xcode, ...); default: the theme's code_style."""
        font: str | None = None
        """Font family of the listing; default: the theme's font for the `code` role (font_mono, JetBrains Mono NL)."""
        size: ThemeSize = "caption"
        """Starting font size (scaled to fill the frame, up to 1.5x)."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlight band."""
        wrap: bool = True
        """Wrap long lines (hanging indent) when the listing would otherwise be scaled below
        size (or the readable minimum), mostly in vertical formats; highlights keep their lines."""

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
            for spec in self.highlight:
                parse_line_spec(spec)
            if self.code is not None:
                self._check_lines(self.code)
            return self

        def _check_lines(self, text: str) -> None:
            n = len(text.rstrip("\n").split("\n"))
            for spec in self.highlight:
                bad = [k for k in parse_line_spec(spec) if k > n]
                if bad:
                    raise ValueError(f"highlight {spec!r}: the code has only {n} lines")

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        if params.path is not None:
            path = project.root / params.path
            if not path.is_file():
                return problems + [f"path: file not found: {params.path} (looked for {path})"]
            try:
                params._check_lines(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append(f"path: {exc}")
        return problems

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        text = p.code if p.code is not None else self.project.asset(p.path).read_text(encoding="utf-8")
        text = text.rstrip("\n")
        language = p.language
        if language is None and p.path is not None:
            from pygments.lexers import get_lexer_for_filename
            from pygments.util import ClassNotFound

            try:
                language = get_lexer_for_filename(p.path).aliases[0]
            except ClassNotFound:
                language = "text"
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading")   # header band, 1.3x in a vertical frame
            body = body.below(title, gap=0.45)
        listing, groups = self._fit_listing(text.expandtabs(4).split("\n"), language or "python", body)
        place(listing, body, fit="none", align="center")
        wrapped = len(groups) != len(listing.code_lines)

        lines = listing.code_lines
        numbers = listing.line_numbers if p.line_numbers else None
        # highlight bands go between the (opaque) window background and the text
        lines.set_z_index(2)
        if numbers is not None:
            numbers.set_z_index(2)
        ys = line_centers(lines, None if wrapped else numbers)
        pitch = abs(ys[0] - ys[1]) if len(ys) > 1 else lines.height
        x_left = (numbers.get_left()[0] if numbers is not None else lines.get_left()[0]) - 0.12
        x_right = listing.background.get_right()[0] - 0.15
        state: dict[str, Any] = {"band": VGroup()}

        def physical(spec: LineSpec) -> set[int]:
            return {j for k in parse_line_spec(spec) for j in groups[k - 1]}

        def bands_for(chosen: set[int]) -> VGroup:
            bands = VGroup()
            for run in line_runs(sorted(chosen)):
                hi, lo = ys[run[0]] + pitch / 2, ys[run[-1]] - pitch / 2
                band = RoundedRectangle(width=x_right - x_left, height=hi - lo, corner_radius=0.06, stroke_width=0)
                band.set_fill(self.theme.color(p.highlight_color), opacity=0.2)
                bands.add(band.move_to([(x_left + x_right) / 2, (hi + lo) / 2, 0]))
            return bands.set_z_index(1)

        def opacities(chosen: set[int]) -> list[tuple[Mobject, float]]:
            pairs = [(line, 1.0 if i in chosen else 0.35) for i, line in enumerate(lines)]
            if numbers is not None:
                pairs += [(n, 1.0 if i in chosen else 0.35) for i, n in enumerate(numbers)]
            return pairs

        def highlight(spec: LineSpec) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                chosen = physical(spec)
                bands = bands_for(chosen)
                anims: list[Animation] = [m.animate.set_opacity(o) for m, o in opacities(chosen)]
                if len(state["band"]):
                    anims.append(FadeOut(state["band"]))
                if len(bands):
                    anims.append(FadeIn(bands))
                state["band"] = bands
                return anims

            return build

        def physical_lines(k: int) -> VGroup:
            rows = [lines[j] for j in groups[k - 1]] + ([numbers[j] for j in groups[k - 1]] if numbers is not None else [])
            return VGroup(*rows)

        intro = Group(listing)
        window = self.target("listing", listing, entrance=lambda: [FadeIn(intro, shift=UP * 0.12)])

        def show() -> list[Animation]:  # a line appears with its listing
            return self.entrance(window)

        for k in range(1, len(groups) + 1):
            self.target(f"line{k}", physical_lines(k), entrance=show)
        for a in range(1, len(groups) + 1):
            for b in range(a + 1, len(groups) + 1):
                self.target(f"lines:{a}-{b}", VGroup(*[physical_lines(k) for k in range(a, b + 1)]), entrance=show)
        if p.highlight:  # the first highlight is already applied when the listing fades in
            chosen = physical(p.highlight[0])
            for m, o in opacities(chosen):
                m.set_opacity(o)
            state["band"] = bands_for(chosen)
            intro.add(state["band"])
        heading = self.target("title", title, entrance=lambda: [FadeIn(title, shift=UP * 0.12)]) if title is not None else None

        def first() -> list[Animation]:  # entrance(): what an action showed early is not shown again
            return self.entrance(window) + (self.entrance(heading) if heading is not None else [])

        plan: list = [first] + [highlight(spec) for spec in p.highlight[1:]]
        self.reveal(plan, fraction=0.6, cap=1.0)
        self.finish()

    @property
    def _font(self) -> str:
        """The listing's font family."""
        return self.params.font or self.theme.font_for("code")

    def _fit_listing(self, lines: list[str], language: str, body: Region) -> tuple[Code, list[list[int]]]:
        """The listing scaled to fill ``body`` (up to 1.5x the requested size, never
        overflowing), wrapped narrower while its width makes it smaller than the requested size
        (and at least the readable size). Returns it and, per original line, its lines."""
        p = self.params
        size = float(self.theme.size(p.size))
        digits = len(str(len(lines))) if p.line_numbers else 0
        # the listing is scaled as a whole, so its padding scales with it: solve for the font
        # size that fits TARGET_COLUMNS into the width (in a vertical frame: smaller than size)
        padding = 2 * CODE_PADDING + (NUMBER_GAP if digits else 0.0)
        advance = mono_metrics(self._font)[0]
        narrow = body.width * size / (padding + (TARGET_COLUMNS + digits) * advance * size)
        floor = max(min(size, narrow), readable_size(self._font))
        columns: int | None = None
        while True:
            shown, groups = wrap_code(lines, columns) if columns else (lines, [[i] for i in range(len(lines))])
            listing = self._listing("\n".join(shown), language, size)
            by_width, by_height = body.width / listing.width, body.height / listing.height
            scale = min(1.5, by_width, by_height)
            longest = max(len(line) for line in shown)
            if not p.wrap or size * scale >= floor or by_width > by_height or longest <= MIN_COLUMNS:
                break
            columns = max(MIN_COLUMNS, min(longest - 1, int(longest * size * scale / floor)))
        if len(shown) != len(lines) and p.line_numbers:
            renumber(self, listing, groups, size, self._font)
        return listing.scale(scale), groups

    def _listing(self, text: str, language: str, size: float) -> Code:
        with text_canvas(text.split("\n"), size):
            return self._code(text, language, size)

    def _code(self, text: str, language: str, size: float) -> Code:
        p = self.params
        return Code(
            code_string=text,
            language=language,
            formatter_style=p.style or self.theme.code_style,
            add_line_numbers=p.line_numbers,
            background="window",
            background_config={
                "fill_color": self.theme.color("surface"),
                "stroke_color": self.theme.color("dim"),
                "stroke_width": 1,
                "corner_radius": 0.15,
            },
            paragraph_config={"font": self._font, "font_size": size},
        )


def renumber(scene: NarratedScene, listing: Code, groups: list[list[int]], size: float, font: str, first: int = 1) -> None:
    """Number the original lines of a wrapped listing (from ``first``): continuation lines get no
    number (an empty group in their place)."""
    numbers = listing.line_numbers
    color = numbers[0][0].get_fill_color() if len(numbers[0]) else scene.theme.color("dim")
    for i, group in enumerate(groups):
        head, *rest = group
        old = numbers[head]
        label = scene.text(str(first + i), size=size, color=color, font=font)
        label.align_to(old, RIGHT).align_to(old, DOWN)
        numbers.submobjects[head] = label
        for j in rest:
            numbers.submobjects[j] = VGroup()


def line_centers(lines: VGroup, numbers: VGroup | None) -> list[float]:
    """Vertical center of every code line: its number's, or (blank lines have no glyphs, and
    wrapped listings no number on continuation lines) a straight line fitted to the others."""
    if numbers is not None and len(numbers) == len(lines):
        return [float(n.get_center()[1]) for n in numbers]
    known = [(i, float(line.get_center()[1])) for i, line in enumerate(lines) if len(line.get_family()) > 1]
    if len(known) < 2:
        return [float(lines.get_center()[1])] * len(lines)
    idx, ys = zip(*known)
    slope, icpt = np.polyfit(idx, ys, 1)
    return [float(icpt + slope * i) for i in range(len(lines))]


def line_runs(indices: list[int]) -> list[list[int]]:
    """Group sorted indices into runs of consecutive numbers."""
    runs: list[list[int]] = []
    for i in indices:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs
