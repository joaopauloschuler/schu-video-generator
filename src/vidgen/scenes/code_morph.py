"""``code_morph``: a listing that changes from one version of the code to the next. Lines and
tokens both versions share glide to their new place, new lines grow in, removed lines fade out;
vidgen finds what changed (``difflib``)."""

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from vidgen.api import *

from .code import (
    BAND_OPACITIES,
    CodeListing,
    LineSpec,
    lexer_name,
    listing_bands,
    parse_line_spec,
    readable_band,
    style_names,
)
from .pie import window as during

#: Two lines whose tokens agree at least this much (``difflib`` ratio) are one line edited, not
#: one line removed and another added.
PAIR_RATIO = 0.5
#: A token: a run of word characters, or one other non-space character.
_TOKEN = re.compile(r"\w+|[^\w\s]")
#: ``highlight: changed``: the lines that differ from the version before.
CHANGED = "changed"
#: Opacity of the lines a version's highlight leaves out (as in ``code``).
DIMMED = 0.35
#: Parts of a morph (fractions of its run time): removed glyphs fade out, kept ones glide, new
#: ones grow in.
FADE_OUT, GLIDE, GROW_IN = (0.0, 0.45), (0.1, 0.9), (0.5, 1.0)
#: Longest morph of the scene's own steps (seconds), and the run time of a ``reveal`` action's.
MORPH_SECONDS = 1.5


@dataclass(frozen=True)
class CodeDiff:
    """What changes from one version of the code to the next (lines 0-based; a glyph is the
    n-th non-space character of its line, as Manim's ``Code`` draws one glyph per such character).

    ``lines``: old line -> new line, for lines kept (perhaps edited, re-indented or moved);
    ``glyphs``: ``(old line, old glyph, new line, new glyph)`` of the characters that glide;
    ``changed``: new lines that are new, edited or moved; ``removed``: old lines with no new
    line; ``added``: new lines with no old line."""

    lines: dict[int, int]
    glyphs: list[tuple[int, int, int, int]]
    changed: list[int]
    removed: list[int]
    added: list[int]


def code_tokens(line: str) -> list[str]:
    """The tokens of a code line: words and single other characters (no whitespace)."""
    return _TOKEN.findall(line)


def diff_code(old: list[str], new: list[str]) -> CodeDiff:
    """The :class:`CodeDiff` of two versions of a listing: lines are matched by their text
    without the indentation (``difflib``), edited lines within a changed block are paired when
    their tokens agree (:data:`PAIR_RATIO`), a line that moved elsewhere unchanged is found, and
    within a pair the shared tokens keep their characters."""
    matcher = difflib.SequenceMatcher(None, [line.strip() for line in old], [line.strip() for line in new], autojunk=False)
    pairs: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            pairs.update(zip(range(i1, i2), range(j1, j2)))
        elif tag == "replace":
            pairs.update(_pair_edited(old, new, list(range(i1, i2)), list(range(j1, j2))))
    moved: set[int] = set()
    free = sorted(set(range(len(new))) - set(pairs.values()))
    for i, line in enumerate(old):
        if i in pairs or not line.strip():
            continue
        j = next((j for j in free if new[j].strip() == line.strip()), None)
        if j is not None:
            pairs[i] = j
            moved.add(j)
            free.remove(j)
    pairs = dict(sorted(pairs.items()))
    glyphs = [(i, a, j, b) for i, j in pairs.items() for a, b in _shared_glyphs(old[i], new[j])]
    kept = set(pairs.values())
    changed = [j for j in range(len(new)) if j not in kept or j in moved]
    changed += [j for i, j in pairs.items() if old[i].rstrip() != new[j].rstrip() and j not in moved]
    return CodeDiff(pairs, glyphs, sorted(set(changed)), [i for i in range(len(old)) if i not in pairs], free)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, code_tokens(a), code_tokens(b), autojunk=False).ratio()


def _pair_edited(old: list[str], new: list[str], olds: list[int], news: list[int]) -> dict[int, int]:
    """Pair the lines of a changed block in order, keeping the pairs whose tokens agree most
    (each at least :data:`PAIR_RATIO`)."""
    n, m = len(olds), len(news)
    ratio = [[_ratio(old[i], new[j]) for j in news] for i in olds]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for a in range(1, n + 1):
        for b in range(1, m + 1):
            best[a][b] = max(best[a - 1][b], best[a][b - 1])
            if ratio[a - 1][b - 1] >= PAIR_RATIO:
                best[a][b] = max(best[a][b], best[a - 1][b - 1] + ratio[a - 1][b - 1])
    pairs: dict[int, int] = {}
    a, b = n, m
    while a and b:
        if ratio[a - 1][b - 1] >= PAIR_RATIO and best[a][b] == best[a - 1][b - 1] + ratio[a - 1][b - 1]:
            pairs[olds[a - 1]] = news[b - 1]
            a, b = a - 1, b - 1
        elif best[a][b] == best[a - 1][b]:
            a -= 1
        else:
            b -= 1
    return pairs


def _shared_glyphs(old: str, new: str) -> list[tuple[int, int]]:
    """``(old glyph, new glyph)`` of the characters of the tokens two lines share, in order."""
    a, b = code_tokens(old), code_tokens(new)
    starts_a = [sum(len(t) for t in a[:k]) for k in range(len(a))]
    starts_b = [sum(len(t) for t in b[:k]) for k in range(len(b))]
    out: list[tuple[int, int]] = []
    for block in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            ga, gb = starts_a[block.a + k], starts_b[block.b + k]
            out += [(ga + c, gb + c) for c in range(len(a[block.a + k]))]
    return out


class CodeVersion(SceneParams):
    """A version of the code: ``{code | path, highlight}``; a string alone is its code."""

    also_accepts = (str,)

    code: str | None = None
    """The code of this version; give exactly one of code / path."""
    path: str | None = None
    """A code file in the project; give exactly one of code / path."""
    highlight: LineSpec | None = None
    """Lines of this version to mark once it shows (the others dim): 3, '2-4', '1, 5-6', [1, 4], or 'changed' (the lines that differ from the version before)."""

    @model_validator(mode="before")
    @classmethod
    def _from_code(cls, data: Any) -> Any:
        return {"code": data} if isinstance(data, str) else data

    @model_validator(mode="after")
    def _check(self) -> "CodeVersion":
        if (self.code is None) == (self.path is None):
            raise ValueError("give exactly one of 'code' (inline text) or 'path' (a file in the project)")
        if self.highlight is not None and self.highlight != CHANGED:
            parse_line_spec(self.highlight)
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """The code alone is also a version (JSON Schema ``anyOf``)."""
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}


def _as_list(target: str | list[str] | None) -> list[str]:
    return [target] if isinstance(target, str) else list(target or [])


def _lines(text: str) -> list[str]:
    """A version's lines as drawn (trailing newlines dropped, tabs expanded to 4)."""
    return text.rstrip("\n").expandtabs(4).split("\n")


@scene("code_morph")
class CodeMorph(CodeListing):
    """Version 1 of the code shows with beat 1; at beat *i* the listing morphs into version *i*:
    what both versions share glides into place, new lines grow in, removed lines fade out.
    More versions than beats are spread evenly; later beats hold. ``{reveal: version2, at:
    "@word"}`` morphs on a spoken word instead (that version then waits for the action). A
    version's ``highlight`` marks its lines once it shows (``changed``: the lines that differ).

    Action targets: ``title``, ``listing`` (the window, whichever version shows), ``version<N>``
    (revealing it morphs to it) and ``version<N>.line<K>`` (line K of version N).
    """

    outro = 0.5
    target_patterns = ("title", "listing", "version<N>", "version<N>.line<K>")

    class Params(SceneParams):
        versions: list[CodeVersion] = Field(min_length=2)
        """The versions in order (at least two): each the code (a string) or {code | path, highlight}; version i shows at beat i."""
        language: str | None = None
        """Pygments lexer name; default: from the first file name, else python."""
        title: TranslatableStr = ""
        """Window title."""
        line_numbers: bool = True
        """Show line numbers."""
        style: str | None = None
        """Pygments style (monokai, dracula, xcode, ...); default: the theme's code_style."""
        font: str | None = None
        """Font family of the listing; default: the theme's font for the `code` role (font_mono, JetBrains Mono NL)."""
        size: ThemeSize = "caption"
        """Starting font size (scaled so the largest version fills the frame, up to 1.5x); one size for every version."""
        highlight_color: ThemeColor = "highlight"
        """Color of the highlight band."""
        wrap: bool = True
        """Wrap long lines (hanging indent) when the listing would otherwise be scaled below size (or the readable minimum), mostly in vertical formats."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if self.style is not None and self.style not in style_names():
                raise ValueError(f"unknown style {self.style!r}; available: {', '.join(style_names())}")
            if self.language is not None:
                from pygments.lexers import get_lexer_by_name
                from pygments.util import ClassNotFound

                try:
                    get_lexer_by_name(self.language)
                except ClassNotFound:
                    raise ValueError(f"unknown language {self.language!r} (a Pygments lexer name, e.g. python)") from None
            texts = [v.code for v in self.versions]
            if None not in texts:
                self.check_versions(texts)
            return self

        def check_versions(self, texts: list[str]) -> None:
            """Raise ``ValueError`` when a version repeats the one before or a highlight names a
            line past its version's end (``texts``: the versions' code)."""
            for k, (version, text) in enumerate(zip(self.versions, texts)):
                lines = _lines(text)
                if k and lines == _lines(texts[k - 1]):
                    raise ValueError(f"versions[{k}] is the same code as versions[{k - 1}]: nothing would change (drop it, or change the code)")
                if version.highlight is not None and version.highlight != CHANGED:
                    past = [n for n in parse_line_spec(version.highlight) if n > len(lines)]
                    if past:
                        raise ValueError(f"versions[{k}].highlight {version.highlight!r}: version {k + 1} has only {len(lines)} lines")

    @classmethod
    def _texts(cls, params: Any, project: Any = None) -> list[str] | None:
        """Every version's code (``None`` when a file cannot be read here)."""
        texts = []
        for version in params.versions:
            if version.code is not None:
                texts.append(version.code)
                continue
            try:
                texts.append((project.asset(version.path) if project is not None else current_project().asset(version.path)).read_text(encoding="utf-8"))
            except (VidgenError, OSError, UnicodeDecodeError):
                return None
        return texts

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``title`` (if any), ``listing``, ``version<N>`` per version and
        ``version<N>.line<K>`` per line of it (files are read in the active project)."""
        texts = cls._texts(params) or []
        names = (["title"] if params.title else []) + ["listing"] + [f"version{n}" for n in range(1, len(params.versions) + 1)]
        return names + [f"version{n}.line{k}" for n, text in enumerate(texts, 1) for k in range(1, len(_lines(text)) + 1)]

    @classmethod
    def reveal_steps(cls, params: Any) -> list[RevealStep]:
        """One step per version (``version<N>``), an error when its changed lines show one."""
        texts = cls._texts(params)
        steps = []
        for n in range(1, len(params.versions) + 1):
            shown: list[str] = []
            if texts is not None:
                new = _lines(texts[n - 1])
                rows = diff_code(_lines(texts[n - 2]), new).changed if n > 1 else range(len(new))
                shown = [new[j] for j in rows]
            steps.append(RevealStep(f"version{n}", "error" if has_error_text(shown) else None))
        return steps

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super(CodeListing, cls).validate_project(params, project)   # not code's: no code / path here
        for k, version in enumerate(params.versions):
            if version.path is not None and not (project.root / version.path).is_file():
                problems.append(f"versions[{k}].path: file not found: {version.path} (looked for {project.root / version.path})")
        if problems:
            return problems
        texts = cls._texts(params, project)
        if texts is None:
            return ["versions: a file could not be read as UTF-8 text"]
        try:
            params.check_versions(texts)
        except ValueError as exc:
            problems.append(str(exc))
        return problems

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = type(self).validate_project(p, self.project)
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        versions = [_lines(text) for text in type(self)._texts(p, self.project) or []]
        first_path = next((v.path for v in p.versions if v.path is not None), None)
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)   # header band, 1.3x in a vertical frame
            body = body.below(title, gap=0.45)
        listings, groups = self._fit_listings(versions, lexer_name(p.language, first_path), body)
        self._place(listings, body)
        self._versions, self._listings, self._groups = versions, listings, groups
        for listing in listings:
            listing.code_lines.set_z_index(2)
            if p.line_numbers:
                listing.line_numbers.set_z_index(2)
        self._changed = [list(range(len(versions[0])))] + [diff_code(versions[k - 1], versions[k]).changed for k in range(1, len(versions))]
        color = self.theme.color(p.highlight_color)
        marked = any(v.highlight is not None for v in p.versions)
        opacity = readable_band(self, [row for listing in listings for row in listing.code_lines], color) if marked else BAND_OPACITIES[0]
        self._bands = [self._version_bands(k, color, opacity) for k in range(len(versions))]
        self._at: int | None = None
        self._top: Mobject | None = None
        version_targets = self._register(title)
        for k in range(len(versions)):   # after registering: targets keep the full look
            self._dim(k)
        heading = self.find_targets("title")[0] if title is not None else None
        waiting = self._revealed_by_actions(version_targets)

        def step(k: int) -> Callable[[], list[Animation]]:
            def build() -> list[Animation]:
                if k in waiting:
                    return []
                anims = self._go(k)
                return anims + (self.entrance(heading) if k == 0 and heading is not None else [])

            return build

        self.reveal([step(k) for k in range(len(versions))], fraction=0.6, cap=MORPH_SECONDS)
        self.finish()

    def _place(self, listings: list[Code], body: Region) -> None:
        """Every version centred across ``body``, all with the top of the tallest when it is
        centred (lines a change keeps in place then move only sideways, if at all)."""
        top = body.center[1] + max(m.height for m in listings) / 2
        for listing in listings:
            listing.shift(RIGHT * (body.center[0] - listing.get_center()[0]) + UP * (top - listing.get_top()[1]))

    def _rows(self, k: int, lines: list[int]) -> set[int]:
        """The physical rows of version ``k``'s (0-based) original ``lines``."""
        return {row for line in lines for row in self._groups[k][line]}

    def _chosen(self, k: int) -> set[int] | None:
        """The rows version ``k``'s highlight marks (``None``: no highlight)."""
        spec = self.params.versions[k].highlight
        if spec is None:
            return None
        lines = self._changed[k] if spec == CHANGED else [n - 1 for n in parse_line_spec(spec)]
        return self._rows(k, lines)

    def _version_bands(self, k: int, color: str, opacity: float) -> VGroup:
        chosen = self._chosen(k)
        if not chosen:
            return VGroup()
        wrapped = len(self._groups[k]) != len(self._listings[k].code_lines)
        return listing_bands(self._listings[k], chosen, color, opacity, numbered=self.params.line_numbers, wrapped=wrapped)

    def _dim(self, k: int) -> None:
        """Dim the rows version ``k``'s highlight leaves out."""
        chosen = self._chosen(k)
        if chosen is None:
            return
        listing = self._listings[k]
        parts = [listing.code_lines] + ([listing.line_numbers] if self.params.line_numbers else [])
        for paragraph in parts:
            for row, m in enumerate(paragraph):
                if row not in chosen:
                    m.set_opacity(DIMMED)

    def _register(self, title: Mobject | None) -> list[list[Target]]:
        """The targets, at full opacity; returns each version's own targets."""
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title, shift=UP * 0.12)])
        self.target("listing", VGroup(*self._listings), entrance=lambda: self._go(0))
        out = []
        for k, listing in enumerate(self._listings):
            show = lambda k=k: self._go(k)
            own = [self.target(f"version{k + 1}", listing, entrance=show)]
            for line, rows in enumerate(self._groups[k]):
                parts = [listing.code_lines[j] for j in rows] + ([listing.line_numbers[j] for j in rows] if self.params.line_numbers else [])
                own.append(self.target(f"version{k + 1}.line{line + 1}", VGroup(*parts), entrance=show))
            out.append(own)
        self._morph_targets = {id(t) for own in out for t in own}
        return out

    def entrance_time(self, target: Target) -> float | None:
        """A ``reveal`` action morphs to a version (or a line of one) in :data:`MORPH_SECONDS`."""
        if id(target) in getattr(self, "_morph_targets", ()):
            return MORPH_SECONDS
        return super().entrance_time(target)

    def _revealed_by_actions(self, version_targets: list[list[Target]]) -> set[int]:
        """The versions (0-based) a ``reveal`` action shows: the scene leaves their morph to it."""
        patterns = [p for action in self.action_uses("reveal") for p in _as_list(action.config.target)]
        revealed = {id(t) for pattern in patterns for t in self.find_targets(pattern)}
        return {k for k, own in enumerate(version_targets) if k and any(id(t) in revealed for t in own)}

    def _group(self, k: int) -> Group:
        return Group(self._listings[k], self._bands[k])

    def _go(self, k: int) -> list[Animation]:
        """The animations to version ``k`` (0-based): the window fades in with it, or the shown
        version morphs into it; nothing when it (or a later one) already shows."""
        if self._at is not None and k <= self._at:
            return []
        old, self._at = self._at, k
        new = self._group(k)
        if old is None:
            self._top = new
            return [FadeIn(new, shift=UP * 0.12)]
        anims = self._morph(old, k)
        top, self._top = self._top, new
        return [_Morph(anims, remove=[top], add=new)]

    def _morph(self, a: int, b: int) -> list[Animation]:
        """Version ``a`` into version ``b``: kept glyphs and line numbers glide, removed ones
        fade, new ones grow in; the window and the bands follow."""
        old, new = self._listings[a], self._listings[b]
        diff = diff_code(self._versions[a], self._versions[b])
        glyphs_a, glyphs_b = self._glyphs(a), self._glyphs(b)
        anims: list[Animation] = [Transform(old.background, new.background.copy(), rate_func=during(*GLIDE))]
        kept_a: set[int] = set()
        kept_b: set[int] = set()
        for i, ga, j, gb in diff.glyphs:
            if ga < len(glyphs_a[i]) and gb < len(glyphs_b[j]):
                source, goal = glyphs_a[i][ga], glyphs_b[j][gb]
                anims.append(Transform(source, goal.copy(), rate_func=during(*GLIDE)))
                kept_a.add(id(source))
                kept_b.add(id(goal))
        if self.params.line_numbers:
            labels_a, labels_b = self._labels(a), self._labels(b)
            for n in range(min(len(labels_a), len(labels_b))):
                anims.append(Transform(labels_a[n], labels_b[n].copy(), rate_func=during(*GLIDE)))
                kept_a.add(id(labels_a[n]))
                kept_b.add(id(labels_b[n]))
            gone = labels_a[len(labels_b):]
            anims += [m.animate(rate_func=during(*FADE_OUT)).set_opacity(0) for m in gone]
            anims += [FadeIn(m, rate_func=during(*GROW_IN)) for m in labels_b[len(labels_a):]]
        for line in glyphs_a:
            anims += [m.animate(rate_func=during(*FADE_OUT)).set_opacity(0) for m in line if id(m) not in kept_a]
        if len(self._bands[a]):
            anims.append(self._bands[a].animate(rate_func=during(*FADE_OUT)).set_opacity(0))
        added = set(diff.added)
        for j, line in enumerate(glyphs_b):
            fresh = [m for m in line if id(m) not in kept_b]
            if not fresh:
                continue
            if j in added:   # a new line grows in from its left end
                group = VGroup(*fresh)
                anims.append(GrowFromPoint(group, group.get_left(), rate_func=during(*GROW_IN)))
            else:
                anims += [FadeIn(m, scale=0.6, rate_func=during(*GROW_IN)) for m in fresh]
        if len(self._bands[b]):
            anims.append(FadeIn(self._bands[b], rate_func=during(*GROW_IN)))
        return anims

    def _glyphs(self, k: int) -> list[list[Mobject]]:
        """Per original line of version ``k``: its glyphs, over all the rows it wraps into."""
        rows = self._listings[k].code_lines
        return [[glyph for row in group for glyph in rows[row].submobjects] for group in self._groups[k]]

    def _labels(self, k: int) -> list[Mobject]:
        """Version ``k``'s line number labels, one per original line."""
        numbers = self._listings[k].line_numbers
        return [numbers[group[0]] for group in self._groups[k]]


class _Morph(AnimationGroup):
    """Plays a morph's animations together; when it ends, the scene holds the new version's
    listing (one ``Code``, as the layout dump and lint read it) instead of the moved pieces."""

    def __init__(self, animations: list[Animation], remove: list[Mobject], add: Mobject, **kwargs: Any) -> None:
        super().__init__(*animations, **kwargs)
        self._remove, self._add = remove, add

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        # whole families: playing the group lifted parts of the old listing (those no animation
        # moves, e.g. a wrapped line's empty number) into the scene on their own
        gone = [self.group, *[anim.mobject for anim in self.animations if anim.is_introducer()], *self._remove]
        scene.remove(*[m for top in gone for m in top.get_family()])
        scene.add(self._add)
