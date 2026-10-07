"""Prose into narration beats and on-screen labels, for ``vidgen plan`` (DESIGN.md §61).

- :func:`split_sentences`: sentence ends at ``. ! ? …`` (and ``。！？``) followed by a capital, a
  digit or an opening mark; abbreviations of the language (:attr:`LanguageRules.abbreviations`:
  ``e.g.``, ``Dr.``, ``Sr.``...), initials (``J. R. Tolkien``) and decimals never end one.
- :func:`narration_beats`: sentences sized to the author guide's pacing rule (beats of 6-15
  words): a long sentence is cut at its best phrase boundaries (:func:`vidgen.cues.phrase_break_cost`:
  clause marks, then conjunctions, then prepositions, never after an article), aiming at
  :data:`TARGET_WORDS`; tiny sentences are merged with a neighbour.
- :func:`compress`: a sentence or heading as an on-screen label: parentheses, leading filler
  ("In this video", "So", "Basically"...), filler words and, if needed, articles dropped, cut at a
  clause mark, capped at a number of words without ending on a word that leans on the next.

Word lists are per language (English and Portuguese fillers; the cue words of
:mod:`vidgen.languages` for all its languages). No manim import.
"""

from __future__ import annotations

import re

from vidgen.cues import phrase_break_cost
from vidgen.languages import language_rules, primary_language

#: The pacing rule of the author guide: beats of 6-15 words, about 10 when a sentence is cut.
MIN_WORDS = 6
MAX_WORDS = 15
TARGET_WORDS = 10
#: Shortest piece a long sentence is cut into (when the sentence allows it).
MIN_PIECE = 4

#: Abbreviations that may also end a sentence (``etc.`` before a capital does).
_ENDING_ABBREVIATIONS = frozenset({"etc", "usw", "ecc"})
_TERMINAL = re.compile(r"([.!?…。！？]+)[\"'”’»)\]]*$")
_OPENING = re.compile(r"^[\"'“‘«(\[¿¡]*[A-ZÀ-ÖØ-Þ0-9]")
_PAREN = re.compile(r"\s*\([^()]*\)")

#: Leading phrases dropped from labels, per language (lower case, longest first when matched).
_LEADING_FILLER: dict[str, tuple[str, ...]] = {
    "en": (
        "in this video", "in this section", "in this part", "let's talk about", "let us", "let's", "we will", "we'll",
        "you will", "you'll", "basically", "so", "then", "first of all", "first", "firstly", "second", "secondly",
        "third", "next", "finally", "lastly", "also", "and", "but", "now", "here", "there are", "there is",
        "it is", "it's", "this is", "that is", "in short", "in fact", "of course", "remember that", "note that",
    ),
    "pt": (
        "neste vídeo", "nesta seção", "nesta parte", "vamos falar sobre", "vamos", "você vai", "basicamente", "então",
        "primeiro", "primeiramente", "segundo", "depois", "em seguida", "por fim", "finalmente", "também", "e",
        "mas", "agora", "aqui", "existem", "existe", "há", "isso é", "isto é", "ou seja", "em resumo", "lembre que",
        "note que",
    ),
}
#: Words dropped anywhere from labels, per language.
_FILLER_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset("really very just actually basically simply quite pretty somewhat literally truly".split()),
    "pt": frozenset("realmente muito apenas simplesmente basicamente bastante literalmente".split()),
}
#: Auxiliary verbs and quantifiers, never the last word of a cut label ("Account balances must",
#: "Run tests every").
_AUXILIARIES: dict[str, frozenset[str]] = {
    "en": frozenset("must should can could will would may might shall have has had do does did cannot each every all any some".split()),
    "pt": frozenset("deve devem pode podem vai vão tem têm precisa precisam cada todo toda todos todas qualquer".split()),
}
#: Articles, dropped from labels when they are still too long.
_ARTICLES: dict[str, frozenset[str]] = {
    "en": frozenset({"the", "a", "an"}),
    "pt": frozenset({"o", "a", "os", "as", "um", "uma", "uns", "umas"}),
    "es": frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas"}),
    "fr": frozenset({"le", "la", "les", "un", "une", "des"}),
    "de": frozenset({"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer"}),
    "it": frozenset({"il", "lo", "la", "i", "gli", "le", "un", "uno", "una"}),
}
#: A label ``"Step 2: Measure"`` keeps the part after the colon when the part before is one of these.
_GENERIC_LEADS = re.compile(
    r"^(step|stage|phase|part|tip|note|example|rule|passo|etapa|fase|parte|dica|nota|exemplo|regra)\b", re.IGNORECASE
)


def words(text: str) -> int:
    """Number of words of ``text``."""
    return len(text.split())


def _ends_sentence(token: str, following: str, abbreviations: frozenset[str]) -> bool:
    """Whether a sentence ends after ``token`` (the next word being ``following``)."""
    match = _TERMINAL.search(token)
    if match is None:
        return False
    starts_new = bool(_OPENING.match(following))
    marks = match[1]
    if marks[-1] != "." or marks.endswith(".."):
        return starts_new or marks[-1] in "。！？"
    core = token[: match.start(1)].lstrip("\"'“‘«([¿¡").lower()
    if core in abbreviations:
        return core in _ENDING_ABBREVIATIONS and starts_new
    if len(core) == 1 and core.isalpha() and token.lstrip("\"'“‘«([")[:1].isupper():
        return False  # an initial: "J. R. Tolkien"
    return starts_new


def split_sentences(text: str, language: str | None = None) -> list[str]:
    """``text`` cut into sentences by the rules of ``language`` (BCP-47; ``None``: English)."""
    tokens = text.split()
    abbreviations = language_rules(language).abbreviations
    sentences: list[str] = []
    current: list[str] = []
    for i, token in enumerate(tokens):
        current.append(token)
        if i + 1 < len(tokens) and _ends_sentence(token, tokens[i + 1], abbreviations):
            sentences.append(" ".join(current))
            current = []
    if current:
        sentences.append(" ".join(current))
    return sentences


def split_long(sentence: str, language: str | None = None, max_words: int = MAX_WORDS, target: int = TARGET_WORDS) -> list[str]:
    """``sentence`` cut into pieces of at most ``max_words`` words at its best phrase boundaries
    (unchanged when short enough): the cut with the cheapest breaks and pieces nearest to
    ``target`` words wins."""
    tokens = sentence.split()
    n = len(tokens)
    if n <= max_words:
        return [sentence] if tokens else []
    smallest = MIN_PIECE if n >= 2 * MIN_PIECE else 1
    best: list[tuple[float, list[int]] | None] = [None] * (n + 1)
    best[0] = (0.0, [])
    for j in range(1, n + 1):
        for i in range(max(0, j - max_words), j - smallest + 1):
            if best[i] is None or (i > 0 and i < smallest):
                continue
            size = j - i
            cost = best[i][0] + 0.04 * (size - target) ** 2
            if i > 0:
                cost += phrase_break_cost(tokens[i - 1], tokens[i], language)
            if best[j] is None or cost < best[j][0]:
                best[j] = (cost, [*best[i][1], i])
    found = best[n]
    if found is None:  # cannot happen with smallest == 1; keep the sentence whole
        return [sentence]
    cuts = [*found[1], n]
    return [" ".join(tokens[a:b]) for a, b in zip(cuts, cuts[1:])]


def merge_short(
    beats: list[str], min_words: int = MIN_WORDS, max_words: int = MAX_WORDS, target: int = TARGET_WORDS
) -> list[str]:
    """Consecutive ``beats`` grouped so that short ones (under ``min_words``) join a neighbour:
    the grouping with beats nearest to ``target`` words, none over ``max_words`` unless it was one
    beat already, and the fewest short beats wins."""
    counts = [words(b) for b in beats]
    n = len(beats)
    best: list[tuple[float, list[int]] | None] = [None] * (n + 1)
    best[0] = (0.0, [])
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            size = sum(counts[i:j])
            if size > max_words and j - i > 1:
                break
            previous = best[i]
            if previous is None:
                continue
            cost = previous[0] + 0.04 * (size - target) ** 2 + 4.0 * max(0, min_words - size)
            if best[j] is None or cost < best[j][0]:
                best[j] = (cost, [*previous[1], i])
    found = best[n]
    assert found is not None
    cuts = [*found[1], n]
    return [" ".join(beats[a:b]) for a, b in zip(cuts, cuts[1:])]


def narration_beats(
    text: str, language: str | None = None, min_words: int = MIN_WORDS, max_words: int = MAX_WORDS
) -> list[str]:
    """``text`` as narration beats: its sentences, long ones cut at phrase boundaries, tiny ones
    merged (:func:`split_sentences`, :func:`split_long`, :func:`merge_short`)."""
    pieces = [p for s in split_sentences(text, language) for p in split_long(s, language, max_words)]
    return merge_short(pieces, min_words, max_words)


def _strip_leading(tokens: list[str], phrases: tuple[str, ...]) -> list[str]:
    """``tokens`` without leading filler ``phrases`` (repeatedly, while a word is left)."""
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        lowered = [t.lower().strip(",;:") for t in tokens]
        for phrase in sorted(phrases, key=lambda p: -len(p.split())):
            parts = phrase.split()
            if len(parts) < len(tokens) and lowered[: len(parts)] == parts:
                tokens = tokens[len(parts) :]
                changed = True
                break
    return tokens


def _clean_word(token: str) -> str:
    return token.strip("\"'“”‘’«»()[]¿¡").lower().rstrip(".,;:!?…")


def compress(text: str, max_words: int, language: str | None = None) -> str:
    """``text`` as a short on-screen label of at most ``max_words`` words (see the module doc);
    a question keeps its question mark when nothing was cut."""
    code = primary_language(language)
    rules = language_rules(language)
    source = " ".join(_PAREN.sub("", text).split())
    question = source.endswith("?")
    head, sep, tail = _partition(source)
    if sep:
        if _GENERIC_LEADS.match(head) and words(head) <= 3 and tail.strip():
            source = tail.strip()
        elif words(head) >= 2:
            source = head
    tokens = source.split()
    tokens = _strip_leading(tokens, _LEADING_FILLER.get(code, ()))
    fillers = _FILLER_WORDS.get(code, frozenset())
    kept = [t for t in tokens if _clean_word(t) not in fillers]
    tokens = kept or tokens
    cut = bool(sep)
    if len(tokens) > max_words:
        first = next((k for k, t in enumerate(tokens) if k >= 1 and t.endswith(",")), None)
        if first is not None:
            cut = True
            subordinate = _clean_word(tokens[0]) in rules.conjunctions | rules.prepositions
            if subordinate and len(tokens) - first - 1 >= 2:
                tokens = tokens[first + 1 :]  # "On a miss, query the database" -> the main clause
            else:
                tokens = tokens[: first + 1]
    if len(tokens) > max_words:
        articles = _ARTICLES.get(code, frozenset())
        tokens = [t for k, t in enumerate(tokens) if k == 0 or _clean_word(t) not in articles] or tokens
    if len(tokens) > max_words:
        tokens = tokens[:max_words]
        cut = True
    if cut:  # a cut text must not end on a word that leans on the next ("Store result with")
        leaning = rules.clinging | rules.conjunctions | rules.prepositions | _AUXILIARIES.get(code, frozenset())
        while len(tokens) > 1 and (_clean_word(tokens[-1]) in leaning or not _clean_word(tokens[-1])):
            tokens = tokens[:-1]
    label = " ".join(tokens).strip()
    label = re.sub(r"[\s,;:.!?…—–-]+$", "", label)
    if label and label[0].islower():
        label = label[0].upper() + label[1:]
    if question and not cut and label:
        label += "?"
    return label


def _partition(text: str) -> tuple[str, str, str]:
    """``text`` split at its first strong clause mark (``: ``, ``; ``, a spaced dash)."""
    match = re.search(r":\s|;\s|\s[—–]\s|\s-\s", text)
    if match is None:
        return text, "", ""
    return text[: match.start()], match.group(), text[match.end() :]


def sentence(text: str) -> str:
    """``text`` ending in sentence punctuation (a period added when it has none)."""
    text = text.strip()
    if not text:
        return text
    return text if re.search(r"[.!?…:]['\"”’»)]*$", text) else f"{text}."
