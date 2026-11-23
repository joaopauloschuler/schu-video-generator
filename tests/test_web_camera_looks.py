"""Camera looks, ``vidgen/camera-looks`` (Step 400, DESIGN.md §124.4): the module is served by its import name and
imports nothing; Python reads the same table (``camera_looks``) and merges a scene's own options over a look the
same way as the module's ``lookMerge``; in Node (when it is installed): every look's finish passes
vidgen/three-finish's checks and turns on the sensor and the lens, every look's operator passes
vidgen/space-camera-air's ``operate``; the main values agree with three-finish's own; unknown names get a
did-you-mean; ``metered: false`` leaves the automatic exposure out."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from vidgen.scenes.space_params import camera_look, look_merge
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, current_loaded, vidgen_file
from vidgen.web.page import INIT_FILES, engine_id
from vidgen.web.space_names import camera_looks, constant_entries

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "vidgen" / "data"
MODULES = DATA / "web" / "modules"
MODULE = MODULES / "camera-looks.js"
LOOKS = ["window_handheld", "drone", "broadcast_long_lens", "phone", "chase_mount"]
#: own options over a look, as a scene gives them: (section, base, own) with a variety of the merge's rules
CASES = [
    ("finish", {"noise": {"amount": 0.01, "size": 1.4}, "grade": {"lift": 0.01, "saturation": 1.1}}, {"noise": 0.004, "grade": {"saturation": 1.3}}),
    ("finish", {"noise": {"amount": 0.01}, "range": {"stops": 2}, "halation": 0.2}, {"noise": False, "range": True, "halation": {"amount": 0.5}}),
    ("finish", {"bloom": {"strength": 0.3, "radius": 0.5}, "vignette": 0.3}, {"bloom": 0, "vignette": {"amount": 0.1}, "grain": 0.05}),
    ("finish", {"edges": {"soft": 1.2, "fringe": 1}, "grade": {"lift": 0.01}}, {"edges": 2, "grade": {"lift": [0, 0.01, 0.02]}}),
    ("operator", {"hand": {"style": "handheld", "amount": 0.6}, "exposure": {"strength": 0.3}}, {"hand": "handheld", "exposure": 0.5}),
    ("operator", {"hand": {"style": "handheld", "amount": 0.6}, "horizon": {"degrees": 0.8}}, {"hand": "mounted", "horizon": False}),
    ("operator", {"hand": {"style": "mounted", "amount": 0.5}}, {"hand": {"amount": 0.2}, "seed": 4}),
    ("operator", {"hand": {"style": "mounted", "amount": 0.5}, "exposure": {"strength": 0.3}}, {"hand": {"style": "handheld", "drift": 2}, "exposure": True}),
]


def test_the_module_is_served_by_its_import_name_and_imports_nothing() -> None:
    assert VIDGEN_MODULES["vidgen/camera-looks"] == "camera-looks.js"
    assert IMPORT_MAP["imports"]["vidgen/camera-looks"] == "/__vidgen__/modules/camera-looks.js"
    assert vidgen_file("modules/camera-looks.js") == MODULE
    assert len(current_loaded(Path("."), ["__vidgen__/modules/camera-looks.js"])["__vidgen__/modules/camera-looks.js"] or "") == 64
    source = MODULE.read_text(encoding="utf-8")
    assert not re.search(r"^import\b", source, re.M)
    assert "Math.random" not in source and "Date.now" not in source and "performance.now" not in source
    assert MODULE not in INIT_FILES and "camera-looks" not in engine_id()


def test_python_reads_the_table_and_the_main_values_are_the_finishs_own() -> None:
    table = camera_looks()
    assert list(table["looks"]) == LOOKS
    for look in table["looks"].values():
        assert set(look) == {"finish", "operator"} and look["finish"] and look["operator"]
        assert "motionBlur" not in look["finish"] and "antialias" not in look["finish"]      # cost and stars stay the scene's
    scalar = {k: v.strip('"') for k, v in constant_entries("vidgen/three-finish", "SCALAR_GROUP").items()}
    assert table["main"]["finish"] == scalar
    assert table["main"]["operator"] == {"exposure": "strength", "horizon": "degrees"}


def test_the_python_merge_and_the_scenes_own_options_win() -> None:
    finish, operator = camera_look("drone", {"noise": 0.004, "grade": {"contrast": 1.2}, "motion_blur": 3}, {"hand": {"amount": 0.2}}, surface=True)
    look = camera_looks()["looks"]["drone"]
    assert finish["noise"] == {**look["finish"]["noise"], "amount": 0.004}
    assert finish["grade"] == {**look["finish"]["grade"], "contrast": 1.2} and finish["motion_blur"] == 3
    assert operator["hand"] == {**look["operator"]["hand"], "amount": 0.2} and operator["exposure"] == look["operator"]["exposure"]
    _, orbital = camera_look("drone", None, None, surface=False)
    assert "exposure" not in orbital and orbital["hand"] == look["operator"]["hand"]
    assert camera_look("phone", {"sharpen": False}, {"hand": False}, surface=True)[0]["sharpen"] is False
    with pytest.raises(ValueError, match="unknown camera_look 'dron'; did you mean 'drone'"):
        camera_look("dron", None, None, surface=True)
    with pytest.raises(ValueError, match="leave out finish: false"):
        camera_look("drone", False, None, surface=True)
    base = {"noise": {"amount": 0.01}}
    look_merge(base, {"noise": {"size": 2}})
    assert base == {"noise": {"amount": 0.01}}      # the look is not changed


def _run_in_node(tmp_path: Path, body: str) -> list:
    """Import camera-looks as ``L``, three-finish as ``F`` and space-camera-air as ``A`` in Node; print ``out``."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    three = tmp_path / "node_modules" / "three"
    three.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (three / name).symlink_to(DATA / "three" / name)
    (three / "addons").symlink_to(DATA / "three" / "addons")
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js", "./addons/*": "./addons/*"}}),
                                        encoding="utf-8")
    names = ("camera-looks", "three-finish", "music-time", "space-camera", "space-scene", "space-camera-air")
    ours = tmp_path / "node_modules" / "vidgen"
    ours.mkdir(parents=True)
    for name in names:
        (ours / f"{name}.js").symlink_to(MODULES / f"{name}.js")
    (ours / "package.json").write_text(json.dumps({"name": "vidgen", "type": "module", "exports": {f"./{n}": f"./{n}.js" for n in names}}), encoding="utf-8")
    (tmp_path / "t.mjs").write_text(
        "import * as L from 'vidgen/camera-looks';\nimport * as F from 'vidgen/three-finish';\nimport * as A from 'vidgen/space-camera-air';\n"
        "const out = [];\nconst err = (f) => { try { f(); return null; } catch (e) { return e.message; } };\n"
        f"{body}\nconsole.log(JSON.stringify(out));\n", encoding="utf-8")
    done = subprocess.run([node, "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_every_look_is_a_valid_finish_and_operator_and_the_merges_agree_in_node(tmp_path: Path) -> None:
    cases = json.dumps(CASES)
    table, main, checked, merged, unknown, other, metered = _run_in_node(tmp_path, f"""
out.push(L.CAMERA_LOOKS, L.LOOK_MAIN);
const shot = (t) => ({{from: [0, 100, 0], forward: [0, 0, -1], up: [0, 1, 0], right: [1, 0, 0], fov: 40, ev: 0}});
out.push(Object.fromEntries(Object.keys(L.CAMERA_LOOKS).map((name) => {{
  const look = L.cameraLook(name), o = F.resolveOptions(look.finish), view = A.operate(shot, look.operator, (s, t) => Math.sin(t));
  return [name, {{noise: o.noise.amount, range: o.range.stops, sharpen: o.sharpen.amount, halation: o.halation.amount, edges: o.edges.soft,
    turned: view(3.3).operator !== undefined, moved: Math.abs(view(3.3).operator.yaw) + Math.abs(view(3.3).operator.pitch) > 0}}];
}})));
out.push({cases}.map(([section, base, own]) => L.lookMerge(base, own, L.LOOK_MAIN[section])));
out.push([err(() => L.cameraLook("phon")), err(() => L.cameraLook("drone", {{finsh: {{}}}}))]);
out.push(L.cameraLook("drone", {{finish: {{noise: 0.004}}, operator: {{hand: {{amount: 0.2}}}}}}));
out.push(L.cameraLook("drone", {{}}, {{metered: false}}).operator);
""")
    assert table == camera_looks()["looks"] and main == camera_looks()["main"]
    for name, o in checked.items():
        assert o["noise"] > 0 and o["range"] >= 1 and o["sharpen"] > 0 and o["halation"] > 0 and o["edges"] > 0, name
        assert o["turned"] and o["moved"], name
    assert merged == [look_merge(base, own, camera_looks()["main"][section]) for section, base, own in CASES]
    assert 'no camera look "phon" (did you mean "phone"?)' in unknown[0] and 'unknown option "finsh" (did you mean "finish"?)' in unknown[1]
    finish, operator = camera_look("drone", {"noise": 0.004}, {"hand": {"amount": 0.2}}, surface=True)
    assert other == {"finish": finish, "operator": operator}
    assert "exposure" not in metered and "hand" in metered
