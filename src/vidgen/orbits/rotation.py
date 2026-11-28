"""How the Sun, the planets, the Moon and the Galilean moons turn (Step 367):
the direction of each body's north pole, the angle of its prime meridian on a date, its
sidereal rotation period, its axial tilt (obliquity) and its radii. No manim.

Source of the formulas: the **IAU Working Group on Cartographic Coordinates and Rotational
Elements**, report 2015 (Archinal et al. 2018, *Celest. Mech. Dyn. Astron.* 130:22; values for
Mars, Saturn and Neptune as in the 2009 report, Archinal et al. 2011, 109:101 — see each entry).
For a body the report gives the north pole's right ascension α₀ and declination δ₀ (ICRF, degrees)
and the prime meridian's angle W (degrees, measured along the body's equator from its ascending
node on the ICRF equator), each a constant plus a rate per Julian century ``T`` (α₀, δ₀) or per day
``d`` (W) from J2000.0 (JD 2451545.0 TDB), plus periodic terms for some bodies. The IAU north pole is
the pole on the north side of the invariable plane: Venus and Uranus turn backwards about it (W
decreases). Kept here: every term of 0.1° or more and the terms written below; terms smaller than
that are left out (each entry says which). Published values from memory of the reports, not
fetched: **for the owner to check against the report** (entries marked ``check``).

Rotation periods and obliquities as published (for comparison; the formulas above are what is
used): NASA NSSDCA planetary fact sheets (D. R. Williams) — sidereal rotation in hours (Mercury
1407.6, Venus −5832.5, Earth 23.9345, Moon 655.7, Mars 24.6229, Jupiter 9.9250, Saturn 10.656,
Uranus −17.24, Neptune 16.11; the Sun 25.38 d, Carrington) and the obliquity to the orbit in
degrees (0.034, 177.4, 23.44, 6.68, 25.19, 3.13, 26.73, 97.77, 28.32; the Sun's equator 7.25° to
the ecliptic). Radii (km): IAU WGCCRE 2015 (equatorial, equatorial, polar; the Sun 695 700, the
IAU 2015 B3 nominal value).

Frames: vectors are in the **mean ecliptic and equinox of J2000** (x towards the equinox, z
towards the ecliptic's north pole), the frame of JPL's Table 1 and of every Sun-centred ``orbit``
model; ICRF directions are turned into it by the J2000 obliquity ε = 84 381.448″ (the ICRF's
0.02″ frame bias is ignored). A body's own frame (body-fixed): x towards the prime meridian on
the equator, z along the IAU north pole, y = z × x.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import did_you_mean

#: Julian date of J2000.0, days per Julian century, seconds per day.
J2000_JD = 2451545.0
CENTURY_DAYS = 36525.0
DAY_S = 86400.0
#: The obliquity of the ecliptic at J2000 (IAU 1976: 84 381.448″), which turns ICRF directions
#: into the mean ecliptic and equinox of J2000.
OBLIQUITY_J2000_DEG = 84381.448 / 3600.0

#: Arguments of periodic terms: name -> (degrees at J2000, rate, per "d" day or "T" century).
ARGUMENTS: dict[str, tuple[float, float, str]] = {
    # the Moon (2015 report; E1 is the node of the Moon's orbit, period 18.6 years)
    "E1": (125.045, -0.0529921, "d"), "E2": (250.089, -0.1059842, "d"),
    # Jupiter's moons (J3..J8, per century)
    "J3": (283.90, 4850.7, "T"), "J4": (355.80, 1191.3, "T"), "J5": (119.90, 262.1, "T"),
    "J6": (229.80, 64.3, "T"), "J7": (352.25, 2382.6, "T"), "J8": (113.35, 6070.0, "T"),
    # Neptune
    "N": (357.85, 52.316, "T"),
}


@dataclass(frozen=True)
class Term:
    """A periodic term: ``amplitude`` degrees × sin or cos of an argument (:data:`ARGUMENTS`), added
    to ``what``: ``alpha`` (α₀), ``delta`` (δ₀) or ``w`` (W)."""

    what: str
    amplitude: float
    func: str
    argument: str


@dataclass(frozen=True)
class RotationModel:
    """A body's rotation (IAU WGCCRE form; see the module docstring): α₀ = ``alpha0`` +
    ``alpha_rate`` T, δ₀ = ``delta0`` + ``delta_rate`` T (degrees; T Julian centuries from J2000),
    W = ``w0`` + ``w_rate`` d (+ ``w_quad`` d²; degrees, d days from J2000), plus ``terms``;
    ``radii`` (m: equatorial, equatorial, polar or the three axes), ``mean_radius`` (m), the
    published sidereal period (``period_published_h``, hours; negative: retrograde) and obliquity
    to the orbit (``obliquity_published``, degrees; ``None``: not in the fact sheets), whether it turns once per orbit
    (``synchronous``: its prime meridian faces the body it orbits), the ``source`` and what is
    left out or uncertain (``note``; ``check``: values for the owner to check)."""

    key: str
    name: str
    alpha0: float
    alpha_rate: float
    delta0: float
    delta_rate: float
    w0: float
    w_rate: float
    radii: tuple[float, float, float]
    mean_radius: float
    period_published_h: float
    obliquity_published: float | None
    source: str
    note: str = ""
    terms: tuple[Term, ...] = field(default=())
    w_quad: float = 0.0
    synchronous: bool = False
    check: bool = True

    @property
    def period(self) -> float:
        """The sidereal rotation period from the formula (s): 360° / Ẇ; negative when the body
        turns backwards about its IAU north pole (Venus, Uranus)."""
        return 360.0 / self.w_rate * DAY_S

    @property
    def retrograde(self) -> bool:
        return self.w_rate < 0

    def _angles(self, jd: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """α₀, δ₀ and W (degrees) at Julian date(s) ``jd``."""
        d = np.asarray(jd, dtype=float) - J2000_JD
        t = d / CENTURY_DAYS
        alpha = self.alpha0 + self.alpha_rate * t
        delta = self.delta0 + self.delta_rate * t
        w = self.w0 + self.w_rate * d + self.w_quad * d * d
        for term in self.terms:
            base, rate, unit = ARGUMENTS[term.argument]
            arg = np.radians(base + rate * (d if unit == "d" else t))
            value = term.amplitude * (np.sin(arg) if term.func == "sin" else np.cos(arg))
            if term.what == "alpha":
                alpha = alpha + value
            elif term.what == "delta":
                delta = delta + value
            else:
                w = w + value
        return np.asarray(alpha), np.asarray(delta), np.asarray(w)

    def pole_radec(self, jd: Any) -> tuple[Any, Any]:
        """The IAU north pole's right ascension and declination (degrees, ICRF) at ``jd``."""
        alpha, delta, _ = self._angles(jd)
        return (float(alpha), float(delta)) if np.ndim(jd) == 0 else (alpha, delta)

    def prime_meridian(self, jd: Any) -> Any:
        """W (degrees, in [0, 360)) at ``jd``: the prime meridian's angle from the equator's
        ascending node on the ICRF equator."""
        w = np.mod(self._angles(jd)[2], 360.0)
        return float(w) if np.ndim(jd) == 0 else w

    def pole(self, jd: Any) -> np.ndarray:
        """The IAU north pole (unit vector, ecliptic J2000) at ``jd``: ``(3,)`` or ``(N, 3)``."""
        alpha, delta, _ = self._angles(jd)
        return ecliptic_from_icrf(radec_vector(alpha, delta))

    def spin_axis(self, jd: Any) -> np.ndarray:
        """The axis the body turns about counterclockwise (right-hand rule): the north pole, or
        the south pole for a body turning backwards."""
        return -self.pole(jd) if self.retrograde else self.pole(jd)

    def frame(self, jd: Any) -> np.ndarray:
        """The body-fixed frame in ecliptic J2000 (columns: x towards the prime meridian, y, z
        the north pole) at ``jd``: ``(3, 3)`` or ``(N, 3, 3)`` — R = E · R₃(α₀ + 90°) R₁(90° − δ₀) R₃(W),
        E the turn from ICRF to the ecliptic."""
        alpha, delta, w = self._angles(jd)
        m = _rz(np.radians(alpha) + math.pi / 2) @ _rx(math.pi / 2 - np.radians(delta)) @ _rz(np.radians(w))
        out = _ECLIPTIC_FROM_ICRF @ m
        return out


def _rz(angle: Any) -> np.ndarray:
    a = np.asarray(angle, dtype=float)
    c, s, z, o = np.cos(a), np.sin(a), np.zeros_like(a), np.ones_like(a)
    return np.moveaxis(np.array([[c, -s, z], [s, c, z], [z, z, o]]), [0, 1], [-2, -1])


def _rx(angle: Any) -> np.ndarray:
    a = np.asarray(angle, dtype=float)
    c, s, z, o = np.cos(a), np.sin(a), np.zeros_like(a), np.ones_like(a)
    return np.moveaxis(np.array([[o, z, z], [z, c, -s], [z, s, c]]), [0, 1], [-2, -1])


#: ICRF (equatorial) coordinates -> ecliptic J2000 coordinates: a turn by −ε about x.
_ECLIPTIC_FROM_ICRF = _rx(-math.radians(OBLIQUITY_J2000_DEG))


def radec_vector(alpha: Any, delta: Any) -> np.ndarray:
    """The unit vector(s) (ICRF) of right ascension ``alpha`` and declination ``delta`` (degrees)."""
    a, d = np.radians(alpha), np.radians(delta)
    return np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], axis=-1)


def ecliptic_from_icrf(vectors: Any) -> np.ndarray:
    """ICRF vector(s) ``(3,)`` / ``(N, 3)`` in the mean ecliptic and equinox of J2000."""
    return np.asarray(vectors, dtype=float) @ _ECLIPTIC_FROM_ICRF.T


def equator_frame(model: RotationModel, jd: float) -> np.ndarray:
    """The frame of a body's equator in ecliptic J2000 (columns): x the ecliptic's ascending node
    on the body's equator (for the Earth: the equinox, so that this is the Earth's equatorial
    frame), z the IAU north pole, y = z × x. Orbits measured from the body's equator
    (``plane: equator`` presets) are turned into the ecliptic by it."""
    z = model.pole(jd)
    node = np.cross(z, [0.0, 0.0, 1.0])
    n = float(np.linalg.norm(node))
    x = node / n if n > 1e-12 else np.array([1.0, 0.0, 0.0])
    return np.column_stack([x, np.cross(z, x), z])


def obliquity(model: RotationModel, orbit_normal: Any, jd: float = J2000_JD) -> float:
    """The axial tilt (degrees, 0–180): the angle between the spin axis (right-hand rule) and the
    orbit's normal ``orbit_normal`` (ecliptic J2000)."""
    n = np.asarray(orbit_normal, dtype=float)
    c = float(model.spin_axis(jd) @ (n / np.linalg.norm(n)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def quaternions(matrices: Any) -> np.ndarray:
    """Unit quaternions (x, y, z, w; w ≥ 0) of rotation matrices ``(3, 3)`` / ``(N, 3, 3)``
    (Shepperd's method: the largest of the four first, for accuracy)."""
    m = np.asarray(matrices, dtype=float)
    flat = m.reshape(-1, 3, 3)
    out = np.zeros((len(flat), 4))
    for k, r in enumerate(flat):
        tr = r[0, 0] + r[1, 1] + r[2, 2]
        cases = [tr, r[0, 0], r[1, 1], r[2, 2]]
        j = int(np.argmax(cases))
        if j == 0:
            s = math.sqrt(1.0 + tr) * 2
            q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, s / 4]
        elif j == 1:
            s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            q = [s / 4, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s]
        elif j == 2:
            s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            q = [(r[0, 1] + r[1, 0]) / s, s / 4, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s]
        else:
            s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            q = [(r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, s / 4, (r[1, 0] - r[0, 1]) / s]
        q = np.array(q)
        out[k] = -q if q[3] < 0 else q
    return out[0] if m.ndim == 2 else out


_KM = 1000.0
_WG15 = "IAU WGCCRE 2015 (Archinal et al. 2018)"
_WG09 = "IAU WGCCRE 2009 (Archinal et al. 2011)"


def _t(what: str, amplitude: float, func: str, argument: str) -> Term:
    return Term(what, amplitude, func, argument)


#: The rotation of each body, by preset key.
ROTATIONS: dict[str, RotationModel] = {m.key: m for m in [
    RotationModel("sun", "Sun", 286.13, 0.0, 63.87, 0.0, 84.176, 14.1844000, (695_700 * _KM,) * 3, 695_700 * _KM, 25.38 * 24, 7.25,
                  _WG15 + "; radius IAU 2015 B3 nominal",
                  note="W is the Carrington rotation (the surface turns faster at the equator, 25 d there, about 35 d near the poles); "
                       "obliquity: the equator to the ecliptic", check=False),
    RotationModel("mercury", "Mercury", 281.0103, -0.0328, 61.4155, -0.0049, 329.5988, 6.1385108, (2440.53 * _KM, 2440.53 * _KM, 2438.26 * _KM),
                  2439.4 * _KM, 1407.6, 0.034, _WG15, note="the libration terms of W (largest 0.01°) left out"),
    RotationModel("venus", "Venus", 272.76, 0.0, 67.16, 0.0, 160.20, -1.4813688, (6051.8 * _KM,) * 3, 6051.8 * _KM, -5832.5, 177.4, _WG15,
                  note="turns backwards (W decreases)", check=False),
    RotationModel("earth", "Earth", 0.00, -0.641, 90.00, -0.557, 190.147, 360.9856235, (6378.1366 * _KM, 6378.1366 * _KM, 6356.7519 * _KM),
                  6371.0084 * _KM, 23.9345, 23.44, _WG15,
                  note="an approximate model (the report says so): W is in TDB without ΔT = TT − UT1 (about 69 s now), so the prime "
                       "meridian is off by about 0.3° of the Earth's real rotation; precession only to first order", check=False),
    RotationModel("moon", "Moon", 269.9949, 0.0031, 66.5392, 0.0130, 38.3213, 13.17635815, (1737.4 * _KM,) * 3, 1737.4 * _KM, 655.7, 6.68,
                  _WG15 + " (mean Earth / polar axis frame)",
                  terms=(_t("alpha", -3.8787, "sin", "E1"), _t("alpha", -0.1204, "sin", "E2"),
                         _t("delta", 1.5419, "cos", "E1"), _t("delta", 0.0239, "cos", "E2"),
                         _t("w", 3.5610, "sin", "E1"), _t("w", 0.1208, "sin", "E2")),
                  w_quad=-1.4e-12, synchronous=True,
                  note="periodic terms E3 to E13 (each under 0.1°) left out; turns once per orbit (its near side faces the Earth)"),
    RotationModel("mars", "Mars", 317.68143, -0.1061, 52.88650, -0.0609, 176.630, 350.89198226, (3396.19 * _KM, 3396.19 * _KM, 3376.20 * _KM),
                  3389.50 * _KM, 24.6229, 25.19, _WG09 + "; radii " + _WG15,
                  note="the 2009 model; the 2015 report adds small periodic terms (Kuchynka et al. 2014) not included here"),
    RotationModel("jupiter", "Jupiter", 268.056595, -0.006499, 64.495303, 0.002413, 284.95, 870.5360000, (71_492 * _KM, 71_492 * _KM, 66_854 * _KM),
                  69_911 * _KM, 9.9250, 3.13, _WG15, note="System III (the magnetic field's period); the pole's periodic terms (each under 0.001°) left out"),
    RotationModel("saturn", "Saturn", 40.589, -0.036, 83.537, -0.004, 38.90, 810.7939024, (60_268 * _KM, 60_268 * _KM, 54_364 * _KM),
                  58_232 * _KM, 10.656, 26.73, _WG09 + "; radii " + _WG15,
                  note="System III (Voyager radio period); Saturn's interior period is uncertain by minutes"),
    RotationModel("uranus", "Uranus", 257.311, 0.0, -15.175, 0.0, 203.81, -501.1600928, (25_559 * _KM, 25_559 * _KM, 24_973 * _KM),
                  25_362 * _KM, -17.24, 97.77, _WG15, note="turns backwards about its IAU north pole (W decreases); lies on its side"),
    RotationModel("neptune", "Neptune", 299.36, 0.0, 43.46, 0.0, 253.18, 536.3128492, (24_764 * _KM, 24_764 * _KM, 24_341 * _KM),
                  24_622 * _KM, 16.11, 28.32, _WG09 + "; radii " + _WG15,
                  terms=(_t("alpha", 0.70, "sin", "N"), _t("delta", -0.51, "cos", "N"), _t("w", -0.48, "sin", "N")),
                  note="Voyager's radio period (16.11 h); the 2015 report may give another W (Karkoschka 2011, about 15.97 h): for the owner to check"),
    RotationModel("io", "Io", 268.05, -0.009, 64.50, 0.003, 200.39, 203.4889538, (1829.4 * _KM, 1819.4 * _KM, 1815.7 * _KM), 1821.49 * _KM,
                  1.769137786 * 24, None, _WG15,
                  terms=(_t("alpha", 0.094, "sin", "J3"), _t("alpha", 0.024, "sin", "J4"), _t("delta", 0.040, "cos", "J3"),
                         _t("delta", 0.011, "cos", "J4"), _t("w", -0.085, "sin", "J3"), _t("w", -0.022, "sin", "J4")),
                  synchronous=True, note="turns once per orbit (the sub-Jupiter point near longitude 0)"),
    RotationModel("europa", "Europa", 268.08, -0.009, 64.51, 0.003, 36.022, 101.3747235, (1562.6 * _KM, 1560.3 * _KM, 1559.5 * _KM), 1560.8 * _KM,
                  3.551181041 * 24, None, _WG15,
                  terms=(_t("alpha", 1.086, "sin", "J4"), _t("alpha", 0.060, "sin", "J5"), _t("alpha", 0.015, "sin", "J6"), _t("alpha", 0.009, "sin", "J7"),
                         _t("delta", 0.468, "cos", "J4"), _t("delta", 0.026, "cos", "J5"), _t("delta", 0.007, "cos", "J6"), _t("delta", 0.002, "cos", "J7"),
                         _t("w", -0.980, "sin", "J4"), _t("w", -0.054, "sin", "J5"), _t("w", -0.014, "sin", "J6"), _t("w", -0.008, "sin", "J7")),
                  synchronous=True, note="turns once per orbit"),
    RotationModel("ganymede", "Ganymede", 268.20, -0.009, 64.57, 0.003, 44.064, 50.3176081, (2631.2 * _KM,) * 3, 2631.2 * _KM, 7.15455296 * 24, None,
                  _WG15,
                  terms=(_t("alpha", -0.037, "sin", "J4"), _t("alpha", 0.431, "sin", "J5"), _t("alpha", 0.091, "sin", "J6"),
                         _t("delta", -0.016, "cos", "J4"), _t("delta", 0.186, "cos", "J5"), _t("delta", 0.039, "cos", "J6"),
                         _t("w", 0.033, "sin", "J4"), _t("w", -0.389, "sin", "J5"), _t("w", -0.082, "sin", "J6")),
                  synchronous=True, note="turns once per orbit"),
    RotationModel("callisto", "Callisto", 268.72, -0.009, 64.83, 0.003, 259.51, 21.5710715, (2410.3 * _KM,) * 3, 2410.3 * _KM, 16.6890184 * 24, None,
                  _WG15,
                  terms=(_t("alpha", -0.068, "sin", "J5"), _t("alpha", 0.590, "sin", "J6"), _t("alpha", 0.010, "sin", "J8"),
                         _t("delta", -0.029, "cos", "J5"), _t("delta", 0.254, "cos", "J6"), _t("delta", -0.004, "cos", "J8"),
                         _t("w", 0.061, "sin", "J5"), _t("w", -0.533, "sin", "J6"), _t("w", -0.009, "sin", "J8")),
                  synchronous=True, note="turns once per orbit"),
]}


def rotation_model(name: str, where: str = "rotation") -> RotationModel:
    """The rotation of preset ``name`` (sun, a planet, moon, io, europa, ganymede, callisto);
    raises with did-you-mean."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    key = {"sol": "sun", "luna": "moon"}.get(key, key)
    if key in ROTATIONS:
        return ROTATIONS[key]
    raise VidgenError(f"{where}: no rotation data for '{name}'" + did_you_mean(key, list(ROTATIONS)) + f"; bodies with it: {', '.join(ROTATIONS)}")


__all__ = ["ARGUMENTS", "CENTURY_DAYS", "J2000_JD", "OBLIQUITY_J2000_DEG", "ROTATIONS", "RotationModel", "Term", "ecliptic_from_icrf", "equator_frame",
           "obliquity", "quaternions", "radec_vector", "rotation_model"]
