# Escapement — a clockwork film

A 1280×720, 30 fps music film, 3:11 long: an original score in D minor at 120 beats to the
minute, and three.js pictures of a watch movement in brass, rhodium, blued steel and ruby. The
tick is the tempo: one beat is exactly 15 frames and one bar exactly 60, the escapement ticks on
every beat, and every wheel turns at the speed its real tooth count gives it. In the climax the
movement flies apart into an exploded view, every part still ticking, and closes again; before
it, in bar 67, everything stops for one silent bar.

This folder is the film's source, as published, made with
[schu-video-generator](https://github.com/joaopauloschuler/schu-video-generator) (`vidgen`).
Music and picture are generated from these files only: vidgen's own synthesizer plays the score
and Chromium draws the pictures; there are no samples, no SoundFont, no images, no audio or video
files here. The code and the score were written by AI agents under the owner's direction.

## Form

| Bars | Time | Music | Scene | Pictures |
|---|---|---|---|---|
| 0–8 | 0:00 | winding: ratchet clicks, a low swell; the tick starts at bar 4; one bell | `01_winding` | The watch in the dark, the crown wound click by click, the title; the seconds hand starts |
| 8–16 | 0:16 | the theme on a music box over tick, tock and a slow bass | `02_dial` | Macro over the dial; a gold pearl glints for each note; the camera pushes in at the small seconds |
| 16–24 | 0:32 | a low ostinato, then the plucked cells | `03_through` | Under the dial: the movement assembles, a part for each entry of the music |
| 24–32 | 0:48 | the theme on a horn; the first great drum | `04_escapement` | Macro of the escape wheel, the pallets, the balance and its breathing hairspring |
| 32–40 | 1:04 | the theme in brass, drums, bells | `05_cathedral` | The same movement from inside, at the height of a grain of dust: wheels as vaults, arbors as columns |
| 40–48 | 1:20 | second phrase; three against four | `06_threefour` | A 36-tooth wheel drives a 48-tooth one: three pins against four, two hammers on a gong |
| 48–56 | 1:36 | no tick: pads, glass, the theme far away | `07_orrery` | An orrery: the sun and six planets on their arms over a night-blue disc |
| 56–60 | 1:52 | the tick comes back, late and later | `08_falter` | The planets slow with each late tick and the sun dims |
| 60–68 | 2:00 | a build on the dominant; bar 67 is silent | `09_build` | Back at the movement, cold, rising and brightening; for one bar everything stops |
| 68–76 | 2:16 | the theme an octave higher, everything playing | `10_climax1` | The movement flies apart on the hit (an exploded view); every part keeps ticking |
| 76–84 | 2:32 | C and D major in place of the minor cadence | `11_climax2` | Round the exploded movement; it closes again in the last bar |
| 84–94 + 3 s | 2:48 | D major: music box, four strokes of the bell, then the clock alone | `12_coda` | The watch whole again, further and further away; the end card |

94 bars = 188 s, plus 3 s for the last chord to ring out.

## The calibre

The watch is imaginary but its going train is real. Tooth counts, in mesh, with neighbours
turning opposite ways:

| Pair | Teeth | Turns once in |
|---|---|---|
| barrel → centre pinion | 72 : 9 | barrel: 8 hours |
| centre wheel → third pinion | 64 : 8 | centre wheel (minute hand): 1 hour |
| third wheel → fourth pinion | 60 : 8 | third wheel: 7.5 minutes |
| fourth wheel → escape pinion | 48 : 12 | fourth wheel (seconds hand): 1 minute |
| escape wheel | 15 teeth, half a tooth a beat | 15 seconds |
| ratchet wheel → crown wheel | 36 : 24 | one tooth for each winding click in the score |
| three-against-four wheels | 36 : 48 | 12 teeth pass each bar: 9 pins strike three times a bar, 16 pins four times |

The balance swings once a second (7,200 beats an hour), so the lever is thrown across on every
beat of the music and the seconds hand steps twice a second, with a small overshoot. At these
true speeds the centre wheel and the barrel do not visibly move within three minutes, as in a
real watch. The orrery's planets keep the ratios of old orrery gearing (Mercury 20:83, Venus
8:13, Mars 79:42, Jupiter 83:7, Saturn 59:2 of an Earth year of eight bars); its wheels are drawn
but not meshed.

Where the music's tick falters (bars 56–60) and where it stops for a bar (bar 67), the mechanism
does the same: its beats are read from the score.

## What's in this folder

| File | What it is |
|---|---|
| [video.yaml](video.yaml) | the project: format, music, and the twelve scenes (`web_cut`, one script, `data.mode` picks the shot) |
| [assets/music/escapement.yaml](assets/music/escapement.yaml) | the score: 26 tracks, 94 bars, played by vidgen's synthesizer |
| [extensions/escapement.js](extensions/escapement.js) | the watch, the orrery, every shot, the title and the end card (one three.js module) |
| [extensions/webcut.py](extensions/webcut.py) | `web_cut`: a `web` scene with no 0.5 s fade-out, so the cuts land on the bar |
| [.gitignore](.gitignore) | keeps `build/`, `output/` and rendered audio and video out of version control |

## Render

From this folder, with `vidgen` on your `PATH` and Chromium installed once
(`python -m playwright install chromium`; Windows: `py -m playwright install chromium`):

```bash
vidgen validate .
vidgen render .
```

That writes `output/escapement.mp4`. The pictures are physically based metal with a baked studio
environment, shadows, depth of field and bloom, drawn by the browser's software renderer where
there is no GPU. Measured on a 2-core machine without a GPU (vidgen after Step 349, 4 s of
`05_cathedral` and 4 s of `10_climax1` rendered at final quality): 0.89 to 1.23 s a frame plus
about 20 s a scene, so the film's 5,730 frames take **about 1 h 30 min to 2 h**. The first
render also synthesizes the score (about 5 minutes); it is cached in `build/music` afterwards.

Quick looks before that:

```bash
vidgen still . --scene 04_escapement --at 2 --at 7.27 --at 13    # single frames at full size, ~20 s
vidgen render --draft .                                          # the whole film, small and fast
vidgen render --draft --scene 04_escapement .                    # one scene
```

`vidgen still` needs the synthesized score too: the first one waits about 5 minutes for it.

**Disk.** A `web` scene keeps its lossless frames: about 27 MB a second at 720p, about 5 GB for
the whole film. `render: {intermediate: compact}` in `video.yaml` (or
`vidgen render --intermediate compact .`) keeps them about 4.6 times smaller, and
`--clean-intermediates` deletes each scene's frames once it is rendered.

A smaller delivery copy under 25 MB: re-encode the video in two passes and copy the audio (on
Windows use `NUL` instead of `/dev/null`):

```bash
ffmpeg -y -i output/escapement.mp4 -c:v libx264 -preset slow -b:v 800k -pass 1 -pix_fmt yuv420p -profile:v high -an -f null /dev/null
ffmpeg -i output/escapement.mp4 -c:v libx264 -preset slow -b:v 800k -pass 2 -pix_fmt yuv420p -profile:v high -movflags +faststart -c:a copy output/escapement_delivery.mp4
```

## How the pictures hear the music

The pictures never hear the track. Every scene has `music_data` in `video.yaml`, so vidgen reads
the score and hands the page `ctx.music`: the times of the ticks, drums, winding clicks, bells and
every note of the theme's voices, and the scene's place in the song (`ctx.music.t0`, worked out
from the scene durations). `escapement.js` (`fromMusic`) turns them into the arrays it draws
from (`trackArrays` of vidgen's `vidgen/music-time`, which also gives the drums' envelopes), and builds the mechanism's beats: one every quarter note from bar 4, the score's own tick
and tock in the faltering bars 56–60, nothing inside the silent bar 67 (`START_BAR`, `FALTER`,
`SILENT_BAR` at the top of the music block). Edit the score and the pictures follow at the next
render; nothing else needs to be run.

The film was first made with a hand-written exporter (a Python script writing a JSON file of the
same events, rerun after each score change). This example replaces it with `music_data` and
draws the same pictures: stills of all twelve scenes, at four times each, are pixel-identical to
the film's. The exporter wrote times on the score's grid of sixteenths rounded to three
decimals; the page keeps that rounding (`grid`), without which the triplet hammer strokes of
`06_threefour` and `09_build` move 42 microseconds and a few pixels differ.

If you change the form of the score (the number of bars in a section), update the scene
durations in `video.yaml` and the bar numbers in `escapement.js`.

## Notes on the pictures

- Everything is a function of the song time (`ctx.music.t0` plus the scene's clock): no state is
  carried between frames or scenes and nothing is random, so renders repeat and scenes can be
  rendered in any order or in parallel.
- Hits pulse the light (the studio's brightness, the turn of its soft boxes, small glints on
  jewels and hammers), never the camera. Rotations are smooth except where the mechanism itself
  steps: the escape wheel, the train behind it, the seconds hand, the ratchet, the hammers.
- The metal is three.js `MeshStandardMaterial` under a studio of soft boxes baked once per scene
  into an environment map. Geneva stripes, perlage and circular graining are normal maps
  computed from height functions at load time. One shadowed key light also dims what a surface
  reflects, so wheels cast shadows on the plate although metal has no diffuse light.
- Finishing is the film's own, done in the page: a gathered depth of field at half size, bloom on
  highlights only, a filmic tone curve, a colour grade per shot, vignette, FXAA and fine grain.
  All shots but the first and the last are drawn at 88 % size and enlarged. The arms and screws
  of the balance, which move up to 54 degrees a frame, are drawn six times across the open
  shutter (motion blur for those parts only).
- vidgen now ships most of this finishing as a module, `vidgen/three-finish` (see
  [examples/three-finish](../three-finish/README.md)). A port of three of these scenes to it
  looked close but not the same (28–34 dB PSNR: the vignette's shape, the fringe, the grade's
  lift), so the example keeps the film's own code and renders the published film.
- The small shared pieces — easing, seeded numbers, the camera's keyframes, the score's events as
  arrays and their envelopes, the drifting dust — come from vidgen's modules `vidgen/music-time`
  and `vidgen/three-kit`; stills of every scene at three moments are pixel-identical to the
  film's own code. The watch, the studio and the finishing stay in `escapement.js`: moving them
  to the shared modules would change the picture.
- The music's theme climbs by fourths (A–D–F–E, D–F–A–G, G–B♭–D–C, A–G–E–C♯); the plucked
  ostinato of the gear train is the same cells four times as fast.

## How it was planned

The grid came first: 120 BPM at 30 fps makes one beat 15 frames and one bar 60 frames, so the
escapement can tick on every beat (tick on 1 and 3, tock on 2 and 4) and nothing drifts. Each
section of the music got one shot and one layer of the mechanism, from the crown and ratchet
(winding) through the dial, the train, the lever escapement, the going train at the scale of a
building, the three-against-four work and the orrery ("an orrery is a clock") to the whole
movement apart and together again.

Colour script: night blue (winding) → ivory and gold (dial) → bright workshop (assembly) → warm
gold macro → amber in haze, tense (cathedral) → deep blue and gold (orrery) → cold steel, then
white heat (build) → blazing gold with blue shadows (climax) → soft warm dusk (coda).

Order of work: the score, measured after each change (loudness per section, peaks, bands,
stereo, a spectrogram); the music data for the pictures; the engine and one hero shot (the
escapement macro) until the metal looked precious; scene by scene with stills, strips of
consecutive frames and fixes; a draft of the whole film, a contact sheet, the three weakest
moments fixed, the final render.
