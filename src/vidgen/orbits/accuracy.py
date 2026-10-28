"""The orbital lint's knowledge (Phase X, Step 234, DESIGN §98.8): which value of an ``orbit``
scene's model a number in the narration or on screen is about, whether it agrees, dates of
oppositions and conjunctions, claims about scale, and the atmospheres a periapsis should stay
above. No manim.

The numbers and units are read by :mod:`vidgen.quantities.accuracy` (the ``calc_*`` lint's
reader: digits and words, "about", resolutions, ranges and bounds left alone); this module adds
weeks and months (a month is a twelfth of a Julian year), the values an orbit scene computes
(:class:`Fact`: a value or a range — a speed along an elliptic orbit lies between its apoapsis and
periapsis speeds), which of them a sentence is about (the bodies it names, then its words: "Δv",
"burn", "transfer", "every", "perihelion", "escape", "L2"...) and the messages. Like the other
accuracy modules it is narrow on purpose: negations, questions, hypotheticals, comparisons,
bounds and ranges are not read, and a value that agrees with any of the named bodies' values (or,
when no body is named, any value of its kind in the scene) is accepted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any

from vidgen.quantities import accuracy as qa
from vidgen.quantities.units import DIMENSIONLESS, dim, parse_unit

from .values import AU, DAY, YEAR, time_unit

#: The rules the facts belong to (DESIGN §98.8), in :data:`vidgen.config.LINT_RULES` order.
ORBIT_RULES: tuple[str, ...] = ("orbit_period", "orbit_speed", "orbit_dv", "orbit_transfer", "orbit_distance", "orbit_date", "orbit_scale",
                                "orbit_conserved", "orbit_crash")
#: Fact kinds and the rule a mismatch is reported under.
KIND_RULES: dict[str, str] = {
    "period": "orbit_period",
    "speed": "orbit_speed", "peri_speed": "orbit_speed", "apo_speed": "orbit_speed", "circular": "orbit_speed", "escape": "orbit_speed",
    "v_inf": "orbit_speed", "planet_speed": "orbit_speed", "shot": "orbit_speed", "sun_speed": "orbit_speed",
    "dv": "orbit_dv", "dv_total": "orbit_dv", "gain": "orbit_dv", "turn": "orbit_dv",
    "transfer_time": "orbit_transfer", "synodic": "orbit_transfer", "wait": "orbit_transfer", "phase": "orbit_transfer",
    "distance": "orbit_distance", "peri": "orbit_distance", "apo": "orbit_distance", "altitude": "orbit_distance", "radius": "orbit_distance",
    "diameter": "orbit_distance", "lagrange": "orbit_distance", "between": "orbit_distance",
}
#: Where an atmosphere starts to matter for an orbit (altitude, m; the source) — a periapsis
#: below it grazes the air: drag brings the orbit down. The Earth's is the Kármán line (the FAI
#: convention); Mars's is the entry-interface altitude used for Mars landings (for the owner to
#: check). Bodies without an entry have none here (no finding).
ATMOSPHERES: dict[str, tuple[float, str]] = {
    "earth": (100e3, "the Kármán line, 100 km"),
    "mars": (125e3, "the entry interface used for Mars landings, about 125 km"),
}

_TIME, _SPEED, _LENGTH = dim(s=1), dim(m=1, s=-1), dim(m=1)


# ----- values --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fact:
    """A value an orbit scene computes: its ``kind`` (:data:`KIND_RULES`), ``quantity``
    (``time``, ``speed``, ``length``, ``angle``), a value (``low`` = ``high``) or a range in SI
    (rad for angles), what it is (``what``, for messages), the bodies it is about
    (``subjects``: their names as the narration says them), a burn's place in the order
    (``order``, 0 for none) and the scene it comes from."""

    kind: str
    quantity: str
    low: float
    high: float
    what: str
    subjects: tuple[str, ...] = ()
    order: int = 0
    scene: str = ""

    @property
    def rule(self) -> str:
        return KIND_RULES[self.kind]

    @property
    def single(self) -> bool:
        return math.isclose(self.low, self.high, rel_tol=1e-12, abs_tol=0.0)

    def shown(self) -> str:
        """The value (or range) as a viewer would read it."""
        if self.single:
            return show(self.low, self.quantity)
        return f"between {show(self.low, self.quantity)} and {show(self.high, self.quantity)}"


def fact(kind: str, value: float | tuple[float, float], what: str, subjects: tuple[str, ...] | list[str] = (), order: int = 0, scene: str = "") -> Fact:
    """A :class:`Fact` of ``kind`` (its quantity from the kind) for a value or a ``(low, high)`` range."""
    lo, hi = (value, value) if not isinstance(value, tuple) else (min(value), max(value))
    quantity = {"orbit_period": "time", "orbit_transfer": "time"}.get(KIND_RULES[kind], "")
    if kind in ("phase", "turn"):
        quantity = "angle"
    elif KIND_RULES[kind] in ("orbit_speed", "orbit_dv"):
        quantity = "speed"
    elif KIND_RULES[kind] == "orbit_distance":
        quantity = "length"
    return Fact(kind, quantity, float(lo), float(hi), what, tuple(s for s in subjects if s), order, scene)


def _figures(x: float) -> str:
    """``x`` to three significant figures, large values with thousands separators (780, 363,000)."""
    r = float(f"{x:.3g}")
    return f"{r:,.0f}" if abs(r) >= 100 else f"{r:.3g}"


def show(value: float, quantity: str) -> str:
    """A value in the unit a viewer expects: times in min / h / d (and years), speeds in km/s,
    lengths in km or million km with AU, angles in degrees."""
    if quantity == "time":
        unit, scale = time_unit(abs(value))
        text = f"{_figures(value / scale)} {unit}"
        if unit == "d" and abs(value) > 300 * DAY:
            text += f" ({value / YEAR:.3g} yr)"
        elif unit == "yr":
            text += f" ({value / DAY:,.0f} d)"
        return text
    if quantity == "speed":
        return qa.in_unit_text(value, parse_unit("km/s" if abs(value) >= 1000 else "m/s"), 3)
    if quantity == "length":
        if abs(value) < 1e9:
            return f"{_figures(value / 1000)} km"
        return f"{value / 1e9:.3g} million km ({value / AU:.3g} AU)"
    if quantity == "angle":
        return f"{math.degrees(value):.1f}°"
    return f"{value:.3g}"


_GROUP_BEFORE = re.compile(r"\d[    ]$")
_WEEKS = re.compile(r"\s+(?P<u>weeks?|months?)\b", re.IGNORECASE)
_MONTH = YEAR / 12


def quantity_of(v: qa.SaidValue) -> str | None:
    """``time``, ``speed``, ``length`` or ``angle`` for a value said with such a unit, else ``None``."""
    if v.unit is None or v.per is not None:
        return None
    if v.dim == _TIME:
        return "time"
    if v.dim == _SPEED:
        return "speed"
    if v.dim == _LENGTH:
        return "length"
    if v.dim == DIMENSIONLESS and v.unit.text in ("°", "rad"):
        return "angle"
    return None


def said_quantities(sentence: str) -> list[qa.SaidValue]:
    """The values of ``sentence`` with a time, speed, length or angle unit, said as values (not
    a bound or one end of a range); "26 months" and "three weeks" as days. A number right after
    a digit group ("384 400 km") is left out: it is the end of a number written with spaces."""
    out: list[qa.SaidValue] = []
    for v in qa.said_values(sentence):
        if not v.checkable or _GROUP_BEFORE.search(sentence[: v.start]):
            continue
        if v.unit is None and v.per is None:
            m = _WEEKS.match(sentence, v.end)
            if m is not None:
                days = 7.0 if m.group("u").lower().startswith("week") else _MONTH / DAY
                v = replace(v, value=v.value * days, resolution=v.resolution * days, unit=parse_unit("d"), unit_text=m.group("u"),
                            end=m.end(), text=sentence[v.start:m.end()])
        if quantity_of(v) is not None:
            out.append(v)
    return out


def agrees(v: qa.SaidValue, f: Fact, tolerance: float) -> bool:
    """Whether ``v`` is the fact's value as it was said (a range: anywhere in it, its ends
    rounded as ``v`` was)."""
    if f.single:
        return qa.agrees(v, f.low, tolerance)
    lo, hi = f.low, f.high
    slack = v.si_resolution
    if lo - slack <= v.si <= hi + slack:
        return True
    if v.approx and lo * (1 - tolerance) <= v.si <= hi * (1 + tolerance):
        return True
    return qa.agrees(v, lo, tolerance) or qa.agrees(v, hi, tolerance)


def _distance(v: qa.SaidValue, f: Fact) -> float:
    """How far (log ratio) ``v`` is from the fact (0 inside a range)."""
    x = abs(v.si)
    if x <= 0 or f.high <= 0:
        return math.inf
    if f.low <= x <= f.high:
        return 0.0
    return min(abs(math.log(x / max(f.low, 1e-300))), abs(math.log(x / f.high)))


# ----- what a sentence is about ------------------------------------------------------------------------

_W = re.IGNORECASE
_TRANSFER = re.compile(r"\b(?:transfers?|trip|journey|cruise|flight|voyage|travel\w*|reach(?:es)?|get\s+to|arriv\w*|coast\w*|later|"
                       r"catch\w*\s+up|rendezvous)\b", _W)
_SYNODIC = re.compile(r"\b(?:synodic|windows?|opposition|conjunctions?|every|again|launch\w*|wait\w*|line\s+up|lines\s+up|comes?\s+(?:a)?round|"
                      r"repeats?)\b", _W)
_DV = re.compile(r"(?:\bdelta[- ]?v\b|Δ\s*v|\bdv\d?\b|\bburns?\b|\bkick\b|\bboosts?\b|\bbudget\b|\bthrust|\bimpulse\b|\bchange\s+(?:in|of)\s+"
                 r"(?:speed|velocity)|\bgain\w*|\blos(?:es|e|ing)\b|\bextra\b|\bslow\w*\s+down\b)", _W)
_PERIOD = re.compile(r"\b(?:periods?|orbits?|orbiting|takes?|took|taking|round|around|revolution|revolves?|laps?|circles?|circling|circuit|"
                     r"once|turns?|year\s+(?:is|lasts))\b", _W)
_ESCAPE = re.compile(r"\bescap\w*", _W)
_PERI = re.compile(r"\b(?:perihelion|periapsis|perigee|perilune|periselene|perijove|pericentre|pericenter|periastron|closest\s+(?:approach|point)|"
                   r"lowest\s+point)\b", _W)
_APO = re.compile(r"\b(?:aphelion|apoapsis|apogee|apolune|aposelene|apojove|apocentre|apocenter|apastron|farthest\s+point|furthest\s+point|"
                  r"highest\s+point)\b", _W)
_ALTITUDE = re.compile(r"\b(?:altitude|above|up|high|height)\b", _W)
_RADIUS = re.compile(r"\b(?:radius|radii|wide|across|diameter|width)\b", _W)
_DIAMETER = re.compile(r"\b(?:diameter|across|wide|width)\b", _W)
_TURN = re.compile(r"\b(?:turn\w*|deflect\w*|bend\w*|swing\w*|turning\s+angle)\b", _W)
_LPOINT = re.compile(r"\bL(?P<n>[1-5])\b")
_DEPART = re.compile(r"\b(?:leave|leaves|leaving|depart\w*|launch\w*|windows?|burn\w*|set\s+off)\b", _W)
_TOTAL = re.compile(r"\b(?:total|in\s+all|altogether|all\s+together|budget|sum|add\s+up|adds\s+up|overall|both\s+burns|together)\b", _W)
#: A burn's place in the order as said (-1: the last one).
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "final": -1, "last": -1,
             "departure": 1, "arrival": -1, "circularis": -1, "circulariz": -1}
_ORDINAL = re.compile(r"\b(?P<w>first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|final|last)\s+(?:\w+\s+)?(?:burns?|kicks?|manoeuvres?|"
                      r"maneuvers?|impulses?|boosts?|firings?|Δv|delta)|\b(?P<w2>departure|arrival|circularis\w*|circulariz\w*)|"
                      r"Δv(?P<sub>[₁₂₃₄₅])|\bdv(?P<dig>[1-5])\b", _W)


_CLAUSE_BREAK = re.compile(r"[,;:—]|\s(?:and|but|while|whereas)\s", re.IGNORECASE)


def clause(sentence: str, start: int, end: int, spans: list[tuple[int, int]] = ()) -> str:
    """The clause of ``sentence`` around ``start`` .. ``end`` (between commas, semicolons,
    colons, dashes, "and", "but", "while"), not breaking inside a number of ``spans`` ("two
    hundred and fifty-nine days")."""
    lo, hi = 0, len(sentence)
    for m in _CLAUSE_BREAK.finditer(sentence):
        if any(a <= m.start() < b for a, b in spans):
            continue
        if m.end() <= start:
            lo = m.end()
        elif m.start() >= end:
            hi = m.start()
            break
    return sentence[lo:hi]


def the(name: str) -> str:
    """'the Sun', 'the Earth', 'the Moon' in a message; other names as they are."""
    return f"the {name}" if name in ("Sun", "Earth", "Moon") else name


def mentions(sentence: str, name: str) -> bool:
    """Whether ``sentence`` names ``name`` (a whole word, any case, possessive allowed)."""
    return bool(name) and re.search(rf"(?<!\w){re.escape(name)}(?:'s)?(?!\w)", sentence, re.IGNORECASE) is not None


def topic_groups(sentence: str, quantity: str) -> tuple[list[tuple[str, ...]], bool]:
    """The fact kinds a value of ``quantity`` in ``sentence`` may be about, most likely first,
    and whether only the first kinds count (``strict``: a named apsis, "escape", a Lagrange
    point); empty when the words do not say ("barely moves in ten years" is a span, not a
    period)."""
    one_apsis = bool(_PERI.search(sentence)) != bool(_APO.search(sentence))
    if quantity == "time":
        if _TRANSFER.search(sentence):
            return [("transfer_time",), ("synodic", "wait"), ("period",)], False
        if _SYNODIC.search(sentence):
            return [("synodic", "wait"), ("period",), ("transfer_time",)], False
        return ([("period",)] if _PERIOD.search(sentence) else []), False
    if quantity == "speed":
        if _DV.search(sentence):
            return [("dv", "dv_total", "gain")], False
        if _ESCAPE.search(sentence):
            return [("escape",)], True
        if one_apsis and _PERI.search(sentence):
            return [("peri_speed",)], True
        if one_apsis:
            return [("apo_speed",)], True
        return [("speed",), ("v_inf", "planet_speed", "shot", "sun_speed", "circular")], False
    if quantity == "length":
        if _LPOINT.search(sentence):
            return [("lagrange",)], True
        if _RADIUS.search(sentence):
            return [("diameter", "radius") if _DIAMETER.search(sentence) else ("radius", "diameter")], False
        if _ALTITUDE.search(sentence):
            return [("altitude",), ("distance", "peri", "apo")], False
        if one_apsis and _PERI.search(sentence):
            return [("peri",)], True
        if one_apsis:
            return [("apo",)], True
        return [("distance", "between"), ("peri", "apo", "altitude")], False
    if quantity == "angle":
        if _TURN.search(sentence) and not re.search(r"\b(?:lead\w*|ahead|behind|phase)\b", sentence, _W):
            return [("turn",)], False
        return [("phase",), ("turn",)], False
    return [], False


def _narrow_dv(sentence: str, facts: list[Fact]) -> list[Fact]:
    """The Δv a sentence names: by its order ("the first burn", "Δv₂"), the total, else all."""
    if _TOTAL.search(sentence):
        total = [f for f in facts if f.kind == "dv_total"]
        if total:
            return total
    m = _ORDINAL.search(sentence)
    if m is not None:
        if m.group("sub"):
            k = "₀₁₂₃₄₅".index(m.group("sub"))
        elif m.group("dig"):
            k = int(m.group("dig"))
        else:
            word = (m.group("w") or m.group("w2")).lower()
            k = next((v for w, v in _ORDINALS.items() if word.startswith(w)), 0)
        orders = [f.order for f in facts if f.kind == "dv"]
        if k == -1 and orders:
            k = max(orders)
        chosen = [f for f in facts if f.kind == "dv" and f.order == k]
        if chosen:
            return chosen
    return [f for f in facts if f.kind != "dv_total"] or facts


def _narrow_lagrange(sentence: str, facts: list[Fact]) -> list[Fact]:
    named = {f"L{m.group('n')}" for m in _LPOINT.finditer(sentence)}
    return [f for f in facts if set(f.subjects) & named] or facts


@dataclass(frozen=True)
class OrbitClaim:
    """A number said for a value of the model that it does not match: the rule, the message."""

    rule: str
    message: str


def orbit_claims(sentence: str, facts: list[Fact], tolerances: dict[str, float], scene_id: str = "", need_name: bool = False) -> list[OrbitClaim]:
    """The numbers of ``sentence`` (one statement) that contradict the facts. A value is
    compared with the facts of the bodies the sentence names (all of the scene's when it names
    none; ``need_name``: only named ones, for facts of another scene) — any of them it agrees with
    is fine; else it is reported against the fact its words point to ("Δv", "transfer",
    "perihelion", "L2"...), when that is clear."""
    out: list[OrbitClaim] = []
    spans = [(w.start, w.end) for w in qa.said_values(sentence)]
    for v in said_quantities(sentence):
        q = quantity_of(v)
        same = [f for f in facts if f.quantity == q]
        if not same:
            continue
        part = clause(sentence, v.start, v.end, spans)
        names = {s for f in same for s in f.subjects if mentions(part, s)} or {s for f in same for s in f.subjects if mentions(sentence, s)}
        mine = [f for f in same if set(f.subjects) & names] if names else ([] if need_name else same)
        groups, strict = topic_groups(part, q)
        if not groups:
            groups, strict = topic_groups(sentence, q)
        chosen: list[Fact] = []
        for group in groups:
            chosen = [f for f in mine if f.kind in group]
            if chosen:
                break
        if not chosen:
            continue
        # it may be any value of the kinds the words allow (the first group only when they are precise)
        allowed = chosen if strict else [f for f in mine if any(f.kind in g for g in groups)]
        if any(agrees(v, f, tolerances.get(f.rule, 0.05)) for f in allowed):
            continue
        if chosen[0].kind in ("dv", "dv_total", "gain"):
            chosen = _narrow_dv(part, chosen)
        if chosen[0].kind == "phase" and _DEPART.search(sentence):   # the lead at departure (order 1), not the one at the start
            chosen = [f for f in chosen if f.order == 1] or chosen
        if chosen[0].kind == "lagrange":
            chosen = _narrow_lagrange(part if _LPOINT.search(part) else sentence, chosen)
        if not names and len({f.subjects for f in chosen}) > 1:
            continue   # several bodies could be meant and none is named
        best = min(chosen, key=lambda f: _distance(v, f))
        out.append(OrbitClaim(best.rule, _message(sentence, v, best, tolerances.get(best.rule, 0.05), scene_id)))
    return out


def _message(sentence: str, v: qa.SaidValue, f: Fact, tolerance: float, scene_id: str) -> str:
    where = f" (scene '{f.scene}')" if f.scene and f.scene != scene_id else ""
    if f.single:
        power = qa.mixup_power(v, f.low, tolerance)
        if power:
            size = "larger" if power > 0 else "smaller"
            return f"{qa.said_name(v)} is {10 ** abs(power):,} times {size} than {f.what}{where}, {f.shown()}: a prefix mixed up?"
    said_in = ""
    if f.single and v.unit is not None and v.unit.text and v.unit.text not in f.shown():
        said_in = f" ({qa.in_unit_text(f.low, v.unit, 3)})"
    return f"{qa.said_name(v)}, but {f.what}{where} is {f.shown()}{said_in} in the scene's model: say that, or change the scene"


# ----- size ratios -------------------------------------------------------------------------------------

_RATIO = re.compile(r"\s+times\s+(?:as\s+(?:wide|broad)\s+as|wider\s+than|broader\s+than|the\s+(?:width|diameter|radius)\s+of)\s+(?:the\s+)?"
                    r"(?P<b>[^\W\d_]+(?:[-'][^\W\d_]+)?)", re.IGNORECASE)


def ratio_claims(sentence: str, radii: dict[str, float]) -> list[str]:
    """"Jupiter is eleven times as wide as the Earth": a ratio of two bodies' radii (``radii``:
    name → m) that the numbers do not give."""
    out: list[str] = []
    values = [v for v in qa.said_values(sentence) if v.checkable and v.unit is None and v.per is None]
    lower = {k.lower(): (k, r) for k, r in radii.items() if r > 0}
    for v in values:
        m = _RATIO.match(sentence, v.end)
        if m is None or m.group("b").lower() not in lower:
            continue
        b_key = m.group("b").lower()
        before = [(found.start(), key) for key, (name, _) in lower.items() if key != b_key
                  for found in re.finditer(rf"(?<!\w){re.escape(name)}(?:'s)?(?!\w)", sentence[: v.start], re.IGNORECASE)]
        if not before:
            continue
        a_key = max(before)[1]
        (a_name, ra), (b_name, rb) = lower[a_key], lower[m.group("b").lower()]
        ratio = ra / rb
        if not qa.agrees(v, ratio):
            out.append(f"{qa.said_name(v)} times as wide: {the(a_name)}'s radius ({show(ra, 'length')}) is {ratio:.3g} times {the(b_name)}'s "
                       f"({show(rb, 'length')}): say about {ratio:.2g}")
    return out


# ----- scale ------------------------------------------------------------------------------------------

_SCALE = re.compile(r"\b(?:to|at|in)\s+(?:(?:its|their|the)\s+)?(?:true\s+|real\s+|actual\s+|correct\s+|the\s+same\s+)?scale\b|"
                    r"\btrue[- ]scale\b|\b(?:true|real|actual|correct)\s+(?:sizes?|proportions?)\b|\bscale\s+model\b|\bscaled\s+correctly\b",
                    re.IGNORECASE)
_SIZE_WORDS = re.compile(r"\b(?:sizes?|sized|big|bigger|biggest|large|larger|small|smaller|radius|radii|diameters?|wide|width|dots?|discs?|disks?|"
                         r"everything|all\s+of\s+it|whole\s+picture|planets?\s+themselves|drawn)\b|\b(?:true|real|actual)\s+sizes?\b", re.IGNORECASE)
_DISTANCE_WORDS = re.compile(r"\b(?:distances?|orbits?|spacing|far|apart|separations?|gaps?)\b", re.IGNORECASE)
#: What an orbit scene draws to scale: ``true`` (sizes and distances), ``enlarged`` (distances to
#: scale, bodies enlarged), ``log`` (distances compressed, every body a dot), ``sizes`` (radii to
#: scale, no distances), ``schematic`` (the tides).
PICTURES = ("true", "enlarged", "log", "sizes", "schematic")


def scale_claims(sentence: str, picture: str) -> str | None:
    """A claim that ``sentence`` makes about scale that the picture does not keep, or ``None``."""
    m = _SCALE.search(sentence)
    if m is None or picture == "true":
        return None
    sizes, distances = _SIZE_WORDS.search(sentence) is not None, _DISTANCE_WORDS.search(sentence) is not None
    if picture == "log":
        return ("the picture compresses distances (radial: log) and draws every body as a dot: nothing in it is to scale; say "
                "'distances compressed' (the panel says it too)")
    if picture == "schematic":
        return "the tides picture is a schematic (sizes, distance and arrows not to scale); say so instead"
    if picture == "enlarged" and sizes:
        return ("only the distances are: the bodies are drawn enlarged (the panel says 'sizes not to scale'); say that the distances "
                "are to scale and the sizes are not")
    if picture == "sizes" and distances:
        return "the sizes picture shows radii to scale, not distances (the bodies stand side by side): say only the sizes are to scale"
    return None


# ----- dates of events ------------------------------------------------------------------------------------

_MONTHS = {m: k for k, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                                       "november", "december"), start=1)}
_MONTH_ABBR = {m[:3]: k for m, k in _MONTHS.items()} | {"sept": 9}
_MON = r"(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
_ORD_WORDS = {w: k for k, w in enumerate(("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
                                          "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth").split(), start=1)}
_ORD_WORDS |= {f"twenty-{w}": 20 + k for w, k in list(_ORD_WORDS.items())[:9]} | {"thirtieth": 30, "thirty-first": 31}
_DAY = rf"(?P<d>\d{{1,2}})(?:st|nd|rd|th)?|(?P<dw>{'|'.join(sorted(_ORD_WORDS, key=len, reverse=True))})"
_DATES = (
    ("day", re.compile(r"\b(?P<y>(?:18|19|20)\d\d)-(?P<m>\d\d)-(?P<d>\d\d)\b")),
    ("day", re.compile(rf"\b(?:the\s+)?(?:{_DAY})(?:\s+of)?\s+{_MON},?\s+(?P<y>(?:18|19|20)\d\d)\b", re.IGNORECASE)),
    ("day", re.compile(rf"\b{_MON}\s+(?:the\s+)?(?:{_DAY}),?\s+(?P<y>(?:18|19|20)\d\d)\b", re.IGNORECASE)),
    ("month", re.compile(rf"\b{_MON},?\s+(?:of\s+)?(?P<y>(?:18|19|20)\d\d)\b", re.IGNORECASE)),
    ("year", re.compile(r"\b(?:in|during|of)\s+(?:early\s+|mid[- ]?|late\s+)?(?P<y>(?:18|19|20)\d\d)\b", re.IGNORECASE)),
    ("month_only", re.compile(r"\b(?:in\s+(?:early\s+|mid[- ]?|late\s+)?|mid[- ]|early\s+|late\s+|by\s+)(?P<mon>January|February|March|April|"
                              r"June|July|August|September|October|November|December)\b")),
)
_EVENT = re.compile(r"\b(?P<k>(?:inferior|superior)\s+conjunction|opposition|conjunction)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class SaidDate:
    """A date in a sentence: as written, how precise (``day``, ``month``, ``year``,
    ``month_only``), the year (0 for a month alone), month (0 for a year) and day (0)."""

    text: str
    start: int
    precision: str
    year: int
    month: int
    day: int


def _month_of(text: str) -> int:
    t = text.lower().rstrip(".")
    return _MONTHS.get(t) or _MONTH_ABBR.get(t[:4] if t.startswith("sept") else t[:3], 0)


def said_dates(sentence: str) -> list[SaidDate]:
    """The calendar dates of ``sentence``, the most precise reading of each place first."""
    out: list[SaidDate] = []
    taken: list[tuple[int, int]] = []
    for precision, pattern in _DATES:
        for m in pattern.finditer(sentence):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            g = m.groupdict()
            if precision == "day" and g.get("mon") is None:
                year, month, day = int(g["y"]), int(g["m"]), int(g["d"])
            else:
                year = int(g["y"]) if g.get("y") else 0
                month = _month_of(g["mon"]) if g.get("mon") else 0
                day = int(g["d"]) if g.get("d") else (_ORD_WORDS.get(g["dw"].lower(), 0) if g.get("dw") else 0)
            if month and not 1 <= month <= 12 or day and not 1 <= day <= 31:
                continue
            taken.append((m.start(), m.end()))
            out.append(SaidDate(m.group().strip(), m.start(), precision, year, month, day))
    return sorted(out, key=lambda d: d.start)


def _bounds(d: SaidDate) -> tuple[float, float]:
    """The Julian dates a said date covers (a day, a month or a year)."""
    from .ephemeris import julian_date

    if d.precision == "day":
        start = julian_date(f"{d.year:04d}-{d.month:02d}-{d.day:02d}")
        return start, start + 1.0
    if d.precision == "month":
        start = julian_date(f"{d.year:04d}-{d.month:02d}-01")
        y, mo = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        return start, julian_date(f"{y:04d}-{mo:02d}-01")
    return julian_date(f"{d.year:04d}-01-01"), julian_date(f"{d.year + 1:04d}-01-01")


def _event_kinds(word: str, target: str) -> tuple[str, ...]:
    from .ephemeris import TABLE1

    outer = TABLE1[target][0][0] > TABLE1["earth"][0][0]
    w = " ".join(word.lower().split())
    if w == "opposition":
        return ("opposition",) if outer else ()
    if w == "conjunction":
        return ("conjunction",) if outer else ("inferior_conjunction", "superior_conjunction")
    if w.startswith(("inferior", "superior")):
        return () if outer else (w.replace(" ", "_"),)
    return ()


_EVENT_NAMES = {"opposition": "opposition", "conjunction": "conjunction", "inferior_conjunction": "inferior conjunction",
                "superior_conjunction": "superior conjunction"}


def event_claims(sentence: str, tolerance_days: float = 3.0, scene_event: Any = None) -> list[str]:
    """Dates said for an opposition or a conjunction of a planet seen from the Earth that the
    JPL elements (Table 1, 1800–2050) do not give: a day (within ``tolerance_days``), a month or a
    year with no such event in it. A month alone ("in mid October") is read only against the
    scene's own ``event`` (:class:`~vidgen.orbits.ephemeris.Event`)."""
    from .ephemeris import PLANETS, date_text, events_between, julian_date, planet_synodic_period, valid_range
    from vidgen.errors import VidgenError

    words = list(_EVENT.finditer(sentence))
    if not words:
        return []
    dates = said_dates(sentence)
    if not dates:
        return []
    targets = [p for p in PLANETS if p != "earth" and mentions(sentence, p)]
    if not targets:
        return []
    lo_valid, hi_valid = valid_range()
    out: list[str] = []
    for d in dates:
        if d.precision == "month_only":
            if scene_event is None or scene_event.target not in targets or scene_event.observer != "earth":
                continue
            jd = scene_event.jd
            ok = False
            for year in (int(date_text(jd)[:4]) - 1, int(date_text(jd)[:4]), int(date_text(jd)[:4]) + 1):
                lo = julian_date(f"{year:04d}-{d.month:02d}-01")
                hi = julian_date(f"{year + (d.month == 12):04d}-{d.month % 12 + 1:02d}-01")
                ok |= lo - tolerance_days <= jd <= hi + tolerance_days
            if not ok:
                out.append(f"\"{d.text}\": the scene's {scene_event.target.capitalize()} {_EVENT_NAMES.get(scene_event.kind, scene_event.kind)} "
                           f"falls on {date_text(jd)}")
            continue
        lo, hi = _bounds(d)
        if lo < lo_valid or hi > hi_valid:
            continue
        found_any = False
        best: tuple[float, Any] | None = None
        for t in targets:
            for w in words:
                for kind in _event_kinds(w.group("k"), t):
                    syn = planet_synodic_period("earth", t) / DAY
                    try:
                        events = events_between(kind, "earth", t, max(lo - 1.2 * syn, lo_valid), min(hi + 1.2 * syn, hi_valid))
                    except VidgenError:
                        continue
                    for ev in events:
                        gap = 0.0 if lo - tolerance_days <= ev.jd <= hi + tolerance_days else min(abs(ev.jd - lo), abs(ev.jd - hi))
                        if gap == 0.0:
                            found_any = True
                        if best is None or gap < best[0]:
                            best = (gap, ev)
        if found_any or best is None:
            continue
        ev = best[1]
        span = {"day": f"within {tolerance_days:g} days of that date", "month": "in that month", "year": f"in {d.year}"}[d.precision]
        out.append(f"\"{d.text}\": no {_EVENT_NAMES[ev.kind]} of {ev.target.capitalize()} (seen from the Earth) {span} by JPL's approximate "
                   f"elements; the nearest is on {date_text(ev.jd)}")
    return out


__all__ = ["ATMOSPHERES", "KIND_RULES", "ORBIT_RULES", "PICTURES", "Fact", "OrbitClaim", "SaidDate", "agrees", "event_claims", "fact", "mentions",
           "orbit_claims", "quantity_of", "ratio_claims", "said_dates", "said_quantities", "scale_claims", "show", "topic_groups"]
