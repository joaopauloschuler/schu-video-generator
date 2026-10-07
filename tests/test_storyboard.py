"""`vidgen storyboard`: sheet layout, scene fingerprints, reuse of current stills, CLI and JSON.

Rendering tests use 160x90 @ 10 fps (preview 96x54 @ 5 fps) and a few small scenes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from test_json_output import documented, run_json
from test_render import make_tone, write_project
from vidgen import sheets
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render import fingerprint
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.sheets import SheetScene, SheetStill, compose_pages, fit_line, format_time, load_font, wrap_text
from vidgen.storyboard import make_storyboard, stills_current

# ----- sheet layout (no rendering) ---------------------------------------------------------------


def test_format_time() -> None:
    assert [format_time(t) for t in (0, 5.66, 59.96, 75.25, 600)] == ["0:00.0", "0:05.7", "1:00.0", "1:15.2", "10:00.0"]


def test_wrap_and_fit() -> None:
    font = load_font(20)
    words = "one two three four five six seven eight nine ten eleven twelve"
    lines = wrap_text(font, words, 120, 10)
    assert len(lines) > 2 and all(font.getlength(line) <= 120 for line in lines)
    assert " ".join(lines) == words
    short = wrap_text(font, words, 120, 2)
    assert len(short) == 2 and short[-1].endswith("…") and font.getlength(short[-1]) <= 120
    broken = wrap_text(font, "x" * 80, 100, 10)  # a word longer than a line is broken
    assert "".join(broken) == "x" * 80 and all(font.getlength(line) <= 100 for line in broken)
    assert fit_line(font, "short", 200) == "short"
    cut = fit_line(font, "a rather long line of text", 80)
    assert cut.endswith("…") and font.getlength(cut) <= 80


def test_font_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    load_font.cache_clear()
    monkeypatch.setattr(sheets, "REGULAR_FONTS", ("no-such-font.ttf",))
    try:
        assert load_font(17).getlength("abc") > 0  # Pillow's built-in font
    finally:
        load_font.cache_clear()


@pytest.mark.parametrize(
    ("size", "detail", "per_beat", "expected"),
    [
        ((1920, 1080), False, 1, 4), ((1920, 1080), True, 1, 2), ((1080, 1920), False, 1, 5),
        ((1080, 1920), True, 1, 4), ((1080, 1080), False, 1, 5), ((1920, 1080), False, 3, 3),
        ((1920, 1080), True, 3, 3), ((1080, 1920), False, 3, 6), ((1920, 1080), False, 12, 8),
    ],
)
def test_columns(size: tuple[int, int], detail: bool, per_beat: int, expected: int) -> None:
    assert sheets._columns(size, detail, per_beat) == expected


def still_files(folder: Path, size: tuple[int, int], count: int) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = folder / f"s{i}.png"
        Image.new("RGB", size, (20 * (i % 10), 40, 90)).save(path)
        paths.append(path)
    return paths


def sheet_scene(number: int, total: int, paths: list[Path], per_beat: int = 1, silent: bool = False, start: float | None = 0.0) -> SheetScene:
    sid = f"scene{number}"
    stills = []
    for i, path in enumerate(paths):
        beat = None if silent else f"{sid}_b{i // per_beat + 1}"
        text = None if silent else f"Narration of beat {i // per_beat + 1} of scene {number}, " + "with many words " * (i % 4)
        t = 1.0 + i
        stills.append(SheetStill(sid, beat, i % per_beat + 1, per_beat, t, None if start is None else start + t, path, text))
    beats = 0 if silent else len(paths) // per_beat
    return SheetScene(sid, "text_card", number, total, start, float(len(paths) + 1), beats, tuple(stills))


def test_compose_one_page(tmp_path: Path) -> None:
    paths = still_files(tmp_path, (160, 90), 5)
    scenes = [sheet_scene(1, 3, paths[:2]), sheet_scene(2, 3, paths[2:4], start=None), sheet_scene(3, 3, paths[4:], silent=True)]
    pages = compose_pages("Title", "subtitle", scenes, (160, 90))
    assert len(pages) == 1
    page = pages[0]
    assert page.image.width == sheets.DEFAULT_WIDTH and page.image.height <= sheets.DEFAULT_WIDTH * sheets.PAGE_RATIO
    assert [s.path for s in page.stills] == paths


def test_compose_splits_long_videos_into_pages(tmp_path: Path) -> None:
    paths = still_files(tmp_path, (160, 90), 60)
    scenes = [sheet_scene(i + 1, 12, paths[i * 5 : i * 5 + 5]) for i in range(12)]
    pages = compose_pages("Long", "sub", scenes, (160, 90), width=1000)
    assert len(pages) > 2
    assert [s.path for page in pages for s in page.stills] == paths  # every still once, in order
    limit = round(1000 * sheets.PAGE_RATIO)
    for page in pages:
        assert page.image.width == 1000 and page.image.height <= limit + 80  # + a repeated header
    heights = [p.image.height for p in pages]
    assert min(heights) > max(heights) / 3  # balanced: no nearly empty last page


def test_compose_continued_scene_and_vertical_frames(tmp_path: Path) -> None:
    paths = still_files(tmp_path, (54, 96), 30)
    pages = compose_pages("Tall", "sub", [sheet_scene(1, 1, paths, per_beat=3)], (54, 96), detail=True, video_times=False)
    assert len(pages) > 1
    m = sheets._metrics(sheets.DEFAULT_WIDTH, (54, 96), True, None, 3)
    assert m.columns == 3 and m.cell_h > m.cell_w  # one beat per row, tall cells
    rows = sheets._paginate(sheets._rows([sheet_scene(1, 1, paths, per_beat=3)], m), m, 100)
    assert all(page[0].segments[0].header for page in rows)
    assert [page[0].segments[0].continued for page in rows] == [False] + [True] * (len(rows) - 1)
    text = sheets._header_text(sheet_scene(1, 1, paths, per_beat=3), True, m.header, 2000)
    assert text.startswith("1/1  scene1  ·  text_card  ·  0:00.0–0:31.0 (31.0 s)") and text.endswith("(continued)")
    narrow = sheets._header_text(sheet_scene(1, 1, paths, per_beat=3), False, m.header, 150)
    assert narrow == "1/1  scene1"  # details left out before cutting
    labels = [sheets._label(s, False) for s in sheet_scene(1, 1, paths[:3], per_beat=3).stills]
    assert labels == ["1/3 @ 1.0 s", "2/3 @ 2.0 s", "3/3 @ 3.0 s"]
    one = sheet_scene(2, 2, paths[:1], start=10.0).stills[0]
    assert sheets._label(one, True) == "scene2_b1 @ 0:11.0" and sheets._label(one, False) == "scene2_b1 @ 1.0 s"


def test_short_scenes_share_a_row(tmp_path: Path) -> None:
    paths = still_files(tmp_path, (160, 90), 7)
    scenes = [sheet_scene(1, 3, paths[:2]), sheet_scene(2, 3, paths[2:3]), sheet_scene(3, 3, paths[3:])]
    m = sheets._metrics(sheets.DEFAULT_WIDTH, (160, 90), False, None, 1)
    rows = sheets._rows(scenes, m)
    assert [[(s.scene.id, s.cells, s.header) for s in row.segments] for row in rows] == [
        [("scene1", 2, True), ("scene2", 1, True)],
        [("scene3", 4, True)],
    ]


# ----- fingerprints (no rendering) ---------------------------------------------------------------


def fp_project(tmp_path: Path) -> Path:
    config = {
        "scenes": [
            {"id": "a", "type": "text_card", "params": {"text": "A"}, "beats": [{"text": "One."}]},
            {"id": "b", "type": "text_card", "params": {"text": "B"}, "beats": [{"text": "Two."}]},
        ]
    }
    root = write_project(tmp_path / "fp", config, {"extensions/helper.py": "X = 1\n", "assets/pic.txt": "1"})
    return root


def edit_config(root: Path, change: Any) -> None:
    import yaml

    path = root / "video.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_fingerprint_inputs(tmp_path: Path) -> None:
    root = fp_project(tmp_path)

    def fps() -> tuple[str, str]:
        project = Project.load(root)
        return scene_fingerprint(project, "a"), scene_fingerprint(project, "b")

    a, b = fps()
    assert a != b and fps() == (a, b)
    edit_config(root, lambda d: d["scenes"][1]["params"].update(text="B2"))
    a2, b2 = fps()
    assert a2 == a and b2 != b  # another scene's params do not matter
    edit_config(root, lambda d: d["scenes"][0]["beats"][0].update(text="Changed."))
    assert fps()[0] != a
    a = fps()[0]
    edit_config(root, lambda d: d["theme"].update(background="#000000"))
    assert fps()[0] != a
    a = fps()[0]
    edit_config(root, lambda d: d.update(title="New title", variants={"v": {"title": "x"}}))
    assert fps()[0] != a  # every section but scenes/variants counts
    a = fps()[0]
    edit_config(root, lambda d: d["variants"].update(w={"title": "y"}))
    assert fps()[0] == a  # variants only count once applied
    make_tone(root / "audio" / "a_b1.mp3", 0.3)
    assert fps()[0] != a
    a = fps()[0]
    (root / "extensions" / "helper.py").write_text("X = 2\n", encoding="utf-8")
    assert fps()[0] != a
    a = fps()[0]
    (root / "assets" / "pic.txt").write_text("22", encoding="utf-8")
    assert fps()[0] != a


def test_vidgen_source_digest_skips_non_render_modules() -> None:
    package = Path(fingerprint.__file__).resolve().parent.parent
    assert not fingerprint._render_input(package / "cli.py")
    assert not fingerprint._render_input(package / "tts" / "run.py")
    assert not fingerprint._render_input(package / "sheets.py")
    assert fingerprint._render_input(package / "scene.py")
    assert fingerprint._render_input(package / "scenes" / "bullets.py")
    assert fingerprint._render_input(package / "render" / "worker.py")
    assert len(fingerprint.vidgen_source_digest()) == 64


def test_options_are_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = fp_project(tmp_path)
    project = Project.load(root)
    assert not stills_current(project, True, "a", 1)
    with pytest.raises(VidgenError, match="--per-beat must be at least 1"):
        make_storyboard(project, per_beat=0)
    with pytest.raises(VidgenError, match="--width must be between 640 and 2000"):
        make_storyboard(project, width=3000)
    with pytest.raises(VidgenError, match="--jobs must be at least 1"):
        make_storyboard(project, jobs=0)
    assert main(["storyboard", str(root), "--scene", "nope"]) == 1
    assert "unknown scene(s): nope; scenes: a, b" in capsys.readouterr().err
    code, doc, _ = run_json(["storyboard", str(root), "--preview", "--final", "--json"], capsys)
    assert code == 2 and doc["error"]["kind"] == "usage"


# ----- rendering ---------------------------------------------------------------------------------


def scenes_config() -> list[dict[str, Any]]:
    return [
        {"id": "m", "type": "bullets", "params": {"items": ["First point", "Second point"]},
         "beats": [{"text": "One point."}, {"text": "And a second, longer point to read."}]},
        {"id": "q", "type": "text_card", "params": {"text": "Quiet"}, "duration": 1.0},
        {"id": "t", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Short words here."}]},
    ]


@pytest.fixture
def board_project(tmp_path: Path) -> Path:
    root = write_project(tmp_path / "proj", {"scenes": scenes_config()})
    make_tone(root / "audio" / "m_b1.mp3", 0.8)
    return root


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.render
@pytest.mark.slow
def test_storyboard_json_reuse_and_staleness(board_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = board_project
    build = root / "build" / "preview"
    code, doc, _ = run_json(["storyboard", str(root), "--json", "--jobs", "2"], capsys)
    assert code == 0 and doc["command"] == "storyboard"
    assert (doc["preview"], doc["per_beat"], doc["variant"]) == (True, 1, None)
    assert doc["format"] == {"width": 96, "height": 54, "fps": 5}
    assert doc["rendered"] == ["m", "q", "t"] and doc["reused"] == []
    assert doc["folder"] == str((build / "storyboard").resolve())
    kinds = [(s["kind"], s["scene"], s["page"], s["pages"]) for s in doc["sheets"]]
    assert kinds == [("video", None, 1, 1), ("scene", "m", 1, 1), ("scene", "q", 1, 1), ("scene", "t", 1, 1)]
    video = doc["sheets"][0]
    assert Path(video["path"]).name == "video-1.png" and Path(doc["sheets"][1]["path"]).name == "m-1.png"
    with Image.open(video["path"]) as image:
        assert image.size == (video["width"], video["height"]) and image.width == 1280
    frames = video["frames"]
    assert [(f["scene"], f["beat"], f["k"], f["n"]) for f in frames] == [
        ("m", "m_b1", 1, 1), ("m", "m_b2", 1, 1), ("q", None, 1, 1), ("t", "t_b1", 1, 1)]
    timings = {sid: read_json(build / "timings" / f"{sid}.json") for sid in ("m", "q", "t")}
    assert frames[2]["time"] == pytest.approx(timings["m"]["duration"] + frames[2]["scene_time"])
    assert all(Path(f["path"]).is_file() for f in frames)
    assert timings["m"]["render"]["fingerprint"] == scene_fingerprint(Project.load(root), "m")
    documented("per_beat", "folder", "reused", "sheets", "kind", "page", "pages", "scene_time")

    # nothing changed: everything reused, nothing rendered
    stamp = (build / "scenes" / "m.mp4").stat().st_mtime_ns
    assert main(["storyboard", str(root)]) == 0
    out = capsys.readouterr().out
    assert "rendered 0 scene(s), 3 reused" in out and "video-1.png  (4 stills" in out
    assert (build / "scenes" / "m.mp4").stat().st_mtime_ns == stamp

    # a changed scene is rendered again, the others are reused
    edit_config(root, lambda d: d["scenes"][2]["params"].update(text="Hello"))
    code, doc, _ = run_json(["storyboard", str(root), "--json"], capsys)
    assert doc["rendered"] == ["t"] and doc["reused"] == ["m", "q"]

    # --scene: only that scene's sheet; the (possibly stale) video sheets are removed
    code, doc, _ = run_json(["storyboard", str(root), "--json", "--scene", "q", "--force"], capsys)
    assert doc["rendered"] == ["q"] and [(s["kind"], s["scene"]) for s in doc["sheets"]] == [("scene", "q")]
    assert not list((build / "storyboard").glob("video-*.png"))
    assert (build / "storyboard" / "scenes" / "m-1.png").is_file()

    # another count of stills per beat renders again; labels group the beat's stills
    code, doc, _ = run_json(["storyboard", str(root), "--json", "--per-beat", "2", "--width", "800"], capsys)
    assert doc["rendered"] == ["m", "q", "t"] and doc["per_beat"] == 2
    assert [f["k"] for f in doc["sheets"][0]["frames"]] == [1, 2, 1, 2, 1, 2, 1, 2]
    assert doc["sheets"][0]["width"] == 800
    assert not stills_current(Project.load(root), True, "m", 1) and stills_current(Project.load(root), True, "m", 2)


@pytest.mark.render
@pytest.mark.slow
def test_storyboard_after_render_and_vertical_variant(board_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = board_project
    config = (root / "video.yaml").read_text(encoding="utf-8")
    (root / "video.yaml").write_text(config + "variants:\n  vertical:\n    preview: {width: 54, height: 96}\n", encoding="utf-8")
    assert main(["render", str(root), "--preview", "--variant", "vertical", "--frames"]) == 0
    capsys.readouterr()
    # a storyboard right after `render --frames` reuses every scene's stills
    code, doc, _ = run_json(["storyboard", str(root), "--variant", "vertical", "--json"], capsys)
    assert doc["rendered"] == [] and doc["reused"] == ["m", "q", "t"] and doc["variant"] == "vertical"
    build = root / "build" / "preview_vertical"
    assert doc["folder"] == str((build / "storyboard").resolve())
    with Image.open(doc["sheets"][0]["path"]) as image:
        assert image.width == 1280 and image.height < image.width * 1.3
    # removing the stills folder of one scene makes it render again (only it)
    os.remove(build / "frames" / "t" / "t_b1-1.png")
    code, doc, _ = run_json(["storyboard", str(root), "--variant", "vertical", "--json", "--scene", "t"], capsys)
    assert doc["rendered"] == ["t"] and doc["reused"] == []
    assert not (build / "frames" / "index.json").exists()  # no longer matches the stills
