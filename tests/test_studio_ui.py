"""``vidgen studio`` in a browser (Step 193, DESIGN.md §94): headless Chromium through Playwright
drives the page served by a studio server on a background thread. Skipped when Playwright or
its Chromium is missing. Kept few and fast: scores of a few seconds, one preset render."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from vidgen.studio_app.app import StudioApp
from vidgen.studio_app.server import StudioServer, start_in_thread

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.ui

TINY = """\
title: Tiny
key: A minor
tempo: 120
progression: "i VI"
sections: [{name: a, bars: 1}, {name: b, bars: 1}]
tracks:
  kick: {instrument: kick, steps: "x... x... x... x..."}
  bass: {instrument: synth_bass, steps: "1.1. 1.1. 1.1. 1.1."}
"""


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[StudioApp, StudioServer]]:
    app = StudioApp(None, studio=tmp_path_factory.mktemp("studio"))
    server, thread = start_in_thread(app)
    yield app, server
    server.shutdown()
    server.server_close()
    thread.join(5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as p:
        try:
            chromium = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        except Exception as exc:  # noqa: BLE001 - no browser installed: nothing to test with
            pytest.skip(f"Chromium for Playwright is not available: {exc}")
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    # bypass_csp: Playwright's waits evaluate strings, which the page's CSP (no eval) refuses
    context = browser.new_context(bypass_csp=True, viewport={"width": 1400, "height": 860})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.errors = errors
    yield page
    context.close()


def wait_rendered(page: Any) -> None:
    page.wait_for_function("document.getElementById('status').textContent.startsWith('v1 ')", timeout=60_000)


def wait_idle(page: Any, version: int | None = None) -> None:
    """Wait until no edit or render is under way (and, given, version ``version`` is shown)."""
    page.wait_for_timeout(50)
    test = "!document.body.dataset.busy"
    if version is not None:
        test += f" && document.getElementById('version-name').textContent === 'v{version}'"
    page.wait_for_function(test, timeout=60_000)


def test_page_loads_the_open_session(studio: tuple[StudioApp, StudioServer], page: Any, tmp_path: Path) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_rendered(page)
    assert page.title() == "vidgen studio"
    assert page.locator("#preset-list li").count() == 17
    assert page.locator("#timeline .section").count() == 2
    assert page.locator("#tracks .track").count() == 2
    assert "title: Tiny" in page.text_content("#yaml")
    assert page.input_value("#f-tonic") == "A" and page.input_value("#f-mode") == "minor" and page.input_value("#f-tempo") == "120"
    assert page.locator("#chords .chord b").all_text_contents() == ["i", "VI"]
    assert page.locator("#chords .chord small").all_text_contents() == ["Am", "F"]
    page.screenshot(path=str(tmp_path / "studio.png"))
    assert page.errors == []


def test_choosing_a_preset_loads_and_renders_it(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    page.goto(server.url)
    wait_rendered(page)
    page.click("#preset-button")
    assert page.is_visible("#preset-list")
    assert "A soft rhythmic bed" in page.text_content("#preset-pulse")
    page.click("#preset-pulse")
    page.wait_for_function("document.getElementById('preset-name').textContent === 'pulse'")
    wait_rendered(page)
    assert app.session is not None and app.session.preset == "pulse"
    assert page.locator("#tracks .track").count() == 3
    assert "# Pulse" in page.text_content("#yaml")
    assert page.errors == []


def test_play_streams_the_render(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    audio: list[Any] = []
    page.on("request", lambda r: audio.append(r) if "/audio/" in r.url else None)
    page.goto(server.url)
    wait_rendered(page)
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 0.3", timeout=15_000)
    assert audio and all(r.url.endswith(".wav") for r in audio)
    assert any(r.headers.get("range", "").startswith("bytes=") for r in audio)  # streamed in ranges
    assert all(r.response() is not None and r.response().status in (200, 206) for r in audio if r.failure is None)
    assert page.get_attribute("#play", "aria-pressed") == "true"
    page.click("#stop")
    page.wait_for_function("document.getElementById('play').getAttribute('aria-pressed') === 'false'", timeout=5_000)
    assert page.evaluate("document.getElementById('audio').currentTime") == 0
    assert page.errors == []


# ----- Step 194: song strip, timeline, track list ------------------------------------------------


def current_text(app: StudioApp) -> str:
    assert app.session is not None and app.session.current is not None
    return app.session.text(app.session.current)


def test_song_strip_edits_tempo_and_chords(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    page.fill("#f-tempo", "96")
    page.press("#f-tempo", "Enter")
    wait_idle(page, 2)
    assert "tempo: 96" in current_text(app) and "tempo: 96" in page.text_content("#yaml")
    assert app.session.versions[-1].label == "tempo 96" and app.session.versions[-1].parent == 1
    # the chords: names follow the numerals while typing; a bad chord is shown and not kept
    page.click("#chords")
    page.fill("#chords-input", "i iv")
    page.wait_for_function("document.getElementById('chords-hint').textContent.includes('Am  Dm')")
    page.fill("#chords-input", "i qq")
    page.wait_for_function("document.getElementById('chords-hint').classList.contains('error')")
    assert "'qq' is not a chord" in page.text_content("#chords-hint")
    page.fill("#chords-input", "i iv")
    page.press("#chords-input", "Enter")
    wait_idle(page, 3)
    assert page.locator("#chords .chord small").all_text_contents() == ["Am", "Dm"]
    assert 'progression: "i iv"' in current_text(app)
    assert page.errors == []


def test_timeline_loops_a_section_drags_an_edge_and_draws_energy(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    assert page.locator("#energy path.line").count() == 1
    page.click("#timeline .section[data-name=b] .sec-name")
    wait_idle(page)
    assert page.get_attribute("#timeline .section[data-name=b] .sec-name", "aria-pressed") == "true"
    assert page.evaluate("document.getElementById('audio').src").endswith("-b.wav")
    assert page.evaluate("document.getElementById('audio').loop") is True
    assert page.input_value("#loop") == "b" and page.input_value("#sec-name") == "b"
    # drag a's right edge one bar to the right: a lasts 2 bars
    edge = page.locator("#timeline .section[data-name=a] .edge").bounding_box()
    width = page.locator("#timeline").bounding_box()["width"]
    page.mouse.move(edge["x"] + 5, edge["y"] + 20)
    page.mouse.down()
    page.mouse.move(edge["x"] + 5 + width / 2 * 1.05, edge["y"] + 20, steps=5)
    page.mouse.up()
    wait_idle(page, 2)
    assert "{name: a, bars: 2}" in current_text(app)
    # the section bar renames b everywhere
    page.fill("#sec-name", "lift")
    page.press("#sec-name", "Tab")
    wait_idle(page, 3)
    assert "{name: lift, bars: 1}" in current_text(app)
    assert page.input_value("#loop") == "lift"
    assert page.errors == []


def test_track_list_mute_volume_pattern_add_and_delete(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    # mute: a listening mix, the score unchanged
    page.click("#tracks .track[data-name=kick] .mute")
    wait_idle(page)
    assert ".m" in page.evaluate("document.getElementById('audio').src") and len(app.session.versions) == 1
    assert "without kick" in page.text_content("#mute-note")
    page.click("#tracks .track[data-name=kick] .mute")
    wait_idle(page)
    # volume: click near the bar's left end
    box = page.locator("#tracks .track[data-name=bass] .vol").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.25, box["y"] + box["height"] / 2)
    wait_idle(page, 2)
    assert "volume: -21" in current_text(app)
    # the steps: a bad symbol is shown under the row and not kept; a good one is
    page.click("#tracks .track[data-name=kick] .pattern")
    page.fill("#tracks .pattern-input", "x..q x... x... x...")
    page.wait_for_selector("#tracks .track[data-name=kick] .problem:not([hidden])")
    assert "unknown symbol 'q'" in page.text_content("#tracks .track[data-name=kick] .problem")
    page.fill("#tracks .pattern-input", "x.x. x... x... x...")
    page.press("#tracks .pattern-input", "Enter")
    wait_idle(page, 3)
    assert 'steps: "x.x. x... x... x..."' in current_text(app)
    # [+ track]: an instrument from the menu, with a default pattern
    page.click("#add-track")
    page.click("#instrument-bell")
    wait_idle(page, 4)
    assert page.locator("#tracks .track").count() == 3 and page.get_attribute("#tracks .track[data-name=bell]", "aria-selected") == "true"
    assert "  bell:\n    instrument: bell\n" in current_text(app)
    page.hover("#tracks .track[data-name=bell]")
    page.click("#tracks .track[data-name=bell] .del")
    wait_idle(page, 5)
    assert page.locator("#tracks .track").count() == 2 and "bell" not in current_text(app)
    assert page.errors == []
