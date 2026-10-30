"""The "under narration" toggle (DESIGN.md §94.14, Step 196): a render heard under the narration
sample ``vidgen music check`` ships, with schu-video-generator's default ducking (the check's
:func:`vidgen.studio.check.duck_gain_db`), so a person hears whether the words stay clear.

The voice is repeated from the piece's start over its whole length (the sample is 20 s: speech,
then the music alone for a few seconds). Voice and music keep a video's balance (the voice at
its own level, the music at −28 LUFS, ducked while the voice speaks), both raised by one gain
that puts the voice's true peak at −1.5 dBTP — the same gain for every version, so A/B under
narration is level-matched.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from vidgen.sfx import RATE


@lru_cache(maxsize=1)
def _voice() -> tuple[np.ndarray, float]:
    """The narration sample (stereo float64) and the gain that puts its true peak at the
    check demo's ceiling."""
    from vidgen.loudness import measure
    from vidgen.studio.check import DEMO_TRUE_PEAK, load_narration

    voice, _ = load_narration(None)
    peak = measure(len(voice), lambda a, b: voice[a:b]).true_peak
    return voice, 10 ** ((DEMO_TRUE_PEAK - peak) / 20)


def under_narration(music: np.ndarray) -> np.ndarray:
    """``music`` (float ``(n, 2)`` at −28 LUFS) under the narration sample repeated over it, with
    schu-video-generator's default ducking, both at the voice's gain (see the module): float64 ``(n, 2)``,
    not clipped."""
    from vidgen.studio.check import duck_gain_db, speech_spans

    voice, gain = _voice()
    n = len(music)
    repeated = voice[np.arange(n) % len(voice)]
    frames = n // (RATE // 100) + 2
    duck_db = np.interp(np.arange(n) / (RATE // 100), np.arange(frames), duck_gain_db(speech_spans(repeated), frames))
    return (repeated + np.asarray(music, dtype=np.float64) * (10 ** (duck_db / 20))[:, None]) * gain
