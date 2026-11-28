<!-- topic: three-d (also: 3d, threejs, three.js, 3d-scenes, stand-ins, standins, guide-passes) -->
## 3D: simple scenes with shapes and stand-ins

One scene type, `3d`, draws plain shapes, labels and character stand-ins with one light, seen by
a camera that stands still or moves on words (three.js in headless Chromium; if Chromium is missing, vidgen's error gives the command
`python -m playwright install chromium`). It is for
explaining where things are and what moves where, not for realism. Every param: `docs/CONFIG.md`;
the craft in full: `docs/COOKBOOK-3D.md` in the schu-video-generator repository; a whole example:
`examples/3d-short` (a 9:16 Short of about 15 s: two stand-ins, a ball, four camera moves, captions,
guide passes).

**Building a set.** Scene units, y up, `floor: true` at y 0; a shape is centred on its
`position`, so a box of height 1 stands at `y: 0.5`, a stand-in of height 1.6 at `y: 0.8`. Short,
meaningful `id`s: actions, lint and the mask's colour table use them. `parent:` (written earlier)
makes parts move together; `visible: false` plus `object_show` on a word brings a thing in.

**The camera.** `fov` is across the frame's shorter side, so a 9:16 frame sees much more above and
below: keep the set compact across, the camera close (`fov` 50–56, 5–6 units away), the objects in
the middle band (title on top, captions below). One move per idea, timed to the word that names
the thing: `camera_fly_to` an object (it follows it if it moves), `camera_orbit` 45–90° to show
depth, `camera_dolly` a small push-in, `camera_move` to pull back at the end.

**Stand-ins.** `shape: standin` with a `name` and a theme colour; its nose shows where it faces
(+z unturned, `rotation: [0, 90, 0]` faces +x). `object_walk` (to `[x, z]` or up to an object)
turns it and walks it there; `object_face` turns it to whom it talks to. Give its beats its
`voice`, so lint checks the speaker is on screen.

**Guide passes.** `guide_passes: true` or `all` (or `vidgen render --guide-passes`) also draws `depth`
(near white, far dark grey; one range for the shot, fitted to the objects, or `depth_range`),
`outline` (white edges on black) and `mask` (each object one flat colour from its id, the floor
dark grey, with `<scene>.mask-colors.json`), same frames and camera, beside the 3D clip. Some of
them: `guide_passes: depth`, `depth,mask` or `[depth, mask]`, as `--guide-passes` takes them.
A beat's `generated_shot` on a `3d` scene can send one as its guide video (`guide: depth |
outline | mask`; `true` = the normal 3D view): `vidgen generate inputs --guide` draws it and cuts
`guide.<pass>.mp4` (see the generated video shots below and `docs/COOKBOOK-3D-SCENE-TO-SEEDANCE.md` §6).

**Lint.** `three_d_off_frame` (an object the beat is about is mostly outside the frame) and
`three_d_hidden` (mostly behind a nearer one); look at `vidgen storyboard --per-beat 3` for the
moves mid-beat.

