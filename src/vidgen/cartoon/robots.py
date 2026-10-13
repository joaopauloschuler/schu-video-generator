"""Original robot characters of the generator (DESIGN.md §69.58): ``look.species: robot`` and its
``look.robot`` (``head``: ``box`` or ``round``; ``face``: ``eyes`` or ``screen``; ``antenna``;
``moves_on``: ``legs`` or ``wheels``).

A robot keeps the person's build, poses, clothes, accessories and lip sync, and changes:

- the head: a rounded box or a ball on a short neck, a round bolt on each side, and a face plate
  (``eyes``: a light plate with the eyes, brows and mouth on it) or a dark screen on which the
  eyes, brows and mouth glow (:data:`SCREEN_GLOW`; the visemes show on the screen);
- an ``antenna`` part (when ``antenna``): a coil spring on a socket with a light on top, which
  wobbles on the follow-through spring, sways and blinks while idle (shape ``dim``) and trails in
  the wind;
- visible joints (a bolt at each shoulder, elbow and knee), gripper hands, block feet, and a
  panel of lights on the chest;
- on ``wheels`` each shin ends in a strut and a wheel instead of a foot.

Everything is drawn from circles, rounded rectangles, lines and polygons in the look's colours
(plating: ``colors.skin``; casing: ``colors.clothes``; the light: ``colors.accessory``) plus a
few fixed colours (the screen, its glow, tyres), with no feature taken from any known robot.
Character units before the figure is scaled to height 1, as in :mod:`vidgen.cartoon.generator`,
which calls these; facing right, the face looks right.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from manim import BLACK, WHITE, Circle, Ellipse, Line, ManimColor, RoundedRectangle, VGroup, VMobject, interpolate_color

from vidgen.cartoon.animals import fur_shade, fur_tint
from vidgen.cartoon.character import CharacterPart
from vidgen.cartoon.idle import ANTENNA_DIM_SHAPE
from vidgen.cartoon.primitives import arc_points, filled, outlined, polygon, trailing
from vidgen.config import CharacterLook

if TYPE_CHECKING:
    from vidgen.cartoon.generator import Frame

#: Fixed colours: the screen face, what glows on it, a wheel's tyre and the chest lights' third lamp.
SCREEN_COLOR = "#25313B"
SCREEN_GLOW = "#8FF0D6"
TYRE_COLOR = "#3A3F47"
AMBER = "#F2C14E"
#: A box head's (width, height) and corner radius, in head radii.
BOX_HEAD = (2.15, 1.85, 0.3)
#: The radius of a joint's bolt and of a wheel (character units).
JOINT_RADIUS = 0.022
WHEEL_RADIUS = 0.065


def _toward(color: str, other: ManimColor, share: float) -> str:
    return interpolate_color(ManimColor(color), other, share).to_hex()


def is_robot(look: CharacterLook) -> bool:
    """Whether ``look`` is a robot (``species: robot``)."""
    return look.species == "robot"


def has_screen(look: CharacterLook) -> bool:
    """Whether ``look`` is a robot with a screen face."""
    return is_robot(look) and look.robot_look().face == "screen"


def face_colors(look: CharacterLook, c: Mapping[str, str]) -> Mapping[str, str]:
    """The colours the face (eyes, brows, mouth) is drawn in: ``c``, or on a screen face the
    same with the features glowing (:data:`SCREEN_GLOW`)."""
    return {**c, "features": SCREEN_GLOW} if has_screen(look) else c


def head_top(look: CharacterLook, f: Frame) -> float:
    """The y of the top of a robot's head (character units)."""
    r = f.p.head_radius
    return f.head_y + (BOX_HEAD[1] / 2 if look.robot_look().head == "box" else 1.0) * r


def _plate(look: CharacterLook, f: Frame) -> VMobject:
    """The face plate's or the screen's outline: a rounded box on a box head, an oval on a ball."""
    r = f.p.head_radius
    x = f.head_x if f.front else f.face_x + 0.08 * r
    y = f.head_y - 0.05 * r
    width = 1.6 * r if f.front else 1.5 * r
    if look.robot_look().head == "box":
        return RoundedRectangle(width=width, height=1.38 * r, corner_radius=0.24 * r).move_to([x, y, 0])
    return Ellipse(width=width, height=1.32 * r).move_to([x - (0.0 if f.front else 0.03 * r), y, 0])


def head(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A robot's neck, side bolts, head (a rounded box or a ball) and its face plate or screen,
    for the ``head`` part (the eyes, brows and mouth are their own parts)."""
    r, cx, cy, skin, ink = f.p.head_radius, f.head_x, f.head_y, c["skin"], c["outline"]
    robot = look.robot_look()
    shade = fur_shade(skin)
    neck = RoundedRectangle(width=0.55 * r, height=0.5 * r, corner_radius=0.1 * r).move_to([cx, cy - 0.85 * r, 0])
    pieces: list[VMobject] = [outlined(neck, shade, ink, w)]
    half = BOX_HEAD[0] / 2 * r if robot.head == "box" else r
    bolts = [outlined(Circle(radius=0.22 * r).move_to([cx + side * (half + 0.04 * r), cy, 0]), shade, ink, w) for side in (-1.0, 1.0)]
    if f.front:   # one on each side, behind the head
        pieces += bolts
    if robot.head == "box":
        width, height, corner = BOX_HEAD
        shape: VMobject = RoundedRectangle(width=width * r, height=height * r, corner_radius=corner * r).move_to([cx, cy, 0])
    else:
        shape = Circle(radius=r).move_to([cx, cy, 0])
    pieces.append(outlined(shape, skin, ink, w))
    if not f.front:   # the near side's bolt, on the side of the head behind the face
        x = cx - (0.75 if robot.head == "box" else 0.68) * r
        pieces += [outlined(Circle(radius=0.22 * r).move_to([x, cy + 0.02 * r, 0]), shade, ink, w),
                   filled(Circle(radius=0.08 * r).move_to([x, cy + 0.02 * r, 0]), ink)]
    plate = _plate(look, f)
    if robot.face == "screen":
        glare = Line(*([plate.get_left()[0] + k * r, plate.get_top()[1] - (0.14 + k) * r, 0] for k in (0.12, 0.3)))
        pieces += [outlined(plate, SCREEN_COLOR, ink, w), glare.set_stroke(_toward(SCREEN_COLOR, WHITE, 0.35), width=w * 0.8)]
    else:
        pieces.append(outlined(plate, fur_tint(skin), ink, w * 0.6))
    return pieces


def screen_eye(style: str, x: float, y: float, width: float, height: float) -> VMobject:
    """One open eye glowing on a screen face at (``x``, ``y``): the eye style's size filled
    (``sleepy``: its lower half)."""
    if style == "sleepy":
        lower = arc_points(x, y, [width / 2] * 13, 180, 360)
        return filled(polygon([(px, y + (py - y) * 2 * height / width) for px, py in lower]), SCREEN_GLOW)
    return filled(Ellipse(width=width, height=height).move_to([x, y, 0]), SCREEN_GLOW)


def antenna_part(look: CharacterLook, f: Frame, c: Mapping[str, str], w: float) -> CharacterPart | None:
    """The ``antenna`` part (``None`` without ``robot.antenna``): a socket on top of the head, a
    coil spring and a ball light (``colors.accessory``; shape ``dim``: the light off), pivoting at
    the socket; the spring and the light trail in the wind."""
    if not look.robot_look().antenna:
        return None
    r, ink = f.p.head_radius, c["outline"]
    x, top = f.head_x, head_top(look, f)
    root = (x, top + 0.12 * r)

    def drawn(lit: bool) -> VGroup:
        socket = outlined(RoundedRectangle(width=0.4 * r, height=0.3 * r, corner_radius=0.1 * r).move_to([x, top + 0.04 * r, 0]), fur_shade(c["skin"]), ink, w)
        turns = 7
        coil_points = [[x + (0.0 if k in (0, turns + 1) else (0.12 if k % 2 else -0.12) * r), root[1] + 0.75 * r * k / (turns + 1), 0] for k in range(turns + 2)]
        coil = VMobject().set_points_as_corners(coil_points).set_fill(opacity=0).set_stroke(ink, width=w * 0.9)
        light = c["accessory"] if lit else _toward(c["accessory"], BLACK, 0.55)
        ball_y = root[1] + 0.92 * r
        ball = outlined(Circle(radius=0.17 * r).move_to([x, ball_y, 0]), light, ink, w)
        moving = [coil, ball]
        if lit:
            moving.append(filled(Circle(radius=0.05 * r).move_to([x - 0.06 * r, ball_y + 0.06 * r, 0]), "#FFFFFF"))
        return VGroup(socket, *(trailing(m, root, "antenna") for m in moving))

    return CharacterPart("antenna", {"default": drawn(True), ANTENNA_DIM_SHAPE: drawn(False)}, root)


def limb_colors(look: CharacterLook, c: Mapping[str, str], colors: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    """A robot's upper arm, forearm, thigh and shin colours: the outfit's ``colors``, except that
    a plain outfit leaves the limbs in the plating (``colors.skin``)."""
    return (c["skin"],) * 4 if look.outfit == "plain" else colors


def joint(x: float, y: float, c: Mapping[str, str], w: float) -> VMobject:
    """A joint's bolt at (``x``, ``y``): a shoulder, an elbow or a knee."""
    return outlined(Circle(radius=JOINT_RADIUS).move_to([x, y, 0]), fur_shade(c["skin"]), c["outline"], w * 0.6)


def hand(x: float, y: float, c: Mapping[str, str], w: float) -> VGroup:
    """A gripper hand at (``x``, ``y``): a round grip split at the bottom."""
    grip = outlined(Circle(radius=0.045).move_to([x, y, 0]), c["skin"], c["outline"], w)
    slit = Line([x, y - 0.045, 0], [x, y - 0.008, 0]).set_stroke(c["outline"], width=w * 0.8)
    return VGroup(grip, slit)


def foot(look: CharacterLook, x: float, front: bool, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A block foot under the shin at ``x``, its sole on the ground (none with shoes)."""
    if look.shoes != "none":
        return []
    block = RoundedRectangle(width=0.1 if front else 0.14, height=0.05, corner_radius=0.018).move_to([x + (0.0 if front else 0.03), 0.025, 0])
    return [outlined(block, fur_shade(c["skin"]), c["outline"], w * 0.8)]


def wheel(x: float, front: bool, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A wheel standing on the ground under (``x``, its middle :data:`WHEEL_RADIUS` up): a tyre and
    a hub from the side, the tyre's tread edge-on from the front."""
    ink = c["outline"]
    if front:
        tread = RoundedRectangle(width=0.06, height=2 * WHEEL_RADIUS, corner_radius=0.025).move_to([x, WHEEL_RADIUS, 0])
        hub = RoundedRectangle(width=0.075, height=0.03, corner_radius=0.012).move_to([x, WHEEL_RADIUS, 0])
        return [outlined(tread, TYRE_COLOR, ink, w), outlined(hub, c["skin"], ink, w * 0.6)]
    tyre = Circle(radius=WHEEL_RADIUS).move_to([x, WHEEL_RADIUS, 0])
    hub = Circle(radius=0.45 * WHEEL_RADIUS).move_to([x, WHEEL_RADIUS, 0])
    return [outlined(tyre, TYRE_COLOR, ink, w), outlined(hub, c["skin"], ink, w * 0.6), filled(Circle(radius=0.012).move_to([x, WHEEL_RADIUS, 0]), ink)]


def chest_panel(f: Frame, c: Mapping[str, str], w: float) -> list[VMobject]:
    """A dark panel with three small lights on the chest (side view: on the front half)."""
    p, ink = f.p, c["outline"]
    y = f.body_bottom + 0.6 * p.body_height
    x, width = (0.0, 0.42 * p.body_width) if f.front else (0.17 * p.body_width, 0.3 * p.body_width)
    panel = outlined(RoundedRectangle(width=width, height=0.22 * p.body_height, corner_radius=0.02).move_to([x, y, 0]), SCREEN_COLOR, ink, w * 0.75)
    lights = [outlined(Circle(radius=0.016).move_to([x + k * width / 3.6, y, 0]), color, ink, w * 0.4)
              for k, color in zip((-1, 0, 1), (c["accessory"], SCREEN_GLOW, AMBER))]
    return [panel, *lights]


__all__ = [
    "AMBER",
    "BOX_HEAD",
    "JOINT_RADIUS",
    "SCREEN_COLOR",
    "SCREEN_GLOW",
    "TYRE_COLOR",
    "WHEEL_RADIUS",
    "antenna_part",
    "chest_panel",
    "face_colors",
    "foot",
    "hand",
    "has_screen",
    "head",
    "head_top",
    "is_robot",
    "joint",
    "limb_colors",
    "screen_eye",
    "wheel",
]
