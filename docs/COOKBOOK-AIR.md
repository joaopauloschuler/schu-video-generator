# Air cookbook: surface scenes, planes and the descent from orbit

For an AI agent or a person making shots inside an atmosphere with schu-video-generator: a dusk at
sea rising to the curve of the world, a skim over the water, a circle round a volcano, a climb
through a cloud deck with lightning on the music, a plane chased over a mountain range, a fly-past,
a descent from orbit to a skim in one shot. All of them are `space` scenes with `world:` (a
**surface scene**), written in `video.yaml` alone. Orbital scenes, giant ships, the costs of every
shot, the checks to run and the messages are in the [space cookbook](COOKBOOK-SPACE.md); every key
in [CONFIG.md](CONFIG.md#space); the short form in `vidgen guide space-scenes`.

Contents: [1. A surface scene](#1-a-surface-scene) · [2. Sea, ground and clouds](#2-sea-ground-and-clouds) ·
[3. Planes and flights](#3-planes-and-flights) · [4. The descent from orbit](#4-the-descent-from-orbit) ·
[5. True and stated looks](#5-true-and-stated-looks) · [What YAML does not reach in the air](#what-yaml-does-not-reach-in-the-air)

## 1. A surface scene

One world from orbit to the ground in the place's own frame (metres, x east, y up, z south;
`vidgen/space-descent`): `world: {planet, at, sun, air, sea, land, clouds, globe, handover, exposure,
ev, quality}`. The air (`vidgen/space-air`) is the one the same planet shows from orbit, so a cut
from an orbital scene of the same world keeps its colours; the sea, ground and clouds belong to that
world and that place (the ground's continents are the globe's). `sun` is `[elevation, azimuth]` in
degrees or `{date, utc}` (the Earth's Sun at the place then). The stars behind the air are `sky:`.
A surface scene is drawn through `vidgen/three-finish` with the default camera look `camera` (Step
401: the sensor and the lens of a camera, nobody holding it; the scenes look different from before);
`camera_look: none` draws it straight to the canvas as before (the cost table's numbers were measured
so), and `finish:` given with `none` draws it through the finish without a camera. `flights:` are planned in Python (the `flight_data` words: legs,
turns, climbs, following the ground, a landing) and checked never to come under the ground or the
sea; `craft:` with `plane:` flies them. Each recipe validates as it stands (`tests/test_docs.py`).

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

## 2. Sea, ground and clouds

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

**The same skim as drone footage.** `camera_look: drone` turns on a small camera on a gimbal (DESIGN
§124.4): its noise, a short dynamic range, sharpening, the wide lens's bend and soft fringed corners,
vibration and an automatic exposure. Into a low sun its 2.4 stops blow the glitter path flat and
yellow-white, as a small camera does; the scene's own `finish:` goes over the look, and `range: 3`
keeps a little more of it. The other
looks: `window_handheld`, `broadcast_long_lens`, `phone`, `chase_mount` (what each sets: CONFIG.md, `space`).

```yaml
- id: skim_drone
  type: space
  duration: 8
  params:
    world: {sea: {state: breeze, seed: 3}, sun: [5, 300]}
    camera: {move: skim, heading: 284, speed: 90, clearance: 14, turn: 14, lens: wide}
    camera_look: drone
    finish: {range: 3}
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
camera nears the top (a look) so the break-out is not a white flash; `operator: {exposure: true}` instead
(and no `adapt`) is a camera's automatic exposure: it opens up in the dark fog, the break-out flashes white
and the picture settles a stop darker after a small overshoot. Decks: `fair`, `overcast`,
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

## 3. Planes and flights

Six invented planes from one body, one wing and tails (`glider`, `freighter`, `needle`, `lifter`,
`scout`, `skiff`; a seed varies each), and their effects (`effects: {reentry, contrails, exhaust,
vapour}`). The designs are invented and must stay so: no copy of a real or film vehicle. Look first:
`vidgen parts 'plane-*'`, `vidgen parts --kind effect`.

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

## 4. The descent from orbit

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

What is drawn on the way down (`handover: low`, the default over a sea or decks; the costs are rows of
the [one table](COOKBOOK-SPACE.md#8-what-a-shot-costs)):

| height | stage | drawn |
|---|---|---|
| over 400 km | `globe` | the globe through the world's air, the stars |
| 400 km to 2.5 km | `handover` | the sea and the decks near the camera (from about 150 km), the globe far off; everything is computed |
| under 2.5 km | `local` | the air, the sea, the decks |

A Mars-like desert is `world: {land: mars, sun: [30, 120]}` with `descend`'s `to: 500` and `speed:
160`. Honest notes for the film: the camera falls far faster than any vehicle; the globe's clouds and
the decks' are not the same clouds, one dissolves into the other (the decks' cover varies with a broad
weather of their own, not the globe's map); from about 60 km a faint repeat of the decks' pattern can be
seen; a thin cirrus deck is a white line on the horizon while the camera passes it.

## 5. True and stated looks

True by default: the air's colours (one scattering model with ozone; Mars-like dust as a stated
season), the horizon's place and dip, the sea's wave speeds, the ground's relief and colours from the
same world's globe, a flight's path and bank, the sun's place on a date. Stated looks, each said in
DESIGN §123 where it is made:

- the film exposure (`exposure: film`, the default): the dusk is lifted up to 16 stops, the twilight
  arch kept under white; high over the day side the stars and the Milky Way are dimmed to a third;
  `exposure: camera` with `ev` is a camera's honest picture;
- the sea: the glitter seen through a low haze from high up; steep seas with darker troughs and
  lighter crests; near water at dusk keeping the sky's colours; each wave's crests wandering along
  their length (short-crested: no closed rings);
- the clouds: densities a tenth of real cloud's; fine lumps in the shading, not in the shape; a deck's
  cover varying with a broad weather of its own, tens of km across; `adapt` pulling the exposure down
  near a deck's top;
- the operator (`operator:`, off unless given): the hand's drift, corrections, reframes and vibration are
  seeded noise shaped like a person's, not measured; the automatic exposure meters an estimate of the frame's
  brightness from the camera's view, the sun, the decks and the ground (within about a stop of the drawn
  picture's mean on the views it was fitted to), not the picture itself;
- the camera looks (`camera_look:`, `camera` by default): matched sets of the finish's and the operator's
  options chosen by eye on eight views (a rise to 60 km, a skim into the sun, a pass beside a hull, a sunrise
  over a limb; for the default also a night side, a desert at noon, a ship's bay and a calm sea at noon), not
  measured from real cameras; the default's 2.8 stops make bright saturated ground (a Mars-like desert at noon)
  a little more saturated;
- the ground: rock beds on steep faces (layered rock in a canyon); the lava's glow lighting the ground
  beside it; the globe's relief shading from very high up;
- the descent: the camera falls far faster than any vehicle; the globe's clouds and the decks' are not
  the same clouds.

## What YAML does not reach in the air

`vidgen space-page . --scene ID` writes any `space` scene out as a `web` scene's script to go on
from. Two things need code from the start.

*Things of your own under the air, and a sun that moves through the scene* (a time-lapse sunset):

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
