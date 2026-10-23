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


# ----- Step 195: inspector, step grid, the score file typed -----------------------------------------


def test_inspector_sliders_instrument_and_effects(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    page.click("#tracks .track[data-name=bass] .name")
    assert page.input_value("#insp-instrument") == "synth_bass" and page.locator("#g-sound .slider-row").count() == 5  # 3 settings, volume, pan
    # a slider drag is one version, written on release
    box = page.locator("#set-tone").bounding_box()
    page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2, steps=10)
    page.mouse.up()
    wait_idle(page, 2)
    assert len(app.session.versions) == 2 and "settings: {tone: " in current_text(app)
    # a typed value outside the range is refused with the score's message, by the control
    page.fill("#set-decay-num", "9")
    page.press("#set-decay-num", "Enter")
    page.wait_for_selector("#pb-sound:not([hidden])")
    assert "out of range" in page.text_content("#pb-sound") and len(app.session.versions) == 2
    page.click("#g-sound .reset[data-reset=set-tone]")  # reset: the key goes, the default plays
    wait_idle(page, 3)
    assert "settings" not in current_text(app).split("bass:")[1]
    # the instrument: the change is explained first, then made
    page.select_option("#insp-instrument", "pluck")
    page.wait_for_selector("#insp-change-ok")
    assert "synth_bass → pluck" in page.text_content(".change-card")
    page.click("#insp-change-ok")
    wait_idle(page, 4)
    assert "instrument: pluck" in current_text(app) and app.session.versions[-1].label == "bass: synth_bass → pluck"
    # effects: add an echo, change a field, then in section b only switch it off
    page.select_option("#insp-add-fx", "echo")
    wait_idle(page, 5)
    page.fill("#fx-echo-repeats-num", "4")
    page.press("#fx-echo-repeats-num", "Enter")
    wait_idle(page, 6)
    assert "echo: {delay: 0.75, feedback: 0.35, repeats: 4}" in current_text(app)
    page.click("#inspector .scope-tab[data-scope=b]")
    assert "b only" in page.text_content(".scope-banner")
    page.click("#inspector .fx-x[data-remove=echo]")
    wait_idle(page, 7)
    assert "sections: {b: {echo: none}}" in current_text(app)
    # a section switched off: the track rests there
    page.click("#inspector .scope-tab[data-scope='']")
    page.click("#inspector .sec-table input[data-plays=a]")
    wait_idle(page, 8)
    assert "rest: [a]" in current_text(app)
    assert page.errors == []


def test_step_grid_and_text_stay_in_step(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    page.click("#tracks .track[data-name=kick] .name")
    assert page.locator("#insp-grid .cell").count() == 16
    page.click("#cell-0-2")  # brush x on a rest: a hit
    wait_idle(page, 2)
    assert 'steps: "x.x. x... x... x..."' in current_text(app)
    page.click("#cell-0-2")  # again: back to a rest
    wait_idle(page, 3)
    assert 'steps: "x... x... x... x..."' in current_text(app)
    # keys: an accent and a soft hit, one version for the burst
    page.focus("#cell-0-1")
    page.keyboard.press("X")
    page.keyboard.press("o")
    wait_idle(page, 4)
    page.wait_for_timeout(900)
    wait_idle(page, 4)
    assert 'steps: "xXo. x... x... x..."' in current_text(app) and len(app.session.versions) == 4
    page.click("#insp-add-bar")
    wait_idle(page, 5)
    assert 'steps: "xXo. x... x... x... | xXo. x... x... x..."' in current_text(app)  # a copy of the last bar
    page.select_option("#g-steps select.count[data-bar='1']", "8")  # in eighths: the steps on the new grid stay
    wait_idle(page, 6)
    assert 'steps: "xXo. x... x... x... | xo x. x. x."' in current_text(app)
    assert page.locator("#insp-grid .bar-row").count() == 2 and page.locator("#insp-grid .bar-row[data-bar='1'] .cell").count() == 8
    # the text field: typed steps show in the grid, Enter keeps them
    page.fill("#insp-steps", "x.x.")
    page.wait_for_function("document.querySelectorAll('#insp-grid .cell').length === 4")
    page.press("#insp-steps", "Enter")
    wait_idle(page, 7)
    assert 'steps: "x.x."' in current_text(app)
    # the pitched bass: a degree from the palette
    page.click("#tracks .track[data-name=bass] .name")
    page.click("#g-steps .brush[data-brush='5']")
    page.click("#cell-0-1")
    wait_idle(page, 8)
    assert 'steps: "151. 1.1. 1.1. 1.1."' in current_text(app)
    assert page.errors == []


def test_score_file_typed_both_ways(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    type_yaml = "(t) => { const el = document.getElementById('yaml-input'); el.value = t; el.dispatchEvent(new Event('input')); }"
    page.click("#yaml-input")
    page.evaluate(type_yaml, TINY.replace("instrument: kick", "instrument: kik"))
    page.wait_for_selector("#yaml-problems:not([hidden])")
    assert "did you mean 'kick'" in page.text_content("#yaml-problems") and "line 7" in page.text_content("#yaml-problems")
    assert page.evaluate("document.body.dataset.draft") == "1" and page.locator("#yaml .ln.bad").count() == 1
    page.wait_for_timeout(900)
    assert len(app.session.versions) == 1  # a draft with problems is never a version
    page.click("#yaml-revert")
    assert page.evaluate("document.body.dataset.draft") is None and page.input_value("#yaml-input") == TINY
    # valid text: a version after 0.8 s, and the controls follow
    page.evaluate(type_yaml, TINY.replace("tempo: 120", "tempo: 90").replace("synth_bass", "sub"))
    wait_idle(page, 2)
    assert current_text(app) == TINY.replace("tempo: 120", "tempo: 90").replace("synth_bass", "sub")
    assert page.input_value("#f-tempo") == "90"
    page.click("#tracks .track[data-name=bass] .name")
    assert page.input_value("#insp-instrument") == "sub"
    # and a control's edit shows in the score file
    page.fill("#insp-transpose", "2")
    page.press("#insp-transpose", "Enter")
    wait_idle(page, 3)
    assert "transpose: 2" in page.input_value("#yaml-input") and "transpose: 2" in page.text_content("#yaml")
    assert page.errors == []
