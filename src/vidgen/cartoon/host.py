"""A cartoon host beside any scene's content (``host:``, DESIGN.md §71). No manim.

Which host a scene has (the video's ``host:`` changed by the scene's), where it stands (a column
beside the content or a band below it, inside the scene's safe area after the overlays' reserved
room), whose lines move its mouth, and the checks ``vidgen validate`` runs. The drawing is
:mod:`vidgen.cartoon.host_drawing`; :class:`~vidgen.scene.NarratedScene` builds it and reserves
the column or band, so the scene's own layout code (regions, ``place``) keeps clear of it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from vidgen.cartoon.cast import character_names, pose_name_problem, unknown_character_message
from vidgen.config import HostConfig, HostOverride, SceneConfig, VideoConfig, validation_problems
from vidgen.errors import Problem, VidgenError
from vidgen.scales import Orientation, frame_orientation

#: A rectangle ``(x0, y0, x1, y1)`` in Manim units, y up.
Box = tuple[float, float, float, float]

#: The host's height (fraction of the frame's shorter side) when ``size`` is not given.
HOST_SIZES: dict[Orientation, float] = {"landscape": 0.5, "square": 0.42, "portrait": 0.36}
#: The most of the area's height a host may take beside the content, and below it.
BESIDE_MAX_HEIGHT = 0.95
BELOW_MAX_HEIGHT = 0.4
#: The most of the area's width a host's column may take beside the content.
BESIDE_MAX_WIDTH = 0.4
#: How far the floor line reaches past the figure on each side (share of its width).
FLOOR_OVERHANG = 0.25


@dataclass(frozen=True)
class HostLayout:
    """Where a host stands: its ``height`` (Manim units), ``feet`` point, the ``figure``'s box,
    the ``floor`` line ``(x0, x1, y)`` (``None`` without one), the ``reserve`` the content keeps
    clear of (the whole column beside it, or the whole band below it), its ``facing`` and
    whether it stands ``below`` the content."""

    height: float
    feet: tuple[float, float]
    figure: Box
    floor: tuple[float, float, float] | None
    reserve: Box
    facing: str
    below: bool


def host_layout(area: Box, frame_width: float, frame_height: float, host: HostConfig, width_ratio: float) -> HostLayout:
    """The host's place in ``area`` (the scene's safe area, overlays' reserved room taken out) of
    a ``frame_width`` x ``frame_height`` frame; ``width_ratio`` is the posed figure's width over
    its height. Beside the content it stands at the bottom of a full-height column on its
    ``side``; below it (``place: below``, or ``auto`` in a portrait frame) at its side of a
    full-width band at the bottom. Its height is ``size`` (or :data:`HOST_SIZES`) of the shorter
    side, made smaller to fit :data:`BESIDE_MAX_HEIGHT` / :data:`BELOW_MAX_HEIGHT` of the area's
    height and, beside, a column of :data:`BESIDE_MAX_WIDTH` of its width."""
    x0, y0, x1, y1 = area
    orientation = frame_orientation(frame_width, frame_height)
    below = host.place == "below" or (host.place == "auto" and orientation == "portrait")
    spread = 1.0 + 2 * FLOOR_OVERHANG if host.floor else 1.0
    height = (host.size if host.size is not None else HOST_SIZES[orientation]) * min(frame_width, frame_height)
    height = min(height, (y1 - y0) * (BELOW_MAX_HEIGHT if below else BESIDE_MAX_HEIGHT))
    if not below:
        height = min(height, BESIDE_MAX_WIDTH * (x1 - x0) / (width_ratio * spread))
    width = height * width_ratio
    column = width * spread
    right = host.side == "right"
    centre = x1 - column / 2 if right else x0 + column / 2
    reserve = (x0, y0, x1, y0 + height) if below else ((x1 - column, y0, x1, y1) if right else (x0, y0, x0 + column, y1))
    facing = facing_for(host.side, host.facing)
    return HostLayout(
        height=height,
        feet=(centre, y0),
        figure=(centre - width / 2, y0, centre + width / 2, y0 + height),
        floor=(centre - column / 2, centre + column / 2, y0) if host.floor else None,
        reserve=reserve,
        facing=facing,
        below=below,
    )


# ----- pointing and moving (Step 134) -------------------------------------------------------------

#: How far (Manim units) a host's hand may reach past its room (its reserved column or band): less
#: than the gap ``avoid`` keeps between the room and the content (0.2), so a pointing arm never
#: touches the content.
HAND_REACH_OUT = 0.1


def pointed_spot(shoulder: tuple[float, float], box: Box) -> tuple[float, float]:
    """The point of ``box`` (a target's) nearest ``shoulder``: the edge a host points at."""
    x0, y0, x1, y1 = box
    return min(max(shoulder[0], x0), x1), min(max(shoulder[1], y0), y1)


def hand_goal(shoulder: tuple[float, float], spot: tuple[float, float], room: Box, reach_out: float = HAND_REACH_OUT) -> tuple[float, float]:
    """Where a pointing hand goes: on the line from ``shoulder`` to ``spot``, as far towards
    ``spot`` as ``room`` grown by ``reach_out`` allows (the arm's solver bends the elbow when that is
    nearer than the arm is long, and points it straight when farther). A shoulder outside the room
    stays where it is."""
    x0, y0, x1, y1 = room[0] - reach_out, room[1] - reach_out, room[2] + reach_out, room[3] + reach_out
    sx, sy = shoulder
    if not (x0 <= sx <= x1 and y0 <= sy <= y1):
        return shoulder
    dx, dy = spot[0] - sx, spot[1] - sy
    share = 1.0
    for d, start, low, high in ((dx, sx, x0, x1), (dy, sy, y0, y1)):
        if d > 1e-12:
            share = min(share, (high - start) / d)
        elif d < -1e-12:
            share = min(share, (low - start) / d)
    return sx + share * dx, sy + share * dy


@dataclass(frozen=True)
class HostMove:
    """A host walking to the other side of its area: the ``side`` it goes to, the x its feet go to
    on screen (``feet_x``), its room there (``reserve``, on screen) and how far the content slides
    on screen meanwhile (``content_shift``: the column's width beside the content, 0 in a band
    below it)."""

    side: str
    feet_x: float
    reserve: Box
    content_shift: float


def host_move_plan(area: Box, feet_x: float, reserve: Box, side: str, below: bool, to: str) -> HostMove | None:
    """Where a ``host_move`` to ``to`` (``other_side``, ``left`` or ``right``) takes a host standing
    at ``feet_x`` (screen) on ``side`` of ``area`` (the safe area its layout used) with its room
    ``reserve`` (screen): mirrored within the area. Beside the content its column swaps sides and
    the content slides the column's width the other way; in a band below the content only the host
    walks. ``None`` when it is on that side already."""
    goal = ("left" if side == "right" else "right") if to == "other_side" else to
    if goal == side:
        return None
    ax0, _, ax1, _ = area
    rx0, ry0, rx1, ry1 = reserve
    mirrored = (ax0 + ax1 - rx1, ry0, ax0 + ax1 - rx0, ry1)
    shift = 0.0 if below else (rx1 - rx0) * (1.0 if goal == "left" else -1.0)
    return HostMove(goal, ax0 + ax1 - feet_x, mirrored, shift)


def facing_for(side: str, facing: str) -> str:
    """Which way a host on ``side`` faces with ``facing`` (``auto``: towards the content)."""
    return facing if facing != "auto" else ("left" if side == "right" else "right")


# ----- which host a scene has ---------------------------------------------------------------------


def video_host(config: VideoConfig) -> HostConfig | None:
    """The video's ``host:`` as a :class:`HostConfig` (a name is ``{character: name}``)."""
    value = config.host
    return HostConfig(character=value) if isinstance(value, str) else value


def scene_host(config: VideoConfig, scene: SceneConfig) -> HostConfig | None:
    """The host of ``scene``: the video's changed by the scene's ``host:`` (``false``: none; a
    name: that character; a mapping: those keys). ``ValueError`` when the result is not a host
    (a mapping or ``true`` without a character and no video host)."""
    base = video_host(config)
    setting = scene.host
    if setting is False:
        return None
    if setting is None or setting is True:
        if setting is True and base is None:
            raise ValueError("host: true, but the video has no host: (give a character name or {character: NAME})")
        return base
    changes: dict[str, Any] = {"character": setting} if isinstance(setting, str) else setting.model_dump(exclude_unset=True)
    merged = {**(base.model_dump() if base is not None else {}), **changes}
    if merged.get("character") is None:
        raise ValueError("host: the video has no host:, so this scene's host needs a character")
    return HostConfig.model_validate(merged)


def scene_takes_host(scene: SceneConfig) -> bool:
    """Whether the scene names a host itself (not just the video's, nor ``false``)."""
    return scene.host is not None and scene.host is not False


def host_continues(config: VideoConfig, index: int, takes_host: Callable[[str], bool]) -> bool:
    """Whether scene ``index``'s host stands on in the next scene, unchanged (same character,
    place and look): it then stays on screen in this scene's fade-out. ``takes_host(type)`` tells
    whether a scene type draws hosts."""
    scenes = config.scenes
    if index + 1 >= len(scenes) or not takes_host(scenes[index].type) or not takes_host(scenes[index + 1].type):
        return False
    try:
        here, after = scene_host(config, scenes[index]), scene_host(config, scenes[index + 1])
    except (ValueError, ValidationError):
        return False
    return here is not None and here == after


# ----- who speaks ---------------------------------------------------------------------------------


def host_speaks(config: VideoConfig, host: HostConfig, voice: str) -> bool:
    """Whether a beat said in ``voice`` moves the host's mouth: always in its own voice; with
    ``speaks: narrator`` also in any voice no other character of the video owns."""
    owners = {entry.name: entry.voice for entry in config.characters}
    if owners.get(host.character) is not None and owners[host.character] == voice:
        return True
    if host.speaks == "own":
        return False
    return all(owner != voice for name, owner in owners.items() if name != host.character)


# ----- checks -------------------------------------------------------------------------------------


def _character_problems(config: VideoConfig, host: HostConfig, where: str, written: set[str]) -> list[Problem]:
    """The ``written`` keys of a host checked: the character is declared, its pose and
    expression are names it knows (checked again when the character changes)."""
    known = character_names(config)
    if "character" in written and host.character not in known:
        return [Problem(f"{where}.character", unknown_character_message(host.character, known))]
    problems = []
    for kind in ("pose", "expression"):
        name = getattr(host, kind)
        checked = kind in written or "character" in written
        message = pose_name_problem(config, host.character, kind, name) if name is not None and checked else None
        if message is not None:
            problems.append(Problem(f"{where}.{kind}", message))
    return problems


def host_problems(config: VideoConfig) -> list[Problem]:
    """The video's and the scenes' ``host:`` checked against ``characters:`` (the character and
    its pose / expression names) and merged per scene, and the host actions of the beats
    (:func:`host_action_problems`); ``parse_config`` runs it."""
    base = video_host(config)
    problems = _character_problems(config, base, "host", {"character"}) if base is not None else []
    for i, scene in enumerate(config.scenes):
        where = f"scenes[{i}].host"
        try:
            host = scene_host(config, scene)
        except ValidationError as exc:
            problems += validation_problems(exc, ("scenes", i, "host"), HostConfig, noun="key")
            continue
        except ValueError as exc:
            problems.append(Problem(where, str(exc).removeprefix("host: ")))
            continue
        setting = scene.host
        if host is not None and isinstance(setting, (str, HostOverride)):
            written = {"character"} if isinstance(setting, str) else set(setting.model_fields_set)
            problems += _character_problems(config, host, where, written)
    return problems + host_action_problems(config)


#: The beat actions that act on a scene's host (DESIGN.md §71.1), and those that walk it.
HOST_ACTIONS: frozenset[str] = frozenset({"host_point", "host_look", "host_react", "host_move", "host_enter", "host_exit"})
HOST_MOVES: frozenset[str] = frozenset({"host_move", "host_enter", "host_exit"})


def host_action_problems(config: VideoConfig) -> list[Problem]:
    """Host actions written in a scene that has no host, more than one host move (``host_move``,
    ``host_enter``, ``host_exit``) in a beat, and a ``host_react`` expression the host does not
    know (``parse_config`` runs it with :func:`host_problems`)."""
    problems = []
    for i, scene in enumerate(config.scenes):
        try:
            host = scene_host(config, scene)
        except (ValueError, ValidationError):
            continue   # host_problems reports it
        for j, beat in enumerate(scene.beats):
            moves = 0
            for k, act in enumerate(beat.actions):
                if act.action not in HOST_ACTIONS:
                    continue
                where = f"scenes[{i}].beats[{j}].actions[{k}]"
                if host is None:
                    problems.append(Problem(where, f"{act.action}: scene '{scene.id}' has no host (give the video or the scene a host:)"))
                    continue
                moves += act.action in HOST_MOVES
                if moves == 2:
                    problems.append(Problem(where, f"{act.action}: one host move per beat (host_move, host_enter or host_exit); put it in another beat"))
                if act.action == "host_react" and act.target is not None:
                    for name in act.targets():
                        message = pose_name_problem(config, host.character, "expression", name)
                        if message is not None:
                            problems.append(Problem(f"{where}.target", message))
    return problems


def host_color_problems(config: VideoConfig, theme: Any) -> list[Problem]:
    """``floor_color`` values that are not theme colours (``theme``: the project's)."""
    problems = []
    entries = [("host", video_host(config))] + [(f"scenes[{i}].host", s.host) for i, s in enumerate(config.scenes) if isinstance(s.host, HostOverride)]
    for where, host in entries:
        color = getattr(host, "floor_color", None)
        if color is None:
            continue
        try:
            theme.color(color)
        except VidgenError as exc:
            problems.append(Problem(f"{where}.floor_color", str(exc)))
    return problems


def host_warnings(config: VideoConfig) -> list[str]:
    """A host with ``speaks: own`` whose character has no voice: its mouth never moves."""
    voices = {entry.name: entry.voice for entry in config.characters}
    hosts = [("host", video_host(config))]
    for i, scene in enumerate(config.scenes):
        if scene_takes_host(scene):
            try:
                hosts.append((f"scenes[{i}].host", scene_host(config, scene)))
            except (ValueError, ValidationError):
                continue
    out = []
    for where, host in hosts:
        if host is not None and host.speaks == "own" and host.character in voices and voices[host.character] is None:
            out.append(f"{where}: speaks: own, but character '{host.character}' has no voice, so its mouth never moves (give it voice: or use speaks: narrator)")
    return out
