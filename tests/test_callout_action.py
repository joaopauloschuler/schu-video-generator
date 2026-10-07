"""Step 41: the ``callout`` beat action (callouts on any scene, by target or by coordinates, for
one beat) and the ``screenshot`` ``caption`` param."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import BARS, BULLETS, beat_total, beats, plays, render
from test_screenshot import quadrants
from vidgen import actions, extensions, registry, schema
from vidgen.callouts import Callout, mobject_region
from vidgen.cli import main, project_problems
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.project import Project
from vidgen.regions import Region, frame_region
from vidgen.theme import Theme

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    root = make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides))
    (root / "assets").mkdir(exist_ok=True)
    Image.fromarray(quadrants((160, 100))).save(root / "assets" / "app.png")
    return Project.load(root)


def options(**raw: Any) -> Any:
    extensions.load_builtins()
    return registry.find_action("callout").cls.Options.model_validate(raw, context={"theme": Theme()})


def made(scene: Any, k: int = 0) -> Callout:
    """The callout the ``k``-th callout action of the scene built."""
    uses = [u for u in scene._actions.uses if u.kind.name == "callout"]
    return uses[k].action.made


def overlaps(a: Region, b: Region) -> bool:
    return min(a.x1, b.x1) > max(a.x0, b.x0) and min(a.y1, b.y1) > max(a.y0, b.y0)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- options and validation ---------------------------------------------------------------------


def test_options_defaults_and_errors() -> None:
    o = options()
    assert (o.kind, o.label, o.area, o.within, o.color, o.keep, o.name) == ("box", "", None, "frame", "highlight", False, None)
    assert options(kind="spotlight", area=[0.1, 0.1, 0.5, 0.5]).area == [0.1, 0.1, 0.5, 0.5]
    assert options(area=[300, 20], units="px").units == "px"
    bad = [
        ({"area": [0.1, 0.2, 0.3]}, r"\[x, y, w, h\] or \[x, y\]"),
        ({"area": [-0.1, 0.2]}, "cannot be negative"),
        ({"area": [0.1, 0.2, 0, 0.1]}, "more than 0"),
        ({"area": [0.8, 0.2, 0.3, 0.1]}, "does not fit in 0-1"),
        ({"kind": "spotlight", "area": [0.5, 0.5]}, "needs an area with a size"),
        ({"kind": "label"}, "needs a label text"),
        ({"kind": "magnifier"}, "needs the area of the picture"),
        ({"kind": "box", "curved": True}, "only arrows"),
        ({"kind": "box", "zoom": 3}, "only for a magnifier"),
        ({"within": "safe"}, "only with an area"),
        ({"kind": "star"}, "box"),
        ({"colour": "accent"}, "colour"),
    ]
    for raw, message in bad:
        with pytest.raises(ValidationError, match=message):
            options(**raw)


def test_validate_reports_callout_problems(make_project) -> None:
    acts = [
        {"action": "callout", "label": "x"},                                         # no target, no area
        {"callout": "bar1", "keep": True, "until": "c_b2"},
        {"callout": "bar1", "name": "bar2"},                                         # taken by the chart
        {"action": "callout", "kind": "magnifier", "area": [0, 0, 0.5, 0.5]},       # no picture target
        {"callout": "bar1", "area": [0.1, 0.1], "within": "safe"},
        {"callout": "bar1", "name": "bad name!"},
        {"dim": "later"},                                                            # named only below
        {"callout": "bar:4K", "name": "later"},
    ]
    scenes = [{"id": "c", "type": "bar_chart", "params": BARS, "beats": beats(acts, None)}]
    problems = {(p.location, p.message) for p in project_problems(load(make_project, scenes))}
    at = "scenes[0].beats[0].actions"
    by = {loc: msg for loc, msg in problems}
    assert "needs a target or an area" in by[f"{at}[0].target"]
    assert "give one of them" in by[f"{at}[1].keep"]
    assert by[f"{at}[2].name"] == "target name 'bar2' is already taken in this scene; pick another"
    assert "needs the target showing the picture" in by[f"{at}[3].target"]
    assert "within is for areas of the frame" in by[f"{at}[4].within"]
    assert "invalid target name 'bad name!'" in by[f"{at}[5].name"]
    assert "unknown target 'later'" in by[f"{at}[6].target"]
    assert not any(loc.startswith(f"{at}[7]") for loc, _ in problems)


def test_named_callouts_are_targets_of_later_actions_and_types_without_targets_take_areas(make_project) -> None:
    scenes = [
        {"id": "c", "type": "bar_chart", "params": BARS,
         "beats": beats([{"callout": "bar:4K", "label": "Slow", "name": "slow", "keep": True}], [{"dim": "slow"}, {"highlight": "slow", "style": "box"}])},
        {"id": "t", "type": "text_card", "params": {"text": "Hello"}, "beats": beats([{"action": "callout", "area": [0.1, 0.1, 0.2, 0.2]}])},
    ]
    assert project_problems(load(make_project, scenes)) == []


def test_until_next_beat_needs_a_reversible_action() -> None:
    class Bad(actions.Action):
        until_next_beat = True

        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    with pytest.raises(VidgenError, match="until_next_beat actions must be reversible"):
        actions.check_action_class("bad", Bad)


def test_schema_and_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    validator = jsonschema.Draft202012Validator(doc)
    assert "action.callout" in doc["$defs"]

    def ok(*acts: dict[str, Any]) -> bool:
        scene = {"id": "s", "type": "bullets", "params": BULLETS, "beats": [{"text": "x", "actions": list(acts)}]}
        return validator.is_valid(minimal_config(scenes=[scene]))

    assert ok({"callout": "item1", "kind": "arrow", "label": "Here", "curved": True, "until": "s_b2"})
    assert ok({"action": "callout", "area": [0.1, 0.2, 0.3, 0.1], "within": "safe", "kind": "spotlight"})
    assert ok({"callout": None, "area": [0.5, 0.5], "kind": "circle"})
    assert not ok({"callout": "item1", "kind": "star"})
    assert not ok({"callout": "item1", "colour": "accent"})
    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^callout +builtin +\(run_time 0\.8 s, until, undone when the next beat starts\)$", out, flags=re.M)
    assert main(["list-scenes", "--json"]) == 0
    acts = {a["name"]: a for a in json.loads(capsys.readouterr().out)["actions"]}
    assert acts["callout"]["until_next_beat"] and not acts["callout"]["needs_target"] and not acts["dim"]["until_next_beat"]


# ----- rendering ------------------------------------------------------------------------------------


@pytest.mark.render
def test_callout_on_a_target_lasts_its_beat_and_keep_stays(make_project, media: Path) -> None:
    acts = beats(
        [{"callout": "bar:4K", "kind": "arrow", "label": "Slowest"}, {"callout": "bar1", "kind": "circle", "keep": True}],
        [{"callout": "bar2", "until": "c_b3", "label": "Middle"}],
        None,
    )
    project = load(make_project, [{"id": "c", "type": "bar_chart", "params": {**BARS, "reveal": "all"}, "beats": acts}])
    scene = render(project, "c", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / 5)
    arrow, ring, middle = made(scene, 0), made(scene, 1), made(scene, 2)
    assert (arrow.kind, ring.kind, middle.kind) == ("arrow", "circle", "box")
    # the arrow points at the bar with its value (the target's outline), its label is off the bar
    bar = scene.find_targets("bar:4K")[0]
    outline = mobject_region(bar.outline)
    assert arrow.area == outline and not overlaps(mobject_region(arrow.tag), outline)
    # beat 2 starts: the arrow fades (next beat), the kept ring stays; beat 3: the box with until goes
    assert plays(scene, "c_b2") == [("Fade", "Fade", "Create", "FadeIn")]   # undone first, then the new one
    assert not scene.on_screen_parts(arrow) and not scene.on_screen_parts(middle)
    assert scene.on_screen_parts(ring)
    assert any("Fade" in p for p in plays(scene, "c_b3"))
    # over everything else of the scene
    assert arrow.mark.z_index > max(m.z_index for m in bar.mobject.get_family())


@pytest.mark.render
def test_callout_by_coordinates_label_spotlight_and_named_target(make_project, media: Path) -> None:
    acts = beats(
        [{"action": "callout", "area": [0.1, 0.2, 0.3, 0.25], "label": "Here", "keep": True, "name": "spot"},
         {"action": "callout", "kind": "spotlight", "area": [0.5, 0.5, 0.2, 0.2], "within": "safe"},
         {"callout": "text", "kind": "label", "label": "Note"}],
        [{"dim": "spot"}],
    )
    project = load(make_project, [{"id": "t", "type": "text_card", "params": {"text": "Hello"}, "beats": acts}])
    scene = render(project, "t", media)
    box, shade, note = made(scene, 0), made(scene, 1), made(scene, 2)
    f = frame_region()
    assert box.area.x0 == pytest.approx(f.x0 + 0.1 * f.width) and box.area.y1 == pytest.approx(f.y1 - 0.2 * f.height)
    assert box.area.width == pytest.approx(0.3 * f.width) and box.area.height == pytest.approx(0.25 * f.height)
    safe = scene.safe_area
    assert shade.area.x0 == pytest.approx(safe.x0 + 0.5 * safe.width)
    assert type(shade.mark).__name__ == "Cutout" and shade.mark.z_index < box.mark.z_index
    text = mobject_region(scene.find_targets("text")[0].mobject)
    assert note.kind == "label" and note.mark.is_label and not overlaps(mobject_region(note.mark), text)
    # the named box is a target: dimmed in beat 2, its label recoloured to stay readable
    target = scene.find_targets("spot")[0]
    assert target.mobject is box and target.on_fill
    glyphs = box.tag.text.family_members_with_points()
    assert box.tag.plate.get_fill_opacity() < 0.6 and min(g.get_fill_opacity() for g in glyphs) > 0.6


@pytest.mark.render
def test_labels_keep_clear_of_text_and_a_zoomed_camera_gets_smaller_callouts(make_project, media: Path) -> None:
    acts = beats(
        [{"callout": "item2", "kind": "arrow", "label": "This one"}],
        [{"zoom": "item3"}, {"callout": "item3", "at": 0.5, "label": "Zoomed"}],
    )
    project = load(make_project, [{"id": "s", "type": "bullets", "params": {**BULLETS, "reveal": "all"}, "beats": acts}])
    scene = render(project, "s", media, size=(320, 180))
    arrow, zoomed = made(scene, 0), made(scene, 1)
    tag = mobject_region(arrow.tag)
    for t in scene.targets:
        if t.name.startswith("item") or t.name == "heading":
            assert not overlaps(tag, mobject_region(t.mobject[-1] if t.name != "heading" else t.mobject)), t.name
    assert tag.x0 >= scene.safe_area.x0 - 1e-6 and tag.x1 <= scene.safe_area.x1 + 1e-6
    assert zoomed.mark.get_stroke_width() < arrow.mark.get_stroke_width()     # built at 1 / magnification
    assert zoomed.tag.height < arrow.tag.height


@pytest.mark.render
def test_a_callout_due_with_a_zoom_is_built_for_the_zoomed_view(make_project, media: Path) -> None:
    acts = beats(
        [{"callout": "item2", "label": "Plain"}],
        [{"callout": "item3", "label": "Zoomed"}, {"zoom": "item3"}],   # same frame, written first
    )
    project = load(make_project, [{"id": "z", "type": "bullets", "params": {**BULLETS, "reveal": "all"}, "beats": acts}])
    scene = render(project, "z", media, size=(320, 180))
    plain, zoomed = made(scene, 0), made(scene, 1)
    assert zoomed.tag.height < 0.8 * plain.tag.height   # built after the camera moved in


@pytest.mark.render
def test_magnifier_on_an_image_target_and_on_other_targets(make_project, media: Path) -> None:
    acts = beats([{"callout": "image", "kind": "magnifier", "area": [0.1, 0.1, 0.25, 0.25], "label": "Detail"}])
    project = load(make_project, [{"id": "i", "type": "image", "params": {"path": "assets/app.png"}, "beats": acts},
                                  {"id": "s", "type": "bullets", "params": BULLETS, "beats": beats([{"callout": "item1", "kind": "magnifier", "area": [0, 0, 0.5, 0.5]}])}])
    scene = render(project, "i", media)
    inset = made(scene)
    assert inset.kind == "magnifier"
    img = scene.find_targets("image")[0].mobject
    picture = mobject_region(img if not img.submobjects else img[0])
    assert inset.area.x0 == pytest.approx(picture.x0 + 0.1 * picture.width, abs=1e-3)
    with pytest.raises(VidgenError, match="a magnifier needs a still picture, the target shows no picture"):
        render(project, "s", media)


@pytest.mark.render
@pytest.mark.slow
def test_callouts_lint_clean_in_landscape_and_portrait(make_project) -> None:
    scenes = [
        {"id": "c", "type": "bar_chart", "params": BARS,
         "beats": beats([{"callout": "bar:4K", "kind": "arrow", "label": "Slowest by far", "at": 0.3}],
                        [{"callout": "bar1", "kind": "label", "label": "Preview", "at": 0.3}, {"action": "callout", "kind": "spotlight", "area": [0.2, 0.3, 0.6, 0.5]}])},
        {"id": "s", "type": "bullets", "params": {**BULLETS, "reveal": "all"},
         "beats": beats([{"callout": "item3", "kind": "box", "label": "Most time goes here", "at": 0.3}])},
    ]
    for preview in ({"width": 320, "height": 180, "fps": 5}, {"width": 180, "height": 320, "fps": 5}):
        project = load(make_project, scenes, preview=preview)
        result = lint_project(project, rules=["off_frame", "safe_area", "text_overlap", "covered_text", "label_spacing", "min_font", "contrast"])
        assert [(f.scene, f.rule, f.message) for f in result.findings] == []


def test_label_spot_side_is_kept_only_while_clear() -> None:
    """Step 57: a ``side`` whose spots are all blocked (a neighbour's bar) gives way; a spot
    clearly nearer a rival than the anchor is avoided; ``straight`` prefers above / below."""
    from vidgen.callouts import _misleading, label_spot

    bounds = Region(-7, -4, 7, 4)
    anchor = Region(0, -2, 1, 0)                 # a bar with its value
    neighbour = Region(1.2, -4, 2.2, 1)          # the taller bar to its right, down to its axis label
    spot = label_spot((1.5, 0.4), anchor, bounds=bounds, avoid=[neighbour], gaps=[0.15, 0.35], side="right")
    assert not overlaps(spot, neighbour) and spot.y0 >= anchor.y1        # moved above, not onto the neighbour
    free = label_spot((1.5, 0.4), anchor, bounds=bounds, gaps=[0.15, 0.35], side="right")
    assert free.x0 >= anchor.x1                                           # nothing in the way: the side holds
    straight = label_spot((1.5, 0.4), anchor, bounds=bounds, gaps=[0.15, 0.35], straight=True)
    assert straight.center[0] == pytest.approx(anchor.center[0]) and straight.y0 > anchor.y1
    rival = Region(-1.6, 0.2, -0.2, 0.5)         # a neighbour's value up and left
    plain = label_spot((1.5, 0.4), anchor, bounds=bounds, gaps=[0.15, 0.35], side="left")
    assert _misleading(plain, anchor, [rival])                            # up-left: by the rival's value
    spot = label_spot((1.5, 0.4), anchor, bounds=bounds, gaps=[0.15, 0.35], rivals=[rival], side="left")
    assert not _misleading(spot, anchor, [rival]) and spot.x1 <= anchor.x0 + 1e-9


@pytest.mark.render
def test_label_callouts_on_a_crowded_bar_chart(make_project, media: Path) -> None:
    """Step 56's routed case: ``kind: label`` with ``side: right | top | left`` on seven bars sat
    on a neighbour's bar or against values / the title; now each label is over its own bar and
    lint's ``label_spacing`` is clean, in 16:9 and 9:16."""
    params = {"title": "Render time per minute of video", "labels": ["240p", "360p", "480p", "720p", "1080p", "1440p", "4K"],
              "values": [0.2, 0.3, 0.4, 1.1, 2.6, 5.2, 9.8], "unit": " min"}
    acts = beats([{"callout": "bar:1080p", "kind": "label", "label": "Default", "side": "right"}],
                 [{"callout": "bar:4K", "kind": "label", "label": "Slowest", "side": "top"}],
                 [{"callout": "bar:480p", "kind": "label", "label": "Preview", "side": "left"}])
    for preview in ({"width": 320, "height": 180, "fps": 5}, {"width": 180, "height": 320, "fps": 5}):
        project = load(make_project, [{"id": "c", "type": "bar_chart", "params": params, "beats": acts}], preview=preview)
        result = lint_project(project, rules=["text_overlap", "covered_text", "label_spacing", "off_frame"])
        assert [(f.rule, f.message) for f in result.findings] == [], preview
    scene = render(load(make_project, [{"id": "c", "type": "bar_chart", "params": params, "beats": acts}]), "c", media, size=(320, 180))
    bars = {f"bar:{n}": mobject_region(scene.find_targets(f"bar:{n}")[0].mobject) for n in params["labels"]}
    for k, name in enumerate(("bar:1080p", "bar:4K", "bar:480p")):
        label = mobject_region(made(scene, k).mark)
        nearest = min(bars, key=lambda n: abs(bars[n].center[0] - label.center[0]))
        assert nearest == name, (name, nearest)


# ----- screenshot caption -------------------------------------------------------------------------


def test_screenshot_caption_param_and_target() -> None:
    extensions.load_builtins()
    cls = registry.get("screenshot").cls
    p = cls.validate_params({"path": "a.png", "title": "T", "caption": "A made-up app"}, Theme())
    assert (p.caption, p.caption_size, p.caption_color) == ("A made-up app", "caption", "text")
    assert cls.target_names(p) == ["title", "image", "caption"]
    assert "caption" in cls.target_patterns
    clip = registry.get("video_clip").cls
    assert clip.target_names(clip.validate_params({"path": "a.mp4", "caption": "c"}, Theme())) == ["clip", "caption"]


@pytest.mark.render
def test_screenshot_caption_sits_under_the_picture(make_project, media: Path) -> None:
    steps = [{"box": [0.1, 0.1, 0.3, 0.2], "label": "Search", "side": "bottom"}, {"callouts": [{"box": [0.5, 0.5, 0.2, 0.2]}], "focus": True}]
    project = load(make_project, [{"id": "s", "type": "screenshot", "params": {"path": "assets/app.png", "title": "App", "caption": "A made-up app", "steps": steps},
                                   "beats": beats(None, None)}])
    scene = render(project, "s", media)
    caption = mobject_region(scene.find_targets("caption")[0].mobject)
    picture = mobject_region(scene.find_targets("image")[0].mobject)
    assert caption.y1 < picture.y0 and caption.y0 >= scene.safe_area.y0 - 1e-6
    assert not overlaps(mobject_region(scene._callouts[0][0].tag), caption)
    # shown with the picture, gone while the camera is in on step 2 (it would be enlarged)
    assert "FadeIn" in plays(scene, "s_b1")[0] and "Fade" in plays(scene, "s_b2")[0]
    assert not scene.is_shown("caption")
