"""The file of an audio-only render (DESIGN.md §111.1): ``build/<render>/audio/mix.wav`` (48 kHz
stereo 24-bit) encoded by the ``ffmpeg`` executable as ``audio_output`` asks: WAV (16 or 24-bit
PCM), MP3 (LAME, constant bitrate), M4A (AAC) or Ogg Opus; mono (the channels' average) or
stereo; resampled to ``sample_rate``; tagged with ``metadata`` (the title, artist, album...).
No chapters are embedded.
"""

from __future__ import annotations

from pathlib import Path

from vidgen.config import AudioOutputConfig
from vidgen.fileio import remove_file, replace_file

#: Per format: the file suffix, ffmpeg's muxer, its encoder and extra arguments.
FORMATS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "wav": (".wav", "wav", "pcm_s24le", ("-rf64", "auto")),
    "mp3": (".mp3", "mp3", "libmp3lame", ("-id3v2_version", "3")),
    "m4a": (".m4a", "ipod", "aac", ("-movflags", "+faststart")),
    "ogg": (".ogg", "ogg", "libopus", ()),
}
#: The encoders that are not in every ffmpeg build, for the error message.
EXTERNAL = {"mp3": "libmp3lame", "ogg": "libopus"}


def suffix(out: AudioOutputConfig) -> str:
    """The file suffix of ``out``'s format (``.wav``, ``.mp3``, ``.m4a``, ``.ogg``)."""
    return FORMATS[out.format][0]


def encode_args(src: Path, dst: Path, out: AudioOutputConfig, tags: dict[str, str]) -> list[str]:
    """ffmpeg's arguments (after ``ffmpeg -y -v error``) that encode ``src`` to ``dst``."""
    _, muxer, codec, extra = FORMATS[out.format]
    if out.format == "wav" and out.bit_depth == 16:
        codec = "pcm_s16le"
    args = ["-i", str(src), "-vn", "-map_metadata", "-1"]
    filters = []
    if out.channels == "mono":
        filters.append("pan=mono|c0=0.5*c0+0.5*c1")
    if out.sample_rate != 48000:
        filters.append(f"aresample={out.sample_rate}")
    if filters:
        args += ["-af", ",".join(filters)]
    args += ["-c:a", codec]
    if out.effective_bitrate is not None:
        args += ["-b:a", out.effective_bitrate]
    for key, value in tags.items():
        args += ["-metadata", f"{key}={value}"]
    return [*args, *extra, "-f", muxer, str(dst)]


def encode(src: Path, dst: Path, out: AudioOutputConfig, tags: dict[str, str]) -> None:
    """Encode the mix ``src`` to ``dst`` (written whole or not at all)."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    partial = dst.with_name(dst.name + ".part")
    dst.parent.mkdir(parents=True, exist_ok=True)
    needs = f" (needs an ffmpeg with {EXTERNAL[out.format]})" if out.format in EXTERNAL else ""
    try:
        run_ffmpeg(find_ffmpeg(), encode_args(src, partial, out, tags), f"encoding {dst.name}{needs}")
    except BaseException:
        remove_file(partial)
        raise
    replace_file(partial, dst)
