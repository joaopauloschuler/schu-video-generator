"""3D scenes drawn by three.js in headless Chromium (DESIGN.md §114).

- :mod:`vidgen.three_d.description` turns a ``3d`` scene's params into the *scene description*
  (JSON: objects with ids, camera, lights, background, timeline, draw mode) the page reads.
- :mod:`vidgen.three_d.browser` drives the page (``data/three``: vendored three.js and
  ``vidgen3d.js``) through Playwright and writes the frames to a lossless clip.

Playwright is an optional extra (``schu-video-generator[3d]``); nothing here imports it until
a 3D scene renders.
"""
