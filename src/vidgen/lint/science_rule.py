"""The scientific-accuracy lint rules (DESIGN.md §95.14): they read the config — each scene's
params (validated by its scene type, its cell world rebuilt where needed, no render) and its
beats' narration — not the stills.

``science_scale`` (a cell scene with a scale bar drawing something far outside its textbook size,
or too many of a one-per-cell structure), ``science_location`` (narration placing a process where
it never is, or a thing where the cell scene does not show it), ``science_direction`` (5′/3′,
N→C, motors, pumps), ``science_energy`` (passive transport called active; active transport with
no energy source in the picture), ``science_naming`` (a scene's gene and protein mixed up, the
wrong case for the species, a gene label without italics), ``science_pathway`` (narration against
a pathway arc's effect) and ``science_counts`` (numbers against the textbook). The knowledge is in
:mod:`vidgen.cellworld.accuracy`; this module gathers each scene's inputs. The runner fills
:attr:`SceneContext.science` with :func:`science_issues`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidgen.cellworld import accuracy as acc
from vidgen.lint.rules import Issue, SceneContext, rule

if TYPE_CHECKING:
    from vidgen.config import LintRules, SceneConfig
    from vidgen.project import Project

#: The rules of this module, in :data:`vidgen.config.LINT_RULES` order.
SCIENCE_RULES: tuple[str, ...] = (
    "science_scale", "science_location", "science_direction", "science_energy", "science_naming", "science_pathway", "science_counts",
)
#: Typical sizes of whole cells (µm, long axis): beyond them by the rule's factor is reported.
CELL_TYPICAL: dict[str, tuple[float, float]] = {"animal": (10.0, 30.0), "plant": (10.0, 100.0), "bacterium": (0.5, 5.0)}
#: Textbook ranges of short axes (µm) for the kinds whose width a scene may set.
WIDTH_RANGES: dict[str, tuple[float, float]] = {"mitochondrion": (0.25, 1.0), "chloroplast": (1.0, 4.0)}
#: Structures a cell has one of (a few at most): more is reported, with the usual exceptions named.
MOST_PER_CELL: dict[str, tuple[int, str]] = {
    "nucleus": (2, "most cells have one nucleus (some, like hepatocytes, two; a muscle fibre many)"),
    "centrosome": (2, "a cell has one centrosome, two after it duplicates in S phase (more is centrosome amplification, as in some cancer cells)"),
    "nucleolus": (4, "a nucleus has one to a few nucleoli"),
    "vacuole": (1, "a plant cell has one central vacuole"),
    "nucleoid": (2, "a bacterium has one nucleoid (two before it divides)"),
}
#: Molecule kinds that show where a cell scene's energy comes from (ATP, a pump, a coupled carrier).
ENERGY_KINDS = frozenset({"atp", "na_k_atpase", "h_atpase", "abc_transporter", "atp_synthase", "carrier"})
MOTOR_KINDS = frozenset({"kinesin", "dynein", "myosin"})


@dataclass(frozen=True)
class ScienceIssue:
    """A finding of one science rule: the beat it is about (``None``: the scene) and the message."""

    rule: str
    beat: str | None
    message: str


def _params(spec: SceneConfig) -> Any:
    """The scene's validated params, or ``None`` (an unknown type or invalid params: validation
    reports those)."""
    from vidgen import registry
    from vidgen.errors import VidgenError

    entry = registry.find(spec.type)
    if entry is None:
        return None
    try:
        return entry.cls.parse_params(spec.params, spec.id)
    except (VidgenError, ValueError, TypeError):
        return None


def _prokaryote(spec: SceneConfig, params: Any) -> bool:
    cell = getattr(params, "cell", None)
    kind = getattr(cell, "kind", cell)
    return kind == "bacterium" or getattr(params, "species", None) == "e_coli"


def _said(quote: str) -> str:
    return f'"{quote}"'


def science_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every science finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in SCIENCE_RULES if getattr(rules, name).severity != "off"}
    params = _params(spec) if spec.type in ("cell", "molecule", "pathway", "cell_cycle", "metabolism") else None
    prokaryote = _prokaryote(spec, params) if params is not None else False
    out: list[ScienceIssue] = []
    for beat in spec.beats:
        if "science_direction" in on:
            out += [ScienceIssue("science_direction", beat.id, f"{_said(c.quote)}: {c.message}") for c in acc.direction_claims(beat.text)]
        if "science_location" in on:
            out += [ScienceIssue("science_location", beat.id, f"{_said(c.quote)}: {c.message}")
                    for c in acc.location_claims(beat.text, prokaryote)]
        if "science_counts" in on:
            out += [ScienceIssue("science_counts", beat.id, f"{_said(c.quote)}: {c.message}") for c in acc.count_claims(beat.text)]
    if params is None:
        return out
    if spec.type == "cell":
        out += _cell(spec, params, rules, on)
    if spec.type in ("cell", "molecule") and "science_energy" in on:
        out += _energy(spec, params)
    if spec.type == "pathway" and "science_pathway" in on:
        out += _pathway(spec, params)
    if "science_naming" in on:
        out += _naming(spec, params)
    return out


# ----- cell scenes ------------------------------------------------------------------------------------


def _cell(spec: SceneConfig, params: Any, rules: LintRules, on: set[str]) -> list[ScienceIssue]:
    from vidgen.cellworld.catalog import KINDS
    from vidgen.cellworld.units import format_length

    out: list[ScienceIssue] = []
    try:
        world = params.world()
    except Exception:  # noqa: BLE001 - validation reports a world that cannot be built
        return out
    first = spec.beats[0].id if spec.beats else None
    claims_scale = bool(params.scale_bar) and not getattr(params, "not_to_scale", False)
    factor = rules.science_scale.factor
    if "science_scale" in on and claims_scale:
        fix = "draw it at a real size, or set the scene's not_to_scale: true (it then says so on screen)"
        body = params.cell
        typical = CELL_TYPICAL.get(body.kind)
        if body.size is not None and typical is not None and not typical[0] / factor <= float(body.size) <= typical[1] * factor:
            out.append(ScienceIssue("science_scale", first, f"cell size {format_length(float(body.size))}: far outside a typical {body.kind} "
                                                            f"cell ({format_length(typical[0])}–{format_length(typical[1])}) while the scene shows "
                                                            f"a scale bar; {fix} (a large cell such as an oocyte is real: lint_ignore it)"))
        for k, obj in enumerate(params.objects):
            kind = KINDS.get(obj.kind)
            if kind is None:
                continue
            name = f"objects[{k}] ({obj.kind}{' ' + repr(obj.id) if obj.id else ''})"
            lo, hi = kind.size_range
            if obj.size is not None and not lo / factor <= float(obj.size) <= hi * factor:
                out.append(ScienceIssue("science_scale", first, f"{name}: size {format_length(float(obj.size))} is far outside the textbook "
                                                                f"{format_length(lo)}–{format_length(hi)}, and the scene shows a scale bar; {fix}"))
            width = WIDTH_RANGES.get(obj.kind)
            if obj.width is not None and width is not None and not width[0] / factor <= float(obj.width) <= width[1] * factor:
                out.append(ScienceIssue("science_scale", first, f"{name}: width {format_length(float(obj.width))} is far outside the textbook "
                                                                f"{format_length(width[0])}–{format_length(width[1])}, and the scene shows a scale "
                                                                f"bar; {fix}"))
    if "science_scale" in on:
        counts: dict[str, int] = {}
        for thing in world.placed:
            counts[thing.kind] = counts.get(thing.kind, 0) + 1
        for kind_name, (most, why) in MOST_PER_CELL.items():
            if counts.get(kind_name, 0) > most:
                out.append(ScienceIssue("science_scale", first, f"the cell has {counts[kind_name]} of kind {kind_name}: {why}; draw fewer "
                                                                f"(an object with the typical one's id replaces it), or lint_ignore it if "
                                                                f"the cell really has them"))
    if "science_location" in on:
        shown: dict[str, tuple[str, frozenset[str]]] = {}
        where: dict[str, set[str]] = {}
        for thing in world.placed:
            where.setdefault(thing.kind, set()).add(thing.host.rsplit(".", 1)[-1])
        for kind_name, comps in where.items():
            kind = KINDS.get(kind_name)
            if kind is None or kind.category == "structure" and kind_name not in ("vesicle",):
                continue          # a structure's place is the cytosol; the location rules refuse others
            for word in {kind.label.lower(), kind.plural.lower()}:
                shown[word] = (kind.plural, frozenset(comps))
        for beat in spec.beats:
            out += [ScienceIssue("science_location", beat.id, f"{_said(c.quote)}: {c.message}") for c in acc.placement_claims(beat.text, shown)]
    return out


# ----- transport ---------------------------------------------------------------------------------------


def _molecule_modes(params: Any) -> dict[str, str | None]:
    """Molecule id -> how it transports (``passive`` / ``secondary`` / ``primary`` / ``None``),
    with the scene's default ids."""
    from vidgen.cellworld.molecules import TRANSPORTERS

    out: dict[str, str | None] = {}
    counts: dict[str, int] = {}
    for item in params.molecules:
        counts[item.kind] = counts.get(item.kind, 0) + 1
        entry = item.id or (item.kind if counts[item.kind] == 1 else f"{item.kind}_{counts[item.kind]}")
        mode = item.mode
        if mode is None and item.transporter and item.transporter.lower() in TRANSPORTERS:
            mode = TRANSPORTERS[item.transporter.lower()].mode
        out[entry] = acc.transport_mode(item.kind, mode)
    return out


def _energy(spec: SceneConfig, params: Any) -> list[ScienceIssue]:
    out: list[ScienceIssue] = []
    if spec.type == "molecule":
        if getattr(params, "gene", None) is not None:
            return out
        modes = _molecule_modes(params)
        has_energy = any(m in ("primary", "secondary") for m in modes.values()) or \
            any(item.kind == "atp" for item in params.molecules) or any(s.solute.lower() == "atp" for s in params.solutes)
    else:
        kinds = {o.kind for o in params.objects}
        if kinds & MOTOR_KINDS:
            return out      # motors walking on ATP are "active transport" in the cell-biology sense
        modes = {}
        has_energy = bool(kinds & ENERGY_KINDS)
    for beat in spec.beats:
        moved = [modes.get(t) for act in beat.actions if act.action == "transport" for t in act.targets()]
        active = acc.says_active(beat.text)
        if active and moved and all(m == "passive" for m in moved):
            out.append(ScienceIssue("science_energy", beat.id, f"{_said(active)}: the beat's transport is passive (a channel, an "
                                                               f"aquaporin or a uniporter, down the gradient, no energy used): call it "
                                                               f"facilitated diffusion, or show a pump or a coupled carrier"))
        elif active and not has_energy:
            out.append(ScienceIssue("science_energy", beat.id, f"{_said(active)}: active transport needs an energy source and the scene "
                                                               f"shows none: add a pump (na_k_atpase, h_atpase), a symporter / antiporter "
                                                               f"(a carrier with its ion) or ATP"))
        passive = acc.says_passive(beat.text)
        if passive and moved and all(m == "primary" for m in moved):
            out.append(ScienceIssue("science_energy", beat.id, f"{_said(passive)}: the beat's transport is a pump using ATP (primary "
                                                               f"active transport), not passive"))
    return out


# ----- pathways ----------------------------------------------------------------------------------------


def _pathway(spec: SceneConfig, params: Any) -> list[ScienceIssue]:
    try:
        pathway = params.pathway()
    except Exception:  # noqa: BLE001 - validation reports it
        return []
    names: dict[str, str] = {}
    for node in pathway.nodes.values():
        if node.kind.name == "phenotype":
            continue
        for name in (node.plain, node.gene):
            if name and len(name) >= 2:
                names.setdefault(name.lower(), node.id)
    arcs = {(e.source, e.target): (e.sign, e.type.name) for e in pathway.edges}
    out: list[ScienceIssue] = []
    for beat in spec.beats:
        out += [ScienceIssue("science_pathway", beat.id, f"{_said(c.quote)}: {c.message}") for c in acc.pathway_claims(beat.text, names, arcs)]
    return out


# ----- names -------------------------------------------------------------------------------------------


def _genes(spec: SceneConfig, params: Any) -> list[acc.GeneName]:
    species = getattr(params, "species", None) or "human"
    found: list[tuple[str, str]] = []
    for item in getattr(params, "molecules", None) or []:
        if getattr(item, "gene", None):
            found.append((item.gene, item.species or species))
    gene = getattr(params, "gene", None)
    if gene is not None and getattr(gene, "name", None):
        found.append((gene.name, gene.species or species))
    if spec.type == "pathway":
        try:
            pathway = params.pathway()
        except Exception:  # noqa: BLE001 - validation reports it
            pathway = None
        if pathway is not None:
            found += [(n.gene, pathway.species) for n in pathway.nodes.values() if n.gene]
    seen: dict[str, acc.GeneName] = {}
    for symbol, sp in found:
        seen.setdefault(symbol, acc.GeneName(symbol, sp, acc.protein_form(symbol, sp)))
    return list(seen.values())


def _texts(spec: SceneConfig, params: Any) -> list[tuple[str, str, bool]]:
    """``(where, text, markup)`` of the scene's own on-screen words: its title, labels of
    molecules (Pango markup) and cell objects, callout labels."""
    out: list[tuple[str, str, bool]] = []
    title = getattr(params, "title", "")
    if isinstance(title, str) and title:
        out.append(("title", title, False))
    for k, item in enumerate(getattr(params, "molecules", None) or []):
        if isinstance(item.label, str):
            out.append((f"molecules[{k}].label", item.label, True))
    for k, obj in enumerate(getattr(params, "objects", None) or []):
        if isinstance(getattr(obj, "label", None), str):
            out.append((f"objects[{k}].label", obj.label, False))
    for beat in spec.beats:
        for act in beat.actions:
            label = act.options.get("label")
            if isinstance(label, str):
                out.append((f"beat '{beat.id}' {act.action} label", label, False))
    return out


def _naming(spec: SceneConfig, params: Any) -> list[ScienceIssue]:
    genes = _genes(spec, params)
    if not genes:
        return []
    out: list[ScienceIssue] = []
    first = spec.beats[0].id if spec.beats else None
    for where, text, markup in _texts(spec, params):
        out += [ScienceIssue("science_naming", first, f"{where} '{c.quote}': {c.message}") for c in acc.naming_claims(text, genes, markup)]
    for beat in spec.beats:
        out += [ScienceIssue("science_naming", beat.id, f"{_said(c.quote)}: {c.message}") for c in acc.naming_claims(beat.text, genes)]
    return out


# ----- the rules -----------------------------------------------------------------------------------------


def _issues(ctx: SceneContext, name: str) -> Iterator[Issue]:
    starts = {beat["id"]: float(beat["start"]) for beat in ctx.beats}
    for found in ctx.science:
        if found.rule != name:
            continue
        beat = found.beat or ctx.beat_at(0.0)
        yield Issue(found.message, None, beat=beat, time=starts.get(beat, 0.0) if beat else 0.0)


@rule("science_scale", scope="scene")
def science_scale(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A cell scene with a scale bar drawing something far outside its textbook size, or too many of a one-per-cell structure."""
    yield from _issues(ctx, "science_scale")


@rule("science_location", scope="scene")
def science_location(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Narration placing a process where it never is, or a thing where the cell scene does not show it."""
    yield from _issues(ctx, "science_location")


@rule("science_direction", scope="scene")
def science_direction(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Narration giving a wrong direction: 3′→5′ synthesis, C→N, kinesin to minus, dynein to plus, pumps the wrong way."""
    yield from _issues(ctx, "science_direction")


@rule("science_energy", scope="scene")
def science_energy(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Passive transport called active (or a pump called passive), or active transport with no energy source shown."""
    yield from _issues(ctx, "science_energy")


@rule("science_naming", scope="scene")
def science_naming(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A scene's gene written as its protein (or the reverse), in the wrong case for the species, or a gene label not in italics."""
    yield from _issues(ctx, "science_naming")


@rule("science_pathway", scope="scene")
def science_pathway(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Narration contradicting a pathway arc's effect (activates for an inhibition, phosphorylates for a dephosphorylation)."""
    yield from _issues(ctx, "science_pathway")


@rule("science_counts", scope="scene")
def science_counts(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A number in the narration contradicting the textbook (net ATP of glycolysis, NADH per turn, ions per pump cycle…)."""
    yield from _issues(ctx, "science_counts")
