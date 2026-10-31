"""``vidgen story draft``, part 1: reading a story in prose (DESIGN.md §105.5). Pure text rules, no
AI, no manim.

:func:`read_story` splits a story (Markdown or plain text) into scenes (headings, scene-break
markers such as ``***`` or ``#``, paragraphs opening with a time cue: ``The next morning``,
``Later``, ``That night``...), finds its characters (capitalised names used as speakers or
subjects, with titles: ``Doctor Vale``), their voice kind (a title, a built-in list of given
names, the pronouns used after them) and whether it is told in the first person, then reads the
scenes paragraph by paragraph into :class:`Line` s: narration in groups of sentences of at most
:data:`MAX_BEAT_WORDS` words, and dialogue (straight or curly double quotes) attributed to a speaker
with a confidence: a speech tag (``said Mara``, ``Mara asked``, ``she whispered``, ``I said``), a
sentence of the paragraph whose subject is a character (an action beat), the alternation of a
two-person exchange, then the last character mentioned. Speech tags are left out of the
narration. Sentences whose subject walks, runs, comes in or leaves become :class:`Move` s.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from vidgen.emotions import EMOTION_WORDS

#: Longest narration beat (words); longer paragraphs are cut between sentences.
MAX_BEAT_WORDS = 25
#: The id of a first-person narrator whose name the story never gives.
PROTAGONIST = "me"

#: Speech verbs (past and present) -> the emotion they suggest (``None``: none).
SPEECH_VERBS: dict[str, str | None] = {}
for _verbs, _emotion in (
    (("said", "says", "asked", "asks", "replied", "replies", "answered", "answers", "added", "adds", "continued",
      "began", "told", "tells", "explained", "agreed", "admitted", "insisted", "repeated", "wondered", "called",
      "calls", "announced", "declared", "warned", "suggested", "offered", "promised", "corrected", "observed",
      "noted", "remarked", "cried", "muttered", "mutters", "mumbled", "went on", "finished"), None),
    (("whispered", "whispers", "murmured", "murmurs", "breathed"), "whisper"),
    (("shouted", "shouts", "yelled", "yells", "screamed", "bellowed", "roared", "called out", "cried out"), "shout"),
    (("exclaimed", "cheered"), "excited"),
    (("laughed", "laughs", "giggled", "chuckled", "teased", "joked", "beamed"), "happy"),
    (("sobbed", "sighed", "sniffed", "wept"), "sad"),
    (("snapped", "growled", "snarled", "hissed", "grumbled", "barked", "huffed"), "angry"),
    (("gasped",), "surprised"),
    (("stammered", "stuttered", "pleaded", "begged", "fretted"), "worried"),
    (("yawned",), "sleepy"),
):
    for _verb in _verbs:
        SPEECH_VERBS[_verb] = _emotion

#: Titles before a name, and the voice kind they say (``None``: none).
TITLES: dict[str, str | None] = {
    **{t: "masculine" for t in ("Mr", "Sir", "Lord", "King", "Prince", "Uncle", "Grandpa", "Grandfather", "Father",
                                "Brother", "Duke", "Mister", "Señor", "Monsieur")},
    **{t: "feminine" for t in ("Mrs", "Ms", "Miss", "Lady", "Queen", "Princess", "Aunt", "Auntie", "Grandma",
                               "Granny", "Grandmother", "Mother", "Sister", "Madam", "Duchess", "Dame")},
    **{t: None for t in ("Dr", "Doctor", "Professor", "Prof", "Captain", "Officer", "Detective", "Agent", "Old", "Little",
                         "Young", "Chief", "Commander", "Nurse", "Coach")},
}
#: A small list of given names and their usual voice kind (a hint only; pronouns and titles win).
FEMININE_NAMES: frozenset[str] = frozenset((
    "Ada", "Alice", "Amara", "Amy", "Ana", "Anna", "Ava", "Bea", "Bella", "Clara", "Chloe", "Daisy", "Dora", "Ella",
    "Ellie", "Elsa", "Emma", "Eva", "Fern", "Fiona", "Grace", "Hana", "Hazel", "Holly", "Ida", "Iris", "Isla", "Ivy",
    "Jane", "Julia", "June", "Kate", "Lena", "Lily", "Lina", "Lucy", "Luna", "Maya", "Mara", "Maria", "Marta", "Mia",
    "Mila", "Nina", "Nora", "Olive", "Olivia", "Pia", "Rosa", "Rose", "Ruby", "Sara", "Sarah", "Sofia", "Sophie",
    "Tess", "Vera", "Wren", "Zoe", "Esme", "Greta", "Ines", "Nell", "Priya", "Yara", "Leila", "Mei", "Ayla",
))
MASCULINE_NAMES: frozenset[str] = frozenset((
    "Adam", "Alex", "Ben", "Bruno", "Carl", "Dan", "David", "Eli", "Felix", "Finn", "Frank", "George", "Hugo", "Ian",
    "Jack", "Jake", "James", "Jim", "Joe", "John", "Jonas", "Kai", "Leo", "Liam", "Luca", "Lucas", "Marco", "Mark",
    "Max", "Milo", "Nick", "Noah", "Omar", "Oscar", "Otto", "Paul", "Pedro", "Peter", "Raj", "Rowan", "Ruben", "Sam",
    "Simon", "Theo", "Tom", "Victor", "Will", "Yusuf", "Zane", "Arlo", "Basil", "Elias", "Ivan", "Nils", "Hal", "Ned",
    "Oren", "Rafael", "Tariq", "Bram", "Cole", "Emil", "Gus", "Jasper",
))
#: Capitalised words that are not names (sentence openers, pronouns, days, months...).
NOT_NAMES: frozenset[str] = frozenset("""
The A An And But Or So Then When While After Before If It Its This That These Those There Here He She They We You
I His Her Their Our My Your Yes No Oh Ah Well Now Just What Where Why How Who Whom Whose Which Maybe Perhaps Still
Even All Every Each Some One Two Three Four Five Later Soon At In On By For With Without From To Into Not Nothing
Something Someone Everyone Everything Nobody Somewhere Hello Hi Hey Thanks Thank Please Sorry Good Okay Ok Let
Come Look Wait Listen Stop Go Help Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
April May June July August September October November December God Chapter Part Scene Once Today Tomorrow
Tonight Yesterday Inside Outside Behind Above Below Across Through Over Under Again Also Only Never Always
Sometimes Finally Suddenly Meanwhile Instead Because Although Though Since Until Unless Whether Like Than As
Did Do Does Was Were Is Are Had Has Have Be Can Could Would Should Will Shall Might Must Mine Yours Hers Ours
Theirs Me Him Them Us Myself Yourself Herself Himself Themselves Ourselves Itself Very Too Much Many More Most
Less Least Few Other Another Such Both Either Neither Nor Yet Ever Hmm Hm Mm Uh Um Wow Ouch Shh Huh Aha Hurray
Hooray Bye Goodbye Dear Mister Lady Sir Madam Lord Christmas Easter English Spanish French Earth Moon Sun Mars
Doctor Professor Captain Grandpa Grandma Mum Mom Dad Mama Papa Auntie Uncle Aunt
""".split())
#: Family words that are a character's name when used as one (``Mum said``, ``Grandpa smiled``).
FAMILY: dict[str, str] = {
    **{w: "feminine" for w in ("Mum", "Mom", "Mama", "Grandma", "Granny", "Auntie")},
    **{w: "masculine" for w in ("Dad", "Papa", "Grandpa")},
}
#: Words after a capitalised word that make it a sentence's subject (with any word ending in -ed).
SUBJECT_VERBS: frozenset[str] = frozenset("""
was is had has could would will did didn't wasn't couldn't wouldn't can can't took gave went came saw felt knew
thought ran walked looked smiled nodded shook turned laughed frowned sighed grinned stood sat stepped hurried
reached pointed held kept made found left began tried wanted needed opened closed lit put picked pulled pushed
grabbed whispered said asked replied shouted waited watched stared glanced listened sank rose fell leaned wiped
blinked shrugged waved hugged cried
""".split())
#: Words that make the capitalised word after them a place rather than a character.
PLACE_WORDS: frozenset[str] = frozenset(("in", "at", "to", "from", "into", "of", "near", "across", "towards", "toward", "through", "via", "on"))
#: Words near a character that suggest a voice effect (``voices:`` ``effect``).
EFFECT_HINTS: dict[str, str] = {
    **{w: "robot" for w in ("robot", "android", "machine", "AI", "computer", "drone", "cyborg", "automaton")},
    **{w: "echo" for w in ("ghost", "spirit", "hologram", "phantom", "spectre", "specter")},
}

#: Movement verbs of a narration sentence's subject -> the kind of move.
MOVE_VERBS: dict[str, str] = {
    **{v: "run" for v in ("ran", "runs", "hurried", "hurries", "rushed", "rushes", "raced", "races", "dashed",
                          "dashes", "sprinted", "jogged", "bolted", "scrambled")},
    **{v: "walk" for v in ("walked", "walks", "went", "goes", "crossed", "stepped", "steps", "headed", "wandered",
                           "strolled", "marched", "crept", "tiptoed", "moved", "returned", "climbed", "limped", "came",
                           "comes", "approached", "paced", "made her way", "made his way", "made their way",
                           "made my way", "followed")},
    **{v: "enter" for v in ("entered", "enters", "arrived", "arrives", "appeared", "appears", "burst in",
                            "came in", "walked in", "stepped in", "ran in", "rushed in", "came back", "came out",
                            "stepped out", "came inside")},
    **{v: "exit" for v in ("left", "leaves", "disappeared", "vanished", "walked out", "went out", "ran out",
                           "walked away", "ran away", "ran off", "went away", "stormed out", "slipped out", "hurried out",
                           "rushed out", "hurried away", "walked off")},
}

_TITLE_RE = "|".join(sorted((re.escape(t) for t in TITLES), key=len, reverse=True))
_CAP = re.compile(rf"\b(?:({_TITLE_RE})\.?\s+)?([A-Z][a-z]+(?:-[A-Z][a-z]+)?)(?:'s|’s)?\b(?!['’](?:t|re|ll|ve|d|m)\b)")
_QUOTE = re.compile(r"“([^”]*)(?:”|$)|\"([^\"]*)(?:\"|$)|«([^»]*)(?:»|$)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BREAK = re.compile(r"^\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,}|#|~{3,}|§|⁂|[oO•◆◇·]{1,3}|\*\s+\*\s+\*)\s*$")
_TIME_CUE = re.compile(
    r"^(?:later|hours later|minutes later|days later|weeks later|months later|years later|meanwhile|"
    r"the (?:next|following) (?:morning|day|evening|night|afternoon|week)|next (?:morning|day|evening)|"
    r"that (?:night|evening|morning|afternoon)|by (?:nightfall|morning|dawn|evening|noon)|"
    r"at (?:dawn|dusk|midnight|noon|sunrise|sunset)|in the (?:morning|evening)|back (?:at|in) |"
    r"when (?:morning|night|evening) came|the morning after|some time later|an hour later)",
    re.IGNORECASE,
)
_ABBREVIATIONS = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof|St|Mt|Jr|Sr|vs|etc|e\.g|i\.e)\.", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’)]*\s+(?=[\"“‘(]?[A-Z0-9])")
_FIRST_PERSON = re.compile(r"\bI\b|\bI['’](?:m|d|ll|ve)\b|\b[Mm]y\b|\b[Mm]e\b|\b[Mm]yself\b")
_THIRD_PERSON = re.compile(r"\b(?:[Hh]e|[Ss]he|[Tt]hey|[Hh]is|[Hh]er|[Tt]heir)\b")
_PROTAGONIST_NAME = re.compile(r"\b(?:[Mm]y name is|[Cc]all me|I['’]m|I am)\s+([A-Z][a-z]+)\b")
_PRONOUNS = {"he": "masculine", "him": "masculine", "his": "masculine", "she": "feminine", "her": "feminine", "hers": "feminine"}
_LEAD = (r"(?:(?:^|(?<=[.!?])\s+|(?<=[,;])\s*)(?:(?:[Aa]nd|[Tt]hen|[Bb]ut|[Ss]o|[Ff]inally|[Ss]uddenly|[Ll]ater)[,]?\s+(?:then\s+)?)?"
         r"|\band\s+(?:then\s+)?|\bthen\s+)")
#: Words before a name at a sentence's start that keep it the subject (``Her friend Theo came in``).
_POSSESSIVE = r"(?:(?:[Hh]er|[Hh]is|[Tt]heir|[Mm]y|[Oo]ur)\s+[a-z]+\s+)?"
_ADVERB = r"(?:\w+ly\s+|then\s+|finally\s+|suddenly\s+)?"


@dataclass
class Character:
    """A character found in the story: its id, its name as written (with a title), how often it is
    mentioned, its voice kind and where that came from, a suggested voice ``effect``, whether it
    speaks."""

    id: str
    name: str
    mentions: int = 0
    kind: str | None = None
    kind_source: str = "no hint"
    effect: str | None = None
    effect_word: str | None = None
    lines: int = 0
    protagonist: bool = False


@dataclass
class Move:
    """A move of a narration line: who, the kind (``walk``, ``run``, ``enter``, ``exit``) and where
    in the line it is said (share of its words, 0-1)."""

    who: str
    kind: str
    at: float
    words: str


@dataclass
class Line:
    """A beat to be: narration (``speaker`` ``None``) or a line of dialogue with its speaker, the
    confidence of the attribution (0-1) and how it was made, the emotion its tag suggests, the
    moves of narration, and the line of the source it starts on."""

    text: str
    source_line: int
    speaker: str | None = None
    dialogue: bool = False
    confidence: float = 1.0
    method: str = ""
    emotion: str | None = None
    moves: list[Move] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)


@dataclass
class StoryScene:
    """A scene of the story: its heading (if any), why it starts here, its first source line, its
    text and its lines."""

    heading: str | None
    reason: str
    start_line: int
    paragraphs: list[tuple[int, str]] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(p for _, p in self.paragraphs)


@dataclass
class Story:
    """A story read by :func:`read_story`."""

    title: str | None
    scenes: list[StoryScene]
    characters: dict[str, Character]
    first_person: bool
    person_note: str
    words: int


# ----- scenes and paragraphs --------------------------------------------------------------------------


def _paragraphs(text: str) -> list[tuple[int, str, str]]:
    """``(line number, kind, text)`` of each block: ``heading`` (its text), ``break`` or ``para``.
    A paragraph's lines are joined; a line ending a sentence followed by one that starts with a
    capital or a quote starts a new paragraph (one paragraph per line)."""
    blocks: list[tuple[int, str, str]] = []
    current: list[str] = []
    start = 0

    def flush() -> None:
        if current:
            blocks.append((start, "para", " ".join(s.strip() for s in current)))
            current.clear()

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        heading = _HEADING.match(line)
        if not line.strip():
            flush()
        elif _BREAK.match(line):
            flush()
            blocks.append((number, "break", line.strip()))
        elif heading:
            flush()
            blocks.append((number, "heading", heading.group(2).strip()))
        else:
            if current and re.search(r"[.!?…\"”’]$", current[-1]) and re.match(r"\s*[\"“‘«A-Z]", line):
                flush()
            if not current:
                start = number
            current.append(line)
    flush()
    return blocks


def split_scenes(text: str) -> tuple[str | None, list[StoryScene]]:
    """The story's title (a first level-1 heading, else ``None``) and its scenes (see the module
    doc). A time cue starts a scene only after two paragraphs of the scene before."""
    title: str | None = None
    scenes: list[StoryScene] = []
    scene: StoryScene | None = None
    for number, kind, body in _paragraphs(text):
        if kind == "heading":
            if title is None and not scenes and scene is None and body:
                title = body
                continue
            scene = StoryScene(body, "heading", number)
            scenes.append(scene)
        elif kind == "break":
            scene = None
        else:
            cue = _TIME_CUE.match(body)
            if scene is None:
                reason = "start" if not scenes else "scene break"
                scene = StoryScene(None, reason, number)
                scenes.append(scene)
            elif cue and len(scene.paragraphs) >= 2:
                scene = StoryScene(None, f"time cue: {cue.group(0).strip()!r}", number)
                scenes.append(scene)
            scene.paragraphs.append((number, body))
    return title, [s for s in scenes if s.paragraphs]


def sentences(text: str) -> list[str]:
    """``text`` cut into sentences (abbreviations such as ``Dr.`` do not end one)."""
    masked = _ABBREVIATIONS.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    return [s.replace("\x00", ".").strip() for s in _SENTENCE_END.split(masked) if s.strip()]


def segments(paragraph: str) -> list[tuple[bool, str]]:
    """``(is a quote, text)`` pieces of a paragraph: quoted speech (straight, curly or guillemet
    double quotes; an unclosed quote runs to the paragraph's end) and the narration between."""
    pieces: list[tuple[bool, str]] = []
    pos = 0
    for match in _QUOTE.finditer(paragraph):
        if match.start() > pos and paragraph[pos:match.start()].strip():
            pieces.append((False, paragraph[pos:match.start()].strip()))
        quoted = next(g for g in match.groups() if g is not None).strip()
        if quoted:
            pieces.append((True, quoted))
        pos = match.end()
    if paragraph[pos:].strip():
        pieces.append((False, paragraph[pos:].strip()))
    return pieces


def _words(text: str) -> int:
    return len(text.split())


def beat_groups(text: str, limit: int = MAX_BEAT_WORDS) -> list[str]:
    """``text``'s sentences grouped into beats of at most ``limit`` words (a longer sentence is a
    beat of its own)."""
    groups: list[list[str]] = []
    for sentence in sentences(text):
        if groups and sum(map(_words, groups[-1])) + _words(sentence) <= limit:
            groups[-1].append(sentence)
        else:
            groups.append([sentence])
    return [" ".join(g) for g in groups]


# ----- characters -----------------------------------------------------------------------------------


def slug(name: str) -> str:
    """``Old Pip`` -> ``old_pip``: lower case, ``_`` between words."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "character"


def _could_name(word: str) -> bool:
    """Whether a capitalised word may be a character's name (not a sentence opener, a pronoun, a
    day...; a family word such as ``Mum`` may)."""
    return word in FAMILY or (word not in NOT_NAMES and word not in TITLES)


def name_words(character: Character) -> list[str]:
    """The words a character is called by in the text: its name, and each of its words that is
    not a title (``Doctor Vale``: also ``Vale``)."""
    own = [w for w in character.name.split() if w not in TITLES or w in FAMILY]
    return list(dict.fromkeys([character.name, *own]))


def _speech_verbs_re() -> str:
    return "|".join(sorted((re.escape(v) for v in SPEECH_VERBS), key=len, reverse=True))


_VERBS_RE = _speech_verbs_re()
_TAG_AFTER = re.compile(rf"\b({_VERBS_RE})\s+(?:({_TITLE_RE})\.?\s+)?([A-Z][a-z]+|he|she|they|I)\b")
_TAG_BEFORE = re.compile(rf"(?:\b({_TITLE_RE})\.?\s+)?\b([A-Z][a-z]+|[Hh]e|[Ss]he|[Tt]hey|I)\s+(?:\w+ly\s+)?({_VERBS_RE})\b")
_TAG_DESCRIBED = re.compile(rf"\b({_VERBS_RE})\s+(?:the|a|an|her|his|their|my)\s+([a-z]+(?:\s+[a-z]+)?)\b")


def find_characters(text: str) -> dict[str, Character]:
    """The story's characters (see the module doc), most mentioned first."""
    plain = _QUOTE.sub(" ", text)
    counts: Counter[str] = Counter()
    subject: Counter[str] = Counter()
    placed: Counter[str] = Counter()
    tagged: Counter[str] = Counter()
    titled: dict[str, str] = {}
    pairs: Counter[tuple[str, str]] = Counter()
    for sentence in sentences(text.replace("\n", " ")):
        previous = None
        for match in _CAP.finditer(sentence):
            title, word = match.group(1), match.group(2)
            if not _could_name(word):
                previous = None
                continue
            counts[word] += 1
            if title:
                titled.setdefault(word, f"{title} {word}")
            before = sentence[: match.start()].strip()
            last = before.split()[-1].lower() if before.split() else ""
            if last in PLACE_WORDS and not title:
                placed[word] += 1
            after = sentence[match.end():].split()
            nxt = after[0].strip(",.;:!?").lower() if after else ""
            if nxt in SUBJECT_VERBS or (nxt.endswith("ed") and len(nxt) > 3) or nxt in SPEECH_VERBS:
                subject[word] += 1
            if previous is not None and match.start() - previous[1] <= 1:
                pairs[(previous[0], word)] += 1
            previous = (word, match.end())
    for match in _TAG_AFTER.finditer(text):
        if match.group(3)[0].isupper() and _could_name(match.group(3)):
            tagged[match.group(3)] += 1
            if match.group(2):
                titled.setdefault(match.group(3), f"{match.group(2)} {match.group(3)}")
    for match in _TAG_BEFORE.finditer(text):
        word = match.group(2)
        if word[0].isupper() and _could_name(word):
            tagged[word] += 1
            if match.group(1):
                titled.setdefault(word, f"{match.group(1)} {word}")
    surnames = {b for (a, b), n in pairs.items() if n == counts[b] and counts[a] >= n}
    found: dict[str, Character] = {}
    for word, n in counts.most_common():
        if word in surnames:
            continue
        known = word in FEMININE_NAMES or word in MASCULINE_NAMES
        if word in FAMILY and not (tagged[word] or subject[word]):
            continue
        named = tagged[word] or word in titled or known or (n >= 2 and subject[word] and placed[word] * 2 < n)
        if not named or (placed[word] * 2 >= n and not tagged[word] and word not in titled):
            continue
        surname = next((b for (a, b) in pairs if a == word and b in surnames), None)
        name = (titled.get(word) or word) + (f" {surname}" if surname else "")
        found[slug(word)] = Character(slug(word), name, n)
    _voice_kinds(found, plain)
    _effects(found, text)
    return found


def _voice_kinds(found: dict[str, Character], plain: str) -> None:
    """Each character's voice kind: its title's, else the given-name list's, else the pronouns of
    the sentences it is the only character in (and of the sentence after)."""
    by_word = {w: c for c in found.values() for w in name_words(c) if " " not in w}
    score: dict[str, Counter[str]] = {cid: Counter() for cid in found}
    parts = sentences(plain.replace("\n", " "))
    for k, sentence in enumerate(parts):
        here = {by_word[w].id for w in re.findall(r"\b[A-Z][a-z]+\b", sentence) if w in by_word}
        if len(here) != 1:
            continue
        cid = next(iter(here))
        window = sentence
        if k + 1 < len(parts) and not any(w in by_word for w in re.findall(r"\b[A-Z][a-z]+\b", parts[k + 1])):
            window += " " + parts[k + 1]
        for word in re.findall(r"\b(?:he|him|his|she|her|hers)\b", window, re.IGNORECASE):
            score[cid][_PRONOUNS[word.lower()]] += 1
    for cid, character in found.items():
        first = character.name.split()[0]
        stated = FAMILY.get(first) or TITLES.get(first)
        if stated:
            character.kind, character.kind_source = stated, f"title {first}"
            continue
        word = next((w for w in character.name.split() if w not in TITLES), first)
        if word in FEMININE_NAMES:
            character.kind, character.kind_source = "feminine", "name list"
        elif word in MASCULINE_NAMES:
            character.kind, character.kind_source = "masculine", "name list"
        feminine, masculine = score[cid]["feminine"], score[cid]["masculine"]
        if max(feminine, masculine) >= 2 and max(feminine, masculine) >= 2 * min(feminine, masculine):
            kind = "feminine" if feminine > masculine else "masculine"
            if character.kind is None or character.kind == kind:
                character.kind, character.kind_source = kind, f"pronouns (she {feminine}, he {masculine})"


def _effects(found: dict[str, Character], text: str) -> None:
    """A voice effect for a character named in a sentence that calls it a robot, a ghost..."""
    for sentence in sentences(text.replace("\n", " ")):
        for word, effect in EFFECT_HINTS.items():
            if not re.search(rf"\b{re.escape(word)}\b", sentence, 0 if word.isupper() else re.IGNORECASE):
                continue
            here = [c for c in found.values() if re.search(rf"\b{re.escape(c.name.split()[-1])}\b", sentence)]
            if len(here) == 1 and here[0].effect is None:
                here[0].effect, here[0].effect_word = effect, word


def person_of(text: str) -> tuple[bool, str, str | None]:
    """Whether the narration (outside quotes) is in the first person, why, and the narrator's
    name if the story gives it (``My name is Lena``, ``I'm Lena``)."""
    plain = _QUOTE.sub(" ", text)
    first = len(_FIRST_PERSON.findall(plain))
    third = len(_THIRD_PERSON.findall(plain))
    words = max(_words(plain), 1)
    found = first >= 3 and first * 100 >= words
    name_match = _PROTAGONIST_NAME.search(text)
    name = name_match.group(1) if name_match and name_match.group(1) not in NOT_NAMES else None
    note = f"first-person words outside quotes: {first} (third-person: {third}) in {words} words"
    return found, note, name


# ----- reading the scenes --------------------------------------------------------------------------


@dataclass
class _State:
    """What the reader remembers while going through the story."""

    characters: dict[str, Character]
    first_person: bool
    protagonist: str | None
    recent: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list)
    #: the characters in the order the story first names them
    order: list[str] = field(default_factory=list)

    def ahead(self, word: str) -> str | None:
        """For ``he`` / ``she`` before any character of that kind was named (``a tall man`` who
        is named later): the first character of that kind the story names, not named yet."""
        kind = _PRONOUNS.get(word.lower())
        return next((c for c in self.order if c not in self.recent and self.characters[c].kind == kind), None)

    def mention(self, cid: str) -> None:
        if cid in self.recent:
            self.recent.remove(cid)
        self.recent.append(cid)

    def named(self, text: str) -> list[tuple[int, str]]:
        """``(offset, character id)`` of the characters named in ``text``."""
        found = []
        for pattern, cid in self.patterns:
            found.extend((m.start(), cid) for m in pattern.finditer(text))
        return sorted(found)

    def who(self, word: str, title: str | None = None) -> str | None:
        """The character a tag's or a subject's word names: a name, a pronoun (the last character
        of its kind mentioned, else the last one), ``I`` (the narrator in the first person)."""
        if word == "I":
            return self.protagonist if self.first_person else None
        lower = word.lower()
        if lower in ("he", "she"):
            kind = _PRONOUNS[lower]
            for cid in reversed(self.recent):
                if self.characters[cid].kind == kind and not self.characters[cid].protagonist:
                    return cid
            for cid in reversed(self.recent):
                if self.characters[cid].kind is None and not self.characters[cid].protagonist:
                    return cid
            return None
        if lower == "they":
            return next((c for c in reversed(self.recent) if not self.characters[c].protagonist), None)
        for pattern, cid in self.patterns:
            if pattern.fullmatch(word) or pattern.fullmatch(f"{title} {word}" if title else word):
                return cid
        return None


def _tag_in(text: str, state: _State, where: str) -> tuple[str | None, str | None, str] | None:
    """A speech tag in narration next to a quote (``where``: ``after`` it or ``before`` it):
    ``(speaker, emotion, how)``; ``None`` when the text holds none."""
    near = sentences(text)
    if not near:
        return None
    sentence = near[0] if where == "after" else near[-1]
    for pattern, order in ((_TAG_AFTER, "after"), (_TAG_BEFORE, "before")):
        match = pattern.search(sentence)
        if match is None:
            continue
        verb, title, word = (match.group(1), match.group(2), match.group(3)) if order == "after" else (match.group(3), match.group(1), match.group(2))
        who = state.who(word, title)
        kind = "pronoun" if word.lower() in ("he", "she", "they") else "first person" if word == "I" else "name"
        if who is None and word.lower() in ("he", "she"):
            who, kind = state.ahead(word), "pronoun, named later"
        emotion = SPEECH_VERBS.get(verb)
        adverb = re.search(r"\b(\w+ly)\b", sentence)
        if emotion is None and adverb and adverb.group(1).lower() in EMOTION_WORDS:
            emotion = EMOTION_WORDS[adverb.group(1).lower()]
        if who is None:
            continue
        return who, emotion, f"tag '{match.group(0).strip()}' ({kind})"
    described = _TAG_DESCRIBED.search(sentence)
    if described:
        return "?", SPEECH_VERBS.get(described.group(1)), f"tag '{described.group(0)}' names no character"
    return None


_TAG_CONFIDENCE = {"name": 0.95, "first person": 0.9, "pronoun": 0.75, "pronoun, named later": 0.5}


def _is_tag(sentence: str) -> bool:
    """A speech tag sentence to leave out of the narration (``said Mara.``, ``Mara asked, smiling.``)."""
    if _words(sentence) > 10:
        return False
    return bool(_TAG_AFTER.search(sentence) or _TAG_BEFORE.search(sentence) or _TAG_DESCRIBED.search(sentence))


def _moves(text: str, state: _State) -> list[Move]:
    """The moves of a narration line: a subject (a name, a pronoun, ``I``) followed by a movement
    verb (:data:`MOVE_VERBS`)."""
    verbs = "|".join(sorted((re.escape(v) for v in MOVE_VERBS), key=len, reverse=True))
    names = "|".join(sorted({re.escape(w) for c in state.characters.values() if not (c.protagonist and c.mentions == 0)
                             for w in name_words(c)}, key=len, reverse=True))
    who = rf"(?P<who>{names + '|' if names else ''}[Hh]e|[Ss]he|I)"
    pattern = re.compile(rf"{_LEAD}{_POSSESSIVE}{who}\s+{_ADVERB}(?P<verb>{verbs})\b(?P<rest>\s+(?:in|out|away|off|back|inside|outside)\b)?")
    total = max(_words(text), 1)
    moves = []
    for match in pattern.finditer(text):
        cid = state.who(match.group("who"))
        if cid is None:
            continue
        verb = match.group("verb") + (match.group("rest") or "")
        kind = MOVE_VERBS.get(verb.lower().strip(), MOVE_VERBS.get(match.group("verb").lower(), "walk"))
        if kind == "exit" and match.group("verb").lower() == "left" and re.match(r"\s+(?:the|a|an|his|her|their|my)\s+\w+\s+(?:on|in|at|behind|with)\b", text[match.end():]):
            continue   # "left the key on the table": not leaving
        moves.append(Move(cid, kind, round(_words(text[: match.start("verb")]) / total, 2), match.group(0).strip()))
    return moves


def _mentions(text: str, state: _State) -> list[str]:
    """Characters named in ``text`` (and the narrator for ``I`` / ``me`` in the first person),
    remembered as mentioned in that order."""
    found = [cid for _, cid in state.named(text)]
    if state.first_person and state.protagonist and re.search(r"\bI\b|\b[Mm]e\b|\b[Mm]y\b", text):
        found.append(state.protagonist)
    for cid in found:
        state.mention(cid)
    return list(dict.fromkeys(found))


def _subjects(text: str, state: _State) -> list[str]:
    """Characters that are the subject of a sentence of ``text`` (a name or ``I`` opening it)."""
    found = []
    for sentence in sentences(text):
        match = re.match(rf"(?:(?:{_TITLE_RE})\.?\s+)?([A-Z][a-z]+|I)\b", sentence)
        if match:
            cid = state.who(match.group(1))
            if cid is not None:
                found.append(cid)
    return found


def _read_paragraph(scene: StoryScene, number: int, paragraph: str, state: _State) -> None:
    """Add the paragraph's lines to ``scene`` (see :func:`read_story`)."""
    pieces = segments(paragraph)
    quotes = [k for k, (quoted, _) in enumerate(pieces) if quoted]
    speaker_of: dict[int, tuple[str | None, float, str, str | None]] = {}
    narration_text = " ".join(t for quoted, t in pieces if not quoted)
    for k in quotes:
        for _, cid in state.named(" ".join(t for quoted, t in pieces[:k] if not quoted)):
            state.mention(cid)   # "Bram looked up. 'Hm,' he said.": he is Bram
        tag = None
        if k + 1 < len(pieces) and not pieces[k + 1][0]:
            tag = _tag_in(pieces[k + 1][1], state, "after")
        if tag is None and k > 0 and not pieces[k - 1][0]:
            tag = _tag_in(pieces[k - 1][1], state, "before")
        if tag is not None and tag[0] != "?":
            who, emotion, how = tag
            kind = how.rsplit("(", 1)[-1].rstrip(")")
            speaker_of[k] = (who, _TAG_CONFIDENCE.get(kind, 0.7), how, emotion)
        elif tag is not None:
            speaker_of[k] = (None, 0.1, f"{tag[2]}: read by the narrator", tag[1])
    # quotes without a tag: the paragraph's other quotes' speaker, an action beat, alternation
    tagged = [v for v in speaker_of.values() if v[0] is not None]
    for k in quotes:
        if k in speaker_of and speaker_of[k][0] is not None:
            continue
        emotion = speaker_of.get(k, (None, 0, "", None))[3]
        if tagged:
            speaker_of[k] = (tagged[0][0], min(tagged[0][1], 0.9), "same paragraph as " + tagged[0][2], emotion)
            continue
        subjects = [s for s in _subjects(narration_text, state)]
        if len(set(subjects)) == 1:
            speaker_of[k] = (subjects[0], 0.6, "action beat: the subject of the paragraph's narration", emotion)
        elif subjects:
            speaker_of[k] = (subjects[-1], 0.45, "action beat: the last subject of the paragraph's narration", emotion)
        elif len(state.speakers) >= 2 and state.speakers[-1] != state.speakers[-2]:
            speaker_of[k] = (state.speakers[-2], 0.5, "alternation of a two-person exchange", emotion)
        else:
            present = [c for c in reversed(state.recent) if c not in state.speakers[-1:]]
            if present:
                speaker_of[k] = (present[0], 0.3, "the last character mentioned (no tag)", emotion)
            else:
                speaker_of[k] = (None, 0.1, "unknown: no tag, no character near", emotion)
    # the lines, in order
    pending_quote: Line | None = None
    for k, (quoted, piece) in enumerate(pieces):
        if quoted:
            who, confidence, how, emotion = speaker_of[k]
            if pending_quote is not None and pending_quote.speaker == who:
                head = pending_quote.text
                if head.endswith(",") and piece[:1].isupper() and not re.match(r"I\b", piece):
                    head = head[:-1] + "."   # "Go," she said. "Now." -> "Go. Now."
                pending_quote.text = f"{head} {piece}"
                continue
            pending_quote = Line(piece, number, who, True, confidence, how, emotion)
            scene.lines.append(pending_quote)
            if who is not None:
                state.mention(who)
                if not state.speakers or state.speakers[-1] != who:
                    state.speakers.append(who)
                state.characters[who].lines += 1
            continue
        kept = [s for s in sentences(piece) if not (_is_tag(s) and (k - 1 in speaker_of or k + 1 in speaker_of))]
        text = " ".join(kept).strip()
        if not re.search(r"\w", text):
            continue
        pending_quote = None
        for group in beat_groups(text):
            line = Line(group, number)
            line.mentions = _mentions(group, state)
            line.moves = _moves(group, state)
            scene.lines.append(line)
    for line in scene.lines:   # a quote's trailing comma ends a line
        if line.dialogue and line.text.endswith(","):
            line.text = line.text[:-1] + "."


def read_story(text: str) -> Story:
    """Read ``text`` (see the module doc)."""
    title, scenes = split_scenes(text)
    body = "\n".join(s.text for s in scenes)
    characters = find_characters(body)
    first_person, note, own_name = person_of(body)
    protagonist: str | None = None
    if first_person:
        protagonist = slug(own_name) if own_name else PROTAGONIST
        if protagonist not in characters:
            kind = "feminine" if own_name in FEMININE_NAMES else "masculine" if own_name in MASCULINE_NAMES else None
            characters[protagonist] = Character(protagonist, own_name or "Me", 0, kind, "name list" if kind else "no hint")
        characters[protagonist].protagonist = True
    state = _State(characters, first_person, protagonist)
    for character in characters.values():
        if character.protagonist and not own_name:
            continue
        pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(name_words(character), key=len, reverse=True)) + r")\b")
        state.patterns.append((pattern, character.id))
    state.order = list(dict.fromkeys(cid for _, cid in state.named(body)))
    for scene in scenes:
        state.speakers = []
        for number, paragraph in scene.paragraphs:
            _read_paragraph(scene, number, paragraph, state)
    words = _words(body)
    return Story(title, scenes, characters, first_person, note, words)
