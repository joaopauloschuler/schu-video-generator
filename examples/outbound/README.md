# Outbound — from first light to the edge of light

A 1280×720, 30 fps music film, 58 seconds long: a sunrise over an Earth-like world, a ship that
burns out of orbit, a fly-by of a ringed giant, a jump, and a black hole. The pictures are five
`space` scenes written in [video.yaml](video.yaml) alone, with no JavaScript: a sky, a sun,
worlds, a ship, a warp, a black hole and the camera's moves are named there, and
[schu-video-generator](https://github.com/joaopauloschuler/schu-video-generator) (`vidgen`)
draws them from its ready-made space parts. The score is an original orchestral cue in D minor
for vidgen's own synthesizer: low strings, four horns, low brass, a men's choir, timpani and
taikos. One bar is exactly 96 frames, so every scene cuts on a bar line and the key moments fall
on the beat. The film and its score were written by an AI agent under the owner's direction.

## Form

75 beats to the minute: one beat is 0.8 s (24 frames), one bar 3.2 s (96 frames). Bars are
counted from 1, as in `video.yaml`.

| Bars | Time | Music | Scene | Pictures | Camera move |
|---|---|---|---|---|---|
| 1–3 | 0:00 | dawn: a far tam-tam, low strings, men humming; a roll grows in bar 3 | `01_dawn` | The night side of an Earth-like world from 446 km, the Milky Way above its thin line of air; the title in the left third | `reveal`: a ride round the world toward the sunrise |
| 4–5 | 0:10 | light: the arrival in B flat major, the horns start the theme | `01_dawn` | The sun's first light comes over the limb exactly on bar 4 and climbs; the taikos pulse its glare | the same move goes on |
| 6–8 | 0:16 | depart: a spiccato pulse in the cellos; taikos and low brass on bar 7 | `02_depart` | A ship in orbit 2,000 km up, just past the dawn line; on bar 7 it burns 7.28 km/s and leaves on an escape hyperbola; the world falls away behind it | `follow`: from above and ahead of the ship, looking back at the world |
| 9 | 0:26 | rings: the theme again, wider, with violins and men's voices | `03_rings` | A ringed giant from afar; its rings close to a line and open again | `arc`: round the world from half lit to three-quarters lit |
| 10–11 | 0:29 | rings | `03_rings` | The ship passes 110,000 km over the cloud tops, in front of the rings | a cut, then `follow` from the side away from the world |
| 12 | 0:35 | jump: one bar on A major, rolls and a swell | `04_jump` | Engines on; the stars stretch into streaks, growing with the timpani roll | `follow`: the chase view |
| 13–16 | 0:38 | horizon: the climax in D minor, everything, men's voices on "aah" | `05_horizon` | A black hole with its disc, light bent round it; closest on bar 15; the disc pulses with the taikos | `fly-by`: past the hole on its left |
| 17–18 | 0:51 | end: D major, a tam-tam, dying away | `05_horizon` | The hole recedes into the left third; the end card in the right third | the fly-by's way out |

18 bars = 57.6 s.

## What is true in it, and what was chosen

- **The burn** (`02_depart`). The ship's orbit, the burn and the path after it come from
  vidgen's orbit mathematics, 150 times faster than life. 7.28 km/s is the departure burn of a
  Hohmann transfer from the Earth's orbit to Saturn's, made from a circular orbit 2,000 km up:
  the transfer needs 10.29 km/s more than the Earth's own speed, and deep in the Earth's gravity
  that costs 7.28 km/s. The Sun stands where it really is on 21 March 2027. Where on its orbit
  the ship burns was chosen for the light and the music (bar 7), not for the direction to Saturn.
- **The fly-by** (`03_rings`). A real hyperbola past Saturn at the speed that transfer arrives
  with (5.44 km/s far from the planet), 110,000 km over the cloud tops, about 3,000 times faster
  than life. The planet's size, flattening, tilt and turning are Saturn's. The sun's direction in
  this scene was set by hand so that the pass is over the day side.
- **The sunrise** (`01_dawn`). The camera's ride is worked out so that the sun's upper edge meets
  the limb at bar 4; `air: 0.1` allows a tenth of a degree for the air that holds the first
  light back.
- **The jump and the black hole** are the film's invention. The hole itself is drawn from the
  light paths round a non-rotating black hole: the shadow has its true size and the far side of
  the disc is seen over and under it.
- The ship is an invented design from vidgen's spacecraft kit (`kind: ship`, `seed: 1`).

## The score

[assets/music/outbound.yaml](assets/music/outbound.yaml) has 17 tracks. The theme is four horns
in unison: D up a fifth to A, then down by step. It is heard three times: at the sunrise, under
the pulse of the departure, and with violins and men's voices at the rings; the climax turns it
upward over D minor, and the last chord is D major.

| Track | Instrument |
|---|---|
| `basses`, `cellos`, `violas`, `violins` | the strings: held low notes and a tremolo at dawn, a spiccato pulse in the cellos from the departure on, the theme in the violins at the rings and the climax |
| `horns` | four horns: the theme |
| `hit`, `swell` | low brass: chords on root and fifth, and the swells into bar 4 and bar 13 |
| `choir` | a men's choir: a hum at dawn, "ooh", "oh", then "aah" at the climax |
| `timpani`, `roll`, `taiko`, `bass_drum`, `pulse`, `snares`, `rise`, `crash`, `gong` | timpani and their rolls, six taikos, a bass drum, a soft frame drum, a snare roll, a cymbal swell and crash, a tam-tam |

Nothing plays above D5. Measured: the dawn is 15 dB quieter than the climax, and the film's mix is
normalised to −14 LUFS with its true peak under −1.5 dBTP.

## Render

From this folder, with `vidgen` on your `PATH` and Chromium installed once
(`python -m playwright install chromium`; Windows: `py -m playwright install chromium`):

```bash
vidgen validate .
vidgen render .
```

That writes `output/outbound.mp4`. The pictures are drawn by the browser's software renderer
where there is no GPU. **Estimate, not a measured render:** on a 2-core machine without a GPU
single frames at 1280×720 took 1.0 to 1.7 s each (dawn 1.0, departure 1.3, rings 1.0, jump 1.0,
black hole 1.4 on average), so the film's 1,728 frames should take **about 35 to 45 minutes**,
plus about 2 minutes to synthesize the score the first time (it is cached in `build/music`
afterwards). On a machine with more cores, `vidgen render --jobs auto .` draws scenes in
parallel.

Quick looks before that:

```bash
vidgen still . --scene 05_horizon --at 6.4          # one frame at full size (about 20 s)
vidgen render --draft .                             # the whole film, small and fast: about 3 minutes
vidgen render --draft --scene 02_depart .           # one scene
```

`vidgen still` needs the synthesized score too: the first one waits for it.

## Which parts of the generator each scene shows

| Scene | Parts |
|---|---|
| `01_dawn` | the algorithmic sky from a seed (`sky`), an Earth-like world with its air (`bodies`), the sun with its glare and spikes (the default `sun`), the camera's `reveal` timed in bars, a pulse on the taikos (`music`), the opening title (`title`) |
| `02_depart` | orbit data (`orbits`: an orbit, a burn, a date), a craft that flies it and shows the burn as thrust (`craft`), the `follow` view with a direction of its own, planet-shine on the ship |
| `03_rings` | a ready-made ringed world, a fly-by from the orbit data (`flyby`), two camera moves with a cut between them (`arc`, `follow`) |
| `04_jump` | a craft standing free with `throttle`, the `warp`, a level that follows a track (`glow`) |
| `05_horizon` | the `black-hole`, the `fly-by` move, a pulse on its disc, the end card (`end_card`) |

All five scenes share one sky (`seed: 7`) and one ship (`seed: 1`), and take the film's
finishing (a soft bloom, grain, a vignette) from the `space` scene's defaults.

## Change it

- **Another sky**: `sky: &sky {seed: 7, look: rich}` in the first scene is used by all five;
  change the seed, or `look` to `natural` or `sparse`.
- **Another world**: in `01_dawn` write `bodies: [{name: Earth, world: azure}]` (or `verdant`,
  `mars`, a `type: ocean` with a `seed` of its own); `vidgen parts --kind body` shows them all.
  In `03_rings`, `bodies: [{name: Saturn, world: tempest}]` is another giant in Saturn's place.
- **Another ship**: change `kind` (`probe`, `tug`, `station`...) or `seed` in the three scenes
  that show it.
- **Another climax**: in `05_horizon` change the hole's `tilt`, or come closer with
  `closest: {radii: 14}` (each frame then takes longer).
- **Another score**: after a change to the notes nothing else needs rebuilding. If you change
  the number of bars in a section, change the scene durations (3.2 s a bar) and the bar numbers
  in `video.yaml` to match.

Look at one frame after each change before rendering: `vidgen still . --scene 03_rings --at 6`.
`vidgen space-page . --scene 05_horizon` writes a scene's page out as JavaScript to go on in code.

## What's in this folder

| File | What it is |
|---|---|
| [video.yaml](video.yaml) | the project: format, music and the five `space` scenes |
| [assets/music/outbound.yaml](assets/music/outbound.yaml) | the score: 17 tracks, 18 bars, played by vidgen's synthesizer |
| [.gitignore](.gitignore) | keeps `build/`, `output/` and rendered audio and video out of version control |
