"""The planets on a date (Phase X, Step 233, DESIGN §98.7). No manim.

Source: E. M. Standish (JPL Solar System Dynamics), "Keplerian Elements for Approximate
Positions of the Major Planets", **Table 1**: mean elements at J2000 and their rates per Julian
century, referred to the mean ecliptic and equinox of J2000, valid **1800 AD – 2050 AD** (the
document's own error table gives the accuracy: arcseconds to arcminutes, Jupiter and Saturn the
worst — their mutual perturbations are not in a linear fit). The Earth's entry is the Earth–Moon
barycentre (EM Bary), not the Earth's centre: they differ by up to 4 671 km (6″ seen from the Sun).
Pluto is in Table 1 with the planets.

The method is the document's: T = (JD − 2451545.0) / 36525 Julian centuries; each element is
its J2000 value plus its rate × T; ω = ϖ − Ω, M = L − ϖ; Kepler's equation for E; the position
in the orbit's plane rotated by ω, I, Ω into heliocentric ecliptic coordinates. Dates are
Gregorian calendar dates; a time of day is taken as TT (the document's time scale; TT − UTC is
about 69 s, far below the table's accuracy).

Dates outside 1800–2050 are refused (``VidgenError``): Table 1 is a fit to that interval and its
rates are not meant for extrapolation (the document's Table 2a covers 3000 BC – 3000 AD with
extra terms; it is not used here).

Conjunctions and oppositions: when two planets' heliocentric ecliptic longitudes coincide (or
differ by 180°), found by bracketing the wrapped difference on a grid of 1/24 of the synodic
period and bisecting. Seen from the inner planet, equal longitudes put the outer one opposite the
Sun in longitude (an opposition: the same instant as the geocentric opposition in longitude,
since the Sun, the inner and the outer planet are then on one line in projection); 180° apart
puts it behind the Sun (a conjunction). Seen from an outer planet, an inner one is at inferior
(equal longitudes) or superior (180°) conjunction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import did_you_mean

from .kepler import eccentric_anomaly
from .values import AU, DAY

#: The document and its validity.
SOURCE = ("E. M. Standish, JPL Solar System Dynamics, 'Keplerian Elements for Approximate Positions of the Major Planets', "
          "Table 1 (mean ecliptic and equinox of J2000; valid 1800 AD - 2050 AD)")
#: Julian date of J2000.0 (2000 January 1, 12:00 TT) and days per Julian century.
J2000 = 2451545.0
CENTURY = 36525.0
#: Table 1's validity, inclusive: 1800-01-01 00:00 to 2050-12-31 24:00.
VALID_FROM = "1800-01-01"
VALID_TO = "2050-12-31"
_EPOCH = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)

#: Table 1: a (AU), e, I (deg), L (deg), ϖ = long. peri. (deg), Ω = long. node (deg) at J2000,
#: then their rates per Julian century (AU/cy, /cy, deg/cy...). "earth" is the Earth–Moon barycentre.
TABLE1: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {
    "mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
    "uranus": ((19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
               (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589)),
    "neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.01183482)),
    "pluto": ((39.48211675, 0.24882730, 17.14001206, 238.92903833, 224.06891629, 110.30393684),
              (-0.00031596, 0.00005170, 0.00004818, 145.20780515, -0.04062942, -0.01183482)),
}
PLANETS = tuple(TABLE1)
#: Event kinds and the longitude difference (target − observer, degrees) that defines them.
EVENTS = {"opposition": 0.0, "conjunction": 180.0, "inferior_conjunction": 0.0, "superior_conjunction": 180.0, "aligned": 0.0}
_ALIASES = {"emb": "earth", "em_bary": "earth", "earth_moon_barycentre": "earth"}


def planet_key(name: str, where: str = "planet") -> str:
    """The Table 1 key of ``name`` (Mercury … Neptune, Pluto); raises with did-you-mean."""
    k = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    k = _ALIASES.get(k, k)
    if k not in TABLE1:
        raise VidgenError(f"{where}: '{name}' is not in JPL's Table 1 of approximate planetary elements (it has {', '.join(PLANETS)})"
                          + did_you_mean(k, list(PLANETS)))
    return k


# ----- dates -----------------------------------------------------------------------------------------


def parse_date(text: Any, where: str = "date") -> datetime:
    """A calendar date 'YYYY-MM-DD', optionally with a time 'YYYY-MM-DD HH:MM[:SS]' (or a 'T'
    between), Gregorian, as a timezone-aware datetime (taken as TT)."""
    if isinstance(text, datetime):
        return text if text.tzinfo is not None else text.replace(tzinfo=timezone.utc)
    if hasattr(text, "year") and hasattr(text, "month") and hasattr(text, "day"):   # a date (YAML reads 2020-10-13 as one)
        return datetime(text.year, text.month, text.day, tzinfo=timezone.utc)
    s = str(text).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise VidgenError(f"{where}: '{text}' is not a date; write it as 2020-10-13 (year-month-day), optionally with a time: '2020-10-13 23:30'")


def julian_date(when: Any, where: str = "date") -> float:
    """The Julian date of a calendar date (text or datetime; 2000-01-01 12:00 → 2451545.0)."""
    d = parse_date(when, where)
    return J2000 + (d - _EPOCH).total_seconds() / 86_400.0


def calendar(jd: float) -> datetime:
    """The calendar date and time (TT) of Julian date ``jd``."""
    return _EPOCH + timedelta(days=float(jd) - J2000)


def date_text(jd: float, time: bool = False) -> str:
    """'2020-10-13' (the day it falls on) or with ``time`` '2020-10-13 23:26' (to the nearest minute)."""
    d = calendar(jd) + (timedelta(seconds=30) if time else timedelta(0))
    return d.strftime("%Y-%m-%d %H:%M") if time else d.strftime("%Y-%m-%d")


def valid_range() -> tuple[float, float]:
    """Table 1's validity as Julian dates (from 1800-01-01 0h to the end of 2050-12-31)."""
    return julian_date(VALID_FROM) - 0.0, julian_date(VALID_TO) + 1.0


def check_valid(jd_start: float, jd_end: float | None = None, where: str = "date") -> None:
    """Refuse dates outside Table 1's 1800–2050 (the start, and the end of a span)."""
    lo, hi = valid_range()
    for jd in (jd_start, jd_start if jd_end is None else jd_end):
        if not lo <= jd < hi:
            what = "starts" if jd == jd_start else "ends"
            raise VidgenError(f"{where}: the scene {what} on {date_text(jd)}, outside 1800-2050 where JPL's approximate planetary elements "
                              "(Table 1) are valid; choose a date in that range (or a shorter span)")


# ----- elements and positions -------------------------------------------------------------------------


@dataclass(frozen=True)
class MeanElements:
    """A planet's mean elements on a date (Table 1): ``a`` (AU), ``e``, and in degrees ``i``,
    ``mean_longitude`` L, ``peri_longitude`` ϖ, ``node`` Ω; derived ``argp`` ω = ϖ − Ω and
    ``mean_anomaly`` M = L − ϖ (in (−180°, 180°])."""

    planet: str
    jd: float
    a: float
    e: float
    i: float
    mean_longitude: float
    peri_longitude: float
    node: float

    @property
    def argp(self) -> float:
        return (self.peri_longitude - self.node) % 360.0

    @property
    def mean_anomaly(self) -> float:
        m = (self.mean_longitude - self.peri_longitude) % 360.0
        return m - 360.0 if m > 180.0 else m


def mean_elements(planet: str, jd: float) -> MeanElements:
    """Table 1's elements of ``planet`` at Julian date ``jd`` (no validity check: see :func:`check_valid`)."""
    key = planet_key(planet)
    base, rate = TABLE1[key]
    T = (float(jd) - J2000) / CENTURY
    a, e, i, L, peri, node = (b + r * T for b, r in zip(base, rate))
    return MeanElements(key, float(jd), a, e, i, L, peri, node)


def heliocentric(planet: str, jd: Any) -> np.ndarray:
    """Heliocentric ecliptic (J2000) position(s) in metres at Julian date(s) ``jd``: shape (3,)
    or (n, 3)."""
    key = planet_key(planet)
    base, rate = TABLE1[key]
    jds = np.atleast_1d(np.asarray(jd, dtype=float))
    T = (jds - J2000) / CENTURY
    a, e, inc, L, peri, node = (b + r * T for b, r in zip(base, rate))
    M = np.radians(np.mod(L - peri + 180.0, 360.0) - 180.0)
    E = np.array([eccentric_anomaly(float(m), float(ee)) for m, ee in zip(M, e)])
    xp = a * (np.cos(E) - e)
    yp = a * np.sqrt(1 - e**2) * np.sin(E)
    w, O, I = np.radians(peri - node), np.radians(node), np.radians(inc)
    cw, sw, cO, sO, cI, sI = np.cos(w), np.sin(w), np.cos(O), np.sin(O), np.cos(I), np.sin(I)
    x = (cw * cO - sw * sO * cI) * xp + (-sw * cO - cw * sO * cI) * yp
    y = (cw * sO + sw * cO * cI) * xp + (-sw * sO + cw * cO * cI) * yp
    z = (sw * sI) * xp + (cw * sI) * yp
    out = np.column_stack([x, y, z]) * AU
    return out[0] if np.ndim(jd) == 0 else out


def longitude(planet: str, jd: Any) -> Any:
    """Heliocentric ecliptic longitude(s) in degrees, in [0, 360)."""
    p = heliocentric(planet, jd)
    return np.mod(np.degrees(np.arctan2(p[..., 1], p[..., 0])), 360.0)


def distance(a: str, b: str, jd: Any) -> Any:
    """Distance(s) between two planets (m); 'sun' is the origin."""
    pa = np.zeros(3) if a.strip().lower() == "sun" else heliocentric(a, jd)
    pb = np.zeros(3) if b.strip().lower() == "sun" else heliocentric(b, jd)
    return np.linalg.norm(np.asarray(pa) - np.asarray(pb), axis=-1)


def sidereal_period(planet: str) -> float:
    """The planet's sidereal period (s) from Table 1's rate of mean longitude (360° / L̇)."""
    rate = TABLE1[planet_key(planet)][1][3]
    return 360.0 / rate * CENTURY * DAY


def planet_synodic_period(a: str, b: str) -> float:
    """The synodic period (s) of two planets: 1 / |1/T₁ − 1/T₂| with Table 1's periods."""
    ka, kb = planet_key(a), planet_key(b)
    if ka == kb:
        raise VidgenError(f"synodic period: give two different planets (got {a} twice)")
    ra, rb = TABLE1[ka][1][3], TABLE1[kb][1][3]
    return 360.0 / abs(ra - rb) * CENTURY * DAY


def elongation(observer: str, target: str, jd: Any) -> Any:
    """The target's elongation from the Sun as seen from the observer (degrees, 0–180): the
    angle Sun–observer–target."""
    o = heliocentric(observer, jd)
    t = heliocentric(target, jd)
    to_sun, to_target = -o, t - o
    cos = np.sum(to_sun * to_target, axis=-1) / (np.linalg.norm(to_sun, axis=-1) * np.linalg.norm(to_target, axis=-1))
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


# ----- events -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """A conjunction or opposition: its ``kind``, the ``observer`` and ``target`` planets, the
    Julian date, the distance between them then (m) and the target's elongation from the Sun as
    seen from the observer (degrees)."""

    kind: str
    observer: str
    target: str
    jd: float
    distance: float
    elongation: float

    @property
    def date(self) -> str:
        return date_text(self.jd)

    def text(self) -> str:
        names = {"opposition": "opposition", "conjunction": "conjunction", "inferior_conjunction": "inferior conjunction",
                 "superior_conjunction": "superior conjunction", "aligned": "aligned with the Sun"}
        return f"{self.target.capitalize()} {names[self.kind]} {date_text(self.jd)}"


def event_kind_check(kind: str, observer: str, target: str) -> tuple[str, str, str]:
    """``(kind, observer key, target key)`` checked: an opposition / conjunction needs a target
    farther out than the observer, an inferior / superior conjunction one closer in."""
    if kind not in EVENTS:
        raise VidgenError(f"event.kind: no event '{kind}' (events: {', '.join(EVENTS)})" + did_you_mean(kind, list(EVENTS)))
    o, t = planet_key(observer, "event.from"), planet_key(target, "event.of")
    if o == t:
        raise VidgenError(f"event: {target} cannot line up with itself; give two different planets")
    outer = TABLE1[t][0][0] > TABLE1[o][0][0]
    if kind in ("opposition", "conjunction") and not outer:
        raise VidgenError(f"event: {t.capitalize()} is closer to the Sun than {o.capitalize()}, so it is never in opposition seen from there; "
                          "use inferior_conjunction (between them) or superior_conjunction (behind the Sun)")
    if kind in ("inferior_conjunction", "superior_conjunction") and outer:
        raise VidgenError(f"event: {t.capitalize()} is farther from the Sun than {o.capitalize()}; use opposition or conjunction")
    return kind, o, t


def next_event(kind: str, observer: str, target: str, after: float, check: bool = True) -> Event:
    """The first ``kind`` (opposition, conjunction, inferior_conjunction, superior_conjunction,
    aligned) of ``target`` seen from ``observer`` strictly after Julian date ``after``: the root
    of the wrapped difference of their heliocentric longitudes (minus 0° or 180°), bracketed on a
    grid of 1/24 synodic period and bisected to about a second. Refused when it falls outside
    1800–2050 (``check``)."""
    kind, o, t = event_kind_check(kind, observer, target)
    offset = EVENTS[kind]
    syn = planet_synodic_period(o, t) / DAY

    def f(jd: float) -> float:
        d = float(longitude(t, jd)) - float(longitude(o, jd)) - offset
        return (d + 180.0) % 360.0 - 180.0

    step = syn / 24.0
    a = float(after) + 1e-6
    fa = f(a)
    for _ in range(int(48 * 1.5) + 2):   # within one and a half synodic periods
        b = a + step
        fb = f(b)
        if fa != 0 and fa * fb <= 0 and abs(fb - fa) < 90.0:   # a crossing, not the ±180° wrap
            lo, hi, flo = a, b, fa
            for _ in range(60):
                mid = (lo + hi) / 2
                fm = f(mid)
                if flo * fm <= 0:
                    hi = mid
                else:
                    lo, flo = mid, fm
                if hi - lo < 1e-5:
                    break
            jd = (lo + hi) / 2
            if check:
                check_valid(jd, where=f"event ({kind} of {t.capitalize()})")
            return Event(kind, o, t, jd, float(distance(o, t, jd)), float(elongation(o, t, jd)))
        a, fa = b, fb
    raise VidgenError(f"event: no {kind} of {t.capitalize()} seen from {o.capitalize()} found after {date_text(after)}")   # pragma: no cover


def events_between(kind: str, observer: str, target: str, start: float, end: float) -> list[Event]:
    """Every ``kind`` event between two Julian dates."""
    out: list[Event] = []
    jd = start
    while True:
        ev = next_event(kind, observer, target, jd, check=False)
        if ev.jd > end:
            return out
        out.append(ev)
        jd = ev.jd


__all__ = ["CENTURY", "EVENTS", "J2000", "PLANETS", "SOURCE", "TABLE1", "VALID_FROM", "VALID_TO", "Event", "MeanElements", "calendar", "check_valid",
           "date_text", "distance", "elongation", "event_kind_check", "events_between", "heliocentric", "julian_date", "longitude", "mean_elements",
           "next_event", "parse_date", "planet_key", "planet_synodic_period", "sidereal_period", "valid_range"]
