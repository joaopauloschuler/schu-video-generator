"""Cuts (DESIGN.md §101): a shorter video made of chosen scenes and beats of a longer one.

A config's ``cut:`` (usually in a variant: one variant per Short or teaser) lists the scenes to
show, in order, each whole or with some of its beats, and what changes in this cut: a scene's
``params`` (merged like a set's: characters, props and layers by name), any other scene key, and
beats by id (``cut.beats``). A ``hook`` adds the ``hook`` overlay (a big caption over the first
seconds) and an ``end_card`` a card at the end. :func:`apply_cut` rewrites the raw config before
it is validated, so everything after it (sets, audio, rendering, lint) sees an ordinary config.

Beats keep their ids (a beat without an ``id`` gets the one it has in the full video,
``<scene>_b<n>``), so a cut reuses the full video's narration audio.
"""

from __future__ import annotations

import copy
import difflib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from vidgen.config import CutConfig, CutEndCard, CutScene
from vidgen.errors import Problem, VidgenError
from vidgen.includes import Origin, entry_names

#: Stage params whose list entries a cut's ``params`` changes by name (like a set's).
NAMED_LISTS = ("characters", "props", "layers")
#: The id of the overlay a cut's ``hook`` adds.
HOOK_ID = "hook"


def merge_params(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """A scene's ``params`` with a cut's changes: mappings merge key by key (recursively),
    ``characters`` / ``props`` / ``layers`` entries named like one of the scene's change it (its
    keys win; others are added; an empty list clears them), anything else is replaced."""
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        before = merged.get(key)
        if isinstance(value, Mapping) and isinstance(before, Mapping):
            merged[key] = merge_params(before, value)
        elif key in NAMED_LISTS and isinstance(value, list) and isinstance(before, list) and value:
            merged[key] = _merge_named(key, before, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_named(key: str, base: list[Any], override: list[Any]) -> list[Any]:
    out = copy.deepcopy(base)
    names = {name: j for j, name in enumerate(entry_names(key, base)) if name is not None}
    for entry, name in zip(override, entry_names(key, override)):
        j = names.get(name) if name is not None else None
        if j is not None and isinstance(out[j], Mapping) and isinstance(entry, Mapping):
            out[j] = merge_params(out[j], entry)
        elif j is not None and isinstance(entry, Mapping):
            out[j] = copy.deepcopy(dict(entry))
        else:
            out.append(copy.deepcopy(entry))
    return out


def _merge(base: Any, override: Any) -> Any:
    """Mappings merged key by key (recursively); anything else replaced."""
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        out = copy.deepcopy(dict(base))
        for key, value in override.items():
            out[key] = _merge(out.get(key), value)
        return out
    return copy.deepcopy(override)


def _with_beat_ids(scene: dict[str, Any]) -> dict[str, Any]:
    """``scene`` with every beat's id written out (``<scene id>_b<n>`` where it has none), so
    the beats keep their ids (and audio) whatever the cut keeps or renames."""
    beats = scene.get("beats")
    if not isinstance(beats, list):
        return scene
    filled = []
    for n, beat in enumerate(beats, start=1):
        if isinstance(beat, Mapping) and beat.get("id") is None:
            beat = {**beat, "id": f"{scene['id']}_b{n}"}
        filled.append(beat)
    return {**scene, "beats": filled}


def _unknown(kind: str, name: str, known: Sequence[str]) -> str:
    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return f"unknown {kind} '{name}'{hint} ({kind}s: {', '.join(known) or 'none'})"


def _select_beats(scene: dict[str, Any], entry: CutScene, where: str, problems: list[Problem]) -> None:
    """Keep the beats ``entry.beats`` names (in place)."""
    if entry.beats is None:
        return
    beats = [b for b in scene.get("beats") or [] if isinstance(b, Mapping)]
    ids = [str(b.get("id")) for b in beats]
    if not beats:
        problems.append(Problem(f"{where}.beats", f"scene '{entry.scene}' has no beats to choose from"))
        return
    if isinstance(entry.beats, list):
        missing = [b for b in entry.beats if b not in ids]
        for name in missing:
            problems.append(Problem(f"{where}.beats", _unknown("beat", name, ids).replace("beats:", f"beats of scene '{entry.scene}':")))
        if len(set(entry.beats)) != len(entry.beats):
            problems.append(Problem(f"{where}.beats", "a beat is listed twice"))
        if missing or not entry.beats:
            return
        by_id = dict(zip(ids, beats))
        scene["beats"] = [by_id[b] for b in entry.beats]
        return
    first = ids.index(entry.beats.from_) if entry.beats.from_ in ids else None
    last = ids.index(entry.beats.to) if entry.beats.to in ids else None
    for key, name, found in (("from", entry.beats.from_, first), ("to", entry.beats.to, last)):
        if name is not None and found is None:
            problems.append(Problem(f"{where}.beats.{key}", _unknown("beat", name, ids)))
    first = 0 if first is None else first
    last = len(beats) - 1 if last is None else last
    if last < first:
        problems.append(Problem(f"{where}.beats", f"'to' ({ids[last]}) comes before 'from' ({ids[first]})"))
        return
    scene["beats"] = beats[first:last + 1]


def _end_card(data: Mapping[str, Any], spec: str | CutEndCard) -> dict[str, Any]:
    card = CutEndCard(text=spec) if isinstance(spec, str) else spec
    title = card.title or str(data.get("title") or "")
    params: dict[str, Any] = {"title": title, "lines": [card.text]} if card.type == "end_card" else {"text": title, "subtitle": card.text}
    scene: dict[str, Any] = {"id": card.id, "type": card.type, "params": merge_params(params, card.params), "duration": card.seconds}
    if card.transition is not None:
        scene["transition"] = copy.deepcopy(card.transition)
    return scene


def _hook(spec: str | Mapping[str, Any]) -> dict[str, Any]:
    options = {"text": spec} if isinstance(spec, str) else dict(spec)
    return {"type": HOOK_ID, "id": HOOK_ID, **options}


def _moved_origins(origins: Mapping[str, Origin], sources: Sequence[int | None]) -> dict[str, Origin]:
    """``origins`` with the locations under ``scenes[i]`` moved to where scene ``i`` is in the
    cut (``sources[j]`` is the full video's index of the cut's scene ``j``; scenes left out lose
    theirs)."""
    pattern = re.compile(r"^scenes\[(\d+)\](.*)$")
    out: dict[str, Origin] = {}
    for key, origin in origins.items():
        match = pattern.match(key)
        if match is None:
            out[key] = origin
            continue
        for j, i in enumerate(sources):
            if i == int(match[1]):
                out[f"scenes[{j}]{match[2]}"] = origin
    return out


def shorts_warnings(project: Any) -> list[str]:
    """What ``vidgen validate`` warns about a Short (``shorts:``): a format that is not portrait,
    and a planned length (with the narration audio there is) over ``max_seconds``."""
    from vidgen.scales import frame_orientation
    from vidgen.videoplan import VideoPlan

    zones = project.config.shorts_zones
    if zones is None:
        return []
    out = []
    fmt = project.config.format
    if frame_orientation(fmt.width, fmt.height) != "portrait":
        out.append(f"shorts: the format is {fmt.width}x{fmt.height}; a Short is vertical (format: {{width: 1080, height: 1920}})")
    seconds = VideoPlan(project, fmt.fps).duration
    if seconds > zones.max_seconds + 1e-6:
        out.append(f"shorts: the video is planned {seconds:.1f} s long, over its {zones.max_seconds:g} s (max_seconds); leave out beats or scenes")
    return out


def apply_cut(data: Any, origins: Mapping[str, Origin] | None = None) -> tuple[Any, dict[str, Origin]]:
    """``data`` (a raw config) with its ``cut:`` applied: its scenes replaced by the cut's
    (whole or some beats, with the cut's changes), the beats changed by ``cut.beats``, the hook
    overlay added and the end card appended; ``origins`` moved with the scenes. Unchanged when
    there is no cut, or when ``cut:`` is malformed (the config check reports it). Raises
    :class:`VidgenError` (problems at ``cut...``) for a scene or beat the video does not have."""
    origins = dict(origins or {})
    if not isinstance(data, Mapping) or data.get("cut") is None or not isinstance(data.get("scenes"), list):
        return data, origins
    try:
        cut = CutConfig.model_validate(data["cut"])
    except ValidationError:
        return data, origins
    scenes = [s for s in data["scenes"] if isinstance(s, Mapping) and isinstance(s.get("id"), str)]
    index = {str(s["id"]): i for i, s in enumerate(data["scenes"]) if isinstance(s, Mapping) and isinstance(s.get("id"), str)}
    problems: list[Problem] = []
    chosen: list[dict[str, Any]] = []
    sources: list[int | None] = []
    for k, raw in enumerate(cut.scenes):
        where = f"cut.scenes[{k}]"
        entry = CutScene(scene=raw) if isinstance(raw, str) else raw
        if entry.scene not in index:
            problems.append(Problem(where if isinstance(raw, str) else f"{where}.scene", _unknown("scene", entry.scene, [str(s["id"]) for s in scenes])))
            continue
        scene = _with_beat_ids(copy.deepcopy(dict(data["scenes"][index[entry.scene]])))
        if not chosen:   # the way into the cut's first scene came from a scene not in the cut
            scene.pop("transition", None)
        _select_beats(scene, entry, where, problems)
        for key, value in (entry.model_extra or {}).items():
            if key == "params" and isinstance(value, Mapping) and isinstance(scene.get("params"), Mapping):
                scene["params"] = merge_params(scene["params"], value)
            else:
                scene[key] = _merge(scene.get(key), value)
        chosen.append(scene)
        sources.append(index[entry.scene])
    seen: dict[str, int] = {}
    for j, scene in enumerate(chosen):
        sid = str(scene.get("id"))
        if sid in seen:
            problems.append(Problem(f"cut.scenes[{j}]", f"scene id '{sid}' comes twice in the cut; give the second one another id (id: {sid}_2)"))
        seen[sid] = j
    beats: dict[str, dict[str, Any]] = {}
    for scene in chosen:
        for beat in scene.get("beats") or []:
            if isinstance(beat, Mapping):
                if str(beat.get("id")) in beats:
                    problems.append(Problem("cut.scenes", f"beat '{beat.get('id')}' is shown twice in the cut (beat ids must be unique)"))
                beats[str(beat.get("id"))] = beat  # type: ignore[assignment]
    for beat_id, change in cut.beats.items():
        if beat_id not in beats:
            problems.append(Problem(f"cut.beats.{beat_id}", _unknown("beat", beat_id, list(beats)).replace("beats:", "beats of the cut:")))
    if problems:
        lines = ["invalid cut", *(f"  {p}" for p in problems)]
        raise VidgenError("\n".join(lines), problems=problems)
    for scene in chosen:
        if isinstance(scene.get("beats"), list):
            scene["beats"] = [_merge(b, cut.beats[b["id"]]) if isinstance(b, Mapping) and b.get("id") in cut.beats else b for b in scene["beats"]]
    out = {**data, "scenes": chosen}
    if cut.end_card is not None:
        out["scenes"] = [*chosen, _end_card(data, cut.end_card)]
        sources.append(None)
    if cut.hook is not None:
        overlays = data.get("overlays") if isinstance(data.get("overlays"), list) else []
        out["overlays"] = [*overlays, _hook(cut.hook)]
    return out, _moved_origins(origins, sources)
