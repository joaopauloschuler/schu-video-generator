"""One colour per concept (DESIGN.md §87.3): the video's ``terms:`` map.

``terms: {loss: accent, gradient: "#E07A5F", "learning rate": {color: primary, tex: '\\eta'}}``
gives each concept a colour (a theme colour token or hex). Wherever one of the words is drawn as
on-screen text by :func:`vidgen.layout.fit_text` or :func:`vidgen.helpers.T` (bullets, cards,
titles, chart and diagram labels, captions...), it is drawn in its colour; an equation colours the
TeX parts given as ``tex``. A scene with ``terms: false`` draws none of them.

Matching (:func:`term_spans`): whole words, any case, the term's words separated by any space,
with a plural ``s`` / ``es``; longer terms first, no overlaps. The terms in effect while a scene
is built are :func:`active_terms` (set by the scene, :func:`using_terms`). No manim import.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidgen.config import SceneConfig, VideoConfig
    from vidgen.theme import Theme


@dataclass(frozen=True)
class Term:
    """A concept of ``terms:``: its words as written, its colour (``#RRGGBB``) and the TeX parts
    of equations that stand for it."""

    name: str
    color: str
    tex: tuple[str, ...] = ()


_active: tuple[Term, ...] = ()


def term_settings(config: VideoConfig) -> list[tuple[str, str, tuple[str, ...]]]:
    """``(term, colour as written, tex parts)`` of the config's ``terms:``, in order."""
    out = []
    for name, value in config.terms.items():
        if isinstance(value, str):
            out.append((name, value, ()))
        else:
            out.append((name, value.color, tuple(value.tex_parts())))
    return out


def resolve_terms(config: VideoConfig, theme: Theme) -> tuple[Term, ...]:
    """The config's terms with their colours resolved against ``theme``."""
    return tuple(Term(name, theme.color(color), tex) for name, color, tex in term_settings(config))


def scene_terms(config: VideoConfig, scene: SceneConfig, theme: Theme) -> tuple[Term, ...]:
    """The terms a scene draws in their colours: none with ``terms: false`` on the scene."""
    return resolve_terms(config, theme) if scene.terms else ()


def active_terms() -> tuple[Term, ...]:
    """The terms in effect for text built now (empty outside a scene of a video with ``terms:``)."""
    return _active


def set_active_terms(terms: Sequence[Term]) -> None:
    """Make ``terms`` the ones in effect (a scene does this when it is created)."""
    global _active
    _active = tuple(terms)


@contextmanager
def using_terms(terms: Sequence[Term]) -> Iterator[None]:
    """Make ``terms`` the ones in effect inside the ``with`` block; the previous ones after it."""
    global _active
    saved = _active
    _active = tuple(terms)
    try:
        yield
    finally:
        _active = saved


@lru_cache(maxsize=256)
def _pattern(name: str) -> re.Pattern[str]:
    words = name.split()
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?:e?s)?(?!\w)", re.IGNORECASE)


def term_spans(text: str, terms: Sequence[Term]) -> list[tuple[int, int, Term]]:
    """``(start, end, term)`` of every place ``text`` says a term, in text order: whole words,
    any case, a plural ``s`` / ``es`` included; a longer term wins over one inside it."""
    taken: list[tuple[int, int, Term]] = []
    for term in sorted(terms, key=lambda t: -len(t.name)):
        for match in _pattern(term.name).finditer(text):
            start, end = match.span()
            if all(end <= a or start >= b for a, b, _ in taken):
                taken.append((start, end, term))
    return sorted(taken, key=lambda span: span[0])


def find_term(text: str, terms: Sequence[Term]) -> Term | None:
    """The first term ``text`` says, or ``None``."""
    spans = term_spans(text, terms)
    return spans[0][2] if spans else None


def term_t2c(text: str, terms: Sequence[Term], taken: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Manim ``t2c`` entries (``"[a:b]" -> colour``) for the terms ``text`` says, leaving out the
    places an entry of ``taken`` (an explicit ``t2c``: slices or substrings) colours already."""
    claimed = _claimed(text, taken or {})
    return {
        f"[{start}:{end}]": term.color
        for start, end, term in term_spans(text, terms)
        if all(end <= a or start >= b for a, b in claimed)
    }


def _claimed(text: str, t2c: Mapping[str, Any]) -> list[tuple[int, int]]:
    """The ``(start, end)`` places a Manim ``t2c`` colours in ``text``."""
    spans = []
    for key in t2c:
        m = re.fullmatch(r"\[(-?\d*):(-?\d*)\]", key)
        if m:
            start = int(m[1]) if m[1] else 0
            end = int(m[2]) if m[2] else len(text)
            spans.append((len(text) + start if start < 0 else start, len(text) + end if end < 0 else end))
            continue
        index = text.find(key) if key else -1
        while index != -1:
            spans.append((index, index + len(key)))
            index = text.find(key, index + len(key))
    return spans


def term_color_problems(config: VideoConfig, theme: Theme) -> list[tuple[str, str]]:
    """``(where, message)`` for each ``terms:`` colour that is not a theme colour."""
    from vidgen.errors import VidgenError

    problems = []
    for name, color, _ in term_settings(config):
        try:
            theme.color(color)
        except VidgenError as exc:
            problems.append((f"terms.{name}", str(exc)))
    return problems


def _flat_tex(tex: str) -> str:
    return "".join(tex.split())


def term_conflicts(config: VideoConfig, theme: Theme) -> list[tuple[str, str | None, str]]:
    """``(scene id, beat id or None, message)`` for each scene setting that colours one of the
    video's terms otherwise than ``terms:`` does: a title's ``highlight`` (``highlight_color``),
    an ``equation_derivation``'s ``colors``, a ``line_chart`` series' ``color``, a
    ``function_plot`` function's or area's ``color`` (its name or label naming the term) and a
    ``callout``'s ``color`` on a label naming the term. Scenes with ``terms: false`` are skipped.
    Colours that are not theme colours are left to ``vidgen validate``."""
    from vidgen.errors import VidgenError

    def hexed(color: Any) -> str | None:
        try:
            return theme.color(color).upper() if isinstance(color, str) else None
        except VidgenError:
            return None

    terms = resolve_terms(config, theme)
    if not terms:
        return []
    out: list[tuple[str, str | None, str]] = []

    def check(scene_id: str, beat_id: str | None, text: Any, color: Any, setting: str) -> None:
        if not isinstance(text, str):
            return
        shown = hexed(color)
        for _, _, term in term_spans(text, terms):
            if shown is not None and shown != term.color.upper():
                out.append((scene_id, beat_id, f"{setting} colours the term '{term.name}' {color} (terms: {term.color}); use the term's colour, or leave the setting out"))

    for scene in config.scenes:
        if not scene.terms:
            continue
        params = scene.params
        if scene.type == "title" and params.get("highlight"):
            check(scene.id, None, params["highlight"], params.get("highlight_color", "highlight"), "highlight_color")
        if scene.type == "line_chart" and isinstance(params.get("series"), list):
            for entry in params["series"]:
                if isinstance(entry, dict) and entry.get("color"):
                    check(scene.id, None, entry.get("name"), entry["color"], f"series '{entry.get('name')}' color")
        if scene.type == "function_plot":
            for key, kind in (("functions", "function"), ("areas", "area")):
                for entry in params.get(key) or []:
                    if isinstance(entry, dict) and entry.get("color"):
                        for text in (entry.get("name"), entry.get("label")):
                            check(scene.id, None, text, entry["color"], f"{kind} '{entry.get('name') or entry.get('label') or entry.get('expr')}' color")
        if scene.type == "equation_derivation" and isinstance(params.get("colors"), dict):
            for tex, color in params["colors"].items():
                for term in terms:
                    if any(_flat_tex(part) == _flat_tex(str(tex)) for part in term.tex) and hexed(color) not in (None, term.color.upper()):
                        out.append((scene.id, None, f"colors colours '{tex}', the TeX of the term '{term.name}', {color} (terms: {term.color}); leave it out of colors"))
        for beat in scene.beats:
            for action in beat.actions:
                options = action.options
                if action.action == "callout" and options.get("color") and options.get("label"):
                    check(scene.id, beat.id, options["label"], options["color"], "a callout's color")
    return out
