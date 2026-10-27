"""The beat actions of the ``plot`` scene type (DESIGN §97.6): ``fit`` draws a fitted curve (its
band, the curve, its parameters and residual panel) and ``annotate`` an annotation, each on a
word (``at: "@word"``); ``reveal`` also works for a series or its error bars. Written against
``vidgen.api``; the scene draws (``scenes/plot.py``)."""

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
