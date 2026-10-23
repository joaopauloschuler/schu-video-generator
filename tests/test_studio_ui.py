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


# ----- Step 196: fast re-render, playing on, under narration, meters ------------------------------------

LONGER = TINY.replace("{name: a, bars: 1}, {name: b, bars: 1}", "{name: a, bars: 4}, {name: b, bars: 4}")  # 16 s


def wait_swapped(page: Any, swaps: int) -> None:
    page.wait_for_function(f"!document.body.dataset.switching && document.body.dataset.swaps === '{swaps}'", timeout=30_000)


def test_edits_mutes_and_narration_play_on_at_the_same_moment(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=LONGER)
    page.goto(server.url)
    wait_idle(page, 1)
    assert page.is_enabled("#narration")
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 1.0", timeout=15_000)
    # the meters show each track's own audio: levels while it plays
    page.wait_for_function("[...document.querySelectorAll('#tracks .meter')].every(m => m.dataset.db !== '' && Number(m.dataset.db) > -60)")
    before = page.evaluate("document.getElementById('audio').currentTime")
    # a volume edit while playing: the kept stem at the new volume, remixed, brought in at the moment playing
    box = page.locator("#tracks .track[data-name=bass] .vol").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.25, box["y"] + box["height"] / 2)
    wait_idle(page, 2)
    wait_swapped(page, 1)
    after = page.evaluate("document.getElementById('audio').currentTime")
    assert before < after < before + 10  # played on: not from the start
    assert abs(int(page.evaluate("document.body.dataset.swapDrift"))) < 150  # the two sources lined up (ms)
    assert "bass at the new volume" in page.text_content("#status") and page.get_attribute("#play", "aria-pressed") == "true"
    assert page.evaluate("document.getElementById('audio').src").endswith(f"{app.render()['key']}.wav")
    # one track's steps: only that track is rendered again
    page.click("#tracks .track[data-name=kick] .pattern")
    page.fill("#tracks .pattern-input", "x.x. x... x... x...")
    page.press("#tracks .pattern-input", "Enter")
    wait_idle(page, 3)
    wait_swapped(page, 2)
    assert "kick rendered + remixed" in page.text_content("#status")
    # mute: a listening mix of the kept stems, brought in the same way; its meter rests
    page.click("#tracks .track[data-name=kick] .mute")
    wait_idle(page)
    wait_swapped(page, 3)
    assert ".m" in page.evaluate("document.getElementById('audio').src")
    page.wait_for_function("document.querySelector('#tracks .track[data-name=kick] .meter').dataset.db === ''")
    assert page.evaluate("document.querySelector('#tracks .track[data-name=bass] .meter').dataset.db") != ""
    # under narration: the same mix under the narration sample, and back
    page.check("#narration")
    wait_idle(page)
    wait_swapped(page, 4)
    assert page.evaluate("document.getElementById('audio').src").endswith(".n.wav") and "under narration" in page.text_content("#status")
    page.uncheck("#narration")
    wait_idle(page)
    wait_swapped(page, 5)
    assert not page.evaluate("document.getElementById('audio').src").endswith(".n.wav")
    assert page.get_attribute("#play", "aria-pressed") == "true" and page.evaluate("document.getElementById('audio').paused") is False
    assert page.evaluate("document.getElementById('audio-next').paused") is True  # the other element is quiet
    assert page.errors == []


# ----- Step 197: check panel, versions, A/B, exports ------------------------------------------------

#: A piano too loud in the voice's range: the check advises lowering it or an octave up.
LOUD = """\
title: Loud
key: A minor
tempo: 120
progression: "i VI"
sections: [{name: a, bars: 2}, {name: lift, bars: 2}]
tracks:
  pad: {instrument: pad, play: chords, volume: -6}
  piano: {instrument: piano, steps: "* . * . * . * .", octave: 4, volume: 4}
"""


def wait_checked(page: Any, version: int) -> None:
    page.wait_for_function(f"!document.body.dataset.checking && document.getElementById('check-for').textContent === 'v{version}'", timeout=90_000)


def test_check_panel_advice_applies_as_a_version(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=LOUD)
    page.goto(server.url)
    wait_idle(page, 1)
    wait_checked(page, 1)
    assert "needs work" in page.text_content("#check-verdict") and "voice" in page.text_content("#check-headline")
    if page.is_hidden("#check-body"):
        page.click("#check-toggle")
    assert page.get_attribute("#check-image", "src").endswith("-check.png")
    page.wait_for_function("document.getElementById('check-image').naturalWidth > 0")
    assert "Loud:" in page.text_content("#check-report")
    button = page.locator("#check-advice button.apply", has_text="octave up").first
    button.click()
    wait_idle(page, 2)
    assert app.session is not None and app.session.versions[-1].label == "check: move piano an octave up (octave 5)"
    assert "octave: 5" in page.input_value("#yaml-input")
    wait_checked(page, 2)  # checked again after the new version's render
    assert page.errors == []


def test_versions_undo_redo_rename_star_and_ab(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    assert page.is_disabled("#ab") and page.is_disabled("#undo")
    page.fill("#f-tempo", "100")
    page.press("#f-tempo", "Enter")
    wait_idle(page, 2)
    page.click("#undo")
    wait_idle(page, 1)
    assert page.input_value("#f-tempo") == "120" and page.is_enabled("#redo")
    page.keyboard.press("Control+Shift+Z")
    wait_idle(page, 2)
    assert page.input_value("#f-tempo") == "100"
    # the list: rename and star v1, then A/B against the original at the same moment
    page.click("#versions")
    page.locator('#version-list li[data-version="1"] button[data-act="rename"]').click()
    page.fill("#rename-input", "the start")
    page.press("#rename-input", "Enter")
    page.wait_for_function("document.querySelector('#version-list li[data-version=\"1\"] .v-label')?.textContent === 'the start'")
    page.locator('#version-list li[data-version="1"] button[data-act="star"]').click()
    page.wait_for_function("document.querySelector('#version-list li[data-version=\"1\"] .star').getAttribute('aria-pressed') === 'true'")
    page.keyboard.press("Escape")
    versions = {v.number: v for v in app.session.versions}
    assert versions[1].label == "the start" and versions[1].starred
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 0.5", timeout=15_000)
    page.click("#ab")
    page.wait_for_function("document.body.dataset.ab === 'A' && !document.body.dataset.busy && !document.body.dataset.switching", timeout=30_000)
    assert "v1 original" in page.text_content("#ab-state") and page.text_content("#status").startswith("v1 ")
    page.click("#ab")
    page.wait_for_function("document.body.dataset.ab === 'B' && !document.body.dataset.busy", timeout=30_000)
    assert "v2 current" in page.text_content("#ab-state")
    page.click("#play")
    assert page.errors == []


def test_export_yaml_audio_and_no_project(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    app, server = studio
    app.load(text=TINY)
    page.context.set_default_timeout(60_000)
    page.goto(server.url)
    wait_idle(page, 1)
    page.click("#export")
    assert "started without a project" in page.text_content("#ex-save-note") and page.is_hidden("#ex-save-form")
    with page.expect_download() as info:
        page.click("#ex-yaml")
    assert info.value.suggested_filename == "tiny-v1.yaml"
    page.select_option("#ex-length", "loops")
    page.fill("#ex-count", "2")
    with page.expect_download() as info:
        page.click("#ex-audio")
    assert info.value.suggested_filename == "tiny-v1-2loops-video.wav"
    page.wait_for_function("!document.body.dataset.exporting")
    assert "Downloaded" in page.text_content("#ex-audio-note") and page.is_visible("#export-panel")
    assert page.errors == []


def test_listening_notes_while_playing(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    """Step 198: N while playing pins a note at the moment; the lane pins one where clicked; the
    Notes tab lists them (resolve, delete; play from a little before)."""
    app, server = studio
    app.load(text=TINY)
    page.goto(server.url)
    wait_idle(page, 1)
    page.click("#play")
    page.wait_for_function("document.getElementById('audio').currentTime > 0.6", timeout=15_000)
    page.keyboard.press("n")
    page.wait_for_selector("#note-text")
    assert "bar 1" in page.text_content("#note-editor") and " · a · " in page.text_content("#note-editor")
    page.keyboard.type("kick too stiff")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('notes-count').textContent === '1'")
    box = page.locator("#note-lane").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.8, box["y"] + box["height"] / 2)  # 3.2 s: bar 2, in b
    page.keyboard.type("love this part")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('notes-count').textContent === '2'")
    assert page.locator("#note-lane .pin.open").count() == 2
    page.click("#tab-notes")
    rows = page.locator("#note-list .note")
    assert rows.count() == 2 and "n2 · bar 2 · beat 3 · b" in rows.nth(1).text_content()
    notes = {n["id"]: n for n in app.state()["notes"]}
    assert notes["n1"]["text"] == "kick too stiff" and notes["n1"]["section"] == "a" and notes["n1"]["version"] == 1
    page.locator('#note-list .note[data-id="n2"] [data-act="resolve"]').click()
    page.wait_for_function("document.getElementById('notes-count').textContent === '1'")
    assert page.locator("#note-lane .pin.resolved").count() == 1
    page.locator('#note-list .note[data-id="n1"] [data-act="play"]').click()
    page.wait_for_function("document.getElementById('note-list').querySelector('.note.lit')")
    page.locator('#note-list .note[data-id="n1"] [data-act="delete"]').click()
    page.wait_for_function("document.querySelectorAll('#note-list .note').length === 1")
    page.click("#play")
    page.click("#tab-yaml")
    assert page.errors == []


def test_ask_an_agent_proposal_ab_and_keep(page: Any, tmp_path: Path) -> None:
    """Step 198: Ask an agent → an MCP agent's proposal (written as the studio_propose tool writes
    it) appears while the page polls → A/B against the current version → keep."""
    from vidgen.studio_app.agent import agent_propose

    app = StudioApp(tmp_path, studio=tmp_path / "build" / "studio")
    server, thread = start_in_thread(app)
    try:
        app.load(text=TINY)
        page.goto(server.url)
        wait_idle(page, 1)
        app.add_note(None, 1.0, "kick too plain")
        page.click("#tab-notes")
        page.wait_for_function("document.getElementById('notes-count').textContent === '1'", timeout=10_000)  # seen by polling
        page.click("#ask")
        page.wait_for_selector("#copy-prompt")
        assert "waiting for a proposal" in page.text_content("#handoff") and page.is_disabled("#provider-send")
        busier = TINY.replace('"x... x... x... x..."', '"x... x.x. x... x.x."')
        agent_propose(tmp_path, busier, {"n1": "two off-beat kicks"}, "busier kick", "test")
        page.wait_for_selector("#proposal-bar .proposal.pending", timeout=10_000)
        assert "An agent proposed v2" in page.text_content("#proposal-bar") and "two off-beat kicks" in page.text_content("#proposal-bar")
        assert page.text_content("#version-name") == "v1" and "answered" in page.text_content("#handoff")
        page.click("#proposal-bar [data-act=ab]")
        page.wait_for_function("document.body.dataset.ab === 'A' && !document.body.dataset.busy", timeout=30_000)
        assert page.text_content("#status").startswith("v2 ")
        page.click("#proposal-bar [data-act=keep]")
        wait_idle(page, 2)
        assert page.is_hidden("#proposal-bar") and app.session is not None and app.session.current == 2
        assert "kept in v2" in page.text_content("#note-list")
        page.click("#play")
        page.click("#tab-yaml")
        assert page.errors == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


VARI = TINY.replace('progression: "i VI"', 'progression: "i VI III VII"').replace(
    "{name: a, bars: 1}, {name: b, bars: 1}", "{name: a, bars: 1}, {name: b, bars: 2}") + '  arp: {instrument: pluck, steps: "1358 5315 1358 5318", accent: "3+3+2"}\n'


def test_variations_play_one_and_keep_it(studio: tuple[StudioApp, StudioServer], page: Any) -> None:
    """Step 199: Variations → four cards rendered and checked → play one at the same moment (A/B
    against the current version) → back → keep it as the next version."""
    app, server = studio
    app.load(text=VARI)
    page.goto(server.url)
    wait_idle(page, 1)
    page.click("#variations-btn")
    page.wait_for_function("document.body.dataset.variations === 'done'", timeout=120_000)
    cards = page.locator("#variations-cards .v-card")
    assert cards.count() == 4 and page.locator("#variations-cards .v-verdict").count() == 4
    assert [cards.nth(k).get_attribute("class").split()[1] for k in range(4)] == ["kind-harmony", "kind-pattern", "kind-mix", "kind-energy"]
    page.click("#play")
    page.click("#variations-cards .v-card[data-letter='b'] .v-play")
    page.wait_for_function("document.body.dataset.ab === 'V' && !document.body.dataset.busy", timeout=30_000)
    assert page.text_content("#status").startswith("variation b ") and "variation b" in page.text_content("#ab-state")
    page.click("#variations-cards .v-card[data-letter='b'] .v-play")  # back to the current version
    page.wait_for_function("document.body.dataset.ab !== 'V' && !document.body.dataset.busy", timeout=30_000)
    assert page.text_content("#status").startswith("v1 ")
    page.click("#variations-cards .v-card[data-letter='b'] .v-keep")
    wait_idle(page, 2)
    assert app.session is not None and app.session.versions[-1].origin == "variation" and app.session.current == 2
    page.wait_for_selector("#variations-cards .v-card[data-letter='b'].kept")
    assert "arp" in page.input_value("#yaml-input")
    page.click("#play")
    assert page.errors == []
