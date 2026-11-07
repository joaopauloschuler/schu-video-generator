"""``3d``: a 3D scene drawn by three.js in headless Chromium (DESIGN.md §114), shown full-bleed under
the scene's title, the overlays and the captions.

Before the scene plays, its frames are drawn into a lossless clip
(``<render_dir>/three_d/<scene_id>.mkv``, with the scene description beside it as ``.json``) and
reused while the description and the page are unchanged; the clip is then a ``ClipMobject``
filling the frame, so stills, fades and the layout dump see it like any picture.
"""

import math
from pathlib import Path
from typing import Any

from vidgen.api import *

#: Extra frames drawn after the planned end (the last one holds if the scene runs longer).
SPARE_FRAMES = 2


@scene("3d")
class Scene3D(NarratedScene):
    """Objects in 3D (a box for now) seen by a fixed camera with one default light (ambient +
    sun) over a background colour. The picture fills the frame from the first frame and keeps
    moving (``spin``) through every beat; beat 1 fades the title in; the scene fades out at the
    end. Frames are drawn by three.js in headless Chromium (``pip install
    "schu-video-generator[3d]"`` and ``python -m playwright install chromium``).

    Action targets: ``view`` (the 3D picture), ``title`` (if any).
    """

    outro = 0.5
    target_patterns = ("view", "title")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``view`` and, with a title, ``title``."""
        return ["view"] + (["title"] if params.title else [])

    class Params(Scene3DParams):
        pass

    def construct(self) -> None:
        view = ClipMobject(self._draw_view())
        view.fit_box(self.frame_width, self.frame_height, "cover").move_to(ORIGIN)
        view.play(self)
        self._view = view
        self.add(view)
        self.target("view", view)
        title = self._title()
        for i, d in self.timeline():
            if i == 0 and title is not None:
                self.play_steps(d, [lambda: self.entrance("title")], fraction=0.6, cap=0.8)
        self.finish()

    def tear_down(self) -> None:
        """Release the clip file, then the usual tear-down."""
        view = getattr(self, "_view", None)
        if isinstance(view, ClipMobject):
            view.close()
        super().tear_down()

    def _title(self) -> Mobject | None:
        """The title on a plate in the header band (registered as target ``title``)."""
        if not self.params.title:
            return None
        header = self.region("header")
        text = fit_text(self.params.title, header.width - 0.6, header.height - 0.2, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
        title = text_plate(text, self.theme.color("surface"))
        place(title, header, fit="none", align="top")
        self.target("title", title)
        return title

    # ----- the 3D frames -----------------------------------------------------------------------

    def _plan(self) -> tuple[list[BeatSpan], int]:
        """The beats on the scene's clock and how many frames to draw (as long as the scene
        plays: its beats or a silent scene's duration, then the fade-out)."""
        fps = int(config.frame_rate)
        spans: list[BeatSpan] = []
        frames = 0
        if self.beats:
            for beat in self.beats:
                window = self.beat_window(beat)
                start = frames / fps
                spans.append(BeatSpan(beat.id, start, start + window.heard))
                frames += round(window.window * fps)
        else:
            frames = round(max((self.spec.duration or 0.0) - self.outro, 1 / fps) * fps)
        return spans, frames + math.ceil(self.outro * fps) + SPARE_FRAMES

    def description(self) -> dict[str, Any]:
        """The scene description this render draws (DESIGN.md §114.3)."""
        spans, frames = self._plan()
        return scene_description(
            self.params, self.theme, width=int(config.pixel_width), height=int(config.pixel_height),
            fps=int(config.frame_rate), frames=frames, beats=spans,
        )

    def _draw_view(self) -> Path:
        """The clip of the 3D frames (drawn now, or reused while its description and the page
        are unchanged)."""
        return make_3d_clip(self.project.render_dir(self.is_preview) / "three_d", self.spec.id, self.description())
