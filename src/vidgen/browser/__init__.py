"""Headless Chromium through Playwright, shared by the ``3d`` and ``web`` scenes (DESIGN.md §118).

- :mod:`vidgen.browser.timing` (`clip_plan`): how many frames such a scene draws.
- :mod:`vidgen.browser.chromium` starts and stops Chromium and checks that Playwright and its
  Chromium are installed.
- :mod:`vidgen.browser.frames_clip` writes the drawn frames to a clip: lossless, or compact
  (``render.intermediate``, DESIGN.md §120.9).

Playwright comes with a plain install; nothing here imports it until a scene renders.
"""
