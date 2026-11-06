"""Audio-only renders (DESIGN.md §111): ``vidgen render --audio-only``, or ``audio_only: true``,
writes the project's sound to ``<output>.wav`` (:meth:`Project.audio_path`) and renders no scene.

:func:`plan_audio` times every beat without pictures. With ``pacing.timing: speech`` (the
default) a line lasts as long as its MP3 (else the word-count estimate) and is followed by a gap:
``pacing.line`` (default ``narration.pad``) between two lines of one voice, ``speaker`` where the
voice changes, ``scene`` between scenes, ``chapter`` before a scene that starts a chapter; a
beat's own ``pause`` replaces the gap after it. A sting at a line's start sounds
``sting_before`` ahead of the speech, one at its end gets its own length plus ``sting_after``
before the next line; lines that overlap or interrupt (§69.34) join as in a video. No gap is
added next to a silent scene, which lasts ``pacing.silent`` or its ``duration``; ``lead_in`` and
``tail`` of silence frame the whole. With ``timing: video`` every beat sits where
:class:`~vidgen.videoplan.VideoPlan` puts it: the MP4's soundtrack without the pictures. Both are
deterministic.

The sound effects are the ones the config fixes: a scene's ``sfx:`` list, ``sfx`` beat actions,
beats' stings, voice sounds the TTS cannot say, a chapter card's whoosh with ``sfx.auto``. What
only a scene's code makes while it renders (stage foley and ambience, automatic animation
sounds, a clip's own sound) is left out and named in :attr:`AudioPlan.left_out`.

:func:`render_audio` writes the voice track (each beat's MP3 at its start, dipped or cut where a
later line joins it; 10 s blocks, so a long audiobook never sits in memory whole), the effects
track (:func:`vidgen.sfx.write_track`) and the mix (:func:`vidgen.mix.mix_audio`: music beds
ducked under the voices, loudness normalisation, the true-peak limiter), then copies the mix to
the deliverable and writes ``build/<render>/audio/timings.json``.

``audio_output`` (§111.1-111.3) chooses the deliverable: the mix is encoded
(:mod:`vidgen.audio_encode`) unless it is wanted as it is; a loudness preset sets the mix's
targets (:func:`vidgen.audio_check.mix_targets`) and the file is measured against it after the
encode (:func:`vidgen.audio_check.check`); the transcripts are written from the timings
(:mod:`vidgen.transcripts`).
"""

from __future__ import annotations

import logging
import shutil
import wave
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from vidgen import __version__, audio_encode, chapter_export, mix, musicfit, sfx
from vidgen.audio_check import PresetResult, check, measure_file, mix_targets, mono_check, project_preset
from vidgen.chapters import chapter_marks
from vidgen.config import BeatConfig, PacingConfig, SceneConfig
from vidgen.fileio import remove_file, replace_file
from vidgen.overlap import BeatWindow, VoiceShape, beat_lines, beat_windows, shape_voice
from vidgen.project import Project
from vidgen.sfx import RATE, STING_SOUNDS, SfxEvent, SoundLibrary, decode_audio, stereo
from vidgen.staging import VoiceStaging, beat_staging, params_stage_pan, stage_voice, uses_staging
from vidgen.transcripts import write_transcripts
from vidgen.videoplan import VideoPlan, beat_seconds
from vidgen.voicesounds import SOUND_GAIN_DB, VOICE_SOUNDS, beat_sound_spans

log = logging.getLogger("vidgen.audio")

#: Samples per block of the voice track written at a time (10 s).
BLOCK = RATE * 10


@dataclass(frozen=True)
class PlacedBeat:
    """A beat in the audio: its voice starts at ``start`` and is heard until ``end`` (seconds
    from the audio's start), shaped by ``shape`` where a later line joins it, placed in stereo
    and in a room by ``staging`` (DESIGN.md §111.4)."""

    id: str
    start: float
    end: float
    text: str
    shape: VoiceShape = VoiceShape()
    staging: VoiceStaging = VoiceStaging()


@dataclass
class AudioScene:
    """A scene in the audio: ``start`` and ``duration`` (seconds), its beats and sound effects
    (audio times) and the seconds it shares with the scene before (``overlap``: a video's
    crossfade, ``timing: video`` only)."""

    spec: SceneConfig
    start: float
    duration: float
    beats: list[PlacedBeat] = field(default_factory=list)
    events: list[SfxEvent] = field(default_factory=list)
    overlap: float = 0.0


@dataclass
class AudioPlan:
    """The timeline of an audio-only render: ``timing`` (``speech`` / ``video``), the scenes,
    the length (seconds) and what the config's sounds leave out (``left_out``, for a warning)."""

    timing: str
    scenes: list[AudioScene]
    duration: float
    left_out: list[str] = field(default_factory=list)

    @property
    def events(self) -> list[SfxEvent]:
        """Every sound effect, in time order."""
        return sorted((e for s in self.scenes for e in s.events), key=lambda e: e.time)

    @property
    def beats(self) -> list[PlacedBeat]:
        """Every beat, in order."""
        return [b for s in self.scenes for b in s.beats]


@dataclass
class AudioRenderResult:
    """What :func:`render_audio` wrote: the sound ``output`` (``audio_output.format``), the
    ``timings_file`` and its content ``timings`` (with the ``mix`` report), the length in
    seconds, the ``timing`` used, what was ``left_out``, the ``transcripts`` (kind -> file) and,
    with a loudness preset, the file's ``check``."""

    output: Path
    timings_file: Path
    duration: float
    timings: dict[str, Any]
    timing: str
    left_out: list[str] = field(default_factory=list)
    transcripts: dict[str, Path] = field(default_factory=dict)
    check: PresetResult | None = None


# ----- sound effects --------------------------------------------------------------------------------


def _scene_events(project: Project, spec: SceneConfig, start: float) -> list[SfxEvent]:
    """A scene's own sounds at audio times: the entrance sound of its type (``sfx.auto``) and its
    ``sfx:`` list."""
    from vidgen import registry

    events = []
    entry = registry.find(spec.type)
    entrance = getattr(entry.cls, "entrance_sfx", None) if entry is not None else None
    if entrance is not None and project.config.sfx.auto:
        events.append(SfxEvent(round(start, 6), entrance[0], entrance[1]))
    for cue in spec.sfx:
        params = cue.params.model_dump(exclude_none=True)
        events.append(SfxEvent(round(start + cue.at, 6), cue.sound, cue.gain, cue.pan, cue.align, params))
    return events


def _action_events(beat: BeatConfig, start: float, body: float, fps: int | None) -> list[SfxEvent]:
    """The beat's ``sfx`` actions at audio times: ``at`` of its narration (``body`` seconds), in
    whole frames at ``fps`` as the action runner cues them (``None``: exact)."""
    events = []
    for act in beat.actions:
        if act.action != "sfx":
            continue
        options, targets = act.options, act.targets()
        sound = options.get("sound") or (targets[0] if len(targets) == 1 else None)
        if not sound:
            continue
        offset = act.fraction * body
        if fps:
            offset = round(offset * fps) / fps
        params = {k: v for k, v in dict(options.get("params") or {}).items() if v is not None}
        gain, pan = float(options.get("gain", 0.0)), float(options.get("pan", 0.0))
        events.append(SfxEvent(round(start + offset, 6), str(sound), gain, pan, str(options.get("align", "start")), params, beat.id))
    return events


def _beat_events(project: Project, beat: BeatConfig, start: float, window: BeatWindow, seconds: float, sting_at: float, fps: int | None) -> list[SfxEvent]:
    """A beat's sounds at audio times: its sting (at ``sting_at``, ducked), the voice sounds the
    TTS cannot say (in the silence around the line, as a scene plays them) and its ``sfx``
    actions."""
    events = []
    if beat.sting is not None:
        events.append(SfxEvent(round(sting_at, 6), STING_SOUNDS[beat.sting.kind], beat.sting.gain, 0.0, "start", {}, beat.id, True))
    cut = window.shape.cut
    for span in beat_sound_spans(project, beat, seconds):
        if span.generated and (cut is None or span.start < cut):
            sound = VOICE_SOUNDS[span.kind].sfx or ""
            events.append(SfxEvent(round(max(start + span.start, 0.0), 6), sound, SOUND_GAIN_DB, 0.0, "start", {}, beat.id))
    return events + _action_events(beat, start, window.body, fps)


def _left_out(project: Project) -> list[str]:
    """What an audio-only render of ``project`` cannot play (made by scene code while it renders)."""
    types = {s.type for s in project.config.scenes}
    out = []
    if "stage" in types and (project.config.foley or project.config.ambience):
        out.append("the foley and ambience of stage scenes")
    if "video_clip" in types:
        out.append("the sound of video_clip scenes")
    if project.config.sfx.auto:
        out.append("the automatic sounds of animations (sfx: {auto: true}; a chapter card's whoosh is kept)")
    return out


# ----- timing ---------------------------------------------------------------------------------------


def _staging(project: Project, spec: SceneConfig, beat: BeatConfig) -> VoiceStaging:
    """Where ``beat`` sounds (a stage's characters at their ``characters:`` places with
    ``audio.follow_stage``)."""
    return beat_staging(project.config, spec, beat, params_stage_pan(project.config, spec, beat))


def _video_timeline(project: Project, fps: int) -> tuple[list[AudioScene], float]:
    """The scenes where the video puts them (:class:`VideoPlan` at ``fps``)."""
    plan = VideoPlan(project, fps)
    pad = project.config.narration.pad
    scenes = []
    for spec, slot in zip(project.config.scenes, plan.scenes):
        scene = AudioScene(spec, slot.start, slot.duration, overlap=slot.overlap_in)
        scene.events = _scene_events(project, spec, slot.start)
        if spec.beats:
            seconds = [beat_seconds(project, b.id, b.text) for b in spec.beats]
            windows = beat_windows(beat_lines(project, spec.beats, lambda b: beat_seconds(project, b.id, b.text)), pad, fps)
            for beat, timed, window, d in zip(spec.beats, slot.beats, windows, seconds):
                start = slot.start + timed.start
                scene.beats.append(PlacedBeat(beat.id, start, slot.start + timed.end, beat.text, window.shape, _staging(project, spec, beat)))
                ends = beat.sting is not None and beat.sting.placed_at == "end"
                scene.events += _beat_events(project, beat, start, window, d, start + (window.heard if ends else 0.0), fps)
        scenes.append(scene)
    return scenes, plan.duration


def _starts_with_sting(beat: BeatConfig) -> bool:
    return beat.sting is not None and beat.sting.placed_at == "start"


def _ends_with_sting(beat: BeatConfig) -> bool:
    return beat.sting is not None and beat.sting.placed_at == "end"


class _SpeechTimer:
    """The speech timing of one project (see the module doc)."""

    def __init__(self, project: Project, pacing: PacingConfig) -> None:
        self.project = project
        self.pacing = pacing
        self.line_gap = project.config.narration.pad if pacing.line is None else pacing.line
        self.voices = project.voice_names()
        self.chapters = {m.scene_index for m in chapter_marks(project.config.scenes)}
        self.library = SoundLibrary(project.root)
        self._sting_seconds: dict[str, float] = {}

    def sting_seconds(self, kind: str) -> float:
        """The length of a sting's sound (seconds)."""
        if kind not in self._sting_seconds:
            self._sting_seconds[kind] = len(self.library.audio(STING_SOUNDS[kind], {})) / RATE
        return self._sting_seconds[kind]

    def scene_gap(self, i: int) -> float:
        """The gap after scene ``i``'s last line: none before a silent scene, the tail after the
        last scene."""
        specs = self.project.config.scenes
        if i + 1 == len(specs):
            return self.pacing.tail
        nxt = specs[i + 1]
        if nxt.silent:
            return 0.0
        gap = self.pacing.chapter if i + 1 in self.chapters else self.pacing.scene
        last, first = specs[i].beats[-1], nxt.beats[0]
        if self.voices.get(last.id) != self.voices.get(first.id):
            gap = max(gap, self.pacing.speaker)
        return max(gap, self.pacing.sting_before) if _starts_with_sting(first) else gap

    def gaps(self, i: int) -> list[float]:
        """The silence after each line of narrated scene ``i``."""
        pacing, beats = self.pacing, self.project.config.scenes[i].beats
        out = []
        for k, beat in enumerate(beats):
            follower = beats[k + 1] if k + 1 < len(beats) else None
            if follower is None:
                gap = self.scene_gap(i) if beat.pause is None else beat.pause
                if i + 1 == len(self.project.config.scenes):
                    gap = max(gap, pacing.tail)
            else:
                speaker_changes = self.voices.get(follower.id) != self.voices.get(beat.id)
                gap = beat.pause if beat.pause is not None else pacing.speaker if speaker_changes else self.line_gap
                if _starts_with_sting(follower):
                    gap = max(gap, pacing.sting_before)
            if _ends_with_sting(beat):
                assert beat.sting is not None
                gap = max(gap, self.sting_seconds(beat.sting.kind) + pacing.sting_after)
            out.append(gap)
        return out

    def scene(self, i: int, start: float, lead: float = 0.0) -> AudioScene:
        """Scene ``i`` starting at ``start`` (seconds), its first line ``lead`` seconds later."""
        project, spec = self.project, self.project.config.scenes[i]
        scene = AudioScene(spec, start, 0.0, events=_scene_events(project, spec, start))
        if spec.silent:
            scene.duration = (spec.duration or 0.0) if self.pacing.silent is None else self.pacing.silent
            if i + 1 == len(project.config.scenes):
                scene.duration += self.pacing.tail
            return scene
        seconds = [beat_seconds(project, b.id, b.text) for b in spec.beats]
        lines = beat_lines(project, spec.beats, lambda b: beat_seconds(project, b.id, b.text))
        windows = beat_windows([replace(line, pause=gap) for line, gap in zip(lines, self.gaps(i))], self.line_gap)
        clock = start + lead
        for beat, window, d in zip(spec.beats, windows, seconds):
            scene.beats.append(PlacedBeat(beat.id, clock, clock + window.heard, beat.text, window.shape, _staging(project, spec, beat)))
            sting_at = clock + window.heard if _ends_with_sting(beat) else clock - self.pacing.sting_before
            scene.events += _beat_events(project, beat, clock, window, d, sting_at, None)
            clock += window.window
        scene.duration = clock - start
        return scene

    def timeline(self) -> tuple[list[AudioScene], float]:
        """Every scene, the first starting at 0 with the lead-in before its first line (long
        enough for a sting before that line; a silent first scene is the lead-in itself)."""
        specs = self.project.config.scenes
        lead = 0.0
        if specs[0].beats:
            lead = max(self.pacing.lead_in, self.pacing.sting_before) if _starts_with_sting(specs[0].beats[0]) else self.pacing.lead_in
        clock = 0.0
        scenes = []
        for i in range(len(specs)):
            scenes.append(self.scene(i, clock, lead if i == 0 else 0.0))
            clock += scenes[-1].duration
        return scenes, clock


def effective_pacing(project: Project) -> PacingConfig:
    """``pacing:`` with, under the ``audiobook`` loudness preset, its room-tone head and tail
    (:data:`~vidgen.audio_check.AUDIOBOOK_PACING`) where ``pacing:`` does not set them."""
    from vidgen.audio_check import AUDIOBOOK_PACING

    pacing = project.config.pacing
    if project.config.audio_output.loudness != "audiobook":
        return pacing
    unset = {k: v for k, v in AUDIOBOOK_PACING.items() if k not in pacing.model_fields_set}
    return pacing.model_copy(update=unset) if unset else pacing


def plan_audio(project: Project, preview: bool = False) -> AudioPlan:
    """The timeline of ``project``'s audio-only render (``pacing.timing``; ``video`` at the fps of
    the final format, or the preview's with ``preview``). Needs the project's scene types
    registered (an extension session) for the video timing and the entrance sounds."""
    pacing = effective_pacing(project)
    if pacing.timing == "video":
        scenes, duration = _video_timeline(project, project.render_format(preview).fps)
    else:
        scenes, duration = _SpeechTimer(project, pacing).timeline()
    return AudioPlan(pacing.timing, scenes, duration, _left_out(project))


# ----- writing --------------------------------------------------------------------------------------


def _voice_samples(project: Project, beat: PlacedBeat, limit: int) -> np.ndarray:
    """A beat's voice as ``(n, 2)`` float32 at :data:`~vidgen.sfx.RATE`, as its shape plays it
    and its staging places it (longer by a room's tail, faded out by ``limit`` samples: the end
    of the audio)."""
    samples = stereo(decode_audio(project.audio_dir / f"{beat.id}.mp3"))
    samples = samples if beat.shape.plain else shape_voice(samples, RATE, beat.shape)
    return samples if beat.staging.plain else stage_voice(samples, beat.staging, limit)


def write_voice_track(path: Path, project: Project, beats: Sequence[PlacedBeat], samples: int) -> None:
    """Write ``path``: a 48 kHz stereo 16-bit WAV of ``samples`` samples with each beat's MP3 (a
    beat without one is silent) from its start, summed; written in :data:`BLOCK` blocks, each
    beat decoded when the first block it sounds in is written."""
    pending = sorted(((round(b.start * RATE), k, b) for k, b in enumerate(beats) if (project.audio_dir / f"{b.id}.mp3").is_file()))
    active: list[tuple[int, np.ndarray]] = []
    next_beat = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for lo in range(0, samples, BLOCK):
            hi = min(lo + BLOCK, samples)
            while next_beat < len(pending) and pending[next_beat][0] < hi:
                start, _, beat = pending[next_beat]
                active.append((start, _voice_samples(project, beat, samples - start)))
                next_beat += 1
            buf = np.zeros((hi - lo, 2), dtype=np.float32)
            for start, data in active:
                a, b = max(start, lo), min(start + len(data), hi)
                if a < b:
                    buf[a - lo : b - lo] += data[a - start : b - start]
            active = [(start, data) for start, data in active if start + len(data) > hi]
            out.writeframes(np.clip(np.round(buf * 32767), -32768, 32767).astype("<i2").tobytes())


def audio_timings(project: Project, plan: AudioPlan, preview: bool) -> dict[str, Any]:
    """The timings of the audio (``timings.json``): the shape of a video render's combined
    timings (scenes with their beats and sound effects at audio times, chapters) without a
    ``format``, plus ``audio_only: {timing, left_out}``."""
    scenes = []
    for scene in plan.scenes:
        entry: dict[str, Any] = {
            "id": scene.spec.id,
            "type": scene.spec.type,
            "start": round(scene.start, 6),
            "duration": round(scene.duration, 6),
            "beats": [{"id": b.id, "start": round(b.start, 6), "end": round(b.end, 6), "text": b.text} for b in scene.beats],
        }
        if scene.events:
            entry["sfx"] = [e.to_json() for e in sorted(scene.events, key=lambda e: e.time)]
        if scene.overlap:
            entry["transition"] = {"overlap": round(scene.overlap, 6)}
        scenes.append(entry)
    chapters = chapter_export.joined_chapters(project.config, scenes, plan.duration)
    return {
        "title": project.config.title,
        "variant": project.variant,
        "language": project.config.language,
        "preview": preview,
        "audio": True,
        "audio_only": {"timing": plan.timing, "left_out": plan.left_out},
        "duration": round(plan.duration, 6),
        "vidgen": __version__,
        "scenes": scenes,
        "chapters": [chapter_export.chapter_json(c) for c in chapters],
    }


def render_audio(project: Project, preview: bool = False) -> AudioRenderResult:
    """Write ``project``'s sound without rendering a scene (see the module doc): the scenes are
    checked as for a render, missing or stale narration is warned about (those beats are timed
    from their text and stay silent), and what the plan leaves out is logged. ``preview`` only
    names the files (``_preview``) and, with ``timing: video``, times it at the preview's fps.
    ``pre_render`` / ``post_render`` hooks are not dispatched (no video is made)."""
    from vidgen import extensions
    from vidgen.render.pipeline import _check_scenes, warn_audio
    from vidgen.render.worker import write_json

    with extensions.project_session(project):
        _check_scenes(project)
        warn_audio(project)
        plan = plan_audio(project, preview)
        if plan.left_out:
            log.warning("an audio-only render leaves out %s (scene code makes them while it renders)", "; ".join(plan.left_out))
        folder = project.render_dir(preview) / "audio"
        total = round(plan.duration * RATE)
        voice = folder / "voice.wav"
        write_voice_track(voice, project, plan.beats, total)
        timings = audio_timings(project, plan, preview)
        track = folder / "sfx.wav"
        remove_file(track)
        events = plan.events
        if events:
            ducking = mix.sting_ducking(project, timings, total) if any(e.duck for e in events) else None
            library = SoundLibrary(project.root)
            stings = musicfit.composed_stings(project, timings, events, library)
            sfx.write_track(track, events, total, library, project.config.sfx.gain, ducking, stings)
        mixed = folder / "mix.wav"
        targets = mix_targets(project)
        report = mix.mix_audio(project, timings, [voice], track if track.is_file() else None, mixed, always_write=True, targets=targets)
        timings["mix"] = report.to_json()
        output = write_output(project, mixed, preview)
        transcripts = write_transcripts(project, timings, preview, project.config.audio_output.transcript_kinds)
        checked = None
        preset = project_preset(project)
        staged = uses_staging(project.config) and project.config.audio_output.channels == "stereo"
        measured = measure_file(output) if preset is not None or staged else None
        if staged:
            assert measured is not None
            mono = mono_check(measured)
            timings["stereo"] = mono.to_json()
            values = "; ".join(f"{i.name} {i.value} ({i.target}){'' if i.status == 'pass' else ' ' + i.status.upper()}" for i in mono.items)
            if mono.ok:
                log.info("%s folds to mono well: %s", output.name, values)
            else:
                log.warning("%s may not fold to mono well: %s (vidgen audio check; a music_width over 1 often does it)", output.name, values)
        if preset is not None:
            assert measured is not None
            checked = check(measured, preset)
            timings["audio_output"] = {"file": output.name, "check": checked.to_json()}
            if checked.ok:
                log.info("%s meets the %s preset", output.name, preset.name)
            else:
                misses = "; ".join(f"{i.name} {i.value} (wanted {i.target})" for i in checked.failures)
                log.warning("%s misses the %s preset: %s (vidgen audio check)", output.name, preset.name, misses)
        timings_file = folder / "timings.json"
        write_json(timings_file, timings)
    return AudioRenderResult(output, timings_file, plan.duration, timings, plan.timing, plan.left_out, transcripts, checked)


def write_output(project: Project, mixed: Path, preview: bool) -> Path:
    """The deliverable :meth:`Project.audio_path` from the mix: copied when ``audio_output`` asks
    for the mix as it is (48 kHz stereo 24-bit WAV, no preset), else encoded
    (:func:`vidgen.audio_encode.encode`, tagged with the ``metadata``)."""
    out = project.config.audio_output
    output = project.audio_path(preview)
    output.parent.mkdir(parents=True, exist_ok=True)
    if out.plain:
        partial = output.with_name(output.name + ".part")
        shutil.copyfile(mixed, partial)
        replace_file(partial, output)
    else:
        audio_encode.encode(mixed, output, out, chapter_export.video_tags(project.config))
    return output
