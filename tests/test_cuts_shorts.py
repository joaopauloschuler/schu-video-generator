"""Cuts and Shorts (DESIGN.md §101): ``cut:`` (scenes and beats of a longer video, with changes, a
hook and an end card), ``shorts:`` (the app's zones kept clear by overlays, lint
``shorts_safe_area`` / ``shorts_length``) and ``zoom`` with ``hold``."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vidgen.config import ShortsConfig, ShortsLengthRule, ShortsSafeAreaRule, VideoConfig
from vidgen.cuts import apply_cut, merge_params, shorts_warnings
from vidgen.errors import VidgenError
from vidgen.lint.rules import RULES, SceneContext, StillContext
from vidgen.project import Project


def _story() -> dict[str, Any]:
    return {
        "title": "Kite day",
        "characters": [{"name": "ana"}, {"name": "ben"}],
        "overlays": [{"type": "watermark", "text": "demo"}],
        "scenes": [
            {"id": "title", "type": "text_card", "params": {"text": "Kite day"}, "duration": 1},
            {
                "id": "park",
                "type": "stage",
                "params": {"characters": [{"name": "ana", "at": 0.3}, {"name": "ben", "at": 0.7, "expression": "happy"}]},
                "beats": [{"text": "Ana had a kite."}, {"text": "Ben had none."}, {"id": "wind", "text": "Then the wind came."}],
            },
            {"id": "sky", "type": "text_card", "params": {"text": "Up!"}, "beats": [{"text": "Up it went."}]},
        ],
    }


def _cut(data: dict[str, Any], cut: dict[str, Any]) -> dict[str, Any]:
    out, _ = apply_cut({**data, "cut": cut})
    return out


# ----- apply_cut -----------------------------------------------------------------------------------


def test_a_cut_keeps_scenes_and_beats_with_their_ids() -> None:
    out = _cut(_story(), {"scenes": [{"scene": "park", "beats": ["wind", "park_b2"]}, "sky"]})
    assert [s["id"] for s in out["scenes"]] == ["park", "sky"]
    assert [b["id"] for b in out["scenes"][0]["beats"]] == ["wind", "park_b2"]   # listed order, ids of the full video
    assert out["scenes"][1]["beats"][0]["id"] == "sky_b1"
    config = VideoConfig.model_validate(out)
    assert [b.id for b in config.scenes[0].beats] == ["wind", "park_b2"]


def test_a_range_of_beats() -> None:
    park = _cut(_story(), {"scenes": [{"scene": "park", "beats": {"from": "park_b2"}}]})["scenes"][0]
    assert [b["id"] for b in park["beats"]] == ["park_b2", "wind"]
    park = _cut(_story(), {"scenes": [{"scene": "park", "beats": {"to": "park_b2"}}]})["scenes"][0]
    assert [b["id"] for b in park["beats"]] == ["park_b1", "park_b2"]


def test_changes_to_scenes_and_beats() -> None:
    story = _story()
    story["scenes"][1]["transition"] = "crossfade"
    out = _cut(story, {
        "scenes": [
            {"scene": "park", "beats": ["park_b1"], "params": {"characters": [{"name": "ben", "at": 0.5}], "light": "night"}},
            {"scene": "park", "id": "park_again", "beats": ["wind"], "transition": {"type": "fade_color"}},
        ],
        "beats": {"park_b1": {"shot": "closeup ana", "emotion": "excited"}},
    })
    first, again = out["scenes"]
    assert first["params"]["characters"] == [{"name": "ana", "at": 0.3}, {"name": "ben", "at": 0.5, "expression": "happy"}]
    assert first["params"]["light"] == "night" and "transition" not in first   # nothing before it in the cut
    assert again["transition"] == {"type": "fade_color"}
    assert first["beats"][0] == {"text": "Ana had a kite.", "id": "park_b1", "shot": "closeup ana", "emotion": "excited"}
    assert again["id"] == "park_again" and [b["id"] for b in again["beats"]] == ["wind"]
    VideoConfig.model_validate(out)


def test_merge_params_names_and_mappings() -> None:
    base = {"props": [{"prop": "tree", "at": 0.2}], "iso": {"place": "indoor", "wide": 1.4}, "characters": [{"name": "ana"}]}
    merged = merge_params(base, {"props": [{"name": "tree", "at": 0.4}, {"prop": "bench"}], "iso": {"wide": 2}, "characters": []})
    assert merged["props"] == [{"prop": "tree", "at": 0.4, "name": "tree"}, {"prop": "bench"}]
    assert merged["iso"] == {"place": "indoor", "wide": 2} and merged["characters"] == []
    cast = [{"name": "ana", "at": 0.3}, "ben", {"name": "cat"}]
    merged = merge_params({"characters": cast}, {"characters": [{"name": "ben", "drop": True}, {"name": "cat", "at": 0.9}, {"name": "zed", "drop": True}]})
    assert merged["characters"] == [{"name": "ana", "at": 0.3}, {"name": "cat", "at": 0.9}]   # ben left out; zed was never there


def test_hook_and_end_card() -> None:
    out = _cut(_story(), {"scenes": ["sky"], "hook": "Will it fly?", "end_card": "Full video on the channel"})
    assert out["overlays"] == [{"type": "watermark", "text": "demo"}, {"type": "hook", "id": "hook", "text": "Will it fly?"}]
    card = out["scenes"][-1]
    assert card == {"id": "cut_end", "type": "end_card", "params": {"title": "Kite day", "lines": ["Full video on the channel"]}, "duration": 3.0}
    out = _cut(_story(), {"scenes": ["sky"], "hook": {"text": "Will it fly?", "seconds": 2},
                          "end_card": {"text": "More soon", "type": "card", "title": "Kites", "seconds": 2, "params": {"style": "plain"}}})
    assert out["overlays"][-1] == {"type": "hook", "id": "hook", "text": "Will it fly?", "seconds": 2}
    assert out["scenes"][-1]["params"] == {"text": "Kites", "subtitle": "More soon", "style": "plain"}
    VideoConfig.model_validate(out)


@pytest.mark.parametrize(("cut", "message"), [
    ({"scenes": ["parc"]}, "cut.scenes[0]: unknown scene 'parc'; did you mean 'park'?"),
    ({"scenes": [{"scene": "park", "beats": ["gust"]}]}, "cut.scenes[0].beats: unknown beat 'gust'"),
    ({"scenes": [{"scene": "title", "beats": ["x"]}]}, "scene 'title' has no beats to choose from"),
    ({"scenes": [{"scene": "park", "beats": {"from": "wind", "to": "park_b1"}}]}, "'to' (park_b1) comes before 'from' (wind)"),
    ({"scenes": ["park", "park"]}, "scene id 'park' comes twice in the cut"),
    ({"scenes": [{"scene": "park", "beats": ["wind"]}], "beats": {"park_b1": {"shot": "wide"}}}, "cut.beats.park_b1: unknown beat 'park_b1'"),
])
def test_cut_problems(cut: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError) as info:
        _cut(_story(), cut)
    assert message in str(info.value)


def test_no_cut_or_a_malformed_one_leaves_the_config() -> None:
    data = _story()
    assert apply_cut(data)[0] is data
    bad = {**data, "cut": {"scenes": []}}
    assert apply_cut(bad)[0] is bad   # the config check reports it


def test_a_variant_cut_shares_the_audio(make_project: Any) -> None:
    root = make_project({**_story(), "variants": {"short": {"cut": {"scenes": [{"scene": "park", "beats": ["wind"]}]}, "shorts": True}}})
    project = Project.load(root, variant="short")
    assert [s.id for s in project.config.scenes] == ["park"] and project.audio_dir == root / "audio"
    assert project.config.shorts_zones == ShortsConfig() and Project.load(root).config.shorts_zones is None
    assert [s.id for s in Project.load(root).config.scenes] == ["title", "park", "sky"]
    bad = make_project({**_story(), "variants": {"short": {"cut": {"scenes": ["nope"]}}}}, folder="bad")
    with pytest.raises(VidgenError) as info:
        Project.load(bad, variant="short")
    assert info.value.problems[0].variant == "short" and info.value.problems[0].location == "cut.scenes[0]"


def test_a_cut_drops_a_scene_overlay() -> None:
    story = _story()
    story["scenes"][1]["overlays"] = {"label": {"type": "lower_third", "at": "park_b1", "title": "Ana"}, "watermark": False}
    out = _cut(story, {"scenes": [{"scene": "park", "beats": ["wind"], "overlays": {"label": {"drop": True}}}]})
    assert out["scenes"][0]["overlays"] == {"watermark": False}   # timed on a beat the cut leaves out
    VideoConfig.model_validate(out)
    kept = _cut(story, {"scenes": [{"scene": "park", "overlays": {"label": {"title": "Ana B."}}}]})
    assert kept["scenes"][0]["overlays"]["label"] == {"type": "lower_third", "at": "park_b1", "title": "Ana B."}


def test_a_change_for_one_scene_of_a_cut_keeps_the_others_renders(make_project: Any) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    def prints(shot: str) -> dict[str, str]:
        cut = {"scenes": ["park", "sky"], "beats": {"sky_b1": {"emotion": shot}}}
        root = make_project({**_story(), "variants": {"short": {"cut": cut}}}, folder=f"p_{shot}")
        project = Project.load(root, variant="short")
        return {sid: scene_fingerprint(project, sid) for sid in ("park", "sky")}

    calm, excited = prints("calm"), prints("excited")
    assert calm["park"] == excited["park"] and calm["sky"] != excited["sky"]


def test_shorts_warnings(make_project: Any) -> None:
    root = make_project({**_story(), "shorts": {"max_seconds": 2}})
    warnings = shorts_warnings(Project.load(root))
    assert warnings[0].startswith("shorts: the format is 1920x1080; a Short is vertical")
    assert "over its 2 s (max_seconds)" in warnings[1]
    assert shorts_warnings(Project.load(make_project(_story(), folder="plain"))) == []


def test_audio_bitrate_reaches_the_encoder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.config import AudioConfig
    from vidgen.render import ffmpeg as ff

    seen: list[list[str]] = []

    def fake_ffmpeg(exe: str, args: list[str], what: str) -> None:
        seen.append(args)
        Path(args[-1]).write_bytes(b"joined")

    monkeypatch.setattr(ff, "run_ffmpeg", fake_ffmpeg)
    ff.join("ffmpeg", [], [], tmp_path / "a.mp4", tmp_path)
    ff.join("ffmpeg", [], [], tmp_path / "b.mp4", tmp_path, audio_bitrate="320k")
    assert [args[args.index("-b:a") + 1] for args in seen] == ["192k", "320k"]
    assert AudioConfig().bitrate == "192k"
    with pytest.raises(ValueError):
        AudioConfig(bitrate="1M")


# ----- lint ----------------------------------------------------------------------------------------


def _still(objects: list[dict[str, Any]], shorts: bool = True) -> StillContext:
    layout = {"width": 1080, "height": 1920, "safe_area": [72, 67, 1008, 1853], "frames": []}
    if shorts:
        layout["shorts"] = [72, 67, 918, 1536]
    return StillContext(layout, {"camera": {}}, objects)


def _text(text: str, box: list[float], overlay: str | None = None) -> dict[str, Any]:
    obj = {"kind": "text", "text": text, "bbox": box, "path": f"t/{text}", "class": "Text", "opacity": 1.0}
    return {**obj, "overlay": overlay} if overlay else obj


def test_shorts_safe_area_text_and_faces() -> None:
    check = RULES["shorts_safe_area"].check
    face = {"kind": "character", "name": "ana", "bbox": [300, 900, 700, 1900], "face": [400, 1000, 600, 1200], "path": "c", "class": "Figure", "opacity": 1}
    objects = [_text("Subscribe", [700, 1600, 1000, 1700]), _text("ok", [200, 400, 600, 500]), face,
               _text("big words", [350, 1050, 750, 1180], overlay="captions")]
    found = [i.message for i in check(_still(objects), ShortsSafeAreaRule())]
    assert any("text 'Subscribe' reaches the right and bottom of the frame" in m for m in found)
    assert any("overlay 'captions' covers 65% of the face of character 'ana'" in m for m in found)
    assert not any("'ok'" in m for m in found)
    low = {**face, "face": [400, 1600, 600, 1800]}
    assert any("the face of character 'ana' is 100% under" in i.message for i in check(_still([low]), ShortsSafeAreaRule()))
    assert list(check(_still(objects, shorts=False), ShortsSafeAreaRule())) == []
    assert list(check(_still([{**low, "hidden": True}]), ShortsSafeAreaRule())) == []


def test_shorts_face_check_uses_the_reach_of_the_line() -> None:
    check = RULES["shorts_safe_area"].check
    face = {"kind": "character", "name": "ana", "bbox": [300, 900, 700, 1900], "face": [400, 1000, 600, 1200], "path": "c", "class": "Figure", "opacity": 1}
    short = _text("it", [700, 1050, 800, 1180], overlay="captions")   # this caption misses the face...
    assert list(check(_still([face, short]), ShortsSafeAreaRule())) == []
    wide = {**short, "reach": [150, 1050, 850, 1180]}   # ...a longer one of the same line covers it
    found = [i.message for i in check(_still([face, wide]), ShortsSafeAreaRule())]
    assert any("overlay 'captions' covers 65% of the face of character 'ana' (while this line is shown)" in m for m in found)
    chin = {**short, "reach": [150, 1170, 850, 1300]}   # 15 % of the face (its chin): over min_cover 0.1
    assert any("covers 15% of the face" in i.message for i in check(_still([face, chin]), ShortsSafeAreaRule()))
    assert list(check(_still([face, chin]), ShortsSafeAreaRule(min_cover=0.2))) == []


def test_an_overlay_that_keeps_off_faces_counts_its_texts_and_panels_only() -> None:
    check = RULES["shorts_safe_area"].check
    face = {"kind": "character", "name": "ana", "bbox": [300, 900, 700, 1900], "face": [400, 1000, 600, 1200], "path": "c", "class": "Figure", "opacity": 1}
    lines = {"kind": "group", "bbox": [0, 0, 1080, 1920], "overlay": "implant", "fill": {"opacity": 0.0}, "path": "overlay:implant/g"}
    alert = _text("ALERT", [380, 1100, 700, 1180], overlay="implant")
    still = _still([face, lines])
    still.frame["overlays"] = [{"id": "implant", "type": "hud", "settled": True, "faces": True}]
    assert list(check(still, ShortsSafeAreaRule())) == []   # its frame's lines run over the whole picture
    still = _still([face, lines, alert])
    still.frame["overlays"] = [{"id": "implant", "type": "hud", "settled": True, "faces": True}]
    found = [i.message for i in check(still, ShortsSafeAreaRule())]
    assert len(found) == 1 and "overlay 'implant' covers 40% of the face of character 'ana'" in found[0]


@pytest.mark.render
def test_a_hud_in_a_short_keeps_its_meters_above_the_captions(make_project: Any, tmp_path: Path) -> None:
    from manim import tempconfig
    from test_overlays import bullets, project, render

    from vidgen.overlays import shorts_area
    from vidgen.render.worker import frame_size
    from vidgen.scenes.hud import SHORTS_CAPTION_BAND

    hud = {"type": "hud", "at": 0.0, "duration": 1.0, "heart": {"bpm": 80}, "scan": {"level": 0.5}, "compact": True}
    proj = project(make_project, [bullets("s", beats=1, overlays={"implant": hud})], [],
                   format={"width": 90, "height": 160, "fps": 5}, shorts=True)
    overlay = render(proj, "s", tmp_path, size=(90, 160)).overlay_layer.overlays[0]
    fw, fh = frame_size(90, 160)
    with tempconfig({"pixel_width": 90, "pixel_height": 160, "frame_width": fw, "frame_height": fh}):
        area = shorts_area(proj)
    for box in (overlay._heart_box, overlay._scan_box):
        assert box[1] == pytest.approx(area.y0 + SHORTS_CAPTION_BAND * area.height)   # above the captions
        assert area.x0 - 1e-6 <= box[0] and box[2] <= area.x1 + 1e-6   # compact: still out of the app's parts


def test_karaoke_in_a_short_shows_a_phrase_on_one_line() -> None:
    from vidgen.cues import split_cues
    from vidgen.scenes.captions import SHORTS_KARAOKE, STYLE_DEFAULTS, Captions

    def captions(shorts: ShortsConfig | None, **options: Any) -> Captions:
        context = SimpleNamespace(project=SimpleNamespace(config=SimpleNamespace(shorts_zones=shorts)))
        return Captions(Captions.Options(style="karaoke", **options), None, context, id="captions")  # type: ignore[arg-type]

    short = captions(ShortsConfig())
    assert [short._setting(k) for k in ("size", "max_lines", "max_words", "bold")] == ["body", 1, 5, True]
    assert [captions(None)._setting(k) for k in ("size", "max_lines", "max_words")] == ["title", 2, 3]
    assert captions(ShortsConfig(), max_words=2, size="title")._setting("max_words") == 2
    assert SHORTS_KARAOKE["max_words"] > STYLE_DEFAULTS["karaoke"]["max_words"]
    # a line of about 20 characters (body text across the Shorts area) cuts into phrases of 3-5 words
    text = "Then the AI they had built to read the motion data sparked to life, projecting a humanoid form in the centre of the lab."
    cues = split_cues(text, 22, max_lines=1, max_words=5)
    sizes = [len(lines[0].split()) for lines in cues]
    assert all(len(lines) == 1 for lines in cues) and max(sizes) <= 5 and sum(sizes) / len(sizes) >= 3


def test_caption_reach_covers_every_caption_of_a_line() -> None:
    from manim import Rectangle

    from vidgen.scenes.captions import _mark_reach

    a = Rectangle(width=1, height=0.5).move_to([-1, -2, 0])
    b = Rectangle(width=3, height=0.5).move_to([0, -2, 0])
    c = Rectangle(width=0.5, height=0.5).move_to([2, -2, 0])
    _mark_reach([({0}, a), ({0}, b), ({1}, c)])
    assert a.overlay_reach == b.overlay_reach == pytest.approx((-1.5, -2.25, 1.5, -1.75))
    assert c.overlay_reach == pytest.approx((1.75, -2.25, 2.25, -1.75))


def test_shorts_length() -> None:
    check = RULES["shorts_length"].check
    ctx = SceneContext("end", {"fps": 30, "beats": []}, Path("."))
    assert list(check(ctx, ShortsLengthRule())) == []
    ctx.video_seconds, ctx.shorts_max = 61.5, 60.0
    issue = next(iter(check(ctx, ShortsLengthRule())))
    assert issue.message.startswith("the Short is 61.5 s long, over its 60 s") and RULES["shorts_length"].default == "error"


# ----- rendering -----------------------------------------------------------------------------------


@pytest.mark.render
def test_a_short_renders_with_hook_captions_and_end_card(make_project: Any) -> None:
    from vidgen.lint import lint_project

    data = {**_story(), "preview": {"width": 96, "height": 54, "fps": 5}, "variants": {"short": {
        "format": {"width": 1080, "height": 1920}, "preview": {"width": 90, "height": 160, "fps": 5},
        "shorts": {"max_seconds": 2}, "overlays": [{"type": "captions", "style": "karaoke"}],
        "cut": {"scenes": [{"scene": "park", "beats": ["park_b1"]}],
                "beats": {"park_b1": {"actions": [{"zoom": "ana", "scale": 2, "at": 0, "cut": True, "hold": True}]}},
                "hook": "Will the kite fly today?", "end_card": {"text": "Full video on the channel", "seconds": 1, "type": "card"}},
    }}}
    project = Project.load(make_project(data), variant="short")
    result = lint_project(project, preview=True)
    layout = json.loads((project.render_dir(True) / "layout" / "park.json").read_text(encoding="utf-8"))
    assert layout["shorts"] == [0.0, 0.0, 76.5, 128.0]   # the frame without its bottom 20 % and right 15 %
    assert [f["k"] for f in layout["frames"]] == [1, 2, 3]   # a Short is linted mid-beat too
    assert RULES["shorts_safe_area"].mid_beat and not RULES["safe_area"].mid_beat
    end = layout["frames"][-1]
    assert {"hook", "captions"} <= {o["id"] for o in end["overlays"]}
    assert end["camera"]["zoom"] == pytest.approx(2.0, abs=0.01)   # held after the zoom
    hook = [o for o in layout["frames"][0]["objects"] if o.get("overlay") == "hook" and o["kind"] == "text"]
    assert [o["text"] for o in hook] == ["Will the kite\nfly today?"]   # a little smaller: 2 lines, not 3
    caption = next(o for o in end["objects"] if o.get("overlay") == "captions")
    assert caption["reach"][3] <= 128.0 * 0.97 + 0.5   # the line's reach, above the app's area with a margin
    assert [s.id for s in project.config.scenes] == ["park", "cut_end"]
    assert "shorts_length" in {f.rule for f in result.findings}   # a narrated beat and a 1 s card: over 2 s
    card = json.loads((project.render_dir(True) / "layout" / "cut_end.json").read_text(encoding="utf-8"))
    assert card["safe_area"][2] <= 76.5   # the scene's safe area leaves the app's buttons out
    assert not [f for f in result.findings if f.scene == "cut_end" and f.rule in ("shorts_safe_area", "safe_area")]   # the card's words too


@pytest.mark.render
@pytest.mark.parametrize("cut", [True, False])
def test_a_cut_zoom_at_the_start_opens_the_scene_framed(make_project: Any, cut: bool) -> None:
    from vidgen.storyboard import make_storyboard

    data = {**_story(), "preview": {"width": 96, "height": 54, "fps": 10}}
    data["scenes"] = [data["scenes"][1]]
    data["scenes"][0]["beats"][0]["actions"] = [{"zoom": "ana", "scale": 2, "at": 0, "cut": cut, "hold": True}]
    project = Project.load(make_project(data))
    make_storyboard(project, per_beat=4)
    layout = json.loads((project.render_dir(True) / "layout" / "park.json").read_text(encoding="utf-8"))
    first = layout["frames"][0]
    assert first["beat"] == "park_b1" and first["time"] < 1.0   # while the set fades in
    assert first["camera"]["zoom"] == pytest.approx(2.0 if cut else 1.0, abs=0.01)   # without cut: wide first
