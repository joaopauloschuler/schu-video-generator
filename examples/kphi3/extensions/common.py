"""kphi3-specific drawing helpers shared by the scene modules (ported from the original common.py).

Generic helpers (``T``, ``MT``, ``column``, ``edges``, ``dense_pairs``, ``grouped_pairs``,
``counter``) come from ``vidgen.api``; colors are theme tokens defined in ``video.yaml``.
Only what is specific to this video lives here.
"""

from vidgen.api import *

#: Dark fills used for gradients and panels (not theme tokens: they are shades, not roles).
NAVY = "#1D3557"     # dark end of the "baseline" gradient (pixels, input channels)
BROWN = "#3B2A12"    # dark end of the "k2" gradient (output channels)
TOKEN_FILL = "#1A2230"
GOLD_FILL = "#2A2410"


def group_color(i: int) -> str:
    """Color of channel group ``i`` (``theme.palette``, wrapping)."""
    return current_theme().palette_color(i)


def mini_net(groups: int, w: float = 0.55, h: float = 0.5) -> VGroup:
    """A 4-to-4 icon network: dense (``groups == 1``, base color) or 2 colored groups."""
    a = column(4, 0, h / 3, r=0.035)
    b = column(4, w, h / 3, r=0.035)
    if groups == 1:
        e = edges(a, b, dense_pairs(4, 4), "base", 1.0, 0.8)
    else:
        e = VGroup(*[Line(a[i].get_center(), b[j].get_center(), stroke_width=1.6,
                          color=group_color(i // 2), stroke_opacity=0.9) for i, j in grouped_pairs(4, 2)])
    return VGroup(e, a, b)


def decoder_layer(groups: int) -> VGroup:
    """A transformer decoder layer box: Attention and MLP, each with a mini network."""
    box = RoundedRectangle(width=4.4, height=1.05, corner_radius=0.15, stroke_color=resolve_color("dim"),
                           fill_color=resolve_color("surface"), fill_opacity=1)
    att = T("Attention", 20).move_to(box.get_center() + LEFT * 1.35)
    mlp = T("MLP", 20).move_to(box.get_center() + RIGHT * 0.75)
    n1 = mini_net(groups).next_to(att, RIGHT, buff=0.15)
    n2 = mini_net(groups).next_to(mlp, RIGHT, buff=0.15)
    return VGroup(box, att, mlp, n1, n2)


def loss_panel(
    title: str, values: list[float], names: list[str], colors: list[str], xc: float, best: int
) -> tuple[VGroup, VGroup, VGroup]:
    """A bar panel of losses on an axis from 1.0 to 1.7; returns ``(frame, bars, value_labels)``."""
    ymin, ymax, unit, base = 1.0, 1.7, 6.0, -2.4
    dim = resolve_color("dim")
    ax = Line([xc - 2.3, base, 0], [xc - 2.3, base + (ymax - ymin) * unit, 0], color=dim, stroke_width=2)
    floor = Line([xc - 2.3, base, 0], [xc + 2.1, base, 0], color=dim, stroke_width=2)
    ticks = VGroup()
    for v in np.arange(1.0, 1.71, 0.1):
        y = base + (v - ymin) * unit
        ticks.add(T(f"{v:.1f}", 16, "dim").next_to([xc - 2.3, y, 0], LEFT, buff=0.12))
        ticks.add(DashedLine([xc - 2.3, y, 0], [xc + 2.1, y, 0], color=dim, stroke_width=0.8,
                             stroke_opacity=0.35, dash_length=0.08))
    head = T(title, 28, weight=BOLD).move_to([xc, base + (ymax - ymin) * unit + 0.55, 0])
    bars, vals, labs = VGroup(), VGroup(), VGroup()
    for i, (v, c) in enumerate(zip(values, colors)):
        x = xc - 1.2 + i * 1.3
        b = Rectangle(width=0.85, height=(v - ymin) * unit, stroke_width=0, fill_color=resolve_color(c), fill_opacity=0.9)
        b.move_to([x, base, 0], aligned_edge=DOWN)
        bars.add(b)
        vals.add(T(f"{v:.2f}", 24, "highlight" if i == best else "text",
                   weight=BOLD if i == best else NORMAL).next_to(b, UP, buff=0.1))
        labs.add(T(names[i], 16, c, line_spacing=0.8).next_to([x, base, 0], DOWN, buff=0.15))
    frame = VGroup(ax, floor, ticks, head, labs)
    return frame, bars, vals
