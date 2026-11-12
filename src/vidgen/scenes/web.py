"""``web``: a page written in HTML, CSS and JavaScript (DESIGN.md §118), screenshotted in headless
Chromium at the render's size and frame rate and shown full-bleed under the overlays and captions.

Before the scene plays, its frames are drawn into a lossless clip (``<render_dir>/web/<scene_id>.mkv``,
with what it was drawn from beside it as ``.json``) and reused while the page or script file, the
size, frame rate and length are unchanged; the clip is then a ``ClipMobject`` filling the frame.
"""

from pathlib import Path
from typing import Any

from vidgen.api import *

#: Extra frames drawn after the planned end (the last one holds if the scene runs longer).
SPARE_FRAMES = 2


@scene("web")
class Web(NarratedScene):
    """A page written in HTML, CSS and JavaScript, shown full-bleed: ``page:`` names an HTML file
    of the project (any HTML, CSS and JavaScript; relative links work) or ``script:`` a
    JavaScript module that vidgen loads into a bare page with one canvas filling the frame.
    Before each frame vidgen calls the page's ``frame(t, ctx)`` (``t``: seconds from the scene's
    start; a page sets ``window.vidgen = {frame}``, a script exports ``frame``), then takes a
    screenshot; without it the page is captured as it stands. Nothing is fetched from the
    internet. The scene fades out at the end. Drawn in headless Chromium (once:
    ``python -m playwright install chromium``).

    Action targets: ``view`` (the page).
    """

    outro = 0.5
    target_patterns = ("view",)

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``view``."""
        return ["view"]

    class Params(SceneParams):
        page: str | None = None
        """An HTML file in the project folder (``extensions/gears.html``): any HTML, CSS and
        JavaScript; relative links to styles, pictures, fonts and modules are served from the
        project folder."""
        script: str | None = None
        """A JavaScript module in the project folder (``extensions/gears.js``), loaded into a bare
        page with one canvas (``id="vidgen-canvas"``, the frame's size; also ``ctx.canvas``)."""

        @model_validator(mode="after")
        def _one_entry(self) -> "Web.Params":
            if (self.page is None) == (self.script is None):
                raise ValueError("give exactly one of page: (an HTML file) or script: (a JavaScript module)")
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        """The page or script file exists in the project folder and has the right suffix."""
        return web_entry_problems(project.root, params)

    def construct(self) -> None:
        view = ClipMobject(self._draw_view())
        view.fit_box(self.frame_width, self.frame_height, "cover").move_to(ORIGIN)
        view.play(self)
        self._view = view
        self.add(view)
        self.target("view", view)
        for _ in self.timeline():
            pass
        self.finish()

    def tear_down(self) -> None:
        """Release the clip file, then the usual tear-down."""
        view = getattr(self, "_view", None)
        if isinstance(view, ClipMobject):
            view.close()
        super().tear_down()

    def _draw_view(self) -> Path:
        """The clip of the page's frames (drawn now, or reused while its inputs are unchanged)."""
        _, frames = clip_plan(self, SPARE_FRAMES)
        return make_web_clip(
            self.project.root, self.project.render_dir(self.is_preview) / "web", self.spec.id, self.params,
            size=(int(config.pixel_width), int(config.pixel_height)), fps=int(config.frame_rate), frames=frames,
        )
