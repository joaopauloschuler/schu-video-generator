"""The scene gallery (``vidgen gallery``, DESIGN.md §60): every scene type has a sample (the
guide's snippet), the committed ``docs/gallery`` lists every type and shows the current
samples, and the command renders a few types at a tiny size."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from vidgen import cli, extensions, gallery, registry
from vidgen.errors import VidgenError
from vidgen.project import Project

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "gallery"
#: What the committed gallery may weigh (stills + GIFs + pages), see HANDOFF.md Steps 57 and 182
#: (8 MB until the showcases came: 16 GIFs and 16 stills, about 2.8 MB).
BUDGET = 10_000_000


def builtin_gallery() -> list[gallery.GalleryType]:
    with registry.isolated():
        extensions.load_builtins()
        return gallery.gallery_types(None)


def test_every_builtin_type_has_a_sample_from_the_guide() -> None:
    types = builtin_gallery()
    with registry.isolated():
        extensions.load_builtins()
        names = registry.names()
    assert sorted(t.name for t in types) == names
    for t in types:
        if t.alias_of is not None:
            assert t.sample is None and t.alias_of in names
            continue
        assert t.sample is not None, f"{t.name} has no snippet in the guide's scenes topic"
        assert t.sample.origin == "guide" and t.sample.config["type"] == t.name
        assert t.sample.group, t.name
    assert {t.name: t.alias_of for t in types}["flowchart"] == "diagram"


def test_samples_prefer_a_real_picture_and_name_shipped_files() -> None:
    samples = gallery.guide_samples()
    assert "path" in samples["image"].config["params"]   # not the generate: placeholder snippet
    for sample in samples.values():
        for value in gallery._strings(sample.config.get("params", {})):
            if value.startswith("assets/"):
                assert gallery.sample_asset(sample.type, value).is_file(), value
    with pytest.raises(VidgenError, match="no sample file"):
        gallery.sample_asset("code", "assets/train.py")


def test_a_config_snippet_brings_its_characters() -> None:
    stage = gallery.guide_samples()["stage"]
    assert stage.group == "cartoons" and stage.config["type"] == "stage"
    assert {c["name"] for c in stage.characters} == {c["name"] for c in stage.config["params"]["characters"]}
    assert stage.yaml.startswith("characters:") and "type: stage" in stage.yaml   # the page shows the whole config
    config = gallery.work_config(builtin_gallery(), None, None)
    assert [c["name"] for c in config["characters"]] == [c["name"] for c in stage.characters]
    assert gallery._config_snippet("# data\n- id: a\n  type: stat\n") is None


def test_snippet_items_keep_the_guide_text() -> None:
    group, items = gallery._snippet_items("# data\n- id: a\n  type: stat\n- id: b\n  type: pie\n  params: {x: 1}\n")
    assert group == "data"
    assert items == ["- id: a\n  type: stat\n", "- id: b\n  type: pie\n  params: {x: 1}\n"]


def test_chooser_uses_cover_every_type() -> None:
    uses = gallery.chooser_uses()
    for t in builtin_gallery():
        assert uses.get(t.name), t.name
    assert uses["pie"].startswith("parts of a whole")


def test_rendered_names() -> None:
    types = builtin_gallery()
    assert gallery.rendered_names(types, ["flowchart", "pie"]) == [n for n in (t.name for t in types) if n in ("diagram", "pie")]
    assert "flowchart" not in gallery.rendered_names(types, None)
    assert gallery.rendered_names(types, ["iso_lamp", "pie"]) == ["pie"]     # a showcase is not a type
    assert [s.name for s in gallery.rendered_showcases(["iso_lamp", "pie"])] == ["iso_lamp"]
    assert gallery.rendered_showcases(None) == list(gallery.SHOWCASES)
    with registry.isolated():
        extensions.load_builtins()
        with pytest.raises(VidgenError, match="unknown scene type 'piechart'"):
            gallery.rendered_names(types, ["piechart"])


# ----- showcases ---------------------------------------------------------------------------------


def test_showcases_are_whole_valid_configs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import yaml

    with registry.isolated():
        extensions.load_builtins()
        types = set(registry.names())
    groups = {t.sample.group for t in builtin_gallery() if t.sample is not None}
    names = [s.name for s in gallery.SHOWCASES]
    assert len(set(names)) == len(names) and not set(names) & types
    assert sorted(p.stem for p in gallery.SHOWCASES_DIR.glob("*.yaml")) == sorted(names)
    assert {s.section for s in gallery.SHOWCASES} == {"cartoons", "isometric cartoons"}
    for showcase in gallery.SHOWCASES:
        assert showcase.section in groups or showcase.section in gallery.SECTION_NOTES
        config = gallery.showcase_work_config(showcase, None)
        assert config["variants"][gallery.PORTRAIT_VARIANT]["preview"]["width"] == gallery.FORMATS["9:16"][0]
        root = tmp_path / showcase.name
        root.mkdir()
        (root / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        problems, _ = cli.validate_all(Project.load(root), keep_going=True)
        assert not problems, f"{showcase.name}:\n" + "\n".join(str(p) for p in problems)
    assert gallery.showcase_work_config(gallery.SHOWCASES[0], "neon")["theme"] == {"preset": "neon"}

    (tmp_path / "two.yaml").write_text("scenes: [{id: two, type: card}, {id: more, type: card}]\n", encoding="utf-8")
    monkeypatch.setattr(gallery, "SHOWCASES_DIR", tmp_path)
    with pytest.raises(VidgenError, match="one scene, id 'two'"):
        gallery.Showcase("two", "cartoons", "x", "y").config()


# ----- clips -------------------------------------------------------------------------------------


def test_clip_start_skips_the_empty_opening() -> None:
    import numpy as np

    fade = [np.full((4, 6), 10.0 * k) for k in range(6)]          # a fade-in over 6 frames, then still
    assert gallery.clip_start(fade + [fade[-1]] * 10, 6) == pytest.approx(4 / 6)   # 40 >= 0.75 * 50
    assert gallery.clip_start([np.zeros((4, 6))] * 5, 6) == 0.0     # nothing changes
    slow = [np.full((4, 6), float(k)) for k in range(60)]           # a build-up over 10 s
    assert gallery.clip_start(slow, 6) == gallery.CLIP_START_MAX


def test_gif_can_open_on_its_held_end(tmp_path: Path) -> None:
    import subprocess

    from vidgen.export import write_gif
    from vidgen.render.ffmpeg import decode_gray_frames, find_ffmpeg

    ffmpeg = find_ffmpeg()
    video = tmp_path / "ramp.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=64x36:r=6:d=2",
                    "-vf", "fade=in:st=0:d=2", "-pix_fmt", "yuv420p", str(video)], check=True)
    frames = decode_gray_frames(video, 32, 6, 2.0)
    assert frames.shape[1:] == (18, 32) and frames[0].mean() < frames[-1].mean()
    gif = tmp_path / "ramp.gif"
    write_gif(ffmpeg, video, gif, 32, 6, 0.0, 2.0, colors=16, dither="none", hold=1.0, hold_first=True)
    from PIL import ImageStat

    def brightness(image: Image.Image, frame: int) -> float:
        image.seek(frame)
        return float(ImageStat.Stat(image.convert("L")).mean[0])

    with Image.open(gif) as image:
        first, last = brightness(image, 0), brightness(image, image.n_frames - 1)
        early = brightness(image, 7)                              # after the held end: the start again
    assert first > 200 and abs(first - last) < 3 and early < 100


def test_project_types_take_their_first_scene(tmp_path: Path) -> None:
    project = Project.load(ROOT / "examples" / "custom_scene")
    with extensions.project_session(project):
        types = {t.name: t for t in gallery.gallery_types(project)}
    gear = types["gear_pair"]
    assert gear.sample is not None and gear.sample.origin == "video.yaml" and gear.sample.group == gallery.PROJECT_GROUP
    assert gear.sample.config["type"] == "gear_pair" and "gear_pair" in gear.sample.yaml
    assert types["bar_chart"].sample is not None and types["bar_chart"].sample.origin == "guide"
    config = gallery.work_config(list(types.values()), project, None)
    assert [Path(d).name for d in config["extensions"]] == ["extensions"]
    assert "gear_pair" in [s["id"] for s in config["scenes"]]
    assert gallery.work_config(list(types.values()), project, "neon")["theme"] == {"preset": "neon"}


def test_cli_usage_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["gallery", "--types", "piechart", "-o", "out"]) == 1
    assert "unknown scene type 'piechart'" in capsys.readouterr().err
    assert cli.main(["gallery", "--formats", "4:3", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert not doc["ok"] and "unknown format '4:3'" in doc["error"]["message"]
    assert not (tmp_path / "out").exists() and not (tmp_path / "build").exists()


# ----- the committed gallery ---------------------------------------------------------------------


def test_committed_gallery_lists_every_type_with_current_samples() -> None:
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    for t in builtin_gallery():
        assert f"`{t.name}`" in index, f"docs/gallery/README.md misses {t.name}: run `vidgen gallery`"
        if t.alias_of is not None:
            continue
        assert t.sample is not None
        page = (DOCS / f"{t.name}.md").read_text(encoding="utf-8")
        assert t.sample.yaml.rstrip() in page, f"docs/gallery/{t.name}.md shows an old sample: run `vidgen gallery --types {t.name}`"
        for fmt in gallery.FORMATS:
            still = DOCS / "media" / gallery.media_name(t.name, fmt, ".png")
            assert still.is_file(), still
            with Image.open(still) as image:
                assert image.size == gallery.FORMATS[fmt]
            assert f"media/{still.name}" in index and f"media/{still.name}" in page
            assert gallery.preview_html(t.name, fmt, link=f"{t.name}.md") in index   # the GIF, the still for reduced motion


def test_committed_gallery_has_every_showcase() -> None:
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    assert "## 2D cartoons" in index and "## Isometric cartoons" in index and "| type | stills |" not in index
    assert index.index("## 2D cartoons") < index.index("[`stage`](stage.md)") < index.index("## Isometric cartoons")
    assert "../../examples/iso-story/video.yaml" in index and (ROOT / "examples" / "iso-story" / "video.yaml").is_file()
    for showcase in gallery.SHOWCASES:
        page = (DOCS / f"{showcase.name}.md").read_text(encoding="utf-8")
        assert showcase.text().rstrip() in page, f"docs/gallery/{showcase.name}.md is old: run `vidgen gallery --types {showcase.name}`"
        assert f"[{showcase.title}]({showcase.name}.md)" in index
        for fmt in gallery.FORMATS:
            assert gallery.preview_html(showcase.name, fmt, link=f"{showcase.name}.md") in index
            with Image.open(DOCS / "media" / gallery.media_name(showcase.name, fmt, ".png")) as image:
                assert image.size == gallery.FORMATS[fmt]
    section = index[index.index("## 2D cartoons"):]
    assert section.index("[`card`](card.md)") < section.index("(talk_in_a_room.md)") < section.index("## Isometric cartoons") < section.index("(iso_village.md)")


def test_committed_gifs_are_light_and_open_on_their_end() -> None:
    gifs = sorted((DOCS / "media").glob("*.gif"))
    assert len(gifs) == 2 * (len([t for t in builtin_gallery() if t.alias_of is None]) + len(gallery.SHOWCASES))
    for gif in gifs:
        assert gif.stat().st_size <= gallery.CLIP_MAX_BYTES, gif.name
        with Image.open(gif) as image:
            first = image.convert("L")
            assert first.width == gallery.CLIP_WIDTHS["16:9" if "-16x9" in gif.name else "9:16"]
            low, high = first.getextrema()
            assert high - low > 40, f"{gif.name} opens on an empty frame"


def test_committed_gallery_is_within_its_size_budget() -> None:
    files = [p for p in DOCS.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    assert total < BUDGET, f"docs/gallery is {total / 1e6:.1f} MB (budget {BUDGET / 1e6:g} MB)"
    assert {p.suffix for p in files} <= {".md", ".png", ".gif"}


def test_readme_strip_links_the_gallery() -> None:
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    strip = readme[readme.index("More from the [scene gallery]"):readme.index("Everything is built around")]
    pictures = re.findall(r'<a href="([^"]+)"><picture><source media="\(prefers-reduced-motion: reduce\)" srcset="([^"]+)"><img src="([^"]+)"', strip)
    assert 3 <= len(pictures) <= 4 and strip.count("<picture>") == strip.count("</picture>") == len(pictures)
    for page, still, gif in pictures:
        assert (ROOT / page).is_file() and (ROOT / still).is_file() and (ROOT / gif).is_file()
        assert Path(still).stem == Path(gif).stem and page.startswith("docs/gallery/")


def test_readme_and_guide_point_to_the_gallery() -> None:
    assert "docs/gallery" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "vidgen gallery" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


# ----- rendering ---------------------------------------------------------------------------------


@pytest.mark.render
def test_gallery_renders_a_few_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gallery, "FORMATS", {"16:9": (160, 90), "9:16": (90, 160)})
    monkeypatch.setattr(gallery, "FPS", 5)
    monkeypatch.setattr(gallery, "CLIP_WIDTHS", {"16:9": 96, "9:16": 54})
    monkeypatch.setattr(gallery, "CLIP_FPS", 5)
    assert cli.main(["gallery", "--types", "stat,flowchart", "-o", "out", "-j", "2", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["command"] == "gallery" and doc["project"] is None and doc["showcases"] == []
    assert sorted(doc["rendered"]) == ["diagram (16:9)", "diagram (9:16)", "stat (16:9)", "stat (9:16)"]
    out = tmp_path / "out"
    types = {t["name"]: t for t in doc["types"]}
    assert types["flowchart"]["alias_of"] == "diagram" and types["flowchart"]["page"] is None
    for name in ("stat", "diagram"):
        assert Path(types[name]["page"]) == (out / f"{name}.md").resolve()
        for fmt, size in gallery.FORMATS.items():
            with Image.open(types[name]["stills"][fmt]) as image:
                assert image.size == size
            with Image.open(types[name]["clips"][fmt]) as clip:
                assert clip.format == "GIF" and clip.n_frames > 3 and clip.size[0] == gallery.CLIP_WIDTHS[fmt]
    assert types["pie"]["stills"] == {} and not (out / "pie.md").exists()
    index = (out / "README.md").read_text(encoding="utf-8")
    assert "[`stat`](stat.md)" in index and "same type as [`diagram`](diagram.md)" in index
    assert "| `pie` | not rendered here yet (`vidgen gallery --types pie`) |" in index
    assert "| A cut-away room | not rendered here yet (`vidgen gallery --types iso_room`) |" in index
    assert '<picture><source media="(prefers-reduced-motion: reduce)" srcset="media/stat-9x16.png">' in index
    page = (out / "diagram.md").read_text(encoding="utf-8")
    assert "type: diagram" in page and "Also available as `flowchart`" in page and "## Targets" in page and "`node:<id>`" in page
    assert "| `nodes` |" in page and "media/diagram-9x16.gif" in page
    first = {p.name: p.read_bytes() for p in (out / "media").iterdir()}
    pages = {p.name: p.read_bytes() for p in out.glob("*.md")}

    # again, without clips, for one type: nothing is rendered, the files are the same
    assert cli.main(["gallery", "--types", "stat", "-o", "out", "--no-clips", "--formats", "16:9"]) == 0
    printed = capsys.readouterr().out
    assert "rendered 0 sample(s), 1 reused" in printed
    assert {p.name: p.read_bytes() for p in (out / "media").iterdir()} == first
    assert {p.name: p.read_bytes() for p in out.glob("*.md")} == pages
