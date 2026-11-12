"""The fixed wide view of an iso place (``iso: {wide: fixed}``, DESIGN.md §106): its scale, how it
centres on the ground and the characters, the camera moves over it and lint ``iso_ground``."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout
from vidgen.camera import SmoothFollow
from vidgen.cartoon.iso_stage import (
    ISO_FIXED_SHARES,
    body_box,
    fixed_fill_size,
    fixed_reach,
    fixed_tiles,
    fixed_view,
    iso_stand,
    iso_view,
    on_ground,
    wide_view,
)
from vidgen.cartoon.shots import MAX_SHOT_SCALE, ShotFigure, frame_shot
from vidgen.includes import expand_character_size
from vidgen.lint.cartoon_rules import iso_ground
from vidgen.config import IsoGroundRule
from vidgen.lint.rules import StillContext
from vidgen.project import Project
from vidgen.scenes.stage import Stage, StageIso
from vidgen.world.iso import ISO_CHARACTER_HEIGHT
from vidgen.world.iso_view import ISO_RISE, iso_point

LAND, TALL = (8 * 16 / 9, 8.0), (8.0, 8 * 16 / 9)


def square(n: int, spot: tuple[int, int] | None = None) -> str:
    """An n x n grass map with the spot ``a`` at ``spot`` (column, row; default the middle)."""
    column, row = spot or (n // 2, n // 2)
    return "\n".join("".join("a" if (c, r) == (column, row) else "." for c in range(n)) for r in range(n)) + "\n"


def corners_on_ground(n: int, u: float, v: float, half_u: float, half_v: float) -> bool:
    """Whether every corner of the view lies on the ground of an n x n map (``z`` 0)."""
    for du in (-half_u, half_u):
        for dv in (-half_v, half_v):
            x, y = 2 * (v + dv) + u + du, 2 * (v + dv) - (u + du)
            if not (-1e-6 <= x <= n + 1e-6 and -1e-6 <= y <= n + 1e-6):
                return False
    return True


# ----- the scale ---------------------------------------------------------------------------------


def test_the_fixed_scale_makes_a_character_its_share_of_the_frame_height() -> None:
    for fw, fh in (LAND, TALL):
        for size, share in ISO_FIXED_SHARES.items():
            tiles = fixed_tiles(fw, fh, size)
            assert ISO_CHARACTER_HEIGHT * ISO_RISE / (tiles * fh / fw) == pytest.approx(share)
    assert fixed_tiles(*LAND) == pytest.approx(fixed_tiles(*LAND, "medium")) == pytest.approx(10.887, abs=1e-3)


def test_the_map_size_that_fills_the_frame_per_format_and_size() -> None:
    sizes = {fmt: [fixed_fill_size(fixed_tiles(*frame, s), *frame) for s in ("small", "medium", "large")]
             for fmt, frame in (("16:9", LAND), ("9:16", TALL))}
    assert sizes == {"16:9": [34, 24, 17], "9:16": [23, 16, 12]}   # measured: the cookbook's table
    assert fixed_reach(10.0, *LAND) == pytest.approx(5 * (1 + 2 * 9 / 16))


# ----- centring ----------------------------------------------------------------------------------


def test_on_ground_moves_the_view_onto_the_ground_or_centres_the_place() -> None:
    place = StageIso(map=square(30)).parsed()
    half_u, half_v = 5.0, 5.0 * 9 / 16
    u, v = on_ground(place, *iso_point(1, 1), half_u, half_v)   # by the back corner: moved in
    assert corners_on_ground(30, u, v, half_u, half_v)
    assert (u, v) == pytest.approx(iso_point(fixed_reach(10, *LAND), fixed_reach(10, *LAND)))
    middle = iso_point(15, 15)
    assert on_ground(place, *middle, half_u, half_v) == pytest.approx(middle)   # room enough: as it is
    small = StageIso(map=square(8)).parsed()
    assert on_ground(small, *iso_point(1, 1), half_u, half_v) == pytest.approx(iso_point(4, 4))   # too small: centred


def test_the_fixed_view_keeps_its_scale_and_fills_a_big_map_with_ground() -> None:
    widths = []
    for n in (24, 32, 48):
        place = StageIso(map=square(n)).parsed()
        view = iso_view(place, *LAND)
        tiles = fixed_tiles(*LAND)
        body = body_box(iso_stand(place, "a"), ISO_CHARACTER_HEIGHT)
        width, (x, y) = wide_view(place, view, *LAND, [body], fit="fixed", tiles=tiles)
        assert width == pytest.approx(tiles * view.unit)
        widths.append(width / view.unit)
        u, v = x / view.unit + view.u0, -y / view.unit + view.v0
        assert corners_on_ground(n, u, v, width / view.unit / 2, width * 9 / 16 / view.unit / 2)
    assert widths == pytest.approx([widths[0]] * 3)   # the same number of tiles across whatever the size


def test_a_character_by_the_edge_stays_in_view_and_a_small_place_shows_whole() -> None:
    place = StageIso(map=square(40, (2, 2))).parsed()
    view = iso_view(place, *LAND)
    body = body_box(iso_stand(place, "a"), ISO_CHARACTER_HEIGHT)
    width, (x, y) = fixed_view(place, view, *LAND, fixed_tiles(*LAND), [body])
    left, top, right, bottom = body.picture_bounds()
    u, v = x / view.unit + view.u0, -y / view.unit + view.v0
    half_u, half_v = width / view.unit / 2, width * 9 / 16 / view.unit / 2
    assert u - half_u <= left and right <= u + half_u and v - half_v <= top - 0.0 and bottom <= v + half_v
    tiny = StageIso(map=square(6)).parsed()
    tiny_view = iso_view(tiny, *LAND)
    assert fixed_view(tiny, tiny_view, *LAND, 40.0) == (pytest.approx(LAND[0]), (pytest.approx(0.0), pytest.approx(0.0)))


def test_the_other_wide_views_are_unchanged() -> None:
    place = StageIso(map=square(12)).parsed()
    view = iso_view(place, *LAND)
    assert wide_view(place, view, *LAND, fit="auto")[0] < LAND[0]
    with pytest.raises(ValueError, match="needs tiles"):
        wide_view(place, view, *LAND, fit="fixed")


# ----- the setting -------------------------------------------------------------------------------


def test_wide_fixed_and_tiles_parse_and_give_the_tiles() -> None:
    fixed = StageIso(map=square(8), wide="fixed")
    assert fixed.fixed and fixed.wide_fit() == "fixed"
    assert fixed.view_tiles(*LAND, "large") == pytest.approx(fixed_tiles(*LAND, "large"))
    tiles = StageIso(map=square(8), wide={"tiles": 9})
    assert tiles.fixed and tiles.view_tiles(*TALL) == 9.0
    old = StageIso(map=square(8), wide=2.0)
    assert not old.fixed and old.wide_fit() == 2.0 and old.view_tiles(*LAND) is None
    with pytest.raises(ValidationError):
        StageIso(map=square(8), wide={"tiles": 1})


def test_character_size_is_taken_by_the_fixed_view_only() -> None:
    params = Stage.Params(iso={"map": square(8), "wide": "fixed"}, character_size="large")
    assert params.character_size == "large"
    for iso, words in (({}, "or iso: {wide: fixed}"), ({"wide": {"tiles": 9}}, "tiles set the view's scale")):
        with pytest.raises(ValidationError, match="remove character_size") as caught:
            Stage.Params(iso={"map": square(8), **iso}, character_size="large")
        assert words in str(caught.value)
    with pytest.raises(ValidationError, match="remove size"):
        Stage.Params(iso={"map": square(8), "wide": "fixed"}, size=0.3)


def test_the_videos_character_size_reaches_fixed_iso_scenes() -> None:
    data = {"character_size": "large", "scenes": [
        {"type": "stage", "params": {"iso": {"map": "..\n", "wide": "fixed"}}},
        {"type": "stage", "params": {"iso": {"map": "..\n"}}},
        {"type": "stage", "params": {"iso": {"map": "..\n", "wide": {"tiles": 9}}}},
    ]}
    out, _ = expand_character_size(data, {})
    assert [s["params"].get("character_size") for s in out["scenes"]] == ["large", None, None]


# ----- camera moves over it ----------------------------------------------------------------------


def test_shots_and_follows_may_go_past_the_old_cap() -> None:
    small = ShotFigure("pip", 0.0, 0.0, 0.1)   # a character small on a big map
    assert frame_shot("closeup", [small], frame_width=LAND[0], frame_height=8.0, bounds=(-7.2, 7.2, -4, 4)).scale == MAX_SHOT_SCALE
    closer = frame_shot("closeup", [small], frame_width=LAND[0], frame_height=8.0, bounds=(-7.2, 7.2, -4, 4), max_scale=4 * MAX_SHOT_SCALE)
    assert closer.scale > MAX_SHOT_SCALE


def test_a_follow_settles_on_the_ground() -> None:
    moved = []

    def settle(width: float, center: tuple[float, float]) -> tuple[float, float]:
        moved.append(width)
        return center[0] - 0.5, center[1]

    follow = SmoothFollow(lambda: 0.0, lambda: (-0.2, 0.2), settle=settle)
    x, _ = follow.view_center((0.0, 0.0), 10.0, 4.0, 2.25, (-10, 10, -10, 10))
    assert moved and x == pytest.approx(-0.5, abs=0.05)
    plain = SmoothFollow(lambda: 0.0, lambda: (-0.2, 0.2))
    assert plain.view_center((0.0, 0.0), 10.0, 4.0, 2.25, (-10, 10, -10, 10))[0] == pytest.approx(0.0)


# ----- lint iso_ground ---------------------------------------------------------------------------


def ground_issues(data: dict, width: int = 270, height: int = 480, **settings: object) -> list:
    ctx = StillContext({"width": width, "height": height}, {"iso_ground": data}, [])
    return list(iso_ground(ctx, IsoGroundRule(**settings)))


def test_lint_names_the_map_size_that_fills_the_frame() -> None:
    small = {"view": "fixed", "place": "outdoor", "map": [12, 12], "size": "medium", "tiles": 3.44, "need": 16}
    [issue] = ground_issues(small)
    assert issue.severity is None and issue.value == 12 and issue.limit == 16
    assert "this 12x12 place shows the background around it in 9:16 at character_size medium" in issue.message
    assert "at least 16x16 fills the frame" in issue.message
    assert ground_issues({**small, "map": [16, 20]}) == []
    [tiles] = ground_issues({**small, "view": "tiles", "tiles": 8, "need": 17}, 480, 270)
    assert "in 16:9 at tiles 8" in tiles.message


def test_lint_hints_quietly_at_the_whole_place_view_outdoors() -> None:
    auto = {"view": "auto", "place": "outdoor", "map": [12, 12], "size": "medium", "tiles": 10.89, "need": 24}
    [hint] = ground_issues(auto, 480, 270)
    assert hint.severity == "info" and "iso: {wide: fixed}" in hint.message and "24x24" in hint.message
    [big] = ground_issues({**auto, "map": [30, 30]}, 480, 270)
    assert "this map is big enough" in big.message
    assert ground_issues(auto, 480, 270, hint=False) == []
    assert ground_issues({**auto, "place": "indoor"}) == [] and ground_issues({**auto, "view": "number"}) == []


# ----- rendered ----------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.render
def test_the_fixed_view_renders_at_its_scale(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    iso = {"map": square(24), "spots": {"a": "mid"}, "wide": "fixed"}
    beats = [{"text": "Here.", "id": "b1"}, {"text": "Closer now.", "id": "b2", "actions": [{"zoom": "pip", "scale": 2, "hold": True}]}]
    scenes = [{"id": "green", "type": "stage", "params": {"idle": False, "background": "#FF00FF", "iso": iso,
                                                            "characters": [{"name": "pip", "at": "mid"}]}, "beats": beats}]
    project = Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "green", tmp_path / "media", recorder)
    first = [frame for frame in recorder.frames if frame["beat"] == "b1"][-1]
    base = scene.zoom_base()
    assert first["camera"]["zoom"] == pytest.approx(base, rel=1e-3) and base > 2
    assert first["iso_ground"]["view"] == "fixed" and first["iso_ground"]["need"] == fixed_fill_size(fixed_tiles(*LAND), *LAND)
    zoomed = max(frame["camera"]["zoom"] for frame in recorder.frames if frame["beat"] == "b2")
    assert zoomed == pytest.approx(2 * base, rel=0.02)   # zoom's scale is over the fixed view
