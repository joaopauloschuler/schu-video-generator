"""Composed music played with real instruments (DESIGN.md §81, §82): symusic (optional extra
``music``) renders a :class:`~vidgen.score.Score` with a SoundFont (:mod:`vidgen.soundfont`).
Nothing here imports symusic until it is needed.

symusic 0.5.9 ignores MIDI volume, pan and reverb, stops at the last note's release and returns
floats that can exceed 1, so :func:`render_score` renders each part on its own and mixes them in
numpy: the part's volume, a constant-power pan, a send to one generated reverb, a tail, and the
result set to the music level (:data:`vidgen.music.MUSIC_LEVEL`) under a true-peak ceiling.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import tempfile
import zlib
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen import DIST_NAME
from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.score import Score

INSTALL_COMMAND = f'pip install "{DIST_NAME}[music]"'
#: The symusic release the extra pins; 0.6.0's SoundFont render fails (TypeError in ``render``).
SYMUSIC_VERSION = "0.5.9"
#: Bumped when the mixing below changes, so cached renders are made again.
RENDERER_VERSION = 1
#: Seconds added after the score's end for the notes' release and the reverb to die away.
TAIL_SECONDS = 3.0
#: The generated reverb: impulse length, decay time to -60 dB, pre-delay (seconds) and the
#: low-pass (Hz) that darkens it.
REVERB_SECONDS = 2.0
REVERB_RT60 = 1.6
REVERB_PREDELAY = 0.012
REVERB_LOWPASS = 5000.0
#: Integrated loudness (LUFS) every part of a ``balance`` score is set to before its volume.
BALANCE_LEVEL = -28.0
#: The rendered music's true peak stays under this (dBTP); at -28 LUFS it is rarely reached.
TRUE_PEAK_CEILING = -1.0
#: Samples per block of the reverb's FFT convolution (overlap-add).
_CONVOLUTION_BLOCK = 1 << 18


def symusic_version() -> str | None:
    """The installed symusic version, or ``None`` when it is not installed."""
    try:
        return importlib.metadata.version("symusic")
    except importlib.metadata.PackageNotFoundError:
        return None


def symusic_status() -> str:
    """One line on symusic: installed and usable, another version, or how to install it."""
    version = symusic_version()
    if version is None:
        return f"not installed: {INSTALL_COMMAND}"
    if version != SYMUSIC_VERSION:
        return f"{version} installed, but vidgen needs {SYMUSIC_VERSION}: {INSTALL_COMMAND}"
    return version


def require_symusic() -> Any:
    """Import and return the ``symusic`` module; :class:`VidgenError` naming the extra when it is
    missing or another version than :data:`SYMUSIC_VERSION` is installed."""
    version = symusic_version()
    if version is None:
        raise VidgenError(f"composed music needs the optional extra: {INSTALL_COMMAND} (symusic {SYMUSIC_VERSION}, ~3 MB)")
    if version != SYMUSIC_VERSION:
        raise VidgenError(
            f"composed music needs symusic {SYMUSIC_VERSION}, and {version} is installed "
            f"(0.6.0 cannot render with a SoundFont): {INSTALL_COMMAND}"
        )
    import symusic

    return symusic


# ----- mixing (numpy) ------------------------------------------------------------------------------


def pan_gains(pan: float) -> tuple[float, float]:
    """Left and right gains of a constant-power pan (``pan`` -1 left to 1 right): 1 and 1 at the
    centre, 0 and sqrt(2) fully right."""
    angle = (pan + 1) * math.pi / 4
    return math.sqrt(2) * math.cos(angle), math.sqrt(2) * math.sin(angle)


@lru_cache(maxsize=1)
def reverb_impulse() -> np.ndarray:
    """The generated reverb's impulse response, float64 ``(n, 2)``, read-only: per channel its own
    seeded noise, low-passed at :data:`REVERB_LOWPASS`, decaying by 60 dB over
    :data:`REVERB_RT60` after :data:`REVERB_PREDELAY`, scaled to unit energy (a send of
    level ``w`` comes back about as loud as ``w``)."""
    from vidgen.sfx import RATE, _filtered, _lowpass

    rng = np.random.default_rng(zlib.crc32(b"vidgen:reverb"))
    n = round(REVERB_SECONDS * RATE)
    delay = round(REVERB_PREDELAY * RATE)
    t = np.arange(n - delay) / RATE
    envelope = np.exp(-math.log(1000) * t / REVERB_RT60) * (1 - np.exp(-t / 0.004))
    impulse = np.zeros((n, 2))
    for c in range(2):
        tail = _filtered(rng.standard_normal(n - delay), lambda f: _lowpass(f, REVERB_LOWPASS, 2)) * envelope
        impulse[delay:, c] = tail / math.sqrt(float(np.sum(tail**2)))
    impulse.setflags(write=False)
    return impulse


def convolve(x: np.ndarray, impulse: np.ndarray) -> np.ndarray:
    """``x`` ``(n, 2)`` convolved channel by channel with ``impulse`` ``(m, 2)`` (FFT blocks,
    overlap-add; silent blocks skipped); the first ``n`` samples."""
    n, m = len(x), len(impulse)
    size = 1 << (_CONVOLUTION_BLOCK + m - 2).bit_length()
    response = np.fft.rfft(impulse, size, axis=0)
    out = np.zeros((n + m, x.shape[1]))
    for lo in range(0, n, _CONVOLUTION_BLOCK):
        block = x[lo : lo + _CONVOLUTION_BLOCK]
        if not block.any():
            continue
        count = len(block) + m - 1
        out[lo : lo + count] += np.fft.irfft(np.fft.rfft(block, size, axis=0) * response, size, axis=0)[:count]
    return out[:n]


def mix_parts(score: Score, rendered: Iterable[np.ndarray | None]) -> np.ndarray:
    """The parts' dry renders (``rendered``: float ``(n, 2)`` at 48 kHz from the score's start,
    in ``score.parts`` order, ``None`` for a part without notes) mixed: each at its ``volume``
    (with ``score.balance``, after being set to :data:`BALANCE_LEVEL`) and ``pan``, a
    ``reverb`` share of it sent to :func:`reverb_impulse`, cut or padded to the score's length
    plus :data:`TAIL_SECONDS`, the last 20 ms faded out, then set to
    :data:`~vidgen.music.MUSIC_LEVEL` under :data:`TRUE_PEAK_CEILING`. Float64 ``(n, 2)``."""
    from vidgen.loudness import integrated_loudness
    from vidgen.sfx import RATE

    total = round((score.length_seconds + TAIL_SECONDS) * RATE)
    dry = np.zeros((total, 2))
    send = np.zeros((total, 2))
    for part, audio in zip(score.parts, rendered):
        if audio is None:
            continue
        take = min(total, len(audio))
        gain_db = part.volume
        if score.balance:
            level = integrated_loudness(audio[:take])
            gain_db += BALANCE_LEVEL - level if math.isfinite(level) else 0.0
        x = audio[:take] * (10 ** (gain_db / 20) * np.array(pan_gains(part.pan)))
        dry[:take] += x
        if part.reverb > 0:
            send[:take] += part.reverb * x
    mixed = dry + convolve(send, reverb_impulse()) if send.any() else dry
    fade = min(total, RATE // 50)
    mixed[total - fade :] *= np.linspace(1.0, 0.0, fade)[:, None]
    return _to_music_level(mixed)


def _to_music_level(x: np.ndarray) -> np.ndarray:
    """``x`` scaled to the music level, its true peaks then limited to :data:`TRUE_PEAK_CEILING`."""
    from vidgen.loudness import integrated_loudness, peak_envelope
    from vidgen.mix import limit
    from vidgen.music import MUSIC_LEVEL

    level = integrated_loudness(x)
    if not math.isfinite(level):
        raise VidgenError("score: the rendered music is silent (are the notes' velocities and the parts' volumes too low?)")
    y = x * 10 ** ((MUSIC_LEVEL - level) / 20)
    ceiling = 10 ** (TRUE_PEAK_CEILING / 20)
    if float(peak_envelope(y).max()) > ceiling:
        y, _ = limit(y, ceiling)
    return y


# ----- rendering -----------------------------------------------------------------------------------


def render_key(score: Score, soundfont_sha256: str) -> str:
    """The cache key (SHA-256 hex) of a render: the score's fingerprint, the symusic version, the
    SoundFont's SHA-256 and :data:`RENDERER_VERSION`."""
    from vidgen.sfx import RATE

    data = {
        "score": score.fingerprint(),
        "symusic": symusic_version(),
        "soundfont": soundfont_sha256,
        "renderer": RENDERER_VERSION,
        "rate": RATE,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _synthesizer(path: str, sha256: str) -> Any:
    """symusic's synthesizer for the SoundFont at ``path`` (``sha256``: so a changed file is
    loaded again), at 48 kHz."""
    from vidgen.sfx import RATE

    return require_symusic().Synthesizer(path, RATE, 0)


def _pcm16(x: np.ndarray) -> np.ndarray:
    """``x`` as the cached 16-bit WAV holds it (what :func:`_read_pcm16` returns): float32,
    read-only."""
    y = (np.clip(np.round(x * 32767), -32768, 32767) / 32767).astype(np.float32)
    y.setflags(write=False)
    return y


def _read_pcm16(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path), "rb") as src:
        data = np.frombuffer(src.readframes(src.getnframes()), dtype="<i2").reshape(-1, src.getnchannels())
    return _pcm16(data / 32767)


def render_score(score: Score, soundfont: Path, cache_dir: Path | None = None) -> np.ndarray:
    """``score`` played with the SoundFont file ``soundfont``: float32 stereo ``(n, 2)`` at 48 kHz,
    the score's length plus :data:`TAIL_SECONDS`, at the music level, read-only (see
    :func:`mix_parts`). With ``cache_dir``, a render is kept there as
    ``score-<render_key>.wav`` (16-bit) and reused. Needs the ``music`` extra."""
    from vidgen.fileio import replace_file
    from vidgen.score import to_symusic
    from vidgen.sfx import write_wav
    from vidgen.soundfont import content_sha256

    require_symusic()
    if not any(part.notes for part in score.parts):
        raise VidgenError("score: it has no notes")
    digest = content_sha256(soundfont)
    path = None if cache_dir is None else cache_dir / f"score-{render_key(score, digest)}.wav"
    if path is not None and path.is_file():
        return _read_pcm16(path)
    synth = _synthesizer(str(soundfont), digest)
    rendered = (
        np.asarray(synth.render(to_symusic(score, (part,), controls=False), stereo=True), dtype=np.float64).T if part.notes else None
        for part in score.parts
    )
    music = _pcm16(mix_parts(score, rendered))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".score-", suffix=".wav", dir=path.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            write_wav(tmp, music)
            replace_file(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return music
