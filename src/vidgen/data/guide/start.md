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

