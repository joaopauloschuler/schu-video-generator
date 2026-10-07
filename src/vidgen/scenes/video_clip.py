"""``video_clip``: a video file (B-roll, a screen recording) from the project's assets, played
inside the scene while the narration runs: full-bleed or in a layout region (optionally in a
browser / window / phone frame, with a title and a caption), trimmed, sped up or slowed down,
looped or held on its last frame, its sound mixed under the narration, and callouts drawn on top
step by step like the ``screenshot`` scene's.

The clip is a ``ClipMobject`` (``vidgen.api``): its frames are decoded as the render reaches
them, so stills, the layout dump, ``vidgen lint`` and beat actions see it like any picture.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, ClassVar, Literal

from vidgen.api import *

from .screenshot import CAPTION_GAP, CalloutSpec, Screenshot

log = logging.getLogger("vidgen.scenes")

#: A held last frame longer than this (seconds) is reported when the scene renders.
HOLD_WARNING = 2.0
#: Clip sound volume under narration when ``volume`` is not given (1.0 in a silent scene).
UNDER_NARRATION = 0.25
#: Regions the clip can take (``bleed`` = the whole frame, edge to edge).
ClipRegion = Literal["body", "full", "hero", "left", "right", "top", "bottom", "center", "bleed"]


@scene("video_clip")
class VideoClip(Screenshot):
    """Beat 1 fades the clip in (with its title and caption) and then step 1's callouts; step *i*
    (an entry of ``steps``) draws its callouts at beat *i*, as in ``screenshot``. The clip starts
    playing when the scene starts and plays through every beat: the scene lasts as long as its
    narration (plus the fade-out), whatever the clip's length. A shorter clip holds its last
    frame (``loop: true`` starts it again; ``fit_duration: true`` changes its speed to fit); a
    longer one is cut by the fade-out.

    Action targets: ``title``, ``clip`` (the picture with its frame), ``caption``,
    ``callout<N>``, ``callout:<label>``, ``step<N>``.
    """

    outro = 0.5
    target_patterns = ("title", "clip", "caption", "callout<N>", "callout:<label>", "step<N>")
    picture_name: ClassVar[str] = "clip"

    class Params(Screenshot.Params):
        path: str
        """Video file relative to the project folder, e.g. assets/demo.mp4 (mp4, mov, m4v, webm, mkv)."""
        title: TranslatableStr = ""
        """Heading above the clip (on a plate over it with region: bleed)."""
        caption: TranslatableStr = ""
        """Line under the clip (on a plate over its bottom with region: bleed)."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""
        caption_color: ThemeColor = "text"
        """Caption colour."""
        region: ClipRegion = "body"
        """Where the clip goes: a layout region (body, full, hero, left, right, top, bottom, center; below the title) or bleed (the whole frame, edge to edge)."""
        fit: Literal["auto", "contain", "cover"] = "auto"
        """contain: the whole picture, as large as fits; cover: fills the region (or the frame), cutting off what does not fit; auto: contain, except a landscape clip without callouts in a vertical frame, shown as a nearly square part from its middle (cover), not a thin strip."""
        trim: tuple[float, float] | None = None
        """[start, end] in seconds of the file: only this part plays (default: all of it)."""
        speed: float = Field(default=1.0, ge=0.25, le=4.0)
        """Playback speed (0.5 = half speed, 2 = twice as fast; the sound keeps its pitch)."""
        fit_duration: bool = False
        """Change the speed so the clip lasts as long as the narration, within fit_range."""
        fit_range: tuple[float, float] = (0.5, 2.0)
        """Slowest and fastest speed fit_duration may choose (0.25-4)."""
        loop: bool = False
        """Start the clip again when it ends before the scene does (else its last frame holds)."""
        volume: float | None = Field(default=None, ge=0.0, le=2.0)
        """Volume of the clip's own sound (1 = as recorded, 0 = silent); default 0.25 under narration, 1 in a silent scene."""
        mute: bool = False
        """Leave out the clip's sound."""
        units: Literal["fraction", "px"] = "fraction"
        """Callout areas in fractions of the clip's picture (0-1, from its top-left corner, before any cover crop) or in its pixels."""
        picture_word: ClassVar[str] = "clip"

        @model_validator(mode="after")
        def _clip_checks(self) -> SceneParams:
            if self.trim is not None and not 0 <= self.trim[0] < self.trim[1]:
                raise ValueError(f"trim: {list(self.trim)} is not [start, end] with 0 <= start < end (seconds)")
            low, high = self.fit_range
            if not 0.25 <= low <= high <= 4.0:
                raise ValueError(f"fit_range: {list(self.fit_range)} is not [slowest, fastest] within 0.25-4")
            if self.fit_duration and "speed" in self.model_fields_set:
                raise ValueError("speed: fit_duration chooses the speed; give one or the other (fit_range limits it)")
            if self.region == "bleed" and self.frame != "none":
                raise ValueError("frame: a frame needs a region; region: bleed fills the whole frame")
            if self.url and self.frame != "browser":
                raise ValueError("url: only a browser frame has an address field")
            for k, step in enumerate(self.steps):
                for j, c in enumerate(step.callouts):
                    if c.kind == "magnifier":
                        raise ValueError(f"steps[{k}].callouts[{j}]: a magnifier needs a still picture; use a box, or focus: true to look closer")
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super(Screenshot, cls).validate_project(params, project) + check_clip(project, params.path, "path")
        if problems:
            return problems
        info = probe_clip(project.root / params.path)
        if params.trim is not None:
            start, end = params.trim
            if end > info.duration + 1.0 / info.fps:
                problems.append(f"trim: {list(params.trim)} ends after the clip ({info.duration:.2f} s)")
        if params.units == "px":
            for k, step in enumerate(params.steps):
                for j, c in enumerate(step.callouts):
                    a = c.area
                    if a[0] > info.width or a[1] > info.height or (len(a) == 4 and (a[0] + a[2] > info.width or a[1] + a[3] > info.height)):
                        problems.append(f"steps[{k}].callouts[{j}].area: {a} is not inside the clip ({info.width} x {info.height} px)")
        return problems

    # ----- construct ---------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        problems = check_clip(self.project, p.path, "path")
        if problems:
            raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
        path = self.project.asset(p.path)
        window = self._window()
        timing = self._timing(probe_clip(path), window)
        self._img = clip = ClipMobject(path, timing)
        title, caption = self._place(clip)
        self._caption = caption
        self._cameras = [self._camera(k) for k in range(len(p.steps))]
        self._warn_cropped()
        self._callouts = self._build()
        self._register(title)
        if caption is not None:
            text = caption[-1] if p.region == "bleed" else caption
            self.target("caption", text, entrance=lambda: [FadeIn(caption, shift=UP * 0.1)])
        self._camera_at: tuple[float, tuple[float, float]] | None = None
        clip.set_resolution(self._magnification())
        clip.play(self)
        self._sound(path, timing, window)

        def intro() -> list[Animation]:
            anims = self.entrance("clip") + (self.entrance("title") if title is not None else [])
            return anims + (self.entrance("caption") if caption is not None else [])

        steps = [(lambda k=k: self._step(k)) for k in range(len(p.steps))]
        plan = distribute(len(steps), len(self.beats))
        for i, d in self.timeline():
            self.play_steps(d, ([intro] if i == 0 else []) + [steps[k] for k in plan[i]], fraction=0.6, cap=1.5)
        self.finish()

    def tear_down(self) -> None:
        """Release the clip file, then the usual tear-down."""
        img = getattr(self, "_img", None)
        if isinstance(img, ClipMobject):
            img.close()
        super().tear_down()

    # ----- timing and sound --------------------------------------------------------------------

    def _window(self) -> float:
        """Seconds the clip plays before the fade-out: the narration (beats + pads), or a
        silent scene's duration minus the fade-out."""
        if not self.beats:
            return max((self.spec.duration or 0.0) - self.outro, 0.1)
        return sum(self.beat_duration(i) + self.pad for i in range(len(self.beats)))

    def _timing(self, info: ClipInfo, window: float) -> ClipTiming:
        """The trim, the speed (fitted to ``window`` with ``fit_duration``) and the loop; warns
        when the last frame would hold for long."""
        p = self.params
        start, end = p.trim if p.trim is not None else (0.0, info.duration)
        end = min(end, info.duration)
        speed = fit_speed(end - start, window, *p.fit_range) if p.fit_duration else p.speed
        timing = ClipTiming(start, end, speed, p.loop)
        if not p.loop and window - timing.length > HOLD_WARNING:
            log.warning(
                "scene '%s': the clip plays %.1f s (at speed %.2g) but the scene runs %.1f s: its last frame holds for %.1f s (loop: true or fit_duration: true keep it moving)",
                self.spec.id, timing.length, speed, window, window - timing.length,
            )
        elif timing.length > window + 0.5:
            log.info("scene '%s': %.1f s of the clip's %.1f s are shown (the scene ends first)", self.spec.id, window, timing.length)
        return timing

    def _sound(self, path: Path, timing: ClipTiming, window: float) -> None:
        """Mix the clip's own sound into the scene's (under the narration), unless muted."""
        p = self.params
        volume = p.volume if p.volume is not None else UNDER_NARRATION if self.beats else 1.0
        if not self.audio_enabled or p.mute or volume <= 0 or not self._img.info.audio:
            return
        with tempfile.TemporaryDirectory(prefix="vidgen_clip_") as folder:
            wav = Path(folder) / "clip.wav"
            clip_audio(path, wav, timing, length=window + self.outro, volume=volume, fade=self.outro)
            self.add_sound(str(wav))

    def _magnification(self) -> float:
        """How much closer than the whole frame the camera gets (focus steps, zoom actions): the
        clip is decoded that much sharper."""
        scales = [self.frame_width / cam[0] for cam in self._cameras if cam is not None]
        for beat in self.beats:
            for act in beat.actions:
                if act.action == "zoom":
                    scales.append(float((act.model_extra or {}).get("scale") or 3.0))
        return max([1.0, *scales])

    # ----- layout ------------------------------------------------------------------------------

    def _place(self, clip: ClipMobject) -> tuple[Mobject | None, Mobject | None]:
        """Lay out the clip, its title and caption; sets ``_picture``, ``_body`` (where callout
        labels may go) and ``_keep_off``. Returns the title and the caption (``None`` if absent)."""
        p = self.params
        if p.region == "bleed":
            return self._place_bleed(clip)
        area = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size="heading", area=self.safe_area)   # header band, 1.3x in a vertical frame
            area = area.below(title, gap=0.45)
        room = area if p.region in ("full", "body") else region(p.region, area)
        caption = None
        if p.caption:
            caption = fit_text(p.caption, room.width, room.height * 0.2, size=p.caption_size, color=p.caption_color)
            room = room.above(room.y0 + caption.height, gap=CAPTION_GAP)
        self._body = area
        fit = p.fit
        if fit == "auto":
            fit = self._auto_fit(clip)
            if fit == "cover":  # a (nearly) square part from the clip's middle, centred in the room
                side = min(room.width, room.height)
                cx, cy = room.center[0], room.center[1]
                room = Region(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
        self._picture = self._layout(room, fill=fit == "cover")
        clip.fit_box(clip.width, clip.height, fit)
        if caption is not None:
            caption.next_to(self._picture, DOWN, buff=CAPTION_GAP).set_x(clip.get_x())
            self._keep_off = self._keep_off + [Region(*caption.get_corner(DL)[:2], *caption.get_corner(UR)[:2]).inset(-0.1)]
        return title, caption

    def _auto_fit(self, clip: ClipMobject) -> str:
        """``fit: auto`` in a region: ``cover`` (a square crop) for a landscape clip without
        callouts in a vertical frame, else ``contain``."""
        info = clip.info
        landscape = info.width / max(info.height, 1) >= self.landscape_aspect
        return "cover" if self.is_portrait and landscape and not self.params.callouts() else "contain"

    def _place_bleed(self, clip: ClipMobject) -> tuple[Mobject | None, Mobject | None]:
        """The clip fills (``cover``) or fits (``contain``) the whole frame; the title and the
        caption sit on plates over it, inside the safe area."""
        p = self.params
        clip.fit_box(self.frame_width, self.frame_height, "contain" if p.fit == "auto" else p.fit).move_to(ORIGIN)
        self._picture = Group(clip)
        self._keep_off = []
        body = self.safe_area
        title = caption = None
        if p.title:
            header = self.region("header")
            text = fit_text(p.title, header.width - 0.6, header.height - 0.2, size="heading", weight=BOLD, font=self.theme.font_for("heading"))
            title = self._plate(text)
            place(title, header, fit="none", align="top")
            body = body.below(title, gap=0.2)
        if p.caption:
            band = self.region("caption")
            text = fit_text(p.caption, band.width - 0.6, band.height * 1.5, size=p.caption_size, color=p.caption_color)
            caption = self._plate(text)
            place(caption, band, fit="none", align="bottom")
            body = body.above(caption, gap=0.2)
        self._body = body
        return title, caption

    def _plate(self, text: Mobject) -> Mobject:
        """``text`` on a rounded plate in the theme's surface colour (readable over any picture)."""
        plate = RoundedRectangle(width=text.width + 0.5, height=text.height + 0.3, corner_radius=0.12)
        plate.set_fill(self.theme.color("surface"), opacity=0.88).set_stroke(width=0).move_to(text)
        return Group(plate, text).set_z_index(3)

    def _picture_entrance(self) -> list[Animation]:
        if self.params.region == "bleed":
            return [FadeIn(self._picture)]
        return super()._picture_entrance()

    # ----- callout areas -----------------------------------------------------------------------

    def _spec_area(self, c: CalloutSpec) -> tuple[list[float], str]:
        """Areas are written on the whole picture (fractions or pixels); the clip may show a
        crop of it (``cover``), so they are moved into the part shown, in fractions of it."""
        info = self._img.info
        area = [float(v) for v in c.area]
        if self.params.units == "px":
            area = [v / (info.width if k % 2 == 0 else info.height) for k, v in enumerate(area)]
        cx, cy, cw, ch = self._img.crop
        moved = [(area[0] - cx) / cw, (area[1] - cy) / ch]
        if len(area) == 4:
            moved += [area[2] / cw, area[3] / ch]
        return moved, "fraction"

    def _warn_cropped(self) -> None:
        """Warn about callout areas outside the part of the picture ``cover`` shows."""
        for n, (_, c) in enumerate(self.params.callouts(), start=1):
            a, _ = self._spec_area(c)
            x1, y1 = (a[0] + a[2], a[1] + a[3]) if len(a) == 4 else (a[0], a[1])
            if a[0] < -1e-3 or a[1] < -1e-3 or x1 > 1.001 or y1 > 1.001:
                log.warning("scene '%s': callout %d (%s) is partly outside the part of the clip that fit: cover shows", self.spec.id, n, c.kind)


def check_clip(project: Any, rel: str, field: str) -> list[str]:
    """Problems with a clip path param (missing file, unsupported type, not a video)."""
    path = project.root / rel
    if not path.is_file():
        return [f"{field}: file not found: {rel} (looked for {path})"]
    if path.suffix.lower() not in CLIP_SUFFIXES:
        return [f"{field}: unsupported video type {path.suffix!r} (use {', '.join(CLIP_SUFFIXES)})"]
    try:
        probe_clip(path)
    except VidgenError as exc:
        return [f"{field}: {exc}"]
    return []
