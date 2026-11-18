# Changelog

The project and its pip distribution are `schu-video-generator`; the command and the Python
package are `vidgen`. The release notes of 0.2.0 (what changed from 0.1) are in `HANDOFF.md`
("Release notes: schu-video-generator 0.2.0") and `DESIGN.md` §63. Step numbers refer to `tasklist.md`;
each step has a section in `HANDOFF.md` and its details in `DESIGN.md`.

## Steps 193–391

### Air, planes and giant ships (Phase AO, Steps 379–394)

- **A gallery for web scenes** (Step 379): the scene types drawn by a web page (`3d`, `web`,
  `space`) have their own [web scene gallery](docs/gallery/web/README.md), linked both ways with
  the [scene gallery](docs/gallery/README.md), which keeps the videos on YouTube. `vidgen gallery`
  puts every type drawn in headless Chromium there, a new one included; `--json` names the web
  index (`web_index`) and says which entries are in it; the MCP server serves its pages too.
- **A cache for baked maps** (Step 380): the surface maps of worlds (`vidgen/space-bodies`) and
  the sky's cube map (`vidgen/space-sky`) are baked once and kept in vidgen's cache folder; later
  pages (scenes, stills, drafts, renders, parallel jobs) load them with the same pixels, bit for
  bit: a world of `size: 2048` opens in 7 s instead of 30 s, Outbound's `02_depart` in 7.6 s
  instead of 13.7 s. Limited to 2000 MB (least recently used removed first),
  `VIDGEN_BAKED_CACHE_MB` sets the limit (`0`: off), `vidgen cache` shows it and `vidgen cache
  clear` empties it. `vidgen/baked` gives a page's own bake the same cache
  ([CONFIG](docs/CONFIG.md#baked-maps-vidgen-cache)).
- **The sky from inside an atmosphere** (Step 381): `vidgen/space-air` draws the view from
  within a world's air, at any height from the ground to space: `air(renderer, "earth", {sun})`
  gives the sky for any sun (day, golden hour, sunset, twilight with the stars coming out, night),
  the sun's disc reddened and darker at its limb, a plain ground under the horizon, aerial
  perspective for anything in the scene (`sky.haze(material)`) and the sun's and the sky's light
  for things in the air. One scattering model (gas, haze, an ozone layer, one stated term for light
  scattered more than once) on the air `vidgen/space-bodies` draws round the same world from
  outside; ready-made airs `earth`, `mars` (butterscotch days, a blue glow round the setting sun),
  `thin` and `thick` (invented), every world of `vidgen/space-bodies` that has air, or an air
  stated by its numbers. Exposure `film` (dusk lifted, a convention), `camera` and `auto`, as
  `vidgen/space-light`. 0.19 s a frame at 1280x720 in software GL; ten parts under the new kind
  `air` (`vidgen parts --kind air`). [CONFIG](docs/CONFIG.md#web), [space cookbook](docs/COOKBOOK-SPACE.md).
- **Twilight, the Mars-like sunset and the sun's disc** (Step 381.1): from sunset to night the
  sky of `vidgen/space-air` now fades without a step (it went black with the sun 10 degrees down):
  light scattered twice reaches the shadowed air, the dusk is blue, the arch stays on the horizon,
  and the film exposure keeps a deep-blue glow at 12 degrees. The Mars-like air's dust has a
  narrow second lobe (`aureole`): a compact blue-white glow round a low sun in a tawny sky. A low
  sun is an orange-gold disc with a darker limb and a soft bloom.

- **Ocean** (Step 382): `vidgen/space-sea` lays water to the horizon under a `vidgen/space-air`
  sky: `sea(renderer, sky, {state: "breeze", seed})` gives waves at several scales from a seed,
  moving on vidgen's clock (sea states `calm`, `breeze`, `swell`, `rough`, `storm`, or wind,
  direction, wave height and swell by numbers), the sky's own picture mirrored with Fresnel's
  share (a sunset and a dusk are mirrored as they are), the sun's glitter path as wide as the sea
  state makes it and golden at sunset, the water's colour (`ocean`, `green`, `tropical`, `grey`,
  and `methane`, an invented dark sea), whitecaps and their lace when it blows, and the horizon
  where the height and the world's radius put it: right from 50 m, curved from 100 km, with the
  air's haze over far water and no seam to the sky. Waves finer than a pixel fade into the
  glitter's width, so far water does not shimmer. `water.heightAt(x, z, t)` and `pointAt` give
  the surface the picture draws, for anything that floats or skims. 1.1 s a frame at 1280x720
  near the water in software GL (0.65 s from 20 km; `quality: "fast"` 0.8 s); eight parts under
  the new kind `sea` (`vidgen parts --kind sea`). [CONFIG](docs/CONFIG.md#web),
  [space cookbook](docs/COOKBOOK-SPACE.md).

- **Glitter from high up, steep seas, dusk** (Step 382.1): seen from 2 to 100 km the sun's
  glitter on `vidgen/space-sea` is a tongue that fades before the horizon (it ended there at
  full strength); `rough` and `storm` seas show their waves' bodies (darker troughs, lighter
  crests, shaded faces) and their foam is broken lines along the crests with thin streaks down
  the wind, no cut-out patches and no net of cells; at dusk in film exposure near water keeps
  the sky's colours until the sun is about 9 degrees down.

- **Ground with relief** (Step 384): `vidgen/space-land` draws mountains, canyon land, dunes,
  Mars-like desert, crater fields, snow and basalt plains under the air of `vidgen/space-air`,
  with the ground's own long shadows, clouds' shadows and the air between. The large forms and
  colours are those the same world of `vidgen/space-bodies` shows from orbit; the relief under
  them comes from a seed. Presets `alpine`, `mars`, `canyon`, `dunes`, `snow`, `volcanic`,
  `airless`; `ground.heightAt(x, z)` for paths and cameras; a coast with `vidgen/space-sea`
  (`depth: ground.depth`); clouds behind mountains (`behind: ground.behind`, new in
  `vidgen/space-clouds`). 1.35 s a frame at 1280x720 after 7 to 19 s for the maps; nine parts
  under the new kind `land` (`vidgen parts --kind land`).
- **Canyon land, volcanoes, a sharper range** (Step 384.1): the `canyon` ground of
  `vidgen/space-land` is a plateau cut by winding canyons 1,100 m deep with stepped walls in
  banded rock and mesas between; `volcanic` has cones with a crater, a lava lake and channels
  that glow at dusk (`ground.setGlow(level)` for a pulse on the music); the `alpine` range has
  finer ridges and gullies and holds from about 150 m. The height maps are kept in vidgen's
  cache of baked maps: a page that starts where another did draws its first still in 8 s
  instead of 12 s at 1280x720.
- **Cloud decks and gas giants** (Step 383): `vidgen/space-clouds` draws clouds in a
  `vidgen/space-air` sky, on the world's own sphere: `clouds(renderer, sky, {sky: "fair", seed})`
  gives decks the camera can be under, in, between and over (`cumulus`: a broken field with flat
  grey bases; `stratus`: a closed deck, a cloud sea from above; `cirrus`: thin high streaks; by
  heights, cover and seed, drifting with the wind on vidgen's clock), cloud towers with anvils
  rising through the decks, and lightning inside them from a seed or at stated times (a
  `ctx.music` track's hits). The sun lights each deck after the air at the deck's own height
  (white tops by day, every swell of a cloud sea lit from the side at sunset, high cloud still
  pink when low cloud is in shadow), thin edges shine towards the sun, bases are grey, upper
  decks cast shadows on lower ones and, with the sea's new `shade` option, on a
  `vidgen/space-sea` sea; the air's haze lies over far cloud. A giant of gas has no ground:
  `giantSky("jupiter", ...)` and `giantAir("jupiter")` give decks in the colours of the band at a
  latitude of the same world in `vidgen/space-bodies`, towers, a high haze and the dark below
  (heights and air: a stated look). Ready-made skies `fair`, `overcast`, `layers`, `towers`,
  `storm`. 0.9 to 1.9 s a frame at 1280x720 in software GL (three decks 2.5 s; `quality: "fast"`
  0.4 to 0.8 s); nine parts under the new kind `cloud` (`vidgen parts --kind cloud`).
  [CONFIG](docs/CONFIG.md#web), [space cookbook](docs/COOKBOOK-SPACE.md).

- **Lumps, soft edges, towers, a banded giant** (Step 383.1): the clouds of `vidgen/space-clouds`
  have fine lumps and frayed edges (the fine caps push each cloud's face in as seen; a cloud sea's
  top has a fine ripple), their edges are soft at `standard` (they were stepped), a cloud tower is
  a leaning column of lumps, still growing or with an anvil drawn out downwind (it was a cylinder
  under a lens), and a giant's main deck shows the planet's bands north and south of the camera,
  40 times narrower than true so that several are in view (`squeeze`; a stated look), with clouds
  drawn out along the wind and deeper gaps in the dark bands. `giantSky` gives no towers unless
  asked. `fair` and `overcast` cost as before within 8 %; towers 14 %, a giant 27 % more.
- **Flight paths** (Step 385): a `web` scene's `flight_data:` plans flights in words — a start
  (place, height or height over the ground, heading, speed), then legs: `straight`, `turn` (to a
  heading or by an angle, at a bank or a radius), `climb` / `descend` / `level`, `speed` (m/s or
  Mach), `follow` (terrain following at a clearance), `waypoints` (a smooth curve through places),
  `circle` (round a peak or a ship), `land` (approach, flare, roll-out) and `reentry` (from an
  orbit of the scene's `orbit_data` down to level flight), each for seconds or until a time ('bar
  9 beat 3') — over `vidgen/space-land`'s ground (its heights computed in Python to 10⁻¹² m of
  the page's), the sea, a level ground or a flat world. The page gets `ctx.flight`: for every
  frame each flight's position, velocity and attitude (banked in turns), speed, Mach number,
  heights over sea level and over the ground, load factor, bank, pitch, heading and a heating
  indicator, in the frame the air, sea and land modules draw in; `craft.fly(ctx.flight, {flight})`
  of `vidgen/space-craft` flies a craft along it. A path that would come under the ground is an
  error naming the time and the place (or, with `lift: true`, it is raised there). Python:
  `vidgen.api.flight`, `web_scene_flights`; `vidgen cache clear` also removes the ground heights
  kept for flights.
- **Giant ship hulls** (Step 388): `vidgen/space-hull` builds hulls of ships 0.5 to 10 km long
  on the spacecraft kit, in seven invented families, each another ship for every seed: `spine`
  (a long truss with drums, tank clusters and great radiator vanes), `carrier` (a thick block
  with a deck trench, a forked blunt bow, hangar slots, terraces), `cluster` (an open frame with
  pressure balls, tanks and container stacks), `lance` (a very long thin hull behind a faceted
  shield), `wheel` (two polygonal crew rings turning against each other on a hub), `ark` (a
  worked asteroid with a hangar portal and a collar) and `twin` (two unequal hulls joined by
  bridges). Large forms that hold as lit masses: chamfered blocks, trenches and hangar mouths
  as real recesses, banks of the kit's bells, radiators, plates of their own tone, five
  palettes. A hull is a craft: it flies a body of `orbit_data`, fires its bells, hides a star's
  glare; `scaleRef` stands a 50 m craft beside it; `problems()` names buried bells and absurd
  proportions. For later fine detail every hull carries named regions, anchors (bells, hangars,
  docks, lights, the command place) and one atlas of non-overlapping charts with their metres
  per texel. Fourteen parts under `vidgen parts 'hull-*'`.
- **Orbit to ground in one shot** (Step 391): the new module `vidgen/space-descent` gives
  `world(renderer, {planet, at, sun, sea, land, clouds})`: the globe, the air, the sea, the ground
  and the cloud decks of one world for one place and one sun, drawn for any camera height from
  the surface to orbit. The air is one model at every height (the globe is seen through it, so
  the limb's glow becomes the sky with no handover); the globe's picture is laid over the sea,
  the ground and the decks where a pixel's ground is far and the camera is high, and fades out on
  the way down (`HANDOVERS`: 80 km to 2.5 km over a sea or decks, 600 km to 60 km over bare
  ground). `vidgen/space-camera-air` gains `descend` and `ascend`: from 400 km to 300 m with equal
  time for each power of ten of height, the view going from the globe under its limb to the
  level horizon, ending level and moving so that a `skim` given `shot.end` follows with no cut.
  `world.honest` says what is not true (the camera's speed; single clouds of the globe and of the
  decks are in different places; the surface is soft between 150 km and 25 km over a sea). Four
  parts: `vidgen parts 'joined-*' camera-descend`.
- **Camera moves in the air and beside giant ships** (Step 390): the new module
  `vidgen/space-camera-air` gives `airCamera(...)`, the rig of `vidgen/space-camera` with thirteen
  more moves, each a function of the scene's time. In the air: `skim` (a low pass over sea or
  ground at a stated clearance and speed, following the ground with look-ahead and banking into
  its turn), `climbThrough` and `descendThrough` (a cloud deck's fog and out the other side, with
  eye adaptation as a stated look), `chase` (behind a plane on its flight with a lag and part of
  its bank), `wing` (locked to the plane: wing tip, tail, belly, nose), `flyPast` (a standing
  camera and a whip-pan), `orbitPeak` (round a mountain, a volcano or a tower of cloud), `rise`
  (a crane from the surface to the curve of the world). Beside a ship: `hullPass` (a slow pass
  whose path is made from the hull's regions at a stated stand-off), `hullReveal` (the bow slides
  into the frame and the hull keeps coming; or from behind a world), `intoBay`, `sternBurn` (the
  bank lights on a bar, the camera is pushed back, a seeded shake on request) and `scaleZoom`
  (from a place on the hull to the ship as a speck by its world). Times are seconds or bars and
  beats of the score; a move may start or end moving; the camera is never under the ground or
  the water and takes "up" from the local vertical. Twelve parts under `vidgen parts
  'camera-*'`; recipes and costs in `docs/COOKBOOK-SPACE.md`.
- **Giant ships that read as kilometres long** (Step 389): `dress(ship, renderer)` of the new
  module `vidgen/space-hull-detail` gives a hull of `vidgen/space-hull` its fine detail: panel
  seams, hatches, pipe runs and vents at 5 to 20 m and panel lines, rivet rows and stencil bars
  at 1 to 5 m (tiling maps, each fading with the metres a pixel covers); windows by the thousand
  in rows along the decks, dense on crew regions and absent from tanks, radiators and engines, a
  seeded share lit, banks coming on with `lights` (for example from `ctx.music`); lit hangar bays
  with floor marks, parked craft and cargo; clutter on decks and in the trench; hull numbers,
  floodlit walls, navigation and guide lamps; dressed engine banks with one long plume a bank
  that lights the stern. `detail.fly(craft, "hangar-2", u)` flies a small craft into a bay. The
  maps are baked once and kept by `vidgen cache`. A fleet of `hullFleet` now has one palette and
  one accent (`navy: false` for the old mix); the `lance`, the `twin` and the `ark`'s terraces
  have more character, and the lance has a hangar. Six new parts under `vidgen parts 'hull-*'`;
  recipes for the shots that show size and the costs are in `docs/COOKBOOK-SPACE.md`.
- **Re-entry and flight effects** (Step 387): `vidgen/space-effects` adds to a plane, a craft or
  any object: the glow of a re-entry (a layer on the windward side made from the craft's own shape,
  hot surfaces, a wake, sparks, and from far away a bright head with a train of light along the
  path), vapour trails that stay where they were laid in the world and spread, break up and fade,
  engine exhaust shaped by the air's density (shock diamonds low down, a wide pale plume high up,
  an afterburner), a vapour cone near Mach 1 and wing vapour in hard turns. With `flight_data:`
  everything follows `ctx.flight` (heating, Mach number, load, height, the path behind); each
  number can be set by hand or from music. Nine parts under `vidgen parts --kind effect`.
  Step 387.1: the exhaust is a defined flame (a sharp core from each bell, a tapering outer
  flame, a row of shock diamonds, a wide faint plume in thin air); the vapour cone is a soft
  uneven disc of mist near Mach 0.97; wing vapour is a sheet over the wing.
- **Space plane parts** (Step 386): `vidgen/space-plane` builds winged craft on the spacecraft
  kit. A lofted body (length, width, height, five nose shapes, droop, a round to flat belly, a
  boat tail, a dorsal hump, a payload bay), ONE wing function (span, root and tip chord, sweep,
  crank, curve, dihedral, thickness, airfoil, twist, fillet, winglets or tip fins, elevons and
  flaps) with nine presets (`delta`, `double-delta`, `cranked-arrow`, `swept`, `straight`,
  `ogival`, `stub`, `blended`, `long`), tails (`single`, `twin`, `vee`), rocket bells for the
  tail, air-breathing pods, a belly intake, landing gear that folds behind doors, bay doors that
  open on their radiators, a body flap, brakes, canards, thrusters and lights. Surfaces that
  hold in close-up: black heat tiles, quilted blankets, panel lines, bare metal, scorch streaks
  (`scorch`), stripes and an invented registration; schemes and colours as options. Six
  ready-made planes, each another one for every seed: `plane("glider" | "freighter" | "needle"
  | "lifter" | "scout" | "skiff", {seed})`; `planeFrom({...})` for a plane of one's own,
  `planeFleet` for a formation, `problems()` for what looks wrong. On a flight of `flight_data`
  a plane banks with the turn and its surfaces move with the flight's rates. All designs are
  invented. `vidgen parts 'plane-*'` shows them (kinds `craft` and `craft-part`).

### Space scenes (Phase AN, Steps 367–378)

- **The phase's review** (Step 378): the cookbook [docs/COOKBOOK-SPACE.md](docs/COOKBOOK-SPACE.md)
  (what to show, honest scale and exposure, a recipe per shot with its `video.yaml`, the cost of
  each shot on 2 cores, the checks, common mistakes and their messages, where the numbers come
  from). Through a long lens the sky stays sharp points over a smooth glow (no soft blobs or
  streaks behind a craft). The page warns of a craft in a world's shadow or seen from its unlit
  side, and `follow` takes `side: sun`. A burn shown for seconds of a sped-up scene keeps its
  direction in the flight's own axes. `vidgen motion check` follows stars across a pan and leaves
  a warp's streaks out: no `shimmer` warnings on fly-bys, warps or 8 fps drafts (two new
  thresholds, `shimmer_reach` and `shimmer_point`). A fly-by's planet pole and sun stand as they
  are on the date; a `transfer` scene may end before its second burn (the departure alone); a dated
  orbit-data speed-up is no longer refused at `vidgen validate`; a camera may name a body nothing
  draws (a comet's). A page may take 90 s to open (2048 world maps). The crewed ship's tanks are
  wrapped in foil. The `space` type in the scene gallery; MCP tool `space_page`. Outbound: a sharper
  world under the departure, the fly-by's true sun and rings, a nearer black hole on the hit, a
  larger end card. The star catalogue: vidgen ships a hand-written list of 221 bright stars; the
  Bright Star Catalogue (no formal licence) is converted by `tools/make_star_catalogue.py` for a
  user who downloads it.
- **An example space film** (Step 377): `examples/outbound`, "Outbound", 58 s at 1280x720, source
  only: five `space` scenes written in `video.yaml` with no JavaScript, cut on the bar lines of an
  original score for vidgen's synthesizer (D minor, 75 BPM, one bar = 96 frames; strings, four horns,
  low brass, a men's choir, timpani, taikos). A sunrise over an Earth-like world on bar 4; a ship's
  7.28 km/s departure burn on bar 7 (the Hohmann transfer to Saturn, from the orbit mathematics) and
  its escape hyperbola; a fly-by of a ringed giant at the transfer's arrival speed; a jump to warp; a
  black hole fly-by as the climax; an opening title and an end card. Its README has the form table,
  what is true and what was chosen, the estimated render time and how to change it. Fixed on the way:
  a world of a `space` scene's orbit data can now be a camera move's subject (`arc` round the planet a
  craft flies past); before, the page stopped with "arc.subject must be ...". The pages of `space`
  scenes with `orbits:` and `bodies:` gain one line, so such scenes are drawn again.

- **Space scenes without code** (Step 376): the new scene type `space`, written in `video.yaml`
  alone. Name a sky (from a seed, or the real bright stars), a sun, worlds (`{name: Saturn}` is
  a ringed giant; `type: ocean` with a seed is a world of your own), craft, phenomena and camera
  moves, and vidgen writes the three.js page from the ready-made space parts and draws it like a
  `web` scene: `vidgen still`, `--draft`, the cache. With `orbits:` (the `orbit` scene's words)
  the worlds and craft are the orbit data's bodies, a craft flies a real transfer with its burns,
  and the Sun stands where it really is on the date; `scale:` enlarges bodies or compresses
  distances and says so on screen. Camera moves follow one another in seconds or in bars of the
  score (`over: ['bar 9', 'bar 13']`); a move that does not start where the last one left the
  camera stops the render unless it says `cut: true`. `music:` pulses the sun's glare, the sky,
  a black hole or a warp on a track's hits and drives a craft's throttle and lights (never the
  camera); `title:` and `end_card:` add Escapement's cards; `finish:` has no FXAA by default.
  Every key is checked by `vidgen validate` with the closest word, the names and options read
  from the space modules themselves; `vidgen lint` warns of a globe that turns too fast under the
  speed-up, an enlarged body covering another, and "to scale" said of an enlarged scene; the page
  prints what only it can know (a subject under 3 px, the camera inside a world). `script:` adds
  your own code with every object by name, and `vidgen space-page` writes the page out as a
  `web` scene to go on in code (the same picture). `vidgen music plan SCORE --style space` drafts
  a whole space film from a score: a world chosen by each scene's colour, a camera move by its
  role, sunrise on a section start, moves on bar lines. `vidgen guide space-scenes`.
- **Camera moves for space scenes** (Step 375): the new module `vidgen/space-camera`.
  `spaceCamera({space, camera})` gives the moves by name, each a function of time, so a cut on a
  bar line and motion blur are safe: `flyBy` (approach, the closest pass at a stated distance
  and side, recede, with an optional bank), `pass` (a craft passes the camera), `arc` (a world
  at a phase by name: `cam.arc(t, {subject: "Saturn", phase: {limb: 0.1}})` is a crescent with
  the sun just off the limb), `arrive` (from far out to a low orbit over a level limb), `reveal`
  (the sun, a moon or a craft comes out over a world's limb, the first light exactly at a given
  time), `follow` (seven views of a craft, among them a long lens that makes the world's limb
  loom behind it) and `zoom` (powers of ten: every second multiplies the distance by a constant,
  with landing points to rest on). The subject sits on a third, the horizon of the world below is
  level, speeds ease. Lenses by focal length, `loomLens` for the long-lens shot, `cam.check`
  that says in sentences when a camera is inside a world or a subject is lost, a match cut on a
  disc, a cut on a flash, the warp as a cut. Five framings on the contact sheet: `vidgen parts
  --kind camera`.
- **Path lines show in close-ups** (Step 375): a line of `space.path` in `vidgen/space-scale` was
  not drawn near the camera, and lost the part of an orbit nearest the camera at the frame's
  edge. Both are fixed.
- **A spacecraft kit** (Step 374): the new module `vidgen/space-craft`. `craft("probe", {seed})`
  gives a finished craft in one line: a deep-space probe, a communications satellite, a modular
  station (with a turning ring habitat on request), a crewed ship, a lander and a cargo tug, all
  invented designs in metres, another design of the kind for every seed and the same craft for
  the same seed; `fleet(kind, {count, seed})` a formation of them. The same parts are there for
  a craft of your own (`craftKit`: hull sections, tanks, trusses, solar wings, radiators,
  dishes, antennas, booms, instruments, docking ports, a cupola, an airlock, engines,
  thrusters, landing legs, a ring habitat, cargo boxes, lights), joined at named points with
  `attach` and `around`. Surfaces are computed, not pictures: gold, silver and black foil that
  crinkles, white paint and bare aluminium with panel lines and rivets, black tiles, solar
  cells with their grid, windows lit from inside. `craft.update(t, {sun})` turns the wings to
  the sun, points gimballed dishes, blinks the lights by the clock and fires the engines
  (`throttle`): plumes that widen into the vacuum (chemical, hydrogen, ion; shock diamonds only
  for an engine in air). `craft.fly(space, {body})` flies a body of `orbit_data` with a stated
  attitude (prograde, retrograde, radial, nadir, to the sun, to a target, or a list of them
  with eased turns) and shows each burn of the data as a short stretch of thrust with the nose
  along it. `craft.shade(sun)` lets a craft hide the sun's glare; `craftEnvironment` gives its
  metal the sky and the planet to mirror; far away a craft is a steady point of light that
  flashes when a panel mirrors the sun. `vidgen parts --kind craft` and the new `--kind
  craft-part` show 31 tiles. Measured at 720p in software GL: a craft in a wide shot 0.05 to
  0.15 s a frame, filling the frame 0.3 to 0.6 s.
  Fixed on the way: `vidgen/space-scale` drew no shadows when the scene had a sky.
- **Phenomena for space scenes** (Step 373): the new module `vidgen/space-phenomena`.
  `blackHole(renderer, {sky})` is a non-rotating black hole whose light paths are worked out for
  every pixel: a shadow of the true size, the sky bent round it (an Einstein ring before the
  Milky Way, stars brighter near it and seen a second time on the far side), a disc of gas whose
  far side stands over and under the shadow, brighter where it comes toward the camera,
  white-hot inside and red outside, turning faster inside. `wormhole(renderer, {sky, other})` is
  a ball that shows another sky, and `passage(camera, progress)` flies through its tunnel of
  bent light. `warp(renderer)` stretches stars into streaks for a jump driven by a progress from
  0 to 1 (a flash, a tunnel, brightness pulses from the music; the lens is never zoomed).
  `asteroids(renderer)` is a field of thousands of seeded, tumbling rocks to fly through or a
  belt round a world, `asteroid()` one rock for a close-up. `comet(renderer)` has a dust tail
  and an ion tail that point away from the sun and, with `orbit_data`, grow as the comet nears
  it. `aurora(world)` lights the polar oval of a world's night side. Every phenomenon has a
  `quality` and a measured cost a frame (CONFIG `web`, "Phenomena"; on the sheet of
  `vidgen parts --kind phenomenon`, 12 parts). What is physics and what is a painter's choice
  is stated in the reference.
- **Suns and the light of a space scene** (Step 372): the new module `vidgen/space-light`.
  `star(renderer, "sun")` is a star you can look at: cells that boil in place, a limb that darkens
  and reddens, spots and faculae from a seed, a corona with streamers, loops of gas at the limb;
  five ready-made kinds by temperature (`red-dwarf`, `orange`, `sun`, `white`, `blue-giant`) or
  your own. Small in the frame (`{direction}` for a sun in the sky, or the Sun of `ctx.orbits`
  with `{space}`) it is a brilliant point with a soft glow, thin diffraction spikes fixed to the
  frame and faint round lens ghosts. `spaceLight({scene, camera, sun, bodies, sky})` lights the
  whole scene from one place each frame: every body's sun, planet-shine and ring-shine on night
  sides, a directional light for ordinary meshes, optional eclipse shadows (`eclipses: true`: a
  moon's shadow on its world, a world's copper shadow on its moon), no ambient light. The glare
  knows the bodies in front of the sun: at sunrise over a world's limb it starts as a red spark
  and grows, with nothing read back from the picture. Exposure is a stated choice: `"film"` (the
  default, a convention: stars beside a day side, planet-shine lifted), `"camera"` (honest: one
  exposure `ev`; the stars are 20 stops under a sunlit ground) and `"auto"` (honest: the exposure
  follows what is in the frame, with no state between frames). `falloff: 2` gives the true
  inverse-square sunlight; the default 0 lights every world alike. 15 parts on `vidgen parts
  --kind light`. `vidgen/space-scale` now draws objects marked `userData.overlay` once, over
  everything, after its depth slices; `vidgen/space-bodies` gained the eclipse test in its shader
  (off unless `spaceLight` asks). A star takes 0.6 s to make and 0.15 to 0.4 s a frame at 720p
  in software GL.
- **Planets, moons and rings in one line** (Step 371): `planet(renderer, "earth")` from the new
  module `vidgen/space-bodies` puts a world into a three.js `web` scene whose surface is generated
  from a seed: seven types (`rocky` with craters, maria and rays; `icy` with long cracks;
  `desert` with canyons, volcanoes and polar caps; `ocean` with continents, sun glint, clouds in
  weather systems, ice caps and faint city lights; `lava`; `gas` with belts, zones, stirred edges
  and storms; `ice-giant`), each with options and palettes, and 21 ready-made worlds: lookalikes
  of the Solar System's bodies from Mercury to Neptune, the Moon, the Galilean moons and Titan (in
  character and colour, not maps of them) and seven invented ones. Air is a thin shell with a blue
  limb, a red terminator and a lit rim when the sun is behind; airless bodies show crater shadows
  at the terminator. Rings (`rings: {...}`) have provinces, gaps and ringlets, shadow the globe
  and are shadowed by it, glow in their thin parts when seen from the unlit side and stay clean at
  grazing angles. With `orbit_data`, `planet(renderer, "Saturn", {space})` places, sizes, tilts,
  turns and lights the body from `ctx.orbits`; `body.problems()` warns when a speed-up makes a
  globe turn so far a frame that it flickers, and `spin: "locked"` or `spin: seconds` are the
  stated ways out. A body is sharp from a close limb down to a single steady point. A body takes
  2 to 4 s to make and 0.05 to 0.2 s a frame at 720p in software GL. 33 new tiles on
  `vidgen parts` (`vidgen parts --kind body`).
- **A sky for space scenes in one line** (Step 370): `spaceSky(renderer, {seed})` from the new
  module `vidgen/space-sky` draws a sky like a photograph taken from space behind a three.js `web`
  scene: about 69,000 stars in the real sky's numbers per magnitude, with pale colours by
  temperature and a small glare on the brightest; the Milky Way with a warm bulge, star clouds and
  a dust rift; on request emission, reflection and dark nebulae and far galaxies. `look: "rich"` or
  `"sparse"`, `density`, `brightness`, `color`, the band's place and more are options. Stars do not
  shimmer when the camera turns slowly (0.015 to 0.022 on `vidgen motion check`'s scale, where the
  warning starts at 0.2). The sky is made once (5 to 6 s at 720p in software GL) and then costs
  about 0.1 s a frame; `sky.environment` lets metal reflect it. `{stars: "real"}` puts the true
  bright stars at their places with the Milky Way where it is, in the frame of `ctx.orbits`, so a
  dated scene has the right constellations behind its planets; the shipped star file holds 221
  well-known bright stars at approximate places, fainter stars are seeded, and
  `tools/make_star_catalogue.py` converts the Yale Bright Star Catalogue into the same file.
  `spiralGalaxy()` is a galaxy of particles that a camera can fly past. Eleven new tiles on
  `vidgen parts` (`vidgen parts 'space-sky*' spiral-galaxy`). With `vidgen/three-finish`, use
  `antialias: "none"` for star fields: FXAA turns small stars into crosses.
- **`vidgen motion check` understands dark pictures** (Step 369): dark frames are also looked at
  640 px wide, so a star field or a thin crescent on black is no longer taken for a blank frame
  and a slow drift of the stars is no longer "frozen", while black frames that break into a star
  field, or a planet that vanishes for a few frames, are reported as errors. New findings: an
  over-exposed sun or planet (`clipped`), stars that shimmer as they move (`shimmer`, a common
  fault of small point stars), a dark glow drawn in steps (`banding`), a nearly empty frame
  (`empty`) and, for the scenes named with `--subject`, a subject lost in the dark (`lost`).
  Escapement's opening and ending are no longer listed as frozen: their title fades in and the
  watch turns.
- **`vidgen parts`** (Step 369): a labelled contact sheet of the ready-made three.js parts for
  `web` scenes (skies, crystals, a tesseract, portals, rings, a corridor, tunnels, flares, shock
  rings, glints, ribbons, spectrum rays, dust, a studio environment), each tile with the one line
  that uses it, drawn in one browser in about 12 s; `--list` names them without drawing; `--kind`,
  names and patterns choose; one part gets one large tile. The parts live in a registry,
  `vidgen/parts`, that a page can build them from by name; the space parts of the coming steps join
  it. Over MCP: `parts`.
- **Planets, moons and a ship at their real sizes and distances in three.js** (Step 368):
  `vidgen/space-scale` places what `ctx.orbits` gives camera-relative in double precision every
  frame and draws in depth slices, so a 100 m ship 400 km above the Earth, the Moon behind it and a
  box 3 m from the camera neither jitter nor z-fight, with `vidgen/three-finish`'s bloom, motion
  blur and depth of field. Three stated scale modes, true (the default), bodies enlarged by a
  stated factor, and distances compressed as the `orbit` scene's `radial: log`, each with its
  honest caption in the `orbit` scene's words ("sizes not to scale"). One camera can travel from
  2 m above the Earth to beyond Neptune in a single shot.
- **Orbits on a three.js page** (Step 367): a `web` scene with `orbit_data:` gets `ctx.orbits`,
  the planets, moons and spacecraft of the `orbit` scene (same keys: `bodies`, `span` or
  `speedup`, `date`, `transfer`, `flyby`, `dynamics`, `system`) computed by vidgen for every frame:
  positions and velocities in metres from the central body in the ecliptic of J2000, each body's
  orbit and path as polylines, a ship's burns, and how each body turns (an orientation and its
  prime meridian per frame). `vidgen still` and the render show the same numbers, to the last
  digit.
- **How the Sun, the planets, the Moon and the Galilean moons turn**: rotation period, axial
  tilt, north pole and radii from the IAU's cartographic report, with their sources; a tidally
  locked moon faces its planet.
- **Transfers in an inclined plane** now leave at the right moment: between two orbits sharing a
  tilted plane the launch window was measured on the flat projection, and the ship arrived up to
  10,000 km from its target. Orbits in the plane of the picture are unchanged.
- **The n-body check of the angular momentum** covers the whole vector, not only its part about
  the picture's axis (flat systems give the same values as before).

### Music-video tools (Phase AM, Steps 358–366)

- **Strings without a breath in slow, soft notes** (Step 366): a soft held note of the strings
  (low `brightness`, a soft dynamic, or a slow `attack` that swells in) had its bow's rosin hiss
  standing over the dark tone in the highs, a breathy "fo" with the note's envelope (Parallel
  Space's `swell`). The hiss now stays under the tone's own highs, as in an ordinary note: about
  21 dB less in such notes. Spiccato, pizzicato and notes held at ordinary or bright bow sound as
  before (their releases a hair less hiss); scores with held string notes change a little.

- **Parallel Space v8** (Step 365): `examples/parallel-space` is now the version the owner
  approved. An opening title and an end card from `vidgen/title-cards` (the light in the right
  third under the title, in the left third under the end card, which carries the credit and the
  project's link); in the opening and the breakdown the far choir line, the tenor soloist and the
  humming choir, the organ's flute stop, the horns, the brass-like swell and the swelling violas
  are silent, their notes kept so the pictures still follow them; output `parallel_space_v8`.

- **Opening titles and end cards for films** (Step 364): `vidgen/title-cards`, a module for any
  `web` page: `await titleCard(ctx, {title, subtitle})` and `await endCard(ctx, {title, subtitle,
  link, lines})`, then `card.update(t)` in `frame`. The look of Escapement's opening and end card:
  a small title with wide letter spacing in the left or right third, a thin rule, one subtitle in
  small capitals, a soft dark gradient behind the block; fades in over the first bars, holds and
  fades out before the first cut (the end card holds to the end). Sized to the frame in 16:9 and
  9:16 (in a portrait frame the block sits in the lower part), a too-long title set smaller to fit,
  options checked with a "did you mean". COOKBOOK-3D section 12, "Opening titles and end cards
  for films", gives the rules (asymmetry, restraint, quiet space, slow timing, a matching end
  card, and when not to use a title card).
- **The choir's `d` without a "sht"** (Step 363): a `d` (`da`, `de` …) opened with a hiss up to
  12 kHz that the hall's reverb carried on ("sht"). Its burst is now a soft tick inside the
  voice's own band (around 2.4 kHz, little above 3.4 kHz, a third of the level); the `d` is heard
  from its closure and the voice opening into the vowel. Notes without a `d`, and every choir
  that uses no syllable, soloist or whisper, sound exactly as before.
- **Review fixes** (Step 362): `vidgen/music-time`'s `melody` no longer dims the light for a frame
  at each note of a legato line (a note's attack rises from the level the note before has; in
  `examples/parallel-space` the `hook`'s light in `heart` and `afterglow` stays steady across its
  notes). A note above MIDI 127 on an instrument without a written range (e.g. a `bell` with
  `octave: 8`) no longer stops a render that collects warnings. `vidgen motion check` cannot hang
  on a file that makes ffmpeg print many errors. MCP tool `music_plan` (`vidgen music plan`). The
  guide's music-data example reads `tidewater`'s `melody` track (it has no `hook`); the choir's
  `morph` says it works with `syllable: vowel` only; README Features gains "Music videos".

- **More choir** (Step 361): `choir` sings syllables, still with no words. `syllable` (a track
  or section setting, or per note: `[la]`, `[na]`, `[mm-ah]`, `[syllable=da]`) starts a note with
  a soft consonant (`l`, `n`, `m`, `d`: `la lo loo le lee`, `na` …, `ma` …, `da` …) whose formants
  move into the vowel, a nasal murmur with its antiformant for `m` and `n`, a closure and burst
  for `d`; or glides between two vowels at `turn` (`ah-oh`, `oo-ah`, `oh-ah`, `ah-ee`, `mm-ah`,
  `mm-oh`, `mm-oo`). In a slur only the first note gets the consonant unless a note's own mark
  names a syllable or vowel (`syllable` and `vowel` may now change inside a slur). `soloist:
  true`: one solo voice, brighter (the singer's formant near 3 kHz), its vibrato wider and later,
  a scoop into each note, more breath. `whisper` (0 to 1) turns the tone into breath at about the
  same loudness. Unknown syllables get the nearest name. A choir that uses none of this sounds
  exactly as before (the film scores and the earlier choir demos render to the same bytes).
- **`vidgen motion check FILE|PROJECT`** (Step 360): watches a rendered video for what stills
  cannot show, without rendering anything: a video file, a project's rendered video (scenes from
  its `timings.json`) or its scene clips in `build/` (`--source scenes`), decoded once at 160 px
  wide. Reports, with time, frame, scene and severity: black or blank frames inside a scene
  (error), one- and two-frame flashes and drop-outs, flicker, regions popping in and out for a
  frame or two, strobing, frozen stretches and brightness jumps at cuts; flashes, pops and pulses
  on the score's drum hits and note starts are info. A contact strip PNG per finding, `--json`,
  `--threshold NAME=VALUE`, `--fail-on`; MCP tool `motion_check` returns the strips. On the
  finished films: Parallel Space v7 has no blank frames and one warning, Escapement none.
- **`vidgen music plan SCORE`** (Step 359): a music video's scenes proposed from a score file,
  without playing it: a role per section (intro, verse, build, drop, climax, breakdown, outro;
  from its name or its energy), scenes cut on bar lines (a section over 16 s split on the phrase
  line where the material changes most, one under 5 s joined to the one before; `--max-scene`,
  `--min-scene`), drops, breaths, silent bars and risers, a colour per scene from a colour script
  (cool → warm → calm, tinted by the key's mode) and the tracks each scene follows (low drums
  pulse the light, accents send rings, melodies leave glints, pads set the glow); `--json`.
  `--out DIR` writes and validates a draft project: `video.yaml` with the score as `music:`, a
  `web_cut` scene per cut (whole frames between bar lines, `music_data`, its plan in `data:`),
  `extensions/web_cut.py`, and a starter page per scene, one look per role, built on the kit
  (`docs/CONFIG.md`, "A music video from a score"; COOKBOOK-3D section 10). For the film scores
  the plan cuts `escapement` and `signal-fire` exactly where the films cut, and `parallel-space`
  at every film cut plus two.
- `vidgen/music-time` gains camera paths (`orbit`, `pathPoint`, `flyThrough`), a colour script
  (`colourScript`) and `reactions` (a drafted page's pulse, glow, drop flash, rings and glints).

- **Building blocks for music videos**: two of vidgen's own modules for `web` scenes, imported by
  name like `vidgen/three-finish`. `vidgen/music-time`: the score's tracks as arrays
  (`trackArrays`), drum and note envelopes, the melody's gliding pitch, a track's level through
  its hairpins, bar lengths, seeded numbers, easing, camera keyframes. `vidgen/three-kit`: glowing
  strokes, glass crystals, a tesseract, a nebula sky, portals, star fields, flares, shock rings,
  note glints, the melody as a ribbon, spectrum rays, tunnels, a corridor, great rings, swarms,
  dust, a camera aim (`docs/CONFIG.md`, `web`; `vidgen guide web`; COOKBOOK-3D section 9).
- The examples use them instead of their own copies, with pixel-identical stills:
  `examples/parallel-space` (`ps.js` 1,313 → 799 lines), `examples/escapement` (1,238 → 1,187),
  `examples/signal-fire` (220 → 200), `examples/three-finish`. Parallel Space now reads the music
  through `music_data`; its `ps_audio.json` and `scripts/make_ps_audio.py` are gone (the same hits
  and notes; spectrum and level measured from the mix: stills 53.5 dB PSNR or closer).

### Gallery (Steps 356–358.1, 371.1, 377.1)

- Step 377.1: three more YouTube Shorts after the six under "Shorts" (`YOUTUBE_SHORTS`), nine thumbnails in the row.
- Step 371.1: six YouTube Shorts under "Shorts" in the gallery's "Videos on YouTube": one row of clickable thumbnails (180 px high, as the gallery's previews), each linking to its `youtube.com/shorts/<id>` page (`YOUTUBE_SHORTS` in `src/vidgen/gallery.py`); `gallery.youtube_id()` also reads `youtube.com/shorts/<id>` links.
- Step 358.1: the gallery's "Videos on YouTube" section shows only the clickable thumbnails (the title is the alt text); the title/channel lines and the `channel` field are gone.
- Step 357: each YouTube video in the gallery shows its clickable thumbnail (YouTube's own `img.youtube.com` image, nothing stored in the repository), then its title and channel; `gallery.youtube_id()` reads the id from `youtu.be/<id>` and `youtube.com/watch?v=<id>` links.
- The scene gallery ends with "Videos on YouTube": links to videos made with schu-video-generator (`YOUTUBE_VIDEOS` in `src/vidgen/gallery.py`); the README points to it.

### "Parallel Space" as an example (Step 355)

- **`examples/parallel-space`**: the 3:05 trance and choir music film "Parallel Space" (v7), source only (score unchanged, `video.yaml`, one three.js module, its audio data file and the script that rebuilds it, the `web_cut` type, README). Listed in the README and the scene gallery ("Pictures and media"); `tests/test_parallel_space_example.py` (validate only).

### Docs (Step 354)

- The music and 3D cookbooks' descriptions (README, `docs/COOKBOOK.md`) name their Phase AL
  sections; `docs/WINDOWS-CHECK.md` has a step 7 for web stills, compact intermediates and their
  deletion, the progress line, music data and the orchestral score.

### "Escapement" as an example (Step 352)

- **`examples/escapement`**: the published 3:11 clockwork music film, source only (score,
  `video.yaml`, one three.js module, the `web_cut` type, README). Its pictures now get the score
  through `music_data` / `ctx.music` instead of the film's hand-written exporter and JSON file;
  stills of all twelve scenes are pixel-identical to the film's, and the score is unchanged (its
  render has the same SHA-256). The film's own finishing is kept. A full render takes about
  1 h 30 min to 2 h on 2 cores; `vidgen still` and `--draft` for quick looks. Listed in the README
  and the scene gallery ("Pictures and media"); `tests/test_escapement_example.py` (validate only).

### Phase AL in one place: what three music films asked of the generator (Steps 341–351)

Three music films made with vidgen ("Parallel Space", "Escapement") reported limits; Steps
341–350 built all of them, Step 351 reviewed them. In short:

- **Score files got an orchestra**: `trumpet`, `horn`, `low_brass`, `organ` (343); `violins`,
  `violas`, `cellos`, `double_basses` with `stroke: sustain | spiccato | tremolo | pizzicato` (344);
  `timpani`, `toms`, `taiko`, `bass_drum`, `frame_drum`, `snare_drum`, `cymbal`, `tam_tam`, `choir`
  (345). One table of every instrument: `docs/COOKBOOK-MUSIC.md` section 13.
- **Expressive notes** (346): dynamics `[pp]`–`[fff]`, hairpins, `fp` / `sfz`, slurs with a glide,
  vibrato speed and delay, settings per note (`[pizzicato]`, `[roll]`), an instrument per section,
  range warnings. Scores without marks play the same samples as before.
- **Pictures that follow the music** (347): `music_data: true` on a `web` scene gives its page
  `ctx.music` (the mix measured per frame, the score's hits and notes in song time); no script of
  your own.
- **Rendering `web` scenes**: an edit to the script of a scene whose type subclasses `Web` renders
  it again (341); `vidgen still` draws single frames without rendering (342); `render.intermediate:
  compact` and `keep_intermediates: false` for small disks (348); quicker screenshots and a
  progress line (349); `vidgen/three-finish`, a ready-made finish for three.js pages (350).
- **Step 351**: the guide's music code block runs in the test again; a flaky test made robust;
  `vidgen studio` shows named settings (`stroke`, `registration`, `vowel`, `voices`, `morph`) as a
  list of their names; `3d` scenes write their frames clip beside the drawing with a `3d frames`
  progress line (same pixels); the cookbook's table of all instruments; a worked example,
  [examples/signal-fire](examples/signal-fire/README.md): an original 24 s orchestral cue with
  expressive marks and a three.js night scene that reads it through `ctx.music`, finished with
  `vidgen/three-finish`. Review findings: DESIGN §120.12.

### Finishing for three.js `web` scenes: `vidgen/three-finish` (Step 350)

- **A ready-made finish** for a three.js page: `import {Finish} from "vidgen/three-finish"`, `new Finish(renderer, scene, camera, ctx, {...})`, `finish.render(t)` in `frame`. Depth of field from the depth buffer (a thin lens: focus distance, object or point, f-stop and scene units, or a blur in pixels; three quality levels), motion blur on the video's clock (the page's `update(t)` called at sub-frame times across a shutter angle and averaged; exactly no blur at shutter 0), bloom on highlights only, ACES / AgX / neutral tone mapping with exposure, a grade (temperature, tint, saturation, contrast, lift, gamma, gain, a linear filter; any option may be a function of time), vignette, chromatic fringe, film grain seeded by the frame, FXAA; one sRGB encoding (with every effect off it draws what `renderer.render` draws, within one level). Deterministic: two renders give the same frames.
- **Helpers**: `studioEnvironment` (soft boxes baked through PMREM for metal), `nebulaSky` (a seeded nebula and stars baked into a cube map), `surfaceFinish` (brushed, Geneva stripes, perlage, circular graining, sunray normal and roughness maps), `softShadows` (three.js 0.186 has no `PCFSoftShadowMap`: PCF with a radius is recommended, VSM measured), `focusDistance`, `warmUp` (compiles the shaders in `load`; `compileAsync` would never resolve there).
- **Cost** at 1280x720 on 2 cores (software WebGL): the passes add 0.01–0.14 s each to a 0.47 s scene; motion blur costs a whole scene drawing per sample (DESIGN §120.11 has the table). A page that does not import the module is unchanged; one that does has it in its cache keys.
- A worked example, `examples/three-finish`; a copy of three "Escapement" scenes ported to the module came within 28–34 dB PSNR of the film's stills. Docs: the guide ("Finishing three.js scenes"), CONFIG (`web`), `docs/COOKBOOK-3D.md` section 8. Tests: `tests/test_web_three_finish.py`.


### Faster `web` rendering, a progress line (Step 349)

- **Faster frames, the same pixels.** A `web` scene's screenshot is now the PNG Playwright gives, compressed quickly (`Page.captureScreenshot` with `optimizeForSpeed`), and the frames clip is decoded and encoded while the next frame is drawn. On 2 cores: a detailed three.js film page 1.61 → 1.24–1.30 s a frame at 1280x720 (a 3 s scene 165 s → 135 s; the whole "Escapement" film estimated at about 1 h 45 min instead of 2 h 10 min), flat SVG pages about 20 % faster. The frames are identical to before (checked frame by frame on WebGL and SVG pages, at 720p and preview size, with alpha, in a body region and with `design_width`); no cache key changed, so nothing is drawn again.
- **A progress line while frames are drawn**: `[4/12] 04_escapement: web frames 120/482, 1.24 s a frame, about 7 min 29 s left` about every 10 s, then a summary that splits a frame's time into the page's `frame(t, ctx)` and the drawing with the screenshot. Also on stderr with `--json`, so the MCP `render` tool reports it as progress.
- **No shader warm-up needed**: the first frame a page draws may take 30 s (the others 10 s), so compiling three.js shaders there no longer risks the time limit.
- Measured and not taken (DESIGN §120.10 has the table): WebP or JPEG screenshots, reading the WebGL canvas back, `Page.startScreencast`, `HeadlessExperimental.beginFrame`, other software-GL flags, two pages or split scenes, lazy imports. `--jobs 2` was about 10 % faster than one job on a two-scene WebGL test. `performance.now()` stays on the video's clock (documented).

### Smaller intermediate files (Step 348)

- **`render: {intermediate: compact}`** (`vidgen render --intermediate compact`, MCP `intermediate`) keeps the frames a `web` or `3d` scene draws as H.264 4:4:4 (CRF 12) with a lossless alpha stream instead of lossless FFV1: about 4.6 times smaller for a WebGL page (5.5–6 MB/s instead of 26–28 MB/s at 720p30). One more lossy step, measured: the scene clip ends 0.04–0.24 dB further from the page than when made from lossless frames. Lossless stays the default and is unchanged (no setting was smaller at the same speed).
- **`render: {keep_intermediates: false}`** (`--clean-intermediates`, MCP `clean_intermediates`) deletes a scene's frames clip once the scene is rendered and every scene's after the join; edits are still noticed; a scene rendered again later draws its frames again.
- **`vidgen render`** warns before it starts when the disk may be too small for the frames clips and prints the build folder's size after the join (`build:`; `--json`: `disk`).
- Measured on the films' frames; details in DESIGN §120.9, docs in `docs/CONFIG.md` ("Intermediate files and disk").

### Music data for `web` scenes (Step 347)

- **`music_data: true`** on a `web` scene gives its page `ctx.music`: the video's music measured at every video frame (spectrum bands, level, low end, onsets; each 0..1) and, when the music is a score file, every track's drum hits and notes with pitch, instrument, dynamic, stroke and slur. No script of your own and no JSON beside the page; the song time of the scene's start is worked out (`ctx.music.t0`, `ctx.music.now()`).
- Functions on the page: `band(i)`, `bands()`, `level()`, `low()`, `onset()`, `hits(track, T0, T1)`, `notes(...)`, `last(track)`, `sounding(track)`, `pulse(track, decay)`, `section()`. Options: `{bands: 32, tracks: [kick, hook], t0: 41.6}`.
- It measures what the video plays (the cue's start, loop, volume, fades, scene levels), from the music the join renders anyway; made once and kept in `build/music`. An edit to the score draws the scenes that use it again; other scenes are not affected and keep their cache keys.
- It replaces the films' own scripts: on "Parallel Space" and "Escapement" the same numbers within the films' own rounding, the same hits and notes, and stills of a page using `ctx.music` equal (or within 11 of 255 levels) to the original. Docs: `docs/CONFIG.md` ("Music data"), the guide ("Pictures that follow the music"), `docs/COOKBOOK-MUSIC.md` section 12. Tests: `tests/test_web_music.py`.

### Expressive notes in score files (Step 346)

- **Dynamics per note.** Marks in square brackets before a step in a track's `steps`: `[pp] [p] [mp] [mf] [f] [ff]` (also `ppp`, `fff`, or dB: `[-6]`), in force until changed; an unmarked note is `mf`. On brass, strings, the choir and the orchestral drums a dynamic changes the tone as well as the level: louder brass is brighter, louder strings brighter with more bite, a louder choir fuller, a louder drum struck harder. The organ, pads and older instruments change level only.
- **Shapes.** Hairpins `[p <] ... [f]` and `[f >] ... [p]` move the level from their step to the next dynamic: inside one held note (a crescendo whose tone opens as it grows) or over a phrase. Swells, `[fp]` and `[sfz]`.
- **Slurs and glides.** `(A4 - C5 - E5 - - -)` is one bow or breath: no new attack, the pitch glides in `glide` seconds (0.06 legato, 0.2–0.4 a portamento; `[glide=0.3]` for one note), the vibrato goes on. On `trumpet`, `horn`, `low_brass`, the strings (sustained, tremolo), `choir` and `soft_lead`.
- **Vibrato** speed and delay: the settings `vibrato_speed` and `vibrato_delay` beside `vibrato`, per track, section or note.
- **Settings per note** with the same marks: `[pizzicato] D3 [spiccato] D3 D3 [sustain] G3 - -` on one strings track, `[roll pp <] A2 - - - | [hit ff] D2` on one timpani track, `[pitch=100] x` on a taiko. `[default]` returns to the track's settings. `touch: 1` makes the old accents (`X`, `!`, `accent:`) bite too.
- **An instrument per section**: `sections: {lift: {instrument: trumpet}}` on a track.
- **Range warning**: notes outside an instrument's written range are reported by `vidgen music render` and `vidgen music check` (they still play).
- A duck with `follow: true` follows the hits' dynamics. Every mistake in a mark is an error naming the mark and the nearest word.
- Existing scores are unchanged: "Escapement", "Parallel Space" and twelve demo scores of Steps 343–345 render to the same bytes as before.
- Docs: `docs/CONFIG.md` ("Expressive notes"), `docs/COOKBOOK-MUSIC.md` section 11, the guide ("Expression"). Tests: `tests/test_studio_expression.py`.

### Orchestral percussion and a choir for score files (Step 345)

- Nine new instruments for score files, synthesised like the others (no samples, no SoundFont), in two new families of `vidgen music patches`, `percussion` and `choir`.
- **Timpani and toms, played by note name.** `timpani` (written D2–A3) ring in a kettledrum's own overtones (1 : 1.5 : 2 : 2.44 : 2.9, not a harmonic series), lower drums longer. `toms` are concert toms from a floor tom (G1) to a high tom (C5); the pitch falls to the note after the blow (`drop`). Both take `stroke: roll`, a `mallet` from soft felt (0) to hard wood (1) and `ring` (how long a note sounds before it is damped). The `kick`, which films had used for toms, stops at 160 Hz.
- **Big drums, played as drum steps.** `taiko` (a hard attack and a long low tail; `players: 6` is an ensemble spread from left to right), `bass_drum` (a concert bass drum), `frame_drum` (`edge` moves the stroke from the middle to the rim), `snare_drum` (`stroke: roll`, `players` for a line of drums). Each has a `pitch` in Hz.
- **Metal.** `cymbal` (a suspended cymbal: a crash, or `stroke: swell`, a mallet roll that grows until its held steps end) and `tam_tam` (a gong whose highs arrive after the blow). The `riser`, `open_hat` and `gated_snare` do not cover these: a noise sweep without ring, 90 ms, and 0.27 s without a roll.
- **`choir`** holds a vowel: `ooh`, `aah`, `eeh`, `mm`, `oh` or `ee`, by formant synthesis with the formants of basses, tenors, altos and sopranos. `voices: mixed` gives each note to the kinds of voice that reach it; `men`, `women` or one kind choose. 8 singers a note by default, each with its own tuning, vibrato and entry. `morph` turns a held note into another vowel. It is a choir pad: it sings no words and will not pass for a recorded choir.
- Every blow at the same settings is the same samples, and a drum is made once per setting: 256 sixteenths cost about what the `kick` costs.
- Levels: `taiko` and `bass_drum` are as loud as `kick` and `boom` at `volume: 0`; the choir is as loud as the strings and the brass.
- Existing scores are unchanged: the scores of the films "Escapement" and "Parallel Space" render to the same bytes as before.
- Docs: `docs/CONFIG.md` (score files: the instrument table, "Orchestral percussion", "Choir"), `docs/COOKBOOK-MUSIC.md` section 10, the guide ("Making music"). Tests: `tests/test_studio_percussion_choir.py`.

### Bowed strings for score files: `violins`, `violas`, `cellos`, `double_basses` (Step 344)

- Four new instruments for score files, synthesised like the others (no samples, no SoundFont): `violins` (G3–C7), `violas` (C3–E6), `cellos` (C2–A5) and `double_basses` (C1–G4). Each is a section by default (6, 5, 4 and 3 players, up to 12; `players: 1` is a solo instrument). `vidgen music patches` lists them in a new family, `strings`.
- **Four strokes**, chosen by the setting `stroke`: `sustain` (bowed for as long as the steps hold the note; notes without a rest between them overlap into a legato), `spiccato` (one short stroke per note; `length: 0.15` and more is a staccato), `tremolo` (a held note of fast bow strokes, 13 a second by default) and `pizzicato` (plucked; it rings until its steps end, low notes longer). A section of the piece can change the stroke.
- **Even ostinatos.** Every spiccato stroke of a pitch is the same samples, and all pitches are equally loud (within 1 dB over each range), so sixteenths at 138 BPM and faster are even. The `pad` played note by note, which the film "Parallel Space" had to use, differs by up to 8 dB from note to note.
- **The instrument's body is in the tone**: resonances at fixed frequencies that do not move with the note, a different piece of wood for every player of a section, and a vibrato that moves each harmonic's level with the pitch. A section's players are a few cents and milliseconds apart with their own vibrato; its level is steady while its harmonics beat.
- Settings: `attack` (0.02–4 s: a firm stroke, a smooth one, a swell), `brightness` (0 bowed over the fingerboard, dark; 1 at the bridge, glassy), `vibrato` (cents, delayed), `accent` (the bite of a stroke), `length`, `speed` (tremolo), `decay`, `bow` (rosin noise), `mute` (con sordino), `detune`, `ring`.
- Their level is that of the brass (a held note about −16.6 LUFS before the piece is levelled). A score that used a `pad` as violins will want the new instrument about 8 dB up.
- The existing `pizzicato` instrument is unchanged. Existing scores are unchanged: the scores of the films "Escapement" and "Parallel Space" render to the same bytes as before.
- Limits: no slur or glide between notes, every stroke of a pitch is the same, and the track's `accent:` pattern changes a stroke's level but not its bite.
- Docs: `docs/CONFIG.md` (score files: the instrument table, "Bowed strings"), `docs/COOKBOOK-MUSIC.md` section 9, the guide ("Making music"). Tests: `tests/test_studio_strings.py`.


### Brass and organ for score files: `trumpet`, `horn`, `low_brass`, `organ` (Step 343)

- Four new instruments for score files (`vidgen music render`, `assets/music/NAME.yaml`), synthesised like the others (no samples, no SoundFont): `trumpet` (a solo trumpet, E3–C6), `horn` (a French horn, B1–F5), `low_brass` (a trombone section, E1–F4, with `tuba` a tuba an octave under it) and `organ` (a drawbar organ, C1–C7). `vidgen music patches` lists their settings under the new families `brass` and `organ`.
- **Brass gets brighter as it gets louder.** `brightness` (0 soft and dark to 1 blaring) changes the harmonics and not the level; inside a note the tone follows the level, so a note opens as it speaks and a long `attack` (up to 4 s) is a swell that starts dark. The pitch starts a little flat, as lips do; vibrato begins 0.3 s into a note. `players` above 1 is a section in unison (a few cents and milliseconds apart, in stereo, as loud as one player); `mute` on trumpet and horn.
- **Organ registrations by name**: `registration: cathedral` (principals 16' 8' 4' with mixtures, the default), `principal`, `flute`, `reed`, `drawbar`, `full`; or your own nine drawbars, `drawbars: "00 8400 000"` (in quotes). A note holds steadily and every note has the same level. Options: `chorus` (a second, detuned pipe per rank: a slow beating; off by default), `detune`, `chiff`, `click` (a key click; off by default), `tone`.
- A setting can now have named values (`registration: flute`; the number works too). An unknown name is reported with the closest one.
- Their levels match piano chords (a held note about −16.5 LUFS before the piece is levelled; `soft_lead` is −20.4, a `saw_pad` chord −10), so they start at `volume: 0`. A score that used a saw pad as brass will want the new instrument about 6 dB up.
- A track plays the same note the same way every time; two tracks in unison are two players.
- Limits: no slur between notes (each note has its own attack), no valve noise, no flutter-tongue; the organ has no swell box, tremulant or Leslie. In `vidgen studio` the `drawbars` setting shows as a plain slider: type the digits in the score instead.
- Existing scores are unchanged: no existing instrument, default or cache key was touched, and the scores of the films "Escapement" and "Parallel Space" render to the same bytes as before.
- Docs: `docs/CONFIG.md` (score files: the instrument table, "Brass and organ"), `docs/COOKBOOK-MUSIC.md` section 8, the guide ("Making music"). Tests: `tests/test_studio_brass_organ.py`.


### `vidgen still`: one frame of a `web` scene at an exact time, without rendering it (Step 342)

- New command: `vidgen still PROJECT --scene ID --at SECONDS` writes that frame of a `web` scene's page as a PNG (`exports/stills/<scene>_<seconds>s.png`, or `--out FILE|DIR`). It is the picture the render draws for that frame: vidgen builds the scene as a render does and opens the page with the same theme, `data:`, beats, size and frame rate. Compared pixel for pixel with rendered lossless page clips in a test, and with eight frames of the film "Escapement" at 1280x720.
- `--at` is seconds from the scene's start and takes lists and repeats (`--at 0,4,8,12`); `--frame N` names a frame; `--count N` spreads N stills over the scene. Stills in increasing order are drawn on one page in one browser.
- `--size final|preview|draft|WIDTHxHEIGHT` (default final); `--sheet FILE [--columns N]` adds a labelled contact sheet; `--transparent` keeps the page's alpha (default: over the video's background colour); `--json`.
- A page that keeps state from frame to frame (a simulation stepped per frame, Motion or lottie-web playing by themselves) shows a still as if the frames before had not been drawn; `--exact` steps through every frame first, as a render does (slower).
- Works for the type `web` and for extension types that subclass it; another scene type is an error naming `vidgen storyboard --scene ID`. Nothing is written under `build/<quality>/`.
- Measured on "Escapement" (2 cores): page ready after about 9 s, then 2.2 s per still at 1280x720, 0.5 s at 640x360, 0.3 s at 320x180.
- MCP: the `still` tool (returns the pictures). Guide: `vidgen guide web`, "Looking at single frames". DESIGN §120.3; tests `tests/test_web_still.py`.

### Fixed: an edited script of a `web` scene of your own type was not rendered again (Step 341)

- **Fixed:** a scene of an extension scene type that subclasses the `web` scene (for example `@scene("web_cut") class WebCut(Web): outro = 0.0`) was reused after an edit to its `script:` / `page:` file or to a file the page imports or fetches; only `vidgen render --force --scene ID` rendered it again. The render fingerprint looked at these files only for the type named `web`. It now does for every type whose class subclasses `Web`. Found in the music film "Escapement"; reproduced in a small project of the same layout before the fix.
- After updating, each scene of such a type is rendered once more (its stored render may be out of date). Its frames are drawn again only if the script or a loaded file differs from what was recorded. Scenes of type `web` are not affected.
- **Fixed:** `vidgen render --force` did not draw the frames of such a scene again when its files were unchanged.
- **Fixed:** a `script:` module that awaits several `fetch()` calls one after the other at its top level failed in about one run in three with `did not become ready within 30 s` (6 of 14 opens of a module with two fetches; 0 of 14 after). vidgen looked once and then waited on a timer of the page, which is vidgen's own clock and stands still before the first frame.
- Not covered: an extension scene type that does not subclass `Web` and calls `make_web_clip` itself. DESIGN §120.1, §120.2; tests `tests/test_web_extension_cache.py`.
- This step opens Phase AL ("What three music films asked of the generator", Steps 341–351) in `tasklist.md` and DESIGN §120.

### A fast draft of a video with `web` scenes; the README names the six kinds of scene (Step 340)

- No new option: `vidgen render --draft` (240 px on the shorter side at the video's shape, 8 fps, its own `build/draft`; `draft: {width, height, fps}` sets another size) already draws a `web` page at that size. It is now documented and measured for `web` scenes: about 2.5 times faster than `--preview` on two 20 s trial pages (an HTML + SVG page 36 s against 99 s, a three.js dashboard 54 s against 127 s, on a slow 1-CPU machine).
- **Corrected:** the guide and `docs/CONFIG.md` said "a whole preview render at 480x270, 12 fps, about 2 s per second". That was a project whose `preview:` had been set to that size; the default preview is 854x480 at 15 fps and cost 4.9 and 6.3 s per second on those pages. Both now have one measured table (draft, preview, final).
- Guide (`vidgen guide web`, "Render cost"): a page must scale (`vw` / `vh` / `%`, the theme's size variables, or `design_width`) to look right in a draft; lint and the storyboard never use a draft, so its small text causes no `min_font` finding. The workflow step and `vidgen render --help` name the draft for any video, not only cartoons.
- README: a third block lists the six kinds of scene (Python-based presentation scenes, 3D, 2D cartoon, isometric cartoon, web, video-model shots), each linked.


### `design_width`: a `web` page built in fixed pixels needs no rewrite (Step 339)

- New param on `web` scenes: `design_width: 1280` (200 to 8192), the window width in CSS pixels the page was designed for. The page is laid out in a window that wide and as high as its region's shape gives, and drawn at the video's size at every quality: `innerWidth`, `100vw`, media queries, `getBoundingClientRect()` and `clientWidth` are the design's pixels, `window.devicePixelRatio` is output pixels per CSS pixel (1.5 for 1280 at 1920x1080). HTML text, SVG and CSS shapes are drawn at the output's resolution (Chromium's device scale factor; no enlarging).
- A canvas is sharp only when its code multiplies its size by `devicePixelRatio` (three.js: `renderer.setPixelRatio(window.devicePixelRatio)`); otherwise it is drawn at the design size and enlarged. `ctx.width` / `ctx.height` and the canvas of a `script:` are the design window in CSS pixels; `ctx.frame` stays output pixels; the theme's sizes still draw text as tall as vidgen's.
- The frames are always exactly the output's size: the window's height is rounded up to a whole CSS pixel and the rows over are cut off the bottom (under one CSS pixel of the page).
- Lint judges the output size: 12 px text of a 1280 design is 18 px in a 1920 px frame. **Fixed:** the `cut` of a text declared with `layout(t, ctx)` was not scaled to frame pixels when the page was not drawn 1:1.
- Without the param nothing changes and stored `web` clips are reused (their keys are the same).
- Guide: "Porting a page built in fixed pixels" in `vidgen guide web`; `docs/CONFIG.md` `web`; DESIGN §118.17.

### A project's own fonts: the `fonts/` folder (Step 338)

- vidgen uses the `.ttf`, `.otf` and `.woff` files in a project's `fonts/` folder for the whole video, with no installation: name the family in the theme (`theme: {font: "Space Grotesk"}` or a role in `fonts:`) and titles, captions, every built-in scene and the designed thumbnail are drawn in it; a `web` page gets an `@font-face` per file, so `font-family: "Space Grotesk"` and `var(--vidgen-font-body)` work there. The family, weight and style are read from each file. Changing a font file renders every scene again. `.woff2` files are not read (`vidgen validate` says so).
- A `web` page that links Google Fonts gets a warning that names the family and says what to do, once per family: `scene 'x': the page asks Google Fonts for "Space Grotesk", but the internet is off during a render, so that text is drawn in a fallback font. Put the font's .ttf, .otf or .woff file in the project's fonts/ folder and remove the link to Google Fonts (see "Using another font" in `vidgen guide web`).`
- **Fixed:** Manim's cache of laid-out texts is named by the family, so a text first drawn in a fallback font kept that font after the font became available. With files in `fonts/` the cache follows them.
- Guide: "Using another font" in `vidgen guide web` (two ways to get a font's files, both tried); `docs/CONFIG.md` "Fonts".
- `fonttools` is now named in the dependencies (every install already had it through fpdf2).

### Relative paths in a `script:` web scene; `render --scene` says what else it renders (Step 337)

- **Fixed:** in a `web` scene with `script: extensions/x.js`, a relative URL is relative to the script's folder: `fetch("data.json")`, an image's or video's `src`, a CSS `url()`, `new URL(x, document.baseURI)` and a three.js loader's path name files beside the script. Before, they named files in vidgen's own page folder (`/__vidgen__/data.json`: not found). vidgen's page for a script now has a `<base>` of the script's folder. `new URL("./x.glb", import.meta.url)` and relative imports work as before; `page:` scenes are unchanged. Every `web` clip is drawn again once (the page file is part of the cache key).
- `vidgen render --scene ID` on a quality or variant never rendered before (`--preview`, `--draft` and each `--variant` keep their own renders) renders every scene, as before, because the video is joined from every scene; it now prints which scenes it adds and why (`--scene lines: also rendering 3 other scene(s) (one, three, four): ...`). `vidgen render --help` says so for `--scene`, and that `--force` with `--scene` renders only those scenes.

### Animation and chart libraries for `web` scenes (Step 336)

- A `web` scene can import five libraries by name, shipped with vidgen (about 1.43 MB with their licences; each one build file of its npm package, unmodified): `import {animate} from "animejs"` (anime.js 4.5.0, MIT), `import {animate} from "motion"` (Motion 14.12.0, MIT), `import * as d3 from "d3"` (D3 7.9.2, ISC), `import Chart from "chart.js/auto"` (Chart.js 4.6.1, MIT) and `import lottie from "lottie-web"` (lottie-web 5.13.0, MIT). Each was run under vidgen's clock; `vidgen guide web` has a table saying how to drive each (which play by themselves frame-exactly, which need a seek from `frame(t)`).
- GSAP is not shipped: its files say "All rights reserved. Subject to the terms at https://gsap.com/standard-license". `import gsap from "gsap"` stops the render with a message saying so and how to use a copy in the project; a copy works under the clock (`gsap.ticker.lagSmoothing(0)`, or a paused timeline and `tl.time(t)`).
- **Fixed:** an animation's `startTime` (Web Animations API) is on vidgen's clock. Before, a page (or a library: Motion does it) that set `animation.startTime` let that animation run in real time until the next frame, so a frame could differ from one render to the next (seen: in five renders Motion's first frame drew a box 10, 10, 10, 11 and 17 px from its place).
- **Fixed:** two renders of a `web` scene could differ in one edge pixel when a script moved content at a fractional position in a `requestAnimationFrame` callback (seen with a Lottie SVG at half size, and with plain `setAttribute`). `web` scenes now start Chromium with `--disable-partial-raster`; every `web` clip is drawn again once.

### Every test passes (Step 335)

- **Fixed:** importing `vidgen.render.worker` no longer loads Manim (it imported `vidgen.three_d.passes` at the top since Step 301). `vidgen.lint` imports the worker for two path functions, so `import vidgen.lint`, and with it `vidgen.cartoon.lighting`, `vidgen.cartoon.wind`, `vidgen.cartoon.iso_weather` and `vidgen.cartoon.iso_stage`, loaded Manim too. The worker now imports the passes when it runs. No command's output changes.
- Tests only: the 53 tests that were failing (HANDOFF.md, Steps 327 and 335) pass, except one marked as an expected failure for a known bug (`scenes/video_clip.py` imports modules outside `vidgen.api`; `tasklist.md` backlog). `tests/conftest.py` makes a relative `PYTHONPATH` absolute, so `PYTHONPATH=src python -m pytest` tests the working tree in render workers too.

### three.js add-ons for `web` scenes (Step 334)

- A `web` scene can import a chosen set of three.js add-ons, shipped with vidgen (three.js 0.186.1, MIT, about 390 kB): `GLTFLoader` (`.gltf` and `.glb` models), `BufferGeometryUtils`, `RoomEnvironment`, bloom (`EffectComposer`, `RenderPass`, `ShaderPass`, `UnrealBloomPass`, `OutputPass`), `CSS2DRenderer` labels, thick lines (`Line2`, `LineGeometry`, `LineMaterial`, `LineSegments2`, `LineSegmentsGeometry`), `RoundedBoxGeometry`, `SVGLoader` and `OrbitControls`. Import them as three.js's docs do: `import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js"` (the older `three/examples/jsm/…` works too); they share the page's one `THREE`.
- Not shipped: 3D text, Draco / KTX2 / Meshopt decoders, other loaders and controls, VR / AR, physics, exporters, the GUI helper, WebGPU. Importing one stops the render with a message that names it and says how to copy the file into the project instead (before, Chromium's "Failed to resolve module specifier").
- `vidgen guide web` has a table of the add-ons, an example (rounded box, environment light, bloom, an HTML label) and the rules found under vidgen's clock: load files in a `script:` with `new URL("./x.glb", import.meta.url)`, give a composer's scene a background (its picture is opaque), set `LineMaterial.resolution`, call `OrbitControls.update(t - last)`.

### `web` scenes taught and shown (Step 333)

- `vidgen guide web` (also `html`, `css`, `javascript`, `canvas`): when to write a `web` scene rather than use a built-in, `3d`, `video_clip` or a Python extension; the two forms with minimal working examples; what follows the video's time and what does not; the `ctx` table; theme variables and fonts; revealing on beats and on spoken words; `data:`; three.js; `region` and transparency; one page for 16:9 and 9:16; no internet; the lint loop; the usual mistakes with their messages; the render cost.
- `examples/web` ("Where rain comes from"): an HTML and CSS page whose cards come in on narration beats, a canvas rain gauge whose text is declared to lint with `layout()`, and a hand-written three.js planet whose camera moves on beats; validate and lint clean at 16:9 and 9:16.
- The scene gallery has a `web` entry (`docs/gallery/web.md`); `vidgen gallery` ships the page the guide's snippet names.
- **Fixed:** in a `layout(t, ctx)` declaration, `font` may now be the canvas font the text was drawn with (`"700 28px Inter"`) as well as a family (`"Inter"`); the canvas font form used to be measured as a tiny cap height, so `min_font` reported the text as about a tenth of its size.
- `docs/EXTENDING.md` has a section on `web` scenes beside Python extensions (project JavaScript is trusted as `extensions/` Python is); `docs/CONFIG.md` `web` reordered into one reference.

### Lint reads a `web` page (Step 332)

- `vidgen lint` now checks the text a `web` page shows: at each still it asks the page for every element that holds visible text (and SVG `<text>`): its box mapped to the frame, its size as drawn (CSS transforms included), colour, what is behind it, opacity, and what clips it. The existing rules run on it (`off_frame`, `text_overlap`, `min_font`, `contrast`, `safe_area`, `overlay_overlap`, `max_words`, `shorts_safe_area`, `covered_text`); a new rule `web_clipped` (error) reports text cut by its own box (`overflow: hidden`) or by the page's box with `region: body`. Text a later beat reveals is checked once it shows.
- `data-vidgen-id="gear"` names an element in the layout dump and in messages (`text 'Gears' (page: gear)`), else a short CSS-like path does; `data-vidgen-lint="off"` (or `"off:contrast"`) opts an element and its children out. Text drawn on a canvas cannot be read: a page or script declares it with `layout(t, ctx)` returning `[{id, text, box: {x, y, width, height}, size, color, background}]`.
- Text under the captions (in the part of the frame a `reserve: true` overlay keeps) is now one `safe_area` finding naming the overlay, for every scene type; `overlay_overlap` leaves it to `safe_area`.
- The layout dump has a `web` entry per still and the page's texts as objects (`class: WebText`), and a `reserved` list in its header; overlays carry `reserve`.
- The reading is taken while the clip is drawn and kept beside it (`<scene>.layout.json`), so lint reads no page again; a frame not read then costs one Chromium start and a step per frame without screenshots. Every web clip is drawn again once. `vidgen.api` adds `web_page_layouts` and `planned_still_frames`; `make_web_clip` takes `layout_frames=`.

### `web` scenes fit with the rest of a video (Step 331)

- `region: bleed` (the default: the page fills the frame) or `region: body` (the page fills the safe area under a `title` that vidgen draws, clear of bottom captions and of a Short's covered parts). With `body` the page is laid out at the region's own size: its viewport and `ctx.width` / `ctx.height` are the region's pixels. `title` draws a heading as on `3d` (a plate over the page) or `video_clip` (above it); action target `title`.
- Transparent pages: what a page leaves transparent shows the video's background, with exact blending of semi-transparent pixels. **Changed:** a page with no background used to show Chromium's white and now shows the theme's background; a `script:`'s bare page is now transparent (it was the theme background, so it looks the same). The frames are kept with their alpha (clips about 1.5× larger at 1080p, same speed).
- One page for every shape: `ctx.aspect` (`"16:9"`, `"9:16"`, `"1:1"` …), `ctx.orientation`, `ctx.frame`, `ctx.region`, and `<html data-aspect="9:16" data-orientation="portrait">` so CSS can switch layout (`[data-aspect="9:16"] .row { flex-direction: column }`).
- Checked with real renders: captions (karaoke too), `progress_bar`, `watermark`, `lower_third`, crossfade, push and wipe into and out of a `web` scene, `--draft`, a 9:16 variant and a Short, `vidgen storyboard`, `vidgen animatic`, `vidgen lint`, `vidgen validate`.
- Every web clip is drawn again once. `vidgen.api` adds `web_page_shape`; `make_web_clip` takes `shape=`.

### `web` scenes: what the page is given (Step 330)

- The theme reaches the page: CSS variables on `:root` (`var(--vidgen-primary)`, `--vidgen-background`, `--vidgen-palette-0`, `--vidgen-font-heading`, `--vidgen-size-body` …) and `ctx.theme`. vidgen's bundled fonts are declared with `@font-face` and served with no download, so a page's text matches a `title` scene's. A `script:`'s bare page uses the theme background (it was black).
- `params: {data: {...}}` (JSON values only, checked with the place of a bad value) arrives as `ctx.data`.
- `ctx.beats`: each narration beat's id, start, end, text and word times. `<body data-beat="b2" data-beat-index="1">` follows the beat and a `vidgen-beat` event fires when it changes, so plain CSS can reveal a part on its beat.
- `import * as THREE from "three"` loads the bundled three.js in a `page:` and a `script:`.
- Editing any file the page loaded (styles, modules, pictures, fonts, fetched data, also one first asked for on a later frame) renders that scene again, and only it; `vidgen render --force` draws the frames again. Every web clip is drawn again once.
- `vidgen.api` adds `web_page_inputs` and `web_json_problem`; `make_web_clip` takes `theme=` and `beats=`.

### `web` scenes: time belongs to vidgen (Step 329)

- A `web` page written the ordinary way now renders frame by frame and the same on every render: CSS animations and transitions, `element.animate`, `requestAnimationFrame`, `setTimeout` / `setInterval`, `Date`, `performance.now()`, SVG `<animate>` and `<video>` follow the video's time instead of the real clock. `Math.random`, `crypto.getRandomValues` and `crypto.randomUUID` give the same numbers for the same scene id. `Date.now()` starts at 2026-01-01T00:00:00Z, time zone UTC.
- New optional hook `load(ctx)` (may be async), run once before frame 0, after the page's fonts, pictures and videos are ready. `frame(t, ctx)` and pages written for Step 328 work unchanged.
- A `load` that does not return within 30 s or a frame within 10 s stops the render with the scene, the hook and the time, instead of hanging.
- Videos in a page can be seeked: the project folder is served with byte ranges.
- Every web clip is drawn again once (the clock is part of its cache key). `3d` clips are reused.

### `web` scenes: a page written in HTML, CSS and JavaScript (Step 328)

- New scene type `web`: `page: extensions/gears.html` (any HTML, CSS and JavaScript) or `script: extensions/gears.js` (a module drawn on one canvas that vidgen supplies). Before each frame vidgen calls the page's `frame(t, ctx)` (`window.vidgen.frame` on a page, an exported `frame` in a script), then takes a screenshot at the render's size and frame rate. The screenshots go into a cached clip, as for `3d`.
- The project folder is served to the page, so relative links to styles, pictures, fonts and modules work. A request to the internet is refused with a warning naming the URL.
- A missing file (also in `vidgen validate`), a JavaScript error at load or in `frame`, or a page not ready within 30 s stops the render with the scene, file and line.
- `3d` and `web` share one Chromium module (`vidgen/browser/`); existing 3D clips stay valid. The install hint now reads "3d and web scenes need Playwright and its Chromium".
- Measured on a 1-CPU machine: 1.4–2.1 s of drawing per second of video at 480x270 and 24 fps, 13 s at 1920x1080 and 30 fps.

### The default test run leaves the slow tests out (Step 327)

- `python -m pytest -q` now runs every test except those marked `slow`: 6258 of 8184 tests, 194 s on a 1-CPU machine (all tests: about 3.7 hours there). `-m slow` runs only the slow ones, `-m "slow or not slow"` everything; a test named by node id always runs. 1002 more test functions are marked `slow` (every one over about 0.4 s). No test was removed.

### A dissolve of a few frames where one generated take continues another, on request (Step 326)

- `video_clip`'s `match_previous` takes two more settings. `dissolve: N` (0 to 12, default 0) blends the clip's first N frames with the previous clip's last frame, held still, the previous frame's share falling in equal steps (N = 3: 75 %, 50 %, 25 %). N counts frames of the render being made (preview or final). `level: false` blends without the correction of brightness and colour. No frame is added or removed; durations and sound do not change.
- `match_previous: true` is unchanged: it never blends.
- Measured on four takes at preview size (mean absolute difference of RGB between the frame before and the first frame after each cut, 0 to 255): 7.09, 6.74 and 5.80 with `match_previous: true`; 2.75, 2.71 and 2.44 with `{dissolve: 3}`. Inside the shots the median is 0.61.

### No flash where one generated take continues another (Step 325)

- `video_clip` has a new param `match_previous: true | {seconds, hold}`. Where a clip continues the clip of the scene before (a take generated from its last frame, which video models draw about 8 % darker), its first frame is given that frame's brightness and colour, one gain per colour channel, and the correction eases away within `seconds` (default 1). No frames are blended or added; durations and sound do not change.
- Measured on four takes at preview size: the step in mean level at the three cuts goes from −7.4 … −7.8 % to within ±0.1 %.
- `vidgen validate` rejects the param where it cannot apply (no `video_clip` before, a transition, a fade, a region other than `bleed`); a pair of frames that is not a continuation is left alone with a warning.

### The director's cookbook: three traps removed (Step 324)

- `docs/COOKBOOK-DIRECTING-YOUR-AI.md`: Card 12 pins an accepted painted picture by its file before the stand-ins move, so that it is not blocked or quoted again; the example stand-in stands on the pier and the text says a stand-in's `position` is its centre; Card 6 uses one `--box` per panel when panels are not evenly spaced.

### An AI given only short prompts finds the cookbook's cards (Step 323)

- `docs/COOKBOOK-DIRECTING-YOUR-AI.md` opens with a section for the AI: each of the tutorial's 11 short prompts maps to its long cards and to the points where the AI must stop and wait, with the safety rules and the details that must not be left out. The README and the author guide point to it.

### A plain install brings every Python package (Step 322)

- `pip install` of schu-video-generator now installs fpdf2, faster-whisper, the MCP SDK, Kokoro and its Mandarin packages (Python 3.10-3.12), symusic and Playwright. The extras `pdf`, `stt`, `mcp`, `kokoro`, `music` and `3d` remain, empty, so older commands still work.
- A missing package is reported as an incomplete installation with the advice to reinstall schu-video-generator. No message or document tells a user to pip install a package. Chromium remains a separate download named in vidgen's own error message.
- Kokoro's Japanese voices are not available from a plain install: pyopenjtalk has no wheels and would need a C++ compiler.

### Generated video: a provider's error never shows the shared address; the mock shares nothing (Step 311)

- A provider's error that quotes a quick tunnel address no longer shows its secret path, wherever it appears: a failed job's error (which used to escape the redaction), submit and download errors, exception details, `ShotRun.message`, `--json`, MCP. This also works for a job polled by a later run, when the tunnel is long gone. Ledger lines never hold the path either.
- `provider: mock` no longer opens a real quick tunnel, even with `videogen.host: quick_tunnel`: it never starts `cloudflared` or shares a file. Its audio / video inputs get fake addresses, so the free demo runs end to end with no host setting and without `cloudflared`, and `vidgen generate plan` says the inputs stay on this machine. `vidgen generate host-test` still opens a real tunnel when you ask for it.

### Generated video: a killed vidgen cleans up after its quick tunnel (Step 310)

- A termination signal (SIGTERM, SIGHUP) now closes an open quick tunnel properly (`host_close` with reason `terminated (SIGTERM)`) and ends vidgen, without replacing a handler someone else set.
- If vidgen is killed outright (SIGKILL, a cancelled MCP call, Task Manager), a small watcher process stops `cloudflared` and deletes the temporary copies at once; on Windows a Job Object stops `cloudflared`. The next tunnel deletes folders left by a vidgen that is gone (never a running host's). Only if the watcher dies too can copies remain until then, and a `cloudflared` left running must be stopped by hand; it serves nothing.
- A second Ctrl+C during closing no longer abandons the cleanup: closing is finished step by step and resumed, and a concurrent close waits for the first. Windows parts of this are not exercised here (mocked).

### Generated video: a paid job does not lose its inputs or get paid twice (Step 309)

- During a paid run a quick tunnel now stays open until the job reaches a final state (or `host_max_minutes`): it no longer closes after every file was fetched, because a provider may fetch again after queueing the job. This is a longer exposure traded for not losing a paid job. **`videogen.host_grace_seconds` is removed**: like any unknown key, it now stops the config with a clear error; delete it from `video.yaml`.
- `host_max_minutes` defaults to 20 (was 15) and must be between 5 and 120. It must leave room for `poll_timeout` plus opening the tunnel and submitting; otherwise a shot with hosted inputs is blocked and the message gives the numbers. Lowering `poll_timeout` is how to keep the tunnel short on purpose.
- A paid submit is refused (nothing sent or paid) when its tunnel has closed or has too little time left; `url_of` refuses a closed tunnel.
- Before every paid POST a `submit_intent` line is on disk. A submit cut off by Ctrl+C, a crash or a lost answer has no known outcome: the next run does not pay for it again by itself, and `plan` / `run` / `status` / `ledger` say what happened. New `vidgen generate resolve --intent ID --not-charged | --job JOB_ID | --charged [--cost USD]` records the outcome. Until resolved it counts against the budget at its estimate.

### Generated video: no paid job from inputs that are out of date (Step 308)

- `vidgen generate inputs` now records what each cut file was made from in `build/videogen/<shot>/inputs.json`. When the scene, the beat's text or timing, the narration MP3 or the draft size changed afterwards, `vidgen generate plan` (text and JSON) blocks the shot and names the free command that cuts it again (`vidgen generate inputs`, with `--guide` when a render input changed).
- `vidgen generate run --pay` refuses the whole run on such a shot before anything is sent or a tunnel opens. Inputs cut before this version have no record and are blocked the same way: cut them again once.
- A shot whose clip or job already exists is still reused free, with a note. Picking a take or editing a shot's prompt does not count as a change. A narration MP3 that no longer matches its text asks for `vidgen tts` first.

### Generated video: a 3D scene's guide pass as a shot's guide (Step 307)

- `generated_shot.guide` now takes `true | false | render | depth | outline | mask`. `true` (= `render`) is unchanged: the beat's silent draft render. On a `3d` scene, `depth`, `outline` or `mask` sends that guide pass of the beat instead, so a video model follows the 3D layout and camera move while it draws the look. Elsewhere such a value is refused when the config is read; a misspelt value gets a did-you-mean.
- `vidgen generate inputs --guide` draws the pass with the scene's draft render (the 3D frames are reused; a current draft render is no longer rendered again) and cuts the beat's part exactly like `guide.mp4` (start, length, size, frame rate) into `build/videogen/<shot>/guide.<pass>.mp4`, converted from the lossless pass to H.264 / yuv420p (mask colours within a few levels inside each object; edges blend over a pixel or two). `first_frame: render` stays the normal render's first frame.
- The prompt says what the guide is ("The guide video is a depth map (near is white, far is dark): follow its layout and camera motion."); a mask guide also lists the stand-ins' colours by name. Changing the pass is a new request (never the cached clip). `vidgen generate plan` names the pass in the shot's guide line and in the "would share" list (`videogen.host: quick_tunnel`); without a host the shot is blocked as before.
- Cookbook: "From a 3D scene to a generated clip" (`docs/COOKBOOK-GENERATED-VIDEO.md` §6, linked from `docs/COOKBOOK-3D.md`): which pass to choose, the order of commands, the limits; new example `examples/3d-to-video`.

### Generated video: talking shots and guides through the quick tunnel (Step 306)

- New `videogen.host: none | quick_tunnel` (default `none`: nothing changes). With `quick_tunnel`, `vidgen generate run --pay` shares a shot's voice (`audio.mp3`) and guide render (`guide.mp4`) through its own Cloudflare quick tunnel: opened and checked just before the job is submitted (if the check fails, nothing is sent or paid), closed as soon as the job is completed or failed (before the download), or once the provider fetched every file plus `host_grace_seconds`, or after `host_max_minutes`, whichever comes first. One tunnel per shot, so no file stays reachable while other shots are made. Talking shots (heygen/avatar-iv lip-sync) and shots with `guide:` can now be paid for.
- `vidgen generate plan` no longer blocks those shots when the host is on, and lists per shot exactly which files a run would share, their sizes and the tunnel's maximum lifetime (JSON `shared`, `share_max_minutes`); without `cloudflared` the shot is blocked with the install hints; without the host the blocked reason names `videogen: {host: quick_tunnel}`.
- A provider error that quotes a shared URL is shown with the secret part replaced by `<secret>`.
- MCP: `generate_host_test` (the free check); `generate_plan` / `generate_run` follow the CLI.
- Safer sharing: a file reached through a linked folder inside the project (or a Windows junction) is refused; the public check accepts a `HEAD` answer without `Content-Length` (still refuses a wrong one); on Windows without `taskkill` cloudflared itself is stopped.
- Cookbook section "Sharing voice and video inputs safely", with a "Test on Windows" walkthrough (install, `host-test`, a dry plan, one paid talking shot).

### Generated video: sharing audio / video inputs through a Cloudflare quick tunnel (Step 305)

- New `vidgen.videogen.host`: shares exactly the given files (copies under random names in a temporary folder outside the project; links refused) from a tiny local server on 127.0.0.1 that answers only `GET` / `HEAD` of `/<secret>/<name>` (404 for everything else, no listing, no `Server` header), through `cloudflared tunnel --url ... --no-autoupdate --protocol http2`; every file is checked through the public `https://<words>.trycloudflare.com` address before use; cloudflared (its whole process tree), the server and the copies are closed and deleted when the work ends, on an error or Ctrl+C, after every file was fetched plus a grace period, or at a hard maximum lifetime (15 min). The ledger records `host_open` (host name only, files with size and SHA-256), `host_fetch` and `host_close`.
- `vidgen generate host-test [PROJECT] [--keep SECONDS] [--json]`: a free check of the tunnel (one tiny text file shared, fetched back, other paths checked for 404, closed); nothing goes to OpenRouter. A missing `cloudflared` names how to install it (Windows `winget install Cloudflare.cloudflared`, macOS `brew install cloudflared`).
- New `videogen` settings: `cloudflared`, `tunnel_protocol` (`http2` | `quic` | `auto`), `host_max_minutes`, `host_grace_seconds`. Paid runs use it with `videogen.host: quick_tunnel` (Step 306).

### 3D scenes: `guide_passes` takes the command-line forms (Step 304)

- A `3d` scene's `guide_passes` now takes every form `vidgen render --guide-passes` takes, read by the same function: one name (`guide_passes: depth`), a comma list (`depth,mask`, spaces allowed: `depth, mask`), `all`, `true`/`false` and lists as before. Step 303's "write a list" refusal of `depth,mask` is gone. An unknown name is refused with did-you-mean, in YAML and on the command line alike (`al` → did you mean `all`). The JSON schema (`vidgen schema`) accepts those strings.

### 3D scenes: `guide_passes: all` (Step 303)

- A `3d` scene's `guide_passes: all` now asks for all three guide passes, like `vidgen render --guide-passes all` (before, only `true` or a list worked in YAML). Other strings are refused with a hint: `al` → did you mean `all`, `depth,mask` → write a list `[depth, mask]`. The JSON schema (`vidgen schema`) accepts `all`.

### 3D scenes: docs, example and review (Step 302)

- `docs/COOKBOOK-3D.md`: setting up the `3d` extra, building a scene, the camera in 16:9 and 9:16, stand-ins, guide passes, checks and common mistakes; `vidgen guide 3d` (topic `three-d`) has the short version.
- `examples/3d-short`: a 9:16 Short of about 15 s (shapes, two stand-ins who walk and turn to each other, a ball that appears, rolls and glows, four camera moves on words, karaoke captions, guide passes). The gallery's `3d` sample now shows object actions.
- Guide passes: the `depth` range is fitted to the objects (the floor is clamped to it, so the objects get the contrast; far is a dark grey, only the background black) or set with the new `depth_range: [near, far]`; `outline` draws white lines on black; in the `mask` the floor is a neutral dark grey (`#404040`, listed as `floor`) and every other object's colour comes from its id, so adding or reordering objects keeps the others' colours.
- A 3D page that does not load (a timeout, a crashed page) is a clear error instead of a traceback, and Chromium is closed.

### 3D scenes: guide passes (Step 301)

- A `3d` scene can also be drawn as three plainer videos beside its 3D clip, with exactly its frames, camera and timing: `depth` (near white, far dark; one range for the whole shot, so it does not flicker), `outline` (edges only, black on white, like a line drawing) and `mask` (each object one flat colour on black, with a table object id → colour, stand-ins also by name, in `<scene>.mask-colors.json`). They hold only the 3D shapes (no labels, title, captions or overlays), are lossless, and are reused like the clip.
- Off by default: ask with `guide_passes: true` (or `[depth, mask]`) in a `3d` scene, or `vidgen render --guide-passes [depth,outline,mask]` for every `3d` scene (MCP `render` takes `guide_passes`). Files: `build/<quality>/three_d/<scene>.<pass>.mkv`; listed in the render's output (`guide_passes` in `--json`).
- `vidgen.api` gains `GUIDE_PASSES`, `guide_pass`, `make_guide_passes` and `mask_table`; `scene_description` accepts `draw_mode` `depth`, `outline` and `mask`.

### 3D scenes: object actions and character stand-ins (Step 300)

- Objects of a `3d` scene change on beats and words with ten new beat actions: `object_move` (to / by), `object_path` (a smooth curve through points, `turn` to face along it), `object_rotate`, `object_spin` (turns about an axis), `object_scale`, `object_show` / `object_hide` (fade or grow; objects may start with `visible: false`), `object_highlight` (a glow in the theme's highlight colour), `object_walk` and `object_face`; timed by `at` and `run_time`, `easing: smooth | linear`; a group's children come along.
- Character stand-ins: `shape: standin`, a capsule with a nose showing where it faces and its `name` above its head; `object_walk` turns it and walks it to a point or up to an object (bobbing with its steps), `object_face` turns it to face an object or a point.
- The camera follows a moving object: `camera_fly_to` keeps its distance to it, `camera_look_at` and `camera.look_at` keep looking at it; an arrow with `to: <object>` follows it too. Every frame's pose is worked out by vidgen and written into the scene description.
- Labels may keep their size on screen (`screen_size: true`).
- `vidgen lint`: `three_d_off_frame` and `three_d_hidden` warn when an object the beat is about (its actions name it, or a stand-in says the line, `voice:`) is mostly outside the frame or hidden behind a nearer object.
- `vidgen.api` gains `ObjectChange`, `plan_world`, `framing_3d` and `hex6`; `scene_description` takes `object_changes`.

### 3D scenes: shapes, groups and camera moves (Step 299)

- `3d` scenes have more shapes: `sphere`, `cylinder`, `cone`, `torus`, `plane`, `arrow` (with `to`: from its position to a point or an object), `label` (text on a plate that always faces the camera, in vidgen's bundled Inter Bold) and `group` (draws nothing); `size` may be one number; a `floor`.
- Groups: an object with `parent: <id>` moves and turns with that object (a group's `spin` carries its children).
- The camera moves on beats and words with new beat actions: `camera_orbit`, `camera_dolly` (push in / pull back), `camera_fly_to`, `camera_look_at` and `camera_move`, timed by `at` (a fraction or `"@word"`) and `run_time`, `easing: smooth | linear`; `camera.look_at` may name an object.
- `vidgen validate` checks object ids (did-you-mean), replays the camera moves (a dolly past its point, an orbit from right above its centre) and warns when a project with a `3d` scene has no Playwright or Chromium (a quick check; no browser started).
- `vidgen.api` gains `CameraMove`, `camera_problems`, `check_3d_scene` and `Floor3D`; `scene_description` takes `camera_moves`.

### 3D scenes: the `3d` scene type (Step 298)

- New scene type `3d`: objects seen by a fixed camera under one default light (ambient + sun) over a background colour, drawn by three.js in headless Chromium through Playwright; a title on a plate, overlays and captions on top; 16:9 and 9:16 (the camera's `fov` is measured across the shorter side, so a subject fills both alike). Only the `box` shape exists yet; `spin` keeps an object turning through the scene. Params `title`, `background`, `camera: {position, look_at, fov}`, `light: {ambient, sun, sun_from, color}`, `objects: [{id, shape, size, color, position, rotation, spin}]`; unknown shapes and keys get a did-you-mean.
- Frames are deterministic: vidgen sets the time of every frame (frame n at n / fps), three.js 0.186.1 ships with schu-video-generator (MIT, `vidgen/data/three/`), nothing is fetched from the network, and WebGL runs on Chromium's software renderer. The frames go to a lossless clip `build/<quality>/three_d/<scene>.mkv` with the scene description as JSON beside it, reused while nothing that draws them changed.
- Optional extra: `pip install "schu-video-generator[3d]"`, then `python -m playwright install chromium`; without them a `3d` scene stops with that hint (Windows wording too), and nothing else needs them.
- `vidgen.api` gains `text_plate` (text on a rounded plate; `video_clip` uses it too), `Scene3DParams`, `Camera3D`, `Light3D`, `Object3D`, `BeatSpan`, `scene_description` and `make_3d_clip`.

### Smaller pictures for video jobs, https-only audio / video (Step 296)

- Pictures sent inline to a video model (frame images and picture references) go as smaller copies: longest side at most 1280 px, JPEG quality 90 (PNG when the picture has transparency), cached in `build/videogen/pictures/`; the sheet files are untouched. The s293 sample's action shot went from a 48 MB request (refused by vidgen's 21 MB limit) to about 1 MB. `vidgen generate plan` shows each ready shot's request size (`request_bytes` in `--json`).
- OpenRouter refuses inline audio and video (HTTP 400 "Only HTTPS URLs are allowed"): with `videogen.inline_media: all`, a shot with `audio:` or `guide:` (and every talking shot) is now a problem in the plan and `run --pay` refuses it before sending; vidgen no longer sends sound or clips as data URLs.
- `docs/COOKBOOK-GENERATED-VIDEO.md`: the account's "ZDR endpoints only" setting refuses every video model (HTTP 404), a free check of the privacy settings (the model count with and without the key), and the https-only rule for audio and video.

### Cleaner reference sheet prompts, real image costs (Step 295)

- Character sheet pictures are now clean model-sheet pictures: full body from head to toe on a plain seamless light grey backdrop with nothing else in the picture, strict view words (a side view is a 90-degree profile facing left), the description introduced as who the person is with "No props", and an always-on "Avoid: text, letters, signs, logos, labels, props, furniture, lamps, scenery, ...". The style sheet's palette is marked as colours only (it drew lamps from "warm lamp orange"); lens, handheld, depth-of-field and scene-lighting words stay out of character pictures. Style frames keep the full look and avoid text and signage. The new prompts make new pictures: sheets made before read "not made yet".
- Picture costs say where they come from: sidecars and the sheets' ledger events have `cost_source: reported` (OpenRouter's `usage.cost`) or `estimate` (counted at the estimate, as before), the sidecar keeps the response's `usage` numbers, and the printed lines say "reported by openrouter" or "estimated". The budget check before paying is unchanged.

### Generated video: takes in the film, QA, run (Step 294)

- `vidgen generate run [--pay] [--budget USD] [--shot ID]`: a dry run, or (with `--pay` and a budget) each ready shot generated in order, the run refused up front when a shot has problems or the estimate is over what is left, stopped at the first failure, never retried, never paid twice. Each clip becomes a take `takes/<shot>/<n>.mp4` with QA (duration, aspect / size, black, frozen, flicker, abrupt cuts, its own sound) and a contact sheet; `vidgen generate takes | status | pick --shot ID --take N | none | auto`.
- `vidgen render` lays the shown take over its beat under the overlays and captions: scaled / cropped to the format (`fit: cover | contain`), at the video's frame rate, lightly colour matched (`videogen.color_match`), with crossfades against vidgen's picture (`crossfade`); the take's sound is never used. Drafts show vidgen's own picture; a new take or pick renders only its scene again.
- The description file ends with "Includes AI-generated footage (models)." and lint's `generated_footage` (info) reminds you to disclose it. MCP tools `generate_plan`, `generate_run` (paid only with `dry_run: false` and `confirm_cost: true`), `generate_status`, `generate_takes`, `generate_pick`. `docs/COOKBOOK-GENERATED-VIDEO.md` (cost control, privacy: no Zero Data Retention).
- Fixes to Steps 292–293: the mock provider returns a playable MP4 and unique job ids (its ledger counted repeated runs once); downloaded clips in `assets/generated_video/` no longer make every scene's render stale; reference sheets work with a proxy-injected key (`VIDGEN_OPENROUTER_KEY_VIA_PROXY` / `videogen.key_via_proxy`).

### Generated video: sheets, shot specs and the plan (Step 293)

- A beat's `generated_shot: {kind: talking | action | establishing, model, prompt, setting, characters, refs, audio, guide, first_frame, seed, resolution, aspect_ratio, line}`: the beat shown by a generated clip, its length snapped to what the model makes (trimmed later; long beats split), its prompt built from the style sheet, setting, characters and line.
- `characters[].reference_sheet` and `style_sheet:`: pictures made by the image provider (`vidgen generate sheets`, a dry run unless `--pay`; paid against `videogen.budget_usd`), used by shots only once `approved: true`.
- `vidgen generate inputs [--guide]` cuts each shot's voice (exact length), and a silent draft render of the beat with its first frame; `vidgen generate plan` lists every shot with its inputs, length, estimated cost and what the budget has left (a dry run). `vidgen validate` names unknown characters and pictures with a did-you-mean.

### Generated video: the provider layer (Step 292)

- `videogen: {provider: openrouter | mock, budget_usd, key_via_proxy, inline_media, poll_timeout}`: OpenRouter's video API (submit, poll, download) behind a hard budget cap; nothing is paid without an explicit pay and a budget; a spending ledger `videogen-ledger.jsonl`; clips cached by request, never paid twice; the model's audio never generated.
- `vidgen generate models`: OpenRouter's video models with durations, resolutions, aspect ratios, frame images and estimated prices (public list, no key; cached, works offline). `vidgen generate ledger`: jobs, costs, what the budget has left.
- The key from `OPENROUTER_API_KEY`, or none when a network proxy adds it (`key_via_proxy: true` / `VIDGEN_OPENROUTER_KEY_VIA_PROXY=1`). `vidgen.api`: `VideoRequest`, `MediaInput`, `generate_clip`, `plan_clip`.

### Audio drama cookbook; Phase AG review (Step 291)

- `docs/COOKBOOK-AUDIODRAMA.md`: structure, casting, narrator balance, rooms and stereo, score, sound design, pacing, the drama checks and a file per chapter, with measured numbers.
- `vidgen tts` copies a cold open's lines from the lines' own audio instead of voicing them again.
- Problems in a `sections:` project with a cold open or spoken credits name the right section (`cold_open` / `credits` for the added scenes); `cold_open: []` no longer crashes.

### Delivering an audio drama (Step 290)

- `audio_output: {loudness: drama}`: podcast loudness (−16 LUFS stereo / −19 mono, −1 dBTP) with checks for earbuds — loudness range ≤ 10 LU, every line and every voice at an even level, the music at least 15 LU under the voices; `vidgen audio check PROJECT --preset drama`.
- `audio_output: {split: chapters}`: one file per chapter, each at the preset's loudness, with an `.m3u` playlist and each file's transcripts.
- `credits: {speak: true}`: closing credits read from the cast ("Starring Bella as Mara and Adam as Jonas. Narrated by George."), the main theme under them.
- `cold_open: [beat ids]` (or a section id): those lines first, then the title and the theme.
- All opt-in: projects without these keys sound exactly as before.

### Music cues for drama (Step 289)

- `score: {themes: {main: love, tension: enigma}, crossfade: 4, duck: drama}`: a scene's or section's `music: tension` plays a named theme from there on, cross-fading at the change (`curve: equal_power | linear | smooth`); variations `{section, start, transpose, tempo, tracks}` re-render the theme's score.
- A beat's `motif: {theme: love, at: "@remember"}` plays a theme briefly over the scene's; `sting: {kind: reveal, at: "@ticket"}` on a word.
- Ducking presets (`duck: light | standard | drama | deep`, on `music:` cues too) and `swell`: the music rises into the pauses.
- The render measures the music under dense dialogue and warns when it is less than 15 LU under the voices (`mix.music_check`).
- All opt-in: projects without these keys sound exactly as before.

### Sound design for audio dramas (Step 288)

- `ambience:` on a scene or section (`rain`, `city`, `hum`, `room_tone`, `fire`, ... or `{beds, gain, width}`) plays beds that cross-fade at scene changes (`audio.ambience_crossfade`); a beat's `ambience: {start | stop, at: "@word"}` changes them on a word.
- Sound cues repeat (`repeat`, `every`; footsteps alternate feet), take named pans and `pan: {from, to}` steps across, and sound in a room (`room:`, or `audio.sfx_room: true` for all).
- `audio.scene_sounds: true`: audio-only renders play the stage sounds they can work out without pictures (set beds, walks, doors, knocks, switches, jumps) and a `video_clip`'s sound.
- All opt-in: projects without these keys sound exactly as before.

### Phase AF review (Step 286)

- Problems in a project written with `sections:` name the section (`sections[1].beats[0].voice`, `sections[2].pause`), not the scene it became; `vidgen schema` knows `sections`.
- No more YouTube chapter warnings for audio-only projects and renders.
- WebVTT transcripts escape `&` and `<` in the text, as the format requires.
- MCP: `render` takes `audio_only`; new tool `audio_check`.
- Step 282's arms default is now tested (character, cartoon and iso suites, MCP, frame baseline: the 25 stills with characters change, arms only).

### Stereo staging and rooms (Step 285)

- `pan:` places a voice in stereo (−1…1, or `far_left`, `left`, `centre`, `right`, `far_right`) on a voice of `voices:` or on a line; `pan: {from: right, to: left}` moves it across the line; `audio.follow_stage` pans stage voices to where their characters stand.
- `room: small_office | corridor | hall | outdoors | car | phone | none` per scene or section (or `audio.room`): generated reflections and reverberation, the narrator dry unless asked; nothing downloaded, nothing re-voiced.
- `audio.music_width` / `ambience_width` narrow or widen the music and ambience beds.
- A mono-compatibility check (channel correlation, mono fold loss) in `vidgen audio check` (`--mono` sets the exit code) and in audio-only renders with staging. All opt-in: videos and mixes without these keys are unchanged.

### Audio files, loudness presets, transcripts (Step 284)

- `audio_output: {format: mp3 | m4a | ogg | wav, bitrate, channels: mono, sample_rate}` for audio-only renders (FFmpeg only).
- Loudness presets `podcast` (−16 LUFS stereo / −19 mono), `audiobook` (ACX: RMS, peaks, noise floor, room tone head and tail), `broadcast` (EBU R128 −23), `custom`: the render measures the file and says PASS / FAIL; `vidgen audio check FILE|PROJECT` measures any audio file.
- `audio.level_voice`: a gentle leveller on the voices before the limiter (on with the podcast and audiobook presets; opt-in for videos): the limiter's deepest cut on ElevenLabs narration at −16 LUFS fell from 5.2 to 0.7 dB.
- Transcripts next to the file: plain text with speakers and chapter times, SRT, WebVTT, the chapter list. Cookbook: `docs/COOKBOOK-AUDIO.md`.

### Audio only (Step 283)

- `vidgen render --audio-only` (or `audio_only: true`) writes the project's sound alone, `output/<output>.wav`: narration and dialogue voices, music ducked under them, sound effects, stings, loudness normalisation; no scene is rendered, so it takes seconds.
- Audio-only projects (audiobooks, podcasts) may list `sections:` (title, voice, music, sfx, lines; `- pause: 2` between them) instead of scenes; `vidgen story draft --audio` drafts one from a story.
- Lines are timed by their speech plus `pacing:` gaps (between lines, speakers, sections, chapters, around stings); `pacing: {timing: video}` keeps a video's own timeline.
- A beat's `pause: 1.5` (or a `- pause: 1.5` item after it) sets the silence after its line, in videos too.

### Arms at the sides by default (Step 282)

- **Visible change:** characters now hang both arms at their sides by default; set `cartoon_arms: classic` for the old look (or `look: {arms: classic}` for one character). Every existing video with generated characters looks slightly different (the arms only); `classic` draws exactly as before.
- A scene host (`host:`) follows `cartoon_arms` too (it was always drawn the old way).
- The gallery's character entries (`stage` and the cartoon and iso showcases) are rendered again with the new arms.

### Arms at the sides, smooth crossfades between stage scenes (Step 281)

- `cartoon_arms: front` (video) or `look: {arms: front}` (a character): both arms read as arms at the sides, hanging just clear of the body; the far arm of the side view is drawn over the body (under the near arm) instead of behind it, where only a sliver showed. The default on iso places with `wide: fixed`; elsewhere `classic` (as before) unless set (since Step 282: `front` everywhere).
- A crossfade, push or wipe into a `stage` scene no longer passes through the background colour: the set comes in with the transition.
- Videos with many crossfaded scenes join in less memory (a batch of runs at a time, the same pictures).

### Faster lit places, zooms onto objects (Step 280)

- Lit iso places (`blue_hour`, `night`, …) render several times faster: a tile is graded and resized again only when its pixels, the light or its place on screen change (854x480: 233 s → 56 s for 7.3 s of a busy room; 1920x1080: ~13 s per second of a still camera). Pictures are the same as before.
- Big maps at full size use less memory: a zoomed view keeps one level of detail's tiles, a long pan lets the tiles it passed go, fewer spare tiles are kept.
- `zoom` onto an iso place's object (`zoom: tv_1`, `zoom: [lamp, pip]`) frames that object, not the middle of the place; a camera move no longer takes an object out of the place's picture.
- Working objects with moving parts (a TV's picture, a cooler's bubbles) are drawn back to front: one standing in front of another shows its moving parts.

### Crisp nights, friendly faces, rooms with walls (Step 279)

- `light: blue_hour` is crisp: colours keep their own hues (saturated before the cool tint), mid tones darker and the tones stretched, clean blacks — no lavender haze (mean luma ~130 against `night`'s ~95).
- `fill_color` on a stage: the fill light lifts the characters towards a colour (a warm key at night).
- `eyes: bright`: a clear white, a fine rim, a small pupil with a catchlight.
- On an iso place with `wide: fixed`, thin outlines are one pixel of that view, not of the whole place (close-ups no longer get thick, dark outlines and eyes).
- `iso: {show_walls: true}` (a room with `wide: fixed`): the view goes as far back as the standing back walls cover, so they fill the top of the frame; iso objects `poster` (`kind: rocket | atom | planet`) and `wall_shelf` hang on a back wall.

### A retro-future kit (Step 278)

- `iso: {style: retro}`: a 1950s "world of tomorrow" palette for iso places (mint lawn mown in stripes, cream checker paths, terrazzo floors, turquoise walls, pastel objects, cream saucer traffic); `textures: {grass, path, floor, tiles}` (`lawn`, `checker`, `terrazzo`, `stones`, `boards`, `tiles`, `tufts`, `plain`) on any place.
- `light: blue_hour`: a bright, clean night — lighter and more colourful than `night`, still dark enough for lamps, windows and neon to glow and pool.
- Iso objects `googie_building`, `retro_tower`, `starburst_sign`, `ray_lamp`, `atomic_sculpture`, `monorail`, `tube_computer`, `sunburst_clock`, `tv_console` (`kind: wave | face`), `retro_desk`, `hedge`, `planter`; a `car`'s `kind: rocket` (parked or driven); traffic `shape: saucer | monorail` and `hull`.
- Looks: `outfit: suit | lab_coat | jumpsuit`, `hair: pompadour | bob`, `accessories: [fedora]` / `[pillbox]`.

### Iso framing (Step 277)

- `iso: {wide: fixed}`: a wide view of one scale whatever the map's size (a character 0.14 / 0.20 / 0.28 of the frame's height at `character_size` small / medium / large, now allowed on an iso place with it; or `wide: {tiles: N}`), centred on the characters as far as the ground reaches, so a bigger map fills the frame with ground: square maps of 34 / 24 / 17 cells in 16:9, 23 / 16 / 12 in 9:16. A `zoom`'s scale is relative to it; close-ups and `follow` zoom in from it on big maps; `follow` and `pan` stay on the ground as far as their target allows. Lint `iso_ground` names the map size that fills the frame (an info hint for outdoor places in the whole-place view). The docs no longer say `fill` fills the frame outdoors (it fits the place's bounding box).

### Phase AD: features without AI APIs (Steps 268–275)

- Moving vehicles on iso places: `drive_to` drives a `car` along the paths (turning at corners, its tail and tail lights showing as it drives away, headlights with `switch_on`) or rolls a `train_car` along its track, `sail_to` sails a `boat` across the water (bobbing, a wake), `lift_off` sends a `rocket` up out of the view in smoke and flame; `to` / `via` spots or cells, `speed`; `follow` keeps the camera on one; engine, brakes and launch sounds; `vidgen validate` names what is in the way.
- Sitting, lying and using furniture on iso places: `sit_on` an object with seats (chair, bench, sofa, armchair, throne, lab stool, log, stump, hay bale, rock, bus stop, café table, school desk, bed), facing the way its seat does, its near arm, chair back or a desk in front drawn over the sitter; `lie_on` a bed (the blanket over it); `use` a laptop, PC, console, piano (typing), a campfire or fireplace (warming the hands), shelves or a machine; `stand_up`; `vidgen validate` names a seat taken, nothing to sit on, a character too far or walking before it stands up.
- A day passing in one scene: `- {time_of_day: night, run_time: 6}` (`morning`, `day`, `sunset`, `night`, `indoor`) fades the light and a sky of the time of day (day to night through a sunset), the stars coming out once it is dark; at dusk the lamps, a house's windows, lit objects and cars' headlights switch on by themselves one after another, and off at dawn (`auto_lights: false`, or `auto_light: false` on an object, opts out); on iso places and the flat stage.
- Iso weather: at night the puddles mirror lit windows, lanterns and neon trims (wobbling while it rains; rain's `settled` with `puddles` starts them full size); `fog` lies over an iso place in drifting bands, thicker further back; `wind` bends the trees, bushes, flowers and plants and swings scarecrows and balloon bunches in gusts. Outdoors only.
- `vidgen story draft story.md -o DIR` (MCP tool `story_draft`): a story cartoon drafted from prose, without AI — scenes from headings, breaks and time cues, a cast with distinct Kokoro voices (told in the first person, the narrator speaks with the protagonist's voice), each quoted line given a speaker with a confidence, ready-made iso places (or flat sets with `--style flat`) with light, weather and objects from the story's words, placeholder walks and shots, title and end cards, a music bed; `story_draft.md` lists every decision and a TODO checklist.
- `vidgen shorts suggest [PROJECT] [--count N] [--min 30 --max 60] [--teaser] [--write]` (MCP tool `shorts_suggest`): Shorts suggested without AI — windows between beat boundaries timed by the narration (or the word count), scored by dialogue, questions, exclamations, emotional and action words, variety, a clean start and a strong last line (the film's ending marked down), each with a hook line of up to six words; `--teaser` about 15 s of the best lines ending on the title; `--write` adds them as `cut:` variants (9:16, karaoke captions, hook, end card, opening zooms) in `shorts.yaml`, included by the config. An included file may now hold `variants`. A story draft no longer names two objects `lamp`.
- Ambient life on iso places: `ambient: {walkers, birds, cat, ducks, butterflies, fireflies, flies, muted, seed}` (or `ambient: true`) sets background walkers strolling the paths, birds pecking and flying off, a cat sitting and grooming, ducks on the water, butterflies by day and fireflies at night about the place, the same on every render; they keep away from the characters, never speak, hide in close shots and are drawn smaller and greyer (`muted`); indoors a cat and flies.
- Review (Step 275): a car's headlights light the road ahead when it drives away up the picture too, and a car or a boat shows a turned in-between frame at corners; a pupil's legs go under the school desk; a setting sun or moon sinks behind the ground instead of fading beside the characters' feet; a rainy day turning to night switches the lamps on; trees bend visibly on a windy day and balloon bunches swing on their strings (a gale no longer stretches them); story drafts read British `‘…’` dialogue, make characters of described speakers (`said the old man`), give a line calling someone by name to the other speaker, choose the title card's look from the story's mood (dark and neon at night) and add a little ambient life outdoors; a Short starting mid-scene keeps the light the scene had reached; walkers have faces and take lamplight, ducks keep off a sailing boat's way; the JSON schema accepts a YAML 1.1 `on` key on iso objects again.

### More iso objects (Steps 261–267)

- Seasons, harbour and travel objects `christmas_tree` (twinkles when on), `snowman`, `pumpkin` (glows when on), `gift_pile`, `balloon_bunch` (sways when on), `birthday_cake` (candles when on), `boat` (floats on water, bobs when on), `dock` (walked on over water), `lighthouse` (its beam sweeps when on), `train_car` and `rocket` (fires when on); review: a fire's or torch's moving glow and a beam are faint by day, softer stove steam, a brighter vending machine at night, a plainer crib, a bigger bicycle, a crystal that glows from within.

- Fantasy objects `treasure_chest` (opens with a golden glow), `cauldron` (bubbles over its fire when on), `giant_crystal` (glows and pulses when on), `throne`, `torch_sconce` (on a back wall; a flickering torch that lights who stands near), `signpost`, `archway` and `statue`; a switched lamp's pool of light is no longer cut off at the edge of its box.

- Farm, school and office objects `vegetable_patch`, `wheelbarrow`, `hay_bale`, `school_desk` (with its chair), `desk_with_pc` (screen and typing when on), `water_cooler` (bubbles when on), `printer` (prints when on), `globe` (spins when on) and `trophy_shelf`.

- Nature objects `campfire` (flames and sparks, lights who sits near), `tent`, `log`, `stump`, `mushroom_ring` (glows faintly at night), `pond` (ripples when on), `scarecrow` and `beehive` (bees when on); a lamp's pool of light is now faint by day and strong only at night.

- Town objects `street_lamp` (lights), `traffic_light` (cycles when on), `bus_stop`, `mailbox`, `fountain` (runs when on), `phone_booth` (lights), `car` (headlights), `bicycle` and `newsstand`; a lit street lamp or phone booth lights the characters near it, and every lamp's pool of light is now warm at night (it read olive or grey).

- Home, café and shop objects `bathtub`, `wardrobe` (`open`), `crib`, `cafe_table` (with two chairs), `counter`, `cash_register`, `display_case` (`kind: cakes | jewels`), `market_stall` and `vending_machine` (glows when on).

- Home objects `fireplace` (flickering fire, warm light), `kitchen_counter`, `stove` (the pot steams), `sink`, `bookshelf_tall`, `armchair`, `floor_lamp` (lights), `tv` (plays a picture) and `piano`; a lit fireplace or floor lamp lights the characters near it.

### More lab objects (Steps 258–260)

- Iso objects `telescope`, `satellite_dish` (turns), `charging_station` (bars fill), `crate_stack`, `airlock` (`open`, a flashing beacon), `printer_3d` (prints layer by layer), `hazard_sign` (`kind:`) and `fire_extinguisher`; the coffee machine now reads as one (light body, big mug), and a laptop's or kiosk's text no longer reads mirrored facing right.

- Iso objects `grow_rack`, `terrarium`, `specimen_tank`, `chemistry_bench`, `distillation_rig`, `lab_fridge` (`open`) and `fume_hood`, with glowing liquids, bubbles, drips, mist and vapour when on; a working object's motion now also shows behind another object and over a character standing behind it.

- Iso objects `laptop`, `terminal_kiosk`, `quantum_core`, `robot_arm`, `microscope`, `centrifuge`, `coffee_machine`, `lab_stool` and `wall_clock` (`time:`); the working ones switch on and move (a pulsing core, a swinging arm, a spinning rotor, steam).

### The project name in messages (Steps 255–256)

- Messages, help texts, schema titles and descriptions, the studio page ("schu-video-generator
  studio"), the Listen page and the gallery's index call the project `schu-video-generator`; the
  command (`vidgen render`, `vidgen studio`) and the Python package stay `vidgen`.

### Shorts with a HUD; review of Phase AA (Step 254)

- A cut can leave out one of a scene's own overlays (`overlays: {readout: {drop: true}}`), e.g.
  one timed on a beat the cut leaves out.
- A `hud` in a Short keeps its heart and scan meters above the captions (they stood on the same
  line) and out of the app's parts with `compact` too.
- Lint `shorts_safe_area` checks a `hud` by its texts and panels only, as `overlay_face` does
  (its frame's lines over the whole picture counted as covering every face).
- Changing a cut's `beats` no longer re-renders every scene of the cut, only the one it changes.

### Wavy hair, neon strip lights, a kiss holding hands (Phase AA, Step 253)

- **`hair: wavy`**: long locks waving past the jaw and ending in curls, the chin and chest left
  clear (`long` hair reads as a block in a close-up).
- **`iso.wall_lights`**: neon strips glowing along a room's walls (one colour, or one per back
  wall), lit at night.
- A `kiss` between two characters holding hands lets go of the hands first (before, the pair
  drifted out of the frame).
- A lab object's blinking lights hide behind a character standing in front of it.
- Lint `hidden_speaker` no longer counts a `hud`'s frame as hiding a speaker (`overlay_face`
  checks the HUD).

### A kiss, floating formulas, a scanner, sliding doors (Phase AA, Step 252)

- **The `hud` keeps off faces**: its alert and readout lines go to the free corner covering the
  least of a character's face, moving only when a face comes under them (`avoid_faces`, on by
  default); `compact: true` for close-ups. It is drawn in pieces (its frame once, the meters on
  every frame): about half the render cost of Step 251. New lint rule **`overlay_face`** (a HUD's
  text or plate over a face, outside Shorts).
- **`kiss`** action: two characters turn, lean in until their faces touch, close their eyes and
  lean back; a small burst of hearts and sparkles (`hearts`, `color`).
- **Display patterns** `equations` (formulas written, formula butterflies fluttering up out of
  the panel) and `timelines` (a branching tree, two figures meeting in a panel at each tip).
- **Small props** `scanner` (a live readout that can spike off its scale: `scan: {level, to,
  at}`), `takeout`, `crystal` (glowing while on).
- **Accessories** `medal` and `pendant` (glowing, pulsing, shining at night).
- **Iso places**: `doors: slide` (steel doors sliding open with a hiss) and `haze` (shimmering
  air with sparkles over a spot, `from` to fade it in). Rain on an iso place splashes in plain
  rings (no droplets that read as a tiny face in a close-up).
- Lint `look_alike` no longer compares an `echo` with anyone (another self, alike on purpose).

### A city at night, glowing particles, a HUD, echoes (Phase AA, Step 251)

- **Towers** on an iso place: the `tower` object, a tall building with rows of windows (a seeded
  share lit), neon trims in its `detail` colour and a blinking antenna light; `height` (2–30
  tiles), `size`, `screen: true` (an info screen whose lines of text crawl up), `garden: true`
  (glowing algae-farm bands); `on: false` / `switch_on` for its windows. With `light: night` a
  neon skyline; towers may reach out of the wide view.
- **Traffic** over an iso place: `iso.traffic` lanes of hover pods gliding between two spots at
  a height, looping or (with `at`) crossing once; glowing rims, canopies with a rider, light
  trails; hidden behind buildings.
- **Glowing particles**: `glow: true` on any particles (a light core, a halo in the colour, more
  opaque): neon rain.
- **The `hud` overlay**: a heads-up display over the frame for a scene (brackets and scan lines,
  a blinking alert, readout lines, a heart monitor with a rising rate and skipped beats, a
  scanner meter spiking off its scale).
- **Echo characters**: `echo: true` (or `{color, opacity, flicker}`) draws a character as a
  translucent other self that keeps its own colours, its outlines glowing; it appears with
  `materialise`.

### Shorts from a longer video (Phase Z2, Steps 249–250)

- **Karaoke captions in a Short** (Step 250) show a phrase of about three to five words on one
  line (`body` size, at most 5 words; title-size words fit only one or two in the narrow clear
  part), a small margin (`lift: 0.03`) above the app's texts. Options given still win.
- **`zoom` with `cut: true`** (Step 250) jumps to the zoomed view; at `at: 0` of a scene's first
  beat the scene opens on it (no second of the wide view while the set fades in, e.g. under a
  Short's hook).
- **`shorts_safe_area`** (Step 250) checks a face against every caption of the line being
  spoken (a longer caption of the line covering a face is found from any still of it), also on
  mid-beat stills (lint renders 3 stills per beat in a Short), and reports an overlay over 10 %
  of a face (`min_cover`).
- **A cut leaves a character out** (Step 250): `params: {characters: [{name: x, drop: true}]}`
  (also props and layers), e.g. someone who only arrives in a later beat.
- **The hook** (Step 250) gets a little smaller (down to 0.8 × the title size) when that keeps it
  on two lines.

- **Cuts** (Step 249). `cut:` (usually in a variant, one per Short or teaser) keeps chosen scenes
  (whole, some beats by id, or `{from, to}`; a scene may come twice under another id) and
  changes them for this cut: a scene's `params` (characters, props and layers merged by name)
  and other keys, beats by id (`cut.beats`: a shot, actions, an emotion). Beats keep their ids,
  so the full video's narration audio is reused. `hook:` adds a hook caption and `end_card:` a
  closing card ("Full video on the channel" under the title).
- **The `hook` overlay** (Step 249): big bold text on a plate near the top over the first
  seconds, popping in and fading out.
- **Shorts** (Step 249). `shorts: true` (or `{max_seconds, bottom, right, top, left}`) keeps
  captions, lower thirds and the hook out of the parts of the frame the phone app covers (bottom
  20 %, right 15 %); lint rules `shorts_safe_area` (text or a face there, a caption over a face)
  and `shorts_length` (over 60 s, an error); `vidgen validate` warns about a Short that is not
  vertical or too long.
- **`zoom` with `hold: true`** (Step 249) stays zoomed in after its beat (a scene ending on a
  close view), until a later camera move.
- **`audio.bitrate`** (Step 249): the AAC bitrate (default 192k as before); a loud Short's mix
  kept its true peak at 256k (192k pushed it from −1.9 to +1.9 dBTP).
- In a Short the scenes' safe area leaves out the app's parts, and a `card`'s words keep to the
  clear part.

### Story-cartoon features (Phase Z, Steps 245–248)

- **Voice effects** (Step 245). `effect:` on `voice:` or a named voice of `voices:` runs that
  speaker's lines through `deep`, `high`, `robot` (a flat, metallic monotone), `radio`, `chorus`,
  `echo`, `hall` or `otherworldly` (deep, many-voiced, in a hall), a list of them, or `{use,
  pitch, amount}`, with any provider (ffmpeg after synthesis). A voice without one keeps every
  audio hash; named voices do not inherit it.
- **Hologram characters** (Step 245). `hologram: true` (or `{color, opacity}`) on a character
  draws it as a translucent figure in one glowing colour with bright edges, which the stage's
  `light` never darkens.
- **Portals** (Step 245). A `portal` prop: switched like a lamp, it tears open from a glowing
  crack into a crackling, swirling, pulsing rift with a glow (`switch_on`) and seals again
  (`switch_off`), with its sounds; on a plain stage or at a spot of an iso place, where a
  character can step out of it (`enter` with `door:` its spot).
- **Framing** (Step 246). `iso: {wide: fill}` (or a zoom 1–2.5) brings a room's wide view
  closer; `shot: closeup ana ben` (and `medium`) frames two or three characters' faces together;
  `shot: {..., clear: true}` hides the characters a shot does not frame for its beat.
- **Holograms appear and flicker** (Step 246). `- materialise: guide` (a flickering wireframe,
  then solid; the character waits unseen until then) and `- dematerialise: guide`; holograms
  flicker now and then (`hologram: {flicker: false}` for a steady one).
- **Visitors** (Step 246). `iridescent: true` (skin and clothes shifting colours like oil on
  water) and `afterimages: true` (faint copies trailing a move) on a character.
- **Hand in hand** (Step 246). `- {hold_hands: ana, with: ben}` keeps two characters holding
  hands wherever they stand or walk; `- let_go_hands: ana`.
- **Alarms and shutters** (Step 246). `- alarm: start` / `stop`: a dark room under a red light
  pulsing like a beacon, with a siren; what the light never grades keeps shining.
  `- shutters: close` / `open` slams steel shutters over an iso room's windows (`iso: {shutters:
  true}` starts them down).
- **A lab and a memory** (Step 246). Iso objects `console` (glowing screens), `server_rack`
  (blinking lights), `projector_pad`, `whiteboard`, `flower_arch`, `chess_table`; a
  `hologram_display` prop (a floating panel of light: `fractal`, `data` or `text`); a portal's
  `view` (`coast`, `stars`, `meadow`); `flashback: true` on a stage (faded warm colours and a
  soft vignette).
- **Sounds** (Step 246). Built-in `alarm`, `crackle`, `hum`, `drone` (a crystalline singing
  drone) and `slam`; ambience beds `hum` (`ambience: hum`) and `alarm` (under an alarm). The
  Listen page has a row for them. Gallery showcase `iso_lab`.
- **Light on the characters** (Step 247). `fill_light: 0–1` on a stage: a soft light on the
  characters alone, so faces read at night or under an alarm while the set stays dark. An
  iridescent visitor shines partly by its own light (`iridescent: {glow}`, default 0.5).
- **Hand in hand, side by side** (Step 247). Two holding hands step in close enough for their
  joined hands to show, and walking together (same `run_time`) they go side by side.
- **Review** (Step 248). A `shot` inside a `zoom`'s `until` holds for its beat, then the zoom
  resumes (the camera no longer pulls back during the shot). Voice effects are level-matched to
  the dry voice (the robot was about 5 dB louder). `vidgen render --max-scenes N` renders a long
  project in steps (stops without joining while scenes are left; run it again to go on).

### Particle physics (Phase Y, Steps 237–244)

- **Review** (Step 244). Every PDG 2024 value and quantum number re-checked (the remaining
  "check" marks resolved, except the Higgs width and branching ratios, Standard Model predictions
  of the Yellow Report 4 left for the owner to confirm). **Fix**: the conservation checker refuses two
  real particles merging into one lighter one (e⁺e⁻ → γ with a real photon — write `gamma*` —,
  p p̄ → π⁰); e⁺e⁻ → Z, g g → H stay allowed. **Fix**: a decay chain no longer gives one νν̄ pair
  the Z's whole invisible fraction. **Fix**: a `feynman` scene with `vertex_rule` cards fills the
  frame before the first card and after the last (it was only centred at the card-time size).
  **Fix** (`plot`, Phase W): a live readout (`events: 12 345`) no longer keeps every frame's text
  (a 57 s `mass_spectrum` took 622 MB, now 392 MB). Phase Q's 31 frames unchanged.

- **Example, docs and gallery** (Step 243). `examples/higgs-discovery` ("How the Higgs boson was
  found", about 3:49 with Kokoro, 16:9 and a 9:16 `short` variant): the Standard Model with the
  Higgs boson's couplings (the W and Z masses, the fermions' through Yukawa couplings; most of a
  proton's mass is not from the Higgs), gluon fusion through a top-quark loop, the predicted decay
  modes, H → γγ through top and W loops, a simulated diphoton event in the schematic detector, the
  photons' invariant mass worked out from the display's numbers (125 GeV), a simulated spectrum
  filling with its bump, fit and local significance, the four-lepton channel, what five sigma
  means (a log plot of the p-value: once in 3.5 million, not "99.99994 % sure"), and the
  announcement of 4 July 2012 by ATLAS and CMS; lint clean of particle findings. A guide topic
  `vidgen guide particle-physics` (not `particles`: that is the cartoon effect) and
  `docs/COOKBOOK-PARTICLES.md` (planning, choosing the scene, natural units, honesty — simulated
  data, schematic detectors, PDG 2024 and YR4 sources, local significance, what a p-value means —
  pacing, mistakes and the rules that catch them). The gallery's "Particle physics" section gets
  its note, footer and a showcase (a Higgs boson in two photons); 15.7 MB of the 16.5 MB budget.
- **Fix** (Step 243): a `feynman` vertex-rule card wraps before the reaction, never inside it (in
  9:16 "t → t H" broke before the H).

- **Particle-physics accuracy lint** (Step 242). Twelve `vidgen lint` rules read the narration and
  the screens against the particle model: `particle_mass` ("the W weighs 91 GeV" — that is the
  Z's; MeV for GeV), `particle_charge` and `particle_spin` (errors: "the down quark has charge +2/3",
  "the photon has spin 1/2"), `particle_lifetime` (mean lives, half-lives, widths),
  `branching_ratio` ("most Higgs bosons decay to two photons"), `conservation_claim` ("μ⁻ → e⁻ γ is
  allowed", "forbidden by charge" against the checker), `feynman_boson` ("a photon changes the
  quark's flavour", "gluons couple to electrons", a boson the diagram does not have),
  `kinematics_number` (a kinematics scene's values, decay lengths βγcτ, thresholds),
  `detector_signature` ("photons leave tracks"), `significance_claim` ("five sigma means 99.99994 %
  sure the Higgs exists"; σ against a spectrum's computed significance), `simulated_label`
  (simulated data called real, or not labelled) and `particle_units` (info). Negations and
  contrasts are left alone; 0 findings on every example. `mass_spectrum` in 16:9: the plot keeps
  about 70 % of the width, larger text, a short significance note by default (`explain: long` for
  the full one); in 9:16 the box no longer covers data. The Higgs branching ratios are labelled
  YR4 at m_H = 125 GeV. `branching` bars have larger labels.

- **Collisions, decays and data** (Step 241). `mass_spectrum`: a simulated invariant-mass spectrum
  (labelled "simulated data") filling event by event with a ticker and the local significance
  growing as the data arrive (Asimov, or the observed excess), Z → μμ with its width, H → γγ as a
  small resolution-dominated bump on a large falling background, H → ZZ* → 4ℓ with a handful of
  events, or your own resonance; the peak fitted with Phase W's Gaussian or Breit–Wigner on a
  polynomial background (mass ± uncertainty, width), a note with the likelihood-ratio significance
  and what its p-value means (5σ ↔ 2.9 × 10⁻⁷: background alone fluctuating this high — not the
  chance the result is wrong), an optional data − background panel; a `plot` underneath (grow, fit,
  annotate, reveal, zoom). `decay_chain`: decays as a tree with τ and cτ (PDG 2024), branching
  fractions, each decay checked. `branching` (bars) and `branching_pie`: branching ratios from the
  model (the Higgs boson's are the LHC Higgs XS WG prediction, said so). Plot models
  `mass_spectrum`, `decay_times` and `z_lineshape` (2, 3, 4 neutrino families; schematic). `plot`
  fits gain `residuals: background` and `parameters`, residual panels their own targets; a note on
  a live histogram whose growth a `grow` action holds no longer crashes the render; fits with a
  polynomial in large x (a cubic background at 100–160 GeV) are no longer refused as undetermined.
  Also: display events of `detector` presets sit on the resonance peak (mass within ± Γ), and the
  16:9 detector is drawn about 15 % larger.

- **Event displays: the `detector` scene type** (Step 240). A schematic cylindrical detector
  (tracker, solenoid, ECAL, HCAL, iron yoke, muon chambers; generic sizes, labelled "schematic
  detector · simulated event") across the beam (x–y) or along it (r–z; the action `switch_view`
  morphs one into the other), with a seeded simulated event built layer by layer over the beats:
  tracks bending in the field with radius p_T / (0.3 B) and the sign of their charge (low-p_T ones
  curl up), calorimeter towers growing with the energy (log or linear, stated), muons through
  everything with chamber hits, jets as cones, the missing transverse momentum computed from the
  visible particles, a readout (p_T, η, invariant or transverse mass), a signature legend and a
  layer key. Presets `z_to_mumu`, `h_to_gammagamma`, `h_to_4l`, `w_to_enu`, `dijet` (decays in the
  boson's rest frame boosted to the lab) or listed particles; what never reaches a detector (τ, π⁰,
  Z, quarks) is refused with the reason, and a claimed signature is checked ("a photon leaves no
  track"). Also: `kinematics` frames fill their halves with three large key numbers each
  (`readout: all` for every number), a root of a sum is set apart from the next factor in
  calculations, plot models can name their axes (`two_body_opening` does), and a `feynman` diagram
  stays centred until a vertex-rule card needs the room.

- **Relativistic kinematics: the `kinematics` scene type** (Step 239). Momentum vectors to scale: a
  two-body decay (`decay: "pi+ -> mu+ nu_mu"`) in the parent's rest frame — the products back to
  back with p* from the masses (29.79 MeV/c) — and in the lab where the parent moves (`momentum:
  200 MeV/c`), side by side in 16:9 and stacked in 9:16; or particles given in the lab with their sum
  and rest frame. Each frame shows β and γ, the energies, the opening angle, the invariant mass
  √((ΣE)² − |Σp|²) — the same in both frames —, the decay length βγcτ and, with `si: true`, SI
  values. The action `boost` speeds a frame up continuously. A `calculation` takes a particle's
  PDG value by name (`{name: m_mu, mass: mu-}`, `lifetime`, `width`) and the picture's numbers
  (`from_scene: pion.p_star`); the plot model `two_body_opening` draws the opening angle against
  momentum. The model `particle_physics.kinematics` adds four-vectors, boosts, thresholds (fixed
  target vs collider) and decay lengths. Decays below threshold or forbidden, β ≥ 1, E < m and
  negative m² are refused with the numbers. Also: gluons in `feynman` diagrams are proper coils,
  diagrams fill more of the frame and the vertex-rule card is larger.
- **Feynman diagrams: the `feynman` scene type** (Step 238). Diagrams in proper notation — fermion
  arrows on the fermion-number flow (antifermions against time), wavy photons, W and Z, curly
  gluons, a dashed Higgs, vertex dots, every line named (e⁻, ν̄ₑ, u, d̄), the time direction stated
  (left → right, or `time: up`) — from 12 presets (e⁺e⁻ → μ⁺μ⁻, Compton, Bhabha, Møller, β⁻ decay
  at quark level with optional spectator quarks, μ⁻ decay, π⁺ → μ⁺ ν_μ, Drell–Yan, gg → H,
  H → γγ through a top or W loop, H → ZZ* → 4ℓ, t → W⁺b) or written by their lines
  (`"photon: gamma v1 -> v2"`). The layout is automatic (s-, t-, u-channel, decays, cascades, one
  loop; no crossings) and every vertex is checked against the Standard Model before it is drawn:
  the allowed vertex types (no H γ γ vertex — "draw the loop"; a W only within a doublet), charge,
  baryon and lepton family numbers at every vertex and along the fermion lines, colour, and the
  whole reaction. Lines appear in time order over the beats; the actions `travel` (a particle
  dot), `vertex_rule` (the vertex type, its coupling — α ≈ 1/137, α_s ≈ 0.118, g ≈ 0.65, Higgs ∝
  mass — and the conservation checks) and `swap_channel` (s ↔ t, γ ↔ Z, top ↔ W loop). Fixed with
  it: the Λ mean life (PDG 2024: 2.617 × 10⁻¹⁰ s).
- **The `standard_model` scene type and the particle model** (Step 237). The Standard Model chart:
  quarks and leptons in three generations, the gauge bosons and the Higgs boson, each cell with
  its mass (PDG 2024), charge and spin, in colour groups with a key and the values' source; the
  classic grid in 16:9, the bosons in rows under the fermions in 9:16. Every particle, generation,
  group and row is a target; the actions `antiparticles` (cells turn into their antiparticles:
  ū, ν̄ₑ, e⁺, the charge reversed) and `couplings` (which particles the photon, gluon, W, Z or Higgs
  couples to, and why). The model is `vidgen.api.particle_physics` (no manim): the Standard Model
  particles and 27 common hadrons with their antiparticles (masses, widths or lifetimes, quantum
  numbers, quark content), names in ASCII or Unicode, and `check("n -> p e- anti-nu_e")`, which
  explains whether a reaction or decay can happen (charge, baryon and lepton family numbers,
  angular momentum, energy and thresholds; flavour, C- and G-parity) and through which
  interaction.

### Orbital mechanics (Phase X, from Step 229)

- **Review of Phase X** (Step 236). The orbit model checked against independent calculations
  (Kepler's equation, element and state conversions, propagation, vis-viva, Hohmann / bi-elliptic /
  plane change, flybys, Lagrange points and Jacobi constants, the figure-eight, resonances, the
  planets' positions and 14 published opposition and conjunction dates, every constant and preset):
  no physics error found. Orbit scenes render about twice as fast and use half the memory (the
  side panel's live numbers are drawn from cached glyphs; title, caption and axes are drawn once
  per stretch) — a 47-second orbit scene at 1080p no longer runs out of memory. In 16:9 the
  caption stands under the side panel so the orbit picture takes the whole height; in 9:16 a
  transfer's per-burn Δv rows give way to the burns' own labels. A `calculation` substitution that
  does not fit with a unit on every value writes them in one unit with the unit once at the end,
  `(√(2.945² + 10.93²) − 7.726) km/s`, before falling back to SI numbers. The orbit lint reads
  numbers written with spaces ("384 400 km"). The phase angle's label and lines keep off the
  labels near them.

- **Example, docs and gallery** (Step 235). `examples/mars-transfer` ("How to get to Mars", about
  3:43 with Kokoro, 16:9 and a 9:16 `short` variant): why a rocket cannot fly straight there, the
  Hohmann transfer (Δv₁ 2.94 + Δv₂ 2.65 km/s, 259 days, Mars 44° ahead) with burns on words, the
  transfer time and phase angle worked out in a `calculation`, the 3.59 km/s departure burn from
  low Earth orbit (the Oberth effect, from `from_scene`), and the Earth and Mars on 28 October 2026
  with the next window (around early December 2026) and the opposition of 19 February 2027. A
  guide topic `vidgen guide orbits` and `docs/COOKBOOK-ORBITS.md` (choosing, scale honesty, units
  and Δv, approximations to state, pacing, mistakes and the rules that catch them). The gallery's
  "Orbital mechanics" section: the `orbit` entry regenerated with the current layout and two
  showcases (the Hohmann transfer to Mars; Jupiter's Trojans in the rotating frame); the gallery's
  size budget grows from 13 to 15 MB (each entry still at most 0.36 MB, each GIF 150 KB).
- **Fix** (Step 235): a transfer's phase-angle label keeps off the bodies and their labels (it
  could sit on the Earth's name in 9:16); `orbits.events_between` no longer lists an event twice
  (the 2029 Mars opposition came twice).

- **Orbital accuracy lint** (Step 234). Nine `vidgen lint` rules compare what the narration and
  the screen say with what each `orbit` scene computes: `orbit_period` ("Mars takes three years"
  for 1.88 yr; "about two years" is fine), `orbit_speed` (vis-viva at the perihelion or aphelion
  named, escape and circular speeds), `orbit_dv` (the first, second and total Δv of a transfer or
  burns), `orbit_transfer` (transfer time, phase angle, synodic period, launch windows),
  `orbit_distance` ("the Moon is 384,000 km away" fits, "L2 is 15 million km away" does not;
  altitudes, radii, size ratios), `orbit_date` (opposition and conjunction dates in any scene,
  against JPL's elements), `orbit_scale` ("drawn to scale" for enlarged bodies or a log view),
  `orbit_conserved` (an n-body run's energy, angular momentum or Jacobi constant drifting) and
  `orbit_crash` (a periapsis in the atmosphere, bodies passing through each other). Cards and
  captions naming a body are checked against the orbit scenes. `said_before_shown` knows the
  orbit actions and targets. The number reader understands "one and a half million kilometres".
- **Fix** (Step 234): Neptune's rate of the longitude of the ascending node in the JPL Table 1
  data was Pluto's (−0.01183482 instead of −0.00508664 deg/century); Neptune's heliocentric
  direction on a date moves by at most 1.2″ over 1800–2050 (below the table's own accuracy). A test
  now pins every number of the table.

- **The Solar System on a date** (Step 233). `date: 2020-06-01` places the planet presets (and
  the new `pluto`) where JPL's approximate elements (Standish, Table 1, valid 1800–2050; dates
  outside refused) put them that day, the panel showing the date as the clock runs; `event: {kind:
  opposition, of: Mars}` finds the next opposition / conjunction after it by root finding and
  draws the line the planets will stand on (Mars 2020-10-13); `radial: log` fits Mercury to Pluto
  in one picture with labelled rings and "distances compressed (log)"; `inset: true` adds the inner
  planets to scale beside a true-scale picture; `sizes: true` compares radii to scale side by side
  with the Sun's edge. The model: `vidgen.api.orbits` gains `julian_date`, `heliocentric`,
  `mean_elements`, `next_event`, `sidereal_period`, `planet_synodic_period`, `elongation`, `TABLE1`
  and more.
- **Compact orbit panels** (Step 233). The `orbit` scene's side panel now shows the time, the
  speed-up and the few values the scene is about (at most six rows in 16:9, five in 9:16, at a
  readable size); diagnostics such as ΔE/E, ΔL/L and a Jacobi constant's drift are left out unless
  asked for (`energy: true`, `panel: full`, or by name: `panel: [time, total_dv, phase]`;
  `panel: none`). `panel: full` restores the earlier panel.

- **Many bodies** (Step 232). `system: earth_moon | sun_earth | sun_jupiter` (or your own pair
  with a mass ratio `mu`): the circular restricted three-body problem integrated about the
  barycentre, seen in the inertial or the rotating frame (`view: rotating`; the actions
  `corotate` / `inertial` turn the view on a word), the Lagrange points L1–L5 computed for μ
  (`lagrange`), Routh's stability test, bodies placed `near: L4` with a `shift` (tadpoles,
  horseshoes, or a body leaving L4 above μ = 0.0385), the Jacobi constant and its drift, the
  zero-velocity curve; Sun–Earth L1 / L2 shown 1.50 / 1.51 million km from the Earth in a close-up
  (`center` with `extent`, an arrow to the off-plot Sun). `system: figure_eight` (three equal
  masses, Chenciner–Montgomery); `origin: barycentre` (binary stars on their two ellipses);
  `resonance: [Io, Europa, Ganymede]` with the Galilean moons as presets (period ratios, the
  Laplace angle 180°, conjunction lines as they happen); a body's `curvature` (the Moon's path
  always bends towards the Sun); `tides` (a schematic: the Moon's pull, the tidal arrows, two
  bulges, tidal locking). n-body panels show ΔL/L with ΔE/E; masses may be written `'2 Msun'`.
  The model: `vidgen.api.orbits` gains `lagrange_points`, `collinear_gamma`, `routh_stable`,
  `jacobi`, `zero_velocity_segments`, `integrate_restricted`, `figure_eight`, `conjunctions`,
  `laplace_angle`, `tidal_acceleration`, `equilibrium_tide` and more.

- **Manoeuvres and gravity assists** (Step 231). A body's `burns` (Δv prograde, retrograde,
  radial, normal… at a time or the next periapsis / apoapsis: the Δv arrow at the burn point, the
  orbit before faint and after drawn, a mission line in the panel); `transfer` — Hohmann (Δv₁, Δv₂,
  total, transfer time, the phase angle drawn live until the launch window, the synodic period),
  bi-elliptic, phasing — between circular coplanar orbits, with clear errors for eccentric or
  inclined orbits; `alongside: Earth` starts a spacecraft with its planet; `flyby` — a gravity
  assist in the planet's frame (asymptotes, v∞ in and out, the turning angle δ, the periapsis,
  the atmosphere) with the Sun-frame vector diagram (speed gained behind the planet, lost in
  front); the clock actions `burn` (a burn on its word), `flyby`, `pause`, `coast`, each stretch
  of the clock showing its own speed-up; a `calculation` takes the computed Δv, times and angles
  with `from_scene`. The model: `vidgen.api.orbits` gains burns and trajectories, `hohmann`,
  `bielliptic` (and its thresholds 11.94 / 15.58, computed), `plane_change`, `phasing`,
  `synodic_period`, `flyby`, `gravity_assist`. In 9:16 a long panel is set in two columns; a
  scale bar takes the corner the paths keep away from.

- **Kepler's laws and orbital speed** (Step 230). A body's `geometry` (the empty focus and the
  centre, a and b with their lengths, perihelion / aphelion — perigee / apogee around the Earth —
  with their distances), `sectors` (equal areas in equal times: each sector shaded as it is swept,
  its area computed and listed), `velocity` (arrows ∝ speed with a key, the vis-viva speed and
  its range); `cannonball` (Newton's cannon: shots from one point at increasing speeds, each
  classified by its energy as suborbital, circular, elliptical, parabolic or hyperbolic); the
  actions `sweep` and `launch` on a word, `reveal` / `highlight` of every overlay; the plot model
  `kepler_planets` for Kepler's third law on log axes. **Changed look of `orbit`:** the picture
  fills the frame's height (the axes' unit written once instead of two axis titles), labels never
  overlap (further out with a leader line when crowded), and a side panel beside the picture
  holds the readout and a legend of the bodies' periods.

- **The `orbit` scene type and the orbital model** (Step 229). Planets, moons, satellites and
  comets on Kepler orbits, moving in correct timing at one speed-up from the first beat to the
  scene's end (so equal areas in equal times show as they are), with conic orbits, fading trails,
  an equal-aspect frame in AU or km (or a scale bar), a readout of the simulated time and the
  speed-up, "sizes not to scale" when bodies are enlarged, a view that follows a body, and
  `dynamics: nbody` (mutual gravity on leapfrog or RK45, with the energy error). Bodies from
  presets (the planets on JPL's approximate J2000 elements, the Moon, an ISS-like orbit,
  geostationary, Halley), from elements with units (`a: "1.5 AU"`, `periapsis`, `altitude`, `i`,
  `raan`, `argp`, `nu`) or from a position and velocity; clear errors such as a periapsis inside
  the planet. The model is `vidgen.api.orbits` (no manim): Kepler's equation for every conic,
  elements ↔ state vectors, vis-viva, periods, energies, n-body runs.

### Science foundation: scientific charts and worked calculations (Phase W, from Step 222)

- **Review of Phase W: accuracy fixes** (Step 228). Checked against numpy / scipy
  (`tests/test_science_review.py`). **Changed results:** counts — a series with `y_err: sqrt`, or
  a curve fitted to a histogram — are fitted by Poisson maximum likelihood (weights from the fitted
  curve; √N weights from the data pulled a decay low: the example's λ 0.276 → 0.274 min⁻¹, its
  narration updated), and a count of 0 is no longer an error; a histogram with a number of bins
  no longer drops its smallest or largest value to round-off; RK45 samples come from its dense
  output (as scipy: far fewer steps, the same accuracy) with an absolute tolerance scaled to the
  model. **Units:** two readings in °C / °F cannot be added, and a difference of readings cannot
  be shown in °C (write changes in K). **Look:** normalized residual panels are symmetric and
  ticked at ±2 (points without bars); `aspect: equal` plots tick both axes with one step (square
  gridlines); a calculation leaving for the next one fades out faster. The lint also accepts a
  number said for an intermediate step of a calculation.

- **A science example, guide topic and cookbook; the PCR trace on the chart core** (Step 227).
  `examples/radioactive-decay` ("Half-life: how radioactive decay keeps time", about 2:52 with
  Kokoro): a live Monte Carlo of 1000 and 20 nuclei beside the exponential law, counts with √N
  error bars on a log axis with an exponential fit, its confidence band and residuals, the
  half-life worked out with its uncertainty, and carbon-14 dating; seeded data from
  `make_data.py`, a 9:16 variant. `vidgen guide science` (plot or chart, honest axes, error bars,
  fits, live models, units and significant figures, pacing, lint; the `biology` topic no longer
  answers to "science") and `docs/COOKBOOK-SCIENCE-CHARTS.md`; the gallery has a "Science charts"
  section. **Changed look:** a `calculation` keeps the units in a long substitution whenever they
  stay comfortably readable (on two lines, or one factor per line) instead of falling back to SI
  numbers, a block too tall for the frame shrinks its largest lines first, and a calculation's
  lines stay within 1.6 times each other's size (a big formula above a long substitution comes
  down towards it); the `dna_lab` PCR
  trace is drawn by the chart core: a horizontal "temperature (°C)" title, the three temperatures
  named by their stage on the axis ("denature 95") with gridlines, "cycle 1…3" under the cycles.
  New: `plotcore.layout_axes` (a panel from axes you built). The population, GWAS, cyclin and
  action-potential plots keep their drawing (DESIGN §97.12 says why).

- **Lint for numbers, units and plots** (Step 226). `vidgen lint` reads the numbers the narration
  and the screen say — in digits and in words ("eleven point two kilometres per second", "three
  point seven times ten to the minus nineteen joules", "one in a hundred and fifty", "three
  halves") — and compares them with what the `calculation` scenes compute: `calc_numbers` (a value
  that is not the result, rounding as written and "about" allowed), `calc_units` ("a speed of 30
  kilometres"; 30 m/s for 29.8 km/s, mg for µg) and `calc_sigfigs` (info: more significant
  figures than the inputs give). New plot rules: `plot_units` (an axis of a physical quantity
  without its unit), `plot_log` (error bars, fits or lines at or below zero on a log axis),
  `plot_errors` (error bars without a stated meaning, or called otherwise in the narration),
  `plot_series` (several series without legend or labels, placeholder names), `plot_truncated`
  (info: bars not starting at zero, also a `bar_chart` baseline), `plot_conserved` (a model's
  conserved energy drifting: use leapfrog or a smaller step) and `plot_fit_claims` ("a half-life
  of twelve days" when the fit gives 8.0 ± 0.1 d). `said_before_shown` / `unsaid_reveal` know the
  plot and calculation actions and targets. No new dependency.

- **Worked calculations with units** (Step 225). A new scene type `calculation` shows a symbol
  table (each value with its unit, its meaning and its source; constants such as `G`, `h`, `c`,
  `M_sun` with CODATA 2022 / SI 2019 / IAU values) and works each calculation step by step: the
  formula (TeX written from the expression), the values substituted with their units, the result
  in a box with the right significant figures — or as an exact fraction when every input is exact
  (2/3 × 1/25 × 1/4 = 1/150) — and the result converted into other units (m/s → km/s, J → eV,
  GeV/c² → kg). Later calculations use earlier results by name, and other scenes can too
  (`from_scene`). Units are checked: adding metres to seconds is refused with both dimensions
  explained. The actions `substitute`, `compute` and `convert` time the steps to words;
  `highlight: "symbol:G"` marks a symbol. The engine is `vidgen.api.quantities` (units,
  prefixes, °C / °F offsets, conversions, significant figures, exact fractions); no new
  dependency.

- **Live plots from simulations** (Step 224). A `plot` takes `models` that generate its data:
  differential equations written as safe expressions (`{x: v, v: "-k*x - c*v"}` with parameters,
  initial conditions and a time span) integrated by RK4, adaptive RK45 or the symplectic
  leapfrog (energy stays bounded on orbits and oscillators), recurrences (the logistic map,
  compound growth), seeded random walks and Poisson events (the same seed gives the same numbers
  everywhere), or a Python function registered with `vidgen.api.register_model`; derived
  quantities (an energy) and their drift when declared conserved. Their series grow over the beat
  with a head marker, an optional readout (`t = 3.20 s`, `x = 0.53 m`) and a fading trail for
  phase-space plots; panels on one model grow together; axes widen smoothly as the data reach
  their edge; histograms can fill as events arrive (a peak emerging from the background). The
  action `grow` times a growth to words (`to: 4` stops part-way), and `zoom` with `x` / `y`
  zooms a plot's axes to a region and back. Fits and annotations wait for the data. Errors name
  the problem: an unknown name in an equation (did you mean), a missing initial condition, a step
  too large, a solution that blows up, a stiff system. No new dependency.

- **Error bars, fits, histograms and annotations on `plot`** (Step 223). Series take error bars
  (`y_err` / `x_err`: a number, a column, a list, `{minus, plus}`, or `sqrt` for √N) with their
  meaning in the legend (`± SD`, `± SEM`, `95 % CI`, `min–max`); `fits` draw fitted curves —
  linear, polynomial, exponential, power law, logistic, Gaussian and Breit–Wigner peaks over a
  polynomial background, or your own expression with named parameters — with the parameters ±
  standard errors (`k = −0.0846 ± 0.0017 d⁻¹`), R², χ²/ν for weighted fits, confidence or
  prediction bands and a residual panel; series with `values` are histograms (Sturges,
  Freedman–Diaconis, Scott, one bin per integer, explicit edges; counts or density) with fitted
  normal, exponential or Poisson distributions; `annotations` (point labels, arrows, reference
  lines, shaded ranges, notes) find a place that covers no data and no other text. The actions
  `fit` and `annotate` put a fit or an annotation on a word. Fitting needs no new dependency
  (numpy; checked against scipy in the tests). Plot text is larger (phone-readable), the plot
  fills its area (axes end just past the data, a legend or fit box without room moves beside the
  figure), legend entries appear with their series, dashed series have dashed swatches, and a
  line no longer crosses an axis break.

- **The chart core and the `plot` scene** (Step 222). A new scene type `plot` draws line and
  point series from inline numbers or a CSV in the project (units read from the headers: `time
  (s)`, `E [MeV]`) on linear, log, symlog, reversed or broken axes, with tick labels in plain
  numbers, powers of ten (`distance (10⁶ km)`, `2.5 × 10⁻³`) or SI prefixes (`time (µs)`, `10
  kHz`), units in the axis titles, gridlines (with a log axis' minor ticks), a legend in a free
  corner, several panels sharing an axis, and an equal aspect for orbits and trajectories. Data
  an axis cannot show (a zero on a log axis, a value inside a break or past `max`), unknown
  columns (with did-you-mean) and mixed units are errors from `vidgen validate`. It is built on a
  chart core without manim (`vidgen.plotcore`: ticks, number formats, axes, CSV tables, the
  layout of multi-panel figures) and a thin drawing layer (`vidgen.plot_draw`), both exported by
  `vidgen.api`. Existing chart scenes are unchanged.

### Genetics (Phase V, from Step 213)

- **Review of Phase V** (Step 221). A scientific-accuracy pass over the presets, reference
  sequences, HGVS, CRISPR, the lab methods, population genetics, GWAS and the lint rules found no
  wrong data (CFTR's legacy numbering, c. + 132, is now documented). Pedigrees use the frame better
  (the chart spreads sideways, a legend column beside it in 16:9, numbers beside the symbols, the
  9:16 chart sized to the cards it shows), place the proband's P where it belongs to no other label,
  and state an exclusion exactly ("— excluded unless I-1 is non-penetrant (Xᵃ Y; very unusual)").
  Normal chromosomes in a 16:9 `karyotype` lie across the frame; `mutation` with few codons puts its
  card beside larger rows; gel labels no longer overlap lanes or ladder bands; a coat colour is
  drawn on a dog for Labradors (`cross` param `animal`, a neutral fur patch when no animal is
  named); `crispr` fits a 9:16 frame. Fixed for every scene: a multi-line text in a font with
  ligatures (the light_academic headings' "fi") no longer moves letters onto the next line.

- **Example, guide topic and cookbook** (Step 220). `examples/cystic-fibrosis`: "Cystic fibrosis:
  from a family to a diagnosis" (about 4 min with Kokoro narration, a 9:16 variant) — a pedigree
  with the modes of inheritance tested, a Punnett square of two carriers, the carrier probability
  2/3 and the risk 1/150, *CFTR* at 7q31.2, c.1521_1523del p.(Phe508del) on the real sequence, an
  NGS carrier test and the carrier frequency from the incidence. A guide topic `vidgen guide
  genetics` and `docs/COOKBOOK-GENETICS.md` (choosing, NSGC / ISCN / HGVS / HGNC notation, exact
  numbers, reading a pedigree aloud, a counselling tone, common mistakes and their lint rules); the
  gallery's Genetics section links both. `dna_lab` NGS reads a **deletion** too (`variant:
  "6_8del"`: gapped reads bridged by a line, the call from the reads spanning it), its reads may
  run past the reference's ends (even coverage up to the edges; **the reads of an existing
  `ngs` scene change**), its tiles drop their letters when they would touch and its call card
  names the verdict in its heading. Lint: `label_spacing` and `max_words` treat a lone character
  on a plate (a DNA base) as a tile, not a label or a word; `contrast` finds the backdrop of a
  narrow glyph (`I`, `1`) beside it; `genetics_hwe` reads "q, the frequency of disease alleles, is
  about one in fifty" as q, not as the incidence.

- **Accuracy lint for genetics** (Step 219). Seven `vidgen lint` rules compare the narration and
  on-screen text with what each genetics scene computes: `genetics_ratio` (a ratio or share the
  `cross` does not give: "a 3:1 ratio" for a dihybrid, "half the daughters affected" for a carrier
  mother), `genetics_pedigree` (a chart that does not fit its stated mode, as an error; a dominant
  trait skipping a generation without reduced penetrance; father-to-son transmission of an X-linked
  trait; carrier and risk probabilities against the chart), `genetics_linkage` (RF over 50 %,
  distances and RF against the map, linked loci called unlinked), `genetics_hwe` (carriers called
  q², q against the incidence, carriers against 2pq), `genetics_crispr` (the wrong PAM for the Cas,
  a cut not 3 bp upstream of the PAM, sticky ends for Cas9, the spacer length), `genetics_karyotype`
  (ISCN that does not parse or lists its changes out of order, "45,X is male", a condition the
  karyotype does not show) and `genetics_hgvs` (HGVS invalid or not the scene's variant, legacy
  numbering such as p.Glu6Val unannounced; `ΔF508` / `R553X` shorthand as info). `science_naming`
  and caption italics know the genes of the new scenes; the narration–picture rules know their
  actions and targets. No new findings on any example or the gallery.

- **Population genetics** (Step 218). A `population` scene type: Hardy–Weinberg worked step by step
  with exact numbers — p and q from genotype counts, genotype frequencies, p or the incidence of a
  recessive condition (1/2500 → q = 1/50, carriers 2pq = 49/1250 ≈ 1 in 25.5), p² + 2pq + q² with an
  inbreeding coefficient, and a chi-square test of HWE with df = 1 — beside the population drawn as
  dots by genotype; and seeded Wright–Fisher simulations — drift (replicate lines, fixation and loss),
  selection (fitnesses or s and h; the deterministic course with drifting lines), mutation,
  migration between two populations, a bottleneck and a founder effect with the heterozygosity
  against H₀ Π(1 − 1/2N). A `gwas` scene type: a Manhattan plot (22 autosomes and X, the 5 × 10⁻⁸ and
  1 × 10⁻⁵ lines, peaks labelled), a QQ plot with λ_GC and a regional plot coloured by r², from a CSV,
  inline variants or a seeded synthetic study labelled "simulated data". New actions `simulate`,
  `resample`, `regional`.

- **Molecular genetics** (Step 217). A `mutation` scene type: a variant applied to a real coding
  sequence (HBB, CFTR, GJB2 reference windows with their exons and transcripts, your own sequence,
  or a gene written as in a `molecule` scene) and worked out with the genetic code — the reference
  codons with their amino acids and the variant row made from them (substitution, deletion,
  duplication, insertion, a frameshift regrouping every later codon to its premature stop,
  splice-site changes with the predicted mRNA) —, with HGVS notation generated and checked against
  the sequence (the 3′ rule, intronic positions, nonsense-mediated decay; `c.20A>T p.(Glu7Val)`,
  `c.1521_1523del p.(Phe508del)`, `c.35del p.(Gly12Valfs*2)`, `c.1657C>T p.(Arg553*)`, legacy
  names). A `crispr` scene type: guides found in a target (PAM `NGG` / `NNGRRT` right after the
  protospacer's 3′ end), the sgRNA's spacer checked, the R-loop, the blunt cut 3 bp upstream of the
  PAM, and the repair — NHEJ with a small indel or HDR from a donor — written in HGVS with its
  protein change on a coding target. A `dna_lab` scene type with `method: pcr | gel | sanger | ngs`:
  primers checked against the template with the product measured, a temperature trace and 2ⁿ /
  2ⁿ − 2n copies from the simulated strands; an agarose gel with a ladder and log-linear migration
  with the sizes read off; a Sanger chromatogram with called bases and a heterozygote; NGS reads
  with coverage and a variant call. New actions `mutate`, `scan`, `cleave`, `repair`, `run`.

- **Chromosomes** (Step 216). A `linkage_map` scene type: the heterozygote's homologue pair with
  its alleles (coupling or repulsion), crossing over between non-sister chromatids giving
  recombinant chromatids, and two- or three-point test crosses worked out from offspring counts
  step by step — parental and double-crossover classes, gene order, interval distances in cM
  (RF × 100, Haldane or Kosambi), expected and observed double crossovers, coefficient of
  coincidence and interference, the map; or loci at map positions with `measure`. A `karyotype`
  scene type: ISCN notation parsed and checked (47,XX,+21; 45,X; 47,XXY; del, dup, inv,
  t(9;22)(q34;q11.2), rob(14;21)(q10;q10)) and drawn as a karyogram in the Denver groups with
  schematic G-banded ideograms (true relative lengths and centromeres) and the change highlighted,
  or as ideograms with structural changes played as edits; a card reads the notation. `cell_cycle`
  meiosis takes `nondisjunction: {division: I | II, pair}`: aneuploid gametes labelled with their
  shares and the zygotes they make. New actions `cross_over`, `measure`, `rearrange`. The committed
  gallery's budget is 13 MB (each entry at most 0.36 MB).

- **A `pedigree` scene type** (Step 215): a family chart in standard human pedigree nomenclature
  (NSGC: squares, circles, diamonds; affected filled, carriers dotted or half-shaded, deceased
  struck, proband arrow with P, consanguinity double line, MZ / DZ twins, adoption brackets,
  miscarriage triangle, a proposed child dashed with ?) laid out by generation (Roman numerals,
  individuals numbered left to right, sibships in birth order, partners beside), written as one
  line per person (`"II-3: female affected of I-1 + I-2"`) or mappings. Its genetics are worked
  out exactly: which modes of inheritance fit (AD, AR, XD, XR, Y-linked, mitochondrial; each
  excluded one with its reason, e.g. father-to-son transmission), reduced penetrance, the
  genotypes the chart forces (obligate carriers), carrier probabilities by Bayes' rule (2/3 for an
  unaffected sibling under AR) and the risk for a proposed child with its factors (2/3 × 1/25 ×
  1/4 = 1/150). The actions `deduce`, `analyse` and `risk` put each step on a word; `reveal`
  brings in generations or people. Validated with the reason (two fathers, a cycle, twins who are
  not siblings, a male carrier under X-linked inheritance).
- **A `cross` scene type** (Step 214): a genetic cross worked out exactly and drawn — the parents
  with their homologous chromosomes, genotypes in standard notation and phenotype pictures (peas,
  flowers, flies, coats, blood groups…), their gametes flying out to a Punnett square's headers
  (each allele in its homologue's colour; recombinants of linked genes ringed, with their exact
  frequencies), the square filling cell by cell or row by row (up to 8 × 8; a branch, forked-line,
  diagram for larger crosses), and the offspring counted into genotype and phenotype classes —
  exact fractions, percentages, whole-number ratios (9 : 3 : 3 : 1, 9 : 3 : 4, 2 : 1 with the
  lethal class crossed out; X-linked crosses split by sex). `P: [RRYY, rryy]` shows P → F1 → F2,
  `kind: test` makes the tester, `kind: reciprocal` swaps the sexes; `observed` counts add a
  chi-square test (χ², df, p, critical value, verdict). The actions `form_gametes`, `fill`,
  `count`, `ratio` and `chi_square` put each step on a word; without them the scene plays itself.
  16:9 and 9:16; validated with the reason (alleles, sexes, phase, counts for classes that do not
  exist, a cell filled twice).
- **The genetics model** (Step 213, no scene type yet; `vidgen.genetics`, also in `vidgen.api`):
  loci and alleles in standard notation (`A`/`a`, `I^A` shown as Iᴬ, `c^{ch}`, wild type `w^+` or
  `+`, X-linked alleles written on their chromosome, `X^H X^h`, `X^h Y`); dominance — complete,
  incomplete, codominant, or a hierarchy of multiple alleles such as `"I^A = I^B > i"`; lethal
  alleles; penetrance and expressivity; epistasis (recessive 9:3:4, dominant 12:3:1, suppression
  13:3, duplicate 15:1, complementary 9:7, cumulative 9:6:1); autosomal, X-, Y-linked and
  mitochondrial loci; linkage with recombination frequencies (coupling / repulsion written
  `AB/ab` / `Ab/aB`, interference for three loci, no crossing over in Drosophila males). An exact
  cross engine computes gametes and offspring genotype and phenotype distributions as fractions,
  with test and reciprocal crosses; 15 presets of textbook crosses (`abo`, `labrador`,
  `drosophila_white`, `drosophila_b_vg`…). Mistakes are refused with the reason: an allele not
  defined for its locus (did-you-mean), a female with a Y, an X-linked allele written without its
  X, linked loci without their phase, a recombination frequency above 0.5. The scene types
  (`cross`, `pedigree`, `karyotype`, `linkage_map`, `mutation`, `crispr`, `dna_lab`,
  `population`, `gwas`) follow in Steps 214–218; plan in `DESIGN.md` §96.

### Cell biology in physical scale (Phase U, from Step 202)

- **A `cell` scene type** (Step 202): a cross-section of an animal cell at textbook sizes in µm
  — nucleus with its two membranes 30 nm apart, nuclear pores and a nucleolus, rough ER studded
  with ribosomes, smooth ER, a Golgi stack (cis face towards the nucleus), the centrosome,
  mitochondria with cristae, lysosomes, peroxisomes, vesicles and 25 nm ribosomes
  (`contents: typical`), plus your own `objects` (`kind`, `at` in µm, `in:` a compartment, `on:`
  a membrane, `count`). Every place is checked by `vidgen validate`: a ribosome in the
  nucleoplasm, a mitochondrion inside the nucleus or a ribosome on the Golgi is refused with the
  textbook reason, and typos get a did-you-mean.
- **A camera in µm** with an automatic **scale bar**: the `zoom_to` action moves between levels —
  tissue, cell, organelle, molecular complex (one ribosome on the ER, a nuclear pore) — on a
  spoken word (`at: "@ribosome"`), zooming at an even pace on a log scale and out on the way
  between far places; **level of detail** switches as things grow on screen (double membranes,
  cristae, nuclear pores, ribosome subunits, 5 nm lipid bilayers). Labels and the scale bar keep
  their size on screen, in 16:9 and 9:16. See `docs/CONFIG.md`, `cell`.
- **The structure library** (Step 203): accurate morphology at every zoom — the nuclear envelope
  continuous with the rough ER, pores with spokes and baskets, nucleolus parts and
  heterochromatin; a smooth-ER tubule network; Golgi cis / medial / trans cisternae with rims and
  buds; mitochondria with crista junctions; early and late (multivesicular) endosomes; clathrin,
  COPI and COPII coated vesicles; centrioles with nine triplets. **Plant cells** (`cell: plant`:
  wall with middle lamella, plasmodesmata, central vacuole, chloroplasts with grana and stroma
  lamellae) and **bacteria** (`cell: bacterium`, Gram-negative or positive, capsule, nucleoid, 70S
  ribosomes, plasmids, flagella, pili). The **cytoskeleton** (microtubules with − and + ends from
  the centrosome, actin cortex and stress fibres, intermediate filaments) and **motors**
  (kinesin, dynein, myosin, with cargo). Bilayer close-ups with phospholipids, cholesterol,
  glycolipids, glycocalyx and a lipid raft; `style: surface` draws things whole, seen from
  outside. Each `zoom_to` view names the parts it shows (`labels:`); a dim during a zoom keeps
  its opacity; the scale bar has a text at any depth.
- **Molecules and notation** (Step 204): a **`molecule` scene type** for close-ups in nm — B-DNA
  with antiparallel strands, 5′/3′ ends, A–T / G–C base pairs and major / minor grooves; mRNA
  (cap, codons, poly(A)), tRNA (cloverleaf or L, anticodon checked against the genetic code),
  rRNA; the nucleosome (147 bp, 1.65 turns, histone marks such as H3K27ac checked against the
  histone sequences) and chromatin; proteins with domains, kinases, phosphatases, G proteins,
  GPCRs, RTKs, gated ion channels, carriers (uniport / symport / antiport), the Na⁺/K⁺ pump and
  ATP synthase in a membrane drawn between its two compartments; ATP, GTP, cAMP, Pᵢ, glucose,
  ions — and the same molecules as `cell` objects (`{kind: atp_synthase, on: mitochondria}` lines
  the cristae). Orientations and places are checked (*ATP synthase F₁ must face the mitochondrial
  matrix*); gene symbols are italic and checked per species (*TP53*, *Trp53*, *CDC28*), proteins
  roman; P / Ub / Ac / Me markers on the residues they go on; charges typeset (Ca²⁺, HCO₃⁻).
- Step 203's zoomed views now point every label at its part (the matrix beside a crista, the
  glycocalyx outside the bilayer), stroma lamellae join grana at their margins, and a ring of
  smooth-ER tubules is no longer drawn filled.
- **Transport and membrane processes as actions** (Step 205). In a `molecule` scene: `solutes`
  (particles at their concentrations, typical mammalian values by default), `potential` (a live
  Vₘ readout and the membrane's charges), concentration bars; `set_state` morphs a molecule
  (a channel opens or inactivates, a carrier turns through its occluded state, the Na⁺/K⁺ pump
  goes E1 → E1P → E2P → E2 with its phosphate shown); `transport` runs a channel (ions one by one
  down their electrochemical gradient, only its own ion), a carrier's alternating access
  (`transporter: sglt1`, `ncx`, `glut1`…), the pump's Post–Albers cycle with ATP → ADP + Pᵢ, H⁺
  pumps (P- and V-type), ABC transporters and aquaporins; `diffuse` (random walks with net flux
  down the gradient), `osmosis` and `action_potential` (channels in step with a trace from −70 to
  +35 and −80 mV in an inset plot). In a `cell` scene: `motor_walk` (kinesin's 8 nm steps to the +
  end, dynein's to the − end, carrying cargo), clathrin-mediated `endocytosis` (coated pit, dynamin
  scission, uncoating) and `exocytosis` (SNARE docking, fusion pore, cargo release). The rules
  come with reasons: *Na⁺ cannot pass a K⁺ channel*, *an antiporter moves its solutes opposite
  ways*, *active transport needs an energy source: ATP or an ion gradient*, *kinesin-1 walks
  towards a microtubule's + end*; states are replayed beat by beat by `vidgen validate`. New
  molecules `h_atpase`, `abc_transporter`, `aquaporin`, `water`, `o2`, `co2`, `drug`. Lipids leave
  room for membrane proteins in cell close-ups, and several membrane proteins in a tall frame go on
  membrane rows.
- **Gene expression as actions** (Step 206). A `gene:` param — a coding-strand `sequence` with
  intron spans, a `protein`, or generated from `codons` and a `seed` (TATA box, Kozak AUG, GU…A…AG
  introns, AAUAAA; a bacterium: −35/−10, Shine–Dalgarno, terminator). In a `molecule` scene, a
  close-up with every base and amino acid written: `transcribe` (GTFs and RNA polymerase II at the
  promoter, a ~13 bp bubble, the template read 3′→5′, an 8 bp RNA–DNA hybrid), `cap`, `splice`
  (snRNPs, the branch A, the lariat, EJCs), `polyadenylate`, `export` through a nuclear pore,
  `translate` (scanning to the AUG, A/P/E sites, codon–anticodon pairing with wobble and
  inosine, the chain growing N→C through the tunnel, eRF1 at the stop codon, ribosome
  recycling), `target_er` (SRP, its receptor, Sec61, signal peptidase), `glycosylate` (OST,
  Glc₃Man₉GlcNAc₂ in SNFG symbols) and `fold` (Hsp70, chaperonin, BiP, calnexin). In a `cell`
  scene the camera follows the products: `transcribe`, `export`, `translate` (free polysomes or
  the rough ER), `to_golgi` (COPII, cis → trans) and `secrete` (to the outside, the membrane or a
  lysosome). The order is checked by `vidgen validate` with reasons (*only proteins made into the
  ER enter the secretory pathway*).
- **Signalling pathways** (Step 207): a `pathway` scene type in SBGN-inspired notation — proteins,
  complexes, second messengers, genes (italic) and outcomes, with their states (GDP / GTP, pS133);
  arcs that activate (arrow), inhibit (T-bar), catalyse (circle), (de)phosphorylate (P), bind,
  translocate into the nucleus, regulate transcription — laid out by itself in compartment bands
  (extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus: columns in 16:9, rows
  in 9:16), routes never crossing a node, the nuclear envelope with pores where arcs pass. Three
  templates checked against the textbook account: `gpcr_camp_pka`, `rtk_ras_mapk`, `pi3k_akt`
  (changed with `nodes`, `edges`, `remove`). Actions: `signal` (wave by wave: GDP → GTP, marks
  appear; an inhibitor of an inhibitor turns its target on), `inhibit`, `knockout` and `drug` (the
  effects downstream computed from the graph, ↑ / ↓ on each node that changes; known drugs checked
  against their targets), `amplify`, and `focus` on nodes. `vidgen validate` refuses unknown nodes,
  arcs against declared effects (a GAP activating Ras), impossible compartments (a gene outside the
  nucleus, a transcription factor in the cytosol on its gene) and names in the wrong case for the
  species, and warns about loops not marked `feedback`.
- **Cell cycle, division and energy** (Step 208): a `cell_cycle` scene type — the cycle as a ring
  (G1, S, G2, M with its stages, the restriction point, G0) with the G1/S, G2/M and spindle
  checkpoints and the cyclin–CDK levels (D–CDK4/6, E–CDK2, A–CDK2, B–CDK1) under a "now" marker;
  mitosis (2n = 2–8, homologues coloured, sisters joined at the centromere; `cell: plant` with a
  cell plate) and meiosis (synapsis, chiasmata with exchanged segments, independent assortment,
  four haploid recombinant cells) with captions and counts. A `metabolism` scene type —
  glycolysis (investment and payoff phases, net 2 ATP and 2 NADH; `link: true` adds pyruvate
  dehydrogenase), the citric acid cycle as a ring (3 NADH, FADH₂, GTP, 2 CO₂), the respiratory
  chain (I–IV, Q, cytochrome c, protons into the intermembrane space, ATP synthase) and the light
  reactions (PSII, PQ, b₆f, PC, PSI, Fd, FNR → NADPH), with tallies. Actions: `advance` (round the
  cycle, through a division's stages, along a pathway, electrons and protons down a chain, the
  gradient through ATP synthase) and `checkpoint` (pass or arrest with its cause; regulators lit
  in order). `vidgen validate` refuses wrong counts after meiosis (`expect`), G0 after R, passing
  an arrested checkpoint, a chain in the wrong membrane and protons pumped the wrong way.
- **Scientific accuracy lint and references** (Step 209): seven `vidgen lint` rules read the
  config and the narration — `science_scale` (a `cell` with a scale bar drawing something far
  outside its textbook size; new `not_to_scale: true` shows a "not to scale" note instead),
  `science_location` ("glycolysis in the mitochondria", "ribosomes in the nucleus" while the
  scene shows them in the cytosol), `science_direction` (RNA made 3′→5′, proteins C→N, kinesin to
  the minus end, protons pumped into the matrix), `science_energy` (active transport through a
  channel, or with no energy source shown), `science_naming` (mouse *Trp53* gene vs TRP53
  protein, the wrong case, a gene label without italics), `science_pathway` (narration against an
  arc's effect) and `science_counts` (net 2 ATP from glycolysis, 3 NADH per turn, 3 Na⁺ / 2 K⁺ per
  pump cycle…), each with the textbook fix; 0 findings on the examples. `said_before_shown` knows
  the cell-biology actions and targets. Scenes take **`references:`** (`{label, doi | pmid | isbn |
  url}`, formats checked offline) and `figure_credit:`; beats `cite:` them; they show as small
  citations (`citations: {show: footer | marker | card | none}`, numbered across the video) and
  as a numbered list in `<output>_chapters.txt`.
- **Example, guide, cookbook and gallery** (Step 210): `examples/gene-to-secreted-protein`, "From
  gene to secreted protein" (about 3:34 with Kokoro): α1-antitrypsin from its gene in a liver
  cell to the blood — a zoom into the nucleus, transcription, capping, splicing,
  polyadenylation, export, translation, SRP targeting, N-glycosylation and calnexin up close, the
  route through the Golgi to secretion across the cell, exocytosis and the IL-6–STAT3 pathway;
  references, concept colours, the `discovery` bed, a 9:16 variant. A guide topic (`vidgen guide
  biology`: choosing the scene, accuracy, naming, references, pacing) and
  `docs/COOKBOOK-CELL-BIOLOGY.md`. The scene gallery has one **Cell biology** section with the five
  types and five showcases (a plant cell, the sodium pump, a MEK inhibitor, mitosis, the
  respiratory chain); gallery stills are now palette PNGs (about 40 % of their size, the room for
  the showcases). Fixes found on the way: a cell route's transcription caption no longer mentions
  schu-video-generator's molecule scene; a zoomed `cell` view and a gene close-up no longer report their cropped
  world as `off_frame`; the close-up's "schematic: not to scale" is at the readable size, in the
  safe area and clear of the protein's readout in 9:16.
- **Review of Phase U** (Step 211): drawings use the frame better — molecule scenes put three or
  more membrane proteins on rows when that frames them larger (also beside a plot in 16:9), and
  in 9:16 the action-potential plot spans the panel above the concentrations; a gene close-up in
  9:16 shows 15 slots across (was 18) and takes a tall frame's layout even when its view is wider
  than tall (a 36-slot strip before); a vesicle near the plasma membrane is framed with the
  membrane it fuses with; pathways grow up to 1.9× and spread their ranks to use the height;
  glycolysis grows to fill. Step captions are never below the readable size and are their
  first clause in 9:16 (`notes: auto | full | short | false`). `exocytosis` names generic
  v-/t-SNAREs by default, `snares: constitutive` (a VAMP, syntaxin-4, SNAP-23) or `neuronal`
  (synaptobrevin/VAMP2, syntaxin-1, SNAP-25, Ca²⁺ on synaptotagmin); the example uses the
  constitutive set with its captions on. The captions overlay sets the gene symbols the video
  declares in italics (`genes: true`). Enzyme names in `metabolism` are roman (proteins).
  Calnexin is anchored in the ER membrane by a stalk; ribosomal subunits part in the cytosol on
  the ER; Sec61 is named beside the channel; ion channels are named by their ion (Na⁺ channel);
  overlapping labels fixed (band names in 16:9 pathways, side names of membrane rows, the light
  reactions' P side in 9:16, leader lines of label rows in 9:16); cell-scene products travel on
  gentle curves; a motor's cargo vesicle is kept off the organelles. `scenes/molecule.py` is
  split (the process runtime in `scenes/molecule_runtime.py`).

### vidgen studio: a music workstation for people (Phase T)

- **`vidgen studio [PROJECT] [--port N] [--no-browser] [--clean]`** (Steps 193–200) opens a
  small web app on 127.0.0.1 in your browser, offline, with no new dependency: load any of the
  17 built-in beds as an editable score file and change it with controls (key, tempo, seed and
  chords; sections dragged, looped and edited; tracks with mute / solo, volume, pan, steps
  text; an inspector with every instrument's settings as sliders, effects as chips, per-section
  changes and a step grid) or by typing the YAML; problems show inline with the command line's
  did-you-mean messages while the last good render keeps playing. The sound is always schu-video-generator's
  own renderer: an edit renders only the tracks it changes and plays on from the same moment,
  also under the narration sample. See `docs/CONFIG.md`, "Music studio".
- **Check, versions, A/B, export** (Step 197): `vidgen music check` after each render (verdict,
  spectrogram with sections, advice with **Apply** where the fix is mechanical); every change is
  a version (undo / redo, rename, star, branches); A/B against the original or any version at
  the same moment and level; export YAML / WAV / MP3 or save into `assets/music/`.
- **Listening notes and "Ask an agent"** (Step 198): pin notes on the timeline while listening;
  an AI agent answers them through new MCP tools (`studio_sessions`, `studio_read`,
  `studio_check`, `studio_propose`) with a new version and one line per note, which you A/B and
  keep or discard; or copy the prompt into any chat assistant; or (optional, paid) OpenRouter.
- **Variations** (Step 199): four deterministic siblings of a version — harmony, pattern, mix,
  energy — rendered and checked side by side; play, keep, "more like this", shuffle; MCP
  `studio_variations`.
- **Polish** (Step 200): keyboard shortcuts (Space, N, L, M / S, V, Ctrl+Z / Ctrl+Shift+Z, ? for
  the list), tabs for the inspector, score file and notes in medium and narrow windows, a light
  theme checked for WCAG AA contrast, a first-run hint, a clear message (and automatic
  reconnection) when the studio server stops, the open variations and the last hand-off shown
  again after a reload, every variation batch listed to come back to, and a disk rule for old
  renders and exports (versions, notes and checks are never removed) with **Clean up** and
  `vidgen studio --clean`. The Listen page and the README link to the studio; the author guide
  tells agents when to suggest it; `docs/COOKBOOK-MUSIC.md` §7 walks through a session.
- **Review** (Step 201): hardened against hostile requests (request lengths, numbers, names
  with a trailing newline or other scripts' digits, Windows device names when saving, YAML
  aliases that expand to millions of values, a session folder linked elsewhere); OpenRouter is
  called only with the person's confirmation; edits of pieces at most tempos render 2–3 times
  faster with a third less memory (the same 16-bit audio as a video's); 5-minute pieces no
  longer run out of memory; exports are at most 10 minutes (was 30, which ran out of memory);
  `vidgen studio --clean` leaves a running studio's open session alone.
- Compatibility: additive. The beds, their templates, existing projects' mixes and every
  existing command are unchanged.

## 0.3.0 (Steps 61–192)

0.2.0 made narrated explainer videos that an AI agent can check and fix by itself. 0.3.0 adds
**cartoons**: original characters who talk with lip sync, move, act and react on drawn stages,
indoors and outdoors, with weather, props, vehicles, sound and music, written as YAML or as a
screenplay. It also adds two narration providers (OpenRouter, and Kokoro running free on your
own computer), OpenRouter pictures including SVG, an `output/` folder and `--jobs auto`; a
cartoon host beside any explainer scene, lines spoken with feeling, drafts and animatics,
ready-made sets, drawing styles, word-level readback flags and dubbing, music composed for
each video and played with real instruments, side-view platform stories (levels written as
small maps, planned walks and jumps, keys, doors, coins and friendly blockers), and a
presentation toolkit for explainers and coding Shorts (actions on a spoken word, one colour per
concept, code that morphs, a terminal, function plots and geometry, charts that change, and a
lint check of narration against the picture), and isometric story places (a village or a room
written as a small map, seen from above, where the cut-out characters walk round what is in the
way, hand things about, open doors and light lamps).

0.3.0 was prepared in Step 132; the work of Steps 133–170
(Phases M, N, O and P in `tasklist.md`, Step 165 and Phase Q) is part of this release.

### Behaviour changes and possible breaks

Changes that affect projects made with 0.2.0:

- **Videos go to `output/`** (Step 66): the MP4, `.srt`, `_chapters.txt` and thumbnail are
  written to `<project>/output/`, not the project folder. Set `output_dir:` or pass
  `--output-dir` to choose another folder. An MP4 left in the project folder by 0.2.0 is not
  found by `export` or `slides`: render again, or pass `--output-dir <project folder>` (the
  flag is relative to the current folder).
- **ffmpeg 4.4 or newer** (Step 64). Crossfades, pushes and wipes now work on ffmpeg 7.0 / 7.1
  (they failed with "frame rate 1/0 is invalid"). With an older ffmpeg, the error names the
  version.
- **`[laugh]`, `[gasp]`, `[sigh]`, `[hmm]`, `[giggle]`, `[groan]` in a beat's text** are now
  voice sounds (Step 99): they are spoken or played as sounds and left out of captions. Before,
  they were read out as text. Such beats get new audio hashes. Other brackets stay as text.
- **`*word*` in a beat's text** marks emphasis (Steps 90–91): the asterisks are removed before
  TTS, captions and readback. Beats with asterisks get new audio hashes. Other beats keep
  theirs.
- **The first render after upgrading renders every scene again**: the scene cache key includes
  the schu-video-generator version.
- **`--jobs` accepts `auto`** (Step 117). A bad value now gives the error `invalid value: 'x'
  (a whole number, or auto)` instead of argparse's message.
- **A Kokoro voice of another language is dubbed** (Step 143): in a video (or variant) whose
  `language:` is not the Kokoro voice's, schu-video-generator now picks a Kokoro voice of the video's language
  of the same kind (female / male) instead of reading the text with the wrong pronunciation and
  only warning. `vidgen validate` prints the choice (`dub [pt]: ...`). Write `lang:` on the voice
  to keep it on purpose, or `dub: {LANG: VOICE}` to choose. Those beats get new audio.
- **New lint warnings** (Steps 157, 163): `concept_colors` (more than 5 concept colours, a
  concept colour hard to read on the background, a term coloured otherwise by a scene setting;
  only with `terms:`) and `said_before_shown` (the narration names a label on screen more than
  1.5 s before it appears). `vidgen lint --fail-on warning` may now fail on a project that passed:
  show the label on the word (`{reveal: ..., at: "@word"}`), or set
  `lint.rules.said_before_shown: {severity: off}`.
- **Built-in pronunciation entries** (Step 165): schu-video-generator now respells some words for some voices
  in every project (`vidgen list-pronunciation` lists them): Kokoro's English voices say `README`
  as `readme`, `JSON` as `Jason`, `YAML` as `yammel`, `ReLU` as `ray loo` and more, and its
  American voices `epoch` as `E pock`. The audio hash covers the spoken text, so **existing Kokoro
  audio of beats with these words becomes stale**: `vidgen validate` counts them in `audio:` and
  prints `pronounce: built-in kokoro-en-us changes N beat(s): ...`; `vidgen tts` regenerates only
  those beats. To keep the old audio, set `pronunciation_defaults: false` or drop an entry with
  `term: null`. A project entry for the same term wins, so projects that already respell a word
  keep their audio. ElevenLabs and OpenRouter videos are unchanged (no lists for them yet).
- **Readback transcripts** (Step 141): `vidgen readback` keeps faster-whisper's word
  probabilities in its cache; a cached faster-whisper transcript without them is transcribed
  once more (local, free). Audio for faster-whisper is decoded with the ffmpeg executable.

Cartoon behaviour that changed during the 0.3.0 cycle (cartoons are new in 0.3.0, so this
matters only for projects made with development builds between Steps 67 and 131):

- **Default ambience beds** (Step 128): `ambience: true` by default. Outdoor stages in daylight
  get birdsong, rooms get a quiet room tone, doors creak instead of whooshing, and boats, pours
  and wet steps splash. To keep only the rain and fire beds, set `ambience: false` at the top
  level. `foley: false` turns off all of these sounds.
- **Generated characters' legs** (Step 92): `legs` is split into `leg_left` / `leg_right`
  (with `_lower` shins), and arms gained `arm_left_lower` / `arm_right_lower`. On a generated
  character, a pose of your own with `legs:` does nothing (validate warns) and a `NAME.legs`
  keyframe target is an unknown part. SVG characters may still use one `legs` piece. In an SVG,
  `id="arm_left_lower"` now names a part, not a shape of `arm_left`.
- **Interrupt timing** (Step 102 follow-up): `interrupt: true` without `overlap` now starts 70 %
  of the way into the earlier line's last word (0.2 s before its end without word timings),
  not 0.5 s before the end. It no longer cuts a whole word. Lint `talked_over` reports
  interrupts that cut words.
- **`auto_direct` adds effect symbols** (Step 107) such as `!` and `?` on strong expression
  changes. Use `auto_direct: {effects: false}` to turn them off.
- **Motion effects** (Step 108): with `cartoon_motion: lively` (the default) or `calm`, jumps
  land in dust (impact stars on hard landings), and fast walks, throws and blown props get
  speed lines. Turn them off with `motion_effects: false` or `cartoon_motion: none`.
- **Soft shadows on by default** (Step 97) under characters and props. Use `shadows: false` to
  turn them off.
- **Stage fades** (Steps 116a, 127): a stage fades in, and then out, as one picture instead of
  each thing on its own. Nothing behind another thing shows through during the fade. The first
  and last second of every stage scene look different from before.
- **Smaller seats** (Step 102): chair, box and rock are drawn lower (0.26 / 0.155 / 0.155 of a
  character), and a seated character's hips rest on the seat.
- **Reframing** (Step 96): a stage whose characters do not fit in one view pans to the speaker
  on its own (in 9:16 also laid out at 16:9 width). Set `reframe: none` to stop this.
- **Close-ups by `auto_direct`** (Step 95) are now `shot: closeup` cuts, not 0.03 s zooms.
- **Wind is stronger at `windy` and above** (Step 104). Rain on a stage lands on the ground
  with splashes and has a rain sound bed (Step 105).
- **`vidgen screenplay`** (Steps 113, 115, 130): it now picks from 11 looks (the first six as
  before), then random looks that contrast well. An exit's edge is written as `to` (it was
  `side`, which validate refused). Manner words that name a feeling (`(excited)`,
  `(whispering)`) also set the line's `emotion` (Step 135), so those lines get new audio; a
  `set:` line naming `bench`, `fence`, `log` and the other new outdoor props now places them
  instead of writing a `# TODO` (Step 139).
- **A beat ends on its planned frame** (Step 191): when a beat's narration and pad came to half a
  frame, a scene could run one frame longer or shorter than the video plan, and every caption
  and timed overlay after it was off by that much (2–3 frames by the end of a video, with a
  render warning). Such scenes are now a frame shorter or longer than before, as planned.

### Cartoons: characters

- A character model of named vector parts with pivots (67); a parametric generator with body
  shapes, heads, hair, eyes, noses and accessories (68); imported SVG characters split by `id`
  (69).
- Poses and expressions with eased part-by-part changes, plus poses of your own (70). Later
  steps added more expressions: `laughing`, `blushing`, `tongue_out`, `crying`, `dizzy`,
  `frightened` (125).
- Lip sync from visemes timed by the stored word timings (71); blinking and idle motion (72).
- Arms and legs that bend, with a two-bone solver (92), and a front view (111).
- Bodies, outfits, patterns, shoes, hair, beards and accessories (113). Original animal
  species: cat, dog, bird, bear, rabbit, mouse (114); fox, owl, frog, turtle, penguin (123).
  Robots and costume pieces (124).
- `vidgen cast --random N` writes a cast whose characters look clearly different from each
  other; lint `look_alike` warns when two characters look too alike (115).
- `vidgen character` and `vidgen character-sheet` (also over MCP) show every pose, expression
  and mouth shape (68, 83).

### Cartoons: stages, sets and props

- The `stage` scene type: a background, a ground, marks, depth (73); parallax layers and a
  camera that can `pan`, `zoom` and `follow` (74); shots `wide` / `two_shot` / `over_shoulder` /
  `closeup` / `medium` (95); vertical videos that follow the speaker (96).
- Props drawn from primitives (75), and SVG props. More props followed: basket, umbrella and
  napkin (103); furniture (110); everyday small props such as cake, book, phone, gift, balloons
  and watering can (122).
- Rooms with walls, floors, windows and doors (109–110); walking in depth (111).
- Props that move by themselves: clock, tv, lamp (120); fireplace, kettle, falling fruit, birds
  (121).
- Vehicles: bicycle, car, bus (118); boat, hot-air balloon, toy rocket (119).
- Reusable casts and sets with `include:` and `set:` (101); `cartoon_style` for generated
  backgrounds (77).
- Ready-made sets for `set: NAME` without writing `sets:`: outdoors `city_street`, `park`,
  `beach`, `forest`, `snowy_hills` (139) and rooms `classroom`, `kitchen`, `shop`,
  `living_room`, `bedroom` (140), with 18 new props (shop, bench, fountain, pine, blackboard,
  school desk, shelf with goods, till...) and marks for two characters and every seat.
- A drawing style for the whole video: `drawing: {outline: thin | normal | bold, shading: flat |
  soft, texture: none | paper | storybook}` (142); the default draws exactly as before.

### Platform stories (Phase O)

- A `stage` scene with a `level:`: a side view written as a small ASCII map (ground, floating
  planks, one-way clouds, ladders, gaps, spots by letter), drawn once into tiles in the cartoon
  look, with the background and layers moving behind by parallax (150).
- Walks along the tiles (steps, ladders, stopping at edges) and jumps planned from the author's
  intent (`jump: pip, to: cloud`): a crouch, a slow arc checked against the tiles, a squash and
  a wobble on landing; `vidgen validate` replays every move and says why one cannot be made (151).
- Story props: coins and stars picked up on the way and in the air, a `key` prop and locked
  `door`s (`level.locks`), friendly blockers (`level.blockers`, `step_aside`), reactions on the
  move (`react: {when: pickup | land | arrive}`) (152); their sounds (`coin`, `twinkle`,
  `unlock`, a soft landing) through the foley (153).
- A camera that follows the hero gently (`level.follow`), up and down on tall levels; a short
  map in 9:16 sits on more ground; `character_size: small | medium | large` for the video, a
  variant or a scene (also on plain stages); lint `small_speaker` (154).
- A `snail` species; a set's sky, layers and light on a level (not its props); `vidgen
  screenplay` with a level from a front-matter set and `jumps onto` directions; portrait
  close-ups no narrower than a face; the example `examples/platform-story` (155).

### Isometric story places (Phase Q)

- A `stage` scene with an `iso:` place: a village, a garden or a room written as a small ASCII
  map with heights (grass, paths, water, garden walls, doors, raised blocks, spots by letter),
  seen from above at an angle; ready-made objects (house, tree, lamp, well, bench, bridge,
  flowers, table, sofa, bed...); indoor rooms with their front walls cut away; the characters
  stay the flat cut-outs, hidden by what stands in front of them (166).
- Moves on the place: `walk_to` / `run_to` a spot along a route round objects, water and walls
  and up steps, `meet`, `wander`, `after:` a leader, `enter` / `exit` over the edge or by a door;
  `vidgen validate` replays them and says where the way stops (167).
- Staging: shots and `follow` on the place (sharp in close-ups), `pan` to a spot; small things
  picked up, given and put down (checked in cells); `open` a house's door or flowers (they
  bloom), `switch_on` a lamp, `reveal` / `hide` an object (a bridge appears) (168).
- Mood and sound: `light: morning | sunset | night` with lit lamps and windows glowing, rain
  landing on the place, name tags over small speakers in wide views, footsteps by the ground
  (grass, path, boards, bridge, stone), door, pick-up and bloom sounds, crickets at night; lint
  `offscreen_action`, and `hidden_speaker` / `small_speaker` measured on the place (169).
- The example `examples/iso-story` (16:9 and 9:16), the guide topic `iso`; rain from a scene's
  start darkens an iso place to the rainy tint unless the scene sets a `light`; a held thing
  fades with a character leaving the place; a walk to where someone stands across a stream is
  refused instead of ending on the near bank; lint `said_before_shown` no longer takes a name
  tag for a label (170).
- Review (171): each iso scene starts on a wide view that fills the frame (16:9: the place's
  tips cut, never a spot, a character or a placed object; 9:16: the part where the characters
  stand, up to twice as close), and `shot: wide` is that view; `pan` to a spot moves in from it;
  a lit lamp lights the characters next to it at night; a larger `flowers` or `bush` is a flower
  bed or a hedge (a clump per cell); the JSON Schema takes a bare `on: true` as YAML 1.1 reads it.
- Weather polish (Phase R, 172): rain on an iso place lands on roofs, crowns and the bridge
  instead of under them; `puddles: true` grows puddles with ripples on its grass and paths;
  `settle: true` snow turns its ground, roofs, block tops and treetops white (both were refused
  before); a run's speed lines follow its diagonal. Iso rain scenes and runs render a little
  differently than in Step 171 (splashes on the roofs, slanted speed lines).
- A new scene type `iso_diagram` (173): architecture and data-flow diagrams of blocks in the
  isometric view (boxes, slabs, cylinders and databases, flat tiles; a block with `layers` is a
  stack), group plates and connectors along the grid (flat arrows, dashed, pipes), with flat
  labels that stay readable, placed in order (`arrange`, a zigzag in 9:16) or on the grid
  (`at`), fitted to 16:9 and 9:16.
- `iso_diagram` actions (174), timed like any action (`at: "@word"`): `build` (blocks grow up
  from the floor, drop in or fade in on the word; the scene leaves them to it), `raise` /
  `lower` (with a shadow), `explode` / `collapse` (a stack's layers apart and back, labels
  going along), `flow` (dots or packets along connectors, one after another with `chain`),
  `focus` (the camera onto a part, staying) and `relabel` (a label or value changes in place);
  `dim` and `highlight` keep the blocks' shading. New params `build: each` (one block or stack
  per step), `entrance` (`drop`, `grow`, `fade`) and `portrait_grid` (an `at` grid slanted down
  a 9:16 frame); a target `diagram`. Labels are placed right by their blocks (with a leader
  line when pushed away), clear of other blocks and labels; a group's caption by its plate's
  front edge, connector labels along the connector, one label per block; a stack's layers are
  listed under it with colour swatches in 9:16, where it is drawn larger. A lint rule
  `iso_labels` reports labels over other blocks, labels or connectors, or far from what they
  name.
- The example `examples/iso-web-page` (175, 16:9 and 9:16): "What happens when you open a web
  page", a two-minute explainer of a request from the browser to the database and back and of
  the browser's rendering steps, in three iso diagrams with a title and a recap. Fixes found
  while making it: a diagram is fitted at the largest scale that fits even when a smaller one
  does not (a label pushed clear at one scale can lie by its block at a larger one; a diagram
  could come out at a third of its size), `focus` keeps its targets clear of the captions, and
  `focus: diagram` goes back to the whole frame (it zoomed onto the diagram and cut off the
  heading).
- Review of Phase R (176): an iso diagram fills the room between heading and captions (labels
  go beside the blocks when those above and below would take a wide frame's height; in 9:16 an
  `at` grid is drawn as written or slanted, whichever is largest); `focus` fades out the labels
  its view would cut and brings them back, and its `padding` is a share of the view's shorter
  side (it zooms in 9:16 too); a flat connector tilts up to a raised block; the floor comes in
  with the blocks that are built and follows them in whole cells without a ragged edge; puddle
  ripples stay inside their puddle. The example drops its "App servers" caption and is drawn a
  third larger.
- Follow-ups (177): pipes tilt up to raised blocks too (dots and packets ride on them); the label
  of a block a `raise` lifts keeps off its tilted connectors (the example lints clean in 16:9 and
  9:16; `iso_labels` judges a label's distance at the diagram's own scale under a `focus`); in
  9:16 on an iso place a shot never cuts a character in half at the frame's edge (whole in, or
  out), centres the figures when the tightest zoom leaves the view taller than needed, and the
  wide view keeps in view the spots the scene's walks go to. 16:9 is unchanged.
- Fix (178): a block built with `grow` no longer shows at full size for a moment before it grows
  (it starts unseen on its first frame, whatever the timing); on an iso place an object revealed,
  hidden, opened or switched no longer shows its final look early in the pictures of what stands
  behind it or of a character behind it, and a hidden object no longer comes back (or a closed
  door's open leaf stays) until the next animation.

### Presentation toolkit (Phase P)

- Actions on a spoken word: any beat action's `at` (and a `lower_third`'s) may be `"@gradient"`,
  `"@gradient#2"`, `"@gradient+0.3s"` or `"@learning rate"`, timed from the TTS word timings
  once there is audio and estimated from the text before; an unknown word is a `vidgen validate`
  error that lists the beat's words like it (156).
- One colour per concept: `terms: {loss: primary, gradient: "#E07A5F", "learning rate": {color:
  tertiary, tex: '\eta'}}` colours those words in every text schu-video-generator writes (titles, bullets, chart
  and diagram labels, callouts, karaoke captions) and their symbols in equations; `terms: false`
  opts a scene out; lint `concept_colors` (157).
- `code_morph`: version A of a listing morphs into version B (kept tokens glide, new lines grow
  in, removed ones fade out; the diff is schu-video-generator's), at a beat or on a word (158).
- `terminal`: commands typed at a prompt and the output you write appearing, beside a code
  listing or after a code scene (`carry`); schu-video-generator runs nothing (159).
- `function_plot`: functions written as maths and parsed safely (no `eval`), a dot tracing a
  curve with its tangent and a live label, shaded areas with their signed value, the `trace`
  action (160); points, vectors (sums, scaling), braces, angle marks, dimension lines, and the
  `number_line` scene type with points, intervals and jumps (161).
- `bar_chart` and `line_chart` take `changes` (values per beat): bars grow and re-sort, lines
  morph and the y axis rescales, a cursor sweeps a line with `trace` (162).
- Lint `said_before_shown` (and `unsaid_reveal`, off by default): the narration and the picture
  checked against each other from the layout dump and the word timings (163).
- The example `examples/gradient-descent` (16:9 and 9:16); the Shorts cookbook covers word
  timing, concept colours, code morphs and the terminal; the review's fixes (164).

### Explainer hosts

- `host:` puts a cartoon character beside the content of any explainer scene (bullets, charts,
  code, diagrams...): the content's area shrinks to make room, the host speaks the narration
  with lip sync, and lint rule `host_overlap` checks it (133).
- Host actions `host_point`, `host_look`, `host_react`, `host_move`, `host_enter`,
  `host_exit`, and `auto_direct` for hosts: point at each newly revealed item, react to a
  chart going up or down (134). Example `examples/host-explainer`.

### Cartoons: acting and directing

- Beat actions: `say`, `look_at`, `turn`, `emote`, `pose`, `react` (78); `walk_to`, `run_to`,
  `enter`, `exit`, `gesture`, `jump` (79, 108); `keyframes` and `move_along` (81);
  `pick_up` / `hold` / `put_down` / `give` / `throw` (93); `sit_on`, `stand_up`, `lean_on` (94);
  `get_in` / `ride_to` / `get_out` (118); `effect` symbols (107); `knock`, `pour`, `let_go`,
  `switch_on` / `switch_off`, `open` / `close` (103–128).
- Animation principles built in: anticipation, squash and stretch, overshoot, follow-through
  on a damped spring (`cartoon_motion`; 80, 82). Motion effects such as dust, speed lines and
  impact stars (108).
- `auto_direct`: looks, reactions, gestures, close-ups and effect symbols, planned so that
  lint stays clean; `vidgen direct --print` writes them out as YAML (89, 90, 95, 107).
- Overlapping speech and interruptions (100); voice sounds such as `[laugh]` (99).
- Cartoon lint rules: `off_stage`, `character_overlap`, `bubble_overlap`, `facing_away`,
  `hidden_speaker`, `mouth_without_voice`, `walk_overlap`, `talked_over`, `prop_overlap`,
  `look_alike` (84, 100, 115, 116a). Storyboards include mid-action stills (83).

### Screenplays, cards and transitions

- `vidgen screenplay FILE.md` (also an MCP tool) turns a screenplay into a stage project, with
  looks and voices chosen to suit each character (`FEN (she): ...`) (91, 102 follow-up, 115).
- The `card` scene type for title cards, "Later that day…" cards and end cards; `iris_in` and
  `iris_out` transitions (112).
- Guide topic `cartoons` in `AGENTS.md` / `vidgen guide` (85).

### Weather, light and mood

- `light: day | morning | sunset | night | indoor` and fades between them; soft shadows (97).
- Wind that sways trees and makes hair and scarves trail (98, 104); props that blow away (104).
- Particles: rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks (76, 104).
  Rain lands on the ground, with shelter and puddles (105).
- Snow that settles, and fog (126); lightning with thunder, rainbows, a sun and moon that move
  with the light (127).

### Sound and music

- Foley tied to actions (footsteps, whooshes, pops, boings, thuds, door creaks, splashes) and
  music stings (86, 128). New generated sounds include `bell`, `engine`, `brakes`, `phone`,
  `thunder`, `beep`, `creak`, `knock`, `splash`.
- Ambience beds: rain, fire, birdsong, city, room tone, crickets (105, 121, 128, 169).
- New music beds: `cartoon` and `lullaby` (129).
- Five documentary music beds with a soft kick and a synth bass (179): `discovery` (D minor,
  104 BPM, a steady approach that builds), `breakthrough` (112 BPM, tension in C minor, then a
  lift to E-flat major 25.7 s into the loop: a reveal), `enigma` (B minor, 96 BPM, mysterious),
  `momentum` (G minor, 120 BPM, the most energetic), `lab` (F minor, 108 BPM, modern tech). Used
  like the other beds (`music: discovery`); bass-heavy, so lighter on phone and laptop speakers.
  The five older beds sound exactly as before. `vidgen validate` suggests the nearest bed name
  for a misspelt `music` source.
- Four energetic electronic music beds (181): `ascent` (A minor, 136 BPM, uplifting trance that
  builds and lifts 28.2 s into the loop), `horizon` (132 BPM, anthemic trance with a gated
  supersaw, D minor lifting to F major 29.1 s in), `beacon` (E minor, 120 BPM, a cosmic
  pulsar-like ticking beacon), `neon` (F-sharp minor, 116 BPM, synthwave night drive). Used like
  the other beds (`music: neon`); bass-heavy, so lighter on phone and laptop speakers. The ten
  older beds sound exactly as before.
- Composed music: `music: {compose: MOOD}` writes an original piece as notes and plays it with
  real instruments (the optional `music` extra, symusic 0.5.9, and the GeneralUser GS SoundFont,
  downloaded once and checked: `vidgen soundfont fetch`, or `soundfont: PATH` for your own) (145,
  146). Eight moods: `calm`, `focused`, `curious`, `upbeat` for explainers, `playful`, `sleepy`,
  `tense`, `triumphant` for cartoons, with instruments per part and a seed (147). The piece is
  composed for the video's timings: scene changes on bar lines, a mood per scene, swells on
  reveals, pauses before punchlines, a closing cadence, and stings played by the music's own
  instruments (148). Without the extra the mood's built-in bed plays and `vidgen validate` warns;
  drafts and animatics play it too; `vidgen music preview` (MCP `music_preview`) writes a piece
  as WAV and MIDI (147, 149). `examples/host-explainer` and `examples/cartoon-rain-check` use it.
- A Listen page, [`docs/music/README.md`](docs/music/README.md), made by `vidgen music page`:
  a 15 s MP3 clip and a spectrogram of every bed (from the lift for `breakthrough`, `ascent` and
  `horizon`), clips that play all 36 sound effects and the six ambience beds, and two composed
  moods; all made by schu-video-generator itself and byte-identical when made again. The README leads with
  the music and sound synthesis and links it (183).
- Score files: music written in YAML (key, tempo, time signature, named sections, a progression
  in Roman numerals or chord names, tracks of step patterns such as `"x... x..."`, `"1358 5315"`
  with `accent: "3+3+2"` or `"E5 - - . G5"`), played by schu-video-generator's own instruments as a seamless
  loop or a one-shot at −28 LUFS; every mistake reported at once with did-you-mean. `vidgen music
  render SCORE.yaml --out FILE.wav` (184).
- Score files gain an instrument library of 26 (gated snare, analog bass, square pluck, soft lead,
  pulsar tick, radio static, saw and glass pads, pizzicato, music box...) and effects on any
  track or section: filter sweeps, side-chain ducking to the kick, trance gates, echo, reverb,
  stereo spread and width, volume curves. `vidgen music patches` describes them all; `vidgen
  music render` writes MP3 too and warns about notes it cannot play (185).
- Templates: every built-in bed as a commented score file to start from, a close re-creation
  measured against the bed (tempo, key, loudness over time, spectrum): `vidgen music template
  momentum --out my_theme.yaml`. Score files gain voicing notes `v1`–`v9`, notes played together
  (`v2+v3+v4`), the bass an octave up (`x'`), a pad `swell` and a `snap`; a pad's sub now plays
  the written bass note and sits in the centre (186).
- `vidgen music check my_theme.yaml` (or any audio file): how a piece will sit under narration,
  in words — loudness and steadiness, peaks and clipping, the tempo heard, the loop's seam, how
  much sits in the voice's range, bass weight, harsh highs, the key, whether the lift lifts and
  the build builds — with advice that names the tracks and score keys to change, a spectrogram
  with the sections marked and a 20 s demo under a narration sample with schu-video-generator's ducking;
  `--compare` puts two versions side by side (187).
- Project pieces: a score file in `assets/music/my_theme.yaml` plays like a bed with `music:
  my_theme` (or `source: assets/music/my_theme.yaml`), rendered when the video is joined and
  cached; `vidgen list-music`, `vidgen validate` and `vidgen lint` (rule `music_check`) include
  them; MCP tools `music_template`, `music_patches`, `music_render`, `music_check`; the author
  guide's "Making music" recipe (188).
- An example made with it: `examples/gps-time-of-flight`, a narrated GPS explainer whose music,
  *Time of Flight*, an AI author made from the `momentum` template in nine checked steps (the
  README has the log and the check report); `docs/COOKBOOK-MUSIC.md`, music craft notes (room for
  the voice, builds and lifts, loops, check and compare, five genre sketches, common mistakes);
  the Listen page gains a "Made with the score format" row. The recipe now says how to change a
  template's key and which section names the check judges; `vidgen music template` suggests the
  check as the next step (189).
- Two new built-in beds written in the score format: `tidewater` (E minor, 108 BPM, steady and
  hopeful, a bell melody in its lift) and `skyline` (D minor, 128 BPM, a pumping supersaw build
  and lift). `music: tidewater` plays them like any bed; `vidgen music template tidewater` gives
  the very score the bed plays. 16 beds in all, on the Listen page too (190).
- Review of the score format (191): a note can be held across a section's change (steps that
  start with `-`); `duck: {follow: true}` dips by each hit's level; a cue can start at a section
  of a piece or score bed (`section: lift`, so the lift begins with a chosen scene); `vidgen music
  render` / `check` (and the MCP tools) take a project piece's or a bed's name; the check finds a
  part that clashes with one chord, notes a lift that stays under an earlier section, no longer
  suggests a riser for a lift and says how far a quiet riser is under a build; lint's
  `music_check` reports only on the part of a piece the video plays; filter sweeps render in
  parallel (the same samples). Every existing score, bed and mix sounds exactly as before.
- *Time of Flight* becomes the 17th built-in bed, `time_of_flight` (B minor, 108 BPM, intro /
  build / lift / settle: science and tech explainers, discovery and measurement stories, maps and
  navigation), exactly as it sounded; `vidgen music template time_of_flight` gives its score. The
  GPS example plays the bed and no longer keeps its own copy (a project piece named
  `time_of_flight` would now clash with the bed: rename it, or play it by its path) (192).

### Narration and pictures

- OpenRouter narration: `voice: {provider: openrouter, ...}`. One provider per video, with
  price estimates in the dry run (62, 63).
- Free local narration with Kokoro: `voice: {provider: kokoro}`, installed with the `kokoro`
  extra on Python 3.10–3.12 (65).
- OpenRouter pictures, `imagegen: {provider: openrouter}` (61); vector pictures with
  `generate: {format: svg}` and `.svg` files in `image` scenes, drawn, recoloured and cleaned up
  (61b). A clear message when the account's privacy settings block a model (Zero Data
  Retention).
- Lines with feeling: `emotion:` on a beat or a voice (13 emotions such as `excited`, `sad`,
  `whisper`, `doubtful`, or your own speed / pitch / gain / pauses). Kokoro changes speed,
  pitch, loudness and pauses (135); ElevenLabs v3 gets audio tags, other ElevenLabs models voice
  settings, OpenRouter models instructions or the same audio changes (136). Kokoro voice blends
  with weights: `af_heart+af_bella:0.6` (135).
- Dubbing: `dub: {LANG: VOICE}` on voices, automatic Kokoro voices of the same kind for a
  translated variant, lip sync and timings from each language's audio, and `--all-languages`
  on `tts`, `render` and `lint` (MCP `render` / `lint`) (143). `examples/cartoon-music-box`
  has a Brazilian Portuguese variant.
- Built-in pronunciation lists per TTS engine and language (`kokoro-en-us`, `kokoro-en-gb`), used
  under every project's own entries; `pronunciation_defaults: false` turns them off; `vidgen
  list-pronunciation [PROJECT] [--json]` shows them and what they change; validate, `tts` and
  readback say when a built-in entry is involved (165).
- `vidgen readback` flags single words the recogniser was unsure of or heard after an odd pause,
  with the time in the video and a suggested fix; `vidgen lint --readback` reports them as rule
  `unclear_speech` (141).

### Rendering and tooling

- `--jobs auto` on `render`, `storyboard`, `lint`, `thumbnail`, `slides`, `gallery` and MCP
  uses as many jobs as the available memory allows, at 1.5 GB per job (117).
- Faster cartoon renders: static layers stay in Manim's static image, and part drawings are
  cached (87).
- Works with Manim 0.22 (64).
- The scene gallery (`docs/gallery`, `vidgen gallery`) shows animated previews: each index cell
  plays the 16:9 and 9:16 GIFs (the still for viewers who ask for reduced motion); every GIF
  skips the empty opening, opens on its held last beat and stays under 150 KB. "2D cartoons" and
  "Isometric cartoons" end with eight showcases, small scenes written for the gallery with their
  whole YAML (a dialogue in a room, walks in depth, rain at nightfall, a platform jump; an iso
  village, a cut-away room, a lamp lit at night, settling snow); `--types` takes their names.
  The README shows four gallery GIFs near the top (182).
- `vidgen render --draft`: a quick render at about 8 fps and 240 px without decoration (idle
  motion, wind, shadows, particles, light grade), every timing kept, in its own `build/draft`
  folder and `_draft.mp4` (137).
- `vidgen animatic` (also an MCP tool): the storyboard's stills timed to the narration with the
  video's audio and captions, joined by ffmpeg in seconds (138).
- Examples: `examples/cartoon`, `cartoon_series`, `screenplay`, `svg_character`,
  `cartoon-music-box`, `cartoon-rain-check`, `cartoon-muffin-mystery`, `cartoon-rainbow-ride`,
  `host-explainer`, `platform-story`, `gradient-descent`.
- Reviews 63, 88, 102, 116, 130, 144, 149, 155 and 164, and full test suite runs (131, 144), fixed what
  they found (4042 tests passed in Step 144's full run).

### Known gaps

- No human has listened to the generated sounds and beds; the composed music was chosen by a
  listening test of the renderer, but the moods and fitted pieces await one. Windows and macOS were not run
  here: see `docs/WINDOWS-CHECK.md`. The open items are listed under "Backlog" in
  `tasklist.md`.
