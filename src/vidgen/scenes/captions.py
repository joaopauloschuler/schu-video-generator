"""Built-in overlay (DESIGN.md §43): ``captions`` — the narration burned into the video.

Two styles: ``subtitles`` (one or two lines on a plate, cut at phrase boundaries like the SRT)
and ``karaoke`` (a few big words at a time, the word being spoken highlighted with a small
scale pop: vertical / social videos). Word times come from the TTS provider's alignment when
it stored one next to the MP3, else they are estimated within the MP3's speech
(``beat_word_times``). The overlay reads the scene's planned beats, so a caption changes
exactly where the narration does.
"""

import logging
from bisect import bisect_right
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from vidgen.api import *

log = logging.getLogger("vidgen.overlays")

#: In portrait, bottom captions sit this share of the safe height above the safe area's bottom
#: (phone apps put their own controls over the bottom of a vertical video).
PORTRAIT_LIFT = 0.12
#: Padding (units) between the text and the edge of its plate.
PAD_X = 0.26
PAD_Y = 0.14
#: Gap between lines, as a share of a line's height.
LINE_GAP = 0.3
#: Karaoke: the spoken word grows by at most this share of a space on each side.
POP_ROOM = 0.45
#: Characters standing on the baseline (no descender), used to line up baselines.
BASELINE_CHARS = set("abcdefhiklmnorstuvwxzABCDEFGHIKLMNOPRSTUVWXYZ0123456789")

#: Defaults per style: text size, bold, lines, words per caption, width (share of the safe width).
STYLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "subtitles": {"size": "body", "bold": False, "max_lines": 2, "max_words": None, "max_width": 0.8},
    "karaoke": {"size": "title", "bold": True, "max_lines": 2, "max_words": 3, "max_width": 0.9},
}


@dataclass
class _Cue:
    """A caption as built: scene-time ``start`` / ``end``, word start times, and for each word
    its line and glyph indices in that line's ``Text`` (``None`` when glyphs cannot be told
    apart)."""

    start: float
    end: float
    word_starts: list[float]
    glyphs: list[tuple[int, list[int]] | None]


def _glyph_map(mob: Mobject, line: str) -> list[list[int]] | None:
    """Per word of ``line``, the indices of its glyphs among ``mob``'s submobjects. Manim
    keeps a submobject per character (spaces included) in newer versions and per visible
    character in older ones; anything else (ligatures) gives ``None``."""
    count = len(mob.submobjects)
    out: list[list[int]] = []
    if count == len(line):
        k = 0
        for word in line.split(" "):
            out.append(list(range(k, k + len(word))))
            k += len(word) + 1
        return out
    if count == len(line.replace(" ", "")):
        k = 0
        for word in line.split(" "):
            out.append(list(range(k, k + len(word))))
            k += len(word)
        return out
    return None


@overlay("captions")
class Captions(Overlay):
    """The narration as captions burned into the video (off unless listed in ``overlays:``).

    ``subtitles`` shows one cue at a time: up to ``max_lines`` lines on a plate, cut at natural
    phrase boundaries exactly like the SRT, each cue from its first spoken word to the next
    cue. ``karaoke`` (alias ``words``) shows a few big words at a time and highlights the word
    being spoken. Captions sit at the bottom (default), the top or the centre of the safe area;
    at the top or bottom the scenes keep clear of them unless ``reserve: false``.
    """

    timed = True
    layer = 10   # over the other overlays
    #: Captions are the narration itself: they do not count as words on screen.
    lint_skip = ("max_words",)

    class Options(OverlayOptions):
        style: Literal["subtitles", "karaoke"] = "subtitles"
        """subtitles (lines of the narration) or karaoke (a few words, the spoken one highlighted; alias words)."""
        position: Literal["bottom", "top", "center"] = "bottom"
        """Where in the safe area: bottom, top or center (center does not reserve space: lint reports what it covers)."""
        size: ThemeSize | None = None
        """Text size (at least the readable size); default body, karaoke title."""
        bold: bool | None = None
        """Bold text; default false, karaoke true."""
        max_lines: int | None = Field(None, ge=1, le=3)
        """Lines per caption; default 2."""
        max_words: int | None = Field(None, ge=1)
        """Words per caption; default no limit, karaoke 3."""
        max_width: float | None = Field(None, gt=0, le=1)
        """Widest a caption's text may be, as a share of the safe width; default 0.8, karaoke 0.9 (9:16: 1)."""
        color: ThemeColor | None = None
        """Text colour; default the theme's text or background colour, whichever reads better on the plate."""
        highlight: ThemeColor = "highlight"
        """Karaoke: colour of the word being spoken (another accent if it does not read on the plate)."""
        pop: float = Field(1.12, ge=1, le=1.5)
        """Karaoke: scale of the word being spoken (1: no pop; limited so it never touches its neighbours)."""
        background: ThemeColor | None = "surface"
        """Plate colour (null: no plate, the text gets an outline in the theme background)."""
        background_opacity: float = Field(0.8, ge=0, le=1)
        """Plate opacity; raised automatically until the text reaches lint's contrast ratio over anything behind it."""
        lift: float | None = Field(None, ge=0, le=0.6)
        """Bottom captions: raise them by this share of the safe height; default 0, 9:16 0.12 (phone controls)."""

        @field_validator("style", mode="before")
        @classmethod
        def _style_alias(cls, value: Any) -> Any:
            return "karaoke" if value == "words" else value

    # ----- settings --------------------------------------------------------------------------

    def _setting(self, name: str) -> Any:
        """An option, or its style's default when not given."""
        value = getattr(self.options, name)
        return STYLE_DEFAULTS[self.options.style][name] if value is None else value

    @property
    def karaoke(self) -> bool:
        """Whether it highlights words (style ``karaoke``)."""
        return self.options.style == "karaoke"

    def default_reserve(self) -> bool:
        """Scenes keep clear of captions at the top or bottom (not of centred ones)."""
        return self.options.position != "center"

    def shown_in(self, start: float, end: float) -> bool:
        """Only on scenes with narration (silent scenes have nothing to caption, nor reserve)."""
        return bool(self.context.scene.beats)

    def _colors(self) -> tuple[str, str, float]:
        """Text colour, highlight colour and plate opacity that keep lint's contrast ratio."""
        o = self.options
        theme = current_theme()
        minimum = self.context.project.config.lint.rules.contrast.min_ratio
        if o.background is None:
            return resolve_color(o.color or "text"), resolve_color(o.highlight), 0.0
        candidates = [o.color] if o.color else ["text", theme.background, "#FFFFFF", "#000000"]
        opacity = o.background_opacity
        while True:   # the most readable colour; the plate more opaque until it reads over anything
            color = max(candidates, key=lambda c: plate_contrast(c, o.background, opacity))
            if plate_contrast(color, o.background, opacity) >= minimum or opacity >= 1:
                break
            opacity = min(1.0, round(opacity + 0.05, 2))
        if plate_contrast(color, o.background, opacity) < minimum:
            log.warning(f"captions: {o.color or 'the text'} does not reach a contrast of {minimum:g} on the plate {o.background}")
        highlight = color
        for option in [o.highlight, "highlight", "accent", "primary", "secondary", "tertiary"]:
            if option in theme.colors or option.startswith("#"):
                if plate_contrast(option, o.background, opacity) >= minimum:
                    highlight = option
                    break
        if self.karaoke and highlight != o.highlight:
            log.warning(f"captions: highlight {o.highlight} is hard to read on the plate {o.background}; using {highlight}")
        return resolve_color(color), resolve_color(highlight), opacity

    # ----- cues ------------------------------------------------------------------------------

    def _cue_texts(self, size: float, weight: str, max_width: float) -> list[CaptionCue]:
        """The scene's cues (scene times; each shown until the next starts, the last of a beat
        until the next beat, the scene's last until the scene ends)."""
        scene = self.context.scene
        widths: dict[str, float] = {}

        def width(word: str) -> float:
            if word not in widths:
                widths[word] = measure_text(word, 1e6, size=size, weight=weight).width
            return widths[word]

        space = width("x x") - width("xx")
        project = self.context.project
        audio = project.audio_dir
        out = []
        beats = scene.beats
        for k, beat in enumerate(beats):
            until = beats[k + 1].start if k + 1 < len(beats) else scene.duration
            # The written words, timed by the audio of their spoken form (pronunciation, §45).
            words = beat_word_times(audio, beat.id, beat.text, beat.start, beat.end, project.pronunciation.apply(beat.text))
            cues = caption_cues(
                beat.text, beat.start, beat.end, words=words, widths=[width(w) for w in beat.text.split()], space=space,
                max_width=max_width, max_lines=self._setting("max_lines"), max_words=self._setting("max_words"), until=until,
            )
            out.extend(cues)
        return out

    # ----- look ------------------------------------------------------------------------------

    def _area(self) -> Region:
        o = self.options
        safe = safe_area()
        lift = o.lift if o.lift is not None else (PORTRAIT_LIFT if orientation() == "portrait" else 0.0)
        if o.position == "bottom" and lift:
            return Region(safe.x0, safe.y0 + lift * safe.height, safe.x1, safe.y1)
        return safe

    def _lines(self, lines: Sequence[str], size: float, weight: str, color: str, max_width: float, pitch: float) -> list[Mobject]:
        """The lines as ``Text``s centred on x = 0, their baselines ``pitch`` apart (shrunk
        together when a word is wider than ``max_width``)."""
        mobs = [T(line, size, color, weight, disable_ligatures=True) for line in lines]
        if self.options.background is None:
            for mob in mobs:
                mob.set_stroke(current_theme().background, width=max(size / 8, 2), background=True)
        for k, (mob, line) in enumerate(zip(mobs, lines)):
            mob.move_to(ORIGIN)
            glyphs = _glyph_map(mob, line)
            chars = line.replace(" ", "") if glyphs is not None and len(mob.submobjects) != len(line) else line
            base = [g.get_bottom()[1] for g, ch in zip(mob.submobjects, chars) if ch in BASELINE_CHARS and len(g.points)]
            mob.shift(UP * (-k * pitch - (min(base) if glyphs is not None and base else mob.get_bottom()[1])))
        block = VGroup(*mobs)
        if block.width > max_width:   # one word wider than the caption: shrink it all
            block.scale(max_width / block.width)
        return mobs

    def build(self) -> Mobject:
        o = self.options
        theme = current_theme()
        size = max(float(theme.size(self._setting("size"))), readable_size())
        weight = BOLD if self._setting("bold") else NORMAL
        area = self._area()
        self._space = measure_text("x x", 1e6, size=size, weight=weight).width - measure_text("xx", 1e6, size=size, weight=weight).width
        room = POP_ROOM * self._space if self.karaoke and o.pop > 1 else 0.0   # a popped first / last word stays on the plate
        pad_x = PAD_X + room
        share = 1.0 if orientation() == "portrait" else self._setting("max_width")
        max_width = max(share * area.width - 2 * pad_x, 1.0)
        color, self._highlight, opacity = self._colors()
        lines_max = self._setting("max_lines")
        probe = T("Hxgy", size, color, weight)   # a line's full height, descenders included
        pitch = probe.height * (1 + LINE_GAP)
        band_h = probe.height + pitch * (lines_max - 1) + 2 * PAD_Y
        band = Rectangle(width=max_width + 2 * pad_x, height=band_h).set_fill(opacity=0).set_stroke(width=0)
        place(band, area, fit="none", align=o.position)
        slot = Region(*band.get_corner(DL)[:2], *band.get_corner(UR)[:2])
        self._cues: list[_Cue] = []
        group = VGroup(band)
        for cue in self._cue_texts(size, weight, max_width):
            lines = self._lines(cue.lines, size, weight, color, max_width, pitch)
            block = VGroup(*lines)
            mob: Mobject = block
            if o.background is not None:
                plate = RoundedRectangle(corner_radius=min(0.12, PAD_Y), width=block.width + 2 * pad_x, height=block.height + 2 * PAD_Y)
                plate.set_fill(resolve_color(o.background), opacity=opacity).set_stroke(width=0).move_to(block)
                mob = VGroup(plate, *lines)
            place(mob, slot, fit="none", align=o.position)
            glyphs: list[tuple[int, list[int]] | None] = []
            for k, line in enumerate(cue.lines):
                found = _glyph_map(lines[k], line)
                glyphs.extend([(k, g) for g in found] if found is not None else [None] * len(line.split(" ")))
            self._cues.append(_Cue(cue.start, cue.end, [w.start for w in cue.words], glyphs))
            group.add(mob)
        self._starts = [c.start for c in self._cues]
        self._plated = o.background is not None
        return group

    # ----- time ------------------------------------------------------------------------------

    def state(self, t: float) -> Hashable | None:
        """The cue shown at video time ``t`` (its index), with karaoke the word being spoken:
        ``(cue, word)`` (``word`` -1 before the first word)."""
        st = t - self.context.scene.start
        k = bisect_right(self._starts, st + 1e-9) - 1
        if k < 0 or st >= self._cues[k].end - 1e-9:
            return None
        if not self.karaoke:
            return k
        return (k, bisect_right(self._cues[k].word_starts, st + 1e-9) - 1)

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        if not self.karaoke:
            return mobject.submobjects[1 + int(state)]  # type: ignore[call-overload]
        k, word = state  # type: ignore[misc]
        cue = mobject.submobjects[1 + k]
        place_of = self._cues[k].glyphs[word] if 0 <= word < len(self._cues[k].glyphs) else None
        if place_of is None:
            return cue
        copy = cue.copy()
        line_index, indices = place_of
        line = copy.submobjects[line_index + (1 if self._plated else 0)]
        chars = VGroup(*(line.submobjects[i] for i in indices))
        chars.set_fill(self._highlight)
        # grow by at most POP_ROOM of a space on each side, so it never touches its neighbours
        pop = min(self.options.pop, 1 + 2 * POP_ROOM * self._space / max(chars.width, 1e-6))
        if pop > 1:
            chars.scale(pop)
        return copy
