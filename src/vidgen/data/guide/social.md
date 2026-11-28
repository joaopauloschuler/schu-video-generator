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
- **Which windows?** `vidgen shorts suggest [--count 3] [--min 30 --max 60] [--teaser]` (MCP
  `shorts_suggest`) times the beats (audio, else words), scores every 30–60 s window between beat
  boundaries (dialogue, questions, exclamations, emotional and action words, variety, a clean start,
  a strong last line; the ending marked down) and prints a table with a hook each. `--write` adds
  them as variants in `shorts.yaml` (included by the config, both backed up): 9:16, captions, hook,
  end card, a held `zoom ... cut` opening each stage scene. It is a draft: read its notes (a
  mid-scene start keeps the light earlier beats set, not their moves), then storyboard and
  restage as above.

