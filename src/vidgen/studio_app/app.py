"""What the studio's JSON API does (DESIGN.md §94.2), without HTTP: the presets, the patches,
loading a score into a new session, checking score text, rendering a version (whole or one
section) into the session's render cache. The HTTP layer (:mod:`vidgen.studio_app.server`)
only translates requests to these calls and their results to JSON.

The sound is always vidgen's own renderer (:func:`vidgen.studio.render_music_score`); the browser
only plays the WAV files written here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import wave
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from vidgen import __version__
from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic, write_text_atomic
from vidgen.studio_app import song
from vidgen.studio_app.edits import apply_edits
from vidgen.studio_app.session import StudioSession, studio_dir, write_open_marker
from vidgen.studio_app.song import describe_score

#: Bump when the studio's renders of the same score change (their cache key includes it).
#: 2 (Step 194): a render's facts hold its loudness per bar (the timeline's energy curve).
STUDIO_RENDER_VERSION = 2
#: The lowest loudness the energy curve shows (a silent bar), LUFS.
ENERGY_FLOOR = -70.0
#: The preset loaded when the page opens without a session (the guide's first suggestion).
DEFAULT_PRESET = "momentum"
#: Longest one-line preset description (characters).
ONE_LINE_CHARS = 110
#: A render cache key (hex digits of a SHA-256).
RENDER_KEY = re.compile(r"^[0-9a-f]{20}$")
#: Audio file names the server may send: ``<key>.wav``, a listening mix with tracks muted
#: ``<key>.m<tag>.wav``, and a section of either, ``<key>[.m<tag>]-<section>.wav``.
AUDIO_NAME = re.compile(r"^([0-9a-f]{20})(?:\.m([0-9a-f]{10}))?(?:-([a-z][a-z0-9_]*))?\.wav$")


def one_line(description: str) -> str:
    """The first clause of a bed's description (up to its first ``:`` or sentence end), cut at a
    comma to at most :data:`ONE_LINE_CHARS` characters."""
    text = re.split(r":|\.\s", description, maxsplit=1)[0].strip().rstrip(".")
    if len(text) > ONE_LINE_CHARS:
        cut = text[:ONE_LINE_CHARS].rfind(", ")
        text = text[:cut] if cut > 0 else text[: ONE_LINE_CHARS - 1] + "…"
    return text


def preset_catalog() -> list[dict[str, Any]]:
    """The 17 built-in beds as presets, in the beds' order: name, title, a one-line description,
    the bed's description and use, and the template's key, tempo, time, bars, seconds, sections
    and tracks; ``score_bed`` when the template is the bed itself (§93.12)."""
    from vidgen.music import BUILTIN_BEDS
    from vidgen.studio import music_template_catalog

    out = []
    for t in music_template_catalog():
        bed = BUILTIN_BEDS[t["name"]]
        out.append({**t, "one_line": one_line(bed.description), "bed_description": bed.description, "use": bed.use, "score_bed": bed.score})
    return out


def parse_problems(message: str) -> list[dict[str, Any]]:
    """The ``where: what`` lines of a score's :class:`VidgenError` as ``{where, message}``."""
    lines = [line[4:] for line in message.splitlines() if line.startswith("  - ")]
    if not lines:
        return [{"where": "", "message": message}]
    out = []
    for line in lines:
        where, sep, what = line.partition(": ")
        out.append({"where": where, "message": what} if sep and " " not in where else {"where": "", "message": line})
    return out


_PATH_PART = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def line_of(text: str, where: str) -> int | None:
    """The line (1-based) of the YAML node a problem's ``where`` (``tracks.bass.steps``,
    ``sections[2].bars``) names, or of its nearest parent that exists; ``None`` for none."""
    try:
        node = yaml.compose(text)
    except yaml.YAMLError:
        return None
    if node is None:
        return None
    line = None
    for m in _PATH_PART.finditer(where):
        if isinstance(node, yaml.MappingNode) and m[1] is not None:
            found = next(((k, v) for k, v in node.value if isinstance(k, yaml.ScalarNode) and k.value == m[1]), None)
            if found is None:
                break
            line, node = found[0].start_mark.line + 1, found[1]
        elif isinstance(node, yaml.SequenceNode) and m[2] is not None and int(m[2]) < len(node.value):
            node = node.value[int(m[2])]
            line = node.start_mark.line + 1
        else:
            break
    return line


def check_text(text: str) -> tuple[Any, Any, list[dict[str, Any]]]:
    """Read and check score ``text``: ``(data, score, problems)`` — ``score`` is ``None`` when
    there are problems (each ``{where, message, line}``), ``data`` when the YAML parsed."""
    from vidgen.studio import parse_music_score

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        what = getattr(exc, "problem", None) or str(exc)
        return None, None, [{"where": f"line {line}" if line else "", "message": f"not valid YAML: {what}", "line": line}]
    try:
        score = parse_music_score(data, "score")
    except VidgenError as exc:
        problems = parse_problems(str(exc))
        for p in problems:
            p["line"] = line_of(text, p["where"]) if p["where"] else None
        return data, None, problems
    return data, score, []


def mute_tag(muted: Iterable[str]) -> str:
    """The file-name tag of a listening mix without the ``muted`` tracks (10 hex digits)."""
    return hashlib.sha256(",".join(sorted(set(muted))).encode("utf-8")).hexdigest()[:10]


def render_key(data: Any) -> str:
    """The render cache key of a score's data: the same notes (comments and layout aside), the
    same renderer and vidgen version give the same key."""
    doc = {"score": data, "renderer": STUDIO_RENDER_VERSION, "vidgen": __version__}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def audition_gain_db() -> float:
    """How much louder the studio plays a piece than a video's mix does: the Listen page's
    +12 dB (−28 → −16 LUFS), the same for every version so A/B is level-matched."""
    from vidgen.listen import MUSIC_GAIN_DB

    return MUSIC_GAIN_DB


#: Edits that change more than one value (:mod:`vidgen.studio_app.song`), by op name.
SONG_OPS = ("add_track", "delete_track", "add_section", "remove_section", "rename_section")


def _op_label(op: Mapping[str, Any]) -> str:
    from vidgen.studio_app.edits import flow

    kind, path = op.get("op"), op.get("path")
    if kind == "set":
        text = flow(op.get("value"))
        return f"{path} {text if len(text) <= 40 else text[:39] + '…'}"
    return f"{kind} {path}"


def _apply_ops(text: str, ops: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    """``text`` with ``ops`` applied in order, and a label for each: the song edits are turned
    into value edits against the text as it is when their turn comes."""
    labels = []
    for op in ops:
        kind = op.get("op") if isinstance(op, Mapping) else None
        if kind not in SONG_OPS:
            text = apply_edits(text, [op])
            labels.append(_op_label(op))
            continue
        data, score, problems = check_text(text)
        if score is None:
            raise VidgenError(f"{kind}: the score has problems to fix first ({problems[0]['where']}: {problems[0]['message']})")
        name = op.get("name")
        if kind == "add_track":
            values, label = song.add_track(data, score, str(op.get("instrument", "")), name)
        elif kind == "delete_track":
            values, label = song.delete_track(data, str(name))
        elif kind == "add_section":
            after, bars = op.get("after"), op.get("bars", 4)
            if not isinstance(bars, int) or isinstance(bars, bool) or not 1 <= bars <= 64:
                raise VidgenError("add section: bars is a whole number from 1 to 64")
            values, label = song.add_section(data, after if isinstance(after, int) and not isinstance(after, bool) else None, name, bars)
        elif kind == "remove_section":
            values, label = song.remove_section(data, str(name))
        else:
            values, label = song.rename_section(data, str(name), op.get("to"))
        text = apply_edits(text, values)
        labels.append(label)
    return text, labels


def _slice_wav(source: Path, target: Path, first: int, count: int) -> None:
    """Write frames ``first .. first + count`` of the WAV ``source`` as ``target``, bit-exact."""
    import io

    with wave.open(str(source), "rb") as src:
        params = src.getparams()
        src.setpos(min(first, src.getnframes()))
        frames = src.readframes(count)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(frames)
    write_bytes_atomic(target, buffer.getvalue())


class StudioApp:
    """The studio's state for one server: its folder, the open session, the render cache.
    Thread-safe: session changes hold one lock, renders another (one render at a time)."""

    def __init__(self, project_root: Path | None, studio: Path | None = None) -> None:
        self.project_root = project_root
        self.studio = studio if studio is not None else studio_dir(project_root)
        self.session: StudioSession | None = None
        self.url: str | None = None
        self._lock = threading.RLock()
        self._render_lock = threading.Lock()
        self._presets: list[dict[str, Any]] | None = None

    # ----- facts ---------------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        return {
            "vidgen": __version__,
            "project": str(self.project_root) if self.project_root else None,
            "studio": str(self.studio),
            "default_preset": DEFAULT_PRESET,
            "audition_gain_db": audition_gain_db(),
            "session": self.session.id if self.session else None,
        }

    def presets(self) -> list[dict[str, Any]]:
        if self._presets is None:
            self._presets = preset_catalog()
        return self._presets

    def patches(self) -> dict[str, Any]:
        from vidgen.studio import patch_catalog

        return patch_catalog()

    # ----- sessions and versions ----------------------------------------------------------

    def load(self, preset: str | None = None, text: str | None = None, title: str | None = None) -> dict[str, Any]:
        """Start a new session from a preset (a built-in bed's template) or from score ``text``;
        its version 1 is that score. Bad text is refused with its problems (no session)."""
        from vidgen.studio import music_template_text

        if (preset is None) == (text is None):
            raise VidgenError("load: give a preset or a score's text")
        if preset is not None:
            text = music_template_text(preset)  # an unknown preset: the error with did-you-mean
        assert text is not None
        data, score, problems = check_text(text)
        if score is None:
            raise VidgenError("load: the score has problems:\n" + "\n".join(f"  - {p['where']}: {p['message']}" for p in problems))
        with self._lock:
            name = title or score.title or (preset or "untitled")
            self.session = StudioSession.create(self.studio, preset, name)
            label = f"the {preset} template" if preset else "the score given"
            self.session.add_version(text, "preset" if preset else "text", label, None)
            if self.url is not None:
                write_open_marker(self.studio, self.url, self.session.id)
            return self.state()

    def state(self) -> dict[str, Any]:
        """The open session (``null`` when none) and its current version's score."""
        with self._lock:
            if self.session is None:
                return {"session": None, "score": None}
            current = self.session.current
            return {"session": self.session.to_json(), "score": self.score(current) if current is not None else None}

    def score(self, version: int) -> dict[str, Any]:
        """Version ``version`` of the open session: its text, facts and problems."""
        session = self._session()
        text = session.text(version)
        data, score, problems = check_text(text)
        outline = describe_score(score, data) if score is not None else None
        return {"version": version, "text": text, "outline": outline, "problems": problems, "render_key": render_key(data) if score is not None else None}

    def validate(self, text: str) -> dict[str, Any]:
        """Check score ``text`` (nothing written): ``ok``, its problems and, when ok, its facts."""
        data, score, problems = check_text(text)
        return {"ok": score is not None, "problems": problems, "outline": describe_score(score, data) if score is not None else None}

    def _session(self) -> StudioSession:
        if self.session is None:
            raise VidgenError("no score is open: load a preset first")
        return self.session

    # ----- edits ----------------------------------------------------------------------------

    def edit(self, version: int | None, ops: Sequence[Mapping[str, Any]], label: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        """Apply the edits ``ops`` to version ``version`` of the open session (default: the
        current one). A valid result becomes the next version (``origin: edit``, its parent the
        version edited) and the session's current one: ``{ok: true, session, score}``. A result
        with problems writes nothing: ``{ok: false, problems}`` (the page shows them by the
        control; the last good version keeps playing). ``dry_run``: check only (``{ok,
        problems, outline}``). Besides :mod:`vidgen.studio_app.edits`' ops: ``add_track``
        (``instrument``, ``name``?), ``delete_track`` (``name``), ``add_section`` (``after``,
        ``name``?, ``bars``?), ``remove_section`` (``name``), ``rename_section`` (``name``,
        ``to``)."""
        if not isinstance(ops, Sequence) or not ops:
            raise VidgenError("edit: give a list of edits (ops)")
        with self._lock:
            session = self._session()
            base = version if version is not None else session.current
            assert base is not None
            text = session.text(base)
            new_text, labels = _apply_ops(text, ops)
            data, score, problems = check_text(new_text)
            if dry_run or score is None:
                return {"ok": score is not None, "problems": problems, "outline": describe_score(score, data) if score is not None else None}
            if new_text == text:
                return {"ok": True, "unchanged": True, **self.state()}
            session.add_version(new_text, "edit", (label or "; ".join(labels) or "an edit")[:120], base)
            return {"ok": True, **self.state()}

    # ----- rendering ----------------------------------------------------------------------

    def render(self, version: int | None = None, section: str | None = None, mute: Sequence[str] = ()) -> dict[str, Any]:
        """Render a version of the open session (default: the current one), or one section of
        it, into the render cache (reused when the notes are unchanged). The section is cut from
        the whole piece's render, so it sounds as in the piece (tails from before it).
        ``mute``: tracks left out of what plays — a listening mix (§94.12), never the score;
        names that are not tracks are ignored."""
        from vidgen.sfx import RATE

        session = self._session()
        number = version if version is not None else session.current
        assert number is not None
        data, score, problems = check_text(session.text(number))
        if score is None:
            raise VidgenError(f"version {number} has problems; fix them before playing it")
        key = render_key(data)
        meta = self._render_whole(session, key, score)
        muted = sorted(set(mute) & {t.name for t in score.tracks})
        name = f"{key}.m{mute_tag(muted)}" if muted else key
        if muted:
            self._render_mix(session, name, score, muted, meta["samples"])
        result = {"version": number, "key": key, **meta, "url": f"/audio/{name}.wav", "section": None, "muted": muted}
        if section is not None:
            found = next((s for s in score.sections if s.name == section), None)
            if found is None:
                names = ", ".join(s.name for s in score.sections)
                raise VidgenError(f"render: no section '{section}' (sections: {names})")
            first = score.section_start(found)
            last = found is score.sections[-1]
            count = (meta["samples"] - first) if last else found.bars * score.bar
            target = session.renders / f"{name}-{section}.wav"
            if not target.is_file():
                _slice_wav(session.renders / f"{name}.wav", target, first, count)
            result.update(url=f"/audio/{target.name}", section={"name": section, "start": first / RATE, "seconds": count / RATE})
        return result

    def _render_mix(self, session: StudioSession, name: str, score: Any, muted: Sequence[str], samples: int) -> None:
        """The listening mix ``name`` without the ``muted`` tracks: the other tracks' stems summed,
        through the master filter, at the whole piece's gain (muting a part does not make the
        rest louder). Step 196 caches the stems; here each mix renders them again."""
        from vidgen.music import _tone_filter
        from vidgen.sfx import wav_bytes
        from vidgen.studio.render import render_music_stems

        path = session.renders / f"{name}.wav"
        with self._render_lock:
            if path.is_file():
                return
            kept: list[np.ndarray] = []

            def keep(track: str, stem: np.ndarray) -> None:
                if track not in muted:
                    if kept:
                        kept[0] = kept[0] + stem
                    else:
                        kept.append(np.array(stem, dtype=np.float64))

            _, gain = render_music_stems(score, keep)
            mix = kept[0] if kept else np.zeros((score.samples, 2))
            mix = _tone_filter(mix, score.lowpass, score.highpass) * gain
            if len(mix) < samples:  # a one-shot's tail after its last bar
                mix = np.concatenate([mix, np.zeros((samples - len(mix), 2))])
            level = 10 ** (audition_gain_db() / 20)
            write_bytes_atomic(path, wav_bytes(np.clip(mix[:samples] * level, -1.0, 1.0)))

    def _render_whole(self, session: StudioSession, key: str, score: Any) -> dict[str, Any]:
        """The cached render ``key`` (rendered now if missing): its facts."""
        from vidgen import loudness
        from vidgen.sfx import RATE, wav_bytes
        from vidgen.studio import render_music_score
        from vidgen.studio.measure import loudness_curve

        meta_path, wav_path = session.renders / f"{key}.json", session.renders / f"{key}.wav"
        with self._render_lock:
            if meta_path.is_file() and wav_path.is_file():
                return {**json.loads(meta_path.read_text(encoding="utf-8")), "cached": True}
            began = time.perf_counter()
            warnings: list[str] = []
            audio = render_music_score(score, warnings)
            render_seconds = time.perf_counter() - began
            meter = loudness.measure(len(audio), lambda a, b: audio[a:b])
            energy = [round(v, 1) if math.isfinite(v) and v > ENERGY_FLOOR else ENERGY_FLOOR for v in loudness_curve(audio[: score.samples], score.bar)]
            gain = 10 ** (audition_gain_db() / 20)
            write_bytes_atomic(wav_path, wav_bytes(np.clip(audio * gain, -1.0, 1.0)))
            meta = {
                "seconds": round(len(audio) / RATE, 3),
                "samples": len(audio),
                "loop": score.loop,
                "loudness": round(meter.integrated, 2),
                "true_peak": round(meter.true_peak, 2),
                "audition_gain_db": audition_gain_db(),
                "warnings": warnings,
                "render_seconds": round(render_seconds, 2),
                "energy": energy,
            }
            write_text_atomic(meta_path, json.dumps(meta, indent=2) + "\n")
            return {**meta, "cached": False}

    def audio_file(self, name: str) -> Path | None:
        """The rendered file ``name`` of the open session, or ``None`` (an unknown or malformed
        name never reaches the file system beyond the render folder)."""
        if self.session is None or not AUDIO_NAME.match(name):
            return None
        path = self.session.renders / name
        return path if path.is_file() else None
