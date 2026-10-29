"""The ``hud`` overlay (DESIGN.md §102.5): a heads-up display over the frame — what an implant, a
visor or a robot's eye shows. Corner brackets and faint scan lines over the frame, a blinking
alert, readout lines appearing one by one, a heart monitor (a scrolling trace, its rate rising,
beats skipped) and a scanner's meter (a live wave that can spike off its scale). It belongs to a
scene like a lower third (``scene``, ``at``, ``duration``) and boots in with a flicker.

Its texts keep off the characters' faces (DESIGN.md §102.8): the overlay layer tells it where the
heads are on screen at each frame (:attr:`Overlay.faces`), and the alert and the lines go to the
free corner covering the least of a face (:func:`vidgen.hud.pick_place`). It is drawn in pieces
(:attr:`Overlay.pieces`), so its still frame is drawn once and only the small meters each frame.

The motion is :mod:`vidgen.hud`'s (pure functions of the time since it came on). Written against
``vidgen.api`` only.
"""

from collections.abc import Hashable
from typing import Literal

import numpy as np

from vidgen.api import *

from .overlays import LowerThird, scene_at

#: The scan lines over the frame: how many, and their opacity.
SCAN_LINES = 36
SCAN_LINE_OPACITY = 0.07
#: The corner brackets: their arm's length (a share of the frame's shorter side), inset from the
#: frame's edges (a share too) and line width.
BRACKET = 0.07
BRACKET_INSET = 0.03
BRACKET_WIDTH = 3.0
#: A panel's plate: colour, opacity and its outline's width.
PANEL_FILL = "#05121A"
PANEL_OPACITY = 0.6
PANEL_STROKE = 1.6
#: The heart and scan panels: their width and height (shares of the area's width / height;
#: portrait frames use the second width).
PANEL_WIDTH = (0.3, 0.47)
PANEL_HEIGHT = 0.18
#: ``compact``: texts and panels this size, the safe margin halved.
COMPACT = 0.72


class HudHeart(OverlayOptions):
    """A heart monitor (bottom left)."""

    bpm: float = Field(72.0, ge=20.0, le=240.0)
    """Beats a minute at the start."""
    to: float | None = Field(None, ge=20.0, le=240.0)
    """The rate it rises (or falls) to from `at` (eased over about 1.5 s); none: steady."""
    at: float = Field(0.0, ge=0.0)
    """Seconds after the HUD comes on when the rate changes (and the skipped beats come)."""
    skips: int = Field(0, ge=0, le=6)
    """Beats left out right at `at`: a heart that skips a beat (or three)."""
    label: TranslatableStr = "BPM"
    """The word beside the rate."""


class HudScan(OverlayOptions):
    """A scanner's meter (bottom right)."""

    level: float = Field(0.35, ge=0.0, le=2.0)
    """Its reading at the start, a share of its scale (above 1: off the scale)."""
    to: float | None = Field(None, ge=0.0, le=2.0)
    """The reading it moves to from `at` (above 1: it spikes off the scale, flashing a warning); none: steady."""
    at: float = Field(0.0, ge=0.0)
    """Seconds after the HUD comes on when the reading changes."""
    wave: Literal["organic", "steady"] = "organic"
    """organic (a living, irregular wave) or steady (a regular one)."""
    label: TranslatableStr = "SCAN"
    """The meter's name."""
    off_scale: TranslatableStr = "OFF SCALE"
    """The warning shown while the reading is above its scale."""


@overlay("hud")
class Hud(Overlay):
    """A heads-up display over the frame (an implant's, a visor's): corner brackets and scan
    lines, a blinking ``alert``, readout ``lines`` appearing one by one, a ``heart`` monitor and a
    ``scan`` meter. It belongs to a scene (``scene``, default the first it is drawn on) from
    ``at`` (seconds, a beat id or a spoken word) for ``duration`` seconds, booting in and out with
    a flicker. Usually written on the scene (``overlays: {implant: {type: hud, ...}}``)."""

    layer = 9   # under the captions and the hook
    lint_skip = ("contrast",)   # glowing lines over a scene; its text stands on dark plates
    avoids_faces = True
    #: drawn in four pieces (DESIGN.md §102.8): the frame and the panels' plates (still), the
    #: alert and the lines (changing when they blink, flicker in or move), the heart monitor and
    #: the scan meter (moving on every frame, each a small patch)
    pieces = 4

    class Options(OverlayOptions):
        scene: str | None = None
        """The scene it belongs to (its `at` is counted from that scene's start); default the first scene the overlay is drawn on."""
        at: float | str = 0.0
        """When it comes on: seconds after its scene's start, a beat id of that scene, or a word its narration says ("@alert")."""
        duration: float = Field(5.0, gt=0)
        """Seconds it shows, its boot in and out included."""
        across_cuts: bool = False
        """Keep it on over the following scenes until `duration` is over (default: it goes by the end of its scene)."""
        color: ThemeColor = HUD_COLOR
        """Its lines, brackets and readouts."""
        warning: ThemeColor = HUD_WARNING
        """The alert, skipped beats and an off-scale reading."""
        frame: bool = True
        """Corner brackets and faint scan lines over the frame."""
        alert: TranslatableStr | None = None
        """A blinking warning at the top (e.g. INCOMING ALERT)."""
        lines: list[TranslatableStr] = []
        """Readout lines (top left), appearing one after another."""
        line_seconds: float = Field(HUD_LINE_SECONDS, gt=0.05, le=10.0)
        """Seconds between the readout lines appearing."""
        heart: HudHeart | None = None
        """A heart monitor (bottom left): {bpm, to, at, skips, label}."""
        scan: HudScan | None = None
        """A scanner's meter (bottom right): {level, to, at, wave, label, off_scale}."""
        opacity: float = Field(0.92, gt=0, le=1)
        """How strongly it shows over the scene."""
        avoid_faces: bool = True
        """Keep the alert and the readout lines off the characters' faces: each goes to the free corner of the frame (top centre, top right, top left, above the meters) that covers the least of a face, moving only when a face comes under it. false: always the alert at the top centre, the lines at the top left."""
        compact: bool = False
        """Smaller texts and meters, closer to the frame's edges (for close-ups)."""
        enter: float = Field(0.4, ge=0)
        """Seconds of its boot in (a flicker)."""
        exit: float = Field(0.35, ge=0)
        """Seconds of its fade out."""

        @field_validator("at")
        @classmethod
        def _at(cls, value: float | str) -> float | str:
            return scene_at(value)

    # timed in its scene as a lower third is: ``scene``, ``at``, ``duration``, ``across_cuts``
    validate_project = classmethod(LowerThird.validate_project.__func__)   # type: ignore[attr-defined]
    window = LowerThird.window
    _start_in_scene = LowerThird._start_in_scene

    # ----- building ---------------------------------------------------------------------------

    def build(self) -> Mobject:
        o = self.options
        frame = frame_region()
        portrait = orientation() == "portrait"
        area = shorts_area(self.context.project) if self.context.project.config.shorts_zones is not None else safe_area()
        short = min(frame.width, frame.height)
        color, warning = resolve_color(o.color), resolve_color(o.warning)
        self._color, self._warning = color, warning
        shrink = COMPACT if o.compact else 1.0
        if o.compact:   # closer to the frame's edges
            inset = min(area.x0 - frame.x0, area.y0 - frame.y0, frame.x1 - area.x1, frame.y1 - area.y1) * 0.5
            area = Region(area.x0 - inset, area.y0 - inset, area.x1 + inset, area.y1 - inset)
        #: the still piece: the frame's brackets and scan lines, the panels' plates
        still: list[Mobject] = self._frame_parts(frame, short, color) if o.frame else []
        width = area.width * PANEL_WIDTH[1 if portrait else 0] * shrink
        height = max(area.height * PANEL_HEIGHT * shrink, 0.9 * shrink)
        #: the heart panel's and the scan panel's boxes (x0, y0, x1, y1), when shown
        self._heart_box: tuple[float, float, float, float] | None = None
        self._scan_box: tuple[float, float, float, float] | None = None
        if o.heart is not None:
            self._heart_box = (area.x0, area.y0, area.x0 + width, area.y0 + height)
            still += self._panel(self._heart_box, color)
        if o.scan is not None:
            self._scan_box = (area.x1 - width, area.y0, area.x1, area.y0 + height)
            still += self._panel(self._scan_box, color)
        #: the alert (its plate and words) and the readout lines, made at the origin; placed by
        #: the poses in one of the places worked out here
        self._alert: Mobject | None = None
        if o.alert:
            self._alert = self._alert_plate(o.alert, area, warning)
            self._alert.scale(shrink).move_to(ORIGIN)
        self._lines: list[Mobject] = []
        for text in o.lines:
            line = T(text, "caption", color, role="code")
            line.set_stroke(PANEL_FILL, width=4, opacity=0.8, background=True)
            line.scale(shrink)
            widest = area.width * (0.9 if portrait else 0.55)
            if line.width > widest:
                line.scale_to_fit_width(widest)
            self._lines.append(line.move_to(ORIGIN))
        above = max((box[3] for box in (self._heart_box, self._scan_box) if box is not None), default=area.y0) + 0.15
        self._places(area, above)
        #: texts made once and reused by the poses
        self._texts: dict[tuple[str, str], Mobject] = {}
        for part in [*still, *self._lines, *([self._alert] if self._alert is not None else [])]:
            _fade(part, o.opacity)
        #: the place chosen now for the alert and the lines (indices into the places)
        self._placed: tuple[int, int] = (0, 0)
        return VGroup(VGroup(*still), VGroup(*([self._alert] if self._alert is not None else []), *self._lines))

    def _places(self, area: Region, above: float) -> None:
        """Where the alert may stand (top centre, top right, top left, bottom centre above the
        meters) and, for each, where the block of lines may stand (top left, top right, bottom
        left and right above the meters; under the alert when it is up there too): boxes
        (left, bottom, right, top) in order of preference."""
        gap = 0.18
        cx = area.center[0]
        self._alert_boxes: list[tuple[float, float, float, float]] = []
        if self._alert is not None:
            w, h = self._alert.width, self._alert.height
            self._alert_boxes = [(cx - w / 2, area.y1 - h, cx + w / 2, area.y1), (area.x1 - w, area.y1 - h, area.x1, area.y1),
                                 (area.x0, area.y1 - h, area.x0 + w, area.y1), (cx - w / 2, above, cx + w / 2, above + h)]
        heights = [line.height for line in self._lines]
        block_w = max((line.width for line in self._lines), default=0.0)
        block_h = sum(heights) + 0.12 * max(len(heights) - 1, 0)
        self._line_boxes: list[list[tuple[float, float, float, float]]] = []
        for alert in self._alert_boxes or [None]:   # type: ignore[list-item]
            boxes = []
            for x0, up in ((area.x0, True), (area.x1 - block_w, True), (area.x0, False), (area.x1 - block_w, False)):
                if up:
                    top = area.y1
                    if alert is not None and alert[3] >= area.y1 - 1e-6 and alert[0] < x0 + block_w and x0 < alert[2]:
                        top = alert[1] - gap
                    boxes.append((x0, top - block_h, x0 + block_w, top))
                else:
                    bottom = above
                    if alert is not None and alert[1] <= above + 1e-6 and alert[0] < x0 + block_w and x0 < alert[2]:
                        bottom = alert[3] + gap
                    boxes.append((x0, bottom, x0 + block_w, bottom + block_h))
            self._line_boxes.append(boxes)

    def _frame_parts(self, frame: Region, short: float, color: str) -> list[Mobject]:
        """Corner brackets inside the frame's edges and faint scan lines across it."""
        arm, inset = BRACKET * short, BRACKET_INSET * short
        x0, y0, x1, y1 = frame.x0 + inset, frame.y0 + inset, frame.x1 - inset, frame.y1 - inset
        brackets = VMobject().set_fill(opacity=0).set_stroke(color, width=BRACKET_WIDTH, opacity=0.85)
        for cx, cy, sx, sy in ((x0, y1, 1, -1), (x1, y1, -1, -1), (x0, y0, 1, 1), (x1, y0, -1, 1)):
            brackets.start_new_path(np.array([cx + sx * arm, cy, 0.0]))
            brackets.add_line_to(np.array([cx, cy, 0.0]))
            brackets.add_line_to(np.array([cx, cy + sy * arm, 0.0]))
        scan = VMobject().set_fill(opacity=0).set_stroke(color, width=1.0, opacity=SCAN_LINE_OPACITY)
        for k in range(SCAN_LINES):
            y = frame.y0 + frame.height * (k + 0.5) / SCAN_LINES
            scan.start_new_path(np.array([frame.x0, y, 0.0]))
            scan.add_line_to(np.array([frame.x1, y, 0.0]))
        return [scan, brackets]

    def _alert_plate(self, text: str, area: Region, warning: str) -> Mobject:
        """A warning: a triangle and the words in the warning colour on a dark plate."""
        words = T(text, "body", warning, weight=BOLD, role="code")
        if words.width > area.width * 0.8:
            words.scale_to_fit_width(area.width * 0.8)
        size = words.height * 1.15
        sign = Polygon([0, size / 2, 0], [-size * 0.58, -size / 2, 0], [size * 0.58, -size / 2, 0])
        sign.set_fill(warning, opacity=1).set_stroke(width=0)
        mark = Rectangle(width=size * 0.12, height=size * 0.42).set_fill(PANEL_FILL, opacity=1).set_stroke(width=0)
        mark.move_to(sign.get_center() + UP * size * 0.05)
        dot = Circle(radius=size * 0.07).set_fill(PANEL_FILL, opacity=1).set_stroke(width=0).move_to(sign.get_center() + DOWN * size * 0.3)
        icon_group = VGroup(sign, mark, dot)
        content = VGroup(icon_group, words).arrange(RIGHT, buff=size * 0.4)
        plate = RoundedRectangle(corner_radius=0.08, width=content.width + 0.5, height=content.height + 0.3)
        plate.set_fill(PANEL_FILL, opacity=PANEL_OPACITY + 0.15).set_stroke(warning, width=PANEL_STROKE * 1.4, opacity=0.95)
        plate.move_to(content)
        return VGroup(plate, content)

    @staticmethod
    def _panel(box: tuple[float, float, float, float], color: str) -> list[Mobject]:
        """A panel's dark plate with an outline."""
        x0, y0, x1, y1 = box
        plate = Rectangle(width=x1 - x0, height=y1 - y0).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0.0])
        plate.set_fill(PANEL_FILL, opacity=PANEL_OPACITY).set_stroke(color, width=PANEL_STROKE, opacity=0.75)
        return [plate]

    def _text(self, text: str, color: str, size: str = "caption") -> Mobject:
        """``text`` in ``color`` (made once, then copied)."""
        key = (text, color + size)
        if key not in self._texts:
            self._texts[key] = T(text, size, color, weight=BOLD, role="code")
        return self._texts[key].copy()

    # ----- time -------------------------------------------------------------------------------

    def state(self, t: float) -> Hashable | None:
        """One state per piece (DESIGN.md §102.8), each ending with the boot level (1: fully on,
        less while it boots in with a flicker or fades): the still frame; the texts (where the
        alert and the lines stand, whether the alert is lit, how far each line has come in); the
        heart monitor's and the scan meter's frame since it came on (they move on every frame)."""
        o = self.options
        start, end = self.interval()
        p = self.transition(t, start, end, o.enter, o.exit)
        if p <= 0:
            return None
        since = t - start
        level = 1.0 if p >= 1 else round(p * (0.55 + 0.45 * (int(since * 30) % 2)), 3)
        frame = round(since * self.context.fps)
        still = (level,) if (o.frame or o.heart is not None or o.scan is not None) else None
        texts = None
        if self._alert is not None or self._lines:
            alert, lines = self._place_texts()
            fades = tuple(round(v, 2) for v in lines_shown(since, len(self._lines), o.line_seconds))
            texts = (alert, lines, self._alert is not None and alert_on(since), fades, level)
        heart = (frame, level) if o.heart is not None else None
        scan = (frame, level) if o.scan is not None else None
        return (still, texts, heart, scan)

    def _place_texts(self) -> tuple[int, int]:
        """Where the alert and the lines stand now: clear of the faces on screen (keeping their
        places while those stay clear), or the first places without ``avoid_faces``."""
        if not self.options.avoid_faces or self.faces is None:
            return (0, 0)
        faces = self.faces()
        alert, lines = self._placed
        if self._alert_boxes:
            alert = pick_place(self._alert_boxes, faces, alert)
        boxes = self._line_boxes[alert if self._alert_boxes else 0]
        if self._lines:
            lines = pick_place(boxes, faces, lines, avoid=[self._alert_boxes[alert]] if self._alert_boxes else [])
        self._placed = (alert, lines)
        return self._placed

    def settled(self, state: Hashable) -> bool:
        """Fully on (not booting or fading)."""
        return all(piece is None or float(piece[-1]) >= 1 for piece in state)   # type: ignore[union-attr]

    def pose_piece(self, mobject: Mobject, index: int, state: Hashable) -> Mobject:
        level = float(state[-1])   # type: ignore[index]
        if index == 0:
            group: Mobject = mobject.submobjects[0]
        elif index == 1:
            group = self._texts_posed(state)   # type: ignore[arg-type]
        else:
            t = int(state[0]) / self.context.fps   # type: ignore[index]
            o = self.options
            moving = (self._heart_parts(t, o.heart, self._heart_box) if index == 2 and o.heart is not None and self._heart_box is not None
                      else self._scan_parts(t, o.scan, self._scan_box) if index == 3 and o.scan is not None and self._scan_box is not None else [])
            for part in moving:   # new each frame: faded in place
                _fade(part, o.opacity)
            group = VGroup(*moving)
        return group if level >= 1 else with_opacity(group, level)

    def _texts_posed(self, state: tuple[int, int, bool, tuple[float, ...], float]) -> Mobject:
        """The alert and the lines in their places, the alert dimmed while it blinks off, each
        line as far as it has come in."""
        alert_at, lines_at, lit, fades, _ = state
        parts: list[Mobject] = []
        if self._alert is not None:
            x0, y0, x1, y1 = self._alert_boxes[alert_at]
            alert = self._alert.copy() if lit else with_opacity(self._alert, 0.25)
            parts.append(alert.move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0.0]))
        if self._lines:
            x0, _, x1, top = self._line_boxes[alert_at if self._alert_boxes else 0][lines_at]
            right = lines_at % 2 == 1   # the places on the right: lines flush right
            for line, shown in zip(self._lines, fades):
                if shown > 0:
                    placed = line.copy() if shown >= 1 else with_opacity(line, shown)
                    x = x1 - line.width / 2 if right else x0 + line.width / 2
                    parts.append(placed.move_to([x, top - line.height / 2, 0.0]))
                top -= line.height + 0.12
        return VGroup(*parts)

    def _heart_parts(self, t: float, options: HudHeart, box: tuple[float, float, float, float]) -> list[Mobject]:
        """The heart monitor at ``t``: its rate and word, a beating heart, the trace."""
        heart = HeartMonitor(options.bpm, options.to, options.at, options.skips)
        x0, y0, x1, y1 = box
        pad = (y1 - y0) * 0.12
        skipping = options.skips > 0 and heart.at <= t < heart.at + options.skips * 60.0 / heart.bpm + 0.4
        color = self._warning if skipping or heart_rate(t, heart) >= 120 else self._color
        label = self._text(f"{round(heart_rate(t, heart)):d} {options.label}", color)
        label.scale_to_fit_height((y1 - y0) * 0.24)
        size = label.height
        if label.width > x1 - x0 - 2 * pad - size * 1.2:   # a narrow panel (portrait)
            label.scale_to_fit_width(x1 - x0 - 2 * pad - size * 1.2)
        beats = heart_beats(t, heart, since=t - 0.3)
        pulse = 1.0 + 0.35 * max((max(0.0, 1 - (t - b) / 0.25) for b in beats if b <= t), default=0.0)
        icon = _heart_shape(size * 0.55 * pulse, color)
        icon.move_to([x0 + pad + size * 0.5, y1 - pad - size / 2, 0.0])
        label.move_to([x0 + pad + size * 1.2 + label.width / 2, y1 - pad - size / 2, 0.0])
        trace = heart_trace(t, heart, samples=90)
        top, bottom = y1 - pad * 2 - size, y0 + pad
        mid, amp = (top + bottom) / 2, (top - bottom) / 2 * 0.9
        line = VMobject().set_fill(opacity=0).set_stroke(color, width=2.4, opacity=1.0)
        line.set_points_as_corners([np.array([x0 + pad + (x1 - x0 - 2 * pad) * k / (len(trace) - 1), mid + amp * v, 0.0])
                                    for k, v in enumerate(trace)])
        return [line, icon, label]

    def _scan_parts(self, t: float, options: HudScan, box: tuple[float, float, float, float]) -> list[Mobject]:
        """The scanner's meter at ``t``: its name (or the off-scale warning, blinking), a bar
        filled to the reading, the live wave."""
        scan = ScanMeter(options.level, options.to, options.at, options.wave)
        x0, y0, x1, y1 = box
        pad = (y1 - y0) * 0.12
        level = scan_level(t, scan)
        off = level > 1.0
        color = self._warning if off else self._color
        word = options.off_scale if off and alert_on(t, 0.5) else options.label
        label = self._text(f"{word} {min(level, 9.99) * 100:.0f}%", color)
        label.scale_to_fit_height((y1 - y0) * 0.24)
        if label.width > x1 - x0 - 2 * pad:   # a narrow panel (portrait)
            label.scale_to_fit_width(x1 - x0 - 2 * pad)
        label.move_to([x0 + pad + label.width / 2, y1 - pad - label.height / 2, 0.0])
        bar_top = y1 - pad * 1.6 - label.height
        bar_h = (y1 - y0) * 0.1
        track = Rectangle(width=x1 - x0 - 2 * pad, height=bar_h).set_fill(color, opacity=0.18).set_stroke(color, width=1.0, opacity=0.8)
        track.move_to([(x0 + x1) / 2, bar_top - bar_h / 2, 0.0])
        filled = max(min(level, 1.0), 0.0) * (x1 - x0 - 2 * pad)
        parts: list[Mobject] = [track, label]
        if filled > 1e-3:
            fill = Rectangle(width=filled, height=bar_h).set_fill(color, opacity=0.95).set_stroke(width=0)
            fill.move_to([x0 + pad + filled / 2, bar_top - bar_h / 2, 0.0])
            parts.append(fill)
        wave = scan_wave(t, scan, samples=60)
        top, bottom = bar_top - bar_h - pad * 0.6, y0 + pad
        mid, amp = (top + bottom) / 2, (top - bottom) / 2 / 1.6
        line = VMobject().set_fill(opacity=0).set_stroke(color, width=2.2, opacity=1.0)
        line.set_points_smoothly([np.array([x0 + pad + (x1 - x0 - 2 * pad) * k / (len(wave) - 1), mid + amp * v, 0.0])
                                  for k, v in enumerate(wave)])
        parts.append(line)
        return parts


def _fade(mobject: Mobject, factor: float) -> None:
    """Multiply every fill and stroke opacity of ``mobject`` (one made for the HUD) by ``factor``."""
    if factor >= 1:
        return
    for part in mobject.get_family():
        if isinstance(part, VMobject):
            for name in ("fill_rgbas", "stroke_rgbas", "background_stroke_rgbas"):
                rgbas = getattr(part, name, None)
                if rgbas is not None and len(rgbas):
                    rgbas = np.array(rgbas, dtype=float)
                    rgbas[:, 3] *= factor
                    setattr(part, name, rgbas)


def _heart_shape(size: float, color: str) -> VMobject:
    """A small heart ``size`` wide, filled with ``color``."""
    points = []
    for k in range(40):
        a = 2 * np.pi * k / 40
        x = 16 * np.sin(a) ** 3
        y = 13 * np.cos(a) - 5 * np.cos(2 * a) - 2 * np.cos(3 * a) - np.cos(4 * a)
        points.append(np.array([x / 34 * size, y / 34 * size, 0.0]))
    shape = VMobject().set_fill(color, opacity=1).set_stroke(width=0)
    shape.set_points_as_corners([*points, points[0]])
    return shape


__all__ = ["Hud", "HudHeart", "HudScan"]
