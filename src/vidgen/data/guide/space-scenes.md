<!-- topic: space-scenes (also: space-scene, space-yaml, declarative-space, spacecraft, surface-scenes, giant-ships) -->
## Space scenes without code: the `space` scene

A `space` scene is written in `video.yaml` alone: name a sky, a sun, worlds, craft, phenomena and
camera moves, and vidgen writes the three.js page from its ready-made space parts and draws it as
a `web` scene (`vidgen still`, `--draft`, the cache). Positions and timing are true; enlarging is a
stated choice. Every key is checked by `vidgen validate` with the closest word. The full list of
keys: `docs/CONFIG.md` (`space`); the craft of good space shots (what to show, honest scale and
exposure, a recipe per shot, the cost of each, the checks): `docs/COOKBOOK-SPACE.md` in the
schu-video-generator repository.
A whole film to copy from: `examples/outbound` (58 s, five `space` scenes cut on bar lines, a score).

```yaml
- id: rings                     # a world standing free: sizes in metres or with units, z up
  type: space
  duration: 8
  params:
    sky: {seed: 4, look: rich}
    sun: {direction: [1, -0.3, 0.25]}
    bodies:
      - {name: Saturn}                                          # a ready-made world: its name is enough
      - {name: Titan, world: titan, at: ["1200000 km", "300000 km", "40000 km"]}
    camera: {move: arc, subject: Saturn, phase: [three-quarter, crescent], distance: {radii: 6}, lens: wide-normal}
- id: transfer                  # orbit data: the craft flies a real Hohmann transfer with its burns
  type: space
  duration: 6
  params:
    orbits:
      central: earth
      date: "2026-06-19"        # the Sun is where it really is that day
      speedup: 6000
      bodies: [{name: Ship, altitude: 900 km}, {preset: geo, name: Geo, nu: 0}]
      transfer: {ship: Ship, to: Geo}
    bodies: [{name: Earth}]
    craft: [{name: Ship, kind: ship, seed: 2, burn: {seconds: 0.6, turn: 0.4}}]
    camera: {move: follow, subject: Ship, view: chase, push: 0.8}
- id: horizon                   # a black hole fly-by, then a cut into a jump to warp
  type: space
  duration: 6
  params:
    phenomena:
      - {kind: black-hole, name: Hole, size: 10 km, tilt: 12}
      - {kind: warp, over: [3.5, 6]}
    camera:
      - {move: fly-by, subject: Hole, over: [0, 3.5], closest: {radii: 26}, side: left}
      - {move: look, from: [0, "-2000 km", 0], to: [0, "-3000 km", "50 km"], over: [3.5, 6], cut: true}
```

- **Worlds**: a ready-made one by name (`earth`, `mars`, `saturn`, `moon`, `europa`, `titan`, invented `tempest`,
  `ochre`, `azure`, `verdant`...; `vidgen parts --kind body` shows them) or `type:` (`rocky`, `icy`, `desert`,
  `ocean`, `lava`, `gas`, `ice-giant`) with `seed`, `rings`, `air`. With `orbits:` a world shows the data's body of
  its name; without, give `at` and (for your own) `radius`.
- **Craft**: `kind` `probe`, `satellite`, `station`, `ship`, `lander`, `tug` (invented designs, another per `seed`),
  `fly:` a body of the orbit data (its burns are shown as thrust); a fleet with `fleet: 5`.
- **Camera**: moves one after another, each with `over: [start, end]` in seconds of the scene or bars of the song
  (`['bar 9', 'bar 13']`, with `music_data: true`). `arc` (round a subject to a phase: `crescent`...), `fly-by`,
  `pass` (a craft passes the camera), `arrive`, `reveal` (sunrise over a limb: `behind: Earth, at: 'bar 17'`),
  `follow` (`view: chase`, `lead`, `side`, `shoulder`...; `side: sun` rides on the craft's lit side), `zoom` (powers of ten: `stops`), `look`. A move that
  does not start where the one before left the camera stops the render unless it says `cut: true`.
- **Music**: `music: [{track: kick, pulse: Sun}, {track: pad, glow: Ship}]`: pulses of brightness and glints, a
  craft's throttle; never the camera. Worlds do not pulse.
- **Finish**: no FXAA by default (it breaks stars and thin rings); `depth_of_field: true` focuses on the move's
  subject; `motion_blur: 3` costs three times a frame. A camera's sensor (on by default through the `camera`
  look, below; with `camera_look: none` off unless given): `finish: {noise: true, range: true, sharpen: true}` (sensor noise instead of the grain, highlights that
  clip, faint sharpening halos; about +0.05 s a frame at 1280x720). The lens (the same):
  `finish: {distort: true, edges: true, halation: true}` (barrel distortion from the camera's lens at each
  moment: strong at ultra-wide, none from 50 mm, the corners kept so no border shows; softer, fringed edges; a
  warm glow round bright edges; about +0.06 s a frame at 1280x720).
- **Operator**: the person holding the camera, off unless given: `operator: {hand: handheld, exposure: true,
  horizon: true}` (slow drift with late corrections and a reframe now and then, larger on the screen with a long
  lens; `hand: mounted` only vibrates; an automatic exposure that lags and hunts after the camera breaks out of
  a deck or turns into the sun, surface scenes only; a horizon a degree off at each cut, levelled after 2.5 s).
  Give a climb's `adapt` or `exposure`, not both. Costs nothing measurable a frame.
- **Camera look**: one word for a matched finish and operator. Every `space` scene gets `camera` unless it says
  otherwise (since Step 401 space scenes look different: fine sensor noise, 2.8 stops of range, light
  sharpening, the lens's bend, faint edge fringes and halation, a light vignette; nobody holding the camera);
  `camera_look: none` restores the clean render of before. Named looks add their operator: `window_handheld`
  (handheld through a spacecraft's window), `drone`, `broadcast_long_lens` (give the moves a long lens),
  `phone`, `chase_mount` (bolted to the craft). Your own `finish:` and `operator:` go over it key by key
  (`finish: {noise: 0.006, range: 3}`, `operator: {horizon: false}`); an orbital scene leaves its automatic
  exposure out. What each sets: docs/CONFIG.md (`space`). `camera` costs about +0.3 to +0.7 s a frame on a
  sea-and-cloud view at 1280x720 (7.3 against 7.7–8.0 s).
- **Look before you render**: `vidgen still . --scene rings --at 4 --size 640x360`. The page prints as warnings
  what only it can know (a subject under 3 px, the camera inside a world, a jump in a move, a craft in a world's shadow or
  seen from its unlit side); `vidgen lint` reports
  a globe turning too fast under the speed-up, an enlarged body covering another, and "to scale" said of an
  enlarged scene.
- **More than the YAML can say**: `script: extensions/more.js` (its `setup(S)` and `frame(t, S)` get every object
  by name), or `vidgen space-page . --scene rings` to write the page out as a `web` scene and go on in code.
- **A whole film from a score**: `vidgen music plan assets/music/song.yaml --style space --out my_film` drafts a
  space scene per cut (a world by the scene's colour, a move by its role, sunrise on a section start).
- **Cost** (2 cores, software GL, 720p): a world through the finish about 0.3 to 0.5 s a frame, a craft filling the
  frame up to 0.9 s, a black hole filling the frame about 1 s, each page 3 to 9 s to open (bakes its maps). Render
  `--draft` first. vidgen keeps the baked maps of worlds and skies in its cache folder, so a later page with the
  same world or sky (another scene, still or render) opens faster with the same pixels: `02_depart` of
  `examples/outbound` 13.7 s, then 7.6 s (`vidgen cache` shows and clears it; `VIDGEN_BAKED_CACHE_MB=0` is off).

### In the air and beside giant ships

Two kinds of `space` scene. **Orbital** (no `world:`): the scene above, which also takes giant ships, planes and
craft of the kit's own parts among `craft:`. **Surface** (`world:`): one world from orbit to the ground in the
place's own frame (metres, x east, y up, z south): the air, the sea, the ground, cloud decks and the globe
seen from high up, with `flights:` (the `flight_data` words of a `web` scene: the ground is the world's own) and
planes flying them. Each kind refuses the other's words with a message saying where they belong.

```yaml
- id: chase                     # a surface scene: a plane chased over the alpine range under fair clouds
  type: space
  duration: 20
  params:
    world: {land: alpine, clouds: fair, sun: [24, 250]}   # sun: [elevation, azimuth] or {date: 2026-06-21, utc: "19:30"}
    flights:
      - name: Plane
        start: {x: -6000, z: 2000, above_ground: 600, heading: 70, speed: 140}
        legs: [{follow: {clearance: 300}, for: 12}, {turn: {by: 60, bank: 35}, follow: {clearance: 300}}]
    craft: [{name: Plane, plane: glider, seed: 7, fly: Plane, effects: {contrails: {always: true}}}]
    camera: {move: chase, flight: Plane, lens: wide-normal}
- id: carrier                   # an orbital scene: a dressed carrier, a pass along its hull, a craft into a bay
  type: space
  duration: 16
  params:
    orbits: {central: earth, speedup: 1, bodies: [{name: Carrier, altitude: 900 km}]}
    bodies: [{name: Earth}]
    craft:
      - {name: Carrier, hull: carrier, seed: 1, length: 3200, dress: {plumes: bank},
         scale_ref: {kind: ship, at: hangar-2, into: {hangar: hangar-2, over: [8, 16]}}}
    camera:
      - {move: hull-pass, ship: Carrier, over: [0, 8], side: port, standoff: 60, from: 0.3, speed: 40}
      - {move: into-bay, ship: Carrier, hangar: hangar-2, over: [8, 16], cut: true}
```

- **The world** (`world:`): `planet` (a world of `bodies`), `at: [latitude, longitude]`, `sun`, `air` (earth, mars, thin, thick),
  `sea` (a state: calm, breeze, swell, rough, storm; or `{state, water, seed}`; waters: ocean, green, tropical, grey, methane),
  `land` (a preset: alpine, mars, canyon, dunes, snow, volcanic, airless; or `{preset, seed, mountains, ...}`), `clouds` (a sky:
  fair, overcast, layers, towers, storm; or `{decks: [{type: cumulus, base, top, cover, fronts}], towers, lightning: {times, track, rate}}`;
  a deck's cover is the one asked for round the place and varies tens of km away, `fronts: 0` keeps it even),
  `globe`, `handover` (low, high), `exposure`, `ev`, `quality` (fast, standard, fine), `shadows` (on by default: the decks' and
  the ground's shadows in the haze and the decks' shadows on the sea and the ground; `false` for none). The stars behind the air are `sky:`.
- **Planes** (`craft: [{plane: glider, fly: FLIGHT}]`): glider, freighter, needle, lifter, scout, skiff; any part of the
  description (`wing: {preset: swept, sweep: 42}`, `fins`, `body`, `scheme`, `scorch`), `gear`, `bay`, `cabin` (0..1, or
  `{over: [10, 14], from: 0, to: 1}`), `controls`, `throttle`. A craft of the kit flies too (`kind: probe, fly: FLIGHT`), and
  a craft of the kit's own parts: `parts: {part: hull, ..., attach: [{at: fore, part: dish}, {around: {count: 2}, part: solar-wing}]}`.
- **Effects** (`effects:` on a craft): reentry, contrails, exhaust, vapour (each `true` or its options); in a surface scene they
  follow the flight; an orbital scene's craft take `exhaust` only.
- **Giant ships** (orbital, `craft: [{hull: carrier}]`): spine, carrier, cluster, lance, wheel, ark, twin; `length`, `age`,
  `palette` (bone, slate, iron, sand, frost), the family's numbers; `dress` (windows, bays, lamps; `false` bare), `scale_ref` (a
  small craft beside it: `{kind: ship, at: hangar-1, gap, into: {hangar, over}, escort: true}`), a fleet: `hull: [carrier, spine]`
  with `fleet: 5`. With a hull in the scene vidgen sets the view's near plane to 4 m (depth precision; said in the page).
- **Moves in the air**: skim, climb-through, descend-through, chase, wing, fly-past, orbit-peak, rise, descend, ascend
  (`flight:` names a flight or the craft flying it; `deck:` a deck's index or name; `around: {near: [x, z], reach}` a peak;
  wing views: wingtip, tail, belly, nose); a `skim` with `continues: true` after a `descend` takes over where it ends.
  **Beside a ship**: hull-pass, hull-reveal, into-bay, stern-burn, scale-zoom (`ship:` the hull; sides of a pass: port,
  dorsal, top, starboard, ventral, bottom; a stand-off under 10 m is refused). Times are seconds or bars, as above.
- **Music**: `{track: kick, pulse: lightning}` (a strike on each hit), `{track: level, glow: lava}` (volcanic ground),
  `{track: lead, glow: Plane, as: boost}` (the afterburner; also `lights`, `throttle`, `pulse`), `{track: pad, glow: Carrier,
  as: lights}` (a hull's windows).
- **Cuts**: `flash: [{at: 'bar 9', amount: 2}]` (the same `at` in the scenes on both sides of the cut), a warp across a cut
  `phenomena: [{kind: warp, cut: {at: 'bar 9', seconds: 3}}]`, a match cut `{move: arc, subject: Moon, match: Earth, cut: true}`.
- **Cost**: a surface scene is 1.2 to 3.5 s a frame at 720p (a sea, ground, clouds; all three are the dearest), a dressed hull
  1 to 2 s; `vidgen lint` says so for a dear combination. A drafted film: `vidgen music plan SCORE --style space-air`
  (a skim at sunset, a descent, a chase over a range, a hull pass, into a bay). Not reachable from YAML (use `script:` or
  `vidgen space-page`): the wormhole passage, a re-entry from orbit, a sun that moves through a scene, the camera placed
  by hand in a ship's own axes, a plane fleet, a hull in a surface scene. Recipes: COOKBOOK-SPACE.md (orbital
  scenes, giant ships), COOKBOOK-AIR.md (surface scenes, planes, the descent).

