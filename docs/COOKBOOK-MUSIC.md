# Music craft: writing score files that sit under a voice

Craft notes for music written as **score files** (YAML: key, tempo, sections, chords, tracks of
step patterns; `docs/CONFIG.md`, "Score files"). The author guide's "Making music" recipe says
*how* to work (start from a template, change one thing at a time, check, compare, let a human
choose); this page says *what* tends to work, with the numbers `vidgen music check` reports.
Everything here was measured, not heard: an agent cannot listen, and neither could the agent that
wrote this page. A person listens and chooses.

Worked example: [examples/gps-time-of-flight](../examples/gps-time-of-flight/README.md), a piece
turned from the `momentum` template into something new in nine checked steps, playing under a
narrated GPS explainer; a person listened and made it the built-in bed `time_of_flight`. Hear
it, and the other built-in beds (17 in all), on the [Listen page](music/README.md). Three of the
beds, `tidewater`, `skyline` and `time_of_flight`, are score files themselves: `vidgen music
template tidewater` shows a finished piece written in the format.

Contents: [room for the voice](#1-room-for-the-voice) ·
[energy curves](#2-energy-curves-builds-and-lifts) · [loops](#3-loop-design) ·
[check and compare](#4-using-check-and-compare) · [genre sketches](#5-genre-recipes-as-score-sketches) ·
[common mistakes](#6-common-mistakes-and-their-fixes) ·
[a person and an agent in the studio](#7-a-person-and-an-agent-in-the-studio) ·
[brass and organ](#8-brass-and-organ) · [bowed strings](#9-bowed-strings) ·
[orchestral percussion and choir](#10-orchestral-percussion-and-choir) ·
[making it expressive](#11-making-it-expressive) ·
[pictures that follow the score](#12-pictures-that-follow-the-score) ·
[every instrument at a glance](#13-every-instrument-at-a-glance)

A worked example of sections 8–12 together: [examples/signal-fire](../examples/signal-fire/README.md),
an original 24 s orchestral cue with dynamics, hairpins and slurs, and a three.js page that
follows it.

## 1. Room for the voice

The voice lives between **300 Hz and 3 kHz**; schu-video-generator plays music at −28 LUFS and ducks it 12 dB
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
  measures almost nothing at its normal level (30–40 dB under a full build); do not rely on
  it alone. When a build with a riser fails, the check says how many dB under the rest it sits
  and how far to raise it.
- **Hold across the change**: a note can run from the build into the lift — the lift's steps
  start with `-` (`sections: {lift: {steps: "- - - - | x..."}}`), so a pad chord or a static
  swell started in the build carries on over the bar line.

A lift after a quiet break passes the check against the break; the check adds a note when it
stays quieter than an earlier section (the build), since it may not feel like the high point.

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
  the piece: `music: {source: time_of_flight, start: 8.9}` starts with the build; `section: build`
  says the same by name. To make the lift begin with a scene, split the music into two cues and
  start the second at the section: `[{source: time_of_flight, to: setup, fade_out: 0.5},
  {source: time_of_flight, from: reveal, section: lift, fade_in: 0.3}]`.
- **Pumping**: `duck: {to: kick, depth: 0.5}` dips at every kick hit alike; with `follow: true`
  soft hits (`o`) dip half as deep and accents (`X`) half again as deep, a gentler pulse.
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
  major (D dorian fits G major) — that is not an error. It also looks under every chord: a part
  whose notes there are off both the key and the chord (a melody written against one chord) is
  named, with the notes and the chord's own notes.
- **Names work too**: in the project's folder `vidgen music check my_theme --compare momentum`
  checks the project piece against the built-in bed (a bed made by code is checked as audio).
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
| key: a part clashes under one chord | written notes (`F#5`) that fit neither the key nor that chord | degrees (`1 3 5 8`) follow each chord; or fix the notes the advice lists |
| "it may not feel like the high point" | a lift after a quiet break, quieter than the build | raise the lift's main part, or make the build smaller |
| changing a template's key sounds wrong | its progression writes out G-minor voicings (`{chord, notes, bass}`) | replace the progression with Roman numerals (a string) when you change the key |
| a seam number near 1 | a curve ending far from where it starts, or a loud tail | end each curve on its starting value; shorter echoes or reverb at the end |
| a piece named like a bed (`calm.yaml`) | the names would clash | rename it, or use `source: assets/music/calm.yaml` |

## 7. A person and an agent in the studio

An agent cannot listen; a person can, but may not want to write YAML. `vidgen studio`
([reference](CONFIG.md#music-studio-vidgen-studio)) puts them on the same piece: the person
listens and says what they hear, the agent changes the score and says why, and every step is a
version either of them can go back to. A session that works:

1. **Load a preset.** `vidgen studio` in the project folder; **Preset ▾** → the bed closest to the
   video (the one-line descriptions help: `momentum` for a driving explainer, `tidewater` for
   something calm). Press Space and listen to it once through, with **under narration** on for
   the second time: that is how the video will play it.
2. **Pin notes while it plays.** Press **N** at the moment something bothers or delights you and
   type a few plain words: "the ostinato feels stiff here", "I want goosebumps at the turn",
   "love this bell". A note records the bar, beat, section and version, so "here" is enough.
   Small fixes you can make yourself: a track's volume bar, mute (**M**) to hear what a part
   adds, a slider in the inspector; each is a version.
3. **Ask an agent.** **Ask an agent** (Notes tab) writes a hand-off: the score, the open notes,
   the check and the last change. Tell your agent (connected with `vidgen mcp`) *answer my
   studio notes*; it reads the session with `studio_read`, checks its change with
   `studio_check`, and proposes a new version with one line per note with `studio_propose`.
   The proposal appears above the tracks within two seconds. (No MCP agent? **Copy prompt** into
   any chat assistant and **Paste reply**.)
4. **A/B it.** **A/B vN vs vM** plays the proposal and the current version at the same moment and
   the same level; switch back and forth at the bar the note was about (click the note's time).
   Read the check's verdict too: a proposal that sounds better but says *needs work* under
   narration will fight the voice. **Keep** it (its notes are resolved) or **Discard** it, add
   new notes, ask again. **A/B original** is always there to hear how far you have come.
5. **Try variations when you are stuck.** **V** (or **Variations**) makes four siblings — another
   harmony, pattern, mix and energy — rendered and checked side by side. Play each at the same
   moment; **More like this** on the one that is closest; **Keep** makes it the next version.
   Candidates not kept stay listed under **Batches ▾**.
6. **Save to the project.** **Export → Save to the project** writes `assets/music/<name>.yaml`;
   the video plays it with `music: <name>`. Render a preview of the video and listen under the
   real narration once more; the studio's versions stay in `build/studio/` if you want to go back.

What agents should keep in mind when handed a session: answer every open note (one line each,
even "left as is: …"), change only what the notes ask for, keep tempo and key unless a note asks,
and run `studio_check` before proposing — a person's ear decides, but the check catches what
would sit badly under a voice. When a person asks an agent to "make the music better" without
saying how, suggesting the studio is often the shortest way to find out what they hear.

## 8. Brass and organ

Four instruments made for the orchestral colours of film scores (Step 343; reference:
[CONFIG](CONFIG.md#score-files-vidgen-music-render), `vidgen music patches`). They are synthesised, not
sampled, and were tuned by measurement: nobody has listened yet, so check a piece that leans on
them with `vidgen music check` and by ear.

| instrument | written range | default octave | what it is for | settings to reach for first |
|---|---|---|---|---|
| `trumpet` | E3–C6 | 4 | a singing solo line, fanfares | `attack` 0.02 (tongued) to 0.3 (soft); `brightness` 0.15 (far, soft) to 1 (blaring); `vibrato` 0–15; `mute: 1`; `players: 3` for a section |
| `horn` | B1–F5 | 3 | warm held notes and slow counter-lines in the tenor; `players: 4` for the film-score horn line | `attack` 0.1–0.3; `brightness` 0.3–0.5 (round) or 0.9 (brassy); `mute: 1` (stopped) |
| `low_brass` | E1–F4 | 2 | sustained low chords, swells, heavy low notes; a section of 4 | `attack` 1–4 with `brightness: 1` (a swell that opens); `tuba` 0.5–1; `players` up to 8 |
| `organ` | C1–C7 | 3 | held chords, chorales, a pedal bass | `registration` (`cathedral`, `principal`, `flute`, `reed`, `drawbar`, `full`); `drawbars: "86 8400 000"` |

**How to write for them**

- Hold notes with `-` and end them with `.`: `"A4 - - - - - . ."`. A phrase breathes where it
  rests. Each note has its own attack, so for a smooth line use `attack: 0.1`–`0.2` and let the
  notes touch (no rest between them); for a fanfare use `attack: 0.02` with rests.
- Loud and soft are `brightness`, not `volume`: 0.2 with `attack: 0.3` sounds far and gentle, 1.0
  with `attack: 0.02` sounds close and hard, at the same level. Use `sections:` to change it:
  `sections: {climax: {settings: {brightness: 1.0}}}`.
- A swell: one long note with `attack` as long as the swell (up to 4 s): it starts dark and opens.
  A `volume` curve on top makes it longer (`volume: {from: -12, to: 0}`), but only the instrument's
  own `attack` changes the tone.
- Keep them in their range: a trumpet under E3 or a horn above F5 still plays, but stops sounding
  like one. Put chords for horns in octave 3 (`v2+v3`: two inner notes of the chord's voicing) and
  the low brass on root and fifth in octave 2 (`"1+5 | -"`); thirds in the low brass are muddy
  under about C3.
- Brass in the voice's range (300 Hz–3 kHz) competes with narration more than a pad does. Under a
  voice: `brightness` at most 0.4, the horn rather than the trumpet, and a reverb with a dark
  `tone`.
- The organ needs a room: `reverb: {size: 4, mix: 0.35}` or more. `cathedral` is loud in the
  highs (mixtures); under a voice use `principal` or `flute`, or lower `tone` to 3000.
- An organ note never decays. Give long chords an end (`"* - - - - - - ."`) or the piece has no air.

**A brass chorale with an organ** (D minor, 84 BPM; original)

```yaml
version: 1
title: Chorale
key: D minor
tempo: 84
loop: false
progression: "Dm Bb F C Gm Dm A D"
sections:
  - {name: organ, bars: 8}
  - {name: all, bars: 8}
tracks:
  organ:   {instrument: organ, settings: {registration: principal}, steps: "* - - - - - - -",
            reverb: {size: 5, mix: 0.4, tone: 4500},
            sections: {all: {settings: {registration: cathedral}}}}
  pedal:   {instrument: organ, octave: 1, settings: {drawbars: "86 8400 000"}, steps: "x - - - - - - -",
            reverb: {size: 5, mix: 0.4, tone: 3000}}
  horns:   {instrument: horn, only: [all], settings: {players: 4, attack: 0.14}, steps: "v2+v3 - - - - - - -",
            reverb: {size: 5, mix: 0.4, tone: 4500}}
  low:     {instrument: low_brass, only: [all], settings: {attack: 0.25, tuba: 0.5}, steps: "x - - - x' - - - | x - - - - - - -",
            reverb: {size: 5, mix: 0.4, tone: 4500}}
  trumpet: {instrument: trumpet, only: [all], settings: {attack: 0.07, vibrato: 10},
            reverb: {size: 5, mix: 0.4, tone: 4500},
            steps: "D5 - - - F5 - E5 - | D5 - - - - - Bb4 - | C5 - - - A4 - - - | G4 - - - - - E4 - | G4 - - Bb4 - - D5 - | F5 - - - E5 - D5 - | E5 - - - - - C#5 - | D5 - - - - - - -"}
```

**The low swell and the heavy low note**

```yaml
swell: {instrument: low_brass, octave: 2, settings: {attack: 3.2, brightness: 1.0, tuba: 0.8, players: 6, ring: 0.4},
        steps: "x | - - - - - - - . | . | .", reverb: {size: 4.5, mix: 0.4}}
hit:   {instrument: low_brass, octave: 2, settings: {attack: 0.18, brightness: 1.0, tuba: 1.0, players: 8, detune: 10, ring: 0.6},
        steps: "1+5 - - - - - . . | .", reverb: {size: 4.5, mix: 0.35}}
```

Put a `boom` or a low `kick` under the hit's first step for the impact; the brass supplies the
tone that follows.

## 9. Bowed strings

Four string instruments (Step 344; reference: [CONFIG](CONFIG.md#score-files-vidgen-music-render),
`vidgen music patches`). Like the brass they are synthesised, not sampled, and were tuned by
measurement: nobody has listened yet.

| instrument | written range | default octave | players | what it is for |
|---|---|---|---|---|
| `violins` | G3–C7 | 4 | 6 | the melody, high held chords, tremolo beds, high ostinatos |
| `violas` | C3–E6 | 3 | 5 | inner parts, the middle ostinato, a darker melody |
| `cellos` | C2–A5 | 2 | 4 | tenor melodies, bass lines, the low ostinato |
| `double_basses` | C1–G4 | 1 | 3 | the bass note under everything, bowed or plucked |

| setting | default | what it does |
|---|---|---|
| `stroke` | `sustain` | `sustain` (bowed while held), `spiccato` (one short stroke per note), `tremolo` (a held note of fast strokes), `pizzicato` (plucked) |
| `players` | by instrument | 1 a solo (mono); more a section in stereo, as loud as one player |
| `attack` | 0.1 | sustain, tremolo: 0.03–0.06 firm with a bite, 0.1–0.3 smooth, 0.5–4 a swell |
| `brightness` | 0.5 | 0 over the fingerboard (dark), 1 at the bridge (glassy); the level stays |
| `vibrato` | 12 | cents; starts 0.16 s into a sustained note; 0 for a cold, still sound |
| `accent` | 1 | the bite of a stroke, 0 (none) to 2 (hard); tremolo: the depth of each stroke; pizzicato: how hard it is plucked |
| `length` | 0.07 | spiccato: seconds the bow is on the string; 0.05 very short, 0.15–0.25 staccato |
| `speed` | 13 | tremolo: strokes a second (6–20) |
| `decay` | 1 | spiccato, pizzicato: how long the string rings, times its natural time |
| `bow` | 1 | rosin noise and scratch (0 none); a held note's hiss stays under its tone's highs, so dark and swelling notes have less |
| `mute` | 0 | 1: con sordino (veiled) |
| `detune` | 8 | cents between the players of a section |
| `ring` | 0.25 | seconds of release; notes without a rest between them overlap by it |

**How to write for them**

- A melody: `stroke: sustain`, `attack` 0.1–0.2, no rests inside a phrase (`"A4 - - - D5 - E5 -"`),
  a rest where the phrase breathes. For a solo instrument `players: 1` and `vibrato` 15–20.
- An ostinato: `stroke: spiccato` on sixteenths. Every stroke of a pitch is identical and all
  pitches are as loud, so the pattern is even by itself; give it life with the track's
  `accent: "3+3+2"` and a `volume` curve over the section. Cellos in octave 2, violas in 3,
  violins in 4 doubling the pattern is the film-score engine. Above about 170 BPM use
  `length: 0.05`. Do not use `pad` or `supersaw` note by note for this: their level changes
  from note to note.
- A tension bed: violins and violas `stroke: tremolo` on two or three notes held for bars, with
  `brightness: 0.8` and `volume: {from: -20, to: 0}`; cellos and basses hold a low note with
  `attack: 1.5`.
- Chords for the whole section: basses `x` in octave 1, cellos `1+5` in octave 2, violas
  `v1+v2`, violins `v2+v3` or the melody. Seat them with `pan` (violins −0.4, violas −0.05,
  cellos 0.25, basses 0.15) and give all one `reverb` (`size` 3.5–4.5, `mix` 0.3–0.4).
- A plucked bass: `double_basses` with `stroke: pizzicato` on `"x . . . x . . ."`; hold a note
  (`"x - - -"`) to let it ring.
- Quiet strings are not `volume` alone: `brightness: 0.25`, `attack: 0.5`, `accent: 0`, and
  `mute: 1` for a veiled sound. Under a voice keep violins out of 1–3 kHz melodies or mute them.
- Replacing a `pad` that played "violins" note by note: the strings sit about 8 dB lower than
  the pad at the same `volume` (the level of the brass and of piano chords), so raise the track.

**A string section: melody, ostinato and a tremolo bed** (D minor, 138 BPM; original)

```yaml
version: 1
title: String engine
key: D minor
tempo: 138
loop: false
progression: "Dm Bb Gm A"
chord_bars: 2
sections:
  - {name: bed, bars: 8}
  - {name: engine, bars: 8}
tracks:
  violins:
    instrument: violins
    pan: -0.4
    reverb: {size: 3.5, mix: 0.32, tone: 4500}
    sections:
      bed: {settings: {stroke: tremolo, brightness: 0.8, attack: 0.4}, volume: {from: -20, to: 0},
            steps: "D5+A5 | - | - | - | D5+Bb5 | - | C#5+A5 | - - - - - - - - - - - - - - . ."}
      engine: {settings: {attack: 0.14},
               steps: "A4 - - - - - - - D5 - - - E5 - - - | F5 - - - - - - - E5 - - - D5 - - - | D5 - - - - - - - - - - - F5 - - - | Bb5 - - - - - - - A5 - - - G5 - - - | G5 - - - - - - - - - - - D5 - - - | Bb4 - - - - - - - - - - - D5 - - - | E5 - - - - - - - - - - - C#5 - - - | D5 - - - - - - - - - - - . . . ."}
  violas:
    instrument: violas
    pan: -0.05
    reverb: {size: 3.5, mix: 0.32, tone: 4500}
    sections:
      bed: {settings: {stroke: tremolo, brightness: 0.8, attack: 0.4}, volume: {from: -20, to: 0}, steps: "F4 | - | - | - | F4 | - | E4 | - - - - - - - - - - - - - - . ."}
      engine: {settings: {stroke: spiccato}, accent: "3+3+2", steps: "1 5 8 1 5 8 5 3 1 5 8 1 5 8 5 3"}
  cellos:
    instrument: cellos
    pan: 0.25
    reverb: {size: 3.5, mix: 0.32, tone: 4500}
    sections:
      bed: {settings: {attack: 1.5, brightness: 0.35}, volume: {from: -16, to: 0}, steps: "x | - | - | - | x | - | x | - - - - - - - - - - - - - - . ."}
      engine: {settings: {stroke: spiccato}, accent: "3+3+2", steps: "1 5 8 1 5 8 5 3 1 5 8 1 5 8 5 3"}
  basses:
    instrument: double_basses
    pan: 0.15
    reverb: {size: 3.5, mix: 0.32, tone: 4500}
    sections:
      bed: {settings: {attack: 1.5, brightness: 0.35}, volume: {from: -16, to: 0}, steps: "x | - | - | - | x | - | x | - - - - - - - - - - - - - - . ."}
      engine: {settings: {stroke: pizzicato}, steps: "x . . . . . . . x . . . . . x ."}
```

## 10. Orchestral percussion and choir

Eight percussion instruments and a choir (Step 345; reference:
[CONFIG](CONFIG.md#score-files-vidgen-music-render), `vidgen music patches`). Synthesised, not
sampled, and tuned by measurement: nobody has listened yet.

| instrument | written as | range or pitch | what it is for |
|---|---|---|---|
| `timpani` | notes (`D2 . A2 .`) | D2–A3 (plays C2–C4) | the pitched drum under the brass: roots and fifths, rolls |
| `toms` | notes (`C4 A3 F3 D3`) | G1 (floor) – C5 (high) | fills from high to low, low tribal patterns |
| `taiko` | drum steps (`X..x`) | `pitch` 36–130 Hz (62) | the big film-score hit; `players: 6` an ensemble |
| `bass_drum` | drum steps | `pitch` 26–75 Hz (40) | a deep, soft bloom under a hit; a slow pulse |
| `frame_drum` | drum steps | `pitch` 55–280 Hz (110) | hand-drum patterns; `edge: 1` the rim |
| `snare_drum` | drum steps | `pitch` 130–280 Hz (185) | march figures, `stroke: roll` into a hit |
| `cymbal` | drum steps | `pitch` 0.6–1.6 (size) | a crash; `stroke: swell` grows into a hit |
| `tam_tam` | drum steps | `pitch` 0.6–1.8 (size) | the dark gong on the last chord, a soft one at the start |
| `choir` | notes and chords | E2–C6 | held vowels (`ooh aah eeh mm oh ee`) and syllables (`la na ma da`, `mm-ah`, `ah-oh` ...), a soloist, a whisper: voices, no words |

**Into a hit.** The bar before the hit: a snare roll and a timpani roll under `volume` curves,
and a cymbal swell that ends on the hit. On the hit: taikos, a bass drum under them (it adds
the bloom the taiko's short crack lacks), a crash, and for a last chord the tam-tam. The
sketch below is this, twice, with a choir.

**Rolls and swells.** `stroke: roll` holds a steady level: write the crescendo as
`volume: [[0, -24], [2, 0]]` (bars from the section's start), or, since Step 346, with marks
on one track: `"[roll pp <] A2 - - - - - - - | [hit ff] D2 . . ."` (section 11).
`stroke: swell` needs no curve. Use a soft mallet for a timpani roll (`mallet: 0.2`) and a short `ring` (0.3), or the
roll rings on over the hit.

**Soft and loud.** A dynamic mark does both: `[p] x` is softer and rounder, `[ff] x` louder
and harder (section 11). `X` and `o` in the steps change the level only, unless the track has
`touch: 1`.

**Tuning drums.** Timpani play the root and the fifth of the chord (`D2`, `A2`); keep them
between D2 and A3. A taiko's `pitch` need not fit the key, but an ensemble a fifth or an
octave under the bass note sits better than one a semitone off: 62 Hz is near B1, 73 Hz is D2.

**The choir.** Write it like a pad that takes notes: chords with `*` or note names, long
holds, a hall. `voices: mixed` shares each note out by its pitch, so one track can sing a chord
from the basses to the sopranos; for a chorale write four tracks (`voices: sopranos`, `altos`,
`tenors`, `basses`). `ooh` under a voice-over (dark, little above 1 kHz), `aah` for the climax
(with `brightness: 0.7`), `mm` for the quietest bars. It will not pass for a recorded choir in
an exposed place: keep it inside the orchestra or under a reverb.

```yaml
# a 12-bar sketch: two rises into two hits, D minor, 100 BPM
key: D minor
tempo: 100
loop: false
sections:
  - {name: rise, bars: 4, progression: "Dm Bb Gm A"}
  - {name: hit, bars: 2, progression: "Dm Dm"}
  - {name: again, bars: 4, progression: "Bb Gm A A"}
  - {name: end, bars: 2, progression: "D D"}
tracks:
  choir:
    instrument: choir
    reverb: {size: 4.5, mix: 0.36, tone: 4500}
    sections:
      rise: {settings: {vowel: mm, morph: ooh, attack: 1.5}, volume: {from: -10, to: -2}, steps: "* - - - - - - -"}
      hit: {settings: {vowel: aah, brightness: 0.7, attack: 0.12}, steps: "D3+A3+D4+F4+A4 | - - - - - . ."}
      again: {settings: {vowel: ooh, voices: men}, octave: 3, steps: "1+5 - - - - - - -"}
      end: {settings: {vowel: aah, brightness: 0.7, attack: 0.12, ring: 1.5}, steps: "D3+A3+D4+F#4+A4 | - - - - - . ."}
  timpani:
    instrument: timpani
    sections:
      rise: {settings: {ring: 0.8}, steps: ["D2 . . . . . . . . . . . A2 . . .", "D2 . . . . . . . . . . . F2 . F2 .", "G2 . . . . . . . G2 . . . D3 . G2 .", "A2 . . A2 . . A2 . A2 . A2 . A2 A2 A2 A2"]}
      hit: {steps: "D2+A2 . . . . . . . | ."}
      again: {settings: {stroke: roll, mallet: 0.2, ring: 0.3}, volume: [[0, -24], [4, 0]], steps: "Bb2 | G2 | A2 | -"}
      end: {steps: "D2+A2 . . . . . . . | ."}
  toms:
    instrument: toms
    only: [rise]
    steps: [".", ".", ".", ". . . . . . . . C4 . A3 . F3 F3 D3 A2"]
  frame:
    instrument: frame_drum
    reverb: {size: 2.8, mix: 0.3}
    only: [rise, again]
    volume: -4
    steps: "x..o ..x. o..x ..o."
  snares:
    instrument: snare_drum
    only: [rise, again]
    settings: {stroke: roll, players: 4}
    sections:
      rise: {volume: [[0, -60], [2.99, -60], [3, -20], [4, 0]], steps: ". | . | . | x"}
      again: {volume: [[0, -60], [1.99, -60], [2, -24], [4, 0]], steps: ". | . | x | -"}
  swell:
    instrument: cymbal
    only: [rise, again]
    settings: {stroke: swell}
    reverb: {size: 4.5, mix: 0.36}
    sections:
      rise: {steps: ". | . | x | -"}
      again: {steps: ". | . | x | -"}
  taiko:
    instrument: taiko
    settings: {players: 6}
    reverb: {size: 3.4, mix: 0.3, tone: 3000}
    sections:
      rise: {volume: -5, steps: ["X... .... .... ....", "X... .... .... ....", "X... .... ..x. ....", "X... .... x... x.x."]}
      hit: {volume: 1, steps: "X..x ..x. X... x.x. | X..x ..x. x.x. xxxx"}
      again: {volume: -5, steps: "X... .... .... ...."}
      end: {volume: 2, steps: "X | ."}
  bass_drum:
    instrument: bass_drum
    only: [hit, end]
    steps: "x | ."
  crash:
    instrument: cymbal
    only: [hit, end]
    settings: {mallet: 0.8}
    reverb: {size: 4.5, mix: 0.36}
    steps: "x | ."
  gong:
    instrument: tam_tam
    only: [end]
    reverb: {size: 4.5, mix: 0.36}
    steps: "x | ."
```

Things that go wrong:

- *A timpani part written with `x`* follows the chord's bass note in the track's octave: write
  note names.
- *A roll that never grows*: `stroke: roll` is steady; add a hairpin (`[roll pp <] ... [ff]`)
  or the `volume` curve.
- *A swell that peaks early or late*: it peaks where its held steps end. `"x | -"` over the two
  bars before the hit, then nothing.
- *The hit is all crack*: add the `bass_drum`, or lower the taiko's `mallet` to 0.4.
- *The choir sounds like an organ*: more `singers` and `detune`, a longer `attack`, more
  reverb; a single held chord without movement is its weakest use.
- *Sopranos above A5* have one vowel only (a real choir's too); write the vowel lower.
- *Syllables that sound late*: a consonant takes 0.08–0.12 s before the vowel arrives (it
  starts on the step). In a fast line use `la` or `na` (the softest) and fewer of them; a
  syllable on every sixteenth is a stutter.
- *A soloist lost in the choir*: give it its own track, `volume: 1` to `3`, and keep the
  section on `ooh` or `mm` five dB under it; the soloist is brighter already.

**Syllables, a soloist, a whisper** (Step 361). Still no words, but a line can now be sung
rather than held. `syllable: la` (a track or section setting) or `[la]` before a note starts it
with a soft consonant: `l` and `n` are the gentlest, `m` hums first, `d` has a small burst, the
mark for articulated rhythm. Two-vowel syllables glide at `turn` (`ah-oh`, `oo-ah`, `mm-ah`: a
hum that opens, as `morph` does but timed). A syllable stays in force until another mark, so
`[la] C4 D4 [na] E4` sings la, la, na. In a slur only the first note gets the consonant; write a
syllable inside the slur where the line should re-articulate without a new breath. A soloist
(`soloist: true`, one voice, brighter, a wider and later vibrato, a scoop into each attacked
note) sits over a section holding `ooh`. `whisper` turns tone into breath (0.3–0.6 breathy, 1 a
whisper) at about the same loudness: whisper an opening, then mark `[whisper=0.4]` and
`[whisper=0]` on the chords that follow. The default (`syllable: vowel`, no soloist, no
whisper) is the choir above, unchanged.

```yaml
# 4 bars: men on "na la", women on "ooh", a soprano soloist; D minor, 72 BPM
key: D minor
tempo: 72
loop: false
sections:
  - {name: verse, bars: 4, progression: "Dm Bb Gm A"}
tracks:
  men: {instrument: choir, settings: {voices: men}, octave: 3, steps: "[na] 1 - [la] 5 - [na] 8 - [la] 5 -"}
  women: {instrument: choir, settings: {voices: women, vowel: ooh, syllable: mm-oo}, volume: -5, steps: "[whisper=0.6] * - - - - - - - | [whisper=0] * - - - - - - -"}
  solo:
    instrument: choir
    settings: {voices: sopranos, soloist: true, vowel: aah}
    volume: 1
    steps: ". . . . . . . . | . . . . . . . . | [mp] D5 - - - [la] (Bb4 - C5 - | C#5 - - - [ah-oh] E5 - - -)"
```

## 11. Making it expressive

Marks make a line breathe: dynamics, hairpins, slurs and per-note settings (Step 346;
reference: [CONFIG](CONFIG.md#score-files-vidgen-music-render), DESIGN §120.7). A score without
them sounds exactly as before, so add them to a finished piece one track at a time and compare
with `vidgen music check ... --compare`.

| write | what it does | where |
|---|---|---|
| `[pp] [p] [mp] [mf] [f] [ff]`, `[-6]` | the level from this step on (−15, −10, −5, 0, +4, +7 dB; an unmarked note is `mf`) and the tone | every note and drum track |
| `[p <] ... [f]`, `[f >] ... [p]` | a hairpin: the level moves from its step to the next dynamic, inside a held note or over a phrase | every track |
| `[fp]`, `[sfz]` | a loud start dropping to piano in 0.25 s; one note 7 dB over the level in force | every track |
| `[spiccato]`, `[stroke=pizzicato]`, `[pitch=100]`, `[default]` | a setting from this step on; `[default]` returns to the track's | every instrument with settings |
| `(A4 - C5 - E5 - - -)` | a slur: one bow or breath, the pitch gliding (`glide` seconds) | brass, strings (sustain, tremolo), `choir`, `soft_lead` |
| `[la]`, `[mm-ah]`, `[syllable=na]`, `[whisper=0.5]`, `[vowel=ooh]` | what a choir sings from this note on; inside a slur a syllable or vowel only where written (section 10) | `choir` |
| `vibrato_speed`, `vibrato_delay` | the vibrato's speed (Hz) and when it begins (s), beside its depth `vibrato` | the same instruments |
| `sections: {lift: {instrument: trumpet}}` | the track plays another instrument in that section | a note track to a note instrument, a drum track to a drum |

**The tone follows the level.** On brass a louder note is blown harder (brighter), on strings
more bow (brighter, with more bite at the stroke's start), a choir sings fuller, a drum is
struck harder (the `mallet` and, on toms and taiko, the pitch drop). The organ, the pads and
the older instruments only get louder. That is the difference from a `volume` curve, which
turns the same sound up: a crescendo written as a hairpin opens the tone as it grows. Keep
`volume` for the mix and marks for the music. `touch: 1` makes the old accents (`X`, `!`,
`accent: 3+3+2`) bite as a dynamic mark would; it is 0 by default so old scores stay as they
were.

**Hairpins.** A hairpin runs from the step that opens it to the next dynamic, which says where
it arrives; that mark may stand at the very end of the steps (`"[p <] A3 - - - - - - - [f]"`).
Inside a held note the level and the tone move smoothly; notes shorter than a quarter second
take the level at their start, so over a phrase of short notes each note is a little louder
than the one before. A swell is two hairpins: `"[p <] A3 - - - [f >] - - - [p] ."`. A `fp`
followed by `<` is the film-score brass swell from nothing: `"[fp <] D4 - - - - - - - [ff]"`.

**Slurs.** Notes in parentheses are not attacked again: on a violin the bow keeps moving, on a
trumpet the breath goes on; the vibrato does not restart. `glide: 0.06` (the default) is a clean
legato; 0.15–0.4 is a portamento, a slide a singer would make; set it for one note with
`[glide=0.3]` before it. Only single notes stand inside a slur, and of the settings only
`glide` may change there. A slur on a pizzicato, a drum or a pad is an error.

**One track, many strokes.** `[pizzicato] D3 A2 [spiccato f] D3 D3 F3 F3 | [sustain] G3 - - -`
plays three ways of bowing on one cellos track; `[roll pp <] A2 - - - | [hit ff] D2` is a
timpani roll growing into a hit; `[pitch=62] X . [pitch=100] x x` is a big and a smaller taiko
answering on one track.

**Vibrato.** A solo violin with `vibrato: 20, vibrato_delay: 0.4` sings: short notes stay
straight, long ones bloom. `vibrato_speed: 4.5` and a depth of 30 is slow and wide (romantic),
7 Hz nervous. In a section each player keeps its own speed and delay around the setting.

```yaml
# 8 bars, D minor, 80 BPM: a slurred violin line with slides, cellos changing stroke,
# horns swelling, a timpani roll into a hit and a choir growing (an original phrase)
key: D minor
tempo: 80
loop: false
sections:
  - {name: alone, bars: 4, progression: "Dm Bb Gm A"}
  - {name: grow, bars: 4, progression: "Dm Bb Gm A"}
tracks:
  violin:
    instrument: violins
    settings: {players: 1, vibrato: 20, vibrato_delay: 0.4}
    reverb: {size: 2.6, mix: 0.26}
    steps: "[mp <] (A4 - - D5 F5 - E5 - | [glide=0.25] D5 - - - - - [mf >] - -) | (C5 - Bb4 - A4 - G4 - | A4 - - - - - - -) [p]"
  cellos:
    instrument: cellos
    reverb: {size: 2.6, mix: 0.24}
    steps: "[pizzicato mf] D3 . . A2 . . D3 . | Bb2 . . F3 . . Bb2 . | G2 . . D3 . . G2 . | [sustain <] A2 - - - - - - - [f]"
    sections:
      grow: {steps: "[spiccato p <] D3 D3 D3 D3 D3 D3 D3 D3 | Bb2 Bb2 Bb2 Bb2 Bb2 Bb2 Bb2 Bb2 | G2 G2 G2 G2 G2 G2 G2 G2 | [sustain ff] A2 - - - - - - -"}
  horns:
    instrument: horn
    settings: {players: 4}
    only: [grow]
    reverb: {size: 2.8, mix: 0.28}
    steps: "[fp <] D4 - - - - - - - | [mf] (D4 - - F4 - - A4 -) | [fp <] Bb3 - - - - - - - | [f <] (A3 - - C#4 - - E4 -) [ff]"
  choir:
    instrument: choir
    reverb: {size: 4.5, mix: 0.36}
    settings: {vowel: ooh}
    steps: "[pp <] * - - - - - - - | [p >] * - - - - - - - [pp]"
    sections:
      grow: {settings: {vowel: aah}, steps: "[p <] * - - - - - - - | * - - - - - - - | * - - - - - - - | [ff] * - - - - - - -"}
  timpani:
    instrument: timpani
    only: [grow]
    settings: {mallet: 0.2}
    steps: ". | . | [roll pp <] D2 - - - - - - - | [hit ff] A2 . . . . . . ."
```

Things that go wrong:

- *"the hairpin '<' has no end"*: write the level it reaches after it (`[f]`, at the end if
  need be).
- *A crescendo that sounds like a fader*: the instrument has no response to dynamics (an
  organ, a pad, a `soft_lead`), or it was written as a `volume` curve.
- *"a mark changes a setting inside a slur"*: close the slur before the mark; a slur is one
  note.
- *A slide everywhere*: `glide` is set on the track; set it before one note instead
  (`[glide=0.3] E5`).
- *A section's settings vanished*: a section that changes instrument starts from the new
  instrument's own settings.
- *A range warning*: the notes play, but the instrument is not made for them; move the octave
  or give the line to a neighbour (violins to violas, horn to trumpet).
- *A long crescendo over many short drum hits renders slowly*: every whole dB is a new blow (a
  six-player taiko over 64 sixteenths took 5 s instead of 0.3 s).

## 12. Pictures that follow the score

A `web` scene can follow the music without a script that measures it (Step 347; `docs/CONFIG.md`,
"Music data"). The films that asked for it ("Parallel Space", "Escapement") each kept a Python
script that rendered the score, measured the WAV and wrote a JSON file beside the page, run by
hand after every change to the score. Now `music_data: true` hands the page `ctx.music` and the
render keeps it current.

```yaml
music: {source: night_drive, fade_in: 0, fade_out: 1.5}   # a project piece: assets/music/night_drive.yaml
scenes:
  - id: drop
    type: web
    duration: 13.87                       # 8 bars at 138.46 BPM: scenes that start on a bar line
    params:
      script: extensions/space.js
      music_data: {tracks: [kick, taiko, hook, violins]}   # only what the page reads: a smaller page
```

What a page usually takes from it, in song time (`T = ctx.music.now()`):

- **The pulse of a drum**: `ctx.music.pulse("kick", 0.1)` is 1 at each kick (1.5 on an accent,
  more under `[ff]`) and falls in 0.1 s. Brightness and glow follow it well; the camera and the
  zoom should not (the films' owner asked for the brightness to pulse, never the zoom).
- **The tune**: `ctx.music.last("hook")` is the hook's latest note (`pitch`, `time`, `duration`,
  `dynamic`, `stroke`, `slur`); `ctx.music.sounding("violins")` the notes held now. A slurred
  note is a note of its own with `slur: true`, so a picture can move on a slur without a new
  flash.
- **The texture**: `level()`, `low()`, `band(i)` and `onset()` are the measured sound, each 0..1,
  smoothed with a fast rise and a slow fall. Use them for what the score does not say: how dense
  the mix is, how much low end, the reverb tail, a riser.
- **The form**: `ctx.music.section().name` and `ctx.music.score.bar` (seconds per bar) place a
  picture in the piece; the score's `sections` give their song times.

Things that go wrong:

- *Pictures late by a scene's start*: use `ctx.music.now()` or `t0 + t`, not `t`; `t` is the
  scene's own time.
- *A drum track that never pulses*: the name is the score's track name, not the instrument's
  (`taiko`, not `kick`); an unknown name is an error listing the tracks.
- *Pictures that jump at a cut*: two scenes read the same song time at the cut only when the
  second starts where the first ends; `music_data: {t0: ...}` is for a scene that should be
  somewhere else in the song.
- *A slow first render*: the music is measured once (a few seconds); when the score was never
  rendered for the video, it is rendered first (minutes for a long orchestral score), and the
  join then reuses it.

The picture side, three.js pages that look like a film: [COOKBOOK-3D.md, section
8](COOKBOOK-3D.md#8-finishing-threejs-web-scenes) and the module `vidgen/three-finish`; ready-made
reactions to the score (`hitEnvelope`, `noteLevel`, `melody`, `signalLevel` in `vidgen/music-time`)
and light-on-black building blocks (`vidgen/three-kit`): [section
9](COOKBOOK-3D.md#9-building-blocks-for-music-videos) there. A worked
example of both: [examples/signal-fire](../examples/signal-fire/README.md) (each track the page
reads, and what it does with it, is listed at the top of its script). To start a music video from a score
instead of from an empty page: `vidgen music plan assets/music/my_song.yaml --out my_video`
drafts the scenes on the score's bar lines with a colour and a starter page each ([COOKBOOK-3D.md,
section 10](COOKBOOK-3D.md#10-from-a-score-to-a-music-video)); once rendered, `vidgen motion check
my_video` watches it for black frames, flicker and one-frame flashes ([section
11](COOKBOOK-3D.md#11-checking-a-music-video)).

## 13. Every instrument at a glance

All score-file instruments in one table (`vidgen music patches` prints the same with every
setting and its range; `--json` as data). *Written range*: the notes the instrument is made for;
`vidgen music render`, `vidgen music check` and the studio report notes outside it, and still play
them. The older instruments have no written range (nothing is reported): the column gives the
octave their notes sit in by default. Drum instruments (`drum`) play hits, not notes: their pitch is
a setting. ★: a dynamic mark changes the tone as well as the level; ◡: can slur (section 11).

| family | instrument | kind | written range (or default octave) | settings to reach for first | typical use |
|---|---|---|---|---|---|
| drums | `kick` | drum | — | `high`, `low` (Hz of the glide), `decay`, `click` | the beat of electronic beds |
| drums | `clap` | drum | — | `tone` | backbeat |
| drums | `hat`, `open_hat` | drum | — | `decay`, `tone` | eighths and sixteenths, an open hat on the off-beat |
| drums | `gated_snare` | drum | — | `gate`, `body` | an 80s backbeat |
| drums | `snap` | drum | — | `tone`, `decay` | a soft backbeat under a voice |
| drums | `tick` | drum | — | `tone` | clocks, a quiet pulse |
| drums | `boom` | drum | — | `low`, `decay` | a deep hit marking a lift |
| noises | `riser` | drum | — | `low`, `high` | a noise sweep into a section (held steps) |
| noises | `pulsar` | drum | — | `high`, `low`, `sweep`, `noise` | a space-like ticking pulse |
| noises | `static` | drum | — | `low`, `high`, `wander` | radio static held under a passage |
| basses | `synth_bass` | note | octave 2 | `decay`, `tone` | the bass of documentary and pop beds |
| basses | `analog_bass` | note | octave 2 | `tone`, `closed`, `snap`, `detune` | a plucky filtered bass, synthwave |
| basses | `sub` | note | octave 1 | `decay`, `second` | a sub bass under a kick |
| plucks and keys | `pluck`, `fm_pluck`, `square_pluck` | note | octave 4, 4, 5 | `decay`, `tone` (`bright`, `index`) | arpeggios and ostinatos |
| plucks and keys | `pizzicato` | note | octave 4 | `decay`, `tone` | a light plucked line (`cellos` with `stroke: pizzicato` is the orchestral one) |
| plucks and keys | `music_box`, `bell` | note | octave 5 | `decay`, `ring` | lullabies, a bell melody in a lift |
| plucks and keys | `woodblock` | note | octave 5 | `tone` | a pitched tock, cartoons |
| plucks and keys | `piano` | note | octave 4 | `decay`, `ring` | soft chords and melodies |
| leads | `soft_lead` ◡ | note | octave 5 | `attack`, `vibrato`, `vibrato_speed`, `glide`, `tone` | a mellow synth melody |
| brass | `trumpet` ★◡ | note | E3–C6 | `attack`, `brightness`, `vibrato`, `mute`, `players` | a solo line, fanfares |
| brass | `horn` ★◡ | note | B1–F5 | `players: 4`, `attack`, `brightness` | warm held notes, the horn line of film scores |
| brass | `low_brass` ★◡ | note | E1–F4 | `attack` (long: a swell), `brightness`, `tuba`, `players` | low chords, the swell into a hit |
| organ | `organ` | note | C1–C7 | `registration` (`cathedral`, `principal`, `flute`, `reed`, `drawbar`, `full`), `drawbars`, `tone` | chorales, held chords, a pedal |
| strings | `violins` ★◡ | note | G3–C7 | `stroke` (`sustain`, `spiccato`, `tremolo`, `pizzicato`), `players` (1: solo), `attack`, `brightness`, `vibrato` | the melody, high held chords, tremolo beds |
| strings | `violas` ★◡ | note | C3–E6 | as the violins | inner parts, a middle ostinato |
| strings | `cellos` ★◡ | note | C2–A5 | as the violins | tenor melodies, the low spiccato ostinato |
| strings | `double_basses` ★◡ | note | C1–G4 | as the violins | the floor of the orchestra, bowed or plucked |
| percussion | `timpani` ★ | note | D2–A3 | `stroke` (`hit`, `roll`), `mallet`, `ring`, `speed` | roots and fifths under the brass, a roll into the hit |
| percussion | `toms` ★ | note | G1–C5 | `stroke`, `mallet`, `drop`, `shell` | fills from high to low |
| percussion | `taiko` ★ | drum | `pitch` 36–130 Hz | `players` (an ensemble), `mallet`, `pitch` | the big film-score hit |
| percussion | `bass_drum` ★ | drum | `pitch` 26–75 Hz | `mallet`, `decay` | a deep bloom under a hit |
| percussion | `frame_drum` ★ | drum | `pitch` 55–280 Hz | `edge` (middle to rim), `mallet` | hand-drum patterns |
| percussion | `snare_drum` ★ | drum | `pitch` 130–280 Hz | `stroke` (`hit`, `roll`), `players`, `snares` | march figures, a roll into a hit |
| percussion | `cymbal` ★ | drum | `pitch` 0.6–1.6 (size) | `stroke` (`hit`, `swell`), `mallet` | a crash; a swell that ends on the hit |
| percussion | `tam_tam` ★ | drum | `pitch` 0.6–1.8 (size) | `stroke`, `bloom`, `mallet` | the dark gong on a last chord |
| choir | `choir` ★◡ | note | E2–C6 | `vowel` (`ooh`, `aah`, `eeh`, `mm`, `oh`, `ee`), `syllable` (`la`, `na`, `ma`, `da`, `mm-ah`, `ah-oh` ...), `voices`, `singers`, `soloist`, `whisper`, `morph`, `attack` | held vowels, a pad of voices; syllables, a soloist, a whispered texture (no words) |
| pads | `pad`, `supersaw`, `saw_pad`, `glass` | pad | octave 3 (`glass` 5) | `tone`, `attack`, `release`, `detune`, `air`, `sub` | chords (`play: chords`), the bed under everything |

Not in the table: `touch` (on every ★ instrument, 0 by default: how much the old accents `X`,
`o` change the tone) and `glide`, `vibrato_speed`, `vibrato_delay` (on every ◡ instrument).
The choir's written range is the whole choir's; a part for one kind of voice (`voices:
sopranos`) is reported only outside E2–C6, so keep it in that voice's own range yourself
(sopranos about C4–A5, basses E2–C4).
