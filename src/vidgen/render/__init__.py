"""The render pipeline (DESIGN.md §5.2).

- ``vidgen.render.worker``: renders one scene per process (``python -m vidgen.render.worker``).
- ``vidgen.render.pipeline.render_project``: drives the workers, pads, joins, writes SRT/timings.
- ``vidgen.render.ffmpeg``: ffmpeg discovery, audio padding, concatenation, probing.

Nothing is imported here, so running the worker module does not import it twice.
"""
