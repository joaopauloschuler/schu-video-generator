"""World map data and projection (DESIGN.md §39; no manim).

The bundled map ``data/geo/world-110m.json`` holds the Natural Earth 1:110m admin-0 countries
(public domain; built by ``tools/make_world_map.py`` from the ``world-atlas`` and
``i18n-iso-countries`` npm packages): ISO 3166-1 alpha-2 / alpha-3 codes, English names and
aliases, a label point, a "main" bounding box and polygons. Borders are Natural Earth's de facto
representation.

Maps use the **Equal Earth** projection (Šavrič, Patterson & Jenny 2018: equal-area, pleasant
shapes), centred on the view's middle longitude. :class:`MapView` fits a longitude / latitude
box into a rectangle of the scene and turns coordinates and country polygons into scene points
(polygons clipped to the view).
"""

from __future__ import annotations

import difflib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

import numpy as np

from vidgen.errors import VidgenError
from vidgen.regions import Region

#: The bundled map file (package data).
MAP_FILE = "world-110m.json"
#: Named views as ``(lon_min, lat_min, lon_max, lat_max)``; ``world`` leaves out Antarctica.
MAP_VIEWS: dict[str, tuple[float, float, float, float]] = {
    "world": (-180.0, -58.0, 180.0, 84.0),
    "europe": (-25.0, 34.0, 45.0, 71.0),
    "africa": (-19.0, -36.0, 53.0, 38.0),
    "asia": (25.0, -11.0, 150.0, 62.0),
    "middle_east": (25.0, 12.0, 63.0, 42.0),
    "north_america": (-170.0, 7.0, -52.0, 75.0),
    "south_america": (-93.0, -56.0, -32.0, 14.0),
    "oceania": (110.0, -48.0, 180.0, 0.0),
}
#: Southern edge of the ``world`` view when Antarctica is drawn.
SOUTH_POLE_VIEW = -90.0
_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3.0) / 2.0


def equal_earth(lon: np.ndarray | float, lat: np.ndarray | float, lon0: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Equal Earth projection of degrees ``lon`` / ``lat`` (arrays or numbers) centred on
    ``lon0``: ``(x, y)`` in units of the earth's radius (the world is 5.41 wide, 2.63 tall)."""
    lam = np.radians(np.asarray(lon, dtype=float) - lon0)
    theta = np.arcsin(_M * np.sin(np.radians(np.asarray(lat, dtype=float))))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = lam * np.cos(theta) / (_M * (_A1 + 3 * _A2 * t2 + t6 * (7 * _A3 + 9 * _A4 * t2)))
    y = theta * (_A1 + _A2 * t2 + t6 * (_A3 + _A4 * t2))
    return x, y


@dataclass(frozen=True)
class Country:
    """A country of the bundled map. ``a3`` is the ISO 3166-1 alpha-3 code (Natural Earth's
    ``ADM0_A3`` for the few without one: ``CYN`` N. Cyprus, ``SOL`` Somaliland), ``a2`` the alpha-2
    code (``""`` when there is none), ``name`` a short English name, ``label`` a point well inside
    its largest part and ``main`` the box of its parts near that one (lon/lat)."""

    a3: str
    a2: str
    name: str
    aliases: tuple[str, ...]
    label: tuple[float, float]
    main: tuple[float, float, float, float]
    polygons: tuple[tuple[np.ndarray, ...], ...] = field(repr=False, compare=False)

    @property
    def codes(self) -> list[str]:
        """``[a3, a2]`` (the codes it has)."""
        return [c for c in (self.a3, self.a2) if c]


def _normal(name: str) -> str:
    """A name for lookups: no accents, case, punctuation or leading "the"."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    plain = re.sub(r"[^a-z0-9 ]+", " ", plain.casefold().replace("&", " and "))
    plain = " ".join(plain.split())
    return plain[4:] if plain.startswith("the ") else plain


@dataclass(frozen=True)
class _World:
    countries: tuple[Country, ...]
    index: dict[str, Country]
    small: dict[str, tuple[str, str]]


@lru_cache(maxsize=1)
def _world() -> _World:
    raw = json.loads(resources.files("vidgen").joinpath("data", "geo", MAP_FILE).read_text(encoding="utf-8"))
    countries = []
    for c in raw["countries"]:
        polygons = tuple(
            tuple(np.asarray(ring, dtype=float).reshape(-1, 2) / 100.0 for ring in poly) for poly in c["polygons"]
        )
        countries.append(Country(c["a3"], c["a2"], c["name"], tuple(c["aliases"]), tuple(c["label"]), tuple(c["main"]), polygons))
    index: dict[str, Country] = {}
    # codes first, then display names, then aliases: the first claim of a name wins ("Congo")
    for keys in (lambda c: c.codes, lambda c: [c.name], lambda c: c.aliases):
        for country in countries:
            for key in keys(country):
                index.setdefault(_normal(key), country)
    small = {a2: (a3, name) for a2, (a3, name) in raw["small"].items()}
    return _World(tuple(countries), index, small)


def world_countries(antarctica: bool = True) -> list[Country]:
    """Every country of the bundled map (177; sorted by alpha-3 code)."""
    return [c for c in _world().countries if antarctica or c.a3 != "ATA"]


def find_country(name: str) -> Country:
    """The country named ``name``: an ISO alpha-2 or alpha-3 code (``DE``, ``DEU``), its name or
    a common alias (``USA``, ``UK``, ``Holland``, ``Ivory Coast``); case, accents and
    punctuation do not matter. Raises :class:`VidgenError` with suggestions."""
    world = _world()
    key = _normal(str(name))
    if key in world.index:
        return world.index[key]
    upper = str(name).strip().upper()
    for a2, (a3, full) in world.small.items():
        if upper in (a2, a3) or key == _normal(full):
            raise VidgenError(f"country {name!r} ({full}) is too small for the bundled 1:110m world map; mark it with a pin {{lon, lat, label}}")
    close = difflib.get_close_matches(key, list(world.index), n=3, cutoff=0.75)
    names = list(dict.fromkeys(world.index[k].name for k in close))
    hint = f"; did you mean {' or '.join(repr(n) for n in names)}?" if names else " (use an ISO code such as 'DE' or 'DEU', or an English name)"
    raise VidgenError(f"unknown country {name!r}{hint}")


# ----- views -------------------------------------------------------------------------------------


def view_box(view: str | Sequence[float], antarctica: bool = False) -> tuple[float, float, float, float]:
    """A view as ``(lon_min, lat_min, lon_max, lat_max)`` with ``lon_max > lon_min`` (a box over
    the antimeridian, ``[170, -50, -170, 0]``, gets ``lon_max + 360``)."""
    if isinstance(view, str):
        if view not in MAP_VIEWS:
            raise VidgenError(f"unknown map view {view!r} (views: {', '.join(MAP_VIEWS)}, auto, or [lon_min, lat_min, lon_max, lat_max])")
        box = MAP_VIEWS[view]
        if view == "world" and antarctica:
            box = (box[0], SOUTH_POLE_VIEW, box[2], box[3])
        return box
    lon0, lat0, lon1, lat1 = (float(v) for v in view)
    if lon1 <= lon0:
        lon1 += 360.0
    return lon0, lat0, lon1, lat1


def fit_view(points: Iterable[tuple[float, float]], pad: float = 0.15, min_size: tuple[float, float] = (14.0, 9.0)) -> tuple[float, float, float, float]:
    """The box around lon/lat ``points`` grown by ``pad`` of its size on each side (at least
    ``min_size`` degrees); over the antimeridian when that is narrower; the ``world`` view when
    it would span more than 200 degrees of longitude."""
    pts = list(points)
    if not pts:
        return MAP_VIEWS["world"]
    lats = [p[1] for p in pts]
    best: tuple[float, float] | None = None
    for lons in ([p[0] for p in pts], [p[0] + 360.0 if p[0] < 0 else p[0] for p in pts]):
        if best is None or max(lons) - min(lons) < best[1] - best[0]:
            best = (min(lons), max(lons))
    assert best is not None
    (x0, x1), (y0, y1) = best, (min(lats), max(lats))
    w, h = max(x1 - x0, min_size[0] / (1 + 2 * pad)), max(y1 - y0, min_size[1] / (1 + 2 * pad))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = w * (1 + 2 * pad), h * (1 + 2 * pad)
    if w > 200.0:
        return MAP_VIEWS["world"]
    y0, y1 = max(cy - h / 2, -89.0), min(cy + h / 2, 89.0)
    return cx - w / 2, y0, cx + w / 2, y1


@lru_cache(maxsize=8)
def _projected(lon0: float) -> dict[str, tuple[tuple[np.ndarray, ...], ...]]:
    """Every country's polygons projected around ``lon0`` (each polygon moved by 360 degrees
    when that brings it nearer ``lon0``), keyed by alpha-3 code."""
    out: dict[str, tuple[tuple[np.ndarray, ...], ...]] = {}
    for c in _world().countries:
        polys = []
        for poly in c.polygons:
            middle = float(poly[0][:, 0].mean())
            shift = 360.0 * round((lon0 - middle) / 360.0)
            polys.append(tuple(np.column_stack(equal_earth(r[:, 0] + shift, r[:, 1], lon0)) for r in poly))
        out[c.a3] = tuple(polys)
    return out


def _clip(ring: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    """Sutherland-Hodgman: the part of a ring inside a rectangle (vectorised per edge)."""
    pts = ring
    for axis, bound, keep_low in ((0, x1, True), (0, x0, False), (1, y1, True), (1, y0, False)):
        if len(pts) == 0:
            break
        v = pts[:, axis]
        inside = v <= bound if keep_low else v >= bound
        if inside.all():
            continue
        nxt = np.roll(pts, -1, axis=0)
        nin = np.roll(inside, -1)
        out: list[np.ndarray] = []
        for p, q, pin, qin in zip(pts, nxt, inside, nin):
            if pin:
                out.append(p)
            if pin != qin:
                t = (bound - p[axis]) / (q[axis] - p[axis])
                out.append(p + t * (q - p))
        pts = np.array(out) if out else np.zeros((0, 2))
    return pts


class MapView:
    """A lon/lat box shown in a scene rectangle ``area`` with the Equal Earth projection.

    The box is projected around its middle longitude, grown to ``area``'s aspect ratio (more of
    the map around it, within the world's outline) and fitted inside ``area``; :attr:`region` is
    where the map is drawn. :meth:`point` gives scene points, :meth:`polygons` a country's
    polygons clipped to the view (scene coordinates)."""

    def __init__(self, box: Sequence[float], area: Region, antarctica: bool = False, expand: bool = True) -> None:
        lon_min, lat_min, lon_max, lat_max = (float(v) for v in box)
        self.box = (lon_min, lat_min, lon_max, lat_max)
        self.lon0 = round((lon_min + lon_max) / 2.0, 6)
        if self.lon0 > 180.0:
            self.lon0 -= 360.0
        self.antarctica = antarctica
        edge = np.linspace(0.0, 1.0, 41)
        lons = np.concatenate([lon_min + (lon_max - lon_min) * edge, np.full(41, lon_max), lon_min + (lon_max - lon_min) * edge, np.full(41, lon_min)])
        lats = np.concatenate([np.full(41, lat_min), lat_min + (lat_max - lat_min) * edge, np.full(41, lat_max), lat_min + (lat_max - lat_min) * edge])
        xs, ys = equal_earth(lons, lats, (lon_min + lon_max) / 2.0)
        x0, x1, y0, y1 = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
        wx = float(equal_earth(180.0, 0.0)[0])
        south = SOUTH_POLE_VIEW if antarctica else MAP_VIEWS["world"][1]
        wy0, wy1 = float(equal_earth(0.0, south)[1]), float(equal_earth(0.0, MAP_VIEWS["world"][3])[1])
        aspect = area.width / area.height
        if expand:
            w, h = x1 - x0, y1 - y0
            if w / h < aspect:
                grow = min(h * aspect, 2 * wx) - w
                x0, x1 = x0 - grow / 2, x1 + grow / 2
                if x0 < -wx:
                    x0, x1 = -wx, x1 + (-wx - x0)
                if x1 > wx:
                    x0, x1 = x0 - (x1 - wx), wx
            else:
                grow = min(w / aspect, wy1 - wy0) - h
                y0, y1 = y0 - grow / 2, y1 + grow / 2
                if y0 < wy0:
                    y0, y1 = wy0, y1 + (wy0 - y0)
                if y1 > wy1:
                    y0, y1 = y0 - (y1 - wy1), wy1
        self.extent = (x0, y0, x1, y1)
        #: Whether the view cuts the world at its sides (a regional view, drawn as a panel).
        self.cropped = x0 > -0.99 * wx or x1 < 0.99 * wx
        self.scale = min(area.width / (x1 - x0), area.height / (y1 - y0))
        cx, cy = area.center[0], area.center[1]
        w, h = (x1 - x0) * self.scale, (y1 - y0) * self.scale
        #: Where the map is drawn (scene coordinates).
        self.region = Region(float(cx - w / 2), float(cy - h / 2), float(cx + w / 2), float(cy + h / 2))
        self._origin = (x0, y0)

    def _to_scene(self, xy: np.ndarray) -> np.ndarray:
        out = np.zeros((len(xy), 3))
        out[:, 0] = self.region.x0 + (xy[:, 0] - self._origin[0]) * self.scale
        out[:, 1] = self.region.y0 + (xy[:, 1] - self._origin[1]) * self.scale
        return out

    def point(self, lon: float, lat: float) -> np.ndarray:
        """The scene point ``[x, y, 0]`` of a longitude / latitude (moved by 360 degrees when that
        brings it nearer the view's middle)."""
        lon = float(lon) + 360.0 * round((self.lon0 - float(lon)) / 360.0)
        x, y = equal_earth(lon, lat, self.lon0)
        return self._to_scene(np.array([[float(x), float(y)]]))[0]

    def contains(self, lon: float, lat: float, margin: float = 0.0) -> bool:
        """Whether a lon/lat shows inside the view (``margin`` scene units in from its edge)."""
        x, y = self.point(lon, lat)[:2]
        r = self.region
        return r.x0 + margin <= x <= r.x1 - margin and r.y0 + margin <= y <= r.y1 - margin

    def polygons(self, country: Country) -> list[list[np.ndarray]]:
        """The country's polygons in scene points (``N x 3``), clipped to the view: a list of
        polygons, each a list of rings (outer ring first, holes after); empty when it is out of
        view."""
        x0, y0, x1, y1 = self.extent
        out = []
        for poly in _projected(self.lon0)[country.a3]:
            outer = poly[0]
            if outer[:, 0].max() < x0 or outer[:, 0].min() > x1 or outer[:, 1].max() < y0 or outer[:, 1].min() > y1:
                continue
            rings = [_clip(r, x0, y0, x1, y1) for r in poly]
            if len(rings[0]) < 3:
                continue
            out.append([self._to_scene(r) for r in rings if len(r) >= 3])
        return out

    def box_region(self, box: Sequence[float]) -> Region:
        """The scene rectangle around a lon/lat box (its edges sampled), not clipped."""
        lon0, lat0, lon1, lat1 = (float(v) for v in box)
        t = np.linspace(0.0, 1.0, 9)
        pts = [self.point(lon0 + (lon1 - lon0) * a, lat) for a in t for lat in (lat0, lat1)]
        pts += [self.point(lon, lat0 + (lat1 - lat0) * a) for a in t for lon in (lon0, lon1)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return Region(float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
