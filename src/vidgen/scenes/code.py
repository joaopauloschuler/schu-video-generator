"""``code``: a syntax-highlighted listing (Manim's ``Code``) with per-beat line highlights."""

import re
from collections.abc import Callable
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


def _style_names() -> list[str]:
    from pygments.styles import get_all_styles

    return sorted(get_all_styles())


@scene("code")
class CodeListing(NarratedScene):
    """Beat 1 shows the listing; ``highlight`` entry *i* is applied at beat *i* (entry 1
    together with the listing). More entries than beats are spread evenly; later beats hold.
    Highlighting dims the other lines and marks the selected ones with a soft band.
    """

    outro = 0.5

    class Params(SceneParams):
        code: str | None = None
        path: str | None = None
        language: str | None = None
        title: str = ""
        highlight: list[LineSpec] = []
        line_numbers: bool = True
        style: str = "github-dark"
        font: str = "Monospace"
        size: ThemeSize = "caption"
        highlight_color: ThemeColor = "highlight"

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if (self.code is None) == (self.path is None):
                raise ValueError("give exactly one of 'code' (inline text) or 'path' (a file in the project)")
            if self.style not in _style_names():
                raise ValueError(f"unknown style {self.style!r}; available: {', '.join(_style_names())}")
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
        listing = Code(
            code_string=text,
            language=language or "python",
            formatter_style=p.style,
            add_line_numbers=p.line_numbers,
            background="window",
            background_config={
                "fill_color": self.theme.color("surface"),
                "stroke_color": self.theme.color("dim"),
                "stroke_width": 1,
                "corner_radius": 0.15,
            },
            paragraph_config={"font": p.font, "font_size": float(self.theme.size(p.size))},
        )
        top = self.frame_height / 2 - self.margin_y
        bottom = -self.frame_height / 2 + self.margin_y
        title = None
        if p.title:
            title = fit_text(p.title, self.safe_width, self.safe_height * 0.15, size="heading", weight=BOLD)
            title.move_to([0, top - title.height / 2, 0])
            top = title.get_bottom()[1] - 0.45
        # fill the space (up to 1.5x the requested font size), never overflow
        listing.scale(min(1.5, self.safe_width / listing.width, (top - bottom) / listing.height))
        listing.move_to([0, (top + bottom) / 2, 0])

        lines = listing.code_lines
        numbers = listing.line_numbers if p.line_numbers else None
        # highlight bands go between the (opaque) window background and the text
        lines.set_z_index(2)
        if numbers is not None:
            numbers.set_z_index(2)
        ys = self._line_centers(lines, numbers)
        pitch = abs(ys[0] - ys[1]) if len(ys) > 1 else lines.height
        x_left = (numbers.get_left()[0] if numbers is not None else lines.get_left()[0]) - 0.12
        x_right = listing.background.get_right()[0] - 0.15
        state: dict[str, Any] = {"band": VGroup()}

        def bands_for(chosen: set[int]) -> VGroup:
            bands = VGroup()
            for run in _runs(sorted(chosen)):
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
                chosen = {k - 1 for k in parse_line_spec(spec)}
                bands = bands_for(chosen)
                anims: list[Animation] = [m.animate.set_opacity(o) for m, o in opacities(chosen)]
                if len(state["band"]):
                    anims.append(FadeOut(state["band"]))
                if len(bands):
                    anims.append(FadeIn(bands))
                state["band"] = bands
                return anims

            return build

        intro = Group(listing)
        if p.highlight:  # the first highlight is already applied when the listing fades in
            chosen = {k - 1 for k in parse_line_spec(p.highlight[0])}
            for m, o in opacities(chosen):
                m.set_opacity(o)
            state["band"] = bands_for(chosen)
            intro.add(state["band"])
        if title is not None:
            intro.add(title)
        plan: list = [FadeIn(intro, shift=UP * 0.12)] + [highlight(spec) for spec in p.highlight[1:]]
        self.reveal(plan, fraction=0.6, cap=1.0)
        self.finish()

    @staticmethod
    def _line_centers(lines: VGroup, numbers: VGroup | None) -> list[float]:
        """Vertical center of every code line (blank lines have no glyphs, so fit a line)."""
        if numbers is not None and len(numbers) == len(lines):
            return [float(n.get_center()[1]) for n in numbers]
        known = [(i, float(line.get_center()[1])) for i, line in enumerate(lines) if len(line.get_family()) > 1]
        if len(known) < 2:
            return [float(lines.get_center()[1])] * len(lines)
        idx, ys = zip(*known)
        slope, icpt = np.polyfit(idx, ys, 1)
        return [float(icpt + slope * i) for i in range(len(lines))]


def _runs(indices: list[int]) -> list[list[int]]:
    """Group sorted indices into runs of consecutive numbers."""
    runs: list[list[int]] = []
    for i in indices:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs
