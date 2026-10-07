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
    """Zoom at the start of the scene (1-4)."""
    end_scale: float = Field(1.15, ge=1.0, le=4.0)
    """Zoom at the end of the scene (1-4)."""
    start_focus: tuple[float, float] = (0.5, 0.5)
    """[x, y] in 0-1 (0,0 = top left) centered at the start."""
    end_focus: tuple[float, float] = (0.5, 0.5)
    """[x, y] in 0-1 (0,0 = top left) centered at the end."""

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

    Action targets: ``image``, ``caption`` (if any).
    """

    outro = 0.5
    target_patterns = ("image", "caption")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``image`` and, with a caption, ``caption``."""
        return ["image"] + (["caption"] if params.caption else [])

    class Params(SceneParams):
        path: str
        """Image file relative to the project folder, e.g. assets/photo.jpg."""
        caption: TranslatableStr = ""
        """Caption text."""
        fit: Literal["contain", "cover"] = "contain"
        """contain: whole image, caption below; cover: fills the frame (cropped), caption on a band."""
        ken_burns: KenBurns | bool = False
        """Slow zoom/pan over the whole scene; true = zoom 1.0 -> 1.15 on the center."""
        caption_color: ThemeColor = "text"
        """Caption color."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""

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

        caption = text = None
        if p.caption:
            caption = text = fit_text(p.caption, self.safe_width, self.safe_height * 0.18, size=p.caption_size, color=p.caption_color)

        if p.fit == "cover":
            box_w, box_h, box_c = fw, fh, np.zeros(3)
            base_w = max(fw, fh * aspect)
            if caption is not None:
                # the caption sits on the bottom of the safe area (never in the margin); the band
                # behind it runs from the frame's bottom edge to a little above the caption
                place(caption, self.region("caption"), fit="none", align="bottom")
                band_h = caption.get_top()[1] + 0.3 + fh / 2
                band = Rectangle(width=fw, height=band_h, stroke_width=0)
                band.set_fill(self.theme.background, opacity=0.72).move_to([0, -fh / 2 + band_h / 2, 0])
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

        picture = self.target("image", img, entrance=lambda: [FadeIn(img)])
        steps: list = [lambda: self.entrance(picture)]  # entrance(): not twice after a reveal action
        if caption is not None:  # the target is the text (a cover caption's band is not recoloured)
            label = self.target("caption", text, entrance=lambda: [FadeIn(caption, shift=UP * 0.1)])
            steps.append(lambda: self.entrance(label))
        self.reveal(steps, fraction=0.6, cap=1.0)
        img.clear_updaters()
        self.finish()

    def _moving_time(self) -> float:
        """Seconds from the first beat to the end of the last (the Ken Burns move's length)."""
        if not self.beats:
            return max((self.spec.duration or 0.0) - self.outro, 0.1)
        return sum(self.beat_duration(i) + self.pad for i in range(len(self.beats)))
