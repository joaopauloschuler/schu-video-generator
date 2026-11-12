"""What a ``web`` scene's page is given besides time (DESIGN.md §118.9): the theme (``ctx.theme``
and CSS custom properties on ``:root``, with ``@font-face`` rules for vidgen's bundled fonts),
the author's ``data:`` values (``ctx.data``), the beats (``ctx.beats``) and the import map that
makes ``import * as THREE from "three"`` load the bundled three.js. No browser here.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from vidgen.fonts import BUILTIN_ROLES, BUNDLED_FAMILIES
from vidgen.web.loaded import VIDGEN_PREFIX

#: The import map vidgen puts in a page: the bare specifier ``three`` is the bundled three.js.
IMPORT_MAP: dict[str, dict[str, str]] = {"imports": {"three": f"/{VIDGEN_PREFIX}three/three.module.js"}}
#: The id of the ``<style>`` element holding the theme's custom properties and font faces.
THEME_STYLE_ID = "vidgen-theme"


def page_theme(theme: Any, px_per_point: float) -> dict[str, Any]:
    """``ctx.theme`` of a :class:`vidgen.theme.Theme`: ``preset``, ``background``, ``colors``
    (name -> hex), ``palette`` (hex list), ``fonts`` (``sans`` / ``serif`` / ``mono`` and every
    role -> family name) and ``sizes`` (name -> CSS pixels; ``px_per_point`` = the frame's pixel
    height over 72 times its height in Manim units, so a size draws text as tall as vidgen's)."""
    roles = sorted({*BUILTIN_ROLES, *theme.fonts})
    fonts = {role: theme.font_for(role) for role in roles}
    fonts.update({"sans": theme.font, "serif": theme.font_serif, "mono": theme.font_mono})
    return {
        "preset": theme.preset,
        "background": theme.background,
        "colors": dict(theme.colors),
        "palette": list(theme.palette),
        "fonts": fonts,
        "sizes": {name: round(float(value) * px_per_point, 3) for name, value in theme.sizes.items()},
    }


def _generic(family: str, fonts: Mapping[str, str]) -> str:
    """The CSS generic family to fall back on: ``serif`` / ``monospace`` for the theme's serif
    and mono families, else ``sans-serif``."""
    if family == fonts.get("mono"):
        return "monospace"
    return "serif" if family == fonts.get("serif") else "sans-serif"


def font_faces(families: Sequence[str]) -> list[str]:
    """``@font-face`` rules for the bundled families among ``families`` (regular, bold and
    italic files, served from ``/__vidgen__/fonts/``)."""
    rules = []
    for family in BUNDLED_FAMILIES:
        if family.family not in families:
            continue
        styles = [(family.regular, 400, "normal"), (family.bold, 700, "normal")]
        styles += [(family.italic, 400, "italic")] if family.italic else []
        for name, weight, style in styles:
            url = f"/{VIDGEN_PREFIX}fonts/{family.folder}/{name}"
            rules.append(f'@font-face {{ font-family: {json.dumps(family.family)}; src: url("{url}") format("truetype"); '
                         f"font-weight: {weight}; font-style: {style}; }}")
    return rules


def theme_properties(theme: Mapping[str, Any]) -> dict[str, str]:
    """The CSS custom properties of ``ctx.theme`` (name -> value), in the documented order:
    ``--vidgen-<color>``, ``--vidgen-background``, ``--vidgen-palette-<i>``,
    ``--vidgen-font-<role or sans/serif/mono>``, ``--vidgen-size-<name>``. Theme names keep their
    underscores, so a name never collides with another kind's ``-`` prefix."""
    fonts = theme["fonts"]
    props = {f"--vidgen-{name}": value for name, value in theme["colors"].items()}
    props["--vidgen-background"] = theme["background"]
    props.update({f"--vidgen-palette-{i}": value for i, value in enumerate(theme["palette"])})
    props.update({f"--vidgen-font-{role}": f"{json.dumps(family)}, {_generic(family, fonts)}" for role, family in fonts.items()})
    props.update({f"--vidgen-size-{name}": f"{value:g}px" for name, value in theme["sizes"].items()})
    return props


def theme_css(theme: Mapping[str, Any]) -> str:
    """The style sheet vidgen puts first in a page: the bundled fonts the theme names and its
    custom properties on ``:root``."""
    faces = font_faces(sorted(set(theme["fonts"].values())))
    props = "".join(f"\n  {name}: {value};" for name, value in theme_properties(theme).items())
    return "\n".join([*faces, f":root {{{props}\n}}"])


def page_head(theme: Mapping[str, Any] | None) -> str:
    """What vidgen inserts at the start of the page's ``<head>``: the theme's style sheet (when
    there is a theme) and the import map."""
    style = f'<style id="{THEME_STYLE_ID}">\n{theme_css(theme)}\n</style>' if theme is not None else ""
    return f'{style}<script type="importmap">{json.dumps(IMPORT_MAP)}</script>'


_HEAD = re.compile(rb"<head(\s[^>]*)?>", re.IGNORECASE)
_HTML = re.compile(rb"<html(\s[^>]*)?>", re.IGNORECASE)
_DOCTYPE = re.compile(rb"<!doctype[^>]*>", re.IGNORECASE)


def with_head(html: bytes, head: str) -> bytes:
    """``html`` with ``head`` inserted right after its ``<head>`` tag (else after ``<html>``,
    else after the doctype, else at the start), so it comes before any script or style of the page."""
    for tag in (_HEAD, _HTML, _DOCTYPE):
        match = tag.search(html)
        if match is not None:
            return html[:match.end()] + head.encode("utf-8") + html[match.end():]
    return head.encode("utf-8") + html


def json_problem(value: Any, path: str = "data") -> str | None:
    """The first part of ``value`` that is not a JSON value (``"data.when: 2026-01-01 is a
    date, not a JSON value ..."``), or ``None``."""
    if value is None or isinstance(value, (bool, str, int)):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else f"{path}: {value} is not a finite number"
    if isinstance(value, (list, tuple)):
        return next((p for i, item in enumerate(value) if (p := json_problem(item, f"{path}[{i}]")) is not None), None)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path}: the key {key!r} is not text (quote it in the YAML)"
            problem = json_problem(item, f"{path}.{key}")
            if problem is not None:
                return problem
        return None
    return (f"{path}: {value} is a {type(value).__name__}, not a JSON value "
            "(use text, numbers, true/false, null, lists and mappings; quote a date)")


def page_beats(spans: Sequence[Any], beats: Sequence[Any], words: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
    """``ctx.beats``: per beat its ``id``, ``index``, ``start`` and ``end`` (seconds on the scene's
    clock: when its narration starts and ends), ``text`` and ``words`` (``{text, start, end}``)."""
    return [
        {"id": span.id, "index": i, "start": round(span.start, 6), "end": round(span.end, 6), "text": beat.text,
         "words": [{"text": w.text, "start": round(w.start, 6), "end": round(w.end, 6)} for w in timed]}
        for i, (span, beat, timed) in enumerate(zip(spans, beats, words))
    ]


def scene_page_inputs(scene: Any, spans: Sequence[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``ctx.theme`` and ``ctx.beats`` of a ``web`` scene (a ``NarratedScene`` being rendered)
    whose beats are ``spans`` on its clock (:func:`vidgen.browser.timing.clip_plan`); the word
    times are the captions' (the stored alignment, else estimated, :func:`vidgen.speech.beat_word_times`)."""
    from manim import config

    from vidgen.speech import beat_word_times

    project = scene.project
    words = [
        beat_word_times(project.audio_dir, beat.id, beat.text, span.start, span.end, project.spoken(beat), project.config.language)
        for beat, span in zip(scene.beats, spans)
    ]
    theme = page_theme(scene.theme, float(config.pixel_height) / (72 * float(config.frame_height)))
    return theme, page_beats(spans, scene.beats, words)


__all__ = ["IMPORT_MAP", "THEME_STYLE_ID", "font_faces", "json_problem", "page_beats", "page_head", "page_theme", "scene_page_inputs", "theme_css",
           "theme_properties", "with_head"]
