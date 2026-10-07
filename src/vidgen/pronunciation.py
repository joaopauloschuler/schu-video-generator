"""Pronunciation dictionary: how the narrator says terms (DESIGN.md §45).

A project's ``pronunciation:`` map (plus the entries of its ``pronunciation_file``) replaces
terms in the text **sent to the TTS only**: ``K-Phi-3`` is written in the subtitles and captions
but sent as ``kay fye three``. The spoken text is what the audio hash covers, so editing an entry
re-voices only the beats it changes; a beat no entry matches keeps its hash.

- :func:`load_pronunciation` builds a :class:`Pronunciation` from a config (reading its files);
  :class:`Pronunciation.apply` gives a :class:`Spoken` text: the original, the spoken form and
  where each replacement went, which :func:`vidgen.speech.map_word_times` uses to time the
  written words by the spoken ones.
- All entries are matched against the original text in one pass (a replacement is never
  matched again). Where matches overlap, the one starting first wins, then the longest, then
  the entry written first; :func:`pronunciation_warnings` reports entries that never match and
  entries that collide.

No manim import (``vidgen.project`` uses it).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import TypeAdapter, ValidationError

from vidgen.config import PronunciationEntry, PronunciationMap, PronunciationValue, validation_problems
from vidgen.errors import Problem, VidgenError

if TYPE_CHECKING:
    from vidgen.config import VideoConfig

_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Rule:
    """One compiled entry: ``term`` as written in the config, its spoken form ``say``, the
    ``pattern`` that finds it and its position ``index`` (ties between equal matches)."""

    term: str
    say: str
    pattern: re.Pattern[str]
    regex: bool
    index: int


def _entry(value: str | PronunciationEntry) -> PronunciationEntry:
    return PronunciationEntry(say=value) if isinstance(value, str) else value


def compile_rule(term: str, value: str | PronunciationEntry, index: int = 0) -> Rule:
    """The :class:`Rule` of one entry; ``ValueError`` for a regex that does not compile, that
    matches the empty string or whose ``say`` refers to a group it does not have."""
    entry = _entry(value)
    flags = 0 if entry.case_sensitive else re.IGNORECASE
    if entry.regex:
        body = f"(?:{term})"
        if entry.whole_word:
            body = rf"(?<!\w){body}(?!\w)"
    else:
        body = re.escape(term)
        if entry.whole_word:
            body = (r"(?<!\w)" if re.match(r"\w", term) else "") + body + (r"(?!\w)" if re.search(r"\w$", term) else "")
    try:
        pattern = re.compile(body, flags)
    except re.error as exc:
        raise ValueError(f"'{term}' is not a valid regular expression: {exc}") from None
    if entry.regex:
        try:
            pattern.sub(entry.say, "")  # the template is parsed up front: bad group references fail here
        except (re.error, IndexError) as exc:
            raise ValueError(f"'{term}': say {entry.say!r} is not a valid replacement: {exc}") from None
        if pattern.fullmatch(""):
            raise ValueError(f"'{term}' matches the empty string")
    return Rule(term, entry.say, pattern, entry.regex, index)


def form_problems(data: Mapping[object, object]) -> list[str]:
    """Messages for raw entries (as written) that are neither a spoken form nor a valid long
    form, one per mistake (pydantic's union errors would list every branch)."""
    problems = []
    for term, value in data.items():
        if not isinstance(term, str) or not term:
            problems.append(f"{term!r}: a term must be non-empty text")
        elif isinstance(value, dict):
            try:
                PronunciationEntry.model_validate(value)
            except ValidationError as exc:
                problems.extend(f"'{term}': {p}" for p in validation_problems(exc, model=PronunciationEntry, noun="key"))
        elif value is not None and not isinstance(value, str):
            problems.append(f"'{term}': must be the spoken form (text) or a mapping {{say, case_sensitive, whole_word, regex, language}}")
    return problems


def entry_problems(entries: Mapping[str, PronunciationValue]) -> list[str]:
    """Messages for entries that do not compile (``term: message``)."""
    problems = []
    for term, value in entries.items():
        if value is None:
            continue
        try:
            compile_rule(term, value)
        except ValueError as exc:
            problems.append(str(exc))
    return problems


# ----- spoken text ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Replacement:
    """A term replaced in a text: ``text[start:end]`` (the original) became
    ``spoken[spoken_start:spoken_end]``."""

    term: str
    start: int
    end: int
    spoken_start: int
    spoken_end: int


@dataclass(frozen=True)
class Conflict:
    """A match of ``term`` dropped because a match of ``winner`` covers it: ``inside`` (the
    winner is longer and holds it), ``overlap`` (they cross) or ``same`` (the same span)."""

    term: str
    winner: str
    kind: Literal["inside", "overlap", "same"]
    matched: str


@dataclass(frozen=True)
class Spoken:
    """A text and what the narrator says for it.

    ``text`` is the original (subtitles, captions), ``spoken`` the text sent to the TTS,
    ``replacements`` where they differ (in order), ``matched`` every entry that matched
    (winning or not) and ``conflicts`` the matches dropped for an overlapping one.
    """

    text: str
    spoken: str
    replacements: tuple[Replacement, ...] = ()
    matched: frozenset[str] = frozenset()
    conflicts: tuple[Conflict, ...] = ()

    @property
    def changed(self) -> bool:
        """True when the TTS gets something else than the written text."""
        return self.spoken != self.text

    def _spoken_pos(self, pos: int, end: bool) -> int:
        """Where original character ``pos`` is in the spoken text (``end``: the position after
        it). Inside a replacement: the replacement's start / end."""
        shift = 0
        for r in self.replacements:
            if pos < r.start:
                break
            if pos < r.end:
                return r.spoken_end if end else r.spoken_start
            shift += (r.spoken_end - r.spoken_start) - (r.end - r.start)
        return pos + shift + (1 if end else 0)

    def word_groups(self) -> list[list[int]]:
        """For each word of ``text`` (``str.split()``), the indices of the words of ``spoken``
        it is said as: ``K-Phi-3`` -> ``kay fye three`` gives three indices; a term said as
        nothing gives none; words that one replacement joins share theirs."""
        spoken_words = [(m.start(), m.end()) for m in _WORD.finditer(self.spoken)]
        groups = []
        for m in _WORD.finditer(self.text):
            lo, hi = self._spoken_pos(m.start(), False), self._spoken_pos(m.end() - 1, True)
            groups.append([i for i, (a, b) in enumerate(spoken_words) if a < hi and b > lo])
        return groups


class Pronunciation:
    """The compiled pronunciation entries of a project (empty: every text is said as written)."""

    def __init__(self, rules: Sequence[Rule] = ()) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules)

    def __bool__(self) -> bool:
        return bool(self.rules)

    def apply(self, text: str) -> Spoken:
        """``text`` with every entry replaced (see the module docstring for overlaps)."""
        if not self.rules:
            return Spoken(text, text)
        found: list[tuple[int, int, Rule, re.Match[str]]] = []
        for rule in self.rules:
            found.extend((m.start(), m.end(), rule, m) for m in rule.pattern.finditer(text) if m.end() > m.start())
        found.sort(key=lambda f: (f[0], -(f[1] - f[0]), f[2].index))
        chosen: list[tuple[int, int, Rule, re.Match[str]]] = []
        conflicts = []
        for item in found:
            start, end, rule, match = item
            if chosen and start < chosen[-1][1]:
                w_start, w_end, winner, _ = chosen[-1]
                if winner is not rule:
                    kind: Literal["inside", "overlap", "same"]
                    if (start, end) == (w_start, w_end):
                        kind = "same"
                    elif end <= w_end:
                        kind = "inside"
                    else:
                        kind = "overlap"
                    conflicts.append(Conflict(rule.term, winner.term, kind, text[min(start, w_start) : max(end, w_end)]))
                continue
            chosen.append(item)
        pieces: list[str] = []
        replacements = []
        pos = length = 0
        for start, end, rule, match in chosen:
            pieces.append(text[pos:start])
            length += start - pos
            say = match.expand(rule.say) if rule.regex else rule.say
            replacements.append(Replacement(rule.term, start, end, length, length + len(say)))
            pieces.append(say)
            length += len(say)
            pos = end
        pieces.append(text[pos:])
        return Spoken(text, "".join(pieces), tuple(replacements), frozenset(f[2].term for f in found), tuple(conflicts))

    def say(self, text: str) -> str:
        """The text the TTS gets for ``text``."""
        return self.apply(text).spoken


# ----- loading ----------------------------------------------------------------------------------

_MAP = TypeAdapter(PronunciationMap)


def read_pronunciation_file(path: Path, rel: str) -> dict[str, PronunciationValue]:
    """The entries of a pronunciation file (a YAML / JSON mapping ``term: spoken form`` or
    ``term: {say, ...}``); ``VidgenError`` with ``pronunciation_file`` problems if it is
    missing or invalid."""
    from vidgen.project import read_config_file

    where = f"pronunciation_file ({rel})"
    if not path.is_file():
        message = f"file not found: {rel} (looked for {path})"
        raise VidgenError(f"pronunciation_file: {message}", problems=[Problem("pronunciation_file", message)])
    try:
        data = read_config_file(path)
    except VidgenError as exc:
        raise VidgenError(str(exc), problems=[Problem(where, str(exc))]) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        message = "must be a mapping of term: spoken form"
        raise VidgenError(f"{rel}: {message}", problems=[Problem(where, message)])
    messages = form_problems(data)
    if not messages:
        entries = _MAP.validate_python(data)
        messages = entry_problems(entries)
    if messages:
        problems = [Problem(where, m) for m in messages]
        raise VidgenError(f"{rel}: invalid pronunciation entries\n" + "\n".join(f"  {p}" for p in problems), problems=problems)
    return entries


def load_pronunciation(config: VideoConfig, root: Path) -> Pronunciation:
    """The project's entries: those of its ``pronunciation_file``(s) in order, then its
    ``pronunciation:`` map over them (a ``null`` value removes a term); entries with a
    ``language`` other than the video's are left out (DESIGN.md §54)."""
    entries: dict[str, PronunciationValue] = {}
    for rel in config.pronunciation_files:
        entries.update(read_pronunciation_file(root / rel, rel))
    entries.update(config.pronunciation)
    used = [(t, v) for t, v in entries.items() if v is not None and applies_to(v, config.language)]
    rules = [compile_rule(term, value, i) for i, (term, value) in enumerate(used)]
    return Pronunciation(rules)


def applies_to(value: str | PronunciationEntry, language: str | None) -> bool:
    """Whether an entry is used in a video in ``language``: an entry without ``language``
    always; else when one of its languages matches (``pt`` matches ``pt-BR``)."""
    from vidgen.languages import language_matches

    if isinstance(value, str) or value.language is None:
        return True
    wanted = [value.language] if isinstance(value.language, str) else value.language
    return any(language_matches(tag, language) for tag in wanted)


# ----- validate warnings ------------------------------------------------------------------------


def pronunciation_warnings(pronunciation: Pronunciation, beats: Iterable[tuple[str, str]]) -> list[str]:
    """Warnings for ``vidgen validate`` over ``(beat id, text)`` pairs: entries that match no
    beat, entries that never apply because longer ones always cover them, and entries whose
    matches collide (cross or share a span) with another's."""
    if not pronunciation:
        return []
    matched: set[str] = set()
    applied: set[str] = set()
    inside: dict[str, set[str]] = {}
    collisions: dict[tuple[str, str], tuple[str, str, str]] = {}
    for beat_id, text in beats:
        spoken = pronunciation.apply(text)
        matched |= spoken.matched
        applied |= {r.term for r in spoken.replacements}
        for c in spoken.conflicts:
            if c.kind == "inside":
                inside.setdefault(c.term, set()).add(c.winner)
            else:
                collisions.setdefault((c.winner, c.term), (beat_id, c.matched, c.kind))
    out = []
    for rule in pronunciation.rules:
        if rule.term not in matched:
            out.append(f"pronunciation: '{rule.term}' matches no beat's text")
        elif rule.term not in applied and rule.term in inside:
            longer = ", ".join(f"'{t}'" for t in sorted(inside[rule.term]))
            out.append(f"pronunciation: '{rule.term}' never applies: every match is inside a longer entry ({longer})")
    for (winner, loser), (beat_id, text, kind) in collisions.items():
        how = "match the same text" if kind == "same" else "overlap"
        out.append(f"pronunciation: '{winner}' and '{loser}' {how} in beat {beat_id} ({text!r}); '{winner}' is used there")
    return out
