"""`vidgen slides --format pdf`: the PDF deck (pages, sizes, notes text, outline, metadata, title
page, translated notes, options, CLI / JSON).

The stills are faked like in ``test_slides`` (no Manim); the PDFs are read back with pypdf (a dev
dependency).
"""

from __future__ import annotations

import builtins
import io
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from test_json_output import documented, run_json
from test_render import write_project
from test_slides import deck_project, fake_stills, no_render, scenes_config  # noqa: F401 - fixtures
from vidgen.cli import main
from vidgen.deck import deck_frames
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.slides_pdf import make_slides_pdf, pdf_path, slide_page_size

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("fpdf")

METADATA = {"artist": "Ada Lovelace", "description": "A deck for tests", "date": "2026", "genre": "Education"}


def read(path: Path) -> Any:
    return pypdf.PdfReader(str(path))


def page_size(page: Any) -> tuple[float, float]:
    box = page.mediabox
    return round(float(box.width), 1), round(float(box.height), 1)


def page_text(page: Any) -> str:
    return " ".join(page.extract_text().split())


def outline(reader: Any, items: list[Any] | None = None) -> list[Any]:
    """The outline as nested ``(title, page number from 1)`` / lists of children."""
    out: list[Any] = []
    for item in reader.outline if items is None else items:
        if isinstance(item, list):
            out.append(outline(reader, item))
        else:
            out.append((item.title, reader.get_destination_page_number(item) + 1))
    return out


def image_filters(page: Any) -> list[str]:
    xobjects = page["/Resources"]["/XObject"]
    return [str(xobjects[name].get_object()["/Filter"]) for name in xobjects]


@pytest.fixture
def meta_project(tmp_path: Path, no_render: list[list[str]]) -> Path:  # noqa: F811 - the fixture
    root = write_project(tmp_path / "meta", {"scenes": scenes_config(), "language": "en", "metadata": METADATA})
    fake_stills(Project.load(root))
    return root


def test_slide_pages(meta_project: Path) -> None:
    project = Project.load(meta_project)
    result = make_slides_pdf(project)
    assert result.path == pdf_path(project, True) == meta_project / "exports" / "out_preview_slides.pdf"
    assert result.pages == 5 and result.bytes == result.path.stat().st_size and (result.width, result.height) == (96, 54)
    reader = read(result.path)
    assert len(reader.pages) == 5
    assert {page_size(p) for p in reader.pages} == {(960.0, 540.0)}  # the video's 16:9
    assert all(image_filters(p) == ["/DCTDecode"] for p in reader.pages)  # JPEG, embedded as is
    # outline: slides before the first chapter at the top, then each chapter with its slides
    assert outline(reader) == [
        ("1. Hello deck", 1),
        ("1 · Main part", 2), [("2. Three points", 2), ("3. Three points", 3), ("4. Breathe", 4)],
        ("2 · Wrap-up", 5), [("5. Bye", 5)],
    ]
    assert result.bookmarks == 7
    info = reader.metadata
    assert (info.title, info.author, info.subject) == ("Render test", "Ada Lovelace", "A deck for tests")
    assert info["/Keywords"] == "Education" and info.creator.startswith("vidgen ")
    root = reader.trailer["/Root"]
    assert root["/Lang"] == "en" and root["/PageMode"] == "/UseOutlines"


def test_notes_pages(meta_project: Path) -> None:
    project = Project.load(meta_project)
    result = make_slides_pdf(project, notes=True, title_page=True)
    assert result.path == meta_project / "exports" / "out_preview_notes.pdf"
    reader = read(result.path)
    assert result.pages == len(reader.pages) == 6 and result.thumbnail is None
    assert {page_size(p) for p in reader.pages} == {(595.3, 841.9)}  # A4 portrait
    title = page_text(reader.pages[0])
    assert "Render test" in title and "Ada Lovelace · 2026" in title and "5 slides with speaker notes" in title
    texts = [page_text(p) for p in reader.pages[1:]]
    assert "Welcome to the deck." in texts[0] and "Slide 1 / 5 · Hello deck" in texts[0] and "2 / 6" in texts[0]
    assert "Second point." in texts[2] and "Nothing new <here> & there." in texts[2]
    assert "1 · Main part" in texts[2] and "Render test" in texts[2]  # header: chapter and title
    assert "No narration (a silent scene)." in texts[3]
    assert "2 · Wrap-up" in texts[4] and "Thanks for watching." in texts[4] and "6 / 6" in texts[4]
    assert outline(reader)[0] == ("Render test", 1) and outline(reader)[1] == ("1. Hello deck", 2)
    fonts = {str(f.get_object()["/BaseFont"]) for p in reader.pages for f in p["/Resources"]["/Font"].values()}
    assert fonts and all("Inter" in name for name in fonts)  # the bundled Inter, embedded (subset)
    letter = make_slides_pdf(project, notes=True, paper="letter", output=meta_project / "letter.pdf")
    assert {page_size(p) for p in read(letter.path).pages} == {(612.0, 792.0)}


def test_long_notes_continue(tmp_path: Path, no_render: list[list[str]]) -> None:  # noqa: F811
    scenes = scenes_config()
    scenes[0]["beats"] = [{"text": " ".join(["A long narration sentence that keeps going."] * 120)}]
    root = write_project(tmp_path / "long", {"scenes": scenes})
    project = Project.load(root)
    fake_stills(project)
    reader = read(make_slides_pdf(project, notes=True).path)
    assert len(reader.pages) > 5
    assert outline(reader)[0] == ("1. Hello deck", 1) and outline(reader)[1][0] == "1 · Main part"
    second = outline(reader)[1][1]
    assert second > 2  # the first slide's notes took more than one page
    assert "Slide 2 / 5" in page_text(reader.pages[second - 1])


def test_title_page_with_thumbnail_and_portrait(tmp_path: Path, no_render: list[list[str]]) -> None:  # noqa: F811
    root = write_project(tmp_path / "tall", {"scenes": scenes_config(), "preview": {"width": 54, "height": 96, "fps": 5}})
    project = Project.load(root)
    fake_stills(project)
    Image.new("RGB", (72, 128), (0, 120, 200)).save(project.thumbnail_path(False))
    result = make_slides_pdf(project, title_page=True, image_format="png")
    assert result.thumbnail == project.thumbnail_path(False)
    reader = read(result.path)
    assert len(reader.pages) == 6 and {page_size(p) for p in reader.pages} == {(540.0, 960.0)}
    assert image_filters(reader.pages[0]) == ["/FlateDecode"]  # the thumbnail, full page
    assert slide_page_size(1920, 1080) == (960.0, 540.0) and slide_page_size(1080, 1350) == (768.0, 960.0)
    # notes pages: a tall slide is at most half the page high
    notes = read(make_slides_pdf(project, notes=True, title_page=True).path)
    assert "Render test" in page_text(notes.pages[0])


def test_translated_notes_render_accents(tmp_path: Path, no_render: list[list[str]]) -> None:  # noqa: F811
    text = "Bem-vindo à apresentação: ações, coração, pão e café — “ótimo”!"
    config = {
        "scenes": scenes_config(),
        "metadata": {"artist": "João Paulo"},
        "variants": {"pt": {"language": "pt-BR", "translations": "translations/pt.yaml"}},
    }
    files = {"translations/pt.yaml": "version: 1\nlanguage: pt-BR\nentries:\n  scenes.intro.beats.intro_b1.text:\n"
             f"    source: Welcome to the deck.\n    text: \"{text}\"\n"}
    root = write_project(tmp_path / "tr", config, files)
    project = Project.load(root, variant="pt")
    fake_stills(project)
    result = make_slides_pdf(project, notes=True)
    assert result.path == root / "exports" / "out_pt_preview_notes.pdf"
    reader = read(result.path)
    assert text in page_text(reader.pages[0])
    assert reader.metadata.author == "João Paulo" and reader.trailer["/Root"]["/Lang"] == "pt-BR"


def test_quality_and_width(meta_project: Path, tmp_path: Path) -> None:
    project = Project.load(meta_project)
    noise = Image.effect_noise((640, 360), 80).convert("RGB")  # hard to compress: sizes differ clearly
    for still in {s.still for s in deck_frames(project).slides}:
        noise.save(still)
    low = make_slides_pdf(project, quality=20, output=tmp_path / "low.pdf")
    high = make_slides_pdf(project, quality=95, output=tmp_path / "high.pdf")
    small = make_slides_pdf(project, quality=95, max_width=160, output=tmp_path / "small.pdf")
    assert low.bytes < high.bytes and small.bytes < high.bytes
    assert (small.width, small.height) == (160, 90)


def test_options_are_checked(meta_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.load(meta_project)
    for kwargs, message in [
        ({"image_format": "webp"}, "--image-format must be one of jpeg, png for a PDF deck"),
        ({"quality": 101}, "--quality must be between 1 and 100"),
        ({"max_width": 100}, "--max-width must be at least 160 pixels"),
        ({"paper": "a3"}, "--paper must be one of a4, letter"),
        ({"output": meta_project / "deck.html"}, "--output must be a .pdf file"),
        ({"mode": "scene", "per_beat": 2}, "--per-beat is for --mode beat"),
    ]:
        with pytest.raises(VidgenError, match=re.escape(message)):
            make_slides_pdf(project, **kwargs)
    real_import = builtins.__import__

    def no_fpdf(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fpdf":
            raise ImportError("no fpdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "fpdf")
    monkeypatch.setattr(builtins, "__import__", no_fpdf)
    with pytest.raises(VidgenError, match=re.escape('pip install "vidgen[pdf]"')):
        make_slides_pdf(project)


def test_cli(meta_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, doc, _ = run_json(["slides", str(meta_project), "--format", "pdf", "--json", "--notes", "--title-page", "--paper", "letter"], capsys)
    assert code == 0 and doc["command"] == "slides" and doc["output_format"] == "pdf"
    assert (doc["pages"], doc["notes"], doc["title_page"], doc["paper"], doc["bookmarks"]) == (6, True, True, "letter", 8)
    assert (doc["image_format"], doc["quality"], doc["thumbnail"]) == ("jpeg", 85, None)
    assert len(doc["slides"]) == 5 and doc["slides"][2]["notes"].startswith("Second point.")
    assert Path(doc["path"]).name == "out_preview_notes.pdf" and doc["bytes"] == Path(doc["path"]).stat().st_size
    documented("output_format", "pages", "title_page", "paper", "bookmarks", "thumbnail")
    code, doc, _ = run_json(["slides", str(meta_project), "--json"], capsys)
    assert code == 0 and doc["output_format"] == "html" and doc["image_format"] == "webp" and doc["quality"] == 80
    # human output
    assert main(["slides", str(meta_project), "--format", "pdf", "--quality", "70"]) == 0
    out = capsys.readouterr().out
    assert "(5 slides from 6 stills, 1 alike merged, 5 pages" in out
    assert "pictures: 96x54 jpeg q70; a slide per page; 7 bookmarks" in out
    # options of the other format
    for argv, message in [
        (["--format", "pdf", "--audio"], "--audio: only for the HTML deck"),
        (["--format", "pdf", "--separate"], "--separate: only for the HTML deck"),
        (["--notes"], "--notes: only for the PDF deck"),
        (["--title-page", "--paper", "a4"], "--title-page, --paper: only for the PDF deck"),
        (["--format", "pdf", "--image-format", "webp"], "--image-format must be one of jpeg, png"),
    ]:
        code, doc, _ = run_json(["slides", str(meta_project), "--json", *argv], capsys)
        assert code == 1 and message in doc["error"]["message"]


def test_pdf_reads_as_pictures(meta_project: Path) -> None:
    """The slide pictures come back out of the PDF at their size."""
    reader = read(make_slides_pdf(Project.load(meta_project), image_format="png").path)
    images = reader.pages[1].images
    assert len(images) == 1
    with Image.open(io.BytesIO(images[0].data)) as image:
        assert image.size == (96, 54) and image.convert("RGB").getpixel((5, 5)) == (30, 200, 30)
