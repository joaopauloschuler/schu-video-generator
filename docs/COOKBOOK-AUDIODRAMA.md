# Audio drama cookbook: dramatized audiobooks

A dramatized audiobook (a radio play, an "audio movie") is a narrator and voiced characters in
rooms, with ambience, sound cues and a score, delivered as one file per chapter. These notes come
from a 9½-minute, four-chapter drama made with Kokoro voices in an audio-only project (render: a
few seconds; no scene is drawn). Basics of audio-only projects, formats and presets:
[COOKBOOK-AUDIO.md](COOKBOOK-AUDIO.md). The reference: CONFIG "Stereo staging and rooms",
"Sound design", "Music for dramas" and "Delivering an audio drama". Every target below is a
recommendation that worked, not a platform's rule.

## 1. A skeleton

```yaml
title: The Night Ferry
output: night_ferry
audio_only: true
voice: {provider: kokoro, voice: bm_george, label: Tom}     # first person: the narrator is Tom
voices:
  tom: {voice: bm_george, label: Tom}                       # Tom's spoken lines: same voice, in the room
  ada: {voice: af_heart, label: Ada, pan: 0.35}
  radio: {voice: am_echo, label: Radio, effect: [robot, echo]}
narration: {pad: 0.4}
pacing: {speaker: 0.45, scene: 1.6, chapter: 2.2}
audio: {ambience_crossfade: 3, ambience_width: 0.9, music_width: 0.8, sfx_room: true}
audio_output: {format: mp3, loudness: drama, split: chapters}
cold_open: [cabin_radio]                                    # the warning first, then the title
credits: {speak: true, lines: ["Thank you for listening."]}
score:
  themes:
    main: calm                                              # or a project piece: assets/music/main.yaml
    tension: {source: enigma, volume: -2}
    love: {source: lullaby, volume: -3}
  crossfade: 4
  duck: drama
variants:
  full: {audio_output: {format: mp3, loudness: drama, split: none}}   # the whole drama in one file
sections:
  - {id: opening, music: main, beats: ["The Night Ferry. A story in two chapters."]}
  - pause: 3
  - {id: ch1, title: "Chapter One: The Crossing", music: main, beats: ["Chapter one. The crossing."]}
  - pause: 1.5
  - id: deck
    room: outdoors
    music: tension
    ambience: {beds: {rain: 0, city: -8}}
    beats:
      - text: The rain had followed me all the way to the pier.
        actions: [{sfx: step_wood, at: "@pier", repeat: 6, every: 0.45, pan: {from: left, to: centre}}]
      - {text: "You're late. The last ferry waits for no one.", voice: ada}
      - {text: "Then why is it still here?", voice: tom}
  - id: cabin                                               # the voice on the speaker: its own section
    room: phone
    ambience: {beds: {room_tone: 3, hum: -6}}
    beats:
      - {id: cabin_radio, voice: radio, text: "All passengers. Do not open the cargo hold.", pause: 1.0}
  - pause: 2.0
  - {id: ch2, title: "Chapter Two: The Hold", music: main, beats: ["Chapter two. The hold."]}
  - pause: 1.5
  - id: hold
    room: corridor
    music: tension
    ambience: {beds: {room_tone: 3, hum: -4}}
    beats:
      - text: The door to the hold slid open with a hiss.
        sting: {kind: reveal, at: "@hiss", gain: -10}
        actions: [{sfx: swoosh, at: "@slid", params: {pitch: 5}}]
      - {text: "It's empty. It was always empty.", voice: ada, motif: {theme: love, at: end, length: 8}, pause: 2.0}
```

## 2. Structure

Cold open (one or two lines that hook: a threat, a question) → title over the main theme and a
swelling pause → chapters → spoken credits under the main theme. A chapter is a section with a
`title`; its first line says it ("Chapter one. The crossing."), then a `- pause: 1.5` and the
scenes. Chapters of 1½–4 minutes made good files. `cold_open: [beat ids]` copies the lines (with
their section's room, ambience and music) to the very start; `vidgen tts` copies their audio
from the originals instead of voicing them again. A section id moves that whole section.

## 3. Casting and voices

- **Narrator**: the base `voice`. In a first-person story the narrator is the protagonist: give
  the narration and a `voices:` entry the same Kokoro voice and `label`. The narration stays dry
  and centred, his spoken lines sound in the room, and transcripts, credits and the speaker check
  treat them as one person.
- Pick characters that differ from the narrator in pitch and accent; an American female voice
  against a male narrator was ~2 LU louder after levelling (the check allows 4).
- **A machine, a radio, a voice in someone's head**: `effect: [robot, echo]` on the voice, centred,
  in a section of its own with `room: phone` (300–3400 Hz). Measured: 0.06 % of its energy above
  3.5 kHz against 5.9 % for the narrator — unmistakably "not in the room". Cues inside the head
  (an implant's beep, a heartbeat) take `room: none`.
- **Reusing a film's voices**: a beat with the same id, text and voice settings as another
  project's has the same hash; copy its `.mp3`, `.hash` and `.align.json` and `vidgen tts` keeps it
  (the drama reused 51 of 69 lines).

## 4. Narrator balance, rooms and stereo

- Narrator dry and centred (the default with any `room`); characters panned modestly (`0.3`–`0.5`,
  not `far_*`): many listen on one earbud.
- A room per place: an office or lab `small_office` (a soft lab: `{use: small_office, amount:
  1.5}`), a vehicle `car`, a corridor `corridor`, outdoors `outdoors`, a phone line `phone`.
- `music_width: 0.8` and `ambience_width: 0.9` leave the sides to the voices; the mono check stayed
  at correlation 0.81–0.95, fold ≤ 0.4 dB.

## 5. Score

| role | what worked |
|---|---|
| main theme | title, chapter openers, credits (`credits` picks `main` itself); a project piece in `assets/music` gives the drama its own tune (`vidgen music check` it) |
| scene beds | a bed per kind of scene: `enigma` for threat and doors, `neon` for a night ride, a sparse variation of the main theme (`tracks: [pad, glass]`) for wonder |
| motif | one phrase (`section: love, tracks: [keys, pad]`) on two or three words only: the first touch, the kiss, after the last line (`at: end`) |
| stings | one or two reveals, `gain: -8` to `-10`; the reveal sting is bright, so not on dark news |

Music helps in openers, pauses and scene changes (`duck: drama` swells it 3 dB in every pause)
and hurts under fast dialogue. Measured: 23 LU under the dialogue, 10 LU under the voices' level
in pauses; dense dialogue 20.7 LU at worst (the check wants ≥ 15). Themes are sticky: a section
without `music` keeps the theme, so name it only where it should change.

## 6. Sound design and ambience

- Beds per section: `{beds: {room_tone: 3, hum: -4, rain: -16}}` (rain through the walls at
  −16 to −22 dB); repeat the same beds on the next section and they play on without a dip.
- Cues on words, `sfx_room: true` puts them in the room: footsteps `repeat` / `every` with `pan:
  {from, to}`, a door `swoosh` (`pitch: 5`: a hiss), a scanner `riser`, a shimmer `drone`, a surge
  `crackle`, a heartbeat `thud` ×3. Levels −6 to −15 dB; quiet is plenty under a voice.
- Leaving a room: `pause: 2.5` on the line and steps at `"@word+0.9s"`, so they fill the pause.
- Word anchors are exact: every cue's onset measured within 0.1 ms of its word.

## 7. Pacing and pauses

`speaker: 0.45`, `scene: 1.6`, `chapter: 2.2`; a beat's `pause: 1`–`2` after a reveal, a question
or a kiss; `- pause: 1.5`–`3` sections where the theme should swell. A dense exchange (speech in
≥ 80 % of 5 s) is where the music check looks.

## 8. Loudness and checks

`audio_output.loudness: drama` (podcast loudness: −16 LUFS stereo / −19 mono ±1 LU, true peak ≤
−1 dBTP, the voice leveller on). The render and `vidgen audio check PROJECT --preset drama`
measure each file:

| item | recommended |
|---|---|
| loudness range | ≤ 10 LU |
| dialogue lines | each line's loudness within 6 LU (10th–90th percentile) |
| voices | each speaker's level within 4 LU of the others |
| music under dialogue | `under_dialogue_lu` and the worst dense run ≥ `score.dense_lu` (15) LU |
| files | loudness within 1 LU, median line within 2 LU |

Measured on the drama: −16.3 LUFS per file, true peak −2.0 dBTP, LRA 3.6–5.4 LU, lines 1.6–2.9 LU,
voices 1.6–2.4 LU, files 0.0 / 0.9 LU. A failing voice or line: raise its `emotion` gain or
re-voice it; failing music: `duck: deep` or a lower theme `volume`.

## 9. Delivery per chapter

`split: chapters` writes, next to the playlist:

```
output/<output>.m3u
output/<output>_01_<chapter_one>.mp3   (+ _transcript.txt, .srt, .vtt)
output/<output>_02_<chapter_two>.mp3   ...
```

Each file is normalised on its own, starts `pacing.lead_in` before its first line with a 0.3 s
fade and ends with a fade of up to 2 s; the cold open and the title are in the first file, the
credits in the last (`credits: {chapter: Credits}` gives them a file). A `full` variant with
`split: none` gives the single file (and `_chapters.txt`).
