"""Drawing a cell world with Manim (DESIGN.md §95.6): the renderer of the three-layer design
(the world and its rules are in :mod:`vidgen.cellworld`, without manim). Kept as the module
``vidgen.api`` imports from; the drawings live in :mod:`vidgen.cell_draw`."""

from __future__ import annotations

from vidgen.cell_draw import CellColors, CellDrawing, Piece, blend, feature_weight, path_mobject, shape_arrays

#: Older name of :func:`~vidgen.cell_draw.base.shape_arrays`.
shape_curves = shape_arrays

__all__ = ["CellColors", "CellDrawing", "Piece", "blend", "feature_weight", "path_mobject", "shape_curves"]
