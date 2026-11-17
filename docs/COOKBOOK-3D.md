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
- `vidgen motion check` watches the rendered video for what stills miss: black frames, one-frame
  flashes, flicker, popping, strobing (section 11).

## 7. Common mistakes

| mistake | fix |
|---|---|
| objects sunk into the floor | `y` = half the object's height |
| a tiny set in a 9:16 frame | a compact set, the camera closer, `fov` 50–56 |
| the arrow points at nothing at the start | give it `visible: false` with the object, `object_show` both |
| everything moves at once | one camera move and one or two object actions per beat |
| a depth pass with flat greys | the camera flies far in and out within the shot: split the shot, or set `depth_range` |

## 8. Finishing three.js `web` scenes

The `3d` type above is deliberately plain. A `web` scene with your own three.js (`vidgen guide
web`) can look like a film, and the finishing both music films wrote by hand ships as a module:
`import {Finish} from "vidgen/three-finish"` (reference: [CONFIG, `web`](CONFIG.md#web), "Finishing
three.js scenes"; worked example: [`examples/three-finish`](../examples/three-finish/README.md)).

- **Write the scene as a function of time.** Put everything that moves in one `update(t)` that
  sets positions from `t` (no `+=`), give it to `Finish`, and call `finish.render(t)` in `frame`.
  Motion blur calls it at sub-frame times; depth of field and the grade may be functions of `t`
  too, read after the scene stands at `t`.
- **Light metal first, finish second.** Metal is black without something to reflect:
  `scene.environment = studioEnvironment(renderer)` (soft boxes, warm against cool), one key
  light with `softShadows(renderer, key, {type: "pcf", radius: 2})`, and a surface from
  `surfaceFinish("circular" | "brushed" | "geneva" | "perlage" | "sunray")`. Get it right with
  every effect off (`bloom: false, dof: false, vignette: 0, grain: 0`), then add them.
- **Bloom only what is brighter than white.** The default threshold is 1 in linear light: a
  lamp's colour multiplied above 1 or a sharp highlight glows, a white wall does not. A bright
  area that blooms veils the whole frame (the widest of its blurs spans most of it); lower
  `strength` before you lower `threshold`.
- **Depth of field in real units.** Say what a scene unit is (`unit: 0.1` = 10 cm) and pick an
  f-stop as a photographer would; pull focus with `dof: (t) => ({focus: THREE.MathUtils.lerp(near,
  far, ease(t))})` using `focusDistance(camera, object)`. `maxBlur` keeps a very near object from
  smearing the frame.
- **Spend motion blur where the motion is.** Each sample draws the whole scene again (about 0.4 s
  a sample for the example at 720p on 2 cores). Use 3–6 samples on shots with something fast, none
  on slow ones, none in `--draft` (`ctx.width < 640`).
- **Check with stills.** `vidgen still PROJECT --scene ID --at …` at the moments that matter; a
  copy of the scene with `data:` that switches one effect off shows what each one does.
- **Porting a hand-written chain.** Map its passes to options (its tone curve: `"aces-narkowicz"`;
  its `pow(1/2.2)`: `encoding: "gamma2.2"`; its scene scale: `renderScale`), then compare stills:
  a copy of "Escapement" ported this way came within 28–34 dB PSNR of the film (DESIGN §120.11).
- **Let the music drive it.** With `music_data` in the scene's params the page reads the score's
  hits and notes and the measured mix as `ctx.music` (`vidgen guide web`, "Pictures that follow
  the music"; [COOKBOOK-MUSIC.md, section 12](COOKBOOK-MUSIC.md#12-pictures-that-follow-the-score)).
  Put light and colour on the hits and keep the camera on the form (sections), never on a beat.
  Worked example: [`examples/signal-fire`](../examples/signal-fire/README.md), an orchestral cue
  and a finished three.js night scene that follows it, track by track.
- **Space at real scale.** Planets millions of metres apart and a ship of 100 m do not fit one
  depth range or float32 world coordinates. Place them with `vidgen/space-scale` (CONFIG `web`,
  "Astronomical scales"): `update: (t) => space.update(t, view(t))` for `Finish`; three.js's
  units are then metres (`dof.unit` stays 1). When the focus is far away (a planet behind a near
  ship), give the same focus as `dofFocus`. Bloom and motion blur need nothing more.

## 9. Building blocks for music videos

Three music films were drawn as `web` scenes and each wrote the same parts by hand. Those parts
ship as two modules (reference: [CONFIG, `web`](CONFIG.md#web), "Building blocks for music
videos"; `vidgen guide web` has a page built from them): `vidgen/music-time` reads the music (the
score's tracks as arrays, envelopes of hits and notes, the melody's pitch, bar lengths, seeded
numbers, easing, keyframes) and `vidgen/three-kit` draws light on black (glowing strokes, glass
crystals, a tesseract, a nebula sky, portals, star fields, flares, shock rings, the melody's
ribbon, the spectrum's rays, tunnels, a corridor, great rings, swarms, dust). The worked example
is [`examples/parallel-space`](../examples/parallel-space/README.md): every scene of the film is
composed from them in `ps.js`.

- **One script, one song time.** All scenes of a film can share one script that picks its set
  from `data.mode`; each draws from `T = ctx.music.time(t)` alone, so a cut between two scenes on
  a bar line is invisible and scenes render in any order.
- **Hits are light.** `hitEnvelope(song.hits.kick, T, 0.1)` into `lightCrystal`, a `Glow`'s
  `tint`, a flare's intensity or `updateTesseract`'s gain; a camera that moves on a beat, or a
  shape that grows on it, looks like a fault. Notes leave glints (`updateGlints`), the melody a
  ribbon (`updateRibbon`), the spectrum rays (`updateSpectrumRays`).
- **Line widths are pixels.** A `Glow` keeps a width in 720p pixels (`px`) at any size of frame,
  and grows with nearness only with `world`; it is cut at the camera's near plane, so a segment
  that passes the camera does not sweep through the frame.
- **Bloom makes them glow.** The strokes add light; finish with `vidgen/three-finish` (`bloom`
  with a threshold under 1) or your own composer, as `examples/parallel-space` does.
- **Seeds, not `Math.random`.** `makeStarField(n, …, seed)`, `rng(seed)` and `hash(i, k)` give the
  same picture every render; change a seed to try another sky.
- **Porting your own film to them.** Move a piece only when stills stay the same: `vidgen still`
  before and after at a few times per scene and compare the PNGs. `examples/parallel-space`,
  `examples/escapement` and `examples/signal-fire` were ported this way with pixel-identical
  stills (Parallel Space then moved to `music_data`, whose spectrum is measured from the mix:
  53.5 dB PSNR or closer); what would have changed a picture (Escapement's watch, studio and
  finishing) stayed in the film's script.
- **A line of notes keeps its light.** `melody(track, T)` starts each note's 0.05 s attack from
  the level the note before has at that moment, so a legato line does not dim for a frame on
  every note; `noteLevel` starts each note from 0 (a swell per note), `noteEnvelope` from 1 (a glint).

## 10. From a score to a music video

The example films were cut by hand: their authors read the score, found the sections, split the
long ones, chose a colour and a set for each and the tracks each set answers. `vidgen music plan`
does that first pass from the score file itself (reference: [CONFIG, "A music video from a
score"](CONFIG.md#a-music-video-from-a-score-vidgen-music-plan)), without playing it:

```bash
vidgen music plan assets/music/my_song.yaml                 # read the plan first
vidgen music plan assets/music/my_song.yaml --out my_video  # then draft the project
vidgen still my_video --scene 05_drop --at 2 --size 640x360
```

```text
scenes (12, cut on bar lines; durations at 30 fps):
  01_winding         0.00 s  bars 1-8      16.00 s  intro     drift  #477bba / #d88d78
                    reacts to brightness pulse: boom; glints: box, tock; glow level: brass
  ...
  08_orrery_2      112.00 s  bars 57-60     8.00 s  breakdown dust   #4845a5 / #d5ba7c
                    breath at bar 60 (118.00 s): 3 new notes between 9 and 42
                    why: longer than 16 s: split at bar 57 (change 0.41)
```

- **Read the plan before the draft.** Each section's role says why (its name, or its energy
  against its neighbours); each cut says why (a whole section, too long, the material changes).
  A section named `drop` that is quiet is still called a drop: rename it or change the role in
  the draft's `data`.
- **The cuts are the film's grid.** Every scene lasts whole frames from one bar line to the next,
  and every page draws from song time (`ctx.music.time(t)`), so the cut between two scenes falls
  on the beat and nothing jumps. Join or split scenes on bar lines only (a 16-bar section of a
  120 BPM song: two scenes of 16 s); keep scenes under about 16 s, or give a long one a camera
  move that changes the view.
- **One look per role, then make it yours.** The draft gives each role a starter page (a nebula
  flight for the intro, a tesseract for a verse, a tunnel for a build, a crystal swarm for a drop,
  rings and rays for the climax, dust for a break, a ribbon for the end), coloured from the colour
  script: cool and sparse at the start, warm and saturated at the peak, calm at the end. The
  pages are short and use the kit's parts; replace a set, keep its `update(t)` drawing from `T`.
- **Reactions are light.** `reactions(ctx.music, data.react)` gives `pulse(T)` (the kick's light),
  `glow(T)` (the pad), the glints' notes and the rings' hits; the starters feed them to
  brightness, glints and rings, never to the camera or a size.
- **What it does not know.** The plan reads notes, not sound: a track made loud by its mix, a
  lyric, a story. Watch a still per scene (`vidgen still --count 3`), then a `--draft` render.

For the three film scores the plan is close to what their authors cut: `escapement` and
`signal-fire` exactly (12 and 3 scenes on the same bars), `parallel-space` with two more cuts (it
splits the 16-bar `pulse` and keeps `heart` and `heart2` apart, where the film shows 16-bar
scenes); DESIGN §121.2 has the tables.


## 11. Checking a music video

A still shows one frame; a music video goes wrong between frames: a shader that returns NaN for
a moment draws black frames (Parallel Space v7 had 20 of them), an envelope that restarts at zero
dips the light for one frame, a spinning wheel strobes. Watching three minutes for that is slow and
easy to miss. `vidgen motion check` watches for you (reference: [CONFIG, "Motion
check"](CONFIG.md#motion-check-vidgen-motion-check)):

```bash
vidgen render my_video --draft                   # or the final render you are about to publish
vidgen motion check my_video --draft             # its rendered video, about 10 s a minute
vidgen motion check output/my_video.mp4          # any file
```

- **Read the errors first.** `blank` inside a scene is a frame that failed to draw: open the
  strip, find the scene and time, then `vidgen still my_video --scene ID --at SECONDS` to see the
  page at that moment, and look for a division by zero, a `normalize` of a zero vector or a
  `pow` of a negative number in the shaders.
- **Warnings are worth a look.** A one-frame `flash` or drop-out that does not fall on a hit or
  note is often a camera passing through an object, a value jumping on a section boundary or a
  reaction without its attack; `flicker` is something oscillating every frame or two (a value
  that changes sign, two layers fighting at one depth); `pop` a part shown for one or two frames;
  `strobe` a pattern turning about half its repeat a frame (slow it, or blur it).
- **Info is the music doing its job.** Flashes, pops and pulses that start on the score's drum
  hits and note starts are listed as info (a pulse that rises on the kick and decays over a few
  frames is not reported at all). A light that drops for one frame on every note of a line is
  still worth a look in the strip: an envelope that starts at 0 dims the picture on each note.
  `frozen` is a held title, or a page whose clock stopped; `cut_jump` a hard change of brightness
  across a cut, deliberate or not.
- **Before the final render**, check the scene clips you have: `--source scenes` reads the clips
  in `build/` (cut to cut) when the whole video is not rendered yet.

On the two finished example films: Parallel Space v7 (fixed) has no blank frames; one warning (a
tunnel ring passing the camera brightens one frame in `06_build`) and 21 infos (seven cuts with
jumps in brightness, eleven flashes and dips on notes and hits, among them one-frame dips on the
`hook` notes in `05_heart`, a small glint, two held frames in the coda; the dips came from the
kit's `melody` restarting each note's light at 0, fixed since: a still on such a note keeps the
light of the frames around it); Escapement has none above
info (seven cut jumps, small glints in its gears, the still opening on the watch while the title
fades in, and the held ending).

## 12. Opening titles and end cards for films

A film can open the way a cinema film does: the picture comes up from black, and for a few bars a
small title sits beside its subject before the film begins; at the end the same type comes back
on the other side. `examples/escapement` does this (its first scene, `01_winding`, and its last,
`12_coda`). The rules it follows:

- **Asymmetry.** The title block sits in the left or the right third of the frame; the subject
  (the watch, the object, the landscape) fills the other side. Never centred on the subject, never
  over it. The end card mirrors the opening: if the title was on the left with the subject on the
  right, the end card is on the right with the subject on the left.
- **Restraint.** A small title (about 4 % of the frame's width) with wide letter spacing, a thin
  rule under it, one quiet subtitle in small capitals. Nothing else on screen: no logo, no
  credits, no web address in the opening, no animation of the letters beyond a slow opening of
  their spacing.
- **Quiet space behind the text.** Dark, calm negative space: the subject is lit, the side the text
  is on is not. Where the picture is busy there, a soft dark gradient from that edge of the frame
  calms it (on by default in the ready-made card below).
- **Slow timing.** Let the picture start alone for a bar or so; fade the title in over the next
  bars, let it settle while the subject settles, hold it, and fade it out before the first cut
  (Escapement: in over bars 2–3, held, out over bars 7–8 of an 8-bar opening).
- **A matching end card.** The same typeface, colours and layout, a little smaller, on the other
  side: the title, the rule, a subtitle, and the credits small (a line or two in italics). Hold it
  to the end and let it fade with the picture.
- **When not to.** Shorts and quick explainers start moving on frame 1: a viewer scrolling past
  decides in the first second, and a title card there is a second of nothing. Keep a title card for
  films watched from the start (a music video, a short film, a long explainer's chapter opening),
  and say the title in the first moving shot otherwise.

**The ready-made card: `vidgen/title-cards`.** A module you import by name gives both cards as
HTML text over the page (crisp at every size, not drawn by WebGL), laid out as Escapement's, with
its timing and colours as defaults (reference: [CONFIG, `web`](CONFIG.md#web), "Opening titles and
end cards"):

```js
// extensions/film.js: the opening scene (data.mode "opening") and the last ("ending") of one script
import {titleCard, endCard} from "vidgen/title-cards";
let card;
export async function load(ctx) {
  // ... the three.js scene, its subject on the right in the opening, on the left at the end ...
  card = ctx.data.mode === "opening"
    ? await titleCard(ctx, {title: "TIDEWATER", subtitle: "a film in four tides"})            // left; in at 2 s, out by 14 s
    : await endCard(ctx, {title: "TIDEWATER", subtitle: "music and pictures by ...", start: 8,  // right; holds to the end
        lines: ["The score is played by vidgen's own synthesizer."]});
}
export function frame(t, ctx) {
  card.update(t);              // its opacity from t alone (fade in, hold, fade out)
  // ... draw the scene at t ...
}
```

- **Time.** `start`, `fadeIn`, `hold`, `fadeOut` in the seconds `frame(t)` gets (defaults: 2, 2,
  8, 2 for the title, so it is gone by 14 s of a 16 s opening; the end card fades in over 2.5 s
  from 1 s and holds to the end). On a 120 BPM song a bar is 2 s: put `start` and the fades on bar
  lines. Pass song time instead if you give `start` in song time.
- **Place.** `side: "left"` (the title's default) or `"right"` (the end card's); in a portrait
  frame both go to the lower part (`"top"` for the upper), left- or right-aligned by `align`. Sizes
  follow the frame (1 % of a 16:9 frame's width, 1.7 % of a portrait frame's), a title too wide for
  its side is set smaller until it fits, and the margins keep the text off the frame's edges.
- **Look.** `font` (the theme's serif), `subFont` (the theme's body font), `color`, `subColor`,
  `accent` (the rule), `glow` (a soft halo, `false` for none), `size`, `tracking` and `settle`
  (how far the spacing opens while the card shows), `rule`, `shade` (the gradient's strength,
  `false` for none), and on the end card `link` (one line in the theme's monospace) and `lines`.
  A misspelt option stops the render with the reason (`unknown option "fadein" (did you mean
  "fadeIn"?)`).
- **Lint.** The cards are real text, so `vidgen lint` reads them (by `data-vidgen-id`
  `title-card` / `end-card`); `min_font` is off for them, since the small subtitle is meant.
- **Shade on a flat background.** On an even, very dark picture the gradient can show 8-bit steps
  one level apart; a little grain (three-finish's `grain`) hides them, or set `shade: false` where
  the picture is already dark there.
