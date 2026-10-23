"""A gene's expression in a ``cell`` scene (DESIGN.md §95.11): with a ``gene`` param, the actions
``transcribe``, ``export``, ``translate``, ``to_golgi`` and ``secrete`` follow its products
through the cell — nucleus, nuclear pores, cytosol or rough ER, Golgi, plasma membrane or
lysosome — the camera following them. A mixin of :class:`~vidgen.scenes.cell.Cell`: the checks
``vidgen validate`` runs (the steps replayed in beat order, with the molecular steps each stands
for) and the animations. The places are :mod:`vidgen.cellworld.expression_route`'s."""

from __future__ import annotations

from typing import Any

import numpy as np

from vidgen.api import *

from .cell_traffic import holds

#: Route markers lie over the cell, under the labels and captions.
ROUTE_Z = 46
#: The view's middle is raised by this share of its span (the captions cover the body's top).
CAPTION_SHIFT = 0.1


class CellExpression:
    """A gene's route through a cell scene."""

    @classmethod
    def expression_problem(cls, params: Any, name: str, target: str, options: Any) -> str | None:
        """Why the step ``name`` cannot act on ``target`` in this cell (whatever comes before)."""
        if params.gene is None:
            return f"{name} is a step of gene expression: give the cell a gene (gene: {{signal_peptide: true}}) and act on its id"
        if target != params.gene.id:
            return f"{name} acts on the gene: {name}: {params.gene.id}{did_you_mean(target, [params.gene.id])}"
        if name not in GENE_CELL_STEPS:
            return gene_cell_step_problem(params.gene.gene(params.cell.kind, "human"), ExpressionState(), name)
        try:
            gene = params.gene.gene(params.cell.kind, "human")
        except VidgenError as error:
            return str(error)
        return gene_route_problem(params.world(), gene, name)

    @classmethod
    def expression_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """The steps replayed in order: each must be possible after the ones before it."""
        if params.gene is None:
            return []
        try:
            gene = params.gene.gene(params.cell.kind, "human")
        except VidgenError:
            return []
        state = ExpressionState.at_start(gene, params.gene.start)
        beats = [b.id for b in spec.beats]
        order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))
        problems = []
        for i in order:
            use = uses[i]
            name = use.kind.name
            if name not in GENE_CELL_STEPS:
                continue
            options = {"to": use.action.options.to} if name == "secrete" else {}
            problem = gene_cell_step_problem(gene, state, name, options)
            if problem:
                problems.append((f"{use.location}.target", problem))
                continue
            state = gene_cell_advance(gene, state, name, options)
        return problems

    # ----- playing ---------------------------------------------------------------------------------

    def _route(self) -> RoutePlanner:
        if not hasattr(self, "_planner"):
            p = self.params  # type: ignore[attr-defined]
            gene = p.gene.gene(p.cell.kind, "human")
            self._planner = GeneRoutePlanner(self.world, gene, p.seed, self._view_now(), p.gene.start == "mrna")  # type: ignore[attr-defined]
            colors = CellColors(self.theme.background, self.theme.color("text"))  # type: ignore[attr-defined]
            self.route_drawing = GeneRouteDrawing(self._planner, colors, self.ref_pixels, ROUTE_Z)  # type: ignore[attr-defined]
            s = float(self.camera.frame.width) / self._frame[0]  # type: ignore[attr-defined]
            self.route_drawing.apply(self._planner.pose, self.to_scene, s)  # type: ignore[attr-defined]
            self.add(self.route_drawing.group)  # type: ignore[attr-defined]
        return self._planner

    def _view_now(self) -> tuple[tuple[float, float], float]:
        """The camera's view now: the world point at the body's middle and the span (µm)."""
        s, _px, span = self.screen_scale()  # type: ignore[attr-defined]
        frame = self.camera.frame  # type: ignore[attr-defined]
        scene_point = np.array(frame.get_center()) + s * self.body_center  # type: ignore[attr-defined]
        c = self.start.center  # type: ignore[attr-defined]
        middle = (c[0] + (scene_point[0] - self.body_center[0]) / self.unit, c[1] + (scene_point[1] - self.body_center[1]) / self.unit)  # type: ignore[attr-defined]
        return middle, span

    def expression_clip(self, name: str, options: Any) -> Any:
        """The clip of a step from where the products are."""
        planner = self._route()
        (cx, cy), span = self._view_now()
        planner.pose.view = ((cx, cy - CAPTION_SHIFT * span), span)       # as the route's views are written
        step = f"secrete:{options.to}" if name == "secrete" else name
        return planner.play(step)

    def expression_seconds(self, clip: Any) -> float:
        return max(1.5, sum(w for w, _, _ in clip.phases))

    def run_expression(self, name: str, options: Any, clip: Any = None) -> list[Animation]:
        """Play the step: the markers move, the camera follows, the captions change."""
        clip = clip or self.expression_clip(name, options)
        edges = clip.edges()
        steps = tuple((edges[k], note) for k, (_, note, _) in enumerate(clip.phases)) if getattr(options, "notes", True) else ()
        captions = self._captions(steps) if steps else []  # type: ignore[attr-defined]
        return [RoutePlayer(self, clip, captions), *holds(captions)]


class RoutePlayer(Animation):
    """A route clip playing: the camera on each moment's view (``follow``), the markers at their
    places and their size on screen, the captions in turn."""

    def __init__(self, scene: Any, clip: Any, captions: list[tuple[float, float, Mobject]], **kwargs: Any) -> None:
        super().__init__(scene.route_drawing.group, rate_func=linear, **kwargs)
        self.scene, self.clip, self.captions = scene, clip, captions
        self.caption_rest = [[(m, m.get_fill_opacity()) for m in c.get_family() if isinstance(m, VMobject)] for _, _, c in captions]
        for _, _, caption in captions:
            caption.set_opacity(0.0)

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        scene = self.scene
        pose = self.clip.at(alpha)
        center, span = pose.view
        # the captions cover the body's top: the view's middle a little higher, so what it frames
        # sits in the part left free
        center = (center[0], center[1] + CAPTION_SHIFT * span)
        width, cam = scene.view_camera(CellView(center, span, "organelle"))
        frame = scene.camera.frame
        frame.width = width
        frame.move_to(cam)
        scene.on_camera()
        s = float(frame.width) / scene._frame[0]
        scene.route_drawing.apply(pose, scene.to_scene, s)
        for (start, end, caption), rest in zip(self.captions, self.caption_rest):
            ramp = 0.03
            if alpha < start or alpha > end:
                f = 0.0
            else:
                f = min(1.0, (alpha - start) / ramp, (end - alpha) / ramp if end < 1.0 else 1.0 if alpha < 0.985 else (1.0 - alpha) / 0.015)
            for m, base in rest:
                m.set_fill(opacity=base * max(0.0, f), family=False)


__all__ = ["CellExpression", "RoutePlayer"]
