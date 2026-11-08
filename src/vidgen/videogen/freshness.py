"""Whether a shot's cut inputs still match what they were cut from (DESIGN.md §113.9).

:func:`vidgen.videogen.inputs.make_inputs` writes ``build/videogen/<shot>/inputs.json`` next to
the cut inputs: per file its SHA-256 and what it was made from. The plan
(:func:`vidgen.videogen.shots.plan_shots`) compares that with the current state, free and offline
(no render, no browser, no network):

- the voice (``audio.mp3``): the SHA-256 of the beat's narration MP3 and the part's offset and
  length;
- a render input (``guide*.mp4``, ``first_frame.png``): the draft project's
  :func:`~vidgen.render.fingerprint.scene_fingerprint` (a draft ignores picked takes,
  :mod:`vidgen.videogen.compose`, so a pick never marks an input as changed), the draft's size and
  frame rate (a draft's ``draft:`` settings are not in the fingerprint), the part's offset and
  length and the guide kind.

A narration MP3 whose ``.hash`` says it no longer matches the beat's text is reported as well
(cutting it again would only cut the same old voice): ``vidgen tts`` comes first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.fileio import write_text_atomic
from vidgen.project import Project
from vidgen.soundfont import file_sha256
from vidgen.videogen.shots import INPUTS_DIR, Shot, ShotInput, inputs_command

#: The record of a shot's cut inputs, in the shot's folder.
RECORD_NAME = "inputs.json"
RECORD_VERSION = 1
#: What differs between a recorded source and the current one, in the order it is reported.
_CHANGE_REASONS: tuple[tuple[str, str], ...] = (
    ("narration_sha256", "the beat's narration MP3 changed"),
    ("scene_fingerprint", "the scene changed (its config, a beat's text, voice or timing, assets, or vidgen)"),
    ("draft", "the draft's size or frame rate changed"),
    ("offset", "the shot's part of the beat moved"),
    ("length", "the shot's length changed"),
    ("guide", "the guide kind changed"),
)


def _part(shot: Shot) -> dict[str, float]:
    return {"offset": round(shot.offset, 6), "length": round(shot.length, 6)}


def voice_source(mp3: Path, shot: Shot) -> dict[str, Any]:
    """What ``shot``'s voice is cut from: the narration MP3 ``mp3`` and the part."""
    return {"narration_sha256": file_sha256(mp3), **_part(shot)}


def _read_record(path: Path) -> dict[str, Any]:
    """The shot's record (``{}`` when missing, unreadable or of another version)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc.get("inputs", {}) if isinstance(doc, dict) and doc.get("version") == RECORD_VERSION else {}


def record_input(path: Path, source: dict[str, Any]) -> None:
    """Note in the record beside the cut input ``path`` that it was made from ``source``."""
    record = path.parent / RECORD_NAME
    inputs = _read_record(record)
    inputs[path.name] = {"sha256": file_sha256(path), "source": source}
    write_text_atomic(record, json.dumps({"version": RECORD_VERSION, "inputs": inputs}, indent=1, sort_keys=True, ensure_ascii=True) + "\n")


@dataclass(frozen=True)
class StaleInputs:
    """Why a shot's cut inputs no longer match, and the command that makes them again."""

    reasons: tuple[str, ...]
    command: str
    needs_tts: bool = False

    @property
    def _action(self) -> str:
        cut = f"`{self.command}` (free)"
        return f"`vidgen tts` for the beat's voice, then {cut}" if self.needs_tts else cut

    @property
    def blocked(self) -> str:
        """The shot's blocked reason."""
        return f"inputs changed since they were cut ({'; '.join(self.reasons)}): run {self._action} before paying"

    @property
    def reuse_note(self) -> str:
        """The note of a shot that would not be paid: its clip or job exists from the old inputs."""
        return (
            f"inputs changed since they were cut ({'; '.join(self.reasons)}), but this request's clip is already paid for: it is reused free. "
            f"For a clip of the new ones, run {self._action}; that is a new request, paid again"
        )


@dataclass
class InputSources:
    """What the inputs of ``project``'s shots are made from now: the draft project's scene
    fingerprints (once per scene) and the narration MP3s."""

    project: Project
    _draft: Project | None = None
    _renders: dict[str, dict[str, Any]] = field(default_factory=dict)
    _outdated_voices: set[str] | None = None

    def _mp3(self, shot: Shot) -> Path:
        return self.project.audio_dir / f"{shot.beat.id}.mp3"

    def render(self, shot: Shot, kind: str, fingerprint: str | None = None) -> dict[str, Any]:
        """The current source of a render input of ``shot``: a guide of ``kind`` or the first frame
        (``render``). ``fingerprint``: the render's own record, when known (else computed)."""
        scene = self._render_of(shot.scene_id)
        return {**scene, "scene_fingerprint": fingerprint or scene["scene_fingerprint"], "guide": kind, **_part(shot)}

    def _render_of(self, scene_id: str) -> dict[str, Any]:
        if scene_id not in self._renders:
            from vidgen import extensions
            from vidgen.render.fingerprint import scene_fingerprint

            if self._draft is None:
                self._draft = Project.load(self.project.config_file, variant=self.project.variant, draft=True)
            size = self._draft.render_format(False)
            with extensions.project_session(self._draft):   # as the render's own fingerprint is taken
                digest = scene_fingerprint(self._draft, scene_id)
            self._renders[scene_id] = {"scene_fingerprint": digest, "draft": [size.width, size.height, size.fps]}
        return self._renders[scene_id]

    def voice_is_outdated(self, beat_id: str) -> bool:
        """Whether the beat's ``.hash`` says its MP3 was made for another text or voice (an MP3
        without a ``.hash`` is the owner's own and counts as current)."""
        if self._outdated_voices is None:
            from vidgen.tts.cache import audio_status

            self._outdated_voices = {s.beat_id for s in audio_status(self.project) if s.state == "stale" and s.hash_file.is_file()}
        return beat_id in self._outdated_voices

    def stale(self, shot: Shot) -> StaleInputs | None:
        """How ``shot``'s cut inputs differ from what they were cut from; ``None`` when they all
        match or some are not made yet (the plan already blocks those)."""
        folder = self.project.root / INPUTS_DIR / shot.id
        cut = [i for i in shot.inputs if i.path.parent == folder]
        if not cut or any(not i.ready for i in cut):
            return None
        recorded = _read_record(folder / RECORD_NAME)
        reasons: list[str] = []
        guide = needs_tts = False
        for item in cut:
            reason = self._change(shot, item, recorded.get(item.path.name))
            if reason is not None:
                reasons.append(f"{item.path.name}: {reason}")
                guide = guide or item.role != "audio"
            if item.role != "audio":
                continue
            outdated = self.voice_is_outdated(shot.beat.id)
            needs_tts = needs_tts or outdated or not self._mp3(shot).is_file()
            if outdated:
                reasons.append(f"{item.path.name}: the beat's narration MP3 does not match its text or voice")
        if not reasons:
            return None
        return StaleInputs(tuple(reasons), inputs_command(self.project, guide), needs_tts)

    def _change(self, shot: Shot, item: ShotInput, record: Any) -> str | None:
        """Why ``item`` no longer matches its ``record``, else ``None``."""
        if not isinstance(record, dict):
            return "no record of what it was cut from (cut by an older vidgen, or the cut did not finish)"
        if item.role == "audio":
            if not self._mp3(shot).is_file():
                return "the beat has no narration MP3 any more"
            source = voice_source(self._mp3(shot), shot)
        else:
            source = self.render(shot, (shot.spec.guide_source or "render") if item.role == "guide" else "render")
        wrote = record.get("source")
        if wrote != source:
            wrote = wrote if isinstance(wrote, dict) else {}
            return next((why for key, why in _CHANGE_REASONS if wrote.get(key) != source.get(key)), "it was cut from something else")
        return None if record.get("sha256") == file_sha256(item.path) else "the file was changed after it was cut"


__all__ = ["RECORD_NAME", "InputSources", "StaleInputs", "record_input", "voice_source"]
