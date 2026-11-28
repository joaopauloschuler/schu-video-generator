"""What a flight must stay over (Step 385): ground heights in the scene's local
frame (:mod:`vidgen.flight.frames`), metres over the world's sphere at a place (x east, z south).

:class:`LandGround` is ``vidgen/space-land``'s ground: a numpy port of its pure height recipe
(``hash2``, ``noised``, ``reliefAt``, ``macroAt``: the first part of ``space-land.js``) evaluated on
its ``definition()`` — ``{radius, recipe, macro: {n, spacing, scale, heights}}``, the macro lattice
made on the GPU and fetched once by :func:`vidgen.web.land.land_definition`. The port gives
``heightAt``'s numbers to float precision (tested against the page). Every operation is in the
same order as the JavaScript; the hash works on unsigned 32-bit integers with wrapping products.
:class:`SphereGround` (a level ground at an elevation over the sphere), :class:`SeaGround` (the sea's
mean level, a wave height as an extra margin) and :class:`FlatGround` (the plane y = elevation of a
flat world) need no page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: The recipe's readings of the noise (``SLOT`` of space-land.js) and its constants.
SLOT = {"warp": 0, "patch": 2, "mountains": 3, "rough": 15, "strata": 19, "dunes": 20, "wander": 21, "field": 22, "ripples": 23,
        "craters": 24, "canyon": 29, "volcano": 33, "count": 34}
CREST = 0.03
RISER = 0.12
CRATER_CLASSES = 5
_GRADIENTS = np.array([[math.cos((i + 0.5) * math.pi / 8), math.sin((i + 0.5) * math.pi / 8)] for i in range(16)])
_M32 = 0xFFFFFFFF


def _u32(a: Any) -> np.ndarray:
    return (np.asarray(a, dtype=np.int64) & _M32).astype(np.uint64)


def _mul(a: np.ndarray, k: int) -> np.ndarray:
    """``Math.imul(a, k) >>> 0`` on unsigned 32-bit values (held in uint64)."""
    return (a * np.uint64(k)) & np.uint64(_M32)


def hash2(ix: Any, iz: Any, seed: Any) -> np.ndarray:
    """space-land's ``hash2``: an unsigned 32-bit hash of a lattice point and a seed (uint64 array)."""
    h = _mul(_u32(ix), 0x9E3779B1) ^ _mul(_u32(iz), 0x85EBCA77) ^ _mul(_u32(seed), 0xC2B2AE3D)
    h ^= h >> np.uint64(15)
    h = _mul(h, 0x2C1B3C6D)
    h ^= h >> np.uint64(12)
    h = _mul(h, 0x297A2D39)
    h ^= h >> np.uint64(15)
    return h


def noise(qx: np.ndarray, qz: np.ndarray, seed: int) -> np.ndarray:
    """space-land's ``noised(qx, qz, seed)[0]``: gradient noise (one lattice cell a unit), times √2."""
    cx, cz = np.floor(qx), np.floor(qz)
    fx, fz = qx - cx, qz - cz
    ix, iz = cx.astype(np.int64), cz.astype(np.int64)
    a = _GRADIENTS[(hash2(ix, iz, seed) & np.uint64(15)).astype(np.int64)]
    b = _GRADIENTS[(hash2(ix + 1, iz, seed) & np.uint64(15)).astype(np.int64)]
    c = _GRADIENTS[(hash2(ix, iz + 1, seed) & np.uint64(15)).astype(np.int64)]
    d = _GRADIENTS[(hash2(ix + 1, iz + 1, seed) & np.uint64(15)).astype(np.int64)]
    va = a[..., 0] * fx + a[..., 1] * fz
    vb = b[..., 0] * (fx - 1) + b[..., 1] * fz
    vc = c[..., 0] * fx + c[..., 1] * (fz - 1)
    vd = d[..., 0] * (fx - 1) + d[..., 1] * (fz - 1)
    ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
    k = va - vb - vc + vd
    v = va + ux * (vb - va) + uz * (vc - va) + ux * uz * k
    return math.sqrt(2) * v


def _slot_at(s: dict[str, float], x: np.ndarray, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c, n = math.cos(s["turn"]), math.sin(s["turn"])
    return (c * x - n * z) / s["length"], (n * x + c * z) / s["length"]


def _slot_noise(s: dict[str, float], x: np.ndarray, z: np.ndarray) -> np.ndarray:
    qx, qz = _slot_at(s, x, z)
    return noise(qx, qz, int(s["seed"]))


def _clamp(x: Any, lo: float, hi: float) -> Any:
    return np.minimum(hi, np.maximum(lo, x))


def _smooth(a: Any, b: Any, x: Any) -> Any:
    u = _clamp((x - a) / (b - a), 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _bowl(d: np.ndarray, floor: float = 0.8) -> np.ndarray:
    inside = np.where(d < 1, np.maximum(d * d - 1, -floor), 0.0)
    return inside + 0.30 * np.exp(-np.power(np.abs(d - 1) * np.where(d < 1, 8.0, 3.0), 1.5))


def _crater_class(s: dict[str, float], x: np.ndarray, z: np.ndarray, density: float, deep: float) -> np.ndarray:
    qx, qz = _slot_at(s, x, z)
    cx, cz = np.floor(qx).astype(np.int64), np.floor(qz).astype(np.int64)
    seed = int(s["seed"])
    h = np.zeros_like(qx)
    for j in (-1, 0, 1):
        for i in (-1, 0, 1):
            k = hash2(cx + i, cz + j, seed).astype(np.int64)
            k2 = hash2(cx + i, cz + j, seed + 77).astype(np.int64)
            keep = (k2 & 65535) / 65535 < density
            r3 = ((k >> 20) & 1023) / 1023
            radius = 0.08 + 0.22 * r3 * r3
            ex = (cx + i) + 0.25 + 0.5 * (k & 1023) / 1023
            ez = (cz + j) + 0.25 + 0.5 * ((k >> 10) & 1023) / 1023
            h = h + np.where(keep, radius * deep * _bowl(np.hypot(qx - ex, qz - ez) / radius), 0.0)
    return h


def _wall_at(k: dict[str, float], d: np.ndarray, soft: float) -> np.ndarray:
    u = _clamp((d - k["floor"]) / (1 - k["floor"]), 0.0, 1.0)
    q = np.minimum(u * k["steps"], k["steps"] - 1e-6)
    f = np.floor(q)
    return 0.85 * (f + _smooth(0.5 - soft, 0.5 + soft, q - f)) / k["steps"] + 0.15 * u


def _cone_at(v: dict[str, float], d: np.ndarray, angle: np.ndarray, turn: np.ndarray) -> np.ndarray:
    flank = np.power(np.maximum(1 - d, 0.0), 1.6) * (1 + v["ridges"] * np.sin(9 * angle + turn) * _smooth(v["crater"], 3 * v["crater"], d) * (1 - d))
    top = math.pow(1 - v["crater"], 1.6) - 0.5 * v["crater"] * _smooth(v["crater"], 0.55 * v["crater"], d)
    return np.where(d >= 1, 0.0, np.minimum(flank, top))


def _volcano_height(s: dict[str, float], v: dict[str, float], x: np.ndarray, z: np.ndarray) -> np.ndarray:
    qx, qz = _slot_at(s, x, z)
    cx, cz = np.floor(qx).astype(np.int64), np.floor(qz).astype(np.int64)
    seed = int(s["seed"])
    out = np.zeros_like(qx)
    for j in (-1, 0, 1):
        for i in (-1, 0, 1):
            a = hash2(cx + i, cz + j, seed).astype(np.int64)
            b = hash2(cx + i, cz + j, seed + 77).astype(np.int64)
            keep = (b & 65535) / 65535 < v["density"]
            size = 0.6 + 0.4 * ((a >> 20) & 1023) / 1023
            ex = qx - ((cx + i) + 0.3 + 0.4 * (a & 1023) / 1023)
            ez = qz - ((cz + j) + 0.3 + 0.4 * ((a >> 10) & 1023) / 1023)
            d = np.hypot(ex, ez) * s["length"] / (v["radius"] * size)
            angle = np.arctan2(ez, ex)
            turn = 6.2831853 * ((b >> 16) & 255) / 255
            out = out + np.where(keep, size * _cone_at(v, d, angle, turn), 0.0)
    return out


def _strata_share(st: dict[str, float], level: np.ndarray) -> Any:
    return 1.0 if st["from"] < -9e5 else 1 - _smooth(st["from"], st["to"], level) * 0.85


def relief_at(recipe: dict[str, Any], macro_height: Any, x: Any, z: Any) -> np.ndarray:
    """space-land's ``reliefAt(recipe, M, x, z)``: the ground's height (m over the sphere) at places
    (x, z) (m, the frame's +x and +z) where the macro's height is ``macro_height`` (m)."""
    x, z, big = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(z, dtype=float), np.asarray(macro_height, dtype=float))
    r, S = recipe, recipe["slots"]
    m, g, d, c, st, k, v = r["mountains"], r["rough"], r["dunes"], r["craters"], r["strata"], r["canyons"], r["volcanoes"]
    wx, wz = _slot_noise(S[SLOT["warp"]], x, z), _slot_noise(S[SLOT["warp"] + 1], x, z)
    X, Z = x + m["warp"] * m["length"] * wx, z + m["warp"] * m["length"] * wz
    level = big + m["patch"] * _slot_noise(S[SLOT["patch"]], x, z)
    mask = m["base"] + (1 - m["base"]) * _smooth(m["from"], m["to"], level)
    total, a, carry = np.zeros_like(x), 1.0, np.ones_like(x)
    for i in range(int(r["octaves"])):
        value = _slot_noise(S[SLOT["mountains"] + i], X, Z)
        if i < m["ridged"]:
            q = 1 + CREST - np.sqrt(value * value + CREST * CREST)
            value = q * q
        else:
            value = 0.5 + 0.5 * value
        total = total + a * carry * value
        carry = np.power(_clamp(1.6 * value, 1e-4, 1.0), m["erosion"])
        a *= m["gain"]
    with np.errstate(invalid="ignore"):
        hm = m["height"] * (np.power(total / r["norm"], m["sharp"]) - m["mid"])
    if st["strength"] > 0:
        wob = st["wobble"] * _slot_noise(S[SLOT["strata"]], x, z)
        u = hm / st["step"] + wob
        f = np.floor(u)
        hm = hm + st["strength"] * _strata_share(st, level) * (st["step"] * (f + _smooth(0.5 - st["soft"], 0.5 + st["soft"], u - f)) - hm)
    h = big + mask * hm
    b = 1.0
    for j in range(4):
        h = h + g["height"] * b * (1 - g["calm"] * mask) * _slot_noise(S[SLOT["rough"] + j], x, z)
        b *= 0.5
    if d["height"] > 0:
        wander = d["wander"] * _slot_noise(S[SLOT["wander"]], x, z)
        fld = (_smooth(1 - 2 * d["field"], 1.4 - 2 * d["field"], _slot_noise(S[SLOT["field"]], x, z)) * _smooth(d["from"], d["from"] + 200, level)
               * (1 - _smooth(d["to"] - 200, d["to"], level)) * (1 - mask))

        def shape(ph: np.ndarray) -> np.ndarray:
            t = ph - np.floor(ph)
            return np.where(t < 0.7, t / 0.7, (1 - t) / 0.3)

        dunes = _slot_at(S[SLOT["dunes"]], x, z)[0]
        ripples = _slot_at(S[SLOT["ripples"]], x, z)[0]
        h = h + d["height"] * fld * (np.power(shape(dunes + wander), 1.3) - 0.45 + 0.2 * (shape(ripples + 2.3 * wander) - 0.5))
    if c["density"] > 0:
        for i in range(CRATER_CLASSES):
            s = S[SLOT["craters"] + i]
            h = h + s["length"] * _crater_class(s, x, z, c["density"], c["deep"])
    if v["height"] > 0:
        h = h + v["height"] * _volcano_height(S[SLOT["volcano"]], v, x, z)
    if k["depth"] > 0:
        X2 = x + k["wander"] * k["length"] * _slot_noise(S[SLOT["canyon"] + 2], x, z)
        Z2 = z + k["wander"] * k["length"] * _slot_noise(S[SLOT["canyon"] + 3], x, z)
        d1 = np.abs(_slot_noise(S[SLOT["canyon"]], X2, Z2)) * k["length"] / (1.6 * k["width"])
        d2 = np.abs(_slot_noise(S[SLOT["canyon"] + 1], X2, Z2)) * S[SLOT["canyon"] + 1]["length"] / (0.72 * k["width"])
        h = h - k["depth"] * np.maximum(1 - _wall_at(k, d1, RISER), k["branches"] * (1 - _wall_at(k, d2, RISER)))
    return h


def _spline(f: np.ndarray) -> list[np.ndarray]:
    return [(1 - f) ** 3 / 6, (3 * f * f * f - 6 * f * f + 4) / 6, (-3 * f * f * f + 3 * f * f + 3 * f + 1) / 6, f * f * f / 6]


def macro_at(macro: dict[str, Any], x: Any, z: Any) -> np.ndarray:
    """space-land's ``macroAt(macro, x, z)[0]``: the macro's height (m) at places, a cubic B-spline
    through the lattice (``heights``: n × n values in units, rows along +z; metres = value × scale)."""
    n = int(macro["n"])
    heights = np.asarray(macro["heights"], dtype=float).reshape(n, n)
    x, z = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(z, dtype=float))
    u = _clamp(x / macro["spacing"] + (n - 1) / 2, 0, n - 1)
    v = _clamp(z / macro["spacing"] + (n - 1) / 2, 0, n - 1)
    i, j = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    wu, wv = _spline(u - i), _spline(v - j)
    out = np.zeros_like(u)
    for b in range(4):
        row = np.clip(j - 1 + b, 0, n - 1)
        for a in range(4):
            out = out + wu[a] * wv[b] * heights[row, np.clip(i - 1 + a, 0, n - 1)]
    return out * macro["scale"]


def height_of(definition: dict[str, Any], x: Any, z: Any) -> np.ndarray:
    """space-land's ``heightOf(field, x, z)`` on a ``definition()``: metres over the world's sphere."""
    return relief_at(definition["recipe"], macro_at(definition["macro"], x, z), x, z)


# ---------- the grounds a flight is checked against ----------
@dataclass(frozen=True)
class Ground:
    """A ground: ``height(x, z)`` metres over the sphere at local places (``flat``: the y of a flat
    world's plane), and the words for it (``kind``, ``text``); ``margin_extra``: metres added to the
    clearance a check asks for (the sea's waves)."""

    kind: str
    text: str
    margin_extra: float = 0.0

    def height(self, x: Any, z: Any) -> np.ndarray:
        raise NotImplementedError

    @property
    def ceiling(self) -> float:
        """No ground is higher than this (m; a path over it needs no check there)."""
        return math.inf


@dataclass(frozen=True)
class SphereGround(Ground):
    """A level ground ``elevation`` metres over the world's sphere (the page's plain ground, or no ground)."""

    elevation: float = 0.0

    def height(self, x: Any, z: Any) -> np.ndarray:
        return np.full(np.broadcast(np.asarray(x), np.asarray(z)).shape, float(self.elevation))

    @property
    def ceiling(self) -> float:
        return float(self.elevation) + self.margin_extra


@dataclass(frozen=True)
class SeaGround(SphereGround):
    """The sea's mean level (height 0) with ``waves`` metres of crests over it (added to the margin)."""


@dataclass(frozen=True)
class FlatGround(SphereGround):
    """The plane y = ``elevation`` of a flat world (a page without the air's sphere)."""


@dataclass(frozen=True)
class LandGround(Ground):
    """``vidgen/space-land``'s ground from its ``definition()``."""

    definition: dict[str, Any] = field(default_factory=dict)

    def height(self, x: Any, z: Any) -> np.ndarray:
        return height_of(self.definition, x, z)

    @property
    def ceiling(self) -> float:
        macro, recipe = self.definition["macro"], self.definition["recipe"]
        return float(np.max(macro["heights"])) * float(macro["scale"]) + float(recipe["bound"]["over"]) + 100.0


__all__ = ["FlatGround", "Ground", "LandGround", "SeaGround", "SphereGround", "hash2", "height_of", "macro_at", "noise", "relief_at"]
