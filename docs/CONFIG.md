# schu-video-generator config reference

This is the reference of every key. How to make a *good* video with them (the working loop,
pacing, which scene type, good vs bad examples) is the author guide: [AGENTS.md](../AGENTS.md),
also `vidgen guide`.

A project is a folder with one config file: `video.yaml` (or `video.yml` / `video.json`), UTF-8.
Unknown keys are an error everywhere except inside `params`, `theme.colors`, `theme.sizes` and
the bodies of `variants`, so typos are caught by `vidgen validate`. Paths are relative to the
project folder. Contents: [top level](#top-level), [scenes and beats](#scenes-and-beats),
[format](#format-and-preview), [variants](#variants), [theme](#theme), [voice](#voice-voice),
[narration](#narration-narration), [narration audio](#narration-audio-elevenlabs),
[multiple voices](#multiple-voices-voices), [characters](#characters-characters), [pronunciation](#pronunciation-pronunciation),
[readback (speech to text)](#readback-vidgen-readback),
[generated images](#generated-images-imagegen-vidgen-imagegen),
[languages and translations](#languages-and-translations),
[sound effects](#sound-effects-sfx), [background music and loudness](#background-music-music),
[transitions](#transitions-transition), [thumbnail](#thumbnail-thumbnail-vidgen-thumbnail),
[GIF and clip export](#export-gif-and-clip-vidgen-export), [built-in scene types](#built-in-scenes), [beat actions](#beat-actions), [overlays](#overlays),
[JSON Schema](#json-schema-vidgen-schema), [frame stills](#frame-stills-vidgen-render---frames),
[storyboard](#storyboard-vidgen-storyboard), [lint](#lint-vidgen-lint),
[drafting from an outline](#drafting-from-an-outline-vidgen-plan),
[JSON output of commands](#json-output---json).

## Top level

| key | default | |
|---|---|---|
| `title` | required | the video's title (the MP4's title tag and `timings.json`; not drawn by itself) |
| `output` | folder name | base name of the output files: `<output>.mp4`, `<output>.srt`, `<output>_chapters.txt`, `<output>_thumbnail.png`, `<output>_preview.mp4`, `<output>_draft.mp4`, `<output>_<variant>.mp4`, all in the [output folder](#output-folder-output_dir---output-dir); no path separators |
| `output_dir` | `output` | the [output folder](#output-folder-output_dir---output-dir) of those files: relative to the project folder, or absolute |
| `format` | `{width: 1920, height: 1080, fps: 30}` | final render (`vidgen render`) |
| `preview` | `{width: 854, height: 480, fps: 15}` | `vidgen render --preview` |
| `draft` | 240 px on the shorter side, 8 fps | `vidgen render --draft`: `{width, height, fps}`, each optional; see [drafts](#drafts-vidgen-render---draft) |
| `variants` | `{}` | named overrides, see [variants](#variants) |
| `include` | `[]` | files (YAML / JSON, relative to this file, e.g. `../shared/cast.yaml`) whose `characters`, `voices` and `sets` this config starts from; this config's own entries win; see [shared casts and sets](#shared-casts-and-sets-include-and-sets) |
| `sets` | `{}` | named `stage` sets (`name: {background, layers, props, marks, light, wind...}`) a stage scene uses with `set: NAME`; see [shared casts and sets](#shared-casts-and-sets-include-and-sets) |
| `theme` | see [theme](#theme) | preset, colors, sizes, font, background, code style |
| `voice` | see [voice](#voice-voice) | the narration voice: ElevenLabs (default), OpenRouter, or Kokoro running locally (free; extra `schu-video-generator[kokoro]`; [Kokoro](#kokoro-on-this-computer-provider-kokoro)) — one provider per video ([narration providers](#narration-providers)) |
| `voices` | `{}` | named voices for dialogue, picked by scenes and beats with `voice: NAME`, see [multiple voices](#multiple-voices-voices) |
| `characters` | `[]` | cartoon characters `{name, voice, look, colors}`, declared once and used by any scene; see [characters](#characters-characters) |
| `host` | none | a cartoon host beside the content of every scene (not `stage` or `card` scenes): a character name, or `{character, side, size, place, floor, floor_color, facing, speaks, pose, expression, auto_direct}`; see [a host beside any scene](#a-host-beside-any-scene-host) |
| `subtitles` | `{speakers: off}` | `speakers: name` puts the speaker's label before their lines in the SRT, see [multiple voices](#multiple-voices-voices) |
| `narration` | see [narration](#narration-narration) | beat padding, duration estimate |
| `pronunciation` | `{}` | how the narrator says terms (TTS text only), see [pronunciation](#pronunciation-pronunciation) |
| `terms` | `{}` | one colour per concept: `{loss: accent, gradient: "#E07A5F"}` (theme colour tokens or hex), or `{term: {color, tex}}`; the term is drawn in its colour wherever it is on-screen text, its `tex` parts in equations; see [one colour per concept](#one-colour-per-concept-terms) |
| `pronunciation_file` | none | YAML/JSON file(s) with more pronunciation entries |
| `language` | none (English rules) | the video's language, a BCP-47 tag (`en`, `pt-BR`, `es-419`): caption and SRT line breaks, the `narration_speed` lint, ElevenLabs `language_code`, the MP4's audio language; see [languages and translations](#languages-and-translations) |
| `translations` | none | a translation file (YAML, `vidgen translate-template`) whose texts replace beat texts and on-screen texts, usually in a variant; see [languages and translations](#languages-and-translations) |
| `extensions` | `[extensions]` | folders whose `*.py` files and packages are imported (see docs/EXTENDING.md); the default may be missing, a folder you list must exist |
| `lint` | see [lint](#lint-vidgen-lint) | thresholds and severities of `vidgen lint` |
| `overlays` | `[]` | lower thirds, a watermark, ... drawn over the scenes, see [overlays](#overlays) |
| `sfx` | `{auto: false, gain: 0}` | sound effects of the whole video: automatic sounds for built-in animations, overall level; see [sound effects](#sound-effects-sfx) |
| `music` | none | background music: a bed name (`calm`, `pulse`, `bright`, `cartoon`, `lullaby`) or a file, a cue `{source, volume, ...}`, or a list of cues with `from` / `to` scenes; see [background music](#background-music-music) |
| `soundfont` | none (GeneralUser GS 2.0.3, downloaded once) | the SoundFont (`.sf2` / `.sf3`, relative to the project) composed music is played with; see [SoundFont](#soundfont-soundfont-vidgen-soundfont) |
| `audio` | `{normalize: auto, target_lufs: -16, true_peak: -1.5}` | loudness of the final mix; see [loudness](#loudness-of-the-final-mix-audio) |
| `transition` | none (cuts) | the default transition between scenes: `cut`, `crossfade`, `fade_color`, `push`, `wipe` or `{type, duration, color, direction, soft}`; see [transitions](#transitions-transition) |
| `chapters` | `{metadata: true, youtube: true, intro: Intro}` | what the render writes about the chapters: MP4 chapter entries, the YouTube list `<output>_chapters.txt`, the chapter at 0:00; see [chapters in the outputs](#chapters-in-the-outputs-chapters-metadata) |
| `metadata` | `{}` (title: the `title`) | tags of the MP4: `title`, `artist`, `album`, `comment`, `description`, `copyright`, `date`, `genre`; see [chapters in the outputs](#chapters-in-the-outputs-chapters-metadata) |
| `thumbnail` | none | the thumbnail `<output>_thumbnail.png`, written by `vidgen render` and `vidgen thumbnail`: a scene's frame `{scene, beat, at, overlays}` or a designed card `{title, subtitle, icon, image, preset, background}`, + `{jpeg, auto}`; see [thumbnail](#thumbnail-thumbnail-vidgen-thumbnail) |
| `stt` | `{provider: faster_whisper}` | speech to text for `vidgen readback` (the narration transcribed and compared with the beat texts): `{provider, model, language, device}`; see [readback](#readback-vidgen-readback) |
| `imagegen` | `{provider: openai, model: gpt-image-1, size: auto}` | image generation for `generate:` params and `vidgen imagegen`: `{provider (openai \| openrouter), model, size, quality, resolution, style, negative, svg_model}`; see [generated images](#generated-images-imagegen-vidgen-imagegen) |
| `cartoon_style` | none | style words added to every `generate:` prompt of [`stage`](#generated-backgrounds-cartoon_style) scenes, so a cartoon's backgrounds look alike (`"flat colours, thick outlines, soft shadows"`); part of those pictures' cache key; a variant may change it |
| `cartoon_motion` | `lively` | how characters move: `lively`, `calm` or `none` ([animation principles](#animation-principles-cartoon_motion)); a stage's or a character's own setting wins |
| `motion_effects` | `true` | dust, speed lines, impact stars and whoosh arcs the moves on `stage` scenes add while `cartoon_motion` is not `none`; `false`: none; a stage's `motion_effects` param wins; see [motion effects](#motion-effects-motion_effects) |
| `drawing` | none (`normal`, `flat`, `none`: as drawn) | how the cartoons are drawn: `{outline: thin \| normal \| bold, shading: flat \| soft, texture: none \| paper \| storybook, seed}` on `stage` scenes (the host: outline and shading); a stage's `drawing` param wins key by key; a variant may change it; see [drawing style](#drawing-style-drawing) |
| `foley` | `true` | sounds for the characters' actions on `stage` scenes (footsteps, whoosh, boing, pop); `false`: none; a stage's `foley` param wins; see [foley](#foley-and-music-stings) |
| `ambience` | `true` | a sound bed chosen from each `stage` scene's set while foley is on: a room tone in a room, birdsong outdoors while the light is `day` or `morning` and it does not rain; `false`: none unless a stage's `ambience` param names one; see [ambience](#ambience-and-door-sounds-ambience-knock) |
| `auto_direct` | `false` | automatic directing on `stage` scenes: listeners look at whoever speaks and react after lines, speakers gesture on stressed words, short punchy lines get a close-up; `true`, `false` or `{looks, reactions, gestures, closeups, effects}`; a stage's or a beat's `auto_direct` wins; see [automatic directing](#automatic-directing-auto_direct) |
| `reframe` | none | on `stage` scenes wider than the frame: `speaker` moves the camera to whoever speaks (a 9:16 frame then crops the stage laid out as wide as the 16:9 one), `none` leaves the camera to the beats' own camera actions; none: `speaker` when a stage's characters do not fit in one view; a stage's `reframe` wins; see [vertical cartoons](#vertical-cartoons-reframe) |
| `character_size` | none (`medium`) | how big the characters are on `stage` scenes: `small` (a wide landscape, for cinema), `medium` (TV / YouTube) or `large` (big characters, for phones and Shorts); on a platform level the tiles and props scale with them; captions, on-screen text and speech bubbles keep their size; a stage's `character_size` or `size` wins; a variant may change it; see [character size](#character-size-character_size) |
| `scenes` | required | the scenes in order, at least one |

### Output folder (`output_dir`, `--output-dir`)

`vidgen render` and `vidgen thumbnail` write the deliverables — the MP4, the SRT, the YouTube
chapter list and the thumbnail (`<output>[_<variant>][_preview].mp4`, `.srt`, `_chapters.txt`,
`_thumbnail.png` / `.jpg`) — into **`<project>/output/`**, created when missing. `vidgen export`,
and `vidgen slides` (the PDF title page's thumbnail) read them from there. Where it is:

1. `--output-dir DIR` on `vidgen render`, `thumbnail`, `export` and `slides`: a relative `DIR`
   is relative to the **current directory**, like any command-line path;
2. else `output_dir:` in `video.yaml` (a variant may set its own): a relative path is relative
   to the **project folder** (not the current directory), an absolute path is used as is;
3. else `output`.

```yaml
output_dir: ../renders     # <project>/../renders/<output>.mp4
```

The intermediate files stay in `build/` and the GIFs, clips and slide decks of `vidgen export`
and `vidgen slides` in `exports/`, wherever the output folder is. The `--json` documents give
the absolute paths. Under `vidgen mcp`, `output_dir:` must stay inside the allowed folder.

## Scenes and beats

```yaml
scenes:
  - id: intro                 # required, unique; letters, digits and _ only
    type: title               # a built-in or extension scene type (`vidgen list-scenes`)
    params: {title: "Hello"}  # checked against the type's params (tables below)
    beats:                    # what the narrator says, in order
      - text: "Welcome."      # required, non-empty
        id: intro_b1          # optional; default <scene id>_b<n> (1-based); unique in the video
      - text: "Let's start."
        actions: []           # optional per-beat actions on the scene's targets (see "Beat actions")
  - id: pause
    type: text_card
    params: {text: "Part 2"}
    duration: 2               # a silent scene: no beats, a duration in seconds
```

| key | default | |
|---|---|---|
| `id` | required | names the scene in `--scene`, build files and errors |
| `type` | required | scene type name |
| `params` | `{}` | free-form for types without a params model |
| `beats` | `[]` | each beat is narrated into `audio/<beat id>.mp3`; its animation lasts as long as its audio plus `narration.pad` |
| `duration` | none | seconds; required on a scene without beats and not allowed on a scene with beats |
| `lint_ignore` | `[]` | `vidgen lint` findings to skip in this scene, see [lint](#lint-vidgen-lint) |
| `overlays` | `true` | the video's [overlays](#overlays) on this scene: `false` for none, or per overlay id `false` / option overrides, or an overlay of this scene only |
| `chapter` | none | a new [chapter](#chapters) starts at this scene: its title, or `{title, number}` |
| `voice` | none (the base `voice:`) | who says this scene's beats: a name from [`voices:`](#multiple-voices-voices) or `default` |
| `sfx` | `[]` | sound effects at seconds from the scene's start (silent scenes too), see [sound effects](#sound-effects-sfx) |
| `music` | `true` | the [background music](#background-music-music) during this scene: `false` for none, `{volume: dB}` to change its level here; under [music that follows the video](#music-that-follows-the-video) also `{mood, key, tempo, instruments, seed}` from this scene's first bar |
| `transition` | the video's `transition` | how the video passes into this scene from the one before it, see [transitions](#transitions-transition) |
| `carry` | `[]` | objects of the scene before that this scene starts with, where they ended (a match cut), then moves into its own targets: target names, or `"NAME -> NAME"`; see [continuity](#continuity-carrying-objects-into-the-next-scene-carry) |
| `set` | none | a `stage` scene's set: a name from [`sets:`](#shared-casts-and-sets-include-and-sets) or a [built-in set](#ready-made-sets-set-city_street) (`city_street`, `park`, `beach`, `forest`, `snowy_hills`; rooms: `classroom`, `kitchen`, `shop`, `living_room`, `bedroom`) whose params this scene starts from; its own `params` win |
| `host` | the video's | the [host](#a-host-beside-any-scene-host) beside this scene's content: `false` for none, a character name, or a mapping of the keys that change here (`{side: left}`, `{expression: thinking}`; with `character` when the video has no host) |
| `terms` | `true` | `false`: this scene draws the video's [terms](#one-colour-per-concept-terms) in their usual colours (its captions too) |

Beat `id`s name the audio files: keep them when you edit the text (only that beat is
re-voiced). A beat `text` is spoken as written; it is also the subtitle. `*word*` in it marks a
stressed word for [automatic directing](#automatic-directing-auto_direct): the asterisks are not
spoken or shown. `[laugh]`, `[gasp]`, `[sigh]`, `[hmm]`, `[giggle]`, `[groan]` and `[beep]` in it are
[voice sounds](#voice-sounds): made at that point, not shown. A beat's `actions`
(default `[]`) point at parts of the scene while it is spoken — reveal, dim, highlight — see
[beat actions](#beat-actions). A beat's `voice` (default: its scene's) picks another speaker for
that beat — a dialogue inside one scene, see [multiple voices](#multiple-voices-voices). A beat's
`sting` (default none) plays a short music sting on it: `reveal`, `comic` or `sad`, or `{kind, at,
gain}`, see [music stings](#foley-and-music-stings). A beat's `music_pause` (default none) stops
[composed music that follows the video](#music-that-follows-the-video) just before it (a
punchline) until the next bar line after it: `true`, or `false` to stop the automatic pause before
a `card` scene's first beat or a short last line. A beat's `auto_direct` (default: its scene's,
else the video's) turns [automatic directing](#automatic-directing-auto_direct) on or off for that
beat of a `stage`. A beat's `shot` (default none) frames characters of a `stage` for that beat:
`closeup kit`, `two_shot`, `over_shoulder kit pip`, ... or `{kind, of, move, run_time}`, see
[shots](#shots-shot). A beat's `overlap` (seconds, default none) starts it before the line of
the beat before has ended, and `interrupt: true` (default `false`) cuts that line off, see
[overlapping lines](#overlapping-lines-overlap-interrupt); not on a scene's first beat. A beat's
`emotion` (default: its voice's, else none) says how the line feels — `excited`, `sad`,
`whisper`... — and changes how it is spoken (Kokoro: speed, pitch, loudness and pauses;
ElevenLabs: an audio tag or voice settings; OpenRouter: an instruction), see [voices with
feeling](#voices-with-feeling-emotion).

## Chapters

A video can be divided into chapters. A chapter starts at every [`chapter`](#chapter) scene (its
`title` and `number` params) and at every scene with a `chapter:` key, which marks a new chapter
without a divider card:

```yaml
scenes:
  - id: intro                 # before the first chapter: no chapter
    type: title
    params: {title: "Engines"}
    beats: [{text: "..."}]
  - id: part1
    type: chapter             # a divider card starts chapter 1 "Setup"
    params: {number: 1, title: "Setup"}
    duration: 3
  - id: data                  # still chapter 1
    type: text_card
    params: {text: "Data"}
    beats: [{text: "..."}]
  - id: results
    type: bullets
    chapter: Results          # chapter 2 starts here, no card (long form: {title: Results, number: 2})
    params: {heading: "Results", items: ["Faster", "Smaller"]}
    beats: [{text: "..."}]
```

| key | default | |
|---|---|---|
| `title` | required | the chapter's name (the short form `chapter: Results` gives only this) |
| `number` | none | its number as shown (an integer, or text like `"Part II"`); without one, indicators show its position (1, 2, ...) |

On a `chapter` scene, `chapter:` renames the chapter in lists and indicators (e.g. a shorter
title than the card's) and keeps the card's number unless it gives one. A chapter lasts until
the next one starts (the last until the video's end). `vidgen validate` rejects the same
chapter twice (same title and number; a card starts its chapter by itself, the scenes after it
need no `chapter:`), integer numbers that do not increase, and a scene with `chapter:` right
after a chapter card (the card would be a chapter of its own; give the card the `chapter:`
instead). The [`progress_bar`](#progress_bar) marks chapters, the
[`chapter_indicator`](#chapter_indicator) names the current one; extensions read the list with
`video_chapters(project)` (docs/EXTENDING.md). `vidgen render` also writes them into the MP4 and
a YouTube chapter list (next section).

### Chapters in the outputs (`chapters`, `metadata`)

`vidgen render` writes the chapters into the MP4 (players such as VLC, mpv, QuickTime and most
video editors list them and jump to them) and next to it a chapter list for a YouTube
description, `<output>_chapters.txt` (`<output>_<variant>[_preview]_chapters.txt` for variants
and previews):

```text
0:00 Intro
0:12 Setup
1:05 Results
```

```yaml
chapters:              # optional; the defaults
  metadata: true       # chapter entries in the MP4
  youtube: true        # <output>_chapters.txt, and warnings when YouTube would ignore it
  intro: Intro         # the chapter at 0:00 before a later first chapter; false: none
metadata:              # optional tags of the MP4 (unset ones are not written)
  artist: "Jane Doe"
  comment: "Made with vidgen"
```

| key | default | |
|---|---|---|
| `metadata` | `true` | write the chapters into the MP4 (`false`: the MP4 has none; its tags are still written) |
| `youtube` | `true` | write `<output>_chapters.txt` (`false`: none, an old one is removed) and check YouTube's rules |
| `intro` | `Intro` | title of the chapter added at 0:00 when the first chapter starts later (the video opens with a title scene); `false`: no intro chapter, the first chapter starts at 0:00 instead |

- **Times** are where the chapter's scene starts in the joined video, with transitions: a
  crossfade, push or wipe into a chapter card starts the chapter where the transition starts
  (the plan's times, `video_chapters(project, intro=True)`; equal to the render for built-in
  scenes). In the MP4 they are milliseconds (FFMETADATA `[CHAPTER]` entries, time base 1/1000);
  the last chapter ends at the end of the video.
- **Titles** are the chapter titles on one line (a card title's line breaks become spaces),
  without their numbers.
- **The intro chapter.** YouTube needs the first chapter at 0:00, and a player's chapter menu
  should cover the whole video, so when the first chapter starts later both lists begin with a
  chapter titled `intro` (only in these outputs: the [`chapter_indicator`](#chapter_indicator)
  and [`progress_bar`](#progress_bar) still show nothing before the first chapter). For a short
  opening (a few seconds of title before chapter 1) set `intro: false`: the first chapter then
  starts at 0:00.
- **YouTube's rules** (it ignores the whole list otherwise): the first timestamp is 0:00, there
  are at least 3 chapters, each at least 10 s long. Timestamps are whole seconds rounded down (a
  click lands at the chapter's first frame or just before it), so a chapter's length is
  measured between its rounded timestamps. `vidgen validate` (planned times) and `vidgen render`
  (the joined video) warn about each broken rule, e.g. `chapters: 'Intro' (0:00-0:03) lasts 3.0
  s; YouTube ignores the whole chapter list when a chapter is shorter than 10 s (...)`; the file
  is written anyway. Paste the file into the video's description on YouTube.
- Without chapters no list is written (and an old one is removed) and the MP4 has no chapters.
- **Tags** (`metadata:`): `title` (default the top-level `title`), `artist`, `album`,
  `comment`, `description`, `copyright`, `date` (e.g. `2026` or `2026-10-07`) and `genre`, all
  text; they are written to every render (variants can override them).
- `timings.json` and `vidgen render --json` list the chapters as published (with the intro
  chapter), `{title, number, scene, start, end, index, count, card, intro}`, also when
  `metadata` and `youtube` are off. Changing `chapters:` or `metadata:` re-renders no scene.

## Thumbnail (`thumbnail`, `vidgen thumbnail`)

The video's thumbnail, `<output>_thumbnail.png` (`<output>_<variant>[_preview]_thumbnail.png`),
is either a **frame of a scene** or a **designed title card**. With a `thumbnail:` section,
`vidgen render` writes it after the video (`auto: false`: only `vidgen thumbnail` does);
`vidgen thumbnail` writes it alone. Its size follows the video's `format`: **1280x720** for a
16:9 video (YouTube's recommended size), **1080x1920** for 9:16 (Shorts, Reels, a vertical
variant), 1080x1080 for a square one; a frame of another shape is cropped to it (centred).

```yaml
thumbnail:                    # a designed card: big bold title, legible when shown small
  title: "Saving 77% of the parameters"   # default: the video's title
  subtitle: "in large language models"
  icon: cpu                   # or image: assets/cover.jpg (beside the title; above it in 9:16)
  preset: bold_neon           # optional: this preset's colours and fonts instead of the video's theme
  background: surface         # optional: a theme colour or hex
  jpeg: true                  # also <output>_thumbnail.jpg, under 2 MB
```

```yaml
thumbnail:                    # a frame of a scene
  scene: results
  beat: 2                     # its id or number (from 1); default: the scene's last beat
  at: 1.5                     # seconds into the beat (into the scene without beat); default: the beat's end
  overlays: false             # without captions, watermark, ... (default true)
```

| key | default | |
|---|---|---|
| `scene` | none | frame thumbnail: the scene; its frame comes from the scene's render (`build/<final\|preview>[_<variant>]/scenes/<scene>.mp4`), which is rendered first when it is missing or stale (fingerprint, as for `vidgen storyboard`) |
| `beat` | the scene's last beat | frame thumbnail: a beat of the scene, its id or its number from 1 (not on a silent scene) |
| `at` | the beat's last frame | frame thumbnail: seconds into the beat, or into the scene without `beat`. Default: the beat's last frame (narration + `narration.pad`, the "end of beat" of [frame stills](#frame-stills-vidgen-render---frames)); a silent scene's frame just before its fade-out |
| `overlays` | `true` | frame thumbnail: with the video's [overlays](#overlays). `false` renders the scene once more without any overlay into `build/..._bare/` (kept for the next time; the scene lays out without the room overlays `reserve`) |
| `title` | the video's `title` | designed: the title, bold, as large as fits in 3 lines (4 in 9:16), font role `heading` |
| `subtitle` | none | designed: a line under the title (font role `body`, the first of the theme's `highlight`, `primary`, `accent` that reaches 4.5:1 on the background, else the title's colour) |
| `icon` | none | designed: an icon (`vidgen list-icons`) in `primary` on a `surface` disc, right of the text (above it in 9:16 / square) |
| `image` | none | designed: a picture (path relative to the project) filling the right part (the top part in 9:16 / square); `icon` or `image`, not both |
| `preset` | the video's theme | designed: a [theme preset](#theme-presets)'s colours and fonts alone (not the video's own theme values) |
| `background` | the theme's | designed: background colour (theme token or hex); the title is `text`, or black / white when `text` would not reach 4.5:1 on it |
| `jpeg` | `false` | also write `<output>_thumbnail.jpg`: the best JPEG quality (92 down to 55) under YouTube's 2 MB limit; without it an old JPEG is removed |
| `auto` | `true` | write the thumbnail at the end of every `vidgen render` (`false`: only `vidgen thumbnail`) |

A thumbnail is either a frame (`scene`, `beat`, `at`, `overlays`) or a designed card (`title`,
`subtitle`, `icon` / `image`, `preset`, `background`); mixing the two is a config error, and
`vidgen validate` checks the scene, beat, icon, image, preset and colour. Without a `thumbnail:`
section `vidgen thumbnail` draws a designed card of the video's title (and `render` writes none).
Changing `thumbnail:` re-renders no scene.

```
vidgen thumbnail [PROJECT] [--variant NAME] [--preview] [--scene ID [--beat ID|N] [--at SECONDS]
                 [--no-overlays]] [--jpeg] [--jobs N|auto] [--output-dir DIR] [--json]
```

`--scene` (with `--beat`, `--at`, `--no-overlays`) takes a frame instead of what the config says;
`--preview` takes frames from the preview render (fast, but scaled up: an `info` says so) and
names the files `..._preview_thumbnail.png`; `--jpeg` also writes the JPEG. The files go to the
[output folder](#output-folder-output_dir---output-dir) (`output/`; `--output-dir DIR`).

**Legibility.** YouTube shows thumbnails at about 320x180 in its grids (and smaller beside a
video). Every run also writes that size, `build/<final|preview>[_<variant>]/thumbnail/<name>_small.png`:
look at it (an AI author: open it as an image) before publishing. A designed card is checked like
[`vidgen lint`](#lint-vidgen-lint) checks a frame, at that small size (long side 320 px):

| rule | severity | |
|---|---|---|
| `min_font` | warning | the title is under 14 px (any other text under 10 px) at the small size: shorten it so it can be set larger |
| `fit` | warning | the title does not fit even at the smallest size (about 14 px small) and was cut with `…` |
| `contrast` | warning | title or subtitle below 4.5:1 (WCAG AA) on the background |
| `max_words` | info | more than 6 words in the title (thumbnails read best with a few) |
| `file_size` | warning | the PNG (or, with `jpeg`, the JPEG) is over YouTube's 2 MB limit |
| `resolution` | info | a frame thumbnail from a render smaller than the thumbnail (e.g. `--preview`) is scaled up |

`vidgen thumbnail` prints them; `vidgen render` logs the warnings (`render --json`: `warnings`).
A frame thumbnail's text is not measured: check it at the small size, or check the scene with
`vidgen lint`.

## Export: GIF and clip (`vidgen export`)

```
vidgen export gif|clip [PROJECT] [--scene ID] [--from SECONDS] [--to SECONDS] [--variant NAME]
              [--preview] [--width PX] [--fps F] [--max-mb MB] [--with-audio] [--output FILE]
              [--output-dir DIR] [--json]
```

Writes a part of the **rendered video** (`<output>[_<variant>][_preview].mp4` in the
[output folder](#output-folder-output_dir---output-dir), `--output-dir DIR` to read it elsewhere, and its
`build/.../timings.json`; render it first) as an animated GIF or an MP4 clip, by default to
`<project>/exports/<output>[_<variant>][_preview]_<scene>[_<from>-<to>s].gif|mp4` (`video` in
place of the scene without `--scene`; `--output FILE` writes elsewhere). With `--scene`,
`--from` / `--to` are seconds from the scene's start (default: the whole scene, kept within it,
including a transition out of it); without it they are times in the video (default: all of it).

- **GIF**: width `--width` (default 480, 270 for a 9:16 video, never wider than the video),
  `--fps` (default 12, at most the video's), loops forever. One palette of 256 colours is made
  for the clip's frames (FFmpeg `palettegen`) and applied with Sierra dithering (`paletteuse`),
  re-dithering only the changed rectangle of each frame, so still parts do not shimmer.
  `--max-mb MB` sets a size budget: while the file is bigger, the frame rate is lowered (down to
  5 fps) and the width with it (down to 160 px), at most 6 encodes; still too big, it keeps the
  smallest and warns (export a shorter part). The JSON lists every attempt.
- **Clip** (MP4): **stream-copied** — exact pixels, instant — when it starts on a keyframe of
  the video (a scene's start, in a video joined without crossfades, pushes or wipes) and keeps
  the video's size and frame rate; otherwise **re-encoded** (H.264 CRF 18, frame-accurate
  start). `--width` / `--fps` re-encode at that size / rate. Silent unless `--with-audio` (the
  sound is then encoded as AAC, cut at the exact start). No chapters.

## Slides (`vidgen slides`)

```
vidgen slides [PROJECT] [--format html|pdf] [--variant NAME] [--preview | --final] [--mode beat|scene] [--per-beat N]
              [--overlays | --no-overlays] [--no-dedupe] [--image-format webp|jpeg|png] [--quality Q]
              [--max-width PX] [--audio] [--separate] [--output FILE] [--jobs N|auto] [--force]
              [--output-dir DIR] [--json]
```

Writes the video as a **slide deck** (a PDF with `--format pdf`, [below](#pdf-deck---format-pdf)): one HTML file, by default
`<project>/exports/<output>[_<variant>][_preview]_slides.html`, that opens in any browser
without network access. Every slide picture is embedded (a `data:` URI, WebP at quality 80 by
default: about 15–40 KB per 854x480 slide, 60–150 KB at 1920x1080), and so are the page's styles
and script.

**Which frames.** The slides are the frame stills of
[`vidgen render --frames`](#frame-stills-vidgen-render---frames), reused like the
[storyboard](#storyboard-vidgen-storyboard)'s: a scene is rendered (with stills) only when its
stills are missing, made at another count or format, or stale.

- `--mode beat` (the default): **one slide per beat**, the beat's last frame: for scenes that
  reveal something per beat (bullets, charts, diagrams...) that is the fully built state of the
  beat, so the deck builds up like a presentation. A silent scene gives its frame before the
  fade-out. `--per-beat N`: N slides per beat (evenly spaced, the last at the beat's end).
- `--mode scene`: **one slide per scene**, the end of its last beat; its notes are all the
  scene's beats.
- Consecutive slides of a scene that look the same (a beat that changes nothing on screen: at
  most 0.05 % of the pixels differ, compared 320 px wide) are **merged** into one slide with both
  beats' notes; `--no-dedupe` keeps them.
- `--preview` (the default, fast; often already rendered by `storyboard` / `lint`) or `--final`
  (full-size, sharp slides for presenting). `--overlays` (the default) shows the video's
  [overlays](#overlays) as they are in the video; `--no-overlays` takes the slides from renders
  without them (captions duplicate the notes on a slide), made in `build/<...>_bare` like a
  [frame thumbnail](#thumbnail-thumbnail-vidgen-thumbnail) without overlays.
- `--variant`: a language variant gives the deck in that language: its translated pictures and
  notes, and the page's `lang`.

**Speaker notes** are the narration of the beats on the slide (the text as written, not the
[pronunciation](#pronunciation-pronunciation)), with the slide's chapter, scene and time in the
video. Pictures get alt text: the scene type, its title and the start of the narration.

**In the browser:**

| key / gesture | |
|---|---|
| `→` `↓` `Space` `PageDown` `Enter`, click on the right two thirds, swipe left | next slide |
| `←` `↑` `Shift+Space` `PageUp` `Backspace`, click on the left third, swipe right | previous slide |
| `Home` / `End` | first / last slide |
| a number, then `Enter` | go to that slide |
| `S` or `N` | speaker notes beside the slide (below it on a narrow or portrait screen), with the next slide; remembered |
| `O` | overview: every slide in a grid, grouped by [chapter](#chapters); click one to go there |
| `F` | fullscreen (the bars hide while the mouse rests) |
| `P` | play / pause: the slides follow the video's timing (each slide from the frame before it to its own); with `--audio`, the narration plays along |
| `?` | the keys |
| `Esc` | close the overview / help, stop playing |

The slide number is in the URL (`deck.html#12` opens slide 12). Slides are scaled to the window
and letterboxed on a dark backdrop; the slide change is a short fade, none with the system's
reduced-motion setting. Printing the page prints one slide per page.

**Options:** `--image-format webp|jpeg|png` and `--quality Q` (1–100; PNG is lossless),
`--max-width PX` scales the pictures down; `--audio` embeds the beats' MP3s (`audio/`, or the
variant's folder) for a narrated deck (a few MB per minute); `--separate` writes the pictures
(and MP3s) into `<name>_files/` beside the page instead of embedding them (keep the folder with
the page); `--output FILE` (`.html`) writes elsewhere; `--jobs`, `--force` as for the
storyboard. A page over 50 MB gets a warning.

### PDF deck (`--format pdf`)

```
vidgen slides [PROJECT] --format pdf [--notes] [--title-page] [--paper a4|letter]
              [--image-format jpeg|png] [--quality Q] [--max-width PX] [--output FILE]
              (+ the frame options above: --variant, --preview | --final, --mode, --per-beat,
               --overlays | --no-overlays, --no-dedupe, --jobs, --force, --json)
```

The same slides as a PDF, by default `exports/<output>[_<variant>][_preview]_slides.pdf`
(`_notes.pdf` with `--notes`). Needs the optional extra **`pip install "schu-video-generator[pdf]"`**
([fpdf2](https://py-pdf.github.io/fpdf2/), pure Python); without it the command says so.

- **Slides** (the default): one slide per page, the page in the video's aspect ratio (16:9:
  960 x 540 pt = 13.33 x 7.5 in, like a widescreen presentation; 9:16: 540 x 960 pt), the
  picture filling it.
- **`--notes`**: a notes page per slide on A4 (or `--paper letter`), portrait: a header with
  the chapter and the video's title, the slide (full width, at most half the page high for
  portrait videos), a line `Slide N / M · <scene title> · <time> in the video`, the narration
  of the slide's beats (in a language variant: the translation) wrapped in Inter, a page number
  `N / total`. Long narration continues on the next page.
- **`--title-page`**: a first page with the thumbnail made by
  [`vidgen thumbnail`](#thumbnail-thumbnail-vidgen-thumbnail) (`<output>[_<variant>][_preview]_thumbnail.png`,
  this quality's or else the other's; run it first) — on a slide page the thumbnail fills it —
  else the title, the thumbnail's `subtitle`, author and date set in type; on a notes title page
  also the number of slides and the narration's length.
- **Bookmarks** (the outline, shown when the PDF opens): the title page, each
  [chapter](#chapters) with its slides under it (`2. <scene title>`); slides before the first
  chapter at the top level.
- **Document properties** from [`metadata:`](#chapters-in-the-outputs-chapters-metadata): title (default the video's
  `title`), author (`artist`), subject (`description`, else `comment`), keywords (`album`,
  `genre`); the language (`language:`); creator `vidgen <version>`.
- **Pictures**: JPEG at quality 85 by default (embedded as is: a 854x480 slide is about
  30–60 KB, 1920x1080 about 100–250 KB), `--quality Q`, or lossless `--image-format png`
  (larger); `--max-width PX` scales them down. Pictures carry alt text.
- Text is set in the bundled Inter (a subset embedded): Latin (accents: pt-BR, es, fr, de...),
  Greek and Cyrillic; scripts Inter lacks (CJK, Arabic, Hebrew, Devanagari) are not drawn.
- `--audio` / `--separate` are HTML-only and `--notes` / `--title-page` / `--paper` PDF-only
  (errors otherwise); the HTML deck always carries the notes. `--output FILE` must end in `.pdf`.

## Format and preview

`format` and `preview` have the same keys: `width` (default 1920 / 854), `height` (1080 / 480)
and `fps` (30 / 15), all positive integers; `width` and `height` must be even (H.264). Any
aspect ratio works: the shorter side of the frame is always 8 Manim units, so 9:16 gives a frame
8 units wide and 14.22 high.

### Drafts (`vidgen render --draft`)

`vidgen render --draft` (MCP `render` with `draft: true`) is the fastest way to check a cartoon's
timing and staging: everything is where and when it will be, without what only decorates.

- **Size and frame rate**: 240 pixels on the shorter side at the format's shape (426x240 for
  16:9, 240x426 for 9:16, 240x240 for 1:1; never larger than `format`), 8 fps (never more than
  `format`'s). `draft: {width, height, fps}` sets them: `width` and `height` together (even),
  `fps` alone or with them. A variant's `format` gives its drafts its shape.
- **Left out**: idle motion (breathing, swaying, blinking; a host's too), the wind's swaying props
  and trailing pieces (balloons and blown props still drift with it), shadows, motion effects
  (dust, speed lines, stars, whoosh arcs, rocket smoke), particles (rain, snow, leaves...: none
  drawn), puddles, settling snow, fog, lightning's flash and bolt, and the light's colour grade
  (the set is drawn as by day; a `light` change still takes its time, stars and window skies still
  follow it), the [drawing style](#drawing-style-drawing)'s soft shading and texture (its outline
  weight stays).
- **Kept**: every beat, action, position and walk, the lip sync (mouths change at the draft's
  frame rate), effect symbols, bubbles, captions, overlays, cards, living props, birds, water,
  rainbows, and every sound (narration, foley, thunder, splashing steps, ambience and music).
  Beat starts fall on whole frames, as at every frame rate, so over a scene they may run a frame or
  two of the draft (up to about 0.2 s) apart from the preview's.
- **Files**: renders go to `build/draft[_<variant>]/` and the video to
  `<output>[_<variant>]_draft.mp4` (with `_draft.srt`, `_draft_chapters.txt`,
  `_draft_thumbnail.png`); a draft never reuses or replaces a preview or final render, nor they a
  draft. `vidgen lint` and `vidgen storyboard` never use drafts.

Measured on one scene of each Phase K / L example, without audio (word-count timing), one
render at a time: `cartoon-rain-check` `storm` (23 s of rain, wind and a light change) 21.5 s at
preview (640x360, 15 fps) → 8.1 s as a draft; `cartoon-muffin-mystery` `morning` (31 s indoors)
25.4 s → 12.7 s.

## Variants

A variant is a named set of overrides deep-merged onto the config: mappings merge key by key,
anything else (lists such as `scenes`, strings, numbers) replaces the base value. The result is
validated like a normal config; a variant cannot contain `variants`. `vidgen validate` checks
every variant.

```yaml
variants:
  vertical:                                   # vidgen render --variant vertical
    format: {width: 1080, height: 1920}       #   -> <output>_vertical.mp4
    preview: {width: 480, height: 854}
  spanish:
    language: es                              # see "Languages and translations"
    translations: translations/spanish.yaml   # beat and on-screen texts: own audio folder audio/spanish/
    voice: {voice_id: "XXXXXXXXXXXXXXXXXXXX"}
  short:
    scenes: [...]                             # a list replaces the whole base list
```

Renders of a variant go to `build/<final|preview>_<variant>/`. Audio sharing rules are under
[narration audio](#narration-audio-elevenlabs).

## Shared casts and sets (`include:` and `sets:`)

A cartoon series keeps its characters, voices and places in shared files, and each episode
starts from them:

```yaml
# an episode's video.yaml (like examples/cartoon_series/episode_2, shortened)
title: "Nib and Olla: The Weather Hat"
include: [../shared/cast.yaml, ../shared/sets.yaml]   # relative to this file
characters:                                           # this episode only: olla gets a scarf
  - name: olla
    look: {accessories: [hat, scarf]}
scenes:
  - id: bench
    type: stage
    set: workshop                                     # from sets.yaml
    params:
      light: night                                    # the scene's own params win
      characters: [nib, {name: olla, at: 0.75}]
    beats: [...]
```

```yaml
# shared/cast.yaml
voices:
  nib_voice: {voice: af_sarah}
characters:
  - name: nib
    voice: nib_voice
    look: {body: round, hair: curly}
```

```yaml
# shared/sets.yaml
sets:
  workshop:
    background: ["#E9DCC9", "#F6EFE4"]
    light: indoor
    marks: {bench: 0.3}
    props: [{prop: table, name: bench, at: bench}, lamp]
```

- **`include:`** a file name or a list. An included file holds only `characters`, `voices`,
  `sets` and its own `include` (relative to it; a file reached twice is merged once). The files
  merge in order, a file's includes before the file, the project's own config last:
  mappings (`voices`, `sets`, a character's `look`) merge key by key; a `characters` entry with a
  name already declared changes that character (its keys win), a new name is added; anything
  else replaces. File paths in an included file (a character's `look.svg`, a set's `image`,
  `layers[].image`, `props[].svg`) are relative to that file. A missing or circular include is
  an error naming the chain (`video.yaml -> ../shared/sets.yaml -> old.yaml: include 'x.yaml' not
  found`). A variant cannot contain `include` (it may change what the includes gave, as usual).
- **`sets:`** named [`stage`](#stage) params: `background` / `image` / `generate`, `ground`,
  `ground_color`, `layers`, `props`, `marks`, `light`, `wind`, `particles`, `width`, even
  `characters` (a shopkeeper always behind the counter). A stage scene's **`set: NAME`** starts
  its params from the set, then its own params win:
  - `image`, `generate` and `background` are one choice: a scene that gives any of them drops
    all three of the set's;
  - mappings (`marks`) merge key by key;
  - `characters`, `props`, `layers` and `particles` add to the set's (the set's first). A scene
    entry named like a set entry changes that entry (its keys win): a character by its name, a
    prop or layer by `name:` equal to the set entry's own or default name (`{name: tree, at:
    0.3}` moves the set's first unnamed `tree`, `tree_2` the second). An unnamed scene prop is
    always added. An empty list (`props: []`) clears the set's;
  - anything else (`light: night`, `width`) replaces the set's value.
- **`vidgen validate`** prints `included:` with the files, and each problem says where its value
  is written: `characters[0].voice (in ../shared/cast.yaml): unknown voice ...`; a problem in a
  set's value points at the set (`sets.workshop.props[1].prop (in ../shared/sets.yaml)`), once
  however many scenes use it; a scene's own entry is named by its place in the scene's params.
  `--json` problems carry `file` (`null`: the project's config file). No line numbers.
- Renders, `vidgen tts` and `vidgen imagegen` see the merged config: editing a character, voice
  or set in an included file re-renders the scenes that use it, makes the audio of a changed
  voice stale and gives a changed `generate:` prompt a new picture; a set no scene uses changes
  nothing. SVGs and pictures an included file names outside `assets/` count like assets.
- **`vidgen screenplay --cast FILE`** reuses a cast (see
  [cartoons from a screenplay](#cartoons-from-a-screenplay-vidgen-screenplay)); `vidgen cast
  --random N` writes a new one whose characters differ clearly ([a random cast](#a-random-cast-vidgen-cast)).

`examples/cartoon_series/` is a series of two episodes on one shared cast and two sets.

### Ready-made sets (`set: city_street`)

vidgen comes with sets of its own. A `set: NAME` that the project's `sets:` (with its includes)
does not define uses the built-in set of that name; a project set of the same name wins. The
scene's params override a built-in set by the same rules as any set (above): `light: night`
replaces, `marks` merge, `props: [{name: shop_2, color: tertiary}]` changes the second shop,
`props: []` or `particles: []` clears them, a `background` / `image` / `generate` replaces the
sky. Every built-in set leaves two marks clear for two characters at depth 0, `stand_left` and
`stand_right`; with them it lints clean.

```yaml
scenes:
  - id: corner
    type: stage
    set: city_street                   # no sets: needed
    params:
      characters: [{name: pip, at: stand_left}, {name: kit, at: bus_stop}]
      light: sunset
```

![The outdoor sets with two characters on stand_left and stand_right](gallery/media/sets_outdoors.png)

| set | what is in it | own marks | light, ambience |
|---|---|---|---|
| `city_street` | blocks of buildings behind two `shop` fronts across a `road`, a `lamp` post, a `bench`, a `bus_stop`; a pavement ground | `stand_left` 0.3, `stand_right` 0.68, `bench` 0.5, `bus_stop` 0.9 | `day`, `city` |
| `park` | hills, a `path`, a `fence` at the back, a `tree`, a `fountain`, a `bench`, two `flowers` beds; grass | `stand_left` 0.3, `stand_right` 0.7, `fountain` 0.5, `bench` 0.84 | `day`, `auto` (birdsong by day) |
| `beach` | the sea on the horizon and in front on the left ([`water`](#water-and-air-vehicles-water-land) from 0 to 0.3, with waves: a boat floats there), sand, the `sun`, a `beach_umbrella`, two `shell`s | `stand_left` 0.4, `stand_right` 0.84, `umbrella` 0.63, `shore` 0.15 (on the water) | `day`, none (no sea sound yet) |
| `forest` | far pine shapes, `tree`s and `pine`s at several depths, a `bush`, a `log` (seats two), two clusters of `mushroom`s | `stand_left` 0.32, `stand_right` 0.68, `log` 0.5 | `morning`, `auto` (birdsong by day) |
| `snowy_hills` | white hills, `pine`s, a `rock`, light snow falling whose layer lies on the ground and the props from the start ([`settle`](#snow-that-settles-settle), `settled: 60`) | `stand_left` 0.34, `stand_right` 0.68 | `day`, none |

The props are named by kind and numbered in the order the set lists them, as on any stage (the
forest's: `pine`, `pine_2`, `tree`, `tree_2`, `pine_3`, `tree_3`, `bush`, `log`, `mushroom`,
`mushroom_2`); `src/vidgen/data/sets/outdoors.yaml` in the package lists every set. Their props
are shown under [Props](#props). `vidgen validate` reports an unknown set with the project's and the
built-in names (`unknown set 'beech'; did you mean 'beach'? sets: none (...); built-in sets:
classroom, kitchen, shop, living_room, bedroom, city_street, park, beach, forest, snowy_hills`). A
built-in set is part of the scene's params, so a newer vidgen that changes a set renders the
scenes using it again.

### Ready-made rooms (`set: classroom`)

Five built-in sets are [rooms](#rooms-room): a wall, a floor, a door (`door`, a mark too: `enter`
/ `exit` with `door: door`), windows, furniture against the wall, `light: day` in the classroom, kitchen and shop (a day sky in the windows), `light: indoor` in the living room and bedroom (lamplight;
the windows show the evening sky) and `ambience: room_tone`. They work like the outdoor sets
above, with the same two clear marks `stand_left` and `stand_right` at depth 0. The room merges
key by key (`room: {wallpaper: dots}` keeps the set's door and windows; `room: {windows: []}`
removes the windows), `light: day` makes it daytime, and a `background` / `image` / `generate`
replaces the room (its `against: wall` props then need a room of the scene's own).

The furniture against the wall stands at the wall's depth, 0.4: a character on `stand_left` sits
or leans on it after walking there (`- walk_to: pip, to: {mark: sofa, depth: 0.4}`, then `-
sit_on: pip, to: sofa`; `vidgen validate` says so when the walk is missing). Each seat has a mark
of its own at its x.

```yaml
- id: lesson
  type: stage
  set: classroom
  params:
    characters: [{name: pip, at: stand_left}, {name: kit, at: stand_right}]
  beats:
    - text: "Kit takes a seat."
      actions:
        - {walk_to: kit, to: {mark: pupil, depth: 0.25}}
        - {sit_on: kit, to: school_desk, at: 0.6}
```

![The indoor sets with two characters on stand_left and stand_right](gallery/media/sets_indoors.png)

| set | what is in it | seats and leans (depth) | own marks |
|---|---|---|---|
| `classroom` | a `blackboard` on the wall, the teacher's `desk` (with its chair), two pupils' `school_desk`s facing the board, a window, the door on the right; boards | `desk` (0.4), `school_desk` and `school_desk_2` (0.25, the pupils face left) | `stand_left` 0.27, `stand_right` 0.69, `blackboard` 0.47, `teacher` 0.12, `pupil` 0.6, `pupil_2` 0.8 |
| `kitchen` | a `fridge`, a `counter` with a `kettle` on it (`lift: 0.18`), a `clock`, a window over a `table` with two `chair`s facing each other; striped wall, tiles | `chair`, `chair_2` (0.2); lean on `fridge`, `counter` (0.4) | `stand_left` 0.27, `stand_right` 0.73, `counter` 0.3, `table` 0.5, `chair` 0.395, `chair_2` 0.605 |
| `shop` | two `shelf_with_goods` at the wall, a `counter` in front (depth 0.2) with a `till` on it, a wide shop window; tiles, a ceiling | lean on `shelf_with_goods`, `shelf_with_goods_2` (0.4), `counter` (0.2); a shopkeeper stands behind the counter at depth 0.3 | `stand_left` 0.27, `stand_right` 0.8, `counter` 0.55, `behind_counter` 0.5 |
| `living_room` | a `lamp` (on), a `sofa` under a `picture`, the door in the middle, a `tv` under the window, an `armchair` (depth 0.25), a `rug`; striped wall, boards | `sofa` (two places, 0.4), `armchair` (0.25) | `stand_left` 0.38, `stand_right` 0.66, `sofa` 0.21, `tv` 0.8, `armchair` 0.93 |
| `bedroom` | a bedside `lamp` (on), a `bed` under a window with curtains, the door, a `wardrobe`, a `rug`; dotted wall, boards | `bed` (two places, 0.4); lean on `wardrobe` (0.4) | `stand_left` 0.42, `stand_right` 0.72, `bed` 0.24, `wardrobe` 0.86 |

Every door is a lean too. `src/vidgen/data/sets/indoors.yaml` in the package lists the rooms; their
new props are shown under [Props](#props).

## Theme

```yaml
theme:
  preset: light_academic    # optional: a named set of theme values (see below)
  background: "#0E1116"     # frame background
  font: Inter               # sans family: body text and every role not set below (bundled)
  font_serif: Source Serif 4  # serif family, the `serif` font token (bundled)
  font_mono: JetBrains Mono NL  # monospace family, the `mono` token: code listings (bundled)
  fonts: {heading: serif}   # optional: font per role (see "Fonts" below)
  code_style: github-dark   # Pygments style of `code` listings
  colors:                   # tokens; these are the defaults, add any name you like
    text: "#E8EAED"
    dim: "#838B98"
    accent: "#FF6B6B"
    highlight: "#FFD166"
    primary: "#58C4DD"
    secondary: "#F2A541"
    tertiary: "#83C167"
    surface: "#161B24"      # panels, code window
    # brand: "#7C3AED"      # your own tokens work in every color param
  palette: ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]   # series colors (charts), in order
  scale: auto               # type scale: compact, standard, large or auto (see below)
  sizes: {title: 56, subtitle: 42, heading: 36, body: 32, caption: 24, small: 20}  # font points
```

You only write what you change: `colors` and `sizes` are merged over the preset and the
defaults (and over tokens registered by extensions); `palette` replaces the list. Colors are hex
(`#RGB`, `#RRGGBB` or `#RRGGBBAA`, quoted in YAML because of the `#`); token names use letters,
digits and `_`. Sizes are positive numbers. `code_style` is any installed Pygments style
(`vidgen schema` lists them); a `code` scene's own `style` param wins over it.

**Precedence** (highest first): the values written under `theme:` (after merging a variant) >
the preset (and its base preset) > defaults registered by extensions
(`register_theme_defaults`, docs/EXTENDING.md) > the built-in defaults shown above (the
`dark_tech` look). Without `preset` the preset level is simply empty, so an existing project
looks exactly as before. `vidgen list-themes` shows every preset with its values (below), and
`vidgen validate` warns (without failing) when the project's own theme has a colour pair below
WCAG AA (`warning: theme contrast: colors.dim #6B7280 on background #0E1116: 3.91:1 (needs
4.5:1, too low)`; same check as the presets' tests, see below).

### Fonts

vidgen ships three open-licence font families (SIL OFL 1.1; licences in
`src/vidgen/data/fonts/`, list in `THIRD_PARTY_NOTICES.md`) and registers them for its own
renders, so they need **no installation** on Windows, macOS or Linux: **Inter** (sans; Regular,
Bold, Italic), **Source Serif 4** (serif; Regular, Bold, Italic) and **JetBrains Mono NL**
(monospace without coding ligatures, so code shows the characters as typed; Regular, Bold).
Any installed font works too: write its family name (`font: Segoe UI`). A bundled family that is
also installed system-wide is fine (either copy is used; they are the same font).

The theme has three family tokens: `font` (sans; default Inter), `font_serif` (default Source
Serif 4) and `font_mono` (default JetBrains Mono NL). Built-in scenes ask for a font by
**role**, and `fonts` maps a role to a token — `sans`, `serif`, `mono` — or directly to a family
name:

| role | used for | default |
|---|---|---|
| `body` | all other text (subtitles, bullets, captions, labels...) | `sans` |
| `heading` | `title` title, `bullets` heading, chart and `code` titles, `end_card` title | `sans` (`serif` in `light_academic`, `warm_editorial`) |
| `quote` | `quote` text | `sans` (`serif` in `warm_editorial`) |
| `quote_mark` | the large mark of `quote` | `serif` |
| `code` | `code` listings and their line numbers | `mono` |

```yaml
theme:
  preset: warm_editorial
  font_serif: Georgia            # an installed serif instead of the bundled one
  fonts: {quote: sans, heading: "Playfair Display"}   # roles: token or family name
```

`fonts` merges over the preset's roles per role; extension scenes can use any role name
(`current_theme().font_for("kicker")`, unknown roles are `sans`). A scene's own font param
(`code.font`, `quote.mark_font`) wins over the role.

Changed in Step 18: `font` is the sans family; a `font` written in `video.yaml` no longer
overrides the roles a preset sets (headings of `light_academic` stay serif; write `fonts:
{heading: sans}` for all-sans). `code` listings use JetBrains Mono NL (was the system's
`Monospace`), the quote mark Source Serif 4 (was Georgia / DejaVu Serif).

### Type scales

`scale` sets the six built-in sizes at once (font points):

| scale | `title` | `subtitle` | `heading` | `body` | `caption` | `small` | for |
|---|---|---|---|---|---|---|---|
| `compact` | 48 | 36 | 32 | 28 | 22 | 20 | dense slides, long lists |
| `standard` | 56 | 42 | 36 | 32 | 24 | 20 | 16:9 video (the defaults) |
| `large` | 66 | 50 | 44 | 38 | 30 | 26 | vertical/mobile video, accessibility |
| `auto` | | | | | | | `large` when the video (`format`) is portrait (taller than 1:1.2), else `standard` |

A scale is shorthand for those six `sizes` at the level where it is chosen: `theme.sizes`
still override single sizes (`{scale: large, sizes: {title: 60}}`), a `scale` written under
`theme:` replaces the preset's scale (and its `sizes` for those six tokens), and a preset's own
`sizes` sit above its scale. Without any `scale` (in the config or the preset) the default is
`auto`, so a `vertical` variant (`format: {width: 1080, height: 1920}`) automatically gets the
larger text a phone needs, while 16:9 output is unchanged; write `scale: standard` to keep
the old sizes in portrait. `auto` follows the variant's final `format` (a `--preview` render
uses the same sizes, so previews show the final layout). Text never overflows because of a
scale: built-in scenes fit text into their regions (wrapping, then shrinking).

Changed in Step 17: portrait projects without a scale get `large` sizes (`auto`), and
`high_contrast` uses `large` (was `caption: 26`, `small: 24`).

### Theme presets

`theme: {preset: NAME}` selects a named set of values; anything else under `theme:` still
wins, so `{preset: light_academic, colors: {primary: "#0B5FFF"}}` is the light look with your
blue. A variant can switch presets: `variants: {light: {theme: {preset: light_academic}}}`.
Mind that values written in the base `theme:` also override the variant's preset (a base
`background: "#0E1116"` would keep a light variant dark): write in the base only what every
variant shares, or select the default look with `preset: dark_tech` there instead.

| preset | background | text / dim | accents (`accent`, `highlight`, `primary`, `secondary`, `tertiary`) | `surface` | palette | `code_style` | scale |
|---|---|---|---|---|---|---|---|
| `dark_tech` (the default look) | `#0E1116` | `#E8EAED` / `#838B98` | `#FF6B6B`, `#FFD166`, `#58C4DD`, `#F2A541`, `#83C167` | `#161B24` | `#58C4DD`, `#F2A541`, `#C792EA`, `#83C167` | `github-dark` | `auto` |
| `light_academic` | `#F8F7F3` (off-white) | `#1F2328` / `#59606B` | `#B42318`, `#A64B00`, `#1D4ED8`, `#C2410C`, `#15803D` | `#FFFFFF` | `#1D4ED8`, `#C2410C`, `#9D2F8F`, `#15803D` | `xcode` | `auto` |
| `high_contrast` | `#000000` | `#FFFFFF` / `#C9CED6` | `#FF7A7A`, `#FFE14D`, `#4DD2FF`, `#FFAA4D`, `#7EE787` | `#141414` | `#4DD2FF`, `#FFAA4D`, `#FF8FD8`, `#7EE787` | `github-dark` | `large` |
| `warm_editorial` | `#F6F0E4` (cream paper) | `#2B2118` / `#6A5A4A` | `#9B1D3A`, `#8F5700`, `#1F5E6E`, `#B4441B`, `#37704F` | `#FFFBF4` | `#1F5E6E`, `#B04A16`, `#8D4AAB`, `#1A7C4D`, `#8C2024` | `default` | `auto` |
| `brand_neutral` | `#F4F5F7` (light grey) | `#15181D` / `#596270` | `#C42B3B`, `#A35200`, `#0B57C2`, `#4A5565`, `#0E7C66` | `#FFFFFF` | `#0B57C2`, `#C2410C`, `#08775A`, `#A04A8A`, `#5B6068` | `xcode` | `auto` |
| `soft_pastel` | `#252238` (dusky plum) | `#F3EEFA` / `#B0A8C4` | `#F7879F`, `#FCE38A`, `#86BDFF`, `#FFC27F`, `#9BEBC9` | `#2C2843` | `#86BDFF`, `#FFC27F`, `#9E8BEF`, `#9BEBC9`, `#F7879F` | `zenburn` | `auto` |
| `bold_neon` | `#0B0614` (violet-black) | `#F7F4FF` / `#A59CC2` | `#FF2E8B`, `#F4FF3A`, `#00C8FF`, `#FF8A1F`, `#39FF9C` | `#170F27` | `#00C8FF`, `#FF2E8B`, `#F4FF3A`, `#8C5BFF`, `#39FF9C` | `monokai` | `large` |

What they are for: `dark_tech` technical explainers; `light_academic` papers and lectures;
`high_contrast` accessibility; `warm_editorial` essays and storytelling; `brand_neutral` a quiet
base for a company colour (`{preset: brand_neutral, colors: {primary: "#..."}}` or a project
preset based on it); `soft_pastel` friendly tutorials; `bold_neon` short social clips.

All presets use the bundled families (Inter, Source Serif 4, JetBrains Mono NL);
`light_academic` sets headings and `warm_editorial` headings and quotes in the serif (see
[Fonts](#fonts)). Every built-in preset
passes WCAG AA (tested): `text` and `dim` at least 4.5:1 on the background and on `surface`,
the accent tokens at least 3:1 on the background and the palette at least 4.5:1 (charts label
series in palette colours; `high_contrast`: 7:1 for all of them). The palettes are ordered and
stay distinguishable for colour-blind viewers: every pair of colours differs by at least 7.5
CIEDE2000 under normal vision and simulated protanopia, deuteranopia and tritanopia (except
`dark_tech`, which keeps the historical default palette; its blue and purple are close for
deuteranopes, so put them apart or use another preset when that matters). Projects can add their own
presets (e.g. a brand look based on `light_academic`) with `register_theme_preset` in an
extension (docs/EXTENDING.md); `vidgen validate` reports an unknown preset name, and
`vidgen schema` lists the built-in and the project's presets.

Changed in Step 17: the third palette colour of `light_academic` (`#7E22CE` → `#9D2F8F`) and
`high_contrast` (`#D7A8FF` → `#FF8FD8`): the old purples were nearly identical to the blue for
deuteranopes.

Changed in Step 16: the default `dim` is `#838B98` (was `#6B7280`, 3.9:1 on the default
background, below WCAG AA); dim captions, axis labels and sources are a little lighter.

### `vidgen list-themes`

`vidgen list-themes [PROJECT] [--json] [--swatches PNG]` lists every preset (built-in, then the
project's own) with its resolved values in this project (background, colours, palette, fonts
and the family of each built-in role, `code_style`, scale and the sizes it gives here), the contrast check (minimum ratios, any
failing pair), the palette's smallest colour difference and for which vision, and the type
scales. `--swatches PNG` (alias `--sheet`, as in `list-icons`) also writes a picture of all presets (one row each: name and
description in its text colours, accent chips, a `surface` panel, the palette as bars), so an
AI author can compare them by opening one image. JSON shape: [below](#vidgen-list-themes---json).

## One colour per concept (`terms`)

A concept the video talks about keeps one colour wherever it is written: the viewer learns that
red means *loss* and finds it again in the next scene, the equation and the chart.

```yaml
terms:
  loss: accent                      # a theme colour token...
  gradient: "#E07A5F"               # ...or hex
  learning rate: {color: secondary, tex: '\eta'}   # TeX parts that stand for it in equations
  weights: {color: primary, tex: [w, W]}
scenes:
  - id: recap
    type: text_card
    terms: false                    # this scene keeps the usual colours
    params: {text: "The loss is not the gradient."}
    beats: [{text: "A recap in plain colours."}]
```

| key | | |
|---|---|---|
| `terms.<term>` | colour | the term's colour: a theme colour token (`accent`, `primary`...) or hex |
| `terms.<term>.color` | colour | the same, in the long form |
| `terms.<term>.tex` | str \| list | TeX parts of equations that stand for the term (`L`, `'\nabla L'`), each whole TeX tokens with balanced braces; coloured in [`equation`](#equation) and [`equation_derivation`](#equation_derivation) steps that contain them |

- **Where**: all text the scenes write with vidgen's text helpers: titles, bullets, cards,
  quotes, tables, chart titles, axis labels, legends and category labels, diagram and process
  labels, timeline entries, captions (karaoke too: the spoken word still takes the highlight
  while it is said), lower thirds; a `line_chart` series whose whole name is a term is drawn in
  its colour (unless the series has its own `color`); a `callout` whose label says a term takes
  its colour for the mark and the plate (unless the callout has its own `color`; the label's text
  keeps the colour that reads on the plate); a `function_plot` function whose name or label is a
  term is drawn in its colour, and an area whose label says one is filled with it, as are a
  `function_plot` point, vector or mark and a `number_line` point, interval or jump whose label
  says one (unless they have their own `color`). Code listings are not coloured (their syntax
  colours would clash), nor text inside pictures.
- **Matching**: whole words, any case, a plural `s` / `es` included (`loss` also colours
  `Losses`, not `glossy`); a term of several words matches them with any spaces or a line break
  between; a longer term wins over a shorter one inside it. Words are matched as written on
  screen: a [translated](#languages-and-translations) variant gives its own `terms:` in its
  language.
- **What wins**: a scene's own colour for a part of its text (a title's `highlight`, a chart's
  `highlight`, an `equation_derivation`'s `colors`, a `highlight` action) wins over the term's
  colour; `vidgen lint` warns when they differ ([`concept_colors`](#lint-vidgen-lint)).
- **Captions**: a term's colour is used when it keeps the `contrast` rule's ratio on the caption
  plate; the plate is made more opaque (up to 1) for it, and a colour that still does not read
  stays in the caption's text colour (a warning in the render log).
- **Checks**: `vidgen validate` names a colour that is not a theme colour (`terms.loss: unknown
  theme color 'acent'`), two keys that are one term (`loss` and `Loss`) and unbalanced braces in
  `tex`; `vidgen lint`'s `concept_colors` rule warns about more than 5 different colours (none
  stands out), a colour below 4.5:1 contrast on the theme background, and a scene setting that
  colours a term otherwise.

## Icons

vidgen ships 200 line icons (from [Lucide](https://lucide.dev), ISC licence), 25 in each
category `tech`, `data`, `science`, `business`, `people`, `ui` (arrows and interface),
`nature`, `education`, chosen for what explainer videos show; the full list with aliases and
tags is the [icon catalogue](ICONS.md). Built-in scenes take them as params: `icon` on
[`title`](#title), [`chapter`](#chapter), [`stat`](#stat) and [`end_card`](#end_card), `{text,
icon}` items of [`bullets`](#bullets), columns and points of [`comparison`](#comparison),
events of [`timeline`](#timeline), nodes of [`diagram`](#diagram), stages and the token of
[`process`](#process), and the [`icon_grid`](#icon_grid) scene. Extension scenes draw them with `icon(name, ...)` (see
docs/EXTENDING.md "Icons"); scene params that take an icon name are typed `icon` in
`vidgen list-scenes` and checked by `vidgen validate` (an unknown name gets suggestions).

**Aliases.** Some icons have other names that work everywhere a name does: Lucide's old names
of renamed icons (`home` → `house`, `pie-chart` → `chart-pie`, `smile` →
`face-slightly-smiling`, `filter` → `funnel`) and a few synonyms (`idea` → `lightbulb`, `ai`
→ `brain-circuit`, `warning` → `triangle-alert`, `bar-chart` → `chart-column`, `money` →
`banknote`). A project icon with an alias's name replaces the alias.

**Project icons.** Put SVG files in `assets/icons/`: `assets/icons/<name>.svg` adds the icon
`<name>` or replaces the built-in icon of that name (letters, digits, `-` and `_`). Draw them on
a square `viewBox` (Lucide's is 24 x 24, with about 2 units of padding) with strokes or fills in
`currentColor`, so they size and recolour like the built-ins. An optional
`assets/icons/icons.json` gives them a category and search tags:

```json
{"icons": [{"name": "bicycle", "category": "transport", "tags": ["bike", "cycling"]}]}
```

Entries need a `name` whose SVG exists; `category` defaults to `project`, `tags` to none.
Problems (bad file names, a broken `icons.json`) are reported by `vidgen validate` under
`assets/icons`.

### `vidgen list-icons`

`vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG [--theme [PRESET]]] [--json]` lists
the icons available in the project (built-in and `assets/icons`; without a PROJECT and no
config in the current folder: built-ins only), one line each: name, category, `[project]` for
project icons, `(alias: ...)`, tags. `--search` keeps icons whose name, aliases, tags or
category contain every word of TEXT (case-insensitive; best first: name, alias, whole words of
a name or alias, tags, whole words of a tag, then words merely contained in a name or tag, so
`--search ai` lists `brain-circuit` and `bot` before `rain`): `--search "chart"`,
`--search computer`. Tags include the concepts an icon stands for
in a script, so search by idea: `money`, `growth`, `security`, `speed`, `AI`, `team`.
`--category` keeps one category (unknown → error listing them). `--sheet PNG` also draws the
listed icons, labelled with name and category, on a 1280 px wide contact sheet (8 per row; a
long list continues in `<stem>-2.png`, ... ), drawn by the same code as a render: open it to
choose icons by eye. It is black on white; `--theme` draws it in the project's theme (its
background, icons in `primary`, names in `text`) and `--theme warm_editorial` in a preset's
(built-in or the project's), to see icons as a video shows them. JSON shape:
[below](#vidgen-list-icons---json).

## Voice (`voice:`)

```yaml
voice:
  provider: elevenlabs              # elevenlabs (default), openrouter or kokoro: see "Narration providers"
  voice_id: nPczCjzI2devNBz1zQrb    # ElevenLabs voice id
  model_id: eleven_multilingual_v2
  output_format: mp3_44100_128      # ElevenLabs output_format query parameter
  settings:                         # sent as voice_settings
    stability: 0.55                 # 0..1
    similarity_boost: 0.75          # 0..1
    style: 0.0                      # 0..1
    use_speaker_boost: true
  context: true                     # send the neighbouring beats' text for smoother intonation
  timestamps: false                 # also fetch when each character is spoken (karaoke captions)
  language_code: null               # ElevenLabs language_code (ISO 639-1) or false; null: auto
  model: null                       # provider openrouter only (required there): the TTS model id
  voice: null                       # openrouter / kokoro: the voice name
  instructions: null                # openrouter: how to speak (models that read it)
  speed: null                       # openrouter / kokoro: speed multiplier 0.25-4 (openrouter: not sent when null; kokoro: 1)
  lang: null                        # kokoro: language letter (a, b, e, f, h, i, j, p, z); null: from voice / language
  device: cpu                       # kokoro: cpu, cuda or auto
  emotion: null                     # how this voice's beats feel (excited, sad, whisper...); every provider
  dub: null                         # this voice in other languages, {pt: pf_dora}: see "Dubbing"
  label: null                       # speaker name in subtitles / captions (none: not tagged)
  color: null                       # speaker colour in captions (theme token or hex; none: text colour)
```

All keys are optional; the values shown are the defaults. Unknown keys are an error. Changing
`voice_id`, `model_id`, `output_format` or `settings` re-voices every beat of this voice on the
next `vidgen tts`; `label` and `color` only name the speaker (they change no audio). `context`
sends the neighbouring beats only when they have the same voice (see
[multiple voices](#multiple-voices-voices)).

`timestamps: true` makes `vidgen tts` use ElevenLabs' *with-timestamps* endpoint (same voice,
same price): besides `audio/<beat_id>.mp3` it stores `audio/<beat_id>.align.json`, when each
character is spoken, and burned-in [`captions`](#captions) and the SRT then time every word
exactly. Without it word times are estimated (see `captions`). It is not part of the audio hash:
turning it on does not re-voice anything; `vidgen tts --force` fetches the timings for existing
beats (paid again).

`language_code` is ElevenLabs' language enforcement (an ISO 639-1 code such as `pt`). By default
(`null`: auto) vidgen sends the video's [`language`](#languages-and-translations) to the models
that accept one (`eleven_turbo_v2_5`, `eleven_flash_v2_5`; others reject the field, and
`eleven_multilingual_v2` detects the language from the text). A code sends it with any model,
`false` never sends one. When a code is sent it is part of the audio hash (re-voicing those
beats); without one the hash is as before. A named voice may set its own (`voices.<name>.language_code`).

These keys are ElevenLabs'. With `provider: openrouter` the voice is `model`, `voice`,
`instructions` and `speed` instead, with `provider: kokoro` `voice`, `speed`, `lang` and `device`
(see [narration providers](#narration-providers)); the keys of the provider not in use are
ignored.

## Narration providers

One TTS provider voices the whole video: **ElevenLabs** (the default; everything above),
**OpenRouter**, which reaches many TTS models (Mistral Voxtral, Kokoro, Gemini TTS, MiniMax,
ElevenLabs' own models, Microsoft MAI-Voice...) with one key, or **Kokoro** run on your own
computer, free ([below](#kokoro-on-this-computer-provider-kokoro)). Nothing changes for a project
that does not set `voice.provider` (likewise OpenAI stays the default image provider).

```yaml
voice:
  provider: openrouter
  model: mistralai/voxtral-mini-tts-2603     # required: an OpenRouter TTS model id
  voice: en_paul_neutral                     # the model's voice name (each model lists its own)
  instructions: "warm, unhurried explainer; slight pause before numbers"   # optional
  speed: 1.0                                 # optional, 0.25-4: not sent when absent
```

| key | default | |
|---|---|---|
| `provider` | `elevenlabs` | `openrouter`: `POST https://openrouter.ai/api/v1/audio/speech`, key in `OPENROUTER_API_KEY` |
| `model` | (required) | an OpenRouter TTS model id (`author/name`); the list: <https://openrouter.ai/models?output_modalities=speech> |
| `voice` | the model's default, if it has one | the model's voice name (`en_paul_neutral` for Voxtral, `af_heart` for Kokoro, `Kore` for Gemini, `en-US-Harper:MAI-Voice-2.1` for MAI-Voice...); most models need one |
| `instructions` | none | how to speak: tone, pace, accent, language. OpenRouter documents it for Gemini TTS and OpenAI TTS models; others ignore it (the dry run notes that) |
| `speed` | none (not sent) | playback speed multiplier; OpenRouter documents it for OpenAI TTS; other models ignore it or refuse a value other than 1 |
| `label`, `color`, `timestamps` | | as in [`voice:`](#voice-voice) (`timestamps` has no effect, see below) |

**Choosing.** ElevenLabs gives the most natural narration, word timings for karaoke captions and
neighbouring-beat context for smooth intonation; it bills characters against a monthly plan.
OpenRouter pays per use from one balance: per input character for most models (Kokoro
$0.000004, Voxtral $0.0000176, ElevenLabs v3 through OpenRouter $0.00004 per character on
2026-10-08, the highest of each model's providers), while Gemini TTS and Seed Audio also bill the
generated audio (no estimate). `vidgen tts --dry-run` prints the current price per character of
the model and the estimated cost of the run (from OpenRouter's public model list, a free lookup;
offline: "price unknown"). The estimate uses the highest price of the model's providers, so the
real charge can be lower (Kokoro's cheapest provider asks $0.00000062 per character). A real run
then prints what OpenRouter reports it charged: OpenRouter writes each request's cost record a
few seconds after the audio, so vidgen asks again for up to 15 s; when the records are still
missing it says `cost not reported by openrouter yet (why; see https://openrouter.ai/activity)`
— the audio is stored all the same, and the activity page shows the cost later.

**One provider per video.** A named voice of [`voices:`](#multiple-voices-voices) may change
`voice`, `instructions`, `speed` (and `model`) but not `provider`: `voices.ana.provider:
elevenlabs` in an OpenRouter video, or ElevenLabs keys such as `voices.ana.voice_id` (OpenRouter
keys in an ElevenLabs video), are config errors naming the key. A [variant](#variants) may switch
the provider of the whole video (`variants: {cheap: {voice: {provider: openrouter, model: ...,
voice: ...}}}`); its audio then goes to `audio/<variant>/` like any other voice change.

**What differs from ElevenLabs.**
- No neighbouring-beat context (the API has none): each beat is voiced on its own.
- No word timings: `voice.timestamps: true` is a `vidgen validate` warning; captions and the SRT
  use estimated word times within each MP3's speech.
- No `language_code`: the language follows the text (a model's voice usually belongs to one
  language; MAI-Voice voices carry their locale). `instructions` can name the language or accent
  ("Brazilian Portuguese, São Paulo accent") on models that read them.
- Not supported: voice cloning from reference audio (`input_references`) and multi-speaker input
  (one request voicing several speakers): vidgen voices one beat per request.

**Audio.** vidgen asks for MP3 (`response_format: mp3`); models that return only raw PCM (Gemini
TTS: 16-bit mono 24 kHz) are asked for PCM and converted to MP3 with ffmpeg, so `audio/` always
holds `<beat_id>.mp3` + `<beat_id>.hash`. The hash covers the spoken text (pronunciation applied)
and `provider`, `model`, `voice`, `instructions` and `speed`: changing any of them re-voices that
voice's beats. ElevenLabs projects keep their hashes.

**Checks.** `provider: openrouter` without `model`, or a model id without `/`, is a config error.
`vidgen validate` warns (no network, OpenRouter's list bundled with vidgen, dated) about a model
not in the list (with a suggestion), a `voice` the model does not list and a missing `voice` for a
model that lists some; lists may be incomplete, so these are warnings. `vidgen tts --dry-run` and
a real run check OpenRouter's live list: a model it does not have is refused before any paid
request (`problem:`), an unlisted voice or an `instructions` / `speed` the model may ignore is a
`note:`.

**Key and privacy.** The same `OPENROUTER_API_KEY` as the [OpenRouter image
provider](#openrouter-provider-provider-openrouter), read from the environment only, never stored.
If your account requires Zero Data Retention (or excludes providers that keep or train on
prompts), choose a model with a ZDR endpoint: a model without one fails with a clear message that
links the privacy settings and lists the TTS models with a ZDR endpoint (on 2026-10-08 27 of 32,
e.g. `hexgrad/kokoro-82m`, `mistralai/voxtral-mini-tts-2603`, the ElevenLabs, Gemini TTS, Deepgram
and MAI-Voice models; not MiniMax, Qwen or Grok). Both `hexgrad/kokoro-82m` (voice `af_alloy`)
and `google/gemini-3.8-flash-lite-tts` (voice `Kore`) voiced a beat live on 2026-10-09 with an
account requiring ZDR. To check a model: look for its id among the `model_id`s of
`https://openrouter.ai/api/v1/endpoints/zdr` (public, no key), or, from a source checkout, run
`python tools/live_check_openrouter.py --tts --zdr`.

### Kokoro on this computer (`provider: kokoro`)

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) is a small open-weight voice
model that runs locally: free, no key, no account, offline after the first download. It is an
optional extra (PyTorch is large), installed with `pip install ".[kokoro]"` from a checkout or
`pip install "schu-video-generator[kokoro]"` (install steps for Windows and Linux in the README).

```yaml
voice:
  provider: kokoro
  voice: af_heart        # optional: a Kokoro voice (default: the best voice of lang)
  speed: 1.0             # optional, 0.25-4 (default 1; 0.8-1.2 sounds natural)
  lang: a                # optional: a b e f h i j p z (default: voice's first letter, else language:)
  device: cpu            # optional: cpu (default), cuda, auto
```

| key | default | |
|---|---|---|
| `voice` | the language's default (below) | a voice name; a blend `af_bella,af_heart` averages voices (Kokoro's own feature); `af_heart+af_bella:0.6` mixes them by weight (0.4 af_heart, 0.6 af_bella; voices without a weight share what the others leave; all weighted: in proportion) |
| `speed` | 1 | speaking speed multiplier |
| `lang` | the first letter of `voice`, else from the video's `language` | Kokoro's language letter; it decides the pronunciation rules |
| `device` | `cpu` | `cuda`: an NVIDIA GPU (needs a CUDA build of PyTorch); `auto`: the GPU if PyTorch sees one. Not in the audio hash |
| `label`, `color`, `timestamps` | | as in [`voice:`](#voice-voice) (`timestamps` is not needed: English timings are always stored) |

**Languages and voices** (Kokoro-82M v1.0, 54 voices, list bundled with vidgen, dated 2026-10-09;
grades from the model's [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)):

| `lang` | language | from `language:` | default voice | other voices |
|---|---|---|---|---|
| `a` | American English | `en` (none set), `en-US`... | `af_heart` (A) | `af_bella` (A-), `af_nicole`, `am_michael`, `am_fenrir`, `am_puck`... (20) |
| `b` | British English | `en-GB`, `en-IE`, `en-AU`, `en-NZ` | `bf_emma` (B-) | `bm_george`, `bm_fable`, `bf_isabella`... (8) |
| `e` | Spanish | `es` | `ef_dora` | `em_alex`, `em_santa` |
| `f` | French | `fr` | `ff_siwis` (B-) | (only one) |
| `h` | Hindi | `hi` | `hf_alpha` | `hf_beta`, `hm_omega`, `hm_psi` |
| `i` | Italian | `it` | `if_sara` | `im_nicola` |
| `j` | Japanese | `ja` | `jf_alpha` | `jf_gongitsune`, `jf_nezumi`, `jf_tebukuro`, `jm_kumo` |
| `p` | Brazilian Portuguese | `pt` (also `pt-PT`) | `pf_dora` | `pm_alex`, `pm_santa` |
| `z` | Mandarin Chinese | `zh` | `zf_xiaobei` | 7 more `zf_` / `zm_` |

A video `language:` Kokoro does not speak (German, say) without `lang` / `voice` is a config error.
`j` needs `pip install "misaki[ja]"`, `z` `pip install "misaki[zh]"` besides the extra. `e`, `f`,
`h`, `i`, `p` are read through espeak-ng (and English uses it for words missing from its
dictionary); misaki loads the espeak-ng library bundled in the `espeakng-loader` wheel (Windows,
Linux, macOS), so no system package is needed normally.

**First run: downloads.** The model is fetched from Hugging Face the first time: `kokoro-v1_0.pth`
(327 MB, SHA256 `496dba11...`) plus ~0.5 MB per voice used, into the Hugging Face cache
(`~/.cache/huggingface/hub`, on Windows `%USERPROFILE%\.cache\huggingface\hub`; `HF_HOME` or
`HF_HUB_CACHE` move it). English voices also make misaki install spaCy's `en_core_web_sm`
(12.8 MB) with pip on first use. vidgen bundles none of these. After that no network is needed
(`HF_HUB_OFFLINE=1` makes sure nothing is asked). `vidgen tts --dry-run` says whether the
download is still to come.

**Speed.** The model loads once per `vidgen tts` run (one pipeline per language, all voices
sharing it): a few seconds to import PyTorch and ~6-10 s to load the model and the English
phonemizer. Then, measured on a 2-core cloud CPU, a 12-word sentence (4.8 s of speech) took 3.6 s
and a 2-word line 1.1 s: about 0.7x real time, so a 5-minute narration takes ~4 minutes. A laptop
CPU is usually faster, a GPU much faster.

**Python.** The `kokoro` package (0.9.4) declares Python 3.10-3.12. On 3.13 the extra installs
nothing and `vidgen tts` prints a command that installs it anyway (it worked on 3.13 here): `pip
install --ignore-requires-python "kokoro>=0.9.4" "misaki[en]>=0.9.4" "spacy>=3.8,<4"
"spacy-curated-transformers<0.4"`.

**Word timings.** For English (`lang` a / b) Kokoro says when each word is spoken: vidgen stores
them as `audio/<beat_id>.align.json` for every beat (free, so `timestamps` is not needed) and
burned-in [`captions`](#captions) and the SRT time every word from them (through the
pronunciation, as with ElevenLabs). Other languages have no timings: word times are estimated
within each MP3's speech (`timestamps: true` there is a `vidgen validate` warning).

**Same rules as the other providers.** One provider per video: a named voice may change `voice`,
`speed` and `lang` (a named voice that sets `voice` gets that voice's language unless it sets
`lang`); a [variant](#variants) may switch the whole video to Kokoro (`variants: {local: {voice:
{provider: kokoro}}}`, own `audio/<variant>/`). Audio goes to `audio/<beat_id>.mp3` (Kokoro's 24
kHz samples encoded with ffmpeg, 128 kb/s) + `.hash`; the hash covers the spoken text
(pronunciation applied) and `provider`, the model (`hexgrad/Kokoro-82M`, `kokoro-v1_0.pth`),
`voice`, `lang` and `speed` (not `device`), and a beat's [emotion](#voices-with-feeling-emotion)
when it has one: changing any of them re-voices that voice's beats.
No neighbouring-beat context. Readback and the narration-speed lint work on its MP3s as on any.

**Cost.** None: the dry run says `cost: free (local): Kokoro-82M runs on this computer`, `tts
--json` has `estimated_cost: 0`, `unknown_cost: 0`, and each beat / voice `provider: kokoro`,
`model: hexgrad/Kokoro-82M`, `provider_voice`, `speed`, `lang`, `device`. Over MCP, `tts` with
`dry_run: false` needs no `confirm_cost` for a Kokoro project (it is still asked for when the
project does not load, or uses another provider).

**Checks.** `vidgen validate` warns (no network, nothing loaded) about a voice not in the bundled
list (with a suggestion), a voice of another language than `lang` ("`bf_emma` is a British
English voice but lang is a"), a `lang` that is not the video's language, `timestamps` with a
language without timings, and the extra (or `misaki[ja]` / `[zh]`) not installed. `vidgen tts`
refuses with the install command when the extra is missing, names espeak-ng when it cannot be
loaded, and says what failed when the first download cannot reach Hugging Face.

**Choosing.** ElevenLabs still sounds the most natural and expressive (and uses neighbouring
beats for intonation); Kokoro is clear and pleasant in English (`af_heart`, `af_bella`,
`bf_emma`), thinner in the other languages, weaker on very short lines (under ~10 words) and may
rush very long ones. It is ideal for drafts, internal videos and projects with no budget, and
costs nothing to re-voice while a script changes.

### Voices with feeling (`emotion`)

Kokoro reads every line in the same even tone. `emotion:` on a beat says how the line feels, and
`vidgen tts` changes how it is spoken (ElevenLabs and OpenRouter: an audio tag, voice settings
or an instruction, [below](#emotion-with-elevenlabs-and-openrouter)). With Kokoro: the speed (Kokoro's own speed control), the pitch (a shift
in semitones by ffmpeg after synthesis that keeps the length), the loudness (gain in dB; a boost
is soft-limited so it never clips) and the pauses at commas and full stops inside the line.

```yaml
voices:
  pip: {voice: af_bella, emotion: happy}     # pip's default feeling (not inherited by other voices)
scenes:
  - id: storm
    type: stage
    beats:
      - {text: "Rain! Grab the basket!", voice: pip, emotion: excited}
      - {text: "Our sandwiches are soup.", voice: pip, emotion: sad}
      - {text: "Quick, under the tree.", emotion: {like: whisper, gain: -6}}   # a row with changes
```

| `emotion` | speed | pitch (semitones) | gain (dB) | pauses |
|---|---|---|---|---|
| `neutral` | 1 | 0 | 0 | 1 |
| `happy` | 1.05 | +1 | +1.5 | 0.9 |
| `excited` | 1.12 | +2 | +3 | 0.7 |
| `sad` | 0.86 | -1.5 | -3 | 1.5 |
| `angry` | 1.06 | -0.5 | +3 | 0.8 |
| `worried` | 1.04 | +0.7 | -1.5 | 1.3 |
| `scared` | 1.1 | +1.5 | -1 | 1.2 |
| `surprised` | 1.04 | +2.5 | +2 | 1 |
| `calm` | 0.93 | -0.5 | -1.5 | 1.2 |
| `doubtful` | 0.92 | -0.3 | -1 | 1.4 |
| `sleepy` | 0.8 | -2 | -4 | 1.6 |
| `whisper` | 0.92 | -1 | -9 | 1.2 |
| `shout` | 1.06 | +2.5 | +5 | 0.8 |

- **Where it comes from**: the beat's `emotion`, else its voice's (`voice.emotion` for the
  narrator, `voices.<name>.emotion` for a speaker — a character's default through its voice). A
  named voice does not inherit the base voice's `emotion`; a beat's `emotion: neutral` speaks a
  line plainly in a voice that has one.
- **The mapping form** `{like, speed, pitch, gain, pauses}` starts from the row `like` (default
  `neutral`) and changes the numbers given: `speed` 0.5-2 (times the voice's `speed`), `pitch`
  -3 to 3, `gain` -12 to 6, `pauses` 0.25-3.
- **Pauses**: above 1, silence is added in the middle of each pause at `,` `;` `:` `—` and
  `.` `!` `?` `…` inside the line, `pauses - 1` times the longer of Kokoro's own pause and a
  narrator's usual one (0.2 s at a comma, 0.4 s after a sentence), so `sad` (1.5) adds 0.1 s at a
  comma and 0.2 s after a sentence; below 1, the middle of Kokoro's pause is cut. The pause after
  the last word is the beat's padding (`narration.pad`), not changed. Pauses use Kokoro's word
  timings, so they change in English (`lang` a / b) only; the other numbers work in every language.
- **Timings and lip sync**: the word timings (`.align.json`, karaoke captions) and the
  phonemes of the [viseme track](#lip-sync) move with the edited pauses; the pitch shift keeps
  the length, so nothing else moves.
- **Audio hash**: a beat with an emotion has the emotion's name and its four numbers in its hash
  (changing them re-voices that beat only); a beat without one, or with `neutral`, keeps its
  hash, so existing audio stays up to date.
- **Measured** (`af_heart`, a 15-word line, 2026-10-13): neutral 5.20 s, 202 Hz, -25.7 LUFS;
  `excited` 4.85 s, 228 Hz, -22.7 LUFS; `sad` 6.16 s, 185 Hz, -28.9 LUFS, comma pause 0.05 →
  0.15 s; `whisper` 5.69 s, 189 Hz, -34.7 LUFS; `shout` 5.00 s, 232 Hz, -20.7 LUFS; `sleepy`
  7.01 s, 178 Hz. `whisper` is a quiet, slower, lower voice, not a breathy one (Kokoro cannot
  whisper).
- **ElevenLabs and OpenRouter** speak an emotion in their own way (below); without an
  `emotion` nothing changes, also not the audio hash.
- **Screenplays**: a manner word in brackets (`PIP (cross): ...`, `NARRATOR (whispering): ...`)
  becomes the beat's `emotion` as well as the speaker's expression: the names above and words
  such as cheerful, proud (happy), thrilled (excited), upset, crying (sad), cross, furious
  (angry), nervous, shy (worried), frightened (scared), shocked (surprised), gentle, deadpan
  (calm), puzzled, unsure (doubtful), tired (sleepy), whispers, quietly (whisper), shouting,
  yelling (shout).
- `vidgen tts --dry-run` names a beat's emotion (`would generate pip_b2.mp3 (24 chars, voice
  pip, sad)`).

#### `emotion` with ElevenLabs and OpenRouter

These providers take words or settings rather than numbers, so they use the emotion's **name**
(a mapping's `like`); its numbers count only where vidgen changes the audio itself.

| `emotion` | ElevenLabs `eleven_v3` tag | other ElevenLabs models: stability, style | OpenRouter instruction (added) |
|---|---|---|---|
| `happy` | `[happy]` | -0.10, +0.20 | Speak in a happy, warm and cheerful tone. |
| `excited` | `[excited]` | -0.25, +0.45 | Speak with excitement: energetic, upbeat and a little faster. |
| `sad` | `[sad]` | -0.15, +0.30 | Speak sadly: a soft, low and slower voice with longer pauses. |
| `angry` | `[angry]` | -0.25, +0.45 | Speak angrily: firm, tense and forceful. |
| `worried` | `[nervous]` | -0.15, +0.30 | Speak in a worried, anxious tone, a little hesitant. |
| `scared` | `[nervous]` | -0.25, +0.40 | Speak as if scared: tense, breathy and a little shaky. |
| `surprised` | `[surprised]` | -0.20, +0.35 | Speak with surprise: bright and astonished, the pitch raised. |
| `calm` | `[calm]` | +0.15, 0 | Speak calmly: relaxed, even and unhurried. |
| `doubtful` | `[thoughtful]` | -0.10, +0.20 | Speak doubtfully: unsure and hesitant, with thoughtful pauses. |
| `sleepy` | `[tired]` | +0.10, 0 | Speak sleepily: slow, low and drowsy, as if about to yawn. |
| `whisper` | `[whispers]` | -0.10, +0.20 | Whisper: speak very quietly and breathily. |
| `shout` | `[shouting]` | -0.30, +0.50 | Shout: speak loudly and forcefully, projecting the voice. |

- **ElevenLabs `eleven_v3`** (models whose id starts `eleven_v3`, the ones that read
  [voice sounds](#voice-sounds) as audio tags): the tag goes before the line's text (`[excited]
  Rain! Grab the basket!`), before any voice sound at its start; captions, subtitles and
  `vidgen readback` leave it out. The voice settings are not changed. `[whispers]` and
  `[excited]` are tags ElevenLabs documents for v3; the others are emotion words of its examples,
  and v3 reads a tag it does not list as a direction too — it may follow some of them less
  than others.
- **Other ElevenLabs models** read no tags: the text is not changed, and the voice's
  `settings` change instead — the stability (lower: more varied, more expressive) and the style
  exaggeration by the amounts above, each kept within 0-1. A beat's emotion is in its hash
  through these settings.
- **OpenRouter models that take `instructions`** (OpenAI and Gemini TTS, the ones OpenRouter
  documents them for): the sentence above is added after the voice's own `instructions`
  (`instructions: Warm narrator` → `Warm narrator. Speak sadly: ...`). The hash gains the
  emotion's name and sentence.
- **Other OpenRouter models** take no instructions: vidgen changes the returned audio with the
  emotion's numbers instead, as for Kokoro but without the pauses (OpenRouter returns no word
  timings): the speed (ffmpeg `atempo`, the pitch kept), the pitch (the length kept) and the
  loudness (a boost soft-limited). The hash gains the name, speed, pitch and gain. `vidgen
  validate` says so (`emotion: mistralai/voxtral-mini-tts-2603 takes no instructions, so the
  emotion of ... changes only the speed, pitch and loudness of the audio, not its tone or pauses`).
- **Numbers on a name-only provider**: `{like: sad, pitch: -2}` on ElevenLabs or an
  instructions model speaks as `sad`; `{like: neutral, ...}` speaks plainly. `vidgen validate`
  warns that the numbers are ignored.

## Multiple voices (`voices:`)

More than one speaker: an interview, a dialogue, a quoted voice. `voices:` names extra voices;
each is the base `voice:` with the keys it gives changed (`settings` merge value by value). A
scene's `voice:` picks one for its beats, a beat's `voice:` for itself; `default` is the base
voice (to hand a line back to the narrator inside a scene of another voice).

```yaml
voice: {voice_id: nPczCjzI2devNBz1zQrb, label: Host}   # the narrator (label: tag it in subtitles too)
voices:
  ana:
    voice_id: 21m00Tcm4TlvDq8ikWAM   # what is not given comes from voice:
    settings: {stability: 0.4}       # merged over voice.settings
    label: "Dr. Ana"                 # default: the name, first letter capital ("Ana")
    color: secondary                 # theme token or hex; default: the palette colour of its place here
subtitles:
  speakers: name                     # SRT: "Dr. Ana: ..." where the speaker changes
scenes:
  - id: interview
    type: quote
    params: {text: "Small models can be sparse too."}
    voice: ana                       # every beat of this scene...
    beats:
      - text: "We were surprised by the results."
      - text: "What surprised you most?"
        voice: default               # ...except this one: the narrator asks
      - text: "That the small models were sparse too."
```

| key (`voices.<name>`) | default | |
|---|---|---|
| `voice_id`, `model_id`, `output_format` | the base voice's | as in [`voice:`](#voice-voice) (ElevenLabs videos) |
| `model`, `voice`, `instructions`, `speed` | the base voice's | as in [narration providers](#narration-providers) (OpenRouter videos) |
| `provider` | the base voice's | only the base voice's: one provider per video (another one is an error; a variant may switch it) |
| `settings` | the base voice's | `stability`, `similarity_boost`, `style`, `use_speaker_boost`; each one not given is the base voice's |
| `context`, `timestamps` | the base voice's | as in [`voice:`](#voice-voice) |
| `label` | the name (`dr_ana` → `Dr ana`) | the speaker's name in subtitles and captions; not inherited from `voice.label` |
| `color` | palette colour by position | the speaker's colour in captions (`speakers: color` / `both` / the `name` tag); not inherited |
| `emotion` | none | how this speaker's beats feel unless a beat says otherwise ([voices with feeling](#voices-with-feeling-emotion)); not inherited from `voice.emotion` |
| `dub` | none | this speaker's voice in other languages (`{pt: pf_dora}`); without one: the base voice's when this voice keeps it, else chosen automatically ([dubbing](#dubbing-dub---all-languages)) |

- **Names**: letters, digits and `_`; `default` is reserved for the base voice. An unknown name in
  a scene or beat is a config error with a suggestion (`scenes[2].beats[1].voice: unknown voice
  'anna'; did you mean 'ana'?`); a voice no beat uses is a `vidgen validate` warning, an unknown
  colour token an error. `vidgen validate` prints `voices: default (12 beats), ana (4 beats)`.
- **Audio**: each beat is hashed with its own voice (see [narration audio](#narration-audio-elevenlabs)),
  so beats of the base voice keep their hash when `voices:` is added, editing one voice re-voices
  only its beats, and moving a beat to another voice re-voices that beat. `label` / `color` are
  not part of the audio.
- **Context**: with `context: true` a beat gets its neighbours' text as `previous_text` /
  `next_text` only when they are spoken by the **same voice**; at a change of speaker it gets none.
  ElevenLabs uses the context as this voice's own surrounding speech (to stitch generations of one
  speaker smoothly), so another speaker's line there could carry its intonation over (an answer
  read with the question's rising tone). Lines of one speaker separated by another's reply are not
  joined either: the turn breaks the flow, as in a real conversation.
- **`vidgen tts --dry-run`** shows the voice of every beat (`would generate s2_b1.mp3 (48 chars,
  voice ana)`) and the beats and characters per voice; `vidgen tts --voice ana` (repeatable;
  `default` for the base voice) generates only that speaker's beats.
- **Variants** deep-merge `voices:` like any mapping (`variants: {fr: {voices: {ana: {voice_id:
  ...}}}}` changes one speaker); a variant gets its own audio folder as soon as one shared beat's
  effective voice differs, and copies every unchanged beat from `audio/`.
- **Subtitles / captions**: `subtitles.speakers: name` writes `Label: ` before the first cue of
  each beat whose voice differs from the beat before (the first beat included) and that has a
  label (named voices always do; the base voice only with `voice.label`); `off` (default) writes
  the text only. Burned-in [`captions`](#captions) follow it, or set their own `speakers` (`name`,
  `color`, `both`, `off`).
- **Pronunciation** is one dictionary for all voices (the hash covers each beat's spoken text and
  its voice); there are no per-voice entries yet: write a variant (`pronunciation:` in it) when a
  voice of another language needs other spoken forms.

## Characters (`characters:`)

Cartoon characters, declared once at the top level and used by any scene that draws characters:
the [`stage`](#stage) scene type, or an extension's scene type with a `CharacterName` param (see
docs/EXTENDING.md). Each one is a figure made of named parts (head, eyes, brows, mouth, body, two
arms, legs) that can be posed one by one; a generated character's arms and legs bend at the elbow
and the knee ([Bending arms and legs](#bending-arms-and-legs)). Only original characters: nothing that imitates a known
character, mascot or brand figure.

```yaml
voices:
  ana: {voice_id: 21m00Tcm4TlvDq8ikWAM}
characters:
  - name: pip
    voice: ana                 # who speaks for pip: a name from voices: (or default)
    look: {body: bean, hair: short, eyes: round, nose: dot, accessories: [glasses, scarf], seed: 3}
    colors: {skin: "#C68B59", clothes: accent}
  - name: rex                  # no voice: rex does not speak; the default look
```

| key (`characters[]`) | default | |
|---|---|---|
| `name` | required | the name scenes use (letters, digits, `_`); unique |
| `voice` | none | who speaks for the character: a name from [`voices:`](#multiple-voices-voices) or `default` (the base voice); none: the character does not speak |
| `look` | `{}` | how the character is drawn (the generator's parameters, below); `{}`: a round head on an oval body |
| `colors` | see below | colours of the parts: theme tokens or hex |
| `poses` | `{}` | the character's own poses: name -> part -> settings ([below](#poses-and-expressions)) |
| `expressions` | `{}` | the character's own expressions, like `poses` |
| `idle` | `true` | breathe, sway the head slightly and blink every 2 to 6 s on its own ([below](#idle-motion)); `false`: hold still between actions |
| `cartoon_motion` | none (the scene's, else the video's: `lively`) | this character's [animation principles](#animation-principles-cartoon_motion): `lively`, `calm` or `none`; wins over the scene's and the video's |

The **generator** draws every character from simple shapes (circles, ellipses, rounded
rectangles, polygons, lines), so each figure is an original drawing:

| key (`look`) | default | |
|---|---|---|
| `body` | `round` | body shape: `round`, `tall`, `square`, `bean`, `pear` (narrow shoulders, wide hips), `triangle` (broad shoulders) |
| `head_size` | `1.0` | head size relative to the default head, 0.6 to 1.6 |
| `eyes` | `dot` | `dot`, `oval` or `round` (white with a pupil), `sleepy` (half closed) |
| `nose` | `none` | `none`, `dot`, `round`, `triangle` |
| `hair` | `none` | `none` (bald), `short`, `spiky`, `long`, `bun`, `curly`, `ponytail`, `braids`, `afro` (colour `colors.hair`) |
| `ears` | `none` | `none`, `round`, `pointy`, `floppy` (skin colour); with or without hair |
| `facial_hair` | `none` | `none`, `moustache`, `beard` (with a moustache; the mouth stays seen); colour `colors.hair` |
| `accessories` | `[]` | any of `glasses`, `hat`, `cap`, `bow` (worn on the head), `scarf`, `bag`, `backpack`, `necklace` (on the body), and the [costume pieces](#robots-and-costumes) `crown`, `wizard_hat`, `party_hat` (on the head) and `cape`; each at most once, and only one of `hat`, `cap`, `crown`, `wizard_hat`, `party_hat` |
| `proportions` | `adult` | `adult`, `kid` (a big head on a short body and legs), `tall_kid` (lankier, a smaller head than a kid's); the figure is as tall as any other, so make a kid smaller with the stage's `scale` (about 0.7 for a `kid`, 0.85 for a `tall_kid`) |
| `outfit` | `plain` | what it wears: `plain` (one colour all over), `dress` (short sleeves, a skirt), `overalls` (over a shirt in `colors.trim`), `coat` (long sleeves, tails, trousers in `trim`), `shorts` (a top, short sleeves, shorts in `trim`), `apron` (in `trim`, over plain clothes) |
| `pattern` | `none` | `none`, `stripes`, `dots` on the clothes of the body (and a skirt), in a darker tone of a light cloth or a lighter tone of a dark one |
| `shoes` | `none` | `none`, `shoes`, `boots` (colour `colors.accessory`) |
| `species` | `human` | `human`, or an animal: `cat`, `dog`, `bird`, `bear`, `rabbit`, `mouse`, `fox`, `owl`, `frog`, `turtle`, `penguin`, `snail` ([Animal characters](#animal-characters-species)); an animal draws its own ears, nose and muzzle, so `ears`, `nose` and `facial_hair` are not given with it; or `robot` ([Robots and costumes](#robots-and-costumes); no `hair` either) |
| `robot` | none | `species: robot` only: `{head: box \| round, face: eyes \| screen, antenna: true \| false, moves_on: legs \| wheels}`; default a box head, eyes, an antenna, legs |
| `seed` | none | a number that varies the proportions (head, body, legs, arms, eye gap and size, mouth) by up to 8 %; the same look and seed always give the same figure; none: no variation |
| `svg` | none | an SVG file (relative to the project folder) drawn instead of the generator, split into parts by element ids ([below](#characters-from-svg-files)); the other `look` keys and `colors` do not apply |

| key (`colors`) | default | |
|---|---|---|
| `skin` | `secondary` | head, ears, a `round` / `triangle` nose and hands (skin); an animal's fur or feathers (its muzzle and inner ears are tints of it); a robot's plating (head, limbs; its face plate a tint of it) |
| `clothes` | `primary` | body, arms and legs (and the hat band); with an `outfit`, the outfit's main cloth |
| `outline` | `"#1F2430"` | outline of every part, and the glasses |
| `features` | `"#1F2430"` | eyes, brows, mouth and a `dot` nose |
| `hair` | `accent` | hair, moustache and beard; a `turtle`'s shell |
| `accessory` | `highlight` | hat, cap, bow, scarf, bag, backpack, necklace, the costume pieces (crown, wizard hat, party hat, cape) and shoes; a robot's antenna light |
| `trim` | `dim` | the outfit's second cloth: the shirt under `overalls`, the trousers under a `coat`, the `shorts`, the `apron` |

`outline` and `features` default to a fixed dark ink, not a theme token: no token is dark in every
theme preset. The outline width follows the character's size on screen (about 0.5 % of the
frame's shorter side for a character 3/8 of it tall), and is never thinner than one pixel.

**Clothes follow the limbs**: sleeves are drawn on the arm segments (a `dress` or `shorts` has
short sleeves: bare forearms), trouser legs on the leg segments (`shorts` cover the thighs), shoes
on the shins, so they bend at the elbow and knee with them. A `dress`'s skirt and a `coat`'s tails
hang from the body, so the legs walk under them; when the character sits (`sit_on`, or the
`sitting` pose) the body shows its `seated` shape, the cloth lying over the lap. Hanging hair and
accessories trail in the [wind](#wind-wind) (a ponytail, braids, a cap, a necklace's pendant, as long
hair, a bun, the scarf and the hat do). [Effect symbols](#effect-symbols-effect) go by the head,
not by an afro or a beard round it, and above an afro, a hat or a cap.

![The looks vidgen screenplay gives, and a kid, from the side and the front](gallery/media/looks.png)

#### Animal characters (`species`)

`look.species` draws an original animal instead of a person: `cat`, `dog`, `bird`, `bear`,
`rabbit` or `mouse`. Each is a plain, generic animal built from the same simple shapes, in your
colours (`colors.skin` is its fur or feathers): it changes the head (its shape, the ears or a
bird's crest, a muzzle, a dog's or mouse's snout, a bird's beak, the nose and whiskers), the hands
(round paws; a bird's arms are wings) and a bird's bare shins (thin, with toes), and adds a
**`tail`** part behind the body (a cat's long curve, a dog's short one, a mouse's long thin tail,
a bear's round stub, a rabbit's puff, a bird's fan of feathers). Everything else is the same as
for a person: bodies, outfits, hair, accessories, poses, gestures, walking, sitting, the front view
and effect symbols. Pick natural fur colours or theme tokens, and vary them between characters.

```yaml
characters:
  - name: tib
    look: {species: cat, eyes: oval, outfit: overalls}
    colors: {skin: "#9C8E80", clothes: primary, trim: "#E7E1D5"}
  - name: wren
    look: {species: bird, eyes: round, outfit: shorts}
    colors: {skin: "#5E86B5", clothes: "#E7E1D5", trim: "#8C5A3C"}
```

- **Talking**: the mouth sits on the muzzle or under the snout, smaller, with every
  [lip-sync](#lip-sync) shape; a bird talks with its beak (it opens more for `A` and `O` than for
  `E` or `F`, and shuts for `M`). Expressions work as on people (a sad bird frowns at the corner
  of its beak).
- **The tail** swings on a spring as the animal sets off, stops or jumps (follow-through, with
  `cartoon_motion`), swings with its steps while it walks, swishes a little while it idles, and
  trails in the [wind](#wind-wind) (long tails, a bird's feathers; a rabbit's or bear's round tail
  does not). An own pose or a [keyframe](#keyframes-and-motion-paths) can turn it: part `tail`
  (`tib.tail`).
- [Effect symbols](#effect-symbols-effect) go by the head, not the ears or the snout, and above
  tall ears.
- Voices: an animal has no voice kind of its own (any voice suits it) unless you state one
  (`voice_kind:` or a pronoun in a [screenplay](#cartoons-from-a-screenplay-vidgen-screenplay)).

![The six animals from the side and the front](gallery/media/animals.png)

Six more species have bodies and moves of their own:

- **`fox`**: tall pointed ears with a light lining, a long snout with a dark nose at its tip (from
  the front a light muzzle and cheek ruffs), a bushy tail with a light tip.
- **`owl`**: two feather tufts on top, big eyes (larger and set apart) in light discs, a short
  beak it talks with, wings for arms, thin shins with toes when they are bare, a short fan of tail
  feathers.
- **`frog`**: a wide, flat head with the eyes high in bulges above it, a wide mouth, long legs
  and flat feet with round toe pads; no tail. It jumps higher: a `jump` without `height` goes
  0.72 of its height (others 0.4).
- **`turtle`**: a small head with a light chin, short legs and a shell on its back
  (`colors.hair`, drawn behind the body: a dome with plates from the side, its rim round the body
  from the front), a short pointed tail. It walks slowly with short steps: `walk_to`, `run_to`,
  `enter` and `exit` without `speed` go at 0.4 of the usual speed.
- **`penguin`**: a light face patch, a beak it talks with, flippers for arms, short legs with flat
  orange feet. It waddles, rocking from foot to foot with short quick steps, at 0.7 of the usual
  speed.
- **`snail`** (Step 155): two feelers with round knobs on top of the head (they sway in the
  wind), shorter legs and arms, and a round spiral shell high on its back (`colors.hair`, drawn
  behind the body: a spiral from the side, its rim round the shoulders from the front); no tail.
  It is the slowest walker: 0.35 of the usual speed, with short gliding steps. A good grumpy
  [blocker](#story-props-on-a-level-keys-doors-coins-stars-blockers) on a platform level.

A `speed` or `height` you give is used as it is. Lip sync, expressions, effect symbols (above the
ears, tufts or eye bulges), sitting, the front view and the wind work on all of them (a fox's
tail, an owl's tufts and feathers trail).

```yaml
characters:
  - name: rusk
    look: {species: fox, eyes: oval, outfit: overalls}
    colors: {skin: "#C8642B", clothes: "#8FA35A", trim: "#E7E1D5"}
  - name: shelby
    look: {species: turtle, eyes: oval}
    colors: {skin: "#9DB06B", hair: "#7A5C3E", clothes: "#E8D44D"}
```

![The fox, owl, frog, turtle and penguin from the side and the front](gallery/media/more_animals.png)

#### Robots and costumes

`species: robot` draws a friendly, original robot from the same simple shapes, built the way
`look.robot` says:

| key (`look.robot`) | default | |
|---|---|---|
| `head` | `box` | `box` (a rounded box) or `round` (a ball), on a short neck with a round bolt on each side |
| `face` | `eyes` | `eyes`: the look's `eyes`, brows and mouth on a light face plate; `screen`: a dark screen on which the eyes, brows and mouth glow (mint), so its [lip-sync](#lip-sync) shapes, blinks and expressions show on the screen |
| `antenna` | `true` | an antenna on a coil spring with a light on top (`colors.accessory`): it tips back and springs on as the robot sets off, stops or jumps (with `cartoon_motion`), wobbles and blinks its light while it idles, and trails in the [wind](#wind-wind); part `antenna` (`zed.antenna`), shapes `default` and `dim` (the light off) |
| `moves_on` | `legs` | `legs`: it walks with stiff knees and elbows; `wheels`: each leg ends in a wheel and it rolls (legs and arms still, no footsteps) on `walk_to`, `run_to`, `enter` and `exit` |

Its plating is `colors.skin` (head, arms, legs), its casing `colors.clothes` (the body, with a
small panel of lights on the chest); the joints show as bolts at the shoulders, elbows and knees,
the hands are round grippers and the feet blocks. Outfits, patterns, shoes (not on wheels) and
accessories work as on people (a plain outfit leaves the limbs in the plating); `hair`, `ears`,
`nose` and `facial_hair` are not given with a robot. Poses, gestures, sitting, the front view,
effect symbols (above the antenna) and voices work as for everyone. A robot speaks with any voice;
the voice sound [`[beep]`](#voice-sounds) gives it a "bee-boop" at the start or end of a line.

```yaml
characters:
  - name: zed
    look: {species: robot, robot: {face: screen, moves_on: wheels}, eyes: oval}
    colors: {skin: "#A7B4C2", clothes: "#4A7BD0", accessory: "#F2C14E"}
  - name: bolt
    look: {species: robot, robot: {head: round}, body: square, accessories: [party_hat]}
```

**Costume pieces** are accessories any character may wear (people, animals and robots), drawn in
`colors.accessory` with trimmings in `colors.clothes`, from the side and the front:

- `crown`: a band with points and gems (worn on top of the head);
- `wizard_hat`: a wide brim, a tall cone whose tip bends back, a band and two stars; it trails in
  the wind;
- `party_hat`: a narrow striped cone at a slant with a pompom; it trails in the wind;
- `cape`: hangs from the shoulders behind the body to about the knees (a clasp at the throat;
  from the front its darker inside shows beside the body); part `cape` (`ida.cape`): it swings back
  on a spring as the character sets off, falls or stops (with `cartoon_motion`), flutters back with
  each step and trails far in the wind.

Only one piece goes on top of the head: `hat`, `cap`, `crown`, `wizard_hat` and `party_hat` exclude
each other (a config error); glasses, a bow, a scarf and a cape go with any of them.

![Robots (box, screen, round and on wheels) and the costume pieces, from the side and the front](gallery/media/robots.png)

**A quick look**: `vidgen character NAME` prints the character's look and colours (each token
with the colour it resolves to); `--png [FILE]` also writes one still of it on the theme
background, in the video's aspect ratio with its shorter side 720 px (default file:
`exports/character_<name>.png`; `--facing left` mirrors it, `--facing front` shows its
[front view](#walking-in-depth-and-the-front-view); `--variant NAME` applies a variant).

**Character sheet**: `vidgen character-sheet [NAME] [PROJECT]` draws every pose (the whole
figure, rest face), every expression and every mouth shape (close-ups of the head) of a
character on one labelled PNG, facing right, on the theme background, and last a generated
character's front view (section kind `view`):
`exports/character_sheet_<name>.png` (`--output FILE` with a NAME). Without NAME it writes one
sheet per character; `--all PROJECT` does that for a project in another folder. The character's
own poses and expressions are marked `*`. Rows hold up to 8 cells of 128 px, so a generated
character's sheet is 1148 x 1082 px and about 35 to 45 KB (a 64-colour PNG), readable as it is by an AI
agent's image viewer. `--variant NAME`, `--json` (below); over MCP the `character_sheet` tool
returns the sheets as pictures. Use it to check a character before writing its scenes.

- **Checks**: two characters with the same name, a `voice` that is not in `voices:` (nor
  `default`) and an unknown key are config errors (`characters[0].voice: unknown voice 'anna';
  did you mean 'ana'?`); `vidgen validate` also reports a colour that is not a theme token or hex
  colour, and a scene param naming a character that is not declared (`unknown character 'pop';
  did you mean 'pip'? characters: pip, rex`).
- **Renders**: editing `characters:` renders every scene again (it is part of each scene's
  fingerprint, like the theme).
- **Variants** replace the whole `characters:` list (lists are not merged).

### Poses and expressions

Every character knows the same named **poses** (`stand`, `pointing`, `waving`, `thinking`,
`shrug`, `arms_crossed`, `sitting`), which set the body, legs, arms, head and accessory, and
**expressions** (`neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`, `thinking`,
`laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`, `frightened`), which set the eyes, brows
and mouth (and the `cheeks` and `bristles` of a generated character, below); a pose and an
expression combine. A change from one to another is
animated part by part: each part turns, scales or slides about its pivot with its own easing,
body first and face last (not a cross-fade). Parts a character does not have are skipped, so the
names work on generated and SVG characters alike (an SVG without `brows_angry` frowns with its
brows lowered only). `vidgen character NAME` lists the names a character knows.

A character may add its own, or replace a built-in one of the same name:

```yaml
characters:
  - name: pip
    poses:
      bow: {body: {angle: -20}, head: {angle: -10}}        # tilt forward
      waving: {arm_right: {angle: -150}}                   # pip waves with the other arm
    expressions:
      smug: {mouth: {shape: [grin, smile], scale: [1.2, 0.6]}, brows: {angle: 10}}
```

| key (each part of a pose or expression) | default | |
|---|---|---|
| `angle` | `0` | degrees counterclockwise about the part's pivot, as drawn facing right (facing left mirrors it); arms hang down at rest, so `90` points the near arm (`arm_left`) forward |
| `scale` | `1` | one factor or `[x, y]` about the pivot; negative flips the part (`[1, -1]` turns the smile into a frown); `0` is an error |
| `shift` | `[0, 0]` | `[x, y]` in character units (1 = the character's height) |
| `shape` | none | the shape shown (`open`, `closed`, `A`, ...): a name, or a list of names of which the first the character has is used; none: the rest shape |

A pose may name `body`, `legs`, `leg_left`, `leg_left_lower`, `leg_right`, `leg_right_lower`,
`arm_left`, `arm_left_lower`, `arm_right`, `arm_right_lower`, `head`, `accessory`, `tail` (an animal's), `antenna` (a robot's),
`cape`; an expression
`eyes`, `brows`, `mouth`, `cheeks`, `bristles` (anything else is a config error). Parts of its group a pose or an
expression does not name go back to their rest pose. Generated characters have the shapes eyes
`open` / `closed` / `laughing` (closed in arcs) / `wide` (a big white, a small pupil) / `swirl` /
`swirl_turned`, brows `default` / `angry` / `sad`, mouth `smile` / `open`, the lip-sync shapes
`A E O U M F L W` ([below](#lip-sync)) and `laugh` / `tongue` / `wavy`, cheeks `none` (nothing
drawn, the rest) / `blush` / `tears` / `tears_running`, and bristles `none` / `up` (behind the head:
hair standing on end, fur or feathers on an animal, fright lines over a bald head, a frog, a
turtle or a robot); a beak, a screen face and a muzzle draw each in their own way. An SVG character
has the shapes its file names (`vidgen character NAME` lists them; no `cheeks` or `bristles`, so
the new expressions fall back: `laughing` closes its eyes, `frightened` widens them). `vidgen validate` reports a
`shape` the character does not have (none of the choices), and warns about a part it lacks.

The six expressions added in Step 125 (DESIGN.md §69.59):

| expression | face | while idling (`idle: true`) |
|---|---|---|
| `laughing` | eyes `laughing`, mouth `laugh` (open, a tongue inside), brows up | the shoulders bounce |
| `blushing` | cheeks `blush`, a small smile, eyes a little lowered | |
| `tongue_out` | eyes `laughing`, mouth `tongue` | |
| `crying` | eyes squeezed (`laughing` flipped), mouth open, cheeks `tears` (streams from the eyes) | the shoulders bounce (sobs); the tears run |
| `dizzy` | eyes `swirl`, mouth `wavy` | the body sways from the hips (the legs stay upright), the head lags; the swirls turn |
| `frightened` | eyes `wide`, brows raised, mouth `wavy`, bristles `up` | the body shivers; a robot's antenna springs up |

The motion comes from the shapes shown (own expressions get it too: `eyes: {shape: swirl}`
sways), grows in and dies away on a spring, and is not part of the pose; closed eyes (`closed`,
`laughing`, `swirl`) never blink. A speaking character keeps the expression's eyes while its
mouth follows the words, and between words shows the expression's mouth (laughing while
talking). The `tear` effect symbol ([effects](#effect-symbols-effect)) is one drop beside the head; the
`crying` streams are on the face.

### Lip sync

A speaking character's mouth follows its words. For a video with `characters:`, `vidgen tts`
stores next to each beat's MP3 a **viseme track** (`audio/<beat>.visemes.json`): which of nine
mouth shapes shows when, from the sounds of the spoken text (pronunciation applied).

| viseme | sounds | generated mouth | SVG shapes tried, in order |
|---|---|---|---|
| `rest` | silence | the mouth the expression shows | the mouth's rest shape |
| `A` | a, i as in "eye", the schwa | wide open | `A`, `open` |
| `E` | e, ee, i as in "sit", and most consonants (t, d, s, z, k, g, n, r, sh, ch, j) | wide, flat | `E`, `A`, `open` |
| `O` | o, aw | round | `O`, `A`, `open` |
| `U` | oo, u | small round | `U`, `O`, `W`, `open` |
| `M` | m, b, p | closed lips | `M`, else the rest shape |
| `F` | f, v | a thin line | `F`, `E`, `M`, else the rest shape |
| `L` | l, th | open | `L`, `E`, `A`, `open` |
| `W` | w, q | puckered | `W`, `U`, `O`, `open` |

- **Where the sounds come from**: Kokoro's own phonemes when Kokoro voiced the beat; else
  [misaki](https://github.com/hexgrad/misaki) or the `espeak-ng` program when installed (misaki
  for English needs spaCy's `en_core_web_sm`; nothing is installed for you); else the letters of
  the words (`th` -> `L`, `ph` -> `F`, `oo` -> `U`, a silent final `e` dropped in English and
  French).
- **When**: the word timings the captions use (ElevenLabs timestamps, Kokoro's `.align.json`,
  else an estimate within the MP3's speech). Shapes shorter than 0.07 s are merged into the
  longer neighbour so the mouth does not flicker; a short `M` is lengthened instead, so lips
  still close.
- The track belongs to the MP3 and the spoken text it was made for (their hash is stored in it);
  a re-voiced or edited beat gets a new one with its audio. Audio voiced before the video had
  characters gets its tracks on the next `vidgen tts` (no new audio, nothing billed). A beat with
  no current track is timed from its text when the scene is drawn.
- Editing a track (or a beat's alignment) re-renders the scenes of that beat in a video with
  characters.
- Who speaks a beat on a `stage` (the characters with the beat's voice, or a `say` action) is in
  [Speaking and acting](#speaking-and-acting). The mouth is timed from the beat's start, so a
  pose change while speaking does not put it behind the audio.

### Idle motion

A character breathes (its body grows and shrinks by about 1 %), sways its head by a degree or two
and blinks every 2 to 6 seconds, so it never stands frozen. The blinks are random but repeatable:
the same character name gives the same blinks in every render. A character never blinks during a
pose or expression change, and the motion does not change its pose, expression or lip sync.
An SVG character blinks only when its file has `eyes_closed`. `idle: false` turns all of it off
for one character; a [`stage`](#stage) scene's `idle: false` turns it off for every character in
that scene.

### Bending arms and legs

A generated character's arms and legs come in two segments: `arm_left` is the upper arm (it
turns about the shoulder) and `arm_left_lower` the forearm and hand (it turns about the elbow);
the legs are `leg_left` / `leg_right` (thighs, about the hips) and `leg_left_lower` /
`leg_right_lower` (shins, about the knees). The built-in poses and gestures bend the elbows
(`pointing`, `waving`, `thinking`, `shrug`, `arms_crossed`), `sitting` bends the knees, and the walk
swings the legs one by one with the knee of the swinging leg bent, keeping a foot on the ground.
In an own pose a lower segment's `angle` is the joint's bend relative to the upper part (an
elbow `+`: the hand comes forward; a knee `-`: the foot goes back):

```yaml
characters:
  - name: pip
    poses:
      reach_up: {arm_left: {angle: 150}, arm_left_lower: {angle: 20}}
      kneel: {body: {shift: [0, -0.08]}, leg_left: {angle: 90}, leg_left_lower: {angle: -90}}
```

A character drawn in one piece (an SVG without `arm_left_lower`) still takes these settings: the
arm turns by half the elbow's bend and gets a little shorter, so its hand ends about where a
bent arm's would. Generated characters have no `legs` part any more (it was both legs in one
piece): an own pose's `legs:` does nothing on them (validate warns), use `leg_left` /
`leg_right`. Extensions can put a hand or a foot on a point (`reach`, `plant`, docs/EXTENDING.md).

### Characters from SVG files

`look: {svg: assets/sprout.svg}` draws the character from your own SVG file (or one made with a
`generate: {format: svg}` model), drawn **facing right**. vidgen sanitises it as it does an SVG
picture (scripts, filters, raster images and text are removed; gradients become one colour; see
the `image` scene) and splits it into parts by **element ids**:

| id | meaning |
|---|---|
| `body`, `legs`, `arm_left`, `arm_right`, `head`, `eyes`, `brows`, `mouth`, `accessory` | that part at rest (a group or one shape). `arm_left` is the character's own left arm: facing right it is the near arm, so draw `arm_right` behind the body |
| `arm_left_lower`, `arm_right_lower` (optional) | the forearm and hand: the arm then bends at the elbow (`arm_left` is the upper arm); without it the arm is one piece and shows a bend folded |
| `leg_left`, `leg_right`, `leg_left_lower`, `leg_right_lower` (optional) | the legs one each instead of `legs` (not both): a thigh and, optionally, a shin that bends at the knee; draw `leg_right` behind |
| `tail` (optional) | a tail (or anything that hangs from the body and swings): it swings on a spring as the figure sets off and stops, swishes while idle and trails in the wind, turning about its pivot ([animal characters](#animal-characters-species)); draw it first, behind the body |
| `antenna`, `cape` (optional) | an antenna on the head, a cape on the body (as a [robot's](#robots-and-costumes) and a cape's): each swings on the follow-through spring and an `antenna` wobbles while idle (with `antenna_dim`, its light blinks); they do not trail in the wind (nothing marks pieces in a drawing) |
| `<part>_<shape>` (`eyes_closed`, `mouth_A`, `mouth_E`, `mouth_O`, `mouth_M`, `arm_left_up`) | another shape of the part, shown when swapped in; hide it in the file with `display="none"` |
| `data-pivot="x y"` (on a part's element) | the point the part turns about, in the SVG's `viewBox` coordinates: the neck for `head`, the shoulder for an arm, the hips for `legs` / `leg_left`, the elbow for `arm_left_lower`, the knee for `leg_left_lower`, where it leaves the body for `tail` |

- A part's element takes everything inside it, except elements with another part's id (so
  `eyes` may sit inside the `head` group). An id starting with the part's own name inside its
  element (`head_outline` inside `head`) is just a piece of it. Shapes outside every named part
  make the `body` (a file without part ids is a body-only character); shapes hidden there are
  not drawn.
- The rest shape of `eyes` is called `open` and that of `mouth` `smile`, as on generated
  characters; other rest shapes are `rest`. Name the mouth shapes for speech `mouth_A` (also I),
  `mouth_E`, `mouth_O`, `mouth_U`, `mouth_M` (M, B, P), `mouth_F` (F, V), `mouth_L`, `mouth_W`
  (W, Q); any subset may be present ([lip sync](#lip-sync) uses the closest one a file has).
- Parts are drawn in the file's order. The feet are the bottom of the rest shapes, under the
  middle of the legs (else of `body`); the top of the rest shapes is the character's height.
  Without `data-pivot` the pivot is guessed from the part's box (head and body: bottom centre;
  legs, a single leg and a lower segment: top centre; an arm: its top corner nearer the body; `tail`: its bottom corner nearer the body; face parts: the centre).
- The SVG's own colours and stroke widths are drawn (`colors:` is not used); stroke widths scale
  with the character's height like a generated character's outline.
- **Missing parts are allowed**: only a body is needed. `vidgen validate` lists the actions such
  a character cannot do (no arm: no `gesture: wave` / `point` / `shrug`; no `eyes_closed`: no
  blink; no head: no `look_at`, `nod`, `shake_head`), ids that look like misspelt part names
  (`Mouth`, `arm-left`), other shapes the file shows, parts without `data-pivot` that turn, and
  what the sanitiser removed. A missing file, two elements with the same part id or a bad
  `data-pivot` are problems.
- Keep the file under `assets/`: editing it then renders the scenes again.
- `vidgen character NAME` lists the parts and shapes found; `--png` shows a still.
  `examples/svg_character` has a small example (`assets/sprout.svg`).

### A host beside any scene (`host:`)

A character of `characters:` can present an explainer: `host:` draws it beside the content of
every scene type (bullets, charts, code, diagrams, images...), and each scene lays its content
out in the room left, so the host never covers it. Its mouth follows the narration (lip sync),
and it breathes, sways and blinks like any character (its `idle:`).

```yaml
characters:
  - name: dot
    look: {body: bean, hair: bun, accessories: [glasses]}
host: dot                       # or a mapping, as below
scenes:
  - id: steps
    type: bullets
    params: {heading: "How a video is made", items: ["Write the beats", "Render a preview"]}
    beats: [{text: "First, you write the narration as short beats."}]
  - id: listing
    type: code
    host: {pose: thinking, expression: thinking}   # this scene changes these keys
    params: {path: assets/moving_average.py}
    beats: [{text: "Code listings are syntax highlighted."}]
  - id: thanks
    type: end_card
    host: false                 # no host here
    params: {title: "Thanks for watching"}
    beats: [{text: "Thanks for watching."}]
```

| key | default | |
|---|---|---|
| `character` | required | the character (a name from `characters:`) |
| `side` | `right` | the side of the content it stands on: `left` or `right` |
| `size` | by format | its height as a fraction of the frame's shorter side (0 to 0.9): 0.5 in 16:9, 0.42 in 1:1, 0.36 in 9:16; made smaller when it would take more than 95 % of the room's height beside the content (40 % below it) or a column wider than 40 % of the room |
| `place` | `auto` | `beside`: in a column next to the content, standing at its bottom; `below`: at its side of a band under the content; `auto`: below in a vertical (9:16) frame, else beside |
| `floor` | `true` | a plain line under its feet (a little wider than it); `false`: no floor |
| `floor_color` | `dim` | the floor line's colour: a theme token or hex |
| `facing` | `auto` | `auto` (towards the content: `left` on the right side), `left`, `right`, or `front` (at the viewer; an SVG character keeps its side) |
| `speaks` | `narrator` | whose lines move its mouth: `narrator` — every beat except those in another character's voice (the host speaks for the narrator, whatever voice says it); `own` — only beats in its own `voice` |
| `pose` | none | its pose (`thinking`, `arms_crossed`... or its own; none: standing) |
| `expression` | none | its expression (`happy`, `thinking`... or its own; none: its rest face) |
| `auto_direct` | the video's | [automatic host directing](#automatic-host-directing): `true` or `false`; not given: on when the video's `auto_direct` is (a beat's `auto_direct` wins) |

- **The room it takes.** The host's column (beside) or band (below) is *reserved* like an
  overlay's `reserve: true`: the scene's safe area (`self.safe_area`, every named region and
  `place()`) shrinks to the rest, a gap of 0.2 units away. Overlays that reserve room (bottom or
  top captions, a reserved lower third) are taken out first, so the host stands above a bottom
  caption band. Content therefore re-flows: lists wrap, code listings wrap long lines, charts get
  narrower.
- **Which scenes.** Every scene type built on the safe area (all built-ins except `stage`, whose
  characters stand on the set already, and `card`, a full-frame title card; both ignore the video's
  `host:`, and a scene's own `host:` on them is a problem). A project's scene type takes a host
  unless it sets `takes_host = False` ([EXTENDING.md](EXTENDING.md)).
- **Between scenes.** The host is on screen from a scene's first frame (unless a `host_enter`
  brings it in). When the next scene shows the same host unchanged (same character, side, size,
  pose, ...), it stays in this scene's fade-out, so it stands still across the cut, unless it
  walked to the other side or left in this scene; otherwise it fades out with the content.
- **Speaking.** With `speaks: narrator`, a beat in the narrator's voice (or any voice no other
  character owns) moves its mouth; a beat in another character's voice (a guest's line) leaves it
  silent. The mouth follows the beat's viseme track (stored by `vidgen tts`, else built from the
  text), timed from the scene's clock like a stage's characters. `vidgen validate` warns about
  `speaks: own` for a character without a voice.
- **Checks.** `vidgen validate`: an unknown character, pose or expression; a scene's mapping
  without `character` and no video host; `host: true` without a video host; `floor_color` not a
  theme colour. `vidgen lint`: the layout dump records the host as one object of kind `host`
  (floor line included), and `host_overlap` reports it over the scene's content, a caption or
  another overlay.
- A `zoom` or `pan` moves the host with the rest of the scene.

#### Pointing, reacting and moving (host actions)

Six beat actions act on the scene's host (the host is not a target: these name a target of the
scene, an expression or a side). They work in every scene type that draws a host; `vidgen
validate` rejects them in a scene without one, on a `stage` or `card`, and more than one host
move (`host_move`, `host_enter`, `host_exit`) in a beat.

```yaml
beats:
  - text: "Here is the first step."
    actions: [{host_point: item1, line: true}]       # the arm towards item1, and a pointer line
  - text: "And that doubled the speed!"
    actions: [{host_react: happy, effect: sparkle}]  # an expression, and a symbol over the head
  - text: "Let me stand over here."
    actions: [{host_move: other_side}]               # walk across; the content slides over
  - text: "That's all for now."
    actions: [{host_exit: right, at: 0.5}]           # walk off; host_enter brings it back
```

| action | target | options | |
|---|---|---|---|
| `host_point` | a target of the scene (`item2`, `bar:2024`, `lines:3-5`...) | `line` (`false`), `color` (`dim`) | the near arm reaches towards the edge of the target's box nearest the host and the head turns there; out of reach the arm points straight at it (the hand stays in the host's room, so it never touches the content); `line: true` adds a thin pointer line from the hand to just short of the target. Until the next beat starts (`until: <beat>`) |
| `host_look` | a target of the scene | | the head turns to the target's nearest edge; until the next beat starts |
| `host_react` | an expression (`happy`, `surprised`, `worried`... or the host's own) | `effect` (none) | the expression and, with `effect`, a [symbol](#effect-symbols-effect) over the head (`sparkle`, `exclaim`, `sweat`, `hearts`...); until the next beat starts |
| `host_move` | `other_side` (default), `left` or `right` | `speed` (2.5) | the host walks to that side and turns to the content. Beside the content its column swaps sides and **the content slides over with it** in the same beat (the camera moves, so everything the scene shows or reveals later moves together; overlays and captions stay); in a band below the content (9:16) only the host walks. It stays there for the rest of the scene; the next scene starts on its own `side` |
| `host_enter` | `left` or `right` (default: its side) | `speed` | the host walks in from beyond that edge to its place, its floor line fading in. A scene whose first host passage is a `host_enter` starts without the host (its room stays free) |
| `host_exit` | `left` or `right` (default: its side) | `speed` | the host walks out beyond that edge, its floor line fading out; its room stays free |

Write `{action: host_enter}` / `{action: host_move}` for the defaults. The layout dump's `host`
object gains `pointing_at` while it points, its `side` is where it stands now, and a pointer
line is one object of kind `pointer` (named after the host; `host_overlap` ignores it and the
host's own effect symbol).

#### Automatic host directing

With `auto_direct` on (the video's, the host's `auto_direct`, or a beat's; the nearest wins), the
host directs itself in every scene with a host:

- **Points** (kind `gestures`) at each item the scene reveals in a beat, once per item and at
  most once per beat (after the item appears).
- **Looks** (kind `looks`) at what a beat highlights (the first target of a written `highlight`,
  `callout` or `zoom`, at its `at`), else at the beat's revealed item, when it does not point.
- **Reacts** (kind `reactions`) to results, at 0.4 of the beat: a chart going up → `happy`, going
  down → `worried`, a code highlight showing an error (error, exception, traceback, fail, panic)
  → `surprised`; with kind `effects` a symbol with it (`sparkle`, `sweat`, `exclaim`).
- **Never moves**: `host_move`, `host_enter` and `host_exit` change the layout, so they are
  yours; a beat with one gets nothing automatic (and one move per beat is the most `vidgen
  validate` allows). Written host actions win: a written `host_point` / `host_look` stops the
  automatic point and look in its beat, a written `host_react` the automatic reaction.

What each scene type reveals: `bullets` an item per step (`reveal: all`: `item1`), `bar_chart` a
bar per step (`per_beat`: up or down from the bar before; `all`: the last bar, up or down from
the first), each of its `changes` (up or down as the values' sum does) and the `highlight` bar,
`line_chart` a series per step (up or down from its first value to its last) and each of its
`changes` (up or down as the lines' last values do), `code` the lines of each `highlight` entry (`listing` without highlights).
Other types reveal nothing the host reacts to (it still looks at written highlights). Everything
it adds is lint-safe by construction (the hand stays in its room; no pointer line). `vidgen
direct` and the storyboard's `auto:` lines show the added actions; `examples/host-explainer`
uses them.

## Narration (`narration:`)

```yaml
narration:
  pad: 0.35               # seconds of silence after each beat
  words_per_second: 2.6   # duration estimate for beats that have no audio yet
```

## Narration audio (ElevenLabs)

Each beat is spoken by ElevenLabs (or [OpenRouter](#narration-providers): same files, its own
key and hash) into `audio/<beat_id>.mp3`, with `audio/<beat_id>.hash`
recording what it was generated from (and, with `voice.timestamps`, `audio/<beat_id>.align.json`:
its character timings, with the text and a hash of the MP3 they belong to, so a stale file is
ignored).

**API key.** vidgen reads the key only from the environment variable `ELEVENLABS_API_KEY`;
it never stores it in the config, audio, build files, logs or error messages.

- Windows: `setx ELEVENLABS_API_KEY your_key` once, then open a new terminal.
- Linux/macOS: `export ELEVENLABS_API_KEY=your_key` (add it to your shell profile to keep it).

**Commands.**

```
vidgen tts --dry-run          # list beats that need audio + character count (no key needed)
vidgen tts                    # generate missing/stale beats only
vidgen tts --beat s2_b1       # only these beats (still skipped if up to date)
vidgen tts --voice ana        # only the beats of this voice (voices:; default = the base voice)
vidgen tts --force            # regenerate (combine with --beat to limit it)
vidgen tts --variant spanish  # audio for a variant
vidgen validate               # prints e.g. "audio: 18 ok, 2 stale, 1 missing"
```

**What triggers regeneration.** A beat is regenerated when its MP3 is missing or its hash does
not match the beat's spoken text (its text with the [pronunciation](#pronunciation-pronunciation)
applied) plus `voice_id`, `model_id`, `output_format` and `settings` of the beat's voice (its
scene's or its own from [`voices:`](#multiple-voices-voices), else `voice:`). Editing
one beat regenerates only that beat: the neighbours' text is sent for intonation but is not part
of the hash, and neither is `context`. Hash files written by the original kphi3 script are
accepted while `output_format` and `settings` keep their defaults.

**Variants.** A variant shares `audio/` unless its voice (after merging), the voice of a beat
(`voices:`, a scene's or beat's `voice:`) or the spoken text of a beat (its text, or the
pronunciation of a word in it) differs from the base config; then its
audio goes to `audio/<variant>/`. Beats that are the same in both are copied from `audio/`
instead of being paid for again.

## Pronunciation (`pronunciation:`)

How the narrator says names, acronyms and symbols the voice gets wrong. Each entry replaces a
term in the text **sent to the TTS only**: the subtitles (SRT), burned-in captions and storyboard
labels keep the written words.

```yaml
pronunciation:
  K-Phi-3: kay fye three                # short form: term: spoken form
  LaTeX: lah-tek
  SQL: {say: sequel, case_sensitive: false}     # also "sql", "Sql"
  "(\\d+)p": {say: "\\1 pee", regex: true}      # 480p -> "480 pee" (regex groups in say)
  Phi: {say: fye, whole_word: false}            # also inside "Phis", "DelPhi"
pronunciation_file: pronunciation.yaml  # optional: more entries in a file (or a list of files)
```

| key | default | |
|---|---|---|
| `say` | required | the spoken form sent instead of the term; with `regex: true`, `\1` / `\g<name>` insert a group |
| `case_sensitive` | `true` | match the term's capitals exactly (`false`: any case) |
| `whole_word` | `true` | match only where no letter, digit or `_` is right before or after the term (`K-Phi-3's` matches `K-Phi-3`, `GPUs` does not match `GPU`) |
| `regex` | `false` | the term is a Python regular expression, not plain text |
| `language` | none (every language) | only in videos of this [language](#languages-and-translations) (or list of languages): `en` matches `en-US` and a video without `language`, `pt` matches `pt-BR` and `pt-PT`, `pt-BR` only `pt-BR` |

- **Matching.** Every entry is matched against the beat's written text in one pass; a spoken form
  is never matched again by another entry. Where matches overlap, the one starting first wins,
  then the longest (`K-Phi-3` before `Phi`), then the entry written first.
- **`pronunciation_file`**: YAML or JSON files (relative to the project) holding the same mapping
  (`term: spoken form` or `term: {say, ...}`), read in order; entries of `pronunciation:` win over
  them, and `term: null` removes one (also how a [variant](#variants) drops an entry of the base
  config: variants deep-merge `pronunciation:` like any mapping).
- **Audio.** The audio hash covers the spoken text, so adding, changing or removing an entry
  re-voices only the beats whose spoken text changes; a beat that no entry matches keeps its
  hash (existing audio stays valid when a dictionary is added). `vidgen tts --dry-run` lists the
  beats to generate and, under each one whose text changed, `says: <spoken text>`.
- **Word timings.** The audio says the spoken words, the captions show the written ones: each
  written word is timed from its first spoken word's start to its last one's end (`K-Phi-3` said
  "kay fye three" lasts all three words; a term said as nothing gets a zero-length time where the
  next word starts). This holds for estimated times (the spoken syllables are weighed) and for
  `voice.timestamps` alignments (stored for the spoken text).
- **Lint.** `narration_speed` counts the words of the spoken text.
- **Per language.** A [variant](#variants) in another language overrides entries by term
  (`LaTeX: látec`), drops them (`LaTeX: null`), or the entries say which languages they are for
  (`LaTeX: {say: lah-tek, language: en}`). `vidgen validate` warns about base entries a variant in
  another language keeps unchanged.
- **`vidgen validate`** warns (it does not fail) about entries that match no beat, entries that
  never apply because a longer entry always covers them, and entries whose matches collide with
  another's (the same text, or crossing) in a beat.
- Not supported (yet): SSML `<phoneme>` / IPA entries (ElevenLabs reads them only with some
  models, and they would break the word timings) and ElevenLabs' server-side pronunciation
  dictionaries; write the spoken form as plain letters instead.

**Housekeeping.** MP3s of beats that no longer exist are reported as orphaned but never deleted.
Failed requests show the HTTP status and ElevenLabs' message; rate limits and server errors are
retried a few times automatically. Rendering uses whatever audio exists; stale or missing audio
is reported as a warning.

## Readback (`vidgen readback`)

Does the narration say what the text says? `vidgen readback [PROJECT]` transcribes every beat's
MP3 with a speech-to-text (STT) provider and compares the transcript with the beat's text. It
catches what nobody hears without listening: a name or acronym the voice mispronounces, a number
read wrongly, words the voice dropped or added, words it says unclearly or after an odd pause.
An AI author can act on the report without
listening: each difference names the written words, what was heard, and a suggested fix. A
beat's [voice sounds](#voice-sounds) are left out: the words a transcript writes for them (`ha
ha`, `hmm`) are not differences.

```yaml
stt:
  provider: faster_whisper    # faster_whisper (local, free) | elevenlabs (paid, ELEVENLABS_API_KEY)
  model: null                 # default: small.en for English, small otherwise; elevenlabs: scribe_v1
  language: null              # default: the video's language (English without one); auto: detected
  device: auto                # faster_whisper: auto | cpu | cuda
```

| key | default | |
|---|---|---|
| `provider` | `faster_whisper` | `faster_whisper`: OpenAI's Whisper run locally (CTranslate2), free, no key; needs the optional extra `pip install "schu-video-generator[stt]"`, and downloads the model from the Hugging Face Hub on first use. `elevenlabs`: ElevenLabs Speech to Text, billed per audio hour, the same `ELEVENLABS_API_KEY` as `vidgen tts` |
| `model` | none (the provider's default) | a Whisper size (`tiny`, `base`, `small`, `medium`, `large-v3`, `turbo`; `.en` sizes for English only; bigger = more accurate, slower) or a folder holding a converted model; ElevenLabs: `scribe_v1`. Default `small.en` for English, `small` otherwise; `scribe_v1` |
| `language` | none (the video's) | the language of the audio (BCP-47, its language subtag is sent: `pt-BR` → `pt`), or `auto` (detected); default the video's [language](#languages-and-translations), English without one |
| `device` | `auto` | `faster_whisper` only: `cpu`, `cuda` (an NVIDIA GPU), or `auto` (a GPU if there is one) |

```
$ vidgen readback my_video
[1/12] transcribed intro_b1 (2.1 s)
...
readback: 12 beats (faster_whisper small.en, language en); 12 transcribed, 0 cached; word error rate 2.4%
flagged (word error rate above 10%): 1
  setup_b2 (setup): 20% (2/10 words)
    expected "NVIDIA", heard "and video" @ 3.2s
    fix: "NVIDIA" is heard as "and video": add a pronunciation entry `NVIDIA: <how to say it>`, then `vidgen tts`
worst: setup_b2 20%, intro_b1 9%
terms misheard in several beats:
  NVIDIA: 2 beats (setup_b2, results_b1), heard "and video", "in video" -> "NVIDIA" is misheard in 2 beats: add a pronunciation entry `NVIDIA: <how to say it>`
words to check: 2 unclear, 1 doubtful (probability below 0.5 / 0.75, pauses over 0.5 s inside a sentence, differences)
  unclear  intro_b2 @ 1.84s (video 9.12s): "rushing" (text "Russian"), heard with probability 0.22
    fix: "Russian" is not heard clearly: add a pronunciation entry `Russian: <how to say it>` (a respelling), then `vidgen tts`
  unclear  setup_b2 @ 3.20s (video 21.40s): expected "NVIDIA", heard "and video"
    fix: "NVIDIA" is heard as "and video": add a pronunciation entry `NVIDIA: <how to say it>`, then `vidgen tts`
  doubtful results_b1 @ 0.95s (video 33.05s): "layers", heard with probability 0.61
    fix: listen to "layers": if it is slurred, change how the beat is said (another `voice:`, the voice's `speed`, an `emotion:`) or respell the word in `pronunciation:` (`layers: <respelling>`), then `vidgen tts`
```

| option | |
|---|---|
| `--variant NAME` | a variant: its audio folder and its language |
| `--beat ID` | only this beat (repeatable) |
| `--max-wer RATE` | flag beats whose word error rate is above this (0-1); default `lint.rules.readback.max_wer` (0.1) |
| `--force` | transcribe again even when a cached transcript exists |
| `--json` | the whole report as JSON (below) |

The exit code is 0 when the command ran, whatever it found (`flagged` in the JSON tells); use
the [`readback` lint rule](#lint-vidgen-lint) to fail a check on it.

**What is compared.** The transcript is compared with the beat's **spoken** text: its text with
the [pronunciation](#pronunciation-pronunciation) applied, which is what the voice was asked to
say. Differences are reported in terms of the **written** text (`expected "K-Phi-3" (said "kay
fye three"), heard "kay five three"`). Both texts are normalised first, so that differences in
writing are not counted as differences in speech: case and punctuation; accents (`você` =
`voce`: STT models drop them now and then); hyphens, dashes and slashes split words
(`one-by-one` = `one by one`); numbers become words in English and Portuguese (`2.58` = `two
point five eight`, `1,57` in pt = `um vírgula cinquenta e sete`, `77%` = `seventy seven
percent`, `1st` = `first`, `$5` = `five dollars`; the language's decimal and thousands marks)
and keep their digits in other languages (`1.000,5` → `1000 5`); `&`, `+`, `=`, `×`, `@` become
words; spelled acronyms are joined (`G.P.U.` = `G P U` = `GPU`). The normalised words are
aligned (fewest substitutions, deletions and insertions); differences are grouped into whole
written words. A difference that disappears when the words are joined (`overparameterized` /
`over parameterized`, `KPhi3`) or when the STT wrote the term as written (`K-Phi-3` heard in a beat
that says "kay fye three") is not counted.

**Word error rate** (WER) of a beat = (substitutions + deletions + insertions) / words of its
spoken text. A beat is **flagged** when its WER is above `max_wer`. STT is not perfect: a WER of
a few percent on good audio is normal, and a single difference can be the transcriber's, not the
voice's. Listen to a flagged beat before regenerating it.

**Suggestions** (each difference has one; a flagged beat lists them):
- a term with a pronunciation entry heard differently: respell the entry's spoken form;
- a name, acronym, number or other hard term (a digit, two capitals, a letter outside ASCII, a
  capitalised word inside a sentence) heard differently: add a pronunciation entry
  `TERM: <how to say it>`, then `vidgen tts`;
- words missing: listen, and regenerate the beat (`vidgen tts --force --beat ID`) if they are not
  said; extra words: listen (the voice or the transcriber added them);
- other words heard differently: probably a transcription slip; listen;
- the audio is **stale** (its hash does not match the current text or voice): run `vidgen tts`
  first. Beats without an MP3 are skipped.

The report then lists the **worst** beats and the **terms misheard in several beats** (a term
heard differently in two or more beats is very likely the voice, not the transcriber: the
strongest reason to add or fix a pronunciation entry).

**Words to check** (word flags). A voice can say every word of the text and still sound wrong:
a slurred name, a word that comes out as something foreign, a hesitation in the middle of a
sentence. The transcript tells where: the report ends with every word to listen to, in every
beat (flagged or not), each with its time in the beat's MP3, its time in the video (from the
last render, preview first; none before a render), what is wrong and a fix. Thresholds are the
[`unclear_speech` lint rule](#lint-vidgen-lint)'s settings (`lint.rules.unclear_speech`):

| a word is | when |
|---|---|
| **unclear** | heard with a probability below `min_probability` (0.5; faster-whisper says how sure it is of each word); heard after a pause longer than `max_gap` (0.5 s) inside a sentence: the word before ends without punctuation (in the text or the transcript) and no [voice sound](#voice-sounds) sits there; or part of a difference with the text (above) about a term (a name, acronym, number or pronunciation entry) or covering two or more words |
| **doubtful** | heard with a probability below `doubtful_probability` (0.75); or a single ordinary word heard differently with confidence (maybe the transcriber's slip) |

A difference and the low probability or pause of its words are one flag. The fixes: a word with
a pronunciation entry, respell the entry's spoken form; a name, acronym or number, add a
pronunciation entry with a respelling; another word, listen, then change how the beat is said
(another `voice:`, the voice's `speed`, an [`emotion:`](#voices-with-feeling-emotion)) or respell the word
in `pronunciation:`; a pause, change the speed or emotion, rephrase, or write a comma where the
pause is wanted. Each fix ends with `vidgen tts` (the change makes the beat's audio stale).
ElevenLabs Speech to Text gives no probabilities: with it, only pauses and differences are
flagged.

**Cache.** Transcripts are stored in `build/readback/<key>.json`, keyed by the MP3's content and
the STT settings (`provider`, resolved `model` and `language`): a beat is transcribed again only
when its audio or those settings change (or with `--force`); variants sharing audio share
transcripts. Each file holds `{version, audio_sha1, stt, beat, transcript: {text, language,
words: [[text, start, end, probability]]}}` (`probability` only when the provider gives one; a
faster-whisper transcript stored before probabilities were kept is transcribed again). Deleting
the folder is safe.

**Lint.** The [`readback` rule](#lint-vidgen-lint) of `vidgen lint` reports the beats above
`lint.rules.readback.max_wer` from these cached transcripts only: it never runs STT, so it finds
nothing until `vidgen readback` has run, and transcripts of older audio are ignored. The
`unclear_speech` rule reports the word flags; it runs only with `vidgen lint --readback`, which
transcribes what is not cached first.

## Generated images (`imagegen`, `vidgen imagegen`)

A picture can be generated from a prompt instead of coming from a file: the
[`image`](#image) scene's `generate:` param (instead of `path`). Generation costs money, so it
happens only when you run `vidgen imagegen`; the picture is then stored in the project like the
narration audio and reused by every render. `vidgen render`, `vidgen validate`, `storyboard` and
`lint` never call the provider: a picture not generated yet shows as a **placeholder card** (the
prompt on a soft gradient in the theme's colours, "Image to generate"), so the video can be
previewed and laid out first; `vidgen validate` and `vidgen render` warn about it.

```yaml
imagegen:
  provider: openai          # OpenAI Images API (paid; OPENAI_API_KEY)
  model: gpt-image-1        # gpt-image-1 | dall-e-3 | dall-e-2
  size: auto                # auto: by the video's format (or generate.aspect); or WIDTHxHEIGHT
  quality: null             # default: medium (gpt-image), standard (dall-e-3)
  style: flat               # added to every prompt: a preset or your own words
  negative: "text, watermarks"
scenes:
  - id: harbour
    type: image
    params:
      generate:
        prompt: "a quiet harbour at dawn, fishing boats, mist over the water"
        negative: people
        aspect: auto        # auto | landscape | portrait | square
        seed: 1             # another number: another picture of the same prompt
      ken_burns: true
    beats:
      - text: "It started in a small harbour town."
  - id: door
    type: image
    params: {generate: "a red front door in a white brick wall", style: photo}
    beats:
      - text: "Behind this door."
```

| key | default | |
|---|---|---|
| `provider` | `openai` | the provider: `openai` (OpenAI Images API, `POST /v1/images/generations`), billed per picture, key in the environment variable `OPENAI_API_KEY`; or `openrouter` (many image models through [OpenRouter](#openrouter-provider-provider-openrouter), key in `OPENROUTER_API_KEY`). vidgen never stores a key |
| `model` | `gpt-image-1` | openai: `gpt-image-1`, `dall-e-3` or `dall-e-2`; another name is sent as is (with gpt-image-1's sizes, no cost estimate). openrouter: **required**, an OpenRouter model id `author/name` (e.g. `bytedance-seed/seedream-4.5`) |
| `size` | `auto` | `WIDTHxHEIGHT` sent to the provider, or `auto`: the model's landscape / portrait / square size for the video's format or the `generate.aspect` (gpt-image-1: `1536x1024`, `1024x1536`, `1024x1024`; dall-e-3: `1792x1024`, `1024x1792`, `1024x1024`; dall-e-2: `1024x1024`). openrouter: `auto` sends an aspect ratio instead (below) |
| `quality` | none (by model) | gpt-image-1: `low`, `medium`, `high` (default `medium`); dall-e-3: `standard`, `hd` (default `standard`); none for dall-e-2. openrouter: `auto`, `low`, `medium`, `high`, `xhigh`, `max` for models that have it (not sent by default) |
| `resolution` | none | openrouter only: `512`, `768`, `1K`, `1.5K`, `2K`, `4K` for models that have it (default: the model's own); not together with a `WIDTHxHEIGHT` size |
| `style` | none | words added to every prompt (`Style: ...`) so the pictures of a video look alike: a preset (below) or your own words; a scene's `generate.style` replaces it |
| `negative` | none | what no picture should show, added to each prompt's `Avoid: ...` (with the scene's own `negative`) |
| `svg_model` | `model` | openrouter only: the model of pictures with `generate.format: svg` (e.g. `recraft/recraft-v4.1-vector`), so one video can mix raster and [vector pictures](#vector-svg-pictures-format-svg) |

`generate:` (a mapping, or just the prompt as a string):

| key | default | |
|---|---|---|
| `prompt` | required | what the picture shows; describe the scene, light, mood and composition |
| `negative` | `""` | what it should not show; the OpenAI API has no negative prompt, so it is sent as `Avoid: ...` |
| `style` | `imagegen.style` | a preset, your own words, or `none` (no style words, not even the project's) |
| `aspect` | `auto` | `auto` (landscape for a wide video, portrait for 9:16, square for 1:1), `landscape`, `portrait`, `square` |
| `seed` | none | a number that is part of the cache key: change it for another picture of the same prompt. OpenAI takes no seed, so it does not make the picture reproducible; on OpenRouter it is sent to models that take one (others: key only) |
| `format` | `png` | `png` (a raster picture) or `svg`: a [vector picture](#vector-svg-pictures-format-svg) drawn as shapes (provider `openrouter` with an SVG model) |

**Style presets**: `photo` (photorealistic photograph, natural light, sharp focus),
`illustration` (clean digital illustration, soft shading, limited colour palette), `flat` (flat
vector illustration, simple geometric shapes, solid colours, no outlines), `isometric`,
`watercolor`, `line_art`, `render_3d`, `cinematic`. The prompt sent is `<prompt>. Style: <style
words>. Avoid: <negative>.`, where a [`stage`](#generated-backgrounds-cartoon_style) scene adds the
video's `cartoon_style` to the style words; `vidgen imagegen --dry-run` prints it.

**Cache.** Each picture is stored as `assets/generated/<key>.png` (`<key>.svg` for `format: svg`) with `<key>.json` beside it
(`prompt`, `negative`, `style`, `sent_prompt`, `revised_prompt` — the prompt the model says it
used —, `provider`, `model`, `size`, `quality`, `seed`, `created` date, `scenes`). The key is a
hash of the prompt sent (with style, `cartoon_style` on a stage, and negative), provider, model, size, quality and seed:
editing any of them asks for a new picture, while scenes sharing a request share one file.
**Commit `assets/generated/`** like `audio/`: the pictures cost money and cannot be made again
identically. A variant with another format (9:16) gets portrait pictures of its own. Pictures no
config uses any more are listed by `vidgen imagegen`, never deleted.

```
$ vidgen imagegen my_video --dry-run
would generate 5deed4af8e8001e7.png for harbour (1536x1024, gpt-image-1 medium, ~$0.063)
    prompt: a quiet harbour at dawn, fishing boats, mist over the water. Style: flat vector illustration, ... Avoid: people; text, watermarks.
dry run: 2 picture(s) to generate, estimated $0.13 (OpenAI list prices of 2025; check current pricing); 0 up to date
$ vidgen imagegen my_video
[1/2] generated 5deed4af8e8001e7.png for harbour (14.2 s)
...
```

| option | |
|---|---|
| `--dry-run` | list the pictures to generate with their prompts and an estimated cost, saying what it is based on (OpenAI: its list prices when this was written; OpenRouter: its prices of today, looked up online; no key needed) |
| `--force` | generate again even when the picture exists (a new picture replaces it) |
| `--scene ID` | only this scene's pictures (repeatable) |
| `--variant NAME` | a variant: its format, prompts and `imagegen` settings |

Requests are retried on rate limits and server errors (honouring `Retry-After`), not on an
exhausted quota or a refused prompt; the provider's error message is shown.

### OpenRouter provider (`provider: openrouter`)

[OpenRouter](https://openrouter.ai) sells many image models (Seedream, FLUX, Recraft, Gemini,
GPT Image, Qwen, ...) behind one key and one API. Choose a model from
[its image models](https://openrouter.ai/models?output_modalities=image) and name it:

```yaml
imagegen:
  provider: openrouter
  model: bytedance-seed/seedream-4.5   # required: an OpenRouter model id
  resolution: 1K                       # optional: 512 | 768 | 1K | 1.5K | 2K | 4K (if the model has it)
  quality: null                        # optional: auto | low | medium | high | xhigh | max (if the model has it)
  style: flat
```

Set the key `OPENROUTER_API_KEY` in the environment (from <https://openrouter.ai/keys>;
Windows: `setx OPENROUTER_API_KEY your_key`, then a new terminal; Linux / macOS: `export
OPENROUTER_API_KEY=your_key`). `openai` stays the default: projects without `provider:
openrouter` and their stored pictures are unchanged.

- **Size.** With `size: auto` vidgen sends an `aspect_ratio`: the one nearest the video's format
  (`16:9`, `9:16`, `1:1`, `4:3`, ...), or `16:9` / `9:16` / `1:1` for a `generate.aspect` that
  differs from the video's; plus `resolution` when set. A model without that ratio uses its
  nearest (the dry run says so) and the scene's `fit` crops or pads. `size: WIDTHxHEIGHT` is
  sent as is instead (OpenRouter fits it to the model).
- **What each model takes.** Before the first paid request vidgen reads the model's public record
  (free) and refuses, with a message, a model OpenRouter does not have, a `quality` or
  `resolution` the model does not take, a model that makes only vector (SVG) pictures for a
  `png` picture (and one that makes none for `format: svg`) and models that only edit an input
  picture. A `seed` is sent only to models that take one. `negative` and
  `style` go into the prompt (`Avoid: ...`, `Style: ...`), as for OpenAI.
- **Prices.** `vidgen imagegen --dry-run` looks up each model's price on OpenRouter (free, a few
  seconds at most) and prints its basis: `$0.04 per image`, `$0.014 per megapixel x 0.59 MP
  (nominal 1024x576)` (the size the provider makes may differ a little), or `price unknown`
  when the model is billed per output token (the tokens per picture are not listed) or
  OpenRouter cannot be reached. With several providers serving a model, the highest price.
- **Cost of a run.** OpenRouter reports what each picture cost; `vidgen imagegen` prints it and
  stores it in the sidecar (`cost_usd`), with `aspect_ratio` and `resolution`.
- **Pictures** come back as PNG, JPEG or WebP and are stored as PNG; the cache key also covers
  the aspect ratio and resolution. SVG: [below](#vector-svg-pictures-format-svg).
- **Privacy settings (Zero Data Retention).** If your OpenRouter account requires Zero Data
  Retention (or excludes providers that may keep or train on prompts), choose a model with a
  ZDR endpoint: OpenRouter refuses the others (HTTP 404, "no endpoints ... matching your data
  policy") and vidgen then says so, links <https://openrouter.ai/settings/privacy> and lists the
  image models that have a ZDR endpoint (from OpenRouter's public list
  `https://openrouter.ai/api/v1/endpoints/zdr`; on 2026-10-08 e.g.
  `bytedance-seed/seedream-5-0-flash`, `bytedance-seed/seedream-4.5`, the Gemini, Krea and MAI
  image models — not Recraft or FLUX, and no SVG model). Seen live on 2026-10-09 with an account
  requiring ZDR: `recraft/recraft-v4.1-flash` and `black-forest-labs/flux.2-klein-4b` refused,
  `bytedance-seed/seedream-5-0-flash` made a 1024x1024 picture in ~10 s for $0.018 (the dry
  run's estimate). To check a model before choosing it: open
  `https://openrouter.ai/api/v1/endpoints/zdr` (public, no key) and look for its id among the
  `model_id`s, or, from a source checkout, `python tools/live_check_openrouter.py --zdr` lists
  the cheapest image models that have one.

```
$ vidgen imagegen my_video --dry-run
would generate 7e9b5bf8aff6f7b2.png for harbour (16:9, openrouter bytedance-seed/seedream-4.5, ~$0.040)
    price: OpenRouter: $0.04 per image
    prompt: a quiet harbour at dawn, fishing boats, mist over the water. Style: ...
dry run: 1 picture(s) to generate, estimated $0.040 (OpenRouter prices of 2026-10-08); 0 up to date
```

vidgen identifies itself to OpenRouter with the optional app headers (`HTTP-Referer`: the
project's repository URL, `X-OpenRouter-Title`: `schu-video-generator`). OpenRouter's terms and
each upstream model's provider policies apply to what you generate.

### Vector (SVG) pictures (`format: svg`)

`generate: {prompt: ..., format: svg}` asks for a vector picture: OpenRouter's SVG models turn
the text prompt into an SVG in one call (no raster picture first). It is stored as
`assets/generated/<key>.svg` (+ sidecar with `format: svg`) and the [`image`](#image) scene
draws it as shapes: sharp at any size, and it can be **drawn in** (`draw: true`: outlines are
traced, then filled) and **painted in the theme's colours** (`recolor: theme`).

```yaml
imagegen:
  provider: openrouter
  model: bytedance-seed/seedream-4.5        # raster pictures
  svg_model: recraft/recraft-v4.1-vector    # format: svg pictures
scenes:
  - id: idea
    type: image
    params:
      generate: {prompt: "a flat illustration of a lightbulb with gears inside", format: svg}
      draw: true
      recolor: theme
```

- **Models** (OpenRouter's public list of 2026-10-08; text prompt in, SVG out, `$` per picture):
  `recraft/recraft-v4.1-vector` and `recraft/recraft-v4-vector` ($0.08),
  `recraft/recraft-v4.1-pro-vector` and `recraft/recraft-v4-pro-vector` ($0.30). None has a
  Zero Data Retention endpoint: an account requiring ZDR cannot use them (vidgen's error says
  so). `vidgen imagegen --dry-run` shows the live price and refuses a model that makes no SVG;
  `vidgen validate` warns about a `format: svg` model not known to make SVG.
- **Requests** send `output_format: svg` and an aspect ratio (no `quality` / `resolution`:
  vectors have none); the cache key includes the format, so PNG keys are unchanged.
- **Sanitised before drawing**: scripts, embedded HTML, embedded raster pictures, filters
  (blur, shadows), masks / clip paths, text (put words on screen with vidgen), animation and
  links to other files are removed; gradients and patterns become one colour (the average of the
  stops). At most 1500 shapes are drawn (the smallest beyond it are dropped) and 60 000 curve
  segments (paths are thinned): each with a warning, so a huge SVG cannot stall a render. The
  scene's `simplify` drops small details on purpose. `vidgen validate` lists what loading a
  stored SVG will remove; renders log it.
- **When it is worth it**: flat illustrations, icons, diagram-like and line art (few flat
  colours: they scale, draw in and recolour well). Not for photos, textures or soft lighting:
  those come back as thousands of shapes (dropped or thinned) and look worse than a PNG.
- An `.svg` file of your own works the same way as the `image` scene's `path`.

**Writing prompts.** Image generators draw letters, numbers, charts and logos poorly (garbled
words, made-up values): `vidgen validate` warns when a prompt quotes text or asks for a sign,
label, title, logo, chart or diagram. Put words on screen with vidgen (a caption, a title, a
callout) and data in its chart scenes; ask the generator for the picture only (`negative: text`
helps). Use one project `style` so the pictures of a video match.

**Responsible use.** vidgen adds no content filter of its own: the provider's usage policies
apply and its safety system may refuse a prompt (the error says so). Do not generate pictures
of real people or brands that could mislead, and say that pictures are generated when that
matters to the viewer. The `revised_prompt` in the sidecar shows what the model made of the
prompt.

## Languages and translations

A video in another language is usually a [variant](#variants) with a `language:` and a
translation file:

```yaml
language: en                      # optional: the base config's language (none: English rules)
variants:
  pt:
    language: pt-BR               # BCP-47 tag
    translations: translations/pt.yaml   # written by `vidgen translate-template --variant pt`
    pronunciation: {LaTeX: "látec"}      # the base's entries, said the Portuguese way
    voice: {voice_id: "XXXXXXXXXXXXXXXXXXXX"}   # optional: another voice (eleven_multilingual_v2 speaks both)
```

**`language`** (top level or per variant; a BCP-47 tag, written as you like it and normalised:
`PT-br` is `pt-BR`) changes:

| what | how |
|---|---|
| SRT and [`captions`](#captions) cues | punctuation breaks cues in every language (`.!?…` and `。！？`, `,;:` and `، 、，`, dashes, before `¿ ¡ «`); the words a phrase starts with (conjunctions, prepositions) and the words that lean on the next one (articles, prepositions: never at a line end) are listed for English, Portuguese, Spanish, French, German and Italian; other languages break at punctuation only (a neutral rule set). Word times: a silent final `e` only in English and French |
| `narration_speed` lint | the language's words-per-second range, or characters per second for languages without one (see [lint](#lint-vidgen-lint)) |
| ElevenLabs | `language_code` for models that accept one (see [voice](#voice-voice)) |
| the MP4 | the audio stream's `language` tag (ISO 639-2: `por`, `eng`...) |
| `timings.json` | `language` |
| [pronunciation](#pronunciation-pronunciation) | entries with a `language` apply only to videos in it |

A video without `language` follows the English rules and sends no language, exactly as before
languages existed. Each variant's outputs are its own (`<output>_<variant>.mp4`, `.srt`,
`_chapters.txt`, `_thumbnail.png`), so a translated variant's subtitles, chapter titles and
thumbnail are in its language when their texts are translated.

**Translation files.** `vidgen translate-template --variant pt [--language pt-BR] [--output FILE]
[--json]` lists every translatable text of the variant in a YAML file (the variant's
`translations:` file, else `translations/<variant>.yaml`) with the source text, a hash of it
and an empty translation:

```yaml
version: 1
language: pt-BR
source_language: en
entries:
  title:
    source: "vidgen: the built-in scenes"
    hash: e3a65b6320
    text: "vidgen: as cenas prontas"
  scenes.intro.beats.intro_b1.text:
    source: This whole video comes from one config file, with no Python code at all.
    hash: 08bb27bb38
    text: Este vídeo inteiro vem de um único arquivo de configuração, sem nenhuma linha de código Python.
  scenes.sizes.params.labels[0]: {source: Preview 480p, hash: e4a94ea70b, text: Prévia 480p}
  scenes.picture.params.caption: {source: Images can slowly zoom and pan, hash: 8d3d9f9450, text: null}
references:
  scenes.sizes.beats.sizes_b3.actions[1].highlight: scenes.sizes.params.labels[0]
```

| key | | |
|---|---|---|
| `version` | `1` | file format |
| `language` / `source_language` | none | the translation's / the source's language (`--language` / `--lang`, else the variant's `language`) |
| `entries` | `{}` | key → `{source, hash, text, stale, old_source, obsolete}`, or the translation alone (`key: text`, no staleness check) |
| `references` | `{}` | places that name a translated text (an action target `bar:<label>`, a `highlight` by label) → that text's key; written by the command |

| entry key | | |
|---|---|---|
| `source` | | the text in the config (for the translator; the `hash` decides) |
| `hash` | | the first 10 hex digits of the source's SHA-1 when it was translated |
| `text` | `null` | the translation; empty: the source text is shown |
| `stale` | `false` | the source changed since the text was translated (set by the command): not used until you check it and delete the flag |
| `old_source` | | the source the stale translation was made from |
| `obsolete` | `false` | the key is gone from the config; kept so the text is not lost |

When the project loads, every entry with a translation whose source still matches its `hash` (or
its `source`, without a hash) replaces the text in the raw config before it is validated, so the
narration, the TTS, the SRT, the captions, the scenes' on-screen text, chapter titles, MP4 tags
and the thumbnail all follow. Then each `references` place that still names the source text is
renamed (`bar:Preview 480p` → `bar:Prévia 480p`, `point:sparse@8` → `point:esparso@8`). A
translated beat text changes the beat's spoken text, so the variant gets its own audio folder
`audio/<variant>/` and `vidgen tts --variant pt` voices only the translated beats there (the
others are copied from `audio/`). A missing file is not an error: every text shows its source.

**Keys** are config paths with ids instead of positions where there are ids: `title`,
`metadata.title|album|comment|description`, `chapters.intro`, `thumbnail.title|subtitle`,
`overlays.<id>.<option>` (a lower third's `name`, a watermark's `text`), `scenes.<id>.chapter`
(or `.chapter.title`), `scenes.<id>.beats.<beat id>.text`, `scenes.<id>.beats.<beat
id>.actions[<n>].label` (callouts), `scenes.<id>.overlays.<id>.<option>` and
`scenes.<id>.params.<path>`. In a path, `[3]` is a list item, `["a key"]` a mapping value
under a key that is not a name, `{"key"}` the mapping key itself (a chart series written as
`series: {baseline: [...]}`), `=id` a shorthand string standing for `{id: string}` (a
`diagram` node `Data` is `{id: Data}`; its label defaults to the id) and `$:` the text after the
first `:` of a shorthand string (a diagram edge `"a -> b: label"`).

**What is translatable** is declared by the scene types: every param that is shown as text
(`title`, `heading`, `caption`, labels, bullet items, table cells, legend names, axis labels,
units, notes, callout labels...; JSON Schema `x-vidgen-text: text`), not ids, paths, colours,
icons, number formats, code or LaTeX. Params that name a text of the scene (`highlight: "4K"` of
a bar chart, `now` of a timeline; `x-vidgen-text: ref`) and action targets naming one
(`bar:4K`, `item:<text>`, `point:<series>@N`) follow its translation through `references`.
Project scene types mark their own params with `TranslatableStr` / `TextRef`
(docs/EXTENDING.md).

**Updating.** Run the command again after editing the config: it keeps every translation whose
source is unchanged; a changed source keeps the old text with `stale: true` and `old_source` (not
used until checked); a text that moved (an item inserted before it) is found again by its hash
in the same scene; a translated key that is gone is kept with `obsolete: true`, an untranslated
one dropped. It prints `texts: 73 (54 translated, 19 to translate); 4 references`.

**`vidgen validate`** warns (it does not fail) about texts left in the source language (listed),
stale translations, entries that name nothing in the config, places that name a translated text
but are not in `references` (run the command again), a file whose `language` differs from the
video's, a missing file, and base pronunciation entries a variant in another language keeps. It
prints `language [pt]: pt-BR (translations/pt.yaml: 54 translated)`; `validate --json` has
`language` and `translations` (top level and per variant).

Known limits: translations change texts that exist in the config (a default such as a stat's
`decimal_mark` cannot be added by a translation file; set it in the scene); number formats
(`value_format`, `x_format`) and the bundled country names of the `map` scene are not
localised (give a country an explicit `label`); a `map` arc written `"A -> B"` naming a pin's
label, `lint_ignore` patterns and `point:<series>@<label>` targets naming a translated point
label are not followed; text in scripts without spaces (Chinese, Japanese) is cut into cues
only at punctuation.

### Dubbing (`dub`, `--all-languages`)

A cartoon (or any video with `voices:`) in another language is the same variant: a `language:`
and a translation file. Each speaker then speaks with a voice of that language:

```yaml
voice: {provider: kokoro, voice: bf_emma, dub: {pt: pf_dora+bf_emma:0.4}}   # the narrator, given
voices:
  fen_voice: {voice: af_heart}                  # automatic: a feminine Portuguese voice (pf_dora)
  bram_voice: {voice: bm_fable}                 # automatic: pm_alex
  gus_voice: {voice: am_fenrir, dub: {pt: pm_santa}}   # given
variants:
  pt: {language: pt-BR, translations: translations/pt.yaml}
```

**`dub`** (on `voice:` and on each `voices:` entry; default none) maps a language tag to the
voice in that language: the provider's voice name as a string (Kokoro / OpenRouter `voice`,
ElevenLabs `voice_id`), or a mapping of the keys a named voice may set (`voice`, `speed`, `lang`
for Kokoro; `voice_id`, `model_id`, `settings` for ElevenLabs; `model`, `voice`, `instructions`,
`speed` for OpenRouter), e.g. `{pt: {voice: pm_alex, speed: 0.9}}`. In a video (variant) whose
`language` it matches, those keys replace the voice's own; the most specific tag wins (`pt-BR`
before `pt`). The dub sits on the voice, not on `characters:`, because beats name voices: the
narrator and a [host](#a-host-beside-any-scene-host) are voices too, and a character speaks with
its `voice`.

**Automatic** (no `dub` for the language):

| the voice | in a video of another language |
|---|---|
| a named voice that keeps the base voice (no `voice` / `voice_id` of its own) | takes the base voice's dub |
| Kokoro, a voice of another language and no `lang` written | a Kokoro voice of the video's language of the **same kind** (the name's second letter: `f` feminine, `m` masculine): the one used least so far, best grade first; never `?m_santa` (name it in a `dub` if you want it); one source voice gets one voice everywhere |
| Kokoro with `lang` written | kept (an accent on purpose) |
| ElevenLabs, OpenRouter | kept: their voices speak many languages (ElevenLabs gets the `language_code` the model takes) |

Kokoro speaks few voices in some languages (Brazilian Portuguese and Spanish one feminine and one
masculine besides the novelty `*_santa`, French one feminine voice only), so two speakers can end
up with one voice. `vidgen validate` warns then (`dub (pt-BR): the base voice (bf_emma) and
voices.fen_voice (af_heart) speak with pf_dora here; give one a dub: {pt-BR: ...} (another voice,
or a blend such as pf_dora+af_heart:0.3)`) and when no voice of the kind exists, and prints what
each voice became: `dub [pt]: default bf_emma -> pf_dora+bf_emma:0.4 (given), fen_voice af_heart
-> pf_dora (auto), ...`. A Kokoro blend takes its language from its first voice; the others only
lend their timbre (no warning for them).

What follows from the variant, as for any translated variant: the dubbed beats get their own
`audio/<variant>/` (hashed with the dubbed voice); [lip sync](#lip-sync) is built from that
language's audio (Kokoro's phonemes per chunk for languages other than English, else the
text's phonemes through misaki / espeak-ng or the letters); speech bubbles (`say` with
`bubble: true` shows the translated line, a `bubble:` text is translatable), [`card`](#card)
texts and burned-in captions follow the translation file; each beat's timing comes from its
language's audio, so `overlap` and `interrupt` start against the dubbed line (a seconds value is
kept: lint says when it hides words in a language).

**One command for every language**: `vidgen tts --all-languages`, `vidgen render --all-languages`
(with `--preview`, `--draft`...) and `vidgen lint --all-languages` run the base config and then
every variant whose `language` differs from the base config's, one after the other (a heading
line `== pt (pt-BR) ==` before each; not with `--variant`). The exit code is the worst one;
`--json` prints one document `{command, ok, languages: [...]}` whose `languages` are each
language's own document. The MCP tools `render` and `lint` take `all_languages`.

## Sound effects (`sfx`)

Short sounds under the narration: a whoosh as a card slides in, a pop per item, a tick per step.
vidgen synthesises its own set (no recordings; free to use in your videos, including
commercially; no attribution needed) and mixes them, sample-exact, into the
video's sound when the scenes are joined. Three ways to place one:

```yaml
sfx: {auto: false, gain: 0}            # optional, video-wide (below)
scenes:
  - id: part2
    type: chapter
    params: {title: "Results"}
    duration: 2.5
    sfx:                               # at seconds from the scene's start (silent scenes too)
      - whoosh                         # a plain name: at 0
      - {sound: chime, at: 1.2, gain: -3}
  - id: points
    type: bullets
    params: {items: [Fast, Cheap, Good]}
    beats:
      - text: "Three things matter."
        actions:                       # a beat action, at a fraction of the beat (like every action)
          - sfx: pop                   # at 0: when the beat starts
          - sfx: riser
            at: 0.6
            align: end                 # the riser ends (at its loudest) at 0.6 of the beat
            params: {duration: 1.5}
```

In scene code (extensions): `self.sfx("pop")` (now) or `self.sfx("chime", at=2.0, gain=-3,
pitch=2)`; see docs/EXTENDING.md.

**Built-in sounds** (`vidgen list-sfx` prints what each one sounds like, `--render-dir DIR`
writes them as WAV files to listen to):

| sound | default length | what it sounds like | use it for |
|---|---|---|---|
| `whoosh` | 0.6 s (0.2–3) | soft band-passed noise sweeping up ~380 Hz → ~2.7 kHz, swelling to a peak at 55% | a slide, card or element moving in; a camera move |
| `swoosh` | 0.45 s (0.15–3) | the reverse: the band falls ~2.7 kHz → ~380 Hz, peaking early | something leaving or being swapped out |
| `pop` | 0.12 s (0.05–0.4) | a round bubble "bloop", ~480 → ~890 Hz in 30 ms | an item, bullet, icon or dot appearing |
| `click` | 0.03 s (0.01–0.1) | a crisp 3 ms UI click around 3.2 kHz | a selection, a toggle, a cursor click |
| `tick` | 0.09 s (0.03–0.3) | a soft wooden tick at 1.5 kHz, ~20 ms | counting, timeline marks, steps |
| `typing` | 1 s (0.2–8) | irregular soft key clicks, 6–14 per second | text or code being typed |
| `riser` | 2 s (0.5–8) | rising noise band (~250 Hz → ~4.3 kHz) + a faint sine glide, louder to the end | tension before a reveal (`align: end`) |
| `chime` | 1.6 s (0.4–5) | a clear bell note at A5 with soft overtones, ringing out | a key insight, a result |
| `success` | 0.9 s (0.4–3) | two soft bell notes, E5 then B5 | a check mark, a goal reached |
| `error` | 0.5 s (0.3–2) | two muted notes falling G4 → E♭4 | a mistake, a failing case |
| `thud` | 0.45 s (0.15–1.5) | a soft low impact, 110 → 55 Hz with a muffled knock | something landing, a big number |
| `footstep` | 0.14 s (0.06–0.4) | one soft step: a muffled heel knock (~260 Hz, a 95 Hz thump), then a faint scuff | a character's step ([foley](#foley-and-music-stings)) |
| `boing` | 0.5 s (0.2–1.5) | a twangy cartoon spring gliding up ~140 → ~260 Hz with a fast wobble | a jump, a bounce |
| `bell` | 0.7 s (0.3–2) | a bicycle bell, "ring-ring": two quick strikes of a small bright bell at ~2.35 kHz | a bicycle setting off ([foley](#foley-and-music-stings)) |
| `engine` | 1.6 s (0.5–8) | a small engine starting and running: a buzzy ~42 Hz tone revving up, settling, with a soft rumble | a car or a bus setting off |
| `brakes` | 0.5 s (0.2–1.5) | brakes squealing to a stop: a thin wavering tone near 2.1 kHz over a soft scrape | a vehicle stopping |
| `burner` | 1.2 s (0.4–4) | a gas burner's roar: deep breathy noise around 450 Hz with a faint hiss, fluttering at 9 Hz, dying away at the end | a hot-air balloon rising |
| `launch` | 1.0 s (0.4–3) | a toy rocket taking off: a soft low "whump", then a fizzing hiss climbing ~1.5 → ~5 kHz with a crackle, fading out | a toy rocket or a firework launching |
| `phone` | 1.0 s (0.4–3) | a phone ringing, "brring-brring": a soft electronic trill (a tone flipping between ~1.1 and ~1.4 kHz 20 times a second) in two pulses of about 0.4 s | a ringing [phone](#everyday-small-props-let_go-pour) (each burst of rings) |
| `thunder` | 3 s (1–8) | thunder: a crack of bright noise around 1.8 kHz (stronger with `intensity`: a near strike), then a deep rumble below ~120 Hz rolling in three to five swells, dying away | after [lightning](#lightning-and-thunder-lightning) (played for it: later, quieter, longer and lower the farther the strike) |
| `creak` | 0.9 s (0.3–3) | a door's hinge creaking: a rough, buzzy squeak (stick-slip pulses gliding ~45 → ~110 → ~70 Hz) coloured by a wooden body (~550 Hz, ~1.3 kHz, ~2.6 kHz) | a door opening or closing ([foley](#foley-and-music-stings)), an old chair |
| `knock` | 0.75 s (0.3–2) | "knock-knock-knock": three knuckle raps on a wooden door 190 ms apart, a dull hollow thump (~190 and ~410 Hz) with a short tap | someone at the door ([`knock`](#ambience-and-door-sounds-ambience-knock)) |
| `unlock` | 0.3 s (0.15–0.8) | a key turning in a lock: a small metallic tick (~2.2 kHz, a ~1.7 kHz ping), then 90 ms later a rounder clack of the bolt (~620 Hz, a soft ~170 Hz knock); low-passed, not sharp | a locked door opened with its key on a [level](#story-props-on-a-level-keys-doors-coins-stars-blockers) (foley), a chest unlocking |
| `coin` | 0.45 s (0.2–1.5) | a coin picked up, "pling-ling": two quick soft bell notes rising a fourth, B5 then E6, 70 ms apart | each coin a walk or a jump picks up on a level (foley), a point scored |
| `twinkle` | 0.8 s (0.3–2.5) | a star picked up: a quick rising arpeggio of soft bell notes C6 E6 G6 C7, 50 ms apart, with a faint airy glitter | each star picked up on a level (foley), something magic |
| `splash` | 0.6 s (0.2–3) | something dropping into water: a bright noise burst (~2.5 kHz) with a low "plunk" (~250 → ~600 Hz), then droplets falling back; at low `intensity` mostly droplets | a boat setting off, a watering can's water, steps in puddles ([foley](#foley-and-music-stings)) |
| `gasp` | 0.35 s (0.15–1) | a sharp breath in, "hah": breath noise around 1.1, 1.75 and 2.9 kHz, loudest after ~50 ms, cut off | surprise ([`[gasp]`](#voice-sounds) at a line's start or end) |
| `sigh` | 0.9 s (0.4–2.5) | a long breath out, "haaah": breathy "ah" noise with a faint hum falling ~190 → ~130 Hz, trailing off | tiredness, relief ([`[sigh]`](#voice-sounds) at a line's start or end) |
| `beep` | 0.4 s (0.2–1.2) | a friendly robot chirp, "bee-boop": two soft electronic notes, ~1.3 kHz (with a quick upward blip) then ~880 Hz | a robot's voice sound ([`[beep]`](#voice-sounds) at a line's start or end), a gadget |
| `sting_reveal` | 1.4 s (0.6–4) | a "ta-da": a brassy pickup note, then a bright C major chord with a soft bell | a reveal ([`sting: reveal`](#foley-and-music-stings)) |
| `sting_comic` | 1.1 s (0.6–3) | "ba-dum-tss": two falling tom hits and a splashy cymbal | after a punchline (`sting: comic`) |
| `sting_sad` | 2.2 s (1.2–5) | "wah wah wah waaah": four muted brass notes falling B♭3 → G3, the last long and wobbling | a let-down played for laughs (`sting: sad`) |

| key | default | |
|---|---|---|
| `sound` | required | a built-in sound or the project's own (below); in an action written as `- sfx: NAME` (or `sound: NAME`) |
| `at` | `0` | scene `sfx:` list: seconds from the scene's start; beat action: fraction of the beat's narration or a word it says (`at: "@crash"`), as for every action (rounded to a frame) |
| `gain` | `0` | dB, -60 to 12; at 0 a sound's loudest 400 ms is −27 LUFS (K-weighted, one channel), about 7 dB under ElevenLabs narration, with peaks at most −9 dBFS |
| `pan` | `0` | -1 left, 0 centre (full level on both channels), 1 right (equal-power) |
| `align` | `start` | `start`: the sound starts at `at`; `end`: it ends there |
| `params` | `{}` | `duration` (seconds, within the sound's range), `pitch` (semitones, -24 to 24, default 0), `intensity` (0 to 1, default 0.5: brighter and up to 3 dB louder towards 1) — built-in sounds only |

Video-wide `sfx:`:

| key | default | |
|---|---|---|
| `auto` | `false` | add soft sounds to built-in animations: `reveal` → pop, `highlight` → tick, `callout` → click, `zoom` → whoosh, `transform` → swoosh (when the action starts animating; not in a beat that has its own `sfx` actions), and a whoosh at the start of every `chapter` card |
| `gain` | `0` | dB added to every sound effect of the video |

- **Project sounds**: `assets/sfx/<name>.wav` (also `.flac`, `.ogg`, `.mp3`; names of letters,
  digits, `_` and `-`) adds a sound, or replaces the built-in of that name. Played at their own
  level (no loudness normalisation; `gain` still applies) and without `params`.
- **Timing.** A beat action's sound plays exactly at its `at` (rounded to a frame), even while the
  scene animates (other actions wait for the scene's animation). A sound that runs past its
  scene's end goes on over the next scene (the last scene's is cut at the video's end).
- **Mixing.** The sounds are not part of the scenes' own renders (`build/.../scenes/*.mp4`, the
  storyboard): `vidgen render` places every scene's sounds on one track for the whole video
  (`build/.../padded/sfx.wav`, 48 kHz) and adds it to the narration when it writes the MP4 (with
  [music](#background-music-music), into the final mix; effects never duck the music).
  `--no-audio` renders have none. The sounds are listed per scene in `timings.json` (`sfx`: video
  times, sound, gain, pan, align, params, beat; `duck: true` on a music sting).
- **Checks.** `vidgen validate` reports unknown sounds (with a suggestion) and params outside a
  sound's range; a sound starting after its scene ends is a render warning.

### Foley and music stings

**Foley.** On a [`stage`](#stage) the characters' actions make their own sounds, timed to the
action as it plays (also when its beat speeds it up): a `footstep` on every footfall of a
`walk_to`, `run_to`, `enter` or `exit` (alternating feet, a softer one when the feet come together), a
`whoosh` as a character enters and a `swoosh` as it leaves the view, a `boing` as a `jump` takes
off, a `thud` where a [thrown](#props-in-hands) prop lands, a `pop` when `emote` or `react`
puts on the `surprised` expression, and a short sound as most [effect
symbols](#effect-symbols-effect) pop up (`idea` a short `chime` ding; `sound: false` on the
`effect` for none), and on a [`ride_to`](#vehicles-get_in-ride_to-get_out) a bicycle's `bell`
as it sets off, or a car's, a bus's or a boat's `engine` for most of the ride, and `brakes`
ending as a bicycle, a car or a bus stops; a balloon's `burner` and a toy rocket's `launch` as
they set off, the rocket's parachute `pop`, and a soft `thud` where either lands; a `click` when
a `tv`, a `lamp` or a `kettle` is [switched on or off](#clocks-televisions-and-lamps-time-on-switch_on)
and a short `burner` whoosh when a `fireplace` is lit; a `phone` trill at each burst of rings of a
[ringing phone](#everyday-small-props-let_go-pour) (a `click` when it is switched off); a `thud` where a
[fruit falls](#fruit-falling-from-a-tree-fruit-drop_fruit); a door's `creak` as it opens or
closes (`open` / `close`, an `enter` / `exit` through a closed room door, which then plays no
whoosh or swoosh: the character fades in the doorway) and a `thud` as it shuts, a `knock` for the
[`knock`](#ambience-and-door-sounds-ambience-knock) action; a `splash` as a boat sets off, where a
watering can's water lands (`pour`) and, softly, under every step once
[puddles](#rain-on-the-ground) lie on the ground; on a [platform
level](#story-props-on-a-level-keys-doors-coins-stars-blockers) a jump's soft landing, a `coin`
or a `twinkle` at each coin or star picked up, a key's `unlock` before a locked door creaks open,
and a blocker's soft shuffle as it steps aside. Other
actions are silent. They are ordinary sound effects (listed in `timings.json` `sfx`, mixed like the rest):
`sfx: {gain}` sets their level with the others, and `assets/sfx/footstep.wav` (or `boing.wav`,
...) replaces a sound with your own. `foley: false` at the top level turns them off for the
video, a stage's `foley: false` (or `true`) for that scene. Rain on a stage also plays a
generated rain sound bed while it lasts, mixed with the music and ducked less
([Rain on the ground](#rain-on-the-ground)), and a burning fireplace a crackle bed
([fireplaces](#fireplaces-and-kettles-on-switch_on)), and every stage a bed of its set
([ambience](#ambience-and-door-sounds-ambience-knock): birdsong outdoors by day, a room tone
indoors, or the city); `foley: false` turns them off too.

**Music stings.** A beat's `sting` plays a short musical phrase on it:

```yaml
beats:
  - text: "And the winner is... the box!"
    sting: reveal                     # "ta-da", as the beat starts
  - text: "It was empty all along."
    sting: {kind: sad, gain: 2}       # "wah wah wah waaah", when the line ends
```

| key | default | |
|---|---|---|
| `kind` | required | `reveal` (`sting_reveal`: a "ta-da" chord), `comic` (`sting_comic`: ba-dum-tss) or `sad` (`sting_sad`: a sad trombone); a plain string is the kind |
| `at` | `start` for `reveal`, `end` for `comic` and `sad` | `start`: as the beat starts; `end`: when its narration ends, in the pause after the line (the beat's `narration.pad`) |
| `gain` | `0` | dB, -60 to 12, like a sound effect's |

Stings go on the sound-effect track (any scene type) and duck under the narration like the
music: 6 dB down while the narrator speaks, 0.15 s down before the speech starts, 0.3 s back up
after it ends, no hold (the music's 1.5 s hold would keep a sting down through every pause). A
sting at a beat's end therefore plays in the clear and ducks when the next line starts. In a
preview timed from word counts (no MP3s yet) the whole beat counts as speech. Under
[composed music](#composed-music-compose) a sting is played by the music's own instruments, in
its key ([stings](#music-that-follows-the-video)).

### Voice sounds

A beat's text may hold non-speech sounds of its speaker: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`,
`[giggle]`, `[groan]` and a [robot](#robots-and-costumes)'s `[beep]` (any case; `[laughs]`,
`[sighs]`... work too). Any scene type; on a
[`stage`](#stage) the speaker's face follows.

```yaml
beats:
  - text: "[gasp] The box is open! [laugh] It was empty."
    voice: kit_voice
  - text: "Well [hmm] I suppose so. [sigh]"
```

- **The text.** The markers are taken out of the beat's `text` when the config is read, like
  `*word*`: captions, subtitles, speech bubbles, slides and lint show `The box is open! It was
  empty.`. Other brackets (`[cough]`, `[pause]`) stay in the text and are spoken as written. A
  beat needs words besides its sounds.
- **The sound.** The voice says the sound where it can, as words in the text sent to the TTS
  (what `vidgen tts --dry-run` shows as `says:` and what the audio hash covers):

  | sound | Kokoro, ElevenLabs (other models), OpenRouter | ElevenLabs `eleven_v3` | face on a stage |
  |---|---|---|---|
  | `[laugh]` | `Ha ha ha!` | `[laughs]` (an audio tag) | `laughing` |
  | `[giggle]` | `Hee hee!` | `[giggles]` | `laughing` |
  | `[hmm]` | `Hmm.` | `Hmm.` | `thinking` |
  | `[groan]` | `Ugh.` | `[groans]` | `worried` |
  | `[gasp]` | at the line's start or end: the built-in `gasp` sound; inside it: `Hah!` | `[gasps]` | `surprised` |
  | `[sigh]` | at the line's start or end: the built-in `sigh` sound; inside it: `Haah.` | `[sighs]` | `sad` |
  | `[beep]` | at the line's start or end: the built-in `beep` sound; inside it: `Beep boop!` | `Beep boop!` | `happy` |

  A TTS says a breath (or a beep) as a word, so `[gasp]`, `[sigh]` and `[beep]` at the start or end of a line are
  generated sounds instead, mixed into the silence there: a gasp ends just before the first word
  (in the pause after the previous line), a sigh starts just after the last one (in the beat's
  `narration.pad`). They are sound effects of the beat (`timings.json` `sfx`, 6 dB louder than
  other effects at `gain: 0`; `assets/sfx/gasp.wav` replaces the sound with your own), and the
  beat's audio stays as without the marker. Inside a line there is no silence to fill, so it is
  said. Measured with Kokoro (`af_heart`): `Ha ha ha!` takes 0.7 s, `Hee hee!` 0.4 s, `Hmm.` and
  `Ugh.` about 0.3 s.
- **Pronunciation** entries apply to the line's words only, never to a sound's words; a beat
  without markers keeps its audio hash.
- **Mouth and face.** A speaking character's mouth follows the sound: the said ones are in the
  beat's viseme track like words (`Hmm.` closes the lips, `Ha ha ha!` opens them), a generated
  gasp opens it round (`O`), a sigh open (`A`), a beep wide (`E`). On a `stage`, each speaker of the line takes the
  face of its first sound (table above) as the sound is heard, until the next beat: an automatic
  `react` (listed by `vidgen direct`, whatever `auto_direct` says), left out when the beat's own
  `emote` or `react` acts on that character or its parts have no face.
- **Captions and readback.** Captions and the SRT time the line's words by the audio (the sound
  takes its own time between them) and never show the sound. `vidgen readback` compares the
  transcript with the line without its sounds and skips the words a transcript writes for them
  (`ha ha`, `hmm`, `ugh`, `laughs`...) unless the line says them.

### Overlapping lines (`overlap`, `interrupt`)

Two speakers talking at once, or one cutting the other off. Any scene type; on a
[`stage`](#stage) both mouths move.

```yaml
beats:
  - text: "And then the box started to hum, and I thought it would never stop."
    voice: pip_voice
  - text: "It hums every night!"
    voice: kit_voice
    overlap: 0.6        # starts 0.6 s before pip's line ends: both heard
  - text: "Wait, wait, listen to me."
    voice: pip_voice
  - text: "No, you listen!"
    voice: kit_voice
    interrupt: true     # cuts pip off inside the last word, "me" (overlap: S for another point)
```

- **Timing.** `overlap: S` starts the beat `S` seconds before the speech of the beat before it
  ends (its MP3's trailing silence cut off; the word-count estimate without audio), in whole
  frames, with no `narration.pad` between them. The beat before keeps at least 0.2 s. `overlap:
  0` starts it right as the speech ends (a tight reply without the pause). Only within a scene:
  a scene's first beat cannot have `overlap` or `interrupt` (a config error), so scenes start and
  end where they would, and chapters, transitions and `carry` are unchanged.
- **Sound.** With `overlap` both lines are heard; the earlier one is 3 dB lower from where the
  later one starts (a 0.1 s ramp), so the new line leads and both stay audible. `interrupt: true`
  cuts the earlier line where the beat starts with a 0.05 s fade. Without `overlap` it starts
  inside that line's last word, 70% of the way through it (the word times `vidgen tts` stores
  with the MP3), so only the end of the word is cut; without stored word times (an estimate, or a
  provider that gives none) 0.2 s before that line's speech ends (`interrupt: true` with
  `overlap: 0` is a config error: it would cut nothing). The MP3s are not changed (no re-voicing; `vidgen tts` is unaffected): the
  scene's sound is shaped when it is rendered. Music ducks under both voices.
- **What the beat before gets.** Its animations and actions get the time until the next beat
  starts (what `with self.narrate(i) as d` yields, and what `at:` fractions are of); a beat whose
  animations take longer makes the next one start late (`animation_overrun` reports it).
- **Mouths.** On a `stage` the earlier speaker's mouth goes on following its line under the new
  one (its `say` too) and rests when its audio ends; an interrupted line's mouth stops at the cut.
  Automatic directing adds no listener reaction after a line that the next beat overlaps (there
  is no pause), and gestures only on words heard before the next line starts.
- **Captions and subtitles.** While both lines sound, captions show both, one line each, the
  earlier one above (in its speaker's colour with `speakers: color`); the SRT has overlapping
  cues of one line each, which players show one above the other. An interrupted line's captions
  end at the cut. `timings.json` gives the interrupted beat's `end` at the cut, an overlapped
  beat's `end` after the next beat's `start`.
- **Checks.** `vidgen validate` warns when a beat overlaps a line of its own voice. `vidgen lint`
  warns when an overlap is so long that whole words of the line before are spoken under the new
  one, or when an `interrupt` (with or without `overlap`) cuts the line before whole words of it
  start ([`talked_over`](#lint-vidgen-lint)).

### `vidgen list-sfx`

`vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]` lists the built-in sounds and the project's
`assets/sfx` with their length, loudness and peak, and for built-ins a precise description of the
sound and when to use it (an AI author cannot listen); `--render-dir` also writes each sound at
its defaults as `DIR/<name>.wav`. JSON: see [below](#vidgen-list-sfx---json).

## Background music (`music`)

A music bed under the whole video (or under parts of it), ducked while the narrator speaks.
vidgen generates five beds itself (no recordings, no samples; free to use in your videos,
including commercially; no attribution needed); any audio file FFmpeg
reads works too, and so does music vidgen composes for the video in a mood
([composed music](#composed-music-compose)).

```yaml
music: calm                            # a bed or a file, with the defaults below
```

```yaml
music:                                 # the long form: one cue over the whole video
  source: assets/music/theme.mp3       # a built-in bed, or a file under the project
  volume: -2                           # dB
  start: 12.5                          # seconds into the file (skip its intro); loops restart here
  loop: true                           # repeat while the video lasts (a file's seam cross-fades)
  crossfade: 2.0
  fade_in: 1.5
  fade_out: 3.0                        # ends with the video
  duck: {depth: 12, attack: 0.4, release: 1.0, hold: 1.5, clips: true}   # or duck: false
scenes:
  - id: interview
    type: video_clip
    params: {path: assets/interview.mp4}
    duration: 20
    music: false                       # no music here: it fades out before, back in after
  - id: outro
    type: end_card
    params: {title: "Thanks"}
    duration: 4
    music: {volume: 4}                 # louder over the end card
```

```yaml
music:                                 # a list of cues: changing tracks
  - {source: calm, to: part2}          # from the first scene to the end of scene part2
  - {source: bright, from: results}    # from scene results to the end
```

**Built-in beds** (`vidgen list-music` describes them, `--render-dir DIR` writes one loop of
each as WAV): seamless loops, generated in about a second when the video is joined.

| bed | loop | what it sounds like | use it for |
|---|---|---|---|
| `calm` | 60 s, D major, no beat | a slow, warm synth-string pad, chords held 7.5 s and cross-faded, a quiet sub-bass, an airy upper layer swelling twice a minute; no percussion, no melody | calm explainers, serious topics, long narration |
| `pulse` | 40 s, A minor, 96 BPM | a soft plucked eighth-note arpeggio over a muted pad, a gentle low thump on every beat; chords every two bars | tech / product explainers, walkthroughs, data stories |
| `bright` | 48 s, C major, 120 BPM | a brighter pad, a plucked arpeggio an octave up, a sparse soft bell melody; I–V–vi–IV style | launches, tutorials, upbeat social clips |
| `cartoon` | 45 s, G major, 128 BPM, 4/4 | a staccato pizzicato-string melody (B4–D6) on a short motif that comes back varied, a plucked bass bouncing root–fifth, oom-pah pizzicato chords on 2 and 4, two woodblocks, soft snare-like ticks, a faint pad; six 4-bar phrases | cartoons and children's stories, comic or light-hearted scenes, playful how-tos |
| `lullaby` | 45 s, F major, 64 BPM, 3/4 | a music-box melody (C5–D6) over a quieter music-box broken chord in eighths, a warm soft pad, a low sine bass on each bar's first beat; no percussion | bedtime stories, soft or sentimental moments, endings |

| key | default | |
|---|---|---|
| `source` | required (or `compose`) | `calm`, `pulse`, `bright`, `cartoon`, `lullaby`, or an audio file under the project (`assets/music/x.mp3`; wav, flac, ogg, mp3, m4a, ...) |
| `compose` | none | instead of `source`: music composed in a mood, `compose: calm` or `{mood, key, tempo, instruments, seed, bars}` ([below](#composed-music-compose)); without `bars` it is composed for the video ([follows it](#music-that-follows-the-video): `start` and `loop` do not apply); with `bars` it loops seamlessly like a bed and `start` wraps around the piece |
| `volume` | `0` | dB, -60 to 12; at 0 the music is −28 LUFS integrated (beds are made at that level, files are measured and matched to it): about 6.5 dB under ElevenLabs narration (≈ −21.4 LUFS) in its pauses |
| `start` | `0` | seconds into the source where it starts; a loop restarts there |
| `loop` | `true` | repeat the source as long as the cue lasts; `false`: it plays once and fades out at its end |
| `crossfade` | `2.0` | seconds over which a file's end cross-fades (equal power) into its start at every repeat; beds loop seamlessly |
| `fade_in` | `1.5` | seconds of fade-in at the cue's start |
| `fade_out` | `3.0` | seconds of fade-out ending at the cue's end (the video's end) |
| `duck` | see below | ducking under the narration; `false` for none |
| `from` | the first scene | (in a list of cues) the scene the cue starts with |
| `to` | the last scene | (in a list of cues) the scene the cue ends with; cues may not overlap |

**Ducking** (`duck:`): the music goes down while the narrator speaks — keyed off the narration
alone: each beat from its start to the end of its speech (the MP3's trailing silence cut off; the
whole beat when it has no audio yet). Sound effects never duck it.

| key | default | |
|---|---|---|
| `depth` | `12` | dB the music drops under speech (0: no ducking); with the defaults the music is ~18.5 dB under the voice while it speaks |
| `attack` | `0.4` | seconds the music takes to go down; it is fully down when the speech starts (the mix looks ahead) |
| `release` | `1.0` | seconds it takes to come back after the speech |
| `hold` | `1.5` | pauses shorter than this stay ducked (no pumping between beats); longer pauses, silent scenes and the gaps between narrated scenes bring the music up |
| `clips` | `true` | a `video_clip` scene whose clip plays sound (not `mute`, `volume` above 0) also ducks the music, for the whole scene |

A scene's `music:` — `false` (none: it fades out over the 0.75 s before the scene, back in over
the 0.75 s after) or `{volume: dB}` (added to the cue's volume during the scene, ramped the same
way). Between two cues the first fades out at the end of its last scene and the next fades in.

- **Mixing.** Music is applied when the scenes are joined (it is not in the scenes' renders or
  the storyboard, and changing it re-renders nothing): the narration (with clip sound), the
  sound effects and the music are summed, 48 kHz, into `build/.../padded/mix.wav` (24-bit),
  which the final MP4 encodes. `--no-audio` renders have no music. Drafts (`render --draft`) and
  animatics mix the music like the video (composed music too: a draft's timings differ a little
  from the preview's, so its piece is composed for them; each render is cached in `build/music/`).
- **Checks.** `vidgen validate` reports a source that is neither a bed nor an existing file, and
  cues naming unknown scenes, out of order or overlapping.
- `timings.json` gains `mix` (below) with each cue's span (`music: [{source, kind, from, to,
  start, end, volume, duck}]`; `kind` `bed`, `file` or `composed`, `source` `compose: <mood>` for
  composed music).

### Composed music (`compose`)

Music written as notes for the video and played with real instruments (a SoundFont), in a mood:
an original piece every time (never a known tune), the same piece for the same settings. It
needs the optional extra (`pip install "schu-video-generator[music]"`) and a
[SoundFont](#soundfont-soundfont-vidgen-soundfont); without the extra, `vidgen validate` and
`vidgen render` warn and the built-in bed named for the mood below plays (scenes' compose settings
are then ignored), so a project still renders. `vidgen validate` also warns while the default
SoundFont is not downloaded yet (the first render downloads it) and prints a `music:` line per cue
(`compose: playful, composed for the video; scenes storm: mood`, or `compose: playful -> bed
cartoon (no music extra)`).

```yaml
music: {compose: playful}              # a mood with its defaults
```

```yaml
music:
  compose:
    mood: calm
    key: E                             # a note, or 'E major' / 'F# minor' (the mood's mode)
    tempo: 80                          # quarter notes per minute
    seed: 3                            # another seed: another piece in the mood
    bars: 16                           # a 16-bar piece that loops; without bars: composed for the video
    instruments:
      melody: flute                    # a friendly instrument name (vidgen list-music)
      pad: none                        # leave a part out
      drums: soft_drums                # add a part the mood has not
      bass: {volume: -2}               # {instrument, volume, pan, reverb}
  volume: -2                           # the cue's keys as for any source
```

| key | default | |
|---|---|---|
| `mood` | required | `calm`, `focused`, `curious`, `upbeat` (explainers), `playful`, `sleepy`, `tense`, `triumphant` (cartoons); a misspelt name gets a did-you-mean |
| `key` | the mood's | a note (`E`, `Bb`) or a note with the mood's mode (`F# minor` for a minor mood); standard key signatures only |
| `tempo` | the mood's | 40 to 200 quarter notes per minute |
| `instruments` | the mood's | per part — `melody`, `chords`, `pad`, `bass`, `drums` — an instrument name, `none`, or `{instrument, volume, pan, reverb}` (`instrument` a name, default the mood's; `volume` in dB against the other parts: every part is first set to the same loudness; `pan` −1 to 1; `reverb` 0 to 1) |
| `seed` | `1` | an integer ≥ 0: the same settings and seed always give the same notes |
| `bars` | none: the piece [follows the video](#music-that-follows-the-video) | 4 to 128, a multiple of 4: a piece of that length that loops (`vidgen music preview` without `--bars` uses the mood's 16; `playful` 24) |

| mood | for | key, tempo | sounds like (defaults) | without the extra |
|---|---|---|---|---|
| `calm` | explainers | D major, 72, 4/4 | a slow legato piano tune over flowing harp arpeggios, a soft string pad and held cello roots; no drums | `calm` |
| `focused` | explainers | A minor, 96, 4/4 | a sparse vibraphone tune, nylon-guitar arpeggios, a warm synth pad, electric bass in eighths, soft brushed drums | `pulse` |
| `curious` | explainers | F major, 108, 4/4 | a staccato flute tune, harp chords on the off-beats, upright bass root–fifth, a cabasa shaker and claves; a raised fourth (II) and ♭VII for colour | `bright` |
| `upbeat` | explainers | G major, 116, 4/4 | a syncopated marimba tune, strummed steel guitar, a quiet string pad, a syncopated electric bass, a pop drum beat | `bright` |
| `playful` | cartoons | C major, 132, 4/4 | a hopping staccato clarinet tune, marimba chords on the off-beats, a tuba oom-pah, woodblocks answering each other | `cartoon` |
| `sleepy` | cartoons | F major, 66, 3/4 | a celesta lullaby over harp arpeggios, a soft string pad, plucked bass on each bar's first beat; no drums | `lullaby` |
| `tense` | cartoons | D minor, 104, 4/4 | a low, sparse clarinet over a staccato piano ostinato, tremolo strings, bowed double bass, a heartbeat bass drum and rising snare | `pulse` |
| `triumphant` | cartoons | B♭ major, 112, 4/4 | a trumpet fanfare, brass chords on 1 and 3, a string pad, a tuba, a march on orchestral drums with cymbals at new sections | `bright` |

`vidgen list-music` describes each mood precisely in words (instruments and ranges, patterns,
chord progressions) and lists the instrument names: `piano`, `electric_piano`, `harpsichord`,
`celesta`, `glockenspiel`, `music_box`, `vibraphone`, `marimba`, `accordion`, `guitar`,
`steel_guitar`, `clean_guitar`, `bass`, `electric_bass`, `synth_bass`, `violin`, `viola`, `cello`,
`contrabass`, `tremolo_strings`, `harp`, `strings`, `slow_strings`, `choir`, `trumpet`,
`trombone`, `tuba`, `muted_trumpet`, `horn`, `brass`, `alto_sax`, `oboe`, `bassoon`, `clarinet`,
`piccolo`, `flute`, `recorder`, `pan_flute`, `ocarina`, `warm_pad`, `kalimba`, `steel_drums`, and
the drum kits `drums`, `room_drums`, `jazz_drums`, `soft_drums` (brushes), `orchestral_drums`.
(Pizzicato strings and the xylophone are not offered: with GeneralUser GS, symusic 0.5.9 plays
them as a 5 ms click.)

**How a piece is made** (`vidgen/composer.py`). It is a series of 4-bar phrases in the form
A A B A (longer pieces repeat it with a C contrast): a *question* phrase ends on the dominant
(V), its *answer* on the tonic; the last bar turns from the tonic to V7, leading back to the first
bar, so the piece loops without a seam (the reverb's tail is added onto its start). Each section
takes one of the mood's progressions; the melody has a motif (rhythm cells and a shape) that comes
back varied, chord tones on the strong beats, steps of the chord's scale between them, and never
the same bar twice in a row. Chords, pad, bass and drums follow the mood's patterns; a drum fill
ends each phrase. `vidgen music preview` writes a piece as WAV and MIDI to listen to or open in
any notation program.

### Music that follows the video

A `compose:` cue without `bars` is composed when the video is joined, for its real timings
(`vidgen/musicfit.py`): after the narration changes, the next render composes it again.

```yaml
music: {compose: playful}
scenes:
  - id: storm
    type: stage
    music: {mood: tense}               # from this scene's first bar to its end
    beats:
      - text: "Then the cloud did what clouds do."
      - text: "The umbrella left without him."
        music_pause: true              # the music stops just before this line
```

- **Length and bar lines.** The piece lasts exactly as long as the cue, and every scene starts on
  a bar line (with a transition, half-way through it): each scene gets a whole number of bars and
  its own tempo, at most 8 % faster or slower than the mood's. When even 8 % slower is too fast
  (a scene a little longer than its bars), its last bar slows down into a held chord (more on each
  later beat). A scene shorter than one bar at the fastest tempo shares its bars with the next
  scene (its own start is on a bar line, the next scene's is not). On two test renders the bar
  lines fell within 0.02 ms of the scene changes (the notes' onsets in the audio within 4 ms
  where measured cleanly).
- **A scene's mood.** `music: {mood, key, tempo, instruments, seed}` on a scene changes the music
  from that scene's first bar to its end; the next scene goes back to the cue's settings. Another
  `mood` starts from that mood's defaults (the cue's seed kept); otherwise `key`, `tempo`, `seed`
  replace the cue's and `instruments` are added to the cue's. Each run of scenes with the same
  settings is one piece in the form above (phrases may cross scene changes); a run that does not
  end the cue ends on its own cadence. Only under a `compose:` cue without `bars`: elsewhere
  `vidgen validate` reports it. (In the score's MIDI export each mood's piece carries its own key
  and time signature from its first bar.)
- **Swells on reveals.** Where a beat reveals something — a step of the scene's own reveal
  (bullets, chart bars, code steps: as the host's pointing sees them), a written `reveal` action,
  a `sting: reveal` — the notes of the two beats before it grow up to 20 % louder and a held chord
  tone starts on it (pad, else chords, else melody). Not on the first beat, in the closing bar,
  or within two beats of the swell before.
- **Pauses.** `music_pause: true` on a beat silences the music from the last beat at least 0.4 s
  before the line until the first bar line after the line ends. Automatically (`music_pause:
  false` on the beat turns it off): before a `card` scene (not the cue's first), until the card's
  first line ends; and before the cue's last line when it has at most 8 words and its scene has
  a line before it — then the closing chord is struck as that line ends (a "button") if at least
  0.3 s of the cue is left (a chord shorter than its bar at 300 BPM runs past the cue's end and
  is cut there).
- **The ending.** The last bar is the tonic chord held (the melody on the tonic, one last kick and
  cymbal), the bar before it holds V and slows down (each beat 6 % longer than the one before),
  and the last bar's beats last 1.3 beats. The cue's `fade_out` never starts before that chord.
- **Stings.** A beat's `sting:` under composed music (and with the extra) is played by the
  music's own instruments, in its key and tempo (the scene's settings): `reveal` a pickup on the
  dominant then the tonic chord held with a cymbal, `comic` two tom hits and a cymbal with the
  bass and a short tonic chord, `sad` the melody falling three semitones onto the tonic. Each is
  set to the loudness of the built-in sting it replaces and keeps its `at`, `gain` and ducking; a
  project's own `assets/sfx/sting_*.wav` is kept. Without composed music the built-in stings play.
- `timings.json`'s `mix.music` entry of the cue gains `fit`: `{sections: [{scenes, start, bars,
  tempo, mood}], swells, pauses, closing}` (video seconds).

### `vidgen music preview`

`vidgen music preview [PROJECT] [--mood M] [--seed S] [--bars N] [--key K] [--tempo T] [--out DIR]`
composes the project's first `compose:` cue (the options change it; another `--mood` starts from
that mood's defaults), or `--mood M` outside a project, renders it with the project's SoundFont and
writes `DIR/<mood>-seed<S>.wav` (one pass plus the 3 s reverb tail, at −28 LUFS) and `.mid`
(type 1, a track per part, section markers). It prints the key, tempo, parts, the chords of each
phrase and the measured loudness and true peak. Needs the `music` extra. `--json`: see
[below](#vidgen-music---json); MCP tool `music_preview` (its `out` defaults to `build/mcp/music`
under the server's root).

### Loudness of the final mix (`audio`)

```yaml
audio: {normalize: auto, target_lufs: -16, true_peak: -1.5}   # the defaults
```

| key | default | |
|---|---|---|
| `normalize` | `auto` | scale the final mix to `target_lufs`: `true`, `false`, or `auto` = only when the video has music (a narration-only video keeps the narration's own level, that of its MP3s). Never while no beat has its narration MP3 yet (a preview timed from word counts would lift the music to the target on its own) |
| `target_lufs` | `-16` | integrated loudness (EBU R128 / ITU-R BS.1770-4, gated) of a normalised mix: −16 for web and social platforms (−14 for louder streaming targets), −23 / −24 for broadcast |
| `true_peak` | `-1.5` | dBTP ceiling of a mixed track: a look-ahead limiter (10 ms, smooth) keeps the 4x-oversampled peaks under it, so the louder mix never clips |

When the mix is written (music, or `normalize: true`) vidgen measures the sum, applies one gain to
reach the target, then the limiter; everything is deterministic numpy. Narration plays at its
MP3s' level (a mono MP3 at full level on both channels; ElevenLabs voices measure about −21.4
LUFS), so reaching −16 lifts it ~5 dB and the limiter shaves speech peaks by a few dB. Without music and with `normalize: auto` / `false` the narration and effects are joined as
before (FFmpeg sums them), and the loudness is only measured. `vidgen render` prints the result
(`loudness: -16.0 LUFS integrated, true peak -1.9 dBTP (normalised to -16, +5.4 dB; music:
calm)`), and `timings.json` / `render --json` carry `mix`: `{mixed, normalized, target_lufs,
true_peak_limit, gain_db, integrated_lufs, true_peak_dbtp, limited_db, music}` (measured on the
mix before the AAC encode; the limiter aims 0.4 dB under `true_peak` because the encode can
raise the peak by ~0.2 dB, so the MP4 stays under it).

### `vidgen list-music`

`vidgen list-music [PROJECT] [--render-dir DIR] [--json]` describes the built-in beds in words —
instruments, key, tempo, chords, mood, frequency range — for an author who cannot listen, and
lists the project's `assets/music` files (length, measured loudness); `--render-dir` writes one
loop of every bed as `DIR/<name>.wav`. Then the moods of [composed music](#composed-music-compose)
(key, tempo, meter, length, each part's instrument and pattern, the melody's range and style, the
chord progressions, the bed played without the extra) and every instrument name (General MIDI
program, range, what it sounds like). JSON: see [below](#vidgen-list-music---json).

### SoundFont (`soundfont`, `vidgen soundfont`)

Composed music (music written as notes and played with real instruments,
[`compose:`](#composed-music-compose)) needs the optional extra and a SoundFont, a bank of
recorded instruments:

- **The extra**: `pip install "schu-video-generator[music]"` installs symusic 0.5.9 (MIT, ~3 MB
  of wheels for Windows, macOS and Linux; the exact version because 0.6.0 cannot render with a
  SoundFont). Without it, `vidgen validate` and `vidgen render` warn (naming this command) and
  each `compose:` cue plays its mood's built-in bed instead; `vidgen music preview` stops with an
  error naming it.
- **The SoundFont**: by default **GeneralUser GS 2.0.3** (32.3 MB, General MIDI instruments and
  drum kits). vidgen does not ship it: the first composed render (or `vidgen soundfont fetch`)
  downloads it from
  `https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2` into
  vidgen's cache folder, `soundfonts/GeneralUser-GS.sf2` under: `VIDGEN_CACHE_DIR` if set, else
  `%LOCALAPPDATA%\vidgen` on Windows, `~/Library/Caches/vidgen` on macOS, `$XDG_CACHE_HOME/vidgen`
  or `~/.cache/vidgen` on Linux. The download goes to a temporary file, is checked (32,319,396
  bytes, sha256 `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`) and only then
  moved into place; after that no network is needed. A file that does not match (the upstream
  file changed, or the cached copy was altered) is an error, never used.
- **Your own SoundFont**: `soundfont: PATH` uses any SF2 or SF3 file instead (relative to the
  project, or absolute), and nothing is downloaded. `vidgen validate` reports a missing file or one
  that is not a SoundFont. If the download fails (offline) or no longer matches, download a
  SoundFont yourself (GeneralUser GS: <https://www.schristiancollins.com/generaluser>) and set
  this key.

```yaml
soundfont: assets/soundfonts/MyBank.sf2   # optional; default: GeneralUser GS 2.0.3 from the cache
```

`vidgen soundfont fetch [--force]` downloads the default SoundFont now (`--force`: again, e.g.
after a mismatch). `vidgen soundfont info [PROJECT]` shows the SoundFont the project uses (or the
default outside a project): path, size, sha256, whether the default file is the expected one, its
licence line, and whether symusic is installed.

**Licence and credit.** GeneralUser GS's licence (v2.0) lets you use it without restriction in
your own music, private or commercial; no attribution is required. A credit is welcome, for
example in the video's description:

> Music rendered with the GeneralUser GS SoundFont by S. Christian Collins (https://www.schristiancollins.com/generaluser).

## Transitions (`transition`)

How the video passes from one scene to the next. Without any, scenes are joined by cuts (every
built-in scene fades out over its last 0.5 s by itself).

```yaml
transition: crossfade                  # the default between scenes (not before the first one)
scenes:
  - id: intro
    type: title
    params: {title: "Hello"}
    transition: fade_color             # the first scene may fade in from a colour
    beats: [{text: "Welcome."}]
  - id: part2
    type: chapter
    params: {number: 2, title: "Results"}
    duration: 3
    transition: {type: fade_color, color: surface, duration: 1.2}   # into this scene
  - id: summary
    type: bullets
    params: {items: ["Fast", "Small"]}
    transition: cut                    # this one is a plain cut
    beats: [{text: "In short: fast and small."}]
  - id: chart
    type: bar_chart
    params: {title: "Speed", labels: ["A", "B"], values: [3, 5]}
    transition: push                   # slides in from the right, pushing the bullets out to the left
    beats: [{text: "B is faster."}]
  - id: outro
    type: end_card
    params: {title: "Thanks"}
    transition: {type: wipe, direction: up, soft: true}   # a soft edge sweeps up, uncovering it
    duration: 3
```

| type | what you see | timing |
|---|---|---|
| `cut` | the next scene straight after the previous one (which fades out by itself) | unchanged |
| `crossfade` | the two scenes blend into each other | the scenes **overlap** by `duration`: the next one starts that much earlier, the video gets that much shorter |
| `fade_color` | the previous scene fades to `color` over the first half of `duration`, the next one fades in from it over the second half | no overlap: the video keeps its length |
| `push` | the next scene slides in from one side and pushes the previous one out the other side | overlap, like `crossfade` |
| `wipe` | an edge sweeps across the picture, uncovering the next scene behind it (`soft`: a blurred edge) | overlap, like `crossfade` |
| `iris_out` | a cartoon iris: a circle closes on a `character` (its head, with a pause on the face) or a point `at` of the previous scene over the first half of `duration`, to `color`; then a circle opens on the next scene from the frame's centre | no overlap, like `fade_color` |
| `iris_in` | a circle closes on the previous scene's centre, then opens on a `character` or a point `at` of the next scene | no overlap, like `fade_color` |

| key | default | |
|---|---|---|
| `type` | `cut` | `cut`, `crossfade`, `fade_color`, `push`, `wipe`, `iris_out` or `iris_in` (a plain string is the type with its defaults) |
| `duration` | `crossfade` 0.5, `fade_color` 1.0, `push` / `wipe` 0.6, `iris_out` / `iris_in` 1.2 | seconds, at most 5; not allowed on a cut |
| `color` | the theme's `background`; black for an iris | `fade_color`, `iris_out`, `iris_in` only: a theme colour token (`surface`, `accent`, ...), `background`, or hex |
| `direction` | `left` (16:9, square), `up` (9:16) | `push` / `wipe` only: where the pictures (push) or the edge (wipe) move: `left`, `right`, `up`, `down`. `left` = the next scene comes in from the right; `up` = from below (like scrolling a phone feed) |
| `soft` | `false` | `wipe` only: a soft, blurred edge (FFmpeg's `smooth*` transitions) instead of a hard one |
| `character` | none | `iris_out` / `iris_in` only: the character the circle closes on (`iris_out`: one on the stage of the scene before, where its head is as that scene ends) or opens on (`iris_in`: one on this scene's stage, where its head is as it starts); the circle follows the head and pauses around it. `vidgen validate` checks it is on that stage |
| `at` | the centre | `iris_out` / `iris_in` only, instead of `character`: the point `[x, y]` the circle closes or opens on, fractions of the frame from its top-left corner (`[0.3, 0.4]`) |

A scene's `transition:` is the way **into** that scene; the video's `transition:` is the default
for every scene but the first (a crossfade, push, wipe or iris_out on the first scene is an error: nothing
comes before it; `fade_color` there fades the video in from the colour, `iris_in` opens on it). A video-level `push`
with no `direction` follows each variant's frame: left in the 16:9 video, up in a 9:16 variant.

```yaml
  - id: later
    type: card                                       # a cartoon title card
    params: {text: "Later that day…"}
    duration: 2.5
    transition: {type: iris_out, character: pip}     # the scene before closes on pip's head
  - id: hill
    type: stage
    params: {characters: [{name: kit, at: right}]}
    transition: {type: iris_in, at: [0.75, 0.6]}     # this scene opens on that point
    beats: [{text: "Up on the hill, Kit was waiting."}]
```

The irises are drawn inside the scenes' renders, like a `fade_color` (the colour covers the
picture outside the circle, the overlays stay on top), so the join stays a cut there and no
FFmpeg filter is involved: they work with every FFmpeg vidgen supports (checked with 6.1, 7.1
and 8.1), and storyboards and stills show them.

- **Speech never overlaps.** A transition covers only the *silent end* of the scene before it:
  the frames after its narration ends (its pad and fade-out; a whole silent scene). When that is
  shorter than the transition (a long crossfade, a scene without a fade-out), the scene before is
  **held** on its last picture that much longer, and `vidgen validate` says so ("'a' is held
  0.20 s longer..."). The defaults fit the built-in scenes' 0.5 s fade-out plus the 0.35 s pad,
  so nothing is held. The next scene's narration starts with it, during a crossfade.
- **The outgoing scene stops fading out by itself**: with a transition other than a cut after it,
  a built-in scene (anything ending with `self.finish()`) holds its picture over its 0.5 s outro
  and the transition takes it away.
- **Every time follows**: scene starts in `timings.json` (scenes with a transition get
  `transition: {type, duration, overlap}`, plus `direction` for a push / wipe), the SRT, captions, chapters and the chapter
  indicator, the progress bar, lower thirds, sound effects, music cues and ducking, storyboard
  times. They all come from the [planned timeline](#overlays), which knows the overlaps.
- **Overlays stay put.** During a crossfade both scenes draw the *incoming* scene's overlays
  (captions, watermark, progress bar, ...), so the blend shows them once, unchanged — no doubled
  captions or ghosted watermark. A `fade_color` fades the scene's picture only; overlays stay on
  top of the colour. A `push` or `wipe` moves the pictures, so overlays are kept out of them: both
  scenes render the frames they share *without* overlays, the incoming scene's render writes
  those frames' overlays to a separate clip (`build/.../scenes/<id>.overlay.mov`, RGBA), and the
  join draws it over the moving pictures — the watermark, progress bar and captions stay where
  they are and appear once. (The overlays switch to the incoming scene's at the transition's
  start, as in a crossfade.) Stills of a scene taken inside such a transition show no overlays;
  beat-end stills are never there.
- **Sound**: in a crossfade the scenes' sound overlaps too: the earlier scene's silent tail fades
  out under the next scene's start (only a clip's sound can be there). Effects and music are
  placed on the video's timeline as always.
- **Encoding**: with any crossfade, push or wipe the join blends the scenes with FFmpeg (`xfade`:
  `fade`, `slide<direction>`, `wipe<direction>` / `smooth<direction>`) and encodes the video once
  (H.264, CRF 18, visually lossless next to the scenes' own encoding) instead of copying the
  scenes' streams (the gallery's 3:49 preview: ~40 s on 2 CPUs, most of it the H.264 encode;
  much less than rendering its scenes); a video with only cuts and
  colour fades is joined as before. Colour fades are drawn inside the scenes' renders, so
  storyboards and stills show them; crossfades, pushes and wipes exist only in the joined video
  (`vidgen render --scene ID` alone shows the outgoing scene held still).
- A transition changes the renders of the scenes on both sides of it (the storyboard re-renders
  both). `vidgen render --scene ID` reuses the other scenes as they are: render the scene before
  a new transition too, or the join shortens a crossfade to the silence it finds (with a
  warning).

### Continuity: carrying objects into the next scene (`carry`)

A scene can start with objects of the scene before it, exactly where, how big and in which
colour they were — a *match cut* — and then move them into its own layout:

```yaml
  - id: part2
    type: chapter
    params: {number: 2, title: "Charts and numbers", icon: chart-column}
    duration: 3
  - id: speedup
    type: stat
    transition: cut                 # a cut: the carried icon does not move at the cut
    carry: [icon]                   # the card's icon flies into this scene's icon
    params: {value: 0.4, unit: "min", label: "per minute of video", icon: chart-column}
    beats: [{text: "Renders take seconds now."}]
  - id: part3
    type: chapter
    params: {number: 3, title: "Results"}
    duration: 3
  - id: results
    type: bullets
    carry: ["title -> heading"]     # the card's title becomes this scene's heading
    params: {heading: "Results", items: ["Faster", "Smaller"]}
    beats: [{text: "Two results stand out."}]
```

- **Entries** are [target names](#beat-actions) of the scene before (`title`, `icon`, `item2`,
  `bar:4K`...); `"a -> b"` moves the scene before's target `a` into this scene's target `b`
  (default: the target of the same name; `title` and `heading` stand for each other as in
  actions). `vidgen validate` checks both names for built-in types, with suggestions.
- **The scene before** keeps those targets on screen in its fade-out (only the rest fades) and
  records their final look (every vector shape: outline, fill, stroke) in
  `build/.../carry/<scene>.json`.
- **This scene** shows that record from its first frame, so across the cut nothing changes. When
  it brings in the destination target (its own entrance animation), the copy **moves** into it
  instead: shape by shape when both have as many shapes (the same text or icon at another
  place, size or colour — glyphs glide into place), else a cross-fade stretched between the two
  boxes (a title flowing into a heading with different words). A destination the scene brings in
  some other way makes the copy fade out as it appears; a destination the scene does not have
  fades it out with the scene's first animation (with a warning).
- **Transitions**: a cut (the natural choice) or a crossfade keep the carried objects in place;
  `fade_color`, `push`, `wipe` and the irises fade, move or cover them with the picture (`vidgen validate` warns).
- **Rendering**: the carrying scene is rendered after the scene before it (with `--jobs` it waits
  for it). `vidgen render --scene ID` / `storyboard --scene ID` also render the scene before when
  its record is missing or out of date, and the carrying scene when the scene before was
  rendered with other inputs since.
- Only vector shapes are carried (text, icons, shapes, TeX); pictures and clips are not (a
  warning names them). Custom scenes can take the copy themselves with `self.carry_in(name)`
  ([EXTENDING.md](EXTENDING.md)).

## Built-in scenes

Every scene has a `type`, `params` (checked by `vidgen validate`; unknown keys are errors) and
either `beats` (narrated) or a `duration` (silent). `vidgen list-scenes` prints every type with
its params. Conventions shared by all built-ins:

- **Colors** (`color` in the tables) are theme tokens (`text`, `dim`, `accent`, `highlight`,
  `primary`, `secondary`, `tertiary`, `surface`, or your own `theme.colors`) or hex (`"#FF6B6B"`).
  **Sizes** (`size`) are theme size tokens (`title`, `subtitle`, `heading`, `body`, `caption`,
  `small`) or a number of points. Unknown tokens are reported by `vidgen validate`.
- **Beats drive the reveal.** Each type splits its content into reveal steps (listed per type
  below). Step *i* appears during beat *i*; with more steps than beats they are spread evenly;
  with more beats than steps the extra beats hold the finished picture. Animations take a
  fraction of each beat and never make a beat longer than its narration (+ `narration.pad`).
  A silent scene shows all steps within its `duration`.
- After the last beat the scene fades out (0.5 s; 1 s for `end_card`; `text_card` does not fade).
- **Any aspect ratio.** Layouts use the frame size, so the same config works for 16:9 and a
  vertical 9:16 variant; long text is wrapped and shrunk to fit. In a vertical frame short
  content grows into the tall frame: headings and list text 1.3x (`bullets`, `icon_grid`
  labels, `comparison`), a vertical `timeline` or a `process` column up to 1.5x, while it fits;
  a `map` with the `world` view keeps only the longitudes of its countries, pins and arcs.
- **Header band.** The line at the top of the frame is `heading` in `bullets`, `icon_grid`,
  `comparison`, `timeline`, `diagram`, `process`, `network` and `title` in the charts, `table`,
  `map`, `code`, `code_morph`, `code_walkthrough`, `terminal`, `equation_derivation`, `function_plot`, `number_line`, `screenshot`, `video_clip`. Every
  one of these types accepts **both names** (also `heading_size` / `title_size`,
  `heading_color` / `title_color`; `vidgen list-scenes` shows `(also: title)`), and the target
  `title` selects a `heading` and the reverse. Not in `title`, `chapter` and `end_card`, whose
  `title` is their main text.
- **Per-beat content** is a `steps` list in `code_walkthrough`, `terminal`, `equation_derivation`,
  `screenshot`, `video_clip` and `map` (`versions` in `code_morph`): step *i* plays at beat *i*. Elsewhere the scene splits
  its content into steps itself (`reveal`); `diagram`'s explicit `steps` are such reveal steps.
  A `highlight` param adds a last step that marks something and dims the rest; where it takes a
  list, one item may be written alone (`highlight: Lint`).
- **Too much content.** Types that fit their content (`table`, `timeline`, `diagram`,
  `process`, `comparison`, `heatmap`, `pie`, `equation_derivation`, `code_walkthrough`) shrink
  text down to the readable minimum (`vidgen lint`'s `min_font`), then scale the whole drawing
  and log a warning at render time — `scene 'x': the timeline's 10 events do not fit this frame
  at the readable size; split it into two timelines (or shorten titles and texts)` — not in
  `vidgen validate`, because it depends on the variant's frame and type scale.
- **Unknown keys** are reported with the closest names: `scenes[2].params.dim_prev: unknown
  parameter 'dim_prev'; did you mean 'dim_previous'? (known: heading, items, ...)`.
- Text-only types need no LaTeX; only `equation` and `equation_derivation` do.

### `title`

Steps: (1) icon, kicker, title and subtitle, (2) authors.
[Action targets](#beat-actions): `icon`, `kicker`, `title`, `subtitle`, `authors` (those the card has).

| param | type | default | |
|---|---|---|---|
| `title` | str | required | wrapped to fit; may contain `\n` |
| `subtitle` | str | `""` | |
| `kicker` | str | `""` | small label above the title |
| `authors` | list[str] | `[]` | one line each |
| `highlight` | str | `""` | part of the title drawn in `highlight_color` |
| `color`, `highlight_color`, `subtitle_color`, `kicker_color`, `authors_color` | color | `text`, `highlight`, `text`, `primary`, `dim` | |
| `icon` | icon | none | optional icon (name or alias, see [Icons](#icons)) |
| `icon_color` | color | `primary` | |
| `icon_position` | `above` \| `left` | `above` | above the kicker/title, or left of the title block, level with it (`left` falls back to `above` in a vertical frame) |

```yaml
- id: intro
  type: title
  params:
    kicker: "TECHNICAL REPORT"
    icon: brain-circuit
    title: "Saving 77% of the Parameters"
    highlight: "77%"
    subtitle: "in Large Language Models"
    authors: ["Ada Lovelace · Analytical Engine Society"]
  beats:
    - text: "What if a large language model could lose most of its parameters?"
    - text: "This report, by Ada Lovelace, shows how."
```

### `bullets`

Steps: one per item (the heading comes with the first). `reveal: all` shows every item in beat 1.
[Action targets](#beat-actions): `heading`, `item<N>` (1-based), `item:<text>`.
The heading sits in the `header` region, the list is centered in the space below it. In a
vertical video the heading is 1.3x larger and a short list grows up to 1.3x and spreads out to
use the taller frame.

| param | type | default | |
|---|---|---|---|
| `items` | list[str \| item] | required | at least one; each a string or `{text, icon}` (below) |
| `heading` | str | `""` | |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `numbered` | bool | `false` | `1.` `2.` ... instead of `marker` |
| `marker` | str | `"•"` | |
| `dim_previous` | bool | `false` | fade earlier items when a new one appears |
| `size`, `heading_size` | size | `body`, `heading` | shrunk automatically for long lists |
| `color`, `heading_color`, `marker_color` | color | `text`, `text`, `primary` | `marker_color` also colours icons |

**Icons.** An item can be `{text: "...", icon: NAME}` (`text` required, `icon` optional; plain
strings keep working, and both forms mix in one list). The icon replaces the bullet; with
`numbered: true` it stands between the number and the text. Icons form a column of their own,
sized to the item text and centred on the capitals of its first line; in a list that mixes
icons and plain items, the plain items' bullets sit centred in that column, so all texts start
at one edge. Icons take `marker_color` and fade with their item (`dim_previous`).

```yaml
- id: points
  type: bullets
  params:
    heading: "Takeaways"
    items:
      - {text: "Fewer parameters", icon: layers}
      - {text: "Same validation loss", icon: chart-line}
      - "One GPU, three days"
    dim_previous: true
  beats:
    - text: "First, the model is much smaller."
    - text: "Second, it learns just as well."
    - text: "And it trained on a single GPU."
```

### `icon_grid`

Icons with a label (and an optional smaller sublabel) in a grid. Steps: one per item (the
heading comes with the first), or one per entry of `groups`; `reveal: all` shows every item in
beat 1; with `highlight`, a last step dims the other items and enlarges the highlighted one in
`highlight_color`. Each item fades in with its icon growing from its centre.
[Action targets](#beat-actions): `heading`, `item<N>` (1-based), `item:<label>` (icon, label and sublabel).

Layout: the heading sits in the `header` region and the grid fills the space below it. Without
`columns`, the shape (rows x columns) is chosen for the frame with `grid_shape` (see
docs/EXTENDING.md), trying narrow and wide cells and keeping the layout whose labels and icons
come out largest: 4 items make one row in 16:9 and a 2 x 2 grid in 9:16, 12 items 2 x 6 or (with
longer labels) 3 x 4 in 16:9. Labels share one size (1.3x in a vertical frame), wrap inside
their column and are reduced
(down to the readable minimum that `vidgen lint` accepts) when they need the room; a word wider
than its column reduces all labels. Icons are as large as the rest of the row allows (at most
1.9 units, a quarter of the frame's shorter side). A last row with fewer items is centred;
labels and sublabels of a row share their baselines. 2–12 items read well in 16:9 and 9:16 (at
most 16).

| param | type | default | |
|---|---|---|---|
| `items` | list[item] | required | 1–16 items `{icon, label, sublabel}`: `icon` (name or alias), `label` (str, required), `sublabel` (str, `""`) |
| `heading` | str | `""` | |
| `columns` | int | auto | fixed number of columns |
| `reveal` | `per_beat` \| `all` | `per_beat` | ignored when `groups` is given |
| `groups` | list[list[int \| str]] | none | reveal steps, each a list of items by 0-based index or label; every item exactly once |
| `highlight` | int \| str | none | item (0-based index or label) emphasised in a last step |
| `badge` | bool | `true` | draw each icon on a soft disc in its colour |
| `icon_color` | `palette` \| color | `primary` | one colour for all icons, or `palette`: one `theme.palette` colour per item |
| `color`, `sublabel_color`, `heading_color`, `highlight_color` | color | `text`, `dim`, `text`, `highlight` | |
| `size`, `sublabel_size`, `heading_size` | size | `body`, `caption`, `heading` | |

```yaml
- id: stack
  type: icon_grid
  params:
    heading: "What the platform covers"
    icon_color: palette
    highlight: "Security"
    items:
      - {icon: cpu, label: "Compute", sublabel: "GPUs and CPUs"}
      - {icon: database, label: "Storage"}
      - {icon: network, label: "Networking"}
      - {icon: shield-check, label: "Security", sublabel: "zero trust"}
    groups: [[0, 1], [2, 3]]       # two items per beat
  beats:
    - text: "Compute and storage come first."
    - text: "Then networking and security."
    - text: "And security matters most."
```

### `bar_chart`

Steps: all bars (`reveal: all`, default) or one per bar (`per_beat`), then one per entry of
`changes`, then — if `highlight` is set — a focus step that dims the other bars. Bars grow
while their value labels count up.
[Action targets](#beat-actions): `title`, `bar<N>` (1-based) and `bar:<label>`, each a bar with
its value and category labels (beat actions can do more than the one `highlight` step), and
`change<N>` (all bars; revealing it plays change N).

**Values that change between beats**: `changes` lists the values the bars change to, one list
per change (one value per label, in the order of `labels`). At a change every bar grows or
shrinks to its new value while its label counts, and with `sort: true` the bars re-sort,
largest first (at the top when horizontal), sliding past each other; a bar keeps its colour
and its targets. Change N plays in its own step (its own beat when there is one), or on a
spoken word with `{reveal: change<N>, at: "@word"}` (that step then waits for the action). The
bars keep one scale over every change (the chart has no value axis to rescale), so their heights
compare across changes; the value labels are sized for every value they will show.

Like every chart, the title stands in the `header` band (1.3x in a vertical frame) and label
sizes are theme size tokens that never go below the readable minimum (see
[charts](#charts-common-to-all-chart-types)). Value labels keep their size where they can: one
too wide for its bar shrinks a little, then a word unit (`" min"`) moves under the number, then
it shrinks further; in a vertical frame the bars turn horizontal when even the readable size
does not fit (or with more than 5 bars), unless `horizontal` is set.

| param | type | default | |
|---|---|---|---|
| `labels` | list[str] | required | |
| `values` | list[float] | required | same length as `labels`; negatives allowed |
| `title` | str | `""` | |
| `caption` | str | `""` | note under the chart (e.g. the data source) |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | category labels |
| `value_size` | size | `body` (`caption` with more than 6 bars) | value labels |
| `unit` | str | `""` | appended to every value label (`"%"`, `" ms"`) |
| `value_format` | str | automatic | Python format, e.g. `"{:.1f}"`, `"{:,.0f}"`, `"{:.0%}"`; default shows the decimals the values need |
| `colors` | color \| list[color] \| `palette` | `primary` | one color, one per bar, or `theme.palette` |
| `highlight` | int \| str | none | bar index (0-based) or label |
| `highlight_color` | color | `highlight` | highlighted value label |
| `horizontal` | bool | auto | default: vertical bars; horizontal in a portrait frame with more than 5 bars or value labels too wide for vertical ones |
| `reveal` | `all` \| `per_beat` | `all` | |
| `baseline` | float | `0` | value the bars start from (e.g. `1.0` for losses; say so in `caption`) |
| `changes` | list[list[float]] | `[]` | values the bars change to, one list per change (one value per label); see above |
| `sort` | bool | `false` | order the bars by value, largest first; they re-sort at each change |

```yaml
- id: params
  type: bar_chart
  params:
    title: "Non-embedding parameters"
    labels: ["phi-3", "kphi-3 (2 layers)", "kphi-3 (3 layers)"]
    values: [227, 35, 53]
    unit: "M"
    colors: palette
    highlight: 2
  beats:
    - text: "The baseline has 227 million parameters; our models far fewer."
    - text: "The three-layer version keeps just 23 percent."
```

Bars that change and re-sort, the last change on a word:

```yaml
- id: langs
  type: bar_chart
  params:
    title: "Most loved languages"
    labels: [Python, Rust, Go, Zig]
    values: [62, 48, 31, 12]
    changes:
      - [58, 66, 30, 20]
      - [55, 72, 41, 35]
    sort: true
    unit: "%"
  beats:
    - text: "In the first survey, Python led by a wide margin."
    - text: "A year later Rust overtook it."
    - text: "Then Go and Zig both climbed as well."
      actions: [{reveal: change2, at: "@climbed"}]
```

### `line_chart`

Steps: one per series (`reveal: per_beat`, default; the axes come with the first) or all
series in beat 1 (`all`), then one per entry of `changes`. Each line ends with a `name value` label; when those labels would be
too wide (e.g. in portrait) the names move to a legend, placed in a corner of the plot that no
line crosses (else above the plot). Axis labels are plain text (no LaTeX); tick labels that
would collide are thinned to every second (third...) one.
[Action targets](#beat-actions): `title`, `axes`, `series<N>` (1-based), `series:<name>` (a line with its markers
and end label), `point:<name>@<x>` (one data point, `x` as its tick label reads:
`point:sparse@8`; without `dots` the point appears as a dot when an action uses it) and
`change<N>` (the axes and lines; revealing it plays change N).

**Values that change between beats**: `changes` lists the values the lines change to, one
entry per change: `{name: [values]}` for the series that change (the others keep theirs) or,
with one series, just `[values]`; `x` stays. At a change every line morphs to its new values,
its markers and end label riding along (the value counting). The y axis rescales when the new
values leave it or would span less than half of it: the old gridlines and tick labels slide to
where their values lie on the new axis as they fade, the new ones slide in. `y_min` / `y_max`
fix an end; `rescale: false` keeps one axis covering every change. Change N plays in its own
step, or on a spoken word with `{reveal: change<N>, at: "@word"}`.

**A cursor on a line**: `{trace: series1, to: 4}` (or `series:<name>`) sweeps a dot along that
line to x = 4 with the line's value over it (between two points, the straight line's), on a
word with `at: "@word"`; on category `x`, `to` is the position from 1 (`to: 3`: the third).
The cursor stays and rides along when the line changes; `until: <beat>` takes it back to the
first x.

| param | type | default | |
|---|---|---|---|
| `x` | list[float] \| list[str] | required | numbers (increasing) or category names |
| `series` | `{name: [values]}` or list of `{name, values, color}` | required | one value per `x`; a series' `color` defaults to the colour of the [term](#one-colour-per-concept-terms) its name is, else the palette's |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | tick and axis labels, end labels, legend |
| `x_label`, `y_label` | str | `""` | |
| `y_min`, `y_max` | float | from the data | |
| `value_format` | str | automatic | for y ticks and end labels (ticks default to the decimals they need) |
| `x_format` | str | `"{:g}"` | for numeric `x` |
| `unit` | str | `""` | appended to y values |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `annotate` | bool | `true` | end-of-line labels |
| `dots` | bool | auto | markers at the data points (default: up to 12 points) |
| `changes` | list of `{name: [values]}` (or `[values]` with one series) | `[]` | values the lines change to, one entry per change; see above |
| `rescale` | bool | `true` | at a change, rescale the y axis when the values leave it or span less than half of it; `false`: one axis for every change |

```yaml
- id: loss
  type: line_chart
  params:
    title: "Validation loss"
    x: [1, 2, 3, 4, 5]
    x_label: "epoch"
    series:
      - {name: baseline, values: [2.1, 1.8, 1.66, 1.58, 1.53]}
      - {name: sparse, values: [2.2, 1.9, 1.68, 1.55, 1.49], color: tertiary}
  beats:
    - text: "Here is the baseline."
    - text: "And the sparse model, which ends lower."
```

Lines that change (the axis rescales) and a cursor on a word:

```yaml
- id: loss
  type: line_chart
  params:
    title: "Training loss"
    x: [1, 2, 3, 4, 5, 6]
    x_label: epoch
    series:
      loss: [2.4, 1.9, 1.5, 1.3, 1.2, 1.15]
      accuracy: [0.3, 0.5, 0.6, 0.65, 0.7, 0.72]
    changes:
      - {loss: [2.4, 1.6, 1.0, 0.7, 0.5, 0.42]}
      - {loss: [0.9, 0.5, 0.3, 0.2, 0.15, 0.12], accuracy: [0.5, 0.7, 0.8, 0.85, 0.88, 0.9]}
    reveal: all
  beats:
    - text: "Here are loss and accuracy over six epochs."
      actions: [{trace: "series:loss", to: 4, at: "@six"}]
    - text: "With a better learning rate the loss drops much faster."
    - text: "And after pretraining, both curves start far better."
```

### Charts: common to all chart types

`bar_chart`, `line_chart`, `scatter`, `histogram`, `pie` and `heatmap` share their frame (and
the axis charts their axes; the helpers are public for project charts, see EXTENDING.md
"Charts"):

- **Title** in the `header` band at the top (bold, the theme's `heading` font role, 1.3x larger
  in a vertical frame), **caption** at the bottom; the plot gets the space between.
- **Label sizes** are theme size tokens (`label_size`, default `caption`), never below the
  readable minimum that `vidgen lint` checks, so they grow with the type scale (`large` in
  9:16) instead of staying small.
- **Ticks** are round numbers (steps of 1, 2, 2.5 or 5 x 10^k; powers of ten on a log axis),
  written with the decimals they need and `k`/`M`/`B` from 10 000 on (`20k`), unless a format
  is given. Labels that would collide are thinned. Gridlines are faint dashes at the labelled
  ticks.
- **Legends** (several series) stand in a corner of the plot that covers no data, on a faint
  framed panel, as one row or stacked; when every corner has data, above the plot.
- **Colours** are theme tokens: series and slices take the palette, colour scales
  (`heatmap`) are mixed from theme colours, and text written on a filled shape (a slice, a
  cell) switches between the theme's text and background colour so it keeps 4.5:1 contrast.

### `scatter`

Points of one or more series on two numeric axes. Steps: one series per beat (`reveal:
series`, default; the axes come with the first), its points popping in from left to right;
`groups`: the points of each `group` (in order of first use; points without one come first);
`all`: everything in beat 1. Then, if set, the `trend` line grows (a step of its own) and the
`highlight` step rings the chosen points and dims the others. Point labels stand beside their
point where they cover no other point, label or trend line.
[Action targets](#beat-actions): `title`, `axes`, `legend`, `series<N>`, `series:<name>`,
`point:<series>@<N>` (1-based, in the order written) and `point:<series>@<label>`, `trend`
(every trend line with its text) and `trend:<series>` (with `trend: each`).

| param | type | default | |
|---|---|---|---|
| `series` | `{name: [points]}` or list of `{name, points, color, marker}` | required | a point is `[x, y]`, `[x, y, label]` or `{x, y, label, group}`; `marker` `auto` (circle, square, triangle, diamond by position), `circle`, `square`, `triangle`, `diamond` |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | ticks, axis labels, point labels, legend, trend text |
| `x_label`, `y_label` | str | `""` | axis titles |
| `x_min`, `x_max`, `y_min`, `y_max` | float | from the data | axis ends (points outside are an error) |
| `x_log`, `y_log` | bool | `false` | logarithmic axis (positive values) |
| `x_format`, `y_format` | str | automatic | Python format of the tick labels |
| `x_unit`, `y_unit` | str | `""` | appended to tick labels |
| `trend` | `none` \| `each` \| `all` | `none` | least-squares line per series or through every point (linear axes) |
| `trend_label` | `none` \| `equation` \| `r2` \| `both` | `none` | `y = 0.52x + 1.3`, `R² = 0.87` beside the line |
| `trend_color` | color | series color / `text` | |
| `reveal` | `series` \| `groups` \| `all` | `series` | |
| `show_labels` | `all` \| `highlight` \| `none` | `all` | which point labels are written (`highlight`: only highlighted points', in the highlight step) |
| `highlight` | list[str] | `[]` | points for a last step: `"<series>@<N>"`, `"<series>@<label>"` or a label |
| `highlight_color` | color | `highlight` | ring color |
| `legend` | bool | auto | default: with more than one series |
| `point_radius` | float | auto | marker radius in units (0.11 for up to 20 points, down to 0.05) |

```yaml
- id: sizes
  type: scatter
  params:
    title: "Model size vs accuracy"
    x_label: "parameters (billions)"
    y_label: "accuracy (%)"
    trend: all
    trend_label: r2
    highlight: ["ours@2"]
    series:
      baselines: [[1.3, 61], [6.7, 70, "7B"], [13, 73], [65, 80, "65B"]]
      ours: [[1.0, 66], [3.8, 72, "small"], [7.0, 75]]
  beats:
    - text: "Baselines improve as they grow."
    - text: "Our models sit above them."
    - text: "The trend makes the gap clear."
    - text: "Especially for the small one."
```

### `histogram`

A distribution as bars over value bins. Step 1 draws the axes and grows the bars from left to
right; then, each a step of its own (so one per beat when there are enough beats): the
`compare` outline, the `mean` marker, the `median` marker, and the `highlight` of chosen bins
(they turn `highlight_color`, the others dim). Bins come from raw `values` — `bins` as a count
of equal bins, or a rule whose width is rounded to 1, 2, 2.5 or 5 x 10^k with edges on its
multiples (so the axis reads 10, 20, 30), or a `bin_width` — or from `counts` with their
`edges`. Mean and median are exact from values, estimated from counts.
[Action targets](#beat-actions): `title`, `axes`, `legend` (with `compare`), `bin<N>`
(1-based), `bin:<range>` (the edges as the axis writes them: `bin:10-20`), `compare`, `mean`,
`median`.

| param | type | default | |
|---|---|---|---|
| `values` | list[float] | — | raw data (or `counts` + `edges`) |
| `bins` | int \| `auto` \| `sturges` \| `sqrt` \| `fd` | `auto` | equal bins over the range, or a rule (numpy's; `fd` = Freedman-Diaconis) with round widths; at most 60 bins |
| `bin_width` | float | none | width; edges on its multiples (or from `bin_range`'s start) |
| `bin_range` | [low, high] | the data's | values outside are left out |
| `counts`, `edges` | list[float] | — | counts per bin and the `len(counts) + 1` increasing edges, instead of `values` |
| `name` | str | `""` | legend name (shown with `compare`; default `data`) |
| `compare` | `{name, values \| counts, color}` | none | a second distribution over the same bins, drawn as an outline (`color` `secondary`) |
| `percent` | bool | `false` | each bin's share of its total (%) instead of counts |
| `mean`, `median` | bool | `false` | dashed marker with its value above the plot |
| `highlight` | list[int \| str] | `[]` | bins (0-based index or range `"10-20"`) for a last step |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |
| `label_size` | size | `caption` | ticks, axis labels, marker labels, legend |
| `x_label`, `y_label` | str | `""` | axis titles |
| `x_format`, `y_format` | str | automatic | Python format of the edges (also in `bin:` names) / y ticks |
| `x_unit` | str | `""` | appended to x ticks and the mean / median values |
| `color` | color | `primary` | bars |
| `mean_color`, `median_color`, `highlight_color` | color | `accent`, `tertiary`, `highlight` | |

```yaml
- id: latency
  type: histogram
  params:
    title: "Response times"
    x_label: "milliseconds"
    values: [12, 15, 17, 18, 21, 22, 23, 25, 26, 28, 30, 31, 33, 35, 38, 41, 45, 52, 61, 75, 97, 120]
    mean: true
    median: true
    highlight: ["40-50"]
  beats:
    - text: "Most requests finish quickly."
    - text: "The slow tail pulls the mean up."
    - text: "The median stays lower."
    - text: "These are the requests to look at."
```

### `pie`

Shares of a whole as slices of a circle, or of a ring with `donut: true` (the total, or
`center`, in the hole). Step 1 sweeps every slice round from the top, clockwise, then writes
the labels (`reveal: all`, default); `per_beat` sweeps slice *i* in at beat *i*. With
`highlight`, a last step pulls that slice out of the pie and dims the others. Each share is
its value / the total.

**Labels** stand inside their slice when they fit there (in the slice's colour-contrasting
text colour), else outside with a leader line, stacked in a column on each side so they never
overlap; when side columns would leave the pie too small (a 9:16 frame) or cannot hold them,
those labels go into a key of colour swatches below the pie (beside it in 16:9). With more than
6 slices (or `legend: true`) every label is in that key, which is then the `legend`. Many small
slices: group them with `other_below: 3` (slices under 3 % become one `Other` slice, drawn
last in `other_color`) or `max_slices`. Label text shrinks towards the readable minimum before
anything is left out (a warning names what did not fit).
[Action targets](#beat-actions): `title`, `slice<N>` (1-based, as drawn, after grouping),
`slice:<label>` (a slice with its label and leader), `center` (a donut's centre text),
`legend` (with the legend).

| param | type | default | |
|---|---|---|---|
| `labels`, `values` | list[str], list[float] | required | one value (≥ 0) per unique label |
| `donut` | bool | `false` | a ring instead of a full pie |
| `hole` | float | `0.58` | donut hole radius / outer radius (0.3–0.85) |
| `center` | str | the total | text in the donut hole (`value_format` + `unit`); `""` for none |
| `center_label` | str | `""` | a smaller line under it (`visits`) |
| `center_size` | size | `title` | fitted into the hole |
| `show_values` | `percent` \| `value` \| `both` \| `none` | `percent` | under each name: `42%`, the value, `42% · 1,200` or nothing |
| `value_format`, `unit` | str | automatic, `""` | format of values and the total |
| `percent_decimals` | int | auto | 0, or 1 when a slice is under 1 % |
| `colors` | `palette` \| color \| list[color] | `palette` | the palette in order (lighter shades past its length) |
| `sort` | bool | `false` | largest slice first |
| `other_below` | float | none | group slices under this share (%) into one |
| `max_slices` | int | none | keep the largest `max_slices - 1`, group the rest |
| `other_label`, `other_color` | str, color | `Other`, `dim` | the grouped slice |
| `label_position` | `auto` \| `outside` | `auto` | `outside`: never inside a slice |
| `legend` | bool | auto | names in a legend (default: with more than 6 slices) |
| `reveal` | `all` \| `per_beat` | `all` | |
| `highlight` | int \| str | none | slice (0-based index or label, as drawn) pulled out in a last step |
| `explode` | float | `0.1` | how far it moves out (share of the radius, 0–0.3) |
| `start_angle`, `clockwise` | float, bool | `90`, `true` | where the first slice starts (degrees; 90 = top) and the direction |
| `label_size` | size | `caption` | labels and legend |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

```yaml
- id: traffic
  type: pie
  params:
    title: "Visits by device"
    donut: true
    center_label: "visits"
    labels: ["Mobile", "Desktop", "Tablet", "TV", "Watch"]
    values: [5200, 3100, 640, 120, 80]
    other_below: 2           # TV and Watch become "Other"
    highlight: Desktop
  beats:
    - text: "Most visits come from phones."
    - text: "Desktop is still a third of them."
```

### `heatmap`

A matrix of values as coloured cells: row labels on the left, column labels on top, a
colour-scale legend (a gradient bar with round ticks) right of it (below it in 9:16). Step 1
brings the labels and legend and the cells in a wave from the top left (`reveal: all`,
default); `rows` reveals one row per beat. With `highlight`, a last step outlines the chosen
cells, rows or columns in `highlight_color` and dims the rest.

**Colours** come from theme colours, interpolated perceptually (OKLab, so equal steps in
value look like equal steps in colour): `sequential` runs from a faint tint of `color` to
`color` (larger values stand out more on any background); `diverging` runs from `low_color`
through a near-background neutral at `center` to `high_color`, symmetric around `center`;
`auto` picks diverging when values lie on both sides of `center`. Each value is written in the
theme's text or background colour, whichever reads better on its cell (WCAG 4.5:1 or more,
what `vidgen lint` checks), and the values are hidden when the cells are too small for
readable text. Cells are at most square-tall and 2.5x as wide as tall; a matrix whose cells
come out smaller than 0.3 units logs a warning to split it. `null` values are empty cells.
[Action targets](#beat-actions): `title`, `legend`, `row<N>`, `row:<label>`, `col<N>`,
`col:<label>` (a row / column with its label), `cell<R>.<C>` (1-based).

| param | type | default | |
|---|---|---|---|
| `values` | list[list[float \| null]] | required | the matrix, row by row (up to 40 x 40) |
| `rows`, `columns` | list[str] | `[]` | unique row / column labels |
| `scale` | `auto` \| `sequential` \| `diverging` | `auto` | |
| `color` | color | `primary` | sequential: the highest values |
| `low_color`, `high_color` | color | `primary`, `accent` | diverging: below / above `center` |
| `center` | float | `0` | diverging: the neutral value |
| `scale_min`, `scale_max` | float | from the data | ends of the scale (diverging: symmetric around `center`) |
| `show_values` | bool | auto | values in the cells (default: when they fit at a readable size) |
| `value_format`, `unit` | str | automatic, `""` | cell values and legend ticks |
| `value_size` | size | `caption` | largest value size (shrinks to fit) |
| `legend` | bool | `true` | the colour-scale bar |
| `legend_label` | str | `""` | its title (`correlation`) |
| `reveal` | `all` \| `rows` | `all` | |
| `highlight` | list[str] | `[]` | `cell<R>.<C>`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>` for a last step |
| `highlight_color` | color | `highlight` | outline colour |
| `label_size` | size | `caption` | row / column labels and ticks |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

```yaml
- id: busy
  type: heatmap
  params:
    title: "Renders per hour"
    rows: ["Mon", "Tue", "Wed"]
    columns: ["9h", "12h", "15h", "18h"]
    values: [[3, 8, 4, 9], [5, 10, 6, 11], [4, 9, null, 13]]
    legend_label: "renders"
    highlight: ["col:18h"]
  beats:
    - text: "Each cell counts the renders in one hour."
    - text: "Evenings are the busiest."
```

### `map`

A world map — the 177 countries of Natural Earth's 1:110m admin-0 map (public domain, bundled;
see THIRD_PARTY_NOTICES.md) in the Equal Earth projection — with highlighted countries, a
choropleth, pins and flight-path arcs. Borders are Natural Earth's *de facto* representation
(e.g. Kosovo, N. Cyprus, Somaliland and W. Sahara are shapes of their own); vidgen takes no
position on disputed boundaries. Countries are named by ISO 3166
alpha-2 or alpha-3 code (`DE`, `DEU`), English name or a common alias (`USA`, `UK`, `Holland`,
`Ivory Coast`, `Czech Republic`...); case and accents do not matter, typos get a "did you mean".
Countries too small for this scale (Singapore, Malta, Bahrain...) are reported by `vidgen
validate`: mark them with a pin instead.

Beat 1 draws the map (a sweep from west to east; a choropleth's colours with it), the legend,
the `countries` / `pins` / `arcs` given outside `steps`, and then step 1. **Per-beat data** is
`steps` (aligned with the beats as in `screenshot` / `code_walkthrough`): step *i* highlights its
countries (the fill fades to the colour, the label follows), drops its pins and grows its arcs
at beat *i*. Earlier steps stay. A step with `focus` moves the camera in on its items (labels
are built for the zoom so they read at their normal size; labels made for another view fade);
the next step without `focus` moves back. More steps than beats are spread evenly; extra beats
hold.

- **View**: `auto` (default) fits the highlighted and valued countries, pins and arcs (with a
  margin; the world when there are none or they span more than 200° of longitude); `world`
  (without Antarctica unless `antarctica: true`); a region — `europe`, `africa`, `asia`,
  `middle_east`, `north_america`, `south_america`, `oceania`; or a box `[lon_min, lat_min,
  lon_max, lat_max]` in degrees (`lon_max < lon_min` crosses the date line, e.g. `[150, -50,
  -170, 0]`). The view is projected around its middle longitude and grown to the shape of the
  space (more of the map, not empty bands); a regional view is drawn as a framed panel with the
  sea in `surface`. In 9:16 the whole world is a narrow strip, so a `world` (or `auto` → world) view
  keeps only the longitudes of the map's countries, pins and arcs (12 % added on each side, at
  least 140°) and all latitudes; items spread round the whole world still give the strip.
- **Highlights** fill countries with `highlight_color` (`accent`; `palette`: one theme palette
  colour per country, in order) or their own `color`, and write their name (`labels`; a
  country's `label` gives other text, `false` none) on its largest part when it fits, else
  beside it with a leader line. A country is highlighted once per scene.
- **Choropleth**: `values` colours countries by a colour scale like `heatmap`'s (`scale`,
  `color`, `low_color`, `high_color`, `center`, `scale_min`, `scale_max`) with a legend bar below
  the map (`legend`, `legend_label`, `value_format`, `unit`); countries without a value are
  fainter land. On a choropleth, highlights are outlines in `highlight_color` (colour is the
  data).
- **Pins** `{lon, lat, label}` (degrees, east / north positive) or `{country, label}` (in the
  middle of the country); **arcs** `{from, to, label}` or `"A -> B"`, where an end is a pin's
  label, a country or `[lon, lat]`. Arcs bend upwards (downwards near the top of the map), grow
  from `from` to an arrowhead at `to` and stop short of pins. Arcs are drawn on the flat map,
  not along great circles, and do not wrap round the date line.
- **Labels** sit on plates of the background colour (readable on any fill), at `label_size`
  (never below the readable minimum), placed clear of each other and of pins.

[Action targets](#beat-actions): `title`, `map` (every country), `legend`, `country:<code>` (a
highlighted or valued country: `country:DEU`, `country:DE` or `country:Germany`), `pin<N>`,
`pin:<label>`, `arc<N>`, `step<N>` (a step's items).

| param | type | default | |
|---|---|---|---|
| `view` | str \| [lon_min, lat_min, lon_max, lat_max] | `auto` | `auto`, `world`, `europe`, `africa`, `asia`, `middle_east`, `north_america`, `south_america`, `oceania`, or a box |
| `countries` | list[str \| {country, color, label}] | `[]` | highlighted in beat 1 |
| `pins` | list[{lon, lat, label, color} \| {country, label, color}] | `[]` | shown in beat 1 |
| `arcs` | list[{from, to, label, color} \| "A -> B"] | `[]` | drawn in beat 1 |
| `steps` | list[{countries, pins, arcs, focus} \| list of countries \| country] | `[]` | step *i* at beat *i* |
| `values` | {country: number} | `{}` | choropleth |
| `labels` | bool | `true` | names on highlighted countries |
| `highlight_color` | color \| `palette` | `accent` | highlight fill (outline on a choropleth) |
| `land_color` | color | `dim` | land, shown faint over the background |
| `pin_color`, `arc_color` | color | `highlight` | defaults for pins / arcs |
| `antarctica` | bool | `false` | draw Antarctica (the `world` view reaches the pole) |
| `scale` | `auto` \| `sequential` \| `diverging` | `auto` | choropleth colour scale (as `heatmap`) |
| `color` | color | `primary` | sequential: the highest values |
| `low_color`, `high_color` | color | `primary`, `accent` | diverging: below / above `center` |
| `center` | float | `0` | diverging: the neutral value |
| `scale_min`, `scale_max` | float | from the data | ends of the scale |
| `value_format`, `unit` | str | automatic, `""` | legend ticks |
| `legend` | bool | `true` | the colour bar under a choropleth |
| `legend_label` | str | `""` | its title (`millions`) |
| `label_size` | size | `caption` | country, pin and arc labels |
| `focus_scale` | float | `3` | largest magnification of `focus: true` (up to 4) |
| `title`, `caption` | str | `""` | |
| `caption_size`, `caption_color` | size, color | `caption`, `dim` | |
| `title_size`, `title_color` | size, color | `heading`, `text` | |

A step's `focus` is `true` (as close as fits, up to `focus_scale`) or a magnification (more
than 1, up to 4).

```yaml
- id: offices
  type: map
  params:
    title: "Our offices"
    view: europe
    steps:
      - [Germany, France]                                    # beat 1: two countries
      - pins: [{lon: -0.13, lat: 51.51, label: London}, {lon: 13.4, lat: 52.52, label: Berlin}]
        arcs: ["London -> Berlin"]                           # beat 2: pins and an arc
      - countries: [{country: NL, label: "Amsterdam HQ"}]
        focus: true                                          # beat 3: the camera moves in
  beats:
    - text: "We started in Germany and France."
    - text: "Then London and Berlin, linked by a weekly flight."
    - text: "Our new head office is in the Netherlands."
```

```yaml
- id: people
  type: map
  params:
    title: "Population"
    view: europe
    values: {Germany: 83, France: 68, Italy: 59, Spain: 48, Poland: 37, UK: 67}
    legend_label: "millions"
    steps: [[], [Germany]]                                   # beat 2 outlines Germany
  beats:
    - text: "Europe's largest countries by population."
    - text: "Germany has the most people."
```

### `image`

Steps: (1) the image, (2) the caption. `vidgen validate` reports a missing or unsupported file
(png, jpg, jpeg, gif, bmp, webp, tif, svg). Instead of a file, `generate:` asks for a
[generated picture](#generated-images-imagegen-vidgen-imagegen): `vidgen imagegen` makes it once
(paid), and until then the scene shows a placeholder card with the prompt in the theme's colours.
An `.svg` file or `generate: {format: svg}` is a [vector picture](#vector-svg-pictures-format-svg):
sanitised, then drawn as shapes (`draw`, `recolor`, `simplify` below; the layout dump and lint
see it as one object of kind `vector`).
[Action targets](#beat-actions): `image`, `caption` (`dim` fades the picture, `highlight` tints it).

| param | type | default | |
|---|---|---|---|
| `path` | str | required (or `generate`) | relative to the project folder, e.g. `assets/photo.jpg` |
| `generate` | str \| mapping | none | a generated picture instead of `path` (not both): the prompt, or `{prompt, negative, style, aspect, seed, format}`, see [generated images](#generated-images-imagegen-vidgen-imagegen) |
| `draw` | bool | `false` | vector pictures only: trace the outlines, then fill them (up to 2.5 s within the beat) instead of fading in |
| `recolor` | `none` \| `theme` | `none` | vector pictures only: `theme` maps each colour to the theme's — greys to the neutral (`background`, `surface`, `dim`, `text`) of nearest lightness, other colours to the theme colour (`primary`, `secondary`, `tertiary`, `accent`, `highlight`, palette) of nearest hue, keeping their lightness |
| `simplify` | bool \| number 0–5 | `false` | vector pictures only: drop shapes smaller than this percentage of the picture's area (`true` = 0.05) so busy SVGs draw faster |
| `caption` | str | `""` | |
| `fit` | `contain` \| `cover` | `contain` | `contain`: whole image, caption below; `cover`: fills the frame (cropped), caption on a band |
| `ken_burns` | bool \| mapping | `false` | slow zoom/pan over the whole scene; `true` = zoom 1.0 → 1.15 on the center |
| `ken_burns.start_scale`, `.end_scale` | float 1–4 | `1.0`, `1.15` | |
| `ken_burns.start_focus`, `.end_focus` | `[x, y]` in 0–1 | `[0.5, 0.5]` | point to center on (0,0 = top left) |
| `caption_color`, `caption_size` | color, size | `text`, `caption` | |

```yaml
- id: lab
  type: image
  params:
    path: assets/lab.jpg
    fit: cover
    caption: "The training cluster"
    ken_burns: {end_scale: 1.25, end_focus: [0.7, 0.35]}
  beats:
    - text: "Everything ran on this machine."
- id: harbour
  type: image
  params:
    generate: {prompt: "a quiet harbour at dawn, fishing boats, mist over the water", negative: people}
    fit: cover
  beats:
    - text: "It started in a small harbour town."
```

### `screenshot`

A picture of an app or a web page with **callouts** pointing at its parts, one step per beat:
boxes, circles, arrows with labels, magnified insets and a spotlight. Steps: (1) the picture (in
its frame) and then step 1's callouts, (*i*) step *i*'s callouts. Before a step's callouts are
drawn, the earlier ones fade out (`previous: fade`, default), dim (`dim`: their boxes, circles
and arrows stay faint, labels, insets and shades go) or stay (`keep`). With more steps than beats
they are spread evenly; extra beats hold. `vidgen validate` reports a missing or unsupported
image file and areas outside the image.

**Areas** are `[x, y, w, h]`: the top-left corner and the size, as fractions of the image (`0`–`1`,
from its top-left corner, like `ken_burns` focus points) or, with `units: px`, in the image's own
pixels (as an image editor shows them). A point `[x, y]` is enough for a box, circle or arrow.

**Callouts** are written `{KIND: area, label: ..., ...}` (or `{kind: KIND, area: [...], ...}`):

| kind | draws | options |
|---|---|---|
| `box` | a rounded frame around the area, the label as a tag on its edge (above it, else below) | `label`, `color`, `side` |
| `circle` | an ellipse through the area's corners (a ring around a point), the label beside it | `label`, `color`, `side` |
| `arrow` | the label away from the area — outside the picture when there is room, never off the frame — and an arrow from it to the area's edge (to the point) | `label`, `color`, `side`, `curved` |
| `magnifier` | an enlarged inset of the area (`zoom` times, less when there is not that much room beside the area), joined to a frame around the area by two lines; cut from the image's own pixels, so it is sharp | `label`, `color`, `side`, `zoom` (`2`, more than 1, up to 8) |
| `spotlight` | the rest of the picture dimmed (the theme's background at 62 %), the area clear | `label`, `color`, `side` |

Labels are bold text on a plate in the callout's colour (default the scene's `color`,
`highlight`), written in whichever theme colour reads best on it (4.5:1 or more), at `label_size`
and never below the readable size; long labels wrap. Each label is placed clear of the other
callouts of its step (and of those kept from earlier steps), of their areas and of the frame's
title bar. `side: top | bottom | left | right` forces where the label (a magnifier: its inset)
goes. A spotlight lies under the other callouts.

**Per-beat data** lives in `steps`, aligned with the beats: entry *i* is beat *i*. An entry is one
callout, a list of callouts, or `{callouts, focus, previous}`.

**Focus.** `focus: true` moves the camera in on the step's areas (at most `focus_scale`, so that
they take about half of the view; a number is the magnification) and builds the step's labels and
lines for the zoom, so they read at their normal size. Callouts built for another view (the
whole frame, or another focus) leave when the camera moves; the next step without `focus` moves
the camera back. A view taller (wider) than the picture is centred on it that way, a smaller one
stays on the picture. Without `focus`, a step focuses by itself in a **vertical frame when the
picture is landscape** (1.2:1 or wider; it would be a thin strip across the middle of a 9:16
frame), and not otherwise; `focus: false` keeps the whole picture.

**Frames.** `frame: browser` draws a title bar with three dots and an address field (`url`),
`window` the title bar alone, `phone` a rounded body with a speaker slot and a home bar (for
portrait screenshots); all in the theme's `surface` and `dim` colours.

[Action targets](#beat-actions): `title`, `image` (the picture with its frame), `caption`, `callout<N>`
(numbered over all steps, in the order written), `callout:<label>`, `step<N>` (a step's callouts;
revealing it plays the step). Revealing a callout early draws it (one of a focus step brings its
step, with the camera); a step whose callouts are all on screen already is skipped at its beat.

| param | type | default | |
|---|---|---|---|
| `path` | str | required | relative to the project folder, e.g. `assets/app.png` |
| `title` | str | `""` | heading above the picture |
| `caption` | str | `""` | a line under the picture (as in `video_clip`; callout labels keep clear of it; it fades out while a `focus` step has the camera in, and back) |
| `caption_size` | size | `caption` | |
| `caption_color` | color | `text` | |
| `steps` | list | `[]` | step *i* at beat *i*: a callout, a list of callouts, or `{callouts, focus, previous}` |
| `steps[].callouts` | list | `[]` | `{KIND: area, label, color, side, curved, zoom}` (see above) |
| `steps[].callouts[].kind`, `.area` | kind, list | required | the canonical form of `{KIND: area}` |
| `steps[].callouts[].label` | str | `""` | |
| `steps[].callouts[].color` | color | the scene's `color` | mark and label plate |
| `steps[].callouts[].side` | `auto` \| `top` \| `bottom` \| `left` \| `right` | `auto` | where the label / inset goes |
| `steps[].callouts[].curved` | bool | `false` | arrows only |
| `steps[].callouts[].zoom` | number | `2` | magnifiers only |
| `steps[].focus` | bool \| number | auto | `true`: the camera moves in on the step's areas; a number (1–4): that magnification; not given: `true` for a landscape picture in a vertical frame, else `false` |
| `steps[].previous` | `fade` \| `dim` \| `keep` | the scene's | what happens to earlier callouts at this step |
| `frame` | `none` \| `browser` \| `window` \| `phone` | `none` | drawn around the picture |
| `url` | str | `""` | text of a `browser` frame's address field |
| `units` | `fraction` \| `px` | `fraction` | how areas are written |
| `color` | color | `highlight` | default callout colour |
| `label_size` | size | `caption` | label text size (never below the readable size) |
| `previous` | `fade` \| `dim` \| `keep` | `fade` | what happens to a step's callouts when the next starts |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |

```yaml
- id: app
  type: screenshot
  params:
    title: "Point at what matters"
    path: assets/app.png
    frame: browser
    url: "planner.example/overview"
    steps:
      - {box: [0.216, 0.038, 0.269, 0.055], label: "Search every task"}
      - - {arrow: [0.857, 0.065], label: "New task", curved: true}
        - {circle: [0.736, 0.15, 0.25, 0.17], label: "Overdue"}
      - {magnifier: [0.675, 0.545, 0.28, 0.085], label: "Done today", zoom: 2.5}
      - callouts:
          - {spotlight: [0.205, 0.37, 0.428, 0.58]}
          - {arrow: [0.425, 0.55], label: "Thursday was the busiest day"}
        focus: true
  beats:
    - text: "A box marks the search field."
    - text: "An arrow points at the new task button, and a circle at the overdue count."
    - text: "A magnifier enlarges a detail."
    - text: "Focus moves the camera in, and a spotlight dims everything else."
```

Project scenes draw the same callouts with the `callout_*` helpers of `vidgen.api`
([EXTENDING.md](EXTENDING.md#2-building-blocks-params-layout-timing-validation), "Callouts").
Callouts on any other scene type (a chart, a diagram) are the [`callout` beat
action](#beat-actions).

### `video_clip`

A **video file** — B-roll, a screen recording — played inside the scene while the narration
runs: framed in a layout region (optionally in a `browser` / `window` / `phone` frame as in
[`screenshot`](#screenshot), with a title above and a caption below) or full-bleed, with
**callouts** drawn over it step by step exactly as in `screenshot` (same `steps`, kinds, `previous`,
`focus`; no `magnifier`, which needs a still picture). Steps: (1) the clip (with its title and
caption) and then step 1's callouts, (*i*) step *i*'s callouts. Files: mp4, mov, m4v, webm, mkv
(anything FFmpeg decodes); `vidgen validate` reports a missing, unsupported or unreadable file, a
`trim` past the clip's end and pixel areas outside its picture.

**Timing contract.** The narration sets the scene's length, never the clip: the scene lasts its
beats (+ `narration.pad` each, as every scene) plus the 0.5 s fade-out, or a silent scene's
`duration`. The clip starts playing when the scene starts (it fades in while playing) and plays
`trim: [start, end]` (default: all of it) at `speed` through every beat. One pass takes
`(end - start) / speed` seconds on screen; when the scene is longer the clip starts again with
`loop: true`, otherwise its **last frame holds** (a warning names the hold when it is longer than
2 s, and `vidgen lint`'s `dead_air` reports a hold over 6 s, as it reports any still picture);
when the scene is shorter the clip is cut by the fade-out. `fit_duration: true` picks the speed
that makes one pass last exactly as long as the narration, kept within `fit_range` (default
`[0.5, 2.0]`, so a clip is never sped up or slowed down beyond recognition; outside it the clip
holds or is cut as above).

**Sound.** The clip's own sound plays as the picture does (trimmed, at its speed with its pitch
kept, looped, silent while the last frame holds) and is mixed **under the narration** into the
scene's sound: `volume` 0.25 by default in a narrated scene, 1 in a silent one; `mute: true` (or
`volume: 0`) leaves it out. It fades out with the picture. There is no ducking: keep `volume` low
under speech.

**Layout.** `region` is a layout region ([`vidgen.api.region`](EXTENDING.md#2-building-blocks-params-layout-timing-validation)) for the clip below the title: `body`
(default) or `full` (all the room below the title), `hero`, `left`, `right` (upper / lower half in
9:16), `top`, `bottom`, `center` — or `bleed`, the whole frame edge to edge, with the title and the
caption on plates in the theme's `surface` colour over the picture (no `frame` then). `fit:
contain` shows the whole picture as large as fits; `cover` fills the region (or the frame),
cutting the picture's excess equally from both sides — a 16:9 clip in a 9:16 frame keeps only its
middle with `region: bleed, fit: cover`, while `contain` leaves bands above and below. The
default `fit: auto` is `contain`, except for a landscape clip (1.2:1 or wider) **without
callouts in a vertical frame** in a region: that shows a nearly square part from the clip's
middle (`cover` into a square room), not a thin strip; with `region: bleed` `auto` is `contain`. Callout
steps of a landscape clip in a vertical frame focus by themselves, as in `screenshot`.

**Callout areas** are `[x, y, w, h]` (or a point `[x, y]`) from the top-left corner of the clip's
**whole picture**, as fractions or, with `units: px`, in its pixels — also with `fit: cover`, so a
callout stays on the same thing whichever part is shown (a warning names callouts outside the part
`cover` shows). Callouts stay put while the picture moves: point at things that stay there, or
give the step its own beat.

Decoding: frames are read with PyAV as the render reaches them, scaled once to the size shown
(sharper when a `focus` step or a `zoom` action will look closer, up to the clip's own pixels) and
not kept in memory; stills, the layout dump and `vidgen lint` see the clip as an image, and the
clip's motion counts as activity for `dead_air`. Rotation metadata (phone videos) is not applied.

[Action targets](#beat-actions): `title`, `clip` (the picture with its frame), `caption`,
`callout<N>`, `callout:<label>`, `step<N>` (as in `screenshot`). `dim: clip` fades the moving
picture, `highlight: clip` tints it, `zoom: clip` looks closer.

| param | type | default | |
|---|---|---|---|
| `path` | str | required | relative to the project folder, e.g. `assets/demo.mp4` |
| `title` | str | `""` | heading above the clip (on a plate with `region: bleed`) |
| `caption` | str | `""` | line under the clip (on a plate at the bottom with `region: bleed`); fades out while a `focus` step has the camera in |
| `caption_size`, `caption_color` | size, color | `caption`, `text` | |
| `region` | `body` \| `full` \| `hero` \| `left` \| `right` \| `top` \| `bottom` \| `center` \| `bleed` | `body` | where the clip goes (see above) |
| `fit` | `auto` \| `contain` \| `cover` | `auto` | whole picture, or fill the region / frame (cropped); `auto`: `contain`, a nearly square part from the middle of a landscape clip without callouts in a vertical frame |
| `trim` | [start, end] | the whole clip | seconds of the file that play |
| `speed` | number (0.25–4) | `1.0` | playback speed; the sound keeps its pitch |
| `fit_duration` | bool | `false` | choose the speed so one pass lasts as long as the narration (not with `speed`) |
| `fit_range` | [slowest, fastest] | `[0.5, 2.0]` | limits of `fit_duration` (within 0.25–4) |
| `loop` | bool | `false` | start again when the scene outlasts the clip (else the last frame holds) |
| `volume` | number (0–2) | 0.25 narrated, 1 silent | the clip's own sound, under the narration (linear; 1 = as recorded, a mono recording at that level on both channels) |
| `mute` | bool | `false` | leave the clip's sound out |
| `steps` | list | `[]` | step *i* at beat *i*: a callout, a list of callouts, or `{callouts, focus, previous}` ([`screenshot`](#screenshot); kinds `box`, `circle`, `arrow`, `spotlight`) |
| `frame`, `url` | `none` \| `browser` \| `window` \| `phone`, str | `none`, `""` | a frame drawn around the clip (not with `bleed`); `url` for `browser` |
| `units` | `fraction` \| `px` | `fraction` | how callout areas are written (of the whole picture) |
| `color`, `label_size` | color, size | `highlight`, `caption` | callout colour and label size |
| `previous` | `fade` \| `dim` \| `keep` | `fade` | what happens to a step's callouts when the next starts |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |

```yaml
- id: clip
  type: video_clip
  params:
    title: "Clips play under the narration"
    path: assets/clip.webm
    frame: window
    caption: "A generated test pattern, looping"
    loop: true
    steps:
      - {box: [0.0, 0.0, 0.21, 0.14], label: "Time code"}
      - {arrow: [0.92, 0.45], label: "Colour bars", curved: true}
  beats:
    - text: "Video clips play inside a scene, and the narration sets how long they run."
    - text: "Callouts work on moving pictures too, one step per beat."
- id: broll
  type: video_clip
  params: {path: assets/city.mp4, region: bleed, fit: cover, trim: [12, 20], fit_duration: true, mute: true}
  beats:
    - text: "Full-bleed B-roll, trimmed and stretched over the sentence."
```

### `quote`

Steps: (1) quote mark and text, (2) attribution. Quote characters around `text` are removed;
the scene draws a large typographic mark.
[Action targets](#beat-actions): `mark`, `quote`, `author`, `source` (those present).

| param | type | default | |
|---|---|---|---|
| `text` | str | required | |
| `author`, `source` | str | `""` | shown as `— author` and, smaller, `source` |
| `size` | size | `subtitle` | of the quote text (shrunk if long; 1.25x in a vertical frame) |
| `color`, `mark_color`, `author_color`, `source_color` | color | `text`, `primary`, `text`, `dim` | |
| `mark_font` | str | role `quote_mark` (Source Serif 4) | font of the quote mark |

The quote text uses the font role `quote`, the mark `quote_mark` ([Fonts](#fonts)).

```yaml
- id: saying
  type: quote
  params: {text: "Simplicity is prerequisite for reliability.", author: "Edsger W. Dijkstra"}
  beats:
    - text: "As Dijkstra put it: simplicity is prerequisite for reliability."
```

### `equation`

Steps: one per formula; each morphs into the next. The caption comes with the first. **Needs
LaTeX** (`latex` and `dvisvgm` on PATH — on Windows install MiKTeX). `vidgen validate` warns
when it is missing; rendering then fails with installation hints. A formula that does not
compile is reported with the scene id and the formula.
[Action targets](#beat-actions): `step<N>` (1-based), `caption`, `term:<tex>` for each of `terms` (in the step on
screen). A step that a `transform` or `reveal` action brought in early is not shown again, and
earlier steps are skipped once a later one is on screen.

| param | type | default | |
|---|---|---|---|
| `latex` | str \| list[str] | required | math-mode LaTeX (no `$`); a list is a sequence of steps |
| `caption` | str | `""` | |
| `size` | size | `96` | formula size (1.25x in a vertical frame; shrunk to fit the width) |
| `caption_size` | size | `caption` | |
| `color`, `caption_color` | color | `text`, `dim` | |
| `terms` | list[str] | `[]` | TeX substrings beat actions can target as `term:<tex>` (e.g. `2ab`); each must occur in a step and be a complete TeX group there (not half of a `\frac{..}{..}`); its first occurrence in a step counts |

```yaml
- id: square
  type: equation
  params:
    latex: ["(a + b)^2", "(a + b)(a + b)", "a^2 + 2ab + b^2"]
  beats:
    - text: "Take a plus b, squared."
    - text: "Write it as a product."
    - text: "And expand."
```

In YAML, write backslashes in single quotes (`'\frac{1}{3}'`) or double them in double quotes.

For a derivation — notes per step, earlier steps kept above, matching parts that move, a boxed
result — use [`equation_derivation`](#equation_derivation).

### `equation_derivation`

A derivation: a sequence of equations where each step **morphs into the next** — the parts that
stay the same move into their new place, the rest fades — with an optional **note** per step
(the justification: "divide both sides by 2"), earlier steps kept above the current one or
replaced by it, and a **box** around the result. Steps: one per entry of `steps` (step 1 comes
with the title); with more steps than beats they are spread evenly; extra beats hold. **Needs
LaTeX**, like [`equation`](#equation); a step that does not compile stops the render with the
step's number, its LaTeX and TeX's own message (`step 2 does not compile: Undefined control
sequence (at: \badcommand {2})`). Unbalanced braces and unclosed `{{` are reported by `vidgen
validate`.

**Per-beat data** lives in `steps`, aligned with the beats (as in
[`code_walkthrough`](#code_walkthrough)): entry *i* is beat *i*, written `{tex, note, match,
transition}` or just the LaTeX string.

**Marking matching parts.** Between two steps, parts written the same way move into each other
when they are *marked*; everything else moves glyph by glyph when the shapes match (a `+` that
stays a `+`) and fades otherwise. Three ways to mark a part:

- `{{ ... }}` around it in both steps (Manim's notation: put a space, or the start of the
  formula, before `{{`): `'{{ 2x }} + 3 = 11'` → `'{{ 2x }} = 8'` moves `2x` as one piece;
- `match: [...]` on a step: those parts are isolated in that step and the one before
  (`{tex: '(a+b)(a+b)', match: ['(a+b)']}`);
- `terms` and the keys of `colors`: isolated in every step.

Parts are compared as TeX tokens, spaces ignored (`2 ab` = `2ab`), and found only as whole tokens
(`x` is not taken out of `\exp`; a part right after `\left` is left alone). A part must be a
complete TeX group (not half of a `\frac{..}{..}`). The alignment sign (`align_at`) is always
isolated, so `=` stays in place from step to step. `transition: shapes` matches glyphs by shape
only, `fade` cross-fades.

**History or replace.** `mode: history` (default) keeps the earlier steps on screen, stacked
above the current one, dimmed (`dim_opacity`, raised where a colour would fall below 2.3:1
contrast) and aligned at the first `align_at` of each step (`=`; a step without it is centred);
the block stays centred as it grows. When the steps do not fit at a readable size, the oldest
scroll away (`keep` sets how many stay). `mode: replace` shows one step at a time, each taking the
place of the previous one (still aligned at `=`, so the sign does not jump).

**Notes** sit beside the equations, level with their step, in 16:9 (earlier notes stay, dimmed,
with their steps) and in a band just below them in a vertical frame (one at a time);
`note_position: bottom` uses the band in 16:9 too.

**Sizes.** All steps share one size: `size` at most (1.25x in a vertical frame), smaller to fit
the widest step and the stacked steps. A step that would be set below 1.5x the readable size
(lint's `min_font`) is broken into lines before its relations (`a = b \\ = c`, aligned at the
sign), when that makes it larger; if it still does not fit it is scaled down further and a
warning says so (shorten the step, or split it in two).

**Colours.** `colors: {x: accent, '\lambda': highlight}` colours those parts in every step (and
in the dimmed history), so a variable keeps its colour through the derivation.

**Result.** `result: box` (default) draws a frame around the last step as it arrives,
`highlight` lays a band of `result_color` behind it, `none` leaves it plain.

[Action targets](#beat-actions): `title`, `step<N>` (a step, also as a dimmed earlier line),
`note<N>` (revealing a note plays its step), `result` (the last step with its box) and
`term:<tex>` for each part named in `terms`, `colors`, `match` or marked `{{ }}` — in the
**current** step (earlier, dimmed lines are not included). `transform: step1` + `into: step3`
jumps ahead; the steps in between are skipped and the result still gets its box.

| param | type | default | |
|---|---|---|---|
| `steps` | list (≥ 1) | required | step *i* at beat *i*: `{tex, note, match, transition}` or the LaTeX string |
| `steps[].tex` | str | required | math-mode LaTeX (no `$`); `{{ ... }}` marks a part that moves into the same part of the next step |
| `steps[].note` | str | `""` | a short justification shown with the step |
| `steps[].match` | list[str] | `[]` | parts that move from the previous step into this one (must occur in both) |
| `steps[].transition` | `auto` \| `shapes` \| `fade` | `auto` | `auto`: marked parts, then glyphs by shape |
| `title` | str | `""` | heading above the derivation |
| `mode` | `history` \| `replace` | `history` | keep earlier steps (stacked, dimmed) or replace them |
| `keep` | int (≥ 1) | as many as fit | `history`: the most steps on screen; older ones scroll away |
| `align_at` | str | `"="` | steps are aligned at the first occurrence of this TeX (`'\le'`, ...); `""` centres every step |
| `colors` | map TeX → color | `{}` | parts coloured in every step |
| `terms` | list[str] | `[]` | more parts to isolate in every step (they move into each other; targets `term:<tex>`) |
| `result` | `box` \| `highlight` \| `none` | `box` | how the last step is marked |
| `result_color` | color | `highlight` | |
| `size` | size | `80` | largest formula size (1.25x in a vertical frame; smaller to fit) |
| `color` | color | `text` | formula colour |
| `dim_opacity` | number (0.15–1) | `0.45` | `history`: opacity of earlier steps and their notes |
| `note_position` | `auto` \| `side` \| `bottom` | `auto` | `auto`: beside in 16:9, below in a vertical frame (always below there) |
| `note_size` | size | `body` | |
| `note_color` | color | `dim` | |
| `note_mark_color` | color | `accent` | the bar beside each note (16:9) |

```yaml
- id: solve
  type: equation_derivation
  params:
    title: "Solving for x"
    colors: {x: accent}                    # x keeps its colour in every step
    steps:
      - '{{ 2x }} + 3 = 11'                # {{ }} marks a part that moves into the next step
      - {tex: '{{ 2x }} = 11 - 3', note: "Subtract 3 from both sides"}
      - {tex: '{{ 2x }} = 8', note: "Simplify"}
      - {tex: 'x = \frac{8}{2}', note: "Divide both sides by 2"}
      - {tex: 'x = 4', note: "The result"}
  beats:
    - text: "Two x plus three equals eleven."
    - text: "Subtract three from both sides."
    - text: "Eleven minus three is eight."
    - text: "Divide both sides by two."
    - text: "And x is four."
```

### `function_plot`

Maths axes with functions f(x): curves, dots that travel along a curve with a live value label
(and a tangent that turns with them), and shaded areas under a curve. The axes are maths style:
they cross at the origin when it is in view (else they run along the bottom and left edges),
with arrow tips, round ticks and plain-text labels (no LaTeX needed).

- **Functions** are written as maths, as text: `x^2 - 1`, `2x + 1` (a number before a letter or a
  bracket multiplies), `3(x + 1)`, `sin(x)^2`, `exp(-x^2/2)`, `sqrt(x)`, `abs(x)`, `1/x`, with
  `^` (or `**`) for powers, the constants `pi`, `e`, `tau` and the functions `sin`, `cos`,
  `tan`, `asin`, `acos`, `atan`, `sinh`, `cosh`, `tanh`, `exp`, `ln` / `log` (natural), `log10`,
  `log2`, `sqrt`, `abs`, `floor`, `ceil`, `sign`, `min(a, b)`, `max(a, b)`. The variable is `x`.
  vidgen parses them with its own small parser: nothing is run as code. `f(x) = x^2` names the
  function (else they are `f`, `g`, `h`, ... in order); a later function may use an earlier one
  (`g(x) = f(x) + 1`). Where a function is undefined (`sqrt` of a negative, `1/x` at 0) or leaves
  the y range, the curve breaks: asymptotes are drawn as separate pieces.
- **Labels**: each curve has a label by it (default `f(x) = x²`, written from the name and the
  expression; `label: ''` for none), placed where it covers no other curve or label. A dot's and
  an area's `label` is a template whose fields are filled in as they move: a dot's `{x}`, `{y}`,
  `{slope}`, `{name}` (default `'{name}({x}) = {y}'`), an area's `{area}` (its signed size, the
  integral), `{from}`, `{to}`, `{name}`; `decimals` sets the places, or a field its own format
  (`{y:.3f}`). The labels and the tick numbers use `label_size` (never below the readable minimum).
- **Steps** (`reveal: per_beat`): the axes and function 1 at beat 1, then each further function,
  then each dot (with its tangent and guides), then each area, one per beat (spread evenly when
  there are more than beats; extra beats hold). `reveal: all`: everything in beat 1. A `reveal`
  action shows an item on a word instead (`{reveal: dot1, at: "@slope"}`, `{reveal: tangent1,
  at: "@tangent"}`); the scene then leaves it to the action (its own beat for it holds).
- **Moving**: the `trace` action moves a dot along its curve to x = `to`, its label, guides and
  tangent following (`{trace: dot1, to: 2.5, at: "@steeper"}`), or an area's right end
  (`{trace: area1, to: 4}`: the area and its value grow); it takes 2 s (`run_time`) and stays
  there; `until: <beat>` moves it back when that beat starts. A dot or area not on screen yet
  appears first.
- **Colours**: a function's `color`, else the colour of the video's [term](#one-colour-per-concept-terms)
  that its name or label is (`{expr: "x^2", name: loss}` with `terms: {loss: accent}`), else the
  theme palette in order. An area takes its own `color`, else the colour of the first term its
  label says, else its function's. Dots are `highlight`, tangents `accent` unless set.
- **Shape**: `aspect: auto` fills the space (a vertical frame: at most 1.5x as tall as wide);
  `aspect: equal` gives both axes the same unit, so slopes and angles look true. `y_range`
  defaults to the functions' values over `x_range` (without the far ends of an asymptote,
  reaching 0 when it is near).
- **Checks** (`vidgen validate`): an expression that does not parse (`functions[0]: 'x^': expected
  a number, x, a function or '(' at character 3, found the end`), an unknown name (with the
  closest known ones), a function used before it is defined, a function with no value on the x
  range, two functions with one name, a dot or an area bound outside its function's range or
  where it has no value, an unknown field in a label, a `trace` whose `to` is outside the range,
  a `trace` of something other than a dot or an area.
- **Geometry on the plane** (no function needed): `points` (`[x, y]` or `{at, name, label, color,
  decimals}`; the label defaults to the name, `{x}`, `{y}` are filled in as it moves), `vectors`
  (arrows: `[x, y]` from the origin, or `{from, to | components, name, label, color}` where `from`
  and `to` are `[x, y]`, a point's name or another vector's name (its tip); `{sum: [a, b]}` adds
  earlier vectors tip to tail: copies of b, c... slide to the tip of the one before, then the
  resultant grows from a's tail; labels may use `{x}`, `{y}` (components), `{length}`, `{name}`)
  and `marks`: `{segment: [A, B, C], closed: true, dashed}` (lines through positions; `closed`: a
  polygon), `{brace: [A, B], label}` (a curly brace beside A-B, its label beyond it),
  `{angle: [A, V, B], label}` (the angle at V, the smaller one: an arc, a small square at 90°; its
  label outside on the bisector; `{angle}` is its size in degrees) and `{dimension: [A, B], label}`
  (a dimension line beside A-B with end bars; label `{length}` by default). A brace or dimension
  goes on the side away from the middle of the figure (outside a triangle); `side: above`,
  `below`, `left`, `right` picks one. A position in a mark is a point's or vector's name,
  `point<N>`, `vector<N>` or `[x, y]`. Marks are drawn in `text` (an angle `accent`, a
  dimension `dim`), points in `text`, vectors in the palette after the functions; each takes the
  colour of a term its label says, unless it has its own `color`. `axes: false` hides the axes,
  ticks and grid (the plane keeps its mapping). Without `x_range` / `y_range` the plot spans the
  geometry with some room (and the origin while the axes show); `aspect` defaults to `equal`
  with vectors or angle marks or without functions, so angles look true.
- **Steps** of the geometry: after the functions, dots and areas, each point, then each vector,
  then each mark, one per beat (`reveal: all`, or `reveal` actions on words, often read better
  for a figure: `{reveal: angle1, at: "@angle"}`). A vector, sum or mark brings the points and
  vectors it is drawn from first.
- **Moving the geometry**: `{trace: "point:C", to: [4, 4]}` moves a point; `{trace: "vector:a",
  to: [2, 3]}` moves a vector's tip and `{trace: "vector:a", scale: 2}` scales it (its tail
  stays; `-1` turns it round). Everything drawn from them follows: vectors from or to the point,
  sums, marks, and labels with `{x}`, `{y}`, `{length}`, `{angle}`. A sum, or a vector ending at a
  point's name, follows others and cannot be traced itself (`vidgen validate` names what to trace
  instead); `to` must stay inside the plot.
- **Checks** of the geometry: an unknown name in a position (with the names there are), a vector
  in `sum` or `from` that is not an earlier one, two items with one name, a name that is also a
  numbered target, a vector of no length, an angle with a ray of no length, a mark with the wrong
  number of positions, a label field the item does not have, a position outside the plot.
- [Action targets](#beat-actions): `title`, `axes`, `function<N>` and `function:<name>` (a curve
  with its label), `dot<N>` (the dot, its label and guides), `tangent<N>` (dot N's tangent, when
  it has one), `area<N>`, `point<N>` and `point:<name>` (a dot and its label), `vector<N>` and
  `vector:<name>` (an arrow, a sum's copies, its label), `segment<N>`, `brace<N>`, `angle<N>`,
  `dimension<N>` (numbered by kind in `marks`).

| param | type | default | |
|---|---|---|---|
| `functions` | list | `[]` | an expression (`x^2`, `f(x) = sin(x)`) or `{expr, name, label, color, domain, dashed}`; at least one of `functions`, `points`, `vectors`, `marks` |
| `functions[].expr` | str | — | f(x) as maths; `f(x) = ...` names it |
| `functions[].name` | str | from `expr`, else `f`, `g`, `h`... | for `on`, `under`, `over` and labels |
| `functions[].label` | str | `f(x) = <expr>` | the label by the curve; `''` for none |
| `functions[].color` | color | term colour, else palette | |
| `functions[].domain` | `[from, to]` | the x range | draw it only there |
| `functions[].dashed` | bool | `false` | a dashed curve |
| `x_range` | `[from, to]` | — (with functions); around the geometry | the x axis |
| `y_range` | `[from, to]` | from the values (and the geometry) | the y axis |
| `dots` | list | `[]` | `{on, x, label, tangent, guides, color, tangent_color, decimals}` |
| `dots[].on` | str | the first function | the function it sits on |
| `dots[].x` | number | — | where it starts (`trace` moves it) |
| `dots[].label` | str | `'{name}({x}) = {y}'` | live label: `{x}`, `{y}`, `{slope}`, `{name}`; `''` for none |
| `dots[].tangent` | bool | `false` | the tangent line at the dot, turning as it moves |
| `dots[].guides` | bool | `false` | dashed lines from the dot to both axes |
| `dots[].color` | color | `highlight` | |
| `dots[].tangent_color` | color | `accent` | |
| `dots[].decimals` | int 0–4 | `1` | places of the label's numbers |
| `areas` | list | `[]` | `{under, over, between, label, color, opacity, decimals}` |
| `areas[].under` | str | the first function | the curve above the area |
| `areas[].over` | str | the x axis | a curve below the area (the area between two curves) |
| `areas[].between` | `[from, to]` | — | its ends on the x axis (`trace` moves the right one) |
| `areas[].label` | str | `''` | in the area: `{area}`, `{from}`, `{to}`, `{name}` (`'A = {area}'`) |
| `areas[].color` | color | term colour, else the function's | |
| `areas[].opacity` | number (0–1] | `0.3` | fill opacity |
| `areas[].decimals` | int 0–4 | `2` | |
| `points` | list | `[]` | `[x, y]` or `{at, name, label, color, decimals}` |
| `points[].name` | str | — | `A`, `P`, `a'`: for positions, targets (`point:A`) and its label |
| `points[].label` | str | the name | `{x}`, `{y}`, `{name}` filled in as it moves (`'P({x}, {y})'`); `''` for none |
| `points[].color` | color | term colour, else `text` | |
| `vectors` | list | `[]` | `[x, y]` (from the origin) or `{from, to, components, sum, name, label, color, decimals}` |
| `vectors[].from` | position | the origin | `[x, y]`, a point's name or a vector's (its tip) |
| `vectors[].to` | position | — | its tip: `[x, y]` or a point's name (it follows the point) |
| `vectors[].components` | `[dx, dy]` | — | instead of `to` |
| `vectors[].sum` | list | — | `[a, b, ...]`: earlier vectors added tip to tail; this arrow is the resultant |
| `vectors[].label` | str | the name | `{x}`, `{y}` (components), `{length}`, `{name}` |
| `vectors[].color` | color | term colour, else palette | |
| `marks` | list | `[]` | each one of `segment`, `brace`, `angle`, `dimension` with its positions |
| `marks[].segment` | positions | — | `[A, B, ...]`; with `closed: true` a polygon, `dashed: true` dashed |
| `marks[].brace` | `[A, B]` | — | a curly brace beside A-B |
| `marks[].angle` | `[A, V, B]` | — | the angle at V (the smaller one); a square at 90° |
| `marks[].dimension` | `[A, B]` | — | a dimension line with end bars |
| `marks[].label` | str | `'{length}'` on a dimension, else none | `{length}` (segment, brace, dimension) or `{angle}` (degrees: `'{angle}°'`) |
| `marks[].side` | `auto` \| `above` \| `below` \| `left` \| `right` | `auto` | brace and dimension: the side of the segment (`auto`: away from the figure's middle) |
| `marks[].color` | color | term colour, else `text` (angle `accent`, dimension `dim`) | |
| `marks[].decimals` | int 0–4 | `1` (`0` for an angle) | |
| `axes` | bool | `true` | `false`: no axes, ticks or grid |
| `x_label` | str | `x` | at the end of the x axis (`''` for none) |
| `y_label` | str | `y` | at the top of the y axis (`''` for none) |
| `grid` | bool | `true` | faint lines at the ticks |
| `aspect` | `auto` \| `equal` | `equal` with vectors, angle marks or no functions, else `auto` | `equal`: one unit is as long on both axes |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `title` | str | `""` | in the header band |
| `title_size` | size | `heading` | 1.3x in a vertical frame |
| `title_color` | color | `text` | |
| `label_size` | size | `caption` | tick, axis, curve, dot, area, point, vector and mark labels |

```yaml
- id: slope
  type: function_plot
  params:
    title: "The slope of x²"
    functions: ["f(x) = x^2"]
    x_range: [-3, 3]
    dots: [{x: -2, tangent: true, guides: true, label: "slope {slope}"}]
  beats:
    - text: "Here is the parabola, f of x equals x squared."
    - text: "A dot on the curve, with its tangent line."
    - text: "As the dot moves right, the slope grows steeper."
      actions: [{trace: dot1, to: 2, at: "@moves"}]
- id: area
  type: function_plot
  params:
    functions: ["sin(x) + 1.2"]
    x_range: [0, 6.5]
    areas: [{between: [1, 2], label: "A = {area}"}]
  beats:
    - text: "Take this wave."
    - text: "The area under it from one to two."
    - text: "Sweep the right end out to five and the area grows."
      actions: [{trace: area1, to: 5, at: "@Sweep"}]
- id: triangle
  type: function_plot
  params:
    axes: false
    points: [{at: [0, 0], name: A}, {at: [4, 0], name: B}, {at: [4, 3], name: C}]
    marks:
      - {segment: [A, B, C], closed: true}
      - {brace: [A, B], label: "4"}
      - {brace: [B, C], label: "3"}
      - {angle: [B, A, C], label: "{angle}°"}
      - {dimension: [A, C], label: "c = {length}"}
    reveal: all
  beats:
    - text: "A right triangle: four along, three up."
    - text: "Lift C and the hypotenuse and the angle grow."
      actions: [{trace: "point:C", to: [4, 4.5], at: "@Lift"}]
- id: adding
  type: function_plot
  params:
    x_range: [-1, 7]
    y_range: [-1, 5]
    vectors:
      - {to: [3, 1], name: a}
      - {to: [1, 3], name: b}
      - {sum: [a, b], label: "a + b = ({x}, {y})", decimals: 0}
  beats:
    - text: "Vector a: three right, one up."
    - text: "Vector b: one right, three up."
    - text: "Slide b to the tip of a; the sum goes from start to end."
    - text: "Scale a by one and a half and the sum follows."
      actions: [{trace: "vector:a", scale: 1.5, at: "@Scale"}]
```

### `number_line`

One number line across the frame (horizontal in 16:9 and 9:16; in a vertical frame the numbers
are thinned to fit) with points, intervals and jumps.

- **Points**: a number or `{at, name, label, color, decimals}`; the label (default: the name)
  sits above the point, or under the numbers where a jump starts or lands; `{x}`, `{name}` are
  filled in as it moves. Colour `highlight` unless set (or a term's).
- **Intervals**: interval notation as text, `"[-1, 3)"`, `"(2, inf)"`, `"(-inf, 0]"` (`∞` works
  too), or `{from, to, ends: "[)", label, color}`: a thick band on the line, a filled dot at a
  closed end, a ring at an open one, an arrow at an infinite end; overlapping intervals stack
  above each other. Colours from the theme palette in order (or a term's).
- **Jumps**: `[from, to]` or `{from, to, label, color}`: an arc above the line with an arrow, its
  label above it (default `'{by}'`: `+3`, `−2`; `{from}`, `{to}` too); a jump over an earlier one
  goes higher. Colour `accent` (or a term's).
- **Ticks**: round numbers (every 2nd or 5th one labelled when they would crowd); `step: 1` puts
  a tick at every whole number.
- **Steps** (`reveal: per_beat`): the line with the first item at beat 1, then each point, each
  interval and each jump, one per beat; `reveal: all`: everything in beat 1; a `reveal` action
  shows an item on a word (`{reveal: jump2, at: "@back"}`).
- **Moving**: `{trace: point1, to: 4}` slides a point along the line (its label follows).
- **Checks**: a number outside `range`, an interval written otherwise than `[a, b)`, an interval
  or jump of no length, a label field it does not have, a `step` that gives over 60 ticks.
- [Action targets](#beat-actions): `title`, `line`, `point<N>`, `point:<name>`, `interval<N>`,
  `jump<N>`.

| param | type | default | |
|---|---|---|---|
| `range` | `[from, to]` | — | the numbers the line shows |
| `step` | number | a round step | distance between ticks |
| `points` | list | `[]` | a number or `{at, name, label, color, decimals}` |
| `intervals` | list | `[]` | `"[-1, 3)"` or `{from, to, ends, label, color}`; `ends`: `[]`, `[)`, `(]`, `()` |
| `jumps` | list | `[]` | `[from, to]` or `{from, to, label, color}`; label default `'{by}'` |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `title` | str | `""` | in the header band |
| `title_size` | size | `heading` | 1.3x in a vertical frame |
| `title_color` | color | `text` | |
| `label_size` | size | `caption` | numbers and labels |

```yaml
- id: hops
  type: number_line
  params:
    title: "Adding on the number line"
    range: [-2, 9]
    step: 1
    points: [{at: 2, name: start}]
    intervals: [{from: 5, to: inf, ends: "[)", label: "x ≥ 5"}]
    jumps: [[2, 5], [5, 7]]
  beats:
    - text: "Start at two."
    - text: "Every number from five on."
    - text: "Jump three to five."
    - text: "And two more, to seven."
```

### `code`

Steps: (1) the listing (with the first highlight applied), then one per further `highlight`
entry. Highlighting dims the other lines and puts a soft band behind the selected ones. Uses
Manim's `Code` (Pygments highlighting); the listing is scaled to fill the space below the
title. When its width would make it smaller than `size` (typical for long lines in a vertical
video), long lines are wrapped with a hanging indent (`wrap`); wrapped lines keep their line
number (on the first piece only) and highlights, `focus`, actions and `line<N>` targets still
count original lines. Each line is highlighted whole before it is wrapped, so a piece keeps the
colour of the token it continues (a `//` comment stays a comment past an apostrophe); lines break
at spaces and punctuation, and a word is cut only when it is longer than a line. Wrapping aims for at least 32 characters per
line: where `size` would leave fewer (a vertical frame, especially with the `large` type scale),
the listing is set smaller instead, down to the readable minimum (`lint` `min_font`), and wraps
there. For code longer than the frame holds, use [`code_walkthrough`](#code_walkthrough).
[Action targets](#beat-actions): `title`, `listing` (the window), `line<N>` (an original line,
1-based, with its number; all its pieces when wrapped) and `lines:<a-b>` (lines a to b,
`lines:3-5`). The scene's own `highlight` steps set line opacities, overriding a `dim` action on
those lines.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `title` | str | `""` | |
| `highlight` | list of line specs | `[]` | entry *i* applies at beat *i*: `3`, `"2-4"`, `"1, 5-6"` or `[1, 4]` (1-based) |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style (`monokai`, `dracula`, `xcode`, ...); default: the theme's `code_style` (`github-dark`, `xcode` in `light_academic`) |
| `font` | str | role `code` (`font_mono`: JetBrains Mono NL) | font family of the listing |
| `size` | size | `caption` | starting font size (scaled to fill the frame, up to 1.5x) |
| `highlight_color` | color | `highlight` | |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the listing below `size` / the readable minimum |

```yaml
- id: listing
  type: code
  params:
    path: assets/train.py
    highlight: ["1-3", "8", "10-12"]
  beats:
    - text: "We load the data."
    - text: "Define the loss."
    - text: "And train."
```

### `code_morph`

Code that changes on screen: version 1 of a listing shows with beat 1, and at beat *i* it morphs
into version *i*. vidgen finds what changed (Python's `difflib`, line by line, then token by
token within an edited line), so you write only the versions: what both versions share
(unchanged lines, and the unchanged tokens of an edited line) glides to its new place, new
lines grow in from their left end, new tokens of an edited line fade in, removed lines and
tokens fade out, and the window resizes. A line that is only re-indented (wrapped in a new
`for`) or moved elsewhere glides too. With more versions than beats they are spread evenly;
extra beats hold.

- **On a word**: `{reveal: version2, at: "@cache"}` in a beat morphs to version 2 as the
  narrator says "cache" ([Actions on a spoken word](#actions-on-a-spoken-word)); a version an
  action reveals is left to that action (its beat does not morph at its start).
  `run_time: 1.5` gives the action's morph the time the scene's own takes (up to 1.5 s).
- **`highlight`** of a version marks its lines once it shows (the others dim, a soft band marks
  them): a line spec as in [`code`](#code), or `changed`: the lines that are new or differ from
  the version before (moved and re-indented ones included).
- **Readability** as in [`code`](#code): one font size for every version (the largest version
  fits the frame, up to 1.5x `size`); long lines wrap at the same width in every version, so a
  vertical frame keeps at least 32 characters per line at the readable minimum. The versions
  share the top of the window and are centred across the frame.
- **Checks** (`vidgen validate`): at least two versions; a version that repeats the one before
  (nothing would change); a `highlight` past its version's last line; a missing `path`.
- [Action targets](#beat-actions): `title`, `listing` (the window, whichever version shows),
  `version<N>` (revealing it morphs to it) and `version<N>.line<K>` (line K of version N, with
  its number; all its pieces when wrapped).

| param | type | default | |
|---|---|---|---|
| `versions` | list | — | at least two, in order: each the code (a string) or `{code, path, highlight}` (exactly one of `code` / `path`, a file in the project); version *i* shows at beat *i* |
| `language` | str | from the first file name, else `python` | a Pygments lexer name |
| `title` | str | `""` | |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style |
| `font` | str | role `code` (`font_mono`) | font family of the listing |
| `size` | size | `caption` | starting font size (the largest version scaled to fill the frame, up to 1.5x) |
| `highlight_color` | color | `highlight` | |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the listing below `size` / the readable minimum |

```yaml
- id: faster
  type: code_morph
  params:
    title: "Make it faster"
    versions:
      - |
        def fib(n):
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)
      - code: |
          from functools import cache

          @cache
          def fib(n: int) -> int:
              if n < 2:
                  return n
              return fib(n - 1) + fib(n - 2)
        highlight: changed
  beats:
    - text: "Here is the slow recursive version."
    - text: "Add a cache, and every value is computed once."
      actions:
        - {reveal: version2, at: "@cache", run_time: 1.5}
```

### `code_walkthrough`

A long listing in a window of fixed height that scrolls, beat by beat, to the lines the narration
talks about. Steps: one per entry of `steps` (step 1 comes with the window): the window scrolls
smoothly so the step's `lines` are in view (centred, or left where they are when they already
show), the other lines dim and a band marks the selected ones; the step's `note` appears beside
the lines or below the window, and `focus` moves the camera in on them. A step without `lines`
keeps the previous lines and view (e.g. a second note on the same lines); `lines: all` removes the
highlight. With more steps than beats they are spread evenly; extra beats hold.

**Lines** are written as in [`code`](#code) — `12`, `"3-7"`, `"1, 5-6"`, `[3, 4]` — or by content:
`"/def train/"` is the first line the regular expression matches (Python syntax, searched within
each line), `"/def train/-/return/"` runs from there to the first match of the second expression
at or after it, and numbers and expressions mix (`"40-/return/"`). Numbers are the file's own:
with `excerpt: "40-120"` only those lines are shown and steps count from 40. `vidgen validate`
reports lines past the end and expressions that match nothing.

**Per-beat data** lives in `steps`, aligned with the beats like `code`'s `highlight` and
`diagram`'s `steps`: entry *i* is beat *i*. An entry is `{lines, note, focus}` or just a line
spec (`- "3-7"`).

**Size and wrapping.** The listing keeps `size` while the window's width allows (it is never
scaled up), else gets smaller down to the readable minimum (or the size that keeps 32 characters
per line, if larger) and wraps long lines there, with their numbers kept (as in `code`). The
window is as tall as the space allows (`visible` caps it); in a 16:9 frame that is about 9 lines at
the `caption` size, with notes below. A scroll indicator on the right shows where the view is.
Syntax colours that would read poorly on the window or on the highlight band (a Pygments `style`
that does not suit the theme) are mixed towards the theme's `text` colour, and the band is made
fainter on themes where it would cost contrast.

**Notes.** `note_position: side` puts each note in a callout beside the window, level with its
lines and pointing at them; `bottom` puts it in a bar under the window (as tall as the tallest
note, so the window does not change size). `auto` uses `side` in 16:9 when the code fits beside
the notes without wrapping (lines up to about 40 characters at `caption`), else `bottom`; a
vertical frame always uses `bottom`. A note belongs to its step and goes with it: the next step's
note fades in only after it has faded out (in the first and second half of the step's change),
so two notes never show on top of each other.

**Focus.** `focus: true` moves the camera in on the step's lines (as close as they fit, at most
`focus_scale`; a number sets the magnification) while the other lines fade out, and shows the
note as a card under them at its normal size. The next step without `focus` moves the camera
back. The camera never stops halfway through the title. Very wide lines leave little to enlarge
(the camera stays, with a warning).

[Action targets](#beat-actions): `title`, `listing` (the window), `line<N>` (a line by its number,
with its number label; all its pieces when wrapped), `lines:<a-b>` (every range in listings of
up to 40 lines; in longer ones the ranges the steps select, as `lines:12-18`) and `note<N>` (the
note of step N). Revealing a line that is out of view scrolls to it; revealing a note plays its
step. The scene's own steps set line opacities, so a `dim` action on lines lasts until the next
step.

| param | type | default | |
|---|---|---|---|
| `code` | str | — | inline code; give exactly one of `code` / `path` |
| `path` | str | — | file in the project (checked by `vidgen validate`) |
| `language` | str | from the file name, else `python` | a Pygments lexer name |
| `excerpt` | str | none | `"a-b"`: show only those lines of the code (they keep their numbers) |
| `title` | str | `""` | above the window |
| `steps` | list | `[]` | step *i* at beat *i*: `{lines, note, focus}` or a line spec; none: the listing from the top, no highlight |
| `steps[].lines` | line spec | none (keep) | `12`, `"3-7"`, `"1, 5-6"`, `[3, 4]`, `"/regex/"`, `"/a/-/b/"`, or `all` (no highlight) |
| `steps[].note` | str | `""` | short annotation of the step |
| `steps[].focus` | bool \| number | `false` | `true`: enlarge the lines (camera); a number (1–4): that magnification |
| `visible` | int (≥ 3) | as many as fit | lines the window shows at once |
| `line_numbers` | bool | `true` | |
| `style` | str | theme `code_style` | a Pygments style |
| `font` | str | role `code` (`font_mono`) | font family of the listing |
| `size` | size | `caption` | font size of the listing (smaller only to fit the width; never below the readable size) |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the listing below `size` / the readable size |
| `highlight_color` | color | `highlight` | band, its edge bar, notes' frame and pointer |
| `note_position` | `auto` \| `side` \| `bottom` | `auto` | see above |
| `note_size` | size | `body` | note text size |
| `note_color` | color | `text` | note text colour |
| `focus_scale` | number (1–4) | `2.0` | largest magnification of `focus: true` |
| `scrollbar` | bool | `true` | scroll indicator when the code is longer than the window |

```yaml
- id: walkthrough
  type: code_walkthrough
  params:
    title: "Walking through a training loop"
    path: assets/train.py
    steps:
      - {lines: "8-12", note: "All settings live in one small dataclass."}
      - {lines: "/def loss_and_grads/-/loss = gw/", note: "The loss: a mean squared error."}
      - {lines: "/err = /", note: "The prediction error drives it all.", focus: true}
      - "/for batch in/-/b -= /"          # just lines: no note
  beats:
    - text: "A code walkthrough scrolls through a long file. First, the settings."
    - text: "Then it scrolls down to the loss function."
    - text: "Focus enlarges a line: here, the prediction error."
    - text: "And the update itself is plain gradient descent."
```

Building a long listing takes about 0.1 s per line (Manim draws every character); `excerpt`
keeps a big file's walkthrough to the part it talks about.

### `terminal`

A terminal window in which commands are typed and their output appears. **You write the
output**: vidgen never runs a command. Step *i* of `steps` plays at beat *i* (the window comes
in with step 1): the command is typed at the prompt, a block cursor moving along
(`typing_speed` characters per second; faster when the beat is too short for it), a moment
later its output appears row by row and the prompt comes back, the cursor waiting after it.
With more steps than beats they are spread evenly; extra beats hold. The look is the code
scenes': the theme's window, font and Pygments style; the commands are coloured by `language`
(a Pygments lexer, `bash` by default; `pycon` for a Python prompt), the output by the style's
colour for program output (or the step's `output_color`), the prompt by `prompt_color`.

- **Steps**: `{command, output, clear, output_color}`, or a string (a command alone). A step with
  only an `output` is a program still running and printing (no prompt before it); the prompt
  comes back after the last step unless that step is such an output. A command may take several
  lines (typed one after the other). `clear: true` clears the screen before the step: its
  page starts at the top of the same window (the window is as large as the largest page).
- **On a word**: `{reveal: output2, at: "@fails"}` shows step 2's output as the narrator says
  "fails", `{reveal: command2, at: "@run"}` types the command then (with its output, unless an
  action shows that); a `reveal` of a command takes its typing time ([Actions on a spoken
  word](#actions-on-a-spoken-word)). The scene leaves what an action shows to it; what comes
  before it on the screen and is not shown yet appears at once.
- **Beside code**: `code: {code | path, language, highlight}` puts a code listing (with line
  numbers, a `highlight` band) beside the terminal: on the left, or above it when that gives
  larger text (always above in a vertical frame); both use one font size. After a `code` or
  `code_morph` scene of the same code, `carry: ["listing -> code"]` (with `transition: cut`)
  makes the listing glide from where it was into place ([continuity](#continuity-carrying-objects-into-the-next-scene-carry)).
- **Readability** as in [`code`](#code): the text fills the window's space up to 1.5x `size`;
  long lines wrap (hanging indent) rather than shrink below the readable minimum, which keeps a
  vertical frame readable. Keep a session short (about 10 rows per page; `clear` starts a new
  one) and the output to the lines that matter.
- **Checks** (`vidgen validate`): a step needs a command or an output; `clear` on step 1; an
  unknown `language`; `code` with both or neither of `code` / `path`, a missing file, a
  `highlight` past its end.
- [Action targets](#beat-actions): `title`, `terminal` (the window), `command<N>` (step N's
  command; revealing it types it), `output<N>` and `output<N>.line<K>` (line K of step N's
  output; blank lines are not targets), `code` and `code.line<K>` (the listing beside it).

| param | type | default | |
|---|---|---|---|
| `steps` | list | — | at least one, in order: a command (a string) or `{command, output, clear, output_color}`; step *i* plays at beat *i* |
| `steps[].command` | str | none | what is typed at the prompt (several lines: typed one after the other) |
| `steps[].output` | str | none | what it prints, written by you |
| `steps[].clear` | bool | `false` | clear the screen before this step (not on step 1) |
| `steps[].output_color` | color | style's output colour | e.g. an error in `secondary` |
| `prompt` | str | `"$"` | `""` for none, `">>>"`, `"PS C:\\>"` |
| `language` | str | `bash` | Pygments lexer of the commands |
| `typing_speed` | number (0–200] | `18` | characters typed per second |
| `code` | `{code, path, language, highlight}` | none | a code listing beside the terminal (above it in a vertical frame) |
| `title` | str | `""` | above the window(s) |
| `prompt_color` | color | `accent` | |
| `line_numbers` | bool | `true` | of the code beside the terminal |
| `style` | str | theme `code_style` | a Pygments style, for the terminal and the code |
| `font` | str | role `code` (`font_mono`) | |
| `size` | size | `caption` | starting font size (scaled to fill the space, up to 1.5x); one size for the terminal and the code |
| `highlight_color` | color | `highlight` | band behind the code's `highlight` |
| `wrap` | bool | `true` | wrap long lines instead of shrinking the text below `size` / the readable minimum |

```yaml
- id: tests
  type: terminal
  params:
    title: "Run the tests"
    code: {path: assets/stats.py, highlight: 4}
    steps:
      - command: "pytest -q"
        output: |
          ..F
          FAILED test_stats.py::test_mean - ZeroDivisionError
          1 failed, 2 passed in 0.03s
        output_color: secondary
      - {command: "python -c 'import stats; print(stats.mean([2, 4]))'", output: "3.0", clear: true}
  beats:
    - text: "We run the tests, and one of them fails."
      actions: [{reveal: output1, at: "@fails"}]
    - text: "By hand, the mean of two and four is three."
```

### `stat`

One big number that counts up, with what it means, an optional comparison and a context line.
Steps: (1) icon, number (counting from `count_from` to `value`, easing out so the last digits
settle) and label, (2) comparison and context; with one beat both come in it.
[Action targets](#beat-actions): `icon`, `value`, `label`, `comparison`, `context` (those present).

Layout, centred in the safe area: icon, number, label, comparison, context. The number is
`size` (default 3x the theme's `title` size) unless that is wider than the frame, then smaller;
the count never changes its size. In a vertical frame the parts are spaced 1.3x further apart.
Numbers use the `heading` font role (serif in `light_academic`/`warm_editorial`).

| param | type | default | |
|---|---|---|---|
| `value` | float | required | the number shown |
| `label` | str | `""` | what the number is, under it |
| `context` | str | `""` | smaller line at the bottom (period, population, source) |
| `prefix`, `suffix` | str | `""` | before/after the number at its size (`"$"`, `"%"`, `"x"`) |
| `unit` | str | `""` | after the number, smaller, on its baseline (`"ms"`, `"users"`) |
| `decimals` | int 0–6 | automatic | decimals of every number shown (also while counting); default: what `value` and the comparison value need, up to 2 |
| `thousands` | str | `","` | thousands separator: `","`, `"."`, `" "`, `"'"` or `""` |
| `decimal_mark` | str | `"."` | `"."` or `","` (e.g. `thousands: "."`, `decimal_mark: ","` for German) |
| `count` | bool | `true` | count up in beat 1; `false`: the number fades in |
| `count_from` | float | `0` | where the count starts; with a `kind: before` comparison, its value |
| `comparison` | number \| mapping | none | a value to compare with (below); a plain number is `{value: N}` |
| `icon` | icon | none | above the number |
| `icon_color`, `color`, `label_color`, `context_color`, `comparison_color` | color | `primary`, `primary`, `text`, `dim`, `dim` | `color` is the number's (prefix, suffix and unit too) |
| `good_color`, `bad_color`, `neutral_color` | color | `tertiary`, `accent`, `dim` | the change chip: better, worse, no change / `better: neither` |
| `size` | size | 3x `title` | number size (shrunk to fit) |
| `label_size`, `context_size`, `comparison_size` | size | `subtitle`, `caption`, `body` | |

**Comparison** (`comparison: {value, label, kind, word, delta, better}`): a row under the label
with the change in a chip (an arrow and the delta, coloured by whether the change is good) and
the words `vs 12% last year`.

| key | default | |
|---|---|---|
| `value` | required | the other value, written with the same prefix, suffix, unit and decimals |
| `label` | `""` | words after it (`"last year"`, `"in 4K"`) |
| `kind` | `versus` | `versus`: "vs 12%"; `before`: a before → after change, the number counts from this value ("from 12%") |
| `word` | `vs` / `from` | the word before the other value (`""` for none; translate it in a language variant) |
| `delta` | `difference` | the chip shows the `difference` (`+19%`, with prefix/suffix/unit), the `percent` change (`+158%`; needs a non-zero value) or `none` (no chip) |
| `better` | `higher` | which direction is good: `higher`, `lower` (costs, latency), `neither` (always neutral) |

```yaml
- id: adoption
  type: stat
  params:
    value: 73
    suffix: "%"
    label: "of developers use AI coding tools"
    comparison: {value: 44, label: "in 2023"}     # chip "▲ +29%" in good_color, "vs 44% in 2023"
    context: "Survey of 12,000 developers, 2025"
  beats:
    - text: "Seventy-three percent of developers now use AI coding tools."
    - text: "Up from forty-four percent two years earlier."
- id: latency
  type: stat
  params:
    value: 12.5
    unit: "ms"
    label: "median latency"
    comparison: {value: 18, kind: before, better: lower, delta: percent}   # counts down from 18
  beats:
    - text: "Median latency fell from eighteen to twelve and a half milliseconds."
```

### `chapter`

A section divider: an optional number, the chapter's `title`, an optional subtitle and icon.
An accent rule draws in, the number (with the icon) and the title slide towards it from either
side, the subtitle rises. In a wide frame with a number or icon, they stand left of a vertical
rule and the title (left-aligned) right of it; otherwise (vertical frames, or only a title) the
parts are stacked and centred, the rule a short line between number and title.
Steps: with two or more beats, (1) rule, icon, number and title, (2) subtitle; with one beat,
or silent with a `duration`, everything comes in together. Further beats hold.
[Action targets](#beat-actions): `icon`, `number`, `title`, `subtitle` (those present).

The chapter's name is its `title` param (what a chapter list or indicator shows; a
`chapter:` key on the scene renames it there, see [chapters](#chapters)).

| param | type | default | |
|---|---|---|---|
| `title` | str | required | the chapter's name; wrapped to fit |
| `number` | int \| str | none | an integer is shown with `number_format` (`02`); text as written (`"II"`, `"Part 2"`) |
| `number_format` | str | `"{:02d}"` | Python format for an integer `number`: `"{}"` gives `2`, `"Part {}"` gives `Part 2` |
| `subtitle` | str | `""` | |
| `icon` | icon | none | above the number, or in its place |
| `rule` | bool | `true` | draw the accent rule |
| `number_color`, `rule_color`, `icon_color`, `title_color`, `subtitle_color` | color | `primary`, `primary`, `primary`, `text`, `dim` | |
| `number_size` | size | 2.4x `title` (1.6x for text) | shrunk to fit |
| `title_size`, `subtitle_size` | size | `title`, `subtitle` | |

```yaml
- id: part2
  type: chapter
  params: {number: 2, title: "Results", subtitle: "What the benchmark shows", icon: chart-line}
  duration: 3                      # silent divider; or give it beats
```

### `comparison`

Two or three columns side by side — A vs B, before / after, three options — each on a card
with a heading, an optional icon and a list of points. A column's `tone` colours it and marks
its points: `positive` (check marks, `positive_color`), `negative` (crosses, `negative_color`)
or `neutral` (dots, `neutral_color`; the heading keeps `heading_color`). An optional `verdict`
line closes the scene. In a vertical frame the columns are stacked.
Steps with `reveal: columns` (default): (1) column 1 (with the heading), (2) column 2, ...,
then the verdict; `reveal: rows`: (1) the column headings, then one point of every column per
step (side by side, the *m*-th points of all columns share a line), then the verdict; `reveal:
all`: every column in step 1, the verdict in step 2.
[Action targets](#beat-actions): `heading`, `col<N>`, `col:<heading>`, `col<N>.item<M>`
(1-based) and `verdict`.

Layout: heading in the `header` region, verdict at the bottom, the cards share the rest
(columns in 16:9, rows in 9:16) and are as tall as the tallest column. Point text starts at
`size` (1.3x in a vertical frame, like the column headings and the verdict) and is reduced
together in every column, not below the readable minimum, until the
columns fit; a comparison that still does not fit is scaled down with a warning (shorten or
remove points).

| param | type | default | |
|---|---|---|---|
| `columns` | list (2–3) | required | `{heading, icon, tone, points}` per column (below) |
| `heading` | str | `""` | above the columns |
| `verdict` | str | `""` | the conclusion, shown in a last step |
| `reveal` | `columns` \| `rows` \| `all` | `columns` | |
| `markers` | bool | `true` | check / cross / dot before each point (a point's own icon always shows) |
| `cards` | bool | `true` | each column on a card in the theme's `surface` colour, outlined in its tone |
| `vs` | str | `""` | text in a small badge between the columns (`"vs"`, `"→"`) |
| `positive_color`, `negative_color`, `neutral_color` | color | `tertiary`, `accent`, `primary` | the tone colours (green and red in every built-in preset) |
| `color`, `heading_color`, `verdict_color` | color | `text`, `text`, `highlight` | point text; scene heading and neutral column headings; verdict |
| `size`, `column_size`, `heading_size`, `verdict_size` | size | `body`, `subtitle`, `heading`, `body` | point text, column headings (reduced with the points), scene heading, verdict |

A column is `{heading, icon, tone, points}`: `heading` (required), `icon` (left of the heading,
in the tone colour), `tone` (`positive`, `negative` or `neutral`, the default) and `points`
(up to 8; each a string or `{text, icon}`, the icon replacing the marker).

```yaml
- id: tradeoff
  type: comparison
  params:
    heading: "Monolith or microservices?"
    vs: "vs"
    columns:
      - heading: "Monolith"
        icon: package
        tone: positive
        points: ["One deploy", "Simple local setup", {text: "Easy refactoring", icon: pencil}]
      - heading: "Microservices"
        icon: network
        tone: negative
        points: ["Many deploys to coordinate", "Network failures between services"]
    verdict: "Start with a monolith; split when teams grow."
  beats:
    - text: "A monolith is one deploy with a simple setup."
    - text: "Microservices mean many deploys and network failures."
    - text: "So start with a monolith."
      actions:
        - {highlight: col1, style: box}
```

### `table`

A header and rows of cells (text or numbers), fitted to the frame, revealed row by row.
Number columns are right-aligned and formatted (`number_format`, default: the decimals the
column needs, with thousands separators); text columns are left-aligned. Every other row is
striped in `stripe_color` (the theme's `surface`); a rule in `header_color` runs under the
header and a thin one under the last row.
Steps with `reveal: per_beat` (default): (1) title, header, caption and row 1, (2) row 2, ...;
with more rows than beats they are spread evenly. `reveal: all`: the whole table in beat 1.
[Action targets](#beat-actions): `title`, `header`, `row<N>`, `row:<first cell>`, `col<N>`,
`col:<header>`, `cell<R>.<C>` and `caption` (1-based; rows count below the header; a row's
first cell as shown, e.g. `row:4K`, `cell2.3`). A `highlight` with `style: fill` lays a
translucent band over a row, column or cell; `box` frames it.

**Fitting.** The title is in the `header` region (1.3x in a vertical frame, like every header
band), the caption at the bottom; the table is centred in the space between, and a table
shorter than that space takes its caption along (just under it, the two centred together). Cell text starts at `size`; when the table is too wide, columns
share the width (a column that needs less keeps its natural width) and text wraps — headings
at any space, body cells of more than 16 characters at spaces; numbers and short cells never
wrap. The size is then reduced until the table fits, not below the readable minimum (lint's
`min_font`). A table that does not fit even then is scaled down and a warning says so: split
it into smaller tables (or drop columns), which is mostly a vertical (9:16) problem — a 9:16
frame holds about 3–4 columns and 12 short rows. In 9:16 rows get more vertical padding.

| param | type | default | |
|---|---|---|---|
| `rows` | list of lists | required | 1–30 rows of cells: text or numbers (`""` for an empty cell); every row as long as the header |
| `header` | list[str] | `[]` | column headings; sets the number of columns (at most 8) |
| `title` | str | `""` | above the table |
| `caption` | str | `""` | note under the table (e.g. the source) |
| `align` | str \| list | `auto` | `auto` (numbers right, text left), `left`, `center`, `right`; one for all columns or one per column |
| `number_format` | str \| list | automatic | Python format for numbers: `"{:,.1f}"`, `"{:.0%}"`, `"${:,.0f}"`, `"{:,.0f}M"`; one for all or one per column (`null` = automatic) |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `zebra` | bool | `true` | stripe every other row |
| `color`, `header_color`, `stripe_color`, `rule_color` | color | `text`, `primary`, `surface`, `dim` | cells; header text and its rule; stripes; the rule under the last row |
| `title_color`, `caption_color` | color | `text`, `dim` | |
| `size`, `title_size`, `caption_size` | size | `body`, `heading`, `caption` | `size` is the cell text (headings too), reduced to fit |

```yaml
- id: results
  type: table
  params:
    title: "Benchmark"
    header: ["Model", "Params", "Accuracy"]
    rows:
      - ["Baseline", 110, 0.812]
      - ["Sparse", 55, 0.809]
      - ["Tiny", 14, 0.742]
    number_format: [null, "{:,.0f}M", "{:.1%}"]   # 110M, 81.2%
    caption: "Illustrative numbers"
  beats:
    - text: "The baseline has a hundred and ten million parameters."
    - text: "The sparse model halves that and loses almost nothing."
      actions:
        - {highlight: "row:Sparse", style: fill}
    - text: "The tiny model pays for its size."
      actions:
        - {highlight: "cell3.3", color: accent}
```

### `timeline`

Dated events along an axis: a horizontal one in 16:9 and square frames, a vertical one in 9:16
(`orientation` overrides). Each event is a marker on the axis (a disc with its icon when the
timeline has icons) and its date, title and optional detail text; events alternate sides of the
axis so neighbours do not collide (or all stand on one side — `sides: auto` picks whichever
keeps the text largest, typically alternating in 16:9 and one column right of the axis in 9:16).
As each event is revealed, a progress line grows along the axis to it.
Steps with `reveal: per_beat` (default): (1) heading, axis and event 1, (2) event 2, ...; with
more events than beats they are spread evenly. `reveal: all`: every event in step 1. A
`highlight` adds a last step: the other events dim, the chosen marker and title turn
`highlight_color`.
[Action targets](#beat-actions): `heading`, `axis`, `event<N>` and `event:<date>` (1-based; the
date as shown, e.g. `event:1969`; an event is its marker, stem and text).

**Spacing.** `even` (default) puts the events at equal gaps. `proportional` places them by date:
a number (`1969`, `2.5`), a year, `YYYY-MM` or `YYYY-MM-DD` (unquoted `2024-03-15` works too),
or an event's own `at` for anything else (`"500 BC"` with `at: -500`); events must be in time
order, and neighbours that are too close are pulled apart just enough to keep their markers
apart.

**Now.** `now` names the present event (0-based index, date or title): it gets a `now_label`
tag ("Now") and a ring in `now_color`; later events are drawn as planned (hollow markers, a
dashed progress line).

**Fitting.** Every event's text shares one size: up to 1.2x the requested sizes (1.5x along a
vertical axis, which has much more room) when every event has room without more wrapping, else reduced together down to the readable minimum (lint's
`min_font`); lines are wrapped to even lengths. A timeline that still does not fit is scaled
down and a warning says so: split it into two timelines or shorten the texts. 10 events with
detail texts are the limit of a 9:16 frame; 3–6 read best (and stay under lint's `max_words`).

| param | type | default | |
|---|---|---|---|
| `events` | list (2–10) | required | `{date, title, text, icon, at}` per event, in time order (below) |
| `heading` | str | `""` | above the timeline, with step 1 |
| `orientation` | `auto` \| `horizontal` \| `vertical` | `auto` | `auto`: horizontal in landscape and square frames, vertical in portrait |
| `sides` | `auto` \| `alternate` \| `one` | `auto` | alternate sides of the axis, or all below a horizontal / right of a vertical axis; `auto` picks the layout with the largest text (then the fewest lines) |
| `spacing` | `even` \| `proportional` | `even` | proportional: gaps follow the dates (or `at`) |
| `reveal` | `per_beat` \| `all` | `per_beat` | |
| `highlight` | int \| str | none | event emphasised in a last step: 0-based index (an int in range), or its date or title |
| `now` | int \| str | none | the present event (as `highlight`): a tag and ring; later events hollow with a dashed progress line |
| `now_label` | str | `"Now"` | text of the tag |
| `color`, `date_color`, `text_color` | color | `text`, `primary`, `dim` | event title, date, detail text |
| `marker_color`, `axis_color`, `progress_color` | color | `primary`, `dim`, `primary` | markers and their icons; the axis (drawn faint); the progress line |
| `heading_color`, `highlight_color`, `now_color` | color | `text`, `highlight`, `accent` | |
| `size`, `date_size`, `text_size`, `heading_size` | size | `body`, `caption`, `caption`, `heading` | event title, date, detail text (all fitted together), heading |

An event is `{date, title, text, icon, at}`: `date` (required; text or a number, shown above the
title), `title` (required), `text` (a detail line, smaller and dimmer), `icon` (in the event's
marker) and `at` (a number: its position with `spacing: proportional` when the date is not one).

```yaml
- id: history
  type: timeline
  params:
    heading: "The space race"
    spacing: proportional            # gaps follow the years
    events:
      - {date: 1957, title: "Sputnik", text: "First satellite in orbit", icon: satellite}
      - {date: 1961, title: "Gagarin", text: "First human in space", icon: user}
      - {date: 1969, title: "Apollo 11", text: "First crewed Moon landing", icon: moon}
    highlight: "Apollo 11"           # a last step: the other events dim
  beats:
    - text: "In 1957 Sputnik reached orbit."
    - text: "Four years later, Gagarin flew."
    - text: "In 1969, Apollo 11 landed on the Moon."
    - text: "The landing is still the high point."
      actions:
        - {highlight: axis, style: flash}
```

### `diagram`

A flowchart or any directed graph — a pipeline, an architecture, a decision tree, a state
machine — laid out automatically: nodes in layers along the edges' direction (left to right in
16:9 and square frames, top to bottom in 9:16; `direction` overrides), each layer ordered to
avoid crossing edges, edges routed between the nodes with arrowheads that end on the node's
outline. A cycle (an edge back to an earlier node) is drawn as one edge running backwards. Also
available as type **`flowchart`** (the same scene).
Steps with `reveal: nodes` (default): one node per step in layout order (layer by layer; within
a layer top to bottom or left to right), each after the edges leading to it from nodes on
screen have grown in from their source; the heading comes with step 1. `reveal: layers`: one
layer per step; `all`: everything in step 1. With more steps than beats they are spread evenly.
**Explicit `steps`** replace that: per step a node id or an edge `"a->b"`, or a list of them.
An edge appears with its nodes unless a later step names it (then it grows in that step); an
edge named in a step brings its nodes; nodes no step names come in one more step at the end.
A `highlight` adds a last step: the listed nodes and edges turn `highlight_color` (outline,
tint, icon, line; labels keep their colour) and everything else dims — list a path as node ids
(`[start, check, ship]`: the edges between consecutive ones are highlighted too) and add single
edges as `"a->b"`.
[Action targets](#beat-actions): `heading`, `node<N>` (1-based, in the order of `nodes`),
`node:<id>` and `edge:<from>-><to>` (`edge:check->ship`; patterns such as `edge:check->*`
select every edge leaving a node). Revealing an edge early brings its nodes too.

**Nodes** are written as their id (`- Load data`: the id is also the label) or as
`{id, label, shape, icon, color}`: `id` (letters, digits, spaces, `_`, `.`, `-`), `label` (the
text, wrapped; default the id), `shape` (`box`, `round` (rounded corners), `pill` (start/end),
`circle`, `diamond` (a decision), `cylinder` (a database); default the scene's `shape`),
`icon` (above the label in left-to-right layouts, circles and diamonds; else beside it) and `color` (outline, tint and
icon; default `node_color`).

**Edges** use a shorthand: `"a -> b"`, `"a -> b: label"` (text on the edge, near its start),
`"a --> b"` (dashed), or a chain `"a -> b -> c"` (one edge per arrow; a label needs a single
arrow). The long form is `{from, to, label, style: solid | dashed, color}`. Each edge may be
listed once, a node may not point to itself, and every id must be a node: `vidgen validate`
reports e.g. `edges[2] (start -> shp): unknown node 'shp'; did you mean 'ship'? (nodes: ...)`.

**Fitting.** Labels share one size: up to 1.3x the requested `size` when the diagram has room,
else reduced (with the edge labels) down to the readable minimum (lint's `min_font`); per
direction (with `auto`, the other one is tried too and wins only if it keeps the text 10 %
larger) and label wrap width the layout with the largest text is used, and spare room widens the
gaps. A diagram that still does not fit is scaled down and a warning says so: split it or
shorten the labels. Up to ~12 nodes read well in 16:9, fewer in 9:16 (wide layers do not fit a
narrow frame; long chains do).

| param | type | default | |
|---|---|---|---|
| `nodes` | list (1–30) | required | node ids, or `{id, label, shape, icon, color}` (above) |
| `edges` | list (≤ 60) | `[]` | `"a -> b"`, `"a -> b: label"`, `"a --> b"`, `"a -> b -> c"`, or `{from, to, label, style, color}` |
| `heading` | str | `""` | above the diagram, with step 1 |
| `direction` | `auto` \| `LR` \| `TB` | `auto` | layers left to right or top to bottom; `auto`: `LR` in landscape and square frames, `TB` in portrait |
| `routing` | `curved` \| `straight` \| `orthogonal` | `curved` | smooth S-curves, straight lines, or right angles (each edge in its own lane) |
| `reveal` | `nodes` \| `layers` \| `all` | `nodes` | ignored when `steps` is given |
| `steps` | list | none | per step a node id, an edge `"a->b"`, or a list of them |
| `highlight` | list[str] | `[]` | node ids (a path: edges between consecutive ones too) and edges `"a->b"`, emphasised in a last step |
| `shape` | `box` \| `round` \| `pill` \| `circle` \| `diamond` \| `cylinder` | `round` | default node shape |
| `node_color`, `label_color` | color | `primary`, `text` | node outline / tint / icon; label text |
| `edge_color`, `edge_label_color` | color | `dim`, `dim` | |
| `heading_color`, `highlight_color` | color | `text`, `highlight` | |
| `size`, `edge_label_size`, `heading_size` | size | `body`, `caption`, `heading` | node labels and edge labels are fitted together |

```yaml
- id: release
  type: flowchart                    # = diagram
  params:
    heading: "How a change ships"
    nodes:
      - {id: start, label: "Pull request", shape: pill}
      - {id: ci, label: "Tests pass?", shape: diamond}
      - {id: fix, label: "Fix the code"}
      - {id: ship, label: "Deploy", icon: rocket, shape: circle}
    edges:
      - "start -> ci"
      - "ci -> ship: yes"
      - "ci -> fix: no"
      - "fix --> ci"                 # dashed; a cycle is drawn as an edge running back
    highlight: [start, ci, ship]     # the happy path, in a last step
  beats:
    - text: "Every change starts as a pull request."
    - text: "If the tests fail, we fix the code and try again."
      actions:
        - highlight: "edge:fix->ci"
          style: flash
    - text: "Otherwise it is deployed."
    - text: "That is the path most changes take."
```

### `flowchart`

The same scene type as [`diagram`](#diagram) (same params, steps and targets), under the name a
flowchart is usually looked up by.

### `process`

A pipeline of 2–8 stages that something passes through — a request, an order, a batch of data —
with a **token** (a dot, or an icon) that travels from stage to stage. Stages stand in a row in
16:9 and square frames, in two rows when that keeps the text clearly larger (the second row runs
back, "snaking"; typical for 6–8 stages), and in a column in 9:16 (`layout` overrides). Each
stage is a card with its label, an optional icon and an optional detail line; connectors with
arrowheads join them.
Steps with `reveal: per_beat` (default): (1) heading, `input` and stage 1 (the token arrives at
it), (2) the connector to stage 2 grows while the token travels along it and stage 2 appears, ...;
the `output` comes with the last stage. The stage where the token is is the **active** one: its
outline and icon turn `active_color`, and the previous stage returns to normal. `loop: true` adds
an arrow from the last stage back to the first (below a row, beside a column) and a last step in
which the token follows it. `reveal: all` shows the whole pipeline in step 1; the following steps
only move the token, one stage per step. With more steps than beats they are spread evenly.
While travelling, the token passes behind the stage it leaves and waits in front of the next
one, on its connector's arrowhead.
[Action targets](#beat-actions): `heading`, `input`, `stage<N>` (1-based), `stage:<label>`,
`connector<N>` (from stage N to N+1), `loop`, `output` and `token` (those the pipeline has).

**Fitting.** Stage texts share one size: up to 1.2x the requested sizes (1.5x in a column)
when the pipeline has room without more wrapping, else reduced together down to the readable minimum (lint's `min_font`); `input`/`output`
labels stand above their arrows (above and below a column). A pipeline that still does not fit
is scaled down and a warning says so: shorten the texts or split it into two scenes. Short
labels with an optional detail line read best; 3–5 stages with details fit a 16:9 row.

| param | type | default | |
|---|---|---|---|
| `stages` | list (2–8) | required | a label, or `{label, icon, text}` per stage (labels must differ) |
| `heading` | str | `""` | above the pipeline, with step 1 |
| `layout` | `auto` \| `row` \| `snake` \| `column` | `auto` | `auto`: a column in portrait frames, else a row (two snaking rows when that keeps the text 10 % larger) |
| `reveal` | `per_beat` \| `all` | `per_beat` | `all`: the whole pipeline in step 1, then the token moves one stage per step |
| `loop` | bool | `false` | an arrow from the last stage back to the first; the token follows it in a last step |
| `loop_label` | str | `""` | text on the loop arrow (`repeat`, `next batch`); needs `loop` |
| `input`, `output` | str | `""` | what goes in / comes out, with an arrow into the first / from the last stage |
| `token` | bool | `true` | the travelling token |
| `token_icon` | icon | none | draw the token as this icon in a small disc instead of a dot |
| `token_label` | str | `""` | a short tag that travels with the token (`order`, `request`) |
| `stage_color`, `active_color` | color | `primary`, `highlight` | card outlines and icons; those of the active stage |
| `label_color`, `text_color` | color | `text`, `dim` | stage labels, detail lines |
| `connector_color`, `token_color` | color | `dim`, `accent` | connectors and loop arrow; the token and its tag |
| `io_color`, `heading_color` | color | `dim`, `text` | input, output and loop labels; heading |
| `size`, `text_size`, `io_size`, `heading_size` | size | `body`, `caption`, `caption`, `heading` | stage labels, detail lines (fitted together), input/output/loop/token labels, heading |

```yaml
- id: orders
  type: process
  params:
    heading: "What happens to an order"
    input: "Checkout"
    output: "At your door"
    token_label: "order"
    stages:
      - {label: "Pay", icon: credit-card, text: "card or invoice"}
      - {label: "Pack", icon: package}
      - {label: "Ship", icon: truck, text: "1-2 days"}
  beats:
    - text: "At checkout, the order is paid."
    - text: "The warehouse packs it."
    - text: "And a courier ships it to your door."
      actions:
        - {highlight: token, style: flash}
```

### `network`

A layered neural network: layers of units (dots) joined by edges, left to right in 16:9 and
square frames, top to bottom in 9:16 (`direction` overrides). A layer larger than `max_neurons`
shows `show` units with an ellipsis between them (half before it, half after) and its unit count
under the label, e.g. 6 dots for a layer of 512. Each layer connects to the previous one
`dense` (every unit to every unit), `sparse` (a reproducible share `ratio` of the pairs, every
unit keeping a connection), `grouped` (both layers split into `groups` blocks, block to block,
coloured by block from the theme palette as in grouped convolutions), `one_to_one` or `none`;
the scene's `connect` is the default, a layer's `connect` overrides it. Edges are drawn between
the units shown (at most `max_edges` per pair of layers, thinned evenly beyond that), thinner
and fainter the more there are, so wide layers do not turn into a hairball.
Steps with `reveal: layers` (default): (1) heading and layer 1, (2) the edges into layer 2 grow
from layer 1, then its units appear, ...; `reveal: all`: the whole network in step 1. Then
`passes` forward passes (default 1), each a step: a pulse in `pulse_color` runs along the edges
layer by layer and each layer's units flash as it arrives. A `highlight` adds a last step: the
listed units grow and turn `highlight_color`, so do the edges between consecutive ones in
neighbouring layers (drawn if the connection had none), and everything else dims.
[Action targets](#beat-actions): `heading`, `layer<N>` (1-based; units, ellipsis, label and
count), `layer:<label>`, `edges<N>` (between layer N and N+1, if they have edges) and
`neuron<L>.<i>` (unit i of layer L as drawn, 1-based from the top or left, the ellipsis not
counted: `neuron2.3`).

| param | type | default | |
|---|---|---|---|
| `layers` | list (2–8) | required | a size, or `{size, label, show, connect, color}` per layer, input first (below) |
| `heading` | str | `""` | above the network, with step 1 |
| `connect` | connection | `dense` | how each layer connects to the previous one: `dense`, `sparse`, `grouped`, `one_to_one`, `none`, `"sparse:0.3"`, `"grouped:3"` or `{type, ratio, groups}` |
| `direction` | `auto` \| `LR` \| `TB` | `auto` | `auto`: `TB` in portrait frames, else `LR` |
| `max_neurons` | int (2–12) | `8` | layers with more units are drawn with an ellipsis |
| `show` | int (2–12) | `6` | units drawn for such a layer (a layer's `show` overrides it) |
| `counts` | `auto` \| `all` \| `none` | `auto` | unit counts under the labels: `auto` only for layers drawn with an ellipsis |
| `count_format` | str | `"{n:,}"` | Python format of the count with `n` (`"{n:,} units"`) |
| `reveal` | `layers` \| `all` | `layers` | |
| `passes` | int (0–4) | `1` | forward-pass steps after the network is built |
| `highlight` | list[str] | `[]` | units as `"layer.unit"` (1-based, as drawn): `["1.2", "2.3", "3.1"]` marks a path in a last step |
| `max_edges` | int (4–200) | `64` | most edges drawn between two layers |
| `neuron_color`, `edge_color` | color | `primary`, `dim` | units (unless a layer sets `color`); edges |
| `group_colors` | bool | `true` | colour `grouped` edges by block (theme palette) |
| `edge_opacity` | float | auto | edge opacity; default lower the more edges a pair of layers has |
| `label_color`, `count_color` | color | `text`, `dim` | layer labels, counts |
| `pulse_color`, `highlight_color`, `heading_color` | color | `accent`, `highlight`, `text` | |
| `label_size`, `heading_size` | size | `caption`, `heading` | labels and counts (never below the readable minimum), heading |

A layer is `{size, label, show, connect, color}`: `size` (required; the number of units it
has), `label`, `show` (units drawn when it is larger than `max_neurons`), `connect` (to the
previous layer; not on the first layer) and `color` (its units). A connection's long form is
`{type, ratio, groups}` (`ratio` 0.35 for `sparse`, `groups` 2 for `grouped`).

```yaml
- id: mlp
  type: network
  params:
    heading: "A small classifier"
    layers:
      - {size: 784, label: "Pixels", show: 5}
      - {size: 128, label: "Hidden"}
      - {size: 10, label: "Digits", connect: "sparse:0.4"}
    highlight: ["1.2", "2.3", "3.4"]
  beats:
    - text: "Each pixel of the image is an input."
    - text: "A hidden layer of 128 units combines them."
    - text: "Ten outputs score the ten digits."
    - text: "In a forward pass, the signal flows from left to right."
      actions:
        - {highlight: "layer:Digits", style: box, at: 0.5}
    - text: "This path leads to the answer."
```

### `end_card`

Steps: (1) logo, icon and title, (2) lines. Fades out over 1 s.
[Action targets](#beat-actions): `logo`, `icon`, `title`, `line<N>` (1-based; those present).

| param | type | default | |
|---|---|---|---|
| `title` | str | `""` | at least one of `title`, `lines`, `logo`, `icon` |
| `lines` | list[str] | `[]` | links, credits; short lines shrink together instead of wrapping |
| `logo` | str | none | image file in the project (checked by `vidgen validate`) |
| `icon` | icon | none | icon above the title (below the logo, if both) |
| `icon_color` | color | `primary` | |
| `title_color`, `color` | color | `highlight`, `text` | |
| `title_size`, `size` | size | `title`, `body` | |

```yaml
- id: outro
  type: end_card
  params:
    title: "Are LLMs over-parameterized?"
    icon: link
    lines: ["github.com/me/my-project", "huggingface.co/me"]
  beats:
    - text: "Code and models are online. Thanks for watching."
```

### `text_card`

One block of text, wrapped to fit, faded in at the first beat and held (no fade-out).
[Action targets](#beat-actions): `text`.

| param | type | default | |
|---|---|---|---|
| `text` | str | required | |
| `size` | size | `title` | |
| `color` | color | `text` | |

```yaml
- id: question
  type: text_card
  params: {text: "Over-parameterized?", color: accent}
  duration: 2
```

### `stage`

A cartoon set: a background, a ground line and the video's [characters](#characters-characters)
standing on it. Steps: (1) the set and every character fade in together; later beats hold the
picture while the characters breathe and blink ([idle motion](#idle-motion); `idle: false` keeps
them still in this scene). The background is a picture (`image`, or a
[generated picture](#generated-images-imagegen-vidgen-imagegen) via `generate:`, scaled to fill
the frame and cropped) or, without one, a theme colour or a gradient (`background: [primary,
highlight]` runs from the first colour at the top to the last at the bottom).
[Action targets](#beat-actions): each character and each [prop](#props) by its name (`dim: kit`,
`highlight: tree`), and each part of a character as `<character>.<part>` (`kit.arm_left`, for
[keyframes and paths](#keyframes-and-motion-paths)). A complete example: `examples/cartoon` (two
scenes, two characters, Kokoro voices); how to stage, shoot and time a cartoon: `vidgen guide
cartoons`.

Characters stand on **marks**: `far_left` (x 0.1), `left` (0.25), `centre` (0.5), `right` (0.75),
`far_right` (0.9), the stage's own `marks`, or an x position from 0 (left edge) to 1 (right edge).
Their feet are on the **ground line**, `ground` (a fraction of the frame height) above the bottom
edge. **Depth** moves a character back: at `depth: 1` it stands `0.12` of the frame height higher
and is drawn at 0.55 of its size; characters further back are drawn behind the ones in front
(ties: in list order). A character's size is `size` (a fraction of the frame's shorter side, so it
is the same in 16:9 and 9:16) times its own `scale`. Facing `auto` turns each character towards the
middle, so two characters on either side face each other.

**Layers and the camera.** `layers` add pictures or shapes in front of the background that move
by a **parallax factor** when the camera moves: `1` moves with the stage and its characters, `0`
stays fixed on screen, between them is further away (moves less, and is magnified less in a
zoom), above 1 is nearer (moves more). Each layer has a `place`: `background` and `middle` are
drawn behind the ground band (in that order), `foreground` in front of the characters; default
factors `0.3`, `0.6` and `1.4`. A stage `width` of more than 1 (frame widths) gives the camera
room to pan: marks and x positions are then fractions of the whole stage, the picture or colour
and the ground band cover all of it, and `camera_at` says where the camera looks at the start.
The camera moves with the beat actions [`pan`, `follow` and `zoom`](#beat-actions); the view
never leaves the stage.

| param | type | default | |
|---|---|---|---|
| `image` | str | none | background picture relative to the project folder (png, jpg, svg, ...) |
| `generate` | str \| mapping | none | a generated background instead of `image` (not both): the prompt, or `{prompt, negative, style, aspect, seed, format}`, with the video's [`cartoon_style`](#generated-backgrounds-cartoon_style) added; leave room for the characters (an empty middle, the ground visible) |
| `background` | color \| list of colors | none | without a picture: one colour, or two or more for a gradient from the top down; none: the theme's background |
| `ground` | float 0–0.6 | `0.2` | height of the ground line above the bottom edge, as a fraction of the frame height |
| `ground_color` | color \| `false` | none | fill below the ground line, up to where the deepest character or prop on the ground (no `lift`) stands, so things at a `depth` stand on it; none: `surface` on a colour background, nothing on a picture; `false`: nothing |
| `marks` | mapping | `{}` | own marks, name -> x from 0 to 1 (`{door: 0.85}`); a built-in name moves that mark |
| `characters` | list | `[]` | the characters on the stage: a name, or a mapping (below); each at most once |
| `size` | float | `0.45` (`0.25` on a `level`) | height of a character at depth 0, as a fraction of the frame's shorter side; default from `character_size` |
| `character_size` | `small` \| `medium` \| `large` | none (the video's, else `medium`) | [character size](#character-size-character_size): the default `size` times 0.7, 1 or 1.4 (a level's tiles and props with it); give it or `size`, not both |
| `idle` | bool | `true` | `false`: no breathing, head sway or blinking in this scene (for every character on it) |
| `cartoon_motion` | `lively` \| `calm` \| `none` | none (the video's) | the [animation principles](#animation-principles-cartoon_motion) of the characters in this scene; a character's own setting wins |
| `motion_effects` | bool | none (the video's `motion_effects`: on) | dust, speed lines, impact stars and whoosh arcs in this scene ([motion effects](#motion-effects-motion_effects)); `false`: none |
| `foley` | bool | none (the video's `foley`: on) | sounds for the characters' actions in this scene (footsteps, whoosh, boing, pop; [foley](#foley-and-music-stings)) and its ambience; `false`: none |
| `ambience` | `auto` \| bed \| list of beds \| bool | none (the video's `ambience`: `auto`) | the sound bed under the scene while foley is on: `birdsong`, `city`, `room_tone` or a list of them, for the whole scene; `auto` (or `true`): chosen from the set; `false`: none ([ambience](#ambience-and-door-sounds-ambience-knock)) |
| `auto_direct` | bool \| mapping | none (the video's `auto_direct`: off) | [automatic directing](#automatic-directing-auto_direct) in this scene: `true`, `false` or `{looks, reactions, gestures, closeups, effects}`; a beat's own `auto_direct` wins |
| `reframe` | `speaker` \| `none` | none (the video's, else `speaker` when the characters do not fit in one view) | [vertical cartoons](#vertical-cartoons-reframe): the camera keeps whoever speaks in view on a stage wider than the frame |
| `width` | float 1–4 | `1` | width of the stage in frame widths (16:9 frame widths while it [reframes](#vertical-cartoons-reframe) in a narrower frame); wider than 1: the camera pans across it (`pan`, `follow`) |
| `camera_at` | mark \| x | `centre` | where the camera looks at the start (on a stage wider than the frame); not with a level's `follow` |
| `layers` | list | `[]` | parallax layers (below), in the order given within their place |
| `props` | list | `[]` | [props](#props): a built-in prop's name (`tree`), or a mapping (below) |
| `particles` | list | `[]` | [particles](#particles) over the whole scene, in front of everything: a kind (`snow`), or `{kind, density, area, color, seed, puddles, lightning, settle, settled}`; rain ends on the ground ([Rain on the ground](#rain-on-the-ground)) and with `lightning: true` flashes [lightning](#lightning-and-thunder-lightning), snow with `settle: true` lands and lies there ([Snow that settles](#snow-that-settles-settle)) |
| `light` | `day` \| `morning` \| `sunset` \| `night` \| `indoor` \| `{tint, strength}` | `day` | the [light](#light-and-shadows-light-shadows) on the set: a colour grade of the background, layers, props and characters (never of speech bubbles or text); `night` adds stars; the `light` action changes it during the scene |
| `shadows` | bool | `true` | soft [shadows](#light-and-shadows-light-shadows) on the ground under the characters and the props standing on it; `false`: none |
| `drawing` | mapping | none (the video's `drawing`) | this scene's [drawing style](#drawing-style-drawing): `{outline, shading, texture, seed}`; the keys given win over the video's `drawing` |
| `wind` | number -1..1 \| `calm` \| `breeze` \| `windy` \| `gale` | `0` | [wind](#wind-wind) in gusts: trees, bushes, plants, signs and lamps sway, scarves, long hair, ponytails, braids, floppy or pointy ears, hats and caps trail, particles drift (`0.3` breeze .. `1` gale, blowing right; negative blows left); `0` changes nothing; the `wind` action changes it during the scene; `blow_away` blows a light prop away |
| `water` | `true` \| mapping | none | a strip of [water](#water-and-air-vehicles-water-land) with waves at the front of the stage, for a `boat`: `true` (the whole width) or `{left, right, color}` (`left` / `right`: marks or x from 0 to 1; `color`: a theme token or #hex, default a clear blue); not in a `room` |
| `room` | `true` \| mapping | none | an [indoor set](#rooms-room) instead of the sky and the ground band: a back wall, a floor, a skirting board, an optional ceiling, windows (their sky follows `light`) and doors (door props whose names are marks; `enter` / `exit` through them); not with `image`, `generate`, `background`, `ground_color`, `wind`, `birds`, `fog` or outdoor particles |
| `birds` | `true` \| number \| mapping | none | a [flock of birds](#birds-birds) crossing the sky, flapping: `true`, how many (`6`), or `{count, direction, height, start, seconds, seed}`; not in a `room` |
| `fog` | `true` \| number \| mapping | none | [fog](#fog-fog) in translucent bands lying between the characters and props by depth, thicker further back, drifting: `true` (density 0.5), a density from 0 to 1, or `{density, color, drift, seed}`; not in a `room` |
| `level` | mapping | none | a [platform level](#platform-levels-level) instead of the ground line: `{map, spots, colors, locks, blockers, follow}`; its tiles are the ground, the stage is as wide as its map, the background and layers move behind it by parallax; not with `room`, `water` or `width` |

| key (`characters[]`) | default | |
|---|---|---|
| `name` | required | a character of [`characters:`](#characters-characters) |
| `at` | `centre` | a mark or an x position from 0 to 1 |
| `depth` | `0` | 0 (front, on the ground line) to 1 (back: higher up, smaller, drawn behind) |
| `scale` | `1` | size relative to `size` (e.g. `0.8` for a child), up to 3 |
| `facing` | `auto` | `auto` (towards the middle), `right`, `left` or `front` (at the viewer: its [front view](#walking-in-depth-and-the-front-view); a character drawn from an SVG keeps its side, towards the middle) |
| `pose` | none | the [pose](#poses-and-expressions) it starts in (`waving`, its own `bow`, ...); none: at rest |
| `expression` | none | the [expression](#poses-and-expressions) it starts with (`happy`, ...); none: at rest |

| key (`layers[]`) | default | |
|---|---|---|
| `name` | `<place>_layer` | its name in the layout dump (`middle_layer`, then `middle_layer_2`, ...); each name once |
| `place` | `background` | `background`, `middle` (both behind the ground band) or `foreground` (in front of the characters) |
| `factor` | by `place` | 0–3: how far it moves for a camera move that moves the stage by one; `0.3` / `0.6` / `1.4` |
| `image` | none | a picture file (a PNG with transparency, or an SVG), as wide as the layer needs, its bottom edge at `bottom` |
| `bottom` | `0` | with `image`: height of the picture's bottom edge above the frame's bottom edge (fraction of the frame height) |
| `shapes` | `[]` | instead of `image`: filled shapes `{shape, x, y, width, height, color}` |

A layer has either `image` or `shapes`. A shape is a `rect`, `ellipse` or `triangle` with its
middle at `x` (0–1 of the stage, as seen with the camera at the stage's centre; default `0.5`) and
its bottom at `y` (a fraction of the frame height above the bottom edge, `0`), `width` (`0.3`)
and `height` (`0.2`) as fractions of the frame's shorter side, and `color` (`secondary`); or
`hills`: a row of rounded hills across the whole layer, each `width` wide and `height` high, their
foot at `y`, filled down to the bottom. A layer is drawn larger than the frame, so that no
camera view inside the stage (a zoom up to 8x included) shows its edge.

#### Character size (`character_size`)

How big the characters are, named instead of a number: set it for the whole video (a variant can
change it, e.g. `large` for a 9:16 Short) or per stage scene; the scene's wins, then the video's,
then `medium`. It sets the scene's default `size` (a `size` written in the scene wins over the
video's `character_size`; a scene gives one or the other).

| `character_size` | `size` on a stage | on a level | a 16:9 frame shows (level) | for |
|---|---|---|---|---|
| `small` | `0.315` | `0.175` | about 20 x 11 tiles | cinema: a wide landscape, small characters |
| `medium` (default) | `0.45` | `0.25` | about 14 x 8 tiles (9:16: 8 x 14) | TV and YouTube: as before `character_size` existed |
| `large` | `0.63` | `0.35` | about 10 x 6 tiles (9:16: 6 x 10) | phones and Shorts: big characters, faces easy to read |

- **What scales.** On a stage: the characters and the props (as `size` always did); the stage,
  its marks, the ground line, the background and the layers stay framed as they are, and a walk
  from mark to mark takes as long. On a [platform level](#platform-levels-level) the whole world
  in front scales together: the tiles (a character is two tiles tall), the props, coins and stars;
  the default walking speeds scale with them, so every walk, climb and jump takes as long in
  seconds at every size (its sounds with it), while the level shows more or fewer tiles. The sky,
  the background picture and the parallax layers are the distance: they keep their framing.
- **What does not scale**: captions, on-screen text, speech bubbles, effect symbols over heads
  and overlays keep their size.
- **Shots zoom in from it**: a beat's [`shot:`](#shots-shot) frames characters by their size on
  screen, so a `closeup` of a `large` character zooms in less than one of a `small` character.
- **Lint**: [`small_speaker`](#lint-vidgen-lint) warns when a character speaks with its face smaller
  than `min_face` of the frame's shorter side (a `small` character on a level, a child far
  back): give that beat a `shot: closeup <name>` (or `medium`), or make the characters larger.

```yaml
character_size: medium          # the video (the default)
variants:
  short:
    format: {width: 1080, height: 1920}
    character_size: large       # the 9:16 Short: big characters
scenes:
  - id: valley
    type: stage
    params: {character_size: small, level: {...}}   # this scene: a wide landscape
```

#### Platform levels (`level`)

A side view for platform stories: the ground is a small map of **tiles** written in the YAML,
one line per row, top row first. Symbols: `.` (or a space) air, `#` ground (earth with grass on
top), `=` a floating wooden platform, `~` a cloud to stand on, `|` a ladder, `$` a coin and `*` a
star to pick up ([story props](#story-props-on-a-level-keys-doors-coins-stars-blockers)); a
**letter** marks a **spot**: whatever stands there stands on the first tile below the letter. Short rows are filled
with air on the right; the blank lines around the map are ignored.

```yaml
- id: meadow
  type: stage
  set: park            # the set's sky, hills, light and birdsong; not its props
  params:
    props: [{prop: tree, at: 0.7}]   # the stage's own props stand on the tiles
    level:
      map: |
        ...............~~~~...........
        ..........b...................
        ..a......=====.........c......
        ##########....################
        ##########....################
      spots: {a: start, b: high, c: home}
      colors: {grass: "#6DBE45"}
    characters:
      - {name: pip, at: start}
      - {name: kit, at: high}
```

- **Size.** A tile is half a character of scale 1 (a character is two tiles tall), so the tile
  size follows `size`, which is `0.25` on a level unless the scene gives one or a
  [`character_size`](#character-size-character_size): about 8 rows and 14 columns fill a 16:9
  frame, 14 rows and 8 columns a 9:16 one. The map's bottom row sits on the frame's bottom edge
  (in a portrait frame a short map sits higher, on more ground: [camera](#the-camera-on-a-level-follow));
  the stage is exactly as wide as the map (`width` is not used), and `camera_at`, `pan` and
  `follow` move across it. `vidgen validate` refuses a map narrower than the frame, with the
  number of columns that fit. A map taller than the frame is fine: the camera rises with the
  character it follows.
- **Spots** are marks: `at: start`, `pan: {to: home}`, `walk_to: c`. `spots` names a letter
  (`{a: start}`); a letter without a name is named by itself (`at: b`). Each letter once; a spot
  must have a tile under it. A character or prop `at` a mark or an x instead stands on the
  highest tile in that column (never over a gap). Everything stands at depth 0 on a level:
  scenery behind it goes in `layers`.
- **Behind the level**: the background picture (`image` / `generate`) is drawn larger and moves
  by a parallax factor of `0.2`; a colour or gradient fills the sky; `layers` move by their
  factors as on any stage. There is no ground band (`ground` and `ground_color` are not used):
  a gap shows the sky and the layers.
- **Tiles** are drawn once, when the scene renders, into pictures of 8 columns each (finer than
  the frame, for shots that zoom in), in the cartoon look: the characters' outline ink, grass on
  every open top, wooden planks, puffy clouds. `colors` changes `ground`, `grass`, `platform`,
  `cloud` and `ladder` (theme tokens or #hex). The light grades them like the rest of the set;
  the [drawing style](#drawing-style-drawing)'s outline width applies.
- Errors name the map's row and column, counted from the top left from 1: `level: map row 2,
  column 7: unknown symbol '@'`, `map row 1, column 3: spot 'a' has nothing below it to stand on`.
- **A set** (`set: park`) gives a level its sky, `layers`, light, ambience, particles and marks;
  its props (they stand at depths), its `water` and a room are left out on a level, and the
  stage's own `props` stand on the tiles.
- Not yet: rain, snow and fog on the tiles (they stop at the plain stage's ground line).

##### The camera on a level (`follow`)

`level.follow` names the hero: the camera starts on it and follows it through the whole scene,
side-scrolling across the level.

```yaml
params:
  character_size: large
  level:
    map: |
      ...
    follow: lumo          # a character of the stage
  characters: [{name: lumo, at: start}, {name: tobble, at: home}]
```

- **Gently**: the hero may move a little either side of the view's middle (8 % of its width)
  before the camera moves; then the camera eases after it (about half a second to catch up, no
  jerk when the hero starts, stops or jumps) and never lets it get further than 30 % of the
  width from the middle. At the level's ends the camera stops at the edge: it never shows past
  the map.
- **Up and down**: when the hero climbs or jumps high (a tall level, a high plank, a big jump at
  `large`), the camera rises to keep room over its head (8 % of the view) and comes back down
  when there is room under its feet again; its head never leaves the frame. The camera may rise
  up to a character's height and two tiles over the map's highest tile; it never goes below the
  map's bottom. The sky stays with the camera, the background and the layers move behind by
  parallax.
- **A short map in a portrait frame** (9:16) sits higher, on more ground drawn under the map
  (the bottom row's earth runs on down; a gap goes on down too), so the empty sky over the tiles
  and a character on them is at most 40 % of the frame (raised by at most 30 % of the frame's
  height); the background and the layers rise with it. A landscape frame keeps the map on its
  bottom edge.
- **Beat camera actions still work**: a `shot:` frames its beat (it can frame a hero high up)
  and the next beat gives the camera back to the follow; a written `pan` stops following (the
  camera stays there), a `follow` action follows another character (also gently, on a level);
  an `exit` of the hero stops the camera. `camera_at` is not given with `follow`. While the camera
  follows, `reframe` leaves it alone.
- Without `follow`, the camera stays at `camera_at` (and `reframe` moves it to whoever speaks);
  `- follow: <name>` in a beat starts the same gentle follow from that beat.
- `vidgen lint`'s `off_frame` never reports the level's tiles cut by the frame (the camera crops
  them on purpose).

##### Walking and jumping on a level

On a level the moving actions follow the tiles. The author says where a character goes; vidgen
plans the way (DESIGN.md §86.7) and `vidgen validate` refuses a move that cannot be made, naming
the beat and why.

```yaml
beats:
  - text: "Pip climbs the ladder up to the long plank."
    actions:
      - {walk_to: pip, to: high}                 # a spot: along the tiles, up the ladder on the way
  - text: "Then Pip hops over the gap."
    actions:
      - {jump: pip, to: {column: 15, row: 3}, at: 0.2}   # a tile of the map (from the top left, from 1)
  - text: "And jumps up onto the fluffy cloud!"
    actions:
      - {jump: pip, to: cloud}                   # a spot on the cloud: up through it from below
      - {walk_to: kit, to: 0.8, at: 0.5}         # a mark or an x: any floor in that column it can walk to
```

- **Walking** (`walk_to`, `run_to`, `enter`, `exit`): along the tops of the tiles, stepping up or
  down one tile at a time (a step is eased across the edge of two columns), up and down ladders on
  the way, never across a gap and never off an edge. A character needs room for its height over
  the tiles (two tiles); the shortest way wins. `to` is a spot (its tile), a mark or an x (any
  floor in that column it can walk to). A walk that cannot get there on foot is refused with where
  the way stops: `beat 'hills_b2': 'pip' cannot walk to spot 'home': the way stops at map column
  10: a gap at column 11; jump there instead (- jump: pip, to: home)`. `depth` is refused (a level
  has none). `enter` walks in from beyond the view's edge along the tiles to the character's own
  place (or `to`), `exit` out beyond the edge; when no way on foot leads there, the render stops
  with the side to use instead.
- **Ladders** (`|`) are climbed facing the camera, legs and arms stepping, at half the walking
  pace; a ladder's top is a place to stand, and a ladder ending under a tile (a hatch) climbs
  through onto it.
- **Clouds** (`~`) are one-way: a character stands on top, walks through a cloud at its own height
  and jumps up through it from below, but a jump that falls onto a cloud lands there (an arc that
  would cross a cloud's top on the way down is refused). Ground (`#`) and platforms (`=`) are solid.
- **Jumping** (`jump` with `to`: a spot, a mark or an x, or a tile `{column, row}`): vidgen first
  walks the character to the best take-off point on its own floor (the shortest jump, at least a
  tile across when it can, then the shortest walk), then it crouches, flies an arc that clears the
  tiles (the lowest of a few heights tried, from 0.75 tiles over the higher end), lands, squashes
  and wobbles a little. Slower than a game: about 0.9 s in the air for a small hop, 1.4 s for a
  jump 3 tiles up, up to 2 s for a long drop. At most 5 tiles across, 3 up and 8 down (a character is 2 tiles tall). To a mark or an
  x it lands on the highest floor there that a jump reaches. An impossible jump is refused with
  why, from the nearest take-off: `'kit' cannot jump to spot 'home': from map column 10 it is 11.7
  tiles across, at most 5; walk closer first or put a platform in between`, `... it is 4 tiles up,
  at most 3; add a step or a ladder on the way`, `... the arc hits the tile at map row 2, column
  3 (also on higher arcs)`, `... it would land on the cloud at map row 2, column 6 first`. Without
  `to`, `jump` jumps up where the character stands (`height`), as on any stage; `to` needs a level
  and is given instead of `height`.
- **Timing**: each move starts at its `at` in the beat and takes as long as its way needs: the
  default walking and running speeds scale with the level's smaller characters (at `size: 0.25`
  a walk goes 1.4 units, about 1.4 tiles, a second), a climbed tile counts as two, a jump adds its
  run-up, crouch, flight and landing. A beat too short for its move speeds it up; `vidgen lint`
  warns (`rushed_animation`) when a walk or jump on a level plays more than 1.5 times as fast as
  its own pace: give the beat more narration, start the move earlier, or split the way over two
  beats (a walk to the ladder in one, the climb in the next). The shadow follows the floor under
  the character (none over a gap); `keyframes` `y: 0` is the floor it last walked or jumped to.
- `walk_to` and `run_to` also take a tile `{column, row}` (Step 152), like `jump`.
- `vidgen storyboard` shows each walk and jump half-way; `vidgen direct` (automatic directing)
  knows where a walk or a jump to a spot, a mark or a tile ends; footsteps, the jump's
  boing, dust and impact stars play as on any stage, and a jump lands with a soft thud (see
  [Sounds](#story-props-on-a-level-keys-doors-coins-stars-blockers)).

##### Story props on a level (keys, doors, coins, stars, blockers)

A level's story props have parts in its rules (DESIGN.md §86.8): coins and stars to pick up, doors
that are in the way until they open (a locked one only with its key), and friendly blockers that
are in the way until they step aside. `vidgen validate` replays them with the walks and jumps, in
beat order, and names the beat and what to write when one does not work.

```yaml
- id: meadow
  type: stage
  params:
    background: ["#9FD8F5", "#E6F6FF"]
    props:
      - {prop: door, name: gate, at: gate_spot}     # a closed door: in the way until it opens
      - {prop: key, name: gold_key, at: key_spot}
    level:
      map: |
        ..................................................
        ...............*....................*.............
        ..a...k..$$$.d........$$.....t...............h....
        ##############....################################
        ##############....################################
      spots: {a: start, k: key_spot, d: gate_spot, t: path, h: home}
      locks: {gate: gold_key}       # gate opens only by whoever holds gold_key
      blockers: [tobble]            # tobble is in the way until it steps aside
    characters: [{name: lumo, at: start}, {name: tobble, at: path, facing: left, expression: angry}]
  beats:
    - text: "Lumo spots something shiny in the grass. A key!"
      actions: [{walk_to: lumo, to: key_spot, at: 0.2}]
    - text: "Lumo picks it up and skips along, collecting coins on the way."
      actions:
        - {pick_up: lumo, to: gold_key}
        - {walk_to: lumo, to: {column: 13, row: 4}, at: 0.3, react: {when: pickup, expression: happy, effect: sparkle}}
    - text: "Click! The golden key opens the little gate."
      actions: [{open: gate, by: lumo, at: 0.3}]
    - text: "Then Lumo takes a big jump over the gap and catches a star in the air!"
      actions: [{jump: lumo, to: {column: 19, row: 4}, at: 0.2, react: {when: land, expression: laughing, effect: stars}}]
    - text: "Please, Tobble, may I pass? Tobble smiles and steps aside."
      actions: [{emote: tobble, to: happy, at: 0.5}, {step_aside: tobble, at: 0.7}]
    - text: "And Lumo walks on, home at last."
      actions: [{walk_to: lumo, to: home}]
```

- **Coins and stars** are map symbols (`$` a coin, `*` a star) floating in the middle of their
  cell, bobbing gently (a coin turns too; not with `idle: false` or in a draft). They are named
  `coin_1`, `coin_2`... and `star_1`... in map order (the top row first, left to right; no prop or
  character may take those names). A walk or a jump picks one up when the character's box (two
  tiles tall, 0.8 wide) comes within 0.3 tiles of its middle, on the way or in the air: it pops
  (grows, rises and fades in 0.35 s) on the frame the character gets there. `colors` takes `coin`
  and `star` (default gold and yellow). Letters stay spots: symbols are tiles or items.
- **Doors** are `door` props standing at a spot or an x. On a level every closed door is in the
  way: it shuts its column from its feet up to the tile above it (the sky: all the way up), so no
  walk or jump passes it. `- open: gate` opens it (`by: lumo`: lumo turns to it and reaches for
  its edge); `close` puts it back in the way. A door in `locks` (`{door: key}`) is **locked**: it
  opens only `by` a character who holds the key prop then (picked up, held or given to it) and
  stands within 1.6 tiles of it on its floor. Refusals: `beat 'meadow_b1': 'lumo' cannot walk to
  spot 'home': the locked door 'gate' is in the way at map column 14; open it first with its key
  'gold_key' (- open: gate, by: <who holds gold_key>)`, `the door 'gate' is locked: say who opens
  it with its key`, `'lumo' cannot open the door 'gate': it is locked and 'lumo' does not hold its
  key 'gold_key'; pick it up first (- pick_up: lumo, to: gold_key)`, `'lumo' is too far from the
  door 'gate' to open it (3.0 tiles; at most 1.6); walk_to next to it first`. The key stays in the
  hand afterwards.
- **The key** is the built-in `key` prop (0.3 of a character tall, gold; held by its bow), or any
  other prop named in `locks`.
- **Blockers** (`blockers: [tobble]`) are characters of the stage in the way like a closed door
  (any character: a grumpy snail, a sleepy fox). `- step_aside: tobble` moves one out of the way
  after the line that asks it nicely: it steps back off the path (a little smaller, its feet 0.3
  tiles higher, drawn behind the others, 1 s), or with `to:` (a spot, a mark, an x or a tile)
  walks there along the tiles. From then on it is not in the way. Refused while it is: `'tobble' is
  in the way at map column 30; ask it to move first (- step_aside: tobble)`.
- **Reactions** during or after a move: `react: {when, expression, effect}` on `walk_to`,
  `run_to` and `jump` (with `to`) on a level. `when: pickup` starts it as the character picks up
  the first coin or star on the way, `land` as a jump lands (the default for a jump), `arrive` as
  it stops (the default for a walk; for a jump once its landing wobble is over). The face eases to
  the `expression` in 0.3 s and keeps it (like `emote`); the `effect` symbol (`sparkle`, `stars`,
  `hearts`, `exclaim`...: the [effect](#effect-symbols-effect) symbols) pops over its head for
  1.4 s. Lip sync goes on while it reacts. A reaction after the move is also a plain `emote`,
  `react` or `effect` action at a later `at` (it waits for the move to end). `vidgen validate`
  refuses `when: pickup` on a move that picks up nothing and `when: land` on a walk.
- **Sounds** ([foley](#foley-and-music-stings), Step 153), each on the frame its event happens
  (also when a short beat speeds the move up): a jump takes off with a `boing` (after its crouch)
  and lands with a soft, short `thud` and a footstep (a little louder after a long drop); each coin
  plays a `coin` "pling-ling" (each further coin of the same walk or jump a semitone higher, up to
  5), each star a `twinkle`, on the way or in the air; `open` of a locked door `by` its key's
  holder clicks the key (`unlock`), then the door creaks (0.3 s later; any other door just creaks,
  `close` creaks and thuds shut); `step_aside` plays a soft low `swoosh` and slow, heavy
  footsteps. Walks on a level have their footsteps as anywhere. The times come from the rules'
  plan (where on its way a move picks a coin up, when its flight ends), so they are known before
  any frame is drawn and listed in `timings.json` `sfx` like every sound. `foley: false` (the
  video's, or a stage's) turns them off with the other foley; `sfx: {gain}` sets their level;
  `assets/sfx/coin.wav` (or `twinkle`, `unlock`, `thud`...) replaces one with your own. A move's
  `react` effect symbol plays no sound (an `effect` action's does).

#### Rooms (`room`)

`room:` turns a stage into an indoor set: a **back wall** (a colour and a wallpaper), a **floor**
in front of it (a colour and boards or tiles drawn in perspective), a **skirting board** where
they meet and an optional **ceiling** band, all drawn from simple shapes and filling the whole
stage (a wide stage too). `room: true` is a room with the defaults. The wall stands at a
**depth** like the characters and props: the floor reaches back to where a thing at that depth
stands (default `0.4`, or further back when something on the floor stands deeper), so everything
on the floor stands in front of the wall. Characters, props, depth, shots, `reframe`, shadows and
the camera work as on any stage; `sets:` can hold a room (a scene giving a room drops its set's
`image` / `generate` / `background` / `ground_color`; one giving one of those drops the set's room;
a set's room and the scene's merge key by key).

- **Windows** hang on the wall and show the sky outside, with its stars: its colours follow the
  stage's `light` (`day` blue, `morning` peach low in the sky, `sunset` blue over orange, `night`
  dark blue with stars, `indoor` evening blue with a few stars: lamplight inside means evening
  outside; a `{tint, strength}` light tints the day's sky) and fade with the `light` action. The
  sky is not graded by the light inside (the room is); frames, sills and curtains are.
- **Doors** are `door` props standing at the wall, drawn closed or open; each door's name
  (default `door`, then `door_2`...) is a target (`- open: door`, `- close: door`, `lean_on`) and
  a **mark** (`walk_to: pip, to: door`; the names may not be marks already). `enter` with
  `door: <name>` brings a character in through it: the door opens (at once, if closed), the
  character fades in in the doorway over 0.35 s and walks to its mark; `exit` with `door:` walks
  it to the door, where it fades out, and then waits off stage. Doors cast no shadows.
- **Indoors there is no weather**: `wind`, the `wind` action, `birds`, `fog`, `rainbow`, a
  `light` action's `move_sun` and `rain`, `snow`, `leaves` and `streaks` particles are refused
  (`vidgen validate`); sparkles, dust, confetti, smoke and bubbles work. The windows show no fog;
  the `lightning` action flashes them (and the room a little), without a bolt.
- **Furniture** is built-in [props](#props): `sofa`, `armchair`, `bed`, `bookshelf`, `counter` (a
  kitchen counter), `fridge`, `picture`, `rug`, `houseplant`, `clock`, `tv` (on a low cabinet),
  `desk` (with its chair) and `fireplace` (a brick fireplace with a mantelpiece and logs), drawn as
  seen from the front of the room (a bed and a desk side on, along the wall). A prop with **`against: wall`** stands with its back to the wall, at the
  wall's depth (its own `depth` when it gives one); such props do not push the wall back. A
  `picture` and a `clock` **hang on the wall** (0.5 and 0.85 of a character's height above the
  floor) and take the wall's depth without `against`. Characters sit on a `sofa` or a `bed` (two
  side by side: each `sit_on` takes the free place nearer to the character), an `armchair` or at
  a `desk` (facing the desk), and lean on a `counter`, `fridge` or `bookshelf`
  ([Sitting and leaning](#sitting-and-leaning)); every seat is at the height of a `chair`'s, so the
  hips rest on it. To sit on furniture against the wall, a character stands at the wall's depth
  too (`depth: 0.4` by default; moving in depth comes later). Furniture casts shadows like any
  prop; a `rug` (lying flat, at the depth of the characters standing on it) and the props on the
  wall cast none.

![The furniture in the default theme](gallery/media/furniture.png)

| key (`room`) | default | |
|---|---|---|
| `wall` | `#E9DCC9` | the wall's colour (a theme token or `#hex`) |
| `wallpaper` | `plain` | `plain`, `stripes` or `dots` (a shade of the wall's colour) |
| `floor` | `#C9A27A` | the floor's colour |
| `flooring` | `boards` | `boards` (rows of boards, joints staggered), `tiles` (rows and lines spreading towards the front) or `plain` |
| `skirting` | the floor's, darker | the skirting board's colour |
| `ceiling` | `false` | a band at the top: `true` (the wall's colour, lighter) or a colour |
| `depth` | `0.4` or deeper | how far back the wall stands (0–1); a character or prop on the floor deeper than a given `depth` is a config error |
| `windows` | `[]` | a mark or an x, or `{at, width, height, sill, frame, curtains}` (below) |
| `doors` | `[]` | a mark or an x, or `{name, at, open, facing, scale, color, detail}` (below) |

| key (`windows[]`) | default | |
|---|---|---|
| `at` | `centre` | its middle: a mark or an x from 0 to 1 of the stage |
| `width` / `height` | `0.6` / `0.62` | in the heights of a character standing at the wall |
| `sill` | `0.42` | how high its bottom is above the floor, in those heights |
| `frame` | `#F4F6FA` | colour of the frame, bars and sill |
| `curtains` | `true` | curtains on both sides: `true` (`accent`), a colour, or `false` |

| key (`doors[]`) | default | |
|---|---|---|
| `name` | `door` | its name (a target and a mark), numbered from the second on |
| `at` | `right` | a mark or an x from 0 to 1 of the stage |
| `open` | `false` | `true`: it starts open |
| `facing` | `right` | its hinges: `right` swings the open door to the left; `left` mirrors it |
| `scale` | `1.3` | its height in the heights of a character standing at the wall |
| `color` / `detail` | `accent` / `highlight` | the door's and its knob's colours |

```yaml
- id: kitchen
  type: stage
  params:
    light: indoor                       # lamplight inside; the windows show the evening sky
    room: {wallpaper: stripes, flooring: boards, windows: [0.3], doors: [{at: 0.8}]}
    characters: [{name: pip, at: left}, {name: kit, at: 0.6}]
    props: [{prop: table, at: 0.45, depth: 0.2}]
  beats:
    - text: "Then Kit comes in."
      actions:
        - {enter: kit, door: door}      # kit waits off stage until now
    - text: "And Pip goes out for the night."
      actions:
        - {exit: pip, door: door}       # the door stays open (- close: door shuts it)
        - {light: night, at: 0.5}       # the windows' sky fades to night, stars come out
- id: living_room
  type: stage
  params:
    room: {wallpaper: stripes, windows: [0.5], doors: [0.94]}
    props:
      - {prop: bookshelf, at: 0.06, against: wall}
      - {prop: sofa, at: 0.3, against: wall}
      - {prop: picture, at: 0.3}        # hangs on the wall above the sofa
      - {prop: counter, at: 0.75, against: wall}
      - {prop: rug, at: 0.45, depth: 0.15}
    characters:                         # at the wall's depth (0.4), to sit on the sofa
      - {name: pip, at: 0.2, depth: 0.4}
      - {name: kit, at: 0.42, depth: 0.4}
  beats:
    - text: "They sit down together."
      actions:
        - {sit_on: pip, to: sofa}       # the place nearer to pip
        - {sit_on: kit, to: sofa}       # the other place
```

##### Clocks, televisions and lamps (`time`, `on`, `switch_on`)

Three props move by themselves (outdoors too):

- A **`clock` runs** when it has a `time` (what it shows at the scene's start, `H:MM` or
  `H:MM:SS`; default the drawn `10:10`) or a `speed` (clock seconds per second: `1` real time, the
  default; `60` a minute a second; up to `3600`). Its hands turn from the scene's clock, clockwise
  also when the clock faces left; up to `speed: 10` a red second hand sweeps round too. A clock
  without either stays as drawn.
- A **`tv` that is on** shows a simple picture (a sky, a ground and two shapes) that changes about every
  1.8 s and flickers about 12 times a second, with a faint cool glow on the wall around it.
- A **`lamp` that is on** lights its lantern and lays a soft warm glow around it. The glow is drawn
  right behind the lamp, so it brightens the wall, the floor and whatever stands behind the lamp;
  characters and props in front of it are not brightened, and the room's `light` stays as set
  (`light: night` with a lamp on is a dark room with one warm spot; there is no light falloff
  across the room).

`on: true` starts a `tv` or a `lamp` switched on; `- switch_on: <prop>` and `- switch_off: <prop>`
switch it at `at` of the beat (at once, with a `click` while `foley` is on). The lit screen, the
lantern and the glows are never graded by the stage's light, so they shine at night. Other props
take no `on`, `time` or `speed` (a config error) except a [`fireplace` or a
`kettle`](#fireplaces-and-kettles-on-switch_on) and a ringing [`phone`](#everyday-small-props-let_go-pour),
and the actions refuse them ("'sofa' cannot be switched on or off (props that can: fireplace,
kettle, lamp, phone, tv)").

Render cost: only the moving parts leave Manim's static picture of the set (the hands; the
picture and the glow of a tv; a lamp's lantern and glow only in the animation where it is
switched), together with whatever is drawn over them; the rest of the room is drawn once per
animation as before. A clock, tv or lamp that never runs or comes on is drawn exactly as before.

```yaml
- id: late_night
  type: stage
  params:
    light: night
    room: {wallpaper: dots, windows: [0.42]}
    props:
      - {prop: clock, at: 0.42, time: "23:55", speed: 60}   # midnight in five seconds
      - {prop: tv, at: 0.8, against: wall}
      - {prop: lamp, at: 0.6, depth: 0.25, scale: 0.6, on: true}
    characters: [{name: pip, at: 0.3}]
  beats:
    - text: "Then Pip turned on the television."
      actions: [{switch_on: tv, at: 0.4}, {switch_off: lamp, at: 0.8}]
```

##### Fireplaces and kettles (`on`, `switch_on`)

Two more props move by themselves while they are on (`on: true`, or `- switch_on: fireplace` /
`- switch_off: kettle` at `at` of a beat):

- A **`fireplace` that burns** (furniture: 0.75 of a character tall, `against: wall` in a room)
  shows flames behind its front logs: five orange tongues and three yellow ones, each flickering
  in height and wavering at its tip (seeded: the same in every render, another fireplace burns
  differently), with a warm orange glow round the fire that flickers with them, drawn right behind
  the fireplace. The flames and the glow shine at night (never graded by the light). With foley a
  fire **crackles**: a generated crackle bed (a soft roar, small crackles and a few pops; a seamless
  8 s loop at −34 LUFS, 2 dB under the rain bed, ducking under the narration like it) plays while
  the fireplace burns in the scene, fading in over 0.6 s and out over 0.8 s, and lighting it
  plays a short `burner` whoosh (it goes out silently). On a stage with `wind` (a fireplace
  outdoors) the flames lean with the gusts.
- A **`kettle` that is on** (0.15 of a character; put it on a `counter` with a `lift`, as for any
  prop on furniture) puffs steam from its spout: soft white puffs that rise about two kettle
  heights, grow, sway and fade, drifting with the wind outdoors. The steam is drawn right in front
  of the kettle and graded by the light like the set; switching it plays a `click`.

```yaml
- id: cold_evening
  type: stage
  params:
    light: night
    room: {windows: [0.15]}
    props:
      - {prop: fireplace, at: 0.45, against: wall}
      - {prop: counter, at: 0.82, against: wall}
      - {prop: kettle, at: 0.8, depth: 0.4, lift: 0.17}   # on the counter
    characters: [{name: pip, at: 0.62, depth: 0.15}]
  beats:
    - text: "Pip lit a fire and put the kettle on."
      actions: [{switch_on: fireplace, at: 0.3}, {switch_on: kettle, at: 0.8}]
```

Render cost: as for a tv, the flames, the glow and the steam leave Manim's static picture while
they burn or steam, with what is drawn over them. Measured on the room above at 854×480, 260
frames: 16 415 Cairo draws and 6.6–7.1 s with both off, 31 846 draws and 10.4–11.4 s with both
on all along (the large translucent glow costs the most).

#### Fruit falling from a tree (`fruit`, `drop_fruit`)

A `tree` with **`fruit: true`** carries four fruits (red, drawn on its crown; they sway with it
in the wind). **`- drop_fruit: tree`** lets one fall: faster and faster, it hits the ground under
the tree with a `thud` (foley), bounces once and lies there (speed lines follow it while
`motion_effects` are on). With **`to: <character>`** it falls on that character's head (the fruit
hanging above the head nearest it), bounces off to the side and lands beside the character, and
**stars** circle the head for 1.6 s (the `stars` [effect symbol](#effect-symbols-effect)). The
character must stand under the tree (nothing checks it: a fruit far from the head drifts sideways
as it falls); when no fruit hangs above the head, the fruit falls to the ground instead. A tree
has 4 fruits: `vidgen validate` reports a fifth `drop_fruit` of it, a tree without `fruit` and a
target that is not a tree. A fallen fruit is not a prop (no target, not in the layout dump).

```yaml
- id: orchard
  type: stage
  params:
    props: [{prop: tree, at: 0.3, fruit: true}]
    characters: [{name: pip, at: 0.32}]
  beats:
    - text: "An apple fell, and then another one right on Pip's head."
      actions: [{drop_fruit: tree, at: 0.2}, {drop_fruit: tree, to: pip, at: 0.6}]
```

#### Birds (`birds`)

**`birds:`** sends a flock across the sky, from beyond one edge of the stage to beyond the other:
a loose V of small dark birds, each beating its wings at its own rate (3–4.2 times a second) and
gliding now and then, the flock bobbing a little (seeded: every render the same). `birds: true`
is five birds; a number is how many (1–20); a mapping sets `count`, `direction` (`right` or
`left`), `height` (0.5–0.97: how high, as a fraction of the frame height above its bottom edge;
default 0.8), `start` (seconds into the scene; default 0.5), `seconds` (how long the crossing
takes; default about 5 s per frame width) and `seed`. The **`birds` action** sends one from `at`
of a beat (`- birds: 4`, `{birds: 3, direction: left, height: 0.9}`; the same keys but `start`).
Birds fly behind the layers, the ground, the props and the characters (right after the sky), are
graded by the light, and stay outdoors (a `room` refuses them). Only the birds and what is drawn
over them leave Manim's static picture while they fly (a stage of 162 frames: 16 910 draws
without birds, 17 990 with six).

```yaml
- id: evening_sky
  type: stage
  params:
    birds: {count: 6, direction: left, start: 1}
    characters: [pip]
  beats:
    - text: "Later, more birds flew home."
      actions: [{birds: 3, at: 0.5}]
```

#### Generated backgrounds (`cartoon_style`)

A stage's `generate:` makes its background with [`vidgen imagegen`](#generated-images-imagegen-vidgen-imagegen).
The top-level **`cartoon_style`** gives every stage of the video the same look: its words are
added to the style words of each stage's `generate:` prompt (after `imagegen.style` or the
`generate.style`, also when that style is `none`). Only `stage` scenes get them: an
[`image`](#image) scene's picture, and its cache key, stay as they are.

```yaml
cartoon_style: "flat colours, thick outlines, soft shadows"
imagegen: {negative: "people, animals, text"}
variants:
  sketch: {cartoon_style: "pencil sketch, light watercolour wash"}   # its own set of pictures
scenes:
  - id: park
    type: stage
    params:
      generate: "a sunny park seen from the side, a path running across the lower third, trees at both edges, open grass in the middle"
      characters: [pip, kit]
    beats: [{text: "Pip and Kit meet in the park."}]
# sent: "a sunny park seen from the side, ... open grass in the middle. Style: flat colours,
#        thick outlines, soft shadows. Avoid: people, animals, text."
```

The words are part of the prompt sent, so they are part of the picture's cache key: changing
`cartoon_style` (or a variant that sets another one) asks for new pictures (`vidgen imagegen
--dry-run` lists them and their cost); the old ones are reported as unused, never deleted.

**Writing a background prompt that leaves room for the characters.** The characters stand on
the ground line in front of the picture, so describe a set, not a scene:

- **An empty middle**: put the interesting things at the edges ("trees at both edges", "a
  house on the left") and keep the middle plain ("open grass in the middle", "an empty
  street"), where the characters stand on `left`, `centre` and `right`.
- **The ground visible**: a side view at eye level with a floor or ground across the lower
  part ("seen from the side", "a path running across the lower third"), so feet stand on
  something; set `ground` to where that ground is in the picture.
- **No people, animals or text**: add them to `negative` (or `imagegen.negative`): a
  generated figure competes with your characters, and generators draw words poorly.
- **Calm detail behind the characters**: few small details, soft contrast; a busy picture
  hides the outlines of the characters (`cartoon_style` words like "simple shapes, soft
  shadows" help).
- **Wide stages**: on a stage wider than the frame (`width: 2`) the picture is enlarged to cover
  the whole stage, so its top and bottom are cut off; keep the ground and the things that matter
  near the middle of its height, and describe the set from left to right.

#### Props

`props` put things on the stage: a built-in prop drawn from simple shapes in the theme's colours,
or an SVG file of your own. A prop stands on a mark or x position like a character, at a `depth`
(further back: higher up, smaller, drawn behind), and sorts with the characters by depth; at the
same depth a character is drawn in front of a prop. Its size follows the stage's `size`: each
prop has a usual height next to a character (a `tree` is 1.7 characters tall, a `table` 0.42, a
`cup` 0.09, an SVG prop 0.5), times its own `scale`. `cloud`, `sun` and `moon` hang in the sky
(`lift: 0.5`); `picture`, `clock` and `blackboard` hang on a wall; other props stand on the ground unless given
a `lift`. The furniture for [rooms](#rooms-room) has a gallery of its own there.

![Every built-in prop in the default theme](gallery/media/props.png)

The outdoor props of the [ready-made sets](#ready-made-sets-set-city_street): a `shop` front (1.7
characters tall, a little wider than tall), a `bench` (0.32; seats two), a `bus_stop` (1.35), a `fountain`
(0.75), `flowers` (0.28, a bed of five; they sway in the wind), a `fence` (0.42), a
`beach_umbrella` (1.3; keeps the rain off), a `shell` (0.06), a `pine` (1.9; sways, keeps the rain
off), `mushroom`s (0.13) and a `log` (0.16; seats two). A `road` (0.12) and a `path` (0.08) lie
flat like a `rug`: bands about 10 and 6 characters long, wide enough for a stage one frame wide;
put one at a `depth` between the characters and what stands behind it.

![The outdoor props in the default theme](gallery/media/outdoor_props.png)

The indoor props of the [ready-made rooms](#ready-made-rooms-set-classroom), besides the
furniture: a `blackboard` (0.5 characters tall, twice as wide; it hangs on a wall like a
`picture`, its bottom 0.42 of a character above the floor), a `school_desk` (0.4, side on with its
chair, like a `desk`: a character sits on the chair facing the desk), a `shelf_with_goods` (0.95,
three shelves of boxes, tins and jars; lean on its sides), a `till` (0.26; put it on a `counter`
with a `lift`) and a `wardrobe` (1.1; lean on its sides).

![The indoor props in the default theme](gallery/media/indoor_props.png)

| key (`props[]`) | default | |
|---|---|---|
| `prop` | — | a built-in prop: `table chair tree bush house door lamp sign box ball cloud sun moon rock plant laptop cup basket umbrella napkin kettle`; [small things](#everyday-small-props-let_go-pour): `cake muffin book phone letter gift balloons vase watering_can`; [furniture](#rooms-room): `sofa armchair bed bookshelf counter fridge picture rug houseplant clock tv desk fireplace`; [outdoors](#ready-made-sets-set-city_street): `shop bench bus_stop road path fountain flowers fence beach_umbrella shell pine mushroom log`; [indoors](#ready-made-rooms-set-classroom): `blackboard school_desk shelf_with_goods till wardrobe`; [on a level](#story-props-on-a-level-keys-doors-coins-stars-blockers): `key`; [vehicles](#vehicles-get_in-ride_to-get_out): `bicycle car bus`, [on water and in the air](#water-and-air-vehicles-water-land): `boat hot_air_balloon toy_rocket` |
| `svg` | — | instead of `prop`: an SVG file relative to the project folder (sanitised like every SVG: no scripts, filters, embedded pictures or text), standing on the bottom edge of its `viewBox` |
| `name` | the prop's name | its name for actions and the layout dump; an SVG's default is its file name (`assets/old_well.svg` -> `old_well`); repeats are numbered (`tree`, `tree_2`) |
| `at` | `centre` | a mark or an x position from 0 to 1 of the stage |
| `depth` | `0` | 0 (front, on the ground line) to 1 (back) |
| `scale` | `1` | size relative to the prop's usual size, up to 5 |
| `lift` | `0.5` for `cloud`, `sun`, `moon`; else `0` | height above the ground line, as a fraction of the frame height |
| `facing` | `right` | `left` mirrors it |
| `color` | per prop | its main colour (a theme token or `#hex`): a tree's leaves (`tertiary`), a chair (`accent`)... |
| `detail` | per prop | its second colour: a tree's trunk, a house's roof, a laptop's screen... |
| `recolor` | `none` | `svg` only: `theme` maps the picture's colours to the nearest theme colours |
| `open` | `false` | `umbrella`, `door`, `book`, `letter` or `gift` only: `true` starts it open ([Umbrellas](#umbrellas-open-and-close), [rooms](#rooms-room), [small props](#everyday-small-props-let_go-pour)) |
| `against` | none | `wall`: in a [room](#rooms-room), it stands with its back to the wall at the wall's depth (unless `depth` is given); a `picture` or `clock` in a room does so without it |
| `on` | `false` | `tv`, `lamp`, `fireplace`, `kettle` or `phone` only: `true` starts it switched on (a phone: ringing). vidgen also takes a bare `on: true`, which YAML 1.1 tools read as a key `true`; write `"on": true` where a YAML 1.1 tool or a JSON Schema check reads the file ([Clocks, televisions and lamps](#clocks-televisions-and-lamps-time-on-switch_on), [fireplaces and kettles](#fireplaces-and-kettles-on-switch_on), [small props](#everyday-small-props-let_go-pour)) |
| `time` | none | `clock` only: the time it shows at the scene's start, `H:MM` or `H:MM:SS` (`"21:45"`); with `time` or `speed` the clock runs |
| `speed` | `1` | `clock` only: how fast it runs, clock seconds per second (`1` real time, `60` a minute a second, up to `3600`) |
| `fruit` | `false` | `tree` only: `true` hangs four fruits on it ([`drop_fruit`](#fruit-falling-from-a-tree-fruit-drop_fruit) lets one fall) |

A picnic set: a `basket` (0.2 of a character, held by its handle), a `napkin` (small: 0.05, a
checked cloth lying flat) and an `umbrella` (0.6), drawn closed or open.

```yaml
      props:
        - tree                                   # a built-in prop at centre
        - {prop: house, at: far_left, depth: 0.8}
        - {prop: table, at: left, color: tertiary}
        - sun                                    # hangs in the sky
        - {svg: assets/old_well.svg, at: far_right, scale: 1.5, recolor: theme}
```

`vidgen validate` reports an unknown character, mark, pose or expression (with the known names),
a missing `image` file (also a layer's) or `svg` file of a prop, a character placed twice, a layer
or prop name used twice (or a prop named like a character), and `image` with `generate` or with
`background`. The layout dump and `vidgen lint` see each character as one object of kind
`character` named after it, each prop as one object of kind `prop` named after it, the picture or
colour as `background`, the band as `ground`, each layer by its name and each particle field as
one object of kind `particles` named after its kind. Characters speak and act through beat
actions ([Speaking and acting](#speaking-and-acting)), walk, enter, leave, gesture and jump
through others ([Moving](#moving)), pick up, carry, put down, hand over and throw props
([Props in hands](#props-in-hands)), and sit on a `chair`, `rock`, `box`, `sofa`, `armchair`,
`bed`, `desk`, `bench` or `log` and lean on a `tree`, `door`, `sign`, `lamp`, `house`, `bookshelf`,
`counter`, `fridge`, `pine`, `bus_stop` or `shop` ([Sitting and leaning](#sitting-and-leaning); an SVG prop gives `data-seat` /
`data-lean`), and get in a `car` or a `bus` or on a `bicycle` and ride it
([Vehicles](#vehicles-get_in-ride_to-get_out)).

```yaml
characters:
  - {name: pip, look: {body: bean, hair: short}}
  - {name: kit, look: {body: tall, hair: spiky}, poses: {bow: {body: {angle: -15}}}}
scenes:
  - id: park
    type: stage
    params:
      generate: "a sunny park, an empty lawn in the middle, flat colours"
      ground: 0.18
      marks: {bench: 0.62}
      characters:
        - {name: pip, at: left, pose: waving, expression: happy}
        - {name: kit, at: bench, depth: 0.5, pose: bow}
    beats:
      - text: "Pip spots an old friend by the bench."
```

#### Speaking and acting

**Who speaks.** A beat is said by its voice (the beat's `voice`, else the scene's, else the base
voice `default`; see [Multiple voices](#multiple-voices-voices)). On a `stage`, the characters whose `voice` is that voice
speak it: their mouths follow the beat's [viseme track](#lip-sync) from the beat's start to its
end. A character without a `voice` never speaks; a beat in the narrator's voice moves no mouth
unless a character has `voice: default`. A `say` action in the beat picks who speaks instead
(also a character whose voice is not the beat's: its mouth follows the beat's audio). When two
characters share a voice, both speak its beats unless a `say` picks one (`vidgen validate`
warns).

The mouth is timed from the beat's start (the scene's clock), so it stays in step with the audio
while the character changes pose; during other animations of the character (a fade, a `dim`) it
holds and then catches up.

**Acting actions** change a character during a beat; all take characters as targets (`- emote:
kit`), and several may share a beat (each waits for the one before on the same character):

| action | options | |
|---|---|---|
| `say` | `bubble` (`false`; `true`: the beat's text, or a short text), `color` (`#FFFFFF`), `size` (`caption`) | the character speaks this beat; `bubble` draws a speech bubble above its head (where there is room, clear of text and other characters) with a tail towards it. Both last until the next beat starts (`until: <beat>`: until that beat starts). |
| `look_at` | `to` (required: a character or prop of the scene, a mark, an x 0–1, or `camera`) | turns towards it and tilts the head up or down (at most 20°; facing the front only the eyes move up or down); `camera` turns the eyes to the viewer. Stays so. |
| `turn` | `to` (`left` \| `right` \| `front`; default: the other way, from the front the side it faced before) | faces the other way (a mirror at half time), or turns between its side and the viewer ([front view](#walking-in-depth-and-the-front-view)): it narrows as it turns, swapping its shapes half-way, and faces the viewer with the head straight. Stays so. |
| `emote` | `to` (required: an expression) | changes the expression (eyes, brows, mouth ease one after another). Stays so. |
| `pose` | `to` (required: a pose) | takes the pose (body, legs, arms, head ease one after another). Stays so. |
| `react` | `expression` and / or `pose` | a listener's reaction for this beat: undone when the next beat starts. |

`look_at`, `turn`, `emote` and `pose` last; `until: <beat>` puts back what they changed when that
beat starts (other changes made since stay). `vidgen validate` reports an unknown character,
pose or expression (with the known names, the character's own included), a `say` by a character
without a `voice`, a `look_at` place that is neither a target, a mark nor `camera`, and an acting
action on a prop; it warns when a character lacks the parts an action needs (a `say` without a
mouth, a `look_at` without a head, an `emote` without eyes, brows or mouth): the action does
nothing for that character. `vidgen lint` checks the beat ends of a stage: a speaker facing
away from the character it last looked at (or the nearest one; `facing_away`), a speaker whose
face something in front of it hides (`hidden_speaker`), a speech bubble over a face or another
bubble (`bubble_overlap`), a mouth moving while no narration is heard (`mouth_without_voice`),
characters standing on each other (`character_overlap`) and a character cut by the view's edge
(`off_stage`); see [lint](#lint-vidgen-lint).

```yaml
voices:
  pip_voice: {voice_id: VOICE_ID_1}
  kit_voice: {voice_id: VOICE_ID_2}
characters:
  - {name: pip, voice: pip_voice, look: {body: bean}}
  - {name: kit, voice: kit_voice, look: {body: tall, hair: spiky}}
scenes:
  - id: park
    type: stage
    params:
      characters: [{name: pip, at: left}, {name: kit, at: right}]
    beats:
      - text: "Hello! Have you seen my kite?"
        voice: pip_voice                        # pip speaks
        actions:
          - {react: kit, expression: surprised} # kit listens, surprised, for this beat
      - text: "It is up in the tree."
        voice: kit_voice
        actions:
          - {say: kit, bubble: "Up there!"}     # kit speaks, with a short bubble
          - {look_at: kit, to: tree, at: 0.3}
          - {emote: pip, to: worried, at: 0.5}
```

#### Effect symbols (`effect`)

`- effect: pip` with `to: idea` puts a small symbol over a character's head so a feeling reads at a
glance. Each is an original shape drawn from circles and polygons in a theme colour with the
characters' ink outline:

| `to` | the symbol | where | colour |
|---|---|---|---|
| `sweat` | a drop sliding down | at the back of the head | `primary` |
| `anger` | four curved ticks in a cross, pulsing | on the head's top front corner | `accent` |
| `idea` | a light bulb with pulsing rays | above the head | `highlight` |
| `question` | a rocking question mark | above the head | `secondary` |
| `exclaim` | an exclamation mark that shakes and calms | above the head | `accent` |
| `sleep` | three Zs rising one after another | in front of the head | `primary` |
| `hearts` | three bobbing hearts | above the head | `accent` |
| `stars` | three stars circling the head | round the top of the head | `highlight` |
| `sparkle` | two twinkling four-pointed stars | in front of the head | `highlight` |
| `tear` | a drop running down from the eye, again and again | under the eye | `primary` |

Options: `color` (a theme token or hex instead of the symbol's own) and `sound` (`true`; `false`:
silent even with [foley](#foley-and-music-stings)). The symbol pops in with a little bounce (an
eased grow with `cartoon_motion: none`), follows the head on every frame (walks, jumps, turns,
shots; a hat lifts the symbols that sit above it), keeps moving, and shrinks away when the next
beat starts (`until: <beat>`: when that beat starts; `run_time` 0.4 is the pop). It is sized by the
head (a bigger or nearer character, a bigger symbol), drawn in front of the set and the
characters, and never graded by the [light](#light-and-shadows-light-shadows) (like speech
bubbles). Placed while a speech bubble is on screen, a symbol that would sit under the bubble moves
to the front of the head, else behind it; a bubble drawn later keeps clear of the symbols. With
foley on, most symbols make a short sound as they pop up (built-in sounds: `idea` a short `chime`
ding, `exclaim` / `question` / `hearts` / `sweat` a `pop` at different pitches, `anger` a soft
`thud`, `sparkle` a high `chime`; `sleep`, `stars` and `tear` are silent). The layout dump records
each as an object of kind `effect` with `effect` (the symbol) and `effect_of` (the character);
`bubble_overlap` reports a speech bubble over a symbol, and a symbol never counts as hiding a
speaker's face (`hidden_speaker`). [`auto_direct`](#automatic-directing-auto_direct) adds one for
a strong change of expression, and a [screenplay](#cartoons-from-a-screenplay-vidgen-screenplay)
direction such as `[Pip has an idea]` writes one.

```yaml
beats:
  - text: "Wait. I know how to get it down!"
    voice: pip_voice
    actions:
      - {effect: pip, to: idea, at: 0.2}          # a bulb over pip, until the next beat
      - {effect: kit, to: question, sound: false} # a silent question mark over kit
```

#### Moving

Seven more actions move the characters of a `stage`; like the acting actions they take characters
as targets and the new state as an option:

| action | options | |
|---|---|---|
| `walk_to` | `to` (a mark or an x 0–1 of the stage, or `{mark, depth}`; on a level also a tile `{column, row}`), `depth` (0 front .. 1 back; default: its depth now), `speed` (`2.5`); `to` or `depth`; on a level `react` | walks along the ground to that place (and depth: [walking in depth](#walking-in-depth-and-the-front-view)), facing the way it goes, legs, arms and body moving in step; it speeds up, walks at `speed` units per second (the frame's shorter side is 8 units; a character is about 3.6 tall at `size: 0.45`) and slows down. It takes as long as the distance needs: about 3.3 s from `left` to `right` of a 16:9 stage (7.1 units), plus the wind-up and settle of [`cartoon_motion`](#animation-principles-cartoon_motion). Stays there. On a [platform level](#walking-and-jumping-on-a-level) it walks along the tiles, steps and ladders (the default speed scaled with `size`), picks up the coins and stars it touches and cannot pass a closed door or a blocker; `react: {when, expression, effect}` reacts on a pickup or as it stops ([story props](#story-props-on-a-level-keys-doors-coins-stars-blockers)). |
| `run_to` | `to`, `depth`, `react` (as `walk_to`), `speed` (`6`) | runs there: a `walk_to` at running speed with steps 1.6 times as long, legs and arms swinging 1.5 times as far, knees and elbows bending more and the body leaning forward 12° at full speed (also with `cartoon_motion: none`). About 1.4 s from `left` to `right` of a 16:9 stage, plus the wind-up and settle. Footsteps follow the longer strides; with [motion effects](#motion-effects-motion_effects) dust puffs up where it sets off and stops and speed lines trail it. |
| `enter` | `side` (`left` \| `right`; default: the edge nearer where it goes), `door` (instead of `side`: a [room](#rooms-room)'s door by name), `to` (a mark or x; default its own `at`), `speed` | walks in from just beyond that edge of what the camera shows, or through the door (it opens; the character fades in in the doorway over 0.35 s, with what it holds). A character with an `enter` action waits off stage (beyond the stage's edge) from the start of the scene until then. |
| `exit` | `to` (`left` \| `right`; default: the nearer edge), `door` (instead of `to`: a room's door by name), `speed` | walks out beyond that edge of what the camera shows, or to the door (it opens) where it fades out over 0.35 s with what it holds, then waits off stage (an `enter` brings it back). A camera `follow`ing it stops (and stays). |
| `gesture` | `to` (required: `point`, `wave`, `shrug`, `nod`, `shake_head`), `big` (`false`) | `big: true`: a sweeping gesture, a whoosh arc trailing the hand of a `point`, `wave` or `shrug` ([motion effects](#motion-effects-motion_effects)). The gesture, then back to its pose: `point` raises the near arm forward, `wave` raises it and waves three times, `shrug` raises both arms, `nod` dips the head twice, `shake_head` moves the head (and eyes) side to side twice. 1.2 s (`point`), 1.6 (`wave`), 1.0 (`shrug`), 0.9 (`nod`), 1.1 (`shake_head`). |
| `jump` | `height` (`0.4`: its own heights, up to 2); on a [platform level](#walking-and-jumping-on-a-level) `to` (a spot, a mark or an x, or a tile `{column, row}`) instead | jumps up and lands where it stood (0.6 s in the air; with `cartoon_motion` a crouch before and a squash after, [below](#animation-principles-cartoon_motion)). With `to` on a level: walks to the take-off point, jumps a planned arc there and lands with a squash and a wobble, picking up the coins and stars it touches on the way and in the air; `react: {when, expression, effect}` reacts on a pickup, as it lands (default) or once it stands still. |
| `step_aside` | `to` (a spot, a mark, an x or a tile; default: a step back off the path), `speed` | on a [platform level](#story-props-on-a-level-keys-doors-coins-stars-blockers), one of its `blockers` moves out of the way: back off the path (smaller, behind the others; 1 s) or along the tiles to `to`. |

A walk's time comes from its distance and `speed`; `run_time:` sets the time instead (and so the
speed). An action never makes its beat longer: a walk longer than the time left in the beat is
sped up (and logged). Look where it goes with `follow` in the same beat and `at`: the camera
catches up with the walking character and then follows it (the two play together). A speech
bubble moves with its character. Lip sync stays in step during a walk, gesture or jump.

`vidgen validate` reports an unknown mark, gesture or edge, and a moving action on a prop; it
warns when a character lacks the parts a gesture needs (`point` / `wave`: an arm; `shrug`: both
arms; `nod` / `shake_head`: a head). `vidgen lint` reports a walk that ends on another character
(`walk_overlap`): pick another mark, or move the other character first. `vidgen storyboard` shows
each walk, entrance, exit, gesture and jump (and `keyframes` / `move_along`, and the [prop actions](#props-in-hands) but `hold`) half-way as well as
at the beat's end ([mid-action stills](#frame-stills-vidgen-render---frames)). Walks, entrances,
exits and jumps make their own sounds ([foley](#foley-and-music-stings)).

```yaml
scenes:
  - id: park
    type: stage
    params:
      characters: [{name: pip, at: left}, {name: kit, at: right}]
    beats:
      - text: "Pip strolls over to the tree."
        actions:
          - {follow: pip, at: 0.2}
          - {walk_to: pip, to: centre, at: 0.2}
      - text: "Then Kit arrives, waving."
        actions:
          - {enter: kit, side: right}           # waits off stage until now; walks to its mark
          - {gesture: kit, to: wave, at: 0.6}
      - text: "Pip jumps for joy, and Kit leaves."
        actions:
          - {jump: pip}
          - {exit: kit, to: right, at: 0.4}
```

#### Walking in depth and the front view

`walk_to` and `run_to` also walk towards or away from the camera: `depth` (or `to: {mark,
depth}`) is where the character ends up, from `0` (the front: the ground line, full size) to
`1` (the back: higher up, 0.55 of the size), like a stage character's own `depth`. x and depth
change together in a straight line on the ground; the character grows or shrinks as it goes
(its outlines and whatever it holds with it), its shadow follows it on the ground, and it passes
behind or in front of the characters and props it walks by at the moment its depth passes theirs
(at the same depth a character stands in front of a prop). Walking from depth 0 to 1 is as far as
walking two of its heights across the stage, so it takes about as long. Walking only in depth
it keeps its facing (a side view walks on the spot as it grows or shrinks; facing `front` it
steps towards the camera, a leg lifting with each step); with an x it faces the way it goes. In
a [room](#rooms-room) a walk may not go behind the wall (`vidgen validate`).

`facing: front` (a stage character's start, or `turn: <name>, to: front`) shows a generated
character's **front view**: the same parts and shapes seen from the front, the face in the
middle of the head with the pupils looking ahead, a symmetric nose, hair and body, both arms
beside the body and in front of it (glasses get a temple on each side). Poses, expressions,
gestures, lip sync, blinking, looks, wind and effect symbols work in it; a turn between the side
and the front narrows the figure towards the middle of the turn and swaps the shapes there, then
widens it again (0.4 s). `look_at` something beside it turns it to its side; `look_at: camera`
keeps the front. Sitting, leaning, crouching (to pick up or put down something low) and walks
across are drawn from the side: they turn it to its side.
A character drawn from an [SVG file](#characters-from-svg-files) has no front view: it keeps
its side (`vidgen validate` warns).

`vidgen validate` reports a `sit_on`, `lean_on`, `pick_up` or `give` across depths (further
apart than 0.05): the character must first walk to the prop's or the other character's depth,
with the `walk_to` that does it:

```
scenes[0].beats[1].actions[0].to: dot stands at depth 0 and 'sofa' at depth 0.4; walk_to first (- walk_to: dot, to: {mark: 0.42, depth: 0.4})
```

A prop put down or thrown lands at its holder's depth. The [layout dump](#layout-dump-buildlayoutscenejson)
gives each character away from the front its `depth`; `vidgen lint`'s `character_overlap` and
`walk_overlap` leave out two characters 0.15 or more apart in depth (one stands behind the
other; `hidden_speaker` still reports a speaker hidden that way).

```yaml
scenes:
  - id: den
    type: stage
    params:
      room: {wallpaper: stripes, depth: 0.4}
      props: [{prop: sofa, at: centre, against: wall}]
      characters: [{name: dot, at: left}, {name: moss, at: right, depth: 0.3, facing: front}]
    beats:
      - text: "Dot walks back to the sofa, past Moss."
        actions:
          - {walk_to: dot, to: {mark: 0.45, depth: 0.4}}
      - text: "She sits down, and Moss steps towards us to tell us why."
        actions:
          - {sit_on: dot, to: sofa}
          - {walk_to: moss, depth: 0, at: 0.3}
```

#### Props in hands

Five actions let the characters of a `stage` handle its [props](#props). The character is the
target; `to` names the prop, the place or the other character:

| action | options | |
|---|---|---|
| `pick_up` | `to` (required: a prop of the stage), `hand` (`left` \| `right`; default: a free one, the near `left` first) | the arm bends and reaches for the prop (crouching for a low one), then lifts it and holds it in front of the character (the hand in front of the shoulder, the elbow bent). 1.2 s. The character must stand next to the prop (within 0.75 of its heights). |
| `hold` | `to` (required: a prop), `hand` | the character holds the prop from now on without picking it up: the prop moves into its hand as the arm comes up (0.4 s); for a prop it has from the start (`at: 0` of the scene's first beat); a character that waits off stage for its `enter` has the prop with it there, unseen. |
| `put_down` | `to` (a mark or an x 0–1; default: just in front of it), `prop` (which one, when it holds two) | reaches down (crouching) and puts the prop on the ground there, at the character's depth and at its full size; the arm goes back to how it was. 1.0 s. The spot must be within 0.75 of its heights. |
| `give` | `to` (required: another character on the stage), `prop`, `hand` (the receiver's) | both turn to face each other and reach to the point between their hands; the prop goes from one hand to the other. 1.2 s. They must stand next to each other (within 1.2 of the giver's heights). |
| `throw` | `to` (required: a mark or an x 0–1), `prop`, `height` (`0.5`: of the thrower's heights, 0.05–3), `spin` (`1`: whole turns, 0–6) | turns that way, winds the arm up and swings; the prop flies an arc `height` above the higher end, spinning, and lands upright on the ground there (at the thrower's depth, at its full size) with a `thud`. 0.5 s plus 0.45–1.6 s of flight, by the distance. |

A held prop goes along with its hand: walks, jumps, turns, gestures and poses of its holder move it
too. It is drawn right in front of its holder (behind characters standing in front of it). A
prop taller than 0.4 of its holder is made smaller while it is held and gets its size back when it
is put down or lands. A character holds at most one prop per hand; with two, `put_down`, `give`
and `throw` need `prop:`. The layout dump records `held_by` and `hand` on a held prop and
`holding` on its holder; with [`auto_direct`](#automatic-directing-auto_direct) a speaker never
gets an arm gesture (`point`, `wave`, `shrug`) with a hand that holds something. When the
hand cannot reach a low prop (or the spot to put it down) from where the character stands, it
crouches: the knees bend, the body lowers (at most 0.6 of its hips' height) and bends forward a
little, the feet stay where they are, and it rises again with the prop. A character with its
legs in one piece (an SVG `legs`) shortens them instead; one that sits or leans does not
crouch. A prop still lower than the crouching hand rises into it.

`vidgen validate` plays the scene's actions in order and reports an unknown prop or character, a
prop someone else holds (`give` it instead), a full hand, nothing to put down, give or throw, and
a prop, spot or character too far away, with the `walk_to` that fixes it:

```text
scenes[0].beats[0].actions[0].to: pip is 1.0 of its heights from 'ball' (it reaches 0.75); walk_to first (- walk_to: pip, to: 0.40)
```

```yaml
scenes:
  - id: park
    type: stage
    params:
      characters: [{name: pip, at: left}, {name: kit, at: right}]
      props: [{prop: ball, at: 0.5}]
    beats:
      - text: "Pip picks up the ball and takes it to Kit."
        actions:
          - {walk_to: pip, to: 0.42}
          - {pick_up: pip, to: ball, at: 0.2}
          - {walk_to: pip, to: 0.62, at: 0.5}    # the ball goes along
      - text: "Kit takes it and throws it far away."
        actions:
          - {give: pip, to: kit}
          - {throw: kit, to: far_left, spin: 2, at: 0.4}
```

A `basket` hangs from its handle in the hand; other props are held by their middle.

##### Umbrellas: open and close

An `umbrella` prop is drawn closed, or open with `open: true` in `props`. Two actions change it;
the prop is the target:

| action | options | |
|---|---|---|
| `open` | `by` (a character who opens it: it reaches for it; on a level it must stand next to a door, and hold the key of a locked one) | the umbrella opens half-way through (0.6 s). Held, it goes up overhead: the holder's arm comes up and the hand holds the shaft in front of the chest, the canopy above the head (0.85 of the holder's height tall in the hand, not the 0.4 limit above), the shaft drawn behind the head. Standing, it opens where it stands. |
| `close` | — | the umbrella closes (0.6 s). Held, it comes back to the hold point in front of the holder, at most 0.4 of its height; standing, it closes where it stands. |

An open umbrella stays open when it is picked up, held, given (the receiver holds it overhead),
put down (it stands on its hook) or thrown. `vidgen validate` reports `open` / `close` on a prop
that cannot open (`'tree' cannot open (props that can: book, door, gift, letter, umbrella)`) or on a character. The layout
dump records `shape` (`closed` or `open`) on a prop that opens. A `door` prop opens and closes the same way (half-way through, where it stands): the doorway dark, the leaf swung towards the viewer on its hinge side.

```yaml
scenes:
  - id: picnic
    type: stage
    params:
      characters: [{name: pip, at: left}]
      props: [{prop: umbrella, at: 0.3}, basket]
    beats:
      - text: "It starts to rain."
        actions:
          - {hold: pip, to: umbrella}
          - {open: umbrella, at: 0.4}      # up over pip's head
      - text: "The sun is back."
        actions:
          - {close: umbrella}
```

##### Everyday small props (`let_go`, `pour`)

Nine small things to hold, give, put down and set on a table (`lift`, as for any prop on
furniture), drawn from simple shapes in the theme's colours:

![The small props in the default theme](gallery/media/small_props.png)

| prop | usual height | |
|---|---|---|
| `cake` | 0.22 | two tiers on a plate, icing dripping, three candles alight |
| `muffin` | 0.08 | a domed top over a ridged paper case |
| `book` | 0.13 | closed (upright, its cover to the viewer) or open (both pages spread); `open` / `close` |
| `phone` | 0.13 | a mobile phone; `on: true` or `- switch_on: phone` makes it **ring** (below) |
| `letter` | 0.08 | closed (a sealed envelope) or open (the sheet unfolded, written on); `open` / `close` |
| `gift` | 0.2 | closed (wrapped, a bow on the lid) or open (the lid leaning on it, sparkles rising); `open` / `close` |
| `balloons` | 1.1 | three balloons on strings tied to a small weight; `let_go` floats them away |
| `vase` | 0.32 | a vase with three flowers |
| `watering_can` | 0.22 | held by its handle; `pour` waters |

- A **book, a letter or a gift** opens and closes like an umbrella (`- open: gift`, `open: true`
  in `props`), standing or in a hand; held open, it stays in front of its holder (only an open
  umbrella goes overhead).
- A **phone that is on rings**: from when it comes on, a burst of rings every 2 s, each 1 s long,
  in which the phone shakes (13 times a second, up to 10° either way), amber ring lines show on
  both sides and its screen lights up (it shines at night). It rings in a hand too. With foley each
  burst plays the built-in `phone` sound (a soft electronic trill, −6 dB). `- switch_off: phone`
  (answering it) stops it with a `click`.
- **Balloons** are held by their strings at their full size (not made smaller like other held
  props), rising behind the holder's head. **`- let_go: <character>`** opens the hand: the arm
  comes down and the balloons float up out of the frame, speeding up, swaying and drifting with the
  stage's wind (gone for the scene: `vidgen validate` reports a later use). The action takes 1–6 s,
  by how far they rise. `let_go` is for props that float (balloons); `put_down` the others. Put
  down, balloons stand on their weight.
- A **watering can** pours with **`- pour: <character>`** (2 s): the can it holds tilts forward
  at the hand, water drops leave the spout and fall to the ground in front of it, and it comes back
  up. `pour` needs a held prop that pours (a `watering_can`). A can held by a character facing the
  other way from its spout (held props are not mirrored with their holder) is turned round in the
  hand as the pour starts, so it always pours ahead of its holder.
- `letter` and `balloons` are light enough for [`blow_away`](#props-that-blow-away-blow_away).

| action | options | |
|---|---|---|
| `let_go` | `prop` (which one, when it holds two) | the character lets go of the balloons it holds: they float up and away. |
| `pour` | `prop` | the character tilts the watering can it holds and water pours out. |

```yaml
scenes:
  - id: party
    type: stage
    params:
      props:
        - {prop: table, at: 0.5}
        - {prop: cake, at: 0.5, lift: 0.17}       # on the table
        - {prop: phone, at: 0.58, lift: 0.17}
        - {prop: balloons, at: 0.25}
        - {prop: gift, at: 0.7}
      characters: [{name: pip, at: 0.25}, {name: kit, at: 0.75}]
    beats:
      - text: "The phone rings, and Pip lets the balloons go."
        actions:
          - {hold: pip, to: balloons, at: 0}
          - {switch_on: phone, at: 0.2}
          - {let_go: pip, at: 0.5}
      - text: "Kit opens the present."
        actions:
          - {pick_up: kit, to: gift}
          - {open: gift, at: 0.5}
          - {switch_off: phone, at: 0.8}
```

#### Sitting and leaning

Three actions let a `stage`'s characters sit on its [props](#props) and lean on them. The
character is the target; `to` names the prop:

| action | options | |
|---|---|---|
| `sit_on` | `to` (required: a prop with a seat: `chair`, `rock`, `box`, `sofa`, `armchair`, `bed`, `desk`, `bench`, `log`, `school_desk`, or an SVG prop with `data-seat`) | the character moves onto the seat, its body lowers until its hips are on the seat line and its hips and knees bend: the feet on the ground in front (the built-in seats are lower than any generated character's hips), or hanging when an SVG prop's seat is higher than its legs are long (legs in one piece turn forward to the ground, or stick out). On a `chair` or at a `desk` or `school_desk` it faces the way the prop faces (its back to the chair's back); on the others it keeps its facing. 1.0 s. It must stand next to the prop (within 0.75 of its heights). One character per seat; a `sofa`, a `bed`, a `bench` and a `log` seat two side by side (each takes the free place nearer to it). |
| `lean_on` | `to` (required: a prop with lean edges: `tree`, `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter`, `fridge`, `pine`, `bus_stop`, `shop`, `shelf_with_goods`, `wardrobe`, or an SVG prop with `data-lean`) | the character turns its back to the prop (on the side of it where it stands), steps against its edge (the trunk, the door's frame, the sign's board, the lamp's or bus stop's post, the wall, the furniture's side) and leans back 12°, the feet forward on the ground. 0.8 s. It must stand within 1.0 of its heights of the prop. Several characters may lean on one prop. |
| `stand_up` | none | the character stands up from where it sits or leans, over its feet: its body and legs go back to how they were before. 0.8 s. |

While a character sits or leans it keeps its place and its facing: it cannot `walk_to`, `exit`,
`jump`, `turn`, `keyframes` or `move_along` (as a whole) before a `stand_up`, a `look_at` turns
only its head (a look behind it is not turned round to), a `pose` or `react` moves only its arms
and head, and `give` / `throw` do not turn it. It can still speak, gesture, emote and pick up,
put down, give and throw props (without a crouch). A prop someone sits or leans on cannot be
picked up or moved by `keyframes` / `move_along` until they stand up. The layout dump records
`sitting_on` or `leaning_on` (the prop's name) on the character; with
[`auto_direct`](#automatic-directing-auto_direct) a seated or leaning listener is not given a look
at a speaker behind it, and no close-up is added in a beat with `sit_on`, `lean_on` or
`stand_up`.

`vidgen validate` plays the scene's actions in order (with the props in hands) and reports a prop
without a seat or lean edges, a seat already taken (a sofa full), a prop someone holds, a prop too far away
(with the `walk_to` that fixes it), a `stand_up` with nothing to stand up from, and a walk, jump,
turn or keyed move of a character that sits or leans:

```text
scenes[0].beats[1].actions[1].target: pip sits on 'chair' then; stand_up first (- stand_up: pip)
```

An SVG prop gives its seat and lean edges on its `<svg>` element, in `viewBox` coordinates like
a character's `data-pivot`: `data-seat="x y"` is the middle of its seat line, `data-lean="left
right"` the x of the two edges a character leans its back on. Both are mirrored with the prop
(`facing: left`).

```yaml
scenes:
  - id: porch
    type: stage
    params:
      characters: [{name: pip, at: left}, {name: kit, at: right}]
      props: [{prop: chair, at: 0.3}, {prop: tree, at: 0.85}]
    beats:
      - text: "Pip sits down on the chair, and Kit leans on the tree."
        actions:
          - {sit_on: pip, to: chair}
          - {walk_to: kit, to: 0.78}
          - {lean_on: kit, to: tree, at: 0.6}
      - text: "Time to go."
        actions:
          - {stand_up: [pip, kit]}
          - {walk_to: pip, to: centre, at: 0.4}
```

#### Vehicles (`get_in`, `ride_to`, `get_out`)

Three built-in [props](#props) are vehicles: a `bicycle` (0.38 of a character tall; one rider),
a `car` (1.12 tall, 1.9 long; two riders, front and back) and a `bus` (1.45 tall, 3.2 long; a
driver and three passengers), drawn side on from simple shapes in the theme's colours, the front
on the right (`facing: left` mirrors them). They are large next to the characters, as real ones
are: give a bus a `scale` below 1, or the stage a smaller `size`, when it must fit the frame.

![The vehicles in the default theme](gallery/media/vehicles.png)

| action | target | options | |
|---|---|---|---|
| `get_in` | characters | `to` (required: a vehicle of the stage) | each character takes the free seat nearest to it and sits down: in a car or a bus it goes behind the side (which hides its legs; its head shows in a window), on a bicycle it sits on the saddle, its feet on the pedals and its hands on the handlebar. 1.0 s. It must stand next to the vehicle (within 0.5 of its heights of either end) at its depth. A full vehicle takes no more. |
| `ride_to` | vehicles, or characters that ride one (their vehicle) | `to` (a mark, an x, or `{mark, depth}`), `depth`, `speed` (units per second; default: a bicycle and a bus 4, a car 5, a boat 2.5, a balloon 1.2, a toy rocket 6), `land` (a balloon or a toy rocket: `false` flies it away, see [below](#water-and-air-vehicles-water-land)) | the vehicle rides there with everyone in it: it turns to face the way it goes (at once), speeds up, goes, slows down and stops, its wheels turning; a bicycle's rider pedals. With a depth it rides towards or away from the camera, growing or shrinking with its riders and passing in front of or behind the others. As long as the distance needs (`run_time` sets it). |
| `get_out` | characters | none | each rider gets out where the vehicle is now: it stands up beside its seat, in front of the vehicle, its body, legs and arms as they were before it got in. 0.9 s. |

While a character rides it keeps its seat and its facing (the vehicle's): it cannot `walk_to`,
`run_to`, `enter`, `exit`, `jump`, `turn`, `sit_on`, `lean_on`, `keyframes` or `move_along`
before a `get_out` (nor `stand_up`), a `look_at` turns only its head, a `pose` or `react` moves
only its arms and head. It can still speak (its mouth shows in the window), gesture and emote. A
rider is not added to its vehicle: it follows its seat on every frame. A vehicle cannot be picked
up, and while someone rides it `keyframes` / `move_along` cannot move it. Its shadow lies under it
(a rider casts none of its own); a ride raises dust where it sets off and stops and leaves speed
lines when it goes fast ([motion effects](#motion-effects-motion_effects)); a bicycle rings its
`bell` as it sets off, a car or a bus starts its `engine`, and each `brakes` as it stops
([foley](#foley-and-music-stings)). A `follow` of the vehicle or of a rider keeps the camera on it;
with [`reframe`](#vertical-cartoons-reframe) and [`auto_direct`](#automatic-directing-auto_direct)
the riders are where their vehicle took them. The layout dump records `riding` (the vehicle's
name) on a rider; `vidgen lint` does not report two riders of one vehicle as standing on each
other, nor a rider's face as hidden by its own vehicle.

`vidgen validate` plays the scene's actions in order and reports a `to` that is not a vehicle of
the stage (with the stage's vehicles), a full vehicle, a rider too far from it or at another depth
(with the `walk_to` that fixes it), a `ride_to` of a character that rides nothing, a `get_out`
without a `get_in`, a walk (or any action above) of a character that rides, and a vehicle picked
up:

```text
scenes[1].beats[0].actions[0].to: pip is 0.9 of its heights beyond the end of 'bus' (it gets in from at most 0.5); walk_to first (- walk_to: pip, to: 0.50)
```

```yaml
scenes:
  - id: street
    type: stage
    params:
      props: [{prop: car, at: 0.35}, {prop: bicycle, at: 0.8}]
      characters: [{name: pip, at: 0.3}, {name: kit, at: 0.4}, {name: moss, at: 0.85}]
    beats:
      - text: "Pip and Kit get in the car; Moss gets on her bicycle."
        actions:
          - {get_in: [pip, kit], to: car}
          - {get_in: moss, to: bicycle}
      - text: "Off they go."
        actions:
          - {ride_to: car, to: {mark: 0.7, depth: 0.4}}
          - {ride_to: moss, to: 0.15, speed: 3}
      - text: "Everyone out!"
        actions:
          - {get_out: [pip, kit, moss]}
```

#### Water and air vehicles (`water`, `land`)

Three more vehicles go outdoors only (a `room` refuses them): a `boat` (0.58 of a character tall,
1.9 long, an outboard motor at the back; two riders sitting behind its side), a
`hot_air_balloon` (2.1 tall; two riders standing in its basket, which hides their legs) and a
`toy_rocket` (0.55 tall; a toy: nobody rides it, and `get_in` to it is refused). They are in the
[vehicles gallery](gallery/media/vehicles.png) above, with the rocket's parachute open.

- **The boat** floats on the stage's `water`: a strip of water at the front, from the bottom of
  the frame up to a little above the ground line, between `left` and `right` (`water: true` is
  the whole width). Waves drift along its front edge (with the wind's way when the stage's `wind`
  blows left) and the boat bobs and rocks on them all the time, its riders with it. The front of
  the water is drawn in front of the boat, over its keel, so it sits in the water. The boat must
  stand on the water (its `at` between `left` and `right`; keep its ends over it too) at depth 0;
  `ride_to` takes it along the water like a car along the road (default speed 2.5), and
  `vidgen validate` refuses a `to` off the water. Its motor runs (an `engine`, higher), no
  brakes, no dust, and it casts no shadow.
- **The balloon** rises about 0.3 of the frame's height above where it set off (less when its top
  would leave the frame; at least 0.12) over the first 30 % of the flight, floats gently along,
  and comes down over the last 30 % to land at `to`. The stage's wind when it sets off blows it
  aside on the way (up to 1.2 character heights at a gale, most half-way); it still lands at
  `to`. Its `burner` roars as it rises, and its basket lands with a soft thud. At 2.1 characters
  tall it needs a small stage `size` (about 0.3) to fit the frame.
- **The toy rocket** launches with a burst of smoke on the ground and a trail of puffs behind it,
  shooting up an arc (about 0.45 of the frame's height, its nose along the way), and at the top its
  parachute pops open: it turns upright and floats down to `to`, swaying less and less, and lands
  softly (`launch`, a `pop`, a soft thud). The smoke is a [motion effect](#motion-effects-motion_effects)
  (`motion_effects: false` turns it off).

`land: false` on a `ride_to` flies a balloon or a toy rocket up out of the top of the frame
(heading for `to`'s x): it and its riders are gone for the scene, and `vidgen validate` reports a
later action on them. Only vehicles on the ground ride in depth (`depth` is refused for the
others), and `land: false` is refused for the others.

```yaml
scenes:
  - id: lake
    type: stage
    params:
      water: {left: 0.35, right: 1.0}
      props: [{prop: boat, at: 0.6}, {prop: toy_rocket, at: 0.12, name: rocket}]
      characters: [{name: pip, at: 0.25}, {name: kit, at: 0.3}]
    beats:
      - text: "Pip and Kit climb into the little boat."
        actions:
          - {get_in: [pip, kit], to: boat}
      - text: "They motor across the lake, and a toy rocket shoots over them."
        actions:
          - {ride_to: boat, to: 0.8}
          - {ride_to: rocket, to: 0.3, land: false}
```

#### Shots (`shot:`)

A beat's `shot` frames characters of a `stage` for that beat: the camera cuts to the framing as
the beat starts and holds it to the beat's end; the next beat without a `shot` cuts back to the
view before the shots (a run of beats with shots goes from one framing to the next). The framing
is computed from where the characters stand when the beat starts (no rendering involved: the
same maths runs in `vidgen direct`); the camera does not follow them during the shot (a walk can
leave it; lint `off_stage` says so).

| shot | names | frames |
|---|---|---|
| `wide` | none | every character on the stage, no zoom (the middle of them on a wide stage) |
| `two_shot` | none, one or two | two characters, whole, with a margin; default: the beat's speaker and the character nearest it (one name: that one and the nearest) |
| `medium` | one | the character from about the hips up, with more room on the side it faces |
| `over_shoulder` | one, optionally the near one | the character seen past the *near* one (default: the one it last looked at, else the nearest), who stands at the other edge, cut by the frame. The nearer they stand, the tighter the shot (at most a close-up) |
| `closeup` | one | its head and shoulders, with more room on the side it faces |

`shot: closeup kit` (the kind, then the names) or `shot: {kind: closeup, of: kit, move: true,
run_time: 1.2}`: `move: true` eases to the framing (1.0 s, or `run_time`) instead of cutting, and
eases back after the beat. A `pan` or `follow` during a shot ends it (the camera stays where they
take it). Shots are views of the stage: parallax layers move and particles stay screen-sized as
for any camera move, and a speech bubble is placed and sized for the shot's view. Storyboard
stills (the beat's end and half-way through its moves) show the shot. The layout dump records
`shot: {kind, subjects, near}` on the frames in a shot, and lint `off_stage` then checks only the
characters the shot frames (the near character of an over-the-shoulder shot may be cut).
`vidgen validate` reports a shot naming no character or the wrong number of them, a prop or
unknown name, and a shot on a scene that is not a `stage`. A shot zooms in from the scene's
[`character_size`](#character-size-character_size): the framing is the same on screen, so a
close-up of `large` characters zooms in less than one of `small` ones. On a platform level a
shot can frame a character high above the frame's resting view, and the next beat gives the
camera back to a [`follow`](#the-camera-on-a-level-follow).
In a portrait (9:16) frame a `closeup` is never narrower than 0.55 of the character's height
and a `medium` (and `over_shoulder`) than 0.7 (Step 155: framed by height alone, a portrait
close-up cut a snout or a beak off the face), so it shows a little more of the figure.

```yaml
beats:
  - text: "Is that a kite in the tree?"
    voice: pip_voice
    shot: over_shoulder pip kit      # pip seen past kit's shoulder
  - text: "A very flat bird."
    voice: kit_voice
    shot: closeup kit
  - text: "They looked at each other."  # no shot: back to the view before the shots
```

#### Vertical cartoons (`reframe`)

A cartoon written for 16:9 also renders in a 9:16 [variant](#variants): with `reframe: speaker`
the camera keeps whoever speaks in view. In a frame narrower than 16:9 (9:16, 1:1) the stage is
then laid out as wide as the 16:9 frame of the same short side, so the characters keep their
places and sizes and the narrow frame crops the landscape stage (`width: 2` is two 16:9 frames).
Without `reframe` (top level, or a stage's param; the stage's wins) a stage reframes when its
characters, where they start, do not fit in one view; otherwise it is laid out in the frame as
before. `reframe: none` keeps the frame-wide layout and moves the camera only with the beats'
own `pan`, `follow`, `zoom` and `shot`.

How the camera moves (`vidgen direct` shows the moves, the storyboard lists them under `auto:`):

- It moves only for a speaker that is not wholly in view, at the start of the beat: it eases
  (1.0 s `pan`) to a view with the speaker in it, a little room on the side it faces, and no other
  character cut by the frame's edge (lint `off_stage`). A speaker who walks during its line is
  framed with both ends of the walk when they fit.
- A short reply (a line under 1.5 s) does not move it: the reply is heard over the view of the
  line before.
- Before the first line, the first beat cuts to the scene's first speaker (the set fades in on
  it). A beat whose `say` draws a speech bubble cuts instead of easing, so the bubble is placed
  for the speaker's view.
- A beat with a written `pan`, `follow`, `zoom` or `shot` is left alone; after a `follow` the
  camera is the followed one's until a written `pan` places it again, and after a `zoom` or
  `shot` it is back where reframing left it. [Automatic directing](#automatic-directing-auto_direct)
  sees these pans as camera moves (no automatic close-up in a beat with one).

```yaml
variants:
  vertical:                                  # vidgen render --variant vertical
    output: box_kite_vertical
    format: {width: 1080, height: 1920, fps: 30}
    preview: {width: 270, height: 480, fps: 15}
    # reframe: none                          # keep the whole stage squeezed into the frame instead
```

#### Automatic directing (`auto_direct`)

With `auto_direct: true` (top level, a stage's param or a beat's key; the nearest one wins; off
by default) vidgen adds acting actions to a stage's beats so a dialogue looks directed without
writing each look (a [host](#a-host-beside-any-scene-host) beside other scene types directs
itself too: [automatic host directing](#automatic-host-directing)):

- **Looks.** When a character speaks (the beat's `voice`, or its `say`), the other characters on
  the stage `look_at` it, and it looks at the one it talks to: the last other character who
  spoke, else the one it talked to before, else the next one who will speak, else the only other
  character on the stage. A look a character already has is not added again. Characters an
  `enter` brings in are not on the stage before it, nor after their `exit`.
- **Reactions.** After a line with a `?` the listeners `react` with `thinking` or `surprised`;
  with a negation (`no`, `not`, `never`, `don't`, `can't`...) `worried` or `sad`; with a `!`
  `surprised` or `happy` (checked in that order; a plain statement gets none). The reaction starts
  at `at: 0.95`, so it plays in the pause after the line (`narration.pad`), and goes at the next
  beat. Which of the two is picked is fixed per scene, beat and character (renders repeat), and a
  character never gets the same automatic reaction twice in a row. A surprised face pops
  ([foley](#foley-and-music-stings)).
- **Actions written in a beat always win.** A character that one of the beat's own actions acts
  on gets no automatic action in that beat; `say`, `zoom`, `pan`, `follow`, a shot, `highlight`,
  `dim` and `callout` only frame or voice it and do not count. In a beat with a written shot the
  lint check below looks at the shot's view. After its own `turn`, walk, `pose` or
  `emote`, a character is given a look again the next time it listens or speaks.
- **Gestures.** A speaker makes one `gesture` per line at most, held on the line's stressed
  word: the first `*word*`, else the first word in capitals (`NEVER`, two letters or more), else
  the longest word of six letters or more, the last only when the speaker did not gesture in its
  previous line. The word picks the gesture: a negation shakes the head, `yes` / `right` / `sure`
  nod, `hello` / `bye` wave, `this` / `that` / `there` / `you` point; else a question shrugs, a
  negation in the line shakes the head, and otherwise `point`, `nod` or `shrug` (fixed per scene,
  beat and speaker, the speaker's last one tried last). The word times come from the beat's
  alignment, else the estimate (as captions use them); a line too short for the gesture gets
  none. The asterisks of `*word*` (one word or a few, `*not now*`) are taken out of the beat's
  text when the config is read: the TTS, captions, subtitles, speech bubbles, `vidgen readback`
  and lint see `word`; only the planner sees the mark. `2*3*4`, `a * b` and `**bold**` are left
  as written.
- **Close-ups.** A line of at most 5 words right after a beat of at least 8 gets a close-up of
  its speaker: a `zoom` (`scale: 2`) that moves in and back in 0.5 s each when both fit in 80 % of
  the line, else a [`shot: closeup`](#shots-shot) of it (a cut held for the line; the next beat
  cuts back). Never in two beats in a row (a written `zoom` or shot counts), never in a beat with
  a walk, `enter`, `exit`, `move_along`, `keyframes`, `pan`, `follow`, `zoom`, a shot, `pick_up`,
  `put_down`, `give`, `throw`, `sit_on`, `lean_on` or `stand_up`, nor while the camera follows something, nor in a beat with a
  speech bubble or an automatic gesture of the speaker.
- **Effect symbols.** A strong change of expression gets an [effect symbol](#effect-symbols-effect)
  over the head as it starts: `surprised` an `exclaim`, `thinking` a `question`, `angry` an
  `anger` mark, `dizzy` `stars`, `frightened` `sweat` (`crying` none: its tears are on the
  face). At most one per line: the first such change in the beat (a written `emote` or
  `react`, a [voice sound](#voice-sounds)'s face, then the automatic reactions), for a character
  on the stage; none in a beat with a written `effect`. The symbol is added also for a written
  `emote` / `react` (it adds to the face; the action itself is unchanged).
- **Lint-safe.** Before adding a look, an arm gesture (`point`, `wave`, `shrug`) or a close-up,
  vidgen predicts the beat's still from the stage's layout (no rendering) with and without it and
  runs the lint rules `off_stage` and `facing_away` on both; an action that would add a finding is
  left out (an arm out of the view, a speaker turned from the one it talks to, a close-up that cuts
  the speaker or leaves only a character behind it in view). Automatic actions draw no bubble, so
  `bubble_overlap` cannot come from them.
- **What the parts allow.** No look for a character without a head, no reaction without eyes,
  brows or a mouth, only the gestures its arms and head allow (an SVG character,
  [above](#characters-from-svg-files)), and no arm gesture with a hand that
  [holds a prop](#props-in-hands) (`point` and `wave` use the near hand, `shrug` both). A look at
  a held prop aims at its holder; one at a prop put down or thrown, at where it landed.

`auto_direct: {looks: true, reactions: false}` picks kinds (`looks`, `reactions`, `gestures`,
`closeups`, `effects`; a kind not given is on). The added actions are ordinary
actions marked as automatic: `vidgen storyboard` lists them under their beat (`auto: look_at kit
pip · react kit thinking`; `--json`: each frame's `auto`), and the log names them `look_at kit
(auto)`. `vidgen direct [PROJECT]` (MCP tool `direct`) prints them per beat without rendering; `vidgen direct
--print` writes them as YAML to paste into `video.yaml` and edit (a close-up shot as the beat's
`shot:` line; once pasted they are written actions, so automatic directing adds nothing more for
those characters):

```yaml
auto_direct: true
scenes:
  - id: park
    type: stage
    params:
      characters: [{name: pip, at: left}, {name: kit, at: right}]
    beats:
      - text: "Is that a kite in the tree, or something else entirely?"
        voice: pip_voice      # kit looks at pip, pip at kit; kit reacts: thinking or surprised;
                              # pip shrugs on "entirely" (a question)
      - text: "A very flat bird."
        voice: kit_voice      # a close-up on kit: a short line after a long one
      - text: "Kit was not good with birds."
        auto_direct: false    # nothing added in this beat
```

#### Cartoons from a screenplay (`vidgen screenplay`)

`vidgen screenplay FILE.md [--out DIR|FILE.yaml] [--cast FILE] [--species NAME ...] [--seed S] [--force] [--json]` (MCP tool `screenplay`)
writes a stage project from a screenplay, without AI: one `stage` scene per `# Scene:` heading,
one beat per line, `auto_direct: true`, and `# TODO:` comments for what it could not map. The
project is checked like `vidgen validate` (exit code 1 when it finds problems). The format:

```markdown
---
title: The Humming Box        # optional front matter: video.yaml keys (not scenes) that win
voice: {provider: kokoro, voice: bf_emma, speed: 0.85}
---
# Scene: yard
set: background: day; props: house at 0.18, box (crate) at 0.6, tree at 0.84; characters: fen at left, bram at right

On a quiet Sunday, Fen heard a sound that did not belong in the yard.

FEN (surprised): Bram, listen! That box is humming a song.

[Fen walks to the crate and points at it.]

BRAM: Boxes do not hum, Fen. Boxes do not do *anything*.

GUS (glad): There it is! [jumps] I left my song in that crate.
```

- **Headings**: a first `# Title` (level 1, not `Scene...` or `Card...`) is the title; `# Scene: NAME` (any
  level; `Scene:` may be left out) starts a scene, its id from the name (`yard`, then `yard_2`).
  `# Card: Later that day…` (any level) is a [`card`](#card) scene with that text: silent for
  2.5 s, or narrated by the lines under it (a `[direction]` there becomes a `# TODO:`: a card has
  no stage; `set:` is an error). After another scene it comes in with an `iris_out`, and the
  scene after it opens with an `iris_in` ([iris transitions](#transitions-transition)).
- **`set:`** (right under the heading; `;`-separated, the colons optional): `background` a sky
  (`day`, `night`, `dusk`, `dawn`, `indoors`; default `day`), a colour or `a to b` (a gradient), or
  a picture file (`image`); `room` an [indoor set](#rooms-room) instead (alone: the defaults;
  else comma separated `stripes`, `dots`, `plain`, `boards`, `tiles`, `ceiling`, `window [at
  place]`, `[open] door [(name)] [at place]`: `room: stripes, window at 0.3, door at right`);
  `props` built-in props, `kind (name) at place` (a mark or an x; without `at` they go to 0.85,
  0.15, 0.65, 0.35; a house or tree goes back, `depth`), `against the wall` (or `on the wall`)
  for `against: wall` in a room; other words for furniture: `couch`, `bookcase`, `kitchen
  counter`, `refrigerator`, `picture frame`, `carpet`, `plant pot`, `wall clock`, `television`,
  `desk with chair`...; `marks` `name x`; `characters` `name at place`. Characters the set does
  not place stand on the marks in the order they appear (`left`, `right`; three: `left`,
  `centre`, `right`...).
- **Lines**: `NAME: text` (the name in capitals, several words allowed: `OLD ASH`); lines run on
  until a blank line. `NAME (manner): text`: manner words that name an expression or a pose
  (`happy`, `thinking`, `arms crossed`...) or a word for one (`doubtful` thinking, `glad`
  happy, `nervous` worried, `cross` angry, `shocked` surprised; since Step 125 `giggling`
  laughing, `embarrassed` / `shy` blushing, `cheeky` / `teasing` tongue_out, `sobbing` / `in
  tears` crying, `dazed` / `woozy` dizzy, `scared` / `afraid` / `terrified` frightened...) become `react` for that line;
  other words a `# TODO:`. A pronoun among them states the speaker's voice kind, for the voice
  and look it is given (once is enough, usually on the first line): `FEN (she): text` feminine,
  `BRAM (he, doubtful): text` masculine, `GUS (they): text` neutral (`she/her`, `he/him`,
  `they/them` too); two different kinds for one character are an error, and the narrator takes
  none. A plain paragraph, or `NARRATOR:`, is the narrator's line. `*word*`
  stresses a word (the speaker gestures on it; the asterisks are not spoken). A
  [voice sound](#voice-sounds) inside a line (`KIT: Oh no [gasp] it fell!`) stays in the line's
  text: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]`, `[beep]` (or `[laughs]`...) are
  sounds, every other `[...]` is a stage direction; on its own line `[laugh]` is a direction
  (a `# TODO:`, no verb matches it).
- **Stage directions** `[...]`: on their own line they act at the start of the next line (after
  the last line of a scene: at 0.6 of it), one after the other, each `at` estimated from how long
  the one before takes (a walk by its distance); inside a line they act at that point of it, with
  the speaker as subject. Each sentence (or clause after `and`) is matched against a small
  grammar: `X walks / goes / runs to Y` (`walk_to`: a mark, an x, or beside a prop or character,
  on the other side or a little further out when someone already stands there; `runs` twice as fast), `X enters [from the left]`, `X exits / leaves [left]`, `X jumps`,
  on a [platform level](#platform-levels-level) `X jumps / hops / leaps [up / down / across / over] to / onto Y` (`jump` with `to`: a spot or a mark; Step 155),
  `X looks at Y` (a character, prop, mark or the camera; `look at each other`), `X points at Y`
  (`look_at`, then `gesture: point`), `X waves [at Y]`, `nods`, `shrugs`, `shakes his head`, and
  an [effect symbol](#effect-symbols-effect) over X's head for `X has / gets an idea` or `lights up`
  (`idea`), `is / looks confused`, `puzzled`, `wonders`, `scratches his head` (`question`), `is
  startled`, `alarmed`, `shocked` (`exclaim`), `sweats`, `gulps`, `is nervous` (`sweat`), `is
  angry`, `furious`, `fumes` (`anger`), `falls asleep`, `dozes off`, `nods off`, `snores` (`sleep`),
  `falls in love [with Y]`, `swoons` (`hearts`), `is dizzy`, `sees stars` (`stars`), `sparkles`,
  `beams with pride` (`sparkle`), `cries`, `weeps`, `sheds a tear` (`tear`).
  Subjects are character names (`X and Y`) or `he` / `she` / `they` for the last ones; `it` /
  `him` / `her` name the last object. Anything else stays as `# TODO: [text]` above its beat.
- **Characters**: a character listed in the front matter's `characters:` is kept as written (a
  `voice_kind: feminine | masculine | neutral` key there states its voice kind and is left out of
  `video.yaml`; a declared character without a `voice` gets one of that kind); every other
  speaker gets a generated look from a set of eleven that differ in body, hair, eyes,
  accessories, clothes and colours (`# generated:` above `characters:`; the
  [gallery](#characters-characters) shows them) and a named voice `NAME_voice` with its `label`. Each look
  has a voice kind (four feminine, four masculine, three neutral); a character
  with a stated kind gets a look of that kind (then a neutral one), and its voice is of the
  look's kind (or the stated one), so the voice suits the look. A look of the set is skipped
  when it would be too like a declared or cast character (a [contrast](#a-random-cast-vidgen-cast)
  below 0.35), and once the set is used up the next characters get
  [random looks](#a-random-cast-vidgen-cast) chosen to differ from everyone before them:
  `--species cat dog` draws them from those species instead of the set (`human` among them keeps
  the set first), `--seed S` gives other random looks (default 0). Kokoro: a feminine character
  gets an `af_` / `bf_` voice, a masculine one `am_` / `bm_`, a neutral one the gender used less
  so far; another accent (American / British) than the characters before where possible, the
  narrator's kind last. The OpenRouter model's listed voices go in turn (no kinds known); with
  ElevenLabs every character keeps the base `voice_id` and a `# TODO:` says to set one, naming
  each character's voice kind.
  A character who speaks or is named by a direction in a scene is on that scene's stage.
- **Defaults**: 1920x1080 (preview 854x480), `theme: {preset: soft_pastel}`, the Kokoro narrator
  `bf_emma` at speed 0.85, `narration: {pad: 0.7}`, `auto_direct: true`; front matter keys win.
- **`--cast FILE`**: an [include file](#shared-casts-and-sets-include-and-sets) of a series
  (`characters`, `voices`, `sets`). The project `include:`s it (its path from the project folder)
  instead of copying it: its characters count as declared and keep their voices (only other
  speakers get generated looks and voices), and a `set:` line that starts with one of its set
  names (`set: meadow; props: ball at 0.4`) writes `set: meadow` on the scene: no default sky, the
  set's marks, props and character places count for the directions.
- **Sets in the front matter** (Step 155): a `set:` line may also start with a set of the front
  matter's `sets:`. That is how a screenplay gets a [platform level](#platform-levels-level): a
  set with a `level:` (its multi-line `map: |` is written back as it is); the level's spots are
  marks for `set:` lines and directions (`characters: nutmeg at start`, `[Nutmeg walks to
  brink.]`, `[Nutmeg jumps onto over.]`). `vidgen validate` then replays the moves on the tiles;
  the directions' `at` times are estimated as on a plain stage.

A sample is `examples/screenplay/humming_box.md`.

#### A random cast (`vidgen cast`)

`vidgen cast --random N [--seed S] [--species NAME ...] [--out FILE.yaml] [--provider kokoro|openrouter|elevenlabs]
[--narrator VOICE] [--model NAME] [--language TAG] [--force] [--json]` (MCP tool `cast`) writes N
original characters as an [include file](#shared-casts-and-sets-include-and-sets) (`characters`
and `voices`; default `cast.yaml`), chosen to be told apart at a glance. Use it with `include:
[cast.yaml]` in `video.yaml` or `vidgen screenplay STORY.md --cast cast.yaml`.

- **Looks**: generated looks (any body, head size, eyes, hair, outfit, pattern, shoes, up to two
  accessories; adult proportions; hex colours, so the cast looks the same in every theme). For
  each character 48 random looks are drawn and the one least like the characters before it is
  kept (the highest lowest contrast). `--species` draws from those species (`human`, `cat`, `dog`,
  `bird`, `bear`, `rabbit`, `mouse`, `fox`, `owl`, `frog`, `turtle`, `penguin`, `snail`, `robot`; several: a mix;
  default `human`; a fox, owl, frog, turtle, penguin or snail gets fur or skin in its own natural tones,
  a turtle or a snail a shell colour, a robot a plating colour and a random `look.robot`). Costume pieces are
  never drawn at random.
- **Voice kinds and voices**: the kinds go round feminine, masculine and neutral (each round of
  three shuffled); a look suits its kind (facial hair only masculine; no dress or bow for a
  masculine or neutral character; no bun, ponytail or braids for a masculine one). Voices are
  chosen like `vidgen screenplay`'s: Kokoro voices of the kind's gender, all different, other
  accents first, never the narrator's (`--narrator`, default `bf_emma`); OpenRouter's listed
  voices of `--model` in turn; ElevenLabs: `label`s only and a `# TODO:` to set `voice_id`s.
- **Names**: short, common first names of the character's kind from a built-in list (never a
  famous character's name), each once.
- **Seeds**: the same seed gives the same file; a bigger cast of the same seed starts with the
  smaller one (`--random 5` adds a character to `--random 4`).
- **Contrast**: a score from 0 (the same look) to 1, the sum of three parts: silhouette 0.45
  (body 0.25, hair 0.2, species 0.15, a hat / cap / bow 0.1, proportions 0.1, head size 0.1, ears
  0.05, a dress or coat 0.05), colour 0.4 (how far apart the clothes 0.4, skin or fur 0.3, hair 0.2
  and accessory 0.1 colours are in CIELAB, the theme's tokens resolved; 30 CIEDE2000 counts as
  fully different) and accessories 0.15 (the share of accessories, facial hair, pattern, shoes,
  eyes and nose only one of them has). The file's comment gives the lowest contrast of the cast;
  the [lint rule](#lint-vidgen-lint) `look_alike` warns when two characters of a video score below
  `min_contrast` (0.35).

#### Animation principles (`cartoon_motion`)

Characters move with four classic principles of cartoon animation, built into the acting and
moving actions:

- **anticipation**: before a move, a short move the other way. A pose change, `emote`, `turn`,
  `look_at`, `react` or `gesture` swings each part a little back first; a walk crouches and
  leans back before the feet move; a jump crouches before take-off.
- **squash and stretch**: a jump squashes the figure in the crouch, stretches it as it leaves the
  ground and as it falls (round at the top), squashes it on landing; its width changes the other
  way, so it keeps its area.
- **overshoot and settle**: a moving part passes where it stops and comes back (a pointing arm, a
  gesture's arm going up and coming down); after a walk the body leans on past the stop and
  straightens; after a landing the figure bounces back a little.
- **follow-through**: the arms, head and accessory (a hat; a generated character's hair and ears
  are part of its head) trail when the body sets off and carry on when it stops, swinging back
  once as on a spring; in a jump the arms lift as the figure falls.

One setting, `cartoon_motion`, chooses how much: `lively` (the default: all four, fully),
`calm` (the same, at 0.4 of the amount: for a quiet or serious video) or `none` (the plain
motion: parts ease straight to their place, nothing squashes). Set it for the whole video
(top level), for one `stage` scene (param) or for one character (`characters[]`); the nearest
wins: the character's own, else the scene's, else the video's.

```yaml
cartoon_motion: calm            # the whole video
characters:
  - name: pip
    cartoon_motion: lively      # pip stays bouncy everywhere
scenes:
  - id: office
    type: stage
    params:
      cartoon_motion: none      # this scene: plain motion (pip still lively)
      characters: [pip, kit]
```

The wind-up and settle add time: a walk 0.65 s (`lively`; 0.26 s `calm`), a jump 0.48 s
(0.19 s). Pose changes and gestures keep their time. As for any action, a beat with less time
left shortens them.

#### Motion effects (`motion_effects`)

With `cartoon_motion` on (`lively`; `calm` draws them at 0.76 of the size), the moves add small
drawings of their own, with nothing to write:

| effect | when |
|---|---|
| dust | puffs blow back where a fast walk or a `run_to` sets off and forward where it stops (not where an `enter` starts or an `exit` ends: off view), and both ways where a `jump` lands |
| speed lines | three ink lines behind a fast walk or a run while it is near full speed (fast: 1.15 of its own heights per second or more; a default `walk_to` goes about 0.7, a `run_to` about 1.7), and behind a prop a `throw` or `blow_away` sends flying |
| impact stars | a burst of small stars from the feet when a `jump` of `height: 0.7` or more lands |
| whoosh | two thin arcs trailing the hand while the arm of a `gesture` with `big: true` sweeps up (`point`, `wave`; `shrug` both hands) |
| smoke | grey puffs rolling out on the ground where a [`toy_rocket`](#water-and-air-vehicles-water-land) launches and a trail behind it while its motor burns, each growing and fading over 1.1 s (behind the rocket); a boat or a balloon makes no dust or lines |

Each is a drawing of its own beside its character or prop (never part of it), not graded by the
stage's `light`, the same in every render (seeded by the scene, the mover and the time), and gone
when it ends (0.55 s for dust, 0.6 s for stars). `motion_effects: false` turns them off for the
whole video (top level) or one `stage` scene (param; the scene's wins); `cartoon_motion: none`
turns them off for that character. With them off a video renders exactly as without them. They
make no sound (foley does that). In the layout dump each is an object of kind `motion_effect`
(name and `motion_effect`: `dust`, `speed_lines`, `impact`, `whoosh`, `smoke`; `effect_of`: the
character or prop); `off_frame`, `covered_text` and `hidden_speaker` skip them (they pass in a
moment), and `lint_ignore`'s `object` matches `effect_of`.

```yaml
motion_effects: false           # the whole video: no dust or lines
scenes:
  - id: race
    type: stage
    params:
      motion_effects: true      # but this scene has them
    beats:
      - text: "Pip dashes off."
        actions:
          - {run_to: pip, to: far_right}
          - {gesture: kit, to: wave, big: true, at: 0.5}
```

#### Keyframes and motion paths

For motion the other actions do not have, two actions move a character, a [prop](#props) or one
part of a character (`kit.arm_left`, `pip.head`; the parts are `body`, `legs`, `leg_left`, `leg_left_lower`,
`leg_right`, `leg_right_lower`, `arm_left`, `arm_left_lower`, `arm_right`, `arm_right_lower`, `head`,
`accessory`, `tail`, `antenna`, `cape`, `eyes`, `brows`, `mouth`, those the character has) by
**keys** or along a **path**:

| action | options | |
|---|---|---|
| `keyframes` | `keys` (required: `[{t, x, y, rotate, scale, ease}, ...]`), `ease` (`smooth`) | moves through the keys and stays at the last one. A key's `t` is seconds from the action's start (`at`), or a share of the beat's narration as a string (`"40%"`); every key one way or the other, in time order. Each key sets some of `x`, `y`, `rotate`, `scale`; a value a key leaves out holds, and the target starts from how it is. A key at `t: 0` sets its values at once. It takes until the last key. |
| `move_along` | `path` (required: `[[x, y], ...]`), `curve` (`smooth` \| `straight`), `ease` (`smooth`), `speed` | moves from where it is through the points, at an even speed eased by `ease`: a smooth curve through every point (`smooth`) or straight lines between them. Takes `speed` units per second along the path, else `run_time` (default 2 s). Stays at the end. |

The values mean, for a **character or prop**: `x` a mark or an x from 0 (left edge) to 1 (right
edge) of the stage; `y` the height of its feet above its ground line (at its depth), in frame
heights (`0` on the ground, `0.5` half the frame higher; at most 1 either way); `rotate` degrees
counterclockwise on screen, about its feet; `scale` its size (`1` as built). For a **part**:
`x` / `y` its shift right / up in character heights (at most 1 either way); `rotate` its angle
about its pivot in degrees, as drawn facing right (a mirrored character turns it the mirrored
way: `kit.arm_left` at `rotate: 90` points forward whichever way kit faces; arms hang down at 0);
`scale` its size (a flipped part, such as a `sad` mouth, stays flipped). `rotate` and `scale` are
where the target ends up, not steps: after `rotate: 30`, `rotate: 0` turns it back.

`ease` names how each key is reached (a key's own `ease` wins over the action's) or how the path
speeds up and slows down. The names are Manim's rate functions: `linear`, `smooth`, `rush_into`,
`rush_from`, `ease_in_sine`, `ease_out_sine`, `ease_in_out_sine`, `ease_in_quad`,
`ease_out_quad`, `ease_in_out_quad`, `ease_in_cubic`, `ease_out_cubic`, `ease_in_out_cubic`,
`ease_in_back`, `ease_out_back`, `ease_in_out_back`, `ease_out_bounce`, `ease_out_elastic`; plus
`lively` and `calm`, a smooth move with the anticipation and overshoot of that
[`cartoon_motion`](#animation-principles-cartoon_motion) level (keyframes do not apply
`cartoon_motion` on their own). On a path, an ease that passes the end (`ease_out_back`) holds at
the end instead.

Both last (`until: <beat>`: the target moves back to where it was, straight, in the action's
`run_time`, default 1 s for `keyframes`, 2 s for `move_along`). `run_time:` on `keyframes`
stretches or squeezes the keys to that time; a beat with less time left squeezes them too. A
moved character does not turn to face where it goes (add a `turn`) and keeps walking, jumping
and acting from where it is (a lifted one walks in the air: bring it down first).

`vidgen validate` reports keys out of order, mixed seconds and shares, a share over 100%, an
unknown ease, a mark the stage does not know, a mark as a part's `x`, a value out of range, a
part the character does not have (`unknown target 'kit.tail'`) and these actions on other scene
types. A pattern such as `k*` also selects the parts (`kit.arm_left`...); the acting and moving
actions skip them, but `keyframes`, `dim` or `highlight` act on each.

```yaml
beats:
  - text: "Pip floats over the bench while Kit waves its arm."
    actions:
      - move_along: pip
        path: [[0.35, 0.25], [0.5, 0.0]]       # up and over, down onto the middle
        speed: 4
      - keyframes: kit.arm_left
        keys:
          - {t: 0.3, rotate: 150, ease: ease_out_back}
          - {t: 0.6, rotate: 120}
          - {t: 0.9, rotate: 150}
          - {t: 1.5, rotate: 0}                # back down (arms hang at 0)
      - keyframes: sun                         # a prop: across the sky over the whole beat
        keys: [{t: "100%", x: 0.8, y: 0.6, ease: linear}]
```

#### Particles

Rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or wind streaks over a scene: on a `stage` for the whole
scene with the `particles` param, or on any scene type from a beat with the `particles`
[beat action](#beat-actions) (for that beat; `until: <beat>` or `keep: true` for longer; `keep:
true` on the first beat gives any scene type particles throughout). They are drawn in front of
everything, over the part of the frame the camera shows (they stay on screen through a `zoom` or
a `pan`), fade in over 0.5 s, and fall, drift, spin or rise on their own. Positions come from
`seed`, so every render of the same video shows the same particles.

| key | default | |
|---|---|---|
| `kind` | required | `rain` (slanted streaks), `snow` (white dots that sway), `sparkles` (twinkling stars, `highlight`), `dust` (faint drifting motes), `confetti` (spinning chips in the theme's colours), `smoke` (grey puffs that rise, grow and thin out), `bubbles` (rising rings), `leaves` (tumbling leaves that drift far in a [wind](#wind-wind)), `streaks` (faint white lines along the wind, seen only while a stage's wind blows harder than a breeze: none on a calm stage or another scene type) |
| `density` | `1` | how many, up to 4: 1 is the kind's usual amount for a whole frame (rain 160, snow 120, confetti 90, dust 60, sparkles 40, bubbles 30, leaves 28, smoke 24, streaks 22), scaled by the share of the frame `area` covers. At most 300 per field, whatever the density; a [preview render](#format-and-preview) draws half as many |
| `area` | the whole frame | `[x, y, w, h]`: fractions 0–1 of the visible frame from its top-left corner (smoke from a chimney: `[0.6, 0.1, 0.08, 0.5]`); particles fade out near its edges |
| `color` | per kind | a colour (theme token or `#hex`) or a list, each particle picking one: rain `#A9C1DD`, snow `#FFFFFF`, sparkles `highlight`, dust `#E6DCC8`, confetti `accent highlight primary secondary tertiary`, smoke `#B9BEC6`, bubbles `#CFE9FF`, leaves `#7BAE4E #C9A23A #C2703D`, streaks `#FFFFFF` |
| `seed` | `1` | another number gives other positions |
| `puddles` | `false` | rain on a `stage` only: `true` lets puddles grow on the ground while it rains ([Rain on the ground](#rain-on-the-ground)) |
| `lightning` | `false` | rain on a `stage` only: `true` flashes [lightning](#lightning-and-thunder-lightning) while it rains, at seeded times about every 8 s, with thunder; a number (2–120) is the seconds between strikes on average |
| `settle` | `false` | snow on a `stage` only: `true` lands it on the ground and on the props, where a white layer grows while it snows ([Snow that settles](#snow-that-settles-settle)) |
| `settled` | `0` | with `settle`: seconds of snowfall already lying when it starts, 0–600 (`24` or more: the full layer at density 1) |

```yaml
- id: storm
  type: stage
  params:
    background: ["#2B3240", "#4A5568"]
    characters: [pip]
    particles: [{kind: rain, density: 1.5}]
  beats:
    - text: "It never stops raining here."
- id: result
  type: title
  params: {title: "We shipped it"}
  beats:
    - text: "And then, after a year of work, we shipped it."
      actions:
        - {particles: confetti, at: 0.4, keep: true}
```

`vidgen validate` reports an unknown kind (with a did-you-mean), the kind given twice, an `area`
outside the frame, a `density` out of range, `keep` with `until`, `puddles` or `lightning` on a
kind other than rain, `settle` on a kind other than snow and `settled` without `settle`. The layout dump sees a
field as one object of kind `particles` named after its kind; `vidgen lint`'s `off_frame` leaves
it out (particles cross the edges on purpose).

##### Rain on the ground

On a `stage`, rain (the `particles` param or the `particles` action) ends on the ground instead of
falling past it. Each drop lands on its own line between 0.05 frame heights in front of the
ground line and the top of the ground area (up to where the deepest character or prop stands),
so drops land at different depths, and a small splash (a flat ring and two droplets, seeded like
the drops) shows where it landed for 0.3 s, smaller further back.

Rain does not fall through a shelter: an **open umbrella** (standing, or held overhead) and a
**tree**'s crown. A shelter is the box its drawing covers now (it follows a held umbrella and a
swaying tree): drops over it stop at its top edge (with a splash there) when they would land
behind its front edge (0.1 frame heights in front of the ground line where it stands, or its
holder stands). So a character under an open umbrella or a tree stays dry; a closed umbrella
shelters nothing. `puddles: true` grows a few flat puddles (4 per frame width of the stage, seeded,
none under a shelter) on the ground from nothing to full size over 10 s of rain; they stay when
the rain stops.

While a rain field lasts, a generated **rain sound bed** plays under the scene (no recordings: a
soft hiss with many small drop ticks and a few plops, a seamless 8 s loop), fading in over 1.5 s
from the rain's start and out over 1.5 s ending where the field is gone (its fade out included);
rain running from one stage scene into the next plays as one bed. It is mixed like the
[music](#background-music-music) at **−32 LUFS** (4 dB under the music's −28 LUFS, about 11 dB
under typical narration in its pauses) and ducked under the narration by **5 dB** (the music: 12),
so it stays faintly audible under the voice (about 16 dB under it). It follows the stage's foley:
on by default, off with `foley: false` (the stage param or the top-level key). The render's
`timings.json` lists it under each scene's `ambience` and the `mix` report's `ambience`. Other
scene types get no ground and no bed: their rain falls through the frame as before.

```yaml
- id: picnic
  type: stage
  params:
    props: [{prop: tree, at: right}, {prop: umbrella, at: 0.35, open: true}]
    characters: [{name: dot, at: 0.3}, {name: moss, at: right}]
    particles: [{kind: rain, density: 1.5, puddles: true}]   # dot under the umbrella, moss under the tree
```

##### Snow that settles (`settle`)

On a `stage`, snow with **`settle: true`** (the `particles` param or the `particles` action) lands
instead of falling past the ground: each flake on its own line in the ground area (as rain does),
or on a prop standing behind that line: on the upper edge of its drawing (a house's roof, a tree's
crown, a table top, a rock, a car's roof...), and on an open umbrella. A landed flake lies still
for half a second, fading. Where it lands a white **layer** grows with the seconds of snowfall
(full after 24 s at `density: 1`, twice as fast at 2), in half-second steps:

- a **blanket** over the ground area, faint at first and covering the ground from 40 % of the full
  layer on, its back edge rising a little above the ground area in soft lumps; under a tree or a
  standing open umbrella it stays thin (about half as opaque);
- a **cap** on every prop on the ground that no action moves, along the upper edge of its drawing
  where that edge is no steeper than 45°, up to 0.03 of the frame's shorter side thick at depth 0
  (thinner further back, at most a fifth of the prop's height). Props that fly, float, lie flat
  (a rug) or hang (a cloud, a picture), umbrellas and, while the stage's wind may blow, swaying
  props (trees, bushes...) get none.

The layer stays when the snow stops (it does not melt). **`settled: 30`** starts it as after 30
seconds of snowfall: a white meadow from the first frame. The layer is graded by the
[light](#light-and-shadows-light-shadows) (bluish at `night`); the flakes are not, like every
particle. `color` (the first colour of a list) also colours the layer. Snow on other scene types,
and without `settle`, falls through the frame as before. Only the layer and what stands in front
of it are redrawn while it grows; once full (or once the snow has stopped) it costs nothing per
frame. No footprints.

```yaml
- id: winter
  type: stage
  params:
    light: night
    props: [{prop: house, at: 0.2, depth: 0.5}, {prop: tree, at: 0.8, depth: 0.3}]
    characters: [{name: dot, at: 0.45}]
    particles: [{kind: snow, density: 1.5, settle: true, settled: 6}]
```

#### Fog (`fog`)

**`fog:`** lays fog over a `stage` outdoors: translucent bands, one lying on the ground at each
of the depths 1, 0.8, 0.6, 0.4 and 0.2, each drawn right in front of everything standing further
back. So a character or prop is seen through every band in front of it: the further back it
stands, the more fog covers it, and the sky and the background layers most; at depth 0.2 or
nearer nothing covers it. Each band is densest near the ground (two wavy banks up to 0.3 of the
frame height above its ground line) and thinner above (a haze up to the top of the frame), with
soft edges. The banks' waves drift slowly sideways (the nearer ones faster) and with the stage's
[wind](#wind-wind). A character walking in depth passes in and out of the bands.

`fog: true` is a density of 0.5 (a character at depth 0.5 about a third hidden near the ground,
the sky low down more than half); a number is the density (above 0, up to 1: a thick fog); a
mapping sets `density`, `color` (a theme token or #hex; default a pale grey blue `#DCE2EA`),
`drift` (0–5, default 1; `0`: the waves stay still unless the wind blows, so the fog is drawn
once per animation, not on every frame) and `seed` (the waves; default one from the scene). The fog is graded by the
light (a blue-grey fog at night). A `room` refuses it. While its waves move, everything from the
backmost band on is redrawn on every frame (a scratch forest at preview: about 12 % more
render time).

```yaml
- id: forest
  type: stage
  params:
    fog: {density: 0.6}
    props: [{prop: tree, at: 0.15, depth: 0.9}, {prop: tree, at: 0.6, depth: 0.5}]
    characters: [{name: dot, at: 0.3}, {name: moss, at: 0.75, depth: 0.7}]
```

#### Lightning and thunder (`lightning`)

The **`lightning`** [beat action](#beat-actions) strikes at its `at`: the whole set flashes two
or three times within about half a second (each flash held for a few hundredths of a second and
dying away, seeded), every graded colour taken half way to a cold white at the brightest (stars and
shadows fading as much; speech bubbles and text unchanged, like the [light](#light-and-shadows-light-shadows)),
and a **bolt** (a white zigzag with a pale blue glow and one to three branches) strikes the
horizon behind everything on the stage, shown only while it flashes. Its target is where:
`- lightning: right` (a mark) or `- lightning: 0.7` (an x); without one the scene picks a place.
`distance` (km, default `1`, up to 10) sets how far away it is: a farther strike flashes less (at
least 0.4 of a near one) and its bolt is thinner, and its **thunder** (the generated
[`thunder`](#sound-effects-sfx) sound: a crack, then a rolling rumble) comes later at the speed of
sound (**about 3 s per km**: 0.343 km a second), quieter (−3 dB at the strike, −3 dB per km, at
least −18), longer (2.2 s + 0.6 s per km) and lower (a semitone per km), panned where it struck.
`bolt: false` is sheet lightning (a flash only); `seed` varies the bolt and the flashes. The
thunder follows the stage's foley (off with `foley: false`); a thunder later than the scene's end
plays into the next scene (`vidgen render` says so).

In a `room`, lightning comes in through the **windows**: their sky flashes nearly white and the
room lights up half as much as outdoors; no bolt. Rain with **`lightning: true`** (the
`particles` param or action) strikes on its own while it rains: seeded times about every 8 s (a
number: those seconds on average, at least 2), places across the stage, 0.6 to 4 km away, most
with a bolt (the others sheet lightning); its thunders whose start would fall after the scene's
end are left out. While a flash lights the set the whole stage is redrawn on every frame (an
animation in which one falls is redrawn whole): a scratch rainy stage with two strikes, a storm
striking every 4 s and a rainbow took about 20 % more render time at preview.

```yaml
- id: storm
  type: stage
  params:
    light: night
    props: [{prop: house, at: 0.2, depth: 0.5}, {prop: tree, at: 0.8, depth: 0.3}]
    characters: [dot]
    particles: [{kind: rain, density: 1.5, lightning: true}]
  beats:
    - text: "The storm broke over the house."
      actions:
        - {lightning: right, at: 0.3, distance: 0.5}   # the thunder 1.5 s later
```

#### Rainbows (`rainbow`)

The **`rainbow`** [beat action](#beat-actions) fades a rainbow into the sky over `run_time`
seconds (default `3`) from its `at`, and it stays: seven soft bands (red outside to violet inside),
a half ring standing on the horizon (the back edge of the ground area), drawn right after the sky,
so the hills, the ground and everything on the stage stand in front of it. Its target is where its
middle is (`- rainbow: centre`, a mark or an x; default the middle of the stage); `width` is its
outer width in frame widths (default `0.75`), `opacity` how strongly it shows (default `0.55`). It
is graded by the light. **`hide: true`** (without a place) fades every rainbow shown so far out.
Best after rain (it does not check for any). Outdoors only: a `room` refuses it. Only the rainbow
and what is drawn over it are redrawn while it fades.

```yaml
- id: after_the_rain
  type: stage
  params:
    background: ["#9CC4E8", "#E8EEF4"]
    characters: [dot, moss]
  beats:
    - text: "Then the rain stopped and a rainbow came out."
      actions:
        - {rainbow: centre, at: 0.2, width: 0.9}
```

#### Light and shadows (`light`, `shadows`)

A stage's `light` sets the mood with a colour grade of everything on the set: the background
(picture, colour or the theme's background), the layers, the props and the characters. Speech
bubbles, callouts, captions and other text are not graded, so they keep the theme's colours and
their contrast (`vidgen lint`'s `contrast` rule reads the graded pixels behind any other text);
particles keep their colours too.

| `light` | what it does |
|---|---|
| `day` (default) | the set as drawn |
| `morning` | a soft peach haze, a little brighter |
| `sunset` | warm and orange-pink, a little darker; blue skies turn warm |
| `night` | dark blue; stars in the sky (on a colour background only, behind the layers, above the characters' heads) and faint shadows |
| `indoor` | warm lamplight, a little dimmer |
| `{tint, strength}` | a light of your own: every colour multiplied towards `tint` (a theme token or `#hex`) by `strength` (0 = no change, 1 = fully, default `0.5`) |

The `light` [beat action](#beat-actions) changes the light during the scene: `- light: night`
(or `tint` + `strength`) fades from the light at its `at` over `run_time` seconds (default `2`)
and lasts until another `light` action; the stars fade in and out with it. Everything on the
stage is redrawn on every frame while the light fades; before and after, the set stays in
Manim's static image as usual.

**`move_sun: true`** on a `light` action (with a preset) moves the stage's `sun` and `moon`
props along an arc across the sky while the light fades, to their places for the new light: the
sun low on the left in the `morning`, at the top by `day`, low on the right at `sunset`, set
(under the horizon) at `night` and `indoor`; the moon rising on the left at `sunset`, at the top at
`night`, setting on the right in the `morning`, under the horizon by `day`. They always move
forward (left to right), so a sun that set comes up again on the left. In a scene with
`move_sun`, the sun and the moon stand on that arc from the start (where the stage's own `light`
puts them; a tint: as by day), whatever their `at` and `lift`, are drawn right after the sky
(behind the hills and everything on the ground), fade out as they sink under the horizon and in as
they rise. The **shadows** then follow the body that shows most (the sun on a tie): stretched
along the ground away from it, longer the lower it is (by the cotangent of its height in the sky,
at most 3 × 0.6 of a shadow's width longer, and fainter), its foot staying under the caster;
straight overhead they are as usual. It needs a `sun` or a `moon` prop and the stage outdoors;
`vidgen validate` says so. A scene without `move_sun` draws its sun, moon and shadows as before.

```yaml
- id: evening
  type: stage
  params:
    background: ["#9CC4E8", "#E8EEF4"]
    props: [sun, moon, {prop: tree, at: 0.85, depth: 0.3}]
    characters: [dot]
  beats:
    - text: "The afternoon wore on and the shadows grew long."
      actions:
        - {light: sunset, move_sun: true, run_time: 4}
    - text: "Then night came and the moon rose."
      actions:
        - {light: night, move_sun: true, run_time: 4}
```

`shadows` (default `true`) puts a soft shadow on the ground under each character and each prop
standing on the ground (not under a cloud, sun or moon or another prop with a `lift`): an
ellipse as wide as about half a character's height (a prop: nine tenths of its width), at the
ground line of its `depth` (so smaller further back), following walks and jumps (smaller and
fainter the higher it is) and thrown or keyed props, and none under a prop someone holds. The
light sets how dark they are (`night` faint). The layout dump leaves shadows and stars out.

```yaml
- id: porch
  type: stage
  params:
    background: ["#9CCBEA", "#E4F3FB"]
    light: sunset                       # the scene starts at sunset
    characters: [pip, kit]
    props: [{prop: lamp, at: 0.85}]
  beats:
    - text: "The sun went down over the porch."
    - text: "And the first stars came out."
      actions:
        - {light: night, at: 0.2, run_time: 3}
```

#### Drawing style (`drawing`)

The top-level **`drawing`** switches how every `stage` scene of the video is drawn; a stage's own
`drawing` param overrides it key by key, and a variant may change it like any key. Characters keep
their looks: only the line weight, the fill and the paper change.

| key | values (default first) | what it does |
|---|---|---|
| `outline` | `normal` \| `thin` \| `bold` | the width of every stroke the stage draws (characters, props, the set, effect symbols, motion effects, speech bubbles, particles with rings): as drawn, 0.6 × (never thinner than one pixel unless it was already) or 1.7 × |
| `shading` | `flat` \| `soft` | `soft`: each filled shape of the characters and props is a little lighter at its top and darker at its bottom (a vertical gradient over its own height, light from above); outlines and silhouettes are unchanged |
| `texture` | `none` \| `paper` \| `storybook` | a still grain over the whole frame: `paper` a fine grain with faint blotches, `storybook` a coarser grain, bigger blotches and darker corners; it lies under the [overlays](#overlays) (captions, lower thirds, watermark…), which stay clean, and over everything the scene draws, the speech bubbles too |
| `seed` | `0` | the texture's grain: the same seed and frame size give the same grain in every scene and every render |

```yaml
drawing: {outline: bold, shading: soft, texture: storybook}   # the whole video
variants:
  clean: {drawing: {texture: none}}                           # a variant without the grain
scenes:
  - id: dream
    type: stage
    params:
      drawing: {outline: thin, texture: paper}                # this scene only (shading stays soft)
```

![One set in each drawing style](gallery/media/drawing_styles.png)

The style is applied as the frames are drawn, never to the drawings themselves: `vidgen lint`,
the layout dump and the character sheets see the same shapes in every style, and a video without
`drawing` (or with `normal`, `flat`, `none`) renders exactly as before. A
[draft](#drafts-vidgen-render---draft) keeps the outline and draws flat, without texture. A
[host](#a-host-beside-any-scene-host) on other scene types gets the outline and the shading, not
the texture (those scenes are not cartoons). Cost, measured on `cartoon-rain-check`'s `storm`
scene: at 640x360 `bold` or `thin` +3–5 %, `soft` +5 %, a texture up to +8 %, all three
+12–18 %; at 1280x720 `soft` +4 %, a texture +10 % (the grain is harder to encode), all three +15 %.

#### Wind (`wind`)

A stage's `wind` blows in gusts (seeded noise, the same in every render): `0` is calm and
changes nothing, `0.3` (`breeze`), `0.6` (`windy`), `1` (`gale`) blow to the right, a negative
number to the left. In the wind:

- built-in trees, bushes, plants, signs and lamps sway, bending about their base, each in its
  own rhythm, gusts reaching the far side of the stage a little later. Strong wind moves things
  more than in proportion: a tree's top leans about 2.5° on average in a breeze, 6° when windy
  and 14° in a gale (up to 25° in a gust), a plant's leaves more, a lamp post hardly. Props an
  action moves, holds, sits on or leans on, props with a `lift` and SVG props stand still;
- generated characters' scarf ends, long hair, buns, floppy and pointy ears, hats, an animal's tail, a robot's
  antenna, a cape (far), a wizard hat and a party hat trail
  downwind on a spring: they lag a gust and swing past it (a scarf's end about 23° when windy,
  45° in a gale, never over the head). Imported SVG characters (except a part `tail`), round ears, short or curly hair
  and glasses do not move (nothing marks such pieces in a drawing);
- particles (the stage's and those of a `particles` action) drift downwind; rain slants more.
  `leaves` tumble and blow far, and `streaks` (faint lines along the wind) show the gusts
  from `windy` on: `particles: [leaves, streaks]` makes a windy scene read at once.

The `wind` [beat action](#beat-actions) changes it: `- wind: 0.8` (or `calm`, `breeze`, `windy`,
`gale`) fades from the wind at its `at` over `run_time` seconds (default `2`) and lasts until
another `wind` action. While anything sways, the stage is redrawn on every frame from the first
swaying prop on (renders of `examples/cartoon` took 7–13 % longer at a gale); a calm stage stays
in Manim's static image as usual.

```yaml
- id: hill
  type: stage
  params:
    wind: breeze                        # a light wind from the start
    characters: [pip, kit]
    props: [{prop: tree, at: 0.85}]
    particles: [{kind: dust, density: 0.6}]
  beats:
    - text: "Then the storm came in."
      actions:
        - {wind: gale, at: 0.3, run_time: 3}
```

##### Props that blow away (`blow_away`)

`- blow_away: napkin` blows a light prop away: it tumbles along a gusty path (seeded, the same
in every render), lifted and bobbing, downwind and off the stage (up and away); with `to:` (a
mark or an x of the stage) it lands there upright, at its full size, at its own depth (or its
holder's). A prop someone holds is blown out of the hand: the hand lets go at once, the empty arm
goes back down and the holder holds nothing from then on (the layout dump and `vidgen validate`
agree). It takes longer the farther it goes and the lighter the wind (from the middle of a 16:9
stage to off its edge: 1.6 s in a gale, 2.9 s when windy; at most 6 s); `run_time` sets it. Light props only: `napkin`,
`umbrella` (open or closed), `ball`, `cup`, `basket`, `box`, `letter`, `balloons`, and SVG props.

`vidgen validate` reports a heavy prop (`'tree' (tree) is too heavy to blow away`), a target
that is not a prop, an unknown `to`, a `blow_away` without `to` while the stage's wind is calm
(its `wind` and the `wind` actions before it), a prop someone sits or leans on, and any later use
of a prop blown off stage (`pick_up`, `hold`, `sit_on`, `lean_on`, `move_along`, `keyframes`,
`open`, `close`, another `blow_away`); a `put_down`, `give` or `throw` by its former holder is
"holds no prop then".

```yaml
- id: picnic
  type: stage
  params:
    wind: windy
    particles: [leaves, streaks]
    characters: [pip, kit]
    props: [{prop: umbrella, at: 0.3, open: true}, {prop: napkin, at: 0.5}]
  beats:
    - text: "Pip holds the umbrella up, and the napkin flies away."
      actions:
        - {hold: pip, to: umbrella}
        - {blow_away: napkin, at: 0.3}
    - text: "Then a gust takes the umbrella right out of her hand!"
      actions:
        - {wind: gale, run_time: 0.5}
        - {blow_away: umbrella, at: 0.2, to: far_right}
```

A wide stage with layers, the camera panning and then following a character:

```yaml
  - id: walk
    type: stage
    params:
      width: 2                                   # two frames wide
      camera_at: left
      background: [primary, surface]
      layers:
        - {name: hills, shapes: [{shape: hills, y: 0.2, height: 0.2, width: 0.8, color: tertiary}]}
        - {name: trees, place: middle, image: assets/trees.png, bottom: 0.18}
        - {name: bushes, place: foreground, shapes: [{shape: ellipse, x: 0.4, width: 0.5, height: 0.15, color: accent}]}
      characters: [{name: pip, at: left}, {name: kit, at: far_right}]
    beats:
      - text: "Far away, on the other side of the park, Kit is waiting."
        actions: [{action: pan, to: far_right, run_time: 2}]
      - text: "Back to Pip, who has not seen her yet."
        actions: [{follow: pip}]
```

#### Ambience and door sounds (`ambience`, `knock`)

While [foley](#foley-and-music-stings) is on, every `stage` scene plays a quiet **sound bed of
its set** under the whole scene, generated like the [rain bed](#rain-on-the-ground) (numpy only,
seeded, seamless loops, no recordings):

| bed | what it sounds like | level (LUFS) | ducks under the voice |
|---|---|---|---|
| `birdsong` | about one bird phrase a second, near and far, left and right (runs of short falling tweets at 3–5 kHz, two-note whistles at 2–3 kHz, trills at 3.5–5.5 kHz) over a faint airy rustle; a 20 s loop | −36 | 4 dB |
| `city` | street sounds: a low traffic rumble, three or four cars passing (1–2 s swells around 600 Hz) and a far murmur of people; a 16 s loop | −35 | 5 dB |
| `room_tone` | the air of a quiet room: soft low noise (40–250 Hz) with a faint hiss; an 8 s loop | −46 | no |

The levels are integrated loudness before ducking (the music: −28, the rain: −32); each bed fades
in over 2 s from the scene's start and out over 1.5 s ending at its end, and the same bed in the
next stage scene goes on without a dip.

**Chosen automatically** (`ambience: auto`, the default): a [room](#rooms-room) plays its
`room_tone`; outdoors, `birdsong` plays while the light is `day` or `morning` (a [`light`
change](#light-and-shadows-light-shadows) counts half-way through its fade; not at `sunset`,
`night`, `indoor` or a tint), never while it [rains](#rain-on-the-ground) and only 2 s after the
rain stops, and not for less than 2 s; nothing else. The `city` bed is never chosen: name it.
A stage's **`ambience`** param names the bed for the whole scene (`ambience: city`, `ambience:
[city, birdsong]` for a park in town) or turns it off (`false`); the top-level `ambience: false`
turns the automatic choice off for the video (a stage that names a bed still plays it).
`foley: false` (the stage's or the video's) silences all of them. Rain and a burning fireplace
play their own beds whatever `ambience` says. `timings.json` lists them under each scene's
`ambience` and the `mix` report's `ambience`; a project file `assets/sfx/...` does not replace a
bed.

**Doors.** A door's hinge `creak`s as it opens (`- open: front`) and, shorter and higher, as it
closes (`- close: front`), and a `thud` as it shuts; an `enter` or `exit` through a closed room
door creaks as it opens (the character fades in the doorway: no whoosh). **`- knock: front`**
knocks three times on a door (a room's door or a `door` prop) at `at` of the beat; nobody needs to
stand at it (a knock from outside). It draws nothing and plays a `knock` with foley.

```yaml
- id: visitor
  type: stage
  params:
    room: {doors: [{name: front, at: 0.85}]}      # room_tone under the scene
    characters: [{name: pip, at: 0.4}]
  beats:
    - text: "Someone knocks at the door."
      actions: [{knock: front, at: 0.2}, {react: pip, expression: surprised, at: 0.5}]
    - text: "Pip opens it. Nobody is there."
      actions: [{walk_to: pip, to: 0.7}, {open: front, at: 0.6}]
- id: street
  type: stage
  params: {ambience: city, characters: [pip]}      # outdoors by day would be birdsong
  beats: [{text: "So Pip goes out into the busy street."}]
```

**Changed in Step 128:** stages that play no new sound action still get the automatic beds, so a
project rendered again sounds different: outdoor day scenes gain birdsong, rooms a room tone, an
entrance or exit through a door a creak instead of the whoosh / swoosh, a boat ride a splash.
`ambience: false` at the top level brings back the earlier beds (only rain and fire).

### `card`

A cartoon title card: the episode's name, "Later that day…" between two scenes, "The End". The
card's `color` fills the frame behind a burst of rays turning slowly (`style: burst`), a double
frame (`frame`) or nothing (`plain`); the text pops in with a bounce, bold, in white or the dark
ink (whichever reads better on the card) with a thick outline in the other; the subtitle rises
under it. Steps: (1) the burst or frame, the text (and the subtitle with one beat or none),
(2) the subtitle. Silent with a `duration`, or narrated by its beats. Fades out over 0.5 s. It
pairs with the [iris transitions](#transitions-transition) and a screenplay's `# Card:` heading.
[Action targets](#beat-actions): `text`, `subtitle` (when given), `burst` or `frame` (by style).

| param | type | default | |
|---|---|---|---|
| `text` | str | required | the card's words, wrapped to fit |
| `subtitle` | str | `""` | a smaller line under the text |
| `style` | `burst` \| `frame` \| `plain` | `burst` | rays behind the text, a double frame round it, or the colour alone |
| `color` | color | `primary` | the card's colour; the lighter rays are a tint of it |
| `text_color` | color | white or the dark ink | fill of the letters |
| `outline_color` | color | the other one | outline of the letters and the frame's lines |
| `spin` | bool | `true` | `burst`: the rays turn slowly while the card is on |
| `sting` | `reveal` \| `comic` \| `sad` \| `{kind, gain}` | none | a [music sting](#foley-and-music-stings) as the text pops in (a beat's own `sting` can come after its line instead) |

```yaml
- id: later
  type: card
  params: {text: "Later that day…", subtitle: "at the old mill", sting: comic}
  duration: 2.5
  transition: {type: iris_out, character: pip}   # closes on pip in the scene before
```

## Beat actions

A beat can act on named parts of its scene — **targets** such as `item3` or `bar:4K` — while it
is spoken: reveal one early, dim it, highlight it, zoom in on it, morph it into another, or
point at it with a callout (also at any spot of the frame). Actions are listed under the beat:

```yaml
- id: sizes
  type: bar_chart
  params: {labels: ["Preview 480p", "720p", "1080p", "4K"], values: [0.4, 1.1, 2.6, 9.8]}
  beats:
    - text: "Bar charts grow their bars while the values count up."
    - text: "Four K takes by far the longest."
      actions:
        - {action: highlight, target: "bar:4K", style: box, until: sizes_b3}   # canonical form
    - text: "Previews are the fast way to iterate."
      actions:
        - dim: [bar2, bar3, bar4]                  # shorthand: {ACTION: TARGET, ...options}
        - highlight: "bar:Preview 480p"
          color: accent                            # an option, in the shorthand too
```

```yaml
- id: square
  type: equation
  params:
    latex: ["(a + b)^2", "(a + b)(a + b)", "a^2 + 2ab + b^2"]
    terms: ["2ab"]                                 # parts of a formula actions can target
  beats:
    - text: "Take a plus b, squared, and jump straight to the result."
      actions:
        - {transform: step1, into: step3, at: 0.5} # step 2's own turn is then skipped
    - text: "The middle term, two a b, comes from the two cross products."
      actions:
        - zoom: "term:2ab"                         # the camera moves in, and is back by the beat's end
    - text: "That is the whole expansion."
```

```yaml
- id: trend
  type: line_chart
  params: {title: "Validation loss", x: [1, 2, 3, 4], series: {baseline: [2.1, 1.8, 1.6, 1.5], sparse: [2.2, 1.7, 1.5, 1.4]}}
  beats:
    - text: "Here is the baseline."
    - text: "And here is the sparse model, which ends lower."
      actions:
        - callout: "point:sparse@4"                # on a target: an arrow from a label to it
          kind: arrow
          label: "Lowest loss"
          at: 0.4                                  # gone when the next beat starts
    - text: "Both start from the same loss."
      actions:
        - {action: callout, kind: box, area: [0.1, 0.15, 0.3, 0.3], label: "Start"}   # coordinates of the frame
```

**Syntax.** The canonical form is a mapping with `action` and the keys below, plus the
action's options. The shorthand `{ACTION: TARGET, ...options}` (as `- dim: item2`) is the
same thing; write the action name as the first key (if a tool sorted the keys, vidgen finds
the one key that names an action).

| key | default | |
|---|---|---|
| `action` | required | `reveal`, `dim`, `highlight`, `zoom`, `pan`, `follow`, `transform`, `callout`, `sfx`, `particles`, `say`, `look_at`, `turn`, `emote`, `pose`, `react`, `walk_to`, `run_to`, `enter`, `exit`, `gesture`, `jump`, `keyframes`, `move_along`, `pick_up`, `hold`, `put_down`, `give`, `throw`, `open`, `close`, `let_go`, `pour`, `switch_on`, `switch_off`, `knock`, `drop_fruit`, `birds`, `sit_on`, `lean_on`, `stand_up`, `step_aside`, `get_in`, `ride_to`, `get_out`, `light`, `wind`, `blow_away`, `effect`, `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`, `host_exit`, or a project action (`vidgen list-scenes` lists them) |
| `target` | required | a target name, a list of names, or a pattern with `*` / `?` (`bar:*`, `item?`) that must match at least one (`callout` with an `area` and `pan` with `to` need none) |
| `at` | `0` | when: a fraction of the beat's narration (`0` ≤ at < `1`), or a word the beat says, `"@gradient"` ([below](#actions-on-a-spoken-word)) |
| `until` | none | a later beat of the same scene: the action lasts until that beat (`dim`, `highlight`, `callout`, `say`, `react`, `look_at`, `turn`, `emote`, `pose`: undone when it starts; `zoom`: the camera is back when it starts; `pan`: the camera moves back when it starts; `follow`: the camera stops following when it starts; `keyframes`, `move_along`: the target moves back) |
| `run_time` | the action's | seconds the animation takes (`reveal` / `callout` / `pose` 0.8, `dim` / `highlight` / `react` 0.6, `zoom` / `transform` / `follow` 1.0, `pan` 1.5, `look_at` / `emote` 0.5, `say` (the bubble) / `turn` / `effect` (the pop) 0.4, `jump` 0.6 (with `to` on a level: its run-up, crouch, flight and landing), `gesture` per gesture (1.2 for `point`), `walk_to` / `run_to` / `enter` / `exit` as long as the distance needs at their `speed`, `keyframes` until its last key, `move_along` 2.0 or its path's length at its `speed`, `pick_up` / `give` 1.2, `put_down` / `sit_on` 1.0, `lean_on` / `stand_up` 0.8, `get_in` 1.0, `get_out` 0.9, `ride_to` as long as the distance needs at its `speed`, `hold` 0.4, `open` / `close` 0.6, `throw` 0.95–2.1 by the distance, `light` / `wind` 2.0 (the fade), `blow_away` by the distance and the wind (0.6–6), `let_go` by how far the balloons rise (1–6), `pour` 2.0; a zoom takes as long again to come back) |

**Targets** depend on the scene type (`vidgen list-scenes` prints them as `targets:`). Every
built-in type has some; `<N>` counts from 1 (`item1`, `item2`...), `<text>`/`<label>`/`<name>`
are written out in full (`item:Pick scene types`, or with a pattern: `item:Pick*`). The last
column lists the actions that make sense on them (the others work, but rarely help: a `zoom` on
a title card, a `transform` of a bar).

<!-- targets-table: kept in sync with the scene types by tests/test_actions.py -->
| scene type | targets | useful actions | notes |
|---|---|---|---|
| `title` | `icon`, `kicker`, `title`, `subtitle`, `authors` | reveal, dim, highlight | those the card has |
| `text_card` | `text` | highlight, zoom | |
| `bullets` | `heading`, `item<N>`, `item:<text>` | reveal, dim, highlight, zoom, transform | an item is its row (marker, icon, text) |
| `icon_grid` | `heading`, `item<N>`, `item:<label>` | reveal, dim, highlight, zoom, transform | an item is its icon, label and sublabel |
| `bar_chart` | `title`, `bar<N>`, `bar:<label>`, `change<N>` | reveal, dim, highlight, zoom | a bar with its value and category labels; a `box` sits on the axis; `change<N>` is every bar, revealing it plays that change |
| `line_chart` | `title`, `axes`, `series<N>`, `series:<name>`, `point:<name>@<x>`, `change<N>` | reveal, dim, highlight, zoom, trace | a series is its line, markers and end label; `point:sparse@8`; `change<N>` is the axes and lines, revealing it plays that change; `trace` a series to sweep a cursor along it |
| `scatter` | `title`, `axes`, `legend`, `series<N>`, `series:<name>`, `point:<series>@<N>`, `point:<series>@<label>`, `trend`, `trend:<series>` | reveal, dim, highlight, zoom | a point is its marker and label; `point:ours@2` is the 2nd point written; `legend` with several series, `trend:` with `trend: each` |
| `histogram` | `title`, `axes`, `legend`, `bin<N>`, `bin:<range>`, `compare`, `mean`, `median` | reveal, dim, highlight, zoom | `bin:10-20` names a bin by its edges; `legend` and `compare` with `compare`; `mean` / `median` when set |
| `pie` | `title`, `slice<N>`, `slice:<label>`, `center`, `legend` | reveal, dim, highlight, zoom | a slice is its wedge, label and leader line (a `box` frames the wedge); `slice:Other` after grouping; `center` with a donut, `legend` with the names in a legend (revealing it reveals every slice); `dim` and `highlight` recolour a label inside its slice so it stays readable on the slice's new look |
| `heatmap` | `title`, `legend`, `row<N>`, `row:<label>`, `col<N>`, `col:<label>`, `cell<R>.<C>` | reveal, dim, highlight, zoom | a row / column is its cells and label (`box` and `fill` cover its cells edge to edge); `cell2.3` is row 2, column 3; `style: box` keeps the data colours (`color` paints the cells, `fill` tints them); values are recoloured to stay readable on dimmed, painted or tinted cells |
| `map` | `title`, `map`, `legend`, `country:<code>`, `pin<N>`, `pin:<label>`, `arc<N>`, `step<N>` | reveal, dim, highlight, zoom | `country:` for highlighted and valued countries, by alpha-3, alpha-2 or name (`country:DEU`, `country:DE`, `country:Germany`): a highlight with its label (revealing it plays its highlight), a valued country its shape; a pin is its dot and label; `step2` is step 2's items (revealing it plays the step); `zoom: country:FRA` looks closer; `dim: map` fades the countries under the highlights |
| `image` | `image`, `caption` | dim, highlight, zoom | `dim` fades the picture, `highlight` tints it |
| `screenshot` | `title`, `image`, `caption`, `callout<N>`, `callout:<label>`, `step<N>` | reveal, dim, highlight, zoom | a callout is its mark and label (`highlight` repaints the mark and the label's plate; its text keeps a readable colour); `callout:New task`; `step2` is step 2's callouts (revealing it plays the step); `zoom: callout3` looks closer; `dim: image` fades the picture under the callouts |
| `video_clip` | `title`, `clip`, `caption`, `callout<N>`, `callout:<label>`, `step<N>` | reveal, dim, highlight, zoom | as in `screenshot`; `clip` is the moving picture with its frame: `dim` fades it, `highlight` tints it, `zoom` looks closer (it is decoded sharper for that) |
| `quote` | `mark`, `quote`, `author`, `source` | reveal, dim, highlight, zoom | |
| `equation` | `step<N>`, `caption`, `term:<tex>` | reveal, dim, highlight, zoom, transform | `term:` for each of the `terms` param, in the step on screen; `transform: step1` + `into: step3` jumps ahead |
| `equation_derivation` | `title`, `step<N>`, `note<N>`, `result`, `term:<tex>` | reveal, dim, highlight, zoom, transform | `term:` for each part in `terms`, `colors`, `match` or marked `{{ }}`, in the current step only; `step2` is also its dimmed line; `note2` (revealing it plays step 2); `result` is the last step with its box |
| `function_plot` | `title`, `axes`, `function<N>`, `function:<name>`, `dot<N>`, `tangent<N>`, `area<N>`, `point<N>`, `point:<name>`, `vector<N>`, `vector:<name>`, `segment<N>`, `brace<N>`, `angle<N>`, `dimension<N>` | reveal, dim, highlight, zoom, trace | a function is its curve and label, a dot its dot, label and guides; `{trace: dot1, to: 2}` moves a dot along its curve (label and tangent follow), `{trace: area1, to: 4}` an area's right end, `{trace: "point:C", to: [4, 4]}` a point, `{trace: "vector:a", scale: 2}` a vector (`to: [x, y]` moves its tip), everything drawn from them following; `{reveal: tangent1, at: "@word"}` draws a tangent on that word; marks are numbered by kind (`brace2` is the second brace) |
| `number_line` | `title`, `line`, `point<N>`, `point:<name>`, `interval<N>`, `jump<N>` | reveal, dim, highlight, zoom, trace | a point is its dot and label, an interval its band, ends and label, a jump its arc and label; `{trace: point1, to: 4}` moves a point along the line |
| `code` | `title`, `listing`, `line<N>`, `lines:<a-b>` | dim, highlight, zoom | a line with its number; `lines:3-5`; a wide line leaves little to zoom |
| `code_morph` | `title`, `listing`, `version<N>`, `version<N>.line<K>` | reveal, highlight, dim | `{reveal: version2, at: "@word"}` morphs to version 2 on that word (the scene then leaves that morph to the action); `listing` is whichever version shows; `version2.line3` is line 3 of version 2 (with its number) |
| `terminal` | `title`, `terminal`, `code`, `code.line<K>`, `command<N>`, `output<N>`, `output<N>.line<K>` | reveal, dim, highlight | `{reveal: output2, at: "@word"}` shows step 2's output on that word, `command2` types the command then (the scene leaves them to the action); `terminal` is the window; `code` the listing beside it |
| `code_walkthrough` | `title`, `listing`, `line<N>`, `lines:<a-b>`, `note<N>` | reveal, dim, highlight | `reveal: line40` scrolls it into view; `lines:<a-b>`: every range up to 40 lines, else the steps' ranges; `note2` is step 2's note (revealing it plays the step); the next step resets line opacities |
| `end_card` | `logo`, `icon`, `title`, `line<N>` | reveal, dim, highlight | those present |
| `chapter` | `icon`, `number`, `title`, `subtitle` | reveal, dim, highlight | those present |
| `card` | `text`, `subtitle`, `burst`, `frame` | reveal, dim, highlight, zoom | `subtitle` when given; `burst` or `frame` by `style` |
| `stat` | `icon`, `value`, `label`, `comparison`, `context` | reveal, dim, highlight, zoom | `reveal: value` early runs the count; `comparison` is the change chip with its text |
| `comparison` | `heading`, `col<N>`, `col:<heading>`, `col<N>.item<M>`, `verdict` | reveal, dim, highlight, zoom | a column is its heading and points (a `box` frames its card); `col2.item1` is a point with its marker; revealing a point brings its column's card |
| `table` | `title`, `header`, `row<N>`, `row:<first cell>`, `col<N>`, `col:<header>`, `cell<R>.<C>`, `caption` | reveal, dim, highlight, zoom | `box` and `fill` cover the whole row / column / cell; `cell2.3` is row 2 (below the header), column 3 |
| `timeline` | `heading`, `axis`, `event<N>`, `event:<date>` | reveal, dim, highlight, zoom | an event is its marker, stem and text; revealing one grows the progress line to it; `event:1969` |
| `diagram` | `heading`, `node<N>`, `node:<id>`, `edge:<from>-><to>` | reveal, dim, highlight, zoom | also for `flowchart`; a node is its shape, icon and label (a `box` frames the shape), an edge its line, arrowhead and label; `highlight: [node:a, "edge:a->b", node:b]` marks a path; revealing an edge brings its nodes |
| `process` | `heading`, `input`, `stage<N>`, `stage:<label>`, `connector<N>`, `loop`, `output`, `token` | reveal, dim, highlight, zoom | a stage is its card (a `box` frames it); `connector2` runs from stage 2 to 3; revealing a stage early shows it without moving the token; `highlight: token` with `style: flash` points at it |
| `network` | `heading`, `layer<N>`, `layer:<label>`, `edges<N>`, `neuron<L>.<i>` | reveal, dim, highlight, zoom | a layer is its units, ellipsis, label and count; `edges1` joins layers 1 and 2; `neuron2.3` is unit 3 of layer 2 as drawn |
| `stage` | `<character>`, `<prop>`, `<character>.<part>` | say, look_at, turn, emote, pose, react, effect, walk_to, run_to, enter, exit, gesture, jump, step_aside, keyframes, move_along, pick_up, hold, put_down, give, throw, open, close, switch_on, switch_off, knock, drop_fruit, blow_away, sit_on, lean_on, stand_up, get_in, ride_to, get_out, dim, highlight, zoom, pan, follow | each character and each prop on the stage by its name (`dim: kit`, `zoom: pip`, `follow: pip`, `highlight: tree`), each part of a character as `kit.arm_left` (the parts it has); everything comes in at step 1 (a character with an `enter` action waits off stage until then); `pan` also takes a mark (`to: right`); the [acting](#speaking-and-acting), [moving](#moving), [prop](#props-in-hands) and [sitting](#sitting-and-leaning) actions and `get_in` / `get_out` take whole characters only, [`ride_to`](#vehicles-get_in-ride_to-get_out) a vehicle or its riders, [`keyframes` and `move_along`](#keyframes-and-motion-paths) characters, props and parts, [`open` / `close`](#umbrellas-open-and-close) and [`switch_on` / `switch_off`](#clocks-televisions-and-lamps-time-on-switch_on) props, [`knock`](#ambience-and-door-sounds-ambience-knock) a door, [`drop_fruit`](#fruit-falling-from-a-tree-fruit-drop_fruit) a tree (`to`: a character); `birds` takes no target |

`title` and `heading` stand for each other (the header band, see "Built-in scenes"): `highlight:
title` works on a `bullets` heading. [Project scene types](EXTENDING.md#8-per-beat-actions-targets-and-custom-actions)
can declare their own targets; a type without any rejects actions in `vidgen validate`.

**Actions**

| action | options | |
|---|---|---|
| `reveal` | — | brings the target on screen with the scene's own entrance animation (e.g. item 4 before its turn). A target already on screen is left alone, and the scene does not reveal it again at its own step. |
| `dim` | `opacity` (`0.45`, 0–1, of the target's full opacity) | fades the target; one that is already dimmer (e.g. by `bullets`' `dim_previous`) stays as it is, so dimming never compounds; `until:` restores the opacity |
| `highlight` | `color` (`highlight`, a theme token or hex), `style` (`color` default, `box`, `underline`, `fill`, `flash`, or a list such as `[color, box]`) | `color` recolours the target and brings a dimmed one back to full opacity while highlighted; `box` draws a rounded frame around it, `underline` a line under it, `fill` lays a translucent band of the colour under it (over backdrops such as table stripes and cards); `flash` flashes the colour there and back (leaves no trace; not with `color`). `until:` restores the colours (and the dimming) and removes box / underline / fill. |
| `zoom` | `scale` (magnification > 1, up to 8; default: as close as the targets fit), `padding` (`0.15`: share of the view kept free on each side of the targets) | moves the camera in on the targets and back out: the zoom-out ends with the beat (with `until: <beat>`, when that beat starts). Without `scale` the view is at most 3x; a target that already fills the frame is not zoomed (a warning says so). The view never leaves the frame (on a wide `stage`: the stage). Coming back, the camera returns to the view it had before the zoom. While a `follow` runs, the camera keeps the followed character in the middle. |
| `pan` | `to` (a `stage`'s mark, or an x from 0 = left to 1 = right of the stage) | moves the camera sideways to the target (on a `stage`: a character) or to `to` — one of the two — keeping its zoom; it stays there (`until: <beat>`: it moves back when that beat starts). Ends a `follow`. The view never leaves the stage, so on a scene as wide as the frame the camera pans only while zoomed in. Other scene types know no marks (`to` is an x). `cut: true` jumps there at once (actions due with it are built for the new view). |
| `follow` | — | pans to the target (one character) and then keeps the camera on its feet as it moves, inside the stage, at the camera's zoom: to the end of the scene, or until the `until` beat starts (the camera then stays where it is). A `pan` or another `follow` ends it. On a [platform level](#the-camera-on-a-level-follow) it follows gently (a dead zone, easing) and up and down too. |
| `transform` | `into` (required: a target not on screen yet), `style` (`auto` default, `replace`, `shapes`, `tex`, `fade`) | morphs the target into `into`, which then stays on screen in its own place (the target is gone). `shapes` moves matching glyphs (what `auto` uses for text and formulas), `replace` morphs point by point (`auto` for other shapes), `tex` matches the TeX parts of two formulas, `fade` cross-fades. `into` must be a target of the scene; text that is not part of the scene cannot be morphed into (give the scene that content, e.g. as a later equation step). If `into` is already on screen, the target fades out into its place (warning). |
| `callout` | `kind` (`box` default, `circle`, `arrow`, `label`, `spotlight`, `magnifier`), `label`, `area`, `within` (`frame` \| `safe`), `units` (`fraction` \| `px`), `color` (`highlight`; a label that says one of the video's [terms](#one-colour-per-concept-terms): its colour), `label_size` (`caption`), `side` (`auto`, `top`, `bottom`, `left`, `right`), `curved` (arrow), `zoom` (magnifier, `2`), `keep` (`false`), `name` | points at the target — or, without a target, at `area` of the frame — with the [Step 34 callouts](#screenshot): a rounded `box` (label as a tag on its edge), a `circle`, an `arrow` from the label, a `label` beside it (no mark), a `spotlight` (the rest of the view darkened) or a `magnifier` (an enlarged inset of a picture: the target must show one, e.g. `image`). Gone when the next beat starts (`until: <beat>`: when that beat starts; `keep: true`: stays to the end of the scene). See "Callouts" below. |
| `sfx` | `sound` (or as the target: `- sfx: NAME`), `gain` (`0` dB), `pan` (`0`), `align` (`start` \| `end`), `params` (`duration`, `pitch`, `intensity`) | plays a [sound effect](#sound-effects-sfx) at `at` — exactly then, even while the scene animates; draws nothing, works on every scene type. Its "target" is the sound's name, not a target of the scene; no `until`, no `run_time`. |
| `wind` | as the target: `- wind: 0.8` (a number from `-1` to `1`, negative blowing left) or `calm`, `breeze`, `windy`, `gale` | on a `stage`: fades the [wind](#wind-wind) from `at` over `run_time` seconds (`2`); it lasts until another `wind` action. Its "target" is the strength, not a target of the scene; no `until`. |
| `blow_away` | as the target: the prop (`- blow_away: napkin`); `to` (a mark or an x 0–1; default: off the stage downwind) | on a `stage`: the wind blows a light prop away, tumbling, out of a holder's hand too; it lands upright at `to` or is gone ([props that blow away](#props-that-blow-away-blow_away)). No `until`. |
| `light` | as the target: `- light: night` (`day`, `morning`, `sunset`, `night`, `indoor`), or `tint` + `strength` (`0.5`); `move_sun` (`false`) | on a `stage`: fades the [light](#light-and-shadows-light-shadows) from `at` over `run_time` seconds (`2`); it lasts until another `light` action; `move_sun: true` moves the sun and moon across the sky meanwhile, the shadows turning. Its "target" is the light, not a target of the scene; no `until`. |
| `lightning` | as the target: where (`- lightning: right`, a mark or an x; optional); `distance` (`1` km), `bolt` (`true`), `seed` | on a `stage`: the set flashes and a bolt strikes from `at`, its thunder `distance` × ~3 s later (foley); in a room the windows flash; see [Lightning](#lightning-and-thunder-lightning). `run_time` is the flash (0.7 s); no `until`. |
| `rainbow` | as the target: where its middle is (`- rainbow: centre`; optional); `width` (`0.75`), `opacity` (`0.55`), `hide` (`false`) | on a `stage` outdoors: a rainbow fades into the sky over `run_time` (`3`) from `at` and stays; `hide: true` fades the rainbows out; see [Rainbows](#rainbows-rainbow). No `until`. |
| `particles` | `kind` (or as the target: `- particles: snow`), `density` (`1`), `area`, `color`, `seed` (`1`), `keep` (`false`), `puddles` (`false`) and `lightning` (`false`, rain on a stage), `settle` (`false`) and `settled` (`0`, snow on a stage) | [particles](#particles) — `rain`, `snow`, `sparkles`, `dust`, `confetti`, `smoke` or `bubbles` — over the scene from `at`, in front of everything; works on every scene type; on a stage, rain ends on the ground and plays a rain sound bed while it lasts ([Rain on the ground](#rain-on-the-ground)), snow with `settle` lands and a white layer grows ([Snow that settles](#snow-that-settles-settle)). They fade in, and fade out (still moving; `run_time`, `0.6` s) when the next beat starts (`until: <beat>`: when that beat starts; `keep: true`: at the end of the scene). Its "target" is the kind, not a target of the scene. |
| `say`, `look_at`, `turn`, `emote`, `pose`, `react` | see [Speaking and acting](#speaking-and-acting) | the acting actions on a `stage`'s characters: speak (lip sync and a speech bubble), look at something, turn round, change expression or pose, react to another speaker for one beat |
| `effect` | `to` (required: `sweat`, `anger`, `idea`, `question`, `exclaim`, `sleep`, `hearts`, `stars`, `sparkle`, `tear`), `color`, `sound` (`true`) | on a `stage`'s characters: a symbol over the head that pops in, follows the character and shrinks away when the next beat starts (`until: <beat>`: when that beat starts); see [Effect symbols](#effect-symbols-effect) |
| `walk_to`, `run_to`, `enter`, `exit`, `gesture`, `jump`, `step_aside` | see [Moving](#moving) | the moving actions on a `stage`'s characters: walk or run to a mark, walk in or out of view, point / wave / shrug / nod / shake the head, jump, a level's blocker moving out of the way |
| `trace` | `to` (an x, or `[x, y]` for a point or a vector's tip) or `scale` (a vector only) | on a [`function_plot`](#function_plot): a dot (`dot<N>`) travels along its curve to x = `to`, its value label, guides and tangent following; an area (`area<N>`) moves its right end to `to`, its value following; a point (`point<N>`, `point:A`) moves to `to: [x, y]`; a vector (`vector<N>`, `vector:a`) moves its tip to `to: [x, y]` or is multiplied by `scale` (2: twice as long, -1: turned round; its tail stays). Vectors, sums, marks and live labels drawn from a moved point or vector follow it. On a [`number_line`](#number_line): a point moves to `to` (a number). On a [`line_chart`](#line_chart): a cursor dot sweeps along a series (`series<N>`, `series:<name>`) to x = `to` (on category `x`, the position from 1) with the line's value over it. 2 s; it stays there (`until: <beat>`: back when that beat starts). |
| `keyframes`, `move_along` | see [Keyframes and motion paths](#keyframes-and-motion-paths) | move a `stage`'s character, prop or character part (`kit.arm_left`) through keys (`t`, `x`, `y`, `rotate`, `scale`, `ease`) or along a path of points |
| `pick_up`, `hold`, `put_down`, `give`, `throw` | see [Props in hands](#props-in-hands) | a `stage`'s character takes a prop in its hand, puts it down, hands it to another character or throws it |
| `open`, `close` | see [Umbrellas](#umbrellas-open-and-close) | a `stage`'s umbrella opens (held overhead) or closes; a door too (`by`: who opens it; on a level a locked door needs its key, [story props](#story-props-on-a-level-keys-doors-coins-stars-blockers)) |
| `switch_on`, `switch_off` | as the target: the prop (`- switch_on: tv`) | on a `stage`: a `tv`, a `lamp`, a `fireplace`, a `kettle` or a `phone` (ringing) goes on or off at `at` (at once, with a click; a fire lights with a whoosh, a phone starts ringing); see [Clocks, televisions and lamps](#clocks-televisions-and-lamps-time-on-switch_on), [fireplaces and kettles](#fireplaces-and-kettles-on-switch_on) and [small props](#everyday-small-props-let_go-pour). No `until`. |
| `knock` | as the target: the door (`- knock: front`) | on a `stage`: someone knocks three times on a door (a room's door or a `door` prop) at `at`, with foley; draws nothing (a knock from outside); see [Ambience and door sounds](#ambience-and-door-sounds-ambience-knock). No `until`. |
| `let_go` | as the target: the character (`- let_go: pip`); `prop` | on a `stage`: the character lets go of the balloons it holds and they float away out of the frame, drifting with the wind ([small props](#everyday-small-props-let_go-pour)). No `until`. |
| `pour` | as the target: the character (`- pour: kit`); `prop` | on a `stage`: the watering can the character holds tilts and pours water drops to the ground (2 s) ([small props](#everyday-small-props-let_go-pour)). No `until`. |
| `drop_fruit` | `to` (a character; none: the ground) | on a `stage`: a fruit falls from the target tree (`fruit: true`), with a bounce and a thud, on a character's head with `to` (stars); see [Fruit falling from a tree](#fruit-falling-from-a-tree-fruit-drop_fruit) |
| `birds` | as the target: how many (`- birds: 5`); `count`, `direction`, `height`, `seconds`, `seed` | on a `stage` outdoors: a flock of birds crosses the sky from `at`; see [Birds](#birds-birds). No `until`. |
| `sit_on`, `lean_on`, `stand_up` | see [Sitting and leaning](#sitting-and-leaning) | a `stage`'s character sits on a chair, a rock, a box or furniture (a sofa, an armchair, a bed, a desk), leans on a tree, a door, a sign or furniture (a counter...), and stands up again |
| `get_in`, `ride_to`, `get_out` | see [Vehicles](#vehicles-get_in-ride_to-get_out) | a `stage`'s character gets in a car, a bus, a boat or a balloon or on a bicycle, the vehicle rides (or flies) to a place with its riders, and they get out |
| `shot` | `kind` (`wide`, `two_shot`, `medium`, `over_shoulder`, `closeup`), `move` (`false`) | what a beat's [`shot:`](#shots-shot) key writes, as an action: the camera frames the target characters of a `stage` from `at` to the beat's end. Write the key; the action is for a shot that starts later in the beat (`at`). |
| `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`, `host_exit` | see [Pointing, reacting and moving](#pointing-reacting-and-moving-host-actions) | the scene's [host](#a-host-beside-any-scene-host) points at or looks at a target of the scene, shows an expression (and a symbol), walks to the other side (the content slides over), walks in or out; any scene type with a host |

`dim`, `highlight`, `zoom` and `transform` act on targets on screen; a target not shown yet is
first revealed (as by `reveal`). `dim` and `highlight` change only opacity resp. colour, so
both can apply to one target and each is undone separately. Images are dimmed and tinted too
(their pixels). Text written on a filled shape of its target (a pie slice's label, a heatmap
value, a callout's label on its plate) is not faded or painted with the shape: it takes the
colour that reads on the shape's new look (dimmed: kept at 70 % opacity). Undoing a `dim`
(`until`) keeps the scene's own dimming since (`bullets`' `dim_previous`, a `highlight` step).
A highlight `box` (and `fill`) surrounds what the scene marks as the target's
outline (a bar and its value, standing on the axis; a table row, column or cell edge to edge; a
comparison column's card; else the whole target). Boxes, underlines and fills move with their
target when the scene moves it later (a `code_walkthrough` scrolling, a pie slice pulled out)
and fade while it is off screen (a line scrolled out of the window).

**Callouts** (`callout`) work on every scene type, also project types without targets (with an
`area`). What they point at:
- a target (`callout: "bar:4K"`): its outline (a bar with its value; else its parts on screen);
  a list or a pattern gives one callout around all of them;
- a target and an `area`: `[x, y, w, h]` (or a point `[x, y]`) from the top-left corner, as
  fractions of the target's picture when it shows one (`image`, `screenshot`'s `image`,
  `video_clip`'s `clip`; so the numbers read off the image file, and `units: px` are its pixels),
  else of the target's box;
- an `area` alone: fractions of the visible frame (`within: safe`: of its safe area), or with
  `units: px` pixels of the output frame (1920 x 1080...).

Labels are bold text on a plate in `color` with readable text (as in `screenshot`), never below
the readable size. They go away from what they point at, inside the safe area (which leaves out
overlays with `reserve: true`), clear of the text on screen, of other callouts, of the scene's
other small parts (a node, a bar) and of the overlays; `side` picks a direction as long as a
spot there is clear (else the label goes where one is: on a crowded chart a label beside a bar
would sit on its neighbour). A `label` (no mark) goes straight above, below or beside its
target before the corners, keeps 0.2 units from other text where it can (lint's
`label_spacing`) and never stands clearly nearer another bar, value or the title than its own
target. A callout is drawn over everything else of the scene. While the camera is zoomed in (a `zoom` earlier in the
beat or due at the same moment — the callout then appears once the camera is in — a `screenshot`
focus) it is built for the zoomed view, so its label reads at the normal size; one drawn before
a zoom grows with the scene. `name: peak` makes it a target of later
actions (`dim: peak`, `highlight: peak`; its label stays readable). Validation: a callout needs a
target or an `area`, a `magnifier` a target and an area; `kind: label` needs a `label`; `curved`
is for arrows, `zoom` for magnifiers; `keep` and `until` exclude each other; a `name` must be new
in the scene. A magnifier on a target without a still picture is an error when the scene renders.

**Timing.** Actions never make a beat longer. An action is due `at` x the beat's narration
(or on its word, below) after the beat starts and runs at the first moment from then on when the scene's own animation
is not playing (the scene's reveal of that beat's step comes first, then the action), for its
`run_time`, shortened to end within the beat (narration + `narration.pad`; `vidgen lint`
reports run times shortened below 0.5 s as `rushed_animation`). Actions due together play
together (ones on the same target, and two camera moves, one after the other). Undoing
(`until`) happens at the start of that beat, with its actions (a `callout` without `until`:
at the start of the next beat). A `zoom` is undone so that the
camera is back when the next beat (or its `until` beat) starts: its zoom-out starts `run_time`
before that beat's end, and a zoom-in late in a short beat is shortened together with its
zoom-out. If a scene leaves no time at all, the action is applied without animation and a
warning is logged. Silent scenes have no beats, so no actions. While the camera is zoomed in,
`vidgen lint` does not report text cut off by the frame or in the margins (`off_frame`,
`safe_area`): that is what a zoom does.

**Checks.** `vidgen validate` reports unknown actions (with suggestions), unknown options,
invalid option values, `until` on an action that cannot be undone or on a beat that is not a
later one of the scene, and unknown targets, listing the scene's targets, e.g.
`scenes[3].beats[1].actions[0].target: unknown target 'bar:4k' for scene type 'bar_chart'; did
you mean 'bar:4K'? (targets: title, bar1, bar:Preview 480p, ...; forms: title, bar<N>,
bar:<label>; * and ? match several)`. The JSON Schema checks action names and options; targets
depend on the params, so only `vidgen validate` checks them. Use `vidgen storyboard --scene ID
--per-beat 3` to see actions mid-beat.

### Actions on a spoken word

Instead of a fraction, `at` can name the word the action belongs to: the action starts as the
narrator begins that word.

```yaml
- text: "The loss is high, so we follow the gradient downhill, and the gradient gets smaller."
  actions:
    - {highlight: "term:loss", at: "@loss"}
    - {callout: "point:grad", label: "slope", at: "@gradient"}      # its first time in the beat
    - {highlight: "term:grad", at: "@gradient#2"}                   # its second time
    - {reveal: arrow, at: "@downhill-0.2s"}                         # 0.2 s before the word
    - {zoom: curve, at: "@gets smaller"}                            # a few words in a row
    - {sfx: pop, at: "@smaller+0.1s"}
```

- **Syntax**: `"@WORD"`, quoted (YAML reads a bare `@` as an error). `#N` picks the N-th time
  the beat says it (from 1); an offset in seconds ends the anchor, with its `s`:
  `"@gradient+0.3s"`, `"@gradient#2 -0.25s"`. A few words in a row (`"@learning rate"`) match
  as a phrase. Words match without case, accents and the punctuation around them (`"@voce"`
  finds "Você,"); a hyphenated word is one word (`"@K-Phi-3"`). An offset moves the moment
  within the beat (at most to its start and just before its end).
- **Every action** takes it: scene actions (`reveal`, `highlight`, `zoom`, `transform`, ...),
  `callout`, `sfx`, `particles`, the stage's actions (`walk_to`, `jump`, `emote`, `gesture`,
  `react`, ...) and the host's. The `lower_third` overlay's `at` takes one too (table in
  [Overlays](#overlays)). A scene's `sfx:` list stays in seconds; for a sound on a word use the
  beat's `sfx` action. A scene's own step can wait for a word too where the scene leaves it to
  a `reveal` action: [`code_morph`](#code_morph) morphs to `version2` on `{reveal: version2, at: "@word"}`,
  [`terminal`](#terminal) shows `output2` (or types `command2`) on `{reveal: output2, at: "@word"}`,
  [`function_plot`](#function_plot) draws a tangent on `{reveal: tangent1, at: "@word"}` and moves a dot on
  `{trace: dot1, to: 2, at: "@word"}` (a point, a vector and the [`number_line`](#number_line)'s points too),
  and [`bar_chart`](#bar_chart) / [`line_chart`](#line_chart) change their values on
  `{reveal: change1, at: "@word"}` (a line's cursor sweeps on `{trace: series1, to: 4, at: "@word"}`).
- **Where the time comes from**: the beat's MP3 once `vidgen tts` has made it (the word timings
  the TTS gives, as ElevenLabs and Kokoro do; else the words spread over the speech in the MP3,
  by syllables), the same timings as the karaoke captions. Before there is any audio, an
  estimate from the text over the word-count length (`narration.words_per_second`), so
  `vidgen validate`, `direct`, `storyboard`, `lint` and drafts use the word's moment already.
  A word the [pronunciation](#pronunciation-pronunciation) respells is still found by its written form.
- **Errors**: `vidgen validate` names the beat and the words like the one written:
  `scenes[0].beats[1]: actions: callout item2 at '@downn': beat 'steps_b2' does not say "downn"
  (words like it: down)`, or `says "gradient" 2 times, so there is no #3`.
- **Translations**: a beat whose text a `translations:` file replaces says other words, so its
  actions keep the moment the source text's word has (as a fraction of the beat).
- **Checked by lint**: [`vidgen lint`](#lint-vidgen-lint)'s `said_before_shown` rule warns when
  the narration names a label on screen (a node, a callout, a stage) more than 1.5 s before it
  appears; the usual fix is a `reveal` (or the `callout`) on that word.

## Overlays

Overlays are drawn **on top of the scenes and fixed to the screen**: a lower third introducing a
speaker, a logo in a corner, a progress bar, the current chapter, captions of the narration. They are listed once for the whole video and appear on every scene
they apply to; the scene's camera moves (a [`zoom`](#beat-actions)) and its fades (the fade-out
at a scene's end) do not touch them, and they look the same on both sides of a cut. They are
drawn into each scene's own render, so `vidgen storyboard`, the [layout dump](#layout-dump-buildlayoutscenejson)
and [`vidgen lint`](#lint-vidgen-lint) see them. `vidgen list-scenes` lists the overlay types
and their options (`--json`: `overlays`).

```yaml
overlays:
  - type: watermark                 # the whole video
    image: assets/logo.png
    corner: bottom_right
    opacity: 0.6
  - type: lower_third               # in scene "intro", 1.5 s after it starts, for 5 s
    scene: intro
    at: 1.5
    duration: 5
    name: Ada Lovelace
    title: Mathematician
    icon: user
  - type: watermark
    id: draft
    text: DRAFT
    corner: top_right
    from: results                   # from the start of scene "results"
    to: 95                          # to 95 s into the video
scenes:
  - id: intro
    type: title
    params: {title: "Engines"}
    beats: [{text: "..."}]
  - id: end
    type: end_card
    params: {title: "Thanks"}
    beats: [{text: "..."}]
    overlays: {watermark: false}    # no logo on the end card
```

Keys every overlay entry has (any other key is an option of its type):

| key | default | |
|---|---|---|
| `type` | required | `lower_third`, `watermark`, `progress_bar`, `chapter_indicator`, `captions`, or a [project overlay type](EXTENDING.md#9-overlays-custom-overlay-types) |
| `id` | the type | the name a scene's `overlays:` refers to; when several entries share a type and have no `id`, they are `<type>1`, `<type>2`, ... (ids must be unique) |
| `scenes` | `all` | the scenes it is drawn on: `all` or a list of scene ids |
| `exclude` | `[]` | scenes it is not drawn on |
| `from` | the video's start | where it starts: seconds in the video, or a scene id (that scene's start) |
| `to` | the video's end | where it ends: seconds in the video, or a scene id (that scene's end) |
| `reserve` | the type's: `false`; `captions` at the top or bottom `true` | keep the scenes' layouts clear of it: on every scene it is drawn on, the safe area (docs/EXTENDING.md "Layout regions") shrinks to leave its box free (plus 0.2 units), so built-in scenes lay out around it (the layout dump's `safe_area` too). Off by default for most types: a lower third shows for a few seconds over content laid out for the whole frame, and a watermark sits in the margin. The safe area is cut on every scene the overlay shows on at all, for the whole scene (a layout is built once): a lower third shown 4 s of a scene shrinks it all along (turn it off there with the scene's `overlays: {ID: {reserve: false}}`). An overlay hidden on a whole scene (the `chapter_indicator` on chapter cards, or outside its `from` / `to`) reserves nothing there. Several reserving overlays on one scene add up (captions + a lower third + a corner indicator leave a picture or clip noticeably smaller): reserve only what the scene must avoid all along |

**On a scene** (`overlays:` of the scene): `false` turns every overlay off there; a mapping
turns single ones off (`{draft: false}`) or overrides their options and `reserve` for that scene
(`{watermark: {corner: top_left}}`); an entry with a `type` that is no video-level id adds an
overlay to **this scene only** (no `scenes`, `exclude`, `from`, `to`):

```yaml
  - id: interview
    type: image
    params: {path: assets/guest.jpg, fit: cover}
    beats: [{text: "..."}, {text: "..."}]
    overlays:
      guest: {type: lower_third, name: Grace Hopper, title: Rear admiral, at: interview_b2}
```

**Timing.** An overlay's times are times in the video. Each scene is rendered on its own, so its
position in the video is *planned* before rendering: a narrated beat lasts its MP3's length
(else the word-count estimate) plus `narration.pad`, a scene its beats plus its fade-out, a
silent scene its `duration`. Built-in scenes keep to this exactly. A scene whose animations run
past its narration (lint `animation_overrun`) or an extension scene that times itself
differently shifts the scenes after it; `vidgen render` then warns that overlays timed in the
video (`from` / `to` in seconds or a scene, a lower third running over a cut) are off there.
Render the scenes again after `vidgen tts` so the plan uses the real audio.

**Lint.** Overlays are checked like the scene (text size, contrast, cut off by the frame), and
the rule `overlay_overlap` reports an overlay covering the scene's text or icons. Their own
placement is deliberate, so `safe_area` does not apply to them (a watermark sits in the margin),
and an overlay over the scene's text is `overlay_overlap`'s finding, not `text_overlap`'s or
`covered_text`'s. Like the scene, an overlay is checked only when settled: a lower third sliding
in or out at a beat's end is left alone. A type may exempt its objects from rules: the watermark
is faint on purpose and is not checked for `contrast`. In the layout dump, overlay objects have the key `overlay` (the
id) and paths starting with `overlay:<id>`, so `lint_ignore` can match them (`{rule:
overlay_overlap, object: "overlay:lower_third*"}`).

### `lower_third`

A name and a title on a plate in the lower third of the frame, sliding in at a moment of a scene
and out after `duration` seconds. It belongs to a scene (`scene`, default the first scene the
entry is drawn on) and starts `at` seconds into it or at one of its beats; it goes by the end of
that scene unless `across_cuts`. It is placed in the safe area (in 9:16 raised by 12 % of the
safe height: phone apps put their controls over the bottom), at least at the readable text size,
and slides in from the side it is aligned to (from below / above when centred). It makes way for
the scene's other overlays that reserve room: where it would meet bottom `captions` (or another
overlay with `reserve: true`) it moves above them (with the 0.2 gap), in 16:9 and 9:16 alike.

| param | default | |
|---|---|---|
| `name` | required | the main line (a person's or a place's name), bold, font role `heading` |
| `title` | none | the second line (role, affiliation) |
| `icon` | none | an icon left of the text |
| `scene` | first scene drawn on | the scene it belongs to; it must be one the overlay is drawn on |
| `at` | `0.5` | when it starts: seconds after its scene's start, a beat id of that scene (the beat's start), or a word its narration says: `"@Ada"` (the scene's first beat that says it; `#2` its second time in the scene) or `"intro_b2@Ada"` (in that beat), with an offset (`"@Ada-0.2s"`) |
| `duration` | `5.0` | seconds shown, slide in and out included |
| `across_cuts` | `false` | stay on over the following scenes (those the entry is drawn on) until `duration` is over; default: gone by the end of its scene |
| `align` | `bottom_left` | `bottom_left`, `bottom`, `bottom_right`, `top_left`, `top`, `top_right` (in the safe area) |
| `max_width` | `0.6` | widest it may be, share of the safe width (9:16: the whole width); longer text wraps |
| `color` | `primary` | accent bar and icon |
| `background`, `background_opacity` | `surface`, `0.92` | the plate |
| `name_color`, `title_color` | `text`, `dim` | |
| `name_size`, `title_size` | `body`, `caption` | |
| `enter`, `exit` | `0.5`, `0.4` | seconds of the slide in and out |

### `watermark`

A logo (an image from the project), an icon or a short text in a corner of the frame, faint and
fixed, over the whole video or the part `scenes` / `from` / `to` give. It sits `inset` from the
frame's edges (in the margin, outside the safe area, at the default size), so scenes need not
avoid it; it is not checked for contrast.

| param | default | |
|---|---|---|
| `image` | none | image file relative to the project (`assets/logo.png`); exactly one of `image`, `text`, `icon` |
| `text` | none | a short text instead |
| `icon` | none | an icon instead |
| `corner` | `bottom_right` | `top_left`, `top_right`, `bottom_left`, `bottom_right` |
| `opacity` | `0.6` | of the whole watermark |
| `size` | `0.06` | height of an image or icon, share of the frame's shorter side (an image is at most 30 % of the frame wide) |
| `text_size` | `caption` | size of a text watermark |
| `color` | `text` | colour of a text or icon watermark |
| `inset` | `0.025` | distance from the frame's edges, share of the shorter side |
| `fade` | `0` | seconds it fades in and out where a `from` / `to` starts and ends it (`0`: no fade) |

### `progress_bar`

A thin bar along the top or bottom edge of the frame that fills up as the video plays: the
share of the whole video played so far, continuous across cuts. With `chapters` (default),
small gaps split it at the [chapters](#chapters)' starts, as video players mark them. It sits
on the frame's edge, outside the safe area, so scenes need not avoid it. Use `from` / `to`
or `exclude` to leave it off the title or the end card; it still counts the whole video.

| param | default | |
|---|---|---|
| `position` | `top` | `top` or `bottom` edge (in 9:16 phone apps cover the bottom) |
| `thickness` | `0.006` | height, share of the frame's shorter side (at least 2 pixels) |
| `color` | `primary` | the played part |
| `track_color`, `track_opacity` | `dim`, `0.35` | the part still to come (`0`: hidden) |
| `opacity` | `1` | of the played part |
| `chapters` | `true` | gaps at chapter starts |
| `inset` | `0` | distance from the frame's edge, share of the shorter side (`0`: flush) |

### `chapter_indicator`

A small label in a corner naming the current [chapter](#chapters): "2 · Results" (the number in
`number_color`), or "2/5 · Results" with `total`. When the chapter changes it cross-fades to
the next; it fades out before a chapter card and in after it. It is hidden before the first
chapter and on the `chapter` cards themselves (they say it already; `on_chapter_cards: true`
shows it there too). A title longer than `max_width` is shortened with "…". It sits `inset`
from the frame's corner; at the default size it reaches a little into the safe area, so give
it `reserve: true` (scenes keep clear of it) unless the scenes leave that corner free.

| param | default | |
|---|---|---|
| `corner` | `top_left` | `top_left`, `top_right`, `bottom_left`, `bottom_right` |
| `number` | `true` | show the number (as written, else the chapter's position) |
| `total` | `false` | show the position out of the count ("2/5") instead of the number |
| `separator` | `" · "` | between number and title |
| `size` | `caption` | text size (at least the readable size) |
| `color`, `number_color` | `text`, `primary` | title, number |
| `opacity` | `0.85` | of the label |
| `background`, `background_opacity` | none, `0.85` | a plate behind the label (e.g. `surface`) for pictures reaching the corner |
| `max_width` | `0.4` | widest it may be, share of the frame's width (in 9:16 twice that, at most 0.85) |
| `inset` | `0.025` | distance from the frame's edges, share of the shorter side |
| `fade` | `0.4` | seconds of its fades and of the cross-fade at a chapter change (`0`: cut) |
| `on_chapter_cards` | `false` | also show it on `chapter` scenes |

```yaml
overlays:
  - type: progress_bar
    exclude: [intro]                # not over the title
  - type: chapter_indicator
    total: true                     # "2/5 · Results"
    reserve: true
```

### `captions`

The narration **burned into the video** as captions, in the theme's font and colours (the
`<output>.srt` file is written either way; this puts the text into the picture, for videos
watched without sound). Off unless listed. Two styles:

- `subtitles` (default): one or two lines at a time on a plate, like the SRT.
- `karaoke` (alias `words`): a few big bold words at a time, the word being spoken in the
  `highlight` colour with a small scale pop — the look of vertical / social videos.

**Cues.** Each beat's text is cut into cues at natural phrase boundaries, the same way as the SRT
(which now uses the same cutting, with widths in characters): breaks go after a sentence, then
after a comma, semicolon, colon or dash, then before a conjunction ("and", "which"...) or a
preposition, never right after an article or preposition ("the | model"); a new sentence starts
a line; fuller cues and balanced lines are preferred. A cue appears when its first word is spoken
and stays until the next one; a beat's last cue stays through the pause after it (until the next
beat, the scene's last until the scene ends). Silent scenes show none.

**Word times** come from the MP3's character timings when `vidgen tts` stored them
(`voice.timestamps: true`, `audio/<beat_id>.align.json`); otherwise they are estimated: the
beat's speech (its MP3 with the leading and trailing silence cut off, or the word-count estimate
without audio) is shared among the words by syllables (numbers by their spoken words, acronyms
by letters), with pauses after sentence ends and commas. The SRT uses the same word times.

**Placement.** In the safe area at the `bottom` (in 9:16 raised by 12 % of the safe height:
phone apps put their controls over the bottom), `top` or `center`, centred, at least the
readable text size, the text no wider than `max_width`. At the top or bottom it **reserves** its
band (`max_lines` lines high) by default, so the scenes lay out above / below it; centred it
does not (lint's `overlay_overlap` reports scene text under it; or set `reserve: false` and
check with lint). Scenes without narration reserve nothing. A `lower_third` on the same scene
moves above bottom captions instead of under them. The plate's opacity is raised when
needed so the text keeps lint's contrast ratio (`lint.rules.contrast.min_ratio`) over anything
behind it; a highlight that would not read on the plate is replaced by another theme accent (with
a warning).

| param | default | |
|---|---|---|
| `style` | `subtitles` | `subtitles` or `karaoke` (`words`) |
| `position` | `bottom` | `bottom`, `top` or `center` (of the safe area) |
| `size` | `body`; karaoke `title` | text size (at least the readable size) |
| `bold` | `false`; karaoke `true` | |
| `max_lines` | `2` | lines per caption (1-3) |
| `max_words` | none; karaoke `3` | words per caption |
| `max_width` | `0.8`; karaoke `0.9` | widest the text may be, share of the safe width (9:16: `1`) |
| `color` | auto | text colour; default the theme's `text` or background colour, whichever reads better on the plate |
| `highlight` | `highlight` | karaoke: the word being spoken |
| `pop` | `1.12` | karaoke: scale of the word being spoken (`1`: none); limited so it never touches its neighbours |
| `background`, `background_opacity` | `surface`, `0.8` | the plate; `background: null` for none (the text then gets an outline in the background colour) |
| `lift` | `0`; 9:16 `0.12` | bottom captions: raised by this share of the safe height |
| `speakers` | `subtitles.speakers` | who speaks ([multiple voices](#multiple-voices-voices)): `name` (a `Label:` tag in the speaker's colour before a beat whose speaker changed), `color` (each speaker's words in its colour), `both`, or `off` |

**Speakers.** With [named voices](#multiple-voices-voices), `speakers: name` puts the speaker's
label (`Guest:`) at the start of the first cue of each beat whose voice differs from the beat
before (the tag is glued to the first word, never a cue of its own, and is not highlighted in
karaoke); the base voice is tagged only if `voice.label` is set. `color` draws each speaker's
words in its colour (`voices.<name>.color`; default the palette colour of the voice's place in
`voices:`; the base voice: `voice.color` or the caption colour); the plate's opacity rises until
every speaker's colour reads, and a colour that cannot reach the contrast ratio even on an opaque
plate falls back to the text colour (warning). Karaoke shows only a few words per cue, so the tag
is brief there: prefer `color` or `both`.

```yaml
overlays:
  - type: captions                  # subtitles at the bottom; scenes keep clear of them
variants:
  social:                           # 9:16 with karaoke captions
    format: {width: 1080, height: 1920}
    overlays: [{type: captions, style: karaoke}]
voice:
  timestamps: true                  # exact word times from ElevenLabs (vidgen tts)
```

## JSON Schema (`vidgen schema`)

`vidgen schema [PROJECT]` prints a [JSON Schema](https://json-schema.org) (draft 2020-12) of
`video.yaml` for the project's scene types: the built-ins plus its extensions (without a
PROJECT and no config file in the current folder: the built-ins only). Editors (e.g. the YAML
language server: `# yaml-language-server: $schema=video.schema.json` on the first line) and AI
agents can check a config with it before running `vidgen validate`:

```
vidgen schema > video.schema.json          # the whole config
vidgen schema --scene bar_chart            # one scene type's params
vidgen schema --all                        # one item of `scenes`, with every type's params
```

What the schema checks: every key and type of this reference (unknown keys are errors);
`scenes[].type` is one of the registered types and `scenes[].params` is checked against that
type's params (`if`/`then` per type: required params, types, `Literal` values, ranges, nested
models); a type's fixed beat count (`minItems`/`maxItems` of `beats`); the silent-scene rule
(`duration` exactly when there are no beats); beat `actions` in both forms (the action name is
one of the registered actions and the options are that action's); even `width`/`height`; and the bodies of
`variants` (partial configs: the same keys, none required). Color and size params accept a
`#hex` color / a positive number or a token name of the project's theme (defaults, extension
defaults, `theme.colors`/`theme.sizes` of the base config and of every variant); such
properties carry `"x-vidgen-theme": "color"` or `"size"`. `theme.preset` is an enum of the
built-in presets and those the project registers, `theme.code_style` of the installed Pygments
styles. Descriptions come from the field docs (the same text as `doc` in
`vidgen list-scenes --json`).

What only `vidgen validate` checks: unique scene and beat ids, action targets and `until`
beats, files referenced by params
(images, code, logos), the checks written in Python (`validate_project`, pydantic validators,
e.g. "values has one entry per label") and loading the extensions. A schema-valid config can
still fail `vidgen validate`. The reverse happens only for values vidgen converts, such as
the string `"30"` for a number: write values with their real type (tests check both
directions on the examples and on common mistakes).

The schema is generated for the project as it is now: regenerate it after adding scene types,
theme tokens or variants. If `video.yaml` is invalid, `vidgen schema` still works (that is
when it is most useful): it uses the file's `extensions` and `theme` as far as they are valid
and prints a warning. `--scene` with an unknown type is an error (exit code 1).

## Parallel renders (`--jobs`)

`vidgen render`, `storyboard`, `lint`, `thumbnail`, `slides` and `gallery` take `--jobs N`
(`-j N`): the number of scenes rendered at once, each in its own worker process (default 1).
`--jobs auto` lets vidgen choose:

    jobs = min(available memory ÷ 1.5 GB, CPU cores), at least 1

- **Available memory** is what the system can give without swapping; swap is never counted.
  Linux: `MemAvailable` of `/proc/meminfo`, or less when the process runs in a cgroup with a
  memory limit (`memory.max` in cgroup v2, `memory.limit_in_bytes` in v1, of its group or a
  parent group): the limit minus what the group uses, not counting file cache the kernel can
  drop. Windows: `ullAvailPhys` of `GlobalMemoryStatusEx`. macOS: free + inactive pages of
  `vm_stat`. Elsewhere, or when the reading fails, `auto` means 1.
- **CPU cores** are the cores the process may run on (its CPU affinity on Linux).
- **1.5 GB per job** is about twice the largest peak measured for one scene render (the Manim
  worker and its ffmpeg): 0.30 GB for a cartoon scene at the 640x360 preview, 0.83 GB at
  1920x1080 (`examples/cartoon-muffin-mystery` and `cartoon-rain-check`). A video larger than
  1080p, or scenes with large pictures or video clips, can need more: give `--jobs N` yourself.

The command prints its choice and the reason before it starts, e.g.

    jobs: 2 (auto: 6.2 GB available (/proc/meminfo MemAvailable) / 1.5 GB per job = 4, 2 CPU cores)

and with `--json` adds it to the document as `jobs` ([JSON output](#json-output---json)). The
MCP tools that render take `jobs: "auto"` too. `vidgen tts` with Kokoro (about 2.2 GB) has no
`--jobs` and should run alone, not next to a render.

## Frame stills (`vidgen render --frames`)

`vidgen render --frames` also saves PNG stills of the render, so you (or an AI agent, which
cannot watch a video) can check what is on screen without playing it. `--frames` takes one
still per beat: its **last frame**, i.e. what is on screen when the narration of the beat (and
its `narration.pad`) is over. `--frames-per-beat N` takes N evenly spaced stills per beat, the
last one again at the end (N=3: after a third, two thirds and all of the beat). A silent scene
counts as one beat lasting `duration` minus the scene's fade-out, so its last still is taken
before the fade. A [`stage`](#stage) scene also gets a **mid-action still** half-way through each
`walk_to`, `run_to`, `enter`, `exit`, `gesture`, `jump`, `keyframes` and `move_along` (at most 3 per beat,
none within 0.4 s of another still of the beat). Stills are off by default; they work with `--preview`, `--variant`, `--scene`
and `--jobs`. They are taken from Manim's renderer while it writes the video (the same pixels
as the video frame, before compression), so they do not change the video or its timings.

Files, in `build/<final|preview>[_<variant>]/frames/`:

```
frames/
  index.json            # every still of the video
  <scene>/
    index.json          # the scene's stills
    <beat>-<k>.png      # still k (1..N) of a beat; <scene>-<k>.png for a silent scene
    <beat>-m<frame>.png # a mid-action still (stage scenes), named by its frame
```

`<scene>/index.json`: `{scene, per_beat, width, height, fps, frames}`; `frames` lists, in time
order, `{beat, k, n, frame, time, path}`: the beat id (`null` for a silent scene), the still's
number within its beat (`k == n` is the end of the beat), `n` = stills per beat, the frame's
0-based index in the scene's video, its time in seconds from the scene start (`frame / fps`)
and the PNG file name. A mid-action still has `k` 0 and a key `mid` naming the actions it shows
half-way (`"walk_to pip"`, several joined by `, `); the [layout dump](#layout-dump-buildlayoutscenejson)
marks it the same way, `vidgen lint` skips it (it checks beat ends) and `vidgen slides` leaves it out.

`frames/index.json`: `{title, variant, preview, format, per_beat, vidgen, scenes}`; each scene
is `{id, start, duration, frames}` (`start` in the video) and each still is as above with
`time` in the **video** (scene start + time in the scene), `scene_time` (time in the scene)
and `path` relative to `frames/` (`<scene>/<file>.png`); each scene also has `layout`, its
layout file relative to `frames/` (`../layout/<scene>.json`, see below) and `activity`, its
activity file (`../activity/<scene>.json`, see below). The beat texts are in
`build/.../timings.json`.

Every scene render deletes the scene's old stills, and every `vidgen render` deletes
`frames/index.json` (it is rewritten when stills are requested), so stills never belong to an
older render. With `--scene ID --frames`, scenes that would be reused but have no stills at
this count are rendered again.

## Layout dump (`build/.../layout/<scene>.json`)

Whenever stills are taken (`--frames`, `--frames-per-beat N`, `vidgen storyboard`), the same
frames are also described as data: for each still, every **visible** object on screen with its
position in pixels, size, colours and opacity: the input of [`vidgen lint`](#lint-vidgen-lint)
(text off the frame or outside the safe area, overlapping text, text too small, low contrast,
too many words); you or an agent can read it directly too. It costs a few milliseconds per still and is deleted
and rewritten with the stills, so it always describes the current render.

File `build/<final|preview>[_<variant>]/layout/<scene>.json`:

```
{version: 1, scene, type, width, height, fps, per_beat,
 px_per_unit,              # output pixels per Manim unit (camera not zoomed)
 background: "#0E1116",    # the theme background
 safe_area: [x0, y0, x1, y1],  # frame minus the scene's margins (margin_x/margin_y), in px
                               # (and minus overlays with reserve: true)
 frames: [{beat, k, n, frame, time,     # the same keys as the stills index
           still: "../frames/<scene>/<file>.png",
           narrating,             # beat-end stills: whether the beat's narration is heard at
                                  # this time (false in the pad after it)
           camera: {center: [x, y], width, height,    # the camera frame in Manim units
                    zoom},                    # frame width / camera width: > 1 while zoomed in
           shot: {kind, subjects, near},      # a stage's shot on screen (shot:), absent outside
                                              # shots; near: over_shoulder only
           objects: [...],
           overlays: [{id, type, settled, skip}]}]}   # overlays drawn in this still; settled:
                                     # false while one slides or fades; skip: lint rules not
                                     # applied to its objects
```

Coordinates are output-frame pixels: origin at the top-left corner, y downwards, the frame
spans `[0, width] x [0, height]`; boxes are `[x0, y0, x1, y1]` (1 decimal) and may lie partly or
wholly outside the frame. A moving or zoomed camera (`MovingCamera`) is taken into account.

Each object:

| key | meaning |
|---|---|
| `id` | `m1`, `m2`, ...: the same Python object keeps its id in every frame of the scene |
| `kind` | `text` (`Text`, `MarkupText`, `Paragraph`), `code` (the text of a `Code` listing), `math` (`Tex`, `MathTex`), `number` (`DecimalNumber`, `Integer`), `shape` (one path), `group` (a group of shapes with no text or image inside, e.g. an axis' ticks), `image`, `icon` (an icon from `icon()`: one object, not one per path), `vector` (a vector picture, an SVG: one object, not one per path), `character` (a cartoon character: one object named after it, its box covering every part), `host` (the [host](#a-host-beside-any-scene-host) beside the content: one object named after its character, its box covering the floor line too), `pointer` (a host's pointer line, `host_point` with `line: true`: one object named after the host), `prop` (a prop on a stage, built-in or SVG: one object named after it), `particles` (a field of [particles](#particles): one object named after its kind), `motion_effect` (dust, speed lines, impact stars or a whoosh of a [motion effect](#motion-effects-motion_effects): one object named after its kind, with `motion_effect` and `effect_of`) |
| `class` | the Manim class |
| `path` | where it sits: parent groups from the top-level mobject down, each `Class[index]` (index among its parent's submobjects; top level: in the scene), or the name the scene gave it |
| `name` | the scene attribute that holds it (`self.title = ...`) or a `Mobject.name` set by the scene, else `null` |
| `bbox` | the box of its visible parts, stroke included |
| `opacity` | the highest opacity of its visible parts (fill, or stroke when it has one); a fade-in in progress shows here |
| `z`, `order` | Manim `z_index`, and the drawing position (higher is drawn later, i.e. on top) of its top-most part |
| `parts` | number of visible parts (glyphs, paths) |
| text kinds only: `text` | the characters (markup tags removed; the LaTeX source for `math`) |
| `font_px` | the 75th percentile of its visible glyphs' heights in output pixels: about the cap height (≈ 0.7 em) for mixed-case text, the x-height for lowercase text without ascenders; a rotated line of text is measured across its direction |
| `rotation` | the angle of a line of text in degrees, counter-clockwise (`90` for an axis title turned upwards); `0` when level, for several lines and for math |
| `color`, `colors` | the most common glyph colour, and all of them (most common first) |
| `backdrop` | the most common colour of the frame inside its box, ignoring its own colours: what the text is read against (`null` when off-frame) |
| other kinds: `fill`, `stroke` | `{color, opacity}` / `{color, opacity, width_px}` of the largest visible part, or `null` |
| `icon` only: `icon` | the icon's name (`cpu`); its `bbox` is what it draws, not its padded design box |
| `character` only: `walked_in` | the beat in which its last walk (`walk_to`, `enter`) ended; absent before it walks (read by the `walk_overlap` rule) |
| `character` only: `facing`, `speaking` | `left`, `right` or `front`; whether its lip sync runs (it speaks this beat) |
| `character` only: `depth` | how far back it stands on the stage (0..1), absent at the front (0); read by `character_overlap` and `walk_overlap` |
| `character` only: `face` | the box of its head (with hair and ears), absent without a `head` part |
| `character` only: `viseme`, `looked_at`, `passage` | when they apply: the viseme its lip sync shows (`rest` between words), the `to` of its last `look_at` (a name, a mark or `camera`), and `enter` / `exit` while it walks in or out |
| `character` only: `holding` | the props in its hands, `{hand: prop}` (`{"left": "ball"}`); absent while it holds nothing ([Props in hands](#props-in-hands)) |
| `character` only: `sitting_on`, `leaning_on` | the prop it sits or leans on; absent while it stands ([Sitting and leaning](#sitting-and-leaning)) |
| `character` only: `riding` | the vehicle it rides; absent while it is on foot ([Vehicles](#vehicles-get_in-ride_to-get_out)) |
| `host` only | the [host](#a-host-beside-any-scene-host): `facing`, `speaking`, `face`, `viseme` as for a character, plus `side` (`left` / `right`: where it stands now, after a `host_move` too), `below` (`true` when it stands under the content) and `pointing_at` (the target it points at, while it does) |
| `prop` only: `held_by`, `hand` | the character holding it and which hand; absent while it stands somewhere. A held prop is its own object, drawn right after its holder (an open umbrella right before it); its box is not part of the character's |
| `prop` only: `shape` | the shape a prop with several shows: an umbrella's `closed` or `open`; absent for other props |
| `prop` only: `prop`, `depth`, `raised`, `flat` | its kind (a built-in prop's name, or `svg`); how far back it stands (0..1, absent at the front); `raised: true` when it is lifted (`lift`) or hangs on a wall, `flat: true` when it lies on the floor (a rug), each absent otherwise; read by `prop_overlap` |
| speech bubbles only: `bubble` | the name of the character speaking (on the bubble's shape and its text) |
| `effect` only: `effect`, `effect_of` | an [effect symbol](#effect-symbols-effect) over a head (one object of kind `effect` named after the symbol): the symbol (`idea`) and the character it marks |
| overlays only: `overlay` | the id of the [overlay](#overlays) it belongs to; overlay objects come after the scene's, their `path` starts with `overlay:<id>` and they are measured as drawn: fixed to the screen whatever the camera does |

An object is one text mobject (not one per glyph), one path, one image, or one group of shapes.
Parts with opacity 0 are not visible: they do not count in the box, and an object with no
visible part is not listed. `text` is the string the mobject was created with; Manim's
`become()` and `Transform` change the glyphs but not that string, and while
`TransformMatchingShapes`/`TransformMatchingTex` run, the moving glyphs are shapes.

## Activity file (`build/.../activity/<scene>.json`)

Written with the stills and the layout dump (and deleted with them): what happens in the scene
over time, the input of `vidgen lint`'s timing rules. Recording it costs about 1.3 ms per
frame of the render (a sampled comparison with the previous frame).

```
{version: 1, scene, type, fps,
 frames, duration,         # frames written, seconds
 pad,                      # narration.pad
 silent: {duration, busy} | null,   # silent scene: its duration, and how long its code ran
 beats: [{id, start, end,  # scene seconds; end = start + narration length d
          busy,            # seconds the beat's own code (animations, waits) took; more than
                           # d + pad means the beat ran past its narration
          source,          # "audio" (d from the MP3) or "estimate" (from the word count)
          text,
          window,          # only when the next beat overlaps this one: seconds until it starts
          overlap,         # only on a beat with overlap / interrupt: seconds it starts early
          interrupt}],     # only when true
 plays: [{start, end, beat, animations: ["Write", ...], wait, requested}],
 motion: {step, grid: [w, h], level, changes: [[frame, fraction], ...]},
 overlap_out}              # last frames a crossfade into the next scene covers (0: none)
```

`plays` lists every `self.play(...)` and `self.wait(...)` (`wait: true`) with the beat being
narrated (`null` outside `narrate`) and the animations' class names (`animate` for
`mobject.animate`, groups with their parts); `requested` is the run time `play_steps` wanted
when it had to shorten an animation to fit the beat, else `null`. `motion.changes` lists the
frames that differ from the previous frame: `fraction` is the part of the frame's sample points
(every `step`-th pixel, `grid` points, at most 180 on the shorter side) whose colour changed by
more than `level` (0-255); frames not listed are identical to the one before.

## Lint (`vidgen lint`)

`vidgen lint [PROJECT]` checks what is on screen at the **end of every beat**, and how the
scenes play over time, and reports problems an author cannot see without watching: text cut
off by the frame edge or in the margins, overlapping text, shapes drawn over text, text too
small for the frame, low contrast and too many words at once (**layout rules**); narration too
fast or too slow, nothing moving for a long time, animations running past their narration or
squeezed into a too short beat (**timing rules**); narration heard differently from its text
(`readback`, from the transcripts of [`vidgen readback`](#readback-vidgen-readback)) and, with
`--readback`, words heard unclearly (`unclear_speech`). It reads the
[layout dump](#layout-dump-buildlayoutscenejson) of the beat-end stills and each scene's
[activity file](#activity-file-buildactivityscenejson); scenes whose stills are current (from
`vidgen render --frames` or `vidgen storyboard`, any `--per-beat`) are reused, the others are
rendered first with one still per beat (preview format unless `--final`; reuse works as for
the [storyboard](#storyboard-vidgen-storyboard)). Only beat-end stills are checked by the
layout rules: mid-beat stills show animations in progress (half-faded or moving objects),
which would only add noise.

```
$ vidgen lint my_video
lint: 11 scenes, 28 beat-end stills (preview 854x480)
picture:
  warning safe_area         picture_b2 @ 7.2s: text 'Images can slowly zoom and pan' is outside the safe area at the bottom (12 px into the bottom margin)
          still: my_video/build/preview/frames/picture/picture_b2-1.png
0 errors, 1 warning, 0 info
```

Each finding names the scene, the beat at whose end it was seen (`+N more beats` when the same
problem stays on screen), the rule, a message with the measured value and the limit, and the
**still** to open to see it. Timing findings name the beat concerned and the scene time where
the problem starts; their still is the end of that beat. The same problem with several objects of one group (an axis' tick
labels, several texts in the same colour) or with the same text in several places (a label of a
repeated component) is reported once (`also N more like it`).

Options:

| option | |
|---|---|
| `--scene ID` | only this scene (repeatable) |
| `--rule NAME` | only this rule (repeatable) |
| `--variant NAME` | lint a variant (e.g. the vertical one) |
| `--preview` / `--final` | preview format (the default) or the final format |
| `--fail-on SEVERITY` | `error`, `warning`, `info` or `never`; overrides `lint.fail_on` |
| `--jobs N\|auto` | scenes rendered in parallel ([`auto`](#parallel-renders---jobs): from the available memory and CPU cores) |
| `--force` | render the selected scenes again even if their stills are current |
| `--readback` | also run `unclear_speech`: the selected scenes' beats are transcribed as [`vidgen readback`](#readback-vidgen-readback) does (cached transcripts reused, progress on stderr; slow the first time, and paid with `stt.provider: elevenlabs`). `--rule unclear_speech` implies it |
| `--json` | print every finding as JSON (below) |

**Exit code**: 1 when a finding is at least as severe as `fail_on` (default `error`), else 0;
with `--fail-on never` it is 0 whatever is found (and 1 only if the command itself fails).

**Theme contrast.** Like `vidgen validate`, `vidgen lint` first checks the theme itself (text and
`dim` on the background and `surface`, accents and palette on the background; see
[Theme presets](#theme-presets)) and prints pairs below WCAG AA as `warning: theme contrast:
...` (JSON: `warnings`). They are not findings and never fail the command; they are skipped
with `--rule` other than `contrast` and when `lint.rules.contrast.severity` is `off`.

**Rules.** Sizes are fractions of the frame's **shorter side** (the height of a landscape
video, the width of a vertical one), so the same thresholds hold for the 480p preview and the
1080p video, and for 16:9 and 9:16 (a phone shows either orientation with its shorter side
across the screen's width). Objects fainter than `lint.min_opacity` are ignored by every rule.

| rule | default severity | finds |
|---|---|---|
| `off_frame` | error for text, warning for other objects | an object cut off by the frame edge by more than `tolerance`. Not reported: objects wholly outside (not visible), and non-text objects running from edge to edge on the side they cross (a full-frame image with `fit: cover` or Ken Burns, a background, a band or divider): those bleeds are intentional; nothing while the camera is zoomed in or looks away from the frame's centre (`zoom`, `pan`, `follow`, a wide `stage`); never [particles](#particles), which cross the edges on purpose, nor a [level's tiles](#the-camera-on-a-level-follow) (the camera crops them), nor characters (`off_stage`'s) |
| `safe_area` | warning | text inside the frame but in its margins (the scene's `margin_x`/`margin_y`, `safe_area` in the layout dump, smaller where an overlay has `reserve: true`) by more than `tolerance`; not checked while the camera is zoomed in or moved (`pan`, `follow`), nor for [overlays](#overlays) (their place is deliberate) |
| `text_overlap` | error | two texts whose boxes overlap by at least `min_overlap` of the smaller box (the same text drawn twice in the same place is not reported) |
| `covered_text` | warning | a shape or image drawn **after** (on top of) a text whose colour shows in at least `min_covered` of the middle of the text's box, measured on the still's pixels. Not reported: shapes drawn before the text (plates, highlight bands, a code window), the text's own parent group, shapes fainter than 0.3, and shapes in the text's own colour (a strike-through) |
| `label_spacing` | warning | a **label on its own plate** — a filled rounded shape without an outline, not in the background colour, drawn just behind one text and hugging it (a callout label, a tag) — closer than `min_gap` of the shorter side to another text (a bar's value, the title, a neighbour's label): it reads as part of that text. The text on the plate itself, texts inside the plate, lone symbols (a bullet) and the text framed by the callout's own mark (an outline in the plate's colour: a `box` tag sits on its edge by design) are not checked; cards, table rows, cells and code bands (several texts, or much larger than their text) are not labels |
| `min_font` | warning; error below `error_size` | text whose cap height is below `min_size` of the shorter side. The cap height is the layout's `font_px` corrected for the text's letters (`font_px` of all-lowercase text is about its x-height); a lone symbol (`+`, `·`) is not checked |
| `contrast` | warning | text whose WCAG contrast ratio with its `backdrop` is below `min_ratio` (4.5, WCAG AA), `large_ratio` (3) for text with a cap height of at least `large_size`, or `dimmed_ratio` (2) for text faded on purpose (opacity below 1, e.g. previous bullets); the text colour is blended with the backdrop at the text's opacity, every colour of a multi-coloured text is checked. A code listing's line numbers are not checked |
| `max_words` | warning | more than `max_words` words (tokens with a letter) of visible `text` objects in one still; code and math do not count |
| `overlay_overlap` | warning | an [overlay](#overlays) whose box (all its objects) covers at least `min_overlap` of the box of a scene text or icon. `text_overlap` and `covered_text` leave an overlay over scene text to this rule; overlays of a type with a `lint_skip` (the watermark: `contrast`) are not checked by those rules |
| `host_overlap` | warning | the [host](#a-host-beside-any-scene-host) (its figure and floor line) sharing at least `min_overlap` of the smaller of two boxes with a scene object (text, shape, picture, character...) or an overlay's object (a caption, a lower third). Not reported: a scene object whose box holds the host's whole box (a backdrop: a full-frame picture, a band), particles, motion effects, the host's own pointer line and effect symbol. `covered_text` leaves the host over text to this rule. Scenes lay out beside the host, so a finding means something was drawn outside the scene's regions (a project scene type that ignores `self.safe_area`, a `zoom`): make the host smaller (`size`), move it (`side`, `place`) or `host: false` on that scene |
| `walk_overlap` | warning | a character whose walk (`walk_to`, `enter`) ended in the still's beat sharing at least `min_overlap` of the narrower character's width with another character: it stopped on the other's place. Only characters that walked in that beat are checked (the layout dump's `walked_in`), and not two 0.15 or more apart in depth (one behind the other); see [Moving](#moving) |
| `off_stage` | warning | a character with at least `min_hidden` of its box outside the view (the frame, or what a `pan` / `follow` shows) and part of it inside. Not reported: characters wholly outside (waiting to enter, gone), while it walks in or out (`enter`, `exit`), and while the camera is zoomed in. In a [shot](#shots-shot) (other than `wide`) only the characters it frames are checked, wholly outside too: their face in a `medium`, `over_shoulder` or `closeup` shot, their whole box in a `two_shot`; the near character of an `over_shoulder` shot and characters the shot does not frame may be cut. Fix: put it on a mark inside the view, or pan to it (in a shot: keep it from walking out, or frame another shot) |
| `character_overlap` | warning | two characters at rest whose boxes share at least `min_overlap` of the narrower one's width, at depths less than 0.15 apart (further apart one stands behind the other: [walking in depth](#walking-in-depth-and-the-front-view)). A character that walked in the still's beat is `walk_overlap`'s. Fix: marks further apart, or walk one away (across, or in depth) |
| `prop_overlap` | warning | two props standing on the floor whose boxes share at least `min_overlap` of the narrower one's width, at depths less than 0.15 apart: drawn over each other, like a [room](#rooms-room)'s door over the sofa against the wall. Not reported: a prop in front of another (depths 0.15 or more apart, like an armchair before the sofa), one lifted onto another (`lift`: a basket on the counter) or hanging on the wall above it (a picture, a clock), a rug under them, a held prop (the layout dump's `raised`, `flat`, `held_by`). Fix: another `at` for one of them (a door: its x in the room's `doors`), a smaller `scale`, or a `depth` that puts one in front |
| `bubble_overlap` | warning | a speech bubble (`say` with `bubble`) covering at least `min_overlap` of a character's face box (its speaker's too), of the smaller of two bubbles, or of an [effect symbol](#effect-symbols-effect)'s box. Fix: a shorter `bubble` text, the characters further apart, or the two lines (or the line and the effect) in different beats |
| `facing_away` | warning | a speaking character facing away from the one it talks to: the character it last looked at (`look_at`), else the nearest one; not checked after `look_at: camera` (it talks to the viewer). Fix: `turn`, `look_at: <listener>`, or swap their marks |
| `hidden_speaker` | warning | a speaking character with at least `min_hidden` of its face box covered by things drawn in front of it (a character or prop nearer the camera, a foreground layer, an overlay; not an effect symbol). The characters are drawn side-on and face left or right, so they never turn their back: this is the case where the viewer cannot see who talks. Fix: move one of them, or a smaller `depth` for the speaker |
| `small_speaker` | warning | a speaking character whose face (its head's box, as seen: a shot that frames it closer counts) is less than `min_face` (`0.075`) of the frame's shorter side tall: too small to read its face and lip sync. A character on a platform level is about `0.07` at `character_size: small` and `0.095` at `medium`. Fix: a `shot: closeup <name>` (or `medium`) for the beat, or larger characters ([`character_size`](#character-size-character_size)) |
| `mouth_without_voice` | warning | at a beat's end, after its narration (the pad), a character whose lip sync still shows a speech shape: its viseme track is longer than the beat's audio. Fix: `vidgen tts` again (the track and the audio are made together); in a custom scene, lip sync with `clock=self.beat_clock()` |
| `concept_colors` | warning | the video's [`terms:`](#one-colour-per-concept-terms) colours: more than `max_colors` different colours (reported once, on the first scene that draws them), a colour whose WCAG contrast on the theme background is below `min_contrast`, and a scene setting that colours a term otherwise: a `title`'s `highlight_color` on a highlight that says a term, a `line_chart` series' `color` on a series named after a term, an `equation_derivation`'s `colors` entry for a term's `tex`, a `function_plot` function's, area's, point's, vector's or mark's `color` or a `number_line` point's, interval's or jump's `color` when its name or label says a term, a `callout`'s `color` when its label says a term (on that beat). Scenes with `terms: false` are not checked. Fix: the term's colour, or leave the setting out |
| `look_alike` | warning | two generated characters on the video's stages whose [contrast](#a-random-cast-vidgen-cast) (silhouette, colours in the theme, accessories; 0 the same look, 1 fully different) is below `min_contrast`: viewers may not tell them apart. Reported once per pair, at the first beat of the scene where the later of the two first appears; the message names what they share, most weighty first, and what to change on the second. Characters drawn from an SVG file are not compared. Fix: another body, hair, species or clothes colour (the message says which), or `vidgen cast --random N` for a cast chosen to differ |
| `narration_speed` | warning; info without audio | a beat (of at least `min_words` spoken words) narrated at fewer than `min_rate` or more than `max_rate` words per second (`unit: words`) or characters per second (`unit: characters`: letters and digits). `unit: auto` counts words for the languages vidgen has a word rate for and characters for others; the default range is the video [language](#languages-and-translations)'s: English (also no `language`) 1.8-3.5 words/s, Portuguese 1.7-3.4, Spanish and French 1.8-3.6, Italian 1.8-3.5, German 1.5-3.1, characters 8-17/s; `min_rate` / `max_rate` set override it. With an MP3 the time is the speech in it (leading and trailing silence below -40 dB of its peak cut off). Words count as spoken: hyphens, dashes and slashes separate words (`K-Phi-3` is 3), a number counts one word per digit up to 3 per digit run, plus one per decimal point and symbol (`2.58` is 4, `15%` 3), an all-capitals acronym of 2-5 letters half a word per letter (`GPU` 1.5). **Without audio** the beat's length is the word-count estimate (`narration.words_per_second`), so the rate is only off when the text is (many numbers or acronyms) or the configured rate itself is implausible: reported as `info`, one finding per scene listing the beats |
| `dead_air` | warning | nothing on screen changes for more than `max_seconds` (a frame counts as changed when at least `min_change` of it changed, from the activity file's `motion`), narrated or not; the finding names the beat where the still picture starts and the beats it lasts through. Silent scenes are checked the same way: a silent card held longer than `max_seconds` without motion is reported. A still picture ends where a [crossfade](#transitions-transition) into the next scene starts blending it away |
| `animation_overrun` | warning | a beat whose code (animations and waits inside `narrate`) takes longer than its narration plus `narration.pad` (or, when the next beat [overlaps](#overlapping-lines-overlap-interrupt) it, than the time until that beat) by more than `tolerance` seconds: the next beat (and its audio) starts late, leaving silence. The message lists the animations still running when the narration ends. A silent scene whose animations take longer than its `duration` is reported the same way |
| `rushed_animation` | warning | animations that `play_steps` (and so `reveal` and most built-in scenes) had to shorten below `min_run_time` seconds because the beat is too short for its steps; a walk or a jump on a [platform level](#walking-and-jumping-on-a-level) sped up more than `max_speedup` times to fit its beat |
| `talked_over` | warning | a beat with [`overlap`](#overlapping-lines-overlap-interrupt) that starts speaking before whole words of the line before it are said: those words are spoken entirely under the new line (word times from the alignment, else estimated). The message names the words and the largest overlap that keeps them clear. With `interrupt`: words of a line with audio that the cut removes before they start (the interrupt should cut at most the end of the last word). Fix: a shorter `overlap`, or `interrupt: true`; for an interrupt, a shorter `overlap` or none |
| `readback` | warning | a beat whose MP3, transcribed by [`vidgen readback`](#readback-vidgen-readback), differs from its spoken text by a word error rate above `max_wer`; the message quotes the first differences and a suggested fix. Reads only the transcripts `vidgen readback` cached for the beats' current MP3s and the `stt:` settings (it never runs speech to text): nothing is reported until that command has run |
| `unclear_speech` | warning; info for doubtful words | only with `--readback`: each [word to check](#readback-vidgen-readback) of `vidgen readback` — a word heard with a probability below `min_probability` (info: below `doubtful_probability`), after a pause longer than `max_gap` seconds inside a sentence, or differently from the text — at its time (the beat's start + the word's time in the MP3), with the fix (a respelling in `pronunciation:`, another voice, speed or emotion). `value` / `limit` are the probability or the pause and its threshold |
| `said_before_shown` | warning | the narration names an on-screen **label** (a scene text of at most `max_words` words with a word that names something: a diagram node, a callout, a stage, an axis title) more than `min_lead` seconds before the label is on screen, and does not name it again when it shows. When it shows is known from the layout dump: it was not there at the still before the one that first shows it (the beat-end still of the beat before, or a mid-beat still of a storyboard), or at the time of the `reveal` / `callout` / `transform` action of its beat that shows it (a callout with that label, or an action [on a word](#actions-on-a-spoken-word) the label says). Words are compared without case and accents, with English plural and verb endings (`databases` = `database`, `moving` = `moves`), without stop words and numbers; a label of several words counts as named when all its words are said close together. Not checked: overlays (captions repeat the narration), speech bubbles, maths and code, numbers (a chart's values, tick labels, live values like `slope 0.50`), texts that another text on screen already says (the heading "How a cache works" before a `Cache` node). Word times come from the beat's audio (the alignment), else the estimate. Fix: show it on the word (`{reveal: node:database, at: "@database"}`), reveal it earlier, or name it when it shows; or `lint_ignore` it (`{rule: said_before_shown, object: Database}`) |
| `unsaid_reveal` | off (info when turned on) | a beat (not the scene's first) brings new labels, and the scene's narration names none of them (same labels and word matching as `said_before_shown`). Off by default: many labels are fine unsaid (a map's city names, a step's output); turn it on with `unsaid_reveal: {severity: info}` to review a script |

**Config** (all optional; the values shown are the defaults):

```yaml
lint:
  fail_on: error              # error | warning | info | never: lowest severity that fails
  min_opacity: 0.1            # objects fainter than this are ignored (end of a fade)
  rules:                      # each rule also takes severity: error | warning | info | off
    off_frame: {tolerance: 0.004}           # fraction of the shorter side (2 px at 480p)
    safe_area: {tolerance: 0.01}            # 5 px at 480p
    text_overlap: {min_overlap: 0.1}        # fraction of the smaller box
    covered_text: {min_covered: 0.02}       # fraction of the middle of the text's box
    label_spacing: {min_gap: 0.02}          # 7 px at 360p, 22 px at 1080p
    min_font: {min_size: 0.025, error_size: 0.018}   # cap height: 12 / 8.6 px at 480p, 27 / 19.4 px at 1080p
    contrast: {min_ratio: 4.5, large_ratio: 3.0, large_size: 0.045, dimmed_ratio: 2.0}
    max_words: {max_words: 40}
    overlay_overlap: {min_overlap: 0.05}    # fraction of the scene object's box
    host_overlap: {min_overlap: 0.02}       # fraction of the smaller box
    walk_overlap: {min_overlap: 0.25}       # fraction of the narrower character's width
    off_stage: {min_hidden: 0.05}           # fraction of the character's box outside the view
    character_overlap: {min_overlap: 0.25}  # fraction of the narrower character's width
    prop_overlap: {min_overlap: 0.15}       # fraction of the narrower prop's width
    bubble_overlap: {min_overlap: 0.1}      # fraction of the face's (or smaller bubble's, or symbol's) box
    facing_away: {}
    hidden_speaker: {min_hidden: 0.5}       # fraction of the speaker's face box
    small_speaker: {min_face: 0.075}        # a speaker's face height, fraction of the shorter side
    mouth_without_voice: {}
    look_alike: {min_contrast: 0.35}        # contrast score of two characters, 0 to 1
    narration_speed: {unit: auto, min_words: 5}   # + min_rate / max_rate: default the language's range
    dead_air: {max_seconds: 6.0, min_change: 0.0002}   # min_change: fraction of the frame
    animation_overrun: {tolerance: 0.1}     # seconds past narration + pad
    rushed_animation: {min_run_time: 0.5, max_speedup: 1.5}   # seconds; times its own pace (walks and jumps on a level)
    talked_over: {}
    readback: {max_wer: 0.1}                # word error rate; also `vidgen readback`'s threshold
    unclear_speech: {min_probability: 0.5, doubtful_probability: 0.75, max_gap: 0.5}   # also `vidgen readback`'s word flags
    concept_colors: {max_colors: 5, min_contrast: 4.5}   # the terms: colours
    said_before_shown: {min_lead: 1.5, max_words: 4}     # seconds; longer texts are sentences
    unsaid_reveal: {max_words: 4}                        # off unless given a severity ("info")
```

`severity` on a rule sets the severity of all its findings (`off` disables the rule). The
`lint` section and `lint_ignore` do not count in a scene's render fingerprint: changing them
never makes stills stale.

**Ignoring findings in a scene** (`lint_ignore` on the scene): a list of rule names (or `all`),
or `{rule, object, beat}` filters. `object` is a pattern (`*` and `?` wildcards, case-sensitive)
matched against the object's `name`, `path`, `text`, icon name and, for a speech bubble, its
speaker's name, for an effect symbol the character it marks (for a pair, either object); `beat`
limits the entry to the end of that beat (it must be a beat of the scene).

```yaml
scenes:
  - id: chart
    type: line_chart
    params: {...}
    lint_ignore:
      - max_words                                   # every max_words finding of this scene
      - {rule: min_font, object: "VGroup[2]/*"}     # the small tick labels, by path
      - {rule: contrast, object: "Illustrative*", beat: chart_b2}
```

## Storyboard (`vidgen storyboard`)

`vidgen storyboard [PROJECT]` writes **contact sheets**: PNG pages showing the stills of the
video in a grid, each labelled `beat @ time` with the beat's narration under it and a header
band per scene (`N/M  id · type · start–end (duration)`). It is the way to *look* at a video
without watching it, and is made for AI agents that open the PNG with an image viewer: pages
are 1280 px wide (`--width PX`, 640–2000) and at most about 1.25 times as high, the font sizes
grow with the width, long narration is wrapped and cut with `…`, and long videos are split into
several pages instead of one huge image. 16:9 videos get 4 stills per row (2 on a scene's
sheet), 9:16 videos 5 (4); with `--per-beat N` a beat's stills stay side by side on one row.
On a [`stage`](#stage), the mid-action stills (above) come before their beat's end still, labelled
`½ walk_to pip @ time`, so a walk or a gesture can be checked in motion, not only where it ends.
With [`auto_direct`](#automatic-directing-auto_direct), a line `auto: look_at kit pip · react kit
thinking` under a beat's narration lists the actions automatic directing added to it.

Files, in `build/<preview|final>[_<variant>]/storyboard/`:

```
storyboard/
  video-1.png, video-2.png ...   # the whole video (times in the video, m:ss.s)
  scenes/<scene>-1.png ...        # one scene, larger stills (times from the scene start)
```

Options:

| option | |
|---|---|
| `--scene ID` | only this scene's sheet (repeatable); no `video-*.png` is written (old ones are deleted) |
| `--per-beat N` | N stills per beat, evenly spaced, the last at the beat's end (default 1: the end of each beat) |
| `--variant NAME` | storyboard a variant (e.g. the vertical one) |
| `--preview` / `--final` | preview format (the default) or the final format |
| `--width PX` | page width (default 1280) |
| `--jobs N\|auto` | scenes rendered in parallel ([`auto`](#parallel-renders---jobs): from the available memory and CPU cores) |
| `--force` | render the selected scenes again even if their stills are current |
| `--json` | print the sheets and the stills on each (below) |

**What gets rendered.** The sheets are built from the stills of `vidgen render --frames` (see
above). A scene is rendered again (with stills, in worker processes like `vidgen render`) only
if its stills are missing, were taken at another `--per-beat` count or format, or are stale:
each render records a fingerprint of what the scene depends on (its config entry, the other
config sections except `scenes`/`variants`/`lint`, its beats' MP3s, the project's extension code,
the files under `assets/`, and vidgen's own rendering code; with [overlays](#overlays), also
every scene's beats, MP3s and type, which place the scene in the video; the transition into the
next scene; with [`carry`](#continuity-carrying-objects-into-the-next-scene-carry), what the next
scene carries out of it and, for a carrying scene, the fingerprint of the scene before), and a
scene whose fingerprint changed is rendered again. So `vidgen storyboard` right after `vidgen render --preview
--frames` renders nothing, and after an edit it renders only the edited scenes. Files a scene
reads from outside `assets/` are not tracked: use `--force`. The storyboard does not join the
video; `vidgen render` does. It dispatches `post_scene` for the scenes it renders, not
`pre_render`/`post_render`.

**`vidgen render` uses the same fingerprints** (since vidgen 0.2): it renders only the scenes
whose render is missing, was made at another format or without the narration it now needs, or
is stale, and joins them with the current renders of the others (`render --json` lists each
scene's `status`: `rendered` or `reused`). So `vidgen render --preview` after a storyboard or a
lint of the preview only joins the video, and keeps their stills. `--force` renders every scene
again; `--scene ID` renders those scenes whatever their state.

## Animatic (`vidgen animatic`)

`vidgen animatic [PROJECT]` writes `<output>[_<variant>]_animatic.mp4` into the
[`output/` folder](#output-folder-output_dir---output-dir): the storyboard's stills (the preview
format's) held in time with the narration, with the video's audio and the subtitles drawn on. It
shows the pacing of a video, scene by scene and beat by beat, before a render: once the stills are
current it takes seconds, because ffmpeg alone makes it (no Manim).

- **Stills.** The ones `vidgen storyboard` uses: the end of each beat, the mid-action stills of a
  [`stage`](#stage) and, after `vidgen storyboard --per-beat N`, the N stills of each beat. Current
  stills at any count are reused; a scene without current stills (never storyboarded, edited
  since, another format) is rendered first, with one still per beat, like `vidgen storyboard`
  would (`--jobs` as there).
- **Timing.** Each beat's stills are shown during that beat: within a beat the stills split its
  time in order, each shown up to the moment it was captured, so a mid-action still (captured
  half-way through its action) from the beat's start or the still before it, and the beat-end
  still from there until the beat's end. What a beat reveals is on screen while the beat is
  spoken, not after it. A scene's first still is shown from the scene's start, the video's first
  from 0:00; a scene's last still stays through the scene's tail until the next scene. The times are those of `vidgen render`:
  the narration's MP3s, else the word-count timing; scenes overlapping in a
  [transition](#transitions-transition) cut to the next scene where it starts (no crossfade, no
  fades between stills).
- **Audio** (`--no-audio`: silent): the video's audio as `vidgen render` mixes it, the narration,
  sound effects, music and ambience, normalised to `audio.target_lufs` the same way.
- **Captions** (`--captions` / `--no-captions`): the cues of the video's SRT, white on a dark
  plate at the bottom of the stills, drawn when they are spoken. Default: on, unless the video
  has a [`captions`](#captions) overlay (the stills show those already, as they were at the
  still's moment).

Measured on `examples/cartoon-music-box` (51 s, 2 stage scenes, no narration MP3s, under the
1500 MB cap): 42 s with no stills (the two scenes rendered with their stills, 34 s), 7 to 9 s
with current stills (2.9 s of that encoding 767 frames at 640x360, 2.7 s mixing the audio), 3.7 s
with `--no-audio`.

Files: the captioned stills, the audio tracks and ffmpeg's lists in
`build/preview[_<variant>]/animatic/`.

## Scene gallery (`vidgen gallery`)

`vidgen gallery [PROJECT]` renders **every scene type** from one canonical sample, at 16:9 and
9:16, and writes a Markdown gallery: the repository's own is [docs/gallery](gallery/README.md).

- **Samples.** A built-in type's sample is its snippet in the author guide's `scenes` topic
  (`AGENTS.md`, `vidgen guide scenes`; the first of the type, one without `generate:` preferred),
  so the guide and the gallery show the same YAML and a test keeps the committed pages in step
  with the guide. Files a snippet names under `assets/` are stand-ins shipped with vidgen (a
  landscape picture for `image`, an app screenshot for other pictures, a short screen recording
  for clips). Another name of the same type (`flowchart` for `diagram`) is listed, not rendered
  again. Run in a project (or given `PROJECT`), the project's own scene types are shown too, each
  from its first scene in `video.yaml` (with the files it names and the project's
  `assets/icons`), in the project's theme and with its extensions; a type with no scene is listed
  as having no sample.
- **Rendering.** The samples become one work project, `build/gallery/` under the project (or the
  current folder): 16:9 at 640x360 and 9:16 (its `portrait` variant) at 360x640, 12 fps, timed
  from the word counts (no audio). Like the storyboard, a sample is rendered again only when its
  stills are missing or stale; the work project always holds every sample, so a run for a few
  `--types` keeps the others current.
- **Output** (default `docs/gallery`; `--output DIR`): `README.md`, the index (every registered
  type by the guide's groups — text and structure, flows, data, pictures and media, maths and
  code, then the project's — with both stills and what it is for, from the guide's chooser),
  `<type>.md` per type (what it is for, the type's description, the stills, links to the GIFs,
  the YAML, a params table from the `Params` model with types, defaults and docs, the action
  targets, the beat count) and `media/<type>-16x9.png|gif`, `media/<type>-9x16.png|gif`. The
  still is the end of the last beat; the GIF plays the scene to that point (320 px / 180 px wide,
  6 fps, 32 colours, the end held 1.5 s; the fade-out left out). Nothing in the files depends on
  the time or the machine: the same vidgen writes the same files.

| option | |
|---|---|
| `--output DIR`, `-o` | the gallery folder (default `docs/gallery`) |
| `--types T,T` | only these types (comma-separated, repeatable; another name renders its type); the index still lists every type, with the stills already in the folder (a type with no page there yet: "not rendered here yet") |
| `--formats 16:9,9:16` | the formats to render (default both) |
| `--theme PRESET` | render in this theme preset (default: the project's theme, or the default look) |
| `--clips` / `--no-clips` | also write the GIFs (default yes); without, the pages link the GIFs already there |
| `--jobs N\|auto` | samples rendered in parallel ([`auto`](#parallel-renders---jobs): from the available memory and CPU cores) |
| `--force` | render the samples again even if their stills are current |
| `--json` | print the gallery's files (below) |

The repository's gallery is committed (stills and GIFs, about 4.4 MB; a test keeps it under
8 MB): run `vidgen gallery -j 2` from the repository root after changing a built-in scene's look
or a guide snippet, look at the stills, and commit `docs/gallery`.

## Drafting from an outline (`vidgen plan`)

`vidgen plan INPUT` turns a Markdown outline (`.md`) or a plain-text script (`.txt`: short lines
standing alone are headings) into a **draft project**: a folder scaffolded like `vidgen init`
(default: named after `INPUT`; `--output DIR`) or just a config file (`--output video.yaml`),
with the pictures the outline shows copied into `assets/`. Nothing is sent anywhere and no AI is
involved: the same input and options always give the same draft. It is a starting point for an
agent (or a person) to refine — it never writes the narration a video deserves — so every scene
carries a `# plan:` comment (why it got its type) and `# TODO:` comments (what to check), and the
command prints the scenes, the estimated length and the TODO count, then validates the draft.
Example: [examples/plan](../examples/plan) (`outline.md` and the unedited `video.yaml`).

**Structure.** A single top-level heading (`#`) at the start is the title; a short first
paragraph under it (one sentence, at most 14 words) is the `title`'s subtitle, and the first beat
of the opening prose its narration — unless that beat has a prominent number, which then opens
the video as a `stat` (the hook) before the title. The highest remaining heading level makes
sections, the next one the units inside them; each unit becomes one or more scenes, its heading
their `heading` / `title`. Deeper headings and short lines ending with `:` (`Pros:`) label the
block that follows. When the narration runs over 2 minutes and there are at least 3 sections,
every section starts with a silent `chapter` card (2.5 s) and the video gets a `progress_bar`. A
last section called Summary, Conclusion, Recap, Takeaways, Next steps (or Resumo, Conclusão...)
ends with an `end_card`: its last beat is the call to action, its links the card's `lines`; a
list in it becomes the recap scene. Without one, a TODO at the top says to add an ending.

**Cues → scene types.** Each block that shows something gets a scene, narrated by the prose
written before it (the prose after the last block of a unit joins that block):

| in the outline | scene type |
|---|---|
| a bullet list | `bullets`; `icon_grid` when every item is a short noun (≤ 3 words) with a matching icon (name, alias, a word of the name, or an exact tag: `vidgen list-icons --search`) |
| a numbered list of 2–8 steps | `process` (more steps: numbered `bullets`) |
| list items starting with a date (`1969:`, `July 1969 —`, `2023-05`) | `timeline` |
| a table | `table` (one row per beat when the prose has a beat per row, else `reveal: all`); labels + one numeric column (`0.1 ms`, `81%`, `$1,200`) → `bar_chart` with its `unit` / `value_format`, and a `highlight` on the bar the last beat names |
| a code block | `code` (≤ 15 lines; a `highlight` per beat by blank-line blocks), else `code_walkthrough` (a step per block) |
| `$$...$$` | `equation` (one formula, or two as steps); `equation_derivation` from 3 formulas (consecutive blocks, `\\` lines or an `aligned` environment) |
| an image on its own line | `image`: the file copied into `assets/`, or a `generate:` prompt from its alt text when it is missing |
| a blockquote (a last line `— Author, Source`) | `quote` (two beats at most; the rest of the prose follows as its own scene) |
| a paragraph of `A -> B -> C` lines | `diagram` (a node per label, an edge per arrow) |
| "A vs B" (or "A or B?") heading with two lists, or `Pros:` / `Cons:` lists | `comparison` (columns from the lists; from the sentences naming each side when there are no lists) |
| a sentence with a prominent number (`46%`, `40x`, `$3.5 million`, `from 120 to 15`) | `stat` (value, prefix / suffix, label from the words around it; "from X to Y" gives a `comparison` that counts up from X) |
| other prose | `bullets` of its compressed sentences, one per beat (≤ 5 per scene), or a `text_card` for a single beat |

**Narration.** Prose is cut into sentences by the rules of `--language` (abbreviations such as
`e.g.`, `Dr.`, `Sr.`, `p.ex.`, initials and decimals do not end a sentence), sentences over 15
words are cut at their best phrase boundary (a clause mark, then a conjunction, then a
preposition; never after an article), and sentences under 6 words join a neighbour — the author
guide's beats of 6–15 words. Each reveal step gets one beat: one sentence per item when the counts
match (the sentences after the block for its items, the ones before as an intro), else the
sentences that share a word with each item, else the items' own text when they are sentences,
else a placeholder beat with a TODO. An intro of one short sentence joins the first beat; a
longer one becomes a scene of its own before the block.

**On-screen text** is compressed from the outline: headings ≤ 5 words, list items ≤ 6, labels
≤ 3, a title or card ≤ 7. Compressing drops parentheses, leading filler ("In this video",
"So", "Basically"...), filler words ("really", "just"...) and, when still too long, articles;
keeps the part before a `:` (or after a generic lead such as `Step 2:`) and the main clause after
a leading "On a miss, ..."; and never ends on a word that leans on the next ("Store result with").

**TODOs** name what a draft cannot know: placeholder beats, narration that repeats the items on
screen, icon choices, a stat's context and which direction is good, a chart's source caption, a
picture to provide, notes for code steps, long lists, beats with parentheses / links / inline
maths, and more beats than a scene has steps (dead air).

| option | |
|---|---|
| `--output DIR\|FILE`, `-o` | the project folder to create (default: `INPUT`'s name without the suffix, in the current folder), or a `.yaml` / `.yml` file to write (its folder gets the `assets/`) |
| `--title TEXT` | the video's title (default: the outline's top heading, else the file name) |
| `--format 16:9\|9:16` | landscape 1920x1080 (preview 854x480, the default) or vertical 1080x1920 (preview 480x854) |
| `--preset NAME` | the theme preset (default `dark_tech`; `vidgen list-themes`) |
| `--language TAG` | the language of the text (BCP-47, e.g. `pt-BR`): sentence, phrase and compression rules, a decimal comma for a `stat`, and `language:` in the config |
| `--force` | write into a folder that is not empty (its `video.yaml` replaced, other files kept) or over an existing config file |
| `--json` | print the summary as JSON ([below](#vidgen-plan---json)) |

Then refine the draft like any project: read the comments, rewrite the narration for the ear,
`vidgen validate`, `vidgen storyboard`, `vidgen lint` (`vidgen guide workflow`).

## MCP server (`vidgen mcp`)

`vidgen mcp [--root DIR]` (also the `vidgen-mcp` script) runs a [Model Context
Protocol](https://modelcontextprotocol.io) server on stdin / stdout, so an AI agent's client
(Claude Desktop, Claude Code, ...) can call vidgen's commands as **tools**. It needs the optional
extra: `pip install "schu-video-generator[mcp]"` (the official MCP Python SDK, 1.19 or newer).
The server calls itself `schu-video-generator`; configuration snippets (server key
`schu-video-generator`, command `vidgen`): README "Use from an AI agent via MCP".

**Tools** (each returns the command's `--json` document below as JSON text; `ok` false comes
back as a tool error with the same text): `guide`, `init`, `plan` (`input_path`, or the outline as
`markdown_text`), `validate`, `schema`, `list_scenes`, `list_icons`, `list_themes`, `list_sfx`,
`list_music`, `music_preview` (`vidgen music preview`: `mood`, `seed`, `bars`, `key`, `tempo`,
`out`), `storyboard`, `animatic`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`,
`thumbnail`, `export`, `gallery`, `translate_template`, `character_sheet`, `direct`, `screenplay`
(`input_path` or `screenplay_text`, `out`, `cast`, `species`, `seed`, `force`), `cast` (`count`
for `--random`, `seed`, `species`, `out`, `provider`, `narrator`, `model`, `force`). Their parameters are the command's
options in snake_case (`per_beat`, `fail_on`, `no_audio`...); list options take lists. Defaults
that differ from the CLI, for agents: `render`, `thumbnail` and `export` use the preview (`preview:
false` for the final format); `gallery` writes into `build/mcp/gallery` without GIFs; `schema`
wants `scene: TYPE` (a few KB) and gives the whole schema (hundreds of KB) only with `full: true`
(or `all_types: true`).

**Pictures.** `storyboard` returns its contact sheets (whole-video sheets first), `thumbnail` the
thumbnail and its small copy, `gallery` the stills, `list_icons` with `sheet: true` an icon
sheet, `list_themes` with `swatches: true` the swatches, as MCP image content: at most 1568 px on
the long side, PNG (JPEG when a PNG would exceed 800 KB). `images` (default 3, at most 8) and
`image_offset` page through more; the document's `mcp_images` says `{total, offset, returned,
next_offset}`. Stills are reused, so asking for the next page renders nothing.

**Costs.** `tts` and `imagegen` are dry runs by default (free, no key): they list what would be
made and its size (characters, estimated dollars). A real run needs `dry_run: false` **and**
`confirm_cost: true`; without the latter the tool refuses before anything starts. `readback` asks
for `confirm_cost: true` when the project's `stt.provider` is a paid service (`elevenlabs`).

**Folder.** Every path a tool takes (project, outputs, `init`'s folder, `plan`'s input) is relative
to `--root` (default: the current folder) and must resolve inside it, `..` and symbolic links
included; other paths are refused. The files a project's config names (a scene's `path` /
`logo`, a watermark, thumbnail, stage or layer `image`, a music `source` file,
`pronunciation_file`, `translations`, `extensions`, `output_dir`, `soundfont`, a character's `look.svg`, a
stage prop's `svg`, a Kokoro `voice` file ending in `.pt`, in every variant, set and included
file; and the `include:` files themselves, also those of `screenplay`'s `cast`) must be inside
the root too: a config naming
`../other/file.png` or an absolute path elsewhere does not load in the server's commands
(`files outside the allowed folder`; the commands it runs get `VIDGEN_CONFINE_ROOT`, which you
can also set yourself). Files the server asks for itself (icon sheet, swatches,
gallery) go into `build/mcp/` under the root. The server passes its environment (API keys) to the
commands it runs but never returns it; documents carry only paths and results.

**How it runs.** Every call starts `python -m vidgen <command> ... --json` in the root folder (a
fresh process: Manim's configuration is process-global and a crashing scene or extension cannot
take the server down) and turns the command's stderr lines into MCP progress notifications.
Rendering calls (`storyboard`, `animatic`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`,
`thumbnail`, `export`, `gallery`) run one at a time; cancelling a call stops its process and the
render workers it started (the process group on macOS / Linux, the process tree on Windows).

**Resources**: `vidgen://guide` (the author guide) and `vidgen://guide/<topic>` (one topic each),
`vidgen://schema` (the JSON Schema of the root project's `video.yaml`, else of the built-ins) and,
when the root has a `docs/gallery` folder (the schu-video-generator repository), `vidgen://gallery/index` and
`vidgen://gallery/<type>`.

## JSON output (`--json`)

`vidgen validate`, `vidgen list-scenes`, `vidgen list-themes`, `vidgen list-icons`, `vidgen render`, `vidgen schema`, `vidgen storyboard`, `vidgen lint`, `vidgen thumbnail`, `vidgen export`, `vidgen slides`, `vidgen translate-template`, `vidgen readback`, `vidgen guide`, `vidgen gallery`, `vidgen plan`, `vidgen init`, `vidgen tts`, `vidgen imagegen`, `vidgen character-sheet`, `vidgen direct`, `vidgen screenplay` and `vidgen animatic` accept `--json` (every command but `vidgen mcp`, which speaks MCP): stdout then holds
exactly one JSON document (ASCII-only, non-ASCII characters escaped), and everything else
(progress, `warning:` lines, Manim output) goes to stderr. These shapes are meant for programs
and AI agents driving vidgen. Without `--json` the human output is unchanged.

**Stability.** `version` is the version of these shapes (currently **1**), not of vidgen. Keys
are only added within a version; removing or renaming a key or changing a value's type bumps
it. Times are seconds (floats), paths are absolute strings, absent values are `null`.

**Envelope** (every document, success or failure):

| key | type | |
|---|---|---|
| `version` | int | schema version of the document (1) |
| `vidgen` | str | vidgen package version |
| `command` | str \| null | `validate`, `list-scenes`, `list-themes`, `list-icons`, `render`, `schema`, `storyboard`, `lint`, `thumbnail`, `export`, `slides`, `translate-template`, `readback`, `guide`, `gallery`, `plan`, `init`, `tts`, `imagegen`, `character-sheet`, `direct` (`null` if the command line could not be parsed) |
| `ok` | bool | `true` on success; the exit code is 0 exactly when `ok` is true |
| `warnings` | list | `{scene, message}`: vidgen warnings of the run (`scene` is `null`, or the scene whose render printed it) |
| `error` | object | only when `ok` is false: `{kind, message, problems, details}` |
| `jobs` | object | only with [`--jobs auto`](#parallel-renders---jobs): `{requested: "auto", jobs, cores, per_job_bytes, available_bytes, memory_source, reason}` (`available_bytes` / `memory_source` `null` when the memory could not be read) |

**Errors.** `error.kind` is `usage` (bad command line; exit code 2), `error` (something the user
can fix: config, missing file, unknown scene, failed scene...; exit code 1) or `internal` (an
unexpected exception; exit code 1, `details.traceback` holds the traceback). `message` is the
text the human output prints after `error: `. `problems` lists config problems as
`{location, message, variant, file}` (`location` is a config path such as `scenes[2].params.title`,
or `null` when the problem is not about one value, e.g. an extension that fails to import;
`variant` is the variant whose merged config has the problem, `null` for the base config;
`file` is the [`include:` file](#shared-casts-and-sets-include-and-sets) the value is written in,
relative to the project, `null` for the project's own config file).
`details` is an object, empty unless stated below.

**Every language.** `vidgen tts`, `render` and `lint` with `--all-languages`
([dubbing](#dubbing-dub---all-languages)) print one envelope whose only other key is
`languages`: the documents of the base config and of each variant in another language, in that
order, each as the command prints it for one variant; `ok` is true when every one is.

```json
{"version": 1, "vidgen": "0.3.0", "command": "render", "ok": false, "warnings": [],
 "error": {"kind": "usage", "message": "unrecognized arguments: --bogus", "problems": [], "details": {}}}
```

### `vidgen validate --json`

Always a validate document (also when the project cannot be loaded); exit code 1 if there is
any problem. A variant whose config does not load is reported as problems (with its `variant`)
and the other variants are still checked (the human output does the same since Step 59).

| key | type | |
|---|---|---|
| `project`, `config_file` | str \| null | project folder and config file (`null`: the project could not be loaded) |
| `included` | list | the [`include:` files](#shared-casts-and-sets-include-and-sets) merged into the config (absolute paths, in merge order); empty without `include:` |
| `title` | str \| null | |
| `language` | str \| null | the base config's `language` |
| `translations` | object \| null | the base config's translation file: `{file, language, applied, stale, unknown, untranslated}` (`applied` a count, the others key lists; see [languages and translations](#languages-and-translations)); `null` without `translations:` |
| `scenes`, `beats` | int \| null | counts in the base config |
| `estimated_duration` | float \| null | seconds, from word counts + `narration.pad` + silent scenes' `duration` |
| `variants` | list | every variant checked: `{name, loaded, estimated_duration, problems, language, translations}` (`problems`: how many are this variant's own; `language` / `translations` as at the top level, `null` when it does not load) |
| `problems` | list | `{location, message, variant, file}` (as in `error.problems`); empty when the project is valid |
| `audio` | list | one per audio folder (the base config's, plus each variant with its own, see [variant audio](#narration-audio-elevenlabs)): `{variant, dir, ok, stale, missing, orphaned, beats}`; `ok`/`stale`/`missing` are counts, `orphaned` the paths of MP3s no beat uses, `beats` lists `{scene, beat, state}` in video order with `state` `ok`, `stale` or `missing` |
| `images` | list | the [generated pictures](#generated-images-imagegen-vidgen-imagegen) of the base config, plus each variant whose pictures differ (none without `generate:` params): `{variant, generated, missing, pictures}`, `pictures` listing each distinct request once as `{key, scenes, path, exists, prompt}` |
| `music` | list | the base config's music cues: `{source, kind, plays, fitted, from, to, scenes}` — `source` the bed, file or `compose: <mood>`; `kind` `bed`, `file` or `composed`; `plays` what will play (`composed`, `file`, or `bed <name>`: a bed, or a composed cue's bed without the `music` extra); `fitted` composed for the video's timings; `scenes` scene id → the compose settings it changes (`["mood"]`...) |

`warnings` include the theme contrast warnings (`theme contrast: ...`, prefixed `[variant] `
for a variant's own; they do not make `ok` false). When there are problems, `error` is
`{"kind": "error", "message": "video.yaml: invalid project ...", "problems": [same list],
"details": {}}`. Problem `message`s are the text after
the location in the human output (`scenes[1].type: unknown scene type 'titel'; did you mean
'title'? ...` → `location` `scenes[1].type`).

### `vidgen list-scenes --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose extensions were loaded (`null`: built-ins only) |
| `scene_types` | list | sorted by name, as below |
| `actions` | list | the [beat actions](#beat-actions) (built-in and the project's), sorted by name, as below |
| `overlays` | list | the [overlay types](#overlays) (built-in and the project's), sorted by name, as below |

Each scene type: `name`; `origin` (`builtin`, or the extension file relative to the project);
`builtin` (bool); `overrides_builtin` (bool, an extension registered with `override=True`);
`doc` (the class docstring, else its module's, or `null`); `beats` (`null` = any number, else
`{min, max, text}` with `max` `null` for no upper limit, e.g. `{"min": 2, "max": 2, "text":
"exactly 2 beats"}`); `params` (`null` = free-form params, else a list of fields); `targets`
(the forms of its [action targets](#beat-actions), e.g. `["heading", "item<N>",
"item:<text>"]`; `[]` = none).
Each field: `name` (as written in `video.yaml`: an alias such as `from` when the field has one); `type` (readable type as in the human listing: `str`, `list[str]`,
`color`, `size`, `'all' | 'per_beat'`, ...); `required` (bool); `default` (JSON value, `null`
when required); `doc` (the docstring under the field or its `Field(description=...)`, or
`null`); `nested` (fields of `SceneParams` models used in the type, as `{model, fields}`);
`aliases` (other names the field accepts, e.g. `["title"]` for `heading`; `[]` = none).
Each action: `name`, `origin`, `builtin`, `overrides_builtin`, `doc` (as for scene types);
`run_time` (default seconds); `reversible` (bool: `until` allowed); `temporary` (bool: undone
by the end of its beat, like `zoom`); `until_next_beat` (bool: without `until`, undone when the
next beat starts, like `callout`); `needs_target` (bool); `scene_targets` (bool: `false` when
`target` names something else, like `sfx`'s sound); `animates` (bool: `false` for an action that
draws nothing and happens exactly at `at`, like `sfx`); `target_options` (options whose
values are target names, e.g. `["into"]`); `options` (fields like `params`; `[]` = none).
Each overlay type: `name`, `origin`, `builtin`, `overrides_builtin`, `doc` (as above); `layer`
(drawing order among overlays); `lint_skip` (lint rules not applied to its objects, e.g.
`["contrast"]`); `options` (fields like `params`).

### `vidgen list-themes --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose presets and registered defaults were used (`null`: built-ins only) |
| `orientation` | str | `landscape`, `portrait` or `square`: the project's `format` (decides `auto`) |
| `current` | object | the project's choice: `{preset, scale, scale_resolved}` (`preset` `null` without one) |
| `presets` | list | every preset, built-in first, as below |
| `type_scales` | object | `{scales: {name: {title, subtitle, heading, body, caption, small}}, auto: {orientation: scale}}` |
| `swatches` | str \| null | the PNG written with `--swatches` |

Each preset: `name`, `origin` (`builtin` or the extension file), `base`, `description`,
`selected` (bool: the project's preset), and what selecting it gives in this project:
`background`, `font`, `font_serif`, `font_mono`, `fonts` (the roles the preset and config
set: role → token or family), `font_roles` (the family of every built-in role: `body`,
`heading`, `quote`, `quote_mark`, `code`), `code_style`, `scale` (as set, e.g. `auto`),
`scale_resolved`, `colors`, `palette`, `sizes`; `contrast` `{ok, min_text_ratio,
min_graphic_ratio, failures}` (`failures`: messages like the validate warnings) and
`palette_distinctness` `{normal, protanopia, deuteranopia, tritanopia}` (smallest CIEDE2000
difference between two palette colours).

### `vidgen list-icons --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project folder whose `assets/icons` were included (`null`: built-ins only) |
| `search`, `category` | str \| null | the filters given |
| `sources` | object | the built-in set: `{lucide: {package, version, license, license_file, homepage}}` |
| `categories` | list | `{name, description, count}` for every category (built-in ones first, then project categories); `count` over all icons, not only the listed ones |
| `count` | int | number of listed icons |
| `icons` | list | the listed icons, best matches first: `{name, category, tags, aliases, source, origin, overrides, path}` (`origin` `builtin` or `project`; `overrides`: a project icon replacing a built-in; `path` the SVG) |
| `sheets` | list | the PNG files written with `--sheet` |

### `vidgen list-sfx --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project folder whose `assets/sfx` were included (`null`: built-ins only) |
| `rate` | int | sample rate of every sound (48000) |
| `loudness_target`, `peak_ceiling` | float | the level built-in sounds are set to at gain 0: loudest 400 ms in LUFS (K-weighted, one channel), highest peak in dBFS |
| `params` | list | the params of built-in sounds (`duration`, `pitch`, `intensity`), fields as in `list-scenes` |
| `count` | int | number of sounds |
| `sounds` | list | `{name, origin, overrides_builtin, description, use, duration, duration_range, channels, loudness, peak_db, preview}`: `origin` `builtin` or the file (`assets/sfx/x.wav`); `description` (what it sounds like), `use` and `duration_range` (`[min, max]` s) for built-ins, else `null`; `duration` (s), `loudness` (LUFS), `peak_db` (dBFS) at the defaults; `preview` the WAV written with `--render-dir`, else `null` |
| `previews` | str \| null | the `--render-dir` folder |

### `vidgen list-music --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project folder whose `assets/music` was included (`null`: built-ins only) |
| `rate` | int | sample rate (48000) |
| `level` | float | integrated loudness (LUFS) of music at `volume: 0` (−28) |
| `duck` | object | the default ducking `{depth, attack, release, hold, clips}` |
| `count` | int | number of entries |
| `music` | list | `{name, origin, description, use, tempo, key, chords, loop_seconds, duration, channels, loudness, preview}`: built-in beds (`origin` `builtin`; `description` what it sounds like, `use`, `tempo` BPM or `null` without a beat, `key`, `chords` in loop order, `loop_seconds`) then the project's files (`origin` `project`, `name` the path to use as `source`, `duration` s); `loudness` measured (LUFS); `preview` the WAV written with `--render-dir`, else `null` |
| `previews` | str \| null | the `--render-dir` folder |
| `moods` | list | composed music's moods: `{name, family, description, use, key, tempo, meter, bars, loop_seconds, instruments, fallback_bed}` (`family` `explainer` or `cartoon`; `instruments` part → instrument name; `fallback_bed` the bed played without the extra) |
| `instruments` | list | `{name, program, drums, low, high, description}`: General MIDI program (a drum kit's number when `drums`), range as note names (`null` for drum kits) |
| `symusic` | str | the installed symusic version, or how to install the extra |

### `vidgen music --json`

`vidgen music preview --json` ([`vidgen music preview`](#vidgen-music-preview)):

| key | type | |
|---|---|---|
| `action` | str | `preview` |
| `wav`, `midi` | str | the files written |
| `mood`, `family` | str | the mood and `explainer` / `cartoon` |
| `seed`, `bars` | int | |
| `key`, `meter` | str | e.g. `F major`, `3/4` |
| `tempo` | float | quarter notes per minute |
| `piece_seconds`, `seconds` | float | one pass of the piece; the WAV (with the 3 s tail) |
| `parts` | list | `{role, instrument, volume}` |
| `phrases` | list | `{bars: [first, last], phrase, chords}` (`phrase` e.g. `A question`; `chords` per bar, a list of chord names) |
| `loudness`, `true_peak` | float | of the WAV: LUFS integrated, dBTP |

### `vidgen schema --json`

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose scene types were used (`null`: built-ins only) |
| `schema` | object | the JSON Schema that `vidgen schema` prints without `--json` |

`warnings` includes the warning about an invalid `video.yaml` (see
[JSON Schema](#json-schema-vidgen-schema)).

### `vidgen render --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | `true` also with `--draft` |
| `draft` | bool | `true` with `--draft` ([drafts](#drafts-vidgen-render---draft)) |
| `audio` | bool | `false` with `--no-audio` |
| `format` | object | `{width, height, fps}` of this render |
| `outputs` | object | `{video, subtitles, timings, frames, chapters, thumbnail}`: the MP4, the SRT, `build/.../timings.json`, `build/.../frames/index.json` (`null` without `--frames`), the YouTube chapter list `<output>_chapters.txt` (`null` without chapters or with `chapters: {youtube: false}`) and the thumbnail `<output>_thumbnail.png` (`null` without `thumbnail:` or with `auto: false`; its warnings are in `warnings`) |
| `duration` | float | length of the video |
| `elapsed` | float | wall time of the command |
| `mix` | object \| null | the measured loudness of the video's audio (`null` with `--no-audio`): `{mixed, normalized, target_lufs, true_peak_limit, gain_db, integrated_lufs, true_peak_dbtp, limited_db, music}` — `mixed`: vidgen wrote the mix (music or normalisation; else FFmpeg joined narration and effects as before), `normalized` / `target_lufs` / `gain_db` the normalisation, `integrated_lufs` (LUFS) and `true_peak_dbtp` (dBTP) measured on the final mix, `limited_db` the limiter's deepest gain reduction (0: never engaged), `music` the cues `{source, kind (bed\|file), from, to, start, end, volume, duck}`; see [loudness](#loudness-of-the-final-mix-audio) |
| `chapters` | list | the chapters as written into the MP4 and the YouTube list (empty without chapters): `{title, number, scene, start, end, index, count, card, intro}` — `number` as written (`null`: none), `scene` the scene it starts at, `start` / `end` seconds in the video, `index` its position in this list (1-based) of `count`, `card` whether it starts with a `chapter` card, `intro` whether it is the chapter added at 0:00 before the first one; see [chapters in the outputs](#chapters-in-the-outputs-chapters-metadata) |
| `scenes` | list | config order: `{id, type, status, start, duration, render_seconds, beats}`; `status` is `rendered` or `reused` (an existing render was joined, see `--scene`), `render_seconds` the worker's wall time (`null` when reused), `start`/`duration` in the video, `beats` lists `{id, start, end}` (absolute; `end` excludes `narration.pad`) |

`warnings` includes those printed by scene code during rendering (e.g. beats a scene never
narrated), with their `scene`, and YouTube's chapter rules the list breaks (`chapters: ...`). On failure, `error.details` is `{failed, rendered}`: `failed`
lists `{scene, exit_code, output_tail}` (the last 60 lines of the worker's output; exit code 1
for a vidgen error, 2 for an exception in scene code), `rendered` the scene ids rendered before
(or, with `--keep-going`, besides) the failures.

### `vidgen storyboard --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | `false` with `--final` |
| `per_beat` | int | stills per beat |
| `format` | object | `{width, height, fps}` of the stills |
| `folder` | str | the `storyboard/` folder |
| `rendered` | list | ids of the scenes rendered by this command (config order) |
| `reused` | list | ids of the selected scenes whose current stills were reused |
| `elapsed` | float | wall time of the command |
| `sheets` | list | every page written: `{kind, scene, page, pages, path, width, height, frames}`; `kind` is `video` (the whole video, `scene` is `null`) or `scene`; `page` of `pages` (1-based); `width`/`height` in px; `frames` lists the stills on the page in order: `{scene, beat, k, n, mid, auto, time, scene_time, path}` (`beat` `null` for a silent scene, `k` of `n` stills of the beat, `mid` the actions a mid-action still shows half-way (its `k` is 0) or `null`, `auto` the actions [automatic directing](#automatic-directing-auto_direct) added to the still's beat as written in `video.yaml` (`[]` for none), `time` in the video or `null` when not every scene has a render at this format, `scene_time` from the scene start, `path` the still's PNG) |

Video sheets come first, then the scene sheets in config order. `warnings` and `error.details`
on a failed scene are as for `vidgen render --json`.

### `vidgen animatic --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `audio` | bool | `false` with `--no-audio` |
| `captions` | bool | whether captions were drawn onto the stills |
| `format` | object | `{width, height, fps}` of the stills and the MP4 (the preview format) |
| `output` | str | the animatic, `<output>[_<variant>]_animatic.mp4` |
| `duration` | float | its length (the video's) |
| `elapsed` | float | wall time of the command |
| `rendered` | list | ids of the scenes rendered for their stills (config order) |
| `reused` | list | ids of the scenes whose current stills were reused |
| `mix` | object \| null | the loudness report of the audio as for `vidgen render --json` (`null` with `--no-audio`) |
| `stills` | list | the stills in the order shown: `{scene, beat, mid, time, start, end, path}` — `beat` `null` for a silent scene, `mid` the actions of a mid-action still or `null`, `time` its moment in the video, `start` / `end` when it is shown (seconds, whole frames), `path` the still's PNG |

`warnings` and `error.details` on a failed scene are as for `vidgen render --json`.

### `vidgen thumbnail --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | frames from the preview render, files named `..._preview_thumbnail` |
| `kind` | str | `frame` or `design` |
| `path`, `width`, `height`, `bytes` | str, int, int, int | the PNG |
| `jpeg`, `jpeg_bytes` | str \| null, int \| null | the JPEG (`null` without `jpeg` / `--jpeg`) |
| `small` | str | the copy at YouTube's small size (long side 320 px), to look at |
| `source` | object | frame: `{scene, beat, at, frame, time, overlays, render, render_size}` (`frame` / `time` in the scene's render, `render` that MP4); design: `{title, subtitle, icon, image, preset, background, title_px, subtitle_px, title_lines}` |
| `checks` | list | `{rule, severity, message}`, see [thumbnail](#thumbnail-thumbnail-vidgen-thumbnail) |
| `rendered` | list | scenes rendered for a frame thumbnail (empty when their renders were current) |
| `elapsed` | float | wall time of the command |

### `vidgen export --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | exported from the preview render |
| `kind` | str | `gif` or `clip` |
| `path`, `bytes` | str, int | the file written |
| `source` | str | the rendered video it comes from |
| `scene` | str \| null | `--scene` |
| `start`, `end`, `duration` | float | the part, seconds in the video (a stream-copied clip starts at the keyframe it starts on) |
| `width`, `height`, `fps` | int, int, float | of the file |
| `method` | str | `palette` (GIF), `copy` or `encode` (clip) |
| `audio` | bool | the clip has sound (`--with-audio`) |
| `max_mb`, `within_budget` | float \| null, bool \| null | the GIF's budget and whether it was met (`null` without `--max-mb`) |
| `attempts` | list | with `--max-mb`: every GIF encode `{width, fps, bytes}` in order |
| `elapsed` | float | wall time of the command |

### `vidgen slides --json`

| key | type | |
|---|---|---|
| `project` | str | |
| `variant`, `language` | str \| null | the variant and its language |
| `output_format` | str | `html`, or `pdf` with `--format pdf` |
| `preview` | bool | `false` with `--final` |
| `mode` | str | `beat` or `scene` |
| `per_beat` | int | stills per beat |
| `overlays` | bool | `false` with `--no-overlays` (stills from the `_bare` renders) |
| `dedupe` | bool | `false` with `--no-dedupe` |
| `format` | object | `{width, height, fps}` of the stills |
| `path`, `bytes` | str, int | the HTML page (the PDF) |
| `files_dir` | str \| null | HTML only: with `--separate`, the folder of pictures and MP3s |
| `image_format`, `quality` | str, int | `webp`, `jpeg` or `png` (PDF: `jpeg` or `png`) |
| `width`, `height` | int | of the slide pictures |
| `audio` | int | HTML only: MP3s included (`--audio`) |
| `pages` | int | PDF only: pages, the title page and continued notes included |
| `notes`, `title_page` | bool | PDF only: `--notes`, `--title-page` |
| `thumbnail` | str \| null | PDF only: the thumbnail on the title page (`null`: none or no title page) |
| `paper` | str | PDF only: `a4` or `letter` (of notes pages) |
| `bookmarks` | int | PDF only: outline entries (title page, chapters, slides) |
| `duration` | float | the deck's play timeline: the scenes back to back |
| `stills` | int | stills read; `merged`: how many were merged into the slide before |
| `rendered`, `reused` | list | scene ids rendered for the deck / whose stills were current |
| `elapsed` | float | wall time of the command |
| `slides` | list | `{index, scene, type, chapter, beats, notes, k, n, merged, time, scene_time, at, until, still}`: 1-based `index`; `chapter` title or `null`; `beats` ids and `notes` (their texts, a blank line between) carried by the slide; `k` of `n` stills of its beat; `merged` stills shown by it (1: none merged); `time` in the video (`null` when not every scene has a render at this format), `scene_time` from the scene's start; `at` / `until` on the play timeline; `still` the PNG |

`warnings` and `error.details` on a failed scene are as for `vidgen render --json`.

### `vidgen translate-template --json`

| key | type | |
|---|---|---|
| `project` | str | project folder |
| `variant` | str \| null | |
| `path`, `rel` | str | the translation file written, and as the config names it |
| `language` | str \| null | the file's language |
| `linked` | bool | the config's `translations:` names this file |
| `texts` | int | translatable texts listed |
| `translated` | int | texts with a current translation |
| `untranslated`, `stale`, `moved`, `obsolete`, `dropped` | list | keys: listed without a translation; translated but the source changed; found again under a new key; translated but gone from the config (kept); untranslated and gone (removed) |
| `references` | int | places in the file's `references` |

### `vidgen readback --json`

`ok` is true whenever the command ran (flagged beats do not fail it); a missing provider package,
API key or model, or an unknown `--beat`, is an error.

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `audio_dir` | str | the folder of the MP3s compared |
| `stt` | object | `{provider, model, language}`: the settings the transcripts are of (`language` `null`: detected) |
| `max_wer` | float | the threshold beats are flagged above |
| `flag_thresholds` | object | `{min_probability, doubtful_probability, max_gap}`: the thresholds of the word flags (`lint.rules.unclear_speech`) |
| `transcribed`, `cached` | int | beats transcribed by this run / read from `build/readback/` |
| `elapsed` | float | wall time of the command |
| `summary` | object | `{beats, flagged, words, errors, wer, worst, unclear, doubtful}`: beats compared, ids of the flagged ones, words of the spoken texts and differences over all of them, their ratio, the worst beats `[{beat, wer}]` (at most 5, with differences, worst first), and the number of unclear and doubtful word flags |
| `beats` | list | each compared beat, video order (below) |
| `skipped` | list | `{beat, reason}`: beats not compared (no MP3) |
| `terms` | list | `{term, entry, beats, heard, consistent, suggestion}`: written terms heard differently, most beats first; `entry` true when the term has a pronunciation entry, `heard` the different hearings, `consistent` true when heard differently in two or more beats |

Each beat: `scene`, `beat`; `audio` (`ok`, or `stale` when its hash does not match the current
text and voice); `cached` (the transcript came from the cache); `wer`; `words` (normalised words
of the spoken text); `errors` = `substitutions` + `deletions` + `insertions`; `flagged`; `text`
(as written), `spoken` (with the pronunciation applied), `heard` (the transcript); `edits`;
`suggestions` (what to do, once each; empty without differences); and `flags` (the words to
check, in time order; below).

Each flag: `scene`, `beat`; `word` (heard, as transcribed; empty for words not heard) and
`written` (the beat's words concerned; empty for an extra word); `level` (`unclear` or
`doubtful`); `reasons` (some of `low_probability`, `gap`, `mismatch`: a difference with the
text); `time` and `end` (seconds in the beat's MP3; for words not heard, the end of the word
before; `null` without word times); `video_time` (`time` in the video, from the last render;
`null` without one); `probability` (the lowest of its words; `null` when the provider gives
none); `gap` (the pause before it, seconds, when it is a reason); `detail` (what is wrong, in
words); `suggestion`.

Each edit: `kind` (`substitution`, `deletion`: words not heard, `insertion`: extra words heard);
`expected` and `heard` (the normalised words); `written` (the beat's words concerned, as written;
empty for words heard where nothing was expected, `after` then names the written word before
them); `said` (the spoken form when a pronunciation entry changed those words, else `null`);
`errors`; `at` (when the heard words start in the MP3, seconds; `null` without word times or when
nothing was heard); `term` (the written term the fix is about: a pronunciation entry's term, or a
name, acronym or number; else `null`) and `entry`; `suggestion`.

### `vidgen guide --json`

The author guide for AI agents (`AGENTS.md`, shipped with vidgen; `vidgen guide [TOPIC] [--list]`).

| key | type | |
|---|---|---|
| `topic`, `title` | str \| null | the topic printed and its heading (`null`: the whole guide, or `--list`) |
| `topics` | list | every topic in order: `{name, title, aliases}` (`vidgen guide NAME` takes the name or an alias) |
| `text` | str \| null | the Markdown printed: the topic, or the whole guide (`null` with `--list`) |
| `path` | str | the packaged guide file |

An unknown topic is an error (`ok` false) whose message suggests the closest names.

### `vidgen gallery --json`

The [scene gallery](#scene-gallery-vidgen-gallery) written by `vidgen gallery`.

| key | type | |
|---|---|---|
| `project` | str \| null | the project whose own types are shown (`null`: built-ins only) |
| `output`, `index`, `work` | str | the gallery folder, its `README.md`, the work project rendered in |
| `formats` | list | the formats rendered (`16:9`, `9:16`) |
| `rendered`, `reused` | list | samples rendered by this run and current ones reused, as `"<type> (<format>)"` |
| `bytes` | int | the size of the gallery folder |
| `elapsed` | float | seconds |
| `types` | list | every registered type, in index order: `{name, alias_of, sample, page, stills, clips}`; `alias_of` names the type it is another name of (`null` otherwise), `sample` is `guide`, the project's config file name or `null` (none), `page` the type's page written by this run (else `null`), `stills` / `clips` the files written by this run by format |

`warnings`: a type with no sample, and the render warnings of the samples (`scene` is then
`"<type> (<format>)"`). An unknown `--types` name or format is an error (`ok` false).

### `vidgen plan --json`

The [draft](#drafting-from-an-outline-vidgen-plan) written by `vidgen plan`. `ok` is false when
`vidgen validate` finds problems in the draft (listed in `problems`; the files are written anyway).

| key | type | |
|---|---|---|
| `project`, `config` | str | the project folder and the config file written |
| `created` | bool | `true` when the folder was scaffolded by this run (like `vidgen init`) |
| `title`, `language`, `format` | str \| null | the video's title, its `language` (`null`: none given) and `16:9` / `9:16` |
| `chapters` | bool | `true` when the draft got chapter cards and a progress bar |
| `scene_count`, `beat_count` | int | scenes (chapter cards included) and narrated beats |
| `estimated_duration` | float | seconds, from the word count (like `vidgen validate`) |
| `todo_count` | int | the `# TODO:` comments in the config |
| `types` | object | `{scene type: count}` |
| `assets` | list | pictures copied into the project (`assets/<name>`) |
| `notes` | list | TODOs about the whole video (e.g. no closing section) |
| `scenes` | list | `{id, type, beats, words, estimated_duration, reason, todos}` per scene, in order; `reason` is the scene's `# plan:` comment, `todos` its `# TODO:` comments |
| `problems` | list | `vidgen validate` problems of the draft, `{location, message, variant, file}` (normally empty) |

### `vidgen init --json`

| key | type | |
|---|---|---|
| `project`, `config_file` | str | the new project folder and its `video.yaml` |
| `example` | str | the template it was made from (`--example`) |

### `vidgen tts --json`

The same document for a dry run (`--dry-run`, nothing sent, no key needed) and a run; the progress
lines (`[2/5] generated ...`) go to stderr. A run that fails part-way is an error document whose
message says how many beats were done (their MP3s are kept: run again to continue).

| key | type | |
|---|---|---|
| `project`, `variant`, `audio_dir` | str \| null | the project, the variant and the audio folder written |
| `dry_run`, `force` | bool | the options |
| `provider` | str | the video's TTS provider: `elevenlabs`, `openrouter` or `kokoro` (see [narration providers](#narration-providers)) |
| `characters` | int | characters sent (or that a run would send) for synthesis: what ElevenLabs and most OpenRouter models bill |
| `estimated_cost` | float | US dollars of the beats to synthesise whose price is known (OpenRouter models priced per character; Kokoro: 0, it runs locally; ElevenLabs bills a plan's quota: never estimated) |
| `unknown_cost` | int | beats to synthesise with no known price (ElevenLabs, OpenRouter models that bill the generated audio, OpenRouter not reachable) |
| `price_note` | str \| null | what the estimate is based on (`OpenRouter prices of <date>`, that they could not be read, the ElevenLabs note, `free (local): ...` for Kokoro) |
| `prices` | object | `{model: {per_character, basis}}` of the OpenRouter models used (`per_character` `null` when unknown; `basis` says why) |
| `notes`, `problems` | list | OpenRouter: what its live model list says about the voices (a voice it does not list, `instructions` / `speed` a model may ignore) and what a run refuses before paying (a model it does not have); Kokoro: free and local, the model download still to come, the extra not installed |
| `charged` | float \| null | US dollars OpenRouter reported for this run's requests; `null` in a dry run, with ElevenLabs, or when not reported |
| `voices` | object | `{voice name: {voice_id, provider, model, provider_voice, instructions, speed, lang, device, beats, characters}}` of the beats to synthesise (`default` = the base voice; `voice_id` `null` in an OpenRouter or Kokoro video; `lang` / `device` Kokoro's, else `null`) |
| `beats` | list | the beats to voice, in video order: `{scene, beat, voice, provider, model, provider_voice, instructions, speed, lang, device, action, characters, estimated_cost, says, source}`; `model` / `provider_voice` are ElevenLabs' `model_id` / `voice_id`, OpenRouter's `model` / `voice` or `hexgrad/Kokoro-82M` / Kokoro's `voice`; `action` `generate` (an API call) or `copy` (the base `audio/` MP3 of a variant beat that did not change; 0 characters, `source` its path), `estimated_cost` `null` when unknown, `says` the text sent when [pronunciation](#pronunciation-pronunciation) changed it (else `null`) |
| `generated` | list | beat ids voiced by this run (`[]` for a dry run) |
| `up_to_date` | list | beat ids skipped because their MP3 is current |
| `orphaned` | list | MP3s in the audio folder no beat uses (never deleted) |
| `elapsed` | float | seconds |

### `vidgen imagegen --json`

The same document for a dry run (`--dry-run`, no key needed) and a run (DESIGN.md §58, §64).

| key | type | |
|---|---|---|
| `project`, `variant` | str \| null | |
| `dry_run`, `force` | bool | the options |
| `estimated_cost` | float | US dollars of the pictures to generate, by `price_note` |
| `unknown_cost` | int | pictures to generate with no known price (model / size not in the price list, priced per token, or OpenRouter not reachable) |
| `price_note` | str | where the prices come from (OpenAI's 2025 list, OpenRouter's prices of a date, or that they are unknown) |
| `charged` | float \| null | US dollars the provider reported for this run (OpenRouter); `null` in a dry run or when not reported |
| `images` | list | the pictures to generate, each distinct request once: `{key, scenes, prompt, sent_prompt, provider, model, size, aspect_ratio, resolution, format, quality, seed, estimated_cost, price_basis, notes, problems, path}` (`sent_prompt` = prompt + style + negative as sent; `size` the nominal size when an `aspect_ratio` is sent; `format` `png` or `svg`; `price_basis` what `estimated_cost` is based on; `notes` options the model ignores or changes and `problems` what a run would refuse — OpenRouter, from its model records; `path` the PNG / SVG it is / will be stored as) |
| `generated` | list | keys generated by this run (`[]` for a dry run) |
| `up_to_date` | list | keys whose picture exists (skipped) |
| `orphaned` | list | pictures in `assets/generated/` no config of the project uses (never deleted) |
| `elapsed` | float | seconds |

### `vidgen character-sheet --json`

| key | type | |
|---|---|---|
| `project`, `variant` | str \| null | |
| `elapsed` | float | seconds |
| `sheets` | list | one per character drawn, in `characters:` order: `{character, path, width, height, bytes, sections}`; `sections` lists `{kind, names, own}` in sheet order: `kind` `pose`, `expression`, `mouth` (mouth shapes; absent for a character without a mouth) or `view` (`names` `[front]`: a generated character's front view, last), `names` the cells in order, `own` the character's own poses / expressions among them |

### `vidgen direct --json`

| key | type | |
|---|---|---|
| `project`, `variant` | str \| null | |
| `scenes` | list | each scene with automatic actions (`--scene`: only those), in config order: `{scene, beats}`; `beats` lists the beats with added actions: `{beat, actions}`, each action as written in `video.yaml` (`{look_at: kit, to: pip}`, `{react: kit, expression: thinking, at: 0.95}`) |

### `vidgen screenplay --json`

The project written by [`vidgen screenplay`](#cartoons-from-a-screenplay-vidgen-screenplay). `ok`
is false when `vidgen validate` finds problems in it (listed in `problems`; the files are written
anyway).

| key | type | |
|---|---|---|
| `project`, `config` | str | the project folder and the config file written |
| `created` | bool | `true` when the folder was scaffolded by this run (like `vidgen init`) |
| `title` | str | the video's title |
| `characters` | list | `{name, voice, generated}` per character (`generated`: it got a generated look) |
| `scene_count`, `beat_count` | int | stage scenes and beats |
| `estimated_duration` | float | seconds, from the word count (like `vidgen validate`) |
| `todo_count` | int | the `# TODO:` comments in the config |
| `notes` | list | TODOs about the whole video (e.g. voices to set by hand) |
| `scenes` | list | `{id, beats, characters, actions, todos}` per scene: the characters on its stage, the actions written from stage directions and manners, its `# TODO:` comments |
| `problems` | list | `vidgen validate` problems of the project, `{location, message, variant, file}` (normally empty) |

### `vidgen cast --json`

The include file written by [`vidgen cast`](#a-random-cast-vidgen-cast).

| key | type | |
|---|---|---|
| `path` | str | the file written |
| `seed` | int | the seed used |
| `species` | list | the species drawn from |
| `provider` | str | the voice provider the voices were chosen for |
| `lowest_contrast`, `min_contrast` | float | the lowest contrast between two of the characters, and the `look_alike` default threshold |
| `characters` | list | `{name, voice_kind, voice, provider_voice, look, colors}` per character: `voice` the `voices:` entry, `provider_voice` its voice name (`null` with ElevenLabs) |
| `notes` | list | TODOs (e.g. voices to set by hand) |

### `vidgen lint --json`

`ok` is false (exit code 1) when a finding is at least as severe as `fail_on`; `error` is then
`{"kind": "error", "message": "lint found 1 error, 3 warning, 0 info (fails on error or worse)",
"problems": [], "details": {"fail_on", "counts"}}` and the findings are still in the document.

| key | type | |
|---|---|---|
| `project` | str | |
| `variant` | str \| null | |
| `preview` | bool | `false` with `--final` |
| `format` | object | `{width, height, fps}` of the stills |
| `fail_on` | str | `error`, `warning`, `info` or `never` |
| `rules` | list | names of the rules run |
| `scenes` | list | ids of the scenes checked (config order) |
| `stills` | int | beat-end stills checked |
| `rendered`, `reused` | list | scene ids rendered for this command / whose current stills were reused |
| `elapsed` | float | wall time of the command |
| `counts` | object | `{error, warning, info}`: findings per severity |
| `ignored` | int | findings skipped by `lint_ignore` |
| `findings` | list | in scene order, then by time and severity, as below |

Each finding: `scene`; `beat` (the beat at whose end it was seen, `null` for a silent scene);
`time` (in the video, `null` when not every scene has a render at this format) and
`scene_time` (from the scene start); `rule`; `severity` (`error`, `warning`, `info`);
`object` (the object concerned, `null` for `max_words` and the timing rules; for `said_before_shown` / `unsaid_reveal` the label, as the layout dump has it where it first shows) and `other` (the second object of a
pair: the other text for `text_overlap`, the shape for `covered_text`; else `null`), each
`{id, kind, class, name, path, text, icon, bbox}` as in the [layout dump](#layout-dump-buildlayoutscenejson)
(`text` `null` for shapes, `icon` the icon name for kind `icon`, else `null`); `similar` (further objects with the same problem, reported with
this one, e.g. the other tick labels); `bbox` (the region to look at in the still, px:
the object, the overlap of a pair, or all counted texts); `message`; `value` and `limit` (the
measured number and the threshold it broke: a fraction of the shorter side for sizes, a ratio
for contrast, px for `off_frame`/`safe_area`, a word count, words per second for
`narration_speed`, seconds for the other timing rules); `beats` (every beat end where the
same problem was seen, the first is `beat`); `still` (the PNG at `beat`'s end; `null` if the
scene has none). Timing findings have `bbox` `null` and `time`/`scene_time` where the problem
starts (the beat's start, the start of the still stretch, the narration's end, the first
rushed animation).
