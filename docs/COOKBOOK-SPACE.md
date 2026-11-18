# Space cookbook: craft notes for space films with schu-video-generator

For an AI agent or a person making space shots with the generator: a sunrise over a planet, a
ringed world as a crescent, a ship on a real transfer, a fly-by, a powers-of-ten zoom, a black
hole, a comet, a jump to warp; in the air, a skim over the sea, a plane over a range, a climb
through a cloud deck, a descent from orbit; a pass along a giant ship and a craft into its bay. The `space` scene writes all of these in `video.yaml` alone; this
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

### In the air and beside giant ships (Steps 381–391, in YAML since Step 392)

Two kinds of `space` scene. With `world:` a **surface scene**: one world from orbit to the ground in
the place's own frame (metres, x east, y up, z south; `vidgen/space-descent`), the air, the sea, the
ground and cloud decks of one planet, the stars behind them, `flights:` (the `flight_data` words of
Step 385; the ground is the world's own) and planes flying them; it is drawn straight to the canvas,
as every number below was measured. Without it an **orbital scene**, which also takes giant ships
(`hull:`), planes (`plane:`) and craft of the kit's own parts (`parts:`). CONFIG has every key
([`space`](CONFIG.md#space)); each recipe here validates (`tests/test_docs.py`).

**A dusk from the sea, rising to the curve of the world.** The air (`vidgen/space-air`) is the one
the same world shows from orbit; a sun 2 degrees up gives the sunset's reds, `film` exposure (the
default) lifts the dusk. `rise` climbs by equal factors in equal times, so the start is slow and the
world falls away at the end; `lens: [normal, wide]` widens with the climb.

```yaml
- id: dusk
  type: space
  duration: 10
  params:
    world: {sea: calm, sun: [2, 255]}
    camera: {move: rise, from: 20, to: 8000, heading: 255, horizon: 0.3, lens: [normal, wide]}
```

The sun's disc is 0.53 degrees across: 7 px in a 640 px frame through a 50 degree lens, so film a
sunset with a long lens if the disc is the subject. From 20 km the horizon lies 4.5 degrees under the
level, from 100 km 10 degrees and it curves. `exposure: camera, ev: 0` shows what a camera set for
daylight sees.

**A skim over the sea at sunset** (1.2 s a frame at 1280x720, 0.18 s in a draft). 14 m over the
water at 90 m/s towards the sun, turning 14 degrees to the right through the move: the horizon rolls
into the turn and back (`horizon: level` keeps it level). The glitter path is narrow on a calm sea
and under a low sun; a `rough` sea shows whitecaps along its crests, a `storm` high waves with dark
troughs and foam streaks; at dusk the near water keeps the sky's colours (looks, stated in DESIGN
§123.4). `quality: fast` draws a smoother sea (other waves than `standard`) for a quarter less.

```yaml
- id: skim
  type: space
  duration: 8
  params:
    world: {sea: {state: breeze, seed: 3}, sun: [5, 300]}
    camera: {move: skim, heading: 284, speed: 90, clearance: 14, turn: 14, lens: wide}
```

**Round a volcano** (1.6 s a frame). The ground (`vidgen/space-land`) is the same world's as the
globe from orbit; `around: {near: [x, z], reach}` finds the highest ground within reach; the circle
rises over ground that stands too near. Over ground give a skim a clearance the ground holds up at
(200 m over a desert, 400 m over the alpine range); from under about 400 m the range looks soft.
`{track: level, glow: lava}` makes the lava glow with the music.

```yaml
- id: volcano
  type: space
  duration: 12
  params:
    world: {land: volcanic, sun: [9, 150]}
    camera: {move: orbit-peak, around: {near: [0, 0], reach: 20000}, radius: 9000, sweep: 30}
```

**A climb through an overcast, lightning on the kick drum** (2.0 s a frame with a sea and two
decks). Under a closed deck the day is grey with a bright line at the horizon; inside it is fog; over
it the deck is a white sea to its own horizon. `adapt: 1` pulls the exposure down a stop as the
camera nears the top (a look) so the break-out is not a white flash. Decks: `fair`, `overcast`,
`layers`, `towers`, `storm` ready-made, or your own; `deck:` names one by index or name.

```yaml
- id: climb
  type: space
  duration: 14
  params:
    music_data: true
    world:
      sea: breeze
      sun: [12, 30]
      clouds:
        seed: 4
        decks: [{type: stratus, base: 1500, top: 2700}, {type: cirrus, base: 12000}]
        towers: 4
        lightning: {track: kick}
    camera: {move: climb-through, deck: 0, heading: 40, adapt: 1}
```

**A plane chased over the range, a contrail behind it** (1.45 s a frame with the alpine ground and
the plane). The flight is planned in Python, checked never to come under the ground (a path into a
mountain is an error naming the time and place, when the frames are made); the camera follows 60 m
behind and 16 m above with a lag, swinging wide in a turn. Contrails form only above 8 to 9 km
(`always: true` anywhere).

```yaml
- id: chase
  type: space
  duration: 20
  params:
    world: {land: alpine, clouds: fair, sun: [24, 250]}
    flights:
      - name: Plane
        start: {x: -6000, z: 2000, above_ground: 600, heading: 70, speed: 140}
        legs:
          - {follow: {clearance: 300}, for: 12}
          - {turn: {by: 60, bank: 35}, follow: {clearance: 300}}
          - {follow: {clearance: 300}, for: 30}
    craft: [{name: Plane, plane: glider, seed: 7, fly: Plane, effects: {contrails: {always: true}}}]
    camera: {move: chase, flight: Plane, lens: wide-normal}
```

**A plane of your own, from its wingtip.** Any part of a ready-made plane's description can be
given (`wing`, `fins`, `body`, `engines`, `cockpit`, `markings`; the wing presets are `delta`,
`double-delta`, `cranked-arrow`, `swept`, `straight`, `ogival`, `stub`, `blended`, `long`). The
`wing` view rides on the plane: the wing and its tip light stand still and the world tilts as it
banks. `vapour` puts mist over the wings in hard turns, a cone near Mach 0.97, only in dense air.
The designs are invented and must stay so: no copy of a real or film vehicle.

```yaml
- id: wingtip
  type: space
  duration: 10
  params:
    world: {sea: rough, clouds: fair, sun: [30, 120]}
    flights:
      - name: Mine
        start: {x: 0, z: 0, height: 1200, heading: 90, speed: 160}
        legs: [{straight: 3}, {turn: {by: 90, bank: 40}}, {straight: 20}]
    craft:
      - name: Mine
        plane: skiff
        seed: 3
        fly: Mine
        wing: {preset: swept, span: 17, sweep: 42, dihedral: 3}
        fins: {type: vee, height: 4}
        scheme: grey
        effects: {exhaust: true, vapour: true}
    camera: {move: wing, flight: Mine, view: wingtip, side: right}
```

**A fly-past seen from the ground** (0.85 s a frame over a sea). The camera stands 3 m over the
water where the plane will pass at 2 s, 100 m to its right, and turns to keep it in frame: a
whip-pan at the pass. `exhaust` gives each bell a flame with a sharp core and shock diamonds low
down (from 45 % throttle).

```yaml
- id: flypast
  type: space
  duration: 6
  params:
    world: {sea: calm, sun: [8, 260]}
    flights:
      - name: Plane
        start: {x: -600, z: 0, height: 40, heading: 90, speed: 300}
        legs: [{straight: 10}]
    craft: [{name: Plane, plane: needle, seed: 2, fly: Plane, throttle: 1, effects: {exhaust: true, vapour: true}}]
    camera: {move: fly-past, flight: Plane, at: 2, closest: 100, side: right, stand: ground, eye: 3}
```

**A giant ship: a pass along its hull, then a craft into a bay** (1.55 s and 1.6 s a frame). A 16 mm
lens 60 m off the port wall at 40 m/s: plates, windows and a hangar's mouth stream past while the
wall runs to a vanishing point; then a 50 m craft of the kit flies into hangar 2 and shrinks to a
speck against the mouth. A 3 km ship takes 80 s at that speed: show 15 or 20 s of it. vidgen sets
the view's near plane to 4 m when a hull is in the scene (closer than that the default slices a
hull and draws the world over it). Families: `spine`, `carrier`, `cluster`, `lance`, `wheel`, `ark`,
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

**From orbit to a skim over the sea, in one shot** (DESIGN §123.13). `descend` comes down by equal
factors of height in equal times and ends moving, level; the `skim` with `continues: true` takes
over there with no cut. Keep ten seconds or more for 400 km.

```yaml
- id: descent
  type: space
  duration: 14
  params:
    world: {planet: earth, at: [8, -150], sun: [38, 250], sea: {state: breeze, seed: 3}, clouds: {sky: fair, seed: 4}}
    camera:
      - {move: descend, over: [0, 10], from: 400 km, to: 300, heading: 300, turn: 30, speed: 90, lens: [normal, wide]}
      - {move: skim, over: [10, 14], continues: true}
```

What happens on the way down, and what a frame costs at 1280x720:

| height | drawn | seconds a frame |
|---|---|---|
| 400 km to 80 km (`globe`) | the globe through the world's air, the stars | 0.75 |
| 80 km to 2.5 km (`handover`) | the sea and the decks near the camera, the globe far off; everything is computed | about 3 |
| under 2.5 km (`local`) | the air, the sea, the decks | 1.8 |

A Mars-like desert is `world: {land: mars, sun: [30, 120]}` with `descend`'s `to: 500` and `speed:
160`. Honest notes for the film: the camera falls far faster than any vehicle; the globe's clouds and
the decks' are not the same clouds, one dissolves into the other; between 150 km and 25 km over a sea
the surface is soft; a thin cirrus deck is a white line on the horizon while the camera passes it.

**A craft of your own parts** (Phase AN's kit, from YAML): the root part, then parts attached at its
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

### What YAML does not reach: three pages in code

`vidgen space-page . --scene ID` writes any `space` scene out as a `web` scene's script to go on
from. Three things need code from the start.

*Things of your own under the air and a sun that moves through the scene* (a time-lapse sunset):

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

*A re-entry from orbit*: a `web` scene with `orbit_data` and `flight_data` whose flight starts
`{orbit: Ship}` with a first leg `{reentry: {to: {height: 12000, speed: 250}}}` (DESIGN §123.7), the
plane flown by `ship.fly(ctx.flight)` and its glow from `vidgen/space-effects`:

```js
import {effects} from "vidgen/space-effects";
const fx = effects(ship, {flight: ctx.flight, name: "Plane", sky, reentry: true, contrails: true, exhaust: true, vapour: true});
scene.add(fx.object);              // trails and the train stay where they were laid
// in frame(t), after ship.update(t, {throttle}) and sky.update(t, {camera}):
fx.update(t);                      // or by hand: fx.update(t, {heating: 0.8, velocity: [6600, 0, 0], height: 75000})
```

`reentry: {full: 0.65}` is the heating shown as the white-pink peak (the 400 km re-entry of DESIGN
§123.7 reaches 0.66); `persist: 14` makes the train glow 14 flight seconds instead of 5. A flight far
from its anchor is lit by the anchor's sun (the scene's +y is not up there).

*A giant ship with the camera in its own axes, and the terminator by hand*: the moves above place
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

A `spaceLight` with a sun given as a direction does not darken the ship in the world's shadow;
do it by hand after `light.update(t)`:

```js
import {sunVisibility} from "vidgen/space-light";
const at = ship.object.getWorldPosition(new THREE.Vector3()), w = earth.object.getWorldPosition(new THREE.Vector3());
const seen = sunVisibility(sun.direction.toArray().map((x) => x * 1e12), Math.tan(0.267 * Math.PI / 180) * 1e12,
  [{at: [w.x - at.x, w.y - at.y, w.z - at.z], radius: earth.object.getWorldScale(new THREE.Vector3()).x, air: null}]);
light.directional.color.setRGB(...seen.fraction);
```

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
| a space plane (`vidgen/space-plane`) on top of the air and the sea / of a world in space: a third of the frame wide / filling it | +0.12 / +0.19 (+0.02 / +0.07 at 320x180; its shadows 0.03 to 0.05 of that) | 1.0–1.3 s for the first plane, under 0.1 s for each later one |
| effects (`vidgen/space-effects`) on top of a plane a third of the frame wide: a re-entry (shock layer, hot surfaces, wake, sparks, train) / the same at `quality: fast` / without hot surfaces / the plane filling the frame | +0.37 / +0.30 / +0.32 / about +0.7 (+0.04 at 320x180) | 0.5 s (shaders, the windward map) |
| exhaust in air, a vapour cone and wing vapour, vapour trails: each, or all three, on a plane over the sea | under +0.05 (inside the scatter; +0.01 at 320x180) | |
| a giant hull (`vidgen/space-hull`) on top of a sky, a world and a star in a `SpaceView`: filling the frame / small in it / `far` detail filling it / a bank of eight bells firing seen from astern | +0.33 / +0.12 / +0.24 / +0.8 (+0.12 / +0.03 at 320x180; its shadows are inside the scatter) | 1.0 s for the first hull, 25 to 110 ms for each more |
| the same hull dressed (`vidgen/space-hull-detail`: maps, windows, bays, clutter, lamps): filling the frame from 2.5 km / small in it / a close view where it covers every pixel / the night side close / eight bells firing (with `plumes: "bank"`) / five dressed hulls at `far` | +0.28 / +0.07 / +0.7 / +0.4 / +0.16 (-0.3) / 0.9 in all (+0.10 and +0.12 at 320x180; the first frame of a page 3 s more) | dressing: 2.1 s with the cache off, 4.2 s cold, 0.9 s warm (`far`: 1.1 / 0.4 s); 4 MB on disk for the first hull, 1 to 3 MB for each more |
| camera moves in the air (`vidgen/space-camera-air`), the whole scene straight to the canvas: `skim` over a sea / over a desert / `climbThrough` with a sea and two decks / `chase` or `wing` over the alpine range with a plane / `flyPast` over a sea / `orbitPeak` round a volcano / `rise` with a sea and fair clouds | 1.2 / 1.5 / 2.0 / 1.5 / 0.85 / 1.6 / 2.1 (0.17 to 0.39 in a draft at 426x240) | 2 s with a sea, 8 to 20 s with a land at 1280x720 |
| camera moves beside a dressed 3.2 km hull over the Earth: `hullPass` / `hullReveal` (the bow, the hull overhead) / `intoBay` / `sternBurn` with eight bells / `scaleZoom` | 1.55 / 0.45, 1.1 / 1.6 / 2.1 / 0.8 (0.20 to 0.44 in a draft at 426x240) | 4 to 5 s warm |
| the joined world (`vidgen/space-descent`), an ocean with decks: from orbit (the globe and the air) / in the handover, 80 km to 2.5 km (everything) / near the surface; a Mars-like desert at 200 km / 20 km / 500 m | 0.75 / 3.1 / 1.8; 1.6 / 1.5 / 1.7 (a draft at 426x240: 0.32 over a whole descent) | page ready 10 s cold, 2.5 to 5.6 s warm; the first frame with ground 6.5 to 10.8 s more |
| `vidgen still` of a whole `space` scene | 1.0–1.7 a still | 8–14 s; Outbound's `02_depart` at 320x180: 13.7 s, warm 7.6 s |
| a `--draft` (426x240, 8 fps) | Outbound's 58 s in 3 minutes | |

**The estimate `vidgen lint` uses** (`space_scene`, from 2 s a frame): one table in code
(`vidgen/scenes/space_costs.py`) that this cookbook prints and a test reads; the rows above,
rounded, for a surface or hull scene's combination of parts (the dearest stretch of the scene; a
quality other than `standard` scales it, motion blur multiplies it):

| what (1280x720, 2 cores) | s / frame |
|---|---|
| the air alone (the dome) | 0.2 |
| a sea under the air (a skim) | 1.2 |
| ground under the air (a range from 2,500 m) | 1.4 |
| cloud decks under the air (fair, from below) | 1.9 |
| between three decks (layers) | 2.7 |
| ground and a sea (a coast) | 2.05 |
| ground under cumulus | 2.5 |
| a sea under cumulus | 3.0 |
| ground, a sea and clouds (not measured: the sum less the dome) | 3.5 |
| a descent through the handover (80 km to 2.5 km over sea or decks) | 3.1 |
| a plane on top (a third of the frame) | +0.12 |
| a re-entry's glow on top | +0.37 |
| a bare hull in a SpaceView (filling the frame, with a sky, a world and a star) | 0.7 |
| a dressed hull filling the frame from 2.5 km | 1.0 |
| hull-pass beside a dressed 3.2 km hull | 1.55 |
| into-bay | 1.6 |
| stern-burn with eight bells | 2.1 |
| hull-reveal (the hull overhead) | 1.1 |
| scale-zoom | 0.8 |

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
| `camera[1] (skim): a skim flies low over ground or water: give world.sea or world.land` | a move needs what the scene lacks | add it to `world:`, or another move |
| `space scene 'chase': flight Plane: at 19.92 s of the flight (leg 1 (descend)) the path is -50.0 m over the ground ...` | the flight goes under the ground or the sea | `follow: {clearance: 300}`, a climb before it, or `lift: true` |
| `camera[1] (hull-pass).standoff: 4 m is closer to the hull than 10 m` | too close for the near plane beside a hull | a larger `standoff` |
| `bodies: is an orbital scene's; this scene has world: (a surface scene)` | a word of the other kind of scene | the message says where its job is done |
| `about 3.5 s a frame at 1280x720 on 2 cores ...` (`vidgen lint`) | a dear combination of parts | `world.quality: fast`, fewer parts in one shot, a shorter scene |

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
