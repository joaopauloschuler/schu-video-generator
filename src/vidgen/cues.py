"""Caption cues: a beat's narration cut into short, readable pieces (DESIGN.md §43).

Both the SRT file (:mod:`vidgen.subtitles`) and burned-in captions (the ``captions`` overlay)
use :func:`segment_cues`, so they show the same pieces: words are grouped into cues of at most
``max_lines`` lines (and ``max_words`` words), breaking where a reader expects a pause — after a
sentence, then after a comma / semicolon / dash, then before a conjunction or a preposition, and
never right after an article or a preposition. Among the ways to cut that fit, the one with
the cheapest breaks wins, with fuller cues and balanced lines preferred. Widths are in any unit
(characters for the SRT, Manim units for captions).

:func:`caption_cues` times the cues from the beat's word times (:mod:`vidgen.speech`): a cue
starts when its first word is spoken and stays until the next cue starts.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.speech import WordTime, estimate_word_times

_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*$")
_CLAUSE_END = re.compile(r"[,;:][\"'”’)\]]*$|[-–—]$")
_DASH = re.compile(r"^[-–—]+$")
_CLEAN = re.compile(r"^[\"'“‘(\[]+|[\"'”’)\].,;:!?…]+$")

#: Words a phrase starts with: a break before them is fine.
CONJUNCTIONS = frozenset(
    "and but or nor so yet because which that who whom whose when where while if then although though unless until since whereas".split()
)
PREPOSITIONS = frozenset("of in on at to for with from by into onto over under about than as like after before between through during without".split())
#: Words that lean on the next one: a break right after them is bad.
CLINGING = frozenset(
    "a an the of in on at to for with from by into onto my your his her its our their this that these those is are was were be very not no".split()
)

#: Costs of a break (cue or line) by where it falls.
COST_SENTENCE = 0.0
COST_CLAUSE = 1.0
COST_CONJUNCTION = 2.0
COST_PREPOSITION = 3.0
COST_PLAIN = 4.5
COST_CLINGING = 9.0
#: Cost of each cue (fewer, fuller cues are better) and weight of an under-filled cue.
CUE_COST = 1.0
FILL_WEIGHT = 3.0
#: Weight of unequal line widths within a cue.
BALANCE_WEIGHT = 4.0
#: Cost of a sentence ending inside a line (the next one should start a line or a cue).
INNER_SENTENCE = 3.0


def phrase_break_cost(before: str, after: str) -> float:
    """How bad a break between the words ``before`` and ``after`` is (0 after a sentence)."""
    if _SENTENCE_END.search(before):
        return COST_SENTENCE
    if _CLAUSE_END.search(before) or _DASH.match(after):
        return COST_CLAUSE
    word_before = _CLEAN.sub("", before).lower()
    word_after = _CLEAN.sub("", after).lower()
    if word_before in CLINGING:
        return COST_CLINGING
    if word_after in CONJUNCTIONS:
        return COST_CONJUNCTION
    if word_after in PREPOSITIONS:
        return COST_PREPOSITION
    return COST_PLAIN


Lines = list[tuple[int, int]]


def segment_cues(
    words: Sequence[str],
    widths: Sequence[float],
    space: float,
    max_width: float,
    max_lines: int = 2,
    max_words: int | None = None,
) -> list[Lines]:
    """``words`` (with their ``widths`` and the width of a ``space``) cut into cues of at most
    ``max_lines`` lines of ``max_width`` (and ``max_words`` words). Returns the cues, each a
    list of lines given as word index ranges ``(i, j)`` (``words[i:j]``). A word wider than
    ``max_width`` gets a line of its own (the caller shrinks it)."""
    n = len(words)
    if n == 0:
        return []
    if max_lines < 1:
        raise ValueError("max_lines must be at least 1")
    prefix = [0.0]
    for w in widths:
        prefix.append(prefix[-1] + float(w))
    cost_after = [phrase_break_cost(words[k], words[k + 1]) for k in range(n - 1)]

    def width(i: int, j: int) -> float:
        return prefix[j] - prefix[i] + space * (j - i - 1)

    def fits(i: int, j: int) -> bool:
        return j - i == 1 or width(i, j) <= max_width + 1e-9

    def inner(a: int, b: int) -> float:
        """Sentence ends inside the line ``words[a:b]`` (a new sentence should start a line)."""
        return INNER_SENTENCE * sum(1 for k in range(a, b - 1) if cost_after[k] == COST_SENTENCE)

    def lines_of(i: int, j: int) -> tuple[float, Lines] | None:
        """The best way to set ``words[i:j]`` as one cue (``None``: it does not fit)."""
        if max_words is not None and j - i > max_words:
            return None
        if fits(i, j):
            return inner(i, j), [(i, j)]
        best: tuple[float, Lines] | None = None
        for count in range(1, min(max_lines, j - i)):
            for cuts in itertools.combinations(range(i + 1, j), count):
                edges = [i, *cuts, j]
                spans = list(zip(edges, edges[1:]))
                if not all(fits(a, b) for a, b in spans):
                    continue
                spread = [width(a, b) for a, b in spans]
                cost = sum(cost_after[c - 1] for c in cuts) + sum(inner(a, b) for a, b in spans)
                cost += BALANCE_WEIGHT * (max(spread) - min(spread)) / max_width
                if best is None or cost < best[0]:
                    best = (cost, spans)
        return best

    capacity = max_width * max_lines
    best: list[tuple[float, list[Lines]] | None] = [None] * (n + 1)
    best[0] = (0.0, [])
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            if j - i > 1 and (width(i, j) > capacity + 1e-9 or (max_words is not None and j - i > max_words)):
                break  # longer cues ending at j only get wider
            if best[i] is None:
                continue
            found = lines_of(i, j)
            if found is None:
                continue
            fill = min(width(i, j) / capacity, 1.0)
            if max_words is not None:
                fill = max(fill, (j - i) / max_words)
            cost = best[i][0] + found[0] + CUE_COST + FILL_WEIGHT * (1.0 - fill) ** 2
            if j < n:
                cost += cost_after[j - 1]
            if best[j] is None or cost < best[j][0]:
                best[j] = (cost, [*best[i][1], found[1]])
    result = best[n]
    assert result is not None  # a word per cue always fits
    return result[1]


def split_cues(text: str, width: int, max_lines: int = 2, max_words: int | None = None) -> list[list[str]]:
    """``text`` cut by :func:`segment_cues` with widths in characters: the cues, each a list of
    lines."""
    words = text.split()
    cues = segment_cues(words, [len(w) for w in words], 1.0, float(width), max_lines, max_words)
    return [[" ".join(words[a:b]) for a, b in lines] for lines in cues]


@dataclass(frozen=True)
class CaptionCue:
    """One caption: its ``lines`` and timed ``words`` (:class:`~vidgen.speech.WordTime`), shown
    from ``start`` to ``end`` (seconds, on the caller's clock)."""

    start: float
    end: float
    lines: tuple[str, ...]
    words: tuple[WordTime, ...]
    #: A speaker tag at the start of the first line (``"Ana:"``; not one of ``words``), or "".
    prefix: str = ""

    @property
    def text(self) -> str:
        """The lines joined by newlines."""
        return "\n".join(self.lines)


def caption_cues(
    text: str,
    start: float,
    end: float,
    *,
    words: Sequence[WordTime] | None = None,
    widths: Sequence[float] | None = None,
    space: float = 1.0,
    max_width: float = 42.0,
    max_lines: int = 2,
    max_words: int | None = None,
    until: float | None = None,
    prefix: str = "",
    prefix_width: float | None = None,
) -> list[CaptionCue]:
    """The cues of one beat whose narration runs ``start``..``end``: :func:`segment_cues` of its
    words (``widths`` default: characters), timed by ``words`` (default: estimated over the
    beat, :func:`~vidgen.speech.estimate_word_times`). The first cue starts at ``start``, each
    other one when its first word is spoken; each lasts until the next starts and the last until
    ``until`` (default ``end``). ``prefix`` (a speaker tag such as ``"Ana:"``, of width
    ``prefix_width``, default its characters) starts the first line, glued to the first word
    so a cut never leaves it alone; it is not a timed word (``CaptionCue.prefix``)."""
    tokens = text.split()
    if not tokens:
        return []
    timed = list(words) if words is not None else estimate_word_times(tokens, start, end)
    if len(timed) != len(tokens):
        timed = estimate_word_times(tokens, start, end)
    sizes = list(widths) if widths is not None else [float(len(w)) for w in tokens]
    prefix = " ".join(prefix.split())
    if prefix:
        sizes[0] += (float(len(prefix)) if prefix_width is None else prefix_width) + space
    cues = segment_cues(tokens, sizes, space, max_width, max_lines, max_words)
    firsts = [lines[0][0] for lines in cues]
    starts = [start, *(max(timed[k].start, start) for k in firsts[1:])]
    stop = end if until is None else until
    out = []
    for n, lines in enumerate(cues):
        a, b = lines[0][0], lines[-1][1]
        cue_end = starts[n + 1] if n + 1 < len(cues) else max(stop, starts[n])
        texts = [" ".join(tokens[i:j]) for i, j in lines]
        tag = prefix if n == 0 else ""
        if tag:
            texts[0] = f"{tag} {texts[0]}"
        out.append(CaptionCue(starts[n], cue_end, tuple(texts), tuple(timed[a:b]), tag))
    return out
