"""``network``: a layered neural-network diagram, built layer by layer, with forward-pass pulses."""

import logging
import re
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

from .actions import dim_to

log = logging.getLogger("vidgen.scenes")

ConnectionKind = Literal["dense", "sparse", "grouped", "one_to_one", "none"]
_SHORT = re.compile(r"^\s*(sparse|grouped)\s*[: ]\s*([0-9.]+)\s*$")
_NEURON = re.compile(r"^\s*(\d+)\s*\.\s*(\d+)\s*$")


class Connection(SceneParams):
    """How a layer connects to the previous one: ``dense``, ``sparse``, ``grouped``,
    ``one_to_one`` or ``none``; short forms ``"sparse:0.3"``, ``"grouped:3"``."""

    also_accepts = (str,)

    type: ConnectionKind = "dense"
    """dense: every unit to every unit; sparse: a share of the pairs; grouped: blocks connected block to block; one_to_one: unit to unit; none."""
    ratio: float = Field(default=0.35, gt=0, le=1)
    """Share of the pairs drawn for sparse."""
    groups: int = Field(default=2, ge=1, le=12)
    """Number of blocks for grouped (each block of one layer connects to the same block of the other)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data
        short = _SHORT.match(data)
        if short:
            kind, value = short[1], float(short[2])
            return {"type": kind, "ratio": value} if kind == "sparse" else {"type": kind, "groups": int(value)}
        return {"type": data.strip()}

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}

    def pairs(self, n: int, m: int, seed: int) -> list[tuple[int, int]]:
        """The ``(i, j)`` unit pairs this connection draws between ``n`` and ``m`` units."""
        if self.type == "dense":
            return dense_pairs(n, m)
        if self.type == "sparse":
            return sparse_pairs(n, m, self.ratio, seed=seed)
        if self.type == "grouped":
            return grouped_pairs(n, self.groups, m)
        if self.type == "one_to_one":
            k = max(n, m)
            return sorted({(i * n // k, i * m // k) for i in range(k)})
        return []


class NetLayer(SceneParams):
    """A layer: ``{size, label?, show?, connect?, color?}`` (a plain number is its size)."""

    also_accepts = (int,)

    size: int = Field(ge=1, le=10**12)
    """Number of units the layer has (a layer larger than max_neurons is drawn as `show` units and an ellipsis)."""
    label: str = ""
    """Name under the layer ('Input', 'Hidden', 'Output')."""
    show: int | None = Field(default=None, ge=2, le=12)
    """Units drawn when the layer is larger than max_neurons (default: the scene's show)."""
    connect: Connection | None = None
    """How this layer connects to the previous one (default: the scene's connect)."""
    color: ThemeColor | None = None
    """Colour of this layer's units (default: the scene's neuron_color)."""

    @model_validator(mode="before")
    @classmethod
    def _from_number(cls, data: Any) -> Any:
        return {"size": data} if isinstance(data, int) and not isinstance(data, bool) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "integer", "minimum": 1}, handler(core_schema)]}


@scene("network")
class Network(NarratedScene):
    """A layered neural network: layers of units (left to right in 16:9, top to bottom in 9:16)
    joined by edges — dense, sparse, grouped or one to one. A large layer shows a few units, an
    ellipsis and its count. Steps: one layer per step (the edges into it grow first), then
    ``passes`` forward passes (a pulse runs through the network layer by layer), then the
    ``highlight`` step (a path of units stands out, the rest dims).

    Action targets: ``heading``, ``layer<N>``, ``layer:<label>``, ``edges<N>`` (between layer N
    and N+1), ``neuron<L>.<i>`` (unit i of layer L as drawn, 1-based).
    """

    outro = 0.5
    target_patterns = ("heading", "layer<N>", "layer:<label>", "edges<N>", "neuron<L>.<i>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``heading`` (if any); per layer ``layer<N>`` (and ``layer:<label>``) and its
        ``neuron<N>.<i>``; then ``edges<N>`` for every pair of layers that has edges."""
        names = ["heading"] if params.heading else []
        for k, layer in enumerate(params.layers, start=1):
            names += [f"layer{k}"] + ([f"layer:{layer.label}"] if layer.label else [])
            names += [f"neuron{k}.{i}" for i in range(1, params.drawn(k - 1) + 1)]
        names += [f"edges{k}" for k in range(1, len(params.layers)) if params.connection(k).type != "none"]
        return names

    class Params(SceneParams):
        layers: list[NetLayer] = Field(min_length=2, max_length=8)
        """The layers from input to output: a size, or {size, label?, show?, connect?, color?} (2-8)."""
        heading: str = ""
        """Optional heading above the network."""
        connect: Connection = Field(default="dense", validate_default=True)  # type: ignore[assignment]
        """How each layer connects to the previous one unless the layer says otherwise: dense, sparse, grouped, one_to_one, none, or 'sparse:0.3' / 'grouped:3' / {type, ratio, groups}."""
        direction: Literal["auto", "LR", "TB"] = "auto"
        """LR: layers left to right; TB: top to bottom; auto: TB in portrait frames, else LR."""
        max_neurons: int = Field(default=8, ge=2, le=12)
        """Layers with more units than this are drawn as `show` units with an ellipsis."""
        show: int = Field(default=6, ge=2, le=12)
        """Units drawn for a large layer (half before the ellipsis, half after)."""
        counts: Literal["auto", "all", "none"] = "auto"
        """Unit counts under the layer labels: auto: for layers drawn with an ellipsis; all; none."""
        count_format: str = "{n:,}"
        """Format of the counts (Python format with n: '{n:,} units', '{n}')."""
        reveal: Literal["layers", "all"] = "layers"
        """layers: one layer per step, its incoming edges first; all: the whole network in step 1."""
        passes: int = Field(default=1, ge=0, le=4)
        """Forward passes after the network is built: each is a step in which a pulse runs from the first layer to the last."""
        highlight: list[str] = Field(default_factory=list)
        """Units emphasised in a last step, as 'layer.unit' (1-based, units as drawn): ['1.2', '2.3', '3.1'] marks a path; the rest dims."""
        max_edges: int = Field(default=64, ge=4, le=200)
        """Most edges drawn between two layers (more are thinned evenly, keeping every unit connected)."""
        neuron_color: ThemeColor = "primary"
        """Units (unless a layer sets its color)."""
        edge_color: ThemeColor = "dim"
        """Edges (grouped edges use the palette instead, see group_colors)."""
        group_colors: bool = True
        """Colour grouped connections by block (theme palette)."""
        edge_opacity: float | None = Field(default=None, gt=0, le=1)
        """Edge opacity; default: lower the more edges a pair of layers has."""
        label_color: ThemeColor = "text"
        """Layer labels."""
        count_color: ThemeColor = "dim"
        """Unit counts."""
        pulse_color: ThemeColor = "accent"
        """The forward-pass pulse."""
        highlight_color: ThemeColor = "highlight"
        """Highlighted units and the edges between them."""
        heading_color: ThemeColor = "text"
        """Heading colour."""
        label_size: ThemeSize = "caption"
        """Layer label size (counts use it too; never below the readable minimum)."""
        heading_size: ThemeSize = "heading"
        """Heading size."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            try:
                self.count_format.format(n=1234)
            except (KeyError, IndexError, ValueError) as error:
                raise ValueError(f"count_format {self.count_format!r} is not a format with n (e.g. '{{n:,}}'): {error}") from None
            labels = [layer.label for layer in self.layers if layer.label]
            if len(labels) != len(set(labels)):
                raise ValueError("layer labels must differ (they name the targets layer:<label>)")
            if self.layers[0].connect is not None:
                raise ValueError("layers[0].connect: the first layer has no previous layer to connect to")
            for ref in self.highlight:
                self.neuron(ref)
            return self

        def drawn(self, k: int) -> int:
            """Units drawn for layer ``k`` (0-based)."""
            layer = self.layers[k]
            if layer.size <= self.max_neurons:
                return layer.size
            return min(layer.show or self.show, layer.size)

        def truncated(self, k: int) -> bool:
            """Whether layer ``k`` is drawn with an ellipsis."""
            return self.drawn(k) < self.layers[k].size

        def connection(self, k: int) -> Connection:
            """How layer ``k`` (0-based, ≥ 1) connects to layer ``k - 1``."""
            return self.layers[k].connect or self.connect

        def neuron(self, ref: str) -> tuple[int, int]:
            """``(layer, unit)`` (0-based) of a ``'L.i'`` reference (1-based, units as drawn)."""
            found = _NEURON.match(str(ref))
            if not found:
                raise ValueError(f"highlight: {ref!r} is not 'layer.unit' (e.g. '2.3': unit 3 of layer 2, both counted from 1)")
            k, i = int(found[1]) - 1, int(found[2]) - 1
            if not 0 <= k < len(self.layers):
                raise ValueError(f"highlight: {ref!r}: there is no layer {k + 1} (layers 1..{len(self.layers)})")
            if not 0 <= i < self.drawn(k):
                raise ValueError(f"highlight: {ref!r}: layer {k + 1} draws units 1..{self.drawn(k)}")
            return k, i

    #: In a vertical frame the heading grows by this factor (as in ``bullets``).
    portrait_growth = 1.3
    #: Largest distance between neighbouring units, and between layers (Manim units).
    max_gap = 0.85
    max_spacing = (3.4, 3.0)
    #: Unit radius as a share of the gap between units, and its bounds.
    radius_share = 0.3
    radius_range = (0.07, 0.22)
    #: Opacity of the parts that are not highlighted in the highlight step.
    dimmed_opacity = 0.3

    def construct(self) -> None:
        p = self.params
        body = self.safe_area
        heading = None
        if p.heading:
            header = self.region("header")
            size = float(self.theme.size(p.heading_size)) * (self.portrait_growth if self.is_portrait else 1.0)
            heading = fit_text(p.heading, header.width, header.height, size=size, color=p.heading_color, weight=BOLD, role="heading")
            place(heading, header, fit="none", align="center")
            body = body.below(heading, gap=0.45)
        self._steps(heading, self._draw(body))

    @property
    def horizontal(self) -> bool:
        """Whether layers run left to right (else top to bottom)."""
        d = self.params.direction
        return d == "LR" or (d == "auto" and not self.is_portrait)

    # ----- drawing ---------------------------------------------------------------------------

    def _captions(self, width: float) -> list[VGroup | None]:
        """Per layer ``VGroup(label?, count?)`` wrapped to ``width`` (``None`` when empty)."""
        p = self.params
        size = max(float(self.theme.size(p.label_size)), readable_size())
        align = "center" if self.horizontal else "right"
        out: list[VGroup | None] = []
        for k, layer in enumerate(p.layers):
            rows: list[Mobject] = []
            if layer.label:
                rows.append(fit_text(layer.label, width, size=size, color=p.label_color, weight=BOLD, align=align, balance=True))
            if p.counts == "all" or (p.counts == "auto" and p.truncated(k)):
                rows.append(fit_text(p.count_format.format(n=layer.size), width, size=size, color=p.count_color, align=align))
            edge = ORIGIN if self.horizontal else RIGHT
            out.append(VGroup(*rows).arrange(DOWN, buff=0.08, aligned_edge=edge) if rows else None)
        return out

    def _draw(self, body: Region) -> "_Drawing":
        p = self.params
        n = len(p.layers)
        slots = max(p.drawn(k) + p.truncated(k) for k in range(n))
        if self.horizontal:
            spacing = min(self.max_spacing[0], body.width / n)
            captions = self._captions(max(spacing - 0.25, 0.8))
            band = max((c.height for c in captions if c is not None), default=0.0)
            area = body.height - (band + 0.3 if band else 0.0)
            gap = min(self.max_gap, area / slots)
            centers = [body.center[0] + (k - (n - 1) / 2) * spacing for k in range(n)]
            middle = body.y1 - area / 2
        else:
            label_w = min(2.6, 0.3 * body.width)
            captions = self._captions(label_w)
            widest = max((c.width for c in captions if c is not None), default=0.0)
            rows_x0 = body.x0 + (widest + 0.35 if widest else 0.0)
            spacing = min(self.max_spacing[1], body.height / n)
            gap = min(self.max_gap, (body.x1 - rows_x0) / slots)
            centers = [body.center[1] + ((n - 1) / 2 - k) * spacing for k in range(n)]
            middle = (rows_x0 + body.x1) / 2
        r = float(np.clip(gap * self.radius_share, *self.radius_range))
        layers, ellipses = [], []
        for k, layer in enumerate(p.layers):
            m = p.drawn(k)
            hole = (m + 1) // 2 if p.truncated(k) else None
            color = layer.color or p.neuron_color
            if self.horizontal:
                dots = column(m, centers[k], gap, middle, r=r, color=color, skip=hole)
            else:
                dots = column(m, middle, gap, centers[k], r=r, color=color, horizontal=True, skip=hole)
            for dot in dots:
                dot.set_stroke(self.theme.background, width=1.5)
            layers.append(dots)
            ellipses.append(self._ellipsis(dots, hole, r, color) if hole is not None else None)
        for k, caption in enumerate(captions):
            if caption is None:
                continue
            if self.horizontal:
                caption.move_to(np.array([centers[k], 0.0, 0.0])).align_to(np.array([0.0, body.y0 + band, 0.0]), UP)
            else:
                caption.move_to(np.array([0.0, centers[k], 0.0])).align_to(np.array([rows_x0 - 0.35, 0.0, 0.0]), RIGHT)
        drawn = [self._edges(k, layers[k - 1], layers[k], r) for k in range(1, n)]
        bundles = [b for b, _ in drawn]
        # one block, centred in the body
        everything = VGroup(*layers, *[e for e in ellipses if e is not None], *[c for c in captions if c is not None], *[b for b in bundles if b is not None])
        everything.shift(body.center - everything.get_center())
        return _Drawing(layers, ellipses, captions, bundles, [pairs for _, pairs in drawn], r)

    def _ellipsis(self, dots: VGroup, hole: int, r: float, color: str) -> VGroup:
        """Three small dots in the empty slot (a vertical or horizontal ellipsis)."""
        a, b = dots[hole - 1].get_center(), dots[hole].get_center()
        middle, step = (a + b) / 2, (b - a) / 2
        size = min(r * 0.35, float(np.linalg.norm(step)) * 0.12)
        marks = [Dot(middle + step * f, radius=size, color=self.theme.color(color)) for f in (-0.45, 0.0, 0.45)]
        return VGroup(*marks).set_z_index(3)

    def _edges(self, k: int, a: VGroup, b: VGroup, r: float) -> tuple[VGroup | None, list[tuple[int, int]]]:
        """The edges from layer ``k - 1`` to layer ``k`` and their unit pairs (``None`` and no
        pairs for ``connect: none``)."""
        p = self.params
        conn = p.connection(k)
        pairs = conn.pairs(len(a), len(b), seed=k)
        if not pairs:
            return None, []
        if len(pairs) > p.max_edges:
            pairs = _thin(pairs, p.max_edges, seed=k)
        colors = None
        if conn.type == "grouped" and p.group_colors and conn.groups > 1:
            bounds = group_bounds(len(a), conn.groups)
            colors = [self.theme.palette_color(next(g for g in range(len(bounds) - 1) if bounds[g] <= i < bounds[g + 1])) for i, _ in pairs]
        opacity = p.edge_opacity if p.edge_opacity is not None else float(np.clip(2.4 / np.sqrt(len(pairs)), 0.2, 0.75))
        width = float(np.clip(r * 14, 1.2, 2.4))
        return edges(a, b, pairs, color=p.edge_color, width=width, opacity=opacity, colors=colors, shorten=r * 1.15), pairs

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, heading: Mobject | None, d: "_Drawing") -> None:
        p = self.params
        n = len(p.layers)
        self._drawing = d
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        self._neurons: list[list[Target]] = []
        self._layers: list[Target] = []
        for k, layer in enumerate(p.layers):
            parts = [d.layers[k], *[m for m in (d.ellipses[k], d.captions[k]) if m is not None]]
            names = [f"layer{k + 1}"] + ([f"layer:{layer.label}"] if layer.label else [])
            self._layers.append(self.target(names, VGroup(*parts), entrance=lambda k=k: [self._grow_layer(k)]))
            self._neurons.append([self.target(f"neuron{k + 1}.{i + 1}", dot, entrance=lambda dot=dot: [GrowFromCenter(dot)]) for i, dot in enumerate(d.layers[k])])
        self._bundles: list[Target | None] = [
            self.target(f"edges{k}", b, entrance=lambda b=b: [self._grow_edges(b)]) if b is not None else None for k, b in enumerate(d.bundles, start=1)
        ]

        def build_step(ks: list[int], first: bool) -> Any:
            def build() -> list[Animation]:
                anims: list[Animation] = list(self.entrance(top)) if first and top is not None else []
                for k in ks:
                    bundle = self._bundles[k - 1] if k > 0 else None
                    edges_in = self.entrance(bundle) if bundle is not None else []
                    layer = self.entrance(self._layers[k])
                    anims += [Succession(*edges_in, *layer)] if edges_in and layer else edges_in + layer
                return [AnimationGroup(*anims, lag_ratio=0.15)] if len(anims) > 1 else anims

            return build

        groups = [list(range(n))] if p.reveal == "all" else [[k] for k in range(n)]
        steps: list[Any] = [build_step(g, i == 0) for i, g in enumerate(groups)]
        steps += [self._pass() for _ in range(p.passes)]
        if p.highlight:
            steps.append(self._focus())
        self.reveal(steps, fraction=0.75, cap=1.8)
        self.finish()

    def _grow_layer(self, k: int) -> Animation:
        """A layer's units grow in one after another, with its ellipsis and caption."""
        d = self._drawing
        anims: list[Animation] = [LaggedStart(*[GrowFromCenter(dot) for dot in d.layers[k] if not self.on_screen_parts(dot)], lag_ratio=0.12)]
        if d.ellipses[k] is not None:
            anims.append(FadeIn(d.ellipses[k]))
        if d.captions[k] is not None:
            anims.append(FadeIn(d.captions[k], shift=(UP if self.horizontal else LEFT) * 0.1))
        return AnimationGroup(*anims)

    @staticmethod
    def _grow_edges(bundle: VGroup) -> Animation:
        """Edges grow from the previous layer towards the next."""
        return Create(bundle, lag_ratio=min(0.5, 4.0 / max(len(bundle), 1)), rate_func=linear)

    def _pass(self) -> Any:
        """A forward pass: the first layer lights up, then a pulse runs along each set of
        edges and the next layer lights up, layer by layer."""
        p = self.params
        color = self.theme.color(p.pulse_color)

        def build() -> list[Animation]:
            d = self._drawing
            chain: list[Animation] = [self._light(d.layers[0], color)]
            for k, bundle in enumerate(d.bundles, start=1):
                if bundle is not None and self.on_screen_parts(bundle):
                    flashes = [ShowPassingFlash(line.copy().set_stroke(color, width=line.get_stroke_width() * 1.8, opacity=1), time_width=0.6) for line in bundle]
                    chain.append(AnimationGroup(*flashes))
                chain.append(self._light(d.layers[k], color))
            return [LaggedStart(*chain, lag_ratio=0.62)]

        return build

    def _light(self, dots: VGroup, color: str) -> Animation:
        """Units flash in ``color`` (and grow a little) and return to their look."""
        shown = [dot for dot in dots if self.on_screen_parts(dot)]
        return AnimationGroup(*[Indicate(dot, color=color, scale_factor=1.35) for dot in shown]) if shown else Wait(0.01)

    def _focus(self) -> Any:
        """The highlight step: the listed units grow and turn ``highlight_color``, so do the
        edges between consecutive ones in neighbouring layers; every other unit and edge dims."""
        p = self.params
        color = self.theme.color(p.highlight_color)
        chosen = [p.neuron(ref) for ref in p.highlight]
        chosen_set = set(chosen)
        links = {(a, b) for a, b in zip(chosen, chosen[1:]) if b[0] == a[0] + 1}

        def build() -> list[Animation]:
            d = self._drawing
            anims: list[Animation] = []
            for k, targets in enumerate(self._neurons):
                for i, target in enumerate(targets):
                    if (k, i) in chosen_set:
                        if self.on_screen_parts(target):
                            anims.append(d.layers[k][i].animate.set_fill(color).scale(1.3))
                    else:
                        anims += [dim_to(target, part, self.dimmed_opacity) for part in self.on_screen_parts(target)]
            for k, ellipsis in enumerate(d.ellipses):
                if ellipsis is not None and self.on_screen_parts(ellipsis):
                    anims.append(dim_to(self._layers[k], ellipsis, self.dimmed_opacity))
            for k, (bundle, target) in enumerate(zip(d.bundles, self._bundles), start=1):
                if bundle is None or target is None:
                    continue
                for line, (i, j) in zip(bundle, d.pairs[k - 1]):
                    if ((k - 1, i), (k, j)) in links:
                        anims.append(line.animate.set_stroke(color, width=line.get_stroke_width() * 2, opacity=1))
                    elif self.on_screen_parts(line):
                        anims.append(dim_to(target, line, self.dimmed_opacity))
            for (ka, i), (kb, j) in links:  # a link the connection does not draw: drawn now
                if (i, j) not in d.pairs[kb - 1]:
                    a, b = d.layers[ka][i].get_center(), d.layers[kb][j].get_center()
                    step = (b - a) / np.linalg.norm(b - a) * d.radius * 1.15
                    anims.append(Create(Line(a + step, b - step, stroke_width=3.5, color=color)))
            return anims

        return build


def _thin(pairs: list[tuple[int, int]], cap: int, seed: int) -> list[tuple[int, int]]:
    """``cap`` of ``pairs`` (evenly spread, reproducible), plus one pair for any unit that
    would lose all its connections. Sorted."""
    rng = np.random.default_rng(seed)
    keep = {pairs[i] for i in sorted(rng.choice(len(pairs), size=cap, replace=False))}
    for side in (0, 1):
        for unit in sorted({pair[side] for pair in pairs}):
            if not any(pair[side] == unit for pair in keep):
                keep.add(next(pair for pair in pairs if pair[side] == unit))
    return sorted(keep)


class _Drawing(NamedTuple):
    """The drawn parts of a network, per layer (bundles per pair of layers)."""

    layers: list[VGroup]
    ellipses: list[VGroup | None]
    captions: list[VGroup | None]
    bundles: list[VGroup | None]
    pairs: list[list[tuple[int, int]]]
    radius: float
