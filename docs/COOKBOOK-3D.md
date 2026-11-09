# Cookbook: simple 3D scenes

Craft notes for videos with schu-video-generator's [`3d`](CONFIG.md#3d) scene type (DESIGN §114):
plain shapes, labels and character stand-ins, seen by a camera that stands still or moves on the
words the narration says, drawn by three.js in headless Chromium. The look is deliberately simple
(plain colours, one light, no shadows or textures): it is for **explaining** — where things are,
what moves where, who walks up to whom — not for realism. The author guide has the short version
(`vidgen guide 3d`); every key is in `docs/CONFIG.md`. The worked example is
[`examples/3d-short`](../examples/3d-short/video.yaml): a 9:16 Short of about 15 s with shapes, two
stand-ins who walk and turn to each other, a ball that appears, rolls and glows, four camera moves
on spoken words, karaoke captions, and its guide passes. The
[scene gallery](gallery/3d.md) shows the type.

## 1. Setting up

A plain install brings Playwright. The Chromium browser is a separate download, needed once:

```
python -m playwright install chromium
```

On Windows: `py -m playwright install chromium`. Without it a render stops with that command, and
`vidgen validate` warns (only when the project has a `3d` scene). Nothing is fetched while rendering: three.js is part of the package.

## 2. Building a scene

Scene units, **y is up**, the floor at `y: 0`. A shape is centred on its `position`, so a box of
height 1 stands on the floor at `y: 0.5`, a stand-in of height 1.6 at `y: 0.8`.

| you want | write | notes |
|---|---|---|
| something to stand on | `floor: true` (or `{size, color, y}`) | an object with id `floor` |
| a thing | `{id: crate, shape: box, size: 0.9, position: [0, 0.45, -1.6]}` | box, sphere, cylinder, cone, torus, plane |
| a person | `{id: ana, shape: standin, name: "Ana", color: primary, position: [-1.7, 0.8, 1], rotation: [0, 90, 0]}` | its nose faces +z unturned; `rotation: [0, 90, 0]` faces +x |
| a name in the air | `{id: tag, shape: label, text: "Crate", position: [0, 1.6, -1.6]}` | always faces the camera; `screen_size: true` keeps its size |
| something pointed at | `{id: pointer, shape: arrow, position: [1.1, 2.4, 0.6], to: ball}` | stops at the object's edge and follows it |
| parts that move together | `{id: tree, shape: group, ...}` then `{id: crown, parent: tree, ...}` | the parent first; children are in its frame |
| something that comes in later | `visible: false`, then `object_show` on a word | `style: grow` grows it from nothing |

Give every object a short, meaningful `id`: actions, lint, the mask's colour table and (later)
video-to-video prompts all use it. Use theme tokens (`primary`, `secondary`, `accent`,
`highlight`) for the objects that matter and quiet hex colours for the set.

## 3. The camera

`camera: {position, look_at, fov}` is where the shot starts. `fov` is the angle across the frame's
**shorter** side, so a subject framed in 16:9 fills a 9:16 frame alike — but a portrait frame then
sees much more above and below. For a Short, keep the set compact across (about as wide as it is
deep), bring the camera close (`fov` 50–56, 5–6 units away) and look slightly down; the title sits
at the top and the captions at the bottom, so keep the objects in the middle band.

Move it with beat actions timed to words (`at: "@word"`), each from where the previous one left it:

| action | when |
|---|---|
| `camera_dolly` (`by`) | a small push-in as the story starts, or a pull-back |
| `camera_orbit` (target or `around`, `degrees`) | to show depth; one orbit per idea, 45–90° |
| `camera_fly_to` (target, `distance`) | when the narration names an object; the camera keeps following it if it moves |
| `camera_look_at` (target or `point`) | a small turn reads better than a long flight |
| `camera_move` (`to`, `look_at`) | to pull back to the whole set at the end |

Let a move finish before the next starts (the next one stops it where it is). Without `run_time`
a move lasts to the end of its beat.

## 4. Objects and stand-ins

The object actions (`object_move`, `object_path`, `object_rotate`, `object_spin`, `object_scale`,
`object_show`, `object_hide`, `object_highlight`, `object_walk`, `object_face`) are timed the same
way. The ones that carry a story:

- **`object_walk: ana, to: crate`** — a stand-in turns and walks up to an object (it stops in front
  of it) or to `[x, z]`, bobbing a little with its steps; its length comes from its `speed`.
- **`object_face: ben, to: ana`** — before a stand-in "speaks", turn it to whom it speaks to.
- **`object_show` + `object_highlight`** on the word that names a thing — the viewer looks where
  the narration points.
- **`object_path`** with a few `points` — a journey; `turn: true` turns it to face the way it goes.

Give a stand-in's lines its voice (`voices: {ana: {}}` and `voice: ana` on the beat): lint then
checks that the speaker is on screen and not hidden while it talks.

## 5. Guide passes

`guide_passes: true` (or `guide_passes: all`, or `vidgen render --guide-passes`) also draws three plainer videos of the 3D
picture, with exactly its frames, camera and timing, beside the 3D clip in
`build/<quality>/three_d/`. They are inputs for tools that need the scene's layout rather than
its look (later: a video model that repaints the scene in a style of its own):

| pass | what it is | tips |
|---|---|---|
| `depth` | near white, far dark grey, background black; one range for the whole shot, fitted to the objects | the floor is clamped to that range (white in front of the objects, the darkest grey behind them); big camera moves widen the range, so a shot that flies in close gets less contrast — set `depth_range: [near, far]` to choose it |
| `outline` | white edges on black: silhouettes, the creases of boxes and cylinders, where an object hides part of itself | thin lines (about 1 px per 540 px); labels and name tags are left out |
| `mask` | each object one flat colour on black, the floor dark grey `#404040` | the colours come from the ids (adding an object keeps the others'), listed in `<scene>.mask-colors.json`: `colors`, `objects` (with parents and stand-in names), `names` |

Ask for some of them as in the command line: `guide_passes: depth`, `guide_passes: depth,mask`
(spaces allowed) or `guide_passes: [depth, mask]`; a misspelt name is refused with did-you-mean.

The passes are lossless `.mkv` clips (exact mask colours); convert them when a tool wants MP4 or
PNG frames. They hold only the 3D shapes: no title, captions, overlays, labels or name tags.

**A pass as the guide of a generated clip.** A beat of a `3d` scene can be made into real-looking
footage by a video model that follows the 3D layout: give the beat a `generated_shot` with
`guide: depth` (or `outline`, `mask`; `guide: true` sends the normal 3D view).
`vidgen generate inputs --guide` draws the pass and converts the beat's part to MP4 for the
model. The walkthrough, which pass to choose and the limits:
[COOKBOOK-GENERATED-VIDEO.md, From a 3D scene to a generated clip](COOKBOOK-GENERATED-VIDEO.md#6-from-a-3d-scene-to-a-generated-clip).

## 6. Checking

- `vidgen validate` names unknown object ids with a did-you-mean (in params and actions), camera
  moves that cannot be made, a walk of something that is not a stand-in.
- `vidgen storyboard --per-beat 3` shows the moves mid-beat; `vidgen lint` has `three_d_off_frame`
  (an object the beat is about is mostly outside the frame) and `three_d_hidden` (mostly behind a
  nearer one) — estimates from spheres, so a tall stand-in counts a little larger than it is.
- The 3D frames are cached: a caption or title change re-renders the scene but reuses the clip.

## 7. Common mistakes

| mistake | fix |
|---|---|
| objects sunk into the floor | `y` = half the object's height |
| a tiny set in a 9:16 frame | a compact set, the camera closer, `fov` 50–56 |
| the arrow points at nothing at the start | give it `visible: false` with the object, `object_show` both |
| everything moves at once | one camera move and one or two object actions per beat |
| a depth pass with flat greys | the camera flies far in and out within the shot: split the shot, or set `depth_range` |
