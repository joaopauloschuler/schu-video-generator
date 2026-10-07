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
#: What the committed gallery may weigh (stills + GIFs + pages), see HANDOFF.md Step 57.
BUDGET = 8_000_000


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
    with registry.isolated():
        extensions.load_builtins()
        with pytest.raises(VidgenError, match="unknown scene type 'piechart'"):
            gallery.rendered_names(types, ["piechart"])


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


def test_committed_gallery_is_within_its_size_budget() -> None:
    files = [p for p in DOCS.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    assert total < BUDGET, f"docs/gallery is {total / 1e6:.1f} MB (budget {BUDGET / 1e6:g} MB)"
    assert {p.suffix for p in files} <= {".md", ".png", ".gif"}


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
    assert doc["ok"] and doc["command"] == "gallery" and doc["project"] is None
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
