"""Echo characters (DESIGN.md §102.6): a character's other self from another timeline or a
memory seen overlapping the present — a translucent figure that keeps its own costume.

Unlike a hologram (§100.3), which maps every colour through one tint, an echo keeps the colours
it was drawn with (a uniform stays a uniform, a gold medal gold), moved a little towards the
echo's colour and made translucent; its outlines glow in a light tint of that colour. The stage
leaves an echo out of its light grade (it shines the same at night) and flickers it softly like
a hologram; it appears and goes with the ``materialise`` / ``dematerialise`` actions.
"""

from __future__ import annotations

from manim import ManimColor, Mobject, VMobject

#: The default colour and opacity (``echo: true``): a violet shimmer, half seen through.
ECHO_COLOR = "#B48CFF"
ECHO_OPACITY = 0.5
#: How far the fills move towards the echo's colour (they keep most of their own).
ECHO_TINT = 0.22
#: How far the outlines go from the echo's colour towards white, and their opacity (a share of
#: the drawn one).
ECHO_EDGE_WHITE = 0.35
ECHO_EDGE_OPACITY = 0.9
#: The attribute an echo character carries: its (colour, opacity).
ECHO_ATTRIBUTE = "echo"


def _mix(a: str, b: str, share: float) -> str:
    return ManimColor(a).interpolate(ManimColor(b), share).to_hex()


def echo_fill(original: str, tint: str) -> str:
    """``original`` as an echo of colour ``tint`` shows it: :data:`ECHO_TINT` of the way to the tint."""
    return _mix(original, tint, ECHO_TINT)


def echo_edge(tint: str) -> str:
    """The outline colour of an echo of colour ``tint``: the tint :data:`ECHO_EDGE_WHITE` of the
    way to white."""
    return _mix(tint, "#FFFFFF", ECHO_EDGE_WHITE)


def apply_echo(figure: Mobject, color: str = ECHO_COLOR, opacity: float = ECHO_OPACITY) -> Mobject:
    """Draw ``figure`` (a character, every shape it may show) as an echo of ``color`` (a hex) at
    fill ``opacity``; marks it with :data:`ECHO_ATTRIBUTE`. Returns it."""
    edge = echo_edge(color)
    for member in figure.get_family():
        if not isinstance(member, VMobject):
            continue
        fill_opacity = float(member.get_fill_opacity())
        if fill_opacity > 0:
            member.set_fill(echo_fill(member.get_fill_color().to_hex(), color), opacity=fill_opacity * opacity, family=False)
        stroke_opacity = float(member.get_stroke_opacity())
        if stroke_opacity > 0 and member.get_stroke_width() > 0:
            member.set_stroke(edge, opacity=stroke_opacity * ECHO_EDGE_OPACITY, family=False)
    setattr(figure, ECHO_ATTRIBUTE, (color, opacity))
    return figure


def is_echo(figure: Mobject) -> bool:
    """Whether ``figure`` was drawn by :func:`apply_echo`."""
    return getattr(figure, ECHO_ATTRIBUTE, None) is not None


__all__ = ["ECHO_ATTRIBUTE", "ECHO_COLOR", "ECHO_EDGE_OPACITY", "ECHO_EDGE_WHITE", "ECHO_OPACITY", "ECHO_TINT", "apply_echo", "echo_edge",
           "echo_fill", "is_echo"]
