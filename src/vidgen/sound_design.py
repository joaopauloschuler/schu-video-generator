"""Sound design without pictures (DESIGN.md §112): ambience beds per scene or section that
cross-fade at scene changes and start or stop on a beat's word, and the sounds an audio-only
render can work out from the config alone for the scenes that would make them while they render
(``audio.scene_sounds``): a stage's set ambience and rain, the footsteps of its walks, its doors,
knocks, switches, jumps and surprised faces, and a ``video_clip``'s own sound.

Everything here is timed in the audio's seconds from a :class:`SceneSlot` per scene (where it
starts, how long it lasts, where each beat's line starts and ends), so the audio-only render
(:mod:`vidgen.audio_only`) and a video render (:mod:`vidgen.render.pipeline`, scene and beat
``ambience`` only) share it. Nothing here imports manim; the stage's params are read through its
registered scene type (an extension session).

**Beds.** A scene's ``ambience`` (a bed, a list, ``{beds, gain, width}``; none or false: no bed)
is what plays from its start; a beat's ``ambience`` changes start beds (fading in from the
moment) or stop them (fading out from it), at a fraction of the line, a word it says or its end.
At a scene change every bed that does not go on unchanged fades out and the next scene's fade in
over ``audio.ambience_crossfade`` seconds centred on the change; a bed in both scenes at the same
level and width plays on without a dip. The first beds fade in from the start over their own fade
(:data:`vidgen.ambience.BEDS`), the last fade out by the end. Each piece is a timings
``ambience`` entry with its own ``fade_in``, ``fade_out``, ``gain`` (dB) and ``width``, which
:func:`vidgen.mix.plan_ambience` places as it is (ducked under the voices as its bed ducks).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vidgen.ambience import BEDS, set_ambience
from vidgen.config import AmbienceConfig, BeatConfig, SceneConfig
from vidgen.sfx import SfxEvent, repeated
from vidgen.staging import cue_room, repeat_pans, stage_pan

if TYPE_CHECKING:
    from vidgen.project import Project

log = logging.getLogger("vidgen.audio")

#: The shortest fade (s) at a change with ``ambience_crossfade: 0`` (a cut that does not click).
MIN_FADE = 0.05
#: A 16:9 frame's width in Manim units (the shorter side is 8): stage widths and walks are
#: worked out in it (DESIGN.md §112: the audio has no frame).
FRAME_WIDTH = 8.0 * 16.0 / 9.0
#: A character's half width as a share of its height (where it stands off stage).
HALF_WIDTH = 0.18
#: A stage's set fades in over this share of its first beat, at most these seconds (its
#: ``reveal(fraction=0.6, cap=1.0)``); the first beat's actions wait for it.
STAGE_ENTRANCE = (0.6, 1.0)
#: The stage actions whose sounds an audio-only render works out (DESIGN.md §112).
STAGE_SOUND_ACTIONS = frozenset({"walk_to", "run_to", "enter", "exit", "open", "close", "knock", "switch_on", "switch_off",
                                 "jump", "emote", "react", "effect"})


@dataclass(frozen=True)
class BeatSlot:
    """A beat in the audio: its line starts at ``start`` and ends at ``end`` (seconds); a fraction
    of the beat counts over ``body`` seconds (its narration, as the actions' ``at``)."""

    beat: BeatConfig
    start: float
    end: float
    body: float


@dataclass
class SceneSlot:
    """A scene in the audio: ``start``, ``duration`` (seconds) and its beats."""

    spec: SceneConfig
    start: float
    duration: float
    beats: list[BeatSlot] = field(default_factory=list)

    @property
    def end(self) -> float:
        return self.start + self.duration


# ----- beds ------------------------------------------------------------------------------------------


def scene_beds(spec: SceneConfig) -> dict[str, tuple[float, float | None]]:
    """The beds of a scene's ``ambience`` as ``{bed: (gain dB, width)}`` (none: empty)."""
    setting = spec.ambience
    if setting is None or setting is False:
        return {}
    if isinstance(setting, AmbienceConfig):
        return {name: (level, setting.width) for name, level in setting.levels().items()}
    names = [setting] if isinstance(setting, str) else list(setting)
    return {name: (0.0, None) for name in dict.fromkeys(names)}


def designs_ambience(scenes: Sequence[SceneConfig]) -> bool:
    """Whether any scene or beat names an ambience (else nothing here changes the mix)."""
    return any(s.ambience not in (None, False) or any(b.ambience is not None for b in s.beats) for s in scenes)


def word_offset(project: Project, beat: BeatConfig, at: str) -> float:
    """Seconds from a beat's start to the word anchor ``at`` (``"@door"``, ``"@door#2+0.3s"``):
    the word's time in the beat's audio, else estimated (:func:`vidgen.word_anchors.beat_words`),
    moved by the anchor's seconds, within the line."""
    from vidgen.word_anchors import beat_words, find_words, parse_word_anchor

    anchor = parse_word_anchor(at)
    seconds, times = beat_words(project, beat)
    index = find_words(anchor, beat.text.split(), beat.id)
    word = times[index].start if index < len(times) else 0.0
    return min(max(word + anchor.offset, 0.0), seconds)


def change_time(project: Project, slot: BeatSlot, at: float | str) -> float:
    """The audio time of an ambience change at ``at`` of a beat: a fraction of its ``body``, a
    word it says (:func:`word_offset`), or ``end`` (where its line ends)."""
    if isinstance(at, str):
        if at.strip() == "end":
            return slot.end
        return slot.start + word_offset(project, slot.beat, at)
    return slot.start + float(at) * slot.body


@dataclass
class _Piece:
    bed: str
    start: float
    fade_in: float
    gain: float
    width: float | None
    scene: int
    end: float = math.inf
    fade_out: float = 0.0

    def entry(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "bed": self.bed, "start": round(self.start, 6), "end": round(self.end, 6),
            "fade_in": round(self.fade_in, 6), "fade_out": round(self.fade_out, 6), "gain": self.gain,
        }
        if self.width is not None:
            data["width"] = self.width
        return data


def ambience_entries(project: Project, slots: Sequence[SceneSlot], total: float) -> list[list[dict[str, Any]]]:
    """The designed ambience of every scene (see the module doc): per scene, the timings
    ``ambience`` entries of the pieces that start in it (audio seconds)."""
    cross = project.config.audio.ambience_crossfade
    half = cross / 2
    playing: dict[str, _Piece] = {}
    done: list[_Piece] = []

    def close(name: str, end: float, fade: float) -> None:
        piece = playing.pop(name)
        piece.end, piece.fade_out = max(end, piece.start), max(fade, MIN_FADE)
        done.append(piece)

    for i, slot in enumerate(slots):
        wanted = scene_beds(slot.spec)
        for name in list(playing):   # the scene change: what does not go on unchanged fades out
            piece = playing[name]
            if wanted.get(name) != (piece.gain, piece.width):
                close(name, slot.start + half, cross)
        for name, (gain, width) in wanted.items():
            if name not in playing:
                first = i == 0 or slot.start <= 0
                start = 0.0 if first else max(slot.start - half, 0.0)
                playing[name] = _Piece(name, start, BEDS[name].fade_in if first else max(cross, MIN_FADE), gain, width, i)
        for beat in slot.beats:
            for change in beat.beat.ambience_changes:
                t = min(max(change_time(project, beat, change.at), slot.start), slot.end)
                for name in change.stopped(playing):
                    fade = change.fade if change.fade is not None else BEDS[name].fade_out
                    close(name, t + fade, fade)
                for name in change.started():
                    if name in playing:
                        continue
                    fade = change.fade if change.fade is not None else BEDS[name].fade_in
                    playing[name] = _Piece(name, t, fade, change.gain, None, i)
    for name in list(playing):
        close(name, total, BEDS[name].fade_out)
    out: list[list[dict[str, Any]]] = [[] for _ in slots]
    for piece in sorted(done, key=lambda p: (p.start, p.bed)):
        if piece.end > piece.start:
            out[piece.scene].append(piece.entry())
    return out


# ----- what scenes would sound like (audio.scene_sounds) -------------------------------------------------


def _stage_params(spec: SceneConfig) -> Any | None:
    """A stage scene's params validated by its registered type (``None``: no stage)."""
    from vidgen import registry

    entry = registry.find(spec.type)
    if spec.type != "stage" or entry is None:
        return None
    return entry.cls.Params.model_validate(spec.params)


def _foley_on(project: Project, params: Any) -> bool:
    return params.foley if params.foley is not None else project.config.foley


def _set_beds(project: Project, params: Any, slot: SceneSlot) -> list[dict[str, Any]]:
    """The stage's beds as a video's stage plays them (:func:`vidgen.ambience.set_ambience`: its
    ``ambience``, else the video's; rain under ``particles`` rain all along; light changes from
    its ``light`` actions, half-way through each fade), at audio times."""
    end = slot.duration
    rain = [(0.0, end)] if any(getattr(p, "kind", None) == "rain" for p in params.particles) else []
    beds = [("rain", 0.0, end)] if rain else []
    given = params.ambience
    setting: bool | list[str]
    if given is None:
        setting = project.config.ambience
    elif isinstance(given, bool):
        setting = given
    else:
        setting = True if given == "auto" else [given] if isinstance(given, str) else list(given)
    lights: list[tuple[float, str | None]] = [(0.0, params.light if isinstance(params.light, str) else None)]
    for beat in slot.beats:
        for act in beat.beat.actions:
            if act.action == "light":
                names = act.targets()
                at = beat.start - slot.start + act.fraction * beat.body + (act.run_time or 2.0) / 2
                lights.append((at, names[0] if names and not act.options.get("tint") else None))
    iso = params.iso
    room = params.room is not None or (iso is not None and iso.place == "indoor")
    beds += set_ambience(setting, room=room, lights=lights, rain=rain, end=end, crickets=iso is not None)
    return [{"bed": bed, "start": round(slot.start + a, 6), "end": round(slot.start + b, 6)} for bed, a, b in beds if b > a]


class _Walker:
    """Where each character of a plain stage stands as the beats go (x in Manim units across the
    stage; ``None``: off stage, waiting to enter)."""

    def __init__(self, project: Project, params: Any, beats: Sequence[BeatSlot]) -> None:
        from vidgen.cartoon.motion import motion_strength, resolve_motion
        from vidgen.cartoon.stage import mark_x

        self.params = params
        self.width = params.width * FRAME_WIDTH
        self.marks = params.stage_marks()
        entering = {t for b in beats for act in b.beat.actions if act.action == "enter" for t in act.targets()}
        own = {getattr(c, "name", None): getattr(c, "cartoon_motion", None) for c in project.config.characters}
        self.height: dict[str, float] = {}
        self.home: dict[str, float] = {}
        self.x: dict[str, float | None] = {}
        self.strength: dict[str, float] = {}
        for member in params.characters:
            self.height[member.name] = params.size * 8.0 * member.scale
            self.home[member.name] = self.units(mark_x(member.at, self.marks))
            self.x[member.name] = None if member.name in entering else self.home[member.name]
            self.strength[member.name] = motion_strength(resolve_motion(own.get(member.name), params.cartoon_motion, project.config.cartoon_motion))

    def units(self, fraction: float) -> float:
        return (fraction - 0.5) * self.width

    def place(self, at: Any, default: float) -> float:
        """The x (units) of a mark, an x from 0 to 1, or a ``{mark}``; ``default`` when unknown."""
        from vidgen.cartoon.stage import mark_x

        mark = getattr(at, "mark", at)
        try:
            return self.units(mark_x(mark, self.marks)) if mark is not None else default
        except (TypeError, ValueError):
            return default

    def pan(self, x: float) -> float:
        return stage_pan(min(max(x / self.width + 0.5, 0.0), 1.0))


def _walk_events(walker: _Walker, act: Any, name: str, start: float, limit: float) -> list[tuple[float, Any, float]]:
    """The foley of one character's walk (``walk_to``, ``run_to``, ``enter``, ``exit``) from audio
    time ``start``, at most ``limit`` seconds (to the next beat), with its ``cartoon_motion``'s
    wind-up and settle: ``(time, FoleyCue, pan)``."""
    from vidgen.cartoon.acting import RUN_SPEED, RUNNING, STEP_LENGTH, WALK_SPEED, walk_seconds
    from vidgen.cartoon.foley import PlayedAction, foley_cues
    from vidgen.cartoon.motion import walk_motion_seconds, walk_phases

    options = act.options
    height = walker.height.get(name, 3.6)
    edge = walker.width / 2 + HALF_WIDTH * height + 0.25
    here = walker.x.get(name)
    door = options.get("door")
    if act.action == "enter":
        to = walker.place(options.get("to"), walker.home.get(name, 0.0))
        side = options.get("side") or ("left" if to <= 0 else "right")
        source = walker.place(door, to) if door else (-edge if side == "left" else edge)
        walker.x[name] = to
    elif act.action == "exit":
        source = here if here is not None else 0.0
        side = options.get("to") or ("left" if source <= 0 else "right")
        to = walker.place(door, source) if door else (-edge if side == "left" else edge)
        walker.x[name] = None
    else:
        source = here if here is not None else walker.home.get(name, 0.0)
        to = walker.place(options.get("to"), source)
        walker.x[name] = to
    distance = abs(to - source)
    if distance <= 1e-6 and not door:
        return []
    run = act.action == "run_to"
    speed = float(options.get("speed") or (RUN_SPEED if run else WALK_SPEED))
    strength = walker.strength.get(name, 1.0)
    feet = walk_seconds(distance, speed)
    seconds = act.run_time or walk_motion_seconds(feet, strength)
    seconds = max(min(seconds, limit), 0.1) if limit > 0 else seconds
    played = PlayedAction(act.action, start, seconds, heights=distance / height, phases=walk_phases(feet, strength),
                          step_length=STEP_LENGTH * (RUNNING.stride if run else 1.0), through_door=bool(door), opens_door=bool(door))
    pan = round(walker.pan((source + to) / 2), 4)
    return [(cue.time, cue, pan) for cue in foley_cues(played)]


def _door_kinds(params: Any) -> dict[str, str | None]:
    """Each prop's name -> its built-in kind (the room's doors are ``door``)."""
    return {name: getattr(prop, "prop", None) for name, prop in zip(params.prop_names(), params.stage_props())}


def stage_sounds(project: Project, slot: SceneSlot) -> tuple[list[SfxEvent], list[dict[str, Any]]]:
    """A stage scene's sounds without pictures (``audio.scene_sounds``, DESIGN.md §112): its set
    beds and rain (plain timings ``ambience`` entries) and the foley of its walks on a plain stage,
    its doors opening and closing, knocks, switches, jumps, surprised faces and effect symbols (each
    walk panned where it goes), in the scene's room with ``audio.sfx_room``; none with its foley
    off. A platform level's or an iso place's moves, vehicles, thrown props, pours, lightning and
    alarms are not worked out."""
    from vidgen.cartoon.foley import BOING_GAIN, EFFECT_SOUNDS, POP_EXPRESSION, POP_GAIN, PlayedAction, door_cues
    from vidgen.cartoon.motion import JUMP_CROUCH_SECONDS
    from vidgen.scenes.stage import KNOCK_GAIN, SWITCH_CLICK_GAIN

    params = _stage_params(slot.spec)
    if params is None or not _foley_on(project, params):
        return [], []
    beds = _set_beds(project, params, slot)
    plain = params.level is None and params.iso is None
    walker = _Walker(project, params, slot.beats) if plain else None
    kinds = _door_kinds(params)
    room = cue_room(project.config, slot.spec, None)
    cues: list[tuple[float, Any, float, str | None]] = []
    ends = [b.start for b in slot.beats[1:]] + [slot.end]
    for k, (beat, until) in enumerate(zip(slot.beats, ends)):
        # the set fades in over the first beat (STAGE_ENTRANCE of it, at most a second): its actions wait
        wait = min(STAGE_ENTRANCE[0] * beat.body, STAGE_ENTRANCE[1]) if k == 0 else 0.0
        for act in beat.beat.actions:
            if act.action not in STAGE_SOUND_ACTIONS:
                continue
            animates = act.action not in ("knock", "switch_on", "switch_off")   # these are cued as their beat starts
            at = beat.start + max(act.fraction * beat.body, wait if animates else 0.0)
            limit = until - at
            targets = act.targets()
            if act.action in ("walk_to", "run_to", "enter", "exit"):
                if walker is not None:
                    for name in targets:
                        cues += [(t, cue, pan, beat.beat.id) for t, cue, pan in _walk_events(walker, act, name, at, limit)]
            elif act.action in ("open", "close"):
                if any(kinds.get(t) == "door" for t in targets):
                    seconds = act.run_time or 0.6
                    cues += [(c.time, c, 0.0, beat.beat.id) for c in door_cues(PlayedAction(act.action, at, seconds, prop="door"))]
            elif act.action == "knock":
                cues.append((at, _cue(at, "knock", KNOCK_GAIN), 0.0, beat.beat.id))
            elif act.action in ("switch_on", "switch_off"):
                quiet = {"fireplace", "portal", "hologram_display", *(("phone",) if act.action == "switch_on" else ())}
                if any(kinds.get(t) not in quiet for t in targets):
                    cues.append((at, _cue(at, "click", SWITCH_CLICK_GAIN), 0.0, beat.beat.id))
            elif act.action == "jump":   # it takes off after its crouch
                crouch = JUMP_CROUCH_SECONDS * (walker.strength.get(targets[0], 1.0) if walker is not None and targets else 1.0)
                cues.append((at + crouch, _cue(at + crouch, "boing", BOING_GAIN), 0.0, beat.beat.id))
            elif act.action in ("emote", "react"):
                if act.options.get("to", act.options.get("expression")) == POP_EXPRESSION:
                    cues.append((at, _cue(at, "pop", POP_GAIN), 0.0, beat.beat.id))
            elif act.action == "effect":
                effect = act.options.get("to")
                if effect in EFFECT_SOUNDS and act.options.get("sound", True):
                    sound, gain, given = EFFECT_SOUNDS[effect]
                    cues.append((at, _cue(at, sound, gain, given), 0.0, beat.beat.id))
    events = [SfxEvent(round(max(t, 0.0), 6), cue.sound, cue.gain, pan, cue.align, dict(cue.params), beat_id, False, room)
              for t, cue, pan, beat_id in sorted(cues, key=lambda c: c[0])]
    return events, beds


def _cue(time: float, sound: str, gain: float, params: dict[str, float] | None = None) -> Any:
    from vidgen.cartoon.foley import FoleyCue

    return FoleyCue(time, sound, gain, params or {})


def clip_sound(project: Project, slot: SceneSlot, folder: Path) -> Path | None:
    """A ``video_clip`` scene's own sound as it would play (``audio.scene_sounds``): its trim,
    speed (fitted to the scene with ``fit_duration``), loop and volume (default 0.25 under
    narration, 1 in a silent scene), faded out over the scene's last half second, written to
    ``folder/<scene>.wav``; ``None`` when muted, silent or the file has no sound."""
    from vidgen.clips import ClipTiming, clip_audio, fit_speed, probe_clip
    from vidgen.errors import VidgenError
    from vidgen.scenes.video_clip import UNDER_NARRATION

    params = slot.spec.params
    if slot.spec.type != "video_clip" or params.get("mute") or not params.get("path"):
        return None
    volume = params.get("volume")
    volume = float(volume) if volume is not None else UNDER_NARRATION if slot.spec.beats else 1.0
    path = project.root / str(params["path"])
    try:
        info = probe_clip(path)
    except VidgenError as exc:
        log.warning("scene '%s': %s; its sound is left out", slot.spec.id, exc)
        return None
    if volume <= 0 or not info.audio:
        return None
    start, end = params.get("trim") or (0.0, info.duration)
    end = min(float(end), info.duration)
    fit = params.get("fit_range") or (0.5, 2.0)
    speed = fit_speed(end - float(start), slot.duration, *fit) if params.get("fit_duration") else float(params.get("speed", 1.0))
    out = folder / f"{slot.spec.id}.wav"
    clip_audio(path, out, ClipTiming(float(start), end, speed, bool(params.get("loop"))), length=slot.duration, volume=volume, fade=0.5)
    return out


def cue_events(project: Project, spec: SceneConfig, sound: str, at: float, *, gain: float, pan: Any, align: str,
               params: dict[str, Any], repeat: int, every: float, room: bool | str | None, beat: str | None = None) -> list[SfxEvent]:
    """The events of one cue (a scene's ``sfx`` entry or an ``sfx`` action) at audio time ``at``:
    ``repeat`` times ``every`` seconds (:func:`vidgen.sfx.repeated`), each at its pan
    (:func:`vidgen.staging.repeat_pans`: a ``{from, to}`` move steps across), in the room
    ``room`` asks for (:func:`vidgen.staging.cue_room`)."""
    where = cue_room(project.config, spec, room)
    plays = zip(repeated(sound, at, repeat, every, params), repeat_pans(pan, repeat))
    return [SfxEvent(t, sound, gain, p, align, given, beat, False, where) for (t, given), p in plays]


__all__ = [
    "BeatSlot",
    "SceneSlot",
    "ambience_entries",
    "change_time",
    "clip_sound",
    "cue_events",
    "designs_ambience",
    "scene_beds",
    "stage_sounds",
    "word_offset",
]
