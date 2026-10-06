"""Per-beat actions (DESIGN.md §26): config forms, registry, validation, schema, listing and
tiny renders of reveal / dim / highlight on bullets and bar_chart."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest
import yaml
from manim import ManimColor, tempconfig

from conftest import minimal_config, write_files
from vidgen import actions, extensions, registry, schema
from vidgen.cli import check_project, main, project_problems
from vidgen.config import ActionConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.worker import frame_size
from vidgen.theme import Theme

ROOT = Path(__file__).resolve().parents[1]
FPS = 5
BULLETS = {"heading": "Steps", "items": ["Write the beats", "Pick scene types", "Render it", "Ship it"]}
BARS = {"title": "Sizes", "labels": ["Preview 480p", "720p", "4K"], "values": [0.4, 1.1, 9.8]}


def beats(*actions_per_beat: list[dict[str, Any]] | None, words: str = "one two three four five six") -> list[dict[str, Any]]:
    """One beat per argument, with those actions (``None``: no actions)."""
    return [{"text": words, **({"actions": a} if a else {})} for a in actions_per_beat]


def project_with(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **overrides)))


# ----- config ---------------------------------------------------------------------------------------


def test_canonical_and_shorthand_forms_are_equivalent() -> None:
    canonical = ActionConfig.model_validate({"action": "highlight", "target": "item3", "color": "accent", "at": 0.5})
    short = ActionConfig.model_validate({"highlight": "item3", "color": "accent", "at": 0.5})
    assert canonical.model_dump() == short.model_dump()
    assert (short.action, short.target, short.at, short.options) == ("highlight", "item3", 0.5, {"color": "accent"})
    assert short.targets() == ["item3"] and short.describe() == "highlight item3"
    many = ActionConfig.model_validate({"dim": ["bar1", "bar2"]})
    assert many.targets() == ["bar1", "bar2"] and many.options == {} and many.until is None


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"at": 0.5}, "no action name"),
        ({"target": "x"}, "no action name"),
        ({"highlight": "x", "target": "y"}, "already gives the target"),
        ({"action": "dim", "target": []}, "at least 1 item"),
        ({"action": "dim", "target": "x", "at": 1}, "less than 1"),
        ({"action": "dim", "target": "x", "run_time": 0}, "greater than 0"),
        ({"action": "di m", "target": "x"}, "pattern"),
    ],
)
def test_action_config_errors(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        ActionConfig.model_validate(raw)


def test_shorthand_with_sorted_keys_is_resolved() -> None:
    """A tool that sorts keys (yaml.safe_dump) puts options before the action name."""
    raw = {"at": 0.5, "color": "accent", "highlight": "item3"}
    act = ActionConfig.model_validate(raw)
    assert act.action == "color"   # provisional: the first non-common key
    fixed = act.resolved(["dim", "highlight", "reveal"])
    assert (fixed.action, fixed.target, fixed.at, fixed.options) == ("highlight", "item3", 0.5, {"color": "accent"})
    assert fixed.resolved(["highlight"]) is fixed
    canonical = ActionConfig.model_validate({"action": "dim", "target": "x"})
    assert canonical.resolved(["highlight"]) is canonical


def test_until_must_be_a_later_beat_of_the_scene() -> None:
    scene = {"id": "s", "type": "bullets", "params": BULLETS, "beats": beats(None, [{"dim": "item1", "until": "s_b1"}], None)}
    with pytest.raises(VidgenError) as info:
        parse_config(minimal_config(scenes=[scene]))
    assert "until 's_b1' is not a later beat of scene 's' (later beats: s_b3)" in str(info.value)
    scene["beats"][1]["actions"][0]["until"] = "s_b3"
    parse_config(minimal_config(scenes=[scene]))


# ----- registry ---------------------------------------------------------------------------------


def test_builtin_actions_are_registered() -> None:
    extensions.load_builtins()
    assert registry.action_names() == ["dim", "highlight", "reveal", "transform", "zoom"]
    assert all(a.builtin for a in registry.all_actions())
    assert registry.find_action("dim").cls.reversible and not registry.find_action("reveal").cls.reversible
    assert "did you mean 'highlight'" in registry.unknown_action_message("higlight")


def test_extension_actions_register_collide_and_reset() -> None:
    extensions.load_builtins()

    @registry.action("tick")
    class Tick(actions.Action):
        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    assert registry.find_action("tick").origin != "builtin"
    with pytest.raises(VidgenError, match="defined twice"):
        registry.action("tick")(Tick)
    with pytest.raises(VidgenError, match="same name as a built-in action"):
        registry.action("dim")(Tick)
    saved = registry.snapshot()
    registry.reset()
    assert registry.find_action("tick") is None and registry.find_action("dim") is not None
    registry.restore(saved)
    assert registry.find_action("tick") is not None


def test_bad_action_classes_are_rejected() -> None:
    class NoApply(actions.Action):
        pass

    class Reserved(actions.Action):
        class Options(actions.ActionOptions):
            at: float = 0

        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    class NoRevert(actions.Action):
        reversible = True

        def apply(self, scene, targets):  # type: ignore[no-untyped-def]
            return []

    with pytest.raises(VidgenError, match="implement apply"):
        registry.register_action("a", NoApply)
    with pytest.raises(VidgenError, match="option names at are reserved"):
        registry.register_action("b", Reserved)
    with pytest.raises(VidgenError, match="implement revert"):
        registry.register_action("c", NoRevert)
    with pytest.raises(VidgenError, match="subclass of Action"):
        registry.register_action("d", object)  # type: ignore[arg-type]
    with pytest.raises(VidgenError, match="not bare @action"):
        registry.action(NoApply)  # type: ignore[arg-type]


def test_match_names_with_wildcards() -> None:
    names = ["title", "bar1", "bar:Preview 480p", "bar2", "bar:4K"]
    assert actions.match_names("bar:4K", names) == ["bar:4K"]
    assert actions.match_names("bar:*", names) == ["bar:Preview 480p", "bar:4K"]
    assert actions.match_names("bar?", names) == ["bar1", "bar2"]
    assert actions.match_names("bar[1]", names + ["bar[1]"]) == ["bar[1]"]  # brackets are literal
    assert actions.match_names("nope*", names) == []


def test_builtin_target_names() -> None:
    extensions.load_builtins()
    bullets, bars = registry.get("bullets").cls, registry.get("bar_chart").cls
    params = bullets.validate_params({"items": ["a", {"text": "b", "icon": "cpu"}]})
    assert bullets.target_names(params) == ["item1", "item:a", "item2", "item:b"]
    params = bars.validate_params(BARS)
    assert bars.target_names(params) == ["title", "bar1", "bar:Preview 480p", "bar2", "bar:720p", "bar3", "bar:4K"]
    assert bullets.target_patterns == ("heading", "item<N>", "item:<text>")


# ----- validation -------------------------------------------------------------------------------


def test_validate_reports_bad_actions(make_project) -> None:
    bad = [
        {"reveal": "item9"},
        {"higlight": "item1"},
        {"action": "dim", "target": "item1", "opacity": 2, "colour": "x"},
        {"action": "reveal", "target": "item2", "until": "s_b2"},
        {"highlight": "item1", "color": "nope"},
        {"highlight": "item*x"},
        {"action": "dim"},
    ]
    scenes = [
        {"id": "s", "type": "bullets", "params": BULLETS, "beats": beats(bad, None)},
        {"id": "c", "type": "bar_chart", "params": BARS, "beats": beats([{"dim": "bar:Preview 48p"}])},
        {"id": "q", "type": "quote", "params": {"text": "hi"}, "beats": beats([{"dim": "text"}])},
    ]
    problems = {(p.location, p.message) for p in project_problems(project_with(make_project, scenes))}
    by_location: dict[str, list[str]] = {}
    for location, message in problems:
        by_location.setdefault(location, []).append(message)
    at = "scenes[0].beats[0].actions"
    assert re.search(r"unknown target 'item9' for scene type 'bullets'; did you mean 'item\d'", by_location[f"{at}[0].target"][0])
    assert "targets: heading, item1, item:Write the beats" in by_location[f"{at}[0].target"][0]
    assert "forms: heading, item<N>, item:<text>" in by_location[f"{at}[0].target"][0]
    assert by_location[f"{at}[1].action"] == [
        "unknown action 'higlight'; did you mean 'highlight'? (known actions: dim, highlight, reveal, transform, zoom)"
    ]
    assert "less than or equal to 1" in by_location[f"{at}[2].opacity"][0]
    assert "Extra inputs" in by_location[f"{at}[2].colour"][0]
    assert by_location[f"{at}[3].until"] == ["action 'reveal' cannot be undone; until works with: dim, highlight, zoom"]
    assert "unknown theme color 'nope'" in by_location[f"{at}[4].color"][0]
    assert "unknown target 'item*x'" in by_location[f"{at}[5].target"][0]
    assert by_location[f"{at}[6].target"] == ["action 'dim' needs a target"]
    assert "did you mean 'bar:Preview 480p'" in by_location["scenes[1].beats[0].actions[0].target"][0]
    assert "unknown target 'text' for scene type 'quote' (targets: mark, quote;" in by_location["scenes[2].beats[0].actions[0].target"][0]


def test_action_names_are_checked_even_when_params_are_invalid(make_project) -> None:
    scenes = [{"id": "s", "type": "bullets", "params": {"items": []}, "beats": beats([{"dimm": "item1"}])}]
    lines = check_project(project_with(make_project, scenes))
    assert any(line.startswith("scenes[0].params.items") for line in lines)
    assert any(line.startswith("scenes[0].beats[0].actions[0].action: unknown action 'dimm'") for line in lines)


def test_validate_json_locations(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(scenes=[{"id": "s", "type": "bullets", "params": BULLETS, "beats": beats([{"reveal": "item7"}])}]))
    assert main(["validate", str(root), "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    (problem,) = doc["error"]["problems"]
    assert problem["location"] == "scenes[0].beats[0].actions[0].target" and "unknown target 'item7'" in problem["message"]


def test_render_checks_actions_before_starting_workers(make_project) -> None:
    from vidgen.render.pipeline import render_project

    project = project_with(make_project, [{"id": "s", "type": "bullets", "params": BULLETS, "beats": beats([{"reveal": "item7"}])}])
    with pytest.raises(VidgenError, match=r"scene 's': invalid actions\n  beats\[0\]\.actions\[0\]\.target: unknown target 'item7'"):
        render_project(project, preview=True)


# ----- schema and listing -----------------------------------------------------------------------


def test_schema_describes_both_forms_and_options() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    validator = jsonschema.Draft202012Validator(doc)
    defs = doc["$defs"]
    assert defs["ActionConfig"]["properties"]["action"]["enum"] == ["dim", "highlight", "reveal", "transform", "zoom"]
    assert {"action.dim", "action.highlight", "action.reveal", "ActionShorthand"} <= set(defs)

    def ok(*acts: dict[str, Any]) -> bool:
        scene = {"id": "s", "type": "bullets", "params": BULLETS, "beats": [{"text": "x", "actions": list(acts)}]}
        return validator.is_valid(minimal_config(scenes=[scene]))

    assert ok({"highlight": "item1", "color": "accent", "style": ["box", "underline"]}, {"action": "dim", "target": ["item2"], "opacity": 0.3})
    assert ok({"action": "reveal", "target": "item3", "at": 0.5, "run_time": 1})
    assert not ok({"highlight": "item1", "colour": "accent"})
    assert not ok({"action": "dim", "target": "item1", "color": "accent"})  # highlight's option on dim
    assert ok({"zoom": "item1", "scale": 2}, {"transform": "item1", "into": "item2", "style": "fade"})
    assert not ok({"action": "spin", "target": "item1"})
    assert not ok({"transform": "item1"})                      # into is required
    assert not ok({"zoom": "item1", "scale": 0.5})
    assert not ok({"dim": "item1", "target": "item2"})
    assert not ok({"highlight": "item1", "color": "nope"})
    assert not ok({"action": "dim", "target": "item1", "at": 1.5})


def test_list_scenes_shows_targets_and_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["list-scenes"]) == 0
    out = capsys.readouterr().out
    assert "    targets: heading, item<N>, item:<text>" in out and "    targets: title, bar<N>, bar:<label>" in out
    assert re.search(r"^highlight +builtin +\(run_time 0\.6 s, until\)$", out, flags=re.M)
    assert main(["list-scenes", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    types = {t["name"]: t for t in doc["scene_types"]}
    assert types["bullets"]["targets"] == ["heading", "item<N>", "item:<text>"]
    assert types["quote"]["targets"] == ["mark", "quote", "author", "source"]
    acts = {a["name"]: a for a in doc["actions"]}
    assert (acts["dim"]["reversible"], acts["dim"]["run_time"], acts["reveal"]["needs_target"]) == (True, 0.6, True)
    assert [o["name"] for o in acts["highlight"]["options"]] == ["color", "style"] and acts["highlight"]["doc"]
    from test_json_output import documented

    documented("targets", "actions", "run_time", "reversible", "needs_target", "options")


# ----- rendering ------------------------------------------------------------------------------------


def render(project: Project, scene_id: str, media: Path, size: tuple[int, int] = (160, 90), fade: bool = False) -> Any:
    """Render one scene in-process (without its final fade-out unless ``fade``)."""
    w, h = size
    fw, fh = frame_size(w, h)
    settings = {
        "pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS,
        "media_dir": str(media), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR",
        "output_file": f"{scene_id}_{w}x{h}",
    }
    with tempconfig(settings):
        spec = project.scene(scene_id)
        theme = extensions.activate(project)
        scene = registry.get(spec.type).cls(spec, project, theme)
        if not fade:
            scene.finish = lambda: None
        scene.render()
        return scene


def beat_total(scene: Any) -> float:
    return sum(scene.beat_duration(i) + scene.pad for i in range(len(scene.beats)))


def rgb(mob: Any) -> tuple[float, ...]:
    """The fill colour drawn (of the first part with points)."""
    return tuple(np.round(mob.family_members_with_points()[0].get_fill_color().to_rgb(), 3))


def alpha(mob: Any) -> float:
    return float(max(m.get_fill_opacity() for m in mob.family_members_with_points()))


def color_of(theme: Theme, token: str) -> tuple[float, ...]:
    return tuple(np.round(ManimColor(theme.color(token)).to_rgb(), 3))


def plays(scene: Any, beat: str) -> list[tuple[str, ...]]:
    return [p.animations for p in scene.play_log if p.beat == beat and not p.wait]


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
def test_bullets_actions_render_within_their_beats(make_project, media: Path) -> None:
    acts = beats(
        [{"reveal": "item3"}],                                            # early reveal: beat 3 skips it
        [{"action": "dim", "target": "item1", "until": "s_b4"}, {"highlight": "item:Pick*", "style": ["color", "box"], "until": "s_b4"}],
        [{"highlight": "item4", "at": 0.5}],                              # not shown yet: revealed first
        None,
    )
    project = project_with(make_project, [{"id": "s", "type": "bullets", "params": BULLETS, "beats": acts}], narration={"pad": 0.2, "words_per_second": 4.0})
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b.id] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beats)
    rows = {t.name: t.mobject for t in scene.targets}
    assert [t.name for t in scene.targets] == ["heading", "item1", "item2", "item3", "item4"]
    assert sorted(n for t in scene.targets for n in t.names) == sorted(type(scene).target_names(scene.params))
    # beat 1: heading + item1 by the scene, then item3 by the action; beat 2: item2, then dim +
    # highlight (+ box) together; beat 3: item3 is not revealed again, item4 is revealed for its
    # highlight; beat 4: both undone, item4 not revealed again
    assert plays(scene, "s_b1") == [("FadeIn", "FadeIn"), ("FadeIn",)]
    assert plays(scene, "s_b2") == [("FadeIn",), ("Repaint", "Repaint", "Create")]
    assert plays(scene, "s_b3") == [("FadeIn",), ("Repaint",)]
    assert plays(scene, "s_b4") == [("Repaint", "Repaint", "FadeOut")]
    (late,) = [p for p in scene.play_log if p.beat == "s_b3" and p.animations == ("FadeIn",)]
    start = next(t.start for t in scene.beat_log if t.beat_id == "s_b3")
    assert late.start == pytest.approx(start + 0.5 * scene.beat_duration("s_b3"), abs=0.5 / FPS)  # at: 0.5
    # end state: dim and highlight undone at beat 4, item4 highlighted (no until), the box removed
    assert alpha(rows["item1"]) == pytest.approx(1.0)
    assert rgb(rows["item2"][-1]) == color_of(scene.theme, "text")
    assert rgb(rows["item4"][-1]) == color_of(scene.theme, "highlight")
    assert all(type(m).__name__ != "SurroundingRectangle" for m in scene.mobjects)
    assert all(scene.is_shown(name) for name in rows)


@pytest.mark.render
def test_bar_chart_actions_and_mid_beat_state(make_project, media: Path) -> None:
    acts = beats([{"action": "highlight", "target": "bar:4K", "style": "underline", "color": "accent"}], [{"dim": "bar?", "opacity": 0.5}, {"highlight": "bar1"}])
    params = {**BARS, "reveal": "all"}
    project = project_with(make_project, [{"id": "c", "type": "bar_chart", "params": params, "beats": acts}], narration={"pad": 0.2, "words_per_second": 4.0})
    scene = render(project, "c", media, size=(90, 160))
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    bars = {t.name: t.mobject for t in scene.targets}
    # dim and highlight of bar1 in the same beat: played one after the other; a colour highlight
    # brings the dimmed bar back to its full opacity
    assert alpha(bars["bar1"][0]) == pytest.approx(0.92, abs=0.01)
    assert rgb(bars["bar1"][0]) == color_of(scene.theme, "highlight")
    assert alpha(bars["bar2"][0]) == pytest.approx(0.92 * 0.5, abs=0.01) and rgb(bars["bar2"][0]) == color_of(scene.theme, "primary")
    assert any(type(m).__name__ == "Underline" for m in scene.mobjects)
    assert len(plays(scene, "c_b2")) == 2


@pytest.mark.render
def test_actions_are_shortened_to_fit_the_beat(make_project, media: Path) -> None:
    acts = beats([{"action": "highlight", "target": "item1", "run_time": 5, "at": 0.9}], words="one two")
    project = project_with(make_project, [{"id": "s", "type": "bullets", "params": {"items": ["a"]}, "beats": acts}], narration={"pad": 0.2, "words_per_second": 4.0})
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    (record,) = [p for p in scene.play_log if p.animations == ("Repaint",)]
    assert record.requested == 5 and record.end <= float(scene.renderer.time) + 1e-6


@pytest.mark.render
def test_extension_targets_waits_and_actions_without_time(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = make_project(minimal_config(
        scenes=[
            {"id": "w", "type": "boxes", "beats": beats([{"tick": "box1"}, {"highlight": "box2"}])},
            {"id": "busy", "type": "boxes", "params": {"busy": True}, "beats": beats([{"highlight": "box*"}])},
        ],
        narration={"pad": 0.2, "words_per_second": 4.0},
    ))
    write_files(root, {"extensions/boxes.py": '''
        from vidgen.api import *


        @action("tick")
        class Tick(Action):
            """Put a dot right of each target."""

            reversible = True

            def apply(self, scene, targets):
                self.dots = [Dot(color=scene.theme.color("tertiary")).next_to(t.mobject, RIGHT) for t in targets]
                return [FadeIn(d) for d in self.dots]

            def revert(self, scene, targets):
                return [FadeOut(d) for d in self.dots]


        @scene("boxes")
        class Boxes(NarratedScene):
            target_patterns = ("box<N>",)

            class Params(SceneParams):
                busy: bool = False

            @classmethod
            def target_names(cls, params):
                return ["box1", "box2"]

            def construct(self):
                squares = VGroup(Square(0.5), Square(0.5)).arrange(RIGHT)
                for i, sq in enumerate(squares, 1):
                    self.target(f"box{i}", sq)
                for i, d in self.timeline():
                    if self.params.busy:   # the narration's whole length: no wait left for actions
                        self.play(FadeIn(squares), run_time=d + self.pad)
                    else:
                        self.add(squares)
                        self.wait(d / 2)   # a plain Manim wait: actions due meanwhile run inside it
    '''})
    project = Project.load(root)
    assert check_project(project) == []
    scene = render(project, "w", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    (record,) = [p for p in scene.play_log if p.beat == "w_b1" and not p.wait]
    assert record.animations == ("FadeIn", "Repaint")   # tick + highlight, in the plain wait
    assert record.start < scene.beat_duration(0) / 2
    assert any(type(m).__name__ == "Dot" for m in scene.mobjects)
    with caplog.at_level(logging.WARNING, logger="vidgen"):
        busy = render(project, "busy", media)
    assert "no time left for actions (highlight box*); applied without animation" in caplog.text
    assert all(rgb(t.mobject) == color_of(busy.theme, "highlight") for t in busy.targets)
    assert float(busy.renderer.time) == pytest.approx(beat_total(busy), abs=1.5 / FPS)


@pytest.mark.render
def test_example_minimal_actions_render(media: Path) -> None:
    project = Project.load(ROOT / "examples" / "minimal")
    scene = render(project, "sizes", media, fade=True)
    assert [len(b.actions) for b in scene.beats] == [0, 1, 2]
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene) + scene.outro, abs=1.5 / FPS)


def extending_example() -> tuple[str, list[dict[str, Any]]]:
    """The extension module and scene of docs/EXTENDING.md "Per-beat actions"."""
    text = (ROOT / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    section = text[text.index("## 8. Per-beat actions") :]
    code = re.search(r"```python\n(# extensions/checklist\.py\n.*?)```", section, flags=re.S)[1]
    scenes = yaml.safe_load(re.search(r"```yaml\n(.*?)```", section, flags=re.S)[1])
    return code, scenes


@pytest.mark.render
def test_extending_example_validates_and_renders(make_project, media: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, scenes = extending_example()
    root = make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 4.0}))
    (root / "extensions").mkdir()
    (root / "extensions" / "checklist.py").write_text(code, encoding="utf-8")
    project = Project.load(root)
    assert check_project(project) == []
    assert main(["list-scenes", str(root)]) == 0
    out = capsys.readouterr().out
    assert "    targets: item<N>" in out and re.search(r"^tick +extensions/checklist\.py +\(run_time 0\.5 s, until\)$", out, flags=re.M)
    scene = render(project, "plan", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    marks = [m for m in scene.mobjects if type(m).__name__ == "Icon"]
    stroke = tuple(np.round(marks[1][1].get_stroke_color().to_rgb(), 3))
    assert len(marks) == 2 and stroke == color_of(scene.theme, "accent")
    assert rgb(scene.targets[1].mobject) == color_of(scene.theme, "text")   # highlight undone at beat 3
