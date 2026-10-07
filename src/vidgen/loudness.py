"""Loudness of long signals (DESIGN.md §48): EBU R128 / ITU-R BS.1770-4 integrated loudness and
true peak, measured block by block so a whole video's audio never has to sit in memory.

Everything is plain numpy and deterministic. K-weighting is applied as the filter's magnitude
response in the frequency domain (as :func:`vidgen.sfx.loudness` does) on blocks read with a
margin on each side, so block edges do not disturb it. True peak is the largest absolute value
of the signal upsampled 4x with a windowed-sinc interpolator (BS.1770-4 Annex 2).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from functools import lru_cache

import numpy as np

from vidgen.sfx import RATE, _k_weighting

#: Gating block (400 ms) and its step (100 ms, 75 % overlap) of the integrated loudness.
GATE_BLOCK = int(0.4 * RATE)
GATE_STEP = int(0.1 * RATE)
#: Absolute gate (LUFS) and relative gate (LU below the absolutely gated loudness).
ABSOLUTE_GATE = -70.0
RELATIVE_GATE = -10.0
#: Samples processed at once by the block-wise functions (10 s) and the margin read on each side.
BLOCK = RATE * 10
MARGIN = RATE // 2
#: True-peak oversampling and the interpolator's half length in input samples.
OVERSAMPLE = 4
_TAPS_HALF = 12


def _interpolator() -> list[np.ndarray]:
    """The polyphase parts (phases 1-3; phase 0 is the signal itself) of a Kaiser-windowed sinc
    low-pass for 4x upsampling."""
    k = np.arange(-_TAPS_HALF * OVERSAMPLE, _TAPS_HALF * OVERSAMPLE + 1)
    h = np.sinc(k / OVERSAMPLE) * np.kaiser(len(k), 8.0)
    return [h[p::OVERSAMPLE].copy() for p in range(1, OVERSAMPLE)]


_PHASES = _interpolator()


def peak_envelope(x: np.ndarray) -> np.ndarray:
    """Per sample of ``x`` (``(n, c)``), the largest absolute value of the 4x-upsampled signal
    between this sample and the next, over all channels (the true-peak envelope)."""
    env = np.max(np.abs(x), axis=1)
    for c in range(x.shape[1]):
        for h in _PHASES:
            # phase p lies between samples n and n+1; its taps cover n-11 .. n+12
            y = np.convolve(x[:, c], h, mode="full")[_TAPS_HALF : _TAPS_HALF + len(x)]
            np.maximum(env, np.abs(y), out=env)
    return env


@lru_cache(maxsize=8)
def _k_response(size: int) -> np.ndarray:
    return _k_weighting(np.fft.rfftfreq(size, 1 / RATE))


def kweighted_power(x: np.ndarray) -> np.ndarray:
    """Per sample, the K-weighted power of ``x`` (``(n, c)``) summed over its channels.

    The filter is applied circularly over ``x`` (fast; its response dies out within ~50 ms), so
    callers discard a margin at both ends (:func:`blocks`)."""
    spectra = np.fft.rfft(x, axis=0) * _k_response(len(x))[:, None]
    return np.sum(np.fft.irfft(spectra, len(x), axis=0) ** 2, axis=1)


class LoudnessMeter:
    """Integrated loudness and true peak of a signal fed in order, block by block.

    :meth:`add` takes K-weighted power (:func:`kweighted_power`) and the true-peak envelope
    (or plain samples via :meth:`add_samples`); :attr:`integrated` and :attr:`true_peak` give
    the results so far.
    """

    def __init__(self) -> None:
        self._steps: list[float] = []  # summed power of every complete 100 ms step
        self._partial = 0.0
        self._filled = 0
        self._peak = 0.0

    def add(self, power: np.ndarray, envelope: np.ndarray) -> None:
        """Feed the next samples' K-weighted power and true-peak envelope."""
        if envelope.size:
            self._peak = max(self._peak, float(envelope.max()))
        pos = 0
        n = len(power)
        if self._filled:
            take = min(GATE_STEP - self._filled, n)
            self._partial += float(power[:take].sum())
            self._filled += take
            pos = take
            if self._filled == GATE_STEP:
                self._steps.append(self._partial)
                self._partial, self._filled = 0.0, 0
        whole = (n - pos) // GATE_STEP
        if whole:
            sums = power[pos : pos + whole * GATE_STEP].reshape(whole, GATE_STEP).sum(axis=1)
            self._steps.extend(float(v) for v in sums)
            pos += whole * GATE_STEP
        if pos < n:
            self._partial += float(power[pos:].sum())
            self._filled += n - pos

    @property
    def integrated(self) -> float:
        """Gated integrated loudness in LUFS (``-inf`` for silence or less than 400 ms)."""
        steps = np.asarray(self._steps)
        if len(steps) < 4:
            return -math.inf
        blocks = (steps[:-3] + steps[1:-2] + steps[2:-1] + steps[3:]) / GATE_BLOCK
        with np.errstate(divide="ignore"):
            levels = -0.691 + 10 * np.log10(blocks)
        kept = blocks[levels > ABSOLUTE_GATE]
        if not len(kept):
            return -math.inf
        relative = -0.691 + 10 * math.log10(float(kept.mean())) + RELATIVE_GATE
        kept = blocks[(levels > ABSOLUTE_GATE) & (levels > relative)]
        return -0.691 + 10 * math.log10(float(kept.mean()))

    @property
    def true_peak(self) -> float:
        """The highest true peak so far in dBTP (``-inf`` for silence)."""
        return 20 * math.log10(self._peak) if self._peak > 0 else -math.inf


def blocks(n: int, read: Callable[[int, int], np.ndarray], margin: int = MARGIN, size: int = BLOCK) -> Iterator[tuple[int, int, np.ndarray]]:
    """Yield ``(lo, hi, extended)`` for consecutive blocks of a signal of ``n`` samples:
    ``extended`` holds samples ``lo - margin`` to ``hi + margin`` (``read(a, b)`` within ``[0, n]``,
    zeros outside), so ``extended[margin : margin + hi - lo]`` is the block."""
    for lo in range(0, n, size):
        hi = min(n, lo + size)
        a, b = max(0, lo - margin), min(n, hi + margin)
        data = read(a, b)
        ext = np.zeros((hi - lo + 2 * margin, data.shape[1]), dtype=np.float64)
        ext[a - (lo - margin) : a - (lo - margin) + (b - a)] = data
        yield lo, hi, ext


def measure(n: int, read: Callable[[int, int], np.ndarray], peaks: bool = True) -> LoudnessMeter:
    """A :class:`LoudnessMeter` fed with a whole signal of ``n`` samples read block by block
    (``read(a, b)`` → ``(b - a, channels)`` floats); ``peaks=False`` skips the true peak (faster;
    the meter's peak is then that of the samples)."""
    meter = LoudnessMeter()
    for lo, hi, ext in blocks(n, read):
        part = slice(MARGIN, MARGIN + hi - lo)
        envelope = peak_envelope(ext)[part] if peaks else np.max(np.abs(ext[part]), axis=1)
        meter.add(kweighted_power(ext)[part], envelope)
    return meter


def integrated_loudness(samples: np.ndarray) -> float:
    """Integrated loudness (LUFS) of a whole signal in memory (mono ``(n,)`` or ``(n, c)``)."""
    x = samples.reshape(len(samples), -1)
    return measure(len(x), lambda a, b: x[a:b], peaks=False).integrated
