"""``web_cut``: the ``web`` scene without its 0.5 s fade-out, so the three scenes of the cue cut
straight into each other on the bar line while the music goes on (docs/EXTENDING.md, "A variant
of the ``web`` type"). Its scenes take the ``web`` params and are cached like ``web`` scenes."""

from vidgen.api import scene
from vidgen.scenes.web import Web


@scene("web_cut")
class WebCut(Web):
    outro = 0.0
