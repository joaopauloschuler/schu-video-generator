"""The lint rule on the video's concept colours (``terms:``, DESIGN.md §87.3).

``concept_colors`` reads the config, not a still: more different colours than ``max_colors``,
a colour below ``min_contrast`` on the theme background (both reported on the first scene that
draws the terms), and a scene setting that colours a term otherwise (on that scene and beat).
The runner fills :attr:`SceneContext.term_issues` with :func:`term_issues`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vidgen.config import ConceptColorsRule
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.terms import resolve_terms, term_conflicts

if TYPE_CHECKING:
    from vidgen.config import VideoConfig
    from vidgen.theme import Theme


def term_issues(config: VideoConfig, theme: Theme, scene_id: str, settings: ConceptColorsRule) -> list[tuple[str | None, str, float | None, float | None]]:
    """``(beat id, message, value, limit)`` of the ``concept_colors`` findings of one scene."""
    out: list[tuple[str | None, str, float | None, float | None]] = []
    terms = resolve_terms(config, theme)
    first = next((s.id for s in config.scenes if s.terms), None)
    if terms and scene_id == first:
        colors = {t.color.upper() for t in terms}
        if len(colors) > settings.max_colors:
            out.append((None, f"terms: uses {len(colors)} different colours; more than {settings.max_colors} and no concept stands out (give fewer concepts a colour, or let related ones share one)", float(len(colors)), float(settings.max_colors)))
        for term in terms:
            ratio = contrast_ratio(hex_rgb(term.color), hex_rgb(theme.background))
            if ratio < settings.min_contrast:
                out.append((None, f"the term '{term.name}' ({term.color}) has contrast {ratio:.2f}:1 on the background {theme.background}; pick a colour that reads (at least {settings.min_contrast:g}:1)", round(ratio, 2), settings.min_contrast))
    out.extend((beat, message, None, None) for where, beat, message in term_conflicts(config, theme) if where == scene_id)
    return out


@rule("concept_colors", scope="scene")
def concept_colors(ctx: SceneContext, settings: ConceptColorsRule) -> Iterator[Issue]:
    """The video's concept colours: too many, too faint, or a term coloured otherwise in a scene."""
    starts = {beat["id"]: beat["start"] for beat in ctx.beats}
    for beat, message, value, limit in ctx.term_issues:
        yield Issue(message, None, value=value, limit=limit, beat=beat or ctx.beat_at(0.0), time=float(starts.get(beat, 0.0)))
