"""Build the bundled world map ``src/vidgen/data/geo/world-110m.json`` from npm packages.

Not shipped with vidgen; a maintainer tool. Sources (both pinned, fetched with ``npm pack``):

- ``world-atlas`` 2.0.2 (ISC, Mike Bostock): ``countries-110m.json``, the Natural Earth 1:110m
  admin-0 countries (public domain) as TopoJSON; each country has its ISO 3166-1 *numeric* code
  as ``id`` and Natural Earth's short name.
- ``i18n-iso-countries`` 7.14.0 (MIT, widdix GmbH): ``codes.json`` (numeric → alpha-2 / alpha-3)
  and ``langs/en.json`` (English names and common aliases).

Run from the repository root::

    python tools/make_world_map.py                          # npm pack both into a temp folder
    python tools/make_world_map.py --world-atlas DIR --iso DIR   # extracted package/ folders

The output (DESIGN.md §39) is compact JSON: per country its codes, a display name, aliases, a
label point and a "main" bounding box (lon/lat) and its polygons as rings of integer hundredths
of a degree, flattened ``[lon0, lat0, lon1, lat1, ...]``; outer rings counter-clockwise, holes
clockwise (so a non-zero fill leaves holes open). ``small`` lists ISO countries too small for
the 1:110m map (for a helpful error message). The output is deterministic.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "src" / "vidgen" / "data" / "geo" / "world-110m.json"
WORLD_ATLAS = ("world-atlas", "2.0.2")
ISO = ("i18n-iso-countries", "7.14.0")

#: Countries Natural Earth draws that have no ISO 3166-1 numeric code in ``world-atlas``:
#: Natural Earth name → (alpha-2 or "", alpha-3 or Natural Earth's ADM0_A3).
NO_ISO = {"Kosovo": ("XK", "XKX"), "N. Cyprus": ("", "CYN"), "Somaliland": ("", "SOL")}
#: Display names that differ from Natural Earth's short name (by alpha-3).
DISPLAY = {"USA": "United States", "SWZ": "Eswatini", "MKD": "North Macedonia"}
#: Aliases besides Natural Earth's and i18n-iso-countries' names (by alpha-3).
EXTRA_ALIASES = {
    "USA": ["America", "United States"],
    "GBR": ["Britain", "U.K."],
    "NLD": ["Holland", "The Netherlands"],
    "MMR": ["Burma"],
    "SWZ": ["Swaziland"],
    "COD": ["DRC", "DR Congo", "Congo-Kinshasa", "Congo (Kinshasa)"],
    "COG": ["Congo-Brazzaville", "Congo (Brazzaville)"],
    "TLS": ["East Timor"],
    "ARE": ["UAE"],
    "BIH": ["Bosnia"],
    "CAF": ["CAR"],
    "VNM": ["Viet Nam"],
    "LAO": ["Lao PDR"],
    "SYR": ["Syria"],
    "MDA": ["Moldova"],
    "KOR": ["Korea"],
    "CYN": ["Northern Cyprus", "North Cyprus"],
    "MKD": ["Macedonia"],
    "CZE": ["Czech Republic"],
    "CPV": ["Cabo Verde"],
}
#: Polygons whose bounding box is further than this (degrees) from the largest polygon's are not
#: part of a country's "main" box (French Guiana is not where France's label goes).
MAIN_REACH = 15.0


def fetch_package(name: str, version: str, workdir: Path) -> Path:
    """``npm pack name@version`` into ``workdir/name`` and extract it; returns ``package/``."""
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found on PATH (or pass --world-atlas / --iso with extracted packages)")
    dest = workdir / name
    dest.mkdir(parents=True)
    result = subprocess.run([npm, "pack", f"{name}@{version}", "--pack-destination", str(dest)],
                            check=True, capture_output=True, text=True, encoding="utf-8")
    tarball = dest / result.stdout.strip().splitlines()[-1]
    with tarfile.open(tarball) as archive:
        if sys.version_info >= (3, 12):
            archive.extractall(dest, filter="data")
        else:  # pragma: no cover - Python < 3.12 has no extraction filters
            archive.extractall(dest)  # noqa: S202 - the npm registry tarball of a pinned version
    return dest / "package"


# ----- TopoJSON -----------------------------------------------------------------------------------


def decode_arcs(topology: dict[str, Any]) -> list[list[tuple[float, float]]]:
    """The topology's arcs as lists of (lon, lat) (quantized, delta-encoded arcs decoded)."""
    (sx, sy), (tx, ty) = topology["transform"]["scale"], topology["transform"]["translate"]
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def ring(indices: list[int], arcs: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """A closed ring from arc indices (``~i`` = arc ``i`` reversed); shared ends kept once."""
    points: list[tuple[float, float]] = []
    for i in indices:
        arc = arcs[i] if i >= 0 else arcs[~i][::-1]
        points.extend(arc if not points else arc[1:])
    return points


def unwrap(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The ring with longitudes made continuous (no jump from +180 to -180 between neighbours);
    a ring that goes round a pole (Antarctica) is closed along the pole's latitude."""
    out = [points[0]]
    for lon, lat in points[1:]:
        prev = out[-1][0]
        lon += 360.0 * round((prev - lon) / 360.0)
        out.append((lon, lat))
    if abs(out[-1][0] - out[0][0]) > 180.0:  # the closing step crosses all longitudes: round a pole
        pole = -90.0 if sum(lat for _, lat in out) < 0 else 90.0
        out += [(out[-1][0], pole), (out[0][0], pole)]
    return out


def clip_side(points: list[tuple[float, float]], x: float, keep_left: bool) -> list[tuple[float, float]]:
    """Sutherland-Hodgman: the part of a ring on one side of the meridian ``x``."""
    def inside(p: tuple[float, float]) -> bool:
        return p[0] <= x if keep_left else p[0] >= x

    out: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:] + points[:1]):
        if inside(b):
            if not inside(a):
                out.append((x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])))
            out.append(b)
        elif inside(a):
            out.append((x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])))
    return out


def split_at_antimeridian(rings: list[list[tuple[float, float]]]) -> list[list[list[tuple[float, float]]]]:
    """A polygon (outer ring + holes) as polygons within -180..180: a ring that crosses the
    antimeridian is cut there and the part beyond moved by 360 degrees."""
    outer = unwrap(rings[0])
    lo, hi = min(p[0] for p in outer), max(p[0] for p in outer)
    if lo >= -180.0 and hi <= 180.0:
        return [rings]
    if any(max(p[0] for p in r) - min(p[0] for p in r) > 180.0 for r in rings[1:]):
        raise SystemExit("a hole crosses the antimeridian; not supported")
    pieces = []
    for shift in (-360.0, 0.0, 360.0):
        moved = [(lon + shift, lat) for lon, lat in outer]
        part = clip_side(clip_side(moved, 180.0, True), -180.0, False)
        if len(part) >= 3 and abs(signed_area(part)) > 1e-6:
            pieces.append([part])
    return pieces


def signed_area(points: list[tuple[float, float]]) -> float:
    """Shoelace area (positive: counter-clockwise with y up)."""
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))


def quantize(points: list[tuple[float, float]], outer: bool) -> list[int] | None:
    """A ring as flattened hundredths of a degree, oriented (outer CCW, hole CW), closing point
    and repeated points dropped; ``None`` when fewer than 3 points remain."""
    q: list[tuple[int, int]] = []
    for lon, lat in points:
        p = (round(lon * 100), round(lat * 100))
        if not q or q[-1] != p:
            q.append(p)
    if len(q) > 1 and q[0] == q[-1]:
        q.pop()
    if len(q) < 3:
        return None
    if (signed_area([(float(x), float(y)) for x, y in q]) > 0) != outer:
        q.reverse()
    return [v for p in q for v in p]


# ----- label point and main box ----------------------------------------------------------------------


def _inside(x: float, y: float, rings: list[list[tuple[float, float]]]) -> bool:
    """Even-odd point-in-polygon over all rings (an outer ring and its holes)."""
    inside = False
    for pts in rings:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def _edge_distance(x: float, y: float, rings: list[list[tuple[float, float]]], k: float) -> float:
    """Distance from (x, y) to the nearest edge, x scaled by ``k`` (cos of the latitude)."""
    best = math.inf
    for pts in rings:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            ax, ay, bx, by, px = x0 * k, y0, x1 * k, y1, x * k
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1.0)))
            best = min(best, math.hypot(px - ax - t * dx, y - ay - t * dy))
    return best


def label_point(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """A point well inside a polygon (outer ring + holes): the grid point farthest from its
    edges (a pole of inaccessibility, two grid passes), in lon/lat."""
    xs, ys = [p[0] for p in rings[0]], [p[1] for p in rings[0]]
    k = math.cos(math.radians((min(ys) + max(ys)) / 2))
    best = (-1.0, (sum(xs) / len(xs), sum(ys) / len(ys)))
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    for _ in range(2):
        n = 24
        for i in range(n + 1):
            for j in range(n + 1):
                x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n
                if _inside(x, y, rings):
                    d = _edge_distance(x, y, rings, k)
                    if d > best[0]:
                        best = (d, (x, y))
        cx, cy = best[1]
        wx, wy = (x1 - x0) / n * 1.5, (y1 - y0) / n * 1.5
        x0, x1, y0, y1 = cx - wx, cx + wx, cy - wy, cy + wy
    return round(best[1][0], 2), round(best[1][1], 2)


def bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def box_gap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Distance in degrees between two boxes (0 when they overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


# ----- build ---------------------------------------------------------------------------------------


def build(world_atlas: Path, iso: Path) -> dict[str, Any]:
    """The map document from the extracted packages."""
    topology = json.loads((world_atlas / "countries-110m.json").read_text(encoding="utf-8"))
    codes = {num: (a2, a3) for a2, a3, num, *_ in json.loads((iso / "codes.json").read_text(encoding="utf-8"))}
    english = json.loads((iso / "langs" / "en.json").read_text(encoding="utf-8"))["countries"]
    arcs = decode_arcs(topology)
    countries = []
    for geometry in topology["objects"]["countries"]["geometries"]:
        ne_name = geometry["properties"]["name"]
        if geometry.get("id") is not None:
            a2, a3 = codes[geometry["id"]]
        else:
            a2, a3 = NO_ISO[ne_name]
        polys = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]]
        polygons, raw = [], []
        for poly in polys:
            for rings in split_at_antimeridian([ring(r, arcs) for r in poly]):
                flat = [quantize(r, outer=(k == 0)) for k, r in enumerate(rings)]
                if flat[0] is None:
                    continue
                polygons.append([f for f in flat if f is not None])
                raw.append([[(f[i] / 100, f[i + 1] / 100) for i in range(0, len(f), 2)] for f in flat if f is not None])
        largest = max(raw, key=lambda rs: abs(signed_area(rs[0])) * math.cos(math.radians(bbox(rs[0])[1] / 2 + bbox(rs[0])[3] / 2)))
        big = bbox(largest[0])
        main = [bbox(rs[0]) for rs in raw if box_gap(bbox(rs[0]), big) <= MAIN_REACH]
        main_box = [min(b[0] for b in main), min(b[1] for b in main), max(b[2] for b in main), max(b[3] for b in main)]
        names = english.get(a2, []) if a2 else []
        names = [names] if isinstance(names, str) else list(names)
        display = DISPLAY.get(a3, ne_name)
        aliases = list(dict.fromkeys([display, ne_name, *EXTRA_ALIASES.get(a3, []), *names]))
        countries.append({
            "a3": a3, "a2": a2, "name": display, "aliases": [a for a in aliases if a != display],
            "label": list(label_point(largest)), "main": [round(v, 2) for v in main_box], "polygons": polygons,
        })
    countries.sort(key=lambda c: c["a3"])
    on_map = {c["a2"] for c in countries}
    small = {}
    for a2, a3, *_ in json.loads((iso / "codes.json").read_text(encoding="utf-8")):
        if a2 not in on_map:
            name = english.get(a2, a2)
            small[a2] = [a3, name if isinstance(name, str) else name[0]]
    return {
        "source": {
            "data": "Natural Earth 1:110m Cultural Vectors, Admin 0 - Countries (public domain), naturalearthdata.com",
            "via": f"npm {WORLD_ATLAS[0]} {WORLD_ATLAS[1]} (countries-110m.json, ISC); codes and English names from npm {ISO[0]} {ISO[1]} (MIT)",
            "units": "rings of integer hundredths of a degree [lon0, lat0, lon1, lat1, ...]; outer rings counter-clockwise, holes clockwise",
        },
        "countries": countries,
        "small": dict(sorted(small.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--world-atlas", type=Path, help="an extracted world-atlas package/ folder")
    parser.add_argument("--iso", type=Path, help="an extracted i18n-iso-countries package/ folder")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        world_atlas = args.world_atlas or fetch_package(*WORLD_ATLAS, Path(tmp))
        iso = args.iso or fetch_package(*ISO, Path(tmp))
        doc = build(world_atlas, iso)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"{args.out}: {len(doc['countries'])} countries, {len(doc['small'])} too small for the map, {len(text) // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
