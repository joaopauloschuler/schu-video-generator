"""The cell world (DESIGN.md §95): a cell's compartments, membranes and contents as plain data
in real units, the location rules, and the physical-scale camera's levels, level of detail and
scale bar. No manim imports (a test checks): ``vidgen validate`` and lint use it without
rendering; ``vidgen.cell_vector`` and ``scenes/cell.py`` draw it."""

from .catalog import (
    BILAYER, CELL_KINDS, COMPARTMENTS, KINDS, MEMBRANES, TYPICAL_ANIMAL, Compartment, Kind, Membrane, main_interior,
)
from .geometry import ArcBand, Capsule, Ellipse, inside, overlap
from .model import CellSpec, CellWorld, Entry, Neighbour, ObjectSpec, Part, Placed, build_cell_world, did_you_mean
from .units import format_length, nice_length, parse_coordinate, parse_length
from .view import LEVELS, LOD, CellView, focus_point, default_level, label_weight, level_view, lod_weights, scale_bar, smooth_fade, zoom_path

__all__ = [
    "ArcBand", "BILAYER", "CELL_KINDS", "COMPARTMENTS", "Capsule", "CellSpec", "CellView", "CellWorld", "Compartment", "Ellipse", "Entry",
    "KINDS", "Kind", "LEVELS", "LOD", "MEMBRANES", "Membrane", "Neighbour", "ObjectSpec", "Part", "Placed", "TYPICAL_ANIMAL",
    "build_cell_world", "default_level", "did_you_mean", "focus_point", "format_length", "inside", "label_weight", "level_view",
    "lod_weights", "main_interior", "nice_length", "overlap", "parse_coordinate", "parse_length", "scale_bar", "smooth_fade", "zoom_path",
]
