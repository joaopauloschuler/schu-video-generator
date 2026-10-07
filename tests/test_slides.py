"""`vidgen slides`: key-frame selection (shared with the PDF deck), the HTML page, CLI / JSON, a
real render and a headless-browser smoke test.

Most tests fake the stills (PNG + index + timings) and stub the rendering, so they run without
Manim; one render test uses 96x54 @ 5 fps previews.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from test_json_output import documented, run_json
from test_render import make_tone, write_project
from vidgen import storyboard
from vidgen.cli import main
from vidgen.deck import deck_frames, stills_alike
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import pipeline
from vidgen.render.worker import scene_frames_dir, scene_timings_path
from vidgen.slides import encode_still, make_slides, slides_path

SIZE = (96, 54)

# ----- a project with fake stills -----------------------------------------------------------------


def scenes_config() -> list[dict[str, Any]]:
    return [
        {"id": "intro", "type": "title", "params": {"title": "Hello deck"}, "beats": [{"text": "Welcome to the deck."}]},
        {"id": "points", "type": "bullets", "chapter": {"title": "Main part", "number": 1},
         "params": {"title": "Three points", "items": ["A", "B", "C"]},
         "beats": [{"text": "First point."}, {"text": "Second point."}, {"text": "Nothing new <here> & there."}]},
        {"id": "pause", "type": "text_card", "params": {"text": "Breathe"}, "duration": 1.5},
        {"id": "end", "type": "end_card", "chapter": "Wrap-up", "params": {"title": "Bye"}, "beats": [{"text": "Thanks for watching."}]},
    ]


#: Picture colour of each still (same colour = alike); per scene, per still.
COLORS = {"intro": [(200, 30, 30)], "points": [(30, 200, 30), (30, 30, 200), (30, 30, 200)], "pause": [(90, 90, 90)], "end": [(250, 250, 0)]}


def fake_stills(project: Project, per_beat: int = 1, preview: bool = True) -> None:
    """Stills, frames index and timings as a render with ``per_beat`` stills per beat writes them."""
    fmt = project.render_format(preview)
    for spec in project.config.scenes:
        folder = scene_frames_dir(project, preview, spec.id)
        folder.mkdir(parents=True, exist_ok=True)
        frames, beats, t = [], [], 0.0
        colors = COLORS[spec.id]
        if spec.beats:
            for j, beat in enumerate(spec.beats):
                beats.append({"id": beat.id, "start": round(t + 0.2, 3), "end": round(t + 1.2, 3), "text": beat.text})
                for k in range(1, per_beat + 1):
                    name = f"{beat.id}-{k}.png"
                    shade = 0 if k == per_beat else 60 * k
                    color = tuple(min(255, c + shade) for c in colors[j])
                    Image.new("RGB", (fmt.width, fmt.height), color).save(folder / name)
                    frames.append({"beat": beat.id, "k": k, "n": per_beat, "time": round(t + 1.5 * k / per_beat, 3), "path": name})
                t += 1.5
            duration = t + 0.4
        else:
            Image.new("RGB", (fmt.width, fmt.height), colors[0]).save(folder / f"{spec.id}-1.png")
            frames.append({"beat": None, "k": 1, "n": 1, "time": 1.0, "path": f"{spec.id}-1.png"})
            duration = float(spec.duration or 0)
        (folder / "index.json").write_text(json.dumps({"per_beat": per_beat, "frames": frames}), encoding="utf-8")
        timings = {"duration": duration, "beats": beats, "render": {"width": fmt.width, "height": fmt.height, "fps": fmt.fps}}
        path = scene_timings_path(project, preview, spec.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(timings), encoding="utf-8")


@pytest.fixture
def no_render(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every scene's stills count as current; rendering is recorded, not done."""
    calls: list[list[str]] = []

    def fake_render(project: Project, preview: bool, scene_ids: list[str], jobs: int = 1, frames: int = 0) -> pipeline.SceneRuns:
        calls.append(list(scene_ids))
        return pipeline.SceneRuns()

    monkeypatch.setattr(storyboard, "stills_current", lambda *args: True)
    monkeypatch.setattr(pipeline, "render_scenes", fake_render)
    return calls


@pytest.fixture
def deck_project(tmp_path: Path, no_render: list[list[str]]) -> Path:
    root = write_project(tmp_path / "deck", {"scenes": scenes_config()})
    make_tone(root / "audio" / "points_b1.mp3", 0.3)
    fake_stills(Project.load(root))
    return root


# ----- frame selection ---------------------------------------------------------------------------


def test_beat_mode_dedupes_alike_stills(deck_project: Path) -> None:
    deck = deck_frames(Project.load(deck_project))
    assert [s.scene for s in deck.slides] == ["intro", "points", "points", "pause", "end"]
    assert [[b.id for b in s.beats] for s in deck.slides] == [["intro_b1"], ["points_b1"], ["points_b2", "points_b3"], [], ["end_b1"]]
    assert [s.index for s in deck.slides] == [1, 2, 3, 4, 5]
    assert deck.stills == 6 and deck.merged == 1 and deck.slides[2].merged == 2
    merged = deck.slides[2]
    assert merged.notes == "Second point.\n\nNothing new <here> & there."
    assert merged.still.name == "points_b3-1.png"  # the later (more finished) still
    # chapters: none before the first, then the marked scenes
    assert [None if s.chapter is None else (s.chapter.label, s.chapter.title) for s in deck.slides] == [
        None, ("1", "Main part"), ("1", "Main part"), ("1", "Main part"), ("2", "Wrap-up")]
    # the deck timeline: scenes back to back, a slide from the still before to its own still
    assert [(s.at, s.until) for s in deck.slides] == [(0.0, 1.9), (1.9, 3.4), (3.4, 6.8), (6.8, 8.3), (8.3, 10.2)]
    assert deck.duration == pytest.approx(10.2)
    assert [s.time for s in deck.slides] == [1.5, 3.4, 6.4, 7.8, 9.8]
    assert [(c.beat, c.at, c.duration) for c in deck.clips] == [("points_b1", 2.1, 1.0)]
    assert deck.slides[0].alt_text() == "title scene “Hello deck”: Welcome to the deck."
    assert deck.slides[3].alt_text() == "text card scene “Breathe”"
    assert deck.reused == ["intro", "points", "pause", "end"] and deck.rendered == []


def test_scene_mode_and_no_dedupe(deck_project: Path) -> None:
    project = Project.load(deck_project)
    deck = deck_frames(project, mode="scene")
    assert [(s.scene, len(s.beats), s.still.name) for s in deck.slides] == [
        ("intro", 1, "intro_b1-1.png"), ("points", 3, "points_b3-1.png"), ("pause", 0, "pause-1.png"), ("end", 1, "end_b1-1.png")]
    assert [(s.at, s.until) for s in deck.slides] == [(0.0, 1.9), (1.9, 6.8), (6.8, 8.3), (8.3, 10.2)]
    assert len(deck_frames(project, dedupe=False).slides) == 6


def test_per_beat_slides(tmp_path: Path, no_render: list[list[str]]) -> None:
    root = write_project(tmp_path / "pb", {"scenes": scenes_config()})
    project = Project.load(root)
    fake_stills(project, per_beat=2)
    deck = deck_frames(project, per_beat=2)
    points = [s for s in deck.slides if s.scene == "points"]
    assert [(s.k, s.n, [b.id for b in s.beats]) for s in points] == [
        (k, 2, [f"points_b{b}"]) for b in (1, 2, 3) for k in (1, 2)]
    assert points[0].at == 1.9 and points[1].at == pytest.approx(1.9 + 0.75)


def test_options_are_checked(deck_project: Path) -> None:
    project = Project.load(deck_project)
    for kwargs, message in [
        ({"mode": "page"}, "--mode must be one of beat, scene"),
        ({"per_beat": 0}, "--per-beat must be at least 1"),
        ({"mode": "scene", "per_beat": 2}, "--per-beat is for --mode beat"),
        ({"jobs": 0}, "--jobs must be at least 1"),
    ]:
        with pytest.raises(VidgenError, match=re.escape(message)):
            deck_frames(project, **kwargs)
    for kwargs, message in [
        ({"image_format": "gif"}, "--image-format must be one of webp, jpeg, png"),
        ({"quality": 0}, "--quality must be between 1 and 100"),
        ({"max_width": 100}, "--max-width must be at least 160 pixels"),
        ({"output": deck_project / "deck.pdf"}, "--output must be an .html file"),
    ]:
        with pytest.raises(VidgenError, match=re.escape(message)):
            make_slides(project, **kwargs)


def test_stills_alike_tolerates_noise(tmp_path: Path) -> None:
    base = Image.new("RGB", (640, 360), (20, 30, 40))
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    base.save(a)
    noisy = base.copy()
    noisy.putpixel((10, 10), (200, 200, 200))  # one pixel: alike
    noisy.save(b)
    changed = base.copy()
    changed.paste((230, 230, 230), (100, 100, 140, 120))  # a small highlight: different
    changed.save(c)
    assert stills_alike(a, b) and not stills_alike(a, c)
    Image.new("RGB", (320, 320)).save(b)
    assert not stills_alike(a, b)


def test_encode_still(tmp_path: Path) -> None:
    path = tmp_path / "s.png"
    Image.new("RGB", (640, 360), (10, 120, 200)).save(path)
    for fmt, magic in (("webp", b"RIFF"), ("jpeg", b"\xff\xd8"), ("png", b"\x89PNG")):
        payload, w, h = encode_still(path, fmt, 70, 320)
        assert payload.startswith(magic) and (w, h) == (320, 180)
    assert encode_still(path, "webp", 70)[1:] == (640, 360)


def test_translated_notes(tmp_path: Path, no_render: list[list[str]]) -> None:
    config = {
        "scenes": scenes_config(),
        "variants": {"pt": {"language": "pt-BR", "translations": "translations/pt.yaml"}},
    }
    files = {"translations/pt.yaml": "version: 1\nlanguage: pt-BR\nentries:\n  scenes.intro.beats.intro_b1.text:\n"
             "    source: Welcome to the deck.\n    text: Bem-vindo à apresentação.\n"}
    root = write_project(tmp_path / "tr", config, files)
    project = Project.load(root, variant="pt")
    fake_stills(project)
    result = make_slides(project)
    assert result.deck.slides[0].notes == "Bem-vindo à apresentação."
    page = result.path.read_text(encoding="utf-8")
    assert '<html lang="pt-BR">' in page and "Bem-vindo à apresentação." in page
    assert result.path == root / "exports" / "out_pt_preview_slides.html"


# ----- the HTML page -----------------------------------------------------------------------------


class _Page(HTMLParser):
    """Collects the slides (images, notes text), the deck data and the audio tags."""

    def __init__(self) -> None:
        super().__init__()
        self.slides: list[dict[str, Any]] = []
        self.audio: list[dict[str, str]] = []
        self.data = ""
        self._in_notes = 0
        self._in_data = False
        self.external: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in ("script", "link") and (a.get("src") or a.get("href")):
            self.external.append(a.get("src") or a.get("href", ""))
        if tag == "section" and "slide" in a.get("class", "").split():
            self.slides.append({"attrs": a, "img": None, "notes": ""})
        elif tag == "img" and self.slides and self.slides[-1]["img"] is None and "src" in a:
            self.slides[-1]["img"] = a
        elif tag == "div" and a.get("class") == "notes":
            self._in_notes = 1
        elif tag == "div" and self._in_notes:
            self._in_notes += 1
        elif tag == "audio":
            self.audio.append(a)
        elif tag == "script" and a.get("id") == "deck-data":
            self._in_data = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._in_notes:
            self._in_notes -= 1
        if tag == "script":
            self._in_data = False

    def handle_data(self, data: str) -> None:
        if self._in_notes:
            self.slides[-1]["notes"] += data
        if self._in_data:
            self.data += data


def parse_page(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def decode_data_uri(uri: str) -> tuple[str, bytes]:
    match = re.fullmatch(r"data:([\w/+.-]+);base64,([A-Za-z0-9+/=]+)", uri)
    assert match, uri[:60]
    return match.group(1), base64.b64decode(match.group(2), validate=True)


def test_page_structure(deck_project: Path) -> None:
    project = Project.load(deck_project)
    result = make_slides(project, audio=True, quality=60)
    assert result.path == slides_path(project, True) == deck_project / "exports" / "out_preview_slides.html"
    assert result.bytes == result.path.stat().st_size and (result.width, result.height) == SIZE and result.audio == 1
    page = parse_page(result.path)
    assert not page.external  # self-contained
    assert len(page.slides) == 5
    assert [s["attrs"].get("hidden") for s in page.slides] == [None, "", "", "", ""]
    assert [s["attrs"]["aria-label"] for s in page.slides] == [f"{i} of 5" for i in range(1, 6)]
    for slide in page.slides:
        mime, payload = decode_data_uri(slide["img"]["src"])
        assert mime == "image/webp"
        with Image.open(io.BytesIO(payload)) as image:
            assert image.format == "WEBP" and image.size == SIZE
        assert slide["img"]["alt"]
    notes = [s["notes"] for s in page.slides]
    assert "Second point." in notes[2] and "Nothing new <here> & there." in notes[2]
    assert "No narration" in notes[3] and "chapter 2 · Wrap-up" in notes[4]
    data = json.loads(page.data)
    assert data["count"] == 5 and data["mode"] == "beat" and data["duration"] == pytest.approx(10.2)
    assert [s["where"] for s in data["slides"]] == [
        "Hello deck", "1 · Main part — Three points", "1 · Main part — Three points", "1 · Main part — Breathe", "2 · Wrap-up — Bye"]
    assert data["clips"] == [{"id": "audio-points_b1", "beat": "points_b1", "at": 2.1, "duration": 1.0}]
    assert [a["id"] for a in page.audio] == ["audio-points_b1"]
    assert decode_data_uri(page.audio[0]["src"])[1] == (deck_project / "audio" / "points_b1.mp3").read_bytes()
    text = result.path.read_text(encoding="utf-8")
    assert "<h3>1 · Main part</h3>" in text and "<h3>2 · Wrap-up</h3>" in text  # overview groups
    assert text.count('class="thumb"') == 5
    # without --audio: no sound, the play mode still follows the timeline
    page = parse_page(make_slides(project, image_format="jpeg").path)
    assert not page.audio and json.loads(page.data)["clips"] == []
    assert decode_data_uri(page.slides[0]["img"]["src"])[0] == "image/jpeg"


def test_separate_files(deck_project: Path, tmp_path: Path) -> None:
    project = Project.load(deck_project)
    out = tmp_path / "talk" / "deck.html"
    stale = tmp_path / "talk" / "deck_files" / "slide-099.webp"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    result = make_slides(project, separate=True, audio=True, output=out, image_format="png")
    assert result.files_dir == tmp_path / "talk" / "deck_files" and not stale.exists()
    names = sorted(p.name for p in result.files_dir.iterdir())
    assert names == ["points_b1.mp3", "slide-001.png", "slide-002.png", "slide-003.png", "slide-004.png", "slide-005.png"]
    page = parse_page(out)
    assert [s["img"]["src"] for s in page.slides][:2] == ["deck_files/slide-001.png", "deck_files/slide-002.png"]
    assert page.audio[0]["src"] == "deck_files/points_b1.mp3"
    assert result.bytes < 60_000


def test_cli_json(deck_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_stills(Project.load(deck_project).without_overlays())
    code, doc, _ = run_json(["slides", str(deck_project), "--json", "--mode", "scene", "--no-overlays"], capsys)
    assert code == 0 and doc["command"] == "slides"
    assert (doc["mode"], doc["per_beat"], doc["overlays"], doc["dedupe"], doc["preview"]) == ("scene", 1, False, True, True)
    assert doc["format"] == {"width": 96, "height": 54, "fps": 5} and doc["image_format"] == "webp" and doc["quality"] == 80
    assert doc["stills"] == 6 and doc["merged"] == 0 and doc["files_dir"] is None and doc["audio"] == 0
    assert [s["scene"] for s in doc["slides"]] == ["intro", "points", "pause", "end"]
    second = doc["slides"][1]
    assert second["beats"] == ["points_b1", "points_b2", "points_b3"] and second["chapter"] == "Main part"
    assert second["notes"].startswith("First point.\n\nSecond point.")
    assert Path(doc["path"]).is_file() and doc["bytes"] == Path(doc["path"]).stat().st_size
    documented("mode", "overlays", "dedupe", "files_dir", "image_format", "quality", "stills", "merged", "notes", "until", "still")
    # human output
    assert main(["slides", str(deck_project), "--no-dedupe"]) == 0
    out = capsys.readouterr().out
    assert "slides: " in out and "(6 slides from 6 stills" in out and "pictures: 96x54 webp q80" in out
    code, doc, _ = run_json(["slides", str(deck_project), "--json", "--mode", "scene", "--per-beat", "2"], capsys)
    assert code == 1 and "--per-beat is for --mode beat" in doc["error"]["message"]


def test_no_overlays_reads_the_bare_render(deck_project: Path, no_render: list[list[str]]) -> None:
    project = Project.load(deck_project)
    with pytest.raises(VidgenError, match="cannot read"):  # nothing in build/preview_bare yet
        deck_frames(project, overlays=False)
    assert no_render[-1] == []  # stills_current is stubbed: nothing to render
    fake_stills(project.without_overlays())
    deck = deck_frames(project, overlays=False)
    assert "preview_bare" in deck.slides[0].still.parts


# ----- real render ---------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.slow
def test_slides_from_a_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = {"scenes": [
        {"id": "m", "type": "bullets", "params": {"items": ["First point", "Second point"]},
         "beats": [{"text": "One point."}, {"text": "And a second point."}]},
        {"id": "q", "type": "text_card", "params": {"text": "Quiet"}, "duration": 1.0},
    ]}
    root = write_project(tmp_path / "proj", config)
    make_tone(root / "audio" / "m_b1.mp3", 0.6)
    code, doc, _ = run_json(["slides", str(root), "--json", "--audio", "--jobs", "2"], capsys)
    assert code == 0 and doc["rendered"] == ["m", "q"] and doc["audio"] == 1
    assert [(s["scene"], s["beats"]) for s in doc["slides"]] == [("m", ["m_b1"]), ("m", ["m_b2"]), ("q", [])]
    page = parse_page(Path(doc["path"]))
    with Image.open(io.BytesIO(decode_data_uri(page.slides[1]["img"]["src"])[1])) as image:
        assert image.size == SIZE and max(image.convert("L").getextrema()) > 100  # text on the slide
    # the stills are reused (like the storyboard's)
    code, doc, _ = run_json(["slides", str(root), "--json", "--mode", "scene"], capsys)
    assert doc["rendered"] == [] and doc["reused"] == ["m", "q"] and len(doc["slides"]) == 2


# ----- headless browser --------------------------------------------------------------------------


@pytest.mark.slow
def test_browser_navigation(deck_project: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    result = make_slides(Project.load(deck_project), audio=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser installed
            pytest.skip(f"no Chromium for Playwright: {exc}")
        try:
            page = browser.new_page(viewport={"width": 800, "height": 500})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(result.path.as_uri())
            counter = page.locator("#counter")
            assert counter.inner_text() == "1 / 5"
            page.keyboard.press("ArrowRight")
            assert counter.inner_text() == "2 / 5" and page.url.endswith("#2")
            page.keyboard.press("Space")
            page.keyboard.press("PageDown")
            assert counter.inner_text() == "4 / 5"
            page.keyboard.press("ArrowLeft")
            assert counter.inner_text() == "3 / 5"
            page.keyboard.press("End")
            assert counter.inner_text() == "5 / 5"
            page.keyboard.press("Home")
            assert counter.inner_text() == "1 / 5"
            page.keyboard.press("3")
            assert page.locator("#jump").is_visible()
            page.keyboard.press("Enter")
            assert counter.inner_text() == "3 / 5" and page.locator("#slide-3").is_visible()
            assert not page.locator("#slide-1").is_visible()
            # click: right part next, left part previous
            box = page.locator("#stage").bounding_box()
            assert box is not None
            page.mouse.click(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2)
            assert counter.inner_text() == "4 / 5"
            page.mouse.click(box["x"] + 10, box["y"] + box["height"] / 2)
            assert counter.inner_text() == "3 / 5"
            # notes, overview, hash
            page.keyboard.press("s")
            assert "Nothing new <here> & there." in page.locator("#notes-panel").inner_text()
            page.keyboard.press("o")
            assert page.locator("#overview").is_visible()
            page.locator(".thumb[data-index='4']").click()
            assert not page.locator("#overview").is_visible() and counter.inner_text() == "5 / 5"
            page.goto(result.path.as_uri() + "#2")
            page.evaluate("window.dispatchEvent(new HashChangeEvent('hashchange'))")
            assert counter.inner_text() == "2 / 5"
            assert page.locator("#notes-panel").is_visible()  # remembered
            # play mode: the beat's MP3 plays on its stretch of the timeline, the slides follow it
            page.evaluate("window.vidgenSlides.go(1)")
            page.keyboard.press("p")
            page.wait_for_function("document.getElementById('audio-points_b1').currentTime > 0", timeout=5000)
            page.keyboard.press("p")
            assert page.evaluate("document.getElementById('audio-points_b1').paused")
            page.evaluate("window.vidgenSlides.go(3)")
            page.keyboard.press("p")
            page.wait_for_function("window.vidgenSlides.index === 4", timeout=5000)
            assert errors == []
        finally:
            browser.close()
