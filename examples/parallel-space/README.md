# Parallel Space — a flight through parallel realities

A 1280×720, 30 fps music film, 3:05 long: an original hybrid cinematic / trance score at
138.46 beats to the minute in F# minor, and eleven three.js scenes of a flight through space and
parallel realities. The score is written for vidgen's own synthesizer: a men's choir, strings,
a horn section, an organ, synth drums and supersaws. It opens slowly on one far light, grows an
ostinato layer by layer, lets the choir sing the hook in the breakdown, stops for a breath before
the trance drop, climbs to a second, higher climax and resolves on F# major in the coda. One bar
is exactly 52 frames, so every scene cuts on a bar line.

This folder is the film's source (version 7, the latest), made with
[schu-video-generator](https://github.com/joaopauloschuler/schu-video-generator) (`vidgen`).
Music and picture are generated from these files only: vidgen's own synthesizer plays the score
and Chromium draws the pictures, with no samples and no SoundFont. The code and the score were written by AI agents under the owner's direction.

## Form

| Bars | Time | Music section | Scene | Pictures |
|---|---|---|---|---|
| 0–8 | 0:00 | dawn | `01_dawn` | One small light in a large cold dark; the title; a far men's choir lights stars, a clock starts to tick |
| 8–24 | 0:14 | pulse | `02_pulse` | The ostinato lights a corridor of cells note by note; it opens onto great rings |
| 24–32 | 0:42 | groove | `03_groove1` | The mirror corridor: two huge glass planes, each showing another, later, tinted copy of the flight; solids split on the kick, the seams flash with the gated chords; the planes fold into one solid |
| 32–40 | 0:55 | groove | `04_groove2` | A portal shows another, warm universe; we fly into it |
| 40–56 | 1:09 | heart, heart2 | `05_heart` | The hook, sung, as a line of light around a great crystal; rings wake, the camera pulls far back |
| 56–64 | 1:37 | build | `06_build` | The corridor again, hot and accelerating towards a white star; a breath of dark before the hit |
| 64–72 | 1:51 | drop | `07_drop1` | The sun: the spectrum is its rays, the lead melody its orbit, the kick sends rings down the flight |
| 72–80 | 2:05 | drop | `08_drop2` | Around the sun; five portals look back into the cold universe |
| 80–88 | 2:19 | climax | `09_climax` | The sun inside the great rings, seen from farther and farther away |
| 88–96 | 2:33 | afterglow | `10_afterglow` | The same place cooling from gold to violet; the hook, an octave lower, drifts round it |
| 96–104 + 4.6 s | 2:46 | coda | `11_coda` | The one light again, now warm; the end card |

104 bars = 180.27 s, plus 4.6 s for the last chord to ring out.

### The mirror corridor

In `03_groove1` the camera flies between two huge parallel planes of glass. Every mirror shows
another copy of the flight, a little later in time (so the kick's flash ripples outwards through
them), turned a little and shifted in colour from ice and cyan to violet and rose: nine realities
receding sideways. Wireframe icosahedra, octahedra, dodecahedra, cubes, tetrahedra and tesseracts
float through all of them; on every kick each splits into copies that drift apart and fade; the
gated chords flash the mirrors' seams and send a light down the corridor. In the last two bars
every seam flies into one solid (an icosahedron with its dual and a tesseract inside) that recedes
to where the portal of `04_groove2` opens.

## The score

`assets/music/parallel_space.yaml` has 30 tracks. It began as a cinematic reworking of an earlier
uplifting-trance score, *Night Drive* (same tempo, key, hook and drop; the score's header names
it, but it is not part of this example and is not needed). What the main voices play:

| Track | Instrument |
|---|---|
| `trumpet` (the name the pictures read) | a men's choir far away in a long hall: `ooh` at dawn (A2–F#3), a hummed `mm` in the groove, `aah` in the coda |
| `hook` | a men's choir (F#3–A4): `ooh` in the breakdown, `aah` in heart2; in the drop and the climax it doubles the supersaw lead an octave or two under |
| `voice` | the choir's basses an octave under the hook: the low body |
| `lead` | the supersaw lead of the drop and the climax |
| `violins`, `swell`, `spicc`, `vla` | violas and cellos: on the hook, swelling single notes, spiccato sixteenths, short strokes |
| `horn`, `organ`, `brass` | a horn section, an organ on a soft flute stop, low sustained swells |
| `kick`, `taiko`, `tom`, `boom`, `clap`, `snare`, `crash`, `tick`, `roll`, `frame` | the drums |

The tempo is 138.4615 rather than 138.4615385: the longer figure would round each bar down to
51.99 frames; this one gives exactly 52. The mix is normalised to −14 LUFS.

## What's in this folder

| File | What it is |
|---|---|
| [video.yaml](video.yaml) | the project: format, music, and the eleven scenes (`web_cut`, one script; `data.mode` picks the scene; `music_data` names the score's tracks the page reads) |
| [assets/music/parallel_space.yaml](assets/music/parallel_space.yaml) | the score: 30 tracks, 104 bars, played by vidgen's synthesizer |
| [extensions/ps.js](extensions/ps.js) | every scene, the opening title and the end card (one three.js module, built from vidgen's `vidgen/three-kit` and `vidgen/music-time`) |
| [extensions/webcut.py](extensions/webcut.py) | `web_cut`: a `web` scene with no 0.5 s fade-out, so the cuts land on the bar |
| [.gitignore](.gitignore) | keeps `build/`, `output/` and rendered audio and video out of version control |

## Render

From this folder, with `vidgen` on your `PATH` and Chromium installed once
(`python -m playwright install chromium`; Windows: `py -m playwright install chromium`):

```bash
vidgen validate .
vidgen render .
```

That writes `output/parallel_space_v7.mp4`. The pictures use bloom and a baked nebula sky and
are drawn by the browser's software renderer where there is no GPU: about 0.5 to 0.75 s a frame
was measured on a 2-core machine, so the film's 5,546 frames take **about 1 hour**. The first
render also synthesizes the score (about 9 minutes on 2 cores); it is cached in `build/music`
afterwards. On a machine with more cores, `vidgen render --jobs auto .` draws scenes in parallel.

Quick looks before that:

```bash
vidgen still . --scene 03_groove1 --at 2 --at 7 --at 12    # single frames at full size
vidgen render --draft .                                    # the whole film, small and fast
vidgen render --draft --scene 07_drop1 .                   # one scene
```

`vidgen still` needs the synthesized score too: the first one waits for it.

**Disk.** `video.yaml` sets `render: {intermediate: compact, keep_intermediates: false}`: each
scene's frames clip is kept about 4.6 times smaller than lossless and deleted once the scene is
rendered, so the build stays small (under about 200 MB). Both are safe on any machine: the
compact clip adds one near-invisible encoding step (0.04–0.24 dB in the scene clip), and a scene
rendered again for any reason (an edited title or timing, `--force`) draws all its frames again. Remove the line to
keep lossless frames (about 27 MB a second at 720p, about 5 GB for the film). Where a command may
run only a few minutes, render in steps with `vidgen render --max-scenes 1 .` and run it again
until it joins: finished scenes are kept. Put such settings in `video.yaml`, not on the command
line: a scene rendered with different command-line settings counts as stale on the next run.

A smaller delivery copy under 25 MB: re-encode the video in two passes and copy the audio (on
Windows use `NUL` instead of `/dev/null`):

```bash
ffmpeg -y -i output/parallel_space_v7.mp4 -c:v libx264 -preset slow -b:v 840k -pass 1 -pix_fmt yuv420p -profile:v high -an -f null /dev/null
ffmpeg -i output/parallel_space_v7.mp4 -c:v libx264 -preset slow -b:v 840k -pass 2 -pix_fmt yuv420p -profile:v high -movflags +faststart -c:a copy output/parallel_space_v7_delivery.mp4
```

## How the pictures hear the music

The pictures never hear the track. Every scene has `music_data` in its params, so vidgen gives
the page `ctx.music`: the music the video plays measured at every frame (16 spectrum bands and the
level) and the score's own events in song time. `ps.js` copies the drums (kick, taikos, toms,
booms, claps, snare, crash, ticks, the roll, the frame drum) and the notes of the hook, the lead,
the choir's call (track `trumpet`) with the violas on the hook (track `violins`), the string
swells and the horn into arrays with `trackArrays` of `vidgen/music-time`. `ctx.music.t0` is each
scene's place in the song, worked out by vidgen from the scene durations.

After a change to the score nothing else needs rebuilding: the next render (or `vidgen still`)
measures the music again. If you change the form of the score (the number of bars in a section),
change the scene durations in `video.yaml` and the bar numbers in `ps.js` to match.

The published film read the music from a data file made by a script of its own. The example
reads the same hits and notes from `ctx.music` (every time, gain and length equal); the spectrum
and level are measured from the video's mix with 256 steps instead of the file's 64. That changes
the length of a spectrum ray or the glow of a crystal a little: in stills of every scene at three
moments, 6 of 36 are identical and the rest differ by 53.5 to 85 dB PSNR, most pixels by one or two
levels and the tips of the sun's rays by more (up to 89 levels on a few pixels).

## Notes on the pictures

- Everything is a function of the song time (`ctx.music.t0` plus the scene's clock): no state is carried
  between frames or scenes and all randomness is seeded, so renders repeat exactly and scenes can
  be rendered in any order or in parallel.
- The kick pulses the brightness of objects, never the zoom, the sky or the exposure. Rotations
  are smooth. Lines are cut at the near plane and wrapped objects fade in far away, so nothing
  sweeps through the camera as large stripes.
- Finishing is done in the page: three.js `EffectComposer` with `UnrealBloomPass`, then one pass
  for the ACES tone curve, a colour grade per section, a slight chromatic fringe, vignette and
  grain.
- The building blocks — glowing strokes, glass crystals, the tesseract, the nebula sky, portals,
  star fields, flares, shock rings, the hook's ribbon, the spectrum's rays, the corridor and the
  great rings — come from vidgen's module `vidgen/three-kit` (they were written for this film and
  moved there in Step 358); `ps.js` composes them into the scenes.
