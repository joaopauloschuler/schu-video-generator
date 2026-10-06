"""Step 36: the bundled world map and its helpers (``vidgen.geo``, public in ``vidgen.api``: data,
country lookup, Equal Earth, views, ``MapView``) and the ``map`` scene type (views, highlights,
choropleth + legend, pins, arcs, steps, focus, labels, targets)."""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import ArcBetweenPoints, Dot, ManimColor, Rectangle
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of
from test_schema import errors
from vidgen import api, geo, registry, schema
from vidgen.cli import check_project
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.project import Project
from vidgen.regions import Region
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
DATA = Path(geo.__file__).parent / "data" / "geo" / geo.MAP_FILE


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


def map_scene(params: dict[str, Any], n_beats: int = 2, scene_id: str = "m", **beat_actions: Any) -> dict[str, Any]:
    acts = [beat_actions.get(f"b{i + 1}") for i in range(n_beats)]
    return {"id": scene_id, "type": "map", "params": params, "beats": beats(*acts)}


def params(**changes: Any) -> Any:
    return cls_of("map").validate_params(changes, Theme())


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- data -------------------------------------------------------------------------------------


def test_bundled_map_is_small_complete_and_coded() -> None:
    assert DATA.stat().st_size < 500_000
    countries = geo.world_countries()
    assert len(countries) == 177 and len(geo.world_countries(antarctica=False)) == 176
    a3 = [c.a3 for c in countries]
    a2 = [c.a2 for c in countries if c.a2]
    assert len(set(a3)) == len(a3) and len(set(a2)) == len(a2) == 175       # N. Cyprus, Somaliland: no alpha-2
    assert all(len(c) == 3 and c.isupper() for c in a3)
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    assert "Natural Earth" in raw["source"]["data"] and "public domain" in raw["source"]["data"]
    for c in countries:
        lon0, lat0, lon1, lat1 = c.main
        assert lon0 <= c.label[0] <= lon1 and lat0 <= c.label[1] <= lat1, c.name
        for poly in c.polygons:
            for ring in poly:
                assert -180 <= ring[:, 0].min() and ring[:, 0].max() <= 180             # split at the date line
                assert np.abs(np.diff(ring[:, 0])).max() < 180, c.name


def test_rings_are_oriented_for_a_nonzero_fill() -> None:
    def area(r: np.ndarray) -> float:
        x, y = r[:, 0], r[:, 1]
        return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))

    holes = 0
    for c in geo.world_countries():
        for poly in c.polygons:
            assert area(poly[0]) > 0, c.name
            assert all(area(h) < 0 for h in poly[1:]), c.name
            holes += len(poly) - 1
    assert holes >= 1                                                       # Lesotho in South Africa


def test_label_points_lie_inside_their_country() -> None:
    def inside(x: float, y: float, rings: tuple[np.ndarray, ...]) -> bool:
        hit = False
        for r in rings:
            for (x0, y0), (x1, y1) in zip(r, np.roll(r, -1, axis=0)):
                if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                    hit = not hit
        return hit

    for c in geo.world_countries():
        assert any(inside(*c.label, poly) for poly in c.polygons), c.name
    france = geo.find_country("France")
    assert france.main[0] > -10                                             # French Guiana is not its main part


@pytest.mark.parametrize(
    ("name", "a3"),
    [("DE", "DEU"), ("deu", "DEU"), ("Germany", "DEU"), ("USA", "USA"), ("US", "USA"), ("United States of America", "USA"),
     ("UK", "GBR"), ("Great Britain", "GBR"), ("Holland", "NLD"), ("the Netherlands", "NLD"), ("Ivory Coast", "CIV"),
     ("cote d'ivoire", "CIV"), ("Côte d’Ivoire", "CIV"), ("Czech Republic", "CZE"), ("Congo", "COG"), ("DRC", "COD"),
     ("Türkiye", "TUR"), ("Turkey", "TUR"), ("South Korea", "KOR"), ("Russia", "RUS"), ("Kosovo", "XKX"), ("N. Cyprus", "CYN"),
     ("Bosnia and Herz.", "BIH"), ("Eswatini", "SWZ"), ("Swaziland", "SWZ")],
)
def test_find_country_by_code_name_and_alias(name: str, a3: str) -> None:
    assert geo.find_country(name).a3 == a3


@pytest.mark.parametrize(
    ("name", "message"),
    [("Germny", "did you mean 'Germany'"), ("Singapore", "too small for the bundled 1:110m world map"),
     ("MT", r"\(Malta\) is too small"), ("Atlantis", "use an ISO code")],
)
def test_find_country_errors(name: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        geo.find_country(name)


# ----- projection and views ---------------------------------------------------------------------------


def test_equal_earth_reference_values() -> None:
    x, y = geo.equal_earth(180.0, 0.0)
    assert float(x) == pytest.approx(math.pi / (geo._M * geo._A1))
    assert float(geo.equal_earth(0.0, 90.0)[1]) == pytest.approx(1.3173, abs=1e-3)
    xs, ys = geo.equal_earth(np.array([-90.0, 90.0]), np.array([45.0, -45.0]))
    assert xs[0] == pytest.approx(-xs[1]) and ys[0] == pytest.approx(-ys[1])
    assert float(geo.equal_earth(100.0, 10.0, lon0=100.0)[0]) == 0.0
    # equal area: a 10 x 10 degree cell has the same projected area at the equator and at 60 N
    def cell(lat: float) -> float:
        corners = [(0, lat), (10, lat), (10, lat + 10), (0, lat + 10)]
        lon_s = np.linspace(0, 10, 50)
        pts = [geo.equal_earth(lo, lat) for lo in lon_s] + [geo.equal_earth(lo, lat + 10) for lo in lon_s[::-1]]
        x = np.array([float(p[0]) for p in pts])
        y = np.array([float(p[1]) for p in pts])
        assert corners
        return 0.5 * abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))

    sphere = lambda lat: math.radians(10) * (math.sin(math.radians(lat + 10)) - math.sin(math.radians(lat)))  # noqa: E731
    assert cell(0) / sphere(0) == pytest.approx(cell(60) / sphere(60), rel=1e-3)


def test_view_box_and_fit_box() -> None:
    assert geo.view_box("europe") == geo.MAP_VIEWS["europe"]
    assert geo.view_box("world", antarctica=True)[1] == -90
    assert geo.view_box([170, -50, -170, 0]) == (170, -50, 190, 0)
    with pytest.raises(VidgenError, match="unknown map view 'mars'"):
        geo.view_box("mars")
    assert geo.fit_view([]) == geo.MAP_VIEWS["world"]
    small = geo.fit_view([(10, 50)])
    assert small[2] - small[0] == pytest.approx(14) and small[3] - small[1] == pytest.approx(9)
    pacific = geo.fit_view([(139.7, 35.7), (-122.4, 37.8)])                 # Tokyo, San Francisco
    assert pacific[0] > 100 and pacific[2] > 180                             # over the date line
    assert geo.fit_view([(-120, 40), (100, 30), (0, 0)]) == geo.MAP_VIEWS["world"]


def test_map_view_fits_grows_and_clips() -> None:
    area = Region(-6, -3, 6, 3)
    world = geo.MapView(geo.view_box("world"), area)
    assert not world.cropped
    r = world.region
    assert r.width == pytest.approx(12) or r.height == pytest.approx(6)
    assert area.x0 - 1e-9 <= r.x0 and r.x1 <= area.x1 + 1e-9 and area.y0 - 1e-9 <= r.y0 and r.y1 <= area.y1 + 1e-9
    europe = geo.MapView(geo.view_box("europe"), area)
    assert europe.cropped and europe.region.width == pytest.approx(12) and europe.region.height == pytest.approx(6)
    berlin = europe.point(13.4, 52.5)
    assert europe.contains(13.4, 52.5) and not europe.contains(-74, 40.7)
    assert berlin[0] > europe.point(2.35, 48.86)[0] and berlin[1] > europe.point(2.35, 48.86)[1]
    russia = europe.polygons(geo.find_country("Russia"))
    pts = np.concatenate([ring for poly in russia for ring in poly])
    m = europe.region
    assert pts[:, 0].min() >= m.x0 - 1e-6 and pts[:, 0].max() <= m.x1 + 1e-6 and pts[:, 1].max() <= m.y1 + 1e-6
    assert europe.polygons(geo.find_country("Australia")) == []
    tall = geo.MapView(geo.view_box("europe"), Region(-3, -6, 3, 6))   # portrait: more map north and south
    assert tall.region.height == pytest.approx(12)
    pacific = geo.MapView(geo.view_box([150, -50, -150, 10]), area)
    fiji = pacific.polygons(geo.find_country("Fiji"))
    assert fiji and pacific.contains(178, -17.8) and pacific.contains(-175, -20)


def test_projected_geometry_is_cached_and_fast() -> None:
    area = Region(-6, -3, 6, 3)
    geo._projected.cache_clear()
    start = time.perf_counter()
    view = geo.MapView(geo.view_box("world"), area)
    n = sum(len(view.polygons(c)) for c in geo.world_countries(False))
    first = time.perf_counter() - start
    assert n > 250 and first < 2.0
    assert geo._projected.cache_info().currsize == 1
    start = time.perf_counter()
    geo.MapView(geo.view_box("world"), area).polygons(geo.find_country("Canada"))
    assert geo._projected.cache_info().hits >= 1 and time.perf_counter() - start < first


def test_geo_helpers_are_public() -> None:
    for name in ("MAP_VIEWS", "Country", "MapView", "equal_earth", "find_country", "fit_view", "view_box", "world_countries"):
        assert name in api.__all__ and name in api.VIDGEN_NAMES and getattr(api, name) is getattr(geo, name)


# ----- params -----------------------------------------------------------------------------------------


def test_params_shorthands_and_lookups() -> None:
    p = params(countries=["USA", {"country": "de", "color": "primary", "label": "DE"}],
               steps=["France", ["Spain", "PT"], {"pins": [{"country": "Japan", "label": "Tokyo"}], "arcs": ["Tokyo -> USA"], "focus": 2}])
    assert [c.a3 for _, _, c in p.highlighted()] == ["USA", "DEU", "FRA", "ESP", "PRT"]
    assert [k for k, _, _ in p.highlighted()] == [0, 0, 1, 2, 2]
    assert p.all_pins()[0][1].where() == geo.find_country("Japan").label
    assert p.arc_end("Tokyo") == geo.find_country("Japan").label and p.arc_end([1, 2]) == (1.0, 2.0)
    arc = p.all_arcs()[0][1]
    assert (arc.start, arc.to) == ("Tokyo", "USA")
    assert p.steps[2].focus == 2
    assert params(values={"Germany": 1, "FR": 2}).valued() == {"DEU": 1.0, "FRA": 2.0}


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"countries": ["Germny"]}, "did you mean 'Germany'"),
     ({"countries": ["Singapore"]}, "too small"),
     ({"countries": ["DE"], "steps": [["Germany"]]}, "already highlighted"),
     ({"values": {"DE": 1, "Germany": 2}}, "are the same country"),
     ({"view": "mars"}, "unknown view 'mars'"),
     ({"view": [0, 10, 20]}, "got 3 numbers"),
     ({"view": [0, 50, 20, 40]}, "lat_max must be greater"),
     ({"view": [0, 10, 200, 40]}, "longitudes are -180..180"),
     ({"pins": [{"lon": 1}]}, "needs lon and lat"),
     ({"pins": [{"lon": 1, "lat": 2, "country": "DE"}]}, "not both"),
     ({"pins": [{"lon": 1, "lat": 95}]}, "less than or equal to 90"),
     ({"pins": [{"lon": 1, "lat": 2, "label": "A"}, {"lon": 3, "lat": 4, "label": "A"}]}, "pin labels must be unique"),
     ({"arcs": ["Paris"]}, "'A -> B'"),
     ({"arcs": ["Paris -> Berlin"]}, "neither a pin label nor a country"),
     ({"arcs": [{"from": "DE", "to": "Germany"}]}, "the same point"),
     ({"arcs": [{"from": [1, 2, 3], "to": "DE"}]}, r"\[lon, lat\]"),
     ({"steps": [{"focus": True}]}, "focus needs"),
     ({"steps": [{"countries": ["DE"], "focus": 5}]}, "at most 4"),
     ({"values": {"DE": -1, "FR": 2}, "scale_min": 0, "scale_max": 3}, "center 0 must lie"),
     ({"highlight_color": "nope"}, "unknown theme color")],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        params(**changes)


def test_validate_reports_map_errors_and_targets(make_project) -> None:
    project = load(make_project, [
        map_scene({"countries": ["Atlantis"]}, scene_id="a"),
        map_scene({"countries": ["France"]}, scene_id="b", b2=[{"zoom": "country:DEU"}]),
    ])
    problems = check_project(project)
    assert "scenes[0].params.countries[0].country: unknown country 'Atlantis' (use an ISO code such as 'DE' or 'DEU', or an English name)" in problems
    assert any("unknown target 'country:DEU' for scene type 'map'" in p and "country:FRA" in p for p in problems)


def test_schema_has_from_and_shorthands() -> None:
    cls_of("map")
    doc = schema.params_schema(registry.get("map"), [Theme()])
    text = json.dumps(doc)
    assert '"from"' in text and '"start"' not in text
    assert "lon_min" in text
    good = {"view": [150, -50, -170, 0], "countries": ["USA", {"country": "DE", "label": False}],
            "pins": [{"lon": 1, "lat": 2, "label": "A"}, {"country": "Japan"}],
            "arcs": ["A -> Japan", {"from": [1, 2], "to": "A", "label": "x"}],
            "steps": ["France", ["Spain", "PT"], {"countries": ["Italy"], "focus": 2}, []], "values": {"DE": 1}}
    assert errors(doc, good) == []
    assert errors(doc, {"arcs": ["Paris"]}) and errors(doc, {"pins": [{"lon": 1, "lat": 2, "city": "x"}]})


# ----- rendering ----------------------------------------------------------------------------------------


def colors(mob: Any) -> str:
    return ManimColor(mob.get_fill_color()).to_hex().upper()


@pytest.mark.render
def test_world_map_steps_highlights_pins_and_arcs(make_project, media: Path) -> None:
    p = {"title": "Offices", "view": "world",
         "steps": [["USA", {"country": "Brazil", "color": "primary"}],
                   {"pins": [{"lon": -0.13, "lat": 51.5, "label": "London"}, {"lon": 139.7, "lat": 35.7, "label": "Tokyo"}],
                    "arcs": [{"from": "London", "to": "Tokyo", "label": "14 h"}]}]}
    scene = render(load(make_project, [map_scene(p)]), "m", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    theme = scene.theme
    assert 170 <= len(scene._countries) <= 176 and scene._panel is None
    usa = scene.find_targets("country:USA")[0]
    overlay = usa.mobject.submobjects[0]
    assert colors(overlay) == ManimColor(theme.color("accent")).to_hex().upper()
    assert colors(scene.find_targets("country:Brazil")[0].mobject.submobjects[0]) == ManimColor(theme.color("primary")).to_hex().upper()
    land = ManimColor(api.mix_colors(theme.color("dim"), theme.background, 0.3)).to_hex().upper()
    assert colors(scene._countries["FRA"]) == land
    arc = scene.find_targets("arc1")[0].mobject
    curve = next(m for m in arc.submobjects if isinstance(m, ArcBetweenPoints))
    london, tokyo = scene._view.point(-0.13, 51.5), scene._view.point(139.7, 35.7)
    assert np.linalg.norm(curve.get_start() - london) == pytest.approx(0.13, abs=0.02)   # stops short of the pins
    assert curve.get_top()[1] > max(london[1], tokyo[1]) + 0.3                           # bends upwards
    assert not any(isinstance(m, Dot) and m.z_index == 2 for m in arc.submobjects)        # ends are pins: no end dots
    # step 2 at beat 2; every target ends up on screen; labels do not overlap
    assert any("Create" in a for a in plays(scene, "m_b2")[0])
    assert all(scene.is_shown(t) for t in scene.targets)
    plates = [m for labels in scene._labels for m in labels if isinstance(m[0], api.RoundedRectangle)]
    boxes = [(m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1]) for m in plates]
    assert len(boxes) == 5
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.mark.render
def test_choropleth_legend_outline_and_regional_panel(make_project, media: Path) -> None:
    p = {"view": "europe", "values": {"Germany": 83, "France": 68, "Spain": 48, "Poland": 37}, "legend_label": "millions",
         "steps": [[], ["Germany"]]}
    scene = render(load(make_project, [map_scene(p)]), "m", media)
    view = scene._view
    assert view.cropped and isinstance(scene._panel, Rectangle)
    legend = scene.find_targets("legend")[0].mobject
    assert legend.get_top()[1] < view.region.y0 and abs(legend.get_center()[0] - view.region.center[0]) < 1e-6
    scale = scene._scale
    assert colors(scene._countries["DEU"]) == ManimColor(scale(83)).to_hex().upper()
    assert colors(scene._countries["FRA"]) != colors(scene._countries["DEU"])
    outline = scene.find_targets("country:DE")[0].mobject.submobjects[0]
    assert outline.get_fill_opacity() == 0 and outline.get_stroke_width() > 3
    assert scene.find_targets("country:Spain")[0].mobject is scene._countries["ESP"]
    assert "AUS" not in scene._countries                                                  # out of view


@pytest.mark.render
def test_auto_view_fits_the_items(make_project, media: Path) -> None:
    p = {"countries": ["Portugal", "Spain"], "pins": [{"lon": 2.35, "lat": 48.86, "label": "Paris"}]}
    scene = render(load(make_project, [map_scene(p, n_beats=1)]), "m", media)
    view = scene._view
    for lon, lat in [(2.35, 48.86), (-9.0, 39.0), (3.0, 42.0)]:
        assert view.contains(lon, lat, margin=0.3)
    assert not view.contains(30.0, 50.0) and view.cropped


@pytest.mark.render
def test_focus_moves_the_camera_and_back_and_fades_other_labels(make_project, media: Path) -> None:
    p = {"view": "europe", "steps": [["France"], {"countries": ["Belgium"], "focus": True}, {"pins": [{"country": "Italy", "label": "Rome"}]}]}
    scene = render(load(make_project, [map_scene(p, n_beats=3)]), "m", media)
    moves = [r for r in scene.play_log if "MoveCamera" in r.animations]
    assert [r.beat for r in moves] == ["m_b2", "m_b3"]
    assert scene._cameras[2] is not None and scene._cameras[2][0] < scene.frame_width / 1.5
    assert "FadeOut" in moves[0].animations                                              # France's label leaves
    assert scene.camera.frame.width == pytest.approx(scene.frame_width)
    _, s = scene._bounds(2)
    belgium_label = scene._labels[2][0]
    france_label = scene._labels[1][0]
    assert belgium_label[1].font_size == pytest.approx(france_label[1].font_size * s, rel=0.02)   # reads the same zoomed in


@pytest.mark.render
def test_portrait_map_and_dateline_view(make_project, media: Path) -> None:
    p = {"view": [150, -50, -170, 5], "countries": ["New Zealand", "Fiji"], "pins": [{"lon": -171.8, "lat": -13.8, "label": "Apia"}]}
    scene = render(load(make_project, [map_scene(p, n_beats=1)]), "m", media, size=(90, 160))
    view = scene._view
    assert view.region.height > view.region.width and view.contains(-171.8, -13.8) and view.contains(174.8, -41.3)
    assert scene.find_targets("country:FJI")[0].mobject.submobjects
    assert all(scene.is_shown(t) for t in scene.targets)


@pytest.mark.render
def test_early_reveal_and_dim_actions(make_project, media: Path) -> None:
    p = {"steps": [["France"], ["Germany"]]}
    acts = {"b1": [{"reveal": "country:Germany"}, {"dim": "map", "at": 0.5}]}
    scene = render(load(make_project, [map_scene(p, **acts)]), "m", media)
    assert plays(scene, "m_b2") == []
    assert scene._countries["ITA"].get_fill_opacity() == pytest.approx(0.45, abs=0.01)
    assert scene.find_targets("country:DEU")[0].mobject.submobjects[0].get_fill_opacity() == pytest.approx(1)


@pytest.mark.render
@pytest.mark.slow
def test_map_lints_clean_in_landscape_and_portrait(make_project) -> None:
    scenes = [
        map_scene({"title": "Offices", "view": "world", "steps": [["USA", "Brazil", "Japan"],
                   {"pins": [{"lon": -0.13, "lat": 51.5, "label": "London"}, {"lon": 2.35, "lat": 48.86, "label": "Paris"}], "arcs": ["London -> Japan"]}]},
                  scene_id="w"),
        map_scene({"title": "People", "view": "europe", "values": {"Germany": 83, "France": 68, "UK": 67, "Italy": 59}, "legend_label": "millions",
                   "steps": [[], {"countries": ["Belgium", "Netherlands"], "focus": True}]}, scene_id="e"),
    ]
    for preview in ({"width": 320, "height": 180, "fps": 5}, {"width": 180, "height": 320, "fps": 5}):
        project = load(make_project, scenes, preview=preview)
        result = lint_project(project, rules=["off_frame", "safe_area", "text_overlap", "covered_text", "min_font", "contrast"])
        assert [(f.scene, f.rule, f.message) for f in result.findings] == []


@pytest.mark.render
def test_extending_map_example_renders(make_project, media: Path) -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    code = re.search(r"\*\*Maps\.\*\*.*?```python\n(.*?)```", text, re.S).group(1)
    project = load(make_project, [{"id": "a", "type": "capital", "beats": beats(None, None)}])
    (project.root / "extensions").mkdir(exist_ok=True)
    (project.root / "extensions" / "capital.py").write_text("from vidgen.api import *\n\n\n" + code, encoding="utf-8")
    scene = render(Project.load(project.root), "a", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert len([m for m in scene.mobjects if isinstance(m, api.VGroup)]) >= 1


def _tool() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_world_map", Path(__file__).resolve().parents[1] / "tools" / "make_world_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_cuts_rings_at_the_antimeridian_and_orients_them() -> None:
    tool = _tool()
    island = [(178.0, -16.0), (-179.0, -16.0), (-179.0, -18.0), (178.0, -18.0)]   # crosses 180
    pieces = tool.split_at_antimeridian([island])
    assert len(pieces) == 2
    spans = sorted((min(p[0] for p in r[0]), max(p[0] for p in r[0])) for r in pieces)
    assert spans == [(-180.0, -179.0), (178.0, 180.0)]
    flat = tool.quantize(island[::-1], outer=True)
    assert tool.signed_area([(flat[i] / 100, flat[i + 1] / 100) for i in range(0, len(flat), 2)]) > 0
    assert tool.quantize([(0, 0), (0, 0), (1, 1)], outer=True) is None
    topo = {"transform": {"scale": [1, 1], "translate": [0, 0]}, "arcs": [[[0, 0], [2, 0], [0, 2]], [[2, 2], [-2, 0], [0, -2]]]}
    arcs = tool.decode_arcs(topo)
    assert arcs[0] == [(0, 0), (2, 0), (2, 2)] and tool.ring([0, 1], arcs) == [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
    assert tool.ring([~0], arcs) == [(2, 2), (2, 0), (0, 0)]
    assert tool.label_point([[(0, 0), (10, 0), (10, 10), (0, 10)]]) == pytest.approx((5, 5), abs=0.5)
