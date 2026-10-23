"""Building a cell world from its spec and the location rules (DESIGN.md §95.4):
:func:`build_cell_world` places every entry (written ``at``, the typical layout of its kind of
cell, else scattered by ``seed``), generates what belongs to a structure (nuclear pores,
ribosomes on the rough ER and the outer nuclear membrane, vesicles at the Golgi and at ER exit
sites) and refuses what cannot be with a :class:`VidgenError` naming the object, what is wrong
and what to write. No manim."""

from __future__ import annotations

import math
from dataclasses import replace

from vidgen.errors import VidgenError

from .builder import Builder, bacterium_defaults, neighbours, nucleoid_size, plant_defaults, ribosome_density, vacuole_size
from .catalog import CELL_KINDS, CELL_LABELS, CELL_SIZES, COAT_NAMES, COMPARTMENTS, KIND_OPTIONS, KINDS, TYPICAL, Kind, main_interior
from .filaments import place_filaments, place_motors
from .geometry import Ellipse, Point
from .model import RESERVED_IDS, CellSpec, CellWorld, ObjectSpec, Placed, at_text, did_you_mean, fail, instance_words, noun
from .units import format_length

#: The order kinds are placed in when nothing else decides: what others are placed by first.
_PLACE_ORDER = {"vacuole": -1, "nucleoid": 0, "nucleus": 0, "golgi": 1, "centrosome": 2, "nucleolus": 3, "rough_er": 4, "smooth_er": 5,
                "chloroplast": 6}
#: Objects of the typical plant cell that differ from the kind's defaults.
_PLANT_TYPICAL = {"nucleus": {"size": 5.6, "width": 4.4}, "rough_er": {"sheets": 3, "span": 170.0}, "golgi": {"size": 1.2},
                  "smooth_er": {"size": 2.2}, "mitochondria": {"size": 1.5, "width": 0.6}}


def _typical(spec: CellSpec, ids: set[str]) -> list[tuple[str, ObjectSpec]]:
    out = []
    for entry_id, kind, count in TYPICAL[spec.kind]:
        if entry_id in ids:
            continue
        extra = _PLANT_TYPICAL.get(entry_id, {}) if spec.kind == "plant" else {}
        out.append((entry_id, ObjectSpec(kind, count=count, where="contents: typical", **extra)))  # type: ignore[arg-type]
    return out


def _entries(spec: CellSpec) -> list[tuple[str, ObjectSpec]]:
    """The entries with their ids: the typical contents (unless ``contents: none``), each
    replaced by an object of the same id, then the other objects in order."""
    if spec.kind not in CELL_KINDS:
        raise VidgenError(f"cell kind '{spec.kind}': use {', '.join(CELL_KINDS)}{did_you_mean(spec.kind, CELL_KINDS)}")
    given: list[tuple[str, ObjectSpec]] = []
    counts: dict[str, int] = {}
    for obj in spec.objects:
        if obj.kind not in KINDS:
            raise VidgenError(f"{obj.where or 'objects'}: unknown kind '{obj.kind}'{did_you_mean(obj.kind, list(KINDS))} "
                              f"(kinds: {', '.join(KINDS)})")
        if obj.id is not None:
            entry_id = obj.id
        else:
            counts[obj.kind] = counts.get(obj.kind, 0) + 1
            entry_id = obj.kind if counts[obj.kind] == 1 else f"{obj.kind}_{counts[obj.kind]}"
        if entry_id in RESERVED_IDS:
            raise VidgenError(f"{obj.where or 'objects'}: id '{entry_id}' is reserved ({', '.join(sorted(RESERVED_IDS))}); choose another")
        if "." in entry_id or "#" in entry_id:
            raise VidgenError(f"{obj.where or 'objects'}: id '{entry_id}': use letters, digits, '_' and '-' (no '.' or '#')")
        if any(entry_id == other for other, _ in given):
            raise VidgenError(f"{obj.where or 'objects'}: two objects have the id '{entry_id}'; give one another id")
        given.append((entry_id, obj))
    ids = {entry_id for entry_id, _ in given}
    typical = _typical(spec, ids) if spec.contents == "typical" else []
    return typical + given


def _check_static(entry_id: str, spec: ObjectSpec, cell_kind: str) -> None:
    kind = KINDS[spec.kind]
    if cell_kind not in kind.cells:
        raise fail(spec, entry_id, f"a {noun(kind.label)} cannot be in {_a_cell(cell_kind)}: {kind.cells_why}")
    if spec.count < 1:
        raise fail(spec, entry_id, "count must be at least 1")
    if spec.at is not None and spec.count > 1:
        raise fail(spec, entry_id, f"at places one thing; for {spec.count} of them leave out at (they are scattered) or write one object per place")
    if spec.inside is not None and spec.on is not None:
        raise fail(spec, entry_id, "give in (a compartment it floats in) or on (a structure whose membrane it sits on), not both")
    if spec.on is not None and not kind.surfaces:
        raise fail(spec, entry_id, f"a {noun(kind.label)} does not sit on a membrane or a filament; {kind.why}")
    if spec.inside is not None and kind.category != "complex":
        raise fail(spec, entry_id, "in is for complexes (ribosomes, proteasomes); place a structure with at, or leave at out to scatter it")
    if kind.shape == "motor" and spec.inside is not None:
        raise fail(spec, entry_id, f"a {noun(kind.label)} walks on a filament: give on: <a filament object>, not in")
    if spec.count > 1 and kind.shape in ("sheets", "stack", "tubules", "box"):
        raise fail(spec, entry_id, f"one {kind.label} per object; write another object for a second one")
    if spec.count > 1 and kind.name == "actin_cortex":
        raise fail(spec, entry_id, "the cortex is one meshwork under the whole plasma membrane; leave out count")
    for name, kinds in KIND_OPTIONS.items():
        if getattr(spec, name) is not None and spec.kind not in kinds:
            raise fail(spec, entry_id, f"{name} is for {' and '.join(kinds)}, not a {noun(kind.label)}")
    if spec.coat is not None and spec.coat not in COAT_NAMES:
        raise fail(spec, entry_id, f"coat '{spec.coat}': use {', '.join(COAT_NAMES)}{did_you_mean(spec.coat, COAT_NAMES)}")
    if spec.size is not None and kind.category == "structure" and spec.size < 0.02:
        raise fail(spec, entry_id, f"size {format_length(spec.size)} is too small for a {noun(kind.label)}")


def _a_cell(cell_kind: str) -> str:
    label = CELL_LABELS[cell_kind].lower()
    return f"an {label}" if label[0] in "aeiou" else f"a {label}"


def _resolve_in(builder: Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[tuple[str, Placed | None]]:
    """The compartment instances ``in:`` names, after the location rule."""
    text = spec.inside or "cytosol"
    names: list[str] = ["cytosol", "extracellular", *COMPARTMENTS]
    entries = {e.id: e for e in builder.entries}
    names += [e for e in entries] + [f"{e}.{c}" for e in entries for c in KINDS[entries[e].kind].interior]
    if text in ("cytosol", "extracellular"):
        compartment, owners = text, [None]
    elif text in COMPARTMENTS:
        compartment = text
        owners = [p for p in builder.structures() if compartment in KINDS[p.kind].interior]
        if not owners:
            raise fail(spec, entry_id, f"in: {text}: nothing in this cell has a {noun(COMPARTMENTS[text].label)}")
    else:
        entry_part, _, sub = text.partition(".")
        if entry_part not in entries:
            raise fail(spec, entry_id, f"in: '{text}' is neither a compartment nor an object{did_you_mean(text, names)}")
        host_kind = KINDS[entries[entry_part].kind]
        compartment = sub or main_interior(host_kind) or ""
        if not compartment:
            hint = " (it is part of the nucleoplasm)" if host_kind.name == "nucleolus" else ""
            raise fail(spec, entry_id, f"in: '{text}': a {noun(host_kind.label)} has no inside of its own{hint}")
        if compartment not in host_kind.interior:
            raise fail(spec, entry_id, f"in: '{text}': a {noun(host_kind.label)} has {', '.join(host_kind.interior) or 'no compartments'}"
                                       f"{did_you_mean(compartment, list(host_kind.interior))}")
        owners = [builder.world().thing(k) for k in entries[entry_part].keys]
    if compartment not in kind.places:
        raise fail(spec, entry_id, f"a {noun(kind.label)} cannot be in the {noun(COMPARTMENTS[compartment].label)}: {kind.why}")
    return [(compartment, owner) for owner in owners]


def build_cell_world(spec: CellSpec) -> CellWorld:
    """Build the world of ``spec``: the cell and its envelope, every entry placed (written
    ``at``, the typical layout, else scattered by ``seed``), the generated things (nuclear pores,
    ribosomes on the rough ER and the outer nuclear membrane, vesicles at the Golgi and the ER's
    exit sites), the filaments and motors, and the tissue around. Raises :class:`VidgenError`
    naming the object and what to change when an entry breaks a location rule, overlaps
    another, does not fit, or names something unknown."""
    if spec.kind not in CELL_KINDS:
        raise VidgenError(f"cell kind '{spec.kind}': use {', '.join(CELL_KINDS)}{did_you_mean(spec.kind, CELL_KINDS)}")
    size, aspect, (lo, hi) = CELL_SIZES[spec.kind]
    size = spec.size if spec.size is not None else size
    if not lo <= size <= hi:
        raise VidgenError(f"cell size {format_length(size)}: {_a_cell(spec.kind)} is drawn from {lo:g} to {hi:g} µm long")
    aspect = spec.aspect if spec.aspect is not None else aspect
    top = 4.0 if spec.kind == "bacterium" else 2.5
    if not 1.0 <= aspect <= top:
        raise VidgenError(f"cell aspect {aspect:g}: the long axis over the short one, from 1 (round) to {top:g}")
    if spec.kind != "plant" and spec.wall is not None:
        raise VidgenError("cell wall: the wall thickness is for plant cells (a bacterium's comes with gram)")
    entries = _entries(spec)
    for entry_id, obj in entries:
        _check_static(entry_id, obj, spec.kind)
    builder = Builder(spec)
    category = {i: KINDS[e[1].kind].category for i, e in enumerate(entries)}
    structures = [(i, e) for i, e in enumerate(entries) if category[i] == "structure"]
    filaments = [(i, e) for i, e in enumerate(entries) if category[i] == "filament"]
    complexes = [(i, e) for i, e in enumerate(entries) if category[i] == "complex"]
    structures.sort(key=lambda item: (_PLACE_ORDER.get(item[1][1].kind, 9), item[1][1].at is None, item[0]))
    for _, (entry_id, obj) in structures:
        kind = KINDS[obj.kind]
        if kind.shape == "sheets":
            things = builder.place_sheets(entry_id, obj, kind)
        elif kind.shape == "stack":
            things = builder.place_golgi(entry_id, obj, kind)
        elif kind.shape == "tubules":
            things = builder.place_tubules(entry_id, obj, kind)
        else:
            obj = _sized(builder, kind, obj)
            things = builder.place_round(entry_id, obj, kind, _defaults(builder, kind, obj))
        builder.add(entry_id, obj, things)
    _generated(builder, entries)
    for _, (entry_id, obj) in filaments:
        builder.add(entry_id, obj, place_filaments(builder, entry_id, obj, KINDS[obj.kind]))
    for _, (entry_id, obj) in complexes:
        kind = KINDS[obj.kind]
        if kind.shape == "motor":
            things = place_motors(builder, entry_id, obj, kind)
        elif obj.on is not None:
            things = _on_surface(builder, entry_id, obj, kind)
        elif obj.at is not None:
            things = _at_point(builder, entry_id, obj, kind)
        else:
            things = builder.scatter_complexes(entry_id, obj, kind, _resolve_in(builder, entry_id, obj, kind))
        builder.add(entry_id, obj, things)
    world = builder.world()
    return CellWorld(world.kind, world.cell, world.placed, world.entries, neighbours(builder), spec.seed, world.envelope, world.membranes,
                     world.channels, world.gram)


def _sized(builder: Builder, kind: Kind, spec: ObjectSpec) -> ObjectSpec:
    """``spec`` with the size its cell gives a kind that has none of its own (a plant's central
    vacuole, a bacterium's nucleoid)."""
    if spec.size is not None:
        return spec
    if kind.name == "vacuole" and builder.spec.kind == "plant":
        size, width = vacuole_size(builder)
        return replace(spec, size=size, width=spec.width or width)
    if kind.name == "nucleoid":
        size, width = nucleoid_size(builder)
        return replace(spec, size=size, width=spec.width or width)
    return spec


def _defaults(builder: Builder, kind: Kind, spec: ObjectSpec) -> list[tuple[Point, float | None] | None]:
    """Default places of the typical layout (``None``: scattered)."""
    if spec.at is not None:
        return []
    if builder.spec.kind == "plant":
        found = plant_defaults(builder, kind, spec.count)
        if found or kind.name not in ("nucleolus",):
            return found
    if builder.spec.kind == "bacterium":
        return bacterium_defaults(builder, kind)
    if kind.name == "nucleus":
        x0, y0, x1, y1 = builder.cell.bounds()
        return [((-0.12 * (x1 - x0) / 2, 0.08 * (y1 - y0) / 2), None)]
    if kind.name == "nucleolus" and builder.nuclei():
        nucleus = builder.nuclei()[0]
        return [((nucleus.center[0] + 0.22 * nucleus.size / 2, nucleus.center[1] + 0.18 * nucleus.width / 2), None)]
    if kind.name == "centrosome":
        point = builder.beside_nucleus(0.8, math.radians(32.0))
        return [(point, None)] if point is not None else []
    return []


def _generated(builder: Builder, entries: list[tuple[str, ObjectSpec]]) -> None:
    """Nuclear pores on each nucleus, ribosomes on the outer nuclear membrane and the rough ER,
    vesicles round each Golgi stack and at the rough ER's exit sites."""
    for entry_id, obj in entries:
        if obj.kind == "nucleus" and obj.pores is not False:
            for nucleus in builder.world().members(entry_id):
                pore_spec = ObjectSpec("nuclear_pore", where=obj.where)
                points = list(nucleus.option("pores", ()))
                builder.add(f"{nucleus.key}.pores", pore_spec, builder.place_bound(f"{nucleus.key}.pores", pore_spec, KINDS["nuclear_pore"],
                                                                                   nucleus, points), owner=entry_id)
        if obj.kind in ("nucleus", "rough_er") and obj.ribosomes is not False:
            for host in builder.world().members(entry_id):
                avoid = [p.center for p in builder.placed if p.surface == host.key and p.kind == "nuclear_pore"]
                avoid += [c for c, _r, _coat, _k in host.option("buds", ())] if host.kind == "rough_er" else []
                points = builder.surface_points(host, 1.0 / ribosome_density(obj.kind), avoid=avoid, clearance=0.09)
                ribo_spec = ObjectSpec("ribosome", where=obj.where)
                builder.add(f"{host.key}.ribosomes", ribo_spec, builder.place_bound(f"{host.key}.ribosomes", ribo_spec, KINDS["ribosome"], host, points),
                            owner=entry_id)
        if obj.kind in ("golgi", "rough_er"):
            for host in builder.world().members(entry_id):
                vesicles = builder.generated_vesicles(host, obj)
                if vesicles:
                    builder.add(f"{host.key}.vesicles", ObjectSpec("vesicle", where=obj.where), vesicles, owner=entry_id)


def _on_surface(builder: Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    entries = {e.id: e for e in builder.entries if e.owner is None}
    if spec.on not in entries:
        raise fail(spec, entry_id, f"on: '{spec.on}' is not an object of this cell{did_you_mean(spec.on or '', list(entries))}")
    host_kind = KINDS[entries[spec.on].kind]
    if host_kind.name not in kind.surfaces:
        allowed = " or ".join(noun(KINDS[k].label) for k in sorted(kind.surfaces))
        raise fail(spec, entry_id, f"a {noun(kind.label)} cannot sit on a {noun(host_kind.label)} (only on a {allowed}): {kind.why}")
    hosts = builder.world().members(spec.on)
    rng = builder.rng(entry_id, "on")
    points: list[tuple[Point, Point]] = []
    taken = [p.center for p in builder.placed if p.surface in {h.key for h in hosts}]
    for host in hosts:
        points += builder.surface_points(host, 0.05, avoid=taken, clearance=0.04)
    rng.shuffle(points)
    if len(points) < spec.count:
        raise fail(spec, entry_id, f"only {len(points)} free places on '{spec.on}' for {spec.count}; use a smaller count")
    chosen = sorted(points[: spec.count])
    host = hosts[0]
    return builder.place_bound(entry_id, spec, kind, host, chosen)


def _at_point(builder: Builder, entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    assert spec.at is not None
    world = builder.world()
    compartment, instance = world.compartment_at(spec.at)
    if spec.inside is not None:
        wanted = _resolve_in(builder, entry_id, spec, kind)
        if not any(compartment == c and (owner is None or instance.startswith(owner.key + ".")) for c, owner in wanted):
            raise fail(spec, entry_id, f"at {at_text(spec.at)} is in the {instance_words(instance)}, not in {spec.inside}; "
                                       "move it or change in")
    if compartment not in kind.places:
        raise fail(spec, entry_id, f"at {at_text(spec.at)}: that point is in the {instance_words(instance)}; {kind.why}")
    size = spec.size or kind.size_in(builder.spec.kind)
    width = spec.width or (kind.width or size)
    angle = math.radians(spec.angle or 0.0)
    p = spec.at
    return [Placed(entry_id, entry_id, kind.name, p, size, width, angle, (Ellipse(p[0], p[1], size / 2, width / 2, angle),), (), instance)]
