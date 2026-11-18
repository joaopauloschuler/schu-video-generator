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

Film exposure (the default) lifts the dusk and brings the stars out as the sky darkens: from
sunset to a sun 12 degrees down the sky fades through orange and deep blue without a step, night
by 18 degrees (a time-lapse: a degree every 4 s of film is the real rate times 60). The sun is
0.53 degrees across: 7 px in a 640 px frame through a 50 degree lens, so film a sunset with a long
lens (`fov` 15 to 25) if the disc is the subject.
`exposure: "camera", ev: 0` shows what a camera set for daylight sees. For a height, move the
camera: at 10 km the horizon curves and the sky darkens, above about 70 km (the Earth-like air's
top) it is space with the limb's glow.

**A sea under that sky** (in a `web` scene's script). `vidgen/space-sea` lays water to the
horizon under the air: seeded waves on vidgen's clock, the sky mirrored, the sun's glitter path,
whitecaps when it blows, the horizon where the height puts it. Here a low pass towards a setting
sun, with something riding the water:

```js
// sketch (parts of a page, not a whole file): 12 m over a breeze sea at sunset
import {air, sunDirection} from "vidgen/space-air";
import {sea} from "vidgen/space-sea";
const sky = air(renderer, "earth", {sun: sunDirection(3, 5), scene});
const water = sea(renderer, sky, {state: "breeze", seed: 3});          // "calm", "swell", "rough", "storm"; water: "methane" on an invented world
scene.add(sky.object, water.object);
export function frame(t) {
  camera.position.set(0, 12, -40 * t); camera.lookAt(0, 6, -40 * t - 300);
  sky.update(t, {camera}); water.update(t, {camera});                  // the air first
  buoy.position.set(...water.pointAt(20, -40 * t - 150, t));           // the same waves the picture draws
  renderer.render(scene, camera);
}
```

The glitter path is narrow on a calm sea and under a low sun, a broad column from high up; a
`rough` sea shows whitecaps along its crests, a `storm` high waves with dark troughs and foam streaks; from high up the glitter fades before the horizon, and at dusk (film exposure) the near water keeps the sky's colours: looks, stated in DESIGN §123.4. From 20 km the horizon lies 4.5
degrees under the level, from 100 km 10 degrees and it curves. Keep the camera over the crests
(`water.heightAt(x, z, t)` plus a margin). Away from the origin the world's roundness counts
(3.45 m at 6.6 km): take heights from `water.pointAt` and `water.horizon.height`. `quality:
"fast"` draws a smoother sea (other waves than `standard`) for a quarter to a third less.

**Ground in that sky** (in a `web` scene's script). `vidgen/space-land` draws mountains, deserts,
dunes and crater fields on the world's sphere, the same world's as `vidgen/space-bodies` shows
from orbit; no mesh, so nothing pops.

```js
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {land} from "vidgen/space-land";
let renderer, scene, camera, sky, ground;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000);
  camera = new THREE.PerspectiveCamera(55, ctx.width / ctx.height, 1, 1e8);
  sky = air(renderer, "earth", {sun: sunDirection(9, 150)});          // a low sun: long shadows
  ground = land(renderer, sky, {preset: "alpine"});                   // "mars", "canyon", "dunes", "snow", "volcanic", "airless"
  scene.add(sky.object, ground.object);                               // the dome, then the ground
}
export function frame(t) {
  const x = 150 * t, z = -60 * t, y = ground.heightAt(0, 0) + 2500;   // metres; never under ground.heightAt(x, z)
  camera.position.set(x, y, z); camera.lookAt(x + 980, y - 160, z - 170); camera.updateMatrixWorld();
  sky.update(t, {camera}); ground.update(t, {camera});                // the air first
  renderer.render(scene, camera);
}
```

A coast: `land(renderer, sky, {world: "earth", at: [-11.5, -15.2], mountains: {from: -300, to:
500, base: 0.35, height: 2600, length: 9000}})` and `sea(renderer, sky, {depth: ground.depth})`
added after the ground. Clouds: `clouds(renderer, sky, {sky: "fair", behind: ground.behind})`,
then `ground.shadedBy(weather.shade)`; update the ground before the clouds. A world without
air: `air(renderer, vacuum(RADII.moon), {exposure: "camera", ev: 1.3})`. Another place:
`{world: "mars", at: [latitude, longitude]}`. High views are the strong ones; from under about
400 m the range looks soft (deserts and craters hold from 200 m). Look first: `vidgen parts
--kind land`.

**Clouds in that sky** (in a `web` scene's script). `vidgen/space-clouds` draws cloud decks on
the world's sphere: here a climb through an overcast into the sun, with towers standing through
the deck and lightning in them on the score's kick drum.

```js
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {clouds} from "vidgen/space-clouds";
import {trackArrays} from "vidgen/music-time";
let renderer, scene, camera, sky, weather;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(60, ctx.width / ctx.height, 1, 1e8);
  sky = air(renderer, "earth", {sun: sunDirection(12, 30)});
  const kicks = ctx.music ? trackArrays(ctx.music, {hits: ["kick"]}).hits.kick : [];
  weather = clouds(renderer, sky, {seed: 4, decks: [{type: "stratus", base: 1500, top: 2700}, {type: "cirrus", base: 12000}],
    towers: {count: 4}, lightning: {times: kicks}});
  scene.add(sky.object, weather.object);                               // the dome, then the clouds
}
export function frame(t) {
  camera.position.set(0, 900 + 260 * t, -90 * t);                      // under the deck, through it, over it
  camera.lookAt(0, 900 + 260 * t + 40, -90 * t - 1000);
  sky.update(t, {camera}); weather.update(t, {camera});                // the air first; the same camera
  renderer.render(scene, camera);
}
```

Under a closed deck the day is grey with a bright line at the horizon; inside it is fog; over it
the deck is a white sea to its own horizon (`weather.horizon(0)`), with every swell lit from the
side when the sun is low. `sky: "fair"`, `"overcast"`, `"layers"`, `"towers"` and `"storm"` are
ready-made; `weather.coverAt(deck, x, z, t)` tells a camera path where the gaps are. Over a sea,
`sea(renderer, sky, {shade: weather.shade})` puts the clouds' shadows on the water. A giant of
gas has no ground: `const sky = air(renderer, giantAir("jupiter")); clouds(renderer, sky,
giantSky("jupiter", {scale: sky.model.H}))` with the camera about 1.1 x `sky.model.H` up gives
decks with the bands of the same world in `vidgen/space-bodies` north and south of that
`latitude`, a high haze and the dark below; its heights, its air and the bands' width (40 times
narrower than true, `squeeze`) are a look (DESIGN §123.5).
Things in the scene are drawn in front of every cloud.

**A plane over that ground** (a `web` scene: the path in `video.yaml`, the picture in its
script). The flight is planned in Python with `flight_data:` — terrain following, a banked turn,
a climb — checked never to come under the alpine range, and the page reads it as `ctx.flight`.
Give the page's `land(...)` the same preset (or options) as `ground:`: the frame is the land's.

```yaml
- id: pass
  type: web
  duration: 20
  params:
    script: fly.js
    flight_data:
      ground: {land: alpine}
      flights:
        - name: Plane
          start: {x: -6000, z: 2000, above_ground: 600, heading: 70, speed: 140}
          legs:
            - {follow: {clearance: 300}, for: 12}
            - {turn: {by: 60, bank: 35}, follow: {clearance: 300}}
            - {follow: {clearance: 300}, for: 30}
            - {climb: {to: 5500, rate: 20}, speed: {to: 180}}
```

```js
import * as THREE from "three";
import {air, sunDirection} from "vidgen/space-air";
import {land} from "vidgen/space-land";
import {craft} from "vidgen/space-craft";
let renderer, scene, camera, sky, ground, plane, f;
export function load(ctx) {
  f = ctx.flight;
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: false});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 1, 4e5);
  sky = air(renderer, "earth", {sun: sunDirection(35, 200), scene});   // scene: the sun's and the sky's light are added to it
  ground = land(renderer, sky, {preset: "alpine"});                    // the same ground as flight_data's
  plane = craft("probe", {seed: 1}).fly(f, {flight: "Plane"});         // a stand-in craft (a few metres); its attitude is the flight's
  scene.add(sky.object, ground.object, plane.object);
}
export function frame(t) {
  plane.update(t);                                                     // where the flight is, banked as it turns
  const p = new THREE.Vector3(...f.position("Plane", t)), v = new THREE.Vector3(...f.velocity("Plane", t)).normalize();
  camera.position.copy(p).addScaledVector(v, -24).add(new THREE.Vector3(4, 7, 0)); camera.lookAt(p);   // a chase from behind
  sky.update(t, {camera}); ground.update(t, {camera});
  renderer.render(scene, camera);
}
```

`f.aboveGround("Plane", t)` is what the page's `ground.above(position)` says (to 10⁻⁷ m), `f.mach`,
`f.bank`, `f.load` and `f.heating` drive instruments and effects, and `f.path("Plane")` is the
whole path as a polyline. A path into a mountain is an error when the scene's frames are made
(`vidgen render`, `vidgen still`), naming the time and place (`lift: true` raises the path there instead). Far ground is drawn
a little smoother than `heightAt` (valleys filled at tens of kilometres): keep the camera near the
plane. A start from orbit: `start: {orbit: Ship, at: 'bar 5'}` with the scene's `orbit_data` and a
first leg `{reentry: {to: {height: 12000, speed: 250}}}` (DESIGN §123.7: what is physical, what is
a look).

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
| a sea under that sky (`vidgen/space-sea`), straight to the canvas, with the dome: 50 m up / 20 km up | 1.1 / 0.65 (0.07 / 0.05 at 320x180); `quality: fast` 0.8 / 0.54; `fine` 1.66 / 0.83 | 0.3 s more |
| clouds in that sky (`vidgen/space-clouds`), with the dome: cumulus and cirrus from below / a cloud sea from above / towers through a deck / between three decks / a giant's decks / cumulus over a sea | 1.9 / 1.1 / 1.6 / 2.7 / 2.4 / 3.0 (0.07 to 0.13 at 320x180); `quality: fast` 0.8 / 0.5; `fine` about 8 / 4 | 0.1 s |
| the same, methods tried first (cumulus and cirrus from below): 10 jittered steps a deck at half size / 6 at a third / 16 at full size | 1.6 / 0.68 / 7.8: grain or terraces on every cloud narrower than a step, so not shipped | |
| ground in that sky (`vidgen/space-land`), with the dome: a range from 2,500 m / the same with a sea / under cumulus / airless craters | 1.35 / 2.05 / 2.5 / 1.45 (0.12 at 320x180); `quality: fast` 1.25; a moving sun 2.4 more | the maps: 9–10 s (craters 19 s; from 30 km 7 s; `fast` 2.3 s; 2.4 s at 320x180); the first still 11.8 s without the cache, 14.8 s cold, 8.0 s from the cache (320x180: 3.2 / 4.1 / 2.1 s) |
| the same, the other method measured (rings of a mesh lifted by the same maps, plain shading): 512 x 384 / 1024 x 512 / 2048 x 768 vertices | 0.67 / 1.0 / 2.1 (0.59 at 320x180): an outline of 9 / 4.5 / 2.3 px edges, and the shading still to pay, so not shipped | |
| `vidgen still` of a whole `space` scene | 1.0–1.7 a still | 8–14 s; Outbound's `02_depart` at 320x180: 13.7 s, warm 7.6 s |
| a `--draft` (426x240, 8 fps) | Outbound's 58 s in 3 minutes | |

Motion blur (`finish: {motion_blur: 3}`) multiplies a frame by its samples; depth of field adds
about a tenth. A page opens once per render chunk (and per `vidgen still`); a page may take 90 s
to open (a 2048 map takes 30 s on 2 cores; the first page that bakes it about 10 s more, to keep
it; later pages 6 s).

## 5. The checks to run

1. **Choose parts by looking**: `vidgen parts --kind body` (and `sky`, `light`, `air`, `sea`, `cloud`, `land`, `craft`,
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
