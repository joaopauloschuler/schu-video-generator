"""What to name in a zoomed view (DESIGN.md §95.9): the parts of a structure seen at the
organelle or the complex level — a mitochondrion's outer and inner membrane, cristae, matrix and
intermembrane space; a nuclear pore with the two nuclear membranes and the perinuclear space; a
bilayer's phospholipids, cholesterol and glycolipids — each with the point its label points at.
The scene labels a ``zoom_to`` view with these. No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .bilayer import lipid_layout, lipids_of, mosaic, plasma_rafts
from .catalog import BILAYER, COAT_LABELS, COATS, COMPARTMENTS, CHLOROPLAST_GAP, KINDS, MEMBRANES, MITO_GAP, PERINUCLEAR_GAP, PERIPLASM
from .curves import shape_curves
from .geometry import ArcBand, Capsule, Ellipse, Point, Polyline
from .glyphs import anchor_point, molecule_glyph
from .model import CellWorld, Placed
from .molecules import MOLECULES, membrane_sides
from .morphology import cristae, heterochromatin, nucleolus_parts
from .view import CellView, membrane_focus


@dataclass(frozen=True)
class Anchor:
    """A part to name: ``name`` (what ``labels: [...]`` of ``zoom_to`` lists), its ``label`` and
    the world ``point`` (µm) the label points at."""

    name: str
    label: str
    point: Point


def _toward(p: Point, q: Point, d: float) -> Point:
    length = math.dist(p, q) or 1.0
    return (p[0] + (q[0] - p[0]) / length * d, p[1] + (q[1] - p[1]) / length * d)


def _off(p: Point, n: Point, d: float) -> Point:
    return (p[0] + n[0] * d, p[1] + n[1] * d)


def _nearest(points: list[Point], center: Point) -> Point | None:
    return min(points, key=lambda q: math.dist(q, center)) if points else None


def _settle(world: CellWorld, p: Point, compartment: str, margin: float = 0.008, reach: float = 0.2) -> Point:
    """The point nearest ``p`` that lies in ``compartment`` at least ``margin`` µm from any
    other (a label points well inside the space it names, not at its edge); ``p`` itself when
    none is found within ``reach``."""

    def clear(q: Point) -> bool:
        if world.compartment_at(q)[0] != compartment:
            return False
        return all(world.compartment_at((q[0] + margin * math.cos(a * math.pi / 4), q[1] + margin * math.sin(a * math.pi / 4)))[0] == compartment
                   for a in range(8))

    if clear(p):
        return p
    step = margin / 2
    for ring in range(1, int(reach / step) + 1):
        r = ring * step
        count = max(8, int(2 * math.pi * r / step))
        for k in range(count):
            q = (p[0] + r * math.cos(2 * math.pi * k / count), p[1] + r * math.sin(2 * math.pi * k / count))
            if clear(q):
                return q
    return p


def _beside(p: Point, n: Point, depth: float, sideways: float, axis: int) -> Point:
    """A point ``depth`` µm from ``p`` along the normal ``n`` and ``sideways`` µm along the
    membrane, the way that keeps it on its side of ``p`` along ``axis`` (0: x, 1: y) — so its
    label, laid out on that side of the view, does not reach across the membrane to it."""
    t = (-n[1], n[0])
    best = None
    for sign in (1.0, -1.0):
        q = (p[0] + n[0] * depth + t[0] * sideways * sign, p[1] + n[1] * depth + t[1] * sideways * sign)
        score = (q[axis] - p[axis]) * (1.0 if n[axis] * depth >= 0 else -1.0)
        if best is None or score > best[0]:
            best = (score, q)
    assert best is not None
    return best[1]


def _ellipse_t(shape: Ellipse, point: Point) -> float:
    x, y = shape.local(point)
    return (math.atan2(y / shape.b, x / shape.a) / (2 * math.pi)) % 1.0


def part_anchors(world: CellWorld, entry_id: str | None, view: CellView, half: tuple[float, float]) -> list[Anchor]:
    """The parts worth naming in ``view`` (looking at ``entry_id``; ``None`` or ``cell``: the
    cell itself) whose points lie inside the view's ``half`` width and height (µm), nearest the
    middle first."""
    center = view.center
    if entry_id in (None, "cell", "tissue"):
        # labels go to the view's left and right in a wide frame, above and below in a tall one
        found = _cell_parts(world, view, 0 if half[0] >= half[1] else 1) if view.level == "complex" else []
        if view.level == "organelle":
            nucleus = next((e.id for e in world.entries if e.kind in ("nucleus", "nucleoid") and e.owner is None), None)
            found = _parts(world, world.members(nucleus)[0], view) if nucleus else []
    else:
        things = world.members(entry_id)
        thing = min(things, key=lambda t: math.dist(t.center, center)) if len(things) > 1 else things[0]
        found = _parts(world, thing, view)
    seen: set[str] = set()
    out = []
    for anchor in found:
        if anchor.name in seen:
            continue
        x, y = anchor.point
        if abs(x - center[0]) <= half[0] * 0.92 and abs(y - center[1]) <= half[1] * 0.92:
            seen.add(anchor.name)
            out.append(anchor)
    return out[:7]


def _surface(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    """A structure drawn whole, seen close: a nuclear pore complex from above, else its outer
    membrane's lipids face on."""
    c = view.center
    info = KINDS[thing.kind]
    if thing.kind == "nucleus":
        return [Anchor("pore", "Nuclear pore complex (from above)", _off(c, (0.0, 1.0), 0.04)),
                Anchor("channel", "Central channel", c),
                Anchor("envelope", "Outer nuclear membrane", _off(c, (0.7071, -0.7071), 0.085))]
    if not info.membranes:
        return [Anchor(thing.kind, info.label, c)]
    membrane = info.membranes[0]
    shape = thing.footprint[0]
    found = mosaic(c, 0.012, shape.contains, lipids_of(world, membrane), "cyto", thing.key)
    out = [Anchor("membrane", f"{MEMBRANES[membrane].label}, face on", _off(c, (0.0, -1.0), 0.016))]
    names = {"phospholipid": "Phospholipid head groups", "sterol": "Sterol (cholesterol)" if world.kind == "animal" else "Sterol",
             "galactolipid": "Galactolipids"}
    for kind, label in names.items():
        p = _nearest([q for k, q in found if k == kind], c)
        if p is not None:
            out.append(Anchor(kind, label, p))
    return out


def _parts(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    level, c = view.level, view.center
    kind = thing.kind
    shape = thing.footprint[0]
    if level == "complex" and thing.option("style") == "surface":
        return _surface(world, thing, view)
    if kind == "nucleus" and isinstance(shape, Ellipse):
        return _nucleus(world, thing, shape, view)
    if kind == "mitochondrion" and isinstance(shape, Capsule):
        inner = shape.inset(MITO_GAP + BILAYER)
        folds = cristae(inner, thing.key)
        pick = min(range(0, len(folds), 2), key=lambda i: math.dist(folds[i].center(), c)) if folds else None
        neck = folds[pick] if pick is not None else None
        lamella = folds[pick + 1] if pick is not None else None
        p = shape.point(0.08)
        n = shape.normal(0.08)
        out = []
        if level == "complex" and neck is not None:
            out.append(Anchor("crista_junction", "Crista junction", neck.center()))
            if lamella is not None:
                # the intracristal space: inside the crista's lumen, past its junction
                q = _toward(neck.center(), lamella.center(), 0.11)
                out.append(Anchor("intracristal_space", "Intracristal space", q if lamella.contains(q, -0.004) else lamella.center()))
            q = _nearest(_on_capsule(shape, c), c) or p
            out += [Anchor("outer_membrane", "Outer membrane", q),
                    Anchor("intermembrane_space", "Intermembrane space", _toward(q, thing.center, (MITO_GAP + BILAYER) / 2)),
                    # the matrix lies round the cristae, inside the inner membrane: beside this crista, not in it
                    Anchor("matrix", "Matrix", _settle(world, _toward(neck.center(), thing.center, 0.07), "matrix", 0.012, 0.12))]
            return out
        # a stretch of the boundary membranes with no crista junction in it
        t = next((u for u in (0.08, 0.1, 0.06, 0.12, 0.04, 0.14, 0.02, 0.16) if not any(f.contains(shape.point(u), MITO_GAP * 2.5) for f in folds)), 0.08)
        p, n = shape.point(t), shape.normal(t)
        out += [Anchor("outer_membrane", "Outer membrane", p),
                Anchor("inner_membrane", "Inner membrane", _off(p, n, -(MITO_GAP + BILAYER))),
                Anchor("intermembrane_space", "Intermembrane space", _off(p, n, -(MITO_GAP + BILAYER) / 2))]
        if lamella is not None:
            out.append(Anchor("crista", "Crista", lamella.center()))
        out.append(Anchor("matrix", "Matrix", _toward(thing.center, shape.point(0.5), 0.12)))
        return out
    if kind == "rough_er":
        return _rough_er(world, thing, view)
    if kind == "smooth_er":
        nodes = thing.option("nodes", ())
        node = _nearest(list(nodes), c)
        out = [Anchor("tubule", "Smooth ER tubule", _nearest([s.center() for s in thing.footprint], c) or thing.center)]
        if node is not None:
            out.append(Anchor("junction", "Three-way junction", node))
        if thing.joined:
            out.append(Anchor("rough_er", "Joined to the rough ER", thing.footprint[-1].center()))
        if level == "complex":
            out += [Anchor("membrane", "ER membrane", _off(node or c, (0.0, 1.0), 0.025)), Anchor("lumen", "ER lumen", node or c)]
        return out
    if kind == "golgi":
        return _golgi(world, thing, view)
    if kind in ("lysosome", "peroxisome", "endosome", "early_endosome", "late_endosome", "vesicle", "vacuole"):
        return _single(world, thing, view)
    if kind == "centrosome":
        from .morphology import centrioles

        mother, tip = centrioles(thing.center, thing.angle)
        return [Anchor("daughter", "Daughter centriole" if level == "organelle" else "Microtubule triplets (9)", tip),
                Anchor("mother", "Mother centriole", mother.center()),
                Anchor("pcm", "Pericentriolar material", _off(thing.center, (0.0, -1.0), thing.size * 0.38))]
    if kind == "nucleolus" and isinstance(shape, Ellipse):
        centres, rims = nucleolus_parts(shape, thing.key)
        out = [Anchor("nucleolus", "Nucleolus", thing.center)]
        if centres:
            fc = min(centres, key=lambda e: math.dist(e.center(), c))
            out = [Anchor("fibrillar_centre", "Fibrillar centre", fc.center()),
                   Anchor("dense_fibrillar", "Dense fibrillar component", _off(fc.center(), (1.0, 0.0), fc.a + 0.022)),
                   Anchor("granular", "Granular component", _toward(thing.center, shape.point(0.3), shape.a * 0.75))]
        return out
    if kind == "chloroplast" and isinstance(shape, Ellipse):
        return _chloroplast(thing, shape, view)
    if kind == "nucleoid":
        out = [Anchor("nucleoid", "Nucleoid (chromosome)", thing.center)]
        ribosomes = [p.center for p in world.placed if p.kind == "ribosome" and p.surface is None]
        r = _nearest(ribosomes, _off(thing.center, (0.0, 1.0), thing.width * 0.7))
        if r is not None:
            out.append(Anchor("ribosome", "Ribosome (70S)", r))
        plasmid = _nearest([p.center for p in world.placed if p.kind == "plasmid"], thing.center)
        if plasmid is not None:
            out.append(Anchor("plasmid", "Plasmid", plasmid))
        return out
    if kind in MOLECULES and thing.option("molecule") is not None:
        glyph = molecule_glyph(thing.option("molecule"))
        out = [Anchor(name, label, anchor_point(glyph, name, thing.center, thing.angle, 0.001)) for name, (label, _p) in glyph.anchors.items()]
        membrane = thing.option("membrane")
        if membrane:
            exo, cyto = membrane_sides(membrane)
            n = thing.normal or (0.0, 1.0)
            step = min(thing.size * 0.4, 0.008)                # inside a crista's 25 nm lumen too
            sides = [Anchor(exo, COMPARTMENTS[exo].label, _settle(world, _off(thing.center, n, step), exo, 0.002, 0.03)),
                     Anchor(cyto, COMPARTMENTS[cyto].label, _settle(world, _off(thing.center, n, -step), cyto, 0.002, 0.03))]
            out = out[:4] + sides + out[4:]                    # a view names at most seven: the two sides among them
        return out
    info = KINDS[kind]
    if info.category == "filament":
        return _filament(world, thing, view)
    if info.shape == "motor":
        return _motor(world, thing)
    return [Anchor(kind, info.label, thing.center)]


def _on_capsule(shape: Capsule, near: Point) -> list[Point]:
    return [shape.point(k / 96) for k in range(96)]


def _nucleus(world: CellWorld, thing: Placed, shape: Ellipse, view: CellView) -> list[Anchor]:
    c = view.center
    inner = shape.inset(PERINUCLEAR_GAP + BILAYER)
    pores = [p for p in world.placed if p.surface == thing.key and p.kind == "nuclear_pore"]
    pore = min(pores, key=lambda p: math.dist(p.center, c)) if pores else None
    if view.level == "complex" and pore is not None:
        n = pore.normal or (1.0, 0.0)
        tangent = (-n[1], n[0])
        side = _off(pore.center, tangent, 0.17)
        t = _ellipse_t(shape, side)
        q, qn = shape.point(t), shape.normal(t)
        out = [Anchor("pore", "Nuclear pore complex", pore.center),
               Anchor("outer_nuclear_membrane", "Outer nuclear membrane", q),
               Anchor("perinuclear_space", "Perinuclear space", _off(q, qn, -(PERINUCLEAR_GAP + BILAYER) / 2)),
               Anchor("inner_nuclear_membrane", "Inner nuclear membrane", _off(q, qn, -(PERINUCLEAR_GAP + BILAYER))),
               Anchor("cytosol", "Cytosol", _off(pore.center, n, 0.12)),
               Anchor("nucleoplasm", "Nucleoplasm", _off(pore.center, n, -0.13))]
        ribosome = _nearest([p.center for p in world.placed if p.surface == thing.key and p.kind == "ribosome"], pore.center)
        if ribosome is not None:
            out.insert(1, Anchor("ribosome", "Ribosome", ribosome))
        return out
    out = [Anchor("envelope", "Nuclear envelope", shape.point(0.18))]
    if pore is not None:
        out.append(Anchor("pore", "Nuclear pores", pore.center))
    nucleolus = next((p for p in world.placed if p.kind == "nucleolus" and p.host == f"{thing.key}.nucleoplasm"), None)
    if nucleolus is not None:
        out.append(Anchor("nucleolus", "Nucleolus", nucleolus.center))
    # heterochromatin: on one of its patches along the inner membrane; the nucleoplasm clear of them
    nucleoli = [p.footprint[0] for p in world.placed if p.kind == "nucleolus" and p.host == f"{thing.key}.nucleoplasm"]
    chromatin = heterochromatin(inner, list(thing.option("pores", ())), [n for n in nucleoli if isinstance(n, Ellipse)], thing.key)
    patch = None
    for k in range(60):
        t = 0.62 + (k // 2) * 0.006 * (1 if k % 2 == 0 else -1)
        for depth in (0.07, 0.05, 0.1):
            q = _off(inner.point(t), inner.normal(t), -depth)
            if chromatin.contains(q):
                patch = q
                break
        if patch is not None:
            break
    if patch is not None:
        out.append(Anchor("heterochromatin", "Heterochromatin", patch))
    plasm = next((q for f in (0.45, 0.35, 0.55, 0.25, 0.65) for u in (0.85, 0.8, 0.9, 0.75)
                  if not chromatin.contains(q := _toward(thing.center, inner.point(u), inner.a * f)) and not any(n.contains(q, 0.1) for n in nucleoli)),
                 _toward(thing.center, inner.point(0.85), inner.a * 0.45))
    out.append(Anchor("nucleoplasm", "Nucleoplasm", plasm))
    er = next((p for p in world.placed if p.kind == "rough_er" and thing.key in p.joined), None)
    if er is not None:
        necks = er.option("necks", ())
        if necks:
            out.append(Anchor("er_junction", "ER joins the envelope", necks[0].center()))
    return out


def _rough_er(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    c = view.center
    sheets = list(thing.option("sheets", ()))
    band = min(sheets, key=lambda b: abs(math.dist((b.cx, b.cy), c) - b.radius)) if sheets else None
    ribosomes = [p for p in world.placed if p.surface == thing.key and p.kind == "ribosome"]
    ribosome = min(ribosomes, key=lambda p: math.dist(p.center, c)) if ribosomes else None
    out: list[Anchor] = []
    if view.level == "complex" and ribosome is not None and band is not None:
        n = ribosome.normal or (0.0, 1.0)
        out += [Anchor("ribosome", "Ribosome", ribosome.center),
                Anchor("large_subunit", "Large subunit (60S)", _off(ribosome.center, n, -0.004)),
                Anchor("small_subunit", "Small subunit (40S)", _off(ribosome.center, n, 0.009)),
                Anchor("membrane", "ER membrane", _off(_off(ribosome.center, (-n[1], n[0]), 0.035), n, -(ribosome.size / 2 + BILAYER / 2))),
                Anchor("lumen", "ER lumen", _off(ribosome.center, n, -(ribosome.size / 2 + band.thickness / 2))),
                Anchor("cytosol", "Cytosol", _off(_off(ribosome.center, (-n[1], n[0]), -0.04), n, 0.02))]
        return out
    if band is not None:
        angle = math.atan2(c[1] - band.cy, c[0] - band.cx)
        p = (band.cx + band.radius * math.cos(angle), band.cy + band.radius * math.sin(angle))
        out.append(Anchor("sheet", "Rough ER sheet", p))
        out.append(Anchor("lumen", "ER lumen", _off(p, (math.cos(angle), math.sin(angle)), 0.0)))
    if ribosome is not None:
        out.append(Anchor("ribosomes", "Ribosomes", ribosome.center))
    necks = list(thing.option("necks", ()))
    if necks:
        idx = min(range(len(necks)), key=lambda i: math.dist(necks[i].center(), c))
        out.append(Anchor("junction", "Joined to the nuclear envelope" if idx < 2 else "Sheets joined", necks[idx].center()))
    buds = thing.option("buds", ())
    if buds:
        out.append(Anchor("exit_site", "ER exit site (COPII)", _nearest([b[0] for b in buds], c) or buds[0][0]))
    return out


def _golgi(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    c = view.center
    bands: list[ArcBand] = list(thing.option("bands", ()))
    buds = list(thing.option("buds", ()))
    out: list[Anchor] = []
    if view.level == "complex" and buds:
        center, radius, coat, k = min(buds, key=lambda b: math.dist(b[0], c))
        names = ["cis", *["medial"] * (len(bands) - 2), "trans"]
        band = bands[k]
        end = min(band.ends(), key=lambda e: math.dist(e, center))
        away = (center[0] - end[0], center[1] - end[1])
        length = math.hypot(*away) or 1.0
        away = (away[0] / length, away[1] / length)          # the coat is on the bud's free side, away from its cisterna
        # along the cisterna, back from the rim the bud grows from: its lumen and a membrane
        a_end = band.end if math.dist(end, band.ends()[-1]) < math.dist(end, band.ends()[0]) else band.start
        inward = 1.0 if a_end == band.start else -1.0

        def on_band(arc: float, r: float) -> Point:
            a = a_end + inward * arc / band.radius
            return (band.cx + r * math.cos(a), band.cy + r * math.sin(a))

        lumen = _settle(world, on_band(0.1, band.radius), f"{names[k]}_golgi_lumen", 0.004, 0.06)
        out += [Anchor("coat", f"{COAT_LABELS[coat]} coat", _off(center, away, radius + BILAYER / 2 + COATS[coat] / 2)),
                Anchor("bud", "Budding vesicle", center),
                Anchor("membrane", "Golgi membrane", on_band(0.16, band.radius + band.thickness / 2)),
                Anchor("lumen", f"{names[k]}-Golgi lumen", lumen)]
        return out
    if bands:
        out += [Anchor("cis", "cis face", bands[0].center()), Anchor("medial", "Medial cisternae", bands[len(bands) // 2].center()),
                Anchor("trans", "trans face", bands[-1].center())]
    vesicles = [p for p in world.placed if p.entry == f"{thing.key}.vesicles"]
    for coat, label in (("copi", "COPI vesicle"), ("clathrin", "Clathrin-coated vesicle"), (None, "Secretory vesicle")):
        mine = [v.center for v in vesicles if v.option("coat") == coat]
        p = _nearest(mine, c)
        if p is not None:
            out.append(Anchor(coat or "secretory", label, p))
    return out


def _single(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    shape = thing.footprint[0]
    kind = thing.kind
    outline = thing.parts[0].membranes[0][1] if thing.parts and thing.kind == "vesicle" else shape
    p = outline.point(0.1) if hasattr(outline, "point") else thing.center  # type: ignore[attr-defined]
    names = {"lysosome": ("Lysosomal membrane", "Lumen (pH 4.5–5, hydrolases)"), "peroxisome": ("Peroxisomal membrane", "Matrix (oxidases, catalase)"),
             "endosome": ("Endosomal membrane", "Lumen"), "early_endosome": ("Endosomal membrane", "Vacuolar part"),
             "late_endosome": ("Limiting membrane", "Lumen"), "vesicle": ("Vesicle membrane", "Lumen (cargo)"),
             "vacuole": ("Tonoplast", "Cell sap")}
    membrane, lumen = names[kind]
    out = [Anchor("membrane", membrane, p), Anchor("lumen", lumen, _toward(thing.center, p, min(thing.size, thing.width) * 0.12))]
    if kind == "late_endosome":
        ilvs = [part.membranes[0][1].center() for part in thing.parts[1:]]
        q = _nearest(ilvs, view.center)
        if q is not None:
            out.insert(0, Anchor("ilv", "Intraluminal vesicles", q))
    if kind == "early_endosome" and len(thing.footprint) > 1:
        out.insert(0, Anchor("tubule", "Tubules (recycling)", thing.footprint[1].center()))
    coat = thing.option("coat")
    if coat:
        out.insert(0, Anchor("coat", f"{COAT_LABELS[coat]} coat", shape.point(0.6)))  # type: ignore[attr-defined]
    if view.level == "complex":
        n = (p[0] - thing.center[0], p[1] - thing.center[1])
        length = math.hypot(*n) or 1.0
        out.append(Anchor("cytosol", "Cytosol", _off(p, (n[0] / length, n[1] / length), 0.04)))
    return out


def _chloroplast(thing: Placed, shape: Ellipse, view: CellView) -> list[Anchor]:
    c = view.center
    discs = list(thing.option("discs", ()))
    lamellae = list(thing.option("lamellae", ()))
    inner = shape.inset(CHLOROPLAST_GAP + BILAYER)
    disc = min(discs, key=lambda d: math.dist(d.center(), c)) if discs else None
    if view.level == "complex" and disc is not None:
        across = (-math.sin(disc.angle), math.cos(disc.angle))
        return [Anchor("thylakoid_membrane", "Thylakoid membrane", _off(disc.center(), across, disc.width / 2)),
                Anchor("thylakoid_lumen", "Thylakoid lumen", _off(disc.center(), (math.cos(disc.angle), math.sin(disc.angle)), disc.length * 0.2)),
                Anchor("granum", "Granum (stacked thylakoids)", _off(disc.center(), across, 0.04)),
                # above the stack, aside from the lamellae leaving its middle and its ends
                Anchor("stroma", "Stroma", _off(_off(disc.center(), across, 0.09), (math.cos(disc.angle), math.sin(disc.angle)), -disc.length * 0.3))]
    p = shape.point(0.22)
    n = shape.normal(0.22)
    out = [Anchor("outer_envelope", "Outer envelope membrane", p),
           Anchor("inner_envelope", "Inner envelope membrane", _off(p, n, -(CHLOROPLAST_GAP + BILAYER)))]
    if disc is not None:
        out.append(Anchor("granum", "Granum", disc.center()))
    lamella = _nearest([l.center() for l in lamellae if l.length > 0.1], c)   # a run across the stroma, not a stub at a granum
    if lamella is not None:
        out.append(Anchor("stroma_lamella", "Stroma lamella", lamella))
    starch = thing.option("starch", ())
    if starch:
        out.append(Anchor("starch", "Starch grain", starch[0].center()))
    out.append(Anchor("stroma", "Stroma", _toward(inner.point(0.75), thing.center, 0.25)))
    return out


def _filament(world: CellWorld, thing: Placed, view: CellView) -> list[Anchor]:
    line = thing.footprint[0]
    assert isinstance(line, Polyline)
    kind = thing.kind
    c = view.center
    if view.level == "complex":
        motors = [p for p in world.placed if p.surface in {t.key for t in world.members(thing.entry)}]
        if motors:
            motor = min(motors, key=lambda m: math.dist(m.center, c))
            return _motor(world, motor)
    if kind == "microtubule":
        if view.level == "complex":
            s = line.length / 2
            p, (dx, dy) = line.at(s)
            return [Anchor("alpha", "α-tubulin", _off(p, (-dy, dx), line.width / 2)),
                    Anchor("beta", "β-tubulin", _off(_off(p, (dx, dy), 0.004), (-dy, dx), line.width / 2)),
                    Anchor("lumen", "Lumen (15 nm)", p), Anchor("plus", "Towards the + end →", _off(p, (dx, dy), 0.03))]
        out = [Anchor("microtubule", "Microtubule", line.at(min(1.4, line.length * 0.6))[0]),
               Anchor("minus_end", "− end (at the centrosome)", line.points[0]), Anchor("plus_end", "+ end", line.points[-1])]
        centrosome = next((p for p in world.placed if p.kind == "centrosome"), None)
        if centrosome is not None:
            out.append(Anchor("centrosome", "Centrosome", centrosome.center))
        return out
    if kind == "flagellum":
        base = thing.option("base", line.points[0])
        normal = thing.option("normal", (1.0, 0.0))
        if view.level == "complex":
            return [Anchor("basal_body", "Basal body (rotary motor)", _off(base, normal, -PERIPLASM / 2)),
                    Anchor("hook", "Hook", _off(base, normal, 0.05)), Anchor("filament", "Filament (flagellin)", _off(base, normal, 0.12))]
        return [Anchor("filament", "Flagellum", line.at(min(1.2, line.length / 2))[0]), Anchor("basal_body", "Basal body", base)]
    if kind == "stress_fiber":
        return [Anchor("fiber", "Stress fiber (actin + myosin II)", line.at(line.length * 0.3)[0]),
                Anchor("adhesion", "Focal adhesion", line.points[0])]
    if kind == "actin_cortex":
        return [Anchor("cortex", "Actin cortex", thing.footprint[0].center()), Anchor("membrane", "Plasma membrane", world.cell.point(0.0))]  # type: ignore[attr-defined]
    label = KINDS[kind].label
    return [Anchor(kind, label, line.at(line.length / 2)[0])]


def _motor(world: CellWorld, thing: Placed) -> list[Anchor]:
    kind = KINDS[thing.kind]
    facing = thing.facing or 0.0
    d = (math.cos(facing), math.sin(facing))
    base = thing.option("base", thing.center)
    track = "Microtubule" if thing.kind != "myosin" else "Actin filament"
    end = "+ end" if thing.kind != "dynein" else "− end"
    out = [Anchor("motor", kind.label, thing.center), Anchor("track", track, _off(base, d, -thing.size * 0.9)),
           Anchor("direction", f"Walks to the {end}", _off(_off(base, d, 0.037 if thing.kind == "myosin" else 0.023), thing.normal or (0.0, 1.0),
                                                           thing.option("filament_width", 0.025) / 2 + 0.008))]
    if thing.option("cargo"):
        n = thing.normal or (0.0, 1.0)
        out.append(Anchor("cargo", "Cargo vesicle", _off(thing.center, n, thing.size * 0.9)))
    return out


def _cell_parts(world: CellWorld, view: CellView, axis: int = 0) -> list[Anchor]:
    """The cell's own envelope seen close: a bilayer's lipids, a plant's wall and plasmodesma, a
    bacterium's layers."""
    focus, _ = membrane_focus(world)
    if world.kind == "plant":
        channel = world.channels[len(world.channels) // 2] if world.channels else None
        if not isinstance(channel, Capsule):
            return [Anchor("wall", "Cell wall", world.cell.point(0.0))]  # type: ignore[attr-defined]
        q = channel.center()                       # on the middle lamella; this cell lies towards -n
        n = (math.cos(channel.angle), math.sin(channel.angle))
        across = (-n[1], n[0])
        wall = channel.length / 2
        return [Anchor("plasmodesma", "Plasmodesma", _off(q, n, -wall * 0.5)),
                Anchor("desmotubule", "Desmotubule (ER)", _off(q, n, wall * 0.45)),
                Anchor("middle_lamella", "Middle lamella", _off(q, across, 0.14)),
                Anchor("wall", "Cell wall", _off(_off(q, across, -0.16), n, -wall * 0.5)),
                Anchor("membrane", "Plasma membrane", _off(_off(q, across, 0.2), n, -wall)),
                Anchor("cytosol", "Cytosol", _off(_off(q, across, -0.1), n, -wall - 0.1))]
    if world.kind == "bacterium":
        x, y = world.cell.point(0.5)  # type: ignore[attr-defined]
        d = view.span * 0.3                  # spread along the envelope, inside the view's short side
        out = []
        layers = dict(world.envelope)
        if world.gram == "negative":
            out += [Anchor("outer_membrane", "Outer membrane (LPS outside)", (x + d * 0.3, y + PERIPLASM)),
                    Anchor("peptidoglycan", "Peptidoglycan", (x - d * 0.5, y + PERIPLASM * 0.62)),
                    Anchor("periplasm", "Periplasm", (x + d, y + PERIPLASM * 0.3)),
                    Anchor("inner_membrane", "Inner (plasma) membrane", (x - d, y))]
        else:
            wall = layers.get("cell_wall")
            depth = wall.bounds()[3] - world.cell.bounds()[3] if wall is not None else 0.04
            out += [Anchor("wall", "Cell wall (peptidoglycan)", (x + d * 0.3, y + depth / 2)), Anchor("membrane", "Plasma membrane", (x - d, y))]
        if "capsule" in layers:
            top = layers["capsule"].bounds()[3]
            out.append(Anchor("capsule", "Capsule", (x, min((top + y) / 2 + 0.06, view.center[1] + view.span * 0.45))))
        out.append(Anchor("cytoplasm", "Cytoplasm", (x + d * 0.2, max(y - 0.05, view.center[1] - view.span * 0.45))))
        return out
    lipids = lipid_layout(world, shape_curves(world.cell), focus, 0.06, "plasma", plasma_rafts(world))
    out = []
    for kind, label in (("phospholipid", "Phospholipid"), ("sterol", "Cholesterol"), ("glycolipid", "Glycolipid")):
        mine = [l for l in lipids if l.kind == kind and (not l.raft or kind != "phospholipid")]
        if mine:
            near = min(mine, key=lambda l: math.dist(l.head, focus) + (0.03 if l.raft and kind == "phospholipid" else 0.0))
            out.append(Anchor(kind, label, near.head))
    n = world.cell.normal(0.12)  # type: ignore[attr-defined]   # the focus is the plasma membrane's point at 0.12
    # the glycocalyx: the sugar chains reach about 3–8 nm out from the bilayer's mid-plane
    out += [Anchor("raft", "Lipid raft", _off(focus, n, -0.001)), Anchor("glycocalyx", "Glycocalyx", _beside(focus, n, 0.0055, 0.012, axis)),
            Anchor("extracellular", "Extracellular space", _beside(focus, n, 0.018, 0.01, axis)),
            Anchor("cytosol", "Cytosol", _beside(focus, n, -0.014, 0.01, axis))]
    return out


__all__ = ["Anchor", "part_anchors"]
