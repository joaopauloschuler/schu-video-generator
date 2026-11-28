<!-- topic: web (also: html, css, javascript, js, canvas, web-scenes, web-scene, web-page, page, script) -->
## Web scenes: a scene you write in HTML, CSS and JavaScript

A `web` scene is a page you write. vidgen opens it in headless Chromium, takes a screenshot per
frame and shows it like any other scene: under the captions and overlays, with transitions,
narration and lint. JavaScript in your project runs as written, as the Python in `extensions/`
does. A whole example to copy from: `examples/web` (a CSS page revealed on beats, a canvas drawing,
a three.js planet; 16:9 and 9:16). Every param and detail: `docs/CONFIG.md`, section `web`.

**When to use it.** A built-in scene type is still the first choice when one fits (`vidgen guide
scenes`): it is laid out, revealed, timed and linted for you, and it is much faster to render.
Write a `web` scene for a picture no built-in draws: a bespoke layout, an animation in CSS or SVG,
a canvas drawing, a three.js scene of your own, an interactive-looking diagram, a styled mock-up
of an app. Simple shapes and stand-ins seen by a moving camera: `3d` (no code). Footage or a
screen recording: `video_clip`. A scene type you will reuse with new params in many scenes, or
one that must move vidgen's own text and targets: a Python extension (`docs/EXTENDING.md`).

**Two forms.** Give exactly one:

- `page: extensions/name.html`: any HTML page of the project (its CSS, pictures, fonts and
  modules load by relative links). Hooks go on `window.vidgen = {load(ctx) {…}, frame(t, ctx) {…}}`.
- `script: extensions/name.js`: a JavaScript module; vidgen puts it on a bare page with one
  transparent `<canvas>` the size of the page (`ctx.canvas`). Hooks are exports: `export function
  frame(t, ctx) {…}`.

Both hooks are optional and may be `async`: `load(ctx)` runs once before frame 0 (time stands at
0 there), `frame(t, ctx)` before each screenshot, `t` in seconds from the scene's start. A page
that only uses CSS needs no JavaScript at all.

```yaml
- id: hello
  type: web
  params: {page: extensions/hello.html, region: body, title: "Three steps"}
  beats:
    - {id: h1, text: "First, we read the data."}
    - {id: h2, text: "Then we clean it."}
    - {id: h3, text: "Last, we draw the chart."}
- id: orbit
  type: web
  params: {script: extensions/orbit.js, data: {moons: 3}}
  beats: [{text: "Three moons go round their planet."}]
```

```html
<style>  /* extensions/hello.html: every colour, font and size from the theme; each step on its beat */
  body { margin: 0; height: 100vh; display: flex; gap: 3vw; align-items: center; justify-content: center;
         font-family: var(--vidgen-font-body); color: var(--vidgen-text); }   /* no background: the video's shows */
  .step { padding: 4vh 3vw; border-radius: 2vh; background: var(--vidgen-surface);
          font-size: var(--vidgen-size-body); opacity: 0; transform: translateY(4vh);
          transition: opacity 0.5s, transform 0.5s; }
  .step b { color: var(--vidgen-primary); }
  body[data-beat="h1"] .s1, body[data-beat="h2"] :is(.s1, .s2), body[data-beat="h3"] .step { opacity: 1; transform: none; }
  [data-orientation="portrait"] body { flex-direction: column; }
</style>
<div class="step s1" data-vidgen-id="read"><b>1</b> Read</div>
<div class="step s2" data-vidgen-id="clean"><b>2</b> Clean</div>
<div class="step s3" data-vidgen-id="draw"><b>3</b> Draw</div>
```

```js
// extensions/orbit.js: draws the whole picture from t alone, so any frame can be drawn on its own
const label = (ctx) => ({text: `${ctx.data.moons} moons`, size: ctx.theme.sizes.body, x: ctx.width * 0.08, y: ctx.height * 0.1,
                         font: `700 ${ctx.theme.sizes.body}px ${ctx.theme.fonts.heading}`});
export function frame(t, ctx) {
  const c = ctx.canvas.getContext("2d");
  const {width: w, height: h} = ctx, r = Math.min(w, h) * 0.32;
  c.clearRect(0, 0, w, h);                     // transparent: the video's background shows
  c.fillStyle = ctx.theme.colors.primary;
  c.beginPath(); c.arc(w / 2, h / 2, r * 0.3, 0, 2 * Math.PI); c.fill();
  for (let i = 0; i < ctx.data.moons; i++) {
    const a = t * (1.2 - i * 0.3) + i * 2;     // radians: each moon at its own speed
    c.fillStyle = ctx.theme.palette[(i + 1) % ctx.theme.palette.length];
    c.beginPath(); c.arc(w / 2 + Math.cos(a) * r * (0.55 + i * 0.22), h / 2 + Math.sin(a) * r * (0.55 + i * 0.22), r * 0.07, 0, 2 * Math.PI); c.fill();
  }
  const l = label(ctx);
  c.font = l.font; c.fillStyle = ctx.theme.colors.text; c.textBaseline = "top";
  c.fillText(l.text, l.x, l.y);
}
```

**Time belongs to vidgen.** Write ordinary web code: CSS animations and transitions, the Web
Animations API (`element.animate`), SVG `<animate>`, `requestAnimationFrame` loops, `setTimeout`
and `setInterval`, `Date.now()`, `performance.now()` and a `<video>` all follow the video's time,
frame by frame, however slow the screenshots are; `Math.random` (and `crypto.getRandomValues`) is
seeded from the scene id, so every render gives the same frames. A loop that adds a little each
`requestAnimationFrame` works; a picture computed from `t` alone is simpler to get right. Not
controlled (avoid them, or drive them from `frame`): `<audio>` (the scene has no sound of its
own), animated GIF / WebP, web workers, iframes, `XMLHttpRequest` and dynamic `import()` (not
waited for: load data with `await fetch("data.json")` in `load`; a relative path is relative to
the page, or to the script of a `script:`), and `ResizeObserver` /
`IntersectionObserver` callbacks. Ordinary timer, `requestAnimationFrame`, CSS and Web Animations
code was measured frame-exact. anime.js, Motion, D3, Chart.js and lottie-web ship with vidgen and
were run under the clock (the table "Animation and chart libraries" below says how to drive
each); any other library must be a file in the project (below: no internet). Because
`performance.now()` is the video's clock, it stands still inside a frame: you cannot time your
own code with it. `vidgen render` tells you instead (below, "Render cost").

**What the page is given**, `ctx`:

| field | value |
|---|---|
| `width`, `height` | the page's size in CSS pixels (the whole frame, or the body region with `region: body`): the frame's own pixels, or with `design_width` the design window's ("Porting a page built in fixed pixels" below) |
| `aspect`, `orientation` | the video's shape: `"16:9"`, `"9:16"`, `"1:1"`…; `landscape`, `portrait`, `square` |
| `fps`, `frames`, `duration` | frame rate, frames drawn, their length in seconds (the beats, the 0.5 s fade-out) |
| `canvas` | the bare page's canvas (`script:`), else `null` |
| `theme` | `colors` (name → hex: `text`, `dim`, `primary`, `secondary`, `tertiary`, `accent`, `highlight`, `surface`…), `background`, `palette` (list), `fonts` (`heading`, `body`, `mono`… → family), `font_files` (the files in the project's `fonts/` folder: `[{family, weight, style, url}]`), `sizes` (`title`, `heading`, `body`, `caption`, `small` → CSS px for this frame) |
| `data` | the scene's `data:` (`{}` without one) |
| `beats` | `[{id, index, start, end, text, words: [{text, start, end}]}]`, seconds from the scene's start (`[]` without narration) |
| `scene`, `frame`, `region` | the scene id, the video frame's `{width, height}`, `bleed` or `body` |
| `music` | with `music_data:` only: the video's music ("Pictures that follow the music" below) |
| `orbits` | with `orbit_data:` only: planets, moons and spacecraft on their orbits ("Orbits on a page" below) |
| `flight` | with `flight_data:` only: planes and space planes through the air ("Flight paths" below) |

**The theme.** vidgen puts CSS variables on `:root` before your own styles: `var(--vidgen-text)`,
`--vidgen-primary` (one per colour), `--vidgen-background`, `--vidgen-palette-0`…,
`--vidgen-font-heading` / `-body` / `-mono` (vidgen's own fonts and the ones in the project's `fonts/` folder, served with no download), and
`--vidgen-size-title` / `-heading` / `-body` / `-caption` / `-small` (px: text that size is as tall
as vidgen's own text of that size). Use them for every colour, font and text size: the page then
matches the other scenes, follows a variant with another theme, and its text is big enough. Size
the rest in `vw` / `vh` (of the page) or `%`, never fixed pixels, in a page you write for the
video: the same page is drawn at the preview size, at 1080p and at 9:16. A page that already
exists and is sized in fixed pixels needs no rewrite: give its window width as `design_width`
("Porting a page built in fixed pixels" below).

**Revealing on the narration.** `<body>` carries `data-beat` (the id of the beat being spoken: give
your beats ids) and `data-beat-index` (from 0), changed exactly when the beat starts, so a CSS
`transition` from it starts on time (`hello.html` above). In JavaScript, use the beats' times;
a word's time reveals a thing on the word that names it:

```js
// in frame(t, ctx): the time "shower" is said in the second beat (else that beat's start)
const beat = ctx.beats[1];
const word = beat ? beat.words.find((w) => w.text.toLowerCase().startsWith("shower")) : undefined;
const at = word ? word.start : beat ? beat.start : 0;
const shown = Math.min(1, Math.max(0, (t - at) / 0.6));   // 0 → 1 over 0.6 s from that word
```

Words are timed like the captions (the voice's own timings once `vidgen tts` ran; before that,
estimated from the word count, so the reveal moves a little when the voice arrives). A
`vidgen-beat` event (`detail: {beat, index, previous, t}`) is also dispatched on each new beat.

**Values from the YAML.** `params: {data: {moons: 3, label: "Moons", color: tertiary}}` is
`ctx.data` (text, numbers, true / false, lists and mappings). A theme colour name in it is not
looked up for you: `ctx.theme.colors[ctx.data.color]`.

**Pictures that follow the music.** `music_data: true` in a scene's `params` gives the page
`ctx.music`: the music the video plays (its `music:`: a score file, a bed or a music file, with
its `start`, `loop`, `volume` and fades) measured at every video frame, and, when it is a score
file, every track's hits and notes. No script of your own, no JSON beside the page: vidgen
measures the music once (from the music it renders for the video anyway, kept in
`build/music`), and an edit to the score draws the scene again.

```yaml
music: tidewater              # a score bed; or your piece (assets/music/*.yaml) or a music file
scenes:
  - id: drop
    type: web
    duration: 13.87
    params: {script: extensions/space.js, music_data: true}   # or {bands: 32, tracks: [kick, melody]}
```

```js
// extensions/space.js
export function frame(t, ctx) {
  const m = ctx.music;                     // every function reads the frame being drawn unless given a song time T
  const glow = 0.3 + 0.7 * m.level();      // 0..1: the whole music's loudness
  const thump = m.pulse("kick", 0.12);     // 1 at each kick, falling over 0.12 s (1.5 on an accent)
  const lows = m.low(), air = m.band(m.bandCount - 1), hit = m.onset();
  const note = m.last("melody");           // the melody's latest note: {time, duration, pitch, dynamic, stroke, slur...}
  const hue = note ? (note.pitch % 12) / 12 : 0;
  // m.hits("kick", T0, T1), m.notes("melody", T0, T1): the events starting in [T0, T1) (song seconds)
}
```

- **Song time.** `ctx.music.t0` is the song time at the scene's start (seconds into the piece:
  the music's `start:`, the scene's place in the video; through a loop's repeats it counts on),
  so `T = t0 + t` and `ctx.music.now()` is the song time of the frame drawn. No `t0` by hand;
  `music_data: {t0: 41.6}` sets one where you want another.
- **Measured per frame** (each 0..1, normalised over the whole video and smoothed with a fast
  rise and a slow fall): `band(i)` (`bandCount` bands, 16 by default, log-spaced from 40 Hz to
  12 kHz, edges in `edges`; `bands()` all of them), `level()`, `low()` (under 150 Hz),
  `onset()` (how much the sound grew since the frame before: drum hits, note starts). The page is
  sent the scene's frames and 5 s on each side; further away it reads the nearest of them.
- **From the score** (`ctx.music.score`: `tempo`, `bar`, `beat`, `sections`, `seconds`; `tracks`:
  name → `{kind, instruments}`): `hits(track?, T0?, T1?)` (drum tracks), `notes(track?, T0?, T1?)`
  (the others), `events(...)`, `last(track, T?)`, `sounding(track, T?)`, `pulse(track, decay?, T?)`,
  `section(T?)`. An event has `time`, `duration`, `end`, `pitch` (MIDI; `pitches` for a chord),
  `instrument`, `dynamic` (dB of its mark, 0 unmarked), `gain` (1.5 an accent, 0.5 soft),
  `strength` (both together), `stroke` (`pizzicato`...), `slur`. A slurred note is a note of its
  own with `slur: true`. `tracks: [kick, melody]` sends only those (a smaller page).
- **Music that is not a score** (a music file, a bed made in code, composed music): the
  measurements only; `ctx.music.score` is `null`. A scene where no music plays reads silence and
  counts video time. A video without music cannot use `music_data` (`vidgen validate` says so).
- The first render measures the music (a few seconds; the score is rendered first if the join
  has not rendered it yet). `vidgen still` shows the frames with the same data.
- A whole worked example: `examples/signal-fire` (an orchestral cue written with dynamics, hairpins
  and slurs, and a three.js page finished with `vidgen/three-finish` that reads ten of its tracks).

**Orbits on a page.** `orbit_data:` in a scene's `params` gives the page `ctx.orbits`: the bodies
of the `orbit` scene (same keys: `central`, `bodies`, `span` / `orbits` / `speedup`, `date`,
`transfer`, `flyby`, `dynamics`, `system`) computed by vidgen for every frame. Do not write orbits
in JavaScript.

```yaml
- id: to_mars
  type: web
  duration: 12
  params:
    script: extensions/to_mars.js
    orbit_data:
      bodies:
        - {preset: earth, e: 0, i: 0, raan: 0, argp: 0}
        - {preset: mars, e: 0, i: 0, raan: 0, argp: 0, nu: 95}
        - {name: Ship, alongside: Earth}
      transfer: {ship: Ship, to: Mars}     # or date: "2026-11-17" and span: "1 yr" for the planets on a day
```

```js
// sketch (parts of a page, not a whole file): what ctx.orbits gives a frame
export function frame(t, ctx) {
  const o = ctx.orbits;                       // metres, m/s, seconds, radians; the frame drawn unless given t
  const p = o.yUp(o.position('Ship'));        // [x, y, z] from the Sun in the ecliptic (z up) -> three.js (y up)
  const v = o.velocity('Ship');               // point the ship along it
  const q = o.quaternion('Earth');            // the Earth's tilt and spin ([x, y, z, w]; o.yUpQuaternion for three.js)
  const burn = o.burns('Ship').find((b) => b.frame === o.index());   // a burn starts on this frame
}
```

- Positions are true (metres from the central body); enlarging bodies or compressing distances is
  your page's choice: say it on screen ("sizes not to scale"). `o.approximations` lists what the
  model simplifies, in words a caption can use.
- Rotation (period, axial tilt, pole, radii, with sources) for the Sun, the planets, the Moon and
  the Galilean moons: `o.bodies.Earth.rotation`; a tidally locked moon faces its planet.
- `o.path(name)` and `o.conic(name)` are polylines relative to the body's parent: the path over
  the scene and the orbit at the start.
- `planes: {Ship: ecliptic}` when a body around a planet is measured from the ecliptic, not the
  planet's equator (the default for `iss`, `geo` and bodies of your own around a planet).

**Astronomical scales: `vidgen/space-scale`.** Do not put metres from the Sun into three.js
yourself (float32 jitters by kilometres there; one near/far range makes a ship and a planet fight).
`SpaceView` places everything camera-relative in double precision each frame and draws in depth
slices; it works with `vidgen/three-finish`.

```js
// sketch (parts of a page, not a whole file): bodies of the orbit data at their true places
import {SpaceView} from "vidgen/space-scale";
const space = new SpaceView(ctx, {renderer, scene, camera});          // mode "true"; or mode: "enlarged", enlarge: 50; or mode: "log"
space.add(new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64), earthMaterial), {body: "Earth"});   // radius 1 -> the Earth's
space.add(shipGroup, {body: "Ship"});                                 // built in metres
space.path("Ship");                                                   // its path as a line
export function frame(t) {
  space.update(t, {from: {body: "Ship", offset: [-200, 0, 50]}, to: "Ship"});   // offsets in metres, ecliptic axes (z north)
  renderer.render(scene, camera);
}
```

- Show `space.note().text` on screen when the mode is not `true` ("sizes not to scale · bodies
  enlarged 50×; distances to scale"; `log`: "distances compressed (log) · sizes not to scale").
- At true scale a whole system is sub-pixel: `space.pixels("Earth")` says how big a body is drawn.
  `space.problems()` warns when an enlarged planet swallows its moon.
- Skies: `vidgen/space-sky` (below), `scene.background`, or a mesh marked `userData.sky = true` (or with
  `frustumCulled = false` and a negative `renderOrder`). With three-finish's depth of
  field focused far away, give `dofFocus` the same focus. Reference: CONFIG.md `web`,
  "Astronomical scales".

**The sky of a space scene: `vidgen/space-sky`.** Do not scatter points for stars yourself (they
shimmer when the camera turns, and equal white dots look like salt). One line gives a sky like a
photograph from space: stars in the real sky's numbers per magnitude with pale colours, the Milky
Way with its bulge and dust, baked once.

```js
// sketch (parts of a page, not a whole file): the sky
import {spaceSky} from "vidgen/space-sky";
const sky = spaceSky(renderer, {seed: 7});            // or {stars: "real"}: the true bright stars, the band where it is
scene.add(sky.object);                                // all round the camera; nothing to update per frame
camera.lookAt(sky.direction("center"));               // the band's centre; "pole", "nebula 1", "Vega" (real sky), {l: 30, b: 5}
```

- Options: `look: "rich" | "sparse"`, `density`, `brightness`, `color`, `milkyWay`, `dust`,
  `center` / `pole` (where the band lies), `nebulae` and `galaxies` (a number, or a list such as
  `[{kind: "emission", at: {l: 20, b: 3}, size: 7}]`; `at` is a world direction or degrees along
  and above the band). `spiralGalaxy({seed, radius})` is a galaxy of particles to fly past.
- With `vidgen/three-finish` give `antialias: "none"`: FXAA turns small stars into crosses. Bloom
  and grain are fine. `scene.environment = sky.environment` lets metal reflect the sky.
- The real sky is in the frame of `ctx.orbits` (with `vidgen/space-scale`): from the Earth in June
  the galactic centre lies opposite the Sun. Its star file is a hand-written list of 221
  well-known bright stars (approximate places, from memory; `sky.info.approximate`), fainter stars
  are seeded. The Bright Star Catalogue is not shipped (no formal licence); downloaded by you, it
  converts with `tools/make_star_catalogue.py`.
- It takes 5–6 s to make at 720p, then about 0.1 s a frame. Look first: `vidgen parts
  'space-sky*'`. Reference: CONFIG.md `web`, "The sky of a space scene".

**Planets, moons and rings: `vidgen/space-bodies`.** Do not texture a sphere yourself (a lit
`MeshStandardMaterial` ball looks like plastic, and three.js has no air, rings or crater
shadows). One line gives a world; every surface is generated from a seed.

```js
// sketch (parts of a page, not a whole file): worlds
import {planet} from "vidgen/space-bodies";
const earth = planet(renderer, "earth");              // or "saturn", "moon", "mars", "europa", ... or {type: "gas", seed: 3}
scene.add(earth.object);                              // radius 1; position and scale it as any object
earth.update(t, {sun: [3, 1, 2]});                    // every frame; the direction toward the sun
// with orbit_data and vidgen/space-scale: placed, sized, tilted, turned, lit by the data
const saturn = planet(renderer, "Saturn", {space});
const update = (t) => { space.update(t, view(t)); saturn.update(t); };
```

- Ready-made: `mercury venus earth moon mars jupiter saturn uranus neptune io europa ganymede
  callisto titan` (lookalikes, not maps of the real bodies) and invented `ember boreas ochre
  tempest verdant cinder azure`. Types for your own: `rocky`, `icy`, `desert`, `ocean`, `lava`,
  `gas`, `ice-giant`, each with a few options and palettes (CONFIG.md lists them), `air`
  (`false`, a name, or `{like, density}`), `rings` (`true` or `{style, inner, outer, gaps}`).
- Look first: `vidgen parts --kind body`.
- three.js lights do not light a body: give the sun's direction. With three-finish give
  `antialias: "none"`.
- Under a big speed-up a planet turns many degrees a frame and flickers: read
  `body.problems()`; choose `spin: "locked"` or `spin: 40` (seconds of film per turn) and say so
  in the film's notes; the default is the true turning.
- A body takes 2 to 4 s to make and 0.05 to 0.2 s a frame at 720p; `size: 1024` for a close-up
  (about 10 s to make; `size: 2048` about 30 s, then 6 s on later pages from vidgen's cache of
  baked maps), `size: 256` for bodies that stay small. A bake of your own can use that cache too:
  `baked(renderer, name, inputs, {targets, draw})` from `vidgen/baked` (CONFIG.md, "Baked maps"). No landing: close to the ground
  the surface is soft. Reference: CONFIG.md `web`, "Planets, moons and rings".

**Suns and light: `vidgen/space-light`.** Do not light a space scene by hand, and do not draw a
sun as a glowing ball with a sprite flare. One line gives a star, one object lights everything.

```js
// sketch (parts of a page, not a whole file): a sun and the scene's light
import {star, spaceLight} from "vidgen/space-light";
const sun = star(renderer, "sun", {direction: [1, 0.2, -1]});   // a far sun in the sky; or star(renderer, "Sun", {space}) with orbit_data
scene.add(sun.object);                                           // close up: star(renderer, "red-dwarf"), radius 1, place it yourself
const light = spaceLight({scene, camera, sun, bodies: [earth, moon], sky});
const update = (t) => { earth.update(t); moon.update(t); sun.update(t); light.update(t); };   // light.update last
```

- Stars: `red-dwarf orange sun white blue-giant`, or `{temperature, seed}`. Small in the frame a
  star is a brilliant point with thin spikes and faint lens ghosts (`spikes: 0`, `flare: 0` turn
  them off); large, it shows boiling cells, spots, a corona and loops.
- Sunrise over a limb works by itself: the bodies given to `spaceLight` hide and redden the glare.
- `spaceLight` gives each body its sun, lights its night side with planet-shine from the nearest
  lit world (`shine: 0` for none) and ring-shine, sets `light.directional` for ordinary meshes
  (a spacecraft), and with `eclipses: true` draws a moon's shadow on its world and the world's on
  its moon. No ambient light by default.
- Exposure, and what to say in the film's notes: `"film"` (the default) is a convention, not what
  a camera sees: stars stay beside a sunlit world and planet-shine is lifted. `exposure: "camera",
  ev: 0` is honest (no stars beside a day side); `exposure: "auto"` is honest and adapts to what
  is in the frame. Do not caption a `film` picture as a photograph.
- `falloff: 0` (default) lights every world alike, an artistic choice; `falloff: 2` is the true
  inverse-square light (Neptune 900 times dimmer than the Earth).
- Look first: `vidgen parts --kind light`. Reference: CONFIG.md `web`, "Suns and light".

**The sky from inside the air: `vidgen/space-air`.** For a shot within an atmosphere (a plane, a
landing, a sunset) do not paint a gradient and do not use three.js fog: one object gives the sky
for any sun, the sun's disc, the haze on far things and the light, from the same air the world
shows from orbit.

```js
// sketch (parts of a page, not a whole file): the air round the camera
import {air, sunDirection} from "vidgen/space-air";
const sky = air(renderer, "earth", {sun: sunDirection(6, 20), stars: spaceSky(renderer, {seed: 7}), scene});   // also "mars", "thin", "thick"
scene.add(sky.object);                       // the dome: sky, sun, a plain ground under the horizon
sky.haze([hill.material, wing.material]);    // far things take the sky's colour
const update = (t) => { sky.update(t, {camera, sun: sunDirection(6 - t, 20)}); };   // after the camera is placed, before the draw
```

- Metres, +y up, the origin on the ground; the camera's height is read from where it stands (0 to
  space: from above the air the same object draws the limb's glow).
- `sunDirection(elevation, azimuth)`: degrees over the horizon, and round from -z towards +x. Day
  above 10, golden hour 3 to 10, sunset 0, twilight -2 to -8 (the stars come out), night below -12.
- Exposure as `vidgen/space-light`: `"film"` (default) lifts dusk so the blue hour is seen and
  shows the stars once the sky is dark, a convention; `exposure: "camera", ev: 0` is what a camera
  set for a sunlit ground sees (dusk goes black); `"auto"` meters the frame.
- `sky.light.sun` and `sky.light.sky` light ordinary meshes (`scene` in the options adds them).
  Straight to the canvas set `renderer.toneMapping = THREE.ACESFilmicToneMapping` for meshes.
- Say what is invented: `thin` and `thick` are invented worlds; `mars` is a dusty season, three
  times the dust the same world shows from orbit by default.
- 0.19 s a frame at 720p, 0.3 s to make. Look first: `vidgen parts --kind air`. Reference:
  CONFIG.md `web`, "The sky from inside an atmosphere".

**Water to the horizon: `vidgen/space-sea`.** For a sea under that sky do not tile a normal map
on a plane: one object gives waves from a seed on vidgen's clock, the mirrored sky, the sun's
glitter path, whitecaps when it blows and the horizon where the height puts it (curved from high
up), and tells you the water's height anywhere.

```js
// sketch (parts of a page, not a whole file): a sea under the air
import {sea} from "vidgen/space-sea";
const water = sea(renderer, sky, {state: "breeze", seed: 3});   // sky: the air above; "calm", "swell", "rough", "storm"
scene.add(water.object);
const update = (t) => { sky.update(t, {camera}); water.update(t, {camera}); };   // the air first, then the sea
const y = water.heightAt(x, z, t);           // metres over sea level; water.pointAt(x, z, t) is the point in the scene
```

- States by name or by numbers: `{wind: 9, direction: 40, swell: {height: 1.5, length: 160, direction: -20}}`
  (m/s, degrees as `sunDirection`'s azimuth, metres). Foam appears from about 8 m/s.
- `water: "ocean"` (default), `green`, `tropical`, `grey`; `methane` is an invented dark sea for
  an invented world (say so).
- Keep the camera over the crests: `water.heightAt` plus a margin; the sea is drawn for a camera
  at least 0.5 m up. `water.horizon` gives the horizon's distance and dip.
- The world is round: far from the origin take heights from `water.pointAt`, not from y.
- 1.1 s a frame at 720p near the water, 0.65 s from 20 km, 0.07 s at 320x180; `quality: "fast"`
  (a smoother sea) 0.8 s. Look first: `vidgen parts --kind sea`. Reference: CONFIG.md `web`,
  "Water to the horizon".

**Clouds: `vidgen/space-clouds`.** For cloud decks, cloud towers, lightning or a flight inside a
giant of gas do not stack textured planes or billboards: one object draws decks on the world's
sphere that the camera can be under, in, between and over.

```js
// sketch (parts of a page, not a whole file): clouds in the air, their shadows on a sea
import {clouds, giantSky, giantAir} from "vidgen/space-clouds";
const weather = clouds(renderer, sky, {sky: "fair", seed: 4});    // sky: the air; "overcast", "layers", "towers", "storm"
const water = sea(renderer, sky, {shade: weather.shade});         // optional: the clouds' shadows on the water
scene.add(water.object, weather.object);                          // the dome first, then the sea, then the clouds
const update = (t) => { sky.update(t, {camera}); water.update(t, {camera}); weather.update(t, {camera}); };
```

- Your own decks: `decks: [{type: "stratus", base: 1800, top: 3000}, {type: "cirrus", base: 11000}]`
  (`cumulus`, `stratus`, `cirrus`; metres; `cover` 0 to 1; at most 4), `towers: {count: 4}` or
  `towers: {at: [[x, z], ...]}` (at most 6).
- Lightning on the music: `lightning: {times: trackArrays(ctx.music, {hits: ["kick"]}).hits.kick}`
  (or seconds, or `rate: 12` a minute from the seed). A flash's strength is a look.
- A giant of gas: `const sky = air(renderer, giantAir("jupiter"));
  clouds(renderer, sky, giantSky("jupiter", {scale: sky.model.H, latitude: 22}))`, the camera
  about 1.1 x `sky.model.H` up. The decks have the bands of the same world in
  `vidgen/space-bodies`; heights, air and the bands' width are a look (say so).
- `weather.update(t, {camera})` needs the camera the picture is drawn with. Things in the scene
  are always in front of the clouds.
- 1.1 to 2.4 s a frame at 720p (three decks 2.7 s), 0.1 s at 320x180; `quality: "fast"` under half.
  Look first: `vidgen parts --kind cloud`. Reference: CONFIG.md `web`, "Cloud decks, towers,
  lightning, a giant's decks".

**Ground: `vidgen/space-land`.** For mountains, deserts, dunes, canyon land or a crater field
under the air do not build a mesh from noise: one object draws the ground of the same world
`vidgen/space-bodies` shows from orbit, to the horizon, with its own shadows.

```js
// sketch (parts of a page, not a whole file): ground under the air
import {land} from "vidgen/space-land";
const ground = land(renderer, sky, {preset: "alpine"});          // sky: the air; "mars", "canyon", "dunes", "snow", "volcanic", "airless"
scene.add(ground.object);                                         // after the dome, before a sea and clouds
const update = (t) => { sky.update(t, {camera}); ground.update(t, {camera}); };
camera.position.y = Math.max(camera.position.y, ground.heightAt(camera.position.x, camera.position.z) + 50);
```

- Another place or world: `{world: "mars", at: [latitude, longitude]}` (+x is east, -z north of
  the place; `survey(renderer, world)` gives the heights round the globe).
- A coast: `sea(renderer, sky, {depth: ground.depth})`. Clouds: `clouds(renderer, sky, {behind:
  ground.behind})`, then `ground.shadedBy(weather.shade)`. No air: `air(renderer,
  vacuum(RADII.moon), {exposure: "camera", ev: 1.3})`.
- 1.35 s a frame at 720p and 7 to 19 s once for the maps (`quality: "fast"`: 2.3 s), 0.12 s a
  frame at 320x180. High views are the strong ones; under about 400 m over the ground a range
  looks soft. Look first: `vidgen parts --kind land`. Reference: CONFIG.md `web`, "Ground with
  relief".

**Flight paths: `flight_data:`.** A plane over the range, a glider round a peak, a space plane
coming down from orbit: do not move a craft by hand in JavaScript. `flight_data:` in a `web`
scene's `params` gives the page `ctx.flight`: each flight's position, velocity and attitude (bank in
turns, nose up in climbs) for every frame, in the frame `vidgen/space-air` and `space-land` draw in,
checked never to come under the ground.

```yaml
- id: pass
  type: web
  duration: 20
  params:
    script: extensions/fly.js
    flight_data:
      ground: {land: alpine}               # the same ground the page draws; or sea, sphere, flat
      flights:
        - name: Plane
          start: {x: -6000, z: 2000, above_ground: 600, heading: 70, speed: 140}
          legs:
            - {follow: {clearance: 300}, for: 12}                    # terrain following
            - {turn: {by: 60, bank: 35}, follow: {clearance: 300}}
            - {follow: {clearance: 300}, for: 30}
            - {climb: {to: 5500, rate: 20}, speed: {to: 180}}
            - {circle: {around: [25000, 19000], radius: 4000}}        # round a place; also waypoints: [[x, z], ...], land: {}
```

```js
// sketch (parts of a page, not a whole file): a craft on a flight
ship.fly(ctx.flight, {flight: "Plane"});          // ship = craft(...) of vidgen/space-craft; then ship.update(t) each frame
ctx.flight.place(marker, "Plane", t);             // or any three.js object
const above = ctx.flight.aboveGround("Plane", t), mach = ctx.flight.mach("Plane", t);
```

- Legs: `straight`, `turn` (to or by, bank or radius), `circle`, `waypoints`, `climb` / `descend`,
  `level`, `follow`, `speed`, `land`, `reentry` (from `start: {orbit: Ship}` of the scene's
  `orbit_data`); each lasts `for` seconds, `until` a time ('bar 9' with `music_data`) or as long
  as it needs. Too near the ground is an error naming the time and place; `lift: true` raises the
  path there instead.
- Keep the page's `land(...)` options, air and place the same as `ground:` (the frame is the
  land's). Reference: CONFIG.md `web`, "Flight data".

**Phenomena: `vidgen/space-phenomena`.** A black hole, a wormhole, a jump to warp, asteroids, a
comet, an aurora: do not write these by hand (a black disc with an orange ring is not a black
hole). Each is one call and one `update(t)`.

```js
// sketch (parts of a page, not a whole file): phenomena
import {blackHole, wormhole, warp, asteroids, asteroid, comet, aurora} from "vidgen/space-phenomena";
const hole = blackHole(renderer, {sky});                 // bends that sky; one unit = the horizon's radius
scene.add(hole.object);                                   // hole.update(t) each frame
const rocks = asteroids(renderer, {seed: 5, light});      // rocks.update(t, {camera}); or {layout: "belt", inner: 42, outer: 90}
const tail = comet(renderer);                             // tail.update(t, {sun: [x, y, z], velocity: [x, y, z], activity: 1})
```

- `blackHole`: `{disc: false}` for the hole and the bent sky alone, `temperature` (5400; lower
  is redder), `tilt`, `doppler`, `speed`, `quality: "fast"` when time is short. Put the Milky
  Way behind it (`camera` opposite `sky.direction("center")`) for an Einstein ring. It bends the
  sky only: keep planets and ships out from behind it.
- `wormhole(renderer, {sky, other: spaceSky(renderer, {seed: 11}), length: 30})` shows the other
  sky in a ball; `const state = hole.passage(camera, progress)` flies through (progress 0..1 from
  your bar clock); when `state.side` is -1 show `other.object` and hide this side's things.
- `warp(renderer, {seconds, fps: ctx.fps})`: `const state = w.update(t, {progress, camera,
  intensity})`, then `sky.set({brightness: state.sky})`. Pulse `intensity` with the music; never
  pump the camera's lens. `vidgen motion check` warns of `shimmer` on the streaks: expected.
- `comet(renderer, {space, body: "Halley"})` with `orbit_data` takes its place, the sun and its
  growth near the sun from `ctx.orbits`. `aurora(world)` lights the night side's polar oval.
- Budget (720p, software GL, on top of sky and finishing): a black hole filling the frame 0.75
  to 0.9 s a frame, a wormhole 0.45, the others 0.05 to 0.2. A black hole shot doubles a
  frame's cost: keep such shots short or the hole smaller in the frame.
- Say in the film's notes what is not physics: the disc's colours, the warp, the sizes of
  comets and belts. Look first: `vidgen parts --kind phenomenon`. Reference: CONFIG.md `web`,
  "Phenomena".

**Spacecraft: `vidgen/space-craft`.** Do not build a ship from grey boxes and cylinders: take a
ready-made craft, or the kit's parts. Every craft is an invented design in metres with foil,
plating, solar cells, windows, lights and engines.

```js
// sketch (parts of a page, not a whole file): craft
import {craft, fleet, craftEnvironment} from "vidgen/space-craft";
const probe = craft("probe", {seed: 7});                  // probe | satellite | station | ship | lander | tug
scene.add(probe.object);                                  // +z the nose, +y the top; another seed, another design
const light = spaceLight({scene, camera, renderer, sun, bodies: [earth], sky, at: probe.object, shadows: probe.shadows});
probe.shade(sun);                                         // the craft hides the sun's glare
scene.environment = craftEnvironment(renderer, scene, {at: probe.object}).texture;   // metal mirrors sky and planet
// each frame, before light.update(t):
probe.update(t, {sun, camera, height: ctx.height});       // wings to the sun, lights blink, far away a point of light
```

- With `orbit_data`: `craft("ship").fly(space, {body: "Ship", attitude: "prograde"})`, then
  `ship.update(t)` after `space.update`. The craft turns its nose along each burn of the data,
  fires its engines for 2 s round it (`burn: {seconds, turn}`) and turns back. Attitudes:
  `prograde`, `retrograde`, `radial`, `nadir` (a station), `sun`, `target` (with `target:
  "Earth"`: a probe's dish to the Earth), or a list with times: `[{mode: "nadir"}, {at: 4,
  turn: 3, mode: "target"}]`.
- Without orbit data: `ship.update(t, {throttle: 1})` (0 to 1, or a function of t: follow the
  music's level), `rcs` for the small thrusters (a kick), `lights` for the lamps.
- Always set `scene.environment` (above) and the light's `shadows`: without the environment
  metal and foil are black where the sun is not mirrored; without shadows a craft looks flat.
- A fleet: `const ships = fleet("ship", {count: 5, seed: 3}); scene.add(ships.object);
  ships.update(t, {sun})`. For a craft far away or many of them use `detail: "far"`.
- A craft of your own: `const kit = craftKit({seed})`, parts such as `kit.hull({shape:
  "prism", sides: 8, skin: "foil"})`, `kit.dish({diameter: 3})`, `kit.solarWing({panels: 3})`,
  `kit.engine({kind: "chemical"})`; join them with `attach(parent, "fore", child)` or
  `attach(parent, {angle: 90, along: 0.5}, child)`, repeat with `around(parent, () =>
  kit.thrusters(), {count: 4})`, finish with `kit.craft(root)`.
- Engines in vacuum widen and have no shock diamonds (`chemical`, `vacuum`, `ion`); `air` is
  for a lander near the ground.
- Budget (720p, software GL): a craft in a wide shot 0.05 to 0.15 s a frame, filling the frame
  0.3 to 0.6 s, engines filling the frame up to 0.65 s more.
- A path line (`space.path`) in a close-up wants more `path_samples` in `orbit_data` (the line
  is a polyline); from afar `marker: 3` keeps the craft a visible point.
- Look first: `vidgen parts --kind craft` and `--kind craft-part`. Reference: CONFIG.md `web`,
  "Spacecraft".

**Space planes: `vidgen/space-plane`.** For a winged craft — a glider coming home from orbit, a
cargo spaceplane, a scout over another world — take a ready-made plane and fly it on a
`flight_data:` path; do not model one from boxes.

```js
// sketch: parts of a page (not a whole file)
import {plane} from "vidgen/space-plane";
const ship = plane("glider", {seed: 7}).fly(ctx.flight, {flight: "Plane"});   // glider, freighter, needle, lifter, scout, skiff
scene.add(ship.object);
for (const m of Object.values(ship.materials)) sky.haze(m);                   // the air between
// each frame: ship.update(t, {gear: 0, bay: 0});
```

- Every seed is another plane of the kind (proportions, wing, scheme, stripes); `scheme`,
  `color`, `belly`, `accent`, `scorch` set the look by hand; `planeFleet("glider", {count: 6})`
  is a formation.
- On a flight the plane banks with the turn and its elevons, rudders and brakes move by the
  flight's rates; `update(t, {gear: 1})` lowers the gear, `{bay: 1}` opens the payload bay in
  orbit, `{controls: {flap: 25}}` sets a surface by hand, `{throttle: 1}` fires the bells.
- A plane of your own: `planeFrom({body: {...}, wing: {preset: "swept", span: 14}, fins:
  {type: "vee"}, engines: {count: 2}})`, then read `ship.problems()`: it names a wing that does
  not touch the body or gear that does not reach the ground.
- Designs are invented: never copy or name a real or film vehicle, and put no flags or agency
  names on a plane (markings are stripes and an invented registration).
- Budget (720p, software GL): 0.12 to 0.2 s a frame for a plane close up; it casts no shadow on
  the ground and is drawn in front of every cloud.
- Look first: `vidgen parts 'plane-*'`. Reference: CONFIG.md `web`, "Space planes".

**Re-entry and flight effects: `vidgen/space-effects`.** A craft coming down through the air
glows; a plane high up leaves a vapour trail; an engine in air has a short bright flame. One call
adds them to a plane or any craft, and with `flight_data:` they follow the flight by themselves:

```js
// sketch: parts of a page (not a whole file)
import {effects} from "vidgen/space-effects";
const fx = effects(ship, {flight: ctx.flight, name: "Plane", sky, reentry: true, contrails: true, exhaust: true, vapour: true});
scene.add(fx.object);                        // the trails are laid in the world, not tied to the craft
// each frame, after ship.update(t):
fx.update(t);
```

- `reentry`: a glowing layer on the windward side, hot tiles, a wake, sparks; from far away a
  bright head with a train of light. Strength from the flight's `heating` (shown as full at
  `reentry: {full: 0.65}`), or by hand: `fx.update(t, {heating: 0.8})`.
- `contrails`: only above 8 to 9 km (`{always: true}` anywhere); `exhaust`: replaces the craft's
  plumes with one shaped by the air's density, `fx.update(t, {boost: 1})` for the afterburner;
  `vapour`: a cone near Mach 0.97 and wing vapour in turns over 2.4 g, low down only.
- Without a flight give `velocity`, `height`, `heating`, `mach`, `load` to `update`. Unknown names
  are refused with the closest word.
- A re-entry costs about 0.4 s a frame at 1280x720 (`quality: "fast"` 0.3), the others next to
  nothing. Look first: `vidgen parts --kind effect`. Reference: CONFIG.md `web`, "Re-entry and
  flight effects".

**Giant ships: `vidgen/space-hull`.** For a ship kilometres long. Seven invented families —
`spine`, `carrier`, `cluster`, `lance`, `wheel`, `ark`, `twin` — each another ship for every
seed. A hull is a craft of `vidgen/space-craft`: it flies a body of `orbit_data`, its bells fire
with `throttle`, a star's glare hides behind it:

```js
// sketch: parts of a page (not a whole file)
import {hull} from "vidgen/space-hull";
const ship = hull("carrier", {seed: 4, length: 3000}).fly(space, {body: "Ship"});   // metres; +z the bow, +y up
ship.scaleRef("ship", {at: "hangar-1", gap: 120});     // a 50 m craft beside a hangar slot: without it nothing says "3 km"
// each frame, after space.update(t, view):
ship.update(t, {sun, throttle: 0.5});
```

- These are the large forms: plates, trenches, hangar slots as dark voids, radiators, bells.
  Dress the hull for anything nearer than a distant silhouette:
  `const detail = dress(ship, renderer)` (`vidgen/space-hull-detail`) and, each frame after
  `ship.update`, `detail.update(t, {lights: 0.5 + 0.5 * ctx.music.level(t), light})`: seams and
  pipe runs at two scales, windows in rows along the decks (they come out where the sun does not
  reach), lit hangar bays with parked craft, deck clutter, marks, navigation lamps, one long
  plume a bank of bells. `detail.fly(small, "hangar-1", u)` flies the small craft into a bay.
  The maps are baked once (`vidgen cache`). Options and costs: `docs/CONFIG.md`.
- What says "kilometres": rows of windows, a small craft in frame, a bay with depth, a wide lens
  close along a wall, the world behind with a long lens. A hull alone on black from far reads as
  a model whatever its detail.
- Something drawn with `frustumCulled = false` and a negative `renderOrder` is sky in a `SpaceView`
  (behind everything); give it `userData.sky = false` to keep it in the world.
- `ship.problems()` names buried bells, absurd proportions and one layout the kit refuses to
  look like. `hullFleet([...], {count, seed})` is a formation at `far` detail.
- A hull filling a 1280x720 frame costs about 0.3 s. Look first: `vidgen parts 'hull-*'`.
  Reference: CONFIG.md `web`, "Giant ship hulls".

**Camera moves in space: `vidgen/space-camera`.** Do not write camera positions by hand: name
the move. Every move is a function of time (same time, same frame; cuts and motion blur are
safe) and never puts the subject in the dead middle unless you ask.

```js
// sketch (parts of a page, not a whole file): camera moves
import {spaceCamera} from "vidgen/space-camera";
const cam = spaceCamera({space, camera});                 // on a SpaceView; subjects are bodies of orbit_data
const view = (t) => cam.arc(t, {subject: "Earth", phase: {limb: 0.12}, distance: {radii: 5}});   // a crescent, the sun just off the limb
// each frame, first of all: cam.apply(t, view(t)); then the worlds, the craft, the sun, the light
```

- The moves: `cam.flyBy(t, {subject, over: [0, 8], closest: {radii: 2.4}, side: "left"})`;
  `cam.arc` (`phase`: `front`, `three-quarter`, `half`, `crescent`, `backlit`, degrees, or
  `{limb: k}`; `[from, to]` with `over` moves); `cam.arrive(t, {subject, over, lens: "wide"})`
  (from far out to a low orbit over a level limb; `sunAhead: 9` ends at a sunrise);
  `cam.reveal(t, {behind: "Earth", at: 4 * bar, rate: 0.5, air: 0.1})` (a sunrise whose first
  light is on the bar; `of: "Moon"` for a moonrise); `cam.follow(t, {subject: ship, view:
  "chase"})` (`lead`, `three-quarter`, `side`, `shoulder` with `target`, `small`, `horizon`: the
  limb looming behind the craft through a long lens); `cam.pass(t, {subject: ship, over})` (the
  craft passes the camera); `cam.zoom(t, {stops: [{subject: ship, distance: 130}, {subject:
  "Earth", distance: {radii: 4.5}, hold: 1}, {subject: "Earth", distance: 2.6e9}]})` (powers of
  ten: every second multiplies the distance by √10).
- Timing: `over: [start, end]` in seconds; on the music's clock give `time: T` with `over: [8 *
  bar, 12 * bar]`. `ease: 0` when you cut into a move that is already going.
- Framing: `place: [x, y]` (−1..1; a third is 1/3), `lens: "wide" | "normal" | "long" | "tele"`
  (or millimetres), `level: "Earth"` for that world's horizon. A long lens from farther back
  makes the world loom behind a craft: `loomLens({craft, world, gap, craftShare, worldShare})`
  gives the lens and the distance.
- Check before you render: `cam.check(view, {from: 0, to: 8})` returns sentences (the camera
  inside a world, the subject out of the frame or under 3 px, a path through a world, a jump);
  an empty list is good. Throw them as an error while you develop.
- Depth of field: a shot's `focus` is the subject's distance: `dof: (t) => ({focus:
  view(t).focus, fStop: 2.8})` in `Finish`, with `dofFocus: (t) => view(t).focus` on the
  `SpaceView`.
- Cuts that suit space, both scenes reading one curve: a match cut on a disc (`cam.disc(shot,
  "Earth")` → `matchDisc(disc, radius, fov)` → `{distance, place}` for the next shot), a cut on
  a flash (`flash: (t) => ({amount: flashCut(T, cutTime)})`), a warp (`warp.update(t, {progress:
  warpCut(T, cutTime)})`).
- Without orbit data: `spaceCamera({camera, sun: [1, 0.2, -1], bodies: [earth]})`; subjects are
  the objects (`subject: earth`) or `{at: [x, y, z], radius}`.
- Look first: `vidgen parts --kind camera`. Reference: CONFIG.md `web`, "Camera moves for space
  scenes".

**Camera moves in the air and beside giant ships: `vidgen/space-camera-air`.** The same rig with
more moves; name the move, do not write camera positions:

```js
// sketch: parts of a page (not a whole file)
import {airCamera} from "vidgen/space-camera-air";
const cam = airCamera({camera, sky, ground, water, clouds: weather, flight: ctx.flight, music: ctx.music, crafts: {Plane: ship}});
// each frame, first the plane, then the camera, then the air and what stands in it:
ship.update(t); cam.apply(t, cam.chase(t, {flight: "Plane"})); sky.update(t, {camera}); ground.update(t, {camera});
```

- In the air: `skim` (a low pass at a stated `clearance` and `speed`, following the ground,
  banking into its `turn`), `climbThrough` / `descendThrough` (a cloud deck's fog and out the
  other side; `adapt: 1` gives an `ev` for the air so the break-out is not a white flash),
  `chase` (behind a plane with a lag and half its bank), `wing` (locked to the plane: `view:
  "wingtip" | "tail" | "belly" | "nose"`), `flyPast` (a standing camera, the plane passes at
  `at`), `orbitPeak` (round a mountain or a cloud tower: `around: {near: [x, z], reach}` or
  `{tower: 0}`), `rise` (a crane from the surface to tens of kilometres; `down: true` back).
- Beside a ship (`airCamera({space, camera, ships: {Ship: hull}})`): `hullPass` (a slow pass a
  `standoff` off a `side`, the path made from the hull's regions), `hullReveal` (the bow slides
  in over the camera at `at` and the hull keeps coming; `mode: "limb"` from behind a world),
  `intoBay` (into a `hangar`; `out: true` out of it), `sternBurn` (the bank lights at `light`; give
  `shot.throttle` to `ship.update`; `shake: {amount: 0.3}` only if you want it), `scaleZoom` (a
  place on the hull → the whole ship → a speck by its world).
- The operator over any view: `const view = cam.operator(moveTrack(moves), {hand: "handheld", exposure: true,
  horizon: true, cuts: [8]})`; hand `shot.ev` to the air (`air(..., {ev: () => shot.ev})`); `operate(view,
  {hand, horizon})` without a rig. A function of t: a still at t is frame t.
- A camera look in code: `const look = cameraLook("drone", {finish: {noise: 0.006}})` (`vidgen/camera-looks`),
  then `new Finish(renderer, scene, camera, ctx, look.finish)` and `cam.operator(view, look.operator)`.
- Timing: `over: [start, end]` in seconds or `{bar, beat}` of the score (`music: ctx.music`);
  `ease: [1, 0]` starts at rest and ends moving, `ease: 0` is steady: cut two moves together on
  motion. Every move is a function of t: a still at t is frame t.
- The camera is never under the ground or the water (it is lifted and the shot's `notes` say
  so), never nearer a hull's regions than the stand-off; "up" is the local vertical. Read
  `cam.check(view, {from, to})` while you develop.
- Beside a ship: `ship.update(t)` before the move; `new SpaceView(ctx, {renderer, scene, camera,
  near: 4})` gives the hull's depth more precision (the `space` scene does it for you).
- Speeds that read: a pass along a 3 km hull at 40 m/s (show a part of it, not the whole ship in
  ten seconds); a `rise` to 60 km in 8 s or more.
- Cost: the scene's own, 0.8 to 2.1 s a frame at 1280x720. Look first: `vidgen parts 'camera-*'`.

**Orbit to ground in one shot: `vidgen/space-descent`.** One call makes the globe, the air, the
sea, the ground and the cloud decks of the same world for one place and one sun, and draws the
right ones for the camera's height, cross-faded:

```js
// sketch: parts of a page (not a whole file)
import {world} from "vidgen/space-descent";
const w = world(renderer, {planet: "earth", at: [8, -150], sun: [38, 250], sea: {state: "breeze"}, clouds: {sky: "fair"}, scene});
scene.add(w.object);
const cam = airCamera({camera, ...w.rig});
const fall = {over: [0, 10], from: 400e3, to: 300, heading: 300, turn: 30};
// in frame(t): the descent, then a skim from where it ends, with no cut
const shot = t < 10 ? cam.descend(t, fall) : cam.skim(t, {over: [10, 14], ...cam.descend(10, fall).end, follow: 0});
cam.apply(t, shot); w.update(t, {camera}); renderer.render(scene, camera);
```

- `world(renderer, {land: "mars", sun: [30, 120]})` is a Mars-like desert (planet, place and air
  are the ground's own). A plain scene in metres, not a `SpaceView`.
- `cam.ascend` is the descent backwards. Give the descent a second for every third of a power of
  ten of height or more (400 km to 300 m: 10 s).
- Say in the film's notes what is not true (`w.honest`): the camera's speed; single clouds differ
  between the globe and the decks; the decks' field shows a faint repeat from 60 km.
- Cost at 1280x720: 0.75 s a frame from orbit, about 3.4 s in the handover (400 km to 2.5 km over a
  sea), 1.5 to 1.8 s near the surface. Look first: `vidgen parts 'joined-*' camera-descend`.
  Reference: CONFIG.md `web`, "Camera moves in the air and beside giant ships"; recipes in
  `docs/COOKBOOK-SPACE.md`.

**Ready-made parts: look before you build.** `vidgen parts` writes `parts_sheet.png`: every
ready-made three.js part (skies, structures, effects, environments; more space parts as they are
added) drawn in one browser, each tile labelled with its name and the one line that uses it.
`vidgen parts --list` prints the same without drawing; `vidgen parts --kind sky`, `vidgen parts
portal` (one large tile) or `vidgen parts 'star-*'` narrow it. Copy the line into your page (it
names its module), or build a part by name with its defaults:
`import "vidgen/parts/three-kit.js"; import {buildPart, defaultStage} from "vidgen/parts";`
(CONFIG.md, "Ready-made parts"). Over MCP: `parts`.

**three.js** comes with vidgen: `import * as THREE from "three"` in a `script:` or in a page's
`<script type="module">` (with a chosen set of its add-ons, below):

```js
// extensions/cube.js
import * as THREE from "three";
let renderer, scene, camera, cube;
export function load(ctx) {
  renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: true, alpha: true});   // alpha: the video's background shows
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(35, ctx.width / ctx.height, 0.1, 50);
  camera.position.set(0, 1.2, 5);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, ctx.theme.background, 0.5));
  const sun = new THREE.DirectionalLight(0xffffff, 2.5);
  sun.position.set(-3, 4, 3);
  scene.add(sun);
  cube = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.4, 1.4), new THREE.MeshStandardMaterial({color: ctx.theme.colors.primary}));
  scene.add(cube);
}
export function frame(t, ctx) {
  cube.rotation.set(0.4, t * 0.8, 0);
  renderer.render(scene, camera);
}
```

**three.js add-ons.** These ship with vidgen, from the same three.js (0.186.1); import them as
three.js's own docs do (`three/addons/…`; the older `three/examples/jsm/…` works too). They use
the same `THREE` as your code.

| for | import |
|---|---|
| glTF models (`.gltf`, `.glb`) | `import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js"` |
| merging, fixing geometry | `import * as BufferGeometryUtils from "three/addons/utils/BufferGeometryUtils.js"` |
| studio light and reflections | `import {RoomEnvironment} from "three/addons/environments/RoomEnvironment.js"` |
| glow (bloom) | `EffectComposer`, `RenderPass`, `UnrealBloomPass`, `OutputPass`, `ShaderPass`: `"three/addons/postprocessing/<Name>.js"` |
| HTML labels on 3D objects | `import {CSS2DRenderer, CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js"` |
| lines thicker than 1 px | `Line2`, `LineGeometry`, `LineMaterial`, `LineSegments2`, `LineSegmentsGeometry`: `"three/addons/lines/<Name>.js"` |
| rounded boxes | `import {RoundedBoxGeometry} from "three/addons/geometries/RoundedBoxGeometry.js"` |
| shapes from SVG paths | `import {SVGLoader} from "three/addons/loaders/SVGLoader.js"` |
| a camera turning round a target | `import {OrbitControls} from "three/addons/controls/OrbitControls.js"` |

```js
// extensions/studio.js: a rounded box lit by RoomEnvironment, a glowing ring, an HTML label
import * as THREE from "three";
import {RoundedBoxGeometry} from "three/addons/geometries/RoundedBoxGeometry.js";
import {RoomEnvironment} from "three/addons/environments/RoomEnvironment.js";
import {EffectComposer} from "three/addons/postprocessing/EffectComposer.js";
import {RenderPass} from "three/addons/postprocessing/RenderPass.js";
import {UnrealBloomPass} from "three/addons/postprocessing/UnrealBloomPass.js";
import {OutputPass} from "three/addons/postprocessing/OutputPass.js";
import {CSS2DRenderer, CSS2DObject} from "three/addons/renderers/CSS2DRenderer.js";
let scene, camera, composer, labels, box, ring;
export function load(ctx) {
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas, antialias: true});
  renderer.setSize(ctx.width, ctx.height, false);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(ctx.theme.background);   // the composer's picture is opaque
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  camera = new THREE.PerspectiveCamera(35, ctx.width / ctx.height, 0.1, 50);
  camera.position.set(0, 1.2, 6);
  camera.lookAt(0, 0, 0);
  box = new THREE.Mesh(new RoundedBoxGeometry(1.4, 1.4, 1.4, 6, 0.2),
                       new THREE.MeshStandardMaterial({color: ctx.theme.colors.primary, metalness: 0.6, roughness: 0.3}));
  box.position.x = -1.2;
  const glow = new THREE.Color(ctx.theme.colors.accent).multiplyScalar(3);   // brighter than white: it blooms
  ring = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.08, 16, 96), new THREE.MeshBasicMaterial({color: glow}));
  ring.position.x = 1.3;
  scene.add(box, ring);
  composer = new EffectComposer(renderer);
  composer.setSize(ctx.width, ctx.height);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(ctx.width, ctx.height), 0.6, 0.3, 0.9));
  composer.addPass(new OutputPass());
  labels = new CSS2DRenderer();
  labels.setSize(ctx.width, ctx.height);
  labels.domElement.style.cssText = "position: absolute; left: 0; top: 0";
  document.body.appendChild(labels.domElement);
  const tag = document.createElement("div");
  tag.textContent = "Rounded box";
  tag.dataset.vidgenId = "box-label";
  tag.style.cssText = "font: var(--vidgen-size-caption) var(--vidgen-font-body); color: var(--vidgen-text)";
  const label = new CSS2DObject(tag);
  label.position.set(-1.2, 1.15, 0);   // above the box
  scene.add(label);
}
export function frame(t) {
  box.rotation.set(0.4, t * 0.6, 0);
  ring.rotation.set(0.5, t, 0);
  composer.render();               // not renderer.render: the composer draws the scene and its glow
  labels.render(scene, camera);
}
```

Rules found by trying each add-on under vidgen's clock:

- **Files a loader reads.** A relative path is relative to the page (`page:`) or to your script
  (`script:`): `loader.loadAsync("model.glb")` (in `load`, awaited) reads the file beside it, and
  so do `fetch("data.json")`, an image's `src` and a CSS `url()`. In a module that is not the
  scene's script (one in another folder that the script imports), name a file beside that module
  with `new URL("./model.glb", import.meta.url).href`. `.gltf` (buffer embedded
  or in a `.bin` beside it) and `.glb` load; compressed models (Draco, KTX2, Meshopt) do not.
- **Glow and transparency.** `EffectComposer` draws an opaque picture (black where nothing is), so
  give the scene a background (`scene.background = new THREE.Color(ctx.theme.background)`), as
  above. Its colours match `renderer.render` exactly: `OutputPass` applies the tone mapping and
  colour space once; add no second one.
- **Labels.** `CSS2DRenderer` labels are page text: they take the theme variables, follow their
  object, and lint reads them (name them with `data-vidgen-id`); over WebGL their contrast is not
  checked.
- **Thick lines.** `LineMaterial({linewidth: 8})` is in pixels only after
  `material.resolution.set(ctx.width, ctx.height)`; then it stays 8 px at every frame size.
- **`OrbitControls`** has its own idea of time: `update()` with no argument turns `1/60` s worth
  per call, so the speed would follow the frame rate. Pass the time since the last frame:
  `controls.update(t - last); last = t;` in `frame` (angle = `autoRotateSpeed` × 2π / 60 × t,
  the same at every fps). Leave `enableDamping` off (it eases per call too). No mouse is needed.
- **`RoomEnvironment`** lights `MeshStandardMaterial` (metal especially, which is black without
  it) through `scene.environment`, made once in `load` as above.

**Not shipped:** 3D text (`FontLoader`, `TextGeometry`: put text in HTML labels or the page),
`DRACOLoader`, `KTX2Loader` and Meshopt (they run WebAssembly in workers, outside vidgen's clock,
and weigh megabytes), other model loaders, HDR loaders, other controls, VR / AR, physics,
exporters, the GUI helper, the WebGPU renderer and node materials. Importing one stops the render
with `scene 'x': the page imports the three.js add-on 'loaders/DRACOLoader.js' …, which is not
shipped with vidgen …`. To use one anyway, copy that file from three.js 0.186.1 (the npm package
`three`, `examples/jsm/…`) into the project and import it by a relative path
(`import {X} from "./lib/X.js"`); its `import … from "three"` keeps working.

**Finishing three.js scenes: `vidgen/three-finish`.** A look like a film's — depth of field, motion
blur, bloom on the highlights, a tone curve, a colour grade, vignette, grain, smoothed edges —
comes ready-made with vidgen, as a module you import by name. It draws your scene into linear
half-float pictures, finishes them and puts the result on the canvas encoded as sRGB once (leave
`renderer.toneMapping` and `outputColorSpace` as they are; give the scene a background: the picture
is opaque). Everything is a function of `t` and the options, so every render draws the same frames;
the grain is seeded by the frame number.

```js
// extensions/finished.js: brushed and polished metal in a baked studio, finished
import * as THREE from "three";
import {Finish, focusDistance, studioEnvironment, surfaceFinish, softShadows} from "vidgen/three-finish";
let finish, camera, wheel, ball;
function update(t) {                       // the whole scene at time t, keeping no state
  wheel.rotation.z = -t * 20;              // fast: motion blur smears it
  camera.position.set(Math.sin(t * 0.2) * 4, 1.5, Math.cos(t * 0.2) * 4);
  camera.lookAt(0, 0.4, 0);
}
export function load(ctx) {
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(ctx.theme.background);
  scene.environment = studioEnvironment(renderer, {preset: "studio"});   // soft boxes for metal to reflect
  camera = new THREE.PerspectiveCamera(35, ctx.width / ctx.height, 0.1, 50);
  const brushed = surfaceFinish("brushed", {size: 256});
  ball = new THREE.Mesh(new THREE.SphereGeometry(0.5, 48, 24),
                        new THREE.MeshStandardMaterial({color: 0xc4c9cf, metalness: 1, roughness: 0.3, normalMap: brushed.normalMap}));
  ball.position.set(-0.8, 0.5, 0.6);
  wheel = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.08, 12, 6), new THREE.MeshStandardMaterial({color: 0xd9a441, metalness: 1, roughness: 0.25}));
  wheel.position.set(0.9, 0.6, -0.8);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(20, 20), new THREE.MeshStandardMaterial({color: 0x222326, roughness: 0.6}));
  floor.rotation.x = -Math.PI / 2;
  const key = new THREE.DirectionalLight(0xfff1e0, 1.5);
  key.position.set(-3, 6, 3);
  softShadows(renderer, key, {type: "pcf", radius: 2});
  for (const m of [ball, wheel]) m.castShadow = true;
  floor.receiveShadow = true;
  scene.add(ball, wheel, floor, key);
  finish = new Finish(renderer, scene, camera, ctx, {
    update,                                                    // needed for motion blur
    motionBlur: {samples: 5, shutter: 180},                    // 5 sub-frames: the scene drawn 5 times
    dof: (t) => ({focus: focusDistance(camera, ball), fStop: 2.8, unit: 0.1}),   // 1 scene unit = 10 cm
    grade: (t) => ({temperature: 0.2 - 0.1 * t, saturation: 1.05}),
  });
  finish.warmUp(0);                         // optional: shaders compiled here, not in frame 0
}
export function frame(t) {
  finish.render(t);                         // instead of renderer.render: calls update(t) itself
}
```

| option | default | what it does |
|---|---|---|
| `update` | none | `update(t)` sets the scene to time `t`; `render(t)` calls it (several times with motion blur) |
| `bloom` | `{strength: 0.25, radius: 0.2, threshold: 1, scale: 0.5}` | glow on linear values above `threshold` only (a colour brighter than 1, a sharp highlight); `scale`: its size against the frame; `false` off |
| `toneMapping`, `exposure` | `"aces"`, `1` | `"aces"`, `"agx"`, `"neutral"`, `"aces-narkowicz"` (the short ACES curve both films used), `"none"` |
| `grade` | none | `temperature`, `tint` (−1..1), `saturation`, `contrast`, `lift`, `gamma`, `gain` (a number or `[r, g, b]`, on the encoded picture), `filter` (a linear colour multiplier) |
| `vignette` | `0.3` | a number (amount) or `{amount, inner, outer}` |
| `grain` | `0.02` | film grain, seeded by the frame number |
| `fringe` | `0` | chromatic fringe towards the corners (try 0.3–1) |
| `noise` | off | a camera sensor's noise in place of the grain: `true`, an amount (0.012) or `{amount, color, size, floor}`; more in the shadows than in the highlights, none where the picture clips, coloured, new each frame |
| `range` | off | a camera's limited dynamic range: `true`, stops above mid grey (2.5) or `{stops, shoulder, black}`; highlights clip to white with a short shoulder, `black` crushes the shadows |
| `sharpen` | off | in-camera sharpening with faint halos: `true`, an amount (0.5) or `{amount, radius, limit}` |
| `distort` | off | the lens's barrel distortion, from `camera.fov` at every frame (4.7 % at the corner at 16 mm, none from 50 mm): `true`, a factor on it (1) or `{amount, mm}` (a fixed focal length); the corners stay put, the middle is magnified a little |
| `edges` | off | softness and a colour fringe growing towards the edges: `true` (1.2 and 0.8 pixels at 720p at the corner), the softness or `{soft, fringe, power}` |
| `halation` | off | a warm glow bleeding round the brightest parts: `true`, an amount (0.25) or `{amount, radius, threshold, color}` |
| `antialias` | `"fxaa"` | `"fxaa"` or `"none"` |
| `dof` | off | `{focus, fStop, unit, maxBlur, quality}`: `focus` a distance, an object or a point; a thin lens of the camera's focal length (`camera.fov`, `filmGauge`) at `fStop`, scene units of `unit` metres; or `blur` (pixels at 720p far behind the focus) instead of `fStop`; `maxBlur` 10 px at 720p; `quality` `"low"`, `"medium"`, `"high"` |
| `motionBlur` | off | `{samples, shutter}`: `update(t)` at `samples` times across `shutter` degrees of a frame (180 = half the frame time), centred on `t`, averaged; shutter 0 is exactly no motion blur |
| `renderScale` | `1` | draw the scene smaller and scale it up (0.75: about half the shading cost) |
| `fade`, `flash`, `encoding` | `1`, `0`, `"srgb"` | fade to black; `{amount, color}` added light; `"gamma2.2"` to match a page that encoded with `pow(c, 1/2.2)` |

Any option may be a function of `t` (`dof: (t) => ({...})`); it is called after `update(t)`, so
`focusDistance(camera, object)` follows a moving camera. `finish.set({...})` changes options from
`frame` too. A misspelt or out-of-range option stops the render with the reason
(`vidgen/three-finish: unknown option "blom" (did you mean "bloom"?)`).

Helpers in the same module: `studioEnvironment(renderer, {preset: "studio" | "cool" | "soft",
boxes, sky, ground, up, blur})` (soft boxes baked through PMREM for `scene.environment`),
`nebulaSky(renderer, {seed, size, deep, mid, bright, density, stars, environment})` (a nebula and
stars baked into a cube map for `scene.background`; the same seed, the same sky),
`surfaceFinish("brushed" | "geneva" | "perlage" | "circular" | "sunray", {size, roughness})`
(`{normalMap, roughnessMap}` for watch-like metal), `softShadows(renderer, light, {type, radius,
mapSize})` and `focusDistance(camera, object)`.

- **What it costs** (2 cores, software WebGL, 1280x720, a PBR still life whose plain
  `renderer.render` takes about 0.47 s a frame): the chain with everything off +0.05 s; tone
  mapping, grade and vignette, grain, FXAA, fringe about +0.01 s each; bloom +0.01 s at `scale:
  0.25`, +0.03–0.07 s at 0.5, +0.13 s at 1; depth of field +0.07 s (`low`), +0.14 s (`medium`),
  +0.6 s (`high`); motion blur costs a whole scene drawing per sample (×2: 0.91 s, ×4: 1.69 s, ×6:
  2.58 s here); `renderScale: 0.75` saves about a third. A shadow-casting light is drawn again for
  each sample too.
- **Motion blur** needs a scene that is a function of `t`: `update(t)` must set everything from `t`
  (no `+=` per call). Start with 3–5 samples and only on shots with fast motion; a `--draft` can
  turn it off (`motionBlur: ctx.width < 640 ? false : {...}`).
- **Soft shadows.** three.js 0.186 has no `PCFSoftShadowMap` (asking for it gives `PCFShadowMap`
  and a console warning). `softShadows(renderer, light, {type: "pcf", radius: 2})` is the
  recommendation: free here, soft edges up to a radius of about 4 texels (beyond that its 5
  rotated samples show as a fine dither under the grain). `type: "vsm"` gives smooth wide
  penumbrae but cost +0.75 s a frame at a 2048 map here, and every receiver also casts.
- **Warm-up.** `finish.warmUp(t)` in `load` compiles the scene's and the chain's shaders and draws
  once (the still life: frame 0 took 3.0 s instead of 8.5 s; `load` 8.7 s instead of 1.1 s). It
  is optional (the first frame may take 30 s). three.js' `compileAsync` must not be awaited in
  `load`: it polls with a timer, and time stands still there, so it never resolves.
- **Fog** mixes in linear light in the chain but in sRGB with `renderer.render` to the canvas, so a
  fogged scene looks slightly different once finished. Otherwise, with every effect off the
  chain draws what `renderer.render` draws (within one level).
- The whole worked example is `examples/three-finish` (`vidgen still` it at three moments); the
  module's file is in the scene's cache key like every file the page loads.

**Building blocks for music videos: `vidgen/music-time` and `vidgen/three-kit`.** Two more modules
you import by name. `vidgen/music-time` reads the music: the score's tracks as arrays
(`trackArrays(ctx.music, ...)`), a drum's light (`hitEnvelope`), a note's glint or level
(`noteEnvelope`, `noteLevel`), the melody's gliding pitch (`melody`), how strongly a track sounds
(`signalLevel`), bar lengths (`barClock`, `count`), seeded numbers (`rng`, `hash`), easing and
camera keyframes (`smoothstep`, `smootherstep`, `keyframes`, `glide`). `vidgen/three-kit` draws
light on black: glowing strokes (`Glow`), glass crystals, a tesseract, a nebula sky lit from
inside (`SkyDome`), portals onto another sky, star fields you fly through, flares, shock rings from
hits, the melody as a ribbon, the spectrum as rays, tunnels, a corridor, great rings, swarms, dust,
and `aimCamera`. They are the parts the example films wrote by hand (`examples/parallel-space` is
built from them).

```yaml
music: tidewater                 # a score bed with tracks kick and melody; or your own score
scenes:
  - id: drift
    type: web
    duration: 12
    params: {script: extensions/kit.js, music_data: {tracks: [kick, melody]}}
```

```js
// extensions/kit.js: a tesseract in a nebula; the kick lights it, every note of the melody leaves a glint
import * as THREE from "three";
import {trackArrays, hitEnvelope, smootherstep} from "vidgen/music-time";
import {setStage, color, SkyDome, Glow, makeTesseract, updateTesseract, tesseractAngles,
        makeStarField, updateStarField, updateGlints, aimCamera} from "vidgen/three-kit";
import {Finish} from "vidgen/three-finish";
const ICE = color(0x9fdcff), GOLD = color(0xffd166);
let M, song, camera, sky, tes, stars, glints, finish;
function update(t) {                       // everything from song time T: no state, so cuts do not show
  const T = M.time(t), kick = hitEnvelope(song.hits.kick, T, 0.12);
  aimCamera(Math.sin(T * 0.1) * 3, 1, 20 - 6 * smootherstep(t / 10), 0, 0, 0, 0.05 * Math.sin(T * 0.2), 50);
  sky.turn(T); sky.follow(camera);
  sky.colors(color(0x010308), color(0x06203a), color(0x2a7fa0), 0.4 + 0.3 * M.level(T));
  updateStarField(stars, T, 4 * T);
  updateTesseract(tes, tesseractAngles(T * 0.4), ICE, 1.2 + 2 * kick);       // the kick: brighter, never bigger
  updateGlints(glints, song.notes.melody, T, {c: GOLD, life: 3, place: (i, pitch) => [(i % 5 - 2) * 3, (pitch - 69) * 0.4, -4]});
}
export function load(ctx) {
  M = ctx.music;
  song = trackArrays(M, {hits: ["kick"], notes: ["melody"]});
  const renderer = new THREE.WebGLRenderer({canvas: ctx.canvas});
  renderer.setSize(ctx.width, ctx.height, false);
  const scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, ctx.width / ctx.height, 0.3, 4000);
  setStage({renderer, scene, camera, width: ctx.width, height: ctx.height});   // before any builder
  sky = new SkyDome(3);                                   // baked once from its seed
  stars = makeStarField(600, [10, 200], 400, 11);
  tes = makeTesseract({world: 0.05}); tes.scale.setScalar(2.5);
  glints = new Glow(60, {px: 1.6, halo: 1.6, haloGain: 0.5});   // 5 segments a glint, 12 glints
  finish = new Finish(renderer, scene, camera, ctx, {update, bloom: {strength: 0.6, radius: 0.5, threshold: 0.9}});
}
export function frame(t) {
  finish.render(t);
}
```

- **Light, not size.** Hits change brightness (`lightCrystal(c, kick)`, a `Glow`'s `tint`, a
  flare's intensity); the camera and the sizes follow the form, never a beat.
- **The stage.** `setStage` comes first in `load`; every builder adds to its scene (or `parent`).
  A `Glow`'s widths are in 720p pixels (`px`) or scene units (`world`) and scale with the frame.
- **Arrays or events.** The envelope functions read `trackArrays`' `{t, g}` / `{t, d, p}`;
  `signalLevel(ctx.music, track, T)` and `eventLevel(e, T)` read `ctx.music`'s events (with
  dynamics and hairpins). `ctx.music.pulse` and `last` stay available too.
- Every name and its options: `docs/CONFIG.md`, "Building blocks for music videos". A whole
  film built on them: `examples/parallel-space`; smaller uses: `examples/escapement` (envelopes,
  keyframes, dust) and `examples/signal-fire` (`signalLevel`).

**Opening titles and end cards: `vidgen/title-cards`.** A film watched from the start (a music
video, a short film) can open as a cinema film does: the picture comes up from black and a small
title sits beside its subject for a few bars, then fades before the first cut; the end card
mirrors it on the other side. The module gives both as HTML text over the page, laid out and
timed as `examples/escapement`'s (its `01_winding` and `12_coda`):

```js
// extensions/opening.js: a title on the left third, its subject (here a lit disc) on the right
import {titleCard} from "vidgen/title-cards";
let card;
export async function load(ctx) {
  document.body.style.background = "#05060a";
  card = await titleCard(ctx, {title: "TIDEWATER", subtitle: "a film in four tides"});   // in at 2 s, out by 14 s
}
export function frame(t, ctx) {
  const c = ctx.canvas.getContext("2d"), r = 0.3 * ctx.height;
  c.clearRect(0, 0, ctx.width, ctx.height);
  const g = c.createRadialGradient(0.7 * ctx.width - r / 3, 0.4 * ctx.height, 0, 0.7 * ctx.width, 0.5 * ctx.height, r);
  g.addColorStop(0, "#f0c987"); g.addColorStop(1, "#3a2a14");
  c.fillStyle = g; c.beginPath(); c.arc(0.7 * ctx.width, 0.5 * ctx.height, r, 0, 2 * Math.PI); c.fill();
  card.update(t);                         // the card's opacity from t alone
}
```

- **The rules** (COOKBOOK-3D section 12): the title in the left or right third and the subject on
  the other side; small type, wide spacing, a thin rule, one quiet subtitle, nothing else (no web
  address in the opening); dark, calm space behind the text (a soft gradient is on by default:
  `shade`); fade in over the first bars, hold, fade out before the first cut. The end card
  (`await endCard(ctx, {title, subtitle, link, lines: [...], start})`) uses the same type, smaller,
  on the other side, with the credits small; it holds to the end.
- **Not for Shorts or quick explainers**: their frame 1 moves. In a portrait frame the cards go
  to the lower part (`side: "top"` for the upper).
- Options (`side`, `start`, `fadeIn`, `hold`, `fadeOut`, `size`, `tracking`, `font`, `color`,
  `accent`, `shade`, ...): `docs/CONFIG.md`, "Opening titles and end cards". A misspelt option
  stops the render with a "did you mean".

**From a score to a music video: `vidgen music plan`.** Before writing pages for a song, let
vidgen read its score: `vidgen music plan assets/music/my_song.yaml` prints a role per section
(intro, verse, build, drop, climax, breakdown, outro) and why, the scenes cut on bar lines (a
section over 16 s split on a phrase line where the material changes, one under 5 s joined to the
one before), drops, breaths and silent bars, a colour per scene (cool at the start, warm at the
peak) and the tracks each scene follows (low drums pulse the light, accents send rings, melodies
leave glints, pads set the glow). `--out my_video` writes and validates a draft: `video.yaml`
with the score as `music:`, a `web_cut` scene per cut (the `web` scene without its fade-out, in
`extensions/web_cut.py`) whose `duration` is whole frames between two bar lines, `music_data`
with its tracks, `data:` with its plan, and a starter page per scene (`extensions/<id>.js`, one
look per role, on the kit above: `reactions(ctx.music, ctx.data.react)`, `colourScript`, `orbit`,
`flyThrough`). Look at a still of each scene, then make the pages your own; keep each scene on
bar lines when you join or split them. `--json` gives the plan as data. The plan reads notes,
not sound or words: check its roles against what you hear described (`vidgen music check`).
Over MCP: `music_plan` (`score`, `out`).

**Watching the result: `vidgen motion check`.** Stills cannot show what happens between frames.
After a render (`--draft` first), `vidgen motion check . --draft --json` decodes the video at
160 px wide (no render; a minute in about 10 s) and lists, with time, frame, scene and
severity: `blank` (black or flat frames entered abruptly inside a scene: a frame that failed to
draw, e.g. a NaN in a shader; **error**), `flash` (one or two frames much brighter or darker than
both neighbours), `flicker` (the light going up and down every frame or two), `pop` (a region
shown for one or two frames), `strobe` (a pattern turning about half its repeat a frame),
`frozen` (no visible change for 1.5 s or more) and `cut_jump` (a big change of brightness across
a cut). Flashes, pops and pulses on the score's drum hits and note starts are info: a reaction to
the music, not a fault. Each finding has a contact strip PNG (`build/<quality>/motion/`, the
finding's frames framed in red): open the errors' and warnings' strips, then `vidgen still` the
scene at that time to find the cause. Without a whole render, `--source scenes` reads the scene
clips in `build/`. Thresholds: `--threshold NAME=VALUE` (`docs/CONFIG.md`, "Motion check"); MCP
`motion_check` returns the strips as pictures.

Dark (space) pictures are measured at 640 px too, so a star field or a small crescent on black is
not a blank frame, a slow drift of the stars is not "frozen", and black frames that cut into a
star field are still an error. They add `clipped` (a sun or planet burnt to flat white over 3 %
of the frame: lower its light), `shimmer` (stars whose brightness jumps from frame to frame:
small point stars aliasing; draw them soft and at least 2 px wide), `banding` (a dark glow in
flat steps; info), `empty` (a tiny thing alone on black for 2 s; info) and, for the scenes you
name with `--subject SCENE` (or `all`), `lost` (only stars or black for 1 s where your planet or
ship should be).

**Animation and chart libraries.** These ship with vidgen: import them by name, in a
`<script type="module">` or a `script:`, with no file in the project. Each was run under vidgen's
clock. "Plays by itself" means the library's own loop follows the video's time from the scene's
first frame, and two renders give the same frames.

| library | import | how to drive it |
|---|---|---|
| anime.js 4.5.0 | `import {animate, createTimeline} from "animejs"` | plays by itself, about 12 ms ahead of the video. Frame-exact: `autoplay: false`, then `anim.seek(t * 1000)` in `frame(t)` (a timeline too) |
| Motion 14.12.0 | `import {animate} from "motion"` | plays by itself, frame-exact (springs, sequences and `animate(0, 100, {onUpdate})` too). Do not seek it from `frame`: `controls.time = t` there shows one frame late |
| D3 7.9.2 | `import * as d3 from "d3"` | `transition()` (with `delay` too) and `d3.timer` play by themselves, frame-exact; or set attributes from `t` in `frame(t)` with scales. A force layout by itself does one tick per video frame, so the picture changes with the fps: `simulation.stop()`, then `simulation.tick(n)` |
| Chart.js 4.6.1 | `import Chart from "chart.js/auto"` | its animations play by themselves, frame-exact (a `chart.update()` from a timer too); or `animation: false` and `chart.update("none")` in `frame(t)` |
| lottie-web 5.13.0 | `import lottie from "lottie-web"` | plays by itself (`autoplay: true`), frame-exact; or `autoplay: false` and `anim.goToAndStop(t * 1000, false)` in `frame(t)`. Give it `animationData` (the JSON, from `await fetch(…)`), not `path:` |
| GSAP | not shipped (its licence): copy `dist/gsap.min.js` into the project, `<script src="lib/gsap.min.js"></script>` | call `gsap.ticker.lagSmoothing(0)`, then it plays by itself, frame-exact; or a paused timeline and `tl.time(t)` in `frame(t)` |

D3, Chart.js and Motion are the packages' one-file builds, which also set `window.d3`,
`window.Chart` and `window.Motion`. Chart.js comes with everything registered
(`import {Chart} from "chart.js"` gives the same class; there is no `registerables`). lottie-web
drew with its `svg` and `canvas` renderers. GSAP is not open source ("All rights reserved.
Subject to the terms at https://gsap.com/standard-license"), so vidgen cannot ship it:
`import gsap from "gsap"` stops the render with a message saying so. Tried with GSAP 3.15.1:
`gsap.min.js` works from a `<script src>` (not as a module import); `index.js`, `gsap-core.js` and
`CSSPlugin.js` copied into one folder work as `import gsap from "./lib/gsap/index.js"`. Without
`lagSmoothing(0)` GSAP counts a step longer than 0.5 s as 33 ms. Any other library: put its file
in the project (below: no internet).

**Where the page goes.** `region: bleed` (the default): the page fills the frame edge to edge, a
`title` sits on a plate over its top, and the captions are drawn over its bottom; keep text away
from the edges and out of the bottom fifth. `region: body`: the page is laid out in the space
under a title vidgen draws (`title: "…"`), clear of the margins and of bottom captions; the
easiest way to keep text readable. What the page leaves transparent (no `background` on a page,
`clearRect` on the canvas, three.js with `alpha: true`) shows the video's background; set
`background: var(--vidgen-background)` to make it opaque.

**Both shapes from one page.** `<html>` carries `data-aspect="16:9"` / `"9:16"` and
`data-orientation="landscape"` / `"portrait"`, so CSS can switch layout:
`[data-orientation="portrait"] .row {flex-direction: column}`; a script reads `ctx.orientation`.
Look at both: `vidgen storyboard --variant vertical` (with a vertical variant, `vidgen guide social`).

**Porting a page built in fixed pixels.** A page that already exists (a dashboard, a mock-up of
an app) is usually sized in `px` for one browser window. Do not rewrite its sizes: give the scene
the window width the page was designed for, `params: {page: extensions/dashboard.html,
design_width: 1280}`. The page is then laid out in a window 1280 CSS pixels wide and as high as
the scene's region gives (720 for a 16:9 page with `region: bleed`), and that picture is drawn at
the video's size. The preview, the draft and the 1080p render show the same layout, and HTML
text, SVG and CSS shapes are drawn at the output's pixels, not enlarged from a smaller picture.

- **What the page sees** is its design window: `window.innerWidth`, `100vw`, media queries,
  `getBoundingClientRect()` and `clientWidth` are in the design's pixels. `window.devicePixelRatio`
  is the number of output pixels per CSS pixel: 1.5 for a 1280 design at 1920 px, about 0.67 at the
  854 px preview.
- **A canvas is sharp only when its code uses `devicePixelRatio`.** A canvas has the pixels its
  code gives it: sized from `clientWidth` alone it is drawn at the design size and enlarged, so
  its edges are soft at 1080p. Size it as on a high-density screen: `canvas.width =
  Math.round(canvas.clientWidth * devicePixelRatio)` (the same for the height), then
  `context.scale(devicePixelRatio, devicePixelRatio)` and draw in CSS pixels as before. With
  three.js: `renderer.setPixelRatio(window.devicePixelRatio)` before `renderer.setSize(w, h)`.
- **`ctx`.** `ctx.width` and `ctx.height` are the window in CSS pixels (1280 and 720 here), the
  same numbers as `innerWidth` and `innerHeight`; the canvas of a `script:` has that many pixels
  (multiply as above for a sharp one). `ctx.frame` stays the video frame in output pixels.
  `ctx.theme.sizes` and `--vidgen-size-…` are CSS pixels that still draw text as tall as vidgen's.
- **The height follows the region's shape**; there is no `design_height`, since a height that
  disagrees with the region would squeeze or crop the page. A page designed for a phone, in a
  9:16 video: `design_width: 390`. When the height is not a whole number of CSS pixels (a 1280
  design at 854x480 is 719.4 high), the window is the next whole pixel (720) and the strip under
  the frame's bottom edge, less than one CSS pixel, is not shown.
- **Lint measures the text as it is drawn in the frame**: 12 px text in a 1280 design is 18 px in
  a 1920 px frame, and `min_font`, `off_frame`, `safe_area`, `text_overlap` and `web_clipped`
  judge that. Text that was fine on a desk monitor is often too small for a video: enlarge it in
  the page.

`design_width` is a whole number from 200 to 8192. Without it nothing changes: the window is the
frame's (or the region's) own pixels.

**No internet.** The page cannot load anything from the internet while rendering (a CDN script, a
web font, an API): the request is refused with the warning `scene 'x': refused https://… (a web
scene cannot reach the internet; put the file in the project folder)` and the page renders
without it. Put every library, picture and data file in the project folder and link it
relatively (`<script src="lib/x.js">`, `import {x} from "./lib/x.js"`); a font goes in `fonts/`
(next paragraph). vidgen's own fonts, three.js and its shipped add-ons, and the libraries in the
table above need nothing.

**Using another font.** A page that links Google Fonts draws its text in a fallback font, with one
warning per family: `scene 'x': the page asks Google Fonts for "Space Grotesk", but the internet is
off during a render, so that text is drawn in a fallback font. Put the font's .ttf, .otf or .woff
file in the project's fonts/ folder and remove the link to Google Fonts (…)`. The font has to be a
file in the project before the render:

1. **Get the font's files and its licence**, once, with a browser or a download tool. Two ways,
   both tried with Space Grotesk (SIL Open Font License) on 2026-11-12:
   - the font's own release: `SpaceGrotesk-2.0.0.zip` from the releases of
     `github.com/floriankarsten/space-grotesk` holds `ttf/static/SpaceGrotesk-Regular.ttf`,
     `-Bold.ttf`…, a variable `ttf/SpaceGrotesk[wght].ttf` and `OFL.txt`. (Google Fonts gives a
     zip from its page in a browser; its address `fonts.google.com/download?family=…` answered a
     download tool with a web page, not the zip.)
   - the npm package `@fontsource/<name>`: the file
     `registry.npmjs.org/@fontsource/space-grotesk/-/space-grotesk-5.3.0.tgz` (check it against the
     `dist.integrity` the registry gives for that version) holds
     `package/files/space-grotesk-latin-400-normal.woff`, `…-700-normal.woff`… and
     `package/LICENSE`. Take the `.woff` files, not the `.woff2` ones.
2. **Copy them into the project's `fonts/` folder** (sub-folders are fine): the regular and the
   bold file, the italic one if you use it, and the licence file beside them. A variable font is
   one file for every weight.
3. **Name the family**, as the font names itself (`Space Grotesk`): for the whole video
   `theme: {font: "Space Grotesk"}` or one role `theme: {fonts: {heading: "Space Grotesk"}}`
   (titles, captions and every built-in scene; in a page `var(--vidgen-font-body)` /
   `-heading`); or only in a page, `font-family: "Space Grotesk", sans-serif`. vidgen has already
   declared an `@font-face` per file, with the family, weight and style it read from the file:
   write none yourself.
4. **Remove the link** to Google Fonts (`<link href="https://fonts.googleapis.com/…">` or an
   `@import` of it).

Formats: `.ttf` and `.otf`; `.woff` too (for its own text vidgen writes a `.ttf` copy in
`build/fonts/`). vidgen does not read `.woff2` (`vidgen validate` says so): such a file is used
only by a page whose own `@font-face` names it (`src: url("../fonts/x.woff2")`). Changing a file in
`fonts/` renders every scene again. Checked on Linux by looking at frames (a `title` scene, the
captions, a page's CSS and theme variable, the designed thumbnail; static `.ttf`, `.woff` and a
variable `.ttf`); not tried on Windows or macOS.

**Looking at single frames: `vidgen still`.** To see what the page shows at one moment, do not
render the scene: `vidgen still . --scene gears --at 2.5` writes that frame as a PNG
(`exports/stills/gears_0002.500s.png`) in a few seconds. It is the picture the render draws for
that frame: the same page, clock, theme, `data:`, beats, size and frame rate (checked pixel for
pixel against rendered clips).

```
vidgen still . --scene gears --at 2.5                         # one frame, final size
vidgen still . --scene gears --at 0,4,8,12 --sheet look.png   # four frames in one browser + a contact sheet
vidgen still . --scene gears --count 12 --size preview --sheet look.png --out /tmp/gears
vidgen still . --scene gears --frame 75 --size 640x360 --out one.png
```

- `--at` counts **seconds from the scene's start** (the `t` your `frame(t, ctx)` gets), not the
  video's time; `--frame N` is a frame number; `--count N` spreads N stills over the scene. Repeat
  them or give lists (`--at 1,2.5,4`).
- `--size final` (default) `| preview | draft | WIDTHxHEIGHT`: the page is laid out and drawn for
  a video of that size. A smaller size is much faster for a WebGL page (a three.js film: 2.2 s per
  still at 1280x720, 0.5 s at 640x360, 0.3 s at 320x180, after 9 s to load the page).
- Give times **in increasing order**: they are drawn on one page. The clock only runs forward,
  so an earlier time opens the page again (its load time once more).
- The still is the page alone, over the video's background colour (`--transparent` keeps its
  transparency): no title drawn by vidgen, no captions or overlays, no fade. With `region: body`
  it has the size of the page's box.
- **A page that keeps state.** By default the clock moves straight to the frame's time. That is
  the render's picture when the page draws from the time alone (`frame(t, ctx)` computing
  everything from `t`, CSS animations, the Web Animations API, anime.js, D3 transitions, GSAP with
  `lagSmoothing(0)`). A page that adds something up from frame to frame (a simulation stepped in
  `requestAnimationFrame`, a canvas drawn over itself, a counter; a D3 force simulation on its own timer; Motion,
  lottie-web or plain GSAP playing by themselves) shows a still as if the frames before it had not been drawn. `--exact`
  steps the page through every frame before the still, as the render does: the render's picture
  again, at the cost of every frame's drawing time.
- Works for `web` and for your own types that subclass it. For other scene types use
  `vidgen storyboard --scene ID`. Over MCP: the `still` tool (returns the pictures).

**The lint loop.** `vidgen lint` reads the page's text at each still (its box, its size as drawn,
its colour and what is behind it) and checks it with the usual rules: `off_frame`, `text_overlap`,
`min_font`, `contrast`, `safe_area` (also text under the captions, named so), plus `web_clipped`
(text cut by `overflow: hidden` or by the page's box). Text hidden at that moment (opacity 0,
`display: none`) is skipped, so a beat's reveal is checked once it shows.

- Name what you will want to find in a message: `data-vidgen-id="price"` → `text '…' (page:
  price)`; else lint names it by a CSS-like path (`div.card:nth-child(2) > h2`).
- `data-vidgen-lint="off"` leaves out decoration (a big faint watermark), `"off:contrast"` one rule.
- Text drawn on a canvas, in a picture or in WebGL cannot be read. Declare it, or lint checks
  nothing of it: a `layout(t, ctx)` hook (an export of a script, or on `window.vidgen`) returns
  `[{id, text, box: {x, y, width, height}, size, font, color, background}]` in page pixels. It is
  called after the screenshot of a frame lint looks at and must not change the page:

```js
// in extensions/orbit.js: the label frame() draws, declared to lint (page pixels, width measured)
export function layout(t, ctx) {
  const l = label(ctx), c = ctx.canvas.getContext("2d");
  c.font = l.font;
  return [{id: "label", text: l.text, box: {x: l.x, y: l.y, width: c.measureText(l.text).width, height: l.size * 1.2},
           size: l.size, font: l.font, color: ctx.theme.colors.text, background: ctx.theme.background}];
}
```

Keep one function for what is drawn and what is declared (`label` here), so they never drift
apart. `font` is the canvas font you drew with (or only its family); `background` is what is behind
the text (here the video's background, since the canvas is transparent).

**Usual mistakes** and what vidgen says:

| you see | cause and fix |
|---|---|
| `scenes[0].params: give exactly one of page: (an HTML file) or script: (a JavaScript module)` | both or neither given |
| `page: file not found: extensions/hello.html (looked for …)` (validate) | the path is relative to the project folder (where `video.yaml` is) |
| `script: must be a path inside the project folder, got ../shared/x.js` (validate) | a page or script outside the project folder: copy it in, or, to share one file between projects side by side, set `web_root: ..` (pages are then served from the folder that holds them; `examples/orchestral-shorts` does this) |
| `scene 'x': JavaScript error in extensions/orbit.js line 7 in frame(t=0.500): TypeError: …` | your code threw; the file, line and time are given. At load: `… line 3 at load: …` |
| `scene 'x': JavaScript error in extensions/x.js …: a module script did not load (a file it imports is missing or refused)` | an `import` names a missing file or a URL on the internet |
| `scene 'x': the page imports the three.js add-on '…', which is not shipped with vidgen …` | an add-on vidgen does not ship (list above): copy the file into the project |
| `scene 'x': the page imports 'gsap', which is not shipped with vidgen. GSAP's licence …` | `import … from "gsap"`: copy GSAP into the project and load it from there (table above) |
| `warning: scene 'x': refused https://… (a web scene cannot reach the internet; …)` | a CDN script or API: copy the file into the project |
| `warning: scene 'x': the page asks Google Fonts for "…", but the internet is off during a render …` | a `<link>` to Google Fonts: put the font's file in `fonts/` and remove the link ("Using another font" above) |
| `fonts/x.ttf: not a font file …` | a damaged or mislabelled file in `fonts/`: replace or remove it |
| `scene 'x': frame(t=0.500) in extensions/x.js did not return within 10 s: a loop that never ends or a promise that never settles …` | an endless loop, or waiting for something that never comes (a timer in `load`: time stands still there). The first frame may take 30 s (shaders are compiled then) |
| `scene 'x': extensions/x.html did not become ready within 30 s …` | the page's load event never came (a module that never finishes) |
| `scenes[0].params.data: … data.when: 2026-01-01 is a date, not a JSON value` | quote dates in `data:` |
| a white page | a `page:` with `background: white` of its own (or an old habit): leave the background out or use `var(--vidgen-background)` |
| text too small for `min_font`, or a layout that only fits one shape | sizes in fixed px: use `var(--vidgen-size-…)` for text, `vw` / `vh` for the rest; for a page that already exists in fixed px, `design_width` ("Porting a page built in fixed pixels" above) |
| a page that fills only a corner of the frame at 1080p, or runs off the preview or the draft | a page built in fixed px for one window: `design_width: <that window's width>` |
| a canvas or three.js picture that is soft at 1080p in a scene with `design_width` | the canvas is drawn at the design size: multiply its size by `devicePixelRatio` (above) |
| `scenes[0].params.design_width: 3 is not a window width a page is designed for …` | give the window's width in CSS pixels, 200 to 8192 |
| lint finds nothing on a canvas scene | canvas text is not read: declare it with `layout(t, ctx)` |

**Render cost.** Every frame is a screenshot of the whole page: a `web` scene renders far slower
than a built-in one, and the time grows with the number of frames and with their size. Measured
on a slow 1-CPU machine on two scenes of 20 s (a whole `vidgen render` of the scene, Chromium's
start included, two runs each):

| render | size at 16:9 | an HTML + SVG page | a three.js dashboard |
|---|---|---|---|
| `--draft` | 426x240, 8 fps | 36 s (1.8 s per second of video) | 54 s (2.7 s per second) |
| `--preview` | 854x480, 15 fps | 99 s (4.9 s per second) | 127 s (6.3 s per second) |
| final | 1920x1080, 30 fps | about 28 s per second | about 58 s per second |

So a draft is about 2.5 times faster than a preview (2.7 and 2.3 times here), and a final render
about 3.5 to 4 times slower than a preview (final: measured on 3 s cuts beside a preview of the
same cut; a minute of 1080p `web` video is half an hour to an hour of rendering). The machine's
own speed changed up to 4 times within an hour on the day of these measurements, so trust the
ratios more than the seconds. Work in this order: `vidgen render --draft` to see the whole video
move (240 px on the shorter side at the video's shape: 240x426 at 9:16, 240x240 at 1:1;
`draft: {width: 480, height: 270, fps: 12}` in the config for a larger one), `--preview` and
`vidgen lint` when the timing is right, the final render once. To look at one moment, `vidgen still` (above)
draws single frames without rendering the scene. Keep `web` scenes short (a few
beats each).

- **Progress and where the time goes.** While a scene's frames are drawn, `vidgen render` prints
  a line about every 10 s, and a summary after the last frame:

  ```
  [4/12] 04_escapement: web frames 120/482, 1.24 s a frame, about 7 min 29 s left
  [4/12] 04_escapement: web frames 482/482 drawn in 9 min 58 s (the page ready in 8.0 s before), 1.24 s a frame (the page's frame(t, ctx) 0.02 s, drawing and the screenshot 1.22 s)
  ```

  "The page's frame(t, ctx)" is your JavaScript; "drawing and the screenshot" is the browser
  painting the page — for WebGL the GL work your code asked for, done in software here (a
  detailed three.js film page: about 1.1 s of its 1.24 s at 720p). To make a WebGL page faster,
  draw less: fewer passes, a smaller bloom target, fewer motion-blur copies. With `--json` the
  lines go to stderr, so the MCP `render` tool shows them as progress.
- **No shader warm-up needed.** three.js compiles its shaders in the first frame it draws; that
  frame may take 30 s (the others 10 s). Rendering a frame in `load` and reading a pixel back
  only moves that time into `load`.
- **Two scenes at once.** `--jobs 2` drew a two-scene WebGL test about 10 % faster than one job
  on 2 cores (one scene's software GL already uses about 1.4 cores); `--jobs auto` decides by
  memory.

**Disk.** A `web` scene's frames are kept in a lossless clip until the scene plays them
(`build/<quality>/web/<scene>.mkv`): a detailed WebGL page takes about 26 MB per second of video
at 720p30 (5 GB for a 3-minute film), a flat page far less. `vidgen render` warns before it starts
when the disk may be too small and prints the build folder's size after the join. For a long
WebGL film on a small disk set `render: {intermediate: compact, keep_intermediates: false}` (or
`vidgen render --intermediate compact --clean-intermediates`): the frames clips are about 4.6
times smaller (one more lossy step, far below the final encode's) and each is deleted once its
scene is rendered (a scene rendered again later draws its frames again). See CONFIG,
"Intermediate files and disk".

- **A draft needs a page that scales.** Its window is 426 CSS pixels wide: a page sized in `vw`,
  `vh`, `%` and `var(--vidgen-size-…)` looks the same as at 1080p, only smaller, and so does a
  page with `design_width` (its window stays as wide as designed). A page in fixed pixels without
  `design_width` runs off a draft.
- **Lint and the storyboard never use a draft.** `vidgen storyboard` and `vidgen lint` render
  the whole scene at the preview size (`--final`: the final size), into `build/preview`, so a
  draft never causes a `min_font` finding. Lint's sizes are fractions of the frame, so the
  preview's verdict holds for the final video; text that is hard to read at 240p is expected.
- **Each size keeps its own frames** (`build/draft`, `build/preview`, `build/final`): a draft
  never replaces a preview. An unchanged scene is not drawn again: the frames are kept with every
  file the page loaded, and editing any of them (or its `data:`, the theme or the narration) draws
  that scene again.
  This also holds for a scene of your own type that subclasses `Web` (for example a `web_cut`
  without the fade-out).

