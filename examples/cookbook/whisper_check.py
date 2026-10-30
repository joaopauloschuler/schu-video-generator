"""Transcribe narration clips with faster-whisper, to check how names and terms are pronounced.

An optional standalone check next to ``vidgen readback`` (it pads each clip with silence and
prints the bare transcript). It is a stand-alone tool: run it from the project folder, do NOT put it in
extensions/ (schu-video-generator imports every .py file there).

    pip install faster-whisper            # once; needs ffmpeg on PATH
    python whisper_check.py audio/*.mp3
    python whisper_check.py --model small --pad 0.8 audio/intro_b1.mp3

Each line prints ``<file> | <transcript>``. Compare it with the beat text by ear and eye: judge
how a word sounds, not how Whisper spells it (an unusual name written phonetically is a pass).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def decode(path: str, pad: float):
    """Decode ``path`` to 16 kHz mono float32 with ffmpeg, with ``pad`` seconds of silence in
    front (Whisper tends to drop the first words of a clip that starts immediately)."""
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)
    return np.concatenate([np.zeros(int(pad * 16000), np.float32), audio])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="audio files (MP3, WAV, ...)")
    ap.add_argument("--model", default="small.en", help="faster-whisper model (default: small.en; "
                    "small.en is more reliable than the multilingual small for English narration)")
    ap.add_argument("--language", default="en")
    ap.add_argument("--pad", type=float, default=0.8, help="seconds of silence added in front (default 0.8)")
    args = ap.parse_args(argv)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed: pip install faster-whisper", file=sys.stderr)
        return 2
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    for f in args.files:
        segments, _ = model.transcribe(decode(f, args.pad), language=args.language, beam_size=5)
        print(os.path.basename(f), "|", " ".join(s.text.strip() for s in segments))
    return 0


if __name__ == "__main__":
    sys.exit(main())
