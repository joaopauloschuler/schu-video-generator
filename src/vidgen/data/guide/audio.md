<!-- topic: audio (also: sound, sfx, music, voice, voices, pronunciation, readback) -->
## Sound: voices, pronunciation, effects and music

**Voice.** One narrator (`voice: {voice_id: ...}`) for explainers. `voices:` plus a scene's or
beat's `voice:` for interviews and dialogue; label speakers (`label`) so subtitles and captions
can name them (`subtitles: {speakers: name}`).

**Choosing a voice provider.** ElevenLabs, the default provider (key `ELEVENLABS_API_KEY`), sounds the most
natural, sends the neighbouring beats for smooth intonation and can time every word exactly
(`timestamps: true`, for karaoke captions); it bills characters against a monthly plan. `voice:
{provider: openrouter, model: author/name, voice: ...}` (`OPENROUTER_API_KEY`) reaches many TTS
models with one pay-as-you-go key, most of them far cheaper per character (e.g.
`hexgrad/kokoro-82m`, `mistralai/voxtral-mini-tts-2603`), but with no context between beats, no
word timings (captions use estimates) and no `language_code`: the language follows the text and
the voice. Read `vidgen tts --dry-run`: it names provider, model and voice, prints the price per
character and the estimated cost (or why it is unknown) and `note:` / `problem:` lines — fix them
before a real run. Then listen to one beat (`vidgen tts --beat ID`, `vidgen readback`) before
voicing the whole video. One provider per video: named `voices:` change `voice` / `instructions`
/ `speed`, not `provider`; try another provider in a variant (it gets its own `audio/<variant>/`).
If the account requires Zero Data Retention, pick a model with a ZDR endpoint (most TTS models
have one; schu-video-generator's error lists them when a model is refused). A real run ends with what
OpenRouter charged, or `cost not reported by openrouter yet (...)` when its cost records lag:
the audio is stored all the same.

**A free local voice: Kokoro.** `voice: {provider: kokoro, voice: af_heart}` runs the open
Kokoro-82M model on the computer itself: no key, no account, nothing to pay, offline after a
one-time download (~330 MB from Hugging Face; `vidgen tts --dry-run` says when it is still to
come). It comes with a plain install on Python 3.10-3.12 (Kokoro has no Python 3.13 release;
there `vidgen tts` says so). This is the voice for your own
projects: re-voicing after every script change costs nothing, and over MCP a real `tts` run needs
no `confirm_cost`. English is its strength (`af_heart` and `af_bella` are the best voices, then
`bf_emma` for British English; males: `am_michael`, `am_fenrir`, `bm_george`), and English beats
get exact word timings for karaoke captions for free. It also speaks Spanish, French, Hindi,
Italian, Brazilian Portuguese (`pf_dora`), Japanese and Mandarin, less well. `lang` follows the
voice's first letter (`p` for `pf_dora`) or the video's `language:`; `vidgen validate` warns about
an unknown voice or one of another language. Compared with ElevenLabs it is flatter and less
expressive, has no context between beats, and is weak on very short lines (give a beat at least
~8 words) — good for drafts, internal videos and your own experiments; suggest ElevenLabs when
the person wants the most natural narration. It runs at about real time on a laptop CPU (~0.7x on
a small cloud CPU): voice a long video once the script is settled.

Give Kokoro lines feeling with `emotion:` on a beat (or as a speaker's default on its voice):
`happy`, `excited`, `sad`, `angry`, `worried`, `scared`, `surprised`, `calm`, `doubtful`,
`sleepy`, `whisper`, `shout`, or a row with changes such as `{like: sad, pitch: -2}`, change the
speed, pitch, loudness and pauses of that line; use it on the lines of a dialogue that carry a feeling, not on every line.
`excited`, `happy`, `angry` and `shout` also speed a line up: with Kokoro keep the voice's `speed` near
0.75–0.8 (`af_heart` at 0.95 read 3.6–4.6 words a second), then check `narration_speed` with
`vidgen lint` on the real audio. A screenplay's `PIP (cross):` sets it for you. A weighted blend `voice: af_heart+af_bella:0.6`
makes an in-between voice. ElevenLabs and OpenRouter speak the same `emotion` by its name: an
audio tag such as `[excited]` before the line on `eleven_v3`, changed voice settings on other
ElevenLabs models, a sentence added to the `instructions` of OpenRouter models that take them
(other OpenRouter models: the audio's speed, pitch and loudness).

```yaml
voice: {provider: kokoro, voice: af_heart}       # speed: 1.0, lang: a, device: cpu (defaults)
voices:
  guest: {voice: am_michael, label: Guest}         # same provider; another voice
```

**Voice effects.** A speaker who is not an ordinary person gets an `effect:` on its voice, for
any provider: `robot` is a flat, metallic monotone (`{use: robot, pitch: -6}` lowers its buzz);
`otherworldly` is deep, many-voiced and in a hall (aliens, spirits, giants); `echo` is a
loudspeaker in a room (a ship's computer); `radio` a phone or a walkie-talkie; also `hall`,
`chorus`, `deep`, `high`, or a list. Pick a distinct base voice too (a deep `am_onyx` under
`otherworldly`), and keep the narrator plain. `echo`, `hall` and `chorus` add a short tail after
the line.

```yaml
voice: {provider: kokoro, voice: bm_fable}         # the narrator, plain
voices:
  ship: {voice: af_nicole, label: Ship, effect: echo}
  stranger: {voice: am_onyx, label: Stranger, effect: otherworldly}
  gate_bot: {voice: am_echo, label: Gate, effect: {use: robot, pitch: -6}}
```

**Writing good `instructions`** (OpenRouter models that read them, e.g. Gemini TTS: the dry run
notes when a model ignores them). Describe the speaker and the delivery in a few words, not the
content: who (a warm, unhurried explainer; a curious guest), pace and pauses (slight pause before
numbers; slow down on definitions), energy (calm, never salesy), and the language or accent when
it matters (Brazilian Portuguese, neutral accent). Keep one `instructions` for the narrator so
every beat sounds alike; give each named voice its own. Never put directions into the beat text:
the model reads it aloud.

```yaml
voice:
  provider: openrouter
  model: google/gemini-3.8-flash-lite-tts
  voice: Kore
  instructions: "warm, unhurried explainer; slight pause before numbers"
voices:
  guest: {voice: Puck, instructions: "curious guest, a little faster, rising tone on questions", label: Guest}
```

**Pronunciation.** Write the text as it should be **read** on screen and in subtitles; fix
how it is **said** with `pronunciation:` (applied to the TTS text only). Run
`vidgen tts --dry-run` and read every `says:` line; after `vidgen tts`, `vidgen readback` finds
what the voice still gets wrong, and the words it says unclearly (`unclear`: probability below
0.5 or a pause over 0.5 s inside a sentence; `doubtful`: below 0.75). For an unclear name or
term, respell it in `pronunciation:`; for another word, try another voice, speed or `emotion:`.
schu-video-generator already respells some words for some voices (built-in lists, e.g. Kokoro's American
voices say `epoch` as `E pock`, `README` as `readme`, `JSON` as `Jason`): `vidgen list-pronunciation`
shows them; `vidgen validate` prints the beats they change (`pronounce: ...`). Your entry for the
same term wins, `term: null` drops one, `pronunciation_defaults: false` turns them off.

```yaml
pronunciation:
  K-Phi-3: kay fye three
  SQL: {say: sequel, case_sensitive: false}
scenes:
  - id: intro
    type: title
    params: {title: "K-Phi-3 and SQL"}
    beats: [{text: "K-Phi-3 writes SQL for you."}]
```

**Sound effects** (`vidgen list-sfx` describes each in words): `whoosh` (something moves in),
`pop` (an item appears), `tick` (steps, counting), `click` (a UI click), `chime` (a key
insight), `success` / `error` (a result), `riser` (tension before a reveal, `align: end`),
`thud` (a big number lands), `swoosh`, `typing`; `footstep`, `step_grass`, `step_gravel`, `step_wood`, `step_stone`, `boing`, `gasp`, `sigh`, `beep`, `bell`, `engine`, `brakes`, `burner`, `launch`, `phone`, `thunder`, `creak`, `knock`, `unlock`, `coin`, `twinkle`, `splash`; for a lab or another world
`alarm` (a two-tone siren), `crackle` (sparks, crackling energy), `hum` (a machine powering up),
`drone` (a crystalline singing drone: awe, another world), `slam` (a steel shutter); and the music stings
`sting_reveal` / `sting_comic` / `sting_sad` are for cartoons (`vidgen guide cartoons`). Two or three per minute, on the moments that
matter; `sfx: {auto: true}` adds soft ones to built-in reveals if you want a uniform feel.

```yaml
sfx: {gain: -3}
scenes:
  - id: reveal
    type: stat
    params: {value: 9.8, unit: "min", label: "for one minute of 4K"}
    beats:
      - text: "One minute of four K took almost ten minutes."
        actions:
          - {sfx: thud, at: 0.2}
```

**Music** (`vidgen list-music`): `calm` (serious, long narration), `pulse` (tech, data,
walkthroughs), `bright` (launches, upbeat social), `cartoon` (playful pizzicato: cartoons,
comic scenes), `lullaby` (music box: bedtime stories, soft endings). It is ducked under the
voice automatically and the mix is normalised to −16 LUFS. Leave the defaults; turn it off over
clips with their own sound (`music: false` on the scene).

Five documentary beds add a soft kick and a synth bass under the chords. **For presentations and
documentaries, suggest `momentum` first** (`music: {source: momentum, volume: -2}`); the others
are alternatives when the tone asks for them. Choosing one: `momentum` (the most energetic of the five:
presentations, documentaries, fast explainers, Shorts, montages), `discovery` (a steady approach
that builds: documentaries closing in on a finding, science stories), `breakthrough` (tension,
then a reveal: good when the reveal lands mid-video; its loop lifts from C minor to E-flat major
25.7 s in, so with the reveal T seconds after the music starts (T under 25.7), `start: 25.7 − T`
puts the lift on it), `enigma` (dark and mysterious: open questions, investigations, history),
`lab` (modern tech: AI, software, engineering). They are bass-heavy (57–67 % of their power under
150 Hz), so they sound lighter on phone and laptop speakers than on headphones.

Four energetic electronic beds are further alternatives (still suggest `momentum` first):
`ascent` (uplifting trance, 136 BPM, builds and lifts: energetic reveals, tech launches, montages,
uplifting endings; the lift lands 28.2 s into its loop, so `start: 28.2 − T` puts it T seconds
after the music starts), `horizon` (anthemic trance with a gated supersaw, 132 BPM: the same uses,
lifting to F major 29.1 s in), `beacon` (a pulsar-like ticking beacon, 120 BPM: space, astronomy,
science, signals, data), `neon` (synthwave night drive, 116 BPM: tech at night, retro-futurism,
cities, coding Shorts). They are even more bass-heavy (71–78 % under 150 Hz): listen on a phone too.

Three beds written in the score format are alternatives too (still suggest `momentum` first):
`tidewater` (steady and hopeful, 108 BPM, a bell melody in its lift 26.7 s in: nature, the sea,
travel, progress stories, calm walkthroughs; 39 % under 150 Hz, lighter than the documentary
beds), `skyline` (a pumping supersaw build and lift, 128 BPM, the lift 30 s in: energetic
reveals, launches, montages; 63 % under 150 Hz) and `time_of_flight` (curious, B minor, 108 BPM,
intro / build / lift / settle, a soft lead in its lift 26.7 s in: science and tech explainers,
discovery and measurement stories, maps and navigation; 54 % under 150 Hz). `vidgen music
template tidewater` gives the very score a bed plays, to start a piece of your own from.

```yaml
music: {source: calm, volume: -2}
scenes:
  - id: intro
    type: text_card
    params: {text: "Listen"}
    beats: [{text: "A calm bed sits under the voice."}]
```

**Composed music** (`music: {compose: MOOD}`) is written as notes for this video and played with
real instruments: an original piece in a mood, the same piece for the same settings. Prefer it to
a bed when the music should follow the video. Moods for explainers: `calm` (piano and harp, no
drums: serious topics, long narration), `focused` (vibraphone, guitar, brushes: tech, data,
walkthroughs), `curious` (staccato flute, harp: science, "how does it work"), `upbeat` (marimba,
pop drums: launches, tutorials). For cartoons: `playful` (clarinet, marimba, tuba oom-pah),
`sleepy` (celesta lullaby in 3/4: night, bedtime, endings), `tense` (low clarinet, tremolo
strings, a heartbeat drum: storms, chases, suspense), `triumphant` (trumpet fanfare, march: the
win). `vidgen list-music` describes each mood and instrument in words.
- **It follows the video.** Without `bars` the piece is composed for the real timings when the
  video is joined: every scene starts on a bar line (tempo within 8 % of the mood's), the music
  swells a little when a bullet, chart bar or code step appears, and it ends on a held chord
  instead of fading mid-phrase. After a script change the next render composes it again.
- **A mood per scene.** `music: {mood: tense}` on a scene changes the music for that scene only
  (the next scene returns to the cue's mood); add `volume: -3` under rain or a busy scene. Use it
  where the story turns (calm → tense at the storm, sleepy at night), not on every scene.
- **Pauses before punchlines.** `music_pause: true` on a beat stops the music just before the
  line, until the next bar line after it; schu-video-generator does this by itself before a `card` scene and
  before a short last line (≤ 8 words), whose closing chord then lands as the line ends.
  `music_pause: false` turns either off.
- **Stings** (`sting: reveal | comic | sad`) are played by the music's own instruments, in its key.
- **Without symusic.** symusic comes with a plain install; the first
  render downloads the SoundFont (32 MB, once; `vidgen soundfont fetch` does it now). Without
  symusic `vidgen validate` warns and the mood's built-in bed plays instead (`calm` → calm,
  `focused` / `tense` → pulse, `curious` / `upbeat` / `triumphant` → bright, `playful` → cartoon,
  `sleepy` → lullaby), so the video still renders. `vidgen music preview --mood M` writes a piece
  as WAV and MIDI to listen to (MCP `music_preview`). Drafts and animatics play it too; storyboards
  have no sound.

```yaml
music: {compose: playful, volume: -2}
scenes:
  - id: storm
    type: stage
    music: {mood: tense, volume: -3}
    beats:
      - text: "Then the cloud did what clouds do."
      - text: "The umbrella left without him."
        music_pause: true
```

**Making music** (a project piece: a score file, no Python, no extra). Music written in YAML —
key, tempo, sections, chords, tracks of step patterns — lives in `assets/music/NAME.yaml` and
plays like a bed: `music: NAME`, `{source: NAME, volume: -2}`, in a cue list with `from` / `to`,
`music: false` on a scene. It is rendered when the video is joined (kept in `build/music`, made
again only when the file changes). You cannot hear it, so work from measurements:
1. **Start from a template**, not from nothing: `vidgen music template momentum --out
   assets/music/my_theme.yaml` (for documentaries keep `momentum` the first suggestion; `vidgen
   music template` lists all 17). Give it a `title:` and a `description:` (list-music shows them).
   A template writes its chords out (`{chord, notes, bass}` in the bed's key): to change the key,
   replace the whole `progression:` with Roman numerals (`"i v VImaj7 iv9"`) in the same step.
2. **Change one thing at a time** — the key and chords, the sections, one track's steps, an
   instrument or a setting (`vidgen music patches` describes every instrument and effect) — and
   keep each version (copy the file to `my_theme_v1.yaml`, `_v2`... outside `assets/music`, or
   under another name, before each change). Name sections `intro`, `build`, `lift`, `settle`:
   the check judges whether a `build` rises through its second half and whether a `lift` is
   louder or brighter than the section before; other names are not judged.
3. **Check after every change and compare** with the version before: `vidgen music check
   assets/music/my_theme.yaml --compare my_theme_v1.yaml --out build/music-check` (MCP
   `music_check` with `compare`; without `--out` the pictures and demos land in the current
   folder). Read the verdict and the fixes: they name the score keys to change. In the tracks
   table a part under about 1 % of the whole is barely there: raise it 4–8 dB. Look at the
   spectrogram PNG: sections where you meant them, nothing loud between the two blue lines (the
   voice's 300 Hz–3 kHz), no red bars in the lane under it. Compare the last version with the
   template too: the piece should be clearly your own.
4. **Keep room for the voice**: the melody sparse or out of the voice's core, pads soft there, no
   bright highs; the check's demo MP3 plays the piece under a narration sample. Craft notes and
   genre sketches (documentary, trance, synthwave, cosmic, cartoon): `docs/COOKBOOK-MUSIC.md`; a
   worked example with its log: `examples/gps-time-of-flight` (its piece is now the bed
   `time_of_flight`).
   **Orchestral colours**: `trumpet`, `horn`, `low_brass` and `organ` are synthesised
   instruments like the others (no samples); `low_brass` is a trombone section, and its `tuba`
   setting adds a tuba underneath. Hold notes with `-`, as in `"A4 - - - . ."`. On brass two
   settings shape the note: `brightness`, from 0 (soft and dark) to 1 (blaring), and `attack`
   in seconds: 0.02 is tongued, 0.3 soft, 1 to 4 a swell that opens; `players: 4` makes a
   section. The organ takes `registration: cathedral | principal | flute | reed | drawbar | full`
   or your own `drawbars: "00 8400 000"` (in quotes) and wants a long `reverb`. Under a voice
   keep brass soft, with `brightness` up to 0.4, and prefer the horn. Recipes:
   `docs/COOKBOOK-MUSIC.md`, section 8.
   **Bowed strings**: `violins`, `violas`, `cellos` and `double_basses` are sections (`players: 1`
   makes a solo instrument). The setting `stroke` picks how they play. `stroke: sustain` bows
   a note while its steps hold it; write a phrase without rests and the notes join.
   `stroke: spiccato` plays one short stroke per note: use it for ostinatos in sixteenths, every
   stroke is the same and equally loud (do not play a `pad` note by note for that, its level
   changes from note to note). `stroke: tremolo` is a held note of fast strokes: with
   `brightness: 0.8` and a rising `volume` curve a tension bed. `stroke: pizzicato` plucks; the
   note rings until its steps end. `brightness`
   0 is dark (over the fingerboard), 1 glassy (at the bridge); `mute: 1` veils; `attack` 0.5 and
   more is a swell. A section of the piece can change the stroke:
   `sections: {drop: {settings: {stroke: spiccato}}}`. Recipes: `docs/COOKBOOK-MUSIC.md`,
   section 9.
   **Orchestral percussion**: `timpani` and `toms` are written as notes (`"D2 . . . A2 . . ."`;
   timpani D2–A3, toms from a floor tom G1 to a high tom C5), the big drums as drum steps:
   `taiko`, `bass_drum`, `frame_drum`, `snare_drum`, and the metal `cymbal` and `tam_tam`.
   `players: 6` on the `taiko` in a hall is the wall of drums of film scores. `mallet`, from 0
   (soft) to 1 (hard), sets the brightness of a blow; `pitch` in Hz tunes a big drum. `stroke: roll` (timpani,
   toms, snare drum) rolls for the held steps; a roll growing into a hit is one track:
   `"[roll pp <] A2 - - - - - - - | [hit ff] D2 . . ."` (see **Expression**). `stroke: swell` on `cymbal` or `tam_tam` grows by itself
   until its held steps end: end it on the hit. Do not build drums from the `kick` any more:
   it is one sine and stops at 160 Hz.
   **Choir**: `choir` holds a vowel (`vowel: ooh | aah | eeh | mm | oh | ee`) or sings
   syllables; it sings no words. `voices: mixed` gives each note to the kinds of voice that
   reach it; `men`, `women`, `basses`, `tenors`, `altos`, `sopranos` choose. Hold chords
   (`"* | - | - | -"`), give it a hall, and use `attack: 1` or more for a swell;
   `{vowel: mm, morph: aah}` opens a held note from a hum. `syllable: la` (or per note `[la]`,
   `[na]`, `[ma]`, `[da]`, `[loo]`, `[mm-ah]`, `[ah-oh]`, `[oo-ah]` ...) starts each note with a
   soft consonant or glides between two vowels at `turn`; in a slur only the first note gets
   the consonant unless a note's own mark names one. `soloist: true` is one solo voice
   (brighter, a wider and later vibrato, a scoop into each note): give it its own track over a
   choir track. `whisper` from 0 to 1 turns the tone into breath. Recipes:
   `docs/COOKBOOK-MUSIC.md`, section 10.
   **Expression**: marks in square brackets stand before a step in a track's `steps` and last
   until changed. Dynamics `[pp] [p] [mp] [mf] [f] [ff]` (or dB: `[-6]`; an unmarked note is
   `mf`) change the level and, on brass, strings, choir and the orchestral drums, the tone:
   louder is brighter and bites harder (the organ and the older instruments change level only).
   A hairpin `[p <] ... [f]` or `[f >] ... [p]` moves the level from its step to the next
   dynamic: over a held note it is a crescendo inside the note, over many notes a phrase
   growing; a swell is `"[p <] A3 - - - [f >] - - - [p] ."`. `[fp]` starts loud and drops,
   `[sfz]` stabs one note. A setting changes per note: `[pizzicato] D3 A2 [spiccato] D3 D3
   [sustain] G3 - - -` on one cellos track, `[pitch=100] x` on a taiko, `[vibrato=0]`,
   `[default]` back to the track's settings. Parentheses slur: `"(A4 - C5 - E5 - - -)"` is one
   bow or breath whose pitch moves (brass, strings sustained or tremolo, choir, `soft_lead`);
   `glide` sets the slide in seconds (0.06 clean, 0.2–0.4 a portamento, `[glide=0.3]` before one
   note). `vibrato_speed` in Hz and `vibrato_delay` in seconds join `vibrato` on those instruments.
   A section may play another instrument on the same track:
   `sections: {lift: {instrument: trumpet}}`. A score without marks sounds exactly as before.
   Notes outside an instrument's written range are reported by `vidgen music check` and
   `render`. Recipes: `docs/COOKBOOK-MUSIC.md`, section 11; every instrument with its range
   and main settings in one table: section 13; a cue using all of this: `examples/signal-fire`.
5. **Use it** (`music: my_theme`), run `vidgen validate` (it reads the score) and `vidgen lint`
   (its `music_check` rule repeats the voice-range, highs, bass, steadiness, peaks and seam checks
   on the part of the piece the video plays). A piece keeps its own pace; to make its lift begin
   with a scene, split it into two cues and start the second at the section:
   `[{source: my_theme, to: setup, fade_out: 0.5}, {source: my_theme, from: results, section: lift, fade_in: 0.3}]`.
6. **Let a human choose**: offer the demo MP3s or `vidgen music render ... --out x.mp3` of two
   versions and a bed; the numbers say whether it fits under a voice, not whether it is good.
   (Both commands also take names: `vidgen music check my_theme --compare momentum` in the
   project's folder.)

**Suggest the studio to a person** who wants to shape the music by ear, says "the music is not
quite right" without saying how, or wants to choose between versions: `vidgen studio` (in the
project folder; it runs on their computer, 127.0.0.1 only, and opens their browser — you cannot
use it yourself) loads any bed as an editable score, plays it under a narration sample, A/Bs
versions, makes four variations at a click and saves into `assets/music/`. Tell them to press
**N** to pin a note where something bothers them and then **Ask an agent**: the session is then
handed to you through MCP (below), and you answer with a version they A/B. People may also hand
you a session unprompted ("answer my studio notes"): start with `studio_sessions`.

**Answering a studio hand-off.** A person shaping a piece in `vidgen studio` pins listening notes
on its timeline ("this part drags", bar 12, beat 3, in the build) and presses *Ask an agent*.
Through MCP: `studio_sessions` lists them (the session open in a running studio first, with its open
notes) → `studio_read` gives the score of the version handed off, the notes with bar, beat and section,
its check report and what changed from its parent → change the score: **one focused change per note**
when you can, in the section and bar the note names, everything else kept, comments too (a note
that says "love this" asks you to keep that part) → `studio_check` with your new score (do not make
the check worse) → `studio_propose` with the whole score, `explanations: {n1: "what I changed and
why", ...}` (one line per note, also when you changed nothing for it) and a short `summary`. The
proposal is validated (a score with problems comes back with them: fix and propose again) and
appears in the studio as a new version the person A/Bs and keeps or discards; it never replaces a
version. `studio_variations` gives four variations of a version (another voicing, an altered
figure, a darker or brighter mix, another arrangement) as whole scores with a label: a starting
point when a note asks for "something different". Without MCP the person copies the same hand-off as a prompt: answer with
`summary: ...`, the whole score in one ```yaml block, then one `n1: ...` line per note.

Write original music: genre styles are fine, never a known tune. A piece named like a built-in bed
is a problem (rename it, or use `source: assets/music/NAME.yaml`). `loop: false` pieces play once
with their ending (the cue's fade-out still applies).

