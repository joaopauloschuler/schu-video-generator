"""``web``: a page written in HTML, CSS and JavaScript (DESIGN.md §118), screenshotted in headless
Chromium at the render's frame rate and shown full-bleed (``region: bleed``) or in the body region
under a title drawn by vidgen (``region: body``), under the overlays and captions.

Before the scene plays, its frames are drawn into a lossless clip with alpha
(``<render_dir>/web/<scene_id>.mkv``, with what it was drawn from beside it as ``.json``) at the
size of the box the page fills, and reused while nothing that draws them changed; the clip is
then a ``ClipMobject`` covering that box, so what the page leaves transparent shows the video's
background.
"""

from pathlib import Path
from typing import Any, Literal

from vidgen.api import *

#: Extra frames drawn after the planned end (the last one holds if the scene runs longer).
SPARE_FRAMES = 2


@scene("web")
class Web(NarratedScene):
    """A page written in HTML, CSS and JavaScript, shown full-bleed (``region: bleed``) or in the
    body region under a title (``region: body``; the page is laid out at that region's size):
    ``page:`` names an HTML file
    of the project (any HTML, CSS and JavaScript; relative links work) or ``script:`` a
    JavaScript module that vidgen loads into a bare page with one canvas filling the frame.
    Time belongs to vidgen: the page's timers, ``requestAnimationFrame``, ``Date``, CSS, SVG and
    video animations follow the video's time and ``Math.random`` is seeded from the scene id, so
    ordinary web code renders the same every time. Optional hooks: ``load(ctx)`` once before
    frame 0 and ``frame(t, ctx)`` before each screenshot (``t``: seconds from the scene's start; a
    page sets ``window.vidgen = {load, frame}``, a script exports them). The page is given the
    theme (``ctx.theme`` and CSS variables such as ``var(--vidgen-primary)``, with the bundled
    fonts), ``data:`` (``ctx.data``) and the narration beats (``ctx.beats``; ``<body
    data-beat="b2">`` and a ``vidgen-beat`` event); ``import * as THREE from "three"`` loads the
    bundled three.js; ``ctx.aspect`` (``16:9``, ``9:16``...) and ``<html data-aspect="9:16"
    data-orientation="portrait">`` let one page lay itself out for each shape of the video. What
    the page leaves transparent (a page without a background, the bare page of a script) shows
    the video's background. Nothing is fetched from the internet. The page is on screen from the
    first frame, beat 1 fades the title in, the scene fades out at the end. Drawn in headless
    Chromium (once: ``python -m playwright install chromium``).

    Action targets: ``view`` (the page), ``title`` (if any).
    """

    outro = 0.5
    target_patterns = ("view", "title")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``view`` and, with a title, ``title``."""
        return ["view"] + (["title"] if params.title else [])

    class Params(SceneParams):
        page: str | None = None
        """An HTML file in the project folder (``extensions/gears.html``): any HTML, CSS and
        JavaScript; relative links to styles, pictures, fonts and modules are served from the
        project folder."""
        script: str | None = None
        """A JavaScript module in the project folder (``extensions/gears.js``), loaded into a bare
        page with one canvas (``id="vidgen-canvas"``, the frame's size; also ``ctx.canvas``) on
        the theme's background."""
        title: TranslatableStr = ""
        """Heading drawn by vidgen: on a plate over the top of the page with region: bleed, above it with region: body."""
        region: Literal["bleed", "body"] = "bleed"
        """Where the page goes: bleed (the whole frame, edge to edge) or body (the safe area below the title; the page is laid out at that size)."""
        data: dict[str, Any] = {}
        """Values for the page, as the page reads them in ``ctx.data`` (``{teeth: 24, color:
        primary}``): text, numbers, true/false, null, lists and mappings; theme colour names are
        not resolved (the page looks them up in ``ctx.theme.colors``)."""

        @field_validator("data", mode="before")
        @classmethod
        def _json_data(cls, value: Any) -> Any:
            problem = web_json_problem(value)
            if problem is not None:
                raise ValueError(problem)
            return value

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
        title = self._title()
        box = self._page_box(title)
        view = ClipMobject(self._draw_view(box))
        view.fit_box(box.width, box.height, "cover").move_to(box.center)
        view.play(self)
        self._view = view
        self.add(view)
        self.target("view", view)
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
        """The title (registered as target ``title``): on a plate in the header band over the
        page (``bleed``, as on ``3d``), or a heading above it (``body``, as on ``video_clip``)."""
        p = self.params
        if not p.title:
            return None
        if p.region == "body":
            title = chart_title(p.title, size="heading", area=self.safe_area)
        else:
            header = self.region("header")
            text = fit_text(p.title, header.width - 0.6, header.height - 0.2, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
            title = place(text_plate(text, self.theme.color("surface")), header, fit="none", align="top")
        self.target("title", title)
        return title

    def _page_box(self, title: Mobject | None) -> Region:
        """Where the page goes, on whole pixels: the frame (``bleed``), or the safe area below the
        title (``body``)."""
        if self.params.region == "bleed":
            w, h = self.frame_width / 2, self.frame_height / 2
            return Region(-w, -h, w, h)
        area = self.safe_area
        return pixel_box(area.below(title, gap=0.45) if title is not None else area)

    def _draw_view(self, box: Region) -> Path:
        """The clip of the page's frames at the size of ``box`` (drawn now, or reused while its
        inputs are unchanged); drawing it also reads the page's text at the stills' frames."""
        spans, frames = clip_plan(self, SPARE_FRAMES)
        theme, beats = web_page_inputs(self, spans)
        frame = (int(config.pixel_width), int(config.pixel_height))
        per_unit = frame[0] / self.frame_width
        size = (max(1, round(box.width * per_unit)), max(1, round(box.height * per_unit)))
        self._clip_args: dict[str, Any] = {
            "root": self.project.root, "folder": self.project.render_dir(self.is_preview) / "web", "scene_id": self.spec.id,
            "params": self.params, "size": size, "fps": int(config.frame_rate), "frames": frames, "theme": theme,
            "beats": beats, "shape": web_page_shape(frame, self.params.region),
        }
        self._still_frames = planned_still_frames(self)
        self._layouts: dict[int, dict[str, Any]] = {}
        return make_web_clip(**self._clip_args, layout_frames=self._still_frames)

    def page_layout(self, frame: int) -> tuple[dict[str, Any], Mobject] | None:
        """What text the page shows at output frame ``frame`` (the clip's frame of that index) and
        the mobject showing it, for the layout dump and lint (DESIGN.md §118.12): read when the
        clip was drawn, else from the page now (frames still to come read in the same go)."""
        args, view = getattr(self, "_clip_args", None), getattr(self, "_view", None)
        if args is None or view is None:
            return None
        n = min(max(frame, 0), args["frames"] - 1)
        if n not in self._layouts:
            self._layouts.update(web_page_layouts(**args, at=[n, *(f for f in self._still_frames if f > n)]))
        return self._layouts[n], view


def pixel_box(area: Region) -> Region:
    """``area`` with its edges moved to the nearest pixel edges of the frame (so the page's
    screenshots are copied pixel for pixel)."""
    per_unit = float(config.pixel_width) / float(config.frame_width)
    half_w, half_h = float(config.frame_width) / 2, float(config.frame_height) / 2

    def snap(value: float, half: float) -> float:
        return round((value + half) * per_unit) / per_unit - half

    return Region(snap(area.x0, half_w), snap(area.y0, half_h), snap(area.x1, half_w), snap(area.y1, half_h))
