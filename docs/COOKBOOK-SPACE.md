# Space cookbook: craft notes for space films with schu-video-generator

For an AI agent or a person making space shots with the generator: a sunrise over a planet, a
ringed world as a crescent, a ship on a real transfer, a fly-by, a powers-of-ten zoom, a black
hole, a comet, a jump to warp, a craft of your own parts; giant ships a pass along their hull, a
craft into a bay, a fleet. The `space` scene writes all of these in `video.yaml` alone; this
cookbook is about choosing what to show, keeping the picture honest, what each shot costs, and
how to check it before a render. **In the air** (a skim over the sea, a plane over a range, a climb
through a cloud deck, a descent from orbit) is its own cookbook: [COOKBOOK-AIR.md](COOKBOOK-AIR.md).
The full list of keys is in [CONFIG.md](CONFIG.md#space), the short form in the author guide
(`vidgen guide space-scenes`), a whole film to copy from in
[examples/outbound](../examples/outbound/README.md) (58 s, five scenes cut on bar lines, an
original score), the scenes playing in the [web scene gallery](gallery/web/README.md). Orbits as
diagrams (the flat `orbit` scene, Δv, launch windows, the units to say) are in [COOKBOOK-ORBITS.md](COOKBOOK-ORBITS.md); three.js pages of your own, finishing and music
videos in [COOKBOOK-3D.md](COOKBOOK-3D.md).

Contents: [1. Choose what to show](#1-choose-what-to-show) ·
[2. Honest scale and honest exposure](#2-honest-scale-and-honest-exposure) ·
[3. Orbital scenes](#3-orbital-scenes) · [4. Giant ships](#4-giant-ships) · [5. Camera moves](#5-camera-moves) ·
[6. In the air](#6-in-the-air) · [7. What YAML does not reach](#7-what-yaml-does-not-reach) ·
[8. What a shot costs](#8-what-a-shot-costs) · [9. The checks to run](#9-the-checks-to-run) ·
[10. Common mistakes and their messages](#10-common-mistakes-and-their-messages) ·
[11. Where the numbers come from](#11-where-the-numbers-come-from)

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
  `--kind light`, `--kind craft`, `--kind phenomenon`, `--kind camera` (and for the air `--kind air`,
  `sea`, `cloud`, `land`, `effect`; `vidgen parts 'plane-*' 'hull-*'`) draw labelled contact sheets.

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

## 3. Orbital scenes

Each recipe is a whole scene for `scenes:` and validates as it stands (`tests/test_docs.py`); the
numbers are the ones drawn for this cookbook (stills at 480x270 and 1280x720). Times are seconds of
the scene unless they are bars. An orbital scene has no `world:`; it may have `orbits:` (true
positions and timing), `bodies:`, `craft:`, `phenomena:`. Every `space` scene is filmed by the
default camera look `camera` (Step 401: sensor noise, a short dynamic range, light sharpening, the
lens's bend, faint fringes and halation; nobody holding it), so space scenes look different from
before; `camera_look: none` gives the clean render of before.

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

**The same sunrise through a spacecraft's window.** `camera_look: window_handheld` (Step 400) is
handheld footage through glass: a calm braced hand and a horizon a degree off at the start, the
camera's noise, a short dynamic range (the sun clips into a round white core), a warm halation and
a wide bloom round it, the glass's veil lifting the black a little, darker corners, the lens's bend.
An orbital scene has no meter, so the look's automatic exposure is left out here. Any of its options
can be given over it: `finish: {vignette: 0.2}`, `operator: {horizon: false}`.

```yaml
- id: sunrise_window
  type: space
  duration: 8
  params:
    sky: {seed: 7, look: rich}
    bodies: [{name: Earth}]
    camera: {move: reveal, behind: Earth, at: 4, rate: 1.0, air: 0.1, lens: wide-normal}
    camera_look: window_handheld
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

**A craft of your own parts** (the craft kit's parts): the root part, then parts attached at its
points (`fore`, `aft`, `port`, `starboard`, `zenith`, `nadir`, `tip`, or `{angle, along, out}`) or in
a ring (`around`).

```yaml
- id: kit
  type: space
  duration: 8
  params:
    sun: {direction: [1, 0.3, 0.4]}
    craft:
      - name: Mine
        seed: 3
        at: [0, 0, 0]
        parts:
          part: hull
          shape: prism
          sides: 8
          radius: 1
          length: 1.4
          skin: foil
          attach:
            - {at: fore, part: dish, diameter: 3}
            - {around: {count: 2, along: 0.5}, part: solar-wing, panels: 3}
            - {at: aft, part: engine, exit: 0.3, kind: chemical}
    camera: {move: arc, subject: Mine, phase: [three-quarter, half], distance: 14, lens: normal}
```

**A jump across a cut, with a flash on it.** Give the same bar to the scene before the cut and the
scene after it: the warp's progress (`warpCut`) and the flash (`flashCut`) are each one curve across
the cut. A match cut inside a scene: `{move: arc, subject: Moon, match: Earth, cut: true}` places the
Moon as the Earth's disc was in the move before.

```yaml
- id: across
  type: space
  duration: 6.4
  params:
    music_data: true
    fade: false
    craft: [{name: Ship, kind: ship, at: [0, 0, 0], velocity: [0, 20000, 0], throttle: 1}]
    phenomena: [{kind: warp, name: Jump, cut: {at: bar 3, seconds: 3}}]
    flash: [{at: bar 3, amount: 2}]
    camera: {move: follow, subject: Ship, view: chase}
```

## 4. Giant ships

Hulls 0.5 to 10 km long from a family and a seed (`spine`, `carrier`, `cluster`, `lance`, `wheel`,
`ark`, `twin`), dressed with plating, windows by the thousand, lit bays and lamps (`dress:`); a craft
of the kit beside one tells its size (`scale_ref:`). They are invented designs and must stay so: no
copy of a ship from any film or game. Look first: `vidgen parts 'hull-*'`. Stated looks: windows are
dimmed where the sun lights the wall and lifted under a pixel in the film exposure; the bank plume is
one soft beam a bank (`plumes: bank`).

**A giant ship: a pass along its hull, then a craft into a bay** (1.55 s and 1.6 s a frame). A 16 mm
lens 60 m off the port wall at 40 m/s: plates, windows and a hangar's mouth stream past while the
wall runs to a vanishing point; then a 50 m craft of the kit flies into hangar 2 and shrinks to a
speck against the mouth. A 3 km ship takes 80 s at that speed: show 15 or 20 s of it. vidgen sets
the view's near plane to 4 m when a hull is in the scene (depth precision beside the hull). Families: `spine`, `carrier`, `cluster`, `lance`, `wheel`, `ark`,
`twin`, another ship for every seed; look first: `vidgen parts 'hull-*'`.

```yaml
- id: carrier
  type: space
  duration: 16
  params:
    orbits: {central: earth, speedup: 1, bodies: [{name: Carrier, altitude: 900 km}]}
    bodies: [{name: Earth}]
    sun: {direction: [0.3, 0.25, 0.9]}
    craft:
      - name: Carrier
        hull: carrier
        seed: 1
        length: 3200
        dress: {plumes: bank}
        scale_ref: {kind: ship, at: hangar-2, into: {hangar: hangar-2, over: [8, 16]}}
    camera:
      - {move: hull-pass, ship: Carrier, over: [0, 8], side: port, standoff: 60, from: 0.3, speed: 40}
      - {move: into-bay, ship: Carrier, hangar: hangar-2, over: [8, 16], cut: true}
```

**Powers of ten from a hangar to the world** (0.8 s a frame): from 80 m off the bay's mouth to the
whole ship to the ship as a speck by its world.

```yaml
- id: powers
  type: space
  duration: 8
  params:
    orbits: {central: earth, speedup: 1, bodies: [{name: Ship, altitude: 900 km}]}
    bodies: [{name: Earth}]
    craft: [{name: Ship, hull: carrier, seed: 1, length: 3200}]
    camera: {move: scale-zoom, ship: Ship, window: hangar-2, close: 80, world: Earth}
```

**The bank lighting on a bar, the windows on the music** (2.1 s a frame with eight bells). The
camera creeps in behind the bells until `light`, then is pushed back as they fire; the hull's
throttle follows the shot. `dress: {plumes: bank}` draws one plume per bank (cheaper).

```yaml
- id: burn
  type: space
  duration: 8
  params:
    music_data: true
    orbits: {central: earth, speedup: 1, bodies: [{name: Ship, altitude: 900 km}]}
    bodies: [{name: Earth}]
    craft: [{name: Ship, hull: lance, seed: 2, dress: {plumes: bank}}]
    camera: {move: stern-burn, ship: Ship, light: bar 3, shake: {amount: 0.3}}
    music: [{track: level, glow: Ship, as: lights}]
```

**A reveal: the ship keeps coming** (0.45 s a frame while only the bow is in frame, 1.1 s with the
hull overhead). The bow slides in over the top of the frame at `at` and the hull keeps coming for
its length over a thirtieth of it a second; the small craft (`escort: true`) enters last, after the
stern. Hold the shot for all of it: the size is told by the time it takes.

```yaml
- id: reveal
  type: space
  duration: 40
  params:
    orbits: {central: earth, speedup: 1, bodies: [{name: Ark, altitude: 1200 km}]}
    bodies: [{name: Earth}]
    craft: [{name: Ark, hull: ark, seed: 3, dress: true, scale_ref: {kind: ship, at: bottom, seed: 2, escort: true}}]
    camera: {move: hull-reveal, ship: Ark, at: 3, lane: 200}
```

**A fleet**: one palette and one accent (one maker); keep one hull near the lens, the rest behind it.
Five dressed hulls at `far` detail: 0.9 s a frame.

```yaml
- id: fleet
  type: space
  duration: 10
  params:
    sky: {seed: 6}
    sun: {direction: [1, -0.4, 0.3]}
    craft: [{name: Fleet, hull: [carrier, spine, twin, lance, cluster], fleet: 5, seed: 3, spacing: 2600, at: [0, 0, 0]}]
    camera: {move: arc, subject: Fleet, phase: [three-quarter, half], distance: 30000, lens: long}
```

## 5. Camera moves

| moves | for | recipes |
|---|---|---|
| `arc`, `follow`, `fly-by`, `pass`, `arrive`, `reveal`, `zoom`, `look` | worlds, craft and phenomena in an orbital scene | sunrise, crescent, depart, flyby, zoom, hole, comet, jump, kit, across, fleet |
| `hull-pass`, `hull-reveal`, `into-bay`, `stern-burn`, `scale-zoom` | beside a giant ship (`ship:` names it) | carrier, powers, burn, reveal |
| `skim`, `climb-through`, `descend-through`, `chase`, `wing`, `fly-past`, `orbit-peak`, `rise`, `descend`, `ascend` | a surface scene (`world:`) | [COOKBOOK-AIR.md](COOKBOOK-AIR.md) |

Moves are kebab-case (`hull-pass`; camelCase is accepted). Several moves are a list with `over`
each; where two meet without `cut: true` the second must start where the first leaves the camera
(the page stops otherwise). Times are seconds or bars (`over: ['bar 3', 'bar 5']` with
`music_data`). `match: Earth` with `cut: true` places the next subject as the last one was on
screen (a match cut inside a scene).

## 6. In the air

A `space` scene with `world:` is a **surface scene**: one world from orbit to the ground in the
place's own frame, with its air, sea, ground and cloud decks, flights planned in Python and planes
flying them, and the air moves above. Its recipes (a dusk at sea, a skim, a volcano, a climb through
a deck, a chase, a wingtip view, a fly-past, the descent from orbit), what is true and what is a
look there, and the two pages that still need code are in [COOKBOOK-AIR.md](COOKBOOK-AIR.md). Its
costs are in the one table below. Any `space` scene can add a camera operator over its moves,
off unless given: `operator: {hand: handheld, horizon: true}` (a person's drift, late corrections and a
horizon a degree off at each cut; `hand: mounted` only vibrates), and in a surface scene `exposure: true`
(an automatic exposure that lags and hunts).

**Camera looks** (`camera_look:`, Steps 400–401, DESIGN §124.4–124.5): one word for a matched
finish and operator, the scene's own `finish:` and `operator:` over it key by key (a number sets a
group's main value: `finish: {noise: 0.006}`; `false` turns a group off). Without `camera_look:` a scene
gets `camera`; `camera_look: none` is the clean render (as before Step 401).

| look | for | what it adds |
|---|---|---|
| `camera` (the default) | every scene that names none | the sensor and the lens only: fine noise, 2.8 stops of range, light sharpening, the lens's own bend, faint fringes towards the corners, a faint warm halation, a light vignette (0.2); no hand, no horizon error, no automatic exposure |
| `window_handheld` | the view from a cabin | a braced hand, a gentle meter, the horizon 0.8° off; noise, 2 stops of range, the glass's veil, wide bloom, warm halation, heavy corners, the lens's bend |
| `drone` | a sweep over sea or ground | gimbal vibration, a smooth meter; fine noise, 2.4 stops, crisp, a little saturated, the wide lens's bend and fringes |
| `broadcast_long_lens` | a launch or a ship seen from far away (give the moves `lens: long` or `tele`) | a heavy head's slow sway, the iris ridden slowly; a big sensor's fine noise, 2.8 stops with a soft knee, strong detail halos, long-lens colour fringes |
| `phone` | someone filming by hand | a light hand, a quick meter that hunts, the horizon 1.5° off; blotchy noise, heavy sharpening, punchy colour, lifted blacks |
| `chase_mount` | a camera bolted to the craft or a chase plane | the engine's vibration, an automatic exposure; the ultra-wide bend with soft fringed corners, contrasty, 2 stops |

The full settings are in CONFIG.md (`space`). Orbital scenes leave the looks' automatic exposure out;
motion blur stays the scene's (`finish: {motion_blur: 3}`). Before and after on four views: the
cloud tops of a rise clip near white with every look, the glitter into a low sun blows out wide
with `drone` (`range: 3` keeps a little more), and `phone` is the loudest (turn its noise down if it shows).

## 7. What YAML does not reach

`vidgen space-page . --scene ID` writes any `space` scene out as a `web` scene's script to go on
from. In the air: a sun that moves through a scene and a re-entry from orbit
([COOKBOOK-AIR.md](COOKBOOK-AIR.md#what-yaml-does-not-reach-in-the-air)). Beside a ship:

*A giant ship with the camera in its own axes*: the moves above place
the camera from the hull's regions; for a place of your own (x port, y up, z the bow):

```js
import {SpaceView} from "vidgen/space-scale";
import {planet} from "vidgen/space-bodies";
import {star, spaceLight} from "vidgen/space-light";
import {hull} from "vidgen/space-hull";
const space = new SpaceView(ctx, {renderer, scene, camera});
const ship = hull("carrier", {seed: 1, length: 3000}).fly(space, {body: "Ship"});   // bow along the path, deck away from the world
const small = ship.scaleRef("ship", {at: "hangar-1", gap: 120});                    // a 50 m ship of the craft kit, riding along
const earth = planet(renderer, "Earth", {space});                                   // a body of the orbit data (not an object placed by hand)
const sun = star(renderer, "sun", {direction: [1, 0.3, 0.2]}); scene.add(sun.object);
const light = spaceLight({scene, camera, renderer, sun, bodies: [earth], at: ship.object, shadows: ship.shadows});
ship.shade(sun);
// frame(t): the camera's place in the ship's own axes (x port, y up, z the bow), turned into the data's
const own = (a) => { const v = new THREE.Vector3(...a).applyQuaternion(ship.object.quaternion); return [v.x, -v.z, v.y]; };
space.update(t, {from: {body: "Ship", offset: [0, 0, 1000]}, to: "Ship"}); ship.update(t, {sun});   // first the attitude, then the view
space.update(t, {from: {body: "Ship", offset: own([900, 60, 900])}, to: {body: "Ship", offset: own([520, -40, 200])}, up: own([0, 1, 0])});
earth.update(t); ship.update(t, {sun, throttle: 0}); small.update(t, {sun}); sun.update(t); light.update(t);
```

A sun given as a direction stands beyond every world: a ship in the world's shadow is dark, crossing
the terminator it brightens through the air's reddening (`spaceLight`'s own test of the bodies before
the sun; no code of your own).

## 8. What a shot costs

One table (`vidgen/scenes/space_costs.py` holds it; `vidgen lint` estimates a surface or hull
scene from its rows, a test compares the two). Seconds a frame at 1280x720 on 2 cores in headless
Chromium with software GL (SwiftShader); orbital rows through `vidgen/three-finish` with a bloom (the
`space` scene's finish), air rows straight to the canvas (`camera_look: none`); the default camera
look (Step 401) adds the finish's passes, about +0.3 to +0.7 s a frame on a sea-and-cloud view. A render
adds the screenshot and the encoder (about 0.2 s a frame at 720p). Budget a film by adding its
shots: a 60 s film at 30 fps is 1,800 frames, so 0.5 s a frame is 15 minutes, 1.2 s a frame 36
minutes. A draft (`--draft`, 426x240) costs about a fifth.

| what (1280x720, 2 cores) | s / frame |
|---|---|
| the sky alone (stars and the Milky Way) | 0.24–0.30 |
| a world filling the frame, or a close limb | 0.47–0.59 |
| a ringed giant | 0.47 |
| a sun as a disc, a sunrise over a limb | 0.38–0.43 |
| a craft a third of the frame high / filling it | 0.38–0.43 / 0.6–0.9 |
| five engines at full throttle filling the frame | 1.25 |
| a black hole filling the frame (`quality: fast` 1.06) | 1.0–1.25 |
| a wormhole | 0.73 |
| a warp | 0.38 |
| an asteroid field, a belt round a world | 0.30–0.33 |
| a comet | 0.23–0.25 |
| an aurora on an Earth-like world | 0.48–0.59 |
| the air alone (the dome) | 0.2 |
| a sea under the air (a skim) | 1.2 |
| a sea seen from 20 km | 0.65 |
| ground under the air (a range from 2,500 m) | 1.4 |
| cloud decks under the air (fair, from below) | 1.9 |
| between three decks (layers) | 2.7 |
| a giant's decks | 2.4 |
| ground and a sea (a coast) | 2.05 |
| ground under cumulus | 2.5 |
| a sea under cumulus | 3.0 |
| ground, a sea and clouds (not measured: the sum less the dome) | 3.5 |
| a descent from orbit, the globe stage (over 400 km) | 0.75 |
| a descent through the handover (400 km to 2.5 km over sea or decks) | 3.4 |
| a descent over a Mars-like desert (200 km to 500 m) | 1.5–1.7 |
| a plane on top (a third of the frame) | +0.12 |
| a re-entry's glow on top | +0.37 |
| a chase or a wing view over the alpine range | 1.5 |
| a bare hull in a SpaceView (filling the frame, with a sky, a world and a star) | 0.7 |
| a dressed hull filling the frame from 2.5 km | 1.0 |
| a dressed hull covering every pixel, close | 2.0 |
| five dressed hulls at `far` detail | 0.9 |
| hull-pass beside a dressed 3.2 km hull | 1.55 |
| into-bay | 1.6 |
| stern-burn with eight bells | 2.1 |
| hull-reveal (the hull overhead) | 1.1 |
| scale-zoom | 0.8 |

Since Step 395 (cloud decks that never repeat) a frame with decks costs about a quarter more than its row near the sea and two fifths more from 20–60 km up (measured on one rise over a sea under `fair`; the rows are older). Since Step 396 (a sea that does not weave) a frame with a sea costs up to about a fifth more close to a rough or stormy sea, a tenth more over a calm one or from 20 km. `quality: fast` saves about a quarter (the clouds' `fine` is four times dearer); motion blur
(`finish: {motion_blur: 3}`) multiplies a frame by its samples; depth of field adds about a tenth.

**Opening a page** bakes its maps once; vidgen keeps them in the [cache of baked
maps](CONFIG.md#baked-maps-vidgen-cache), so a later page with the same sky or world opens faster
(warm): the sky's cube 5–6 s (warm 3.5 s); a world 2.5–4 s at 512, 9–14 s at 1024, 30 s or more at
2048 (warm 6.3 s); the ground's height maps 9–10 s (warm 8 s for a first still at 1280x720); the
first plane 1.0–1.3 s; a dressed hull 2.1 s (warm 0.9 s); a descent's page 10 s cold, 2.5 to 5.6 s
warm. A page may take 90 s to open before vidgen gives up.

## 9. The checks to run

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

## 10. Common mistakes and their messages

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
| `camera[1] (skim): a skim flies low over ground or water: give world.sea or world.land` | a move needs what the scene lacks | add it to `world:`, or another move |
| `space scene 'chase': flight Plane: at 19.92 s of the flight (leg 1 (descend)) the path is -50.0 m over the ground ...` | the flight goes under the ground or the sea | `follow: {clearance: 300}`, a climb before it, or `lift: true` |
| `camera[1] (hull-pass).standoff: 4 m is closer to the hull than 10 m` | too close for the near plane beside a hull | a larger `standoff` |
| `bodies: is an orbital scene's; this scene has world: (a surface scene)` | a word of the other kind of scene | the message says where its job is done |
| `about 3.5 s a frame at 1280x720 on 2 cores ...` (`vidgen lint`) | a dear combination of parts | `world.quality: fast`, fewer parts in one shot, a shorter scene |

## 11. Where the numbers come from

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
