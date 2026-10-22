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
    assert page.text_content("#f-key") == "A minor" and page.text_content("#f-tempo") == "120 BPM"
    assert page.text_content("#f-roman") == "i VI"
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
