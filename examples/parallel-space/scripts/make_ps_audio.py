#!/usr/bin/env python3
"""Rebuild extensions/ps_audio.json: everything the pictures know about the music.

The visuals (extensions/ps.js) never hear the track. They read this JSON file instead:

* measured from the rendered WAV, one value per video frame (30 fps): 16 spectrum bands, the
  overall level, the level under 150 Hz and the onset strength (how much the spectrum grew
  since the frame before);
* read from the score file: the sections, and when the notes that the pictures follow are played
  (kick, big drums, the far frame drum, booms, claps, ticks, and every note of the hook, the lead,
  the far choir (the track named trumpet), the violas on the hook (the track named violins), the
  string swells and the horn with its pitch), on the score's grid of sixteenth notes.

You only need to run it after changing the score. The copy shipped with the project matches
assets/music/parallel_space.yaml.

Usage (from the project folder; needs vidgen's own Python environment, which has numpy):

    vidgen music render assets/music/parallel_space.yaml --out build/parallel_space.wav
    python scripts/make_ps_audio.py build/parallel_space.wav extensions/ps_audio.json

A third argument names another score file (default: assets/music/parallel_space.yaml).
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

FPS = 30
WIN = 4096
N_BANDS = 16
FMIN, FMAX = 40.0, 12000.0
#: 64 printable characters: one character is one value from 0 to 63.
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
#: Drum tracks whose hits are exported under their own names.
HIT_TRACKS = ("kick", "taiko", "tom", "boom", "clap", "snare", "crash", "tick", "roll", "frame")
#: Melodic tracks whose notes are exported: name in the JSON -> the score tracks it gathers. "call" is
#: what the star glints follow: the far choir (track "trumpet": dawn, groove, coda) and the violas on the
#: hook (track "violins": heart2, climax). v7 sings and bows them one or two octaves under v6, so ps.js
#: places the glints by pitch minus the lowered offsets.
NOTE_TRACKS = {"hook": ("hook",), "lead": ("lead",), "call": ("trumpet", "violins"), "horn": ("horn",),
               "swell": ("swell",), "vla": ("vla",)}
DEFAULT_SCORE = Path(__file__).resolve().parent.parent / "assets" / "music" / "parallel_space.yaml"


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """The WAV's samples as one mono float array, and its sample rate (16, 24 or 32 bit PCM)."""
    with wave.open(str(path), "rb") as w:
        rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(frames)
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 2**15
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) - ((b[:, 2] & 0x80) << 17)).astype(np.float64) / 2**23
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2**31
    else:
        raise SystemExit(f"{path}: {8 * width}-bit WAV files are not read (use 16, 24 or 32 bit PCM)")
    return x.reshape(-1, channels).mean(axis=1), rate


def encode(values: np.ndarray) -> str:
    """Values from 0 to 1 as one character each."""
    q = np.clip(np.round(np.asarray(values) * 63), 0, 63).astype(int)
    return "".join(ALPHABET[v] for v in q.ravel())


def released(x: np.ndarray, keep: float) -> np.ndarray:
    """Fast attack, slow release: a value falls to ``keep`` of itself per frame at most."""
    out = np.zeros_like(x)
    for i in range(len(x)):
        out[i] = x[i] if i == 0 else np.maximum(x[i], out[i - 1] * keep + x[i] * (1 - keep))
    return out


def analyse(wav_path: Path) -> dict:
    x, rate = read_wav(wav_path)
    hop = rate // FPS
    n = int(np.ceil(len(x) / hop)) + 2
    edges = np.geomspace(FMIN, FMAX, N_BANDS + 1)
    freqs = np.fft.rfftfreq(WIN, 1 / rate)
    masks = [(freqs >= edges[i]) & (freqs < edges[i + 1]) for i in range(N_BANDS)]
    low_mask, all_mask = (freqs >= 25) & (freqs < 150), (freqs >= 25) & (freqs < 14000)
    window = np.hanning(WIN)
    padded = np.pad(x, (WIN // 2, WIN + hop))
    power = np.zeros((n, N_BANDS))
    level, low, flux = np.zeros(n), np.zeros(n), np.zeros(n)
    before = None
    for f in range(n):
        seg = padded[f * hop : f * hop + WIN]
        spectrum = np.abs(np.fft.rfft(seg * window)) ** 2
        power[f] = [10 * np.log10(spectrum[m].mean() + 1e-12) for m in masks]
        level[f] = 10 * np.log10(spectrum[all_mask].sum() + 1e-12)
        low[f] = 10 * np.log10(spectrum[low_mask].sum() + 1e-12)
        log_spec = np.log10(spectrum[all_mask] + 1e-9)
        flux[f] = 0.0 if before is None else np.maximum(log_spec - before, 0).mean()
        before = log_spec
    bands = np.zeros_like(power)
    for b in range(N_BANDS):
        lo, hi = np.percentile(power[:, b], 20), np.percentile(power[:, b], 99.5)
        bands[:, b] = np.clip((power[:, b] - lo) / (hi - lo + 1e-9), 0, 1)
    bands = released(bands, 0.82)
    top = np.percentile(level, 99.5)
    level = released(np.clip((level - (top - 36)) / 36, 0, 1), 0.9)        # 36 dB under the loudest frames -> 0
    top = np.percentile(low, 99.5)
    low = released(np.clip((low - (top - 30)) / 30, 0, 1), 0.8)
    flux = released(np.clip(flux / (np.percentile(flux, 99.7) + 1e-9), 0, 1), 0.7)
    return {"fps": FPS, "n": int(n), "nbands": N_BANDS, "alphabet": ALPHABET,
            "bands": encode(bands), "level": encode(level), "low": encode(low), "flux": encode(flux)}


def score_events(score_path: Path) -> dict:
    """Sections and note times of the score, on its grid of sixteenth notes (16 per 4/4 bar)."""
    from vidgen.studio import load_music_score

    score = load_music_score(score_path)
    per_bar = 16
    sections = [{"name": s.name, "bar": s.first_bar, "bars": s.bars} for s in score.sections]
    tracks = {t.name: t for t in score.tracks}
    hits: dict[str, list] = {}
    notes: dict[str, list] = {}
    tidy = lambda v: int(v) if float(v).is_integer() else round(float(v), 3)

    def events(name: str) -> list[list[float]]:
        """The notes of one score track: [sixteenth, length, MIDI pitch (0: a chord degree), gain]."""
        track = tracks.get(name)
        out: list[list[float]] = []
        if track is None:
            return out
        current = None
        previous_section_end = None
        for section in score.sections:
            part = track.parts.get(section.name)
            if part is None or part.steps is None:
                current = None
                continue
            if previous_section_end != section.first_bar:
                current = None                       # a hold only carries on from the section just before
            for b in range(section.bars):
                bar_steps = part.steps[b % len(part.steps)]
                for k, step in enumerate(bar_steps):
                    at = (section.first_bar + b) * per_bar + k * per_bar / len(bar_steps)
                    length = per_bar / len(bar_steps)
                    if step.kind == "hold":
                        if current is not None:
                            current[1] += length
                        continue
                    if step.kind == "rest":
                        current = None
                        continue
                    pitch = step.value + part.transpose if step.kind == "note" else 0
                    current = [at, length, pitch, round(step.gain, 2)]
                    out.append(current)
            previous_section_end = section.first_bar + section.bars
        return out

    for name in HIT_TRACKS:
        if name in tracks:
            hits[name] = [[tidy(e[0]), tidy(e[3])] for e in events(name)]                  # [sixteenth, gain]
    for name, sources in NOTE_TRACKS.items():
        gathered = sorted((e for source in sources for e in events(source)), key=lambda e: e[0])
        if gathered:
            notes[name] = [[tidy(e[0]), tidy(e[1]), int(e[2])] for e in gathered]         # [sixteenth, length, MIDI pitch]
    return {"bars": score.bars, "bar_seconds": score.bar / 48000, "sections": sections, "hits": hits, "notes": notes}


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    score_path = Path(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_SCORE
    data = {"version": 7, **analyse(src), **score_events(score_path)}
    bar_frames = data["bar_seconds"] * FPS
    if abs(bar_frames - round(bar_frames)) > 1e-6:
        print(f"warning: one bar is {bar_frames:.4f} frames, not a whole number: the pictures drift from the music", file=sys.stderr)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {dest}: {data['n']} frames at {FPS} fps, {N_BANDS} bands, {data['bars']} bars, "
          f"{sum(len(v) for v in data['hits'].values())} hits, {sum(len(v) for v in data['notes'].values())} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
