"""Named poses and expressions of characters (DESIGN.md §69.3). No manim.

A *pose* sets the body parts (:data:`POSE_PARTS`), an *expression* the face
(:data:`EXPRESSION_PARTS`), so one of each can be combined. Each is a table part ->
:class:`~vidgen.config.PartPoseEntry` (angle, scale, shift, shape) relative to the rest drawing;
the parts of its group it does not name go back to rest. A part the character does not have is
skipped, and a shape is a list of choices (the first the character has), so every entry works on
generated and SVG characters alike. Characters may add or replace entries under ``poses:`` /
``expressions:`` in ``video.yaml``.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from typing import get_args

from vidgen.config import ExpressionPart, PartPoseEntry, PosePart
from vidgen.errors import VidgenError

#: Parts a pose sets.
POSE_PARTS: tuple[str, ...] = get_args(PosePart)
#: Parts an expression sets.
EXPRESSION_PARTS: tuple[str, ...] = get_args(ExpressionPart)
KINDS: tuple[str, ...] = ("pose", "expression")

PoseTable = Mapping[str, Mapping[str, PartPoseEntry]]


def _p(**settings: dict) -> dict[str, PartPoseEntry]:
    return {part: PartPoseEntry(**values) for part, values in settings.items()}


#: Built-in poses. Facing right, ``arm_left`` is the near arm (on the screen's right); arms hang
#: down at rest, so +90 points it forward.
POSES: dict[str, dict[str, PartPoseEntry]] = {
    "stand": {},
    "pointing": _p(arm_left={"angle": 88}, head={"angle": -3}),
    "waving": _p(arm_left={"angle": 150}, head={"angle": 4}),
    "thinking": _p(arm_left={"angle": 160, "scale": [1, 0.72]}, head={"angle": 7}),
    "shrug": _p(arm_left={"angle": 45, "shift": [0, 0.02]}, arm_right={"angle": -45, "shift": [0, 0.02]}, head={"angle": 6}),
    "arms_crossed": _p(arm_left={"angle": -65, "scale": [1, 0.8]}, arm_right={"angle": 65, "scale": [1, 0.8]}),
    "sitting": _p(body={"shift": [0, -0.1]}, legs={"angle": 80}),
}

#: Built-in expressions. The rest mouth is a smile (``smile``), so a negative y scale makes a frown.
EXPRESSIONS: dict[str, dict[str, PartPoseEntry]] = {
    "neutral": _p(mouth={"scale": [0.9, 0.35]}),
    "happy": _p(mouth={"scale": [1.15, 1.25]}, brows={"shift": [0, 0.01]}),
    "sad": _p(mouth={"scale": [0.9, -0.8]}, brows={"shape": "sad", "shift": [0, 0.005]}, eyes={"scale": [1, 0.85], "shift": [0, -0.005]}),
    "angry": _p(mouth={"scale": [0.8, -0.5]}, brows={"shape": "angry", "shift": [0, -0.012]}, eyes={"scale": [1, 0.8]}),
    "surprised": _p(mouth={"shape": ["open", "O", "A"]}, brows={"shift": [0, 0.025]}, eyes={"scale": 1.2}),
    "worried": _p(mouth={"scale": [0.7, -0.45], "shift": [0, -0.004]}, brows={"shape": "sad", "shift": [0, 0.015]}, eyes={"scale": [1, 1.1]}),
    "thinking": _p(mouth={"scale": [0.6, 0.3], "shift": [0.01, 0]}, brows={"angle": -8, "shift": [0, 0.01]}, eyes={"shift": [0.008, 0.012]}),
}


def kind_parts(kind: str) -> tuple[str, ...]:
    """The parts a ``pose`` or an ``expression`` sets."""
    return POSE_PARTS if kind == "pose" else EXPRESSION_PARTS


def builtin_table(kind: str) -> dict[str, dict[str, PartPoseEntry]]:
    """:data:`POSES` or :data:`EXPRESSIONS`."""
    if kind not in KINDS:
        raise ValueError(f"kind must be pose or expression, not {kind!r}")
    return POSES if kind == "pose" else EXPRESSIONS


def merged_table(kind: str, own: PoseTable | None = None) -> dict[str, Mapping[str, PartPoseEntry]]:
    """The built-in table of ``kind`` with a character's own entries added (same name: its own wins)."""
    return {**builtin_table(kind), **(own or {})}


def unknown_name_message(kind: str, name: str, known: Iterable[str], who: str | None = None) -> str:
    """``character 'pip': unknown pose 'pointng'; did you mean 'pointing'? poses: stand, ...``."""
    known = list(known)
    close = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    prefix = f"character '{who}': " if who else ""
    return f"{prefix}unknown {kind} '{name}'{hint} {kind}s: {', '.join(known)}"


def find_entry(kind: str, name: str, own: PoseTable | None = None, who: str | None = None) -> Mapping[str, PartPoseEntry]:
    """The parts of pose / expression ``name``; raises :class:`VidgenError` listing the known names."""
    table = merged_table(kind, own)
    if name not in table:
        raise VidgenError(unknown_name_message(kind, name, table, who))
    return table[name]


def chosen_shape(entry: PartPoseEntry, shapes: Iterable[str]) -> str | None:
    """The first of ``entry``'s shape choices among ``shapes`` (``None``: the rest shape)."""
    available = set(shapes)
    return next((s for s in entry.shape_choices() if s in available), None)


__all__ = [
    "EXPRESSIONS",
    "EXPRESSION_PARTS",
    "KINDS",
    "POSES",
    "POSE_PARTS",
    "builtin_table",
    "chosen_shape",
    "find_entry",
    "kind_parts",
    "merged_table",
    "unknown_name_message",
]
