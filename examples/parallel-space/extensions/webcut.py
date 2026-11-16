"""``web_cut``: the ``web`` scene without its 0.5 s fade-out, so beat-locked scenes cut straight
into each other on the bar line (the music video's scenes are back to back, 52 frames per bar)."""
from vidgen.api import scene
from vidgen.scenes.web import Web


@scene("web_cut")
class WebCut(Web):
    outro = 0.0
