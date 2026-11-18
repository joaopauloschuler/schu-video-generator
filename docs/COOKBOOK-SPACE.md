# Space cookbook: craft notes for space films with schu-video-generator

For an AI agent or a person making space shots with the generator: a sunrise over a planet, a
ringed world as a crescent, a ship on a real transfer, a fly-by, a powers-of-ten zoom, a black
hole, a comet, a jump to warp. The `space` scene writes all of these in `video.yaml` alone; this
cookbook is about choosing what to show, keeping the picture honest, what each shot costs, and
how to check it before a render. The full list of keys is in [CONFIG.md](CONFIG.md#space), the
short form in the author guide (`vidgen guide space-scenes`), a whole film to copy from in
[examples/outbound](../examples/outbound/README.md) (58 s, five scenes cut on bar lines, an
original score), the scene playing in the [web scene gallery](gallery/web/space.md). Orbits as
diagrams (the flat `orbit` scene, Δv, launch windows, the units to say) are in [COOKBOOK-ORBITS.md](COOKBOOK-ORBITS.md); three.js pages of your own, finishing and music
videos in [COOKBOOK-3D.md](COOKBOOK-3D.md).

Contents: [1. Choose what to show](#1-choose-what-to-show) ·
[2. Honest scale and honest exposure](#2-honest-scale-and-honest-exposure) ·
[3. Recipes, one per shot](#3-recipes-one-per-shot) · [4. What a shot costs](#4-what-a-shot-costs) ·
[5. The checks to run](#5-the-checks-to-run) · [6. Common mistakes and their messages](#6-common-mistakes-and-their-messages) ·
[7. Where the numbers come from](#7-where-the-numbers-come-from)

## 1. Choose what to show

- **One subject a shot.** A world, a craft or a phenomenon; the others are its background. A shot
  that wants two subjects is two shots and a cut.
- **Light from the side.** A world lit from behind the camera is a flat disc; a crescent, a
  terminator or a sunrise shows its shape and its air. `phase: three-quarter` or `half` for a
  world, `crescent` or `thin-crescent` for drama; a craft on its sunlit side (`follow` with
  `side: sun`).
- **Near and far together.** Space has no haze, so size alone says distance: a craft in front of
  a world's limb, a moon over a planet. A long lens (`lens: tele`) flattens the two together; a
  wide lens close to a craft makes it loom over a small world.
- **Motion that reads.** At true speed orbits are slow: use `orbits.speedup` (a stated choice:
  "150 times faster than life"), and let the camera carry the motion (`follow`, `fly-by`, `arc`).
  A globe that turns more than 12° a frame strobes (`vidgen lint` says so): give the world
  `spin: locked` or `spin: SECONDS` (a stated artistic rate), or a smaller speed-up.
- **Cut on the music.** With `music_data` every time can be a place in the song (`'bar 9'`,
  `'bar 13 beat 3'`); a scene with `fade: false` cuts straight into the next on a bar line.
- **Look at the parts before you choose.** `vidgen parts --kind body` (worlds), `--kind sky`,
  `--kind light`, `--kind air`, `--kind craft`, `--kind phenomenon`, `--kind camera` draw labelled contact sheets.

## 2. Honest scale and honest exposure

**Positions and timing are true by default.** With `orbits:` every world and craft is where the
orbit model puts it (Kepler orbits, burns, transfers, fly-bys; the planets on a date from JPL's
approximate elements), at its true size. Two departures are allowed, and both are stated:

| choice | how | what it says on screen |
|---|---|---|
| bodies enlarged | `scale: {mode: enlarged, enlarge: 50}` (or `scale: 50`) | "sizes not to scale · bodies enlarged 50×; distances to scale" |
| distances compressed | `scale: log` | "distances compressed (log)" |
| time sped up | `orbits.speedup: 150` | nothing by itself: say it in the narration or a caption ("150 times faster") |
| a burn shown as thrust | `craft: [{burn: {seconds: 2, turn: 3}}]` (the default) | the orbit keeps its exact impulsive Δv; the plume lasts `seconds` of the scene, the nose turns over `turn` seconds and keeps the burn's direction in the flight's own axes (a prograde burn stays prograde at any speed-up) |
| a craft as a marker | `marker: 3` (pixels) | a point of light where the craft is too small to see |

`note: false` leaves the scale's sentence to the narration; `vidgen lint` (`orbit_scale`) warns
when the narration says "to scale" while the scene enlarges or compresses.

**Exposure.** A sunlit world and the stars cannot share a real exposure (the stars are about 20
stops fainter than a sunlit ground). `light: {exposure: film}` (the default) is a film's
convention: the stars stay visible beside a day side, planet-shine is lifted to be seen. Two
honest choices: `exposure: camera` with `ev` (stops over a sunlit ground's: the stars vanish
behind a day side, as in a photograph) and `exposure: auto` (metered from the bodies and the sun
in the frame). The sky's own look is a choice too: `sky: {look: natural}` (the default),
`rich` (a brighter Milky Way and nebulae) or `sparse`; `stars: real` puts the bright stars at
their true places in the orbit data's frame.

**The real sky.** vidgen ships a short hand-written list of 221 well-known bright stars (positions
and magnitudes written from memory, approximate); fainter stars are seeded. It does not ship the
Yale Bright Star Catalogue, which has no formal licence: if you download it yourself (CDS
catalogue V/50), `tools/make_star_catalogue.py PATH/catalog.gz` in a source checkout converts it
into the same star file, every naked-eye star at its place.

## 3. Recipes, one per shot

Each is a whole scene for `scenes:`; the numbers are the ones drawn for this cookbook (stills at
480x270 and 1280x720). Times are seconds of the scene unless they are bars.

**A sunrise over a limb.** The camera rides round the world so that the sun's upper edge meets
the limb exactly at `at` (here 4 s; `at: 'bar 4'` with `music_data`); `air` allows for the air
that holds the first light back (degrees); `rate` is how fast the camera rides (degrees a second).

```yaml
- id: sunrise
  type: space
  duration: 8
  params:
    sky: {seed: 7, look: rich}
    bodies: [{name: Earth}]
    camera: {move: reveal, behind: Earth, at: 4, rate: 1.0, air: 0.1, lens: wide-normal}
```

**A ringed planet as a crescent.** `arc` goes round the subject from one phase to another; the
sun stands where `sun.direction` says (free-standing worlds) or where it really is (with orbits
on a date).

```yaml
- id: crescent
  type: space
  duration: 8
  params:
    sky: {seed: 4}
    sun: {direction: [1, -0.3, 0.25]}
    bodies: [{name: Saturn}]
    camera: {move: arc, subject: Saturn, phase: [half, thin-crescent], distance: {radii: 6}, lens: normal}
```

**A craft on a real transfer, its burn on the beat.** The transfer's departure fires at
`depart` in simulated time; divided by the speed-up it is a time of the scene: 8 min at 150× is
3.2 s, a bar at 75 BPM. A scene that ends before the second burn shows the departure alone. The
Sun is where it really is on the date; `side: sun` keeps the camera on the craft's lit side; a
1024 map gives the world under a low orbit sharper ground (8 s more to open the page).

```yaml
- id: depart
  type: space
  duration: 6.4
  params:
    orbits:
      central: earth
      date: "2027-03-21"
      speedup: 150
      bodies: [{name: Ship, altitude: 900 km}, {preset: geo, name: Geo, nu: 0}]
      transfer: {ship: Ship, to: Geo, depart: "8 min"}
    bodies: [{name: Earth, size: 1024}]
    craft: [{name: Ship, kind: ship, seed: 1}]
    camera: {move: follow, subject: Ship, view: three-quarter, side: sun}
```

**A fly-by.** `orbits.flyby` is a real hyperbola past the planet (patched conics: the planet's
gravity alone near it) in the planet's own frame, x along its motion round the Sun on the date;
the planet's pole and the Sun are turned into that frame, so the rings are tilted to the Sun as
they really are that day. A camera can also fly past a free-standing world: `move: fly-by`.

```yaml
- id: flyby
  type: space
  duration: 8
  params:
    orbits:
      central: saturn
      date: "2033-04-08"
      flyby: {v_inf: "5.44 km/s", altitude: "110000 km", angle: 100, side: behind, name: Ship}
    bodies: [{name: Saturn}]
    craft: [{name: Ship, kind: probe, seed: 2}]
    camera: {move: follow, subject: Ship, view: {direction: [0.3, 1.0, 0.3], distance: 4.5, lens: wide}}
```

**The powers-of-ten zoom.** The camera backs away from the first stop to the last, the distance
multiplied by √10 every second between eased rests; `hold` rests on a stop. Everything is at true
scale, so give a craft a `marker` for the stretch where it is under a pixel.

```yaml
- id: zoom
  type: space
  duration: 12
  params:
    orbits:
      central: earth
      speedup: 20
      bodies: [{name: Ship, altitude: 900 km}, {preset: moon}]
    bodies: [{name: Earth}, {name: Moon}]
    craft: [{name: Ship, kind: station, marker: 3}]
    camera:
      move: zoom
      stops:
        - {subject: Ship, distance: 130}
        - {subject: Earth, distance: {radii: 4.5}, hold: 1}
        - {subject: Earth, distance: 1.0e+9}
```

**A black hole.** A non-rotating hole bends the sky behind it and its disc (its far side seen over
and under the shadow); `size` is the horizon's radius. Fly past it at 20 horizon radii; start
nearer (`before: 2`) for a large hole on the first beat.

```yaml
- id: hole
  type: space
  duration: 10
  params:
    phenomena: [{kind: black-hole, name: Hole, size: 10 km, tilt: 12}]
    camera: {move: fly-by, subject: Hole, closest: {radii: 20}, before: 2, after: 6, side: left, lens: wide-normal}
```

**A comet.** A comet of the orbit data grows with its nearness to the Sun ((1 AU / r)²); its dust
tail bends behind its motion, its ion tail points straight away from the Sun. A comet preset has
no place on a date: give `nu` (the true anomaly, degrees from perihelion).

```yaml
- id: comet
  type: space
  duration: 8
  params:
    orbits:
      central: sun
      date: "1986-02-09"
      speedup: 200000
      bodies: [{preset: halley, name: Halley, nu: -60}]
    phenomena: [{kind: comet, name: Tail, body: Halley}]
    camera: {move: arc, subject: Halley, phase: half, distance: 2.0e+9, lens: normal}
```

**A cut into a warp.** Two moves, the second with `cut: true` (without it the page stops: two
moves must meet where one hands over); the warp's `over` is when the jump runs, and with
`music: [{track: roll, glow: Jump}]` a track raises it.

```yaml
- id: jump
  type: space
  duration: 6
  params:
    craft: [{name: Ship, kind: ship, at: [0, 0, 0], velocity: [0, 20000, 0], throttle: 1}]
    phenomena: [{kind: warp, name: Jump, over: [2, 6]}]
    camera:
      - {move: follow, subject: Ship, view: side, over: [0, 2]}
      - {move: follow, subject: Ship, view: chase, over: [2, 6], cut: true}
```

**A sky from inside the air** (in a `web` scene's script; the `space` scene does not reach it
yet). `vidgen/space-air` draws the sky from within a world's air for any sun and any height, the
sun's disc, the haze on far things and the light for things in the air; the air is the one the same
world shows from orbit. Here a sunset over hills, the sun sinking a degree a second:

```js
// sketch (parts of a page, not a whole file): a sunset from 300 m
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {spaceSky} from "vidgen/space-sky";
const stars = spaceSky(renderer, {seed: 7});
const sky = air(renderer, "earth", {stars, scene});          // "mars": butterscotch days, a blue glow at sunset
scene.add(stars.object, sky.object);
const rock = sky.haze(new THREE.MeshStandardMaterial({color: 0x3a3f36, roughness: 1}));   // far hills fade into the sky
renderer.toneMapping = THREE.ACESFilmicToneMapping;          // only when drawing straight to the canvas
export function frame(t) {
  camera.position.set(0, 300, 0); camera.lookAt(0, 400, -1000);
  sky.update(t, {camera, sun: sunDirection(4 - t, 10)});     // 4 degrees up at the start, twilight after 4 s
  renderer.render(scene, camera);
}
```

Film exposure (the default) lifts the dusk and brings the stars out as the sky darkens;
`exposure: "camera", ev: 0` shows what a camera set for daylight sees. For a height, move the
camera: at 10 km the horizon curves and the sky darkens, above about 70 km (the Earth-like air's
top) it is space with the limb's glow.

Write numbers with an exponent as `1.0e+9` (YAML 1.1 reads `1e9` and `1e+9` as text; vidgen takes such
text as metres too).

## 4. What a shot costs

Measured on 2 cores in headless Chromium with software GL (SwiftShader), 1280x720, through
`vidgen/three-finish` with a bloom (the `space` scene's default), seconds a frame. A render adds
the screenshot and the encoder (about 0.2 s a frame at 720p). Budget a film by adding its shots:
a 60 s film at 30 fps is 1,800 frames, so 0.5 s a frame is 15 minutes, 1.2 s a frame 36 minutes.

The last column is the page's first opening, which bakes the maps; vidgen keeps them (the
[cache of baked maps](CONFIG.md#baked-maps-vidgen-cache)), so a later page with the same sky or
world opens faster: "warm" below is measured with the maps already in the cache (Step 380).

| shot | s / frame | to open the page |
|---|---|---|
| the sky alone (stars and Milky Way) | 0.24–0.30 | 5–6 s (the cube map's bake; 2 s at 640x360); warm 3.5 s |
| a world filling the frame / a close limb | 0.47–0.59 | 2.5–4 s a world (maps 512); 1024: 9–14 s; 2048: 30 s or more; warm 2048: 6.3 s |
| a ringed giant | 0.47 | 2.5 s |
| a sun as a disc / a sunrise over a limb | 0.38–0.43 | 8–9 s with the world |
| a craft a third of the frame high / filling it | 0.38–0.43 / 0.6–0.9 | 1.5 s for the first craft |
| five engines at full throttle filling the frame | 1.25 | |
| a black hole filling the frame | 1.0–1.25 (`quality: fast` 1.06) | 1–2 s |
| a wormhole | 0.73 | 7 s (its second sky) |
| a warp | 0.38 | |
| an asteroid field / a belt round a world | 0.30–0.33 | |
| a comet | 0.23–0.25 | |
| an aurora on an Earth-like world | 0.48–0.59 | |
| the sky from inside the air (`vidgen/space-air`), straight to the canvas | 0.19 (0.013 at 320x180); 0.22 while the sun or the height moves (`quality: fast` 0.20, `fine` 0.30) | 0.3 s (0.2 s with its table in the cache) |
| the same with aerial perspective on a few far things / on a ground filling half the frame | 0.21 / 0.28 | |
| `vidgen still` of a whole `space` scene | 1.0–1.7 a still | 8–14 s; Outbound's `02_depart` at 320x180: 13.7 s, warm 7.6 s |
| a `--draft` (426x240, 8 fps) | Outbound's 58 s in 3 minutes | |

Motion blur (`finish: {motion_blur: 3}`) multiplies a frame by its samples; depth of field adds
about a tenth. A page opens once per render chunk (and per `vidgen still`); a page may take 90 s
to open (a 2048 map takes 30 s on 2 cores; the first page that bakes it about 10 s more, to keep
it; later pages 6 s).

## 5. The checks to run

1. **Choose parts by looking**: `vidgen parts --kind body` (and `sky`, `light`, `air`, `craft`,
   `craft-part`, `phenomenon`, `camera`): a contact sheet of every ready-made part with its one
   line of use.
2. **Validate**: `vidgen validate .` checks every key and name with the closest word, what goes
   with orbits and what without, the order of the moves, times in bars.
3. **Stills at the moments that matter**: `vidgen still . --scene depart --at 3.2 --size
   640x360` (the cut, the burn, the closest pass). The page prints as warnings what only it can
   know: a subject under 3 px, the camera inside a world or too near its ground, a subject behind
   a world, a jump in a move, a craft in a world's shadow or seen from its unlit side, a globe
   turning too fast. Then one still at 1280x720 of the shot you care about most.
4. **Lint**: `vidgen lint .`: a globe turning more than 12° a frame, an enlarged body covering
   another, "to scale" said of an enlarged scene.
5. **A draft**: `vidgen render --draft .` (small and fast), then **`vidgen motion check --draft
   --subject all .`**: black or blank frames inside a scene, flashes, a subject lost in the dark,
   over-exposed discs, banding of dark gradients, shimmering stars. A star field is not a blank
   frame. Stars are followed across a pan and streaks are not counted as stars, so a fly-by's pan
   or a warp gives no `shimmer` warning, at 8 fps too; a `shimmer` warning means small stars that
   really flicker. The warp's entry flash is reported as a `flash`: it is the effect, not a fault.
6. **The full render** last, once the stills and the draft are right.

## 6. Common mistakes and their messages

| you see | it means | do |
|---|---|---|
| `camera: give at least one move, e.g. [{move: arc, subject: Saturn}]` | a `space` scene needs a camera | add a move |
| `unknown option 'tilt' (options: ...)`, `no lens "nomal" (did you mean "normal"?)` | a key or name the module does not have | take the closest word |
| `with a date, 'geo' has no position on that date here ... place it yourself with nu or mean_anomaly` | only the planets are placed by date | give `nu: 0` (degrees) |
| `the transfer's first burn at 87.41 min comes after the scene's span (10 min): ... give transfer.depart a time inside it` | the launch window is later than the scene | `depart: "2 min"`, or a longer span / larger speed-up |
| `span: the scene ends on 2061-06-03, outside 1800-2050` | the planets' elements are valid 1800–2050 | a shorter span or a smaller speed-up |
| `Ship is in Earth's shadow: only its own lights show` | true: the craft is on the night side | another time or place in sunlight (`side: sun` does not help here); `light: {ambient: 0.1}` lifts it (a stated choice) |
| `the camera sees the unlit side of Ship (the sun is 160 degrees round, behind it)` | the sun is behind the craft | `follow` with `side: sun`, or another `view` |
| `Ship is 1.2 px in radius, under 3` | too small to see | come closer, a longer lens, or `marker: 3` |
| `the camera turns 16.7 degrees in one step: a jump in the move` | two moves meet badly or a move starts at a kink | give `cut: true`, or start the next move where the last one ends |
| `camera[2] (follow) does not start where camera[1] (arc) leaves the camera at 4.00 s (the camera jumps ...` (the page stops) | two moves hand over without a cut | `cut: true`, or start the second move where the first ends |
| stars like small crosses, thin rings broken into dots | FXAA in a finish of your own | `finish: {antialias: none}` (the `space` default) |
| `did not return within 90 s` at load | very large maps (`size: 2048` on several worlds) | `size: 1024`, or fewer worlds in the scene (a world already in the cache of baked maps loads in about 6 s) |
| a globe that strobes | it turns too far a frame under the speed-up | `spin: locked` or `spin: 30` (seconds a turn) |

## 7. Where the numbers come from

- **Orbits**: the orbit model of `vidgen.orbits` (two-body Kepler orbits, impulsive burns,
  transfers between circular coplanar orbits, patched-conic fly-bys, n-body runs), the planets on
  a date from JPL's approximate elements (Table 1, valid 1800–2050). Each scene's data lists its
  approximations (`ctx.orbits.approximations`).
- **Rotation** (poles, prime meridians, periods, tilts, radii of the Sun, the planets, the Moon and
  the Galilean moons): the IAU WGCCRE models, **written from memory** of the reports (no network
  in the step that wrote them), checked against the published periods and tilts. Neptune's
  rotation uses the 2009 report's **16.11 h**; the 2015 report may give about 15.97 h. To be
  checked against the reports by a person (DESIGN.md §122.2 has the table).
- **Light**: the stops between a sunlit ground and the sky's look (20), city lights (10), the
  Earth's light on the Moon and the stars' colours by temperature are **from memory and
  arithmetic**, not from a cited source; the worlds' tilts and flattenings too.
- **Stars**: the hand-written list of 221 bright stars (from memory, approximate places to about
  0.1°; `sky.info.approximate` is true); the seeded sky follows the real sky's counts per
  magnitude.
- **Looks** (surfaces, clouds, craft, the black hole's disc colours) are generated from seeds and
  invented; no real image or texture is used, and no real spacecraft is copied.
