"""The ``web`` scene's own lint rule (DESIGN.md §118.12): ``web_clipped``, page text cut by a box
on the page. The page's texts are layout objects like vidgen's own (``source: web``), so the
layout rules (``off_frame``, ``text_overlap``, ``min_font``, ``contrast``, ``overlay_overlap``,
``shorts_safe_area``...) check them too; this rule reads what only a page has: ``clipped`` (the
text's own box or an ancestor's with ``overflow`` other than visible cuts it, the commonest fault
of an HTML layout) and ``cut`` (the page's box cuts it where the page does not reach the frame's
edge, as with ``region: body``; at the frame's edge it is ``off_frame``'s)."""

from __future__ import annotations

from collections.abc import Iterator

from vidgen.config import WebClippedRule
from vidgen.lint.layout_rules import describe, object_box
from vidgen.lint.rules import Issue, StillContext, rule
from vidgen.web.layout import sides_text


@rule("web_clipped", default="error")
def web_clipped(ctx: StillContext, settings: WebClippedRule) -> Iterator[Issue]:
    """In a web scene, page text is cut by its container (overflow: hidden) or by the page's box."""
    tolerance = settings.tolerance * ctx.short_side
    for obj in ctx.objects:
        if obj.get("source") != "web":
            continue
        clipped = obj.get("clipped") or {}
        sides = {s: px for s, px in (clipped.get("sides") or {}).items() if px > tolerance}
        if sides:
            worst = max(sides.values())
            how = f"overflow: {clipped['overflow']}" if clipped.get("overflow") else "its overflow"
            yield Issue(
                f"{describe(obj)} is cut by its box {clipped['by']} ({how}) at the {sides_text(sides)} "
                f"({worst:.0f} px of the text hidden); shorten the text, make it smaller, or let the box grow "
                "(or `data-vidgen-lint=\"off\"` if it is cut on purpose)",
                object_box(obj), (obj,), value=round(worst, 1), limit=round(tolerance, 1),
            )
            continue
        cut = {s: px for s, px in (obj.get("cut") or {}).items() if px > tolerance}
        if cut:
            worst = max(cut.values())
            yield Issue(
                f"{describe(obj)} runs past the page's box at the {sides_text(cut)} ({worst:.0f} px of the text "
                "hidden); lay the page out within ctx.width x ctx.height (100vw x 100vh) or make the text smaller",
                object_box(obj), (obj,), value=round(worst, 1), limit=round(tolerance, 1),
            )
