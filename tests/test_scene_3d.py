"""The ``3d`` scene type (Steps 298–299, DESIGN.md §114): params, the scene description, the page's
file serving and the missing-dependency errors without a browser; a few tiny renders through
Playwright's Chromium (skipped when it is missing). Shapes, groups and camera moves: test_scene_3d_camera.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

from vidgen.config import FormatConfig, ThemeConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme
from vidgen.three_d import browser
from vidgen.three_d.description import BeatSpan, description_key, hex6, scene_description
from vidgen.three_d.spec import Scene3DParams

THEME = Theme.for_format(ThemeConfig(), FormatConfig())


def params(**raw: Any) -> Scene3DParams:
    return Scene3DParams.model_validate(raw)


def describe(p: Scene3DParams, width: int = 160, height: int = 90, fps: int = 10, frames: int = 4) -> dict[str, Any]:
    return scene_description(p, THEME, width=width, height=height, fps=fps, frames=frames, beats=[BeatSpan("b1", 0.0, 0.3)])


def errors_of(**raw: Any) -> str:
    from vidgen.scenes.scene_3d import Scene3D

    with pytest.raises(VidgenError) as exc:
        Scene3D.parse_params(raw, "s", THEME)
    return str(exc.value)


# ----- params ---------------------------------------------------------------------------------


def test_registered_with_its_params() -> None:
    import vidgen.scenes  # noqa: F401 - registers the built-ins
    from vidgen import registry

    entry = registry.get("3d")
    assert entry.cls.__name__ == "Scene3D"
    assert issubclass(entry.cls.params_model(), Scene3DParams)


def test_unknown_shape_and_key_suggest_the_right_name() -> None:
    assert "did you mean 'box'?" in errors_of(objects=[{"id": "a", "shape": "boxx"}])
    assert "did you mean 'sphere'?" in errors_of(objects=[{"id": "a", "shape": "sphre"}])
    assert "posiiton" in (text := errors_of(objects=[{"id": "a", "posiiton": [0, 0, 0]}])) and "position" in text
    assert "came" in (text := errors_of(came={"fov": 30})) and "camera" in text


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"objects": [{"id": "a"}, {"id": "a"}]}, "used twice"),
        ({"objects": [{"id": "camera"}]}, "reserved"),
        ({"objects": [{"id": "1x"}]}, "must start with a letter"),
        ({"objects": [{"id": "a", "size": [1, 0, 1]}]}, "positive"),
        ({"camera": {"position": [1, 2, 3], "look_at": [1, 2, 3]}}, "cannot look at"),
        ({"camera": {"fov": 5}}, "greater than or equal to 10"),
        ({"light": {"sun_from": [0, 0, 0]}}, "no direction"),
        ({"background": "#12"}, "invalid hex color"),
    ],
)
def test_bad_params_are_named(raw: dict[str, Any], message: str) -> None:
    assert message in errors_of(**raw)


# ----- the scene description ------------------------------------------------------------------


def test_description_holds_objects_camera_lights_and_timeline() -> None:
    d = describe(params(objects=[{"id": "crate", "color": "#ABC", "position": [1, 0.5, 0], "spin": [0, 90, 0]}], background="#102030"))
    assert d["version"] == 1 and d["draw_mode"] == "normal"
    assert (d["width"], d["height"], d["fps"], d["frames"], d["duration"]) == (160, 90, 10, 4, 0.4)
    assert d["background"] == "#102030"
    assert d["objects"] == [{"id": "crate", "shape": "box", "parent": None, "size": [1.0, 1.0, 1.0], "color": "#aabbcc", "position": [1.0, 0.5, 0.0], "rotation": [0.0, 0.0, 0.0]}]
    assert [light["id"] for light in d["lights"]] == ["ambient", "sun"]
    sun = d["lights"][1]["position"]
    assert np.linalg.norm(sun) == pytest.approx(20.0, abs=1e-4) and sun[1] > 0
    assert d["camera"]["look_at"] == [0.0, 0.0, 0.0] and d["camera"]["fov"] == 40.0
    assert d["timeline"]["beats"] == [{"id": "b1", "start": 0.0, "end": 0.3}]
    (track,) = d["timeline"]["tracks"]
    assert track["target"] == "crate" and track["property"] == "rotation"
    assert track["keys"] == [{"t": 0.0, "value": [0.0, 0.0, 0.0]}, {"t": 0.4, "value": [0.0, 36.0, 0.0]}]


def test_description_defaults_and_theme_colours() -> None:
    d = describe(params(objects=[{"id": "a"}]))
    assert d["background"] == hex6(THEME.background)
    assert d["objects"][0]["color"] == hex6(THEME.color("accent"))
    assert d["timeline"]["tracks"] == []   # nothing spins
    with pytest.raises(ValueError, match="unknown draw mode 'sketch'"):   # depth, outline, mask: test_scene_3d_passes.py
        scene_description(params(), THEME, width=16, height=9, fps=10, frames=1, beats=[], draw_mode="sketch")


def test_hex6() -> None:
    assert hex6("#AbC") == "#aabbcc" and hex6("#11223344") == "#112233" and hex6("#a1b2c3") == "#a1b2c3"


def test_description_key_follows_description_and_engine() -> None:
    a = describe(params(objects=[{"id": "a"}]))
    b = describe(params(objects=[{"id": "a", "color": "#ff0000"}]))
    assert description_key(a, "e1") == description_key(dict(a), "e1")
    assert description_key(a, "e1") != description_key(b, "e1")
    assert description_key(a, "e1") != description_key(a, "e2")


# ----- the page and missing dependencies --------------------------------------------------------


class FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = type("Request", (), {"url": url})()
        self.answer: tuple[str, Any] | None = None

    def abort(self) -> None:
        self.answer = ("abort", None)

    def fulfill(self, **kwargs: Any) -> None:
        self.answer = ("fulfill", kwargs)


def test_page_serves_only_its_own_files() -> None:
    for url, kind in [
        (browser.PAGE_ORIGIN + "vidgen3d.js", "fulfill"),
        (browser.PAGE_ORIGIN + "three.module.js?x=1", "fulfill"),
        (browser.PAGE_ORIGIN + "inter-bold.ttf", "fulfill"),
        (browser.PAGE_ORIGIN + "LICENSE", "abort"),
        (browser.PAGE_ORIGIN + "../spec.py", "abort"),
        ("https://cdn.jsdelivr.net/npm/three/build/three.module.js", "abort"),
    ]:
        route = FakeRoute(url)
        browser._serve(route)
        assert route.answer is not None and route.answer[0] == kind, url
    route = FakeRoute(browser.PAGE_ORIGIN + "page.html")
    browser._serve(route)
    assert route.answer[1]["headers"]["Content-Type"].startswith("text/html")


def test_vendored_three_is_pinned_with_its_licence() -> None:
    assert (browser.PAGE_DIR / "LICENSE").read_text(encoding="utf-8").startswith("The MIT License")
    for name in browser.PAGE_FILES:
        assert (browser.PAGE_DIR / name).is_file(), name
    assert "import * as THREE from './three.module.js'" in (browser.PAGE_DIR / "vidgen3d.js").read_text(encoding="utf-8")
    assert len(browser.page_digest()) == 64 and browser.page_digest() in browser.engine_id()


def test_three_files_count_in_the_render_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.render import fingerprint

    fingerprint.vidgen_source_digest.cache_clear()
    before = fingerprint.vidgen_source_digest()
    real = fingerprint._contents_digest
    seen: list[str] = []
    monkeypatch.setattr(fingerprint, "_contents_digest", lambda paths, root: seen.extend(p.name for p in paths) or real([], root))
    fingerprint.vidgen_source_digest.cache_clear()
    fingerprint.vidgen_source_digest()
    fingerprint.vidgen_source_digest.cache_clear()
    assert "vidgen3d.js" in seen and "three.core.js" in seen and before


def test_missing_playwright_names_the_install_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    with pytest.raises(VidgenError) as exc:
        browser.PageRenderer(describe(params())).__enter__()
    text = str(exc.value)
    assert 'pip install "schu-video-generator[3d]"' in text and "python -m playwright install chromium" in text
    assert "py -m playwright install chromium" in text   # Windows wording


def test_missing_chromium_names_the_install_command() -> None:
    error = browser._browser_error(Exception("BrowserType.launch: Executable doesn't exist at /x/chrome\nLooks like Playwright was just installed"))
    assert str(error) == browser.BROWSER_HINT and "playwright install chromium" in str(error)
    assert "cannot start Chromium" in str(browser._browser_error(Exception("boom")))


def test_page_that_does_not_load_is_a_message_and_closes_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    class Error(Exception):
        pass

    closed: list[str] = []

    class Page:
        def on(self, *_: Any) -> None: ...
        def goto(self, *_: Any, **__: Any) -> None:
            raise Error("Timeout 60000ms exceeded.\n=== logs ===")

    class Context:
        def route(self, *_: Any) -> None: ...
        def new_page(self) -> Page:
            return Page()

    class Browser:
        def new_context(self, **_: Any) -> Context:
            return Context()
        def close(self) -> None:
            closed.append("browser")

    class Playwright:
        chromium = type("Chromium", (), {"launch": lambda self, **_: Browser()})()
        def start(self) -> "Playwright":
            return self
        def stop(self) -> None:
            closed.append("playwright")

    fake = type("SyncApi", (), {"Error": Error, "sync_playwright": staticmethod(lambda: Playwright())})
    monkeypatch.setattr(browser, "_sync_api", lambda: fake)
    with pytest.raises(VidgenError, match=r"^3D page did not load: Timeout 60000ms exceeded\.$"):
        browser.PageRenderer(describe(params())).__enter__()
    assert closed == ["browser", "playwright"]


def test_a_clip_open_elsewhere_is_a_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows refuses to replace a file another program has open (a video player)."""
    class Page:
        def __init__(self, description: dict[str, Any]) -> None: ...
        def __enter__(self) -> "Page":
            return self
        def __exit__(self, *_: Any) -> None: ...
        def frame(self, n: int) -> np.ndarray:
            return np.zeros((16, 16, 3), dtype=np.uint8)

    def refuse(*_: Any) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(browser, "PageRenderer", Page)
    monkeypatch.setattr(browser.os, "replace", refuse)
    with pytest.raises(VidgenError, match="cannot replace .*close the program"):
        browser.write_clip(describe(params(), width=16, height=16, frames=2), tmp_path / "s.mkv")
    assert list(tmp_path.iterdir()) == []   # no partial file left


# ----- renders (Chromium) -----------------------------------------------------------------------


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    try:
        with browser.PageRenderer(describe(params(), width=16, height=16, frames=1)) as page:
            page.frame(0)
    except VidgenError as exc:
        pytest.skip(f"Chromium for Playwright is not available: {exc}")


@pytest.mark.render
def test_page_frames_are_deterministic_and_follow_time() -> None:
    _chromium_or_skip()
    d = describe(params(objects=[{"id": "crate", "color": "#e04040", "spin": [0, 60, 0]}], background="#000000"), frames=6)
    with browser.PageRenderer(d) as page:
        first = [page.frame(n) for n in (0, 3)]
    with browser.PageRenderer(d) as page:
        again = [page.frame(n) for n in (0, 3)]
    assert first[0].shape == (90, 160, 3)
    assert np.array_equal(first[0], again[0]) and np.array_equal(first[1], again[1])   # same description, same pixels
    assert not np.array_equal(first[0], first[1])   # the box turned
    centre = first[0][45, 80]
    assert centre[0] > 100 and centre[0] > centre[2] and first[0][2, 2].tolist() == [0, 0, 0]


@pytest.mark.render
def test_page_reports_a_bad_description() -> None:
    _chromium_or_skip()
    d = describe(params())
    d["objects"] = [{"id": "x", "shape": "teapot", "size": [1, 1, 1], "color": "#ffffff", "position": [0, 0, 0], "rotation": [0, 0, 0]}]
    with pytest.raises(VidgenError, match="unknown shape 'teapot'"):
        with browser.PageRenderer(d):
            pass


def _frames(path: Path) -> list[np.ndarray]:
    with av.open(str(path)) as container:
        return [f.to_ndarray(format="rgb24").astype(int) for f in container.decode(video=0)]


@pytest.mark.render
@pytest.mark.slow
def test_render_landscape_and_portrait_with_captions_and_cache(make_project) -> None:
    _chromium_or_skip()
    from vidgen.render.pipeline import render_project

    root = make_project({
        "title": "3D",
        "format": {"width": 160, "height": 90, "fps": 5},
        "preview": {"width": 160, "height": 90, "fps": 5},
        "variants": {"vertical": {"format": {"width": 90, "height": 160, "fps": 5}, "preview": {"width": 90, "height": 160, "fps": 5},
                                  "overlays": [{"type": "captions"}]}},
        "scenes": [{
            "id": "cube", "type": "3d",
            "params": {"title": "Box", "background": "#000000",
                       "objects": [{"id": "crate", "color": "#e04040", "size": [1.6, 1.6, 1.6], "spin": [0, 30, 0]}]},
            "beats": [{"id": "b1", "text": "A box turns slowly in the middle."}],
        }],
    })
    result = render_project(Project.load(root), preview=True)
    clip = root / "build" / "preview" / "three_d" / "cube.mkv"
    record = clip.with_suffix(".json")
    assert clip.is_file() and record.is_file()
    shown, drawn = _frames(root / "build" / "preview" / "scenes" / "cube.mp4"), _frames(clip)
    assert len(drawn) >= len(shown) == round(result.duration * 5)
    k = len(shown) // 2   # frame k of the scene is frame k of the 3D clip (away from the title)
    assert np.abs(shown[k][40:] - drawn[k][40:]).mean() < 6
    assert shown[k][45, 80, 0] > 100   # the box in the middle
    stamp = os.stat(clip).st_mtime_ns
    render_project(Project.load(root), preview=True, force=True)
    assert os.stat(clip).st_mtime_ns == stamp   # the 3D frames were reused

    tall = render_project(Project.load(root, variant="vertical"), preview=True)
    frames = _frames(tall.output)
    assert frames[0].shape == (160, 90, 3)
    k = len(frames) // 2
    view = _frames(root / "build" / "preview_vertical" / "three_d" / "cube.mkv")[k]
    assert frames[k][80, 45, 0] > 100   # the box in the middle of the tall frame
    assert np.abs(frames[k][110:140] - view[110:140]).mean() > 10   # the caption is drawn over the 3D picture
