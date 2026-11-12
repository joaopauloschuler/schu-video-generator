"""Step 338: the font files in a project's ``fonts/`` folder are used by the whole video
(DESIGN.md §119): read with fontTools, registered for Pango, declared to ``web`` pages, in the
render fingerprint; and the warning for a refused Google Fonts request names the family.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from vidgen import fonts
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.web.entry import WebEntry
from vidgen.web.page import FONT_RECIPE, WebPage, google_font_families, google_font_message

FAMILY = "Vidgen Test Wide"
#: The advance of the test font's "A" in em: far wider than any real font's, so a text's width
#: tells whether the test font drew it.
A_ADVANCE_EM = 2.0


def make_font(path: Path, family: str = FAMILY, *, weight: int = 400, italic: bool = False, style: str | None = None,
              wght: tuple[int, int] | None = None) -> Path:
    """Write a tiny valid font at ``path`` (``.notdef`` and a box for "A"; a ``.woff`` suffix
    writes WOFF). ``style``: a typographic style such as ``Medium`` (the legacy family name is
    then ``<family> <style>``, as in real static files); ``wght``: a variable font's weight range."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    pen = TTGlyphPen(None)
    for point in ((100, 0), (100, 700), (900, 700), (900, 0)):
        (pen.moveTo if point == (100, 0) else pen.lineTo)(point)
    pen.closePath()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({ord("A"): "A"})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (int(1000 * A_ADVANCE_EM), 100)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    names = {"familyName": family, "styleName": "Bold" if weight == 700 else "Regular"}
    if style is not None:
        names = {"familyName": f"{family} {style}", "styleName": "Regular", "typographicFamily": family, "typographicSubfamily": style}
    builder.setupNameTable(names)
    builder.setupOS2(usWeightClass=weight, fsSelection=0x01 if italic else 0x40)
    builder.setupPost()
    if wght is not None:
        builder.setupFvar([("wght", wght[0], weight, wght[1], "Weight")], [])
    if path.suffix == ".woff":
        builder.font.flavor = "woff"
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)
    return path


def test_fonttools_is_a_declared_dependency() -> None:
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert '"fonttools>=' in text.split("dependencies = [", 1)[1].split("\n]", 1)[0]


def test_family_weight_and_style_come_from_the_file(tmp_path: Path) -> None:
    folder = tmp_path / "fonts"
    make_font(folder / "a-regular.ttf")
    make_font(folder / "sub" / "b-bold.otf", weight=700)
    make_font(folder / "c-medium-italic.ttf", weight=500, italic=True, style="Medium Italic")
    make_font(folder / "d-variable.ttf", wght=(300, 700))
    make_font(folder / "e.woff", "Other Family")
    (folder / "OFL.txt").write_text("licence", encoding="utf-8")
    read = {font.rel: (font.family, font.weight, font.italic) for font in fonts.project_fonts(tmp_path)}
    assert read == {
        "fonts/a-regular.ttf": (FAMILY, (400, 400), False),
        "fonts/sub/b-bold.otf": (FAMILY, (700, 700), False),
        "fonts/c-medium-italic.ttf": (FAMILY, (500, 500), True),   # the typographic family, not "<family> Medium Italic"
        "fonts/d-variable.ttf": (FAMILY, (300, 700), False),
        "fonts/e.woff": ("Other Family", (400, 400), False),
    }
    assert fonts.project_fonts(tmp_path / "nowhere") == []


def test_a_broken_font_file_is_named(tmp_path: Path) -> None:
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "bad.ttf").write_text("not a font", encoding="utf-8")
    with pytest.raises(VidgenError, match=r"fonts/bad\.ttf: not a font file vidgen can read .*\.ttf, \.otf or \.woff"):
        fonts.project_fonts(tmp_path)


def test_a_woff2_file_is_not_read_and_validate_says_so(make_project: Any) -> None:
    from vidgen.cli import validate_warnings

    root = make_project()
    (root / "fonts").mkdir()
    (root / "fonts" / "alone.woff2").write_bytes(b"wOF2")
    (root / "fonts" / "paired.woff2").write_bytes(b"wOF2")
    make_font(root / "fonts" / "paired.woff")
    assert [font.rel for font in fonts.project_fonts(root)] == ["fonts/paired.woff"]
    warnings = [w for w in validate_warnings(Project.load(root)) if "woff2" in w]
    assert len(warnings) == 1 and warnings[0].startswith("fonts/alone.woff2: vidgen does not read .woff2 font files")
    assert "@font-face" in warnings[0] and ".ttf, .otf or .woff" in warnings[0]


def test_fonts_are_registered_and_a_woff_through_a_copy(tmp_path: Path) -> None:
    from fontTools.ttLib import TTFont

    import manimpango

    family = "Vidgen Test Registered"
    make_font(tmp_path / "fonts" / "r.ttf", family)
    make_font(tmp_path / "fonts" / "b.woff", family, weight=700)
    build = tmp_path / "build"
    assert [font.rel for font in fonts.register_project_fonts(tmp_path, build)] == ["fonts/b.woff", "fonts/r.ttf"]
    copies = list((build / "fonts").iterdir())
    assert len(copies) == 1 and copies[0].name.startswith("b-") and copies[0].suffix == ".ttf"
    with TTFont(copies[0]) as copy:
        assert copy.flavor is None and copy["name"].getDebugName(1) == family
    assert family in manimpango.list_fonts()
    assert fonts.font_file(family) == tmp_path / "fonts" / "r.ttf" and fonts.font_file(family, bold=True) == copies[0]
    assert fonts.font_file("Inter", bold=True) == fonts.bundled_font_file("Inter", bold=True) and fonts.font_file("No Such") is None
    stamp = copies[0].stat().st_mtime_ns
    fonts.register_project_fonts(tmp_path, build)
    assert copies[0].stat().st_mtime_ns == stamp and len(list((build / "fonts").iterdir())) == 1


def test_activating_a_project_registers_its_fonts(make_project: Any) -> None:
    from vidgen import extensions

    root = make_project()
    make_font(root / "fonts" / "x.ttf", "Vidgen Test Active")
    extensions.activate(Project.load(root))
    assert fonts.font_file("Vidgen Test Active") == root / "fonts" / "x.ttf"
    other = make_project(folder="other")
    extensions.activate(Project.load(other))
    assert fonts.font_file("Vidgen Test Active") is None   # another project's file is not handed out


def test_the_fingerprint_and_the_text_cache_follow_the_font_files(make_project: Any) -> None:
    from vidgen.render.fingerprint import fingerprint_digest, fingerprint_inputs
    from vidgen.render.worker import _text_cache_dir

    root = make_project()
    project = Project.load(root)
    scene_id = project.config.scenes[0].id
    plain = fingerprint_inputs(project, scene_id)
    texts = root / "build" / "texts"
    assert "fonts" not in plain and _text_cache_dir(texts, scene_id, root) == texts / scene_id
    font = make_font(root / "fonts" / "x.ttf")
    (root / "fonts" / "OFL.txt").write_text("licence", encoding="utf-8")
    with_font = fingerprint_inputs(project, scene_id)
    assert list(with_font["fonts"]) == ["fonts/x.ttf"] and fingerprint_digest(with_font) != fingerprint_digest(plain)
    first = _text_cache_dir(texts, scene_id, root)
    assert first.parent == texts and first.name.startswith(f"{scene_id}.") and first != texts / scene_id
    first.mkdir(parents=True)
    make_font(font, weight=700)
    changed = fingerprint_inputs(project, scene_id)
    assert fingerprint_digest(changed) != fingerprint_digest(with_font)
    second = _text_cache_dir(texts, scene_id, root)
    assert second != first and not first.exists()   # the texts laid out with the old file are gone


# ----- web pages ---------------------------------------------------------------------------------


def _page_theme(root: Path) -> dict[str, Any]:
    from vidgen.config import ThemeConfig
    from vidgen.theme import Theme
    from vidgen.web.inputs import page_theme

    return page_theme(Theme(ThemeConfig(font=FAMILY)), 1080 / (72 * 8), fonts.project_fonts(root))


def test_a_page_is_given_a_font_face_per_file(tmp_path: Path) -> None:
    from vidgen.web.inputs import declared_families, theme_css, theme_properties

    make_font(tmp_path / "fonts" / "Wide[wght].ttf", wght=(300, 700))
    make_font(tmp_path / "fonts" / "wide italic.woff", italic=True)
    theme = _page_theme(tmp_path)
    assert theme["font_files"] == [
        {"family": FAMILY, "weight": "300 700", "style": "normal", "url": "/fonts/Wide%5Bwght%5D.ttf"},
        {"family": FAMILY, "weight": "400", "style": "italic", "url": "/fonts/wide%20italic.woff"},
    ]
    css = theme_css(theme)
    assert f'@font-face {{ font-family: "{FAMILY}"; src: url("/fonts/Wide%5Bwght%5D.ttf"); font-weight: 300 700; font-style: normal; }}' in css
    assert 'src: url("/fonts/wide%20italic.woff"); font-weight: 400; font-style: italic;' in css
    assert theme_properties(theme)["--vidgen-font-body"] == f'"{FAMILY}", sans-serif'
    assert declared_families(theme) == {FAMILY, "Source Serif 4", "JetBrains Mono NL"}
    assert _page_theme(tmp_path / "nowhere")["font_files"] == []


def test_google_fonts_urls_name_their_families() -> None:
    assert google_font_families("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700&family=Lora&display=swap") == ["Space Grotesk", "Lora"]
    assert google_font_families("https://fonts.googleapis.com/css?family=Lora:400,700|Open+Sans") == ["Lora", "Open Sans"]
    assert google_font_families("https://fonts.gstatic.com/s/spacegrotesk/v16/abc.woff2") == ["spacegrotesk"]
    assert google_font_families("https://fonts.googleapis.com/icon") == []
    assert google_font_families("https://cdn.example/fonts.googleapis.com/x.css?family=Lora") is None
    message = google_font_message("hero", "Space Grotesk", False)
    assert message == ("scene 'hero': the page asks Google Fonts for \"Space Grotesk\", but the internet is off during a render, so that "
                       "text is drawn in a fallback font. Put the font's .ttf, .otf or .woff file in the project's fonts/ folder and "
                       f"remove the link to Google Fonts ({FONT_RECIPE}).")
    assert "vidgen guide web" in FONT_RECIPE and "Using another font" in FONT_RECIPE
    assert "already gives the page this family: remove the link" in google_font_message("hero", "Inter", True)
    assert "asks Google Fonts for a font," in google_font_message("hero", None, False)


class _Route:
    """A refused request as ``WebPage._serve`` sees it."""

    def __init__(self, url: str) -> None:
        self.request = type("Request", (), {"url": url})()
        self.aborted = False

    def abort(self, reason: str) -> None:
        self.aborted = True


def test_one_warning_per_family_asked_of_google_fonts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    make_font(tmp_path / "fonts" / "x.ttf")
    page = WebPage(tmp_path, WebEntry("page", "p.html"), scene_id="hero", size=(64, 36), fps=5, frames=1, theme=_page_theme(tmp_path))
    urls = ["https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400&family=Vidgen+Test+Wide",
            "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700",
            "https://fonts.gstatic.com/s/spacegrotesk/v16/abc.woff2",
            "https://cdn.example/lib.js"]
    with caplog.at_level(logging.WARNING, logger="vidgen.web"):
        routes = [_Route(url) for url in urls]
        for route in routes:
            page._serve(route)
    messages = [record.getMessage() for record in caplog.records]
    assert all(route.aborted for route in routes) and page.refused == urls
    assert len(messages) == 3
    assert 'asks Google Fonts for "Space Grotesk", but the internet is off during a render, so that text' in messages[0]
    assert f'asks Google Fonts for "{FAMILY}"' in messages[1] and "already gives the page this family" in messages[1]
    assert messages[2].startswith("scene 'hero': refused https://cdn.example/lib.js")


@pytest.mark.slow
@pytest.mark.render
def test_a_page_draws_text_in_a_project_font(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """In Chromium: the family named in CSS and the theme's role both draw with the file from
    ``fonts/`` (the test font's "A" is 2 em wide), a ``.woff`` too; the files are recorded."""
    from vidgen.browser import chromium

    if chromium.missing_dependency() is not None:
        pytest.skip("Playwright or its Chromium is not installed")
    make_font(tmp_path / "fonts" / "wide.ttf")
    make_font(tmp_path / "fonts" / "other.woff", "Vidgen Test Woff")
    (tmp_path / "p.html").write_text(
        '<link href="https://fonts.googleapis.com/css2?family=Vidgen+Test+Wide&family=Lora" rel="stylesheet">'
        f'<style>span {{ font-size: 10px }}</style><span id="css" style=\'font-family: "{FAMILY}"\'>AAAA</span>'
        '<span id="role" style="font-family: var(--vidgen-font-body)">AAAA</span>'
        '<span id="woff" style=\'font-family: "Vidgen Test Woff"\'>AAAA</span><span id="plain">AAAA</span>', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="vidgen.web"), \
            WebPage(tmp_path, WebEntry("page", "p.html"), scene_id="w", size=(320, 90), fps=5, frames=1, theme=_page_theme(tmp_path)) as page:
        page.frame(0)
        widths = page._page.evaluate("Object.fromEntries([...document.querySelectorAll('span')].map(e => [e.id, e.getBoundingClientRect().width]))")
        loaded = page.loaded
    wide = 4 * A_ADVANCE_EM * 10
    assert widths["css"] == widths["role"] == widths["woff"] == wide and widths["plain"] < wide / 2
    assert loaded["fonts/wide.ttf"] is not None and loaded["fonts/other.woff"] is not None
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 2 and "already gives the page this family" in messages[0] and 'for "Lora", but the internet is off' in messages[1]
