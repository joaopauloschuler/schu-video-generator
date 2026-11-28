<!-- topic: orbits (also: orbit, orbital, orbital-mechanics, kepler, hohmann, planets, space, spaceflight) -->
## Orbits: orbital mechanics videos

One scene type, `orbit`, draws bodies on their orbits and **computes** everything it shows from
two-body Kepler orbits (or n-body integration): positions in correct timing, speeds, Δv, transfer
times, phase angles, Lagrange points, the planets on a date. Worked numbers go in a `calculation`
(`from_scene: <orbit scene>.dv1`); Kepler's third law is a `plot` (`kepler_planets`). Every param:
`docs/CONFIG.md`; the craft in full: `docs/COOKBOOK-ORBITS.md` in the schu-video-generator
repository; a whole example: `examples/mars-transfer` ("How to get to Mars": why not straight,
the Hohmann transfer, the transfer time worked out, the departure burn from low Earth orbit, the
Earth and Mars on a real date; 16:9 and 9:16).

For a three.js space scene of the same orbits (worlds, craft, sky, a moving camera) with no code,
see the `space` scene: `vidgen guide space-scenes`.

**Choosing a view.** The planets for a year or a comet's ellipse → bodies with `span` / `orbits`;
Kepler's laws → `geometry`, `sectors`, `velocity`; why orbits are falling → `cannonball`; a
manoeuvre → `burns` or `transfer` (hohmann, bielliptic, phasing); a gravity assist → `flyby` (the
planet's frame plus the Sun-frame vector diagram); Lagrange points and Trojans → `system` with
`view: rotating` (or `corotate` on a word); resonances → `resonance`; tides → `tides` (a
schematic); the sky on a day → `date` with `event`; sizes → `sizes`. One idea per scene: the
orbit, then the manoeuvre, then the number in a `calculation`.

**Scale honesty.** Distances are drawn to scale; bodies too small to see are enlarged and the
panel says "sizes not to scale" — say the same ("the distances are to scale, the sizes are
not"). For the whole Solar System use `inset: true` (the inner planets to scale in a box) or
`radial: log` (distances compressed, labelled so; overlays that measure lengths are refused
there). `sizes` shows radii to one scale (distances are not). Tides are a schematic.

**Panels.** The side panel is compact (time, speed-up and the few values the scene is about, at a
readable size); `panel: [time, total_dv, phase]` names the rows, `panel: full` shows every row
including the diagnostics (ΔE/E, ΔL/L, the Jacobi drift), `energy: true` adds ΔE/E. The time
readout is always true: the clock runs at one speed-up, `burn` / `flyby` / `pause` / `coast`
change it on words and the panel shows each stretch's own speed-up.

**Presets and units.** Body presets: `sun`, `mercury` … `neptune`, `pluto`, `moon`, `io` …
`callisto`; orbit presets add `iss`, `geo`, `halley` (illustrative). The planets use JPL's Table 1
(J2000 elements, rates per century). Values carry units as text (`"1.5 AU"`, `"7.8 km/s"`, `"92
min"`), angles are degrees; elements next to a preset override it.

**Manoeuvres.** Burns are impulsive (`prograde`, `retrograde`, `radial`, `normal`… with a speed),
at a time or the next `periapsis` / `apoapsis`. A `transfer` needs circular, coplanar orbits:
write `e: 0, i: 0, raan: 0, argp: 0` on the presets and say "circular, coplanar orbits (an
approximation)" in a caption. Δv around the Sun is not the burn from low Earth orbit: that one is
√(v∞² + v_esc²) − v_circ (the Oberth effect; work it out in a `calculation`). A periapsis inside
a body or its atmosphere is refused.

**Three bodies.** `system: earth_moon | sun_earth | sun_jupiter` (the circular restricted
problem) or `figure_eight`; `lagrange`, `zero_velocity`, bodies `near: L4` with `shift`; RK45 by
default (leapfrog's fixed step can blow up at a close pass). Say "in the rotating frame" when the
view turns.

**Dates.** `date: 2026-10-28` (1800–2050, refused outside) places the planets from JPL's
approximate elements; `event: {kind: opposition, of: Mars}` finds the next one (within hours of
published dates). A launch window from a date is approximate (the elements and the circular
transfer are approximations): say "around early December 2026", not a day.

**Pacing.** A planet needs a few seconds to show its motion: 2–4 beats per orbit scene, an action
every few seconds (`burn` on "burn", `highlight: phase` on the angle, `sweep`, `launch`,
`reveal: "foci:Comet"`); say a number once, as the panel writes it, with "about" when rounded.

**Lint.** `orbit_period`, `orbit_speed`, `orbit_dv`, `orbit_transfer`, `orbit_distance`,
`orbit_date`, `orbit_scale`, `orbit_conserved`, `orbit_crash` check the narration and the screens
against the scene's model; `calc_numbers`, `calc_units`, `calc_sigfigs` check the calculations.
Run `vidgen lint` in 16:9 and 9:16.

```yaml
- id: hohmann
  type: orbit
  params:
    title: "The Hohmann transfer"
    bodies:
      - {preset: earth, e: 0, i: 0, raan: 0, argp: 0, trail: false}
      - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 95, trail: false}
      - {name: Ship, alongside: Earth, trail: 0.15}
    transfer: {ship: Ship, to: Mars}
    caption: "Circular, coplanar orbits (an approximation)"
  beats:
    - text: "We leave when Mars leads the Earth by forty-four degrees: the launch window."
      actions: [{highlight: phase, at: "@forty-four"}]
    - text: "A prograde burn of two point nine four kilometres per second starts the transfer."
      actions: [{burn: "burn:1", at: "@burn"}]
```

