"""The beat action of ``karyotype`` scenes (DESIGN.md §96.10): ``rearrange`` plays a change the
notation names — in an ideogram view a structural change as an edit of the normal chromosomes
(deletion, duplication, inversion, translocation, Robertsonian fusion), otherwise its highlight
(an extra copy boxed, a lost one as a dashed ghost, a derivative's changed stretch marked).
Timed like any action (``at: "@word"``). Written against ``vidgen.api``; the scene draws
(``scenes/karyotype.py``)."""

from typing import Any

from vidgen.api import *


def _indices(scene: Any, targets: list[str]) -> list[int]:
    n = len(scene.k.abnormalities)
    out: list[int] = []
    for t in targets:
        ids = list(range(n)) if t in ("changes", "all") else [int(t.split(":", 1)[1]) - 1]
        out += [i for i in ids if i not in out]
    return out


@action("rearrange")
class Rearrange(Action):
    """Play a change of the karyotype (``rearrange: change:1`` — the first change written after
    the sex chromosomes —, or ``changes`` for all in turn). In ``show: ideogram`` a structural
    change runs as an edit: the breakpoints flash, a deletion's segment falls away, a duplicated
    segment is copied in, an inverted one turns round, a translocation's distal segments swap
    places, a Robertsonian translocation joins two long arms while the short arms are lost. A
    numerical change (or any change in a karyogram) is highlighted."""

    run_time = 2.6
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "karyotype_actions", False):
            return [("action", "rearrange is an action of karyotype scenes (type: karyotype)")]
        n = len(params.parsed().abnormalities)
        if n == 0:
            return [("action", f"rearrange plays the changes of the karyotype, and {params.karyotype} has none (write e.g. 47,XX,+21)")]
        for t in self.config.targets():
            if t in ("changes", "all"):
                continue
            if not t.startswith("change:") or not t[7:].isdigit() or not 1 <= int(t[7:]) <= n:
                return [("target", f"rearrange acts on change:1…change:{n} (the changes in the order written) or changes, not '{t}'")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.change_seconds(_indices(scene, self.config.targets()))  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for i in _indices(scene, self.config.targets()):
            anims += scene.run_change(i)  # type: ignore[attr-defined]
        return [Succession(*anims)] if len(anims) > 1 else anims
