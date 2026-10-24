"""The process runtime of the ``molecule`` scene (DESIGN.md §95.10; a mixin of
:class:`~vidgen.scenes.molecule.Molecule`, split from it in Step 211): the animations of
``set_state``, ``transport``, ``diffuse``, ``osmosis`` and ``action_potential`` — plans from
``vidgen.cellworld.transport`` played with their captions (full or short, ``notes``), the
concentration bars and the voltage readout following them."""

import math
import random
from dataclasses import replace
from typing import Any

from vidgen.api import *

from .cell import PLATE_OPACITY
from .molecule_process import Hold, PlanPlayer, Segment, Track, plan_morph, voltage_at

tr = cell_transport
#: Particles and captions lie over the molecules, under the labels.
PARTICLE_Z, NOTE_Z = 1.0, 8.0


class MoleculeRuntime:
    """The process actions of a molecule scene, playing."""

    # ----- process actions: runtime ---------------------------------------------------------------

    def molecule_state(self, molecule: str) -> str | None:
        """A molecule's state now."""
        return self.specs[molecule].state

    def _segment(self, molecule: str, spec: MoleculeSpec) -> Segment:
        placed = next(p for p in self.placed if p.id == molecule)
        seg = plan_morph(self.live[molecule], self._prims(placed, spec), self._make, self.groups[molecule])
        seg.owner = molecule
        self.specs[molecule] = spec
        return seg

    def _player(self, plan: Any, tracks: dict[str, Track], segments: dict[int, list[Segment]], notes: CellNoteMode, extra: list[Any] | None = None) -> list[Animation]:
        """The animation of ``plan``: its molecules, particles and captions (``notes``, full or
        short) and ``extra``."""
        captions: list[Mobject | None] = []
        for phase in plan.phases:
            text = cell_note_text(phase.note, notes, self.frame_height > self.frame_width)
            captions.append(self._caption(text) if text else None)
        owners = dict.fromkeys(seg.owner for segs in segments.values() for seg in segs)
        movers = [self.groups[m] for m in owners] + [c for c in captions if c is not None] + [t.mob for t in tracks.values()]
        if extra:
            movers += [m for m in getattr(self, "_extra_mobs", [])]
        previous = getattr(self, "_last_caption", None)       # the caption an earlier process left: it gives way
        if previous is not None:
            movers.append(previous)
        player = PlanPlayer(self.particles, plan, self.to_scene, tracks, segments, captions, extra or [], previous=previous)
        player.dead_parents = list(self.groups.values())
        self._last_caption = captions[-1] if captions else None
        return [player, *[Hold(m) for m in movers]]

    def _caption(self, note: str) -> Mobject:
        """A step's caption on a plate at the top of the body."""
        room = self.body.width - 0.4
        size = chart_label_size(self.params.label_size)          # never below the readable size
        words = self.markup(note, size=size, color="text")
        if words.width > room:
            # lines of words (breaks outside tags), as many as it takes
            spaces = [k for k, ch in enumerate(note) if ch == " " and note[:k].count("<") == note[:k].count(">")]
            lines, start = [], 0
            while True:
                fits = [k for k in spaces if k > start and self.markup(note[start:k], size=size).width <= room]
                if not fits or self.markup(note[start:], size=size).width <= room:
                    lines.append(note[start:])
                    break
                lines.append(note[start:fits[-1]])
                start = fits[-1] + 1
            words = VGroup(*[self.markup(line, size=size, color="text") for line in lines]).arrange(DOWN, buff=0.08)
        lines_room = self.caption_top - self.body.y1 - 0.1
        if words.width > room or words.height > lines_room:
            words.scale(min(room / words.width, lines_room / words.height))
        plate = RoundedRectangle(width=words.width + 0.3, height=words.height + 0.2, corner_radius=0.08, stroke_width=0,
                                 fill_color=self.theme.background, fill_opacity=PLATE_OPACITY)
        group = VGroup(plate, words)
        group.move_to([self.body.center[0], self.caption_top - group.height / 2 - 0.05, 0.0])
        group.set_z_index(NOTE_Z)
        self.notes_layer.add(group)
        return group

    def morph_molecule(self, molecule: str, state: str | None) -> list[Animation]:
        """``set_state``: the molecule morphs to ``state``."""
        spec = self.specs[molecule]
        if spec.state == state:
            return []
        seg = self._segment(molecule, replace(spec, state=state))
        plan = tr.Plan((), (tr.Phase(1.0),))
        return self._player(plan, {}, {0: [seg]}, False)

    def _row_of(self, molecule: str) -> int:
        return next(p.row for p in self.placed if p.id == molecule) or 0

    def run_transport(self, molecule: str, options: Any, seed: str) -> list[Animation]:
        """``transport``: plan the molecule's transport from its state now and play it."""
        placed = next(p for p in self.placed if p.id == molecule)
        spec = replace(self.specs[molecule], bare=True)
        state = spec.state or (placed.kind.states[0] if placed.kind.states else "")
        glyph = molecule_glyph(spec)
        pool = self.pools[self._row_of(molecule)]
        b = tr.builder(f"{self.params.seed}:{seed}:{len(pool.by_side)}", pool, f"{molecule}.t{id(options) % 997}.")
        origin = placed.center
        kind = placed.item.kind
        if kind == "ion_channel":
            ion = options.ion or spec.ion or "K+"
            way = options.direction or self.gradients.passive_way(ion) or MOLECULE_ION_FLOW.get(ion, "in")
            plan = tr.plan_channel(molecule, glyph, origin, ion, way, options.count, b)
        elif kind == "aquaporin":
            way = options.direction or "in"
            plan = tr.plan_aquaporin(molecule, glyph, origin, way, options.count, b)
        elif kind == "carrier":
            plan = tr.plan_carrier(molecule, spec, glyph, origin, state, options.cycles, b)
        elif kind == "na_k_atpase":
            plan = tr.plan_na_k_pump(molecule, glyph, origin, state, options.cycles, b)
        elif kind == "h_atpase":
            plan = (tr.plan_v_type(molecule, glyph, origin, options.cycles, b) if glyph.facts.get("type") == "v"
                    else tr.plan_p_type_h(molecule, glyph, origin, state, options.cycles, b))
        else:
            plan = tr.plan_abc(molecule, spec, glyph, origin, state, options.cycles, b)
        plan, segments = self._with_bare(plan, [molecule])
        tracks = self._tracks(plan)
        return self._player(plan, tracks, segments, options.notes)

    def _with_bare(self, plan: Any, molecules: list[str]) -> tuple[Any, dict[int, list[Segment]]]:
        """``plan`` with a short first phase in which the molecules' drawn solutes and arrows
        give way to the moving ones, and the morphs of its phases."""
        total = sum(phase.weight for phase in plan.phases) or 1.0
        plan = replace(plan, phases=(cell_transport.Phase(total * 0.06),) + tuple(plan.phases))
        segments: dict[int, list[Segment]] = {0: [self._segment(m, replace(self.specs[m], bare=True)) for m in molecules]}
        for k, phase in enumerate(plan.phases):
            for mol, new_state in phase.states:
                segments.setdefault(k, []).append(self._segment(mol, replace(self.specs[mol], state=new_state)))
        return plan, segments

    def _tracks(self, plan: Any) -> dict[str, Track]:
        """Each moving particle's mobject (made now for new ones, unseen until they appear) and
        its moves by phase."""
        tracks: dict[str, Track] = {}
        for particle in plan.particles:
            mob = self.particle_mobs.get(particle.id)
            if mob is None:
                mob = self._particle(particle.species, particle.start, particle.id, shown=False)
            moves = [(k, m) for k, phase in enumerate(plan.phases) for m in phase.moves if m.particle == particle.id]
            rest = []
            for m in mob.get_family():
                if isinstance(m, VMobject) and len(m.points):
                    rest.append((m, 1.0 if m.get_fill_opacity() > 0 or not particle.shown else 0.0, 1.0 if m.get_stroke_opacity() > 0 or not particle.shown else 0.0))
            tracks[particle.id] = Track(mob, moves, particle.shown, rest)
        return tracks

    def run_diffusion(self, solute: str, share: float, seed: str) -> list[Animation]:
        """``diffuse``: every particle of the solute wanders; more cross down the gradient."""
        s = next(x for x in self.params.solutes if x.name == solute)
        rng = random.Random(f"{self.params.seed}:{seed}")
        self._extra_mobs = []
        phases_moves: list[Any] = []
        particles: list[Any] = []
        ends: dict[str, str] = {}
        summary = ""
        for row, pool in enumerate(self.pools):
            field_ = {side: list(items) for (species, side), items in pool.by_side.items() if species == s.solute}
            if not field_:
                continue
            crossing = tr.Crossing((), self.rows_y[row], BILAYER_NM / 2, self.membrane is not None)
            boxes = {side: pool.boxes[side] for side in pool.boxes}
            for side in boxes:
                field_.setdefault(side, [])
            plan = tr.plan_diffusion(s.solute, field_, boxes, crossing, share, rng, "")
            particles += list(plan.particles)
            phases_moves += list(plan.phases[0].moves)
            ends.update(plan.sides)
            summary = summary or plan.summary
            # the pool follows the particles to where they end
            last = {m.particle: m.path[-1] for m in plan.phases[0].moves}
            for side in boxes:
                pool.by_side[(s.solute, side)] = []
            for pid, side in plan.sides.items():
                pool.by_side[(s.solute, side)].append((pid, last.get(pid, (0.0, 0.0))))
        how = "through the bilayer" if self.membrane is not None else "through the solution"
        note = f"{MOLECULE_KINDS[s.solute].label if s.solute in MOLECULE_KINDS else chem_markup(s.solute)} diffuses {how}: random walks, net flux down the gradient"
        plan = tr.Plan(tuple(particles), (tr.Phase(1.0, (), tuple(phases_moves), note),), {}, (), (), ends, summary)
        tracks = self._tracks(plan)
        extra = self._level_change(s, ends)
        return self._player(plan, tracks, {}, "auto", extra)

    def _level_change(self, s: Any, ends: dict[str, str]) -> list[Any]:
        """The bars and values of ``s`` moving to the concentrations its particles now give."""
        levels = self.levels[s.name]
        counts: dict[str, int] = {}
        for side in ends.values():
            counts[side] = counts.get(side, 0) + 1
        total_mM = sum(levels.values())
        total = sum(counts.values()) or 1
        sides = list(membrane_sides(self.membrane)) if self.membrane else ["left", "right"]
        new = {side: total_mM * counts.get(self._side_key(side), 0) / total for side in sides}
        self.levels[s.name] = new
        return self._bar_updates(s.name, levels, new)

    def _bar_updates(self, name: str, old: dict[str, float], new: dict[str, float]) -> list[Any]:
        """Callbacks that grow the bars from ``old`` to ``new`` and swap the values at the end."""
        updates = []
        for side in old:
            item = self.bar_items.get((name, side))
            if item is None:
                continue
            rect, text, high = item
            start_w = rect.width
            end_w = max(self.bar_full * new.get(side, 0.0) / high, 0.02)
            left = rect.get_left()
            fresh = self.markup(_concentration(new.get(side, 0.0)), size=self.params.label_size, color="text")
            fresh.move_to(text.get_center()).align_to(text, LEFT).set_z_index(NOTE_Z)
            fresh.set_opacity(0.0)
            group = self.bars[name] if name in self.bars else VGroup()
            group.add(fresh)
            self._extra_mobs += [rect, text, fresh]
            self.bar_items[(name, side)] = (rect, fresh, high)

            def grow(alpha: float, rect: Any = rect, start_w: float = start_w, end_w: float = end_w, left: Any = left, text: Any = text,
                     fresh: Any = fresh) -> None:
                w = start_w + (end_w - start_w) * alpha
                rect.stretch_to_fit_width(max(w, 0.02))
                rect.move_to(left + RIGHT * rect.width / 2)
                swap = min(1.0, max(0.0, (alpha - 0.8) / 0.2))
                text.set_opacity(1.0 - swap)
                fresh.set_opacity(swap)

            updates.append(grow)
        return updates

    def run_osmosis(self, count: int, seed: str) -> list[Animation]:
        """``osmosis``: water crosses towards the side with more solute (through aquaporins when
        there are any)."""
        exo, cyto = membrane_sides(self.membrane)  # type: ignore[arg-type]
        sides = {cyto: {}, exo: {}}  # type: ignore[var-annotation]
        for s in self.params.solutes:
            for side, value in self.levels[s.name].items():
                sides[side][s.solute] = value
        way = tr.osmosis_way(sides[cyto], sides[exo]) or "in"
        src, dst = ("p", "n") if way == "in" else ("n", "p")
        rng = random.Random(f"{self.params.seed}:{seed}")
        self._extra_mobs = []
        moves: list[Any] = []
        particles: list[Any] = []
        ends: dict[str, str] = {}
        for row, pool in enumerate(self.pools):
            spots = tuple(p.center[0] for p in self.placed if p.item.kind == "aquaporin" and p.row == row)
            crossing = tr.Crossing(spots, self.rows_y[row], BILAYER_NM / 2, True)
            source = list(pool.by_side.get(("water", src), []))
            back = list(pool.by_side.get(("water", dst), []))
            n = min(count, len(source))
            crossers = {pid for pid, _ in sorted(source, key=lambda it: _reach(it[1], crossing))[:n]}
            returners = {pid for pid, _ in sorted(back, key=lambda it: _reach(it[1], crossing))[:max(0, min(len(back), n // 4))]}
            boxes = pool.boxes
            new_src, new_dst = [], []
            for side, items in ((src, source), (dst, back)):
                other = dst if side == src else src
                for pid, q in items:
                    particles.append(tr.Particle(pid, "water", q, shown=True))
                    if pid in crossers or pid in returners:
                        x = min(spots, key=lambda sx: abs(sx - q[0])) if spots else q[0] + rng.uniform(-1.0, 1.0)
                        sign = 1.0 if side == "p" else -1.0
                        reach = BILAYER_NM / 2 + 1.2
                        a, z = (x, self.rows_y[row] + sign * reach), (x, self.rows_y[row] - sign * reach)
                        end = (rng.uniform(boxes[other][0], boxes[other][2]), rng.uniform(boxes[other][1], boxes[other][3]))
                        t0 = rng.uniform(0.0, 0.45)
                        path = tr.wander(rng, q, a, 7, 1.0, boxes[side]) + [(x, self.rows_y[row])] + tr.wander(rng, z, end, 7, 1.0, boxes[other])
                        moves.append(tr.Move(pid, tuple(path), t0, min(1.0, t0 + 0.5)))
                        ends[pid] = other
                        (new_dst if other == dst else new_src).append((pid, end))
                    else:
                        path = tr.jiggle(rng, q, 10, 0.8, boxes[side])
                        moves.append(tr.Move(pid, tuple(path), 0.0, 1.0))
                        ends[pid] = side
                        (new_src if side == src else new_dst).append((pid, path[-1]))
            pool.by_side[("water", src)] = new_src
            pool.by_side[("water", dst)] = new_dst
            # the solutes stay on their sides: they only jiggle
            for (species, side), items in list(pool.by_side.items()):
                if species == "water":
                    continue
                for pid, q in items:
                    particles.append(tr.Particle(pid, species, q, shown=True))
                    moves.append(tr.Move(pid, tuple(tr.jiggle(rng, q, 8, 0.4, boxes[side])), 0.0, 1.0))
        through = "through the aquaporins" if any(p.item.kind == "aquaporin" for p in self.placed) else "slowly through the bilayer"
        names = {exo: CELL_COMPARTMENTS[exo].label.lower(), cyto: CELL_COMPARTMENTS[cyto].label.lower()}
        note = (f"Osmosis: water moves {through} to the {names[cyto if way == 'in' else exo]}, the side with more solute "
                f"({tr.osmolarity(sides[exo]):.0f} mOsm/L in the {names[exo]}, {tr.osmolarity(sides[cyto]):.0f} in the {names[cyto]})")
        plan = tr.Plan(tuple(particles), (tr.Phase(1.0, (), tuple(moves), note),), {}, (), (), ends, f"{count} water {way}")
        tracks = self._tracks(plan)
        extra: list[Any] = []
        # dilution: the solutes of the side water enters get more dilute, the other side's more concentrated
        dst_name, src_name = (cyto, exo) if way == "in" else (exo, cyto)
        o_dst, o_src = tr.osmolarity(sides[dst_name]), tr.osmolarity(sides[src_name])
        mean = (o_dst + o_src) / 2
        f_dst = (o_dst + (mean - o_dst) * 0.5) / o_dst if o_dst else 1.0
        f_src = (o_src + (mean - o_src) * 0.5) / o_src if o_src else 1.0
        for s in self.params.solutes:
            if s.solute == "water":
                continue
            old = dict(self.levels[s.name])
            new = {dst_name: old.get(dst_name, 0.0) * f_dst, src_name: old.get(src_name, 0.0) * f_src}
            self.levels[s.name] = new
            extra += self._bar_updates(s.name, old, new)
        return self._player(plan, tracks, {}, "auto", extra)

    def run_action_potential(self, options: Any, seed: str) -> list[Animation]:
        """``action_potential``: the channels open and close with the voltage trace; ions flow;
        the readout, the charges and the inset plot follow the membrane potential."""
        na, k = _ap_channels(self.placed)
        row = na[0].row or 0
        pool = self.pools[row]
        b = tr.builder(f"{self.params.seed}:{seed}", pool, "ap.")
        na_g = [(p.id, molecule_glyph(replace(self.specs[p.id], bare=True)), p.center) for p in na]
        k_g = [(p.id, molecule_glyph(replace(self.specs[p.id], bare=True)), p.center) for p in k]
        plan = tr.plan_action_potential(na_g, k_g, b, options.ions)
        trace = plan.voltage
        plan, segments = self._with_bare(plan, [p.id for p in na + k])
        lead = plan.phases[0].weight / sum(phase.weight for phase in plan.phases)
        # the trace starts after the short first phase
        trace = tuple([(0.0, trace[0][1])] + [(lead + (1 - lead) * a, v) for a, v in trace])
        tracks = self._tracks(plan)
        extra: list[Any] = []
        self._extra_mobs = []
        if self.readout is not None:
            self._extra_mobs.append(self.readout)
            extra.append(lambda alpha: self.digits.show(voltage_at(trace, alpha)))
        if self.charge_sets.get("rest"):
            self._extra_mobs.append(self.charges)
            extra.append(lambda alpha: self.show_charges(voltage_at(trace, alpha)))
        if options.plot and self.plot is not None:
            _, axes, live, dot = self.plot
            self._extra_mobs += [live, dot]

            def draw(alpha: float) -> None:
                u = max(0.0, (alpha - lead) / (1.0 - lead))
                live.pointwise_become_partial(self.ap_full, 0.0, max(u, 1e-4))
                dot.move_to(axes.point(u * tr.AP_DURATION, voltage_at(trace, alpha)))

            extra.append(draw)
        return self._player(plan, tracks, segments, options.notes, extra)


def _reach(p: tuple[float, float], crossing: Any) -> float:
    dy = abs(p[1] - crossing.y)
    if crossing.spots:
        return min(math.hypot(p[0] - x, dy) for x in crossing.spots)
    return dy


def _concentration(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.3g} M"
    if value >= 1:
        return f"{value:.3g} mM"
    if value >= 0.001:
        return f"{value * 1000:.3g} µM"
    if value <= 0:
        return "0"
    return f"{value * 1e6:.3g} nM"


def _ap_channels(placed: list[Any]) -> tuple[list[Any], list[Any]]:
    """The voltage-gated Na⁺ and K⁺ channels of the scene."""
    na, k = [], []
    for p in placed:
        if p.item.kind != "ion_channel" or (p.item.gating or "voltage") != "voltage":
            continue
        ion = p.item.ion or "K+"
        if ion == "Na+":
            na.append(p)
        elif ion == "K+":
            k.append(p)
    return na, k


def _end_state(p: Any, state: str | None) -> str | None:
    """The state a transporter is in after its transport cycles."""
    kind = p.item.kind
    if kind in ("na_k_atpase",) or (kind == "h_atpase" and p.glyph.facts.get("type") != "v"):
        return "e1"
    if kind == "abc_transporter":
        return "inward"
    if kind == "carrier":
        mode, solutes, moves, ratio = carrier_parts(p.spec)  # type: ignore[arg-type]
        first = "outward" if moves[0] == "in" else "inward"
        if mode == "antiport" and state in ("outward", "inward"):
            return state
        return first
    return state


__all__ = ["MoleculeRuntime", "NOTE_Z", "PARTICLE_Z"]
