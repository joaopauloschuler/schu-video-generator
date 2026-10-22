# Music craft: writing score files that sit under a voice

Craft notes for music written as **score files** (YAML: key, tempo, sections, chords, tracks of
step patterns; `docs/CONFIG.md`, "Score files"). The author guide's "Making music" recipe says
*how* to work (start from a template, change one thing at a time, check, compare, let a human
choose); this page says *what* tends to work, with the numbers `vidgen music check` reports.
Everything here was measured, not heard: an agent cannot listen, and neither could the agent that
wrote this page. A person listens and chooses.

Worked example: [examples/gps-time-of-flight](../examples/gps-time-of-flight/README.md), a piece
turned from the `momentum` template into something new in nine checked steps, playing under a
narrated GPS explainer. Hear it, and the 16 built-in beds, on the
[Listen page](music/README.md). Two of the beds, `tidewater` and `skyline`, are score files
themselves: `vidgen music template tidewater` shows a finished piece written in the format.

Contents: [room for the voice](#1-room-for-the-voice) ·
[energy curves](#2-energy-curves-builds-and-lifts) · [loops](#3-loop-design) ·
[check and compare](#4-using-check-and-compare) · [genre sketches](#5-genre-recipes-as-score-sketches) ·
[common mistakes](#6-common-mistakes-and-their-fixes)

## 1. Room for the voice

The voice lives between **300 Hz and 3 kHz**; vidgen plays music at −28 LUFS and ducks it 12 dB
while someone speaks, and still a busy part in that band blurs the words. The check measures
the share of the music in that band (the beds: 7–63 %, limit 72 %), the loudest bar there (limit
−26 dB) and, in its demo under a narration sample, how far the voice stands over the music
(the beds: 17.6–26.2 dB; under 15 is a problem).

- **Pads**: they hold most of the power. Keep them dark under narration — `lowpass: 1200` to
  `2600`, or `settings: {tone: 1500}` — and open them where nobody speaks or in the lift.
- **Figures and arpeggios**: in octave 3 they sit under the voice's core; an octave up (octave 5,
  a bell, `glass`) they sit above it. Octave 4 is right in it: keep such parts quiet or sparse.
- **Melodies**: long notes, one or two a bar, mostly in the lift. A melody that moves every
  eighth note competes with the words even when it is quiet.
- **Highs**: hats and ticks above 5 kHz are fine when they are small (the beds: −94 … −35 dB
  under the whole; limit −30). A hat at its default level is plenty.
- **Bass**: up to about 80 % of the power under 150 Hz is normal for these beds (limit 85 %);
  it does not mask the voice, but a boomy kick plus a sub plus a pad `sub` can.

## 2. Energy curves: builds and lifts

A piece that stays the same for a minute is a drone; one that changes too much fights the
story. The shape that works under explainers: **quiet intro → build → lift → settle**, then
the loop starts again. Name the sections that way: the check judges sections named `build`
(its second half against its first: 0.5 dB louder or 1 dB brighter) and `lift` (against the
section before: 0.5 dB louder or 1.5 dB brighter). Other names are not judged.

Ways to build, strongest first in our measurements:
- **Open a filter**: `lowpass: [[0, 800], [8, 3200]]` on the pad or arpeggio over the build
  (the sweep is measured as brightness; in `time_of_flight` it gave +3.3 dB).
- **Ramp a volume**: `volume: {from: -3, to: 0}` on the main part.
- **Bring parts in**: `rest: [intro]` on the kick and bass, `only: [build, lift]` on the hats,
  `only: [lift]` on the clap and lead.
- **A riser** in the last two bars (`steps: ". | . | . | . | . | . | x | -"`): it is heard but
  measures almost nothing; do not rely on it alone.

A lift is a few dB louder **and** clearly brighter: the pad's filter open (`lowpass: none`), a
part that only plays there, a wider stereo image (`width: 1.4`). `time_of_flight`'s lift is
+2.4 dB and +10 dB brighter; `ascent` (a built-in bed) lifts only +0.3 dB but +1.9 dB brighter
— brightness does most of the work.

Keep the whole within the steadiness limit (the 3 s loudness between its 10th and 95th
percentile within 8 dB; the beds 0.5–1.8, `time_of_flight` 5.1): a very quiet intro under a
loud lift makes the ducking pump.

## 3. Loop design

A bed loops under a video longer than itself, so its end must run into its start.

- **Curves end where they start**: the settle's `lowpass: {from: 2600, to: 1200}` and
  `volume: {from: 0, to: -3}` land on the intro's values. The seam number (the step across the
  loop over the music's own biggest steps; under 1 is clean) stays low.
- **Harmony leads home**: end on a chord that wants to go to the first one (`Vsus4` or `V`
  before `i`, `IV` or `V` before `I`).
- **Tails wrap**: a loop is rendered circularly, so echoes and reverb at the end sound at the
  start. A hit right on the first step raises the seam number (in our log a ping on step 1
  moved it from 0.21 to 0.46, still clean) — that is a downbeat, not a click.
- **Whole numbers**: a pad's `swell` should divide the piece's bars (12 for 24 bars).
- **Placing the lift**: the cue's `start:` (seconds into the loop) moves where the video joins
  the piece: `music: {source: time_of_flight, start: 8.9}` starts with the build.
- **Length**: 40–60 s loops repeat once or twice in a short video; a lift every 50 s is
  about right for an explainer.

## 4. Using check and compare

```
vidgen music check assets/music/my_theme.yaml --compare assets/music/my_theme_v1.yaml --out build/check
```

- **The verdict line** is what matters for the video: `fine under narration`, or the topics to
  fix. `note` lines are information.
- **The tracks table** shows each part's share of the power, of the voice range, of the bass and
  of the highs. A part under about 1 % of the whole is barely there: in `time_of_flight` the
  first arpeggio at `volume: -8` was 2 % and the satellite ping 0 % until raised. A part with most
  of the voice-range share is the one to darken or lower first.
- **The advice** names score keys (`` `pad: sections: {lift: {volume: 3.6}}` ``); apply one, check
  again.
- **The comparison table** puts the two versions side by side; change one thing per version so
  the difference has one cause.
- **The spectrogram** (one row per piece, section lines, the voice band between dotted blue
  lines, a lane of voice-range level per bar with its limit): look for the sections where you
  meant them, the filter opening as a widening bright band, nothing bright between the blue lines
  for long stretches, no red bars in the lane.
- **Tempo** "heard 72 BPM = 2/3 of 108" is fine: accents or figures in threes make the onsets
  repeat in threes. "No steady beat" is fine for a calm bed.
- **The key** line says which key the chroma fits best; a dorian piece is heard as its relative
  major (D dorian fits G major) — that is not an error.
- `vidgen lint` repeats the voice-range, highs, bass, steadiness, peaks and seam checks on the
  pieces a video plays (rule `music_check`); the demo MP3 is for the human.

## 5. Genre recipes as score sketches

Short, complete score files to start from instead of a template (all original; each checked
`fine under narration`). Copy one into `assets/music/NAME.yaml`, then work as the recipe says.

**Documentary** — slow, warm, hopeful; a sparse low piano, a soft pulse, a bell in the lift.

```yaml
title: Field Notes (sketch)
key: D dorian
tempo: 84
chord_bars: 2
progression: "i IV i VII"             # Dm G Dm C: the dorian IV keeps it hopeful, not sad
sections:
  - {name: open, bars: 4}             # pad and piano alone
  - {name: body, bars: 8}             # a soft pulse joins
  - {name: lift, bars: 4, progression: "VII IV i i"}
tracks:
  pad:   {instrument: pad, play: chords, settings: {tone: 1500, air: 0.25}, volume: -2,
          sections: {lift: {settings: {tone: 2400}, volume: 0}}}
  piano: {instrument: piano, octave: 3, volume: -6,
          steps: "1 . 5 . 8 . . . | 3' . . . 5 . . ."}   # low and sparse: under the voice's core
  bass:  {instrument: sub, steps: "x . . . . . . . | x . . . . . x .", rest: [open]}
  kick:  {instrument: kick, settings: {decay: 0.25, click: 0.02}, volume: -6,
          steps: "x... .... x... ....", rest: [open]}
  bell:  {instrument: bell, only: [lift], volume: 2, steps: "A5 - - - - - - - | F5 - - - E5 - - -"}
```
Measured: 45.7 s loop, voice range 18 %, lift +2.1 dB and +7.4 dB brighter, voice 25.5 dB clear.

**Uplifting trance** — four on the floor, pumping supersaws, a gated, sweeping build and an open
lift with an echoing arpeggio.

```yaml
title: High Pass (sketch)
key: F# minor
tempo: 138
chord_bars: 2
progression: "VI III VII i"           # D A E F#m
sections:
  - {name: groove, bars: 8}
  - {name: build, bars: 8}
  - {name: lift, bars: 8}
tracks:
  saws:
    instrument: supersaw
    play: chords
    duck: {to: kick, depth: 0.55, release: 0.13}   # the pump: room for the kick
    lowpass: 900
    sections:
      build: {lowpass: [[0, 900], [8, 3600]], gate: {steps: "X.xX .xX. X.xX .x-x", duty: 0.5}}
      lift: {lowpass: 4200, volume: 2, width: 1.4}
  kick:  {instrument: kick, steps: "x... x... x... x...",
          sections: {build: {steps: "x... x... x... x... | x... x... x... x... | x... x... x... x... | x... x... x... x... | x... x... x... x... | x... x... x... x... | x... x... x... x... | ...."}}}
  bass:  {instrument: analog_bass, steps: ".1.1 .1.1 .1.1 .1.1", settings: {tone: 900}}
  hat:   {instrument: open_hat, steps: "..x. ..x. ..x. ..x.", rest: [groove]}
  clap:  {instrument: clap, steps: "....x.......x...", only: [lift]}
  arp:   {instrument: fm_pluck, steps: "1 5 8 5 1 5 8 5 1 5 8 5 9 8 5 3", octave: 4, volume: -6,
          echo: {delay: 0.75, feedback: 0.35, repeats: 2}, only: [lift]}
  riser: {instrument: riser, only: [build], steps: ". | . | . | . | x | - | - | -", volume: 3}
```
Measured: 41.7 s loop, heard 138 BPM, voice range 10 %, build +10 dB brighter, lift +4.1 dB and
+7 dB brighter. The kick drops out for the build's last bar: the lift lands harder.

**Synthwave / night drive** — eighth-note analog bass, a gated snare on 2 and 4, a soft saw pad,
a square arpeggio with echoes, a lead in the lift.

```yaml
title: Overpass (sketch)
key: A minor
tempo: 96
chord_bars: 2
progression: "i VI III VII"           # Am F C G, slow and open: a night drive
sections:
  - {name: cruise, bars: 8}
  - {name: lift, bars: 8, progression: "VI VII i i"}
tracks:
  pad:   {instrument: saw_pad, play: chords, volume: -1, settings: {tone: 1400},
          sections: {lift: {settings: {tone: 2200}, volume: 1}}}
  bass:  {instrument: analog_bass, steps: "1 1 1 1 1 1 1 1"}          # driving eighths
  kick:  {instrument: kick, steps: "x... .... x... ...."}
  snare: {instrument: gated_snare, steps: ".... x... .... x...", volume: 4}   # the 80s gated snare on 2 and 4
  hat:   {instrument: hat, steps: "x.x. x.x. x.x. x.x.", spread: 0.3}
  arp:   {instrument: square_pluck, octave: 4, steps: "1 3 5 8 5 3 1 3 5 8 5 3 1 3 5 3", volume: 3,
          spread: 0.3, echo: {delay: 0.75, feedback: 0.3, repeats: 2}, lowpass: 2400}
  lead:  {instrument: soft_lead, only: [lift], volume: -2, reverb: {size: 2.4, mix: 0.3},
          steps: "E5 - - - - - D5 - | C5 - - - - - . . | B4 - - - C5 - D5 - | E5 - - - - - . ."}
```
Measured: 40 s loop, voice range 29 %, lift +1.7 dB and +5.8 dB brighter, voice 22 dB clear.

**Cosmic / pulsar** — no beat: a wide dark pad, pulsar ticks and radio static, a sub and a deep
boom when the lift opens, a glassy shimmer above the voice.

```yaml
title: Deep Field (sketch)
key: C# minor
tempo: 72
chord_bars: 4
progression: "i VI"                   # C#m A: slow and wide, no resolution
sections:
  - {name: drift, bars: 8}
  - {name: lift, bars: 8, progression: "VI VII i i"}
tracks:
  pad:    {instrument: pad, play: chords, settings: {tone: 1200, air: 0.4, swell: 8, sub: 0.4}, volume: -2,
           sections: {lift: {settings: {tone: 2000}, volume: 0}}}
  shimmer: {instrument: glass, play: chords, volume: -2, only: [lift]}   # high and quiet, above the voice
  pulsar: {instrument: pulsar, steps: "X... .... ..x. .... | x... .... ..x. ..x.", spread: 0.4, volume: 5}
  static: {instrument: static, steps: "x | - | - | - | - | - | - | -", volume: 2}
  sub:    {instrument: sub, steps: "1 . . . . . . . | . . . . 1 . . .", rest: [drift]}
  boom:   {instrument: boom, steps: "x | . | . | . | . | . | . | .", only: [lift]}
```
Measured: 53.3 s loop, no steady beat (fine), voice range 13 %, lift +2.4 dB and +7.7 dB
brighter, voice 26.6 dB clear. The pad is 94 % of the power: the ticks and static are small on
purpose, but at their defaults (`volume: 0`) the check showed them under 1 % — raise them first.

**Cartoon** — bouncy oom-pah on pizzicato, a woodblock, snaps from the second phrase, a
music-box tune in the lift.

```yaml
title: Puddle Jump (sketch)
key: F major
tempo: 132
chord_bars: 1
progression: "I vi ii V"              # F Dm Gm C: a bouncy turnaround
sections:
  - {name: a, bars: 8}
  - {name: b, bars: 4, progression: "IV IV I V"}
  - {name: lift, bars: 4}
tracks:
  bass:  {instrument: pizzicato, octave: 2, steps: "1 . 5 . 1 . 5 ."}       # oom...
  chords: {instrument: pizzicato, octave: 3, steps: ". v2+v3+v4 . v2+v3+v4 . v2+v3+v4 . v2+v3+v4", volume: -4}   # ...pah
  block: {instrument: woodblock, steps: "x.x. ..x. x.x. ....", volume: -4}
  snap:  {instrument: snap, steps: ".... x... .... x...", only: [b, lift]}
  tune:  {instrument: music_box, only: [lift], volume: -2,
          steps: "C6 . A5 . F5 . . . | D6 . . . A5 . . . | Bb5 . G5 . D5 . . . | C6 . . . . . . ."}
```
Measured: 29.1 s loop, voice range 28 %, loudest voice-range bar −27.6 dB (close to the −26
limit: the pah chords are in octave 3–4; lower them a dB or two under dense dialogue), lift
+1.2 dB and +2.2 dB brighter.

## 6. Common mistakes and their fixes

| what you see | why | fix |
|---|---|---|
| "the build does not build" | every part plays the same through it | a `lowpass` sweep or `volume` ramp on the main part; parts entering at its start (`rest: [intro]`) |
| "the lift does not lift" although parts enter there | the new parts are too quiet to count (check the tracks table) | open the pad's filter and raise it 1–2 dB in the lift; `only: [lift]` parts at audible levels |
| a part at 0–1 % of the whole | default levels are the beds' (a hat is 0.06 of a kick) | raise it 4–8 dB, check again |
| voice-range share or loudest bar flagged | pad open, figure in octave 4, melody busy | `lowpass: 1500`–`2600` on the pad, the figure an octave down or up, fewer melody notes |
| highs flagged | open hats, master filter opened, loud ticks | `lowpass: 5000` on the hats, master `lowpass: 4500` (the default), quieter ticks |
| unsteady | a near-silent intro before a loud lift | bring the intro up (a pad at −3 dB rather than −12), or make the lift smaller |
| key: few notes on the key's scale | chords or a melody from another key | Roman numerals in the score's key; a section `key:` for a real modulation |
| changing a template's key sounds wrong | its progression writes out G-minor voicings (`{chord, notes, bass}`) | replace the progression with Roman numerals (a string) when you change the key |
| a seam number near 1 | a curve ending far from where it starts, or a loud tail | end each curve on its starting value; shorter echoes or reverb at the end |
| a piece named like a bed (`calm.yaml`) | the names would clash | rename it, or use `source: assets/music/calm.yaml` |
