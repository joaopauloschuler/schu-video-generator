"""Continuity between scenes (DESIGN.md §50): a scene starts with objects of the scene before it,
exactly where and how they were (a match cut), then moves them into its own layout.

``carry: [title]`` on scene B (``"title -> heading"`` to move A's ``title`` into B's
``heading``) works across the scenes' separate renders:

1. A's render keeps the carried targets on screen in its fade-out (only the rest fades) and
   records their final look: every vector shape of their on-screen parts (points, fill, stroke)
   in scene coordinates, written next to A's video as ``carry/<A>.json`` with A's fingerprint;
2. B's render (always after A's: the pipeline orders them and renders A first when its record
   is missing or stale) rebuilds those shapes and shows them from its first frame;
3. when B brings in the destination target (its entrance, :meth:`NarratedScene.entrance`), the
   copy moves into it instead: shape by shape when both have as many shapes (the same text or
   icon at another size, place or colour), else a cross-fade between their boxes.

Config-level helpers here import no Manim; the drawing helpers import it when called.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import ValidationError

from vidgen.config import CarryEntry, VideoConfig
from vidgen.errors import Problem

if TYPE_CHECKING:
    from manim import Animation, Mobject, VGroup

    from vidgen.project import Project

#: Version of the ``carry/<scene>.json`` format.
CARRY_VERSION = 1
#: Decimals kept of points (Manim units: 1e-5 is far below a pixel at 4K).
_DECIMALS = 5


def carried_from(config: VideoConfig) -> dict[str, str]:
    """``{scene id: id of the scene before it}`` for every scene that carries objects."""
    return {spec.id: config.scenes[i - 1].id for i, spec in enumerate(config.scenes) if i > 0 and spec.carry}


def carried_out(config: VideoConfig, scene_id: str) -> list[CarryEntry]:
    """The entries of the scene after ``scene_id`` that carry objects out of it (none for the
    last scene or a scene not in the video)."""
    ids = [s.id for s in config.scenes]
    i = ids.index(scene_id) if scene_id in ids else len(ids)
    return list(config.scenes[i + 1].carry) if i + 1 < len(ids) else []


def carry_problems(config: VideoConfig) -> list[Problem]:
    """``carry`` entries naming targets the scene before (source) or the scene itself
    (destination) does not have, for scene types that declare their targets. Skipped where the
    params do not validate (reported elsewhere) or the type is not registered."""
    from vidgen import registry
    from vidgen.actions import match_names, unknown_target_message

    def names(index: int) -> tuple[list[str], tuple[str, ...]] | None:
        spec = config.scenes[index]
        entry = registry.find(spec.type)
        if entry is None or not entry.cls.target_patterns:
            return None
        try:
            params = entry.cls.validate_params(spec.params)
        except ValidationError:  # reported by the params check
            return None
        return entry.cls.target_names(params), entry.cls.target_patterns

    problems: list[Problem] = []
    for i, spec in enumerate(config.scenes):
        if i == 0 or not spec.carry:
            continue
        before, own = names(i - 1), names(i)
        prev = config.scenes[i - 1]
        for entry in spec.carry:
            if before is not None and not match_names(entry.source, before[0]):
                message = unknown_target_message(entry.source, prev.type, before[0], before[1])
                problems.append(Problem(f"scenes[{i}].carry", f"'{entry}': {message} (of the scene before, '{prev.id}')"))
            if own is not None and not match_names(entry.dest, own[0]):
                message = unknown_target_message(entry.dest, spec.type, own[0], own[1])
                problems.append(Problem(f"scenes[{i}].carry", f"'{entry}': {message} (to move into)"))
    return problems


def carry_warnings(config: VideoConfig) -> list[str]:
    """Carries combined with a transition that moves or fades the pictures: the carried objects
    move / fade with them, so the cut is no longer invisible."""
    from vidgen.transitions import effective

    out = []
    for i, spec in enumerate(config.scenes):
        if i and spec.carry:
            t = effective(config, i)
            if t.type not in ("cut", "crossfade"):
                out.append(
                    f"scenes[{i}].carry: '{spec.id}' carries objects in through a {t.type}, which moves or fades them "
                    "with the pictures; a cut (or a crossfade) keeps them in place"
                )
    return out


# ----- the record of the scene before -----------------------------------------------------------


def _enum_name(value: Any) -> Any:
    return getattr(value, "name", value)


def shape_state(mobject: Mobject) -> dict[str, Any]:
    """One vector shape's look as JSON-ready data (without its submobjects)."""
    return {
        "points": np.round(np.asarray(mobject.points, dtype=float), _DECIMALS).tolist(),
        "fill": np.round(np.asarray(mobject.fill_rgbas, dtype=float), 6).tolist(),
        "stroke": np.round(np.asarray(mobject.stroke_rgbas, dtype=float), 6).tolist(),
        "background_stroke": np.round(np.asarray(mobject.background_stroke_rgbas, dtype=float), 6).tolist(),
        "stroke_width": float(mobject.stroke_width),
        "background_stroke_width": float(mobject.background_stroke_width),
        "z_index": float(mobject.z_index),
        "joint_type": _enum_name(mobject.joint_type),
        "cap_style": _enum_name(mobject.cap_style),
    }


def parts_state(parts: Sequence[Mobject]) -> tuple[list[dict[str, Any]], int]:
    """The look of every vector shape with points in ``parts`` (in drawing order) and the
    number of other mobjects with points left out (images, clips: they cannot be rebuilt)."""
    from manim import VMobject

    shapes, skipped, seen = [], 0, set()
    for part in parts:
        for member in part.family_members_with_points():
            if id(member) in seen:
                continue
            seen.add(id(member))
            if isinstance(member, VMobject):
                shapes.append(shape_state(member))
            else:
                skipped += 1
    return shapes, skipped


def rebuild(shapes: Sequence[dict[str, Any]]) -> VGroup:
    """The shapes recorded by :func:`parts_state` as a ``VGroup`` of plain ``VMobject`` s that
    draw exactly like the originals."""
    from manim import VGroup, VMobject
    from manim.constants import CapStyleType, LineJointType

    group = VGroup()
    for state in shapes:
        shape = VMobject()
        shape.set_points(np.array(state["points"], dtype=float).reshape(-1, 3))
        shape.fill_rgbas = np.array(state["fill"], dtype=float).reshape(-1, 4)
        shape.stroke_rgbas = np.array(state["stroke"], dtype=float).reshape(-1, 4)
        shape.background_stroke_rgbas = np.array(state["background_stroke"], dtype=float).reshape(-1, 4)
        shape.stroke_width = state["stroke_width"]
        shape.background_stroke_width = state["background_stroke_width"]
        shape.z_index = state["z_index"]
        if state.get("joint_type") in LineJointType.__members__:
            shape.joint_type = LineJointType[state["joint_type"]]
        if state.get("cap_style") in CapStyleType.__members__:
            shape.cap_style = CapStyleType[state["cap_style"]]
        group.add(shape)
    return group


def carry_path(render_dir: Path, scene_id: str) -> Path:
    """``<render_dir>/carry/<scene_id>.json``: what the scene after ``scene_id`` carries from it."""
    return render_dir / "carry" / f"{scene_id}.json"


def write_record(path: Path, scene_id: str, fingerprint: str, objects: dict[str, list[dict[str, Any]]]) -> None:
    """Write the record of ``scene_id``'s carried objects (``{source name: shapes}``)."""
    from vidgen.fileio import write_text_atomic

    data = {"version": CARRY_VERSION, "scene": scene_id, "fingerprint": fingerprint, "objects": objects}
    write_text_atomic(path, json.dumps(data, separators=(",", ":")) + "\n")


def read_record(path: Path) -> dict[str, Any] | None:
    """A record written by :func:`write_record`, or ``None`` when missing / unreadable / of
    another version."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") == CARRY_VERSION else None


def record_current(project: Project, preview: bool, scene_id: str) -> bool:
    """Whether ``scene_id`` has a carry record made from its current inputs (fingerprint)."""
    from vidgen.render.fingerprint import scene_fingerprint

    record = read_record(carry_path(project.render_dir(preview), scene_id))
    return record is not None and record.get("fingerprint") == scene_fingerprint(project, scene_id)


# ----- moving the copy into the scene ------------------------------------------------------------


def _leaves(mobject: Mobject) -> list[Mobject]:
    from manim import VMobject

    return [m for m in mobject.family_members_with_points() if isinstance(m, VMobject)]


def carry_move(snapshot: VGroup, target: Mobject, **kwargs: Any) -> Animation:
    """The animation moving a carried copy ``snapshot`` into ``target`` (which ends on screen
    in its place): shape by shape when both have as many shapes, else a cross-fade of the two
    stretched between their boxes (Manim's ``FadeTransform``)."""
    from manim import FadeTransform, Transform, VGroup

    leaves = _leaves(target)
    if len(leaves) != len(snapshot.submobjects) or not leaves:
        return FadeTransform(snapshot, target, **kwargs)

    flat = VGroup()
    for leaf in leaves:
        copy = leaf.copy()
        copy.submobjects = []
        flat.add(copy)

    class CarryMove(Transform):
        """``Transform`` of the copy into a flat copy of the target's shapes, then the target
        itself in its place (later actions find it on screen)."""

        def clean_up_from_scene(self, scene: Any) -> None:
            super().clean_up_from_scene(scene)
            scene.remove(self.mobject)
            scene.add(target)

    return CarryMove(snapshot, flat, **kwargs)
