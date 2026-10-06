"""``process``: a linear pipeline of stages; a token travels from stage to stage, one per beat."""

import logging
import math
from typing import Any, Literal, NamedTuple

import numpy as np

from vidgen.api import *

log = logging.getLogger("vidgen.scenes")


class ProcessStage(SceneParams):
    """A stage: ``{label, icon?, text?}`` (a plain string is its label)."""

    also_accepts = (str,)

    label: str = Field(min_length=1)
    """Name of the stage (short; wrapped to fit the card)."""
    icon: IconName | None = None
    """Optional icon on the stage's card."""
    text: str = ""
    """Optional detail line under the label, smaller and dimmer."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"label": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "string", "minLength": 1}, handler(core_schema)]}


def rounded_path(points: list[np.ndarray], radius: float) -> VMobject:
    """A polyline through ``points`` with its corners rounded (quadratic arcs of up to
    ``radius``; straight runs through collinear points stay straight)."""
    path = VMobject()
    path.start_new_path(points[0])
    for k in range(1, len(points) - 1):
        a, corner, b = points[k - 1], points[k], points[k + 1]
        d_in, d_out = corner - a, b - corner
        l_in, l_out = float(np.linalg.norm(d_in)), float(np.linalg.norm(d_out))
        if l_in < 1e-9 or l_out < 1e-9:
            continue
        u_in, u_out = d_in / l_in, d_out / l_out
        if abs(float(np.dot(u_in, u_out))) > 1 - 1e-6:  # straight on (or back)
            path.add_line_to(corner)
            continue
        r = min(radius, l_in / 2, l_out / 2)
        path.add_line_to(corner - u_in * r)
        path.add_quadratic_bezier_curve_to(corner, corner + u_out * r)
    path.add_line_to(points[-1])
    return path


def _trim(points: list[np.ndarray], length: float) -> list[np.ndarray]:
    """``points`` with the last ``length`` units of the polyline cut off."""
    out = [p.copy() for p in points]
    while len(out) > 1 and length > 1e-9:
        seg = out[-1] - out[-2]
        n = float(np.linalg.norm(seg))
        if n > length:
            out[-1] = out[-1] - seg / n * length
            return out
        length -= n
        out.pop()
    return out


class _Geometry(NamedTuple):
    """One planned layout (see ``Process._geometry``)."""

    layout: str
    sizes: dict[str, float]
    factor: float
    over: float
    clean: bool
    lines: int
    width: float
    height: float
    centers: list[np.ndarray]
    gap: float
    lane: float
    leads: tuple[float, float]

    @property
    def fits(self) -> bool:
        return self.over <= 1.0 + 1e-6 and self.clean


@scene("process")
class Process(NarratedScene):
    """A pipeline of 2-8 stages, left to right in 16:9 (two rows, snaking, for many stages) and
    top to bottom in 9:16. Each step reveals the next stage: the connector into it grows while a
    token travels along it, and the stage becomes the active one (outline and icon in
    ``active_color``). ``loop`` adds a last step: an arrow back to the first stage, which the
    token follows. ``reveal: all`` shows the whole pipeline in beat 1 and then only moves the
    token, one stage per step.

    Action targets: ``heading``, ``input``, ``stage<N>`` (1-based), ``stage:<label>``,
    ``connector<N>`` (from stage N to N+1), ``loop``, ``output``, ``token``.
    """

    outro = 0.5
    target_patterns = ("heading", "input", "stage<N>", "stage:<label>", "connector<N>", "loop", "output", "token")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """Those the pipeline has, in this order: ``heading``, ``input``, ``stage<N>`` and
        ``stage:<label>`` per stage, ``connector<N>``, ``loop``, ``output``, ``token``."""
        names = (["heading"] if params.heading else []) + (["input"] if params.input else [])
        for i, stage in enumerate(params.stages, start=1):
            names += [f"stage{i}", f"stage:{stage.label}"]
        names += [f"connector{i}" for i in range(1, len(params.stages))]
        names += (["loop"] if params.loop else []) + (["output"] if params.output else [])
        return names + (["token"] if params.token else [])

    class Params(SceneParams):
        stages: list[ProcessStage] = Field(min_length=2, max_length=8)
        """The stages in order: a label, or {label, icon?, text?} (2-8; 3-5 read best)."""
        heading: str = ""
        """Optional heading above the pipeline."""
        layout: Literal["auto", "row", "snake", "column"] = "auto"
        """row: left to right; snake: two rows, the second running back; column: top to bottom. auto: column in portrait, else a row (snake when that keeps the text clearly larger)."""
        reveal: Literal["per_beat", "all"] = "per_beat"
        """per_beat: one stage per step, the token following; all: the whole pipeline in step 1, then the token moves one stage per step."""
        loop: bool = False
        """Draw an arrow from the last stage back to the first (a cycle); the token follows it in a last step."""
        loop_label: str = ""
        """Optional text on the loop arrow ('repeat', 'next batch')."""
        input: str = ""
        """Optional label before the first stage (what goes in), with an arrow into it."""
        output: str = ""
        """Optional label after the last stage (what comes out), with an arrow from it."""
        token: bool = True
        """Show the moving token (a dot) that travels from stage to stage."""
        token_icon: IconName | None = None
        """Draw the token as this icon in a small disc instead of a dot."""
        token_label: str = ""
        """Optional short tag that travels with the token ('order', 'request')."""
        stage_color: ThemeColor = "primary"
        """Stage outlines and icons."""
        label_color: ThemeColor = "text"
        """Stage labels."""
        text_color: ThemeColor = "dim"
        """Stage detail lines."""
        connector_color: ThemeColor = "dim"
        """Connectors and the loop arrow."""
        active_color: ThemeColor = "highlight"
        """Outline and icon of the active stage (where the token is)."""
        token_color: ThemeColor = "accent"
        """The token and its tag."""
        io_color: ThemeColor = "dim"
        """Input, output and loop labels."""
        heading_color: ThemeColor = "text"
        """Heading colour."""
        size: ThemeSize = "body"
        """Stage label size (up to 1.2x larger when there is room; reduced together with the other sizes, not below the readable minimum, when space is short)."""
        text_size: ThemeSize = "caption"
        """Stage detail size."""
        io_size: ThemeSize = "caption"
        """Size of the input, output, loop and token labels."""
        heading_size: ThemeSize = "heading"
        """Heading size."""

        @model_validator(mode="after")
        def _labels(self) -> SceneParams:
            seen: dict[str, int] = {}
            for i, stage in enumerate(self.stages):
                if stage.label in seen:
                    raise ValueError(f"stages[{i}]: label {stage.label!r} is used by stages[{seen[stage.label]}] too; stage labels must differ (they name the targets stage:<label>)")
                seen[stage.label] = i
            if self.loop_label and not self.loop:
                raise ValueError("loop_label needs loop: true")
            if (self.token_icon or self.token_label) and not self.token:
                raise ValueError("token_icon and token_label need token: true")
            return self

    #: In a vertical frame the heading grows by this factor (as in ``bullets``).
    portrait_growth = 1.3
    #: Token radius (Manim units): a dot / an icon in a disc.
    dot_radius = 0.12
    #: The token's soft halo, as a multiple of its radius.
    halo = 1.7
    icon_radius = 0.27
    #: Widest stage card in a row (Manim units) and widest in a column.
    max_card_width = (3.4, 6.0)
    #: Text grows up to this factor over the requested sizes when the pipeline has room.
    growth = 1.2
    #: ``auto`` keeps the frame's preferred layout unless the other's text is this much larger.
    layout_bias = 1.1
    #: Cards in a row are at least this share of their width tall when there is room.
    card_aspect = 0.5
    #: Set per planned layout: whether it is a column (the io labels wrap wider).
    _column = False
    #: Outline width of a stage card, and the factor for the active one.
    stroke = 2.5
    active_stroke = 2.0
    #: Room between connector lanes and the cards, and how deep the loop runs below/beside them.
    lane = 0.35
    loop_depth = 0.4

    # ----- planning --------------------------------------------------------------------------

    @property
    def radius(self) -> float:
        """Token radius (0 without a token)."""
        p = self.params
        if not p.token:
            return 0.0
        return self.icon_radius if p.token_icon else self.dot_radius

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
        geo = self._choose(body)
        if not geo.fits:
            log.warning(
                "scene '%s': the process's %d stages do not fit this frame at the readable size; "
                "shorten the labels and texts (or split the process into two scenes)", self.spec.id, len(p.stages),
            )
        self.plan = geo
        self._column = geo.layout == "column"
        self._steps(heading, self._draw(body, geo))

    def _options(self) -> list[str]:
        """Layouts to try, the preferred first."""
        p = self.params
        if p.layout != "auto":
            return [p.layout]
        if self.is_portrait:
            return ["column"]
        return ["row", "snake"] if len(p.stages) >= 4 else ["row"]

    def _choose(self, body: Region) -> _Geometry:
        """The layout with the largest text (the preferred one unless another's is
        :attr:`layout_bias` larger); growth beyond the requested size never decides it."""
        best: tuple[Any, ...] | None = None
        chosen = None
        for rank, layout in enumerate(self._options()):
            geo = self._fit(body, layout)
            bias = 1.0 if rank == 0 else 1 / self.layout_bias
            if geo.fits:
                key: tuple[Any, ...] = (1, round(min(geo.factor, 1.0) * bias, 3), -geo.lines, round(geo.factor * bias, 3))
            else:  # nothing fits: the one that needs the least scaling down
                key = (0, round(-geo.over / bias, 3))
            if best is None or key > best:
                best, chosen = key, geo
        assert chosen is not None
        return chosen

    def _fit(self, body: Region, layout: str) -> _Geometry:
        """The largest common size factor (up to :attr:`growth`, down to the readable minimum)
        at which every stage fits ``layout`` in ``body``."""
        p = self.params
        base = {k: float(self.theme.size(getattr(p, k))) for k in ("size", "text_size", "io_size")}
        floor = readable_size()
        lowest = min(min(1.0, floor / v) for v in base.values())  # every size at its floor

        def attempt(factor: float) -> _Geometry:
            sizes = {k: max(min(v, floor), v * factor) for k, v in base.items()}
            return self._geometry(body, layout, sizes, factor)

        factor = 1.0
        geo = attempt(factor)
        if geo.fits:
            grown = attempt(self.growth)
            if grown.fits and grown.lines <= geo.lines:
                return grown
            return geo
        while not geo.fits and factor > lowest + 1e-9:
            factor = max(lowest, factor * min(0.93, max(0.75, 1 / geo.over if geo.over > 1 else 0.93)))
            geo = attempt(factor)
        return geo

    def _units(self, sizes: dict[str, float]) -> float:
        """Spacing unit: 1 at a 32 pt stage label."""
        return sizes["size"] / 32

    def _content(self, stage: ProcessStage, width: float, sizes: dict[str, float], inline: bool) -> tuple[float, bool, int]:
        """Estimated height of a stage's content at ``sizes`` in an inner ``width``, whether
        every word fits, and the number of lines (icon above the text, or beside it ``inline``)."""
        u = self._units(sizes)
        icon_h = self._icon_height(sizes) if self._has_icons else 0.0
        text_w = width - (icon_h + 0.18 * u if inline and icon_h else 0.0)
        label = measure_text(stage.label, max(text_w * 0.97, 0.1), size=sizes["size"], weight=BOLD, balance=True)
        heights = [label.height]
        ok, lines = label.fits, len(label.lines)
        if stage.text:
            detail = measure_text(stage.text, max(text_w * 0.97, 0.1), size=sizes["text_size"], balance=True)
            heights.append(detail.height)
            ok, lines = ok and detail.fits, lines + len(detail.lines)
        text_h = sum(heights) + (len(heights) - 1) * 0.1 * u
        if inline:
            return max(text_h, icon_h), ok, lines
        return text_h + (icon_h + 0.14 * u if icon_h else 0.0), ok, lines

    def _longest_word(self, sizes: dict[str, float]) -> float:
        """Width of the widest single word of the stage labels and texts at ``sizes``."""
        widths = [0.0]
        for stage in self.params.stages:
            widths += [measure_text(w, 100.0, size=sizes["size"], weight=BOLD).width for w in stage.label.split()]
            widths += [measure_text(w, 100.0, size=sizes["text_size"]).width for w in stage.text.split()]
        return max(widths)

    @property
    def _has_icons(self) -> bool:
        return any(s.icon for s in self.params.stages)

    @staticmethod
    def _icon_height(sizes: dict[str, float]) -> float:
        return 0.75 * sizes["size"] / 32

    def _io_wrap(self, body: Region) -> float:
        """Wrap width of the input and output labels (beside the pipeline in a row, above and
        below it in a column)."""
        if self._column:
            return min(self.max_card_width[1], body.width) * 0.8
        return max(1.2, min(1.8, 0.13 * body.width))

    def _label_box(self, text: str, size: float, wrap: float) -> tuple[float, float, bool]:
        """Width, height and whether every word fits for an io / loop label."""
        m = measure_text(text, wrap, size=size, balance=True)
        return m.width, m.height, m.fits

    def _tag_box(self, sizes: dict[str, float]) -> tuple[float, float]:
        """Width and height of the token's tag (0, 0 without one)."""
        if not self.params.token_label:
            return 0.0, 0.0
        m = measure_text(self.params.token_label, 100.0, size=sizes["io_size"], weight=BOLD)
        return m.width + 0.24, m.height + 0.16

    def _geometry(self, body: Region, layout: str, sizes: dict[str, float], factor: float) -> _Geometry:
        """Card size and centres for ``layout`` at ``sizes``; ``over`` > 1 when it does not fit."""
        p = self.params
        n = len(p.stages)
        u = self._units(sizes)
        r = self.radius
        gap = max(0.7, 2 * r + 0.45)
        pad_x, pad_y = 0.22 * u, 0.2 * u
        io = sizes["io_size"]
        loop_w, loop_h, loop_ok = self._label_box(p.loop_label, io, 2.6) if p.loop_label else (0.0, 0.0, True)
        tag_w, tag_h = self._tag_box(sizes)
        halo = self.halo * r + 0.05  # room the token (with its halo) takes beyond a lead-in's start
        token_room = r + 0.04 + halo if p.token else 0.0
        inline = layout == "column"
        self._column = inline
        wrap = self._io_wrap(body)
        in_w, in_h, in_ok = self._label_box(p.input, io, wrap) if p.input else (0.0, 0.0, True)
        out_w, out_h, out_ok = self._label_box(p.output, io, wrap) if p.output else (0.0, 0.0, True)
        clean = in_ok and out_ok and loop_ok
        if layout == "column":
            left = tag_w + 0.2 if tag_w else 0.0
            lane = max(self.lane, loop_w / 2 + 0.12)
            leads = (gap, gap)
            right = lane + max(0.15, loop_w / 2 + 0.05) if p.loop else 0.0
            width = min(self.max_card_width[1], body.width - left - right)
            top = in_h + halo + gap if p.input else token_room
            bottom = out_h + 0.1 + gap if p.output else 0.0
            room = (body.height - top - bottom - (n - 1) * gap) / n
            measured = [self._content(s, width - 2 * pad_x, sizes, inline) for s in p.stages]
            height = max(m[0] for m in measured) + 2 * pad_y
            height = max(height, min(room, height + 0.5 * u))  # some air in the cards, room permitting
            over = max(height / room if room > 0 else 9.0, 1.4 / width if width > 0 else 9.0)
            gap += max(0.0, min(0.8, (body.height - top - bottom - n * height - (n - 1) * gap) / (n + 1)))
            total_h = top + n * height + (n - 1) * gap + bottom
            x = body.x0 + left + width / 2 + (body.width - left - right - width) / 2
            y_top = body.center[1] + total_h / 2 - top
            centers = [np.array([x, y_top - height / 2 - i * (height + gap), 0.0]) for i in range(n)]
        else:
            lane = self.lane
            rows = 2 if layout == "snake" else 1
            cols = math.ceil(n / rows)
            leads = (max(gap, in_w + 0.3), max(gap, out_w + 0.3))  # io labels stand above their arrows
            in_part = leads[0] + halo if p.input else token_room
            if tag_w:  # the token's tag is centred over its start
                in_part = max(in_part, (leads[0] if p.input else r + 0.04) + tag_w / 2 + 0.02)
            out_part = leads[1] + 0.05 if p.output else 0.0
            if rows == 1:
                left, right = in_part, out_part
            else:
                left = max(in_part, out_part) + (self.lane + 0.25 if p.loop else 0.0)
                right = self.lane + 0.2
            width = min(self.max_card_width[0], (body.width - left - right - (cols - 1) * gap) / cols)
            width = max(width, self._longest_word(sizes) + 2 * pad_x)  # too narrow: scaled down whole
            measured = [self._content(s, width - 2 * pad_x, sizes, inline) for s in p.stages]
            height = max(max(m[0] for m in measured) + 2 * pad_y, 2 * (max(in_h, out_h) + 0.15))
            band = tag_h + 0.15 if tag_h else 0.0
            row_gap = max(0.75, band + 0.45) if rows == 2 else 0.0
            loop_band = (self.loop_depth + (loop_h + 0.12 if loop_h else 0.0) + 0.1) if p.loop else 0.0
            total_h = band + rows * height + row_gap + loop_band
            roomy = max(height, self.card_aspect * width)  # cards no flatter than that, room permitting
            if total_h + rows * (roomy - height) <= body.height:
                total_h, height = total_h + rows * (roomy - height), roomy
            total_w = left + cols * width + (cols - 1) * gap + right
            over = max(total_h / body.height, total_w / body.width, 1.3 / width if width > 0 else 9.0)
            x0 = body.center[0] - total_w / 2 + left + width / 2
            y1 = body.center[1] + total_h / 2 - band - height / 2
            centers = []
            for i in range(n):
                row, col = divmod(i, cols)
                if row == 1:
                    col = cols - 1 - col
                centers.append(np.array([x0 + col * (width + gap), y1 - row * (height + row_gap), 0.0]))
        clean = clean and all(m[1] for m in measured)
        lines = sum(m[2] for m in measured)
        return _Geometry(layout, sizes, factor, over, clean, lines, width, height, centers, gap, lane, leads)

    # ----- routes ----------------------------------------------------------------------------

    def _side(self, i: int, direction: np.ndarray, geo: _Geometry) -> np.ndarray:
        """The middle of stage ``i``'s side facing ``direction``."""
        c = geo.centers[i]
        return c + np.array([direction[0] * geo.width / 2, direction[1] * geo.height / 2, 0.0])

    def _flow(self, i: int, geo: _Geometry) -> np.ndarray:
        """The direction the pipeline runs through stage ``i``."""
        if geo.layout == "column":
            return DOWN
        cols = math.ceil(len(self.params.stages) / (2 if geo.layout == "snake" else 1))
        return LEFT if i >= cols else RIGHT

    def _connector_route(self, i: int, geo: _Geometry) -> list[np.ndarray]:
        """Points of the connector from stage ``i`` to stage ``i + 1``."""
        a, b = self._flow(i, geo), self._flow(i + 1, geo)
        if np.allclose(a, b):
            return [self._side(i, a, geo), self._side(i + 1, -b, geo)]
        start, end = self._side(i, RIGHT, geo), self._side(i + 1, RIGHT, geo)  # snake turn
        x = max(start[0], end[0]) + self.lane
        return [start, np.array([x, start[1], 0.0]), np.array([x, end[1], 0.0]), end]

    def _loop_route(self, body: Region, geo: _Geometry) -> list[np.ndarray]:
        """Points of the loop arrow from the last stage back to the first."""
        n = len(self.params.stages)
        first, last = geo.centers[0], geo.centers[-1]
        if geo.layout == "column":
            x = first[0] + geo.width / 2 + geo.lane
            return [self._side(n - 1, RIGHT, geo), np.array([x, last[1], 0.0]), np.array([x, first[1], 0.0]), self._side(0, RIGHT, geo)]
        y = last[1] - geo.height / 2 - self.loop_depth
        start, end = self._side(n - 1, DOWN, geo), self._side(0, DOWN, geo)
        if geo.layout == "row":
            return [start, np.array([last[0], y, 0.0]), np.array([first[0], y, 0.0]), end]
        x = min(c[0] for c in geo.centers) - geo.width / 2 - self.lane - self._io_room(geo)
        x = max(x, body.x0 + 0.05)
        between = first[1] - geo.height / 2 - (first[1] - last[1] - geo.height) / 2
        return [start, np.array([last[0], y, 0.0]), np.array([x, y, 0.0]), np.array([x, between, 0.0]), np.array([first[0], between, 0.0]), end]

    def _io_room(self, geo: _Geometry) -> float:
        """Width the input/output labels and their arrows take left of a snake's cards."""
        p = self.params
        io = geo.sizes["io_size"]
        wrap = self._io_wrap(self.safe_area)
        widths = [max(geo.gap, self._label_box(t, io, wrap)[0] + 0.3) + 0.05 for t in (p.input, p.output) if t]
        return max(widths, default=2 * self.radius + 0.15 if p.token else 0.0)

    # ----- drawing ---------------------------------------------------------------------------

    def _arrow(self, points: list[np.ndarray], color: str, u: float) -> VGroup:
        """``VGroup(line, tip)`` along ``points`` with a filled arrowhead ending on the last."""
        tip_length = float(np.clip(0.2 * u, 0.14, 0.24))
        end = points[-1]
        tangent = end - points[-2]
        tangent = tangent / max(float(np.linalg.norm(tangent)), 1e-9)
        line = rounded_path(_trim(points, tip_length * 0.9), 0.22)
        line.set_stroke(color, width=3).set_fill(opacity=0)
        side = np.array([-tangent[1], tangent[0], 0.0])
        tip = Polygon(end, end - tangent * tip_length + side * tip_length * 0.5, end - tangent * tip_length - side * tip_length * 0.5)
        tip.set_fill(color, opacity=1).set_stroke(color, width=1)
        return VGroup(line, tip)

    def _card(self, stage: ProcessStage, geo: _Geometry) -> VGroup:
        """``VGroup(box, icon?, label, text?)`` centred on the origin."""
        p = self.params
        sizes = geo.sizes
        u = self._units(sizes)
        inline = geo.layout == "column"
        inner = geo.width - 2 * 0.22 * u
        icon_h = self._icon_height(sizes)
        mark = icon(stage.icon, color=p.stage_color, height=icon_h, theme=self.theme) if stage.icon else None
        text_w = inner - (icon_h + 0.18 * u if inline and self._has_icons else 0.0)
        align = "left" if inline and self._has_icons else "center"
        rows: list[Mobject] = [fit_text(stage.label, text_w, size=sizes["size"], color=p.label_color, weight=BOLD, align=align, balance=True)]
        if stage.text:
            rows.append(fit_text(stage.text, text_w, size=sizes["text_size"], color=p.text_color, align=align, balance=True))
        block = VGroup(*rows).arrange(DOWN, buff=0.1 * u, aligned_edge=LEFT if align == "left" else ORIGIN)
        box = RoundedRectangle(width=geo.width, height=geo.height, corner_radius=min(0.16 * u, geo.height / 4))
        box.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color(p.stage_color), width=self.stroke)
        if inline and self._has_icons:
            x_text = -geo.width / 2 + 0.22 * u + icon_h + 0.18 * u
            block.move_to(np.array([x_text + block.width / 2, 0.0, 0.0]))
            if mark is not None:
                mark.move_to(np.array([-geo.width / 2 + 0.22 * u + icon_h / 2, 0.0, 0.0]))
        else:
            content = VGroup(*([mark] if mark is not None else []), block).arrange(DOWN, buff=0.14 * u)
            content.move_to(ORIGIN)
        box.set_z_index(2)  # content above the box: an animated box is re-added on top of the card
        parts: list[Mobject] = [box, *([mark] if mark is not None else []), *rows]
        for part in parts[1:]:
            part.set_z_index(3)
        return VGroup(*parts)

    def _token(self) -> VGroup:
        """The token: a dot with a soft halo, or the icon in a disc (``VGroup``, centred)."""
        p = self.params
        color = self.theme.color(p.token_color)
        r = self.radius
        halo = Circle(radius=r * self.halo).set_fill(color, opacity=0.22).set_stroke(width=0)
        if p.token_icon:
            disc = Circle(radius=r).set_fill(self.theme.background, opacity=1).set_stroke(color, width=3)
            mark = icon(p.token_icon, color=p.token_color, height=r * 1.25, theme=self.theme).move_to(disc)
            group = VGroup(halo, disc, mark)
        else:
            group = VGroup(halo, Circle(radius=r).set_fill(color, opacity=1).set_stroke(self.theme.background, width=2))
        return group.set_z_index(1)

    def _tag(self, geo: _Geometry) -> VGroup | None:
        """The token's tag: its label on a pill outlined in the token colour."""
        p = self.params
        if not p.token_label:
            return None
        label = self.text(p.token_label, size=geo.sizes["io_size"], color=p.token_color, weight=BOLD)
        pill = RoundedRectangle(width=label.width + 0.24, height=label.height + 0.16, corner_radius=(label.height + 0.16) / 2)
        pill.set_fill(self.theme.color("surface"), opacity=1).set_stroke(self.theme.color(p.token_color), width=2).move_to(label)
        return VGroup(pill, label).set_z_index(4)

    def _io_label(self, text: str, geo: _Geometry, align: str) -> Paragraph:
        wrap = self._io_wrap(self.safe_area)
        return fit_text(text, wrap, size=geo.sizes["io_size"], color=self.params.io_color, align=align, balance=True)

    def _draw(self, body: Region, geo: _Geometry) -> "_Drawing":
        p = self.params
        n = len(p.stages)
        u = self._units(geo.sizes)
        dim = self.theme.color(p.connector_color)
        r = self.radius
        rest_gap = r + 0.04
        cards = [self._card(s, geo).move_to(geo.centers[i]) for i, s in enumerate(p.stages)]
        for card, c in zip(cards, geo.centers):
            card.shift(c - card[0].get_center())  # the box centred on its place, whatever the content
        routes = [self._connector_route(i, geo) for i in range(n - 1)]
        connectors = [self._arrow(route, dim, u) for route in routes]
        # where the token waits in front of each stage, and the paths between them
        entry_dirs = [self._flow(0, geo)] + [_unit(route[-1] - route[-2]) for route in routes]
        rests = [self._side(i, -entry_dirs[i], geo) - entry_dirs[i] * rest_gap for i in range(n)]
        paths: list[list[np.ndarray]] = [[]]
        for i, route in enumerate(routes):
            paths.append([rests[i], geo.centers[i], *_trim(route, rest_gap)])
        start = rests[0]
        input_group = output_group = None
        if p.input:
            entry = self._side(0, -entry_dirs[0], geo)
            begin = entry - entry_dirs[0] * geo.leads[0]
            label = self._io_label(p.input, geo, "center")
            arrow = self._arrow([begin, entry], dim, u)
            if geo.layout == "column":
                label.next_to(begin, UP, buff=self.halo * r + 0.05)
            else:
                label.next_to(arrow, UP, buff=0.1)
            input_group = VGroup(label, arrow)
            start = begin
            paths[0] = [begin, rests[0]]
        if p.output:
            flow = self._flow(n - 1, geo)
            exit_ = self._side(n - 1, flow, geo)
            arrow = self._arrow([exit_, exit_ + flow * geo.leads[1]], dim, u)
            label = self._io_label(p.output, geo, "center")
            if geo.layout == "column":
                label.next_to(arrow, DOWN, buff=0.1)
            else:
                label.next_to(arrow, UP, buff=0.1)
            output_group = VGroup(arrow, label)
        loop = None
        if p.loop:
            route = self._loop_route(body, geo)
            loop = self._arrow(route, dim, u)
            if p.loop_label:
                text = fit_text(p.loop_label, 2.6, size=geo.sizes["io_size"], color=p.io_color, balance=True)
                if geo.layout == "column":
                    mid = (route[1] + route[2]) / 2
                    plate = RoundedRectangle(width=text.width + 0.16, height=text.height + 0.12, corner_radius=0.08)
                    plate.set_fill(self.theme.background, opacity=1).set_stroke(width=0).move_to(mid)
                    text.move_to(mid)
                    loop.add(VGroup(plate, text))
                else:
                    mid = (route[1] + route[2]) / 2
                    text.next_to(mid, DOWN, buff=0.1)
                    loop.add(text)
            up = _unit(route[-1] - route[-2])
            paths.append([rests[-1], geo.centers[-1], *_trim(route, rest_gap)])
            rests.append(route[-1] - up * rest_gap)
        token = self._token().move_to(start) if p.token else None
        tag = self._tag(geo)
        offset = np.zeros(3)
        if tag is not None:
            if geo.layout == "column":
                offset = LEFT * (geo.width / 2 + 0.12 + tag.width / 2)
            else:
                offset = UP * (geo.height / 2 + 0.1 + tag.height / 2)
            tag.move_to(start + offset)
        drawing = _Drawing(cards, connectors, loop, input_group, output_group, token, tag, offset, paths, rests)
        return self._fit_into(body, drawing)

    def _fit_into(self, body: Region, d: "_Drawing") -> "_Drawing":
        """The drawing scaled down about its centre into ``body`` when it is larger (a plan that
        does not fit at the readable size); token paths and places follow."""
        group = VGroup(*d.cards, *d.connectors, *[m for m in (d.loop, d.input, d.output, d.token, d.tag) if m is not None])
        scale = min(1.0, body.width / group.width, body.height / group.height)
        if scale >= 1.0 - 1e-6:
            return d
        center = group.get_center()
        group.scale(scale, about_point=center).shift(body.center - center)

        def move(point: np.ndarray) -> np.ndarray:
            return body.center + (point - center) * scale

        paths = [[move(q) for q in path] for path in d.paths]
        return d._replace(offset=d.offset * scale, paths=paths, rests=[move(q) for q in d.rests])

    # ----- steps -----------------------------------------------------------------------------

    def _steps(self, heading: Mobject | None, d: "_Drawing") -> None:
        p = self.params
        n = len(p.stages)
        self._drawing = d
        top = self.target("heading", heading, entrance=lambda: [FadeIn(heading, shift=DOWN * 0.15)]) if heading is not None else None
        self._input = self.target("input", d.input, entrance=lambda: [AnimationGroup(FadeIn(d.input[0]), self._grow(d.input[1]), lag_ratio=0.4)]) if d.input is not None else None
        self._stages = [
            self.target([f"stage{i + 1}", f"stage:{s.label}"], d.cards[i], entrance=lambda i=i: [FadeIn(d.cards[i], scale=0.92)], outline=d.cards[i][0])
            for i, s in enumerate(p.stages)
        ]
        self._connectors = [self.target(f"connector{i + 1}", c, entrance=lambda c=c: [self._grow(c)]) for i, c in enumerate(d.connectors)]
        self._loop = self.target("loop", d.loop, entrance=lambda: [self._grow(d.loop)]) if d.loop is not None else None
        self._output = self.target("output", d.output, entrance=lambda: [AnimationGroup(self._grow(d.output[0]), FadeIn(d.output[1]), lag_ratio=0.6)]) if d.output is not None else None
        self._token_target = None
        if d.token is not None:
            token_group = VGroup(d.token, *([d.tag] if d.tag is not None else []))
            self._token_target = self.target("token", token_group, entrance=lambda: [FadeIn(token_group, scale=0.6)])
        self._active: int | None = None

        first_extra: list[Any] = [t for t in (top, self._input) if t is not None]
        if p.reveal == "all":
            everything = [*first_extra, *self._stages, *self._connectors, *[t for t in (self._loop, self._output) if t is not None]]
            steps: list[Any] = [self._arrive(0, extra=everything)]
            steps += [self._arrive(i) for i in range(1, n)]
        else:
            steps = [self._arrive(0, extra=first_extra)]
            steps += [self._arrive(i, after=[self._output] if i == n - 1 and self._output is not None else []) for i in range(1, n)]
        if p.loop:
            steps.append(self._arrive(n, extra=[]))
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()

    @staticmethod
    def _grow(arrow: VGroup) -> Animation:
        """An arrow grows along its line, then its head (and label) appear."""
        rest = [FadeIn(arrow[1], scale=0.5), *[FadeIn(part) for part in arrow[2:]]]
        return Succession(Create(arrow[0], rate_func=linear), AnimationGroup(*rest))

    def _arrive(self, index: int, extra: list[Target] | None = None, after: list[Target] | None = None) -> Any:
        """Step: the token moves to stage ``index`` (``n``: back to the first, along the loop),
        growing the connector it travels on if that is not shown yet; the stage appears (if it
        is not on screen) and becomes the active one. ``extra`` targets come along first,
        ``after`` targets last."""
        p = self.params
        n = len(p.stages)

        def build() -> list[Animation]:
            d = self._drawing
            stage = index % n
            lead: list[Animation] = [a for t in extra or [] if t is not self._stages[stage] for a in self.entrance(t)]
            travel: list[Animation] = []
            path_points = d.paths[index]
            road = self._loop if index == n else (self._connectors[index - 1] if index > 0 else None)
            grow = self.entrance(road) if road is not None else []
            if self._token_target is not None:
                lead += self.entrance(self._token_target)
            if d.token is not None and len(path_points) >= 2:
                path = rounded_path(path_points, 0.22)
                travel.append(MoveAlongPath(d.token, path, rate_func=smooth))
                if d.tag is not None:
                    if index == n:  # the tag would sit on the cards while the token loops: it waits
                        travel.append(d.tag.animate.set_opacity(0))
                    else:
                        travel.append(MoveAlongPath(d.tag, path.copy().shift(d.offset), rate_func=smooth))
            arrival: list[Animation] = []
            card_target = self._stages[stage]
            if not self.on_screen_parts(card_target):
                self._set_active(stage, True)
                arrival.append(FadeIn(d.cards[stage], scale=0.92))
            else:
                arrival += self._look(stage, True)
            if self._active is not None and self._active != stage:
                lead += self._look(self._active, False)
            self._active = stage
            chain: list[Animation] = []
            if lead:
                chain.append(AnimationGroup(*lead, lag_ratio=0.2))
            if travel or grow:
                chain.append(AnimationGroup(*travel, *grow))
            arrival += [a for t in after or [] for a in self.entrance(t)]
            if arrival:
                chain.append(AnimationGroup(*arrival, lag_ratio=0.3))
            return [Succession(*chain)] if len(chain) > 1 else chain

        return build

    def _set_active(self, i: int, on: bool) -> None:
        """Give stage ``i``'s card its active (or normal) look at once (before it is shown)."""
        card = self._drawing.cards[i]
        color = self.theme.color(self.params.active_color if on else self.params.stage_color)
        card[0].set_stroke(color, width=self.stroke * (self.active_stroke if on else 1.0))
        if self.params.stages[i].icon:
            card[1].set_color(color)

    def _look(self, i: int, on: bool) -> list[Animation]:
        """Animations to the active (or normal) look of stage ``i`` (only parts on screen)."""
        card = self._drawing.cards[i]
        if not self.on_screen_parts(self._stages[i]):
            return []
        color = self.theme.color(self.params.active_color if on else self.params.stage_color)
        anims: list[Animation] = [card[0].animate.set_stroke(color, width=self.stroke * (self.active_stroke if on else 1.0))]
        if self.params.stages[i].icon:
            anims.append(card[1].animate.set_color(color))
        return anims


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


class _Drawing(NamedTuple):
    """The drawn parts of a process."""

    cards: list[VGroup]
    connectors: list[VGroup]
    loop: VGroup | None
    input: VGroup | None
    output: VGroup | None
    token: VGroup | None
    tag: VGroup | None
    offset: np.ndarray
    paths: list[list[np.ndarray]]
    rests: list[np.ndarray]
