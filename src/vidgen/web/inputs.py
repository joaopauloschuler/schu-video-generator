"""What a ``web`` scene's page is given besides time (DESIGN.md §118.9): the theme (``ctx.theme``
and CSS custom properties on ``:root``, with ``@font-face`` rules for vidgen's bundled fonts),
the author's ``data:`` values (``ctx.data``), the beats (``ctx.beats``), the video's shape
(``ctx.aspect``, ``ctx.orientation`` and ``data-aspect`` / ``data-orientation`` on ``<html>``,
§118.11) and the import map that makes ``import * as THREE from "three"`` load the bundled
three.js. No browser here.
"""

from __future__ import annotations

import json
import math
import re
from math import gcd
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from vidgen.fonts import BUILTIN_ROLES, BUNDLED_FAMILIES, ProjectFont
from vidgen.scales import frame_orientation
from vidgen.web.libs import LIB_FOLDER, NOT_SHIPPED, WEB_LIBS
from vidgen.web.loaded import ADDONS_FOLDER, VIDGEN_PREFIX

#: The import map vidgen puts in a page: the bare specifier ``three`` is the bundled three.js,
#: ``three/addons/...`` (and the older ``three/examples/jsm/...``) its shipped add-ons, whose own
#: ``import ... from "three"`` resolves through the same map to the same module; the name of each
#: shipped library (``animejs``, ``d3``..., :data:`vidgen.web.libs.WEB_LIBS`) is its file; a name of
#: :data:`vidgen.web.libs.NOT_SHIPPED` points at a file vidgen does not have, so that the render's
#: error can say why and what to do.
IMPORT_MAP: dict[str, dict[str, str]] = {"imports": {
    "three": f"/{VIDGEN_PREFIX}three/three.module.js",
    "three/addons/": f"/{VIDGEN_PREFIX}three/{ADDONS_FOLDER}/",
    "three/examples/jsm/": f"/{VIDGEN_PREFIX}three/{ADDONS_FOLDER}/",
    **{specifier: f"/{VIDGEN_PREFIX}{LIB_FOLDER}/{lib.package}/{lib.entry}" for lib in WEB_LIBS for specifier in lib.specifiers},
    **{package: f"/{VIDGEN_PREFIX}{LIB_FOLDER}/{package}/index.js" for package in NOT_SHIPPED},
}}
#: The id of the ``<style>`` element holding the theme's custom properties and font faces.
THEME_STYLE_ID = "vidgen-theme"
#: Aspect names a frame is given when its width / height is within :data:`ASPECT_TOLERANCE` of
#: one (``--format`` and the gallery use ``16:9`` and ``9:16``); else the reduced ``W:H``.
NAMED_ASPECTS: tuple[str, ...] = ("16:9", "9:16", "1:1", "4:5", "5:4", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21")
ASPECT_TOLERANCE = 0.01
#: The window widths ``design_width:`` takes (CSS pixels): from a narrow phone to an 8K screen.
DESIGN_WIDTH_MIN, DESIGN_WIDTH_MAX = 200, 8192


def design_width_problem(value: Any) -> str | None:
    """Why ``value`` is not a usable ``design_width:`` (a whole number of CSS pixels within
    :data:`DESIGN_WIDTH_MIN` .. :data:`DESIGN_WIDTH_MAX`), or ``None``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not value.is_integer()):
        return f"{value!r} is not a whole number of CSS pixels (the window width the page was designed for, e.g. 1280)"
    if not DESIGN_WIDTH_MIN <= value <= DESIGN_WIDTH_MAX:
        return (f"{int(value)} is not a window width a page is designed for (give the width in CSS pixels, "
                f"{DESIGN_WIDTH_MIN} to {DESIGN_WIDTH_MAX}, e.g. 1280 for a desktop page or 390 for a phone page)")
    return None


def design_width_of(params: Any) -> int | None:
    """The ``design_width:`` of a ``web`` scene's params (a model or a mapping), ``None`` when unset."""
    value = params.get("design_width") if isinstance(params, Mapping) else getattr(params, "design_width", None)
    return int(value) if value is not None else None


def page_viewport(size: tuple[int, int], design_width: int | None = None) -> tuple[tuple[int, int], float]:
    """The page's window (CSS px) and its device scale factor for screenshots of ``size`` (output
    px; §118.17). Without ``design_width``: ``size`` and 1. With it: a window ``design_width``
    wide at the scale ``size[0] / design_width`` (the page's ``devicePixelRatio``), as high as
    ``size``'s aspect gives, rounded up to a whole CSS pixel so that the screenshot is never
    shorter than ``size`` (:func:`vidgen.web.page.fit_pixels` cuts off what is over)."""
    if design_width is None:
        return size, 1.0
    scale = size[0] / design_width
    return (design_width, max(1, math.ceil(size[1] / scale - 1e-6))), scale


def css_height(size: tuple[int, int], design_width: int | None = None) -> float:
    """The height of the picture of ``size`` in the page's CSS pixels (:func:`page_viewport`'s
    window height before it is rounded up)."""
    return float(size[1]) if design_width is None else size[1] * design_width / size[0]


def page_theme(theme: Any, px_per_point: float, project_fonts: Sequence[ProjectFont] = ()) -> dict[str, Any]:
    """``ctx.theme`` of a :class:`vidgen.theme.Theme`: ``preset``, ``background``, ``colors``
    (name -> hex), ``palette`` (hex list), ``fonts`` (``sans`` / ``serif`` / ``mono`` and every
    role -> family name), ``sizes`` (name -> CSS pixels; ``px_per_point`` = the frame's pixel
    height over 72 times its height in Manim units, so a size draws text as tall as vidgen's)
    and ``font_files`` (the project's own fonts, :func:`vidgen.fonts.project_fonts`: per file
    its ``family``, ``weight`` (``"400"``; a variable font's range ``"300 700"``), ``style`` and
    ``url``, as declared to the page in an ``@font-face``)."""
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
        "font_files": [
            {"family": font.family, "weight": " ".join(str(w) for w in dict.fromkeys(font.weight)),
             "style": "italic" if font.italic else "normal", "url": "/" + quote(font.rel)}
            for font in project_fonts
        ],
    }


def aspect_name(width: int, height: int) -> str:
    """The aspect of a ``width`` x ``height`` frame (px) as a name: ``16:9`` (also 854x480),
    ``9:16``, ``1:1``... (:data:`NAMED_ASPECTS`), else the reduced ``W:H``."""
    ratio = width / height
    for name in NAMED_ASPECTS:
        w, h = (int(part) for part in name.split(":"))
        if abs(ratio / (w / h) - 1) <= ASPECT_TOLERANCE:
            return name
    k = gcd(width, height)
    return f"{width // k}:{height // k}"


def page_shape(frame: tuple[int, int], region: str = "bleed") -> dict[str, Any]:
    """The video's shape as the page is given it (§118.11): ``aspect`` (:func:`aspect_name`),
    ``orientation`` (``landscape`` / ``portrait`` / ``square``, the rule vidgen's own layouts
    use), ``frame`` (the video frame's ``{width, height}`` in px) and ``region`` (``bleed`` or
    ``body``: where the page is drawn)."""
    width, height = frame
    return {"aspect": aspect_name(width, height), "orientation": frame_orientation(width, height),
            "frame": {"width": width, "height": height}, "region": region}


def shape_script(shape: Mapping[str, Any]) -> str:
    """A script setting ``data-aspect`` and ``data-orientation`` on ``<html>`` while the page is
    parsed (before its styles and scripts), so CSS can switch layout by the video's shape."""
    attributes = {"aspect": shape["aspect"], "orientation": shape["orientation"]}
    sets = "".join(f"e.dataset.{name}={json.dumps(value)};" for name, value in attributes.items())
    return f"<script>((e)=>{{{sets}}})(document.documentElement)</script>"


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


def project_font_faces(font_files: Sequence[Mapping[str, str]]) -> list[str]:
    """One ``@font-face`` rule per font file of the project (``ctx.theme.font_files``), so a
    page's ``font-family: "<family>"`` finds it with no rule of its own."""
    return [f'@font-face {{ font-family: {json.dumps(font["family"])}; src: url("{font["url"]}"); '
            f'font-weight: {font["weight"]}; font-style: {font["style"]}; }}' for font in font_files]


def declared_families(theme: Mapping[str, Any]) -> set[str]:
    """The font families vidgen's style sheet declares to the page: the bundled ones the theme
    names and those of the project's font files."""
    bundled = {family.family for family in BUNDLED_FAMILIES} & set(theme["fonts"].values())
    return bundled | {font["family"] for font in theme.get("font_files", ())}


def theme_css(theme: Mapping[str, Any]) -> str:
    """The style sheet vidgen puts first in a page: the bundled fonts the theme names, the
    project's own fonts (after them, so a project file of the same family wins) and the theme's
    custom properties on ``:root``."""
    faces = font_faces(sorted(set(theme["fonts"].values()))) + project_font_faces(theme.get("font_files", ()))
    props = "".join(f"\n  {name}: {value};" for name, value in theme_properties(theme).items())
    return "\n".join([*faces, f":root {{{props}\n}}"])


def page_head(theme: Mapping[str, Any] | None, shape: Mapping[str, Any] | None = None) -> str:
    """What vidgen inserts at the start of the page's ``<head>``: the theme's style sheet (when
    there is a theme), the script setting the shape attributes (when there is a ``shape``,
    :func:`shape_script`) and the import map."""
    style = f'<style id="{THEME_STYLE_ID}">\n{theme_css(theme)}\n</style>' if theme is not None else ""
    script = shape_script(shape) if shape is not None else ""
    return f'{style}{script}<script type="importmap">{json.dumps(IMPORT_MAP)}</script>'


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


def scene_page_inputs(scene: Any, spans: Sequence[Any], css_scale: float = 1.0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """``ctx.theme`` and ``ctx.beats`` of a ``web`` scene (a ``NarratedScene`` being rendered)
    whose beats are ``spans`` on its clock (:func:`vidgen.browser.timing.clip_plan`); the word
    times are the captions' (the stored alignment, else estimated, :func:`vidgen.speech.beat_word_times`).
    ``css_scale``: output pixels per CSS pixel of the page (:func:`page_viewport`; the theme's
    sizes are given in CSS pixels that draw text as tall as vidgen's)."""
    from manim import config

    from vidgen.fonts import project_fonts
    from vidgen.speech import beat_word_times

    project = scene.project
    words = [
        beat_word_times(project.audio_dir, beat.id, beat.text, span.start, span.end, project.spoken(beat), project.config.language)
        for beat, span in zip(scene.beats, spans)
    ]
    theme = page_theme(scene.theme, float(config.pixel_height) / (72 * float(config.frame_height) * css_scale), project_fonts(project.root))
    return theme, page_beats(spans, scene.beats, words)


__all__ = ["ASPECT_TOLERANCE", "DESIGN_WIDTH_MAX", "DESIGN_WIDTH_MIN", "IMPORT_MAP", "NAMED_ASPECTS", "THEME_STYLE_ID", "aspect_name",
           "css_height", "declared_families", "design_width_of", "design_width_problem", "font_faces",
           "json_problem", "page_beats", "page_head", "page_shape", "page_theme", "page_viewport", "project_font_faces", "scene_page_inputs",
           "shape_script", "theme_css", "theme_properties", "with_head"]
