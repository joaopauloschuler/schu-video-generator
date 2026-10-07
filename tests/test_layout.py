"""Layout helpers: wrapping, fitting, beat distribution, number formatting, LaTeX detection."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from manim import Square, tempconfig

from vidgen import layout
from vidgen.errors import VidgenError
from vidgen.layout import (
    auto_format,
    check_format,
    distribute,
    fit_text,
    format_value,
    measure_text,
    nice_ticks,
    normalize_text,
    shrink_to_fit,
    wrap_lines,
)
from vidgen.theme import Theme

# ----- wrapping ------------------------------------------------------------------------------


def test_normalize_text_collapses_spaces_keeps_breaks() -> None:
    assert normalize_text("  a   b\t c \n\n  d  ") == "a b c\nd"


def test_wrap_lines_greedy() -> None:
    assert wrap_lines("one two three four", 9) == ["one two", "three", "four"]


def test_wrap_lines_honours_explicit_breaks() -> None:
    assert wrap_lines("a b\nc d", 10) == ["a b", "c d"]


def test_wrap_lines_never_splits_words_and_keeps_indices() -> None:
    text = "tiny supercalifragilistic word"
    lines = wrap_lines(text, 5)
    assert lines == ["tiny", "supercalifragilistic", "word"]
    assert len("\n".join(lines)) == len(normalize_text(text))


def test_wrap_lines_rejects_zero_width() -> None:
    with pytest.raises(ValueError):
        wrap_lines("x", 0)


def test_highlight_ranges_cover_every_occurrence_across_breaks() -> None:
    t2c = layout._highlight_ranges("ab cd\nab", {"ab": "#FF0000", "d ab": "#00FF00", "": "#000000"})
    assert t2c == {"[0:2]": "#FF0000", "[6:8]": "#FF0000", "[4:8]": "#00FF00"}


# ----- fitting (builds Text, no rendering) ---------------------------------------------------------


@pytest.fixture
def text_media(tmp_path: Path) -> Iterator[None]:
    with tempconfig({"media_dir": str(tmp_path / "media"), "verbosity": "ERROR"}):
        yield


def test_fit_text_wraps_to_width(text_media: None) -> None:
    block = fit_text("the quick brown fox jumps over the lazy dog " * 3, 4.0, theme=Theme())
    assert block.width <= 4.0 + 1e-6
    assert len(block.submobjects) >= 3


def test_fit_text_single_short_line_unchanged(text_media: None) -> None:
    block = fit_text("Hello", 10.0, theme=Theme())
    assert len(block.submobjects) == 1


@pytest.mark.slow
def test_fit_text_fits_height_by_shrinking(text_media: None) -> None:
    long = "word " * 120
    block = fit_text(long, 6.0, 2.0, theme=Theme())
    assert block.height <= 2.0 + 1e-6 and block.width <= 6.0 + 1e-6


def test_fit_text_long_word_is_scaled_not_split(text_media: None) -> None:
    block = fit_text("https://example.com/a/very/long/path/without/spaces", 2.0, theme=Theme())
    assert block.width <= 2.0 + 1e-6 and len(block.submobjects) == 1


def test_fit_text_squeeze_prefers_one_line(text_media: None) -> None:
    text = "a moderately long line of text"
    wrapped = fit_text(text, 4.0, theme=Theme())
    natural = fit_text(text, 100.0, theme=Theme()).width
    squeezed = fit_text(text, natural / 1.2, squeeze=1.3, theme=Theme())
    assert len(wrapped.submobjects) > 1 and len(squeezed.submobjects) == 1


def test_fit_text_balance_evens_out_lines(text_media: None) -> None:
    text = "Manual reports every single week"
    greedy = fit_text(text, 5.0, size=32, theme=Theme())
    even = fit_text(text, 5.0, size=32, theme=Theme(), balance=True)
    assert len(greedy) == len(even) == 2
    assert even.width < greedy.width and even[-1].width > greedy[-1].width   # no lone last word
    assert len(fit_text("Short", 5.0, theme=Theme(), balance=True)) == 1


def test_measure_text_estimates_fit_text(text_media: None) -> None:
    theme = Theme()
    for text, width in [("the quick brown fox jumps over the lazy dog " * 2, 4.0), ("Apollo 11", 3.0), ("one two three", 1.5)]:
        for balance in (False, True):
            m = measure_text(text, width * 0.97, size=32, theme=theme, balance=balance)
            built = fit_text(text, width, size=32, theme=theme, balance=balance)
            assert len(built) <= len(m.lines) <= len(built) + 1
            assert m.height == pytest.approx(built.height, rel=0.15) and m.fits
    long = measure_text("https://example.com/a/very/long/path", 2.0, theme=theme)
    assert not long.fits and long.lines == ["https://example.com/a/very/long/path"] and long.width > 2.0
    with pytest.raises(VidgenError, match="text is empty"):
        measure_text("  ", 2.0, theme=theme)


def test_fit_text_highlight_colors_glyphs(text_media: None) -> None:
    block = fit_text("plain red plain", 20.0, highlights={"red": "#FF0000"}, theme=Theme())
    colors = [g.get_color().to_hex().upper() for g in block[0]]
    assert colors.count("#FF0000") == 3


def test_fit_text_empty_is_an_error(text_media: None) -> None:
    with pytest.raises(VidgenError):
        fit_text("   ", 5.0, theme=Theme())


def test_shrink_to_fit_never_enlarges() -> None:
    sq = Square(side_length=2)
    shrink_to_fit(sq, 10, 10)
    assert sq.width == pytest.approx(2)
    shrink_to_fit(sq, 1, 10)
    assert sq.width == pytest.approx(1)
    shrink_to_fit(sq, None, 0.5)
    assert sq.height == pytest.approx(0.5)


# ----- distribution of reveal steps over beats ------------------------------------------------------


@pytest.mark.parametrize(
    ("steps", "beats", "expected"),
    [
        (3, 3, [[0], [1], [2]]),
        (2, 4, [[0], [1], [], []]),
        (5, 2, [[0, 1, 2], [3, 4]]),
        (7, 3, [[0, 1, 2], [3, 4], [5, 6]]),
        (4, 1, [[0, 1, 2, 3]]),
        (3, 0, [[0, 1, 2]]),
        (0, 2, [[], []]),
    ],
)
def test_distribute(steps: int, beats: int, expected: list[list[int]]) -> None:
    plan = distribute(steps, beats)
    assert plan == expected
    assert [i for b in plan for i in b] == list(range(steps))


def test_distribute_balanced_for_many_cases() -> None:
    for steps in range(1, 30):
        for beats in range(1, 10):
            sizes = [len(b) for b in distribute(steps, beats)]
            assert len(sizes) == beats and sum(sizes) == steps
            if steps >= beats:
                assert max(sizes) - min(sizes) <= 1 and sizes == sorted(sizes, reverse=True)


def test_distribute_rejects_negative() -> None:
    with pytest.raises(ValueError):
        distribute(-1, 2)


# ----- numbers -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lo", "hi", "n", "expected"),
    [
        (0, 10, 6, [0, 2, 4, 6, 8, 10]),
        (1.41, 2.25, 6, [1.4, 1.6, 1.8, 2.0, 2.2, 2.4]),
        (1.41, 2.25, 5, [1.25, 1.5, 1.75, 2.0, 2.25]),
        (-12, 30, 6, [-20, -10, 0, 10, 20, 30]),
        (5, 5, 5, [4.5, 4.75, 5.0, 5.25, 5.5]),
    ],
)
def test_nice_ticks(lo: float, hi: float, n: int, expected: list[float]) -> None:
    ticks = nice_ticks(lo, hi, n)
    assert ticks == pytest.approx(expected)
    assert ticks[0] <= lo and ticks[-1] >= hi and 2 <= len(ticks) <= n


def test_nice_ticks_swapped_bounds() -> None:
    assert nice_ticks(10, 0, 6) == nice_ticks(0, 10, 6)


@pytest.mark.parametrize(
    ("values", "fmt"),
    [([1, 2, 3], "{:,.0f}"), ([1.5, 2], "{:,.1f}"), ([0.25, 3.1], "{:,.2f}"), ([0.12345], "{:,.2f}"), ([1200.0], "{:,.0f}")],
)
def test_auto_format(values: list[float], fmt: str) -> None:
    assert auto_format(values) == fmt


@pytest.mark.parametrize(
    ("value", "fmt", "unit", "text"),
    [
        (1234.5, None, "", "1,234"),
        (12.5, "{:.1f}", " ms", "12.5 ms"),
        (0.5, "{:.0%}", "", "50%"),
        (3, "{:,.2f}", "%", "3.00%"),
        (-4.25, auto_format([-4.25]), "", "-4.25"),
    ],
)
def test_format_value(value: float, fmt: str | None, unit: str, text: str) -> None:
    assert format_value(value, fmt, unit) == text


def test_format_value_bad_pattern() -> None:
    with pytest.raises(VidgenError, match="invalid number format"):
        format_value(1, "{:q}")
    with pytest.raises(ValueError):
        check_format("{0} {1}")
    assert check_format("{:.1f}x") == "{:.1f}x"


# ----- LaTeX ---------------------------------------------------------------------------------------


def test_require_latex_mentions_miktex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layout.shutil, "which", lambda name: None)
    assert not layout.latex_available()
    assert "dvisvgm" in layout.missing_latex_tools()
    with pytest.raises(VidgenError, match="MiKTeX") as info:
        layout.require_latex("scene 'eq'")
    assert "scene 'eq' needs LaTeX" in str(info.value)


def test_require_latex_ok_when_tools_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(layout.shutil, "which", lambda name: f"/usr/bin/{name}")
    layout.require_latex("x")
    assert layout.latex_available()
