"""Step 376: the declarative ``space`` scene (DESIGN.md §122.12): its words checked in Python, the
page it writes (stable bytes, every param in them), the runtime helpers ``vidgen/space-scene`` in Node,
``vidgen space-page``, ``vidgen music plan --style space`` and the ``space_scene`` / ``orbit_scale`` lint."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from vidgen import extensions, registry
from vidgen.cli import main, validate_all
from vidgen.project import Project
from vidgen.web.space_names import array_strings, constant_text, object_entries, space_names
from conftest import minimal_config

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "src" / "vidgen" / "data" / "web" / "modules"
DATA = ROOT / "src" / "vidgen" / "data" / "web" / "libs"

RINGS = {"sky": {"seed": 4, "look": "rich"}, "sun": {"direction": [1, -0.3, 0.25]},
         "bodies": [{"name": "Saturn"}, {"name": "Titan", "world": "titan", "at": ["1200000 km", "300000 km", "40000 km"]}],
         "camera": {"move": "arc", "subject": "Saturn", "phase": ["three-quarter", "crescent"], "distance": {"radii": 6}, "lens": "wide-normal"}}
TRANSFER = {"orbits": {"central": "earth", "date": "2026-06-19", "speedup": 6000,
                       "bodies": [{"name": "Ship", "altitude": "900 km"}, {"preset": "geo", "name": "Geo", "nu": 0}], "transfer": {"ship": "Ship", "to": "Geo"}},
            "bodies": [{"name": "Earth"}], "craft": [{"name": "Ship", "kind": "ship", "seed": 2, "burn": {"seconds": 0.6, "turn": 0.4}}],
            "camera": {"move": "follow", "subject": "Ship", "view": "chase", "push": 0.8}}
HOLE = {"sky": {"seed": 4}, "phenomena": [{"kind": "black-hole", "name": "Hole", "size": "10 km", "tilt": 12}, {"kind": "warp", "over": [3.5, 6]}],
        "camera": [{"move": "fly-by", "subject": "Hole", "over": [0, 3.5], "closest": {"radii": 26}, "side": "left"},
                   {"move": "look", "from": [0, "-2000 km", 0], "to": [0, "-3000 km", "50 km"], "over": [3.5, 6], "cut": True}]}


@pytest.fixture
def builtins_loaded() -> None:
    extensions.load_builtins()


@pytest.fixture
def space(builtins_loaded: None) -> Any:
    return registry.get("space").cls


def params(space: Any, raw: dict[str, Any]) -> Any:
    return space.Params.model_validate(copy.deepcopy(raw))


def problem(space: Any, raw: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as caught:
        params(space, raw)
    return str(caught.value)


# ----- the names, read from the modules ---------------------------------------------------------------


def test_the_reader_reads_js_literals() -> None:
    source = 'const A = {x: 1, "y-z": [1, {a: 2}], f(o) { return "}"; }, ...B}; // c\nexport const B = Object.freeze({b: `t${1}`}); const L = ["p", ...M]; const M = ["q"];'
    assert list(object_entries(constant_text(source, "A"), source)) == ["x", "y-z", "f", "b"]
    assert array_strings(constant_text(source, "L"), source) == ["p", "q"]


def test_names_come_from_the_shipped_modules() -> None:
    n = space_names()
    assert {"saturn", "earth", "tempest", "azure"} <= set(n["worlds"]) and "ice-giant" in n["world_types"]
    assert list(n["craft"]) == ["probe", "satellite", "station", "ship", "lander", "tug"] and "ring" in n["craft"]["station"]
    assert set(n["moves"]) == {"arc", "fly-by", "pass", "arrive", "reveal", "follow", "zoom", "look"}
    assert "closest" in n["moves"]["fly-by"] and "side" in n["moves"]["pass"] and "stops" in n["moves"]["zoom"] and "phase" in n["moves"]["arc"]
    assert n["lenses"]["wide-normal"] == 35 and "crescent" in n["phases"] and "chase" in n["views"]
    assert n["sky_looks"] == ["natural", "rich", "sparse"] and "milkyWay" in n["sky_options"]
    assert n["stars"] == ["red-dwarf", "orange", "sun", "white", "blue-giant"] and n["exposures"] == ["film", "camera", "auto"]
    assert "clouds" in n["world_options"]["ocean"] and "bands" in n["world_options"]["gas"] and "clouds" not in n["world_options"]["gas"]
    assert "disc" in n["phenomena"]["black-hole"] and "latitude" in n["phenomena"]["aurora"]
    assert n["finish_options"]["bloom"] == ["strength", "radius", "threshold", "scale"] and "fStop" in n["finish_options"]["dof"]
    assert n["finish_options"]["noise"] == ["amount", "color", "size", "floor"] and n["finish_options"]["range"] == ["stops", "shoulder", "black"]
    assert n["finish_options"]["sharpen"] == ["amount", "radius", "limit"]
    assert n["finish_options"]["distort"] == ["amount", "mm"] and n["finish_options"]["edges"] == ["soft", "fringe", "power"]
    assert n["finish_options"]["halation"] == ["amount", "radius", "threshold", "color"]
    assert "link" in n["end_options"] and "link" not in n["title_options"]


def test_node_reads_the_same_names(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    for name in ("music-time", "space-camera", "title-cards", "space-scene"):
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in ("music-time", "space-camera", "title-cards", "space-scene")}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as C from 'vidgen/space-camera'; import * as T from 'vidgen/title-cards';\n"
        "console.log(JSON.stringify({lenses: C.LENSES, phases: Object.keys(C.PHASES), views: Object.keys(C.VIEWS), title: Object.keys(T.TITLE_DEFAULTS), end: Object.keys(T.END_DEFAULTS)}));\n",
        encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    got, n = json.loads(done.stdout), space_names()
    assert got["lenses"] == n["lenses"] and got["phases"] == n["phases"] and got["views"] == n["views"]
    assert got["title"] == n["title_options"] and got["end"] == n["end_options"]


# ----- checking the words ------------------------------------------------------------------------------


def test_the_demonstrations_validate(space: Any) -> None:
    for raw in (RINGS, TRANSFER, HOLE):
        params(space, raw)
    p = params(space, RINGS)
    assert p.bodies[0].world == "saturn" and p.camera[0].options()["phase"] == ["three-quarter", "crescent"]
    assert params(space, {**RINGS, "sky": "real"}).sky.stars == "real" and params(space, {**RINGS, "sky": "sparse"}).sky.look == "sparse"
    assert params(space, {**RINGS, "camera": {"move": "flyby", "subject": "Saturn"}}).camera[0].move == "fly-by"
    snake_value = {**RINGS, "camera": {"move": "arc", "subject": "Saturn", "phase": "thin_crescent"}}
    assert params(space, snake_value).camera[0].options()["phase"] == "thin-crescent"


@pytest.mark.parametrize("change,words", [
    ({"bodies": [{"name": "Satrun"}]}, "did you mean 'saturn'"),
    ({"bodies": [{"name": "X", "world": "tempst"}]}, "did you mean 'tempest'"),
    ({"bodies": [{"name": "Saturn", "bnads": 3}]}, "did you mean 'bands'"),
    ({"bodies": [{"name": "X", "type": "gass"}]}, "did you mean 'gas'"),
    ({"sky": {"look": "richh"}}, "did you mean 'rich'"),
    ({"sky": {"milky_wya": 2}}, "did you mean 'milky_way'"),
    ({"sun": {"kind": "red_dwarff"}}, "did you mean 'red-dwarf'"),
    ({"sun": {"glair": 2}}, "did you mean 'glare'"),
    ({"camera": {"move": "arcc", "subject": "Saturn"}}, "did you mean 'arc'"),
    ({"camera": {"move": "arc", "subject": "Saturn", "phase": "cresent"}}, "did you mean 'crescent'"),
    ({"camera": {"move": "fly-by", "subject": "Saturn", "closets": 3}}, "did you mean 'closest'"),
    ({"camera": {"move": "arc", "subject": "Saturnn"}}, "did you mean 'Saturn'"),
    ({"camera": {"move": "follow", "subject": "Saturn", "view": "chaes"}}, "did you mean 'chase'"),
    ({"camera": {"move": "arc", "subject": "Saturn", "lens": "wde"}}, "did you mean 'wide'"),
    ({"craft": [{"name": "P", "kind": "prob"}]}, "did you mean 'probe'"),
    ({"craft": [{"name": "P", "kind": "probe", "attitude": "prograd"}]}, "did you mean 'prograde'"),
    ({"phenomena": [{"kind": "blackhole"}]}, "did you mean 'black-hole'"),
    ({"phenomena": [{"kind": "black-hole", "disk": False}]}, "did you mean 'disc'"),
    ({"finish": {"bloom": {"strenght": 1}}}, "did you mean 'strength'"),
    ({"finish": {"depth_of_field": {"f_stp": 2}}}, "did you mean 'f_stop'"),
    ({"finish": {"noise": {"colour": 0.5}}}, "did you mean 'color'"),
    ({"finish": {"range": {"stop": 2}}}, "did you mean 'stops'"),
    ({"finish": {"edges": {"sfot": 2}}}, "did you mean 'soft'"),
    ({"finish": {"halation": {"colour": [1, 0.5, 0.2]}}}, "did you mean 'color'"),
    ({"operator": {"hand": "handhled"}}, "did you mean 'handheld'"),
    ({"operator": {"exposure": True}}, "operator.exposure is a surface scene's"),
    ({"camera_look": "windw_handheld"}, "did you mean 'window_handheld'"),
    ({"camera_look": "drone", "finish": False}, "leave out finish: false"),
    ({"camera_look": "phone", "operator": {"exposure": True}}, "operator.exposure is a surface scene's"),
    ({"camera_look": "drone", "finish": {"noise": {"colour": 1}}}, "did you mean 'color'"),
    ({"title": {"title": "T", "sied": "left"}}, "'side'?"),
    ({"scale": 50}, "scale: goes with orbits"),
    ({"camera": [{"move": "arc", "subject": "Saturn"}, {"move": "arc", "subject": "Titan"}]}, "with several moves each gives over"),
    ({"camera": [{"move": "arc", "subject": "Saturn", "over": [0, 5]}, {"move": "arc", "subject": "Titan", "over": [4, 8]}]}, "moves do not overlap"),
    ({"camera": {"move": "arc", "subject": "Saturn", "over": ["bar 1", "bar 5"]}}, "need the score on the page: add music_data"),
    ({"camera": {"move": "arc", "subject": "Saturn", "over": ["bar 0", "bar 5"]}, "music_data": True}, "count from 1"),
    ({"music": [{"track": "kick", "pulse": "Sun"}]}, "add music_data"),
    ({"music": [{"track": "kick", "pulse": "Saturn"}], "music_data": True}, "worlds reflect the sun: they do not pulse"),
    ({"music": [{"track": "kick", "pulse": "Sun", "glint": "Sun"}], "music_data": True}, "gives one of pulse, glow or glint"),
    ({"music": [{"track": "kick", "pulse": "Sunn"}], "music_data": True}, "did you mean 'Sun'"),
    ({"bodies": [{"name": "Saturn"}, {"name": "Saturn"}]}, "given to two things"),
    ({"phenomena": [{"kind": "aurora", "world": "Earth"}]}, "is not a world of bodies"),
    ({"script": "extensions/more.py"}, "expected a .js"),
])
def test_mistakes_are_named_with_the_closest_word(space: Any, change: dict[str, Any], words: str) -> None:
    assert words in problem(space, {**RINGS, **change})


def test_what_goes_with_orbits(space: Any) -> None:
    assert "with orbits a world shows a body of the orbit data" in problem(space, {**TRANSFER, "bodies": [{"name": "Mars"}]})
    assert "leave out at and radius" in problem(space, {**TRANSFER, "bodies": [{"name": "Earth", "radius": "7000 km"}]})
    assert "a craft flies a body of the orbit data: fly: NAME" in problem(space, {**TRANSFER, "craft": [{"name": "Shp", "kind": "ship"}]})
    assert "fly: needs orbits:" in problem(space, {**RINGS, "craft": [{"name": "Ship", "kind": "ship", "fly": "Ship"}]})
    assert "has no position on that date" in problem(space, {**TRANSFER, "orbits": {**TRANSFER["orbits"], "bodies": [{"name": "Ship", "altitude": "900 km"}, {"preset": "geo", "name": "Geo"}]}})
    assert params(space, {**TRANSFER, "scale": {"mode": "enlarged", "enlarge": {"default": 20}}}).scale.mode == "enlarged"
    assert "needs enlarge" in problem(space, {**TRANSFER, "scale": "enlarged"})


# ----- the page ------------------------------------------------------------------------------------------


def page(space: Any, raw: dict[str, Any], scene_id: str = "s") -> str:
    from vidgen.scenes.space_page import page_source

    return page_source(params(space, raw), scene_id)


def test_the_page_is_stable_and_written_from_the_params(space: Any) -> None:
    for raw in (RINGS, TRANSFER, HOLE):
        a, b = page(space, raw), page(space, raw)
        assert a == b and "Math.random" not in a and "Date" not in a and "performance" not in a
    text = page(space, RINGS)
    assert 'planet(renderer, "saturn", {}); space.add(S.bodies["Saturn"].object, {at: [0, 0, 0], size: 60268000});' in text
    assert 'S.cam.arc(t, {"phase": ["three-quarter", "crescent"], "distance": {"radii": 6}, "subject": S.subjects["Saturn"], "lens": "wide-normal", "over": [0, S.seconds]})' in text
    assert '"antialias": "none"' in text and "direction: yUp([1, -0.3, 0.25])" in text
    orbit = page(space, TRANSFER)
    assert 'planet(renderer, "earth", {space, body: "Earth"})' in orbit and 'S.craft["Ship"].fly(space, {"body": "Ship", "attitude": "prograde", "burn": {"seconds": 0.6, "turn": 0.4}})' in orbit
    assert "direction: yUp([0.0455" in orbit   # the Sun from the Earth on 19 June 2026: ecliptic longitude about 87 degrees
    assert 'S.subjects["Earth"] = "Earth";' in orbit   # Step 377: a world of the orbit data is a subject of the camera (an arc round it)
    arc = page(space, {**TRANSFER, "camera": {"move": "arc", "subject": "Earth", "distance": {"radii": 5}}})
    assert 'S.cam.arc(t, {"distance": {"radii": 5}, "subject": S.subjects["Earth"]' in arc
    hole = page(space, HOLE)
    assert "P.blackHole(renderer, {" in hole and '"tilt": 12' in hole and "cut: true" in hole and "P.warp(renderer" in hole


def test_review_fixes_of_the_page(space: Any) -> None:
    """Step 378: a camera that names a body of the orbit data nothing draws (a comet's body) has it as a subject;
    a length YAML read as text ('2.6e9') is metres; a length without a unit inside a move is refused at validation."""
    comet = {"orbits": {"central": "sun", "date": "1986-02-09", "speedup": 200000, "bodies": [{"preset": "halley", "name": "Halley", "nu": -60}]},
             "phenomena": [{"kind": "comet", "name": "Tail", "body": "Halley"}], "camera": {"move": "arc", "subject": "Halley", "phase": "half", "distance": "2e9"}}
    text = page(space, comet)            # the dated speed-up is not refused on the stand-in span of one period (76 years)
    assert 'S.subjects["Halley"] = "Halley";' in text and '"distance": 2000000000,' in text
    assert 'S.subjects["Earth"] = "Earth";   // a body' not in page(space, TRANSFER)   # drawn worlds are subjects already
    words = problem(space, {**RINGS, "camera": {"move": "zoom", "stops": [{"subject": "Saturn", "distance": "2 parsnips"}, {"subject": "Saturn", "distance": 1e9}]}})
    assert "unknown unit 'parsnips'" in words and "camera.0" in words          # at validation, not a traceback at render


@pytest.mark.parametrize("path,value", [
    (("seed",), 2), (("sky", "seed"), 5), (("sky", "look"), "sparse"), (("sun", "direction"), [1, 0, 0]), (("sun", "glare"), 0.5),
    (("bodies", 0, "seed"), 3), (("bodies", 0, "rings"), False), (("bodies", 1, "at", 0), "1300000 km"), (("light", "exposure"), "camera"),
    (("camera", "distance", "radii"), 7), (("camera", "lens"), "wide"), (("finish",), False), (("finish",), {"grain": 0.05}),
    (("finish",), {"noise": 0.01}), (("finish",), {"range": {"stops": 2, "black": 0.01}}), (("finish",), {"sharpen": True}),
    (("finish",), {"distort": True}), (("finish",), {"edges": {"soft": 2}}), (("finish",), {"halation": 0.3}),
    (("operator",), {"hand": True}), (("operator",), {"horizon": 2}), (("camera_look",), "drone"),
    (("title",), "Saturn"), (("end_card",), {"title": "End", "link": "x"}), (("data",), {"a": 1}),
])
def test_every_param_changes_the_page(space: Any, path: tuple[Any, ...], value: Any) -> None:
    raw = copy.deepcopy(RINGS)
    target = raw
    for key in path[:-1]:
        target = target.setdefault(key, {}) if isinstance(key, str) else target[key]
    target[path[-1]] = value
    assert page(space, raw) != page(space, RINGS)


def test_a_camera_look_sets_the_finish_and_the_operator_and_the_scene_wins(space: Any) -> None:
    """camera_look: (Step 400) writes the look's finish and operator into the page, the scene's own finish and operator
    over them key by key (the space finish's defaults under both); an orbital scene leaves the look's automatic
    exposure out (no meter there); without it the page is the same as before (no look line)."""
    from vidgen.web.space_names import camera_looks

    assert "camera look" not in page(space, RINGS) and "vidgen/camera-looks" not in page(space, RINGS)
    look = camera_looks()["looks"]["window_handheld"]
    p = params(space, {**RINGS, "camera_look": "window-handheld", "finish": {"noise": 0.02, "grain": 0.05, "grade": {"saturation": 1.2}},
                       "operator": {"horizon": False, "seed": 4}})
    o = p.finish.options()
    assert p.camera_look == "window_handheld"
    assert o["noise"] == {**look["finish"]["noise"], "amount": 0.02} and o["grain"] == 0.05 and o["antialias"] == "none"
    assert o["grade"] == {**look["finish"]["grade"], "saturation": 1.2} and o["halation"] == look["finish"]["halation"]
    assert p.operator.options() == {"hand": look["operator"]["hand"], "horizon": False, "seed": 4}       # no exposure: an orbital scene
    text = page(space, {**RINGS, "camera_look": "window_handheld"})
    assert "// camera look window_handheld (vidgen/camera-looks)" in text and 'S.view = operate(S.view, {"hand": {"style": "handheld", "amount": 0.6}' in text
    line = next(x for x in text.splitlines() if "new Finish(" in x)
    assert '"noise": {"amount": 0.01}' in line and '"range": {"stops": 2, "shoulder": 0.08}' in line and '"antialias": "none"' in line


def test_the_camera_sensor_is_off_unless_given(space: Any) -> None:
    """finish.noise, range and sharpen (Step 397) reach the page only when given: a page without them is unchanged."""
    line = next(x for x in page(space, RINGS).splitlines() if "new Finish(" in x)
    assert all(k not in line for k in ('"noise"', '"range"', '"sharpen"'))
    line = next(x for x in page(space, {**RINGS, "finish": {"noise": True, "range": {"stops": 2}, "sharpen": 0.4}}).splitlines() if "new Finish(" in x)
    assert '"noise": true' in line and '"range": {"stops": 2}' in line and '"sharpen": 0.4' in line


def test_the_camera_lens_is_off_unless_given(space: Any) -> None:
    """finish.distort, edges and halation (Step 398) reach the page only when given: a page without them is unchanged."""
    line = next(x for x in page(space, RINGS).splitlines() if "new Finish(" in x)
    assert all(k not in line for k in ('"distort"', '"edges"', '"halation"'))
    line = next(x for x in page(space, {**RINGS, "finish": {"distort": True, "edges": {"fringe": 1}, "halation": 0.3}}).splitlines() if "new Finish(" in x)
    assert '"distort": true' in line and '"edges": {"fringe": 1}' in line and '"halation": 0.3' in line


def test_floats_are_written_exactly() -> None:
    from vidgen.scenes.space_page import Ref, js

    assert js({"a": 0.1, "b": 3.0, "c": [1e20, -2.5], "d": Ref("S.x")}) == '{"a": 0.1, "b": 3, "c": [1e+20, -2.5], "d": S.x}'


def test_the_page_imports_only_shipped_modules(space: Any) -> None:
    from vidgen.web.loaded import VIDGEN_MODULES

    for raw in (RINGS, TRANSFER, HOLE, {**RINGS, "title": "T", "end_card": {"title": "E"}, "music_data": True,
                                       "craft": [{"name": "C", "kind": "probe", "at": [0, "70000 km", 0]}], "music": [{"track": "kick", "glint": "C"}]}):
        for module in re.findall(r'from "([^"]+)"', page(space, raw)):
            assert module == "three" or module in VIDGEN_MODULES, module


def test_the_pages_are_valid_javascript(space: Any, tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    raw = {**RINGS, "title": "T", "end_card": {"title": "E", "lines": ["a"]}, "music_data": True, "script": "extensions/more.js",
           "craft": [{"name": "C", "kind": "probe", "at": [0, "70000 km", 0], "velocity": [0, 100, 0]}, {"name": "F", "kind": ["probe", "satellite"], "fleet": 3, "at": [0, 0, "90000 km"]}],
           "phenomena": [{"kind": "aurora", "world": "Saturn"}, {"kind": "asteroids", "layout": "belt", "around": "Saturn"}, {"kind": "comet", "at": ["900000 km", 0, 0]}],
           "music": [{"track": "kick", "glint": "C"}, {"track": "level", "glow": "C"}, {"track": "kick", "pulse": "Sun"}, {"track": "pad", "glow": "sky"}],
           "camera": [{"move": "arc", "subject": "Saturn", "over": ["bar 1", "bar 3 beat 2"]}, {"move": "zoom", "over": ["bar 3 beat 2", "bar 5"], "cut": True,
                      "stops": [{"subject": "C", "distance": 100}, {"subject": "Saturn", "distance": {"radii": 4}}]}],
           "finish": {"depth_of_field": True, "motion_blur": 3}, "scale": None}
    raw.pop("scale")
    for k, r in enumerate((RINGS, TRANSFER, HOLE, raw)):
        (tmp_path / f"p{k}.mjs").write_text(page(space, r), encoding="utf-8")
        done = subprocess.run([node, "--check", str(tmp_path / f"p{k}.mjs")], capture_output=True, text=True, timeout=60, check=False)
        assert done.returncode == 0, done.stderr[-1500:]


# ----- the runtime helpers in Node ------------------------------------------------------------------------


def test_the_scene_helpers_in_node(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    names = ("music-time", "space-camera", "space-scene")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text("""
import * as S from 'vidgen/space-scene'; import {spaceCamera} from 'vidgen/space-camera';
const out = {}, err = (f) => { try { f(); return null; } catch (e) { return e.message; } };
const ctx = {music: {t0: 10, score: {bar: 2, beat: 0.5}}};
out.bars = [S.sceneTime(ctx, 3), S.sceneTime(ctx, {bar: 9, beat: 1}), S.sceneTime(ctx, {bar: 9, beat: 3})];
out.noScore = err(() => S.sceneTime({}, {bar: 2}));
const W = S.freeSubject('World', [0, 0, 0], 6.371e6), cam = spaceCamera({sun: [1, 0.2, 0.3], up: [0, 0, 1], bodies: [W]});
const arc = (t) => cam.arc(t, {subject: W, phase: 'three-quarter', distance: {radii: 4}, over: [0, 4]});
const fly = (t) => cam.flyBy(t, {subject: W, over: [4, 8], closest: {radii: 2}});
out.jump = err(() => S.moveTrack([{name: 'camera[1] (arc)', start: 0, shot: arc}, {name: 'camera[2] (fly-by)', start: 4, shot: fly}]));
const view = S.moveTrack([{name: 'a', start: 0, shot: arc}, {name: 'b', start: 4, cut: true, shot: fly}]);
out.picks = [view(1).move, view(3.99).move, view(4).move, view(7).move];
const same = S.moveTrack([{name: 'a', start: 0, shot: arc}, {name: 'b', start: 4, shot: (t) => cam.arc(t, {subject: W, phase: 'three-quarter', distance: {radii: 4}, over: [0, 4]})}]);
out.joins = same(5).move;
out.order = err(() => S.moveTrack([{name: 'a', start: 2, shot: arc}, {name: 'b', start: 1, cut: true, shot: fly}]));
globalThis.__vidgenNotes = undefined;
out.checks = S.checkMoves(cam, [{name: 'camera[1] (arc)', start: 0, shot: (t) => cam.arc(t, {subject: W, phase: 'half', distance: 3e6})}], 2, {fps: 10});
out.notes = globalThis.__vidgenNotes.length;
const music = {time: (t) => t + 1, level: (T) => T / 10, events: (name) => name === 'kick' ? [{time: 1.5, gain: 1}, {time: 2.5, gain: 0.5}] : [], score: {bar: 2, beat: 0.5}, t0: 1};
const kick = S.reaction(music, {on: 'kick', kind: 'hits', decay: 0.2});
out.kick = [kick(0), kick(0.5), kick(0.7), kick(1.5)];
out.level = S.reaction(music, {on: 'level', kind: 'level'})(2);
console.log(JSON.stringify(out));
""", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    got = json.loads(done.stdout)
    assert got["bars"] == [3, 6, 7] and "has no score" in got["noScore"]
    assert "camera[2] (fly-by) does not start where camera[1] (arc) leaves the camera at 4.00 s" in got["jump"] and "cut: true" in got["jump"]
    assert got["picks"] == ["arc", "arc", "flyBy", "flyBy"] and got["joins"] == "arc" and "time order" in got["order"]
    assert any("inside World" in c for c in got["checks"]) and got["notes"] >= 1
    assert got["kick"][0] == 0 and got["kick"][1] == pytest.approx(1, abs=1e-6) and got["kick"][2] == pytest.approx(0.3679, abs=1e-3)
    assert got["level"] == pytest.approx(0.3)


# ----- the project: validate, space-page, lint, music plan -------------------------------------------------


def _project(make_project: Any, scenes: list[dict[str, Any]], **extra: Any) -> Path:
    return make_project(minimal_config(scenes=scenes, **extra))


def test_validate_checks_the_script_file(make_project: Any) -> None:
    root = _project(make_project, [{"id": "s", "type": "space", "duration": 4, "params": {**RINGS, "script": "extensions/more.js"}}])
    problems, _ = validate_all(Project.load(root), keep_going=True)
    assert any("script: file not found: extensions/more.js" in str(p) for p in problems)
    (root / "extensions").mkdir()
    (root / "extensions" / "more.js").write_text("export function setup(S) {}\n", encoding="utf-8")
    problems, _ = validate_all(Project.load(root), keep_going=True)
    assert not problems, problems


def test_space_page_writes_a_web_scene(make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(make_project, [{"id": "rings", "type": "space", "duration": 8, "params": RINGS}, {"id": "card", "type": "text_card", "duration": 2, "params": {"text": "x"}}])
    assert main(["space-page", str(root), "--scene", "rings"]) == 0
    out = capsys.readouterr().out
    page_text = (root / "extensions" / "rings.js").read_text(encoding="utf-8")
    assert page_text.startswith("// Written out by `vidgen space-page`") and "export async function load(ctx)" in page_text
    scene = yaml.safe_load(out[out.index("- id: rings"):])[0]
    assert scene == {"id": "rings", "type": "web", "duration": 8.0, "params": {"script": "extensions/rings.js", "data": {"scene_seconds": 7.5}}}
    assert main(["space-page", str(root), "--scene", "rings"]) == 1 and "exists already" in capsys.readouterr().err
    assert main(["space-page", str(root), "--scene", "ringz"]) == 1 and "did you mean 'rings'" in capsys.readouterr().err
    assert main(["space-page", str(root), "--scene", "card"]) == 1 and "is a text_card scene" in capsys.readouterr().err
    orbit = _project(make_project, [{"id": "t", "type": "space", "duration": 6, "params": TRANSFER}], )
    assert main(["space-page", str(orbit), "--scene", "t", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["web_scene"]["params"]["orbit_data"]["transfer"] == {"ship": "Ship", "to": "Geo"}


def _lint(make_project: Any, scene: dict[str, Any]) -> list[tuple[str, str]]:
    from vidgen.lint.orbit_rule import orbit_issues
    from vidgen.lint.space_rule import space_issues

    project = Project.load(_project(make_project, [scene]))
    rules = project.config.lint.rules
    return sorted((f.rule, f.message) for f in [*space_issues(project, scene["id"], rules), *orbit_issues(project, scene["id"], rules)])


def test_lint_a_fast_globe_an_enlarged_body_and_to_scale(make_project: Any, builtins_loaded: None) -> None:
    fast = {"orbits": {"central": "sun", "bodies": [{"preset": "earth"}, {"preset": "moon", "around": "Earth"}], "speedup": 3e6},
            "bodies": [{"name": "Earth"}, {"name": "Moon"}], "scale": {"mode": "enlarged", "enlarge": {"default": 1, "Earth": 80}},
            "camera": {"move": "arc", "subject": "Earth"}}
    found = _lint(make_project, {"id": "f", "type": "space", "params": fast, "beats": [{"text": "Here everything is drawn to scale, sizes too."}]})
    rules = [r for r, _ in found]
    assert rules.count("space_scene") == 2 and "orbit_scale" in rules
    text = " | ".join(m for _, m in found)
    assert "Earth: under the orbit data's speed-up it turns" in text and "Earth enlarged 80 times reaches past Moon's middle" in text
    assert "the bodies are drawn enlarged" in text
    calm = {**fast, "orbits": {**fast["orbits"], "speedup": 600}, "scale": None}
    calm.pop("scale")
    assert _lint(make_project, {"id": "c", "type": "space", "params": calm, "beats": [{"text": "Everything here is to scale."}]}) == []
    inside = {**RINGS, "bodies": [{"name": "Saturn"}, {"name": "Titan", "world": "titan", "at": ["30000 km", 0, 0]}]}
    assert [r for r, _ in _lint(make_project, {"id": "i", "type": "space", "duration": 4, "params": inside})] == ["space_scene"]


def test_music_plan_proposes_space_scenes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.music_space_plan import colour_family, space_plan_yaml
    from vidgen.music_video_plan import plan_music_video

    score = ROOT / "examples" / "signal-fire" / "assets" / "music" / "signal_fire.yaml"
    plan = plan_music_video(score)
    a, b = space_plan_yaml(plan, "assets/music/signal_fire.yaml", 1), space_plan_yaml(plan, "assets/music/signal_fire.yaml", 1)
    assert a == b and space_plan_yaml(plan, "assets/music/signal_fire.yaml", 2) != a
    assert colour_family("#f8761f") == "gold" and colour_family("#3060e0") == "blue" and colour_family("#808080") == "pale"
    assert main(["music", "plan", str(score), "--style", "space", "--out", str(tmp_path / "film")]) == 0
    out = capsys.readouterr().out
    assert "space scenes (seed 1):" in out and "(3 space scenes)" in out
    config = yaml.safe_load((tmp_path / "film" / "video.yaml").read_text(encoding="utf-8"))
    kinds = {s["type"] for s in config["scenes"]}
    assert kinds == {"space"} and all(s["params"]["fade"] is False and s["params"]["camera"]["over"][0].startswith("bar ") for s in config["scenes"])
    assert config["scenes"][0]["params"]["title"]["title"] == "Signal Fire" and "end_card" in config["scenes"][-1]["params"]
    assert not (tmp_path / "film" / "extensions").exists()


@pytest.mark.slow
@pytest.mark.render
def test_a_space_scene_draws_in_chromium(make_project: Any, tmp_path: Path) -> None:
    """The page written from the params draws (sky, world, light, camera, finish) and its notes reach the log."""
    from vidgen.web.still import make_web_stills
    from vidgen.web.still import Moment

    root = _project(make_project, [{"id": "rings", "type": "space", "duration": 2, "params": RINGS}])
    result = make_web_stills(root, "rings", moments=[Moment("at", 1.0)], count=None, size="160x90", variant=None, out=tmp_path / "s.png",
                             sheet=None, columns=None, exact=False, transparent=False)
    from PIL import Image

    with Image.open(result.stills[0].path) as im:
        assert im.size == (160, 90) and max(im.convert("L").getdata()) > 100
    assert (root / "build" / "space" / "rings.js").is_file()
