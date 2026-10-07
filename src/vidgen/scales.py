"""Type scales: named sets of the six built-in font sizes, selected with ``theme: {scale: NAME}``.

A scale is shorthand for the sizes ``title``, ``subtitle``, ``heading``, ``body``, ``caption``
and ``small`` (DESIGN.md §20). ``auto`` picks a scale from the frame's orientation: ``large``
for portrait (9:16) video, ``standard`` otherwise. This module does not import manim.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

Orientation = Literal["landscape", "portrait", "square"]

#: The size tokens a scale defines.
SCALE_TOKENS: tuple[str, ...] = ("title", "subtitle", "heading", "body", "caption", "small")

TYPE_SCALES: Mapping[str, Mapping[str, int]] = MappingProxyType(
    {
        "compact": MappingProxyType({"title": 48, "subtitle": 36, "heading": 32, "body": 28, "caption": 22, "small": 20}),
        "standard": MappingProxyType({"title": 56, "subtitle": 42, "heading": 36, "body": 32, "caption": 24, "small": 20}),
        "large": MappingProxyType({"title": 66, "subtitle": 50, "heading": 44, "body": 38, "caption": 30, "small": 26}),
    }
)
#: What ``auto`` means per orientation.
AUTO_SCALES: Mapping[Orientation, str] = MappingProxyType({"landscape": "standard", "square": "standard", "portrait": "large"})
#: Valid ``scale`` values.
SCALE_CHOICES: tuple[str, ...] = (*TYPE_SCALES, "auto")
#: The scale used when neither the config nor a preset chooses one.
DEFAULT_SCALE = "auto"


def frame_orientation(width: float, height: float) -> Orientation:
    """``"landscape"`` (wider than 1.2:1), ``"portrait"`` (taller than 1:1.2) or ``"square"``."""
    if width > 1.2 * height:
        return "landscape"
    if height > 1.2 * width:
        return "portrait"
    return "square"


def resolve_scale(name: str, orientation: Orientation = "landscape") -> str:
    """The concrete scale for ``name`` (``auto`` → by ``orientation``)."""
    if name == "auto":
        return AUTO_SCALES[orientation]
    if name not in TYPE_SCALES:
        raise ValueError(f"unknown type scale {name!r}; available: {', '.join(SCALE_CHOICES)}")
    return name


def scale_sizes(name: str, orientation: Orientation = "landscape") -> dict[str, int]:
    """The six font sizes of scale ``name`` (resolving ``auto`` by ``orientation``)."""
    return dict(TYPE_SCALES[resolve_scale(name, orientation)])
