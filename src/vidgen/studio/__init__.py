"""Music agents can write (Phase S, DESIGN.md §93): score files in YAML — key, tempo, sections,
chords, tracks of step patterns with effects — rendered with vidgen's own synthesizer.

Self-contained: it uses only :mod:`vidgen.music`'s building blocks, :mod:`vidgen.sfx`,
:mod:`vidgen.loudness` and :mod:`vidgen.errors`, never video, scene or render code, so it can
become a package of its own.
"""

from __future__ import annotations

from vidgen.studio.check import MusicCheck, check_music_audio, check_music_score, music_check_text
from vidgen.studio.effects import EFFECTS
from vidgen.studio.instruments import INSTRUMENTS, Instrument
from vidgen.studio.patches import patch_catalog, patch_text
from vidgen.studio.render import render_music_score
from vidgen.studio.score_file import MusicScore, load_music_score, parse_music_score, score_outline
from vidgen.studio.templates import music_template_catalog, music_template_text, template_path

__all__ = [
    "EFFECTS",
    "INSTRUMENTS",
    "Instrument",
    "MusicCheck",
    "MusicScore",
    "check_music_audio",
    "check_music_score",
    "load_music_score",
    "music_check_text",
    "music_template_catalog",
    "music_template_text",
    "template_path",
    "parse_music_score",
    "patch_catalog",
    "patch_text",
    "render_music_score",
    "score_outline",
]
