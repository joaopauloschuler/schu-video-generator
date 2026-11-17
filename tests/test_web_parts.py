"""Ready-made three.js parts (Step 369, DESIGN.md §122.5): the registry ``vidgen/parts``, the parts
files under ``data/web/parts/`` (their JSON descriptions read without a browser), ``vidgen parts``
(``--list``, choosing by name, pattern and kind, the tile size) and, in Chromium (``slow``), the
contact sheet: every part drawn, none left black."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.web import parts as P
from vidgen.web.inputs import IMPORT_MAP
from vidgen.web.loaded import VIDGEN_MODULES, vidgen_file

DATA = Path(P.__file__).resolve().parent.parent / "data"


def test_every_shipped_part_is_described_and_served() -> None:
    found = P.read_parts()
    names = [p.name for p in found]
    assert len(names) == len(set(names)) >= 20 and {"nebula-dome", "star-field", "crystals", "portal", "studio-environment"} <= set(names)
    assert [P.KINDS.index(p.kind) for p in found] == sorted(P.KINDS.index(p.kind) for p in found)  # the sheet's order
    for p in found:
        assert p.module in VIDGEN_MODULES and p.label and p.use and isinstance(p.options, dict) and p.at >= 0
        assert vidgen_file(f"parts/{p.file}") == P.PARTS_DIR / p.file
    assert VIDGEN_MODULES["vidgen/parts"] == "parts.js" and vidgen_file("modules/parts.js") == P.REGISTRY_FILE
    assert IMPORT_MAP["imports"]["vidgen/parts"] == "/__vidgen__/modules/parts.js"
    assert IMPORT_MAP["imports"]["vidgen/parts/"] == "/__vidgen__/parts/"
    assert vidgen_file("parts/../modules/parts.js") is None and vidgen_file("parts/nope.js") is None


def test_the_kinds_and_fields_are_the_registrys() -> None:
    text = P.REGISTRY_FILE.read_text(encoding="utf-8")
    kinds = re.search(r"export const KINDS = Object\.freeze\(\[([^\]]*)\]\)", text)
    assert kinds is not None and tuple(json.loads(f"[{kinds[1]}]")) == P.KINDS
    required = re.search(r"export const REQUIRED = Object\.freeze\(\[([^\]]*)\]\)", text)
    assert required is not None and tuple(json.loads(f"[{required[1]}]")) == P.REQUIRED
    assert "Math.random" not in text and "Math.random" not in (P.PARTS_DIR / "three-kit.js").read_text(encoding="utf-8")


def test_a_parts_file_must_describe_each_part_in_json() -> None:
    good = 'definePart({"name": "a-b", "kind": "sky", "module": "vidgen/three-kit", "label": "x {y}", "use": "f(\\"}\\")", "at": 1}, (s) => {});'
    (part,) = P.parse_parts(good, "x.js")
    assert (part.name, part.label, part.use, part.at, part.seed, part.options) == ("a-b", "x {y}", 'f("}")', 1.0, 1, {})
    with pytest.raises(VidgenError, match="x.js:2: definePart's first argument is not JSON"):
        P.parse_parts("\ndefinePart({name: 'a'}, f)", "x.js")
    with pytest.raises(VidgenError, match="needs use; unknown field\\(s\\) colour"):
        P.parse_parts('definePart({"name": "a", "kind": "sky", "module": "m", "label": "l", "colour": 1}, f)', "x.js")
    with pytest.raises(VidgenError, match="kind 'planet'; kinds: sky, body"):
        P.parse_parts('definePart({"name": "a", "kind": "planet", "module": "m", "label": "l", "use": "u"}, f)', "x.js")


def test_parts_are_chosen_by_name_pattern_and_kind() -> None:
    found = P.read_parts()
    assert [p.name for p in P.select_parts(found, ["star-*"])] == ["star-field", "star-shell"]
    assert [p.name for p in P.select_parts(found, ["portal", "*portal*"])] == ["portal"]
    assert {p.kind for p in P.select_parts(found, kind="effect")} == {"effect"}
    with pytest.raises(VidgenError, match="no part 'nebula-dom' \\(did you mean 'nebula-dome'\\?\\)"):
        P.select_parts(found, ["nebula-dom"])
    with pytest.raises(VidgenError, match="--kind skyy: no such kind \\(did you mean 'sky'\\?\\)"):
        P.select_parts(found, kind="skyy")
    with pytest.raises(VidgenError, match="--kind craft: no part of that kind yet"):
        P.select_parts(found, kind="craft")
    assert P.parse_tile(None, False) == (320, 180) and P.parse_tile(None, True) == (960, 540) and P.parse_tile("640x360", True) == (640, 360)
    for bad in ("640", "641x360", "40x40"):
        with pytest.raises(VidgenError, match="--size"):
            P.parse_tile(bad, False)


def test_the_list_needs_no_browser(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["parts", "--list", "--kind", "sky"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("sky:\n  space-sky ") and "\n  nebula-dome " in out and "vidgen/three-kit: const sky = new SkyDome(seed)" in out and "structure:" not in out
    assert cli.main(["parts", "tesseract", "--list", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert (doc["command"], doc["action"], [p["name"] for p in doc["parts"]]) == ("parts", "list", ["tesseract"])
    assert doc["parts"][0]["import"] == 'import "vidgen/parts/three-kit.js"' and doc["parts"][0]["module"] == "vidgen/three-kit"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    return node


def test_the_registry_checks_what_is_defined(tmp_path: Path) -> None:
    three = tmp_path / "node_modules" / "three"
    three.mkdir(parents=True)
    for name in ("three.module.js", "three.core.js"):
        (three / name).symlink_to(DATA / "three" / name)
    (three / "package.json").write_text(json.dumps({"name": "three", "type": "module", "exports": {".": "./three.module.js"}}), encoding="utf-8")
    (tmp_path / "parts.mjs").symlink_to(P.REGISTRY_FILE)
    body = """
import * as R from './parts.mjs';
const out = [], err = (f) => { try { f(); return null; } catch (e) { return e.message; } };
const info = {name: "a-sky", kind: "sky", module: "m", label: "l", use: "u", options: {gain: 1, size: 2}, seed: 4};
R.definePart(info, (s) => ({got: [s.options, s.seed, s.scene]}));
out.push(R.parts().map((p) => [p.name, p.at, p.seed]), R.parts({kind: "body"}).length, R.parts({name: "sk"}).length);
out.push(R.buildPart("a-sky", {scene: "S"}, {size: 5}).got, R.buildPart("a-sky", {scene: "S"}, {}, 9).got[1]);
out.push(err(() => R.part("a-skye")), err(() => R.definePart(info, () => 0)), err(() => R.definePart({...info, name: "B"}, () => 0)));
out.push(err(() => R.definePart({...info, name: "b", kind: "skye"}, () => 0)), err(() => R.definePart({...info, name: "c", colour: 1}, () => 0)));
out.push(err(() => R.definePart({...info, name: "d", use: ""}, () => 0)), Object.isFrozen(R.part("a-sky")));
const st = R.defaultStage(320, 180);
out.push([st.camera.aspect, st.camera.position.z, st.scene.children.length]);
console.log(JSON.stringify(out));
"""
    (tmp_path / "t.mjs").write_text(body, encoding="utf-8")
    done = subprocess.run([_node(), "--preserve-symlinks", "t.mjs"], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True)
    out = json.loads(done.stdout)
    assert out[0] == [["a-sky", 2, 4]] and out[1] == 0 and out[2] == 1
    assert out[3] == [{"gain": 1, "size": 5}, 4, "S"] and out[4] == 9
    assert out[5] == 'vidgen/parts: no part "a-skye" (did you mean "a-sky"?); import its file ("vidgen/parts/<module>.js") first'
    assert out[6] == 'vidgen/parts: part "a-sky" is defined twice' and "lower-case words joined by hyphens" in out[7]
    assert 'kind "skye" (did you mean "sky"?)' in out[8] and 'unknown field "colour"' in out[9] and 'needs "use"' in out[10]
    assert out[11] is True and out[12] == [320 / 180, 6, 2]


@pytest.mark.slow
@pytest.mark.render
def test_the_contact_sheet_draws_every_part(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Every shipped part at 96x54 in one browser: a tile each, none black; the sheet labels them."""
    from PIL import Image

    tiles: list[np.ndarray] = []
    found = P.read_parts()
    original = P.compose_sheet

    def keep(drawn, columns, title):  # the tiles as drawn, before the labels
        tiles.extend(pixels for pixels, _ in drawn)
        return original(drawn, columns, title)

    P.compose_sheet = keep
    try:
        result = P.make_parts_sheet(found, tmp_path / "sheet.png", tile=(96, 54), columns=6)
    finally:
        P.compose_sheet = original
    assert [t.part.name for t in result.tiles] == [p.name for p in found] and result.skipped == []
    assert all(t.shape == (54, 96, 3) and t.max() > 60 and t.mean() > 2 for t in tiles), [float(t.mean()) for t in tiles]
    assert Image.open(result.path).size == result.size and result.size[0] == 8 + 6 * 104
    stopped = P.make_parts_sheet(found[:3], tmp_path / "first.png", tile=(64, 64), time_limit=0)
    assert [t.part.name for t in stopped.tiles] == [found[0].name] and [p.name for p in stopped.skipped] == [p.name for p in found[1:3]]
    assert cli.main(["parts", "tesseract", "--out", str(tmp_path / "one.png"), "--size", "128x72", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["action"] == "sheet" and doc["tile"] == [128, 72] and [p["name"] for p in doc["parts"]] == ["tesseract"]
