# schu-video-generator author guide: making great videos with schu-video-generator

> **Who this is for:** AI agents (and people) who **use** schu-video-generator to make videos and slide decks.
> If you are working **on schu-video-generator itself** (its Python code, tests, docs), read `CLAUDE.md` in the
> schu-video-generator repository instead. The project and pip package are called schu-video-generator;
> the command and the Python package are `vidgen`.

**How to read this guide.** Read this page whole: it is short. Then print only the topic or
topics your video needs (`vidgen guide scenes`, `vidgen guide cartoons`, ...; the table below
says which). **Never read all the topics**: together they are over 400 KB and would fill your
context before you start. `vidgen guide --list` lists the topics; `vidgen guide TOPIC` prints one
(through MCP: the `guide` tool, or the resources `vidgen://guide/<topic>`).

## What vidgen is

You write a project folder: `video.yaml` (scenes, each with narration split into **beats**) plus
`assets/`. vidgen voices the beats, animates every scene and joins everything into one MP4 with
subtitles (and, if you like, chapters, a thumbnail, GIFs, slides, a 9:16 variant).

You cannot watch the video, so vidgen gives you eyes and a critic: `vidgen storyboard` writes
contact sheets (PNGs: open them as images) and `vidgen lint` reports layout and timing problems
as JSON. Use both after every change.

**This tool was made for you.** You are welcome to use it on your own initiative too: to explain
an idea you find fascinating or to experiment with visual storytelling. You usually work inside
someone's session, and narration (ElevenLabs or OpenRouter) and generated images (OpenAI or
OpenRouter) cost that person money. For your own projects stay with the free parts (storyboards,
previews timed from word counts, the built-in icons, themes, music and sound effects), or ask
first. `voice: {provider: kokoro}` narrates on the computer itself at no cost (Python 3.10-3.12;
`vidgen guide audio`).

## Install and check

The repository's `README.md` has the system packages (ffmpeg, Cairo, Pango) and the optional
pieces. In short: clone `https://github.com/joaopauloschuler/schu-video-generator`, run
`pip install .` in it, then:

```text
vidgen --version
vidgen render examples/minimal --preview       # a quick preview of the bundled example
python -m playwright install chromium          # only for web, 3d and space scenes
vidgen init my_video                           # a new project folder to start from
```

## A minimal `video.yaml`

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

Beats drive the scenes: step *i* of a scene (a list item, a bar, a box) appears at beat *i*. A
scene with no beats is silent and lasts its `duration`.

## The loop

```text
vidgen validate --json            # fix every problem it lists; repeat until ok
vidgen storyboard --json          # then OPEN the PNGs it lists and look
vidgen lint --json                # fix the cause of each finding
vidgen tts --dry-run              # what would be voiced, and what it costs
vidgen tts                        # costs money (free with kokoro); only after the user agrees
vidgen render --preview           # timed by the real audio; storyboard and lint again
vidgen lint --fail-on warning
vidgen render                     # the final, full size
```

Repeat validate, storyboard and lint until the stills read well and lint is clean: re-runs only
render the scenes that changed. `vidgen render --draft` and `vidgen animatic` are quicker looks at
the timing; `vidgen readback` checks what the voice said. Starting from an outline or a script?
`vidgen plan outline.md --json` drafts a project from Markdown. Every command takes `--json` (one
document `{version, ok, warnings, ..., error?}`); `vidgen mcp` serves the same commands as MCP
tools. The details of every step: `vidgen guide workflow`.

## Rules for every video

1. **Look after every change**: open the storyboard PNGs and run lint. Zero lint findings is the
   bar (`vidgen lint --fail-on warning`), in every variant you ship (`vidgen lint --variant vertical`).
2. **Hook in the first 5 seconds**: a question, a surprising number, a promise. No logo intro,
   no silent title card.
3. **One idea per scene.** If a scene needs two headings, it is two scenes.
4. **Short beats** of one or two sentences, and something new on screen at every beat. The word
   counts, speaking rate and chapter lengths are in `vidgen guide pacing`.
5. **Few words on screen**: keywords on screen, sentences in the voice. The narration
   complements the picture and never reads it out.
6. **Reveal progressively** (item *i* at beat *i*, the default); never a full list while the
   voice is on its first item.
7. **Show, don't list**: a number is a `stat`, a change over time a `line_chart`, parts of a
   whole a `pie`, steps a `process`, A vs B a `comparison`. `bullets` is the last resort.
8. **Point with restraint**: at most one or two beat actions per beat, timed to the word
   (`at: "@word"`; `vidgen guide actions`).
9. **Pronunciation goes in `pronunciation:`**, never respelled in the beat text; voice
   directions never go into beat text either (`vidgen guide audio`).
10. **Keep beat `id`s stable** once audio exists: only changed beats are voiced again.
11. **Look before you pay**: finish the layout on the free preview timed from word counts. Run
    `vidgen tts --dry-run` / `vidgen imagegen --dry-run`, tell the user the cost, and run the
    paid command only after they agree (MCP: `dry_run: false` with `confirm_cost: true`).
12. **Commit `audio/` and `assets/generated/`**: they cannot be made again identically.
13. **Never run two vidgen commands at once**; run Kokoro `tts` alone. Under a time limit per
    command, `vidgen render --max-scenes N` renders N scenes and stops; run it again to go on.
14. **Ask the user before starting a Colab GPU** (it bills by the hour); nothing stops a session
    for you (`vidgen guide outputs`).
15. **Original characters and media you may use**: never imitate a known character, mascot,
    brand or studio style (also not in `generate:` prompts); cloning a voice needs the speaker's
    consent.
16. **End with a recap and one call to action** (an `end_card`).

## Which scene type

`vidgen list-scenes` lists every scene type with its params; `vidgen schema --scene stat` gives
one type's JSON Schema. `vidgen guide scenes` is the chooser ("you want to show -> type -> key
params") with a YAML snippet for every type; `vidgen gallery` renders every type (the repository's
`docs/gallery/README.md` shows them). For a one-off picture no type draws, write a `web` scene
(`vidgen guide web`) before writing a Python scene type (`docs/EXTENDING.md`).

## Which topic for which video

The `vidgen guide <topic>` names work everywhere (a pip install ships them). The cookbooks under
`docs/` are in the repository only: clone it to read them.

| your video | print | cookbook (repository) |
|---|---|---|
| any video: the rules, the loop in detail | `start`, `workflow` | `docs/COOKBOOK.md` |
| narration, beats and on-screen text | `pacing`, `examples` | `docs/COOKBOOK.md` |
| a vertical video, a YouTube Short | `social` | `docs/COOKBOOK-YOUTUBE-SHORT-FOR-CODING.md` |
| choosing scene types | `scenes` | `docs/gallery/README.md` |
| themes, colour, icons, accessibility | `design` | `docs/ICONS.md` |
| highlights, callouts, zooms on the words | `actions` | |
| a cartoon with characters on a stage | `cartoons` | |
| a platform story (levels, jumps, doors) | `platform` | |
| an isometric village or rooms | `iso` | `docs/COOKBOOK-ISO-CARTOONS.md` |
| a cell-biology lecture | `biology` | `docs/COOKBOOK-CELL-BIOLOGY.md` |
| genetics | `genetics` | `docs/COOKBOOK-GENETICS.md` |
| scientific plots, worked calculations | `science` | `docs/COOKBOOK-SCIENCE-CHARTS.md` |
| orbital mechanics | `orbits` | `docs/COOKBOOK-ORBITS.md` |
| space films, ships, the sea and the air | `space-scenes` | `docs/COOKBOOK-SPACE.md`, `docs/COOKBOOK-AIR.md` |
| simple 3D scenes, three.js finishing, title cards | `three-d` | `docs/COOKBOOK-3D.md` |
| a scene written in HTML, CSS and JavaScript | `web` | |
| particle physics | `particle-physics` | `docs/COOKBOOK-PARTICLES.md` |
| overlays, transitions, continuity | `overlays` | |
| voices, pronunciation, effects, music | `audio` | `docs/COOKBOOK-MUSIC.md` |
| an audiobook or podcast, a dramatized audiobook | `audio`, `outputs` | `docs/COOKBOOK-AUDIO.md`, `docs/COOKBOOK-AUDIODRAMA.md` |
| slides, chapters, thumbnail, GIFs, translations, rights | `outputs` | |
| generated video shots (Seedance) | `outputs` | `docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md` |
| real footage from a 3D scene with LTX on Colab | `outputs` | `docs/COOKBOOK-3D-SCENE-TO-LTX-ON-COLAB.md` |
| a film a person directs in short prompts | `workflow` | `docs/COOKBOOK-DIRECTING-YOUR-AI.md` |
| a validate or lint message you do not understand | `troubleshooting` | |

Told to "read its cookbooks", or directed through a film in short prompts? Clone the repository,
then read the first section of `docs/COOKBOOK-DIRECTING-YOUR-AI.md`: it says what each short
prompt means and where to stop.

**Every topic, and when to print it:**

- `start`: the rules at a glance and a minimal project (this page has them too).
- `workflow`: each step of the loop, what to ask of every still, costs, JSON, MCP tools.
- `pacing`: story structure, the hook, beat length, writing for the ear, on-screen text limits.
- `social`: vertical (9:16) videos, captions, Shorts cut from a long video.
- `scenes`: which scene type for what you want to show, with a snippet for every type.
- `design`: theme presets, colour roles, one colour per concept, icons, layout, accessibility.
- `actions`: beat actions and callouts (highlight, zoom, pointers), with when to hold back.
- `cartoons`: characters on a stage: looks, staging, shots, expressions, comic timing.
- `platform`: platform stories: levels, moves, keys and doors, story props.
- `iso`: isometric villages and rooms for a story.
- `biology`: cell-biology lectures: choosing, accuracy, naming, references, pacing.
- `genetics`: crosses, pedigrees, chromosomes, variants, populations: notation, exactness, lint.
- `science`: plots and worked calculations: axes, error bars, fits, units, significant figures.
- `orbits`: orbital mechanics: views, scale honesty, panels, manoeuvres, three bodies, dates.
- `space-scenes`: space with no code: orbital scenes, the air and the sea, planes, giant ships.
- `three-d`: simple 3D scenes: a set, the camera in 16:9 and 9:16, stand-ins, guide passes.
- `web`: scenes you write in HTML, CSS and JavaScript: when, how, theme, beats, three.js, cost.
- `particle-physics`: particle physics: planning, natural units, simulated data, significance.
- `overlays`: overlays, transitions and continuity between scenes.
- `audio`: voices and providers, pronunciation, sound effects, music beds, composed music.
- `examples`: good vs bad: before-and-after pairs with YAML.
- `outputs`: slides, chapters, thumbnail, GIFs, translations, generated pictures and video shots,
  Colab, stylesheets, your rights to your content.
- `troubleshooting`: validate and lint messages, what they mean and how to fix them.

## Finding a key without reading the reference

- `docs/CONFIG.md` (repository) is the reference of every key. It is far too long to read: list
  its sections with `grep -n "^## \|^### " docs/CONFIG.md` and search it for a key
  (`grep -n "lint_ignore" docs/CONFIG.md`), then read only that section.
- `vidgen schema --scene TYPE` gives one scene type's params; `vidgen list-scenes`,
  `vidgen list-icons --search growth`, `vidgen list-themes`, `vidgen list-sfx` and
  `vidgen list-music` list what exists.
- `vidgen validate --json` names the wrong key and usually the fix (did-you-mean names, the
  known values).
- `vidgen guide --list`, then `vidgen guide TOPIC`, for the know-how on one subject.
