# Cookbook: orbital mechanics videos

Craft notes for videos about orbits, spaceflight and the Solar System with schu-video-generator's
[`orbit`](CONFIG.md#orbit) scene type (DESIGN §98), worked numbers in a
[`calculation`](CONFIG.md#calculation) and Kepler's third law in a [`plot`](CONFIG.md#plot). The
scene computes everything it draws — positions in correct timing, speeds, Δv, transfer times,
phase angles, Lagrange points, the planets on a date — so the craft is choosing what to show,
being honest about scale and approximations, and saying the numbers the model gives. The author
guide has the short version (`vidgen guide orbits`); every key is in `docs/CONFIG.md`. The worked
example is [`examples/mars-transfer`](../examples/mars-transfer/README.md): "How to get to Mars"
— why a rocket cannot fly straight there, the Hohmann transfer, the transfer time and phase angle
worked out, the departure burn from low Earth orbit and the Earth and Mars on a real date. The
[scene gallery](gallery/README.md#orbital-mechanics) shows the type.

## 1. Choosing what to show

| the viewer should understand | `orbit` params | notes |
|---|---|---|
| planets or moons going round, at their real speeds | `bodies` (presets), `span` or `orbits` | equal video times are equal simulated times |
| Kepler's first and second laws | `geometry`, `sectors`, `velocity` on one body | `reveal` / `sweep` on words |
| why an orbit is falling | `cannonball` | shots classified by energy: 1.414 × v_circ is still an ellipse; only `escape` is parabolic |
| Kepler's third law | a `plot` with `kepler_planets` on log axes and a `power` fit | the exponent comes out 1.500 |
| a burn, an orbit raised, a transfer | `bodies[].burns`, `transfer` (hohmann, bielliptic, phasing) | Δv, times and the phase angle in the panel |
| a Δv budget | a `calculation` with `from_scene: <scene>.dv1` | the formula and the units on screen |
| a gravity assist | `flyby` (`v_inf`, `altitude`, `side`) | the planet's frame plus the Sun-frame vector diagram |
| Lagrange points, Trojans, horseshoes | `system`, `lagrange`, bodies `near: L4`, `view: rotating` or `corotate` | the circular restricted problem |
| resonances, binary stars, the figure-eight | `resonance`, `origin: barycentre`, `system: figure_eight` | |
| tides | `tides` | a schematic, labelled so |
| the sky on a day, the next opposition | `date`, `event` | JPL's approximate elements, 1800–2050 |
| how big the planets are | `sizes` | radii to one scale; distances are not |

One idea per scene: the orbits, then the manoeuvre, then its number in a `calculation`. The
example spends about 30 s on why straight does not work, 45 s on the transfer, 30 s on each
calculation and 45 s on the date.

## 2. Scale honesty

- **Distances are to scale; sizes usually are not.** At the scale of an orbit a planet is far
  smaller than a pixel, so the scene enlarges bodies too small to see and the panel says **"sizes
  not to scale"**. Say it the same way: "the distances are to scale, the sizes are not" —
  `orbit_scale` flags "to scale" said of enlarged bodies.
- **The whole Solar System does not fit at one scale.** `inset: true` keeps a true-scale picture
  and adds the inner planets to scale in a box; `radial: log` compresses distances (labelled
  "distances compressed (log)", rings at round distances, no axes). Lengths and speeds cannot be
  read from a log picture, so overlays that measure them are refused there.
- **Sizes have their own picture.** `sizes` puts radii side by side to one scale ("radii to scale
  (distances are not)").
- **A schematic says so.** The tides scene is not to scale and its panel says it; do not narrate
  its arrows as measurements.
- **Low orbits hide under the planet.** At true scale a 400 km orbit is a hair outside the Earth's
  disc; narrate it as close to the surface rather than pretending the picture shows the altitude.

## 3. Units and numbers

- **Values carry units as text**: `"1.5 AU"`, `"7.8 km/s"`, `"92 min"`, `"5.97e24 kg"`; angles
  are degrees (`nu: 75`) or `"0.9 rad"`. A length without a unit is refused.
- **The panel's units follow the scene**: AU above 0.05 AU, km below; times in min, h, d or yr by
  the span; the speed-up as `× 1.4 million`.
- **Δv around the Sun is not the burn from Earth.** A Hohmann transfer's Δv₁ (2.94 km/s for Earth →
  Mars) is the speed left over after escaping, v∞. From a circular low orbit the burn is
  Δv = √(v∞² + v_esc²) − v_circ — 3.59 km/s from 300 km (v_esc 10.93, v_circ 7.73 km/s): less than
  escape plus v∞, because burning deep in the gravity well, where the rocket is fast, gains more
  energy per km/s (the Oberth effect). Work it out in a `calculation` with `from_scene`.
- **Say numbers as the screen writes them**, rounded with "about": "two point nine four
  kilometres per second", "two hundred and fifty-nine days", "about twenty-six months".

## 4. Approximations to state

Every orbit video simplifies; say how, in a `caption` or a sentence:

| approximation | where | say |
|---|---|---|
| two-body Kepler orbits (other planets ignored) | every `orbit` scene without `dynamics: nbody` | rarely needed; say it for long spans |
| circular, coplanar orbits | `transfer` (it refuses others: give `e: 0, i: 0, raan: 0, argp: 0`) | "Circular, coplanar orbits (an approximation)" |
| impulsive burns | `burns`, `transfer` | "a short burn" |
| patched conics | `flyby` | "in Jupiter's frame…; around the Sun…" |
| the circular restricted three-body problem | `system` | "the Moon's orbit taken as a circle" when it matters |
| JPL's approximate elements (Table 1, 1800–2050) | `date`, `event` | "from JPL's approximate planetary elements"; dates "around", not to the hour |
| a schematic | `tides` | "not to scale" |

Real missions fly elliptical, inclined orbits on trajectories computed numerically; a closing
sentence saying so keeps a simplified video honest.

## 5. Pacing

- **Let the motion play.** A planet needs a few seconds to show it moves: 2–4 beats per orbit
  scene, 10–25 words each. The clock runs at one speed-up from the end of the first beat's
  entrance to the scene's end, so a longer scene shows the same span more slowly.
- **Time the clock to words, not the physics.** `burn: "burn:1"` on "burn" makes the clock run so
  the burn falls on that word (the burn's simulated time does not change); `pause` / `coast` hold
  the picture while you explain the launch window; `flyby` puts the closest approach on a word.
- **Something moves every few seconds**: `highlight: phase` on the angle, `highlight:
  "velocity:Earth"`, `reveal: "foci:Comet"`, `sweep`, `launch`, `highlight: event`.
- **Calculations**: one line per action (`substitute` on the word that names the values, `compute`
  on the result's first word); say the formula in words once ("pi times the square root of a cubed
  over the Sun's G M").
- **9:16**: the panel stands above the picture and the picture takes the width; keep the panel to
  the compact rows (`panel: compact`) and lint the vertical variant too.

## 6. Common mistakes and the rule that catches each

| mistake | rule |
|---|---|
| a period that the orbit does not have ("Mars takes three years" for 1.88 yr) | `orbit_period` |
| a speed that vis-viva does not give at the point named ("forty kilometres per second at aphelion") | `orbit_speed` |
| a burn's or a transfer's Δv said otherwise ("the first burn is 3.2 km/s" for 2.94) | `orbit_dv` |
| a transfer time, phase angle or launch-window interval said otherwise ("180 days", "every 18 months") | `orbit_transfer` |
| a distance, altitude, Lagrange point or size ratio said otherwise ("L2 is 15 million km away") | `orbit_distance` |
| an opposition or conjunction on a date the elements do not give | `orbit_date` |
| "to scale" said of enlarged bodies or a log picture | `orbit_scale` |
| an n-body run whose energy drifts (a too-long leapfrog step) | `orbit_conserved` |
| a periapsis in the atmosphere, a flyby through the air | `orbit_crash` |
| a calculation's result said otherwise, wrong units, too many figures | `calc_numbers`, `calc_units`, `calc_sigfigs` |
| a word said before the thing it names appears | `said_before_shown` |

Run `vidgen lint` on the preview in 16:9 and 9:16 before the final render; the orbit rules read the
config and the narration, not the stills, so they are quick.

## 7. The pattern

```yaml
- id: hohmann
  type: orbit
  params:
    title: "The Hohmann transfer"
    central: sun
    bodies:
      - {preset: earth, e: 0, i: 0, raan: 0, argp: 0, trail: false}
      - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 95, trail: false}
      - {name: Ship, alongside: Earth, trail: 0.15}
    transfer: {ship: Ship, to: Mars}
    caption: "Circular, coplanar orbits (an approximation)"
  beats:
    - text: "We leave when Mars leads the Earth by forty-four degrees: the launch window."
      actions: [{highlight: phase, at: "@forty-four"}]
    - text: "Then a prograde burn of two point nine four kilometres per second stretches our orbit into an ellipse."
      actions: [{burn: "burn:1", at: "@burn"}]
    - text: "Two hundred and fifty-nine days later a second burn of two point six five kilometres per second matches the speed of Mars."
      actions: [{burn: "burn:2", at: "@second"}]
- id: leaving
  type: calculation
  params:
    title: "Leaving the Earth: the Oberth effect"
    results_in_table: false
    symbols:
      - {name: v_inf, from_scene: hohmann.dv1, meaning: "excess speed needed (Δv₁)", tex: "v_{\\infty}"}
      - {name: GM_earth, constant: GM_earth}
      - {name: R_earth, constant: R_earth}
      - {name: h, value: "300 km", exact: true, meaning: "height of a low orbit", source: "chosen"}
    calculations:
      - {name: v_c, expr: "sqrt(GM_earth/(R_earth + h))", unit: km/s, meaning: "circular speed there", symbol: "v_{\\mathrm{circ}}"}
      - {name: v_esc, expr: "sqrt(2*GM_earth/(R_earth + h))", unit: km/s, meaning: "speed to escape from there", symbol: "v_{\\mathrm{esc}}"}
      - {name: dv_LEO, expr: "sqrt(v_inf^2 + v_esc^2) - v_c", unit: km/s, sig: 3, meaning: "Δv for the departure", symbol: "\\Delta v"}
  beats:
    - text: "From low Earth orbit the burn is about three point six kilometres per second."
```

## 8. Orbits in a three.js `web` scene

For films of space shots written in `video.yaml` alone (a `space` scene: worlds, craft on these
orbits, a sky, camera moves; a recipe per shot and what each costs), see
[COOKBOOK-SPACE.md](COOKBOOK-SPACE.md). This section is for pages written in code.

A `web` scene with `orbit_data:` gets the same model as `ctx.orbits` (Step 367; keys and the
accessor in [CONFIG.md](CONFIG.md#web), "Orbit data"): every body's position and velocity for
every frame, in metres from the central body, in the mean ecliptic and equinox of J2000 (z up;
`yUp` turns it into three.js's y-up), each planet's and moon's rotation (period, tilt, pole,
prime meridian), each orbit as a polyline and a ship's burns. The numbers are the ones the flat
`orbit` scene draws, to the last bit; the page only chooses how to show them.

**No code at all: the `space` scene** (Step 376; [CONFIG.md](CONFIG.md#space), `vidgen guide
space-scenes`). Its `orbits:` takes the same words, and `bodies`, `craft` and `camera` name the
data's bodies: `craft: [{name: Ship, kind: ship}]` flies the transfer's `Ship` with its burns,
`camera: {move: follow, subject: Ship, view: chase}` goes with it, and a date puts the Sun where
it really is that day. `scale: {mode: enlarged, enlarge: 50}` is said on screen in this
cookbook's words; `vidgen lint` (`orbit_scale`) catches narration that calls it "to scale", and
`space_scene` a globe that turns too fast under the speed-up. Write the bullets below by hand only
for what the YAML cannot say (`script:`, or `vidgen space-page` to take the page over).

- **True by default.** The positions are true; a page that enlarges the bodies or compresses the
  distances says so on screen, as the flat scene does ("sizes not to scale").
- **Draw them with `vidgen/space-scale`** (Step 368; CONFIG `web`, "Astronomical scales"):
  `new SpaceView(ctx, {renderer, scene, camera, mode})` places every body camera-relative in
  double precision each frame and draws in depth slices, so a ship 400 km above the Earth and the
  Moon behind it neither jitter nor fight. Modes: `true`; `enlarged` (radii times a stated factor);
  `log` (the flat scene's `radial: log`, the same mapping and r0). `space.note().text` is the
  honest caption in the flat scene's words.
- **The bodies themselves** (Step 371; CONFIG `web`, "Planets, moons and rings"):
  `planet(renderer, "Earth", {space})` from `vidgen/space-bodies` draws the body of the orbit
  data called Earth as an Earth-like world at its true size, pole and turning, lit from where the
  data's Sun is; call `body.update(t)` after `space.update(t, view)`. Under a large speed-up read
  `body.problems()` and choose `spin: "locked"` or a stated rate.
- **The Sun and the light** (Step 372; CONFIG `web`, "Suns and light"): `star(renderer, "Sun",
  {space})` from `vidgen/space-light` is the data's Sun at its true size and place (from the
  Earth 4.5 px in radius through a 40° lens at 720p: a brilliant point with its glare), and
  `spaceLight({scene, camera, sun, bodies, sky})` lights every body from where the Sun is, with
  planet-shine, eclipses on request and `falloff: 2` for the true light with distance; call
  `light.update(t)` after `space.update` and the bodies' `update`.
- **A spacecraft on its orbit** (Step 374; CONFIG `web`, "Spacecraft"): a body of `orbit_data`
  (a `transfer`'s ship, a body with `burns`) is flown by `craft("ship").fly(space, {body:
  "Ship", attitude: "prograde"})` from `vidgen/space-craft`; `ship.update(t)` after
  `space.update` puts the nose along the velocity and, round each burn of the data, along the
  burn's change of velocity with the engines on for `burn.seconds` (2) centred on it: the model's
  burn is an instant, the film's a short stretch (a convention). `craft.burns` lists the
  stretches in scene seconds for a camera cut or a label. From far away give `marker: 3` so the
  ship stays a visible point on its path (a stated choice), and draw the path with
  `space.path("Ship")`; for a close-up give `orbit_data` more `path_samples`, since the line is
  a polyline and the craft flies the true curve.
- **The camera on an orbit** (Step 375; CONFIG `web`, "Camera moves for space scenes"):
  `const cam = spaceCamera({space, camera})` from `vidgen/space-camera`, then each frame
  `cam.apply(t, cam.follow(t, {subject: ship, view: "chase"}))` goes with a flown craft (forward
  is its velocity, up is away from the world it goes round), `cam.pass(t, {subject: ship, over:
  [0, 4]})` lets it pass the camera, `cam.reveal(t, {behind: "Earth", of: "Moon", at: 4})` times
  a moonrise over the Earth's limb, and `cam.zoom(t, {stops: [{subject: "Earth", distance:
  {radii: 4}}, {subject: "Earth", distance: 2.4e9, hold: 1}, {subject: "Sun", distance:
  3.2e12}]})` backs away by powers of ten from a world to its moon's orbit to the planets (draw
  the orbits with `space.path(name, {kind: "conic"})`: at true scale the bodies are points).
- **A comet on its orbit** (Step 373; CONFIG `web`, "Phenomena"): with `orbit_data` holding
  `{preset: halley}`, `comet(renderer, {space, body: "Halley"})` from `vidgen/space-phenomena`
  stands where the data puts the comet; `comet.update(t)` points its ion tail away from the
  data's Sun, bends its dust tail behind its motion and grows both as (1 AU / distance)². One
  unit of the comet is `unit` metres (2e9 by default): head and tails are drawn at a stated
  size, not to scale; say so in the film's notes.
- **The real sky behind them** (Step 370; CONFIG `web`, "The sky of a space scene"):
  `spaceSky(renderer, {stars: "real"})` from `vidgen/space-sky` is in the same frame as
  `ctx.orbits`, so a dated scene has the right stars behind its planets (the Earth in June stands
  in front of Sagittarius seen from the Sun's side). The shipped star file is a hand-written list of
  221 well-known bright stars at approximate places (written from memory); fainter stars are
  seeded. The Bright Star Catalogue is not shipped (no formal licence): download it yourself and
  convert it with `tools/make_star_catalogue.py` for every naked-eye star.
- **Which plane.** In 3D an orbit's inclination needs its reference plane: the planets and the
  Moon's preset are measured from the ecliptic, `iss`, `geo` and the Galilean moons from their
  planet's equator (an ISS-like orbit is 51.6° to the Earth's equator, up to 75° to the
  ecliptic). `planes: {Ship: ecliptic}` changes a body's. The flat scene draws each orbit seen
  from above its own reference plane.
- **What stays in a plane.** A `flyby` (the planet's frame), the restricted three-body `system`,
  the figure-eight and the cannonball are planar models; a `transfer` is between orbits in one
  plane (any plane: since Step 367 the launch window is measured in that plane).
- **Say the approximations.** `ctx.orbits.approximations` lists them in words (two-body orbits,
  JPL's approximate elements on the date, impulsive burns, patched conics).
