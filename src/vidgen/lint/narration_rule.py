"""The lint rules comparing what the narration says with what the picture shows (DESIGN.md §87.10).

``said_before_shown``: the narration names an on-screen label (a short text of the scene: a
diagram node, a callout, an axis title...) clearly before that label is on screen. ``unsaid_reveal``
(off by default): a beat brings new labels and the scene's narration never names any of them.

Both read the scene's layout dump (every captured frame, beat-end stills and mid-beat ones) and
the beats' word times (:func:`vidgen.word_anchors.beat_words`: the TTS alignment, else the
estimate). A label is *visible* at a frame when the frame records it; it was surely *not yet
visible* at the last frame before its first one. A ``reveal`` / ``callout`` / ``transform``
action of that beat narrows the moment: a callout whose label it is, or an action on a word the
label says (``at: "@decoder"``), shows it at the action's time. Words are compared in lower
case without accents, with English plural and verb endings removed, stop words and numbers
left out; a label is a text of at most ``max_words`` words (longer texts are sentences, not
names). The runner fills :attr:`SceneContext.narration` with :func:`narration_picture`. No manim.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidgen.config import SaidBeforeShownRule, UnsaidRevealRule
from vidgen.languages import primary_language
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.textnorm import fold

if TYPE_CHECKING:
    from vidgen.project import Project

#: Actions that bring something on screen at their time: the built-in ones, the cell-biology
#: scenes' actions that bring labels, captions, badges or a zoomed view's part names (§95.14), the
#: genetics scenes' actions that bring gametes, cells, tables, cards and plots (§96.18), and the
#: plot and calculation actions that bring fits, notes, growing series and worked steps (§97.11),
#: the orbit actions that bring sectors, shots, burns with their Δv labels and a flyby (§98.8).
SHOWING_ACTIONS = frozenset({
    "reveal", "callout", "transform",
    "zoom_to", "advance", "checkpoint", "signal", "knockout", "drug", "inhibit", "amplify", "transcribe", "cap", "splice", "polyadenylate",
    "export", "translate", "target_er", "glycosylate", "fold", "to_golgi", "secrete", "transport", "set_state", "diffuse", "osmosis",
    "action_potential", "motor_walk", "endocytosis", "exocytosis",
    "form_gametes", "fill", "count", "ratio", "chi_square", "deduce", "analyse", "risk", "cross_over", "measure", "rearrange", "mutate",
    "scan", "cleave", "repair", "run", "simulate", "resample", "regional",
    "fit", "annotate", "grow", "substitute", "compute", "convert",
    "sweep", "launch", "burn", "flyby",
})

_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")
_STOP_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        """a about above after again all also am an and any are as at be because been before being below between both but by
        can could did do does doing down during each else every few for from further had has have having he her here hers
        him his how i if in into is it its itself just let lets me more most my no nor not now of off on once one only or
        other our ours out over own same she should so some such than that the their theirs them then there these they
        this those through to too under until up us very was we were what when where which while who whom why will with
        would you your yours vs via per""".split()
    ),
    "pt": frozenset(
        """a ao aos as até com como da das de do dos e é em entre era essa esse esta este eu foi há isso isto já la lhe mais
        mas me mesmo muito na nas não nem no nos o os ou para pela pelo por qual quando que se sem ser seu sua são só também
        te tem um uma umas uns vai vez""".split()
    ),
}
# folded once (the narration and the labels are folded before the lookup)
_STOP_WORDS = {code: frozenset(fold(w) for w in words) for code, words in _STOP_WORDS.items()}


def stem(word: str, language: str | None = None) -> str:
    """``word`` (folded) without its inflection: English plural, ``-ing``, ``-ed`` and a final
    ``e`` (``moving`` = ``moves`` = ``move``); other languages only a plural ``s``."""
    if primary_language(language) != "en":
        return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif (len(word) > 4 and word.endswith("es") and word[-3] in "sxz") or word.endswith(("ches", "shes")):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":  # running -> runn -> run
        word = word[:-1]
    return word


def words_of(text: str) -> list[str]:
    """The folded words of ``text`` (letters only: numbers and symbols are left out)."""
    return [fold(m.group()) for m in _WORD.finditer(unicodedata.normalize("NFKC", text).replace("’", "'"))]


def content_stems(words: Iterable[str], language: str | None = None) -> list[str]:
    """The stems of ``words`` (folded) that name something: no stop words, no single letters."""
    stops = _STOP_WORDS.get(primary_language(language), frozenset())
    return [stem(w, language) for w in words if len(w) > 1 and w not in stops]


# ----- what the picture shows -------------------------------------------------------------------


@dataclass
class ShownLabel:
    """A label of the scene: its ``text`` (as first shown), ``stems`` (its content words),
    ``words`` (how many words it has),
    ``beat`` and ``time`` of the first frame showing it, ``hidden_until`` the latest scene time
    it is known not to be on screen yet (``None``: from the scene's start on, as far as the
    frames tell), ``screen`` the content words of each other text on screen then, ``obj`` its
    layout object (the first frame's)."""

    text: str
    stems: frozenset[str]
    words: int
    beat: str | None
    time: float
    hidden_until: float | None
    screen: list[frozenset[str]] = field(default_factory=list)
    obj: dict[str, Any] = field(default_factory=dict)

    def on_screen_elsewhere(self) -> bool:
        """Whether another text on screen around its arrival already says all its words."""
        return any(self.stems <= other for other in self.screen)


@dataclass(frozen=True)
class ShowingAction:
    """A ``reveal`` / ``callout`` / ``transform`` of a beat at scene time ``time``: the content
    words of a callout's ``label`` and of the action's word anchor (``None`` when it has none)."""

    beat: str
    time: float
    label: frozenset[str] | None = None
    anchor: frozenset[str] | None = None


def _label_texts(frame: dict[str, Any], min_opacity: float) -> list[dict[str, Any]]:
    """The frame's scene texts (no overlays: captions repeat the narration; no speech bubbles; no
    name tags: a tag names a speaker already on screen, DESIGN.md §89.12)."""
    return [
        o
        for o in frame["objects"]
        if o.get("kind") == "text" and o.get("text") and "overlay" not in o and "bubble" not in o and "name_tag" not in o
        and o["opacity"] >= min_opacity
    ]


def shown_labels(
    layout: dict[str, Any], actions: Sequence[ShowingAction] = (), *, language: str | None = None, max_words: int = 4, min_opacity: float = 0.1
) -> list[ShownLabel]:
    """The labels a scene shows (texts of 1 to ``max_words`` words with a content word), each
    once, in the order they first appear. Labels with the same content words are one label (a
    live value label ``slope 0.50`` -> ``slope 1.20``)."""
    frames = sorted(layout.get("frames", []), key=lambda f: f["time"])
    first: dict[frozenset[str], ShownLabel] = {}
    seen_texts: list[list[tuple[frozenset[str], dict[str, Any]]]] = []
    for index, frame in enumerate(frames):
        texts = []
        for obj in _label_texts(frame, min_opacity):
            words = words_of(obj["text"])
            texts.append((frozenset(content_stems(words, language)), obj, len(words)))
        seen_texts.append([(stems, obj) for stems, obj, _ in texts])
        for stems, obj, count in texts:
            if not stems or count > max_words or stems in first:
                continue
            before = frames[index - 1] if index else None
            label = ShownLabel(" ".join(obj["text"].split()), stems, count, frame.get("beat"), float(frame["time"]), None if before is None else float(before["time"]), obj=obj)
            _narrow(label, frame, actions)
            others = (seen_texts[index - 1] if index else []) + seen_texts[index]
            label.screen = [s for s, o in others if s != stems and s]
            first[stems] = label
    return list(first.values())


def _narrow(label: ShownLabel, frame: dict[str, Any], actions: Sequence[ShowingAction]) -> None:
    """Move ``hidden_until`` to the time of the action of the label's beat that shows it: a
    callout with its words as label, else an action on a word the label says."""
    mine = [a for a in actions if a.beat == label.beat and a.time <= float(frame["time"]) + 1e-6]
    match = next((a for a in mine if a.label == label.stems), None) or next((a for a in mine if a.anchor and a.anchor <= label.stems), None)
    if match is not None and (label.hidden_until is None or match.time > label.hidden_until):
        label.hidden_until = match.time


# ----- what the narration says ------------------------------------------------------------------


@dataclass(frozen=True)
class SpokenWord:
    """A content word of the narration: its ``stem``, the ``word`` as written, its ``beat``,
    when it starts (scene seconds) and its place among the beat's content words."""

    stem: str
    word: str
    beat: str
    time: float
    index: int


def spoken_words(beat_id: str, words: Sequence[tuple[str, float]], language: str | None = None) -> list[SpokenWord]:
    """The content words of a beat from its written words and their start times (scene seconds)."""
    stops = _STOP_WORDS.get(primary_language(language), frozenset())
    out: list[SpokenWord] = []
    for written, start in words:
        for word in words_of(written):
            if len(word) > 1 and word not in stops:
                out.append(SpokenWord(stem(word, language), written.strip(".,;:!?\"'()[]{}…“”«»"), beat_id, start, len(out)))
    return out


def first_mention(stems: frozenset[str], spoken: Sequence[SpokenWord]) -> list[SpokenWord]:
    """The first place the narration says all of ``stems`` close together (within
    ``len(stems) + 1`` content words of one beat): its content words up to the last one needed
    (empty when it never does)."""
    span = len(stems) + 1
    for i, word in enumerate(spoken):
        if word.stem not in stems:
            continue
        window = [w for w in spoken[i : i + span] if w.beat == word.beat]
        if stems <= {w.stem for w in window}:
            last = max(next(k for k, w in enumerate(window) if w.stem == s) for s in stems)
            return window[: last + 1]
    return []


@dataclass
class NarrationPicture:
    """One scene's labels and spoken words, as the narration rules read them."""

    labels: list[ShownLabel]
    spoken: list[SpokenWord]
    first_beat: str | None


def target_texts(project: Project, scene_id: str | None) -> Callable[[str], str | None]:
    """What each action target of scene ``scene_id`` is called on screen, from its scene type's
    ``target_text(params, name)`` when it has one (the cell-biology scenes: a cell object's
    label, a pathway node's, a molecule's); ``None`` for the others."""
    from vidgen import registry
    from vidgen.errors import VidgenError

    spec = next((s for s in project.config.scenes if s.id == scene_id), None)
    entry = registry.find(spec.type) if spec is not None else None
    hook = getattr(entry.cls, "target_text", None) if entry is not None else None
    if spec is None or hook is None:
        return lambda name: None
    try:
        params = entry.cls.parse_params(spec.params, spec.id)
    except VidgenError:
        return lambda name: None

    def text(name: str) -> str | None:
        try:
            return hook(params, name)
        except (VidgenError, KeyError, ValueError):
            return None

    return text


def narration_picture(project: Project, layout: dict[str, Any], activity: dict[str, Any], max_words: int, scene_id: str | None = None) -> NarrationPicture:
    """The :class:`NarrationPicture` of a rendered scene: word times from the beats' audio
    (else the estimate) over the narration times of the activity file; an action without a
    ``label`` of its own shows its target's on-screen name (:func:`target_texts`)."""
    from vidgen.word_anchors import beat_words, parse_word_anchor

    language = project.config.language
    spoken: list[SpokenWord] = []
    actions: list[ShowingAction] = []
    named = target_texts(project, scene_id)
    for entry in activity["beats"]:
        beat = project.beat(entry["id"])
        seconds = max(float(entry["end"]) - float(entry["start"]), 0.0)
        _, times = beat_words(project, beat, seconds or None)
        start = float(entry["start"])
        spoken += spoken_words(beat.id, [(w.text, start + w.start) for w in times], language)
        for act in beat.actions:
            if act.action not in SHOWING_ACTIONS:
                continue
            label = (act.model_extra or {}).get("label")
            if not isinstance(label, str) and len(act.targets()) == 1:
                label = named(act.targets()[0])
            anchor = parse_word_anchor(act.anchor).words if act.anchor else None
            actions.append(
                ShowingAction(
                    beat.id,
                    start + act.fraction * seconds,
                    frozenset(content_stems(words_of(label), language)) if isinstance(label, str) else None,
                    frozenset(content_stems(words_of(" ".join(anchor)), language)) or None if anchor else None,
                )
            )
    spoken = [SpokenWord(w.stem, w.word, w.beat, w.time, i) for i, w in enumerate(spoken)]
    labels = shown_labels(layout, actions, language=language, max_words=max_words, min_opacity=project.config.lint.min_opacity)
    first = activity["beats"][0]["id"] if activity["beats"] else None
    return NarrationPicture(labels, spoken, first)


# ----- the rules --------------------------------------------------------------------------------


@rule("said_before_shown", scope="scene")
def said_before_shown(ctx: SceneContext, settings: SaidBeforeShownRule) -> Iterator[Issue]:
    """The narration names an on-screen label more than ``min_lead`` seconds before it shows."""
    picture = ctx.narration
    if picture is None:
        return
    for label in picture.labels:
        if label.hidden_until is None or label.words > settings.max_words or label.on_screen_elsewhere():
            continue
        mention = first_mention(label.stems, picture.spoken)
        if not mention or mention[0].time + settings.min_lead > label.hidden_until:
            continue
        arrival = [w for w in picture.spoken if w.beat == label.beat and w.time >= label.hidden_until - settings.min_lead]
        if first_mention(label.stems, arrival):
            continue  # named again as it shows: the early word was in passing ("a render starts...")
        said, phrase = mention[0], " ".join(w.word for w in mention)
        lead = label.hidden_until - said.time if label.beat == said.beat else None
        when = f"{lead:.1f} s later" if lead is not None else f"only in beat '{label.beat}'"
        yield Issue(
            f"beat '{said.beat}' says \"{phrase}\" at {said.time:.1f} s, but '{label.text}' appears {when}: "
            f"show it on the word ({{reveal: <target>, at: \"@{said.word}\"}}) or say it when it shows",
            None,
            objects=(label.obj,),
            value=round(label.hidden_until - said.time, 2),
            limit=settings.min_lead,
            beat=said.beat,
            time=said.time,
        )


@rule("unsaid_reveal", scope="scene", default="info")
def unsaid_reveal(ctx: SceneContext, settings: UnsaidRevealRule) -> Iterator[Issue]:
    """A beat brings new labels that the scene's narration never names (off by default)."""
    picture = ctx.narration
    if picture is None:
        return
    said = {w.stem for w in picture.spoken}
    starts = {beat["id"]: float(beat["start"]) for beat in ctx.beats}
    by_beat: dict[str, list[ShownLabel]] = {}
    for label in picture.labels:
        if label.beat not in (None, picture.first_beat) and label.hidden_until is not None and label.words <= settings.max_words:
            by_beat.setdefault(label.beat, []).append(label)
    for beat, labels in by_beat.items():
        if any(label.stems & said for label in labels):
            continue
        names = ", ".join(f"'{label.text}'" for label in labels[:4]) + ("…" if len(labels) > 4 else "")
        yield Issue(
            f"beat '{beat}' shows {names}, which the narration never names: say what the viewer should look at",
            None,
            objects=(labels[0].obj,),
            beat=beat,
            time=starts.get(beat, labels[0].time),
        )
