"""The Listen page (DESIGN.md §92): ``docs/music/README.md``, written by ``vidgen music page``.

Every clip on it is made by vidgen itself: a 15 s MP3 and a spectrogram of each built-in music bed
(:data:`vidgen.music.BUILTIN_BEDS`), the pieces made with the score format that became beds
(:data:`SCORE_PIECES`, Steps 189 and 192: how they were made, linking the bed's clip), rows of the
built-in sound effects
(:data:`vidgen.sfx.BUILTIN_SOUNDS`, every one of them) and of the ambience beds, and composed music
in two moods when the ``music`` extra and the SoundFont are there. Deterministic: the same vidgen,
ffmpeg (libmp3lame), Pillow and symusic give the same files, so regenerating changes nothing.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vidgen import ambience, composer, music, sfx
from vidgen.errors import VidgenError
from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg
from vidgen.sfx import RATE
from vidgen.studio import MusicScore, load_music_score
from vidgen.studio.templates import TEMPLATE_DIR

#: Length of a music clip (s): a bed's, a composed mood's.
CLIP_SECONDS = 15.0
#: Fades of a music clip (s), so it does not start or stop with a click.
FADE_IN_SECONDS = 0.2
FADE_OUT_SECONDS = 1.5
#: How much louder than in a video the clips play (dB). Music: from its mix level
#: (:data:`vidgen.music.MUSIC_LEVEL`, -28 LUFS) to -16 LUFS, the level of a finished video.
MUSIC_GAIN_DB = 12.0
#: Sound effects sit at -27 LUFS (their loudest 400 ms); ambience beds at -32 to -40 LUFS.
SOUND_GAIN_DB = 8.0
AMBIENCE_GAIN_DB = 12.0
#: No clip's samples go above this (dBFS): a clip's gain is lowered to stay under it.
PEAK_CEILING_DB = -1.5
#: MP3 bit rates (CBR): stereo clips (music, ambience), mono clips (sound effects).
STEREO_BITRATE = "128k"
MONO_BITRATE = "96k"
#: Spectrograms: pixels per second of the clip, height in pixels, the frequency range shown
#: (log scale, Hz), the level range (dB, a full-scale sine is 0 dB) and the grid lines (Hz).
SPECTROGRAM_PX_PER_SECOND = 32
SPECTROGRAM_HEIGHT = 120
SPECTROGRAM_HZ = (40.0, 8000.0)
SPECTROGRAM_DB = (-95.0, -10.0)
SPECTROGRAM_GRID_HZ = (100.0, 1000.0)
SPECTROGRAM_FFT = 4096
#: Where a bed's clip starts when its loop's top is not the best part to hear: the moment (a
#: fraction of the loop) lands :data:`CLIP_LEAD_SECONDS` into the clip. A clip past the loop's end
#: goes on at its start, as the bed does in a video.
CLIP_MOMENTS: dict[str, tuple[float, str]] = {
    "discovery": (0.72, "the pad at its brightest"),
    "breakthrough": (0.5, "the lift to E-flat major"),
    "momentum": (1.0, "the riser into the top of the loop"),
    "ascent": (0.5, "the build and the lift"),
    "horizon": (0.5, "the build and the lift to F major"),
    "tidewater": (0.5, "the riser and the lift with its bell melody"),
    "skyline": (0.5, "the end of the build and the lift"),
    "time_of_flight": (0.5, "the end of the build and the lift with its lead"),
}
CLIP_LEAD_SECONDS = 6.0
#: The composed moods with a clip: one for explainers, one for cartoons.
COMPOSED_MOODS = ("curious", "playful")


@dataclass(frozen=True)
class ScorePiece:
    """A piece an author wrote in the score format (§93) that became a built-in bed (a score bed,
    ``studio/beds/<name>.yaml``; Step 192): ``made`` says how it was made and ``example`` names
    the example project that plays it and keeps the log of how it was made. Its clip and
    spectrogram are the bed's (no second copy)."""

    name: str
    made: str
    example: str


#: The "made with the score format" rows, in page order.
SCORE_PIECES: tuple[ScorePiece, ...] = (
    ScorePiece(
        "time_of_flight",
        "An AI author's piece, made from the `momentum` template one change at a time (new key, tempo, "
        "chords, sections, arpeggio, pings and lead), checked with `vidgen music check` after each; "
        "approved as a built-in bed",
        "gps-time-of-flight",
    ),
)
#: The page's folder and file names.
PAGE_NAME = "README.md"
MEDIA_DIR = "media"

# A perceptual dark-to-bright palette (anchors of matplotlib's "inferno", which is CC0).
_PALETTE_ANCHORS = (
    (0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99), (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164),
)
_LEVELS = 64
_GRID_INDEX = _LEVELS
_GRID_COLOUR = (200, 200, 200)


@dataclass(frozen=True)
class SoundRow:
    """A clip of several built-in sounds: ``events`` are ``(seconds, sound, pitch, duration)``
    (``duration`` ``None``: the sound's own)."""

    name: str
    title: str
    seconds: float
    events: tuple[tuple[float, str, float, float | None], ...]


def _steps(start: float) -> tuple[tuple[float, str, float, float | None], ...]:
    """Four steps of each footstep sound, a walk's pace apart, a pause between the surfaces."""
    surfaces = ("footstep", "step_grass", "step_gravel", "step_wood", "step_stone")
    return tuple((round(start + k * 2.3 + j * 0.45, 2), name, 0.0, None) for k, name in enumerate(surfaces) for j in range(4))


#: The sound-effect clips, in page order; together they play every built-in sound.
SOUND_ROWS: tuple[SoundRow, ...] = (
    SoundRow(
        "sfx-screen", "On-screen moments", 13.4,
        (
            (0.3, "whoosh", 0.0, None), (1.3, "pop", 0.0, None), (1.7, "pop", 2.0, None), (2.1, "pop", 4.0, None),
            (2.9, "click", 0.0, None), (3.5, "tick", 0.0, None), (3.9, "tick", 0.0, None), (4.3, "tick", 0.0, None),
            (5.0, "typing", 0.0, 1.6), (7.0, "chime", 0.0, None), (8.8, "success", 0.0, None), (10.0, "error", 0.0, None),
            (11.0, "swoosh", 0.0, None), (12.1, "thud", 0.0, None),
        ),
    ),
    SoundRow(
        "sfx-stings", "A build and three stings", 9.4,
        ((0.3, "riser", 0.0, None), (2.3, "sting_reveal", 0.0, None), (4.6, "sting_comic", 0.0, None), (6.5, "sting_sad", 0.0, None)),
    ),
    SoundRow("sfx-footsteps", "Footsteps by surface: shoe, grass, gravel, wood, stone", 11.6, _steps(0.3)),
    SoundRow(
        "sfx-home", "Door, phone, bell", 6.6,
        ((0.3, "knock", 0.0, None), (1.5, "unlock", 0.0, None), (2.1, "creak", 0.0, None), (3.6, "phone", 0.0, None), (5.2, "bell", 0.0, None)),
    ),
    SoundRow(
        "sfx-cartoon", "Cartoon foley and voice sounds", 8.2,
        (
            (0.3, "boing", 0.0, None), (1.2, "coin", 0.0, None), (1.6, "coin", 2.0, None), (2.0, "coin", 4.0, None),
            (2.7, "twinkle", 0.0, None), (3.9, "splash", 0.0, None), (5.0, "beep", 0.0, None), (5.9, "gasp", 0.0, None),
            (6.7, "sigh", 0.0, None),
        ),
    ),
    SoundRow(
        "sfx-rides", "Vehicles, a rocket and thunder", 9.4,
        ((0.3, "engine", 0.0, None), (2.0, "brakes", 0.0, None), (3.0, "burner", 0.0, None), (4.6, "launch", 0.0, None), (6.1, "thunder", 0.0, None)),
    ),
)
#: The ambience clip: each bed for this long (s), cross-faded into the next.
AMBIENCE_PART_SECONDS = 3.5
AMBIENCE_FADE_SECONDS = 0.5


@dataclass
class ListenResult:
    """What :func:`make_listen_page` wrote."""

    output: Path
    page: Path
    clips: list[Path] = field(default_factory=list)
    spectrograms: list[Path] = field(default_factory=list)
    composed: bool = False
    composed_note: str = ""

    @property
    def bytes(self) -> int:
        """Size of the page and its media together."""
        return sum(p.stat().st_size for p in (self.page, *self.clips, *self.spectrograms))


# ----- audio -------------------------------------------------------------------------------------


def _faded(x: np.ndarray, fade_in: float, fade_out: float) -> np.ndarray:
    """``x`` (``(n, c)``) with raised-cosine fades at both ends."""
    y = x.astype(np.float64)
    for seconds, part in ((fade_in, slice(None, None)), (fade_out, slice(None, None, -1))):
        m = min(int(seconds * RATE), len(y))
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(m) / max(m, 1))
        y[part][:m] *= ramp[:, None]
    return y


def _gained(x: np.ndarray, gain_db: float) -> np.ndarray:
    """``x`` raised by ``gain_db``, less if its loudest sample would pass :data:`PEAK_CEILING_DB`."""
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak > 0:
        gain_db = min(gain_db, PEAK_CEILING_DB - 20 * math.log10(peak))
    return x * 10 ** (gain_db / 20)


def bed_clip_start(name: str) -> float:
    """Seconds into a bed's loop where its clip starts (:data:`CLIP_MOMENTS`; else 0)."""
    moment = CLIP_MOMENTS.get(name)
    if moment is None:
        return 0.0
    seconds = music.BUILTIN_BEDS[name].seconds
    return round((moment[0] * seconds - CLIP_LEAD_SECONDS) % seconds, 2)


def bed_clip(name: str) -> np.ndarray:
    """``(n, 2)``: :data:`CLIP_SECONDS` of a bed's loop from :func:`bed_clip_start`, faded, raised."""
    loop = music.bed_loop(name)
    first = round(bed_clip_start(name) * RATE)
    index = (first + np.arange(round(CLIP_SECONDS * RATE))) % len(loop)
    return _gained(_faded(loop[index], FADE_IN_SECONDS, FADE_OUT_SECONDS), MUSIC_GAIN_DB)


def piece_score(piece: ScorePiece) -> MusicScore:
    """The score file of a :data:`SCORE_PIECES` entry (its bed's, ``studio/beds``), read (not rendered)."""
    if not music.BUILTIN_BEDS[piece.name].score:
        raise VidgenError(f"listen page: {piece.name} is not a bed written as a score file")
    return load_music_score(TEMPLATE_DIR / f"{piece.name}.yaml")


def sound_row_clip(row: SoundRow) -> np.ndarray:
    """``(n, 1)``: the row's sounds at their times (mono, as the built-ins are), raised."""
    out = np.zeros(round(row.seconds * RATE))
    for at, name, pitch, duration in row.events:
        sound = sfx.synthesize(name, duration, pitch).astype(np.float64)
        start = round(at * RATE)
        part = sound[: max(0, len(out) - start)]
        out[start : start + len(part)] += part
    return _gained(out[:, None], SOUND_GAIN_DB)


def ambience_clip() -> np.ndarray:
    """``(n, 2)``: every ambience bed for :data:`AMBIENCE_PART_SECONDS`, cross-faded (equal power)."""
    part, fade = round(AMBIENCE_PART_SECONDS * RATE), round(AMBIENCE_FADE_SECONDS * RATE)
    beds = ambience.AMBIENCE_BEDS
    out = np.zeros((part * len(beds) + fade, 2))
    ramp = np.sin(0.5 * np.pi * np.arange(fade) / fade)[:, None]
    for k, name in enumerate(beds):
        loop = ambience.BEDS[name].loop().astype(np.float64)
        x = loop[np.arange(part + fade) % len(loop)].copy()
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]
        out[k * part : k * part + part + fade] += x
    return _gained(out, AMBIENCE_GAIN_DB)


def composed_available() -> str:
    """``""`` when composed clips can be made here (symusic and the cached default SoundFont,
    never downloaded by this page), else why not."""
    from vidgen import soundfont, synth

    if synth.symusic_version() is None:
        return f"the `music` extra is not installed (`{synth.INSTALL_COMMAND}`)"
    if not soundfont.default_path().is_file():
        return "the SoundFont is not downloaded (`vidgen soundfont fetch`)"
    return ""


def composed_clip(mood: str) -> tuple[np.ndarray, composer.Piece]:
    """``(n, 2)``: the first :data:`CLIP_SECONDS` of the mood's piece (default settings), faded,
    raised; and the piece. Needs :func:`composed_available`."""
    from vidgen import soundfont, synth

    piece = composer.compose_piece(mood)
    audio = synth.render_score(piece.score, soundfont.resolve(None, Path.cwd(), download=False))
    return _gained(_faded(audio[: round(CLIP_SECONDS * RATE)], FADE_IN_SECONDS / 4, FADE_OUT_SECONDS), MUSIC_GAIN_DB), piece


def write_mp3(samples: np.ndarray, target: Path) -> None:
    """``samples`` (``(n, c)``, 48 kHz) as a CBR MP3 at ``target`` (libmp3lame, no tags, no
    encoder version: the same samples give the same file)."""
    channels = samples.reshape(len(samples), -1).shape[1]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vidgen-listen-") as tmp:
        wav = Path(tmp) / "clip.wav"
        sfx.write_wav(wav, samples)
        run_ffmpeg(
            find_ffmpeg(),
            [
                "-i", str(wav), "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
                "-c:a", "libmp3lame", "-b:a", STEREO_BITRATE if channels > 1 else MONO_BITRATE,
                "-id3v2_version", "0", "-write_xing", "0", str(target),
            ],
            f"encoding {target.name} (an ffmpeg with libmp3lame is needed)",
        )


# ----- spectrograms ------------------------------------------------------------------------------


def _palette() -> list[int]:
    """:data:`_LEVELS` colours along :data:`_PALETTE_ANCHORS`, then the grid colour; flat RGB."""
    anchors = np.array(_PALETTE_ANCHORS, dtype=np.float64)
    u = np.linspace(0, len(anchors) - 1, _LEVELS)
    colours = np.stack([np.interp(u, np.arange(len(anchors)), anchors[:, c]) for c in range(3)], axis=1)
    return [int(round(v)) for v in colours.flatten()] + list(_GRID_COLOUR)


def spectrogram_levels(samples: np.ndarray) -> np.ndarray:
    """``(SPECTROGRAM_HEIGHT, width)`` palette indices of a clip's spectrogram (mono mix): time
    left to right at :data:`SPECTROGRAM_PX_PER_SECOND`, frequency bottom to top on a log scale
    over :data:`SPECTROGRAM_HZ`, level over :data:`SPECTROGRAM_DB` in :data:`_LEVELS` steps,
    dotted grid lines at :data:`SPECTROGRAM_GRID_HZ`."""
    x = samples.reshape(len(samples), -1).astype(np.float64).mean(axis=1)
    width = max(1, round(len(x) / RATE * SPECTROGRAM_PX_PER_SECOND))
    window = np.hanning(SPECTROGRAM_FFT)
    half = SPECTROGRAM_FFT // 2
    padded = np.pad(x, (half, half))
    centres = ((np.arange(width) + 0.5) * len(x) / width).astype(int)
    frames = np.stack([padded[c : c + SPECTROGRAM_FFT] for c in centres]) * window
    amplitude = np.abs(np.fft.rfft(frames, axis=1)) / (window.sum() / 2)
    db = 20 * np.log10(np.maximum(amplitude, 1e-12))
    freqs = np.fft.rfftfreq(SPECTROGRAM_FFT, 1 / RATE)
    rows = np.geomspace(SPECTROGRAM_HZ[1], SPECTROGRAM_HZ[0], SPECTROGRAM_HEIGHT)
    image = np.stack([np.interp(rows, freqs, column) for column in db], axis=1)
    lo, hi = SPECTROGRAM_DB
    levels = np.round(np.clip((image - lo) / (hi - lo), 0.0, 1.0) * (_LEVELS - 1)).astype(np.uint8)
    for hz in SPECTROGRAM_GRID_HZ:
        row = int(np.argmin(np.abs(rows - hz)))
        levels[row, ::4] = _GRID_INDEX
    return levels


def write_spectrogram(samples: np.ndarray, target: Path) -> None:
    """A clip's spectrogram (:func:`spectrogram_levels`) as a palette PNG at ``target``."""
    from PIL import Image

    levels = spectrogram_levels(samples)
    image = Image.frombytes("P", (levels.shape[1], levels.shape[0]), np.ascontiguousarray(levels).tobytes())
    image.putpalette(_palette())
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, optimize=True)


# ----- the page ----------------------------------------------------------------------------------


def _media(name: str, suffix: str) -> str:
    return f"{MEDIA_DIR}/{name}{suffix}"


def _clip_link(name: str, seconds: float) -> str:
    return f"[▶ listen ({seconds:g} s)]({_media(name, '.mp3')})"


def _spectrogram_img(name: str, alt: str, width: int = 300) -> str:
    return f'<img src="{_media(name, ".png")}" width="{width}" alt="Spectrogram: {alt}">'


def _bed_facts(bed: music.Bed) -> str:
    tempo = f"{bed.tempo} BPM" if bed.tempo else "no beat"
    return f"{bed.key}, {tempo}, {bed.seconds:.1f} s loop"


def _bed_row(name: str) -> str:
    bed = music.BUILTIN_BEDS[name]
    start = bed_clip_start(name)
    moment = CLIP_MOMENTS.get(name)
    where = f"<br>from {start:g} s: {moment[1]}" if moment else ""
    use = bed.use[0].upper() + bed.use[1:]
    return (
        f"| `{name}` | {_bed_facts(bed)} | {use} | {_spectrogram_img('bed-' + name, name)} | "
        f"{_clip_link('bed-' + name, CLIP_SECONDS)}{where} |"
    )


def _events_text(row: SoundRow) -> str:
    """``0.3 s `whoosh`, 1.3, 1.7, 2.1 s `pop` (pitch 0, +2, +4)``: a run of one sound in one entry."""
    runs: list[list[tuple[float, str, float, float | None]]] = []
    for event in row.events:
        if runs and runs[-1][0][1] == event[1]:
            runs[-1].append(event)
        else:
            runs.append([event])
    parts = []
    for run in runs:
        times = ", ".join(f"{e[0]:g}" for e in run)
        pitches = f" (pitch {', '.join(f'{e[2]:+g}' if e[2] else '0' for e in run)})" if any(e[2] for e in run) else ""
        parts.append(f"{times} s `{run[0][1]}`{pitches}")
    return ", ".join(parts)


def _piece_row(piece: ScorePiece) -> str:
    score = piece_score(piece)
    tempo = f"{score.tempo:g} BPM"
    kind = "loop" if score.loop else "piece with an ending"
    example = f"[examples/{piece.example}](../../examples/{piece.example}/README.md)"
    return (
        f"| `{piece.name}`<br>{score.title} | {score.key.name}, {tempo}, {score.seconds:.1f} s {kind} | "
        f"{piece.made}; it plays under {example}, whose README keeps the log of every version and the check report | "
        f"the bed `{piece.name}` above: {_clip_link('bed-' + piece.name, CLIP_SECONDS)} |"
    )


def page_text(composed_pieces: Sequence[composer.Piece], composed_note: str) -> str:
    """The Listen page's Markdown (no dates, no paths: the same inputs give the same text)."""
    beds = list(music.BUILTIN_BEDS)
    score_beds = [name for name, bed in music.BUILTIN_BEDS.items() if bed.score]
    score_beds_text = []
    if score_beds:
        quoted = [f"`{name}`" for name in score_beds]
        names = ", ".join(quoted[:-1]) + " and " + quoted[-1] if len(quoted) > 1 else quoted[0]
        score_beds_text = [
            f"{names} are written in the score format (below): `vidgen music template {score_beds[0]}` gives",
            "the very score the bed plays, to start a piece of your own from.",
            "",
        ]
    score_rows: list[str] = []
    if SCORE_PIECES:
        score_rows = [
            "## Made with the score format",
            "",
            "Music written as a score file: YAML with a key, a tempo, sections, chords and tracks of step",
            "patterns, played by vidgen's own instruments. Agents write them without listening: they start",
            "from a template of a built-in bed, change one thing at a time and read `vidgen music check`'s",
            "report after each change. A score file in a project's `assets/music/` plays like a bed",
            "(`music: my_theme`). How: [score files](../CONFIG.md#score-files-vidgen-music-render),",
            "[templates of the beds](../CONFIG.md#templates-of-the-built-in-beds-vidgen-music-template),",
            "[checking a piece](../CONFIG.md#checking-a-piece-vidgen-music-check),",
            "[project pieces](../CONFIG.md#project-pieces-score-files-in-a-video) and the",
            "[music craft notes](../COOKBOOK-MUSIC.md). The piece below was written this way and is now",
            "a built-in bed (hear it in the beds table above).",
            "",
            "| piece | key, tempo, length | how it was made | hear it |",
            "|---|---|---|---|",
            *(_piece_row(piece) for piece in SCORE_PIECES),
            "",
            "To do the same by ear, [`vidgen studio`](../CONFIG.md#music-studio-vidgen-studio) opens any",
            "bed above as an editable score in your browser: change it, listen as you go, A/B versions,",
            "try variations, pin notes for an AI agent to answer, and save it into your project.",
            "",
        ]
    lines = [
        "# Listen: vidgen's music and sounds",
        "",
        "<!-- Generated by `vidgen music page` (src/vidgen/listen.py). Do not edit by hand: run it again. -->",
        "",
        "Every sound on this page was made by vidgen from code. The music beds, sound effects and",
        "ambience are synthesised (no recordings, no samples); composed music is written note by note",
        "and played with the instruments of the GeneralUser GS SoundFont. Use them in your videos, also",
        "commercially; no attribution needed. GitHub cannot play audio inside a page: a **▶ listen**",
        "link opens the MP3 in GitHub's player (or downloads it).",
        "",
        f"The clips are MP3s, {STEREO_BITRATE}bps stereo (sound effects {MONO_BITRATE}bps mono, as they are made). Music",
        f"plays {MUSIC_GAIN_DB:g} dB louder here than in a mix, at {music.MUSIC_LEVEL + MUSIC_GAIN_DB:g} LUFS, a finished video's level (in a",
        f"video a bed sits at {music.MUSIC_LEVEL:g} LUFS and ducks under the narration). Each spectrogram shows its",
        f"clip: time left to right, pitch bottom to top on a log scale from {SPECTROGRAM_HZ[0]:g} Hz to",
        f"{SPECTROGRAM_HZ[1] / 1000:g} kHz, brighter is louder; the dotted lines mark"
        f" {' and '.join(f'{hz:g} Hz' if hz < 1000 else f'{hz / 1000:g} kHz' for hz in SPECTROGRAM_GRID_HZ)}.",
        "",
        "Reference: [background music](../CONFIG.md#background-music-music),",
        "[composed music](../CONFIG.md#composed-music-compose),",
        "[sound effects](../CONFIG.md#sound-effects-sfx). Agents, who cannot listen, read the same",
        "sounds described in words with `vidgen list-music` and `vidgen list-sfx`.",
        "",
        "## Music beds",
        "",
        f"{len(beds)} seamless loops, generated when the video is joined; the same name always gives the same",
        "music. `music: momentum` plays one under the whole video (`{source: momentum, volume: -2}`,",
        "or a list of cues with `from` / `to` scenes).",
        "",
        *score_beds_text,
        "| bed | key, tempo, loop | use it for | spectrogram | clip |",
        "|---|---|---|---|---|",
        *(_bed_row(name) for name in beds),
        "",
        *score_rows,
        "## Sound effects",
        "",
        f"{len(sfx.BUILTIN_SOUNDS)} sounds, synthesised when the video is joined: `- sfx: whoosh` in a beat, a scene's `sfx:` list, or",
        "played by cartoon actions (foley: footsteps by surface, doors, pickups, rides). Each clip",
        f"plays several sounds at the times listed, {SOUND_GAIN_DB:g} dB louder than in a mix; together they",
        "play every built-in sound.",
        "",
        "| clip | sounds (seconds into the clip) | spectrogram | listen |",
        "|---|---|---|---|",
        *(
            f"| {row.title} | {_events_text(row)} | {_spectrogram_img(row.name, row.title, 240)} | {_clip_link(row.name, row.seconds)} |"
            for row in SOUND_ROWS
        ),
        "",
        "## Ambience beds",
        "",
        f"{len(ambience.AMBIENCE_BEDS)} beds, played under cartoon scenes while the rain falls, a fire burns, or a set calls for them",
        "(birds by day, crickets at night, a city street, a room's tone). The clip plays each for",
        f"{AMBIENCE_PART_SECONDS:g} s, in this order: {', '.join(f'`{b}`' for b in ambience.AMBIENCE_BEDS)}.",
        "",
        f"{_spectrogram_img('ambience', 'the six ambience beds in turn', 480)}",
        "",
        _clip_link("ambience", round(AMBIENCE_PART_SECONDS * len(ambience.AMBIENCE_BEDS) + AMBIENCE_FADE_SECONDS, 2)),
        "",
        "## Composed music",
        "",
        "With the `music` extra, `music: {compose: {mood: curious}}` writes original music for the",
        "video and plays it with real instruments: every scene change on a bar line, a mood per",
        "scene, swells on reveals and a closing cadence. Eight moods:",
        "",
        "| mood | for | key, tempo |",
        "|---|---|---|",
        *(f"| `{m['name']}` | {m['use']} | {m['key']}, {m['tempo']:g} BPM, {m['meter']} |" for m in composer.mood_entries()),
        "",
    ]
    if composed_pieces:
        lines += [
            f"The first {CLIP_SECONDS:g} s of a piece in two moods (default settings, `vidgen music preview --mood NAME`):",
            "",
            "| mood | parts | spectrogram | clip |",
            "|---|---|---|---|",
            *(
                f"| `{p.mood.name}` | {', '.join(f'{v.role}: {v.instrument.name}' for v in p.voices)} | "
                f"{_spectrogram_img('composed-' + p.mood.name, p.mood.name)} | {_clip_link('composed-' + p.mood.name, CLIP_SECONDS)} |"
                for p in composed_pieces
            ),
            "",
        ]
    else:
        lines += [f"No clips here: when this page was made, {composed_note}.", ""]
    return "\n".join(lines)


def make_listen_page(output: Path, composed: bool = True) -> ListenResult:
    """Write the Listen page and its clips and spectrograms into ``output`` (``media/`` beside the
    page). ``composed``: also the composed moods' clips when :func:`composed_available`."""
    output.mkdir(parents=True, exist_ok=True)
    result = ListenResult(output=output, page=output / PAGE_NAME)
    clips: list[tuple[str, np.ndarray]] = [("bed-" + name, bed_clip(name)) for name in music.BUILTIN_BEDS]
    clips += [(row.name, sound_row_clip(row)) for row in SOUND_ROWS]
    clips.append(("ambience", ambience_clip()))
    pieces: list[composer.Piece] = []
    result.composed_note = composed_available() if composed else "composed clips were turned off"
    if not result.composed_note:
        for mood in COMPOSED_MOODS:
            audio, piece = composed_clip(mood)
            clips.append(("composed-" + mood, audio))
            pieces.append(piece)
        result.composed = True
    for name, audio in clips:
        if not np.all(np.isfinite(audio)):
            raise VidgenError(f"listen page: clip {name} is not finite")
        mp3, png = output / _media(name, ".mp3"), output / _media(name, ".png")
        write_mp3(audio, mp3)
        write_spectrogram(audio, png)
        result.clips.append(mp3)
        result.spectrograms.append(png)
    result.page.write_text(page_text(pieces, result.composed_note), encoding="utf-8")
    return result
