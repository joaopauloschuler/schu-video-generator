"""``web`` scenes: a page written in HTML, CSS and JavaScript, screenshotted in headless Chromium
(DESIGN.md §118).

- :mod:`vidgen.web.entry` checks the file a scene names (``page:`` or ``script:``); no browser.
- :mod:`vidgen.web.page` serves the project folder to the page and takes the screenshots.
- :mod:`vidgen.web.clip` writes them to a cached lossless clip the scene shows.

Playwright comes with a plain install; nothing here imports it until a ``web`` scene renders.
"""
