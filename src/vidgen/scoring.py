"""Music cues for dramas (DESIGN.md §112.2): named themes that scenes and sections play and beats
hear briefly, cross-fading at the scene changes, and a check that the music does not fight dense
dialogue.

**Themes.** ``score.themes`` names music: a built-in bed, a project piece (a studio score file
under ``assets/music``) or an audio file, with its level and maybe a variation (another
``section`` / ``start``, ``transpose``, ``tempo``, only some ``tracks``). A variation that changes
the notes re-renders the theme's score (a project piece's, a score bed's, or a built-in bed's score
template, :mod:`vidgen.studio.templates`) and keeps the render in ``build/music``.

**Scene themes.** A scene's (section's) ``music: NAME`` (or ``{theme, variation, volume}``) plays
that theme from there on: the scenes after it keep it until one names another or says ``music:
false``. At a change the theme playing fades out and the next fades in over ``score.crossfade``
seconds centred on the scene change (:func:`theme_pieces`, the walk of
:func:`vidgen.sound_design.ambience_entries`); the same theme with the same variation plays on. The
first fades in over ``score.fade_in`` from the start, the last out over ``score.fade_out`` by the
end. The fades follow ``score.curve`` (:func:`fade_shape`).

**Motifs.** A beat's ``motif:`` plays a theme from its start (or section) for ``length`` seconds
from ``at`` (the line's start or end, a word it says, a fraction of it) while the scene's theme dips
``dip`` dB (:func:`motif_pieces`); a beat's sting dips it ``score.sting_dip`` dB while it sounds
(:func:`sting_windows`). :func:`vidgen.mix.plan_score` turns the pieces into music placements,
ducked under the voices by ``score.duck`` (presets: ``drama`` releases slowly and swells into the
pauses).

**Check.** :func:`dense_dialogue_check` measures, after the mix, the music's loudness under the
voices where they speak almost without pauses (and, for the record, under all dialogue and in the
pauses).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.config import BeatConfig, MotifCue, MusicCue, SceneMusic, ThemeVariation, VideoConfig
from vidgen.errors import VidgenError
from vidgen.sfx import RATE

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.studio import MusicScore

#: The shortest fade (s): a cut that does not click.
MIN_FADE = 0.05
#: Frames of the dense-dialogue check (100 ms) and its window (s): speech filling at least
#: :data:`DENSE_SHARE` of the window around a moment is dense dialogue; runs shorter than
#: :data:`DENSE_MIN` seconds are not reported. Pauses of at least :data:`PAUSE_MIN` seconds count
#: as pauses.
CHECK_FRAME = RATE // 10
DENSE_WINDOW = 5.0
DENSE_SHARE = 0.8
DENSE_MIN = 2.0
PAUSE_MIN = 1.0
#: How a sting's dip of the scene's theme starts and ends (s).
STING_DIP_RAMPS = (0.05, 0.6)
#: Bumped when a variation renders differently, so its cached render is made again.
VARIATION_VERSION = 1


# ----- fades -----------------------------------------------------------------------------------------


def fade_shape(u: np.ndarray, curve: str) -> np.ndarray:
    """A fade-in's gain at ``u`` (0 → 1 over the fade, clipped): ``equal_power`` sin(πu/2) (two
    different pieces cross-fade at an even loudness), ``linear`` u, ``smooth`` an S curve
    (raised cosine)."""
    u = np.clip(u, 0.0, 1.0)
    if curve == "linear":
        return u
    if curve == "smooth":
        return 0.5 - 0.5 * np.cos(np.pi * u)
    return np.sin(0.5 * np.pi * u)


def envelope(times: np.ndarray, start: float, end: float, fade_in: float, fade_out: float, curve: str) -> np.ndarray:
    """1 between the fades, fading in from ``start`` and out by ``end`` in ``curve``, 0 outside."""
    out = np.where((times >= start) & (times <= end), 1.0, 0.0)
    if fade_in > 0:
        out = out * fade_shape((times - start) / fade_in, curve)
    if fade_out > 0:
        out = out * fade_shape((end - times) / fade_out, curve)
    return out


# ----- themes ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThemePlay:
    """A theme as it plays once: its ``name`` (as written), ``source``, level (dB) and variation."""

    name: str
    source: str
    volume: float = 0.0
    section: str | None = None
    start: float = 0.0
    transpose: int | None = None
    tempo: float | None = None
    tracks: tuple[str, ...] | None = None

    @property
    def changes_score(self) -> bool:
        """Whether its score is rendered again (transpose, tempo or tracks)."""
        return self.transpose is not None or self.tempo is not None or self.tracks is not None

    def variation(self) -> dict[str, Any]:
        """Its variation as plain data (only what is set)."""
        data = {"section": self.section, "start": self.start or None, "transpose": self.transpose, "tempo": self.tempo,
                "tracks": list(self.tracks) if self.tracks is not None else None}
        return {k: v for k, v in data.items() if v is not None}

    @property
    def label(self) -> str:
        """``name`` with its source and variation, for summaries."""
        parts = [] if self.source == self.name else [self.source]
        parts += [f"{k} {' '.join(v) if isinstance(v, list) else f'{v:+d}' if k == 'transpose' else v}" for k, v in self.variation().items()]
        return f"{self.name} ({', '.join(parts)})" if parts else self.name


def resolve(config: VideoConfig, name: str, variation: ThemeVariation | None = None, gain: float = 0.0) -> ThemePlay:
    """The theme ``name`` (a ``score.themes`` entry, else a bed or project piece of that name)
    with ``variation``'s keys over its own, ``gain`` dB added."""
    theme = config.score.themes.get(name)
    base: dict[str, Any] = {"source": name, "volume": 0.0}
    if theme is not None:
        base = theme.model_dump(exclude_none=True)
    if variation is not None:
        base.update(variation.model_dump(exclude_none=True))
    tracks = base.get("tracks")
    return ThemePlay(name, str(base["source"]), float(base.get("volume", 0.0)) + gain, base.get("section"), float(base.get("start", 0.0)),
                     base.get("transpose"), base.get("tempo"), tuple(tracks) if tracks is not None else None)


def scene_theme(config: VideoConfig, music: bool | SceneMusic) -> ThemePlay | bool | None:
    """What a scene's ``music:`` asks of the themes: a :class:`ThemePlay` (play it from here),
    ``False`` (stop) or ``None`` (go on with the theme before)."""
    if music is False:
        return False
    if isinstance(music, SceneMusic) and music.theme is not None:
        return resolve(config, music.theme, music.variation)
    return None


def uses_score(config: VideoConfig) -> bool:
    """Whether a scene plays a theme or a beat a motif (else nothing here changes the mix)."""
    return any((isinstance(s.music, SceneMusic) and s.music.theme is not None) or any(b.motif is not None for b in s.beats) for s in config.scenes)


@dataclass
class ThemePiece:
    """A theme placed in the audio: from ``start`` to ``end`` (seconds) with its fades; a
    ``motif`` plays over the scene's theme, which dips ``dip`` dB under it."""

    play: ThemePlay
    start: float
    end: float
    fade_in: float
    fade_out: float
    scene: int
    motif: bool = False
    dip: float = 0.0


def theme_pieces(config: VideoConfig, scenes: Sequence[tuple[float, float]], total: float) -> list[ThemePiece]:
    """The scene themes (see the module doc) over scenes at ``(start, duration)`` (seconds) of
    audio ``total`` seconds long."""
    score = config.score
    cross = score.crossfade
    half = cross / 2
    playing: ThemePiece | None = None
    done: list[ThemePiece] = []
    for i, (spec, (start, _)) in enumerate(zip(config.scenes, scenes)):
        wanted = scene_theme(config, spec.music)
        if wanted is None or (isinstance(wanted, ThemePlay) and playing is not None and wanted == playing.play):
            continue
        if playing is not None:
            playing.end, playing.fade_out = max(start + half, playing.start), max(cross, MIN_FADE)
            done.append(playing)
            playing = None
        if isinstance(wanted, ThemePlay):
            first = start <= 0
            begin = 0.0 if first else max(start - half, 0.0)
            playing = ThemePiece(wanted, begin, math.inf, score.fade_in if first else max(cross, MIN_FADE), 0.0, i)
    if playing is not None:
        playing.end, playing.fade_out = total, max(score.fade_out, MIN_FADE)
        done.append(playing)
    return [p for p in done if p.end > p.start]


def motif_time(project: Project, beat: BeatConfig, start: float, at: float | str) -> float:
    """When a motif at ``at`` of a beat whose line starts at ``start`` begins: ``start``, ``end``
    (its speech ends), a word (:func:`vidgen.sound_design.word_offset`) or a fraction of its speech."""
    from vidgen.sound_design import word_offset
    from vidgen.word_anchors import beat_words

    if at == "start":
        return start
    if isinstance(at, str) and at != "end":
        return start + word_offset(project, beat, at)
    seconds, _ = beat_words(project, beat)
    return start + (seconds if at == "end" else float(at) * seconds)


def motif_pieces(project: Project, timings: Mapping[str, Any]) -> list[ThemePiece]:
    """The beats' motifs at the timings' beat starts (seconds)."""
    config = project.config
    beats = {b.id: b for _, b in project.beats()}
    out = []
    for i, scene in enumerate(timings["scenes"]):
        for entry in scene["beats"]:
            beat = beats.get(entry["id"])
            if beat is None or beat.motif is None:
                continue
            motif: MotifCue = beat.motif
            t = motif_time(project, beat, float(entry["start"]), motif.at)
            play = resolve(config, motif.theme, motif.variation, motif.gain)
            dip = config.score.motif_dip if motif.dip is None else motif.dip
            out.append(ThemePiece(play, t, t + motif.length, motif.fade_in, max(motif.fade_out, MIN_FADE), i, True, dip))
    return out


def sting_windows(project: Project, timings: Mapping[str, Any]) -> list[tuple[float, float]]:
    """``(start, end)`` seconds of every beat's sting (the timings' ducked sound effects)."""
    from vidgen.sfx import SoundLibrary

    events = [e for scene in timings["scenes"] for e in scene.get("sfx", []) if e.get("duck")]
    if not events:
        return []
    library = SoundLibrary(project.root)
    out = []
    for e in events:
        seconds = len(library.audio(str(e["sound"]), dict(e.get("params") or {}))) / RATE
        start = float(e["time"]) - (seconds if e.get("align") == "end" else 0.0)
        out.append((start, start + seconds))
    return out


def dip_curve(times: np.ndarray, pieces: Sequence[ThemePiece], stings: Sequence[tuple[float, float]], sting_dip: float, curve: str) -> np.ndarray:
    """The dip (dB, 0 or negative) of the scene themes under the motifs and the stings: the
    deepest one at each time, following each one's fades."""
    out = np.zeros(len(times))
    for p in pieces:
        if p.motif and p.dip > 0:
            out = np.minimum(out, -p.dip * envelope(times, p.start, p.end, p.fade_in, p.fade_out, curve))
    if sting_dip > 0:
        for a, b in stings:
            out = np.minimum(out, -sting_dip * envelope(times, a, b + STING_DIP_RAMPS[1], STING_DIP_RAMPS[0], STING_DIP_RAMPS[1], "smooth"))
    return out


# ----- sources ---------------------------------------------------------------------------------------


def score_path(source: str, root: Path) -> Path | None:
    """The score file a theme's notes come from: a project piece, a score bed's file, or a built-in
    bed's score template; ``None`` for an audio file."""
    from vidgen.music import is_bed
    from vidgen.music_pieces import is_score_source, piece_path
    from vidgen.studio.templates import TEMPLATE_DIR

    if is_bed(source):
        path = TEMPLATE_DIR / f"{source}.yaml"
        return path if path.is_file() else None
    if is_score_source(source, root):
        return piece_path(source, root)
    return None


def _uses_template(play: ThemePlay) -> bool:
    """Whether the theme plays from its score (a variation of its notes, or a section of a bed
    made in Python: its template has the sections)."""
    from vidgen.music import BUILTIN_BEDS

    bed = BUILTIN_BEDS.get(play.source)
    return play.changes_score or (play.section is not None and bed is not None and not bed.score)


def variant_score(path: Path, play: ThemePlay) -> MusicScore:
    """The score at ``path`` as ``play`` varies it: another tempo, its pitched tracks transposed,
    only some tracks (a kept track that ducked under a left-out one no longer ducks)."""
    import yaml

    from vidgen.studio.score_file import parse_music_score

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if play.tempo is not None and isinstance(data, dict):
        data = {**data, "tempo": play.tempo}
    score = parse_music_score(data, str(path))
    tracks = list(score.tracks)
    if play.tracks is not None:
        names = [t.name for t in tracks]
        missing = [n for n in play.tracks if n not in names]
        if missing:
            raise VidgenError(f"{path.name} has no track {missing[0]!r}{_did_you_mean(missing[0], names)} (tracks: {', '.join(names)})")
        kept = set(play.tracks)
        tracks = [t for t in tracks if t.name in kept]
        tracks = [replace(t, parts={k: replace(p, duck=None) if p.duck is not None and p.duck.to not in kept | {"beat"} else p
                                    for k, p in t.parts.items()}) for t in tracks]
    if play.transpose:
        tracks = [t if t.instrument.kind == "drum" else replace(t, parts={k: replace(p, transpose=p.transpose + play.transpose) for k, p in t.parts.items()})
                  for t in tracks]
    return replace(score, tracks=tuple(tracks))


def _did_you_mean(name: str, known: Sequence[str]) -> str:
    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.6)
    return f"; did you mean '{close[0]}'?" if close else ""


class ThemeAudio:
    """A theme's samples from its start (``read(a, b)`` → float32 ``(b - a, 2)``): a loop repeats
    seamlessly, a one-shot ends."""

    def __init__(self, data: np.ndarray, offset: int, loop: bool, label: str, kind: str) -> None:
        self.data, self.loop, self.label, self.kind = data, loop, label, kind
        self.offset = offset % len(data) if loop and len(data) else offset

    def read(self, a: int, b: int) -> np.ndarray:
        idx = np.arange(a, b) + self.offset
        if self.loop:
            return self.data[idx % len(self.data)]
        out = np.zeros((b - a, 2), dtype=np.float32)
        inside = idx < len(self.data)
        out[inside] = self.data[idx[inside]]
        return out


def _variant_audio(path: Path, play: ThemePlay, cache_dir: Path | None) -> tuple[np.ndarray, MusicScore]:
    """The variation's render (float32 stereo at the music level), kept in ``cache_dir``."""
    from vidgen.music_pieces import piece_key
    from vidgen.studio import render_music_score

    score = variant_score(path, play)
    key = hashlib.sha256(json.dumps({"piece": piece_key(path), "variation": play.variation(), "version": VARIATION_VERSION},
                                    sort_keys=True).encode("utf-8")).hexdigest()
    cached = None if cache_dir is None else cache_dir / f"theme-{key}.npy"
    if cached is not None and cached.is_file():
        try:
            data = np.load(cached, allow_pickle=False)
            if data.ndim == 2 and data.shape[1] == 2:
                return data, score
        except (OSError, ValueError):
            pass
    data = render_music_score(score)
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        np.save(cached, data, allow_pickle=False)
    return data, score


def theme_source(play: ThemePlay, project: Project) -> Any:
    """What plays for ``play``: its source as a ``music:`` cue plays it (:class:`vidgen.music.Source`,
    looped, from ``section`` / ``start``), or the render of its score with the variation
    (:class:`ThemeAudio`)."""
    from vidgen.music import Source

    cache = project.build_dir / "music"
    if not _uses_template(play):
        cue = MusicCue(source=play.source, section=play.section, start=play.start, loop=True)
        source = Source(cue, project.root, project.config.soundfont, cache)
        source.label = play.label
        return source
    path = score_path(play.source, project.root)
    if path is None:
        raise VidgenError(f"theme '{play.name}': {play.source} is an audio file; only a score (a bed or a project piece) can vary")
    data, score = _variant_audio(path, play, cache)
    offset = play.start
    if play.section is not None:
        section = next((s for s in score.sections if s.name == play.section), None)
        if section is None:
            names = [s.name for s in score.sections]
            raise VidgenError(f"theme '{play.name}': {path.name} has no section '{play.section}'{_did_you_mean(play.section, names)} (sections: {', '.join(names)})")
        offset += score.section_start(section) / RATE
    return ThemeAudio(data, round(offset * RATE), score.loop, play.label, "theme")


# ----- checks ----------------------------------------------------------------------------------------


def _plays(config: VideoConfig) -> list[tuple[str, ThemePlay]]:
    """``(location, play)`` of every theme the scenes and beats name."""
    out = []
    for i, spec in enumerate(config.scenes):
        if isinstance(spec.music, SceneMusic) and spec.music.theme is not None:
            out.append((f"scenes[{i}].music", resolve(config, spec.music.theme, spec.music.variation)))
        for j, beat in enumerate(spec.beats):
            if beat.motif is not None:
                out.append((f"scenes[{i}].beats[{j}].motif", resolve(config, beat.motif.theme, beat.motif.variation)))
    return out


def theme_problems(config: VideoConfig, root: Path | None) -> list[tuple[str, str]]:
    """``(location, message)`` problems of the themes: a name that is neither a theme, a bed nor a
    project piece (did-you-mean), a source that does not exist, a variation of an audio file, a
    track or section its score does not have."""
    from vidgen.music import BUILTIN_BEDS, is_bed
    from vidgen.music_pieces import is_score_source, piece_path, project_pieces
    from vidgen.studio import load_music_score

    if root is None:
        return []
    found: list[tuple[str, str]] = []
    for name, theme in config.score.themes.items():
        if is_bed(theme.source):
            continue
        if is_score_source(theme.source, root):
            try:
                piece_path(theme.source, root)
            except VidgenError as exc:
                found.append((f"score.themes.{name}.source", str(exc)))
        elif not (root / theme.source).is_file():
            found.append((f"score.themes.{name}.source", f"neither a built-in bed, a project piece nor a file: {theme.source}{_did_you_mean(theme.source, [*BUILTIN_BEDS, *project_pieces(root)])}"))
    known = [*config.score.themes, *BUILTIN_BEDS, *project_pieces(root)]
    for where, play in _plays(config):
        if play.name not in config.score.themes and not is_bed(play.name) and play.name not in project_pieces(root):
            found.append((where, f"unknown theme '{play.name}'{_did_you_mean(play.name, known)} (themes: {', '.join(config.score.themes) or 'none'}; or a built-in bed or project piece)"))
            continue
        if not _uses_template(play) and play.section is None:
            continue
        try:
            path = score_path(play.source, root)
        except VidgenError as exc:
            found.append((where, str(exc)))
            continue
        if path is None:
            found.append((where, f"theme '{play.name}' plays the audio file {play.source}: only a score (a built-in bed or a project piece) has sections, a key, a tempo and tracks to vary"))
            continue
        try:
            score = load_music_score(path)
        except VidgenError:
            continue  # the piece's own problems are reported on its source
        tracks, sections = [t.name for t in score.tracks], [s.name for s in score.sections]
        for track in play.tracks or ():
            if track not in tracks:
                found.append((where, f"theme '{play.name}' ({path.name}) has no track '{track}'{_did_you_mean(track, tracks)} (tracks: {', '.join(tracks)})"))
        if play.section is not None and play.section not in sections:
            found.append((where, f"theme '{play.name}' ({path.name}) has no section '{play.section}'{_did_you_mean(play.section, sections)} (sections: {', '.join(sections)})"))
    return found


def check_wanted(config: VideoConfig) -> bool:
    """Whether the mix measures the music under dense dialogue (``score.check``)."""
    check = config.score.check
    return bool(config.music_cues or uses_score(config)) if check is True else bool(check is None and uses_score(config))


def _frame_power(total: int, read: Callable[[int, int], np.ndarray]) -> np.ndarray:
    """The mean K-weighted power of every :data:`CHECK_FRAME` of a signal."""
    from vidgen import loudness

    frames = -(-total // CHECK_FRAME)
    sums = np.zeros(frames)
    m = loudness.MARGIN
    for lo, hi, ext in loudness.blocks(total, read):
        power = loudness.kweighted_power(ext)[m : m + hi - lo]
        idx = np.arange(lo, hi) // CHECK_FRAME
        sums += np.bincount(idx, weights=power, minlength=frames)[:frames]
    counts = np.full(frames, float(CHECK_FRAME))
    counts[-1] = total - (frames - 1) * CHECK_FRAME
    return sums / counts


def _lufs(power: np.ndarray) -> float:
    mean = float(np.mean(power)) if len(power) else 0.0
    return -0.691 + 10 * math.log10(mean) if mean > 0 else -math.inf


def _lu(voice: np.ndarray, music: np.ndarray) -> float | None:
    """How far (LU) the music is under the voice over the same frames (``None``: no music)."""
    gap = _lufs(voice) - _lufs(music)
    return round(gap, 1) if math.isfinite(gap) else None


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.concatenate([[0], mask.astype(int), [0]]))
    return list(zip(np.nonzero(edges == 1)[0].tolist(), np.nonzero(edges == -1)[0].tolist()))


def dense_dialogue_check(total: int, voice: Callable[[int, int], np.ndarray], music: Callable[[int, int], np.ndarray],
                         speech: Sequence[tuple[float, float]], dense_lu: float) -> dict[str, Any]:
    """The music measured against the voices (see the module doc): ``under_dialogue_lu`` (all the
    speech), ``in_pauses_lu`` (the music in pauses of at least :data:`PAUSE_MIN` against the voices'
    level), each ``dense`` run ``{start, end, lu}`` and the ``worst_dense_lu``; ``ok`` when every
    dense run keeps the music at least ``dense_lu`` under the voices."""
    vp, mp = _frame_power(total, voice), _frame_power(total, music)
    frames = len(vp)
    step = CHECK_FRAME / RATE
    talk = np.zeros(frames, dtype=bool)
    for a, b in speech:
        talk[max(0, math.floor(a / step)) : min(frames, math.ceil(b / step))] = True
    pause = np.zeros(frames, dtype=bool)
    on = np.nonzero(talk)[0]
    for a, b in _runs(~talk):
        if on.size and on[0] < a and b <= on[-1] and (b - a) * step >= PAUSE_MIN:
            pause[a:b] = True
    width = max(1, round(DENSE_WINDOW / step))
    share = np.convolve(talk.astype(float), np.ones(width) / width, mode="same")
    # a window filled with speech marks its whole width dense (the speech in it: the gaps between lines are left out)
    dense = np.convolve((share >= DENSE_SHARE).astype(float), np.ones(width), mode="same") > 0
    runs = []
    for a, b in _runs(dense):
        said = np.nonzero(talk[a:b])[0]
        if said.size and (said[-1] + 1 - said[0]) * step >= DENSE_MIN:
            runs.append((a + int(said[0]), a + int(said[-1]) + 1))
    level = _lufs(vp[talk]) if talk.any() else -math.inf
    report: dict[str, Any] = {
        "under_dialogue_lu": _lu(vp[talk], mp[talk]) if talk.any() else None,
        "in_pauses_lu": round(level - _lufs(mp[pause]), 1) if pause.any() and math.isfinite(level - _lufs(mp[pause])) else None,
        "dense": [{"start": round(a * step, 1), "end": round(b * step, 1), "lu": _lu(vp[a:b][talk[a:b]], mp[a:b][talk[a:b]])} for a, b in runs],
        "dense_lu": dense_lu,
    }
    lus = [r["lu"] for r in report["dense"] if r["lu"] is not None]
    report["worst_dense_lu"] = min(lus) if lus else None
    report["ok"] = not lus or min(lus) >= dense_lu
    return report


__all__ = [
    "ThemeAudio",
    "ThemePiece",
    "ThemePlay",
    "check_wanted",
    "dense_dialogue_check",
    "dip_curve",
    "envelope",
    "fade_shape",
    "motif_pieces",
    "resolve",
    "scene_theme",
    "sting_windows",
    "theme_pieces",
    "theme_problems",
    "theme_source",
    "uses_score",
]
