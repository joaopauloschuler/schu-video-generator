# Changelog

The project and its pip distribution are `schu-video-generator`; the command and the Python
package are `vidgen`. The release notes of 0.2.0 (what changed from 0.1) are in `HANDOFF.md`
("Release notes: vidgen 0.2.0") and `DESIGN.md` §63. Step numbers refer to `tasklist.md`;
each step has a section in `HANDOFF.md` and its details in `DESIGN.md`.

## 0.3.0 (Steps 61–149)

0.2.0 made narrated explainer videos that an AI agent can check and fix by itself. 0.3.0 adds
**cartoons**: original characters who talk with lip sync, move, act and react on drawn stages,
indoors and outdoors, with weather, props, vehicles, sound and music, written as YAML or as a
screenplay. It also adds two narration providers (OpenRouter, and Kokoro running free on your
own computer), OpenRouter pictures including SVG, an `output/` folder and `--jobs auto`; a
cartoon host beside any explainer scene, lines spoken with feeling, drafts and animatics,
ready-made sets, drawing styles, word-level readback flags and dubbing, and music composed for
each video and played with real instruments.

0.3.0 was prepared in Step 132 but never tagged or published, so the work of Steps 133–149
(Phases M and N in `tasklist.md`) is part of this release rather than an "Unreleased" section.

### Behaviour changes and possible breaks

Changes that affect projects made with 0.2.0:

- **Videos go to `output/`** (Step 66): the MP4, `.srt`, `_chapters.txt` and thumbnail are
  written to `<project>/output/`, not the project folder. Set `output_dir:` or pass
  `--output-dir` to choose another folder. An MP4 left in the project folder by 0.2.0 is not
  found by `export` or `slides`: render again, or pass `--output-dir <project folder>` (the
  flag is relative to the current folder).
- **ffmpeg 4.4 or newer** (Step 64). Crossfades, pushes and wipes now work on ffmpeg 7.0 / 7.1
  (they failed with "frame rate 1/0 is invalid"). With an older ffmpeg, the error names the
  version.
- **`[laugh]`, `[gasp]`, `[sigh]`, `[hmm]`, `[giggle]`, `[groan]` in a beat's text** are now
  voice sounds (Step 99): they are spoken or played as sounds and left out of captions. Before,
  they were read out as text. Such beats get new audio hashes. Other brackets stay as text.
- **`*word*` in a beat's text** marks emphasis (Steps 90–91): the asterisks are removed before
  TTS, captions and readback. Beats with asterisks get new audio hashes. Other beats keep
  theirs.
- **The first render after upgrading renders every scene again**: the scene cache key includes
  the vidgen version.
- **`--jobs` accepts `auto`** (Step 117). A bad value now gives the error `invalid value: 'x'
  (a whole number, or auto)` instead of argparse's message.
- **A Kokoro voice of another language is dubbed** (Step 143): in a video (or variant) whose
  `language:` is not the Kokoro voice's, vidgen now picks a Kokoro voice of the video's language
  of the same kind (female / male) instead of reading the text with the wrong pronunciation and
  only warning. `vidgen validate` prints the choice (`dub [pt]: ...`). Write `lang:` on the voice
  to keep it on purpose, or `dub: {LANG: VOICE}` to choose. Those beats get new audio.
- **Readback transcripts** (Step 141): `vidgen readback` keeps faster-whisper's word
  probabilities in its cache; a cached faster-whisper transcript without them is transcribed
  once more (local, free). Audio for faster-whisper is decoded with the ffmpeg executable.

Cartoon behaviour that changed during the 0.3.0 cycle (cartoons are new in 0.3.0, so this
matters only for projects made with development builds between Steps 67 and 131):

- **Default ambience beds** (Step 128): `ambience: true` by default. Outdoor stages in daylight
  get birdsong, rooms get a quiet room tone, doors creak instead of whooshing, and boats, pours
  and wet steps splash. To keep only the rain and fire beds, set `ambience: false` at the top
  level. `foley: false` turns off all of these sounds.
- **Generated characters' legs** (Step 92): `legs` is split into `leg_left` / `leg_right`
  (with `_lower` shins), and arms gained `arm_left_lower` / `arm_right_lower`. On a generated
  character, a pose of your own with `legs:` does nothing (validate warns) and a `NAME.legs`
  keyframe target is an unknown part. SVG characters may still use one `legs` piece. In an SVG,
  `id="arm_left_lower"` now names a part, not a shape of `arm_left`.
- **Interrupt timing** (Step 102 follow-up): `interrupt: true` without `overlap` now starts 70 %
  of the way into the earlier line's last word (0.2 s before its end without word timings),
  not 0.5 s before the end. It no longer cuts a whole word. Lint `talked_over` reports
  interrupts that cut words.
- **`auto_direct` adds effect symbols** (Step 107) such as `!` and `?` on strong expression
  changes. Use `auto_direct: {effects: false}` to turn them off.
- **Motion effects** (Step 108): with `cartoon_motion: lively` (the default) or `calm`, jumps
  land in dust (impact stars on hard landings), and fast walks, throws and blown props get
  speed lines. Turn them off with `motion_effects: false` or `cartoon_motion: none`.
- **Soft shadows on by default** (Step 97) under characters and props. Use `shadows: false` to
  turn them off.
- **Stage fades** (Steps 116a, 127): a stage fades in, and then out, as one picture instead of
  each thing on its own. Nothing behind another thing shows through during the fade. The first
  and last second of every stage scene look different from before.
- **Smaller seats** (Step 102): chair, box and rock are drawn lower (0.26 / 0.155 / 0.155 of a
  character), and a seated character's hips rest on the seat.
- **Reframing** (Step 96): a stage whose characters do not fit in one view pans to the speaker
  on its own (in 9:16 also laid out at 16:9 width). Set `reframe: none` to stop this.
- **Close-ups by `auto_direct`** (Step 95) are now `shot: closeup` cuts, not 0.03 s zooms.
- **Wind is stronger at `windy` and above** (Step 104). Rain on a stage lands on the ground
  with splashes and has a rain sound bed (Step 105).
- **`vidgen screenplay`** (Steps 113, 115, 130): it now picks from 11 looks (the first six as
  before), then random looks that contrast well. An exit's edge is written as `to` (it was
  `side`, which validate refused). Manner words that name a feeling (`(excited)`,
  `(whispering)`) also set the line's `emotion` (Step 135), so those lines get new audio; a
  `set:` line naming `bench`, `fence`, `log` and the other new outdoor props now places them
  instead of writing a `# TODO` (Step 139).

### Cartoons: characters

- A character model of named vector parts with pivots (67); a parametric generator with body
  shapes, heads, hair, eyes, noses and accessories (68); imported SVG characters split by `id`
  (69).
- Poses and expressions with eased part-by-part changes, plus poses of your own (70). Later
  steps added more expressions: `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`,
  `frightened` (125).
- Lip sync from visemes timed by the stored word timings (71); blinking and idle motion (72).
- Arms and legs that bend, with a two-bone solver (92), and a front view (111).
- Bodies, outfits, patterns, shoes, hair, beards and accessories (113). Original animal
  species: cat, dog, bird, bear, rabbit, mouse (114); fox, owl, frog, turtle, penguin (123).
  Robots and costume pieces (124).
- `vidgen cast --random N` writes a cast whose characters look clearly different from each
  other; lint `look_alike` warns when two characters look too alike (115).
- `vidgen character` and `vidgen character-sheet` (also over MCP) show every pose, expression
  and mouth shape (68, 83).

### Cartoons: stages, sets and props

- The `stage` scene type: a background, a ground, marks, depth (73); parallax layers and a
  camera that can `pan`, `zoom` and `follow` (74); shots `wide` / `two_shot` / `over_shoulder` /
  `closeup` / `medium` (95); vertical videos that follow the speaker (96).
- Props drawn from primitives (75), and SVG props. More props followed: basket, umbrella and
  napkin (103); furniture (110); everyday small props such as cake, book, phone, gift, balloons
  and watering can (122).
- Rooms with walls, floors, windows and doors (109–110); walking in depth (111).
- Props that move by themselves: clock, tv, lamp (120); fireplace, kettle, falling fruit, birds
  (121).
- Vehicles: bicycle, car, bus (118); boat, hot-air balloon, toy rocket (119).
- Reusable casts and sets with `include:` and `set:` (101); `cartoon_style` for generated
  backgrounds (77).
- Ready-made sets for `set: NAME` without writing `sets:`: outdoors `city_street`, `park`,
  `beach`, `forest`, `snowy_hills` (139) and rooms `classroom`, `kitchen`, `shop`,
  `living_room`, `bedroom` (140), with 18 new props (shop, bench, fountain, pine, blackboard,
  school desk, shelf with goods, till...) and marks for two characters and every seat.
- A drawing style for the whole video: `drawing: {outline: thin | normal | bold, shading: flat |
  soft, texture: none | paper | storybook}` (142); the default draws exactly as before.

### Explainer hosts

- `host:` puts a cartoon character beside the content of any explainer scene (bullets, charts,
  code, diagrams...): the content's area shrinks to make room, the host speaks the narration
  with lip sync, and lint rule `host_overlap` checks it (133).
- Host actions `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`,
  `host_exit`, and `auto_direct` for hosts: point at each newly revealed item, react to a
  chart going up or down (134). Example `examples/host-explainer`.

### Cartoons: acting and directing

- Beat actions: `say`, `look_at`, `turn`, `emote`, `pose`, `react` (78); `walk_to`, `run_to`,
  `enter`, `exit`, `gesture`, `jump` (79, 108); `keyframes` and `move_along` (81);
  `pick_up` / `hold` / `put_down` / `give` / `throw` (93); `sit_on`, `stand_up`, `lean_on` (94);
  `get_in` / `ride_to` / `get_out` (118); `effect` symbols (107); `knock`, `pour`, `let_go`,
  `switch_on` / `switch_off`, `open` / `close` (103–128).
- Animation principles built in: anticipation, squash and stretch, overshoot, follow-through
  on a damped spring (`cartoon_motion`; 80, 82). Motion effects such as dust, speed lines and
  impact stars (108).
- `auto_direct`: looks, reactions, gestures, close-ups and effect symbols, planned so that
  lint stays clean; `vidgen direct --print` writes them out as YAML (89, 90, 95, 107).
- Overlapping speech and interruptions (100); voice sounds such as `[laugh]` (99).
- Cartoon lint rules: `off_stage`, `character_overlap`, `bubble_overlap`, `facing_away`,
  `hidden_speaker`, `mouth_without_voice`, `walk_overlap`, `talked_over`, `prop_overlap`,
  `look_alike` (84, 100, 115, 116a). Storyboards include mid-action stills (83).

### Screenplays, cards and transitions

- `vidgen screenplay FILE.md` (also an MCP tool) turns a screenplay into a stage project, with
  looks and voices chosen to suit each character (`FEN (she): ...`) (91, 102 follow-up, 115).
- The `card` scene type for title cards, "Later that day…" cards and end cards; `iris_in` and
  `iris_out` transitions (112).
- Guide topic `cartoons` in `AGENTS.md` / `vidgen guide` (85).

### Weather, light and mood

- `light: day | morning | sunset | night | indoor` and fades between them; soft shadows (97).
- Wind that sways trees and makes hair and scarves trail (98, 104); props that blow away (104).
- Particles: rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks (76, 104).
  Rain lands on the ground, with shelter and puddles (105).
- Snow that settles, and fog (126); lightning with thunder, rainbows, a sun and moon that move
  with the light (127).

### Sound and music

- Foley tied to actions (footsteps, whooshes, pops, boings, thuds, door creaks, splashes) and
  music stings (86, 128). New generated sounds include `bell`, `engine`, `brakes`, `phone`,
  `thunder`, `beep`, `creak`, `knock`, `splash`.
- Ambience beds: rain, fire, birdsong, city, room tone (105, 121, 128).
- New music beds: `cartoon` and `lullaby` (129).
- Composed music: `music: {compose: MOOD}` writes an original piece as notes and plays it with
  real instruments (the optional `music` extra, symusic 0.5.9, and the GeneralUser GS SoundFont,
  downloaded once and checked: `vidgen soundfont fetch`, or `soundfont: PATH` for your own) (145,
  146). Eight moods: `calm`, `focused`, `curious`, `upbeat` for explainers, `playful`, `sleepy`,
  `tense`, `triumphant` for cartoons, with instruments per part and a seed (147). The piece is
  composed for the video's timings: scene changes on bar lines, a mood per scene, swells on
  reveals, pauses before punchlines, a closing cadence, and stings played by the music's own
  instruments (148). Without the extra the mood's built-in bed plays and `vidgen validate` warns;
  drafts and animatics play it too; `vidgen music preview` (MCP `music_preview`) writes a piece
  as WAV and MIDI (147, 149). `examples/host-explainer` and `examples/cartoon-rain-check` use it.

### Narration and pictures

- OpenRouter narration: `voice: {provider: openrouter, ...}`. One provider per video, with
  price estimates in the dry run (62, 63).
- Free local narration with Kokoro: `voice: {provider: kokoro}`, installed with the `kokoro`
  extra on Python 3.10–3.12 (65).
- OpenRouter pictures, `imagegen: {provider: openrouter}` (61); vector pictures with
  `generate: {format: svg}` and `.svg` files in `image` scenes, drawn, recoloured and cleaned up
  (61b). A clear message when the account's privacy settings block a model (Zero Data
  Retention).
- Lines with feeling: `emotion:` on a beat or a voice (13 emotions such as `excited`, `sad`,
  `whisper`, `doubtful`, or your own speed / pitch / gain / pauses). Kokoro changes speed,
  pitch, loudness and pauses (135); ElevenLabs v3 gets audio tags, other ElevenLabs models voice
  settings, OpenRouter models instructions or the same audio changes (136). Kokoro voice blends
  with weights: `af_heart+af_bella:0.6` (135).
- Dubbing: `dub: {LANG: VOICE}` on voices, automatic Kokoro voices of the same kind for a
  translated variant, lip sync and timings from each language's audio, and `--all-languages`
  on `tts`, `render` and `lint` (MCP `render` / `lint`) (143). `examples/cartoon-music-box`
  has a Brazilian Portuguese variant.
- `vidgen readback` flags single words the recogniser was unsure of or heard after an odd pause,
  with the time in the video and a suggested fix; `vidgen lint --readback` reports them as rule
  `unclear_speech` (141).

### Rendering and tooling

- `--jobs auto` on `render`, `storyboard`, `lint`, `thumbnail`, `slides`, `gallery` and MCP
  uses as many jobs as the available memory allows, at 1.5 GB per job (117).
- Faster cartoon renders: static layers stay in Manim's static image, and part drawings are
  cached (87).
- Works with Manim 0.22 (64).
- `vidgen render --draft`: a quick render at about 8 fps and 240 px without decoration (idle
  motion, wind, shadows, particles, light grade), every timing kept, in its own `build/draft`
  folder and `_draft.mp4` (137).
- `vidgen animatic` (also an MCP tool): the storyboard's stills timed to the narration with the
  video's audio and captions, joined by ffmpeg in seconds (138).
- Examples: `examples/cartoon`, `cartoon_series`, `screenplay`, `svg_character`,
  `cartoon-music-box`, `cartoon-rain-check`, `cartoon-muffin-mystery`, `cartoon-rainbow-ride`,
  `host-explainer`.
- Reviews 63, 88, 102, 116, 130, 144 and 149, and full test suite runs (131, 144), fixed what
  they found (4042 tests passed in Step 144's full run).

### Known gaps

- No human has listened to the generated sounds and beds; the composed music was chosen by a
  listening test of the renderer, but the moods and fitted pieces await one. Windows and macOS were not run
  here: see `docs/WINDOWS-CHECK.md`. The open items are listed under "Backlog" in
  `tasklist.md`.
