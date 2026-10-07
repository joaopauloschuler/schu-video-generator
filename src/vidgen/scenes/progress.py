"""Built-in overlays (DESIGN.md §42): ``progress_bar`` and ``chapter_indicator``.

Both read the whole video's planned timeline (``context.duration``, ``context.chapters``), so
they look the same on both sides of every cut; chapters come from ``chapter`` scenes and scenes
with a ``chapter:`` field (docs/CONFIG.md "Chapters").
"""

from collections.abc import Hashable
from dataclasses import dataclass
from functools import cached_property
from html import escape
from typing import Literal

from vidgen.api import *

Corner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


def _pixel() -> float:
    """One output pixel in Manim units."""
    return float(config.frame_width) / float(config.pixel_width)


@overlay("progress_bar")
class ProgressBar(Overlay):
    """A thin bar along the top or bottom edge of the frame filling up with the video: how much
    of the whole video has been played. With ``chapters``, small gaps split it into the video's
    chapters (as a video player marks them).
    """

    timed = True

    class Options(OverlayOptions):
        position: Literal["top", "bottom"] = "top"
        """Edge of the frame: top or bottom."""
        thickness: float = Field(0.006, gt=0, le=0.05)
        """Height of the bar, as a share of the frame's shorter side (at least 2 pixels)."""
        color: ThemeColor = "primary"
        """Colour of the played part."""
        track_color: ThemeColor = "dim"
        """Colour of the part still to come."""
        track_opacity: float = Field(0.35, ge=0, le=1)
        """Opacity of the part still to come (0: only the played part shows)."""
        opacity: float = Field(1.0, gt=0, le=1)
        """Opacity of the played part."""
        chapters: bool = True
        """Split the bar at chapter starts with small gaps."""
        inset: float = Field(0.0, ge=0, le=0.3)
        """Distance from the frame's edge (0: flush with it), as a share of the shorter side."""

    def _geometry(self) -> tuple[float, float, float, float, list[tuple[float, float]]]:
        """``(x0, x1, y_center, height, segments)``: the bar's span in units and its segments."""
        o = self.options
        frame = frame_region()
        short = min(frame.width, frame.height)
        height = max(o.thickness * short, 2 * _pixel())
        inset = o.inset * short
        y = frame.y1 - inset - height / 2 if o.position == "top" else frame.y0 + inset + height / 2
        x0, x1 = frame.x0 + inset, frame.x1 - inset
        segments = [(x0, x1)]
        duration = self.context.duration
        if o.chapters and duration > 0:
            gap = max(2 * height, 3 * _pixel())
            cuts = [x0 + (x1 - x0) * c.start / duration for c in self.context.chapters if 0 < c.start < duration]
            edges = [x0, *cuts, x1]
            segments = [(a if k == 0 else a + gap / 2, b if k == len(edges) - 2 else b - gap / 2) for k, (a, b) in enumerate(zip(edges, edges[1:]))]
            segments = [(a, b) for a, b in segments if b - a > _pixel()]
        return x0, x1, y, height, segments

    @staticmethod
    def _bars(segments: list[tuple[float, float]], upto: float, y: float, height: float, color: str, opacity: float) -> VGroup:
        group = VGroup()
        for a, b in segments:
            end = min(b, upto)
            if end - a <= 1e-6:
                continue
            bar = Rectangle(width=end - a, height=height).set_fill(color, opacity=opacity).set_stroke(width=0)
            group.add(bar.move_to([(a + end) / 2, y, 0]))
        return group

    def build(self) -> Mobject:
        o = self.options
        x0, x1, y, height, segments = self._geometry()
        self._shape = (x0, x1, y, height, segments)
        self._pixel = _pixel()
        track = self._bars(segments, x1, y, height, resolve_color(o.track_color), o.track_opacity)
        if o.track_opacity <= 0:
            track = VGroup()
        played = self._bars(segments, x1, y, height, resolve_color(o.color), o.opacity)
        return VGroup(track, played)

    def state(self, t: float) -> Hashable | None:
        """How many pixel columns of the bar are played (a whole number: frames that differ by
        less than a pixel are drawn once)."""
        duration = self.context.duration
        fraction = min(max(t / duration, 0.0), 1.0) if duration > 0 else 1.0
        x0, x1 = self._shape[0], self._shape[1]
        return int(round(fraction * (x1 - x0) / self._pixel))

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        o = self.options
        x0, _, y, height, segments = self._shape
        track = mobject.submobjects[0]
        played = self._bars(segments, x0 + int(state) * self._pixel, y, height, resolve_color(o.color), o.opacity)  # type: ignore[call-overload]
        return VGroup(track, played)


@dataclass(frozen=True)
class _Run:
    """Time the indicator shows one chapter without a break: ``start`` / ``end`` in the video,
    the chapter's position (0-based) and whether the run before / after it touches it (a
    cross-fade instead of a fade)."""

    start: float
    end: float
    chapter: int
    joined_before: bool = False
    joined_after: bool = False


@overlay("chapter_indicator")
class ChapterIndicator(Overlay):
    """A small label in a corner naming the current chapter ("2 · Results", optionally "2/5 ·
    Results"); when the chapter changes it cross-fades to the next one. Hidden before the first
    chapter and, by default, on the ``chapter`` cards themselves (they already say it).
    """

    timed = True

    class Options(OverlayOptions):
        corner: Corner = "top_left"
        """top_left, top_right, bottom_left or bottom_right."""
        number: bool = True
        """Show the chapter's number (as written, else its position) before the title."""
        total: bool = False
        """Show the position out of the number of chapters ("2/5") instead of the number."""
        separator: str = " · "
        """Between the number and the title."""
        size: ThemeSize = "caption"
        """Text size (at least the readable size)."""
        color: ThemeColor = "text"
        """Title colour."""
        number_color: ThemeColor = "primary"
        """Number colour."""
        opacity: float = Field(0.85, gt=0, le=1)
        """Opacity of the label."""
        background: ThemeColor | None = None
        """A plate behind the label (e.g. surface), for scenes with pictures up to the corner; default none."""
        background_opacity: float = Field(0.85, ge=0, le=1)
        """Plate opacity."""
        max_width: float = Field(0.4, gt=0, le=1)
        """Widest it may be, as a share of the frame's width (9:16: twice that, at most 0.85); a longer title is shortened with an ellipsis."""
        inset: float = Field(0.025, ge=0, le=0.3)
        """Distance from the frame's edges, as a share of the frame's shorter side."""
        fade: float = Field(0.4, ge=0)
        """Seconds of its fades and of the cross-fade when the chapter changes (0: cut)."""
        on_chapter_cards: bool = False
        """Also show it on chapter scenes (default: hidden there)."""

    # ----- when ------------------------------------------------------------------------------

    @cached_property
    def runs(self) -> list[_Run]:
        """Where it shows which chapter: the scenes it is drawn on that belong to a chapter (not
        chapter cards, unless ``on_chapter_cards``), consecutive scenes of a chapter merged."""
        chapters = self.context.chapters
        drawn = set(self.scenes)
        runs: list[_Run] = []
        k = -1
        for slot in self.context.scenes:
            while k + 1 < len(chapters) and chapters[k + 1].start <= slot.start + 1e-9:
                k += 1
            if k < 0 or slot.id not in drawn or slot.duration <= 0:
                continue
            if not self.options.on_chapter_cards and chapters[k].scene == slot.id and chapters[k].card:
                continue
            if runs and runs[-1].chapter == k and abs(runs[-1].end - slot.start) < 1e-6:
                runs[-1] = _Run(runs[-1].start, slot.end, k)
            else:
                runs.append(_Run(slot.start, slot.end, k))
        joined = [abs(a.end - b.start) < 1e-6 for a, b in zip(runs, runs[1:])]
        return [_Run(r.start, r.end, r.chapter, i > 0 and joined[i - 1], i < len(joined) and joined[i]) for i, r in enumerate(runs)]

    def _bounds(self, run: _Run) -> tuple[float, float]:
        half = self.options.fade / 2
        return (run.start - half if run.joined_before else run.start, run.end + half if run.joined_after else run.end)

    def _opacity(self, run: _Run, t: float) -> float:
        f = self.options.fade
        start, end = self._bounds(run)
        if t < start - 1e-9 or t >= end - 1e-9:
            return 0.0
        if f <= 0:
            return 1.0 if run.start - 1e-9 <= t < run.end - 1e-9 else 0.0
        return self.transition(t, start, end, f, f)

    def shown_in(self, start: float, end: float) -> bool:
        """Shown when one of its runs reaches into ``[start, end)``."""
        return any(a < end - 1e-9 and b > start + 1e-9 for a, b in map(self._bounds, self.runs))

    def state(self, t: float) -> Hashable | None:
        """``((chapter position, opacity), ...)``: one label, or two while they cross-fade."""
        shown = tuple((run.chapter, round(p, 2)) for run in self.runs if (p := self._opacity(run, t)) > 0.005)
        return shown or None

    def settled(self, state: Hashable) -> bool:
        """One label at its full look."""
        return len(state) == 1 and state[0][1] >= 1  # type: ignore[arg-type,index]

    # ----- look ------------------------------------------------------------------------------

    def _text(self, chapter: Chapter) -> str:
        o = self.options
        if not o.number:
            return ""
        return f"{chapter.index}/{chapter.count}" if o.total else chapter.label

    def _label(self, chapter: Chapter, width: float, size: float) -> Mobject:
        o = self.options
        head = self._text(chapter)
        color, number_color = ManimColor(resolve_color(o.color)).to_hex(), ManimColor(resolve_color(o.number_color)).to_hex()

        def markup(title: str) -> str:
            text = f'<span foreground="{color}">{escape(title)}</span>'
            if head:
                text = f'<span foreground="{number_color}"><b>{escape(head)}</b></span><span foreground="{color}">{escape(o.separator)}</span>' + text
            return text

        title = chapter.title
        label = MT(markup(title), size, o.color)
        words = title.split()
        while label.width > width and len(words) > 1:
            words.pop()
            title = " ".join(words).rstrip(",;:·-") + "…"
            label = MT(markup(title), size, o.color)
        if label.width > width:
            label.scale_to_fit_width(width)
        return label

    def build(self) -> Mobject:
        o = self.options
        frame = frame_region()
        short = min(frame.width, frame.height)
        size = max(current_theme().size(o.size), readable_size())
        pad_x, pad_y = (0.22, 0.12) if o.background else (0.0, 0.0)
        share = min(2 * o.max_width, 0.85) if orientation() == "portrait" else o.max_width
        width = share * frame.width - 2 * pad_x
        area = frame.inset(o.inset * short, o.inset * short)
        labels = VGroup()
        for chapter in self.context.chapters:
            label: Mobject = self._label(chapter, width, size)
            if o.background:
                plate = RoundedRectangle(corner_radius=0.08, width=label.width + 2 * pad_x, height=label.height + 2 * pad_y)
                plate.set_fill(resolve_color(o.background), opacity=o.background_opacity).set_stroke(width=0)
                label = VGroup(plate, label.move_to(plate))
            place(label, area, fit="none", align=o.corner)
            labels.add(with_opacity(label, o.opacity))
        return labels

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        parts = []
        for chapter, p in state:  # type: ignore[attr-defined]
            label = mobject.submobjects[chapter]
            parts.append(label if p >= 1 else with_opacity(label, p))
        return VGroup(*parts)

