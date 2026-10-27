"""The chart core for scientific plots (Phase W, DESIGN §97), without manim: tick values and
number formats (:mod:`.numbers`, :mod:`.ticks`), axes with linear, log, symlog, reversed and
broken scales (:mod:`.axis`), tables read from CSV with units in the headers (:mod:`.data`) and
the layout of multi-panel figures (:mod:`.figure`). The drawing layer is ``vidgen.plot_draw``;
the ``plot`` scene type uses both. Exported by ``vidgen.api`` as the module ``plotcore``."""

from .axis import BREAK_GAP, SCALES, Axis, AxisSpec, build_axis, equal_aspect
from .data import Column, Table, did_you_mean, parse_number, read_table, split_header
from .figure import Label, Measure, PanelInput, PanelLayout, Rect, approx_measure, clip_polyline, label_stride, layout_figure
from .numbers import (
    MINUS,
    SI_PREFIXES,
    TICK_FORMATS,
    TIMES,
    TickLabels,
    axis_title,
    check_tick_format,
    clean,
    exponent_of,
    plain_number,
    power_of_ten,
    prefixed_unit_problem,
    sci_number,
    si_number,
    superscript,
    tick_labels,
)
from .ticks import default_linthresh, linear_ticks, log_ticks, symlog_inverse, symlog_ticks, symlog_transform

__all__ = [
    "BREAK_GAP",
    "MINUS",
    "SCALES",
    "SI_PREFIXES",
    "TICK_FORMATS",
    "TIMES",
    "Axis",
    "AxisSpec",
    "Column",
    "Label",
    "Measure",
    "PanelInput",
    "PanelLayout",
    "Rect",
    "Table",
    "TickLabels",
    "approx_measure",
    "axis_title",
    "build_axis",
    "check_tick_format",
    "clean",
    "clip_polyline",
    "default_linthresh",
    "did_you_mean",
    "equal_aspect",
    "exponent_of",
    "label_stride",
    "layout_figure",
    "linear_ticks",
    "log_ticks",
    "parse_number",
    "plain_number",
    "power_of_ten",
    "prefixed_unit_problem",
    "read_table",
    "sci_number",
    "si_number",
    "split_header",
    "superscript",
    "symlog_inverse",
    "symlog_ticks",
    "symlog_transform",
    "tick_labels",
]
