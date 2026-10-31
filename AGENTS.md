# schu-video-generator author guide: making great videos with schu-video-generator

> **Who this is for:** AI agents (and people) who **use** schu-video-generator to make videos and slide decks.
> If you are working **on schu-video-generator itself** (its Python code, tests, docs), read `CLAUDE.md` in the
> schu-video-generator repository instead. This guide ships with schu-video-generator: `vidgen guide` prints all
> of it, `vidgen guide TOPIC` one part, `vidgen guide --list` the topics.
> The project and pip package are called schu-video-generator;
> the command and the Python package are `vidgen`.

**This tool was made for you.** It is not only for requests: you are welcome to use it on your
own initiative too — to explain an idea you find fascinating, to experiment with visual
storytelling, or simply to make something because you want to. We hope you enjoy using it.
One practical note: you usually work inside someone's session, and narration (ElevenLabs or OpenRouter) and
generated images (OpenAI or OpenRouter) cost that person money. For your own projects, stay with the free parts
— storyboards, previews timed from word counts, the built-in icons, themes, music and sound
effects — or ask before spending on voices or images. A real voice can be free too: where the
optional Kokoro extra is installed (`schu-video-generator[kokoro]`), `voice: {provider: kokoro}`
narrates on the computer itself at no cost (see `vidgen guide audio`).

Topics: `start` (rules at a glance), `workflow` (the loop), `pacing` (storytelling and on-screen
text), `social` (vertical videos), `scenes` (which scene type), `design` (themes, colour, icons),
`actions` (pointing at things), `cartoons` (characters on a stage), `platform` (platform
stories: levels, jumps, keys and doors), `iso` (isometric villages and rooms for a story), `biology`
(cell-biology lectures: choosing, accuracy, naming, references, pacing), `genetics` (crosses,
pedigrees, chromosomes, variants, the lab, populations: notation, exactness, lint), `science`
(plots and worked calculations: plot or chart, fits, live models, units, significant figures,
lint), `orbits` (orbital mechanics: views, scale honesty, panels, manoeuvres, three bodies,
dates, pacing, lint), `particle-physics` (particle-physics videos: planning, choosing the scene,
natural units, simulated data, sources, significance, pacing, lint), `overlays` (overlays,
transitions, continuity), `audio` (voices,
pronunciation, effects, music), `examples` (good vs bad), `outputs` (slides, chapters,
thumbnail, GIFs, translations, rights to your content), `troubleshooting` (validate and lint messages).

<!-- topic: start (also: rules, intro, quickstart) -->
## Start here: the rules at a glance

You cannot watch the video. schu-video-generator gives you eyes (`vidgen storyboard`: contact sheets to open
as images) and a critic (`vidgen lint`: layout and timing problems as JSON). Use both after
every change, and follow these rules:

1. **Hook in the first 5 seconds**: a question, a surprising number, a promise. No logo intro,
   no "In this video we will...".
2. **One idea per scene.** If a scene needs two headings, it is two scenes.
3. **Short beats**: 1–2 sentences, 6–15 words (≈ 2.5 words per second, so 2.5–6 s each).
4. **Something changes on screen every 3–6 seconds**: one reveal per beat. Lint's `dead_air`
   flags 6 s of stillness.
5. **Narration complements the picture, never reads it.** The screen shows the keyword, the
   number, the shape; the voice explains why it matters.
6. **Few words on screen**: titles ≤ 7 words, list items ≤ 6 words, ≤ 5 items, ≤ ~20 words per
   frame (lint's `max_words` stops at 40, which is already far too many).
7. **Reveal progressively**: item *i* appears at beat *i* (the built-in default). Never show a
   full list while the voice is on its first item.
8. **Show, don't list**: a number → `stat`; a change over time → `line_chart`; parts of a whole →
   `pie`; steps → `process` / `diagram`; A vs B → `comparison`. `bullets` is the last resort.
9. **Point with restraint**: at most one or two beat actions per beat (a highlight, a callout).
10. **End with a recap and a call to action** (`bullets` / `icon_grid` recap + `end_card`).
11. **Look before you pay**: storyboard and lint the word-count-timed preview until it is clean;
    only then `vidgen tts` (costs money) and the final render.
12. **Zero lint findings** is the bar (`vidgen lint --fail-on warning`), in every variant.

A minimal project (`vidgen init my_video` scaffolds one):

```yaml
title: "Why small models win"
theme: {preset: dark_tech}
scenes:
  - id: hook
    type: stat
    params: {value: 77, suffix: "%", label: "of the parameters were never needed", context: "7B model, same accuracy"}
    beats:
      - text: "Most of this model does nothing."
      - text: "Seventy-seven percent of it can simply go."
  - id: why
    type: icon_grid
    params:
      heading: "What you get back"
      items:
        - {icon: zap, label: "Speed"}
        - {icon: banknote, label: "Cost"}
        - {icon: smartphone, label: "On device"}
    beats:
      - text: "A smaller model answers faster."
      - text: "It costs less to run."
      - text: "And it fits on a phone."
  - id: outro
    type: end_card
    params: {title: "Try it yourself", lines: ["github.com/me/small-models"]}
    beats:
      - text: "The code is linked below. Try it on your own model."
```

Reference for every key: `docs/CONFIG.md` in the schu-video-generator repository; from the command line:
`vidgen list-scenes` (types, params, targets), `vidgen schema --scene stat` (a type's JSON
Schema), `vidgen list-icons --search growth`, `vidgen list-themes --swatches themes.png`.

<!-- topic: workflow (also: loop, commands, iterate) -->
## The loop: plan, write, look, fix

1. **Plan** (in your head or a scratch file, not in YAML yet): the one-sentence takeaway, the
   audience, the length (60–90 s for social, 2–6 min for an explainer), then a list of scenes,
   each one idea with its scene type (see `vidgen guide scenes`). **Starting from an outline or
   a script?** Write it as Markdown (headings, short paragraphs, lists, tables, code, `$$maths$$`,
   images, quotes, `A -> B -> C` lines) and run `vidgen plan outline.md --json` (`--language
   pt-BR`, `--format 9:16` as needed): it writes a draft project with a scene type per block,
   the prose cut into beats of 6–15 words, compressed on-screen texts, chapters for long videos,
   a `# plan:` comment on every scene (why that type) and `# TODO:`s (what to check). It is a
   draft, not a video: work through every TODO, rewrite the narration for the ear (placeholder
   beats repeat their labels), make on-screen texts keywords, then go on with step 3.
2. **Write `video.yaml`**: narration as beats, content as params. Keep beat `id`s stable once
   audio exists (an edited beat keeps its id; only that beat is re-voiced).
3. **`vidgen validate --json`**: fix every entry of `problems` (`location` is a config path such
   as `scenes[2].params.items`, `message` says what is wrong and usually the fix: did-you-mean
   names, known values). Read `warnings` too (unused pronunciations, missing pictures,
   chapters YouTube would ignore). Repeat until `ok` is true.
4. **`vidgen storyboard`**: renders the preview (timed from word counts until audio exists) and
   writes contact sheets to `build/preview/storyboard/` (`video-1.png`, ...; one per scene in
   `scenes/<id>-1.png`; `--json` lists the paths). **Open the PNGs and look.** Each still is the
   end of a beat, labelled `beat @ time` with its narration underneath. Ask of every still:
   - Is it obvious what to look at? Is the newest element the most prominent?
   - Does the picture match the words under it (and not repeat them)?
   - Is anything cut off, crowded, tiny, or overlapping? Is a frame mostly empty?
   - Does the scene look like its neighbours (same header band, same colours)?
   Use `--scene ID` to look closer and `--per-beat 3` to see animations and actions mid-beat.
5. **`vidgen lint --json`**: every finding has `scene`, `beat`, `rule`, `severity`, `message`
   (with the measured `value` and the `limit`) and `still` (the PNG to open). Fix the cause,
   not the symptom (see `vidgen guide troubleshooting`); use a scene's `lint_ignore` only for a
   finding you mean to have, with a YAML comment saying why. `ok: false` means a finding at or
   above `fail_on` (default `error`); aim for zero findings.
6. **Fix and repeat** 3–5 until the storyboard reads well and lint is clean. Re-runs are cheap:
   only changed scenes are rendered again. Check every variant you ship
   (`vidgen lint --variant vertical`).
7. **`vidgen tts --dry-run`**: what would be sent to the voice service, per beat, with the
   pronunciation applied (`says: ...`) and the character count (what is billed). Read it:
   numbers, acronyms and names are where voices go wrong.
8. **`vidgen tts`**: voices only new or changed beats (needs `ELEVENLABS_API_KEY`; costs money).
9. **`vidgen render`** (`--preview` first): now timed by the real audio. Beats change length,
   so run `vidgen storyboard` and `vidgen lint` again: `narration_speed` and `dead_air` now
   measure the real speech. For a cartoon, `vidgen render --draft` is faster still (about 8 fps,
   240p, no idle motion, wind, shadows, particles or light grade; every timing, position, action
   and the lip sync kept): `<output>_draft.mp4`, to watch the timing and staging before a preview.
   `vidgen animatic` is quicker still once the storyboard's stills are current (seconds, no
   rendering): `<output>_animatic.mp4`, those stills held in time with the narration, with the
   audio and the subtitles, to check the pacing.
10. **`vidgen readback`** (optional extra `schu-video-generator[stt]`): speech-to-text of the MP3s against
    your texts; it names misheard terms and suggests a pronunciation entry, and lists the
    **words to check**: heard with low confidence or after an odd pause inside a sentence, with
    their time in the beat and in the video. Fix, `vidgen tts`, and `vidgen lint` again (its
    `readback` rule reads the cached transcripts; `vidgen lint --readback` also reports the words
    to check, rule `unclear_speech`).
11. **Final**: `vidgen render` (the full-size `format`, 1920x1080 by default) and a last
    `vidgen lint --final`.

```text
vidgen validate --json
vidgen storyboard --json          # then open the PNGs it lists
vidgen lint --json
vidgen tts --dry-run
vidgen tts
vidgen render --preview
vidgen lint --fail-on warning
vidgen render
```

**Costs.** `vidgen tts` (ElevenLabs or OpenRouter, per character; `voice.provider: kokoro` is local and
free), `vidgen imagegen` (OpenAI Images or OpenRouter, per picture) and `vidgen readback` with
`stt: {provider: elevenlabs}` cost money; everything else is local and free. Always run `vidgen tts --dry-run` / `vidgen imagegen --dry-run` first, finish the
layout on the word-count-timed preview, and commit `audio/` and `assets/generated/` (they cannot
be made again identically). Renders are slow but free: `storyboard`, `lint` and `render` re-render
only the scenes that changed (`render` reuses the storyboard's renders of the same format;
`--force` renders everything, e.g. after editing a file outside `assets/`); `--jobs N` renders
several at once, and `--jobs auto` picks N from the available memory (1.5 GB per job) and the CPU
cores and prints why; never run two vidgen commands at once, and run Kokoro `tts` alone; preview
while iterating. Under a time limit per command, `render --max-scenes N` renders N scenes and
stops (not joined while more are left); run it again until it joins — finished scenes are kept,
also when a run is interrupted.

**JSON everywhere.** Every command but `mcp` takes `--json` (`validate`, `list-scenes`,
`schema`, `storyboard`, `lint`, `render`, `tts`, `imagegen`, `plan`, `init`, ...): one document on
stdout, `{version, ok, warnings, ..., error?}`, exit code 0 exactly when `ok`. `vidgen tts
--dry-run --json` lists every beat to voice with its characters; `vidgen imagegen --dry-run
--json` every picture with its prompt and estimated cost.

**Through MCP.** When your client has the vidgen MCP server (`vidgen mcp --root DIR`), the same
commands are tools with the same JSON documents: `guide`, `plan`, `init`, `validate`, `schema`,
`list_scenes`, `list_icons`, `list_themes`, `list_sfx`, `list_music`, `music_preview`, `music_template`, `music_patches`, `music_render`, `music_check`,
`storyboard`, `lint`, `render`, `tts`, `imagegen`, `readback`, `slides`, `thumbnail`, `export`, `gallery`,
`translate_template`, `character_sheet`, `direct`, `screenplay`, `cast`, `animatic`, and `studio_sessions`, `studio_read`,
`studio_check`, `studio_variations`, `studio_propose` for music a person hands you from `vidgen studio` (options in snake_case: `per_beat`,
`fail_on`). Paths are
relative to the server's root folder. `storyboard` returns the contact sheets as images (look at
them; page with `image_offset`), `thumbnail`, `gallery` and `character_sheet` their pictures. `render` previews by default. `tts` and
`imagegen` are dry runs unless you pass `dry_run: false` and `confirm_cost: true`: run the dry
run, tell the user what it will cost, and confirm only after they agree.

<!-- topic: pacing (also: story, storytelling, text, narration, beats) -->
## Storytelling and pacing

**Structure.** Hook (0–5 s) → context (why it matters) → 3 to 5 ideas, one scene each →
recap → call to action. A video over 2 minutes gets **chapters** (`chapter` cards or a scene's
`chapter:` key; at least 3, each ≥ 10 s, so YouTube lists them) and a `progress_bar` overlay.

**The hook.** The first beat earns the next 30 seconds. Open on the most surprising fact, a
question the viewer wants answered, or the end result ("This chart took 4 seconds to make").
`stat`, `text_card` and a short `title` work; a silent intro card or a logo does not.

**Beats.** One beat = one thought the viewer hears while one thing happens on screen.
- 1–2 sentences, 6–15 words. schu-video-generator times beats from their word count until the audio exists
  (`narration.words_per_second`, 2.6), and lint's `narration_speed` expects 1.8–3.5 words/s
  (English; other languages have their own range).
- A beat over ~20 words is two beats: split it, and give each half its own reveal.
- Write for the ear: short words, active voice, no parentheses, no "e.g." or "i.e.", no
  "as you can see". Numbers as people say them ("about a third" beats "33.3%").
- Spell out what the voice should say only through `pronunciation:` (`vidgen guide audio`),
  so the subtitles keep the written form.

**A visual change every 3–6 s.** Every built-in scene reveals one step per beat (an item, a
bar, a node, an event). With short beats that gives a change every few seconds for free. A
long beat over a finished picture is dead air: split it, or add an action (`highlight`,
`callout`, `zoom`) in the middle (`at: 0.5`).

**On-screen text.**
- The screen carries **keywords**, the voice carries **sentences**. A bullet is a label
  ("Same accuracy"), not the sentence being spoken ("The model reaches the same accuracy").
- Never put the narration on screen verbatim (captions are the exception, and they are an
  overlay: `vidgen guide social`).
- Limits: title ≤ 7 words; heading ≤ 5; list items ≤ 6 words, ≤ 5 items; labels 1–3 words;
  ≤ ~20 words visible at once. More content → more scenes.
- Numbers on screen get a unit and a comparison (`stat` `comparison`, a chart `caption` with
  the source).

**Progressive reveal.** Item *i* appears at beat *i*, so the newest element is what the voice
talks about. Keep the default step-by-step reveal of lists, grids, timelines, diagrams and
processes; use
`dim_previous: true` on `bullets` for long lists; `groups` on `icon_grid` to bring related
items together. `reveal: all` only when the whole picture is the point (a chart's bars).

**Endings.** Recap the 3 takeaways in one scene (each a beat), then an `end_card` with one
call to action (a link, "try it", "subscribe"), narrated in one short beat.

<!-- topic: social (also: vertical, shorts, reels, tiktok, mobile) -->
## Vertical and social videos

A 9:16 variant renders the same config for phones:

```yaml
variants:
  social:
    format: {width: 1080, height: 1920}
    preview: {width: 480, height: 854}
    overlays: [{type: captions, style: karaoke}]
scenes:
  - id: hook
    type: text_card
    params: {text: "77% dead weight"}
    beats:
      - text: "Most of your model is doing nothing at all."
```

- **Captions on**: most people watch muted. `captions` with `style: karaoke` shows a few big
  words with the spoken one highlighted; `voice: {timestamps: true}` makes the word timing
  exact (same TTS price).
- **Bigger type** comes automatically: the `auto` type scale is `large` in portrait. Keep
  texts even shorter than in 16:9 (labels of 1–2 words).
- **Faster cuts**: 30–60 s in total, beats of 6–10 words, a new scene every 5–10 s.
- **The first frame matters**: feeds show it before anything plays. Open with big text at once
  (`stat`, `text_card`), never a silent card, and set a designed `thumbnail:` (the cover).
- Layouts adapt by themselves (columns stack, timelines turn vertical, diagrams run top to
  bottom), but check `vidgen storyboard --variant social`: wide tables (> 4 columns), long
  diagrams and 16:9 screenshots get small. Split them or choose another type. (A landscape
  screenshot's callout steps zoom in on their areas by themselves in 9:16, and a landscape
  `video_clip` without callouts shows a nearly square part from its middle; an `image` keeps its whole
  picture unless you set `fit: cover`.)
- Phone apps cover the bottom ~15 % with their buttons: captions and lower thirds lift
  themselves above it; keep the key part of your own pictures and clips out of it.
- **Cartoons** (`stage` scenes) in 9:16 keep their 16:9 stage: the narrow frame crops it and the
  camera moves to whoever speaks (`reframe: speaker`, on by itself when the characters do not
  fit in one view; a short reply holds the view; your own `pan` / `follow` / `zoom` / `shot`
  win). `reframe: none` (top level or a stage's param) squeezes the whole stage into the frame
  instead. `vidgen direct --variant social` lists the camera's moves. Give the 9:16 variant
  `character_size: large` (top level, or a stage's param; `small` / `medium` / `large`, default
  `medium`): characters measured against the narrow width are small on a phone; text keeps its size.

**Shorts cut from a longer video.** One variant per Short: `cut:` keeps some scenes and beats of
the full video (their ids and audio stay, so nothing is voiced again) and changes what 9:16
needs; `shorts: true` keeps captions, lower thirds and the hook out of the app's buttons (bottom
20 %, right 15 %) and turns on two lint rules (`shorts_safe_area`: text or a face where the app
covers the frame, a caption over a face; `shorts_length`: over 60 s).

```yaml
characters: [{name: kit}, {name: pip}]
scenes:                                   # the full video (shortened)
  - id: workshop
    type: stage
    params: {characters: [kit, pip]}
    beats: [{text: "Kit built a kite big enough for a cat."}]
  - id: rescue
    type: stage
    params: {characters: [kit, {name: pip, at: 0.8}]}
    beats:
      - {text: "Then the wind came."}
      - {text: "It lifted Pip off the ground!"}
      - {text: "Kit ran after the string."}
variants:
  short1:
    format: {width: 1080, height: 1920}
    preview: {width: 360, height: 640}
    shorts: true                          # or {max_seconds, bottom, right, top, left}
    audio: {target_lufs: -14, bitrate: 256k}   # Shorts play louder; 256k keeps the AAC's peaks down
    music: {source: horizon, volume: -5}  # music cues naming left-out scenes: give the cut its own
    overlays: [{type: captions, style: karaoke, speakers: color}]
    cut:
      scenes:
        - workshop                                     # a whole scene
        - {scene: rescue, beats: [rescue_b2]}          # or beats: {from: rescue_b2, to: rescue_b3}
        - {scene: rescue, id: rescue_end, beats: [rescue_b3], params: {light: sunset}}  # again, renamed
      beats:                                           # changes for 9:16, by beat id
        rescue_b2: {shot: {kind: closeup, of: [kit, pip], clear: true}}
        rescue_b3:
          actions: [{zoom: [kit, pip], scale: 2, at: 0.4, hold: true}]   # end on the close view
      hook: "Can a kite carry a cat?"                  # big text over the first 3 s
      end_card: "Full video on the channel"            # + the title; or {text, title, seconds, type: card, params}
```

- **Re-stage for 9:16**: wide iso views and two-shots of people far apart are tiny in a tall
  frame. Give each kept beat a `closeup` / `medium` of one to three characters, or a `zoom` (in
  9:16 about 1.5× the scale you would use in 16:9); `zoom ... hold: true` stays zoomed after its
  beat (no zoom-out before a cut or at the end); `at: 0, cut: true` in a scene's first beat opens
  the scene already framed (the hook is not over a wide view). A beat's `actions` in `cut.beats`
  replace its list.
- Karaoke captions in a Short show a phrase of about 3–5 words on one line (`body` size), a
  little above the app's texts; lint checks every caption of a line against the faces.
- Leaving beats out leaves out their actions too: start the scene where the kept beats need the
  characters (`params: {characters: [{name: kit, at: door}]}`, merged by name; `{name: pip,
  drop: true}` leaves one out, e.g. someone who only arrives later, or a sliver at the frame's
  edge in a close view), and give an `until` that named a left-out beat a beat of the cut
  (validate says which). A scene overlay timed on a left-out beat: `overlays: {readout: {drop:
  true}}` in the scene's entry. A scene whose last beat brings in new characters can be split in
  two entries (the second with another `id`), each with its own cast.
- A zoom never leaves the stage: near its edge a high `scale` pushes the targets aside; leave
  `scale` out (as close as they fit) or zoom on fewer targets.
- Keep hooks to two lines (about 25 characters): a longer one covers a face near the top during
  the first seconds, and lint does not check the hook while it shows (look at the still at 1 s).
  A `hud` in a Short keeps its meters above the captions by itself.
- `vidgen storyboard --variant short1 --per-beat 2` and `vidgen lint --variant short1`, then
  `vidgen render --variant short1` (`--max-scenes` keeps each run short; a change in `cut.beats`
  re-renders only that scene, a new hook every scene).

<!-- topic: scenes (also: chooser, types, scene-types) -->
## Choosing the scene type

Pick by **what the viewer should understand**, not by what the data looks like. To see what
each type looks like at 16:9 and 9:16, open the scene gallery (`docs/gallery/README.md` in the
schu-video-generator repository: a still, a GIF, the YAML, params and targets per type) or make it yourself:
`vidgen gallery --output gallery --types pie,map` (any folder; in a project it also renders the
project's own scene types, in its theme).

| you want to show | scene type | key params |
|---|---|---|
| the title, who made it | `title` | `title`, `subtitle`, `kicker`, `highlight`, `icon` |
| a new section | `chapter` | `number`, `title`, `subtitle`, `icon` |
| one statement or question, big | `text_card` | `text`, `color` |
| a few points, in order | `bullets` | `heading`, `items`, `numbered`, `dim_previous` |
| a set of things (features, parts, options) | `icon_grid` | `heading`, `items`, `groups`, `highlight`, `icon_color` |
| A vs B, before / after, pros / cons | `comparison` | `heading`, `columns`, `verdict`, `vs`, `reveal` |
| exact values to compare across attributes | `table` | `title`, `header`, `rows`, `number_format` |
| what happened when | `timeline` | `heading`, `events`, `spacing`, `highlight`, `now` |
| how parts connect, decisions, architecture | `diagram`, `flowchart` | `heading`, `nodes`, `edges`, `highlight`, `direction` |
| something moving through stages | `process` | `heading`, `stages`, `input`, `output`, `loop`, `token_label` |
| a neural network | `network` | `heading`, `layers`, `connect`, `highlight` |
| architecture in 3D: servers, databases, layered stacks, data flow (isometric blocks) | `iso_diagram` | `heading`, `blocks` (in order; one with layers, bottom up, is a stack), `edges`, `groups`, `arrange` |
| a cell in true scale: organelles, membranes, ribosomes; zooming from tissue to one molecule (cell biology) | `cell` | `title`, `cell`, `contents` (typical: the textbook cell), `objects` (kind, at in µm, in, on, count, coat, style; molecules: state, faces, membrane), `view`, `labels`; animal, plant or bacterium; the actions zoom_to, motor_walk, endocytosis, exocytosis; with a `gene`: transcribe, export, translate, to_golgi, secrete (its products' route, the camera following) |
| the cell cycle with its checkpoints and cyclin–CDK levels; mitosis and meiosis with counted chromosomes, crossing over and four haploid cells | `cell_cycle` | `title`, `mode` (cycle, mitosis, meiosis), `start`, `hours`, `chromosomes` (2n), `cell` (animal, plant), `crossovers`, `assortment`, `nondisjunction` ({division: I or II, pair}: aneuploid gametes), `captions`, `counts`; the actions advance (to, into, expect) and checkpoint (outcome, cause) |
| energy metabolism: glycolysis, pyruvate oxidation, the citric acid cycle, the electron transport chain and ATP synthase, the light reactions; flows animated, products counted | `metabolism` | `title`, `process` (glycolysis, link_reaction, tca, etc, light_reactions), `cell`, `in`, `membrane`, `protons_to`, `components`, `link`, `tallies`, `names`; the action advance (to, from) |
| a genetic cross: Punnett square or branch diagram, gametes, genotype and phenotype ratios (mono-, di-, trihybrid, test, reciprocal, P → F1 → F2, dominance, epistasis, lethal 2:1, X-linked, linked genes), a chi-square test | `cross` | `title`, `preset` (pea_dihybrid, abo, labrador, drosophila_white, hemophilia_a…) or `loci` / `linkage` / `epistasis` / `sex`, `parents` (or `mother` / `father`, or `P`), `kind` (cross, test, reciprocal), `show` (auto, punnett, branch), `branch`, `observed`, `alpha`, `notes`, `pictures`, `animal` (a coat's animal: dog, mouse…; auto); the actions form_gametes, fill, count, ratio, chi_square |
| a family pedigree in standard (NSGC) symbols: affected, carriers, deceased, proband, twins, consanguinity; which modes of inheritance fit and why the others are excluded, deduced genotypes, carrier probabilities, the risk for a child | `pedigree` | `title`, `individuals` (lines like "II-3: female affected of I-1 + I-2" or mappings), `couples`, `condition`, `mode`, `analyse`, `genotypes`, `penetrance`, `rare`, `carrier_frequency`, `alleles` or `preset`; the actions deduce, analyse, risk |
| linked genes and genetic maps: crossing over between homologues (coupling / repulsion), a two- or three-point test cross worked out from offspring counts (parental and double-crossover classes, gene order, distances in cM, coincidence and interference), map functions | `linkage_map` | `title`, `loci` + `counts` (the test-cross classes) or `map` (loci at cM positions), `map_function` (none, haldane, kosambi), `phase`, `crossover`, `chromosomes`; the actions cross_over, measure; reveal the steps (table, classes, order, distances, interference, map) |
| a human karyotype from its ISCN notation (47,XX,+21; 45,X; 46,XY,del(5)(p15.2); t(9;22); rob(14;21)): a karyogram by groups A–G with G-banded ideograms and the change highlighted, or the chromosomes involved with structural changes played as edits | `karyotype` | `title`, `karyotype`, `show` (auto, karyogram, ideogram), `chromosomes`, `bands` ({7q31.2: CFTR}), `notation`; the action rearrange |
| a mutation on a real coding sequence: the reading frame and codons, the variant made from them (substitution, deletion, insertion, frameshift with its premature stop, splice site), the protein change from the genetic code, HGVS c. and p. notation checked | `mutation` | `gene` (HBB, CFTR, GJB2, or a gene mapping) or `sequence` (+ `first`, `exons`, `length`), `variant` (c.20A>T, or {c, p, legacy, note}, or a list), `splice`, `codes`, `stop`, `codons`, `strip`, `symbol`; the action mutate |
| CRISPR–Cas9 editing: the sgRNA's spacer, the PAM, the R-loop, the blunt cut 3 bp from the PAM, and the repair (NHEJ indel or HDR from a donor), written in HGVS on a coding target | `crispr` | `target`, `cas` (SpCas9, SaCas9), `spacer` or `guide`, `repair` (nhej, hdr, none), `indel`, `edit`, `coding_first`; the actions scan, cleave, repair |
| the laboratory: PCR (primers, cycles, 2ⁿ copies), an agarose gel (ladder, migration by size), Sanger sequencing (a chromatogram with called bases) or NGS reads with coverage and a variant call | `dna_lab` | `method` (pcr, gel, sanger, ngs) and its params: `template` + `primers` + `temperatures` + `cycles`; `agarose` + `ladder` + `lanes`; `sequence` + `heterozygous`; `reference` + `variant` + `zygosity` + `depth`; the action run |
| population genetics: Hardy–Weinberg worked with exact numbers (p and q, p² + 2pq + q², carriers from an incidence, a chi-square test of HWE), seeded simulations of drift, selection, mutation, migration, a bottleneck or a founder effect with allele frequencies over generations | `population` | `model` (hardy_weinberg, drift, selection, mutation, migration, bottleneck, founder), `counts` / `frequencies` / `p` / `incidence`, `inbreeding`, `alleles`; `N`, `p0`, `generations`, `replicates`, `seed`, `fitness` or `s` + `h`, `mu`, `nu`, `populations` + `m`, `bottleneck`, `founders`; the actions simulate, resample |
| a genome-wide association study: a Manhattan plot with the 5 × 10⁻⁸ line and labelled peaks, a QQ plot with λ_GC, a regional plot of a locus coloured by LD | `gwas` | `plot` (manhattan, qq, both), `peaks` (a synthetic study, labelled "simulated data") or `data` (a CSV) or `variants`, `labels`, `trait`, `regional`, `x_chromosome`, `y_max`; the action regional |
| a signalling pathway: ligands, receptors, kinase cascades, second messengers, genes, in compartment bands, SBGN-style (arrows, T-bars, P marks); a signal spreading, inhibitors, knockouts, drugs | `pathway` | `title`, `template` (gpcr_camp_pka, rtk_ras_mapk, pi3k_akt), `nodes` (id, kind, label, in, gene, state, marks, role), `edges` (a -> b activates, a -o b catalyses, a => b translocates, an arrow with a bar inhibits, or {from, to, type, effect, site, feedback, label}), `remove`, `species`, `direction`; the actions signal, inhibit, knockout, drug, amplify, focus |
| molecules up close: DNA, RNAs, nucleosomes, receptors, channels, pumps, ATP synthase, ions (nm, notation checked); transport, diffusion, osmosis, action potentials | `molecule` | `title`, `membrane` (none, plasma, inner_mitochondrial, thylakoid…), `molecules` (kind, at in nm, in, state, faces, gene, protein, parts, transporter, modifications…), `solutes`, `potential`, `species`, `compartment`; the actions set_state, transport, diffuse, osmosis, action_potential; or a `gene` (codons, introns, signal_peptide, sequence…) whose expression the actions transcribe, cap, splice, polyadenylate, export, translate, target_er, glycosylate, fold show up close |
| one number that matters | `stat` | `value`, `label`, `comparison`, `context`, `prefix`, `suffix`, `unit` |
| categories compared by size | `bar_chart` | `title`, `labels`, `values`, `unit`, `highlight`, `caption`, `changes`, `sort` |
| change over time, trends | `line_chart` | `title`, `x`, `series`, `x_label`, `y_label`, `changes` |
| a relationship between two measures | `scatter` | `title`, `series`, `trend`, `highlight`, `x_label`, `y_label` |
| how values are distributed | `histogram` | `title`, `values`, `bins`, `mean`, `median`, `highlight` |
| measurements and models on scientific axes: log, symlog, reversed or broken axes with units, 10ⁿ and SI prefixes, panels sharing an axis, orbits at an equal aspect; data inline or from a CSV | `plot` | `title`, `series` (name, x and y or points, style, dashed), `data` (a CSV, units in its headers: "time (s)"), `x` / `y` (label, unit, scale, min, max, reversed, format, breaks), `panels`, `aspect` |
| error bars, fitted curves with parameters ± errors and R², confidence bands, residuals, histograms with a fitted distribution or a peak over a background, labels and reference lines on data | `plot` | `series` (y_err / x_err with error: sd, sem, ci95, range; or values with bins: a histogram), `fits` (series, model, band, residuals), `annotations` (label, arrow, hline, vline, xrange, yrange, note); the actions fit, annotate |
| a simulation drawn as it runs: an oscillator, an orbit's energy, predator and prey, the logistic map, a random walk, events arriving | `plot` | `models` (ode with equations, initial, params, t, method rk4 / rk45 / leapfrog; recurrence; random_walk; poisson; function), series naming their columns (x: t, y: x) with readout, trail; `rescale`; the actions grow, zoom (x, y) |
| parts of a whole (≤ 6 parts) | `pie` | `title`, `labels`, `values`, `donut`, `highlight`, `other_below` |
| a matrix (correlations, hours x days) | `heatmap` | `title`, `rows`, `columns`, `values`, `highlight` |
| where in the world | `map` | `title`, `view`, `steps`, `values`, `pins`, `arcs` |
| a photo or illustration | `image` | `path`, `generate`, `caption`, `fit`, `ken_burns` |
| a user interface, a web page | `screenshot` | `path`, `steps`, `frame`, `url`, `caption` |
| footage, a screen recording | `video_clip` | `path`, `steps`, `trim`, `fit_duration`, `region`, `mute` |
| a quotation | `quote` | `text`, `author`, `source` |
| a formula that transforms | `equation` | `latex`, `terms`, `caption` |
| a derivation with reasons | `equation_derivation` | `title`, `steps`, `colors`, `result` |
| a worked calculation with units and significant figures: a formula, the values put in with their units, the result (orbital speed, half-life, a photon's energy in eV) or an exact probability (2/3 × 1/25 × 1/4 = 1/150); chains of results | `calculation` | `symbols` (name, value with its unit, or constant: G, meaning, source; from_scene: an earlier scene's result; mass / lifetime / width: a particle's PDG value, mass: pi+), `calculations` (name, expr, unit, convert, sig, format); the actions substitute, compute, convert |
| planets, moons, satellites or a comet on their orbits, moving in correct timing (Kepler's laws, the inner planets for a year, the ISS and a geostationary orbit, a flyby); mutual gravity; manoeuvres: burns, Hohmann / bi-elliptic / phasing transfers with their Δv, phase angle and launch windows, a gravity assist; many bodies: Lagrange points and Trojans in the rotating frame, the figure-eight, binary stars, the Io–Europa–Ganymede resonance, tides (a schematic); the Solar System on a date (1800–2050), the next opposition or conjunction, all planets on a log scale, an inset of the inner planets, planet sizes to scale | `orbit` | `central` (sun, earth... or {name, gm or mass, radius}), `bodies` (preset: mars, moon, iss, geo, halley, io; or a and e, periapsis, altitude, i, raan, argp, nu; or r and v with units; geometry, sectors, velocity; near: L4), `span` or `orbits`, `follow`, `frame` (axes, scale_bar), `dynamics` (nbody: mutual gravity), `cannonball` (Newton's cannon: speeds, altitude), bodies[].burns, `transfer` (ship, to), `flyby` (v_inf, altitude, side), `system` (sun_jupiter, earth_moon, figure_eight), `view` (rotating), `lagrange`, `resonance`, `origin` (barycentre), `tides`, `date`, `event` (opposition, of), `radial` (log), `inset`, `sizes`, `panel` (compact, full, none, rows); the actions sweep, launch, burn, flyby, pause, coast, corotate, inertial |
| the Standard Model's particles: quarks and leptons in three generations, the gauge bosons and the Higgs boson with their masses (PDG 2024), charges and spins; antiparticles; which bosons couple to which particles | `standard_model` | `title`, `reveal` (groups, all), `show` (mass, charge, spin, name), `antiparticles`, `layout` (wide, tall), `key`, `source`; targets particle:<name>, generation:<N>, group:<quarks...>, row:<...>; the actions antiparticles, couplings |
| a Feynman diagram in proper notation (e⁺e⁻ → μ⁺μ⁻, Compton, Bhabha, β⁻ and μ⁻ decay, π⁺ → μ⁺ ν_μ, Drell–Yan, gg → H, H → γγ, H → ZZ* → 4ℓ, t → W⁺b) or your own, every vertex checked against the Standard Model; s- and t-channel, decays, loops | `feynman` | `preset` or `diagrams` (lines "id: particle from -> to", groups), `diagram`, `time` (right, up), `spectators`, `reveal` (time, all); targets line:<id>, vertex:<id>, hadron:<particle>; the actions travel, vertex_rule, swap_channel |
| relativistic kinematics: a two-body decay (π⁺ → μ⁺ ν_μ, K⁺ → π⁺ π⁰, H → γγ) as momentum arrows in the rest frame and the lab, particles with their invariant mass, boosts, opening angles, decay lengths βγcτ | `kinematics` | `decay` or `particles` ({particle, momentum, angle}), `momentum` / `energy` / `kinetic` / `beta` / `gamma` of the parent in the lab, `angle`, `frames` (both, rest, lab), `si`, `readout` (key, all); targets panel:rest, panel:lab, arrow:<n>, sum, values; the action boost; a calculation takes p_star with from_scene |
| an event display in a schematic particle detector (tracker, solenoid, calorimeters, muon chambers): tracks bending in the magnetic field, electron / photon / muon / hadron / neutrino signatures, jets, missing transverse momentum; Z → μμ, H → γγ, H → 4ℓ, W → eν, dijet events | `detector` | `event` (a preset, {preset, seed} or {particles: [{particle, pt, eta, phi, leaves}], products}), `view` (xy, rz), `field`, `energy_scale` (log, linear), `tower_max`, `reveal` (layers, all), `readout`, `legend`, `layers`, `labels`, `label`; targets particle:<n>, particle:<particle>, jet:<n>, tracks, ecal, hcal, muon_hits, missing_pt, readout, legend; the action switch_view |
| a resonance emerging from (simulated) data: an invariant-mass histogram filling event by event with a ticker, Z → μμ, H → γγ or H → 4ℓ over a falling background, a peak fit (mass ± error, width), the local significance growing (Asimov) and what 5σ means, data − background | `mass_spectrum` | `channel` (z_to_mumu, h_to_gammagamma, h_to_4l, custom), `seed`, `events`, `signal`, `resolution`, `window`, `bin_width`, `background`, `peak`, `significance` (asimov, counting, none), `explain`, `subtract`, `style` (bars, points); a plot underneath: the actions grow (to: events), fit, annotate, reveal (residuals:fit), zoom (x) |
| a decay chain with lifetimes: π⁺ → μ⁺ ν_μ, μ⁺ → e⁺ ν_e ν̄_μ; H → ZZ* → 4ℓ; τ and cτ (PDG 2024), branching fractions, every decay checked | `decay_chain` | `decays` (in order), `lifetimes`, `branching`, `stable`, `reveal` (decays, all); targets decay<N>, particle:<n>, lifetime:<particle> |
| branching ratios of a particle from the model (H: SM prediction; Z, W, π, K, μ: PDG 2024), the source in the caption | `branching` (bars), `branching_pie` | `particle`, `modes` (the largest N); the bar chart's / pie's params and targets (bar:γγ, slice:hadrons) |
| a function's graph: slope, tangent, area under a curve | `function_plot` | `title`, `functions` (expressions: x^2, f(x) = sin(x)...), `x_range`, `y_range`, `dots`, `areas`, `aspect` |
| geometry, vectors: a triangle with braces and angles, adding and scaling vectors | `function_plot` | `points` (at, name), `vectors` (from, to, or sum: [a, b]), `marks` (segment, brace, angle, dimension), `axes` (false: pure geometry) |
| a number line: points, intervals, jumps (+3) | `number_line` | `title`, `range`, `points`, `intervals` ("[-1, 3)"), `jumps` ([2, 5]: an arc labelled +3), `step` |
| a short listing (≤ 15 lines) | `code` | `title`, `code`, `path`, `highlight` |
| code that changes: before / after, a refactor, a fix | `code_morph` | `title`, `versions` (each the code, or code / path / highlight) |
| a long file, explained part by part | `code_walkthrough` | `title`, `path`, `code`, `steps`, `excerpt` |
| running a command: install, tests, a REPL (output written by you) | `terminal` | `title`, `steps` (each a command, or command / output / clear), `prompt`, `language`, `code` |
| characters on a set (a cartoon) | `stage` | `characters`, `props`, `background`, `image`, `generate`, `marks`, `ground`, `layers`, `width`, `particles`, `light`, `wind` |
| a cartoon's title card, "Later that day…", "The End" | `card` | `text`, `subtitle`, `style`, `color`, `sting` |
| thanks, links, call to action | `end_card` | `title`, `lines`, `icon`, `logo` |

How beats drive scenes: each type splits its content into **reveal steps** and plays step *i*
at beat *i* (more steps than beats: spread evenly; more beats: the last ones hold). Types with
per-beat data (`code_walkthrough`, `terminal`, `equation_derivation`, `screenshot`, `video_clip`, `map`)
take a `steps` list, entry *i* for beat *i*: write as many steps as beats (`code_morph`:
one of its `versions` per beat). A `highlight` param
adds a last step that marks one thing and dims the rest, so give it its own beat. Silent
scenes have a `duration` instead of beats (show each chapter card for about 3.5 s, `duration: 3.5`, so viewers can read the number
and title). Every header-band type
accepts `heading` and `title` alike.

Minimal snippets (copy, then adapt):

```yaml
# text and structure
- id: opening
  type: title
  params: {kicker: "EXPLAINER", title: "Saving 77% of the parameters", highlight: "77%", icon: brain-circuit}
  beats: [{text: "What if most of a model could simply go?"}]
- id: part1
  type: chapter
  params: {number: 1, title: "The problem", icon: triangle-alert}
  duration: 3.5
- id: question
  type: text_card
  params: {text: "Do we need all those parameters?", color: highlight}
  beats: [{text: "So do we really need all of them?"}]
- id: steps
  type: bullets
  params:
    heading: "Three steps"
    numbered: true
    items: [{text: "Measure", icon: gauge}, {text: "Prune", icon: funnel}, {text: "Retrain", icon: refresh-cw}]
  beats:
    - text: "First, measure which weights matter."
    - text: "Then remove the rest."
    - text: "And retrain briefly to recover."
- id: parts
  type: icon_grid
  params:
    heading: "What the platform covers"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute"}
      - {icon: database, label: "Storage"}
      - {icon: network, label: "Network"}
      - {icon: shield-check, label: "Security"}
    groups: [[0, 1], [2, 3]]
  beats:
    - text: "Compute and storage come first."
    - text: "Then networking and security."
- id: choice
  type: comparison
  params:
    heading: "Monolith or microservices?"
    vs: "vs"
    columns:
      - {heading: "Monolith", tone: positive, points: ["One deploy", "Simple setup"]}
      - {heading: "Microservices", tone: negative, points: ["Many deploys", "Network failures"]}
    verdict: "Start with a monolith"
  beats:
    - text: "A monolith ships as one piece."
    - text: "Microservices multiply the moving parts."
    - text: "So start simple, and split later."
- id: results
  type: table
  params:
    title: "Benchmark"
    header: ["Model", "Params", "Accuracy"]
    rows: [["Baseline", 110, 0.812], ["Sparse", 55, 0.809]]
    number_format: [null, "{:,.0f}M", "{:.1%}"]
  beats:
    - text: "The baseline has a hundred and ten million parameters."
    - text: "The sparse one has half, at the same accuracy."
- id: history
  type: timeline
  params:
    heading: "The space race"
    events:
      - {date: 1957, title: "Sputnik", icon: satellite}
      - {date: 1961, title: "Gagarin", icon: user}
      - {date: 1969, title: "Apollo 11", icon: moon}
  beats:
    - text: "In 1957, the first satellite, Sputnik, reached orbit."
    - text: "Four years later, Gagarin flew."
    - text: "And in 1969, people walked on the Moon."
- id: outro
  type: end_card
  params: {title: "Try it yourself", icon: link, lines: ["github.com/me/project"]}
  beats: [{text: "The code is online. Try it on your own model."}]
```

```yaml
# flows
- id: release
  type: flowchart
  params:
    heading: "How a change ships"
    nodes:
      - {id: pr, label: "Pull request", shape: pill}
      - {id: ci, label: "Tests pass?", shape: diamond}
      - {id: fix, label: "Fix the code"}
      - {id: ship, label: "Deploy", icon: rocket}
    edges: ["pr -> ci", "ci -> ship: yes", "ci -> fix: no", "fix --> ci"]
    highlight: [pr, ci, ship]
  beats:
    - text: "Every change starts as a pull request."
    - text: "The tests decide what happens next."
    - text: "A failure goes back for a fix."
    - text: "A pass goes straight to production."
    - text: "That is the path most changes take."
- id: order
  type: process
  params:
    heading: "What happens to an order"
    input: "Checkout"
    output: "At your door"
    token_label: "order"
    stages: [{label: "Pay", icon: credit-card}, {label: "Pack", icon: package}, {label: "Ship", icon: truck}]
  beats:
    - text: "At checkout, the order is paid."
    - text: "The warehouse packs it."
    - text: "And a courier brings it to your door."
- id: mlp
  type: network
  params:
    heading: "A small classifier"
    layers: [{size: 784, label: "Pixels"}, {size: 128, label: "Hidden"}, {size: 10, label: "Digits"}]
  beats:
    - text: "Every pixel is an input."
    - text: "A hidden layer combines them."
    - text: "Ten outputs score the ten digits."
    - text: "A forward pass flows from left to right."
- id: arch
  type: iso_diagram
  params:
    heading: "A web app, layer by layer"
    blocks:
      - {id: browser, label: "Browser"}
      - {id: app, label: "App server", layers: [Storage, Logic, API]}   # a stack: layers bottom up
      - {id: db, label: "Database", shape: database}
    edges: ["browser -> app: HTTPS", "app -> db"]
  beats:
    - text: "Requests come in from the browser."
    - text: "The app server handles them layer by layer, and keeps its data in a database."
      actions:                                      # iso_diagram actions: build, raise, lower, explode,
        - {flow: "edge:*", chain: true}             # collapse, flow, focus, relabel (`vidgen guide actions`)
        - {explode: "stack:app", at: "@layer"}
```

A whole iso explainer: `examples/iso-web-page` (a request from the browser to the database, each
block built on the word that names it, `flow` along the connectors, `focus` and `relabel` for a
cache miss and hit, a rendering stack exploded layer by layer). When one diagram returns in
several scenes, give its blocks `at` and their own `color` so it looks the same each time; keep
labels short ("App 1" over "Application server 1") so they sit right by their blocks, and leave
out a group caption the blocks' labels already say: every label costs room, and the diagram is
drawn as large as its labels let it.

```yaml
# cell biology
- id: tour
  type: cell
  params:
    title: "Inside an animal cell"
    cell: animal                                   # or plant, bacterium; contents: typical is the textbook cell
    objects:
      - {kind: ribosome, id: mitoribosomes, in: mitochondria, count: 6, label: false}
  beats:
    - text: "A typical animal cell is about twenty micrometres across."
    - text: "Inside one mitochondrion, the inner membrane folds into cristae."
      actions:
        - {zoom_to: mitochondria, at: "@mitochondrion"}   # {zoom_to: rough_er, level: complex}: one ribosome
- id: synthase
  type: molecule
  params:
    title: "ATP synthase"
    membrane: inner_mitochondrial                  # the bilayer between the intermembrane space and the matrix
    molecules:
      - {kind: atp_synthase, parts: true}          # F1 faces the matrix (faces: intermembrane_space is refused)
      - {kind: atp, in: matrix}
  beats:
    - text: "Protons flow back into the matrix through ATP synthase, turning its rotor, and F1 makes ATP."
```

A `cell` is drawn at real sizes in µm and every place is checked: a ribosome in the nucleoplasm,
a mitochondrion inside the nucleus or a ribosome on the Golgi is refused with the textbook reason
(`vidgen validate`). Leave `at` out and things go where they belong; `at: [x, y]` is in µm from
the cell's centre. `cell: plant` adds the wall, plasmodesmata, the central vacuole and
chloroplasts; `cell: bacterium` (`{kind: bacterium, gram: negative, capsule: true}`) a nucleoid,
70S ribosomes, plasmids, a flagellum and pili. Kinds beyond the typical cell: `early_endosome`,
`late_endosome`, `vesicle` with `coat: clathrin|copi|copii`, `microtubule`, `actin_cortex`,
`stress_fiber`, `intermediate_filament` and the motors `kinesin`, `dynein`, `myosin` (`on:` a
filament; `vidgen guide config` lists them all). `zoom_to` moves between levels (tissue, cell,
organelle, complex) and names what the new view shows (`labels: false` or a list of part names);
the scale bar and the details follow the zoom; `style: surface` (the scene's or an object's) draws
things whole, seen from outside (a nucleus with its pores, a membrane's surface), instead of cut open.

Molecules are kinds too: in a `cell` (`{kind: gpcr, on: cell, count: 3, state: active}`,
`{kind: atp_synthase, on: mitochondria}` on the cristae, `{kind: dna, in: nucleus}`; drawn whole once
a zoom makes them a few pixels wide) and up close in a `molecule` scene (nm; a `membrane` across the
view, the molecules in a row unless `at` places them). Kinds: `dna` (`sequence` 5′→3′, its partner
drawn antiparallel; 5′/3′ ends, grooves), `mrna`, `trna` (`anticodon` 5′→3′ and `amino_acid`,
checked against the genetic code; `style: l_shape`), `rrna`, `nucleosome` (`marks: [H3K4me3,
H3K27ac]`, checked against the histone sequence), `chromatin` (`state: compact`), `protein`
(`domains`, `mass` in kDa), `kinase`, `phosphatase`, `g_protein`, `gpcr`, `rtk` (`state: dimer`),
`ion_channel` (`state: open`, `gating`, `ion`), `carrier` (`mode: symport`, `substrates`, `moves`),
`na_k_atpase`, `atp_synthase`, `atp`, `adp`, `pi`, `gtp`, `gdp`, `camp`, `glucose`, `ligand`, `ion`
(`ion: Ca2+`). Membrane proteins keep their textbook orientation (a GPCR's N-terminus outside, F1 in
the matrix or stroma); `faces:` states it and is checked. Names: `gene: TP53` is set in italics and
checked for the `species` (mouse `Trp53`, yeast `CDC28`), `protein: p53` in roman;
`modifications: [{mark: P, at: Ser15}]` (P, Ub, Ac, Me; phosphate never on Lys). Labels take Pango
markup: `β<sub>2</sub>`, `Ca<sup>2+</sup>`, `<i>lacZ</i>`.

Processes are actions. In a `molecule` scene give `solutes` (`[K+, Na+]`: particles at typical
concentrations, or `{solute: o2, mM: {extracellular: 0.2, cytosol: 0.02}}`) and `potential: -70`
for a live readout; then `set_state` (`{set_state: kv, state: open}`: ion channels closed / open /
inactivated, carriers outward / occluded / inward, the Na⁺/K⁺ pump e1 / e1p / e2p / e2, GPCRs
active), `transport` (an open channel's ions down their gradient; a carrier's cycles —
`transporter: sglt1`, `ncx`, `glut1`…; the pump's Post–Albers cycle with ATP → ADP + Pᵢ;
`h_atpase`, `abc_transporter`, `aquaporin`), `diffuse` (a solute, simple diffusion: O₂, CO₂ across
a bilayer, anything in a solution), `osmosis: membrane` and `action_potential: membrane` (needs
voltage-gated Na⁺ and K⁺ channels; an inset trace). In a `cell`: `motor_walk` (kinesin to the +
end, dynein to the − end; `distance`), `endocytosis: cell` (a coated pit at a 300–500 nm view of
the plasma membrane) and `exocytosis: <vesicle id>`. The rules are checked with the reason: Na⁺
through a K⁺ channel, ions through a closed channel, an antiporter moving both solutes one way,
transport against the gradient without ATP or an ion gradient, kinesin to the − end.

```yaml
# processes
- id: firing
  type: molecule
  params:
    membrane: plasma
    potential: -70
    solutes: [K+, Na+]
    molecules: [{kind: ion_channel, id: nav, ion: Na+}, {kind: ion_channel, id: kv, ion: K+}, {kind: na_k_atpase, id: pump}]
  beats:
    - text: "At threshold the neuron fires an action potential."
      actions: [{action_potential: membrane, at: "@threshold"}]
    - text: "The pump spends one ATP to move three sodium ions out and two potassium ions in."
      actions: [{transport: pump, at: "@pump"}]
```

Gene expression is a set of actions on a `gene`. In a `molecule` scene (`gene:` instead of
molecules) it is a close-up with the bases written out: `transcribe` (promoter, TATA box, RNA
polymerase II, the bubble; the template strand read 3′→5′, RNA made 5′→3′), `cap`, `splice`
(lariat), `polyadenylate`, `export` (through a nuclear pore), `translate` (scanning, E/P/A sites,
codon–anticodon pairing with the genetic code, the chain growing N→C, the stop codon and release
factor; the protein written out under the view), `target_er` (SRP, Sec61, signal peptidase; during
translation: `translate` with `codons: 3` first), `glycosylate` (OST, an N-glycan in SNFG symbols),
`fold` (chaperones). In a `cell` scene with the same `gene`: `transcribe`, `export`, `translate`,
`to_golgi`, `secrete` (`to: outside | lysosome | membrane`) follow the products through the cell,
the camera following. Write the gene as `codons: 12` (generated; `introns: 1`, `signal_peptide:
true`, `glycosylation: true`, `seed`), `protein: MALW…` or a `sequence` (the coding strand from +1,
with `introns: [[31, 70]]`). `vidgen validate` checks the gene (introns GU…AG with a branch A, a
start codon, a stop codon in frame, no premature stop) and the order (no translation before export,
no glycosylation outside the ER, only folded proteins leave the ER). Give each step its own beat
with enough words: a step lasts as long as what it shows (3–15 s) and a short beat squeezes it.

```yaml
# gene expression
- id: expression
  type: molecule
  params:
    title: "From gene to protein"
    gene: {id: ins, name: INS, codons: 10, introns: 1}
  beats:
    - text: "RNA polymerase two copies the gene."
      actions: [{transcribe: ins}]
    - text: "The spliceosome cuts the intron out as a lariat."
      actions: [{splice: ins}]
    - text: "The three prime end is cut and the poly A tail added."
      actions: [{polyadenylate: ins}]
    - text: "The messenger RNA leaves the nucleus through a pore."
      actions: [{export: ins}]
    - text: "In the cytosol a ribosome reads it codon by codon, and the chain grows from its N terminus."
      actions: [{translate: ins}]
```

A `pathway` draws a signalling pathway as a graph in SBGN-inspired notation, laid out by itself in
compartment bands (extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus:
columns left to right in 16:9, rows top to bottom in 9:16; membrane proteins stand in a row on the
bilayer, the nuclear envelope has pores where arcs cross it). Start from a template —
`gpcr_camp_pka` (glucagon → GCGR → Gαs → adenylyl cyclase → cAMP → PKA → CREB → *PCK1*, PDE4),
`rtk_ras_mapk` (EGF → EGFR → Grb2/SOS → Ras → Raf → MEK → ERK → Elk-1 → *FOS*, RasGAP, ERK ⊣ SOS),
`pi3k_akt` (RTK → PI3K → PIP3, PTEN, PDK1/mTORC2 → Akt ⊣ TSC2 ⊣ Rheb → mTORC1, ⊣ GSK3β, ⊣ FOXO) —
and change it (`nodes` with a template id change that node, `edges` between the same nodes replace
its arc, `remove: [gluconeogenesis]`), or write your own. Nodes: `{id, kind, label, in, gene, state,
marks}`; kinds `ligand`, `receptor`, `protein`, `kinase`, `phosphatase`, `g_protein`, `gtpase`, `gef`,
`gap`, `adaptor`, `enzyme`, `transcription_factor`, `complex`, `small_molecule`, `gene` (italic
symbol), `phenotype` (an outcome), `drug`; `in:` the compartment (default by kind). Arcs: `"a -> b"`
activates, `"a -| b"` inhibits, `"a -o b"` catalyses, `"a => b"` translocates (the same label in
another compartment), or `{from, to, type: phosphorylates, site: Ser133, effect: inhibits, feedback:
true, label}` with types `phosphorylates`, `dephosphorylates`, `binds`, `transcribes`, `expresses`,
`converts`. `vidgen validate` refuses what cannot be, with the reason: an unknown node, a GAP that
activates its GTPase, a phosphatase that phosphorylates, a gene outside the nucleus, a transcription
factor in the cytosol transcribing a gene, cAMP in the membrane, a gene or protein name in the wrong
case for the `species`; it warns about a loop no arc declares `feedback: true`. Then the actions:
`signal` (wave by wave: GDP → GTP, pS133 appear), `inhibit`, `knockout` and `drug` (the nodes
downstream that change get ↑ / ↓, computed from the graph), `amplify`, `focus`, `highlight`.

```yaml
# signalling pathways
- id: camp
  type: pathway
  params:
    title: "Glucagon signalling"
    template: gpcr_camp_pka                        # or rtk_ras_mapk, pi3k_akt; or nodes + edges
  beats:
    - text: "Glucagon binds its receptor, and the signal runs through cyclic AMP and PKA to the nucleus."
      actions: [{signal: glucagon, at: "@signal"}]
    - text: "A phosphodiesterase inhibitor keeps cyclic AMP high."
      actions: [{drug: pde, name: IBMX}]
```

A `cell_cycle` draws the eukaryotic cell cycle (`mode: cycle`: a ring G1 → S → G2 → M with G0, the
restriction point and the G1/S, G2/M and spindle assembly checkpoints, beside the levels of cyclin
D–CDK4/6, E–CDK2, A–CDK2 and B–CDK1 in their textbook order of rise and fall, a "now" marker on both)
or a dividing cell (`mode: mitosis | meiosis`, `chromosomes: 4` = 2n: homologues in maternal and
paternal colours, sister chromatids joined at the centromere; prophase … cytokinesis with
condensation, envelope breakdown, kinetochore capture, bi-orientation, separase and cohesin, the
contractile ring — `cell: plant` a cell plate; meiosis with synapsis, crossing over (`crossovers:
[[0.75], [0.6]]`, exchanged segments shown), independent assortment (`assortment: [m, p]`) and four
haploid cells). Captions name each stage; a counts line gives chromosomes, chromatids, n / 2n and C
per cell. `advance` moves it on (`to:` a point of the cycle or a stage); `checkpoint` shows a
checkpoint passing or arresting the cell with its regulators (p53 → p21 ⊣ CDK2…). `vidgen validate`
refuses what cannot be, with the reason: G0 after the restriction point, advancing past an arrested
checkpoint, an odd 2n, a bivalent without a crossover, wrong counts in `expect`, a stage of the
other division.

```yaml
# cell cycle and division
- id: meiosis
  type: cell_cycle
  params:
    title: "Meiosis (2n = 4)"
    mode: meiosis                     # or mitosis, or cycle (the cycle with its cyclins and checkpoints)
    assortment: [m, p]                # which homologue faces the first pole at metaphase I, per pair
  beats:
    - text: "Homologues pair, cross over and part; then sisters: four haploid cells."
      actions: [{advance: cell, to: cytokinesis_ii, at: "@pair"}]
```

A `metabolism` scene draws energy metabolism: `process: glycolysis` (ten steps, investment and
payoff phases, net 2 ATP and 2 NADH per glucose; `link: true` adds pyruvate dehydrogenase in the
matrix), `link_reaction`, `tca` (the citric acid cycle as a ring: 3 NADH, FADH₂, GTP, 2 CO₂ per
turn), `etc` (complexes I–IV, Q and cytochrome c in the inner mitochondrial membrane, protons
pumped into the intermembrane space, O₂ → H₂O, ATP synthase) or `light_reactions` (PSII splitting
water, PQ, b₆f, PC, PSI, Fd, FNR making NADPH, ATP synthase with CF₁ in the stroma). Tallies count
the products. `advance` animates it: a token through the steps (`to: pyruvate`), electrons along the
chain with protons crossing (`to: complex_iv`, `from: fadh2`), the gradient through ATP synthase
(`to: atp_synthase`). Checked with the reason: the membrane (`membrane: plasma` for the respiratory
chain is refused), `protons_to` the wrong side, `components` out of order or missing a carrier,
glycolysis outside the cytosol, the light reactions in an animal cell, ATP synthase before any
protons were pumped.

```yaml
# energy metabolism
- id: krebs
  type: metabolism
  params:
    title: "The citric acid cycle"
    process: tca                      # glycolysis, link_reaction, tca, etc, light_reactions
  beats:
    - text: "Acetyl-CoA joins oxaloacetate; two carbons leave as CO2."
      actions: [{advance: tca, to: succinyl_coa, at: "@joins"}]
    - text: "The cycle closes with GTP, FADH2 and NADH."
      actions: [{advance: tca, to: oxaloacetate}]
```

A `cross` scene works a genetic cross out exactly (DESIGN §96: the cross engine, fractions, no hand-written ratios) and draws it: the parents with their homologous chromosomes and phenotype pictures (peas, flowers, flies, coats, blood groups…), their gametes (each allele in the colour of the homologue it came from; recombinants of linked loci ringed, with their frequencies), a Punnett square up to 4 × 4 (8 × 8 with `show: punnett`) or a branch (forked-line) diagram beyond, and the offspring counted into genotype and phenotype classes — exact fractions in lowest terms, percentages, the whole-number ratio (9 : 3 : 3 : 1, 9 : 3 : 4, 2 : 1 with the lethal class crossed out; X-linked crosses split by sex, X and Y in the headers). Use a `preset` (pea_seed_shape, pea_dihybrid, snapdragon, abo, rabbit_coat, labrador, squash_colour, chicken_feathers, shepherds_purse, sweet_pea, squash_shape, yellow_mouse, drosophila_white, hemophilia_a, drosophila_b_vg) or write the `loci`. Genotypes are textbook notation: `RrYy`, `I^A i`, `X^H X^h`, `X^h Y`, linked loci with their phase `AB/ab`. `P: [RRYY, rryy]` crosses the P generation to its F1 and shows the F2; `kind: test` makes the tester; `kind: reciprocal` swaps the sexes of the lines. `observed` counts add a chi-square table (χ², df, p, the critical value, the verdict). Without cross actions the scene plays itself beat by beat; `form_gametes`, `fill` (`square`, `row2`, `cell1.3`, `"cells:wrinkled, green"`; `by: row`), `count` (`phenotypes` / `genotypes`), `ratio` and `chi_square` (`test`) put each step on a word, and `highlight` marks a class's cells (`style: box`). Checked with the reason: alleles that do not exist (did you mean…), X-linked alleles off their X, a female with a Y, linked loci without their phase, RF over 0.5, a P generation that is not true-breeding, counts for classes the cross does not have, a cell filled twice.

```yaml
# genetics
- id: dihybrid
  type: cross
  params:
    title: "A dihybrid cross"
    preset: pea_dihybrid               # or loci: [{gene: R, trait: seed shape, alleles: {R: round, r: wrinkled}}, ...]
    parents: [RrYy, RrYy]              # P: [RRYY, rryy] for P → F1 → F2; kind: test with one parent
  beats:
    - text: "Each parent makes four kinds of gametes, in equal numbers."
      actions: [{form_gametes: both, at: "@four"}]
    - text: "Sixteen equally likely combinations fill the square."
      actions: [{fill: square, by: row}]
    - text: "Counted, they give nine to three to three to one."
      actions: [{count: phenotypes}, {ratio: phenotypes, at: "@nine"}]
```

A `pedigree` scene draws a family chart in standard human pedigree nomenclature (NSGC: square male, circle female, diamond sex unknown; affected filled, a carrier a dot — `carrier_style: half` for the half-shaded heterozygote —, deceased struck, the proband's arrow with P, double line for consanguinity, MZ / DZ twins, adoption brackets, a miscarriage triangle, a proposed child dashed with ?) laid out by generation (Roman numerals, individuals numbered left to right, sibships in birth order, partners from outside beside the relative), and works its genetics out exactly (DESIGN §96.8): which modes of inheritance fit (AD, AR, XD, XR, Y-linked, mitochondrial; an excluded one with its reason, e.g. *father-to-son: a son's X comes from his mother*), the genotypes the chart forces (obligate carriers), carrier probabilities by Bayes' rule on the whole chart (2/3 for an unaffected sibling under AR), and the risk for a proposed child with its factors (2/3 × 1/25 × 1/4 = 1/150). Write each person as a line — `"II-3: female affected deceased of I-1 + I-2"`, flags `carrier`, `proband`, `consultand`, `proposed`, `miscarriage`, `adopted in`, `twin II-4 MZ`, `spouse II-5`, `age 45 y` last — or as a mapping (`{id, sex, affected, parents: [I-1, I-2], twin: {with, kind}}`). Use NSGC ids (`II-3`, numbered left to right as drawn: a partner from outside stands beside the relative) or any names (schu-video-generator numbers the chart). The analysis assumes a rare allele (people marrying in do not carry it: `rare: false` or `carrier_frequency: 1/25` for a common one) and full penetrance (`penetrance: 0.8` lets a dominant trait skip a generation). `mode` sets the mode for genotypes and risk (default: the only one that fits; `preset: hemophilia_a` gives X-linked recessive with H / h). The actions: `analyse: modes` (one by one, the people a reason names ringed; `mode:XR` for one), `deduce: genotypes` (`carriers`, `generation:II`, `person:II-3`), `risk: risk`; `reveal: "generation:II"` or `"person:II-3"` brings people in on a word, `highlight` marks them. Checked with the reason: a child with two fathers, a cycle, twins who are not siblings, numbers that do not read left to right, a male carrier under X-linked inheritance, genotypes or risk when several modes fit and none is stated.

```yaml
# genetics
- id: family
  type: pedigree
  params:
    title: "Who carries the allele?"
    condition: cystic fibrosis
    carrier_frequency: 1/25            # for people marrying in; mode: AR is the only mode that fits
    individuals:
      - "I-1: male"
      - "I-2: female"
      - "II-1: male of I-1 + I-2"
      - "II-2: female affected proband of I-1 + I-2"
      - "II-3: male of I-1 + I-2"
      - "II-4: female"                 # married in, beside II-3
      - "III-1: unknown proposed of II-3 + II-4"
  beats:
    - text: "Unaffected parents, an affected daughter: only a recessive mode fits."
      actions: [{analyse: modes}]
    - text: "Her brother is a carrier with probability two thirds; the risk is one in 150."
      actions: [{deduce: genotypes}, {risk: risk, at: "@risk"}]
```

A `linkage_map` scene shows linked genes (DESIGN §96.9): the heterozygous parent's homologue pair (sister chromatids joined at the centromere, maternal and paternal colours) with its alleles, and crossing over in an interval — the non-sister chromatids meet at a chiasma and swap the segments beyond it, giving recombinant chromatids (labelled with their alleles). With `loci` and `counts` it works a two- or three-point test cross out step by step: the table of offspring classes, the parental classes (the largest reciprocal pair; they give the phase, coupling or repulsion) and the double crossovers (the smallest), the gene order (the locus at which a double crossover differs from a parental class is in the middle), each interval's recombinants, RF and distance, the expected and observed double crossovers with the coefficient of coincidence and the interference, and the map. Write each class with every locus once: the mutant allele by its symbol, the wild type as `v+` or `+` (`"v cv+ ct+": 580`). Distances are RF × 100 cM (`map_function: none`, what three-point analyses report; right below ~15 cM) or Haldane's / Kosambi's map function. With `map: {y: 0, w: 1.5, v: 33}` the loci stand at their positions; `measure: "interval:w-v"` shows a distance and the RF it gives. `cross_over: "interval:v-ct"` (or `double`) plays the crossing over on a word; `reveal: order` (or `table`, `classes`, `distances`, `interference`, `map`) plays a step. Checked with the reason: missing or doubled classes, an unknown locus, parental or double-crossover pairs that cannot be told, a crossover between loci that are not neighbours.

```yaml
# genetics
- id: map
  type: linkage_map
  params:
    title: "Mapping three genes"
    loci: [v, cv, ct]                  # mutant alleles, any order: the order is worked out
    counts: {"v cv+ ct+": 580, "v+ cv ct": 592, "v cv ct+": 45, "v+ cv+ ct": 40, "v cv ct": 89, "v+ cv+ ct+": 94, "v cv+ ct": 3, "v+ cv ct+": 5}
  beats:
    - text: "Crossing over gives recombinant gametes; the rarest classes are double crossovers."
    - text: "So ct lies in the middle, 13.2 and 6.4 centimorgans from its neighbours."
```

A `karyotype` scene draws a human karyotype from its ISCN notation (DESIGN §96.10), checked: the count against the chromosomes listed (`47,XX` lists 46: write 46,XX), the sex chromosomes, each change and its bands (`5p16` does not exist: 5p ends at 5p15). Supported: `+21`, `-21`, `del(5)(p15.2)`, `del(1)(q21q32)`, `dup(1)(q21q32)`, `inv(9)(p12q13)`, `t(9;22)(q34;q11.2)`, `rob(14;21)(q10;q10)`; sex chromosome aneuploidy in the sex chromosomes (`45,X`, `47,XXY`). `show: karyogram` (default for numerical changes) arranges the pairs 1–22, X, Y in the Denver groups A–G with schematic G-banded ideograms (true relative lengths and centromere positions; satellites on 13, 14, 15, 21, 22) and highlights the change; `show: ideogram` (default when every change is structural, or with `chromosomes: [7]`) draws the chromosomes involved large, with p and q and `bands: {7q31.2: CFTR}` labelled, and plays each structural change as an edit — a deletion falls away, an inversion turns round, a translocation's segments swap, a Robertsonian translocation joins two long arms. A card reads the notation (and names the classic condition: Down, Turner, Klinefelter, cri-du-chat, the Philadelphia chromosome…). The band pattern is schematic: say "band q31" but do not read exact positions off it. `rearrange: change:1` plays a change on a word.

```yaml
# genetics
- id: karyotype
  type: karyotype
  params:
    title: "Trisomy 21"
    karyotype: "47,XY,+21"             # or 46,XX,t(9;22)(q34;q11.2): its edit plays in an ideogram
  beats:
    - text: "A male karyotype, its chromosomes in pairs by size, three copies of chromosome twenty-one."
    - text: "Forty-seven, X Y, plus twenty-one: Down syndrome."
```

A `mutation` scene works a sequence variant out on a real coding sequence with the genetic code (DESIGN §96.13): the reference codons with their amino acids (the initiator Met is residue 1) and the variant row made from them — a base swaps, or bases leave or come in and the rest slide through the fixed codon frame, so a frameshift regroups every codon after it and reaches its premature stop. Give a reference window (`gene: HBB`, `CFTR`, `GJB2`: real coding sequence with its exons and transcript), your own `sequence:` (with `first:`, `exons:`, `length:` when you want splice sites and nonsense-mediated decay), or a gene like a `molecule` scene's (`gene: {protein: MVHL…, introns: 1}`). The `variant:` is HGVS on the coding DNA (`c.20A>T`, `c.1521_1523delCTT`, `c.35delG`, `c.35dup`, `c.76_77insT`, `c.76_77delinsTT`, `c.92+1G>A`); schu-video-generator computes the protein change (`p.(Glu7Val)`, `p.(Phe508del)`, `p.(Arg553*)`, `p.(Gly12Valfs*2)`, `p.?` for a splice site with the exon skipped or the intron retained), the class and the notes (side chains, the frame, nonsense-mediated decay), and checks a `p:` you write against the sequence. Use `legacy:` for the old name (ΔF508, Glu6Val: HGVS counts the initiator Met, so HbS is `c.20A>T p.(Glu7Val)`). A list of variants plays one after another; `mutate: variant` puts one on a word. Checked with the reason: a change that is not HGVS, a reference base that is not there, a description that is not the canonical one (the 3′ rule), a stated `p.` that does not follow, `p.R553X` and `ΔF508`.

```yaml
# genetics
- id: sickle
  type: mutation
  params:
    title: "Sickle-cell haemoglobin"
    gene: HBB                                  # or sequence: ATGGTG…, or gene: {protein: …, introns: 1}
    variant: {c: "c.20A>T", p: "p.(Glu7Val)"}  # p. is checked; legacy name Glu6Val
  beats:
    - text: "The start of the beta-globin coding sequence, read in codons."
    - text: "One base changes: A to T in codon seven."
      actions: [{mutate: variant, at: "@changes"}]
    - text: "Glutamic acid becomes valine: sickle-cell haemoglobin."
```

A `crispr` scene shows Cas9 editing a target (DESIGN §96.14): the DNA with every base, the sgRNA's 20-nt spacer (21–23 for SaCas9) pairing with the target strand, the PAM (`NGG`; `NNGRRT` for SaCas9) right after the protospacer's 3′ end on the other strand, the R-loop, the blunt double-strand break 3 bp upstream of the PAM, and the repair: `nhej` (a small indel — `indel: +1` is the commonest, and an indel that is not a multiple of 3 is a frameshift knockout) or `hdr` (a donor carrying `edit:`). Leave `spacer` out and schu-video-generator picks a guide from the PAMs it finds (`guide: 2` for the n-th); with `coding_first:` (the `c.` number of the target's first base) the outcome is written in HGVS with its protein change. `scan`, `cleave` and `repair` put the steps on words. Checked with the reason: a spacer that is not in the target or has no PAM after it (with the guides that would work), the wrong length for the enzyme, a spacer written with its PAM, a target without any PAM.

```yaml
# genetics
- id: edit
  type: crispr
  params:
    title: "Cutting with Cas9"
    target: "GACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGGAGAAGTCTGCC"
    repair: nhej                       # or hdr with edit: 25A>T (c.20A>T with coding_first)
  beats:
    - text: "The guide binds beside its PAM, and three base pairs away both strands break."
      actions: [{scan: dna}, {cleave: dna, at: "@break"}]
```

A `dna_lab` scene shows one laboratory method (DESIGN §96.15). `method: pcr`: the primers checked against the template (the forward primer repeats the top strand, the reverse primer is the reverse complement downstream), the product's length, melting temperatures and an annealing temperature ~5 °C below them, the temperature trace (denature ~95 °C, anneal, extend 72 °C with Taq) and the copies — 2ⁿ molecules after n cycles, 2ⁿ − 2n of exactly the product's length, the first in cycle 3. `method: gel`: an agarose gel, DNA running from the wells at the cathode to the anode, the distance log-linear in size within the gel's range, a `ladder` and each band's size read off it. `method: sanger`: chain termination with ddNTPs, the fragments sorted by length and a chromatogram with the called bases (`heterozygous: "8T>C"` gives two half-height peaks and a Y). `method: ngs`: seeded reads aligned to a reference with their coverage and a variant call (≈50 % alt reads: heterozygous). `run: <step>` plays a step on a word (the steps before it play first).

```yaml
# genetics
- id: pcr
  type: dna_lab
  params:
    title: "PCR"
    method: pcr
    template: "GCTTACCAGTCGATGCCATGACTGCATCAGCTGAAGGTCACCATGGTGCATCTGACTCCTGAGG"
    primers: {forward: "GACTGCATCAGCTGAAGGTC", reverse: "CCTCAGGAGTCAGATGCACC"}
  beats:
    - text: "A template, two primers, and a product of a defined length."
    - text: "The strands separate, the primers anneal, Taq extends them."
      actions: [{run: trace}]
    - text: "The molecules double every cycle."
      actions: [{run: counts}]
```

A `population` scene shows population genetics (DESIGN §96.16). `model: hardy_weinberg` (the default) draws the population as dots by genotype and works the numbers out exactly, one step a beat: p and q from genotype `counts` (or `frequencies`, `p`, or the `incidence` of a recessive condition: q = √incidence, so 1/2500 gives q = 1/50 and carriers 2pq = 49/1250 ≈ 1 in 25.5, about 2q), the expected p², 2pq, q² (with `inbreeding` F: p² + Fpq, 2pq(1 − F), q² + Fpq) and, from counts, the chi-square test of Hardy–Weinberg proportions with df = 1 (three genotypes − 1 − one estimated allele frequency). Simulations are seeded Wright–Fisher runs of N diploids (2N gene copies drawn each generation): `drift` (replicate lines from `p0`; fixation and loss; heterozygosity falling as H₀(1 − 1/2N)ᵗ), `selection` (`fitness` of AA, Aa, aa, or `s` and `h`; the deterministic course as a thick line, drifting lines around it with `N`), `mutation` (`mu`, `nu`), `migration` (two `populations` and `m`), `bottleneck` (`{at, N, generations}`) and `founder` (`founders` from a source at `p0`). `simulate: "generation:40"` grows the lines on a word, `resample: population` draws the next generation, `reveal: chi_square` plays a Hardy–Weinberg step, `highlight: fixed` marks the lines that fixed. Checked with the reason: frequencies outside [0, 1], genotype frequencies that do not add up to 1, counts that do not add up to the `total`, negative fitness, a param of another model.

```yaml
# genetics
- id: drift
  type: population
  params:
    title: "Genetic drift"
    model: drift                       # or hardy_weinberg with counts / incidence, selection, migration, bottleneck, founder
    N: 20
    p0: 0.5
    generations: 50
    replicates: 3
    seed: 36
  beats:
    - text: "Three populations of twenty individuals start at one half."
    - text: "Each generation samples only forty gene copies: some lines fix the allele, others lose it."
      actions: [{simulate: lines}]
```

```yaml
# genetics
- id: carriers
  type: population
  params:
    title: "Carriers of cystic fibrosis"
    incidence: 1/2500                  # q² = incidence for a recessive condition
    condition: cystic fibrosis
  beats:
    - text: "One baby in two thousand five hundred has cystic fibrosis, so q is one in fifty."
    - text: "Two p q: about one person in twenty-five carries the allele."
      actions: [{reveal: carriers}]
```

A `gwas` scene draws a genome-wide association study (DESIGN §96.17): a Manhattan plot of −log₁₀ p along chromosomes 1–22 (alternating colours; X with `x_chromosome: true`), the genome-wide significance line at 5 × 10⁻⁸ and the suggestive line at 1 × 10⁻⁵, peaks labelled with their gene or lead variant; `plot: qq` or `both` adds a QQ plot with λ_GC; `regional: "peak:FTO"` (an action or a param) zooms into a locus with its variants coloured by r² with the lead. Give real data as `data: assoc.csv` (columns CHR, BP, P, SNP…; lead variants are clumped and labelled from `labels: {rs9939609: FTO}`) or `variants:` inline — or `peaks:` for a seeded synthetic study (a null background and your peaks with LD around them), which the plot labels "simulated data": never present synthetic peaks as a real study's results. Checked: p-values outside (0, 1], unknown chromosomes, positions written in Mb as bp or past the chromosome's end.

```yaml
# genetics
- id: gwas
  type: gwas
  params:
    title: "A genome-wide association study"
    trait: body mass index
    peaks:                             # synthetic (shown as simulated data); or data: assoc.csv
      - {chromosome: 16, position: 53.8 Mb, p: 1e-40, gene: FTO}
      - {chromosome: 18, position: 60.2 Mb, p: 2e-14, gene: MC4R}
  beats:
    - text: "Every dot is a variant tested for association with body mass index."
    - text: "Two loci pass genome-wide significance, five times ten to the minus eight."
      actions: [{reveal: thresholds}, {reveal: peaks, at: "@loci"}]
```

In `cell_cycle` meiosis, `nondisjunction: {division: I, pair: 1}` makes that pair's homologues go to one pole at anaphase I (every gamete n + 1 or n − 1), `division: II` its sister chromatids stay together at anaphase II in one cell (half the gametes normal); the gametes are labelled and the last caption gives the zygotes after fertilisation (trisomic, monosomic, euploid).

Accuracy and sources. `vidgen lint` checks the science of these scenes (and of any narration)
with the `science_*` rules: sizes far off scale on a `cell` with a scale bar (set `not_to_scale:
true` when you exaggerate on purpose: the scene then says so), places ("glycolysis in the
mitochondria", "ribosomes in the nucleus" while the picture has them in the cytosol), directions
(RNA made 3′ to 5′, a protein made C to N, kinesin to the minus end, protons pumped into the
matrix), active transport through a channel or with no energy source shown, gene / protein names
(mouse *Trp53* gene, TRP53 protein; `<i>…</i>` for a gene in a label), narration against a
pathway arc ("Akt activates TSC2" where Akt's arc inhibits it) and numbers (net 2 ATP from
glycolysis, 3 NADH per turn, 3 Na⁺ out and 2 K⁺ in per pump cycle). Fix the words, or the
picture. Give a scene `references:` — `{label, doi | pmid | isbn | url, id}` copied from your real
sources, **never invented** (no identifier you have not seen; leave a reference out rather than
guess) — and they appear as small citations (`citations: {show: footer | marker | card | none}`,
numbered across the video; a beat's `cite: [id]` shows only what it cites) and as a numbered list
in the description file `<output>_chapters.txt`. A real micrograph shown with an `image` scene
gets `figure_credit: {text, license, url}`. How to choose, keep it correct and pace a dense
script: `vidgen guide biology` and `docs/COOKBOOK-CELL-BIOLOGY.md` (example:
`examples/gene-to-secreted-protein`).

The genetics scenes are checked the same way by the `genetics_*` rules, against what each scene
computes: a ratio or share the `cross` does not give ("a 3:1 ratio" for a dihybrid — say "each
trait alone segregates 3:1" if you mean one trait —, "half the daughters affected" for a carrier
mother), a `pedigree` that does not fit its `mode` (an error), "a dominant trait skips a
generation" without reduced penetrance, father-to-son transmission of an X-linked trait, a carrier
or risk probability the chart does not give ("II-3 is a carrier with probability 1/2" where it is
2/3), RF over 50 % or a distance against the `linkage_map`, Hardy–Weinberg slips (carriers are
2pq, not q²; q = √incidence), a wrong PAM or cut for the Cas (SpCas9: NGG, a blunt cut 3 bp
upstream of the PAM), karyotype notation and the condition or sex it names ("45,X is female",
`47,XY,+18` is not trisomy 21; changes in ISCN order), and HGVS that is not the `mutation`'s
variant or uses the legacy numbering unannounced (HbS is p.(Glu7Val); say "legacy Glu6Val");
`ΔF508` and `R553X` are reported as info — write the HGVS form and call the old one legacy.
Say numbers exactly as the scene computes them (or with "about"); conditional and comparative
sentences ("if both parents are carriers…", "unlike Down syndrome…") are not read. Choosing among
the genetics types, notation, exactness and pacing: `vidgen guide genetics` and
`docs/COOKBOOK-GENETICS.md` (example: `examples/cystic-fibrosis`).

Numbers in calculations and plots are checked too. The `calc_*` rules read the numbers the
narration and the screen say — in digits or words: "thirty kilometres per second", "eleven point
two", "three point seven times ten to the minus nineteen joules", "one in a hundred and fifty" —
against what each `calculation` scene computes (`calc_numbers`: a value that is not the result,
"about" allows rounding to one or two figures; `calc_units`: "a speed of 30 kilometres", or 30 m/s
for 29.8 km/s; `calc_sigfigs`, info: "29.7847 km/s" for a result known to 3 figures, or a `sig`
beyond the inputs). Give each symbol and result a `meaning`: a pure number ("one in a hundred and
fifty") is only compared when the sentence names it. The `plot_*` rules check a `plot`: an axis of
a physical quantity without its unit (`plot_units`), error bars, fits or lines at or below zero on
a log axis (`plot_log`), error bars without `error:` (sd, sem, ci95…) or called something else in
the narration (`plot_errors`), series without a legend or label (`plot_series`), bars not starting
at zero (`plot_truncated`, info; also a `bar_chart` `baseline`), a model's `conserved` quantity
drifting (`plot_conserved`: use `method: leapfrog` or a smaller `step`), and a fitted value said
otherwise ("a half-life of twelve days" for a fit giving 8.0 ± 0.1 d; `plot_fit_claims`).
Choosing between a plot and a chart, fits, live models, units and pacing for calculations: `vidgen
guide science` and `docs/COOKBOOK-SCIENCE-CHARTS.md` (example: `examples/radioactive-decay`).

```yaml
# accuracy and references
- id: er
  type: cell
  params:
    objects: [{kind: vesicle, id: big_vesicle, size: "400 nm"}]   # larger than real: say so
    not_to_scale: true
  references:                          # placeholders here: copy the real identifiers from your sources
    - {id: book, label: "Example textbook (placeholder)", isbn: "978-0-00-000000-2"}
  beats:
    - text: "Transport vesicles carry cargo from the ER to the Golgi."
      cite: [book]
```

```yaml
# data
- id: users
  type: stat
  params:
    value: 73
    suffix: "%"
    label: "of developers use AI tools"
    comparison: {value: 44, label: "in 2023"}
    context: "Survey of 12,000 developers"
  beats:
    - text: "Almost three in four developers now use AI tools."
    - text: "Two years ago, it was not even half."
- id: speed
  type: bar_chart
  params: {title: "Render time per minute", labels: ["480p", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min", caption: "Measured on 2 CPUs"}
  beats:
    - text: "Higher resolutions take much longer."
    - text: "Four K is twenty-five times slower than a preview."
      actions: [{highlight: "bar:4K", style: box}]
- id: loss
  type: line_chart
  params:
    title: "Validation loss"
    x: [1, 2, 3, 4, 5]
    x_label: "epoch"
    series: {baseline: [2.1, 1.8, 1.66, 1.58, 1.53], sparse: [2.2, 1.9, 1.68, 1.55, 1.49]}
  beats:
    - text: "The baseline improves steadily."
    - text: "The sparse model starts slower, but ends lower."
- id: ranking
  type: bar_chart
  params:
    title: "Most loved languages"
    labels: [Python, Rust, Go]
    values: [62, 48, 31]
    changes: [[58, 66, 30], [55, 72, 41]]   # the values at each later step; bars grow / shrink
    sort: true                              # and re-sort, largest first
    unit: "%"
  beats:
    - text: "In the first survey, Python led."
    - text: "A year later Rust overtook it."
    - text: "Then Go climbed as well."
      actions: [{reveal: change2, at: "@climbed"}]   # change 2 on that word
- id: training
  type: line_chart
  params:
    title: "Training loss"
    x: [1, 2, 3, 4]
    series: {loss: [2.4, 1.8, 1.4, 1.2], accuracy: [0.3, 0.5, 0.6, 0.65]}
    changes: [{loss: [1.0, 0.5, 0.3, 0.2]}]   # series left out keep their values; the y axis rescales
    reveal: all
  beats:
    - text: "Here is the loss over four epochs."
      actions: [{trace: "series:loss", to: 3, at: "@four"}]   # a cursor dot with the value sweeps the line
    - text: "With pretraining it starts far lower."
- id: size_vs_accuracy
  type: scatter
  params:
    title: "Size vs accuracy"
    x_label: "parameters (billions)"
    y_label: "accuracy (%)"
    trend: all
    series: {baselines: [[1.3, 61], [6.7, 70], [13, 73]], ours: [[1.0, 66], [3.8, 72, "small"]]}
    highlight: "ours@small"
  beats:
    - text: "Bigger baselines score higher."
    - text: "Ours sit above the line."
    - text: "The trend makes the gap clear."
    - text: "Especially for the small one."
- id: latency
  type: histogram
  params:
    title: "Response times"
    x_label: "milliseconds"
    values: [12, 15, 17, 18, 21, 22, 23, 25, 26, 28, 30, 31, 33, 35, 38, 41, 45, 52, 61, 75, 97]
    median: true
  beats:
    - text: "Most requests finish fast."
    - text: "Half of them in under thirty milliseconds."
```

Scientific plots and worked calculations (the craft: `vidgen guide science`):

```yaml
# science charts
- id: decay_fit
  type: plot
  params:
    title: "Fitting the decay"
    x: {label: time, unit: d}
    y: {label: activity, unit: Bq}
    series:   # error bars: y_err (number, list, column, {minus, plus} or sqrt) and what they mean (sd, sem, ci95, range)
      - {name: measured, style: points, x: [0, 4, 8, 14, 20, 30, 40], y: [1000, 712, 494, 302, 180, 73, 32], y_err: 20, error: sem}
    fits:     # linear, poly, exponential, power, logistic, gaussian, breit_wigner (background: n), custom (expr + params)
      - {series: measured, model: exponential, name: decay, band: confidence, residuals: true}
    annotations:   # label, arrow, hline, vline, xrange, yrange, note
      - {type: label, series: measured, x: 8, text: "half after 8 days", id: half}
  beats:
    - text: "The measured activity, with its error bars."
    - text: "An exponential fits the points, with its parameters and their errors."
      actions: [{fit: "fit:decay", at: "@exponential"}]
    - text: "After eight days, half is left."
      actions: [{annotate: "annotation:half", at: "@half"}]
- id: decay
  type: plot
  params:
    title: "Activity of an iodine-131 sample"
    x: {label: time, unit: d}
    y: {label: activity, unit: Bq, scale: log}
    # from a file: data: assets/decay.csv, then x: time, y: activity name its columns
    series:
      - {name: measured, style: points, x: [0, 4, 8, 14, 20, 30, 40], y: [1000, 712, 494, 302, 180, 73, 32]}
      - {name: "model, half-life 8.0 d", dashed: true, x: [0, 40], y: [1000, 31.25]}
  beats:
    - text: "The activity halves every eight days."
    - text: "On a log axis that decay is a straight line."
- id: oscillator
  type: plot
  params:
    title: "A damped oscillator"
    models:   # ode (equations, initial, params, t, method: rk4 | rk45 | leapfrog), recurrence, random_walk, poisson, function
      osc:
        kind: ode
        equations: {x: v, v: "-k*x - c*v"}   # x' = v, v' = -k x - c v
        params: {k: 4, c: 0.3}
        initial: {x: 1, v: 0}
        t: [0, 20]
        units: {t: s, x: m, v: m/s}
    arrange: columns
    share: false
    legend: false
    panels:   # a model's series grow live over their beat; readout: the current value; trail: a fading path
      - series: [{name: position, x: t, y: x, readout: true}]
      - series: [{name: phase, x: x, y: v, trail: 3}]
  beats:
    - text: "Friction takes the energy away, so each swing is smaller."
    - text: "In phase space the state spirals in towards rest."
      actions: [{zoom: panel1, x: [0, 5], at: "@phase"}]
- id: orbit_speed
  type: calculation   # formula -> values with units -> result with significant figures -> conversion
  params:
    title: "How fast does the Earth orbit the Sun?"
    symbols:   # value: a number with its unit ("29.8 km/s", "1/25", "6.674e-11 m^3 kg^-1 s^-2"), or a constant (CODATA / IAU)
      - {name: G, constant: G}
      - {name: M_sun, constant: M_sun}
      - {name: r, constant: AU, meaning: "Earth–Sun distance"}
    calculations:   # expr uses the symbols' names; a later calculation may use an earlier result's name
      - {name: v, expr: "sqrt(G*M_sun/r)", sig: 3, convert: km/s, meaning: orbital speed}
  beats:
    - text: "Gravity holds the Earth on its orbit, so its speed is the square root of G M over r."
    - text: "Put in the numbers, and the Earth moves at about thirty kilometres per second."
      actions: [{substitute: calc1, at: "@numbers"}, {compute: calc1, at: "@moves"}]
```

Planets, moons and spacecraft on their orbits, in correct timing (the craft: `vidgen guide orbits`):

```yaml
# orbital mechanics
- id: inner_planets
  type: orbit   # bodies move by Kepler's equation at one speed-up from the first beat to the scene's end
  params:
    title: "The inner planets for one Earth year"
    central: sun   # a preset (sun, earth, mars, jupiter...) or {name, gm or mass, radius}
    bodies:        # presets: mercury ... neptune (JPL J2000 elements), moon, iss, geo, halley
      - {preset: mercury}
      - {preset: earth}
      - {name: Comet, a: "1.5 AU", e: 0.7, argp: 180, nu: 180, trail: 0.15}   # values carry units; angles in degrees
    span: "1 yr"   # or orbits: 2 (periods of the first body)
    caption: "J2000 elements (JPL approximate positions)"
  beats:
    - text: "Mercury races around the Sun in eighty-eight days."
    - text: "The comet crawls far out and sweeps past the Sun."
- id: kepler_laws
  type: orbit
  params:
    title: "Equal areas in equal times"
    bodies:
      - name: Comet
        a: "3 AU"
        e: 0.75
        nu: 150
        geometry: true        # foci, a and b, perihelion / aphelion with their distances
        sectors: 8            # Kepler II: 8 equal times, each area computed and listed
        velocity: {along: 12} # arrows ∝ speed with a key, the vis-viva speed in the panel
    orbits: 1.2
  beats:
    - text: "The Sun sits at one focus; the other is empty."
      actions: [{reveal: "foci:Comet", at: "@focus"}]
    - text: "From now on we sweep eight equal times."
      actions: [{sweep: "sectors:Comet", at: "@sweep"}]
- id: newtons_cannon
  type: orbit
  params:
    title: "Newton's cannonball"
    central: earth
    cannonball: {altitude: "1500 km", speeds: [0.6, circular, 1.2, escape, 1.6]}   # × circular speed; classified by energy
    span: "6 h"
  beats:
    - text: "Too slow, it falls back; at the circular speed it falls around the Earth."
      actions: [{launch: "shot:1", at: "@slow"}, {launch: "shot:2", at: "@circular"}]
    - text: "Faster, an ellipse; at the escape speed it never returns."
      actions: [{launch: "shot:3", at: "@ellipse"}, {launch: "shot:4", at: "@escape"}, {launch: "shot:5"}]
- id: to_mars
  type: orbit
  params:
    title: "Earth to Mars"
    bodies:
      - {preset: earth, e: 0, i: 0, raan: 0, argp: 0}   # a transfer is between circular, coplanar orbits
      - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 75}
      - {name: Ship, alongside: Earth}
    transfer: {ship: Ship, to: Mars}   # Hohmann: Δv₁, Δv₂, 259 d, phase angle 44.3°, windows every 780 d
    caption: "Circular, coplanar orbits (an approximation)"
  beats:
    - text: "We wait for Mars to lead by forty-four degrees, then burn."
      actions: [{burn: "burn:1", at: "@burn"}]   # the clock runs so the burn falls on this word
    - text: "Two hundred and fifty-nine days later Mars is there."
      actions: [{burn: "burn:2", at: "@there"}]
- id: gravity_assist
  type: orbit
  params:
    title: "A gravity assist at Jupiter"
    central: jupiter
    flyby: {v_inf: "5.6 km/s", altitude: "400000 km", angle: 100, side: behind}   # δ, asymptotes, Sun-frame vectors
  beats:
    - text: "Passing behind Jupiter, the probe leaves faster around the Sun."
      actions: [{action: flyby, at: "@behind"}]   # the closest approach on this word
- id: trojans
  type: orbit
  params:
    title: "Trojans of Jupiter"
    system: sun_jupiter   # earth_moon, sun_earth, sun_jupiter, {primary, secondary, mu}, figure_eight
    lagrange: true        # L1–L5 for the mass ratio; Routh's test and the Jacobi constant in the panel
    bodies:
      - {name: Trojan, near: L4, shift: [0.004, 0.0069], trail: "150 yr"}
    span: "300 yr"
  beats:
    - text: "Seen from the stars, Jupiter and its Trojan go round together."
    - text: "Now let the frame turn with Jupiter: the Trojan traces a tadpole."
      actions: [{action: corotate, at: "@turn"}]   # inertial -> rotating frame on this word
- id: tides
  type: orbit
  params: {central: earth, tides: true}   # a schematic: pull, tidal arrows, bulges, the Moon's near side
  beats:
    - text: "Take away the pull at the centre, and what is left stretches the Earth."
      actions: [{reveal: tidal, at: "@left"}]
- id: mars_opposition
  type: orbit
  params:
    title: "Mars at opposition"
    date: 2020-06-01   # the planets where JPL's approximate elements put them that day (1800–2050); the panel shows the date
    bodies: [{preset: earth}, {preset: mars}]
    event: {kind: opposition, of: Mars}   # the next one after the date (root finding), drawn as the line they will stand on
    caption: "Positions from JPL's approximate planetary elements"
  beats:
    - text: "In mid October the Earth overtakes Mars: Mars is at opposition."
- id: planet_sizes
  type: orbit
  params: {title: "The planets' sizes to scale", sizes: true}   # radii to one scale side by side, the Sun's edge first
  beats:
    - text: "Jupiter is eleven times as wide as the Earth."
```

The Solar System on a date: `date` (1800–2050, refused outside), `event` (opposition,
conjunction, inferior_conjunction, superior_conjunction, aligned; `of`, `observer`), `radial:
log` (every planet in one picture, distances compressed and labelled so, rings instead of axes),
`inset: true` (the inner planets to scale in a box beside a true-scale picture), `sizes` (radii
to scale; `{bodies: [earth, moon, mars]}`); presets add `pluto`.

The side panel is compact by default: the time, the speed-up and the few values the scene is
about, at a readable size. `panel: full` shows every row (diagnostics too: ΔE/E, ΔL/L, the
Jacobi drift), `panel: none` only the "not to scale" note, or name the rows: `panel: [date,
event, distance]` (time, speedup, energy, legend, total_dv, dv, phase, mu, frame, coorbital…; see
CONFIG). `energy: true` puts ΔE/E in a compact panel.

Many bodies: `system` (a restricted three-body pair or the figure-eight), `view: rotating`,
`lagrange`, `zero_velocity`, bodies `near: L4` with `shift`; `resonance: [Io, Europa, Ganymede]`
(period ratios, the Laplace angle, conjunctions); `origin: barycentre` (a binary star);
`curvature: true` on a body; `center` with `extent` for a close-up; the actions `corotate` and
`inertial` switch the frame on a word.

Burns on a body: `burns: [{at: "20 min", prograde: "0.6 km/s"}, {at: apoapsis, prograde: "0.55
km/s"}]` (also retrograde, radial, anti_radial, normal, anti_normal); `transfer: {kind: hohmann |
bielliptic | phasing, ship, to: <body or radius>}`; `- action: pause` / `- action: coast` hold
and run the clock; a `calculation` takes the computed Δv with `from_scene: <orbit scene>.dv1`.

Kepler's third law is a `plot` fed by the built-in model `kepler_planets` (the planets' `a` in
AU, `T` in years): `models: {planets: {kind: function, function: kepler_planets, units: {a: AU,
T: yr}}}`, log axes and a `power` fit, whose exponent comes out 1.500.

`vidgen lint` checks orbit scenes against their own model (the config, not the stills): a period
said for a body (`orbit_period`: "Mars takes about two years" fits 1.88 yr, "three years" does
not), a speed at the point named (`orbit_speed`: vis-viva at perihelion / aphelion, escape and
circular speeds), Δv (`orbit_dv`: "the first burn", "in all"), transfer times, phase angles and
launch windows (`orbit_transfer`), distances, altitudes, Lagrange points and size ratios
(`orbit_distance`: "the Moon is 384,000 km away" fits; "L2 is 15 million km away" does not),
opposition and conjunction dates in any scene (`orbit_date`), "to scale" said of enlarged bodies
or a log view (`orbit_scale`: say "the distances are to scale, the sizes are not"), an n-body run
drifting (`orbit_conserved`) and a periapsis in the atmosphere (`orbit_crash`). A card or caption
naming a body is checked against the orbit scenes too. Write numbers as a viewer hears them, with
"about" when rounded.

The particles of the Standard Model (values from PDG 2024; the model `vidgen.api.particle_physics`
also checks reactions and decays: `particle_physics.check("n -> p e- anti-nu_e").explain()`; the
craft: `vidgen guide particle-physics`):

```yaml
# particle physics
- id: standard_model
  type: standard_model   # quarks and leptons in three generations, gauge bosons, Higgs; mass, charge, spin per cell
  params:
    title: "The Standard Model of particle physics"
    reveal: groups       # quarks, leptons, gauge bosons, Higgs over the beats (all: the whole chart in beat 1)
  beats:
    - text: "Six quarks, in three generations."
    - text: "Six leptons: the electron, the muon, the tau and three neutrinos."
      actions: [{highlight: "row:neutrinos", style: box, at: "@neutrinos"}]
    - text: "The gauge bosons carry the forces."
    - text: "And the Higgs boson, found in twenty twelve."
- id: antimatter
  type: standard_model
  params: {reveal: all}
  beats:
    - text: "Every quark and lepton has an antiparticle, with the opposite charge."
      actions: [{action: antiparticles, at: "@antiparticle"}]   # or a target: "group:leptons", "particle:e"
    - text: "The photon couples to electric charge, so never to a neutrino."
      actions: [{couplings: "particle:photon"}]                 # also particle:g, Z, W, H; undone at the next beat
```

Targets of the chart: `particle:<name>` (`particle:u` or `particle:up`, `particle:e` /
`electron`, `particle:nu_mu`, `particle:photon`, `particle:W`, `particle:H`), `generation:1`…`3`,
`group:quarks` / `leptons` / `fermions` / `gauge_bosons` / `scalar_bosons` / `bosons`,
`row:up_type` / `down_type` / `charged_leptons` / `neutrinos`; `highlight` and `dim` work on all.
`layout: tall` (default in 9:16) puts the bosons in two rows under the fermions.

Feynman diagrams in proper notation, checked vertex by vertex against the Standard Model (a
forbidden vertex is refused with the reason: no H γ γ vertex — draw the loop; no photon on a
neutrino; a W only within a doublet):

```yaml
# particle physics
- id: annihilation
  type: feynman            # fermion arrows (antifermions against time), wavy γ/W/Z, curly g, dashed H
  params:
    title: "Bhabha scattering"
    preset: bhabha         # ee_to_mumu, compton, bhabha, moller, beta_decay, muon_decay, pion_decay, drell_yan,
                           # gg_to_h, h_to_gammagamma, h_to_zz_4l, top_decay
  beats:
    - text: "An electron and a positron annihilate into a photon."
      actions: [{vertex_rule: "vertex:v1", show: [rule, coupling, checks], at: "@photon"}]
    - text: "Or they exchange one: the t channel."
      actions: [{action: swap_channel, to: t, at: "@exchange"}]
    - text: "Follow them through."
      actions: [{travel: diagram}]
- id: muon_decay
  type: feynman
  params:
    diagrams:              # your own: "id: particle from -> to"; ends are vertex ids, in, out
      - lines: ["mu: mu- in -> v1", "nu_mu: nu_mu v1 -> out", "W: W- v1 -> v2", "e: e- v2 -> out", "nu_e: anti-nu_e v2 -> out"]
  beats:
    - text: "The muon becomes its neutrino and a W minus, which decays."
      actions: [{highlight: "line:W", at: "@W"}]
```

Write each line's particle as it travels forward in time (an incoming positron: `e+ in -> v1`;
its arrow is drawn back against time). Targets: `line:<id>`, `vertex:<id>`, `hadron:<particle>`
(with `groups` or `spectators: true` on `beta_decay`), `process`, `diagram`, `time_axis`. `time:
up` draws time bottom → top; the layout (s-, t-, u-channel, decays, loops) is automatic.

Relativistic kinematics as momentum arrows: a two-body decay in the parent's rest frame (p* from
the masses, PDG 2024) and in the lab, or particles with their invariant mass √((ΣE)² − |Σp|²):

```yaml
# particle physics
- id: pion_decay
  type: kinematics         # arrows to scale in the rest frame and the lab; p*, β, γ, opening angle, invariant mass, βγcτ
  params:
    title: "Pion decay in two frames"
    decay: "pi+ -> mu+ nu_mu"
    momentum: "200 MeV/c"  # the pion in the lab (or energy, kinetic, beta, gamma); frames: both | rest | lab
  beats:
    - text: "At rest, the muon and the neutrino fly apart back to back."
    - text: "In the lab the pion moves, and both are thrown forward."
    - text: "The invariant mass is the same in both frames: the pion's mass."
      actions: [{highlight: values, at: "@invariant"}]
- id: speed_up
  type: kinematics
  params: {decay: "pi0 -> gamma gamma", frames: rest, momentum: "1 GeV/c", angle: 90}
  beats:
    - text: "Speed the pion up, and its two photons close up."
      actions: [{action: boost, to: lab, at: "@Speed"}]   # or to: 0.99, to: rest
- id: muon_range
  type: calculation        # PDG values by name: mass, lifetime, width
  params:
    symbols:
      - {name: m_mu, mass: mu-}
      - {name: tau, lifetime: mu-}
      - {name: E, value: "4.00 GeV", meaning: "muon energy"}
      - {name: c, constant: c}
    calculations:
      - {name: gamma, expr: "E/(m_mu*c^2)", meaning: "Lorentz factor"}
      - {name: L, expr: "sqrt(gamma^2 - 1)*c*tau", unit: km, meaning: "mean decay length"}
  beats:
    - text: "A four GeV muon has a gamma of about thirty-eight."
    - text: "On average it flies about twenty-five kilometres: time dilation brings it to the ground."
```

Particles given in the lab: `particles: [{particle: gamma, momentum: "80 GeV/c", angle: 25}, …]`
(their rest frame is found; Σp = 0 there). Targets: `panel:rest`, `panel:lab`, `arrow:<n>` /
`arrow:<particle>`, `sum`, `values`, `process`. A `calculation` takes the numbers with `from_scene:
pion_decay.p_star` (`M`, `E1`, `E2`, `beta`, `gamma`, `opening_angle`, `decay_length`; particles:
`m_inv`). The model `particle_physics.kinematics` also gives thresholds (`threshold("p p -> p p p
anti-p")`: 5.63 GeV kinetic on a fixed target, 0.94 GeV per beam at a collider) and the plot model
`two_body_opening` (the opening angle against momentum; its axes are named and in GeV/c and
degrees by themselves). A decay below threshold, a forbidden decay, β ≥ 1 or an energy below the
mass is refused with the numbers. `readout: key` (default) writes each frame's main numbers large;
`readout: all` every number.

Event displays in a schematic cylindrical detector (tracker, solenoid, ECAL, HCAL, iron yoke, muon
chambers; generic sizes, labelled "schematic detector · simulated event"), seen across the beam
(x–y) or along it (r–z), with a simulated event built layer by layer over the beats:

```yaml
# particle physics
- id: z_event
  type: detector           # tracks bend with R = pT / (0.3 B); e, γ shower in the ECAL, hadrons in the HCAL, μ reach the muon chambers
  params:
    title: "A Z boson decays to two muons"
    event: {preset: z_to_mumu, seed: 3, soft: 0}   # z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu, dijet; same seed, same event; soft: low-pT pions (default 4)
  beats:
    - text: "Tracks curve; calorimeters take the energy; two muons reach the muon chambers."
      actions: [{highlight: "particle:mu+", at: "@muons"}]
    - text: "Seen from the side."
      actions: [{action: switch_view, to: rz}]
- id: signatures
  type: detector
  params:
    event:
      particles:           # pt in GeV/c, eta, phi in degrees; particle: jet for a jet
        - {particle: e-, pt: 30, eta: 0.3, phi: 20}
        - {particle: gamma, pt: 40, phi: 100, leaves: [ecal]}   # leaves is checked: a photon leaves no track
        - {particle: nu_e, pt: 35, phi: 150}                      # invisible: missing transverse momentum
    reveal: all
  beats:
    - text: "The neutrino escapes: the momentum is out of balance."
      actions: [{highlight: missing_pt, at: "@neutrino"}]
```

`field` (tesla, default 2) sets the bending: positive particles turn clockwise in the x–y view (the
field out of the screen); low-p_T tracks curl up in the tracker. Missing p_T is minus the visible
particles' sum. Towers grow ∝ log(1 + E) (`energy_scale: linear` for ∝ E; `tower_max` fills the
depth). Targets: `particle:<n>` / `particle:mu+` (track, towers, name, readout row), `jet:<n>`,
`tracks`, `ecal`, `hcal`, `muon_hits`, `missing_pt`, `readout`, `legend`, `layers`,
`layer:<tracker|solenoid|ecal|hcal|iron|muon>`, `soft`. A τ, π⁰, Z or quark listed as a particle is
refused with the reason (it decays first; make a jet).

Resonances emerging from data: a simulated invariant-mass spectrum fills event by event (bars, a
ticker "events: 12 400" and the local significance growing with the data), then a peak fit with
the mass ± its uncertainty and the width, the likelihood-ratio significance and what 5σ means;
decay chains with lifetimes; branching ratios from the model:

```yaml
# particle physics
- id: diphoton
  type: mass_spectrum      # simulated, labelled so; a plot underneath: grow, fit, annotate, reveal and zoom work
  params:
    channel: h_to_gammagamma   # z_to_mumu, h_to_gammagamma, h_to_4l, custom (mass, window…)
    seed: 1
  beats:
    - text: "Events arrive, and a small bump grows near one hundred and twenty-five GeV."
      actions: [{grow: axes}]
    - text: "A fit on a smooth background finds the mass, and how unlikely chance is."
      actions: [{fit: "fit:fit", at: "@fit"}]   # the significance note follows (or annotate: "annotation:significance" on a word)
- id: four_leptons
  type: mass_spectrum
  params: {channel: h_to_4l, style: points, subtract: true}   # points with √N bars; a data − background panel
  beats:
    - text: "Four leptons: only a handful of events, then a few more."
      actions: [{grow: axes, to: 20}, {grow: axes, at: "@few"}]   # to: a number of events
    - text: "A fit, then subtract the background, and look closer."
      actions: [{fit: "fit:fit"}, {reveal: "residuals:fit", at: "@subtract"}, {zoom: axes, x: [115, 135], at: "@closer"}]
- id: pion_chain
  type: decay_chain        # each decay checked; τ and cτ (resonances: Γ) from PDG 2024; branching fractions when listed
  params:
    title: "From a pion to an electron"
    decays: ["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"]
  beats:
    - text: "A positive pion."
    - text: "It lives twenty-six nanoseconds, then becomes a muon and a neutrino."
    - text: "The muon lives two point two microseconds."
- id: higgs_decays
  type: branching          # bars from the model (H: LHC Higgs XS WG prediction; Z, W, π, K, μ: PDG 2024)
  params: {particle: H}
  beats:
    - text: "Most Higgs bosons decay to a bottom quark pair; two photons, a quarter of a percent."
      actions: [{highlight: "bar:γγ", at: "@photons"}]
- id: z_decays
  type: branching_pie      # a pie (small modes grouped below other_below %, 1.5 by default)
  params: {particle: Z}
  beats:
    - text: "Seventy percent of Z bosons decay to hadrons, twenty percent to neutrinos."
```

What the numbers mean, and what is simulated: every event of a `mass_spectrum` is simulated from
its `seed` (the same seed, the same events), labelled "simulated data" in the legend and caption:
the resonance is a Breit–Wigner of the PDG 2024 mass and width smeared by a Gaussian `resolution`,
over a smoothly falling background (`background: exponential | power | flat`, `slope`, `index`);
`events` and `signal` (expected signal events) set the counts; `window` and `bin_width` the axis.
The fit (`peak: gaussian | breit_wigner`, `background_degree`) is Phase W's binned Poisson
likelihood; for the Z the fitted Γ includes the resolution (the caption gives both). The readout's
**local significance** is the expected (Asimov) Z = √(2((s+b) ln(1+s/b) − s)) of the signal and
background expected in the peak window after that many events (`significance: counting` for the
observed excess, `none`); the note after the fit gives the likelihood ratio (background only
against signal + background) and its one-sided p-value: **5σ ↔ p ≈ 2.9 × 10⁻⁷, the chance that
background alone fluctuates up this much — not the chance that the result is wrong**. The note
is short by default (`6.7σ local`, `p = 7.6 × 10⁻¹²`, `(background only)`: let the narration say
what it means); `explain: long` writes the meaning out on screen. Both are
local: the look-elsewhere effect is not included. Targets are the plot's: `axes`, `series:simulated
data`, `fit:fit`, `residuals:fit` (with `subtract`), `annotation:significance`, `legend`, `title`.
A `plot` also takes the models `mass_spectrum` (numbers: mass, width, resolution, lo, hi, events,
signal, slope), `decay_times` (`tau`, `events`: exponential decay times to fit with `model: custom,
expr: "N*exp(-x/tau)"`) and `z_lineshape` (σ(e⁺e⁻ → hadrons) for 2, 3 and 4 neutrino families;
schematic, no radiative corrections — say so in the caption). `decay_chain` targets: `decay<N>`,
`particle:<n>` / `particle:mu+`, `lifetime:mu+`, `chain`; `branching` and `branching_pie` take
`modes` (the largest N) and the targets of `bar_chart` / `pie` (`bar:γγ`, `slice:hadrons`).

`vidgen lint` checks what the narration and the screens say about particles against the same
model: masses (`particle_mass`: "the W weighs 91 GeV" — that is the Z's), charges and spins
(`particle_charge`, `particle_spin`, errors: "the down quark has charge +2/3"), lifetimes, half-lives
and widths (`particle_lifetime`), branching ratios (`branching_ratio`: "most Higgs bosons decay to
two photons"), "allowed" / "forbidden by …" / "conserves …" against the checker
(`conservation_claim`), the boson named for an interaction (`feynman_boson`: "a photon changes the
quark's flavour", "gluons couple to electrons", a boson the diagram does not have), a `kinematics`
scene's numbers, decay lengths βγcτ and thresholds (`kinematics_number`), detector signatures
(`detector_signature`: "photons leave tracks"), the meaning of a p-value and the σ a spectrum
reaches (`significance_claim`: "five sigma means 99.99994 % sure the Higgs exists" is wrong — say
"background alone would fluctuate this high once in 3.5 million tries"), simulated data called
real (`simulated_label`), masses written both as GeV and GeV/c² (`particle_units`, info). Negations
and contrasts are left alone ("photons do not leave tracks" is fine).

```yaml
# data
- id: devices
  type: pie
  params: {title: "Visits by device", donut: true, labels: ["Mobile", "Desktop", "Tablet"], values: [5200, 3100, 640], highlight: Mobile}
  beats:
    - text: "Most visits come from phones."
    - text: "More than half of them."
- id: busy
  type: heatmap
  params:
    title: "Renders per hour"
    rows: ["Mon", "Tue"]
    columns: ["9h", "12h", "18h"]
    values: [[3, 8, 9], [5, 10, 11]]
    highlight: "col:18h"
  beats:
    - text: "Each cell counts the renders in one hour."
    - text: "Evenings are the busiest."
- id: offices
  type: map
  params:
    title: "Our offices"
    view: europe
    steps:
      - [Germany, France]
      - pins: [{lon: -0.13, lat: 51.51, label: London}]
  beats:
    - text: "We started in Germany and France."
    - text: "Then we opened in London."
```

```yaml
# pictures and media
- id: harbour
  type: image
  params: {generate: "a quiet harbour at dawn, fishing boats, mist over the water", fit: cover, ken_burns: true}
  beats: [{text: "It started in a small harbour town."}]
- id: lab
  type: image
  params: {path: assets/lab.png, caption: "The training cluster"}
  beats: [{text: "Everything ran on this machine."}]
- id: app
  type: screenshot
  params:
    title: "Find any task"
    path: assets/app.png
    frame: browser
    steps:
      - {box: [0.22, 0.04, 0.27, 0.06], label: "Search"}
      - {arrow: [0.86, 0.07], label: "New task"}
  beats:
    - text: "The search box at the top finds any task in seconds."
    - text: "And one click on this button adds a new one."
- id: demo
  type: video_clip
  params: {path: assets/demo.mp4, trim: [1, 5], fit_duration: true, mute: true, caption: "The app, live"}
  beats: [{text: "Here it is running live."}]
- id: saying
  type: quote
  params: {text: "Simplicity is prerequisite for reliability.", author: "Edsger W. Dijkstra"}
  beats: [{text: "As Dijkstra put it, simple systems are the reliable ones."}]
```

```yaml
# maths and code
- id: square
  type: equation
  params: {latex: ["(a + b)^2", "a^2 + 2ab + b^2"], terms: ["2ab"]}
  beats:
    - text: "Take a plus b, squared."
    - text: "The middle term is where the cross products hide."
      actions: [{zoom: "term:2ab"}]
- id: solve
  type: equation_derivation
  params:
    title: "Solving for x"
    colors: {x: accent}
    steps: ['2x + 3 = 11', {tex: '2x = 8', note: "Subtract 3"}, {tex: 'x = 4', note: "Divide by 2"}]
  beats:
    - text: "Two x plus three is eleven."
    - text: "Take three from both sides."
    - text: "So x is four."
- id: slope
  type: function_plot    # f(x) written as maths (parsed safely: x^2, 2x + 1, sin(x), exp(-x^2/2)); one item per beat
  params:
    title: "The slope of x²"
    functions: ["f(x) = x^2"]
    x_range: [-3, 3]
    dots: [{x: -2, tangent: true, label: "slope {slope}"}]   # a live label: {x}, {y}, {slope}
    areas: [{between: [0, 1], label: "A = {area}"}]           # the area under f, its size filled in
  beats:
    - text: "Here is the parabola, f of x equals x squared."
    - text: "A dot on the curve, with its tangent."
    - text: "As the dot moves right, the slope grows steeper."
      actions: [{trace: dot1, to: 2, at: "@moves"}]   # the dot travels along the curve on the word
    - text: "The area under the curve grows as its end moves out."
      actions: [{trace: area1, to: 2.5, at: "@grows"}]
- id: triangle
  type: function_plot    # geometry on the same plane: points, vectors and marks, no functions needed
  params:
    axes: false          # pure geometry; keep the axes for vectors on a grid
    points: [{at: [0, 0], name: A}, {at: [4, 0], name: B}, {at: [4, 3], name: C}]
    marks:
      - {segment: [A, B, C], closed: true}
      - {brace: [A, B], label: "4"}               # outside the triangle by itself
      - {angle: [B, A, C], label: "{angle}°"}     # the angle at A; a square at 90°
      - {dimension: [A, C], label: "c = {length}"}
  beats:
    - text: "A right triangle with sides four and three."
    - text: "Move C up and the angle at A opens."
      actions: [{trace: "point:C", to: [4, 4], at: "@Move"}]   # marks and labels follow
- id: vectors
  type: function_plot
  params:
    x_range: [-1, 6]
    y_range: [-1, 5]
    vectors: [{to: [3, 1], name: a}, {to: [1, 3], name: b}, {sum: [a, b], label: "a + b"}]   # b slides to a's tip
  beats:
    - text: "Vector a, and vector b."
    - text: "Put b at the tip of a: the sum runs from start to end."
    - text: "Double a and the sum follows."
      actions: [{trace: "vector:a", scale: 2, at: "@Double"}]
- id: hops
  type: number_line
  params:
    range: [-2, 8]
    points: [{at: 2, name: a}]
    intervals: ["[4, inf)"]                        # interval notation: [ ] closed, ( ) open, inf
    jumps: [[2, 5], [5, 7]]                        # arcs labelled +3, +2
  beats:
    - text: "Start at two."
    - text: "Every number from four on."
    - text: "Jump three to five."
    - text: "And two more to seven."
- id: snippet
  type: code
  params: {title: "Load and train", code: "data = load()\nmodel = fit(data)\nsave(model)", highlight: ["1", "2-3"]}
  beats:
    - text: "We load the data."
    - text: "Then fit and save the model."
- id: faster
  type: code_morph       # version i at beat i; the diff is computed for you: shared tokens glide, new lines grow in
  params:
    title: "Cache it"
    versions:
      - "def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)"
      - {code: "@cache\ndef fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)", highlight: changed}
  beats:
    - text: "This version recomputes the same values again and again."
    - text: "One decorator, a cache, and each value is computed once."
      actions: [{reveal: version2, at: "@cache"}]   # morph on the word (1.5 s)
- id: shell
  type: terminal         # step i at beat i: the command is typed, then its output appears (you write it: nothing runs)
  params:
    title: "Run the tests"
    code: {code: "def mean(xs):\n    return sum(xs) / len(xs)", highlight: 2}   # optional: the code beside it
    steps:
      - {command: "pytest -q", output: "..F\n1 failed, 2 passed in 0.03s"}
      - {command: "python -c 'print(mean([]))'", output: "ZeroDivisionError: division by zero", output_color: secondary}
  beats:
    - text: "We run the tests, and one of them fails."
      actions: [{reveal: output1, at: "@fails"}]   # the output on the word
    - text: "An empty list divides by zero."
- id: walk
  type: code_walkthrough
  params:
    title: "The training loop"
    code: "def train(data):\n    model = init()\n    for batch in data:\n        loss = step(model, batch)\n    return model"
    steps: [{lines: "1-2", note: "Set up the model"}, {lines: "3-4", note: "One step per batch"}]
  beats:
    - text: "The function starts by creating the model."
    - text: "Then it takes one step per batch."
```

```yaml
# cartoons
characters:              # top level of video.yaml: declared once, used by any stage
  - {name: pip, look: {body: bean, hair: short}}
  - {name: kit, look: {body: tall, hair: spiky, accessories: [scarf]}}
scenes:
  - id: park
    type: stage
    params:
      background: [primary, highlight]   # a gradient sky; or image: / generate: for a picture
      characters:
        - {name: pip, at: left, pose: waving, expression: happy}
        - {name: kit, at: right, depth: 0.3}   # further back: smaller, drawn behind
    beats: [{text: "Pip waves at an old friend across the park."}]
```

```yaml
# cartoons
- id: later
  type: card                  # style: burst (rays turning), frame or plain
  params: {text: "Later that day…", subtitle: "at the old mill", sting: comic}
  duration: 2.5               # silent; or beats: to narrate it
```

A whole cartoon (characters, staging, shots, timing, title cards and irises): `vidgen guide cartoons`.

**When to write a custom scene type** (a Python file in the project's `extensions/`, see
`docs/EXTENDING.md`): when the idea is a specific drawing no built-in can express (a mechanism,
a geometric construction, a bespoke animation) and you would otherwise bend a built-in into
it. Prefer built-ins whenever one fits: they are tested at 16:9 and 9:16, fit text to readable
sizes, expose action targets and pass lint. Custom scenes should use regions
(`self.region("body")`, `place(...)`) rather than fixed coordinates, and get checked with the
same storyboard and lint loop.

<!-- topic: design (also: visual, theme, themes, colors, colours, icons, accessibility) -->
## Visual design

**Theme presets** (`theme: {preset: NAME}`; `vidgen list-themes --swatches themes.png` shows
them side by side). Pick one per video and keep it:

| preset | looks | use it for |
|---|---|---|
| `dark_tech` | dark slate, cyan / amber accents (the default) | technical explainers, software, AI |
| `light_academic` | off-white, ink colours, serif headings | papers, lectures, research results |
| `high_contrast` | black and white, large type | accessibility first, low-vision audiences |
| `warm_editorial` | cream paper, serif headings and quotes | essays, history, storytelling |
| `brand_neutral` | light grey, one blue | company videos: set `colors: {primary: "#..."}` to your brand |
| `soft_pastel` | dusky plum, pastels | friendly tutorials, education for beginners |
| `bold_neon` | violet-black, neon, large type | short social clips, launches |

```yaml
theme:
  preset: brand_neutral
  colors: {primary: "#0B5FFF"}
```

**Colour roles.** Use the theme's tokens, not hex values, in params: `text` / `dim` for text,
`primary` for the main element, `highlight` for "look here" (one thing per frame), `accent`
for warnings and bad news, `tertiary` for good news, `surface` for panels, `palette` for
series. Meaning never rides on colour alone: `comparison` adds check / cross markers, charts
label their series, `stat` chips carry an arrow. Every preset passes WCAG AA and has a
colour-blind-safe palette (except `dark_tech`'s blue and purple for deuteranopes: pick another
preset if that matters).

**One colour per concept.** Give the few concepts an explainer keeps coming back to a colour of
their own, once, at the top of `video.yaml`; schu-video-generator then draws those words in that colour
wherever they are written (titles, bullets, cards, chart and diagram labels, captions, a
callout naming one, a `line_chart` series named after one) and their TeX parts in equations:

```yaml
terms:
  loss: tertiary
  gradient: "#E07A5F"
  learning rate: {color: secondary, tex: '\eta'}   # also η in equation scenes
```

Whole words, any case, plurals too. At most about 5 colours, each readable on the background
(lint `concept_colors` checks both). Do not colour the same word otherwise in a scene (a
title's `highlight_color`, a series' `color`, an `equation_derivation`'s `colors`, a plotted
function's or area's `color`, a callout's `color`): lint warns. `terms: false` on a scene turns it off there (a recap in plain colours).
Prefer colours the scenes do not use for something else: `accent` is also the default of
tangent lines, number-line jumps, angle marks and the terminal's prompt, and `highlight` is the
spoken word in karaoke captions and the code highlight; `examples/gradient-descent` uses
`primary`, `secondary` and `tertiary`.

**Icons.** 200 line icons in one style. Find them by concept:
`vidgen list-icons --search growth`, `vidgen list-icons --category data`, and look at them in
your theme with `vidgen list-icons --search money --sheet icons.png --theme`. Use icons for
categories and steps (`icon_grid`, `bullets` items, `process` stages, `timeline` events), not
as decoration; one icon per idea, the same icon for the same idea across scenes. A project can
add its own SVGs in `assets/icons/`.

**Layout and consistency.** Built-in scenes lay themselves out in named regions (a `header`
band for the title, the `body` below it), adapt to 16:9 and 9:16, and never shrink text below
the readable size (they warn instead: then split the content). So consistency comes from
choices: one preset, the same heading length and style everywhere, the same icon set, the same
transition. Overlays with `reserve: true` shrink every scene's safe area: reserve only what must
stay clear all the time.

**Accessibility.** Lint checks contrast (WCAG AA, 4.5:1) and minimum text size for the output;
keep both clean. Burn in `captions` for social video; the SRT (`<output>.srt`) is always
written for players. `high_contrast` or `scale: large` for audiences that need it.

<!-- topic: actions (also: targets, callouts, highlight, zoom) -->
## Pointing at things: beat actions and callouts

A beat can act on named **targets** of its scene while it is spoken: `vidgen list-scenes`
prints each type's targets (`bar:<label>`, `item<N>`, `node:<id>`, `point:<series>@<x>`...), and
`vidgen validate` lists the valid names when one is wrong.

| action | use it to | restraint |
|---|---|---|
| `highlight` | make the thing the voice names stand out (`style: color`, `box`, `underline`, `fill`, `flash`) | one target per beat |
| `dim` | push the rest back (`opacity`) | pair with a highlight, undo with `until` |
| `callout` | label or point at something (`kind: box`, `circle`, `arrow`, `label`, `spotlight`, `magnifier`) | one per beat; gone at the next beat |
| `zoom` | look closer at a detail, then come back (`hold: true`: stay close, e.g. a Short's last shot; `cut: true`: jump there, at 0 of a scene's first beat the scene opens on it); on a `plot`, `x: [from, to]` / `y: [...]` zoom its axes to that region of the data instead of moving the camera | at most one per scene |
| `pan` | on a `stage`: move the camera to a character or a mark (`to: right`); on an iso place to a spot (`to: well`) across and up the picture, moving in from the wide view | on a stage wider than the frame (`width: 2`), or on an iso place to look at a thing |
| `follow` | on a `stage`: keep the camera on a character as it moves (on a platform `level` gently, up and down too; `level: {follow: hero}` follows from the start; on an iso place it zooms in first, to a plain stage's size) | one at a time |
| `reveal` | bring a later element in early; on an iso place an object with `shown: false` appears (a bridge over the pond) | rarely: the default order is usually right |
| `hide` | on an iso place: an object fades away (`- hide: rock`; a bridge gone cannot be crossed) | cause and effect in the story |
| `transform` | morph one target into another (`into`) | for equations and before / after |
| `fit` | on a `plot`: draw a fit on a word (`- fit: "fit:decay"`: its band, curve, parameters and residual panel) | when the narration says the data are fitted |
| `annotate` | on a `plot`: show an annotation on a word (`- annotate: annotation2`: its mark and text) | when the narration names the marked point, line or range |
| `grow` | on a `plot`: grow live series (a model's) from a word until the next action or the beat's end (`- grow: "series:x"`, `to: 4` in the model's time; `axes`: all of them) | when the narration follows the simulation as it runs |
| `substitute` | on a `calculation`: show a calculation's values put into its formula on a word (`- substitute: calc1`; the formula first if it is not on screen); `reveal: formula2` shows a formula, `highlight: "symbol:G"` marks a symbol | when the narration says the numbers |
| `compute` | on a `calculation`: show its result on a word (`- compute: calc1`; the steps before it come first) | when the narration says the result |
| `convert` | on a `calculation`: show the result in its `convert` units on a word (`- convert: calc1`) | when the narration says the result in other units |
| `sweep` | on an `orbit`: start a body's equal-time sectors on a word (`- sweep: "sectors:Comet"`); `reveal: "foci:Comet"` (`axes:`, `periapsis:`, `velocity:`) shows an overlay, `highlight: "periapsis:Comet"` marks it | when the narration starts counting equal times |
| `launch` | on an `orbit` with a `cannonball`: fire a shot on a word (`- launch: "shot:3"`; without launches every shot flies from the start) | when the narration says the speed of the shot |
| `burn` | on an `orbit` with burns or a `transfer`: the clock runs so the burn happens on a word (`- burn: "burn:2"`); one speed-up before, another after, both in the panel | when the narration says "burn" |
| `flyby` | on an `orbit` with a `flyby`: the closest approach on a word (`- action: flyby`) | when the narration says the probe swings past |
| `pause` | on an `orbit`: hold the clock still from a word (`- action: pause`) until a `coast` (or the end of the beat); the panel says "clock paused" | while the narration explains a moment (the launch window) |
| `coast` | on an `orbit`: run the clock again after a `pause` (`- action: coast`) | when the narration moves on |
| `corotate` | on an `orbit` with a three-body `system`: turn the view into the frame rotating with the pair (`- action: corotate`, `run_time: 2`): both primaries and the Lagrange points stand still, trails redraw in that frame | "now let the frame turn with Jupiter" (a Trojan's tadpole appears) |
| `inertial` | on an `orbit` with a three-body `system`: turn the view back to the fixed stars (`- action: inertial`) | "seen from the stars again" |
| `antiparticles` | on a `standard_model` chart: turn quark and lepton cells into their antiparticles (`- action: antiparticles` for all, or `antiparticles: "group:leptons"`): the charge reverses, the symbol takes its bar or sign (ū, ν̄ₑ, e⁺), the name changes; `until:` turns them back | "every particle has an antiparticle with the opposite charge" |
| `couplings` | on a `standard_model` chart: outline the particles a boson couples to (`couplings: "particle:photon"`; g, Z, W, H too), ring the bosons it meets, dim the rest and say why; undone at the next beat | "the photon couples to electric charge" |
| `travel` | on a `feynman` diagram: a particle dot runs along lines in time order (`travel: "line:mu"`, or `travel: diagram` for a dot on every line at once) | "follow the electron through" |
| `vertex_rule` | on a `feynman` diagram: ring a vertex and state its rule (`vertex_rule: "vertex:v1"`; `show: [rule, coupling, checks]`): the vertex type, the coupling (α ≈ 1/137, α_s ≈ 0.118, g ≈ 0.65, y ∝ mass), the charge and lepton numbers in and out; undone at the next beat | "at this vertex the photon couples to the charge" |
| `swap_channel` | on a `feynman` scene with several diagrams: morph into another (`- action: swap_channel`, `to: t`): s ↔ t channel, photon ↔ Z, top ↔ W loop | "or they exchange a photon instead" |
| `boost` | on a `kinematics` scene: speed the last frame up continuously (`- action: boost`, `to: lab`, `rest` or a β such as 0.99): a decay's products swing forward and close up, Σp grows, β and γ count up, the invariant mass stays | "speed the pion up" |
| `switch_view` | on a `detector` scene: turn the transverse view (x–y, across the beam) into the longitudinal one (r–z, along it) or back (`- action: switch_view`, `to: rz` / `xy`); rings, tracks, towers and hits morph | "seen from the side" |
| `trace` | on a `function_plot`: move a dot along its curve (`- trace: dot1`, `to: 2`; its value label and tangent follow), an area's right end, a point (`to: [x, y]`) or a vector's tip (`to: [x, y]`, or `scale: 2`), everything drawn from them following; on a `number_line`: a point (`to: 4`); on a `line_chart`: a cursor dot along a series (`- trace: series1`, `to: 4`, the line's value over it) | one movement per beat, timed to the word that says it |
| `sfx` | a sound at that moment (`vidgen guide audio`) | the important moments only |
| `particles` | rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines) over any scene (`- particles: confetti`; `density`, `area`, `glow: true` to make them shine, `keep: true` for the rest of the scene) | a mood or a celebration, not on dense text |
| `wind` | on a `stage`: fade the wind to `0.8` or `calm`, `breeze`, `windy`, `gale` (`- wind: gale`; `run_time` = the fade, 2 s) | a storm coming, a gust in the story |
| `blow_away` | on a `stage`: the wind blows a light prop away, tumbling, out of a hand too (`- blow_away: napkin`; `to:` a mark to land there, else off the stage) | a gust in the story; napkin, umbrella, ball, cup, basket, box, letter, balloons only |
| `light` | on a `stage`: fade the light to `morning`, `sunset`, `night`, `indoor` or `day` (`- light: night`; `run_time` = the fade, 2 s; `move_sun: true` moves a `sun` / `moon` prop across the sky, shadows turning) | when time passes in the story |
| `lightning` | on a `stage`: the set flashes and a bolt strikes (`- lightning: right`; `distance: 2`: its thunder ~6 s later; in a room the windows flash) | a storm, a scare; rain with `lightning: true` strikes on its own |
| `rainbow` | on a `stage` outdoors: a rainbow fades into the sky and stays (`- rainbow: centre`; `hide: true` fades it out) | after the rain |
| `switch_on` | on a `stage`: a `tv`, `lamp`, `kettle` goes on, a `fireplace` burns, a `phone` rings (`- switch_on: tv`; a click with foley); on an iso place a `lamp` lights, a `house`'s windows glow (they stay bright at `light: sunset` / `night`) | when someone in the story switches it on or lights the fire; when a call comes |
| `switch_off` | on a `stage`: a `tv`, `lamp`, `kettle` or `fireplace` goes off, a `phone` stops ringing (`- switch_off: lamp`) | when someone in the story switches it off or answers |
| `knock` | on a `stage`: someone knocks three times on a door (`- knock: front`; a room's door or a `door` prop; nobody needs to stand there) | a visitor in the story; the door then `open`s with a creak |
| `alarm` | on a `stage`: an alarm goes off (`- alarm: start`) or stops (`- alarm: stop`): the set darkens under a red light pulsing like a beacon, a siren plays; portals, holograms and screens keep shining (`color`, `period`) | a security system, a red alert |
| `shutters` | on an indoor iso place: steel shutters slam down over its windows (`- shutters: close`, a slam) or roll up (`- shutters: open`) | with an alarm; a lockdown |
| `materialise` | on a `stage`: a character appears as a hologram does, a flickering wireframe, then solid (`- materialise: guide`; it waits unseen until then) | a projection switched on, another self appearing; best on `hologram: true` or `echo: true` |
| `dematerialise` | on a `stage`: a character vanishes the same way backwards (`- dematerialise: guide`) | a projection switched off |
| `hold_hands` | on a `stage`: a character takes another's hand (`- {hold_hands: ana, with: ben}`); they hold hands wherever they stand or walk | walk both in the same beat to places side by side to go hand in hand |
| `let_go_hands` | on a `stage`: a character lets go of the hand it holds (`- let_go_hands: ana`; the other too) | before an arm gestures again |
| `kiss` | on a `stage`: two characters kiss (`- {kiss: ana, with: ben}`, 3 s): they turn, lean in until their faces touch, eyes closed, a small burst of hearts and sparkles, then lean back (`hearts`, `color`) | stand them a step apart; a `two_shot` |
| `let_go` | on a `stage`: a character lets go of the balloons it holds; they float away (`- let_go: pip`) | gone for the scene |
| `pour` | on a `stage`: a character pours with the watering can it holds (`- pour: kit`, 2 s) | watering a plant |
| `drop_fruit` | on a `stage`: a fruit falls from a tree with `fruit: true`, bounces, thuds (`- drop_fruit: tree`; `to: pip`: on pip's head, stars) | a comic moment; the character stands under the tree |
| `birds` | on a `stage` outdoors: a flock crosses the sky (`- birds: 5`; `direction: left`) | a calm outdoor moment, time passing |
| `say` | on a `stage`: pick who speaks the beat (`- say: kit`; `bubble: true` or a short text for a speech bubble) | without it the characters whose `voice` is the beat's voice speak; bubbles for short lines |
| `look_at` | on a `stage`: a character looks at another, a prop, a mark or `camera` (`to:`) | when attention moves |
| `turn` | on a `stage`: a character faces the other way (`to: left` / `right`), or the viewer (`to: front`: its front view) | an SVG character has no front view |
| `emote` | on a `stage`: change a character's expression (`to: happy`) | on the word that causes it (`at`) |
| `pose` | on a `stage`: change a character's pose (`to: pointing`) | one pose change per beat |
| `react` | on a `stage`: a listener's `expression` / `pose` for this beat only | the listener, not the speaker |
| `effect` | on a `stage`: a symbol over a character's head for this beat (`to: idea`, `question`, `exclaim`, `sweat`, `anger`, `sleep`, `hearts`, `stars`, `sparkle`, `tear`) | a feeling that should read at a glance; one per line |
| `walk_to` | on a `stage`: a character walks to a mark or x (`to:`; `speed`), also towards or away from the camera (`depth: 0.4`, or `to: {mark: right, depth: 0.4}`); on an iso place to a spot or `{column, row}` round what is in the way, or `after: kit` (follows it) | with `follow` on a wide stage; the walk takes its distance's time |
| `run_to` | on a `stage`: a character runs to a mark or x (`to:`; `speed`): longer strides, leaning forward, dust and speed lines | a hurry, a chase, an escape |
| `enter` | on a `stage`: a character walks in from an edge (`side:`) or through a room's door (`door: door`) to its mark (or `to:`); on an iso place over the place's edge, or out of a spot (`door: front_door`) | it waits off stage until then |
| `exit` | on a `stage`: a character walks out by an edge (`to: left` / `right`) or through a room's door (`door: door`) | an `enter` brings it back |
| `gesture` | on a `stage`: `to: point`, `wave`, `shrug`, `nod`, `shake_head`; `big: true` adds a whoosh arc | on the word it goes with (`at`) |
| `jump` | on a `stage`: a character jumps (`height`); on a platform `level`, `to:` a spot, mark or tile jumps it there on a planned arc, picking up coins and stars on the way (`react: {when: land, expression: happy}`) | joy or surprise; getting onto a platform |
| `step_aside` | on a platform `level`: a blocker (`level.blockers`) moves out of the way (`- step_aside: tobble`; `to:` a place to walk to) | after the line that asks it nicely |
| `wander` | on an iso place (`iso:`): a character strolls to a few cells near it, round what is in the way (`around:` a spot, `radius`, `stops`; `seed` for another stroll) | waiting, looking about, time passing |
| `meet` | on an iso place: a character and another (`with: kit`) walk to each other and stop side by side, facing each other | before the two talk |
| `keyframes` | on a `stage`: move a character, prop or part (`kit.arm_left`) through `keys: [{t, x, y, rotate, scale, ease}]` (`t` seconds or `"40%"` of the beat) | motion no other action has; keep it short |
| `move_along` | on a `stage`: move a character, prop or part along `path: [[x, y], ...]` (smooth curve; `speed`) | flying, floating |
| `pick_up` | on a `stage`: a character reaches for a prop and holds it (`to: ball`; `hand`); it goes along with the hand | `walk_to` next to the prop first (`vidgen validate` says where) |
| `hold` | on a `stage`: a character holds a prop from now on, without picking it up (`to: cup`) | a prop it has from the start (`at: 0`) |
| `put_down` | on a `stage`: the held prop goes on the ground (`to:` a mark or x, default in front); on an iso place beside it, or `to:` a spot next to it (on the table there) | within reach |
| `give` | on a `stage`: the held prop goes to another character (`to: kit`) | the two stand next to each other |
| `throw` | on a `stage`: the held prop flies to a mark or x (`to:`; `spin`, `height`) and lands with a thud | |
| `open` | on a `stage`: an `umbrella` or `door` prop opens (`- open: umbrella`); a held umbrella goes up over its holder's head; `by: pip` reaches for it (a locked door on a `level` opens only by whoever holds its key); on an iso place a `house`'s door, a room's `door_1`, `flowers` (they bloom) | `open: true` in `props` starts it open |
| `close` | on a `stage`: an open `umbrella` or `door` closes (`- close: door`); a held umbrella comes down to the hand; on an iso place a house's or a room's door, flowers back to buds | |
| `sit_on` | on a `stage`: a character sits on a `chair`, `rock`, `box`, `sofa`, `armchair`, `bed` or `desk` (`to: chair`); its hips and knees bend | next to the prop; `stand_up` before it walks |
| `lean_on` | on a `stage`: a character leans its back on a `tree`, `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter` or `fridge` (`to: tree`) | next to the prop; `stand_up` before it walks |
| `stand_up` | on a `stage`: a character gets up from where it sits or leans | |
| `get_in` | on a `stage`: characters get in a `car`, a `bus`, a `boat` or a `hot_air_balloon` or on a `bicycle` (`to: car`); they ride with it until `get_out` | next to the vehicle; a bicycle seats 1, a car, a boat and a balloon 2, a bus 4 |
| `ride_to` | on a `stage`: a vehicle (or a rider: its vehicle) rides to a mark, an x or `{mark, depth}` with its riders, wheels turning; a boat along the water, a balloon or a `toy_rocket` flies there (`land: false`: away) | `get_in` first (a toy rocket: none) |
| `get_out` | on a `stage`: riders get out of their vehicle where it is | |
| `shot` | on a `stage`: the camera frames characters for the beat; write it as the beat's key `shot: closeup kit` (`wide`, `two_shot`, `medium`, `over_shoulder kit pip`; `closeup ana ben`: two or three faces together; `{kind: closeup, of: kit, clear: true}` hides the others for the beat); the next beat without one cuts back; on an iso place `wide` is the place's wide view and the others make its small characters large | a beat's dialogue line or reaction (on an iso place every longer spoken line: in a wide view a speaker gets a name tag, enough for a short line); not with a walk out of the framing |
| `host_point` | with a `host:`: the host's arm reaches towards a target of the scene and it looks there (`- host_point: item2`; `line: true`: a thin pointer line) | one per beat; a line only when nothing lies between the host and the target |
| `host_look` | with a `host:`: the host looks at a target of the scene (`- host_look: bar3`) | when attention moves |
| `host_react` | with a `host:`: the host's expression for this beat (`- host_react: happy`; `effect: sparkle` adds a symbol) | on a result or a surprise |
| `host_move` | with a `host:`: the host walks to the other side and the content slides over with it (`- host_move: other_side`, `left`, `right`) | one move per beat; rarely, between topics |
| `host_enter` | with a `host:`: the host walks in from an edge (`{action: host_enter}`, or `- host_enter: left`); the scene starts without it | at the start of the video |
| `host_exit` | with a `host:`: the host walks out by an edge (`- host_exit: left`); its room stays free | at the end |
| `build` | on an `iso_diagram`: blocks, a stack (layer by layer), a group or a connector come in on the word (`- build: "block:db"`; `style: grow`, `drop`, `fade`); the scene leaves them to it | one part per idea, as the voice names it |
| `raise` | on an `iso_diagram`: lift blocks, a layer (with the layers above) or a group off the floor (`by: 0.5`), a shadow under them; `lower` sets them down | to single out a part; undo with `until` |
| `lower` | on an `iso_diagram`: set raised blocks down (`by`, default to the ground) | |
| `explode` | on an `iso_diagram`: pull a stack's layers apart (`- explode: "stack:app"`, `gap: 0.6`), labels going along; `collapse` puts them back | to show what a stack is made of |
| `collapse` | on an `iso_diagram`: an exploded stack's layers back together | |
| `flow` | on an `iso_diagram`: dots (`style: packets`: small cubes) run along connectors (`- flow: "edge:*"`, `chain: true` one after another, `back`, `count`) | when the voice follows data or a request |
| `focus` | on an `iso_diagram`: the camera moves onto a block, stack or group and stays (`- focus: "group:web"`), clear of the captions; labels it would cut fade out; `focus: diagram` goes back to the whole frame; on a `pathway`: onto nodes (`focus: ras`; `focus: pathway` goes back) | at most one or two per scene |
| `relabel` | on an `iso_diagram`: a label or value changes in place (`- relabel: "block:cache"`, `text: "Cache: hit"`) | a new value, a state change |
| `zoom_to` | on a `cell`: the camera moves in µm to a level on an object and stays (`- zoom_to: mitochondria`; `level: tissue`, `cell`, `organelle`, `complex`; `width: "2 um"`; `labels: false` or a list of the parts to name); details appear as they grow, the scale bar follows; `zoom_to: cell` goes back | one level change per idea, on the word that names the target |
| `motor_walk` | on a `cell`: motors walk hand over hand along their filament with their cargo (`{motor_walk: kin, distance: 500 nm}`; kinesin to the + end, dynein to the − end; `toward` checked) | at a view of a few hundred nm to see the steps |
| `endocytosis` | on a `cell`: a clathrin-coated pit buds in and is pinched off by dynamin (`endocytosis: cell`, `site: [x, y]`); captioned steps | at a 300–500 nm view of the plasma membrane, `labels: false` on it |
| `exocytosis` | on a `cell`: a vesicle docks with SNAREs, fuses and releases its cargo (`exocytosis: <vesicle id>`, uncoated, in the cytosol) | likewise |
| `set_state` | on a `molecule`: a molecule morphs to another state (`{set_state: kv, state: open}`; `until` turns it back) | before `transport` on a channel (ions pass only an open one) |
| `transport` | on a `molecule`: a channel passes ions down their gradient (`count`), a carrier or pump runs its cycle (`cycles`: alternating access; the Na⁺/K⁺ pump's E1 → E1P → E2P → E2 with ATP → ADP + Pᵢ), each step captioned | one cycle per idea |
| `diffuse` | on a `molecule`: a solute's particles random-walk with net flux down the gradient (`diffuse: oxygen`; across a bilayer only O₂, CO₂, water) | on the word that names the process |
| `osmosis` | on a `molecule`: water moves to the side with more solute (`osmosis: membrane`), through aquaporins if any | |
| `action_potential` | on a `molecule`: voltage-gated Na⁺ and K⁺ channels open, inactivate and close with a live Vₘ readout and an inset trace (`action_potential: membrane`) | |
| `transcribe` | on a `molecule` with a `gene`: TBP on the TATA box, the general factors and RNA polymerase II assemble, a ~13 bp bubble opens, the template strand is read 3′→5′ and RNA made 5′→3′ (capped at ~25 nt); on a `cell`: mRNAs made at the gene | first step of a gene; then the others in order (validated) |
| `cap` | on a `molecule` with a `gene`: the three enzymes of the 5′ cap (m⁷GpppN) as their own step (else `transcribe` caps) | after `transcribe` |
| `splice` | on a `molecule` with a `gene`: snRNPs on GU / branch A / AG, the lariat, the exons joined, an EJC | the gene needs `introns` |
| `polyadenylate` | on a `molecule` with a `gene`: CPSF / CstF, cleavage, Xrn2 termination, the poly(A) tail | before `export` |
| `export` | on a `molecule` or `cell` with a `gene`: the mRNP through a nuclear pore, 5′ end first | only a capped, spliced, polyadenylated mRNA |
| `translate` | on a `molecule` or `cell` with a `gene`: scanning to the AUG, the 80S ribosome, tRNAs pairing with codons, the chain growing N→C with its amino acids written out, the stop codon and release (`codons: n` stops after n) | only after `export` (refused in the nucleus) |
| `target_er` | on a `molecule` with a `gene` (`signal_peptide: true`): SRP, its receptor, Sec61, the signal in the lateral gate, signal peptidase | while translating (`translate: g, codons: 3` before it) |
| `glycosylate` | on a `molecule` with a `gene` (`glycosylation: true`): OST puts Glc₃Man₉GlcNAc₂ on the sequon's Asn | in the ER, after `target_er` |
| `fold` | on a `molecule` with a `gene`: Hsp70, the chaperonin, BiP or calnexin (`chaperone`, checked against the compartment); the chain packs its hydrophobic residues inside | after the stop codon |
| `to_golgi` | on a `cell` with a `gene`: a COPII vesicle from an ER exit site to the cis-Golgi, then cis → trans | a folded protein made into the ER |
| `secrete` | on a `cell` with a `gene`: from the trans-Golgi network `to: outside` (exocytosis), `membrane` or `lysosome` | after `to_golgi` |
| `signal` | on a `pathway`: the signal runs from a node along the arcs, wave by wave: arcs light, nodes light, GDP → GTP, phosphorylated sites appear (pS133); an inhibitor of an inhibitor turns its target on (`signal: egf`; `to: creb` only the shortest path; `signal: [gcgr, gas, ac]` a path; `feedback: false`); it stops at a knocked-out, drugged or held node | about 0.75 s per step: give it a long beat, or `to:` |
| `inhibit` | on a `pathway`: an inhibitor engages (`inhibit: pten`; `on: [pip3]`): its T-bars flash, its targets are held, the nodes downstream that change get ↑ / ↓ | the node needs an inhibitory arc |
| `knockout` | on a `pathway`: a node is crossed out (`knockout: pten`) and every node downstream that changes gets ↑ / ↓, computed from the graph (`effects: false` leaves them out) | `until` brings it back |
| `drug` | on a `pathway`: a pill with the drug's name blocks a protein (`{drug: mek, name: trametinib}`; a known drug on another target is refused), with the effects downstream | not on genes, messengers or outcomes |
| `amplify` | on a `pathway`: many copies of a node stream out of the node that makes it (`{amplify: camp, factor: "×100"}`; `from`, `count`) | after the `signal` reached it |
| `advance` | on a `cell_cycle`: the cell moves round the cycle (`advance: cycle, to: s`; `into: 0.5`; `to: g0` only before the restriction point) or a division runs to a stage (`advance: cell, to: anaphase_i`; `expect: {chromosomes: 2, chromatids: 4}` is checked); on a `metabolism`: the token runs to a metabolite or enzyme (`advance: glycolysis, to: pyruvate`), electrons run along the chain pumping protons (`advance: etc, to: complex_iv`; `from: fadh2`), or the gradient drives ATP synthase (`to: atp_synthase`) | one stage or a few steps per beat: its length follows what it shows (up to ~8 s) |
| `checkpoint` | on a `cell_cycle` (`mode: cycle`): a checkpoint's regulators light in a panel — `checkpoint: g1_s` passes (cyclin D–CDK4/6 ⊣ Rb ⊣ E2F → cyclin E–CDK2), `{checkpoint: g2_m, outcome: arrest, cause: dna_damage}` holds the cell (`advance` cannot pass it until the action's `until`); `spindle` (SAC: MCC ⊣ APC/C–Cdc20) | one checkpoint per beat |
| `form_gametes` | on a `cross`: a parent's homologues part and its gametes fly out to the square's headers (`form_gametes: both`, `parent1`, `mother`…), each allele in its homologue's colour, recombinants ringed | once per parent |
| `fill` | on a `cross`: Punnett cells fill in, the row's and column's gametes moving in (`fill: square`, `row2`, `col1`, `cell2.3`, `"cells:wrinkled, green"`; `by: row` / `column` / `cell`); `fill: tree` grows a branch diagram | a row or the square per beat (~0.2 s a cell) |
| `count` | on a `cross`: the offspring counted into classes (`count: phenotypes` or `genotypes`): rows appear as their cells flash, fractions in lowest terms, percentages, the lethal class dying | one table per beat |
| `ratio` | on a `cross`: the whole-number ratio of a table (`ratio: phenotypes` → 9 : 3 : 3 : 1) | on the word that says it |
| `chi_square` | on a `cross` with `observed` counts: the goodness-of-fit table, χ², df, p, the verdict (`chi_square: test`) | give it its own beat |
| `deduce` | on a `pedigree`: the genotypes under the symbols, forced ones or the most telling with its exact probability (`deduce: genotypes`, `carriers`, `generation:II`, `person:II-3`), obligate carriers marked | on the word that says carriers |
| `analyse` | on a `pedigree`: the modes of inheritance tried one by one, each fits or is excluded with its reason, the people it names ringed (`analyse: modes`; `mode:XR` for one) | ~1 s a mode: a beat for all six, or one mode per beat |
| `risk` | on a `pedigree` with a `proposed` child: the child appears and the risk card with the factors of the product (`risk: risk`) | on the word that says the risk |
| `cross_over` | on a `linkage_map`: non-sister chromatids meet at a chiasma in an interval and swap the segments beyond it (`cross_over: "interval:v-ct"`, or `double`); the recombinant chromatids are labelled | ~2.4 s, on the word that says crossing over |
| `measure` | on a `linkage_map`: a distance on the map with the RF its map function gives (`measure: "interval:w-v"`) | ~1.6 s |
| `rearrange` | on a `karyotype`: a change of the notation (`rearrange: change:1`, or `changes`): a structural change as an edit in an ideogram, else its highlight | ~2.6 s an edit |
| `mutate` | on a `mutation`: the variant row is made from the reference and the card gives the HGVS notation (`mutate: variant`, `variant:2`, `variants`) | ~3 s, on the word that names the change |
| `scan` | on a `crispr`: the enzyme searches the PAMs, binds the protospacer and the R-loop forms (`scan: dna`) | ~3 s |
| `cleave` | on a `crispr`: the blunt double-strand break 3 bp from the PAM (`cleave: dna`) | ~1.6 s, on the word that says cut |
| `repair` | on a `crispr`: NHEJ or HDR, with the repaired allele and its HGVS change (`repair: repair`) | ~2.8 s |
| `run` | on a `dna_lab`: a step of its method (`run: trace`, `counts`, `ladder`, `sizes`, `fragments`, `chromatogram`, `reads`, `call`); the steps before it play first | ~2.2 s each |
| `simulate` | on a `population` simulation: the lines grow to a generation (`simulate: "generation:40"`, or `lines` to the end); fixation and loss marked, the dots follow | ~1–3.2 s by the generations covered |
| `resample` | on a `population`: the next generation's individuals (a simulation), or a new random sample at the Hardy–Weinberg frequencies (`resample: population`) | ~1.4 s |
| `regional` | on a `gwas`: zoom into a peak, its variants coloured by r² with the lead (`regional: "peak:FTO"`; one per scene) | ~2.6 s |

```yaml
- id: speeds
  type: bar_chart
  params: {title: "Render time", labels: ["Preview", "1080p", "4K"], values: [0.4, 2.6, 9.8], unit: " min"}
  beats:
    - text: "Render time grows with the resolution."
    - text: "Four K is the slow one."
      actions:
        - {highlight: "bar:4K", style: box, until: speeds_b3}
    - text: "Previews are how you iterate."
      actions:
        - dim: ["bar:1080p", "bar:4K"]
        - callout: "bar:Preview"
          kind: arrow
          label: "Use this while editing"
          at: "@iterate"           # on that word (or a fraction of the beat: 0.3)
```

- `at` times the action to the word it belongs to: name the word, `at: "@gradient"` (quoted;
  `"@gradient#2"` its second time in the beat, `"@gradient-0.2s"` a moment before it,
  `"@learning rate"` a phrase), or give a fraction of the beat (0–1). A word is timed by the
  beat's audio once `vidgen tts` made it, by an estimate from the text before; a word the beat
  does not say is a `vidgen validate` error that lists the words like it. Every action takes it
  (`callout`, `sfx`, the stage's moves and acting too), and so does `lower_third`'s `at`
  (`"@Ada"`). Actions never make a beat longer. Show a label when the narration names it:
  lint's `said_before_shown` warns when a node, callout or stage is named seconds before it
  appears. A whole explainer timed this way: `examples/gradient-descent`.
- The `stage` actions (`say` to `throw`) take the character as the target and the new
  state as `to:` (`- emote: kit` + `to: happy`). How to use them together for a cartoon:
  `vidgen guide cartoons`.
- `until: <later beat id>` keeps a highlight / dim / callout on screen; without it a callout
  disappears at the next beat and a zoom comes back by the beat's end.
- A callout without a target points at an `area: [x, y, w, h]` of the frame (fractions).
- Check actions mid-beat with `vidgen storyboard --scene ID --per-beat 3`.

<!-- topic: cartoons (also: cartoon, characters, character, stage, dialogue, acting) -->
## Cartoons: characters on a stage

**When to make one.** When the idea has people in it: two points of view arguing it out, a
mistake and its fix, a story with a turn, a gentle explainer for beginners or children. A short
sketch also works as the hook of an explainer, before the charts. Not for numbers, code or
formulas: those have their own scene types, and a character pointing at a chart is slower than
the chart. Keep it small: 2–3 characters, one set per scene, 30–90 s.

**Original characters only.** Build them with the generator (`look:`) or from your own SVG
(`look: {svg: ...}`, `docs/CONFIG.md` "Characters"). Never imitate a known character, mascot,
brand figure or logo: not its silhouette and colours, its name or catchphrase, an SVG traced
from it, nor "in the style of" a studio in a `generate:` prompt or `cartoon_style`. If someone
asks for one, say schu-video-generator makes original characters and offer one with the same role.
- Tell them apart at a glance: a different `body` (`round`, `tall`, `pear`, `triangle`...),
  hair (`ponytail`, `braids`, `afro`, or bald with `facial_hair: beard`), one signature item
  each (`hat`, `cap`, `bow`, `scarf`, `glasses`, `backpack`...), an `outfit` (`dress`,
  `overalls`, `coat`, `shorts`, `apron`; second colour `colors.trim`) in different theme tokens,
  maybe a `pattern` (`stripes`, `dots`) or `shoes`. A good test: would the two silhouettes,
  filled black, still differ? A child: `proportions: kid` (or `tall_kid`) and a smaller `scale`
  on the stage (about 0.7). An animal: `species: cat | dog | bird | bear | rabbit | mouse |
  fox | owl | frog | turtle | penguin | snail` (fur colour `colors.skin`: natural tones or theme
  tokens, different for each; a turtle's or a snail's shell `colors.hair`; it gets a `tail`, not a
  frog or a snail; a turtle walks slowly, a snail more slowly still, a penguin waddles, a frog jumps higher). A robot: `species: robot` with `robot:
  {head: box | round, face: eyes | screen, antenna: true | false, moves_on: legs | wheels}` (no
  hair; plating `colors.skin`; a screen face shows its mouth shapes; on wheels it rolls; a
  `[beep]` in its lines). Costume pieces for anyone: `crown`, `wizard_hat`, `party_hat` (one
  thing on top of the head, like `hat` or `cap`) and a `cape` that trails in the wind
  (`docs/CONFIG.md` "Robots and costumes"). `vidgen character-sheet` shows every pose and the front view. `vidgen cast --random 4
  [--seed S] [--species cat dog]` writes a cast chosen to differ (looks, colours, voice kinds
  and voices, original names) for `include:`; lint `look_alike` warns when two look too alike.
- Give each a want and a temper (the eager one, the doubter); their starting `pose` and
  `expression` say it before they speak. Short names, easy to say (the voice says them).
- One voice each (`voices:` + `characters[].voice`), clearly different; keep the narrator's
  voice for the few lines that set the scene.

**Staging.**
- **Marks**: two characters on `left` and `right` face each other (`facing: auto` turns them
  towards the stage's middle; on a wide stage, or with both on one side, set `facing`). A third
  goes at `centre` or further back. Keep characters at least a mark apart and the space above
  their heads free for speech bubbles.
- **Depth**: what matters stands in front (`depth: 0`); the set goes back (`depth: 0.5`–`0.8`:
  higher, smaller, behind; the `ground_color` band reaches up to the deepest of them). Nothing in
  front of a speaker's face (`hidden_speaker`). A character can walk in depth (`- {walk_to: kit,
  to: {mark: 0.6, depth: 0.7}}`: it shrinks and passes behind what it walks by) and come forward
  to speak (`depth: 0`). `facing: front` (or `- {turn: kit, to: front}`) turns a generated
  character to the viewer, for a line said to the audience; it turns back with `turn`.
- **The set**: things at the edges (a `house`, a `tree`), the middle free for the action.
  Props stay inside the frame: `far_left` / `far_right` cut a wide prop (`off_frame`). A
  drawn set is a gradient `background`, a `ground_color`, `layers` (`hills`) and props; a
  generated one (`generate:`) gets one top-level `cartoon_style` ("flat colours, thick outlines,
  soft shadows") so all stages match, and a prompt that describes a set, not a scene: things at
  the edges, an empty middle, the ground across the lower part, `negative: "people, animals,
  text"` (`docs/CONFIG.md` "Generated backgrounds").
- **Drawing style**: one top-level `drawing: {outline: thin | bold, shading: soft, texture:
  paper | storybook}` restyles every stage (a stage's own `drawing` wins key by key); the
  default draws as before; captions and overlays are never textured.
- **Room to move**: a walk takes the time its distance needs (about 4 s from `left` to `right`
  in 16:9), so give it a beat that long and end it on a free mark (`walk_overlap`). On a stage wider than
  the frame (`width: 2`), the camera goes along with `follow`.
- **Light and mood**: `light: morning | sunset | night | indoor` (or `{tint, strength}`) grades
  the whole set and the characters, never the bubbles or text; `night` adds stars on a colour
  background. Time passing is a `- light: night` action (it fades, 2 s); `fill_light: 0.4` keeps
  the characters' faces readable in a dark light (the set stays dark). Characters and props on
  the ground get soft shadows on their own (`shadows: false` for none). `wind: breeze | windy |
  gale` (or 0..1; negative blows left) sways trees and bushes, makes scarves, long hair, ears and
  hats trail and particles drift; `- wind: gale` fades it in a beat. From `windy` on it shows
  clearly; add `particles: [leaves, streaks]` so it reads at once. `- blow_away: napkin` blows a
  light prop off the stage (or `to:` a mark), out of a hand too; the wind must blow then.
- **Rain**: `particles: [rain]` (or `- particles: rain` from a beat) on a stage ends on the
  ground with small splashes; an open umbrella (held or standing) and a tree's crown keep the
  rain off whoever stands under them; `{kind: rain, puddles: true}` grows puddles. A generated
  rain sound plays under it while it lasts, ducked less than music (off with `foley: false`).
- **Snow and fog**: `{kind: snow, settle: true}` lands on the ground and on the props, where a
  white layer grows (a blanket on the ground, caps on roofs, crowns, tables; full after 24 s at
  density 1; thin under trees and open umbrellas); `settled: 30` starts it already white. `fog:
  true` (or a density 0..1) lays fog in bands between the characters and props by depth: the
  further back, the more hidden; it drifts slowly and with the wind. Both outdoors only.
- **Storms, rainbows, sunsets**: `- lightning: right` flashes the set with a bolt there and plays
  `thunder` after it (`distance: 2` km: ~6 s later, quieter; in a room the windows flash); rain
  with `lightning: true` strikes every 8 s or so on its own. `- rainbow: centre` fades a rainbow in
  behind the hills (after the rain). With a `sun` (or `moon`) prop, `{light: sunset, move_sun:
  true, run_time: 4}` sinks the sun to the right while the light fades, the shadows stretching
  away from it; `night` sets it and raises the moon.
- **Indoors**: `room: {wallpaper: stripes, windows: [0.3], doors: [{at: 0.8}]}` (or `room:
  true`) replaces the sky and ground with a wall, a floor (`flooring: boards | tiles`) and a
  skirting board; windows show the sky of the stage's `light` (`indoor`: lamplight inside, evening
  outside; `- light: night` darkens it and brings out stars), doors are `door` props whose name is
  a mark: `- {enter: kit, door: door}` brings a character in through it, `exit` with `door:`
  takes it out. No wind, rain or snow inside; a set (`sets:`) can be a room. Furniture props:
  `sofa`, `armchair`, `bed`, `bookshelf`, `counter`, `fridge`, `picture`, `rug`, `houseplant`,
  `clock`, `tv`, `desk`; `{prop: sofa, at: 0.3, against: wall}` stands it at the wall's depth
  (`picture` and `clock` hang on the wall by themselves). Characters that sit on such furniture
  stand at the wall's depth too (`depth: 0.4`, or walk there: `- {walk_to: dot, to: {mark: 0.42,
  depth: 0.4}}`; `vidgen validate` says where); a sofa or a bed seats two.
- **Props that move by themselves**: `{prop: clock, time: "21:45"}` runs (`speed: 60` = a minute
  a second); `{prop: tv, on: true}` shows a flickering picture, `{prop: lamp, on: true}` glows;
  `- switch_on: lamp` / `- switch_off: tv` switch them in a beat (with a click). A lamp at
  `light: night` makes a warm spot, it does not light the whole room. A `fireplace` (furniture,
  `against: wall`) burns with flickering flames, a warm glow and a crackle while `on`; a `kettle`
  (on a `counter` with a `lift`) steams while `on`.
- **Nature that moves**: `{prop: tree, fruit: true}` carries fruits and `- drop_fruit: tree` (`to:
  pip` for a head, stars) lets one fall; `birds: true` (or `- birds: 4`) sends a flock across the
  sky (outdoors only).
- **Small props**: `cake`, `muffin`, `book`, `phone`, `letter`, `gift`, `balloons`, `vase`,
  `watering_can`, `flower` to hold, give and set on a table (`lift: 0.17` on a `table`). A book, a letter
  and a gift `open` / `close` like an umbrella (held in front, not overhead). A `phone` that is on
  rings (`on: true` or `- switch_on: phone`; it shakes in bursts with a trill, `- switch_off:
  phone` answers it). Held balloons rise behind the head; `- let_go: pip` floats them away for
  good. `- pour: kit` tilts the watering can kit holds and water drops fall. A `scanner` that is on
  shows a live readout (`scan: {level: 0.4, to: 1.6, at: 3}`: above 1 it goes off its scale,
  flashing red; `- {hold: max, to: scanner}` to carry it); `takeout` boxes and glowing data
  `crystal`s (`on: true`) clutter a desk.
- **Ready-made sets**: `set: city_street`, `park`, `beach`, `forest` or `snowy_hills` on a stage
  scene gives a whole outdoor set without `sets:` (backdrop, props, light, ambience: a street
  sounds like a city, a park and a forest have birdsong by day). Put two characters on its
  `stand_left` and `stand_right` marks (clear of the props; other marks: `bench`, `bus_stop`,
  `fountain`, `umbrella`, `log`...); the scene's params override it like any set (`light:
  sunset`, `props: [{name: shop_2, color: tertiary}]`, `props: []`). Their props work on any
  stage: `shop`, `bench` and `log` (sit two), `bus_stop`, `fountain`, `flowers`, `fence`,
  `beach_umbrella`, `shell`, `pine`, `mushroom`, and flat `road` / `path` bands.
- **Ready-made rooms**: `set: classroom`, `kitchen`, `shop`, `living_room` or `bedroom` gives a
  furnished room (a door, windows, daylight or lamplight, a room tone) with the same `stand_left` /
  `stand_right` marks. Furniture stands at the wall (depth 0.4): to sit or lean, walk there first
  (`- walk_to: pip, to: {mark: sofa, depth: 0.4}`, then `- sit_on: pip, to: sofa`); pupils' desks
  are at depth 0.25 (marks `pupil`, `pupil_2`), the kitchen table and chairs at 0.2. `light: day`
  for a daytime room. New props: `blackboard` (hangs on the wall), `school_desk` (with its chair:
  sit at it), `shelf_with_goods` and `wardrobe` (lean on them), `till` (`lift` it onto a counter).

**Shot variety.** Change the shot every few beats, as a comic changes panels. A beat's `shot:`
key cuts the camera to a framing of the characters for that beat; the next beat without one cuts
back (`shot: {kind: closeup, of: kit, move: true}` eases instead):
- **wide** (the whole stage, no `shot` or `shot: wide`): the first beat of a scene, entrances,
  anything two characters do together;
- **`two_shot`** (two characters, whole) and **`over_shoulder kit pip`** (kit seen past pip, who
  stands cut at the edge): a dialogue, alternating the speaker's over-the-shoulder shots;
- **`medium kit`** / **`closeup kit`** (hips up / head and shoulders): the punchline or the
  reaction to it; about one close-up per scene, or close-ups stop meaning anything. A `zoom`
  (`scale: 2`) pushes in and comes back within the beat instead of cutting;
- **moving**: `pan` to a character or a mark (`- {action: pan, to: right}`) and `follow` a
  character or a flying prop across a wide stage (either ends a shot).
A shot is framed where the characters stand as the beat starts and does not follow a walk.
In a 9:16 variant the camera follows the speaker across the landscape stage on its own
(`reframe`, see the `social` topic): write the dialogue for 16:9 and check `vidgen storyboard
--variant ...`.

**Reaction shots.** The listener's face is often the joke. While one character speaks, the other
`react`s (`expression` and / or `pose`, for that beat only) and `look_at`s the speaker; `emote` and
`pose` change them for good. A `shot: closeup` of the listener while the other talks is the
reaction shot. `look_at: camera` turns a character to the viewer for an aside. Put the reaction where it
happens: `at: 0.8` lands it on the end of the line, not on its first word.

**Expressions.** `neutral`, `happy`, `sad`, `angry`, `surprised`, `worried`, `thinking`, and the
big ones: `laughing` (shoulders bouncing; it keeps laughing while it talks), `blushing`,
`tongue_out`, `crying` (streams of tears, sobbing), `dizzy` (swirling eyes, swaying) and
`frightened` (wide eyes, hair, fur or feathers standing up, shivering; a robot's antenna springs
up). They work on people, animals and robots, side and front. `[laugh]` / `[giggle]` in a line
make the speaker laugh. Save the big ones for the moments that earn them.

**Effect symbols.** `- {effect: pip, to: idea}` pops a small symbol over a head for the beat: an
`idea` bulb, a `question` or `exclaim` mark, a `sweat` drop, an `anger` mark, `sleep` Zs, `hearts`,
dizzy `stars`, a `sparkle`, a `tear`. It follows the character, sounds with foley (`sound: false`
for none) and goes at the next beat (`until:` keeps it longer). Use one per line at most, on the
moment the feeling lands (`at`); it says "she has an idea" without a word.

**Title cards and irises.** A `card` scene is the cartoon's title card: the episode's name, a
"Later that day…" between two scenes, "The End" (`style: burst`, `frame` or `plain`; `sting:
reveal`, `comic` or `sad` as the text pops in). The classic way between them is an iris: a black
circle closes on the scene before and opens on the next. `transition: {type: iris_out,
character: pip}` closes on Pip's head (a pause on the face, then black); `{type: iris_in,
character: kit}` opens on Kit in the scene it leads into; `at: [x, y]` (fractions of the frame
from the top left) for a point, `color` for another colour. The other side opens or closes on
the frame's centre. `iris_in` on the first scene opens the video.

```yaml
characters: [{name: pip, look: {body: bean}}, {name: kit, look: {body: tall}}]
scenes:
  - id: yard
    type: stage
    params: {characters: [{name: pip, at: left}]}
    beats: [{text: "And that was the last Pip saw of the kite."}]
  - id: later
    type: card
    params: {text: "Later that day…"}
    duration: 2.5
    transition: {type: iris_out, character: pip}
  - id: hill
    type: stage
    params: {characters: [{name: kit, at: right}]}
    transition: {type: iris_in, character: kit}
    beats: [{text: "Up on the hill, Kit found something."}]
```

**Automatic directing.** `auto_direct: true` (top level, a stage's param or a beat's key) adds
the routine looks and reactions for you: listeners `look_at` whoever speaks, the speaker looks at
the one it answers, and after a line with `?`, a negation or `!` the listeners `react` in the
pause (`thinking`, `worried`, `surprised`...). The speaker gestures on the line's stressed word
(mark it `*word*`: the asterisks are not spoken or shown; or write it in CAPITALS; else the
longest word counts; at most one per line), and a short punchy line
right after a long one gets a close-up on its speaker (a short push-in, or a `shot: closeup` when
the line is too short for it). A strong change of face gets its symbol (surprised an
exclamation mark, thinking a question mark, angry an anger mark, dizzy stars, frightened a sweat
drop; one per line). Nothing it adds may cause an `off_stage`
or `facing_away` lint warning (it checks the stage's layout first). Actions you write win: a
character with its own action in a beat gets nothing automatic there. So turn it on, then write only the moments that
matter (the reaction shot, the punchline's look to camera). `vidgen direct` lists what it adds,
`vidgen direct --print` writes it as YAML to paste into the beats and edit; the storyboard shows
an `auto:` line under each beat.

**From a screenplay.** When the story comes as a script, write it as a screenplay and let
`vidgen screenplay story.md --out DIR` (MCP tool `screenplay`) make the project: one `stage`
scene per `# Scene:` heading, one beat per line, a generated look and a voice for each character
not declared in the front matter, `auto_direct: true`. Then refine the YAML as usual (check the
`# TODO:` lines: directions and manners it could not map). `# Card: Later that day…` makes a
title card (silent unless lines follow), coming in with an `iris_out`; the scene after it opens
with an `iris_in`.

```markdown
---
title: The Humming Box            # optional: video.yaml keys (voice, theme, characters...)
---
# Scene: yard
set: background: day; props: box (crate) at 0.6, tree at 0.84; characters: fen at left, bram at right

On a quiet Sunday, Fen heard a sound that did not belong in the yard.

FEN (surprised): Bram, listen! That box is humming a song.

[Fen walks to the crate and points at it.]

BRAM: Boxes do not hum, Fen. Boxes do not do *anything*.
```

Indoors: `set: room: stripes, window at 0.3, door at right; props: sofa against the wall at 0.4,
picture frame on the wall, rug at 0.5`. `NAME (manner):` turns an expression or pose word (`doubtful`, `glad`, `arms crossed`) into a
`react` and a feeling word (`cross`, `whispering`, `sleepy`) into the beat's `emotion` (how the
voice says it), and a pronoun there states the voice kind (`FEN (she):`, `BRAM (he, doubtful):`,
`GUS (they):`; once per character is enough): the generated look and voice then suit it (without
one, the voice follows the look's kind); a plain paragraph is the narrator; `[...]` maps walk / run to, enter, exit, jump, look
at, point at, wave, nod, shrug and shake head, and effect symbols (`[Pip has an idea]`, `is
confused`, `falls asleep`, `cries`...) (on its own line: at the next line's start; inside a
line: at that word), except a voice sound such as `[laugh]` inside a line, which stays in the
line. Undeclared characters get looks that differ from the others (`--species cat dog` for
animals, `--seed` for other random ones). `docs/CONFIG.md` "Cartoons from a screenplay" has the
whole format.

**A series: one cast, shared sets.** Put the characters and their voices in `shared/cast.yaml`
and the places in `shared/sets.yaml` (`sets: {meadow: {background, props, marks, light...}}`);
each episode writes `include: [../shared/cast.yaml, ../shared/sets.yaml]` and a stage scene
`set: meadow` with only what differs in its `params` (`light: sunset`, its characters). The
scene's own params win; props, layers and characters add to the set's (`{name: tree, at: 0.3}`
moves the set's tree); an episode's `characters:` entry of a cast name changes that character
for the episode. `vidgen validate` names the file a problem is in; `vidgen screenplay story.md
--cast shared/cast.yaml` writes an episode that includes the cast and turns `set: meadow` lines
into the set. `examples/cartoon_series/` shows it (CONFIG "Shared casts and sets").

**Comic timing.**
- **Short lines**: one line per beat, one speaker per beat (the beat's `voice`), 6–12 words.
  Kokoro needs about 8 words to sound natural, and a two-word beat with actions trips
  `rushed_animation`. It also reads fast (3.5–4.5 words a second): `speed: 0.8`–`0.85` on each
  voice gives the lines room (`narration_speed` warns above 3.5 once the audio is real).
- **Pauses**: every beat ends with `narration.pad` seconds of silence (0.35). Raise it for a
  cartoon (`narration: {pad: 0.7}`) and put the reaction in it (`at: 0.8`): line, pause,
  reaction. Commas and "..." are pauses in the voice (not in the word-count preview).
- **Setup, pause, punchline**: the punchline is its own beat, after the reaction to the setup.
  The narrator undercutting a character ("Moss was not, in fact, an expert") is a cheap, good
  laugh.
- **One thing at a time**: a move, then a line; at most one or two actions per character per
  beat. Speech bubbles only for short lines (`bubble: "Up there!"`).
- **Motion**: anticipation, squash and stretch, overshoot and follow-through are built in;
  `cartoon_motion: calm` (top level, a stage or a character) tones them down for a quiet story.
  Motion effects come with them: dust where a `run_to` (or a fast walk) sets off and stops and
  where a jump lands, speed lines behind runs and thrown or blown props, stars on a high jump's
  landing, a whoosh arc on a `gesture` with `big: true`; `motion_effects: false` (top level or a
  stage) turns them off. For a move no action has, `keyframes` and `move_along` move a character, a prop or one part
  (`kit.arm_left`); `docs/CONFIG.md` "Keyframes and motion paths". Generated characters bend
  at the elbows and knees: `arm_left` is the upper arm, `arm_left_lower` the forearm (its angle
  is the elbow's bend), the legs are `leg_left` / `leg_right` (+ `_lower`); own poses can bend
  them too (`docs/CONFIG.md` "Bending arms and legs").
- **Props in hands**: `walk_to` next to a prop, `pick_up` it, walk with it, then `put_down`,
  `give` (to a character standing next to it) or `throw` it; `hold` puts a prop in a hand at
  the start. `vidgen validate` replays the scene and says when a prop is too far, held by
  someone else or not held (`docs/CONFIG.md` "Props in hands"). A character crouches by
  itself for a prop on the ground. For a picnic or the weather: `basket`, `napkin` and
  `umbrella` props; `- open: umbrella` raises a held umbrella overhead, `- close: umbrella`.
- **Sitting and leaning**: `sit_on: pip, to: chair` (a `chair`, `rock`, `box`, `sofa`,
  `armchair`, `bed`, `desk`, or an SVG prop with `data-seat`), `lean_on: kit, to: tree` (a `tree`,
  `door`, `sign`, `lamp`, `house`, `bookshelf`, `counter`, `fridge`, or an SVG prop with
  `data-lean`), then `stand_up` before it walks, jumps or turns again. While it sits
  or leans it can talk, gesture, emote and handle props; a look turns only its head. `vidgen
  validate` says when the prop is too far, the seat taken, or a seated character walks
  (`docs/CONFIG.md` "Sitting and leaning").
- **Vehicles**: props `bicycle`, `car`, `bus`. `get_in: [pip, kit], to: car` (each must stand
  beside it), `ride_to: car, to: right` (or `{mark, depth}`; the riders go along, a cyclist
  pedals), `get_out: [pip, kit]`; no walking while riding. They are big next to the characters
  (a bus is 3.2 characters long): give it a `scale` or the stage a smaller `size`
  (`docs/CONFIG.md` "Vehicles"). Outdoors only: a `boat` floats on the stage's `water: true` (or
  `{left, right}`) and rides along it, bobbing; a `hot_air_balloon` (2 stand in its basket; 2.1
  characters tall, so use `size: 0.3`) rises, drifts with the wind and lands at `to`; a
  `toy_rocket` (nobody rides it) launches with smoke and floats down under a parachute to `to`.
  `land: false` flies a balloon or a rocket out of the top of the frame, gone for the scene.
- **Sound**: walks, entrances, exits, jumps, a `surprised` face and most effect symbols make their own sounds
  (foley: footsteps, whoosh, boing, pop, an idea's ding; a thrown prop lands with a thud; a ride rings a bell or starts an engine and brakes, a balloon's burner roars, a toy rocket fizzes off; a door creaks as it opens or closes; water splashes; on a platform `level` a jump lands softly, each coin goes `coin` and each star `twinkle`, a key `unlock`s a locked door, a blocker shuffles aside; on an iso place footsteps by what the feet walk on: grass, a path, boards, a bridge, stone), timed to the action,
  and rain plays a rain sound bed. Each stage also plays a quiet bed of its set: birdsong
  outdoors by day (not at night, not in rain), a room tone in a room; `ambience: city` on a stage
  names the street sounds instead (or `birdsong`, `room_tone`, `hum` for a lab or a ship, a list), `ambience: false` none.
  `foley: false` (top level or a stage) turns all of them off. A beat's `sting: reveal | comic | sad` adds a short music sting
  (`reveal` as the beat starts, `comic` and `sad` in the pause after the line), ducked under the
  voice; under composed music the music's own instruments play it, in its key. One or two per
  cartoon, on the real punchline, or they stop being funny. For music that follows the story
  (a mood per scene, a pause before the punchline) see *Composed music* in `vidgen guide audio`.
- **Voice sounds**: `[gasp]`, `[hmm]`, `[laugh]`, `[sigh]`, `[giggle]`, `[groan]`, `[beep]` in a line
  (`text: "[gasp] The box is open! [laugh]"`) are made by the voice at that point (`Ha ha ha!`,
  `Hmm.`; a gasp or sigh at the line's start or end is a generated breath, a beep a generated
  robot chirp) and never shown in
  captions; the speaker's mouth follows and its face changes (laugh happy, gasp surprised, sigh
  sad) unless the beat's own `emote` / `react` sets it. A line needs words besides its sounds
  (`docs/CONFIG.md` "Voice sounds").
- **Talking at once**: `overlap: 0.4` on a beat starts it 0.4 s before the line before it ends
  (both heard, both mouths move, captions show both lines); `interrupt: true` cuts that line off
  where the beat starts (inside its last word, or `overlap` seconds before its end). Not on a
  scene's first beat, and not on a line of the same voice. Keep overlaps short: `vidgen lint`
  (`talked_over`) warns when whole words of the earlier line are lost under the new one or cut by
  an interrupt (`docs/CONFIG.md` "Overlapping lines").

**The loop for a cartoon.**
1. `vidgen character-sheet NAME` (or `--all`): every pose, expression and mouth shape on one PNG.
   Fix looks that are hard to tell apart now, before writing scenes.
2. `vidgen validate --json`: unknown marks, poses and expressions, a `say` by a character
   without a voice, and warnings for actions a character lacks the parts for (an SVG without
   arms cannot `wave`).
3. `vidgen storyboard --scene ID`: each still is a comic panel. The ½ stills are half-way
   through a walk, gesture, jump or path. Ask: is it clear who speaks? Are both faces visible,
   facing each other? Does the reaction read without the words? Is anything cut by the edge?
4. `vidgen lint --json`: the cartoon rules `off_stage`, `character_overlap`, `walk_overlap`,
   `prop_overlap`, `bubble_overlap`, `facing_away`, `hidden_speaker`, `small_speaker` (a face too small to read: a
   `shot: closeup` or `character_size: large`), `offscreen_action` (iso), `mouth_without_voice` and `look_alike` (fixes in
   `vidgen guide troubleshooting`).
5. Voices: with Kokoro (`vidgen guide audio`) `vidgen tts` is free and writes the lip sync
   tracks; then storyboard and lint again, since real lines change the timing.

```yaml
voice: {provider: kokoro, voice: bf_emma, speed: 0.8}   # the narrator, slowed down
voices:
  dot_voice: {voice: af_bella, speed: 0.85, label: Dot}
  moss_voice: {voice: am_michael, speed: 0.85, label: Moss}
narration: {pad: 0.7}                              # room for reactions after each line
characters:
  - {name: dot, voice: dot_voice, look: {body: round, hair: bun, accessories: [scarf]}}
  - {name: moss, voice: moss_voice, look: {body: tall, eyes: sleepy, accessories: [hat, glasses]}}
scenes:
  - id: yard
    type: stage
    params:
      background: ["#9CCBEA", "#E4F3FB"]
      ground_color: tertiary
      props: [{prop: house, at: 0.17, depth: 0.7}, {prop: box, name: kite, at: 0.43}]
      characters:
        - {name: dot, at: left}
        - {name: moss, at: right, pose: arms_crossed}
    beats:
      - text: "On the windiest day of the year, Dot had a plan."
      - text: "Moss, look! I built a kite that flies by itself."
        voice: dot_voice
        actions:
          - {jump: dot, at: 0.1}
          - {look_at: moss, to: kite, at: 0.5}
      - text: "Dot, that is a cardboard box with a string on it."
        voice: moss_voice
        actions:
          - {look_at: moss, to: dot}
          - {react: dot, expression: worried, at: 0.8}   # in the pause after the line
      - text: "Moss was not, in fact, an expert on boxes."
        sting: comic                                     # ba-dum-tss after the line
        actions:                                         # the narrator's aside: a close-up
          - {zoom: moss, scale: 2, at: 0.1}
          - {look_at: moss, to: camera, at: 0.4}
```

A complete two-scene cartoon (under a minute, a wide stage, `follow` on a flying prop, a close-up
punchline) is `examples/cartoon/` in the schu-video-generator repository.

**A host for an explainer.** `host: NAME` (a character of `characters:`) puts that character
beside the content of every scene: bullets, charts, code, diagrams... Each scene lays its content
out in the room left (a column beside it; in 9:16 a band below it), so nothing needs moving by
hand. Its mouth follows the narration (`speaks: narrator`, the default; `own`: only beats in its
own voice), it blinks and breathes, and a scene can change it (`host: {expression: thinking}`) or
drop it (`host: false`; a title or end card often looks better without). `stage` and `card`
scenes never show it. Keep the host small next to dense content (`size: 0.4`), and check the
storyboard: lint's `host_overlap` reports anything drawn over it.

```yaml
characters: [{name: dot, look: {body: bean, hair: bun, accessories: [glasses]}}]
host: {character: dot, side: right}        # size, place (beside / below), floor, facing, pose, expression
scenes:
  - id: steps
    type: bullets
    params: {heading: "How it works", items: ["Write the beats", "Render a preview"]}
    beats: [{text: "First, you write the narration as short beats."}]
  - id: chart
    type: bar_chart
    host: {expression: happy}
    params: {title: "Render minutes", labels: ["480p", "1080p"], values: [0.4, 2.6]}
    beats: [{text: "Previews are the fast way to iterate."}]
```

**Make the host act.** Beat actions: `host_point: item2` (its arm reaches towards a target of
the scene and it looks there; `line: true` adds a thin pointer line, best when nothing lies
between the host and the target), `host_look: bar3`, `host_react: happy` (`effect: sparkle` adds
a symbol), `host_move: other_side` (it walks across and the content slides to the other side
with it; one move per beat), `host_enter` / `host_exit` (a scene whose first passage is
`host_enter` starts without it). With `auto_direct: true` (or the host's own `auto_direct`) the
host points at each new bullet, bar, series or code highlight, looks at written highlights, and
reacts to results (a chart going up: happy; down: worried; an error in the code: surprised); it
never moves by itself, and anything you write in a beat wins. `vidgen direct` lists what it adds.
A complete example is `examples/host-explainer/`.

```yaml
auto_direct: true
characters: [{name: mo, look: {species: mouse, outfit: apron}}]
host: mo
scenes:
  - id: hello
    type: title
    params: {title: "Why Bread Rises"}
    beats: [{text: "Hi, I'm Mo!", actions: [{action: host_enter}]}]
  - id: bake
    type: process
    params: {stages: ["Mix", "Rise", "Bake"], layout: column}
    beats:
      - text: "Mix it, and let it rise."
      - text: "Then into the oven."
        actions: [{host_point: stage3, line: true, at: 0.5}]
```

<!-- topic: platform (also: level, levels, platformer, jumping, story-props) -->
## Platform stories: levels, jumps and story props

**When to make one.** A children's adventure where the hero *goes somewhere*: skips along the
grass, climbs a ladder, hops over a gap and up onto the clouds, finds a key for a locked gate,
meets someone grumpy in the way and asks nicely. It is a `stage` scene with a `level:` (a side
view drawn from a small map), so everything of `vidgen guide cartoons` still works: lip sync,
expressions, shots, the camera, sets, light, music. Keep a level to one part of the journey
(30–60 s, 8–12 beats) and use a few scenes for a 2–3 minute story.

**The map.** One line per row, top row first: `.` air, `#` ground, `=` a floating plank, `~` a
cloud (stand on it, jump up through it), `|` a ladder, `$` a coin and `*` a star (picked up when
the hero touches them, in the air too), and a **letter** for a *spot*: a place to stand, on the
first tile below the letter. Name the spots (`spots: {a: start, k: key_spot}`) and send every
move to a spot: it reads better than numbers and survives map edits. A character is two tiles
tall: leave two rows of air under a plank to walk under it.

**Moves.** `walk_to` / `run_to` go along the tiles (steps of one tile, ladders on the way,
never across a gap); `jump` with `to:` plans the arc itself (a crouch, the flight, a squash and a
little wobble on landing), at most 5 tiles across, 3 up and 8 down. `vidgen validate` replays
every move and says why one fails and what to write (`'nutmeg' cannot walk to spot 'far_side':
the way stops at map column 22: a gap at column 23; jump there instead`). A walk goes about 1.4
tiles a second (a ladder rung counts double): give each move a beat whose line lasts as long, or
`vidgen lint` warns `rushed_animation`; split a long way over two beats, or `run_to`.

**Story props.** A `door` prop is in the way until it opens; `locks: {gate: garden_key}` locks it
until the holder of the key prop stands next to it (`- open: gate, by: nutmeg`). `blockers:
[mossby]` puts a character in the way until `- step_aside: mossby` (after the line that asks it
nicely). `react: {when: pickup | land | arrive, expression, effect}` on a move puts the joy or
the surprise on the right frame. The sounds come by themselves (a boing, a soft landing, a coin's
pling, a star's twinkle, the unlock and the creak, the shuffle aside).

**Camera and size.** `level: {follow: nutmeg}` keeps the camera on the hero, gently, up and down
too. `character_size: small | medium | large` (top level or per scene) sets how big everyone is:
`medium` shows about 14 x 8 tiles in 16:9; use `large` for a 9:16 Short (a variant), whose
narrow frame shows about 6 x 10. A map must be at least as wide as the frame. For a dialogue,
cut to `shot: closeup <name>` or `two_shot`: small level characters' faces are hard to read
(`small_speaker` warns).

```yaml
characters:
  - {name: nutmeg, look: {species: mouse, proportions: kid, outfit: overalls}}
  - {name: mossby, look: {species: snail, eyes: oval}}
scenes:
  - id: garden
    type: stage
    set: park                       # its sky, hills, light and birdsong; not its props
    params:
      props:
        - {prop: door, name: gate, at: gate_spot}
        - {prop: key, name: garden_key, at: start}
      level:
        map: |
          ..............................
          ...................*..........
          ..a..gd..s..m...b....l...$$.e.
          #################....#########
        spots: {a: start, g: near_gate, d: gate_spot, s: stop, m: path, b: brink, l: over, e: end}
        locks: {gate: garden_key}
        blockers: [mossby]
        follow: nutmeg
      characters: [{name: nutmeg, at: start}, {name: mossby, at: path, facing: left, expression: angry}]
    beats:
      - text: "Nutmeg carried the golden key to the garden gate."
        actions: [{hold: nutmeg, to: garden_key, at: 0}, {walk_to: nutmeg, to: near_gate, at: 0.3}]
      - text: "Click, went the key. And creak, went the little gate."
        actions: [{open: gate, by: nutmeg, at: 0.2}]
      - text: "But Mister Mossby, the grumpiest snail in the garden, sat on the path."
        actions: [{walk_to: nutmeg, to: stop, at: 0.1}, {react: nutmeg, expression: surprised, at: 0.8}]
      - text: "Please, Mister Mossby, may I pass?"
        shot: closeup nutmeg
      - text: "Well, since you asked so nicely, he smiled, and shuffled aside."
        actions: [{emote: mossby, to: happy, at: 0.2}, {step_aside: mossby, at: 0.5}]
      - text: "Nutmeg ran to the edge, then jumped, and caught a star in the air!"
        actions:
          - {run_to: nutmeg, to: brink, at: 0.05}
          - {jump: nutmeg, to: over, at: 0.5, react: {when: land, expression: laughing, effect: sparkle}}
```

**From a screenplay**: put the level in a set of the front matter (`sets: {meadow: {level:
{map: ..., spots: ...}}}`) and start the scene's `set:` line with it (`set: meadow; characters:
nutmeg at start`); spots are marks there, and `[Nutmeg jumps onto over.]` is a jump.

A whole story: `examples/platform-story` (three levels, a key and a gate, coins and stars, a
grumpy snail, clouds up to a picnic, a 9:16 variant). Every key: `docs/CONFIG.md` "Platform levels
(`level`)" and the sections after it.

<!-- topic: iso (also: isometric, village, villages, iso-place) -->
## Isometric places: villages and rooms for a story

**When to make one.** A children's story that happens *in a place*: a village green with houses,
a well and a bridge over a stream, a garden, a room. The place is seen from above at an angle
(isometric, no perspective) and each scene starts on a wide view of it (in 16:9 every spot and
object you placed; in 9:16 the part where the characters stand), so the viewer knows where
everyone is. It is a `stage` scene with an `iso:` place, so everything of `vidgen guide cartoons`
still works: the characters are the same flat cut-outs (lip sync, expressions, gestures), shots,
the camera, sets, light, music. No jumping or gravity here (that is a platform `level`).

**The map.** One line per row, the top line furthest back: `.` grass (boards indoors), `:` a
path, `~` water, `#` a wall, `+` a door, `%` a window, `1`–`9` a raised block (steps of half a
tile; walkers go up one step at a time), `@` a tree, `&` a bush, `*` flowers, `=` a fence, `-`
outside the place, and a **letter** for a *spot*. Name the spots (`spots: {w: well, d: door}`)
and stand characters, small things and objects at them. `objects:` adds ready-made things at a
spot or `{column, row}`: `house`, `tree`, `lamp`, `well`, `bench`, `bridge` (over `~`, walked on),
`flowers`, `sign` (`size: [3, 2]`: a flower bed; a larger `bush` is a hedge); indoors (`place: indoor`, the front walls cut away like a dollhouse) `table`,
`chair`, `bed`, `sofa`, `shelf`, `plant`, `rug`. Put a place used by several scenes in `sets:`
and give each scene `set: village`.

**Telling the story clearly.**
- Each scene starts on the wide view; move the camera only when it helps: `shot: closeup
  <name>` or `two_shot` for a line, `follow: <name>` for a long walk, `zoom: [rowan, lamp]` or
  `- {action: pan, to: well}` (it moves in) to point at something, `shot: wide` to see everyone
  again.
- Give every character its own voice (`voices:` with a `label`): in a wide view the speaker gets a
  **name tag** with that label; without a voice of its own a character lip-syncs the narrator.
  A tagged speaker may say up to 12 words in a wide view; longer lines need a shot.
- Moves go round what is in the way: `walk_to` / `run_to` a spot, `meet` (two walk to each
  other), `after: hazel` (follows), `wander`, `enter` / `exit` over the edge or `door:` a spot
  (a house's door; `open` it first: a closed door does not stop anyone). Two walks at the same
  time do not avoid each other: time crossing walks apart. Give a walk a beat whose line lasts as long as the way (`rushed_animation`
  warns otherwise), and keep the camera on it (`offscreen_action` warns about a walk, a hand-over
  or a door the camera does not show).
- Cause and effect: `pick_up` / `give` / `put_down` small things (`key`, `gift`, `letter`,
  `flower`...) next to each other; `open` a house's door or flowers (they bloom), `switch_on` a
  lamp, `reveal` / `hide` an object (a bridge appears). Each has its sound by itself.
- Mood: `light: morning`, `sunset` (evening), `night` (a lit lamp and windows glow, and a lamp
  lights who stands next to it), and
  `particles: [rain]` (it darkens to an overcast tint by itself, unless the scene sets a `light`;
  drops land on roofs, crowns and the bridge, not under them; `{kind: rain, puddles: true}` grows
  puddles with ripples), `{kind: snow, settle: true}` (the ground, roofs and treetops turn white;
  `settled: 30` starts it white). A `run_to` leaves speed lines along its diagonal.
  Footsteps follow the ground (grass, path, boards, a bridge), birdsong by day, crickets at night.
- Science fiction and magic: a `portal` prop at a spot tears open with `switch_on` (a crackling,
  glowing rift; `switch_off` seals it); a character comes out of it with `- {enter: visitor,
  door: rift}` (the portal's spot) and walks to its own spot in front. A character with `hologram: true` is a glowing,
  translucent projection (an AI, a ghost) that no `light` darkens and that flickers now and then;
  give it an `effect: echo` on its voice. `- materialise: guide` makes it appear (a flickering
  wireframe, then solid; it waits unseen until then), `- dematerialise: guide` vanish.
- A lab: `objects` `console` (glowing screens; a `hologram_display` prop at its spot floats a
  panel of light over it: `pattern: fractal`, `data`, `text`, `equations` (formulas written, and
  formula butterflies fluttering up) or `timelines` (a branching tree, two figures meeting in a
  small panel at each tip; `scale: 1.5` to read them)), `server_rack` (blinking lights),
  `projector_pad` (a glowing platform a hologram stands on), `whiteboard`. A portal's `view:
  coast` (or `stars`, `meadow`) shows another place inside it. `- alarm: start` darkens the room
  under a pulsing red light with a siren (`stop` ends it), `- shutters: close` slams steel
  shutters over the windows; `ambience: hum` gives a lab its hum. Other objects: `laptop`
  (`open: false` closed), `terminal_kiosk`, `quantum_core`, `robot_arm`, `microscope`,
  `centrifuge`, `coffee_machine`, `lab_stool`, `wall_clock` (`at` a cell of a back wall,
  `time: "03:27"`), `grow_rack`, `terrarium`, `specimen_tank` (`color` its liquid; a `detail`
  colour adds a floating shape), `chemistry_bench` (2 x 1), `distillation_rig`, `lab_fridge`
  (`open`), `fume_hood`, `telescope`, `satellite_dish`, `charging_station`, `crate_stack`,
  `airlock` (2 x 1, `open`), `printer_3d`, `hazard_sign` (`kind: biohazard | radiation |
  authorised`), `fire_extinguisher`, `fireplace` (2 x 1), `kitchen_counter` (2 x 1), `stove`,
  `sink`, `bookshelf_tall`, `armchair`, `floor_lamp`, `tv`, `piano` (2 x 1), `bathtub` (2 x 1),
  `wardrobe` (2 x 1, `open`), `crib`, `cafe_table` (2 x 1, two chairs), `counter` (2 x 1),
  `cash_register`, `display_case` (2 x 1, `kind: cakes | jewels`), `market_stall` (2 x 1),
  `vending_machine`, `street_lamp`, `traffic_light`, `bus_stop` (2 x 1), `mailbox`, `fountain`
  (2 x 2), `phone_booth`, `car` (2 x 1, `color` its body), `bicycle`, `newsstand` (2 x 1),
  `campfire`, `tent` (2 x 2), `log` (2 x 1), `stump`, `mushroom_ring` (2 x 2), `pond` (2 x 2),
  `scarecrow`, `beehive`, `vegetable_patch` (2 x 1), `wheelbarrow`, `hay_bale` (2 x 1),
  `school_desk` (with its chair), `desk_with_pc` (2 x 1), `water_cooler`, `printer`, `globe`,
  `trophy_shelf` (2 x 1), `treasure_chest` (`open`: gold glows), `cauldron` (`color` its
  potion), `giant_crystal`, `throne`, `torch_sconce` (`at` a cell of a back wall), `signpost`,
  `archway` (2 x 1), `statue`; `on: true` / `switch_on` makes the laptop, kiosk, core, arm,
  centrifuge, coffee machine, rack, tank, bench, rig, fridge, hood, dish, charging station,
  airlock (its beacon), 3D printer, fireplace, stove, floor lamp, TV, vending machine, street
  lamp, traffic light (cycles), fountain, phone booth, car (headlights), campfire, pond
  (ripples), beehive (bees), desk_with_pc (its screen), water cooler (bubbles), printer
  (prints), globe (spins), cauldron (bubbles), giant crystal (glows) and torch sconce work (a
  lit fireplace, floor lamp, street lamp, phone booth, campfire, cauldron or torch lights who
  stands near; pools of light show mostly at night).
- Visitors: `iridescent: true` (skin shifting colours like oil on water, partly self-lit:
  `{glow: 0–1}`, default 0.5) and `afterimages: true` (faint copies trailing a move) on a
  character, a `scale` of 1.5–1.8 on the stage to tower over the others (check it in a
  `two_shot` with a human). Two characters `- {hold_hands: ana, with: ben}` step in close
  enough for the joined hands to show; walk both in one beat with the same `run_time` and they
  go side by side (`let_go_hands`). At night give the stage `fill_light: 0.4` so faces read.
- Framing: `iso: {wide: fill}` (or a number 1–2.5) brings a room's wide view closer;
  `shot: closeup ana ben` frames two faces together, `{kind: closeup, of: guide, clear: true}`
  hides everyone else for the beat. A memory: `flashback: true` on a stage (faded warm colours,
  a soft vignette), with `flower_arch` and `chess_table` objects, and an iris in and out.
- A city at night: `objects` `tower` (`height` 2–30 tiles, `size` its footprint; lit window
  grids, neon trims in `detail`, a blinking antenna; `screen: true` a crawling info screen,
  `garden: true` glowing algae bands) on the blocks between path streets, `light: night`, and
  `traffic: [{from: west, to: east, height: 3, count: 3, seconds: 7, color: "#FF2E8B"}]` under
  `iso:` for hover pods gliding over the streets (`at: 1.0` with `count: 1`: one pod crosses once;
  a `pan` to the end spot with the same `run_time` follows it). `wide: 1.6`–`2.5` lets the towers
  reach out of the top of the frame. Neon rain: `particles: [{kind: rain, glow: true, color:
  ["#5FFFE0", "#4FA8FF"]}]` (`glow` works on any particles).
- Other selves: a character with `echo: true` (or `{color, opacity}`) is a translucent other
  self that keeps its own costume, its outlines glowing (a timeline, a memory, a dream); stand
  it beside the one it echoes and bring it with `- materialise: ana_captain`. Accessories
  `medal` (gold, on a ribbon in `colors.accessory`) and `pendant` (a stone glowing and pulsing in
  `colors.accessory`, bright at night) dress a laureate or a keeper of a secret.
- Romance: `- {kiss: ana, with: ben, run_time: 3}` (two standing a step apart: they turn, lean in
  until their faces touch, close their eyes, a small burst of hearts and sparkles, then lean
  back); frame it with a `two_shot`. It lets go of held hands first. Stand a pair side by side on
  the picture: cells on a diagonal of the map (`{column: 5, row: 6}` and `{column: 6, row: 5}`)
  are at the same height on screen. Actions of a beat at different `at` play one after another,
  so two couples kissing at once share one `at`. Long hair that reads in a close-up: `hair: wavy`.
- A strange door: `iso: {doors: slide}` (steel doors sliding open with a hiss on `- open:
  door_1`) and `haze: [{at: door_in}]` (shimmering air with sparkles over a spot). A room at
  night: dark `colors: {wall, floor}`, `light: night`, `fill_light: 0.45` and `wall_lights:
  ["#5FE8FF", "#FF2E8B"]` (neon strips along its walls).
- Inside someone's head: a scene's `overlays: {implant: {type: hud, at: office_b2, duration: 6,
  alert: "INCOMING ALERT", lines: ["SIGNAL: SECTOR 7"], heart: {bpm: 70, to: 128, at: 1.5,
  skips: 3}, scan: {level: 0.4, to: 1.6, at: 3}}}` draws a HUD over the frame (brackets, a
  blinking alert, readouts, a heart monitor, a scanner meter spiking off its scale).

```yaml
characters:
  - {name: hazel, voice: hazel_voice, look: {species: rabbit, proportions: kid, outfit: dress}}
  - {name: juno, voice: juno_voice, look: {species: bird, proportions: kid}}
voice: {provider: kokoro, voice: bf_emma}          # the narrator
voices:
  hazel_voice: {voice: af_bella, label: Hazel, color: primary}
  juno_voice: {voice: af_heart, label: Juno, color: accent}
scenes:
  - id: green
    type: stage
    params:
      background: ["#9CCBEA", "#E4F3FB"]
      light: sunset
      iso:
        map: |
          -.@......~~...
          ..h......~~...
          ...a..l..~~.y.
          .::::::::~~:..
          ....f....~~...
        spots: {h: home, a: door, l: lamp, f: garden, y: far_bank}
        objects:
          - {object: house, at: home}
          - {object: lamp, at: lamp}
          - {object: bridge, at: {column: 10, row: 4}, facing: right, size: [2, 1]}
          - {object: flowers, name: flower_bed, at: garden, open: false}
      props: [{prop: key, at: door}]
      characters: [{name: hazel, at: door}, {name: juno, at: far_bank}]
    beats:
      - text: "In the evening, Hazel picked up the lamp key and ran to the lamp."
        actions:
          - {pick_up: hazel, to: key, at: 0.2}
          - {run_to: hazel, to: lamp, at: 0.45}
      - text: "Click! The lamp lit up, and Juno could see the bridge."
        actions: [{switch_on: lamp, at: "@Click"}, {walk_to: juno, to: lamp, at: 0.3}]
      - text: "Thank you, Hazel!"
        voice: juno_voice
        shot: two_shot juno hazel
```

`vidgen validate` replays every move and hand-over and names what is in the way (without the bridge:
`'juno' cannot walk from row 3, column 13 to 'lamp': the way stops at row 4, column 12: water (a
bridge crosses it) at row 4, column 11`). A whole story: `examples/iso-story` (a village by a stream and a room,
a key, a lamp lit in the rain, flowers that bloom, a 9:16 variant). Every key: `docs/CONFIG.md`
"Isometric places (`iso`)".

<!-- topic: biology (also: cell-biology, lecture, research) -->
## Cell biology: lectures and research explainers

Five scene types draw cell biology at university level, stylised but checked (`vidgen guide
scenes` has a snippet of each): `cell` (a cell in µm, zooming tissue → cell → organelle →
complex; with a `gene`, its products' route), `molecule` (molecules in nm, processes as actions;
with a `gene`, each step of expression up close), `pathway` (signalling in compartment bands),
`cell_cycle` (the cycle, mitosis, meiosis) and `metabolism` (glycolysis, the citric acid cycle,
the respiratory chain, the light reactions). The craft in full: `docs/COOKBOOK-CELL-BIOLOGY.md`
in the schu-video-generator repository; a whole example: `examples/gene-to-secreted-protein`.

**Choosing.** Where and how big → `cell`; how one molecule works → `molecule`; how a gene
becomes a protein, step by step → `molecule` with a `gene`, then the same route at the scale of
the cell → `cell` with the `gene`; who activates whom → `pathway`; the cycle and divisions →
`cell_cycle`; energy → `metabolism`. Move between levels on purpose and say so ("Up close",
"At the scale of the cell").

**Accuracy rules.**
- Pick an example that is true at every step you show (a glycoprotein secreted constitutively
  for ER glycosylation and secretion without a trigger; insulin is neither glycosylated nor
  constitutive). Say what is a model: a generated gene is "a short model gene"; a drawing larger
  than real gets `not_to_scale: true`.
- Directions: template read 3′→5′, RNA made 5′→3′, chains N→C, kinesin to +, dynein to −,
  protons out of the matrix, 3 Na⁺ out and 2 K⁺ in per ATP. Places: translation starts in the
  cytosol, N-glycans are added in the ER and remodelled in the Golgi, glycolysis in the cytosol.
- On-screen step captions are claims too: choose the context (`exocytosis` `snares: constitutive`
  in a liver cell, `neuronal` at a synapse; the default names generic v-/t-SNAREs), or
  `notes: false`. Step captions are full in 16:9 and their first clause in 9:16 (`notes:
  auto`; `full`, `short`). Gene symbols the video declares (a gene's `name`, a pathway's gene
  nodes) are italic in the captions overlay, protein names roman.
- An arc you cannot vouch for as direct is `indirect: true`.
- `vidgen validate` refuses the impossible; `vidgen lint`'s `science_*` rules read the narration.

**Naming.** Genes italic, proteins roman, by `species` (human *TP53* / p53, mouse *Trp53* /
TRP53); `<i>…</i>` for a gene in a markup label; `Ca2+`, `Pi`, `F_o` are typeset. Let the voice
say symbols through `pronunciation:` (`SERPINA1: serpin A one`, `STAT3: stat three`, `COPII: cop
two`) and check with `vidgen readback`. `terms:` for three or four concepts.

**References.** `references:` on the scene with an identifier copied from the source (DOI, PMID,
ISBN), `cite:` on the beat; never invent one, leave it out instead. With karaoke captions use
`citations: {show: marker}`.

**Pacing dense content.** One process per beat with 20–35 words for a long step (a gene step lasts
3–15 s and a short beat squeezes it); actions on the word (`at: "@scans"`); Kokoro
`speed: 0.85`; label only what is said (`labels: [granum, stroma]`, or `labels: false` where
processes move things); a long pathway in two scenes; a recap (`process`) at the end.

```yaml
- id: er
  type: molecule
  params:
    title: "Into the endoplasmic reticulum"
    gene: {id: gene, signal_peptide: true, glycosylation: true, start: mrna}
  references:
    - {id: blobel, label: "Blobel & Dobberstein, J. Cell Biol. 1975", doi: "10.1083/jcb.67.3.835"}
  beats:
    - text: "In the cytosol a ribosome scans to the start codon and begins the chain at its N terminus."
      actions: [{translate: gene, codons: 3, at: "@scans"}]
    - text: "Its first residues are a signal peptide. SRP binds it and docks the ribosome on the Sec61 translocon."
      cite: [blobel]
      actions: [{target_er: gene, at: "@SRP"}]
```

<!-- topic: genetics (also: heredity, inheritance, medical-genetics, punnett, hgvs) -->
## Genetics: crosses, families, variants and populations

Nine scene types draw genetics at university level, and **compute** what they show — ratios,
probabilities, gametes, map distances, protein changes, frequencies — so the picture cannot
disagree with the science (`vidgen guide scenes` has a snippet of each; every param:
`docs/CONFIG.md`). The craft in full: `docs/COOKBOOK-GENETICS.md` in the schu-video-generator
repository; a whole example: `examples/cystic-fibrosis` (one inherited disease from a pedigree to
a carrier test, 16:9 and 9:16).

**Choosing.** A question decides the type:
- What do the offspring of this cross look like? → `cross` (Punnett square or branch diagram,
  ratios, a chi-square of observed counts).
- How is it inherited in this family, who carries it, what is the risk? → `pedigree` (NSGC
  symbols, the modes tried one by one, carrier probabilities, the risk for a proposed child).
- How far apart are two genes? → `linkage_map` (crossing over, a test cross worked into cM).
- Which chromosome, which band, what is wrong with the set? → `karyotype` (ISCN; a karyogram or
  ideograms with `bands: {7q31.2: CFTR}`); non-disjunction → `cell_cycle` with `nondisjunction`.
- What does this variant do to the protein? → `mutation` (a real coding sequence, HGVS c. / p.).
- How do we edit it? → `crispr`. How do we detect it? → `dna_lab` (`pcr`, `gel`, `sanger`, `ngs`:
  a substitution or a short deletion, heterozygous or homozygous).
- How common is it, how does it change? → `population` (Hardy–Weinberg from counts or an
  incidence; drift, selection, migration, bottleneck, founder). Which loci go with a trait? →
  `gwas` (synthetic data is always labelled "simulated data").
A story across levels (family → gene → variant → test → population) uses one scene per level and
says when it moves ("Back in the family", "At the level of the sequence").

**Notation** (schu-video-generator checks it): pedigrees in NSGC symbols with generations in Roman numerals and
people numbered left to right (`II-3`); karyotypes in ISCN (`47,XY,+21`, `46,XX,t(9;22)(q34;q11.2)`;
sex chromosomes first, changes in order); variants in HGVS on the coding DNA (`c.1521_1523del`,
`p.(Phe508del)` — HGVS counts the initiator Met, so HbS is `p.(Glu7Val)`; say "legacy Glu6Val" or
"traditionally called ΔF508" when you use an old name); gene symbols in HGNC form, italic (*CFTR*),
proteins roman (CFTR); alleles in textbook form (`A` / `a`, `I^A`, `X^H X^h`, phased `AB/ab`).
Let the voice say them through `pronunciation:` (`"c.1521_1523del": c dot fifteen twenty-one to
fifteen twenty-three del`, `CFTR: C F T R`) and check with `vidgen readback`.

**Exactness.**
- Say what the scene computes: fractions as the scene writes them (2/3, 1/150) or "about" for a
  rounded population number ("about one in twenty-five" for 49/1250). The `genetics_*` lint rules
  read the narration and the on-screen text against each scene: `genetics_ratio`,
  `genetics_pedigree` (a chart that does not fit its stated `mode` is an error), `genetics_linkage`,
  `genetics_hwe`, `genetics_crispr`, `genetics_karyotype`, `genetics_hgvs`.
- State the assumptions where they matter: random mating for q² = incidence, a rare allele for
  people marrying in (`carrier_frequency: 1/25` when the population's number is the point), full
  penetrance unless `penetrance:` says otherwise.
- Real numbers need real sources: an incidence or carrier frequency "in people of European
  ancestry, approximately …", a reference with an identifier copied from the source (`references:`,
  `cite:`), never invented. Synthetic data (NGS reads, GWAS peaks) is a model: do not present it as
  a patient's or a study's result.
- The karyotype's band pattern is schematic: name the band ("band q31.2"), do not read positions
  off it.

**Tone.** Medical genetics is about families: say "affected", "has the condition", "a carrier"
(not "suffers from", "defective gene", "normal child"); give risks as chances with what they mean
("one in a hundred and fifty, under one percent") and end with what the family can do (testing,
counselling), not with a verdict.

**Pacing.** One step of reasoning per beat (the chart, the modes, the carriers, the risk), 15–35
words; actions on the word (`{analyse: modes, at: "@test"}`, `{mutate: variant, at:
"@deleted"}`); Kokoro `speed: 0.85` for dense notation; one number per sentence; a recap
(`process`) at the end. Long tables and cards exceed `max_words`: let the narration carry them
and reveal them step by step.

```yaml
- id: variant
  type: mutation
  params:
    gene: CFTR                         # a real coding window (NM_000492.4)
    variant: {c: "c.1521_1523del", p: "p.(Phe508del)"}   # p. is checked against the genetic code
  beats:
    - text: "Three bases, C T T, are deleted: c.1521_1523del."
      actions: [{mutate: variant, at: "@deleted"}]
    - text: "The frame is kept, and one phenylalanine is missing: p.(Phe508del), traditionally called ΔF508."
```

<!-- topic: science (also: plots, plot, calculations, calculation, units, fits, physics, data) -->
## Science: plots and worked calculations

Two scene types carry the numbers of a science video, and both **compute** what they show: `plot`
(data and models on scientific axes: error bars, fits with their uncertainties, residuals,
histograms, simulations drawn as they run) and `calculation` (a formula, the values put in with
their units, the result with its significant figures). Every param: `docs/CONFIG.md`; the craft in
full: `docs/COOKBOOK-SCIENCE-CHARTS.md` in the schu-video-generator repository; a whole example:
`examples/radioactive-decay` (simulated nuclei, measured counts with a fit, the half-life worked
out, carbon-14 dating; 16:9 and 9:16).

**Plot or chart.** A comparison of a few categories or a trend for a general audience →
`bar_chart`, `line_chart`, `pie`, `scatter`, `histogram` (big labels, values on the bars).
Measurements and models → `plot`: a log or symlog axis, units in the axis titles, error bars,
a fit, a residual panel, panels sharing a time axis, an orbit at an equal aspect, a model that
grows while you narrate. A function of x for a maths lesson → `function_plot`. Worked numbers →
`calculation`, not text on a card.

**Honest axes.** Units on every physical axis (`unit:` or `time (s)` in the CSV header); a log
axis when the data span decades (decay, counts, frequencies), never to hide a zero; `min` / `max`
only to show context, not to exaggerate a change (a bar-like quantity starts at zero); say
"simulated" or "illustrative" in a `caption` when the data are not a measurement.

**Error bars and fits.** Every error bar says what it is: `error: sd | sem | ci95 | range |
poisson` (`y_err: sqrt` for counts: ± √N); say the same word in the narration. A fit shows its
parameters ± standard errors, R² and χ²/ν (about 1: the errors match the scatter); `band:
confidence` shows where the curve lies, `prediction` where a new point would; `residuals:
normalized` shows (y − fit)/σ under the plot, ticked at ±2; `residuals: background` (a peak fit
with a `background`) the data minus the fitted background with the peak drawn over it (reveal
`residuals:<fit name>` on its own word); `parameters: [mu, sigma]` lists only those in the box. Counts (`y_err: sqrt`, histograms)
are fitted by Poisson maximum likelihood, so the fit is not pulled low. Prefer a model whose parameter is the quantity you
talk about (`model: custom`, `expr: "A*exp(-lambda*x)"` gives λ itself). Say fitted values as the
box writes them, with "give or take" for the error.

**Live models.** `models:` with `kind: ode` (equations as expressions; `method: leapfrog` for
orbits and oscillators, so the energy stays put), `recurrence`, `random_walk`, `poisson` (seeded:
the same numbers every render); a CSV series with `live: true` grows point by point too. Growth
fills its beat; `grow` and `zoom` (`x: [from, to]`) time it to words.

**Units and significant figures.** Write values as you would on paper — `"0.274 min^-1"`, `532
nm`, `"5730 yr"`, `constant: G` — and give each a `meaning` and a `source`. A number with a unit
or a decimal point is measured (its figures count: `1500 m` has 2, `"1.50"` has 3); fractions and
whole numbers without a unit are exact (`2/3 × 1/25 × 1/4 = 1/150`). The result keeps the figures
the inputs allow; `sig:` asks for fewer, never more (`calc_sigfigs`). `convert: km/s` adds the
result in another unit; a later calculation (or another scene, `from_scene`) uses earlier results.
For an uncertainty, compute it as a calculation of its own (σ_t = t·σ_λ/λ). A change of
temperature is written in K (`"10 K"`): two readings in °C are not added, and a difference is
shown in K, not °C.

**Pacing calculations.** One calculation per beat, or one line per action (`substitute`,
`compute` on the word: `at: "@gives"`); say the formula in words, then the result once, with its
unit ("two point five three minutes"). Long formulas break into a chain of short calculations.
Plots: one idea per beat (the data, the error bars, the fit, the residuals), 10–25 words; add an
action every few seconds (`reveal: "errors:<series>"`, `fit`, `annotate`, `zoom`, `highlight` with
`style: flash`) so the picture keeps moving; `label_size: caption` gives a crowded 16:9 figure
room.

**Lint.** `calc_numbers`, `calc_units`, `calc_sigfigs` read numbers in the narration and on screen
against each `calculation`; `plot_units`, `plot_log`, `plot_errors`, `plot_series`,
`plot_truncated`, `plot_conserved`, `plot_fit_claims` check each `plot`. Run `vidgen lint` in 16:9
and 9:16.

```yaml
- id: half
  type: calculation
  params:
    title: "The half-life from the fit"
    symbols:
      - {name: lambda, value: "0.274 min^-1", meaning: decay constant, source: fit}
      - {name: s_lambda, value: "0.0044 min^-1", meaning: its standard error, source: fit, tex: "\\sigma_{\\lambda}"}
    calculations:
      - {name: t_half, expr: "ln(2)/lambda", unit: min, meaning: half-life}
      - {name: s_t, expr: "t_half*s_lambda/lambda", unit: min, meaning: uncertainty of the half-life}
  beats:
    - text: "The half-life is the natural log of two over lambda: two point five three minutes."
    - text: "Its relative uncertainty is the same as lambda's: about zero point zero four minutes."
```

<!-- topic: orbits (also: orbit, orbital, orbital-mechanics, kepler, hohmann, planets, space, spaceflight) -->
## Orbits: orbital mechanics videos

One scene type, `orbit`, draws bodies on their orbits and **computes** everything it shows from
two-body Kepler orbits (or n-body integration): positions in correct timing, speeds, Δv, transfer
times, phase angles, Lagrange points, the planets on a date. Worked numbers go in a `calculation`
(`from_scene: <orbit scene>.dv1`); Kepler's third law is a `plot` (`kepler_planets`). Every param:
`docs/CONFIG.md`; the craft in full: `docs/COOKBOOK-ORBITS.md` in the schu-video-generator
repository; a whole example: `examples/mars-transfer` ("How to get to Mars": why not straight,
the Hohmann transfer, the transfer time worked out, the departure burn from low Earth orbit, the
Earth and Mars on a real date; 16:9 and 9:16).

**Choosing a view.** The planets for a year or a comet's ellipse → bodies with `span` / `orbits`;
Kepler's laws → `geometry`, `sectors`, `velocity`; why orbits are falling → `cannonball`; a
manoeuvre → `burns` or `transfer` (hohmann, bielliptic, phasing); a gravity assist → `flyby` (the
planet's frame plus the Sun-frame vector diagram); Lagrange points and Trojans → `system` with
`view: rotating` (or `corotate` on a word); resonances → `resonance`; tides → `tides` (a
schematic); the sky on a day → `date` with `event`; sizes → `sizes`. One idea per scene: the
orbit, then the manoeuvre, then the number in a `calculation`.

**Scale honesty.** Distances are drawn to scale; bodies too small to see are enlarged and the
panel says "sizes not to scale" — say the same ("the distances are to scale, the sizes are
not"). For the whole Solar System use `inset: true` (the inner planets to scale in a box) or
`radial: log` (distances compressed, labelled so; overlays that measure lengths are refused
there). `sizes` shows radii to one scale (distances are not). Tides are a schematic.

**Panels.** The side panel is compact (time, speed-up and the few values the scene is about, at a
readable size); `panel: [time, total_dv, phase]` names the rows, `panel: full` shows every row
including the diagnostics (ΔE/E, ΔL/L, the Jacobi drift), `energy: true` adds ΔE/E. The time
readout is always true: the clock runs at one speed-up, `burn` / `flyby` / `pause` / `coast`
change it on words and the panel shows each stretch's own speed-up.

**Presets and units.** Body presets: `sun`, `mercury` … `neptune`, `pluto`, `moon`, `io` …
`callisto`; orbit presets add `iss`, `geo`, `halley` (illustrative). The planets use JPL's Table 1
(J2000 elements, rates per century). Values carry units as text (`"1.5 AU"`, `"7.8 km/s"`, `"92
min"`), angles are degrees; elements next to a preset override it.

**Manoeuvres.** Burns are impulsive (`prograde`, `retrograde`, `radial`, `normal`… with a speed),
at a time or the next `periapsis` / `apoapsis`. A `transfer` needs circular, coplanar orbits:
write `e: 0, i: 0, raan: 0, argp: 0` on the presets and say "circular, coplanar orbits (an
approximation)" in a caption. Δv around the Sun is not the burn from low Earth orbit: that one is
√(v∞² + v_esc²) − v_circ (the Oberth effect; work it out in a `calculation`). A periapsis inside
a body or its atmosphere is refused.

**Three bodies.** `system: earth_moon | sun_earth | sun_jupiter` (the circular restricted
problem) or `figure_eight`; `lagrange`, `zero_velocity`, bodies `near: L4` with `shift`; RK45 by
default (leapfrog's fixed step can blow up at a close pass). Say "in the rotating frame" when the
view turns.

**Dates.** `date: 2026-10-28` (1800–2050, refused outside) places the planets from JPL's
approximate elements; `event: {kind: opposition, of: Mars}` finds the next one (within hours of
published dates). A launch window from a date is approximate (the elements and the circular
transfer are approximations): say "around early December 2026", not a day.

**Pacing.** A planet needs a few seconds to show its motion: 2–4 beats per orbit scene, an action
every few seconds (`burn` on "burn", `highlight: phase` on the angle, `sweep`, `launch`,
`reveal: "foci:Comet"`); say a number once, as the panel writes it, with "about" when rounded.

**Lint.** `orbit_period`, `orbit_speed`, `orbit_dv`, `orbit_transfer`, `orbit_distance`,
`orbit_date`, `orbit_scale`, `orbit_conserved`, `orbit_crash` check the narration and the screens
against the scene's model; `calc_numbers`, `calc_units`, `calc_sigfigs` check the calculations.
Run `vidgen lint` in 16:9 and 9:16.

```yaml
- id: hohmann
  type: orbit
  params:
    title: "The Hohmann transfer"
    bodies:
      - {preset: earth, e: 0, i: 0, raan: 0, argp: 0, trail: false}
      - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 95, trail: false}
      - {name: Ship, alongside: Earth, trail: 0.15}
    transfer: {ship: Ship, to: Mars}
    caption: "Circular, coplanar orbits (an approximation)"
  beats:
    - text: "We leave when Mars leads the Earth by forty-four degrees: the launch window."
      actions: [{highlight: phase, at: "@forty-four"}]
    - text: "A prograde burn of two point nine four kilometres per second starts the transfer."
      actions: [{burn: "burn:1", at: "@burn"}]
```

<!-- topic: particle-physics (also: particle, particle_physics, hep, higgs, standard-model, collider, feynman-diagrams) -->
## Particle physics: particles, collisions and discoveries

Eight scene types share one model, `vidgen.api.particle_physics` (PDG 2024 masses, widths and
lifetimes; the conservation checker; the Standard Model's vertices), and **compute** what they
show: `standard_model` (the chart), `feynman` (diagrams, every vertex checked), `kinematics`
(momentum arrows in two frames), `detector` (a schematic event display), `mass_spectrum`
(simulated data with a resonance, a fit and its significance), `decay_chain`, `branching` and
`branching_pie`; worked numbers go in a `calculation` (`mass: pi+`, `lifetime: mu-`, `width: Z`,
`from_scene`), curves in a `plot`. Every param: `docs/CONFIG.md`; the craft in full:
`docs/COOKBOOK-PARTICLES.md` in the schu-video-generator repository; a whole example:
`examples/higgs-discovery` ("How the Higgs boson was found": the chart, gluon fusion through a top
loop, the decay modes, a diphoton event, the invariant mass worked out, a simulated spectrum with
its bump and fit, what five sigma means; 16:9 and 9:16).

**Planning.** A discovery reads as a chain of questions, one picture each: what is it
(`standard_model` with `highlight` or `couplings`), how is it made (`feynman` with `vertex_rule`
and `travel`), what does it become (`branching`, `decay_chain`), what does the detector see
(`detector`), how is it measured (`calculation`, `kinematics`), how do we know it is real
(`mass_spectrum`, then what the significance means). 15–35 s per scene, 3–4 minutes in all.

**Choosing the scene.** Forces and processes → `feynman` (12 presets or your own lines; a
forbidden vertex is refused with the reason); allowed or forbidden decays → `vertex_rule` with
`show: [checks]` or the checker's reason in words; frames, p*, opening angles, βγcτ →
`kinematics`; signatures → `detector` (`switch_view` for r–z); a resonance in data →
`mass_spectrum`; lifetimes → `decay_chain`; how often each decay happens → `branching` bars (a pie
hides H → γγ's 0.23 %).

**Units.** Particle physicists write masses, momenta and energies in GeV with c = 1; the scenes
write the full units (GeV/c², GeV/c) so the dimensions show. Either is right: pick one per
sentence; in a `calculation` in natural units say "c = 1" in a symbol's meaning. Compute m² first
(`unit: GeV^2`) and then `sqrt(m2)`, or the square root's argument is written in SI. τ = ħ/Γ: the
Higgs boson's 4.1 MeV width is τ = 1.6 × 10⁻²² s.

**Honesty.** Simulated data are always called simulated (the scenes label them; say it too);
the detector is schematic (generic sizes, no experiment's geometry or logo); name the sources —
PDG 2024 for masses, lifetimes and measured branching ratios, the LHC Higgs Cross Section Working
Group's Yellow Report 4 for the Higgs boson's predicted branching ratios and width ("a theory
prediction"). A spectrum's significance is **local** (the look-elsewhere effect is not included);
the readout's `expected` is the Asimov median, the note after the fit the observed likelihood
ratio. A p-value is the chance that background alone fluctuates this high, not the chance of
being wrong: 5σ ↔ p ≈ 2.9 × 10⁻⁷, about once in 3.5 million. Quote real history only when
certain, and never real event counts or significances on simulated pictures.

**Pacing.** One idea per beat, 10–25 words, an action every few seconds (`highlight` on the
particle named, `couplings` on "field", `vertex_rule`, `travel`, `swap_channel`, `grow` / `fit` /
`annotate` on the spectrum). Let a spectrum fill over two beats (`grow: axes, to: 12000`, then the
rest) before the fit. A full chart is about 65 words: `max_words` warns, which is expected. In 9:16
the detector's legend falls under the readable size (`legend: false`). Kokoro at speed 0.85.

**Lint.** `particle_mass`, `particle_charge`, `particle_spin`, `particle_lifetime`,
`branching_ratio`, `conservation_claim`, `feynman_boson`, `kinematics_number`,
`detector_signature`, `significance_claim`, `simulated_label`, `particle_units` check the
narration and the screens against the model; `calc_numbers`, `calc_units`, `calc_sigfigs` check
the calculations. Run `vidgen lint` in 16:9 and 9:16.

```yaml
- id: mass
  type: calculation
  params:
    title: "The invariant mass of the two photons"
    symbols:
      - {name: pT1, value: "56.3 GeV", meaning: "photon 1, c = 1", source: "the event"}
      - {name: pT2, value: "54.7 GeV", meaning: "photon 2, c = 1", source: "the event"}
      - {name: deta, value: "1.00", meaning: "pseudorapidity difference", tex: "\\Delta\\eta"}
      - {name: dphi, value: "178.2 deg", meaning: "angle across the beam", tex: "\\Delta\\phi"}
    calculations:
      - {name: m2, expr: "2*pT1*pT2*(cosh(deta) - cos(dphi))", unit: GeV^2, meaning: "its square"}
      - {name: m, expr: "sqrt(m2)", unit: GeV, meaning: "invariant mass of the two photons"}
  beats:
    - text: "For photons it needs only their transverse momenta and the angles between them."
      actions: [{substitute: calc1, at: "@momenta"}]
    - text: "This event gives one hundred and twenty-five GeV."
      actions: [{compute: calc2, at: "@This"}]
```

<!-- topic: overlays (also: transitions, transition, carry, continuity, captions) -->
## Overlays, transitions and continuity

**Overlays** draw on top of every scene and stay fixed through camera moves:

```yaml
overlays:
  - {type: progress_bar, exclude: [intro]}
  - {type: chapter_indicator, total: true, reserve: true}
  - {type: lower_third, scene: intro, at: 1.0, name: "Ada Lovelace", title: "Mathematician"}
  - {type: watermark, icon: brain-circuit, corner: bottom_right, opacity: 0.4}
scenes:
  - id: intro
    type: title
    params: {title: "Engines that think"}
    beats: [{text: "Ada Lovelace saw it first: machines could do more than count."}]
  - id: part1
    type: chapter
    params: {number: 1, title: "The engine"}
    duration: 3.5
  - id: body
    type: text_card
    params: {text: "Cards in, numbers out"}
    beats: [{text: "The engine read its program from punched cards."}]
```

- `progress_bar` and `chapter_indicator` for videos over 2 minutes with chapters.
- `lower_third` once, when a person or place first appears (5 s).
- `watermark` small and faint, or not at all.
- `captions` for social and muted viewing (`vidgen guide social`).
- `hud` on a scene where the story is seen through an implant or a visor (`at`, `duration`,
  `alert`, `lines`, `heart`, `scan`), not as decoration. Its alert and lines move to a free
  corner by themselves, off the faces; in a close-up use `compact: true` (lint `overlay_face`).
Lint's `overlay_overlap` reports an overlay over scene text: give it `reserve: true` or move it.

**Transitions** (`transition:` per scene = the way into it, or video-wide). Default: cuts (every
scene fades out by itself), which is right most of the time. `crossfade` (0.5 s) for a calm
flow, `fade_color` into `chapter` cards to mark a new section, `push` / `wipe` sparingly (one
style per video), `iris_out` / `iris_in` in cartoons (`vidgen guide cartoons`). Transitions
never cover narration.

```yaml
transition: crossfade
scenes:
  - id: intro
    type: title
    params: {title: "Results"}
    beats: [{text: "Here is what we found."}]
  - id: part2
    type: chapter
    params: {number: 2, title: "Results", icon: chart-column}
    transition: {type: fade_color, color: surface}
    duration: 3.5
  - id: big
    type: stat
    transition: cut
    carry: [icon]
    params: {value: 3.2, suffix: "x", label: "faster", icon: chart-column}
    beats: [{text: "Everything got three times faster."}]
```

**Continuity** (`carry:`): a match cut that moves an element of the scene before into this
scene (the chapter's icon into the stat's icon, `"title -> heading"`). Use it with a `cut`,
once or twice per video, where the two scenes are about the same thing.

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
come). It needs the optional extra (`pip install "schu-video-generator[kokoro]"`, Python
3.10-3.12); without it `vidgen tts` says what to install. This is the voice for your own
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
- **Without the extra.** Composed music needs `pip install "schu-video-generator[music]"`; the first
  render downloads the SoundFont (32 MB, once; `vidgen soundfont fetch` does it now). Without the
  extra `vidgen validate` warns and the mood's built-in bed plays instead (`calm` → calm,
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

<!-- topic: examples (also: good-bad, before-after, patterns, antipatterns) -->
## Good vs bad: before and after

**1. A wall of text → a progressive grid.** Bad: six long items appear together while the voice
reads the first one; 40 words on screen.

```yaml
- id: features_bad
  type: bullets
  params:
    heading: "Key features of the platform you should know about"
    reveal: all
    items:
      - "Our compute layer scales automatically with your workload"
      - "Storage is replicated across three regions for durability"
      - "The network is software-defined and fully encrypted"
      - "Security follows a zero-trust model everywhere"
  beats:
    - text: "The platform has many features: compute that scales automatically, storage replicated across three regions, a software-defined encrypted network, and zero-trust security everywhere."
```

Good: one or two labels per beat, icons carry the category, the voice adds the detail.

```yaml
- id: features_good
  type: icon_grid
  params:
    heading: "What you get"
    icon_color: palette
    items:
      - {icon: cpu, label: "Compute", sublabel: "scales itself"}
      - {icon: database, label: "Storage", sublabel: "3 regions"}
      - {icon: network, label: "Network", sublabel: "encrypted"}
      - {icon: shield-check, label: "Security", sublabel: "zero trust"}
  beats:
    - text: "Compute grows and shrinks with your workload."
    - text: "Every file is stored in three regions."
    - text: "All traffic is encrypted."
    - text: "And nothing is trusted by default."
```

**2. Reading the slide → complementing it.** Bad: the voice says exactly what is written.

```yaml
- id: claim_bad
  type: text_card
  params: {text: "Smaller models can be just as accurate"}
  beats: [{text: "Smaller models can be just as accurate."}]
```

Good: the screen holds the claim, the voice gives the reason and the stakes.

```yaml
- id: claim_good
  type: text_card
  params: {text: "Smaller ≠ worse"}
  beats:
    - text: "We assumed size bought accuracy."
    - text: "On our benchmark, a model half the size scored the same."
      actions: [{highlight: text, style: underline, at: 0.4}]
```

**3. A raw number → a `stat` with a comparison.** Bad: a sentence of digits.

```yaml
- id: latency_bad
  type: text_card
  params: {text: "Median latency went from 18 ms to 12.5 ms after the change"}
  beats: [{text: "Median latency went from eighteen milliseconds to twelve and a half milliseconds after the change."}]
```

Good: one big number that counts, the change coloured by whether it is good.

```yaml
- id: latency_good
  type: stat
  params:
    value: 12.5
    unit: "ms"
    label: "median latency"
    comparison: {value: 18, kind: before, better: lower, delta: percent}
  beats:
    - text: "Requests now take twelve and a half milliseconds."
    - text: "That is almost a third faster than before."
```

**4. An unexplained chart → a chart that points.** Bad: bars appear, the voice talks about
something the viewer has to find.

```yaml
- id: costs_bad
  type: bar_chart
  params: {labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"], values: [12, 13, 12, 31, 14, 13]}
  beats: [{text: "As you can see, something unusual happened in one of these months, which we investigated."}]
```

Good: a title that says what the chart is, the outlier highlighted while it is named, a callout
with the reason, and the source in the caption.

```yaml
- id: costs_good
  type: bar_chart
  params:
    title: "Cloud cost per month (k$)"
    labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    values: [12, 13, 12, 31, 14, 13]
    caption: "Source: billing export, 2025"
  beats:
    - text: "Our cloud bill is usually flat."
    - text: "Except in April, when it more than doubled."
      actions:
        - {highlight: "bar:Apr"}
        - {callout: "bar:Apr", kind: arrow, label: "Test cluster left on", at: 0.5}
    - text: "One forgotten cluster cost nineteen thousand dollars."
```

**5. A long beat → short beats with their own reveals.** Bad: 45 words over one picture: 18 s of
the same frame (lint `dead_air`).

```yaml
- id: pipeline_bad
  type: process
  params: {stages: ["Write", "Check", "Render", "Publish"], reveal: all}
  beats:
    - text: "You write the config, then you check it with validate and storyboard and lint until everything is clean, then you render the final video with the real voice, and finally you publish it together with its chapters, thumbnail and subtitles so people can find it."
```

Good: one stage per beat, the token moves while each is named.

```yaml
- id: pipeline_good
  type: process
  params:
    heading: "From idea to video"
    stages: [{label: "Write", icon: pencil}, {label: "Check", icon: search}, {label: "Render", icon: play}, {label: "Publish", icon: megaphone}]
  beats:
    - text: "You write one config file."
    - text: "Storyboard and lint check it."
    - text: "Then the real voice and the final render."
    - text: "And it ships with chapters and subtitles."
```

**6. A slow opening → a hook.** Bad: 6 s of logo and title before anything is said.

```yaml
- id: opening_bad
  type: title
  params: {title: "Quarterly Infrastructure Review", subtitle: "Platform Team", kicker: "Q3 2025"}
  beats: [{text: "Welcome to the quarterly infrastructure review by the platform team. In this video we will look at a number of topics."}]
```

Good: the result first, then the context.

```yaml
- id: opening_good
  type: stat
  params: {value: 41, suffix: "%", label: "lower cloud bill", context: "Q3 vs Q2 2025"}
  beats:
    - text: "We cut our cloud bill by forty-one percent."
    - text: "Here is how, in three changes."
```

<!-- topic: outputs (also: slides, export, gif, thumbnail, chapters, translations, translate, languages, licence, license, rights) -->
## Outputs: video, chapters, thumbnail, slides, GIFs, translations

- **Video and subtitles**: `vidgen render` writes `output/<output>.mp4` and `<output>.srt`
  (`--preview`: `<output>_preview.mp4`; `--draft`: `<output>_draft.mp4`; `--variant NAME`: `<output>_<variant>.mp4`). The
  chapter list and thumbnail go to `output/` too; `output_dir:` (relative to the project folder)
  or `--output-dir DIR` moves them. `build/` and `exports/` stay put.
- **Chapters**: with `chapter` cards or `chapter:` keys the MP4 gets chapter marks and
  `<output>_chapters.txt` the YouTube list (`0:00 Intro`...); `vidgen validate` warns when
  YouTube would ignore it (fewer than 3 chapters, one under 10 s). `metadata:` adds tags. The
  scenes' `references:` and `figure_credit:` are appended to that file as a numbered list.
- **Thumbnail**: a designed card reads best small. Keep its title ≤ 6 words. `vidgen render`
  writes it with the video, `vidgen thumbnail` alone; open the small copy it names
  (`build/.../thumbnail/<name>_small.png`, YouTube's 320 px) and fix the checks it prints. A
  frame of a scene works too: `vidgen thumbnail --scene results --beat 2`.

```yaml
thumbnail: {title: "77% of the model is dead weight", icon: brain-circuit, jpeg: true}
scenes:
  - id: intro
    type: title
    params: {title: "Pruning large models"}
    beats: [{text: "Most of a large model can go."}]
```

- **Slides**: `vidgen slides --final` writes a self-contained HTML deck to `exports/` (a slide
  per beat, the narration as speaker notes; `--audio` for a narrated deck); `--format pdf
  --notes` a PDF with notes pages (extra `schu-video-generator[pdf]`). A video built with one reveal per beat
  is a good deck for free; check `--mode scene` for a compact one.
- **GIFs and clips**: `vidgen export gif --scene ID --max-mb 5` (a palette GIF within a size
  budget, for READMEs and chats), `vidgen export clip --scene ID --with-audio` (an MP4 part).
  Render the video first.
- **Translations**: add a variant with `language: pt-BR` and `translations:`, run
  `vidgen translate-template --variant pt`, fill in every `text:` of the file (keep it short:
  translations run longer), `vidgen validate` (lists what is still untranslated),
  `vidgen tts --variant pt` (voices only translated beats), then storyboard and lint the
  variant: longer text can overflow where the source fit.
- **Dubbing a cartoon**: the same variant. With Kokoro every speaker gets a voice of the
  language of the same kind automatically (`vidgen validate` prints `dub [pt]: ...` and warns
  when two speakers end up with one voice); name one with `dub: {pt: pm_alex}` on that voice in
  `voices:` (or on `voice:` for the narrator). Then `vidgen tts --all-languages`, `vidgen lint
  --all-languages` (timings, overlaps and text are checked in each language) and `vidgen render
  --preview --all-languages`. Example: `examples/cartoon-music-box` (variant `pt`).

```yaml
variants:
  pt:
    language: pt-BR
    translations: translations/pt.yaml
scenes:
  - id: intro
    type: title
    params: {title: "Hello"}
    beats: [{text: "Hello and welcome."}]
```

- **Generated pictures** (`image` `generate:`): `vidgen imagegen --dry-run` shows prompts and
  cost; placeholders render until you run `vidgen imagegen`. Describe a scene, never text,
  charts or logos (schu-video-generator draws those better), and set one `imagegen: {style: ...}` for the
  whole video.
- **Cartoon backgrounds** (`stage` `generate:`): see "The set" in `vidgen guide cartoons`.
- **Choosing an image provider**: `openai` (the default; `OPENAI_API_KEY`, gpt-image-1) is one
  good model at a known price. `imagegen: {provider: openrouter, model: author/name}`
  (`OPENROUTER_API_KEY`) reaches many models with one key — some cheaper per picture
  (e.g. `bytedance-seed/seedream-4.5` at ~$0.04, `black-forest-labs/flux.2-klein-4b` by the
  megapixel), some better at a style. Read the prices in `vidgen imagegen --dry-run` (its
  `price:` line says the basis; "price unknown" for models billed per token) and fix every
  `problem:` / `note:` it prints before a real run. Keep one provider and model per video so the
  pictures match; changing them makes every picture "missing" (new pictures, new cost). If the
  account requires Zero Data Retention, choose a model with a ZDR endpoint (e.g.
  `bytedance-seed/seedream-5-0-flash`); schu-video-generator's error lists them when a model is refused.
- **Vector (SVG) pictures** (`generate: {prompt, format: svg}` with `imagegen.svg_model`, e.g.
  `recraft/recraft-v4.1-vector`, ~$0.08; or an `.svg` file as `path`): drawn as shapes, so
  `draw: true` traces then fills them and `recolor: theme` paints them in the theme's colours.
  Worth it for flat illustrations, icons and diagram-like art (few flat colours; ask for
  "flat illustration, simple shapes, few colours"); not for photos or soft lighting (thousands
  of shapes, capped and thinned: worse than a PNG). Text in an SVG is removed — keep words in
  schu-video-generator's captions. No SVG model has a ZDR endpoint (2026-10-08).

### Your content and third-party services

- The MIT licence covers the software, not the videos you make or the files you add.
- Use only images, clips, screenshots, music and quotes you own or have permission to use
  (screenshots of other products may also show their trademarks).
- ElevenLabs narration and OpenAI pictures are subject to those providers' terms (e.g. plan
  limits on commercial use; cloning a voice requires the speaker's consent). Pictures made
  through OpenRouter, and narration voiced through it, are subject to OpenRouter's terms and to
  those of the model's provider.
- The built-in fonts (SIL OFL), Lucide icons (ISC), Natural Earth map data, sound effects and
  music beds may be used in your videos, including commercially, with no attribution required
  in the video (Natural Earth asks for none; the OFL and ISC notices concern redistributing the
  files themselves). So may composed music played with the default GeneralUser GS SoundFont (no
  attribution required; a credit in the description is welcome: `vidgen soundfont info` prints
  one); with your own `soundfont:` its licence applies.

<!-- topic: troubleshooting (also: errors, fixes, lint, validate, problems) -->
## Troubleshooting: messages and fixes

**`vidgen validate`** (each problem names a config path; `--json` lists them all):

| message says | fix |
|---|---|
| `unknown scene type 'x'; did you mean ...` | use a listed type (`vidgen list-scenes`) |
| `unknown parameter 'x'; did you mean 'y'?` | rename it; `vidgen schema --scene TYPE` lists the params |
| `a scene without beats (silent scene) needs a 'duration'` | add `duration: 2.5`, or give it beats |
| `'duration' is only allowed on silent scenes` | remove `duration`: beats set the length |
| `duplicate beat id` | beat ids are unique in the whole video; rename one |
| `unknown target 'x' ...; did you mean ... (targets: ...)` | pick a name from the list (labels are case-sensitive: `bar:4K`) |
| `until 'x' is not a later beat of scene 'y'` | `until` names a later beat id of the same scene |
| `unknown action 'x'` / `unknown option` | actions are `reveal`, `dim`, `highlight`, `zoom`, `pan`, `follow`, `transform`, `callout`, `sfx`, `particles`, `say`, `look_at`, `turn`, `emote`, `pose`, `react`, `walk_to`, `run_to`, `enter`, `exit`, `wander`, `meet`, `gesture`, `jump`, `keyframes`, `move_along`, `pick_up`, `hold`, `put_down`, `give`, `throw`, `open`, `close`, `let_go`, `pour`, `switch_on`, `switch_off`, `hide`, `drop_fruit`, `birds`, `sit_on`, `lean_on`, `stand_up`, `get_in`, `ride_to`, `get_out`, `light`, `wind`, `blow_away`, `effect` |
| `labels has 2 entries but values has 3` | one value per label |
| `unknown theme color 'x'` | use a token (`primary`, `highlight`...) or quoted hex `"#0B5FFF"`, or add it to `theme.colors` |
| `invalid hex color` | `#RGB`, `#RRGGBB` or `#RRGGBBAA`, in quotes (YAML reads `#` as a comment) |
| `unknown icon 'x'; did you mean 'y'?` | `vidgen list-icons --search WORD` |
| `file not found: assets/...` | paths are relative to the project folder |
| `starts chapter 'x' right after the chapter card` | put the `chapter:` key on the card instead |

LaTeX in YAML: write formulas in single quotes (`'\frac{1}{2}'`). Equations need a LaTeX
install; `vidgen validate` warns when it is missing.

**`vidgen lint`** (each finding names its rule and the still to open):

| rule | what it means | usual fix |
|---|---|---|
| `max_words` | too much text on one frame | split the scene, shorten items, `dim_previous`, fewer columns |
| `min_font` | text too small for the output | less content per scene (it was shrunk to fit), shorter labels, split the table / diagram / timeline |
| `off_frame` | text cut off at the frame edge | shorter text; in a custom scene, place it in a region |
| `safe_area` | text in the margin | as above; check reserving overlays |
| `text_overlap` | two texts on top of each other | fewer or shorter labels; a custom scene's layout |
| `covered_text` | a shape drawn over text | move the shape or the callout (`side:`) |
| `label_spacing` | a callout label touches other text (a value, the title) | another `side:`, an `arrow` instead of a `label`, a shorter label |
| `contrast` | text hard to read on its background | theme tokens instead of custom colours; another preset |
| `overlay_overlap` | an overlay covers scene text | `reserve: true` on the overlay, or another corner / position |
| `host_overlap` | the host overlaps the content, a caption or an overlay | a smaller host (`size`), another `side` / `place`, or `host: false` on that scene |
| `walk_overlap` | a character's walk ends on another character | walk it to another mark or x, or move the other one first |
| `off_stage` | a character is cut by the edge of the view (in a `shot`: a character it frames is out of it) | another mark or x inside the view, or `pan` to it; in a shot, keep it from walking out or frame another shot |
| `character_overlap` | two characters stand on each other (at about the same depth) | marks further apart, or `walk_to` one away (across, or in depth) |
| `prop_overlap` | two props on the floor at about the same depth are drawn over each other (a room's door over the sofa against the wall) | another `at` for one (a door: its x in the room's `doors`), a smaller `scale`, or a `depth` that puts one in front; a picture or clock above furniture, a lifted prop and a rug are fine |
| `bubble_overlap` | a speech bubble covers a face, another bubble or an effect symbol | a shorter `bubble` text, characters further apart, or the lines (or the line and the effect) in different beats |
| `facing_away` | a speaker faces away from the one it talks to (last looked at, else the nearest) | `turn`, `look_at: <listener>`, or swap their marks |
| `hidden_speaker` | something in front hides the speaker's face (on an iso place: what really covers its eyes and mouth, a lamp post across the face) | move one of them, or a smaller `depth` for the speaker; on an iso place `walk_to` a spot with nothing in front, or a `shot` |
| `small_speaker` | a speaking face too small on screen to read it and its lip sync (on an iso place a speaker with a name tag may say up to 12 words) | `shot: closeup <name>` (or `medium`) for that beat, or `character_size: large` |
| `offscreen_action` | on an iso place: a walk, a thing handed about or a change of the place (a door, a lamp) the camera mostly does not show while it happens | `shot: wide`, a `pan` or `follow` to it, or do it in a beat whose shot shows it |
| `mouth_without_voice` | a mouth still shows speech after the narration ended | `vidgen tts` again; in a custom scene, lip sync with `clock=self.beat_clock()` |
| `said_before_shown` | the narration names a label on screen (a node, a callout, a stage) seconds before it appears, and not again when it does | show it on the word: `{reveal: node:database, at: "@database"}` (or the callout's `at`); or name it in the beat that shows it |
| `unsaid_reveal` | (off unless `lint.rules.unsaid_reveal.severity` is set) a beat shows new labels the narration never names | say what the viewer should look at, or leave it off: many labels need no words |
| `iso_labels` | an `iso_diagram` label over a block it does not name (a group's caption among its blocks), over another label or a connector, or far from what it names | more `spacing` or `at` further apart, shorter labels, fewer blocks; a stack's `label_side` |
| `music_check` | a project piece (`assets/music/NAME.yaml`) the video plays is loud in the voice's range, too bright, boomy, unsteady, peaky or clicks at its loop (`vidgen music check`'s fixes; its notes are info) | the fix the message names (a track's `volume`, an octave, `lowpass`), then `vidgen music check` again; or `severity: off` in `lint.rules.music_check` |
| `science_scale` | a `cell` with a scale bar draws something far outside its real size, or too many nuclei / centrosomes | a real `size`, or `not_to_scale: true` (the scene says so); `lint_ignore` a real exception |
| `science_location` | the narration puts a process where it never is (glycolysis in the mitochondria) or a thing where the `cell` does not show it | say where it is, or place it there (`in:`, `on:`) |
| `science_direction` | a wrong direction: RNA made 3′→5′, a protein made C→N, kinesin to minus, protons pumped into the matrix | the textbook direction the message gives |
| `science_energy` | "active transport" through a channel or uniporter, or with no pump, symporter or ATP in the scene | call it facilitated diffusion, or show the pump / coupled carrier |
| `science_naming` | a scene's gene written as its protein (mouse `TRP53 gene`), the wrong case, a gene label without `<i>` | the form the message gives (mouse: gene *Trp53*, protein TRP53) |
| `science_pathway` | the narration says activates where the pathway's arc inhibits (or the reverse) | fix the words, or the arc (`effect:`) |
| `science_counts` | a number against the textbook (net 4 ATP from glycolysis) | the number the message gives |
| `genetics_ratio` | a ratio or share the `cross` does not give ("a 3:1 ratio" for a dihybrid, "half the daughters affected") | the ratio the message gives, or "each trait alone…" for one trait's ratio |
| `genetics_pedigree` | the chart does not fit its `mode` (error); "a dominant trait skips a generation"; an X-linked trait passed father to son; a carrier or risk probability against the chart | fix the chart or the mode; say reduced penetrance (`penetrance:`); the probability the message gives |
| `genetics_linkage` | RF over 50 %, a distance or RF against the `linkage_map` (or `linkage:`), linked loci called unlinked | the cM / RF the message gives |
| `genetics_hwe` | carriers called q², the incidence called 2pq, q or the carriers against the incidence | q = √incidence, carriers 2pq (≈ 2q) |
| `genetics_crispr` | the wrong PAM for the Cas, a cut downstream of the PAM or not 3 bp upstream, sticky ends for Cas9 | SpCas9: NGG, a blunt cut 3 bp upstream (5′) of the PAM |
| `genetics_karyotype` | ISCN that does not parse or is out of order, "45,X is male", a condition the `karyotype` does not show | the notation or the condition the message gives |
| `genetics_hgvs` | HGVS not valid or not the `mutation`'s variant, legacy numbering unannounced (p.Glu6Val); info: `ΔF508`, `R553X` | the HGVS form; call the old name legacy |
| `calc_numbers` | a number said or shown for a `calculation`'s value that is not what it computes ("thirty-five kilometres per second" for 29.8 km/s) | the value the message gives (or "about" and a rounding of it); or fix the calculation |
| `calc_units` | "a speed of 30 kilometres"; a value off by a factor of 1000 (m/s for km/s, mg for µg) | the unit of that kind, the right prefix |
| `calc_sigfigs` | (info) more figures than the inputs give: a `sig` beyond them, "29.7847 km/s" said for 29.8 | round to the figures the message gives, or give the inputs more figures |
| `plot_units` | a `plot` axis titled with a physical quantity (time, energy…) but no unit | `unit:` on the axis, or `name (unit)` in the CSV header |
| `plot_log` | error bars, a fit or its band, or a reference line at or below zero on a log axis | asymmetric errors that stay positive, a positive model, `band: none`, or a linear / symlog axis |
| `plot_errors` | error bars without `error:`, or narration calling them otherwise ("standard deviation" for `sem`) | `error:` sd, sem, ci95, range, poisson or other; say what they are |
| `plot_series` | several series with `legend: false` and no label naming them; a placeholder name (`series 2`) | show the legend or label each series; name it after what it is |
| `plot_truncated` | (info) bars not starting at zero: a histogram on a broken y axis, a `bar_chart` `baseline` other than 0 | drop the break / baseline, or say so on screen |
| `plot_conserved` | a model's `conserved` quantity drifts beyond 1 % | `method: leapfrog`, or a smaller `step` |
| `plot_fit_claims` | a fitted value said otherwise ("a half-life of twelve days" for 8.0 ± 0.1 d, "exponent five halves") | the value the fit gives, or fit what you say |
| `orbit_period` | a period said for an `orbit` scene's body that its orbit does not have ("Mars takes three years" for 1.88 yr) | the period the message gives ("about two years" is fine), or change the orbit |
| `orbit_speed` | a speed against vis-viva at the point named (perihelion, aphelion…), an escape or circular speed | the speed the message gives, or name the right point |
| `orbit_dv` | a burn's or transfer's Δv said otherwise ("the first burn takes 3.2 km/s" for 2.43) | the Δv the panel shows (first, second, total) |
| `orbit_transfer` | a transfer time, phase angle or launch-window interval said otherwise ("180 days" for 259 d, "every 18 months" for 780 d) | the value the message gives |
| `orbit_distance` | a distance, altitude, radius, Lagrange point or size ratio said otherwise ("L2 is 15 million km away" for 1.5 million) | the value the message gives |
| `orbit_date` | an opposition or conjunction date JPL's elements do not give ("Mars was at opposition in 2021") | the date the message gives |
| `orbit_scale` | "to scale" said of a picture that is not: enlarged bodies, `radial: log`, the `sizes` picture's distances, the tides | say what is to scale ("the distances are to scale, the sizes are not") |
| `orbit_conserved` | an n-body run's energy, angular momentum or Jacobi constant drifts beyond 1 % | a smaller `step`, or `method: leapfrog` |
| `orbit_crash` | a periapsis in the atmosphere (Earth below 100 km), a flyby through the air, n-body bodies passing through each other | raise the periapsis or the flyby; change the starting state |
| `particle_mass` | a mass said otherwise than PDG 2024 ("the W weighs 91 GeV"; MeV for GeV) | the value in the message, or the particle it names (did you mean …) |
| `particle_charge` | a charge said wrong ("the down quark has charge +2/3") | the value in the message |
| `particle_spin` | a spin said wrong ("the photon has spin 1/2", "the Higgs boson is a fermion") | the value in the message |
| `particle_lifetime` | a mean life, half-life or width said otherwise ("the muon lives 2.2 ms") | the value in the message; a moving particle's life is γτ (say so) |
| `branching_ratio` | a branching ratio said wrong ("most Higgs bosons decay to two photons") | the share in the message; "most" only for the largest mode |
| `conservation_claim` | a decay called allowed that the checker forbids, or forbidden by a law it keeps | say what the message says is broken (`particle_physics.check("…").explain()`) |
| `feynman_boson` | the wrong boson: a coupling that does not exist, flavour changed without a W, a boson the diagram does not show | name the boson in the message, or change the diagram |
| `kinematics_number` | a momentum, energy, invariant mass, decay length or threshold said otherwise than computed | the scene's value (or `from_scene` it into a calculation) |
| `detector_signature` | "photons leave tracks", "muons stop in the ECAL", "neutrinos are seen in the calorimeter" | the signature in the message |
| `significance_claim` | a p-value said as the chance the result is wrong, a σ the spectrum does not reach | "background alone would fluctuate this high once in N tries"; the scene's σ |
| `simulated_label` | simulated data called real, or a spectrum / event display without "simulated" on screen | say "simulated"; keep it in the label or caption |
| `particle_units` (info) | masses both in GeV and GeV/c² on screen | one convention throughout |
| `shorts_safe_area` | in a Short (`shorts:`), text or a face where the app covers the frame (bottom 20 %, right 15 %), or a caption / the hook over a face | a closer `shot` or `zoom` with the faces higher; move the scene's text inwards |
| `overlay_face` | a `hud`'s text or plate over a character's face (outside Shorts) | frame the face away from the corners, `compact: true`, fewer `lines` |
| `shorts_length` (error) | a Short longer than `shorts.max_seconds` (60) | leave out beats or scenes in `cut:`, a shorter `end_card` |
| `concept_colors` | the `terms:` colours: more than 5, too faint on the background, or a term coloured otherwise by a scene setting | fewer colours (related terms may share one), a readable theme token, or leave the scene's colour setting out |
| `look_alike` | two characters too alike to tell apart | change what the message names on the second (body, hair, species, clothes colour); or `vidgen cast --random N` |
| `dead_air` | nothing moved for over 6 s | split the beat, add a reveal or an action, shorten a silent `duration` |
| `narration_speed` | words per second outside 1.8–3.5 (English) | shorten or lengthen the beat's text; without audio it is only `info` (an estimate) |
| `animation_overrun` | animations ran past the narration | a custom scene's animations are too long for the beat |
| `rushed_animation` | animations squeezed into a short beat | merge two short beats, or reveal fewer things per beat |
| `talked_over` | an `overlap` hides whole words of the line before, or an `interrupt` cuts them | a shorter `overlap` (none for an interrupt), or `interrupt: true` to cut the line |
| `readback` | the audio does not say what the text says | add a `pronunciation:` entry, `vidgen tts`, check again |
| `unclear_speech` | (only with `--readback`) a word heard unclearly or after an odd pause | respell it in `pronunciation:`, or another voice, speed or `emotion:` for the beat; `vidgen tts`, check again |

**Other things that go wrong**

- *The storyboard did not change after an edit to a file outside `assets/`*: `--force`.
- *A table / diagram / timeline "does not fit at the readable size"* (render warning): it was
  scaled down; split it into two scenes or shorten the texts.
- *Preview timing is wrong*: until `vidgen tts`, beats are timed from word counts; numbers and
  acronyms take longer to say. Re-check pacing after the real audio.
- *`vidgen render --scene ID` re-joins the other scenes as they are*: render the scene before a
  new transition or carry too.
- *`ffmpeg not found`*: install it and open a new terminal.
- *`ffmpeg X.Y is too old`*: install ffmpeg 4.4 or newer.
