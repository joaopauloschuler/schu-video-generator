"""Placing molecules in a cell world (DESIGN.md §95.9): a membrane protein ``on:`` the cell (its
plasma membrane) or a structure sits in one of that structure's membranes — ATP synthase on a
mitochondrion's cristae (the inner membrane) or a chloroplast's thylakoids, a channel in the ER
— oriented by the catalog's rule: each place's two sides are found in the world (which
compartment lies either way), so the glyph's exoplasmic side faces the right one and ``faces:``
can be checked. Soluble molecules are scattered ``in:`` their compartments like other complexes.
No manim."""

from __future__ import annotations

import math
from dataclasses import replace

from .builder import Builder
from .catalog import BILAYER, KINDS, MEMBRANES, MITO_GAP, Kind
from .geometry import ArcBand, Capsule, Ellipse, Point, RoundedBox
from .glyphs import MoleculeSpec, check_molecule
from .model import ObjectSpec, Placed, did_you_mean, fail, noun
from .molecules import MOLECULES, check_faces, check_membrane, membrane_sides
from .morphology import cristae

#: How far either side of a membrane its two compartments are probed (µm).
PROBE = 0.008
#: Short names of a structure's membranes (``membrane: inner``).
SHORT = {"inner": ("inner_mitochondrial_membrane", "inner_envelope_membrane", "inner_nuclear_membrane", "bacterial_inner_membrane"),
         "outer": ("outer_mitochondrial_membrane", "outer_envelope_membrane", "outer_nuclear_membrane", "bacterial_outer_membrane"),
         "thylakoid": ("thylakoid_membrane",), "plasma": ("plasma_membrane", "bacterial_inner_membrane")}


def molecule_spec(spec: ObjectSpec, entry_id: str, membrane: str | None) -> MoleculeSpec:
    """The checked molecule options of an object (its state; the membrane it is in)."""
    return check_molecule(MoleculeSpec(spec.kind, state=spec.state, membrane=membrane, where=f"{spec.where or 'objects'} ({spec.kind} '{entry_id}')"))


def _membranes_of(builder: Builder, on: str | None) -> tuple[list[tuple[str, list[object]]], list[Placed]]:
    """The membranes of ``on`` (``cell``: the cell's own) with the shapes their places lie on,
    and its things."""
    if on in (None, "cell"):
        cell = builder.cell
        if builder.spec.kind == "bacterium":
            found: list[tuple[str, list[object]]] = [("bacterial_inner_membrane", [cell])]
            found += [(name, [shape]) for name, shape in builder.membranes if name == "bacterial_outer_membrane"]
            return found, []
        return [("plasma_membrane", [cell])], []
    things = builder.world().members(on)
    out: dict[str, list[object]] = {}
    for thing in things:
        kind = thing.kind
        if kind == "mitochondrion":
            outer = thing.footprint[0]
            assert isinstance(outer, Capsule)
            inner = outer.inset(MITO_GAP + BILAYER)
            folds = cristae(inner, thing.key)
            out.setdefault("outer_mitochondrial_membrane", []).append(outer)
            out.setdefault("inner_mitochondrial_membrane", []).extend(folds[1::2] or [inner])   # ATP synthase lines the cristae
        elif kind == "chloroplast":
            out.setdefault("outer_envelope_membrane", []).append(thing.footprint[0])
            out.setdefault("thylakoid_membrane", []).extend([l for l in thing.option("lamellae", ()) if l.length > 0.1] or list(thing.option("discs", ())))
        elif thing.option("sheets"):
            out.setdefault("er_membrane", []).extend(thing.option("sheets"))
        elif kind == "golgi":
            out.setdefault("golgi_membrane", []).extend(thing.option("bands", ()))
        else:
            for part in thing.parts[:1]:
                name, shape = part.membranes[0]
                out.setdefault(name, []).append(shape)
    return list(out.items()), things


def _points(shape: object, spacing: float) -> list[tuple[Point, Point]]:
    if isinstance(shape, ArcBand):
        return shape.faces(spacing)
    if isinstance(shape, (Ellipse, Capsule, RoundedBox)):
        return shape.surface(spacing, 0.5)
    return []


def place_on_membrane(builder: Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """A membrane (or peripheral) protein ``on:`` the cell or a structure, in the membrane
    ``membrane:`` names (default: the first of the structure's membranes it occurs in), its
    exoplasmic side towards that membrane's exoplasmic compartment; ``faces:`` checked."""
    mol = MOLECULES[kind.name]
    entries = {e.id: e for e in builder.entries if e.owner is None}
    if spec.on not in (None, "cell") and spec.on not in entries:
        raise fail(spec, entry_id, f"on: '{spec.on}' is not an object of this cell{did_you_mean(spec.on or '', ['cell', *entries])} "
                                   "(cell: its plasma membrane)")
    found, _things = _membranes_of(builder, spec.on)
    names = [name for name, _ in found]
    if spec.membrane is not None:
        wanted = [n for n in SHORT.get(spec.membrane, (spec.membrane,)) if n in names]
        if not wanted:
            raise fail(spec, entry_id, f"membrane '{spec.membrane}': '{spec.on or 'cell'}' has {', '.join(names) or 'no membrane'}"
                                       f"{did_you_mean(spec.membrane, names)}")
        membrane = wanted[0]
    else:
        usable = [n for n in names if n in mol.membranes]
        membrane = usable[0] if usable else names[0] if names else ""
    if not membrane:
        target = noun(KINDS[entries[spec.on].kind].label) if spec.on in entries else "this"
        raise fail(spec, entry_id, f"a {target} has no membrane to sit in")
    where = f"{spec.where or 'objects'} ({mol.plain} '{entry_id}')"
    check_membrane(mol, membrane, where)
    check_faces(mol, membrane, spec.faces, where)
    exo, cyto = membrane_sides(membrane)
    shapes = dict(found)[membrane]
    size = spec.size or kind.size
    world = builder.world()
    candidates: list[tuple[Point, Point]] = []
    for shape in shapes:
        for p, n in _points(shape, size * 1.4):
            outside = world.compartment_at((p[0] + n[0] * PROBE, p[1] + n[1] * PROBE))[0]
            inside = world.compartment_at((p[0] - n[0] * PROBE, p[1] - n[1] * PROBE))[0]
            if {outside, inside} != {exo, cyto}:
                continue                       # a junction, a pore, a place another structure covers
            n_exo = n if outside == exo else (-n[0], -n[1])
            candidates.append((p, n_exo))
    rng = builder.rng(entry_id, "membrane")
    rng.shuffle(candidates)
    taken = [p.center for p in builder.placed if p.option("membrane") is not None]
    chosen: list[tuple[Point, Point]] = []
    for p, n in candidates:
        if len(chosen) == spec.count:
            break
        if all(math.dist(p, q) > size * 1.2 for q in taken + [c for c, _ in chosen]):
            chosen.append((p, n))
    if len(chosen) < spec.count:
        raise fail(spec, entry_id, f"only {len(chosen)} free places in the {MEMBRANES[membrane].label.lower()} for {spec.count}; use a smaller count")
    mspec = molecule_spec(spec, entry_id, membrane)
    things = []
    host = spec.on if spec.on not in (None, "cell") else None
    for k, (p, n) in enumerate(sorted(chosen)):
        key = f"{entry_id}#{k + 1}" if spec.count > 1 else entry_id
        angle = math.atan2(n[1], n[0]) - math.pi / 2           # the glyph's +y (exoplasmic side) along n
        instance = world.compartment_at((p[0] - n[0] * PROBE, p[1] - n[1] * PROBE))[1]
        things.append(Placed(key, entry_id, kind.name, p, size, size, angle, (Ellipse(p[0], p[1], size / 2, size / 2),), (), instance,
                             surface=host, normal=n, options=(("molecule", mspec), ("membrane", membrane))))
    return things


def with_molecule(things: list[Placed], spec: ObjectSpec, entry_id: str) -> list[Placed]:
    """Soluble molecules placed as complexes, with their checked options for the drawing."""
    mspec = molecule_spec(spec, entry_id, None)
    return [replace(t, options=(*t.options, ("molecule", mspec))) for t in things]


__all__ = ["molecule_spec", "place_on_membrane", "with_molecule"]
