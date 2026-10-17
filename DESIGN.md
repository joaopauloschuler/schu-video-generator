# schu-video-generator — design spec

A configurable generator for narrated, animated explainer videos (Manim + ElevenLabs + ffmpeg).
The project and pip distribution are called `schu-video-generator`; the command (`vidgen`, also
`vidgen-mcp`) and the Python package (`vidgen`, `src/vidgen/`) are `vidgen`, and so is every name
below unless it says otherwise. `vidgen.DIST_NAME` (`"schu-video-generator"`) is used where the
distribution is meant: install hints of the optional extras (`schu-video-generator[pdf|stt|mcp]`),
the PDF deck's creator and the HTML deck's `generator`, and the MCP server's advertised name. The
JSON envelope key `vidgen`, the `vidgen://` MCP resources and `--version` (`vidgen 0.3.0`) keep
the command's name.
It generalises the one-off `kphi3_paper_video` project: the pipeline is shared, each video is a
**project folder** with a config file, and each project can **extend** the tool with its own
scene types, helpers, theme tokens and pipeline hooks.

Status of this document: describes the implemented system (version 0.3.0: the version 0.1
contract after the Step 7 review, plus the roadmap steps 8–60 (version 0.2.0) and 61–131
(version 0.3.0) in tasklist.md recorded in §11 onwards; §63 is the 0.2.0 review and lists what
changed for users of 0.1; `CHANGELOG.md` lists what changed from 0.2.0 to 0.3.0). Sections 1–9 give the original contract; the "Refinements (Step N)" lists record how
each step made it precise, and where a refinement differs from the text above it, the
refinement is what the code does. Changing a public interface requires updating this file in
the same commit and noting it in HANDOFF.md. User documentation: README.md, docs/CONFIG.md
(every config key, checked by `tests/test_docs.py`) and docs/EXTENDING.md.

---

## 1. Goals and non-goals

Goals
- One engine, many videos. A new video = a new project folder, no engine edits.
- Config-only videos for common explainers (built-in scene library).
- **First-class extensibility**: any project can add new scene types, helpers, theme tokens and
  hooks in its own `extensions/` folder, and use them from config by name. A project extension can
  later be promoted into the core library unchanged.
- Narration-driven timing: every beat's animation lasts as long as its audio (+ padding).
- Incremental work: TTS only for changed beats; render one scene at a time; fast previews.
- Runs on Windows (primary user platform), Linux and macOS.

Non-goals (for now)
- Voice providers other than ElevenLabs (keep a small seam, but implement ElevenLabs only).
- Declarative animation DSL. Complex animation lives in Python scene classes.
- GUI / web editor.

## 2. Repository layout

```
pyproject.toml            # package "vidgen", console scripts `vidgen` (+ `vidgen-mcp`, §62), Python >= 3.10
src/vidgen/
  __init__.py             # __version__
  __main__.py             # `python -m vidgen` -> cli.main()
  api.py                  # THE public surface for project extensions (see §6)
  cli.py                  # argparse CLI (see §8)
  jsonout.py              # --json documents of the CLI (see §11)
  describe.py             # scene-type/params descriptions for list-scenes
  guide.py                # `vidgen guide`: the author guide for AI agents, its topics (§59)
  gallery.py              # `vidgen gallery`: samples from the guide, work project, stills / GIFs, pages (§60)
  outline.py              # Markdown outline / plain-text script -> blocks; inline Markdown removal (§61; no manim)
  prose.py                # sentences (language-aware), beats of 6-15 words, on-screen label compression (§61; no manim)
  plan.py                 # `vidgen plan`: blocks -> planned scenes (cue -> type, beats fitted to steps, TODOs) (§61; no manim)
  plan_yaml.py            # `vidgen plan` output: commented video.yaml writer, project scaffold, assets (§61; no manim);
                          # also writes `vidgen screenplay`'s project (commented_yaml, write_project)
  screenplay.py           # `vidgen screenplay`: screenplay -> stage scenes, set, direction grammar, looks, voices (§69.25; no manim)
  random_cast.py          # `vidgen cast --random N`: seeded well-contrasted looks, names, voices; screenplay looks (§69.49; no manim)
  mcp_server.py           # `vidgen mcp`: MCP server (optional SDK), tools = CLI subprocesses with --json, resources (§62)
  mcp_tools.py            # its SDK-free parts: root folder policy, command lines, cost refusal, pictures, paging (§62)
  schema.py               # JSON Schema export (see §12)
  errors.py               # VidgenError, Problem
  config.py               # pydantic v2 models for video.yaml (see §4)
  project.py              # Project: locate/load config, resolve paths, variants
  theme.py                # Theme object (colors, fonts, sizes, background, code style; precedence §19)
  fonts.py                # bundled fonts (data/fonts/, OFL), Pango registration, font roles (§21)
  presets.py              # theme presets: seven built-in presets (§19, §20)
  scales.py               # type scales compact / standard / large / auto, frame orientation (§20)
  themelist.py            # `vidgen list-themes`: preset listing, JSON entries, swatch PNG (§20)
  icons.py                # icon registry: vendored set + project assets/icons, search (§22; no manim)
  icon_mobject.py         # icon() / Icon: SVG -> recoloured VGroup with scaling strokes (§22); SvgDrawing base
  svgclean.py             # SVG sanitiser (scripts, filters, rasters, text out; gradients flattened; caps) + theme_color (§65; no manim)
  vector_mobject.py       # load_vector() / VectorPicture: a sanitised SVG as Manim shapes (§65)
  cartoon/                # cartoons (§69): character.py (Character: named vector parts with pivots,
                          # poses, mirroring; character(); part drawings cached by look, §69.20), cast.py (characters: lookups, checks; no manim),
                          # generator.py (look: parameters -> parts, §69.1), clothes.py (outfits,
                          # patterns, shoes, things worn on the body, §69.47), animals.py (species:
                          # heads, paws, wings, tails, a beak that talks, §69.48), robots.py (species
                          # robot: heads, screen face, antenna, joints, wheels, §69.58), costumes.py
                          # (crown, wizard hat, party hat, cape, §69.58), expression_shapes.py
                          # (Step 125 eyes, mouths, cheeks, hair standing up, §69.59), contrast.py (how
                          # clearly two looks differ, §69.49; no manim), primitives.py (the
                          # generator's shapes, trailing and outer-hair marks, outline maths), svg_look.py (look: {svg} -> parts by
                          # element ids, §69.2), still.py (`vidgen character --png`), poses.py (pose and
                          # expression tables, §69.3; no manim), transition.py (PoseChange, §69.3;
                          # Walk, Gesture, Jump, §69.12; KeyedMotion, §69.14),
                          # visemes.py (lip sync: viseme tracks, .visemes.json, §69.4; no manim),
                          # idle.py (blinking, breathing, head sway: the seeded schedule, §69.5; no manim),
                          # host.py (host: which host a scene has, its column / band, who speaks, checks,
                          # §71; pointing and moving geometry, §71.1; no manim), host_drawing.py
                          # (HostFigure: the host and its floor line, §71), host_directing.py (the
                          # host's automatic directing, RevealStep, §71.2; no manim),
                          # stage.py (marks, ground line, depth, draw order of a stage, §69.6; parallax
                          # layer offsets and extents, §69.7; no manim), props.py (Prop, draw_prop,
                          # svg_prop: props from primitives or an SVG, §69.8), acting.py (where a
                          # character looks: look_pose, camera_look, §69.11; walk times and cycle,
                          # entrances and exits, gestures, jumps, §69.12; no manim), motion.py
                          # (animation principles: anticipation, squash and stretch, overshoot,
                          # follow-through, cartoon_motion, §69.13; no manim), keyframes.py (keys,
                          # eases, motion paths, §69.14; no manim), spring.py (Spring: a damped
                          # spring for secondary motion, §69.15; no manim), foley.py (the sounds
                          # of actions as they played, §69.19; no manim), directing.py
                          # (auto_direct: the looks, reactions, gestures and close-ups it adds,
                          # checked by the lint rules on predicted stills, `vidgen direct`,
                          # §69.23, §69.24; no manim), limbs.py (arms and legs in two segments: the
                          # two-bone solver, folded one-piece limbs, §69.26; no manim), holding.py
                          # (props in hands: Holdings, where held / put-down / thrown props go, the
                          # replay vidgen validate runs, §69.27; no manim), seating.py (seats,
                          # lean edges, Postures, seated feet and the crouch, §69.28; no
                          # manim), shots.py (the framings of a beat's shot:, §69.29; no
                          # manim), reframe.py (reframe: the camera keeps the speaker in view,
                          # the landscape stage a narrow frame crops, §69.30; no manim),
                          # lighting.py (light presets, grades, fades, stars and shadow ellipses,
                          # §69.31; no manim), shading.py (StageLight: the grade as the camera
                          # draws, StarField, StageShadows, §69.31), drawing_style.py (the
                          # drawing: outline / shading / texture as the camera draws and the
                          # renderer writes, §79), wind.py (wind levels,
                          # seeded gusts, fades, sway and trailing angles, §69.32; the felt
                          # force and a blown prop's path, §69.38; no manim),
                          # windblown.py (SwayingProp, StageWind, §69.32), rain.py (rain on a
                          # stage's ground: landing band, shelter boxes, splashes, puddles,
                          # §69.39; no manim), effects.py (effect symbols: shapes, spots on
                          # the head, motion, pop, §69.40; no manim), effect_symbols.py
                          # (EffectSymbol: drawn and following a head, §69.40),
                          # motion_effects.py (dust, speed lines, impact stars, whoosh: when
                          # they fire and their shapes, §69.41; no manim),
                          # motion_effect_shapes.py (MotionEffect, §69.41), room.py (rooms:
                          # wall, floor, windows, the sky outside, §69.42; no manim),
                          # room_drawing.py (draw_room, WindowViews, §69.42), cards.py (title
                          # cards: layout, burst rays, outlined text colours, §69.46; no manim),
                          # vehicles.py (seats, wheels, pedals, get-in reach, §69.52; no manim),
                          # vehicle_drawing.py (the bicycle, car, bus, boat, balloon and toy
                          # rocket, §69.52-53), riding.py (Ride, riders on their seats,
                          # pedalling, §69.52), vehicle_paths.py (waves, bobbing, balloon and
                          # rocket paths, smoke, §69.53; no manim), water.py (a stage's water,
                          # §69.53), living.py (clock hands, a tv's picture and flicker, glows,
                          # switches, what is redrawn over moving parts, §69.54; no manim),
                          # living_drawing.py (LivingProp, PropGlow, PropSteam, §69.54-55),
                          # nature.py (fruit spots, a dropped fruit's fall and bounce, flocks of
                          # birds, §69.55; no manim), nature_drawing.py (Flock, FallenFruit,
                          # FruitDrop, hit_stars, §69.55), small_props.py (balloons floating away,
                          # a pour's tilt and drops, §69.56; no manim), small_props_drawing.py
                          # (Pouring, WaterFlow, WaterDrops, §69.56), snow.py (snow that settles:
                          # top lines, the layer's steps, blanket and caps, flakes on their floors,
                          # §69.60; no manim), fog.py (fog bands by depth, their opacities and
                          # waves, §69.60; no manim), storm.py (lightning strikes, their flashes,
                          # bolts, thunder, rain storms, rainbows, §69.61; no manim), sun_path.py
                          # (the sun's and moon's path across the sky, shadows cast by a low sun,
                          # §69.61; no manim), weather_drawing.py (SettledSnow, SnowBlanket,
                          # SnowCap, StageFog, FogBand, §69.60; LightningBolt, Rainbow,
                          # StageRainbow, SkyBody, §69.61); still.py also
                          # draws the prop, furniture, small-prop and vehicle galleries (§69.43), the look gallery
                          # (§69.47) and `vidgen character-sheet` (§69.16)
  iconlist.py             # `vidgen list-icons`: listing, JSON, contact sheet, docs/ICONS.md (§22, §23)
  registry.py             # scene-type and action-type registry
  actions.py              # per-beat actions: Target, Action, validation, ActionRunner (§26)
  extensions.py           # discovery + import of project extensions
  hooks.py                # hook registry + dispatch
  runtime.py              # "current project/theme" context used by helpers and extensions
  scene.py                # NarratedScene base class + narrate()
  camera.py               # camera views kept inside bounds (zoom, pan, follow, a wide stage; §69.7; no manim)
  particles.py            # particle kinds, count cap, seeded positions over time (§69.9; no manim)
  particle_field.py       # ParticleField: draws the particles over the camera's view, shared options (§69.9);
                          # rain splashes, Puddles (§69.39)
  ambience.py             # the generated sound beds (rain, fire, birdsong, city, room tone): seamless loops, levels, ducking, which a set plays (§69.39, §69.55, §69.62; no manim)
  capture.py              # frame capture: stills at beat ends / N per beat (see §13); mid-action stills (§69.16)
  introspect.py           # layout dump of the captured frames: objects, px boxes, sizes (§15)
  activity.py             # activity file: beat timings, play log, per-frame motion signal (§17)
  storyboard.py           # `vidgen storyboard`: reuse/render stills, write contact sheets (§14)
  sheets.py               # contact-sheet layout and drawing with Pillow (§14)
  lint/                   # `vidgen lint` (§16, §17): rules.py (framework), layout_rules.py,
                          # cartoon_rules.py (characters, §69.17), timing_rules.py, readback_rule.py (§57, §78),
                          # color.py, run.py (lint_project), findings.py, report.py
  helpers.py              # theme-aware text helpers and generic drawing utilities
  layout.py               # fit/wrap text, beat distribution, chart numbers, LaTeX detection
  regions.py              # layout regions: safe area, named regions, grids, place(), readable text (§18)
  graph.py                # layered layout of directed graphs, pure Python (§31; no manim)
  callouts.py             # callouts: areas, label placement, box, circle, arrow, magnifier, spotlight (§37)
  clips.py                # video clips: probe, timing, ClipMobject (frames decoded per frame), clip sound (§38)
  geo.py                  # world map data, country lookup, Equal Earth projection, MapView (§39; no manim)
  videoplan.py            # the planned timeline: scene / beat positions in the video before rendering (§41),
                          # planned chapters and video_chapters() (§42)
  chapters.py             # chapter marks from `chapter` scenes and scenes' `chapter:` keys; their checks (§42)
  chapter_export.py       # published chapters (intro at 0:00), MP4 FFMETADATA + tags, YouTube list and rules (§52)
  thumbnail.py            # the thumbnail: a scene's frame or a designed card, small copy, legibility checks (§53)
  export.py               # `vidgen export gif|clip`: palette GIF with a size budget, MP4 clip copy / encode (§53)
  deck.py                 # slide decks' key frames: stills per beat / scene, dedupe, notes, timeline (§55)
  slides.py               # `vidgen slides`: one self-contained HTML deck (data/slides/deck.css, deck.js) (§55)
  slides_pdf.py           # `vidgen slides --format pdf`: slide / notes pages, title page, outline (fpdf2, §56)
  overlays.py             # overlays: Overlay base, OverlayContext, config entries, validation, reserve (§41)
  overlay_layer.py        # OverlayLayer: overlays composited into every frame a scene writes (§41)
  charts.py               # chart helpers: ticks, number labels, axes, legend, markers, fit (§33),
                          # colour scales, colour bar, readable text on fills (§34)
  tts/__init__.py         # provider seam: get_provider(cfg), tts_warnings (§66)
  tts/elevenlabs.py       # ElevenLabs provider (stdlib urllib), cache by hash
  tts/openrouter.py       # OpenRouter TTS provider: /audio/speech, PCM -> MP3, prices, ZDR message (§66)
  tts/kokoro.py           # local Kokoro-82M provider (extra schu-video-generator[kokoro]): engine, MP3, timings (§68)
  kokoro_voices.py        # Kokoro's languages and voices, voice / lang resolution, weighted blends, validate warnings (§68, §72)
  tts/prosody.py          # an emotion applied to speech: pauses by word timings, soft-limited gain, pitch filter (§72)
  emotions.py             # emotion: the table (speed, pitch, gain, pauses), manner words (§72; no manim)
  stt/                    # speech-to-text seam (§57): __init__.py (STTProvider, Transcript, stt_settings,
                          # get_stt_provider), faster_whisper.py (local, extra schu-video-generator[stt]), elevenlabs.py
  readback.py             # `vidgen readback`: transcripts cached, aligned with the spoken text, WER, edits, suggestions (§57)
  speech_flags.py         # word flags: low recogniser confidence, pauses inside sentences, differences; fixes (§78; no manim)
  textnorm.py             # text normaliser for readback: case, accents, hyphens, numbers to words (en, pt) (§57; no manim)
  imagegen/               # generated images (§58): __init__.py (GenerateImage, ImageRequest, cache keys, prompt
                          # helpers, warnings), openai.py (OpenAI Images provider), openrouter.py (OpenRouter
                          # provider, §64; SVG and data-policy errors, §65), placeholder.py, run.py (`vidgen imagegen`)
  httpapi.py              # POST with retries / scrubbed errors (+ a plain GET), shared by the ElevenLabs, OpenAI and OpenRouter providers (§58, §64)
  render/                 # worker.py (one scene per process), pipeline.py, ffmpeg.py,
                          # fingerprint.py (what a scene's render depends on, §14),
                          # jobs.py (`--jobs auto`: memory and cores, §70)
  subtitles.py            # SRT from beat timings (cues cut and timed like captions, §43)
  speech.py               # spoken words, speech bounds of an MP3, word times: estimate / TTS alignment (§43)
  pronunciation.py        # pronunciation dictionary: TTS text of a beat, spoken -> written word map (§45; no manim)
  voicesounds.py          # [gasp] [laugh] ... in a beat's text: markers, what each voice says, sound times (§69.33; no manim)
  overlap.py              # overlap: / interrupt: beats: windows, voice shapes (dip / cut), talked-over words (§69.34; no manim)
  includes.py             # include: files and named sets: merge rules, set: of a stage (built-in sets, §76), where problems are written (§69.35; no manim)
  voices.py               # named voices: effective voice per beat, speaker labels / colours / tags (§46; no manim)
  languages.py            # language tags and per-language rules: cue words, speech rate, TTS / MP4 codes (§54; no manim)
  translation.py          # translation files: text markers, keys, extracting, applying, merging, warnings (§54; no manim)
  dubbing.py              # each voice's voice in the video's language (dub:, automatic Kokoro picks), --all-languages (§80; no manim)
  cues.py                 # caption cues: phrase-boundary cutting and timing, shared by SRT and captions (§43)
  sfx.py                  # sound effects: synthesised set, loudness, project sounds, the SFX track (§47; no manim)
  music.py                # background music: generated beds, music files and composed music as looping sources (§48, §82, §83; no manim)
  composer.py             # composed music from a mood: moods, instruments, chords, phrases, melody, accompaniment (§83; pure, seeded, no manim)
  musicfit.py             # composed music that follows the video: bar lines at scene changes, per-scene moods, swells, pauses, cadence, stings (§84)
  score.py                # composed music as notes: Score / Part / Note / Section, beats to seconds, key signatures, .mid export (§82; no manim)
  soundfont.py            # the SoundFont of composed music: GeneralUser GS download, size / SHA-256 check, cache folder, soundfont: (§81; no manim)
  synth.py                # composed music played with symusic (optional extra music): install check, per-part render, numpy mix, reverb, cache (§81, §82; no manim)
  mix.py                  # the final mix: music placement, ducking, normalisation, limiter (§48; no manim)
  loudness.py             # BS.1770-4 integrated loudness and true peak, block by block (§48; no manim)
  transitions.py          # scene transitions: effective transition, frame math, colour fade and irises (§69.45), voice track, xfade names (§49-50; no manim)
  carry.py                # continuity: carried objects' record, rebuild and move, carry checks (§50; manim imported lazily)
  fileio.py               # atomic writes; replacing files that Windows programs keep open
  scenes/                 # built-in scene library (registered like extensions; actions.py:
                          # the built-in beat actions reveal/dim/highlight/zoom/transform, §26-27,
                          # pan/follow, §69.7;
                          # callout_action.py: the callout beat action, §44; sfx_action.py: sfx, §47;
                          # particles_action.py: particles, §69.9; acting.py: say, look_at, turn,
                          # emote, pose, react and the speech bubble, §69.11; moving.py: walk_to,
                          # enter, exit, gesture, jump, §69.12; keyframes_action.py: keyframes,
                          # move_along, §69.14; handling.py: pick_up, hold, put_down, give,
                          # throw, §69.27, open, close, §69.37, blow_away, §69.38;
                          # sitting.py: sit_on, lean_on, stand_up, §69.28;
                          # shot_action.py: shot (the beat key shot:), §69.29;
                          # light_action.py: light (a stage's light fades), §69.31;
                          # wind_action.py: wind (a stage's wind fades), §69.32;
                          # effect_action.py: effect (a symbol over a head), §69.40;
                          # switch_action.py: switch_on, switch_off (a tv or a lamp), §69.54;
                          # storm_action.py: lightning, rainbow, §69.61;
                          # knock_action.py: knock (a door), §69.62;
                          # host_actions.py: host_point, host_look, host_react, host_move,
                          # host_enter, host_exit (the scene's host), §71.1;
                          # overlays.py: the built-in overlays lower_third/watermark, §41;
                          # progress.py: progress_bar/chapter_indicator, §42; captions.py: captions, §43;
                          # stage.py: the stage scene type, §69.6; card.py: the card scene type, §69.46)
  data/fonts/             # Inter, Source Serif 4, JetBrains Mono NL (.ttf + OFL.txt; package data)
  data/icons/             # manifest.json + lucide/*.svg + lucide/LICENSE (ISC; package data, §22)
  data/geo/               # world-110m.json: Natural Earth 1:110m countries (public domain; package data, §39)
  data/slides/            # deck.css + deck.js inlined into `vidgen slides` pages (package data, §55)
  data/guide/             # AGENTS.md: the author guide printed by `vidgen guide` (package data, §59)
  data/gallery/           # stand-in files for the guide snippets' assets/ paths: picture.png, app.png, clip.webm (§60)
  data/openrouter/        # tts_models.json: OpenRouter's TTS models, voices, list prices, ZDR (dated snapshot, §66)
  data/kokoro/            # voices.json: Kokoro-82M's languages, voices and grades (dated, §68)
  data/sets/              # outdoors.yaml, indoors.yaml: the built-in stage sets `set: NAME` falls back to (§76, §77)
tools/                    # maintainer scripts, not shipped: vendor_icons.py + icon_set.json (§22, §23),
                          # make_screenshot.py, make_clip.py (example assets, §37, §38),
                          # make_gallery_clip.py (data/gallery/clip.webm, §60),
                          # make_sets_gallery.py (docs/gallery/media/sets_outdoors.png, §76),
                          # make_world_map.py (builds data/geo/world-110m.json from npm packages, §39)
tests/                    # pytest; no network; slow renders marked `render`
examples/
  minimal/                # config-only example using built-ins
  custom_scene/           # built-ins + one extension scene type, helper module, variant, hook
  kphi3/                  # migrated paper video, custom scenes as extensions
  plan/                   # outline.md + the unedited draft video.yaml `vidgen plan` writes from it (golden file, §61)
  cartoon/                # a two-scene cartoon, two generated characters, Kokoro voices, no audio (§69.18)
  cartoon_series/         # shared/cast.yaml + shared/sets.yaml included by two short episodes, no audio (§69.35)
  cartoon-music-box/      # the screenplay example after hand editing, most Phase I features, no audio
docs/
  CONFIG.md               # config reference
  EXTENDING.md            # how to write project extensions
  ICONS.md                # icon catalogue, generated from the manifest by tools/vendor_icons.py (§23)
  gallery/                # scene gallery written by `vidgen gallery`: README.md, <type>.md, media/ (§60)
AGENTS.md                 # the author guide for agents *using* vidgen (copy of data/guide/AGENTS.md, §59)
DESIGN.md  CLAUDE.md  HANDOFF.md  README.md  THIRD_PARTY_NOTICES.md (bundled fonts §21, icons §22, world map §39)
```

## 3. Project folder layout

```
my_video/
  video.yaml              # config (video.json also accepted)
  extensions/             # optional; every *.py and every package here is auto-imported
  assets/                 # images, data files referenced by scenes (paths relative to project)
    icons/                #   optional project icons <name>.svg (+ icons.json: category, tags) (§22)
    generated/            #   `vidgen imagegen`: <key>.png + <key>.json per generated picture (committed, §58)
  translations/           # optional: translation files of language variants (`vidgen translate-template`, §54)
  audio/                  # generated: <beat_id>.mp3 + <beat_id>.hash  (kept, cheap to reuse)
    <variant>/            #   only for a variant whose voice or beat texts differ (§7)
  build/                  # generated: manim media, per-scene mp4, timings json, concat list
  output/                 # the deliverables (Step 66; `output_dir:` / `--output-dir` move it, see §4)
    <output>.mp4          #   final video   (<output>_preview.mp4 for previews, <output>_draft.mp4
    <output>.srt          #                 for drafts (§74), <output>_<variant>.mp4 for variants)
    <output>_chapters.txt #   YouTube chapter list, when the video has chapters (Step 49, §52)
    <output>_thumbnail.png#   thumbnail (+ .jpg), `vidgen thumbnail` / render with `thumbnail:` (Step 50, §53)
    <output>_animatic.mp4 #   `vidgen animatic`: storyboard stills timed to the narration (Step 138, §75)
  exports/                # `vidgen export`: GIFs and MP4 clips of parts of the video (Step 50, §53); `vidgen slides` decks (§55, §56)
```

`build/<final|preview>[_<variant>]/` (Step 4; `build/draft[_<variant>]/` for drafts, Step 137, §74) holds: `scenes/<id>.mp4` (the scene as rendered,
with Manim's own audio) and `scenes/<id>.wav` (Manim's uncompressed sound mix, only if the scene
has sound), `timings/<id>.json` (beat timings + the render settings), `media/` (Manim's
intermediate files), `padded/<id>.wav` (each scene's audio padded to its exact video length) with
`padded/video_concat.txt` / `audio_concat.txt`, and `timings.json` (the whole video). Step 44 /
45 add `padded/sfx.wav` (the sound effects, §47) and `padded/mix.wav` (the final mix with
music / normalisation, §48); Step 46 `padded/voice.wav` (the scenes' sound summed where
crossfades overlap them) and `padded/video_concat_<k>.txt` (runs of cut-joined scenes, §49);
Step 47 `scenes/<id>.overlay.mov` (the overlays of the frames a push / wipe into the scene
moves, RGBA) and `carry/<id>.json` (the objects the next scene carries out of it, §50);
Step 49 `padded/metadata.txt` (the MP4's tags and chapters, FFMETADATA, §52); Step 50
`thumbnail/<name>_small.png` (the thumbnail at YouTube's small size, §53) and, for a frame
thumbnail without overlays, a sibling folder `build/<final|preview>[_<variant>]_bare/` (scene
renders of the project without overlays, §53). Step 54: `build/readback/<key>.json` (speech-to-text
transcripts of the beats' MP3s, keyed by audio content + STT settings, shared by qualities and
variants, §57). Step 55: `build/imagegen/<key>-<look>.png` (placeholder cards of generated pictures
not made yet, §58). With `--frames` (Step 10, §13) also `frames/<id>/*.png` + `frames/<id>/index.json` and
`frames/index.json`, and `layout/<id>.json` (Step 12, §15).

## 4. Config schema (`video.yaml`)

Pydantic v2 models in `config.py`. Unknown top-level keys are an error (typo protection);
`params` of scenes and `theme.colors` are open dictionaries.

```yaml
title: "Saving 77% of the Parameters in LLMs"   # required
output: kphi3_video                              # basename of output files; default: folder name

format:                                          # final render
  width: 1920
  height: 1080
  fps: 30
preview:                                         # `--preview` render
  width: 854
  height: 480
  fps: 15

variants:                                        # optional named overrides, deep-merged onto the config
  vertical:
    format: {width: 1080, height: 1920}
    preview: {width: 480, height: 854}

theme:
  preset: light_academic                         # optional (Step 16, §19); values below still win
  background: "#0E1116"
  font: Inter                                    # sans family (Step 18: bundled, §21)
  font_serif: Source Serif 4                     # serif family (Step 18)
  font_mono: JetBrains Mono NL                   # mono family, code listings (Step 18)
  fonts: {heading: serif}                        # font roles -> sans/serif/mono or a family (Step 18)
  code_style: github-dark                        # Pygments style of `code` listings (Step 16)
  scale: auto                                    # type scale (Step 17, §20): compact/standard/large/auto
  colors:                                        # open dict; these names are the defaults
    text: "#E8EAED"
    dim: "#838B98"                               # Step 16 (was #6B7280, below WCAG AA)
    accent: "#FF6B6B"
    highlight: "#FFD166"
    primary: "#58C4DD"
    secondary: "#F2A541"
    tertiary: "#83C167"
    surface: "#161B24"                           # panels / code background (Step 5)
    # projects may add any name, e.g. k2: "#F2A541"
  palette: ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]   # ordered series colors (charts, groups)
  sizes: {title: 56, subtitle: 42, heading: 36, body: 32, caption: 24, small: 20}

voice:
  provider: elevenlabs                           # or openrouter (Step 62, §66: model, voice, instructions, speed)
                                                 # or kokoro (Step 65, §68: voice, speed, lang, device)
  voice_id: nPczCjzI2devNBz1zQrb
  model_id: eleven_multilingual_v2
  output_format: mp3_44100_128
  settings: {stability: 0.55, similarity_boost: 0.75, style: 0.0, use_speaker_boost: true}
  context: true                                  # send previous_text/next_text for continuity

narration:
  pad: 0.35                                      # seconds of silence after each beat
  words_per_second: 2.6                          # duration estimate when a beat has no audio

pronunciation: {K-Phi-3: kay fye three}          # Step 42 (§45): TTS text only; + pronunciation_file
voices: {ana: {voice_id: 21m00Tcm4TlvDq8ikWAM, label: "Dr. Ana"}}   # Step 43 (§46): + scene / beat `voice: ana`
subtitles: {speakers: off}                       # Step 43 (§46): `name` tags speakers in the SRT
sfx: {auto: false, gain: 0}                      # Step 44 (§47): + scene `sfx:` lists, beat action `sfx`
music: calm                                      # Step 45 (§48): bed / file / cue / cues; + scene `music:`
audio: {normalize: auto, target_lufs: -16, true_peak: -1.5}   # Step 45 (§48): the final mix
transition: crossfade                            # Step 46 (§49): default between scenes; + scene `transition:`
                                                 # Step 47 (§50): push / wipe {direction, soft}; scene `carry:`
chapters: {metadata: true, youtube: true, intro: Intro}   # Step 49 (§52): MP4 chapters, <output>_chapters.txt
metadata: {artist: "Jane Doe"}                   # Step 49 (§52): MP4 tags (title defaults to `title`)
thumbnail: {title: "Saving 77%", icon: cpu}      # Step 50 (§53): designed card, or {scene, beat, at, overlays}
language: en                                     # Step 51 (§54): BCP-47; cue rules, speed lint, TTS / MP4 language
translations: translations/pt.yaml               # Step 51 (§54): usually in a variant; texts replaced at load
stt: {provider: faster_whisper}                  # Step 54 (§57): speech to text of `vidgen readback`
imagegen: {model: gpt-image-1, style: flat}      # Step 55 (§58): generated pictures (`generate:` params); provider: openrouter (§64)

extensions: [extensions]                         # dirs (relative to project) to auto-import; default shown

scenes:
  - id: intro                                    # required, unique, [A-Za-z0-9_]+
    type: title                                  # registered scene type (built-in or extension)
    params:                                      # validated by the scene type's Params model, if any
      title: "Saving 77% of the Parameters"
      subtitle: "in Large Language Models"
    beats:
      - id: s1_b1                                # optional; default f"{scene.id}_b{n}" (1-based)
        text: "What if a large language model ..."
      - text: "This technical report ..."
```

Validation rules: beat ids unique across the whole video; scene ids unique; `type` must be
registered after extensions load (`vidgen validate` reports unknown types with the list of known
ones); `params` validated against the scene class's `Params` model when it defines one.

Refinements (Step 1):
- Unknown keys are rejected in every structural model (not only top level): `format`, `preview`,
  `theme`, `voice`, `voice.settings`, `narration`, scenes and beats. Open: `params`,
  `theme.colors`, `theme.sizes`, and the bodies of `variants` (validated after merging).
- `theme.colors` / `theme.sizes` / `theme.palette` in the config hold only what the user wrote;
  `Theme` merges them over the built-in defaults shown above. Color values must be hex
  (`#RGB`, `#RRGGBB` or `#RRGGBBAA`); token names follow the id pattern.
- **Silent scenes**: a scene may have no beats (`beats: []` or omitted) if it sets
  `duration: <seconds>`; `duration` is an error on a scene that has beats (narrated scenes are
  timed by their audio).
- Variants: the variant mapping is deep-merged onto the raw config (mappings merge recursively,
  lists such as `scenes` and scalars replace), then the result is validated. A variant may not
  contain `variants`. `vidgen validate` checks the base config and every variant.
- `output` defaults to the project folder name and must be a plain file name (no path separators).
- **Output folder** (Step 66): the deliverables — `Project.output_path` (MP4), `srt_path`,
  `chapters_path`, `thumbnail_path` — live in `Project.output_dir`, the one property that decides
  it: the CLI's `--output-dir DIR` (`Project.load(..., output_dir=)`, resolved from the current
  directory; on `render`, `thumbnail`, `export`, `slides`) wins over the top-level
  `output_dir:` (relative to the project root, or absolute; a variant may set its own), else
  `<root>/output`. The path is not created on access; the render creates it before joining
  (thumbnails via `write_bytes_atomic`). `build/` and `exports/` stay under the root. No
  fallback to a video left in the root by older versions. `output_dir` is a confined path key
  under `vidgen mcp` (§63).
- `extensions` entries are directories relative to the project root; `Project.asset(rel)` also
  resolves relative to the project root (e.g. `assets/logo.png`).

## 5. Scene runtime

### 5.1 `NarratedScene` (in `scene.py`, subclass of `manim.Scene`)

Attributes available inside `construct()`:
- `self.spec` — the `SceneConfig` from video.yaml
- `self.params` — validated params (instance of the class's `Params` model, or a plain dict)
- `self.beats` — list of `BeatConfig` in order
- `self.theme` — the active `Theme`
- `self.project` — the active `Project` (paths: `self.project.asset(rel)` resolves assets)

Methods:
- `with self.narrate(beat) as d:` — `beat` is a beat id **or** 0-based index into `self.beats`.
  Adds the beat's MP3 (if present) at the current time, yields its duration `d` (audio length,
  or the word-count estimate), and on exit waits until `d + pad` has elapsed. Records
  `(beat_id, start, end, text)` into `self.beat_log` (used for subtitles).
- `self.beat_duration(beat) -> float`
- (Step 14) `self.play_log` (every `play`/`wait`: `PlayRecord(start, end, beat, animations,
  wait, requested)`), `self.beat_busy` (seconds each `narrate` body took), `self.silent_busy`;
  recorded always, written to the activity file (§17) when stills are captured.
- `self.clear_all(run_time=0.6)` — fade out everything.
- `self.narrate_all()` — convenience generator: `for beat, d in self.narrate_all(): ...`.

Theme-aware text: `self.text(s, size="body"|int, color="text"|"#hex", weight=...)` and
`self.markup(...)`; sizes and colors accept theme token names or literal values.

Refinements (Step 2):
- Injection is the constructor: `SceneClass(spec, project=None, theme=None, *, audio=True,
  **manim_scene_kwargs)`. `project`/`theme` default to the runtime context (§6.3); without a
  context the theme is built from `project.config.theme`. Constructing needs Manim's config set
  up (Manim creates its renderer); params validation does not: `SceneClass.validate_params(raw)`
  (raises `pydantic.ValidationError`), `SceneClass.parse_params(raw, scene_id)` (raises
  `VidgenError`), `SceneClass.params_model()`. `Params` must subclass `SceneParams`
  (pydantic, `extra="forbid"`); inherited `Params` count.
- `audio=False` (`--no-audio`) skips `add_sound` but still takes durations from the MP3s, so
  timing is identical.
- `self.beat_log: list[BeatTiming]`, `BeatTiming(beat_id, start, end, text)` (NamedTuple; seconds
  from scene start; `end = start + d`). `self.timings()` returns
  `{"scene": id, "duration": total_seconds, "beats": [{"id", "start", "end", "text"}]}`.
- Waits are frame-exact (`self.wait_seconds(t)` rounds to whole frames), so a beat lasts
  `d + pad` within half a frame. Narrating a beat twice is an error; beats never narrated are
  logged as a warning at the end of the scene.
- Silent scenes are held to `spec.duration` automatically in `tear_down()`; `self.hold(until=None)`
  holds earlier. Subclasses overriding `tear_down` must call `super().tear_down()`.
- Also available: `self.beat(id|index|BeatConfig)`, `self.beat_audio(beat) -> Path | None`,
  `self.pad`. `text()`/`markup()` colors may also be `ManimColor` objects.

### 5.2 How a scene gets rendered

The renderer renders **each scene in its own subprocess** (Manim's global config is not
re-entrant): `python -m vidgen.render.worker <project_dir> <scene_id> --quality final|preview
[--variant NAME] [--no-audio]`. The worker:
1. loads the project + variant, builds the Theme, sets the runtime context (§6.3),
2. imports built-in scenes and project extensions,
3. configures Manim (resolution, fps, background, explicit `media_dir` under `build/`, explicit
   output file name — never guess Manim's folder naming),
4. instantiates the registered class for `scene.type`, injects spec/params/beats/theme/project,
   renders, and writes `build/<quality>[_<variant>]/timings/<scene_id>.json` from `beat_log`.

The parent then pads each scene's audio with silence to the exact video length, concatenates in
config order, and writes the final MP4 and SRT (SRT times = scene offset + beat start/end).

Refinements (Step 2): the worker does steps 1–2 with `vidgen.extensions.activate(project)`
(returns the Theme), then `cls = vidgen.registry.get(spec.type).cls`,
`scene = cls(spec, project, theme, audio=not no_audio)`, `scene.render()`, and writes
`scene.timings()`. Manim caching must be disabled (`disable_caching=True`): on a cache hit Manim
advances its clock by the unquantized duration, which would desynchronise `beat_log` from the
frames.

Refinements (Step 4):
- **Worker** (`vidgen/render/worker.py`, extra flag `--progress` shows Manim's progress bars):
  sets `pixel_width/height`, `frame_rate`, `background_color = theme.background`,
  `disable_caching`, `media_dir = <render_dir>/media`, `video_dir`/`partial_movie_dir` per scene
  id (so parallel workers never share a folder) and `output_file = <scene_id>`; after rendering
  it moves `renderer.file_writer.movie_file_path` (and Manim's `.wav` beside it, if any) to
  `scenes/<id>.mp4|.wav` and writes `timings/<id>.json` = `scene.timings()` (rounded to µs) plus
  `"render": {width, height, fps, audio, vidgen}`. Old files of the scene are deleted first, so
  a failed render leaves none. Manim cannot handle `'`, `{` or `}` in its paths (it formats them
  with `str.format` and writes unescaped concat lists); for such project paths Manim's media
  folder is a temporary directory instead. Exit codes: 0 ok, 1 `VidgenError` (`error: ...` on
  stderr), 2 other exceptions (full traceback). The worker runs with `PYTHONUTF8=1`.
- **Frame size**: Manim does not recompute `frame_width` when pixel sizes are set from code (a
  portrait render would be squashed), so the worker sets it: the **shorter side is 8 units**
  with square pixels (16:9 → 14.22 x 8, Manim's default; 9:16 → 8 x 14.22; 1:1 → 8 x 8). Scenes
  read `config.frame_width/height`, or `NarratedScene.frame_width`, `.frame_height`,
  `.is_portrait` (new read-only properties).
- **Audio/no drift**: concatenating AAC segments drifts (every segment carries ~21 ms of encoder
  priming that the concat demuxer does not remove — measured: +50 ms after two scene
  boundaries). So the parent pads Manim's **PCM WAV** of each scene (silence for silent scenes
  and `--no-audio`) to exactly the video's length (48 kHz stereo; the sample count of scene *i*
  is `round(end_i*48000) - round(start_i*48000)`, so rounding never accumulates), concatenates
  the videos (stream copy) and the WAVs (PCM) with two concat-demuxer lists, and encodes the
  audio once to AAC 192k in the final mux. Measured beat onsets in the output match
  `timings.json` within 1 ms. Scene durations are measured from the rendered videos with PyAV
  (frames / fps). The final MP4 is written to `<name>.partial.mp4` and renamed (Step 7: if
  the target stays locked, the partial file is kept and the error says so).
- **Timings**: `build/<q>[_<variant>]/timings.json` = `{title, variant, preview, format: {width,
  height, fps}, audio, duration, vidgen, scenes: [{id, type, start, duration, beats: [{id,
  start, end, text}]}]}`, all times absolute seconds. SRT cues come from it (`subtitles.py`):
  1-based, `HH:MM:SS,mmm`, UTF-8; beat text wrapped to 42-character lines, at most 2 lines per
  cue, the beat's time (start → narration end, pad excluded) shared in proportion to characters.
- **Scene selection**: no automatic up-to-date detection. Without `--scene` every scene is
  rendered. With `--scene` those are rendered, and others are reused if their render exists and
  was made at the current format (and with audio, unless `--no-audio`); otherwise they are
  rendered too. Reused renders are not checked against config/extension changes.
- **Failures**: without `--keep-going` the first failing scene stops the command (message: scene
  id, exit code, last 60 lines of worker output — the user's traceback for exceptions in scene
  code). With it, the remaining scenes are rendered, failures are printed as they happen, the
  video is **not** joined, and the command fails listing the failed scenes.
- **Parallelism**: `render_project(..., jobs=N)` / `vidgen render --jobs N` runs N workers at
  once (default 1). Live Manim progress is shown only for `jobs == 1` on a terminal; otherwise
  worker output is captured and its `warning:` lines are re-printed. `--jobs auto` is resolved
  to a number by the CLI before the command runs (§70); the Python functions take an int.
- **Audio check**: before rendering, missing/stale narration audio (`tts.audio_status`) is
  logged as a warning recommending `vidgen tts`; ffmpeg missing is a `VidgenError` with install
  hints (`winget install ffmpeg` on Windows).

Refinements (Step 5):
- **Worker caches**: `config.text_dir = media/texts/<scene_id>` and `config.tex_dir =
  media/Tex/<scene_id>`. Manim caches Text/Tex SVGs by content hash in one folder; with
  `--jobs N` two workers writing the same SVG at once made the other parse a half-written file
  (`xml.etree.ElementTree.ParseError`). Per-scene folders cost cache reuse across scenes only.

### 5.3 Scene-building API (Step 5)

Added to `NarratedScene` so built-ins and extensions share it:
- `validate_params(params, theme=None)` / `parse_params(params, scene_id, theme=None)`: the theme
  is passed to validators as `info.context["theme"]`; the constructor passes `self.theme`.
- `ThemeColor` (`Annotated[str, ...]`) and `ThemeSize` (`Annotated[str | float, ...]`) for
  `Params` fields: hex syntax is always checked, token names when a theme is given (validate and
  render). Both carry a `ThemeToken(kind)` marker; `list-scenes` prints them as `color` / `size`.
- classmethod `validate_project(params, project) -> list[str]`: project-aware checks run by
  `vidgen validate` (inside the project session, after params validated); each message is
  reported as `scenes[i].params.<message>` (convention: start with the param name). Default `[]`.
- `outro: float = 0.0` (class attribute) and `finish()` (fade out everything over `outro`).
- `timeline()`: yields `(index, d)` per narrated beat; a silent scene yields one
  `(0, duration - outro)` step and then holds to that time.
- `play_steps(d, steps, fraction=0.7, cap=1.2)`: spreads steps (animation | list | callable
  returning either) over `d` seconds, each run for `min(cap, fraction * slot)`; never longer
  than `d` (if `d` has fewer frames than steps, consecutive steps are merged).
- `reveal(steps, fraction, cap)`: `distribute(len(steps), len(beats))` + `timeline()` +
  `play_steps()` per beat.
- `safe_width` / `safe_height` (frame minus `margin_x = 0.6`, `margin_y = 0.5` units; Step 15:
  derived from `self.safe_area`, §18).

Refinements (Step 6, found while porting kphi3):
- `beat_count: int | tuple[int, int | None] | None = None` (class attribute): how many beats a
  scene type narrates (`None` any, `2` exactly, `(1, None)` at least one, `(2, 4)` a range).
  Types that narrate fixed beat indices set it. `check_beat_count(n) -> str | None` (e.g.
  `"needs exactly 2 beats, got 3"`) and `beat_count_text()` (`"exactly 2 beats"`) are
  classmethods. `vidgen validate` reports `scenes[i].beats: type 'x' needs ...`; the constructor
  raises `VidgenError("scene 'id': needs ...")`; `vidgen list-scenes` prints `beats: ...`.
  Built-ins leave it `None` (they adapt to any number of beats).

`vidgen.layout` (exported by `vidgen.api`): `fit_text`, `measure_text` (Step 27), `shrink_to_fit`, `wrap_lines`,
`normalize_text`, `distribute`, `nice_ticks`, `auto_format`, `format_value`, `check_format`,
`latex_available`, `require_latex` (+ `missing_latex_tools`, not exported). `fit_text` measures
each word once (cached per font/weight) and searches the font size arithmetically, building the
`Paragraph` once; `Paragraph` `line_spacing` defaults to 0.7 (Manim's -1 sets lines nearly
touching). Highlights are applied with `t2c` index ranges (wrapping only turns spaces into line
breaks, so indices into the normalized text stay valid).

## 6. Extension system (the core requirement)

### 6.1 Discovery
For each directory in `extensions` (default `extensions/`, silently skipped if absent):
every `*.py` file (not starting with `_`) and every sub-package is imported, in sorted order,
under a private package name `vidgen_ext_<sanitised project name>` so that extension modules can
import each other with relative imports (`from .common import column`). The project's
directory is **not** put on `sys.path` globally. Import errors are reported with the file name
and the original traceback.

### 6.2 What an extension can register (all via `vidgen.api`)
```python
from vidgen.api import *          # NarratedScene, scene, hook, theme helpers, manim names

@scene("loss_panel")              # name used as `type:` in video.yaml
class LossPanel(NarratedScene):
    class Params(SceneParams):    # optional pydantic model for params validation
        values: dict[str, float]
        best: str | None = None

    def construct(self):
        with self.narrate(0) as d:
            ...

@hook("post_render")              # events: pre_tts, post_tts, pre_render, post_scene, post_render
def add_watermark(ctx): ...       # ctx: HookContext(project, event, data: dict)

register_theme_defaults({"k2": "#F2A541"})   # extra theme tokens; video.yaml values still win
register_theme_preset("acme", base="light_academic", colors={"primary": "#0B5FFF"})   # Step 16
```
- **Scene types**: `@scene(name, *, override=False)`. Name collision with another extension is an
  error. Colliding with a built-in raises unless `override=True`, which replaces it and logs a
  warning (`vidgen list-scenes` marks it as overridden).
- **Helpers**: plain Python functions/modules inside `extensions/`; shared via relative imports.
- **Theme tokens**: `register_theme_defaults()`; `theme.color("k2")`, `theme.size("body")`.
- **Hooks**: `@hook(event)`; called in registration order; exceptions abort the command with the
  hook's name in the message.
- **Hook data** (Step 3, TTS): `pre_tts` — `beats: list[str]` (ids about to be generated, video
  order; a hook may remove ids to skip them or add known ids), `audio_dir: Path`, `force: bool`,
  `dry_run: bool`; dispatched on dry runs too. `post_tts` — `generated: list[str]` (ids written,
  in order), `audio_dir: Path`; not dispatched on dry runs or when the command fails. The API key
  is never part of hook data.
- **Hook data** (Step 10): `post_scene` also gets `frames` (the scene's stills folder, or `None`
  without `--frames`), `post_render` gets `frames_index` (`frames/index.json` or `None`).
- **Hook data** (Step 4, render; hooks run in the parent `vidgen render` process): `pre_render` —
  `scenes: list[str]` (ids about to be rendered, config order; a hook may remove ids to reuse
  their existing render), `preview: bool`, `variant: str | None`, `no_audio: bool`,
  `render_dir: Path`. `post_scene` — once per scene rendered in this run (not for reused ones):
  `scene_id`, `video: Path` (`scenes/<id>.mp4`, before padding), `timings: dict` (the scene's
  timings file content), `preview`, `variant`. `post_render` — after the MP4, SRT and
  `timings.json` are written: `output: Path`, `srt: Path`, `timings: dict` (combined),
  `timings_file: Path`, `preview`, `variant` (later steps add `frames_index`, `chapters` and,
  Step 60, `thumbnail`: the hook runs after the thumbnail is written). Not dispatched when the
  command fails.
- **Promotion**: an extension module copied into `src/vidgen/scenes/` works unchanged, because
  built-ins use exactly the same `@scene` API.

### 6.3 Runtime context
`vidgen.runtime` holds the active Project and Theme. It is set **before** extensions are imported,
so module-level code in an extension may read theme values
(`C_BASE = current_theme().color("primary")`). `api.T(...)` / `api.MT(...)` are function forms of
`self.text`/`self.markup` that use the current theme — this makes porting old scripts easy.

### 6.4 `vidgen.api` exports (stable surface)
`NarratedScene, SceneParams, scene, hook, HookContext, register_theme_defaults, current_theme,
current_project, T, MT`, generic helpers from `helpers.py`, and `from manim import *`.
Step 5 adds `ThemeColor, ThemeSize`, the `vidgen.layout` helpers (§5.3) and pydantic's
`Field, field_validator, model_validator`.
Step 15 adds the layout regions (§18): `Region, frame_region, safe_area, region, grid, place,
orientation, readable_size, readable_text`. Step 16 adds `register_theme_preset` (§19); Step 17
gives it the keyword arguments `scale` and `fonts` (§20). Step 19 adds `icon`, `Icon` and
`IconName` (§22). Step 21 adds `grid_shape` (§24). Step 22 (§25) adds keyword arguments only:
`role=` on `T`, `MT`, `NarratedScene.text`/`markup`, `fit_text` and `readable_text`; `region(name,
area)` also takes a region name as `area`; `SceneParams.also_accepts`. Step 23 (§26) adds
`action`, `Action`, `ActionOptions`, `Target` and, on `NarratedScene`, `target_patterns`,
`target_names()`, `target()`, `targets`, `find_targets()`, `on_screen_parts()`, `is_shown()`,
`entrance()`. Step 24 (§27) adds, compatibly: `NarratedScene` is a `MovingCameraScene`;
`target(..., outline=)`; `Target.outline`, `Target.rest`, `Target.rest_opacity()`; `Action`
class attributes `temporary`, `moves_camera`, `target_options`. Step 27 adds `measure_text`.
Step 28 (§31) adds `layered_layout`, `GraphLayout`, `GraphNode`, `GraphEdge`, `EdgeRoute`,
`NodePlace`.
Step 29 (§32) adds `sparse_pairs` and `group_bounds`, and compatible keyword arguments:
`column(..., horizontal=False, skip=None)`, `edges(..., colors=None, shorten=0.0)`,
`grouped_pairs(n, groups, m=None)`.
Step 30 (§33) adds the chart helpers: `ChartAxis`, `ChartAxes`, `LinearFit`, `CHART_MARKERS`,
`axis_ticks`, `short_number`, `tick_texts`, `value_axis`, `chart_axes`, `chart_label_size`,
`chart_legend`, `auto_legend`, `legend_spot`, `sample_path`, `chart_marker`, `linear_fit`,
`chart_title`, `chart_caption`.
Step 31 (§34) adds `ColorScale`, `color_scale`, `color_bar`, `mix_colors`, `text_color_on`.
Step 34 (§37) adds the callout helpers: `Callout`, `CalloutArea`, `CALLOUT_KINDS`, `callout`,
`callout_area`, `callout_box`, `callout_circle`, `callout_arrow`, `callout_magnifier`,
`callout_spotlight`, `callout_label`, `label_spot`.
Step 35 (§38) adds the video clip helpers: `CLIP_SUFFIXES`, `ClipInfo`, `ClipMobject`,
`ClipTiming`, `clip_audio`, `fit_speed`, `probe_clip`.
Step 36 (§39) adds the map helpers: `MAP_VIEWS`, `Country`, `MapView`, `equal_earth`,
`find_country`, `fit_view`, `view_box`, `world_countries`.
Step 38 (§41) adds `overlay`, `Overlay`, `OverlayOptions`, `OverlayContext`, `with_opacity`, and
`NarratedScene.overlay_layer` (compatible: `NarratedScene.safe_area` shrinks for reserved overlays).
Step 39 (§42) adds `video_chapters`, `Chapter`. Step 40 (§43) adds `WordTime`, `beat_word_times`,
`estimate_word_times`, `speech_bounds`, `spoken_words`, `syllables`, `CaptionCue`,
`caption_cues`, `segment_cues`, `phrase_break_cost`, `plate_contrast`, and compatibly
`Overlay.default_reserve()` / `Overlay.reserves`.
Step 41 (§44) adds, compatibly, the `Action` class attribute `until_next_beat` and the methods
`problems()`, `provides()`, `default_until(later)`.
Step 42 (§45) adds `Pronunciation`, `Spoken`, `map_word_times`, and compatibly the optional last
argument `spoken` of `beat_word_times`.
Step 43 (§46) adds `speaker_label`, `speaker_color`, `speaker_prefix`, and compatibly the keyword
arguments `prefix` / `prefix_width` of `caption_cues` and the field `CaptionCue.prefix`.
Step 44 (§47) adds `SfxEvent`, `SfxParams`, `SoundLibrary`, `sound_library`, `synthesize`; on
`NarratedScene` `sfx()`, `sfx_log`, `sounds`, `auto_sfx()` and the class attribute
`entrance_sfx`; on `Action` (compatibly) the class attributes `scene_targets`, `animates` and
the method `cue(scene, time)`.
Step 46 (§49) adds, compatibly, `NarratedScene.transition_in` / `transition_out` (planned
`TransitionSlot`s or `None`) and `SceneSlot.overlap_in`, `overlap_out`, `cut` (fields with
defaults / a property); `finish()` holds instead of fading when a transition follows.
Step 47 (§50) adds `carry_move`; on `NarratedScene` `carry_in(name)`, `carry_out`, `carry_state`,
`carried_in`, `overlay_head`, and compatibly `clear_all(run_time, keep=())`; `entrance()` moves
a carried copy into its target; `finish()` keeps carried targets on screen.
Step 49 (§52) adds, compatibly, the keyword argument `intro=False` of `video_chapters` and the
field `Chapter.intro` (default `False`).
Step 51 (§54) adds `TranslatableStr`, `TextRef`, `LanguageRules`, `language_rules`; on
`SceneParams` the class attributes `text_shorthand` and `text_defaults`; and compatibly the
keyword argument `language=None` of `caption_cues`, `segment_cues`, `phrase_break_cost`,
`beat_word_times`, `estimate_word_times` and `syllables`.
Step 55 (§58) adds `GenerateImage`, `generated_image`.
Step 67 (§69) adds `Character`, `CharacterPart`, `CharacterState`, `PartPose`, `PART_NAMES`,
`character` and the param type `CharacterName`.
Step 70 (§69.3) adds `PoseChange` (and the `Character` methods `set_pose`, `set_expression`,
`posed_state`, `names`).
Step 71 (§69.4) adds `VISEMES`, `VisemeCue`, `VisemeTrack` (and the `Character` methods
`viseme_shape`, `show_viseme`, `lip_sync`, `stop_lip_sync`; `NarratedScene.beat_visemes`).
Step 73 (§69.6) adds the stage geometry `MARKS`, `StageItem`, `StagePlacement`, `stage_layout`,
`mark_x`, `facing_towards_centre` and the check `pose_name_problem` (the built-in `stage` scene
uses only `vidgen.api`, like every built-in).
Step 74 (§69.7) adds `DEFAULT_FACTORS`, `LAYER_PLACES`, `layer_transform`, `layer_half_extent`
and `view_center_within`; `NarratedScene` gains `camera_bounds`, `camera_place`,
`follow_with_camera`, `camera_following`, `add_camera_listener`; `Action` gains `scene_problems`.
Step 75 (§69.8) adds `Prop`, `draw_prop`, `svg_prop`, `PROP_KINDS`, `PROP_HEIGHTS`, `PROP_LIFTS`,
`SVG_PROP_HEIGHT`; `StageItem` gains `lift=0.0` (compatible).
Step 76 (§69.9) adds `PARTICLE_KINDS`, `MAX_PARTICLES`, `particle_count`, `particle_seeds`,
`particle_states`, `ParticleField`, `ParticleSettings`, `ParticleKindName`, `particle_field`, and
compatibly the attribute `NarratedScene.is_preview`.
Step 77 (§69.10) adds, compatibly, the keyword argument `cartoon=False` of `generated_image`, the
`NarratedScene` class attribute `uses_cartoon_style` (default `False`) and the method
`generated_picture(generate)`.
Step 78 (§69.11) adds `beat_voice`, `speaking_characters`, `say_problem`, `LookPose`,
`look_pose`, `camera_look`; `NarratedScene` gains `current_beat`, `beat_clock`, `speak`,
`beat_action_names`; `Action` gains `character_needs`; `Character.lip_sync` gains the keyword
`clock=None` and `Character` the methods `sync_mouth`, `lip_sync_track` (all compatible).
Step 79 (§69.12) adds `Walk`, `Gesture`, `Jump`, `WALK_SPEED`, `GESTURES`, `GESTURE_SECONDS`,
`JUMP_HEIGHT`, `JUMP_SECONDS`, `walk_seconds`, `enter_path`, `exit_path`, `nearer_side`,
`offstage_x`; `Action` gains `run_time_for` and the class attribute `alters_targets` (default
`True`); `NarratedScene` gains `action_uses`; `Character` gains `character_height` and
`walked_in` (all compatible).
Step 80 (§69.13) adds `MOTION_LEVELS`, `MotionSetting`, `walk_motion_seconds`,
`jump_motion_seconds`; `PoseChange`, `Walk`, `Gesture` and `Jump` gain the keyword `motion=None`;
`Character` gains the constructor keyword `motion="lively"`, the attribute `motion`, the
property `motion_strength` and `set_squash`; `character()` gains `motion=None` (all compatible;
the default `lively` changes how the four animations look, not their end states).
Step 81 (§69.14) adds `KeyedMotion`, `feet_of`, `CHANNELS`, `DEFAULT_EASE`, `EASE_NAMES`,
`EaseName`, `Key`, `KeyFrame`, `MotionPath`, `ease_progress`, `key_seconds`,
`key_time_problems`, `keyed_values`, `path_length`, `part_target_names`, `feet_point` (all
compatible); the `stage` scene type gains the target pattern `<character>.<part>`.
Step 82 (§69.15) adds `Spring` (compatible; follow-through in `Walk` and `Jump` now wobbles).
Step 83 (§69.16) adds the `NarratedScene` class attribute `mid_still_actions` (default empty;
compatible).
Step 84 (§69.17) adds to `Character` the attributes `looked_at` and `passage` and the property
`spoken_viseme` (all compatible).
Step 86 (§69.19) adds `PlayedAction`, `FoleyCue`, `foley_cues`, the `NarratedScene` hook
`action_foley(action, options, animations, start, seconds)` (does nothing by default), `Walk.heights`
and `Walk.phases` / `Jump.phases`, and compatibly the `SfxEvent` field `duck` (default `False`).
The fixes after Step 88 (§69.22) add `ground_top` (compatible).
Step 89 (§69.23) adds `ActionConfig`, `AutoDirect`, `AutoDirectSetting`, `DirectedBeat`, `stage_directions` and
the `NarratedScene` class method `auto_actions(project, spec, params)` (none by default;
compatible); `ActionConfig` gains `automatic(data)`, the property `auto` and `shorthand()`.
Step 90 (§69.24) adds `StageFrame`, `StagePlace` and `stage_frame`; `stage_directions` gains the
optional `stage` argument (compatible).
Step 92 (§69.26) adds no names; `PART_NAMES` gains `leg_left`, `leg_right` and the `_lower`
segments, `CharacterPart` the optional `end`, and `Character` the methods `reach`, `plant`,
`hand_point`, `foot_point`, `sole_height`, `grounded` (compatible; generated characters have
single legs instead of `legs`).
Step 93 (§69.27) adds `ArmMove`, `PropMove`, `Holdings`, `HoldingError`, `HandlingStep`,
`holding_problems`, `hold_point`, `held_height`, `put_down_x`, `throw_seconds`,
`throw_release_share`, `HAND_ORDER`, `HANDLING_ACTIONS` and the timing constants
`PICK_UP_SECONDS`, `PUT_DOWN_SECONDS`, `GIVE_SECONDS`, `HOLD_SECONDS`, `REACH_SHARE`,
`PUT_DOWN_REACH_SHARE`, `PUT_DOWN_LAND_SHARE`, `THROW_WIND_UP`, `THROW_SWING`, `THROW_HEIGHT`,
`THROW_SPIN`; `Character` gains `reached_parts`, `shoulder_point` and the attribute `holding`,
`Prop` the attributes `height_factor`, `held_by` and `hand`, `PlayedAction` the field `lands`, and
`NarratedScene` the class method `action_sequence_problems(spec, params, uses)` (none by
default). All compatible.
Step 94 (§69.28) adds `BodyMove`, `Postures`, `PostureError`, `PROP_SEATS`, `PROP_LEANS`,
`SEAT_BACKS`, `POSTURE_ACTIONS`, `SIT_SECONDS`, `LEAN_SECONDS`, `STAND_UP_SECONDS`, `CROUCH_MIN`,
`crouch_drop`, `crouch_stoop` and `read_svg_seat_and_lean`; `Character` gains `limb_rest`,
`hip_height`, `part_box`, `sole_points`, `planted`, `lowered`, `seated`, `leaning` and the
attributes `sitting_on` / `leaning_on`, `reached_parts` the optional `state`; `Prop` gains `seat`,
`lean`, `seat_point()` and `lean_edges()`; `StageFrame` the field `seat_facings` (default empty).
`holding_problems` also replays sitting and leaning. All compatible.
Step 95 (§69.29) adds `ShotConfig`, `SHOT_NAMES`, `SHOT_KINDS`, `SHOT_MOVE_SECONDS`, `Shot`,
`ShotFigure`, `ShotView`, `frame_shot`, `shot_figures` and `shot_view`; `Character` gains
`standing_height`; `NarratedScene` the attributes `camera_shot` and `shot_home`; `BeatConfig` the
key `shot`. All compatible.
Step 96 (§69.30) adds `ReframeSetting`, `REFRAME_SECONDS`, `REPLY_HOLD_SECONDS`, `CameraMove`,
`ReframeBeat`, `ReframeFigure`, `reframe_needed`, `reframe_path`, `stage_base_width`,
`plan_reframe` and `stage_reframes`; `stage_directions` gains the keyword `reframe` (default
`False`); the `pan` action the option `cut`. Compatible, except that a `stage` whose characters
do not fit in one view now gets automatic pans, and in a frame narrower than 16:9 is laid out as
wide as the 16:9 frame (set `reframe: none` for the old behaviour).
Step 97 (§69.31) adds `LIGHT_PRESETS`, `LIGHT_FADE_SECONDS`, `DEFAULT_STRENGTH`, `STAR_SKY`,
`SHADOW_WIDTH`, `PROP_SHADOW_WIDTH`, `LightGrade`, `LightChange`, `Stars`, `ShadowEllipse`,
`tint_grade`, `light_grade`, `blend_grades`, `grade_rgbas`, `grade_pixels`, `light_at`,
`night_stars`, `shadow_ellipse`, `CustomLight`, `LightSetting`, `resolve_light`, `mark_lit`,
`StageLight`, `StarField`, `ShadowCaster` and `StageShadows`; `vidgen.particle_field`'s
`_unit_shape` becomes `particle_shape`. Compatible, except that every `stage` now draws soft
shadows under what stands on the ground (`shadows: false` for the old picture).
Step 98 (§69.32) adds `SWAYS`, `WIND_FADE_SECONDS`, `WIND_LEVELS`, `Sway`, `Wind`, `WindChange`,
`WindSetting`, `bent_points`, `gust`, `sway_degrees`, `trail_degrees`, `wind_level`, `wind_seed`,
`StageWind`, `SwayingProp` and `ParticleWind`; `Character` gains `set_wind`, `wind`,
`has_trails` (`TRAIL_ATTRIBUTE` in `cartoon/character.py`), `ParticleField` the keyword `wind`,
`particle_states` the keywords `blown` and `wind`, `Spring` the property `memory_seconds`,
`Action` the class attribute `number_target`; `ActionConfig.target` keeps a number as its
text. Compatible: a stage without `wind` (or `wind: 0`) renders the same frames as before.
Step 99 (§69.33) adds no names: `stage_directions` also returns the speakers' faces for voice
sounds (any `auto_direct`), `BeatConfig` gains `voice_sounds`, `Project` the method `spoken`,
`Spoken` the method `inserted`; beats without `[laugh]`-style markers are unchanged.
Step 100 (§69.34) adds `CueStack`, `stack_cues` and `overlapping_beats`; `NarratedScene` gains
`beat_window` and `end_lip_sync`, `VisemeTrack` the method `until`, `BeatConfig` the keys
`overlap` / `interrupt`, `add_narration` the argument `shape`; the `captions` overlay's karaoke
state becomes `(caption, (word, ...))`. Compatible: beats without the keys keep their timings
and audio (pinned in `tests/test_overlap_pinned.py`).
Step 101 (§69.35) adds `numbered_names` and `prop_default_name` (the stage's prop and layer
names, shared with the set merge); `Problem` gains `file`.
Step 102 (§69.36) adds `STAR_HEAD_ROOM`; `PROP_HEIGHTS` changes for `chair`, `box` and `rock`
(lower seats), and `Character.seated` puts the hips, not the body's lowest point, on the seat.
Step 103 (§69.37) adds `PROP_SHAPES`, `PROP_GRIPS`, `PropReshape`, `OVERHEAD_SHAPES`,
`OVERHEAD_FORWARD`, `OVERHEAD_HAND`, `OVERHEAD_HEIGHT`, `RESHAPE_SECONDS`, `RESHAPE_SHARE` and
`overhead_point`; `PROP_KINDS` gains `basket`, `umbrella`, `napkin`; `Prop` gains `shapes`,
`shape`, `show_shape`, `shape_width`, `grips`, `grip`, `grip_point` (and the keywords `shapes`,
`grips`), `draw_prop` the keyword `shape`, `held_height` the keyword `overhead`, `ShadowCaster`
the field `widths`; `PropMove` moves a prop by its grip (its middle unless it has one). New
built-in actions `open` / `close`, stage prop key `open`, layout key `shape`. Compatible: props
without a grip are moved and held by their middle as before.
Step 104 (§69.38) adds `LIGHT_PROPS`, `blow_seconds`, `blown_point`, `felt_force` and
`gusty_progress`; `PropMove` gains the keyword `path`, `Holdings` the method `drop`,
`HANDLING_ACTIONS` the name `blow_away`, `PARTICLE_KINDS` `leaves` and `streaks` (last, so the
other kinds' seeded streams are unchanged), `ParticleKind` the field `wind_shown`. New built-in
action `blow_away`. Changed on purpose: a windy stage sways and trails more (`felt_force`, larger
`SWAYS`, `TRAIL_WEIGHTS` for long hair, bun and hat), so its frames differ from Step 98's; a
calm stage (`wind: 0`) renders the same frames as before.
Step 105 (§69.39) adds `Puddles`, `RainGroundSource`, `RainGround`, `ShelterBox`, `SHELTER_PROPS`,
`SPLASH_SECONDS`, `drop_floors`, `drop_landings`, `landing_lines`, `prop_shelter`,
`puddle_count`, `puddle_growth`, `puddle_spots`, `rain_ground` and `splash_shapes`;
`ParticleSettings` gains `puddles` (default `False`), `ParticleField` the keywords `ground` and
`seed` and the attributes `drops`, `splashes`, `ended`, and `NarratedScene` the hook
`particles_started(field, settings)` (does nothing by default). Changed on purpose: rain on a
`stage` ends on its ground and shelters (other scene types: unchanged), and plays a rain bed with
foley on.
Step 107 (§69.40) adds `EFFECT_KINDS`, `EFFECT_SECONDS`, `EFFECT_STYLES`, `EXPRESSION_EFFECTS`,
`EffectSpot`, `EffectSymbol`, `effect_color`, `effect_spot`, `head_box`, `piece_pose` and
`pop_scale`; `PlayedAction` gains `effect`, `DIRECTING_KINDS` and `AutoDirect` the kind
`effects`. New built-in action `effect`; layout kind `effect` (keys `effect`, `effect_of`).
Changed on purpose: `auto_direct: true` now also adds effect symbols (a stage with
`auto_direct` and a surprised, thinking or angry face renders a symbol it did not before;
`{effects: false}` gives the old actions).
Step 108 (§69.41) adds `MOTION_EFFECT_KINDS`, `FAST_SPEED`, `HARD_LANDING`, `MotionEffectCue`,
`MotionEffect`, `effect_scale`, `motion_effect_cues`, `motion_seed`, `motion_strength`,
`resolve_motion`, `Gait`, `WALKING`, `RUNNING` and `RUN_SPEED`; `Walk(gait=)` with
`Walk.gait` / `Walk.step_length`; `PlayedAction` gains `step_length`, `lift`, `gesture`, `big`,
`flight`; `NarratedScene` the hook `action_motion_effects(action, options, animations, start,
seconds)` (does nothing by default, called right after `action_foley`). New built-in action
`run_to`, `gesture` option `big`, top-level and stage `motion_effects`; layout kind
`motion_effect`. Changed on purpose: with `cartoon_motion` lively or calm, jumps land in dust,
fast walks, throws and blown props get speed lines (a default-speed walk is unchanged);
`motion_effects: false` renders the same frames as before.
Step 109 (§69.42) adds `DEFAULT_FLOOR`, `DEFAULT_WALL`, `DOOR_FADE_SECONDS`, `DOOR_SCALE`,
`FLOORINGS`, `OUTDOOR_PARTICLES`, `WALL_DEPTH`, `WALLPAPERS`, `WINDOW_FRAME`, `WINDOW_HEIGHT`,
`WINDOW_SILL`, `WINDOW_SKIES`, `WINDOW_WIDTH`, `RoomGeometry`, `SkyChange`, `WindowParts`,
`WindowSky`, `floor_lines`, `room_geometry`, `sky_at`, `wall_depth`, `window_parts`,
`window_sky`, `RoomColors`, `RoomDrawing`, `WindowLook`, `WindowViews`, `draw_room`,
`room_colors` and `passage_fade`; `Walk(fade_in=, fade_out=)`; `Character.shown`; the `door`
prop gains the shapes `closed` / `open` (`PROP_SHAPES`). New stage param `room`; `enter` /
`exit` option `door`; `Stage.door(name)`, `Stage.window_views`; stage params' `stage_props()`,
`stage_marks()`, `door_names()`, `wall_depth()`. Compatible: a stage without `room` renders as
before (a `door` prop draws its closed shape as it did).
Step 110 (§69.43) adds `FURNITURE`, `PROP_HANGS`, `FLAT_PROPS` and `SEAT_PLACES`; `PROP_KINDS`
gains twelve furniture props, `PROP_SEATS` / `PROP_LEANS` / `SEAT_BACKS` their seats and lean
edges; `StageItem(hang=0.0)`; `Prop(seat_places=())`, `Prop.seat_places`,
`Prop.seat_point(place=None)`; `Postures.sit(character, prop, places=1, prefer=())` returns the
place taken, `Postures.places`; `StageFrame.seat_places`; `holding_problems(seat_places=None)`.
Stage prop key `against`; stage params' `stage_props()` puts props against the wall at its
depth. Compatible: every default keeps the old behaviour and output (the prop gallery
`props.png` is byte-identical).
Step 111 (§69.44) adds `DEPTH_WALK_HEIGHTS`, `SAME_DEPTH`, `depth_scale`, `depth_slot`,
`depth_walk_distance`, `facing_sign` and `walk_destination`; `Walk(depth=None, feet_y=None,
carried=())`, `Walk.to_depth`; `Character(front=None)`, facing `front`, `has_front_view`,
`side_facing`, `order_changes`, `stage_depth`, `ground_y`; `ShadowCaster(grows=False)` (its
ground from the caster's `ground_y`); `StageFrame.depths`; `holding_problems(depths=None)`;
`walk_to` / `run_to` options `depth` and `to: {mark, depth}`; `turn` `to: front`; stage
character `facing: front`; layout key `depth`. Compatible: a scene without them renders as
before (a generated character also carries its front view's hidden shapes).
Step 112 (§69.45, §69.46) adds `BURST_SPIN`, `CARD_STYLES`, `CardLayout`, `burst_ray_color`,
`burst_rays`, `card_layout`, `card_outline_width`, `card_text_inks`, `StingCue` and
`StingSetting`; `NarratedScene.sting(sting, time)` (public; it was the private `_add_sting`).
New built-in scene type `card`; transition types `iris_out` / `iris_in` with the keys
`character` and `at`. Compatible: renders without them are unchanged, but the fingerprint of a
scene with a transition next to it changes once (the transition's dump gains `character` and
`at`), so those scenes render again once.
Step 118 (§69.52) adds `VEHICLE_KINDS`, `VEHICLES`, `VehicleSpec`, `RIDING_ACTIONS`,
`GET_IN_REACH`, `GET_IN_SECONDS`, `GET_OUT_SECONDS`, `get_in_gap`, `pedal_points`,
`place_order`, `seat_count`, `seat_origin`, `wheel_degrees`, `Ride`, `RiderSeat`, `place_rider`,
`riding_state` and `seat_point`; `PROP_KINDS` gains `bicycle`, `car`, `bus`; `Prop(wheels=(),
crank=None)`, `Prop.is_vehicle`, `.prop_point`, `.unit`, `.standing_height`, `.turn_wheels`,
`.wheels`, `.crank`, `.wheel_angle`, `.crank_angle`, `.ground_y`; `BodyMove(y=None)`;
`Character.riding`; `Postures.ride`, `.get_out`, `.riders`; `PlayedAction.vehicle`;
`StageFrame.vehicles`; `holding_problems(vehicles=None)`; `Stage.ride_in_depth`; actions
`get_in`, `ride_to`, `get_out`; built-in sounds `bell`, `engine`, `brakes`; layout key `riding`.
Compatible: a scene without vehicles renders as before (`props.png` is byte-identical).
Step 119 (§69.53) adds `GROUND_VEHICLES`, `WATER_VEHICLES`, `AIR_VEHICLES`, `medium`,
`character_unit`, `Course`, `balloon_point`, `rocket_point`, `boat_bob`, `wave_offset`,
`smoke_puffs`, `BALLOON_ALTITUDE`, `BALLOON_DRIFT`, `ROCKET_APEX`, `WATER_COLOR` and
`StageWater`; `VehicleSpec.medium` / `.stands`; `PROP_KINDS` gains `boat`, `hot_air_balloon`,
`toy_rocket` (`PROP_SHAPES["toy_rocket"]`: `folded`, `chute`); `Prop.pose_at`, `.tilt`,
`.afloat`, `.flight`; `Ride(rise=0, drift=0, away_y=None, seed=1)` and `Ride.course`;
`StageFrame.water`; `holding_problems(water=None)`; the stage param `water`; the `ride_to`
option `land`; motion effect `smoke`; built-in sounds `burner`, `launch`. Compatible: scenes
without these vehicles or water render as before.
Step 120 (§69.54) adds `DRAWN_CLOCK_SECONDS`, `GLOWS`, `LIVING_KINDS`, `MAX_CLOCK_SPEED`,
`SWITCHED_PROPS`, `LivingProp`, `PropGlow`, `glow_box`, `hand_angles`, `parse_clock_time`,
`redrawn_members` and `tv_picture`; `Prop(anchored=False)`; `draw_prop(living=False)`; the stage
prop keys `on`, `time`, `speed`; `Stage.living`, `Stage.switch_props`; actions `switch_on`,
`switch_off`. Compatible: a scene without a running clock or a tv / lamp that comes on renders as
before, pixel for pixel.
Step 121 (§69.55) adds `FRUIT_INDEX`, `flame_shapes`, `on_spans`, `steam_puffs`, `PropSteam`,
`BIRD_SPAN`, `FLOCK_COUNT`, `FLOCK_HEIGHT`, `FRUIT_SPOTS`, `GROUND_ASIDE`, `GROUND_BOUNCE`,
`HEAD_ASIDE`, `HEAD_BOUNCE`, `MAX_BIRDS`, `bird_place`, `drop_point`, `drop_timing`,
`flock_plan`, `fruit_to_drop`, `FallenFruit`, `Flock`, `FruitDrop`, `fruit_skin` and
`hit_stars`; `PROP_KINDS` gains `kettle` and `fireplace` (furniture); `SWITCHED_PROPS` /
`LIVING_KINDS` gain both; `draw_prop(fruit=False)`; `Prop.prop_points`; `LivingProp(wind=None)`,
`LivingProp.steam`, `.flames`, `.region(start, end)`; the stage prop key `fruit`, the stage param
`birds`; `Stage.flocks`, `.add_flock`, `.drop_fruit`, `.fruit_drop_seconds`; actions `drop_fruit`,
`birds`; the ambience bed `fire`. Compatible: a scene without these renders as before, pixel for
pixel.
Step 122 (§69.56) adds `SMALL_PROPS`, `WATERING_SPOUT`, `OVERHEAD_PROPS`, `FULL_SIZE_HELD`,
`FLOATING_PROPS`, `POURING_PROPS`, `POUR_SECONDS`, `Drop`, `float_end`, `float_point`,
`float_seconds`, `pour_drops`, `pour_flow`, `pour_tilt`, `Pouring`, `WaterDrops`, `WaterFlow`,
`RING_BURST`, `RING_PERIOD`, `RING_TILT`, `on_since`, `ring_burst`, `ring_bursts` and
`ring_shake`; `PROP_KINDS` gains nine small props; `PROP_SHAPES` gains `book`, `letter`, `gift`;
`SWITCHED_PROPS` / `LIVING_KINDS` gain `phone`; `LIGHT_PROPS` gains `letter`, `balloons`;
`Prop.drawn_points`, `Prop.anchor`; `held_height(full_size=False)`; `holding_problems(kinds=None)`;
`HANDLING_ACTIONS` gains `let_go`, `pour`; actions `let_go`, `pour`; built-in sound `phone`.
Compatible: a scene without them renders as before (`props.png` is byte-identical).
Step 124 (§69.58) adds no names; `PART_NAMES` gains `antenna` and `cape` at its end (draw-order
ties and pose-change order of the other parts unchanged; compatible).
Step 126 (§69.60) adds `settle_problem`, `CAP_THICKNESS`, `SETTLE_SECONDS`, `SETTLE_STEP`,
`SNOW_COLOR`, `TopLine`, `bare_patches`, `blanket_cover`, `cap_full_thickness`, `flake_floors`,
`settle_amount`, `settled_seconds`, `FOG_COLOR`, `FOG_DENSITY`, `FOG_DEPTHS`, `band_opacities`,
`fog_cover`, `FogBand`, `SettledSnow`, `SnowBlanket`, `SnowCap`, `StageFog` and `prop_top_line`;
`ParticleSettings.settle` / `.settled`; the stage param `fog`; `Stage.snow_ground`,
`Stage.snow_layers`, `Stage.fog`. Compatible: a scene without settling snow or fog renders as
before, pixel for pixel.
Step 127 (§69.61) adds `LightningBolt`, `Rainbow`, `SkyBody`, `StageRainbow`, `FLASH_SECONDS`,
`MAX_DISTANCE`, `RAINBOW_FADE_SECONDS`, `RAINBOW_OPACITY`, `RAINBOW_WIDTH`, `ROOM_FLASH`,
`STORM_EVERY`, `THUNDER_DISTANCE`, `RainStorm`, `Strike`, `bolt_paths`, `flash_grade`,
`flash_level`, `flash_strength`, `rainbow_level`, `storm_strikes`, `thunder_cue`, `thunder_delay`,
`thunder_pan`, `SKY_BODIES`, `PathMove`, `path_point`, `place_for`, `shadow_cast`, `flash_sky`,
`storm_every` and `storm_problem`; `ParticleSettings.lightning`; `StageLight.strikes`, `.storms`,
`.flash_share`, `.flash`, `.strikes_until`; `StageShadows.cast`, `.set_cast`; the `light`
action's `move_sun` and `Stage.change_light(..., move_sun=False)`; actions `lightning`,
`rainbow`; built-in sound `thunder`; `Stage.strike_lightning`, `.show_rainbow`,
`.hide_rainbows`, `.bolt`, `.rainbows`, `.sky_bodies`. Compatible: a scene without them renders
as before, pixel for pixel, but for its outro (below: a stage now fades out as one picture).
Step 128 (§69.62) adds `SET_BEDS`, `set_ambience` and `wet_steps`; `PlayedAction.prop`,
`.through_door`, `.opens_door`, `.pours`; `Walk(opens_door=False)`; the top-level key `ambience`
and the stage param `ambience`; `Stage.knock_on`, `.set_beds`, `.light_marks`; action `knock`;
built-in sounds `creak`, `knock`, `splash`; the ambience beds `birdsong`, `city`, `room_tone`.
Pixels unchanged; the sound of a stage changes on purpose (§69.62: set beds, door creaks, water).
Step 134 (§71.1, §71.2) adds `HAND_REACH_OUT`, `HostMove`, `facing_for`, `hand_goal`,
`host_move_plan`, `pointed_spot`, `RevealStep`, `has_error_text` and `value_trend`;
`Action.alters(scene)`; `NarratedScene.reveal_steps(params)` (class method, default none) and a
default `NarratedScene.auto_actions` (the host's directing; `stage` overrides it as before);
actions `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`, `host_exit`; host key
`auto_direct`; layout kind `pointer`. Compatible: a video without a host renders as before.
Step 142 (§79) adds `DrawingConfig`, `DrawingStyle` and `mark_shaded`; the top-level key and the
stage param `drawing`; `NarratedScene.uses_drawing_style` (class attribute, `False`; `stage`
sets it), `NarratedScene.drawing_settings()` and the attribute `drawing`. Compatible: a video
without `drawing` renders the same frames as before.
Step 153 (§86.9) adds the `PlayedAction` fields `pickups` and `unlocks` (`lands` also marks a
level jump's touch-down) and the built-in sounds `unlock`, `coin`, `twinkle`. Compatible: a
`PlayedAction` without them gives the same cues; a stage without a level sounds as before.
Anything not exported from `vidgen.api` is internal and may change.

### 6.5 Refinements (Step 2)
- **Built-in vs extension** is decided by the module that defines the class/function: modules
  inside the `vidgen` package are built-in, anything else is an extension. The origin shown in
  messages and `list-scenes` is `builtin` or the defining file relative to the project root.
- **Discovery**: names starting with `_` or `.` are skipped; folders without `__init__.py` are
  skipped. Several `extensions` directories share the one synthetic package (its `__path__`
  lists them all), so relative imports work across them; the same module name in two
  directories is an error. The default `extensions/` may be absent; a directory written
  explicitly in `extensions:` must exist. The package name is `vidgen_ext_<folder name,
  lower-cased, non-word characters replaced by _>`; it is removed from `sys.modules` before each
  load. An exception raised while importing becomes a `VidgenError` with the file (relative to
  the project) and the traceback (importlib frames removed); a `VidgenError` raised during
  import (e.g. a name collision) propagates unchanged.
- **Override**: `override=True` replacing a built-in logs a warning on logger `vidgen.registry`;
  `override=True` without a built-in of that name also logs a warning. The CLI prints vidgen log
  warnings as `warning: <message>` on stderr.
- **Isolation** (several projects/variants in one process): built-in registrations are
  permanent (their modules stay imported); extension scene types and hooks form a per-project
  layer. `registry.reset()/snapshot()/restore()/isolated()` and the same four in `hooks`;
  `runtime.set_context()/clear_context()/use_context()`;
  `extensions.activate(project)` (process-wide: context + reset + load) and
  `extensions.project_session(project)` (context manager: everything restored on exit, the
  synthetic package unloaded). Every `activate` builds a fresh Theme, so theme defaults
  registered by one project never leak into another.
- **Hooks**: built-in hooks run before extension hooks, each group in registration order.
  `dispatch(event, project, **data)` returns the `HookContext` (hooks may modify `ctx.data`).
  Errors are wrapped as `hook <module.qualname> (<origin>) failed during <event>: ...` with the
  traceback appended (a `VidgenError` from a hook keeps just its message).
- **`vidgen.api`** additionally exports `VidgenError` (for extensions to raise clear errors) and
  `resolve_color(color, theme=None)`. The only name shared with `from manim import *` is
  `scene` (manim's `manim.scene` subpackage); `vidgen.api.scene` is the decorator.
  `vidgen.api.SHADOWED_MANIM_NAMES` records this and a test pins it.
- **Validation** (`vidgen validate`): unknown types are reported as
  `scenes[i].type: unknown scene type 'x'; did you mean 'y'? (known types: ...)`; params errors as
  `scenes[i].params.<field>: <message>`. Variant problems are prefixed `[variant NAME]`; problems
  identical to the base config's are not repeated.
- **`vidgen list-scenes [PROJECT]`** prints `name  origin  [(overrides builtin)]` and one indented
  line per `Params` field (`name: type [= default]`), or `params: free-form`. Without a PROJECT
  argument and no config file in the current directory it lists the built-ins only.
- **Built-in library**: `vidgen/scenes/__init__.py` imports each scene module explicitly
  (Step 2 ships `text_card`: params `text`, `size="title"`, `color="text"`). Step 5 adds
  `title, bullets, bar_chart, line_chart, image, quote, equation, code, end_card` (reference:
  docs/CONFIG.md "Built-in scenes"). Their only vidgen import is `from vidgen.api import *`
  (a test pins this); shared code between built-ins uses relative imports (`end_card` imports
  `check_image`/`load_image` from `.image`), exactly like extension modules.

## 7. TTS (ElevenLabs)

- Endpoint `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=...`.
  Standard library only (urllib).
- **API key location**: read only from the environment variable `ELEVENLABS_API_KEY`
  (Windows: `setx ELEVENLABS_API_KEY your_key` once, then open a new terminal; Linux/macOS:
  `export ELEVENLABS_API_KEY=...`). vidgen never stores the key: it is not a config field, and it
  is never written to video.yaml, audio/, build/, logs, error messages, hook contexts or git.
  It is sent only as the `xi-api-key` header to api.elevenlabs.io. Only `vidgen tts` (without
  `--dry-run`) needs it; validate/render/dry-run work without it.
- Cache key: sha1 of `voice_id | model_id | output_format | json(settings, sorted keys) | text`,
  stored as `audio/<beat_id>.hash`. Neighbouring beats' text is sent as `previous_text` /
  `next_text` for intonation but is **not** hashed, so editing one beat regenerates only that beat.
- Backward compatibility: the kphi3 hash format (`sha1(voice_id + model_id + text)`) is also
  accepted as "up to date" when settings/output_format equal the old defaults, so existing audio
  is reused without paying for regeneration.
- `vidgen tts [--force] [--dry-run] [--beat ID ...]`; dry run lists what would be generated and the
  character count. Missing API key → clear error, no traceback. HTTP errors show status + body.
- Orphaned mp3s (beat ids no longer in config) are reported, not deleted.
- Tests mock `urllib.request.urlopen`; no network.

Refinements (Step 3):
- **Provider seam** (`vidgen.tts`): `get_provider(voice) -> TTSProvider` (ElevenLabs only; other
  providers raise `VidgenError`). `TTSProvider`: `name`, `cache_key(text)`, `matches(text,
  stored_hash)`, `check_credentials()`, `synthesize(text, previous_text=None, next_text=None) ->
  bytes`. Constructing a provider never needs the key; it is read from the environment on every
  request (stripped) and never kept on the object.
- **Exact cache key**: `sha1("|".join([voice_id, model_id, output_format,
  json.dumps(settings, sort_keys=True), text]).encode("utf-8"))` where `settings` is
  `voice.settings.model_dump()` (default `json.dumps` separators). `voice.context` is not hashed.
- **kphi3 hashes**: accepted when `output_format == mp3_44100_128` and settings equal
  `{stability 0.55, similarity_boost 0.75, style 0.0, use_speaker_boost true}` (the defaults).
  They are **not rewritten** to the new format: the files stay untouched (no git noise for the
  committed kphi3 example audio); any regeneration writes a new-format hash.
- **Requests**: JSON body `{text, model_id, voice_settings}` plus `previous_text`/`next_text` (the
  neighbouring beats in video order, across scene boundaries, omitted at the ends) only when
  `voice.context` is true. Timeout 120 s. Transient failures (HTTP 429/500/502/503/504, timeouts,
  dropped connections) are retried 3 times with backoff 2, 4, 8 s (or `Retry-After`, capped at
  30 s). Errors become `VidgenError`: `ElevenLabs returned HTTP <code>: <body, max 500 chars>` or
  `cannot reach ElevenLabs: ...`; any occurrence of the key is replaced by `***`. The CLI prefixes
  `beat '<id>': ` and says how many beats were done before the error.
- **Writes**: MP3 via temp file + `os.replace` in the same folder, then the hash the same way, so a
  hash never vouches for a partially written MP3. Already generated beats are kept on failure.
- **Command details**: `--variant NAME` added. `--beat` restricts the selection (unknown id →
  error) but up-to-date beats are still skipped unless `--force`. The key is required only when
  at least one beat must be synthesised (an up-to-date project needs no key). Output: one
  `[n/N] generated <id>.mp3 (<chars> chars)` line per beat and a summary; dry run prints
  `would generate ...` lines and `dry run: N beat(s) to generate, C characters; U up to date`.
  The character count is what is billed (beat text only, not context).
- **Variant audio**: a variant uses `audio/<variant>/` when its effective `voice` (after merging)
  differs from the base config's, or a beat id present in both configs has a different text;
  otherwise it shares `audio/`. `Project.audio_dir` implements this (`Project.has_own_audio`,
  `Project.base_config`), so `NarratedScene.beat_audio` picks the right files. When generating
  into a variant folder, beats whose audio in `audio/` is up to date for the variant's voice
  and text are copied instead of synthesised.
- **Orphans**: MP3s in the audio folder whose id is used by no config sharing that folder (base +
  variants) are listed, never deleted; subfolders are ignored.
- **Audio status** (no key): `vidgen.tts.audio_status(project) -> list[BeatAudioStatus]`
  (`scene_id, beat_id, text, state, mp3, hash_file`; state `ok` | `stale` | `missing`; stale =
  MP3 exists but its hash is missing or does not match). `format_audio_summary(statuses)` →
  `"18 ok, 2 stale, 1 missing"`; `orphaned_audio(project) -> list[Path]`. `vidgen validate`
  prints `audio:     <summary>` (plus `(N orphaned mp3)`) and one `audio [<variant>]: ...` line
  per variant with its own audio folder. `render` (Step 4) should warn, not fail, on stale/missing.

## 8. CLI

```
vidgen init <dir> [--example minimal] [--json]   # scaffold a project
vidgen mcp [--root DIR]                 # MCP server (stdio) with the commands as tools, inside DIR (§62)
vidgen plan INPUT [--output DIR|FILE] [--title TEXT] [--format 16:9|9:16] [--preset NAME] [--language TAG]
              [--force] [--json]                  # a draft project from an outline / script (§61)
vidgen guide [TOPIC] [--list] [--json]  # the author guide for AI agents (AGENTS.md, §59)
vidgen validate [PROJECT] [--json]      # load config + extensions, report all errors
vidgen list-scenes [PROJECT] [--json]   # built-ins + extensions (+ which overrides)
vidgen list-themes [PROJECT] [--swatches PNG] [--json]   # theme presets + type scales (§20)
vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]   # icons (§22)
vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]   # sound effects with descriptions (§47)
vidgen list-music [PROJECT] [--render-dir DIR] [--json]   # music beds with descriptions (§48), moods and instruments (§83)
vidgen music preview [PROJECT] [--mood M] [--seed S] [--bars N] [--key K] [--tempo T] [--out DIR]   # composed music as WAV + .mid (§83)
vidgen schema [PROJECT] [--scene TYPE | --all] [--json]   # JSON Schema of video.yaml (§12)
vidgen tts [PROJECT] [--force] [--dry-run] [--beat ID ...] [--voice NAME ...] [--variant NAME] [--json]
vidgen render [PROJECT] [--preview | --draft] [--scene ID ...] [--variant NAME] [--no-audio] [--keep-going]
              [--jobs N|auto] [--frames] [--frames-per-beat N] [--force] [--output-dir DIR] [--json]   # changed scenes only (§63)
vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview | --final]
              [--width PX] [--jobs N|auto] [--force] [--json]      # contact sheets (§14)
vidgen animatic [PROJECT] [--variant NAME] [--no-audio] [--captions | --no-captions] [--jobs N|auto]
              [--output-dir DIR] [--json]   # the storyboard's stills timed to the narration (§75)
vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME] [--preview | --final]
              [--fail-on SEVERITY] [--jobs N|auto] [--force] [--json]   # layout checks (§16)
vidgen thumbnail [PROJECT] [--variant NAME] [--preview] [--scene ID [--beat ID|N] [--at S] [--no-overlays]]
              [--jpeg] [--jobs N|auto] [--output-dir DIR] [--json]   # output/<output>_thumbnail.png (§53)
vidgen export gif|clip [PROJECT] [--scene ID] [--from S] [--to S] [--variant NAME] [--preview] [--width PX]
              [--fps F] [--max-mb MB] [--with-audio] [--output FILE] [--output-dir DIR] [--json]   # exports/ (§53)
vidgen slides [PROJECT] [--format html|pdf] [--variant NAME] [--preview | --final] [--mode beat|scene] [--per-beat N]
              [--overlays | --no-overlays] [--no-dedupe] [--image-format F] [--quality Q] [--max-width PX]
              [--audio] [--separate] [--notes] [--title-page] [--paper a4|letter]
              [--output FILE] [--jobs N|auto] [--force] [--output-dir DIR] [--json]   # HTML deck (§55), PDF deck (§56)
vidgen translate-template [PROJECT] [--variant NAME] [--language TAG] [--output FILE] [--json]   # translation file (§54)
vidgen readback [PROJECT] [--variant NAME] [--beat ID ...] [--max-wer RATE] [--force] [--json]   # STT check of the audio (§57)
vidgen imagegen [PROJECT] [--dry-run] [--force] [--scene ID ...] [--variant NAME] [--json]   # generated pictures (§58)
vidgen gallery [PROJECT] [--output DIR] [--types T,T] [--formats 16:9,9:16] [--theme PRESET]
              [--clips | --no-clips] [--jobs N|auto] [--force] [--json]   # every scene type rendered (§60)
vidgen character NAME [PROJECT] [--variant NAME] [--png [FILE]] [--facing right|left]   # a character's look, poses; one still (§69.1)
vidgen character-sheet [NAME] [PROJECT] [--all] [--variant NAME] [--output FILE] [--json]   # every pose, expression, mouth shape on one PNG (§69.16)
vidgen cast --random N [--seed S] [--species NAME ...] [--out FILE] [--provider P] [--narrator VOICE] [--model NAME]
              [--language TAG] [--force] [--json]   # a well-contrasted cast as an include file (§69.49)
```
PROJECT defaults to the current directory. `render` renders the scenes whose render is missing
or stale by its fingerprint (§14, §63; `--force`: all); `--scene` re-renders only those scenes
and re-joins using the existing renders of the others (missing ones are rendered). Exit code
non-zero on error.
`render` prints one line per scene, then the output paths and the total duration (Step 45: and
the measured loudness, §48). `--jobs auto` (every command with `--jobs`) first prints `jobs: N
(auto: <reason>)` (§70).

## 9. Testing

- `pytest -q` must pass at every step. No network, no API keys.
- Tests that invoke Manim rendering are marked `@pytest.mark.render` and use tiny resolutions
  (e.g. 160x90 @ 5 fps); they run by default but can be skipped with `-m "not render"`. The
  slowest of them are also marked `slow` (Step 22): `-m "not slow"` is a quick full-coverage-ish run.
- ffmpeg is required on PATH for render tests; skip with a clear reason if missing.

## 10. Refinements (Step 7, independent review)

- **Audio length** (`scene.audio_duration`) = decoded samples / sample rate. The container
  duration depends on the PyAV/FFmpeg version: PyAV 13 (what Manim 0.19 pins, i.e. every
  Python 3.10 install) includes MP3 encoder padding, ~25–50 ms more per beat than PyAV 14+.
  Decoding gives identical timings everywhere (kphi3: unchanged with PyAV 19).
- **Dependencies**: `manim>=0.19` (the `code` scene uses the 0.19 `Code` API). Tested with
  Manim 0.19.1 / PyAV 13 on Python 3.10 and Manim 0.21 / PyAV 19 on Python 3.13; Manim 0.22
  (Step 64) also passes (its `SceneFileWriter.write_frame` takes the count as keyword-only
  `repeat` instead of `num_frames`; `renderer.add_frame(frame, num_frames)`, which vidgen
  wraps, is unchanged).
- **Config**: `format`/`preview` `width` and `height` must be even (Manim's H.264 writer
  crashed with a segfault on odd sizes). Config files may start with a UTF-8 BOM (Windows
  Notepad) and use CRLF line endings.
- **Files on Windows** (`vidgen.fileio`): every output that may be open in another program is
  written to a temporary file and moved with `replace_file`, which retries for ~1.5 s
  (virus scanners) and then raises `VidgenError("cannot write X (...); is it open in another
  program...")`. Used for the final MP4 (the joined video is kept as `<name>.partial.mp4`),
  SRT, timings JSON, TTS MP3/hash files; the worker deletes a scene's old render with
  `remove_file` (same error). The CLI reconfigures stdout/stderr with
  `errors="backslashreplace"`, so a console with a legacy code page never crashes on a title
  or path; a closed pipe (`vidgen list-scenes | more`) ends quietly.
- **API key**: render worker processes get the environment without `ELEVENLABS_API_KEY` (scene
  code never needs it).
- **Extensions**: `beat_count` is validated when the class is registered (`VidgenError` naming
  the type); `SystemExit` raised while importing an extension is reported like any import error;
  an exception in (or a non-list returned by) `validate_project` is reported by `vidgen
  validate` as `scenes[i]: validate_project of scene type 'x' (<file>) failed: ...` and the
  other scenes are still checked; `register_theme_defaults(sizes=...)` requires positive
  numbers; bare `@scene` / `@hook` (no parentheses) raise a message showing the right form;
  hook tracebacks start at the hook. `render` also checks beat counts before starting workers.
- **CLI**: `vidgen list-scenes` prints the fields of nested `SceneParams` models indented
  under their field. `vidgen init` creates `assets/`, `extensions/` and a `.gitignore`
  (template files cannot start with a dot, because setuptools does not package dot files: the
  template stores `gitignore` and `init` renames it).

## 11. Refinements (Step 8, JSON output)

- **`--json`** on `validate`, `list-scenes` and `render` (`vidgen.cli.JSON_COMMANDS`): stdout
  holds exactly one JSON document (`vidgen.jsonout.dumps`: indented, `ensure_ascii=True`, so a
  legacy console code page cannot corrupt it); everything the command prints meanwhile is
  redirected to stderr (`contextlib.redirect_stdout`), and vidgen log warnings are both printed
  on stderr and collected into the document. Exit code 0 iff `ok`; 1 for errors; 2 for usage
  errors. Without `--json` the human output is unchanged.
- **Shapes** (`vidgen/jsonout.py`, reference: docs/CONFIG.md "JSON output"): envelope `{version,
  vidgen, command, ok, warnings: [{scene, message}], ..., error?: {kind, message, problems,
  details}}`. `version` is `jsonout.SCHEMA_VERSION` (1): keys may be added within a version;
  removing/renaming a key or changing a value's type bumps it. `error.kind`: `usage` (argparse
  error, `command` may be `null`), `error` (`VidgenError`), `internal` (any other exception;
  `details.traceback`). Paths are absolute, times are seconds.
- **Structured problems**: `vidgen.errors.Problem(location, message, variant=None, file=None)` (`file`: Step 101, §69.35)
  (`str()` = the human line, `to_json()`), and `VidgenError(message, *, problems=(),
  details=None)` (both optional; existing calls unchanged). `config.validation_problems(err,
  prefix)` (`validation_error_lines` now derives from it); `parse_config` and
  `Project.load` (variant problems carry the variant) attach problems to their error.
  `cli.project_problems(project) -> list[Problem]`; `cli.check_project` keeps returning the
  same strings. A `validate_project` message `"<param>: <text>"` gets location
  `scenes[i].params.<param>`; other messages get `scenes[i].params`, and their human line is now
  `scenes[i].params: <message>` (was `scenes[i].params.<message>`, which read like a param
  name). `cli.validate_all(project, keep_going=False)`; with `--json`, a variant whose config
  does not load is reported as problems and the other variants are still checked (the human
  command still stops at it).
- **Render**: `RenderResult` gained `timings` (the combined timings), `render_seconds`
  (`{scene_id: wall seconds}` for scenes rendered in this run) and `warnings`
  (`[(scene_id, message)]` printed by workers, also collected when progress is shown live).
  Render failures raise `VidgenError(..., details={"failed": [{scene, exit_code,
  output_tail}], "rendered": [ids]})`.
- **Param docs**: `SceneParams` sets pydantic's `use_attribute_docstrings=True` (requires
  `pydantic>=2.7`), so a docstring under a field becomes its `description`, shown as `doc` by
  `list-scenes --json`; every built-in param has one. The scene type's `doc` is its class
  docstring, else its module's. The listing helpers moved from `cli.py` to
  `vidgen/describe.py` (`type_name`, `nested_models`, `describe_params`, `params_json`,
  `scene_type_json`).
- **Usage errors**: the CLI parser raises `cli.UsageError` instead of exiting; `main` prints
  argparse's usual `usage:` + `prog: error:` lines and returns 2 (so `main()` returns 2 rather
  than raising `SystemExit(2)`); `--help`/`--version` still exit through argparse.

## 12. Refinements (Step 9, JSON Schema export)

- **`vidgen schema [PROJECT] [--scene TYPE | --all] [--json]`** (`vidgen/schema.py`; reference:
  docs/CONFIG.md "JSON Schema"). Default: the schema of the whole `video.yaml`
  (`schema.config_schema(entries, themes)`); `--scene TYPE`: one type's params
  (`params_schema`, unknown type → `VidgenError` with the did-you-mean message); `--all`: one
  `scenes[]` item with every type's params (`scene_schema`). Draft 2020-12, generated from the
  pydantic models (`model_json_schema`, validation mode) and post-processed. Output is
  `jsonout.dumps` (indented, ASCII) on stdout; extension output during loading goes to stderr.
  With `--json` (now in `cli.JSON_COMMANDS`) the envelope holds `project` and `schema`.
- **Scene types** come from `cli.scene_types_session(path, lenient)` (also used by
  `list-scenes`): without a PROJECT and no config file in the current directory, built-ins
  only. `lenient=True` (schema): if the config does not load, `schema.lenient_project` loads
  the project from a placeholder config keeping the file's `extensions` and `theme` (each only
  if valid) and logs a warning; a missing project is still an error.
- **Per-type params**: `$defs/SceneConfig` gets `type: {enum: [registered names]}` and an
  `allOf` of `if {type: const NAME} then {params: $ref #/$defs/scene.NAME}` (plus `required:
  [params]` when the model has required fields, and `beats` `minItems`/`maxItems`/required from
  `beat_count`); a type without `Params` gets `{type: object}`. Nested models of a type are
  `$defs/scene.NAME.Model` (no collisions between types). Also encoded: the silent-scene rule
  (`if beats non-empty then duration null else duration required`), beat `id` optional/null,
  `variants` bodies (the top-level properties without `variants`, none required,
  `additionalProperties: false`), and `dict[Identifier, X]` as `propertyNames` +
  `additionalProperties` (pydantic's `patternProperties` alone let other keys through);
  `minLength`/`maxLength` pydantic puts on an `anyOf` (a union field's `min_length`) move to
  each branch as `minItems`/`minProperties`/`minLength` by the branch's type.
- **Theme tokens**: `ThemeToken` adds `"x-vidgen-theme": "color"|"size"` to the field's JSON
  Schema (`__get_pydantic_json_schema__`); the export replaces such a node's type by `anyOf`
  [hex pattern | positive number, `enum` of token names]. Token names are the union of the
  active theme (defaults + `register_theme_defaults` + `theme.*`) and every loadable variant's
  theme (`schema.project_themes`).
- **Config models**: `_Strict` uses `use_attribute_docstrings=True` and every config field has a
  one-line docstring (the schema's `description`); `FormatConfig.width/height` carry
  `multipleOf: 2` (`json_schema_extra`; the check stays the `_even` validator, same message);
  `config.Size` has an explicit `WithJsonSchema` (pydantic emitted a non-standard `gt` for the
  `int | float` union). Validation behaviour and messages are unchanged.
- **Not in the schema** (only `vidgen validate`): unique ids, referenced files,
  `validate_project`, Python validators. Values pydantic coerces (`"30"` for an int) pass
  `vidgen validate` but not the schema.
- `describe._doc` is now public as `describe.scene_doc(entry)`. `jsonschema` is a dev
  dependency (tests only).

## 13. Refinements (Step 10, frame capture)

- **Option**: `vidgen render --frames` (one still per beat, its last frame) or
  `--frames-per-beat N` (N evenly spaced stills per beat; implies `--frames`; N >= 1);
  `render_project(..., frames=N)` (0 = off, the default); worker flag `--frames N`. Off by
  default. Reference: docs/CONFIG.md "Frame stills".
- **Where stills are taken** (`vidgen.capture`): a `FrameCapture(per_beat, listeners)` is
  passed to the scene (`NarratedScene(..., capture=None)`, keyword-only, available as
  `self.capture`) and wraps `scene.renderer.add_frame`, the single point where Manim's Cairo
  renderer hands every frame (`num_frames` copies for a frozen wait) to the file writer. It
  counts frames written (skipped animations are not written and not counted), so a still's
  `frame` is its 0-based index in the scene's video and `time = frame / fps`. The wrapper calls
  the original unchanged and only reads the array (Manim passes a fresh copy), so frames,
  `renderer.time` and the beat log are identical to a render without capture (tested:
  identical per-scene timings and frame counts). `narrate()` calls `begin_segment(beat_id,
  round((d + pad) * fps), include_end=False)` on entry and `end_segment(beat_id)` after its
  wait: still `k < N` is planned on entry on the last frame before `k/N` of the beat
  (`capture.plan_targets`) and taken when that frame is written; still `N` is the last frame
  written when the beat ends (exact even if the beat's animations overran `d + pad`). A
  silent scene is one segment (`beat_id = None`) of `duration - outro` (at least one frame),
  planned with its end at construction; `tear_down` calls `finish()`, which takes planned
  stills never reached from the last frame. Stills of a short beat that fall on the same frame
  are merged (highest `k` kept).
- **Listeners** (the seam for Step 12 layout introspection): `capture.listeners` is a list of
  `CaptureListener = Callable[[NarratedScene, CapturedFrame], None]`, called at the moment the
  captured frame is written (mid-beat: inside `add_frame`, after Manim updated the mobjects to
  that frame; end of beat: right after the beat's wait), so `scene.mobjects`, the camera and
  `renderer` are in the state of that frame. `CapturedFrame(scene_id, beat_id, k, n, frame,
  time, pixels)` (`pixels`: H x W x 4 RGBA uint8). `StillWriter(folder)` is the listener that
  writes `<beat>-<k>.png` (`<scene>-<k>.png` for silent scenes; RGB PNG via Pillow, atomic)
  and builds the scene index.
- **Why from the renderer, not by decoding the MP4**: exact pixels and exact frame index (no
  H.264 loss, no seeking/rounding of times), no second pass over the video, works the same for
  every Manim/PyAV version, and it gives listeners the live scene state at the same moment
  (decoding the video afterwards could not). Cost: PNG encoding during the render (~ms per
  still at preview size).
- **Files** (`worker.scene_frames_dir`): `<render_dir>/frames/<scene>/` with the PNGs and
  `index.json` = `{scene, per_beat, width, height, fps, frames: [{beat, k, n, frame, time,
  path}]}` (time from scene start, path relative to the folder); the parent writes
  `frames/index.json` after joining (`pipeline.write_frames_index`) = `{title, variant,
  preview, format, per_beat, vidgen, scenes: [{id, start, duration, frames}]}` with `time` in
  the video, `scene_time` and `path` relative to `frames/`. The per-scene timings' `render`
  block records `frames` (stills per beat, 0 = none).
- **Staleness**: the worker deletes the scene's stills folder before every render (so stills
  always match the scene's current render; `worker.remove_tree`, a locked file is a
  `VidgenError`), and `render_project` deletes `frames/index.json` before rendering. With
  frames requested, `_usable_render` also requires the render's `frames` to equal the count
  and its index to exist, so `--scene ID --frames` renders other scenes again when they have no
  such stills. A scene a `pre_render` hook kept from rendering without matching stills gets an
  empty list in the combined index and a warning.
- **Outputs**: `RenderResult.frames_index` (`Path | None`); `vidgen render` prints `frames:
  <index>`; `render --json` `outputs.frames` (path or `null`; key added within version 1).

## 14. Refinements (Step 11, storyboard)

- **`vidgen storyboard [PROJECT] [--scene ID ...] [--per-beat N] [--variant NAME] [--preview |
  --final] [--width PX] [--jobs N] [--force] [--json]`** (`vidgen/storyboard.py`
  `make_storyboard(project, *, preview=True, scenes=None, per_beat=1, width=1280, jobs=1,
  force=False) -> StoryboardResult`; reference: docs/CONFIG.md "Storyboard"). Preview format by
  default. Writes `<render_dir>/storyboard/video-<p>.png` (whole video; not with `--scene`) and
  `storyboard/scenes/<scene>-<p>.png`, `p` = page 1, 2, ... The folder is cleared first (with
  `--scene`: the video pages and those scenes' pages), so no stale sheet survives.
- **Built on Step 10's stills**: for each selected scene, `storyboard.stills_current(project,
  preview, scene_id, per_beat)` checks the scene's timings (format, `render.frames ==
  per_beat`, `render.fingerprint`), its `frames/<scene>/index.json` and PNGs. Scenes that fail
  (or all selected with `force`) are rendered by `pipeline.render_scenes(project, preview, ids,
  jobs, frames)`: the same workers as `render_project` (`_render_scenes`, renamed result type
  `SceneRuns`), with audio, dispatching `post_scene` but not `pre_render`/`post_render`, no join;
  it removes the combined `frames/index.json` when it renders anything. Stills are then read
  from the per-scene indexes and timings (beat texts); a still's video time uses scene starts
  summed from the per-scene timings' durations (`null` if a scene has no render at the format).
- **Fingerprint** (`vidgen/render/fingerprint.py`, `scene_fingerprint(project, scene_id)`): a
  SHA-256 over the scene's config entry, the config minus `scenes`/`variants`/`lint` (Step 13; the entry without `lint_ignore` and, Step 39, `chapter`) (with the variant
  applied), the beats' MP3 size+mtime, the contents of the `.py` files of the extension folders,
  size+mtime of the files under `<root>/assets`, the vidgen version and a digest of vidgen's own
  source except `NOT_RENDER_INPUTS` (CLI, JSON, schema, sheets, storyboard, pipeline, ffmpeg,
  subtitles, tts: modules that cannot change pixels or timing; new modules count by default).
  The worker computes it before rendering and stores it as `render.fingerprint` in the scene's
  timings (key added; older renders have none and count as stale). Since Step 60 `vidgen render`
  uses it too (§63: renders only stale scenes; `--force` all).
- **Sheet layout** (`vidgen/sheets.py`, `compose_pages(title, subtitle, scenes, frame_size, *,
  width, detail, video_times, max_height) -> list[SheetPage]`): white page, a title line and a
  line saying what stills/times mean; per scene a grey header band `N/M  id · type ·
  start–end (duration)` (details dropped when narrow); stills of a beat side by side (a
  *block*), each labelled `beat @ time` (`k/n @ time` with several per beat, the beat id then
  prefixes the narration), the narration wrapped under the block (4 lines on video sheets, 6 on
  scene sheets, `…` when cut). Columns: 16:9 → 4 (scene sheets 2), ~square → 5 (3), 9:16 → 5
  (4); with N stills per beat the multiple of N nearest to that (≤ 8). Scenes that fit in the
  rest of a row share it. Pages are `width` px wide (640–2000, default 1280; font sizes scale
  with it) and at most about `1.25 x width` high, balanced so the last page is not nearly
  empty; a scene continued on a new page repeats its header marked `(continued)`. Fonts: Inter,
  else DejaVu Sans / Arial / Liberation Sans / Helvetica, else Pillow's built-in font.
- **Why these sizes**: an AI agent sees the PNG through an image tool that downsizes large
  images (around 1.2 megapixels / 1568 px long edge); at 1280 px wide the 19 px labels and
  narration stay readable after that, which one huge image of the whole video would not.
- **JSON** (`jsonout.storyboard_document`, `storyboard` in `cli.JSON_COMMANDS`): `project,
  variant, preview, per_beat, format, folder, rendered, reused, elapsed, sheets: [{kind
  (video|scene), scene, page, pages, path, width, height, frames: [{scene, beat, k, n, time,
  scene_time, path}]}]` (`mid`, Step 83: the actions a mid-action still shows, else null; §69.16).

## 15. Refinements (Step 12, layout introspection)

- **What**: whenever stills are captured (worker `--frames N`, so `render --frames`,
  `--frames-per-beat` and `storyboard`), `vidgen.introspect.LayoutRecorder` — a second
  `FrameCapture` listener next to `StillWriter` — describes the same frames as data and the
  worker writes `<render_dir>/layout/<scene>.json` (`worker.scene_layout_path`). Not behind a
  separate flag: it costs ~50 ms per 1080p still (measured on kphi3; negligible next to the
  render), and stills and layout then always come from the same render. It is the input of
  Step 13's `vidgen lint` (§16). Reference: docs/CONFIG.md "Layout dump".
- **Format** (`LAYOUT_VERSION = 1`): `{version, scene, type, width, height, fps, per_beat,
  px_per_unit, background, safe_area: [x0, y0, x1, y1], frames: [{beat, k, n, frame, time,
  still, camera: {center, width, height}, objects}]}`; frames carry the stills index keys and
  `still` (`../frames/<scene>/<file>`, relative to the layout file; `capture.still_name`).
  Objects: `{id, kind, class, path, name, bbox, opacity, z, order, parts}` plus, for text kinds
  (`text|code|math|number`), `{text, font_px, color, colors, backdrop}` and otherwise
  (`shape|group|image|icon`) `{fill: {color, opacity}|null, stroke: {color, opacity,
  width_px}|null}`; kind `icon` (Step 19, §22) also has `icon` (the name). Pixels: output frame, origin top-left, y down, frame `[0,W] x [0,H]`,
  1 decimal. Colours `#RRGGBB`.
- **Measuring**: points go through the scene's own `camera.points_to_subpixel_coords`, so a
  `MovingCamera` frame (zoom/pan) is honoured. VMobject curves are sampled at 5 parameters per
  cubic (anchors+handles would overstate round glyphs); visible strokes widen the box by half
  their width (`stroke_width * camera.cairo_line_width_multiple` units). Images: their corner
  points, opacity = max alpha of the pixel array. Visibility per drawn leaf: max of fill alpha
  and (if `stroke_width > 0`) stroke alpha; leaves at 0 are ignored, objects without a visible
  leaf are not listed (fade-ins show as fractional `opacity`).
- **Grouping** (walk of `scene.mobjects`): text mobjects (`Text`, `MarkupText`, `Paragraph`,
  `SingleStringMathTex` = `Tex`/`MathTex`, `DecimalNumber`) are one object; inside a `Code`,
  paragraphs are kind `code` (Manim's invisible alignment suffix ` pA<n>` removed from `text`)
  and the background is a shape; a group whose family has no text or image is one `group`
  object (fill/stroke of its largest part); other groups are walked into; a group drawing
  points itself also yields a `shape`. Each mobject is visited once.
- **Identity**: `id` = `m<N>` per Python object for the whole scene (the recorder keeps the
  objects alive so `id()` is never reused); `path` = parent chain of `Class[index]` segments,
  replaced by the name where the scene named a mobject (a public attribute of the scene, or a
  `Mobject.name` other than the class name).
- **Sizes and colours**: `font_px` = 75th percentile of the visible glyph heights (outline,
  output px): ≈ cap height for mixed case, x-height for all-lowercase-without-ascenders text;
  robust to punctuation and to one large glyph, and works the same for Tex. `backdrop` = the
  most common exact colour inside the text box in the captured frame, after dropping pixels
  within RGB distance 60 of the text's own colours (unless that leaves < 5 %; boxes are
  subsampled to ≤ 40 000 pixels; colours are grouped in 5-bit bins first so anti-aliasing does
  not split the vote). `order` = position of the object's top-most part in Manim's draw order
  (`extract_mobject_family_members` with z-index).
- **Staleness/reuse**: the worker deletes the layout file before every render (like the stills);
  `pipeline._usable_render` with frames requested also requires it; `frames/index.json` scene
  entries gain `layout` (`../layout/<id>.json` or `null`). `introspect.py` counts in the scene
  fingerprint (it changes the layout output).
- **Limits**: `text` is the string the mobject was built with (Manim's `become`/`Transform`
  keep it; the built-in `bar_chart` counter now updates it); during
  `TransformMatchingShapes`/`TransformMatchingTex` loose glyphs are shapes; while Manim's Cairo
  renderer animates, moving mobjects are drawn over static ones regardless of z-index, which
  `order` does not model; 3D cameras are only as right as `transform_points_pre_display`.

## 16. Refinements (Step 13, `vidgen lint` layout rules)

- **Command**: `vidgen lint [PROJECT] [--scene ID ...] [--rule NAME ...] [--variant NAME]
  [--preview | --final] [--fail-on error|warning|info|never] [--jobs N] [--force] [--json]`
  (`vidgen.lint.lint_project(project, *, preview=True, scenes=None, rules=None, fail_on=None,
  jobs=1, force=False) -> LintResult`; reference: docs/CONFIG.md "Lint"). Exit code 1 iff a
  finding is at least as severe as `fail_on` (`--fail-on`, else `lint.fail_on`, default
  `error`); with `--json` that document has `ok: false` and `error.kind` `error` (`details:
  {fail_on, counts}`) and still lists every finding.
- **Input**: the layout dumps (§15) of the **beat-end stills** (`k == n`) only: mid-beat stills
  show fades and motion in progress, which would be noise. Stills are reused when
  `storyboard.stills_current(project, preview, scene, per_beat=None)` holds (now: any stills
  count, and the layout file must exist); other scenes are rendered with one still per beat
  by `pipeline.render_scenes` (as the storyboard does). Objects below `lint.min_opacity`
  (0.1) are dropped first (the end of a fade).
- **Framework** (`vidgen/lint/rules.py`): `@rule(name, scope="still", default=severity)`
  registers `check(context, settings) -> Iterable[Issue]` in `RULES`; `name` must be in
  `config.LINT_RULES`, whose order is `RULES`' order, and `config.LintRules` has one settings
  model per rule (subclass of `RuleConfig`: `severity: error|warning|info|off|None`); a test
  keeps the three in sync. `Issue(message, bbox, objects=(), severity=None, value=None,
  limit=None, group=None)`. Scope `still` gets a `StillContext(layout, frame, objects, still)`
  (`width`, `height`, `short_side`, `region(box)` = the still's RGB pixels, read lazily).
  Step 14's timing rules use scope `scene` (§17); findings, config, ignores and report are
  shared.
- **Severity** of a finding: the rule's configured `severity`, else the issue's own (rules
  escalate: `off_frame` error for text / warning otherwise, `min_font` error below
  `error_size`), else the rule's default. `off` skips the rule.
- **Merging** (one problem, one line): findings of a scene with the same rule, severity and
  object ids are merged across beats (`beats` lists them, the first gives `beat`, `time`,
  `still`); then findings first seen at the same still with the same rule, severity and
  `group` (default: the object's parent path, e.g. an axis' tick labels; `contrast` groups by
  colour, backdrop and opacity) become one finding with the others in `similar` and `also N
  more like it (...)` in the message. Order: scenes in config order, then scene time,
  severity, rule order.
- **Sizes** are fractions of the frame's **shorter side** (`StillContext.short_side`), not the
  height: equal for landscape, and for 9:16 the height would make the same text count 1.78x
  smaller, although a phone shows either orientation with its shorter side across the screen.
- **Rules** (thresholds in `config.LintRules`, defaults documented in docs/CONFIG.md):
  `off_frame` (bbox beyond the frame by > `tolerance` 0.004; wholly outside objects skipped;
  non-text objects spanning an axis edge to edge are intentional bleeds on that axis: cover
  images, Ken Burns, backgrounds, bands), `safe_area` (text only, inside the frame but past
  the layout's `safe_area` by > `tolerance` 0.01), `text_overlap` (intersection ≥
  `min_overlap` 0.1 of the smaller box; identical text with IoU > 0.9 skipped), `covered_text`
  (a non-text object drawn later (`order`) whose fill/stroke colour, blended at its opacity
  over the text's backdrop, shows in ≥ `min_covered` 0.02 of the middle of the text's box,
  counted on the still's pixels, excluding pixels of the text's own colours; skipped: the
  text's ancestors, shapes below opacity 0.3, shapes whose colour is within RGB distance 40
  of the text or backdrop colour (a strike-through); images: their box), `min_font` (cap
  height < `min_size` 0.025 → warning, < `error_size` 0.018 → error; cap height =
  `font_px * 0.73 / p75(per-character em heights)` with x-height letters 0.55, descender
  letters 0.76, punctuation 0.15, others 0.73, so all-lowercase text is not penalised; math
  uses `font_px`; text without a letter or digit skipped), `contrast` (WCAG 2 ratio of each
  text colour blended at the text's opacity over `backdrop`, worst colour counts; needs
  `min_ratio` 4.5, `large_ratio` 3 when the cap height ≥ `large_size` 0.045, `dimmed_ratio`
  2 when opacity < 0.95 (de-emphasised on purpose); a `code` object of only digits (line
  numbers) skipped), `max_words` (> `max_words` 40 tokens with a letter in `text` objects; code,
  math and numbers do not count; `object` null, `bbox` the union).
- **Config**: `VideoConfig.lint: LintConfig` (`fail_on`, `min_opacity`, `rules`) and
  `SceneConfig.lint_ignore: list[RuleName | "all" | LintIgnore]` (`LintIgnore(rule, object,
  beat)`; `beat` must be a beat of the scene; `SceneConfig.lint_ignores()` normalises).
  `object` is matched with `*`/`?` wildcards only (brackets literal, so paths like
  `VGroup[2]/*` work) against the object's name, path and text (either object of a pair).
  Both are excluded from the render fingerprint (`fingerprint.scene_fingerprint`), and the
  `lint` package is in `NOT_RENDER_INPUTS`.
- **Output**: `Finding.to_json()` = `{scene, beat, time, scene_time, rule, severity, object,
  other, similar, bbox, message, value, limit, beats, still}` (objects as `{id, kind, class,
  name, path, text, bbox}`); `jsonout.lint_document` adds `{project, variant, preview,
  format, fail_on, rules, scenes, stills, rendered, reused, elapsed, counts, ignored,
  findings}` to the envelope. Human report (`lint.report_lines`): a header, findings grouped
  by scene (`severity rule beat @ t (+N more beats): message` + `still: <path>` relative to
  the current folder), a count line and `failed: ...` when failing.
- **Limits**: only beat-end stills; boxes are rectangles (rotated text, curves); `opacity` is
  the max over an object's parts, so per-line dimming inside one `Paragraph`/`Code` is not
  seen; `text` may be stale after `Transform` (§15), so messages can quote the old string
  (the still and `bbox` are right); `backdrop` is the most common colour, approximate over
  busy images.

## 17. Refinements (Step 14, timing lint)

- **Rules** (`vidgen/lint/timing_rules.py`, scope `scene`, all default `warning`):
  `narration_speed`, `dead_air`, `animation_overrun`, `rushed_animation` (Step 100 adds
  `talked_over`, §69.34); settings models
  `NarrationSpeedRule`, `DeadAirRule`, `AnimationOverrunRule`, `RushedAnimationRule` in
  `config.LintRules` (names added to `LINT_RULES`/`RuleName`); defaults and the rule table in
  docs/CONFIG.md "Lint". Same command, report, JSON, `lint:` config and `lint_ignore` as §16.
- **Framework**: `Scope = "still" | "scene"`. A `scene` rule gets `SceneContext(scene_id,
  activity, audio_dir)` (`fps`, `beats`, `beat_at(t)`: the beat whose start ≤ t, pad
  included) once per scene and yields `Issue`s with the new fields `beat` (`None` in a silent
  scene) and `time` (scene seconds). The runner (`run._timing_findings`) makes one finding per
  issue (`still` = the beat-end still of `beat`, `bbox` and `object` null); issues sharing a
  `group` become one finding with all their `beats`. `Finding.still` may be `None` (report and
  JSON handle it). Human report: rule column widened to 17 characters.
- **Input: the activity file** (`vidgen/activity.py`, `ACTIVITY_VERSION = 1`,
  `worker.scene_activity_path` = `<render_dir>/activity/<scene>.json`), written by the worker
  whenever stills are captured, deleted before every render like the stills and layout;
  `storyboard.stills_current` and `pipeline._usable_render` (with frames) require it, so
  renders from before Step 14 count as stale; `frames/index.json` scenes gain `activity`.
  Content: `{version, scene, type, fps, frames, duration, pad, silent: {duration, busy} |
  null, beats: [{id, start, end, busy, source: audio|estimate, text, window?, overlap?,
  interrupt?}], plays: [{start, end,
  beat, animations, wait, requested}], motion: {step, grid, level, changes: [[frame,
  fraction]]}}` (docs/CONFIG.md "Activity file").
- **Play log** (`NarratedScene.play` overrides Manim's to append a `PlayRecord`; Manim's `wait`
  goes through `play`, so waits are recorded with `wait: true`). `narrate()` sets the current
  beat for the log and stores `beat_busy[id]` = time its body took before the wait up to
  `d + pad`; `tear_down` stores `silent_busy` before holding a silent scene. `play_steps` marks
  the plays it shortened with `requested = cap`. Recording never changes frames or timing.
- **Motion signal — why from the renderer**: `MotionTrack` is fed by `FrameCapture._observe`
  (`FrameCapture(per_beat, listeners, motion=None)`), which already sees every frame Manim
  writes, with `num_frames` for frozen waits. Each written frame is sampled on a grid (every
  `step = ceil(short side / 180)`-th pixel: 3 at 480p, 6 at 1080p) and compared with the
  previous one; `fraction` = share of sample points with a channel moved by > 6 (0-255);
  only changed frames are stored. ~1.3 ms per written frame (a frozen wait is one), a few
  percent of a preview render. Decoding the scene MP4 with ffmpeg/PyAV afterwards would be a
  second pass, add codec noise (every frame "changes" slightly, needing a fuzzy threshold) and
  could not run without the MP4; the renderer's frames are exact (a static frame is
  bit-identical), so a tiny threshold works. Only recorded with stills (`--frames`,
  storyboard, lint), which is when lint needs it.
- **`narration_speed`**: spoken words (`timing_rules.spoken_words`: hyphens/dashes/slashes
  split words; digit runs `min(len, 3)` words, `+1` per decimal separator and symbol, `+1` for
  letters next to digits; 2-5 letter all-caps acronyms half a word per letter) per second of
  speech: with an MP3, its length minus leading/trailing silence (10 ms envelope below -40 dB
  of the peak; `speech_bounds`, cached by path+mtime); without audio, the estimated `d`, so
  the rate only deviates where spoken words differ from `len(text.split())` or the configured
  `words_per_second` is itself outside the range: those findings are `info`, grouped into one
  per scene. Beats under `min_words` (5) spoken words are skipped.
- **`dead_air`**: static runs between changed frames (`fraction >= min_change`, default 0.0002
  ≈ 9 sample points, which ignores the near-zero first/last frames of eased animations), the
  tail to the scene end included, longer than `max_seconds` (6). Applies to narrated and
  silent scenes alike (a silent card held still longer than 6 s is reported); the beat is
  where the run starts.
- **`animation_overrun`**: `busy - (d + pad) > tolerance` (0.1 s); the message lists the
  non-wait plays of the beat ending after the narration end. Silent scenes: `silent.busy >
  duration + tolerance`. `time` = narration end (or `duration`).
- **`rushed_animation`**: plays with `requested` set whose run time is below `min_run_time`
  (0.5 s), one finding per beat. Plays a scene shortens itself (e.g. `run_time=d / 5`) are not
  seen: only `play_steps` says what it wanted.

## 18. Refinements (Step 15, layout regions)

- **Module** `vidgen/regions.py`, exported by `vidgen.api`; reference: docs/EXTENDING.md
  "Layout regions". `Region(x0, y0, x1, y1)` (frozen dataclass, Manim units, y up; negative
  sizes are a `VidgenError`): `width`, `height`, `center`, `orientation`, `point(align)`,
  `contains(mob, tolerance)`, `inset(x, y)`, `below(mob_or_y, gap)` / `above(...)` (clamped,
  may have zero height), `rows(n | weights, gap)` (top to bottom), `columns(...)` (left to
  right), `split(...)` (columns, or rows when the **active frame** is portrait), `grid(rows,
  cols, gap, gap_y)` (row-major cells), `to_rectangle()`. Default gap `GAP = 0.3` units.
- **Frame and safe area**: `frame_region()` from `config.frame_width/height` (shorter side 8,
  §5.2); `safe_area(margin_x=MARGIN_X, margin_y=MARGIN_Y)` (0.6 / 0.5). Single source of truth:
  `NarratedScene.margin_x/margin_y` default to those constants, `NarratedScene.safe_area` is
  `regions.safe_area(self.margin_x, self.margin_y)` (`safe_width`/`safe_height` derive from
  it), and the layout dump's `safe_area` (§15), which lint's `safe_area` rule reads, is built
  from the same function (`introspect.LayoutRecorder.document`), so values are unchanged.
- **Orientation**: `orientation(w, h)` = `landscape` if w > 1.2 h, `portrait` if h > 1.2 w,
  else `square`.
- **Named regions** (`region(name, area=None, gap=GAP)`; `NarratedScene.region(name)` uses the
  scene's safe area): `full`; `header` (top band, height share of the area 0.16 landscape /
  0.15 square / 0.12 portrait); `caption` (bottom band 0.12 / 0.11 / 0.09); `body` (below the
  header, gap apart); `hero` (between header and caption); `top` / `bottom` (halves);
  `left` / `right` (`area.split(2)`: halves side by side, **but the upper/lower half in
  portrait**, so a two-column layout written for 16:9 becomes two rows in 9:16; literal halves:
  `area.columns(2)`); `center` (centered box, shares of width x height 0.72 x 0.72 / 0.86 x
  0.72 / 1.0 x 0.6). Unknown names → `VidgenError` listing `REGION_NAMES`.
  `grid(rows, cols, area="full", gap, gap_y)` takes a name or a Region.
- **`place(mob, area, fit="contain", align="center", *, max_scale=None, buff=0.0)`**: `contain`
  scales up or down to fit both sides, `width`/`height` match one side (the other may
  overflow), `none` keeps the size; zero-size sides are ignored; `max_scale` caps the factor
  (`1.0`: shrink only). `align` is one of `ALIGNMENTS` (`center, top, bottom, left, right,
  top_left, top_right, bottom_left, bottom_right`; spaces/hyphens accepted) or a Manim
  direction (`UL`, only its signs count): the mobject's matching edge/corner goes on the
  region's (`move_to(point, aligned_edge=...)`). Unknown fit/align → `VidgenError`.
- **Readable size**: `readable_size(font=None, *, fraction=None, margin=1.05)` = the font size
  (points) whose capital `H` is `fraction` of the frame's shorter side, times `margin`.
  `fraction` defaults to `min_text_fraction()`: the active project's
  `lint.rules.min_font.min_size` (default `MIN_TEXT_FRACTION = 0.025`), so layout and lint
  share the threshold; that one lint value is therefore part of the render fingerprint (key
  `readable`), while other lint settings still are not. Inter and the default `Monospace`
  (JetBrains Mono NL since Step 18) measure ≈ 0.0101 units of cap height per point → ≈ 20.8 pt at any resolution (theme `small`
  20 is below it, `caption` 24 above, matching what lint reports).
- **`readable_text(text, area, *, size="body", min_size=None, theme=None, **fit_text_kwargs)`**:
  `fit_text` into the region starting at `max(size, floor)` with `min_size = floor =
  max(readable_size(), min_size)`, so long text wraps instead of shrinking; if it still does
  not fit the height it is scaled down (as `fit_text` does) and a warning is logged on
  `vidgen.regions` (shown as `warning:` by the worker). Not positioned. Built on
  `layout.fit_text_sized` (new, internal: `fit_text` returning the final font size after any
  scaling; `fit_text` delegates to it, behaviour unchanged).
- **Built-ins on regions**: `bullets` — heading fitted into and centered in `header`, list
  centered in `safe_area.below(heading)`; in portrait the heading is `portrait_growth` (1.3,
  class attribute) larger, a short list (≤ 5 items, rows < 75 % of the space) grows up to 1.3x
  and rows are spaced 0.8 x the line pitch (0.55 in landscape). `code` — title in `header`,
  listing scaled into the rest (up to 1.5x, as before); new param `wrap: bool = True`: while
  the listing is width-bound and would end below `max(size, readable_size(font))`, long lines
  are wrapped (`scenes/code.py`: `lex_code` lexes the whole text with Pygments into runs per
  line, `wrap_runs(rows, columns)` breaks the run stream after the last space or `,`/`;`
  outside a string literal if past half the line, else after an opening bracket (not in a
  string or comment), else a space inside a string, else after `/ - . _` inside a word, else
  hard; continuation lines indented 4 more and keeping their tokens' types; never narrower
  than `MIN_COLUMNS` 20) and the listing rebuilt. Manim's `Code` gets the wrapped text as
  `language="text"` and `paint_code` colours its glyphs from the runs (Manim would lex each
  wrapped piece as a separate line: an apostrophe in a `//` comment then opened a string). Wrapped listings number original lines only (continuation numbers
  replaced by empty groups; the dumped `text` of the number column is still Manim's string)
  and highlights map original lines to all their wrapped lines. Landscape output of both is
  unchanged except the title/heading now centered in `header` (a few px lower).

## 19. Refinements (Step 16, theme presets)

- **Config**: `ThemeConfig` gains `preset: Identifier | None` and `code_style: str | None`
  (a Pygments style, checked against the installed styles); `background` and `font` now default
  to `None` (= "not written"), so a preset can supply them. Variants deep-merge as before, so a
  variant `theme: {preset: NAME}` switches the preset while base `theme:` values still apply
  (and still win). Reference: docs/CONFIG.md "Theme presets".
- **Precedence** (highest first, `Theme` in `theme.py`): `video.yaml` `theme.*` > the preset
  (`preset_chain()`: the preset, below it its `base`, recursively) > `register_theme_defaults`
  > built-in defaults. For `colors`/`sizes` the layers merge per token; `background`, `font`,
  `code_style` and `palette` take the highest layer that sets them. Without `theme.preset` the
  preset layer is empty, so output is unchanged for existing projects (the built-in defaults are
  the `dark_tech` values). Rationale: a preset is an explicit choice in the config, so it beats
  defaults an extension registered in code, but never a value written in the config.
- **Presets** (`vidgen/presets.py`, `ThemePreset` frozen dataclass: `name, description, base,
  background, font, code_style, colors, palette, sizes, origin`; `None`/empty = not set):
  `BUILTIN_PRESETS` = `dark_tech` (= the defaults), `light_academic` (off-white `#F8F7F3`,
  near-black text, ink accents, white `surface`, `code_style: xcode`), `high_contrast` (black,
  white text, saturated accents ≥ 7:1, `caption` 26 / `small` 24). Values: docs/CONFIG.md table
  (a test keeps it in sync). `DEFAULT_*` constants moved here (`vidgen.theme` re-exports them).
- **Default `dim` changed** from `#6B7280` (3.91:1 on `#0E1116`, below WCAG AA; every dim
  caption was a lint `contrast` warning) to `#838B98` (5.5:1 on the background, 5.0:1 on
  `surface`): a visible change, dim text is slightly lighter.
- **Project presets**: `vidgen.api.register_theme_preset(name, *, base, background, font,
  colors, palette, sizes, code_style, description)` → `presets.make_preset` (validates names,
  hex colours, positive sizes, Pygments style) → `Theme.add_preset` (error on a built-in name,
  a duplicate, or an unknown `base`). Stored on the active `Theme`, so they are per project like
  `register_theme_defaults` (every `activate` builds a fresh Theme). Presets are looked up when
  a value is read; an unknown name raises `VidgenError("unknown theme preset ...; known
  presets: ...")`. `Theme.derive(config)` builds a variant's theme sharing the registered
  defaults and presets (used by `schema.project_themes`).
- **Validation/schema**: `vidgen validate` reports an unknown preset as `theme.preset: ...`
  (and skips the scene checks, which all need the theme); `vidgen schema` gives `preset` an
  `enum` of the built-in and project presets (`schema.theme_presets`) and `code_style` an
  `enum` of the installed Pygments styles.
- **Contrast check** (`vidgen/lint/color.py`): `theme_contrast(theme, *, text_ratio=4.5,
  graphic_ratio=3.0) -> list[ContrastCheck(subject, color, against, against_color, ratio,
  minimum)]` (`.ok`): `text`/`dim` on the background and on `surface` need 4.5:1 (WCAG AA
  text), the accent tokens (`accent, highlight, primary, secondary, tertiary`) and the palette
  3:1 on the background (WCAG 1.4.11 graphical objects / large text). Tests run it on every
  built-in preset. `hex_rgb` now accepts `#RGB` and `#RRGGBBAA` (alpha ignored).
- **Built-ins on light backgrounds**: no built-in hard-codes white/black; colours come from
  theme tokens and the image caption band from `theme.background`. Changed: `code` `style`
  defaults to `None` = `theme.code_style` (a dark style on a white window was unreadable);
  `bullets` dims earlier items to `dimmed_opacity = 0.45` (was 0.4: a dimmed `primary` marker
  on `light_academic` was 1.9:1, under lint's 2:1 for de-emphasised text).

## 20. Refinements (Step 17, more presets and type scales)

- **Type scales** (`vidgen/scales.py`, manim-free): `TYPE_SCALES` `compact` (48/36/32/28/22/20
  for title/subtitle/heading/body/caption/small), `standard` (56/42/36/32/24/20 = the built-in
  `DEFAULT_SIZES`), `large` (66/50/44/38/30/26); `auto` = `AUTO_SCALES[orientation]` (`large`
  for portrait, `standard` for landscape/square). `frame_orientation(w, h)` is the classifier
  (`regions.orientation` now delegates to it). No scale goes below `small` 20 (the lint
  `min_font` floor is ≈ 19.8 pt).
- **Config**: `ThemeConfig.scale: Literal["compact", "standard", "large", "auto"] | None`;
  presets gain `scale` and `fonts` (`ThemePreset`, `make_preset`, `register_theme_preset`).
- **Theme orientation**: `Theme(config, *, orientation="landscape")`, `Theme.for_format(config,
  fmt)` (used by `runtime.set_context` and `NarratedScene` with the project's **final**
  `format`, so preview and final render share sizes), `derive(config, fmt=None)` (variants:
  `schema.project_themes` passes the variant's format). `Theme.scale_setting` (as chosen),
  `Theme.scale` (resolved).
- **Size precedence**: a scale is shorthand for the six sizes at the level where it is chosen.
  `Theme.sizes` = base, then registered extension sizes, then per preset in the chain (lowest
  first) its scale's sizes then its `sizes`, then the config's scale's sizes, then the config's
  `sizes`. The base is `DEFAULT_SIZES` when any level chooses a scale, else the `auto` scale for
  the orientation — so with no scale anywhere, extension defaults still override the built-in
  sizes (as in Step 16), while a chosen scale overrides them for the six scale tokens (like a
  preset's colours override extension colour defaults). **Visible change**: portrait projects
  that choose no scale get `large` sizes (was standard); landscape output is unchanged.
  Built-in scenes fit text into regions, so larger sizes wrap/shrink rather than overflow
  (checked: storyboard + lint of examples/minimal `--variant vertical`, render test at 9:16).
- **Font roles hook**: `ThemePreset.fonts` (role → family, roles are identifiers);
  `Theme.fonts` merges the chain, `Theme.font_for(role)` = `video.yaml` `font` if written, else
  the chain's family for the role, else `Theme.font`. No built-in preset sets roles and no
  built-in scene reads them yet (Step 18 bundles serif/mono fonts and wires them; §21 changes
  the precedence: a config `font` no longer overrides roles).
- **Presets**: `BUILTIN_PRESETS` (built through `make_preset`, so validated at import) adds
  `warm_editorial` (cream `#F6F0E4`, espresso text, petrol/terracotta, Pygments `default`),
  `brand_neutral` (grey `#F4F5F7` with white `surface`, graphite text, one blue, `xcode`),
  `soft_pastel` (dusky plum `#252238`, pastel accents, `zenburn`) and `bold_neon`
  (violet-black `#0B0614`, cyan/magenta/yellow, `monokai`, scale `large`). Every built-in preset
  sets a `scale` (`auto`, `high_contrast` and `bold_neon` `large`) and no `sizes`;
  `high_contrast` dropped its `caption: 26, small: 24` for `large`. Values: docs/CONFIG.md table
  (test keeps it in sync). Code styles were chosen so every Python token colour reaches 4.5:1
  on the preset's `surface`.
- **Palettes**: 4–6 ordered colours; every built-in palette colour reaches 4.5:1 on its
  background (charts draw series labels in palette colours; the first draft of the light
  presets got lint `contrast` warnings on line-chart labels at 3.9:1). Colour-blind check
  `vidgen.lint.color.palette_distinctness(palette) -> {vision: min CIEDE2000}` for `normal` and
  simulated `protanopia`/`deuteranopia`/`tritanopia` (Machado et al. 2009 full-severity
  matrices on linear RGB; `simulate_cvd`, `lab`, `delta_e` = CIEDE2000). Built-in presets
  except `dark_tech` reach ≥ 7.5 under all four (tested); `light_academic` and `high_contrast`
  changed their third colour to reach it (deuteranopia 2.5 → 11.9 and 0.4 → 8.8); `dark_tech`
  keeps the historical default palette (deuteranopia 4.7) so default output does not change.
- **`vidgen list-themes [PROJECT] [--swatches PNG] [--json]`** (`themelist.py`, not a render
  input): per preset (built-in then project) `preset_entry`: values resolved in the project
  (`Theme.derive(ThemeConfig(preset=name))`, so registered defaults and the project's
  orientation apply), `theme_contrast` summary and `palette_distinctness`; plus the type scales.
  JSON: Step 8 envelope, command `list-themes`, documented in docs/CONFIG.md. `--swatches`
  draws one 1280x190 row per preset with Pillow (name/description in its text colours, accent
  chips, `surface` panel, palette bars).
- **`vidgen validate`** logs `theme_contrast` failures of the project's theme (and of each
  variant's, prefixed `[variant]`, unless equal to the base's) as warnings: stderr
  `warning: theme contrast: ...`, JSON `warnings`; they never fail validation.

## 21. Refinements (Step 18, bundled fonts)

- **Bundled families** (package data `src/vidgen/data/fonts/<Family>/`, each with its `OFL.txt`;
  `THIRD_PARTY_NOTICES.md` lists sources, versions and sizes; `pyproject` package-data
  `data/fonts/**/*`): Inter 4.001 (`Inter`: Regular, Bold, Italic), Source Serif 4 4.005
  (`Source Serif 4`: Regular, Bold, Italic), JetBrains Mono NL 2.242 (`JetBrains Mono NL`:
  Regular, Bold; the no-ligature variant, so code shows the typed characters). ~2.0 MB of TTF,
  ~1.1 MB in the wheel. All SIL OFL 1.1, unmodified (Inter/JetBrains Mono decompressed from
  WOFF2, lossless).
- **Registration** (`vidgen/fonts.py`): `register_bundled_fonts()` calls
  `manimpango.register_font` for every file (Linux: fontconfig app font; Windows:
  `AddFontResourceEx` private; macOS: CoreText), once per process, and clears Manim's cached
  `Text.font_list` so its missing-font warning knows them. Pango reads registered fonts when it
  builds its font map (the first text laid out), so registration must precede any text:
  `vidgen.helpers` and `vidgen.regions` call it at import (every vidgen text path imports one
  of them; extensions import them through `vidgen.api`), and the worker calls it first in
  `render_scene`. A file that fails to register is a logged warning (text then uses an
  installed font of that name or Pango's fallback), never an error. A family that is also
  installed system-wide is found twice by fontconfig; either copy renders it (same font).
  Pillow contact sheets and `list-themes --swatches` also prefer the bundled Inter files.
- **Theme tokens**: `font` (sans; default Inter), `font_serif` (default Source Serif 4) and
  `font_mono` (default JetBrains Mono NL), each with the usual precedence (config > preset chain
  > default; `ThemeConfig`, `ThemePreset`, `make_preset`, `register_theme_preset` gain
  `font_serif`/`font_mono`). Config `theme.fonts: {role: token-or-family}` (new, merged per role
  over the preset chain's `fonts`).
- **Font roles** (`Theme.font_for(role)`): setting = config `fonts[role]` > preset chain
  `fonts[role]` > `fonts.ROLE_DEFAULTS` (`code` → `mono`, `quote_mark` → `serif`) > `sans`;
  the tokens `sans`/`serif`/`mono` (`fonts.FONT_TOKENS`) resolve to `font`/`font_serif`/
  `font_mono`, any other value is a family name. **Changed from §20**: a `font` written in
  `video.yaml` is the sans family only and no longer overrides every role (otherwise a config
  `font: Inter`, as in examples/minimal, would silently cancel a preset's serif headings, and
  code listings would lose their mono font). `Theme.fonts` = the roles set by presets + config
  (without defaults).
- **Built-in scenes**: role `heading` for the `title` title, `bullets` heading, `bar_chart` /
  `line_chart` / `code` titles and the `end_card` title; `quote` for the quote text;
  `quote_mark` for its mark (param `mark_font` default `None` = the role; was
  `"Georgia,DejaVu Serif,serif"`); `code` for listings and line numbers (param `font` default
  `None` = the role; was `"Monospace"`, which on Windows was not a monospace font). All other
  text: `body` = theme `font`. `fit_text`/`fit_text_sized` gain `font=None` (default the theme
  font); `readable_text` measures its floor with the `font` it is given.
- **Presets**: `light_academic` `fonts: {heading: serif}`, `warm_editorial` `{heading: serif,
  quote: serif}`; every other preset keeps all-sans text. Source Serif 4 has a smaller cap
  height per point (0.0093 vs Inter 0.0101 units), so serif headings look ~8 % smaller at the
  same size token; headings are far above the `min_font` floor, so sizes were left alone.
- **Fingerprint**: the bundled font files are part of `vidgen_source_digest` (a font update
  re-renders storyboards).
- `vidgen list-themes`: entries gain `font_serif`, `font_mono` and `font_roles` (the family of
  every built-in role); the swatch panel draws "Aa Heading" in the preset's heading family when
  it is bundled.

## 22. Refinements (Step 19, icons: mechanism + seed set)

- **Vendored set** (package data `src/vidgen/data/icons/`, `pyproject` `data/icons/**/*`):
  `lucide/<name>.svg` (unmodified files of npm `lucide-static` 1.52.0), `lucide/LICENSE` (ISC +
  the MIT notice of the Feather-derived icons) and `manifest.json` = `{version: 1, sources:
  {lucide: {package, version, license, license_file, homepage}}, icons: [{name, category, tags,
  source}]}` (sorted by name; tags = Lucide's `tags.json` + `extra_tags`). Seed set: 40 icons,
  5 in each of the 8 categories `icons.CATEGORIES` (`tech, data, science, business, people,
  ui, nature, education`; `ui` = arrows and interface), listed in `tools/icon_set.json`.
  `tools/vendor_icons.py` (not shipped) re-creates the folder from that list (`npm pack`, or
  `--package-dir`), checks names/categories/version, removes unlisted SVGs; Step 20 extended the
  list to 200 (§23). `THIRD_PARTY_NOTICES.md` records the source.
- **Registry** (`vidgen/icons.py`, manim-free): `IconInfo(name, path, category, tags, source,
  origin, overrides)`; `builtin_icons()`, `builtin_sources()`, `project_icons(root)` (every
  `<root>/assets/icons/*.svg`, names `[A-Za-z0-9][A-Za-z0-9_-]*`, optional `icons.json` `{icons:
  [{name, category, tags}]}`, category default `project`; cached per folder by file
  names/sizes/mtimes), `available_icons(root=None)` (built-ins, then project icons replacing by
  name; sorted), `active_icons()` (the runtime project's), `search_icons(icons, text,
  category)` (every word of `text` must be in the name, a tag, or equal the category; ranked
  exact name < name prefix < in name < exact tag < in tag < category, then by name; Step 22
  ranks whole words before substrings, §25),
  `find_icon(name)` / `unknown_icon_message` (difflib close names + icons whose tags match,
  pointing at `vidgen list-icons --search`). Project icon problems are `VidgenError`s;
  `vidgen validate` reports them as `assets/icons: ...`.
- **Mobject** (`vidgen/icon_mobject.py`): `icon(name, size="body", color="text",
  stroke_width=None, *, height=None, theme=None) -> Icon`; `build_icon(info, height, color,
  stroke_width, current=)`. The SVG is pre-processed into a per-process temporary folder
  (Manim's `SVGMobject` writes `<stem>_.svg` next to the file it parses, which would race
  between parallel workers and fail in a read-only install): an invisible `<rect>` spanning the
  `viewBox` is inserted first, `currentColor` becomes a marker colour (Manim reads it as black)
  and `stroke="none"` a zero stroke width (Manim draws it as a white stroke). Then: the rect is
  the `Icon`'s `box` (submobject 0, opacity 0: layout, `place()` and alignment use the design
  box; the layout dump ignores it as invisible), every visible fill/stroke gets `color` (or,
  with `color=None`, only the marker-coloured paint gets the theme `text` colour), each SVG
  stroke width `w` (viewBox units) becomes Manim `w * height / viewBox_height / 0.01` (Cairo
  draws `stroke_width * 0.01` frame units, so the result is resolution independent),
  `stroke-linecap`/`-linejoin` of the root map to `cap_style`/`joint_type`. **Sizes**: a
  size token or number is points as for text; box height = `points * ICON_UNITS_PER_POINT`
  (0.0208 = 1.5 em of Inter: a `body` icon draws ~1.7x the cap height of body text, the ratio
  of 24 px icons to 16 px text in UI kits); `height` is Manim units. `Icon.scale(f,
  scale_stroke=True)` scales strokes by default (Manim's default is False), so `place()`,
  `animate.scale` and `GrowFromCenter` keep proportions. `icon_name`, `icon_origin`.
- **Params**: `vidgen.scene.IconName` = `Annotated[str, AfterValidator, ThemeToken("icon")]`:
  syntax always; with a theme in the validation context (validate, scene construction) the name
  must be in `active_icons()`. `ThemeToken.kind` may now be `icon`: `list-scenes` prints type
  `icon`; the schema export turns `x-vidgen-theme: icon` into `enum` of the active project's
  icon names (`schema.theme_tokens()["icon"]`; built-ins if the project's icon folder is broken).
- **Layout dump / lint**: an `Icon` is one object, kind `icon`, `class` `Icon`, `icon` = its name,
  `fill`/`stroke` of its largest part, `bbox` of its drawn parts. Lint treats icons like other
  non-text objects (`covered_text` when drawn over text, `off_frame`); `describe()` prints
  `icon 'cpu'`; findings' objects gain the key `icon` (`null` for other kinds; added within JSON
  version 1); `lint_ignore` `object` patterns also match the icon name.
- **`vidgen list-icons [PROJECT] [--search TEXT] [--category NAME] [--sheet PNG] [--json]`**
  (`iconlist.py`, not a render input): project root from `find_config_file` without loading the
  config (works while `video.yaml` is broken; no PROJECT and no config in the current folder:
  built-ins); unknown category → `VidgenError` listing them. `--sheet`: 1280 px wide pages, 8
  icons per row (150 px cells, 64 px icon box), name + category under each, at most ~1.25 x
  width high (`<stem>-2.png`... for more; stale extra pages removed); icons drawn by
  `build_icon` through Manim's Cairo `Camera` in one capture per page (same pixels as a render).
  JSON (Step 8 envelope, command `list-icons`): `project, search, category, sources,
  categories [{name, description, count}], count, icons [IconInfo.to_json()], sheets`.
- **Fingerprint**: `icons.py`/`icon_mobject.py` count as vidgen source; the vendored SVGs and
  manifest are part of `vidgen_source_digest`; project icons are under `assets/` (already
  tracked by size+mtime).

## 23. Refinements (Step 20, icons: curated expansion)

- **Set**: 200 Lucide icons, 25 per category, chosen for explainer videos (concepts scripts name:
  hardware/networks/security/AI, chart types/tables/statistics, lab/space/medicine/maths,
  money/growth/commerce/industry, persons/communication/emotions/health, arrows and status
  symbols, weather/plants/animals/landscape, books/school/writing/arts); near-duplicates and
  brand marks left out. Lucide 1.52's current names are listed (e.g. `building-complex`,
  `face-slightly-smiling`, `book-bookmark`, `waves-horizontal`); the old ones are aliases.
- **Tags**: Lucide's `tags.json` + `extra_tags` with the words an explainer script uses for the
  concept (`banknote`: cash, bill, finance; `trending-up`: growth, profit; `shield-check`:
  security, trust; `gauge`: performance, speed, kpi). Every icon has >= 3 distinct tags.
- **Aliases** (manifest entry key `aliases: [str]`, sorted; always present): (1) Lucide keeps
  renamed icons' old names as copies of the new file, so the tool makes every package file that
  has no `tags.json` entry and draws exactly like one vendored icon (comment and `class`
  ignored) an alias of it (`home` → `house`, `pie-chart` → `chart-pie`; an old name drawing like
  two vendored icons is skipped); (2) curated `aliases` in `tools/icon_set.json`
  (`{alias: icon}`): synonyms (`idea`, `ai`, `warning`, `money`, ...) and `bar-chart` →
  `chart-column` (Lucide's `bar-chart` is the axis-less `chart-no-axes-column-increasing`,
  which is not vendored). The tool rejects: a curated alias that is a current Lucide name or
  conflicts with an upstream alias of a vendored icon, an alias of an unlisted icon, and an old
  (alias) name listed as an icon.
- **Resolution** (`vidgen/icons.py`): `IconInfo.aliases`; `builtin_aliases()` (`{alias: name}`);
  `resolve_icon(name, icons)` (name first, then an alias of an icon in `icons`; an alias never
  shadows an icon name); `icon_names(icons)` (names + aliases, sorted). `find_icon` (so `icon()`),
  the `IconName` validator and the schema `enum` accept aliases; `Icon.icon_name` (layout dump,
  lint) is the resolved icon's name. A project icon replacing a built-in keeps its aliases; a
  project icon named like an alias takes the name over (`available_icons` drops it from the
  built-in's aliases). Search: an exact alias scores like a name prefix (1), part of an alias
  like part of a name (2). `unknown_icon_message` also matches aliases, suggesting the icon
  they stand for.
- **Listing**: `list-icons` text lines show `(alias: ...)`; JSON icon entries gain `aliases`
  (additive, envelope version 1).
- **Catalogue**: `docs/ICONS.md` = `iconlist.catalogue_markdown(manifest)` (per category: name,
  aliases, first 8 tags), written by `tools/vendor_icons.py` (`--docs`); a test keeps it equal to
  the shipped manifest.
- **Rendering check**: every icon was compared with a reference rasteriser (cairosvg, not a
  dependency) at 192 px: overlap of inked pixels >= 0.97 for all 200 (arcs, spirals, filled
  dots), so the loader needed no change; tests build all 200 (box, colours, extent) and render
  six with arcs/fills at 96 px.

## 24. Refinements (Step 21, icons in built-in scenes)

- **`grid_shape(n, aspect=None, *, cell_aspect=1.0, max_cols=None) -> (rows, cols)`**
  (`vidgen/regions.py`, exported by `vidgen.api`): `aspect` = width / height as a number, a
  region name or a `Region` (default: the safe area). Every column count without an empty row
  is scored by the cell size it allows at `cell_aspect` (`min(aspect / cols / cell_aspect, 1 /
  rows)`); among shapes within 3 % of the best, fewest empty cells, then fewest rows. `n < 1`,
  non-positive `aspect`/`cell_aspect` → `VidgenError`.
- **Icons scaled with their group**: `vidgen.icon_mobject.scale_icon_strokes(mob, factor)`
  multiplies the stroke widths of the `Icon`s inside a scaled group (not of `mob` itself when it
  is an `Icon`, whose `scale` already does it). `shrink_to_fit` and `place` call it, so icons
  in a list or card keep their proportions when the layout shrinks it. Only icons are affected
  (other mobjects keep Manim's behaviour), so existing output is unchanged.
- **`bullets`**: `items: list[BulletItem]`; `BulletItem(text: str (min 1), icon: IconName |
  None = None)` accepts a plain string (`model_validator(mode="before")` → `{text}`), so old
  configs are unchanged; its JSON Schema is `anyOf: [string (minLength 1), object]`
  (`__get_pydantic_json_schema__`), so the exported schema accepts both forms. Layout per row
  `VGroup(marker?, icon?, text)` (text last): without icons exactly as before. With icons, the
  icons (size = item size x `icon_scale` 0.95 points, box 1.5 em) form a column left of the
  text, centred on the cap height of the first line; numbers stand right-aligned left of that
  column; an item without an icon shows its marker centred in the column (unless numbered).
  Icons use `marker_color`. `dim_previous` now uses `fade(1 - dimmed_opacity)` once per row
  (multiplies each part's opacity) instead of `set_opacity`, which would have made an icon's
  invisible box and unfilled paths visible; for text the result is identical.
- **`title`**: `icon: IconName | None`, `icon_color` (`primary`), `icon_position: above | left`
  (`left` falls back to `above` in portrait). The icon is `icon_height` (1.25) units; above, it
  is stacked over kicker/title/subtitle and the title gets 36 % (was 42 %) of the safe height;
  left, the text width shrinks by the icon and `icon_gap` (0.5) and the icon is scaled to at
  most 1.1x the text block's height. Revealed first in beat 1 (`FadeIn(scale=0.6)`).
- **`end_card`**: `icon: IconName | None`, `icon_color` (`primary`), `icon_height` 1.1 units,
  between logo and title; an icon alone satisfies "at least one of title, lines, logo, icon".
- **`icon_grid`** (`scenes/icon_grid.py`): params in docs/CONFIG.md. Layout: heading in
  `header` (portrait x1.3 like `bullets`), grid in the safe area below it. Shape: `columns` if
  given, else `grid_shape` for each of `cell_aspects` (0.7, 0.9, 1.2, 1.6, 2.2) and each
  distinct shape is planned (`_plan`): column width `min((W - gaps) / cols, 4.2)`; labels and
  sublabels built at one size each, reduced by 10 % steps (not below `readable_size()`) until
  the tallest label block takes ≤ 45 % of a row and the widest word fits the column; icon (or
  disc) height `min(0.6 cell width, 0.85 (row - labels - 0.2), 1.9)`, at least 0.5. Score:
  `(fits, icon_h * min(1, label_size / size)^2)`, so a shape that keeps text at its size and
  icons large wins; if nothing fits, the best one is used and the grid is shrunk as a whole.
  Rows are spread over spare height (≤ 1 unit extra per gap), a short last row is centred,
  labels/sublabels are placed by baseline. Cells (`VGroup(visual, label, sublabel?)`, visual
  = `VGroup(disc, icon)` with `badge`, else `VGroup(icon)`) are added to the scene whole before
  their entrance (a part's introducing animation would otherwise add it alone and dissolve the
  cell); entrance `GrowFromCenter(disc)`, `FadeIn(icon, scale=0.6)`, labels `FadeIn(shift=UP)`,
  lagged. Steps: per item, per `groups` entry, or all; `highlight` adds a last step: other
  cells `fade` to `dimmed_opacity` 0.55 (0.45 left a `dim` sublabel at 1.93:1 on the light
  presets, under lint's 2:1 for dimmed text), the chosen visual is transformed into a 1.15x
  copy in `highlight_color`. `groups`/`highlight` items are 0-based indices (as `bar_chart`'s
  `highlight`) or labels; groups must list every item once.

## 25. Refinements (Step 22, review 1)

- **Font roles in the text helpers**: `T`, `MT`, `NarratedScene.text`/`markup`
  (`helpers.styled`), `fit_text`/`fit_text_sized` and `readable_text` take a keyword `role=None`:
  the family is `font` if given, else `theme.font_for(role)`, else `theme.font`. Additive;
  `readable_text` measures its floor with that family.
- **`region(name, area=None, gap)`**: `area` may also be a region name (`region("left",
  "body")`), like `grid` and `place`.
- **`SceneParams.also_accepts: ClassVar[tuple[type, ...]] = ()`**: other input types a nested
  model is built from (`BulletItem.also_accepts = (str,)`); `describe.type_name` prints them
  before the model (`list[str | BulletItem]` in `list-scenes` and its JSON `type`).
- **`register_theme_defaults`** (`Theme.add_defaults`) rejects token names that are not
  identifiers (`video.yaml` could never override them) and colours that are not `#RGB`,
  `#RRGGBB`, `#RRGGBBAA` (was: any string starting with `#`).
- **Icon search** (`icons._score`): 0 exact name, 1 name prefix or exact alias, 2 a whole word of
  the name or an alias (split at spaces, `-`, `/`, `.`, `_`), 3 exact tag, 4 a whole word of a
  tag, 5 part of the name or an alias, 6 part of a tag, 7 the category. Whole words now rank
  above substrings (`ai`: `brain-circuit`, `bot` before `rain`, `mail`).
- **Lint**: `vidgen lint` logs `theme_contrast` failures of the project's theme like `vidgen
  validate` (`warning: theme contrast: ...`; JSON `warnings`), unless `--rule` excludes
  `contrast` or `lint.rules.contrast.severity` is `off`; they are not findings. Findings
  merging (`run._group_similar`) also merges findings of one still with the same rule,
  severity and object `text` (a label repeated in copies of a component, e.g. two decoder
  boxes' "Attention"), besides the parent-path group.
- **Built-ins on regions / 9:16**: `quote` (`portrait_growth` 1.25 for the text, mark and
  author; `place(card, safe_area, max_scale=1)`), `equation` (`portrait_growth` 1.25 for the
  formulas, positions from the safe area; new param `caption_size`), `image` (with `fit: cover`
  the caption is placed at the bottom of the `caption` region, i.e. on the safe area's bottom
  edge, and the band runs from the frame's edge to 0.3 above it: it was 12 px into the margin),
  `bar_chart`/`line_chart` (new params `caption_size` = `caption` (was the fixed `small`, below
  lint's `min_font`) and `caption_color` = `dim`; caption fitted to 15 % of the safe height).
  16:9 output is unchanged except the chart captions (24 instead of 20 pt) and the cover-image
  caption (0.2 units higher). `title`, `end_card`, `text_card` and the chart bodies were left
  as they are: their 9:16 sheets read well since the Step 17 `auto` scale; charts move to shared
  helpers in Step 30.
- **CLI**: `list-themes --sheet PNG` is an alias of `--swatches` (as `list-icons --sheet`).
  Checked: every command with `--json` (validate, list-scenes, list-themes, list-icons, schema,
  render, storyboard, lint) answers errors with the envelope, `ok: false`, exit 1 (usage: 2).
- **Tests**: marker `slow` on the 18 slowest render tests (several seconds each); `pytest -m
  "not slow"` is the quick run, `-m "not render"` the fastest; the default runs everything.

## 26. Refinements (Step 23, per-beat actions)

- **Config** (`config.ActionConfig`, `BeatConfig.actions: list[ActionConfig] = []`; reference:
  docs/CONFIG.md "Beat actions"). Canonical form `{action: NAME, target, at, until, run_time,
  ...options}`: `action` an identifier; `target` a name or pattern (`*`/`?`, brackets literal)
  or a non-empty list of them; `at` in [0, 1) of the beat's narration (default 0); `until` a
  later beat of the same scene (checked by `SceneConfig`); `run_time` > 0 (default the action
  type's). Every other key is an option of the action (`extra="allow"`, `ActionConfig.options`;
  `ACTION_KEYS` are reserved). **One shorthand**: `{NAME: TARGET, ...options}`; `NAME` is the
  first key that is not one of `ACTION_KEYS` (a wrap validator rewrites it to the canonical
  form and keeps the raw mapping); `ActionConfig.resolved(known)` re-picks the key when that
  one is not a registered action but exactly one other key is (keys sorted by a tool such as
  `yaml.safe_dump`). `target` next to a shorthand is an error. Actions are part of the scene's
  config entry, so they count in the render fingerprint, not in the TTS hash.
- **Registry** (`vidgen.registry`): action types live next to scene types, with the same two
  layers and collision rules (`ActionType(name, cls, origin, overrides)`, `register_action`,
  decorator `action(name, *, override=False)`, `find_action`, `action_names`, `all_actions`,
  `unknown_action_message`; both kinds go through `_add`). `reset/snapshot/restore/isolated`
  cover both layers (`Snapshot` is now a pair). Built-in actions: `src/vidgen/scenes/actions.py`
  (only `from vidgen.api import *`, imported by `vidgen.scenes`).
- **Action class** (`vidgen.actions.Action`, exported): `Options` (an `ActionOptions` pydantic
  model, `extra="forbid"`, theme tokens checked with the theme in the context; field names may
  not be `ACTION_KEYS`), class attributes `run_time` (0.6), `reversible` (`until` allowed;
  requires `revert`), `needs_visible` (True: hidden targets are revealed first),
  `needs_target` (True). One instance per use (`__init__(options, config)`), so `apply(scene,
  targets) -> list[Animation]` can keep what `revert(scene, targets)` needs.
  `check_action_class` validates at registration.
- **Targets** (`vidgen.actions.Target(names, mobject, entrance)`, exported). A scene type
  declares `target_patterns` (doc forms, e.g. `("heading", "item<N>", "item:<text>")`) and
  classmethod `target_names(params)` (every concrete name, for validation without rendering);
  `construct()` registers them with `self.target(names, mobject, entrance=None)` (names match
  `TARGET_NAME`: `word`, `word3`, `kind:any label`; a name may repeat, a pattern selects every
  match). `self.on_screen_parts(t)` = the largest parts of the target that are in the scene's
  family (a group target such as a bar + its labels is never added itself; animating the group
  would make Manim add it and draw its parts twice); `is_shown` = any such part; `entrance(t)`
  = the target's entrance animations, or `[]` when shown. Built-ins build their own reveal
  steps from `entrance()`, which is how **a target revealed early by an action is not revealed
  again by the scene's step** (decision: `reveal` of a shown target is a no-op, not an error —
  whether it is shown depends on timing a static check cannot see). `bullets`: `heading`,
  `item<N>`, `item:<text>` (the row); `bar_chart`: `title`, `bar<N>`, `bar:<label>` (bar +
  value label + category label; title and caption are no longer one `head` group, visually
  identical).
- **Validation** (`actions.scene_actions(type, cls, spec, params, theme) -> (uses, problems)`,
  locations relative to the scene): unknown action (did-you-mean + known list), options
  (pydantic problems at `...actions[k].<option>`), `until` on a non-reversible action, missing
  target, unknown target (difflib suggestions, up to 14 names, the forms, wildcard hint; a type
  without targets names the types that have some). `vidgen validate` reports them as
  `scenes[i].beats[j].actions[k].<key>` (action names and options are checked even when the
  params are invalid; targets need valid params). `plan_actions` raises one `VidgenError`
  with all problems; it runs in `pipeline._check_scenes` (before any worker) and in
  `NarratedScene.__init__`.
- **Timing** (`actions.ActionRunner`, created by the scene when it has actions). `narrate()`
  calls `start_beat(id, d, pad)`: due frame = beat start + `round(at * d * fps)`; reverts of
  applied uses with `until == id` are due at the start, before the beat's own actions. Actions
  run **inside waits only**: `wait_seconds` and an overridden `wait` (plain Manim waits in
  extension code) hand the wait to `ActionRunner.wait(frames)`, which waits to the due frame,
  plays the due actions and waits the rest (`_wait_frames` is the old frame-exact wait). So an
  action never shares a `play` with the scene's own animation of the same mobjects; with `at:
  0` it follows the beat's entrance step. Run time = the configured/default run time, scaled
  down so all phases end by the beat's end (`d + pad`), quantised to whole frames; shortened
  plays carry `requested` (lint `rushed_animation`). Phases: entrances of hidden targets
  (`reveal_time` 0.6 s) for `needs_visible` actions, then batches of due actions whose target
  families do not overlap (actions on one target play one after the other). `end_beat()` (after
  the final wait of `narrate`) applies what found no time without frames (`_apply_now`:
  begin + finish) and logs a warning. `play_steps` now ends slot *k* at `start + (k+1)·slot`
  (absolute), so an action that lengthened a slot's wait is absorbed by later waits (no
  change without actions beyond frame rounding; every built-in's timing test still holds).
- **Built-in actions**: `reveal` (run time 0.8, `needs_visible` False: the targets' entrances).
  `dim` (`opacity` 0.45 relative to the current, reversible). `highlight` (`color` =
  `highlight` token, `style` `color` | `box` | `underline` | `flash` or a list; `flash` and
  `color` cannot combine; reversible: colours restored, box/underline faded out).
  Colour/opacity changes use `Repaint`, an animation of the fill/stroke RGBA arrays of every
  `VMobject` in each on-screen part (points untouched); revert restores only the channels the
  action changed (RGB for highlight, alpha for dim) from the arrays saved at `apply`, so the two
  combine and undo independently. Box: `SurroundingRectangle(buff 0.12, corner_radius 0.1,
  stroke 4)`; underline: `Underline(buff 0.08, stroke 4)`. A first `pulse` style (Indicate-like
  scaling about the target) was dropped: a bar scaled about its group's centre crossed the axis.
- **Listing / schema**: `list-scenes` prints `targets:` per type and an `actions` section;
  `--json` adds `targets` to scene types and a top-level `actions` list (`describe.
  action_type_json`; keys added within version 1). `vidgen schema`: `BeatConfig.actions.items`
  = `anyOf` [`ActionConfig` (`action` enum, per-action `if`/`then` with the options and
  `additionalProperties: false`), `ActionShorthand` (`anyOf` one object per action: `required:
  [NAME]`, its options, `additionalProperties: false`)]; options under `$defs/action.NAME`
  (theme tokens as for params). Targets and `until` are left to `vidgen validate`.
- **Limits / for Step 24**: only `bullets` and `bar_chart` have targets; `dim`/`highlight`
  recolour vectorized mobjects only (images keep their pixels); `dim` compounds with a scene's
  own dimming (`bullets` `dim_previous`); `highlight` keeps the target's current opacity (a
  dimmed item is highlighted dimmed). Step 24 adds `zoom`/`transform` and targets for the
  other built-ins on this framework.

## 27. Refinements (Step 24, zoom, transform, targets everywhere)

- **Camera.** `NarratedScene` subclasses Manim's `MovingCameraScene` (was `Scene`). The camera
  frame starts on the whole frame (`config.frame_width` x `frame_height`, aspect kept for 9:16),
  so scenes that never move it render pixel-identically (whole suite and every example
  unchanged). `NarratedScene.play` removes the frame from `self.mobjects` after a play that
  added it (Manim adds the animated mobject; the frame is never drawn), unless it has updaters
  (an extension's follow-cam). The layout dump already measured with the scene's camera
  (`camera.center/width/height`, §15); it gains `camera.zoom` (= `config.frame_width /
  camera.frame_width`, added within layout version 1). `lint.StillContext.zoomed` (zoom >
  1.001): `off_frame` and `safe_area` skip zoomed stills (cutting the scene off is the point).
  **For Step 38 (overlays):** anything drawn as a mobject in the scene moves with the camera; a
  screen-fixed overlay must either follow `camera.frame` (an updater scaling/moving it with
  the frame) or be composited outside Manim (ffmpeg), which also keeps it out of scene renders.
  (Step 38 composites in the renderer's `add_frame` instead, §41.)
- **Framework additions** (`vidgen.actions`): `Action.temporary` (requires `reversible`): the
  runner schedules `revert` itself, due `run_time` before the end of the *return beat* — the
  use's own beat, or with `until: B` the beat before `B` — so the effect is over when the next
  beat (resp. `B`) starts; at `until` beats it is not undone again. `Action.moves_camera`: two
  such uses never share a batch (the camera frame counts as a shared mobject).
  `Action.target_options`: option names whose values are target names (str or list):
  `scene_actions` checks them like `target` (problems at `...actions[k].<option>`);
  `check_action_class` requires them to be `Options` fields. Ordering on one frame: `until`
  undoings, then the beat's actions, then temporary undoings (`_rank`). Budget: when actions
  run, the time of temporary undoings still pending in the beat is reserved, and both are
  shortened by one factor when the beat is short (`factor = remaining / (phases + reserved)`).
  An undo of a use that was never applied is skipped. `resolve_targets(scene, pattern)`: a
  plain name shared by several targets selects the ones on screen, else the first (patterns
  select all) — used for equation terms registered once per step.
- **Full opacity** (`Target.rest`, a dict `id(member) -> (fill, stroke)` filled at
  registration, shared by a scene's targets via `NarratedScene._rest`; `rest_opacity(member)`
  falls back to 1/0 for members created later, e.g. a value label rebuilt by `become`). Scenes
  register targets right after layout, before any opacity changes of their own.
- **`dim`** now means "at most `opacity` x full opacity": each member's alpha array is scaled
  so its maximum is `<= full x opacity` (ratios kept, so gradients and transparent pixels
  survive); nothing that is already dimmer changes, so dimming never compounds. Exposed to
  built-ins as `scenes.actions.dim_to(target, part, factor)`; `bullets` `dim_previous` and
  `icon_grid`'s highlight step use it (same values as their former relative `fade`).
- **`highlight`**: `style: color` also raises alpha to full (a dimmed target is highlighted at
  full opacity); revert restores RGB and sets alpha to min(current, saved) (undoes the raise,
  keeps dimming that happened since). Box around `Target.outline` (default the mobject);
  `bar_chart` gives each bar an outline = bar + final value label, stopping `outline_gap`
  (0.15) short of the axis, so the box (buff 0.12) stands on the axis instead of crossing it.
- **Images**: `Repaint` also animates the `pixel_array` of `ImageMobject` members
  (`paint_image(member, rgba float array)`): `dim` scales the alpha channel, `highlight` tints
  RGB 30% towards the colour (`image_tint`); `_Memory` saves pixel arrays for undo.
- **`zoom`** (`run_time` 1.0, reversible, temporary, moves_camera; options `scale` (> 1, <= 8)
  and `padding` (0.15, share of the view on each side)). The view: the union box of the
  targets' on-screen parts; magnification `min(max_scale=3, (1-2p) x frame/box)` per axis, or
  `scale`; centre clamped so the view stays inside the frame. Magnification <= 1.01 → no move
  and a warning (the targets fill the frame). Revert: back to the whole frame (no-op when home).
  Animation `MoveCamera(scene, width, center)` (a `Transform` of the frame; its name shows in
  the play log / activity file).
- **`transform`** (`run_time` 1.0, not reversible; options `into` (required; `target_options`)
  and `style` `auto|replace|shapes|tex|fade`). The source's on-screen parts are removed and a
  copy added (so the originals stay intact, and a group target never added whole is not drawn
  twice), then morphed into `into` (its hidden matches); `auto` = `TransformMatchingShapes` when
  both sides are text/formulas only, else `ReplacementTransform`; non-vector sides use
  `FadeTransform`; `tex` without two `MathTex` falls back to shapes (warning). `into` already on
  screen: the sources fade out towards it (warning). **Decision: `into` must be a target**, not a
  text literal: a literal has no place, size or style in the scene's layout; scenes that need
  alternatives provide them as targets (equation steps). Scene steps that would animate a
  transformed-away target skip it (`bar_chart`/`icon_grid` highlight steps, `bullets`
  `dim_previous` via `on_screen_parts`).
- **Targets of every built-in** (table in docs/CONFIG.md "Beat actions", kept in sync with
  `target_patterns` by `tests/test_actions_coverage.py`): `title` (`icon`, `kicker`, `title`,
  `subtitle`, `authors`), `text_card` (`text`), `quote` (`mark`, `quote`, `author`, `source`),
  `equation` (`step<N>`, `caption`, `term:<tex>`; new param `terms`: substrings isolated with
  `MathTex(substrings_to_isolate=...)`, each must occur in a step; a term target per step that
  contains it (`get_part_by_tex`, first occurrence; works with Manim 0.19 and 0.21), entrance
  `[]`), `code` (`title`, `listing`, `line<N>` = physical lines + numbers of original line N,
  `lines:<a-b>` for every a < b; `target_names` counts a `path` file's lines through
  `current_project()`, none without a project context), `image` (`image`, `caption` = the text,
  entrance fades the caption group), `line_chart` (`title`, `axes`, `series<N>`,
  `series:<name>`, `point:<name>@<x>` with `x` as its tick label; without dots a point is a
  separate dot that its entrance fades in), `end_card` (`logo`, `icon`, `title`, `line<N>`),
  `icon_grid` (`heading`, `item<N>`, `item:<label>`). Every built-in builds its steps from
  `self.entrance()`; `equation` steps morph from whichever step is on screen, and a step is
  skipped once a later one is shown.
- **Listing**: `list-scenes` shows `, undone by the beat's end` for temporary actions;
  `--json` actions gain `temporary` and `target_options` (within version 1). `vidgen schema`
  adds required options (`into`) to both action forms.

## 28. Refinements (Step 25, `stat` and `chapter`)

- **`stat`** (`scenes/stat.py`; reference docs/CONFIG.md): params `value`, `label`, `context`,
  `prefix`/`suffix` (number size), `unit` (`unit_ratio` 0.42 of it, on the number's baseline:
  median glyph bottom), `decimals` (default `needed_decimals([value, comparison.value])`, up to
  2), `thousands` (`,`), `decimal_mark` (`.`), `count`, `count_from`, `comparison`, `icon`,
  colours (`color` `primary`; `good_color` `tertiary`, `bad_color` `accent`, `neutral_color`
  `dim`: in every built-in preset `tertiary` is the green and `accent` the red), sizes (number
  `value_scale` 3.0 x `title`). `format_number(value, decimals, thousands, decimal_mark)`
  (module function, typographic minus, no "minus zero"). `StatComparison` (nested, `also_accepts
  = (float,)`: a plain number is `{value: N}`; JSON Schema `anyOf` number | object like
  `BulletItem`): `value`, `label`, `kind: versus | before` (`before` = before → after: the count
  starts at the old value), `word` (default `vs`/`from`, translatable), `delta: difference |
  percent | none`, `better: higher | lower | neither`. The change chip (`Stat.change() -> (text,
  colour token, direction)`) is an arrow (a filled `Triangle`, none for no change) + the signed
  delta in a pill filled with the theme's `surface` and stroked in the colour: a tint of the
  colour behind the delta cost it contrast on light presets (lint `contrast` 4.0:1 on
  `light_academic`), the surface keeps every preset's text ≥ 4.5:1.
- **Count**: the layout is built with the final value (the number's font size is chosen so the
  wider of start/end fits 92 % of the safe width and 42 % of its height, then the card is
  `place`d with `max_scale=1` and the size scaled with it, so the count never changes size).
  Targets are registered at that full look; then the number line shows the start value. Its
  entrance is one `UpdateFromAlphaFunc` (linear) that rebuilds the line each frame
  (`ease_out_cubic` value, fade over the first `fade_share` 25 %, rising 0.15 units into place),
  keeping the final line's top edge and centre x (digits have one height, so nothing jumps);
  `become` + `original_text` as in `bar_chart` so the layout dump sees the shown string.
- **`chapter`** (`scenes/chapter.py`): `title` (required; **the chapter's name** — Step 39's
  indicator and Step 49's chapter list read `params.title` of `chapter` scenes, `number_text()`
  for the number), `number: int | str` (`number_format` `{:02d}` for ints, checked by formatting
  7), `subtitle`, `icon`, `rule`, colours, sizes (number 2.4 x `title` for ints, 1.6 x for text).
  Layout: landscape with a number or icon → `VGroup(left column (icon over number), vertical
  rule, left-aligned title block)`; else stacked and centred (icon, number, short rule
  `rule_length` 1.6, title, subtitle). Entrance: rule `Create` (vertical, drawn downwards) /
  `GrowFromCenter`, number/icon slide in from the left (from above when stacked), title from
  the right (from below), subtitle rises; lagged 0.25. Steps: with ≥ 2 beats `[head,
  subtitle]`, else one step (silent or one beat: the subtitle belongs with the title; two
  steps in one short silent card would rush both).
- Both: Step 15 regions (`safe_area`, `place`), theme tokens and font roles only (numbers and
  chapter titles use the `heading` role), targets per Step 23/24 and the table in CONFIG.md,
  `outro` 0.5, `reveal()` with `fraction` 0.75 (caps 2.0 / 1.6).

## 29. Refinements (Step 26, `comparison` and `table`)

- **Target names may be dotted** (`actions.TARGET_NAME`: `word(.part)*(:label)?`), for parts of
  parts: `col2.item3`, `cell2.4`. Patterns (`cell1.*`) work as before.
- **`highlight` style `fill`**: a `SurroundingRectangle` of the target's outline (`box_buff`
  0.12, corner 0.1, no stroke) filled with the colour at `fill_opacity` 0.22 (below lint's
  0.3 cover threshold; text over it keeps its contrast), faded in by a `Transform` of its
  opacity (not `FadeIn`, an introducer that would move it to the top). It is inserted into
  `scene.mobjects` just before the target's first part when the parts were added on their own,
  else just after the group holding them (then it is a faint overlay), with the parts' lowest
  `z_index`; scenes put backdrops (table stripes, comparison cards) at `z_index` -1 so the plate
  lies between backdrop and text. Undone (`until`) like `box`.
- **`comparison`** (`scenes/comparison.py`; reference docs/CONFIG.md): `columns` (2–3
  `ComparisonColumn`: `heading`, `icon`, `tone: positive | negative | neutral`, `points` ≤ 8 of
  `ComparisonPoint`, a string or `{text, icon}` like `BulletItem`), `heading`, `verdict`,
  `reveal: columns | rows | all`, `markers` (check / x icons, or a dot for neutral), `cards`,
  `vs` badge, tone colours `tertiary`/`accent`/`primary` (as `stat`'s good/bad). Layout: heading
  in `header` (1.3x in portrait), verdict at the bottom of the body, `Region.split(n)` for the
  card slots (columns in landscape, rows in portrait), cards of one size (tallest column).
  One text size for every column: from `size` down (x ≤ 0.95 per try) to `readable_size()`;
  still too tall → scaled about the top-left corner and a warning. Rules line up across
  columns side by side; with `reveal: rows` the *m*-th points too. Targets: a column is
  `VGroup(head, rule, points)` (the card is outside, so `color` does not paint it; `outline` =
  the card inset by the box buff); a point's entrance brings its column's card and heading
  first. Steps through `_column_entrance` (frame, then points not on screen), so early
  reveals are never repeated.
- **`table`** (`scenes/table.py`): `rows` (≤ 30, cells `str | int | float`; bool/null rejected
  with a hint), `header` (≤ 8 columns), `title`, `caption`, `align` (`auto` = numbers right),
  `number_format` (str or per column; default `auto_format` of the column, so a column shares
  its decimals), `reveal: per_beat | all`, `zebra`, colours, sizes. `Params.texts()` gives the
  cells as shown (also used for `row:<first cell>`). **Fitting** (`_fit`): sizes `size` x
  (1, .92, .85, .78, .72, .66, .6) and the readable minimum; at each, `_widths` gives natural
  widths (one line, cell padding 0.75 cap each side) or water-fills the area width (columns
  needing less than a fair share keep their natural width, columns whose floor — longest
  header word, body cells > 16 characters by word, shorter cells and numbers whole — exceeds
  the share get the floor); the first size whose widths fit and whose height fits wins.
  Nothing fits → built at the readable size, scaled to the area, warning "split it into
  smaller tables or drop columns" (lint `min_font` reports it too). A narrow landscape table
  spreads its columns up to 1.25x (at most 80 % of the width). Rows: cells positioned by first
  baseline; header rule `header_color`, stripes every other row (`z_index` -1), end rule
  `rule_color` drawn with the last row. Every cell text is added on its own (so a `fill` plate
  sits just under a row's / column's cells); invisible row/column/cell rectangles (inset by the
  box buff) are the targets' outlines.

## 30. Refinements (Step 27, `timeline`)

- **`measure_text(text, max_width, *, size, weight, slant, line_spacing, balance, theme, font,
  role) -> TextMeasure(lines, width, height, fits)`** (`vidgen.layout`, exported): how
  `fit_text` would wrap the text, estimated from the cached word widths (`_Metrics`) without
  building a `Paragraph`; `fits` is false when a word is wider than `max_width` (`fit_text`
  would scale the block down). Estimates run a few percent short of the built text (Pango
  kerning; `fit_text` re-wraps narrower when a built line comes out too wide), so planners
  measure at ~0.97 of the width and check the built result. Reason: building a `Paragraph`
  costs 0.1–0.3 s for a long text; the timeline's size search over two layouts took 90 s for
  10 long events when it built every candidate, 5 s with `measure_text`.
- **`fit_text(..., balance=False)`** (also `fit_text_sized`, `measure_text`): wrapped text is
  re-wrapped at the narrowest width (down to half of `max_width`, binary search on the
  metrics) that keeps its number of lines, so a two-line title has no lone last word.
  Additive; off by default (existing scenes unchanged).
- **`timeline`** (`scenes/timeline.py`; reference docs/CONFIG.md): `events` (2–10
  `TimelineEvent`: `date: str | int | float` — a YAML date object becomes its ISO string, bool
  rejected — `title`, `text`, `icon`, `at`), `heading`, `orientation: auto | horizontal |
  vertical` (`auto`: horizontal unless the frame is portrait), `sides: auto | alternate | one`,
  `spacing: even | proportional`, `reveal: per_beat | all`, `highlight` and `now` (event refs:
  an int in range is a 0-based index, else the date as shown, else the title; ambiguous →
  error), `now_label`, colours, sizes. `date_position()` parses numbers, years, `YYYY-MM` and
  `YYYY-MM-DD` (fraction of the year); proportional spacing needs a position for every event in
  non-decreasing order (validation errors otherwise).
- **Geometry** in axis coordinates (`along`, `across`; `_point`): events at `pad + q·usable` with
  `pad` = half an even gap at both ends; proportional `q` is blended towards even (`w` in steps
  of 0.05) until neighbours keep `min_gap_share` (0.45) of the even gap and the markers do not
  touch. Each event's text (a "card": date row, title, detail) may use the stretch along the
  axis up to halfway to the neighbouring events *on the same side* (less `card_gap`) or the
  body's end; across it, the room from the stem (`stem` 0.3 beyond the marker) to the body's
  edge. Horizontal: card width = that stretch (≤ `max_card_width` 5.2), centred over the
  marker and pushed inwards at the ends; vertical: card width = the side's room (≤ 5.6), card
  height ≤ the stretch, text aligned towards the axis, the date's line level with the marker
  where there is room. Everything is centred across the axis at the end.
- **Fitting** (`_plan` per side mode): one factor for all events; date/title/detail sizes are
  `max(min(size, floor), size·factor)` (floor = `readable_size()`, the heading role's for
  titles). Factor 1, then 1.2 (`growth`) if that adds no wrapped lines, else reduced (×0.75–0.93
  per try) to the factor where every size is at its floor. Measured with `measure_text`
  (balanced, at 0.97 width); the built cards (`fit_text(balance=True)`) are scaled down alike if
  one is still taller than its room. Not fitting at the floor → `fits` false → the warning
  "split it into two timelines (or shorten titles and texts)" (lint `min_font` reports it too).
  `sides: auto` builds both plans and keeps the better by (fits, factor up to 1, fewer lines,
  factor): growth never decides the layout; typically alternating in 16:9, one column right of
  the axis in 9:16 for ≤ 6 events, alternating for more.
- **Drawing**: track (`axis_color`, 0.55 opacity, tip) from half a gap (≤ 0.7) before the first
  event to as far past the last; markers (`icon_radius` 0.3 disc on the background colour,
  outlined, with the icon or a small dot, when any event has an icon; else a filled 0.12 dot);
  stems; one progress segment per event (`progress_color`, from the previous marker's edge or
  the track start to its marker's edge; `DashedLine` after `now`); `now` → a ring in
  `now_color` and a tag (pill on `surface`, outlined in `now_color`, as `stat`'s chip for
  contrast) after the date; events after `now` have hollow markers.
- **Steps / targets**: steps `[event 1 (with heading and axis), event 2, ...]` (`all`: one
  step), then the `highlight` step (others `dim_to` 0.55; the chosen marker ×1.2 and its title
  in `highlight_color`). `_reveal(indices)` builds one `Succession`: the axis if not shown,
  then per event not shown the missing segments up to it and its marker/stem/card — so an
  early `reveal` of event 3 grows the line through event 2's position without showing event 2,
  and the scene's own steps never repeat an entrance. Targets `heading`, `axis` (the track),
  `event<N>` / `event:<date>` (marker + stem + card; segments are not part of a target).


## 31. Refinements (Step 28, graph layout and `diagram`)

- **`vidgen.graph`** (manim-free; exported by `vidgen.api`): `layered_layout(nodes, edges, *,
  direction="LR"|"TB", layer_gap=1.0, node_gap=0.5, routing="straight"|"orthogonal",
  port_spacing=0.2, port_spread=0.6, label_margin=0.15, sweeps=12) -> GraphLayout(nodes:
  {id: NodePlace(x, y, width, height, layer, order)}, edges: [EdgeRoute(source, target, points,
  reversed, label_at)], layers, width, height, direction, crossings, reversed_edges)`. Nodes
  are ids or `GraphNode(id, width, height, shape)` (`box`/`ellipse`/`diamond`/`stadium`: the
  outline ports are clipped to); edges `(source, target)` or `GraphEdge(source, target,
  label=(w, h))`. Result centred on the origin, y up, in the nodes' units. Unknown ids, duplicate
  ids, self-loops, unknown direction/routing/shape → `VidgenError`.
- **Phases.** (1) Cycles: depth-first search in input order; back edges are laid out reversed
  and their routes reversed again (`EdgeRoute.reversed`). (2) Layers: longest path from the
  sources, then each source with successors moves to just before its nearest successor;
  edges spanning *k* layers get *k − 1* dummy items. (3) Order: from two starts (input order and
  its reverse; later layers by first predecessor), barycenter sweeps alternately down and up
  (ties keep the current order) with adjacent-swap transposition, best order kept; phases 1–3
  depend on the topology only and are cached (`_topology`, `lru_cache`), because the scene lays
  out one graph at many sizes. (4) Coordinates: a layer's centre line is spaced by the deepest
  item of the neighbouring layers plus the gap (`layer_gap`, or label extent + 2 `label_margin`
  for a labelled edge leaving its source through that gap); across, items are packed with
  `node_gap` (half next to a dummy), then 10 passes (alternately towards predecessors and
  successors, ending with successors so parents sit centred over their children) set each
  layer to the weighted least-squares fit of the neighbours' mean under the separation
  constraints (pool adjacent violators; dummies weigh 2x so long edges run straight).
  (5) Routes: ports on the facing sides, ordered by the cross position of the edge's next point
  and spaced `port_spacing` apart within `port_spread` of the side, clipped to the shape;
  `straight` = polyline through the dummies; `orthogonal` adds per gap a run in a lane of its
  own (lanes assigned greedily, downward runs before upward ones, so nested runs do not
  cross). Label anchor: the first segment from the real source at the middle of its gap (for
  orthogonal routes the nearest point of the route to it). `crossings` counts crossings of the
  dummy graph between neighbouring layers.
- **`diagram`** (`scenes/diagram.py`; reference docs/CONFIG.md; registered again as
  **`flowchart`**: `scene("flowchart")(Diagram)` — the same class under a second name, so
  `list-scenes`, the schema and `validate` treat it as a type of its own; the docs test points
  a second name's CONFIG.md section to the first). Params: `nodes` (1–30 `DiagramNode`: a string
  is `{id}`; `id` letters/digits/spaces/`_.-`, `label`, `shape` box | round | pill | circle |
  diamond | cylinder, `icon`, `color`), `edges` (≤ 60 `DiagramEdge`: `{from, to, label, style:
  solid | dashed, color}`, `from` is the alias of the field `source`; strings `"a -> b"`, `"a ->
  b: label"`, `"a --> b"` dashed, chains `"a -> b -> c"` expanded by a before-validator of
  `edges`; JSON Schema `anyOf` string (`pattern: "->"`) | object), `heading`, `direction`
  auto | LR | TB, `routing` curved | straight | orthogonal, `reveal` nodes | layers | all,
  `steps` (per step a ref or a list of refs; a ref is a node id or `a->b`, spaces around `->`
  ignored), `highlight` (refs), `shape`, colours, `size`/`edge_label_size`/`heading_size`.
  Validation (model validator): duplicate ids, unknown nodes in edges (`difflib` suggestions +
  the node list), self-loops, duplicate edges, unknown or repeated refs in `steps`, unknown
  refs in `highlight`. `describe` now shows a field's alias (`from`) in `list-scenes` and its
  JSON `name` (no other built-in uses aliases).
- **Fitting.** Per direction option (`auto`: the frame's orientation first; the other one is
  kept only if its text is `direction_bias` 1.1x larger) and per label wrap width (`wraps` 3.2,
  2.3, 1.7, 4.4 units at 32 pt, scaled with the size), the size factor goes from `growth` 1.3,
  1.15, 1, then x0.9 down to where label and edge-label sizes both sit at their floor
  (`readable_size() x floor_margin` 1.05: lint measures short lowercase labels a little small);
  the first factor whose `layered_layout` fits the body wins. The plan key is (fits, factor
  capped at 1 x bias, factor x bias): growth never decides the layout. Then `_spread` widens the
  gaps (layer factor 1.8 → 1, node factor 1.4x that) while it still fits. Node boxes come
  from `measure_text` (content + padding 0.32 / 0.2 x size/32 units; circle = diagonal; diamond:
  half-diagonals `a = x + 1.5 y`, `b = a / 1.5`; pill: + 0.35 h; cylinder: + two rims);
  icons stand above the label in LR layouts, circles and diamonds, else left of it. Nothing
  fits at the floor → scaled down whole and the warning "split it into smaller diagrams (or
  shorten labels)".
- **Drawing.** A node is `VGroup(shape, icon?, label)` (z 1): the shape filled with its colour
  at `fill_opacity` 0.1 (a tint: `highlight` style `color` then paints a highlight tint under a
  highlight-coloured label that keeps 4.5:1 on light presets; 0.14 did not) and stroked at 3.
  Cylinder: a closed body path (top arc, side, bottom arc, side) + the front rim arc without
  fill. An edge is `VGroup(line, tip, label?)`; `curved` lines are cubic Béziers between the
  route points with handles along the main axis (S-curves; the arrowhead points along the
  axis into the node), `straight`/`orthogonal` polylines; the line stops 0.9 tip-lengths before
  the route's end and a filled triangle tip ends on the outline; `dashed` = `DashedVMobject`.
  An edge label sits on a pill of the background colour (z 2, not part of the target, so
  colour highlights do not paint it) at the route's label anchor.
- **Steps.** Groups per step: `steps` (+ one step with the nodes no step names), else per
  `reveal` in layout order (layer, then order). A step plays in waves (`_reveal`): nodes no
  pending edge leads to, then edges whose source is on screen (`Create`, linear; dashes one
  after another; then tip and label), then the nodes they reach, … (a cycle inside a step starts
  at its first node). Edges between nodes on screen come along unless a later step names them;
  a named edge brings its ends. `highlight` adds a last step: listed nodes (outline stroke
  1.5x, tint 1.6x, icon in `highlight_color`; labels unchanged) and edges (listed, or between
  consecutive listed nodes; line 1.6x wider) recoloured, every other node/edge `dim_to`
  `dimmed_opacity` 0.55. `reveal(fraction=0.75, cap=1.6)`, `outro` 0.5.
- **Targets.** `heading`, `node<N>`/`node:<id>` (outline = the shape, so a `box` frames it),
  `edge:<from>-><to>` (line, tip, label; its entrance as a target brings its hidden ends first).


## 32. Refinements (Step 29, `process` and `network`)

- **Network helpers** (`helpers.py`, exported; kphi3 renders unchanged): `column(n, x, gap, y0,
  r, color, *, horizontal=False, skip=None)` — `horizontal` lays the dots out left to right along
  `y0` centred on `x`; `skip=k` spreads `n` dots over `n + 1` slots leaving slot `k` empty (an
  ellipsis). `edges(a, b, pairs, color, width, opacity, *, colors=None, shorten=0.0)` — one
  colour per pair, lines trimmed by `shorten` at both ends (from the rim of dots).
  `grouped_pairs(n, groups, m=None)` — blocks from `group_bounds(n, groups)` (near-equal,
  `round(g * n / groups)`; identical to the old `n // groups` blocks when `groups` divides `n`),
  block `g` of the first layer to block `g` of the second (`m` units). `sparse_pairs(n, m, ratio,
  seed=0)` — each pair kept with probability `ratio` (numpy `default_rng(seed)`), then any unit
  of either layer left without a pair gets one; sorted, reproducible.
- **`process`** (`scenes/process.py`; reference docs/CONFIG.md): `stages` (2–8 `ProcessStage`:
  a string is `{label}`; `label` unique, `icon`, `text`), `heading`, `layout: auto | row | snake |
  column`, `reveal: per_beat | all`, `loop` (+ `loop_label`), `input`, `output`, `token`,
  `token_icon`, `token_label`, colours (`stage_color`, `active_color`, `token_color`, ...) and
  sizes (`size`, `text_size`, `io_size`, `heading_size`). `auto`: `column` in portrait; else
  `row`, or `snake` (two rows, the second right to left, joined by a turn on the right) for ≥ 4
  stages when its text is `layout_bias` (1.1x) larger — growth never decides; when no layout
  fits, the one that needs the least scaling down.
  **Planning** (`_fit`/`_geometry`): one size factor for label/detail/io sizes (up to `growth`
  1.2 without more lines, down to the factor where every size sits at `readable_size()`),
  measured with `measure_text`; card width = the room left after the io labels (which stand
  above their arrows: lead = max(gap, label width + 0.3)) and gaps (`gap` = max(0.7, token
  diameter + 0.45)), capped at 3.4 (6.0 in a column), never narrower than the longest word;
  height = the tallest content + padding, at least half the width in rows when there is room
  (`card_aspect`), +0.5 u of air in a column; room before the first stage for the token's halo
  (1.7 r) and for its tag centred over the start; bands for the token tag (above rows, a lane left of
  a column), the loop (below a row, a lane right of a column, below and left of a snake). Not
  fitting → warning "shorten the labels and texts (or split the process into two scenes)" and
  the drawing (with the token's paths) is scaled into the body.
  **Drawing**: cards = surface-filled rounded boxes (z 2; content z 3, so a box animated on its
  own does not cover its text) with icon above the text (rows) or left of it (column);
  connectors and the loop are rounded polylines (`rounded_path`, corners as quadratic arcs) with
  a filled tip; the token (z 1: under the cards, over the connectors) is a dot with a halo or an
  icon in a disc; it waits in front of a stage on the incoming connector's tip
  (`rests[i]`); its path to the next stage runs from there through the stage's centre (hidden
  behind the card) and along the connector (`paths[i]`). The tag (pill, z 4) follows the token
  on the same path shifted by a fixed offset (no updaters); it fades while the token loops.
  **Steps** (`_arrive(i)`): previous stage back to `stage_color`, then the token moves while the
  connector it rides grows (if not shown), then the stage appears already active (or, if shown,
  turns active: outline `active_color` at 2x width, icon recoloured); `input` and heading come
  with step 1, `output` after the last stage arrives; `loop` adds step n (token along the loop to
  below/beside stage 1, which becomes active again). `reveal: all`: everything in step 1, later
  steps only move the token. `reveal(fraction=0.75, cap=1.6)`.
  **Targets**: `heading`, `input`, `stage<N>`, `stage:<label>` (outline = the box),
  `connector<N>`, `loop`, `output`, `token` (token + tag). An early `reveal` of a stage shows the
  card only; its step still moves the token there.
- **`network`** (`scenes/network.py`): `layers` (2–8 `NetLayer`: an int is `{size}`; `label`,
  `show`, `connect`, `color`), `heading`, `connect` (`Connection`: `{type: dense | sparse |
  grouped | one_to_one | none, ratio, groups}`, or a string `dense`, `sparse:0.3`, `grouped 3`;
  JSON Schema `anyOf` string | object; default `"dense"`), `direction: auto | LR | TB`,
  `max_neurons` 8, `show` 6, `counts: auto | all | none`, `count_format` `{n:,}`, `reveal:
  layers | all`, `passes` 1 (0–4), `highlight` (`"L.i"` refs, 1-based, units as drawn),
  `max_edges` 64, colours, `group_colors`, `edge_opacity`, sizes. Validation: unique labels, no
  `connect` on the first layer, `count_format` formats `n`, highlight refs in range.
  **Layout**: LR — layers `min(3.4, width / n)` apart, captions (bold label, dim count) in a band
  below; TB (portrait) — rows `min(3.0, height / n)` apart, captions right-aligned in a column
  left of the rows. Unit gap = `min(0.85, room / slots)` (slots = the most drawn units + 1 for an
  ellipsis), radius 0.3 x gap within 0.07–0.22; a truncated layer is `column(..., skip=(m+1)//2)`
  with three small dots in the hole. Edges between drawn units via `Connection.pairs` (sparse
  seeded by the layer index), thinned to `max_edges` (`_thin`: a reproducible sample plus one
  pair per unit that lost all), opacity `clip(2.4 / sqrt(count), 0.2, 0.75)`, width from the
  radius, trimmed to the rims; grouped edges coloured per block with `palette_color`.
  **Steps**: layer k = its incoming edges grow (`Create`, lag) then its units grow one by one with
  the ellipsis and caption; a pass = `LaggedStart` (lag 0.62) of: layer 1 `Indicate` in
  `pulse_color`, then per pair `ShowPassingFlash` copies of the edges and the next layer's
  `Indicate`; highlight = listed units filled `highlight_color` and ×1.3, edges between
  consecutive listed units in neighbouring layers recoloured ×2 width (a missing one drawn), the
  other units, ellipses and edges `dim_to` 0.3. `reveal(fraction=0.75, cap=1.8)`.
  **Targets**: `heading`, `layer<N>` / `layer:<label>` (units, ellipsis, caption), `edges<N>`
  (when the pair has edges), `neuron<L>.<i>` (one dot).


## 33. Refinements (Step 30, chart helpers, `scatter` and `histogram`)

- **`vidgen/charts.py`** (exported by `vidgen.api`; reference docs/EXTENDING.md "Charts").
  Numbers: `axis_ticks(lo, hi, max_ticks=6, *, log=False)` (= `nice_ticks`, or powers of ten:
  1-2-5 steps within two decades, every k-th decade beyond `max_ticks`; `log` needs `lo > 0`);
  `short_number(v, decimals=None)` (`k`/`M`/`B`/`T`); `tick_texts(ticks, fmt=None, unit="", *,
  log=False)` (`fmt` if given; log: `short_number`; else one shared decimals count
  (`auto_format`), suffixed from 10 000 on, `0` stays `0`). `LinearFit(slope, intercept, r2)`
  (callable, `equation(digits=3)` with typographic minus) from `linear_fit(xs, ys)` (`np.polyfit`;
  r² 1 for constant y; < 2 distinct x → `VidgenError`).
- **Axes.** `ChartAxis(lo, hi, ticks, labels, log=False, title="")` (frozen; `fraction(v)`,
  `contains(v)`); `value_axis(values, *, lo, hi, max_ticks, log, fmt, unit, title,
  include_zero)`: domain = data extended to the outer ticks, unless `lo`/`hi` fix an end (then
  ticks outside are dropped) — the old `line_chart` rule. `chart_axes(area, x, y, *, size,
  color, axis_color, grid="y"|"x"|"both"|"none", lines="x"|"xy", right, top, theme) ->
  ChartAxes(plot, x, y, label_size)` with `x_pos`/`y_pos`/`point`/`inside`, `group` and parts
  `lines`, `grid`, `x_labels`, `y_labels`, `x_title`, `y_title`. Layout: y tick labels right-
  aligned left of the plot (gap 0.45 cap + 0.05), y title above them left-aligned at the
  area's top (below `top`), x labels below, x title under them centred (clamped to the area);
  the plot's right end moves in by half the last x label when a tick sits at the end. Label
  thinning `_stride`: the smallest k such that every k-th label clears its neighbour (x: 0.35
  cap + 0.15; y: 0.9 cap), plus the last label when it has room. Gridlines: dashed, stroke 1,
  opacity 0.4, at the *labelled* ticks (not on the axis line). Sizes: `chart_label_size(size)`
  = `max(theme.size(size), readable_size())`.
- **Legend.** `chart_legend(entries, max_width, *, size, color, stack, theme)` (entries `(name,
  colour, swatch)`, swatch `line` | `box` | a marker; rows wrapped to `max_width`, `stack` one
  per row; scaled down only if one entry is wider). `legend_spot(size, plot, points, *, pad=0.15,
  corners=(top_right, top_left, bottom_right, bottom_left))`: the first corner whose box (pad
  inside the plot, pad of air) contains no frame point. `auto_legend(...)`: one row, else
  stacked, in a free corner on a framed panel (`RoundedRectangle`, background fill 0.85, `dim`
  stroke 1 at 0.5; `LEGEND_BUFF` 0.15; `z_index` 1, so gridlines drawn later never cover it —
  lint `covered_text` found exactly that in 9:16) → `(legend, centre)`; no free corner →
  `(row legend, None)` and the caller reserves `top` room and puts it above the plot.
  `sample_path(points, step=0.1)` samples polylines for it. `chart_marker(kind, radius,
  colour)`: `CHART_MARKERS` circle / square (side 1.7 r) / triangle (height 1.95 r) / diamond
  (side 1.6 r, rotated), similar visual weight.
- **Title and caption.** `chart_title(text, *, size="heading", color, growth=None, area)`: bold,
  `heading` role, `balance=True`, fitted into and centred in `region("header")`, x
  `PORTRAIT_TITLE_GROWTH` 1.3 in portrait (as `bullets`). `chart_caption(text, area, *, size,
  color)`: `fit_text` to the area width, ≤ 15 % of its height, at its bottom.
- **`bar_chart` / `line_chart` refactored** (Step 22 findings): title via `chart_title` (was the
  top of the safe area, 18 % high: in 16:9 now a few px lower, centred in the header band; in
  9:16 1.3x larger); caption via `chart_caption`. New params (additive): `title_size`,
  `title_color`, `label_size` (both), `value_size` (`bar_chart`). `bar_chart`: category labels at
  `label_size` (`caption`, was `caption`/`small` by count) with the readable floor as `min_size`;
  value labels: `_value_style` tries the wanted size (`value_size`, default `body`/`caption` as
  before) and 0.9x on one line, then with a word unit (leading space) under the number
  (`unit_ratio` 0.8), then 0.8x, then 0.7x/0.6x, then the floor; nothing fits → in portrait with
  `horizontal` unset the bars turn horizontal (as before also for > 5 bars), else the labels are
  scaled to the slot as before. Horizontal slots are 1.1 (landscape) / 1.5 (portrait) units, at
  least the tallest label + 0.3, bars up to 0.9 thick. The count-up rebuilds a one- or two-line
  label (`become` + `original_text` per `Text`). `line_chart` on `value_axis` + `chart_axes`:
  ticks label with the decimals the *ticks* need (`2.4` instead of `2.40`; `value_format` still
  applies to both), x labels thinned by width instead of "at most 7 (4 in portrait)", tick /
  axis / end labels and legend at `label_size` (`caption`, was `small` for ticks), legend via
  `auto_legend` (inside the plot when a corner is free, else above, as before). 16:9 output:
  same structure; ticks and axis titles 24 instead of 20 pt, title ~0.1 unit lower.
- **`scatter`** (`scenes/scatter.py`; reference docs/CONFIG.md): `ScatterPoint` (`also_accepts
  = (list,)`: `[x, y]` / `[x, y, label]`; JSON Schema `anyOf` array (prefixItems) | object;
  `label`, `group`), `ScatterSeries` (`name`, `points`, `color`, `marker` auto → `CHART_MARKERS`
  by position); `series` dict or list; axes `x_/y_ min/max/log/format/unit/label`; `trend: none |
  each | all` + `trend_label: none | equation | r2 | both` + `trend_color`; `reveal: series |
  groups | all`; `show_labels: all | highlight | none`; `highlight` refs (`<series>@<N>`,
  `<series>@<label>`, a unique label; `Params.point_ref`); `legend` (default > 1 series);
  `point_radius` (default 0.11 / 0.085 / 0.065 / 0.05 for ≤ 20 / 60 / 150 / more points).
  Validation: unique series names and labels per series, positive values and bounds on log
  axes, points inside explicit bounds (no silent clipping), trend only on linear axes with ≥ 2
  distinct x per fit, `trend_label` needs a trend, `groups` needs a group.
  **Layout**: x ticks ≤ 7 (4 in portrait), y ≤ 6 (8 in portrait), grid both, both axis lines;
  legend via `auto_legend` avoiding markers and trend samples. Markers (z 2) get a 1.2 stroke in
  the background colour (overlaps stay apart); trend lines (z 1) run over the fitted points' x
  range, cut where they leave the y domain. Point labels (z 3, a background-colour outline as
  a halo) try right, left, above, below, then diagonals, scored 4·outside the plot + 2·overlap
  of labels/legend + markers covered + 2·trend lines crossed; trend labels are placed after
  them: beside the line's end (away from the line), then on the normal at 6 places along it
  (offset by the label's extent along the normal, so no slope makes them cross), scored 5·lines
  crossed + points covered + 3·boxes; both clamped to the plot. **Steps**: per group a
  `LaggedStart` (lag `min(0.25, 2/n)`) of point pops (`GrowFromCenter`, then the label) sorted
  by x; then the trend (`Create`, linear, then its text); then the highlight (rings 1.9 r in
  `highlight_color`, labels with `show_labels: highlight`, the rest `dim_to` 0.35).
  `reveal(fraction=0.8, cap=2.0)`. Targets per the table; a label that is a number another
  point has as its index names nothing (the index wins).
- **`histogram`** (`scenes/histogram.py`): `values` with `bins` (int: equal bins via
  `np.linspace`; rule `auto` | `sturges` | `sqrt` | `fd`: numpy's bin count, width rounded by
  `nice_width` (nearest of 1, 2, 2.5, 5 x 10^k on a log scale), edges `aligned_edges` on its
  multiples), `bin_width` (aligned, or from `bin_range[0]`), `bin_range`; or `counts` +
  `edges`; `MAX_BINS` 60. `compare` (`HistogramCompare`: `name`, `values` | `counts`, `color`
  `secondary`) binned on the same edges. `percent` (each distribution's own total). `mean` /
  `median`: exact from values; from counts the mean of bin middles and the median interpolated
  in its bin. `highlight`: 0-based indices or range labels. Range labels (`bin:<range>`) are
  `tick_texts(edges, x_format)` joined with `-` (`10-20`, `0-10k`).
  **Layout**: x ticks at the edges when the bins are round (equal nice widths, edges on their
  multiples, or `x_format` given), else round ticks inside; y from 0 (`include_zero`), unit `%`
  with `percent`. Bars inset by `min(0.03, 8 %)` per side. `compare` = a `Polygon` fill at 0.1
  under its step outline (stroke 4). Marker labels (bold, in the marker colour) stand above the y
  title, the second one a line higher if they would touch; room for them is reserved with
  `chart_axes(top=)`; the dashed line runs from the axis up to its label. Legend (with
  `compare`: `name` or `data` as a box, the compare name as a line) via `auto_legend` avoiding the
  outlines and verticals through every bar. **Steps**: bars grow (`ReplacementTransform` of a
  flattened copy, `LaggedStart` lag `min(0.15, 2/n)`), compare, mean, median, highlight (chosen
  bars filled `highlight_color`, others `dim_to` 0.35) — each its own step.


## 34. Refinements (Step 31, `pie` / donut and `heatmap`)

- **Colour helpers** (`vidgen/charts.py`, exported). `mix_colors(a, b, t)`: `a` at opacity `t`
  over `b` in sRGB (what alpha blending shows), `#RRGGBB`. `text_color_on(fill, min_ratio=4.5)`:
  the theme's `text` or `background`, whichever contrasts more with `fill`; below `min_ratio`
  white or black (the better one; the worst case over all fills is ≈ 4.58:1). `ColorScale(lo,
  hi, stops, kind, center)` (frozen): `fraction(v)` (clamped; diverging: 0.5 at `center`, each
  side scaled to its own end), `at(f)` (OKLab interpolation between `(fraction, hex)` stops —
  Ottosson's matrices, sRGB gamma via `lint.color`), `__call__(v)`. `color_scale(values, kind,
  color, low_color, high_color, center, lo, hi)`: sequential stops `mix(color, background, 0.14)`
  → `color` (lightness monotone, "more = more contrast with the background" on light and dark
  presets); diverging `low_color` → `mix(text, background, 0.1)` → `high_color`, domain `center ±
  max distance` unless `lo`/`hi` are given (then `center` must lie inside: `VidgenError`).
  `color_bar(scale, length, vertical, thickness=0.26, size, color, title, max_ticks=5, fmt,
  unit)`: 48 opaque segments + a faint frame, ticks from `axis_ticks` inside the domain with
  `tick_texts` labels (right of a vertical bar, below a horizontal one; thinned with `_stride`),
  optional title above; `VGroup(bar, ticks, labels[, title])` centred at the origin.
- **`pie`** (`scenes/pie.py`; reference docs/CONFIG.md). `Params.slices()` → `PieSlice(label,
  value, color, other)` after `sort` and grouping (`other_below` %, `max_slices`; grouping only
  when ≥ 2 slices qualify; the group is last, `other_color`). Colours: own / one colour / the
  palette in order, past its length lighter shades (`mix(base, background, max(0.4, 1 - 0.3k))`),
  the last slice never equal to the first. Angles from `start_angle` (90 = top), clockwise by
  default; wedges are `AnnularSector`s (inner radius 0 for a pie) with a 2 px background-coloured
  edge. **Layout** (`_plan`): for label sizes from `label_size` down to the readable floor
  (x `floor_margin` 1.05), modes `sides` then `keys` (`legend` alone when `uses_legend()`:
  `legend` or > 6 slices — static, so `target_names` knows it). In each mode up to four rounds:
  labels that fit inside their slice (box corners and edge midpoints inside the annular sector,
  6 % margins; spots at 0.6 / 0.5 / 0.68 / 0.4 r for a pie, mid-ring for a donut; wrap widths
  1.2 / 0.8 / 0.5 r) go inside, the rest outside; `sides`: columns at `r(1 + explode) + ELBOW
  (0.2) + LEAD (0.5)` left/right, room reserved per side only for the sides that have labels,
  labels stacked top-down near their elbow height (`_stack`: `gap` 0.12, pushed back up from the
  bottom; the smallest slices' labels dropped if a side cannot hold them), leader = rim → radial
  elbow → label; `keys`: `chart_legend` swatches + "name value", wrapped rows below the pie in
  9:16 (≤ 60 % of the body, else dropped), stacked beside it in 16:9 (wrapped rows if taller
  than the body), pie and key centred together. The first layout with nothing dropped and
  radius ≥ 0.3 x the body's shorter side wins; else the one dropping fewest (warning). Inside
  labels use `text_color_on(slice colour)`. Donut centre: `center_text()` (the total via
  `value_format`/`unit`) bold in the heading role, fitted to 0.78 x the hole's diameter, plus
  `center_label` in `dim`. **Steps**: wedges grow by `UpdateFromAlphaFunc` rebuilding the
  sector (invisible at alpha 0, the original at 1); `all` = one continuous sweep (each wedge's
  rate is its share of `smooth` over the first 70 %), labels / leaders after 65 %; `per_beat`
  sweeps over 0–65 % and the label over 55–100 % (`window(a, b)` rate functions). Highlight step:
  the wedge (and an inside label) shifts by `explode x r` along its middle, an outside leader's
  first corner follows (`Transform` to the moved polyline), other wedges `dim_to` 0.3, their side
  labels / leaders / keys 0.45, inside labels recoloured with `recolor` to
  `text_color_on(mix(colour, background, 0.3))` at 0.7. `reveal(fraction=0.75, cap=2.0)`.
  **Targets**: `slice<N>` / `slice:<label>` = wedge + label (+ leader), outline the wedge;
  `center`; `legend` = the key (entrance: every slice's entrance).
- **`heatmap`** (`scenes/heatmap.py`). Params `values` (rectangular, `null` allowed, ≤ 40 x 40),
  `rows`/`columns` (unique), `scale` (`auto` = diverging when values lie on both sides of
  `center`), colours, `scale_min/max`, `show_values`, `legend`, `legend_label`, `reveal: all |
  rows`, `highlight` refs (the target names `cell<R>.<C>` / `row<N>` / `row:` / `col<N>` /
  `col:`; `Params.cells_of`). **Layout**: the colour bar (vertical right of the grid in 16:9,
  horizontal below it in 9:16; rebuilt as long as 0.9 x the grid height, 2.4–4.5 units / 0.8 x
  the grid width, 3–5 units), row labels right-aligned (≤ 25 % / 30 % of the width), column
  labels wrapped to the cell width at one size from `label_size` down to the floor (else a
  warning, scaled), cells `min(width / cols, MAX_CELL 2.2)`, height ≤ width ≤ 2.5 x height, the
  whole block centred; gap between cells `min(0.05, 0.06 x side)`; cells smaller than `MIN_CELL`
  (0.3) → warning "split the matrix". Cells are opaque (`surface` + faint outline for null);
  values at the largest size from `value_size` down to the floor at which the four longest
  strings fit (`cell - 0.12` wide, `- 0.1` high), else hidden (warning with `show_values:
  true`), each in `text_color_on(cell colour)`. **Steps**: `all` = labels, legend, and cells
  popping in (`FadeIn(scale=0.6)`) in a diagonal wave (window by `(r + c)`); `rows` = row k's
  label and cells left to right (column labels, legend, title with row 1). Highlight step:
  `highlight_color` outlines (stroke 4, z 2) round each ref's cells; other cells `dim_to` 0.3,
  their values recoloured for the dimmed cell at 0.7. `reveal(fraction=0.75, cap=1.6)`.
  **Targets**: `cell<R>.<C>` (rect + value, outline the rect), `row<N>`/`row:<label>` and
  `col<N>`/`col:<label>` (label + cells; outline a band over the cells; entrance: the hidden
  cells one by one), `legend`, `title`.

## 35. Refinements (Step 32, `code_walkthrough`)

- **`code_walkthrough`** (`scenes/code_walkthrough.py`; reference docs/CONFIG.md). Params `code` |
  `path`, `language`, `excerpt` (`"a-b"`, numbers kept), `title`, `steps`, `visible`,
  `line_numbers`, `style`, `font`, `size`, `wrap`, `highlight_color`, `note_position`
  (`auto | side | bottom`), `note_size`, `note_color`, `focus_scale`, `scrollbar`. **Per-beat
  data** is a params list aligned with the beats (as `code.highlight`, `diagram.steps`): `steps[i]`
  = `WalkStep {lines, note, focus}` or a bare line spec (`also_accepts = (str, int, list)`; JSON
  Schema `anyOf` string | integer | array | object). Steps go through `reveal(fraction=0.6,
  cap=1.0)` like every built-in.
- **Line specs** (`parse_lines` syntax, `resolve_lines(spec, source, first)`): items `N`, `N-M`,
  `/regex/`, and ranges mixing both (`/def f/-/return/`: the end is the first match at or after
  the start), comma-separated (commas inside `/.../` belong to the expression), or a list; `all`
  clears the highlight; `None` keeps the view. Checked at params validation for inline code and
  by `validate_project` for a `path` (problems prefixed `steps[k].lines`).
- **Sizing** (`_fit`, analytic, no trial builds: a listing costs ~0.1 s per line): `size` if
  the longest line fits the window width, else smaller down to `max(readable x 1.05, size giving
  TARGET_COLUMNS)`, else wrapped (`code.wrap_runs` on the whole file's `lex_code` runs, so an
  excerpt starting inside a comment keeps its colour) at that size. A note replacing another
  fades in during the second half of the change, after the old one has faded out in the first
  half (they share the bottom bar). Notes: `side` (16:9 / square,
  when the code fits beside a column of `0.3 x body` (3.4–4.8 units) without wrapping) or
  `bottom` (bar as tall as the tallest note; always in portrait). The window holds `visible` /
  as many rows as fit; window chrome (title bar with three theme-coloured dots, padding, scroll
  indicator) is drawn by the scene, not by `Code`.
- **Scrolling model.** The `Code` (background removed) stays in the scene as one mobject; rows
  out of view are taken out of its two `Paragraph`s' submobjects (`_include`), so they are not
  drawn, `is_shown(line<N>)` is false for them, and the layout dump still sees a `Code` (kind
  `code`, line numbers exempt from contrast); `lines_text.original_text` is set to the shown rows
  so lint sizes the text by its real characters. `_ViewChange` (an `Animation` without a
  starting copy) interpolates offset, per-row emphasis (1 / `DIMMED` 0.35 / 0 around a focus) x
  edge fade (`FADE` 0.75 rows beyond the window), band shapes (cut at the window's edges) and the
  scroll thumb; rows that can show are positioned lazily (`_place_row`), the others never move.
  Offsets: a selection already in view (with a line of context) stays; else it is centred (its
  start when longer than the window). The band's opacity is `BAND` 0.12, lowered (0.1 … 0.05)
  until every syntax colour keeps `min(4.5, its ratio on the window)` on it (light themes); a bar
  in the highlight colour marks the band's left edge.
- **Notes and focus.** Side notes sit level with the step's highlighted rows (pointer line + dot
  from the window edge); bottom notes in the bar. `focus` moves the camera (`MoveCamera` from
  `scenes/actions.py`) onto the selected rows' ink (numbers excluded), magnification `min(limit,
  0.84 fw / w, (0.84 fh - card) / h)`, hides the other rows and shows the note as a card under
  them built at `1 / magnification` (reads at its normal size); a view top inside the title moves
  below it (or above it); magnification < 1.05 → no focus, warning. The next view without focus
  moves the camera home.
- **Targets**: `title`, `listing` (chrome + `Code`), `line<N>` (file numbers; all wrapped
  pieces), `lines:<a-b>` (all ranges up to `ALL_RANGES_UP_TO` 40 lines, else the steps' runs),
  `note<N>` (step N's note or focus card). Entrances: a hidden line scrolls into view (`_bring`;
  leaves a focus), a note plays its step's view, `listing` the first step.
- **`code` changes** (Step 22 routed issue): wrapping targets `max(readable, min(size, size giving
  TARGET_COLUMNS 32 columns))` instead of `max(size, readable)`, so a 9:16 listing at the `large`
  scale wraps at ~32 columns, not ~25 (16:9 unchanged: `caption` already gives > 32 columns).
  New module helpers shared with `code_walkthrough`: `mono_metrics(font)` (advance and line pitch
  per point), `size_for_columns`, `text_canvas` (see below), `renumber`, `line_centers`,
  `line_runs`, `style_names` (were private methods / functions).
- **Manim text canvas** (found here, affects any long text): Manim renders `Text` with Pango on a
  canvas of the *output's pixel size* and fails the glyph check ("rendered fewer glyph(s)...") when
  text runs off it: ~60 lines of 24 pt code at 854x480, 9 at 160x90. `code.text_canvas(lines,
  size)` enlarges `config.pixel_width/height` while a listing is built (restored after; the SVG
  cache key does not include the canvas, so a clipped SVG cached by an earlier failure must be
  deleted with `build/`).


## 36. Refinements (Step 33, `equation_derivation`)

- **`equation_derivation`** (`scenes/equation_derivation.py`; reference docs/CONFIG.md). Params
  `steps` (≥ 1; `DerivationStep {tex, note, match, transition}` or a string, `also_accepts =
  (str,)`, JSON Schema `anyOf` string | object), `title`, `mode` (`history | replace`), `keep`,
  `align_at` (`"="`), `colors` (TeX → colour), `terms`, `result` (`box | highlight | none`),
  `result_color`, `size` (80; 1.25x `portrait_growth`), `color`, `dim_opacity`, `note_position`
  (`auto | side | bottom`), `note_size`, `note_color`, `note_mark_color`. Per-beat data is the
  params list aligned with the beats (as `code_walkthrough.steps`); steps go through
  `reveal(fraction=0.6, cap=1.6)` like `equation`.
- **Part isolation without Manim's substring splitting.** Manim's `substrings_to_isolate` splits
  raw substrings (`x` out of `\exp`, breaking the TeX) and `{{ }}` main parts become top-level
  `MathTexPart`s whose boundaries may cut TeX groups. Instead the scene tokenises the TeX
  (control words, control symbols, characters), finds parts as whole-token runs (spaces ignored;
  the key of a part is its tokens joined by spaces) and wraps each occurrence in its own dvisvgm
  group (`\special{dvisvgm:raw <g id='vgpartNNN'>}` … `</g>`), which Manim's SVG parser exposes in
  `id_to_vgroup_dict`. `{{ … }}` (split with Manim's own `MathTex._split_double_braces`, so the
  notation means the same as in Manim) becomes such a group too, parts inside it nest. Braces are
  added where TeX takes one argument (after `^`, `_`, `\vec`, `\frac`, … : `{\special…x\special…}`);
  a token after `\left`/`\right`/`\big…` is never wrapped. One compile per step (two more at most
  when it is broken into lines). `tex_string` is reset to the step as written (lint, layout dump).
- **Morph** (`morph(source, target, style)`): `auto` pairs parts with the same key (occurrences in
  order, bigger parts first, glyphs used once) → `Transform` per pair; the remaining glyphs go
  through `TransformMatchingShapes` (identical shapes move, others fade). `shapes`: one
  `TransformMatchingShapes`; `fade`: cross-fade. The source is always a *copy* of the step on
  screen; `_Swap` (an `AnimationGroup`) removes `hide` at setup and, at clean-up, every mobject its
  animations used, then adds the target formula whole — so the scene holds whole `MathTex`es
  between beats (targets, lint) and the source step stays intact for later actions.
- **History.** Each step has an archived copy (dimmed at hand-over: `dim_opacity`, raised by
  `readable_opacity` until every formula / note colour keeps 2.3:1 with the background — lint's
  dimmed 2:1 plus margin). When a step arrives, the live previous step hands over to its archived
  copy (moved up a row), so `term:` targets (registered on the live formula's parts) mean the
  current step only, while `step<N>` (registered on `VGroup(live, archived)`) is the line either
  way. The block is re-centred as it grows; the oldest rows fade out upwards beyond `rows`.
- **Layout** (`_layout`). Notes beside (16:9; column 0.3 × body, 3.0–4.6 units) or in a band below
  (portrait, or `note_position: bottom`; the band sits right under the tallest block, both centred).
  All steps share one scale: ≤ 1, fitting the width (aligned steps: left and right reach from the
  alignment point; others centred) and the tallest run of `rows` rows, where a side note taller
  than its formula sets its row's height. A step whose width alone would set it below `COMFORT`
  (1.5) x the readable size is rebuilt with `\\ &` before its top-level relations (`break_lines`:
  all but the first, then all), kept when it gets larger. `rows` (history, `keep` unset) drops
  while the height would push the scale below the readable size. Below it anyway: a warning.
  The readable size for math is lint's: the 75th percentile of glyph heights vs the cap height of
  `readable_size()`.
- **Errors.** `brace_problem` / unclosed or empty `{{ }}` / parts not in any step / `match` not in
  both steps → params errors (`vidgen validate`). LaTeX errors → `VidgenError` "step N does not
  compile: <TeX message> (at: <context>)" read from the `.log` Manim names
  (`tex_error_excerpt`, dvisvgm markers removed).
- **Targets**: `title`, `step<N>`, `note<N>` (entrance plays the step), `result` (last step + box;
  entrance: the step, or just the box), `term:<tex>` (parts of `terms`, `colors`, `match`, `{{ }}`).
  A `transform` jump to the last step leaves the result's box to the last step's own beat.


## 37. Refinements (Step 34, `screenshot` and callouts)

- **Callout helpers** (`vidgen/callouts.py`, exported by `vidgen.api`; reused by Step 41's callout
  overlay). An *area* is a mobject (its bounding box), a `Region`, or `[x, y]` / `[x, y, w, h]`
  (top-left corner + size, y downwards) relative to `within` (mobject or region; default the
  frame) in fractions or, `units="px"`, pixels of an `ImageMobject`'s `pixel_array` (or of
  `pixels=(w, h)`); `callout_area` turns any of them into a `Region` (a point has size 0). The
  helpers `callout_box`, `callout_circle`, `callout_arrow`, `callout_magnifier` (needs `image=`),
  `callout_spotlight` share the signature `(area, label="", *, within, units, color, label_size,
  side, bounds, avoid, scale, theme, ...)`; `callout(kind, area, label, **options)` dispatches by
  name (`CALLOUT_KINDS`). Names carry the `callout_` prefix like the `chart_*` helpers: bare `box`,
  `circle`, `arrow` would shadow common local names in `from vidgen.api import *` code.
- **`Callout(Group)`**: `kind`, `area` (Region), `mark`, `tag` (label or `None`), `steps` (parts in
  drawing order: a magnifier's source frame, connector lines, inset); `extent(pad)` (mark + tag; a
  spotlight only by its hole and tag) feeds the next callout's `avoid`; `draw(start=0)` returns
  one animation per part with staggered rate functions inside a single run time (no
  `AnimationGroup`, which would leave its own `Group` in `scene.mobjects`): mark then tag, an
  arrow's label before its `GrowArrow`; `start` delays them (while earlier callouts leave).
- **Labels** (`callout_label`): `readable_text` (bold, `label_size`, never below the readable
  size; wrapped at 0.3 x frame width, 0.6 in portrait) on a `RoundedRectangle` plate filled with
  the callout colour; the text colour is `text_color_on(plate)` (≥ 4.5:1, lint's contrast); the
  plate is drawn first, so lint reads it as the text's backdrop.
- **Placement** (`label_spot`, `tag_spot`): candidates in eight directions (arrows, insets) at
  several gaps, or on a mark's edge (tags: above at its left / right end, below, beside; inside
  its top-left corner as a last resort); each is moved inside `bounds` and scored by overlap with
  the anchor (x10), with `avoid` (x4), the shift, a preference order, being nearer than 0.7 x the
  first gap (x6: arrows keep a visible length) and overlap with `prefer_off` (x0.8: the
  screenshot's picture, so labels and insets go to free background when there is room).
- **Arrow**: straight `Arrow` (tip 0.22) or `CurvedArrow` (±45°, bulging towards the bounds'
  centre), from the label plate's edge to where the ray from the area's centre leaves it (a
  point: the point). **Circle**: an ellipse through the area's corners (x√2 + padding; flat
  areas get a minimum height). **Spotlight**: `Cutout(rectangle, rounded hole)` filled with the
  theme background at 0.62 over `cover`/`within`. **Magnifier**: the inset size is `zoom` x the
  area, limited by the room above / below (full bounds width) or beside (full height) the area,
  whichever allows more (that axis is then the only one tried); the pixels are cut from the
  image's `pixel_array` (or `source`) by the area's fractions and resampled (Lanczos) to the
  output resolution / `scale`; connectors are the convex-hull edges joining a corner of the
  source frame to a corner of the inset (`connector_lines`).
- **`screenshot`** (`scenes/screenshot.py`; reference docs/CONFIG.md). Params `path`, `title`,
  `steps` (`ScreenshotStep {callouts, focus, previous}`, a list of callouts or one callout;
  `CalloutSpec {kind, area, label, color, side, curved, zoom}` or the shorthand `{KIND: area,
  ...}`; JSON Schema `anyOf` for both), `frame` (`none | browser | window | phone`), `url`, `units`
  (`fraction | px`), `color`, `label_size`, `previous` (`fade | dim | keep`), `focus_scale`.
  Fractions are checked by the params model, pixels by `validate_project` (image size).
- **Layout**: the picture (and its frame: bar 0.065 x width, 0.4–0.6 units, taller for a
  readable `url`; phone bezels 5 % / 12 % / 10 % of the width) is fitted into the body (below the
  title) inset by 0.25 x 0.1 units in landscape, 10 % of the height in portrait. Labels' bounds are
  the body; the title bar is in every step's `avoid`.
- **Steps**: per-beat data is the params list aligned with beats, like Steps 32/33. Beat 1 plays
  the picture's entrance then step 1 (`play_steps` with two slots); `fraction=0.6, cap=1.5`. A
  step = earlier callouts leave (fade, or `dim`: box / circle / arrow / magnifier source frame to
  0.35 opacity, the rest fades) + the camera move + its callouts' `draw(start=0.4)`. Callouts are
  built once, before the first beat, step by step with `avoid` = title bar + kept callouts + the
  step's areas + the callouts placed so far; spotlights first (z-index 1, other callouts 2).
- **Focus**: the camera (`MoveCamera`) frames the union of the step's areas so it takes at most
  half of the view each way (≤ `focus_scale` / the step's number); the step's callouts are built
  with `scale = 1 / magnification` and `bounds` = the zoomed view's safe area (∩ body), so they
  read at normal size. Callouts built for another camera always leave when it changes (kept
  ones would be enlarged or tiny).
- **Targets**: `title`, `image` (picture + frame), `callout<N>` / `callout:<label>` (numbered in
  written order; entrance: `draw()`, or the step for a focus step not yet zoomed), `step<N>`
  (entrance: the step). A step whose callouts are all on screen (an early `reveal`) is skipped.

## 38. Refinements (Step 35, `video_clip`)

- **Approach: frames decoded inside Manim, not composited by ffmpeg afterwards.** Compositing a
  clip into the rendered scene with ffmpeg would be faster, but stills (§13), the layout dump
  (§15), lint (§16, §17), callouts, camera moves and beat actions would never see it. Instead the
  clip is a mobject drawn by the camera on every frame, so everything that works on an image works
  on a clip. Cost: a full-bleed 854x480 preview renders at ~0.6 s per second of video (Manim's
  image drawing and encoding dominate; decoding and scaling a frame takes ~2 ms).
- **`ClipMobject(ImageMobject)`** (`vidgen/clips.py`, exported by `vidgen.api`). Its picture is the
  frame at the scene's clock: `play(scene, at=None)` ties a shared `_Playback` (reader, timing,
  crop, decode size, clock) to `scene.renderer.time`; `get_pixel_array()` (what the camera draws)
  asks the reader for the frame at `timing.source_time(now - start)`. A time-based no-op updater
  makes Manim treat it as moving (redrawn every frame; waits are not frozen), so it plays through
  `play` and `wait` alike. `Mobject.copy` (deepcopy) shares the playback (`_Playback.__deepcopy__`
  returns itself), so the copies `FadeIn` / `Transform` make show the same moving picture.
- **Modulation.** Manim's animations and vidgen's `dim` / `highlight` actions change an image's
  `pixel_array`. For a clip that array is a 1 x 2 *modulation* — a black and a white RGBA pixel —
  and every frame is mapped through it affinely (`out = black + frame * (white - black) / 255`,
  all four channels). Interpolations (`FadeIn`), alpha scaling (`dim`, `set_opacity`) and tints
  (`highlight`: `p (1 - t) + c t`) are affine per pixel, so they act on the moving picture exactly
  as on a still. The composed frame is cached per (reader, frame serial, modulation).
- **Decoding** (`ClipReader`): PyAV, sequential; the frame showing at `t` is the last whose time
  is ≤ `t` + 2 ms (container time stamps are rounded, WebM to 1 ms); going back (a loop) or more
  than 2 s ahead seeks to the key frame before `t`. Only the current frame (and its converted
  picture) is held. Conversion is FFmpeg's scaler (`VideoFrame.to_ndarray(width, height,
  format="rgba")`) to the decode size of the whole picture, then the crop is sliced out.
  `set_resolution(scale)` sets the decode size: the size shown × `scale` (focus / zoom), as far as
  the clip has pixels inside the crop, and never less than the size shown — so at magnification 1
  the decoded frame has exactly the on-screen size and the camera copies it pixel for pixel:
  `resampling_algorithm` is a property returning `NEAREST` then (PIL perspective transform ~3 ms
  vs ~50 ms bicubic at 854x480), else `BILINEAR`.
- **Timing** (`ClipTiming(start, end, speed, loop)`): `source_time(played) = start + played ×
  speed`, modulo the span with `loop` (played time rounded to µs, so frame times summed from
  1/fps wrap exactly), clamped to `end - 5 ms` (`END_GAP`) otherwise — the frame at `end` is never
  shown, the last one before it holds. `fit_speed(span, window, low, high)` clamps
  `span / window`. In the scene the clip starts at scene time 0 (it fades in playing); the window
  is the narration (Σ beat `d + pad`) or a silent scene's `duration - outro`; `fit_duration`
  speeds one pass to the window within `fit_range`. The scene's length is never changed by the
  clip (the §5 contract): a longer clip is cut by the fade-out (log info), a shorter one holds its
  last frame (warning above 2 s; `dead_air` above 6 s) unless it loops.
- **Sound** (`clip_audio`): one ffmpeg call writes the clip's sound as it plays — `atrim` to the
  span, 48 kHz stereo, an `atempo` chain for the speed (each factor 0.5–2; pitch kept), padded /
  cut to exactly one pass in samples (so loops stay in step with the picture), `volume`, `aloop`
  when looping, `apad` + `atrim` to the scene's length, `afade` over the outro — into a temporary
  WAV that `NarratedScene.add_sound` mixes at scene time 0 (Manim's pydub mix: sounds are summed;
  narration MP3s are added at their beats). The pipeline pads that mix to the video length as for
  any scene (§5.2, Step 4). Default volume 0.25 under narration, 1 in a silent scene; no ducking
  (Step 45). `--no-audio` renders skip it.
- **`video_clip`** (`scenes/video_clip.py`, a subclass of `screenshot`'s scene class: steps,
  callouts, focus, `previous`, frames and targets are shared; `screenshot` gained `picture_name`,
  `_spec_area()` (an area and its units), `_layout(body, fill=)` (cover: the picture takes the
  room's aspect) and `_picture_entrance()` for it). Params add `caption`, `caption_size`,
  `caption_color`, `region` (`body | full | hero | left | right | top | bottom | center | bleed`),
  `fit`, `trim`, `speed`, `fit_duration`, `fit_range`, `loop`, `volume`, `mute`; `magnifier`
  callouts are rejected (a still inset of a moving picture), `frame` with `bleed` too. Callout
  areas are written on the clip's whole picture and moved into the `cover` crop (warning when
  outside it). `bleed` puts title and caption on `surface` plates (z-index 3, over callouts).
- **Targets**: `title`, `clip`, `caption`, `callout<N>`, `callout:<label>`, `step<N>`.
- Known limits: rotation metadata is ignored; variable-frame-rate files show the frame whose
  time stamp precedes the scene time (correct, but uneven if the file is); a file without a
  stated length is measured from its packets.

## 39. Refinements (Step 36, `map`)

- **Data** (`src/vidgen/data/geo/world-110m.json`, 132 KB, package data). Natural Earth 1:110m
  Cultural Vectors, Admin 0 – Countries (public domain), via the npm package `world-atlas` 2.0.2
  (`countries-110m.json`, TopoJSON, ISC) whose ids are ISO 3166-1 numeric codes; alpha-2 /
  alpha-3 codes and English names / aliases from `i18n-iso-countries` 7.14.0 (MIT).
  `tools/make_world_map.py` (maintainer script, `npm pack` of both pinned versions, or
  `--world-atlas DIR --iso DIR`) decodes the topology (delta-encoded quantized arcs), cuts rings
  that cross the antimeridian at ±180° (d3's spherical topology has jumps there; a ring round
  the pole — Antarctica — is closed along its edge), orients outer rings counter-clockwise and
  holes clockwise (so Cairo's non-zero fill leaves Lesotho open in South Africa), rounds to
  hundredths of a degree (flattened integer rings), and computes per country a label point (pole
  of inaccessibility of the largest part by a two-pass grid search) and a "main" box (parts within
  15° of the largest: France without French Guiana). Countries without an ISO code get
  `XK`/`XKX` (Kosovo) or Natural Earth's ADM0_A3 (`CYN`, `SOL`). ISO countries missing at this
  scale are listed in `small` for an explicit error. Output is deterministic.
- **Lookup** (`find_country`): one index of normalised names (NFKD without accents, casefolded,
  punctuation and a leading "the" dropped; `&` = and), claimed in priority order — codes, display
  names, then aliases (Natural Earth's short name, a curated list such as `UK`, `Holland`, `DRC`,
  then i18n-iso-countries' names) — so an ambiguous alias (`Congo`) goes to Natural Earth's
  meaning. Unknown names get `difflib` suggestions; small countries a "use a pin" message.
- **Projection**: Equal Earth (Šavrič, Patterson & Jenny 2018; equal-area, pure numpy) centred on
  the view's middle longitude. `MapView(box, area, antarctica, expand)`: projects the box's
  sampled edges, grows the projected rectangle to `area`'s aspect ratio (more map, within the
  world's outline; the world view without Antarctica is cut at 58° S), fits it inside `area`
  (`region`), and maps points with one scale. Polygons are projected once per centre longitude
  (`lru_cache`; each polygon moved by ±360° to be nearest the centre, which makes views over the
  date line work), then clipped to the view rectangle (Sutherland–Hodgman, numpy per edge).
  World view: ~280 polygons in ~25 ms; cached views ~6 ms. `cropped`: the view cuts the world at
  its sides (a regional view).
- **`map`** (`scenes/world_map.py`). Stages: stage 0 = the top-level `countries` / `pins` /
  `arcs` (with the map), stage *i* = `steps[i-1]`; steps follow `screenshot`: step *i* at beat
  *i* via `distribute`, beat 1 = intro (title, map sweep, legend, caption, stage 0) + step 1,
  `play_steps(fraction=0.6, cap=1.6)`. **Layout**: title (`chart_title`), caption
  (`chart_caption`), legend (`color_bar`, horizontal, ≤ 0.6 x body width) centred under the map,
  map and legend centred together in the body; a cropped view gets a panel (`surface` fill = sea,
  thin `dim` frame) under the countries. Countries are one `VMobject` each (rings as closed
  straight-segment subpaths built with numpy), land = `land_color` mixed 0.3 over the background
  (0.18 for countries without a value on a choropleth), borders 0.8 wide in the background colour.
  **Highlights** are copies over the base shape (fill + 1.6x border; on a choropleth an outline
  of 3.5) so a highlight can be revealed, dimmed or zoomed as its own target. **Labels** are text
  on background-coloured plates (opacity 0.88; lint reads the plate as the backdrop): a country's
  goes on its label point when it fits in 90 % of its main box and is free, else beside it via
  `label_spot` with a leader (z 3.5, under every plate); pins' labels go beside the pin (leader
  when pushed away), arcs' at the top of the arc; all avoid earlier labels and every pin of the
  same view. **Arcs**: `ArcBetweenPoints` bending 72° upwards (flipped when its top would leave
  the map), trimmed 0.13 units at pin ends, arrow tip; `Create` grows them. **Focus**: as
  `screenshot` — camera on the step's items (country main boxes clipped to the map, pins, arc
  ends) at most `focus_scale` / 0.6 of the frame, the step's labels, pins and strokes built at
  1 / magnification; labels built for another camera fade when the camera moves. Animations:
  the map sweeps west to east (each country's `FadeIn` windowed by its x), highlights fade in,
  pins drop in, arcs grow, labels follow (`window` rates).
- **Targets**: `title`, `map` (panel + countries), `legend`, `country:<a3>` / `country:<a2>` /
  `country:<name>` (one target: a highlight with its label and leader, or a valued country's
  shape), `pin<N>` / `pin:<label>`, `arc<N>`, `step<N>`. Only countries the params name have
  targets, so `target_names` stays short and static.
- Known limits: arcs are drawn on the flat map, not as great circles, and do not wrap; no
  bundled city list (pins take coordinates or a country); 1:110m drops small states; no
  graticule; a `world` view in 9:16 is a narrow strip (documented).

## 40. Refinements (Step 37, review 2)

- **Examples split**: `examples/minimal` keeps the core built-ins (title, bullets, icon_grid,
  bar/line charts, image, quote, equation, code, text_card, end_card) and the beat-action
  examples; `examples/gallery` uses every type added in Steps 25–36 once (three `chapter`
  dividers group them). Their assets moved with them (`app.png`, `clip.webm`, `train.py`; the
  maintainer scripts `tools/make_screenshot.py` / `make_clip.py` write there). A test checks
  that the two examples together use every built-in type (`flowchart` = `diagram`).
- **Header synonyms** (`SceneParams.header_synonyms`, default on; `HEADER_SYNONYMS` in
  `vidgen.scene`): a `Params` model with only one of `heading` / `title` (and of the `_size`,
  `_color` pairs) also accepts the other name, via a pydantic `AliasChoices` set in
  `__pydantic_init_subclass__` (inherited models keep it). `title`, `chapter`, `end_card` opt out
  (their `title` is the main text). Giving both names is an error (`'title' is another name for
  'heading', which is given too; keep one`). `vidgen schema` adds the other name as a property
  with the field's schema and a `not: {anyOf: [{required: [a, b]}]}`; `list-scenes` prints
  `(also: title)` and its JSON fields gain `aliases` (list; added within version 1). Target
  names: `actions.TARGET_SYNONYMS` — `title` selects a `heading` target when the scene has no
  `title`, and the reverse (`match_names` over a scene's whole name list; `find_targets` uses
  it too).
- **Unknown keys**: `config.validation_problems(error, prefix, model=None, noun="parameter")`
  rewrites pydantic's "Extra inputs are not permitted" with `describe.unknown_key_message`:
  `unknown parameter 'dim_prev'; did you mean 'dim_previous'? (known: ...)` (16 names shown),
  resolving nested models along the error location (list indexes and union tags skipped).
  Used for scene params (`validate`, `parse_params`), action options (`noun="option"`) and the
  top-level config (`noun="key"`).
- **`one_or_many(item)`** (`vidgen.api`): `Annotated[list[item] | item, AfterValidator]`, the
  value always a list. `highlight` of `diagram`, `heatmap`, `histogram`, `network`, `scatter`
  use it (a single item was an error).
- **Text on fills** (`Target.on_fill`, `NarratedScene.target(..., on_fill=)`): `(text, shape)`
  pairs. `dim_to` recolours such text with `text_color_on(shape colour mixed over the background
  at its dimmed opacity)` and keeps it at `TEXT_ON_FILL_DIM` (0.7) instead of fading it with the
  shape; `highlight` `color` / `flash` give it `text_color_on(highlight colour)` while the shape
  is painted; `fill` gives it the colour that reads on the plate-tinted shape. Registered by
  `pie` (labels inside their slice), `heatmap` (values; rows, columns, cells) and
  `screenshot` / `video_clip` (callout labels on their plates). `pie` and `heatmap` highlight
  steps use `dim_to` for their texts too (the module helper `pie.recolor` is gone). Undo:
  `Dim.revert` restores the colours of the recoloured text; `Highlight.revert` after `fill`
  likewise.
- **Scene dimming survives `until`** (`Target.scene_dim`): `dim_to(..., own=True)` (scenes)
  records the factor; `Dim` (the action) passes `own=False`, and its revert caps the restored
  opacity at `rest x scene_dim` (`_Memory.restore(cap=)`).
- **Decorations follow** (`scenes/actions._follow`): highlight boxes, underlines and fill plates
  get an updater that keeps their offset to the outline (not time-based: waits stay frozen
  frames) and scales their opacity with the anchor's (0 while it is off screen); an outline the
  scene never draws (table / comparison guide rectangles) is followed but never faded. Undo
  clears the updaters before fading them out.
- **Copy-free fades** (`helpers.Fade`, `helpers.fade_out`, in `vidgen.api`): Manim's
  `FadeIn`/`FadeOut` and every `Animation.begin` copy the mobject (`create_starting_mobject`);
  for a 57-line `code_walkthrough` that was 33 of 59 s of a preview render. `Fade` animates fill /
  stroke arrays (and a shift) of the family's `VMobject`s and returns no starting copy;
  `clear_all` (every scene's outro) uses `fade_out` (`Fade` for vector-only families, Manim's
  `FadeOut` with images/clips). `Repaint` (dim / highlight) skips the starting copy too. The
  walkthrough: 59 → 27 s (profiled, preview).
- **Portrait growth**: `comparison` points, column headings and verdict x `portrait_growth`
  (1.3, as `bullets`); `icon_grid` labels x 1.3 in portrait (reduced as before when they do not
  fit); `timeline.vertical_growth` 1.5 and `process.column_growth` 1.5 (tried, then the halfway
  factor, then the old 1.2 rule; never more wrapped lines). 16:9 unchanged.
- **9:16 world map** (`WorldMap._portrait_world`): a `world` (or `auto` → world) view in a
  portrait frame keeps the longitudes of the items (+12 % each side, at least 140°; unchanged
  past 300°) and every latitude, so the map is a regional panel instead of a strip.
- **Layout dump `rotation`** (`introspect._glyph_heights`): for a one-line text (≥ 4 glyphs)
  the principal axis of the glyph centres gives its angle; ≥ 8° counts as rotated and glyph
  heights are measured along the normal, so `font_px` (and lint `min_font`) no longer measure a
  rotated label sideways. New key `rotation` (degrees, 0 when level / several lines / math);
  `LAYOUT_VERSION` stays 1 (additive). kphi3's `lint_ignore` for its rotated label is gone.
- **`table` widths**: one-line widths are measured once per text at `measure_size` (40 pt) and
  scaled (linear in the size): a 24-row table's fitting took 85 s, 26 s now.
- **`list-icons --sheet PNG --theme [PRESET]`** (`iconlist.SheetColors`): the sheet in the
  project's theme (no value) or a preset's: background, icons in `primary`, names in `text`,
  categories in `dim`.
- **Warnings for too much content** read alike: `the <thing>'s N <items> do(es) not fit this
  frame at the readable size; <remedy>` (`heatmap` and `comparison` reworded).
- **Header bands alike**: `table`, `code`, `code_walkthrough`, `equation_derivation`,
  `screenshot` and `video_clip` (framed) build their title with `chart_title` (1.3x in portrait,
  balanced lines) like the charts and the `heading` scenes; their 9:16 titles were ~1.3x
  smaller than the others'. A `table` caption follows a short table (`Table._tuck`: at most
  `caption_gap` 0.45 under it, both centred in their space) instead of standing at the frame's
  bottom.
- **Test markers**: `slow` now also marks the parametrized render sweeps (every scene type x
  orientation, every target, every preset) and every test function over ~1.5 s, so `pytest -m
  "not slow"` stays a quick check (~1.7 min on a 2-CPU box, 1257 tests) while the full suite
  (~14 min) runs everything.

## 41. Refinements (Step 38, overlays: framework, `lower_third`, `watermark`)

- **Config.** `VideoConfig.overlays: list[OverlayConfig]` (`config.OverlayConfig`, `extra="allow"`
  like actions): `type`, `id` (default the type; `<type><n>` (1-based) when several id-less entries
  share a type), `scenes` (`all` | ids), `exclude`, `from` / `to` (field `from_`, alias `from`:
  seconds in the video, or a scene id = its start / its end), `reserve`; every other key is an
  option of the type (`OverlayConfig.options`). `SceneConfig.overlays: bool | {id: bool |
  mapping}` (default `true`): `false` = none on the scene; per id `false`, or a mapping of option
  overrides (+ `reserve`; the other common keys are an error); a mapping with `type` under an id
  that is no video-level id = an overlay of that scene only (no `scenes`/`exclude`/`from`/`to`).
  Reference: docs/CONFIG.md "Overlays".
- **Registry.** A third kind next to scene types and actions (`registry.OverlayType`,
  `register_overlay`, decorator `overlay(name, *, override=False)`, `find_overlay`,
  `overlay_names`, `all_overlays`, `unknown_overlay_message`; same two layers and collision rules;
  `Snapshot` is now a triple). `overlays.check_overlay_class`: `Options` an `OverlayOptions`, no
  option named like a common key, `build` implemented, `layer` an int. Built-ins in
  `scenes/overlays.py` (only `from vidgen.api import *` + `.image` helpers).
- **`Overlay`** (one instance per scene render): `options`, `config`, `context`, `id`, `scenes`
  (ids it is drawn on), `span` (`from`/`to` in video seconds, `inf` without an end). Subclass
  API: `build()` (full look, placed on the whole frame, once per render), `window()` (video
  seconds or `None`), `state(t)` (hashable or `None`; **a pure function of video time**, so the
  look is identical on both sides of a cut), `pose(mobject, state)` (a copy), `settled(state)`
  (full look, for lint), classmethod `validate_project(options, project, scenes)`, class
  attributes `layer`, `lint_skip`; helpers `interval()`, `transition(t, start, end, enter, exit)`
  (smooth 0..1), property `timed` (span bounded or a window; a subclass sets `timed = True` when
  `state` reads the video time otherwise, e.g. Step 39's progress bar). `with_opacity(mob, f)`
  (exported) scales fill / stroke / image alpha of a copy.
- **Timeline contract** (`vidgen/videoplan.py`, `VideoPlan(project, fps)`, lazy and cached): each
  scene renders alone, so its position in the video is planned: a beat lasts `round((d + pad) x
  fps)` frames, `d` = the MP3's decoded length (`scene.audio_duration`, cached by path + size +
  mtime) else the word estimate; a narrated scene = its beats + `ceil(outro x fps)` (the type's
  class attribute `outro`); a silent one `max(round(duration x fps), round((duration - outro) x
  fps) + ceil(outro x fps))`. `SceneSlot(index, id, type, start, duration, beats: BeatSlot(id,
  start, end, text), chapter)`, `Chapter(title, number, scene, start)` from `chapter` scenes
  (Steps 39/49), `scene_start`, `duration`, `resolve(value, end)`. Built-in scenes match it exactly
  (tested: every frame count equal, half-frame durations aside). Overrunning scenes / extensions
  with their own timing shift later scenes: the worker records `render.overlays = {ids, timed,
  start, duration}` in the scene's timings, and `join_scenes` warns when a scene with timed
  overlays starts more than 1.5 frames away from its planned start. Only timed overlays make the
  layer read the plan (reading every MP3 before the scene).
- **Fingerprint.** With any overlay, `_overlay_inputs`: per scene id, type, duration, chapter
  title, `overlays`, beats' ids, texts and MP3 stats (what the plan reads), so editing another
  scene's narration re-renders scenes with overlays; projects without overlays are unaffected
  (the key is `null`).
- **Drawing: composited in the renderer, not mobjects of the scene.** `OverlayLayer` wraps
  `renderer.add_frame` *after* `FrameCapture` attached (outermost), so stills, the layout dump and
  the motion signal see the composited frames, and nothing in `scene.mobjects` changes: the
  `MovingCamera` (zoom, focus) and `clear_all`/outro fades never touch overlays; they never change
  timing or frame counts (tested against renders without them). Frame `k` is drawn at video time
  `start + k / fps`. A frozen wait (one frame written N times) is split into runs of equal states
  (a lower third sliding in during a silent card is drawn frame by frame; static overlays cost one
  call). Why not an updater following `camera.frame`: it would make every wait non-frozen (each
  frame redrawn), add the overlay to `scene.mobjects` (clear_all, scene walks, targets) and have to
  undo scaling for a zoom; why not ffmpeg afterwards: stills, layout and lint would not see it.
- **Patches.** Each distinct tuple of states is drawn once (LRU of 64) with two Manim `Camera`s
  showing the whole frame over black and over white: Cairo draws premultiplied while Manim
  composites images with PIL in straight alpha, so a single transparent camera gives wrong
  colours where they mix; the two opaque renders give exact premultiplied colour (`on_black`) and
  `255 - alpha` (`on_white - on_black`) for both. The patch is cropped to its visible box;
  compositing a frame is `colour + under x (255 - alpha) / 255` on that box (uint16) — within 2
  levels of Cairo drawing directly on the frame (tested).
- **Layout dump.** `LayoutRecorder` appends the overlays shown at the still (`layer.posed(frame)`),
  measured with the layer's whole-frame camera (`_Walk.camera`), after every scene object (`order`
  + 1000), paths `overlay:<id>/...`, key `overlay` (the id); frames gain `overlays: [{id, type,
  settled, skip}]`. `safe_area` is now `scene.safe_area` (equal unless reserved).
- **Reserved space.** `reserve: true` → `NarratedScene._reserved` (the built mobject's box) and
  `safe_area` = the margins' safe area cut by `overlays.avoid(area, box, gap=0.2)` (the largest of
  the four parts above / below / left / right of the box). Static for the whole scene (a layout
  is built once), so a lower third with `reserve` shrinks the scene also while it is not shown.
  The global `regions.safe_area()` is unchanged (built-ins lay out in `self.safe_area`).
- **Lint.** `overlay_overlap` (layout rule after `max_words`, default warning, `min_overlap` 0.05
  of the scene object's box): an overlay's union box over a scene text/code/math/number/icon.
  `safe_area` skips overlay objects; `text_overlap` skips overlay-vs-scene pairs; `covered_text`
  skips an overlay shape over scene text (all `overlay_overlap`'s). The runner drops objects of
  overlays not `settled` (sliding / fading at a beat end, like mid-beat stills) and, per rule,
  objects of overlays whose type's `lint_skip` names it (`watermark`: `contrast`).
- **Validation** (`overlays.overlay_problems`, in `cli.project_problems` and
  `pipeline._check_scenes` via `check_overlays`): unknown types (did-you-mean), duplicate ids,
  unknown scene ids in `scenes`/`exclude`/`from`/`to`, numeric `to <= from`, misplaced keys in scene
  overrides / scene-only overlays, unknown override ids; options as written (at `overlays[i]`)
  and with each scene's overrides (new problems at `scenes[j].overlays.<id>`), theme tokens
  checked; the type's `validate_project`. `scene_overlays(project, spec, theme, plan)` builds the
  scene's instances (sorted by `layer`), skipping timed ones whose interval misses the scene.
- **Listing / schema.** `list-scenes` prints an `overlays` section; `--json` adds `overlays:
  [{name, origin, builtin, overrides_builtin, doc, layer, lint_skip, options}]` (within version
  1). `vidgen schema`: `OverlayConfig.type` an `enum`, per type `if`/`then` with its options and
  `additionalProperties: false` (`overlay.NAME` defs); scene overrides only by shape.
- **`lower_third`**: name (bold, heading role) and optional title / icon on a `surface` plate
  (0.92) with an accent bar, wrapped at the readable size within `max_width` (0.6 of the safe
  width; 9:16 the whole width), placed with `place(..., align)` in the safe area (9:16: raised by
  `PORTRAIT_LIFT` 0.12 of the safe height). Window: its scene's planned start + `at` (seconds or a
  beat's start) for `duration`, cut at that scene's end unless `across_cuts`. State: the eased
  progress (3 decimals); pose: opacity x p, shifted `SLIDE` 0.5 x (1 - p) from its side (from
  below / above when centred).
- **`watermark`**: one of `image` (`image.load_image`, height `size` x the shorter side, at most
  0.3 of the frame wide), `icon`, `text`; `opacity` applied at build; placed `inset` (0.025 of the
  shorter side) from the frame's corner; `fade` at a bounded `from` / `to`. `lint_skip =
  ("contrast",)`.
- **For Steps 39–41.** A progress bar: `timed = True`, `state` from `t / context.duration`
  (quantised to a pixel); a chapter indicator: `context.chapters` / `context.scene.chapter`;
  captions: `context.scene.beats` (planned scene times and texts; karaoke word times can be spread
  in a beat's `[start, end]`). Callouts on any scene (Step 41) need scene targets, i.e. scene-level
  actions rather than overlays.
- Known limits: the plan cannot see what a scene's code does beyond the contract (warning at
  join); `reserve` is per scene, not per moment; overlays are drawn at the render's resolution
  from vector / image mobjects (no video overlays).

## 42. Refinements (Step 39, chapters, `progress_bar`, `chapter_indicator`)

- **Chapters** (`vidgen/chapters.py`, config only): a chapter starts at a `chapter` scene
  (`params.title`, `params.number`) and at any scene with **`SceneConfig.chapter`**: a string
  (the title) or `ChapterConfig {title, number?}` (`number` int or non-empty text). On a
  `chapter` scene the field renames the chapter in lists/indicators and keeps the card's number
  unless it gives one. `chapter_marks(scenes) -> [ChapterMark(title, number: str | None, scene,
  scene_index, card)]`. `chapter_problems(scenes)` runs in `VideoConfig`'s validator (so `parse_config`,
  `validate` and every command reject them): the same (title casefolded, number) twice; integer
  numbers not strictly increasing (text numbers and repeated chapters are skipped); a non-card
  mark right after a chapter card (the card would be a chapter of its own). Two cards in a row
  are allowed (two chapters).
- **Planned chapters** (`VideoPlan.chapters`): `Chapter(title, number, scene, start, end, index,
  count, card)` (+ `label` = number or index, `duration`); a chapter ends where the next starts,
  the last at the planned video end. `chapter_of(scene_id)`, `chapter_at(t)`; `SceneSlot.chapter`
  stays the title (now also from `chapter:` fields). **Public**: `vidgen.api.video_chapters(project,
  fps=None)` (default the final format's fps) and `Chapter` — what Step 49 (MP4 chapter metadata,
  YouTube list) reads; Step 49 adds the "Intro" chapter at 0:00 YouTube needs when the first
  chapter starts later (`video_chapters(..., intro=True)`, published lists only, §52).
  `OverlayContext.chapters` (all), `.chapter` (the scene's).
- **Fingerprint**: a scene's own `chapter:` is excluded from its dump (no pixels depend on it
  without overlays); `_overlay_inputs` carries every scene's `chapter` and a card's `number`.
- **`Overlay.shown_in(start, end)`** (default `True`, asked of timed overlays for the scene's
  slot ∩ interval): `False` drops the overlay from that scene's render, so it neither draws nor
  **reserves** there. This is the cheap part of the Step 38 "reserve is per scene" gap; an
  overlay shown during part of a scene still reserves for the whole scene (a layout is built
  once; documented in CONFIG.md `reserve`).
- **Reserved space respected by chart titles**: built-ins called `chart_title(...)` without
  `area`, i.e. in the global safe area, so a `reserve`d overlay at the top did not move their
  header (seen in 9:16 with two-line titles); every built-in now passes `area=self.safe_area`.
- **Drawing per overlay with cropped cameras** (`OverlayLayer`): patches are cached per
  `(overlay, state)` (LRU 64 per overlay) instead of per combination of states, and each is drawn
  by two cameras (black / white) cropped to the posed mobject's pixel box (points' box + strokes
  + 3 px, clamped to the frame; same pixels-per-unit and an integer pixel offset, so Cairo and
  image drawing match the whole-frame result — tested within 2 levels). A progress bar changing
  every few frames costs a strip, not two 1080p captures plus a redraw of every other overlay.
  Compositing blends the shown patches in layer order (the over operator; equal to drawing them
  together up to rounding).
- **`progress_bar`** (`scenes/progress.py`, `timed = True`): track segments (`track_color`
  `dim` at 0.35) and played segments (`color` `primary`) along the top/bottom edge, `thickness`
  0.006 of the shorter side (≥ 2 px), `inset` 0 (flush; outside the safe area, so no reserve
  needed); with `chapters`, gaps of max(2 x thickness, 3 px) at every chapter start inside the
  video. State: the number of played pixel columns, `round(t / duration x width_px)` — a pure
  function of video time, quantised to a pixel (one patch per column, ≤ width states per video).
  The fraction is of the whole planned video even with `from` / `to` / `exclude`.
- **`chapter_indicator`** (`timed = True`): one `MarkupText` label per chapter (number bold in
  `number_color`, separator and title in `color`; `total` → "index/count"; `number: false` →
  title only), at least the readable size, shortened word by word with "…" to `max_width` (0.4
  of the frame width; 9:16 min(2x, 0.85)), optional rounded plate (`background`), `opacity`
  0.85, placed `inset` from the `corner`. `build()` returns all labels (so `reserve` keeps clear
  of the widest); `pose` shows one or two. **Runs**: the scenes it is drawn on that have a
  chapter, minus chapter cards (unless `on_chapter_cards`), consecutive scenes of one chapter
  merged; runs touching another run (a `chapter:` field change, no card) cross-fade over `fade`
  centred on the cut; free ends fade in/out over `fade` inside the run. State: `((chapter
  position, opacity 2 decimals), ...)`; settled = one label at full opacity. `shown_in` is false on
  cards and before the first chapter, so those scenes get no reserve.
- **Example**: `examples/gallery` has a top `progress_bar` (3 chapter segments) and a top-left
  `chapter_indicator` with `reserve: true`; lint 0 findings in all 8 variants.

## 43. Refinements (Step 40, burned-in captions)

- **Word times** (`vidgen/speech.py`, render input; `spoken_words`, `speech_bounds`,
  `SILENCE_DB` moved here from `lint/timing_rules.py`, which re-imports them). `WordTime(text,
  start, end)`. `beat_word_times(audio_dir, beat_id, text, start, end)`: (1) a stored alignment
  that belongs to the beat's current MP3 and text; (2) else `estimate_word_times` within the MP3's
  speech (`speech_bounds`: leading / trailing silence below -40 dB of the peak cut, as lint's
  `narration_speed`); (3) else the estimate over `start..end` (no audio: the word-count `d`). The
  estimate gives each word `syllables(word) + 0.05 x letters` (vowel groups, a silent final `e`
  dropped; acronyms a syllable per letter; numbers 2 per spoken word) and a pause after it of 2
  syllables at a sentence end, 1 at a comma / semicolon / colon / dash, scaled to fill the span.
- **Alignment seam.** `voice.timestamps` (default `false`, not hashed: the audio is the same)
  makes `vidgen tts` call `provider.synthesize_timed(text, previous, next) -> (audio,
  alignment | None)` when the provider has it; ElevenLabs implements it with
  `POST /v1/text-to-speech/{voice}/with-timestamps` (JSON: `audio_base64`, `alignment {characters,
  character_start_times_seconds, character_end_times_seconds}`; the non-normalised alignment, whose
  characters are the text sent). `write_alignment` stores `<audio_dir>/<beat>.align.json`
  `{version: 1, text, audio_sha1, characters, starts, ends}` after the MP3 and before the hash; a
  beat generated without timings removes an old one; a variant copying base audio copies its
  alignment. `read_alignment` accepts it only for the same text and MP3 bytes (sha1), so a stale
  file is ignored, never wrong. Words map to characters by position (`\S+` runs of the text, or of
  its whitespace-normalised form). Tests mock urlopen; the real endpoint was never called.
- **Cue cutting** (`vidgen/cues.py`, shared by SRT and captions). `segment_cues(words, widths,
  space, max_width, max_lines, max_words)`: dynamic programming over cue ends; a cue's best line
  split is found by trying every split into ≤ `max_lines` lines that fit. Costs: each break by
  `phrase_break_cost(before, after)` — sentence end 0, clause mark or dash 1, before a conjunction 2,
  before a preposition 3, plain 4.5, right after an article / preposition / determiner 9; per cue
  1; an under-filled cue `3 x (1 - fill)^2` (fill = width share of `max_lines x max_width`, or of
  `max_words`); unequal lines `4 x (widest - narrowest) / max_width`; a sentence ending inside a
  line 3. A word wider than a line gets a line of its own. `caption_cues` times them: the first
  cue at the beat's start, the others at their first word's start, each until the next, the last
  until `until` (captions: the next beat's start / the scene's end; SRT: the narration end).
- **SRT change**: `subtitles.split_text` / `beat_cues` now use this cutting (was `textwrap` at
  42 characters + pairs of lines) and cue times follow word times (was: proportional to
  characters); `write_srt(path, timings, audio_dir)` (the pipeline passes `project.audio_dir`, so
  MP3 speech bounds and alignments time the SRT too). SRT and burned-in captions therefore cut at
  the same kind of boundaries; their cues are identical only when the caption width in characters
  equals the SRT's 42 (captions measure real text widths).
- **`captions` overlay** (`scenes/captions.py`, `timed`, `layer` 10, `lint_skip = ("max_words",)`:
  the captions are the narration, not extra words on screen). Reads `context.scene.beats`
  (planned scene times) and the project's audio folder; `shown_in` is false on scenes without
  beats (no reserve there). `build()`: an invisible band (`max_lines` lines + padding, `max_width`
  + padding) placed at the safe area's bottom (9:16: raised by `lift` 0.12 of the safe height, like
  the lower third), top or centre, then every cue of the scene as `VGroup(plate, *line Texts)`
  placed in the band (bottom / top / centre aligned). Lines are `Text`s with ligatures off,
  baselines one pitch apart (glyphs standing on the baseline are lined up), shrunk together when
  a word is wider than the line. State: the cue index (subtitles) or `(cue, word)` (karaoke, the
  last word whose start ≤ t; -1 before the first); `pose` returns the cue, karaoke a copy with the
  word's glyphs in the highlight colour scaled by `pop`, capped so it grows by at most 0.25 of a
  space per side (0.45 until Step 48: neighbours nearly touched) (the plate is that much wider). Glyph indices: Manim keeps a submobject per
  character with spaces (0.21) or without (0.19); other counts (ligatures) → no highlight.
- **Colours**: the text colour (default the best of `text`, background, white, black) and the plate
  opacity are chosen so `plate_contrast` (the plate over black and over white: the worst case of
  whatever is behind) reaches `lint.rules.contrast.min_ratio`, raising the opacity in 0.05 steps;
  a highlight that does not reach it is replaced by the first accent token that does (warning).
  `background: null`: no plate; the text gets a background-coloured outline (lint may then report
  contrast over busy scenes — the user's choice).
- **Reserve default** (framework): `OverlayConfig.reserve` is `bool | None` (default `None`);
  `Overlay.reserves` = the entry's / scene override's value, else `default_reserve()` (base
  `False`). Captions return `position != "center"`: a caption band at the top or bottom shrinks
  the scenes' safe area; centred karaoke text does not (it would cut the frame in half), so lint's
  `overlay_overlap` reports scene text under it. The reserved box is the band (stable across
  scenes), not the scene's own cues.
- **Fixes found with it**: `title` and `end_card` centred their card on the frame origin, not on
  `self.safe_area` (with a reserved bottom band their last line ran into it); both now centre on
  the safe area.
- **Fingerprint**: `_overlay_inputs` beats also carry the `.align.json` stat.
- **Example**: `examples/minimal` variants `subtitled` (16:9, `captions`) and `social` (9:16,
  `captions` `style: karaoke`); `vidgen lint` 0 findings for both.
- Known limits: cue times between alignment-less words are estimates (good to a few hundred ms on
  even speech; numbers and pauses vary); karaoke highlights one word at a time (no fill sweep);
  the caption band is reserved per scene (a scene with only one-line cues still keeps room for
  `max_lines`); a lower third and bottom captions are both placed in the global safe area and can
  overlap in 9:16 (move one with `align` / `position` or `lift`).

## 44. Refinements (Step 41, the `callout` beat action)

- **A beat action, not an overlay** (Step 38's note): a callout points at a scene's targets, which
  only exist inside the scene's render, and should move with a zoom like the rest of the scene,
  so it is a per-beat action (`scenes/callout_action.py`, built on the §26 framework and the §37
  helpers), not a screen-fixed overlay. Syntax as every action: `- callout: "bar:4K"` + options,
  or `{action: callout, area: [x, y, w, h], ...}` without a target. It reuses the action
  machinery: target validation and suggestions, `at`, `until`, `run_time`, timing inside waits,
  the JSON Schema, `list-scenes`.
- **Options**: `kind` (`box` default | `circle` | `arrow` | `label` | `spotlight` | `magnifier`),
  `label`, `area` (`[x, y, w, h]` / `[x, y]`, top-left origin as in §37), `within` (`frame` |
  `safe`, areas without a target), `units` (`fraction` | `px`), `color` (`highlight`),
  `label_size` (`caption`), `side`, `curved` (arrow), `zoom` (magnifier), `keep`, `name`.
  Checks in the model (area shape and range, kind-only options, `label` needs text, magnifier
  needs an area) and in `problems()` (a target or an area; a magnifier needs a target; `within`
  only without a target; `keep` with `until`).
- **What it points at**: the targets' outline (`Target.outline`, e.g. a bar with its value),
  else their parts on screen; several targets → one callout around all of them. With `area`
  and a target: fractions (or `px`) of the target's largest picture (an `ImageMobject` or clip
  in its family — so `image` / `screenshot` areas read off the image file), else of its box.
  Without a target: fractions of the **visible view** (`within: frame`, the camera frame when
  zoomed) or of its safe area (`within: safe`); `px` are pixels of the output frame.
- **Where labels go** (`bounds`, `avoid` of the §37 helpers): inside `scene.safe_area` (which
  already excludes `reserve`d overlays); while the camera is zoomed in, inside the view minus
  margins x scale, and the callout is built with `scale` = view width / frame width so it reads
  at its normal size (§37). `avoid`: boxes of every `Text` / `MarkupText` / `Paragraph` / TeX
  mobject on screen, callouts on screen (targets whose mobject is a `Callout`), the scene's other
  targets on screen smaller than 20 % of the view that do not hold the area's centre (a node,
  a bar; not the axes or a map), and the overlays' boxes (mapped into a zoomed view). The arrow
  and `label` kinds prefer spots off the targets. `label` = a `callout_label` placed by
  `label_spot` at gaps 0.15 / 0.35 / 0.7 (a mark-less note). Z-index: above everything on
  screen (+2; a spotlight +1, under other callouts).
- **Lifetime** (framework): new `Action.until_next_beat` (class attribute; requires reversible,
  not temporary) and `default_until(later)`; the runner stores `ActionUse.until` = `until` or
  the default, and undoes at that beat's start as for `until`. The callout goes when the next
  beat starts (`keep: true`: stays to the scene's fade-out; on the last beat it stays anyway).
  Decision: not "by the end of its beat" like `zoom`, because beat-end stills — what storyboard
  and lint look at — would never show it. Undoing fades the parts out (`fade_out`).
- **Named callouts** (framework): `Action.provides()` lists target names a use registers when
  applied; `scene_actions` lets later actions (same beat after it, or later beats) name them,
  checks the name (`TARGET_NAME`, not taken by the scene or an earlier callout). The callout
  registers itself with `on_fill = (label text, plate)`, so `dim` / `highlight` keep its label
  readable (Step 37's routed item). `Action.problems()` reports use-level checks (key, message).
- **Magnifier**: needs a still picture in the target (`image`, `screenshot` `image`); a clip or
  no picture is a render-time `VidgenError` (static checks cannot see the mobjects).
- **`screenshot` `caption`** (+ `caption_size`, `caption_color`), as `video_clip`'s: a line
  under the picture (the picture shrinks to make room), target `caption`, kept clear by callout
  labels (`_keep_off`); `target_names` moved from `video_clip` to `screenshot`. The caption (of
  both types) fades out when a `focus` step moves the camera in and back with the whole frame
  (enlarged under the picture it ran into the watermark in the gallery's `contrast` / `neon`).
- Known limits: placement is the §37 scored search (labels avoid text and small targets, not
  lines: an arrow or a label may cross a chart line or an edge); a callout added before a `zoom`
  scales with the scene (built for the camera of the moment it appears); a callout with `at` in
  the same frame as a `zoom` plays after the zoom-in, built for the zoomed view
  (`Action.after_camera`, Step 48).

## 45. Refinements (Step 42, pronunciation dictionary)

- **Config** (`config.py`): top-level `pronunciation: {term: value}` with value = the spoken form
  (text), `PronunciationEntry {say, case_sensitive: true, whole_word: true, regex: false}` or
  `null` (removes the term: how a variant or the config drops a file's / the base's entry; the map
  deep-merges in variants like any mapping); `pronunciation_file: PATH | [PATH, ...]` (YAML or
  JSON mappings of the same form, relative to the project). Effective entries = the files' in
  order, then `pronunciation:` over them. A value that is neither form is reported once per
  mistake (a `mode="before"` check, not pydantic's per-branch union errors); a regex that does
  not compile, matches the empty string or whose `say` refers to a missing group is a config error.
  The files are read when the `Project` is built (`Project.pronunciation`), so a missing or invalid
  file is a load error with `pronunciation_file (<file>)` problem locations (`validate --json`
  lists them).
- **Matching** (`vidgen/pronunciation.py`, no manim): each entry is a compiled pattern: a plain
  term is escaped; `whole_word` adds `(?<!\w)` / `(?!\w)` on the sides where the term starts /
  ends with a word character (so `C++` and `K-Phi-3's` work); a regex gets both lookarounds;
  `case_sensitive: false` → `re.IGNORECASE`. All matches of all entries in the **written** text
  are collected and chosen greedily by start, then length, then entry order; replacements are
  never matched again (no cascades). `Pronunciation.apply(text) -> Spoken(text, spoken,
  replacements, matched, conflicts)`; `say(text)`; `Project.spoken_texts()` (beat id → spoken).
- **TTS and hash**: everything sent to the provider is the spoken text (the beat and its
  `previous_text` / `next_text` context); the cache key is `provider.cache_key(spoken)` (formula
  of §7 unchanged), so a beat no entry matches keeps the hash of its written text: adding a
  dictionary does not invalidate existing audio (the committed kphi3 MP3s stay valid; kphi3 has
  no entries), and changing an entry re-voices only the beats whose spoken text changes.
  `audio_status` compares with the spoken text. `vidgen tts --dry-run` prints `says: <spoken>`
  under each beat to generate whose spoken text differs; the character count is of the spoken text.
  Variant audio rule (§7): "a beat's text differs" now reads "a beat's spoken text differs" (each
  config with its own pronunciation; `Project.has_own_audio` is cached per project).
- **Alignment / word timings** (Step 40 interaction): the stored alignment (`voice.timestamps`)
  is of the spoken text (`write_alignment(..., spoken, ...)`; `read_alignment` needs the spoken
  text). Subtitles, captions and storyboards keep the written text; their word times come from
  `beat_word_times(audio_dir, beat_id, text, start, end, spoken)`: when `spoken.changed`, the
  spoken words are timed (alignment, else the estimate within the MP3's speech — so the spoken
  syllables are weighed — else over the beat) and `map_word_times(spoken, times)` maps them back.
  Mapping: `Spoken.word_groups()` gives, per written word (`\S+`), the spoken words (`\S+` of the
  spoken text) its characters became: unchanged characters shift by the replacements before them,
  a character inside a replacement maps to the whole replacement; a written word's time runs from
  its first spoken word's start to its last one's end ("K-Phi-3" → "kay fye three": 3 → 1); a
  word said as nothing gets a zero-length time at the next spoken word's start (or the previous
  end); written words joined by one replacement share its words' time. The SRT gets the project's
  pronunciation (`write_srt(path, timings, audio_dir, pronunciation)`), captions read
  `context.project.pronunciation`.
- **Lint**: `SceneContext.spoken` (beat id → spoken text, from `Project.spoken_texts()`);
  `narration_speed` counts `spoken_words` of the spoken text. The no-audio duration estimate
  (`words_per_second`) still counts written words (unchanged, so renders do not move).
- **Render fingerprint**: `pronunciation` / `pronunciation_file` are excluded from the config
  part (they change only audio, which is tracked); with overlays, each beat's spoken text joins
  the overlay inputs (captions' word times depend on it).
- **`vidgen validate` warnings** (not problems; `--json` `warnings`): an entry that matches no
  beat; an entry that matches but never applies because a longer entry always holds it; two
  entries matching the same span or crossing spans in a beat (which one is used there). An entry
  inside a longer one that also applies elsewhere is intended (no warning). `cli.validate_warnings`
  = theme contrast + pronunciation (`log_theme_warnings` became `log_validate_warnings`).
- **Example**: `examples/minimal` (no committed audio): `LaTeX: lah-tek`, `JSON: jay-son`.
- Known limits / not done: no SSML `<phoneme>` (IPA) entries — ElevenLabs reads phoneme tags only
  with some models (not `eleven_multilingual_v2`), the tags would be billed characters and the
  alignment would no longer be of plain words; no ElevenLabs server-side pronunciation
  dictionaries (`pronunciation_dictionary_locators`); no per-beat `say:` override; matching is
  per beat (a term split across two beats never matches); `whole_word` uses Python's `\w`
  (Unicode letters and digits).


## 46. Refinements (Step 43, multiple voices)

- **Config** (`config.py`): top-level `voices: {name: VoiceEntry}` — every key of `voice:`
  optional (`provider`, `voice_id`, `model_id`, `output_format`, `settings` as
  `VoiceSettingsOverride` with every value optional, `context`, `timestamps`) plus `label` and
  `color`; `SceneConfig.voice` and `BeatConfig.voice` (identifiers); `VoiceConfig` gains `label`
  (default `None`: the base voice is not tagged) and `color` (`ColorRef`: hex or a theme token);
  top-level `subtitles: {speakers: off | name}`. `default` is reserved (the base voice; a
  `voices:` key `default` is an error). Names are checked after the model validates, in
  `parse_config` (`voices.voice_reference_problems`): `scenes[i].voice` /
  `scenes[i].beats[j].voice: unknown voice 'x'; did you mean 'y'? voices: default, ...` as
  problems with locations (variant problems are attributed to the variant as usual). Colour
  tokens are checked by `vidgen validate` with the project's theme (`voice.color`,
  `voices.<name>.color`); a voice no beat uses is a warning (`validate_warnings`). Variants
  deep-merge `voices:` like any mapping.
- **Effective voice** (`vidgen/voices.py`, no manim): a beat's voice is its `voice`, else its
  scene's, `default` → `None` (the base). `resolve_voice(config, name)`: the base voice's
  `model_dump` without `label` / `color`, the entry's non-`None` keys over it, `settings` merged
  key by key; `label` / `color` only from the entry (a speaker's name is never inherited).
  `Project.voice_names()` (beat id → name | `None`, video order), `Project.voice(name)` (cached),
  `Project.beat_voice(beat_id)`, `Project.speaker_tags(mode)`.
- **Hash / cache key**: unchanged formula (§7), computed by the provider of the beat's effective
  voice: `tts.beat_providers(project)` (one provider per voice). Beats of the base voice are hashed
  exactly as before, so a project without the new keys keeps every hash (kphi3's committed audio:
  27 ok); editing one named voice re-voices only its beats; moving a beat to another voice
  re-voices it; `label` / `color` are not hashed. `audio_status`, `plan_tts` and `run_tts` use the
  per-beat providers; their optional `provider` argument replaces all of them (tests). Variant
  audio rule (§7): own folder when the base voice's audio fields differ (`audio_fields`: all but
  `label` / `color`) or a shared beat's spoken text **or effective voice** differs; unchanged beats
  are copied from `audio/` (checked with the beat's own provider).
- **Context decision**: `previous_text` / `next_text` are the neighbouring beats in video order
  (across scenes, as before) **only when they have the same voice name**; at a change of speaker
  none is sent (`tts.run.context_texts`). Reason: ElevenLabs' request context (and request
  stitching, which is defined for one voice) treats the text as the same speaker's surrounding
  speech; another speaker's line would be read as this voice's own words (e.g. the rising tone of
  a question carried into the answer). A speaker's lines separated by another speaker's reply
  are not joined either (a turn is a prosodic reset). Not hashed (unchanged). ElevenLabs' newer
  multi-speaker *text-to-dialogue* endpoint (v3) is not used: it returns one file for many lines,
  which does not fit the beat-per-MP3 cache.
- **`vidgen tts`**: `--voice NAME` (repeatable; `default` = the base voice; unknown → error with
  suggestion) restricts the plan like `--beat` (both: intersection). When `voices:` is non-empty,
  `--dry-run` adds `, voice <name>` to every `would generate` line and after the summary one line
  per voice `  voice <name> (<voice_id>): N beat(s), C characters` (beats to synthesise, copies
  excluded); projects without `voices:` print exactly as before. `TTSPlan.voices`,
  `TTSPlan.characters_by_voice()`. `timestamps` is read from each beat's voice.
- **`vidgen validate`** (human) prints `voices:    default (N beats), ana (M beats)` when
  `voices:` is set.
- **Speakers in subtitles** (`subtitles.speakers: name`): `voices.speaker_tags(config)` gives a
  label for every beat whose voice differs from the previous beat's (video order; the first beat
  included) and that has a label (named voices: `label` or the name with `_` as spaces and a
  capital first letter; the base voice only with `voice.label`). `write_srt(..., speakers)` /
  `cues_from_timings(..., speakers)` / `beat_cues(..., speaker=)` start that beat's first cue with
  `"<label>:"` (`speaker_prefix`). The tag is cut with the text as `caption_cues(prefix=,
  prefix_width=)`: glued to the first word (its width added to the first word's), so a cue never
  holds the tag alone; `CaptionCue.prefix` holds it and `words` excludes it.
- **Captions** (`captions` option `speakers`: `off | name | color | both`, default
  `subtitles.speakers`): `name` adds the tag (glyphs in the speaker's colour); `color` draws each
  cue in its speaker's colour (`speaker_color`: the voice's `color`; a named voice without one:
  `theme.palette_color(index in voices)`; the base voice: `voice.color` or the caption's text
  colour); `both` does both. The plate opacity is raised (0.05 steps) until every speaker colour of
  the scene reaches `lint.rules.contrast.min_ratio`; one that cannot even at opacity 1 falls back
  to the text colour with a warning. Karaoke's word glyph map skips the tag's words (never
  highlighted).
- **Fingerprint**: `voices` and `subtitles` are excluded from the config part (they change only
  audio, which is tracked by the MP3 stats, and captions); with overlays, the overlay inputs carry
  each beat's voice name and the `voices` / `subtitles` sections (a scene's tag depends on the
  previous beat's speaker, possibly in another scene). The overlay inputs are now `{scenes,
  voices}` (renders with overlays count as stale once).
- **Pronunciation (§45)**: one dictionary for every voice; the hash covers the spoken text and
  the voice, so both edits re-voice exactly the beats they change. Per-voice entries are not
  implemented (a variant with its own `pronunciation:` covers another-language voice).
- **Example**: `examples/minimal` names a `guest` voice (another `voice_id`, `stability`, label,
  `secondary` colour), the `note` scene is a two-line dialogue (guest asks, narrator answers),
  `subtitles.speakers: name`, and the `subtitled` variant's captions use `speakers: both`.
- Known limits: storyboard labels and `timings.json` do not name speakers; the tag shows only on
  a beat's first cue (karaoke shows it briefly: prefer `color`); no per-voice `narration.pad` or
  `words_per_second`; no ElevenLabs text-to-dialogue.


## 47. Refinements (Step 44, sound effects)

- **Sounds** (`vidgen/sfx.py`, no manim): eleven built-in sounds (five more since Step 86, §69.19) (`BUILTIN_SOUNDS`: whoosh,
  swoosh, pop, click, tick, typing, riser, chime, success, error, thud), each a deterministic
  numpy generator (`BuiltinSound(name, generate, duration, duration_range, description, use)`;
  noise from `default_rng(crc32(name))`; filters as zero-phase magnitude responses in the
  frequency domain, time-varying band-passes by STFT) taking `Synth(n, ratio, intensity, rng)`:
  `params` `duration` (within the sound's range), `pitch` (semitones, ±24) and `intensity` (0–1:
  timbre, and ±3 dB around 0.5). Finishing (`_finish`): high-pass 25 Hz, raised-cosine fades
  (first and last sample exactly 0), the mean removed by subtracting a scaled Hann window (zero
  at the ends, so DC is 0 and the ends stay 0), then the level: the loudest 400 ms window
  (BS.1770 K-weighting at 48 kHz, applied as a magnitude response; `loudness()`) at
  `LOUDNESS_TARGET` −27 LUFS (one channel), peaks capped at `PEAK_CEILING` −9 dBFS (short clicks
  and ticks are peak-limited, so they measure quieter). Calibration: the committed kphi3
  ElevenLabs MP3s measure −18.5 to −21.4 LUFS the same way (peaks −4 to −8 dBFS), so a sound at
  gain 0 sits ~7 dB under narration (a test keeps it ≥ 5 dB under the quietest beat).
- **Decision: synthesised when the video is joined, cached per process** (`synthesize`,
  `lru_cache`), not shipped as package-data WAVs: the params are continuous (pre-rendered files
  could only give the defaults), every sound takes 5–110 ms, and nothing (~1 MB of WAVs) is
  added to the wheel. `vidgen list-sfx --render-dir DIR` writes previews for a human.
- **Project sounds**: `assets/sfx/<name>.<wav|flac|ogg|mp3>` (`project_sounds`; `.wav` first
  when a name has several; invalid names skipped with a warning) extend or replace built-ins by
  name (`SoundLibrary`; `list-sfx` marks `overrides_builtin`); decoded with PyAV to 48 kHz
  (mono or stereo kept); played at their own level, no `params` (a problem when given).
- **Where sounds come from**: `NarratedScene.sfx(sound, at=None, *, gain, pan, align, **params)`
  (scene seconds; default `renderer.time`) validates with the config model `SfxCue` and the
  library and appends an `SfxEvent(time, sound, gain, pan, align, params, beat)` to `sfx_log`;
  nothing is drawn, no time passes. A scene's `sfx:` list (`SfxCue`: `sound`, `at` seconds,
  `gain` dB −60..12, `pan` −1..1, `align` `start|end`, `params` `SfxParams`; a plain string =
  `{sound}`; on a silent scene `at` < `duration`) is recorded in the constructor. The beat action
  `sfx` (`scenes/sfx_action.py`) — `- sfx: NAME` (or `sound:`), options `gain`, `pan`, `align`,
  `params` — is cued by the runner. `timings()` gains `sfx` (the events) when there are any.
- **Framework** (`vidgen.actions`, compatible): `Action.scene_targets` (False: `target` is not
  checked against / resolved among the scene's targets; the action's `problems()` checks it) and
  `Action.animates` (False: the runner calls `cue(scene, time)` when the beat starts, with the
  due frame's time — `at` rounded to a frame like any action — and marks the use applied; it is
  never queued for a wait; `check_action_class`: such actions implement `cue`, not `apply`, and
  cannot be reversible). **Decision**: a sound plays exactly at `at`, even while the scene's own
  animation runs (animating actions wait for it), so `at: 0` lands with the beat's entrance;
  syncing to a delayed action's start is left to `sfx.auto`.
- **Auto** (`sfx: {auto: true}`; `SfxConfig.auto`, default off): `ActionRunner._build` calls
  `scene.auto_sfx(name)` when a *built-in* action's `apply` returns animations (so a no-op
  `reveal` makes no sound), at the moment it starts playing — `AUTO_ACTION_SFX`: reveal → pop
  −3 dB, highlight → tick −3, callout → click −2, zoom → whoosh 0.5 s −6, transform → swoosh −6
  — except in beats that have their own non-animating (`sfx`) actions; and scene types with
  `entrance_sfx` (`chapter`: whoosh −3 dB) get it at time 0. Scene types' own reveal steps get no
  automatic sounds (a pop per bullet / bar / node was judged too busy).
- **Mixing (no Manim sound)**: the worker stores the events in `timings/<id>.json` (always, also
  with `--no-audio`). `join_scenes` shifts them by each scene's offset (combined `timings.json`
  scenes gain `sfx`, video times) and, unless `no_audio`, writes **one SFX track for the whole
  video**, `padded/sfx.wav` (`write_track`: 48 kHz stereo s16, exactly `round(total * 48000)`
  samples = the sum of the padded scene WAVs; event start sample `round(time * 48000)`, minus
  its length for `align: end`; parts before 0 / after the end cut; written in 10 s blocks;
  sums clipped, never wrapped), with `sfx.gain` (master dB) added. Pan: equal-power, centre =
  full level on both channels (as a mono narration MP3 is duplicated, since Step 48 by
  `scene.add_narration`; see §51), so loudness compares 1:1. `ffmpeg.join(..., sfx=)` adds it to the concatenated narration with
  `amix=inputs=2:duration=first:dropout_transition=0:normalize=0` (a plain sum) before the one
  AAC encode. Sounds therefore run across scene cuts (a sound after its scene's end is a warning),
  are sample-exact in the timeline, and do not resample the narration (Manim's pydub mix would
  place at 1 ms and resample the MP3 to the sound's rate). Scene renders and storyboards have no
  effects. Without events (or with `--no-audio`) the join is byte-for-byte the old command.
- **For Step 45 (music, ducking, loudness)**: the voice track (concatenated `padded/<id>.wav`:
  narration + clip sound) and the SFX track stay separate until the final mux, so music can be
  ducked with the voice track alone as the sidechain (`sidechaincompress`), then voice + SFX +
  ducked music summed and `loudnorm`ed; the SFX levels are relative (−27 LUFS ≈ 7 dB under
  narration) and survive a normalisation of the sum.
- **Checks**: `vidgen validate` (`cli.project_problems` + `sfx.config_problems`): unknown sounds
  with did-you-mean and the list, params on project files, durations outside the range, at
  `scenes[i].sfx[k].<key>` and `scenes[i].beats[j].actions[k].<target|sound|params.duration|
  run_time>`; the render pre-check raises them; `NarratedScene.sfx` raises `VidgenError`.
- **Listing**: `vidgen list-sfx [PROJECT] [--render-dir DIR] [--json]` (`sound_entries`: name,
  origin, description — precise words for an author who cannot listen — use, duration, range,
  channels, loudness, peak, preview); `list-scenes` shows `sfx` as "(at its time, does not
  animate)", JSON actions gain `scene_targets`, `animates` (within version 1). `sfx.py` is not a
  render-fingerprint input (sounds never change pixels); scene `sfx:` lists and `sfx` actions
  are part of the scene's config, so editing them re-renders that scene's stills.
- Known limits: no per-scene switch for `auto` (a variant can turn it off); a sound still
  playing at the video's end is cut without a fade; project sounds are not loudness-normalised;
  built-ins are mono (pan places them).

## 48. Refinements (Step 45, background music, ducking, loudness)

- **Config** (`config.py`): top-level `music:` (`MusicSetting`): a source name, one `MusicCue`,
  a list of cues, or `false` / null. `MusicCue`: `source` (a bed name or a path under the
  project), `volume` dB (−60..12), `start` s, `loop` (true), `crossfade` s (2), `fade_in` (1.5),
  `fade_out` (3), `duck` (`DuckConfig` or a bool: `false` = depth 0), `from` / `to` scene ids.
  `VideoConfig._music_problems`: known scenes, `from` not after `to`, no two cues on one scene.
  `VideoConfig.music_cues` gives the list. Scene `music: true | false | {volume}`
  (`SceneMusic`). Top-level `audio:` (`AudioConfig`): `normalize: auto | true | false`,
  `target_lufs` (−16, −40..−5), `true_peak` (−1.5 dBTP, −9..0). `vidgen validate`
  (`music.config_problems`) reports a source that is neither a bed nor a file; the render
  pre-check raises it. `music` / `audio` and a scene's `music` are not render-fingerprint
  inputs, nor are `music.py`, `mix.py`, `loudness.py` (music never changes pixels or timing).
- **Beds** (`vidgen/music.py`, numpy only): `calm` (60 s, D major, no beat), `pulse` (40 s,
  A minor, 96 BPM), `bright` (48 s, C major, 120 BPM); Step 129 adds `cartoon` and `lullaby`
  (§69.63). Pads by PADsynth: each chord's harmonics
  as Gaussian bumps (18–30 cents wide) with random phases in one spectrum, one inverse FFT → a
  periodic wave whose length divides the chord's segment; chords cross-fade with equal-power
  windows of 1.6 s; an airy layer an octave up swells with an LFO whose period divides the loop;
  a sub-bass under each chord; `pulse` / `bright` add plucked eighth-note arpeggios (patterns
  picked per bar), a soft thump per beat (`pulse`) or a sparse bell melody (`bright`). Tone
  shaping per partial (high-pass 40 Hz, low-pass 3.5–4.5 kHz, both second order): nothing harsh,
  no rumble (tests: < −30 dB of the energy above 5 kHz, < −30 dB below 35 Hz). Everything is
  rendered **circularly** (notes past the loop's end continue at its start; the waves are
  periodic in the loop), so the loop tiles without a seam. Seed `crc32("music:<name>")`;
  `bed_loop(name)` is cached per process (~1–1.5 s to make). Level: `MUSIC_LEVEL` −28 LUFS
  integrated (−30 until Step 48, §51). **Decision: a loop tiled to the needed length**, not a piece generated for the
  whole video: generation cost is fixed, loops of 40–60 s with chord changes every 4–7.5 s and
  slow LFOs rarely sound repetitive under narration, and a loop is trivially seamless.
- **Files**: decoded with PyAV (`sfx.decode_audio`), mono duplicated, cached per (path, size,
  mtime); measured (integrated) and scaled to `MUSIC_LEVEL`. `music.Source(cue, root)`: from
  `start` on; looping files play `body[:-X]` once, then a loop whose first `X` samples are the
  head cross-faded (equal power) with the tail, so every repeat continues exactly where the
  previous pass stopped; `loop: false` → silence after the end (the cue's fade-out ends there).
- **Loudness** (`vidgen/loudness.py`): BS.1770-4 integrated loudness (400 ms blocks, 100 ms
  step, absolute gate −70 LUFS, relative gate −10 LU), K-weighting as the filter's magnitude
  response applied by FFT to 10 s blocks read with 0.5 s margins (circular per block; the margins
  absorb the edges), `LoudnessMeter` fed in order, true peak by 4x polyphase windowed-sinc
  interpolation (Kaiser, 12 taps a side). Checked against FFmpeg's `ebur128` on a rendered mix
  (−16.1 / −1.6 dBTP both). ~0.2 s per 10 s of audio per pass.
- **Ducking** (`vidgen/mix.py`): **decision: a gain curve computed from the narration's timing,
  not an audio envelope follower or FFmpeg `sidechaincompress`**. The key is where speech is: each
  beat from its start to the end of its speech (`speech.speech_bounds` of its MP3; the whole beat
  without audio), so it is exactly "the narration track only" (clip sound and SFX are mixed into
  the same WAVs / track and could not be told apart by level), deterministic, and able to look
  ahead (offline). `duck_curve` at 100 Hz: pauses shorter than `hold` filled; in dB, `-depth`
  where speech is, raised-cosine ramps of `attack` s ending at a speech start and `release` s
  after its end (max of both). Defaults 12 dB / 0.4 s / 1.0 s / 1.5 s: ElevenLabs beats are
  ~1 s apart (lead/trail silence + pad), so with a shorter hold the music pumped up between
  every beat. With `duck.clips` (default) a `video_clip` scene whose clip has sound (not
  `mute`, `volume` ≠ 0, the file has an audio stream) is foreground for its whole span.
- **Per scene and per cue gain** (`plan_music` → `Placement`s, 10 ms frames, interpolated per
  sample): `10^(volume/20)` × fades (raised cosine; fade-out ends at the cue's end or the
  source's) × scene levels (`false` → 0, `{volume}` → dB; steps smoothed by `smooth_steps`:
  a running minimum then a moving average, 0.75 s, so a ramp lies on the louder side — the
  quieter scene has its level from its first to its last sample) × ducking. A cue spans its
  `from` scene's start to its `to` scene's end (the last cue to the video's exact end).
- **The mix** (`mix_audio`, called by `join_scenes` unless `--no-audio`): tracks read block by
  block — `WavTrack` (the padded scene WAVs, the SFX track) and `MusicTrack`. **Decision:
  normalisation `auto` by default — on when the video has music, off otherwise** — so every
  existing narration-only video keeps its exact audio (the join command is byte-for-byte the
  old one; the mix is only measured), while a video with music, whose level is new anyway, comes
  out at −16 LUFS. Not while the video has narrated beats but none has its MP3 (a preview timed
  from word counts: the gallery measured +25 dB of gain on music and effects alone; logged at
  info level, `normalized: false`). With music or `normalize: true`: pass 1 measures the sum (no true peak),
  gain = target − measured; pass 2 writes `padded/mix.wav` (48 kHz stereo **24-bit**: the gain
  and fades stay clean) through `limit()` — the gain each sample needs for its true-peak
  envelope to stay `LIMITER_MARGIN_DB` (0.4 dB since Step 48, was 0.1) under `true_peak`, a running minimum (±5 ms) then a 10 ms moving
  average, so the gain never exceeds the need and moves smoothly; block margins make it exact
  across blocks — and measures the output. `ffmpeg.join(..., mix=)` then uses the WAV as the
  audio (one AAC encode). `MixReport` → combined `timings.json` `mix` and `render --json` `mix`:
  `{mixed, normalized, target_lufs, true_peak_limit, gain_db, integrated_lufs, true_peak_dbtp,
  limited_db, music: [{source, kind, from, to, start, end, volume, duck}]}`; the human render
  output adds a `loudness:` line.
- **Levels measured**: committed kphi3 MP3s are −21.4 LUFS integrated (as stereo). Until Step
  48 a rendered narration track was −24.4 (Manim's MP3 conversion upmixed mono −3 dB per
  channel) and `MUSIC_LEVEL` was −30; Step 48 plays narration at the MP3s' level and sets
  `MUSIC_LEVEL` −28, so music is ~6.5 dB under the voice in pauses and ~18.5 dB under it when
  ducked, and the Step 44 SFX level (≈ 7 dB under narration) holds as stated (§51).
- **`vidgen list-music [PROJECT] [--render-dir DIR] [--json]`** (`music.music_entries`,
  `jsonout.list_music_document`): every bed with a precise description, use, tempo, key, chords,
  loop length and measured loudness; the project's `assets/music` files (any path works as a
  source; that folder is only what is listed); previews of one loop per bed.
- Known limits: cues do not cross-fade into each other (the first fades out, the next fades
  in); the beds are fixed (no tempo / key parameters); a file is decoded whole into memory
  (~23 MB per stereo minute); music is not in scene renders or storyboards; the AAC encode may
  raise the true peak by ~0.2 dB (inside the limiter's margin); no LRA / short-term loudness targets.


## 49. Refinements (Step 46, transitions: crossfade and fade through a colour)

- **Config** (`config.py`): `TransitionConfig {type: cut | crossfade | fade_color, duration,
  color}` (`duration` 0 < d ≤ 5, default per type `TRANSITION_DURATIONS`: crossfade 0.5,
  fade_color 1.0; a cut has no duration; `color` only on fade_color: a theme token, `background`
  or hex, default the theme's background); a plain string is the type (`TransitionSetting`).
  `SceneConfig.transition` = the way **into** that scene; `VideoConfig.transition` = the default
  for every scene but the first (`transitions.effective(config, i)`). A crossfade on the first
  scene is a config error; `fade_color` there fades the video in. `vidgen validate` checks colour
  tokens (`transitions.color_problems`) and warns about holds (below).
- **Timing contract (decision): a crossfade overlaps the two scenes, a fade_color does not.** A
  real cross-dissolve needs both pictures at once, so the next scene starts `overlap` frames before
  the previous one ends and the video gets shorter by it; a fade through a colour needs no second
  picture, so the previous scene's last `fade_out` frames fade to the colour and the next scene's
  first `fade_in` frames fade in from it (`round(duration x fps / 2)` each), and the video keeps
  its length. **Speech never overlaps**: a transition may cover only the *silent tail* of the scene
  before it — its frames after the last beat's narration end (`start + d`: the pad and the
  fade-out), the whole scene when it is silent, never the frames its own incoming transition uses
  (`transitions.silent_tail`). When the tail is shorter, that scene is **held** on its last
  picture by the difference (`hold`, added in `NarratedScene.tear_down`) — a decision for
  "extend" over "clamp": the author gets the transition asked for, and pacing changes by the
  hold only, which `vidgen validate` reports. Defaults need no hold for built-ins (tail = pad 0.35
  + outro 0.5 ≥ 0.5). The incoming scene's narration starts with it, so it may speak during a
  crossfade (over the previous scene's silence).
- **The plan is the one source of start times** (`videoplan`): frame-based now — a scene's own
  frames (beats + outro, or its duration), `transition(i) -> TransitionSlot(type, seconds, color,
  overlap, fade_out, fade_in, hold)` (frames; a cut for every scene of a video without
  transitions, which keeps the old plan exactly), `scene_duration(i)` = own + the hold of the
  transition out of it, `start(i) = start(i-1) + frames(i-1) - overlap(i)`. `SceneSlot` gains
  `overlap_in`, `overlap_out` (seconds) and `cut` (= `end - overlap_out`, where the next scene
  starts). Chapters, the progress bar, the chapter indicator (runs now end at `cut`), lower
  thirds (`min(end, slot.cut)`), `resolve(scene id, end=True)` (= `cut`), captions (per scene
  times), all follow it. The join computes the same overlaps from the renders
  (`transitions.join_overlaps`: the requested frames limited to the measured silent tail and the
  scene's length; equal to the plan when renders match it, and a shortened crossfade is warned
  about), and every later time — combined `timings.json` starts and beats, the SRT, SFX events,
  music cues and ducking spans, the frames index, storyboard times (`storyboard.scene_starts`) —
  is derived from the overlapped starts. `Project.estimated_duration` subtracts crossfades.
- **How a scene ends** (`NarratedScene`): with a transition other than a cut after it,
  `finish()` holds the picture for the outro frames instead of `clear_all` (same frame count),
  so a crossfade blends the full picture (no dip through the background) and a colour fade fades
  the picture itself. Extension scenes that fade out themselves still work (the crossfade blends
  their faded picture). `transition_in` / `transition_out` hold the planned slots; the scene
  reads the plan only when the video has transitions.
- **Video at the join** (`ffmpeg.join(..., crossfades, frames, fps)`): consecutive scenes joined by
  cuts form runs (one concat list each); runs are blended with `xfade=transition=fade`, chained,
  each starting half a frame before its first shared frame (`crossfade_graph`): weights
  `(j + 0.5) / n`, symmetric, the middle frame of an odd crossfade 50/50, and exactly
  `sum - overlaps` output frames (tested). The video is then encoded once (libx264, CRF 18
  `VIDEO_CRF`, yuv420p) — decision: re-encoding only the transitions would need cuts at arbitrary
  frames of stream-copied H.264 (keyframes), and CRF 18 over Manim's CRF 23 sources is visually
  lossless; it costs about real time at 1080p. Without crossfades the join is the old stream copy.
  `xfade` also has wipes and slides (Step 47). Each run enters `xfade` through
  `ffmpeg.constant_rate` (Step 64): `tpad=stop=1:stop_mode=clone,setpts=PTS-STARTPTS,fps=<fps>,
  trim=end_frame=<run frames>,settb=AVTB`. `xfade` refuses an input without a constant frame
  rate, and FFmpeg 7.0 / 7.1's `setpts` clears it ("1/0 is invalid"; 6.x keeps it, 8.x clears
  it only with `strip_fps`), so `fps` sets it after the `setpts`; FFmpeg 4.4 / 5.1's `fps`
  drops a stream's last frame (their end of stream is at that frame's timestamp), hence the
  one-frame `tpad` before and the `trim` back to the exact count after. Tested on 4.4, 5.1,
  6.1, 7.0, 7.1 and 8.1. ffmpeg 4.4 or newer is required (`ffmpeg.MIN_VERSION`; 4.3 lacks
  `amix=normalize`, 4.2 `xfade`); an ffmpeg error from an older one says so (`version_hint`).
- **Audio at the join**: the padded scene WAVs keep their exact lengths; with overlaps they are
  summed into `padded/voice.wav` (`transitions.write_voice_track`, sample offsets from the same
  cumulative rounding as before, so nothing drifts), the earlier scene's tail fading out (raised
  cosine) under the next scene's start at full level — that tail has no narration by the
  contract; only clip sound can be there. `voice.wav` replaces the per-scene list for the final
  mux and `mix.mix_audio`.
- **fade_color inside the render** (`transitions.ColorFade`): wraps `renderer.add_frame`
  outermost (after the overlay layer), so the colour blends the scene's picture and the overlays
  are drawn on top; colour weight `1 - k / fade_in` at the start, `(j + 1) / fade_out` at the end
  (the scenes' boundary frames are the pure colour); frozen waits are split per faded frame. The
  last frames are found from the planned length (the plan contract; a scene that overruns would
  fade early — the join's drift warning covers it). Stills, the layout dump and storyboards see it.
- **Overlays in a crossfade (decision: the incoming scene's on both sides)**: overlays are
  composited inside each scene's render, so a crossfade blends two composited pictures. Overlay
  states are a pure function of video time, but *which* overlays a scene draws is not (captions
  show the scene's own cues, a chapter card has no indicator, a scene may turn overlays off): A's
  tail would show A's last caption while B's head shows B's first — a doubled, half-transparent
  caption. So `OverlayLayer` takes `following` (the next scene's overlays, built with
  `scene_overlays(next)`) and a `cut` time: from the next scene's start on, A's render draws B's
  overlays instead of its own. Both renders then hold identical overlay pixels in every shared
  frame and, the blend being linear, `α (o + (1 - a) A) + (1 - α) (o + (1 - a) B) = o + (1 - a)
  (α A + (1 - α) B)`: the overlays come out exactly as if drawn over the blended pictures (tested:
  caption region and progress bar equal in both renders, the intro shows the talk's caption over
  its last frames). Overlay changes therefore happen at the *start* of a crossfade. Own overlays
  still decide the scene's `reserve`; `scene_overlays` drops overlays that end before `cut`.
- **Lint / storyboard**: beat-end stills are before the transitions (the overlap lies in the
  outro), so layout rules are unaffected. `dead_air`: the activity file gains `overlap_out`
  (frames the crossfade covers) and a still run ends there (the held outro would otherwise add
  0.5 s of "no change"). Storyboard sheet times are video times with overlaps.
- **Fingerprint**: a scene's render depends on the transition out of it (held vs faded, colour
  fade, hold) — `next_transition` (its config and what limits it: the next scene's duration,
  beats and MP3 stats; `"cut"` for a cut, so adding a transition elsewhere does not re-render
  unrelated scenes); its own `transition` is in its config dump; with overlays every scene's
  `transition` joins the overlay inputs (crossfades move later scenes).
- **JSON**: combined `timings.json` scenes with a transition gain `transition: {type, duration,
  overlap}` (within version 1); activity `overlap_out`.
- **For Step 47 (push, wipe, continuity; done, see §50)**: `type` grows (`push`, `wipe`) with a `direction`
  option; `crossfade_graph` maps them to `xfade`'s `slideleft/right/up/down` and
  `wipeleft/...`. Unlike a fade, a slide or wipe is not linear in the two pictures per pixel, so
  overlays baked into both scenes would slide/wipe with them (a watermark moving). Suggested
  approach: the incoming scene's worker also writes its overlay layer for the overlap frames as a
  separate RGBA clip (or both scenes render the overlap *without* overlays), the join slides the
  bare pictures and overlays the RGBA clip on top (`overlay` filter). The timing contract
  (overlap, silent tail, hold) carries over unchanged. A match-cut helper can use the plan to
  know the previous scene and its last state.
- Known limits: the join re-encodes the whole video when any crossfade exists; `fade_color` and
  crossfades happen at planned frames, so an extension scene that times itself differently from
  the contract is faded/overlapped where the plan expected it (warned at join); a crossfade into a
  scene shorter than the crossfade is shortened to that scene; no transition after the last scene
  (an `end_card` fades out by itself); transitions are not previewed in a single scene's render
  (`vidgen render --scene X` shows the scene's held tail, the blend happens at the join).

## 50. Refinements (Step 47, push, wipe, continuity)

- **Config.** `TransitionConfig.type` adds `push` and `wipe` (default 0.6 s), with `direction`
  (`left | right | up | down`: where the pictures / the edge move; push / wipe only) and `soft`
  (wipe only). `config.OVERLAPPING_TRANSITIONS = (crossfade, push, wipe)`,
  `TransitionConfig.overlaps`; every place that tested `type == "crossfade"` (plan, join
  overlaps, head frames, estimated duration, first-scene check, join warnings) now tests
  `overlaps`. Default direction (`transitions.direction(t, portrait)`): `left` in a wide or square
  frame, `up` in a tall one (the next scene comes in from the right / from below), resolved per
  render format, so one video-level `push` suits the 16:9 video and its 9:16 variant.
  `transitions.xfade_name`: `fade`, `slide<dir>`, `wipe<dir>`, soft → `smooth<dir>` (FFmpeg's
  soft-edged wipes). Checked empirically: `slideleft` moves both pictures left with the next one
  entering from the right, `wipeup` uncovers the next one from the bottom; with the half-frame
  early offset the next scene covers `(j + 0.5) / n` of the picture at shared frame `j` (tested
  with solid colours, all four directions).
- **Timing**: exactly the crossfade contract (overlap of the silent tail, hold, the plan as the
  one source of starts, voice track summed over the overlap).
- **Overlays (decision: rendered once, outside both pictures, composited at the join).** A slide
  or wipe is not per-pixel linear, so overlays baked into both renders would move (a sliding
  watermark, two half captions). So: the outgoing scene draws **no** overlays from the planned
  cut on (`OverlayLayer` without `following`: `_build_overlays` gives `following` only for a
  crossfade, the own overlays stop at `cut` as before); the incoming scene's worker calls
  `OverlayLayer.split_head(overlap, path)` (`NarratedScene.overlay_head` = the planned overlap
  of an incoming push / wipe): its first `overlap` frames are written bare and the overlays of
  those frames go, per frame and as a pure function of video time like everything else, into an
  RGBA clip `scenes/<id>.overlay.mov` (`RgbaClip`: QuickTime + PNG, straight alpha;
  `OverlayLayer.rgba(states, h, w)` blends the cached premultiplied patches over transparency, so
  it is the same picture `composite` would draw, within 2 levels — tested). The join (`ffmpeg.join
  (kinds=, overlays=[(clip, first output frame)])`, `overlay_graph`) draws each clip after the
  `xfade` chain with `overlay=eof_action=pass:format=yuv444`, the clip shifted half a frame early
  so frame `j` lands exactly on output frame `start + j`; `RgbaClip.close` appends a transparent
  frame because `overlay` stops showing a clip at its last frame's timestamp (found by test: the
  last frame was dropped). Which overlays: the incoming scene's, from the transition's start, as
  for a crossfade (§49). The clip covers the incoming scene's first frames whatever overlap the
  join ends up using, so a shortened overlap stays correct. Timings `render.overlays.head`
  records the frames; a clip is used only when the transition into the scene is still a push /
  wipe. Alternative rejected: compositing in Python at the join (decode + re-encode the overlaps
  ourselves) — more code, and the join already re-encodes once.
- **Continuity (`carry`).** `SceneConfig.carry: list[CarryEntry(source, dest)]` from `name` /
  `"a -> b"` strings (`CarrySetting`: dumped back as the strings; target-name syntax
  `config.TARGET_NAME_PATTERN`, now shared with `actions.TARGET_NAME`; one destination once; not
  on the first scene). `carry.carry_problems` (validate + before any render) checks sources
  against the scene before's `target_names(params)` and destinations against the scene's (types
  that declare `target_patterns` only; synonyms `title`/`heading` as for actions);
  `carry_warnings`: a carry through `fade_color` / `push` / `wipe` (they fade or move the
  carried objects with the picture).
  - **Recording** (scene A): `NarratedScene.carry_out` = the next scene's sources; `finish()`
    fades everything but their on-screen parts (`clear_all(keep=)`: a group holding a kept part
    fades only its other submobjects); `tear_down` records each source's on-screen parts as
    plain shape data (`carry.parts_state`: per vector family member with points, its points,
    fill / stroke / background-stroke RGBAs, widths, z, joint / cap style; images are skipped
    with a warning) into `carry_state`; the worker writes `carry/<A>.json` `{version, scene,
    fingerprint, objects: {source: [shapes]}}`. Decision: **re-created shapes, not pickled
    mobjects** (no class identity, updaters or file paths to carry; pixel-identical — tested
    within 1 level on text, strokes and fills).
  - **Showing** (scene B): the worker reads A's record (missing → `VidgenError` naming A) into
    `scene.carried_in` and notes `render.carry_from` = A's fingerprint; `setup()` adds the
    rebuilt `VGroup` of each entry from frame 0. `entrance(target)` (what built-ins use to bring
    targets in) returns `carry_move(copy, target.mobject)` for a target a copy waits for:
    `Transform` of the copy into a flat copy of the target's shapes, then the target itself in
    its place (so later actions find it) when both have as many shapes (same text / icon:
    glyphs glide), else Manim's `FadeTransform` (stretched cross-fade between boxes). `play()`
    fades out a copy whose destination is brought in another way (it is in the play's
    animations) or does not exist (warning). `carry_in(name)` hands the copy to custom code.
  - **Order of renders** (decision: B depends on A's artifact, not on recomputing A's end):
    `pipeline.with_carried` adds to any render list the scene before a carrying scene whose
    record is missing or has another fingerprint than A's current one, and a carrying scene
    whose `carry_from` is not A's current fingerprint when A is rendered; `_runs(after=)` makes a
    carrying scene's task wait for the scene before (thread events; the pool starts tasks in
    list order, so the awaited one has started: no deadlock). Works for `render` (with
    `--scene` / `--jobs`), `storyboard` and `lint` (all go through `_render_scenes`).
  - **Fingerprint**: A gains `next_carry` (what it keeps), B `carry` + `carry_from` (A's
    fingerprint, recursively), only when there are carries; a scene's own `carry` is left out of
    its config dump, so projects without carries keep their fingerprints (adding the
    `direction` / `soft` keys changes those of scenes with transitions once).
- **Example**: `examples/gallery`: `structure` (chapter) → `tradeoff` cut with `carry: ["title ->
  heading"]` (different words: a stretched cross-fade into the heading), `part2` → `speedup` cut
  with `carry: [icon]` (glides into the stat's icon), `schedule` `push`, `cost` `{wipe, right,
  soft}`.
- Known limits: carried objects are vector shapes only, in scene coordinates (a camera zoomed at
  the end of A is not undone); a push / wipe still blends pictures whose overlays were *chosen*
  per scene (the incoming scene's from the transition's start, like a crossfade); stills taken in
  a push / wipe's frames show no overlays (beat-end stills never are); `vidgen render --scene X`
  alone shows neither the slide nor the carry's partner (the join and the scene before do).


## 51. Refinements (Step 48, review 3: overlays, captions, audio, transitions)

- **Narration level**: `NarratedScene.narrate` adds a beat's MP3 through `scene.add_narration`,
  which decodes it (`sfx.decode_audio`, 48 kHz) and hands Manim a stereo WAV (`sfx.stereo`: a
  mono file at full level on both channels, as sound effects have always been). Given the MP3,
  Manim's `convert_audio` encoded it with PyAV's default stereo layout, i.e. libswresample's
  mono → stereo matrix at −3.01 dB per channel: every rendered video since Step 4 was 3 dB
  quieter than its MP3s (kphi3: −24.4 → now −21.4 LUFS integrated, true peak −2.2 dBTP). Clip
  sound (`clips.clip_audio`, FFmpeg `aformat` stereo) keeps the standard −3 dB upmix for mono
  clips; it is under the narration at a chosen `volume` anyway. Recalibrated: `MUSIC_LEVEL` −28
  LUFS (Step 45 had planned −28 and set −30 only to make up for the bug): ~6.5 dB under
  narration in pauses, ~18.5 dB when ducked; the SFX level (−27 LUFS loudest 400 ms) needs no
  change — it was calibrated on the MP3s and is now ~7 dB under the voice as stated.
- **Limiter margin** `mix.LIMITER_MARGIN_DB` 0.4 (was 0.1): the AAC encode raised the gallery's
  true peak 0.2 dB over the WAV's, past the −1.5 dBTP ceiling.
- **Scene lengths** (`ffmpeg.probe`): duration = frames / the stream's nominal rate
  (`guessed_rate`, `r_frame_rate`) instead of the average rate, which Manim's joined partial
  movies put off by a few 1/10000 (15.0003 for 15 fps): the join's starts drifted up to ~3 ms
  from the plan over the gallery (chapter start ≠ scene start) and each padded WAV was a few
  samples short of its video.
- **Overlays making way** (`Overlay.yields`, `clear_of`, `clear_area`; `overlays.build_overlays`
  used by `OverlayLayer`): yielding overlays are built after the others and know the boxes of
  those that reserve room; the built-in `lower_third` yields and, where it would come within the
  reserve gap of such a box (bottom captions in 9:16 *and* 16:9 when `align: bottom`), is placed
  again in `avoid(area, box)` — above the captions. Nothing moves when nothing is in its way.
  Decision: a class attribute on the overlay type (which one gives way is a property of the
  kind of overlay), not a priority number in the config.
- **Actions due with a camera move** (`Action.after_camera`; `callout` sets it): in a frame
  where a `moves_camera` action is due, after-camera actions are ordered last and get a batch of
  their own after it, so a callout written next to a `zoom` (same `at`) is built for the zoomed
  view (it was built for the camera before the zoom and then scaled with the scene).
- **Karaoke pop**: `captions.POP_ROOM` 0.25 of a space per side (was 0.45: the popped word
  nearly touched its neighbour in 9:16).
- **Not changed, documented**: `reserve` stays per scene (a layout is built once; a time-ranged
  reserve would mean re-laying out scenes mid-way) — several reserving overlays add up (the
  gallery's voiced clip in 16:9: captions + lower third + indicator + watermark leave the clip
  small). The SRT's / captions' first cue of a beat starts at the beat's start (not at the
  speech onset ~50–90 ms later), by design (`cues.caption_cues`). Joins with a crossfade, push
  or wipe re-encode the whole video: measured on the gallery preview (3:49, 854x480, 2 CPUs)
  ~40 s of a ~60 s join+mix, ~10 s of it decoding / filtering, the rest x264; stream-copying the
  parts between transitions would need re-encoded head / tail pieces whose H.264 parameters
  (SPS/PPS) match Manim's encoder for a concat copy, and Manim's keyframes fall at its
  partial-movie boundaries, not at the transitions — not robust enough for the gain (the
  scenes' own renders take 2–3x longer than the join).

## 52. Refinements (Step 49, chapters in the MP4 and a YouTube chapter list)

- **Config** (`config.py`): top-level `chapters: ChaptersConfig {metadata: true, youtube: true,
  intro: "Intro" | false}` and `metadata: MetadataConfig {title, artist, album, comment,
  description, copyright, date, genre}` (all optional text; `title` defaults to the video's
  `title`). Both are left out of scene fingerprints (they change no pixels and no timing).
- **Published chapters** (`chapter_export.py`): the list written to the outputs starts at 0:00.
  When the first chapter starts later (an opening title scene), `published_chapters` adds a
  chapter titled `chapters.intro` before it (`Chapter.intro = True`, `scene` = the first scene,
  no number, not a card), or with `intro: false` moves the first chapter's start to 0:00;
  `index` / `count` are renumbered in that list. A first chapter starting within 1 ms of 0
  counts as starting at 0. **Decision: the intro exists only in published lists.** Overlays
  (progress bar gaps, chapter indicator) keep the plain `VideoPlan.chapters` — an indicator saying
  "Intro" over a title card would be noise, and Step 39's runs, fades and reserves stay as they
  were. `video_chapters(project, fps, intro=True)` returns the published list from the plan
  (what `vidgen validate` checks).
- **Times in the outputs come from the join**, not from the plan: `joined_chapters(config,
  scenes, duration)` starts each chapter at its scene's start in the combined timings (the
  overlapped starts of §49: a crossfade / push / wipe into a chapter card starts the chapter where
  the transition starts) and ends the last at the joined duration. For scenes that keep to the
  plan (all built-ins; §51) they equal `video_chapters(..., intro=True)` exactly; for a scene
  that does not, the outputs follow the real video. Found while testing: at 5 fps a silent
  `chapter` card of 1.2 s plans 7 frames and renders 6 (`(duration - outro) x fps` = 3.5 frames:
  the plan rounds the tie up, the scene's waits end a frame shorter) — a half-frame tie only;
  routed to Step 60. The test uses 10 fps.
- **MP4** (`ffmpeg.join(..., metadata=)`): the pipeline writes `padded/metadata.txt`
  (FFMETADATA: global tags, then one `[CHAPTER]` per chapter with `TIMEBASE=1/1000`, `START` /
  `END` rounded to the millisecond, `END > START`, titles on one line; `\ = ; #` and newlines
  escaped) and the final mux adds it as the last input with `-map_metadata N -map_chapters N`.
  FFmpeg's MP4 muxer stores the chapters as a QuickTime chapter text track (a `bin_data` data
  stream in ffprobe) plus a Nero `chpl` list, which is what players read; ffprobe
  `-show_chapters` reads them back (tested: starts equal the plan within 1 ms). With
  `chapters.metadata: false` the file has no `[CHAPTER]` entries (tags still). The join now
  always maps metadata from this file (the concat demuxer's input tags are no longer copied;
  they were only FFmpeg's `encoder`, which the muxer writes anyway).
- **YouTube list** (`pipeline.write_chapter_list`): `<output>[_<variant>][_preview]_chapters.txt`
  (`Project.chapters_path`), one `M:SS Title` line per published chapter (`H:MM:SS` from an hour
  on), UTF-8. **Timestamps round down** to the second: a click lands at the chapter's first frame
  or before it, never after (rounding to nearest could skip up to half a second of a card).
  Rules checked (`youtube_problems`, on the rounded times, since that is what YouTube sees): at
  least 3 chapters, each ≥ 10 s (the first at 0:00 holds by construction); each broken rule is
  one warning starting `chapters:` naming the chapter, its span and a remedy (for a short intro:
  begin with a chapter or `intro: false`). The render logs them (so `render --json` lists them
  in `warnings`) and writes the file anyway; `vidgen validate` reports the same from the plan
  (`chapter_warnings`, part of `validate_warnings`). Without chapters, or with `youtube: false`,
  no file is written and an old one is removed (it would describe another video).
- **JSON**: combined `timings.json` gains `chapters` (published, `chapter_json`: the `Chapter`
  fields, times to 1 µs; also when both outputs are off); `render --json` gains top-level
  `chapters` (the same list) and `outputs.chapters` (the file or `null`); `post_render` hooks get
  `chapters` (the file or `None`); `RenderResult.chapters`. All within version 1.
- **Titles**: the chapter's title on one line (whitespace runs → one space), without its number
  (numbers are part of the on-screen design; "2 · Results" would read oddly in a menu next to
  the player's own numbering).
- Known limits: chapter titles are not translated per variant beyond what the variant's config
  says; a chapter's `number` is not shown in the outputs; YouTube also requires the list in the
  description to be the video's own (vidgen only writes the file); the MP4 has no chapter
  thumbnails.

## 53. Refinements (Step 50, thumbnail and GIF / clip export)

- **Config** (`config.py`): top-level `thumbnail: ThumbnailConfig | None` — a frame of a scene
  (`scene`, `beat` id or 1-based number, `at` seconds ≥ 0, `overlays` default true) or a designed
  card (`title` default the video's `title`, `subtitle`, `icon` | `image`, `preset`,
  `background`), plus `jpeg` (false) and `auto` (true). Frame and design keys together, frame keys
  without `scene`, `icon` with `image`: config errors; `VideoConfig.thumbnail_problems(thumb)`
  checks the scene and beat (also a beat on a silent scene); `vidgen validate` checks icon, image
  file, preset and colour token (`thumbnail.thumbnail_problems`, also run by `render`'s scene
  checks). `ThumbnailConfig()` (no section) = a designed card of the title. Out of scene
  fingerprints.
- **Size** (`thumbnail.thumbnail_size`): from the final `format`'s orientation (`scales.frame_orientation`):
  landscape 1280x720 (YouTube's recommendation), portrait 1080x1920 (Shorts / Reels covers),
  square 1080x1080. Every picture is cover-fitted (centre crop) to it with Lanczos.
- **Files**: `Project.thumbnail_path(preview, suffix)` = `<output>[_<variant>][_preview]_thumbnail.png`
  (and `.jpg`), the small copy `build/<render dir>/thumbnail/<name>_small.png` (long side
  `SMALL_LONG_SIDE` 320 px: YouTube's grid size, for the author — an AI agent opens it as an
  image). JPEG (`jpeg` / `--jpeg`): qualities 92 → 55 until ≤ 2 MB (YouTube's limit); without
  it an old JPEG is removed. Atomic writes.
- **Frame thumbnails** (`_frame_thumbnail`): the frame comes from the **scene's own render**
  (`scenes/<id>.mp4`), not from the joined video: a frame of a scene is the same with or without
  transitions, and it can be (re)made alone. `render_current` (format + fingerprint, §14) decides
  whether the scene is rendered first (`pipeline.render_scenes`, no join). Frame number
  (`frame_number`): a beat without `at` → its last frame, `round(start·fps) + round((end − start
  + pad)·fps) − 1`, capped by the next beat's first frame (the beat-end still of §13, computed
  from the timings instead of capturing stills, so a plain render is reused); `at` → `floor((beat
  start | 0) + at)·fps`; nothing → the last beat's end, or for a silent scene the frame before
  its fade-out (`duration − outro`, the scene type's `outro`); past the scene's end → error.
  Decoded with PyAV (exact frame, no seek rounding). From a render smaller than the thumbnail
  (e.g. `--preview`) an `info` check says it was scaled up.
- **Without overlays** (`overlays: false` / `--no-overlays`): overlays are composited inside the
  render (§41), so the picture without them needs another render. `Project.without_overlays()`
  is the project with `overlays: []` and every scene `overlays: false`, `bare = True`, whose
  `render_dir` is `build/<final|preview>[_<variant>]_bare`; the pipeline passes worker `--bare`,
  which does the same in the worker process. Its fingerprints differ (no overlay inputs), so the
  bare renders are reused while current; carries render the scene before into the bare folder
  too (`with_carried`). Decision: a separate folder rather than a flag on the normal render, so
  the normal renders (and the joined video) are never replaced by overlay-less ones. The scene
  lays out without the room reserving overlays take (the frame shows the scene as designed for
  a clean frame).
- **Designed thumbnails** (`design_thumbnail`, Pillow; the icon through Manim's Cairo camera as
  in `list-icons --sheet`, on the disc colour so no alpha is needed): in 16:9 the text on the
  left 58 %, the icon (on a `surface` disc, `primary`, ≥ 3:1 on the disc) or the image (a bleed
  panel) on the right; in 9:16 / square the visual on top (≈ 45 %), text centred below. Text
  sizes in units of the short side S (720 / 1080 px): margins 0.075 S; the title (font role
  `heading`, bold) the largest even size from 0.2 S down to 0.078 S whose balanced wrap
  (narrowest width keeping the line count) fits in 3 lines (4 in portrait) and the box; at the
  smallest size the rest is cut with `…` (`fit`). Then an accent bar (0.22 S x 0.016 S, theme
  `accent`), the subtitle (role `body`, 0.068 S, ≤ 2 lines). Colours: background = `background`
  (token / hex) or the theme's; title `text` unless below 4.5:1 there (then black / white, the
  stronger); subtitle the first of `highlight`, `primary`, `accent` ≥ 4.5:1, else the title's.
  `preset` uses `Theme.derive(ThemeConfig(preset=...))`: the preset alone, not the project's
  overrides (which would otherwise win over the preset). Fonts: the bundled file of the theme's
  family (`fonts.bundled_font_file`), else an installed font of that name, else
  `sheets.load_font`.
- **Checks** (`ThumbnailCheck(rule, severity, message)`, lint names where they mean the same):
  designed cards are measured at the small size (factor `320 / long side`): `min_font` title
  < 14 px / subtitle < 10 px (the title's minimum size 0.078 S is exactly 14 px small in both
  orientations), `contrast` < 4.5:1 (WCAG via `lint.color`), `fit`, `max_words` > 6 (info);
  all kinds: `file_size` > 2 MB, frame thumbnails `resolution` (info). A frame thumbnail's text
  is not measured (a plain render has no layout dump; `vidgen lint` checks scenes) — documented.
- **Render**: with `thumbnail:` and `auto`, `render_project` makes the thumbnail after the join,
  outside its extension session (a frame thumbnail may run `render_scenes`, which opens its own);
  the scene's render is current then, so nothing is rendered again unless `overlays: false`.
  Warnings are logged (`render --json` `warnings`); `RenderResult.thumbnail` (`ThumbnailResult`),
  `render --json` `outputs.thumbnail`, human `thumbnail:` line. Since Step 60 `post_render` runs
  after it (in a second extension session) with `thumbnail` (its path, else `None`) — §63.
- **`vidgen thumbnail`** (`cmd_thumbnail`): the config's thumbnail, or `--scene` (+ `--beat`
  id or number — a digit string is a number unless the scene has a beat of that id —, `--at`,
  `--no-overlays`) checked like the config; `--preview`, `--jpeg`, `--jobs`, `--json`
  (`jsonout.thumbnail_document`).
- **`vidgen export gif|clip`** (`export.py`): source = the joined video + `timings.json` of the
  render dir (error naming `vidgen render [--preview]` when missing; durations must agree within
  0.1 s). `resolve_range`: with `--scene` times from its start (default the whole scene, `end`
  kept within it — `start + duration`, so a transition out of it is included), else video times.
  Default path `exports/<output>[_<variant>][_preview]_<scene|video>[_<from>-<to|end>s].<gif|mp4>`;
  `--output` elsewhere. Decision: an `exports/` folder in the project (not next to the output) —
  shareable artefacts, many per video, easy to ignore in git (`**/exports/`, also in the init
  template's `.gitignore`).
  - **GIF**: one FFmpeg pass, `fps, scale=W:-1:flags=lanczos, split, palettegen=stats_mode=full,
    paletteuse=dither=sierra2_4a:diff_mode=rectangle` (`stats_mode=full`: explainer graphics are
    mostly still, one palette for all frames avoids colour pumping; `diff_mode=rectangle`: only
    changed areas are re-dithered, no shimmer, smaller files), `-loop 0`. Defaults: width 480
    (270 for 9:16), ≤ the video's; 12 fps, ≤ the video's. **Budget** `--max-mb`: `next_try` —
    size ≈ width² · fps, needed factor × 0.9 split as fps × factor^(1/3) (≥ 5 fps) and the width
    taking the rest (≥ 160 px); at most `MAX_ATTEMPTS` 6 encodes or until nothing can be lowered;
    still too big → warning (`within_budget: false`). Attempts listed in the JSON.
  - **Clip**: stream copy when the start lies within half a frame of a keyframe (PyAV demux,
    packets only) and neither `--width` nor `--fps` changes the picture: `-ss <keyframe> -i`,
    `-c:v copy -frames:v N` (`-t` alone let a copy run 2 frames long); with `--with-audio` the
    sound comes from a second input seeked to the same time and is encoded AAC 192k (copied AAC
    packets started up to a packet early: the clip opened with 0.15 s of sound before its first
    picture). Otherwise re-encoded (`libx264 -crf 18 -pix_fmt yuv420p`, accurate input seek,
    `scale=W:-2`, `fps=F`). Chapters dropped. A joined video without crossfades / pushes / wipes
    stream-copies the scenes, so scene starts are keyframes and `export clip --scene X` copies.
- Known limits: frame thumbnails are not checked for text size / contrast; a designed card has
  one layout (title + bar + subtitle + one visual) and no background image behind the text; the
  `_bare` render folder is not cleaned up; GIF budgets assume size ∝ width² · fps (static
  explainer frames compress better, so it can take a few encodes); in a re-encoded join
  (transitions) keyframes fall where x264 put them, so most clips of it are re-encoded.

## 54. Refinements (Step 51, multi-language variants)

- **`language`** (`config.LanguageTag`, top level, so per variant by deep merge): a BCP-47 tag
  (`^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$`) normalised (`pt-br` → `pt-BR`, scripts title case,
  regions upper case). `None` = the English rules and nothing sent: every project without the key
  behaves exactly as before. `vidgen/languages.py` (no manim): `LanguageRules(code, name,
  conjunctions, prepositions, clinging, words_per_second, silent_final_e, iso639_2)` for `en`
  (Step 40's lists), `pt`, `es`, `fr`, `de`, `it`; any other language gets a neutral set (no word
  lists, no word rate, ISO 639-2 from a small table). `language_matches(entry, video)`: subtag
  prefix match (`pt` ⊂ `pt-BR`; no language = `en`).
- **Cues** (`vidgen.cues`): `phrase_break_cost(before, after, language=None)` uses the language's
  lists; punctuation counts in every language (sentence ends incl. `。！？`, clause marks incl.
  `،、，；：`, a break before `¿ ¡ «` is a clause break). `segment_cues`, `split_cues`,
  `caption_cues`, `subtitles.split_text / beat_cues / cues_from_timings / write_srt` take
  `language` (the SRT uses the combined timings' `language` by default; the pipeline passes the
  project's); captions read `project.config.language`. `speech.syllables(word, language)`: the
  silent final `e` only in English and French; `estimate_word_times` / `beat_word_times` pass it.
- **Lint** `narration_speed`: `unit: auto | words | characters`, `min_rate` / `max_rate` now
  default `None` = the language's range (`NarrationSpeedRule.limits(language) -> (unit, min,
  max)`); auto uses words for languages with a word rate, else characters per second
  (`speech.spoken_characters`: letters and digits; 8-17/s). `SceneContext.language`.
  Decision: per-language word ranges rather than one character mode for all, so English results
  are unchanged and the familiar unit stays where it is meaningful.
- **ElevenLabs `language_code`**: `VoiceConfig.language_code` / `VoiceEntry.language_code` (`str |
  false | None`). `voices.resolve_voice` stores the code actually sent
  (`languages.elevenlabs_language_code`): the configured code, `false` → none, `None` (auto) → the
  video language's ISO 639-1 subtag for `LANGUAGE_CODE_MODELS` (`eleven_turbo_v2_5`,
  `eleven_flash_v2_5`; other models reject the field). The provider sends it in the body and
  inserts `language_code=<code>` into the §7 hash parts before the text only when it sends one
  (hashes without a code are unchanged; no legacy kphi3 hash then). `Project._audio_differs`
  compares resolved voices, so a variant whose code is sent gets its own audio folder.
- **MP4 / outputs**: `ffmpeg.join(..., language=<ISO 639-2>)` tags the audio stream
  (`-metadata:s:a:0 language=por`); the combined `timings.json` gains `language`. Per-variant
  SRT, chapter list and thumbnail are already separate files (§52, §53); they carry the
  language through their (translated) texts. No `language` tag in FFMETADATA (the MP4 muxer
  stores no global language).
- **Pronunciation**: `PronunciationEntry.language` (tag or list); `load_pronunciation` leaves out
  entries for other languages (`pronunciation.applies_to`). `translation.language_warnings`: a
  variant in another primary language that keeps base inline entries unchanged (and matching a
  beat) gets a validate warning.
- **Translation files** (`vidgen/translation.py`, no manim):
  - *Markers*: `TextMarker(kind)` in `Annotated` metadata (JSON Schema `x-vidgen-text: text|ref`);
    `TranslatableStr = Annotated[str, TRANSLATABLE]`, `TextRef = Annotated[str, TEXT_REF]` (in
    `vidgen.api`). Every built-in `Params` / action / overlay text field is marked (titles,
    headings, captions, labels, items, table cells, legend / axis names, units, notes, callout
    labels, a lower third's name / title, a watermark's text, chapter `number` text, stat
    separators); refs: `bar_chart` / `pie` / `icon_grid` `highlight` (+ `groups`), `heatmap` /
    `scatter` `highlight`, `timeline` `highlight` / `now`, `map` arc ends. Shorthands:
    `SceneParams.text_shorthand` (`{type: "text" | ("field", F) | ("after", SEP) | ("fields",
    names) | ("model", M)}`) and `text_defaults` (`{"label": "id"}`), read with `getattr` so any
    pydantic model may set them.
  - *Keys*: `parse_key` / `format_key` over `Seg(kind, value)`: `.name` (mapping key, or the id of
    an item of `scenes` / `beats` (default `<scene>_b<n>`) / top-level `overlays` (type /
    `<type><n>`)), `[n]`, `["key"]`, `{"key"}` (the key itself, last), `=field`, `$sep` (last).
    Beat texts are `scenes.<id>.beats.<id>.text`. `_Cursor` reads / writes the raw mapping by key;
    `=field` wraps a string as `{field: string}` (written back only when a field is added) and
    makes the next field default to it.
  - *Extraction* (`extract_texts(data, scene_model, action_model, overlay_model)`, needs the
    models; `project_texts(project)` inside a project session): top-level `title`, `metadata`
    title / album / comment / description, `chapters.intro`, `thumbnail` title / subtitle,
    overlay options, then per scene `chapter`, params (walked by the field types: unions pick the
    member that fits the raw value — marked `str` first; lists by their first item; dicts by the
    model whose fields cover most keys; aliases and header synonyms), beat texts, action options
    (canonical or shorthand form, `ActionConfig.resolved`'s rule) and scene overlay overrides.
    Only values present in the raw config are listed (defaults are not). References: `TextRef`
    values and action targets naming a params text of the scene (whole, after `kind:`, or before
    `@`) → that text's key.
  - *File*: `TranslationFile {version: 1, language, source_language, entries: {key:
    TranslationEntry {source, hash, text, stale, old_source, obsolete} | text}, references}`
    (extra keys forbidden, keys parsed); `source_hash` = sha1[:10] of the source. Written with a
    comment header by `dump_translation_file` (YAML, `allow_unicode`, insertion order).
  - *Applying* (`apply_translations(data, doc) -> (data, TranslationReport)`; registry-free):
    `Project.load` merges the variant, validates, and when the merged config has `translations:`
    applies the file to the **raw** mapping and validates again (`Project.source_data` /
    `source_config` keep the untranslated form, `Project.translation` the report). Texts first,
    mapping-key renames last, then references (`_renamed`: whole value, `kind:` suffix, `@`
    prefix). An entry is applied when it has a text and its `hash` (or `source`) matches the
    current text and it is not `stale`; else the source stays (`untranslated` / `stale` /
    `unknown` in the report). Text is used as written (no stripping: `" min"`), a YAML block's
    final line break dropped. A missing file is not an error (`missing`, a validate warning).
    Decision: **apply at load on the raw config**, so every consumer (TTS, audio hash and folder,
    SRT, captions, scenes, chapters, tags, thumbnail, lint, storyboard) sees one translated
    config with no special cases, and applying needs no scene types (keys are plain paths;
    what needed the models — which fields are text, which places are references — was resolved
    when the template was written). Decision: **stale translations are not used** (gettext's
    fuzzy rule): after a source edit the old text may say something else; validate lists them.
  - *Merging* (`merge_template`): (1) same key, same hash → kept (a hand-written entry without
    source / hash is kept and gets them); (2) the same hash under another key of the same scene →
    moved (an item inserted before it); (3) the key remains, source changed → `stale: true`,
    `old_source`, text kept; leftovers: translated → `obsolete: true`, untranslated → dropped.
    References are rewritten from the current config every run.
  - *Command* `vidgen translate-template [--variant] [--lang] [--output] [--json]`
    (`write_template` → `TemplateResult`): the file is the variant's `translations:` or
    `translations/<variant>.yaml`; the language is `--lang`, else the variant's own `language`;
    prints a hint when the config does not name the file yet. JSON: `translate_template_document`.
  - *Validate*: `translation_warnings` (texts showing the source, stale, unknown keys, references
    the file lacks or that broke, file language ≠ video language, missing file) and
    `language_warnings` join `validate_warnings`; human `language [pt]: pt-BR (file: N
    translated, M stale)`; `validate --json` `language` / `translations` at the top level and per
    variant (`jsonout.translation_json`).
- **Fingerprint**: `translations` excluded from the config part (the texts are in the scenes /
    config already); `translation.py` is not a render input; `languages.py` is (captions).
    `language` is in the config part. Renders made before Step 51 are stale once (new config keys
    in the dump).
- **Example**: `examples/minimal` variant `pt` (`pt-BR`, `translations/pt.yaml`: 54 of 73 texts
  translated — title, intro, steps, feedback, sizes, trend, outro; picture, saying, math,
  listing and note left in English on purpose; the variant's own pronunciation of LaTeX / JSON;
  captions). `vidgen lint` of the translated scenes: 0 findings (two Portuguese texts were
  shortened: 44 words on the bullets slide, 6.3 s of dead air in a longer beat).
- Known limits: a translation file only changes texts present in the config (a stat's default
  `decimal_mark` cannot be added); number formats and the map's country names are not
  localised; a map arc shorthand `"A -> B"`, `lint_ignore` object patterns and targets naming a
  translated point label (`point:<series>@<label>`) do not follow translations; languages
  without spaces are cut at punctuation only; the storyboard / lint labels of vidgen itself stay
  English.

## 55. Refinements (Step 52, slides export: HTML)

- **Key frames** (`vidgen/deck.py`, no manim; shared with the PDF deck of Step 53, §56):
  `deck_frames(project, *, preview=True, mode="beat"|"scene", per_beat=1, overlays=True,
  dedupe=True, jobs=1, force=False) -> Deck`. The stills are the §13 frame stills, made current
  the §14 way (`storyboard.stills_current` → `pipeline.render_scenes(..., frames=per_beat)` for
  the stale or missing scenes only), so a deck after `storyboard` / `lint` / `render --frames`
  renders nothing. `overlays=False` uses `Project.without_overlays()` (§53: `build/..._bare`).
  - `beat` (default): every still is a slide — one per beat (its last frame: for reveal-per-beat
    scenes the fully built state, so the deck "builds" like a presentation), N per beat with
    `per_beat`, a silent scene's still(s) before its fade-out. `scene`: the scene's last still,
    all its beats as notes (`per_beat` > 1 is an error there). Decision: **beat by default** —
    scenes whose content is replaced per beat (walkthroughs, derivations, screenshot steps,
    maps) lose everything but the last state in scene mode; dedupe keeps beat decks compact.
  - **Dedupe** (`stills_alike`): consecutive stills of one scene whose pictures (at most 320 px
    wide, box-filtered) differ in at most 0.05 % of their pixels by more than 24 levels on a
    channel are one slide: the later still (the more finished one), both beats' notes, the first
    one's start (`DeckSlide.merged` counts the stills). Never across scenes. Burned-in captions
    or a moving progress bar make beats differ, so with those overlays nothing merges.
  - `DeckSlide(index, scene, scene_type, scene_number, scene_title, chapter, still, beats, k, n,
    time, scene_time, at, until, merged)`; `notes` (the beats' texts, a blank line between: the
    configured text, translated by the variant's translation file at load, §54 — not the
    pronunciation); `alt_text()` (`"<type> scene “<title>”: <narration, ≤ 160 chars>"`, the
    title from `params` `title` / `heading` / `text` / `name` / `quote`). `DeckChapter(title,
    label, index)` from `chapters.chapter_marks` (no planned timeline needed). `time` = §14
    `scene_starts` (transition overlaps included) + the still's scene time.
  - **Deck timeline** (play mode): the scenes' rendered durations back to back (no overlaps,
    so every slide gets its full time); a slide is on from the still before it in its scene (0 for
    the first) to its own still, the scene's last slide to the scene's end. `DeckClip(beat, audio,
    at, duration)` for each beat with an MP3 in `project.audio_dir` (the file the render used; its
    speech `start` / `end` from the scene timings).
- **Page** (`vidgen/slides.py`): `make_slides(project, ..., image_format="webp", quality=80,
  max_width=None, audio=False, separate=False, output=None) -> SlidesResult` and
  `slides_html(deck, images, size, audio)`. Default path `slides_path` =
  `exports/<output>[_<variant>][_preview]_slides.html` (the §53 `exports/` folder). One HTML file:
  pictures as base64 `data:` URIs (Pillow: WebP `method=4`, JPEG optimised progressive, or PNG;
  Lanczos down to `max_width`), CSS / JS read from package data `data/slides/deck.css` /
  `deck.js` and inlined, the deck data as `<script type="application/json" id="deck-data">`
  (`</` escaped), the MP3s as `<audio>` data URIs with `--audio`. `separate`: pictures
  `slide-NNN.<ext>` and `<beat>.mp3` in `<name>_files/` (earlier `slide-*` / `*.mp3` there
  removed first), referenced relatively. Pages over 50 MB log a warning. Each picture appears
  once in the HTML; the overview and the notes' "next" preview copy its `src` at run time.
  Decision: **WebP q80** default (every current browser; ≈ 3x smaller than PNG for these flat
  graphics, text stays clean); JPEG for old viewers, PNG for exact pixels.
- **Behaviour** (`deck.js`, no libraries, ES5-compatible syntax): one `<section class="slide">`
  visible at a time (others `hidden`), the `<img>` `object-fit: contain` in a black stage
  (letterboxed at any window shape); keys → / ↓ / Space / PageDown / Enter next, ← / ↑ /
  Shift+Space / PageUp / Backspace previous, Home / End, digits + Enter jump (a "Go to N" box,
  Esc / timeout clears), S / N notes, O / G overview, F fullscreen (bars hide after 2.5 s idle),
  P / K play, ? / H help, Esc closes / stops; clicks on the stage's left third go back, else
  forward; horizontal swipes (> 50 px). URL hash `#N` (`history.replaceState`, `hashchange`
  followed). Notes panel: beside the stage (30 %), below it on screens ≤ 760 px or portrait,
  with the slide's meta line and the next slide; its state kept in `localStorage` (guarded).
  Overview: a dialog layer, buttons grouped under chapter headings. Accessibility: slides are
  `role="group"` `aria-roledescription="slide"`, alt text, a polite live region announcing
  "Slide N of M, <chapter — title>", visible focus rings, icon buttons with labels / titles;
  `prefers-reduced-motion` drops the 0.22 s fade. Print CSS: one slide per page.
- **Play mode**: a clock (`performance.now`) runs along the deck timeline; the slide shown is the
  last one whose `at` ≤ t; the clip whose span contains t plays, re-seeked when it drifts > 0.3 s;
  navigating while playing seeks to the slide's `at`; it stops at the end. Without `--audio` it is
  a timed slideshow at the video's pace. Decision: clock-driven rather than chained `ended`
  events, so silent scenes, beats without MP3s, pads and seeking all follow one rule.
- **CLI** `vidgen slides` (`cmd_slides`), `--json` (`jsonout.slides_document`: options, page,
  pictures, `duration`, `stills`, `merged`, `rendered` / `reused`, per slide `{index, scene, type,
  chapter, beats, notes, k, n, merged, time, scene_time, at, until, still}`). `deck.py` /
  `slides.py` are not render inputs (fingerprints unchanged).
- **Tests**: fake stills + stubbed rendering for selection, dedupe, timelines, translated notes,
  page structure (parsed; pictures decoded with Pillow), separate files, CLI / JSON; one render
  test; a Playwright (Chromium) smoke test of navigation, notes, overview, hash and play mode
  with sound (skipped without Playwright; Playwright is not a dependency).
- Known limits: no per-slide `--scene` selection; titles and help texts of the page are English
  (the notes and pictures follow the variant's language); the deck shows frames, not motion
  (animations, clips); a merged slide's notes are joined without saying where the picture
  changed; slides of a 9:16 video are tall (letterboxed on landscape screens).

## 56. Refinements (Step 53, slides export: PDF)

- **Command**: `vidgen slides --format pdf` (one command, two deck formats; `--format html` the
  default) rather than a separate `slides-pdf`: the frame options (`--variant`, `--preview` /
  `--final`, `--mode`, `--per-beat`, `--overlays`, `--no-dedupe`, `--jobs`, `--force`) and the
  picture options (`--image-format`, `--quality`, `--max-width`) are shared. HTML-only `--audio`
  / `--separate` with a PDF, and PDF-only `--notes` / `--title-page` / `--paper` with HTML, are
  errors (`cli._slides_options`, before loading). `--image-format` / `--quality` defaults now
  depend on the format (HTML webp q80, PDF jpeg q85), so the parser's defaults are `None`.
- **Library** (`vidgen/slides_pdf.py`): **fpdf2** as the optional extra `schu-video-generator[pdf]`
  (`fpdf2>=2.7.9`; also in `dev`, with `pypdf` for the tests). Decision: fpdf2 is pure Python
  (≈ 340 KB), embeds subsets of TrueType fonts with a ToUnicode map (extractable, searchable
  Unicode text — pt-BR accents), writes outlines, page labels, document info / XMP and alt text,
  and embeds JPEG files as they are (`DCTDecode`, no re-encode). Its dependency fontTools (~5 MB
  wheel with compiled speed-ups, pure-Python fallback) and LGPL-3.0 licence are why it is an
  extra, not a base dependency; vidgen does not bundle it. Without it, `make_slides_pdf` raises
  `VidgenError('... pip install "schu-video-generator[pdf]" ...')` before rendering anything. Alternatives
  rejected: cairo's PDF surface (already installed with Manim) cannot load a font file through
  pycairo (fontconfig / Windows system fonts only) — the bundled Inter would not be guaranteed;
  ReportLab is several times larger for what this needs. fontTools' INFO logging (subsetting steps) is set to
  WARNING when fpdf2 is imported.
- **Pages**: `make_slides_pdf(project, *, preview, mode, per_beat, overlays, dedupe, notes=False,
  title_page=False, paper="a4", image_format="jpeg", quality=85, max_width=None, output=None,
  jobs, force) -> PdfResult(path, bytes, pages, options: PdfOptions, width, height, bookmarks,
  thumbnail, deck)`; `write_pdf(deck, options)` builds it from a `Deck`. Default file `pdf_path`
  = `exports/<output>[_<variant>][_preview]_slides.pdf`, `_notes.pdf` with notes.
  - **Slide pages**: `slide_page_size` — the video's aspect ratio, the long side 960 pt (13.33 in,
    a widescreen presentation's page; 16:9 → 960 x 540, 9:16 → 540 x 960); the picture fills it.
  - **Notes pages** (`notes=True`): A4 595.28 x 841.89 / Letter 612 x 792 pt portrait, margins
    48 pt; header (chapter `label · title` left, bold; the video's title right; a rule), the
    picture full width (at most half the page high, centred: 9:16) with a hairline border, a
    meta line (`Slide N / M · <scene title> · <m:ss.s> in the video`, 9 pt), the narration of
    the slide's beats (`DeckBeat.text`: the configured, i.e. translated, text) as paragraphs at
    11.5 / 17 pt in Inter, left-aligned, footer `page / total` (fpdf2's `{nb}` alias). Long
    notes break onto further pages with the same header (auto page break only on notes pages).
    A silent scene says "No narration (a silent scene)." in italics.
  - **Title page** (`title_page=True`): the thumbnail `vidgen thumbnail` wrote
    (`Project.thumbnail_path`, this quality's, else the other's; not made here — a designed
    thumbnail would need the theme session and a frame thumbnail a render), full page on a
    slide-page deck; otherwise / on notes paper: (the thumbnail above) the title (`metadata.title`
    else `title`) bold, the thumbnail config's `subtitle`, `artist · date`, and on notes paper
    "N slides with speaker notes · m:ss of narration".
- **Outline**: the title page (its title), then chapters (`DeckChapter`: `label · title`) at
  level 0 with their slides (`N. <scene title or id>`) at level 1; slides before the first
  chapter at level 0. Each entry points at the slide's first page (added right after
  `add_page`, so a notes page continued over several pages is found at its start).
  `page_mode = USE_OUTLINES` opens the bookmarks panel.
- **Document info**: `/Title` (metadata title or title), `/Author` (`metadata.artist`),
  `/Subject` (`description`, else `comment`), `/Keywords` (`album`, `genre`), `/Creator`
  `vidgen <version>`, creation date (now, UTC), catalog `/Lang` (the video's `language`).
- **Pictures**: `slides.encode_still` (JPEG optimised progressive at `quality`, or PNG),
  scaled down to `max_width`; alt text = `DeckSlide.alt_text()`. Each picture once per PDF.
- **Fonts**: the bundled Inter Regular / Bold / Italic (§21) via `add_font`, subset-embedded.
  Characters Inter lacks (CJK, Arabic, Hebrew, Devanagari, emoji) are left out (fpdf2 warns);
  no fallback fonts (none bundled for those scripts).
- **JSON**: `jsonout.slides_pdf_document` — the `slides` document with `output_format: "pdf"`,
  `pages`, `notes`, `title_page`, `thumbnail`, `paper`, `bookmarks` (no `files_dir` / `audio`);
  the HTML document gains `output_format: "html"`. Per-slide entries are shared
  (`jsonout._deck_slides`). `slides_pdf.py` is not a render input.
- **Tests** (`tests/test_slides_pdf.py`, fake stills from `test_slides`, read back with pypdf):
  page count and sizes (16:9, 9:16, A4, Letter), JPEG embedded as `DCTDecode`, PNG as
  `FlateDecode`, outline tree and destinations (incl. notes continued over pages), document
  info and `/Lang`, notes / header / footer text extracted, fonts are Inter, pt-BR text with
  accents and typographic quotes extracted exactly, quality / max width shrink the file, option
  errors, missing fpdf2, CLI / JSON. Layout was checked by eye on `pdftoppm` renders of
  `examples/minimal` (title page with thumbnail, notes pages, the 9:16 variant, pt-BR notes) and
  `examples/gallery` (chapter headers, typeset title page).
- Known limits: the page's own words (`Slide`, `in the video`, `No narration`, `slides with
  speaker notes`) are English, like the HTML deck's; no theme colours on a typeset title page
  (white; the thumbnail gives a themed one); no per-slide `--scene` selection; no fallback font
  for scripts Inter lacks.

## 57. Refinements (Step 54, readback check: speech to text)

- **Purpose**: the AI author cannot listen. `vidgen readback` transcribes each beat's MP3 and
  compares the transcript with what the beat should say, so mispronounced terms, misread numbers
  and dropped / added words show up as text an agent can act on (a pronunciation entry, a
  regenerated beat).
- **Provider seam** (`vidgen.stt`, like §7's TTS seam): `STTProvider` protocol (`name`,
  `check_available()`, `transcribe(path) -> Transcript`); `Transcript(text, words:
  tuple[TranscriptWord(text, start, end)], language)` with `to_json` / `from_json`,
  `word_texts()` / `word_times()`; `get_stt_provider(project)`; `stt_settings(project) ->
  {provider, model, language}` (resolved defaults, no provider import: the cache and the lint
  rule use it). Constructing a provider loads nothing and needs no key.
  - `faster_whisper` (`stt/faster_whisper.py`, optional extra `schu-video-generator[stt]` =
    `faster-whisper>=1.0`; not in `dev`: ~70 MB of CTranslate2 / ONNX Runtime and a model
    download): `WhisperModel(model, device)` loaded on the first transcription, `transcribe(audio,
    language, beam_size=5, word_timestamps=True, condition_on_previous_text=False,
    vad_filter=False)` (each beat on its own, so one mistake cannot carry over; no VAD so quiet
    words are not cut). `audio` is the beat decoded by vidgen (`load_audio`: the ffmpeg
    executable via `render.ffmpeg.decode_mono(path, 16000)`, 1-D float32, since Step 141; PyAV
    before), not the path: faster-whisper's own decoder passes `metadata_errors`, which PyAV 19
    removed. Each word keeps its `probability` (§78). Missing package → `VidgenError('... pip install "schu-video-generator[stt]"')`; a model
    that cannot load (download refused, bad folder) → `VidgenError` naming the model.
  - `elevenlabs` (`stt/elevenlabs.py`): `POST /v1/speech-to-text`, multipart (`model_id`
    `scribe_v1`, `language_code` when known, `timestamps_granularity=word`,
    `tag_audio_events=false`, `file`), `ELEVENLABS_API_KEY` as for TTS. The TTS provider's
    retry / error / key-scrubbing loop moved to `tts.elevenlabs.post_with_retries` (shared; TTS
    behaviour unchanged). Only `type: word` entries of the response are words.
  - No OpenAI provider (the task's "openai?" was optional; the seam takes one more module).
- **Config** `stt: {provider: faster_whisper | elevenlabs, model, language, device}`
  (`SttConfig`): `model` default `small.en` for English / `small` otherwise (faster-whisper),
  `scribe_v1` (ElevenLabs); `language` default the video's language subtag (`en` without one),
  `auto` = detected (`None` sent); `device` `auto|cpu|cuda` (faster-whisper; not part of the cache
  key). `stt` is excluded from the render fingerprint; `stt/`, `readback.py`, `textnorm.py` are
  not render inputs.
- **Normaliser** (`vidgen.textnorm`, no manim): `normalize_words(words, language) ->
  [Token(text, source)]` (source = index of the input word, so differences map back),
  `normalize_text`, `fold` (casefold + accents removed: `você` = `voce`; STT accent slips are
  more common than accent-only minimal pairs), `number_words` / `english_number` /
  `portuguese_number`. Hyphens, dashes, slashes, `_` split words; apostrophes dropped inside
  words (`let's` → `lets`); numbers by the language's marks (en `1,000.5`, pt `1.000,5`), English
  decimals digit by digit (`one point zero eight`), Portuguese decimals as a number (`um vírgula
  cinquenta e sete`; digit by digit after a leading 0 or beyond 3 digits), `%` / currency symbols
  / English ordinals (`22nd`); other languages keep digits (canonical, group marks removed);
  `& + = × @` as words; dotted acronyms and runs of ≥ 2 single capitals joined (`G.P.U.`, `G P
  U` → `gpu`). The same function normalises both sides, so a convention only needs to be
  consistent, not linguistically perfect.
- **Comparison** (`vidgen.readback`): reference = the beat's **spoken** text (pronunciation
  applied, §45); `align(ref, hyp)` Levenshtein with ties broken towards more matches, then
  substitutions; `word_error_rate`. Ops are assigned to **written** words (spoken word → written
  word via `Spoken.word_groups()`; an insertion goes with the next word when that one differs
  too, else the previous one), and consecutive differing written words form one `Edit(kind,
  expected, heard, written, said, errors, at, after, term, entry, suggestion)`. An edit is dropped
  when its words are equal once joined (`overparameterized`, `KPhi3`) or when the heard words
  equal the normalised *written* words (the STT wrote `K-Phi-3` for "kay fye three"): these are
  writing differences. `errors` = non-equal ops of the block (S + D + I), so WER = Σ errors /
  normalised spoken words. `at` = start time of the first differing heard word.
- **Terms and suggestions**: `hard_term` (a digit, two capitals, a non-ASCII letter, or a
  capitalised word inside a sentence) marks a written word a pronunciation entry can fix; an edit
  over a replaced term has `entry: true`. Suggestions: entry → respell its spoken form; hard term
  → `add a pronunciation entry TERM: <how to say it>` (`<the number in words>` for digits);
  deletion → listen, `vidgen tts --force --beat ID`; insertion → listen; else a probable
  transcription slip. A stale MP3 (hash mismatch) adds "run `vidgen tts` first". `term_reports`
  aggregates terms over beats; `consistent` = heard differently in ≥ 2 beats (the strongest
  signal: one slip may be the transcriber's).
- **Flagging**: `wer > lint.rules.readback.max_wer` (default 0.1; `--max-wer` overrides). Below
  it, edits are still reported (JSON) and counted in terms. Exit code 0 whenever the command ran;
  the lint rule is the failing check.
- **Cache**: `build/readback/<sha1(json({audio: sha1(mp3), provider, model, language}))>.json`
  `{version 1, audio_sha1, stt, beat, transcript}`: content-addressed, so variants / qualities
  sharing audio share transcripts and a regenerated MP3 is transcribed again; `--force`
  re-transcribes. In `build/` (not `audio/`): derived, cheap to drop, never committed (kphi3's
  committed `audio/` stays untouched). The provider is created only when something must be
  transcribed (an all-cached run works without the extra or key).
- **CLI** `vidgen readback [PROJECT] [--variant] [--beat ID ...] [--max-wer RATE] [--force]
  [--json]`: progress `[n/N] transcribed <beat> (s)`, then `report_lines` (settings + counts,
  skipped beats, flagged beats with each edit `describe()` + `@ time` and `fix:` lines, worst
  beats, terms misheard in several beats). JSON `jsonout.readback_document` (version 1, new
  document): `project, variant, audio_dir, stt, max_wer, transcribed, cached, elapsed, summary
  {beats, flagged, words, errors, wer, worst}, beats[], skipped[], terms[]`.
- **Lint rule** `readback` (scope `scene`, default warning, `ReadbackRule{severity, max_wer}`,
  last in `LINT_RULES`): `SceneContext.readback` (beat id → `BeatReadback`) is filled by the
  runner from `readback.cached_readback` only when the rule runs and is not `off`; it never
  transcribes, so without `vidgen readback` it reports nothing ("off unless transcripts exist").
  The finding: `value` = WER, `limit` = `max_wer`, time = the beat's start, message quoting up to
  3 edits and the first suggestion, pointing to `vidgen readback --beat ID`.
- **Tests** (`tests/test_readback.py`, all mocked): number words (en / pt), digits in other
  languages, case / punctuation / hyphens / acronyms / pt-BR accents, alignment and WER, writing
  differences not counted, misheard pronunciation entry, terms without entry, insertions /
  deletions with times, pt-BR names, `hard_term`, settings defaults and config errors, a fake
  `faster_whisper` module (options, model loaded once, load error, missing package), ElevenLabs
  multipart request / response / errors with a mocked `urlopen`, the transcript cache (hits,
  `--force`, new audio, new settings), skipped / stale / unknown beats, the CLI (human + JSON,
  documented keys), the lint rule end to end on fake renders and as a unit, the fingerprint.
- **Known limits**: no real STT run was possible while building it (Hugging Face model downloads
  were refused by the build environment's proxy; see HANDOFF.md Step 54); number words only for
  English and Portuguese; English "and" inside spoken numbers ("two hundred and five") and years
  read in pairs ("twenty twenty-four") are not normalised; STT errors on ordinary words are
  reported as possible slips, not filtered.

## 58. Refinements (Step 55, generated images)

- **Purpose**: pictures for `image` scenes (and extension scene types) from a prompt, made once
  (they cost money), stored with the project and reused; the video can be previewed, laid out
  and linted before any picture exists.
- **Param** `GenerateImage` (`vidgen.imagegen`, exported by `vidgen.api`; a plain pydantic model,
  extra keys forbidden, a string = the prompt): `prompt` (required), `negative` (`""`), `style`
  (preset / words / `none`; default `imagegen.style`), `aspect` (`auto|landscape|portrait|square`),
  `seed` (≥ 0). The `image` scene's `path` became optional with `generate` beside it; exactly one is
  required (model validator). A scene type opts in by having a top-level field holding a
  `GenerateImage`; `find_images` discovers it through the registry (built-ins and extensions).
- **Config** `imagegen: {provider: openai, model: gpt-image-1, size: auto | WxH, quality, style,
  negative}` (`ImagegenConfig`). Part of the render fingerprint (it decides which picture or
  placeholder a scene shows); the pictures themselves are files under `assets/` (already tracked).
- **Request** (`image_request(project, generate) -> ImageRequest`): size = `imagegen.size`, or the
  model family's size for the aspect (`auto` = the final `format`'s orientation, so a 9:16 variant
  gets portrait pictures): gpt-image `1536x1024 / 1024x1536 / 1024x1024`, dall-e-3 `1792x1024 /
  1024x1792 / 1024x1024`, dall-e-2 `1024x1024`; quality default medium / standard / none. Text sent
  = `<prompt>. Style: <words>. Avoid: <negative; imagegen.negative>.` (OpenAI has no negative
  prompt). Style presets `photo, illustration, flat, isometric, watercolor, line_art, render_3d,
  cinematic` (`STYLE_PRESETS`). **Key** = sha1(json{v: 1, provider, model, size, quality, seed,
  prompt: text})[:16]; files `assets/generated/<key>.png` + `<key>.json` (`prompt, negative, style,
  sent_prompt, revised_prompt, provider, model, size, quality, seed, created (UTC date), scenes`).
  Content-addressed: no "stale" state; a changed request is "missing", the old file an orphan
  (reported, never deleted); equal requests share one file. Meant to be committed (like `audio/`).
- **Provider seam**: `ImageProvider` protocol (`name`, `check_credentials()`, `generate(request)
  -> GeneratedPicture(data: PNG bytes, revised_prompt)`), `get_image_provider(project)`. One
  provider: `OpenAIImageProvider` (`imagegen/openai.py`, stdlib urllib): `POST
  https://api.openai.com/v1/images/generations`, `Authorization: Bearer $OPENAI_API_KEY` (read at
  request time, never stored / logged / in errors), body `{model, prompt, n: 1, size, quality}` +
  `response_format: b64_json` for DALL·E models (gpt-image models always return base64); response
  `data[0].b64_json` (+ `revised_prompt`), non-PNG data converted with Pillow. Retries: 3 (backoff
  4 / 8 / 16 s or `Retry-After`, cap 60 s, timeout 240 s) on 429 / 5xx / timeouts — not on a 429
  for `insufficient_quota` / `billing_hard_limit`. The ElevenLabs loop moved to
  `vidgen.httpapi.post_with_retries(url, data, headers, service, secret, ..., transient=)`
  (`tts.elevenlabs.post_with_retries` keeps its signature and messages).
- **Placeholder** (`imagegen/placeholder.py`, Pillow): the request's aspect at long side 1280 px,
  surface → surface/primary gradient, rounded outline in dim, a picture glyph in primary, "IMAGE
  TO GENERATE", the prompt (wrapped, ≤ 6 lines, shrunk then cut) in text, "placeholder · run vidgen
  imagegen" in dim; the whole block centred so a `cover` fit crops margins, not text. Cached as
  `build/imagegen/<key>-<sha1(version, colours, font, size, prompt)[:10]>.png`.
  `generated_image(project, generate, theme)` returns the stored PNG or this placeholder.
- **Never a provider call outside `vidgen imagegen`**: `validate` warns (`imagegen_warnings`):
  pictures not made yet, and prompts that quote text or mention text words (text, words, letters,
  label, title, logo, slogan, says, written, font...) or charts / diagrams / tables, unless negated
  ("no text", "without lettering"); summary line `images: N generated, M missing` (and per variant
  whose pictures differ). `render` / `storyboard` log `generated image not made yet for <scenes>`.
- **CLI** `vidgen imagegen [PROJECT] [--dry-run] [--force] [--scene ID ...] [--variant NAME]`:
  distinct requests in video order; dry run prints each key, scenes, size, model, quality, cost
  estimate and the full prompt, then the total (`PRICES`: OpenAI list prices of 2025 per model /
  quality / square-or-not; unknown → "of unknown price"); a real run checks the key first, writes
  PNG + JSON atomically per picture, and on an error names the scene and how many were done.
  Orphans are listed (base config + all variants count as users).
- **Responsible use**: no content filter beyond the provider's (its refusals surface as errors);
  CONFIG.md asks not to generate misleading pictures of real people or brands.
- **Tests** (`tests/test_imagegen.py`, urlopen mocked): prompt composition, style / negative
  resolution, sizes per format / aspect / model, the cache key's inputs, text-in-prompt detection,
  `image` params (`path` xor `generate`), validate warnings and summary (+ variant), render
  warning, provider request / response / conversion / bad responses, 429 retry with Retry-After,
  timeouts, quota and 400 errors not retried with the key scrubbed, missing key, dry run without a
  key, generate / skip / force / `--scene`, orphans, an error midway, a stub provider, the
  placeholder card and its cache, the fingerprint, a render of the placeholder and of a stored
  picture (16:9 and 9:16).
- **Not done**: `generate:` on `screenshot` (its `px` callouts and magnifier need the real
  picture's pixels) and as a thumbnail background (designed thumbnails have no picture behind the
  text yet); no `--json` for `vidgen imagegen`; no image editing / variations endpoints; no second
  provider; prices are a snapshot. (Step 59 added `--json`; Step 61 the OpenRouter provider with
  looked-up prices, §64.)

## 59. Refinements (Step 56, the author guide for AI agents)

- **Two agent files, two audiences**: `CLAUDE.md` is for agents developing vidgen; `AGENTS.md`
  (repository root) is for agents **using** vidgen to make videos and decks. Each says so at its
  top and points to the other.
- **One source, shipped**: the guide is package data, `src/vidgen/data/guide/AGENTS.md`
  (`pyproject` package-data `data/guide/*`), so it is there after `pip install`; the root
  `AGENTS.md` is a byte-identical copy (a test fails when they differ). Not a render input
  (`guide.py` is in `NOT_RENDER_INPUTS`; the data folder is outside the source digest).
- **Topics**: each `##` section is introduced by a marker line `<!-- topic: NAME (also: ALIAS,
  ...) -->` (invisible when the Markdown is rendered). `vidgen.guide`: `GUIDE_FILE`,
  `GuideTopic(name, title, aliases, text)`, `guide_text()` (markers removed), `guide_topics()`,
  `find_topic(name)` (name or alias, case-insensitive; unknown → `VidgenError` with
  did-you-mean and the topic list), `topic_lines()`. Topics: `start`, `workflow`, `pacing`,
  `social`, `scenes`, `design`, `actions`, `cartoons` (Step 85, §69.18), `overlays`, `audio`,
  `examples`, `outputs`, `troubleshooting`.
- **CLI** `vidgen guide [TOPIC] [--list] [--json]`: the whole guide, one topic, or the list
  (`TOPIC` with `--list` is an error). No PROJECT argument (the guide does not depend on one).
  `--json` (in `JSON_COMMANDS`): `{topic, title, topics: [{name, title, aliases}], text, path}`.
- **Kept true by tests** (`tests/test_guide.py`): every `vidgen <command>` in a code span or
  block exists, with every `--option` written after it; the scene chooser table covers every
  built-in type, its params column names real params (or their `title` / `heading` synonyms);
  every type has a snippet; the presets, actions and lint-rule tables list exactly the
  built-in ones; every sound and music bed is named; and every fenced `yaml` block, wrapped
  into a config (a scene list, a partial config, or top-level keys plus one scene; files under
  `assets/` copied from the examples), passes `vidgen validate`'s checks (`validate_all`).

## 60. Refinements (Step 57, scene gallery)

- **`vidgen gallery [PROJECT] [--output DIR] [--types T,T] [--formats 16:9,9:16] [--theme PRESET]
  [--clips | --no-clips] [--jobs N] [--force] [--json]`** (`vidgen.gallery.make_gallery`): every
  registered scene type rendered from one canonical sample at 16:9 and 9:16 into a Markdown
  gallery, default `docs/gallery` (committed in this repository). `PROJECT` (or a config file in
  the current folder) adds the project's own types, its theme (unless `--theme`) and extensions.
- **Samples: one source.** A built-in type's sample is its snippet in the guide's `scenes` topic
  (`guide_samples()`: the yaml blocks are split into list items, keeping the text as written; the
  first of a type, a later one replacing a `generate:` snippet that only renders a placeholder);
  the block's first comment line (`# data`) is the index group, the chooser table's first column
  the "use it for" line (`chooser_uses()`). A project's type takes its first scene in
  `video.yaml` (`project_samples()`, YAML dumped). A name whose class is registered under an
  earlier name (`flowchart` → `diagram`) is an alias: listed, not rendered (`GalleryType.alias_of`).
  Files under `assets/` in the guide's snippets map to stand-ins shipped in `data/gallery/`
  (`sample_asset()`: `picture.png` for `image`, `app.png` for other pictures, `clip.webm` for
  videos — made by `tools/make_gallery_clip.py` from `app.png`).
- **Work project** `<project or .>/build/gallery/video.yaml`: every sample (id = type name),
  preview 640x360 @ 12 fps, variant `portrait` 360x640; always all samples and files, so a
  `--types` run does not make the others' fingerprints stale (they see the config and `assets/`).
  Rendered with `render_scenes(..., frames=1)`; current stills are reused (`stills_current`). The
  "audio missing" warning is filtered (samples have no audio by design).
- **Media**: the last still of each scene saved as an optimised PNG (`media/<type>-16x9.png`,
  `-9x16.png`; 640x360 / 360x640); a GIF of the scene up to its last beat's end (no fade-out:
  full-frame changes cost the most bytes), 320 / 180 px wide, 6 fps, 32-colour palette without
  dithering (flat graphics), last frame held 1.5 s (`export.write_gif(..., colors, dither, hold)`,
  shared with `vidgen export gif`). Deterministic: no times or paths in the pages, Pillow and
  FFmpeg outputs are reproducible for the same inputs and versions, and render workers now run
  with `PYTHONHASHSEED=0` (unless set): with a random per-process seed, frames during a camera
  move (zoom actions, focus steps) differed by a few pixel values between two renders, so their
  GIFs changed on every regeneration. Checked: two `--force` regenerations give byte-identical
  files except `screenshot-9x16.gif` (the picture's sub-pixel edges while the camera moves over
  an image differ between renders; not tracked down, the frames look the same); a regeneration
  that reuses the renders is byte-identical.
- **Pages**: `README.md` (by group: type, stills linked to the page, use; aliases "same type as";
  types without a sample "no sample", types without a page in the folder "not rendered here
  yet"; a project type's "use" is the first sentence of its docstring) and `<type>.md` (use, description = first paragraph of
  the class / module docstring, stills, GIF links, the YAML as written, a params table from the
  `Params` model with nested fields as `a.b`, targets, beat count). An index after a `--types`
  run still lists every type, with whatever stills the folder has.
- **What is committed** (decision): the pages, all stills and all GIFs, about 4.4 MB in total (1.3 MB stills, 3.1 MB GIFs), under
  a tested 8 MB budget (`tests/test_gallery.py`): humans browsing GitHub and agents reading the
  docs see every type without rendering; clips are small enough at 320 px / 6 fps / 32 colours (a regenerated GIF adds to the history, so they stay small). A test
  keeps every page's YAML equal to the guide's current snippet and the index listing every type.
- **Routed visual fixes** (Steps 37 and 56):
  - `map`: a regional view in a vertical frame is narrowed to the longitudes that fill the frame
    at the view's latitudes, around its items (`_portrait_region`; before, the frame was filled
    by growing the view north and south: `europe` showed mostly Africa, Europe tiny). Country
    labels that need a leader avoid crossing earlier leaders and labels, and a label must not
    stand nearer another labelled place (any step) than its own (`_misleading`); when the first
    spot fails, `_clear_spot` searches eight directions out to 3 units (the empty bands above and
    below the map in 9:16).
  - `screenshot` / `video_clip`: `steps[].focus` defaults to auto (`None`): `true` in a vertical
    frame for a landscape picture (≥ 1.2:1), else `false`; a focus view taller / wider than the
    picture is centred on it, a smaller one stays on it. `video_clip` `fit: auto` (new default):
    `contain`, but a landscape clip without callouts in a vertical frame (not `bleed`) is shown
    as a nearly square part from its middle (`cover` into a square room, less the layout's 10 %
    vertical inset).
  - Callout labels (`kind: label`): `label_spot` gained `clearance` (soft distance from `avoid`),
    `rivals` (a spot clearly nearer — under 0.75x the own distance — another bar, value or the
    title than its target is penalised and counts as blocked) and `straight` (above / below /
    beside before the corners); `side` is now honoured only while a spot on that side is clear,
    else the best clear spot elsewhere is used (also for arrows and magnifiers with `side`).
  - Lint rule **`label_spacing`** (warning, `min_gap` 0.02 of the shorter side): a label on its
    own plate (filled rounded shape without an outline — an outlined badge such as the
    timeline's "Now" tag sits in its line by design —, not the background colour, behind exactly one text, at most
    2.2x its height and 3 heights wider; the text's backdrop is the plate) closer than `min_gap`
    to another text (not lone symbols, not the text framed by an outline in the plate's colour:
    the callout's own mark). `text_overlap` / `covered_text` missed these (no overlap, no
    cover). A `box` / `circle` tag (`tag_spot`) gets the same soft `clearance` (0.2 units) and
    the same spots one clearance further out.

## 61. Refinements (Step 58, `vidgen plan`)

- **`vidgen plan INPUT [--output DIR|FILE] [--title] [--format 16:9|9:16] [--preset] [--language]
  [--force] [--json]`**: a draft project from a Markdown outline or a plain-text script. **No LLM
  and no network**: deterministic heuristics, so the same input gives byte-identical output (no
  times, no absolute paths in the file). The draft is scaffolding for an agent, which is why every
  decision is written down as a `# plan:` comment and every doubt as a `# TODO:`.
- **Pipeline** (all without manim): `outline.parse_outline(text, plain)` → blocks (`Heading`,
  `Paragraph` (lines kept, joined by newlines), `ListBlock` of `ListItem(text, children)`, `Table`,
  `Code`, `Math(formulas)`, `Image`, `Quote(text, author, source)`); `outline.plain()` removes
  inline Markdown and collects links. `plan.make_plan(blocks, PlanOptions)` → `Plan(title, scenes:
  [PlannedScene(id, type, params, beats, duration, reason, todos)], language, chapters, assets,
  notes)`. `plan_yaml.plan_yaml(plan, fmt, preset, source)` → the commented text;
  `plan_yaml.write_plan(...)` → `PlanResult(root, config, assets, created)`; the CLI then loads and
  validates the draft (`validate_all`) and reports.
- **Structure**: a single leading H1 is the title; the highest remaining heading level makes
  sections, the next one units (a unit = heading + blocks → scenes); deeper headings and short
  `Label:` lines label the next block (comparison columns). Chapters: estimated narration over
  `CHAPTER_SECONDS` (120) and ≥ 3 sections → a silent `chapter` card (2.5 s) before each
  section's first scene + `overlays: [{type: progress_bar}]` (the guide's rule). The last unit is
  the closing one when it (or its section) is called Summary / Conclusion / Recap / Takeaways /
  Next steps (en, pt, es, de, it, fr words): its last prose beat narrates an `end_card` whose
  `lines` are the unit's links (scheme stripped).
- **Prose to beats** (`prose.py`): `split_sentences` (end marks before a capital / digit /
  opening mark; `LanguageRules.abbreviations` — a new field, per language — and initials never end
  one; `etc.` / `usw.` / `ecc.` before a capital do); `split_long` (a DP over cut points: break
  cost `cues.phrase_break_cost` of the language + 0.04 x (piece − 10)²; pieces ≥ 4 words);
  `merge_short` (a DP grouping consecutive pieces: ≤ 15 words unless already one piece, nearest
  10, +4 per word under 6). Scenes that reveal steps get one beat per step (`_Planner.fit`):
  sentences as written first (so "one sentence per item" survives), then merged; the sentences
  after the block as the steps' when they count right (those before = intro); then a match by
  shared content-word stems (first 5 letters, in order); then the items' own sentences; then the
  beats as they are (TODO when more than one extra beat); placeholders last (TODO). An intro of
  one sentence joins beat 1 when the two stay ≤ 18 words, else becomes prose scenes before.
- **Compression** (`prose.compress(text, max_words, language)`): parentheses out; `head: tail`
  keeps the head (or the tail after a generic lead: Step / Tip / Passo...); leading filler
  phrases and filler words (en, pt lists) out; over the limit: cut at the first comma (the main
  clause when the head starts with a conjunction / preposition: "On a miss, query the database"),
  then articles out, then truncate; a cut label never ends on a clinging word, conjunction,
  preposition, auxiliary or quantifier. Limits: heading 5, item 6, label 3 (stages, chart labels,
  nodes, comparison headings), title / card 7, comparison points 4.
- **Cue rules** (first match): dated items (all) → `timeline`; numbered 2–8 → `process`;
  unordered 2–12 nouns ≤ 3 words with a distinct icon each (`icons.match_icon`, score ≤ 3: name,
  name prefix / alias, a word of the name / alias, an exact tag; then the label's words, longest
  first, and their singular) → `icon_grid`; else `bullets` (`numbered`, `dim_previous` over 5).
  Two-column table with all second cells numeric (`$`, unit, `%`) and 2–12 rows → `bar_chart`
  (common unit, `value_format` for a currency, `highlight` = the label the last of 2+ beats names,
  a beat per change from the raw sentences); else `table` (`reveal: all` when the prose has
  fewer sentences than rows). Code ≤ 15 lines → `code` (highlight per blank-line block per
  beat), else `code_walkthrough` (2–6 steps from the blocks / beats). Math: 1–2 formulas →
  `equation`, ≥ 3 → `equation_derivation`. Image → copied into `assets/` (name de-duplicated),
  else `generate:` its alt text. Quote → `quote` (≤ 2 beats). A paragraph made only of arrow
  chains → `diagram`. Comparison: an "A vs B" / "A x B" / "A or B?" heading with two lists, or a
  `Pros:` and a `Cons:` list (tones positive / negative, no `vs` badge), or a vs heading over
  prose (points from the sentences naming one side only). Prose: a beat with a prominent number
  (`%`, `x` / times, currency with magnitude, "N million", "from X to Y" → `comparison: {kind:
  before}`; pt / es / fr / de / it read `3,5` and set `decimal_mark`) → `stat` with one beat (two
  with a comparison: beat 2 reveals it; a second beat without one was lint `dead_air`); else
  `bullets` of compressed beats (≤ 5, a lone leftover joins) or a `text_card` for one beat. An
  opening beat with a number becomes the hook `stat` before the `title`.
- **YAML writer**: hand-written so comments sit above each scene; flow style for short scalar
  lists and small mappings (≤ 96 characters), block style for beats (`- text: "..."`), literal
  blocks for code (`|2-` when the first line is indented); strings plain only when word-like and
  not a YAML 1.1 keyword, single-quoted when they hold backslashes (LaTeX), else JSON-quoted;
  floats with a mantissa dot. The text is checked to load back to exactly `plan_config(plan)`.
- **Decisions**: the example `examples/plan/video.yaml` is committed as a golden file (a test
  regenerates it), unedited, so the README / guide can point at what a draft looks like; its
  `vidgen lint` has 1 finding (see Step 58 in HANDOFF). `vidgen init`'s scaffolding is now
  `cli.scaffold_project(target, example)` (shared). `--output` defaults to a folder named after
  the input in the current folder (like `vidgen init NAME`). A draft with validate problems is
  still written (exit code 1, `ok` false) — it should never happen and the agent needs the file
  to fix it. The new modules are not render inputs (fingerprint); `languages.py` and `icons.py`
  changed, so render fingerprints change once.

## 62. Refinements (Step 59, MCP server)

- **`vidgen mcp [--root DIR]`** (and the console script `vidgen-mcp`): a Model Context Protocol
  server on stdio, optional extra `schu-video-generator[mcp]` = the official MCP Python SDK (`mcp>=1.19`).
  Written against SDK 2.x's `MCPServer` (`mcp.server.mcpserver`); with a 1.x SDK it uses
  `FastMCP` (the same decorator API; 1.19 is the first that passes a returned `CallToolResult`
  through). Results are built as `CallToolResult.model_validate({...camelCase wire names...})`,
  which both generations accept. Without the SDK, `vidgen mcp` is a `VidgenError` naming the
  extra.
- **Tools** (`mcp_server.build_server`): `guide`, `init`, `plan`, `validate`, `schema`,
  `list_scenes`, `list_icons`, `list_themes`, `list_sfx`, `list_music`, `storyboard`, `lint`,
  `render`, `tts`, `imagegen`, `readback`, `slides`, `thumbnail`, `export`, `gallery`,
  `translate_template`; Step 83 adds `character_sheet` (§69.16), Step 90 `direct` (§69.24), Step 91
  `screenplay` (§69.25; `input_path` or `screenplay_text`, `out`, `cast` (§69.35), `species`, `seed`
  (§69.49), `force`), Step 115 `cast` (§69.49; `count`, `seed`, `species`, `out`, `provider`,
  `narrator`, `model`, `force`). Parameters mirror the command's options (snake_case; lists for repeatable
  options), with pydantic `Field` descriptions and bounds. Result: one text block with the
  command's `--json` document re-serialised compactly (fewer tokens), then images; a document with
  `ok` false is an `isError` result holding only the JSON. Argument errors (path outside the root,
  missing cost confirmation) are SDK `ToolError`s. Tool annotations: read-only for guide / list /
  schema / validate, open-world for tts / imagegen / readback.
- **Process model: a fresh subprocess per call** (`run_vidgen`: `sys.executable -m vidgen
  <command> ... --json`, cwd = root, stdin = devnull, list arguments). Why not in-process: Manim's
  `config` and vidgen's registries / runtime context are process-global and not re-entrant
  (render already uses worker processes for that reason); a long-lived server must survive a
  crashing scene, extension or native library; the CLI's JSON mode already guarantees exactly
  one document on stdout with everything else on stderr. Cost: ~1 s of interpreter + import per
  call, negligible next to rendering. stdout is collected whole; stderr is split into lines (on
  `\n` and `\r`), kept as a 30-line tail (shown when a command prints no JSON) and forwarded as
  `ctx.report_progress(n, None, line)` at most every 0.5 s (no-op when the client sent no
  progress token). Cancellation kills the process — its whole process group on POSIX
  (`start_new_session`), so render workers go too. Rendering tools (storyboard, lint, render,
  tts, imagegen, readback, slides, thumbnail, export, gallery) hold one `anyio.Lock`: they share
  build folders and CPUs; listing / checking tools run concurrently.
- **Root policy** (`mcp_tools.RootPolicy`): every path argument is resolved (`Path.resolve`, so
  `..` and symbolic links are followed) against the root and must be the root or under it
  (`PathOutsideRoot`, a `VidgenError`). Option values are passed as `--name=value` so a value
  starting with `-` is never read as an option; positionals are resolved absolute paths or
  checked names (no leading `-`). Pictures are only returned from inside the root. Files the
  server asks for itself go to `build/mcp/` (icon sheet, swatches, gallery: `build/mcp/gallery`,
  no GIFs). Files a project's own `video.yaml` names are confined too since Step 60 (§63:
  `VIDGEN_CONFINE_ROOT`).
- **Secrets**: the subprocess inherits the server's environment (API keys are needed by tts /
  imagegen / readback); nothing returned contains environment values (documents hold paths and
  results; provider errors were already scrubbed of keys, §58).
- **Cost guard**: `tts` and `imagegen` default to `dry_run=True`; `dry_run=False` without
  `confirm_cost=True` is refused before any process starts (`mcp_tools.cost_refusal` tells the
  agent to show the dry run to the user first). `readback` asks for `confirm_cost` when the
  project's `stt.provider` (loaded in-process with `Project.load`, which imports no Manim) is in
  `PAID_STT` (`elevenlabs`).
- **Pictures** (`mcp_tools.prepare_picture`): scaled to ≤ 1568 px on the long side (Claude's
  vision limit; larger costs tokens and is downscaled by the client anyway), PNG unless over
  800 KB, then JPEG q85. `page_of`: `images` (default 3, ≤ 8) from `image_offset`; the document
  gets `mcp_images: {total, offset, returned, next_offset}`. Storyboard sheets are ordered
  whole-video first, then per scene.
- **Agent-friendly defaults** that differ from the CLI: `render`, `thumbnail`, `export` preview by
  default; `gallery` writes `build/mcp/gallery` without clips; `plan` takes `markdown_text` (written
  to a temporary file outside the root; pictures it names are not copied) as well as
  `input_path`; `validate` has no `variant` (it checks every variant); `schema` refuses to return
  the whole schema (~370 KB compact, ~100k tokens: over most clients' tool-output limits) unless
  `full=true` / `all_types=true` — `scene=TYPE` (~6 KB) is what an agent needs.
- **Resources**: `vidgen://guide`, `vidgen://guide/<topic>` (static, one per topic, read
  in-process), `vidgen://schema` (a `vidgen schema --json` subprocess in the root), and
  `vidgen://gallery/index` / `vidgen://gallery/<type>` for `docs/gallery/*.md` under the root
  when present (the repository's gallery; not shipped in the wheel).
- **JSON gaps closed** (every wrapped command has a JSON mode): `vidgen init --json`
  (`{project, config_file, example}`), `vidgen tts --json` (dry run and run: beats with action
  generate / copy, voice, characters, spoken text; characters per voice; generated, up to date,
  orphaned), `vidgen imagegen --json` (pictures with prompt, sent prompt, size, model, estimated
  cost; totals and price note; generated, up to date, orphaned), `validate --json` `images`
  (`jsonout.images_json`, per config whose pictures differ, from `cli.variant_images`, which the
  human summary uses too). Human `vidgen validate` now checks every variant even when one does
  not load (`validate_all(keep_going=True)`), so its error lists them all (`[variant NAME]`
  lines, like the JSON problems).
- `mcp_server.py` and `mcp_tools.py` are not render inputs (fingerprint).

## 63. Refinements (Step 60, final review; version 0.2.0)

- **Incremental `vidgen render`**: `render_project(..., force=False)` renders only the scenes for
  which `pipeline.current_render` is false — no usable render (`_usable_render`: format, audio
  mode, `--frames` stills) or a recorded `render.fingerprint` that differs from
  `scene_fingerprint` now (§14) — and reuses the others (`RenderResult.reused`, `render --json`
  scene `status: reused`). `--force` (CLI, MCP `render` `force`) renders every scene; `--scene`
  keeps its meaning (those scenes, plus the ones without a usable render). Continuity
  (`with_carried`) and the `pre_render` hook apply as before. A render after a storyboard / lint
  of the same format joins only, and keeps their stills and layout dumps. Files a scene reads
  outside `assets/` are not tracked (as for the storyboard): `--force`.
- **Silent scenes render exactly their planned frames**: `NarratedScene.timeline()` waits to
  `round(d * fps)` frames from its start and `hold()` to `round(target * fps)` frames, the same
  rounding as `VideoPlan` (whose silent part is now `max(duration - outro, 1 / fps)`, as the
  scene's). Before, rounding the remainder after a step could lose a frame on a half frame (5 fps,
  a 1.2 s `chapter` card: plan 7 frames, render 6).
- **`code` highlight band**: `scenes.code.readable_band` picks the strongest band opacity of
  `BAND_OPACITIES` (0.2, 0.16, 0.12, 0.1) at which every syntax colour keeps `INK_RATIO` (4.6:1)
  over the window and the band; below the last one the colours that fall short are mixed towards
  the theme's `text` (as `code_walkthrough` does). GitHub-dark's keyword red on dark_tech's band
  was 4.15:1 (lint `contrast` on `examples/plan`).
- **Mono clip sound** (`clips.clip_audio`): a mono stream is panned to both channels at full level
  (`pan=stereo|c0=c0|c1=c0`) instead of FFmpeg's −3 dB upmix, like the narration (§51).
  `ClipInfo.channels` (0 when unknown) added.
- **`post_render` after the thumbnail**: with a `thumbnail:` config the hook is dispatched after
  `make_thumbnail`, in a second extension session (the thumbnail must run outside the first, a
  frame thumbnail may render); hook data gains `thumbnail` (`Path | None`, also `None` without a
  thumbnail).
- **Config files confined under MCP**: `Project.load` checks, when `VIDGEN_CONFINE_ROOT`
  (`project.CONFINE_ENV`) is set, that every string under a `PATH_KEYS` key anywhere in the raw
  config (variants included: `path`, `logo`, `image`, `source`, `pronunciation_file`,
  `translations`, `extensions`, `output_dir` since Step 66, `svg` since Step 102; and the `.pt` parts of a
  Kokoro `voice`, against the project folder and the current folder) resolves (links followed) inside that folder
  (`confinement_problems`); else a `VidgenError` "files outside the allowed folder". The MCP
  server sets it to its root for every command it runs. Non-path values under those keys (a
  quote's `source`, a music bed name) resolve inside the folder and pass.
- **MCP cancel on Windows**: `_kill` runs `taskkill /F /T` (the process tree: render workers).
- **`vidgen plan`**: a stat whose number comes right before one or two words ("40x faster") is
  labelled "faster with a cache" (the English subject before its verb, not a pronoun); a number
  ending a range ("between 20 and 80 percent") is not a stat; bare web addresses
  (`batteryuniversity.com`, `www.x.org/docs`) are links (`outline._DOMAIN`, end card `lines`);
  placeholder beats of `process` / `bullets` steps say the whole item, not the label cut from it.
- **CLI consistency**: `translate-template --language` (alias of `--lang`, as `plan --language`;
  MCP `translate_template` parameter renamed `language`); `init` suggests the storyboard / lint
  loop.
- **Packaging**: version 0.2.0; PEP 639 metadata (`license = "MIT"`, `license-files` with
  `THIRD_PARTY_NOTICES.md`; build needs setuptools ≥ 77); `data/geo/LICENSE` carries the ISC / MIT
  notices of the map data in the wheel. Wheel ~2.0 MB (fonts 2.0 MB of it), sdist ~2.2 MB.

## 64. Refinements (Step 61, OpenRouter image provider)

- **API facts** (OpenRouter's OpenAPI spec `https://openrouter.ai/openapi.yaml`, its image
  generation guide and the public endpoints, checked 2026-10-08). Base `https://openrouter.ai/api/v1`.
  - `POST /images` (`createImages`): body `{model, prompt}` required; optional `n` (1–10),
    `aspect_ratio` (`1:1 1:2 1:4 1:8 2:1 2:3 2.35:1 3:2 3:4 4:1 4:3 4:5 5:2 5:4 5:7 7:5 8:1 9:16
    16:9 9:19.5 19.5:9 9:20 20:9 9:21 21:9 auto`; "providers clamp to their supported subset"),
    `resolution` (`512 768 1K 1.5K 2K 4K`), `size` (a tier or explicit `WxH`; explicit pixels are
    authoritative and a mismatched `resolution` / `aspect_ratio` is a 400), `quality` (`auto low
    medium high xhigh max`; ignored by providers without it), `seed`, `output_format` (`png jpeg
    webp svg`; svg only for vectorisation models, UTF-8 SVG base64 in `b64_json`), `background`,
    `output_compression`, `input_references` (image to image), `provider` (routing), `stream`
    (OpenAI-backed models only), `user`, `session_id`, `trace`. Response `{created, data:
    [{b64_json, media_type?}], usage?: {prompt_tokens, completion_tokens, total_tokens, cost}}` —
    always base64, never a URL; `cost` in US dollars when available. Errors `{error: {code,
    message}}` with 400, 401, 402 (insufficient credits), 403, 404, 413, 429, 500, 502 (provider
    error; a generation that does not complete is a 502 and not billed), 524 (edge timeout), 529
    (provider overloaded).
  - `GET /images/models` (public, no key): `{data: [{id, name, description, created, architecture:
    {input_modalities, output_modalities}, supported_parameters: {name: {type: enum, values} |
    {type: range, min, max} | {type: boolean}}, supports_streaming, endpoints: "/api/v1/images/
    models/{id}/endpoints"}]}` (61 image models on 2026-10-08, 50 of them text-to-image raster).
  - `GET /images/models/{author}/{slug}/endpoints` (public): `{id, endpoints: [{provider_name,
    provider_slug, provider_tag, supported_parameters, allowed_passthrough_parameters,
    supports_streaming, pricing: [{billable: output_image | input_image | input_text | ...,
    unit: image | megapixel | token | request, cost_usd, variant?}]}]}`; 404 `{error: {message:
    'No image model found for "x"', code: 404}}` for an unknown model. `variant` is a resolution
    tier (`2k`, `4k`) for tiered prices. Samples: seedream-4.5 $0.04 per image, flux.2-klein-4b
    $0.014 per megapixel, gpt-image-2 $0.00003 per output token, recraft-v4.1-flash $0.007 per
    image.
  - `GET /models?output_modalities=image` (the general catalog) has per-token strings only
    (`pricing.image_output` etc.), so vidgen uses the image-specific records above.
  - The older route — `POST /chat/completions` with `modalities: ["image", "text"]` and
    `image_config` — also exists; vidgen uses the dedicated `/images` endpoint (one picture,
    base64, a cost in the response).
  - App identification headers (optional): `HTTP-Referer` (the app's URL; creates the app's page
    in OpenRouter's rankings), `X-OpenRouter-Title` (display name; `X-Title` is the older alias),
    `X-OpenRouter-Categories`. vidgen sends `HTTP-Referer:
    https://github.com/joaopauloschuler/schu-video-generator` and `X-OpenRouter-Title:
    schu-video-generator` on every request (`openrouter.APP_HEADERS`).
- **Config** `imagegen.provider: openai | openrouter` (`openai` stays the default; unknown values
  are a config error), new `imagegen.resolution` (OpenRouter tiers). An `ImagegenConfig` model
  validator: `provider: openrouter` needs an explicit `model` in `author/name` form, a `quality`
  from `config.OPENROUTER_QUALITIES`, and not both a `WxH` size and a resolution; `resolution`
  with `openai` is an error. All surface in `vidgen validate` and the JSON Schema.
- **Request** (`image_request`): OpenRouter's `size: auto` sends `aspect_ratio` = the listed
  ratio nearest the final format with the same orientation (`openrouter_aspect`; 16:9 → `16:9`,
  9:16 → `9:16`, 4:3 → `4:3`), or `16:9` / `9:16` / `1:1` for a `generate.aspect` other than the
  video's; plus `resolution`. `ImageRequest` gained `aspect_ratio`, `resolution`,
  `explicit_size` (defaults keep old constructors working) and `shape`; with an aspect ratio,
  `size` is the nominal `WxH` at the tier's long side (1K = 1024 without a tier;
  `nominal_size`) — the placeholder's shape and the per-megapixel estimate. Default quality for
  OpenRouter: none (not sent). `estimated_cost` is OpenAI-only (`PRICES`).
- **Cache key**: `request_key(..., extra)` adds `{aspect_ratio, resolution}` for OpenRouter only,
  so every OpenAI key is unchanged (pinned in a test). Sidecar: OpenRouter pictures record
  `aspect_ratio`, `resolution`, `size` (`null` unless explicit) and, when reported, `cost_usd`.
- **Provider** `imagegen/openrouter.py` (`OpenRouterImageProvider`, stdlib): `POST /images`
  through `httpapi.post_with_retries` (retries on 429 / 500 / 502 / 503 / 504 / 524 / 529 with
  `Retry-After` / backoff 4·2^n s, cap 60 s, timeout 240 s; 402 and other 4xx not retried; key
  scrubbed). Key only from `OPENROUTER_API_KEY` at request time. Body (`request_body`): `model,
  prompt, n: 1`, then `size` (explicit) or `aspect_ratio` (+ `resolution`), `quality`, `seed`
  unless the model's record lists no seed (then it only names another picture, as for OpenAI),
  `output_format: png` when listed. `negative` / `style` go into the prompt (no negative-prompt
  parameter). Response (`decode_response` → `RawPicture(data, media_type, cost,
  revised_prompt)`, then `parse_response`): SVG (`image/svg+xml` or `<svg` / `<?xml` bytes) is
  refused with a clear message (vector output is Step 61b: it plugs in at `RawPicture`); JPEG /
  WebP converted to PNG (`openai.as_png(data, service)`). `GeneratedPicture.cost` (new, default
  `None`).
- **Checks before paying**: the `ImageProvider` protocol gained an optional
  `check_requests(requests)`; `run_imagegen` calls it (when present) after `check_credentials`.
  OpenRouter fetches each model's public record once (`model_info`) and refuses, in one message:
  a model OpenRouter does not have (404 / no endpoints), a `quality` / `resolution` the model
  lacks or whose value it does not list, SVG-only models, models needing an input picture
  (`input_references.min ≥ 1`). Notes (not errors): an aspect ratio the model does not list
  (the provider clamps), no aspect-ratio parameter, a seed not sent. When the records cannot be
  reached nothing is refused and the body is sent as configured.
- **Prices** (`openrouter.quote(request, lookup) -> PriceQuote(cost, basis)`; `PriceQuote` in
  `vidgen.imagegen`): from the endpoint records' `output_image` lines — `image` / `request` units
  as is, `megapixel` × the request's (nominal) pixels, `$0` = free, `token` = unknown ("the
  tokens per picture are not listed"); a `variant` matching the resolution tier, else the
  untiered line, else the highest; with several endpoints the highest ("the highest of N
  providers"). `lookup_models` fetches each distinct model once (`LOOKUP_TIMEOUT` 5 s) and stops
  after the first unreachable answer (offline costs one short wait). `run.price_plan` fills the
  plan's `quotes`, `notes`, `problems` and `price_notes` (`OpenRouter prices of <UTC date>` or
  `OpenRouter prices unknown (its model list could not be reached)`; OpenAI keeps its 2025 note).
  Only the dry run looks prices up.
- **Output**: dry-run lines for OpenRouter `would generate KEY.png for S (16:9, openrouter MODEL
  QUALITY, ~$0.040 | price unknown)` then `price: <basis>`, `note:` / `problem:` lines, the
  prompt; the total line says how many a run would refuse. A run prints each picture's reported
  cost and ends `done: N picture(s) generated ($X charged by openrouter)` (`cost not reported by
  openrouter` without usage). OpenAI output is unchanged. `imagegen --json` images gain
  `aspect_ratio, resolution, price_basis, notes, problems`; the document gains `charged`;
  `price_note` is the plan's. MCP: same tool (description names OpenRouter); real runs still
  need `confirm_cost`.
- **Not render inputs**: `imagegen/openrouter.py` (fingerprint); the `imagegen` config stays in.
- **Tests** (`tests/test_imagegen_openrouter.py`, urlopen mocked, real endpoint records of
  2026-10-08 in `tests/data/openrouter_endpoints.json`): config errors, schema, pinned OpenAI
  keys, aspect ratios / tiers / explicit sizes / keys, the body, headers (app identification,
  no key on lookups), JPEG / WebP / SVG / bad responses, retried 429 / 529, 402 / 400 not retried
  with the key scrubbed, missing key, quotes per image / megapixel / token / free / tiers / several
  endpoints / offline, lookups stopping offline, model checks, dry run human / JSON / offline /
  refusals, a run with costs and sidecars, refusals before any POST, an unreachable lookup not
  blocking.
- **Live check** `tools/live_check_openrouter.py` (not shipped, not tested): lists the cheapest
  text-to-image models with vidgen's estimates, then one picture's dry run; `--yes` generates
  that picture through `run_imagegen` in a temporary project and prints the PNG, sidecar and
  reported cost.
- **Not done**: SVG output (Step 61b; done, §65); per-token prices (no tokens-per-picture data); input
  pictures / editing; provider routing preferences (`provider.only`, `sort`); streaming; the
  input-text price lines are not added to the estimate (prompts are short).

## 65. Refinements (Step 61b, vector (SVG) generated images; data-policy errors)

- **API facts** (OpenRouter's public `GET /api/v1/images/models`, the per-model endpoint records,
  `openapi.yaml` and the image generation guide, checked 2026-10-08):
  - `output_format: svg` exists "for vectorization models (e.g. Quiver)"; the SVG markup comes
    UTF-8 base64 in `b64_json` with `media_type: image/svg+xml`. No Quiver model is in the image
    list; the models listing `output_format` `svg` (and only svg) are Recraft's:
    `recraft/recraft-v4.1-vector`, `recraft/recraft-v4-vector` ($0.08 per image),
    `recraft/recraft-v4.1-pro-vector`, `recraft/recraft-v4-pro-vector` ($0.30 per image) — **text
    prompt in, SVG out** (`input_references` 0–1, optional), aspect ratios `1:1 4:3 3:4 16:9
    9:16 auto`, no seed / quality / resolution, passthrough `style`, `controls`, `text_layout`;
    and `recraft/recraft-v4-styles-vector` ($0.05 + $0.005 per reference) /
    `-styles-pro-vector`, which need 1–10 style reference pictures (refused as input-picture
    models). So no two-call "PNG then vectorise" pipeline is needed (nor possible: no
    vectorise-only model is listed).
  - `GET /api/v1/endpoints/zdr` (public) lists every endpoint with Zero Data Retention
    (`data: [{model_id, provider_name, tag, ...}]`, 942 on 2026-10-08). Image models among them:
    Seedream 4.5 / 5.0 flash / lite / pro, Gemini image models, Krea 2, MAI image 2.5 / 2.6,
    Tencent HY image 3.5, Ming image design. **No SVG model** (Recraft has no ZDR endpoint), nor
    FLUX. An account requiring ZDR gets HTTP 404 `No endpoints available matching your guardrail
    restrictions and data policy ... ZDR violation (account settings). Configurable at
    https://openrouter.ai/settings/privacy` (seen live by the coordinator for
    `recraft/recraft-v4.1-flash` and `black-forest-labs/flux.2-klein-4b`).
- **Param** `GenerateImage.format: png | svg` (default `png`). **Config** `imagegen.svg_model`
  (openrouter only, `author/name`; default `model`): the model of `format: svg` pictures, so one
  video can mix raster and vector pictures. `imagegen_problems(project)` (in `vidgen validate`'s
  project problems, so any scene type's `generate:`): `format: svg` needs `provider: openrouter`.
  `vector_warnings` (in `imagegen_warnings`): a `format: svg` model not in the snapshot
  `SVG_MODELS` (and without "vector" in its id), an SVG-only model asked for `png`, and the
  sanitiser's warnings for stored SVGs (with the scene's `simplify`; `SceneImage.params` added).
- **Request** (`image_request`): `format: svg` → model `svg_model or model`, `aspect_ratio` as
  §64 (`auto` = nearest the video), no quality / resolution, nominal size at 1K, `path
  <key>.svg`, `ImageRequest.format`; key `extra` gains `format: svg` (PNG keys unchanged,
  pinned). Body: `output_format: svg`. `check_request`: `format: svg` with a model not listing
  svg → problem naming the SVG models; `png` with an SVG-only model → "add format: svg".
  `parse_response(body, format)`: svg must be vector (`media_type` or `<svg` / `<?xml`) and pass
  the sanitiser, stored as sent; raster when svg was asked (or the reverse) → error. Sidecar
  `format: svg` (only for svg). `run_imagegen` / `price_plan`: svg with another provider is a
  problem / refused before paying. Orphans: `.png` and `.svg`. Messages and `--json` use the
  file name; JSON images gain `format`. Prices as §64 (per image).
- **Sanitiser** (`vidgen/svgclean.py`, no manim; svgelements from Manim for colours, paths,
  transforms): refuses > 20 MB, `<!ENTITY` declarations, non-SVG roots, unparsable XML, nothing
  drawable left. Removes (warning): `script`, `foreignObject`, `image`, `filter` (+ `filter=`),
  `mask` / `clipPath` (+ attributes; "shapes they hid may show"), `text` (with a hint to use
  vidgen's captions), `use` / `href` to other files; silently: metadata, title, desc, animation
  elements, gradients / patterns after flattening, `on*` attributes, other `url()` style
  properties. Flattens `fill` / `stroke` `url(#id)` (attribute or `style`) to the mean of the
  gradient's stops (following `href`), a pattern's first shape fill, else `#888888`. Manim
  quirks shared with icons (`fix_manim_quirks`, `insert_box`, `view_box`; icon_mobject now uses
  them): `currentColor` → a marker (icons) / black (pictures), `stroke: none` → zero width, the
  invisible viewBox rectangle first. Caps: `MAX_SHAPES` 1500 (smallest by transformed box area
  dropped), `MAX_SEGMENTS` 60 000 (paths and polylines keep 1 point in k, as lines); `simplify`
  (% of the viewBox area; `true` = 0.05) drops smaller shapes first (a note, not a warning).
  `CleanSvg(data, view_box, shapes, segments, warnings, notes)`. Measured: an SVG at the caps
  loads in ~6 s and draws a 1080p frame in ~0.25 s.
- **Shapes** (`vidgen/vector_mobject.py`): `load_vector(path, *, height, recolor, theme,
  simplify, where) -> VectorPicture` (sanitised copy in the icon work folder, `SVGMobject`,
  invisible box, SVG stroke widths → Manim units for the height, sanitiser warnings logged).
  `SvgDrawing` (new base of `Icon` and `VectorPicture` in `icon_mobject.py`): box / parts and
  `scale(scale_stroke=True)`; `scale_icon_strokes` handles any `SvgDrawing`. Fill-only parts get
  a zero-width outline in their fill colour at opacity 1, so `DrawBorderThenFill` traces them.
  `recolor: theme` (`svgclean.theme_color`): saturation < 0.2 or lightness < 0.06 / > 0.96 → the
  neutral (`background`, `surface`, `dim`, `text`) of nearest lightness; else hue and saturation of
  the theme colour (`primary`, `secondary`, `tertiary`, `accent`, `highlight`, palette) of
  nearest hue, the original lightness kept (a halfway lightness was tried: flat-looking).
  `vidgen.api` exports `VectorPicture`, `load_vector`.
- **`image` scene**: `.svg` accepted as `path` (validate runs the sanitiser); `draw` (bool),
  `recolor` (`none | theme`), `simplify` (bool | 0–5) — a config error unless the picture is
  vector. Vector sources (stored SVG, `.svg` file) load with `load_vector`; the placeholder
  before generation stays a PNG (faded in). Fit, cover, caption and Ken Burns work unchanged
  (`scale_to_fit_width` scales strokes). `draw: true`: the entrance is `DrawBorderThenFill`,
  played with `reveal(fraction=0.75, cap=2.5)` (fades: 0.6 / 1.0).
- **Layout dump / lint**: a `VectorPicture` is one object, kind `vector`, class `VectorPicture`,
  `fill` / `stroke` of its largest part; lint's `covered_text` treats it like a shape (pixels),
  not like an opaque image.
- **Data-policy errors**: `openrouter.is_policy_error` (an HTTP 404 whose body mentions data
  policy / ZDR / guardrail / settings/privacy) → `policy_message(model, svg)`: the account's
  privacy settings exclude every provider of the model, the settings link, and the image models
  (SVG ones for `format: svg`) with a ZDR endpoint now (`zdr_image_models`: the ZDR list ∩ the
  image list, 5 s timeout, `None` offline → "could not be reached to suggest models"). Not
  retried; the provider's `zdr` callable is injectable.
- **Live check** `tools/live_check_openrouter.py`: `--zdr` restricts the cheapest pick to models
  with a ZDR endpoint; `--svg` picks the cheapest text-to-SVG model and generates one vector
  picture (dry run unless `--yes`), printing the sanitiser's report.
- **Tests** `tests/test_vector_images.py` (urlopen mocked; fixture `tests/data/vector_hills.svg`,
  hand-written): sanitiser (fixture, removed parts, refusals, caps, simplify, thinning),
  theme colours, keys / paths / config / params / validate warnings and problems, check and
  body, SVG responses, dry run + run storing the SVG, OpenAI refusal, policy error with / without
  suggestions and offline, the ZDR lists, loading (box, strokes, recolor), draw states, the
  layout object, scene renders (generated SVG drawn, file SVG with cover + Ken Burns) at
  160x90 / 90x160, validate of an `.svg` path.
- **Not done**: `fill-rule: evenodd` holes and per-element `stroke-linecap` follow Manim's SVG
  parser; text is removed, not converted to vidgen text; recolor is per colour, not per region;
  no SVG model can be used by an account that requires ZDR (none has a ZDR endpoint).


## 66. Refinements (Step 62, OpenRouter TTS provider; one provider per video)

- **API facts** (checked 2026-10-08 from `https://openrouter.ai/openapi.yaml`, the TTS guide
  `docs/guides/overview/multimodal/tts`, the Python SDK's `tts.create_speech` page and the public
  endpoints; no key used): `POST /api/v1/audio/speech` (OpenAI-compatible) `{model, input,
  voice?, instructions?, response_format?: mp3 | pcm (default pcm), speed?, input_references?,
  provider?: {zdr, data_collection, options}, session_id?, user?}` → **raw audio bytes** (not
  JSON), headers `Content-Type` (`audio/mpeg` / `audio/pcm`: 16-bit LE mono, 24 kHz) and
  `X-Generation-Id`. No cost in the response: `GET /api/v1/generation?id=<id>` (with the key)
  gives `data.total_cost`. `instructions`: OpenAI gpt-4o-mini-tts and Gemini TTS only, others
  ignore it; `speed`: OpenAI, others ignore it or return 400 for a value other than 1; Gemini TTS
  returns only `pcm` (`mp3` → 400 "only supports response_format=\"pcm\""); multi-speaker
  `input` (a list of turns): Gemini only. Errors `{error: {code, message}}`; 402 / 429 / 502 /
  503 / 524 / 529 as for images. Models: `GET /api/v1/models?output_modalities=speech` (public):
  32 models with `supported_voices` (null for some: Fish Audio, Seed Audio) and list `pricing
  {prompt, completion}`; `GET /api/v1/models/{author}/{slug}/endpoints` (public): each
  provider's `pricing` (they differ: Kokoro $0.00000062 DeepInfra vs $0.000004 Together; Voxtral
  $0.000016 vs $0.0000176 EU). "Most TTS models are priced per character of input text"
  (`pricing.prompt`), per-second / per-audio-token models report `pricing.completion` (Gemini
  TTS: prompt per text token + completion per audio token; Seed Audio: per second). ZDR (`GET
  /api/v1/endpoints/zdr`, field `model_id`): 27 of the 32 TTS models (all but MiniMax speech-2.8
  hd / turbo, Qwen TTS flash / plus, Grok voice).
- **Config**: `VoiceConfig.provider: elevenlabs | openrouter` (`config.TTS_PROVIDERS`), new
  optional `model`, `voice`, `instructions`, `speed` (0.25–4; not sent when absent); a model
  validator requires `model` (`author/name`) for openrouter. Keys of the provider not in use are
  **ignored, not errors** (`ELEVENLABS_VOICE_KEYS` / `OPENROUTER_VOICE_KEYS`): a variant that
  switches the provider deep-merges onto the base voice, whose other-provider keys stay. The
  same four keys are optional on `VoiceEntry`.
- **One provider per video**: `voices.voice_provider_problems(config)` (in `parse_config`, after
  the model validates, beside the voice-name check): a named voice with another `provider` →
  `voices.<name>.provider: one TTS provider per video: ...`; a named voice setting a key of the
  other provider (`voice_id`, `settings`, `context`... in an OpenRouter video; `model`, `voice`,
  `instructions`, `speed` in an ElevenLabs one) → `voices.<name>.<key>: ...`. Problems with
  locations; a variant's are attributed to it. A variant may switch the provider: its effective
  voice differs, so `Project.has_own_audio` gives it `audio/<variant>/` (§7 rule unchanged); a
  named voice's ElevenLabs keys are cleared in the variant with `null` (`voices: {guest:
  {voice_id: null, settings: null, voice: ...}}`).
- **Provider** `tts/openrouter.py` (`OpenRouterTTSProvider`, `name = "openrouter"`, stdlib):
  `POST /audio/speech` through `httpapi.post_with_retries` (new optional `response_headers`
  dict; same retries as images: 429 / 5xx / 524 / 529), headers `Authorization: Bearer`, the
  app identification of §64, `Accept: audio/mpeg, audio/*`. Body `{model, input,
  response_format}` + `voice` / `instructions` / `speed` when set; **no** `previous_text` /
  `next_text` (the API has none: the run passes them, the provider ignores them), **no**
  `language_code` (`voices._with_language` returns `None` for any provider but elevenlabs: the
  language follows the text and voice), no `input_references`, no multi-speaker input. Format:
  `mp3` asked for, `pcm` for `google/` models (`PCM_ONLY_PREFIXES`) and after a 400 naming
  `response_format` and `pcm` (then remembered); `as_mp3`: MP3 kept (ID3 / frame sync, or
  `audio/mpeg`), WAV and PCM (`s16le`, rate from `Content-Type` `rate=` else 24000, mono)
  converted with ffmpeg (`libmp3lame`, 128 kb/s) in a temporary folder; anything else (JSON,
  HTML) → error quoting its start. `X-Generation-Id`s are kept on the provider;
  `reported_cost()` reads `GET /generation?id=` for each, never raises (retries: §67). Key:
  `imagegen.openrouter.read_api_key("tts")` (the missing-key
  message names `vidgen tts --dry-run`).
- **Hash**: `sha1(json.dumps({provider, model, voice, instructions, speed}, sort_keys=True,
  ensure_ascii=False) + "|" + spoken_text)` — every key that changes the audio; ElevenLabs keys
  are untouched (two ElevenLabs keys pinned in `tests/test_tts_openrouter.py`, kphi3's 27
  committed hashes still "ok").
- **Data policy**: a 404 recognised by `imagegen.openrouter.is_policy_error` → `policy_message`:
  the shared first line (`policy_intro`, factored out of §65's message) and "Text-to-speech
  models with a ZDR endpoint now: ..." (`zdr_tts_models`: the ZDR list ∩ the speech model list;
  offline: "could not be reached to suggest models"). Not retried.
- **Prices** (`tts.run.price_tts`, dry run and before a paid run): `lookup_speech_models`
  reads the speech model list once (5 s timeout) and each used model's endpoint records;
  `character_rate`: the highest `prompt` over the endpoints (the list price when the records
  cannot be read), "free" at 0, **unknown** when any endpoint has a non-zero `completion` (the
  generated audio is billed and its length is not known beforehand), offline or for a missing
  model. `TTSPlan` gains `beat_voices`, `rates`, `notes`, `problems`, `price_notes`, `charged`,
  `beat_cost(beat)`, `cost`, `price_note`, `synthesised()`, `engine(beat)`. ElevenLabs is never
  estimated (`ELEVENLABS_PRICE_NOTE`: plan quota).
- **Checks**: `vidgen validate` (no network) warns via `tts.tts_warnings(project)` (in
  `validate_warnings`) from the bundled snapshot `data/openrouter/tts_models.json` (dated; ids,
  voices, ZDR flag, list prices): a model not listed (did-you-mean), a voice the model does not
  list, no voice for a model that lists some, `timestamps: true` (no timings; captions estimate).
  Warnings, not errors: lists may be incomplete and change. `vidgen tts --dry-run` / a real run use
  the live list: a model OpenRouter does not have is a `problem:` (a real run refuses before any
  paid request), an unlisted voice or `instructions` / `speed` on a model not documented to use
  them (`INSTRUCTION_PREFIXES` `openai/`, `google/`; `SPEED_PREFIXES` `openai/`) a `note:`.
  Offline: nothing refused, "price unknown".
- **`vidgen tts`**: ElevenLabs output unchanged. With OpenRouter beats the dry run adds `,
  ~$0.0002` (or `, price unknown`) to each `would generate` line, one `voice <name> (openrouter
  <model>, voice <v>[, instructions '...'][, speed s]): N beat(s), C characters` line per voice
  (also without `voices:`), `price of <model>: <basis>`, `note:` / `problem:` lines and `cost:
  estimated $X (OpenRouter prices of <date>)`. A real run prints `note:` lines first and ends
  `done: N beat(s) generated (C characters, $X charged by openrouter), ...` (or `cost not
  reported by openrouter`; `for K of N requests` when only some were). Captions / SRT / lint /
  readback need nothing new: the MP3s are ordinary, `speech.read_alignment` finds no
  `.align.json`, so word times are estimated within the MP3's speech bounds.
- **JSON** (`tts --json`): top level `provider`, `estimated_cost`, `unknown_cost`, `price_note`,
  `prices {model: {per_character, basis}}`, `notes`, `problems`, `charged`; each beat and voice
  gains `provider`, `model`, `provider_voice`, `instructions`, `speed` (+ beat `estimated_cost`).
  MCP `tts` is unchanged in shape (description names OpenRouter); real runs still need
  `confirm_cost`.
- **Live check** `tools/live_check_openrouter.py --tts [--zdr] [--yes] [--model ID] [--voice
  NAME]`: prices every TTS model with a per-character price, picks the cheapest (an English /
  neutral voice of its list), prints `vidgen tts --dry-run` of one 12-word beat in a temporary
  project and with `--yes` voices it through `run_tts`, printing the MP3 path, duration and the
  reported cost. Free part run here: cheapest ZDR model `hexgrad/kokoro-82m` ($0.000004 per
  character, the highest of 2 providers; ~$0.00024 for the beat).
- **Not done**: voice cloning (`input_references`), multi-speaker input, provider routing
  preferences (`provider.zdr` is not sent: the account setting decides), per-token / per-second
  estimates (Gemini TTS, Seed Audio), streaming; no real paid request was made here (no key).

## 67. Refinements (Step 63, review of Phase F)

- **Live results** (the coordinator, owner's key, account requiring ZDR, 2026-10-09): image
  models without a ZDR endpoint (`recraft/recraft-v4.1-flash`, `black-forest-labs/flux.2-klein-4b`)
  → HTTP 404 `0 endpoints out of 1 requested are available matching your guardrail restrictions
  and data policy ... ZDR violation (account settings) ...` with `metadata.ineligibility_reasons:
  [{reason: zdr-violation-by-account, ...}]` (recognised by `is_policy_error`; pinned in
  `conftest.LIVE_ZDR_404`); `bytedance-seed/seedream-5-0-flash` 1K 1:1 → 1024x1024 PNG, 9.7 s,
  `usage.cost` $0.018 = the estimate. TTS `hexgrad/kokoro-82m` / `af_alloy` → MP3 (24 kHz mono,
  4.46 s); `google/gemini-3.8-flash-lite-tts` / `Kore` → PCM converted (4.68 s). Both runs
  printed "cost not reported": the `X-Generation-Id` header was there (the line is printed only
  for providers with ids), so `GET /generation` gave no `total_cost` within one 1 s retry. Key
  usage rose $0.000038 for both beats: Kokoro routed to its cheapest provider (61 × $0.00000062),
  6x below vidgen's highest-provider estimate (an upper bound, as documented).
- **Cost lookup** (`OpenRouterTTSProvider.reported_cost(timeout, waits=COST_WAITS)`):
  OpenRouter writes generation records asynchronously, so every request whose record is not
  there yet — HTTP 404, 429 / 5xx / 524 / 529, unreachable, a record without a numeric
  `total_cost` — is asked again after each of `COST_WAITS` = 1, 2, 4, 8 s (all requests in one
  round per wait: at most 15 s after a run, plus a deadline of `sum(waits) + 2·timeout`); other
  statuses (400 / 401 / 403) and unreadable JSON are not retried. `cost_problem` (new attribute)
  says why a request was left out (`GET /generation answered HTTP 404 for gen-...: <body, key
  scrubbed> (still missing after waiting 15 s)`, `the generation record of ... has no total_cost
  yet`, `N audio response(s) came without an X-Generation-Id header`); `requests` counts audio
  responses (with or without an id). `run._reported_cost` asks every provider with `requests`
  and prints `, cost not reported by openrouter yet (<why>; see https://openrouter.ai/activity)`
  or `for K of N requests (<why>; see ...)`. Never fails the run.
- **Key hygiene**: `httpapi.scrub` also removes the key as `repr` escapes it (http.client quotes a
  rejected header value as bytes); `httpapi.get(..., secret=)` scrubs its errors (used by the
  key-authenticated `/generation` lookup) and wraps `http.client.HTTPException`;
  `imagegen.openrouter.read_api_key` refuses a key with spaces, control or non-ASCII characters
  without quoting it.
- **JSON**: `tts --json` `voices.<name>.voice_id` is `null` in an OpenRouter video (it showed
  the ElevenLabs default id).
- **Live check** `tools/live_check_openrouter.py`: `--generation ID [--wait S]` probes one
  generation record (status / main fields each time, backoff 1 → 16 s); `--tts --yes` keeps the
  provider, prints the `X-Generation-Id`s and, without a cost, `cost_problem` and the probe of the
  first id. Options documented in the docstring.
- **Tests** `tests/test_phase_f_review.py` (imagegen → render with a PNG and a drawn, recoloured
  SVG; OpenRouter tts → render with captions; a variant switching provider; one-provider errors;
  MCP dry runs offline with the `confirm_cost` guard; scrubbing; the tool never printing the
  key) and in `tests/test_tts_openrouter.py` (records written late: 404 → no `total_cost` → cost;
  giving up; no id; the run's message) and `tests/test_vector_images.py` (the live ZDR body).

## 68. Refinements (Step 65, local Kokoro TTS; optional extra)

- **Facts** (checked 2026-10-09): model `hexgrad/Kokoro-82M` v1.0 on Hugging Face, Apache-2.0
  (weights and the `kokoro` / `misaki` packages), 82 M parameters (StyleTTS 2 + ISTFTNet),
  `kokoro-v1_0.pth` 327,212,226 bytes, SHA256 `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4`;
  54 voices in `voices/` (~0.5 MB each), 9 languages `a b e f h i j p z`. PyPI `kokoro` 0.9.4
  (2025-04-05; deps `huggingface-hub, loguru, misaki[en]>=0.9.4, numpy, torch, transformers`) and
  `misaki` 0.9.4 both declare `Requires-Python <3.13,>=3.10`. `KPipeline(lang_code, repo_id,
  model=True | KModel, device=None | cpu | cuda)` downloads `config.json` + the weights
  (`hf_hub_download`) and each voice on first use; calling it with `(text, voice, speed,
  split_pattern)` yields `Result(graphemes, phonemes, tokens, output)`, `audio` = float32 at 24
  kHz. For `a` / `b` the tokens are misaki `MToken`s with `start_ts` / `end_ts` (seconds, from
  the predicted durations, per chunk); other languages yield no tokens. English G2P = misaki +
  spaCy `en_core_web_sm` (installed with `spacy.cli.download`, i.e. pip, on first use) + espeak-ng
  fallback; `e f h i p` = espeak-ng; `j` / `z` need `misaki[ja]` / `misaki[zh]`. misaki's
  `espeak.py` points phonemizer at the library **bundled in the `espeakng-loader` wheel** (Windows,
  Linux, macOS) at import, so no system espeak-ng is used or needed (a Portuguese beat was voiced
  here with no espeak-ng installed). Linux PyPI torch pulls ~4.3 GB of CUDA libraries + triton;
  the CPU wheel index is the small path.
- **Config** (`config.py`): `provider: kokoro` (`TTS_PROVIDERS`), `KOKORO_VOICE_KEYS = (voice,
  speed, lang, device)`, `PROVIDER_VOICE_KEYS`; new `VoiceConfig.lang: a|b|e|f|h|i|j|p|z|null`,
  `VoiceConfig.device: cpu|cuda|auto = cpu`; `VoiceEntry.lang`. `voice` / `speed` are shared with
  OpenRouter. Keys of other providers are ignored on `voice:` (as §66).
- **Resolution** (`kokoro_voices.resolve`, applied by `voices._with_language`): `lang` = given,
  else the voice's first letter (`^[a-z][fm]_`), else the video `language` (`en`→a, `en-GB/IE/AU/NZ`
  →b, `es` e, `fr` f, `hi` h, `it` i, `ja` j, `pt` p (also pt-PT), `zh` z; none → a); `voice` =
  given, else the language's `default_voice` (af_heart, bf_emma, ef_dora, ff_siwis, hf_alpha,
  if_sara, jf_alpha, pf_dora, zf_xiaobei); `speed` = given, else 1. A named voice that sets
  `voice` without `lang` gets that voice's language (the base `lang` is not inherited then). A
  language with no Kokoro voice and no `lang` / voice is a config error
  (`voices._kokoro_language_problems`, inside `voice_provider_problems`, so variants too).
- **One provider per video** (`voice_provider_problems` generalised): other-provider keys are
  every key of the other providers not used by the base provider; the message names the owners
  ("voice is an OpenRouter or Kokoro setting", "lang is a Kokoro setting"); a Kokoro named voice
  changes `voice, speed, lang`. Existing ElevenLabs / OpenRouter messages unchanged.
  `voices.audio_fields` now leaves out `device` (`RUNTIME_FIELDS`): a variant changing only the
  device shares `audio/`.
- **Provider** `tts/kokoro.py` (`KokoroProvider`, `name = "kokoro"`, `timings_included = True`):
  nothing imports `kokoro` / torch until the first beat (validate, render, dry run never do; tested
  via `sys.modules`). `check_credentials` = `check_installed(lang)`: the extra
  (`find_spec("kokoro")`), `misaki[ja]` / `[zh]` (pyopenjtalk / jieba), `espeakng_loader` for
  espeak languages → `VidgenError` with the command (`pip install "schu-video-generator[kokoro]"`;
  on Python > 3.12 also the forced install that worked on 3.13: `--ignore-requires-python` +
  `spacy>=3.8,<4`, `spacy-curated-transformers<0.4`, without which pip backtracks to a spaCy 4
  pre-release sdist that fails to build). `KokoroEngine(device)`: one `KPipeline` per language,
  the first one's `KModel` passed to the next (`model=`), shared by every voice of the process
  (`shared_engine`, module dict) = loaded once per `vidgen tts`. `synthesize_timed`: pipeline
  called with `split_pattern=None`, results' float audio → 16-bit PCM (`pcm16`) → MP3 with ffmpeg
  (`openrouter.convert_to_mp3`, new `source=` for its messages; 128 kb/s, 24 kHz mono); token
  times shifted by each chunk's offset → `alignment_from_tokens` (each token found in order in the
  spoken text spreads its time over its characters, other characters take the previous end;
  `None` when < 80 % of the words are timed) → stored like ElevenLabs' alignment, so captions /
  SRT time words exactly and pronunciation maps back (`speech.map_word_times`). Non-English: no
  alignment (estimates). While Kokoro loads / runs, fd 1 goes to stderr (`quiet_stdout`: spaCy's
  pip install prints to stdout, which would break `--json`) and torch's load warnings are
  ignored. Library exceptions → `explain()`: espeak-ng (both installs named), misaki extras,
  CUDA (`device: cpu`), downloads (Xet / CAS, proxy, offline; `HF_HUB_DISABLE_XET=1` hint),
  else `Kokoro could not voice the text: <type>: <msg>`.
- **Hash**: `sha1(json.dumps({provider: kokoro, model: hexgrad/Kokoro-82M, weights:
  kokoro-v1_0.pth, voice, lang, speed}, sort_keys=True, ensure_ascii=False) + "|" + spoken_text)`
  with the resolved values (pinned in `tests/test_tts_kokoro.py`); not the device nor the package
  version (an upgrade does not re-voice). ElevenLabs and OpenRouter keys pinned unchanged.
- **Run** (`tts/run.py`): `run_tts` calls `synthesize_timed` when `voice.timestamps` **or** the
  provider's `timings_included`; before synthesis prints `note:` lines (`kokoro.run_notes`: free
  and local on <device>, the download still to come when the weights are not in the HF cache —
  `hf_cache_dir()`: `HF_HUB_CACHE`, `HF_HOME/hub`, `XDG_CACHE_HOME/huggingface/hub`,
  `~/.cache/huggingface/hub` — the extra / language packages missing). `TTSPlan.beat_cost` = 0
  for Kokoro; `price_tts` adds `KOKORO_PRICE_NOTE` ("free (local): Kokoro-82M runs on this
  computer") and the notes (no network); dry run prints per-voice lines `kokoro <voice> (lang x,
  <Language>), speed s, <device>`, `note:` lines and `cost: free (local): ...`; the run summary has
  no cost part.
- **JSON / MCP**: `tts --json` beats and voices gain `lang` and `device` (Kokoro's; `null` for the
  others), `model` `hexgrad/Kokoro-82M`, `provider_voice` the voice, `speed` 1.0 by default,
  `voice_id` `null`; `estimated_cost` 0, `unknown_cost` 0, `price_note` the free note. MCP `tts`:
  a real run needs `confirm_cost` unless the project (variant applied) loads and its
  `voice.provider` is in `FREE_TTS = ("kokoro",)` (`mcp_server.tts_provider`); a project that
  does not load still needs it (conservative). Tool text and server instructions say so.
- **Validate** (`tts.tts_warnings` → `kokoro.voice_warnings` / `kokoro_voices.voice_warnings`,
  `kokoro.install_warnings`; no network, nothing loaded): voice not in the bundled
  `data/kokoro/voices.json` (dated 2026-10-09, did-you-mean, the language's best voices; `.pt`
  files and blends `a,b` checked per part), voice of another language than `lang`, `lang` not the
  video language (a / b both English: fine), `timestamps` with a language without timings, the
  extra or `misaki[ja]` / `[zh]` not installed.
- **Packaging**: extra `kokoro = ["kokoro>=0.9.4; python_version < '3.13'"]` (on 3.13 the extra
  installs nothing instead of failing a combined `.[dev,kokoro]`; vidgen explains); package data
  `data/kokoro/*`. Nothing of Kokoro is bundled (THIRD_PARTY_NOTICES).
- **Live** (this workspace, 2026-10-09): Hugging Face's file CDN and Xet hosts are blocked by
  the egress proxy, so the weights and three voices were fetched from Kokoro-FastAPI's GitHub
  release / repository and verified against the model card's SHA256 (weights) and VOICES.md's
  hash prefixes (af_heart `0ab5709b`, bf_emma `d0a423de`, pf_dora `07e4ff98`), then laid out as
  an HF cache and used with `HF_HUB_OFFLINE=1` — vidgen's normal `hf_hub_download` path. Python
  3.12 venv with `pip install -e ".[dev,kokoro]"` (torch 2.14.1, transformers 5.19, manim 0.22):
  `vidgen tts` voiced 2 English + 1 Portuguese beats (MP3 24 kHz mono; `.align.json` for the
  English ones), a preview render's SRT kept the written words through the pronunciation;
  ~0.7x real time on 2 CPU cores (3.6 s for 4.8 s of speech), ~10 s to load. Python 3.13:
  the forced install above, then a real synthesis with word timestamps, worked.
- **Not done**: Kokoro v1.1-zh (`hexgrad/Kokoro-82M-v1.1-zh`), custom `.pt` voice files are not
  hashed by content, no streaming, no automatic download of `misaki[ja]` / `[zh]`.

## 69. Characters (Step 67, character model: vector parts with pivots)

The base of Phase H (cartoons). Later steps build on these names: the parametric generator (Step
68) and imported SVGs (Step 69) produce `CharacterPart` lists; poses and expressions (Step 70)
are `PartPose` tables applied with `set_state`; lip sync (Step 71) and blinking (Step 72) swap
shapes; the `stage` scene (Step 73) places characters by `feet()`; acting actions (Step 78+)
take `CharacterName` options.

- **Parts** (`cartoon/character.py`): `PART_NAMES = body, legs, arm_left, arm_right, head, eyes,
  brows, mouth, accessory` (Step 92 adds `leg_left`, `leg_right` and the lower segments
  `arm_left_lower`, `arm_right_lower`, `leg_left_lower`, `leg_right_lower`, §69.26; Step 114 an
  animal's `tail`, parent `body`, draw order 5, §69.48; Step 124 a robot's `antenna`, parent `head`,
  order 49, and a `cape`, parent `body`, order 3, §69.58); `REQUIRED_PARTS` all but `legs`, `accessory`, `tail`, `antenna` and `cape` (`Character(...,
  required=)` overrides it: an imported SVG needs only `body`, §69.2). A part is a
  `CharacterPart(name, shapes, pivot, parent=None, order=None)`: `shapes` maps shape names to
  `VMobject`s (the first is the rest shape; e.g. eyes `open` / `closed`, mouth `smile` / `open`;
  Step 71 adds viseme shapes the same way), `pivot` an (x, y) point. Parents default to
  `DEFAULT_PARENTS` (body is the root; head, arms, legs hang from body; eyes, brows, mouth,
  accessory from head); a custom `parent` must be a part the character has, without cycles.
  Draw order defaults to `DEFAULT_DRAW_ORDER` (arm_right 10, legs 20, body 30, arm_left 40, head
  50, eyes / mouth 60, brows 70, accessory 80; ties by `PART_NAMES`), so facing right the
  character's right arm is the far arm behind the body. `arm_left` / `arm_right` are the
  character's own left / right (as in anatomy), so `arm_left` is on the screen's right in the
  rest view. Bad part sets raise `VidgenError` naming the character and the parts.
- **Character units**: parts are drawn with the origin between the feet, `y` up, 1 = the top of
  the character. `Character(parts, name=, height=3.0, facing="right", voice=None)` scales them to
  `height` Manim units; `feet()` is the origin on screen (the ground point a stage uses).
- **State and redraw**: the character keeps a copy of every rest shape and one
  `PartPose(angle, scale, shift, shape)` per part (frozen dataclass; angle in degrees
  counterclockwise as drawn facing right, scale (x, y) about the pivot, shift in character
  units). `refresh()` writes each live part's points as `screen · mirror · world(part) ·
  rest_points`, where `world(part) = world(parent) · pose(part)` and `pose = T(shift) · T(pivot) ·
  R · S · T(-pivot)`. So a part's pose moves its children and nothing else, and poses never
  accumulate rounding: every redraw starts from the rest shape. Styles of the live parts
  (colour, opacity) are not touched; only a shape swap replaces a part's child with a copy of
  the new shape (its rest style). `pivot(part)` gives the pivot on screen now.
- **Placement**: `submobjects[0]` is an invisible anchor of three points (feet, feet + 0.05
  right, feet + 0.05 up, in character units, inside the figure's box so `get_center` / `width` do
  not change). Manim's `shift`, `scale`, `rotate`, `move_to` move it with the parts, and
  `refresh()` reads the placement back from it, so poses set after a move land where the
  character is. No overrides of Manim's transforms were needed.
- **Facing**: `face("left")` mirrors the whole character about the vertical line through its
  feet (in character units, before the placement); `turn()` toggles. The draw order is kept (a
  mirror image), and part names keep their meaning (the left arm stays `arm_left`).
  `face("front")` shows the front view (Step 111, §69.44).
- **API**: `set_part(part, angle=, scale=, shift=, shape=)` (values not given keep the pose),
  `swap(part, shape)`, `reset(part=None)`, `face`, `turn`, `state()` → `CharacterState(facing,
  parts)`, `set_state(state)`, `pose_of`, `shape_names`, `parent_of`, `has_part`, `draw_order`,
  `parts` (name → live `VGroup`; since §69.22 one child per shape, only the shown one has points). All changes return the character (chainable). Animate poses by
  calling `set_part` / `set_state` from an updater, or with `PoseChange` (§69.3);
  `.animate.set_part(...)` would interpolate points linearly (a chord, not an arc).
  `copy()` is a deep copy with its own poses.
- **The default look** (`generate_parts(CharacterLook(), colors)`, §69.1; Step 67 called it the
  basic figure, `basic_parts`): a round head on an oval body, sleeves with round hands, two legs,
  dot eyes (`open` / `closed`), line brows, a smile arc or an open mouth; the face sits 0.025 to
  the right so facing is visible.
- **Stroke widths** (Step 68): parts are drawn with `OUTLINE_WIDTH = 4` for a character
  `REFERENCE_HEIGHT = 3` units tall. `Character.__init__` multiplies every stroke width of its
  rest shapes by `height / REFERENCE_HEIGHT` and keeps each at least one pixel wide in the current
  Manim config (`100 * frame_height / pixel_height`, as Cairo draws width `w` as `w * 0.01` frame
  units). Since the frame's shorter side is always 8 units (§5), the outline is a fixed fraction
  of the character and of the frame at any resolution and aspect. Manim's own `scale()` of a
  character afterwards does not scale strokes (as for any `VGroup`).
- **Config** (`config.py`): `characters: list[CharacterEntry]` at the top level;
  `CharacterEntry(name: Identifier, voice: Identifier | None, look: CharacterLook, colors:
  CharacterColors)`; `CharacterLook` holds the generator's parameters (§69.1) or `svg:` (§69.2); `CharacterColors(skin = secondary, clothes = primary, outline = features =
  CHARACTER_INK #1F2430, hair = accent, accessory = highlight)` as `ColorRef`s. A list (not a mapping) so that a repeated name is a
  clear error (YAML mappings silently keep the last duplicate key): `VideoConfig` raises
  `duplicate character name 'pip' (characters[0] and characters[1])`.
- **Checks**: `voices.voice_reference_problems` also checks `characters[k].voice` (a config
  error from `parse_config`, so variants too). `cartoon/cast.py` (no manim): `character_names`,
  `find_character` (raises with `unknown_character_message`: did-you-mean and the known names,
  or "the video declares no characters"), `character_color_problems` (run by
  `cli.project_problems`, i.e. `vidgen validate`), `check_character_name`.
- **`CharacterName`** (`scene.py`, exported): `Annotated[str, pattern ID_PATTERN,
  AfterValidator]`; like `IconName`, it checks the name only when the validation context has a
  theme (`vidgen validate`, scene build) and a project is active, against that project's
  `characters:`. It works in scene `Params` and action `Options` alike. It is not given an enum
  in `vidgen schema` (the schema is per video, not per project yet).
- **`character(name, height=3.0, facing="right")`** (exported): the active project's character,
  coloured with the current theme (`build_character(entry, theme=, height=, facing=)`).
- **Fingerprint**: `characters` is not excluded from `scene_fingerprint`'s config part, so editing
  a character re-renders every scene (conservative; Step 87, §69.20, did not narrow it to
  scenes that use characters: not one of its items).
- **Layout dump**: a `Character` is one object of kind `character` named after it (Step 73,
  §69.6).
- **Not done here**: no scene type draws characters yet (the `stage` scene type, Step 73, §69.6).

### 69.1 The character generator (Step 68)

`cartoon/generator.py`: `generate_parts(look, colors, *, outline_width=OUTLINE_WIDTH) ->
list[CharacterPart]`, the parts `build_character` (and so `character(name)`) uses for every
`characters:` entry. `colors` maps `COLOR_KEYS` (`skin, clothes, outline, features, hair,
accessory`, and since Step 113 `trim`) to Manim colours. Step 113 added more bodies, hair,
accessories and the clothes (§69.47); the values below are those of Step 68.

- **Parameters** (`CharacterLook`, all optional): `body` (`round | tall | square | bean`; sizes in
  `BODY_SIZES`), `head_size` (0.6–1.6, radius 0.2 × it), `eyes` (`dot | oval | round | sleepy`),
  `nose` (`none | dot | round | triangle`), `hair` (`none | short | spiky | long | bun | curly`),
  `ears` (`none | round | pointy | floppy`), `accessories` (subset of `glasses, hat, scarf, bag`,
  no repeats: a config error), `seed` (int or none).
- **Proportions** (`resolve_proportions(look) -> Proportions`, no drawing): head radius, body
  width and height, leg and arm length, eye gap, eye size and mouth width. With a `seed`, each is
  multiplied by `0.92 + 0.16 × random.Random(seed).random()` in field order (`SEED_VARIATION`);
  Python guarantees that `Random(int).random()` gives the same sequence on every platform and
  version (`uniform` is not covered by that promise, so it is not used), so a look always gives
  the same figure. Without a seed: no variation.
- **Layout** (character units before scaling): legs from 0 to `leg_length`; the body from
  `leg_length - 0.06` up `body_height`; shoulders (arm pivots) at `(±body_width/2, body_top -
  0.08)`; the head centred `head_radius - 0.02` above the body top, its pivot at the neck; the
  face 0.125 × the head radius to the right (facing right), eyes 0.15 r above the head centre.
  The finished parts are then scaled about the feet so the top of the tallest shape (hair, bun,
  ears or hat included) is at 1 (`_scaled_to_unit_height`); the default look is already 1 tall.
- **Where things go**: hair (back pieces for `long` / `bun` / `curly`, then ears, the head
  circle, the hair cap in front, the nose) is drawn inside the `head` part, so it turns with the
  head; `scarf` and `bag` inside `body`; `glasses` and `hat` make the optional `accessory` part
  (parent `head`, drawn on top). Shape names are the same for every look: eyes `open` /
  `closed`, mouth `smile` / `open` (and, since Step 71, the viseme shapes `A E O U M F L W`, §69.4),
  so Steps 70–72 swap them on any generated character.
- **Originality**: every shape is a primitive (circle, ellipse, rounded rectangle, polygon, line,
  arc); no option names or imitates a known character.
- **`vidgen character NAME [PROJECT] [--variant NAME] [--png [FILE]] [--facing right|left]`**
  (`cli.cmd_character`): with the project's extensions active (so project theme presets work),
  prints `cast.character_lines(entry, theme)` (voice, every `look` value, every colour with its
  resolved hex). `--png` calls `still.write_character_png(project, entry, theme, path,
  facing=)`: Manim's camera draws the character `0.8 × 8` units tall, centred, on the theme
  background, in the final format's aspect ratio with its shorter side 720 px; default file
  `exports/character_<name>.png` (`default_png_path`). No `--json`: Step 83's
  `vidgen character-sheet` (§69.16) is the agent tool, with `--json` and over MCP.

### 69.2 Characters from SVG files (Step 69)

`look: {svg: FILE}` (`CharacterLook.svg`, a path relative to the project folder ending in `.svg`;
any other `look` key with it is a config error) draws the character from an SVG instead of the
generator. `build_character(entry, root=)` (root default: the active project's folder; `character()`
and `still.write_character_png` pass it) calls `cartoon/svg_look.py`.

- **Splitting** (`split_character_svg(data, where) -> SvgCharacter`, `read_character_svg(path,
  where)`; no manim): the file goes through `svgclean.sanitize_svg` (§65; `currentColor` black),
  then every drawn element (`path rect circle ellipse line polyline polygon use`, not inside
  `defs` / `symbol`) is marked with its owner: the nearest enclosing element whose id names a part
  (`part_key`: `<part>` → the rest shape, `<part>_<shape>` → another shape; the longest part name
  wins, so `arm_left_up` is arm_left's `up`). An id of the same part inside its element does not
  start a new shape (`head_outline` in `head` is a piece of the head). Shapes with no owner belong
  to `body` (rest), except shapes hidden in the file there (`display: none` / `visibility:
  hidden`, inherited), which are dropped; hiding is reset inside a part element (alternatives are
  hidden in the file). Rest names: `REST_SHAPE_NAMES` (`eyes` → `open`, `mouth` → `smile`, as the
  generator), else `rest`. Each (part, shape) becomes its own document: a copy of the sanitised
  file with the other owners' shapes removed and its element and ancestors un-hidden, so
  inherited styles and transforms and the viewBox box stay. Parts keep the order of their first
  drawn shape in the file; the rest shape first, then the others in file order.
- **Pivots**: `data-pivot="x y"` (or `x,y`) on a part's element, in viewBox coordinates (the
  rest element's wins over an alternative's). Without it, `default_pivot` from the rest shape's
  box in character units: head / body bottom centre, legs top centre, an arm the top corner
  nearer the body's centre, others the centre. `pivot_warnings` names `TURNING_PARTS` (head, arms,
  legs) without one.
- **Problems** (`VidgenError`): a missing / unreadable file, what the sanitiser refuses, two
  elements naming the same (part, shape), a `data-pivot` that is not two numbers, no body.
  **Warnings** (`SvgCharacter.warnings`): ids that look like misspelt part names (`_near_miss`:
  lower case / `-` → `_` names a part, or difflib ≥ 0.8: `Mouth`, `arm-left`, `eye`), a non-rest
  shape the file shows, a part element that draws nothing.
- **Shapes** (`svg_character_parts(path, where) -> list[CharacterPart]`, manim): each document
  is parsed with `vector_mobject.svg_shapes` (factored out of `load_vector`: `SVGMobject` of the
  work copy, the invisible box first) and moved so its viewBox's top-left corner is the origin
  (Manim flips y about each drawing's own centre, so documents are aligned by their box). The
  rest shapes' union box gives the character units: bottom = feet height, x = the middle of the
  `legs` box (else `body`), top → 1. Stroke widths: `vector_mobject.set_svg_stroke` (also
  factored out of `load_vector`) with the factor for a character `REFERENCE_HEIGHT` tall, so
  `Character` scales them with `height` like a generated outline; fill-only shapes get a zero
  outline in their fill colour. Parent: `DEFAULT_PARENTS`, walking up to a part the file has (no
  head: the eyes hang from the body). Draw order: the file's order (`order = 10 × index`). The
  SVG's colours are kept (`colors:` unused). `Character(..., required=SVG_REQUIRED_PARTS)` (only
  `body`).
- **Actions a character cannot do** (`cast.ACTION_NEEDS`: action → alternatives of parts or
  `part.shape`; `unavailable_actions(part_shapes)`, `missing_needs(part_shapes, action)`): `say`
  mouth (Step 69 called it `say (lip sync)`), `blink` eyes.closed, `look_at` head, `emote` eyes or
  brows or mouth, `gesture: point` / `wave` an arm, `shrug` both arms, `nod` / `shake_head` head.
  Actions name their entry with `Action.character_needs()` and skip what a character lacks;
  `vidgen validate` warns per use (§69.11).
- **Validate**: `cast.character_look_problems(config, root)` (in `cli.project_problems`:
  `characters[k].look.svg: ...`); `cast.character_look_warnings(config, root)` (in
  `cli.validate_warnings`): the sanitiser's warnings, the split warnings, guessed pivots,
  `colors` given (unused), a mouth with one shape (it will not move when speaking), and
  `character 'x' (FILE): actions unavailable: gesture: wave (needs arm_left or arm_right); ...`.
- **`vidgen character NAME`**: for an svg look prints `look: svg FILE`, `parts: arm_right, legs,
  body, ..., eyes (open, closed), mouth (smile, A, E, O, M)` (`character_lines(entry, theme,
  root)`) and `colors: the SVG's own`; `--png` works unchanged.
- **Fingerprint**: a file under `assets/` is part of every scene's fingerprint (its stat); a
  file elsewhere is not (documented: keep it under `assets/`).
- **Example**: `examples/svg_character` (`assets/sprout.svg`, an original figure: every part,
  `eyes_closed`, `mouth_A` / `_E` / `_O` / `_M`, pivots), with a generated character beside it.
  Tests: `tests/test_cartoon_svg.py`.

### 69.3 Poses and expressions (Step 70)

Named poses and expressions are tables of part settings, applied with `set_state`; a change
between two of them is the `PoseChange` animation.

- **Tables** (`cartoon/poses.py`, no manim): `POSES` (`stand, pointing, waving, thinking, shrug,
  arms_crossed, sitting`) and `EXPRESSIONS` (`neutral, happy, sad, angry, surprised, worried,
  thinking`; since Step 125 `laughing, blushing, tongue_out, crying, dizzy, frightened`, §69.59),
  each name -> part -> `PartPoseEntry(angle, scale, shift, shape)` (the config model of
  `poses:`, so built-in and own entries are one type). A pose sets `POSE_PARTS` (`body, legs,
  arm_left, arm_right, head, accessory`), an expression `EXPRESSION_PARTS` (`eyes, brows, mouth`;
  since Step 125 `cheeks, bristles`),
  so one of each combines; the parts of its group an entry does not name go back to rest (`stand`
  is empty: everything at rest). Values are relative to the rest drawing: arms hang down, so
  `pointing` turns `arm_left` (the near arm facing right) +88°; `sitting` lowers `body` 0.1 and
  turns `legs` +80°; the rest mouth is a smile, so `sad` / `angry` / `worried` flip it with a
  negative y scale. `shape` is a list of choices (`surprised`: mouth `open`, `O`, `A`): the first
  the character has (`chosen_shape`), else the rest shape. A part the character lacks is skipped.
  So every entry works on generated characters (brows gain the shapes `angry` / `sad`, inner ends
  low / high) and on SVGs (`brows_angry` if the file has it; otherwise only the shift).
- **Character** (`cartoon/character.py`): `Character(..., poses=, expressions=)` takes the
  character's own tables; `names(kind)` (built-in first, then own; an own entry with a built-in
  name replaces it), `posed_state(pose=None, expression=None) -> CharacterState` (the current
  state with the entries applied; nothing drawn), `set_pose(name)`, `set_expression(name)`.
  Unknown names raise `VidgenError` from `poses.find_entry`: `character 'pip': unknown pose
  'pointng'; did you mean 'pointing'? poses: stand, pointing, ...`. `build_character` passes the
  entry's `poses` / `expressions`.
- **Own entries** (`characters[].poses` / `.expressions`, config): name -> part -> `{angle, scale,
  shift, shape}`; a part outside the group, a zero scale or an unknown key is a config error.
  `vidgen validate`: `cast.character_pose_problems` (a `shape` none of whose choices the
  character has: `characters[0].expressions.grin.mouth.shape: character 'pip': part 'mouth' has
  no shape 'wide' (shapes: smile, open, A, E, O, U, M, F, L, W)`) and `character_pose_warnings` (a part the character
  does not have). Shapes are known without drawing: an svg look's from `read_character_svg`, a
  generated one's from `cast.GENERATED_SHAPES` (a test keeps it equal to the generator's).
  `vidgen character NAME` lists the known names (`cast.pose_lines`; own ones marked `*`).
- **`PoseChange(character, *, pose=None, expression=None, state=None, facing=None,
  lag_ratio=0.15, part_rate_func=smooth, **animation_kwargs)`** (`cartoon/transition.py`,
  exported): the target is resolved when it is created, the start when it begins. Each part
  whose `PartPose` differs gets a window (`part_windows`: parts in `PART_NAMES` order, i.e. body,
  legs, arms, head, then the face, each starting `lag_ratio` of a window after the previous; the
  last ends at 1) and eases in it with `part_rate_func`; `blend_poses` mixes angle, scale and shift
  linearly and switches the shape at the halfway point. The character is redrawn with
  `set_state` each frame, so a turning part sweeps an arc about its pivot (not a cross-fade, not
  `.animate`'s straight lines). `rate_func` (default `linear`) maps the animation's time first.
  A facing change switches the mirror at the halfway point. `state=` with `pose` / `expression`
  is a `TypeError`.
- **Not done here**: no action uses poses yet (Step 78); the `stage` scene (§69.6) starts its
  characters in a pose / expression. Blinking (Step 72,
  §69.5) never shows during a `PoseChange`: `begin` calls `Character.end_blink()`. Tests: `tests/test_cartoon_poses.py`.

### 69.4 Lip sync: viseme tracks (Step 71)

A beat's **viseme track** says which mouth shape shows when; a character's mouth follows it.
`cartoon/visemes.py` (no manim) builds and stores tracks; `Character.lip_sync` plays one.

- **Visemes** (`VISEMES`): `rest, A (also I), E (and most consonants), O, U, M (M B P), F (F V),
  L (L, TH), W (W Q)`, the nine Preston Blair groups; their names are the SVG mouth shape names
  of §69.2. `VISEME_SHAPES` gives each viseme's mouth shapes in order of preference (`U`: `U, O,
  W, open`; `M`: `M` only; `F`: `F, E, M`; ...); none present (and `rest`) shows the rest shape.
  Generated characters (§69.1) gain the mouth shapes `A E O U M F L W` (filled ellipses in the
  `features` ink, `M` a line), so every viseme has its own shape; `cast.GENERATED_SHAPES` follows.
- **Phonemes -> visemes** (`PHONEME_VISEMES`, one code point each): IPA from espeak-ng / misaki
  and misaki's diphthong letters (`I` = aɪ -> `A, E`, `O` = oʊ -> `O, U`, `W` = aʊ -> `A, U`, `Y`
  = ɔɪ -> `O, E`, `A` = eɪ -> `E`). Stress and length marks, `h`, the glottal stop and anything not
  listed take no time. `phoneme_units` gives (viseme, weight): vowels 2, consonants 1 (a
  diphthong splits its 2), a space a `rest` of 0.5. **Letter fallback** (`letter_units`): digraphs
  (`th` L, `ph` F, `sh` / `ch` / `ck` / `ng` E, `wh` / `qu` W, `oo` U, `ee` E, `gh` silent), then
  letters (`a` A; `e i y` E; `o` O; `u` U; `m b p` M; `f v` F; `l` L; `w q` W; `h` silent; other
  Latin letters E; digits and other scripts A), a silent final `e` dropped where
  `language_rules(...).silent_final_e` (checked before accents are removed: a final `é` is said).
- **Phoneme sources** (`SOURCES`): `kokoro` — `KokoroProvider.last_phonemes`, set by every
  `synthesize_timed`: `(token.phonemes, start, end)` per timed token (English), else `(result.phonemes,
  chunk start, chunk end)` per chunk. Otherwise the spoken text, word by word, through
  `text_g2p(language)`: the first of `G2P_BACKENDS` that loads — `misaki` (English: `en.G2P(trf=False,
  british=en-GB/IE/AU/NZ, fallback=None)` only when `en_core_web_sm` is importable, since misaki
  would pip-install it; other languages: `espeak.EspeakG2P` when `espeakng_loader` is importable),
  then `espeak` (the `espeak-ng` program on `PATH`: `-q --ipa -v <voice> <word>`, voice = the tag
  lower-cased, `en` -> `en-us`) — else `letters`. A word the G2P fails on or gives nothing for
  uses its letters. Nothing is installed by vidgen; none is needed (tests mock them).
- **Timing** (`TIMINGS`): Kokoro's token times (`kokoro`), else the words of
  `speech.beat_word_times(audio_dir, beat, spoken_text, 0, duration, language)` — the stored
  alignment (`alignment`: ElevenLabs timestamps or Kokoro's `.align.json`), else the estimate
  within the MP3's speech (`speech`), else over the beat (`estimate`). Each word's (or token's)
  units share its time by weight (`cues_from_units`); `rest` fills the time between words and
  around them, 0 .. the beat's duration (the MP3's length).
- **Merge rule** (`merge_short_cues`, `MIN_CUE_SECONDS = 0.07`, two frames at 30 fps): neighbours
  of one viseme join; then, shortest first, a cue shorter than the minimum goes to its longer
  neighbour (the earlier on a tie), joining again, until none is short or one cue remains. A short
  `M` is instead lengthened to the minimum from its longer neighbour when that one stays at least
  the minimum (closed lips that never show read as mumbling). The cues stay contiguous.
- **Storage** (`.visemes.json` next to the MP3, `write_visemes` / `read_visemes`): `{version: 1,
  text (spoken), audio_sha1, source, timing, cues: [[start, end, viseme], ...]}` (seconds, 4
  decimals). Like `.align.json`, it is used only while the MP3's sha1 and the spoken text match
  (`speech.audio_digest`, made public; reads cached by mtime). `vidgen tts` (`run.py`) writes it
  for every voiced or copied beat **when the video declares `characters:`** (`_store_visemes`: a
  copied beat's stored track is copied; else built with Kokoro's phonemes or from the text), and
  after the run writes the missing tracks of up-to-date beats (`_store_missing_visemes`: "wrote
  viseme tracks (lip sync) for N beat(s) already voiced"; a beat whose MP3 cannot be read gets a
  `note:`). The beat's `.hash` is unchanged (the track never re-voices a beat).
- **Reading** (`beat_visemes(project, beat_id, duration=None) -> VisemeTrack`; scene shortcut
  `NarratedScene.beat_visemes(beat)` with `beat_duration`): the stored track while current, else
  built from the spoken text in memory (not written, so rendering never changes the inputs of its
  own fingerprint). `VisemeTrack(cues, source, timing)`: `duration`, `at(seconds)` (`rest`
  outside the cues).
- **Fingerprint**: in a video with `characters:`, each scene's fingerprint has `visemes`: the
  stat of every beat's `.visemes.json` and `.align.json` (videos without characters keep their
  fingerprints' shape).
- **Character** (`cartoon/character.py`): `viseme_shape(viseme)` (the first of `VISEME_SHAPES` it
  has, or `None`; an unknown viseme is a `VidgenError`), `show_viseme(viseme, rest=None)` (sets
  the mouth's pose shape; swaps only when the shape changes), `lip_sync(track, *, start=0.0,
  clock=None)`: adds the updater `Character._lip_sync_step` (a plain method, like idle's) that
  shows `track.at(seconds)`; `seconds` is `clock()` when a clock is given (Step 78: the scene's
  time since the beat started, `NarratedScene.beat_clock`), else `start` plus the frames' `dt`.
  The viseme's shape is a layer over the mouth's pose (`_spoken`, shown by `_shape_name`), so the
  pose (the expression's shape, scale and angle: a `sad` flipped mouth speaks flipped) is never
  changed; `rest`, or a viseme without a shape, shows the pose's shape, also one set while
  speaking. It replaces a running lip sync; `stop_lip_sync()` removes the layer; `lip_sync_track`
  is the running track; `sync_mouth()` shows the viseme for the clock now. No mouth: all do
  nothing (`ACTION_NEEDS["say"]`). Manim suspends a mobject's updaters while an `Animation` plays
  on it: `PoseChange` calls `sync_mouth()` on every frame, so with a clock the mouth stays in
  step through a pose change; other animations on the character hold it, and it catches up when
  they end (Step 72 left this open: the `dt` clock fell behind by every such animation).
- **API**: `vidgen.api` exports `VISEMES`, `VisemeCue`, `VisemeTrack`; `Character.lip_sync`,
  `stop_lip_sync`, `show_viseme`, `viseme_shape`; `NarratedScene.beat_visemes`.
- **Also**: `audio_duration` moved from `scene.py` to `speech.py` (no manim; `scene` re-imports
  it), so `vidgen tts` measures MP3s without loading Manim.
- **Speaking** (Step 78, §69.11): a `stage` makes the characters with the beat's voice speak; the
  `say` action picks them instead. No per-language phoneme tables beyond IPA; no coarticulation (each
  phoneme is one shape). Tests: `tests/test_cartoon_visemes.py`.

### 69.5 Automatic life: blinking and idle motion (Step 72)

A character from `characters:` breathes, sways its head slightly and blinks on its own, so it
does not freeze between actions. The motion is a layer on top of the poses, driven by one
updater, so `PoseChange` (§69.3) and `lip_sync` (§69.4) never fight with it.

- **Schedule** (`cartoon/idle.py`, no manim): blinks start `next_blink_gap(rng)` apart on the
  character's *idle clock*, uniform in `BLINK_GAP_SECONDS = (2, 6)` from `random.Random(seed)`
  (`random()` only, as in §69.1, so a seed gives the same blinks on every Python version), the
  first one a gap after the clock starts; each keeps the eyes `closed` for `BLINK_SECONDS = 0.15`.
  The seed defaults to `idle_seed(name)` (CRC-32 of the name), so two characters do not blink
  together. Breathing: `breath_scale(seconds, seed)` scales the body about its pivot (the bottom
  of the body; its children follow) by at most `BREATH_SCALE = (0.006, 0.015)` (x, y), one breath
  every `BREATH_SECONDS = 3.6`; head sway: `sway_angle(seconds, seed)` turns the head by at most
  2 × `SWAY_DEGREES = 1.5`° every `SWAY_SECONDS = 5.5`. Both are 0 at the clock's start (the
  phases come from the seed), so a still at time 0 is the plain pose.
- **Idle clock and pose changes**: the clock advances by each frame's `dt` in the updater, and
  Manim suspends a mobject's updaters while an animation plays on it, so the clock stops during a
  `PoseChange` (and any other animation played on the character): no blink starts there, and the
  breath and sway hold. `PoseChange.begin` calls `Character.end_blink()`, so a blink running when
  it starts ends at once (it is not resumed). `blink_times(seed, duration, *, pose_changes=())`
  gives exactly this schedule in scene seconds, `(start, end)` per blink, without drawing: the
  idle clock mapped past each pose change window (a blink due at a window's start comes after
  it), a blink cut at the start of the next window. `IdleClock` (seed, `seconds`, `advance(dt)`,
  `is_blinking`, `end_blink()`) is the running state the updater keeps; a test checks it against
  `blink_times` frame by frame.
- **Character** (`cartoon/character.py`): `start_idle(seed=None)` adds the updater
  `Character._idle_step` (a plain method, so `copy()` gets its own clock), `stop_idle()` removes
  it and the layer, `end_blink()`, `is_idle`, `shown_shape(part)` (the shape on screen, a blink
  included). The layer is `_overlays`: part -> `PartPose` (body: scale; head: angle; eyes: shape
  `closed` while blinking), applied after the part's pose about the same pivot (`world(part) =
  world(parent) · pose(part) · overlay(part)`); an overlay's shape is shown instead of the
  pose's. `state()` / `set_state()` / `posed_state()` hold the poses only, so `PoseChange` blends
  and stores no idle values, an expression set during a blink shows once the blink ends, and the
  mouth (lip sync) is never touched by the layer. A character without `head` does not sway;
  without an `eyes` shape `closed` it does not blink (`ACTION_NEEDS["blink"]`, §69.2).
- **Config**: `characters[].idle: bool = True`; `build_character` (so `character(name)`) calls
  `start_idle()` unless it is false. A `Character` built directly from parts does not idle until
  `start_idle()`.
- **Per scene**: the `stage` scene's `idle: false` calls `stop_idle()` on its characters (§69.6).
- **Not done here**: `PoseChange`, `Walk`, `Gesture` and `Jump` (§69.12) end a running blink;
  another animation played on the character (e.g. `.animate.shift`) holds the eyes as they are
  until it ends. Lip sync (§69.4) has
  its own clock (the scene's time since Step 78), so it does not fall behind during an animation.
  Tests: `tests/test_cartoon_idle.py`.

### 69.6 The `stage` scene type (Step 73)

A built-in scene type (`scenes/stage.py`) that puts the video's characters on a set: a
background, a ground line, named marks and depth. Its geometry lives in `cartoon/stage.py` (no
manim), so it is tested without rendering and later steps (props, Step 75; walking, Step 79;
lint, Step 84) reuse it.

- **Geometry** (`cartoon/stage.py`): x positions are fractions of the frame width (0 = left
  edge), the ground line's height a fraction of the frame height above the bottom edge, sizes
  fractions of the frame's shorter side (8 units in every aspect, so a character is as tall in 9:16
  as in 16:9). `MARKS` = `far_left 0.1, left 0.25, centre 0.5, right 0.75, far_right 0.9`; a
  stage's own `marks` are added (same name: its own wins). `mark_x(at, marks)` (a mark or an x in
  0..1; `ValueError` with did-you-mean and the known marks otherwise). Depth 0..1:
  `depth_scale(d) = 1 - (1 - FAR_SCALE) d` (`FAR_SCALE = 0.55`), the feet `FAR_RISE = 0.12` × the
  frame height higher at depth 1 (`feet_point`). `draw_order(depths)`: deeper first, ties in list
  order. `stage_layout(items, marks=, ground=, size=, frame_width=, frame_height=) ->
  [StagePlacement]` in draw order: `StageItem(name, kind, at, depth, scale, lift=0)` in, `StagePlacement(name, kind,
  index, x_fraction, depth, feet, height)` out (`height = size × short side × scale ×
  depth_scale`; `lift`, Step 75, raises the feet by that fraction of the frame height). `kind`
  is `character` or `prop` (§69.8); both sort together by depth. `facing_towards_centre(x)`: `right` on the left half and in
  the middle, else `left`.
- **Params** (`Stage.Params`): `image` (a file, checked by `image`'s `check_image`; raster via
  `load_image`, `.svg` via `load_vector`) or `generate` (a top-level `GenerateImage`, so `vidgen
  imagegen` finds it like `image`'s; a placeholder until made) — both scaled to cover the frame,
  centred, named `background`; else `background`: a colour or a list of two or more (a vertical
  gradient: one `Rectangle` filled with the colours, `sheen_direction` DOWN, first colour at the
  top); none: nothing drawn (the theme's background). `image` with `generate`, or either with
  `background`, is an error. `ground` (0..0.6, default 0.2); `ground_color` (a band from the
  bottom edge up to `ground_top(ground, items)`: the ground line, or the line where the deepest
  character or prop on the ground stands, §69.22; named `ground`; default `surface` without a picture, nothing
  with one; `false`: nothing). `marks` (identifier -> 0..1). `size` (0.45). `idle` (true). `cartoon_motion` (none: the video's; §69.13).
  `characters: list[StageCharacter]` (a string is the name): `name: CharacterName`, `at` (mark or
  x), `depth` 0..1, `scale` (0, 3], `facing` `auto | right | left`, `pose`, `expression` (none:
  rest). A name twice or an unknown mark is a params error (`characters[k].at: unknown mark ...`).
  `validate_project` checks the image file and each pose / expression with
  `cast.pose_name_problem` (exported; the built-in and the character's own tables) (`characters[0].pose: character 'kit': unknown pose 'pointng';
  did you mean 'pointing'? poses: ...`); the name itself is the `CharacterName` check.
- **Construct**: `stage_layout` with the frame size; each character is `character(name,
  height=placement.height, facing=...)` (the theme's colours, idle running unless the entry says
  `idle: false`), then `set_pose` / `set_expression`, `stop_idle()` when the scene says `idle:
  false`, and shifted so `feet()` is the placement's feet. **Starting state** is this minimal
  pose / expression / facing per character; actions change it later (Step 78). One reveal step:
  the backdrop parts fade in with every character's entrance (targets registered back to front,
  so the fade-ins add, and Manim draws, them in that order); later beats hold (idle motion
  runs); `finish()` fades out (outro 0.5 s).
- **Targets**: each character by its name (`target_patterns = ("<character>",)`), so `dim`,
  `highlight`, `zoom`, `reveal` and `callout` work on characters today.
- **Layout dump / lint**: `introspect` reports a `Character` as one object of kind `character`
  whose `name` is the character's (its box: every drawn part; the invisible anchor has opacity 0
  and is left out); the picture or colour is `background`, the band `ground`. `lint`'s
  `describe` names it `character 'pip'`, and `lint_ignore` matches it by that name. The rules specific to characters are §69.12's
  `walk_overlap` and §69.17's.
- **Guide and gallery**: the author guide's `scenes` topic has a `# cartoons` block that is a
  config (`characters:` + `scenes:`), since a stage needs declared characters. `gallery.guide_samples`
  reads such a block as one sample per scene, shown whole, with `Sample.characters`;
  `work_config` adds the samples' characters to the work project. `tests/test_guide.py` accepts
  both block forms.
- **Hooks for Step 78+**: `Stage.cast` (name -> `Character`, back to front) is set in
  `construct`. Step 78 (§69.11) built speaking (`Stage.narrate`) and the acting actions on it;
  walking (Step 79, §69.12) moves the feet along the ground line at the character's depth (it
  keeps its depth, so the draw order stays).
- **Not done here**: props (Step 75), speech and acting (Steps 78–79, §69.11), cartoon lint
  rules (Step 84). Parallax layers, a stage wider than the frame and the camera actions are Step 74 (§69.7).
  Tests: `tests/test_cartoon_stage.py`.

### 69.7 Parallax layers and the camera on a stage (Step 74)

A `stage` can be wider than the frame and have layers (pictures or shapes) that move by a
*parallax factor* when the camera moves. The camera moves with beat actions: the existing `zoom`
and the new `pan` and `follow`, which are generic (any scene type) and reuse `MoveCamera`.

- **Layer offsets** (`cartoon/stage.py`, no manim): a layer is drawn for the camera's *home view*
  (centre at the origin = the stage's centre, zoom 1). `layer_transform(factor, camera_center,
  zoom) -> (scale, (dx, dy))` gives the move that makes it appear moved by `factor` × the
  camera's move and magnified by `zoom ** factor` (zoom = frame width / view width): a home point
  `b` is put at `k b + c (1 - factor k)`, `k = zoom ** (factor - 1)`, so it shows at `zoom **
  factor (b - factor c)` from the view's centre. Factor 1 (the stage, its ground and characters):
  no change; 0: fixed on screen; < 1 far, > 1 near. `layer_half_extent(factor, stage_width=,
  frame_width=, frame_height=, max_zoom=MAX_ZOOM (8))` is the half size a layer must cover so no
  view inside the stage at zoom 1–8 shows its edge (`half view / z ** factor + factor × the
  farthest view centre`, maximised over a 64-step grid of `z`; a test checks random views).
  `LAYER_PLACES = (background, middle, foreground)`, `DEFAULT_FACTORS` 0.3 / 0.6 / 1.4.
- **Camera bounds** (`camera.py`, no manim): `view_center_within(bounds, center, width, height)`
  clamps a view's centre into `(left, right, bottom, top)` (the bounds' middle on an axis where
  the view is larger). `NarratedScene.camera_bounds()` is the frame; `Stage` returns its width ×
  the frame height. `zoom` now clamps with it (was the frame), so a zoom on a wide stage stays on
  the stage.
- **Stage params** (§69.6 plus): `width` (1–4 frame widths; marks and x are fractions of the
  stage, `stage_layout(..., stage_width=)`; a reframing stage in a frame narrower than 16:9
  counts in 16:9 frame widths, §69.30; sizes still follow the frame's shorter side; the
  picture covers the stage, the colour / gradient and ground band span it), `camera_at` (a mark
  or x: the view's centre at the start, clamped), `layers: [StageLayer]` = `{name, place,
  factor, image | shapes, bottom}` (one of `image` / `shapes`; names default to
  `<place>_layer`, then `_2`...; a name twice is an error; `validate_project` checks layer
  images with `check_image`). An image layer is scaled to the layer's width (`2 × half extent`)
  with its bottom edge at `bottom`; shapes (`LayerShape`: `rect`, `ellipse`, `triangle` at `x`
  of the stage and bottom `y` of the frame height, `width` / `height` of the short side, `color`;
  `hills`: `hill_outline`, a row of sine-arc hills over the layer's whole width filled down to
  its lower extent). Draw order: picture / colour, background then middle layers, ground band,
  characters (back to front), foreground layers; the entrance fades them in in that order.
  `Stage.layers` (name -> mobject) like `Stage.cast`. Each layer mobject is named after it
  (layout dump, lint).
- **Moving the layers**: the stage keeps every layer member's points at the home view
  (`_Parallax`) and, when some factor is not 1, registers `_move_layers` with
  `NarratedScene.add_camera_listener`: on every frame each member's points are set to `home ×
  scale + shift` for the camera now. Starting from the home points (not the last frame's) means
  an animation of the layer (its fade-in copies points) can never shift it.
- **Camera driver** (`NarratedScene`): `follow_with_camera(x_of)` (a callable giving the x to
  follow; `None` stops; `camera_following` reads it) and `add_camera_listener(callback)` share
  one scene updater, `_camera_step`: first the follow (the frame's centre x set to `x_of()`
  inside `camera_bounds` at the view's size), then the listeners. A scene updater runs after
  every animation and mobject updater of the frame, and Manim never suspends it (a `MoveCamera`
  suspends the frame's own updaters), so layers move during a zoom or pan and never lag a frame.
  While the camera follows something, `get_moving_mobjects` returns every mobject: otherwise
  Manim draws the ones before the first moving mobject once into a static image, for the camera
  as it was (with listeners only, Step 87 lets Manim keep that image; §69.20).
- **`pan`** (`scenes/actions.py`; run_time 1.5, reversible, not temporary, `needs_target =
  False`, moves_camera): option `to` (a mark name or an x 0..1 of `camera_bounds`' width) or a
  target (one of the two: `problems`). Ends a `follow`, then a `MoveCamera` keeping the view's
  size and y (Step 96: `cut: true` moves the frame at once, §69.30). `until` moves back to the view before. Marks: the new classmethod
  `NarratedScene.camera_place(params, place)` (a number is itself, a name `ValueError`; `Stage`:
  `mark_x` with its own marks), checked at validate time through the new hook
  `Action.scene_problems(scene_cls, params)` (called by `scene_actions` when params are valid).
- **`follow`** (run_time 1.0, reversible, moves_camera; one target pattern): pans to the target
  (`_MoveThenFollow`, a `MoveCamera` that calls `follow_with_camera` in
  `clean_up_from_scene`, so it starts after the move, also when the runner applies it without
  animation) and then follows it to the end of the scene; `until` stops following (the camera
  stays), unless a later `follow` took over. A `Character` is followed by its `feet()` x (a
  pointing arm does not move the camera), anything else by its centre.
- **`zoom` coming back**: `revert` returns to the view *before the zoom* (`camera_view` /
  `move_camera_back`), not to the whole frame. Without other camera moves it is the same; after
  a `pan` or on a stage with `camera_at`, the camera no longer jumps home.
- **Lint**: `StillContext.camera_moved` (zoomed, or the view's centre away from the frame's
  centre); `off_frame` and `safe_area` skip such stills (they skipped zoomed ones).
- **Not done here**: a followed character that walks (§69.12) is followed by x only (the view's
  y and zoom stay; a `follow` due with a walk plays with it and catches up, §69.12); `zoom` on another character while following keeps the followed one in the
  middle. An image layer's bottom stays at `bottom`, so a near layer (factor > 1) zoomed in at the
  bottom of the stage can show a sliver below it. No vertical pan. Layers are not action targets.
  Tests: `tests/test_cartoon_parallax.py`.

### 69.8 Props (Step 75)

Things on a stage that are not characters: built-in props drawn from primitives, or SVG files.
They are placed by the same `stage_layout` as the characters and sort with them by depth.

- **Built-in props** (`cartoon/props.py`): `PROP_KINDS = table, chair, tree, bush, house, door,
  lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup` (and `basket, umbrella,
  napkin` since Step 103, §69.37; twelve pieces of furniture since Step 110, §69.43). Each is drawn in *prop
  units* (feet at the origin, `y` up, top at 1) from rectangles, rounded rectangles, circles,
  ellipses, polygons (some with rounded corners), lines and `Union`s of circles (a tree's crown,
  a bush, a cloud: one outline). Colours: two per prop, `main` and `detail` (`PROP_COLORS`, theme
  tokens, except the cloud's fixed light `#F4F6FA` and the window glass `GLASS`), plus shades of
  them (`SHADE` 0.25 towards black, `LIGHT` 0.4 towards white) and the characters' outline ink
  `CHARACTER_INK`, stroke `OUTLINE_WIDTH`. Every shape is original; no option names or imitates
  a known design.
- **`Prop(VGroup)`**: `name`, `kind` (a `PROP_KINDS` name or `svg`), `facing`; `feet()` is the
  middle of its bottom edge. `draw_prop(kind, *, height, theme, name=None, main=None,
  detail=None, facing="right", character_height=None)` scales the drawing to `height` and its
  strokes like a character's of `character_height` (`scale_strokes` / `one_pixel_stroke` of
  `character.py`, made public for this), so a cup and a house next to a character share its
  outline width; `facing="left"` mirrors it. `svg_prop(path, *, height, name, theme=None,
  recolor="none", facing="right", where=None)` loads the file with `load_vector` (sanitised by
  `svgclean`, sanitiser warnings logged; `recolor: theme` maps colours to the theme's) and stands
  it on the bottom edge of its `viewBox`.
- **Sizes**: `PROP_HEIGHTS` gives each prop's height relative to a character (the stage's
  `size`): table 0.42, chair 0.26, tree 1.7, bush 0.35, house 1.6, door 1.0, lamp 1.5, sign 0.75,
  box 0.155, ball 0.18, cloud 0.35, sun 0.4, moon 0.35, rock 0.155, plant 0.4, laptop 0.14, cup 0.09,
  basket 0.2, umbrella 0.6, napkin 0.05 (chair 0.5, box 0.3, rock 0.22 before Step 102, §69.36);
  an SVG `SVG_PROP_HEIGHT` 0.5. The stage passes `height factor × scale` as the item's `scale`.
  `PROP_LIFTS`: `cloud`, `sun`, `moon` hang 0.5 of the frame height above the ground line unless
  `lift` says otherwise.
- **Stage params**: `props: list[StageProp]`; a string is a built-in prop's name. `StageProp`:
  `prop` (one of `PROP_KINDS`) or `svg` (a `.svg` file relative to the project; one of the two),
  `name`, `at` (mark or x), `depth`, `scale` (0, 5], `lift` (0..1 or default), `facing` (`right`
  | `left`), `color` / `detail` (built-in props only), `recolor` (`none` | `theme`, SVG only).
  Names default to the prop's name (an SVG: its file stem made an identifier), numbered from the
  second (`tree`, `tree_2`, `Params.prop_names`). Errors: a name twice, a prop named like a
  character on the stage, an unknown mark (`props[k].at: ...`), both or neither of `prop` / `svg`.
  `validate_project` checks SVG files with `image`'s `check_image` (missing, sanitiser refusal).
- **Construct**: `Params.items()` lists the props first, then the characters (`StageItem(name,
  "prop", at, depth, height factor, lift)`), so at the same depth a character is drawn in front of
  a prop (a character behind a table: give it a larger depth). Each placement builds its prop or
  character; all are registered as targets back to front (they fade in with the set at step 1).
  `Stage.props` (name -> `Prop`, back to front) next to `Stage.cast`.
- **Targets**: `target_patterns = ("<character>", "<prop>")`; `target_names` = the characters,
  then the props. `dim`, `highlight`, `zoom`, `pan` / `follow` (by its centre) work on props.
- **Layout dump / lint**: `introspect` reports a `Prop` (an SVG one too, not a `vector`) as one
  object of kind `prop` named after it; `describe` gives `prop 'tree'`.
- **Gallery still**: `still.write_props_png(theme, path, width=960, height=540)` draws every
  built-in prop with its name in a 6-column grid, a prop with shapes once per shape (`umbrella`,
  `umbrella (open)`; 64-colour palette PNG, about 20 KB):
  `docs/gallery/media/props.png`, shown in CONFIG.md.
- **Not done here**: putting a prop on another one (`lift` is in frame heights: a laptop on a
  table needs the table's height worked out by hand); props do not move or animate (Step 79's
  motion, Step 76's particles; Step 93's characters carry and throw them, §69.27). An SVG prop outside `assets/` is not in the scene fingerprint.
  Tests: `tests/test_cartoon_props.py`.

### 69.9 Particles (Step 76)

Rain, snow, sparkles, dust, confetti, smoke and bubbles: a field of small shapes that falls,
drifts, spins or rises over a scene. On a `stage` for the whole scene (`particles` param); on any
scene type from a beat (the `particles` beat action). Nothing like it existed before (the
cookbook's `_looping_particles` is an example file, not library code), so the step adds the model
and reuses the action machinery rather than overlays. (Step 105 makes rain on a `stage` end on
its ground and shelters, with splashes, puddles and a rain sound bed: §69.39.)

- **Model** (`particles.py`, no manim): `PARTICLE_KINDS = rain, snow, sparkles, dust, confetti,
  smoke, bubbles` (Step 104 adds `leaves` and `streaks`, §69.38); `KINDS` (kind -> `ParticleKind`: shape `streak | dot | star | chip | ring`,
  `count` per whole frame at density 1, size range, `fall` (negative: rises), speed range,
  `drift` (rain's slant, or a random one for dust), sway amplitude / Hz, `spin`, `twinkle`,
  `grow`, opacity, default colours). Sizes and speeds are fractions of the frame's shorter side
  (per second). `particle_seeds(kind, count, seed, colors)` draws each particle's start from
  `numpy.random.default_rng([seed, kind index])` once; `particle_states(seeds, t, width, height)`
  is a pure function of the time: positions are fractions of the area (`y` from the top, like a
  callout's area), wrapped into 0..1 (a particle leaving one edge comes back at the other), faded
  within `EDGE_FADE` 0.06 of the area's edges; rain is tilted along its fall, confetti spins and
  tumbles (`flip`, a width factor), sparkles twinkle (`sin²`), smoke grows by `grow` and thins out
  as it rises. `particle_count(kind, density, area_share, preview=)` = the kind's count × density
  × the area's share of the frame, at most `MAX_PARTICLES` 300, at preview quality
  `PREVIEW_SHARE` 0.5 of that (rounded up), at least 1. `check_area` checks `[x, y, w, h]`.
- **Drawing** (`particle_field.py`): `ParticleField(VGroup)` holds one `VMobject` per particle
  with the unit shape's points; `draw_at(now)` sets every particle's points (unit points scaled,
  flipped, rotated, moved) and fill / stroke alpha from `particle_states` at `now - start`, over
  the part of the scene the camera shows (`scene_view`: the `camera.frame`), sizes scaled with the
  view, so particles stay on screen and the same size through a `zoom`, `pan` or `follow`. Its
  clock is the scene's `renderer.time`, so the look at a frame does not depend on how often the
  updater ran. A time-based updater calls `draw_at` (a wait with a field draws every frame);
  `suspend_updating` is a no-op, so an animation of the field (the outro's fade) never freezes
  it. Fade in: `FADE_IN` 0.5 s from its start; fade out: `fade_out_animation()` (`_FieldFadeOut`,
  a remover that takes `level` to 0 while the particles keep moving). `helpers.fade_out` uses a
  mobject's own `fade_out_animation` when it has one, so `clear_all` / `finish()` fade fields that
  way. `particle_field(scene, kind, settings)` builds a field for a running scene (count from
  `scene.is_preview`, colours resolved with the theme, `z_index` one above everything on screen).
  `ParticleSettings` (a pydantic model): `density` (0, 4], `area`, `color` (one or a list; each
  particle picks one by its seed), `seed`.
- **Preview quality**: `NarratedScene.is_preview` (default `False`) is set by the render worker
  (`render_scene`) before the scene renders; preview and final renders live in separate build
  folders, so it needs no fingerprint entry.
- **The `particles` action** (`scenes/particles_action.py`; run_time 0.6 = the fade out,
  reversible, `until_next_beat`, `needs_target = False`, `needs_visible = False`, `scene_targets =
  False`): `- particles: snow` or `kind:`; `Options(ParticleSettings, ActionOptions)` + `kind`,
  `keep`. `apply` adds the field and returns no animation (it fades itself in); `revert` fades it
  out. `problems()`: kind given twice, more than one, none, unknown (did-you-mean), `keep` with
  `until`. The runner (`ActionRunner._resolve`) now resolves no targets for actions with
  `scene_targets = False` (until now only the non-animating `sfx` had it). Works on every scene
  type; particles for a whole scene of any type: `keep: true` on the first beat.
- **Stage** (§69.6): `particles: list[StageParticles]` (`ParticleSettings` + `kind`; a string is
  the kind); the fields are made before the entrance step (they fade in on their own) and drawn in
  front of everything, foreground layers included; `Stage.particles` (list of `ParticleField`).
- **Layout dump / lint**: `introspect` reports a field as one object of kind `particles` named
  after its kind; `describe` gives `particles 'snow'`; `off_frame` skips it (particles cross the
  edges on purpose). Other rules see it like any shape group (`covered_text` measures its pixels).
- **Why not an overlay**: overlays are composited per distinct state with two whole-frame Manim
  cameras (§41); particles change on every frame, so that would cost two extra full renders per
  frame, and overlays cannot start at a beat's `at`.
- **Not done here**: a `place: behind` (particles between the backdrop and the characters); wind
  or speed options; particles reacting to the stage (rain stopping at the ground line). Tests:
  `tests/test_particles.py`.

### 69.10 Shared style for generated backgrounds (Step 77)

A cartoon's stages should look like one world. `cartoon_style:` (top level, `VideoConfig`; a
non-empty string, none by default) holds style words added to every `generate:` prompt of
`stage` scenes, e.g. "flat colours, thick outlines, soft shadows".

- **Which scene types**: a scene type opts in with the class attribute
  `NarratedScene.uses_cartoon_style` (`False`; `Stage` sets `True`). `find_images` (so `vidgen
  imagegen`, `validate`, orphans and `used_keys`) reads it from the registry entry's class, and
  the scene's `generated_picture(generate)` (= `generated_image(project, generate, theme,
  cartoon=self.uses_cartoon_style)`) uses it when rendering, so both resolve the same request.
  The `image` scene and extension types keep their prompts unless they opt in. Stage `layers`
  take only files (no `generate:`), so the background's `generate` is the only stage prompt.
- **Prompt** (`image_request(project, generate, *, cartoon=False)`): the style part is
  `"; ".join` of the style words (`generate.style` or `imagegen.style`, §58) and
  `cartoon_style_words` (spaces collapsed, a final full stop dropped), each once. So the text sent
  is `<prompt>. Style: <style words>; <cartoon style>. Avoid: <negative>.`; `style: none` drops
  the style words but not the cartoon style. `ImageRequest.style` and the sidecar's `style` hold
  the joined words.
- **Cache key**: unchanged formula (§58, `KEY_VERSION` 1); the cartoon style is in the text, so
  it changes the key of stage pictures only. Without `cartoon_style`, or for other scene types,
  the request and its key are exactly what they were (the keys pinned in
  `test_imagegen_openrouter.test_openai_keys_are_unchanged` and `tests/test_cartoon_style.py`).
- **Variants**: a top-level key, so a variant may set another style (or `null`) by the usual
  deep merge; its stage pictures get their own keys, and `used_keys` counts them, so neither set
  is reported as unused.
- **Fingerprint**: `cartoon_style` is in the dumped config like `imagegen`, so changing it makes
  every scene's render stale (not only stages); accepted, as for `imagegen.style`.
- **Docs**: CONFIG.md "Generated backgrounds (`cartoon_style`)" under `stage`, with how to write
  a background prompt that leaves room for the characters (an empty middle, the ground visible,
  no people or text, calm detail, wide stages). Tests: `tests/test_cartoon_style.py`.

### 69.11 Acting actions, part 1: speaking and looking (Step 78)

Characters speak and act during beats: who speaks follows the beat's voice; six beat actions
(`scenes/acting.py`, written against `vidgen.api` only) change a character's state with
`PoseChange` (§69.3).

- **Who speaks** (`cartoon/cast.py`, no manim): `beat_voice(scene, beat)` = the beat's `voice`,
  else the scene's, else `default`; `speaking_characters(config, voice, names)` = the characters
  among `names` whose `voice` is it (none without a voice). `Stage.narrate` (a context manager
  around `NarratedScene.narrate`) makes those characters on the stage speak for the beat
  (`self.speak(c)` on entering, `stop_lip_sync()` after the beat's `d + pad`, unless a later lip
  sync took over: `lip_sync_track` is no longer the one it started), except in a beat with a `say`
  action (`beat_action_names(beat)`), where the `say` picks the speakers. `shared_voice_warnings`
  (`vidgen validate`): characters sharing a voice all speak its beats.
- **Timing**: `NarratedScene.beat_clock()` returns a callable giving `renderer.time` minus the
  scene time the current beat started (`narrate` records it); `speak(character)` =
  `character.lip_sync(self.beat_visemes(current_beat), clock=self.beat_clock())`. The mouth is
  thus a function of the scene time from the audio's start, whatever runs meanwhile (§69.4); a
  `say` applied at `at: 0.5` or after the stage's entrance starts mid-track, in step.
  `NarratedScene.current_beat` is the beat being narrated.
- **Actions** (all target characters; `_Acting` base: a target name of the scene that is not a
  declared character is a problem from `scene_problems`, `'tree' is not a character; emote acts on
  characters`; at render time a non-character target is logged and skipped; `_change` records,
  per character, the parts and facing a `PoseChange` changes and `_undo` puts back just those,
  so later changes to other parts stay):
  - `say` (run_time 0.4 = the bubble's fade-in; reversible, `until_next_beat`; needs `say`):
    options `bubble` (`false`; `true`: the beat's text; a string: that text, `TranslatableStr`;
    empty is a problem), `color` (`#FFFFFF`), `size` (`caption`). `apply` calls `scene.speak` on
    each character and draws a bubble; `revert` stops the lip sync it started (not a later one)
    and fades the bubble out. `scene_problems`: `say_problem` (a character without `voice`).
    On the scene's last beat nothing reverts it: the mouth rests after the track and the bubble
    goes with the scene's fade-out.
  - `look_at` (0.5; reversible; needs `look_at`): `to` = a target name (a character or prop), a
    mark or x (through `camera_place`, like `pan`), or `camera`; checked in `scene_problems`. The
    geometry is `cartoon/acting.py` (no manim): `look_pose(dx, dy, facing)` from the looker's head
    centre to the other's head (a prop's centre; a mark at the looker's head height): faces that
    way unless `|dx| < SAME_X` (0.05 units), the head angle `atan2(dy, max(|dx|, SAME_X))` capped at
    `LOOK_MAX_DEGREES` 20 (positive tilts up in both facings: the mirror), the eyes shifted
    `LOOK_EYES_AHEAD` 0.008 forward and up / down with the angle; `camera_look(facing)`: head
    straight, eyes `CAMERA_EYES_BACK` 0.025 back (the middle of a generated face). Applied with
    `looked_state` (head angle and eyes shift set in the pose; missing parts skipped). A later
    `pose` / `emote` sets the head / eyes again.
  - `turn` (0.4; reversible): `to` `left` | `right` (default: the other way); a `PoseChange` with
    the same parts and another facing (the mirror switches halfway).
  - `emote` (0.5; reversible; needs `emote`): `to` an expression; `pose` (0.8; reversible): `to`
    a pose. Both checked with `pose_name_problem` (built-in and the character's own names).
  - `react` (0.6; reversible, `until_next_beat`): `expression` and / or `pose` (neither: a
    problem); needs `emote` when it has an expression.
  Several on one character in a beat play one after another (the runner's batches by target).
- **Speech bubble** (`speech_bubble(text, anchor, *, color, size, bounds, avoid, scale, theme)`):
  reuses the callout helpers: `callout_label` (text wrapped to a third of the frame, readable size,
  ink that reads on `color`) and `label_spot` (`side: top`, `straight`, gaps `BUBBLE_GAPS` 0.25 /
  0.45 / 0.8 × scale) above the speaker's head region, inside `label_bounds` (the safe area, or the
  zoomed / panned view) clear of `label_avoid` (text, callouts, other small targets such as the
  other characters, overlays) and earlier bubbles; these three helpers of `callout_action.py`
  were made public for it (they were `_view`, `_bounds`, `_avoid`). The tail (`bubble_tail`: a
  triangle from the plate's edge facing the head, `TAIL_HALF_WIDTH` 0.14, at most `TAIL_LENGTH`
  0.4 or `TAIL_REACH` 0.6 of the way; counterclockwise like the plate, since Manim's `Union` joins
  only paths turning the same way) and the plate are one `Union` filled with `color` and outlined
  in the text's ink (`BUBBLE_STROKE` 3). It is a `Callout` of kind `label` (so later callouts and
  bubbles avoid it), fading in (`callout_fade`), one z-index level above everything like a callout.
- **Validate**: problems as above, plus the usual unknown target (an unknown character name) and
  option errors. Warnings (`cast.acting_warnings(project)`, run by `cli.validate_warnings` in a
  project session so project actions count): for each action use whose `character_needs()` names
  an `ACTION_NEEDS` entry, each declared character its targets match (`fnmatch`) whose parts
  (`character_part_shapes`) lack it: `scenes[0].beats[0].actions[1]: character 'blob' cannot
  look_at (needs head); the action does nothing for it`.
- **Not done here**: gestures, walking, entering and leaving are §69.12 (which also makes a bubble
  follow its speaker); a long beat text makes a large bubble (use a short `bubble` text); a
  `say` by a character whose voice differs from the beat's is allowed (its mouth follows the
  beat's audio) and not warned about; a shape swap still resets the mouth's style, so a dimmed
  character's speaking mouth shows at full opacity (Step 67 gap). Tests:
  `tests/test_cartoon_acting.py`.

### 69.12 Acting actions, part 2: moving (Step 79)

Five beat actions (`scenes/moving.py`, against `vidgen.api` only, on the `_Acting` base of §69.11:
targets must be declared characters, a prop is a problem from `scene_problems`) move characters:
`walk_to`, `enter`, `exit`, `gesture`, `jump`. As in §69.11 the character is the target and the
new state an option (`- walk_to: pip` + `to: door`; `- gesture: kit` + `to: wave`).

- **Motion without manim** (`cartoon/acting.py`): `walk_seconds(distance, speed=WALK_SPEED 2.5)`
  = |distance| / (speed × (1 − `WALK_EASE` 0.15)): the walk speeds up evenly over the first 15 %
  of its time, goes at `speed` (Manim units per second), slows down evenly over the last 15 %
  (`walk_progress(t)`, the share of the distance at time share `t`; `walk_amplitude(t)`, the speed
  as a share of the full one). `walk_cycle(steps, amplitude)` gives the pose change after
  `steps` steps (one per `STEP_LENGTH` 0.35 character heights walked, so the feet keep pace):
  legs turned ±`WALK_LEG_DEGREES` 10 and arms ±`WALK_ARM_DEGREES` 16 (the far arm the other way)
  furthest at a footfall (`sin(π steps)`), the legs `WALK_LEG_SQUEEZE` 0.3 narrower and the body
  `WALK_BOB` 0.02 higher as the legs pass (`1 − sin²`); scaled by the amplitude, so a walk starts
  and ends in the pose. Entrances and exits: `nearer_side(x, left, right)`, `offstage_x(side,
  left, right, half_width)` (wholly beyond that edge, `OFFSTAGE_GAP` 0.25 away), `enter_path(side,
  to_x, view, half_width)` → (side, start, end), `exit_path(side, from_x, view, half_width)` →
  (side, end). Gestures (`GESTURES`: point, wave, shrug, nod, shake_head; `GESTURE_SECONDS`
  1.2 / 1.6 / 1.0 / 0.9 / 1.1): `gesture_moves(kind, t, arm)` → part → `PartMove(angle, weight,
  turn, shift)` (turn `weight` of the way from the pose's angle to `angle`, plus `turn`, plus
  `shift`), with `gesture_weight(t)` easing in and out over `GESTURE_EASE` 0.25 (smoothstep): point
  the near arm to 88°; wave to 145° ± 20° three times; shrug both arms ±45° and 0.02 up; nod the
  head down 12° twice (`sin²(2πt)`); shake_head the head 0.012 sideways twice and the eyes as far
  again (a flat figure cannot turn its head in depth). The near arm is `arm_left`, else
  `arm_right` with mirrored angles. `jump_lift(t, height)` = 4 h t (1 − t), `JUMP_HEIGHT` 0.4
  character heights, `JUMP_SECONDS` 0.6.
- **Animations** (`cartoon/transition.py`, exported): `Walk(character, x, *, start_x=None,
  park_x=None, speed=WALK_SPEED)` (run time `walk_seconds` unless given; `begin` ends a blink,
  jumps to `start_x`, records the state, the feet and the facing towards `x`; each frame sets
  `walking_state(base, cycle, facing)`, moves the feet's x (y kept) and calls `sync_mouth`;
  `clean_up_from_scene` moves it to `park_x`), `Gesture(character, kind)`, `Jump(character,
  height)`. All redraw from the state they began with and end in it (a walk with the new
  facing). `Character.character_height` (its height in Manim units, from the anchor) scales steps
  and jumps.
- **Actions**: `walk_to` (`to` a mark or x, `speed` (0, 20]; class `run_time` 2.0; faces the way
  it goes and keeps that facing); `enter` (`side`, `to` (default the character's own mark:
  `Stage.homes`, name -> x), `speed`; starts just beyond the camera view's edge); `exit` (`to`
  edge, `speed`; ends just beyond the view's edge, then is parked beyond the stage's edge so a
  later pan never shows it; a `follow` of that character stops: the follow function's
  `followed`); `gesture` (`to` one of `GESTURES`; `character_needs` = `"gesture: <kind>"`, the
  §69.2 entries); `jump` (`height` (0, 2]). None is reversible. Places are checked like `pan`'s
  (`camera_place`).
- **Timing**: the new hook `Action.run_time_for(scene, targets) -> float | None` (default `None`)
  gives a use's natural run time for its targets when it falls due; `ActionRunner._phases` uses
  it (through `_natural`) unless the config gives `run_time` or the phase undoes something. So a
  walk lasts its distance over its speed (the longest of several targets; all walk for that
  time), and is shortened with the other actions when the beat has less time left (as always,
  `rushed_animation` may report it). The estimate is taken when the batch is planned: two walks of
  one character due on the same frame use the first one's start for both.
- **Camera**: `Action.alters_targets` (class attribute, default `True`; `pan` and `follow`
  `False`): such an action's targets do not count when the runner splits due actions into batches
  of distinct targets, so a `follow` due with a `walk_to` of the same character plays with it.
  `_MoveThenFollow` re-aims its end view at `x_of()` on every frame (inside `camera_bounds`), so
  the pan catches up with a walking character and hands over to following without a jump.
- **Stage**: `Stage.homes` (each character's mark x); characters an `enter` names
  (`NarratedScene.action_uses("enter")`, the new method listing a scene's validated uses of an
  action type) start parked beyond the stage's edge on the side of their first `enter` (else the
  edge nearer their mark) and fade in there with the set (unseen); `off_frame` ignores objects
  wholly outside. A walk keeps the character's depth (feet y), so the draw order never changes
  (a walk in depth changes both: Step 111, §69.44).
- **Speech bubble follows its speaker** (fixes §69.11's gap): `follow_speaker(bubble, speaker)`
  (`scenes/acting.py`) adds an updater keeping the bubble at its offset from the speaker's feet,
  so it moves with a walk or jump (it is not clamped to the view).
- **Lint `walk_overlap`** (still rule after `overlay_overlap`, in `lint/cartoon_rules.py` since
  Step 84, default warning, `WalkOverlapRule`
  `min_overlap` 0.25): the walk actions set `Character.walked_in` to the current beat; `introspect`
  writes it as `walked_in` on the character's object; at a beat-end still, a character whose
  `walked_in` is that beat and whose box shares at least `min_overlap` of the narrower width with
  another character's is reported (`character 'pip' ends its walk on character 'kit' (60% ...)`),
  a pair that both walked once.
- **Not done here**: changing depth while walking (`walk_to` keeps the depth; Step 111 adds
  `depth`, §69.44); a path or curve
  is `move_along` (§69.14, not a walk); foley is §69.19 (anticipation, squash and follow-through: §69.13); a single `legs`
  part cannot step leg by leg (the cycle turns and narrows the pair); `enter` teleports a
  character that is on screen to the edge first; an `exit` with a camera that keeps moving can
  end in view (it is parked off stage at its end anyway). Tests: `tests/test_cartoon_moving.py`.

### 69.13 Animation principles built in (Step 80)

Characters move with four principles of cartoon animation: anticipation, squash and stretch,
overshoot and settle, follow-through. They are pure functions of time in `cartoon/motion.py` (no
manim) applied inside the existing animations of `cartoon/transition.py` (`PoseChange`, `Walk`,
`Gesture`, `Jump`; no new animation class), scaled by one setting.

- **Setting**: `cartoon_motion: lively | calm | none` (`config.MotionSetting`, exported) at the
  top level (`VideoConfig.cartoon_motion`), as a `stage` param and on a character
  (`CharacterEntry.cartoon_motion`), all default none. The nearest wins:
  `resolve_motion(character, scene, video)` = the first given, else `DEFAULT_MOTION` `lively`.
  `character(name, motion=<the scene's>)` resolves the scene's against the video's;
  `build_character(entry, motion=)` puts the entry's own first. `MOTION_LEVELS` gives the
  strength: `lively` 1, `calm` 0.4, `none` 0. Every effect is linear in it, and at 0 every
  function returns the plain motion of §69.3 / §69.12 (no offset, no extra time).
- **Character** (`cartoon/character.py`): `Character(..., motion="lively")` (an unknown value is
  a `VidgenError`), the attribute `motion` (read by the animations when they are created; a
  `motion=` keyword on the animation wins), `motion_strength`, and `set_squash(x, y)`: a scale of
  the whole figure about its feet, applied in `_screen` before the mirror, outside the poses
  (`state()` never holds it; the feet stay on the ground; `set_squash()` puts it back; a call
  with the current values does not redraw).
- **Phases** (`Phases(before, after)`, `Phases.of(before_s, main_s, after_s)`, `split(t)` →
  how far into the wind-up, the move and the settle): an animation with the principles has a
  wind-up before the move and a settle after it.
- **Anticipation and overshoot** (`motion_ease(u, strength, base=smoothstep)`, a part's or a
  gesture's progress): the first `ANTICIPATION_SHARE` 0.2 × strength of the time goes back
  `ANTICIPATION` 0.12 × strength of the move (`-A sin²(πx)`, flat at both ends), the middle is
  `base`, the last `SETTLE_SHARE` 0.25 × strength passes the end by up to `OVERSHOOT` 0.1 ×
  strength and comes back a third of that (`settle_wobble(v)`: `sin(πv) sin(2πv) e^(−3v)`
  normalised to peak 1; 0 and flat at both ends). `PoseChange` eases each part's window with
  `motion_ease(local, strength, part_rate_func)`; `gesture_weight(t, strength)` (and
  `gesture_moves(..., strength)`) eases the arms in and out with it (the way out is the way in
  reversed, so it winds up before going back and passes the pose before stopping); `nod` and
  `shake_head` keep their own oscillation.
- **Walk**: `walk_motion_seconds(walk_time, strength)` = the walk's time plus strength ×
  (`WALK_WIND_UP_SECONDS` 0.25 + `WALK_SETTLE_SECONDS` 0.4) (no walk: 0); `walk_phases`. The
  feet stand still in the wind-up and the settle; the walk cycle and `walk_progress` run in the
  move. `walk_accent(t, phases, strength) -> BodyAccent(lean, stretch)`: the wind-up crouches
  (`WALK_CROUCH` 0.05) and leans back (`WALK_LEAN_DEGREES` 6, body angle about its pivot) as
  `sin²`, the settle leans on forward (`STOP_LEAN_DEGREES` 6 × `settle_wobble`). `Walk`'s run
  time default and the actions' `run_time_for` (`walk_to`, `enter`, `exit`) use
  `walk_motion_seconds` with the character's strength.
- **Jump**: `jump_motion_seconds(flight, strength)` = flight (`JUMP_SECONDS` 0.6) + strength ×
  (`JUMP_CROUCH_SECONDS` 0.18 + `JUMP_LAND_SECONDS` 0.3); `jump_phases`. The lift is
  `jump_lift` of the move's share (0 in the crouch and the landing). `jump_stretch(t, phases,
  strength)`: the crouch squashes to `−JUMP_SQUASH` 0.22 (`sin²(πx/2)`), the flight stretches by
  `JUMP_STRETCH` 0.15 × `(1 − 2m)²` (most at take-off and landing, round at the top), the landing
  squashes fully at touch-down and bounces back (`landing_bounce(v) = (1 − v)² cos(2.5πv)`).
  `squash_scale(stretch)` = (1 / (1 + stretch), 1 + stretch): the area stays. `JumpAction` gains
  `run_time_for`.
- **Follow-through** (arms, head, accessory; a generated character's hair and ears are drawn in
  its head, §69.1, so they move with it): `follow_through(position, seconds)` = the lagged body
  speed minus the body speed (character heights per second, the speed by central difference of
  `position`, the body's distance walked or height jumped as a function of seconds): negative
  while the body speeds up, positive while it slows down and just after it stops, 0 at a steady
  speed. The lag is `follow_lag(signal, seconds, spring=FOLLOW_SPRING)`, the signal as a part on
  a damped spring sees it (§69.15; Step 80 had a first-order lag here): `FOLLOW_SPRING` =
  `Spring.tuned(FOLLOW_SPRING_HZ 2.0, FOLLOW_DAMPING_RATIO 0.5)`, so a part trails a steady
  speed-up by 2ζ/ω ≈ 0.08 s, passes a sudden change by about 16 % and swings back once (settled
  to 2 % in 0.64 s). It is a pure function of time, whatever
the frame rate. `follow_angles(forward, up, strength)` turns the parts: both arms
  `FOLLOW_ARM_DEGREES` 30 per height/s (trailing back, at most `FOLLOW_ARM_LIMIT` 25°), head
  `−FOLLOW_HEAD_DEGREES` 10 (tips back, at most 8°), accessory `−FOLLOW_ACCESSORY_DEGREES` 18 (at
  most 12°); `up` raises the arms outwards (as a shrug: `arm_left` +, `arm_right` −; inwards at
  most `FOLLOW_INWARD_LIMIT` 8°). `end_fade(t)` takes it to 0 over the last `FOLLOW_FADE_SHARE`
  0.12, so the animation ends exactly in its state. `accented_state(base, lean, turns)` adds the
  lean and the turns to a state (`transition.py`).
- **Spring** (Step 82, §69.15): `follow_lag` is the only place the lag is computed, so walks and
  jumps got the spring without other changes.
- **Not done here**: no principle on a `PoseChange`'s facing switch (it still flips at half);
  follow-through only on walks and jumps (not on pose changes or gestures); no squash on
  walking footfalls; anticipation of an `enter` happens off stage (unseen, its time is spent).
  Tests: `tests/test_cartoon_motion.py`.

### 69.14 Keyframes and motion paths (Step 81)

Two beat actions (`scenes/keyframes_action.py`, against `vidgen.api` only) move what the other
actions cannot: `keyframes` (through keys) and `move_along` (along a path). They act on a
`stage`'s characters, props and **character parts**.

- **Part targets**: the `stage` registers each part of each character as a target
  `<character>.<part>` (`kit.arm_left`; `target_patterns` gains `"<character>.<part>"`), the
  dotted form of other scenes' sub-targets (`col2.item3`, `cell2.4`). The target's mobject is the
  part's live `VGroup` (`Character.parts`); its entrance is its character's. `target_names`
  lists them after the characters and props, from `cast.part_target_names(names)` (the parts
  each declared character has: `character_part_shapes`, an svg read from the file), only while a
  project is active (validate, render); without one only characters and props are named. A
  wildcard such as `*` or `k*` selects parts too: the acting and moving actions skip them
  (`scenes/acting.py`: `is_part_target`, a name with a dot; at render silently), a part named on
  its own is a problem for them (`'kit.mouth' is a character's part; emote acts on whole
  characters`); `dim` and `highlight` act on parts like any target.
- **Channels** (`cartoon/keyframes.py`, no manim): `CHANNELS = x, y, rotate, scale`. Author units:
  a character or prop's `x` is a mark or an x 0..1 of the stage (`camera_place`, as `walk_to`),
  `y` the height of its feet above its ground line at its depth in frame heights (`Stage.grounds`,
  name -> the ground line's y at the item's depth, a prop's `lift` not included), `rotate`
  degrees counterclockwise on screen about the feet, `scale` a factor of its built size; a part's
  `x` / `y` are its pose shift in character heights, `rotate` its pose angle (as drawn facing
  right, so mirrored with the character), `scale` its size (`KeyedMotion` keeps the signs of the
  pose's scale, so a flipped mouth stays flipped). `rotate` and `scale` are absolute: a whole
  target keeps its turn and size as `keyed_rotate` / `keyed_scale` on the mobject.
- **Keys** (`KeyFrame`, pydantic, `extra=forbid`): `t` (seconds 0..600, strict, or a share of the
  beat's narration `"40%"`, `SHARE_PATTERN`), `x` (mark or number), `y` (±2), `rotate` (±1080),
  `scale` (0, 10], `ease`; at least one channel. `key_seconds(t, beat_seconds)`;
  `key_time_problems(times)`: all seconds or all shares (so the order is known without the
  audio), strictly increasing, a share ≤ 100 %. Times count from the action's start (its `at`).
- **Interpolation** (`keyed_values(start, keys, seconds)` with `Key(seconds, values, ease)`):
  per channel, the value before the first key that sets it is `start` (the target now); between
  two keys that set it, the later key's ease of the elapsed share; held after the last; a key at
  0 s sets its values at once. Only channels some key sets are animated.
- **Eases** (`EASES`, `EASE_NAMES`, `EaseName`, `DEFAULT_EASE` `smooth`): the names of Manim's rate
  functions, so authors who know Manim know them (`linear`, `smooth`, `rush_into`, `rush_from`,
  `ease_in|out|in_out_sine|quad|cubic|back`, `ease_out_bounce`, `ease_out_elastic`), written out
  without importing manim (validate stays light) and checked against `manim.utils.rate_functions`
  by a test; plus `lively` / `calm` = `motion_ease(u, MOTION_LEVELS[...], smoothstep)` (§69.13).
  No author-facing ease names existed before (the project's scenes use Manim's functions in
  code), and `there_and_back`-style eases are left out (they end where they start).
- **Paths** (`path_curve(points, smooth)`: the points, or a uniform Catmull-Rom curve through them
  (tangent half the chord from the point before to the point after; the ends' tangent the chord
  to their neighbour) sampled `PATH_SAMPLES` 32 per segment; `path_length`; `MotionPath(points,
  smooth).at(share)`: the point that share of the length along, so the speed is even). Lengths
  are in the points' units.
- **Animation** (`KeyedMotion(mobject, values_at, *, part=None)`, `cartoon/transition.py`,
  exported): `values_at(share)` gives the channels at each share of the run time (rate_func
  linear). A whole target: each frame undoes the last frame's turn and size about the old feet,
  moves the feet, applies the new turn and size about them (a `Character`'s anchor moves along,
  so its poses, idle and later walks work from there; another mobject's feet are kept as
  `keyed_feet`, read by `feet_of`). A part (`mobject` the `Character`): `set_part` with the
  channels. A character ends a running blink and keeps lip sync in step, as `PoseChange`.
- **Actions**: `keyframes` (`keys`, `ease`; class `run_time` 1.0; `run_time_for` = the last key's
  seconds, so a configured `run_time` or a short beat stretches or squeezes the keys);
  `move_along` (`path` `[[x, y], ...]`, `curve` `smooth | straight`, `ease`, `speed` (0, 20]
  units per second on screen; class `run_time` 2.0; with `speed`, `run_time_for` = the longest
  path's screen length (a part's × `character_height`) / speed). The path starts where the
  target is (that point first, repeated points dropped); an ease past 0..1 holds at the ends
  (`MotionPath.at` clamps). Both reversible: `until` moves each target back to the values saved
  at `apply`, straight with `smooth`, in the use's run time. `scene_problems`: the scene type's
  `target_patterns` must include `<character>` (else `keyframes moves the characters, props and
  character parts of a stage`); per matched target name and per key / point, a whole target's
  `x` through `camera_place` and |y| ≤ `WHOLE_Y_LIMIT` 1, a part's `x` a number and |x|, |y| ≤
  `PART_SHIFT_LIMIT` 1. `problems()`: `key_time_problems` (`keys[1].t: t 0.5 is not after the key
  before (1.0); keys go in time order`). Unknown parts are the usual unknown-target problem.
- **Not done here**: no `cartoon_motion` on keyed moves (use `ease: lively`); a moved character
  does not face its way (add `turn`) and walks / jumps from where it is (a lifted character walks
  in the air); a whole-target `scale` is a Manim scale (strokes keep their width); no rotation
  along a path's direction; keys for `depth` or opacity. Tests: `tests/test_cartoon_keyframes.py`.

### 69.15 Spring physics for secondary motion (Step 82)

Parts that hang on something moving (antennae, ears, tails, hair, hanging signs) lag behind it,
pass it and wobble back. `cartoon/spring.py` (no manim, exported by `vidgen.api`) gives that as a
pure function of time, so custom scenes and the built-in follow-through (§69.13) share one helper.

- **`Spring(stiffness, damping)`** (frozen dataclass): a spring of unit mass, `x'' = stiffness·(s −
  x) − damping·x'` (stiffness 1/s² = ω², damping 1/s = 2ζω; both > 0, else `ValueError`).
  `Spring.tuned(frequency_hz, damping_ratio)` builds one from the undamped wobbles per second and
  ζ. Properties: `angular_frequency` ω, `damping_ratio` ζ, `is_critical` (|ζ − 1| < 1e-9, so
  `tuned(f, 1.0)` counts despite rounding), `decay_rate` (ζω, or ω(ζ − √(ζ² − 1)) over-damped: how
  fast the slowest motion dies).
- **Closed form**: `step_response(seconds)`, the spring's position after its target jumps 0 → 1
  from rest (under-damped `1 − e^(−ζωt)(cos ω_d t + ζ/√(1−ζ²) sin ω_d t)`, critical `1 −
  e^(−ωt)(1 + ωt)`, over-damped the two-exponential form). `overshoot()` = e^(−πζ/√(1−ζ²)) (0 when
  ζ ≥ 1). `settle_seconds(tolerance=0.02)`: when it enters the band ±tolerance for good,
  bisected between the last turning point outside the band and the first inside (turning points
  at kπ/ω_d, e^(−ζω kπ/ω_d) from 1), or from 0 when ζ ≥ 1 (the response only rises).
- **`follow(target, seconds)`**: where a part on the spring is while it follows `target(seconds)`,
  at rest at `target(0)` before 0. It weighs the target's past by the spring's impulse response
  (the slice weights are differences of `step_response`, exact, so they sum to 1 and a constant
  target gives itself back), over the last 6 decay times (older weighs < e^−6, taken at the
  oldest value) in 32..512 slices (8 per radian of ω). No state between calls: the same value at
  any frame rate and after any seek, unlike stepping the equation frame by frame. Checked
  against the equation stepped at 20 µs (within 0.005).
- **Use**: follow-through (`motion.follow_lag`, §69.13). A custom scene drives a part from it, e.g.
  an antenna's angle `k·(spring.follow(head_x, t) − head_x(t))` in an updater, `t` the seconds
  since the motion started.
- **`cartoon_motion: none`** still gives no offset: `follow_angles` scales by the strength (0) and
  `Walk` / `Jump` skip follow-through at 0 (tested on a walk's head angle).
- **Not done here**: no author-facing YAML for springs (a character has no tail or antenna part;
  generated hair and ears are drawn in the head); follow-through stays on walks and jumps (not
  pose changes, gestures or keyed moves). Tests: `tests/test_cartoon_spring.py`,
  `tests/test_cartoon_motion.py`.

### 69.16 Character sheets and mid-action storyboard stills (Step 83)

Two ways for an author (or an agent, which cannot watch a video) to look at cartoon work without
rendering it whole.

- **Character sheet** (`cartoon/still.py`, next to `write_character_png`):
  `character_sheet_sections(entry, root) -> [SheetSection]` (no manim): `pose` (`merged_table`
  names: built-in, then the character's own), `expression` (same) and `mouth` (the mouth's shape
  names from `cast.character_part_shapes`; no section without a mouth); `own` marks the
  character's own entries. `sheet_layout(sections, columns=SHEET_COLUMNS 8) -> SheetLayout(width,
  height, columns, section_tops, cells)` (no drawing): a title and a note line, then per section a
  heading line and its cells in rows of at most `columns` (fewer when no section has that many),
  each cell `SHEET_CELL_WIDTH` 128 px wide, `SHEET_POSE_CELL_HEIGHT` 160 (whole figure) or
  `SHEET_HEAD_CELL_HEIGHT` 128 (close-up) high, a label line under it. `write_character_sheet(project,
  entry, theme, path=None) -> CharacterSheet(character, path, width, height, bytes, sections)`:
  each section's cells are drawn by Manim's `Camera` at the cell's pixel size (`tempconfig`, so
  strokes keep their one-pixel floor), facing right, on the theme background, then pasted onto a
  white Pillow page with the storyboard's fonts and colours (`sheets.load_font`, `TEXT`, `MUTED`,
  `BORDER`). Poses: one figure, its height chosen from a probe at height 1 so the tallest and the
  widest pose fit (0.84 of the cell's height, 0.9 of its width), centred on its drawn parts, feet
  near the bottom; expressions and mouth shapes (`swap("mouth", shape)`, the rest face): a figure
  built `HEAD_FILL` 0.6 times the cell's size over its head box (`HEAD_PARTS` head, eyes, brows,
  mouth, accessory; the whole figure if it has none) and shifted so the rest head box is centred,
  so every close-up has the same scale. Built at the right height (not scaled afterwards), so
  outlines stay proportional. The page is saved as a `SHEET_COLORS` 64-colour PNG without
  dithering: a generated character is 1148 x 858 px, about 33 KB (sprout, `examples/svg_character`,
  1148 x 696, 26 KB), drawn in about 0.5 s.
- **`vidgen character-sheet [NAME] [PROJECT] [--all] [--variant NAME] [--output FILE] [--json]`**
  (`cli.cmd_character_sheet`): NAME, else every character (`--all PROJECT` makes the one
  positional the project, since NAME comes first, as in `vidgen character NAME [PROJECT]`);
  default file `exports/character_sheet_<name>.png` (`default_sheet_path`); `--output` only with a
  NAME; no characters is a `VidgenError`. Human output: one line per sheet (path, size, counts,
  KB). JSON (`jsonout.character_sheet_document`, in `cli.JSON_COMMANDS`): `project, variant,
  elapsed, sheets: [{character, path, width, height, bytes, sections: [{kind, names, own}]}]`.
- **MCP** (`mcp_server`): tool `character_sheet(project, name=None, variant=None, images,
  image_offset)` runs `character-sheet [NAME] PROJECT` (no name: `--all`) and returns the document
  and the sheets as pictures (paged like `storyboard`); not serialised with the rendering tools
  (a few seconds).
- **Mid-action stills** (`capture.py`): `NarratedScene.mid_still_actions` (class attribute, empty
  by default; `Stage`: `walk_to, enter, exit, gesture, jump, keyframes, move_along`) names the
  action types whose uses also get a still half-way through them. `ActionRunner._phases` labels
  each batch with those of its (not undoing) actions (`ActionConfig.describe()`: `walk_to pip`,
  joined by `, `); `ActionRunner._run`, right before it plays the batch for `frames` frames from
  frame `now`, calls `FrameCapture.add_mid_still(beat, now, frames, label)` when stills are
  captured. Which frame is the pure function `mid_action_frame(start, frames, taken, min_gap)`:
  `start + frames // 2`, `None` for an action under two frames or within `min_gap` frames
  (`MID_STILL_GAP_SECONDS` 0.4 s) of another still of the beat (`taken`: its planned stills and
  planned end, and its mid stills so far); at most `MAX_MID_STILLS` 3 per beat.
  `mid_action_frames(spans, taken, min_gap, limit)` folds it over a beat's actions in play order
  (what the capture does one call at a time; tested without rendering). Times come from the run
  as played (after `run_time_for` and any shortening to fit the beat), so a pure function of
  the played spans; computing them before the render would need every walk's distance there.
- **Records**: a mid still is a `CapturedFrame` with `k` 0 and `mid` the label; file
  `<beat>-m<frame>.png` (`still_name`); its `index.json` entry and its layout dump frame carry
  `mid` (absent on other stills, so their shape is unchanged). `FrameCapture.finish` drops mid
  stills never reached. Readers: `lint` checks only `k == n` (unchanged: mid stills are skipped),
  `deck` (slides) leaves entries with `mid` out, `gallery` takes the last still (an end still).
  `storyboard` passes `mid` to `SheetStill.mid`; `sheets._label` writes `½ walk_to pip @ time`;
  the subtitle adds `½ = half-way through an action` when a page shows one; the JSON frames gain
  `mid` (null on others). Existing renders are stale anyway (capture, actions and scene code are
  in the render fingerprint).
- **Not done here**: no mid stills for `PoseChange`-based acting actions (`pose`, `emote`,
  `turn`) or camera moves; the sheet shows no facing left, no blink (`eyes` `closed`) and no
  gestures in motion (the storyboard does). Tests: `tests/test_cartoon_sheet.py`,
  `tests/test_frames.py` (mid-action frames, the capture), `tests/test_mcp.py`.

### 69.17 Cartoon lint rules (Step 84)

Six still rules in `lint/cartoon_rules.py` (with §69.12's `walk_overlap`, moved there; imported
right after `layout_rules`, so `RULES` keeps `LINT_RULES`' order), default `warning`, one settings
model each in `config.LintRules`. Like every still rule they read beat-end stills only (`k == n`;
§69.16's mid-action stills stay skipped by the runner). Step 115 adds a scene rule there,
`look_alike` (after `mouth_without_voice`; it reads the config, not a still: §69.49).

- **Layout dump** (`introspect._character_keys`, read by these rules only): a `character` object
  always has `facing` (`left` / `right`) and `speaking` (a lip sync runs:
  `Character.lip_sync_track` is set; at a beat-end still that is the beat's speakers, `Stage.narrate`
  stops them after it); when they apply, `face` (the box of the `head` part's drawn shapes, px),
  `viseme` (new property `Character.spoken_viseme`: the viseme the running lip sync shows, `rest`
  between words), `looked_at` (new attribute `Character.looked_at`: the `to` of its last
  `look_at` when that is a name, a mark or `camera`; `LookAt.revert` puts the one before back),
  `passage` (new attribute `Character.passage`: `enter` / `exit` while a `Walk` with `start_x` /
  `park_x` plays; `begin` sets it, `clean_up_from_scene` clears it) and `walked_in`. The objects
  of a speech bubble (its plate-and-tail `Union` and its text) carry `bubble`: the speaker's name
  (`Say._bubble` sets `speech_bubble_of` on the bubble group; `LayoutRecorder._walk` copies it onto
  the objects walked under it). A frame of a beat-end still has `narrating`: whether its time lies
  in its beat's narration (`scene.beat_log`: `start <= time < end`, so false in the pad); other
  stills have no such key (the beat is not logged yet).
- **Rules**:
  - `off_stage` (`min_hidden` 0.05): a character with at least that share of its box outside the
    view and some of it inside; skipped with `passage` set and while the camera is zoomed in (a
    pan still counts: the viewer sees the cut). `off_frame` now skips characters (one finding).
    In a shot (Step 95, §69.29) only the characters the shot frames are checked.
  - `character_overlap` (`min_overlap` 0.25 of the narrower width, as `walk_overlap`): two
    characters at rest whose boxes share that much; a character that walked in the still's beat
    (`walk_overlap`'s) or has `passage` set is left out.
  - `bubble_overlap` (`min_overlap` 0.1): a bubble (union of its objects' boxes) covering that
    share of a character's `face` box (its own speaker's too), or of the smaller of two bubbles.
  - `facing_away`: a speaking character in view whose listener's face x lies on the side it does
    not face (more than 0.02 of the shorter side away). The listener is the character it last
    looked at (`looked_at`) when in view, else the nearest one by face x; `looked_at: camera`
    means it talks to the viewer: not checked.
  - `hidden_speaker` (`min_hidden` 0.5): the characters are flat and face left or right, so a
    back turned to the camera does not exist; what does is a speaker the viewer cannot see:
    the share of its `face` box covered by the boxes of objects drawn after it (`order`: a
    character or prop nearer the camera, a foreground layer, an overlay; not text, particles or
    bubbles), sampled on a 12 x 12 grid.
  - `mouth_without_voice`: a frame with `narrating: false` where a character's `viseme` is not
    `rest`: its mouth shows speech while nothing is heard (a viseme track longer than the beat's
    audio, a custom scene's lip sync without the beat clock).
- **Fix hints**: each message ends with the usual fix; the same in docs/CONFIG.md's rule table
  and the guide's troubleshooting table. `lint_ignore`'s `object` also matches a bubble's
  `bubble` (the speaker), so `{rule: all, object: pip}` covers pip's bubble too.
- **Not done here**: depth is not in the dump, so two characters at different depths that
  overlap are reported like two at the same depth; boxes (not drawn pixels) decide what covers a
  face; keyed moves (§69.14) and jumps are not told apart from standing. Tests:
  `tests/test_cartoon_lint.py`.

### 69.18 Cartoon storytelling in the guide, and `examples/cartoon` (Step 85)

- **Guide topic `cartoons`** (aliases `cartoon`, `characters`, `character`, `stage`, `dialogue`,
  `acting`), between `actions` and `overlays`: when to make a cartoon, original characters only
  (generator or own SVG; never a known character, mascot, brand figure or logo, nor a "style of"
  prompt), staging (marks and `facing`, depth, the set, room to move), shot variety (wide; `zoom`
  for medium and close-up; `pan` / `follow`), reaction shots (`react`, `look_at`, `zoom` on the
  listener, `at` near the line's end), comic timing (one short line per beat, `narration.pad` as
  the pause, setup / pause / punchline), and the loop character sheet → validate → storyboard
  (mid-action stills) → lint → `vidgen tts` (Kokoro) → again. One validated YAML block.
- **Consolidated, not repeated**: the `actions` topic keeps one row per action (the test needs
  every action there) and points to `cartoons` instead of its former dialogue bullet; the
  `outputs` topic's cartoon-background bullet moved into "The set"; the `scenes` chooser keeps
  the `stage` row and its snippet (the gallery sample) with a pointer; the cartoon lint rules stay
  in `troubleshooting`, named once in the loop.
- **`examples/cartoon`** ("The Box Kite", `output: box_kite`): two `stage` scenes, 12 beats
  (115 words: ~44 s of narration at the word-count rate, ~54 s with pads and fades), two generated
  characters (`dot` round with bun and scarf, `moss` tall with hat and glasses), Kokoro voices
  (`bf_emma` narrator, `af_bella`, `am_michael`), `narration.pad: 0.7`, props, a `hills` layer,
  a `width: 2` stage with `follow` on a flying prop (`move_along`), one close-up `zoom` per scene,
  `react` / `emote` / `look_at` / `jump` / `gesture` / `say` with a bubble, dust and confetti
  particles; since Step 88 also a `walk_to` and an `enter` (so footsteps and a whoosh), a bare
  prop name (`- cloud`) and slower voices (`speed: 0.8` narrator, `0.85` characters; §69.21). No
  audio committed: `vidgen validate` (one warning: the Kokoro extra is not
  installed) and `vidgen lint --fail-on warning` on the preview (timed from word counts) pass with
  no findings. The test `test_examples_validate_against_their_schema` (`tests/test_schema.py`)
  picks it up like every example folder.

### 69.19 Foley and music stings (Step 86)

Sounds tied to what the characters do (foley), and short music stings on beats. Both are ordinary
sound effects (§47): `SfxEvent`s in the scene's `sfx_log`, stored in its timings and placed on the
video's one SFX track when the scenes are joined. No audio files were added and nothing is
downloaded: the five new sounds are built-in generators like the other eleven.

- **New built-in sounds** (`sfx.BUILTIN_SOUNDS`, now 16; same finishing and level as §47, so
  `test_sfx` checks them like the others): `footstep` (0.14 s: a heel knock, band noise at 260 Hz
  plus a 95 Hz thump, then a faint scuff at 1.8 kHz), `boing` (0.5 s: a three-partial tone gliding
  140 → 260 Hz with a 12 Hz wobble dying away), and three music stings, `sting_reveal` (1.4 s: a
  brassy G4 pickup, then a C major chord C5 E5 G5 C6 of eight-partial brass tones with a soft C7
  bell), `sting_comic` (1.1 s: two tom hits 200 → 130 and 150 → 100 Hz 150 ms apart, a cymbal of
  noise around 7.5 kHz at 0.33 s) and `sting_sad` (2.2 s: four muted-horn notes B♭3 A3 A♭3 G3, ten
  partials whose brightness opens and closes per note like a wah mute, the last long, sagging 3 %
  with a 5.5 Hz vibrato). Searched first: whoosh, swoosh and pop were reused for enter, exit and
  surprise; nothing could stand in for a step, a spring or a musical phrase.
- **The schedule, without manim** (`cartoon/foley.py`, exported): `foley_cues(PlayedAction) ->
  [FoleyCue]`. `PlayedAction(action, start, seconds, expression, heights, phases)` is one
  character's action *as it played*: its scene start time and the seconds it took (after
  `run_time_for` and any shortening to fit the beat), the expression an `emote` / `react` put on,
  the walk's length in character heights and the wind-up / settle shares (`Phases`,
  `cartoon_motion`). `FoleyCue(time, sound, gain, params, align)`.
  - `walk_to`, `enter`, `exit`: a `footstep` on each footfall (`footfall_shares(heights, phases)`):
    the walk cycle of §69.12 has the legs furthest apart at `k + 0.5` steps (`STEP_LENGTH` 0.35
    heights), so a foot lands there; the share of the walk's time comes from inverting
    `walk_progress` (its ease-in / ease-out is quadratic, so the inverse is closed-form), mapped
    into the move between the wind-up and the settle; plus one softer step (`intensity` 0.3) when
    the walk stops at least `LAST_STEP_MIN` 0.25 steps after the last footfall (the feet come
    together). Feet alternate `pitch` 0 / −1.5 semitones, `intensity` 0.5 / 0.4; −5 dB.
    `enter` adds a `whoosh` (−6 dB) at its start, `exit` a `swoosh` (−6 dB) ending (`align: end`)
    when the walk ends, just beyond the view.
  - `jump`: a `boing` (−3 dB) at take-off, after the crouch (`phases.before`).
  - `emote` / `react` putting on `surprised`: a `pop` (−3 dB) at its start.
  - Other actions: nothing. Gestures were left silent (not asked for; a wave has no natural sound).
- **Timing from the real run**: as Step 83 found, the times an action plays are only known in
  `ActionRunner._run` (after `run_time_for`, the batch split and the beat's shortening).
  `_build` records each built-in action it applied with the animations it made (`_built`);
  `_run`, right before `scene.play`, calls `scene.action_foley(name, options, animations,
  start=now, seconds=frames / fps)` for each. Not for actions applied without animation at a
  beat's end (they make no sound) nor for undoing. `NarratedScene.action_foley` does nothing;
  `Stage.action_foley` builds one `PlayedAction` per animation (`Walk.heights` / `Walk.phases`,
  `Jump.phases`, the new public read-outs of what the animations computed) and records each cue
  with `self.sfx`, without `params` when the project's `assets/sfx` replaces that sound.
- **Switch**: top-level `foley: true` (`VideoConfig.foley`) and a `stage` param `foley: bool |
  None` (none: the video's). Part of the config, so of the render fingerprint (the events are
  recorded by the render, like the `sfx` action's).
- **Music stings**: a beat's `sting:` (`BeatConfig.sting`, `StingSetting`: a kind `reveal |
  comic | sad` or `StingCue(kind, at, gain)`; `StingCue.placed_at`: `at`, else `start` for reveal
  and `end` for comic / sad). `NarratedScene.narrate` records it when the beat starts:
  `STING_SOUNDS[kind]` at the beat's start, or at start + `d` (the end of its narration, before
  `narration.pad`), with `duck` set. Any scene type, since every beat is narrated by `narrate`.
- **Ducking, the existing path**: `SfxEvent.duck` (JSON `duck: true` only when set, so other
  events keep their shape). `join_scenes`, when any event ducks, computes
  `mix.sting_ducking(project, {"scenes": ...}, samples)` = `duck_curve(speech_spans(...),
  frames, STING_DUCK)`: the music's own curve and narration spans (§48) with
  `STING_DUCK = {depth 6, attack 0.15, release 0.3, hold 0}`, and passes it to
  `sfx.write_track(..., ducking_db=)`, which scales the ducked events by it (`ducked`, per sample).
  **Decision**: lighter and quicker than the music's 12 dB / 1.5 s hold, since a sting lasts
  1–2.5 s and with that hold it would stay down through every pause between lines. The stings stay
  on the SFX track (not the music track): they are events at beat times, they must sound with or
  without `music:`, and the SFX track already carries per-event gains.
- **Docs**: CONFIG.md "Foley and music stings" (under Sound effects), the sounds table, the `foley`
  top-level and stage rows, the beat `sting` key; guide topic `cartoons` ("Sound" bullet, a
  `sting` in its example); EXTENDING.md (`action_foley`).
- **Not done here**: no panning by where the character stands; footsteps do not change with
  depth, speed or the ground; no landing sound for a jump; gestures, `pose`, `look_at`, keyed moves
  and particles make no sound; in a preview timed from word counts every beat is "speech", so a
  `reveal` sting at a beat's start is ducked from its first sample and an `end` sting starts ducked
  and comes up over the 0.3 s release (checked by hand on a preview: −6.0 and −2.4 dB at the peaks). `examples/cartoon` has no
  sting yet (its guide excerpt does). Tests: `tests/test_cartoon_foley.py`.

### 69.20 Render speed for cartoons (Step 87)

Measured first (`examples/cartoon`, preview 854x480 at 15 fps, no audio, one scene per process,
cProfile and a per-object timer around Manim's `Camera.display_vectorized`): a scene takes 9–11 s
for 25–29 s of video. The time goes to Manim's Cairo drawing of the characters (about 45 shapes a
frame for two characters, 2–3 s), H.264 encoding in Manim's writer thread (2.6–3 s, overlapping
on the second core), Manim's per-frame family walks (1.5 s), `Character.refresh` (1.25 s) and
imports (2.7 s). Manim already draws everything before the first moving mobject (with an updater,
in an animation) once per `play` / `wait` into a static image: on a plain stage that is the sky,
ground band and the props behind the characters. Two caches were added where the profile showed
time to save:

- **Static stage image with parallax layers** (`NarratedScene.get_moving_mobjects`): Step 74
  returned every mobject while `_camera_step` was installed, so a stage with layers redrew its sky,
  layers, ground band and props on every frame (1.24 s of the `hill` scene). Now every mobject is
  moving only while the camera follows something (`follow_with_camera` may move it on any frame);
  a camera animation (`zoom`, `pan`) still makes Manim's `MovingCameraScene` treat every mobject
  as moving. With listeners only, the camera stays still for the whole animation: the listeners
  run first (so the layers stand where the camera is now) and Manim keeps the static image
  (`hill`: those draws 1.24 → 0.39 s).
- **Part drawings, transformed only** (`cartoon/character.py`): each part shape's points are
  kept once per character (`shape_drawing`: the point arrays of its family members with points),
  and the live members of each part's shown shape are found again only when the shape shown
  changes (`_live_members`, keyed by the shown child; since §69.22 each shape keeps one live
  copy and its members are listed once). `refresh` then only applies the matrices:
  1.25 → 0.58 s in `yard`.
- **Part drawings by look** (`look_parts(look, colors)`, `look_key`): the generator's parts for
  a look in resolved colours are drawn once per process and shared (a `Character` copies the
  shapes it is given); the key is the `look` and the colours, never the poses, expressions,
  name, voice, height or state. At most `LOOK_CACHE_SIZE` 16 looks (the oldest dropped). A
  render builds each character once per scene process, so this saves nothing there; `vidgen
  character-sheet` builds each character six times (2.07 → 1.60 s for both sheets of the
  example). SVG looks are not cached (their warnings are logged per build).
- **Not done**: a raster cache of parts (rotating and scaling a bitmap per frame changes the
  drawing beyond anti-aliasing; not measured); caching the subpath
  split of each part (Manim 0.21's `get_subpath_split_indices_from_points`, 1.1 s of `yard`), which
  needs a per-instance override of a Manim internal that Manim 0.19 does not have.
- **Result**: the same frames (the `hill` preview decodes bit for bit as before; `yard` differs
  only in its last 60 frames, which also differ between two runs of the unchanged code: Step 88
  found that Manim's H.264 encoding, not the drawing, varies there, §69.21). Before /
  after in HANDOFF.md (Step 87): `hill` −8 %, `yard` −3 % at preview, within noise end to end and
  at the final format (encoding bound). Tests: `tests/test_cartoon_speed.py`,
  `tests/test_cartoon_parallax.py`.

### 69.21 Review of Phase H (Step 88)

- **End to end**: `examples/cartoon` through `vidgen validate`, `lint --fail-on warning`,
  `storyboard` (4 mid-action stills before Step 88's walk and enter, 6 after), `character-sheet
  --all` and a preview render, by the CLI and by the MCP tools `validate`, `schema`, `lint`,
  `storyboard`, `character_sheet`, `render`: no failures. `tests/test_phase_h_review.py` repeats
  this cheaply (a 160x90, 5 fps copy of the example, word-count timing; mocked Kokoro audio).
- **JSON Schema of `stage`**: `StageCharacter`, `StageProp` and `StageParticles` accept a plain
  string (a character name, a built-in prop, a particle kind) through `before` validators, which
  `vidgen schema` did not show; each now has `__get_pydantic_json_schema__` returning `anyOf`
  (the string form, then the object), like `bullets`' items. The example uses `- cloud` again.
- **Real narration** (Kokoro 0.9.4, Python 3.12, Manim 0.22, not committed): `vidgen tts` wrote
  the 12 MP3s, `.align.json` and `.visemes.json` (source and timing `kokoro`, 13–22 cues a beat
  after merging). It was killed twice by the 1500 MB cap after three beats each (peak about 2.2
  GB counting the page cache) and finished under 2500 MB. At `speed: 1` Kokoro reads 3.5–4.6
  words a second, so `narration_speed` warned on 9 of 12 beats; at `speed: 0.8` / `0.85` 3 beats
  remain just above 3.5 (3.54–3.68). The guide says so in its cartoon timing advice.
- **The `yard` render that differed between runs** (Step 87): the raw frames Manim hands its
  writer are bit-identical across runs (md5 of every frame), and a render whose partial movie
  files are encoded after the scene (no thread overlap) still differs, but only in the two zoom
  animations and only at the 854-pixel preview width: at 848x480 (a multiple of 16) three runs
  give identical files. So libx264, as Manim calls it through PyAV, encodes a frame whose width is
  not a multiple of 16 differently from run to run (most likely reading uninitialised padding
  next to the frame in a long-running process; a fresh process encoding the same frames gives
  the same bytes every time). Decoded frames of the variants are equally close to the raw frames.
  Not fixed (Manim's encoder options are not reachable from vidgen; changing the preview size
  would change every preview): compare renders by their frames before encoding, or at sizes that
  are multiples of 16. Backlog.

### 69.22 Fixes after the Phase H review: the ground under the set, the mouth while moving

Two faults the owner saw in the Step 88 review video (`examples/cartoon` at 1280x720):

- **Props standing above the ground**: a thing at `depth` d stands `FAR_RISE` × d of the frame
  height above the ground line (`feet_point`), but the `ground_color` band ended at the ground
  line, so the house (depth 0.7) and the tree (0.5) in `yard` stood on the sky. The band now
  reaches up to `ground_top(ground, items)` (`cartoon/stage.py`, exported): `ground + FAR_RISE ×`
  the largest depth of the items on the ground (`lift` 0; a lifted sun or cloud hangs in the air
  and does not count), so everything at a depth stands inside the drawn ground and the deepest
  thing on its top edge, as a thing at depth 0 stood on the band's edge before. The depth
  geometry itself is unchanged (feet, sizes, `grounds` for `keyframes` y 0), so characters,
  props, walks and lint keep their places; only the band grows, and only on stages with
  something at a depth (the gallery's `stage` sample, `kit` at 0.3, changed a little). Chosen
  over keeping the lift inside a fixed band (which would move every depth-0 thing down) and over
  a band always up to depth 1 (which would change every stage). Layers: `background` and
  `middle` layers are drawn behind the band, so its taller top covers a little more of their
  lower part (hills keep their tops; a layer meant to sit on the horizon goes at a `y` at or
  above `ground_top`). A picture (`image`, `generate`) has no band unless `ground_color` is
  given (then the same rule); its own floor must reach up to where its deepest things stand.
  Test: `tests/test_cartoon_stage.py` (every placement on the ground lies between the bottom
  edge and the band's top, for the example's yard and two more stages) and the props render test
  (the band's top is at or above the tree at depth 0.6).
- **A mouth left behind**: while `dot` walked and spoke, a copy of her mouth stayed where the walk
  began. Lip sync (and blinks, expressions) changed a part's shape by replacing the part slot's
  child with a fresh copy of the shape. Manim lists, when an animation begins, the moving
  mobjects as the flattened families (`Scene.get_moving_mobjects` returns family members), and
  draws that list on every frame: the replaced child stayed in the list, no longer in the
  character, so `shift` and `refresh` no longer moved it, and it was drawn where it was when it
  was swapped out (the camera's follow path lists the same way). The same held for every
  animation on a speaking or blinking character (walk, enter, exit, jump, gesture, keyframes,
  `move_along`, pose changes). Now a `Character` keeps one live copy of every shape of every
  part for its whole life (`parts[name]` holds them in `shape_names` order); the shapes not shown
  have no points, so Manim draws only the shown one, and a swap only moves points (the old
  shape's are emptied, `refresh` draws the new one). The family never changes, so any list made
  from it stays right, and a style set on the character (a fade, `dim`) is kept by every shape.
  Cost: a few more family members per character (the hidden shapes, not drawn). Test:
  `tests/test_cartoon_acting.py` (for a walk, an entrance, a jump, a gesture, a keyed motion and
  a pose change of a speaking, blinking character: what Manim would draw from the list made at
  the start holds nothing outside the character, and every mouth point lies in the head's box;
  it failed for all six before the fix).
- **The review video again**: `/home/claude/work/phase-h-review/cartoon_review_v2.mp4` (the same
  scratch copy and Kokoro audio, 1280x720, 59.93 s).

### 69.23 Automatic directing, part 1: looks and reactions (Step 89)

`auto_direct` adds the routine acting of a dialogue to a stage's beats: listeners look at whoever
speaks, the speaker at the one it talks to, and listeners react after lines. The added actions
are ordinary beat actions (`look_at`, `react`), so the action runner, foley, mid stills, the
layout dump and lint treat them like written ones.

- **Setting** (`config.py`): `AutoDirect(looks, reactions, gestures, closeups)` (Step 107 adds
  `effects`, §69.40) (each `True` by
  default: a kind not given is on), `AutoDirectSetting = bool | AutoDirect`, on `VideoConfig`
  (`False`), the stage param `auto_direct` and `BeatConfig.auto_direct` (both none: inherit).
  `directing_kinds(beat, scene, video)`: the first setting given wins (`true` every kind of
  `DIRECTING_KINDS`, `false` none, a mapping its true kinds); none given: off. `gestures` and
  `closeups` are planned since Step 90 (§69.24).
- **Planner** (`cartoon/directing.py`, no manim): `plan_directions(scene_id, cast, beats) ->
  [DirectedBeat(beat, actions)]` is a pure function of `CastMember(name, can_look, can_emote)`
  (stage order) and `BeatInput(id, text, speakers, actions, kinds)` (the beat's written actions,
  resolved). It walks the beats with one `_SceneState` (who is on stage, what each looks at,
  whom each speaker last addressed, the speakers so far and to come, each character's last
  automatic reaction) and runs, per beat, the pass of each kind on (`_PASSES`, in
  `DIRECTING_KINDS` order). Before the passes, `_follow_written` applies the beat's written
  actions to the state: `enter` / `exit` (characters an `enter` of the scene names are off stage
  until their first `enter` beat, as `Stage` keeps them), `look_at` (its `to`), and
  `LOOK_CHANGING` (`turn`, walks, `move_along`, `keyframes`, `pose`, `emote`), after which the look
  is unknown. A character a written action of the beat targets (by name, wildcard or part,
  except the `FRAMING_ACTIONS` `say`, `zoom`, `pan`, `follow`, `highlight`, `dim`, `callout`) is
  *touched*: no pass adds anything for it in that beat (written actions always win).
  - **Looks** (`_plan_looks`): with speakers on stage, every other present character looks at
    the first speaker, each speaker at its addressee (`_addressee`: the most recent other speaker
    on stage, else the one it addressed before, else the next other speaker of the scene, else
    the only other character on stage, else none); a `look_at` (at 0, run time 0.5) is added
    unless the character is touched, has no head (`ACTION_NEEDS["look_at"]`) or already looks
    there.
  - **Reactions** (`_plan_reactions`): `line_cue(text)` = `question` (a `?`), else `negation` (a
    word of `NEGATIONS`, English, curly apostrophes too), else `exclaim` (a `!`), else none. Each
    present listener that can `emote` and is not touched gets `react` with an expression of
    `REACTIONS[cue]` (`thinking`/`surprised`, `worried`/`sad`, `surprised`/`happy`) other than
    its last automatic one, picked by `random.Random("<scene>/<beat>/<character>")` (seeded by
    the names: the same in every run and process), at `REACTION_AT` 0.95 of the narration, so
    the 0.6 s change plays in the pad (shortened by the runner when the pad is short) and the
    runner undoes it at the next beat (`until_next_beat`).
  - Steps 90 and 95 add passes (gestures, close-ups, shots) to `_PASSES` and fields to
    `CastMember` / `BeatInput` (word timings, positions) as they need them.
- **Tag**: each added action is `ActionConfig.automatic(data)` (private `_auto`, property
  `auto`); `describe()` appends `(auto)` (log lines, mid-still labels), `shorthand()` gives the
  `video.yaml` form (`{NAME: TARGET, ...options, at}`).
- **Merge**: `NarratedScene.auto_actions(project, spec, params)` (class method; default none) and
  `with_auto_actions(spec, directed)` (a copy with each beat's automatic actions after its
  written ones). `NarratedScene.__init__` merges right after parsing the params and sets
  `self.spec` / `self.beats` to the merged scene, before `plan_actions` and the `ActionRunner`;
  the project's config is unchanged. `Stage.auto_actions` = `stage_directions(project, spec,
  characters, params.auto_direct)`: speakers per beat as `Stage.narrate` picks them (`say`
  targets, else `speaking_characters` of `beat_voice`), `can_look` / `can_emote` from
  `character_part_shapes` and `missing_needs`, the action names from the registry (so it runs in
  a project session). `vidgen validate` checks only written actions; the planner emits only
  built-in actions on declared characters with built-in expressions (a test runs
  `scene_actions` on the directed `examples/cartoon`).
- **Fingerprint**: `auto_direct` is in the config; `cartoon/directing.py` is render code. A
  changed setting or planner makes the scene's render stale.
- **Visible**: `project_directions(project, scenes)` (scene id -> directed beats; each scene
  type's `auto_actions`; `directing_used` skips the session when `auto_direct` appears nowhere
  and no `stage` scene may reframe, §69.30).
  `vidgen storyboard`: `SheetStill.auto` (the beat's automatic actions), a wrapped line `auto:
  look_at kit pip · react kit thinking` (`auto_label`, at most `AUTO_LINES` 2) under the beat's
  narration; `--json` frames gain `auto` (the shorthand forms, `[]` for none).
  **`vidgen direct [PROJECT] [--print] [--scene ID] [--variant NAME] [--json]`**
  (`cli.cmd_direct`): without rendering, per scene and beat the added actions (`auto_label`);
  `--print`: `directions_yaml`, a `scenes:` -> `id`, `beats:` -> `id`, `actions:` block (one flow
  mapping per action) to paste into `video.yaml`; once pasted they are written actions, so the
  planner adds nothing more for those characters (tested). JSON (`jsonout.direct_document`):
  `project, variant, scenes: [{scene, beats: [{beat, actions}]}]`.
- **Not done here**: gestures, close-ups and the lint check (Step 90, §69.24), shots (Step 95, §69.29); a negation word list for other languages; a speaker with two or more
  listeners and no one answering looks at nobody in particular; a listener looks where the
  speaker stands when the look starts (not where a walk ends); `examples/cartoon` unchanged
  (with `auto_direct: true` it would add one look: its beats act on both characters); no MCP
  tool for `direct`. Tests: `tests/test_cartoon_directing.py`.

### 69.24 Automatic directing, part 2: gestures, close-ups and the lint check (Step 90)

Two more passes in `cartoon/directing.py`'s `_PASSES` (after looks and reactions, in
`DIRECTING_KINDS` order) and a lint check of what the planner adds. Still no manim and no
rendering: `plan_directions(scene_id, cast, beats, stage=None)` stays a pure function.

- **Inputs**: `CastMember.gestures` (the gestures of `GESTURES` whose `ACTION_NEEDS` entry
  `gesture: <kind>` the character's parts meet); `BeatInput.seconds` and `.words` (the
  narration's length and `WordTime`s from its start: `_beat_words`, the MP3's length else the
  word-count estimate, `beat_word_times` as captions use them; only read for beats with
  `gestures` or `closeups` on and a speaker). `StageFrame(frame_width, frame_height, stage_width,
  camera_x, places, props, marks)`: the stage's geometry in Manim units, `StagePlace(x, feet_y,
  height, facing)` per character; `stage_frame(project, params)` builds it from a `stage`'s
  params with `stage_layout` as `Stage.construct` places them (frame size from the video's
  `format` by `render.worker.frame_size`). `Stage.auto_actions` passes it to `stage_directions`.
- **State**: `_SceneState` also follows each character's feet x (`None`: not known, after a
  `move_along` / `keyframes` of the whole character), its facing and the camera's centre x
  (`None` while it follows): `_follow_written` applies written `enter` (to `to`, else its place;
  facing the way it walks, from the `side` or the view's nearer edge), `walk_to` (facing the way it
  goes), `turn`, `look_at` (facing the target's x by `look_pose`), `pan` (to the targets' or the
  place's x, kept on the stage by `view_center_within`) and `follow`. Automatic looks turn the
  character too.
- **Predicted stills** (`_still`): the beat's still as a lint `StillContext` built from the
  state, 100 px per unit: a `character` object per present character whose x is known, its box
  `FIGURE_HALF_WIDTH` 0.21 heights to each side (with an arm gesture: `GESTURE_REACH` 0.4 / 0.35
  forward for `point` / `wave`, 0.34 to both sides for `shrug`), its `face` from `FACE_BOTTOM` 0.5
  heights up, `facing`, `speaking` (a speaker of the beat), `looked_at`; the frame's `camera`
  (zoom, centre). The proportions are the generator's looks measured (an SVG look is taken to be
  alike). `still_findings(ctx)` runs the registered rules of `CHECKED_RULES` (`off_stage`,
  `facing_away`, their default settings) and returns `(rule, object names)`; an action is added
  only when the still with it has no finding the still without it lacks. `bubble_overlap` needs no
  check: automatic actions draw no bubble and move no face, and no close-up goes into a beat with
  a bubble (the bubble is placed for the view at its start). Without a `StageFrame` (or while the
  camera follows) looks are not checked (as in Step 89), and arm gestures and close-ups are not
  added.
- **Gestures** (`_plan_gestures`): `stressed_word(words, seconds)`: the first `*word*`
  (`emphasis`), else the first all-capitals word of 2+ letters (`capitals`), else the longest word
  of `LONG_WORD_LETTERS` 6+ letters by spoken length (`longest`, only when the speaker did not
  gesture in its previous line: `gestured_line`). `gesture_choices(word, text, seed, last)`: the
  word's own (`NEGATIONS` shake_head, `AFFIRMATIONS` nod, `GREETINGS` wave, `POINTING` point),
  the line's (question shrug, negation shake_head), then `EMPHASIS_GESTURES` (point, nod, shrug)
  shuffled by `random.Random("<scene>/<beat>/<speaker>")`, the speaker's last automatic gesture
  last. The first speaker not touched with gestures takes the first choice its parts allow, that
  fits and passes the check (head gestures always pass): at most one per line. `at` (rounded
  down to hundredths) starts it `GESTURE_EASE` of its length before the word, not before
  `LOOK_SECONDS` 0.5 when the speaker got an automatic look in the beat, and so that it ends
  within the narration; a line too short for it gets none (the action runner would rush it).
- **Close-ups** (`_plan_closeups`): a line of at most `SHORT_LINE_WORDS` 5 words right after a
  beat of at least `LONG_LINE_WORDS` 8 gets `zoom` on its first speaker, `scale: CLOSEUP_SCALE`
  (2, centred on its box, kept on the stage), `run_time` `CLOSEUP_SECONDS` 0.5 when both moves fit
  in 80 % of the narration after the speaker's look, else `CLOSEUP_CUT_SECONDS` 0.03 (a cut in and
  back: under a frame at 25 fps, so the runner plays it at once and never rushes it; the runner
  ends the narration's actions at its end, so a 0.5 s move into a 0.8 s line was shortened and
  `rushed_animation` warned; since Step 95 the cut is a `shot: closeup`, §69.29). Not in the beat after a close-up or a written `zoom`, nor with a
  written `MOVING_ACTIONS` action (walks, `enter`, `exit`, `move_along`, `keyframes`, `pan`,
  `follow`, `zoom`), a `say` with a bubble or an automatic gesture of the speaker, nor while the
  camera follows. The check: on the zoomed view the speaker is wholly in view (`off_stage` on the
  view with the zoom left out of the frame's camera, since the rule skips zoomed stills), and
  `facing_away` adds nothing (in a close-up the one it talks to may be out of view and lint then
  takes the nearest character in view as the listener).
- **Visible**: as §69.23 (`vidgen direct`, the storyboard's `auto:` line); MCP tool `direct`
  (`vidgen direct --json`; read-only; `variant`, `scene`).
- **Measured on `examples/cartoon`** (scratch copies, preview 854x480, `vidgen lint --fail-on
  warning`): with `auto_direct: true` the planner adds a `look_at` (hill_told) and a `shake_head`
  (yard_expert: its `say` only voices moss); lint clean. A copy with only the walks, entrance,
  flight, pan, jump and confetti kept (and `hill_told` cut to "Told you.") gets 13 automatic
  actions (looks, reactions, two shrugs, a cut close-up); lint clean. The committed example is
  unchanged (its explicit actions are the guide's example of writing them).
- **Emphasis marks** (Step 91): `BeatConfig` takes the asterisks of `*word*` out of `text` when
  the config is read (`config.EMPHASIS`, `strip_emphasis`; one word or a few, not `2*3*4`, `a * b`
  or `**bold**`) and keeps the written text in the private `_marked_text` (`marked_text`). So every
  reader of `beat.text` (TTS and its hash, captions, SRT, bubbles, readback, lint, slides) gets it
  without them; a beat without marks is unchanged (its audio hash too). `_beat_words` times the
  plain text and gives each word its written form (same word count), `stage_directions` passes
  `marked_text`, so `stressed_word` still finds `*word*`. The scene fingerprint adds `emphasis`
  (beat id -> marked text) when a scene has marks, since they change the automatic gestures.
- **Not done here**: English word lists; a close-up waits for changes to its speaker at
  the beat's start (the undoing of the speaker's reaction of the beat before) before it moves;
  depth and props are not in the predicted stills (`hidden_speaker`, `character_overlap` not
  checked: automatic actions move no one); a written `zoom` with `until` is not followed (the
  planner takes the camera as unzoomed); shots: §69.29. Tests:
  `tests/test_cartoon_directing.py` (Step 90 part).

### 69.25 Screenplays (Step 91)

`vidgen screenplay FILE [--out DIR|FILE.yaml] [--cast FILE] [--species NAME ...] [--seed S] [--force] [--json]` (`cli.cmd_screenplay`, MCP tool
`screenplay`) makes a stage project from a screenplay without AI. `screenplay.py` (no manim;
props' kinds imported when a `set:` line is read) has the parser and the builder; the writing is
`vidgen plan`'s (`plan_yaml.commented_yaml`: a config with comments above top-level keys, scenes
and, new, beats, checked to load back; `write_project`: scaffold like `vidgen init`, write the
config; `write_plan` now calls both, its output unchanged).

- **Parsing** (`parse_screenplay(text) -> Screenplay(title, front, scenes)`): optional YAML
  front matter (a mapping of top-level keys; `scenes` refused); elements by `_paragraphs` (a
  heading, `set:` or `NAME:` line stands alone; other lines join the element above until a blank
  line; HTML comments dropped). The first level-1 heading not starting with `Scene` is the title;
  any other heading starts a `ScriptScene` (`Scene:` stripped; text before any heading: `scene 1`).
  `set:` lines right under it are joined. `[...]` alone is a `Direction`; `NAME [(manner)]: text`
  (`_SPEAKER`: words in capitals) a `Line`, its inline `[...]` taken out as directions with `at` =
  words before / words (≤ 0.9) and the speaker as default subject; `NARRATOR`, `NARRATION`,
  `VOICE OVER`, `V.O.` and plain paragraphs are the narrator (`speaker None`). Errors
  (`VidgenError`) name the line.
- **The set** (`parse_set(text, names) -> SetDesign(params, placed, props, todos)`): `;` parts
  `background` (`SKIES` gradient + `GROUNDS` colour, else tokens / hex / `a to b`, else an image
  file), `props` (built-in `PROP_KINDS`, `kind (name) at place`, else the next of `PROP_SLOTS`;
  `BACKDROP_PROPS` house / tree get `depth`), `marks`, `characters`. Not understood: a scene
  `# TODO:`. Characters not placed take the marks of `PLACES[count]` at least `SPACING` 0.12 from
  placed ones, in order of appearance; the scene's cast is the placed, speaking and
  direction-named characters (`_scene_cast`).
- **Directions** (`direction_actions(text, state, default) -> (groups, unmatched)`): sentences
  (`.`, `;`, `!`, `then`) cut at `and` unless a name follows (`_clauses`); leading `then` /
  `suddenly`..., trailing `-ly` words tried off on a second attempt. Subject: character names
  (written names and, for a multi-word name, its last word when unique), `he` / `she` / `it` for a
  single last subject, `they`; else `default`. `_VERBS` (in order): walk / go / run... `to` ->
  `walk_to` (a mark or x as given; a prop or character: `PROP_GAP` 0.1 / `CHARACTER_GAP` 0.14
  before it on the walker's side; when another character stands within `CHARACTER_GAP` of that
  spot, the other side, then `CHARACTER_GAP` further out (Step 106); `runs` `speed: RUN_SPEED`
  5), `enter` / `exit` with a side,
  `jump`, `look at` (characters, props by name or unique kind, marks, `camera` / `us`; `each
  other`), `point at` (`look_at` + `gesture: point`), `wave` / `nod` (+ a look when they name
  someone), `shrug`, `shake ... head`. `StageState` follows each character's x (`home`: its
  starting mark), the last subjects and object (`it`, `him`, `her`). Each action carries its
  estimated seconds (`walk_motion_seconds(walk_seconds(distance))`, a jump's, `LOOK_SECONDS`,
  `GESTURE_SECONDS`, + `MARGIN` 0.1); `_add_scene`'s `attach` puts a beat's direction groups one
  after the other: `at` = start / the line's estimated seconds (words / 2.6, or the front
  matter's `narration.words_per_second`), rounded down, ≤ `LATEST_AT` 0.95. Directions before a
  line start at its 0; after a scene's last line at `TRAILING_AT` 0.6 of it; inline ones at
  their word. A manner (`manner_actions`: built-in expression / pose names, `MANNERS` words) is a
  `react` first in the beat; unknown words and unmatched sentences are beat `# TODO:`s.
- **Characters and voices** (`screenplay_project`): front matter `characters` are kept as
  written (declared; only a screenplay `voice_kind:` key is taken out); every other speaker
  (`character_id`: `OLD ASH` -> `old_ash`) gets a look of `LOOKS` (eleven looks differing in body,
  hair, eyes, ears, accessories, skin, clothes and hair colours, the last five also in outfit,
  pattern, shoes and facial hair, §69.47; since Step 115 no look is taken twice: random
  well-contrasted looks follow, §69.49) and a `<id>_voice`
  entry with `label`. **Voice kinds** (`VOICE_KINDS` feminine / masculine / neutral; Phase I
  review follow-up): each look carries the `voice_kind` that suits it (bun + scarf, long hair,
  ponytail + dress and braids + apron feminine; tall short hair + glasses, bald + hat, beard +
  coat and moustache + shorts masculine; the other three neutral). `_stated_kinds` reads a kind from a pronoun in a line's brackets (`FEN (she): ...`,
  `(he, doubtful)`, `(they)`; `_pronoun_kind` takes it out of the manner, `Line.voice_kind`;
  `PRONOUN_KINDS`) or a front matter character's `voice_kind:`; two kinds for one character, a
  pronoun on the narrator or an unknown kind are `VidgenError`s naming the line.
  `_generated_looks` (Step 115, replacing `_pick_look`; §69.49) gives a generated character the
  first unused look of its stated kind (then a neutral look; without a kind: the first unused
  look in order) that keeps `MIN_CONTRAST` against the declared, cast and earlier generated
  characters, else a random look of its kind, and the character's voice kind is the stated one,
  else its look's. Declared characters keep their entries; one without a
  `voice` gets one of its stated kind (else any).
  `assign_voices(voice, language, kinds)` (`kinds`: one per character, or a count of
  characters without a kind): Kokoro: the voices of the narrator's language
  (`kokoro_voices.resolve`), for English American and British, grouped by accent and gender,
  each group best grade first without the narrator's voice (and no `santa` voice), the narrator's
  own group last; `_kokoro_picks` takes for each character a group of its kind's gender
  (neutral: the gender used less so far), the least used group, then the least used accent, then
  in order; within a group the next voice. Without kinds this gives the groups in turn as before.
  OpenRouter: the model's listed voices (`openrouter.known_voices`) without the narrator's, in
  turn (no kinds known); ElevenLabs: no list, the entries only get a `label` and a video `# TODO:`
  asks for `voice_id`s, naming each character's voice kind. Defaults (`DEFAULTS`): 1920x1080,
  preview 854x480, `soft_pastel`, Kokoro `bf_emma` at 0.85, `narration.pad` 0.7, `auto_direct:
  true`; front matter keys win.
- **Output**: a header comment, `# generated: ...` above `characters`, the notes above `voices`,
  scene and beat `# TODO:`s; then `validate_all` (exit 1 on problems). JSON:
  `jsonout.screenplay_document`.
- **Sample**: `examples/screenplay/humming_box.md` (three original characters, two scenes): 11
  beats, 0 TODOs; the project validates, `vidgen lint` (preview) finds nothing, `vidgen direct`
  adds 18 actions (looks, reactions, a head shake on `*anything*`, a shrug). Tests:
  `tests/test_screenplay.py`.
- **Not done here**: English grammar and manner words only; no grammar for props moving, sitting
  (Step 94), holding (Step 93) or shots (Step 95, §69.29); a walk to a character goes where it stood at
  the start of the beat; one set per scene (no set changes inside a scene); ElevenLabs voices are
  not chosen.

### 69.26 Arms and legs in two segments (Step 92)

Arms and legs bend at the elbow and the knee. `cartoon/limbs.py` (no manim) holds the limb names,
the two-bone solver and the fold of one-piece limbs; `Character` (§69) applies them.

- **Parts**: `arm_left` / `arm_right` keep their names and are now the upper arm (pivot: the
  shoulder); `arm_left_lower` / `arm_right_lower` are the forearm and hand (pivot: the elbow,
  parent: the upper arm). Legs are either `legs` (both in one piece, as before) or `leg_left` /
  `leg_right` (a thigh each, pivot the hip, parent `body`) with optional `leg_left_lower` /
  `leg_right_lower` (shin, pivot the knee); a character with `legs` and a single leg is a
  `VidgenError` (and an SVG split error). Draw order: each lower segment over its upper one, the
  far leg (`leg_right`) behind the near one, all legs behind the body. `CharacterPart.end` (new,
  optional) is the hand's middle or the foot's sole on a limb's last segment; without it the
  drawn point of the limb farthest from its root is taken. A default parent the character lacks
  is replaced by its own parent (a forearm without an upper arm hangs from the body); an
  explicit `parent` must still exist.
- **Generated characters** (`generator.py`): arms and legs in two capsule segments
  (`LIMB_WIDTH` 0.08, round ends centred on the joints, so a bent joint stays smooth); the elbow
  and the knee half-way; the sole at the ground. The figure at rest is unchanged in size and
  place (the sleeve and leg ends are rounder). They have no `legs` part any more: one-leg parts
  replace it (`cast.GENERATED_SHAPES`).
- **Solver** (`solve_two_bone(root, target, upper_length, lower_length, bend) -> TwoBone(direction,
  bend, reached)`): law of cosines; `bend`'s sign picks the joint's side (`ELBOW_BEND` +1:
  counterclockwise as drawn facing right, the hand forward and the elbow behind / below the line
  to the hand; `KNEE_BEND` −1: the foot back, the knee forward). Too far: straight at the point;
  too near: folded as far as the lengths allow; `reached` says which.
- **Character API**: `reach(hand, point, bend=+1)` (`hand` `left` / `right`), `plant(foot, point,
  bend=-1)` (needs `leg_left` / `leg_right`), `hand_point(hand)`, `foot_point(foot)` (screen,
  Manim units; Step 93 holds props at `hand_point`), `sole_height(state=None)` (the lower sole
  above the ground, character units; `None` without single legs), `grounded(state, level=0)`
  (the body shifted so the lower sole is at `level`). `reach` / `plant` work in the parent's frame
  through the inverse of the screen matrix, so facing left, squash and Manim moves are handled;
  they set only the two angles (shift and scale kept; lengths as drawn at rest).
- **One-piece limbs keep working (folded)**: a character with `arm_left` but no `arm_left_lower`
  (sprout, any older SVG) still has a pose for `arm_left_lower` (in `state()`, `pose_of`,
  `set_part`, poses, gestures and walks; not in `parts`, `has_part`, keyframe targets). Its bend
  `b` is shown on the one piece by `fold(b)`: turned by `b / 2` and shortened along the limb
  to `cos(b / 2)` (at least `FOLD_MIN_LENGTH` 0.6) about the root, which puts its end where a limb
  of two equal halves would. So `reach` also works on one-piece arms, and the built-in poses and
  gestures were chosen so that upper + half the elbow is the one-piece angle they had before
  (pointing 82 + 12/2 = 88, wave 115 + 60/2 = 145, shrug 15 + 60/2 = 45, waving 150, thinking
  160; arms_crossed −55 against −65). The look changes a little: a bent one-piece arm is shorter
  (waving 0.82, thinking 0.6 against the old explicit 0.72, arms_crossed 0.77 against 0.8).
  `validate` does not warn about a lower segment whose upper part the character has.
- **Poses** (§69.3): `pointing`, `waving`, `thinking`, `shrug`, `arms_crossed` bend the elbows;
  `sitting` names both `legs` (80°, one piece) and the single legs (thighs 80° / 75°, knees
  −35°: the feet forward on the ground); a character uses the entries of the parts it has. A
  pose names the new parts like the others (`PosePart`), so own poses can bend elbows and knees.
- **Pose changes**: `part_windows` gives a part of `TIMING_GROUP` its group's window: a lower
  segment moves with its upper part, single legs together as `legs` did, so pose changes keep
  their timing.
- **Gestures** (§69.12): `point` and `wave` turn the upper arm and bend the forearm
  (`POINT_DEGREES` 82 + `POINT_ELBOW` 12; `WAVE_DEGREES` 115 + `WAVE_ELBOW` 60, the wave's
  `WAVE_SWING` 40° to and fro now about the elbow), `shrug` both (15 + 60). The planner's
  `GESTURE_REACH` (§69.24) was measured again: the reaches did not grow (round look: point 0.484
  → 0.484, wave 0.384 → 0.373, shrug 0.415 → 0.386 heights), so it stays.
- **Walk** (§69.12): legs in one piece walk as before. Single legs swing opposite ways
  (`WALK_THIGH_DEGREES` 20), the knee of the leg swinging forward bends most as it passes the
  other (`WALK_KNEE_DEGREES` 40 × max(cos πs, 0)) and both are straight at the footfall; elbows
  bend `WALK_ELBOW_DEGREES` 10, plus `WALK_ELBOW_SWING` 20 as the arm swings forward
  (`WalkCycle.thigh_angle`, `knee_bends`, `elbow_bends`). Instead of the fixed `WALK_BOB`, `Walk`
  keeps the lower sole at the height it started at (`grounded`; only when that is within
  `GROUND_TOLERANCE` 0.02 of the ground, so a sitting walk is not pulled down): the body dips at
  the footfall and rises as the legs pass, and no foot sinks or floats.
- **SVG** (§69.2): ids `arm_left_lower`, `leg_left`, `leg_left_lower`, ... (the longest part name
  wins, so `arm_left_lower` is a part, no longer arm_left's shape `lower`); default pivots: a single
  leg and a lower segment the top centre of their box; `pivot_warnings` names them too; the feet
  are under the middle of all leg parts. `examples/svg_character`'s sprout stays one-piece (the
  compatibility case); its raised hand in `waving` / `thinking` is behind its head, as before,
  since the file draws `arm_left` before `head`.
- **Not done here**: no knees in `Jump` (the crouch is still the whole-figure squash); no
  follow-through on forearms; no YAML action for `reach` / `plant` (Step 93's `pick_up`, Step
  94's sitting use them); a generated `legs` reference (an own pose's `legs:`, a `kit.legs`
  keyframe target) no longer applies to generated characters (validate warns / reports an
  unknown part). Tests: `tests/test_cartoon_limbs.py`.

### 69.27 Props in hands (Step 93)

Five beat actions (`scenes/handling.py`, against `vidgen.api` only, on the `_Acting` base of
§69.11: the targets are characters) let a stage's characters handle its props: `pick_up`,
`hold`, `put_down`, `give`, `throw`. Same `to:` convention as §69.11–69.12: the character is the
target; `to` is the prop (`pick_up`, `hold`), the place (`put_down`, `throw`: a mark or x) or the
other character (`give`); `prop` picks one of two held props, `hand` a hand (`left`, the near
one, drawn in front of the body; `right`).

- **State** (`cartoon/holding.py`, no manim): `Holdings` maps prop -> (character, hand).
  `take(character, prop, hand=None)` (a free hand, `HAND_ORDER` left first), `release(character,
  prop=None)` (the only prop it holds, else `prop` must say which), `give(giver, receiver, prop,
  hand)`, `hands(character)`, `holder(prop)`; each refusal is a `HoldingError` whose message says
  what to do (`'ball' is held by pip; pip can give it (give: pip, to: kit)`, `kit holds no prop
  then; pick_up one first`, a full hand). The stage keeps one (`Stage.holdings`), `vidgen validate`
  replays the scene through one, and the directing planner keeps one.
- **Attached, not added** (§69.22's invariant): a held prop never becomes a part or a submobject
  of its character (the character's family never changes, and the layout dump's character box is
  the figure only). It stays its own mobject; `attach` gives it an updater that puts its middle at
  `Character.hand_point(hand)` on every frame and moves it in `scene.mobjects` to right after its
  holder (drawn in front of it, behind whatever is drawn after the holder: characters nearer the
  camera, foreground layers). Manim runs the updaters after the frame's animations, so the prop
  follows walks, jumps, turns, gestures, pose changes, keyframes and exits of its holder.
  `Character.holding` (hand -> prop) and `Prop.held_by` / `Prop.hand` record it; the layout dump
  writes them as `holding` (character) and `held_by` / `hand` (prop).
- **Geometry** (Manim units, character heights): `hold_point(shoulder, height, facing)`: the
  hand and the prop's middle `HOLD_FORWARD` 0.12 heights in front of the arm's shoulder
  (`Character.shoulder_point`) and `HOLD_DROP` 0.13 below it, within reach of the generated
  arms (0.23 heights long) with the elbow bent. `held_height(factor, holder_height)`: a prop's
  height next to its holder (`Prop.height_factor`, set by the stage from `StageProp.height_factor()`),
  at most `HOLD_MAX_HEIGHT` 0.4 of it. A put-down or landed prop stands on the ground at its
  character's depth (that character's feet y) at `factor` × that character's height.
  `put_down_x`: `PUT_DOWN_AHEAD` 0.35 heights in front of the feet. Throws: `throw_point(t, start,
  end, rise)` (x even, y a parabola peaking `rise` above the higher end), `spin_degrees` (whole
  turns, clockwise flying right), `throw_seconds(distance)` = `THROW_WIND_UP` 0.35 +
  `THROW_SWING` 0.15 + flight (0.45 s + 0.06 s per unit, at most 1.6 s).
- **Animations** (`cartoon/transition.py`, exported): `ArmMove(character, keys)` eases the parts
  named in `(share, part -> PartPose)` keys from their pose at its start (`smooth`, held after the
  last key; like `PoseChange` it ends a blink and keeps lip sync in step). `PropMove(prop, to=,
  follow=, leave=, arrive=, height=, rise=, turns=, lands=)`: until `leave` the prop is at
  `follow()` (a hand) or where it is; from `leave` to `arrive` it goes to `to` (a point, or a
  function read every frame, such as the receiver's hand), changing to `height`, on an arc with
  spin when `rise` > 0; each frame is drawn from its points at the start (so it ends upright);
  `lands_at` is `arrive` for a landing. Arm targets come from `Character.reached_parts(hand,
  point)` (new: the poses `reach` would set, without setting them; `reach` uses it).
- **Actions**: `pick_up` (`ArmMove` to the prop's top at `REACH_SHARE` 0.45 then to the hold
  point; `PropMove` from there into the hand, scaled to its held height; 1.2 s), `hold` (the arm
  to the hold point while the prop moves into the hand, 0.4 s; no distance check: for a prop the
  character has from the start), `put_down` (reaches to the spot at 0.5, the prop goes from the
  hand to the ground by 0.75, the arm back to its pose before the prop was taken; 1.0 s), `give`
  (both turn to face each other at once, both reach to the middle of their hold points at 0.45,
  the prop goes from one hand to the other; 1.2 s), `throw` (turns towards the spot, the arm winds
  up behind and above the shoulder, swings forward and lets go at `throw_release_share`, settles
  back; the prop flies, spins `spin` turns and lands; `run_time_for` = `throw_seconds`). The
  arm's pose before the prop was taken is kept with the held prop and put back when it is let
  go. A character holds at most one prop per hand.
- **Validate**: each use's `scene_problems` checks names (a prop of the stage, a character on
  the stage and not the giver, a place); the new class hook `NarratedScene.action_sequence_problems
  (spec, params, uses)` (default none; `scene_actions` calls it once every use is valid, so
  `vidgen validate` and the render's `plan_actions` both run it) lets the stage replay the scene's
  actions in play order (beat, `at`, written order) through `holding_problems` with
  `stage_frame`'s geometry: characters' x from their marks, `walk_to` / `enter` move them,
  `move_along` / `keyframes` make them unknown (no distance check), `exit` / `enter` take them off
  and on; a prop's x is its holder's while held and the spot after `put_down` / `throw`. Reported:
  a prop someone else holds, a full hand, nothing to put down / give / throw, two props and no
  `prop`, `pick_up` farther than `PICK_UP_REACH` 0.75 heights, `put_down` farther than
  `PUT_DOWN_REACH` 0.75, `give` to a character farther than `GIVE_REACH` 1.2 heights or not on
  stage, a `keyframes` / `move_along` of a held prop. The distance messages end with the
  `walk_to` that fixes them (`STAND_BESIDE` 0.4 heights from the prop on the character's side,
  as a 0..1 x).
- **Foley** (§69.19): `PlayedAction.lands` (share of the action's time); `foley_cues` gives a
  `thud` (`LANDING_GAIN` −4 dB) there; `Stage.action_foley` passes a `PropMove`'s `lands_at`.
- **Automatic directing** (§69.23–24): the planner's state follows the written prop actions
  (`Holdings`, and where a put-down or thrown prop stands, for `look_at` a prop); an arm gesture
  is not added while a hand it moves holds a prop (`GESTURE_HANDS`: `point` / `wave` the near
  hand, `CastMember.near_hand`, `shrug` both); prop actions count as moves for close-ups
  (`MOVING_ACTIONS`). Storyboards show `pick_up`, `put_down`, `give` and `throw` half-way
  (`mid_still_actions`).
- **Not done here**: a crouch to the ground came with Step 94 (§69.28); a held prop is not mirrored when
  its holder turns, and pose changes and gestures of the holding arm move it (written ones are
  allowed); `dim` / `highlight` on a held prop pauses its following for that animation (Manim
  suspends a mobject's updaters while it is animated); no `on: <prop>` to put a prop on a
  table; the screenplay grammar (§69.25) has no prop verbs yet. Tests:
  `tests/test_cartoon_holding.py`.

### 69.28 Sitting, leaning and crouching (Step 94)

Three beat actions (`scenes/sitting.py`, against `vidgen.api` only, on the `_Acting` base of
§69.11) let a stage's characters sit on its props and lean on them, and `pick_up` / `put_down`
(§69.27) crouch for a low prop. They reuse the two-bone solver of §69.26 for the hips and knees.
The target is the character; `to` is the prop.

- **Seats and lean edges** (`cartoon/seating.py`, no manim), in prop units (origin the middle of
  the prop's foot, `y` up, top 1, `x` in the same unit) as drawn facing right:
  `PROP_SEATS` (the middle of the seat line: chair (0.1, 0.54), rock (0, 0.9), box (−0.1, 0.9)),
  `PROP_LEANS` (the left and right x a back leans on: tree ±0.08 (the trunk), door ±0.3, sign
  (−0.4, 0.36) (the board), lamp ±0.04, house ±0.5), `SEAT_BACKS` (`chair`: a sitter faces the way
  it faces); the furniture's seats and lean edges are in §69.43. `Prop` keeps `seat` / `lean` mirrored with its facing (`mirrored_seat`,
  `mirrored_lean`); `seat_point()` / `lean_edges()` give them on screen. An SVG prop gives
  `data-seat="x y"` / `data-lean="left right"` on its `<svg>` element in `viewBox` coordinates
  (the sanitiser keeps them; `svg_seat_and_lean`, `read_svg_seat_and_lean`; a bad value is a
  `VidgenError`).
- **State**: `Postures` maps character -> (`sitting` | `leaning`, prop): `sit` (one sitter per
  prop; per place on a sofa or a bed since Step 110, §69.43), `lean` (several may lean on one), `stand`, `pinned(character, action)` (refuses
  `PINNED_ACTIONS`: `walk_to`, `enter`, `exit`, `jump`, `turn`, `move_along`, `keyframes` while it
  sits or leans); each refusal is a `PostureError` saying what to do (`pip sits on 'chair' then;
  stand_up first (- stand_up: pip)`). The stage keeps one (`Stage.postures`), `vidgen validate`
  and the planner too. `Character.sitting_on` / `leaning_on` record it (layout dump keys of the
  same names).
- **Character states** (`Character`, none drawn; character units as drawn facing right):
  `seated(state, seat)`: the body shifted until the hips (the leg parts' pivot; without legs the lowest
  point of the body) are on the seat (since Step 102, §69.36; before, the body's lowest point);
  single legs planted at `seated_sole(hip, thigh, shin)` (the shin straight down to the ground in
  front, the knee forward; a seat higher than shin + thigh: the thigh level, the foot hanging; a
  seat too low: folded); a one-piece `legs` part turned forward until its end is on the ground
  (`acos(hip height / leg length)`), or `SEATED_LEGS_DEGREES` 80 when the seat is higher than the
  legs are long. `leaning(state, degrees=LEAN_DEGREES 12)`: the body turned back about its pivot
  (the legs, its children, swing forward), lowered until the higher sole is on the ground and both
  soles planted there. `lowered(state, drop, stoop=, soles=)`: the body `drop` lower and turned
  `stoop` degrees forward, the soles planted where they were (a one-piece `legs` part shortened
  from its top and turned back upright instead). `planted(state, soles)` re-solves each single leg
  so its sole is at a point (`plant` for a state); `sole_points`, `part_box`, `limb_rest`,
  `hip_height` read the geometry. `reached_parts(..., state=)` reaches from the shoulder of a
  state (a crouch). `_limb_poses` now works in character units with given poses, so `reach`,
  `plant`, `reached_parts` and `planted` share one solver path.
- **Animation**: `BodyMove(character, keys, x=, facing=, soles=)` (`cartoon/transition.py`) is
  an `ArmMove` (parts eased through keys) that faces `facing` at its start, eases the feet's x to
  `x` and, with `soles`, re-plants the single legs every frame on the way from their soles at the
  start to `soles` (so feet stay on the ground while the hips go down or up).
- **Actions**: `sit_on` (`SIT_SECONDS` 1.0): the character's feet x goes to the seat's x, it
  faces the chair's way (rock, box: its own), and eases to `seated` with the seat
  `(seat_y − feet_y) / height` character units high. `lean_on` (`LEAN_SECONDS` 0.8): it faces
  away from the prop (it stays on its side), eases to `leaning`, and its feet x is put where the
  back edge of its body (`part_box("body")` of the leaning state) meets the prop's near lean edge.
  `stand_up` (`STAND_UP_SECONDS` 0.8): the body and legs back to how they were before the
  `sit_on` / `lean_on`, the feet x moved to the middle of its soles (it stands up over its feet,
  so they stay put on screen). Only body and legs (`POSTURE_PARTS`) change; arms and head keep
  their poses. One character per action (the first target), like the prop actions.
- **While seated or leaning** (`is_posed`): `look_at` keeps the facing and tilts only the head
  (the point is taken on the side it faces); `pose` / `react` keep the body and legs
  (`_kept_posture`); `give` / `throw` do not turn it; it does not crouch.
- **Crouch** (`handling.crouch`): when the arm (`limb_rest`: upper + lower, using `CROUCH_REACH`
  0.95 of it) cannot reach the point from the shoulder, `crouch_drop(above, ahead, arm, hips)` is
  how far the body lowers (at most `CROUCH_MAX` 0.6 of the hips' height), `crouch_stoop` bends it
  forward up to `CROUCH_STOOP` 15° in proportion; under `CROUCH_MIN` 0.01 no crouch. `pick_up` and
  `put_down` then play a `BodyMove` with the soles kept: crouched with the arm at the prop at the
  reach share, standing with the carry (or the arm before) at the end. A point still out of reach
  (beside, not below the shoulder) is reached as far as the arm goes, as before.
- **Validate**: `_Posture.scene_problems` checks the prop (of the stage, with a seat / lean
  edges; an SVG prop's attributes read through the sanitiser); `holding_problems` (§69.27) also
  replays the postures: a seat taken, a prop held, a prop farther than `SIT_REACH` 0.75 /
  `LEAN_REACH` 1.0 heights (with the `walk_to` that fixes it; sitting or leaning puts the
  character at the prop's x), a `stand_up` with nothing to stand up from, a pinned action of a
  posed character, a `pick_up` / `hold` / `keyframes` / `move_along` of a prop someone sits or leans
  on. `Stage.action_sequence_problems` runs it when a scene has a handling or posture action.
- **Automatic directing** (§69.23–24): the planner follows written `sit_on` / `lean_on` /
  `stand_up` (`Postures`; a seat's facing from `StageFrame.seat_facings`, a leaner faces away
  from its prop); a posed character is not turned by a look (`_turn_to`) and gets no look at a
  speaker behind it (`_behind`); the three actions count as moves for close-ups and make a look
  unknown. Storyboards show them half-way (`mid_still_actions`).
- **Checked by eye** (scratch storyboards at 854x480): a tall generated look and sprout on a
  chair, a rock and a box; leaning on a tree, a door and a sign; crouching to pick up and put down
  a box (generated) and a ball (sprout, shortened legs).
- **Not done here**: sitting on the ground or on a table; a seat at another depth than the
  character's is not refused (the hips go to the seat's screen height); no arms on the prop while
  leaning; no foley for sitting down. Tests: `tests/test_cartoon_seating.py`.

### 69.29 Shots within a scene (Step 95)

A beat's `shot:` frames characters of a `stage` for that beat: the camera cuts (or, with `move:
true`, eases) to a framing computed from where they stand, holds it for the beat, and the next
beat without a shot goes back to the view before the shots.

- **Framing maths** (`cartoon/shots.py`, no manim). `ShotFigure(name, x, feet_y, height, facing,
  top)` (the figure's middle x, its feet, its standing height, the top of its head: lower while
  it sits); its box is `FIGURE_HALF_WIDTH` 0.21 heights to each side (as the planner's predicted
  stills, §69.24). `frame_shot(kind, subjects, frame_width=, frame_height=, bounds=, near=) ->
  ShotView(center_x, center_y, scale)`, kept inside `bounds` with `view_center_within`, scale
  within 1 .. `MAX_SHOT_SCALE` (= `MAX_ZOOM` 8, what the parallax layers are sized for):
  - `wide`: scale 1, centred on the middle of the subjects' boxes (the stage's middle without any);
  - `two_shot`: the union of the subjects' boxes with `TWO_SHOT_PADDING` 0.1 of the view free on
    each side (the tighter of the width and height fits);
  - `medium` / `closeup`: `SHOT_SPANS` (below / above the head's top, in heights) 1.0 / 0.12 and
    0.62 / 0.1 give the view's height, so its scale; the subject moved `LOOK_ROOM` 0.1 of the
    view's width away from the side it faces;
  - `over_shoulder` (subject, near): vertically like `medium`; the view's width puts the subject
    at `SUBJECT_AT` 0.66 of it from the near character's side and the near one's middle on that
    edge (scale `0.66 × frame width / their distance`, between 1 and the close-up's scale); then
    centred from the subject, so a clamped scale keeps the subject in place. Characters are flat
    and side-on, so the near character is as large as the subject (both magnified), cut by the
    edge; far apart (the `left` and `right` marks) the shot is only about 1.3x.
  - `shot_figures(kind, named, present, speakers=, looked_at=) -> Shot(kind, subjects, near)` fills
    in names: `wide` every present character; `two_shot` the named two, else the named one or the
    beat's first speaker (else the first present) and the present character nearest it;
    `over_shoulder` the near one named second, else the one the subject last looked at, else the
    nearest. A named character not present (waiting to enter, gone) is left out; nothing to frame
    gives a `wide`. `shot_view(shot, present, ...)` = `frame_shot` of those figures.
- **Config** (`config.py`): `ShotConfig(kind, of, move, run_time)`, from a mapping or the words
  `"over_shoulder kit pip"` (`of` may be one name). `SHOT_NAMES` (kind -> fewest, most names: wide
  0, two_shot 0–2, medium 1, over_shoulder 1–2, closeup 1) checked there, names twice, `run_time`
  without `move`. `BeatConfig.shot`. `ShotConfig.action()` is the `shot` action it stands for.
- **The `shot` action** (`scenes/shot_action.py`, against `vidgen.api`, on `_Acting` so its
  targets must be characters): options `kind` (none: back to the view before the shots) and
  `move`; `needs_target` / `needs_visible` false (a character waiting to enter is not brought
  in), `moves_camera`, `alters_targets` false, run time `SHOT_MOVE_SECONDS` 1.0 when moving, 0
  (`run_time_for`) when cutting. `scene_problems`: a scene type without `shot_framing` (only
  `stage`) is refused; the targets' names are checked as for the acting actions. `apply`: asks
  `Stage.shot_framing(kind, names)` for the view (present = characters whose feet are inside the
  stage; `ShotFigure` top = the highest of the `head` and `accessory` parts, so a hat is in
  frame; height = the new `Character.standing_height`; speakers = `Stage.beat_speakers`, set by
  `narrate`; `looked_at` of each character), stores the view before the first shot and what the
  camera followed in `NarratedScene.shot_home`, stops following, sets `NarratedScene.camera_shot`
  (`Shot.layout()`), and cuts by setting the camera frame directly (no animation: the runner
  batches a camera move with the other actions due on its frame and plays the batch for the
  longest run time, so a cut must not be an animation) or returns a `MoveCamera`. Without a kind
  it goes back to `shot_home` (cut, or `MoveCamera` / `_MoveThenFollow` when following was
  paused) and clears both attributes. `pan` and `follow` call `end_shot` (both cleared): the
  camera stays where they take it.
- **Where shots come from** (`actions.beat_action_list(spec, known)`, the list `scene_actions`
  validates and the runner plays): each beat's `shot:` key first (location `beats[j].shot`), then
  its written actions; a beat after one with a shot (key or a written `shot` action with a kind)
  gets a `shot` without a kind first, unless it has a shot at `at: 0` (`move` and `run_time` as the
  last shot, so it eases back as it eased in). The planner reads the key too (`_resolved_actions`).
- **Layers, particles, bubbles, stills**: a cut changes the camera between two plays; the next
  play's `get_moving_mobjects` runs the camera listeners first (§69.20), so the parallax layers
  and Manim's static image are for the new view; particles draw themselves over the view each
  frame (screen-sized, §69.9). A `say` bubble is `after_camera`, so it is built (sized and placed)
  for the shot's view. Beat-end and mid-action stills (§69.16) show the shot as rendered; a walk
  in a shot can leave the view (the shot does not follow).
- **Layout dump / lint**: frames in a shot get `shot: {kind, subjects, near}`
  (`introspect`, from `camera_shot`). `off_stage` with a shot other than `wide`: only the
  subjects are checked, also when wholly outside or zoomed; their `face` box in `medium`,
  `over_shoulder` and `closeup` (`FACE_SHOTS`), their box in `two_shot`; the near character and
  characters not framed are left out. Without a shot, a zoomed still is still skipped (§69.17).
- **Automatic directing** (§69.24): `shot` is a framing action (`FRAMING_ACTIONS`: it does not
  touch its characters) and a move (`MOVING_ACTIONS`: no close-up in its beat; after it, none in
  the next). A close-up whose 0.5 s moves fit the line stays a `zoom`; otherwise (was: a 0.03 s
  zoom cut in and back) it is a `shot` of kind `closeup` of the speaker, held for the line and cut
  back at the next beat: no cut back at the end of the pad, and the framing is a close-up (head and
  shoulders), not a 2x zoom. Its check (`_closeup_shot`) predicts the still with the shot's view
  and `shot` key, so `off_stage` checks the speaker's face and `facing_away` the one it talks to
  if in view. In a beat with a written shot, the passes check their looks and gestures on the
  shot's view (`_SceneState.shot`); a shot whose framing cannot be predicted leaves the camera
  unknown for that beat (no arm gestures, unchecked looks). `vidgen direct --print` writes an
  automatic shot as the beat's `shot: closeup kit` line (and `actions:` only when others remain),
  `auto_label` as `shot closeup kit`; `--json` keeps the action's shorthand.
- **Not done here**: the shot does not follow a walk (lint reports a subject that walks out); a
  pan or follow in a shot ends it; a seated character's head top is taken from its parts at
  runtime but from its standing height in the planner; no shots in `vidgen screenplay`'s grammar;
  the near character of an over-the-shoulder shot is not drawn larger (no depth change). Tests:
  `tests/test_cartoon_shots.py`.

### 69.30 Vertical cartoons follow the speaker (Step 96)

On a `stage` wider than the frame the camera keeps whoever speaks in view (`reframe: speaker`),
so a cartoon written for 16:9 renders in a 9:16 variant without camera directions of its own.

- **Setting** (`config.ReframeSetting` = `speaker | none`): `VideoConfig.reframe` and the stage
  param `reframe` (the stage's wins), both default none. `directing.stage_reframes(project,
  params)`: the setting if given, else `speaker` when the characters' boxes (`FIGURE_HALF_WIDTH`
  heights to each side of their start marks, laid out as while reframing) are wider together
  than the frame (`reframe_needed`). A video variant can turn it off (`reframe: none` merges into
  the top level; a variant cannot change one scene's params, §7).
- **The landscape stage** (`cartoon/reframe.py`, no manim): `stage_base_width(frame_width,
  frame_height, reframing)` is the width of a `width: 1` stage: the frame's, or while reframing
  `max(frame width, 16/9 × short side)` (`LANDSCAPE_ASPECT`). In 9:16 (8 × 14.22) a reframing
  stage is 14.22 units per `width`, as in 16:9, so marks, sizes (the short side, §69.6) and walk
  lengths match the landscape video and the frame crops it. `Stage.stage_width` and
  `stage_frame` use it; 16:9 frames are unchanged. Without reframing, a 9:16 stage is squeezed
  into the frame as before (§69.6).
- **The path** (`reframe_path(beats, frame_width=, bounds=, start_x=) -> [CameraMove(beat, x,
  seconds)]`, pure): `ReframeBeat(id, speakers, seconds, figures, camera, camera_x, bubble)` with
  `ReframeFigure(name, x, half_width, facing, start_x)` (where it ends the beat's written moves,
  and where it started when it moved). The camera's centre starts at `start_x` (clamped in
  `bounds`). Per beat: a written `pan` sets it (`camera_x`, `None` when not known: then nothing
  until a known pan), a `follow` makes it unknown, `held` (a `zoom` or a `shot` with a kind)
  changes nothing (the view comes back); in a `free` beat the first speaker on stage with a line
  of at least `REPLY_HOLD_SECONDS` 1.5 s (a shorter reply holds the view) that is not wholly in
  view (`CUT_TOLERANCE` 0.02 of its width) moves the camera to `_view_for`: the speaker's span
  (start and end of a walk, else its end box), `REFRAME_LOOK_ROOM` 0.1 of the view in front of
  its face, then the nearest centre inside the stage that shows it wholly and puts no view edge
  inside another figure (candidates: that ideal and the centres whose edge sits at a figure's
  tolerance; none: the ideal kept in range). The move eases `REFRAME_SECONDS` 1.0 (at most 0.8
  of the shortest line that moves it), or is a cut (`seconds` 0) in the first beat and in a beat
  whose `say` draws a bubble (built for the view at its start). Before the first line, the first
  beat cuts to the scene's first speaker (before any written camera move) when the start view
  does not show it.
- **Planner** (`cartoon/directing.py`): `plan_reframe(cast, beats, stage)` replays the written
  actions with the planner's state (`_start_state`, `_follow_written`: enters, exits, walks,
  pans, follows; `CAMERA_ACTIONS` = pan, follow, zoom, shot) into `ReframeBeat`s and turns each
  move into an automatic `pan` with `to` (the stage fraction, 4 decimals) and `run_time`, or
  `cut: true`. `stage_directions(..., reframe=)` reads every speaking beat's length when
  reframing, puts the pans first in their beats' `DirectedBeat`s and gives them to
  `plan_directions` as written actions (so automatic close-ups avoid their beats and the lint
  checks see the camera); `Stage.auto_actions` passes `stage_reframes`. The pans are ordinary
  automatic actions: `vidgen direct` / `--print`, the storyboard's `auto:` line (`auto_label`
  writes a true flag by its name: `pan 0.3062 cut`), and pasted they count as written.
- **`pan` `cut`** (§69.7): `cut: true` moves the camera frame at once in `apply` (no animation,
  `run_time_for` 0), as a shot's cut does (§69.29). **Runner**: in a batch of actions due
  together, camera moves now come first (they start at their `at`; before, a camera move listed
  after two actions on one character joined the second's batch), then the others, then
  `after_camera` actions.
- **Checked**: a scratch copy of `examples/cartoon` with a 9:16 variant (`vidgen storyboard` and
  `vidgen lint --variant vertical`): the yard scene (dot and moss at `left` / `right`, 7.1 units
  apart in a frame 8 wide) cuts to dot at the start, eases to moss and back, follows dot's walk,
  cuts to moss for his bubble and leaves the written zoom alone; the hill (both start within one
  view) does not reframe. Lint: 1 warning, `off_stage` in hill_count, from the written `follow`
  of the kite (present without this step too), so the variant is not added to the example.
- **Not done here**: the camera moves only in x (no zoom to the speaker in a tall frame, where
  the characters stay small); a walk that does not speak is not followed; the entering side of an
  `enter` is predicted from the written camera only; props are not framed. Tests:
  `tests/test_cartoon_reframe.py`.

### 69.31 Lighting and mood (Step 97)

A `stage` has a light (`light:` param, the `light` beat action) and soft shadows on the ground
(`shadows:` param, on by default).

- **The grade** (`cartoon/lighting.py`, no manim): `LightGrade(multiply, glow, stars, shadow)`;
  a colour channel `c` becomes `clip(c * multiply + glow, 0, 1)`, alpha unchanged
  (`grade_rgbas` for Manim's RGBA rows, `grade_pixels` for 8-bit pictures). `tint_grade(tint,
  strength)`: `multiply = 1 - strength * (1 - tint)` per channel. Presets (`PRESET_LIGHTS`,
  `LIGHT_PRESETS`): `day` (no change), `morning` (`#FFE4CC` 0.3 + a small warm glow, shadows
  0.8), `sunset` (`#FF8A5C` 0.55 + a warm glow, so a blue sky turns warm instead of grey; shadows
  0.9), `night` (`#2A3C78` 0.72, stars 1, shadows 0.45), `indoor` (`#E6BC7E` 0.4, shadows 0.75).
  `{tint, strength}` (`CustomLight`, default strength 0.5) has no glow, no stars, shadows 1.
  `blend_grades` mixes every field linearly (exactly the ends at 0 and 1).
- **Fades**: `LightChange(start, seconds, grade)`; `light_at(base, changes, now)` applies the
  changes in start order, each from the light at its own start (so one that starts during
  another continues from where that one is), eased with smoothstep. `light_changing(changes,
  start, end)`: whether any change is under way in a window.
- **Drawing** (`cartoon/shading.py`): the grade is applied as Manim draws, not to the mobjects'
  colours. `StageLight(camera, base)` wraps the scene camera's `get_fill_rgbas`,
  `get_stroke_rgbas` and `display_image_mobject` (Cairo camera; same names in Manim 0.21 and
  0.22): a mobject with the `light_graded` attribute (`mark_lit`, set on every family member of
  the backdrop, the layers, the props and the characters) is drawn graded; a picture's pixel
  array is graded while it is drawn and put back. Nothing is recoloured, so `dim`, `highlight`,
  expressions and lip sync keep working, and what the stage does not mark (speech bubbles,
  callouts, particles, captions, text) keeps the theme's colours and contrast. A stage whose
  light is `day` and that has no `light` action installs nothing (renders as before, apart from
  the shadows). A lit stage without a picture or `background` gets a `background` rectangle in
  the theme's background colour, so the sky is graded too.
- **The `light` action** (`scenes/light_action.py`): `- light: night` or `tint` + `strength`;
  `animates = False`, so the runner cues it at its `at` (`cue`) and it never stretches a batch of
  other actions; `run_time` (default `LIGHT_FADE_SECONDS` 2) is the fade; not reversible (a later
  `light` action changes it again); `scene_problems` refuses scene types without
  `change_light`. `Stage.change_light(setting, start, seconds)` adds the change and a scene
  updater (`_light_step`, kept as `_light_updater`: Manim removes an updater by identity and
  each `self._light_step` is a new bound method) that sets the grade for the scene time on every
  frame and removes itself once every change is over (Step 99; before, the removal in
  `get_moving_mobjects` never matched and ran only when a new animation started); while it is
  installed a wait is not frozen. **Static image** (§69.20): `Stage.get_moving_mobjects` updates
  the light first, returns every mobject while a change falls in the animation's time
  (`self.duration`; unknown: until the changes are over), otherwise Manim's moving mobjects, so
  the set stays in the static image before and after a fade. Measured on a scratch copy of `examples/cartoon`: `yard` storyboard at
  preview 12.5–13.1 s with `day` (HEAD 12.3–13.0 s), 13.4 s with `night` (the grading of every
  lit shape on every frame drawn).
- **Stars**: when the starting light or any `light` action has stars and the stage has no
  picture, `night_stars(area_share, seed, preview)` draws positions, sizes and brightness from
  the `sparkles` particles' seeded stream (`particle_seeds`; `STAR_DENSITY` 1.0 of their count,
  half at preview; `STAR_SIZE` 0.7 of their size; brightness from each seed's speed) and
  `StarField` builds them with the sparkle's shape (`particle_field.particle_shape("star")`) in
  `STAR_COLOR` over the top `STAR_SKY` 0.75 of the sky above the ground band (since Step 102 ending
  `STAR_HEAD_ROOM` 0.04 of the frame height above the highest character's head at the start), right after the
  sky in the backdrop (behind the layers and the props). They do not twinkle (a moving field
  behind the set would take the whole set out of the static image); `set_level(grade.stars)`
  fades them with the light. Not graded.
- **Shadows**: `shadow_ellipse(x, ground_y, width, above=, size=, strength=)`: on the ground
  line of the caster's depth, `SHADOW_FLATNESS` 0.16 as high as wide, opacity `SHADOW_OPACITY`
  0.3 × the light's `shadow`; `above` the ground the shadow shrinks and fades by `1 / (1 +
  SHADOW_SHRINK (1.5) × above / size)`. Widths: `SHADOW_WIDTH` 0.55 of a character's standing
  height, `PROP_SHADOW_WIDTH` 0.9 of a prop's width, so depth scales them with their caster.
  `Shadow` is three ellipses in the characters' ink (`SHADOW_RINGS`, darker inside: soft
  edges). `ShadowCaster(mobject, ground, width, size)` reads `feet()`; a prop with `held_by` set
  casts none. `Stage._shadows` splits the casters: props on the ground that no action can move
  form one `StageShadows` in the backdrop (after the ground band, static); characters and the
  props a `pick_up` / `hold` names or `keyframes` / `move_along` targets form another, with an
  updater (`follow`), faded in just before the first of them in the reveal, so the back of the
  set stays in the static image. Props with a `lift` (cloud, sun, moon) cast none. The layout
  dump leaves `StageShadows` and `StarField` out (`introspect`), so lint never sees them.
- **Checked by eye** on scratch copies of `examples/cartoon` with each preset on both stages
  (storyboards at preview), and the hill scene fading `sunset` then `night` (3 s, with
  confetti): the bubble stays white with dark text, stars show in the night sky behind the cloud
  and hills, the jump's shadow shrinks under dot, the kite's shadow leaves with it. `vidgen lint`
  on the night and the fading copies: 0 findings (the `contrast` rule included).
- **Not done here**: stars do not twinkle and are not drawn over a picture background
  (`generate:` / `image`: the sky is unknown); particles are not graded; shadows do not stretch
  with a low sun; a held prop's shadow is not under its holder's (the holder's covers it).
  Tests: `tests/test_cartoon_lighting.py`. Since Step 98 `light_at` / `light_changing` are
  `fade_at` / `changing` (any change with `start`, `seconds`, `end`, `value`), shared with the wind.

### 69.32 Wind (Step 98)

A `stage` has a wind (`wind:` param, the `wind` beat action): props sway, characters' trailing
pieces follow it on a spring, particles drift.

- **Levels and gusts** (`cartoon/wind.py`, no manim): a level is signed, `0` calm, `1` a gale
  blowing right (`+x` on screen), `-1` left; `wind_level` reads a number (also as text) or
  `WIND_LEVELS` (`calm` 0, `breeze` 0.3, `windy` 0.6, `gale` 1). `gust(t, seed)` is smooth value
  noise in 0..1: two octaves (`GUST_OCTAVES`: knots 2.6 s apart weight 0.65, 0.85 s weight 0.35),
  knot values from splitmix64 of (seed, octave, knot) (pure integers: the same on every
  platform, cached), eased between knots with a quintic. `Wind(base, seed, changes)`: `level(t)`
  fades through `WindChange(start, seconds, value)` with the light's `fade_at` (smoothstep, a
  change during another continues from where it is); `force(t, delay) = level ×
  (STEADY_SHARE 0.5 + 0.5 × gust(t − delay))`; `delay(x_share, t)` = `GUST_CROSSING_SECONDS` 1.2
  × the distance from the upwind edge (gusts cross the stage); `blown(start, t)` adds the force
  up with trapezoids `BLOWN_STEP` 0.05 s apart from 0 (cached; the same whatever order frames are
  asked in). The scene's seed is `wind_seed(scene id)` (the idle motion's name hash).
- **Sway** (Step 104 changed the numbers and added `felt_force`, §69.38): `SWAYS` (tree 5° at force 1, 0.45 Hz, straight up to 0.08 of its height; bush 4°;
  plant 9°, from 0.45 (above the pot); sign 1.5°; lamp 1.2°); `sway_degrees(kind, force, t,
  phase) = degrees × force × (1 + SWAY_WOBBLE 0.25 × sin(2π hz t + phase))`, phase from the
  prop's name (`wind_phase`). `bent_points(points, degrees, foot_y, height, bend_from)` moves
  each point sideways by `tan(degrees) × bending length × u²` (`u` the share of the height above
  `bend_from`): the base stays, the top leans; `y` is kept. Exactly the rest points at 0°.
- **Trailing pieces**: the generator marks members of a shape with `TRAIL_ATTRIBUTE`
  (`wind_trail` = pivot x, pivot y, weight; scaled with the figure): the scarf's end (weight
  1.2, pivot its top), long hair (0.55, above the head's middle), a bun (0.35, its bottom),
  pointy ears (0.35, their base), floppy ears (1.0, their top), the hat's crown, band and brim
  (0.3, the brim's middle) (`TRAIL_WEIGHTS`). Hair and ears are drawn inside the `head` part
  and the scarf inside `body`, so trailing is per member inside a part, not a new part: the part
  set, poses, sheets, SVG ids and the look cache are unchanged. `Character` finds them once
  (`_trailing_members`; sign + for a piece hanging below its pivot, − for one standing above it,
  so a positive turn always moves its free end right as drawn facing right) and
  `set_wind(degrees)` turns each by `degrees × weight` about its pivot after its part's matrix,
  mirrored for `facing: left`, on top of the poses (not in `state()`); at 0 `refresh` takes the
  old path. `trail_degrees(wind, t, delay, phase) = TRAIL_DEGREES 24 × TRAIL_SPRING.follow(force)
  + FLUTTER_DEGREES 4 × level × sin(2π 2.5 t + phase)`, `TRAIL_SPRING = Spring.tuned(1.2 Hz,
  ζ 0.3)` (Step 82: it lags a gust and swings past it); exactly 0 once the force has been 0 for
  `Spring.memory_seconds` (6 decay times, 2.65 s). Imported SVG characters have no marks.
- **Particles** (`particles.py`): `WIND_DRIFT` per kind (shorter sides per second at force 1;
  dust 0.4, snow 0.35, rain / confetti 0.3, smoke 0.25, bubbles 0.2, sparkles 0.08);
  `particle_states(..., blown, wind)` shifts each particle by drift × |speed| × blown and slants
  rain by `atan2(drift + WIND_DRIFT × wind, fall)`; 0 adds nothing. `ParticleField(wind=)` reads
  `(blown since it started, force now)`; `particle_field` passes the scene's `particle_wind`.
- **Stage** (`windblown.py`, `scenes/stage.py`): `_start_wind` installs nothing when the param
  and every `wind` action are 0 (`blowing` and `particle_wind` stay `None`: proved by frame
  hashes, below). Otherwise `StageWind(wind, props, cast, x_share)`: the swaying props are
  built-in `SWAYS` kinds on the ground that no action moves, holds (`_movable_props`), sits on or
  leans on (`_posture_props`), each a `SwayingProp` keeping its rest points; characters with
  trailing pieces. A scene updater (kept in `_wind_updater`: Manim removes updaters by identity)
  calls `update(t)` each frame after the animations; `refresh` is anchor-based, so turning
  trailing pieces during a walk or pose change is consistent. **Static image** (§69.20, cost
  asked for): `get_moving_mobjects` returns, while `moving(now − spring memory, end)`, the scene's
  family from the first swaying prop or trailing character on (the sky, layers, ground band,
  still shadows and props behind stay static); otherwise Manim's set, and the updater is removed
  once nothing can move again (since Step 100 also by `_wind_step` itself, on that frame, so a
  calm that starts inside a long wait does not keep Manim redrawing every frame). Measured (854x480, 15 fps, no audio, 2 runs each, a scratch copy
  of `examples/cartoon`): `yard` 11.5 / 10.9 s → 12.8 / 12.8 s with `wind: windy` (+13 %, the
  tree and everything in front of it redrawn); `hill` 13.2 / 12.9 s → 13.8 / 14.3 s with `gale`
  (+7 %). `trail_degrees` costs about 0.4 ms per character per frame.
- **The `wind` action** (`scenes/wind_action.py`): `- wind: 0.8` / `calm` / `breeze` / `windy`
  / `gale`; like `light`: `animates = False`, cued at its `at`, `run_time` the fade
  (`WIND_FADE_SECONDS` 2), `scene_problems` refuses scenes without `change_wind`; validate:
  none, several, unknown name (did-you-mean), out of range. `number_target = True`: the YAML
  number is kept as text by `ActionConfig` (a `before` validator on `target`) and the schema's
  shorthand accepts a number.
- **`wind: 0` changes nothing**: a scratch copy of `examples/cartoon` with `wind: 0` on both
  stages rendered at 160x90, 5 fps on this step's code gives the same frame hashes as the
  unchanged copy on HEAD 868914f (`yard` 147 frames, `hill` 127); `tests/test_cartoon_wind.py`
  checks `wind: 0` plus a `- wind: calm` action against no wind frame by frame.
- **Not done here**: wind relative to a walking character (walking into it), wind on held props,
  SVG props or picture backgrounds, layers swaying, a `wind` setting at the top level, leaves
  blowing as particles of their own (Step 104 adds `leaves` and a held prop blowing away, §69.38). The light's updater, found never removed here, is fixed in
  Step 99 (§69.31). Tests: `tests/test_cartoon_wind.py`.

### 69.33 Non-speech voice sounds (Step 99)

A beat's text may hold `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]` (any case,
an `s` allowed: `[laughs]`): sounds of its speaker at that point (CONFIG "Voice sounds").

- **One place for the markers** (`voicesounds.py`, no manim): `BeatConfig`'s after-validator
  calls `take_out_sounds` (`SOUND_MARKER`, the spaces before a marker go with it, a word glued
  to it gets a space) before `strip_emphasis`: `text` is the plain line, `marked_text` keeps the
  `*word*` marks (the same words, so the gesture planner's word count holds), `voice_sounds` the
  `VoiceSound(kind, word)` list, `word` = how many words of `text` come before it (independent
  of the asterisks). Everything that reads `beat.text` (captions, SRT, bubbles, slides, lint,
  readback's written side) never sees a marker; a text of markers only is a config error. Other
  brackets stay in the text. `model_copy` keeps the private attributes (automatic actions copy
  beats).
- **What the TTS gets**: `Project.spoken(beat)` = `pronunciation.apply(beat.text)` (the rules
  see the written words only), then `voiced_spoken`, which inserts what the beat's voice says
  for each sound (`sound_voicing`) after its word with `Spoken.inserted` (zero-length
  `Replacement`s: the said words belong to no written word in `word_groups`, so
  `map_word_times` times the written words around them). `spoken_texts` (the audio hash, the
  dry run, `context_texts`, lint's speed, `vidgen tts`) is built from it. A beat without
  markers is unchanged (pinned cache keys in `tests/test_voice_sounds.py`).
- **Per provider** (`VOICE_SOUNDS`): ElevenLabs models starting `eleven_v3` read audio tags
  (`[laughs]`, `[gasps]`, `[sighs]`, `[giggles]`, `[groans]`; `hmm` is said `Hmm.`). Every other
  voice (Kokoro, other ElevenLabs models, OpenRouter's models) says `Ha ha ha!`, `Hee hee!`,
  `Hmm.`, `Ugh.`; `gasp` / `sigh` at the line's first or last position are the built-in
  generated `gasp` / `sigh` sounds (`sfx.py`, breath noise through formant bands, plus a falling
  hum for the sigh), not in the text, so the beat's audio and hash stay as without the marker;
  inside a line they are said `Hah!` / `Haah.` (the speech leaves no silence: Kokoro makes a
  0.05 s pause for `…` and 0.11 s for `...`, measured). Real Kokoro (`af_heart`, Step 99): `Ha ha
  ha!` 0.73 s, `Hee hee!` 0.43 s, `Hmm.` 0.28 s, `Ugh.` 0.33 s, `Hah!` 0.23 s; with timings, so
  the alignment holds the sound and the mouth follows it (`Hmm` -> `M`).
- **When** (`sound_spans`, `beat_sound_spans`): from the written words' times (the caption
  path: alignment of the spoken text, else the estimate over the spoken words, which weighs the
  sound's words and pauses): a said sound spans the gap between its words (from 0 / to the
  beat's end at the edges); a generated one ends `SOUND_GAP` (0.05 s) before the first word or
  starts that long after the last, its built-in length long (the gasp may start before the beat,
  in the previous beat's pad; clamped to the scene's start).
- **Generated sounds** are recorded by `NarratedScene.narrate` (any scene type) as sound effects
  of the beat at `SOUND_GAIN_DB` (+6 dB: built-ins sit −27 LUFS, about 7 dB under the voice; a
  breath belongs to it), so `assets/sfx/gasp.wav` replaces one like any built-in.
- **Mouth**: said sounds are in the viseme track (stored or built from the spoken text).
  `beat_visemes` lays the generated ones over it with `with_cues` (`gasp` `O`, `sigh` `A`;
  before 0 cut off, past the end with `rest` before it), at read time, so stored
  `.visemes.json` files are unchanged.
- **Face**: `directing.sound_reactions` (run first by `stage_directions`, whatever
  `auto_direct` says; `directing_used` is true for a stage with sounds) adds per beat an
  automatic `react` with the expression of its first sound (`laugh` / `giggle` happy, `gasp`
  surprised, `sigh` sad, `hmm` thinking, `groan` worried) at the sound's start as a share of the
  beat (at most `REACTION_AT`), for each speaker (`say` targets, else the voice's characters)
  that can emote and that no written `emote` / `react` (`FACE_ACTIONS`) acts on. The planner
  then sees it as written, so it adds no gesture or reaction for that speaker in that line.
  `vidgen direct` lists it (pasting it makes it written; the automatic one then goes away).
- **Captions, SRT, readback**: `captions` and `write_srt` (`spoken=` per beat, from the
  pipeline) time the written words with `Project.spoken`; `directing._beat_words` too for a beat
  with sounds. `readback` compares with the line without sounds and `compare_beat(...,
  skip_heard=)` drops heard tokens in `heard_sound_words` that the line does not say.
- **Screenplay** (§69.25): inside a line, a bracket whose content `is_voice_sound` stays in the
  line's text; every other `[...]` is a direction. On its own line a `[laugh]` stays a direction
  (no verb matches: a `# TODO:`). A line of sounds only is an error naming its line.
- **Fingerprint**: a scene with sounds adds `voice_sounds` (beat -> `[kind, word]`), since a
  generated sound changes the SFX, the mouth and the face but not the text or audio.
- **Not done here**: one face per beat (the first sound's); a sound marker on a line of its own
  (a beat needs words); no panning; the `[gasp]` foley `pop` of a `surprised` react plays with
  the gasp; ElevenLabs v3 tags and OpenRouter models were not tried against the real services
  (no API calls), and how a given OpenRouter model says `Ha ha ha!` is unknown.
  Tests: `tests/test_voice_sounds.py`.

### 69.34 Overlapping speech and interruptions (Step 100)

A beat's `overlap: S` starts it `S` seconds before the speech of the beat before it ends;
`interrupt: true` cuts that line where the beat starts (CONFIG "Overlapping lines").

- **Only within a scene**: `SceneConfig` refuses the keys on a scene's first beat, so a scene's
  start, end and length rules (transitions §49, carry §50, chapters §52) are unchanged; scenes
  only get shorter. `BeatConfig` refuses `interrupt` with `overlap: 0` (cuts nothing); `overlap`
  is `>= 0`. `vidgen validate` warns about an overlap of a line of the same voice
  (`overlap.overlap_warnings`).
- **The timeline** (`overlap.py`, no manim): `beat_lines` builds a `SpokenLine(seconds,
  speech_end, overlap, interrupt)` per beat; the speech end (`speech_bounds` of the MP3, the
  trailing silence cut off; `d` without audio) is read only for a beat the next one joins.
  `beat_windows(lines, pad, fps)` gives each beat a `BeatWindow(body, rest, heard, shape)`: not
  joined, `(d, pad, d, plain)`, so `window = d + pad` is the same float expression as before;
  joined, `body = max(speech_end - lead, MIN_WINDOW)` in whole frames (with `fps`, so the cut
  lands where the next beat really starts), `rest = 0`, `heard = d` (overlap; `VoiceShape(dip_from
  = body)`) or `body` (interrupt; `VoiceShape(cut = body)`), and `next_lead = speech_end - body`.
  The lead (`SpokenLine.lead_after(earlier)`) is `overlap`; for an interrupt without `overlap`,
  inside the earlier line's last word: `speech_end - (start + INTERRUPT_WORD_SHARE 0.7 *
  length)` of that word (`SpokenLine.last_word`, read by `beat_last_word` from the stored
  alignment of what the TTS said, `speech.stored_word_times`, only for a beat an interrupt
  without overlap follows), so at most its last 30% is cut; without a stored alignment
  `INTERRUPT_LEAD` (0.2 s; it was a fixed 0.5 s, which cut the whole word "normal" of a Kokoro
  line in the Phase I showcase). `NarratedScene.beat_window` and `VideoPlan` call the
  same function, so the plan and the render agree; `narrate` yields `body`, gives the action
  runner `(body, rest)`, waits to `window`, records `end = start + heard`, captures `window`
  worth of frames, puts an `end` sting at `heard` and drops a generated voice sound after a cut.
- **The mix plan**: `VoiceShape.gain(seconds)` (raised-cosine `DIP_RAMP` 0.1 s to
  `-OVERLAP_DIP_DB` 3 dB; fade to 0 over `INTERRUPT_FADE` 0.05 s from the cut) and
  `shape_voice(samples, rate, shape)` (also drops what follows the fade). `add_narration` shapes
  the beat's decoded WAV before Manim adds it, at the beat's start as before; a plain shape is
  not applied at all (the pinned test compares every WAV Manim gets with the plain decode). The
  shape is for the planned start of the next beat: a custom scene that plays between two
  `narrate` blocks starts the next beat later than the cut. Music ducking and sting ducking read
  the beats' `start` / `end`, so they cover both voices.
- **Mouths** (§69.11): `NarratedScene.end_lip_sync(character, track)` stops a beat's lip sync
  now, or, while the voice of the beat just narrated still sounds (`_voice_until`), keeps it in
  `_lingering` until the next `narrate` ends; `Stage.narrate` and `Say.revert` call it. The track
  past its end shows `rest`; `beat_visemes` of an interrupted beat is `VisemeTrack.until(cut)`,
  and as `heard` ends at the cut, the mouth is stopped there.
- **Captions**: `cues.overlapping_beats(spans)` (beats whose narrations intersect) get
  one-line cues; `cues.stack_cues([(beat, cue)])` cuts the cues' timeline at every start / end
  and shows the cues sounding at once (at most `MAX_STACK` 2, earlier beat on top). Without
  overlaps it gives one stack per cue with its own times (the overlay draws the same mobjects).
  The `captions` overlay draws a stack as one caption: lines of both cues on one plate, each in
  its speaker's colour, tags as before; karaoke highlights the current word of each part (state
  `(caption, (word, ...))`). The last cue of an overlapped beat lasts to its own end (`until =
  max(next start, end)`). The SRT (`cues_from_timings`) uses one-line cues for overlapping beats
  and lets their cues overlap in time (sorted by start); players stack them.
- **Directing** (§69.23-24, §69.33): `BeatInput.next_joins`; `stage_directions` gives a joined
  beat `seconds = body` and only the words that end before it, and the reactions pass adds no
  listener reaction after it (no pause). A voice-sound face after the cut is left out.
- **Lint**: the activity file's beats get `window` (joined) and `overlap` / `interrupt` (the
  joining beat; for an interrupt without `overlap`, `overlap` is the lead used, the earlier
  beat's `next_lead`); `animation_overrun` measures against `window`; the new rule `talked_over` (scene
  scope, default warning, `TalkedOverRule` without settings) reports words of the earlier line
  (`beat_word_times`) spoken entirely after the overlapping beat's speech starts (`talked_over`),
  with the largest overlap that keeps them clear. For an interrupt (`_cut_words`, a line with an
  MP3 only) it reports the words that start at or after the cut (the beat's `end`), timed over
  the whole MP3, with the overlap below which they would be heard.
- **Fingerprint**: the beat keys are left out of the scene's config dump while unset and added
  as `joins` when set (scene, overlay inputs, the next transition's scene), so renders made
  before Step 100 stay valid.
- **Unchanged**: `timings.json` keys (the interrupted beat's `end` is the cut, an overlapped
  beat's `end` passes the next `start`; consumers that took the last beat's `end` as the scene's
  speech end now take the latest end), readback (it transcribes the whole MP3), the MP3s and
  their hashes, the screenplay format (no syntax for overlaps yet).
- **Not done here**: no screenplay syntax; no per-beat dip or fade settings; no overlap across
  scenes. Tests: `tests/test_overlap.py`, `tests/test_overlap_pinned.py`.

### 69.35 Shared casts and sets (Step 101)

A series keeps its characters, voices and places in files every episode includes
(CONFIG "Shared casts and sets").

- **Loading** (`includes.py`, no manim): `Project._load` calls `read_project_config(config_file,
  confine)`, which reads the `include:` tree depth first (paths relative to the including file; a
  file reached twice merged once, where first reached) and merges the files in that order, then the
  project's own mapping: `merge_config` merges mappings key by key, `characters` entries by name
  (a later entry's keys win; new names are added), anything else replaces. Only `include`,
  `characters`, `voices` and `sets` may be in an included file. File paths in it (`look.svg`, a
  set's `image`, `layers[].image`, `props[].svg`) are rewritten relative to the project and
  collected (`ConfigSource.named_files`). Missing, unreadable, circular, non-YAML or (under `vidgen
  mcp`) outside-the-root includes raise a `VidgenError` naming the chain of files, with a problem
  at `include[k]` of the file that names it. Variants keep `deep_merge` (lists replace) and may not
  contain `include`. `VideoConfig.include` / `sets` and `SceneConfig.set` are model fields (schema,
  docs); `include` is read only by the loader.
- **Sets**: `expand_sets` applies each scene's `set:` before validation (`apply_set`), so the
  stage's `Params` never sees it: `image` / `generate` / `background` are one choice (a scene
  giving one drops the set's three), mappings merge, `characters` / `props` / `layers` /
  `particles` combine (set first; a scene entry named like a set entry, by explicit name for the
  scene and own-or-default name for the set, `numbered_names`, changes it; `[]` clears), the rest
  replaces. Chosen over replacing lists because a set is furniture a scene adds to; the
  explicit-name rule keeps an unnamed `tree` in a scene a second tree. An unknown set is a config
  problem (`set_reference_problems`, did-you-mean). Unused sets are not validated on their own.
- **Where problems are written**: the loader records `Origin(file, location)` for every location
  an included file, a set or a merge moved (`ConfigSource.origins`, `Project.origins`; empty
  without includes or sets). `attributed(problems, origins)` takes the longest recorded prefix of
  a problem's location and rewrites it: a set's value -> `sets.NAME...` in its file (dropping the
  repeats from other scenes using the set), a character merged by name -> its own index in its
  file, an appended scene entry -> its index in the scene. `Project._load` applies it to config
  errors (the message is rebuilt from the problems), `cli.project_problems` to its result.
  `Problem.file` (JSON `file`) names the included file, `None` for the project's config file;
  `str()` shows `location (in FILE): message`. YAML line numbers are not kept (`yaml.safe_load`).
  Warnings (strings) are not attributed.
- **Caches**: the merged config is what renders, TTS hashes and imagegen keys see. The scene
  fingerprint leaves `include`, `sets` and the scene's `set` out of its config dumps (the expanded
  params carry what a set gives, so an unused set changes nothing and old renders stay valid),
  and adds `included_files` (stats of `named_files` outside `assets/`) when there are any.
- **`vidgen validate`** prints `included:`; `--json` gains `included` (absolute paths).
- **`vidgen screenplay --cast FILE`** (MCP `cast`): `read_include_file` reads the cast with its
  includes; `screenplay_project(play, title, cast, include)` writes `include: [<path from the
  project>]`, treats the cast's characters as declared (their voices kept, not written into the
  project), and `parse_set(text, names, sets)` reads a first part naming a cast set as `set:` (no
  default sky; the set's marks, props and character places count for placing and directions;
  characters the set already places at the same spot are not written again).
- **Example**: `examples/cartoon_series/` (`shared/cast.yaml`, `shared/sets.yaml`, `episode_1`,
  `episode_2`), both episodes validate and lint clean at preview. Tests: `tests/test_includes.py`.

### 69.36 Review of Phase I (Step 102)

- **End to end**: `examples/screenplay` (`vidgen screenplay` -> project -> `validate`, `direct`,
  `storyboard`, `lint`, `character-sheet --all`, `render --preview`), `examples/cartoon` with
  `auto_direct: true` and both `examples/cartoon_series` episodes (`validate`, `direct`, `lint`,
  sheets, a storyboard, a preview render), by the CLI and by the MCP tools `screenplay` (also with
  `cast`), `validate`, `direct`, `character_sheet`, `lint`: lint clean everywhere.
  `tests/test_phase_i_review.py` repeats the cheap part and renders one 160x90 stage using the
  Phase I features together.
- **Captions over an automatically directed scene**: `overlays.scene_overlays` looked the scene up
  with `list.index(spec)`; a stage with `auto_direct` renders a copy of its `SceneConfig` with the
  automatic actions merged (§69.23), which equals no scene of the config, so any overlay on such a
  scene raised `ValueError`. It now looks the scene up by id.
- **Seats**: generated characters' hips are 0.15–0.24 of their height (big heads, short legs;
  `head_size` 1.6 to 0.6), the SVG examples' 0.19–0.23, but the built-in seats were at 0.27
  (chair, box) and 0.2 (rock): a seated character sat higher than it stood, its feet hanging, and
  read as standing on the prop. `PROP_HEIGHTS` now makes `chair` 0.26 (seat 0.14), `box` 0.155 and
  `rock` 0.155 (seats 0.14), below every generated look's hips, and `Character.seated` puts the
  hips (`_hips_y`: the pivot of the first leg part) on the seat line, the body's bottom sinking a
  little in front of the seat, so the knees bend and the soles reach the ground. Tested for every
  body and head size and the SVG examples. A box or rock is drawn smaller than before everywhere
  (`examples/cartoon`'s box, the series' crate).
- **Stars**: the night's stars stopped `STAR_SKY` of the sky above the ground, which is beside
  the characters' heads; the stage now builds its backdrop after the layout and ends the stars
  `STAR_HEAD_ROOM` 0.04 of the frame height above the highest character's head at the start (a
  jump or a close-up can still bring a head among them).
- **`vidgen mcp` confinement**: `svg` (a character's `look.svg`, a stage or set prop's `svg`)
  joins `PATH_KEYS`; a Kokoro `voice` part ending in `.pt` (Kokoro reads it from the current
  folder, which under `vidgen mcp` is the root) is checked against the project folder and the
  current folder; `read_include_file` (`screenplay --cast`) confines the cast's own includes when
  `VIDGEN_CONFINE_ROOT` is set. Files found by scanning a folder (`assets/sfx/`, `assets/icons/`,
  `audio/`) are not checked (a link there can still point outside: Backlog).
- **Unused voices of a shared cast**: `voices.voice_warnings(config, origins)` leaves out voices
  written in an included file (an episode need not use the whole cast).
- **Real narration**: a scratch copy of the screenplay project with a two-shot, a close-up, an
  overlap, an interrupt, `[gasp]` / `[laugh]`, sitting, leaning, a crate picked up and given,
  sunset fading to night, wind and captions; Kokoro at speed 0.75 / 0.8 (`narration_speed` warned
  at 0.85), lint clean, rendered at 1280x720 (`/home/claude/work/phase-i-review/showcase.mp4`,
  57.6 s). Not transcribed (the owner skipped the Whisper check).

### 69.37 Props: basket, umbrella, napkin (Step 103)

Three built-in props for Phase J's picnic in the rain, and the two things the umbrella needs: a
prop with more than one shape, and a prop held somewhere other than its middle.

- **Drawings** (`cartoon/props.py`, primitives and theme colours like §69.8): `basket` (0.2 of a
  character; `secondary` wicker with weave lines, an `accent` cloth peeking out, an arched
  handle), `umbrella` (0.6; `primary` canopy with lighter panels and ribs, `dim` wooden shaft
  and hook), `napkin` (0.05; a light cloth `#F4F6FA` lying flat with `accent` checks and a
  turned-up corner; small, for Step 104's wind to blow away). Both umbrella shapes are one prop
  unit tall (tip or hook at 0, the top at 1), so a swap keeps its height; closed it stands on its
  tip with the hook up, open it stands on its hook with the canopy up.
- **Shapes** (`PROP_SHAPES = {"umbrella": ("closed", "open")}`): a drawer returns a dict of shapes
  instead of a list; `Prop(shapes=...)` adds each shape as a group and shows the first. Like a
  character's part shapes (§69.22) every shape stays in the family for the prop's life: a hidden
  shape's members have no points, and `Prop.show_shape(name)` hides the shown one and draws the
  other from its points in prop units (recorded at construction) through an invisible anchor
  triangle (`character.anchor_mobject` / `anchor_placement`, now shared with `Character`; the
  affine helper is `apply_matrix`) that moves, scales and mirrors with the prop, so the new shape
  appears where the old one was, at its size and facing, whatever moved it since (a `PropMove`, a
  hand's updater, a throw). `Prop.shape` (`None` for one shape), `shapes`, `shape_width(shape)`.
  `draw_prop(..., shape=)` draws another shape first; `StageProp.open: true` passes `shape="open"`
  (only for props with an `open` shape; else a config error).
- **Grips** (`PROP_GRIPS`, prop units per (kind, shape)): where a hand holds a prop:
  `("basket", None)` the top of its handle (it hangs below the hand), `("umbrella", "open")` the
  shaft just above the hook; others (a closed umbrella, every other prop) by their middle.
  `Prop.grip_point()` maps it through the anchor (the middle without one). Every hand use goes
  through it: the follow updater keeps the grip at `hand_point` (was the middle), `PropMove`
  moves and scales the prop about its grip (`_standing_grip` gives the grip's spot on the ground
  for `put_down` / `throw`), `pick_up` reaches for the grip when there is one (else the top).
  `Prop.feet()` of a prop with an anchor is the bottom edge below the anchor's origin (the tip or
  hook), the same for each shape, so opening on the ground does not slide it sideways.
- **Overhead** (`cartoon/holding.py`): an `OVERHEAD_PROPS` prop (an umbrella; §69.56) showing an `OVERHEAD_SHAPES` shape (`open`) is held
  with the hand at `overhead_point(feet, height, facing)`, `OVERHEAD_FORWARD` 0.08 heights in
  front of the feet and `OVERHEAD_HAND` 0.6 above them, and is `OVERHEAD_HEIGHT` 0.85 of the
  holder tall (`held_height(..., overhead=True)`, not capped at 0.4). Measured on every body
  (round, tall, square, bean) at head size 0.6 / 1.0 / 1.6 with a bun: the arm reaches 0.6 or
  stops at 0.53–0.57 (big heads), the canopy's rim is 1.02–1.09 heights up (the head top is 1.0)
  and it spans −0.34 to +0.50 heights about the feet (heads are at most ±0.25). A prop held
  overhead is drawn right *before* its holder in `scene.mobjects` (the shaft behind the head and
  body, the canopy above the head; the hand in front), others right after (§69.27).
- **Actions** `open` / `close` (`scenes/handling.py`, `_Reshape`; the targets are props, `0.6 s`
  `RESHAPE_SECONDS`): each target prop that has the shape and does not show it switches at
  `RESHAPE_SHARE` 0.5 (`PropReshape(prop, shape, at=, height=, follow=)` in
  `cartoon/transition.py`: shows the shape, rescales about the grip, and keeps the grip at
  `follow()` every frame, since Manim pauses the prop's own follow updater while it is
  animated). A held one: an `ArmMove` to the overhead point (open) or the hold point (close) and
  the new held height; standing: it changes where it stands. Validate (`scene_problems`): a target
  that is not a prop, or a prop without that shape (`'tree' cannot open (props that can:
  umbrella)`). No sequence check: opening an open umbrella does nothing. An open umbrella stays
  open through `pick_up`, `hold`, `give` (the receiver holds it overhead), `put_down` and `throw`.
- **Shadows**: props targeted by `open` / `close` are movable (§69.31: their shadow follows), and
  a `ShadowCaster` takes `widths` per shape, so a closing umbrella's shadow narrows.
- **Layout dump**: a prop with shapes carries `shape`.
- **Gallery**: `docs/gallery/media/props.png` shows the 20 props plus the open umbrella (and, since Step 109, the open door).
- **Not done here**: no tilt of the umbrella towards the head (it stays upright, the canopy
  centred on the hand); no opening animation in between (the shape switches at once, half-way);
  the automatic directing planner does not count `open` / `close` as moves; a closed umbrella is
  held upright by its middle; wind does not move a held umbrella (Step 104), rain does not
  stop under it (Step 105). Tests: `tests/test_cartoon_props.py`, `tests/test_cartoon_holding.py`.

### 69.38 Visible wind and props that blow away (Step 104)

Step 98's wind was barely visible (Backlog); Step 104 makes it read at `windy` and above and lets
the wind take a light prop.

- **Felt force** (`cartoon/wind.py`): `felt_force(f) = f × (1 + WIND_BOOST 2 × |f|)` (odd, 0 at 0,
  3 at force 1). `sway_degrees` uses it, and `SWAYS` grow to tree 8°, bush 6°, plant 12°, sign
  2°, lamp 1.5° (per felt force 1). `trail_degrees` feeds the felt force to the spring and the
  flutter, then limits softly: `TRAIL_LIMIT 80 × tanh(x / 80)` (a scarf streams out flat, never
  over the head). `TRAIL_WEIGHTS`: long hair 0.55 → 0.7, bun 0.35 → 0.4, hat 0.3 → 0.35. Measured
  over 30 s (seed 5; mean / max |degrees|; before → after): tree breeze 1.1 / 1.7 → 2.5 / 4.1,
  windy 2.1 / 3.3 → 6.4 / 10.9, gale 3.6 / 5.5 → 14.1 / 24.5; scarf end (weight 1.2) windy 12.5 /
  18.5 → 23.0 / 37.0, gale 20.9 / 30.9 → 46.3 / 69.4; long hair windy 5.7 / 8.5 → 15.3 / 24.7 at
  weight 0.8 (0.7 kept: at a gale the hair, turned as one piece about the head's top, swings out
  too far on the other side). Stills checked by eye at breeze, windy and gale (854x480): the tree
  bends visibly at windy and leans hard at a gale.
- **Leaves and streaks** (`particles.py`, reusing particles): `leaves` (shape `leaf`, a pointed
  lens; 28 per frame, falling slowly, tumbling like confetti, `WIND_DRIFT` 0.6, green / ochre /
  rust hex colours like snow's white) and `streaks` (the `streak` shape, `fall` 0, so the
  existing "along its fall" angle lays them along the wind; twinkling in and out; `WIND_DRIFT`
  1.6). `ParticleKind.wind_shown` (streaks 0.2): opacity × `clip((|force| − wind_shown) /
  WIND_SHOWN_RAMP 0.3, 0, 1)`, so streaks show the gusts and are never seen on a calm stage or a
  scene without a stage wind. Not automatic: the author adds `particles: [leaves, streaks]` (an
  automatic field would change the layout dump and lint of every windy stage).
- **The blown path** (pure): `gusty_progress(share, seed)` is how far along the way a prop is,
  the normalised running sum of `0.35 + gust(share × BLOW_GUSTS 6, seed)` (64 trapezoids, cached):
  monotone, surging and slowing, 0 → 1. `blown_point(share, start, end, rise=, seed=)` = x along
  by that progress, y on the straight line plus `rise × sin(π g) × (1 + 0.3 sin(2π 3 g + phase))`
  (never below the line, so a landing prop never dips under the ground), turn
  `−360 × blow_turns(dx) × g × direction + 25° wobble × sin(π g)` (whole turns, so it ends
  upright; `blow_turns` = one per 3 units, at least 1). `blow_seconds(distance, level) = 0.6 +
  distance / (3 × max(felt_force(|level|), 0.5))`, at most 6 s.
- **`blow_away`** (`scenes/handling.py`, `BlowAway`; targets are props, `to` optional): light
  props only (`LIGHT_PROPS` napkin, umbrella, ball, cup, basket, box; SVG props allowed). The end:
  `to` → its grip standing there at its standing height on its own ground line (a held prop:
  its holder's, like `put_down`); no `to` → beyond the stage edge downwind (the sign of the
  stage's level now; right when calm) by the prop's size + 0.3, `BLOW_AWAY_UP` 0.2 frame heights
  above where it started. Rise: `min(0.12 frame heights, 0.35 × distance)`; seed
  `wind_seed("<scene>:<prop>")`. It plays as `PropMove(..., path=blown_point)` (the new keyword:
  `path(u, start, end) -> (x, y, degrees)` replaces the arc) from the hand at once (`follow`,
  `leave` 0), growing back to its standing size; a held prop is dropped from the scene's
  `Holdings` (`drop`), detached (`held_by` / `hand` cleared, so the layout dump agrees) and its
  holder's arm goes back to how it was before it took the prop (`ArmMove` by `BLOW_ARM_SHARE`
  0.35). `run_time_for` from the distance and the level now. Blown props are movable
  (`_movable_props`: their shadow follows, they do not sway); `mid_still_actions` includes it;
  the directing planner counts it as a move and follows it (`Holdings.drop`, where it lands).
- **Validate**: `scene_problems`: not a prop, too heavy, a bad `to`. `holding_problems` (the
  replay): a prop someone sits or leans on; a prop blown off stage (no `to`) is *gone*: a later
  `pick_up`, `hold`, `sit_on`, `lean_on` (`.to`), `move_along`, `keyframes`, `open`, `close` or
  `blow_away` of it is reported with where it blew away; the former holder's `put_down` / `give`
  / `throw` reads "holds no prop then"; a prop blown `to` a mark lies there for later reach
  checks. `Stage._calm_blow_problems`: a `blow_away` without `to` while the stage's level (its
  `wind`, then the `wind` actions in play order) is 0.
- **`wind: 0` still changes nothing**: nothing in the calm path changed (no `StageWind`, the new
  particle kinds appended last); the Step 98 frame-hash test passes, and a scratch copy of
  `examples/cartoon` with `wind: 0` at 160x90, 5 fps gives the same frame hashes as HEAD 837eb8b
  (`yard` 147 frames, `hill` 127).
- **Not done here**: an open umbrella tugging its holder or turning inside out (optional, left
  out); hair bending rather than turning as one piece; no sound for a blown prop; leaves and
  streaks are not added automatically. Tests: `tests/test_cartoon_wind.py`.

### 69.39 Rain on the ground (Step 105)

Step 76's rain fell through the whole frame, past the ground and through an open umbrella. On a
`stage` it now ends on the ground, depth-aware, with splashes; open umbrellas and trees keep it
off; puddles may grow; and a generated rain sound bed plays under it.

- **Model** (`cartoon/rain.py`, pure numpy, Manim units of the scene, `y` up): `rain_ground(ground,
  top, frame_height, shelters)` → `RainGround(ground, front, back, frame_height, shelters)`: the
  *landing band* from `LANDING_FRONT` 0.05 frame heights in front of the ground line (never below
  the frame) up to the top of the ground area (`ground_top`, the deepest thing on the ground).
  Each drop gets a landing share (and a splash spread) once from `landing_shares(count, seed)`,
  `default_rng([seed, 105])`, a stream of its own so the drops keep Step 76's positions;
  `landing_lines` maps it into the band. `ShelterBox(left, right, top, feet)`: `covers(x, landing,
  reach)` = over it, landing at most `reach` in front of its feet (`SHELTER_REACH` 0.1 frame
  heights: a shelter up to depth ~0.4 keeps its whole column dry; at 0.05 a few drops landing in
  front of a tree's crown crossed it on screen and read as rain through it), and below its top.
  `drop_floors` = the landing line, or the highest covering shelter's top. `drop_landings(tip,
  floor, speed, slant)`: a drop whose lower tip is below its floor is not drawn (it reappears at
  the top when it wraps, as before) and splashes for `SPLASH_SECONDS` 0.3 after its tip crossed
  (age = distance below / fall speed; `back` = how far it slid along the slant since, so the
  splash stays where it landed). `splash_shapes(age, spread, scale)`: three ellipses per splash
  (a flat ring widening from 0.008 to 0.024 shorter sides and flattening to nothing; two droplets
  thrown left and right up to 0.022, radius 0.0045 shrinking to 0), scaled by the floor's depth
  (`splash_depth_scale`). Puddles: `puddle_spots(count, seed, left, right, ground, short_side)`
  (`default_rng([seed, 1105])`, rejected under a shelter, half width 0.05–0.1 shorter sides × depth
  scale, `PUDDLE_FLAT` 0.22 high), `puddle_count` = 4 per frame width, `puddle_growth(seconds)`
  eases out to full at `PUDDLE_GROW_SECONDS` 10. `prop_shelter(kind, shape, box, feet)`:
  `SHELTER_PROPS` tree (any shape) and umbrella (`open` only).
- **Drawing** (`particle_field.py`): `ParticleField` takes `ground` (a callable giving the
  `RainGround` now; `particle_field` passes the scene's `rain_ground` for kind `rain` only) and
  `seed`; with a ground it holds one more child, `splashes`, a single `VMobject` whose subpaths
  are every splash's ellipses this frame (opacity `SPLASH_OPACITY` 0.85 × the field's level),
  and multiplies each drop's alpha by "still falling". `drops` lists the particles; `ended` is
  set by its fade out. `Puddles(spots, start=, ended=, clock=)` (a `VGroup` of ellipses,
  `#7393B8` at 0.55) resize about their centres from the rain's seconds and drop their updater
  once full or once the rain ended; they hold plain functions, not the field or the scene,
  because Manim deep-copies a mobject it fades in. The layout dump leaves puddles out (like
  shadows and stars).
- **Stage** (`scenes/stage.py`): `rain_ground()` builds the shelters every frame from its props
  (box = the prop's drawn bounds now, so a held umbrella and a swaying tree carry theirs; feet =
  the holder's feet for a held one). `NarratedScene.particles_started(field, settings)` (new hook,
  nothing by default; `particle_field` calls it) on a stage keeps rain fields for the sound bed
  when foley is on (`_foley_on`: the stage's `foley`, else the video's, shared with
  `action_foley`) and lays `Puddles` (lit by the light) right after the set behind the characters
  (`_lay_on_ground`: into the backdrop while it has not come on screen, so they fade in with it;
  else into `scene.mobjects` after the ground band, before the shadows). `puddles` on another kind
  is a config error (stage param) or a validate problem (the action). Other scene types have no
  `rain_ground`: their rain is unchanged.
- **Sound bed** (`ambience.py`, `mix.py`): a stage's `timings()` adds `ambience: [{bed: rain,
  start, end}]` (scene seconds: each kept field's start to its `ended`, or the scene's end);
  `join_scenes` shifts them to video times in the combined timings. `ambience_spans` merges spans
  closer than `JOIN_GAP` 0.25 s (rain across a cut plays on). `rain_loop()`: 8 s stereo, numpy
  only, seeded by `crc32("ambience:rain")`: per channel a hiss (noise, Gaussian band 2.5 kHz σ 1.1
  octaves, high-pass 300 Hz, low-pass 9 kHz), 240 drop ticks per second (impulses, Pareto
  amplitudes capped at 3×, band 3.5 kHz) and 25 plops per second (band 900 Hz), a 2-cycle ±15 %
  swell; every filter one circular FFT, so the loop has no seam; set to `RAIN_LEVEL` −32 LUFS
  integrated (measured: −32.0, peak −14.9 dBFS, 62 % of its energy at 1–4 kHz, 31 % at 4–8 kHz).
  `plan_ambience` places it like a music cue (`AmbiencePlacement`, read by `MusicTrack`):
  raised-cosine fades `RAIN_FADE_IN` / `RAIN_FADE_OUT` 1.5 s inside the span, ducked by
  `RAIN_DUCK` (depth 5 dB, attack 0.4, release 1.0, hold 1.5; the music's default depth is 12) over
  `speech_spans`. So in a pause it sits 4 dB under the music's −28 LUFS (~11 dB under narration
  at ~−21), under speech at about −37 LUFS (~16 dB under the voice; music ducked: −40). A bed
  makes `mix_audio` write the mix (like music) but does not trigger `normalize: auto`; the `mix`
  report gains `ambience: [{bed, start, end, duck}]` when one played. Measured on a 20 s
  word-count preview (every beat counts as speech, so ducked throughout): −37.5 LUFS integrated,
  per-second −36.4 to −38.3 (the swell), −45 / −44 in the first and last second (the fades).
- **Render cost**: drops stay capped (`MAX_PARTICLES`, half at preview); the ground adds a few
  numpy operations per frame and one `VMobject`. A 20 s preview of a stage with rain at density
  1.5 (120 drops): HEAD 518e142 14.2 s, this step 14.3 s, with puddles 14.8 s (without rain:
  10.3 s).
- **Checked by eye**: a scratch stage (854x480) with a held open umbrella, a tree at depth 0.3, a
  bush, wind `breeze`, rain 1.5 with puddles: the umbrella's and the tree's columns stay dry, the
  splashes read as small light marks on the ground band, puddles sit on the ground under the
  characters, the rain still falls on the character before the umbrella opens.
- **Not done here**: drops are drawn in front of everything (Step 76), so a drop landing behind a
  character still crosses it on screen; no rain on other props (a house's roof, a table); puddles
  do not reflect or ripple; the bed has one intensity (no light / heavy rain by density); snow does
  not settle. Tests: `tests/test_cartoon_rain.py`.

### 69.40 Effect symbols over characters (Step 107)

A feeling should read at a glance: the `effect` beat action pops a small symbol over a character's
head (`- effect: pip` + `to: idea`, the `to:` convention of §69.11).

- **Symbols** (`cartoon/effects.py`, pure): `EFFECT_KINDS` sweat, anger, idea, question, exclaim,
  sleep, hearts, stars, sparkle, tear. Each is one or more *pieces* (`effect_pieces(kind)`), each a
  few closed outlines (`EffectShape`: counterclockwise points in *symbol units*, about 1 tall;
  fill `main` = the symbol's colour, `shine` white, `base` grey; ink outline or none) drawn from
  circles, ellipses, stars, a parametric drop and heart, explicit polygons (`!`, `Z`) and
  `thick_path` (a polyline turned into a band, so it fills and outlines like the rest: the `?`
  hook, the bulb's rays). Original simple shapes only; no font glyphs. `EFFECT_STYLES` gives each
  a spot, a size in head heights (0.2 tear .. 0.7 sleep / stars) and a theme token (`primary`,
  `accent`, `highlight`, `secondary`: tokens every preset defines).
- **Where** (`spot_at(spot, kind, head, facing, eye, crown)`, `effect_spot(..., avoid=)`): from
  the head's box on screen (`head_box`: the `head` part, else the top 30 % of the figure) and the
  facing: `above` (0.12 head heights over the head, a little forward), `front` / `back` (beside
  it near the top; the back one overlapping the head's edge), `corner` (on the head's top front
  corner), `ring` (round the top), `eye` (under the `eyes` part's middle, else a default eye
  point). A hat (`crown_top`: the `accessory` part's top when higher) lifts `above` and `ring`; the
  size always goes by the head. `effect_spot` takes the symbol's own spot unless its box overlaps
  one of `avoid` (the speech bubbles on screen), then tries `ALTERNATE_SPOTS` (above → front, back;
  corner → front, back...). The spot is chosen once when the effect starts and worked out again
  every frame from the head (it moves with walks, jumps, turns and shots).
- **Motion** (pure, a function of the seconds since it appeared): `pop_scale(t, strength)` blends
  an eased grow over `POP_SECONDS` 0.25 (strength 0) with the step response of `POP_SPRING`
  (3 Hz, ζ 0.35: about 30 % overshoot, settled by ~1 s; Step 82's `Spring`) by the character's
  `cartoon_motion` strength; `exit_scale` shrinks over `EXIT_SECONDS` 0.3. `piece_pose(kind, k, t)`
  → `PiecePose(dx, dy, scale, angle)`: the drop slides down 0.25 and stays, the anger mark and the
  bulb's rays pulse, `?` rocks ±10°, `!` shakes and calms, the Zs rise along a diagonal one after
  another (2.4 s cycle, growing and shrinking), hearts bob, the stars orbit (1.6 s) and spin,
  sparkles twinkle, the tear forms, runs down and forms again (2 s). Shapes are never mirrored (a
  `?` reads the same either way); offsets forward and turns follow the facing.
- **Drawing** (`cartoon/effect_symbols.py`): `EffectSymbol(kind, color=, character_height=)` is a
  `VGroup` of one `VGroup` per piece, each shape a `VMobject` with corners; strokes 0.8 of a
  character's outline for its height, at least one pixel. `place(spot, facing, strength)` redraws
  every member from its stored points (an affine per piece: scale, turn, offset); a member smaller
  than 3 % of the symbol gets no points (no ink dot at scale 0). `follow(character, avoid=)` adds a
  time-based updater (`age += dt`, then `place`). The symbol is a mobject of its own, never part
  of the character (§69.22).
- **The action** (`scenes/effect_action.py`, against `vidgen.api`): options `to` (required),
  `color`, `sound`; `run_time` `EFFECT_SECONDS` 0.4 (the pop); reversible, `until_next_beat`;
  `alters_targets = False`, so it plays in the same batch as the character's other actions due
  with it instead of after them (a `react` and an `effect` at one `at` do not stretch the beat).
  `apply` makes a symbol per character, chooses its spot clear of the speech bubbles on screen,
  puts it above everything drawn (`z_index` top + 1) and returns `EffectAppear` (an `Animation`
  that only holds time: no starting copy, updating not suspended, `introducer`); `revert` sets
  `leaving` and returns `EffectAppear(leave=True)` (a `remover`). A `say` bubble placed later
  avoids the symbols on screen (`Say._bubble`). Not marked lit, so the stage's light never grades
  it (§69.31). Validate: targets must be characters (`_Acting`), `to` one of the kinds.
- **Sound** (`cartoon/foley.py`): `PlayedAction.effect`; `EFFECT_SOUNDS`: idea `chime` 0.5 s
  +3 st (the short ding), sparkle `chime` 0.4 s +12 st, exclaim / question / hearts / sweat a `pop`
  at +5 / −4 / +2 / −5 st, anger a 0.3 s `thud`; sleep, stars, tear silent; at the pop's start.
  `Stage.action_foley` passes the kind unless `sound: false`; `foley: false` silences all.
- **Layout dump and lint**: an `EffectSymbol` is one object of kind `effect` named after the kind,
  with `effect` and `effect_of`; `describe` says `effect 'idea' of character 'pip'`;
  `lint_ignore`'s `object` matches `effect_of`. `bubble_overlap` also reports a speech bubble
  covering at least `min_overlap` of a symbol's box; `hidden_speaker` ignores symbols (a tear sits
  on the face on purpose).
- **Automatic directing** (`cartoon/directing.py`, kind `effects`, last in `DIRECTING_KINDS`): at
  most one symbol per beat, for the first change of expression in it (written `emote` / `react`,
  a voice sound's face, then this beat's automatic reactions, recorded in `_SceneState.faces_now`)
  to one of `EXPRESSION_EFFECTS` (surprised → exclaim, thinking → question, angry → anger; since
  Step 125 dizzy → stars, frightened → sweat, §69.59), at the
  change's `at`, for a character on the stage; none in a beat with a written `effect`. Unlike the
  other passes it acts on a character a written `emote` / `react` targets: the symbol adds to that
  face and changes nothing the action set. Pasting `vidgen direct --print` makes it written, so
  the planner adds no other one there.
- **Screenplay** (`screenplay.py`, `_EFFECT_VERBS`, tried before the other verbs): `has / gets an
  idea`, `lights up` (idea); `is / looks confused`, `puzzled`, `wonders`, `scratches his head`
  (question); `is startled`, `alarmed`, `shocked` (exclaim); `sweats`, `gulps`, `is nervous`
  (sweat); `is angry`, `furious`, `fumes` (anger); `falls asleep`, `dozes off`, `nods off`,
  `snores` (sleep); `falls in love [with X]`, `swoons` (hearts); `is dizzy`, `sees stars` (stars);
  `sparkles`, `beams with pride` (sparkle); `cries`, `weeps`, `sheds a tear` (tear).
- **Checked by eye**: every symbol on two generated looks (`dot`, round with a bun; `moss`, tall
  with a hat and glasses) and the SVG `sprout`, facing right and left, at 1 s (scratch sheets);
  a scratch copy of `examples/cartoon` with six written effects and `auto_direct: true` at
  preview: the bulb over Dot, the sparkle after her walk, the exclamation mark following Moss's
  jump, the anger mark moved in front of Moss's face by his speech bubble, Zs over Moss while
  Dot enters;
  `vidgen lint` 0 findings (before the fixes: the anger mark under the bubble, and a
  `rushed_animation` from the effect waiting for a `react`).
- **Not done here**: symbols do not scale with a close-up beyond the head's own size; a symbol
  that cycles (tear, Zs) can be between cycles in a still; no symbol for a prop. Tests:
  `tests/test_cartoon_effects.py`.

### 69.41 Motion effects and running (Step 108)

Fast moves read better with the cartoon marks of speed; the motion code adds them on its own.

- **When** (`cartoon/motion_effects.py`, pure): `motion_effect_cues(played, strength)` turns one
  animation of an action *as it played* (`PlayedAction`, the record foley reads, §69.19; new
  fields `step_length`, `lift`, `gesture`, `big`, `flight`) into `MotionEffectCue(kind, time,
  seconds, toward, arm)`, scene times. Strength 0 (`cartoon_motion: none`) gives none. A walk
  (`walk_to`, `run_to`, `enter`, `exit`) whose top speed (`walk_top_speed`: heights over the
  feet's seconds × (1 − `WALK_EASE`)) is at least `FAST_SPEED` 1.15 heights/s (default walk ≈
  0.7, run ≈ 1.7): `dust` blowing `back` where the feet set off (after the wind-up; not for an
  `enter`, off view), `speed_lines` while the speed is at least `SPEED_SHOWN` 0.7 of the top,
  `dust` blowing `front` where the feet stop (not for an `exit`). A `jump`: `dust` both ways at
  the landing (the end of the flight phase), plus `impact` stars from `HARD_LANDING` 0.7 heights.
  A prop `PropMove` that flies (`rise > 0`: a throw; `path`: blown): `speed_lines` from `leave`
  to `arrive`. A `gesture` with `big: true` of `WHOOSH_ARMS` (point, wave: the gesture's arm;
  shrug: both): `whoosh` while the arm moves in (the ease-in window without the anticipation and
  settle of `motion_ease`) plus `WHOOSH_TRAIL_SECONDS` 0.15. Lasting `DUST_SECONDS` 0.55,
  `IMPACT_SECONDS` 0.6.
- **Shapes** (pure, seconds since the cue started + a seed, lengths in mover heights):
  `dust_puffs` (5 round puffs, each a little later, drifting away and up, growing, fading),
  `speed_lines` (3 lanes, flickering length, faded in and out by `fade`), `impact_stars` (4 stars
  bursting in a 25–155° fan, popping in, spinning, shrinking), `arc_band` (a band along a circle
  tapering from nothing to its width: the whoosh). `motion_seed(scene, mover, kind, time, arm)`
  (crc32) makes every render alike. `effect_scale(strength)` = 0.6 + 0.4 × strength (`calm`
  0.76).
- **Drawing** (`cartoon/motion_effect_shapes.py`): `MotionEffect(cue, mover, delay=, seed=,
  scale=, star_color=, effect_of=)`, a `VGroup` of a fixed pool of `VMobject`s redrawn from the
  pure shapes by a `dt` updater (`clock`; nothing before `delay`, `done` and no points after
  the cue). Dust and stars stay where the mover's feet were when they started (`feet_of`); speed
  lines follow the mover: behind a character's back edge at 0.45 of its height along its facing,
  behind a prop along its frame-to-frame motion (sized by at least `PROP_LINE_UNIT` 2 units so a
  ball's lines are not specks); the whoosh follows the hand about the shoulder (`hand_point`,
  `shoulder_point`), trailing back to where the hand was 0.15 s ago (angle history, so its arc is
  round at any frame rate). Ink outline and lines (`CHARACTER_INK`, lines at 0.55 opacity), dust
  in the `dust` particles' colour, stars in `highlight`. Never added to a character (§69.22).
- **On a stage** (`scenes/stage.py`): the runner calls the new hook
  `NarratedScene.action_motion_effects` right after `action_foley` with the same arguments (base:
  nothing). `Stage` returns at once with `motion_effects: false` (the stage's param, else the
  top-level `motion_effects`, default true); else per animation the strength is the animation's
  (`Walk` / `Jump` / `Gesture` `.strength`), for a prop move its thrower's `cartoon_motion`, else
  the scene's. Each `MotionEffect` goes right after its mover in `scene.mobjects` (speed lines
  right before it), with its `z_index`; it is not marked lit, so the light never grades it
  (§69.31). A scene updater (`_motion_sweep`, kept by identity) removes finished effects and
  itself when none is left, so a scene after its effects keeps Manim's static frames. Foley and
  motion effects build their `PlayedAction` with one helper (`_played`).
- **Running** (`run_to`, `scenes/moving.py`, a `WalkTo` subclass): `Walk(gait=RUNNING)`; `Gait`
  (`cartoon/acting.py`) scales the walk cycle: `stride` 1.6 (`Walk.step_length` = `STEP_LENGTH`
  × stride, also for the footsteps: `footfall_shares(..., step_length)`), `swing` 1.5, `knee`
  1.6, `elbow` 2, `bob` 2 and `lean` 12° forward × `walk_amplitude` (part of the gait, so also
  with `cartoon_motion: none`). `RUN_SPEED` 6 units/s. `WALKING` is the plain walk, computed with
  the same floating-point operations as before. `run_to` counts as a walk everywhere a walk does
  (foley, directing's look and move sets, the holding replay, a pinned seat, mid-action stills).
- **`big` gestures**: `gesture` option `big` (default false); only the whoosh reads it.
- **Layout dump and lint**: kind `motion_effect` named after the kind, keys `motion_effect` and
  `effect_of` (`lint_ignore`'s `object` matches it); `describe` says `motion effect 'dust' of
  'pip'`; `off_frame`, `covered_text` and `hidden_speaker` skip it (a mark that passes in a
  moment).
- **Checked**: a scratch stage at preview 854×480 / 15 fps (run, high jump, big wave, fast walk,
  throw, big point): stills by eye (the run's long strides and lean, lines behind it, dust at
  set-off and stop, stars and dust at the landing, the whoosh behind the waving hand, lines
  behind the ball); `vidgen lint`: only an author-caused `off_frame` of the tree. The same scene
  with `motion_effects: false` (run_to → a fast walk_to, no `big`) gives a video whose 350 frames
  have the same `framemd5` as one rendered by the code before this step.
- **Not done here**: no sound of its own (foley has footsteps, boing, thud); no dust where a prop
  lands; `big` does not enlarge the gesture itself; no effects for `keyframes` / `move_along`
  moves; the screenplay has no "runs" verb for `run_to` (`runs to` still means `walk_to`).
  Tests: `tests/test_cartoon_motion_effects.py`.

### 69.42 Rooms: indoor sets (Step 109)

Indoor stories need a set that reads as a room at once. A stage's `room:` param draws one instead
of the sky and the ground band; everything else on the stage stays as it is.

- **Geometry** (`cartoon/room.py`, pure): the wall stands at a *depth* (§69.6):
  `wall_depth(items, depth)` is the given `room.depth`, else the larger of `WALL_DEPTH` 0.4 and
  the deepest item standing on the floor (`lift` 0), so the floor always reaches behind what
  stands on it (a given depth with something deeper is a config error). `room_geometry(ground=,
  depth=, size=, frame_width=, frame_height=, stage_width=, ceiling=)` → `RoomGeometry`: the
  `floor` box from the frame's bottom edge up to the *wall line* (`ground + FAR_RISE × depth`,
  where a thing at that depth stands, which is also `ground_top` of the stage's items, the
  doors included), the `wall` above it to the frame's top, the `skirting` board
  `SKIRTING_HEIGHT` 0.07 wall units high on the wall, an optional `ceiling` band
  (`CEILING_HEIGHT` 0.07 of the frame height); all as wide as the stage. The *wall unit* is the
  height of a character of scale 1 at the wall's depth; windows and doors are sized in it, so
  they match the characters in 16:9, 9:16 and on a wide stage. Patterns: `wallpaper_stripes`
  (`STRIPE_WIDTH` 0.11), `wallpaper_dots` (a grid `DOT_SPACING` 0.28, every other row shifted);
  `floor_rows` (rows of boards or tiles, the first `ROW_DEPTH` 0.16 deep at the wall, each
  further one deeper by a constant ratio so the front row is about `FRONT_ROWS` 2.2 times the
  first: perspective without a camera model), `floor_lines(flooring, floor, unit)`: `boards`
  (row seams plus joints every `BOARD_LENGTH` 0.9, scaled with the row, staggered by 0.37 of a
  board per row), `tiles` (row seams plus lines from the wall line to the bottom edge spreading
  `FLOOR_SPREAD` 1.6 times from the stage's middle, cut at the side edges), `plain`.
  `window_parts(x, wall_line, unit, width, height, sill, curtains)` → `WindowParts`: frame,
  glass (inset by `FRAME_SHARE` 0.08 of the smaller side), a cross of bars, the sill, the rod and
  two gathered curtains (closed outlines, `CURTAIN_SHARE` 0.3 of the width each).
- **The sky outside** (pure): `window_sky(light)` → `WindowSky(top, bottom, stars)`:
  `WINDOW_SKIES` per preset (`day` blue, `morning` peach low in the sky, `sunset` blue over
  orange, `night` dark blue with stars at 1, `indoor` an evening blue with stars at 0.6: lamplight
  inside means evening outside), a `(tint, strength)` light multiplies the day's sky as the grade
  would. `SkyChange` + `sky_at(base, changes, now)` fade it with the light (§69.31's `fade_at`,
  smoothstep, `blend_skies`).
- **Drawing** (`cartoon/room_drawing.py`): `draw_room(geometry, colors, wallpaper=, flooring=,
  windows=[WindowLook(parts, frame, curtains)], sky=, short_side=, frame_area=, preview=)` →
  `RoomDrawing` of three mobjects, back to front: `room` (wall, wallpaper in `shade(wall, 0.1)`:
  darker on a light wall, lighter on a dark one; floor, seams, skirting, ceiling), `window_views`
  (`WindowViews`: a gradient per glass and a `StarField` per window, seeded per window) and
  `room_front` (frames with the glass cut out, bars, sills, rods, curtains, ink outlines as wide
  as a character's at the wall). `room_colors` fills in the skirting (the floor's colour 0.3
  darker) and a `ceiling: true` (the wall's 0.25 lighter). Default colours are fixed hex
  (`DEFAULT_WALL` cream, `DEFAULT_FLOOR` wood, `WINDOW_FRAME` white; no theme token is light and
  warm in every preset, like the cloud's white, §69.8); curtains default to `accent`.
- **On the stage** (`scenes/stage.py`): `StageRoom` (`wall`, `wallpaper`, `floor`, `flooring`,
  `skirting`, `ceiling`, `depth`, `windows`, `doors`; `room: true` = defaults), `RoomWindow` and
  `RoomDoor` (a mark or an x alone is one). `_backdrop` returns the room's three mobjects then the
  background / middle layers (no picture, colour, ground band or open-sky stars); the construct
  marks everything lit but `WindowViews` (and stars): the room is graded by the light, the sky
  outside is not. `_room` keeps `_sky_base`; `change_light` adds a `SkyChange` per `light` action;
  `_show_light` (the light's listener, called on every grade change, so every frame of a fade)
  shows `sky_at(...)` in the windows. Manim's static image keeps the whole room while the light
  does not change (§69.20).
- **Doors are props** (§69.8): the `door` prop gains the shapes `closed` / `open` (§69.37's live
  copies; open: the doorway in a dark shade, the leaf swung towards the viewer on the hinge side,
  nearly edge on, within the prop's box), so `open` / `close`, `open: true`, `lean_on` and the
  layout dump's `shape` work as for an umbrella. `Params.stage_props()` is the props, then one
  `StageProp(prop: door, depth: wall depth, scale: DOOR_SCALE 1.3...)` per room door;
  `prop_names()` (numbered together, so a second door is `door_2`), `items()`, the holding /
  seating / reshape / blow-away checks, `stage_frame` and the construct read it. A door's name is
  also a **mark** (`stage_marks()`: own marks plus doors; used for characters' `at`, `camera_at`,
  `camera_place`, `stage_layout` and the planner's frame); a door named like a mark, a character
  or another prop is a config error. Doors cast no shadow (they are in the wall). The prop
  gallery still (`docs/gallery/media/props.png`) gains `door (open)`.
- **Through a door** (`scenes/moving.py`): `enter` / `exit` option `door` (not with `side` /
  `to`). The action opens the door at once if it is closed (`Stage.door(name).show_shape`), then
  `Walk(start_x=door x, fade_in=DOOR_FADE_SECONDS 0.35)` (exit: `Walk(door x, park_x=offstage,
  fade_out=...)`), at least twice the fade long. `Walk` keeps every family member's fill and
  stroke alphas at `begin` and scales them by `passage_fade(t, run_time, fade_in, fade_out)`
  (smoothstep ramps, each at most half the walk), sets `Character.shown`, and puts them back
  after parking; `ShadowCaster` fades the shadow by `shown`. Without `door` nothing changes (no
  alphas kept, the same `run_time`). The character keeps its own depth (moving in depth is Step
  111), so it fades in in front of the doorway.
- **No weather inside**: a room with `wind` not 0, or `particles` of `OUTDOOR_PARTICLES` (rain,
  snow, leaves, streaks), is a config error; the `wind` action and an outdoor `particles` action
  are validate problems. Rain or snow seen through a window was left out: drawn behind the
  characters, an animated window would put the whole set in Manim's moving mobjects (§69.20).
- **Sets** (`includes.apply_set`, §69.35): a stage's `room` drops the set's `image`, `generate`,
  `background` and `ground_color`; a stage's `image` / `generate` / `background` drops the set's
  `room`; a set's room and a stage's merge key by key (a mapping).
- **Checked by eye** (scratch projects at preview 854×480, `vidgen storyboard`): a striped room
  with boards, a table, a window and a door where moss comes in through the door (half-way still:
  fading in in the doorway, the door open) and dot leaves through it (fading out); `sunset` with
  dots, tiles, a ceiling and an open door facing left (the window sky blue over orange);
  `night` (dark sky with stars in both windows, the room graded blue); `indoor` then `- light:
  night` (evening blue, then night); a 2-frame-wide room in `morning` with a close-up and
  automatic reframing pans, and its 9:16 variant. `vidgen lint` on both projects: 0 findings
  (one author-caused `rushed_animation`).
- **Not done here** (Step 110 adds furniture and the screenplay's rooms, §69.43): rain or snow
  through the windows; a door's own sound; walking in depth through a door.
  Tests: `tests/test_cartoon_room.py`.

### 69.43 Furniture (Step 110)

Rooms need furniture that characters use: sit on, lean on, stand in front of. All of it is
built-in props (§69.8), so placing, sizing, colours, the layout dump, lint, shadows, the light and
shots work as for any prop.

- **The props** (`cartoon/props.py`, `FURNITURE`): `sofa` 0.36, `armchair` 0.38, `bed` 0.34,
  `bookshelf` 0.9, `counter` 0.5 (a kitchen counter: cupboards, drawers, a worktop), `fridge`
  0.95, `picture` 0.3 (a framed hill and sun), `rug` 0.06 (an oval seen nearly edge on, 20
  prop units wide), `houseplant` 0.75 (broad leaves in a round pot; the older `plant` stays the
  small one), `clock` 0.2 (ten past ten), `tv` 0.55 (on a low cabinet), `desk` 0.42 (with its
  chair); heights relative to a character (`PROP_HEIGHTS`). Primitives, two theme colours each
  (`PROP_COLORS`) plus shades and the ink, except fixed light colours where no token is light in
  every theme: the fridge and the clock's face (`#F4F6FA`), a bed's sheet and pillow (`CLOTH`),
  a television's case (`TV_CASE`). Drawn as seen from the front of the room, their backs to its
  wall; a bed and a desk side on, along it (headboard / chair on the left as drawn facing
  right). Every drawing's box is centred on x 0, so a prop's feet are its middle. Original simple
  shapes; nothing imitates a known design. Gallery: `still.write_props_png(..., kinds=FURNITURE,
  columns=4)` → `docs/gallery/media/furniture.png` (16 KB, 4×3), shown in CONFIG.md "Rooms";
  `props.png` keeps the other props (`kinds` default: everything but `FURNITURE`; the file is
  byte-identical to Step 109's).
- **Seats** (`cartoon/seating.py`): every built-in seat line is at **0.14 of a character's
  height** (the prop's height × the seat's y), the rule of §69.36: below every generated
  character's hips, so `Character.seated` puts the hips on the line with the knees bent and the
  feet on the floor. `PROP_SEATS` gains sofa (0, 0.39), armchair (0, 0.37), bed (0.15, 0.41), desk
  (−0.64, 0.333: its chair); `SEAT_BACKS` gains `desk` (the sitter faces the desk).
  `SEAT_PLACES` (sofa ±0.6, bed −0.45 / 0.75 prop units): a seat with more than one place seats
  one character per place. `Prop.seat_places` (mirrored with the facing,
  `mirrored_places`), `Prop.seat_point(place)`. `Postures.sit(character, prop, places,
  prefer)` takes the first free place in `prefer`, then in order, and returns it
  (`Postures.places`); a full seat is a `PostureError` ("'sofa' is full: pip and kit sit on it
  then"; one place keeps "'chair' is taken: ..."). `sit_on` prefers the place nearest to the
  character's feet. `holding_problems(seat_places=)` and the planner (`StageFrame.seat_places`,
  from `stage_frame`) count the places. `PROP_LEANS` gains bookshelf, counter and fridge (their
  sides).
- **Against the wall** (`scenes/stage.py`): `StageProp.against: wall | None`. In a room, a prop
  `on_wall()` (`against: wall`, or a prop that hangs, without a `depth` of its own) is put at the
  wall's depth by `Params.stage_props()` (a copy with `depth` set), which every reader of the
  props already uses (§69.42); such props are left out of `wall_depth`'s "deepest thing on the
  floor", so they never push the wall back. A given `depth` wins (in front of the wall; behind it
  is the room's config error). `against: wall` without a room is a config error.
- **Hanging on the wall**: `PROP_HANGS` (picture 0.5, clock 0.85): how far above the floor the
  prop's bottom edge is, in the heights of a character at its depth. `StageItem.hang` (new,
  default 0) is added by `stage_layout` to the feet's y (`hang × size × short side × depth
  scale`), so the height is right in 16:9, 9:16 and at any depth, unlike `lift` (frame heights).
  Hanging props cast no shadow; nor does a prop in `FLAT_PROPS` (`rug`). (The napkin keeps its
  shadow: it can fly.)
- **Screenplay** (`screenplay.py`): `set:` gains `room` (alone: `room: true`; else comma
  separated `ROOM_WORDS`, `window [at place]`, `[open] door [(name)] [at place]`); a room drops the
  sky / ground colour defaults (a written background is left out with a TODO). Props take
  `against the wall` / `on the wall` (→ `against: wall`; without a room it is left out with a
  TODO) and other words (`PROP_WORDS`: couch, bookcase, kitchen counter, refrigerator, picture
  frame, carpet, plant pot, wall clock, television...). No sit / lean verbs yet (§69.28's gap).
- **Checked by eye** (scratch project at preview 854×480, `vidgen storyboard`, `indoor` light): a
  striped living room with a bookshelf, a sofa (two characters sitting side by side, each on the
  place nearer to it), a picture above it, an armchair (a third sitting), a clock, a houseplant, a
  rug and a door; a tiled studio with a ceiling, a fridge, a counter (a character leaning on its
  end), a television, a desk (a character sitting on its chair, facing it) and a bed (a character
  sitting on its edge). Hips on the seats, feet on the floor. `vidgen lint`: only the author's
  props cut at the frame's edges.
- **Not done here**: sitting on furniture from another depth (characters stand at the wall's
  depth to use it; Step 111 walks there in depth, and `vidgen validate` asks for that walk,
  §69.44); lying on a bed; a prop on another (a tv on a
  counter: `lift` by hand); door marks in the screenplay's directions ("walks to the door").
  Tests: `tests/test_cartoon_furniture.py`.

### 69.44 Moving in depth, and a front view (Step 111)

Characters stood at one depth all scene and showed only their side. Now they walk towards and
away from the camera, and turn to face the viewer.

- **Depth paths** (pure, `cartoon/stage.py`): `walk_to` / `run_to` take `depth` (0..1) or `to:
  {mark, depth}` (`WalkPlace` in `scenes/moving.py`; `walk_destination(options)` reads the raw
  options for the planner and `vidgen validate`). x and depth move together in a straight line:
  `depth_along(start, end, share)` is the depth at a share of the distance, and
  `depth_walk_distance(dx, start, end, height)` the length, a unit of depth counting
  `DEPTH_WALK_HEIGHTS` (2) of the walker's heights where it starts (`hypot`). The run time is
  `walk_seconds` of that length (plus `cartoon_motion`'s wind-up and settle), so a walk across
  is unchanged. Missing `to` keeps the x, missing `depth` the depth; one of them is required,
  the depth only once (a validate problem), and in a room not behind the wall
  (`wall_depth()`).
- **The walk** (`Walk(..., depth=, feet_y=, carried=)`): every frame the walker's depth is
  `depth_along` of the share walked (`walk_progress`), its feet on `feet_y(depth)` (the stage's
  `feet_y_at`: `feet_point`'s ground line there), and it is scaled about its feet by
  `depth_scale(depth) / depth_scale(previous)`, its stroke widths by the same factor
  (`scale_strokes`, no floor, so a walk back restores them), and so are the props it holds
  (`carried`, about their grip). `Character.stage_depth` and `ground_y` follow (not `depth`:
  that is Manim's z-size property, whose setter rescales). A walk only in depth keeps the
  facing; the walk cycle counts steps along the whole path. The action passes the props whose
  `held_by` is the walker and calls `Stage.walk_in_depth`, which also moves `grounds[name]`
  (the `keyframes` y 0) to the new depth.
- **Draw order** (pure: `depth_crossings(start, end, others)` → the shares where the walker's
  depth passes another's, `acting.depth_switch_times(...)` → the seconds, through the inverse
  `walk_time_at` of `walk_progress` and the `cartoon_motion` phases; `depth_slot(depth, others,
  current)` → where a character at a depth goes among the others, back to front: after the deeper
  ones and the props at its depth, before the nearer ones, keeping its place among characters at
  its depth). Manim lists the mobjects it draws when an animation begins (`moving_mobjects`, a
  flat family list), so reordering `scene.mobjects` alone shows only at the next `play`. The
  stage therefore runs a scene updater while a walk in depth is under way (`_draw_order_step`,
  installed by `walk_in_depth`, or from the start when a character faces or turns to the front):
  each frame it moves the walker, with the props right after it that it holds, to its
  `depth_slot` (`_keep_depth_order`), keeps the moving shadows group before the first thing whose
  shadow it draws (`_shadows_first`: the walker's shadow lies under a tree it walks behind), and,
  when anything moved or a character's parts changed order, sets `scene.moving_mobjects` again
  from `get_moving_and_static_mobjects`. `get_moving_mobjects` redraws, during a walk in depth,
  everything from the first character or prop whose depth it passes (`_depth_crossers`), so the
  static image never holds something the walker goes behind. A put-down or thrown prop takes its
  holder's `stage_depth`.
- **Shadows**: `ShadowCaster.ellipse` takes the ground from the caster's `ground_y` when it has
  one, and with `grows` (the stage's characters) scales the shadow by `standing_height / size`.
- **Front view** (`generate_parts(look, colors, front=True)`, `look_parts(..., front=)`, cached
  per view): the same parts and shape names as the side view; the face centred (`face_x` 0), the
  pupils ahead, the triangle nose symmetric, the fringe parted in the middle, long hair and the
  bun symmetric, the bean body without its back pinch, a temple each side of glasses.
  `Character(..., front=parts)` checks the parts and shape names match (`_check_front`) and keeps
  one `_View` per view (shapes, drawings, members, pivots, limbs, order, trailing pieces); each
  part's `VGroup` holds both views' live copies (side first), only the shown one has points, so
  the family never changes (§69.22). Facing `front` (`FACINGS`) activates the front view: no
  mirror, `FRONT_DRAW_ORDER` (both arms in front of the body). Switching views hides what the
  other showed and reorders the parts (`submobjects`), counted by `order_changes` (the stage's
  updater then refreshes Manim's list). Poses, expressions, visemes, blinks and gestures use the
  same entries: the pose tables already move the two arms symmetrically on screen.
  `side_facing` remembers the side; `turn()` from the front goes back to it. A character without
  a front view (an SVG one) ignores `front`; `cast.front_view_warnings` (in `vidgen validate`)
  warns for a stage character `facing: front` or a `turn` `to: front` of one.
- **Turning**: `PoseChange` between a side and the front swaps the view at half (like the mirror)
  and narrows the figure about its feet by `turn_squash(progress)` (1 at the ends, 1 −
  `TURN_SQUASH` 0.12 half-way). `turn` takes `to: front` (default from the front: `side_facing`).
- **Walking facing front**: `walking_state(..., "front")` keeps the legs from swinging sideways:
  a leg drawn one each is shortened (thigh and shin y scale, by `FRONT_STEP_SHORTEN` 0.25 at the
  largest knee bend) so its foot lifts, one-piece legs narrow, the body bobs, the arms sway
  together by `FRONT_ARM_SWING` 0.3 of the swing; no lean or follow-through (they would tilt
  sideways). Sitting (`sit_on` keeps `side_facing`), leaning and crouching (`_reach_low` turns a
  front-facing character to its side first) are drawn from the side.
- **Facing in the pure modules**: `facing_sign(facing, front=1.0)`: effect symbols, held props,
  motion effects treat the front like `right`; shots and reframing leave no look room in front of
  a front-facing face (`front=0`); `look_pose` / `camera_look` keep the eyes centred from the
  front; the planner never sees a speaker behind a front-facing posed character.
- **Validate and lint**: `holding_problems(depths=)` (from `StageFrame.depths`, every character
  and prop's start depth) follows walks in depth (a character's height scales with
  `depth_scale`) and reports a `sit_on`, `lean_on`, `pick_up` or `give` across more than
  `DEPTH_REACH` (0.05) with the walk that fixes it (`- walk_to: dot, to: {mark: 0.42, depth:
  0.4}`); `StageFrame.place_x` and the planner read `{mark, depth}`. The layout dump writes a
  character's `depth` when it is above 0; `character_overlap` and `walk_overlap` skip pairs
  `DEPTH_APART` (0.15) or more apart in depth, also in the planner's predicted stills (start
  depths).
- **Checked by eye** (a scratch project at preview 854×480, `vidgen storyboard`, 3 and 5
  stills per beat): dot walking away past a tree at depth 0.5 (in front of it, then behind it,
  shrinking, her shadow under the trunk), behind moss at depth 0.5, and back to the front facing
  her side; moss walking towards the camera in front of a box; dot facing front, talking (lip
  sync), waving; moss turning to the front and both turning back; in a room dot walking back to
  the sofa at the wall's depth and sitting on it, and moss facing front stepping towards the
  camera (a lifted foot each step). Stills of `vidgen character --png --facing front` for both
  looks. `vidgen lint`: no findings.
- **Not done here**: a back view (walking away facing front walks backwards: keep the side);
  `enter` / `exit` at a depth; a speech bubble does not resize with its speaker; the planner
  (automatic directing, reframing) keeps each character's start depth and size; sitting on the
  ground or lying, from the front.
  Tests: `tests/test_cartoon_depth.py`.

### 69.45 Iris transitions (Step 112)

- **Config** (`config.py`): `TransitionConfig.type` adds `iris_out` and `iris_in` (default 1.2 s,
  `TRANSITION_DURATIONS`), with `character` (a character name) or `at` (`[x, y]`, fractions of
  the frame from its top-left corner, each 0..1; not both) and `color` (default black,
  `transitions.IRIS_COLOR`; `background`, tokens and hex as for `fade_color`). `character` / `at`
  on another type, `color` on a type other than fade_color and the irises are config errors.
  `IRIS_TRANSITIONS`, `COLOR_TRANSITIONS = (fade_color, iris_out, iris_in)` and
  `TransitionConfig.through_color` replace the `type == "fade_color"` tests (plan, requested and
  head frames). The key is `character`, not `on`: PyYAML reads a bare `on:` key as `True`.
  An `iris_out` on the first scene is an error (nothing before it); an `iris_in` there opens the
  video (fade_in only, like `fade_color`).
- **Semantics (decision).** Both are a close then an open through the colour, split like a
  `fade_color` (`round(duration x fps / 2)` frames on each side, no overlap, the timing contract
  of §49: the closing covers the silent tail of the scene before or holds it). The type says
  which side has the target: `iris_out` closes on the scene before's `character` / `at` and opens
  the next scene from the frame's centre; `iris_in` closes the scene before on its centre and
  opens on the next scene's `character` / `at` (`transitions.iris_scene(i, t)`: `i - 1` for
  iris_out, `i` for iris_in). One transition per boundary gives the classic "iris out, iris in";
  a card between two scenes (iris_out into it, iris_in out of it) is the usual cartoon flow.
- **Drawn in the renders, not at the join (decision).** The iris is a `fade_color` with a
  circular mask: `ColorFade(..., iris_in=, iris_out=)` (outermost `add_frame` wrapper, §49)
  replaces the uniform blend of those frames by `frame x inside + colour x (1 - inside)`,
  `inside = iris_coverage(h, w, x, y, r)` (1 in the disc, a one-pixel soft edge),
  `r = iris_radius(weight, iris_full_radius(w, h, x, y), hold)` of the same colour weight as the
  fade (1 on the boundary frames: closed). `iris_radius` eases from the radius that clears the
  frame's farthest corner to 0 (`smoothstep`); with `hold` (a character's head) it eases to it by
  `IRIS_HOLD[0]` (0.55) of the way, stays until `IRIS_HOLD[1]` (0.8), then closes (an opening is
  the same in reverse). `NarratedScene._iris_point` gives the callable `(width, height) ->
  IrisPoint(x, y, hold)`: the `at` point, the frame's centre, or the character's head (`head_box`
  of `self.cast[name]`, through the camera frame, so shots and zooms are followed; `hold` =
  `IRIS_HEAD_SCALE` 1.5 x half the head box's diagonal), asked on every masked frame (the circle
  follows a moving character; "its head as the scene ends" is where it is in those frames). A
  name not in the scene's cast at render time is a `VidgenError`. So the join sees a cut: no
  `xfade` filter, nothing that depends on the FFmpeg version (the render test joins with 6.1.1,
  7.1.5 and 8.1.3; in a video with crossfades the iris boundaries are cuts inside a run, tested),
  and stills, storyboards and the layout dump see the irises. Rejected: a custom `xfade`
  expression at the join (an overlapping transition would hide the next scene's first frames
  under the colour while its narration starts, needs the head position written by the worker,
  and the expression's planes and pixel format differ per FFmpeg build).
- **Validate**: `transitions.iris_problems(config)` (in `vidgen validate`): a `character` not on
  the target scene's stage (`target_names` of its params, declared characters only):
  `scenes[1].transition.character: the iris_out into 'later' closes on 'kit', who is not in
  scene 'a' (its characters: pip)` (`transition.character` for the video's default).
- **Not done**: `wipe_star` (optional in the step); a shape other than a circle; an iris that
  closes on a prop.
  Tests: `tests/test_cartoon_cards.py`.

### 69.46 Title cards: the `card` scene (Step 112)

- **Scene** (`scenes/card.py`, `@scene("card")`): `text` (required), `subtitle`, `style: burst |
  frame | plain`, `color` (default `primary`), `text_color` / `outline_color` (default the better
  of white and the dark ink for the fill, the other for the outline), `spin` (burst: turns at
  `BURST_SPIN` 0.12 rad/s by an updater), `sting` (`StingSetting`; `at: end` is an error: the
  card's sting plays as the text pops in, `NarratedScene.sting(cue, 0.0)`). The card's colour is
  a full-frame rectangle from frame 0 (an `iris_in` opens on the card, not on the theme's
  background). Steps: burst / frame, text (and the subtitle unless there are two beats), then
  the subtitle; silent with `duration` or narrated; `outro` 0.5. Targets `text`, `subtitle`,
  `burst` / `frame`.
- **Pure layout** (`cartoon/cards.py`, no manim): `card_layout(width, height, style=,
  subtitle=)` -> `CardLayout` (text box 0.8 of the room in a wide frame, 0.9 in a tall one; 0.36
  / 0.46 of its height with / without a subtitle; the frame's outer and inner rectangles at
  `FRAME_INSET` 0.05 and `FRAME_GAP` 0.025 of the shorter side, the text kept clear of them; a
  burst radius past the corners); `burst_rays(radius, turn, count=18)` (every other ray, the
  lighter tone `burst_ray_color(color)` = 22 % towards white); `card_text_inks(*backgrounds)`
  (white or `CHARACTER_INK`, whichever has the higher worst contrast over the card's colours:
  lint's `contrast` passes on the fill alone); `card_outline_width(cap)` (twice
  `OUTLINE_SHARE` 0.09 of the cap height: the stroke is centred on the letters' edge).
- **Drawing**: the outline is a layer of plain shapes (each glyph's points) filled and stroked
  in the outline colour behind the text, not a background stroke per glyph (each glyph's stroke
  would cover the glyph before it: found in the first render). In the layout dump it is a
  `group` object below the text. The text pops in with `pop_scale` (§69.40) at strength 0.5 (a
  15 % overshoot; the text box leaves room for it); the burst grows by an `UpdateFromAlphaFunc`,
  not Manim's `GrowFromCenter`: an introducer is added to the scene again as it starts, over the
  text popping in with it (found by eye: the rays covered the letters).
- **Screenplay** (§69.25): `# Card: TEXT` (any level, `Card` with `:`, `.` or a dash; not a title
  heading) is a `ScriptScene(card=True)`; `_add_card` writes a `card` scene with that text,
  `duration: CARD_SECONDS` (2.5) without lines, else one beat per line (voices as on a stage;
  `[directions]` become `# TODO:` notes, a card has no stage); `set:` under a card is an error.
  After another scene the card comes in with `iris_out`, and the scene after a card gets
  `transition: iris_in` (written right after its `type`). `vidgen screenplay --json` counts a
  silent card's beats and characters as 0.
- **Gallery**: the guide's `scenes` topic has a `card` snippet (`# cartoons`) and a chooser row;
  `docs/gallery/card.md` and its four media files (about 180 KB) come from `vidgen gallery
  --types card`.
  Tests: `tests/test_cartoon_cards.py`.

### 69.47 More bodies and clothes (Step 113)

New `look` values (`config.CharacterLook`), all drawn from primitives, each with a side and a
front drawing (§69.44):

- **Bodies**: `body: pear` (an ellipse whose half width is × `0.78 − 0.22 sin t`: narrow at the
  shoulders, widest low down; its shoulders at `SHOULDER_SHARES` 0.62 of half its width) and
  `triangle` (a squarish outline, broad at the top, × `0.76 + 0.24 y` towards the hips);
  `BODY_SIZES` 0.42 × 0.46 and 0.44 × 0.46. **`proportions`**: `adult` (unchanged), `kid`, `tall_kid`
  multiply the adult `Proportions` by `PROPORTION_FACTORS` before the seed's variation (kid: head
  and eye gap × 1.3, eyes × 1.12, body 0.85 wide and 0.72 tall, legs 0.72, arms 0.78; tall kid:
  head 1.12, body 0.8 / 0.85, legs 0.95, arms 0.9). The figure is still scaled to height 1; how
  small a kid stands is the stage character's `scale` (guide: 0.7 / 0.85), so seats, reach and
  lint keep using one character unit. Hips stay on seats (Step 102): `Character.seated` puts the
  hips on the seat whatever the legs; a kid at scale 0.7 meets a seat 0.2 of its height up, above
  its hips, so its feet hang (`seated_sole`).
- **Outfits** (`cartoon/clothes.py`, `outfit` + `colors.trim`, default token `dim`): `limb_colors`
  colours the segments of §69.26 (upper arm, forearm, thigh, shin): `plain` and `apron` all
  `clothes`; `dress` short sleeves (bare forearms) and bare legs; `overalls` a `trim` shirt with
  `clothes` trouser legs, a bib clipped to the body and straps with buttons; `coat` long sleeves,
  `trim` trousers, a closure line, three buttons and lapels; `shorts` short sleeves, `trim` thighs
  and waistband, bare shins. `apron`: a `trim` panel from the chest to below the body (side view
  the front half, front view the middle), neck straps, a pocket from the front. The clothes of
  the body are cut from its outline (`primitives.outline_polygon`: each Bézier curve sampled;
  `clip_to_box`: Sutherland–Hodgman; `span_at`: its width at a height).
- **Skirts on the body, not on the legs**: a dress's skirt and a coat's tails (`SKIRTED_OUTFITS`)
  are drawn in the `body` part, from just above its bottom to the knee (a curved hem, flaring
  `SKIRT_FLARE`), so the legs walk under them. Such a body has a second shape `seated`
  (`config.SEATED_BODY_SHAPE`): the cloth as a wedge from the hips between `LAP_UP_DEGREES` 15°
  and `LAP_DOWN_DEGREES` −50° out to the knee plus 0.045 (from the front: shorter and wider).
  `Character.seated` shows it when the body has it (so `sit_on` does; `stand_up` goes back to the
  state before), and the `sitting` pose names it as its body's shape (`chosen_shape` falls back
  to the rest shape for every other character, which keeps their drawings). `cast.character_part_shapes`
  lists it, so validate knows it.
- **Patterns**: `stripes` (bands `STRIPE_HEIGHT` 0.03 every 0.065) and `dots` (radius 0.017 on a
  0.06 grid, every other row shifted, at least 0.008 inside the edge) on the body's cloth and on a
  skirt, in `pattern_tone`: 28 % towards black on a cloth of relative luminance above 0.35, else
  40 % towards white; the outline is drawn again over the pattern.
- **Shoes** (`shoes: shoes | boots`, `colors.accessory`): in the shin's group (`leg_*_lower`),
  the sole on the ground (the figure's bottom stays at 0), the toe forward (from the front a
  dome; boots add a shaft to 0.11).
- **Hair**: `ponytail` (tied at the back, a tapering tail, from the front swinging out on one
  side), `braids` (four lobes and a tie; one behind the head from the side, one each side from
  the front), `afro` (a bumpy mass 3 × 2.5 head radii about the head); all three with the hair
  cap. **`facial_hair`**: `moustache` (two lobes under the nose) and `beard` (round the jaw,
  growing towards the chin, a skin patch where the mouth moves, and the moustache), in
  `colors.hair`; `hair: none` gives bald with a beard.
- **Accessories**: `bow`, `cap` (head: the `accessory` part, `config.HEAD_ACCESSORIES`; a cap's
  dome sits above the brows, its peak forward or, from the front, a band), `backpack` (the pack
  behind the back from the side, the straps over the shoulders from the front), `necklace` (beads
  and a pendant) in the body. `hat` and `cap` together are a config error.
- **Wind** (§69.32): `TRAIL_WEIGHTS` (now in `cartoon/primitives.py`, re-exported by the
  generator) adds ponytail 0.9, braids 0.6, cap 0.25, pendant 0.5. Afro, bow, backpack and beard
  do not trail.
- **Effect symbols** (§69.40): afro, ponytail, braids and beard are marked
  `OUTER_HAIR_ATTRIBUTE`; `effect_symbols.head_box` leaves them out (the size and spots go by the
  head) and `crown_top` is the higher of the accessory's top and theirs (symbols go above an
  afro). Looks without those marks take the old code path.
- **Looks made before stay the same**: a plain outfit without pattern, backpack or necklace goes
  through the old body code; the new branches add nothing to old looks. `tests/test_cartoon_outfits.py`
  pins a digest of every drawn member (points, styles, trailing marks) of eight earlier looks, both
  views, taken before the change.
- **Screenplay** (§69.25): `LOOKS` gains five looks using the new values, each with its
  `voice_kind` (two feminine, two masculine, one neutral); casts of up to six without stated
  kinds get the same looks as before.
- **Sheets and docs**: `vidgen character-sheet` ends with a `view` section (`front`) for generated
  characters; `vidgen character` prints a `wears:` line. `still.write_looks_png(theme, path,
  entries)` draws looks side and front; `docs/gallery/media/looks.png` (the screenplay looks and a
  kid, about 50 KB) is in CONFIG.md "Characters".
  Tests: `tests/test_cartoon_outfits.py` (sampled combinations from a seed, not every one).

### 69.48 Animal characters and the `tail` part (Step 114)

`look.species` (`config.Species`): `human` (default, unchanged) or `cat`, `dog`, `bird`, `bear`,
`rabbit`, `mouse`. Each is a plain generic animal from primitives in the look's colours, with no
feature taken from a known character (brief: no signature ear shape paired with a signature colour,
gloves, buttoned shorts, a bow on a mouse...). `ears`, `nose` and `facial_hair` other than `none`
with an animal are a config error (`config.SPECIES_OWN_KEYS`); `svg` with `species` is the usual
"svg draws the character" error.

- **Drawing** (`cartoon/animals.py`, called by the generator; side and front each): the head is an
  ellipse (`HEAD_SHAPES`; a mouse's drawn out into a snout from the side, `MOUSE_SNOUT`); ears
  behind it (cat triangles with a lining, rabbit long ellipses, mouse big ovals set back on the
  sides, bear rounds, a bird's crest of three feathers; a dog's long ears hang beside the head from
  the front and over its side from the side); on the face a muzzle (`fur_tint`: 50 % towards white
  on dark fur, 14 % towards black on light fur), a dog's snout, noses (`PINK` for cat, rabbit and
  mouse, the features ink for dog and bear), whiskers, a bird's beak (`BEAK_COLOR`). Ears, snouts
  and the beak are marked `OUTER_HAIR_ATTRIBUTE` (§69.47), so effect symbols size and place by the
  head and go above tall ears. Hands are round paws with two toe lines (`paw`); a bird's arms are
  `wing`s (feather colour whatever the sleeves, three darker feather tips at the hand point); a
  bird's bare shins (`limb_colors` gives skin) are thin and `BEAK_COLOR` with toes unless it wears
  shoes. Fixed natural colours (`BEAK_COLOR`, `PINK`) are like `EYE_WHITE`: not theme tokens.
- **Mouth**: `mouth_place` moves the human mouth (same shapes and numbers, scaled by a size) onto
  the muzzle or under the snout (`MOUTH_PLACES`, `FRONT_MOUTH_PLACES`); a human's place is the old
  one exactly. A bird's `mouth` part is `beak_mouth`: pivot the hinge; `smile` a line at the
  beak's corner, `M` the closed seam, `open` and the other visemes the beak opened by
  `BEAK_OPENINGS` degrees (both halves turned apart about the hinge over a dark fan; from the
  front a dark opening on the rhombus). Every shape is symmetric about the hinge's line, so the
  expressions' negative y scale (a frown) keeps an open beak the right way up while speaking.
- **`tail` part** (`PART_NAMES`, `PosePart`, `DEFAULT_PARENTS` body, `DEFAULT_DRAW_ORDER` 5 in
  both views; optional): `tail_part` roots it low on the back of the body (from the front behind
  the body, its end showing on one side), pivot the root; centre lines (`TAIL_LINES`, a
  Catmull-Rom `keyframes.path_curve`) turned into `primitives.tapered_band` (a band narrowing to
  a round tip); a bear's round stub, a rabbit's puff (`fur_tint`), a bird's fan of three
  feathers (`TAIL_FEATHERS`). Motion: `motion.follow_angles` gives `tail` −`FOLLOW_TAIL_DEGREES`
  45 × (forward + up) × strength, limited to ±30° (the Step 82 spring: back and down as the body
  sets off or rises, on past it as it stops or falls); `walking_state` swings it by
  `WALK_TAIL_SWING` 0.5 of the near arm's swing; the idle layer swishes it (`idle.tail_sway_angle`,
  ±2 × 5° every 2.6 s, 0 at the clock's start); wind trails it (`TRAIL_WEIGHTS` `tail` 0.8,
  `feathers` 0.4, a rabbit's `long_ears` 0.3; the bear's and rabbit's round tails do not trail).
  An SVG `id="tail"` is that part (default pivot: the bottom corner nearer the body; a
  `TURNING_PARTS` pivot warning), and `svg_character_parts` marks it trailing like a generated
  tail. Characters without a tail take the old code paths (their drawings, poses and idle state
  are unchanged; pinned in `tests/test_cartoon_animals.py` with the eight looks of
  `test_cartoon_outfits.py` and seven Step 113 looks).
- **Validate and tools**: `cast.character_part_shapes` adds `tail` for an animal (so part targets
  `tib.tail`, own poses and the character sheet know it); `vidgen character` prints `species` on
  the look line for an animal.
- **Voice kinds** (§69.25): an animal has no kind of its own (either suits it) unless the
  screenplay states one; the screenplay's `LOOKS` stay human (animals for undeclared characters
  are Step 115's `--species`).
- **Docs**: CONFIG.md "Animal characters (`species`)" and `docs/gallery/media/animals.png` (the six
  species side and front, `still.write_looks_png`, about 30 KB).
  Tests: `tests/test_cartoon_animals.py`.

### 69.49 A random, well-contrasted cast (Step 115)

- **Contrast score** (`cartoon/contrast.py`, no manim): `look_features(look, colors, theme)`
  reduces a generated look to `LookFeatures` (silhouette values; the clothes, skin, hair and
  accessory colours with theme tokens resolved, a bald head's hair colour taken as its skin and a
  look without accessories or shoes its accessory colour as its clothes, since nothing is drawn
  in them; a set of small details); `None` for an `svg` look. `contrast_score(a, b)` (pure,
  symmetric, 0 the same look .. 1) = `WEIGHTS` silhouette 0.45 + colour 0.4 + accessories 0.15 of
  `contrast_parts`: silhouette = `SILHOUETTE_WEIGHTS` (body 0.25, hair 0.2, species 0.15,
  headwear (hat / cap / bow) 0.1, proportions 0.1, head size 0.1 (|difference| / 0.4, capped),
  ears 0.05, outfit (dress / coat / other) 0.05) of the features that differ; colour =
  `COLOUR_WEIGHTS` (clothes 0.4, skin 0.3, hair 0.2, accessory 0.1) of CIEDE2000 in CIELAB
  (`lint.color.lab` / `delta_e`) / `COLOUR_SPAN` 30, capped at 1 (an unresolved token: 0 when the
  same name, else 1); accessories = the Jaccard distance of the detail sets (accessories other
  than headwear, facial hair, pattern, shoes, eyes, nose; both empty: 0). The weights favour what
  reads at stage size: outline first, then large colour areas. Calibration: the screenplay's 11
  `LOOKS` in `soft_pastel` score 0.49 to 0.84 against each other; a look and a copy with only the
  clothes colour changed far scores 0.16; the same silhouette in all-new colours about 0.4.
  `MIN_CONTRAST` (0.35) is the `look_alike` default.
- **Advice**: `compare(first, a, second, b) -> PairContrast(score, parts, shared, advice)`:
  `shared` lists the equal silhouette features (not the unremarkable defaults: no ears, plain
  outfit, nothing on the head, human, adult, head size 1) and the colours closer than
  `CLOSE_COLOUR` 10, ordered by their weight in the score; `advice` names the keys of the three
  heaviest (`give 'ben' another colors.clothes, colors.skin, look.body`).
- **Lint `look_alike`** (scene scope, in `lint/cartoon_rules.py`; `LookAlikeRule.min_contrast`
  0.35; default warning): `contrast.character_pairs(config, theme)` compares every two generated
  characters on the video's stages (any scene's `params.characters`, sets expanded), in the order
  they first appear, and ties each pair to the scene where the later one first appears. The runner
  (`_timing_findings`) fills `SceneContext.character_pairs` with that scene's pairs (the theme:
  `Theme.for_format` of the project) when the rule runs; the issue is at the scene's first beat,
  without objects (the names are in the message). Video-level, so one finding per pair, not per
  scene they share.
- **Generator** (`random_cast.py`, no manim): `random_look(rng, kind, species)` draws every
  generator value (bodies, head sizes 0.85..1.3, eyes, nose / ears for humans, hair (animals: none,
  short, spiky, curly), outfit, pattern, shoes, 0-2 accessories never hat with cap, facial hair
  for 40 % of masculine humans) and hex colours from fixed lists (`SKIN_COLORS` / `FUR_COLORS`,
  `CLOTHES_COLORS`, ...: the same in every theme), all through `Random(seed).random()` (`_pick`,
  `_shuffled`: the one call Python keeps stable, §69.1). `KIND_EXCLUDES` keeps a look suited to its
  voice kind (feminine: no facial hair; masculine: no dress, bow, bun, ponytail, braids; neutral:
  no facial hair, dress or bow). Adult proportions only (a kid needs the stage's `scale`, §69.47).
  `pick_looks(kinds, rng, species, existing, curated, theme)`: per character, first the first
  unused `curated` look of the kind (then neutral) whose `min_contrast` against `existing` and the
  picks so far is at least `MIN_CONTRAST`; else `CANDIDATES` (48) random looks and the one with the
  highest lowest contrast (greedy maximin; ties: the first drawn); a kind of `None` takes the voice
  kind picked least so far.
- **`vidgen cast --random N`** (`cli.cmd_cast`, MCP tool `cast`, `jsonout.cast_document`):
  `random_cast(count, seed, species, voice, language, taken)`: kinds from `balanced_kinds` (each
  round of three a shuffle of `VOICE_KINDS`), looks, names and voices each from their own stream
  (`Random(3 * seed)`, `+ 1`, `+ 2`), so `--random 5` starts with `--random 4`'s cast; names from
  `NAMES[kind]` (short common first names, none a famous character's; `_k` suffixes when a kind's
  list runs out); voices by `screenplay.assign_voices` (Kokoro by the kinds' genders, narrator
  `--narrator` default `bf_emma` left out; OpenRouter in turn; ElevenLabs labels and a TODO).
  Written with `plan_yaml.commented_yaml` (now also for a mapping without `scenes`): a header, the
  kinds and the lowest contrast above `characters:`, TODOs above `voices:`; each entry is checked
  with `CharacterEntry`. 1-24 characters (`MAX_CAST`); `.yaml` only; an existing file needs `--force`.
- **Screenplay** (§69.25): `_generated_looks` calls `pick_looks` with the stated kinds, the
  declared and cast characters as `existing`, `LOOKS` as `curated` (when `human` is among
  `--species`), the front matter's theme and `Random(--seed)`. Casts of up to 11 that do not
  collide with a declared character get the same looks as before; a look of `LOOKS` too like a
  declared one is skipped; after the 11 (and for a fifth stated "she", which took the first
  feminine look again with a seed before) come unused neutral looks, then random looks instead of
  repeats. `--species cat dog` (MCP `species`) gives only random animals. The voice kind of a
  random look is its drawn kind.
  Tests: `tests/test_random_cast.py`.

### 69.50 Review of Phase K (Step 116)

- **The indoor example**: `examples/cartoon-muffin-mystery` (an original screenplay,
  `muffin_mystery.md`, then hand-edited `video.yaml`): a `card` title and end card, `iris_in` /
  `iris_out` (closing on the dog), one `sets: home` room (stripes, boards, a window, a door, sofa,
  picture, clock, armchair at depth 0.2, rug, counter and fridge against the wall), a dog
  character (`species: dog`) and two people, `indoor` light fading to `night`, then `morning`;
  effect symbols (written and from `auto_direct`), `run_to`, `jump`, walks in depth behind and in
  front of the armchair and the others, `enter` / `exit` through the door, a basket held from the
  start, a close-up in the front view, captions and a music bed. End to end by the CLI and the
  MCP tools `screenplay` (also with a `cast` of dogs and people), `cast`, `validate`, `direct`,
  `lint`, `storyboard`, `character_sheet`; lint clean at preview (word-count timing) and with
  Kokoro audio. `tests/test_phase_k_review.py` repeats the cheap part.
- **`vidgen screenplay` without `--json` crashed on a silent card** (`KeyError: 'beats'`: a
  `card` scene with only `duration` has no beats); the summary now counts a card's beats as 0 and
  says "N scenes" (not "N stage scenes").
- **A prop held before its holder's entrance flew across the set**: `hold` at `at: 0` by a
  character that waits off stage for an `enter` moved the prop from its own spot into the hand off
  stage, in view (and it stood there through the set's fade-in). `Stage._held_before_entering`
  finds the props a `hold` gives to a character of `_entering()` before its first `enter` (in the
  order the scene's actions are written); the construct puts each beside its holder off stage, so
  the hold plays unseen.
- **A held prop did not fade through a door**: `Walk`'s `fade_in` / `fade_out` (§69.42) now scale
  the props in `carried` with the character; `enter` / `exit` with `door` pass the props the
  character holds (`moving._carried`, also used by walks in depth).
- **Turning to the front kept a look's head angle**: from the side the head angle is a nod; in the
  front view it rolls the head sideways (seen after `look_at` a held basket, then `turn: front`).
  `turn` `to: front` now ends with `camera_look("front")` (head straight, eyes in the middle), and
  `look_pose` facing the front (a point straight above or below) keeps the head upright and moves
  only the eyes up or down.
- **Real narration**: Kokoro (narrator `bf_emma` 0.8, Mira `af_heart` 0.75, Olen `am_fenrir`
  0.75, the dog `bm_fable` 0.8; `narration_speed` warned at 3.52 words/s for Mira at 0.8), rendered
  at 1280x720 (`/home/claude/work/phase-k-review/muffin_mystery.mp4`, 69.9 s, −16.2 LUFS).

### 69.51 Props that vanished, overlapped or showed through (after Step 116)

- **Props vanished during a walk in depth** (the example at 0:12: the door, picture, sofa,
  counter, basket and fridge went while Mira walked from the wall to the front). Manim draws the
  mobjects before the first moving one once into a static image when an animation begins, and the
  rest (`moving_mobjects`) on every frame. `get_moving_mobjects` (§69.44) makes everything from
  the first thing a walk in depth passes "moving", measured from the walker's depth *now*. The
  draw-order updater (`_draw_order_step`) rebuilt that list mid-play when the walker crossed the
  armchair; by then the walker had left the wall's depth, so the props there were no longer passed
  and dropped out of the list, while they were not in the static image either: drawn by nothing
  until the next animation. The camera did not move. Now `Stage._moving_in_order` keeps
  everything the list had and adds what moves now, in the current draw order; a rebuild never
  drops a thing. Test: a render where every frame's moving list plus static image holds every
  prop on the stage (`test_props_at_the_depth_a_walker_leaves_stay_drawn`, fails before).
- **`prop_overlap` lint rule** (warning, `min_overlap` 0.15 of the narrower prop's width): two
  props standing on the floor at depths less than `DEPTH_APART` (0.15) apart whose boxes overlap
  side by side, e.g. a room's door over the sofa against the wall. Props in front of others
  (further apart in depth), lifted (`lift`) or hanging on a wall (a picture over the sofa), lying
  flat (a rug) or held are left out. The layout dump gains on a prop: `prop` (its kind), `depth`
  (above 0), `raised` and `flat` (only when true); `Prop.raised` is set by the stage from
  `lift` + the hang height. A still rule, like `character_overlap`, so it sees the props where they
  are drawn (a door's width, an open door); the runner merges a pair's findings over the beats.
  The example's layout was fixed with it (door at 0.13, the sofa at 0.325 and scale 0.9, the
  picture at 0.26; the counter at 0.745 and the fridge at 0.925 overlapped too).
- **The set fades in as one picture**: the stage's entrance faded each thing in on its own, so
  during the fade (and under an `iris_in` that opens meanwhile) what stood behind showed through
  what stood in front (the dog over the armchair, the door over the sofa). The entrance now adds
  the set, props, shadows and characters at once, back to front, under `Stage._cover`: a
  rectangle of the camera's background colour, 1.5 times the view and kept on it, that fades out
  over the same time. Every frame of the fade is the finished picture blended with the background
  by one amount (`test_the_set_fades_in_as_one_picture`). A copy carried from the scene before
  (`carry:`) still moves in. Since Step 127 the scene's fade out is one picture too:
  `Stage.finish` fades the same kind of cover in over everything (its z index above all, so
  particles, bubbles and symbols go under it as well) instead of `clear_all` fading each thing (a
  character behind a house showed through the fading house as a faint outline). With a
  transition other than a cut the picture is held as before; when the next scene carries a
  target out (`carry:`) the outro stays `clear_all(keep=)`.

### 69.52 Vehicles on the ground (Step 118)

Characters get in a car or a bus, or on a bicycle, ride it somewhere and get out. A vehicle is a
built-in prop (§69.8), so placing, `scale`, `facing`, colours, depth, shadows, the light, the
layout dump and the prop checks work as for any prop; riding is a posture like sitting (§69.28).

- **Geometry** (`cartoon/vehicles.py`, no manim): `VEHICLES` kind → `VehicleSpec` (prop units as
  drawn facing right, built by `_spec` from measures in a character's heights): `height` next to
  a character (bicycle 0.38, car 1.12, bus 1.45; `PROP_HEIGHTS` reads them), `seats` (each
  place's hips x, front first: 1, 2, 4 places), the `seat` line and the `floor` under the riders'
  feet (car 0.2 / 0.08, bus 0.44 / 0.3, bicycle 0.255 / 0), `wheels` (x, y, radius: every
  wheel stands on the ground), `half_length`, `hides_legs` (car, bus), default `speed` (bicycle
  and bus 4, car 5 units/s), a bicycle's `crank` and `grip`. The car's and bus's seat lines put a
  seated head (about 0.8 above the hips) under the roof, the floor behind the side. Pure
  functions: `seat_origin`, `seated_height`, `get_in_gap` (beyond the nearer end),
  `place_order` (nearest seat first), `wheel_degrees(forward, radius)` (clockwise going forward,
  one turn per circumference), `crank_degrees` (÷ `GEAR` 2), `pedal_points(kind, angle)` (the
  two pedals opposite on the crank circle), `ride_facing`. A ride's time is a walk's
  (`walk_seconds`: eased over 15 % at each end) at the vehicle's speed; in depth it goes as far
  as a walk in depth (`depth_walk_distance`, a unit of depth = 2 heights of a character there).
- **Drawings** (`cartoon/vehicle_drawing.py`): side on, the front on the right, primitives in
  the prop's two colours (`PROP_COLORS`: bicycle primary / accent, car accent / highlight, bus
  highlight / primary) plus shades, dark tyres (`TV_CASE`), fixed light hubs and headlights.
  Original simple shapes; nothing imitates a known make or model. Windows are see-through glass
  (`GLASS_OPACITY` 0.3) between filled pillars, so riders drawn *before* the vehicle show in them
  while its lower side hides their legs. Drawn in character heights, then scaled to prop units;
  wheel and crank places come from the spec (one source). `draw_prop` returns a `Prop` with an
  anchor and `wheels` (each wheel's spokes or bolts group and its axle) and a `crank`;
  `Prop.turn_wheels(degrees)` rotates them about their axles (mirrored when facing left) and
  keeps `wheel_angle` / `crank_angle`; `Prop.prop_point(x, y)` and `Prop.unit` map prop units to
  the screen. Gallery: `write_props_png(..., kinds=VEHICLE_KINDS, columns=3)` →
  `docs/gallery/media/vehicles.png` (720×240, 10 KB) in CONFIG.md "Vehicles"; `props.png` leaves
  the vehicles out (byte-identical).
- **Riders** (`cartoon/riding.py`): never added to the vehicle (§69.22's fixed family; the
  vehicle's box stays its own). A `RiderSeat` (rider, vehicle, place, `ratio` = rider height /
  vehicle unit) and `place_rider` put the rider's feet on its seat's floor point where the
  vehicle is now, at `ratio` × the vehicle's unit (growing and shrinking with it in depth), facing
  its way, with its `stage_depth` / `ground_y`. An updater on the rider calls it every frame
  while it rides; `Ride` calls it too (Manim pauses an animated character's updaters).
  `riding_state` seats the rider (`Character.seated` on the seat above the floor); on a bicycle
  it also leans forward `CYCLING_LEAN` 14°, plants the feet on the pedals (`Character.planted`,
  the two-bone solver of §69.26; legs too short reach towards them) and reaches both hands to the
  grip. `Ride(vehicle, x, seats=, speed=, depth=, feet_y=, strength=)` turns the vehicle round
  at once to face the way it goes (riders with it), moves its feet along `walk_progress`, scales
  it about its feet in depth (like `Walk`), turns the wheels by the way gone and re-plants a
  cyclist's feet every frame. `BodyMove(y=)` eases the feet's y too (getting in climbs to the
  floor, getting out steps down).
- **Actions** (`scenes/riding.py`, against `vidgen.api`): `get_in` (characters; `to` a vehicle;
  1.0 s): each takes the nearest free seat (`Postures.ride`), faces the vehicle, a `BodyMove` to
  its seat with the riding posture (arms too on a bicycle), the follow updater, `Character.riding`,
  and is drawn right before a car / bus (behind its side) or right after a bicycle (on it).
  `ride_to` (a vehicle, or a character: the vehicle it rides; `to` a place or `{mark, depth}`,
  `depth`, `speed`): a `Ride` per vehicle; a ride in depth registers with `Stage.ride_in_depth`.
  `get_out` (0.9 s): the updater off, `Postures.get_out`, a `BodyMove` back to the saved body,
  legs and arms with the feet on the ground, drawn right after the vehicle (stepping out towards
  the camera). Riding counts as posed (`is_posed`): looks turn only the head, poses move only
  the arms and head.
- **Stage** (`scenes/stage.py`): vehicles are movable props when a `ride_to` is used (their
  shadow follows; `ShadowCaster(grows=True)` with `Prop.standing_height`); a rider casts no
  shadow (`ShadowCaster` treats `riding` like `held_by`). The draw-order keeper of §69.44 moves a
  vehicle with its riders and their held props as one block (`_moving_block`) and redraws what a
  ride in depth passes (`_depth_crossers` knows `Ride`). Mid-action stills cover the three actions.
- **Validate** (`holding_problems(vehicles=)`, `StageFrame.vehicles`): `get_in` too far beyond the
  vehicle's end (`GET_IN_REACH` 0.5 heights) or at another depth, with the `walk_to` that fixes
  it; a full vehicle ("'car' is full: it has 2 seats and pip, kit ride it then; get_out one
  first"); a `ride_to` of a character that rides nothing; `get_out` without `get_in`; the
  pinned actions (§69.28) and `stand_up` / `sit_on` / `lean_on` while riding ("pip rides 'car'
  then; get_out first (- get_out: pip)"); `pick_up` / `hold` of a vehicle; `keyframes` /
  `move_along` of a ridden one. The replay moves riders and vehicles (and their depths) with each
  ride. `scene_problems`: `to` / targets that are not vehicles, naming the stage's vehicles.
- **Foley and motion effects**: `PlayedAction.vehicle`; `ride_cues`: a bicycle's `bell` as it
  sets off, a car's / bus's `engine` (pitch −5 for the bus) for `ENGINE_SHARE` 0.8 of the ride
  (0.8–6 s), `brakes` ending at the stop (`RIDE_SOUNDS`, `BRAKES`). Three new generated sounds in
  `sfx.py` (`bell`, `engine`, `brakes`; nothing downloaded). `motion_effect_cues` treats a
  `ride_to` like a walk (its `heights` in the heights of a character beside the vehicle): dust
  at the vehicle's back end as it sets off and its front end as it stops, speed lines from its
  back end, from `FAST_SPEED`.
- **Planner, reframe, shots, follow**: `_follow_written` replays `get_in` / `ride_to` /
  `get_out` (`_riding`): riders' x and facing follow their vehicle, so automatic looks, close-up
  checks and `reframe` pans see them where they are; the three actions are `LOOK_CHANGING` and
  `MOVING_ACTIONS`. `follow` of a vehicle (its box) or a rider (its feet) keeps the camera on
  it during the ride. A beat's `shot` is framed where the riders are when the beat starts.
- **Lint and layout dump**: layout key `riding` on a character; `character_overlap` and
  `walk_overlap` skip two riders of one vehicle; `hidden_speaker` does not count a rider's own
  vehicle as covering its face.
- **Checked by eye** (scratch projects at preview 854×480, `vidgen storyboard`): two riders
  getting in a car (heads in the windows, legs hidden), the car riding right then to depth 0.7
  behind a tree (shrinking, riders with it) and both getting out in front of it; a cyclist (a
  tall look) on the saddle, leaning to the handlebar, feet on the pedals, riding right and back
  left (the bicycle turning round); four characters (one a cat) getting on a bus facing left, the
  bus turning and riding right with dust and speed lines; the CONFIG.md example. `vidgen lint`:
  only the scratch cast's own `look_alike`.
- **Not done here**: no door opening; a shot does not follow a ride within its beat (as for
  walks); a rider's feet show under a car's side for a moment while it climbs in; a prop a rider
  holds follows its hand but keeps its size during a ride in depth; no vehicles in the
  screenplay grammar; water and air vehicles are Step 119 (§69.53). Tests:
  `tests/test_cartoon_vehicles.py`.

### 69.53 Vehicles on the water and in the air (Step 119)

A `boat` rides along a strip of water, a `hot_air_balloon` rises, drifts with the wind and lands,
and a `toy_rocket` launches with smoke and floats down under a parachute (or flies off). They are
vehicle props like those of §69.52 and reuse `get_in` / `ride_to` / `get_out`, seats, riders on
updaters and the validate replay; only where they go differs.

- **Geometry** (`cartoon/vehicles.py`): `VehicleSpec.medium` (`ground` / `water` / `air`;
  `GROUND_VEHICLES`, `WATER_VEHICLES`, `AIR_VEHICLES`, `medium(kind)`) and `.stands` (riders stand
  on the floor instead of sitting: `riding_state` returns the standing state). `boat` 0.58 of a
  character tall, 1.9 long, 2 seats behind its side (seat line 0.2, floor 0.05), speed 2.5;
  `hot_air_balloon` 2.1 tall, 2 riders standing in the basket (rim 0.5), speed 1.2; `toy_rocket`
  0.55 tall, no seats (a toy: `get_in` to it is refused in `scene_problems`), speed 6.
  `ROCKET_ASCENT_SHARE` 0.3 lives here (foley and paths share it). No wheels: `Ride` turns
  wheels only for ground vehicles.
- **Paths** (`cartoon/vehicle_paths.py`, pure, seeded): `Course(kind, start, end, rise, drift,
  land, seed).at(share)` → the feet (x, y) and a turn (degrees about the feet). Ground and water:
  straight, eased like a walk. `balloon_point`: rises `rise` over `BALLOON_RISE_SHARE` 0.3 of the
  time while starting across (`smoothstep` up, cruise, `smoothstep` down to land at `end`), a
  gentle seeded float (5 % of the altitude, twice) and a `drift` bulge `drift·sin(πs)` (largest
  half-way, 0 at both ends, so it still lands at `to`); `land=False` keeps rising to `end` above
  the frame. `rocket_point`: up an arc `x0 + across·v`, `y0 + apex·(2v − v²)` (`across` = 0.5 of
  the way, `v` = 1 − (1 − u)², slowing to the top) over `ROCKET_ASCENT_SHARE`, the nose along the
  tangent (blended in from upright over the first 30 %, level at the top), then down to `end`
  (`smoothstep`) turning upright over `CHUTE_TURN` 0.25 and swaying `CHUTE_SWAY` 9° less and
  less; `land=False`: `x0 + dx·v²`, `y0 + dy·v`, `v = s^1.6`, nose along the tangent.
  `balloon_seconds` (way across + up and down at its speed), `rocket_seconds` (1.8 s landing /
  0.6 s away plus the way at its speed). Water: `wave_offset(x, t, sign)` (two drifting sines, at
  most `WAVE_HEIGHT` 0.035 character heights), `front_outline`, `boat_bob(t, phase)` (±0.025
  character heights every 2.4 s, ±2.5°), `bob_phase(name)`. Smoke: `smoke_puffs(age, course,
  seconds, size, seed)`: `SMOKE_BURST` 6 puffs rolling out both ways on the ground where it set
  off, `SMOKE_TRAIL` 12 left where its tail was while the motor burns (`Course.powered()`: the
  ascent, or 0.7 of a flight away), each growing and fading over `SMOKE_SECONDS` 1.1 s.
- **Drawings** (`cartoon/vehicle_drawing.py`): a small open boat with an outboard motor at the
  stern, a stripe and a dark gunwale; a balloon with a round envelope in two bands of gores
  narrowing to its mouth, ropes, a burner and a wicker basket; a toy rocket with fins, a pointed
  nose, a round window and a dark nozzle, in two shapes (`PROP_SHAPES["toy_rocket"]`: `folded`,
  `chute`, its parachute open on four lines above it; `VehicleDrawing.shapes`). Every vehicle
  prop now has an anchor; `Prop.pose_at(x, y, degrees)` undoes its `tilt` about the feet and sets
  place and turn afresh. Original shapes; the rocket is a toy, not any real craft. Colours:
  boat highlight / accent, balloon accent / secondary, rocket primary / accent. Gallery:
  `docs/gallery/media/vehicles.png` now 960×480, 4 columns, 7 cells (the rocket twice).
- **Water** (stage param `water: true | {left, right, color}`; `cartoon/water.py`
  `StageWater`): a band from the frame's bottom to `WATERLINE` 0.12 character heights above the
  ground line, between `left` and `right`, in the backdrop after the ground band; a front strip
  with a wavy top `FRONT_DROP` 0.05 under the surface and a light crest line, put first in the
  foreground (in front of the boats, over their keels). A scene updater (`_water_step`) moves the
  waves and bobs each boat about where it rests (`Prop.afloat`), re-placing its riders after
  (the riders' own updaters ran before it in the frame). Waves drift right, left when the stage's
  `wind` is negative. `get_moving_mobjects` redraws from the first boat on (front strip, boats,
  riders). Boats cast no shadow. Params checks: a boat needs water, its `at` on it, depth 0;
  `water`, a boat, a balloon or a rocket in a `room` is refused ("stays outdoors").
- **Rides** (`Ride(..., rise=, drift=, away_y=, seed=)`): a boat starts from `afloat` and
  updates it; a flying vehicle's `Course` is built in `begin` (and in `__init__` for the run
  time) from `prop_point(0, 0)`; `interpolate` calls `pose_at` on the course; a rocket shows its
  `chute` from the top of a landing flight and `folded` at the touchdown. `Ride` leaves
  `(course, seconds)` on `Prop.flight`. `RideTo._flight` (`scenes/riding.py`): the rise wanted
  (`BALLOON_ALTITUDE` 0.3 / `ROCKET_APEX` 0.45 frame heights) capped so the top (a rocket with
  its parachute: 2.2 × its height) stays `FLIGHT_MARGIN` 0.04 under the frame's top, at least
  `LOWEST_RISE` 0.12; the drift `BALLOON_DRIFT` 1.2 character heights × the stage's wind level
  then (balloon only); `land: false` → `away_y` above the frame (vehicle height + 0.3); seed from
  the scene and the vehicle's name.
- **Validate** (`holding_problems(water=)`, `StageFrame.water`): a boat's `to` off the water;
  `depth` for a vehicle not on the ground; `land: false` for one not in the air; anything a later
  action does with a vehicle that flew away or its riders ("'kit' flew away out of the frame
  (...); it is gone for the scene"). The planner (`_riding`) marks them gone too.
- **Foley and motion effects**: `RIDE_SOUNDS` boat `engine` (pitch +6, no brakes), balloon
  `burner`, rocket `launch`; with `PlayedAction.lands` (a landing flight) a rocket's parachute
  `pop` at `ROCKET_ASCENT_SHARE` and a soft `thud` at the touchdown (`TOUCHDOWN`). Two new
  generated sounds in `sfx.py` (`burner`, `launch`; 21 → 23). `motion_effect_cues`: no dust or
  speed lines on the water or in the air; a rocket's `smoke` cue (a new `MOTION_EFFECT_KINDS`
  kind, drawn behind it by `MotionEffect._smoke` from `Prop.flight`, the `smoke` particles'
  colour).
- **Checked by eye** (scratch project, preview 854×480 storyboards): two riders climbing into a
  boat on water from 0.35, motoring right, bobbing with waves crossing its keel; a balloon at
  `size: 0.3` in a `windy` stage taking two standing riders up, drifting and landing at 0.75,
  then both getting out; a toy rocket launching with a smoke burst and trail, its parachute
  opening at the top, landing upright, and a second one flying off the top of the frame.
- **Not done**: the boat's ends are not checked against the water's edges (only its middle);
  `get_out` of a balloon puts the riders in front of the basket like a car's; no water in depth,
  no splash, no riding in depth on water or in the air; the balloon does not lean with the wind;
  smoke does not drift with the wind; a balloon's riders are as tall as on the ground, so the
  balloon is 2.1 characters tall (authors use a small `size`). Tests:
  `tests/test_cartoon_water_air.py`.

### 69.54 Props that move by themselves, indoors (Step 120)

A wall `clock` runs, a `tv` shows a flickering picture and a `lamp` glows. They are the props of
§69.8 / §69.43 drawn with a few extra parts; every other prop, and these three while they never
run or come on, are drawn exactly as before.

- **Maths** (`cartoon/living.py`, no manim): `parse_clock_time` (`H:MM` / `H:MM:SS`, 0:00–23:59:59),
  `clock_seconds(start, speed, t)`, `hand_angles(seconds)` → `HandAngles(hour, minute, second)`
  in degrees clockwise from twelve (the hour hand twice round a day, moving between hours),
  `hand_tip`, `shows_second_hand(speed)` (up to `SECOND_HAND_MAX_SPEED` 10), `DRAWN_CLOCK_SECONDS`
  (10:10, the drawing), `MAX_CLOCK_SPEED` 3600. Switches: `switched_on(on_at_start, switches, t)`
  (the last `(time, on)` at or before `t` wins), `switch_between`, `on_between`. A television's
  picture: `tv_shot(t, seed)` (picture `k` starts near `k` × `TV_SHOT_SECONDS` 1.8 s, moved by up to
  ± `TV_SHOT_JITTER` / 2, so they stay in order), `tv_flicker(t, seed)` (1 − `FLICKER_DEPTH` 0.22 ×
  u², a new u every `FLICKER_STEP` 1/12 s), `tv_picture` → `TvPicture(shot, colors, brightness)`
  from `TV_PALETTES` (six sets of sky, ground and two shapes; no programme of any kind). Glows:
  `GLOWS` (lamp: warm `#FFD67A` about the lantern, radius 0.42 prop units, 0.55 at the middle; tv:
  cool `#A8D8FF` about the screen, 0.8, 0.3), `glow_rings(radius, opacity)` (`GLOW_RINGS` 12 equal
  discs whose stacked opacity is `opacity` at the middle), `glow_box`, `union_box`,
  `boxes_overlap`, and `redrawn_members(boxes, regions, margin)` (below). Seeds are
  `random.Random` of a text key, the same in every run.
- **Drawing** (`cartoon/living_drawing.py`): `draw_prop(kind, ..., living=True)` (for `clock`,
  `tv`, `lamp`: `LIVING_KINDS`) adds `living_overlays` after the drawing and an anchor
  (`Prop(anchored=True)`): a clock's red second hand (`SECOND_HAND`), a tv's picture over its
  screen (four members, the first outlined like the screen), a lamp's lit lantern and core. The
  clock's hour and minute hands are tagged in its drawing (`LIVING_PART`); the overlays lie inside
  the prop's box, so its feet, size, shadow and layout dump are unchanged. A `LivingProp(prop,
  start, speed, on, seed, movable)` sets them for a scene time (`update`): the hands from the
  screen position of the clock's middle (`prop_point`), so a clock facing left still runs
  clockwise; a tv's picture colours darkened by the flicker; the overlays shown (their drawn
  opacities) or hidden (0). A `PropGlow` (the rings) is a mobject of its own, placed by the
  prop's anchor, drawn right before the prop, never graded by the light (§69.31); the lit
  overlays are not graded either (`LIT` cleared), the hands are. The layout dump leaves glows out.
- **Stage** (`scenes/stage.py`): prop keys `on` (`tv` / `lamp`), `time` and `speed` (`clock`;
  a clock with either runs: `StageProp.runs`, `clock_start`), each a config error on other props.
  YAML 1.1 reads a bare key `on` as `true`; `StageProp` takes that key as `on`. `_living_names`:
  running clocks, and tvs / lamps that are `on` or named by a `switch_on` (glob patterns too);
  only those are drawn `living`. `_start_living` makes the `LivingProp`s (after `mark_lit`; seeds
  from `motion_seed(scene, name)`; `movable` from `_movable_props`) and a scene updater
  (`_living_step`) that updates them on every frame; the entrance adds each glow right before its
  prop. `switch_props(patterns, on, time)` records the switches and plays a `click`
  (`SWITCH_CLICK_GAIN` −4 dB) with foley.
- **Actions** (`scenes/switch_action.py`): `switch_on` / `switch_off`, non-animating like `light`
  (cued at `at` when the beat starts, at once); `scene_problems`: not a prop, or a prop that does
  not switch ("'sofa' cannot be switched on or off (props that can: lamp, tv)"), or not a stage.
- **Only the moving parts leave the static image** (§69.20): `get_moving_mobjects` ends with
  `_living_redrawn`. For each `LivingProp` that changes during the animation (`changing(start,
  end)`: a running clock always; a tv while on; a lamp only when a switch falls in it, or while on
  if an action may move it) its movers (the hands; the picture or lantern and the glow) are
  redrawn on every frame, and so is every family member drawn after the first mover whose box
  overlaps a mover's region (the prop's box with its glow, + `REDRAW_MARGIN` 0.006 frame heights
  for outlines) or the box of a member already redrawn (`redrawn_members`: a member redrawn over
  the static image would otherwise cover what lies on it). Everything else, before or after,
  stays in Manim's static image; Manim's own moving list (characters with idle motion, from the
  first of them on) is kept as it was. The result is in draw order.
- **Measured** (scratch room at preview 854×480, 15 fps, 266 frames, no audio, one process per
  run under the 1500 MB cap; a sofa, a picture, a clock, a tv, a lamp, an armchair, a rug, a
  door, a window, two characters, `light: night`; Cairo draws counted around
  `Camera.display_vectorized`, raw frames hashed):

  | render | Cairo draws | drawing (s) | wall (s) | CPU (s) |
  |---|---|---|---|---|
  | HEAD 118b1b9 (props as drawn), 3 runs | 20 358 | 2.88–3.09 | 6.60–6.91 | 7.73–8.23 |
  | this step, same scene | 20 358 | 3.41 | 8.82 | 10.07 |
  | this step, clock running (`speed: 1`, second hand), tv and lamp `on` (lamp glow 0.34 then), 3 runs | 32 665 | 4.66–4.92 | 10.50–10.77 | 11.63–11.95 |
  | the same, everything from the first moving part redrawn (for comparison) | 34 171 | 4.71 | 9.61 | 10.92 |
  | final glow size, alternating with the plain scene (2 pairs): plain | 20 358 | 2.83–2.84 | 7.27–7.49 | 8.44–8.64 |
  | final glow size, alternating: everything on | 32 665 | 3.90–4.38 | 8.97–9.83 | 10.21–10.88 |

  The scene with nothing on gives the same raw frames as HEAD (all 266 hashes; the 8.8 s run
  was on a busier machine: two HEAD runs with hashing took 7.6 and 8.7 s). With everything on, 46
  more draws a frame on average: the hands (3), the tv's picture (4) and glow (12 rings) on every
  frame; the lamp's glow (12) and lantern (2), which stand after a character sitting at the wall
  and so are redrawn with it anyway; the rest in the fade in and out, where everything is drawn.
  A logging run shows the overlap rule added nothing else in this room (no member after the clock
  or the tv overlaps them before the first character). In the alternating pairs, drawing +1.1 to
  +1.5 s (the glows are large translucent discs) and wall +1.7 to +2.3 s (+23 to +31 %) for
  17.7 s of video; the earlier runs (+1.7 s drawing) were on a busier machine. Against redrawing everything from the clock on, the rule saved
  1 506 draws here (the tv's body, the door...); both give the same frames. A lamp that stays on
  and stands before every moving thing stays in the static image (render test).
- **Checked by eye** (scratch projects, preview stills and frames): a night room with the lamp
  switched on in beat 2 (glow on the wall and window behind it, lantern lit), the tv switched on
  in beat 3 (picture, cool glow), the lamp off in beat 4 with the tv still on, a clock at 23:55
  running a minute a second; a second room with a clock at 21:40 in real time (the second hand
  sweeping), a tv and a lamp on from the start. `vidgen lint`: 0 findings.
- **Not done**: the room's own light does not change with a lamp (no light falloff, no lit
  characters: the glow lies behind the lamp); a carried lamp's glow follows it but keeps its
  place in the draw order; no fade when switching (at once); a tv has no sound; the clock does
  not strike. Tests: `tests/test_cartoon_living.py`.

### 69.55 Props that move by themselves, part 2: fire, steam, nature (Step 121)

A `fireplace` burns, a `kettle` steams, a tree drops fruit and birds cross the sky. All of it is
seeded and pure (the same in every render) and nothing changes for a scene that uses none of it.

- **Fire and steam** (`cartoon/living.py`, no manim): `flame_shapes(t, seed, lean)` → 5 outer
  and 3 inner `FlameShape`s (closed outlines in prop units: widest a fifth of the way up, pointed,
  the middle bending to the tip); each height × (1 + `FLAME_FLICKER` 0.28 × noise), the tip
  wavering by `FLAME_WAVER` 0.035 × noise, where the noise is three seeded sines of 1.3–5 Hz
  (`_noise`, terms cached). `flame_lean(force)` = `FLAME_LEAN` 0.22 × felt force, at most
  `FLAME_LEAN_MAX` 0.3. `fire_flicker(t, seed)` ∈ [0.75, 1]: the glow's strength. `GLOWS`
  gains the fireplace's (`#FFA94D`, radius 1.05 prop units about (0, 0.32), 0.5).
  `steam_puffs(t, seed, lean)`: `STEAM_PUFFS` 6 puffs, each rising `STEAM_RISE` 2 prop units over
  `STEAM_SECONDS` 2.2 s from `STEAM_SPOUT` (0.66, 0.68), one after another (seeded jitter),
  growing from radius 0.08 to 0.3, swaying, drifting away from the spout, opacity
  `STEAM_OPACITY` 0.85 × min(1, 8 age) × (1 − age)^1.3; the felt wind force (at most
  `STEAM_LEAN_MAX` 1.2) pushes them aside × age². `steam_box(lean)` bounds them.
  `on_spans(on, switches, end)`: when a prop is on. `SWITCHED_PROPS` = fireplace, kettle, lamp, tv.
- **Drawing** (`cartoon/props.py`, `cartoon/living_drawing.py`): `fireplace` (furniture, 0.75 of a
  character; `dim` bricks, `secondary` mantel, a sooty arched hollow `HEARTH_HOLLOW`, two
  `LOG_WOOD` logs in front, `FIREPLACE_FRONT` 2) and `kettle` (0.15; `accent` / `dim`; spout up to
  the right). Drawn `living`, a fireplace gets 8 flame members (`LIVING_PART` `flame`, orange
  `#F2762E` edged `#C9472A`, yellow `#FFD25A` inner ones) inserted before its front logs.
  `LivingProp` burns them (`_burn`: all outlines through `closed_curve`, a vectorised Catmull-Rom
  to Manim's cubic points, 0.7 ms a frame instead of 5 ms with `set_points_smoothly`, then one
  `Prop.prop_points` for all), flickers the glow, and for a kettle places a `PropSteam` (6 discs
  `#F4F6FA` with a faint `#AEB9C6` edge, so steam shows on a pale sky) drawn right after the
  kettle and graded by the light (the flames and the glow are not). `LivingProp(wind=)` is the
  stage's felt wind force (`Stage._felt_wind`) for a fireplace or a kettle when the stage's wind
  may blow, else `None`. `changing`: a fireplace or kettle while on; `region(start, end)` adds
  the glow box and the steam's box (both ways with wind).
- **Fruit** (`cartoon/nature.py`): `FRUIT_SPOTS` (4 spots on the crown, prop units),
  `FRUIT_RADIUS` 0.034, red `#D9473B`. `draw_prop("tree", fruit=True)` (stage key `fruit`, trees
  only) appends stalk, skin and shine per fruit, each tagged `FRUIT_INDEX`; the tree's box is
  unchanged. A drop: `drop_timing(fall, bounce)` (frame heights; `FRUIT_GRAVITY` 3.2 frame heights
  / s²; the fall √(2h/g), the bounce 2√(2b/g); `impact` = the fall's share), `drop_point(u,
  start, impact, end, hit_share, bounce)` (y ∝ time² to the impact, then a parabola `bounce`
  high to `end`, turning `BOUNCE_TURN` 100° the way it rolls), `fruit_to_drop(left, near_x,
  xs)`. `Stage.drop_fruit(tree, onto)` (the `drop_fruit` action): hides the tree's fruit (opacity
  0; the tree stays in the static image), adds a `FallenFruit` (copies at their drawn opacities,
  moved by its skin's middle, `grip_point`) right after the tree (and after the character it
  hits) and plays a `FruitDrop` (a `PropMove` with `path`, `lands_at` = the impact: the `thud`
  of §69.27's foley; speed lines as for a thrown prop). Without `to` it falls from its spot to the
  tree's ground line and bounces `GROUND_BOUNCE` 0.05 frame heights, `GROUND_ASIDE` 0.04 away
  from the trunk. With `to: <character>` the fruit nearest above the head (`head_box`'s top)
  falls on it, bounces `HEAD_BOUNCE` 0.12 and lands `HEAD_ASIDE` 0.4 of the character's height
  beside its feet, and `hit_stars` (Step 107's `stars` symbol, hidden until `FruitDrop` sets its
  age to 0 at the impact, `HIT_STARS_SECONDS` 1.6 s, then shrinking, `done`) circles the head; it
  goes into `Stage.motion_effects`, so the sweep takes it off. No fruit above the head: it falls to
  the ground. Validate: a target that is not a tree or has no fruit, `to` not a character, a
  fifth drop of a tree (`_fruit_count_problems`, in `action_sequence_problems` before its early
  return).
- **Birds** (`cartoon/nature.py`, `cartoon/nature_drawing.py`): `flock_birds(count, seed)` (a
  loose V: rank `RANK_BEHIND` 1.3 spans behind, `RANK_ASIDE` 0.55 up or down, seeded jitter, size
  0.85–1.15, wing beat 3–4.2 Hz), `wing_lift(t, bird)` (a sine with a glide `GLIDE_SHARE` 0.3 of
  every `GLIDE_SECONDS` 2.6 s, wings held at 0.3), `bird_outline(lift, span)` (five corners: a
  V up, an upturned V down), `flock_plan(start, seconds, direction, left, right, y, span, count,
  seed, frame_width)` (default seconds: `FLOCK_SPEED` 0.2 frame widths a second over the stage and
  a margin of the flock's length each side), `bird_place(plan, k, t)` (`None` outside its time),
  `flock_box(plan, start, end)` (24 samples). `Flock` (two `wing_curve` cubics per bird,
  `BIRD_INK` `#2E3440`, stroke 9 × span, at least a pixel; `update_to(t)`) is graded by the light
  and drawn right after the sky (`Stage._sky_end`: the backdrop's background and stars), behind
  the layers, ground, props and characters (`_put_in_sky`: into the backdrop before the set comes
  in, else into the scene). Stage param `birds` (`StageBirds`: `true`, a count, or {count,
  direction, height (0.5–0.97 of the frame height, 0.8), start (0.5 s), seconds, seed}) and the
  non-animating action `birds` (`FlockSettings`; a number target is the count; cued at `at`),
  both refused in a room. Default seed `motion_seed(scene, "birds", k)`.
- **What is redrawn** (§69.54's rule, generalised): `_living_things` = the living props and the
  flocks; each has `changing(start, end)`, `movers()` and `region(start, end)` (a flock: the box
  of its birds during that time). The scene updater `_living_step` updates both (installed for a
  living prop, or by `add_flock`) and removes itself once only flocks that have flown are left.
- **Sound** (`ambience.py`, `mix.py`): `fire_loop()` (8 s stereo, numpy, `crc32("ambience:fire")`:
  a roar of noise around 220 Hz with a 3-cycle breath, 9 crackles a second and 1.5 pops a second,
  impulses ringing 4 ms (`_ringing`, circular) band-passed at 3 kHz and 1.2 kHz, circular filters)
  at `FIRE_LEVEL` −34 LUFS. `BEDS` holds each bed's loop, duck (fire: `RAIN_DUCK`) and fades (fire
  0.6 / 0.8 s); `plan_ambience` places every bed of `AMBIENCE_BEDS` (rain, fire) the same way
  (rain unchanged). `Stage.timings()` adds `{bed: fire}` for each burning fireplace's `on_spans`
  when foley is on. `switch_props` plays the `click` for the other props and a 0.8 s `burner` at
  `FIRE_LIGHT_GAIN` −10 dB when a fireplace is lit.
- **Layout dump**: `PropSteam`, `Flock` and `FallenFruit` are left out (not placed by authors).
- **Measured** (scratch projects at preview 854×480, 15 fps, no audio, one process each under
  the 1500 MB cap; Cairo draws counted around `Camera.display_vectorized`, raw frames hashed):

  | render | frames | Cairo draws | wall (s) |
  |---|---|---|---|
  | a stage without the new things (trees, ball, lamp on, wind, leaves, a throw): HEAD c8fad68 / this step | 162 | 16 910 / 16 910 | 8.3 / 7.8–8.1 |
  | Step 120's room with clock, tv and lamp on: HEAD / this step | 266 | 32 665 / 32 665 | 9.6 / 9.7 |
  | a night room with a fireplace and a kettle, both off (2 runs) | 260 | 16 415 | 6.6–7.1 |
  | the same, both on all along (4 runs; the first two before `closed_curve`) | 260 | 31 846 | 10.4–11.4 |
  | the same, everything from the first moving part redrawn (for comparison) | 260 | 35 551 | 11.4 |
  | the first stage with `birds: 6` (2 runs) | 162 | 17 990 | 7.5–8.2 |

  The scenes without the new things give the same raw frame hashes as HEAD (all 162 and 266).
  Fire and kettle on: 59 more draws a frame (flames 8, glow 12, steam 6, and the rug, armchair and
  character in front of the glow), wall +3.3 to +4.4 s (+50 to +63 %): the fireplace's glow is a
  large translucent disc stack. The overlap rule saved 3 705 draws over redrawing everything from
  the first moving part, with the same frames. Birds: +1 080 draws, wall within the noise.
- **Checked by eye** (scratch projects, preview frames): a night room with the fireplace lit in
  beat 1 (flames behind the logs, the glow on the wall and floor) and the kettle switched on in
  beat 2 (steam rising from the spout); an orchard with a breeze: a fruit falling and lying
  under the tree, one falling on a character's head with the stars, the second tree's fruit, a
  flock of five crossing to the right and three to the left, a burning fireplace and a steaming
  kettle outdoors.
- **Not done**: the fire lights no character; a fallen fruit cannot be picked up (it is not a
  prop) and lies where it bounced; nothing checks that a `to:` character stands under the tree;
  the crackle plays while the fireplace burns in the scene, also when the camera looks away; a
  carried kettle's steam keeps its draw-order place; no birdsong (Step 128); birds do not land or
  perch; a tree's fruit count is fixed (4). Tests: `tests/test_cartoon_fire_nature.py`.

### 69.56 Everyday small props (Step 122)

Nine small props to hold, give, open and set on a table, a phone that rings, balloons that float
away and a watering can that pours. Original simple shapes in the theme's colours (fixed hex only
where no token fits every theme: `CANDLE_FLAME`, `LIGHT_FLAME`, `PAPER`, `PAGE_TEXT`, `STEM`,
`FLOWER_HEART`, `BALLOON_STRING`, a phone's dark case `#2B2F3A`).

- **Props** (`cartoon/props.py`, `SMALL_PROPS`, in `PROP_KINDS` after `kettle`): `cake` 0.22 (two
  tiers, icing, three candles; `accent` / `highlight`), `muffin` 0.08 (`secondary` top, `accent`
  case), `book` 0.13 (`primary` / `highlight`), `phone` 0.13, `letter` 0.08 (`PAPER` / `accent`),
  `gift` 0.2 (`primary` / `highlight`), `balloons` 1.1 (three on strings tied to a weight;
  `accent`, `highlight` and a lighter `accent`), `vase` 0.32 (`primary` vase, `accent` flowers),
  `watering_can` 0.22 (`tertiary` / `highlight`). `book`, `letter` and `gift` have the shapes
  `closed` / `open` (`PROP_SHAPES`, §69.37's live copies, both shapes one prop unit tall), so the
  `open` / `close` actions and `open: true` work on them unchanged; each shape has its own
  members. Grips (`PROP_GRIPS`): balloons by `BALLOON_KNOT` (0, 0.07), the strings' end above the
  weight; a watering can by `WATERING_GRIP` (−0.05, 0.75), the top of its handle;
  `WATERING_SPOUT` (0.7, 0.64) is the rose.
- **Held** (`cartoon/holding.py`, `scenes/handling.py`): `OVERHEAD_PROPS` = {umbrella}: only an open
  umbrella goes overhead (`is_overhead` checks the kind too), an open book, letter or gift stays at
  the hold point. `FULL_SIZE_HELD` = {balloons}: `held_height(..., full_size=True)` keeps their size
  (not `HOLD_MAX_HEIGHT`), and they are drawn right before the holder (behind the head, like an
  overhead umbrella). `_moving_block` now also takes the props held right *before* a walker (an
  overhead umbrella, balloons), so they keep their place when it walks in depth.
- **A ringing phone** (`cartoon/living.py`, `living_drawing.py`): `phone` is in `SWITCHED_PROPS`;
  on = ringing. Drawn `living`, it gets a lit screen (`LIT_SCREEN`, a caller's head and shoulders;
  `LIVING_PART` `screen`, never graded) and four amber ring lines (`RING_LINE` `#E8A33D`, two each
  side about `PHONE_CENTRE`, `ring`). `on_since(on, switches, t)` is when the current on span
  began; `ring_burst(t, since)`: a burst of `RING_BURST` 1 s every `RING_PERIOD` 2 s;
  `ring_shake(t, since)` = `RING_TILT` 10° × sin(2π × 13 Hz) eased over 0.08 s at both ends of a
  burst, 0 between. `LivingProp` keeps the phone's whole drawing (every member with points but the
  anchor) in prop units (`Prop.drawn_points`, the inverse of `prop_points`) and redraws it turned
  about `PHONE_CENTRE` through the anchor on every frame while it rings (absolute, so a held phone
  or a `PropMove` never accumulates a turn); its `movers` are the whole drawing, its `region` the
  box grown by sin 10° of its height. `Stage._ring_sounds` (after `finish`, with foley) records a
  `phone` sound (`PHONE_RING_GAIN` −6 dB) at each `ring_bursts(on_spans(...))`; switching a phone
  on plays no `click` (switching it off does).
- **Balloons let go** (`cartoon/small_props.py`, no manim): `FLOATING_PROPS` = {balloons}.
  `float_end(start, top, force)`: up to `top` (the stage's top + the prop's height + 0.3) and
  `FLOAT_DRIFT` 0.6 × force sideways per unit risen (force: the felt wind now, `felt_force`);
  `float_progress(share)` speeds up from rest over `FLOAT_SPEED_UP` 0.25 then rises evenly;
  `float_point(share, start, end, seed)` adds a seeded sway (`FLOAT_SWAY` 0.12 units, 2 swings,
  none at the ends) and a lean of up to `FLOAT_LEAN` 8°; `float_seconds(rise)` = rise / 1.6 × 1.25,
  1–6 s. The `let_go` action (character target, `prop`) releases the prop, brings the arm back
  (`LET_GO_ARM_SHARE` 0.3) and plays `PropMove(path=float_point)`; the prop is detached and stays
  above the frame.
- **Pouring** (`small_props.py`, `small_props_drawing.py`): `POURING_PROPS` = {watering_can}.
  `pour_tilt(share)`: 0 → 1 → 0 of `POUR_TILT` 40°, cosine ramps over `POUR_RAMP` 0.2 at each end;
  `pour_flow(seconds)`: the water runs while the tilt is past `POUR_FLOWS` 0.7; `pour_drops(t,
  flow, spout, ground, height, direction, seed)`: `DROP_RATE` 22 drops a second, each thrown
  forward `DROP_AHEAD` 0.35 heights/s, falling at `DROP_GRAVITY` 4 heights/s², radius 0.012 heights
  (± 30 % seeded), kept while above the ground. The `pour` action (character target, `prop`,
  `POUR_SECONDS` 2 s) plays `Pouring` (the can redrawn from its starting points turned about its
  grip, clockwise when the spout points right, the grip at the hand every frame) and `WaterFlow` on
  a `WaterDrops` (40 discs, `#8FD3F4` edged `#3E86B5`, graded) inserted right after the can and
  removed when the flow ends (`remover`). The layout dump leaves `WaterDrops` out.
- **Validate**: `holding_problems(kinds=)` (prop → kind): `let_go` needs a held prop that floats
  (else "'cake' does not float away ...; put_down it instead") and makes it gone for the scene
  (a later pick_up, open, ... is reported); `pour` needs a held prop that pours. Each action's
  `prop` option is checked against the kinds in `scene_problems`. `LIGHT_PROPS` gains `letter` and
  `balloons`.
- **Sound** (`sfx.py`): built-in `phone` (1 s, 0.4–3): a tone flipping between ~1.1 and ~1.4 kHz
  20 times a second in two pulses (0–42 % and 50–92 %). Step 128's phone ring may refine it.
- **Gallery**: `write_props_png` leaves `SMALL_PROPS` out by default (`props.png` byte-identical);
  `write_props_png(..., kinds=SMALL_PROPS, columns=4)` → `docs/gallery/media/small_props.png`
  (960×540, 21 KB), in CONFIG.md "Everyday small props".
- **Checked by eye** (scratch `s122/yard`, storyboard and preview frames): a cake held, then put
  down; a muffin, phone, book and vase on a table; the phone ringing (tilts, ring lines, lit
  screen) and picked up; held balloons behind the head, floating away with a breeze; a gift
  picked up and opened in the hand; a watering can held, tilted, drops falling; a book picked up
  from the table and opened in front of the reader.
- **Not done**: no splash or watering sound (Step 128); drops do not wet or grow anything; a phone
  is answered with `switch_off` (no `answer` action, no voice in the handset); balloons let go are
  gone for the scene; a held prop is not mirrored when its holder turns (§69.27); since Step 130
  `pour` turns a can whose spout points behind its holder round in the hand first (§69.64). Tests:
  `tests/test_cartoon_small_props.py`.

### 69.57 More animals: fox, owl, frog, turtle, penguin (Step 123)

`config.Species` gains `fox`, `owl`, `frog`, `turtle`, `penguin`: generic animals from the same
primitives in the look's colours, no feature or colour combination taken from a known character
(no mask or bandana on a turtle, no hat or glasses on the owl by default, no signature outfit). The
§69.48 rules hold (`SPECIES_OWN_KEYS`, svg error, clothes, hair, accessories).

- **Drawing** (`cartoon/animals.py`): `HEAD_SHAPES` for each; `SPECIES_PROPORTIONS` multiplies
  `Proportions` fields after `proportions` and before the seed (frog `leg_length` 1.3 and
  `mouth_width` 2.2; owl `eye_size` 1.4 and `eye_gap` 1.2; penguin `leg_length` 0.6,
  `arm_length` 0.85, `body_width` 1.08; turtle `leg_length` 0.85, `head_radius` 0.92). A **fox**:
  tall pointed ears lined with `fur_tint`, from the side a snout grown out of the head (filled over
  the head's outline, only its ridge and underside stroked) with a light jaw and a dark nose at the
  tip, from the front cheek ruffs and a light muzzle; a bushy tail (`FOX_TAIL`, the new
  `tapered_band(profile=...)` widest in its middle) with a `patch_tint` tip. An **owl**: two tufts
  of two slim feathers (`fur_shade`, trailing `pointy`), light discs round its big eyes, the
  `wing` arms and bare `bird_shin`s of a bird (`WINGED`), a short fan of tail feathers. A **frog**:
  a wide flat head lowered onto the shoulders and the eyes `FROG_EYE_RISE` 0.6 head radii up in
  bulges drawn behind the head (`species_frame` replaces the `Frame`'s `head_y` and `eye_y`;
  brows on the bulges, `BROW_GAPS`), nostrils, a wide mouth, `flat_foot` with toe pads, no tail
  (`config.SPECIES_WITHOUT_TAIL`, also in `cast.character_part_shapes`). A **turtle**: a light
  chin, nostrils, a short pointed tail rooted behind the shell, and a `shell` (`colors.hair`)
  added at the back of every `body` shape: from the side a dome bulging out behind the back over
  a `fur_tint` rim with plate lines in `fur_shade`, from the front its rim round the body. A
  **penguin**: a `patch_tint` face patch, `flipper` arms (skin colour whatever the sleeves), short
  legs with `BEAK_COLOR` flat feet (none with shoes), one stubby tail feather.
- **Beaks**: `BEAKS` gives each beaked species (`BEAKED`: bird, owl, penguin) its side hinge,
  half height and length and its front seam, half height and half width; `beak_mouth(species,
  ...)` scales the front openings by the beak's size against the bird's (the bird's numbers are
  the old ones exactly). Mouth places for fox, frog and turtle are in `MOUTH_PLACES` /
  `FRONT_MOUTH_PLACES`.
- **Moving** (`cartoon/acting.py`): `SpeciesMotion(gait, speed, jump)` and `SPECIES_MOTIONS`
  (turtle: short slow steps, speed 0.4; penguin: `Gait(stride 0.55, swing 0.45, ...,
  waddle 9)`, speed 0.7; frog: jump 1.8); every other species and a person use `PERSON_MOTION`.
  `build_character` sets `Character.species_motion`. `Walk` walks `species_motion.walking(gait)`
  (a plain walk becomes the species' walk; a run keeps `RUNNING` with the waddle), so its
  `step_length` and footsteps follow. `Gait.waddle` puts `WalkCycle.rock` (`waddle × swing ×
  amplitude`) on the cycle; `walking_state` rocks the body by it (`SIDE_ROCK` 0.5 of it from the
  side) and turns the legs back so they stay upright. The moving actions use the species factor
  only when the YAML gives no `speed` (`model_fields_set`), and `jump` only when it gives no
  `height`. The screenplay still plans walk times at a person's speed.
- **Contrast** (§69.49): `species_difference` counts two species of one `SPECIES_FAMILIES` family
  (bird / owl / penguin, cat / fox) 0.5 apart instead of 1; a turtle's hair colour is compared even
  without hair (its shell). `random_cast` draws fur from `SPECIES_COLORS` for the new species and a
  turtle's hair from `SHELL_COLORS` (the other species and humans get the same picks as before).
- **Gallery**: `write_looks_png` moves a figure back inside its character's cell (a long tail is
  no longer cut); `docs/gallery/media/more_animals.png` (720×420, 25 KB) shows the five side and
  front, in CONFIG.md "Animal characters". `animals.png` is unchanged.
- Step 114's six species and every human look draw exactly as before (digests pinned in
  `tests/test_cartoon_animals.py`). Tests: `tests/test_cartoon_more_animals.py`.

### 69.58 Robots and costumes (Step 124)

`config.Species` gains `robot`, built by the new `look.robot` (`config.RobotLook`: `head` box |
round, `face` eyes | screen, `antenna` true | false, `moves_on` legs | wheels; `CharacterLook.robot_look()`
gives the defaults when it is not given). A robot is a friendly generic machine from primitives
in the look's colours, no shape taken from a known film, TV or game robot (no dome head, no
binocular eyes, no humanoid protocol figure). Rules: `ROBOT_OWN_KEYS` (`ears`, `nose`,
`facial_hair`, `hair`) are not given with a robot; `robot` with another species and `shoes` on
wheels are config errors. `animals.is_animal` is false for a robot; `SPECIES_WITHOUT_TAIL` holds
`robot`.

- **Drawing** (`cartoon/robots.py`, called by the generator): the `head` part is a neck, side
  bolts, a rounded box (`BOX_HEAD`) or a ball, and a face plate (`fur_tint` of the plating) or a
  dark screen (`SCREEN_COLOR`, a glare line). The eyes, brows and mouth are the person's parts;
  on a screen they are drawn with `features` = `SCREEN_GLOW` (`face_colors`) and the open eyes
  are filled glowing ellipses (`screen_eye`; sleepy: the lower half), so visemes, blinks and
  expressions show on the screen. Arms and legs are the person's segments in the plating (a plain
  outfit) or the outfit's colours, with `joint` bolts at the shoulders, elbows and knees,
  gripper `hand`s and block `foot`s (none with shoes); on wheels each shin ends at a `wheel`
  (`WHEEL_RADIUS`, tyre `TYRE_COLOR`, the sole still at 0, so seats, planting and grounding are
  unchanged). A `chest_panel` of three lights goes over every `body` shape.
- **`antenna` part** (new in `PART_NAMES`, `PosePart`, `SVG_PART_NAMES`; parent `head`, draw order
  49, behind the head): a socket, a coil (stroked zigzag) and a ball light in `colors.accessory`,
  pivoting at the socket; shapes `default` and `dim` (`idle.ANTENNA_DIM_SHAPE`, the light 55 %
  darker). The coil and light trail in the wind (`TRAIL_WEIGHTS["antenna"]` 0.35);
  `follow_angles` gives it `-FOLLOW_ANTENNA_DEGREES (40) × (forward + up)`, limit 25° (it tips back
  as the robot sets off); idle: `antenna_sway_angle` (1.7 s, 3°) and `antenna_light_on` (dim 30 %
  of every 1.3 s, lit at the clock's start) as overlays. `crown_top` counts it, so effect symbols
  go above it.
- **Moving** (`acting.py`): a legged robot walks with `SPECIES_MOTIONS["robot"]` (knees 0.5,
  elbows 0.4); on wheels `ROLLING_MOTION` (`Gait(swing 0, knee 0, elbow 0, bob 0.25, rolls=True)`;
  a run keeps the roll and leans like a run): `species_motion(species, wheels=)`, set by
  `build_character`. `Gait.rolls` reaches `foley.PlayedAction.rolls` (from `Walk.gait`), which
  plays no footsteps.
- **Costume pieces** (`cartoon/costumes.py`; `Accessory` gains `crown`, `wizard_hat`,
  `party_hat`, `cape`): the first three are drawn in the `accessory` part (`HEADWEAR_DRAWINGS`,
  `HEAD_ACCESSORIES`), their base `BASE_RISE` 0.72 head radii above the head's centre (the hat's
  brim): a crown (band, points with balls, gems in `colors.clothes`; rigid), a wizard hat (brim,
  a `tapered_band` cone along a `path_curve` bending back, band, two stars; trailing
  `wizard_hat` 0.4), a party hat (a cone turned 12°, two stripes `clip_to_box`ed, a pompom;
  trailing `party_hat` 0.2). `config.TOP_OF_HEAD` (hat, cap, crown, wizard_hat, party_hat): at
  most one per look ("X and Y are both worn on top of the head", the old hat-and-cap message
  unchanged).
- **`cape` part** (new; parent `body`, draw order 3, behind the tail and everything): from the
  shoulders to `CAPE_HEM` 0.45 of the legs' length, a waving hem; from the side flaring out
  behind the back, from the front its inside (`fur_shade` of `colors.accessory`) beside the body;
  pivot at the neck. Its ties and clasp (`cape_clasp`) go over every `body` shape. Trailing
  `cape` 0.9; `follow_angles` `FOLLOW_CAPE_DEGREES (50) × (forward - up)`, limit 35° (back as it
  sets off or falls, on as it stops); `walking_state` turns it back by `WALK_CAPE_FLUTTER` 0.4 of
  the size of the arm swing each step.
- **Voice**: `[beep]` (`VOICE_SOUNDS`, said `Beep boop!`, face `happy`, viseme `E`) with the new
  built-in sound `beep` (0.4 s, two soft electronic notes) at a line's start or end, like a gasp
  (§69.33); voices work as for anyone.
- **Cast and contrast**: `cast.character_part_shapes` adds `antenna` (`default`, `dim`) and
  `cape`; `vidgen character` prints `species robot (box head, eyes face, antenna, legs)`.
  `contrast.HEADWEAR` gains the three hats; two robots differ by details `robot head ...`,
  `robot face ...`, `robot on ...`, `antenna`. `random_cast` draws a robot's plating from
  `SPECIES_COLORS["robot"]` and its build from `ROBOT_CHOICES` (only for `robot`, so other casts
  keep their picks); costume pieces are never drawn at random.
- **Gallery**: `docs/gallery/media/robots.png` (four robots and four costumed characters, side and
  front). Every earlier look draws as before: Steps 113 / 114 pins in `tests/test_cartoon_animals.py`,
  Step 123 species pinned in `tests/test_cartoon_robots.py` (taken at 8dceb29). Tests:
  `tests/test_cartoon_robots.py`.

### 69.59 More expressions (Step 125)

Six built-in expressions join `poses.EXPRESSIONS` (after the seven of §69.3, whose entries are
unchanged): `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`, `frightened`. They work on
every generated look (people, animals with muzzles or beaks, robots with a plate or a screen),
side and front, and fall back on SVG characters through their shape lists.

- **Parts and shapes.** `ExpressionPart` gains two optional parts, both children of `head`
  (`PART_NAMES`, `DEFAULT_PARENTS`; not in `SVG_PART_NAMES`): `cheeks` (draw order 55, over the
  head under the eyes and mouth; shapes `none`, `blush`, `tears`, `tears_running`) and
  `bristles` (48, behind the head and a robot's antenna; `none`, `up`). Their rest shape `none`
  draws nothing (`expression_shapes.nothing`: one point, no fill area, no stroke, so dimming or
  fading never shows it), so every expression that does not name them, the seven old ones
  included, shows nothing there. The eyes gain `laughing` (an arc, closed), `wide` (a big white,
  a small pupil; on a screen a glowing ring), `swirl` and `swirl_turned` (a spiral, turned half
  round); the mouth `laugh` (open, flat on top, a pink tongue), `tongue` (a lip line and a tongue
  hanging out, forward from the side) and `wavy`. All are appended after the earlier shapes
  (`cast.GENERATED_SHAPES`), so the rest shapes and shape order of every part stay. Drawing:
  `cartoon/expression_shapes.py` (called by the generator; eye and mouth shapes in the face's
  colours, so a screen's glow), a beak's `laugh` / `tongue` / `wavy` in `animals.beak_mouth`
  (`BEAK_LAUGH_OPENING` 46°, `BEAK_TONGUE_OPENING` 18°). Blush: `BLUSH_COLOR` at 0.7 opacity under
  each eye (a screen: three glowing strokes); tears: `TEAR_COLOR` streams from under each eye down
  to 0.72 head radii below the head's centre, with a drop (two lower in `tears_running`).
  `bristles` `up`: a person with hair: a zigzag crown in the hair colour reaching 0.3 head radii
  above the head part's top (hair, ears; at least 1.35 r); a furry animal (`FURRY`): fur tufts in
  its colour on its head's ellipse; a bird, an owl, a penguin: five feathers in `fur_shade`;
  anything else (a bald person, a frog, a turtle, a robot): four fright lines over the head.
- **Sizes stay.** `generator._scaled_to_unit_height` ignores the Step 125 shapes
  (`EXPRESSION_ONLY`), so hair standing up never shrinks a figure; `drawing_digest` in the tests
  leaves them out, so every pin taken before (Steps 113, 114, 123) still holds for everything drawn
  before.
- **Expressions** (`EXPRESSIONS`): `laughing` eyes `laughing` (else `closed`), mouth `laugh`
  (else `open`, `A`); `blushing` cheeks `blush`, a small smile, eyes lowered, brows `sad` raised a
  little; `tongue_out` eyes `laughing`, mouth `tongue`; `crying` eyes `laughing` flipped (y
  -0.9: squeezed), mouth `open` 1.1 × 0.85, cheeks `tears`, brows `sad`; `dizzy` eyes `swirl`,
  mouth `wavy`; `frightened` eyes `wide` scaled 1.15, brows `sad` raised 0.03, mouth `wavy`,
  bristles `up`. A `PoseChange` swaps the shapes at each part's half like any shape.
- **Moods** (`idle.py`, no manim; applied by `Character._idle_step` as overlays, never in
  `state()`): `shape_mood` picks the first of `MOOD_SHAPES` the pose shapes show (`eyes swirl` →
  `sway`, `eyes wide` → `shiver`, `mouth laugh` / `cheeks tears` → `bounce`), so own expressions
  using these shapes get the motion. `IdleClock.set_mood` / `mood_levels`: the new mood's strength
  follows `MOOD_SPRING` (1.4 Hz, damping 0.45: about 20 % past full) from its strength at the
  change, the old one dies away on the same spring (never below 0, dropped after
  `MOOD_SETTLE_SECONDS`), so nothing jumps when an expression starts or ends (the clock stops
  during a `PoseChange`; the mood starts after it). `mood_motion`: `sway` turns the body
  `MOOD_SWAY_DEGREES` 4° about the hips every 1.8 s and the head 6° a quarter behind, the legs
  turned back by the same overlay so the feet stay; `shiver` shakes the body 0.005 units at 13 Hz
  (legs held back the same way), stretches a robot's `antenna` by `ANTENNA_FRIGHT_STRETCH` 0.35 of
  its height (springing up past it) and makes `bristles` quiver; `bounce` lifts the body 0.008
  units 4.5 times a second (the shoulders shake: laughing, sobbing). With `idle: false` there is no
  mood motion (nor blinks).
- **Eyes and tears.** No blink shows over `BLINKLESS_EYES` (`closed`, `laughing`, `swirl`,
  `swirl_turned`); `ALTERNATE_SHAPES` swaps `swirl` ↔ `swirl_turned` and `tears` ↔
  `tears_running` every `ALTERNATE_SECONDS` 0.2 s (overlays), so swirls turn and tears run.
- **Speech.** Lip sync shows visemes over the expression's mouth and the expression's mouth
  between words (§69.4), so a character laughs while talking: eyes `laughing`, the shoulders
  bouncing, the mouth moving with the words.
- **Mappings.** Voice sounds `[laugh]` and `[giggle]` give `laughing` (was `happy`; `[gasp]` stays
  `surprised`); screenplay manners (`MANNERS`): the six names, and `giggling` / `amused` laughing,
  `embarrassed` / `shy` / `bashful` blushing, `cheeky` / `teasing` tongue_out, `sobbing` /
  `weeping` / `in tears` crying (was sad), `dazed` / `woozy` dizzy, `scared` / `afraid` /
  `terrified` frightened (was worried); `EXPRESSION_EFFECTS` adds `dizzy` → `stars` and
  `frightened` → `sweat`. `crying` has no symbol: the `tear` symbol (§69.40) is one drop beside
  the head, kept for directions such as `[cries]`; the streams are part of the face. `react`,
  `emote` and stage `expression` accept the new names (they read `Character.names`), and the
  character sheet lists them and the new mouth shapes (it reads the tables).
- Tests: `tests/test_cartoon_expressions.py`.

### 69.60 More weather, part 1: snow that settles, fog (Step 126)

Snow on a `stage` may land and settle in a growing white layer, and a stage may have fog lying
in bands between its things by depth. Both are seeded and pure, outdoors only, and a scene
without them renders as before.

- **Settling snow** (`cartoon/snow.py`, no manim; Manim units, `y` up): `ParticleSettings.settle`
  (snow only, `settle_problem`; stage param error / validate problem like `puddles`) and
  `settled` (seconds of snowfall already lying, 0–600, needs `settle`). `particle_field` gives a
  snow field with `settle` the scene's `snow_ground` (rain keeps `rain_ground`). A
  `RainGround`'s shelters may now also be a `TopLine(xs, ys, feet)`: a prop's upper edge, with
  `top_at(x)` and `covers` like `ShelterBox`. `flake_floors` = Step 105's landing line or the
  highest covering shelter's top there (a box's top, a line's height); `rest_flakes(bottom, floor,
  speed)`: a flake below its floor lies on it (raised there) fading over `FLAKE_REST` 0.5 s, then
  is hidden until it wraps (Step 76's drops keep their positions: the landing shares are Step
  105's stream). `ParticleField` keeps its landing shares for any ground and makes splashes for
  rain only.
- **The layer**: `settled_seconds(now, start, ended, settled)` counts the snowfall in
  `SETTLE_STEP` 0.5 s steps (frozen at the field's end: it never melts); `settle_amount(seconds,
  density)` = seconds × density / `SETTLE_SECONDS` 24, at most 1 (linear, so each step adds the
  same). Blanket: `blanket_outline(left, right, bottom, back, rise, frame_height, seed)` from the
  frame's bottom edge to the ground area's back edge (rain's `back`) raised by amount ×
  `BLANKET_RISE` 0.018 frame heights × `edge_lumps` (three seeded sines, 1 ± `LUMP_DEPTH` 0.6),
  counter-clockwise; opacity `BLANKET_OPACITY` 0.97 × `blanket_cover` (amount / `COVER_SHARE` 0.4,
  at most 1). `bare_patches(shelters)`: clockwise ellipses (`BARE_WIDTH` 0.8 of the shelter's width,
  `BARE_FLAT` 0.22 high) on the feet line of each standing shelter (a tree, an open umbrella that
  no action moves): holes in the blanket (Cairo fills by winding), covered by a second shape at
  `THIN_SNOW` 0.45 of its opacity (a first try with plain holes showed the theme's dark ground as
  black ellipses). Caps: `curve_segments` turns a member's cubic points into straight pieces
  (6 samples a curve) and `top_line(segments, columns)` takes the highest crossing over each of
  `CAP_COLUMNS` 28 column middles (plus segment ends inside a column; empty columns between their
  neighbours) — sampling points per curve alone left dips where one long roof edge had no sample
  and a window's top was the highest point (seen as thin white spikes); `cap_thickness` is the full
  thickness × amount where the line's slope is at most `CAP_SLOPE` 1 (45°), tapered next to steeper
  parts; `cap_outlines` makes one counter-clockwise shape per run, `CAP_SINK` 0.35 of it below
  the line (over the outline), pointed ends; `cap_full_thickness` = `CAP_THICKNESS` 0.03 shorter
  sides × the depth scale, at most `CAP_SHARE` 0.2 of the prop's height. `SNOW_COLOR` `#F4F7FC`
  (or the field's first `color`).
- **Drawing** (`cartoon/weather_drawing.py`): `SnowBlanket` (a `VGroup`: the blanket with holes,
  the thin snow), `SnowCap(xs, ys, full, color, cap_of)`, `SettledSnow` (`amount_at`, `update`
  redraws only when the step changes, `changing`, `done`, `movers`, `region`: the full layer's
  box). `prop_top_line(prop)` reads the members with points that show (fill or stroke).
- **Stage**: `snow_ground()` = rain's band, open umbrellas as boxes (`_shelter_of`, shared with
  `rain_ground`) and the `_snow_tops()` top lines (taken once) of every prop on the ground that no
  action moves (`_movable_props`), not lifted or hung, not `FLAT_PROPS`, water or air vehicles,
  umbrellas or held. `particles_started` → `_settle_snow`: a `SettledSnow` for the field, its
  blanket laid like the puddles (`_lay_on_ground(under_water=True)`: right before the water's
  band when the stage has water), a cap right after each such prop (`_put_after_prop`: into
  `scene.mobjects`, or kept in `_after_props` for the entrance, which adds it right after the
  prop), none on swaying kinds (`SWAYS`) when the stage's wind may blow (the cap would not
  sway); all lit (`mark_lit`). `Stage.snow_layers`.
- **Fog** (`cartoon/fog.py`, no manim): `FOG_DEPTHS` (1, 0.8, 0.6, 0.4, 0.2); `band_opacities(
  density)`: band k holds `1 − exp(−FOG_THICKNESS (1.8) × density × (d_k − d_{k+1}))` (the front
  band down to 0), so the bands in front of a depth hide `1 − exp(−1.8 × density × d)` where d is
  the deepest band in front of it; `fog_cover(depth, density, high=False)` multiplies them (0 at
  depth ≤ 0.2; the sky = every band). Each band has `FOG_LAYERS` 3 layers holding
  `FOG_LAYER_SHARES` (0.5, 0.25, 0.25) of its optical depth (`layer_opacity`; together exactly the
  band's opacity): a haze up to the frame's top edge, banks up to 1 and 0.5 × `FOG_HEIGHT` 0.3
  frame heights × the depth scale (the back band `FOG_HAZE_HEIGHT` 0.4) with wavy tops
  (`FOG_WAVE` 0.3 × two seeded sines of 1.3 and 0.55 frame heights), each taller layer starting
  `FOG_FEATHER` 0.015 frame heights lower (soft edges). `band_outlines(index, ground, left, right,
  frame_height, shift, seed)`, `band_box` (the box whatever the drift). `fog_shift(t, blown,
  depth, drift)` = drift × `FOG_DRIFT` 0.02 × (2 − depth) × t + `FOG_WIND_DRIFT` 0.12 × blown
  (frame heights; nearer bands twice as fast). A first try with only short ground banks left
  deep tree crowns crisp over fogged trunks; the haze layer fixes that.
- **Drawing and order**: `FogBand` (a `VGroup` of the layers; `stage_depth` is its depth: Manim's
  `Mobject.depth` is the z extent, and setting it on a first try scaled the band instead), and
  `StageFog` (`update`, `moves` = drift > 0 or a wind may blow, `changing`, `movers`, `region`).
  Stage param `fog` (`StageFogSetting`: `true`, a density, or {density, color, drift, seed};
  `false` is an error like `birds: false`; refused in a room). `Stage._fog()` builds it lit
  (`blown` from `particle_wind`), seed `motion_seed(scene, "fog")`; `_sort_fog()` puts each band
  right before the first character or prop (draw order, held props excepted) standing at its
  depth or nearer (before the props that one holds in front of it), else before the foreground
  (`_in_front`) or the first particle field; it runs in the entrance and, while a walk in depth is
  under way, on every frame in `_draw_order_step` (a changed order is then redrawn), and
  `_depth_crossers` adds the bands a walker passes. The windows of a room show no fog.
- **What is redrawn** (§69.54's rule): `_living_things` adds the snow layers and the fog;
  `_living_step` updates them (installed by `_watch_living`) and removes itself once only flown
  flocks, done layers and still fog are left. A layer redraws itself and what stands in front of
  it only in animations where a step passes; a full layer (or after the snow) is static. Moving
  fog redraws everything from the back band on.
- **Measured** (scratch `s126/` in the scratchpad, preview 854×480 15 fps, no audio, one process
  each under the 1500 MB cap, `s120/measure_room.py`):

  | render | frames | Cairo draws | wall (s) |
  |---|---|---|---|
  | snowy meadow (house, tree, rock, table, umbrella, a walk in depth), snow without `settle`: HEAD e3e8e3d / this step | 277 | 48 224 / 48 224 | 11.9 / 11.6 |
  | the same with rain and puddles: HEAD / this step | 277 | 62 416 / 62 416 | 14.9 / 14.6 |
  | the meadow with `settle: true, settled: 6`, density 1.5 (the layer grows all along) | 277 | 54 427 | 12.9 |
  | a night meadow, `settled: 30` (full from the start) / without `settle` | 162 | 22 757 / 22 547 | 6.9 / 6.8 |
  | a forest (5 trees, 3 characters, a walk in depth) with `wind: breeze`: `fog: true` / none | 185 | 23 296 / 20 521 | 9.9 / 8.9 |
  | the forest calm: `fog: {drift: 0}` / none | 185 | 22 092 / 19 833 | 9.4 / 8.3 |

  Without the new things the raw frame hashes equal HEAD's (all 277 in both). A growing layer:
  +13 % draws, +11 % wall; a full one: the blanket and caps once per animation. Moving fog: +12 %
  wall; still fog still costs +13 % here: the walk in depth redraws the bands it passes, and five
  translucent frame-high shapes are slow to draw even once per animation.
- **Checked by eye** (preview frames): a snowy meadow by day (caps on the roof, chimney, crown,
  table and rock, the blanket with lumps along its back edge, thin snow under the tree and the
  umbrella, flakes lying a moment) and at night (`settled: 30`: the layer graded bluish, white
  flakes); a foggy forest in a breeze (the trees at depths 1, 0.85, 0.55, 0.3 paler the further
  back, characters at 0, 0.45 and 0.9, one walking from 0.9 to the front coming out of the fog);
  a foggy night street at density 0.8 (houses fading, wavy banks over the sky).
- **Not done**: no footprints; caps do not sway with a swaying prop (none then) and stay where a
  prop stood when it is later moved (movable props get none); snow does not settle on characters
  or held props; the layer does not melt; no fog action (it is there all scene) and none through
  a room's windows; particles stay ungraded and in front of the fog. Seen while checking, not
  from this step (also without `settle`): a character walking behind a house in depth leaves a
  faint outline of itself over the house (fixed in Step 127, §69.61: it was the scene's outro).
  Tests: `tests/test_cartoon_snow_fog.py`.

### 69.61 More weather, part 2: lightning, rainbows, the sun and moon moving (Step 127)

- **Strikes** (`cartoon/storm.py`, no manim): `Strike(time, x, distance, seed, bolt)`: its
  `pulses` (`strike_pulses(seed)`: the first two or all three of `FLASH_PULSES` (start, length,
  peak): (0, 0.1, 1), (0.2, 0.08, 0.7), (0.36, 0.06, 0.45), the later ones ±0.03 s and 85–100 %
  of their peak), each held for its length, then `peak · exp(-age / 0.07)` for `FLASH_TAIL`
  0.25 s; `level(now)` = `flash_strength(distance)` (1.1 − 0.14 · km, 0.4..1) × the brightest
  pulse; `end`. `flash_level(strikes, now)`, `flashing(strikes, start, end)` (like
  `lighting.changing`). `flash_grade(grade, level, share=FLASH_SHARE 0.5)`: every channel
  `f = level · share` of the way to `FLASH_COLOR` `#EEF2FF` (`multiply · (1 − f)`, `glow · (1 − f)
  + f · white`), stars and shadow × (1 − f).
- **Thunder**: `thunder_delay(km) = km / 0.343` s; `thunder_cue(km)`: gain −3 − 3 · km (≥ −18 dB),
  duration 2.2 + 0.6 · km (≤ 7 s), intensity 0.9 − 0.15 · km (0.15..0.9), pitch −km semitones (≥ −6);
  `thunder_pan(x)` (x − 0.5) · 1.6 within ±0.8. The built-in sound `thunder` (`sfx._thunder`, 3 s,
  1–8): a crack (noise band-passed at 1.8 kHz, 60 ms decay, × 1.6 · intensity) over a rumble (noise
  low-passed at 120 Hz) in 3–5 seeded Gaussian swells, rising in 3 % of its length, falling as
  (1 − u)^1.2. `Stage._thunder` cues it with those params (a project file `thunder` plays as is)
  when the stage's foley is on.
- **Rain storms**: `ParticleSettings.lightning: bool | float (2..120)` (`storm_problem`: rain only;
  `storm_every`: 8 s for `true`). `storm_strikes(start, until, every, seed, stop)`: gaps
  `every · (0.5 + r)` (the first `every · (0.3 + 0.7 r)` in), x 0.12..0.88, distance 0.6 + 3.4 r^1.5
  km, 70 % with a bolt, a prefix of the same sequence whatever `until`. `RainStorm(start, every,
  seed, ended)` (`ended`: the field's), `.strikes(until)`, `.over(now)`. `Stage.particles_started`
  adds one per rain field with `lightning` (seed from the scene, the field's seed and its index)
  to the light; `_storm_thunder` (after the scene played) cues the thunder of those whose thunder
  starts before the scene's end.
- **The flash** (`shading.StageLight`): `strikes` (the action's), `storms`, `flash_share`
  (outdoors `FLASH_SHARE`, × `ROOM_FLASH` 0.5 in a room), `flash` (the level now),
  `strikes_until(t)`; `update` grades `light_at(...)` and then `flash_grade`; `changing` also when
  a strike's window overlaps; `settled` also needs every strike over and every storm `over`. The
  stage installs its light from the start when the scene may flash (`Stage._lightning_used`: a
  `lightning` action, or rain with `lightning` in the param or a `particles` action), so a stage
  without a background gets the lit background rectangle (the theme's colour: the same pixels).
  `_light_step` keeps running while flashes may come; `get_moving_mobjects` redraws everything in
  an animation where one falls. `_show_light` also lights a room's window skies
  (`room.flash_sky(sky, level)`: `WINDOW_FLASH` 0.85 × level of the way to the flash colour).
- **The bolt** (`weather_drawing.LightningBolt`, not graded, named `lightning`): one per stage
  outdoors when the scene may flash, put right after the sky (`_put_in_sky`), 4 paths × (a glow 4 ×
  the width, `#9FB6FF` at 0.55, and a white core). `Stage._show_bolt(now)` (in `_sky_step`) shows
  the brightest strike with a bolt: `bolt_paths(seed, x, top, bottom, spread)` (cached per seed)
  from the frame's top to the horizon (`_horizon_y`: the ground area's back edge), its stage x
  `left + strike.x · stage_width`, spread `BOLT_SPREAD` 0.12 frame heights (`BOLT_CORNERS` 11
  corners jittering ±0.175 · spread, 1–3 branches of 3–4 corners from a middle corner, down and
  out), core width `BOLT_WIDTH` 4 × (1.2 − 0.1 · km, 0.4..1.2), at the pulse level (without the
  distance's strength); hidden otherwise.
- **The `lightning` action** (`scenes/storm_action.py`, non-animating like `light`, `run_time`
  `FLASH_SECONDS` 0.7, `number_target`): target a mark or an x (`_place`: a number written as the
  target is an x), `distance` (0..10 km), `bolt`, `seed`; `cue` → `Stage.strike_lightning(at,
  time, ...)` (no place: x 0.15..0.85 from the seed; seed default `motion_seed(scene,
  "lightning", time)`; no bolt in a room). Validate: a stage scene, one place, a known mark or x.
- **Rainbows**: `RAINBOW_COLORS` (7, soft, red outside), `rainbow_bands(cx, base, radius,
  thickness=0.16)` (half rings, the outer `radius`, each band `radius · 0.16 / 7`),
  `RainbowChange` + `rainbow_level` (`fade_at` from 0). `Rainbow` (a `VGroup` of 7 filled bands,
  `opacity`, `box`), `StageRainbow` (a thing that moves by itself, §69.54: `fade`, `update`,
  `changing`, `done`, `movers`, `region`), in `Stage.rainbows` / `_living_things`. The `rainbow`
  action (non-animating, `run_time` 3): target where its middle is (default `centre`), `width`
  (frame widths across, default 0.75), `opacity` (0.55), `hide` (fades all rainbows out; no
  place); refused in a room. `Stage.show_rainbow` puts it right after the sky, lit, standing on
  the horizon; `hide_rainbows`.
- **The sun and moon's path** (`cartoon/sun_path.py`, no manim): a path share 0 (horizon, left)
  .. 0.5 (top) .. 1 (horizon, right), hidden beyond for `PATH_HIDDEN` 0.08 at each end, one round
  `PATH_ROUND` 1.16 (`wrap_share`). `PATH_PLACES`: sun morning 0.1, day 0.5, sunset 0.9, night and
  indoor 1.08; moon morning 0.9, day −0.08, sunset 0.1, night 0.5, indoor 0.3. `path_blend`
  moves forward only (round the hidden part when the place is behind); `PathMove` +
  `path_share_at` (`fade_at`, eased like the light). `path_point(s)` → x share `0.1 + 0.8 s` of
  the stage, height `sin(π s)` (below 0 under the horizon), shown (smoothstep of height / 0.15).
  `elevation(s)` = 65° · height; `shadow_cast(s)` → (stretch = cot(elevation) ≤ `MAX_SHADOW_STRETCH`
  3, the maximum under the horizon; side +1 before noon, −1 after, 0 at 0.5);
  `cast_shadow(ellipse, stretch, side)`: `width · 0.6 · stretch` longer on that side (its foot
  stays), opacity / (1 + 0.25 · stretch); the ellipse itself when stretch or side is 0.
- **Moving them** (`light` option `move_sun`; validate: a preset, outdoors, a `sun` or `moon`
  prop): with it anywhere in the scene, `Stage._start_sky_path` makes every sun and moon prop a
  `SkyBody` (base: the stage light's place, a tint as `day`; `stage_depth` 1), the entrance moves
  them right after the sky, `change_light(..., move_sun=True)` adds a `PathMove` per body with the
  light change's start and seconds, `_sky_place(x, height)` puts a body's middle at `left + x ·
  stage_width`, `horizon + height · (frame top − horizon − SKY_TOP_ROOM 0.14 frame heights)`, and
  `SkyBody.update` fades its own opacities by `shown`. `_sky_step(now)` (in `_light_step` and
  `get_moving_mobjects`, before the light's update) places the bodies, sets every shadow group's
  `set_cast(stretch · shown, side)` from the body that shows most (the sun on a tie) and shows the
  bolt. A sun move only comes with a light change, so the whole stage is redrawn while it moves.
- **The outro** (the Backlog bug from Step 126): `NarratedScene.finish` → `clear_all` faded every
  mobject on its own, so for 0.5 s a fading house (opacity 0.98, 0.9, ...) showed the character
  standing behind it as a faint outline (a frame-by-frame check proved the drawn frames equal a
  whole redraw: neither the depth walk's draw order, `_moving_in_order` nor the static image was
  the cause). `Stage.finish` now fades in a cover of the background colour (`_cover`, also the
  entrance's) with a z index above everything over `outro` seconds, then removes every mobject
  (the scene ends empty, as after `clear_all`); with a transition other than
  a cut, or a next scene carrying a target out, it keeps the old behaviour.
  `test_a_character_behind_a_house_does_not_show_through_it_as_the_scene_fades_out` (54 levels
  off before, ≤ 2 after). Also fixed: while the light changed during an animation, a moving part
  of a character was listed again after everything (`get_moving_mobjects`), so it was drawn over
  the entrance's cover.
- **Measured** (scratch `s127/`, preview 854×480 15 fps, no audio, `s127/measure.py`):

  | render | frames | Cairo draws | wall (s) |
  |---|---|---|---|
  | rainy stage (house, tree, 2 characters): HEAD 4f2dc6e / this step (no new things) | 237 | 38 178 / 38 039 | 8.7 / 9.0 |
  | the same with 2 `lightning` actions, `lightning: 4` on the rain and a `rainbow` | 237 | 43 423 | 11.1 |
  | dusk: `light: sunset`, then `night` (4 s fades) with `move_sun` / without | 168 | 17 495 / 17 682 | 7.0 / 6.8 |
  | a room with one `lightning` / without | 71 | 4 001 / 2 573 | 2.5 / 2.2 |

  Without the new things the raw frames equal HEAD's but for the outro (the meadow of §69.60: 270
  of 277 frames equal, the last 7 differ; the rainy stage: 230 of 237). Every frame of the new
  renders equals the scene drawn whole in its draw order (`s127/ghost_check.py`).
- **Checked by eye** (preview frames): the rainy stage flashing (washed out, the bolt behind the
  tree), the rainbow behind the house and the hills; the dusk with the sun sinking to the right
  behind the hills, the shadows stretching left, the moon rising behind the house and standing at
  the top at night with the stars; the room's windows flashing white.
- **Not done**: the bolt strikes only at the horizon (never on a prop or a character); clouds
  are not lit from inside; no rain-storm thunder after the scene's end; the sun and moon move only
  with a light change (no `sun_path` of their own) and keep their size; shadows of a moving body
  stretch only along the ground (no skew, no second shadow for the moon at the same time); a
  room's light does not change with `move_sun` (refused). Tests: `tests/test_cartoon_storm.py`
  (13 without rendering, 2 tiny renders), `tests/test_cartoon_depth.py` (the outro).

### 69.62 More sounds: door creaks, knocks, splashes, the set's ambience (Step 128)

- **Searched first**: `bell` (a bicycle bell, Step 118), `engine` (starting and running, the
  "engine hum", Step 118) and `phone` (a ringing trill, Step 122) existed and are kept as they
  are; no creak, knock, splash or set bed existed. Reused: `sfx` generators and `_finish`, the
  ambience beds' `AmbienceBed` / `plan_ambience` / `merge_spans` / `_circular`, `foley_cues`,
  `pour_flow`, `RESHAPE_SHARE`, `on_spans`'s pattern for timings, the non-animating action shape
  of `switch_on`.
- **New built-in sounds** (`sfx.py`, now 29; finishing and level as §47; measured at intensity
  0 / 0.5 / 1 as the loudest 400 ms, K-weighted): `creak` (0.9 s, 0.3–3: stick-slip pulses at a
  rate gliding 45 → 110 → 70 Hz with a seeded 3.3 / 7.9 Hz wobble, filtered by wood bands at 550
  Hz, 1.3 kHz, 2.6 kHz; −30.0 / −27.6 / −27.4 LUFS, peak-limited at −9 dBFS), `knock` (0.75 s,
  0.3–2: three raps at 0, 0.19, 0.38 of 0.75 s, each a 190 Hz thump falling from +15 %, a 410 Hz
  hollow and a tap of noise at 1.5 kHz; −30.0 / −27.0 / −24.0, peak −12.1 at 0.5), `splash`
  (0.6 s, 0.2–3: a noise burst at 2.5 kHz decaying in 70 ms, a 250 → 600 Hz plunk, 18 droplets a
  second of length (+4) placed early-weighted, a fading 4 kHz fizz; the burst and plunk × (0.35 +
  1.3 · intensity); −30.0 / −27.0 / −26.4, peak −10.3 at 0.5). Generation 20–55 ms each.
- **Set beds** (`ambience.py`, numpy only, seeded by `crc32("ambience:<bed>")`, circular so they
  loop without a seam, `_leveled` to their integrated loudness; the rain and fire loops use the same
  helper, unchanged): `birdsong_loop` (20 s; 18 phrases from `_bird_phrase`: 3–6 falling tweets at
  3–5 kHz, a two-note whistle at 2–3.2 kHz, or a 0.5–0.9 s trill at 3.5–5.5 kHz warbling 18–25
  Hz; each at 30–100 %, panned ±0.8 equal-power, placed around the loop by `_placed`; a rustle of
  noise at 3 kHz at 0.04; −36 LUFS, peak −23.4 dBFS, channels correlate 0.63), `city_loop` (16 s:
  a 35–250 Hz rumble swelling once a loop, 3–4 cars as wrapped Gaussian swells of 600 Hz noise
  0.8–1.6 s wide, a 900 Hz murmur whose level wanders at three whole-cycle rates of 3–6 Hz; −35,
  peak −23.1), `room_tone_loop` (8 s: 40–250 Hz noise + 0.2 × a wide 1.5 kHz hiss, ±5 % once a
  loop; −46, peak −34.1). Ducking `BIRDSONG_DUCK` 4 dB, `CITY_DUCK` = `RAIN_DUCK` 5 dB,
  `ROOM_TONE_DUCK` 0 (it is ~25 dB under the voice); fades `SET_FADE_IN` 2 s / `SET_FADE_OUT`
  1.5 s. `AMBIENCE_BEDS` / `BEDS` gain the three, so `plan_ambience`, the mix report and the
  pipeline's shift to video times take them unchanged. In a scratch 28 s preview (word-count
  timing, so ducked all along): birdsong −38.2 LUFS, the city −41.3, the room with its foley −30.5.
- **Which bed** (`set_ambience(setting, room=, lights=, rain=, end=)`, pure): `False` none; a list
  of `SET_BEDS` names: each for the whole scene (deduplicated, in order); `True` (automatic): a
  room → `room_tone` for the whole scene; outdoors `birdsong` over the spans whose light is in
  `DAYLIGHT` (`day`, `morning`; a tint counts as not), minus each rain span extended by
  `BIRDS_AFTER_RAIN` 2 s, spans under `MIN_BIRDSONG_SECONDS` 2 s dropped; `city` never automatic.
  `Stage.set_beds(rain, end)`: none without foley; the stage's `ambience` (`auto` / `true`
  automatic, a bed name or a list, `false`), else the top-level `ambience` (bool, default true =
  automatic). `Stage.light_marks`: `(0, params.light)` and, per `change_light`, `(start +
  seconds / 2, preset or None)`. `Stage.timings()` appends the beds after the rain and fire ones,
  with the rain spans of the foley-kept rain fields.
- **Door foley**: `_played` maps a `PropReshape` to `PlayedAction(prop=kind)` and a `Walk` to
  `through_door` (it fades in or out: a door passage, §69.42) and `opens_door` (`Walk(opens_door=)`,
  set by `enter` / `exit` from `_door_closed` before `_door_x` opens it). `door_cues`: `open` →
  `creak` (−8 dB, 0.9 s) at the start; `close` → `creak` (−10 dB, 0.5 s, +2 st), then `thud` (−6 dB,
  0.3 s, +5 st) at `RESHAPE_SHARE` of the action, when it shuts. A walk through a door plays no
  whoosh / swoosh (it fades in the doorway; the Step 109 gap), and a creak first when it opened
  the door. An open door or one that is already in the asked shape makes no sound (no animation).
- **Water**: a boat's `ride_to` adds `splash` (−12 dB, 0.9 s, −3 st, intensity 0.3) at its start;
  a `pour`'s `WaterFlow` → `PlayedAction(pours=True)` → one long soft `splash` (−10 dB, +7 st,
  intensity 0.15, as long as the water runs, 0.2–3 s) from `pour_flow`'s start +
  `POUR_FALL_SECONDS` 0.25; `wet_steps(cues, wet_from)` adds a `splash` (−14 dB, 0.25 s, +4 st,
  intensity 0.2) under every footstep from the first puddles' start (`Stage.puddles`) on.
- **`knock`** (`scenes/knock_action.py`, non-animating like `switch_on`, `run_time` 0.75):
  targets door props (a room's doors or a `door` prop; validate names the stage's doors otherwise,
  and a scene without `knock_on`); `cue` → `Stage.knock_on(patterns, time)`: one `knock` at
  `KNOCK_GAIN` −3 dB with foley, however many doors match. Nothing moves (a knock from outside).
- **Compatibility, decided**: the automatic beds are on by default (top-level `ambience: true`),
  as the step asks ("chosen automatically where it fits"), so a project rendered again sounds
  different: outdoor day stages gain birdsong, rooms a room tone; door passages creak instead of
  whooshing, a boat ride splashes. Turning it on only for new projects was rejected: nothing tells
  an old project from a new one but a key `vidgen new` would write, and authors who write YAML by
  hand would never get it. `ambience: false` (top level) brings back the earlier beds; `foley:
  false` silences all. Pixels are untouched (no drawing changed).
- **Not done**: no door rattle or visible shake on a knock (nobody needs to stand there); no
  splash when getting in or out of a boat or for a fruit falling into water; the knock and creaks
  are centred (not panned by the door's x); birdsong ignores snow and fog; a light action's
  fade counts as one instant (its middle); no listening by a human. Tests:
  `tests/test_cartoon_sounds.py` (13 without rendering, 2 tiny renders).

### 69.63 More music: the `cartoon` and `lullaby` beds (Step 129)

- **Searched first**: the beds of §48 (`music.py`: `_pads`, `_partials`, `_pluck`, `_bell`,
  `_circular_add`, `_finish`, `BUILTIN_BEDS`, `bed_loop`), `sfx._filtered` / `_band` /
  `_lowpass` for the noise tick. Both new beds are made the same way: numpy only, no recordings,
  no samples, seeded `crc32("music:<name>")`, rendered circularly, `_finish`ed to `MUSIC_LEVEL`
  −28 LUFS integrated. Original melodies written for vidgen (no known tune, lullaby or theme).
- **New voices** (`music.py`): `_pizzicato` (3 ms attack, harmonics 1–5 at 1 / .45 / .22 / .1 /
  .05, the upper ones decaying faster), `_music_box` (1.5 ms strike, a second tine 3.5 cents
  sharp at 0.3 for a slow shimmer, a faint octave, a short ping at 5.4×), `_woodblock` (60 ms,
  partials 1 and 2.76, 0.5 ms strike), `_tick` (80 ms noise burst, band around 2.2 kHz, 4th-order
  low-pass at 3.5 kHz); `_add_panned` places a mono note in the stereo loop.
- **`cartoon`** (45 s = 24 bars of 4/4 at 128 BPM, G major): the score is data, `_CARTOON_BARS`
  (chord, voicing, bass on beats 1 / 3 and an optional pickup, melody in eight eighth slots) in
  six 4-bar phrases: A (G C D7 G), A' towards the dominant (G Em A7 D7), B syncopated and lower
  (C G/B Am D7), A an octave up, C a call and response with the woodblocks (Em Am D7 G), a
  turnaround (C D7 G D7) whose last bar runs back into the top. Pizzicato melody B4–D6 (pan
  +0.2, off-beats at 0.8), a pizzicato bass D2–E3 bouncing root–fifth, short pizzicato chords on
  beats 2 and 4 (three notes spread by 60 samples, pan −0.35), percussion per phrase
  (`_CARTOON_PERCUSSION`: ticks, a high woodblock 1250 Hz right, a low one 880 Hz left; each
  phrase's fourth bar a fill), a pad at 0.1. Layers before levelling: plucks −7.9 LUFS, pad
  −16.8, woodblocks −23.1, ticks −30.3.
- **`lullaby`** (45 s = 16 bars of 3/4 at 64 BPM, F major): `_LULLABY_BARS` (chord, voicing,
  bass, melody as `(note, beats)`); a music-box melody C5–D6 (pan +0.2), a music-box broken
  chord in eighths an octave over the voicing (E4–G5, pan −0.25; one pattern per 4-bar phrase,
  `_LULLABY_PATTERNS`), a soft `_pluck` bass C2–B♭2 on each bar's first beat, a pad at 0.22.
  Layers: music box −9.2 LUFS, pad −10.0, bass −16.3.
- **Measured** (`vidgen list-music --render-dir`, then `loudness.integrated_loudness`): both
  −28.00 LUFS, peak −14.4 / −14.5 dBFS (the others −16.3 to −17.2); energy above 5 kHz −53 /
  −49 dB, below 35 Hz −38 / −46 dB; channel correlation 0.88 / 0.60; 3 s windows −28.7 to −27.2 LUFS;
  made in ~1 s each.
- **Seam test changed**: the old check (50 ms RMS before and after the seam within 1.5 dB) holds
  for a pad but not for a bed whose loop starts on a downbeat with plucked attacks (cartoon
  +6.6 dB, lullaby +5.3 dB: the first note's strike). For beds with a tempo the test now asks
  that the change at the seam lies within the range of that change at the loop's other beats
  (± 0.5 dB); `calm` keeps the 1.5 dB rule. The sample-step and tiled-read checks are unchanged.
  Rotating the loop off the downbeat was rejected: `start: 0` should begin on the top of the tune.
- **Not done**: no time signature field (`Bed` has none; the 3/4 is in the description); nobody
  has listened to the beds (no audio playback here). Tests: `tests/test_music.py` (the
  parametrized bed tests now cover five beds; a score test for both new beds).

### 69.64 Review of Phase L (Step 130)

- **The example**: `examples/cartoon-rainbow-ride` (an original screenplay, `rainbow_ride.md`,
  then a hand-edited `video.yaml`, 6 KB): a title `card` and `iris_in`; an orchard with a tree
  with `fruit`, `birds`, a robot (`species: robot`, a screen face, on wheels, a `party_hat`)
  holding a `watering_can` and pouring, an apple dropped on its head (`dizzy`), a fox (`fox`) who
  gets on a `bicycle` and rides (bell, brakes), `laughing`, a gift picked up, a tint and rain with
  two `lightning` strikes (thunder), `frightened`, the light back to day and a `rainbow`, the fox
  riding on and the robot rolling out; a `crossfade` to an owl's (`owl`) room with a burning
  `fireplace`, a running `clock`, a `kettle` switched on, a `knock` and two entrances through the
  door (a creak), the gift given and opened (`blushing`, `tongue_out`), `night` and a `lamp`
  switched on; `iris_out` on the robot and an end card; the automatic ambience (birdsong, rain,
  fire, room tone) and the `cartoon` bed. End to end by the CLI and the MCP tools `screenplay` (also
  with a `cast` of robots, foxes and owls), `cast`, `validate`, `direct`, `list_music`, `lint`
  (`jobs: auto`), `storyboard`, `character_sheet`; lint clean at preview (word-count timing) and
  with Kokoro audio. `tests/test_phase_l_review.py` repeats the cheap part.
- **`vidgen screenplay` wrote an exit's edge as `side`**: `[X exits right.]` gave `{exit: x, side:
  right}`, which `vidgen validate` refuses (`exit`'s edge option is `to`; `enter`'s is `side`), so
  the draft of any screenplay with such a direction failed. It now writes `to` for an exit.
- **A watering can poured backwards**: a held prop keeps the facing it was drawn with (§69.27), so a
  character facing left poured onto its own feet with a can drawn spout right. `pour` now turns the
  can round about its grip (`Prop.flip`, `facing`) when its spout points behind its holder.
- **A prop held off stage showed at the edge**: a character waiting beyond the edge for its `enter`
  stands half its width outside the view (§69.12), but a prop `hold` gives it (§69.50) is in its
  hand in front of it, towards the stage: a gift showed at the right edge of the room. The construct
  now puts such a holder a further half its width plus the prop's width outwards.
- **Real narration**: Kokoro (narrator `bf_emma` 0.8 (0.85 read 3.58 words/s in one beat), the robot
  `bm_fable` 0.85, the fox `af_bella` 0.8, the owl `af_heart` 0.75), rendered at 1280x720 with
  `--jobs auto` (1 job under the 1500 MB cap): 93.9 s, −16.1 LUFS, true peak −1.9 dBTP.

## 70. Render jobs: `--jobs auto` (Step 117)

- **Formula** (`vidgen/render/jobs.py`, `jobs_for(available_bytes, cores, per_job_bytes)`):
  `min(available_bytes // per_job_bytes, cores)`, at least 1; 1 when the memory cannot be read.
  `choose_jobs()` reads both and returns a `JobsChoice(jobs, cores, per_job_bytes, memory)` with a
  `reason` (`5.2 GB available (/proc/meminfo MemAvailable) / 1.5 GB per job = 3, 2 CPU cores`)
  and `to_json()`.
- **Available memory** (`available_memory()`, `MemoryReading(available_bytes, source)`), standard
  library only; swap is never counted:
  - Linux: `MemAvailable` of `/proc/meminfo`; `cgroup_headroom` walks the process's memory cgroup
    (from `/proc/self/cgroup`) and its parents, v2 `memory.max` / `memory.current` /
    `inactive_file`, v1 `memory.limit_in_bytes` / `memory.usage_in_bytes` / `total_inactive_file`,
    and takes the smallest `limit - (usage - inactive file cache)`; the smaller of the two wins.
    When the group's path from `/proc/self/cgroup` is not under the mount (a container), the
    mount's root group is read.
  - Windows: `ullAvailPhys` of `GlobalMemoryStatusEx` through `ctypes`.
  - macOS: free + inactive pages of `vm_stat` (as `psutil` counts available memory).
  - Other systems: unknown, so 1 job.
- **Cores** (`cpu_cores()`): `len(os.sched_getaffinity(0))` where it exists, else `os.cpu_count()`.
  A cgroup CPU quota is not read.
- **Per-job figure** `PER_JOB_BYTES` = 1.5 GB, from measurements of one scene render at a time
  (`--jobs 1`, `--no-audio`) in a fresh cgroup-v1 memory group, polling `memory.stat` every 50 ms
  (peak anonymous memory of the group = the vidgen command, the worker and its ffmpeg):

  | example | format | peak RSS of the group | largest process | incl. page cache | wall |
  |---|---|---|---|---|---|
  | `cartoon-muffin-mystery` | 640x360 @ 15 (preview) | 291 MB | 252 MB | 439 MB | 53 s |
  | `cartoon-muffin-mystery` | 1920x1080 @ 30 | 756 MB | 717 MB | 995 MB | 191 s |
  | `cartoon-rain-check` | 640x360 @ 15 (preview) | 288 MB | 246 MB | 557 MB | 56 s |
  | `cartoon-rain-check` | 1920x1080 @ 30 | 790 MB | 752 MB | 1104 MB | 195 s |

  (MB = MiB here; 790 MiB = 0.83 GB.) 1.5 GB is about 1.8 times the largest peak: room for
  heavier scenes (pictures, video clips) without the 3 GB of the task list's default, which would
  have halved the jobs on an 8 GB machine for no measured reason. Formats above 1080p are not
  covered: memory grows with the pixel count (0.30 GB at 0.23 MP, 0.83 GB at 2.07 MP), so a 4K
  render needs about 2.5 GB per job; the docs say to give `--jobs N` there.
- **CLI**: every `--jobs` (`render`, `storyboard`, `lint`, `thumbnail`, `slides`, `gallery`) takes
  `N` or `auto` (`_jobs_value`; anything else is a usage error `invalid value: 'x' (a whole
  number, or auto)`; `0` is still the command's `--jobs must be at least 1`). `main` /
  `_run_json` call `_resolve_auto_jobs` before the command: it replaces `auto` by the number,
  prints `jobs: N (auto: <reason>)` on stdout (stderr with `--json`) and, with `--json`, the
  document gets a `jobs` object (`JobsChoice.to_json()`, also on an error document). An explicit
  number adds nothing.
- **MCP**: the tools with `jobs` accept an int 1–16 or `"auto"` (default still 1) and pass
  `--jobs=auto` on.
- **Unchanged**: Kokoro `vidgen tts` has no `--jobs` and runs alone (the MCP server already runs
  heavy tools one at a time); the Python functions (`render_project(jobs=...)` and the others)
  take an int.


## 71. A cartoon host beside any scene (Step 133)

A character of `characters:` presents an explainer: `host:` draws it beside the content of every
scene type that lays out in the safe area. Part 1 (this step): placement, the region split,
speaking, idle life, layout dump and lint. Pointing, reacting, walking between sides and
entering / leaving are Step 134 (§71.1, §71.2). Reference: docs/CONFIG.md "A host beside any
scene".

- **Config** (`config.py`): `VideoConfig.host: Identifier | HostConfig | None` (a name is
  `{character: name}`); `HostConfig(character, side left|right = right, size (0, 0.9] | None,
  place auto|beside|below = auto, floor = true, floor_color = dim, facing auto|left|right|front =
  auto, speaks narrator|own = narrator, pose, expression)`. `SceneConfig.host: SceneHost | None`
  with `SceneHost = bool | Identifier | HostOverride`: `false` none, `true` / unset the video's, a
  name (the video's settings with that character), or `HostOverride` (every key optional; the
  keys written, `model_fields_set`, replace the video's). Variants deep-merge as usual.
- **Which host** (`cartoon/host.py`, no manim): `video_host(config)`, `scene_host(config, scene)`
  (`ValueError` for `true` or a mapping without a character when the video has none).
  `host_problems(config)` runs in `parse_config` (next to the voice references, so variants and
  every command reject them): those two, an unknown character (did-you-mean), a pose /
  expression the character does not know (`cast.pose_name_problem`); a scene's are checked for
  the keys it writes (`scenes[i].host.pose`). `cli.project_problems`: `floor_color` not a theme
  colour (`host_color_problems`) and a scene's own `host:` on a type with `takes_host = False`;
  `validate_warnings`: `speaks: own` for a character without a voice (`host_warnings`).
- **Which scene types**: `NarratedScene.takes_host: ClassVar[bool] = True`; `stage` (its
  characters stand on the set) and `card` (a full-frame title card) set `False` and ignore the
  video's host. Every other built-in lays out in `self.safe_area`; `text_card` centred its text
  on the frame's origin and now centres it on the safe area (equal without reserved room).
- **Geometry** (`host_layout(area, frame_width, frame_height, host, width_ratio) -> HostLayout`,
  pure; `area` = the scene's safe area after the overlays' reserves, as a tuple): `below` when
  `place: below`, or `auto` in a portrait frame (9:16; 16:9 and 1:1 stand beside). Height =
  `size` or `HOST_SIZES` (landscape 0.5, square 0.42, portrait 0.36) x the shorter side (8
  units), capped at `BESIDE_MAX_HEIGHT` 0.95 / `BELOW_MAX_HEIGHT` 0.4 of the area's height and,
  beside, so the column is at most `BESIDE_MAX_WIDTH` 0.4 of the area's width. The column is the
  figure's width (`width_ratio` x height, measured from the posed character) x (1 + 2 x
  `FLOOR_OVERHANG` 0.25) with a floor, else the figure's width. **Reserve**: beside, the
  full-height column at the area's `side`; below, the full-width band at the area's bottom (the
  figure at its `side` end) — the whole column / band, so `overlays.avoid` always keeps the
  content on the intended side. Feet on the area's bottom edge; `facing: auto` looks at the
  content (`left` on the right side). `HostLayout(height, feet, figure, floor, reserve, facing,
  below)`.
- **Drawing** (`cartoon/host_drawing.py`): `build_host(host, entry, *, theme, area, frame_width,
  frame_height, root, motion) -> HostFigure`: `build_character` (the theme's colours, idle per the
  entry's `idle`) at `REFERENCE_HEIGHT` with the facing, pose and expression to measure
  `width / REFERENCE_HEIGHT`, then built again at the layout's height (so its outline has the
  width of a character that tall, §69.1) and shifted so its drawing's middle is on the column's
  middle and its feet on the area's bottom (an arm held out does not push it out of its column).
  The floor is a `Line` across the column in `floor_color`, `OUTLINE_WIDTH x height /
  REFERENCE_HEIGHT` wide (at least a pixel). `HostFigure(VGroup)`: `floor`, `character`, `layout`,
  `config`, `host_name`. No stage code is used (`stage_layout`, grounds, shadows untouched).
- **In the scene** (`scene.py`): `__init__` builds the overlays, then `_build_host()`: the host in
  `self.safe_area` (overlays already reserved, so a bottom caption band stays below it), its
  reserve appended to `_reserved` (§41's mechanism: `safe_area` = the margins' area cut by
  `avoid(area, box, gap=0.2)` per reserved box), so every named region and `place()` call lays
  out beside it, unchanged scene code. `self.host` (`None` without one). `setup()` adds it with
  `add_foreground_mobject`: Manim keeps foreground mobjects last, so while it idles or speaks
  (time-based updaters) Manim redraws only the host each frame over a static image of the rest
  (`get_moving_mobjects` returns the list from the first moving mobject on). Measured at preview
  854x480: a bullets scene of 15.5 s renders in 6.4 s with the host, 5.4 s without; a bar chart
  of 8.1 s in 5.2 s / 4.6 s.
- **Who speaks**: `host_speaks(config, host, voice)`: the host's own voice always; with `speaks:
  narrator` also any voice no other character owns (the narrator's, a named voice nobody
  has); `own`: only its own. `NarratedScene.narrate` calls `_host_speak(beat)` right after the beat
  starts (`self.speak(host.character)`: the beat's viseme track on the scene clock, §69.11) and
  `end_lip_sync` after the beat (on under an overlapping next beat, §69.34), like
  `Stage.narrate`. A beat in another character's voice leaves the mouth at rest.
- **Between scenes**: on screen from frame 0. `host_continues(config, index, takes_host)`: the
  next scene shows an equal `HostConfig` (and both types take hosts) → `finish()` keeps it out
  of the outro's `clear_all` (as carried targets are), so it stands still across a cut. The
  fingerprint gains `next_host` (the next scene's type and `host:`) when the video or either
  scene sets a host.
- **Layout dump**: `HostFigure` → one object of kind `host` named after the character, its box
  covering the floor line; `_character_keys` (`facing`, `speaking`, `face`, `viseme`...) plus
  `side` and `below`. Cartoon rules read kind `character` only, so they do not see the host.
- **Lint** `host_overlap` (layout rule after `overlay_overlap`, default warning, `min_overlap`
  0.02 of the smaller box): the host's box against every scene object and overlay object, except
  particles, motion effects, and scene objects whose box holds the whole host box (a backdrop:
  full-frame image, band); findings on one overlay group together. `covered_text` skips the host
  (this rule's finding). `describe` names it `host 'dot'`.
- **Checked by eye** (scratch project, preview, `vidgen storyboard`): bullets, bar chart, code and
  text_card in 16:9 (also with bottom captions), 9:16 (plain: the host in a band below the
  chart / list / listing; with karaoke captions: above the caption band), 1:1 (beside), a left
  host facing front, happy, without floor; the code scene with `pose: thinking`. `vidgen lint`:
  0 findings in 16:9, 16:9 captions and 9:16 karaoke. Mid-beat stills: the mouth moves in the
  narrator's beats (`speaking: true`, visemes) and rests in a guest's.
- **Not done**: a `zoom` / `pan` moves the host with the scene (it is a scene mobject, not an
  overlay: the host actions need scene targets). A scene type that draws outside
  `self.safe_area` can overlap it (`host_overlap` reports it). The host's idle motion counts as
  change for `dead_air` (as a stage's characters). Pointing, reacting and moving: §71.1, §71.2.

### 71.1 Host actions: pointing, reacting, moving (Step 134)

Six built-in beat actions in `scenes/host_actions.py` (written against `vidgen.api` only) act on
`scene.host`; the host is never a target (they name a scene target, an expression or a side).
Reference: docs/CONFIG.md "Pointing, reacting and moving (host actions)".

- **Common** (`_HostAction(_Acting)`): `alters_targets = False` and the new
  `Action.alters(scene) -> [scene.host]`, which `ActionRunner` adds to the mobjects an action
  changes (`_changed`), so two host actions due together play one after the other.
  `scene_problems`: a type with
  `takes_host = False` (`stage`, `card`) rejects them. `cartoon/host.py`'s
  `host_action_problems` (run by `host_problems` in `parse_config`): a host action in a scene
  without a host, more than one move (`HOST_MOVES`: `host_move`, `host_enter`, `host_exit`) in a
  beat, a `host_react` expression the character does not know.
- **Pointing geometry** (pure, `cartoon/host.py`): `pointed_spot(shoulder, box)` = the point of
  the target's box nearest the shoulder (clamped); `hand_goal(shoulder, spot, room, reach_out =
  HAND_REACH_OUT 0.1)` = the point on the shoulder→spot line as far as the host's room (its
  reserved column / band) grown by 0.1 allows: less than `avoid`'s 0.2 gap, so a pointing hand
  never touches the content. `host_point` sets the look first (`_looked`: `look_pose` towards the
  spot from the head, as `look_at`), reads the shoulder in that state, then
  `Character.reached_parts(hand, goal)` (the two-bone solver of §69.26: elbow bent when the goal
  is nearer than the arm is long, straight when farther) with the near arm (`left`, else
  `right`). The target box is each target's `outline`, else its parts on screen, else its
  mobject. One `PoseChange`; reverted at the next beat (`until_next_beat`) or `until:`.
- **Pointer line** (`line: true`, `color` `dim`): a `Line` from the hand to `POINTER_GAP` 0.12
  short of the spot, `POINTER_WIDTH` 3, growing in the action's second half, its start kept on
  the hand by an updater; it fades with the revert. The layout dump records it as kind `pointer`
  (attribute `host_pointer_of`), which `host_overlap` skips along with the host's own effect
  symbol. Off by default and never added by automatic directing (it crosses whatever lies
  between the hand and the target).
- **`host_look`**: the same look without the arm. **`host_react`**: `posed_state(expression=)`
  and, with `effect`, an effect symbol (§69.40's `show_symbol` / `hide_symbol`, factored out of
  the `effect` action).
- **`host_move`** (target `other_side` default, `left`, `right`; option `speed`). Decision: **the
  content swaps side with the host.** `host_move_plan(area, feet_x, reserve, side, below, to) ->
  HostMove(side, feet_x, reserve, content_shift)` mirrors the feet and the room within the area;
  beside the content `content_shift` is the column's width, towards the side the host left. The
  action moves the camera frame by `-content_shift` (`MoveCamera`, `moves_camera = True`), so
  every scene mobject, also one revealed later, moves on screen together and the scene's own
  layout code needs no second layout; overlays and captions are fixed in the frame and stay. The
  host walks (`Walk`, then a `TURN_SECONDS` 0.3 turn to the content) to the mirrored feet in
  scene coordinates (screen x minus the accumulated shift), the floor line fades out, jumps and
  fades in. In a band below the content (9:16) only the host walks (`content_shift` 0).
  `HostFigure` tracks `side`, `feet_x` and `room` on screen, and `content_shift`; `_room(host)`
  gives the room in scene coordinates for `hand_goal` after a move. A `zoom` afterwards zooms
  from the moved view. The next scene starts on its own `side`; `finish()` keeps the host on
  through the cut only when it is `at_home` (present and on its configured side).
- **`host_enter` / `host_exit`** (target `left` / `right`, default its side; option `speed`):
  a walk between its place and `offstage_x(side, view edges, host.half_reach)` (`half_reach`:
  the drawing's reach from the feet on its wider side, so an animal's tail does not stay in
  view), the floor fading in / out. `starts_present(actions)`: a scene whose first passage is an
  enter starts with the host parked off screen (`NarratedScene._park_host` in `setup()`); its
  room stays reserved either way, so the layout never jumps. `host_exit` clears `pointing_at`.
- **Layout dump**: the `host` object's `side` is `HostFigure.side` (where it stands now), plus
  `pointing_at` while it points.

### 71.2 Automatic host directing (Step 134)

`cartoon/host_directing.py` (no manim). Reference: docs/CONFIG.md "Automatic host directing".

- **When**: `directing_kinds(beat.auto_direct, host.auto_direct, video auto_direct)` per beat
  (the nearest wins; new key `auto_direct: bool` on `HostConfig` / `HostOverride`).
  `directing_used` also looks at hosts' `auto_direct`. `NarratedScene.auto_actions` now returns
  `host_directions(project, spec, cls, params)` by default (`stage` overrides it unchanged).
- **What a scene reveals**: the class method `NarratedScene.reveal_steps(params) ->
  list[RevealStep(focus, result)]`, one per step passed to `reveal()`, mapped to beats with
  `layout.distribute` exactly as `reveal()` does. Built-ins: `bullets` `item<N>` per item
  (`reveal: all`: `item1`); `bar_chart` per bar (`per_beat`: `value_trend` of the bar and the one
  before; `all`: the last bar with the trend first→last) plus the `highlight` bar's step;
  `line_chart` a series per step with its first→last trend; `code` per `highlight` entry
  (`line<N>`, `lines:<a>-<b>` when contiguous, `error` when `has_error_text` finds error,
  exception, traceback, fail(ed/ure/s) or panic in the marked lines; none: `listing`).
  `value_trend`: `rise` / `fall` when last − first exceeds `TREND_SHARE` 0.05 of the largest
  magnitude.
- **Planner** `plan_host_directions(beats: [HostBeat(id, actions, kinds, steps)], present)`,
  pure, simple rules per beat: skip a beat with a written move (moves are the author's: they
  change the layout, so automatic directing **never adds a move**, which also keeps "at most one
  move per beat") or while the host is off screen (tracked through enters / exits); `gestures`:
  `host_point` at the first revealed focus not pointed at before in the scene (one point per
  beat) unless a `host_point` / `host_look` is written; `looks` (when no point was added and none
  written): `host_look` at the first target of a written `highlight` / `callout` / `zoom` at its
  `at`, else at the beat's first focus; `reactions`: the beat's first result →
  `host_react` `HOST_REACTIONS` (rise happy, fall worried, error surprised) at `REACT_AT` 0.4,
  with `HOST_EFFECTS` (sparkle, sweat, exclaim) as `effect` when `effects` is on, unless a
  `host_react` is written. Every action is `ActionConfig.automatic` (shown as `(auto)` by
  `vidgen direct` and the storyboard).
- **Lint-safe by construction**: the hand stays in the host's room (`hand_goal`), looks and
  reactions change only the host, the effect symbol is the host's own (skipped by
  `host_overlap`), no pointer line is added.
- **Example** `examples/host-explainer` ("Why Bread Rises", about 58 s, an original mouse host):
  `host_enter` on the title, automatic points at bullets and bars and `happy` + sparkle as the
  bars rise, a written `host_point` with `line: true` on a `process` column, `host_move` and
  `host_exit` on the closing `text_card`. `vidgen validate` and `vidgen lint` (preview) clean;
  stills checked by eye. Step 144 gave its beats `emotion:` (§72) and slowed `af_heart` from 0.95
  to 0.75 (at 0.95 the real Kokoro lines ran at 3.6–4.6 words/s, `narration_speed` warnings): 66 s
  with Kokoro narration; `vidgen lint --readback` finds only `unclear_speech` word flags (3
  warnings, 7 info).
- **Not done**: no `reveal_steps` for the other built-in scene types (the host only looks at
  their written highlights); the host does not dodge a pointer line crossing other content; a
  walk across passes in front of the content mid-beat (by design: it lasts about two seconds);
  a `host_enter` on a scene with its own entrance animation starts after that animation.

## 72. Voices with feeling, part 1: Kokoro (Step 135)

Reference: docs/CONFIG.md "Voices with feeling (`emotion`)". The owner found Kokoro's lines flat
(Juno in "Rain Check"); `emotion:` gives a line a feeling without a new model.

- **Config**: `emotion: NAME | {like, speed, pitch, gain, pauses}` (`EmotionSetting`;
  `EmotionName` literal = `emotions.EMOTION_NAMES`, a test keeps them equal; `EmotionConfig`
  ranges speed 0.5-2, pitch -3..3 semitones, gain -12..6 dB, pauses 0.25-3) on `BeatConfig`,
  `VoiceConfig` and `VoiceEntry`. `voices.SPEAKER_FIELDS = {"emotion"}`: `resolve_voice` does not
  pass the base voice's emotion to a named voice (it names that speaker, like `label`).
  `Project.beat_emotion(beat_id) -> Prosody | None`: the beat's, else its effective voice's;
  `None` when unset or neutral. `has_own_audio` also compares the beats' emotions.
- **Table** (`emotions.py`, no manim): `Prosody(name, speed, pitch, gain, pauses)`, frozen and
  hashable; `EMOTIONS` 13 rows (neutral, happy, excited, sad, angry, worried, scared, surprised,
  calm, doubtful, sleepy, whisper, shout); `prosody(setting)`; `EMOTION_WORDS` (manner words →
  rows) and `manner_emotion(manner)`.
- **Providers**: `get_provider(voice, emotion=None)`; `beat_providers` makes one provider per
  (voice name, emotion) (Step 135: Kokoro only; since Step 136 every provider, §73).
  `tts.emotion_warnings` (in `tts_warnings`): §73. The dry run names the emotion.
- **Kokoro** (`KokoroProvider(voice, emotion=...)`): `spec()` gains `emotion: {name, speed,
  pitch, gain, pauses}` only when there is a non-neutral emotion (so every existing hash, the
  pinned ones included, is unchanged). `spoken_speed` = voice speed × emotion speed (clamped to
  0.25-4) is passed to Kokoro, whose word timings already reflect it. After synthesis
  (`tts/prosody.py`, numpy): `inner_pauses(timed)` (punctuation tokens `, ; : — – . ! ? …` with
  a word after them; ≥ 0.02 s), `scale_pauses` (above 1: silence inserted at the pause's middle,
  `(pauses − 1) × max(pause, natural_pause)` with `CLAUSE_PAUSE` 0.2 s / `SENTENCE_PAUSE` 0.4 s,
  because Kokoro's own comma pause is ~0.05 s and scaling it alone is inaudible; below 1: the
  middle `(1 − pauses) × pause` cut) returning edits, `shift_time` moving every token time and
  every phoneme time (`last_phonemes`, so the viseme track follows), `apply_gain` (a tanh soft
  limiter above 0.7 of full scale towards 0.98 for boosts), then `pitch_filter` →
  `asetrate=r·2^(st/12),aresample=r,atempo=1/…` passed to ffmpeg with the MP3 encode
  (`convert_to_mp3(..., filters=)`, `pcm_to_mp3(..., filters)`): the length is kept, so nothing
  else moves. Pauses need the word timings: English (`a` / `b`) only.
- **Weighted blends**: `kokoro_voices.blend_weights("af_heart+af_bella:0.6")` → `[(af_heart, 0.4),
  (af_bella, 0.6)]` (unweighted parts share the rest; all weighted: normalised; malformed: a
  `ValueError`, a config error from `VoiceConfig` and `voice_provider_problems`).
  `KokoroProvider.voice_for(pipeline)` mixes `pipeline.load_single_voice(name)` packs by weight
  once and passes the tensor as the voice (kokoro 0.9.4's `KPipeline.__call__` /
  `load_voice` accept a `FloatTensor`); `voice_parts` strips the weights, so language and
  validate warnings work as for `,` blends. The voice string is in the hash as written.
- **Screenplays**: `screenplay_project` sets a line's `emotion` from `manner_emotion(manner)`
  (not `neutral`); emotion words are no longer reported as `# TODO:` manners, and a narrator's
  manner that is only an emotion is not either.
- **Measured** (real Kokoro 0.9.4, `af_heart`, CPU, the 15-word line "Not a cloud in the sky, Pip.
  I checked, and the forecast said sunshine all day."; median pitch by autocorrelation, BS.1770
  loudness): neutral 5.20 s / 202 Hz / -25.7 LUFS / comma pause 0.05 s / sentence pause 0.12 s;
  excited 4.85 / 228 / -22.7 / 0.03 / 0.09; sad 6.16 / 185 / -28.9 / 0.15 / 0.35; whisper 5.69 /
  189 / -34.7 / 0.09 / 0.23; shout 5.00 / 232 / -20.7 / 0.04 / 0.10; sleepy 7.01 / 178 / -30.2 /
  0.19 / 0.40; `af_heart+af_bella:0.5` 5.50 / 196 / -25.3. Kokoro's peaks were 0.3-0.6, so the
  limiter did not act. 3-4 s per line after the model load.
- **Not done**: other providers (Step 136, §73); a real whisper (no breathiness: a quieter, slower,
  lower voice); pauses outside English; emotion inside a line (one emotion per beat).

## 73. Voices with feeling, part 2: ElevenLabs and OpenRouter (Step 136)

Reference: docs/CONFIG.md "`emotion` with ElevenLabs and OpenRouter". The same `emotion:`
(§72) is spoken by every provider; without one, every request and hash is as before.

- **Table** (`emotions.py`): `NamedCues(tag, stability, style, instruction)` and `NAMED_CUES`, one
  row per emotion but `neutral` (a test keeps the names equal to `EMOTION_NAMES`);
  `named_cues(prosody)` looks up the emotion's **name** (a mapping's `like`), so these providers
  ignore a mapping's numbers and `like: neutral` changes nothing for them.
- **ElevenLabs `eleven_v3`** (`voicesounds.is_tagged_voice`: provider `elevenlabs`, model id
  starting `eleven_v3`): `Project.spoken(beat)` inserts `"<tag> "` at position 0 of the written
  text with `Spoken.inserted` (term `emotion`), after the voice sounds are voiced, so the tag
  comes first and belongs to no written word: captions, SRT, karaoke timings and the viseme track
  map the alignment past it as they do for voice-sound tags (§69.33). The tag is part of the
  text sent and so of the hash (`cache_key(text)`); `vidgen tts --dry-run` shows it in `says:`.
  The voice settings stay. `readback.compare_beat` drops spoken words that are bracketed audio
  tags no written word claims (`_audio_tags`), so neither an emotion tag nor a v3 voice-sound
  tag counts as a word missing from the transcript. Tags: `[whispers]` and `[excited]` are in
  ElevenLabs' documented v3 tag list (with `[sighs]`, `[laughs]` of the voice sounds); `[happy]`, `[sad]`, `[angry]`,
  `[nervous]`, `[surprised]`, `[thoughtful]`, `[shouting]` are emotion words of its examples;
  `[calm]` and `[tired]` were chosen by analogy (v3 reads free-form tags; untested against the
  real API, which no step may call).
- **Other ElevenLabs models**: `ElevenLabsProvider(voice, emotion=...)` keeps `cues` (none for
  v3); `settings` adds the row's `stability` and `style` changes to the voice's
  `voice_settings`, each clamped to 0-1 and rounded to 3 decimals. The text is never changed.
  The hash follows through the settings in `cache_key` (the kphi3 legacy key then no longer
  matches, as for any other settings).
- **OpenRouter models with instructions** (`openrouter.takes_instructions(model)`:
  `INSTRUCTION_PREFIXES` `openai/`, `google/`): `OpenRouterTTSProvider.instructions` = the
  voice's own `instructions` (a full stop added when it has none) + `" "` + the row's sentence, or
  the sentence alone; `request_body` sends it. `spec()` keeps `instructions` as the voice's
  (pinned keys unchanged) and gains `emotion: {name, instruction}`.
- **Other OpenRouter models**: no instructions and no word timings, so `with_prosody(mp3,
  emotion)` changes the returned audio as Kokoro's is changed, without the pauses: decoded at
  24 kHz mono (`sfx.decode_audio`), `prosody.apply_gain` (soft-limited boost), then
  `prosody.tempo_filter` (`atempo`, 0.5-2) and `prosody.pitch_filter` in the MP3 encode
  (`kokoro.pcm_to_mp3`). `spec()` gains `emotion: {name, speed, pitch, gain}` (not `pauses`:
  they change nothing here). An emotion whose speed, pitch and gain are neutral (only pauses) is
  dropped, so it keeps the plain hash.
- **Providers per beat**: `beat_providers` keys every provider by (voice name, emotion);
  `tts.EMOTION_PROVIDERS` is gone. `tts.speaks_emotion_by_name(voice)`: ElevenLabs, or an
  OpenRouter model with instructions.
- **Validate** (`tts.emotion_warnings`, replacing Step 135's "only kokoro" warning): (1) beats
  whose emotion's numbers differ from its named row on a name-only voice (the numbers are
  ignored); (2) per OpenRouter model without instructions, the beats whose emotion changes only
  speed, pitch and loudness. Kokoro and plain named emotions give no warning.
- **Not done**: OpenRouter's own ElevenLabs models (`elevenlabs/eleven-v3`) are treated like
  any model without instructions (post-processing), not given tags; no ElevenLabs `speed`
  setting; tags not checked against the real API (mocked tests only).

## 74. Fast drafts: `vidgen render --draft` (Step 137)

Reference: docs/CONFIG.md "Drafts". A draft is a render for checking timing and staging: small,
slow-framed and without decoration, with every timing, position, action and the lip sync kept.

- **Settings** (`config.py`): `draft: DraftConfig | None` (`width`, `height` together, `fps`, each
  optional, sizes even). `draft_format(format, draft)`: the set values, else
  `DRAFT_SHORT_SIDE` 240 px on the shorter side at the format's shape (the longer side rounded
  down to even: 426x240, 240x426, 240x240, 320x240), never larger than `format`, and
  `DRAFT_FPS` 8, never more than `format.fps`. `draft` is left out of the scene fingerprint
  (only drafts use it; their format is checked like any render's).
- **The project** (`project.py`): `Project.draft` (set by `Project.load(..., draft=True)`, kept by
  `without_overlays`) wins over the `preview` argument of the path methods: `render_dir` →
  `build/draft[_<variant>][_bare]`, `render_format` → `draft_format`, output names
  `<output>[_<variant>]_draft` (MP4, SRT, chapter list, thumbnail, export stem). So a draft and a
  preview or final render never share a folder or a file, even at the same size and rate, and
  `current_render` / `_usable_render` never take one for the other.
- **The pipeline**: `vidgen render --draft` (exclusive with `--preview`; MCP `render` `draft`,
  which drops `preview`) loads the project as a draft and renders with `preview=True` (a draft is a
  kind of preview: `is_preview` is true too). The worker gets
  `--quality draft`; scene timings gain `render.draft: true`, the combined timings `draft: true`,
  `render --json` `draft`. Hooks see `preview: true` and the draft's `render_dir`.
- **The scene**: `NarratedScene.is_draft` (from its project, set before the host is built).
  What a draft leaves out, each at the place that makes it: the host's and the stage
  characters' idle motion (`stop_idle`: no breathing, swaying, blinking or mood motion); the
  stage's wind (`StageWind` with no swaying props or trailing characters and no updater; its
  `Wind` stays, so balloons and blown props drift as in the video); shadows (`_shadows`); motion
  effects (`action_motion_effects`); particles (`particle_field`: a `ParticleField(drawn=False)`
  with no particles, no ground and no updater; its start, fade out and end stay, so the rain bed,
  storms and thunder follow it); puddles and settling snow (`particles_started`; steps still
  splash from the puddles' start, kept in `_puddles_from`); fog (`_fog`); lightning's bolt and
  flash (`strike_lightning` and rain storms do not reach the light; the thunder stays); the
  light's grade (`StageLight(flat=True)`: the camera is not wrapped, flashes are 0, `changing` and
  `settled` follow the light changes only; stars, window skies and sky bodies still follow the
  grade's changes, so a `light` change still redraws the frame while it lasts).
- **Kept on purpose**: living props, birds, water, rainbows, effect symbols, cards, overlays and
  every sound. Beat starts fall on whole frames at any rate (`narrate` waits relative to the
  beat's start), so a draft's beats may drift by a frame or two of 8 fps from the preview's over a
  scene (measured: up to 0.15 s over 23 s and 0.18 s over 31 s).
- **Measured** (worker wall time, one scene, `--no-audio`, two alternating runs, under the
  1500 MB cap): `cartoon-rain-check` `storm` preview 640x360@15 21.2 / 21.8 s, draft 426x240@8
  8.0 / 8.2 s (×2.6); `cartoon-muffin-mystery` `morning` 25.3 / 25.4 s → 12.7 / 12.8 s (×2.0);
  peak memory of the worker processes at most 0.25 GB (muffin) and 0.28 GB (rain-check).

## 75. Animatic: `vidgen animatic` (Step 138)

Reference: docs/CONFIG.md "Animatic". An animatic is the storyboard's stills held in time with the
narration, with the video's audio and captions: a way to watch the pacing in seconds, made by
ffmpeg alone once the stills are current.

- **Stills** (`animatic.py`, `make_animatic`): the preview format's stills of
  `build/preview[_<variant>]/frames/<scene>/index.json`. A scene whose stills are not current
  (`storyboard.stills_current(..., per_beat=None)`: any count per beat, the format and the render
  fingerprint matching) is rendered by `render_scenes(..., frames=1)`, the storyboard's call; with
  every scene current nothing is rendered and the scenes are not checked again (they were, from
  this config, when rendered). No Manim render is added: the animatic uses no still the storyboard
  does not make, and `animatic.py` is left out of the render fingerprint.
- **Timing** (pure `hold_plan(scenes, frames, fps)`): a still is held up to its time in the video
  (scene start + its scene time), from the time of the scene's still before it, in whole frames:
  within a beat the stills split the beat's time in order and the last (beat-end) still covers it
  until the beat's end (the gap between beats goes to the next beat's stills, as its beat-start
  is the previous beat's end); a scene's first still from the scene's start, the video's first
  from frame 0; a scene's last still until the next scene's first starts (through the scene's
  tail), the video's last to the end. Where scenes overlap (§49) a still is cut at the next
  scene's start and one that would start at or after it is left out; a still held no frame is
  dropped. So each beat's picture is on screen during the beat it belongs to (Step 138 first held
  each still from its own time, which showed a beat-end still through the following beat). The
  scene starts and the length are those of the combined timings, so beat overlaps (§69.34) and
  word-count timing (no MP3s) need nothing of their own. No crossfade between stills or scenes:
  the concat demuxer cannot blend, and a blend would need the filter graph `ff.join` uses for
  scene transitions.
- **Audio**: `render/pipeline.prepare_join` (split out of `join_scenes`, which now calls it and
  `ff.join`) pads the scene WAVs, builds the effects track and mixes music, ambience and
  normalisation exactly as for the video, into `build/preview[_<variant>]/animatic/audio/`; the
  animatic's audio is the video's. `--no-audio`: a silent track.
- **Captions** (pure `with_captions(holds, cues, fps)`; `draw_captions`): the cues of the video's
  SRT (`pipeline.video_cues`, now also what `render_project` writes) cut the holds where they start
  and end; each piece shows the cues spoken then (overlapping beats' cues stacked), drawn with
  Pillow (bold font of `sheets.load_font`, `CAPTION_SIZE` 0.055 of the shorter side, white on a
  plate of opacity `CAPTION_PLATE_ALPHA` 170, 5 % above the bottom, wrapped to 90 % of the width),
  one PNG per still and text in `animatic/stills/`. Pillow rather than ffmpeg's `subtitles` filter:
  that filter needs an ffmpeg built with libass, which not every Windows build has. Default on
  unless the video has a `captions` overlay (`captions_default`).
- **Encoding** (`render/ffmpeg.join_stills`): the concat demuxer with a `duration` per still
  (`write_concat_list(..., durations)`, the last still listed twice), `fps`, `tpad` and
  `-frames:v` for exactly `round(duration × fps)` frames, x264 `-tune stillimage`, the audio
  inputs of `ff.join` (`_audio_inputs`, shared) and its partial-file replace (`_write_video`).
  Output `Project.animatic_path()`: `<output>[_<variant>]_animatic.mp4` in `output_dir`.
- **Interfaces**: CLI `vidgen animatic [PROJECT] [--variant] [--no-audio] [--captions |
  --no-captions] [--jobs] [--output-dir] [--json]`; MCP tool `animatic` (`captions: null|true|false`).
- **Measured** (copy of `examples/cartoon-music-box`, 51.1 s, 2 stage scenes, no MP3s, 21 stills,
  under the 1500 MB cap): no stills 42 s (render of both scenes 34.7 s); stills current 7.0 to
  9.1 s wall (profile: 2.9 s x264 for 767 frames at 640x360, 2.7 s the mix, 1.1 s of it the
  music bed, 1.0 s loading the extensions), captions add 0.2 to 0.5 s; `--no-audio` 3.7 s.

## 76. Ready-made sets, part 1: outdoors (Step 139)

Reference: docs/CONFIG.md "Ready-made sets". `set: NAME` on a stage scene works without
`sets:` for five built-in outdoor sets.

- **Library** (`src/vidgen/data/sets/outdoors.yaml`, package data; Step 140 adds indoor files
  beside it): every `*.yaml` there holds `sets:` in the format of a project's. `includes.builtin_sets()`
  returns a copy (read once, `functools.cache`). Plain YAML rather than Python so a set reads like
  the project sets it can be copied into.
- **Lookup** (`includes.expand_sets`): the project's `sets:` (with its includes) first, else the
  built-in set of that name; `apply_set` merges it with the scene's params by the §69.35 rules
  unchanged. Origins: a built-in set's values are not recorded (`from_set` skipped), so a problem in
  one keeps the scene's own location (`scenes[i].params.props[k]`) instead of pointing at a
  `sets.NAME` the project does not have; moved scene entries are recorded as before.
  `set_reference_problems` checks both and lists both (`sets: ...; built-in sets: city_street,
  park, beach, forest, snowy_hills`), did-you-mean over both. Fingerprints: the expanded params
  carry the set, so an edit of a built-in set re-renders the scenes using it; nothing else.
- **Sets**: each has a gradient sky, a `ground_color`, background (and middle) layer shapes, its
  props at depths, `light`, `ambience`, and marks `stand_left` / `stand_right` (two characters at
  depth 0, clear of every prop within 0.15 of their depth, 16:9) plus marks at its props.
  `city_street`: building blocks, two `shop`s at depth 0.9 (`shop`, `shop_2`), a flat `road` at
  0.5 between them and the pavement, a `lamp` (the existing lamp post with its lantern serves as
  the streetlamp: searched first, it sways and glows `on`), a `bench`, a `bus_stop`; `ambience:
  city`. `park`: hills, a flat `path`, two `fence`s, a `tree`, a `fountain`, a `bench`, two
  `flowers`; `ambience: auto` (birdsong by day, §69.62). `beach`: a sea band in the background
  layer and `water: {left: 0, right: 0.3}` (§69.53's strip with waves) in front on the left, sand,
  the `sun`, a `beach_umbrella`, two `shell`s; `ambience: false` (no sea bed exists). `forest`:
  far pine triangles, trees and pines at depths 0.95 to 0.5, a `bush`, a `log`, `mushroom`s;
  `light: morning`, `ambience: auto`. `snowy_hills`: two hill layers, four `pine`s, a `rock`, snow
  `{density: 0.5, settle: true, settled: 60}` (the full layer from the start, §69.60);
  `ambience: false`.
- **Props** (`cartoon/props.py`, `OUTDOOR_PROPS`, 13 new; primitives and two theme colours like
  every built-in prop, fixed hex where no token fits: asphalt, gravel, white pickets, shell pink):
  `shop` 1.7 (sign board, upper windows, striped awning, a shop window with goods, a glazed door),
  `bench` 0.32 (seat line at 0.4375 = 0.14 of a character, places ±0.7), `bus_stop` 1.35, `road`
  0.12 and `path` 0.08 (flat bands ±`BAND_HALF` 40 prop units long, in `FLAT_PROPS`: no shadow,
  no snow, left out of `prop_overlap`), `fountain` 0.75, `flowers` 0.28 (petals without outlines:
  at that size outlined petals read as black dots), `fence` 0.42, `beach_umbrella` 1.3, `shell`
  0.06, `pine` 1.9, `mushroom` 0.13 (two in a cluster), `log` 0.16 (seat at 0.875, places −1.3 /
  1.2). Seats in `PROP_SEATS` / `SEAT_PLACES` (bench, log); lean edges in `PROP_LEANS` (pine
  trunk, bus stop pole, shop wall); `SWAYS` gains `pine` (6°, 0.4 Hz) and `flowers` (10°, 1.2
  Hz); `SHELTER_PROPS` gains `pine` and `beach_umbrella` (rain stops above them, snow lies thin
  under them). `write_props_png` leaves `OUTDOOR_PROPS` out of its default (props.png
  byte-identical, md5 checked); `docs/gallery/media/outdoor_props.png` (19 KB) shows them but the
  two bands.
- **Gallery**: `tools/make_sets_gallery.py SETS... --work DIR --out PNG` writes a project with one
  stage per set (two generated characters on `stand_left` / `stand_right`), runs `vidgen
  storyboard --jobs 1 --json`, tiles each scene's first still at 320x180 (3 columns, names below,
  64 colours): `docs/gallery/media/sets_outdoors.png` (28 KB).
- **Checked**: a scratch project with the five sets, two characters each on their marks, at
  preview 854x480: `vidgen lint` 0 findings (first run: `off_frame` on edge trees and pines, moved
  in); each scene renders in about 5 s (5–6 s of video), like any stage of that size; stills
  checked by eye.
- **Not done**: no sea or wind ambience bed (the beach and the snowy hills are silent); the road
  and the path do not reach across a stage wider than about 1.5 frames (give them a `scale`); the
  sets are laid out and checked for 16:9 (in a 9:16 frame the props are wider for the frame and
  may overlap the characters' marks);
  `vidgen screenplay`'s `set:` line does not look up built-in sets (a screenplay `set: park; ...`
  keeps meaning a default sky with those props). Tests: `tests/test_builtin_sets.py`.

## 77. Ready-made sets, part 2: indoors (Step 140)

Reference: docs/CONFIG.md "Ready-made rooms". Five built-in sets are rooms (§69.42), read with the
outdoor ones by §76's lookup unchanged.

- **Library** (`src/vidgen/data/sets/indoors.yaml`): `classroom`, `kitchen`, `shop`,
  `living_room`, `bedroom`. `_read_builtin_sets` reads the files sorted by name, so the rooms come
  first in `builtin_sets()` and in validate's "built-in sets:" list. Each is a `room:` (wall
  colour, wallpaper, flooring, one door named `door`, one window; the shop a ceiling and a wide
  shop window without curtains), `light: day` (classroom, kitchen, shop) or `light: indoor` (living room, bedroom), `ambience: room_tone` (what `auto` picks in a
  room, written out), marks `stand_left` / `stand_right` (two characters at depth 0, clear of
  every prop within 0.15 of their depth; checked by `test_marks_are_inside_the_stage_and_clear_of_the_props`,
  which now counts doors and furniture at the wall's depth through `Params.stage_props()` and checks
  every standing prop is inside the stage) and a mark at each seat. Furniture stands `against:
  wall` (depth 0.4, the default wall depth; nothing stands deeper, so the wall stays there);
  pupils' desks at 0.25, the kitchen table and chairs and the shop counter at 0.2: 0.15 or more
  from the wall's furniture, so `prop_overlap` never compares them. Things on furniture are lifted
  (kettle 0.18, till 0.2: the counter's height × the depth scale × `size`, 16:9); the blackboard
  and pictures hang (§69.43). The layout puts the stand marks where the wall behind is low or bare
  (a door, a window, between furniture), so the characters hide little of the set.
- **Props** (`cartoon/props.py`, `INDOOR_PROPS`, 5 new, primitives and two colours like every
  built-in prop): `blackboard` 0.5 (in `PROP_HANGS` at 0.42: hangs above desks; a fixed dark-green
  board, chalk `CHALK` lines: a triangle and three wavy lines of writing), `school_desk` 0.4 (side on
  like `desk`, a sloping lid on metal legs, its chair on the left as drawn: seat (−0.63, 0.35) =
  0.14 of a character, in `SEAT_BACKS`, so the sitter faces the desk; the classroom's face left,
  towards the board), `shelf_with_goods` 0.95 (three shelves of boxes, tins and jars in the fixed
  `GOODS_COLORS`, the same in every theme like a tree's fruit; leans ±0.45), `till` 0.26 (a cash
  drawer, a sloping key top, a display on a stalk), `wardrobe` 1.1 (two panelled doors, a cornice;
  leans ±0.3). Searched first: the existing `table`, `chair`, `desk` (the teacher's), `counter`
  (kitchen and shop, recoloured), `fridge`, `kettle`, `sofa`, `armchair`, `tv`, `lamp` (the lamp
  post, `scale` 0.5–0.6, `on`), `rug`, `picture`, `clock` and `bed` are reused; a kitchen chair is
  the `chair`. `write_props_png` leaves `INDOOR_PROPS` out of its default (props.png unchanged);
  `docs/gallery/media/indoor_props.png` (11 KB) shows them.
- **Gallery**: `tools/make_sets_gallery.py ... classroom kitchen shop living_room bedroom` →
  `docs/gallery/media/sets_indoors.png` (27 KB).
- **Checked**: a scratch project with the five rooms, two characters on their marks, at preview
  854x480: `vidgen lint` 0 findings; each scene renders in about 3.5 s (2 s of video); stills
  checked by eye. Tests: each room validates with two characters, every seat is sat on (both
  places of a sofa or bed) and every lean leaned on after a walk to its depth, sitting without the
  walk is refused, overrides (light, room key by key, a prop changed by name), lint rules on a
  tiny render of each, two tiny renders of characters sitting (sofa, school desk).
- **Not done**: like §76, laid out for 16:9 only; the lifts of the kettle and the till are frame
  fractions, so in 9:16 they float or sink (give them another `lift`); no shop bell or classroom
  sounds; `vidgen screenplay` does not know the rooms or the new props' other words (chalkboard,
  cash register, closet).

## 78. Flag badly spoken words (Step 141)

Reference: docs/CONFIG.md "Readback" (words to check) and the `unclear_speech` lint rule. A voice
can say every word of the text and still sound wrong (the owner heard a Kokoro line as "two
Russian words"); a word error rate of 0 misses it. The recogniser's own confidence and its word
times show where.

- **Transcripts** (§57): `TranscriptWord(text, start, end, probability=None)`; faster-whisper's
  `word.probability` is kept (ElevenLabs gives none). `Transcript.word_probabilities()` (parallel
  to `word_texts()`), `has_probabilities`; JSON words `[text, start, end(, probability)]`, so
  older cache files still load. `run_readback` transcribes again a cached faster-whisper
  transcript with words but no probabilities (local and free; an ElevenLabs one is kept: no
  probabilities to gain). `CACHE_VERSION` stays 1.
- **Decoding**: `stt.faster_whisper.load_audio` decodes with the ffmpeg executable
  (`render.ffmpeg.decode_mono(path, rate)`: `-ac 1 -ar 16000 -f f32le pipe:1`, 1-D float32),
  not PyAV: no PyAV version can break it (Step 54's PyAV 19 fix decoded with `sfx.decode_audio`,
  which stays for the other callers). Loading the model sets the `faster_whisper` logger to
  WARNING (Step 144): `vidgen lint --readback` imports Manim, whose logging setup at INFO
  otherwise printed faster-whisper's "Processing audio" line per beat among the progress lines.
- **Alignment kept**: `compare_beat` stores on `BeatReadback` the `transcript` and `heard_spoken`
  (heard word index → aligned spoken word index, `None` for an extra word; voice sounds' heard
  words, skipped, are absent), and on each `Edit` its `heard_indices` and `written_index` (not in
  the JSON). The helpers the flags share are public: `term_core`, `written_owner`,
  `entries_by_word`, `entry_says`, `EDGE_CHARS`.
- **Flags** (`speech_flags.py`, no manim): `flag_words(result, spoken, settings, pauses_before)
  -> [WordFlag]`. Units: each compared heard word alone, or the heard words of one edit together,
  plus edits with no heard words (deletions). Per unit: lowest probability `< min_probability`
  → `low_probability` unclear, `< doubtful_probability` → doubtful; a pause before one of its
  words `> max_gap` that is not expected → `gap` unclear; an edit → `mismatch`, unclear for a term
  (`Edit.term`) or 2+ errors, else doubtful (one ordinary word heard differently with confidence
  may be the transcriber's). The level is unclear if any reason is. A pause is **expected** (not
  measured) after a word ending in punctuation (`, . ; : ! ? … — – - ) ] } " ' ” ’ »`) in the
  transcript or in the spoken text (also on spoken words between the two heard ones: not heard),
  before an opening quote / parenthesis / dash, before a written word with a voice sound before
  it (`VoiceSound.word`), and next to skipped heard words (a laugh's "ha ha"); the first word
  has none. Times: the unit's first start and last end in the MP3; a deletion at the end of the
  last heard word before it (0 at the start). `detail`: the edit's `describe()` or the heard word
  (with `(text "...")` when it differs), `heard with probability P`, `after a G s pause inside
  the sentence`. `suggestion`: the edit's; else a pronunciation entry → respell its spoken form;
  a hard term (`hard_term`) → add an entry with a respelling; only a gap → listen, change speed
  or emotion or rephrase, or write a comma; else listen, change voice / speed / emotion or
  respell the word. Each ends with `vidgen tts` (the change makes the audio stale).
- **Settings** `lint.rules.unclear_speech` (`UnclearSpeechRule`: `min_probability` 0.5,
  `doubtful_probability` 0.75, `max_gap` 0.5 s; ordered). The same thresholds serve
  `vidgen readback` (`ReadbackResult.flag_settings`).
- **Video time**: `beat_video_starts(project)` = scene start (`storyboard.scene_starts`, the
  preview's renders, else the final format's) + the beat's start in its scene timings;
  `set_video_times` fills `WordFlag.video_time` (`null` before a render; from the last render,
  so stale if the audio changed since).
- **`vidgen readback`**: always flags (no option): `BeatReadback.flags`, report section `words
  to check: N unclear, M doubtful (thresholds)` with `level beat @ t (video t): detail` and `fix:`
  lines. JSON: `flag_thresholds`, `summary.unclear` / `doubtful`, each beat's `flags` (`scene,
  beat, word, written, level, reasons, time, end, video_time, probability, gap, detail,
  suggestion`).
- **Lint**: rule `unclear_speech` (scope `scene`, default warning, doubtful → `info`; last in
  `LINT_RULES`, in `lint/readback_rule.py`). It runs only when asked: `lint_project(readback=True)`
  (`vidgen lint --readback`, MCP `lint` `readback`) or a `rules` list naming it; otherwise it is
  left out of the rules (`LintResult.rules`). Then, before rendering, `_speech_flags` runs
  `run_readback` on the selected scenes' beats (cache reused; progress lines through `log`, the
  CLI's stderr) and `SceneContext.speech_flags` gets each scene's beats' flags. One finding per
  flag: time = the activity file's beat start + the flag's start; `value` / `limit` = probability
  and its threshold, or the pause and `max_gap`. MCP `lint` with `readback` (or the rule) and a
  paid `stt.provider` needs `confirm_cost`, like MCP `readback`.
- **Checked** on a copy of the `cartoon-music-box` audio (Kokoro, 11 beats; Whisper `small` on
  CPU in the Kokoro venv: ~5 s a beat, killed at 1.5 GB, ran under 2.5 GB): see HANDOFF Step 141.
- **Not done**: no flag for a long pause at punctuation (Kokoro's sentence pauses and the
  emotions' pauses, §72, vary too much for one threshold); the first word of a beat often comes
  out doubtful (Whisper's start-of-clip uncertainty); no per-word audio clip to listen to; the
  `readback` lint rule still reads only the cache.

## 79. Drawing style switch: `drawing:` (Step 142)

Reference: docs/CONFIG.md "Drawing style (`drawing`)". One video-wide switch for how cartoons are
drawn, apart from the characters' looks. `cartoon_style:` (§69.10) stays the words of generated
background prompts; it is not reused.

- **Setting**: `DrawingConfig {outline: thin | normal | bold, shading: flat | soft, texture: none |
  paper | storybook, seed ≥ 0}`, every key optional, at the top level (`VideoConfig.drawing`; a
  variant changes it by the usual deep merge) and as the `stage` param `drawing`.
  `resolve_drawing(*settings) -> DrawingStyle` merges them key by key, later winning (defaults
  `normal`, `flat`, `none`, 0). `NarratedScene.drawing_settings()` lists a scene's settings (the
  video's; `stage` adds its param); `__init__` resolves them into `self.drawing` after the
  overlays and the host are built and before the colour fade is attached; a draft
  (`is_draft`, §74) keeps the outline and drops shading and texture (`DrawingStyle.for_draft`).
- **Applied when drawn**, like the light (§69.31): nothing is recoloured or re-stroked, so the
  generator's pinned digests (Steps 113–125), the layout dump, lint and character sheets are
  unchanged, and a plain style installs nothing (the frames are bit-identical: checked against
  HEAD on `cartoon-rain-check` `storm` and `host-explainer` `grow`).
  - **Outline** (`style_camera`): the camera's `apply_stroke` is wrapped; for a stroke of width
    `w` it scales Manim's `cairo_line_width_multiple` by `max(w·f, min(w, 1 px)) / w` (`f` =
    `OUTLINE_FACTORS`: thin 0.6, normal 1, bold 1.7) around the original call: a thinned stroke
    stays at least one pixel unless it was thinner. On a `stage` (`uses_drawing_style`) every
    stroke (set, characters, props, effect symbols, motion effects, bubbles, particle rings;
    overlays have their own camera, §41); on another scene only what `mark_outlined` marked (the
    host's figure and floor line, §71).
  - **Shading** `soft`: `apply_fill` is wrapped; a member marked by `mark_shaded` (the stage
    marks every character and prop at the start; a host its character) with a one-colour fill is
    filled with a vertical Cairo linear gradient over its own points' height: `soft_stops` =
    the colour 14 % towards white at the top, itself half-way, 16 % towards black at the bottom.
    The colour is read through `camera.get_fill_rgbas`, so the light's grade applies first. The
    path, and so the silhouette, is Manim's.
  - **Texture** (stage only): `attach_texture` wraps the renderer's `add_frame` between the
    overlay layer (§41) and the colour fade (§49): each written frame (a frozen wait: once) is
    multiplied by `texture_shade(texture, seed, width, height)` (cached, H × W × 4 uint16, 256 =
    unchanged; alpha kept): a per-pixel grain (`grain_pixels` large) plus bicubic blotches from a
    grid of `cells` across the short side, `storybook` also darker corners; seeded with
    `numpy.random.default_rng([seed, kind])`. So it lies over everything the scene draws (bubbles
    too) and the fade's colour, under overlays and burned-in captions; frame stills, storyboards
    and animatics show it. It is not a mobject and not in Manim's static image (§69.20): a
    mobject over the moving characters would be redrawn each frame anyway, and the stage's depth
    ordering can move a walker after the last mobject.
- **Cost** (worker, `--no-audio`, `cartoon-rain-check` `storm`, 23 s): 640x360@15 plain 20.7–22.3
  s, thin / bold +3–5 %, soft +5 %, texture +0–8 %, all three +12–18 %; 1280x720@30 plain 56.3–56.6
  s, bold 56.8, soft 58.6, paper 62.2 (most of it the encoder: the multiply is 1.9 ms a frame),
  bold + soft + storybook 65.0.
- **Not done**: no texture on non-stage scenes or under a host; the host's effect symbols and
  pointer line keep their width; bubbles and particles are not left out of the outline weight
  (one rule for the stage's camera); the grain is in screen space (it does not pan with the
  camera); `vidgen character --png`, character sheets and the props galleries draw plain.


## 80. Dubbing: `dub:` and `--all-languages` (Step 143)

Reference: docs/CONFIG.md "Dubbing (`dub`, `--all-languages`)". A dubbed video is the translated
variant of §54 (a `language:` and a translation file); this section adds the voices, the checks
and one command for every language.

- **Setting**: `dub: {LANG: VOICE | {voice, voice_id, model_id, model, instructions, speed, lang,
  settings}}` (`DubVoice`; default none) on `VoiceConfig` and `VoiceEntry`. A string is the
  provider's voice key (`voice_id` for ElevenLabs, else `voice`). `dub_setting` picks the most
  specific key that `language_matches` the video's language. It sits on voices, not on
  `characters:` (the task list's example), because beats name voices: the narrator and a host
  are voices too, and a character speaks only through its `voice`.
- **Rules** (`dubbing.voice_dubs(config) -> {name | None: Dub}`, no manim, nothing without a
  `language`): a given dub wins; a named voice with no `voice` / `voice_id` (and no `lang`) of its
  own follows the base voice's dub (`how: base`); a Kokoro voice whose language letter is not the
  video's (`a` / `b` count as one) and that has no `lang` written gets `auto`: a voice of the
  video's Kokoro language of the same kind (`voice_kind`: second letter `f` / `m`, the
  `voice_kind` of §69.25 screenplays), the least used so far counting the given ones (ties: best
  grade), never a novelty voice (`NOVELTY_VOICES`: `santa`); one source voice maps to one target
  (`chosen`), so two named voices of one speaker stay one voice. A language without the kind
  takes any of its voices (`kind_kept: false`). ElevenLabs and OpenRouter voices are kept (both
  speak many languages; ElevenLabs' `language_code` already follows the language, §54).
  `screenplay.assign_voices` was not reused: it leaves out the narrator's voice and, in a language
  with one voice of a kind, hands a character the other kind.
- **Applied** in `voices.resolve_voice`: the dub's fields go over the named voice's (`_merge_voice`,
  the same rule as a named voice over the base: a Kokoro `voice` without `lang` takes its own
  language); the resolved voice has no `dub` (`DUB_FIELDS`), so `audio_fields`, hashes and the
  provider see only the effective voice. A base voice without a dub is returned as before (the
  same object). So the dubbed beats differ from the base config's: the variant gets
  `audio/<variant>/` (`has_own_audio`), `vidgen tts --variant` voices them, the viseme tracks
  (§69.4) are written from that audio and language, and every timing (VideoPlan, overlaps,
  interrupts, §69.34) comes from those MP3s.
- **Checks**: `voice_provider_problems` adds `_dub_problems` (keys the provider does not use, a
  malformed Kokoro blend). `vidgen validate` warns (`dubbing.dub_warnings`) about a voice dubbed
  without its kind and about voices that differ in their own language but speak with one voice in
  this one (only voices the beats use; a Kokoro blend `target+source:0.3` suggested), and prints
  `dub [pt]: default bf_emma -> pf_dora+bf_emma:0.4 (given), ...` under the language line.
  `kokoro_voices.voice_warnings` no longer warns about the later voices of a blend (they lend
  timbre; the first gives the language).
- **Every language** (`cli.each_language`): `--all-languages` on `tts`, `render` and `lint` runs
  the command for the base config and then each `dubbing.language_variants(project)` (variants
  whose loaded `language` differs from the base config's), sequentially, a heading line before
  each; exit code the worst; `--json` an envelope with `languages: [documents]`. Not with
  `--variant`. MCP `render` / `lint` pass `all_languages`. Lint per language is the existing lint
  of each variant: its timing rules (`talked_over`, `rushed_animation`, `narration_speed`, dead
  air) see that language's lines.
- **Example**: `examples/cartoon-music-box` variant `pt` (pt-BR; `translations/pt.yaml`, 12 texts;
  narrator `pf_dora+bf_emma:0.4` and Gus `pm_santa` given, Fen `pf_dora` and Bram `pm_alex`
  automatic).
- **Not done**: no per-language `overlap` / `interrupt` values (a variant would have to replace the
  scene); OpenRouter voices named after a language (Voxtral `fr_marie_*`) are not swapped; voice
  labels (`Fen:`) are not translatable; Kokoro gives word timings only for English, so a dubbed
  interrupt without `overlap` starts `INTERRUPT_LEAD` before the line's end.

## 81. Composed music, part 1: the `music` extra and the SoundFont (Step 145)

Reference: docs/CONFIG.md "SoundFont (`soundfont`, `vidgen soundfont`)". Phase N plays music
written as notes with symusic 0.5.9 and the GeneralUser GS SoundFont (research report and
listening test after Step 144); this section covers what has to be installed and downloaded.

- **Extra** `music = ["symusic==0.5.9"]` (exact: 0.6.0's `Synthesizer.render` fails with a
  TypeError). `synth.require_symusic()` imports it or raises `VidgenError` naming
  `pip install "schu-video-generator[music]"`, also when another version is installed;
  `synth.symusic_status()` is the one-line state for `vidgen soundfont info`. Nothing imports
  symusic at load time. symusic's own `BuiltInSF` downloader (pySmartDL) is not used.
- **Default SoundFont** (`vidgen/soundfont.py`): GeneralUser GS 2.0.3, `URL` =
  `raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2`, `SIZE_BYTES`
  32,319,396, `SHA256` `9575028c…8cfe` (upstream publishes no checksum; computed by the research
  agent). Never in the wheel (no package data; a test checks `src/` holds no `.sf2` / `.sf3`).
- **Cache folder** (`cache_dir()`; vidgen had none before: Kokoro's model lives in the Hugging
  Face cache): `VIDGEN_CACHE_DIR`, else `%LOCALAPPDATA%\vidgen` (Windows), `~/Library/Caches/vidgen`
  (macOS), `$XDG_CACHE_HOME/vidgen` or `~/.cache/vidgen`; the file is `soundfonts/GeneralUser-GS.sf2`.
- **Download** (`fetch(force, url, progress)`): `httpapi.stream_get` streams 1 MB chunks (stopping
  after more than `SIZE_BYTES`) into a `mkstemp` file next to the target while hashing; size and
  SHA-256 are compared, then `fileio.replace_file` moves it into place; the temporary file is
  removed on every failure. Errors: offline / HTTP status → "cannot download the GeneralUser GS
  2.0.3 SoundFont (…); connect … `vidgen soundfont fetch`, or … set `soundfont: PATH`"; mismatch →
  the sizes and hashes, "may have changed upstream", the same `soundfont: PATH` hint. A mismatch is
  never used.
- **Use** (`resolve(setting, root, download=True)`): `soundfont: PATH` (relative to the project
  folder, or absolute) must be a file with suffix `.sf2` / `.sf3` and a RIFF `sfbk` header
  (`override_problem`; also a `vidgen validate` problem, `soundfont_problems`); else the cached
  default, hashed before its first use in a process (then remembered by size and mtime), else
  downloaded (or, with `download=False`, an error naming `vidgen soundfont fetch`). `soundfont` is
  in `PATH_KEYS` (confined under `vidgen mcp`) and left out of scene fingerprints (audio only).
- **CLI** `vidgen soundfont fetch [--force]` and `vidgen soundfont info [PROJECT]` (path, origin,
  size, sha256, check, licence line, suggested credit, symusic state); no `--json` yet.
- **Licences**: THIRD_PARTY_NOTICES lists symusic (MIT), Prestosynth (MIT), symusic's bundled
  `abc2midi` / `midi2abc` (not run by vidgen; licence unverified) and GeneralUser GS (licence
  v2.0: free use in music, private or commercial; no attribution required). Suggested credit
  (`soundfont.CREDIT`, naming the SoundFont's author, S. Christian Collins, as its licence and
  README suggest) in THIRD_PARTY_NOTICES, CONFIG.md, the README and `vidgen soundfont info`.

## 82. Composed music, part 2: the score and its renderer (Step 146)

- **Score** (`vidgen/score.py`, pure dataclasses, frozen, checked on creation with `VidgenError`
  "score: ..."): `Score(tempo, parts, time_signature=(4, 4), key="C major", sections=(), length=None)`,
  `Part(name, notes, program=0, drums=False, volume=0.0 dB, pan=0.0, reverb=0.2)`,
  `Note(start, length, pitch, velocity=90)`, `Section(name, start, tempo=None)`. A *beat* is a
  quarter note (`tempo` in quarter notes per minute; a 6/8 bar is 3 beats). A drum part's
  `program` is the GM drum kit (0 standard, 40 brushes...). `length_beats` defaults to the last
  note's end rounded up to a whole bar; a section's `tempo` changes the tempo from its start
  (`tempo_changes()`, `seconds_at(beat)`); `key` is `"<tonic> major|minor"` with a standard
  signature (`key_signature()` → sharps, minor; `tonic` pitch class). `fingerprint()` hashes the
  content and `FORMAT_VERSION`.
- **MIDI export**: `to_symusic(score, parts, controls)` builds a symusic score in ticks (480 per
  beat): tempo changes, time and key signature, section markers, one track per part, and (with
  `controls`) volume / pan / reverb as CC 7 (`midi_volume`: 40 log10(v/127) dB), 10 and 91.
  `write_midi(score, path)` writes a type-1 SMF. Both need the extra.
- **Renderer** (`synth.render_score(score, soundfont, cache_dir)`): symusic 0.5.9 ignores CC 7 / 10 /
  91 and pitch bends, ends at the last note and returns floats above 1, so each part with notes is
  rendered alone (48 kHz stereo, quality 0, leading silence kept) and `mix_parts` mixes them in
  float64: gain `10^(volume/20)`, constant-power pan (`pan_gains`: √2·cos, √2·sin of (pan+1)·π/4,
  1 and 1 at the centre), `reverb` × the part sent to one reverb bus; the bus is convolved
  (overlap-add FFT, 2^18-sample blocks) with `reverb_impulse()`: per channel its own seeded noise
  (`crc32("vidgen:reverb")`), low-passed at 5 kHz, 12 ms pre-delay, 60 dB decay over 1.6 s,
  2 s long, unit energy. The mix is cut or padded to the score's length + `TAIL_SECONDS` (3 s),
  the last 20 ms faded, set to `MUSIC_LEVEL` (−28 LUFS integrated) and, only if its true peak
  would pass `TRUE_PEAK_CEILING` (−1 dBTP), limited by `mix.limit`. Silence is an error.
- **Cache**: `cache_dir / "score-<render_key>.wav"` (16-bit; the returned array is always the
  16-bit value, so a cached and a fresh render are identical); `render_key` hashes the score's
  fingerprint, the symusic version, the SoundFont's SHA-256 (`soundfont.content_sha256`: the
  default file's known hash once checked, others hashed once per process by size + mtime),
  `RENDERER_VERSION` and the rate. Written to a temporary file, then moved into place. The mix
  passes `build/music/`; the symusic `Synthesizer` is kept per SoundFont (lru 1).
- **As a music source**: Step 146's internal hook `music.SCORES` was replaced in Step 147 by
  `music: {compose: ...}` (§83).
- `score.py`, `synth.py` and `soundfont.py` are in `NOT_RENDER_INPUTS` (audio only: no scene
  re-render when they change).
- Measured (manual, GeneralUser GS, 2 cores): a 5-part, 16-bar score at 100 BPM (38.4 s + 3 s
  tail) renders in 2.1 s (cached read 0.08 s, identical), −28.00 LUFS, −15.6 dBTP, 376 MB peak RSS.

## 83. Composed music, part 3: the composer and its moods (Step 147)

Reference: docs/CONFIG.md "Composed music (`compose`)" and "`vidgen music preview`".

- **Config**: a music cue takes `compose:` instead of `source:` (exactly one; `MusicCue._one_source`),
  so composed music is a cue like a bed or a file (lists of cues with `from` / `to`, `volume`,
  fades, ducking, scene volumes). `ComposeConfig {mood, key, tempo, instruments, seed=1, bars}`
  (`compose: playful` is short for `{mood: playful}`); `instruments` maps a part (`melody`,
  `chords`, `pad`, `bass`, `drums`) to a friendly name, `none` / null, or `ComposeInstrument
  {instrument, volume, pan, reverb}`. The model validator calls `composer.settings_problems`:
  unknown mood / instrument / part with a did-you-mean (`cartoon.poses.unknown_name_message`), a
  drum kit outside `drums` or the reverse, a key in the other mode, bars not a multiple of 4.
  `MusicCue.label` is `compose: <mood>` for summaries.
- **Composer** (`vidgen/composer.py`, pure, no numpy): `compose_piece(mood, key, tempo,
  instruments, seed, bars) -> Piece` (score, key, tempo, bars, voices, chord names per bar,
  phrases, `harmony` as `(beat, beats, Chord)`; `chord_at(beat)`), `compose(...) -> Score`. Seeded
  by `random.Random(crc32("vidgen-compose:<mood>:<seed>"))`, one more generator per part (so
  changing one part's instrument leaves the other parts' notes alone).
  - *Moods* (`MOODS`): `Mood` holds family, words, key, tempo, meter, default bars, A
    progressions (`themes`) and B / C progressions (`contrasts`) as `Progression(question,
    answer)` of 4 bars each in Roman numerals (a bar may hold 2-4 chords), the melody's range,
    words, rhythm cells (`"1 .5 .5 r1 1"`: beats, `r` a rest), the cadence cells (`half`, `full`)
    and the last bar (`turn`), articulation, the chord / bass / drum pattern names, default
    parts (`RoleDefault` instrument, volume, pan, reverb), the fallback bed, bass and chord
    registers. A test checks every question ends on V and every answer on I.
  - *Chords* (`parse_chord`): case gives major / minor, `°` `ø` `+`, `7` `maj7` `6` `9` `sus2`
    `sus4` `add9`, `/3` `/5`, `b` / `#` before the numeral; each tone is `(scale degree, pitch
    class)`, so `Chord.scale(key)` is the key's scale with the chord's tones on their degrees (the
    raised leading tone over V in minor, the raised fourth over II); names are spelt from the
    key's letters (`Gb`, not `F#`, in B♭ major).
  - *Form* (`form`): blocks of A-question, A-answer, B (C in every second block)-question,
    A-answer; the rest A / A A / A B A; the last phrase is an answer whose last bar becomes
    `I V7` (`i V7`). Each letter picks one progression per seed (C another than B).
  - *Melody*: per letter a motif of three rhythm cells (bar 1, bar 2, the answer's bar 3; a
    question repeats bar 1's cell in bar 3; a return varies bar 2 / 3 by splitting the longest
    note or merging two) and a shape (semitone offsets per anchor, inverted on a return). The
    first note of a bar and notes on strong beats (1 and 3 in 4/4, 1 in 3/4) are *anchors*: a
    chord tone of the chord sounding there, nearest to an arch target (a question rises and
    stays up, an answer comes down; B higher, C lower) plus the shape, within a sixth of the
    previous anchor, not repeating it; an answer's cadence takes the tonic nearest below or at
    the previous note, a question's the V chord tone nearest it. The notes between anchors
    follow the straight line to the next anchor in steps of the chord's scale (a chord tone for a
    leap over 4 semitones), the last ones leading back to the first note. A bar equal to the bar
    before (cell and first pitch) takes the second-best anchor or a varied cell. The melody's
    range is the mood's moved by octaves into the instrument's (`fit_range`).
  - *Accompaniment*: close-position voicings with the inversion nearest the previous one
    (`_voicing`); patterns `pad`, `block`, `arpeggio` (eighths; a shape per letter), `broken`,
    `oompah`, `ostinato` (root / fifth / octave), `strum` (staggered 15 ms per note); a chord
    starting off the pattern's onsets is struck there; an event is cut at a chord change.
    Bass patterns `sustain`, `half`, `root_fifth`, `walking` (with a chromatic approach to the
    next root), `pulse`, `pop`; the root of an inversion is its bass note. Drum patterns
    (`DrumPattern`: hits in 4/4, the phrase-end fill from `fill_from`, a cymbal at each new section
    when `crash`, a generic 3/4 bar from `backbeat` / `tick`). Velocities are humanised ±4 (drums
    ±5) by the part's generator; B / C drums play 8 % harder.
  - The score is `balance=True`, its `length` exactly the bars (notes are cut at the end), its
    sections named `A1 question`, `B1 question`...
- **`Score.balance`** (new field, default false): `synth.mix_parts` first sets each part's dry
  render to `BALANCE_LEVEL` (−28 LUFS integrated; measured from its first to its last sample
  above −120 dBFS since Step 149, §85), then applies its `volume`. GeneralUser GS's
  instruments differ by up to ~40 dB as symusic renders them (pizzicato −59 LUFS, horn −13 LUFS
  for the same note), so the moods' volumes are levels against the other parts. Render time
  of a 16-bar mood: ~4.5 s (2 cores; ~2 s without the per-part loudness measurement).
- **As a music source** (`music.Source`): `source_kind(cue)` gives `composed`, `bed` or `file`;
  `composed_score(cue)`; the render (`render_score`, cache `build/music/`) is the piece plus
  `TAIL_SECONDS`: looped, the tail is added circularly onto the piece's start (the last bar
  leads back to the first), the first pass is the piece without that tail, and `start` wraps
  around the piece; `loop: false` plays the piece and its tail once. `crossfade` does not apply.
  Without symusic 0.5.9 (`fallback_bed(cue)`) the mood's bed plays (`Mood.bed`: calm → calm,
  focused / tense → pulse, curious / upbeat / triumphant → bright, playful → cartoon, sleepy →
  lullaby) with a warning naming the install command; the summary then says `kind: bed`,
  `source: "compose: <mood> (bed <bed>: no music extra)"`.
- **Instruments**: 42 friendly names → GM programs with a playable range and words, and 5 drum
  kits. Not offered, measured with GeneralUser GS 2.0.3 and symusic 0.5.9: pizzicato strings
  (45) and xylophone (13) render a 5 ms click and silence (FluidR3 Mono plays its pizzicato), and
  bright piano (1) is the piano's sound. All drum keys the patterns use sound in all five kits.
- **CLI**: `vidgen list-music` adds the moods (`composer.mood_entries`, `describe(mood)` built
  from the parameters, so the words follow the code) and the instruments
  (`instrument_entries`); JSON keys `moods`, `instruments`, `symusic`. `vidgen music preview`
  (`cli.cmd_music`) composes the project's first `compose:` cue changed by `--mood`, `--seed`,
  `--bars`, `--key`, `--tempo` (another mood starts from its defaults) or the mood alone, renders
  it with the project's SoundFont (no cache) and writes `<mood>-seed<S>.wav` and `.mid` into
  `--out` (default `.`).
- `composer.py` is in `NOT_RENDER_INPUTS`. Measured samples (scratchpad, not committed): every
  mood −28.00 LUFS, true peak −13.0 to −17.1 dBTP, 33-47 s with the tail, 4.4-6.1 s to render.

## 84. Composed music, part 4: music that follows the video (Step 148)

Reference: docs/CONFIG.md "Music that follows the video".

- **Which cues.** A `compose:` cue without `bars` (`musicfit.is_fitted`) is composed in
  `mix.plan_music` from the combined timings, when the scenes are joined; with `bars` it loops as
  in §83. Without the extra the mood's bed plays (§83). `start` and `loop` do not apply.
- **Inputs** (`musicfit.cue_inputs`, reads the config and the timings): a `Slot(scene, start,
  settings, button)` per scene of the cue (seconds from the cue's start: the scene's start, plus
  half its transition's `overlap`); reveal times (the beats in which the scene type's
  `reveal_steps` show a step, mapped with `layout.distribute` as host directing does; written
  `reveal` actions at their `at` share of the beat; `sting_reveal` events of the timings); pauses
  `Pause(start, end)` (a beat's `music_pause: true`; automatically a `card` scene that is not the
  cue's first, until its first beat ends; the cue's last beat when it has at most `PAUSE_WORDS`
  8 words and its scene another beat, unless `music_pause: false`). That last pause adds a
  `button` slot where the line ends (when at least `BUTTON_MIN` 0.3 s remain).
- **Settings** (`Settings(mood, key, tempo, instruments, seed)`; `cue_settings`,
  `scene_settings`): a scene's `SceneMusic` (new optional fields `mood`, `key`, `tempo`,
  `instruments`, `seed`; `compose_keys`) changes the cue's for that scene: another mood starts
  from its defaults with the cue's seed; the same mood keeps the cue's settings, replaces `key`,
  `tempo`, `seed` and adds `instruments`. `VideoConfig._scene_compose_problems`: only under a
  fitted cue, and the result must pass `composer.settings_problems`.
- **Sections** (`plan_sections(slots, seconds, limit=TEMPO_LIMIT)`, pure): a slot shorter than
  one bar at the fastest tempo joins the next (the last, or one before the button, joins the one
  before). `_fit` picks the bar count whose tempo (`60 · Σ stretch / seconds`) is nearest the
  settings' within ±`TEMPO_LIMIT` (8 %); when even −8 % is too fast, the tempo is −8 % and the
  missing time is a *hold*: added to the last bar's beats with weights 1..meter (`_hold`; no beat
  under 20 BPM, the rest spilling over the section). When one bar at +8 % is too long (a cue
  shorter than a bar), one bar at the tempo it needs. The last section *closes*: its last bar's
  beats last `CLOSE_STRETCH` 1.3 beats and the bar before slows by `RIT_STEP` 6 % more per beat;
  a button is one bar of plain beats at whatever tempo fills it (20-300 BPM: under 0.8 s in 4/4
  it runs past the cue's end, cut there). Each `FitSection` keeps its per-beat `stretch`;
  `TempoMap.of(sections)` is the tempo of each beat, with `seconds_at` / `beat_at`.
- **The piece** (`fit_music(sections, reveals, pauses)`, pure): each run of sections with equal
  settings is one `compose_piece(..., bars, ending)` (new `ending`: `loop` as before, `cadence`
  for the last run, `open` for the others; any bar count when not looping: whole phrases of
  `form`, then a tag repeating an answer's last `bars % 4` bars). `cadence`: the last bar is the
  tonic alone (`_Bar.closing`: the melody holds the tonic, the chords hold the chord whatever the
  pattern, the bass holds the root, the drums play one kick and cymbal) and the bar before ends
  on V7 if it did not end on V. Parts are merged by (role, program, drums, volume, pan, reverb);
  another instrument for a role becomes `"<role> 2"`. Score sections: one per fit section (named
  by its scenes) and one per tempo change inside (`hold` / `a tempo`); `length` the total beats;
  `time_signature` and `key` the first run's, and each run's first section carries its own
  (`Section.key` / `time_signature`, Step 149; MIDI only: the audio follows the notes).
- **Swells**: each reveal at the nearest beat (`_swell_beats`: not before beat 1, not in the
  closing bar, not in or one beat before a pause, `SWELL_BEATS` 2 apart); notes in the 2 beats
  before grow to `SWELL_GAIN` ×1.2 velocity, the beat on it ×1.2, and a chord tone near E5 (not
  one struck there already) is held 2 beats in the pad, else chords, else melody part.
- **Pauses** (`_pause_windows`): from the last whole beat at least `PAUSE_LEAD` 0.4 s before the
  beat to the first bar line after it ends (the closing bar at the latest); notes starting inside
  are dropped, notes sounding into it end at its start (`_cut`).
- **Cache**: the fitted score is hashed like any score (`render_key`), so its tempo changes and
  notes — the section plan — are in the key: new timings compose and render again; unchanged
  timings reuse `build/music/score-<key>.wav`.
- **In the mix**: `Source(..., fitted=score)` plays the render once from the cue's start;
  `Placement.fit` adds `fit: {sections, swells, pauses, closing}` to the cue's mix summary; the
  cue's fade-out never starts before the closing chord (`FittedMusic.closing_seconds`).
  `music.cue_scene_range` is shared by the mix and the stings.
- **Stings** (`sting_score(kind, settings)`, pure): in the settings' key, tempo and voices —
  reveal: melody pickup a fourth below the tonic, then the tonic held 2.5 beats with the tonic
  chord (chords, pad), bass root, kick and cymbal; comic: toms 48, 45 and kick + crash 49 on
  eighths with the mood's kit (standard without drums), the bass and a short tonic chord on the
  last; sad: melody tonic+3, +2, +1, then the tonic held. `composed_stings(project, timings,
  events, library)` (from `join_scenes` before `sfx.write_track`, new `replaced` argument; also
  `sfx.placed(..., audio)`): for each built-in sting event in a scene under a composed cue (with
  the extra, no project `assets/sfx/sting_*` file), the sting of that scene's settings rendered
  (`build/music`), its tail cut to `STING_TAIL` 1.5 s with a fade, scaled to the integrated
  loudness of the built-in sting it replaces. Its `gain`, `at` and the sting ducking stay.
- `musicfit.py` is in `NOT_RENDER_INPUTS`; a beat's `music_pause` is left out of scene
  fingerprints (applied when joined).
- **Measured** (scratch copies, preview): `host-explainer` with `compose: curious` and real Kokoro
  audio (66.1 s, 5 scenes: tempos −8 % with a hold, +0.6 %, −4.4 %, 0 %, −8 % with a hold;
  6 swells): scene changes on bar lines within 0.01 ms (plan and symusic's own tempo map) and
  note onsets in the render within 3.3 ms; `cartoon-rain-check` with `compose: playful` and
  `storm` `{mood: tense}`, word-count timing (75.9 s): within 0.02 ms (plan, symusic), onsets
  within 45 ms (a coarse onset detector), a pause and button before the last line, the comic
  sting played by the playful instruments.

## 85. Composed music, part 5: tooling, examples and the review of Phase N (Step 149)

- **`vidgen validate`** (`music.music_warnings(config)`, in `cli.validate_warnings`): with a
  `compose:` cue and no usable symusic, one warning naming the extra (`synth.symusic_status()`)
  and the bed each composed cue plays instead (and that scenes' compose settings are not
  played); with the extra but no `soundfont:` and the default SoundFont not in the cache, one
  warning that the first render downloads it (32.3 MB) or `vidgen soundfont fetch` does it now.
  A missing SoundFont still downloads (or errors offline) at render time: only the extra's
  absence falls back to the beds (§83), so a final render never silently loses its music for a
  network problem. `music.music_summary(config)` (`{source, kind, plays, fitted, from, to,
  scenes}` per cue) is printed as `music:` lines (`music_summary_line`) and is `validate
  --json`'s new `music` key.
- **Drafts, animatics, storyboards.** No code: `render --draft` and `vidgen animatic` mix through
  `pipeline.prepare_join` like the video, so composed music (fitted to their own timings, which
  differ from the preview's by up to a frame or two of 8 fps per beat) plays in both; the render
  is cached in `build/music/` (shared by preview, draft and final). Measured on scratch copies:
  host-explainer's draft (65.9 s) and animatic (66.1 s, 22 s) carry `compose: curious`;
  composing rain-check's three-mood 93.9 s piece takes 2.0 s and rendering it 18.7 s without
  the cache (21.8 s before the balance fix below), once per timing change, so no cheaper path for
  drafts. Storyboards have no sound.
- **MCP**: `list_music`'s description names the moods; new tool `music_preview` (`vidgen music
  preview --json`, `music` added to `cli.JSON_COMMANDS`, `jsonout.music_preview_document`; `out`
  confined, default `build/mcp/music`, a heavy call); `render` / `animatic` documents carry
  `mix.music[].fit` as before.
- **MIDI export of several moods** (`score.Section.key` / `time_signature`, optional, checked;
  `to_symusic` writes a key or time signature change at a section that changes them;
  `musicfit._score_sections` sets them at the first section of each run of settings).
- **Fix: balance measured where a part sounds** (`synth._sounding`): `mix_parts` measured each
  part's loudness over the whole piece; in a piece of several moods most parts play in one
  stretch, so ~80 % of that time measured silence (13 parts × 94 s for rain-check). Only the
  stretch from the first to the last sample above −120 dBFS is measured now; the gated loudness
  differs only by the half-silent 400 ms blocks at its edges (≤ 0.34 dB on a 2 s tone, less on
  real parts). `RENDERER_VERSION` 2, so cached renders are made again.
- **Fix: `compose: MOOD` in the JSON Schema** (`config._mood_name_schema`): the short form
  (Step 147) passed `vidgen validate` but not `vidgen schema`'s schema (`BeforeValidator` does not
  reach the generated schema); `compose` now also accepts a string there, like `shot:`'s words.
  Found by `tests/test_schema.py` once the examples used the short form.
- **Examples**: `examples/host-explainer` `music: {compose: curious}`; `examples/cartoon-rain-check`
  `music: {compose: playful, volume: -2}` with `storm` `{mood: tense, volume: -3}` (under the rain
  bed) and `night` `{mood: sleepy, volume: -3}` (the two beds replaced); both validate and lint
  with 0 findings on real Kokoro audio.
- **Measured** (scratch copies with real Kokoro narration, 1280x720 @ 30, `--jobs auto`, outside
  the repository in `/home/claude/work/phase-n-review/`): `host_explainer.mp4` 66.13 s, 3.7 MB,
  −16.1 LUFS, −1.8 dBTP; music alone −33.0 LUFS under speech and −25.6 LUFS in the pauses (the mix
  in speech −15.2 LUFS: the music ~18 dB under the voice, ~10 dB under it between lines); 5
  sections (−8 % with a hold, +0.6, −4.2, 0, −8 % with a hold), 6 swells. `rain_check.mp4`
  93.93 s, 11.4 MB, −16.1 LUFS, −1.8 dBTP; music −38.2 LUFS under speech, −29.0 LUFS in pauses
  (plus the rain bed); sections playful −1.3 / −2.5 %, tense +2.2 %, sleepy (3/4) −3.9 %, the
  button bar; the pause before "It rained for the rest of the week." (88.9-92.7 s) and its
  closing chord. Scene changes on bar lines within 0.06 ms (plan and symusic's tempo map); every
  note of the new section starts exactly there (onset detector within 3.3 ms for host-explainer;
  for rain-check it picks an earlier woodblock pickup or the tense strings 70-78 ms before, while
  the 5 ms levels rise at the change).

## 86. Platform worlds (Phase O, Steps 150–155)

Reference: docs/CONFIG.md "Platform levels (`level`)". Side-view platform scenes for kids'
stories: a level written as a small ASCII map, walking along it and jumping between its
platforms from the author's intent, story props, sounds, and a camera that follows the hero.
Designed so that simple computer games could reuse the world and its rules later; games are not
in scope.

### 86.1 Three layers

1. **World model** (`vidgen/world/`, plain frozen dataclasses): a `Level` (a grid of tile kinds,
   its `Spot`s), `Body`s (characters and props: feet `x`, `y` and `height` in *tile units*),
   a `World` (a level and its bodies). Step 152 adds items (keys, doors, coins, stars, friendly
   blockers) as world data beside the bodies.
2. **Rules** (`vidgen/world/`, from Step 151; pure functions): take a world and a scripted
   input (`walk to c`, `jump to cloud`, `pick up key`) and give the next world plus the planned
   motion (paths, arcs, events such as take-off, landing, pickup), deterministic, with a
   `VidgenError` when the input is impossible. A player's inputs could replace the script later;
   no physics engine, fixed paths and simple arcs only.
3. **Renderers**: vidgen / Manim now (`vidgen/cartoon/level_stage.py` maps tile units to Manim
   units, `vidgen/cartoon/level_drawing.py` draws the tiles, `scenes/stage.py` shows them).

`vidgen.world` never imports Manim (a test imports it, `level_stage` and `level_drawing` in a
fresh interpreter and checks `manim` is not loaded); the drawing uses Pillow only.

### 86.2 A `stage` with a `level`, not a new scene type

A level is the `stage` scene's new `level:` param. The stage already has the characters, their
lip sync, acting and walking, props, shots, the camera's `pan` / `follow` / `zoom`, reframing,
parallax `layers`, light, foley and `sfx`; a new scene type would duplicate or re-plumb all of it.
With a level the stage changes only where the ground is: the tiles replace the ground line and
band, the stage is as wide as the map, and things stand on the tiles at depth 0. Sets (`set:`)
apply as on any stage (their sky and layers; their props stand at depths, so a level asks for
`props: []`).

### 86.3 The map (Step 150)

- One text line per row, top row first; `.` or a space air, `#` ground, `=` platform, `~` cloud,
  `|` ladder; a letter (ASCII, either case, each once) is a *spot*: an air cell with a name
  (`spots: {a: start}`, else the letter itself). Symbols are tiles and (from Step 152) items;
  letters are only ever spots. Blank lines around the map are dropped, tabs expand to 4, short
  rows are padded with air on the right (editors strip trailing spaces). At most `MAX_COLUMNS`
  400 by `MAX_ROWS` 40.
- Inside the model row 0 is the bottom; a cell spans `column .. column + 1`, `row .. row + 1`.
  `STANDABLE` = ground, platform, cloud: a body stands on the tile's top edge. Ladders are drawn
  and parsed; climbing is Step 151's to decide. Outside the map is air (a gap goes down forever).
- A spot stands on the first standable tile below its letter (`Level.surface_below`), so a spot
  under a platform stands on the ground beneath it. A body asked to stand at an x instead stands
  on the highest tile of that column (`Level.top_surface`).
- Errors (`parse_level`, `VidgenError`) name the map's row and column from the top left, both
  from 1, as the author reads the YAML: unknown symbol (with the symbol list), a letter twice
  (both places), a spot with nothing below it, a map with nothing to stand on, a `spots` letter
  not on the map, one name for two letters, too large. `StageLevel` turns them into validation
  errors at `scenes[i].params.level`.

### 86.4 Geometry on the stage (Step 150)

- `CHARACTER_TILES` = 2: a character of scale 1 is two tiles tall, so the tile is
  `size × shorter side / 2` and the characters keep the size the scene gives them. A level's
  default `size` is `LEVEL_SIZE` 0.25 (a `mode="before"` validator fills it when the scene gives
  none): about 8 rows by 14.2 columns in 16:9, 14.2 rows by 8 columns in 9:16. Step 154's
  `character_size` replaces this default (small / medium / large → sizes; `size` keeps winning
  when written).
- `level_frame`: the stage is exactly as wide as the map (`Stage.stage_width`; `width` is refused
  with a level, reframing does not change it), centred, the map's bottom edge on the frame's
  bottom edge. Spots are stage marks at `(column + 0.5) / columns` (frame-independent, so `pan`
  / `walk_to` / `camera_at` validate without a frame). `level_fit_problems` (in `vidgen validate`
  and before a render): a map narrower than the frame (the camera would see past its ends), or
  tiles above the frame's top (the camera moves sideways only; Step 154 keeps that).
- `level_layout` replaces `stage_layout` (`Params.layout`, used by the scene, `stage_frame` and
  `stage_reframes`): `level_world` resolves each item's `at` (a spot by name, else a mark or x
  → tile column), `place_bodies` stands it, and the feet come out in Manim units raised by the
  item's `lift` (frame heights) and `hang`. `Stage.grounds[name]` is the tile's top, so shadows lie
  on the tiles. Depth is refused (characters and props) as are `room` and `water`; `ground` and
  `ground_color` are not used.

### 86.5 Drawing (Step 150)

- `level_shapes(level, colors, outline)`: filled shapes in tile units, back to front: ladders,
  ground, platforms, clouds. The ground is one mass: every cell in ink, then its fill inset by the
  outline width on its open sides (an ink square in each inner corner), grass (`GRASS_DEPTH` 0.2,
  scalloped) on every open top, a pebble in one cell of three placed by `crc32` of the cell. A
  run of platforms is one rounded wooden slab (`PLATFORM_THICKNESS` 0.38) under the tiles' top,
  with plank seams and a light edge; a run of clouds is one puffy cloud whose bumps reach the
  tiles' top; other forms are drawn ink-then-shrunk-fill so the outline follows their union.
  Outline `OUTLINE` 0.04 tile × the drawing style's `outline_factor`; ink is `CHARACTER_INK`.
  Colours `LevelColors` (`colors:` theme tokens or #hex).
- `draw_columns` paints columns `first..last` at `tile_pixels` per tile, `SUPERSAMPLE` 2 and a
  box filter, so chunks drawn separately are byte-identical to one drawing (tested). The scene
  (`Stage._level_tiles`) draws `CHUNK_COLUMNS` 8 columns per `ImageMobject` (plus one column
  under the next chunk: the resampled edge of a picture is half transparent and showed a seam),
  at `LEVEL_OVERSAMPLE` 1.25 × the frame's pixel density (1 in a draft; fewer pixels when the
  pictures would pass `LEVEL_MAX_PIXELS` 24 M), up to the used rows + `TOP_ROOM` 0.25. No disk
  cache: drawing a level takes tens of milliseconds and the scene render itself is cached.
- `LevelTiles` (a `Group`, named `level`; chunks `level_1`...) keeps as members only the chunks
  that overlap the camera's view (a camera listener), because Manim transforms every
  `ImageMobject` on every frame whether it is in view or not. In the layout dump each chunk in
  view is an `image`.
- Behind the level: a background picture is drawn larger (`layer_half_extent`) and moves by
  `LEVEL_PICTURE_FACTOR` 0.2 (`_move_by_parallax`, shared with `layers`); a colour or gradient
  sky is as before (it looks the same from any camera position); `layers` as on any stage. The
  light grades the tiles (they are in the backdrop, `mark_lit`).
- Measured: the 42 x 6 scratch level at 854x480 renders 5.9 s of video (a pan across it) in
  6.8 s, like a plain stage.

### 86.6 The rest of the phase (plan)

- **Step 151, walking and jumping.** Rules: `walk` along a run of standable tiles to a spot or x,
  stopping at an edge (a gap or a wall) with a clear error naming where it stops; `jump to <spot
  or x>`: take-off at the edge nearest the target, an arc whose height clears the tiles between
  (sampled against the cells, the body's height in tiles), landing on the target's surface;
  `VidgenError` when no arc within a kid's reach (a few tiles across and up) clears. Output: a
  path in tile units and events (`take_off`, `land`) that the renderer maps to the existing
  `Walk` / `Jump` motion (crouch first, slower arcs, squash and wobble on landing) and the beat's
  narration timing (a step starts at its `at` in the beat and lasts what the walking speed or the
  arc gives).
- **Step 152, props and reactions.** Items on the map (symbols, never letters) or listed by
  spot: key, door, coins / stars, a friendly blocker that moves when asked; rules for pickups,
  doors opening with the key, blockers stepping aside; reactions with the existing `react`,
  `emote` and `effect` actions.
- **Step 153, sounds.** The rules' events (take-off, landing, pickup, door) placed through the
  existing `sfx` system; new synthesised sounds only where none fits.
- **Step 154, camera and `character_size`.** The camera follows the hero sideways (the existing
  `follow`, held inside the stage); `character_size: small | medium | large` at video level and
  per scene (scene, then video, then medium) sets the base `size` (and so the tile size); shots
  zoom from it; captions and on-screen text keep their size; a lint rule for a talking character
  too small to read. Not named `characters:` (the cast list and the stage's placement list).
- **Step 155**: a 2–3 minute original kids' story using only these features, the guide and docs,
  and the review of the phase.

### 86.7 Walking and jumping (Step 151)

Reference: docs/CONFIG.md "Walking and jumping on a level".

- **Rules** (`vidgen/world/moves.py`, no manim): a body is a box `BODY_WIDTH` 0.4 of its height
  wide on its feet. `SOLID` = ground and platform (they block from the side and from below); a
  *floor* (`is_floor`) is the top of a ground, platform or cloud tile or of a ladder. A body stands
  at a height in a column when a floor is there with room for its height above (no solid cell).
  Walking is a cheapest-path search (Dijkstra, deterministic ties) over (column, height) states:
  to the next column at most `STEP_TILES` 1 up or down (a flat way costs 1, a step 1.05), up a
  ladder at its feet to the ladder's top (or onto the tile over it: a hatch) and down one under
  it, at `CLIMB_SLOWNESS` 2 per tile. `walk_route` turns the states into a `Route` of `Leg`s
  (`walk`, `step`: half a tile across the column edge, eased; `climb`: at the column's middle);
  its `effort` (tiles walked, climbs doubled) sets the time. No way there: `VidgenError` naming
  where the way stops (a gap, a drop, a wall, no room under the tiles, or the column reached only
  at another height) and suggesting a jump.
- **Clouds are one-way** (decided here): a body stands on a cloud's top, walks through a cloud at
  its own height and jumps up through it from below; a falling arc that crosses a cloud's top
  lands there, so `plan_jump` refuses one that would cross a cloud before its landing. Why: it is
  the usual platform-game reading of a cloud, it makes "jump up onto the cloud" work from right
  under it, and solid platforms (`=`) remain for a ceiling. Walking through a low cloud shows the
  character inside the drawing; levels put clouds high, so this was left.
- **Jumps** (`plan_jump`): the landing is the goal's height (a spot, a tile) or, for a mark or x,
  the highest floor in that column a jump reaches. Take-off candidates are the states the body can
  walk to (no ladders) at the column's middle and 0.3 towards the landing (and where it stands);
  each is tried with the arc `y(u) = y0 + (y1 − y0) u + 4 b u (1 − u)` (x moving evenly) peaking
  `JUMP_CLEARANCE` 0.75 over the higher end, then 0.25 higher up to `MAX_JUMP_UP` +
  `JUMP_HEADROOM` over the take-off. An arc is clear when the body's box overlaps no solid cell at
  samples 0.05 tiles apart and crosses no cloud top on the way down. Limits: `MAX_JUMP_ACROSS` 5,
  `MAX_JUMP_UP` 3, `MAX_JUMP_DOWN` 8 tiles (a character is 2 tiles). The best candidate is the
  shortest jump (at least a tile across beats straight up), then the shortest run-up, then the
  lowest arc. No candidate: `VidgenError` with the reason from the nearest take-off. The flight
  takes `flight_seconds`: rising and falling under `JUMP_GRAVITY` 8 tiles/s² (about half a real
  gravity for a character two tiles tall, so arcs read slower than in a game), at most
  `JUMP_AIR_SPEED` 4 tiles/s across, at least 0.7 s. `walk_body` / `jump_body` apply a rule to a
  `World` (`World.moved`); a game could feed them a player's inputs.
- **Goals and the replay** (`cartoon/level_stage.py`, no manim): `level_goal` reads a place (a
  spot, a mark or x, a map tile `{column, row}` from the top left, from 1). `vidgen validate`
  replays the scene's `walk_to`, `run_to`, `jump` (with `to`), `enter` and `exit` in beat and `at`
  order (`Stage.action_sequence_problems` → `level_move_problems`) and reports each refusal at
  `beats[j].actions[k].to` with the beat's id; a character is not followed after a refusal, an
  exit or a keyframed / ridden move (until it enters again). `enter` / `exit` depend on the
  camera's view, so their ways are checked when the scene renders.
- **Renderer** (`cartoon/level_motion.py`): `RouteWalk` is a `Walk` whose `_place` hook (a small
  refactor of `Walk.interpolate_mobject`: where the feet are and the facing at a share of the
  distance) follows the route: facing each walking leg's way, the front on a ladder (front-view
  walk cycle), the last side once stopped; footsteps and motion effects read its route length.
  `ArcJump` is a `Jump` along the planned arc: it faces the landing, crouches
  `LEVEL_JUMP_CROUCH_SECONDS` 0.32, stretches, squashes on landing and leans forward and back
  (`settle_wobble`, `LANDING_WOBBLE_DEGREES` 7) over `LEVEL_JUMP_LAND_SECONDS` 0.55, all scaled by
  `cartoon_motion` (`jump_phases` / `jump_motion_seconds` take the crouch and landing seconds).
  A jump with a run-up is one `Succession(RouteWalk, ArcJump)`; foley and motion effects take its
  parts in turn (`_timed_parts`: the run-up as a `walk_to`). Both set the character's `ground_y`
  to the floor under it every frame (the shadow; far below over a gap), and the stage records the
  end floor in `grounds` (`keyframes` y 0, `level_moved`).
- **Stage** (`scenes/stage.py`): `on_level`, `level_pace` (`size / STAGE_SIZE`: default walking
  and running speeds, and a jump's run-up, scale with the level's smaller characters, so they walk
  as many of their heights per second as on a plain stage), `level_walk`, `level_enter`,
  `level_exit`, `level_jump`, `level_moved`, `level_homes`. The moving actions (`scenes/moving.py`)
  call these when `on_level`; a run time asked for while a batch is planned that the rules refuse
  then gives the default (the batch may start after another move of the character; `apply` plans
  again and raises naming the scene and beat). `feet_y_at` raises on a level; `walk_to` `depth`
  is refused there.
- **Timing**: moves keep the beat action timing (start at `at`, natural run time, sped up when
  the beat is short). `rushed_animation` has `max_speedup` (1.5): a `RouteWalk` or `ArcJump` play
  sped up more than that is reported (only level moves, so lint results on plain stages are as
  before). Automatic directing (`_follow_written`, `_jumps_somewhere`) and the prop-handling
  replay treat a jump to a spot or mark like a walk there (to a tile: the x is unknown).
- Measured: the 47 x 6 scratch level at 854x480 renders 31 s of video (a jump with a run-up, a
  walk over steps, a ladder climb, a jump up onto a cloud) in about 40 s; `plan_jump` takes a few
  milliseconds per jump.

### 86.8 Story props and reactions (Step 152)

Reference: docs/CONFIG.md "Story props on a level (keys, doors, coins, stars, blockers)".

- **World data** (`vidgen/world/items.py`, no manim): an `Item` (name, kind `key` / `door` /
  `coin` / `star` / `blocker`, where it is in tile units, its height; a door's `key` and `open`, a
  blocker's `aside`, the `holder` of a key or of a picked-up coin or star; `blocks`, `label`,
  `hint`). `World.items` holds them (`item`, `with_items`; `moved` moves a blocker's item with its
  body).
- **Symbols versus named placements** (decided here): what a map has many of and nobody names in
  a beat (coins, stars) is a map symbol, `$` and `*`, floating in the middle of an air cell and
  named `coin_1`, `star_1`... in map order (the top row first). What a beat names and acts on
  (`pick_up: gold_key`, `open: gate`, `step_aside: tobble`) is a prop or a character of the stage
  standing at a spot like any other: its part in the rules is data on the level, `locks: {door:
  key}` and `blockers: [name]`. This keeps Step 150's rule (letters are only spots, symbols only
  tiles or items), reuses the stage's props (`door` with its open / closed shapes, a new `key`
  prop held by its bow), its characters and every prop action, and puts no second placement
  syntax into the map. Every closed `door` prop on a level is in the way (a door is a way through;
  a free-standing door drawn shut that one walks through looked wrong); `locks` only adds the key.
- **Rules** (`vidgen/world/moves.py`, `vidgen/world/story_props.py`, pure functions): an item
  that `blocks` is an `Obstacle` shutting its column from its feet up to the first solid tile
  above it (`_OPEN_SKY_ROWS` with none), so a walk or a jump never passes it but a way over the
  tiles above it still does. `walk_route` / `plan_jump` take `obstacles`; when they refuse, the
  same move without them is planned and the first obstacle its way runs into (or the one right
  after where the walk stops) is named with what clears it: `the locked door 'gate' is in the way
  at map column 14; open it first with its key 'gold_key' (- open: gate, by: <who holds
  gold_key>)`. `route_pickups` / `jump_pickups` sample the way (every `_ARC_SAMPLE` 0.05 tiles)
  and give each coin or star whose middle the body's box comes within `PICKUP_RADIUS` 0.3 of, in
  order, with its share of the walk or of the flight (mid-jump). `walk_body` / `jump_body` apply
  both (the body is never in its own way). `open_door` (a locked door only by the key's holder,
  within `DOOR_REACH` 1.6 tiles across and `DOOR_REACH_UP` 0.5 up or down), `close_door`,
  `step_aside`, `hold_key`.
- **Validation** (`level_move_problems` with `LevelProps`): the replay follows the key through
  `pick_up`, `hold`, `give`, `put_down`, `throw`, `let_go` and `blow_away`, doors through `open`
  (with `by`) and `close`, blockers through `step_aside`, and the moves with the obstacles and the
  pickups; each refusal names the beat (`beats[j].actions[k].to`, `.by`, `.target`, `.react`). A
  blocker that stepped back off the path is no longer followed (it stands behind the path).
  `StageLevel` checks that `locks` names a door prop and a prop for its key, `blockers`
  characters, and that no prop or character takes a coin's or star's name.
- **Renderer**: `cartoon/level_items.py` `Collectible` (a coin: a disc, a ring and a shine; a star:
  a rounded five-point star), drawn from an updater counting its own seconds: it bobs (a coin
  turns) while it waits, and pops (grows 1.6×, rises 0.8 tiles, fades in `POP_SECONDS` 0.35)
  from `collect()`. The coins and stars go in the backdrop after the shadows, not graded by the
  light (they shine at night). `RouteWalk` and `ArcJump` (a `_Cues` mixin) take `pickups`
  (share, collectible) and call `collect()` on the frame the move's progress passes the share.
- **Reactions** (`react: {when, expression, effect}` on `walk_to`, `run_to` and `jump` on a
  level): a move's progress is its walk (or flight) share 0..1, then 1..2 over its settle;
  `Reaction(at, expression, effect)` starts when the progress passes `at` (the first pickup's
  share, `LANDED` 1, `SETTLED` 2), eases the face parts (`kind_parts("expression")`) to the
  expression over `REACTION_BLEND_SECONDS` 0.3 by changing the base state the walk cycle or the
  jump is drawn from (so the walk, the squash and the lip sync go on), and starts the effect
  symbol: an `EffectSymbol` the stage adds when the move is applied (`level_moved`), hidden with
  a very negative age until then, shrinking away by itself after `REACTION_EFFECT_SECONDS` 1.4.
  The expression is kept (as `emote`). A run-up's pickup puts the reaction on the run-up walk.
  The key `when` (not `on`): YAML 1.1 reads a bare `on:` key as `true`. Why inside the move, not
  a second action at a time: the runner plays an action that changes the same character after
  the one playing (`_changed` batches), so a separate `emote` cannot start mid-walk, and the
  pickup's time is only known once the move is planned.
- **Stage** (`scenes/stage.py`): `level_state` (the world as the rules see it now; `_level_now`
  reads each key's holder from its prop), `level_pickups`, `level_walk` / `level_jump` with
  `react`, obstacles and pickups (`walk.picked`), `level_enter` / `level_exit` with obstacles (no
  pickups, as in the replay), `level_moved` records the pickups and adds the effect symbol,
  `level_open` / `level_close` (called by `open` / `close` on a door), `level_step_aside` (a walk
  to `to`, else a `Walk` in depth to `ASIDE_DEPTH` 0.3 with its feet `ASIDE_RISE_TILES` 0.3
  higher, its draw order kept by the depth walks). `open` gained `by` (the opener turns to the
  door and reaches for its edge with the key's hand, `_reach_low`; `alters` keeps the opener out
  of other batches); `step_aside` is a new moving action.
- **Step 151 gaps closed**: `walk_to` / `run_to` take a tile `{column, row}` (`MapTile`, was
  `JumpTile`); `StageFrame.columns` lets `place_x` place a tile, so `vidgen direct` and the
  prop-handling replay know where a walk or a jump to a tile ends.
- Measured: the 50 x 5 scratch story at 854x480 (a key, two coin runs, a locked gate, a jump
  over a gap catching a star, a turtle stepping aside) renders 31.5 s of video in 27 s.

### 86.9 Sounds on a level (Step 153)

Reference: docs/CONFIG.md "Story props on a level", **Sounds**; "Foley and music stings".

- **Through foley, not a new system.** A level's sounds are stage foley (§69.19): the action
  runner calls `Stage.action_foley` with each action as it played (scene start, seconds after any
  speed-up); `_timed_parts` splits a jump with a run-up; `_played` turns each animation into a
  `PlayedAction`; `foley_cues` (no manim) gives the cues; `NarratedScene.sfx` records them
  (`timings.json` `sfx`, the SFX track, the final mix with its loudness normalisation and
  limiter). So `foley: false` (video or stage), `sfx: {gain}` and `assets/sfx/<name>.wav` control
  them as every other foley sound, and nothing new reaches the config.
- **Events and their times.** The rules' plan, not the frames, gives every time, so the cues are
  known when the action starts (before any frame of it is drawn):
  - take-off: the existing `boing` at the end of the crouch (`phases.before`), unchanged;
  - landing: `_played` gives an `ArcJump` `lands = 1 − phases.after` (its settle starts as it
    touches down); `landing_cues` plays a short, soft, higher `thud` and a `footstep` there, their
    intensity 0.35 + 0.1 per character height fallen (`lift`), at most 0.7. A jump in place (a
    plain `Jump`, also on a plain stage) keeps its boing only;
  - pickups: `RouteWalk.pickups` / `ArcJump.pickups` hold (share of the walk's distance or of the
    flight, collectible); `_played` passes `(share, kind)` as `PlayedAction.pickups`, and
    `pickup_cues` maps a walk's share through the inverse of `walk_progress` (`_walk_time_share`,
    as the footfalls) and the wind-up, a flight's linearly through the crouch: the same mapping
    `_Cues._cue` uses to pop the collectible, so the sound falls on the frame it pops (the render
    test checks within a frame). Coins play `coin`, stars `twinkle`; each further one of a kind in
    one move is a semitone higher (at most 5), the usual rising run of a coin trail;
  - door: `level_open` now returns whether a key unlocked the door (it had a `key` and was
    closed); `Open.apply` marks its `PropReshape` `unlocks`, and `door_cues` plays `unlock` at the
    action's start and the creak `UNLOCK_SECONDS` 0.3 later (never after the door swings at
    `RESHAPE_SHARE`). Other doors creak as before (§69.62);
  - a blocker stepping aside (`step_aside`, a `Walk` in depth or a `RouteWalk`): a soft low
    `swoosh` (−12 dB, 7 semitones down) and footsteps 3 semitones lower and 3 dB softer than a
    walk's. Not in `WALKING_ACTIONS`, so motion effects do not change.
- **New sounds** (`sfx.py`, numpy only, through the library's `_finish`: −27 LUFS loudest 400 ms,
  peaks at most −9 dBFS): `unlock` (a small metallic tick, then a rounder clack, low-passed at
  5 kHz), `coin` (two soft bell notes B5 → E6), `twinkle` (a soft bell arpeggio C6–C7 with a faint
  glitter, low-passed at 8 kHz). Bells with the soft partials of `success`, nothing above ~8 kHz
  of note: kid-friendly, not shrill. Missing before: no lock, no coin, no star sound. The landing
  and the blocker reuse `thud`, `footstep` and `swoosh`.
- **Loudness.** Gains follow the foley table: pickups −4 dB (like a boing), the unlock −6, the
  landing thud −8 with its step −5. A coin trail may overlap its sounds when run through (a coin a tile
  apart is about 0.7 s at walking pace, 0.45 s long); the render test writes the story's SFX track and checks its peak stays
  under −3 dBFS and its loudest 400 ms under −20 LUFS (narration is about −20; the final mix
  normalises and limits as before).
- Not done: a move's `react` effect symbol plays no sound (an `effect` action's does), nor does a
  `react` expression `surprised` during a move.
