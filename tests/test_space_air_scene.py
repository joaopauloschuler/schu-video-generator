"""Step 392: the `space` scene reaches the pictures of Phase AO (DESIGN.md §123.14): a surface scene
(``world:``: the joined world of vidgen/space-descent, flights, planes, effects, the air moves) and an
orbital scene with giant hulls, planes, kit-built craft, the moves beside a ship, flashes, match cuts and
a warp across a cut. Its words checked in Python with did-you-mean, the cross-checks, the pages written
(stable, readable, valid JavaScript, run in Node with stand-ins for the drawing modules), the flights
and their cache key, ``vidgen space-page``, the one registry of names, the music plan's new style, MCP,
the lint's cost estimate. Chromium stills are ``slow``."""

from __future__ import annotations

import copy
import hashlib
import json
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
from conftest import minimal_config

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "src" / "vidgen" / "data" / "web" / "modules"

FLIGHT = {"name": "Plane", "start": {"x": -6000, "z": 2000, "above_ground": 600, "heading": 70, "speed": 140},
          "legs": [{"follow": {"clearance": 300}, "for": 12}, {"turn": {"by": 60, "bank": 35}, "follow": {"clearance": 300}}]}
#: The guide's surface example: a plane chased over the alpine range under fair clouds with a contrail.
CHASE = {"world": {"land": "alpine", "clouds": "fair", "sun": [24, 250]}, "flights": [FLIGHT],
         "craft": [{"name": "Plane", "plane": "glider", "seed": 7, "fly": "Plane", "effects": {"contrails": {"always": True}}}],
         "camera": {"move": "chase", "flight": "Plane", "lens": "wide-normal"}}
#: A skim over the sea at sunset (no flight).
SKIM = {"world": {"sea": "breeze", "sun": [5, 300]}, "camera": {"move": "skim", "heading": 284, "speed": 90, "clearance": 14, "turn": 14, "lens": "wide"}}
#: From orbit to a skim over the sea, in one shot.
DESCENT = {"world": {"planet": "earth", "at": [8, -150], "sun": [38, 250], "sea": {"state": "breeze", "seed": 3}, "clouds": {"sky": "fair", "seed": 4}},
           "camera": [{"move": "descend", "over": [0, 10], "from": "400 km", "to": 300, "heading": 300, "turn": 30, "speed": 90, "lens": ["normal", "wide"]},
                      {"move": "skim", "over": [10, 14], "continues": True}]}
#: The guide's orbital example: a dressed carrier, a pass along its hull, a craft into a bay.
CARRIER = {"orbits": {"central": "earth", "speedup": 1, "bodies": [{"name": "Carrier", "altitude": "900 km"}]}, "bodies": [{"name": "Earth"}],
           "craft": [{"name": "Carrier", "hull": "carrier", "seed": 1, "length": 3200, "dress": {"plumes": "bank"},
                      "scale_ref": {"kind": "ship", "at": "hangar-2", "into": {"hangar": "hangar-2", "over": [8, 16]}}}],
           "camera": [{"move": "hull-pass", "ship": "Carrier", "over": [0, 8], "side": "port", "standoff": 60, "from": 0.3, "speed": 40},
                      {"move": "into-bay", "ship": "Carrier", "hangar": "hangar-2", "over": [8, 16], "cut": True}]}
#: A free hull beside a world, a plane, a kit-built craft, a flash, a warp across a cut and a match cut.
MIXED = {"sky": {"seed": 4}, "sun": {"direction": [1, -0.3, 0.25]}, "music_data": True,
         "bodies": [{"name": "Saturn"}],
         "craft": [{"name": "Ark", "hull": "ark", "seed": 2, "at": ["70000 km", 0, 0], "dress": False},
                   {"name": "Glider", "plane": "glider", "seed": 3, "at": ["70000 km", "4 km", 0], "effects": {"exhaust": True}, "throttle": 0.6},
                   {"name": "Mine", "parts": {"part": "hull", "shape": "prism", "sides": 8, "radius": 1, "length": 1.4, "skin": "foil",
                                              "attach": [{"at": "fore", "part": "dish", "diameter": 3}, {"around": {"count": 2, "along": 0.5}, "part": "solar-wing", "panels": 3}]},
                    "at": ["70000 km", "-3 km", 0]}],
         "phenomena": [{"kind": "warp", "name": "Jump", "cut": {"at": "bar 5", "seconds": 3}}],
         "flash": [{"at": "bar 5", "amount": 2}],
         "music": [{"track": "kick", "glow": "Glider", "as": "boost"}],
         "camera": [{"move": "arc", "subject": "Saturn", "over": ["bar 1", "bar 3"], "distance": {"radii": 6}},
                    {"move": "arc", "subject": "Ark", "over": ["bar 3", "bar 5"], "cut": True, "match": "Saturn", "distance": {"radii": 3}}]}


@pytest.fixture
def space() -> Any:
    extensions.load_builtins()
    return registry.get("space").cls


def params(space: Any, raw: dict[str, Any]) -> Any:
    return space.Params.model_validate(copy.deepcopy(raw))


def problem(space: Any, raw: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as caught:
        params(space, raw)
    return str(caught.value)


def page(space: Any, raw: dict[str, Any], scene_id: str = "s") -> str:
    from vidgen.scenes.space import page_source

    return page_source(params(space, raw), scene_id)


# ----- the words ---------------------------------------------------------------------------------------


def test_the_examples_validate(space: Any) -> None:
    for raw in (CHASE, SKIM, DESCENT, CARRIER, MIXED):
        params(space, raw)
    p = params(space, CHASE)
    assert p.world.land_spec.preset == "alpine" and p.world.cloud_spec.sky == "fair" and p.craft[0].maker == "plane"
    assert params(space, {**SKIM, "camera": {"move": "climbThrough", "deck": 0}, "world": {"clouds": "overcast"}}).camera[0].move == "climb-through"
    assert params(space, CARRIER).camera[0].move == "hull-pass" and params(space, MIXED).craft[2].parts["attach"][1]["part"] == "solarWing"


@pytest.mark.parametrize("change,words", [
    ({"world": {"land": "alpne"}}, "did you mean 'alpine'"),
    ({"world": {"sea": "rogh"}}, "did you mean 'rough'"),
    ({"world": {"sea": {"state": "storm", "watr": "grey"}}}, "did you mean 'water'"),
    ({"world": {"sea": {"water": "tropicl"}}}, "did you mean 'tropical'"),
    ({"world": {"land": "alpine", "clouds": "ovrcast"}}, "did you mean 'overcast'"),
    ({"world": {"land": "alpine", "clouds": {"decks": [{"type": "cumulos"}]}}}, "did you mean 'cumulus'"),
    ({"world": {"land": "alpine", "clouds": {"sky": "fair", "lightning": {"pwer": 2}}}}, "did you mean 'power'"),
    ({"world": {"land": {"preset": "alpine", "mountians": {"height": 3000}}}}, "did you mean 'mountains'"),
    ({"world": {"land": "alpine", "air": "erth"}}, "did you mean 'earth'"),
    ({"world": {"land": "alpine", "planet": "marz"}}, "did you mean 'mars'"),
    ({"world": {"land": "alpine", "exposure": "flim"}}, "did you mean 'film'"),
    ({"world": {"land": "alpine", "handover": "lo"}}, "did you mean 'low'"),
    ({"world": {"land": "alpine", "sun": {"date": "2026-06-21"}}}, "give both date and utc"),
    ({"craft": [{"name": "Plane", "plane": "glidr", "fly": "Plane"}]}, "did you mean 'glider'"),
    ({"craft": [{"name": "Plane", "plane": "glider", "fly": "Plane", "wnig": {"sweep": 40}}]}, "did you mean 'wing'"),
    ({"craft": [{"name": "Plane", "plane": "glider", "fly": "Plane", "effects": {"contrail": True}}]}, "contrail"),
    ({"craft": [{"name": "Plane", "plane": "glider", "fly": "Plane", "effects": {"reentry": {"ful": 0.5}}}]}, "did you mean 'full'"),
    ({"craft": [{"name": "Plane", "plane": "glider", "fly": "Plan"}]}, "did you mean 'Plane'"),
    ({"camera": {"move": "chace", "flight": "Plane"}}, "did you mean 'chase'"),
    ({"camera": {"move": "chase", "flight": "Plain"}}, "did you mean 'Plane'"),
    ({"camera": {"move": "chase", "flight": "Plane", "distnce": 40}}, "did you mean 'distance'"),
    ({"camera": {"move": "wing", "flight": "Plane", "view": "wingtp"}}, "did you mean 'wingtip'"),
    ({"camera": {"move": "climb-through", "deck": "cumulos"}}, "did you mean 'cumulus'"),
    ({"camera": {"move": "climb-through", "deck": 5}}, "the clouds have 2 deck(s)"),
    ({"operator": {"hand": "handhled"}}, "did you mean 'handheld'"),
    ({"operator": {"hand": {"style": "mounted", "vibraton": 0.1}}}, "did you mean 'vibration'"),
    ({"operator": {"exposure": {"hunts": 1}}}, "did you mean 'hunt'"),
    ({"operator": {"horizn": True}}, "did you mean 'horizon'"),
])
def test_surface_mistakes_are_named_with_the_closest_word(space: Any, change: dict[str, Any], words: str) -> None:
    raw = copy.deepcopy(CHASE)
    if "world" in change:
        raw["world"] = change["world"]
    raw.update({k: v for k, v in change.items() if k != "world"})
    assert words in problem(space, raw)


@pytest.mark.parametrize("change,words", [
    ({"craft": [{"name": "Carrier", "hull": "carier"}]}, "did you mean 'carrier'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "palete": "bone"}]}, "did you mean 'palette'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "palette": "bon"}]}, "did you mean 'bone'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "length": 50}]}, "200 m to 20 km"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "dress": {"plums": "bank"}}]}, "did you mean 'plumes'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "dress": {"plumes": "banks"}}]}, "did you mean 'bank'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "scale_ref": {"kind": "shipp"}}]}, "did you mean 'ship'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "scale_ref": {"at": "hanger-2"}}]}, "did you mean 'hangar-1'"),
    ({"craft": [{"name": "Carrier", "hull": "carrier", "kind": "ship"}]}, "not both"),
    ({"craft": [{"name": "Carrier", "hull": ["carrier", "spine"]}]}, "give fleet: N"),
    ({"camera": {"move": "hull-pas", "ship": "Carrier"}}, "did you mean 'hull-pass'"),
    ({"camera": {"move": "hull-pass", "ship": "Carier"}}, "did you mean 'Carrier'"),
    ({"camera": {"move": "into-bay", "ship": "Carrier", "hangar": "hangr-2"}}, "did you mean 'hangar-1'"),
    ({"camera": {"move": "hull-pass", "ship": "Carrier", "standof": 60}}, "did you mean 'standoff'"),
    ({"craft": [{"name": "P", "parts": {"part": "hul"}, "fly": "Carrier"}]}, "did you mean 'hull'"),
    ({"phenomena": [{"kind": "warp", "cut": {"at": 3, "secs": 2}}]}, "did you mean 'seconds'"),
])
def test_orbital_mistakes_are_named_with_the_closest_word(space: Any, change: dict[str, Any], words: str) -> None:
    assert words in problem(space, {**CARRIER, **change})


@pytest.mark.parametrize("raw,words", [
    ({**SKIM, "world": {"sun": [5, 300]}}, "a skim flies low over ground or water"),
    ({**SKIM, "camera": {"move": "chase"}}, "add flights:"),
    ({**SKIM, "camera": {"move": "climb-through"}}, "give world.clouds, or deck: {base, top}"),
    ({**SKIM, "camera": {"move": "orbit-peak"}}, "circles a peak of the ground: give world.land"),
    ({**SKIM, "camera": {"move": "orbit-peak", "around": {"tower": 0}}}, "needs cloud towers"),
    ({**CHASE, "craft": [{"name": "Plane", "plane": "glider"}]}, "give fly: the flight it flies"),
    ({**CHASE, "camera": {"move": "hull-pass"}}, "is a move beside a giant ship"),
    ({**CHASE, "camera": {"move": "arc", "subject": "Plane"}}, "is a move of an orbital scene"),
    ({**CHASE, "bodies": [{"name": "Earth"}]}, "bodies: is an orbital scene's"),
    ({**CHASE, "sun": {"kind": "orange"}}, "the sun of a surface scene is world.sun"),
    ({**CHASE, "craft": [{"name": "Plane", "hull": "carrier", "fly": "Plane"}]}, "a giant hull belongs to an orbital scene"),
    ({**CHASE, "craft": [{"name": "Plane", "plane": "glider", "fly": "Plane", "at": [0, 0, 0]}]}, "at is an orbital scene's"),
    ({**CARRIER, "flights": [FLIGHT]}, "flights: are a surface scene's"),
    ({**CARRIER, "camera": {"move": "skim"}}, "is a move in the air"),
    ({**CARRIER, "camera": {"move": "hull-pass", "standoff": 4}}, "closer to the hull than 10 m"),
    ({**CARRIER, "camera": {"move": "arc", "subject": "Carrier", "distance": 300}}, "is inside the hull"),
    ({**CARRIER, "craft": [{"name": "Carrier", "hull": "carrier", "effects": {"exhaust": True}}]}, "a hull's bells fire by throttle"),
    ({**CARRIER, "craft": [{"name": "Carrier", "kind": "ship", "effects": {"contrails": True}}], "camera": {"move": "follow", "subject": "Carrier"}}, "follow a flight through air"),
    ({**CARRIER, "craft": [{"name": "Carrier", "kind": "ship"}], "camera": {"move": "hull-pass"}}, "needs a hull among craft"),
    ({**CARRIER, "craft": [{"name": "Carrier", "hull": "carrier", "dress": False, "scale_ref": {"into": {"hangar": "hangar-2", "over": [0, 4]}}}]}, "it needs dress"),
    ({**SKIM, "camera": {"move": "skim", "over": ["bar 1", "bar 5"]}}, "need the score on the page"),
    ({**CHASE, "flash": [{"at": 4}]}, "add finish"),
    ({**CHASE, "music_data": True, "music": [{"track": "kick", "pulse": "lightnin"}]}, "did you mean 'lightning'"),
    ({**SKIM, "music_data": True, "music": [{"track": "kick", "pulse": "lightning"}]}, "lightning needs clouds"),
    ({**CHASE, "music_data": True, "music": [{"track": "level", "glow": "lava"}]}, "lava glows on volcanic ground"),
    ({**CHASE, "music_data": True, "music": [{"track": "kick", "glow": "Plane", "as": "rcs"}]}, "a craft in the air takes lights, throttle, boost or pulse"),
    ({**MIXED, "camera": [{"move": "arc", "subject": "Saturn", "over": [0, 2], "match": "Saturn", "cut": True}]}, "the first move has none"),
    ({**DESCENT, "camera": [{"move": "skim", "continues": True, "over": [0, 4]}]}, "continues follows a descend"),
])
def test_cross_checks(space: Any, raw: dict[str, Any], words: str) -> None:
    assert words in problem(space, raw)


def test_times_in_bars_and_the_sun_on_a_date(space: Any) -> None:
    from vidgen.scenes.space_air_params import sun_of_date

    noon = sun_of_date("2026-06-21", "12:00", [51.48, 0.0])     # Greenwich at midsummer noon: the Sun about 62 degrees up, due south
    assert noon[0] == pytest.approx(62.0, abs=0.6) and noon[1] == pytest.approx(180, abs=3)
    dusk = sun_of_date("2026-12-21", "15:50", [51.48, 0.0])
    assert -2 < dusk[0] < 4 and 220 < dusk[1] < 240
    raw = {**CHASE, "music_data": True, "camera": [{"move": "chase", "flight": "Plane", "over": ["bar 1", "bar 3 beat 2"]},
                                                     {"move": "fly-past", "flight": "Plane", "over": ["bar 3 beat 2", "bar 6"], "at": "bar 5", "cut": True}]}
    text = page(space, raw)
    assert '"over": [T({"bar": 1, "beat": 1}), T({"bar": 3, "beat": 2})]' in text and '"at": T({"bar": 5, "beat": 1})' in text
    dated = page(space, {**CHASE, "world": {"land": "alpine", "sun": {"date": "2026-06-21", "utc": "16:00"}}})
    assert '"sun": [' in dated


# ----- the pages ---------------------------------------------------------------------------------------


def test_the_pages_are_stable_and_say_what_the_params_say(space: Any) -> None:
    for raw in (CHASE, SKIM, DESCENT, CARRIER, MIXED):
        a, b = page(space, raw), page(space, raw)
        assert a == b and "Math.random" not in a and "Date(" not in a and "performance" not in a
    chase = page(space, CHASE)
    assert 'S.world = world(renderer, {"sun": [24, 250], "land": {"preset": "alpine"}, "clouds": {"sky": "fair", "seed": 1}' in chase
    assert 'S.craft["Plane"] = plane("glider", {"detail": "near", "seed": 7}).fly(ctx.flight, {flight: "Plane"});' in chase
    assert '"contrails": {"always": true}' in chase and 'S.cam.chase(t, {"flight": "Plane", "lens": "wide-normal"' in chase
    assert "checkMoves(S.cam, S.moves, S.seconds, {fps: 6});" in chase and "S.world.problems(camera)" in chase
    descent = page(space, DESCENT)
    assert '"from": 400000' in descent and '"lens": ["normal", "wide"]' in descent and "S.ends[1] = S.moves[0].shot(10).end" in descent
    carrier = page(space, CARRIER)
    assert '"near": 4' in carrier and "set by vidgen because a giant hull is in the scene" in carrier
    assert 'hull("carrier", {"length": 3200' in carrier and 'dress(S.craft["Carrier"], renderer, {"plumes": "bank"})' in carrier
    assert 'S.cam.hullPass(t, {"ship": "Carrier"' in carrier and 'S.detail["Carrier"].fly(S.refs["Carrier"], "hangar-2"' in carrier
    mixed = page(space, MIXED)
    assert "kit.hull(" in mixed and "attach(p0, \"fore\", p1, \"mount\")" in mixed and "around(p0, () => kit.solarWing(" in mixed
    assert "warpCut(t, T(" in mixed and "flash: (t) => flashes(t, [" in mixed and "matchDisc(" in mixed and '"boost": Math.min(1' in mixed


@pytest.mark.parametrize("raw,path,value", [
    (CHASE, ("world", "sun"), [30, 250]), (CHASE, ("world", "land"), "mars"), (CHASE, ("world", "clouds"), "overcast"),
    (CHASE, ("world", "quality"), "fast"), (CHASE, ("craft", 0, "seed"), 8), (CHASE, ("craft", 0, "plane"), "skiff"),
    (CHASE, ("craft", 0, "effects"), {"vapour": True}), (CHASE, ("craft", 0, "gear"), 1), (CHASE, ("camera", "distance"), 90),
    (CHASE, ("flights", 0, "start", "speed"), 150), (CHASE, ("seed",), 3), (CHASE, ("sky", "seed"), 9),
    (CARRIER, ("craft", 0, "seed"), 2), (CARRIER, ("craft", 0, "dress"), {"plumes": "both"}), (CARRIER, ("camera", 0, "standoff"), 80),
    (CARRIER, ("craft", 0, "scale_ref", "kind"), "tug"), (CARRIER, ("flash",), [{"at": 8}]),
    (SKIM, ("operator",), {"hand": "handheld"}), (SKIM, ("operator",), {"exposure": 0.5}), (SKIM, ("operator",), {"horizon": {"degrees": 2}}),
    (CARRIER, ("operator",), {"hand": "mounted"}),
])
def test_every_new_param_changes_the_page(space: Any, raw: dict[str, Any], path: tuple[Any, ...], value: Any) -> None:
    changed = copy.deepcopy(raw)
    target: Any = changed
    for key in path[:-1]:
        target = target.setdefault(key, {}) if isinstance(key, str) else target[key]
    target[path[-1]] = value
    assert page(space, changed) != page(space, raw)


def test_existing_space_scenes_write_the_same_pages(space: Any) -> None:
    """Outbound's five scenes and Step 376's demos: the generated page text is byte-identical to Step 391's (hashes
    taken at commit 1d1f7fb before this step's change)."""
    from test_space_scene import HOLE, RINGS, TRANSFER

    before = {"01_dawn": "4ed80c6ff2621a06627dc640e5bbcb882f18009d125605247ab383933e7530a5",
              "02_depart": "27e79b87f4b0e9a5a3283092258993cb0f1794f3eccc850391dab999cd9d88a8",
              "03_rings": "b2982b3bb00792f38c71520bcc6c5043252167224189750961362b304b375e16",
              "04_jump": "bf1a81b60ee367be16140dd3816a00b30eb6d036650c7cb86e7bf3be5087b1b5",
              "05_horizon": "45430b9b2bd9b31bfbbbf18604c49616f59ad89176cc7e139a3dc6fcb9832e84",
              "RINGS": "6ecf4574031693dc7d1cfeecd07b28d1bd44f2a91cafe15587542c8a4f512d6f",
              "TRANSFER": "4264d7035b4d9e646bb8815f4fd1f3e71d0bea7c998acfd32e1d515f6913ce58",
              "HOLE": "27c741d74b9c08737f5622135bff1a04077e74efd3034adecfd3640852433a5d"}
    project = Project.load(ROOT / "examples" / "outbound")
    got = {s.id: hashlib.sha256(page(space, s.params, s.id).encode("utf-8")).hexdigest() for s in project.config.scenes if s.type == "space"}
    for name, raw in (("RINGS", RINGS), ("TRANSFER", TRANSFER), ("HOLE", HOLE)):
        got[name] = hashlib.sha256(page(space, raw).encode("utf-8")).hexdigest()
    assert got == before


def test_the_pages_import_only_shipped_modules_and_are_valid_javascript(space: Any, tmp_path: Path) -> None:
    import re

    from vidgen.web.loaded import VIDGEN_MODULES

    node = shutil.which("node")
    for k, raw in enumerate((CHASE, SKIM, DESCENT, CARRIER, MIXED)):
        text = page(space, raw)
        for module in re.findall(r'from "([^"]+)"', text):
            assert module == "three" or module in VIDGEN_MODULES, module
        if node is not None:
            (tmp_path / f"p{k}.mjs").write_text(text, encoding="utf-8")
            done = subprocess.run([node, "--check", str(tmp_path / f"p{k}.mjs")], capture_output=True, text=True, timeout=60, check=False)
            assert done.returncode == 0, done.stderr[-1500:]


STANDINS = {
    "three": """
export class Color { constructor(c) { this.c = c; } }
export class Scene { constructor() { this.children = []; } add(...o) { this.children.push(...o); } }
export class WebGLRenderer { constructor(o) { this.o = o; } setSize() {} setRenderTarget() {} render() { globalThis.__draws = (globalThis.__draws ?? 0) + 1; } }
export class PerspectiveCamera {
  constructor(fov, aspect, near, far) { Object.assign(this, {fov, aspect, near, far, isCamera: true}); const v = () => ({set: (...a) => { v.last = a; }}); this.position = {set: (...a) => { this.at = a; }}; this.quaternion = {set: (...a) => { this.q = a; }}; }
  updateMatrixWorld() {} updateProjectionMatrix() {}
}
""",
    "vidgen/space-sky": "export const spaceSky = (r, o) => ({object: {name: 'stars'}, options: o});\n",
    "vidgen/space-descent": """
export function world(renderer, o) {
  globalThis.__world = o;
  const sky = {model: {radius: 6.371e6, H: 8500}, options: {unit: 1}, haze: (m) => m};
  const ground = o.land ? {heightAt: () => 300, above: (p) => p[1] - 300} : null;
  const water = o.sea ? {heightAt: () => 0, list: {waves: []}} : null;
  const clouds = o.clouds ? {decks: [{name: "cumulus", base: 1000, top: 2100}, {name: "cirrus", base: 9500, top: 10100}], towers: []} : null;
  return {object: {name: 'world'}, sky, ground, update: (t, {camera}) => { globalThis.__updates = (globalThis.__updates ?? 0) + 1; },
    problems: () => [], get rig() { return {sky, ...(ground ? {ground} : {}), ...(water ? {water} : {}), ...(clouds ? {clouds} : {})}; }};
}
""",
    "vidgen/space-plane": """
export function plane(kind, o) {
  const p = {kind, o, object: {name: kind}, materials: {a: {}}, size: {length: 26, width: 18, radius: 14}, anchors: {wingTips: [{p: [9, 0, -5]}, {p: [-9, 0, -5]}]},
    fly(f, {flight}) { this.flight = flight; return this; }, update(t, u) { globalThis.__planeUpdates = (globalThis.__planeUpdates ?? []).concat([u]); return this; }};
  return p;
}
""",
    "vidgen/space-effects": "export const effects = (craft, o) => ({o, object: {}, update(t, u) { globalThis.__fx = o; return this; }});\n",
}


def _node_page(tmp_path: Path, text: str) -> dict[str, Any]:
    """Run a surface page's load(ctx) and frame(t) in Node: the real camera modules (vidgen/space-camera-air,
    -camera, -scene, -scene-air, music-time), stand-ins for three.js and the drawing modules."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    real = ("music-time", "space-camera", "space-camera-air", "space-scene", "space-scene-air")
    for name in real:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    stand = {k.split("/", 1)[1]: v for k, v in STANDINS.items() if k.startswith("vidgen/")}
    for name, source in stand.items():
        (ours / f"{name}.js").write_text(source, encoding="utf-8")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in (*real, *stand)}}), encoding="utf-8")
    three = tmp_path / "node_modules" / "three"
    three.mkdir()
    (three / "index.js").write_text(STANDINS["three"], encoding="utf-8")
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "main": "index.js"}), encoding="utf-8")
    (tmp_path / "page.mjs").write_text(text, encoding="utf-8")
    (tmp_path / "run.mjs").write_text("""
import * as P from './page.mjs';
const flight = {names: ['Plane'], position: (n, t) => [-6000 + 140 * t, 900, 2000], velocity: () => [140, 0, 0], quaternion: () => [0, 0, 0, 1], bank: () => 0};
const ctx = {canvas: {}, width: 320, height: 180, fps: 30, duration: 8, data: {scene_seconds: 8}, flight, theme: {sizes: {}, fonts: {}}};
await P.load(ctx);
const shots = [0, 2, 4.5].map((t) => { P.frame(t); const s = P.S.shot; return {move: s.move, from: s.from, fov: s.fov}; });
console.log(JSON.stringify({shots, world: globalThis.__world, draws: globalThis.__draws, updates: globalThis.__updates, planeUpdates: globalThis.__planeUpdates?.length ?? 0,
  fx: globalThis.__fx ? Object.keys(globalThis.__fx) : null, notes: globalThis.__vidgenNotes ?? []}));
""", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "run.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout)


def test_a_surface_page_runs_in_node_with_stand_ins(space: Any, tmp_path: Path) -> None:
    got = _node_page(tmp_path, page(space, CHASE))
    assert [s["move"] for s in got["shots"]] == ["chase", "chase", "chase"] and got["draws"] == 3 and got["updates"] >= 4
    assert got["world"]["land"] == {"preset": "alpine"} and got["world"]["sun"] == [24, 250] and got["fx"] and "contrails" in got["fx"]
    x0, x1 = got["shots"][0]["from"][0], got["shots"][2]["from"][0]
    assert x1 - x0 == pytest.approx(140 * 4.5, rel=0.05)                     # the camera follows the flight east at 140 m/s
    assert got["shots"][0]["from"][0] < -6000 + 140 * 0                         # behind the plane


def test_the_camera_operator_is_off_unless_given(space: Any, tmp_path: Path) -> None:
    """operator: (Step 399) reaches the page only when given (a page without it is unchanged: no operate line, the
    air's ev a number); on a surface scene the rig's meter drives the air's exposure through the shot's ev; every cut
    starts a shot; an orbital scene takes the hand and the horizon but not the exposure; the page runs in Node."""
    plain = page(space, SKIM)
    assert "operator" not in plain.split("export const PARAMS")[1].split("\n", 1)[1] and "operate" not in plain and '"ev": 0,' in plain
    given = page(space, {**SKIM, "operator": {"hand": "mounted", "exposure": True, "horizon": 1.5, "seed": 3}})
    assert 'S.view = S.cam.operator(S.view, {"hand": "mounted", "exposure": true, "horizon": 1.5, "seed": 3});' in given
    assert '"ev": () => (S.shot && Number.isFinite(S.shot.ev) ? S.shot.ev : 0) + 0,' in given
    hand = page(space, {**SKIM, "operator": {"hand": {"style": "handheld", "amount": 0.5}}})
    assert '"hand": {"style": "handheld", "amount": 0.5}' in hand and '"ev": 0,' in hand                  # no exposure: the air's ev untouched
    carrier = page(space, {**CARRIER, "operator": {"hand": True, "horizon": True}})
    assert 'import {airCamera, operate} from "vidgen/space-camera-air";' in carrier and 'S.view = operate(S.view, {"hand": true, "horizon": true, "cuts": [8]});' in carrier
    assert "operator.exposure is a surface scene's" in problem(space, {**CARRIER, "operator": {"exposure": True}})
    got, bare = _node_page(tmp_path / "a", given), _node_page(tmp_path / "b", plain)
    assert [s["from"] for s in got["shots"]] == [s["from"] for s in bare["shots"]] and [s["fov"] for s in got["shots"]] == [s["fov"] for s in bare["shots"]]


def test_a_descent_with_a_skim_runs_in_node(space: Any, tmp_path: Path) -> None:
    got = _node_page(tmp_path, page(space, {**DESCENT, "camera": [{**DESCENT["camera"][0], "over": [0, 4]}, {"move": "skim", "over": [4, 8], "continues": True}]}))
    moves = [s["move"] for s in got["shots"]]
    assert moves == ["descend", "descend", "skim"]
    assert got["shots"][0]["from"][1] > 3e5 and got["shots"][2]["from"][1] < 400       # from orbit to a low skim


def test_the_helper_module_in_node(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    names = ("music-time", "space-camera", "space-scene-air")
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text("""
import * as A from 'vidgen/space-scene-air';
const out = {};
out.ramp = [A.ramp(0, {over: [1, 3]}), A.ramp(2, {over: [1, 3]}), A.ramp(5, {over: [1, 3], from: 2, to: 4})];
out.flash = [A.flashes(-1, [{at: 0}]), A.flashes(0, [{at: 0, amount: 3}]), A.flashes(10, [{at: 0}])];
const music = {t0: 4, events: (n) => n === 'kick' ? [{time: 5, gain: 1}, {time: 6.5, gain: 0.5}] : []};
out.hits = A.hitTimes(music, 'kick');
let n = 0; const f = A.once(() => ++n); f(); f(); out.once = n;
try { A.ramp(0, {over: [3, 1]}); } catch (e) { out.bad = e.message; }
console.log(JSON.stringify(out));
""", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    got = json.loads(done.stdout)
    assert got["ramp"] == [0, 0.5, 4] and got["flash"] == [0, 3, 0] and got["hits"] == [1, 2.5] and got["once"] == 1 and "end after start" in got["bad"]


# ----- flights in the scene, its project, space-page ------------------------------------------------------


def test_flights_take_the_worlds_ground_and_their_key(space: Any) -> None:
    from vidgen.web.flights import flight_data_key

    land = params(space, CHASE).flights.data(params(space, CHASE).world)
    assert land.ground.kind == "land" and land.ground.land_options == {"preset": "alpine"}
    sea = params(space, {**CHASE, "world": {"sea": "rough", "sun": [10, 90]}, "camera": {"move": "chase"}})
    data = sea.flights.data(sea.world)
    assert data.ground.kind == "sea" and data.ground.sea.waves == 3.2 and data.anchor() == [0.0, 0.0]
    placed = params(space, {**CHASE, "world": {"land": "alpine", "at": [-34.0, 21.0]}})
    assert placed.flights.data(placed.world).ground.land_options["at"] == [-34.0, 21.0]
    a = flight_data_key(land, 30, 100, 98)
    faster = copy.deepcopy(CHASE)
    faster["flights"][0]["start"]["speed"] = 150
    b = flight_data_key(params(space, faster).flights.data(params(space, faster).world), 30, 100, 98)
    assert a != b and a == flight_data_key(params(space, CHASE).flights.data(params(space, CHASE).world), 30, 100, 98)


def _project(make_project: Any, scenes: list[dict[str, Any]], **extra: Any) -> Path:
    return make_project(minimal_config(scenes=scenes, **extra))


def test_a_flight_under_the_sea_level_is_an_error_with_the_scene_id(make_project: Any, space: Any) -> None:
    """Step 385's error surfaces with the scene's name when the frames are made (a sea ground: no page needed)."""
    from vidgen.errors import VidgenError
    from vidgen.scenes.space import scene_flights

    low = copy.deepcopy(CHASE)
    low["world"] = {"sea": "calm"}
    low["flights"] = [{"name": "Plane", "start": {"x": 0, "z": 0, "height": 60, "heading": 90, "speed": 120}, "legs": [{"descend": {"to": -50, "rate": 10}, "for": 30}]}]
    root = _project(make_project, [{"id": "under", "type": "space", "duration": 4, "params": low}])
    with pytest.raises(VidgenError) as caught:
        scene_flights(Project.load(root), "under", params(space, low), 30, 122, None)
    assert "space scene 'under'" in str(caught.value) and "flight Plane" in str(caught.value) and "under the 20 m it must keep" in str(caught.value)


def test_space_page_writes_both_kinds_out(make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(make_project, [{"id": "chase", "type": "space", "duration": 8, "params": CHASE},
                                   {"id": "carrier", "type": "space", "duration": 16, "params": CARRIER}])
    problems, _ = validate_all(Project.load(root), keep_going=True)
    assert not problems, problems
    assert main(["space-page", str(root), "--scene", "chase"]) == 0
    out = capsys.readouterr().out
    scene = yaml.safe_load(out[out.index("- id: chase"):])[0]
    assert scene["type"] == "web" and scene["params"]["flight_data"]["ground"] == {"land": {"preset": "alpine"}}
    assert scene["params"]["flight_data"]["flights"][0]["name"] == "Plane"
    text = (root / "extensions" / "chase.js").read_text(encoding="utf-8")
    assert text.startswith("// Written out by `vidgen space-page`") and "world(renderer, {" in text
    assert main(["space-page", str(root), "--scene", "carrier", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "orbit_data" in doc["web_scene"]["params"] and "flight_data" not in doc["web_scene"]["params"]


# ----- the registry of names, the plan, MCP, lint -------------------------------------------------------------


def test_one_registry_of_names_for_validation_the_guide_and_the_parts_sheet() -> None:
    import re

    from vidgen.web.space_names import PART_PREFIXES, yaml_names

    names = yaml_names()
    parts = set()
    for f in (ROOT / "src" / "vidgen" / "data" / "web" / "parts").glob("space-*.js"):
        parts |= set(re.findall(r'"name": "([a-z0-9-]+)"', f.read_text(encoding="utf-8")))
    # every name on the sheet that names a plane, a hull, a sea state, a ground, a cloud sky or a move is the YAML's word
    for key, prefix in PART_PREFIXES.items():
        listed = names[key] if key != "moves" else [*names["air_moves"], *names["ship_moves"]]
        shown = [p[len(prefix):] for p in parts if p.startswith(prefix)]
        assert any(s in listed for s in shown), key
        for word in listed:
            assert word == word.lower() and "_" not in word
    for word in [*names["planes"], *names["hulls"], *names["air_moves"], *names["ship_moves"], *names["land_presets"]]:
        prefix = "plane-" if word in names["planes"] else "hull-" if word in names["hulls"] else "land-" if word in names["land_presets"] else "camera-"
        assert f"{prefix}{word}" in parts or word in ("descend-through", "ascend"), word
    guide = (ROOT / "src" / "vidgen" / "data" / "guide" / "AGENTS.md").read_text(encoding="utf-8")
    for key in ("air_presets", "sea_states", "waters", "skies", "land_presets", "planes", "hulls", "palettes", "air_moves", "ship_moves", "wing_views"):
        assert ", ".join(names[key]) in guide, key


def test_music_plan_space_air_is_deterministic_and_space_is_unchanged(tmp_path: Path, space: Any) -> None:
    from vidgen.music_space_plan import space_plan_text, space_plan_yaml
    from vidgen.music_video_plan import plan_music_video

    score = ROOT / "examples" / "signal-fire" / "assets" / "music" / "signal_fire.yaml"
    plan = plan_music_video(score)
    old = space_plan_yaml(plan, "assets/music/x.yaml", 1) + space_plan_text(plan, 1)
    assert hashlib.sha256(old.encode()).hexdigest() == "326716a8d64d074c2caad9e4c002423b9a46ff672e0306fccd4012308a71f8a2"
    a = space_plan_yaml(plan, "assets/music/x.yaml", 1, style="space-air")
    assert a == space_plan_yaml(plan, "assets/music/x.yaml", 1, style="space-air") and a != space_plan_yaml(plan, "assets/music/x.yaml", 2, style="space-air")
    config = yaml.safe_load(a)
    for s in config["scenes"]:
        params(space, s["params"])
    kinds = {("world" in s["params"]) for s in config["scenes"]}
    assert kinds == {True, False} or kinds == {True}
    assert main(["music", "plan", str(score), "--style", "space-air", "--out", str(tmp_path / "film")]) == 0


def test_mcp_space_page_and_the_schema_know_the_new_keys(space: Any) -> None:
    schema = space.Params.model_json_schema()
    for key in ("world", "flights", "flash"):
        assert key in schema["properties"]
    text = (ROOT / "src" / "vidgen" / "mcp_server.py").read_text(encoding="utf-8")
    tool = text[text.index("async def space_page") - 900:text.index("async def space_page")]
    assert "world:" in tool and "hulls" in tool and "flight_data" in tool
    plan = text[text.index("async def music_plan"):text.index("async def audio_check")]
    assert '"space-air"' in plan and '"style": style if style != "web" else None' in plan
    from vidgen.mcp_tools import cli_args

    assert cli_args(["music"], ["plan", "x.yaml"], {"style": "space-air", "seed": 2})[3:5] == ["--style=space-air", "--seed=2"]


def test_the_lint_warns_of_costly_combinations(make_project: Any) -> None:
    from vidgen.lint.space_rule import frame_seconds, space_issues

    heavy = {**CHASE, "world": {"land": "alpine", "sea": "breeze", "clouds": "layers", "sun": [24, 250]}}
    assert frame_seconds(params(space_cls(), heavy)) > 3
    assert frame_seconds(params(space_cls(), SKIM)) == pytest.approx(1.2)
    project = Project.load(_project(make_project, [{"id": "h", "type": "space", "duration": 4, "params": heavy}]))
    found = space_issues(project, "h", project.config.lint.rules)
    assert any("s a frame at 1280x720" in i.message for i in found)
    calm = Project.load(_project(make_project, [{"id": "c", "type": "space", "duration": 4, "params": SKIM}]))
    assert not space_issues(calm, "c", calm.config.lint.rules)


def space_cls() -> Any:
    extensions.load_builtins()
    return registry.get("space").cls


def test_the_cookbook_cost_table_holds_the_lints_numbers() -> None:
    from vidgen.scenes.space_costs import COSTS

    text = (ROOT / "docs" / "COOKBOOK-SPACE.md").read_text(encoding="utf-8")
    for key, (seconds, row) in COSTS.items():
        assert row in text, key
    # the one table (Step 393): the cost section prints exactly these rows, and no other cookbook has a table of seconds
    section = text[text.index("## 8. What a shot costs"):text.index("## 9. The checks to run")]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| what") and not line.startswith("|---")]
    assert rows == [row for _, row in COSTS.values()]
    assert "s / frame" not in (ROOT / "docs" / "COOKBOOK-AIR.md").read_text(encoding="utf-8")


# ----- Chromium (slow) -----------------------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.render
def test_a_surface_scene_and_an_orbital_hull_scene_draw_in_chromium(make_project: Any, tmp_path: Path) -> None:
    from PIL import Image

    from vidgen.web.still import Moment, make_web_stills

    skim = {**SKIM, "camera": {**SKIM["camera"], "over": [0, 2]}}
    carrier = {**CARRIER, "craft": [{**CARRIER["craft"][0], "dress": False, "scale_ref": None}], "camera": {**CARRIER["camera"][0], "over": [0, 2]}}
    carrier["craft"][0].pop("scale_ref")
    root = _project(make_project, [{"id": "skim", "type": "space", "duration": 2, "params": skim}, {"id": "carrier", "type": "space", "duration": 2, "params": carrier}])
    for sid in ("skim", "carrier"):
        result = make_web_stills(root, sid, moments=[Moment("at", 1.0)], count=None, size="160x90", variant=None, out=tmp_path / f"{sid}.png",
                                 sheet=None, columns=None, exact=False, transparent=False)
        with Image.open(result.stills[0].path) as im:
            assert im.size == (160, 90) and max(im.convert("L").getdata()) > 60
