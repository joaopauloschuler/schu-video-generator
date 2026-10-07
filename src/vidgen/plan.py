"""``vidgen plan``: a draft video from an outline or script, with no AI involved (DESIGN.md §61).

:func:`make_plan` turns the blocks of :func:`vidgen.outline.parse_outline` into scenes:

- **Structure.** A single H1 at the top is the title (a short first paragraph its subtitle, the
  rest of the opening prose the hook). The highest remaining heading level makes *sections*, the
  next one *units* inside them; each unit (heading + blocks) becomes one or more scenes. When the
  narration runs over :data:`CHAPTER_SECONDS` and there are at least three sections, every section
  starts with a silent ``chapter`` card and the video gets a ``progress_bar`` (the author guide's
  rule for videos over 2 minutes). A last section called Summary / Conclusion / Recap ... ends
  with an ``end_card``.
- **Cues → scene types.** A bullet list → ``bullets``, or ``icon_grid`` when every item is a
  short noun with a matching icon (:func:`vidgen.icons.match_icon`); numbered steps →
  ``process``; dated items → ``timeline``; a table → ``table`` (a numeric two-column table →
  ``bar_chart``); code → ``code`` (``code_walkthrough`` over :data:`CODE_LINES` lines); display
  maths → ``equation`` (``equation_derivation`` from three steps); an image → ``image``; a
  blockquote → ``quote``; ``A -> B -> C`` → ``diagram``; "A vs B" headings and pros / cons lists →
  ``comparison``; prose with a prominent number → ``stat``; other prose → ``bullets`` of its
  compressed sentences or a ``text_card``.
- **Narration.** Prose is cut into beats of 6-15 words (:func:`vidgen.prose.narration_beats`),
  matched to the scene's reveal steps (one beat per item, by shared words when the counts
  differ); a step without prose gets a placeholder beat marked TODO. On-screen texts are
  compressed (:func:`vidgen.prose.compress`): headings ≤ 5 words, items ≤ 6, labels ≤ 3.

Every scene carries the reason for its type and TODOs for the agent who refines the draft;
:mod:`vidgen.plan_yaml` writes them as ``# plan:`` / ``# TODO:`` comments. Deterministic: the
same input and options give the same plan. No manim import.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.icons import IconInfo, builtin_icons, match_icon
from vidgen.languages import language_rules, primary_language
from vidgen.outline import Block, Code, Heading, Image, ListBlock, Math, Paragraph, Quote, Table, plain
from vidgen.prose import compress, merge_short, narration_beats, sentence, split_long, split_sentences, words

#: Words per second used for the estimate (vidgen's ``narration.words_per_second`` default).
WORDS_PER_SECOND = 2.6
#: Seconds of silence after each beat (the init template's ``narration.pad``).
PAD = 0.35
#: Narration longer than this (seconds) with at least three sections gets chapter cards.
CHAPTER_SECONDS = 120.0
#: Length of a chapter card (silent).
CHAPTER_CARD_SECONDS = 2.5
#: Longest listing shown whole by ``code``; longer code becomes a ``code_walkthrough``.
CODE_LINES = 15
#: Most steps of a walkthrough the planner makes.
WALK_STEPS = 6
#: On-screen word limits of the author guide.
HEADING_WORDS = 5
TITLE_WORDS = 7
ITEM_WORDS = 6
LABEL_WORDS = 3
#: A list item of at most this many words is a short noun (a candidate for ``icon_grid``).
NOUN_WORDS = 3
#: Most items per ``bullets`` scene made from prose; most points per comparison column.
MAX_ITEMS = 5
MAX_POINTS = 4
#: A beat with more words than this gets a TODO (the guide: "a beat over ~20 words is two beats").
LONG_BEAT = 20

_SUMMARY = re.compile(
    r"^(?:\d+[.)]\s*)?(summary|conclusions?|recap|wrap[- ]?up|takeaways?|key takeaways|in summary|in short|next steps|"
    r"resumo|conclus(?:ão|ões|ao|oes)|recapitulando|próximos passos|resumen|conclusión|zusammenfassung|fazit|"
    r"riassunto|conclusione|résumé)\b",
    re.IGNORECASE,
)
_VS = re.compile(r"^(.+?)\s+(?:vs\.?|versus|x|contra)\s+(.+?)[?!.]?$", re.IGNORECASE)
_CHOICE = re.compile(r"^(.+?)\s+(?:or|ou|o|oder)\s+(.+?)\?$", re.IGNORECASE)
_PROS = re.compile(r"^(pros?|advantages?|benefits?|strengths?|good|prós|vantagens|benefícios|pontos fortes)\b", re.IGNORECASE)
_CONS = re.compile(r"^(cons?|disadvantages?|drawbacks?|weaknesses?|bad|risks?|contras|desvantagens|riscos|pontos fracos)\b", re.IGNORECASE)
_ARROW = re.compile(r"\s*(?:->|→|=>|⟶|-->)\s*")
_LEAD = re.compile(r"^(.{1,48}?)\s*(?::|—|–|\s-)\s+(.+)$")
_BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*[:.]?\s*(.*)$")
_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|"
    "october|november|december|janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
)
_DATE = re.compile(
    rf"^((?:(?:{_MONTHS})\.?\s+)?\d{{4}}s?(?:-\d{{2}}(?:-\d{{2}})?)?|q[1-4]\s+\d{{4}}|\d{{4}}\s*[-–]\s*\d{{2,4}})\s*(?::|—|–|-|,)?\s*(.*)$",
    re.IGNORECASE,
)
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class PlannedScene:
    """One scene of the draft: its config (``id``, ``type``, ``params``, beat texts or a silent
    ``duration``), why the planner chose the type (``reason``) and what the agent should check
    (``todos``)."""

    id: str
    type: str
    params: dict[str, Any]
    beats: list[str] = field(default_factory=list)
    duration: float | None = None
    reason: str = ""
    todos: list[str] = field(default_factory=list)

    def config(self) -> dict[str, Any]:
        """The scene as a ``video.yaml`` entry."""
        entry: dict[str, Any] = {"id": self.id, "type": self.type, "params": self.params}
        if self.beats:
            entry["beats"] = [{"text": text} for text in self.beats]
        else:
            entry["duration"] = self.duration
        return entry

    @property
    def words(self) -> int:
        """Words of narration."""
        return sum(words(b) for b in self.beats)

    @property
    def estimated_duration(self) -> float:
        """Seconds, estimated from the word count like an unvoiced preview."""
        if not self.beats:
            return float(self.duration or 0.0)
        return sum(words(b) / WORDS_PER_SECOND + PAD for b in self.beats)


@dataclass
class Plan:
    """The draft: ``title``, ``scenes``, the video's ``language``, whether it has chapter cards,
    the ``assets`` to copy into the project (``{project path: source file}``) and ``notes``
    (TODOs about the whole video)."""

    title: str
    scenes: list[PlannedScene]
    language: str | None = None
    chapters: bool = False
    assets: dict[str, Path] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def estimated_duration(self) -> float:
        """Seconds, estimated from the narration's word count."""
        return sum(s.estimated_duration for s in self.scenes)

    @property
    def todo_count(self) -> int:
        """TODOs in the plan (scenes' and the video's)."""
        return len(self.notes) + sum(len(s.todos) for s in self.scenes)


@dataclass(frozen=True)
class PlanOptions:
    """What the planner needs besides the blocks: a ``title`` overriding the document's (and the
    ``default_title`` when it has none), the ``language`` (BCP-47; ``None``: English rules), the
    folder images are relative to (``base``) and the icons to choose from (default: the built-in
    set)."""

    title: str | None = None
    default_title: str = "Untitled"
    language: str | None = None
    base: Path | None = None
    icons: dict[str, IconInfo] | None = None


@dataclass
class _Unit:
    """A heading and its blocks: one or more scenes; ``section`` is the top-level section it
    belongs to (-1: the opening), ``summary`` marks the closing unit."""

    heading: str
    blocks: list[Block]
    section: int
    summary: bool = False


@dataclass
class _Cue:
    """A visual cue of a unit with its ``label`` (a ``Pros:`` line, a deeper heading) and the
    prose beats written ``before`` it and, for the last cue, ``after`` it."""

    block: Block
    label: str = ""
    before: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)

    @property
    def raw(self) -> list[str]:
        """Every prose sentence of the cue, in order (tiny ones not merged)."""
        return [*self.before, *self.after]

    @property
    def prose(self) -> list[str]:
        """The cue's narration beats: its sentences with tiny ones merged."""
        return merge_short(self.raw)


class _Planner:
    """State of one planning run: options, used scene ids, assets."""

    def __init__(self, options: PlanOptions) -> None:
        self.options = options
        self.language = options.language
        self.icons = options.icons if options.icons is not None else builtin_icons()
        self.ids: set[str] = set()
        self.assets: dict[str, Path] = {}
        #: Links of the closing unit (shown on the end card).
        self.links: list[str] = []
        rules = language_rules(options.language)
        self.leaning = rules.clinging | rules.conjunctions | rules.prepositions

    # ----- helpers ---------------------------------------------------------------------------

    def scene_id(self, *hints: str) -> str:
        """A new scene id from the first usable hint (a heading, a label, the type)."""
        base = ""
        for hint in hints:
            words_ = [w for w in _SLUG.split(_ascii(hint).lower()) if w and w not in self.leaning]
            base = "_".join(words_[:3])[:24].strip("_")
            if base:
                break
        base = base or "scene"
        if base[0].isdigit():
            base = f"s{base}"
        candidate, n = base, 2
        while candidate in self.ids:
            candidate = f"{base}_{n}"
            n += 1
        self.ids.add(candidate)
        return candidate

    def beats(self, texts: Sequence[str]) -> list[str]:
        """Narration beats of prose paragraphs (inline Markdown removed)."""
        return [b for t in texts for b in narration_beats(plain(t).text, self.language)]

    def sentences(self, texts: Sequence[str]) -> list[str]:
        """The sentences of prose paragraphs, long ones cut, tiny ones not merged yet (so that
        one sentence per list item can still be matched)."""
        return [p for t in texts for s in split_sentences(plain(t).text, self.language) for p in split_long(s, self.language)]

    def short(self, text: str, limit: int) -> str:
        """``text`` (inline Markdown removed) compressed to ``limit`` words (never empty)."""
        clean = plain(text).text
        return compress(clean, limit, self.language) or " ".join(clean.split()[:limit]) or "TODO"

    def keywords(self, text: str) -> set[str]:
        """Content-word stems of ``text`` (first 5 letters of words of 3+ letters, not leaning
        words): what a beat and a label share when the beat talks about the label."""
        out = set()
        for raw in re.findall(r"[\wÀ-ÿ]+", plain(text).text.lower()):
            if len(raw) >= 3 and raw not in self.leaning:
                out.add(raw[:5])
        return out

    # ----- beats for reveal steps ---------------------------------------------------------------

    def fit(
        self,
        labels: list[str],
        step_texts: list[str | None],
        sentences: list[str],
        after: Sequence[str] = (),
        filler: list[str] | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """Beats for ``labels`` (one reveal step each) from the scene's prose ``sentences`` (the
        last ones, ``after``, written after the cue) and the steps' own sentences
        (``step_texts``); returns ``(intro beats, step beats, todos)``. In order, with the
        sentences as they are, then with tiny ones merged (:func:`merge_short`): one per step;
        the ones after the cue for the steps and the ones before as an intro. Then sentences
        matched to the steps by the words they share; the steps' own sentences; the merged beats
        as they are (extra ones hold the last step); placeholders for steps without a beat (the
        step's ``filler`` sentence, else its label as a sentence)."""
        k = len(labels)
        for prose, tail in ((sentences, list(after)), (merge_short(sentences), merge_short(list(after)))):
            if len(prose) == k:
                return [], list(prose), []
            if len(tail) == k and len(prose) > k:
                return merge_short(prose[: len(prose) - k]), tail, []
        starts = None if filler else self._match(labels, sentences)  # made-up labels share no words
        if starts is not None:
            bounds = [*starts, len(sentences)]
            joined = [" ".join(sentences[a:b]) for a, b in zip(bounds, bounds[1:])]
            return merge_short(sentences[: starts[0]]), joined, []
        prose = merge_short(sentences)
        if step_texts and all(step_texts):
            todo = "the narration repeats the items on screen: say why each one matters instead"
            return list(prose), [t for t in step_texts if t], [todo]
        if len(prose) > k:
            todos = []
            if len(prose) > k + 1:
                todos.append(f"{len(prose)} beats for {k} reveal step(s): the last beats hold the finished picture (split the scene or add actions)")
            return [], list(prose), todos
        beats = list(prose)
        todos = []
        placeholders: list[int] = []
        for i in range(len(prose), k):
            own = step_texts[i] if i < len(step_texts) else None
            if own:
                beats.append(own)
            else:
                beats.append(filler[i] if filler else sentence(labels[i]))
                placeholders.append(i + 1)
        if placeholders:
            which = f"beat {placeholders[0]} is a placeholder" if len(placeholders) == 1 else f"beats {_ranges(placeholders)} are placeholders"
            todos.append(f"{which} ({'generic' if filler else 'repeating the label'}): write what the viewer should hear")
        if any(step_texts[i] for i in range(len(prose), min(k, len(step_texts)))):
            todos.append("some beats read their item aloud: say why it matters instead")
        return [], beats, todos

    def _match(self, labels: list[str], prose: list[str]) -> list[int] | None:
        """For each label in order, the first later beat sharing a content word with it; ``None``
        unless every label finds one."""
        if not prose or len(prose) < len(labels):
            return None
        stems = [self.keywords(b) for b in prose]
        starts: list[int] = []
        position = 0
        for label in labels:
            want = self.keywords(label)
            found = next((j for j in range(position, len(prose)) if want & stems[j]), None)
            if found is None:
                return None
            starts.append(found)
            position = found + 1
        return starts

    def with_intro(self, intro: list[str], scene: PlannedScene, heading: str) -> list[PlannedScene]:
        """``scene`` preceded by its intro beats: merged into its first beat when short, else as
        scenes of their own (:meth:`prose_scenes`)."""
        if not intro:
            return [scene]
        if len(intro) == 1 and scene.beats and words(intro[0]) + words(scene.beats[0]) <= 18:
            scene.beats[0] = f"{intro[0]} {scene.beats[0]}"
            return [scene]
        return [*self.prose_scenes(heading, intro), scene]

    # ----- prose ---------------------------------------------------------------------------------

    def prose_scenes(self, heading: str, beats: list[str], *, closing: bool = False) -> list[PlannedScene]:
        """Scenes for narration without a visual cue: a ``stat`` where a beat has a prominent
        number, else ``bullets`` of the compressed beats (a ``text_card`` for a single beat)."""
        scenes: list[PlannedScene] = []
        rest = list(beats)
        while rest:
            spot = next((i for i, b in enumerate(rest[:2]) if _stat_params(b, self.language) is not None), None)
            if spot is not None:
                params = _stat_params(rest[spot], self.language)
                assert params is not None
                if spot:
                    scenes.extend(self.prose_scenes(heading, rest[:spot]))
                # beat 2 of a stat shows its comparison; without one, a second beat is dead air
                take = rest[spot : spot + (2 if "comparison" in params else 1)]
                rest = rest[spot + len(take) :]
                todos = ["check the stat's value and label; add a `context` line (source, period)"]
                if "comparison" in params:
                    todos.append("check `comparison.better` (is the higher or the lower value the good one?)")
                scene = PlannedScene(
                    self.scene_id(heading, "stat"), "stat", params, take,
                    reason=f"a sentence with a prominent number ({_number_text(params)}) -> stat", todos=todos,
                )
                scenes.append(scene)
                continue
            if len(rest) == 1:
                text = self.short(heading, TITLE_WORDS) if heading else self.short(rest[0], TITLE_WORDS)
                scenes.append(
                    PlannedScene(
                        self.scene_id(heading, text), "text_card", {"text": text}, rest[:1],
                        reason="one short thought without a visual cue -> text_card",
                        todos=["one statement shown big: keep it if it is worth it, else merge it into a neighbouring scene"],
                    )
                )
                break
            take, rest = rest[:MAX_ITEMS], rest[MAX_ITEMS:]
            if len(rest) == 1:  # never leave a lone beat for a scene of its own
                take, rest = take + rest, []
            items = [self.short(b, ITEM_WORDS) for b in take]
            params: dict[str, Any] = {"heading": self.short(heading, HEADING_WORDS)} if heading else {}
            params["items"] = items
            if len(items) > MAX_ITEMS:
                params["dim_previous"] = True
            todo = "items are compressed from the narration: make them keywords, or pick a visual type (vidgen guide scenes)"
            scenes.append(
                PlannedScene(
                    self.scene_id(heading, items[0]), "bullets", params, take,
                    reason=f"{len(take)} beats of prose without a visual cue -> bullets (one compressed item per beat)",
                    todos=[todo],
                )
            )
        if closing and scenes:
            scenes[-1].todos.append("closing prose: a recap of the takeaways reads best as one item per beat")
        return scenes

    # ----- cues ----------------------------------------------------------------------------------

    def list_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """A list: ``timeline`` (dated items), ``process`` (numbered steps), ``icon_grid`` (short
        nouns with icons) or ``bullets``."""
        block = cue.block
        assert isinstance(block, ListBlock)
        raw = [item.text for item in block.items]
        leads = [_lead(text) for text in raw]
        prose = cue.raw
        title = self.short(cue.label or heading, HEADING_WORDS) if (cue.label or heading) else ""
        todos: list[str] = []
        if any(item.children for item in block.items):
            todos.append("nested list items were left out: fold them into the narration or a scene of their own")
        step_texts = [_step_sentence(lead, desc, text) for (lead, desc), text in zip(leads, raw)]
        dates = [_DATE.match(plain(t).text) for t in raw]
        if 2 <= len(raw) <= 10 and all(d is not None and d[2] for d in dates):
            events = []
            for d in dates:
                assert d is not None
                events.append({"date": _date_value(d[1]), "title": self.short(d[2], 4)})
            labels = [str(e["title"]) for e in events]
            params: dict[str, Any] = ({"heading": title} if title else {}) | {"events": events}
            reason = f"{len(raw)} dated items -> timeline"
            return self.stepped("timeline", params, labels, step_texts, prose, heading, reason, todos, cue.after)
        if block.ordered and 2 <= len(raw) <= 8:
            labels = [self.short(lead or text, LABEL_WORDS) for (lead, _), text in zip(leads, raw)]
            params = ({"heading": title} if title else {}) | {"stages": labels}
            reason = f"{len(raw)} numbered steps -> process"
            todos.append("process: consider `input` / `output` labels and stage icons")
            return self.stepped("process", params, labels, step_texts, prose, heading, reason, todos, cue.after)
        nouns = [plain(lead or text).text.rstrip(".:;!") for (lead, _), text in zip(leads, raw)]
        if not block.ordered and 2 <= len(raw) <= 12 and all(0 < words(n) <= NOUN_WORDS for n in nouns):
            icons = self.icons_for(nouns)
            if icons is not None:
                items = [{"icon": icon, "label": noun} for icon, noun in zip(icons, nouns)]
                params = ({"heading": title} if title else {}) | {"items": items}
                choices = ", ".join(f"{icon} for '{noun}'" for icon, noun in zip(icons, nouns))
                todos.append(f"check the icon choice: {choices} (vidgen list-icons --search WORD)")
                reason = f"{len(raw)} short items, every one with a matching icon -> icon_grid"
                return self.stepped("icon_grid", params, nouns, step_texts, prose, heading, reason, todos, cue.after)
        labels = [self.short(lead or text, ITEM_WORDS) for (lead, _), text in zip(leads, raw)]
        params = ({"heading": title} if title else {}) | {"items": labels}
        if block.ordered:
            params["numbered"] = True
        if len(labels) > MAX_ITEMS:
            params["dim_previous"] = True
            todos.append(f"{len(labels)} items: the guide's limit is {MAX_ITEMS} per scene; split the list or cut items")
        kind = "numbered list" if block.ordered else "bullet list"
        reason = f"{kind} of {len(raw)} items -> bullets" + ("" if block.ordered else " (no icon for every item)")
        return self.stepped("bullets", params, labels, step_texts, prose, heading, reason, todos, cue.after)

    def icons_for(self, nouns: list[str]) -> list[str] | None:
        """A different matching icon for every noun (whole label, then its words, longest
        first), or ``None`` when one has none."""
        chosen: list[str] = []
        for noun in nouns:
            terms = ["-".join(noun.lower().split())]
            content = sorted((w for w in re.findall(r"[a-z]+", noun.lower()) if len(w) >= 3 and w not in self.leaning), key=lambda w: -len(w))
            for word in content:
                terms.append(word)
                if word.endswith("s") and len(word) > 3:
                    terms.append(word[:-1])
            found = None
            for term in terms:
                found = match_icon(self.icons, term, exclude=chosen)
                if found is not None:
                    break
            if found is None:
                return None
            chosen.append(found.name)
        return chosen

    def stepped(
        self,
        kind: str,
        params: dict[str, Any],
        labels: list[str],
        step_texts: list[str | None],
        prose: list[str],
        heading: str,
        reason: str,
        todos: list[str],
        after: Sequence[str] = (),
        filler: list[str] | None = None,
    ) -> list[PlannedScene]:
        """A scene revealing one step per label, its beats fitted (:meth:`fit`), intro first."""
        intro, beats, fit_todos = self.fit(labels, step_texts, prose, after, filler)
        scene = PlannedScene(self.scene_id(heading, labels[0] if labels else kind), kind, params, beats, reason=reason, todos=todos + fit_todos)
        return self.with_intro(intro, scene, heading)

    def table_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """A table: ``bar_chart`` when it is labels + one numeric column, else ``table``."""
        block = cue.block
        assert isinstance(block, Table)
        title = self.short(cue.label or heading, HEADING_WORDS) if (cue.label or heading) else ""
        rows = [[plain(c).text for c in row] for row in block.rows if any(c.strip() for c in row)]
        header = [plain(c).text for c in block.header]
        width = len(header)
        rows = [(row + [""] * width)[:width] for row in rows]
        todos: list[str] = []
        measured = [_measure(row[1], self.language) for row in rows] if width == 2 else []
        if width == 2 and 2 <= len(rows) <= 12 and all(m is not None for m in measured):
            values = [m[1] for m in measured if m is not None]
            units = {m[2] for m in measured if m is not None}
            prefixes = {m[0] for m in measured if m is not None}
            labels = [self.short(row[0], LABEL_WORDS) for row in rows]
            params: dict[str, Any] = {"title": title or self.short(header[1], HEADING_WORDS), "labels": labels, "values": values}
            if len(units) == 1 and next(iter(units)):
                unit = next(iter(units))
                params["unit"] = unit if unit == "%" else f" {unit}"
            elif len(units) > 1:
                todos.append(f"the values have different units ({', '.join(sorted(u or '-' for u in units))}): check them")
            if len(prefixes) == 1 and next(iter(prefixes)):
                decimals = max((len(str(v).split(".")[1]) if isinstance(v, float) else 0) for v in values)
                params["value_format"] = next(iter(prefixes)) + "{:,." + str(decimals) + "f}"
            prose = cue.raw if 2 <= len(cue.raw) <= 3 else cue.prose  # a beat per change of the chart
            mentioned = _mentioned(labels, prose[-1]) if len(prose) >= 2 else None
            if mentioned is not None:
                params["highlight"] = mentioned
            steps = 2 if mentioned is not None else 1
            todos.append("bar_chart: add a `caption` with the source of the numbers")
            if mentioned is None and len(prose) >= 2:
                todos.append("bar_chart: a `highlight` (the bar the narration is about) gives the last beat a change")
            beats = list(prose) or [sentence(f"{params['title']}")]
            if not prose:
                todos.append("beat 1 is a placeholder: say what the chart shows")
            elif len(prose) > steps + 1:
                todos.append(f"{len(prose)} beats over a chart that changes {steps} time(s): add actions (highlight, callout) or split")
            reason = f"a table of labels and numbers ({len(rows)} rows) -> bar_chart"
            scene = PlannedScene(self.scene_id(heading, title, "chart"), "bar_chart", params, beats, reason=reason, todos=todos)
            return [scene]
        cells = [[_cell(c, self.language) for c in row] for row in rows]
        params = ({"title": title} if title else {}) | ({"header": header} if any(header) else {}) | {"rows": cells}
        labels = [str(row[0]) or f"row {i + 1}" for i, row in enumerate(rows)]
        if width > 4:
            todos.append(f"{width} columns: tables over 4 columns get small, especially in 9:16")
        if len(cue.raw) < len(rows):
            params["reveal"] = "all"
            scene_beats = list(cue.prose) or [sentence(title or header[0] or "The table")]
            todos.append("reveal: all (fewer beats than rows); give each row a beat to reveal them one by one")
            if not cue.prose:
                todos.append("beat 1 is a placeholder: say what the table shows")
            reason = f"a table of {len(rows)} rows x {width} columns -> table"
            return [PlannedScene(self.scene_id(heading, title, "table"), "table", params, scene_beats, reason=reason, todos=todos)]
        reason = f"a table of {len(rows)} rows x {width} columns -> table (one row per beat)"
        return self.stepped("table", params, labels, [None] * len(labels), cue.raw, heading, reason, todos, cue.after)

    def code_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """Code: ``code`` (short; a highlight per beat by blank-line blocks) or
        ``code_walkthrough`` (long; a step per block)."""
        block = cue.block
        assert isinstance(block, Code)
        lines = block.code.split("\n")
        chunks = _chunks(lines)
        title = self.short(cue.label or heading, HEADING_WORDS) if (cue.label or heading) else ""
        params: dict[str, Any] = ({"title": title} if title else {}) | {"code": block.code}
        if block.language:
            params["language"] = _lexer(block.language)
        prose = cue.raw if 2 <= len(cue.raw) <= len(chunks) else cue.prose  # a beat per highlighted block
        todos: list[str] = []
        if len(lines) <= CODE_LINES:
            beats = list(prose) or [sentence(f"Here is {title.lower() or 'the code'}")]
            if not prose:
                todos.append("beat 1 is a placeholder: say what the code does")
            if len(beats) >= 2 and len(chunks) >= 2:
                params["highlight"] = [_span(a, b) for a, b in chunks[: len(beats)]]
                todos.append("check the highlighted lines per beat (`highlight`)")
            reason = f"a code block of {len(lines)} lines -> code"
            return [PlannedScene(self.scene_id(heading, title, "code"), "code", params, beats, reason=reason, todos=todos)]
        sentences = cue.raw
        count = max(2, min(WALK_STEPS, len(sentences) if len(sentences) >= 2 else len(chunks)))
        groups = _group(chunks, count)
        params["steps"] = [{"lines": _span(a, b)} for a, b in groups]
        labels = [f"lines {_span(a, b)}" for a, b in groups]
        todos.append("add a short `note` to the steps ({lines, note}) and check their line ranges")
        reason = f"a code block of {len(lines)} lines (over {CODE_LINES}) -> code_walkthrough"
        filler = [f"Look at lines {a} to {b}." if a != b else f"Look at line {a}." for a, b in groups]
        return self.stepped("code_walkthrough", params, labels, [None] * len(labels), sentences, heading, reason, todos, cue.after, filler)

    def math_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """Display maths: ``equation`` (one or two formulas) or ``equation_derivation``."""
        block = cue.block
        assert isinstance(block, Math)
        formulas = list(block.formulas)
        title = self.short(cue.label or heading, HEADING_WORDS) if (cue.label or heading) else ""
        todos = ["check that the LaTeX compiles and say the formula in words in the narration"]
        if len(formulas) >= 3:
            params: dict[str, Any] = ({"title": title} if title else {}) | {"steps": formulas}
            reason = f"{len(formulas)} formulas in a row -> equation_derivation"
            labels = [f"step {i + 1}" for i in range(len(formulas))]
            todos.append("add a `note` to the steps that need a reason ({tex, note})")
            return self.stepped("equation_derivation", params, labels, [None] * len(labels), cue.raw, heading, reason, todos, cue.after, _math_filler(len(labels)))
        params = {"latex": formulas[0] if len(formulas) == 1 else formulas}
        if title:
            params["caption"] = title
        labels = [f"formula {i + 1}" for i in range(len(formulas))]
        reason = "display maths -> equation" + (" (two steps)" if len(formulas) == 2 else "")
        return self.stepped("equation", params, labels, [None] * len(labels), cue.raw, heading, reason, todos, cue.after, _math_filler(len(labels)))

    def image_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """An image: copied into ``assets/`` when the file exists, else a ``generate:`` prompt."""
        block = cue.block
        assert isinstance(block, Image)
        caption = self.short(block.title or block.alt, ITEM_WORDS) if (block.title or block.alt) else ""
        params: dict[str, Any] = {}
        todos: list[str] = []
        source = self._image_source(block.path)
        if source is not None:
            params["path"] = self._asset(source)
            reason = "an image -> image (copied into assets/)"
        else:
            prompt = plain(block.alt or block.title or cue.label or heading).text or "an illustration"
            params["generate"] = prompt
            todos.append(f"picture '{block.path}' not found: put the file in assets/ and set `path`, or refine the prompt and run `vidgen imagegen`")
            reason = "an image whose file is missing -> image with a generate: prompt"
        if caption:
            params["caption"] = caption
        beats = list(cue.prose) or [sentence(caption or "Look at this picture")]
        if not cue.prose:
            todos.append("beat 1 is a placeholder: say what the picture shows")
        if len(beats) >= 2:
            params["ken_burns"] = True
        if len(beats) > 3:
            todos.append(f"{len(beats)} beats over one picture: split them, or add callouts")
        return [PlannedScene(self.scene_id(heading, caption, "image"), "image", params, beats, reason=reason, todos=todos)]

    def _image_source(self, path: str) -> Path | None:
        if re.match(r"^[a-z]+://", path) or self.options.base is None:
            return None
        candidate = (self.options.base / path).resolve()
        return candidate if candidate.is_file() else None

    def _asset(self, source: Path) -> str:
        """The project path ``assets/<name>`` for ``source`` (a new name when another file has it)."""
        name, n = source.name, 2
        while f"assets/{name}" in self.assets and self.assets[f"assets/{name}"] != source:
            name = f"{source.stem}_{n}{source.suffix}"
            n += 1
        self.assets[f"assets/{name}"] = source
        return f"assets/{name}"

    def quote_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """A blockquote -> ``quote``."""
        block = cue.block
        assert isinstance(block, Quote)
        text = plain(block.text).text
        params: dict[str, Any] = {"text": text}
        if block.author:
            params["author"] = plain(block.author).text
        if block.source:
            params["source"] = plain(block.source).text
        todos = []
        if words(text) > 25:
            todos.append(f"the quote has {words(text)} words: shorten it to its key sentence")
        beats = list(cue.prose)
        if not beats:
            who = params.get("author", "")
            beats = [sentence(f"As {who} put it: {text}" if who else text)]
            todos.append("narration reads the quote on screen: introduce it or say why it matters instead")
        beats, rest = beats[:2], beats[2:]  # a quote never changes: more beats would be dead air
        scene = PlannedScene(self.scene_id(heading, params.get("author", ""), "quote"), "quote", params, beats, reason="a blockquote -> quote", todos=todos)
        return [scene, *self.prose_scenes(heading, rest)]

    def diagram_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """``A -> B -> C`` lines -> ``diagram``: a node per distinct label, an edge per arrow."""
        block = cue.block
        assert isinstance(block, Paragraph)
        nodes: dict[str, tuple[str, str]] = {}  # lower-case label -> (id, label)
        edges: list[str] = []
        for line in _arrow_lines(block.text):
            ids = []
            for name in _ARROW.split(line.strip(" .;")):
                label = self.short(name.strip(" .;,"), LABEL_WORDS)
                if label.lower() not in nodes:
                    nodes[label.lower()] = (_node_id(label, {n for n, _ in nodes.values()}), label)
                ids.append(nodes[label.lower()][0])
            edges.extend(f"{a} -> {b}" for a, b in zip(ids, ids[1:]) if a != b)
        node_list = [{"id": node, "label": label} for node, label in nodes.values()]
        labels = [label for _, label in nodes.values()]
        title = self.short(cue.label or heading, HEADING_WORDS) if (cue.label or heading) else ""
        params: dict[str, Any] = ({"heading": title} if title else {}) | {"nodes": node_list, "edges": list(dict.fromkeys(edges))}
        reason = f"an arrow chain of {len(node_list)} nodes -> diagram"
        todos = ["check the diagram: node shapes / icons, and whether a `process` tells it better"]
        return self.stepped("diagram", params, labels, [None] * len(labels), cue.raw, heading, reason, todos, cue.after)

    def comparison_scenes(self, heading: str, sides: tuple[str, str] | None, lists: list[_Cue], prose: list[str]) -> list[PlannedScene]:
        """Two lists (pros / cons, or the two sides of an "A vs B" heading) -> ``comparison``."""
        columns = []
        tones = []
        for i, cue in enumerate(lists[:2]):
            block = cue.block
            assert isinstance(block, ListBlock)
            name = cue.label or (sides[i] if sides else ("Pros" if i == 0 else "Cons"))
            column: dict[str, Any] = {"heading": self.short(name, LABEL_WORDS)}
            tone = "positive" if _PROS.match(name) else "negative" if _CONS.match(name) else ""
            if tone:
                column["tone"] = tone
            tones.append(tone)
            column["points"] = [self.short(_lead(item.text)[0] or item.text, 4) for item in block.items[:MAX_POINTS]]
            columns.append(column)
        params: dict[str, Any] = {"heading": self.short(heading, HEADING_WORDS)} if heading else {}
        params["columns"] = columns
        if sides is not None and not any(tones):  # "A vs B" columns, not pros / cons
            params["vs"] = "vs"
        todos = []
        if any(len(c.block.items) > MAX_POINTS for c in lists[:2] if isinstance(c.block, ListBlock)):
            todos.append(f"points were cut to {MAX_POINTS} per column")
        labels = [str(c["heading"]) for c in columns]
        reason = ("pros / cons lists" if any(tones) else f"'{heading}' with two lists") + " -> comparison"
        steps = [_items_sentence(c["heading"], c["points"]) for c in columns]
        return self.stepped("comparison", params, labels, list(steps), prose, heading, reason, todos)

    def prose_comparison(self, heading: str, sides: tuple[str, str], beats: list[str]) -> list[PlannedScene] | None:
        """An "A vs B" heading over prose: each side's points from the beats that name it."""
        keys = [self.keywords(side) for side in sides]
        points: list[list[str]] = [[], []]
        for beat in beats:
            stems = self.keywords(beat)
            hits = [bool(k & stems) for k in keys]
            if hits[0] != hits[1]:
                side = 0 if hits[0] else 1
                if len(points[side]) < MAX_POINTS:
                    points[side].append(self.short(_after_side(beat, sides[side]), 4))
        if not all(points):
            return None
        columns = [{"heading": self.short(side, LABEL_WORDS), "points": pts} for side, pts in zip(sides, points)]
        params = {"heading": self.short(heading, HEADING_WORDS), "vs": "vs", "columns": columns}
        labels = [str(c["heading"]) for c in columns]
        reason = f"'{heading}' over prose naming both sides -> comparison (points from the sentences)"
        todos = ["the points are compressed from the narration: make them keywords"]
        return self.stepped("comparison", params, labels, [None, None], beats, heading, reason, todos)

    # ----- units ----------------------------------------------------------------------------------

    def unit_scenes(self, unit: _Unit) -> list[PlannedScene]:
        """The scenes of one unit: its cues with their prose, comparisons, prose scenes, and for a
        summary unit the end card."""
        heading = plain(unit.heading).text
        cues, trailing = self._cues(unit.blocks)
        scenes: list[PlannedScene] = []
        sides = _sides(heading)
        lists = [c for c in cues if isinstance(c.block, ListBlock)]
        pros_cons = len(lists) >= 2 and any(_PROS.match(c.label) for c in lists) and any(_CONS.match(c.label) for c in lists)
        if len(lists) >= 2 and (sides is not None or pros_cons):
            pair = lists[:2]
            prose = [b for c in pair for b in c.raw]
            if not [c for c in cues if c not in pair]:
                prose, trailing = prose + trailing, []
            cues = [c for c in cues if c not in pair]
            scenes.extend(self.comparison_scenes(heading, sides, pair, prose))
        if unit.summary:
            self.links = [link for block in unit.blocks for link in _block_links(block)]
            return scenes + self.summary_scenes(heading, cues, trailing)
        if not cues:
            if trailing and sides is not None and not scenes:
                compared = self.prose_comparison(heading, sides, trailing)
                if compared is not None:
                    return compared
            return scenes + (self.prose_scenes(heading, merge_short(trailing)) if trailing else [])
        cues[-1].after = trailing
        for cue in cues:
            scenes.extend(self.cue_scenes(cue, heading))
        return scenes

    def _cues(self, blocks: list[Block]) -> tuple[list[_Cue], list[str]]:
        """The unit's cues, each with the prose sentences before it, and the sentences after the
        last cue (all of them when the unit has no cue)."""
        cues: list[_Cue] = []
        pending: list[str] = []
        label = ""
        for block in blocks:
            if isinstance(block, Heading):
                label = plain(block.text).text
                continue
            if isinstance(block, Paragraph):
                text = plain(block.text).text
                if _arrow_lines(block.text):
                    cues.append(_Cue(block, label, self.sentences(pending)))
                    pending, label = [], ""
                elif _is_label(text):
                    label = text.rstrip(":").strip()
                else:
                    pending.append(block.text)
                continue
            if isinstance(block, Math) and cues and isinstance(cues[-1].block, Math) and not pending:
                previous = cues[-1].block
                cues[-1].block = Math(previous.formulas + block.formulas)
                continue
            cues.append(_Cue(block, label, self.sentences(pending)))
            pending, label = [], ""
        return cues, self.sentences(pending)

    def cue_scenes(self, cue: _Cue, heading: str) -> list[PlannedScene]:
        """The scene(s) of one cue."""
        block = cue.block
        if isinstance(block, ListBlock):
            return self.list_scenes(cue, heading)
        if isinstance(block, Table):
            return self.table_scenes(cue, heading)
        if isinstance(block, Code):
            return self.code_scenes(cue, heading)
        if isinstance(block, Math):
            return self.math_scenes(cue, heading)
        if isinstance(block, Image):
            return self.image_scenes(cue, heading)
        if isinstance(block, Quote):
            return self.quote_scenes(cue, heading)
        return self.diagram_scenes(cue, heading)

    def summary_scenes(self, heading: str, cues: list[_Cue], prose: list[str]) -> list[PlannedScene]:
        """The closing unit: its cues (a recap list), then an ``end_card`` narrated by the last
        beat of the prose after them (the call to action) and showing the section's links."""
        scenes: list[PlannedScene] = []
        for cue in cues:
            scenes.extend(self.cue_scenes(cue, heading))
        prose = merge_short(prose)
        closing = prose[-1:] if prose else []
        recap = prose[:-1]
        if recap:
            scenes.extend(self.prose_scenes(heading, recap, closing=True))
        links = self.links
        lines = [re.sub(r"^(?:https?://|mailto:)(?:www\.)?", "", u).rstrip("/") for u in links][:3]
        todos = []
        if closing:
            title = self.short(closing[0], 5)
            beats = closing
        else:
            title = self.short(heading, 5) if heading else "Thanks for watching"
            beats = [sentence(title)]
            todos.append("beat 1 is a placeholder: end with one call to action")
        params: dict[str, Any] = {"title": title}
        if lines:
            params["lines"] = lines
        else:
            todos.append("add `lines` with a link or the next step for the viewer")
        reason = f"the closing section ('{heading}')" if heading else "the closing prose"
        scenes.append(PlannedScene(self.scene_id("outro"), "end_card", params, beats, reason=f"{reason} -> end_card", todos=todos))
        return scenes

    def opening_scenes(self, title: str, doc_title: str, intro: list[Block]) -> list[PlannedScene]:
        """The ``title`` scene (a short first paragraph is its subtitle; the first beat of the
        opening prose its narration) and scenes for the rest of the opening blocks."""
        paragraphs = [b for b in intro if isinstance(b, Paragraph) and not _arrow_lines(b.text)]
        others = [b for b in intro if b not in paragraphs]
        params: dict[str, Any] = {"title": title}
        todos: list[str] = []
        if words(title) > TITLE_WORDS:
            todos.append(f"the title has {words(title)} words: titles read best with at most {TITLE_WORDS}")
        texts = [b.text for b in paragraphs]
        if texts:
            first = plain(texts[0]).text
            if words(first) <= 14 and len(split_sentences(first, self.language)) == 1 and _stat_params(first, self.language) is None:
                params["subtitle"] = first.rstrip(".")
                texts = texts[1:]
        beats = self.beats(texts)
        hook: list[PlannedScene] = []
        opening = _stat_params(beats[0], self.language) if beats else None
        if opening is not None:  # open on the number: the guide's hook
            count = 2 if "comparison" in opening else 1
            hook = self.prose_scenes("", beats[:count])
            hook[0].reason += " (the opening number is the hook, before the title)"
            beats = beats[count:]
        if beats:
            title_beats, rest = beats[:1], beats[1:]
        else:
            title_beats, rest = [sentence(title)], []
            if hook:
                todos.append("beat 1 is a placeholder reading the title: say what the video promises")
            else:
                todos.append("beat 1 is a placeholder: open with a hook (a question, a surprising number, a promise)")
        reason = "the document's title" + (" and its first short paragraph" if "subtitle" in params else "") + " -> title"
        if not doc_title:
            reason = "the video's title -> title"
        scenes = [*hook, PlannedScene(self.scene_id("opening"), "title", params, title_beats, reason=reason, todos=todos)]
        if rest:
            scenes.extend(self.prose_scenes("", rest))
        if others:
            scenes.extend(self.unit_scenes(_Unit("", others, -1)))
        return scenes


def make_plan(blocks: Sequence[Block], options: PlanOptions | None = None) -> Plan:
    """The draft video for the outline ``blocks`` (see the module doc)."""
    options = options or PlanOptions()
    planner = _Planner(options)
    rest = list(blocks)
    h1s = [b for b in rest if isinstance(b, Heading) and b.level == 1]
    doc_title = ""
    if rest and isinstance(rest[0], Heading) and rest[0].level == 1 and len(h1s) == 1:
        doc_title = plain(rest.pop(0).text).text
    title = options.title or doc_title or options.default_title
    levels = sorted({b.level for b in rest if isinstance(b, Heading)})
    top = levels[0] if levels else 0
    sub = levels[1] if len(levels) > 1 else None
    intro: list[Block] = []
    units: list[_Unit] = []
    section = -1
    for block in rest:
        if isinstance(block, Heading) and block.level == top:
            section += 1
            units.append(_Unit(block.text, [], section))
        elif isinstance(block, Heading) and block.level == sub:
            units.append(_Unit(block.text, [], section))
        elif units:
            units[-1].blocks.append(block)
        else:
            intro.append(block)
    if units and (_SUMMARY.match(plain(units[-1].heading).text) or _SUMMARY.match(plain(_section_heading(units, section)).text)):
        units[-1].summary = True
    scenes = planner.opening_scenes(title, doc_title, intro)
    starts: dict[int, int] = {}  # section -> index of its first scene
    for unit in units:
        made = planner.unit_scenes(unit)
        if made and unit.section not in starts and not unit.summary:
            starts[unit.section] = len(scenes)
        scenes.extend(made)
    notes: list[str] = []
    if not any(s.type == "end_card" for s in scenes):
        notes.append("no closing section (Summary / Conclusion): end with a recap scene and an `end_card` with a call to action")
    plan = Plan(title, scenes, options.language, False, planner.assets, notes)
    if plan.estimated_duration > CHAPTER_SECONDS and len(starts) >= 3:
        plan.chapters = True
        cards = []
        for number, (index, position) in enumerate(sorted(starts.items(), key=lambda kv: kv[1]), start=1):
            heading = plain(_section_heading(units, index)).text
            card = PlannedScene(
                planner.scene_id(f"chapter{number} {heading}"), "chapter",
                {"number": number, "title": planner.short(heading, HEADING_WORDS)}, [], CHAPTER_CARD_SECONDS,
                reason=f"narration over {CHAPTER_SECONDS / 60:.0f} minutes: section '{heading}' starts chapter {number}",
            )
            cards.append((position, card))
        for position, card in reversed(cards):
            scenes.insert(position, card)
    _beat_todos(plan)
    return plan


def _section_heading(units: list[_Unit], section: int) -> str:
    """The heading of section ``section`` (its first unit's)."""
    return next((u.heading for u in units if u.section == section), "")


def _beat_todos(plan: Plan) -> None:
    """TODOs about beat texts written for the eye rather than the ear."""
    for scene in plan.scenes:
        for i, beat in enumerate(scene.beats, start=1):
            if words(beat) > LONG_BEAT:
                scene.todos.append(f"beat {i} has {words(beat)} words: split it (6-15 words per beat)")
            if "(" in beat or re.search(r"\b(e\.g|i\.e|etc)\.", beat):
                scene.todos.append(f"beat {i} has parentheses or abbreviations: write it for the ear")
            if "$" in beat and re.search(r"\$[^$]+\$", beat):
                scene.todos.append(f"beat {i} has inline maths: say it in words")
            if re.search(r"https?://|www\.", beat):
                scene.todos.append(f"beat {i} reads a link aloud: show it on screen instead")


def _ascii(text: str) -> str:
    """``text`` with accents removed (for ids)."""
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _node_id(label: str, used: set[str]) -> str:
    """A diagram node id for ``label``, unique among ``used``."""
    base = "_".join(w for w in _SLUG.split(_ascii(label).lower()) if w)[:20].strip("_") or "node"
    if base[0].isdigit():
        base = f"n{base}"
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base}{n}"
        n += 1
    return candidate


def _arrow_lines(text: str) -> list[str]:
    """The lines of a paragraph (Markdown, one chain per line or per ``;``) that are arrow chains
    (``A -> B``), when the whole paragraph is made of them, each part a short label (at most 5
    words); ``[]`` otherwise. The lines come back without inline Markdown."""
    if not _ARROW.search(text):
        return []
    lines = [plain(line).text for line in re.split(r"(?<=[.;])\s+|\n", text) if line.strip()]
    chains = []
    for line in lines:
        parts = _ARROW.split(line.strip(" .;"))
        if len(parts) < 2 or any(not p.strip() or words(p) > 5 for p in parts):
            return []
        chains.append(line)
    return chains


def _is_label(text: str) -> bool:
    """A paragraph that only labels what follows: ``Pros:``, ``**Before**``."""
    return text.endswith(":") and words(text) <= 4


def _lead(text: str) -> tuple[str, str]:
    """``("Label", "description")`` of an item written ``**Label** description`` or ``Label:
    description`` (a lead of at most 5 words); ``("", text)`` otherwise."""
    bold = _BOLD_LEAD.match(text.strip())
    if bold is not None and bold[2]:
        return plain(bold[1]).text.rstrip(":."), plain(bold[2]).text
    clean = plain(text).text
    match = _LEAD.match(clean)
    if match is not None and words(match[1]) <= 5 and words(match[2]) >= 2:
        return match[1].strip(), match[2].strip()
    return "", clean


def _step_sentence(lead: str, desc: str, raw: str) -> str | None:
    """The narration a list item gives its own step: its description (or the whole item) when it
    is a sentence of at least 4 words; ``None`` for a short label."""
    if lead and words(desc) >= 4:
        return sentence(desc[0].upper() + desc[1:])
    text = plain(raw).text
    if not lead and words(text) >= 5:
        return sentence(text)
    return None


def _items_sentence(heading: str, points: list[str]) -> str:
    """A placeholder sentence naming a comparison column's points."""
    return sentence(f"{heading}: {', '.join(p.lower() for p in points)}")


def _sides(heading: str) -> tuple[str, str] | None:
    """The two sides of an "A vs B" (or "A or B?") heading."""
    text = plain(heading).text.strip()
    match = _VS.match(text) or _CHOICE.match(text)
    if match is None:
        return None
    a, b = match[1].strip(), match[2].strip()
    if words(a) > 4 or words(b) > 4:
        return None
    return a, b


def _after_side(beat: str, side: str) -> str:
    """The part of ``beat`` after the side's name (what it says about it), or the whole beat."""
    found = re.search(re.escape(side), beat, re.IGNORECASE)
    if found is None:
        return beat
    rest = beat[found.end() :].strip(" ,:")
    return rest if words(rest) >= 2 else beat


def _date_value(text: str) -> int | str:
    """A timeline date: a year as a number, anything else as written."""
    text = text.strip()
    return int(text) if re.fullmatch(r"\d{4}", text) else text


def _mentioned(labels: list[str], beat: str) -> str | None:
    """The label ``beat`` names (as a whole word), if exactly one."""
    hits = [label for label in labels if re.search(rf"(?<!\w){re.escape(label)}(?!\w)", beat, re.IGNORECASE)]
    return hits[0] if len(hits) == 1 else None


def _chunks(lines: list[str]) -> list[tuple[int, int]]:
    """1-based line ranges of the code's blocks (separated by blank lines)."""
    chunks: list[tuple[int, int]] = []
    start: int | None = None
    for n, line in enumerate(lines, start=1):
        if line.strip():
            if start is None:
                start = n
        elif start is not None:
            chunks.append((start, n - 1))
            start = None
    if start is not None:
        chunks.append((start, len(lines)))
    return chunks or [(1, max(1, len(lines)))]


def _group(chunks: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    """``chunks`` merged (or a single long one split) into ``count`` consecutive ranges."""
    if len(chunks) < count:
        first, last = chunks[0][0], chunks[-1][1]
        size = max(1, (last - first + 1) // count)
        edges = [first + i * size for i in range(count)] + [last + 1]
        return [(a, b - 1) for a, b in zip(edges, edges[1:]) if b > a]
    out = []
    for i in range(count):
        part = chunks[i * len(chunks) // count : (i + 1) * len(chunks) // count]
        out.append((part[0][0], part[-1][1]))
    return out


def _span(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}-{b}"


def _ranges(numbers: list[int]) -> str:
    """Consecutive ``numbers`` as ranges: ``[1, 2, 3, 5]`` -> ``1-3, 5``."""
    out: list[tuple[int, int]] = []
    for n in numbers:
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return ", ".join(_span(a, b) for a, b in out)


def _math_filler(count: int) -> list[str]:
    """Placeholder narration for formula steps."""
    return ["Here is the formula.", *["Then it becomes this." for _ in range(count - 1)]]


_LEXERS = {"py": "python", "js": "javascript", "ts": "typescript", "sh": "bash", "shell": "bash", "yml": "yaml", "c++": "cpp", "rs": "rust"}


def _lexer(language: str) -> str:
    """A Pygments lexer name for a fence's info string."""
    return _LEXERS.get(language, language)


def _number(text: str, language: str | None) -> float | None:
    """``text`` as a number, with the language's decimal mark (``3,5`` in Portuguese)."""
    text = text.strip()
    comma_decimal = primary_language(language) in ("pt", "es", "fr", "de", "it")
    if comma_decimal:
        text = text.replace(".", "").replace(" ", "").replace(",", ".") if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?|\d+(,\d+)?", text) else text
    else:
        text = text.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?", text) else text
    try:
        return float(text)
    except ValueError:
        return None


def _num(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _cell(text: str, language: str | None) -> str | int | float:
    """A table cell: a number when it is one, else its text."""
    value = _number(text, language)
    return _num(value) if value is not None else text


_MEASURE = re.compile(r"^([$€£]?)\s*(\d[\d.,\s]*?)\s*(%|[A-Za-zµ/]{1,6})?$")


def _measure(text: str, language: str | None) -> tuple[str, int | float, str] | None:
    """``(currency prefix, number, unit)`` of a numeric cell (``$1,200``, ``45 ms``, ``81%``)."""
    match = _MEASURE.match(text.strip())
    if match is None:
        return None
    value = _number(match[2], language)
    if value is None:
        return None
    return match[1], _num(value), match[3] or ""


_NUM = r"\d{1,3}(?:[,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_STAT_PATTERNS = (
    (re.compile(rf"\b(?:from|de)\s+({_NUM})\s*(%|percent|por cento)?\s+(?:to|para|a)\s+({_NUM})\s*(%|percent|por cento|x|×|times|vezes)?", re.IGNORECASE), "change"),
    (re.compile(rf"(?<![\w.,])({_NUM})\s?(%|percent\b|por cento\b)", re.IGNORECASE), "%"),
    (re.compile(rf"(?<![\w.,])({_NUM})\s?(x\b|×|times\b|vezes\b)", re.IGNORECASE), "x"),
    (re.compile(rf"([$€£])\s?({_NUM})\s*(k|m|bn|million|billion|thousand|mil|milhões|bilhões)?\b", re.IGNORECASE), "money"),
    (re.compile(rf"(?<![\w.,])({_NUM})\s+(million|billion|thousand|milhões|bilhões|milhão|bilhão)\b", re.IGNORECASE), "big"),
)
_MAGNITUDE = {"k": "k", "thousand": "k", "mil": "k", "m": "M", "million": "M", "milhão": "M", "milhões": "M", "bn": "B", "billion": "B", "bilhão": "B", "bilhões": "B"}


def _stat_params(beat: str, language: str | None) -> dict[str, Any] | None:
    """``stat`` params for a beat with a prominent number (a percentage, a multiple, money, a
    change "from X to Y", millions...); ``None`` when it has none."""
    for pattern, kind in _STAT_PATTERNS:
        match = pattern.search(beat)
        if match is None:
            continue
        params: dict[str, Any] = {}
        if kind == "change":
            old, new = _number(match[1], language), _number(match[3], language)
            if old is None or new is None:
                continue
            unit = (match[4] or match[2] or "").lower()
            params["value"] = _num(new)
            if unit in ("%", "percent", "por cento"):
                params["suffix"] = "%"
            elif unit in ("x", "×", "times", "vezes"):
                params["suffix"] = "x"
            params["comparison"] = {"value": _num(old), "kind": "before"}
        elif kind == "money":
            value = _number(match[2], language)
            if value is None:
                continue
            params["prefix"] = match[1]
            params["value"] = _num(value)
            if match[3]:
                params["suffix"] = _MAGNITUDE.get(match[3].lower(), "")
        else:
            value = _number(match[1], language)
            if value is None:
                continue
            params["value"] = _num(value)
            params["suffix"] = {"%": "%", "x": "x"}.get(kind) or _MAGNITUDE.get(match[2].lower(), "")
        if not params.get("suffix"):
            params.pop("suffix", None)
        after = beat[match.end() :].strip(" ,.;:!?")
        before = beat[: match.start()].strip(" ,.;:!?")
        if words(after) >= 2:
            label = compress(after, ITEM_WORDS, language)
            label = label[:1].lower() + label[1:]  # it follows the number: "73% of developers..."
        else:
            label = compress(f"{before} {after}", ITEM_WORDS + 1, language)
        if label:
            params["label"] = label
        if primary_language(language) in ("pt", "es", "fr", "de", "it"):
            params["decimal_mark"] = ","
            params["thousands"] = "."
        return params
    return None


def _number_text(params: dict[str, Any]) -> str:
    """How the stat's number reads (``46%``)."""
    value = params["value"]
    return f"{params.get('prefix', '')}{value}{params.get('suffix', '')}"


def _block_links(block: Block) -> list[str]:
    """Link targets named in a block's text."""
    texts: list[str] = []
    if isinstance(block, (Paragraph, Heading)):
        texts = [block.text]
    elif isinstance(block, ListBlock):
        texts = [i.text for i in block.items] + [c for i in block.items for c in i.children]
    elif isinstance(block, Quote):
        texts = [block.text]
    return [link for t in texts for link in plain(t).links if re.match(r"^(?:https?://|mailto:)", link)]
