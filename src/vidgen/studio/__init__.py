"""Music agents can write (Phase S, DESIGN.md §93): score files in YAML — key, tempo, sections,
chords, tracks of step patterns — rendered with vidgen's own synthesizer.

Self-contained: it uses only :mod:`vidgen.music`'s building blocks, :mod:`vidgen.sfx`,
:mod:`vidgen.loudness` and :mod:`vidgen.errors`, never video, scene or render code, so it can
become a package of its own.
"""

from __future__ import annotations

from vidgen.studio.instruments import INSTRUMENTS, Instrument
from vidgen.studio.render import render_music_score
from vidgen.studio.score_file import MusicScore, load_music_score, parse_music_score, score_outline

__all__ = ["INSTRUMENTS", "Instrument", "MusicScore", "load_music_score", "parse_music_score", "render_music_score", "score_outline"]
