"""Step 172: weather on an iso place (DESIGN.md §90) — shelter from rain under roofs, crowns and
bridges, puddles with ripples, settling snow on the place's tops, and speed lines along a walk's
diagonal; a tiny render of it."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from test_cartoon_acting import figure
from test_iso_staging import iso_project, looks, pond
from vidgen.cartoon.iso_drawing import Blobs, IsoCanvas, Line, Poly, draw_shapes, surface_normal, upward
from vidgen.cartoon.iso_objects import ObjectLook, object_shapes
from vidgen.cartoon.iso_scenery import WATER_DEPTH, IsoColors
from vidgen.cartoon.iso_stage import IsoScenery, iso_view
from vidgen.cartoon.iso_weather import (
    MAX_PUDDLES,
    SHELTER_CLEARANCE,
    iso_puddles,
    lift_floors,
    puddle_cells,
    ripples,
    top_surface,
    world_at,
)
from vidgen.cartoon.rain import IsoRainGround, RainGround, landing_lines
from vidgen.scenes.stage_iso import iso_particle_problem
from vidgen.world.iso import ObjectPlacing, parse_iso_map, place_objects
from vidgen.world.iso_view import ISO_RISE, iso_point

FW, FH = 8 * 16 / 9, 8.0
VILLAGE = """
..........
.h........
..........
..........
.....t....
..........
.~~.......
"""


def village():   # type: ignore[no-untyped-def]
    place = parse_iso_map(VILLAGE, names={"h": "home", "t": "oak"})
    return place_objects(place, [ObjectPlacing("house", "home"), ObjectPlacing("tree", "oak"), ObjectPlacing("bridge", (2, 7), facing="right", size=(2, 1))])


def scenery(place):   # type: ignore[no-untyped-def]
    return IsoScenery(place, IsoColors(), looks(place), iso_view(place, FW, FH), 20.0)


# ----- what faces up (no manim) --------------------------------------------------------------------


def test_tops_and_roof_slopes_face_up_walls_do_not() -> None:
    top = Poly(((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#888888")
    wall = Poly(((0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#888888")
    slope = Poly(((0.0, 0.0, 2.0), (1.0, 0.0, 2.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#888888")
    assert upward(top) == pytest.approx((0.0, 0.0, 1.0))
    assert upward(wall) is None and surface_normal(wall.points) is not None
    assert upward(slope) is not None and upward(slope)[1] > 0   # faces the viewer's lower left
    assert surface_normal(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))) is None


# ----- shelter from rain (no manim) ----------------------------------------------------------------


def test_the_top_surface_has_roofs_crowns_and_the_bridge_over_the_ground() -> None:
    place = village()
    surface = scenery(place).top_surface()
    open_grass = surface.top_z(np.array([8.5]), np.array([1.5]))[0]
    assert open_grass == pytest.approx(0.0)
    roof = surface.top_z(np.array([2.5]), np.array([2.5]))[0]   # the middle of the house: its ridge
    assert roof > 4.0
    crown = surface.top_z(np.array([5.5]), np.array([4.5]))[0]
    assert crown > 3.0
    water = surface.ground_z(np.array([1.5]), np.array([6.5]))[0]
    assert water == pytest.approx(-WATER_DEPTH)
    deck = surface.top_z(np.array([1.5]), np.array([6.5]))[0]
    assert deck == pytest.approx(0.22, abs=0.02)   # the bridge's deck over the stream
    assert surface.sheltered(np.array([1.5, 8.5, 2.5]), np.array([6.5, 1.5, 2.5]), np.array([-WATER_DEPTH, 0.0, 0.0])).tolist() == [True, False, True]
    assert surface.top_z(np.array([-1.0]), np.array([2.0]))[0] == -math.inf   # outside the place
    # nobody stands under a shelter: the cells next to the house and the tree are dry in the middle
    for c, r in ((4, 2), (1, 4), (6, 4), (5, 5), (4, 3), (6, 5)):
        assert not surface.sheltered(np.array([c + 0.5]), np.array([r + 0.5]), 0.0)[0]


def test_world_at_undoes_the_projection() -> None:
    u, v = iso_point(3.2, 1.7, 0.5)
    x, y = world_at(np.array([u]), np.array([v]), 0.5)
    assert (x[0], y[0]) == pytest.approx((3.2, 1.7))


def test_a_drop_lands_on_the_roof_or_the_crown_not_under_it() -> None:
    surface = scenery(village()).top_surface()
    points = [(2.5, 2.5, 0.0), (5.5, 4.5, 0.0), (8.5, 1.5, 0.0), (1.5, 6.5, -WATER_DEPTH)]   # under the roof, the crown, open, the bridge
    u = np.array([iso_point(*p)[0] for p in points])
    v = np.array([iso_point(*p)[1] for p in points])
    lift = lift_floors(u, v, surface)
    assert lift[0] / ISO_RISE > 4.0 and lift[1] / ISO_RISE > 2.5   # up to the roof and the crown
    assert lift[2] == 0.0
    assert lift[3] / ISO_RISE == pytest.approx(0.22 + WATER_DEPTH, abs=0.03)   # on the bridge's deck


def test_iso_rain_ground_lands_drops_on_what_shelters() -> None:
    shares = np.array([0.0, 0.5, 1.0])
    x = np.array([0.0, 0.0, 0.0])
    plain = IsoRainGround(-4.0, -4.0, 4.0, 8.0, (), (-1.0, 1.0), (-2.0, -2.0), (2.0, 2.0))
    lifted = IsoRainGround(-4.0, -4.0, 4.0, 8.0, (), (-1.0, 1.0), (-2.0, -2.0), (2.0, 2.0), lift=lambda x, y: np.where(y > 0, 0.5, 0.0))
    assert plain.landing(shares, x).tolist() == [-2.0, 0.0, 2.0]
    assert lifted.landing(shares, x).tolist() == [-2.0, 0.0, 2.5]
    flat = RainGround(-2.0, -2.2, -1.0, 8.0)   # a plain stage: the band, as before
    assert np.array_equal(flat.landing(shares, x), landing_lines(shares, flat))


# ----- puddles (no manim) --------------------------------------------------------------------------


def test_puddles_lie_on_open_ground_in_front_of_everything() -> None:
    place = village()
    view = scenery(place)
    surface = view.top_surface()
    boxes = [piece.box for piece in view.pieces]
    cells = puddle_cells(place, surface, boxes)
    assert (8, 1) in cells and (5, 6) in cells
    assert (1, 6) not in cells and (2, 2) not in cells and (5, 4) not in cells   # water, the house, the tree
    assert (1, 0) not in cells   # behind the house: it would cover it
    puddles = iso_puddles(place, surface, boxes, seed=3)
    assert 2 <= len(puddles) <= MAX_PUDDLES and puddles == iso_puddles(place, surface, boxes, seed=3)
    assert puddles != iso_puddles(place, surface, boxes, seed=4)
    for puddle in puddles:
        c, r = math.floor(puddle.x), math.floor(puddle.y)
        assert (c, r) in cells and c < puddle.x - puddle.radius + 1e-9 and puddle.x + puddle.radius < c + 1 + 1e-9
    assert [p.x + p.y for p in puddles] == sorted(p.x + p.y for p in puddles)   # back to front


def test_ripples_spread_and_fade_and_start_again() -> None:
    (puddle,) = iso_puddles(parse_iso_map("."), top_surface(parse_iso_map("."), []), [], seed=1)[:1]
    rings = [ripples(puddle, t) for t in np.linspace(0.0, 3.0, 31)]
    assert all(len(r) == 2 for r in rings)
    assert all(ring.radius <= puddle.radius and math.hypot(ring.dx, ring.dy) < puddle.radius for r in rings for ring in r)
    first = [r[0] for r in rings]
    assert any(b.radius < a.radius for a, b in zip(first, first[1:]))   # a ring starts again
    assert ripples(puddle, 1.3) == ripples(puddle, 1.3)
    assert all(ring.opacity == 0.0 for ring in ripples(puddle, 1.0, size=0.0))


def test_puddles_and_settling_snow_are_no_longer_refused_outdoors() -> None:
    class Iso:
        place = "outdoor"

    class Settings:
        puddles = True
        settle = True

    assert iso_particle_problem(Iso(), "rain", Settings()) is None
    assert iso_particle_problem(Iso(), "snow", Settings()) is None
    Iso.place = "indoor"
    assert "outdoors" in (iso_particle_problem(Iso(), "rain", Settings()) or "")


# ----- settling snow drawn (no manim) --------------------------------------------------------------


def test_the_snow_lies_on_tops_and_crowns_and_is_hidden_by_what_is_in_front() -> None:
    canvas = IsoCanvas(40.0, -1.5, -2.0, 120, 140)
    top = Poly(((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#3366AA")
    side = Poly(((0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#224477")
    water = Poly(((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0)), "#7CC7EA", holds_snow=False)
    snow = np.asarray(draw_shapes([side, top], canvas, snow=True))

    def at(point: tuple[float, float, float]) -> np.ndarray:
        x, y = canvas.pixel(point)
        return snow[int(y), int(x)]

    assert at((0.5, 0.5, 1.0))[3] == 255 and at((0.5, 0.5, 1.0))[:3].min() > 230   # white on the top
    assert at((0.5, 1.0, 0.5))[3] == 0   # none on the side
    assert np.asarray(draw_shapes([water], canvas, snow=True))[..., 3].max() == 0
    front = Poly(((0.7, 1.2, 0.0), (1.7, 1.2, 0.0), (1.7, 1.2, 3.0), (0.7, 1.2, 3.0)), "#000000")   # a wall standing in front of it
    hidden = np.asarray(draw_shapes([top, front], canvas, snow=True))
    x, y = canvas.pixel((0.5, 0.5, 1.0))
    assert hidden[int(y), int(x), 3] == 0   # a wall in front of it hides it
    ball = Blobs(((0.5, 0.5, 1.0),), (0.6,), "#2F6B3A")
    capped = np.asarray(draw_shapes([ball], canvas, snow=True))
    x, y = canvas.pixel((0.5, 0.5, 1.0))
    r = 0.6 * canvas.scale
    assert capped[int(y - 0.8 * r), int(x), 3] > 200 and capped[int(y + 0.5 * r), int(x), 3] == 0   # a cap on top only
    thin = np.asarray(draw_shapes([top, Line(((0.0, 0.5, 1.0), (1.0, 0.5, 1.0)), "#000000", 0.6)], canvas, snow=True))
    assert np.array_equal(thin, np.asarray(draw_shapes([top], canvas, snow=True)))   # a seam is covered


def test_a_pine_and_a_well_roof_get_a_cap_and_the_picture_itself_is_unchanged() -> None:
    from vidgen.world.iso import IsoObject

    look = ObjectLook("#81B29A", "#8A5A3C")
    pine = object_shapes(IsoObject("pine_1", "pine", 0, 0, 1, 1, 4.2), look, 0.0)
    tiers = [s for s in pine if isinstance(s, Poly) and s.snow_cap > 0]
    assert len(tiers) == 3
    canvas = IsoCanvas(40.0, -1.0, -3.0, 80, 160)
    snow = np.asarray(draw_shapes(pine, canvas, snow=True))
    x, y = canvas.pixel((0.5, 0.5, 4.0))
    assert snow[int(y), int(x), 3] == 255   # the tip is white
    plain = np.asarray(draw_shapes(pine, canvas))
    assert np.array_equal(plain, np.asarray(draw_shapes([Poly(s.points, s.fill, s.ink, s.glow) if isinstance(s, Poly) else s for s in pine], canvas)))


def test_the_scenery_draws_a_picture_of_its_snow() -> None:
    place = village()
    view = scenery(place)
    _, snow = view.picture(view.base(), snow=True)
    _, whole = view.picture(view.base())
    pixels, base = np.asarray(snow), np.asarray(whole)
    assert pixels.shape == base.shape and (pixels[..., 3] > 0).sum() > 0.3 * (base[..., 3] > 0).sum()


# ----- speed lines along the diagonal (manim, no render) -----------------------------------------


def test_speed_lines_on_an_iso_place_go_along_the_walk() -> None:
    from vidgen.cartoon.motion_effect_shapes import MotionEffect
    from vidgen.cartoon.motion_effects import MotionEffectCue

    flat = figure()
    lines = MotionEffect(MotionEffectCue("speed_lines", 0.0, 1.0), flat, delay=0.0, seed=3)
    lines.update(0.5)
    ahead, _ = lines._way()
    assert ahead.tolist() == [1.0, 0.0]   # a plain stage: level, the way it faces

    walker = figure()
    walker.iso_feet = (1.0, 1.0, 0.0)
    lines = MotionEffect(MotionEffectCue("speed_lines", 0.0, 1.0), walker, delay=0.0, seed=3)
    lines.update(0.1)
    for step in range(1, 6):   # down the map's column: to the lower right on screen
        walker.iso_feet = (1.0 + 0.1 * step, 1.0, 0.0)
        lines.update(0.1)
    ahead, back = lines._way()
    assert ahead == pytest.approx(np.array([2.0, -1.0]) / math.sqrt(5.0))
    assert lines.family_members_with_points()
    trail = lines.get_center()
    assert trail[1] > back[1] and trail[0] < back[0]   # behind it, up the diagonal


# ----- a tiny render ------------------------------------------------------------------------------


@pytest.mark.render
def test_rain_with_puddles_and_settling_snow_render_on_the_place(make_project, tmp_path: Path) -> None:
    from test_cartoon_stage import render_with_layout
    from vidgen.cartoon.iso_pictures import IsoPuddles

    beats = [
        {"text": "It rains on the pond and puddles grow on the grass.", "actions": [{"particles": "rain", "puddles": True, "keep": True}]},
        {"text": "Then it snows, and the snow lies on the table and the well.", "actions": [{"particles": "snow", "settle": True, "settled": 30}]},
    ]
    project = iso_project(make_project, beats)
    scene, _ = render_with_layout(project, "pond", tmp_path / "media")
    puddles = [p for p in scene.puddles if isinstance(p, IsoPuddles)]
    assert len(puddles) == 1 and puddles[0].puddles
    assert scene.iso_snow.cover == pytest.approx(0.97)
    base = next(m for m in scene._iso_groups if m.name == "iso_place")
    assert base.snow_opacity == pytest.approx(0.97)
