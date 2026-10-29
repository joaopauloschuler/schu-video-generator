"""Built-in overlay (DESIGN.md §43): ``captions`` — the narration burned into the video.

Two styles: ``subtitles`` (one or two lines on a plate, cut at phrase boundaries like the SRT)
and ``karaoke`` (a few big words at a time, the word being spoken highlighted with a small
scale pop: vertical / social videos). Word times come from the TTS provider's alignment when
it stored one next to the MP3, else they are estimated within the MP3's speech
(``beat_word_times``). The overlay reads the scene's planned beats, so a caption changes
exactly where the narration does. Where a beat overlaps the one before (DESIGN.md §69.34),
both lines show while both sound: one line each, the earlier above (``stack_cues``).
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
#: Karaoke: the spoken word grows by at most this share of a space on each side (0.45 left
#: words nearly touching in 9:16, Step 48; 0.25 keeps half the gap).
POP_ROOM = 0.25
#: Characters standing on the baseline (no descender), used to line up baselines.
BASELINE_CHARS = set("abcdefhiklmnorstuvwxzABCDEFGHIKLMNOPRSTUVWXYZ0123456789")

#: Defaults per style: text size, bold, lines, words per caption, width (share of the safe width).
STYLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "subtitles": {"size": "body", "bold": False, "max_lines": 2, "max_words": None, "max_width": 0.8},
    "karaoke": {"size": "title", "bold": True, "max_lines": 2, "max_words": 3, "max_width": 0.9},
}


_GENES: dict[int, tuple[Any, frozenset[str]]] = {}


def video_gene_symbols(project: Any) -> frozenset[str]:
    """The gene symbols the video's scenes declare (scene types with ``gene_symbols(params)``:
    ``cell``, ``molecule``, ``pathway``), worked out once per project config."""
    from vidgen import registry

    config = project.config
    cached = _GENES.get(id(config))
    if cached is not None and cached[0] is config:
        return cached[1]
    found: set[str] = set()
    for spec in config.scenes:
        entry = registry.find(spec.type)
        hook = getattr(entry.cls, "gene_symbols", None) if entry is not None else None
        if hook is None:
            continue
        try:
            found.update(hook(entry.cls.parse_params(spec.params, spec.id)))
        except (VidgenError, ValueError, KeyError):
            continue
    result = frozenset(found)
    _GENES.clear()
    _GENES[id(config)] = (config, result)
    return result


@dataclass
class _Part:
    """One beat's cue in a caption as built: its word start times, and for each word its line
    (in the caption) and glyph indices in that line's ``Text`` (``None`` when glyphs cannot be
    told apart)."""

    word_starts: list[float]
    glyphs: list[tuple[int, list[int]] | None]


@dataclass
class _Cue:
    """A caption as built: scene-time ``start`` / ``end`` and its parts (one cue, or two stacked
    while two lines overlap)."""

    start: float
    end: float
    parts: list[_Part]


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
    at the top or bottom the scenes keep clear of them unless ``reserve: false``. ``speakers``
    tags or colours the speakers of a dialogue (``voices:``, DESIGN.md §46).
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
        speakers: Literal["off", "name", "color", "both"] | None = None
        """Show who speaks (voices:): name (a "Label:" tag in the speaker's colour where the speaker changes), color (each speaker's words in its colour), both, off; default subtitles.speakers."""
        genes: bool = True
        """Gene symbols in italics (protein names stay roman): the symbols the video's cell-biology scenes declare as genes (a cell or molecule scene's gene name, a molecule's gene, a pathway's gene nodes); not where the next word makes it the protein (SERPINA1 protein)."""

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

    @property
    def speakers(self) -> str:
        """How speakers are shown: the option, else the project's ``subtitles.speakers``."""
        return self.options.speakers or self.context.project.config.subtitles.speakers

    def _scene_speakers(self) -> list[str | None]:
        """The voices of the scene's beats (``None``: the base voice), first use first."""
        names = self.context.project.voice_names()
        return list(dict.fromkeys(names.get(beat.id) for beat in self.context.scene.beats))

    def _speaker_colors(self, default: str, opacity: float, minimum: float) -> tuple[dict[str | None, str], float]:
        """Each speaker's colour (``speaker_color``; the base voice without a colour: ``default``)
        and the plate opacity at which they all read; a colour that cannot reach ``minimum``
        even on an opaque plate is replaced by ``default`` (warning)."""
        o = self.options
        config = self.context.project.config
        out: dict[str | None, str] = {}
        for name in self._scene_speakers():
            color = default if name is None and config.voice.color is None else speaker_color(config, name, current_theme())
            if o.background is not None:
                need = opacity
                while plate_contrast(color, o.background, need) < minimum and need < 1:
                    need = min(1.0, round(need + 0.05, 2))
                if plate_contrast(color, o.background, need) < minimum:
                    log.warning(f"captions: the colour of speaker {name or 'default'} ({color}) is hard to read on the plate {o.background}; using {default}")
                    color = default
                else:
                    opacity = need
            out[name] = resolve_color(color)
        return out, opacity

    def _readable_terms(self, opacity: float) -> tuple[list[Term], float]:
        """The video's terms drawn in their colours in the captions, and the plate opacity: the
        plate is made more opaque (up to 1) until their colours keep lint's contrast ratio on
        it; a colour that does not read even then (or, without a plate, on the theme background
        of the outline) stays in the text colour."""
        plate = self.options.background
        minimum = self.context.project.config.lint.rules.contrast.min_ratio
        terms = list(active_terms())
        if plate is None:
            behind = current_theme().background
            return [t for t in terms if plate_contrast(t.color, behind) >= minimum], opacity
        readable = [t for t in terms if plate_contrast(t.color, plate) >= minimum]
        while opacity < 1 and any(plate_contrast(t.color, plate, opacity) < minimum for t in readable):
            opacity = min(1.0, round(opacity + 0.05, 2))
        for term in terms:
            if term not in readable:
                log.warning(f"captions: the term '{term.name}' ({term.color}) is hard to read on the plate {plate}; it keeps the text colour there")
        return readable, opacity

    def _colors(self) -> tuple[str, str, float]:
        """Text colour, highlight colour and plate opacity that keep lint's contrast ratio (and
        the speakers' colours, ``self._speaker_color``)."""
        o = self.options
        theme = current_theme()
        minimum = self.context.project.config.lint.rules.contrast.min_ratio
        if o.background is None:
            color = resolve_color(o.color or "text")
            self._speaker_color = self._speaker_colors(color, 0.0, minimum)[0] if self.speakers != "off" else {}
            return color, resolve_color(o.highlight), 0.0
        candidates = [o.color] if o.color else ["text", theme.background, "#FFFFFF", "#000000"]
        opacity = o.background_opacity
        while True:   # the most readable colour; the plate more opaque until it reads over anything
            color = max(candidates, key=lambda c: plate_contrast(c, o.background, opacity))
            if plate_contrast(color, o.background, opacity) >= minimum or opacity >= 1:
                break
            opacity = min(1.0, round(opacity + 0.05, 2))
        if plate_contrast(color, o.background, opacity) < minimum:
            log.warning(f"captions: {o.color or 'the text'} does not reach a contrast of {minimum:g} on the plate {o.background}")
        self._speaker_color = {}
        if self.speakers != "off":
            self._speaker_color, opacity = self._speaker_colors(color, opacity, minimum)
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

    def _cue_texts(self, size: float, weight: str, max_width: float) -> list[tuple[int, CaptionCue, str | None]]:
        """The scene's cues (scene times; each shown until the next starts, the last of a beat
        until the next beat (or its own end when the next overlaps it), the scene's last until
        the scene ends), each with its beat's index and the name of its voice (``None``: the
        base voice). Beats that overlap get one-line cues."""
        scene = self.context.scene
        widths: dict[str, float] = {}

        def width(word: str) -> float:
            if word not in widths:
                widths[word] = measure_text(word, 1e6, size=size, weight=weight).width
            return widths[word]

        space = width("x x") - width("xx")
        project = self.context.project
        audio = project.audio_dir
        voices = project.voice_names()
        tags = project.speaker_tags("name") if self.speakers in ("name", "both") else {}
        language = project.config.language  # where cues break, how words are timed (§54)
        out = []
        beats = scene.beats
        crowded = overlapping_beats([(beat.start, beat.end) for beat in beats])
        for k, beat in enumerate(beats):
            until = max(beats[k + 1].start, beat.end) if k + 1 < len(beats) else scene.duration
            # The written words, timed by the audio of their spoken form (pronunciation, §45;
            # voice sounds, §69.33).
            spoken = project.spoken(project.beat(beat.id))
            words = beat_word_times(audio, beat.id, beat.text, beat.start, beat.end, spoken, language)
            prefix = speaker_prefix(tags[beat.id]) if beat.id in tags else ""
            tag_width = sum(width(w) for w in prefix.split()) + space * (len(prefix.split()) - 1) if prefix else None
            cues = caption_cues(
                beat.text, beat.start, beat.end, words=words, widths=[width(w) for w in beat.text.split()], space=space,
                max_width=max_width, max_lines=1 if k in crowded else self._setting("max_lines"), max_words=self._setting("max_words"), until=until,
                prefix=prefix, prefix_width=tag_width, language=language,
            )
            out.extend((k, cue, voices.get(beat.id)) for cue in cues)
        return out

    # ----- look ------------------------------------------------------------------------------

    def _area(self) -> Region:
        o = self.options
        project = self.context.project
        if project.config.shorts_zones is not None:   # a Short: out of the app's buttons (§101)
            safe = shorts_area(project)
            lift = o.lift or 0.0
        else:
            safe = safe_area()
            lift = o.lift if o.lift is not None else (PORTRAIT_LIFT if orientation() == "portrait" else 0.0)
        if o.position == "bottom" and lift:
            return Region(safe.x0, safe.y0 + lift * safe.height, safe.x1, safe.y1)
        return safe

    def _lines(self, lines: Sequence[str], size: float, weight: str, colors: Sequence[str], max_width: float, pitch: float) -> list[Mobject]:
        """The lines as ``Text``s (each in its colour) centred on x = 0, their baselines
        ``pitch`` apart (shrunk together when a word is wider than ``max_width``)."""
        with using_terms(self._terms):
            mobs = []
            for line, color in zip(lines, colors):
                italic = {f"[{a}:{b}]": ITALIC for a, b in gene_spans(line, self._genes)} if self._genes else {}
                mobs.append(T(line, size, color, weight, disable_ligatures=True, **({"t2s": italic} if italic else {})))
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
        self._terms, opacity = self._readable_terms(opacity)
        self._genes = video_gene_symbols(self.context.project) if o.genes else frozenset()
        lines_max = self._setting("max_lines")
        probe = T("Hxgy", size, color, weight)   # a line's full height, descenders included
        pitch = probe.height * (1 + LINE_GAP)
        band_h = probe.height + pitch * (lines_max - 1) + 2 * PAD_Y
        band = Rectangle(width=max_width + 2 * pad_x, height=band_h).set_fill(opacity=0).set_stroke(width=0)
        place(band, area, fit="none", align=o.position)
        slot = Region(*band.get_corner(DL)[:2], *band.get_corner(UR)[:2])
        self._cues: list[_Cue] = []
        group = VGroup(band)
        colored = self.speakers in ("color", "both")
        entries = self._cue_texts(size, weight, max_width)
        speakers = {id(cue): speaker for _, cue, speaker in entries}
        for stack in stack_cues([(k, cue) for k, cue, _ in entries]):
            texts: list[str] = []
            colors: list[str] = []
            firsts: list[int] = []
            for _, cue in stack.parts:   # the earlier line on top (§69.34)
                firsts.append(len(texts))
                texts += cue.lines
                colors += [self._speaker_color.get(speakers[id(cue)], color) if colored else color] * len(cue.lines)
            lines = self._lines(texts, size, weight, colors, max_width, pitch)
            parts: list[_Part] = []
            for (_, cue), first in zip(stack.parts, firsts):
                parts.append(self._part(cue, lines, first, self._speaker_color.get(speakers[id(cue)], color)))
            block = VGroup(*lines)
            mob: Mobject = block
            if o.background is not None:
                plate = RoundedRectangle(corner_radius=min(0.12, PAD_Y), width=block.width + 2 * pad_x, height=block.height + 2 * PAD_Y)
                plate.set_fill(resolve_color(o.background), opacity=opacity).set_stroke(width=0).move_to(block)
                mob = VGroup(plate, *lines)
            place(mob, slot, fit="none", align=o.position)
            self._cues.append(_Cue(stack.start, stack.end, parts))
            group.add(mob)
        self._starts = [c.start for c in self._cues]
        self._plated = o.background is not None
        return group

    @staticmethod
    def _part(cue: CaptionCue, lines: Sequence[Mobject], first: int, tag_color: str) -> _Part:
        """The cue whose lines are ``lines[first:]`` as built: its "Label:" tag in the speaker's
        colour, its words' start times and glyphs."""
        tag_words = len(cue.prefix.split())
        tag_glyphs = _glyph_map(lines[first], cue.lines[0]) if tag_words else None
        if tag_glyphs is not None:   # the "Label:" tag in the speaker's colour
            VGroup(*(lines[first].submobjects[i] for g in tag_glyphs[:tag_words] for i in g)).set_fill(tag_color)
        glyphs: list[tuple[int, list[int]] | None] = []
        for k, line in enumerate(cue.lines):
            found = _glyph_map(lines[first + k], line)
            entries: list[tuple[int, list[int]] | None] = [(first + k, g) for g in found] if found is not None else [None] * len(line.split(" "))
            glyphs.extend(entries[tag_words:] if k == 0 else entries)   # the tag is not a spoken word
        return _Part([w.start for w in cue.words], glyphs)

    # ----- time ------------------------------------------------------------------------------

    def state(self, t: float) -> Hashable | None:
        """The caption shown at video time ``t`` (its index), with karaoke the word being spoken
        in each of its parts: ``(caption, (word, ...))`` (``word`` -1 before the first word)."""
        st = t - self.context.scene.start
        k = bisect_right(self._starts, st + 1e-9) - 1
        if k < 0 or st >= self._cues[k].end - 1e-9:
            return None
        if not self.karaoke:
            return k
        return (k, tuple(bisect_right(part.word_starts, st + 1e-9) - 1 for part in self._cues[k].parts))

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        if not self.karaoke:
            return mobject.submobjects[1 + int(state)]  # type: ignore[call-overload]
        k, words = state  # type: ignore[misc]
        cue = mobject.submobjects[1 + k]
        copy: Mobject | None = None
        for part, word in zip(self._cues[k].parts, words):
            place_of = part.glyphs[word] if 0 <= word < len(part.glyphs) else None
            if place_of is None:
                continue
            copy = cue.copy() if copy is None else copy
            line_index, indices = place_of
            line = copy.submobjects[line_index + (1 if self._plated else 0)]
            chars = VGroup(*(line.submobjects[i] for i in indices))
            chars.set_fill(self._highlight)
            # grow by at most POP_ROOM of a space on each side, so it never touches its neighbours
            pop = min(self.options.pop, 1 + 2 * POP_ROOM * self._space / max(chars.width, 1e-6))
            if pop > 1:
                chars.scale(pop)
        return cue if copy is None else copy
