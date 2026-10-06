"""`vidgen lint`: the layout rules on synthetic layouts, the runner (reuse, ignores, merging,
fail_on), the CLI and JSON, the config section, and one render test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from PIL import Image

from conftest import minimal_config
from test_json_output import documented, run_json
from test_render import write_project
from vidgen import config as config_module
from vidgen.cli import main
from vidgen.config import LINT_RULES, LintConfig, LintRules, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import RULES, StillContext, lint_project
from vidgen.lint.color import blend, contrast_ratio, hex_rgb
from vidgen.lint.layout_rules import cap_height
from vidgen.project import Project
from vidgen.render import fingerprint
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.render.worker import scene_activity_path, scene_frames_dir, scene_layout_path, scene_timings_path

ROOT = Path(__file__).resolve().parents[1]
BG = "#0E1116"

# ----- helpers -----------------------------------------------------------------------------------


def text(oid: str, bbox: list[float], words: str = "Hello world", *, font: float = 30.0, color: str = "#E8EAED",
         opacity: float = 1.0, order: int = 1, path: str | None = None, kind: str = "text", backdrop: str = BG) -> dict[str, Any]:
    return {"id": oid, "kind": kind, "class": "Text", "path": path or f"Text[{oid}]", "name": None, "bbox": bbox,
            "opacity": opacity, "z": 0.0, "order": order, "parts": len(words), "text": words, "font_px": font,
            "color": color, "colors": [color], "backdrop": backdrop}


def shape(oid: str, bbox: list[float], *, kind: str = "shape", fill: str | None = "#FF0000", fill_opacity: float = 1.0,
          stroke: str | None = None, order: int = 5, path: str | None = None, opacity: float = 1.0) -> dict[str, Any]:
    return {"id": oid, "kind": kind, "class": "Rectangle", "path": path or f"Rectangle[{oid}]", "name": None,
            "bbox": bbox, "opacity": opacity, "z": 0.0, "order": order, "parts": 1,
            "fill": None if fill is None else {"color": fill, "opacity": fill_opacity},
            "stroke": None if stroke is None else {"color": stroke, "opacity": 1.0, "width_px": 2.0}}


def layout(width: int = 1920, height: int = 1080, margin: float = 0.06) -> dict[str, Any]:
    mx, my = margin * height, margin * height
    return {"version": 1, "scene": "s", "type": "t", "width": width, "height": height, "fps": 30, "per_beat": 1,
            "px_per_unit": height / 8, "background": BG, "safe_area": [mx, my, width - mx, height - my], "frames": []}


def check(name: str, objects: list[dict[str, Any]], *, size: tuple[int, int] = (1920, 1080), still: Path | None = None,
          **settings: Any) -> list[Any]:
    """Run one rule on one still; returns its issues."""
    rule = RULES[name]
    model = type(getattr(LintRules(), name))
    ctx = StillContext(layout(*size), {"beat": "b", "k": 1, "n": 1, "time": 1.0}, objects, still=still)
    return list(rule.check(ctx, model(**settings)))


# ----- colour and size ---------------------------------------------------------------------------


def test_wcag_contrast() -> None:
    assert contrast_ratio((0, 0, 0), (1, 1, 1)) == pytest.approx(21.0)
    assert contrast_ratio(hex_rgb("#777777"), hex_rgb("#777777")) == pytest.approx(1.0)
    assert contrast_ratio(hex_rgb("#767676"), hex_rgb("#FFFFFF")) == pytest.approx(4.54, abs=0.01)  # the AA grey
    assert blend((1, 1, 1), (0, 0, 0), 0.25) == pytest.approx((0.25, 0.25, 0.25))


def test_cap_height_corrects_for_lowercase() -> None:
    # same font size: x-height glyphs measure smaller than ascenders/caps; the estimate agrees
    sparse = cap_height(text("a", [0, 0, 1, 1], "sparse", font=11.3))
    baseline = cap_height(text("b", [0, 0, 1, 1], "Baseline", font=14.6))
    assert sparse == pytest.approx(baseline, rel=0.1)
    assert cap_height(text("c", [0, 0, 1, 1], "HELLO 42", font=20)) == pytest.approx(20)
    assert cap_height(text("d", [0, 0, 1, 1], "x^2", font=20, kind="math")) == 20  # LaTeX source: as measured


# ----- rules -------------------------------------------------------------------------------------


def test_off_frame() -> None:
    cut = text("t", [1800, 500, 2000, 540])
    issues = check("off_frame", [cut])
    assert len(issues) == 1 and issues[0].severity == "error" and "right edge" in issues[0].message
    assert issues[0].value == 80.0
    assert not check("off_frame", [text("t", [1800, 500, 1923, 540])])  # within the tolerance (4.3 px)
    assert not check("off_frame", [text("t", [2000, 500, 2100, 540])])  # wholly outside: not seen
    # full-frame bleeds: an image with fit: cover, a band running across the frame
    assert not check("off_frame", [shape("i", [-60, -20, 1980, 1100], kind="image", fill=None)])
    band = check("off_frame", [shape("b", [-5, 1000, 1925, 1120])])
    assert [i.severity for i in band] == ["warning"] and "bottom" in band[0].message and "left" not in band[0].message
    assert not check("off_frame", [shape("b", [-5, 1000, 1925, 1080])])  # spans the width, inside vertically
    logo = check("off_frame", [shape("l", [-100, 10, 100, 110], kind="image", fill=None)])
    assert [i.severity for i in logo] == ["warning"]  # a small image half out of the frame


def test_safe_area() -> None:
    # 1080p: margins 64.8 px, tolerance 10.8 px
    issues = check("safe_area", [text("t", [40, 500, 400, 540])])
    assert len(issues) == 1 and "left" in issues[0].message and issues[0].value == pytest.approx(24.8)
    assert not check("safe_area", [text("t", [60, 500, 400, 540])])  # within the tolerance
    assert not check("safe_area", [text("t", [-40, 500, 400, 540])])  # off the frame: off_frame's job
    assert not check("safe_area", [shape("s", [0, 0, 1920, 100])])  # only text
    assert check("safe_area", [text("t", [40, 500, 400, 540])], tolerance=0.03) == []


def test_text_overlap() -> None:
    a = text("a", [100, 100, 500, 150], "Title", order=1)
    b = text("b", [300, 130, 700, 180], "Subtitle", order=2)
    issues = check("text_overlap", [a, b])
    assert len(issues) == 1 and issues[0].objects[0]["id"] == "b" and issues[0].bbox == (300, 130, 500, 150)
    assert issues[0].value == pytest.approx(0.2)
    assert not check("text_overlap", [a, text("c", [100, 148, 500, 200])])  # touching (4 % of a box)
    assert not check("text_overlap", [a, text("d", [101, 100, 501, 150], "Title")])  # the same text twice
    assert not check("text_overlap", [a, b], min_overlap=0.5)


def still_png(path: Path, size: tuple[int, int], boxes: list[tuple[list[int], str]]) -> Path:
    pixels = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    pixels[:, :] = np.array(hex_rgb(BG)) * 255
    for (x0, y0, x1, y1), color in boxes:
        pixels[y0:y1, x0:x1] = np.array(hex_rgb(color)) * 255
    Image.fromarray(pixels).save(path)
    return path


def test_covered_text_looks_at_pixels(tmp_path: Path) -> None:
    size = (400, 200)
    label = text("t", [100, 80, 300, 120], "Label", order=3)
    # the text's middle (140..260 x 90..110) shows a red bar drawn after it
    still = still_png(tmp_path / "a.png", size, [([100, 80, 300, 120], "#E8EAED"), ([150, 95, 250, 105], "#FF0000")])
    bar = shape("r", [150, 95, 250, 105], order=7)
    issues = check("covered_text", [label, bar], size=size, still=still)
    assert len(issues) == 1 and [o["id"] for o in issues[0].objects] == ["t", "r"]
    assert 0.3 < issues[0].value < 0.5
    assert not check("covered_text", [label, {**bar, "order": 1}], size=size, still=still)  # drawn before: a backdrop
    assert not check("covered_text", [label, {**bar, "opacity": 0.2}], size=size, still=still)  # faint
    parent = {**bar, "path": "Group[0]"}
    assert not check("covered_text", [{**label, "path": "Group[0]/Text[1]"}, parent], size=size, still=still)
    # a group whose box covers the text but draws elsewhere: the pixels show no red there
    clean = still_png(tmp_path / "b.png", size, [([100, 80, 300, 120], "#E8EAED")])
    assert not check("covered_text", [label, shape("g", [0, 0, 400, 200], kind="group", order=9)], size=size, still=clean)
    # a strike-through in the text's own colour is intentional
    strike = shape("s", [100, 98, 300, 102], fill="#E8EAED", order=9)
    assert not check("covered_text", [label, strike], size=size, still=still)
    # an image on top hides what its box covers
    image = shape("i", [0, 0, 200, 200], kind="image", fill=None, order=9)
    assert [round(i.value, 2) for i in check("covered_text", [label, image], size=size, still=None)] == [0.5]


def test_min_font_relative_to_shorter_side() -> None:
    assert not check("min_font", [text("t", [0, 0, 1, 1], "Readable", font=30)])  # 2.8 % of 1080
    warn = check("min_font", [text("t", [0, 0, 1, 1], "Small", font=25)])
    assert [i.severity for i in warn] == ["warning"] and warn[0].limit == 0.025
    error = check("min_font", [text("t", [0, 0, 1, 1], "Tiny", font=15)])
    assert [i.severity for i in error] == ["error"] and error[0].limit == 0.018
    # preview 854x480 and 9:16 (shorter side = width) give the same verdicts
    assert [i.severity for i in check("min_font", [text("t", [0, 0, 1, 1], "Small", font=25 * 480 / 1080)], size=(854, 480))] == ["warning"]
    assert not check("min_font", [text("t", [0, 0, 1, 1], "Readable", font=30)], size=(1080, 1920))
    assert not check("min_font", [text("t", [0, 0, 1, 1], "+", font=5)])  # a lone symbol
    assert not check("min_font", [text("t", [0, 0, 1, 1], "Small", font=25)], min_size=0.02, error_size=0.01)


def test_contrast() -> None:
    dim = check("contrast", [text("t", [0, 0, 1, 1], "Caption", color="#6B7280")])
    assert len(dim) == 1 and dim[0].value == pytest.approx(3.91, abs=0.01) and dim[0].limit == 4.5
    assert not check("contrast", [text("t", [0, 0, 1, 1], "Body", color="#E8EAED")])
    # large text needs 3:1, faded text 2:1 (its colour blended with the backdrop)
    assert not check("contrast", [text("t", [0, 0, 1, 1], "Big", color="#6B7280", font=60)])
    assert not check("contrast", [text("t", [0, 0, 1, 1], "Previous bullet", opacity=0.4)])  # 3.2:1
    faded = check("contrast", [text("t", [0, 0, 1, 1], "Ghost", opacity=0.2)])
    assert len(faded) == 1 and faded[0].limit == 2.0 and "at 0.20" in faded[0].message
    # every colour of a multi-coloured text counts; a listing's line numbers do not
    multi = {**text("t", [0, 0, 1, 1], "Two tone"), "colors": ["#E8EAED", "#30343A"]}
    assert len(check("contrast", [multi])) == 1
    assert not check("contrast", [text("n", [0, 0, 1, 1], "1\n2\n3", color="#4A4F57", kind="code")])
    assert not check("contrast", [{**text("t", [0, 0, 1, 1], "Off"), "backdrop": None}])


def test_max_words() -> None:
    texts = [text(str(i), [0, 50 * i, 100, 50 * i + 40], "one two three four five six seven eight nine ten") for i in range(4)]
    assert not check("max_words", texts)  # 40
    code = text("c", [0, 0, 1, 1], "for x in range ten words of code here a b", kind="code")
    assert not check("max_words", [*texts, code, text("n", [0, 0, 1, 1], "1.5 2.5 3.5")])  # code, numbers: no words
    issues = check("max_words", [*texts, text("x", [500, 500, 600, 540], "and more")])
    assert len(issues) == 1 and issues[0].value == 42 and issues[0].objects == ()
    assert issues[0].bbox == (0, 0, 600, 540)
    assert not check("max_words", [*texts, text("x", [0, 0, 1, 1], "and more")], max_words=50)


def test_rules_match_the_config() -> None:
    assert tuple(RULES) == LINT_RULES == tuple(LintRules.model_fields)
    assert set(config_module.RuleName.__args__) == set(LINT_RULES)  # type: ignore[attr-defined]
    assert all(rule.doc and rule.default in ("error", "warning", "info") for rule in RULES.values())


# ----- config ------------------------------------------------------------------------------------


def test_lint_config_section() -> None:
    cfg = parse_config(minimal_config(lint={"fail_on": "warning", "rules": {"min_font": {"min_size": 0.03}, "contrast": {"severity": "off"}}}))
    assert cfg.lint.fail_on == "warning" and cfg.lint.rules.min_font.min_size == 0.03
    assert cfg.lint.rules.min_font.error_size == 0.018 and cfg.lint.rules.contrast.severity == "off"
    for bad, message in [
        ({"rules": {"min_fnt": {}}}, "lint.rules.min_fnt"),
        ({"rules": {"min_font": {"min_size": 0.01}}}, "error_size must not be larger than min_size"),
        ({"rules": {"contrast": {"severity": "loud"}}}, "lint.rules.contrast.severity"),
        ({"rules": {"safe_area": {"tolerance": 2}}}, "lint.rules.safe_area.tolerance"),
        ({"fail_on": "sometimes"}, "lint.fail_on"),
    ]:
        with pytest.raises(VidgenError, match=message):
            parse_config(minimal_config(lint=bad))


def test_lint_ignore_entries() -> None:
    data = minimal_config()
    data["scenes"][0]["lint_ignore"] = ["min_font", {"rule": "contrast", "object": "Hello*", "beat": "intro_b2"}, "all"]
    scene = parse_config(data).scenes[0]
    assert [(e.rule, e.object, e.beat) for e in scene.lint_ignores()] == [
        ("min_font", None, None), ("contrast", "Hello*", "intro_b2"), ("all", None, None)]
    data["scenes"][0]["lint_ignore"] = ["min_fnt"]
    with pytest.raises(VidgenError, match=r"scenes\[0\]\.lint_ignore"):
        parse_config(data)
    data["scenes"][0]["lint_ignore"] = [{"rule": "contrast", "beat": "custom"}]  # a beat of another scene
    with pytest.raises(VidgenError, match="scene 'intro' has no beat 'custom'"):
        parse_config(data)


def test_lint_settings_do_not_change_the_fingerprint(make_project) -> None:
    package = Path(fingerprint.__file__).resolve().parent.parent
    assert not fingerprint._render_input(package / "lint" / "run.py")
    root = make_project()
    before = scene_fingerprint(Project.load(root), "intro")
    data = minimal_config(lint={"fail_on": "never"})
    data["scenes"][0]["lint_ignore"] = ["contrast"]
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert scene_fingerprint(Project.load(root), "intro") == before


def test_docs_list_the_lint_defaults() -> None:
    md = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    block = md[md.index("```yaml\nlint:") + 8 : md.index("```", md.index("```yaml\nlint:") + 8)]
    documented_cfg = yaml.safe_load(block)["lint"]
    defaults = LintConfig().model_dump(exclude_none=True)
    assert {k: v for k, v in documented_cfg.items() if k != "rules"} == {k: v for k, v in defaults.items() if k != "rules"}
    for name, values in documented_cfg["rules"].items():
        assert {k: v for k, v in defaults["rules"][name].items() if k != "severity"} == values, name
    assert set(documented_cfg["rules"]) == set(LINT_RULES)
    for name in LINT_RULES:
        assert f"| `{name}` |" in md, f"rule {name} missing from the rules table"


# ----- runner on fake renders (no Manim) ---------------------------------------------------------


def fake_render(project: Project, scene_id: str, frames: list[list[dict[str, Any]]], size: tuple[int, int] = (854, 480),
                activity: dict[str, Any] | None = None) -> None:
    """Write what a render with one still per beat leaves behind: timings (with the current
    fingerprint), the stills, their index, the layout dump and the activity file (``activity``
    overrides its keys); ``frames`` = objects per beat."""
    spec = project.scene(scene_id)
    beats = [b.id for b in spec.beats] or [None]
    folder = scene_frames_dir(project, True, scene_id)
    folder.mkdir(parents=True, exist_ok=True)
    entries, layout_frames = [], []
    for i, (beat, objects) in enumerate(zip(beats, frames)):
        name = f"{beat or scene_id}-1.png"
        still_png(folder / name, size, [])
        entry = {"beat": beat, "k": 1, "n": 1, "frame": 10 * (i + 1), "time": float(i + 1)}
        entries.append({**entry, "path": name})
        layout_frames.append({**entry, "still": f"../frames/{scene_id}/{name}", "camera": {}, "objects": objects})
    (folder / "index.json").write_text(json.dumps({"scene": scene_id, "per_beat": 1, "frames": entries}), encoding="utf-8")
    doc = {**layout(*size), "scene": scene_id, "frames": layout_frames}
    scene_layout_path(project, True, scene_id).parent.mkdir(parents=True, exist_ok=True)
    scene_layout_path(project, True, scene_id).write_text(json.dumps(doc), encoding="utf-8")
    fmt = project.render_format(True)
    timings = {"scene": scene_id, "duration": float(len(beats) + 1),
               "beats": [{"id": b, "start": 0.0, "end": 1.0, "text": "x"} for b in beats if b],
               "render": {"width": fmt.width, "height": fmt.height, "fps": fmt.fps, "frames": 1,
                          "fingerprint": scene_fingerprint(project, scene_id)}}
    scene_timings_path(project, True, scene_id).parent.mkdir(parents=True, exist_ok=True)
    scene_timings_path(project, True, scene_id).write_text(json.dumps(timings), encoding="utf-8")
    doc = {"version": 1, "scene": scene_id, "type": spec.type, "fps": 10, "frames": 10 * len(beats),
           "duration": float(len(beats)), "pad": 0.35, "silent": None if spec.beats else {"duration": 1.0, "busy": 1.0},
           "beats": [{"id": b, "start": float(i), "end": i + 0.6, "busy": 0.6, "source": "estimate", "text": "x"}
                     for i, b in enumerate(beats) if b],
           "plays": [], "motion": {"step": 3, "grid": [285, 160], "level": 6, "changes": [[0, 1.0]]}, **(activity or {})}
    scene_activity_path(project, True, scene_id).parent.mkdir(parents=True, exist_ok=True)
    scene_activity_path(project, True, scene_id).write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def faked(make_project) -> Path:
    """A two-scene project whose renders are faked: 'intro' has a dim caption (both beats) and
    a too small label (beat 2), 'main' has two overlapping texts and three dim tick labels."""
    data = minimal_config(preview={"width": 854, "height": 480, "fps": 15})
    root = make_project(data)
    project = Project.load(root)
    caption = text("m1", [300, 300, 500, 320], "Illustrative numbers", color="#6B7280", font=15, path="VGroup[1]/Text[0]")
    small = text("m2", [300, 100, 400, 110], "tiny label", font=6)
    fake_render(project, "intro", [[caption], [caption, small]])
    ticks = [text(f"t{i}", [40, 100 + 40 * i, 70, 112 + 40 * i], f"1.{i}", color="#6B7280", font=13, path=f"Axes[0]/VGroup[2]/Text[{i}]")
             for i in range(3)]
    overlap = [text("a", [100, 50, 400, 90], "Title", font=30, order=1), text("b", [200, 70, 500, 110], "Other", font=30, order=2)]
    fake_render(project, "main", [[*ticks, *overlap]])
    return root


def test_findings_merge_group_and_sort(faked: Path) -> None:
    result = lint_project(Project.load(faked))
    assert result.rendered == [] and result.reused == ["intro", "main"] and result.stills == 3
    summary = [(f.scene, f.beat, f.rule, f.severity, f.objects[0]["id"] if f.objects else None) for f in result.findings]
    assert summary == [
        ("intro", "intro_b1", "contrast", "warning", "m1"),
        ("intro", "intro_b2", "min_font", "error", "m2"),
        ("main", "custom", "text_overlap", "error", "b"),
        ("main", "custom", "contrast", "warning", "t0"),
    ]
    caption = result.findings[0]
    assert caption.beats == ["intro_b1", "intro_b2"]  # same problem at both beat ends: one finding
    assert caption.scene_time == 1.0 and caption.time == 1.0
    assert caption.still == scene_frames_dir(Project.load(faked), True, "intro") / "intro_b1-1.png"
    ticks = result.findings[3]
    assert [o["id"] for o in ticks.similar] == ["t1", "t2"] and "also 2 more like it ('1.1', '1.2')" in ticks.message
    assert ticks.bbox == (40, 100, 70, 192)
    assert result.findings[2].time == pytest.approx(3.0 + 1.0)  # after intro (3 s)
    assert result.counts() == {"error": 2, "warning": 2, "info": 0} and result.failed


def test_rules_scenes_and_fail_on(faked: Path) -> None:
    project = Project.load(faked)
    only = lint_project(project, rules=["contrast"], scenes=["main"])
    assert [f.rule for f in only.findings] == ["contrast"] and only.scenes == ["main"] and only.rules == ["contrast"]
    assert not only.failed and lint_project(project, rules=["contrast"], fail_on="warning").failed
    assert not lint_project(project, fail_on="never").failed
    with pytest.raises(VidgenError, match="unknown lint rule"):
        lint_project(project, rules=["nope"])
    with pytest.raises(VidgenError, match="unknown scene"):
        lint_project(project, scenes=["nope"])


def test_config_severities_and_ignores(faked: Path) -> None:
    data = yaml.safe_load((faked / "video.yaml").read_text(encoding="utf-8"))
    data["lint"] = {"fail_on": "warning", "rules": {"text_overlap": {"severity": "info"}, "min_font": {"severity": "off"}}}
    data["scenes"][0]["lint_ignore"] = [{"rule": "contrast", "object": "Illustrative*", "beat": "intro_b2"}]
    data["scenes"][1]["lint_ignore"] = [{"rule": "all", "object": "Axes[0]/*"}]
    (faked / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lint_project(Project.load(faked))
    summary = [(f.scene, f.rule, f.severity, f.beats) for f in result.findings]
    assert summary == [("intro", "contrast", "warning", ["intro_b1"]), ("main", "text_overlap", "info", ["custom"])]
    assert result.ignored == 4 and result.fail_on == "warning" and result.failed


def test_cli_human_and_json(faked: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(faked)
    assert main(["lint"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "lint: 2 scenes, 3 beat-end stills (preview 854x480)"
    assert out[1] == "intro:" and out[2].startswith("  warning contrast          intro_b1 @ 1.0s (+1 more beat): text 'Illustrative numbers'")
    assert out[3].strip() == f"still: {Path('build', 'preview', 'frames', 'intro', 'intro_b1-1.png')}"
    assert out[-2:] == ["2 errors, 2 warnings, 0 info", "failed: findings at or above 'error'"]
    assert main(["lint", "--fail-on", "never", "--rule", "contrast"]) == 0
    capsys.readouterr()

    code, doc, _ = run_json(["lint", ".", "--json"], capsys)
    assert code == 1 and doc["command"] == "lint" and doc["error"]["kind"] == "error"
    assert doc["error"]["details"] == {"fail_on": "error", "counts": {"error": 2, "warning": 2, "info": 0}}
    assert (doc["stills"], doc["scenes"], doc["reused"], doc["rendered"]) == (3, ["intro", "main"], ["intro", "main"], [])
    first = doc["findings"][0]
    assert list(first) == ["scene", "beat", "time", "scene_time", "rule", "severity", "object", "other", "similar", "bbox",
                           "message", "value", "limit", "beats", "still"]
    assert first["object"] == {"id": "m1", "kind": "text", "class": "Text", "name": None, "path": "VGroup[1]/Text[0]",
                               "text": "Illustrative numbers", "icon": None, "bbox": [300, 300, 500, 320]}
    assert Path(first["still"]).is_absolute() and Path(first["still"]).is_file()
    overlap = doc["findings"][2]
    assert overlap["object"]["id"] == "b" and overlap["other"]["id"] == "a" and overlap["bbox"] == [200, 70, 400, 90]
    documented("fail_on", "rules", "stills", "counts", "ignored", "findings", "other", "similar", "limit", "beats", "still")
    code, doc, _ = run_json(["lint", ".", "--json", "--fail-on", "never"], capsys)
    assert code == 0 and doc["ok"] and "error" not in doc and len(doc["findings"]) == 4
    code, doc, _ = run_json(["lint", ".", "--json", "--fail-on", "sometimes"], capsys)
    assert code == 2 and doc["error"]["kind"] == "usage"


def test_lint_warns_about_the_theme_contrast(faked: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Like validate, lint reports theme pairs below WCAG AA as warnings (not findings) (Step 22)."""
    data = yaml.safe_load((faked / "video.yaml").read_text(encoding="utf-8"))
    data["theme"] = {"colors": {"dim": "#6B7280"}}
    (faked / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    project = Project.load(faked)
    for scene_id in ("intro", "main"):  # the theme is in the fingerprint: fake current renders again
        fake_render(project, scene_id, [[]] * max(1, len(project.scene(scene_id).beats)))
    monkeypatch.chdir(faked)
    assert main(["lint"]) == 0
    captured = capsys.readouterr()
    assert "warning: theme contrast: colors.dim #6B7280 on background #0E1116" in captured.err
    assert captured.out.splitlines()[-1] == "0 errors, 0 warnings, 0 info"
    code, doc, _ = run_json(["lint", ".", "--json"], capsys)
    assert code == 0 and any(w["message"].startswith("theme contrast: colors.dim") for w in doc["warnings"])
    assert main(["lint", "--rule", "min_font"]) == 0
    assert "theme contrast" not in capsys.readouterr().err
    data["lint"] = {"rules": {"contrast": {"severity": "off"}}}
    (faked / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["lint"]) == 0
    assert "theme contrast" not in capsys.readouterr().err


def test_same_text_in_copies_of_a_component_is_one_finding(make_project) -> None:
    """A label repeated in two copies of a component (different parents) is merged (Step 22)."""
    project = Project.load(make_project(minimal_config(preview={"width": 854, "height": 480, "fps": 15})))
    labels = [text(f"a{i}", [100, 100 + 80 * i, 200, 112 + 80 * i], "Attention", font=9, path=f"VGroup[{i}]/Text[1]")
              for i in range(2)]
    fake_render(project, "intro", [labels, labels])
    fake_render(project, "main", [[]])
    result = lint_project(project, rules=["min_font"])
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert [o["id"] for o in finding.similar] == ["a1"] and "also 1 more like it ('Attention')" in finding.message


def test_stale_or_partial_stills_are_not_reused(faked: Path) -> None:
    from vidgen.storyboard import stills_current

    project = Project.load(faked)
    assert stills_current(project, True, "intro", None) and stills_current(project, True, "intro", 1)
    assert not stills_current(project, True, "intro", 2)
    scene_layout_path(project, True, "intro").unlink()  # a render from before layout dumps
    assert not stills_current(project, True, "intro", None)


# ----- rendering ---------------------------------------------------------------------------------

EXTENSION = '''
from vidgen.api import *

@scene("crowded")
class Crowded(NarratedScene):
    def construct(self):
        with self.narrate(0):
            title = Text("Overlapping title", font_size=40, color=WHITE)
            other = Text("Second text", font_size=40, color=WHITE).move_to(title.get_center() + 0.2 * DOWN)
            edge = Text("Cut off", font_size=40, color=WHITE).move_to(self.frame_width / 2 * RIGHT + 0.5 * DOWN)
            self.add(title, other, edge)
'''


@pytest.mark.render
def test_lint_renders_then_reuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(
        tmp_path / "proj",
        {"scenes": [{"id": "c", "type": "crowded", "beats": [{"text": "Look at this."}]}]},
        {"extensions/crowded.py": EXTENSION},
    )
    code, doc, _ = run_json(["lint", str(root), "--json"], capsys)
    assert code == 1 and doc["rendered"] == ["c"] and doc["stills"] == 1
    rules = {(f["rule"], (f["object"] or {}).get("text")) for f in doc["findings"]}
    assert ("text_overlap", "Second text") in rules and ("off_frame", "Cut off") in rules
    still = Path(doc["findings"][0]["still"])
    with Image.open(still) as image:
        assert image.size == (96, 54)
    code, doc, _ = run_json(["lint", str(root), "--json", "--rule", "off_frame"], capsys)
    assert doc["rendered"] == [] and doc["reused"] == ["c"]
    assert [f["rule"] for f in doc["findings"]] == ["off_frame"] and doc["findings"][0]["severity"] == "error"
