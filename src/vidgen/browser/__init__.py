"""Headless Chromium through Playwright, shared by the ``3d`` and ``web`` scenes (DESIGN.md §118).

- :mod:`vidgen.browser.timing` (`clip_plan`): how many frames such a scene draws.
- :mod:`vidgen.browser.chromium` starts and stops Chromium, checks that Playwright and its
  Chromium are installed, and writes frames to a lossless clip.

Playwright comes with a plain install; nothing here imports it until a scene renders.
"""
