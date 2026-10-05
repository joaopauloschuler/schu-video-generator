"""``image``: a picture from the project's assets with an optional caption and Ken Burns move."""

from typing import Any, Literal

import numpy as np
from PIL import Image as PILImage

from vidgen.api import *

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


class KenBurns(SceneParams):
    """Slow zoom/pan over the whole scene. Focus points are ``[x, y]`` in image coordinates
    (0..1, origin top-left): the point the view is centered on."""

    start_scale: float = Field(1.0, ge=1.0, le=4.0)
    end_scale: float = Field(1.15, ge=1.0, le=4.0)
    start_focus: tuple[float, float] = (0.5, 0.5)
    end_focus: tuple[float, float] = (0.5, 0.5)

    @field_validator("start_focus", "end_focus")
    @classmethod
    def _unit(cls, v: tuple[float, float]) -> tuple[float, float]:
        if not all(0.0 <= c <= 1.0 for c in v):
            raise ValueError("focus coordinates must be between 0 and 1")
        return v


def check_image(project: Any, rel: str, field: str) -> list[str]:
    """Problems with an image path param (missing file, unsupported type), for validate_project."""
    path = project.root / rel
    if not path.is_file():
        return [f"{field}: file not found: {rel} (looked for {path})"]
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return [f"{field}: unsupported image type {path.suffix!r} (use {', '.join(sorted(IMAGE_SUFFIXES))})"]
    return []


def load_image(path: Any) -> ImageMobject:
    """An ``ImageMobject`` from a file, converted to RGBA first (palette PNGs would otherwise be
    resampled without smoothing)."""
    with PILImage.open(path) as im:
        return ImageMobject(np.array(im.convert("RGBA")))


@scene("image")
class Image(NarratedScene):
    """Beat 1 fades the image in, beat 2 the caption (both in beat 1 if there is only one).

    ``fit: contain`` shows the whole image (caption below it); ``cover`` fills the frame
    (cropping) with the caption on a band at the bottom. ``ken_burns`` zooms/pans slowly over
    the whole scene (in ``contain`` mode the image never outgrows its box).
    """

    outro = 0.5

    class Params(SceneParams):
        path: str
        caption: str = ""
        fit: Literal["contain", "cover"] = "contain"
        ken_burns: KenBurns | bool = False
        caption_color: ThemeColor = "text"
        caption_size: ThemeSize = "caption"

        def motion(self) -> KenBurns | None:
            """The Ken Burns settings, or ``None`` when disabled."""
            if self.ken_burns is True:
                return KenBurns()
            return self.ken_burns or None

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        return super().validate_project(params, project) + check_image(project, params.path, "path")

    def construct(self) -> None:
        p = self.params
        problems = check_image(self.project, p.path, "path")
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        img = load_image(self.project.asset(p.path))
        aspect = img.width / img.height
        fw, fh = self.frame_width, self.frame_height
        motion = p.motion()

        caption = None
        if p.caption:
            caption = fit_text(p.caption, self.safe_width, self.safe_height * 0.18, size=p.caption_size, color=p.caption_color)

        if p.fit == "cover":
            box_w, box_h, box_c = fw, fh, np.zeros(3)
            base_w = max(fw, fh * aspect)
            if caption is not None:
                band_h = caption.height + 0.6
                band = Rectangle(width=fw, height=band_h, stroke_width=0)
                band.set_fill(self.theme.background, opacity=0.72).move_to([0, -fh / 2 + band_h / 2, 0])
                caption.move_to(band)
                caption = Group(band, caption)
        else:
            # the image box is the image at its largest scale; box + caption are centered
            cap_h = caption.height + 0.35 if caption is not None else 0.0
            box_w = min(self.safe_width, (self.safe_height - cap_h) * aspect)
            box_h = box_w / aspect
            box_c = np.array([0.0, cap_h / 2, 0.0])
            base_w = box_w / (max(motion.start_scale, motion.end_scale) if motion else 1.0)
            if caption is not None:
                caption.move_to([0, box_c[1] - box_h / 2 - 0.35 - caption.height / 2, 0])

        def frame_at(progress: float) -> None:
            s0, s1 = (motion.start_scale, motion.end_scale) if motion else (1.0, 1.0)
            f0, f1 = (motion.start_focus, motion.end_focus) if motion else ((0.5, 0.5), (0.5, 0.5))
            t = smooth(progress)
            w = base_w * (s0 + (s1 - s0) * t)
            h = w / aspect
            fx = f0[0] + (f1[0] - f0[0]) * t - 0.5
            fy = f0[1] + (f1[1] - f0[1]) * t - 0.5
            # move the focus point towards the box center, but keep the image covering the frame
            # (cover) or inside its box (contain)
            slack = np.array([abs(w - box_w) / 2, abs(h - box_h) / 2, 0.0])
            offset = np.clip(np.array([-fx * w, fy * h, 0.0]), -slack, slack)
            img.scale_to_fit_width(w).move_to(box_c + offset)

        frame_at(0.0)
        if motion is not None:
            total = self._moving_time()
            start = float(self.renderer.time)

            def drift(m: Mobject, dt: float) -> None:
                frame_at(min(1.0, (self.renderer.time - start) / total))

            img.add_updater(drift)

        steps: list = [FadeIn(img)]
        if caption is not None:
            steps.append(FadeIn(caption, shift=UP * 0.1))
        self.reveal(steps, fraction=0.6, cap=1.0)
        img.clear_updaters()
        self.finish()

    def _moving_time(self) -> float:
        """Seconds from the first beat to the end of the last (the Ken Burns move's length)."""
        if not self.beats:
            return max((self.spec.duration or 0.0) - self.outro, 0.1)
        return sum(self.beat_duration(i) + self.pad for i in range(len(self.beats)))
