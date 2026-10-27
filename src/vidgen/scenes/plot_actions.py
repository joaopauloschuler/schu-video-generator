"""The beat actions of the ``plot`` scene type (DESIGN §97.6, §97.8): ``fit`` draws a fitted curve
(its band, the curve, its parameters and residual panel), ``annotate`` an annotation and
``grow`` grows live series, each on a word (``at: "@word"``); ``reveal`` also works for a series
or its error bars, and ``zoom`` with ``x`` / ``y`` zooms a plot's axes to a region. Written
against ``vidgen.api``; the scene draws (``scenes/plot.py``, ``scenes/plot_live.py``)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


def _plot_problems(action: str, prefix: str, what: str, scene_cls: type[NarratedScene], params: Any, targets: list[str]) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "plot_actions", False):
        return [("action", f"{action} is an action of plot scenes (type: plot)")]
    names = [n for n in scene_cls.target_names(params) if n.startswith(prefix)]
    if not names:
        return [("action", f"{action} needs {what} in the plot's params ({'fits' if action == 'fit' else 'annotations'}: [...])")]
    for t in targets:
        if not any(fnmatchcase(n, t) for n in names):
            return [("target", f"{action} acts on {what}: {', '.join(names)}; '{t}' is not one" + did_you_mean(t, names))]
    return []


@action("fit")
class FitAction(Action):
    """Draw a fit of a ``plot`` on a word (``fit: fit1`` or ``fit: "fit:decay"``): the band, the
    curve, its legend entry and parameter box, and its residual panel (the data first, if not on
    screen yet)."""

    run_time = 1.6
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _plot_problems("fit", "fit", "a fit", scene_cls, params, self.config.targets())

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return [anim for target in targets for anim in scene.entrance(target)]


def _grow_names(params: Any) -> list[str]:
    """The targets a ``grow`` may name: live series, and panels / axes holding some."""
    names = []
    live_panels = set()
    for k, panel in enumerate(params.panel_list(), start=1):
        for s in panel.series:
            if s.is_live:
                live_panels.add(k)
    for i, s in enumerate(params.all_series(), start=1):
        if s.is_live:
            names += [f"series{i}", f"series:{s.name}"]
    if live_panels:
        names.append("axes")
        if params.panel_count() > 1:
            names += [f"panel{k}" for k in sorted(live_panels)]
    return names


@action("grow")
class Grow(Action):
    """Grow live series of a ``plot`` until the beat's next action or its end, or over ``run_time`` (``grow:
    "series:position"``, ``grow: axes`` for every live series together, ``grow: panel2``),
    from where they are to ``to`` (in the model's time, or the point number for live data; default
    the end): the line draws with its head marker and readout, the axes widening as the data
    reach their edge. A later ``grow`` continues from there."""

    class Options(ActionOptions):
        to: float | None = None
        """Grow to this time of the model (or point number of live data); default: the end."""

    run_time = 3.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "plot_actions", False):
            return [("action", "grow is an action of plot scenes (type: plot)")]
        names = _grow_names(params)
        if not names:
            return [("action", "grow needs a live series in the plot (a series of a model, or live: true)")]
        for t in self.config.targets():
            if not any(fnmatchcase(n, t) for n in names):
                return [("target", f"grow acts on live series and the panels holding them: {', '.join(names)}; '{t}' is not one" + did_you_mean(t, names))]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """Until the beat's next action (a ``fit`` on a later word) or the end of the beat."""
        left = scene.beat_time_left(next_action=True)
        return None if left is None else max(left, 1 / config.frame_rate)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.grow_to(targets, self.options.to)  # type: ignore[attr-defined]


@action("annotate")
class Annotate(Action):
    """Show an annotation of a ``plot`` on a word (``annotate: annotation2`` or ``annotate:
    "annotation:peak"``): its ring, arrow, line or shaded range, and its text."""

    run_time = 1.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _plot_problems("annotate", "annotation", "an annotation", scene_cls, params, self.config.targets())

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return [anim for target in targets for anim in scene.entrance(target)]
