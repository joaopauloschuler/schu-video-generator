"""``vidgen readback``: does the narration say what the text says? (DESIGN.md §57)

Each beat's MP3 is transcribed by a speech-to-text provider (:mod:`vidgen.stt`), the transcript
is compared with the beat's **spoken** text (its text with the pronunciation applied: what the
TTS was asked to say), and the differences are reported in terms of the **written** text: a
word error rate per beat, the words expected and heard, and a suggested fix (a pronunciation
entry for a term the voice gets wrong, regenerating a beat that lost words...).

- Both texts are normalised by :func:`vidgen.textnorm.normalize_words` (case, punctuation,
  accents, numbers, hyphens), aligned word by word (:func:`align`, Levenshtein), and the
  differences grouped into :class:`Edit` objects covering whole written words. A difference
  that disappears when the words are joined (``over parameterized`` / ``overparameterized``)
  or when the STT wrote the term as written (``K-Phi-3`` for a beat that says ``kay fye three``)
  is not an error.
- Transcripts are cached in ``build/readback/<key>.json``, keyed by the MP3's content and the
  STT settings (:func:`vidgen.stt.stt_settings`): a beat is transcribed again only when its audio
  or the settings change. The ``readback`` lint rule reads only this cache.

No manim import.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.stt import STTProvider, Transcript, stt_settings
from vidgen.textnorm import Token, normalize_text, normalize_words

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.pronunciation import Spoken

#: Version of the transcript cache files.
CACHE_VERSION = 1

OpName = Literal["equal", "substitute", "delete", "insert"]
EditKind = Literal["substitution", "deletion", "insertion"]


# ----- alignment --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Op:
    """One step of an alignment: ``ref`` / ``hyp`` are token indices (``None`` for the side an
    insertion / deletion does not have)."""

    op: OpName
    ref: int | None
    hyp: int | None


def align(ref: Sequence[str], hyp: Sequence[str]) -> list[Op]:
    """The alignment of ``hyp`` (heard) to ``ref`` (expected) with the fewest substitutions,
    deletions and insertions (Levenshtein, each costing 1); among those, the one matching the
    most words, then substitutions before deletions. Ops are in order of the texts."""
    n, m = len(ref), len(hyp)
    # cost[i][j] = (edits, -matches) of aligning ref[:i] with hyp[:j]
    cost = [[(0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = (i, 0)
    for j in range(1, m + 1):
        cost[0][j] = (j, 0)

    def diagonal(i: int, j: int) -> tuple[int, int]:
        e, neg = cost[i - 1][j - 1]
        return (e, neg - 1) if ref[i - 1] == hyp[j - 1] else (e + 1, neg)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            up, left = cost[i - 1][j], cost[i][j - 1]
            cost[i][j] = min(diagonal(i, j), (up[0] + 1, up[1]), (left[0] + 1, left[1]))
    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == diagonal(i, j):
            ops.append(Op("equal" if ref[i - 1] == hyp[j - 1] else "substitute", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == (cost[i - 1][j][0] + 1, cost[i - 1][j][1]):
            ops.append(Op("delete", i - 1, None))
            i -= 1
        else:
            ops.append(Op("insert", None, j - 1))
            j -= 1
    ops.reverse()
    return ops


def word_error_rate(ref: Sequence[str], hyp: Sequence[str]) -> float:
    """(substitutions + deletions + insertions) / words of ``ref`` (0 for two empty texts, 1 per
    heard word when nothing was expected)."""
    errors = sum(1 for op in align(ref, hyp) if op.op != "equal")
    return errors / len(ref) if ref else float(errors)


# ----- comparing a beat -------------------------------------------------------------------------


@dataclass
class Edit:
    """A difference between what a beat says and what was heard, covering whole written words.

    ``expected`` / ``heard`` are the normalised words; ``written`` the beat's words as written
    (empty for words heard where nothing was expected; ``after`` then names the written word
    before them), ``said`` the spoken form when a pronunciation entry changed them; ``errors``
    the substitutions + deletions + insertions; ``at`` when the heard words start in the MP3
    (seconds, ``None`` without word times); ``term`` the written term a fix is about (a
    pronunciation entry's term, a name, acronym or number), ``entry`` true when it has a
    pronunciation entry; ``suggestion`` what to do."""

    kind: EditKind
    expected: str
    heard: str
    written: str
    said: str | None
    errors: int
    at: float | None = None
    after: str | None = None
    term: str | None = None
    entry: bool = False
    suggestion: str = ""

    def to_json(self) -> dict[str, Any]:
        """``{kind, expected, heard, written, said, after, errors, at, term, entry, suggestion}``."""
        return {
            "kind": self.kind,
            "expected": self.expected,
            "heard": self.heard,
            "written": self.written,
            "said": self.said,
            "after": self.after,
            "errors": self.errors,
            "at": None if self.at is None else round(self.at, 3),
            "term": self.term,
            "entry": self.entry,
            "suggestion": self.suggestion,
        }

    def describe(self) -> str:
        """``expected "K-Phi-3" (said "kay fye three") heard "k five three"``."""
        if self.kind == "insertion" and not self.written:
            where = f' after "{self.after}"' if self.after else " at the start"
            return f'heard extra "{self.heard}"{where}'
        said = f' (said "{self.said}")' if self.said else ""
        heard = f'"{self.heard}"' if self.heard else "nothing"
        return f'expected "{self.written}"{said}, heard {heard}'


@dataclass
class BeatReadback:
    """The comparison of one beat's text with what its MP3 says."""

    scene: str
    beat: str
    text: str
    spoken: str
    heard: str
    words: int
    errors: int
    counts: dict[str, int]
    edits: list[Edit]
    audio: str = "ok"
    cached: bool = False
    flagged: bool = False
    suggestions: list[str] = field(default_factory=list)

    @property
    def wer(self) -> float:
        """Word error rate: errors / words of the spoken text."""
        return self.errors / self.words if self.words else float(self.errors)

    def to_json(self) -> dict[str, Any]:
        """The beat in ``vidgen readback --json``."""
        return {
            "scene": self.scene,
            "beat": self.beat,
            "audio": self.audio,
            "cached": self.cached,
            "wer": round(self.wer, 4),
            "words": self.words,
            "errors": self.errors,
            **self.counts,
            "flagged": self.flagged,
            "text": self.text,
            "spoken": self.spoken,
            "heard": self.heard,
            "edits": [e.to_json() for e in self.edits],
            "suggestions": list(self.suggestions),
        }


_EDGE = ".,;:!?\"'()[]{}…“”‘’«»¿¡"
_SENTENCE_END = re.compile(r"[.!?…:][\"'”’)\]]*$")


def _core(word: str) -> str:
    core = word.strip(_EDGE)
    for suffix in ("'s", "’s"):
        if core.endswith(suffix):
            core = core[: -len(suffix)]
    return core


def hard_term(words: Sequence[str], index: int) -> bool:
    """Whether written word ``index`` is the kind of term a voice may say wrongly and a
    pronunciation entry can fix: one with a digit, two capitals (``GPU``, ``LaMini``), a letter
    outside ASCII (``João``), or a capitalised word inside a sentence (a name)."""
    core = _core(words[index])
    if not core or not any(ch.isalnum() for ch in core):
        return False
    if any(ch.isdigit() for ch in core) or sum(ch.isupper() for ch in core) >= 2:
        return True
    if any(ch.isalpha() and not ch.isascii() for ch in core):
        return True
    starts_sentence = index == 0 or bool(_SENTENCE_END.search(words[index - 1]))
    return core[0].isupper() and not starts_sentence and core.lower() not in ("i", "i'm", "i've", "i'll", "i'd")


def _invert_groups(spoken: Spoken, count: int) -> list[int]:
    """Spoken word index -> the written word it says (the nearest earlier one for a word no
    written word claims)."""
    owner = [-1] * count
    for w, group in enumerate(spoken.word_groups()):
        for s in group:
            if 0 <= s < count and owner[s] == -1:
                owner[s] = w
    last = 0
    for s in range(count):
        if owner[s] == -1:
            owner[s] = last
        last = owner[s]
    return owner


def _entries_by_word(spoken: Spoken) -> dict[int, str]:
    """Written word index -> the pronunciation entry replaced in it."""
    out: dict[int, str] = {}
    for w, match in enumerate(re.finditer(r"\S+", spoken.text)):
        for r in spoken.replacements:
            if r.start < match.end() and r.end > match.start():
                out.setdefault(w, r.term)
    return out


def _says(spoken: Spoken, term: str) -> str | None:
    for r in spoken.replacements:
        if r.term == term:
            return spoken.spoken[r.spoken_start : r.spoken_end]
    return None


def _op_words(ops: Sequence[Op], ref_words: Sequence[int]) -> list[int]:
    """The written word each op belongs to: its expected token's; inserted words go with the
    next word when that one is heard differently too ("NVIDIA" heard "and video"), else with the
    word before (the first word at the start)."""
    out: list[int] = []
    for k, op in enumerate(ops):
        if op.ref is not None:
            out.append(ref_words[op.ref])
            continue
        nxt = next(((o.ref, o.op) for o in ops[k + 1 :] if o.ref is not None), None)
        prev = out[-1] if out else None
        if nxt is not None and (prev is None or nxt[1] != "equal"):
            out.append(ref_words[nxt[0]])
        else:
            out.append(prev if prev is not None else 0)
    return out


def compare_beat(
    scene: str,
    beat: str,
    spoken: Spoken,
    transcript: Transcript,
    language: str | None = None,
) -> BeatReadback:
    """Compare a beat (its :class:`~vidgen.pronunciation.Spoken` text) with a transcript of its
    MP3: normalised words aligned, differences grouped by written word (see the module
    docstring), each with a suggestion."""
    written_words = spoken.text.split()
    spoken_words = spoken.spoken.split()
    ref = normalize_words(spoken_words, language)
    heard_words = transcript.word_texts()
    times = transcript.word_times()
    hyp = normalize_words(heard_words, language)
    owner = _invert_groups(spoken, len(spoken_words))
    entries = _entries_by_word(spoken)

    ops = align([t.text for t in ref], [t.text for t in hyp])
    word_of = _op_words(ops, [owner[t.source] for t in ref])

    edits: list[Edit] = []
    counts = {"substitutions": 0, "deletions": 0, "insertions": 0}
    k = 0
    while k < len(ops):
        # a block = the ops of consecutive written words with a difference
        w0 = word_of[k]
        end = k
        while end < len(ops) and word_of[end] == w0:
            end += 1
        if all(op.op == "equal" for op in ops[k:end]):
            k = end
            continue
        while end < len(ops):
            nxt = end
            while nxt < len(ops) and word_of[nxt] == word_of[end]:
                nxt += 1
            if all(op.op == "equal" for op in ops[end:nxt]):
                break
            end = nxt
        block = ops[k:end]
        edit = _edit(block, ref, hyp, written_words, spoken_words, owner, word_of[k], word_of[end - 1], times, entries, spoken, language)
        if edit is not None:
            edits.append(edit)
            for op in block:
                if op.op == "substitute":
                    counts["substitutions"] += 1
                elif op.op == "delete":
                    counts["deletions"] += 1
                elif op.op == "insert":
                    counts["insertions"] += 1
        k = end
    return BeatReadback(scene, beat, spoken.text, spoken.spoken, transcript.text, len(ref), sum(counts.values()), counts, edits)


def _edit(
    block: Sequence[Op],
    ref: Sequence[Token],
    hyp: Sequence[Token],
    written_words: Sequence[str],
    spoken_words: Sequence[str],
    owner: Sequence[int],
    w_first: int,
    w_last: int,
    times: Sequence[tuple[float, float] | None],
    entries: dict[int, str],
    spoken: Spoken,
    language: str | None,
) -> Edit | None:
    expected = [ref[op.ref].text for op in block if op.ref is not None]
    heard = [hyp[op.hyp].text for op in block if op.hyp is not None]
    has_ref = bool(expected)
    written = " ".join(written_words[w_first : w_last + 1]).strip(_EDGE) if has_ref else ""
    # not a difference in speech: words joined or split, or the STT wrote the term as written
    if "".join(expected) == "".join(heard):
        return None
    if written and "".join(normalize_text(written, language)) == "".join(heard):
        return None
    kinds = {op.op for op in block if op.op != "equal"}
    kind: EditKind = "insertion" if kinds == {"insert"} else "deletion" if kinds == {"delete"} else "substitution"
    errors = sum(1 for op in block if op.op != "equal")
    said_words = [spoken_words[s] for s in range(len(spoken_words)) if w_first <= owner[s] <= w_last] if has_ref else []
    said = " ".join(said_words).strip(_EDGE)
    # when the difference is heard: its first differing word heard, else the block's first
    sources = [hyp[op.hyp].source for op in block if op.hyp is not None and op.op != "equal"]
    sources += [hyp[op.hyp].source for op in block if op.hyp is not None and op.op == "equal"]
    at = next((t[0] for t in (times[s] for s in sources if s < len(times)) if t is not None), None)
    edit = Edit(kind, " ".join(expected), " ".join(heard), written, said if said and said != written else None, errors, at)
    if not has_ref and written_words:
        edit.after = written_words[w_first]
    # an extra word heard next to a term says nothing about how the term is said
    words = range(w_first, w_last + 1) if has_ref and kind != "insertion" else range(0)
    entry = next((entries[w] for w in words if w in entries), None)
    if entry is not None:
        edit.term, edit.entry = entry, True
    else:
        hard = next((w for w in words if hard_term(written_words, w)), None)
        if hard is not None:
            edit.term = _core(written_words[hard])
    edit.suggestion = _suggestion(edit, spoken)
    return edit


def _suggestion(edit: Edit, spoken: Spoken) -> str:
    heard = f'"{edit.heard}"' if edit.heard else "nothing"
    if edit.entry and edit.term is not None:
        says = _says(spoken, edit.term)
        return (
            f'the pronunciation entry "{edit.term}" (says "{says}") is heard as {heard}: respell its spoken form '
            "(other letters, syllables split by hyphens), then `vidgen tts`"
        )
    if edit.term is not None:
        how = "the number in words" if any(ch.isdigit() for ch in edit.term) else "how to say it"
        return f'"{edit.term}" is heard as {heard}: add a pronunciation entry `{edit.term}: <{how}>`, then `vidgen tts`'
    if edit.kind == "deletion":
        return "words missing from the audio (or from the transcript): listen to the beat; regenerate it (`vidgen tts --force --beat <id>`) if they are not said"
    if edit.kind == "insertion":
        return "extra words heard: listen to the beat; regenerate it if the voice added them (or the transcription did)"
    return "heard differently: may be a transcription slip; listen to the beat and regenerate it if the voice is wrong"


def beat_suggestions(result: BeatReadback) -> list[str]:
    """What to do about a beat: the edits' suggestions (once each, the beat id filled in), a
    note first when the audio is stale."""
    out: list[str] = []
    if result.audio == "stale":
        out.append(f"the audio is stale (the text or voice changed since it was generated): run `vidgen tts --beat {result.beat}` and readback again")
    for edit in result.edits:
        text = edit.suggestion.replace("<id>", result.beat)
        if text not in out:
            out.append(text)
    return out


# ----- terms across beats -----------------------------------------------------------------------


@dataclass
class TermReport:
    """A written term heard differently in one or more beats."""

    term: str
    entry: bool
    beats: list[str] = field(default_factory=list)
    heard: list[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        """Heard differently in at least two beats: likely the voice, not a transcription slip."""
        return len(self.beats) >= 2

    @property
    def suggestion(self) -> str:
        """What to do about it."""
        where = f"in {len(self.beats)} beats" if self.consistent else f"in beat {self.beats[0]}"
        if self.entry:
            return f'"{self.term}" is misheard {where} despite its pronunciation entry: respell the entry\'s spoken form'
        return f'"{self.term}" is misheard {where}: add a pronunciation entry `{self.term}: <how to say it>`'

    def to_json(self) -> dict[str, Any]:
        """``{term, entry, beats, heard, consistent, suggestion}``."""
        return {
            "term": self.term,
            "entry": self.entry,
            "beats": list(self.beats),
            "heard": list(self.heard),
            "consistent": self.consistent,
            "suggestion": self.suggestion,
        }


def term_reports(results: Iterable[BeatReadback]) -> list[TermReport]:
    """Terms heard differently, most beats first (then in video order)."""
    terms: dict[str, TermReport] = {}
    for result in results:
        for edit in result.edits:
            if edit.term is None:
                continue
            report = terms.setdefault(edit.term, TermReport(edit.term, edit.entry))
            if result.beat not in report.beats:
                report.beats.append(result.beat)
            if edit.heard not in report.heard:
                report.heard.append(edit.heard)
    return sorted(terms.values(), key=lambda t: -len(t.beats))


# ----- transcript cache -------------------------------------------------------------------------


def audio_digest(path: Path) -> str:
    """sha1 of a file's bytes."""
    return hashlib.sha1(path.read_bytes()).hexdigest()


def cache_path(project: Project, digest: str, settings: dict[str, Any]) -> Path:
    """``build/readback/<sha1(audio sha1 + settings)>.json``: the transcript of that audio with
    those STT settings (shared by variants with the same audio)."""
    key = hashlib.sha1(json.dumps({"audio": digest, **settings}, sort_keys=True).encode("utf-8")).hexdigest()
    return project.build_dir / "readback" / f"{key}.json"


def read_cached(path: Path, digest: str, settings: dict[str, Any]) -> Transcript | None:
    """The cached transcript at ``path`` when it is of that audio and settings, else ``None``."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("version") != CACHE_VERSION or doc.get("audio_sha1") != digest or doc.get("stt") != settings:
        return None
    try:
        return Transcript.from_json(doc["transcript"])
    except (ValueError, KeyError, TypeError):
        return None


def write_cached(path: Path, digest: str, settings: dict[str, Any], transcript: Transcript, beat: str) -> None:
    """Store a transcript (``beat``: the beat it was made for, informative only)."""
    doc = {"version": CACHE_VERSION, "audio_sha1": digest, "stt": settings, "beat": beat, "transcript": transcript.to_json()}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(doc, ensure_ascii=False, indent=1))


# ----- the command ------------------------------------------------------------------------------


@dataclass
class ReadbackResult:
    """What :func:`run_readback` found: compared beats (video order), skipped beats
    ``(beat, reason)``, how many were transcribed now / read from the cache."""

    settings: dict[str, Any]
    max_wer: float
    beats: list[BeatReadback] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    transcribed: int = 0
    cached: int = 0

    @property
    def flagged(self) -> list[BeatReadback]:
        """Beats above ``max_wer``, in video order."""
        return [b for b in self.beats if b.flagged]

    @property
    def wer(self) -> float:
        """Errors / words over all compared beats."""
        words = sum(b.words for b in self.beats)
        return sum(b.errors for b in self.beats) / words if words else 0.0

    def worst(self, count: int = 5) -> list[BeatReadback]:
        """The beats with the highest word error rate (with errors), worst first."""
        ranked = sorted((b for b in self.beats if b.errors), key=lambda b: -b.wer)
        return ranked[:count]

    def terms(self) -> list[TermReport]:
        """Terms heard differently (:func:`term_reports`)."""
        return term_reports(self.beats)


def _beats_with_audio(project: Project, beat_ids: Sequence[str]) -> tuple[list[tuple[str, str, Path, str]], list[tuple[str, str]]]:
    """``(scene, beat, mp3, audio state)`` of the selected beats that have an MP3, and the
    skipped ``(beat, reason)``."""
    from vidgen import tts

    known = [beat.id for _, beat in project.beats()]
    unknown = [b for b in beat_ids if b not in known]
    if unknown:
        raise VidgenError(f"unknown beat(s): {', '.join(unknown)}")
    chosen, skipped = [], []
    for status in tts.audio_status(project):
        if beat_ids and status.beat_id not in beat_ids:
            continue
        if status.state == "missing":
            skipped.append((status.beat_id, "no audio (run `vidgen tts`)"))
        else:
            chosen.append((status.scene_id, status.beat_id, status.mp3, status.state))
    return chosen, skipped


def run_readback(
    project: Project,
    *,
    beat_ids: Sequence[str] = (),
    force: bool = False,
    max_wer: float | None = None,
    provider: STTProvider | None = None,
    log: Callable[[str], None] = print,
) -> ReadbackResult:
    """Transcribe the beats' MP3s (``beat_ids``: only these) that have no cached transcript
    (``force``: all), compare each with its spoken text and flag those above ``max_wer``
    (default ``lint.rules.readback.max_wer``). ``provider`` replaces the configured one
    (tests). Progress lines go to ``log``."""
    from vidgen.stt import get_stt_provider

    settings = stt_settings(project)
    threshold = project.config.lint.rules.readback.max_wer if max_wer is None else max_wer
    if not 0 <= threshold < 1:
        raise VidgenError("--max-wer must be at least 0 and below 1")
    chosen, skipped = _beats_with_audio(project, beat_ids)
    result = ReadbackResult(settings, threshold, skipped=skipped)
    pending: list[tuple[int, str, Path, Path, str]] = []
    transcripts: dict[str, Transcript] = {}
    for scene, beat, mp3, _state in chosen:
        digest = audio_digest(mp3)
        path = cache_path(project, digest, settings)
        cached = None if force else read_cached(path, digest, settings)
        if cached is not None:
            transcripts[beat] = cached
            result.cached += 1
        else:
            pending.append((len(pending), beat, mp3, path, digest))
    if pending:
        stt = provider if provider is not None else get_stt_provider(project)
        stt.check_available()
        for n, beat, mp3, path, digest in pending:
            started = time.monotonic()
            transcript = stt.transcribe(mp3)
            write_cached(path, digest, settings, transcript, beat)
            transcripts[beat] = transcript
            result.transcribed += 1
            log(f"[{n + 1}/{len(pending)}] transcribed {beat} ({time.monotonic() - started:.1f} s)")
    language = project.config.language
    for scene, beat, _mp3, state in chosen:
        compared = compare_beat(scene, beat, project.pronunciation.apply(project.beat(beat).text), transcripts[beat], language)
        compared.audio = state
        compared.cached = beat not in {p[1] for p in pending}
        compared.flagged = compared.wer > threshold
        compared.suggestions = beat_suggestions(compared) if compared.edits else []
        result.beats.append(compared)
    return result


def cached_readback(project: Project, beat_ids: Iterable[str]) -> dict[str, BeatReadback]:
    """Comparisons of the beats whose current MP3 has a cached transcript for the project's STT
    settings (the ``readback`` lint rule: never transcribes). Not flagged; the caller applies
    its threshold."""
    settings = stt_settings(project)
    audio_dir = project.audio_dir
    out: dict[str, BeatReadback] = {}
    scenes = {beat.id: scene.id for scene, beat in project.beats()}
    for beat_id in beat_ids:
        mp3 = audio_dir / f"{beat_id}.mp3"
        if beat_id not in scenes or not mp3.is_file():
            continue
        digest = audio_digest(mp3)
        transcript = read_cached(cache_path(project, digest, settings), digest, settings)
        if transcript is None:
            continue
        spoken = project.pronunciation.apply(project.beat(beat_id).text)
        compared = compare_beat(scenes[beat_id], beat_id, spoken, transcript, project.config.language)
        compared.cached = True
        compared.suggestions = beat_suggestions(compared) if compared.edits else []
        out[beat_id] = compared
    return out


# ----- human report -----------------------------------------------------------------------------


def report_lines(result: ReadbackResult) -> list[str]:
    """The human ``vidgen readback`` output: settings and counts, each flagged beat with its
    differences and suggestions, the worst beats, terms misheard in several beats."""
    s = result.settings
    beats = result.beats
    lines = [
        f"readback: {len(beats)} beat{'s' if len(beats) != 1 else ''} ({s['provider']} {s['model']}, "
        f"language {s['language'] or 'auto'}); {result.transcribed} transcribed, {result.cached} cached; "
        f"word error rate {result.wer:.1%}"
    ]
    for beat, reason in result.skipped:
        lines.append(f"  skipped {beat}: {reason}")
    flagged = result.flagged
    lines.append(f"flagged (word error rate above {result.max_wer:.0%}): {len(flagged)}")
    for b in flagged:
        stale = " [audio stale]" if b.audio == "stale" else ""
        lines.append(f"  {b.beat} ({b.scene}): {b.wer:.0%} ({b.errors}/{b.words} words){stale}")
        for edit in b.edits:
            at = f" @ {edit.at:.1f}s" if edit.at is not None else ""
            lines.append(f"    {edit.describe()}{at}")
        for suggestion in b.suggestions:
            lines.append(f"    fix: {suggestion}")
    worst = result.worst()
    if worst:
        lines.append("worst: " + ", ".join(f"{b.beat} {b.wer:.0%}" for b in worst))
    terms = [t for t in result.terms() if t.consistent]
    if terms:
        lines.append("terms misheard in several beats:")
        for t in terms:
            heard = ", ".join(f'"{h}"' for h in t.heard[:3])
            lines.append(f"  {t.term}: {len(t.beats)} beats ({', '.join(t.beats)}), heard {heard} -> {t.suggestion}")
    return lines
