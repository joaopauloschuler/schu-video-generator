"""Final review (Step 60): fixes found while reviewing Steps 8–59 (DESIGN.md §63)."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest
from manim import Square

from conftest import minimal_config, write_clip
from vidgen.charts import mix_colors
from vidgen.clips import ClipTiming, clip_audio, probe_clip
from vidgen.errors import VidgenError
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.project import CONFINE_ENV, Project, confinement_problems
from vidgen.scenes.code import BAND_OPACITIES, INK_RATIO, readable_band
from vidgen.theme import Theme


# ----- code: the highlight band keeps the syntax colours readable ----------------------------------


def _ratio(a: str, b: str) -> float:
    return contrast_ratio(hex_rgb(a), hex_rgb(b))


def test_code_band_is_lighter_when_a_syntax_colour_would_lose_contrast() -> None:
    """GitHub-dark's keyword red (#FF7B72) was 4.15:1 on the 0.2 band of dark_tech (lint
    `contrast` on examples/plan); the band now fades until every colour keeps 4.6:1."""
    theme = Theme()
    scene = type("FakeScene", (), {"theme": theme})()
    band = theme.color("highlight")
    surface = theme.color("surface")
    rows = [Square().set_fill(c, opacity=1) for c in ("#FF7B72", "#79C0FF", "#E6EDF3")]
    opacity = readable_band(scene, rows, band)
    assert opacity < BAND_OPACITIES[0]
    behind = mix_colors(band, surface, opacity, theme=theme)
    assert all(_ratio(r.get_fill_color().to_hex(), behind) >= INK_RATIO for r in rows)
    assert rows[0].get_fill_color().to_hex().upper() == "#FF7B72"   # colours kept: only the band changed


def test_code_band_mixes_an_unreadable_syntax_colour_towards_the_text() -> None:
    theme = Theme()
    scene = type("FakeScene", (), {"theme": theme})()
    dark = Square().set_fill("#30363D", opacity=1)   # a comment colour nearly the window's
    opacity = readable_band(scene, [dark], theme.color("highlight"))
    assert opacity == BAND_OPACITIES[-1]
    ink = dark.get_fill_color().to_hex()
    assert ink.upper() != "#30363D"
    assert _ratio(ink, theme.color("surface")) >= INK_RATIO


# ----- a silent scene renders exactly the planned frames -------------------------------------------


@pytest.mark.render
def test_silent_scenes_render_the_planned_frames_on_half_frames(make_project) -> None:
    """5 fps, a 1.2 s chapter card: (1.2 - 0.5) x 5 is a half frame; plan and render used to round
    it differently (plan 7 frames, render 6)."""
    from vidgen.extensions import load_builtins
    from vidgen.render.pipeline import render_project
    from vidgen.videoplan import VideoPlan

    scenes = [
        {"id": "a", "type": "chapter", "params": {"number": 1, "title": "One"}, "duration": 1.2},
        {"id": "b", "type": "text_card", "params": {"text": "Two"}, "duration": 1.3},
        {"id": "c", "type": "title", "params": {"title": "Three"}, "duration": 0.9},
    ]
    root = make_project(minimal_config(preview={"width": 160, "height": 90, "fps": 5}, scenes=scenes))
    project = Project.load(root)
    result = render_project(project, preview=True, no_audio=True)
    load_builtins()
    plan = VideoPlan(project, 5)
    rendered = {s["id"]: s["duration"] for s in result.timings["scenes"]}
    for spec in project.config.scenes:
        assert round(rendered[spec.id] * 5) == round(plan.scene(spec.id).duration * 5), spec.id
    assert round(rendered["a"] * 5) == 7


# ----- render reuses current scene renders ---------------------------------------------------------


@pytest.mark.render
def test_render_reuses_scenes_whose_inputs_did_not_change(make_project) -> None:
    from vidgen.render.pipeline import render_project
    from vidgen.storyboard import make_storyboard

    scenes = [
        {"id": "a", "type": "text_card", "params": {"text": "One"}, "duration": 1.0},
        {"id": "b", "type": "text_card", "params": {"text": "Two"}, "duration": 1.0},
    ]
    config = minimal_config(preview={"width": 160, "height": 90, "fps": 5}, scenes=scenes)
    root = make_project(config)
    make_storyboard(Project.load(root), preview=True)                     # renders both, with stills
    first = render_project(Project.load(root), preview=True)
    assert (first.rendered, first.reused) == ([], ["a", "b"])            # the storyboard's renders
    config["scenes"][1]["params"]["text"] = "Three"
    root = make_project(config)
    second = render_project(Project.load(root), preview=True)
    assert (second.rendered, second.reused) == (["b"], ["a"])
    forced = render_project(Project.load(root), preview=True, force=True)
    assert forced.rendered == ["a", "b"]


# ----- plan: stat labels, ranges, bare web addresses -----------------------------------------------


def test_plan_stat_label_and_ranges() -> None:
    from vidgen.plan import _stat_params

    assert _stat_params("A cache can make the same page 40x faster.", None)["label"] == "faster with a cache"
    assert _stat_params("It makes pages 40x faster.", None)["label"] != "faster with it"
    assert _stat_params("Keep it between 20 and 80 percent.", None) is None   # a range is not one number
    assert _stat_params("Sales grew 40% last year.", None)["value"] == 40


def test_plan_placeholder_beats_say_the_whole_item() -> None:
    """A step without prose is narrated by its item, not by the label cut from it ("Steep for four.")."""
    from vidgen.outline import parse_outline
    from vidgen.plan import PlanOptions, make_plan

    plan = make_plan(parse_outline("## Tea\n\n1. Boil fresh water\n2. Add two spoons of leaves\n3. Steep for four minutes\n"), PlanOptions())
    (scene,) = [s for s in plan.scenes if s.type == "process"]
    assert scene.params["stages"][2] == "Steep for four"
    assert scene.beats[2] == "Steep for four minutes."


def test_plain_collects_bare_web_addresses() -> None:
    from vidgen.outline import plain

    assert plain("Read more at batteryuniversity.com.").links == ["batteryuniversity.com"]
    assert plain("See https://example.org/a and www.example.com/docs").links == ["https://example.org/a", "www.example.com/docs"]
    assert plain("Node.js and e.g. config.yaml are not links").links == []


# ----- clip sound: mono at full level --------------------------------------------------------------


def test_mono_clip_sound_plays_at_full_level_on_both_channels(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "mono.mp4", seconds=2)   # a mono 440 Hz sine, amplitude 1/8
    assert probe_clip(clip).channels == 1
    out = tmp_path / "a.wav"
    assert clip_audio(clip, out, ClipTiming(0, 2), length=2.0, fade=0)
    with wave.open(str(out)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2) / 32768
    middle = data[24000:72000]
    assert np.allclose(middle[:, 0], middle[:, 1])
    rms = float(np.sqrt(np.mean(middle[:, 0] ** 2)))
    assert rms == pytest.approx(0.125 / np.sqrt(2), rel=0.05)   # not 3 dB down (0.0625)


# ----- MCP: files a config names stay inside the root ----------------------------------------------


def test_confinement_finds_config_files_outside_the_folder(tmp_path: Path) -> None:
    root = tmp_path / "videos" / "p"
    root.mkdir(parents=True)
    (tmp_path / "secret.png").write_bytes(b"x")
    data = {
        "pronunciation_file": ["ok.yaml", "../../secret.yaml"],
        "scenes": [
            {"id": "a", "type": "image", "params": {"path": "../../secret.png"}},
            {"id": "b", "type": "quote", "params": {"text": "Hi", "source": "Proceedings, 1975"}},
            {"id": "c", "type": "image", "params": {"path": "assets/a.png"}},
        ],
        "music": {"source": "calm"},
        "variants": {"v": {"thumbnail": {"title": "T", "image": "/etc/passwd"}}},
    }
    problems = confinement_problems(data, root, tmp_path / "videos")
    assert len(problems) == 3
    assert any(p.startswith("pronunciation_file[1]:") for p in problems)
    assert any(p.startswith("scenes[0].params.path:") for p in problems)
    assert any(p.startswith("variants.v.thumbnail.image:") for p in problems)
    assert len(confinement_problems(data, root, tmp_path)) == 1   # only /etc/passwd is outside tmp_path


def test_project_load_refuses_outside_files_only_when_confined(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    scenes = [{"id": "a", "type": "image", "params": {"path": "../../outside.png"}, "beats": [{"text": "A picture."}]}]
    root = make_project(minimal_config(scenes=scenes))
    Project.load(root)   # not confined: loads (validate reports the missing file)
    monkeypatch.setenv(CONFINE_ENV, str(root))
    with pytest.raises(VidgenError, match="outside the allowed folder"):
        Project.load(root)


# ----- post_render hooks see the thumbnail ---------------------------------------------------------


@pytest.mark.render
def test_post_render_hook_runs_after_the_thumbnail(make_project) -> None:
    from vidgen.render.pipeline import render_project

    scenes = [{"id": "a", "type": "text_card", "params": {"text": "Card"}, "duration": 1.0}]
    root = make_project(minimal_config(preview={"width": 160, "height": 90, "fps": 5}, scenes=scenes, thumbnail={"title": "A thumbnail"}))
    (root / "extensions").mkdir(exist_ok=True)
    (root / "extensions" / "hooks.py").write_text(
        "import json\nfrom pathlib import Path\nfrom vidgen.api import *\n\n\n"
        "@hook(\"post_render\")\n"
        "def seen(ctx):\n"
        "    t = ctx.data[\"thumbnail\"]\n"
        "    out = {\"thumbnail\": str(t), \"exists\": t is not None and Path(t).is_file()}\n"
        "    (ctx.project.root / \"hook.json\").write_text(json.dumps(out), encoding=\"utf-8\")\n",
        encoding="utf-8",
    )
    result = render_project(Project.load(root), preview=True, no_audio=True)
    seen = json.loads((root / "hook.json").read_text(encoding="utf-8"))
    assert result.thumbnail is not None
    assert seen == {"thumbnail": str(result.thumbnail.path), "exists": True}
