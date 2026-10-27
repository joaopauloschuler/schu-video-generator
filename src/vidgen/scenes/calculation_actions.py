"""The beat actions of the ``calculation`` scene type (DESIGN §97.10): ``substitute`` shows a
calculation's values substituted into its formula, ``compute`` its result (with an
intermediate value first, if it has one), ``convert`` the result in other units — each on a
word (``at: "@word"``), with the steps before it that are not on screen yet. ``reveal`` shows
a formula (``reveal: formula2``) or any step, ``highlight`` marks a symbol (``symbol:G``).
Written against ``vidgen.api``; the scene draws (``scenes/calculation.py``)."""

from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *


def _calc_problems(action: str, scene_cls: type[NarratedScene], params: Any, targets: list[str]) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "calculation_actions", False):
        return [("action", f"{action} is an action of calculation scenes (type: calculation)")]
    calcs = list(params.calculations)
    names = []
    for k, c in enumerate(calcs, start=1):
        if action == "convert" and not c.converts():
            continue
        if action == "substitute" and not c.substitute:
            continue
        names += [f"calc{k}", f"calc:{c.name}"]
    if not names:
        need = "a calculation with convert: [unit]" if action == "convert" else "a calculation with substitute: true"
        return [("action", f"{action} needs {need}")]
    for t in targets:
        if not any(fnmatchcase(n, t) for n in names):
            return [("target", f"{action} acts on calculations: {', '.join(names)}; '{t}' is not one" + did_you_mean(t, names))]
    return []


class _CalcAction(Action):
    #: The action's name (the step it shows).
    step = ""
    run_time = 1.2
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _calc_problems(self.step, scene_cls, params, self.config.targets())

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return [anim for target in targets for anim in scene.calculation_step(target, self.step)]  # type: ignore[attr-defined]


@action("substitute")
class Substitute(_CalcAction):
    """Show the values of a ``calculation`` substituted into its formula, on a word
    (``substitute: calc1`` or ``substitute: "calc:v"``); the formula first if it is not on
    screen."""

    step = "substitute"


@action("compute")
class Compute(_CalcAction):
    """Show the result of a ``calculation`` on a word (``compute: calc1``): the steps before it
    that are not on screen yet, then the result in its box (and a conversion no other action
    names)."""

    step = "compute"
    run_time = 1.4


@action("convert")
class Convert(_CalcAction):
    """Show a ``calculation``'s result converted into its ``convert`` units on a word
    (``convert: calc1``)."""

    step = "convert"
