"""Step 126: snow that settles (a layer growing in steps on the ground and on props' top lines,
flakes landing there) and fog in bands between the things by depth (DESIGN.md §69.60)."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from test_cartoon_living import frames_of, room_project
from test_cartoon_rain import OrderRecorder, drawn_between
from test_cartoon_stage import render_with_layout, stage_params
from test_particles import fake_scene
from vidgen.cartoon.fog import (
    FOG_DEPTHS,
    FOG_DRIFT,
    FOG_FEATHER,
    FOG_LAYER_SHARES,
    FOG_THICKNESS,
    band_box,
    band_opacities,
    band_outlines,
    fog_cover,
    fog_shift,
    layer_opacity,
)
from vidgen.cartoon.rain import SHELTER_REACH, ShelterBox, rain_ground
from vidgen.cartoon.snow import (
    BLANKET_RISE,
    CAP_SHARE,
    CAP_THICKNESS,
    COVER_SHARE,
    FLAKE_REST,
    LUMP_DEPTH,
    SETTLE_SECONDS,
    SETTLE_STEP,
    TopLine,
    bare_patches,
    blanket_cover,
    blanket_outline,
    cap_full_thickness,
    cap_outlines,
    cap_thickness,
    curve_segments,
    flake_floors,
    rest_flakes,
    settle_amount,
    settled_seconds,
    top_line,
)
from vidgen.cartoon.weather_drawing import FogBand, SettledSnow, SnowBlanket, SnowCap, StageFog, polygon_points
from vidgen.cli import check_project
from vidgen.particle_field import ParticleSettings, particle_field

FRAME_HEIGHT = 9.0


def signed_area(corners: np.ndarray) -> float:
    """Shoelace area: above 0 for corners counter-clockwise."""
    x, y = corners[:, 0], corners[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# ----- settling (no manim) -------------------------------------------------------------------------------


def test_the_layer_grows_in_steps_with_the_snowfall_and_stays() -> None:
    assert settled_seconds(3.74, 1.0, None) == pytest.approx(2.5)   # 2.74 s of snow, in 0.5 s steps
    assert settled_seconds(3.74, 1.0, None, settled=10.0) == pytest.approx(12.5)
    assert settled_seconds(20.0, 1.0, 4.2) == pytest.approx(3.0)   # it stopped at 4.2: the layer stays
    assert settled_seconds(0.5, 1.0, None) == 0.0 and settled_seconds(math.inf, 1.0, None) == math.inf
    times = np.linspace(0.0, 40.0, 401)
    amounts = [settle_amount(settled_seconds(t, 0.0, None)) for t in times]
    assert amounts == sorted(amounts) and amounts[0] == 0.0 and amounts[-1] == 1.0
    assert len(set(amounts)) == SETTLE_SECONDS / SETTLE_STEP + 1   # one value per step until full
    assert settle_amount(SETTLE_SECONDS / 2) == pytest.approx(0.5) and settle_amount(SETTLE_SECONDS / 4, density=2.0) == pytest.approx(0.5)
    assert settle_amount(math.inf) == 1.0 and settle_amount(-1.0) == 0.0
    assert blanket_cover(0.0) == 0.0 and blanket_cover(COVER_SHARE / 2) == pytest.approx(0.5) and blanket_cover(0.9) == 1.0


def test_the_blanket_covers_the_ground_area_rising_in_lumps() -> None:
    rise = BLANKET_RISE * FRAME_HEIGHT
    outline = blanket_outline(-8.0, 8.0, -4.5, -2.16, rise, FRAME_HEIGHT, seed=3)
    assert signed_area(outline) > 0   # counter-clockwise: it fills
    assert outline[:2].tolist() == [[-8.0, -4.5], [8.0, -4.5]]
    edge = outline[2:, 1]
    assert (edge >= -2.16 + rise * (1 - LUMP_DEPTH) - 1e-9).all() and (edge <= -2.16 + rise * (1 + LUMP_DEPTH) + 1e-9).all()
    assert np.ptp(edge) > 0.5 * rise   # lumpy, not flat
    assert np.array_equal(outline, blanket_outline(-8.0, 8.0, -4.5, -2.16, rise, FRAME_HEIGHT, seed=3))
    assert not np.array_equal(outline, blanket_outline(-8.0, 8.0, -4.5, -2.16, rise, FRAME_HEIGHT, seed=4))
    flat = blanket_outline(-8.0, 8.0, -4.5, -2.16, 0.0, FRAME_HEIGHT, seed=3)
    assert np.allclose(flat[2:, 1], -2.16)
    [patch] = bare_patches([ShelterBox(left=1.0, right=3.0, top=2.0, feet=-2.7)])
    assert signed_area(patch) < 0   # clockwise: a hole in the blanket
    assert patch[:, 0].min() == pytest.approx(1.2) and patch[:, 0].max() == pytest.approx(2.8)
    assert patch[:, 1].mean() == pytest.approx(-2.7, abs=1e-9)


def house_points() -> np.ndarray:
    """A house's outline as Manim cubic points: a wall 4 wide and 2 tall, a roof up to 3.5, and a
    window inside the wall."""
    wall = polygon_points(np.array([[-2.0, 0.0], [2.0, 0.0], [2.0, 2.0], [-2.0, 2.0]]))
    roof = polygon_points(np.array([[-2.4, 2.0], [2.4, 2.0], [0.0, 3.5]]))
    window = polygon_points(np.array([[-1.0, 0.8], [-0.2, 0.8], [-0.2, 1.6], [-1.0, 1.6]]))
    return np.concatenate([wall, roof, window])


def test_a_top_line_follows_the_upper_edge_of_a_drawing() -> None:
    xs, ys = top_line(curve_segments(house_points()), columns=24)
    assert xs[0] == pytest.approx(-2.4) and xs[-1] == pytest.approx(2.4) and np.all(np.diff(xs) > 0)
    roof = 2.0 + 1.5 * (1 - np.abs(xs) / 2.4)   # the roof's slopes, never the window or the wall below
    assert np.allclose(ys, roof, atol=0.08)
    assert ys.max() == pytest.approx(3.5, abs=0.1)
    legs = [np.array([[-1.0, 0.0], [-0.9, 0.0], [-0.9, 1.0], [-1.0, 1.0]]), np.array([[0.9, 0.0], [1.0, 0.0], [1.0, 1.0], [0.9, 1.0]])]
    top = np.array([[-1.2, 1.0], [1.2, 1.0], [1.2, 1.1], [-1.2, 1.1]])
    xs, ys = top_line(curve_segments(np.concatenate([polygon_points(c) for c in [*legs, top]])))
    assert np.allclose(ys, 1.1)   # a table: its top, flat
    xs, ys = top_line(curve_segments(np.concatenate([polygon_points(c) for c in legs])), columns=10)
    assert np.allclose(ys, 1.0)   # two legs: the gap between them takes their height


def test_caps_lie_where_the_top_line_is_flat_enough() -> None:
    xs = np.linspace(-2.0, 2.0, 21)
    ys = np.where(np.abs(xs) < 1.0, 2.0, 2.0 - 3.0 * (np.abs(xs) - 1.0))   # a flat top between two steep sides
    thick = cap_thickness(xs, ys, full=0.2, amount=0.5)
    assert thick[np.abs(xs) < 0.7].tolist() == pytest.approx([0.1] * int(np.sum(np.abs(xs) < 0.7)))
    assert (thick[np.abs(xs) > 1.15] == 0).all() and (thick >= 0).all()
    assert np.allclose(cap_thickness(xs, ys, 0.2, 1.0), 2 * thick) and not cap_thickness(xs, ys, 0.2, 0.0).any()
    [cap] = cap_outlines(xs, ys, thick)
    assert signed_area(cap) > 0
    assert cap[:, 1].max() == pytest.approx(2.1) and cap[:, 1].min() >= 2.0 - 0.1 * 0.5 - 1e-9   # on the line, sunk a little
    assert cap_outlines(xs, ys, np.where(np.abs(xs - 0.0) < 0.3, 0.0, thick)).__len__() == 2   # a dip splits it
    assert cap_full_thickness(9.0, 0.0, 10.0) == pytest.approx(CAP_THICKNESS * 9.0)
    assert cap_full_thickness(9.0, 1.0, 10.0) < cap_full_thickness(9.0, 0.0, 10.0)   # smaller further back
    assert cap_full_thickness(9.0, 0.0, 0.5) == pytest.approx(CAP_SHARE * 0.5)   # never thicker than a share of a small prop


def test_flakes_stop_on_top_lines_and_shelters_and_lie_there_a_moment() -> None:
    house = TopLine(np.array([-3.0, 0.0, 3.0]), np.array([1.0, 2.0, 1.0]), feet=-2.2)
    umbrella = ShelterBox(left=4.0, right=6.0, top=0.0, feet=-2.7)
    ground = rain_ground(0.2, 0.26, FRAME_HEIGHT, [house, umbrella])
    x = np.array([0.0, 1.5, 1.5, 5.0, 7.0])
    landing = np.array([-2.16, -2.3, -2.2 - SHELTER_REACH * FRAME_HEIGHT - 0.1, -2.6, -2.5])
    floors = flake_floors(x, landing, ground)
    assert floors.tolist() == pytest.approx([2.0, 1.5, landing[2], 0.0, -2.5])
    # on the ridge; on a slope; in front of the house; on the umbrella; on the ground
    shown, lift = rest_flakes(np.array([1.0, -0.1, -0.5, -2.0]), np.zeros(4), np.full(4, 1.0))
    assert shown.tolist() == pytest.approx([1.0, 1.0 - 0.1 / FLAKE_REST, 0.0, 0.0])   # falling, lying and fading, gone
    assert lift.tolist() == pytest.approx([0.0, 0.1, 0.0, 0.0])   # a lying flake sits on its floor


# ----- fog (no manim) --------------------------------------------------------------------------------------


def test_fog_thickens_with_depth_and_density() -> None:
    depths = np.linspace(0.0, 1.0, 51)
    covers = [fog_cover(d, 0.5) for d in depths]
    assert covers == sorted(covers) and covers[0] == 0.0 and fog_cover(0.2, 0.5) == 0.0   # nothing in front of the first band
    assert fog_cover(0.5, 0.5) == pytest.approx(1 - math.exp(-FOG_THICKNESS * 0.5 * 0.4))   # behind the bands at 0.4 and 0.2
    assert fog_cover(math.inf, 0.5) == pytest.approx(1 - math.exp(-FOG_THICKNESS * 0.5))   # the sky: behind every band
    assert fog_cover(0.7, 1.0) > fog_cover(0.7, 0.5) > fog_cover(0.7, 0.2)
    assert 0 < fog_cover(0.7, 0.5, high=True) < fog_cover(0.7, 0.5)   # thinner above the banks
    opacities = band_opacities(0.5)
    assert len(opacities) == len(FOG_DEPTHS) and all(0 < a < 1 for a in opacities)
    for opacity in opacities:   # a band's layers add up to its opacity where they overlap
        seen = np.prod([1 - layer_opacity(opacity, share) for share in FOG_LAYER_SHARES])
        assert 1 - seen == pytest.approx(opacity)


def test_fog_bands_lie_on_their_ground_lines_and_drift() -> None:
    for index, depth in enumerate(FOG_DEPTHS):
        layers = band_outlines(index, 0.2, -8.0, 8.0, FRAME_HEIGHT, shift=0.0, seed=1)
        base = (0.2 + 0.12 * depth - 0.5) * FRAME_HEIGHT
        assert len(layers) == len(FOG_LAYER_SHARES) and all(signed_area(layer) > 0 for layer in layers)
        bottoms = [layer[0, 1] for layer in layers]
        assert bottoms == sorted(bottoms) and bottoms[-1] == pytest.approx(base)   # the taller layers reach lower
        assert bottoms[0] == pytest.approx(base - 2 * FOG_FEATHER * FRAME_HEIGHT)
        assert layers[0][:, 1].max() == pytest.approx(FRAME_HEIGHT / 2)   # the haze up to the frame's top
        box = band_box(index, 0.2, -8.0, 8.0, FRAME_HEIGHT)
        for shift in (0.0, 0.7, 3.1):
            for layer in band_outlines(index, 0.2, -8.0, 8.0, FRAME_HEIGHT, shift=shift, seed=1):
                assert box[1] - 1e-9 <= layer[:, 1].min() and layer[:, 1].max() <= box[3] + 1e-9
    still, moved = (band_outlines(2, 0.2, -8.0, 8.0, FRAME_HEIGHT, shift=s, seed=1)[1] for s in (0.0, 0.3))
    assert not np.allclose(still, moved)   # the waves drift
    assert np.allclose(still, band_outlines(2, 0.2, -8.0, 8.0, FRAME_HEIGHT, shift=0.0, seed=1)[1])   # seeded
    assert fog_shift(10.0, 0.0, 0.2) > fog_shift(10.0, 0.0, 1.0) == pytest.approx(10 * FOG_DRIFT)   # nearer bands faster
    assert fog_shift(10.0, 2.0, 1.0) > fog_shift(10.0, 0.0, 1.0) and fog_shift(10.0, 0.0, 1.0, drift=0.0) == 0.0


# ----- drawing objects (manim, no render) -------------------------------------------------------------------


def test_the_settled_snow_redraws_only_when_a_step_passes() -> None:
    clock: dict[str, float | None] = {"ended": None}
    cap = SnowCap(np.linspace(-1, 1, 11), np.full(11, 1.0), 0.2, "#FFFFFF", cap_of="table")
    layer = SettledSnow(
        SnowBlanket("#FFFFFF"), [cap], area=(-8.0, 8.0, -4.5, -2.16), frame_height=FRAME_HEIGHT,
        bare=bare_patches([ShelterBox(1.0, 3.0, 2.0, -2.7)]), start=2.0, ended=lambda: clock["ended"], density=1.0, settled=0.0, seed=1,
    )
    cover, thin = layer.blanket.submobjects
    assert layer.amount == 0.0 and len(cover.points) == 0 and len(cap.points) == 0   # nothing at the start
    assert not layer.changing(2.0, 2.4) and layer.changing(2.0, 2.6) and layer.changing(5.0, math.inf)
    layer.update(8.0)
    assert layer.amount == pytest.approx(6.0 / SETTLE_SECONDS) and cover.get_fill_opacity() > 0 and len(cap.points) > 0
    assert thin.get_fill_opacity() == pytest.approx(0.45 * cover.get_fill_opacity())   # thin snow under the tree
    before = cap.points.copy()
    layer.update(8.3)
    assert np.array_equal(cap.points, before)   # the same step
    clock["ended"] = 9.0
    assert layer.done(30.0) and not layer.done(8.6) and layer.amount_at(100.0) == pytest.approx(7.0 / SETTLE_SECONDS)
    box = layer.region(0.0, 1.0)
    assert box[0] == -8.0 and box[1] == -4.5 and box[3] >= 1.2


def test_the_fog_moves_only_when_it_drifts_or_blows() -> None:
    def fog(drift: float, blown: Any = None) -> StageFog:
        return StageFog(density=0.5, color="#DCE2EA", ground=0.2, left=-8.0, right=8.0, frame_height=FRAME_HEIGHT, drift=drift, seed=2, blown=blown)

    drifting, still, blown = fog(1.0), fog(0.0), fog(0.0, blown=lambda now: 0.3 * now)
    assert [b.stage_depth for b in drifting.bands] == list(FOG_DEPTHS)
    assert drifting.changing(0.0, 1.0) and not still.changing(0.0, 1.0) and blown.changing(0.0, 1.0)
    first = drifting.bands[2][1].points.copy()
    drifting.update(5.0)
    assert not np.array_equal(first, drifting.bands[2][1].points)
    band = FogBand(0.4, "#DCE2EA", 0.3)
    assert 1 - np.prod([1 - layer.get_fill_opacity() for layer in band]) == pytest.approx(0.3)
    assert drifting.region(0.0, 1.0)[3] == pytest.approx(FRAME_HEIGHT / 2)


def test_settling_snow_field_lies_on_its_floors() -> None:
    scene = fake_scene(time=0.0)
    house = TopLine(np.array([-4.0, 0.0, 4.0]), np.array([0.0, 1.0, 0.0]), feet=-2.7)
    scene.snow_ground = lambda: rain_ground(0.2, 0.26, FRAME_HEIGHT, [house])
    field = particle_field(scene, "snow", ParticleSettings(settle=True, density=2.0, seed=5))
    plain = particle_field(scene, "snow", ParticleSettings(density=2.0, seed=5))
    assert field.splashes is None and len(field) == len(field.drops) and plain.ground is None and field.ground is not None
    lying = 0
    for now in np.linspace(2.0, 30.0, 57):
        scene.renderer.time = float(now)
        field.update(0.1)
        for flake in field.drops:
            if flake.get_fill_opacity() <= 0:
                continue
            x, bottom = flake.get_bottom()[:2]
            floor = house.top_at(np.array([x]))[0] if abs(x) < 3.5 else -2.7 - 0.05 * FRAME_HEIGHT
            assert bottom > floor - 0.05, (now, x, bottom)   # never through the roof or the ground
            lying += int(flake.get_fill_opacity() < 0.89)
    assert lying > 0   # some lie fading on their floors


# ----- validation -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"particles": [{"kind": "rain", "settle": True}]}, "only snow settles, not rain"),
        ({"particles": [{"kind": "snow", "settled": 10}]}, "settled is for snow that settles: add settle: true"),
        ({"fog": False}, "fog: false is the default; leave fog out"),
        ({"fog": 1.5}, "less than or equal to 1"),
        ({"room": True, "fog": True}, "there is no fog in a room"),
    ],
)
def test_bad_params(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        stage_params(**params)


def test_params(make_project) -> None:
    p = stage_params(fog=True, particles=[{"kind": "snow", "settle": True, "settled": 30}])
    assert p.fog.density == 0.5 and p.fog.drift == 1.0 and p.particles[0].settle and p.particles[0].settled == 30
    assert stage_params(fog=0.8).fog.density == 0.8 and stage_params().fog is None
    beats = [{"text": "Snow.", "actions": [{"particles": "snow", "settle": True}, {"particles": "rain", "settle": True, "at": 0.5}]}]
    problems = check_project(room_project(make_project, {"characters": ["pip"]}, beats))
    assert len(problems) == 1 and "only snow settles, not rain" in problems[0]


# ----- a stage (tiny renders) ---------------------------------------------------------------------------------


SNOWY: dict[str, Any] = {
    "idle": False,
    "props": [{"prop": "house", "at": 0.2, "depth": 0.5}, {"prop": "tree", "at": 0.8, "depth": 0.3}, {"prop": "table", "at": 0.55},
              {"prop": "umbrella", "at": 0.35, "open": True}],
    "characters": [{"name": "pip", "at": 0.45, "depth": 0.1}],
}
BEATS = [{"text": "Pip waits outside for a little while."}, {"text": "Then the snow begins to fall and to settle."}]


@pytest.mark.render
def test_settling_snow_started_later_changes_nothing_before_it_and_grows_after(make_project, tmp_path: Path, monkeypatch) -> None:
    """Every frame before the snow starts is the same, pixel for pixel, as without it; then the
    blanket lies on the ground under pip and a cap right after the house, the table and the tree,
    none on the umbrella; the layout dump leaves them out."""
    from vidgen import extensions, registry

    extensions.load_builtins()
    monkeypatch.setattr(registry.get("stage").cls, "outro", 0)
    plain, before = frames_of(room_project(make_project, SNOWY, BEATS), tmp_path / "plain", monkeypatch)
    assert plain.snow_layers == [] and plain.fog is None
    snowing = [BEATS[0], {**BEATS[1], "actions": [{"particles": "snow", "settle": True, "settled": 20, "keep": True}]}]
    scene, after = frames_of(room_project(make_project, SNOWY, snowing), tmp_path / "snow", monkeypatch)
    start = round(scene.beat_log[1].start * 5)
    assert len(after) == len(before) and 5 < start < len(after) - 3
    assert all(np.array_equal(a, b) for a, b in zip(after[:start], before[:start]))
    assert not np.array_equal(after[-1], before[-1])
    [layer] = scene.snow_layers
    assert layer.amount > 20 / SETTLE_SECONDS - 1e-9 and sorted(cap.cap_of for cap in layer.caps) == ["house", "table", "tree"]
    order = scene.mobjects
    band = next(m for m in order if getattr(m, "name", None) == "ground")
    assert drawn_between(order, band, layer.blanket, scene.cast["pip"])
    for cap in layer.caps:
        assert order.index(cap) == order.index(scene.props[cap.cap_of]) + 1
    _, objects = render_with_layout(room_project(make_project, {**SNOWY, "particles": [{"kind": "snow", "settle": True}]}, BEATS[:1]), "home", tmp_path / "dump")
    assert not any(obj["class"] in ("SnowBlanket", "SnowCap") for obj in objects)


@pytest.mark.render
def test_fog_bands_lie_between_the_things_by_depth(make_project, tmp_path: Path) -> None:
    """Each band is drawn right before the first thing standing at its depth or nearer; a character
    walking from the back to the front ends in front of every band; nothing of the fog is in the
    layout dump."""
    params = {
        "idle": False, "fog": {"density": 0.6},
        "props": [{"prop": "tree", "at": 0.2, "depth": 0.9}, {"prop": "bush", "at": 0.7, "depth": 0.5}],
        "characters": [{"name": "pip", "at": 0.4, "depth": 0.3}, {"name": "kit", "at": 0.8, "depth": 0.7}],
    }
    beats = [{"text": "It is foggy in the park."}, {"text": "Kit comes to the front.", "actions": [{"walk_to": "kit", "to": {"mark": 0.8, "depth": 0.0}}]}]
    recorder = OrderRecorder()
    scene, objects = render_with_layout(room_project(make_project, params, beats), "home", tmp_path / "media", recorder)
    assert not any(obj["class"] == "FogBand" for obj in objects)
    bands = {b.stage_depth: b for b in scene.fog.bands}

    def check(order: list[Any], depths: dict[str, float]) -> None:
        for name, depth in depths.items():
            thing = scene.cast.get(name) or scene.props[name]
            for band_depth, band in bands.items():
                assert (order.index(band) < order.index(thing)) == (depth <= band_depth), (name, band_depth)

    check(recorder.orders[0], {"tree": 0.9, "bush": 0.5, "pip": 0.3, "kit": 0.7})
    check(recorder.orders[-1], {"tree": 0.9, "bush": 0.5, "pip": 0.3, "kit": 0.0})
