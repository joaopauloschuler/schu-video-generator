"""The calculation lint rules (DESIGN.md §97.11): numbers in the narration and on screen against
what the video's ``calculation`` scenes compute.

``calc_numbers`` (a number said or shown for a calculation's value that differs from it beyond
the way it was written), ``calc_units`` (a value in a unit of the wrong kind for its quantity, or
off by a power of 1000) and ``calc_sigfigs`` (more significant figures than the inputs give: a
calculation's ``sig``, or a number said for a result). A number refers to a value of its own
scene when its unit has that value's dimension (a unique result of that dimension, else the one
the sentence names) and to another scene's result only when the sentence names it (its meaning or
name); a pure number only when the sentence names the value. The knowledge (numbers and units in
words and digits, comparisons) is in :mod:`vidgen.quantities.accuracy`; the runner adds
:func:`calc_issues` to :attr:`SceneContext.science`, and the findings are reported like the
``science_*`` rules'.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues, _params
from vidgen.quantities import accuracy as qa
from vidgen.quantities.units import DIMENSIONLESS, describe_dim

if TYPE_CHECKING:
    from vidgen.config import LintRules, SceneConfig
    from vidgen.project import Project

#: The rules of this module, in :data:`vidgen.config.LINT_RULES` order.
CALC_RULES: tuple[str, ...] = ("calc_numbers", "calc_units", "calc_sigfigs")
#: Params of any scene type whose text is shown on screen (cards, titles, captions, lists).
SCREEN_KEYS = ("title", "subtitle", "heading", "caption", "text", "body", "lines", "bullets", "items", "points", "note", "footer")
_cache: dict[int, tuple[Any, dict[str, list[qa.Candidate]], dict[str, list[Any]]]] = {}


def _stems(text: str) -> list[tuple[str, int]]:
    """The content stems of ``text`` with where each word starts."""
    from vidgen.lint.narration_rule import content_stems, words_of

    out = []
    for m in re.finditer(r"[^\W\d_]+(?:'[^\W\d_]+)*", text):
        if qa.is_number_word(m.group()):
            continue
        stems = content_stems(words_of(m.group()))
        if stems:
            out.append((stems[0], m.start()))
    return out


def candidates(project: Project) -> tuple[dict[str, list[qa.Candidate]], dict[str, list[Any]]]:
    """Every calculation scene's symbols and results (``{scene id: [Candidate]}``) and its
    results' warnings (``{scene id: [CalcResult]}``), computed once per project."""
    key = id(project)
    if key in _cache and _cache[key][0] is project:
        return _cache[key][1], _cache[key][2]
    found: dict[str, list[qa.Candidate]] = {}
    results: dict[str, list[Any]] = {}
    for spec in project.config.scenes:
        if spec.type != "calculation":
            continue
        params = _params(spec)
        if params is None:
            continue
        try:
            worked = params.worked(project)
        except Exception:  # noqa: BLE001 - validation reports it
            continue
        rows: list[qa.Candidate] = []
        # a result is shown in its first conversion when it has one (29.8 km/s rather than 2.98 × 10⁴ m/s)
        values = [(v, v, False) for v in worked.symbols.values()] + [(r.value, (r.conversions or [r.value])[0], True) for r in worked.results]
        for v, display, is_result in values:
            q = v.quantity
            stems = frozenset(s for s, _ in _stems(str(v.meaning)))
            rows.append(qa.Candidate(v.name, str(v.meaning), float(q.value), q.dim, q.sig, display.value_text(), display.unit, is_result, spec.id,
                                     stems))
        # the parts of an intermediate line (no name: a number said for one agrees, none is named)
        for r in worked.results:
            for part in (p for step in r.steps for p in step.values):
                q = part.quantity
                rows.append(qa.Candidate("", "", float(q.value), q.dim, q.sig, part.value_text(), part.unit, False, spec.id))
        found[spec.id] = rows
        results[spec.id] = list(worked.results)
    _cache.clear()
    _cache[key] = (project, found, results)
    return found, results


def _mention(c: qa.Candidate, sentence: str, words: list[tuple[str, int]]) -> tuple[int, frozenset[str]] | None:
    """Where the sentence names ``c`` and the meaning words it uses (all of them for its
    name), or ``None``."""
    if len(c.name) >= 2:
        m = re.search(rf"(?<![\w]){re.escape(c.name)}(?![\w])", sentence)
        if m is not None:
            return m.start(), c.stems | {"\0name"}
    hits = [(s, at) for s, at in words if s in c.stems]
    return (hits[0][1], frozenset(s for s, _ in hits)) if hits else None


def _mentions(sentence: str, own: list[qa.Candidate], others: list[qa.Candidate]) -> tuple[dict[int, int], dict[int, int]]:
    """``(named, hinted)``: candidates (by ``id``) the sentence names — by name, or by at least
    two of their meaning's words (all of them when it has one) — and the scene's own values it
    names by a single word no other value of the scene has ("carriers" for "carrier
    frequency"), each with where."""
    words = _stems(sentence)
    named: dict[int, int] = {}
    hinted: dict[int, int] = {}
    for c in own + others:
        found = _mention(c, sentence, words)
        if found is None:
            continue
        at, hits = found
        if "\0name" in hits or len(hits) >= min(2, len(c.stems)):
            named[id(c)] = at
        elif any(c is o for o in own) and not any(hits & o.stems for o in own if o is not c):
            hinted[id(c)] = at
    return named, hinted


def _who(c: qa.Candidate, scene_id: str) -> str:
    what = f"{c.meaning} ({c.name})" if c.meaning else c.name
    return what + (f" in scene '{c.scene}'" if c.scene != scene_id else "")


def screen_texts(spec: SceneConfig) -> list[tuple[str, str]]:
    """``(where, text)`` of a scene's own words on screen: the params of :data:`SCREEN_KEYS`
    (strings and lists of strings), a plot's notes and labels, callout labels."""
    out: list[tuple[str, str]] = []
    for key in SCREEN_KEYS:
        value = spec.params.get(key)
        if isinstance(value, str) and value:
            out.append((key, value))
        elif isinstance(value, list):
            out += [(f"{key}[{k}]", v) for k, v in enumerate(value, start=1) if isinstance(v, str)]
    if spec.type == "plot":
        for k, a in enumerate(spec.params.get("annotations") or [], start=1):
            if isinstance(a, dict) and isinstance(a.get("text"), str) and a["text"]:
                out.append((f"annotations[{k}].text", a["text"]))
    for beat in spec.beats:
        for act in beat.actions:
            label = act.options.get("label")
            if isinstance(label, str):
                out.append((f"beat '{beat.id}' {act.action} label", label))
    return out


def calc_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every calculation finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in CALC_RULES if getattr(rules, name).severity != "off"}
    if not on:
        return []
    out: list[ScienceIssue] = []
    seen: set[tuple[str, str | None, str]] = set()
    first = spec.beats[0].id if spec.beats else None

    def add(rule_name: str, beat: str | None, message: str) -> None:
        if rule_name in on and (rule_name, beat, message) not in seen:
            seen.add((rule_name, beat, message))
            out.append(ScienceIssue(rule_name, beat, message))

    found, results = candidates(project)
    own = found.get(scene_id, [])
    # another scene's results are named in scenes without numbers of their own (a calculation
    # has its values, a plot with fits its fitted ones: plot_fit_claims)
    has_own_numbers = spec.type == "calculation" or spec.type == "plot" and bool(spec.params.get("fits"))
    others = [] if has_own_numbers else [c for sid, rows in found.items() if sid != scene_id for c in rows if c.result]
    texts: list[tuple[str | None, str, str | None]] = [(beat.id, str(beat.text), None) for beat in spec.beats]
    texts += [(first, text, where) for where, text in screen_texts(spec)]
    for beat, text, where in texts:
        def said(sentence: str) -> str:
            return f"{where} '{qa.quote(sentence)}'" if where else f'"{qa.quote(sentence)}"'

        if "calc_units" in on:
            for claim in qa.dimension_claims(text):
                add("calc_units", beat, f"{said(claim.quote)}: {claim.message}")
        if not own and not others:
            continue
        for sentence in qa.statements(text):
            _check_sentence(sentence, said(sentence), own, others, scene_id, rules, lambda r, m, b=beat: add(r, b, m))
    if "calc_sigfigs" in on:
        for r in results.get(scene_id, []):
            for w in r.warnings:
                add("calc_sigfigs", first, f"calculations[{r.index}] ({r.name}): {w}: lower its sig, or give the inputs as many figures "
                                           f"as they really have")
    return out


def _check_sentence(sentence: str, quoted: str, own: list[qa.Candidate], others: list[qa.Candidate], scene_id: str, rules: LintRules,
                    add: Any) -> None:
    values = [v for v in qa.said_values(sentence) if v.checkable]
    if not values:
        return
    mentioned, hinted = _mentions(sentence, own, others)
    tol = rules.calc_numbers.tolerance
    checks: list[tuple[qa.SaidValue, tuple[qa.Candidate, bool] | None]] = []
    for v in values:
        if v.unit is None or v.dim == DIMENSIONLESS:
            continue
        pool = [c for c in own if c.dim == v.dim] + [c for c in others if c.dim == v.dim and id(c) in mentioned]
        if not pool:
            named = [c for c in own + others if id(c) in mentioned and c.dim not in (v.dim, DIMENSIONLESS) and mentioned[id(c)] < v.start]
            if named and not (v.unit.text == "°" and describe_dim(named[0].dim).startswith("temperature")):
                c = named[0]
                add("calc_units", f"{quoted}: {qa.said_name(v)} is {describe_dim(v.dim)}, but {_who(c, scene_id)} is {c.shown}, "
                                  f"{describe_dim(c.dim)}: say it in {c.unit.text if c.unit is not None and c.unit.text else 'its unit'}")
            continue
        checks.append((v, _target(v, pool, own, mentioned, tol)))
    pure = [v for v in values if v.unit is None or v.dim == DIMENSIONLESS]
    named_pure = [c for c in own + others if c.dim == DIMENSIONLESS and (id(c) in mentioned or id(c) in hinted)]
    for c in named_pure:
        at = mentioned.get(id(c), hinted.get(id(c), 0))
        v = _value_for(pure, at)
        # a value hinted at by one word takes only a share, fraction, percentage or decimal ("carriers ... one in 26")
        if v is None or v in [w for w, _ in checks] or id(c) not in mentioned and v.per is None and v.unit is None and float(v.value).is_integer():
            continue
        checks.append((v, _target(v, named_pure, own, {id(c): at}, tol)))
    for v, target in checks:
        if target is None:
            continue
        c, matched = target
        if matched:
            if c.result and c.sig is not None and v.sig is not None and v.sig_sure and v.sig > c.sig and v.per is None:
                add("calc_sigfigs", f"{quoted}: {qa.said_name(v)} gives {v.sig} significant figures, but {_who(c, scene_id)} is known to "
                                    f"{c.sig} (its inputs): say {qa.in_unit_text(c.value, v.unit, c.sig)}")
            continue
        power = qa.mixup_power(v, c.value, rules.calc_units.tolerance)
        if power:
            size = "larger" if power > 0 else "smaller"
            shown = c.shown + (f" ({qa.in_unit_text(c.value, v.unit, c.sig)})" if c.unit is None or v.unit.text != c.unit.text else "")
            add("calc_units", f"{quoted}: {qa.said_name(v)} is {10 ** abs(power):,} times {size} than {_who(c, scene_id)} = {shown}: a "
                              f"prefix mixed up?")
            continue
        if v.per is not None and c.value > 0:
            shown = f"{c.shown} (1 in {1 / c.value:.3g})"
        elif v.unit is not None and v.dim == c.dim and v.unit.text != (c.unit.text if c.unit is not None else ""):
            shown = f"{qa.in_unit_text(c.value, v.unit, c.sig)} ({c.shown})"
        else:
            shown = c.shown
        add("calc_numbers", f"{quoted}: {qa.said_name(v)}, but {_who(c, scene_id)} is {shown}: say that, or fix the calculation")


def _value_for(values: list[qa.SaidValue], at: int) -> qa.SaidValue | None:
    """The pure number a value named at ``at`` is given as: one containing the name ("one birth
    in 2,500"), else the nearest after it, shares, fractions, percentages and decimals before
    bare whole numbers ("two p q: about one in twenty-six")."""
    if not values:
        return None
    preferred = [v for v in values if v.per is not None or v.unit is not None or not float(v.value).is_integer()] or values

    def distance(v: qa.SaidValue) -> float:
        if v.start <= at <= v.end + 1:      # "one birth in 2,500", "133 proton masses"
            return 0.0
        return float(v.start - at) if v.start >= at else 1e6 + at - v.end

    best = min(preferred, key=distance)
    return best if distance(best) < 1e6 else None


def _target(v: qa.SaidValue, pool: list[qa.Candidate], own: list[qa.Candidate], mentioned: dict[int, int], tol: float) -> tuple[qa.Candidate, bool] | None:
    """The value ``v`` refers to and whether it agrees: any value of the pool it agrees with;
    else the one the sentence names, else the scene's only result of that dimension."""
    for c in pool:
        if qa.agrees(v, c.value, tol):
            return c, True
    named = [c for c in pool if id(c) in mentioned]
    if named:
        return min(named, key=lambda c: abs(v.start - mentioned[id(c)])), False
    same = [c for c in own if c in pool and c.name]   # an intermediate part never takes the blame
    results = [c for c in same if c.result]
    if len(results) == 1 and len(same) == 1:
        return results[0], False
    return None


# ----- the rules -----------------------------------------------------------------------------------------


@rule("calc_numbers", scope="scene")
def calc_numbers(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A number said or shown for a calculation's value that differs from what it computes."""
    yield from _issues(ctx, "calc_numbers")


@rule("calc_units", scope="scene")
def calc_units(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A value in a unit of the wrong kind for its quantity ("a speed of 30 kilometres"), or off by a power of 1000 (m for km)."""
    yield from _issues(ctx, "calc_units")


@rule("calc_sigfigs", scope="scene", default="info")
def calc_sigfigs(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """More significant figures than a calculation's inputs give: its sig, or a number said for a result."""
    yield from _issues(ctx, "calc_sigfigs")
