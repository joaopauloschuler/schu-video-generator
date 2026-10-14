"""The cartoon host beside any scene (``host:``, DESIGN.md §71): config and merging, the column /
band it takes from the scene's region per format, who speaks, lint, and one tiny render."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_cartoon_stage import render_with_layout
from test_lint import check, shape, text
from vidgen import extensions, registry
from vidgen.cartoon.host import HOST_SIZES, host_continues, host_layout, host_speaks, scene_host, video_host
from vidgen.cli import check_project
from vidgen.config import HostConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project

CHARACTERS = [{"name": "dot"}, {"name": "kit", "voice": "guest"}]
VOICES = {"guest": {"voice_id": "abc"}}


def bullets(scene_id: str = "steps", **extra: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "bullets", "params": {"heading": "How", "items": ["One thing", "Another thing"]},
            "beats": [{"text": "First beat here."}, {"text": "Second beat here.", "voice": "guest"}], **extra}


def config(scenes: list[dict[str, Any]] | None = None, **top: Any) -> dict[str, Any]:
    return {"title": "Host", "characters": CHARACTERS, "voices": VOICES, "scenes": scenes or [bullets()], **top}


# ----- config and merging ------------------------------------------------------------------------


def test_a_name_is_a_host_and_scenes_change_it() -> None:
    cfg = parse_config(config([bullets("a"), bullets("b", host=False), bullets("c", host={"side": "left", "expression": "happy"}),
                               bullets("d", host="kit"), bullets("e", host=True)], host="dot"))
    assert video_host(cfg) == HostConfig(character="dot")
    hosts = [scene_host(cfg, s) for s in cfg.scenes]
    assert hosts[0] == HostConfig(character="dot") and hosts[1] is None and hosts[4] == hosts[0]
    assert hosts[2] == HostConfig(character="dot", side="left", expression="happy")
    assert hosts[3] == HostConfig(character="kit")


def test_host_problems() -> None:
    with pytest.raises(VidgenError) as exc:
        parse_config(config([bullets("a", host={"side": "left"}), bullets("b", host=True), bullets("c", host="nobody")]))
    lines = str(exc.value)
    assert "scenes[0].host: the video has no host:, so this scene's host needs a character" in lines
    assert "scenes[1].host: true, but the video has no host:" in lines
    assert "scenes[2].host.character: unknown character 'nobody'" in lines
    with pytest.raises(VidgenError, match=r"host.pose: character 'dot': unknown pose 'pointng'; did you mean 'pointing'"):
        parse_config(config(host={"character": "dot", "pose": "pointng"}))
    with pytest.raises(VidgenError, match=r"host.character: unknown character 'dott'; did you mean 'dot'"):
        parse_config(config(host="dott"))


def test_validate_rejects_a_host_on_a_stage_and_warns_about_a_silent_host(make_project) -> None:
    stage = {"id": "park", "type": "stage", "host": "dot", "params": {"characters": ["kit"]}, "beats": [{"text": "Hi."}]}
    root = make_project(config([bullets(), stage], host={"character": "dot", "floor_color": "nope"}))
    lines = check_project(Project.load(root))
    assert any(line.startswith("scenes[1].host: type 'stage' draws no host") for line in lines)
    assert any(line.startswith("host.floor_color: unknown theme color 'nope'") for line in lines), lines
    from vidgen.cli import validate_warnings

    root = make_project(config(host={"character": "dot", "speaks": "own"}), folder="silent")
    assert any("speaks: own, but character 'dot' has no voice" in w for w in validate_warnings(Project.load(root)))


def test_the_host_stays_in_the_fade_out_only_when_the_next_scene_shows_it_unchanged() -> None:
    cfg = parse_config(config([bullets("a"), bullets("b"), bullets("c", host={"side": "left"}), bullets("d")], host="dot"))
    takes = lambda kind: kind != "stage"   # noqa: E731
    assert [host_continues(cfg, i, takes) for i in range(4)] == [True, False, False, False]


# ----- who speaks ----------------------------------------------------------------------------------


def test_who_moves_the_hosts_mouth() -> None:
    cfg = parse_config(config(host="dot", characters=[{"name": "dot"}, {"name": "kit", "voice": "guest"}, {"name": "ann", "voice": "default"}]))
    narrator = HostConfig(character="dot")
    assert not host_speaks(cfg, narrator, "default")   # ann owns the narrator's voice
    assert not host_speaks(cfg, narrator, "guest")     # kit's
    cfg = parse_config(config(host="dot"))
    assert host_speaks(cfg, narrator, "default") and not host_speaks(cfg, narrator, "guest")
    assert not host_speaks(cfg, HostConfig(character="dot", speaks="own"), "default")   # no voice of its own
    assert host_speaks(cfg, HostConfig(character="kit", speaks="own"), "guest")
    assert not host_speaks(cfg, HostConfig(character="kit", speaks="own"), "default")


# ----- placement per format ------------------------------------------------------------------------


def frame(width: float, height: float) -> tuple[float, float, float, float]:
    return (-width / 2 + 0.6, -height / 2 + 0.5, width / 2 - 0.6, height / 2 - 0.5)   # the default safe area


@pytest.mark.parametrize(("size", "below", "orientation"), [((14.222, 8.0), False, "landscape"), ((8.0, 14.222), True, "portrait"), ((8.0, 8.0), False, "square")])
def test_layout_per_format(size: tuple[float, float], below: bool, orientation: str) -> None:
    area = frame(*size)
    layout = host_layout(area, *size, HostConfig(character="dot"), 0.5)
    x0, y0, x1, y1 = layout.reserve
    assert layout.below is below and layout.facing == "left"   # right side: looks at the content
    assert layout.height == pytest.approx(HOST_SIZES[orientation] * 8)
    assert layout.feet[1] == pytest.approx(area[1]) and x1 == pytest.approx(area[2])
    if below:   # a band across the bottom; the figure at its right end
        assert (x0, y0, y1) == pytest.approx((area[0], area[1], area[1] + layout.height))
        assert layout.figure[2] <= area[2] + 1e-9 and layout.figure[0] > 0
    else:       # a full-height column on the right
        assert (y0, y1) == pytest.approx((area[1], area[3]))
        assert x1 - x0 == pytest.approx(0.5 * layout.height * 1.5)   # the figure plus the floor's overhang
    fx0, fy0, fx1, fy1 = layout.figure
    assert x0 - 1e-9 <= fx0 and fx1 <= x1 + 1e-9 and fy1 <= y1 + 1e-9


def test_layout_options() -> None:
    area = frame(14.222, 8.0)
    left = host_layout(area, 14.222, 8.0, HostConfig(character="dot", side="left", floor=False, size=0.3, facing="front"), 0.5)
    assert left.reserve[0] == pytest.approx(area[0]) and left.reserve[2] - left.reserve[0] == pytest.approx(0.5 * 0.3 * 8)
    assert left.floor is None and left.facing == "front" and left.height == pytest.approx(2.4)
    below = host_layout(area, 14.222, 8.0, HostConfig(character="dot", place="below", side="left"), 0.5)
    assert below.below and below.facing == "right" and below.height == pytest.approx(0.4 * 7.0)   # capped to the band's share
    wide = host_layout(area, 14.222, 8.0, HostConfig(character="dot", size=0.9), 1.2)   # too wide for a column: made smaller
    assert wide.reserve[2] - wide.reserve[0] == pytest.approx(0.4 * (area[2] - area[0]))


# ----- the region split in a scene (built, not rendered) ----------------------------------------------


def built_scene(root: Path, pixels: tuple[int, int], scene_id: str = "steps") -> tuple[Any, Any]:
    """The scene built (not rendered) at that pixel size, and its safe area (read while Manim's
    config has that frame)."""
    from manim import tempconfig

    from vidgen.render.worker import frame_size

    fw, fh = frame_size(*pixels)
    project = Project.load(root)
    with tempconfig({"pixel_width": pixels[0], "pixel_height": pixels[1], "frame_width": fw, "frame_height": fh, "frame_rate": 5,
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        theme = extensions.activate(project)
        spec = project.scene(scene_id)
        scene = registry.get(spec.type).cls(spec, project, theme)
        return scene, scene.safe_area


@pytest.mark.parametrize("pixels", [(160, 90), (90, 160), (90, 90)], ids=["16:9", "9:16", "1:1"])
def test_the_scene_region_shrinks_clear_of_the_host(make_project, pixels: tuple[int, int]) -> None:
    from vidgen.overlays import mobject_region

    from vidgen.render.worker import frame_size

    root = make_project(config(host="dot", overlays=[{"type": "captions"}]))
    scene, area = built_scene(root, pixels)
    host = mobject_region(scene.host)
    assert area.x1 <= host.x0 or area.y0 >= host.y1   # the content keeps to one side of the host (or above it)
    assert (area.y0 >= host.y1) is (pixels[1] > pixels[0])   # 9:16: above it
    fw, fh = frame_size(*pixels)
    assert -fw / 2 < host.x0 and host.x1 < fw / 2 and -fh / 2 < host.y0 and host.y1 < fh / 2
    captions = scene._reserved[0]   # the caption band, reserved first: the host stands above it
    assert host.y0 >= captions.y1


def test_no_host_on_a_stage_or_with_host_false(make_project) -> None:
    stage = {"id": "park", "type": "stage", "params": {"characters": ["kit"]}, "beats": [{"text": "Hi."}]}
    root = make_project(config([bullets("steps", host=False), stage], host="dot"))
    assert built_scene(root, (160, 90))[0].host is None
    assert built_scene(root, (160, 90), "park")[0].host is None


# ----- lint ------------------------------------------------------------------------------------------


def host_object(bbox: list[float]) -> dict[str, Any]:
    return {**shape("h", bbox, kind="host", order=50), "name": "dot", "class": "HostFigure"}


def test_host_overlap() -> None:
    host = host_object([1500, 400, 1800, 1000])
    clear = [text("t1", [100, 100, 1400, 200]), shape("bg", [0, 0, 1920, 1080], order=0)]   # a backdrop holding the host
    assert check("host_overlap", [host, *clear]) == []
    issues = check("host_overlap", [host, text("t2", [1300, 500, 1600, 560], "Long line")])
    assert len(issues) == 1 and "host 'dot' overlaps text 'Long line'" in issues[0].message
    caption = {**text("c", [1400, 950, 1900, 1020], "A caption"), "overlay": "captions"}
    issues = check("host_overlap", [host, caption])
    assert len(issues) == 1 and "overlay 'captions'" in issues[0].message
    assert check("host_overlap", [host, text("t3", [1300, 500, 1502, 560])]) == []   # under 2 % of the smaller box
    covering = check("covered_text", [text("t2", [1300, 500, 1600, 560]), host])   # host_overlap's finding, not this rule's
    assert covering == []


# ----- one tiny render -----------------------------------------------------------------------------


@pytest.mark.render
def test_a_bullets_scene_with_a_host_renders(make_project, tmp_path: Path) -> None:
    from vidgen.introspect import LayoutRecorder

    root = make_project(config([bullets(), bullets("after")], host="dot"))
    recorder = LayoutRecorder()
    scene, objects = render_with_layout(Project.load(root), "steps", tmp_path / "media", recorder)
    hosts = [o for o in objects if o["kind"] == "host"]
    assert len(hosts) == 1 and hosts[0]["name"] == "dot" and hosts[0]["facing"] == "left" and hosts[0]["side"] == "right"
    assert scene.host in scene.mobjects and len(scene.mobjects) == 1   # the next scene shows it too: kept in the fade-out
    assert scene.host.character.lip_sync_track is None   # spoke beat one (the narrator's), silent in kit's, stopped
    assert [i.message for i in check("host_overlap", objects)] == []
