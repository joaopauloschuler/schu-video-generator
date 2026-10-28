"""``branching`` and ``branching_pie``: a particle's branching ratios from the model (Phase Y,
Step 241; DESIGN §99.12) as bars or a pie — the ``bar_chart`` and ``pie`` scene types with their
labels, values and caption made from ``particle_physics.branching`` (PDG 2024 measurements; the
Higgs boson: Standard Model predictions of the LHC Higgs Cross Section Working Group, said so on
screen). Everything else — sizes, reveal, highlight, actions — is the chart's own."""

from typing import Any

from vidgen.api import *

from .bar_chart import BarChart
from .pie import Pie

br = particle_physics.branching

#: Chart params the scenes make themselves.
_MADE = ("labels", "values", "changes")


def _fill(data: dict[str, Any], kind: str) -> dict[str, Any]:
    """The chart params of ``particle``'s table: labels, values in %, unit, format, title and the
    source as the caption (an author's caption is kept after the source)."""
    given = [k for k in _MADE if k in data]
    if given:
        raise ValueError(f"{kind} takes its {', '.join(given)} from the particle's branching ratios; for your own numbers use "
                         f"type: {'bar_chart' if kind == 'branching' else 'pie'}")
    name = data.get("particle")
    if not name:
        raise ValueError(f"{kind} needs particle: the decaying particle (listed: {', '.join(br.listed())})")
    try:
        table = br.branching(str(name))
    except VidgenError as exc:
        raise ValueError(str(exc)) from None
    modes = list(table.modes)
    top = data.get("modes")
    if top is not None:
        if not isinstance(top, int) or top < 1:
            raise ValueError("modes: how many of the largest modes to show (a whole number ≥ 1)")
        modes = sorted(modes, key=lambda m: -m.fraction)[:top]
    out = dict(data)
    out["labels"] = [m.label for m in modes]
    out["values"] = [round(m.percent, 6) for m in modes]
    out.setdefault("unit", " %")
    out.setdefault("value_format", "{:.3g}")
    symbol = particle_physics.particle(str(name)).symbol
    out.setdefault("title", f"How the {symbol} decays" if table.parent != "H" else "How a 125 GeV Higgs boson decays")
    source = f"source: {table.source}" + (" (a theory prediction, not a measurement)" if table.kind == "theory" else "")
    if top is not None and len(modes) < len(table.modes):
        source += f" · the {len(modes)} largest of {len(table.modes)} listed modes"
    caption = str(data.get("caption") or "")
    out["caption"] = f"{source} · {caption}" if caption else source
    return out


@scene("branching")
class Branching(BarChart):
    """A particle's branching ratios as bars (``particle: H``; Z, W±, π±, π⁰, K±, μ±): each decay
    mode's share in percent from the model, the source in the caption (PDG 2024; for the Higgs
    boson the LHC Higgs XS WG prediction, labelled a prediction). Sorted largest first,
    horizontal; the bar chart's reveal, highlight and actions.

    Action targets: those of ``bar_chart`` — ``title``, ``bar<N>``, ``bar:<label>`` (e.g.
    ``bar:γγ``)."""

    class Params(BarChart.Params):
        particle: str = Field(min_length=1)
        """The decaying particle: H, Z, W+ / W-, pi+ / pi-, pi0, K+ / K-, mu- / mu+."""
        modes: int | None = Field(default=None, ge=1)
        """Show only the largest this many modes (the caption says so)."""
        labels: list[str] = Field(default_factory=list)
        """Made from the particle (do not set): the products' symbols (bb̄, γγ), hadrons, invisible."""
        values: list[float] = Field(default_factory=list)
        """Made from the particle (do not set)."""

        @model_validator(mode="before")
        @classmethod
        def _build(cls, data: Any) -> Any:
            if not isinstance(data, dict):
                return data
            out = _fill(data, "branching")
            out.setdefault("sort", True)
            out.setdefault("horizontal", True)
            out.setdefault("colors", "palette")
            return out


@scene("branching_pie")
class BranchingPie(Pie):
    """A particle's branching ratios as a pie (``particle: Z``): each decay mode's share from the
    model with the source in the caption; modes under ``other_below`` % (default 1.5 for a pie:
    the Higgs boson's γγ at 0.23 % would be a sliver — use ``branching`` bars for it) are grouped.

    Action targets: those of ``pie`` — ``title``, ``slice<N>``, ``slice:<label>``, ``legend``."""

    class Params(Pie.Params):
        particle: str = Field(min_length=1)
        """The decaying particle: H, Z, W+ / W-, pi+ / pi-, pi0, K+ / K-, mu- / mu+."""
        modes: int | None = Field(default=None, ge=1)
        """Show only the largest this many modes (the caption says so)."""
        labels: list[str] = Field(default_factory=list)
        """Made from the particle (do not set): the products' symbols (μ⁺μ⁻), hadrons, invisible."""
        values: list[float] = Field(default_factory=list)
        """Made from the particle (do not set)."""

        @model_validator(mode="before")
        @classmethod
        def _build(cls, data: Any) -> Any:
            if not isinstance(data, dict):
                return data
            out = _fill(data, "branching_pie")
            out.setdefault("show_values", "value")
            out.setdefault("other_below", 1.5)
            out.setdefault("sort", True)
            return out


__all__ = ["Branching", "BranchingPie"]
