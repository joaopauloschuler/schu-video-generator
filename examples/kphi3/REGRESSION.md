# Regression: vidgen port vs the original kphi3 video

Reference: `kphi3_paper_video/kphi3_video.mp4` (original one-off project: `scenes.py` +
`render.py`, 1920x1080 @ 30 fps, 6932 frames, 231.07 s).
New: `vidgen render examples/kphi3 --jobs 2` (same format; 2 min 40 s on 2 CPUs, 6944 frames,
231.47 s). Measured 2026-10-05 with Manim 0.21.0. `--preview` (854x480 @ 15 fps) renders in 54 s.

## Method

**Original scene boundaries.** The original MP4 has no scene markers, so the original scenes
were re-rendered with the original code (a temporary copy of `scenes.py`, `common.py`,
`script.json`, `audio/`) at 320x180 and the same 30 fps, without caching:
`python -m manim -r 320,180 --fps 30 --disable_caching scenes.py S1Title ...`. Frame counts do
not depend on the resolution, and the eight counts add up to exactly 6932, the frame count of
`kphi3_video.mp4`, so they are the original per-scene lengths.

**Explaining the difference.** The original `narrate()` was instrumented (in that temporary copy)
to log, per beat, the remaining time `rest = d + pad - elapsed` and the frames its
`self.wait(rest)` wrote. The original waits only if `rest > 0.02` and Manim writes
`int(rest × fps)` frames for a still wait, i.e. it truncates. vidgen's `narrate()` waits
`round(rest × fps)` frames (DESIGN §5.2: a beat lasts `d + pad` to within half a frame). The
predicted difference per scene is the sum over its beats of `round(rest×30) - frames written`.

**Frames.** For each of the 27 beats, three frames were compared (early: `min(1 s, d/4)` after
the beat starts; mid: `0.6 d`; end: `d + 0.30 s`). New frame numbers come from
`build/final/timings.json`; the original frame number is the same minus the accumulated
per-beat rounding differences of the earlier beats. Frames were extracted **by frame index**
(`select=eq(n,N)`). Seeking by time is off by one frame in the original, whose video stream
starts at 0.021 s (AAC priming from its old concat). SSIM and PSNR come from ffmpeg's `ssim` and
`psnr` filters, and the frames were also viewed side by side.

## Scene durations

| scene | original | frames | vidgen | frames | diff | predicted from beat rounding |
|---|---|---|---|---|---|---|
| S1Title → `title` | 15.167 s | 455 | 15.233 s | 457 | +2 | +2 |
| S2Sparsity → `sparsity` | 28.233 s | 847 | 28.267 s | 848 | +1 | +1 |
| S3Equivalence → `equivalence` | 29.133 s | 874 | 29.167 s | 875 | +1 | +1 |
| S4Method → `method` | 44.833 s | 1345 | 44.867 s | 1346 | +1 | +1 |
| S5Setup → `setup` | 34.733 s | 1042 | 34.767 s | 1043 | +1 | +1 |
| S6Params → `params` | 21.367 s | 641 | 21.433 s | 643 | +2 | +2 |
| S7Loss → `loss` | 32.467 s | 974 | 32.533 s | 976 | +2 | +2 |
| S8Conclusion → `conclusion` | 25.133 s | 754 | 25.200 s | 756 | +2 | +2 |
| **total** | **231.067 s** | **6932** | **231.467 s** | **6944** | **+12** | **+12** |

12 of the 27 beats are one frame longer in vidgen (those whose `rest × 30` has a fractional part
≥ 0.5: s1_b1, s1_b2, s2_b1, s3_b3, s4_b5, s5_b3, s6_b2, s6_b3, s7_b1, s7_b3, s8_b2, s8_b3). The
prediction matches every scene exactly, so the animation timeline inside each beat is
frame-for-frame the original's.

## Frames

81 aligned frame pairs (3 per beat): **72 bit-identical** (PSNR ∞), the other 9 SSIM 1.0000 and
PSNR 75–98 dB. All 9 are "end" frames in a still hold, where x264 makes slightly different
decisions because the frame and GOP positions shifted. Side-by-side views of the end of every
scene show no visible difference.

One difference was found and fixed along the way. The first port colored "77%" in the title
with Manim's `t2c`. That makes Pango shape the line as separate color runs, which moves the
glyph outlines slightly and changes the stroke color that `Write` draws (title frames came out
at about 53 dB). The port now colors the glyph slice like the original (`color_glyphs` in
`s1_title.py`), and the title frames are identical too.

## Audio

The narration onset was located by cross-correlating each beat's MP3 with the soundtrack (8 kHz
mono) around where the frame timeline says the beat starts:

| beat | original: audio vs its frames | vidgen: audio vs its frames |
|---|---|---|
| s2_b1 | +44 ms | 0 ms |
| s4_b1 | +51 ms | 0 ms |
| s6_b1 | +61 ms | 0 ms |
| s8_b3 | +42 ms | −1 ms |

The original's narration starts 42–61 ms after the frame time. 21 ms of that is the video
stream's start offset; the rest is the per-segment AAC priming of its concat, which
vidgen's PCM concat avoids (DESIGN §5.2, Step 4). vidgen's narration is in sync to within 1 ms.

## Remaining differences

- +1 frame on 12 beats (+0.40 s in total): vidgen rounds each beat to the nearest frame, the
  original truncated. This is deliberate engine behaviour, not special-cased for this video.
- Audio sync is better than the original (see above); the audio is AAC 192 kbps 48 kHz in both.
- Subtitles (`kphi3_video.srt`) are new; the original had none.
