"""Video clips inside a scene (exported by ``vidgen.api``): the frames of an mp4 / mov / webm file
shown by a Manim mobject while the scene renders, and the clip's sound for the scene's mix.

- :func:`probe_clip` reads a clip's size, frame rate, length and whether it has sound
  (:class:`ClipInfo`), without decoding it.
- :class:`ClipTiming` maps playback time (seconds since the clip started playing) to a time in
  the file: ``trim`` start/end, ``speed`` and ``loop`` (else the last frame holds).
- :class:`ClipMobject` is an ``ImageMobject`` whose picture is the clip's frame at the scene's
  current time. Frames are decoded one by one with PyAV as the render reaches them, scaled once
  by FFmpeg to the size shown on screen (cropped for ``cover``), and never all held in memory.
  It fades, dims, tints, moves and zooms like any image: the pixels Manim's animations change
  are a 1 x 2 *modulation* (a black and a white pixel), applied to each frame as an affine map,
  so ``FadeIn``, the ``dim`` / ``highlight`` actions and Manim's ``set_opacity`` keep working
  on a moving picture.
- :func:`clip_audio` writes the clip's sound as it plays in the scene (trimmed, at its speed,
  looped, at a volume, faded out at the end) to a WAV that ``NarratedScene.add_sound`` mixes
  under the narration.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import av
import numpy as np
from manim import ImageMobject, config
from PIL import Image as PILImage

from vidgen.errors import VidgenError
from vidgen.render.ffmpeg import AUDIO_RATE, find_ffmpeg, run_ffmpeg

#: File types accepted as clips (anything PyAV decodes works; these are checked by validate).
CLIP_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
#: Slowest and fastest playback speeds (FFmpeg's ``atempo`` chains cover this range).
MIN_SPEED, MAX_SPEED = 0.25, 4.0
#: How far before a part's ``end`` its last shown moment is (seconds; less than a frame at
#: 200 fps, more than the reader's frame-time tolerance), so the frame at ``end`` never shows.
END_GAP = 5e-3
#: The modulation of a clip shown as it is: black stays black, white stays white, opaque.
_IDENTITY = np.array([[[0, 0, 0, 255], [255, 255, 255, 255]]], dtype=np.uint8)


@dataclass(frozen=True)
class ClipInfo:
    """What a clip file holds: picture size in pixels, frames per second, length in seconds (of
    its video stream), whether it has a sound stream and its channel count (0: no sound or not
    stated)."""

    width: int
    height: int
    fps: float
    duration: float
    audio: bool
    channels: int = 0

    @property
    def aspect(self) -> float:
        """Width / height of the picture."""
        return self.width / self.height


def probe_clip(path: Path) -> ClipInfo:
    """Read a clip's :class:`ClipInfo` with PyAV (container metadata; nothing is decoded unless
    the file does not state its length). Raises :class:`VidgenError` when it is not a video."""
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise VidgenError(f"{path.name} has no video stream")
            stream = container.streams.video[0]
            rate = stream.average_rate or stream.guessed_rate or 0
            fps = float(rate) if rate else 0.0
            duration = 0.0
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration = container.duration / av.time_base
            if duration <= 0:  # no length stated: read the packets' timestamps
                last = 0.0
                for packet in container.demux(stream):
                    if packet.pts is not None and packet.time_base is not None:
                        last = max(last, float((packet.pts + (packet.duration or 0)) * packet.time_base))
                duration = last
            width, height = stream.codec_context.width, stream.codec_context.height
            audio = bool(container.streams.audio)
            channels = int(container.streams.audio[0].channels or 0) if audio else 0
    except av.error.FFmpegError as exc:
        raise VidgenError(f"cannot read video {path.name}: {exc}") from None
    except OSError as exc:
        raise VidgenError(f"cannot read video {path}: {exc}") from None
    if width <= 0 or height <= 0 or duration <= 0:
        raise VidgenError(f"cannot read video {path.name}: no picture size or length")
    return ClipInfo(int(width), int(height), fps or 25.0, duration, audio, channels)


@dataclass(frozen=True)
class ClipTiming:
    """Which part of a clip plays and how: from ``start`` to ``end`` (seconds in the file) at
    ``speed``; when that is over it starts again (``loop``) or its last frame holds."""

    start: float
    end: float
    speed: float = 1.0
    loop: bool = False

    @property
    def span(self) -> float:
        """Seconds of the file that play (``end - start``)."""
        return self.end - self.start

    @property
    def length(self) -> float:
        """Seconds one pass takes on screen (``span / speed``)."""
        return self.span / self.speed

    def source_time(self, played: float) -> float:
        """The time in the file shown ``played`` seconds after the clip started playing (never
        the ``end`` itself: the last frame before it)."""
        t = round(max(played, 0.0) * self.speed, 6)  # frame times are sums of 1/fps: 2.0 not 1.9999999
        if self.loop and self.span > 0:
            t = math.fmod(t, round(self.span, 6))
        return self.start + min(t, max(self.span - END_GAP, 0.0))


def fit_speed(span: float, window: float, low: float = 0.5, high: float = 2.0) -> float:
    """The speed that makes ``span`` seconds of clip last ``window`` seconds, kept within
    ``[low, high]`` (so a clip is never sped up or slowed down beyond recognition)."""
    if window <= 0:
        return high
    return float(min(high, max(low, span / window)))


def atempo_chain(speed: float) -> list[str]:
    """FFmpeg ``atempo`` filters whose product is ``speed`` (each factor within 0.5–2)."""
    filters: list[str] = []
    rest = speed
    while rest > 2.0 + 1e-9:
        filters.append("atempo=2.0")
        rest /= 2.0
    while rest < 0.5 - 1e-9:
        filters.append("atempo=0.5")
        rest /= 0.5
    if abs(rest - 1.0) > 1e-9 or not filters:
        filters.append(f"atempo={rest:.6f}")
    return filters


def clip_audio(path: Path, out: Path, timing: ClipTiming, *, length: float, volume: float = 1.0, fade: float = 0.5) -> bool:
    """Write the clip's sound as it plays for ``length`` seconds in a scene to the WAV ``out``
    (48 kHz stereo): ``timing``'s part of the file at its speed (pitch kept), looped when it
    loops (else silence after one pass), at ``volume`` (linear, 1 = as recorded), fading out
    over the last ``fade`` seconds of ``length``. Mono sound plays at full level on both channels
    (like the narration; FFmpeg's own upmix would put it 3 dB down). Returns ``False`` (writing
    nothing) when the file has no sound."""
    info = probe_clip(path)
    if not info.audio:
        return False
    one_pass = max(1, round(timing.length * AUDIO_RATE))
    graph = [
        f"atrim=start={timing.start:.6f}:end={timing.end:.6f}",
        "asetpts=PTS-STARTPTS",
        f"aresample={AUDIO_RATE}",
        *(["pan=stereo|c0=c0|c1=c0"] if info.channels == 1 else []),
        "aformat=sample_fmts=fltp:channel_layouts=stereo",
        *atempo_chain(timing.speed),
        f"apad=whole_len={one_pass}",  # exactly one pass long, so loops stay in step with the picture
        f"atrim=end_sample={one_pass}",
        f"volume={volume:.4f}",
    ]
    if timing.loop:
        graph.append(f"aloop=loop=-1:size={one_pass}")
    graph += ["apad", f"atrim=end={length:.6f}"]  # silence after a single pass, up to length
    if fade > 0:
        graph.append(f"afade=t=out:st={max(length - fade, 0.0):.6f}:d={fade:.6f}")
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(find_ffmpeg(), ["-i", str(path), "-vn", "-af", ",".join(graph), "-c:a", "pcm_s16le", str(out)], f"reading the sound of {path.name}")
    return True


class ClipReader:
    """Decodes a clip's frames in order and returns the one showing at a time in the file, as an
    RGBA array of ``size`` = (width, height) pixels cut from ``crop`` = (x, y, w, h) fractions of
    the picture. Going back (a loop) or far ahead seeks; only the current frame is kept."""

    #: Jumps further ahead than this (seconds) seek instead of decoding every frame between.
    SEEK_AHEAD = 2.0
    #: Frame times in a file are rounded (WebM: to milliseconds); a frame this close after the
    #: requested time is already the one showing.
    TOLERANCE = 2e-3

    def __init__(self, path: Path, size: tuple[int, int], crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)) -> None:
        self.path = path
        self.size = (max(1, int(size[0])), max(1, int(size[1])))
        self.crop = crop
        self._container: Any = None
        self._stream: Any = None
        self._frames: Iterator[Any] | None = None
        self._current: Any = None  # the av.VideoFrame showing
        self._next: Any = None  # the one after it (None at the end of the file)
        self._pixels: np.ndarray | None = None
        self._pixels_of: Any = None
        #: Counts the frames converted, so a picture made from the current one can be reused.
        self.serial = 0

    def _open(self) -> None:
        try:
            self._container = av.open(str(self.path))
        except (OSError, av.error.FFmpegError) as exc:
            raise VidgenError(f"cannot read video {self.path.name}: {exc}") from None
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"

    def _decode_from(self, t: float) -> None:
        """(Re)start decoding at the key frame before ``t``."""
        if self._container is None:
            self._open()
        if t > 0 and self._stream.time_base is not None:
            self._container.seek(int(t / self._stream.time_base), stream=self._stream, backward=True)
        else:
            self._container.seek(0)
        self._frames = self._container.decode(self._stream)
        self._current = next(self._frames, None)
        self._next = next(self._frames, None)
        if self._current is None:
            raise VidgenError(f"cannot read video {self.path.name}: no frames at {t:.2f} s")

    def _frame(self, t: float) -> Any:
        if self._frames is None or t < self._current.time - 1e-6 or (self._next is not None and t > self._next.time + self.SEEK_AHEAD):
            self._decode_from(t)
        while self._next is not None and self._next.time <= t + self.TOLERANCE:
            self._current, self._next = self._next, next(self._frames, None)  # type: ignore[arg-type]
        return self._current

    def frame(self, t: float) -> np.ndarray:
        """The picture showing at ``t`` seconds into the file (the last frame after the end)."""
        frame = self._frame(t)
        if frame is not self._pixels_of:
            self._pixels = self._convert(frame)
            self._pixels_of = frame
            self.serial += 1
        assert self._pixels is not None
        return self._pixels

    def _convert(self, frame: Any) -> np.ndarray:
        """Scale (FFmpeg) so the crop is ``size``, then cut the crop out."""
        w, h = self.size
        cx, cy, cw, ch = self.crop
        full_w, full_h = max(w, round(w / cw)), max(h, round(h / ch))
        pixels = frame.to_ndarray(width=full_w, height=full_h, format="rgba")
        x0 = min(max(round(cx * full_w), 0), full_w - w)
        y0 = min(max(round(cy * full_h), 0), full_h - h)
        return np.ascontiguousarray(pixels[y0 : y0 + h, x0 : x0 + w])

    def close(self) -> None:
        """Release the file."""
        if self._container is not None:
            self._container.close()
        self._container = self._stream = self._frames = self._current = self._next = None


class _Playback:
    """What every copy of a :class:`ClipMobject` shares: the reader, the timing, the clock.
    ``copy.deepcopy`` (Manim's ``Mobject.copy``) returns it as it is."""

    def __init__(self, path: Path, info: ClipInfo, timing: ClipTiming) -> None:
        self.path = path
        self.info = info
        self.timing = timing
        self.crop = (0.0, 0.0, 1.0, 1.0)
        self.size: tuple[int, int] | None = None
        self.reader: ClipReader | None = None
        self.clock: Callable[[], float] | None = None
        self.started = 0.0

    def __deepcopy__(self, memo: dict[int, Any]) -> _Playback:
        return self

    def played(self) -> float:
        """Seconds since the clip started playing (0 before it starts or without a clock)."""
        return 0.0 if self.clock is None else max(self.clock() - self.started, 0.0)

    def pixels(self, shown: tuple[int, int]) -> tuple[np.ndarray, int]:
        """The frame showing now and its serial number (see :attr:`ClipReader.serial`)."""
        if self.reader is None:
            self.reader = ClipReader(self.path, self.size or shown, self.crop)
        frame = self.reader.frame(self.timing.source_time(self.played()))
        return frame, self.reader.serial

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
            self.reader = None


def _playing(mob: ImageMobject, dt: float) -> None:
    """A time-based updater: it makes Manim redraw the clip on every frame (a mobject without
    one is drawn once into a static background, and a wait would repeat a frozen frame)."""


class ClipMobject(ImageMobject):
    """A video clip as an image whose picture follows the scene's clock (see the module doc).

    ``ClipMobject(path, timing=None, height=2.0)``: ``timing`` defaults to the whole clip at
    normal speed, holding its last frame. Size and place it like any mobject (its aspect ratio
    is the clip's; :meth:`fit_box` fits or fills a box), call :meth:`set_resolution` if it will
    be zoomed (default: decoded at the size it has on screen when it is first drawn), then
    :meth:`play` with the scene before the frames it should play in; :meth:`close` after
    rendering. Copies share the playback.
    """

    def __init__(self, path: Path | str, timing: ClipTiming | None = None, *, height: float = 2.0, **kwargs: Any) -> None:
        path = Path(path)
        info = probe_clip(path)
        super().__init__(_IDENTITY.copy(), **kwargs)  # the modulation (get_pixel_array shows frames once live)
        self.playback = _Playback(path, info, timing or ClipTiming(0.0, info.duration))
        self.stretch_to_fit_height(height)
        self.stretch_to_fit_width(height * info.aspect)
        self.add_updater(_playing)
        self._shown_key: tuple[Any, ...] | None = None
        self._shown: np.ndarray | None = None
        self._live = True

    @property
    def resampling_algorithm(self) -> Any:
        """How Manim's camera resamples the frames: nearest pixel when they are decoded at the
        size shown (an exact copy, ~15x faster than bicubic), else bilinear."""
        playback = self.__dict__.get("playback")
        if playback is None:
            return self.__dict__.get("_resampling", PILImage.Resampling.BICUBIC)
        exact = playback.size is None or playback.size == self.shown_pixels()
        return PILImage.Resampling.NEAREST if exact else PILImage.Resampling.BILINEAR

    @resampling_algorithm.setter
    def resampling_algorithm(self, value: Any) -> None:
        self.__dict__["_resampling"] = value

    @property
    def info(self) -> ClipInfo:
        """The clip's :class:`ClipInfo`."""
        return self.playback.info

    @property
    def timing(self) -> ClipTiming:
        """The part of the clip that plays and how (:class:`ClipTiming`)."""
        return self.playback.timing

    @property
    def crop(self) -> tuple[float, float, float, float]:
        """The part of the picture shown, ``(x, y, w, h)`` fractions from its top-left corner."""
        return self.playback.crop

    def fit_box(self, width: float, height: float, fit: str = "contain") -> ClipMobject:
        """Size the clip for a ``width`` x ``height`` box: ``contain`` shows the whole picture
        as large as fits; ``cover`` fills the box, cutting the picture's excess equally from
        both sides. Call before the clip is first drawn."""
        aspect = self.info.aspect
        if fit == "cover":
            box = width / height
            if box > aspect:  # wider box: cut top and bottom
                h = aspect / box
                self.playback.crop = (0.0, (1 - h) / 2, 1.0, h)
            else:
                w = box / aspect
                self.playback.crop = ((1 - w) / 2, 0.0, w, 1.0)
            w_shown, h_shown = width, height
        elif fit == "contain":
            self.playback.crop = (0.0, 0.0, 1.0, 1.0)
            w_shown = min(width, height * aspect)
            h_shown = w_shown / aspect
        else:
            raise VidgenError(f"unknown fit {fit!r}; use contain or cover")
        self.stretch_to_fit_width(w_shown)
        self.stretch_to_fit_height(h_shown)
        return self

    def shown_pixels(self) -> tuple[int, int]:
        """The clip's size on the output frame in pixels (at the full-frame camera)."""
        per_unit = config.pixel_width / config.frame_width
        return max(1, round(self.width * per_unit)), max(1, round(self.height * per_unit))

    def set_resolution(self, scale: float = 1.0) -> ClipMobject:
        """Decode frames at up to ``scale`` x the size shown (for a camera that zooms in) when the
        clip has that many pixels inside the crop, and at least at the size shown (FFmpeg scales
        a small clip up once per frame; the camera then copies it pixel for pixel). Call before
        the clip is first drawn."""
        w, h = self.shown_pixels()
        _, _, cw, ch = self.crop
        detail = min(self.info.width * cw / w, self.info.height * ch / h)
        k = max(1.0, min(scale, detail))
        self.playback.size = (max(1, round(w * k)), max(1, round(h * k)))
        return self

    def play(self, scene: Any, at: float | None = None) -> ClipMobject:
        """Tie playback to ``scene``'s clock: the clip starts at scene time ``at`` (default: now)."""
        renderer = scene.renderer
        self.playback.clock = lambda: float(renderer.time)
        self.playback.started = float(renderer.time) if at is None else at
        return self

    def playback_time(self) -> float:
        """The time in the file shown now."""
        return self.timing.source_time(self.playback.played())

    def get_pixel_array(self) -> np.ndarray:
        """The current frame with this mobject's opacity / tint (its modulation) applied."""
        if not getattr(self, "_live", False):  # inside ImageMobject.__init__
            return self.pixel_array
        frame, serial = self.playback.pixels(self.shown_pixels())
        mod = self.pixel_array
        key = (id(self.playback.reader), serial, mod.tobytes())
        if key == self._shown_key and self._shown is not None:
            return self._shown
        if np.array_equal(mod, _IDENTITY):
            shown = frame
        else:
            black = mod[0, 0].astype(np.float32)
            white = mod[0, 1].astype(np.float32)
            shown = np.clip(black + frame.astype(np.float32) * ((white - black) / 255.0), 0, 255).astype(np.uint8)
        self._shown_key, self._shown = key, shown
        return shown

    def close(self) -> None:
        """Release the clip file (after rendering)."""
        self.playback.close()
