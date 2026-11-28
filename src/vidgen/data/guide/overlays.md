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

