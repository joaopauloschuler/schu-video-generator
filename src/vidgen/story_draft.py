"""``vidgen story draft``: a story cartoon project drafted from a story in prose (DESIGN.md §105.5).
Deterministic, no AI: the tool never calls a model; an author or an agent refines the draft.

:func:`draft_story` reads the story (:mod:`vidgen.story_text`) and builds the ``video.yaml``
mapping: a title card, one ``stage`` scene per story scene on a ready-made place
(:mod:`vidgen.story_places`: an iso place, or with ``style="flat"`` the flat stage's ready-made
set) with its light (time cues; a later cue fades with ``time_of_day``), weather and
``fill_light`` at night, the scene's characters at the place's spots (an ``enter`` where the
story brings one in), one beat per narration group or line of dialogue (the speaker's voice and
emotion; a close-up on an emotional line, a two-shot on a long one; walks and runs on movement
verbs), an end card; a cast with generated looks (:func:`vidgen.screenplay._generated_looks`) and
distinct Kokoro voices (:func:`vidgen.screenplay.assign_voices`; told in the first person, the
narrator speaks with the protagonist's voice), a music bed from the mood words, captions in the
speakers' colours and ``auto_direct``. :func:`report_markdown` writes ``story_draft.md``: every
decision, the confidence of each attribution and a TODO checklist.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from vidgen.story_places import (
    INDOOR_SKY, OUTDOOR_SKIES, PLACES, NamedObject, choose_place, light_cues, music_of, objects_named, weather_of,
)
from vidgen.story_text import Line, Story, StoryScene, slug

#: Ways to draw the scenes.
STYLES: tuple[str, ...] = ("iso", "flat")
#: The narrator of a story told in the third person (``vidgen screenplay``'s).
NARRATOR_VOICE = "bf_emma"
#: Colours of the speakers' captions and name tags, in turn.
VOICE_COLORS: tuple[str, ...] = ("primary", "secondary", "accent", "highlight", "tertiary")
#: Where characters stand on a flat ready-made set, in turn, and where they walk to.
FLAT_STANDS: tuple[str, ...] = ("stand_left", "stand_right", "centre", "far_left")
FLAT_GOALS: tuple[str, ...] = ("centre", "stand_right", "stand_left", "far_right", "far_left")
#: Seconds of the title card, the end card and a ``time_of_day`` fade.
TITLE_SECONDS = 2.5
END_SECONDS = 3.0
FADE_SECONDS = 6.0
#: ``fill_light`` at night outdoors / indoors (faces read in the dark).
FILL_NIGHT = 0.4
FILL_NIGHT_INDOOR = 0.45
#: Below this confidence an attribution gets a TODO.
DOUBTFUL = 0.6
#: A line of more words than this needs a shot (a tagged speaker may say 12 words in a wide view).
WIDE_WORDS = 12
#: Emotions that make a line worth a close-up, and the expression shown with them.
EMOTION_EXPRESSIONS: dict[str, str | None] = {
    "happy": "happy", "excited": "happy", "sad": "sad", "angry": "angry", "worried": "worried", "scared": "frightened",
    "surprised": "surprised", "shout": None, "whisper": None,
}
#: Latest ``at`` of an action the draft adds.
LATEST_AT = 0.8
#: The title card's look by the story's mood (DESIGN.md §105.8): dark with neon letters for a
#: night story or a mystery, deep and soft for a bedtime story, warm for a cosy one, quiet for a
#: sad one; otherwise the card's own (the theme's colour behind a burst of rays).
CARD_LOOKS: dict[str, dict[str, str]] = {
    "night": {"style": "frame", "color": "#141A33", "text_color": "#7CF4FF", "outline_color": "#FF4FA3"},
    "bedtime": {"style": "frame", "color": "#2E2A4F", "text_color": "#FFE4A3", "outline_color": "#1B1830"},
    "cosy": {"style": "burst", "color": "#E3924B"},
    "quiet": {"style": "plain", "color": "#5B7083"},
}
#: A modest ambient life for the outdoor places, by day and at night (DESIGN.md §105.7, §105.8):
#: a few passers-by and birds by day, fireflies on a green place at night.
DRAFT_AMBIENT: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "village": ({"walkers": 2, "birds": 2, "cat": True}, {"cat": True, "fireflies": 6}),
    "city": ({"walkers": 3, "birds": 2}, {"walkers": 2}),
    "forest": ({"birds": 3, "butterflies": 2}, {"fireflies": 8}),
    "harbour": ({"walkers": 2, "birds": 3}, {"walkers": 1}),
    "castle": ({"walkers": 1, "birds": 2}, {"fireflies": 4}),
    "winter": ({"walkers": 1, "birds": 2}, {}),
}
#: Words of a cosy story (with a fire, tea and blankets): two or more make its card warm.
COSY_WORDS: tuple[str, ...] = ("cosy", "cozy", "warm", "fireplace", "fire", "tea", "cocoa", "blanket", "snug", "kitchen", "soup", "candle",
                               "candles", "baking", "hearth", "quilt")


def card_mood(lights: Sequence[str], music: str, text: str) -> str | None:
    """The mood of the story's title card (a key of :data:`CARD_LOOKS`; ``None``: the card's own
    look): ``night`` when the story opens at night or most of its scenes are at night, or its
    music is a mystery's or a neon city's; ``bedtime`` for a lullaby; ``cosy`` with two or more
    :data:`COSY_WORDS`; ``quiet`` for a sad story."""
    nights = sum(1 for light in lights if light == "night")
    if (lights and lights[0] == "night") or nights * 2 > len(lights) or music in ("enigma", "neon"):
        return "bedtime" if music == "lullaby" else "night"
    if music == "lullaby":
        return "bedtime"
    words = {w.strip(".,;:!?\"'“”‘’()").lower() for w in text.split()}
    if sum(1 for w in COSY_WORDS if w in words) >= 2:
        return "cosy"
    return "quiet" if music == "calm" else None


@dataclass
class DraftOptions:
    """How to draft: ``style`` (``iso`` / ``flat``), ``fmt`` (``16:9`` / ``9:16``), the
    narrator's Kokoro voice (``None``: :data:`NARRATOR_VOICE`, or the protagonist's in the first
    person), the title when the story has none, the seed of the random looks."""

    style: str = "iso"
    fmt: str = "16:9"
    narrator: str | None = None
    default_title: str = "Untitled"
    seed: int = 0


@dataclass
class SceneNotes:
    """What was decided for a scene, for the report."""

    id: str
    source_line: int
    reason: str
    place: str
    place_reason: str
    light: str
    light_reason: str
    changes: list[str] = field(default_factory=list)
    weather: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    off_stage: list[str] = field(default_factory=list)
    todos: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)


@dataclass
class Attribution:
    """A line of dialogue as attributed: scene, beat number (from 1), speaker (``None``: the
    narrator reads it), confidence, how, and its first words."""

    scene: str
    beat: int
    speaker: str | None
    confidence: float
    method: str
    text: str


@dataclass
class StoryDraft:
    """The drafted project: the ``video.yaml`` mapping, the comments of its scenes and beats, the
    report's parts."""

    config: dict[str, Any]
    story: Story
    options: DraftOptions
    scene_comments: list[list[str]] = field(default_factory=list)
    beat_comments: list[list[list[str]]] = field(default_factory=list)
    scenes: list[SceneNotes] = field(default_factory=list)
    attributions: list[Attribution] = field(default_factory=list)
    cast: list[dict[str, Any]] = field(default_factory=list)
    music: tuple[str, dict[str, int]] = ("cartoon", {})
    notes: list[str] = field(default_factory=list)
    #: objects the story names, added to each place (:func:`vidgen.story_places.objects_named`)
    added: dict[str, list[NamedObject]] = field(default_factory=dict)

    @property
    def todo_count(self) -> int:
        """``# TODO:`` comments in the config."""
        texts = [*(t for s in self.scene_comments for t in s), *(t for s in self.beat_comments for b in s for t in b)]
        return sum(1 for t in texts if t.startswith("TODO"))


# ----- the cast -----------------------------------------------------------------------------------


def _cast(story: Story, options: DraftOptions) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[str]]:
    """The narrator's voice, the ``characters`` entries, the ``voices`` mapping, the cast rows of
    the report and notes."""
    from vidgen.screenplay import _generated_looks, assign_voices

    people = sorted(story.characters.values(), key=lambda c: (not c.protagonist, -(c.lines * 3 + c.mentions)))
    looks = _generated_looks({"theme": {"preset": "soft_pastel"}}, [c.kind for c in people], [], ("human",), options.seed)
    kinds = {c.id: c.kind or look["voice_kind"] for c, look in zip(people, looks)}
    notes: list[str] = []
    protagonist = next((c for c in people if c.protagonist), None)
    if options.narrator:
        narrator = options.narrator
    elif protagonist is not None:
        picked, _ = assign_voices({"provider": "kokoro", "voice": NARRATOR_VOICE}, None, [kinds[protagonist.id]])
        narrator = str(picked[0].get("voice") or NARRATOR_VOICE)
    else:
        narrator = NARRATOR_VOICE
    others = [c for c in people if not c.protagonist]
    settings, voice_notes = assign_voices({"provider": "kokoro", "voice": narrator}, None, [kinds[c.id] for c in others])
    notes.extend(voice_notes)
    chosen = {c.id: str(s.get("voice", "")) for c, s in zip(others, settings)}
    if protagonist is not None:
        chosen[protagonist.id] = narrator
    characters: list[dict[str, Any]] = []
    voices: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for k, (character, look) in enumerate(zip(people, looks)):
        name = f"{character.id}_voice"
        entry: dict[str, Any] = {"voice": chosen[character.id], "label": character.name, "color": VOICE_COLORS[k % len(VOICE_COLORS)]}
        if character.effect:
            entry["effect"] = character.effect
        voices[name] = entry
        characters.append({"name": character.id, "voice": name, "look": look["look"], "colors": look["colors"]})
        source = character.kind_source if character.kind else "no hint: the generated look's"
        rows.append({
            "id": character.id, "name": character.name, "kind": kinds[character.id], "kind_source": source,
            "voice": chosen[character.id], "lines": character.lines, "mentions": character.mentions,
            "protagonist": character.protagonist, "effect": character.effect, "effect_word": character.effect_word,
        })
    return narrator, characters, voices, rows, notes


# ----- a scene ------------------------------------------------------------------------------------


@dataclass
class _Stage:
    """Where the scene's characters stand and what is free while the beats are written."""

    stands: dict[str, str]
    goals: tuple[str, ...]
    gone: set[str] = field(default_factory=set)

    def goal_for(self, who: str) -> str | None:
        """A spot to walk to: the first goal nobody stands at, not where ``who`` stands."""
        taken = {spot for name, spot in self.stands.items() if name not in self.gone}
        return next((g for g in self.goals if g not in taken), None)


def _at(share: float) -> float:
    return min(math.floor(share * 20) / 20, LATEST_AT)


def _scene_light(scene: StoryScene, indoor: bool, before: str | None) -> tuple[str, str, list[tuple[int, str, str]]]:
    """The scene's light, why, and the later changes ``(line index, preset, words)``; without a
    cue a scene that does not start on a time cue keeps the night (or evening) of the scene
    ``before``."""
    default = "indoor" if indoor else "day"
    found: list[tuple[int, str, str]] = []
    for k, line in enumerate(scene.lines):
        if not line.dialogue:
            found.extend((k, preset, words) for _, preset, words in light_cues(line.text))
    heading = light_cues(scene.heading or "")
    light, reason = default, f"no time cue: {default}"
    if before in ("night", "sunset") and not scene.reason.startswith("time cue"):
        light, reason = before, f"no time cue: still {before} (the scene before)"
    if heading:
        light, reason = heading[0][1], f"heading: {heading[0][2]!r}"
    elif found and found[0][0] <= max(1, len(scene.lines) // 3):
        light, reason = found[0][1], f"cue {found[0][2]!r}"
        found = found[1:]
    if indoor:
        light = "night" if light == "night" else "indoor"
        return light, reason, []
    changes: list[tuple[int, str, str]] = []
    current = light
    for k, preset, words in found:
        if preset != current and len(changes) < 2 and (not changes or changes[-1][0] != k):
            changes.append((k, preset, words))
            current = preset
    return light, reason, changes


def _weather(scene: StoryScene, indoor: bool, place_weather: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Stage params for the scene's weather, what was found, and TODOs."""
    text = " ".join(line.text for line in scene.lines if not line.dialogue)
    found = weather_of(text)
    if place_weather.get("snow"):
        found.setdefault("snow", ["(a winter place)"])
    words = [f"{kind}: {', '.join(ws)}" for kind, ws in found.items()]
    if indoor:
        return {}, words, ([f"TODO: {', '.join(found)} outside: a room shows no weather (an ambience or sfx, or a scene outdoors)"] if found else [])
    params: dict[str, Any] = {}
    particles: list[Any] = []
    if "rain" in found:
        particles.append({"kind": "rain", "puddles": True, "settled": 8})
    if "snow" in found:
        particles.append({"kind": "snow", "settle": True, "settled": 30})
    if particles:
        params["particles"] = particles
    if "fog" in found:
        params["fog"] = 0.5
    if "wind" in found:
        params["wind"] = "gale" if {"gale", "storm", "stormy"} & set(found["wind"]) else "windy"
    return params, words, []


def _scene_cast(scene: StoryScene, characters: Sequence[str]) -> list[str]:
    """The scene's characters in order of appearance: mentioned in its narration or speaking."""
    found: list[str] = []
    for line in scene.lines:
        found.extend(line.mentions)
        if line.speaker:
            found.append(line.speaker)
    return [c for c in dict.fromkeys(found) if c in characters]


def _first_seen(scene: StoryScene, who: str) -> int:
    for k, line in enumerate(scene.lines):
        if who in line.mentions or line.speaker == who:
            return k
    return len(scene.lines)


def _seen_after(scene: StoryScene, who: str, index: int) -> bool:
    return any(who in line.mentions or line.speaker == who for line in scene.lines[index + 1:])


def _dialogue_beat(line: Line, beat: dict[str, Any], stage: _Stage, voice_of: dict[str, str], last_other: str | None) -> None:
    """Voice, emotion, shot and expression of a line of dialogue."""
    who = line.speaker
    if who is None:
        return
    beat["voice"] = voice_of[who]
    if line.emotion:
        beat["emotion"] = line.emotion
    if who not in stage.stands or who in stage.gone:
        return
    emotional = line.emotion in EMOTION_EXPRESSIONS or "!" in line.text
    present = [c for c in stage.stands if c not in stage.gone and c != who]
    other = last_other if last_other in present else (present[0] if present else None)
    if emotional:
        beat["shot"] = f"closeup {who}"
    elif len(line.text.split()) > WIDE_WORDS:
        beat["shot"] = f"two_shot {who} {other}" if other else f"closeup {who}"
    expression = EMOTION_EXPRESSIONS.get(line.emotion or "")
    if expression:
        beat["actions"] = [{"emote": who, "to": expression}]


def _narration_beat(scene: StoryScene, k: int, line: Line, beat: dict[str, Any], stage: _Stage, entering: dict[str, int],
                    notes: list[str]) -> None:
    """Walks, runs, entrances and exits of a narration line."""
    actions: list[dict[str, Any]] = []
    moved: set[str] = set()
    for move in line.moves:
        who = move.who
        if who in moved or who not in stage.stands or who in stage.gone:
            continue
        moved.add(who)
        at = _at(move.at)
        timing = {"at": at} if at > 0 else {}
        if move.kind == "enter" and entering.get(who) == k:
            actions.append({"enter": who, "to": stage.stands[who], "side": "right", **timing})
        elif move.kind == "exit":
            if _seen_after(scene, who, k):
                notes.append(f"TODO: '{move.words}': {who} leaves but is in the scene later; act it (exit / enter) by hand")
                continue
            actions.append({"exit": who, "to": "right", **timing})
            stage.gone.add(who)
        elif move.kind in ("walk", "run"):
            goal = stage.goal_for(who)
            if goal is None:
                continue
            actions.append({"walk_to" if move.kind == "walk" else "run_to": who, "to": goal, **timing})
            stage.stands[who] = goal
            notes.append(f"plan: '{move.words}' -> {move.kind} to {goal} (a placeholder spot: change `to:` to where the story goes)")
    if actions:
        beat.setdefault("actions", []).extend(actions)


def _scene(draft: StoryDraft, index: int, scene: StoryScene, previous: tuple[str, str] | None, voice_of: dict[str, str],
           used_ids: set[str]) -> tuple[dict[str, Any], str, str]:
    """The stage scene of a story scene (``previous``: the place and light of the scene before);
    returns it, its place and its light."""
    flat = draft.options.style == "flat"
    narration = " ".join(line.text for line in scene.lines if not line.dialogue)
    choice = choose_place(" ".join(filter(None, [scene.heading, narration])), previous[0] if previous else None)
    place = PLACES[choice.place]
    light, light_reason, changes = _scene_light(scene, place.indoor, previous[1] if previous else None)
    weather, weather_words, weather_todos = _weather(scene, place.indoor, place.weather)
    base = slug(scene.heading) if scene.heading else (f"{place.name}_{light}" if light not in ("day", "indoor") else place.name)
    scene_id = base
    while scene_id in used_ids or scene_id in ("title", "end"):
        scene_id = f"{base}_{index}" if scene_id == base else f"{scene_id}_{index}"
    used_ids.add(scene_id)
    extras = [] if flat else objects_named(narration, place, draft.added.get(place.name, ()))
    cast = _scene_cast(scene, list(voice_of))
    stands = FLAT_STANDS if flat else place.stands
    on_stage, off_stage = cast[: len(stands)], cast[len(stands):]
    stage = _Stage({who: stands[k] for k, who in enumerate(on_stage)}, FLAT_GOALS if flat else place.goals)
    entering = {}
    for who in on_stage:
        first = _first_seen(scene, who)
        if first > 0 and any(m.who == who and m.kind == "enter" for m in scene.lines[first].moves):
            entering[who] = first
    notes = SceneNotes(
        scene_id, scene.start_line, scene.reason, choice.place, choice.reason, light, light_reason,
        [f"beat {k + 1}: {preset} ({words!r})" for k, preset, words in changes], weather_words, on_stage, off_stage,
    )
    params: dict[str, Any] = {}
    if light != ("indoor" if place.indoor else "day") or place.indoor:
        params["light"] = light
    if not flat and not place.indoor and not changes:
        params["background"] = OUTDOOR_SKIES.get(light, OUTDOOR_SKIES["day"])
    elif not flat and place.indoor:
        params["background"] = INDOOR_SKY
    if light == "night" or any(preset == "night" for _, preset, _ in changes):
        params["fill_light"] = FILL_NIGHT_INDOOR if place.indoor else FILL_NIGHT
    params.update(weather)
    life = DRAFT_AMBIENT.get(place.name, ({}, {}))[1 if light == "night" else 0] if not flat and not place.indoor else {}
    if life:   # a little life in the background (§105.8)
        params["ambient"] = {**life, "seed": draft.options.seed + index}
    params["characters"] =[{"name": who, "at": stage.stands[who]} for who in on_stage]
    beats: list[dict[str, Any]] = []
    beat_notes: list[list[str]] = []
    change_at = {k: preset for k, preset, _ in changes}
    last_speakers: list[str] = []
    for k, line in enumerate(scene.lines):
        beat: dict[str, Any] = {"text": line.text}
        comments: list[str] = []
        if k in change_at:
            beat["actions"] = [{"time_of_day": change_at[k], "run_time": FADE_SECONDS}]
        if line.dialogue:
            last_other = next((s for s in reversed(last_speakers) if s != line.speaker), None)
            extra = beat.pop("actions", [])
            _dialogue_beat(line, beat, stage, voice_of, last_other)
            if extra:
                beat["actions"] = [*extra, *beat.get("actions", [])]
            if line.speaker:
                last_speakers.append(line.speaker)
            draft.attributions.append(Attribution(scene_id, k + 1, line.speaker, line.confidence, line.method, line.text))
            if line.speaker is None:
                comments.append(f"TODO: who says this? ({line.method}); the narrator reads it now: give it `voice: <name>_voice`")
            elif line.confidence < DOUBTFUL:
                comments.append(f"TODO: speaker guessed ({line.method}, {line.confidence:.0%}): check `voice:`")
            if line.speaker in off_stage:
                comments.append(f"TODO: {line.speaker} speaks but is not on this stage (four at most): stand it in or cut a character")
        else:
            _narration_beat(scene, k, line, beat, stage, entering, comments)
        beats.append(beat)
        beat_notes.append(comments)
    entry: dict[str, Any] = {"id": scene_id, "type": "stage"}
    night = light == "night" and bool(place.lights or place.lit)
    if flat:
        entry["set"] = place.flat_set
    else:
        entry["set"] = f"{place.name}_night" if night else place.name
    if extras:   # on the place's set: every scene there shows them
        draft.added.setdefault(place.name, []).extend(extras)
        notes.objects = [f"{kind} ('{word}')" for word, kind, _ in extras]
    entry["transition"] = "iris_in" if index == 1 else "crossfade"
    entry["params"] = params
    entry["beats"] = beats
    scene_comments = [f"story: line {scene.start_line} ({scene.reason}); place {choice.place} ({choice.reason}); light {light} ({light_reason})"]
    if weather_words:
        scene_comments.append(f"weather: {'; '.join(weather_words)}")
    if extras:
        scene_comments.append(f"plan: objects the story names, added to the set {entry['set']}: {', '.join(notes.objects)}")
    if "ambient" in params:
        scene_comments.append("plan: a little background life (ambient: passers-by, birds, fireflies at night); remove it for a quiet place")
    if flat and place.flat_set != place.name:
        scene_comments.append(f"plan: the story's place reads as '{place.name}'; the nearest flat set is '{place.flat_set}'")
    if off_stage:
        notes.todos.append(f"{', '.join(off_stage)} not on the stage (a place has {len(stands)} spots)")
        scene_comments.append(f"TODO: {', '.join(off_stage)} not on the stage: a place has {len(stands)} spots; split the scene or add spots")
    notes.todos.extend(t.removeprefix("TODO: ") for t in weather_todos)
    scene_comments.extend(weather_todos)
    draft.scenes.append(notes)
    draft.scene_comments.append(scene_comments)
    draft.beat_comments.append(beat_notes)
    return entry, choice.place, light


def draft_story(story: Story, options: DraftOptions | None = None) -> StoryDraft:
    """The project drafted from ``story`` (see the module doc)."""
    from vidgen.plan_yaml import FORMATS

    options = options or DraftOptions()
    final, preview = FORMATS[options.fmt]
    title = story.title or options.default_title
    narrator, characters, voices, rows, notes = _cast(story, options)
    music, counts = music_of(" ".join(line.text for s in story.scenes for line in s.lines))
    config: dict[str, Any] = {
        "title": title,
        "format": dict(final),
        "preview": dict(preview),
        "theme": {"preset": "soft_pastel"},
        "voice": {"provider": "kokoro", "voice": narrator, "speed": 0.85},
        "narration": {"pad": 0.4},
        "music": {"source": music, "volume": -4},
        "overlays": [{"type": "captions", "speakers": "color"}],
        "auto_direct": True,
    }
    if voices:
        config["voices"] = voices
    config["characters"] = characters
    draft = StoryDraft(config, story, options, cast=rows, music=(music, counts), notes=notes)
    voice_of = {c["name"]: c["voice"] for c in characters}
    scenes: list[dict[str, Any]] = [{"id": "title", "type": "card", "params": {"text": title}, "duration": TITLE_SECONDS}]
    draft.scene_comments.append([])
    draft.beat_comments.append([])
    previous: tuple[str, str] | None = None
    used: set[str] = set()
    places: dict[str, str] = {}
    lights: list[str] = []
    for index, scene in enumerate((s for s in story.scenes if s.lines), 1):
        entry, place, light = _scene(draft, index, scene, previous, voice_of, used)
        previous = (place, light)
        lights.append(light)
        scenes.append(entry)
        places.setdefault(entry["set"], place)
    mood = card_mood(lights, music, " ".join(line.text for s in story.scenes for line in s.lines))
    if mood is not None:   # the card's look by the story's mood (§105.8)
        scenes[0]["params"].update(CARD_LOOKS[mood])
        draft.notes.append(f"title card: {mood} look ({', '.join(f'{k} {v}' for k, v in CARD_LOOKS[mood].items())})")
    sets = {} if options.style != "iso" else {
        name: {"iso": PLACES[place].iso(name.endswith("_night"), draft.added.get(place, ()))} for name, place in places.items()
    }
    scenes.append({"id": "end", "type": "end_card", "params": {"title": "The End"}, "duration": END_SECONDS, "transition": "crossfade"})
    draft.scene_comments.append([])
    draft.beat_comments.append([])
    if sets:
        config["sets"] = sets
    config["scenes"] = scenes
    return draft


def story_yaml(draft: StoryDraft, source: str) -> str:
    """The draft's ``video.yaml`` text with its comments (why each scene, TODOs on beats)."""
    from vidgen.plan_yaml import commented_yaml

    header = [
        f"# Draft written by `vidgen story draft` from {source} (no AI: rules and keyword tables). A starting",
        "# point: places, spots and walks are placeholders; story_draft.md lists every decision, how sure each",
        f"# speaker is and what to refine. Then: vidgen validate, vidgen storyboard, vidgen lint (`vidgen guide "
        f"{'iso' if draft.options.style == 'iso' else 'cartoons'}`).",
    ]
    keys = {"characters": ["generated looks and voices: `vidgen character-sheet --all`"]}
    if draft.notes:
        keys["voices"] = [f"TODO: {n}" for n in draft.notes]
    return commented_yaml(draft.config, header, keys, draft.scene_comments, draft.beat_comments)


# ----- the report ----------------------------------------------------------------------------------


def report_markdown(draft: StoryDraft, source: str, config_path: str) -> str:
    """``story_draft.md``: the draft's decisions, attributions and a TODO checklist."""
    story, options = draft.story, draft.options
    lines = [
        f"# Story draft: {draft.config['title']}",
        "",
        f"Drafted by `vidgen story draft` from `{source}` (no AI: rules and keyword tables). Config: `{config_path}`.",
        f"Style {options.style}, format {options.fmt}; {story.words} words, {len(draft.scenes)} scenes, "
        f"{sum(len(s.lines) for s in story.scenes)} beats.",
        "",
        "## Narration",
        "",
        f"- Told in the **{'first' if story.first_person else 'third'} person** ({story.person_note}).",
        f"- Narrator voice: `{draft.config['voice']['voice']}`"
        + (" (the protagonist's: the narrator is the one telling the story)" if story.first_person else "") + ".",
        f"- Music: `{draft.music[0]}`"
        + (f" (mood words: {', '.join(f'{b} {n}' for b, n in draft.music[1].items())})" if draft.music[1] else " (no mood words: the default)")
        + "; captions in the speakers' colours; `auto_direct: true`.",
        "",
        "## Cast",
        "",
        "| id | name | voice kind (from) | voice | lines | mentions | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in draft.cast:
        note = "protagonist / narrator" if row["protagonist"] else ""
        if row["effect"]:
            note = (note + "; " if note else "") + f"effect {row['effect']} ('{row['effect_word']}' near the name)"
        lines.append(f"| {row['id']} | {row['name']} | {row['kind']} ({row['kind_source']}) | {row['voice']} | {row['lines']} | {row['mentions']} | {note} |")
    if not draft.cast:
        lines.append("| - | no characters found | | | | | |")
    lines += ["", "## Scenes", "", "| scene | starts at | place (why) | light (why) | changes | weather | objects added | on stage |",
              "|---|---|---|---|---|---|---|---|"]
    for s in draft.scenes:
        lines.append(
            f"| {s.id} | line {s.source_line} ({s.reason}) | {s.place} ({s.place_reason}) | {s.light} ({s.light_reason}) | "
            f"{'; '.join(s.changes) or '-'} | {'; '.join(s.weather) or '-'} | {', '.join(s.objects) or '-'} | {', '.join(s.cast) or '-'}"
            + (f" (not placed: {', '.join(s.off_stage)})" if s.off_stage else "") + " |"
        )
    lines += ["", "## Dialogue attribution", ""]
    if draft.attributions:
        lines += ["| scene | beat | speaker | confidence | how | line |", "|---|---|---|---|---|---|"]
        for a in draft.attributions:
            flag = " **check**" if a.speaker is None or a.confidence < DOUBTFUL else ""
            words = a.text if len(a.text) <= 60 else a.text[:57] + "..."
            lines.append(f"| {a.scene} | {a.beat} | {a.speaker or 'narrator'} | {a.confidence:.0%}{flag} | {a.method} | {words.replace('|', '/')} |")
    else:
        lines.append("No dialogue found (double quotes: \"...\", “...” or «...»).")
    doubtful = [a for a in draft.attributions if a.speaker is None or a.confidence < DOUBTFUL]
    lines += ["", "## TODO (for the author or an agent)", ""]
    todo = [
        f"Check the {len(doubtful)} doubtful attributions above (beats with `# TODO: speaker guessed`): set each beat's `voice:`."
        if doubtful else "Read the attributions above once (all were tagged or clear).",
        "Check the cast: a capitalised place or thing taken for a character, or a character missed (`characters:` and `voices:`).",
        "Look at the generated looks (`vidgen character-sheet --all`): species, clothes and colours that suit the story.",
        "Places are ready-made placeholders: rename spots, add or move objects (`vidgen guide iso`), give each scene its own place.",
        "Walks go to placeholder spots: point each `walk_to` / `run_to` at where the story goes; add `pick_up`, `give`, `open`, `sit_on`, `use`.",
        "Shorten long narration beats and cut what the picture shows; add `sfx` on the moments that matter.",
        "Music: `vidgen list-music`; a scene's mood can change with `music: {mood: ...}` (composed music).",
        "Then: `vidgen validate`, `vidgen storyboard` (look at the stills), `vidgen lint`, `vidgen tts`, `vidgen render`.",
    ]
    todo += [f"{s.id}: {t}" for s in draft.scenes for t in s.todos]
    todo += draft.notes
    lines += [f"- [ ] {t}" for t in todo]
    return "\n".join(lines) + "\n"
