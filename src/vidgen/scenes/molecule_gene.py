"""Gene expression in a ``molecule`` scene (DESIGN.md §95.11): with a ``gene``, the scene is a
close-up of one gene's expression — the DNA with its promoter, exons and introns; RNA polymerase
II and the general transcription factors; the pre-mRNA, its cap, splicing, its 3′ end; the
nuclear pore; the ribosome with its tRNAs; the ER membrane with SRP, Sec61 and the
oligosaccharyltransferase; chaperones — and the steps of expression are beat actions
(``transcribe``, ``cap``, ``splice``, ``polyadenylate``, ``export``, ``translate``,
``target_er``, ``glycosylate``, ``fold``). A mixin of :class:`~vidgen.scenes.molecule.Molecule`:
the ``gene`` param, the checks ``vidgen validate`` runs (the steps replayed in beat order), the
drawing and the animations. The model and the poses are ``vidgen.cellworld.expression*``'s."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .math_axes import ChainedTargets
from .molecule_process import Hold

#: The steps a molecule scene plays (vesicle traffic between organelles is the cell scene's).
GENE_ACTIONS = ("transcribe", "cap", "splice", "polyadenylate", "export", "translate", "target_er", "glycosylate", "fold")
#: Steps of a cell scene only.
CELL_ONLY = ("to_golgi", "secrete")
#: Captions and the not-to-scale note lie over the drawing.
NOTE_Z = 8.0
#: The slots the view spans across: a wide frame, a tall one.
WINDOW_WIDE, WINDOW_TALL = 36.0, 18.0


class GeneParams(SceneParams):
    """A gene: written (``sequence`` with ``introns`` positions) or generated (``protein`` or
    ``codons``, ``introns`` a count) from ``seed``."""

    id: str = "gene"
    """Its name for actions (transcribe: gene)."""
    name: str | None = None
    """The gene's symbol (italic; checked against the species' nomenclature: human INS, mouse Ins2)."""
    product: str | None = None
    """The protein's name (roman; checked like a molecule's protein)."""
    species: str | None = None
    """For name and product: human (default: the scene's), mouse, rat, yeast…"""
    sequence: str | None = None
    """The coding strand of the transcribed region, 5′→3′ from the transcription start (+1), DNA (ACGT): 5′ UTR, exons and introns, 3′ UTR with the poly(A) signal AATAAA."""
    introns: int | list[tuple[int, int]] | None = None
    """With a sequence: their positions [[start, end], …] (1-based, inclusive; each must start GT and end AG); with protein or codons: how many (generated: GU…branch A…AG)."""
    protein: str | None = None
    """The protein (one-letter MALW… or three-letter Met-Ala-Leu…): the gene is written for it (frequent human codons); with a sequence: checked against what it encodes."""
    codons: int | None = Field(None, ge=3, le=160)
    """A generated protein of this many codons (Met included, the stop codon not); default 12 (72 with a signal peptide)."""
    signal_peptide: bool = False
    """Generated: start with a cleavable signal peptide (n-, h- and c-region); written: checked that it has one."""
    glycosylation: bool = False
    """Generated: an N-glycosylation sequon (Asn-X-Ser/Thr) after the signal peptide; written: checked."""
    seed: int = 1
    """Changes a generated gene's sequence."""
    start: Literal["dna", "mrna"] = "dna"
    """What the scene shows at first: dna (the gene in the nucleus) or mrna (a mature mRNA in the cytosol, ready to be translated)."""
    codes: Literal["three", "one"] = "three"
    """Amino acids as three-letter (Met) or one-letter (M) codes."""

    def spec(self, cell: str) -> GeneSpec:
        introns: int | tuple[tuple[int, int], ...] | None
        introns = tuple((int(a), int(b)) for a, b in self.introns) if isinstance(self.introns, list) else self.introns
        return GeneSpec(self.name, self.sequence, introns, self.protein, self.codons, self.signal_peptide or None, self.glycosylation or None,
                        self.seed, cell, "gene")

    def gene(self, cell: str, species: str) -> Gene:
        """The built gene (cached), its names checked."""
        sp = self.species or species
        if self.name is not None:
            gene_markup(self.name, sp, "gene: name")
        if self.product is not None:
            check_protein(self.product, sp, "gene: product", self.name)
        return _gene(self.spec(cell))


@lru_cache(maxsize=32)
def _gene(spec: GeneSpec) -> Gene:
    return build_gene(spec)


def step_options(name: str, options: Any) -> dict[str, object]:
    """The options a step's rules read."""
    out: dict[str, object] = {}
    for key in ("codons", "chaperone", "to"):
        value = getattr(options, key, None)
        if value is not None:
            out[key] = value
    return out


class GeneExpression:
    """The gene-expression close-up of a molecule scene."""

    # ----- validation -----------------------------------------------------------------------------

    @classmethod
    def gene_problem(cls, params: Any, name: str, target: str, options: Any) -> str | None:
        """Why the step ``name`` cannot act on ``target`` in this scene (whatever comes before it:
        :meth:`gene_sequence_problems` replays the order)."""
        if params.gene is None:
            return (f"{name} is a step of gene expression: give the scene a gene (gene: {{codons: 12, introns: 1}}) and act on its id "
                    f"({name}: gene)")
        if target != params.gene.id:
            return f"{name} acts on the gene: {name}: {params.gene.id}{did_you_mean(target, [params.gene.id])}"
        if name in CELL_ONLY:
            return (f"{name} carries the protein between organelles in vesicles: it is an action of cell scenes (a cell with the same "
                    f"gene); a molecule scene shows the molecular steps (transcribe … fold)")
        chaperone = getattr(options, "chaperone", None)
        if chaperone is not None and chaperone not in GENE_CHAPERONES:
            return f"chaperone '{chaperone}'{did_you_mean(chaperone, list(GENE_CHAPERONES))} ({', '.join(GENE_CHAPERONES)})"
        return None

    @classmethod
    def gene_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The steps replayed in beat and ``at`` order from the scene's start: each must be
        possible after the ones before it (no translation before export, no glycosylation
        outside the ER…)."""
        try:
            gene = params.gene.gene(params.cell, params.species)
        except VidgenError:
            return []
        state = ExpressionState.at_start(gene, params.gene.start)
        beats = [b.id for b in spec.beats]
        order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))
        cap_later = any(u.kind.name == "cap" for u in uses)
        problems: list[tuple[str, str]] = []
        for i in order:
            use = uses[i]
            name = use.kind.name
            if name not in GENE_STEPS or name in CELL_ONLY:
                continue
            options = step_options(name, use.action.options)
            problem = gene_step_problem(gene, state, name, options)
            if problem:
                problems.append((f"{use.location}.target", problem))
                continue
            state = gene_advance(gene, state, name, {**options, "cap_later": cap_later})
        return problems

    # ----- building -----------------------------------------------------------------------------

    def construct_gene(self) -> None:
        """The close-up: the stage, its drawing, the note that it is not to scale."""
        p = self.params  # type: ignore[attr-defined]
        body = self.safe_area  # type: ignore[attr-defined]
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)  # type: ignore[attr-defined]
            body = body.below(title, gap=0.3)
        self.full_body = body
        self.caption_top = body.y1
        lines = 2 if body.width >= body.height else 4
        body = Region(body.x0, body.y0, body.x1, body.y1 - lines * (self.markup("Xg", size=p.label_size).height + 0.08) - 0.3)  # type: ignore[attr-defined]
        self.body = body
        self.notes_layer = VGroup().set_z_index(NOTE_Z)
        self.add(self.notes_layer)  # type: ignore[attr-defined]
        gene = p.gene.gene(p.cell, p.species)
        wide = body.width >= body.height
        window = WINDOW_WIDE if wide else WINDOW_TALL
        cap_later = bool(self.action_uses("cap"))  # type: ignore[attr-defined]
        line = self.markup("Xg", size=p.label_size).height + 0.12  # type: ignore[attr-defined]
        unit = body.width / window
        # under the view: the legend or the protein's readout, and the note (beside them in a
        # wide frame, under them in a tall one)
        strip = line + 0.13 if wide else 2 * line + 0.13
        view = Region(body.x0, body.y0 + strip, body.x1, body.y1)
        self.stage = ExpressionStage(gene, window, view.width / view.height, p.gene.codes, p.gene.start, cap_later,
                                     (line + 0.13) / unit)
        body = view
        colors = CellColors(self.theme.background, self.theme.color("text"))  # type: ignore[attr-defined]
        self._texts: dict[tuple[str, str], Mobject] = {}
        self.drawing = ExpressionDrawing(self.stage, colors, unit, np.array([body.center[0], body.center[1], 0.0]),
                                         (body.width / 2, body.height / 2), self._gene_text, self.theme.color("dim"))  # type: ignore[attr-defined]
        self.drawing.apply(self.stage.pose)
        self.drawing.group.scenery = True   # the strands run on past the view as it follows a step (lint off_frame)
        note =self.markup("schematic: not to scale", size=p.label_size, color="dim")  # type: ignore[attr-defined]
        # the readable size, in the safe area, right of the legend / the protein's readout (which
        # take the left 62 % of a wide view, all of a tall one); a line over them when it does not fit
        beside = wide and note.width <= 0.36 * body.width
        note.move_to([body.x1 - note.width / 2, body.y0 - strip + line / 2 + 0.03 + (0.0 if beside else line + 0.05), 0.0])
        note.set_z_index(NOTE_Z)
        self._last_caption: Mobject | None = None
        chain = ChainedTargets(self)
        base: list[Target] = []
        if title is not None:
            base.append(chain.add("title", title, lambda: [FadeIn(title)], []))
        group = VGroup(self.drawing.group, note)
        items = [chain.add(p.gene.id, group, lambda: [StageFade(self.drawing, self.stage.pose), FadeIn(note)], list(base))]
        chain.reveal(base, items, p.reveal == "all")
        self.finish()  # type: ignore[attr-defined]

    def _gene_text(self, markup: str, height: float, color: str) -> Mobject:
        """A markup text ``height`` high (scene units; the height of an X), made once per text and
        colour as plain shapes (copying a text mobject is slow: it deep-copies its SVG) and
        copied."""
        key = (markup, color)
        made = self._texts.get(key)
        if made is None:
            text = self.markup(markup, size=self.params.label_size, color=color)  # type: ignore[attr-defined]
            made = VGroup(*[VMobject().set_points(m.points.copy()).match_style(m) for m in text.family_members_with_points()])
            self._texts[key] = made
        if not hasattr(self, "_x_height"):
            self._x_height = self.markup("X", size=self.params.label_size).height  # type: ignore[attr-defined]
        mob = made.copy()
        mob.scale(height / self._x_height)
        return mob

    def _gene_caption(self, note: str) -> Mobject:
        """A step's caption on a plate at the top of the body, wrapped by its words' share of the
        whole line's width (a text per line: making texts is slow)."""
        size = self.params.label_size  # type: ignore[attr-defined]
        room = self.body.width - 0.4
        if not hasattr(self, "_char_w"):
            sample = "The polymerase reads the template strand and makes RNA, 5′→3′"
            self._char_w = self.markup(sample, size=size).width / len(sample)  # type: ignore[attr-defined]
        words = _caption_words(note)
        plain = [_plain(w) for w in words]
        per_char = self._char_w
        if (sum(len(w) for w in plain) + len(plain) - 1) * per_char <= room * 0.97:
            group = VGroup(self.markup(note, size=size, color="text"))  # type: ignore[attr-defined]
        else:
            lines: list[list[str]] = [[]]
            width = 0.0
            for w, bare in zip(words, plain):
                add = (len(bare) + (1 if lines[-1] else 0)) * per_char
                if lines[-1] and width + add > room:
                    lines.append([w])
                    width = len(bare) * per_char
                else:
                    lines[-1].append(w)
                    width += add
            group = VGroup(*[self.markup(" ".join(line), size=size, color="text") for line in lines])  # type: ignore[attr-defined]
        group.arrange(DOWN, buff=0.08)
        lines_room = self.caption_top - self.body.y1 - 0.1
        if group.width > room or group.height > lines_room:
            group.scale(min(room / group.width, lines_room / group.height))
        plate = RoundedRectangle(width=group.width + 0.3, height=group.height + 0.2, corner_radius=0.08, stroke_width=0,
                                 fill_color=self.theme.background, fill_opacity=0.86)  # type: ignore[attr-defined]
        caption = VGroup(plate, group.move_to(plate.get_center()))
        caption.move_to([self.body.center[0], self.caption_top - caption.height / 2 - 0.05, 0.0])
        caption.set_z_index(NOTE_Z)
        self.notes_layer.add(caption)
        return caption

    # ----- playing ---------------------------------------------------------------------------------

    def expression_clip(self, name: str, options: Any) -> Any:
        """The clip of a step from where the stage is (made once per use)."""
        return self.stage.play(name, step_options(name, options))

    def expression_seconds(self, clip: Any) -> float:
        """A step's natural length: its phases' weights in seconds."""
        return max(1.5, sum(w for w, _, _ in clip.phases))

    def run_expression(self, name: str, options: Any, clip: Any = None) -> list[Animation]:
        """Play the step ``name``: the stage's clip with its captions."""
        clip = clip or self.expression_clip(name, options)
        notes = getattr(options, "notes", True)
        edges = clip.edges()
        captions: list[tuple[float, float, Mobject]] = []
        if notes:
            k = 0
            phases = clip.phases
            while k < len(phases):
                j = k
                while j + 1 < len(phases) and phases[j + 1][1] == phases[k][1]:
                    j += 1
                if phases[k][1]:
                    captions.append((edges[k], edges[j + 1], self._gene_caption(phases[k][1])))
                k = j + 1
        previous = self._last_caption
        self._last_caption = captions[-1][2] if captions else None
        player = StagePlayer(self.drawing, clip, captions, previous)
        holds = [Hold(c) for _, _, c in captions] + ([Hold(previous)] if previous is not None else [])
        return [player, *holds]


def _caption_words(note: str) -> list[str]:
    """A caption's words, markup tags kept whole within a word (``<sub>3</sub>`` never split)."""
    words, current, depth = [], "", 0
    for ch in note:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == " " and depth == 0:
            if current:
                words.append(current)
            current = ""
        else:
            current += ch
    if current:
        words.append(current)
    return words


def _plain(word: str) -> str:
    """A word without its markup tags."""
    out, depth = "", 0
    for ch in word:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif depth == 0:
            out += ch
    return out


def _opacities(mob: Mobject) -> list[tuple[VMobject, float, float]]:
    return [(m, float(m.get_fill_opacity()), float(m.get_stroke_opacity())) for m in mob.get_family() if isinstance(m, VMobject) and len(m.points)]


def _fade(items: list[tuple[VMobject, float, float]], factor: float) -> None:
    for m, fill, stroke in items:
        m.set_fill(opacity=fill * factor, family=False)
        m.set_stroke(opacity=stroke * factor, family=False)


class StageFade(Animation):
    """The close-up fading in as it is (its entrance): the drawing's own opacities scaled, no
    copy of its thousands of pieces."""

    def __init__(self, drawing: ExpressionDrawing, pose: Any, **kwargs: Any) -> None:
        super().__init__(drawing.group, **kwargs)
        self.drawing, self.pose = drawing, pose

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        self.drawing.apply(self.pose, self.rate_func(alpha))


class StagePlayer(Animation):
    """Plays a gene-expression clip: each frame the stage's pose at that moment, the captions
    of its phases in turn (the one an earlier step left fades at once)."""

    def __init__(self, drawing: ExpressionDrawing, clip: Any, captions: list[tuple[float, float, Mobject]], previous: Mobject | None,
                 **kwargs: Any) -> None:
        super().__init__(drawing.group, rate_func=linear, **kwargs)
        self.drawing, self.clip = drawing, clip
        self.captions = [(a, b, _opacities(m)) for a, b, m in captions]
        for _, _, items in self.captions:
            _fade(items, 0.0)
        self.previous = _opacities(previous) if previous is not None else []

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        self.drawing.apply(self.clip.at(alpha))
        last = len(self.captions) - 1
        for k, (a, b, items) in enumerate(self.captions):
            ramp = min(0.05, (b - a) * 0.25)
            if alpha < a or alpha > b:
                factor = 0.0 if not (k == last and alpha >= b) else 1.0
            else:
                factor = min(1.0, (alpha - a) / ramp if ramp > 0 else 1.0, (b - alpha) / ramp if ramp > 0 and k < last else 1.0)
            _fade(items, max(0.0, factor))
        _fade(self.previous, max(0.0, 1.0 - alpha / 0.04))


__all__ = ["CELL_ONLY", "GENE_ACTIONS", "GeneExpression", "GeneParams", "StagePlayer", "step_options"]
