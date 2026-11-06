# Audio cookbook: audiobooks and podcasts

Settings that worked for audio without pictures: an audiobook of a short story, a podcast-style
episode, and the soundtrack of an existing video. The reference is in
[CONFIG.md](CONFIG.md#audio-only-audio_only-sections-pacing) (`audio_only`, `sections`, `pacing`)
and [CONFIG.md](CONFIG.md#audio-files-audio_output-loudness-presets-transcripts) (`audio_output`,
presets, `vidgen audio check`). An audio-only render takes seconds: no scene is drawn.

## 1. Two starting points

An audiobook for ACX / Audible-style stores (mono MP3, 44.1 kHz, 192 kb/s, no music):

```yaml
title: The Lantern Shop
output: lantern
audio_only: true
voice: {provider: kokoro, voice: bf_emma, speed: 0.85}
voices:
  ada: {voice: af_heart, label: Ada}
  pell: {voice: bm_fable, label: Mr Pell}
narration: {pad: 0.4}
pacing: {speaker: 0.6, scene: 1.5, chapter: 2.5}
audio_output: {format: mp3, sample_rate: 44100, bitrate: 192k, channels: mono, loudness: audiobook}
sections:
  - id: evening
    title: Evening
    beats:
      - It was evening when Ada opened the door of the lantern shop.
      - {text: "We are closing.", voice: pell}
      - {text: "I only need one lantern.", voice: ada}
```

A podcast episode (stereo MP3 at −16 LUFS, a quiet bed under the voices):

```yaml
title: Saving 77% of the Parameters
output: episode
audio_only: true
voice: {provider: kokoro, voice: am_michael}
music: {source: calm, volume: -3}
audio_output: {format: mp3, loudness: podcast}
sections:
  - id: intro
    title: Why it matters
    beats:
      - Large language models carry far more parameters than they use.
```

Any video project becomes an episode with `vidgen render --audio-only` and a variant that sets
`audio_output` (and `pacing: {timing: video}` to keep the video's own timeline).

## 2. Loudness targets

| preset | target | where |
|---|---|---|
| `podcast` | −16 LUFS stereo, −19 LUFS mono (±1 LU), true peak ≤ −1 dBTP | Apple Podcasts, Spotify, most hosts |
| `audiobook` | RMS −23 to −18 dB, peaks ≤ −3 dB, noise floor ≤ −60 dB, room tone 0.5–1 s at the head and 1–5 s at the tail | ACX (Audible); a file per chapter, at most 120 minutes |
| `broadcast` | −23 LUFS (±0.5 LU), true peak ≤ −1 dBTP | EBU R128 radio / TV |
| `custom` | `audio.target_lufs` ±1 LU, `audio.true_peak` | anything else (YouTube −14, a −18 house standard) |

- Mono is −19, not −16: a mono file plays on both speakers, so it sounds as loud as a −16 stereo
  file. With a preset the mix is made for the file's channels, so the file measures the target.
- ACX measures RMS over the whole file, pauses included, so a talky chapter with long pauses gets
  raised more. The audiobook preset aims at −20 dB, the middle of the range.
- Raising speech to these levels makes its peaks hit the limiter (ElevenLabs narration at −16
  LUFS: up to 5 dB). The `podcast` and `audiobook` presets turn on `audio.level_voice`, a gentle
  3:1 leveller on the loudest syllables only: the limiter then works ≤ 1 dB on that narration and
  the waveform is otherwise unchanged. `audio: {level_voice: false}` turns it off.
- MP3 at 192 kb/s comes out about 0.3 dB quieter than the mix; inside every tolerance.

## 3. Pacing

- **Audiobook**: slower voices (`speed: 0.85`–`0.9` with Kokoro), `pad: 0.4`, `speaker: 0.6`,
  `scene: 1.5`, `chapter: 2.5`. A beat's `pause: 1.5` (or a `- pause: 1.5` item) for a beat of
  silence after a dramatic line; a `- pause: 3` section between parts.
- **Podcast**: normal speed, `speaker: 0.5`–`0.7`; music `volume: -3` or lower, ducked under the
  voices by itself; a sting (`sting: reveal`) at a turn in the story, sparingly.
- **Room tone**: the audiobook preset makes `lead_in: 0.6` and `tail: 2.5` unless `pacing` says
  otherwise. ACX counts the head to the first *sound*: an effect at `at: 0.2` in the first section
  fails it (the check says `head 0.20 s`), so start effects after half a second.
  `audio_output: {room_tone: -72}` puts a faint steady noise under the whole file if a store
  rejects digital silence.

## 4. Voices

- One narrator plus one voice per character; give each a `label`: the transcript writes
  `Ada: ...`, and with `subtitles: {speakers: name}` the SRT / WebVTT too. The base voice without a
  label is `Narrator`.
- Pick voices that differ in pitch and accent (Kokoro: `bf_emma` narrator, `af_heart` a girl,
  `bm_fable` / `bm_george` older men); `emotion:` on a line where the reading should change.
- `vidgen story draft --audio story.md` drafts the sections, speakers and emotions from prose.
- Drama: place the characters with `pan: left` / `right` (`voices:`), keep the narrator centred
  and dry, and give each section a `room:` (`small_office`, `corridor`, `hall`, `outdoors`, `car`,
  `phone`); a line can walk: `pan: {from: right, to: left}`. `audio.music_width: 0.7` leaves the
  sides to the voices. An audiobook for ACX is better without rooms on the narration (the default)
  and with modest pans (`left` / `right`, not `far_*`): many listen on one earbud. See
  [CONFIG: Stereo staging and rooms](CONFIG.md#stereo-staging-and-rooms-pan-room).

## 5. Checking without listening

`vidgen render` measures the file after encoding and prints `check: audiobook PASS ...` or the
values that miss. `vidgen audio check FILE` measures any audio file against every preset (exit
code 1 when `--preset` fails); `--json` for scripts. Look at what it names: loudness, true and
sample peak, RMS, noise floor, head and tail. A stereo file also gets a `mono` line (channel
correlation, the worst second, how much the mono fold loses); `--mono` makes it count.

| format | when |
|---|---|
| `mp3` | audiobooks (ACX wants 192 kb/s, 44.1 kHz), podcasts |
| `m4a` | Apple-first podcasts; smaller at the same quality |
| `ogg` | Opus: the smallest; web players, voice notes (48 / 24 / 16 kHz only) |
| `wav` | masters and further editing (`bit_depth: 24`) |

The transcripts come with every render: `<output>_transcript.txt` (title, `[M:SS]` chapter
headings, a paragraph per speaker's turn: show notes and accessibility), `.srt` and `.vtt`
(captions for a podcast player or a video upload), `<output>_chapters.txt` (timestamps for the
show notes).
