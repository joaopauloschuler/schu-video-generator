# Orchestral shorts — seven portrait music videos

Seven YouTube Shorts, 1080×1920 at 30 fps, 33 to 37 seconds each. Each has an original score
for vidgen's own orchestra (bowed strings, horns, trumpet and low brass, organ, timpani, taiko
and orchestral percussion, and a choir that sings syllables) and three.js pictures of abstract
space: crystals, a turning hypercube, portals, tunnels of light, great rings, swarms. The
pictures follow the score: the shots cut on its bar lines, and chosen objects light up on the
drums and glow with the choir, read from the score's notes.

This folder is the films' source, as published, made with
[schu-video-generator](../../README.md) (`vidgen`).
The code and the scores were written by AI agents under the owner's direction.

| Film | Length | Key and tempo | Music | On YouTube |
|---|---|---|---|---|
| [First Light](first-light/) | 0:36 | D major, 96 BPM | a dawn: tremolo violins and a choir opening from a hum, horns, then the trumpet's theme over everything | [Short](https://www.youtube.com/shorts/y1zxGYL9OOE) |
| [The Signal](the-signal/) | 0:35.5 | E minor, 120 BPM | a muted horn sends a three-note signal over a spiccato engine and taikos; the whole orchestra answers | [Short](https://www.youtube.com/shorts/VIaxZaXD56Y) |
| [Gate of Stars](gate-of-stars/) | 0:33.5 | Eb major, 80 BPM | a cathedral organ, a horn chorale and sopranos; the gate opens on the trumpets over full organ | [Short](https://www.youtube.com/shorts/nSDKRQBD6V4) |
| [Choir of the Void](choir-of-the-void/) | 0:33.6 | B minor, 72 BPM | whispered chords, a soprano soloist on "la" and "ah-oh", the full choir on "aah"; ends in B major | [Short](https://www.youtube.com/shorts/8EZThIyJKOQ) |
| [Ascension](ascension/) | 0:37 | A major (rising to B major), 100 BPM | plucked strings like a clock, a heroic horn theme, a step up a tone for the summit | [Short](https://www.youtube.com/shorts/cEob9Rqooqo) |
| [Eclipse](eclipse/) | 0:35.5 | F minor (turning to F major), 90 BPM | low brass and a reed organ pedal, a glassy tremolo at totality, sunrise in F major | [Short](https://www.youtube.com/shorts/gLsKCVGfdz4) |
| [Orchestra](orchestra/) | 0:35 | D minor (ending in D major), 90 BPM | the orchestra section by section: strings, drums, brass, choir, then everything | [Short](https://www.youtube.com/shorts/rHDSSkKPzPw) |

**Orchestra** labels each section of the orchestra on screen while it plays (first "Strings",
"violins + violas: tremolo", "cellos + basses: swell"; then "Taiko + Timpani", "Brass", "Choir"
and "Tutti"), so it doubles as a listening test: each family of instruments is heard on its own
before they all play.

## Render one

Each film is a complete project in its own folder. With `vidgen` on your `PATH` and Chromium
installed once (`python -m playwright install chromium`; Windows: `py -m playwright install
chromium`):

```bash
cd first-light
vidgen validate .
vidgen render .
```

That writes `output/first_light.mp4` (`output/the_signal.mp4` and so on for the others). The
pictures are drawn by the browser's software renderer where there is no GPU. **Estimate, not a
measured render:** single frames at 1080×1920 took about 1.1 s each on a 2-core machine without a
GPU, so a film's 1,000 to 1,100 frames take about 20 minutes, plus about 1.5 minutes to
synthesize the score the first time (it is cached in `build/music` afterwards). On a machine
with more cores, `vidgen render --jobs auto .` draws scenes in parallel.

Quick looks first:

```bash
vidgen still . --scene 01_drift --at 2 --size 360x640    # one frame, small
vidgen still . --count 12 --size 180x320 --sheet sheet.png --scene 12_ribbon   # a contact sheet of one shot
vidgen render --draft .                                  # the whole film, small and fast
vidgen motion check .                                    # after a render: flashes, black frames, flicker
```

`vidgen still` needs the synthesized score too: the first one waits for it.

## The shared scene module

All seven films draw with one three.js module, [shared/orch.js](shared/orch.js), built on
vidgen's `vidgen/three-kit`, `vidgen/music-time`, `vidgen/three-finish` and `vidgen/title-cards`.
Each shot picks a mode in its `data:`:

| Mode | What it shows |
|---|---|
| `drift` | a slow flight through a nebula and stars towards a far light; notes leave glints in the distance |
| `crystal` | one great glass crystal (`kind`: octa, dodeca, ico...) turning slowly in a shell of stars; the drums light it |
| `portal` | a ring of light with a window onto another sky, a tesseract floating inside; the dial runs on the eighths |
| `tesseract` | a hypercube turning in four dimensions, glints around it |
| `swarm` | crystals on slow orbits around a light; big hits send slow rings out |
| `rings` | great rings with scale marks and the spectrum as rays around a light: the climax |
| `tunnel` | a tunnel of polygons flying past, one on every beat, towards a light |
| `ribbon` | the melody (`melody: trumpet`) drawn as a ribbon of light while the camera draws back |

Other keys of a shot: `colours` (`base`, `accent`, `deep`), `react` (which tracks pulse, glint,
glow or ring), `grade`, `seed`, `lookY`, `speed`, `size`, `title` (the opening title), `end`
(the end card), `label` (Orchestra's section labels). Hits light chosen objects only, never the
sky or the whole frame; every turn and camera move is slow and smooth; nothing comes close to the
camera.

The films cut straight from shot to shot on the bar line with the `web_cut` scene type,
[shared/web_cut.py](shared/web_cut.py): the `web` scene without its half-second fade-out. Each
film's `video.yaml` reaches both with two lines, `extensions: [../shared]` (the scene type) and
`web_root: ..` (its pages are served from this folder, so `script: ../shared/orch.js` works).

## Make another one

1. Copy a film's folder, put your score in `assets/music/` and name it in `shots.yaml`.
2. Write the shot list in `shots.yaml`: for each shot its length in bars, its mode and anything
   it changes.
3. From this folder, `python tools/gen.py my-film` writes `my-film/video.yaml`: the cuts on the
   score's bar lines, and the colours, grade and reactions of the section each shot starts in,
   from `vidgen music plan` (a shot's own values win).

Check the score without listening: `vidgen music check assets/music/my_score.yaml` reports each
track's share of the sound, of the voice range, of the bass and of the highs, notes outside an
instrument's range, and harsh highs or a lift that does not lift. `vidgen music render` plays it
to a WAV.

## What's in this folder

| File | What it is |
|---|---|
| `<film>/video.yaml` | the film: format, music, and one `web_cut` scene per shot |
| `<film>/shots.yaml` | the shot list `video.yaml` is written from |
| `<film>/assets/music/*.yaml` | the score, played by vidgen's synthesizer |
| [shared/orch.js](shared/orch.js) | the three.js scene module of every shot |
| [shared/web_cut.py](shared/web_cut.py) | the `web_cut` scene type: straight cuts on the bar |
| [tools/gen.py](tools/gen.py) | writes a film's `video.yaml` from its `shots.yaml` |
| [.gitignore](.gitignore) | keeps `build/`, `output/` and rendered audio and video out of version control |
