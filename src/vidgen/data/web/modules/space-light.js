// vidgen/space-light: suns and the light of a space scene (DESIGN.md §122.8). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-light".
//
//   import {star, spaceLight} from "vidgen/space-light";
//   const sun = star(renderer, "sun");                         // a ready-made star (STARS) or {temperature, seed, ...}
//   scene.add(sun.object);                                     // radius 1: place and scale it as any object, or
//   const sun = star(renderer, "sun", {direction: [1, 0.2, -1]});   // ... a far sun in the sky, 0.53 degrees wide
//   const sun = star(renderer, "Sun", {space});                // ... or the Sun of ctx.orbits, placed and sized
//   const light = spaceLight({scene, camera, sun, bodies: [earth, moon], sky});
//   function frame(t) { earth.update(t); moon.update(t); sun.update(t); light.update(t); finish.render(t); }
//
// A star is a globe you can look at: cells that boil in place (a function of t, nothing scrolls), a
// limb that darkens and reddens, spots and bright faculae from the seed, a corona with streamers that
// fades over several radii, loops of glowing gas at the limb; colour and character follow the
// temperature. When it is small in the frame the same object is a brilliant point: a soft glow,
// diffraction spikes fixed to the frame and a few faint lens ghosts on the line through the frame's
// middle. The glare knows the bodies in front of the sun (`sun.occluders`, set by spaceLight): it
// shrinks, reddens through their air and moves to the sliver that is left, with no read-back.
//
// spaceLight is the light of the whole scene in one object. Each update(t) it gives every body its sun
// (direction, colour, strength), a second weak light (planet-shine from the nearest lit world, ring-shine
// from its own rings), other bodies' shadows (eclipses, opt-in), and it sets one THREE.DirectionalLight
// for ordinary meshes (and a second for planet-shine), no ambient light. Exposure: "film" (the default
// convention: stars stay visible beside a day side, planet-shine is lifted), "camera" (honest: one
// exposure `ev` for everything; the stars are 20 stops under a sunlit ground) and "auto" (honest, the
// exposure chosen from what is in the frame at t: no state between frames).
//
// Light. Linear values for a tone-mapped picture (vidgen/three-finish), as the sky and the bodies;
// straight to the canvas the star applies the ACES curve and the sRGB encoding itself.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {blackbody} from "vidgen/space-sky";

export const VERSION = 1;
const RAD = Math.PI / 180, TAU = Math.PI * 2;
const PREFIX = "vidgen/space-light";

/** One astronomical unit (m), and the Sun's angular radius seen from there (radians). */
export const AU = 1.495978707e11;
export const SUN_ANGULAR_RADIUS = 0.004652;
/** How many stops fainter than a sunlit ground the sky of vidgen/space-sky is at its brightness 1 (a long
 * exposure of the Milky Way against the "sunny 16" rule: about a million times). */
export const SKY_STOPS = 20;
/** How many stops the city lights of a night side are lifted by the film convention. */
export const LIGHTS_STOPS = 10;
/** The most a light is multiplied by when an honest exposure burns it out (the picture is white long before). */
export const BURN = 32;
export const EXPOSURES = Object.freeze(["film", "camera", "auto"]);
export const QUALITIES = Object.freeze(["fast", "standard"]);

// ---------- checks ----------
const fail = (message) => new Error(`${PREFIX}: ${message}`);
function editDistance(a, b) {
  const row = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j++) { const keep = row[j]; row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = keep; }
  }
  return row[b.length];
}
function hint(word, choices) {
  let best = null, score = Infinity;
  for (const c of choices) { const d = editDistance(String(word).toLowerCase(), c.toLowerCase()); if (d < score) { best = c; score = d; } }
  return best !== null && score <= Math.max(2, Math.floor(String(word).length / 3)) ? ` (did you mean "${best}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; known: ${keys.join(", ")}`);
}
function number(where, v, lo, hi) {
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(v)}`);
  return v;
}
function choice(where, v, list) {
  if (!list.includes(v)) throw fail(`${where} must be one of ${list.map((x) => JSON.stringify(x)).join(", ")}, got ${JSON.stringify(v)}${hint(v, list)}`);
  return v;
}
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp01((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const lum = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const n = len(a) || 1; return [a[0] / n, a[1] / n, a[2] / n]; };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

// ---------- the stars ----------
/** The ready-made stars: `temperature` (K) gives the colour; the rest is each kind's character. */
export const STARS = Object.freeze({
  "red-dwarf": Object.freeze({temperature: 3200, seed: 11, light: 1.5, saturation: 2.2, granulation: 1.25, cells: 16, spots: 3, spotSize: 2.4, faculae: 0.6, limb: 1.15, corona: 0.7, streamers: 0.8, prominences: 3}),
  "orange": Object.freeze({temperature: 4600, seed: 12, granulation: 1.1, cells: 24, spots: 6, spotSize: 1.4, faculae: 0.9, limb: 1.08, corona: 0.9, streamers: 1, prominences: 4}),
  "sun": Object.freeze({temperature: 5772, seed: 13, granulation: 1, cells: 32, spots: 5, spotSize: 1, faculae: 1, limb: 1, corona: 1, streamers: 1, prominences: 4}),
  "white": Object.freeze({temperature: 8500, seed: 14, light: 2.0, saturation: 1.3, granulation: 0.3, cells: 40, spots: 0, spotSize: 1, faculae: 0.2, limb: 0.8, corona: 0.9, streamers: 0.7, prominences: 0}),
  "blue-giant": Object.freeze({temperature: 22000, seed: 15, light: 2.3, saturation: 1.2, granulation: 0.12, cells: 12, spots: 0, spotSize: 1, faculae: 0, limb: 0.65, corona: 1.2, streamers: 0.45, prominences: 0}),
});
/** A star's options and their defaults (see DESIGN.md §122.8 for each). */
export const STAR_DEFAULTS = Object.freeze({name: null, temperature: 5772, seed: 1, light: 1.2, saturation: 3, granulation: 1, cells: 32, boil: 1, spots: 5, spotSize: 1, faculae: 1,
  limb: 1, corona: 1, reach: 6, streamers: 1, prominences: 4, spin: 0, tilt: 0, glare: 1, spikes: 6, spikeAngle: 15, spikeLength: 1, flare: 0.5, quality: "standard",
  direction: null, angularRadius: SUN_ANGULAR_RADIUS / RAD, display: "auto"});
const STAR_CONTROL = ["space", "orbits", "body"];
const MAX_SPOTS = 12, MAX_LOOPS = 8, CORONA_SIZE = 256;

/** A star's colour (linear sRGB, largest channel 1) for a temperature in K: a black body's, `saturation` times
 * as far from white as it is (3 by default in a star: a film's sun is yellower than the real one, which is white). */
export function starTint(temperature, saturation = 1) {
  const c = blackbody(temperature), top = Math.max(...c);
  return c.map((v) => Math.pow(Math.max(v / top, 1e-4), saturation));
}
/** The colour of a star's light on a white ground (linear sRGB, luminance 1): white for a sun-like star,
 * `amount` (0 to 1) of the way to the black body's colour relative to the Sun's for another. */
export function sunlightColor(temperature, amount = 0.7) {
  const c = blackbody(temperature), s = blackbody(5772), r = c.map((v, i) => mix(1, v / Math.max(s[i], 1e-4), amount)), l = lum(r);
  return r.map((v) => v / l);
}

/** The options of a star in full, checked: `what` a name of STARS or an options object, `extra` over it. */
export function resolveStar(what = "sun", extra = {}) {
  let base = {};
  if (typeof what === "string") {
    const key = what.toLowerCase();
    if (!(key in STARS)) throw fail(`no star "${what}"${hint(key, Object.keys(STARS))}; stars: ${Object.keys(STARS).join(", ")} (or give options: {temperature, seed, ...})`);
    base = {...STARS[key], name: key};
  } else if (what && typeof what === "object" && !Array.isArray(what)) base = {...what};
  else throw fail(`a star is a name of STARS or an options object, got ${JSON.stringify(what)}`);
  const keys = Object.keys(STAR_DEFAULTS);
  known("star options", base, [...keys, "like"]);
  known("star options", extra, [...keys, ...STAR_CONTROL]);
  if (base.like !== undefined) {
    if (!(String(base.like) in STARS)) throw fail(`like: no star "${base.like}"${hint(base.like, Object.keys(STARS))}`);
    base = {...STARS[base.like], ...base}; delete base.like;
  }
  const o = {...STAR_DEFAULTS, ...base};
  for (const k of keys) if (extra[k] !== undefined) o[k] = extra[k];
  number("temperature", o.temperature, 1700, 40000); number("light", o.light, 0, 64); number("saturation", o.saturation, 0, 3);
  number("granulation", o.granulation, 0, 3); number("cells", o.cells, 4, 120); number("boil", o.boil, 0, 20);
  if (!Number.isInteger(o.spots) || o.spots < 0 || o.spots > MAX_SPOTS) throw fail(`spots must be a whole number from 0 to ${MAX_SPOTS}, got ${JSON.stringify(o.spots)}`);
  if (!Number.isInteger(o.prominences) || o.prominences < 0 || o.prominences > MAX_LOOPS) throw fail(`prominences must be a whole number from 0 to ${MAX_LOOPS}, got ${JSON.stringify(o.prominences)}`);
  number("spotSize", o.spotSize, 0.2, 5); number("faculae", o.faculae, 0, 4); number("limb", o.limb, 0, 1.6); number("corona", o.corona, 0, 8);
  number("reach", o.reach, 1, 20); number("streamers", o.streamers, 0, 3); number("spin", o.spin, -1e9, 1e9); number("tilt", o.tilt, -180, 180);
  number("glare", o.glare, 0, 8); number("spikeAngle", o.spikeAngle, -360, 360); number("spikeLength", o.spikeLength, 0.1, 6); number("flare", o.flare, 0, 4);
  if (![0, 4, 6, 8].includes(o.spikes)) throw fail(`spikes must be 0, 4, 6 or 8, got ${JSON.stringify(o.spikes)}`);
  choice("quality", o.quality, QUALITIES); choice("display", o.display, ["auto", "linear", "display"]);
  number("angularRadius", o.angularRadius, 0.001, 45);
  if (o.direction !== null && !(isVec(o.direction) && len(o.direction) > 0) && !(o.direction && o.direction.isVector3)) throw fail(`direction must be [x, y, z] (towards the star, the scene's axes), got ${JSON.stringify(o.direction)}`);
  if (!Number.isInteger(o.seed)) throw fail(`seed must be a whole number, got ${JSON.stringify(o.seed)}`);
  return o;
}

/** The spots of a star from its seed: [x, y, z, radius] (unit vectors in the star's axes, radians), in two
 * belts of latitude, some in pairs along a parallel as real groups are. */
export function starSpots(seed, count, size = 1) {
  const r = rng(seed * 7919 + 17), out = [];
  while (out.length < count) {
    const lat = (8 + 22 * r()) * (r() < 0.5 ? -1 : 1) * RAD, lon = r() * TAU, radius = (0.04 + 0.06 * r() * r()) * size;
    const at = (la, lo) => [Math.cos(la) * Math.cos(lo), Math.sin(la), -Math.cos(la) * Math.sin(lo)];
    out.push([...at(lat, lon), radius]);
    if (out.length < count && r() < 0.6) out.push([...at(lat + (r() - 0.5) * 0.06, lon + radius * (2.6 + 1.5 * r())), radius * (0.45 + 0.35 * r())]);
  }
  return out;
}
/** The loops of gas at a star's limb from its seed: {foot: unit vector, along: unit tangent, radius, sink, phase}
 * (a circle of `radius` star radii standing in the plane of `foot` and `along`, its middle `sink` radii of its
 * own under or over the surface). */
export function starLoops(seed, count) {
  const r = rng(seed * 104729 + 5), out = [];
  for (let i = 0; i < count; i++) {
    const lat = (10 + 35 * r()) * (r() < 0.5 ? -1 : 1) * RAD, lon = r() * TAU;
    const foot = [Math.cos(lat) * Math.cos(lon), Math.sin(lat), -Math.cos(lat) * Math.sin(lon)];
    const a = r() * TAU, east = unit(cross([0, 1, 0], foot)), north = cross(foot, east);
    const along = unit([east[0] * Math.cos(a) + north[0] * Math.sin(a), east[1] * Math.cos(a) + north[1] * Math.sin(a), east[2] * Math.cos(a) + north[2] * Math.sin(a)]);
    out.push({foot, along, radius: 0.05 + 0.11 * r() * r(), sink: -0.35 + 0.8 * r(), phase: r() * TAU});
  }
  return out;
}

// gradient noise for the corona's map (made once in JavaScript: the same on every GPU)
function lattice(x, y, z, seed) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 2147483647) ^ Math.imul(seed, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16;
  return h;
}
function noise3(x, y, z, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), fx = x - xi, fy = y - yi, fz = z - zi;
  const u = fx * fx * fx * (fx * (fx * 6 - 15) + 10), v = fy * fy * fy * (fy * (fy * 6 - 15) + 10), w = fz * fz * fz * (fz * (fz * 6 - 15) + 10);
  let total = 0;
  for (let c = 0; c < 8; c++) {
    const dx = c & 1, dy = (c >> 1) & 1, dz = (c >> 2) & 1, h = lattice(xi + dx, yi + dy, zi + dz, seed);
    const g = ((h & 1) ? 1 : -1) * (fx - dx) + ((h & 2) ? 1 : -1) * (fy - dy) + ((h & 4) ? 1 : -1) * (fz - dz);
    total += g * (dx ? u : 1 - u) * (dy ? v : 1 - v) * (dz ? w : 1 - w);
  }
  return total * 0.72;                                                   // about -1 to 1
}
// a cube face's direction as OpenGL addresses it (face 0..5 = +x -x +y -y +z -z; u, v from -1 to 1)
const FACE = [(u, v) => [1, -v, -u], (u, v) => [-1, -v, u], (u, v) => [u, 1, v], (u, v) => [u, -1, -v], (u, v) => [u, -v, 1], (u, v) => [-u, -v, -1]];
/** The corona's map: six faces of `size` x `size` RGBA bytes read by direction from the star's middle. R: where
 * the great streamers stand (0 to 1), G: finer structure, B: thin rays, A: where the surface is active. */
export function coronaFaces(seed, size = CORONA_SIZE, streamers = 1) {
  const faces = [], f = 1.25 + 0.75 * streamers;
  for (let face = 0; face < 6; face++) {
    const data = new Uint8Array(size * size * 4);
    for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) {
      const d = unit(FACE[face]((2 * i + 1) / size - 1, (2 * j + 1) / size - 1)), k = (j * size + i) * 4;
      const belt = 1 - Math.abs(d[1]);                                   // streamers gather over the belts of activity
      const big = noise3(d[0] * f + 3.1, d[1] * f * 1.5 + 7.7, d[2] * f + 1.3, seed) + 0.5 * noise3(d[0] * f * 2.3, d[1] * f * 2.3, d[2] * f * 2.3, seed + 1);
      const fine = noise3(d[0] * 5.5, d[1] * 5.5, d[2] * 5.5, seed + 2) + 0.5 * noise3(d[0] * 11, d[1] * 11, d[2] * 11, seed + 3);
      const rays = noise3(d[0] * 19, d[1] * 19, d[2] * 19, seed + 4) + 0.7 * noise3(d[0] * 43, d[1] * 43, d[2] * 43, seed + 5);
      const active = noise3(d[0] * 2.6 + 9.1, d[1] * 3.4, d[2] * 2.6, seed + 6);
      data[k] = 255 * clamp01(0.42 + 0.95 * big + 0.22 * (belt - 0.5));
      data[k + 1] = 255 * clamp01(0.5 + 0.8 * fine);
      data[k + 2] = 255 * clamp01(0.5 + 0.75 * rays);
      data[k + 3] = 255 * clamp01(0.5 + 1.1 * active * smooth(0.15, 0.55, belt));
    }
    faces.push(data);
  }
  return faces;
}

// ---------- what hides the sun ----------
const SAMPLES = 96;
const DISC = Array.from({length: SAMPLES}, (_, i) => { const r = Math.sqrt((i + 0.5) / SAMPLES), a = i * 2.39996323; return [r * Math.cos(a), r * Math.sin(a)]; });
/** The air of a tangent ray passing `h` radii above a body's ground, in zenith columns (Chapman's function at the
 * horizon, as vidgen/space-bodies' shader), for a scale height of `height` radii. */
export const tangentColumn = (h, height) => Math.sqrt(TAU * (1 + Math.max(h, 0)) / height) * Math.exp(-Math.max(h, -4 * height) / height);
/** How much of a sun's disc is seen past the bodies in front of it. `toSun`: the vector to the sun's middle,
 * `sunRadius` its radius (the same units), `occluders`: [{at: [x, y, z] (from the same eye), radius, air}], `air`
 * null or {height (radii), ext: [r, g, b] zenith optical depths}; `right`, `up`: two directions of the eye's own
 * (the frame's x and y) for the offset. Returns {fraction: [r, g, b] (1 = all of it, each colour dimmed by the air
 * it passes), offset: [x, y] (where the middle of the light that is left lies, in sun radii along right and up),
 * covered: the share of the disc behind solid ground}. The disc is 96 fixed points, each as wide as its share,
 * so the answer changes smoothly as a limb crosses; rays are straight (the air's bending is left out). */
export function sunVisibility(toSun, sunRadius, occluders = [], right = [1, 0, 0], up = [0, 1, 0]) {
  const D = len(toSun), s = unit(toSun);
  let ex = unit(cross(cross(s, right), s)), ey = cross(s, ex);
  if (dot(ey, up) < 0) ey = ey.map((v) => -v);
  if (!Number.isFinite(ex[0]) || len(ex) < 0.5) { ex = unit(cross(up, s)); ey = cross(s, ex); }
  const alpha = Math.min(sunRadius / Math.max(D, 1e-30), 1), near = occluders.filter((o) => dot(o.at, s) > 0 && dot(o.at, s) < D && o.radius > 0);
  if (!near.length) return {fraction: [1, 1, 1], offset: [0, 0], covered: 0};
  const total = [0, 0, 0], centre = [0, 0];
  let weight = 0, solid = 0;
  for (const [a, b] of DISC) {
    const d = unit([s[0] + alpha * (a * ex[0] + b * ey[0]), s[1] + alpha * (a * ex[1] + b * ey[1]), s[2] + alpha * (a * ex[2] + b * ey[2])]);
    const T = [1, 1, 1];
    let open = 1;
    for (const o of near) {
      const along = dot(o.at, d);
      if (along <= 0) continue;
      const miss = Math.sqrt(Math.max(dot(o.at, o.at) - along * along, 0)) / o.radius;      // the ray's nearest point, in the body's radii
      const soft = Math.max(alpha * along / o.radius * 1.1 / Math.sqrt(SAMPLES), 1e-9);  // a point's own width there
      const clear = smooth(1 - soft, 1 + soft, miss);
      open *= clear;
      for (let c = 0; c < 3; c++) T[c] *= clear * (o.air ? Math.exp(-o.air.ext[c] * tangentColumn(miss - 1, o.air.height)) : 1);
    }
    solid += 1 - open;
    const w = lum(T);
    for (let c = 0; c < 3; c++) total[c] += T[c];
    centre[0] += w * a; centre[1] += w * b; weight += w;
  }
  return {fraction: total.map((v) => v / SAMPLES), offset: weight > 1e-9 ? [centre[0] / weight, centre[1] / weight] : [0, 0], covered: solid / SAMPLES};
}

/** How far away (scene units) a sun given as a direction is put when worlds are tested for standing before it. */
export const SKY_SUN = 1e20;

// ---------- photometry ----------
/** The share of a full disc's light a round, matt body shows at phase angle `phase` (radians; 0 = full). */
export const phaseLight = (phase) => (Math.sin(phase) + (Math.PI - phase) * Math.cos(phase)) / Math.PI;
/** Planet-shine, honestly: the light a world of `radius` and mean albedo `albedo` (0 to 1), `distance` away and at
 * phase angle `phase` (radians, 0 = seen full) throws on a surface facing it, as a share of the sunlight that
 * world itself gets. A matt sphere: (2/3) albedo (radius / distance)^2 phaseLight; close to the ground it
 * stays under albedo (the light of an endless lit plain). The full Earth on the Moon: 5.5e-5. */
export function planetShine(albedo, radius, distance, phase) {
  const size = Math.min(1, radius / Math.max(distance, radius));
  return Math.min(albedo, (2 / 3) * albedo * size * size * phaseLight(phase) * (1 + 0.5 * size * size));
}
/** Ring-shine, honestly: the light a planet's own rings throw on its night side as a share of the sunlight, for
 * rings of mean `opacity` (0 to 1) lit at `elevation` radians (the sun's height over their plane). A flat
 * estimate: half the grains' light comes back (albedo 0.5), a quarter of the sky is ring. */
export const ringShine = (opacity, elevation) => 0.125 * clamp01(opacity) * Math.abs(Math.sin(elevation));
/** The film convention for a faint second light: `honest` (a share of sunlight) to what is drawn. 0.236 x
 * honest^0.158: the full Earth on the Moon (5.5e-5) becomes 0.05, a low orbit's ground-shine (0.18) stays 0.18;
 * lights fainter than a full Moon's on the Earth (2.5e-6) fade out (x honest / (honest + 2e-6)). */
export const filmShine = (honest) => (honest <= 0 ? 0 : 0.236 * Math.pow(honest, 0.158) * honest / (honest + 2e-6));
/** Sunlight at `distance` relative to that at `reference`: (reference / distance)^falloff. `falloff` 2 is the
 * inverse-square law, 0 (the default of spaceLight) lights every world as if exposed for it. */
export const sunlight = (distance, reference, falloff = 2) => (falloff === 0 ? 1 : Math.pow(reference / Math.max(distance, 1e-30), falloff));
/** What each kind of light is multiplied by. `film`: nothing is changed and planet-shine is lifted. Otherwise
 * honest: every light 2^ev (spaceLight then holds each at BURN times white at most), the sky 2^(ev - SKY_STOPS)
 * of its brightness (at most 1), city lights 2^(ev - LIGHTS_STOPS) (at most 1), planet-shine as faint as it is. */
export function exposureGains(mode, ev = 0) {
  choice("exposure", mode, EXPOSURES);
  if (mode === "film") return {sun: 1, sky: 1, lights: 1, film: true, ev: 0};
  return {sun: Math.pow(2, ev), sky: Math.min(1, Math.pow(2, ev - SKY_STOPS)), lights: Math.min(1, Math.pow(2, ev - LIGHTS_STOPS)), film: false, ev};
}
/** The automatic exposure (stops over a sunlit ground's): `entries` are the lit things in the frame, each {ev:
 * the stops it wants, share: the share of the frame it covers}. From `evMax` (nothing lit: the stars' own
 * exposure) every entry pulls the exposure to its own, the brightest last, by how much of the frame it covers:
 * not at all under `dark` (2e-4 of the frame: a disc 6 px in radius at 720p), wholly from `day` (0.02: a fiftieth of
 * the frame), as a light meter that reads the whole frame lets a thin crescent burn out to show the dark side. */
export function autoExposure(entries, {evMax = SKY_STOPS, day = 0.02, dark = 2e-4} = {}) {
  let ev = evMax;
  for (const e of [...entries].sort((a, b) => b.ev - a.ev)) {
    const w = e.share > 0 ? smooth(Math.log10(dark), Math.log10(day), Math.log10(e.share)) : 0;
    ev = mix(ev, Math.min(Math.max(e.ev, 0), evMax), w);
  }
  return ev;
}

// ---------- shaders ----------
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
const SHARED = /* glsl */`
precision highp float;
uniform float uDisplay;
${TONE}
float dither(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 display(vec3 c) {
  c = clamp(ACESFilmicToneMapping(max(c, 0.0)), 0.0, 1.0);
  c = mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
  return c + (dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0) / 255.0;
}
vec4 put(vec3 col, float alpha) { return vec4(uDisplay < 0.5 ? col : display(col), alpha); }
`;
const SHELL_VERT = /* glsl */`
uniform float uGrow; varying vec3 vObj;
void main() {
  vObj = position * uGrow;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(vObj, 1.0);
  gl_Position.z = min(gl_Position.z, gl_Position.w * 0.99999);
}`;
// the corona: everything is a function of where the view ray passes nearest the star (its direction from the
// middle reads the map, its distance sets the fall-off), so streamers are straight rays that thin outward
const CORONA_FRAG = /* glsl */`
${SHARED}
varying vec3 vObj;
uniform vec3 uCam, uTint; uniform samplerCube uMap; uniform vec4 uCorona;   // strength, reach (radii), streamers, fade to a point
void main() {
  vec3 ro = uCam, rd = normalize(vObj - uCam);
  float tm = -dot(ro, rd);
  vec3 q = ro + rd * tm;
  float b = max(length(q), 1.0), lb = log(b);
  vec3 axis = normalize(ro);
  vec3 round_ = normalize(q - axis * dot(q, axis) + 1e-6);           // the angle round the disc only: rays stay rays in any lens
  vec4 m0 = textureCube(uMap, round_);
  // a streamer leans a little as it leaves: the angle it is read at drifts with the distance
  vec4 m = textureCube(uMap, round_ + cross(axis, round_) * (m0.g - 0.5) * 0.5 * (1.0 - 1.0 / b));
  float s = clamp(m.r + 0.35 * (m.g - 0.5) * smoothstep(0.0, 0.6, lb), 0.0, 1.0);
  float streamer = pow(s, 1.0 + 2.6 * lb);                           // a streamer narrows to a stalk as it leaves
  float rays = 1.0 + (m.b - 0.5) * 1.5 * smoothstep(0.0, 0.3, lb);
  float inner = pow(b, -11.0) * (0.75 + 0.5 * m.g);                  // the bright ring that hugs the limb
  float outer = pow(b, -3.0 - 1.6 * (1.0 - s)) * (0.02 + 0.7 * uCorona.z * streamer * streamer * (3.0 - 2.0 * streamer) + 0.02 * s) * rays;
  float edge = 1.0 - smoothstep(0.55, 1.0, (b - 1.0) / uCorona.y);
  float I = uCorona.x * (0.42 * inner + outer) * edge * edge * step(0.0, tm) * (1.0 - uCorona.w);
  // pearl white with the star's own colour near the limb
  vec3 col = mix(uTint, vec3(0.93, 0.97, 1.0), 0.72 + 0.28 * smoothstep(0.0, 0.9, lb)) * I;
  if (I <= 0.0) discard;
  gl_FragColor = put(col, 0.0);
}`;
// the surface: cells that turn in place (gradient noise whose gradients turn with time), spots, faculae, limb
const STAR_FRAG = /* glsl */`
${SHARED}
varying vec3 vObj;
uniform vec3 uCam, uColor, uLimb, uOff, uPromColor; uniform samplerCube uMap;
uniform vec4 uViewZ; uniform vec2 uProj; uniform float uPix, uTime, uFar, uPoint;
uniform vec4 uSurface;        // light, granulation, cells across a radius, faculae
uniform vec4 uSpots[SPOTS];   // middle (unit), radius (radians)
uniform vec4 uLoopA[LOOPS], uLoopB[LOOPS];   // foot (unit), radius; tangent (unit), sink
uniform vec2 uLoopC[LOOPS];   // phase, strength
float depthOf(vec3 p) { float z = dot(uViewZ, vec4(p, 1.0)); return clamp(0.5 - 0.5 * (uProj.x * z + uProj.y) / z, 0.0, 1.0); }
vec3 hash3(vec3 p) { p = fract(p * vec3(0.1031, 0.1030, 0.0973)); p += dot(p, p.yxz + 33.33); return fract((p.xxy + p.yxx) * p.zyx); }
// gradient noise whose every gradient turns about an axis at its own rate: the pattern changes in place
float flow(vec3 x, float t) {
  vec3 i = floor(x), f = x - i, w = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float n = 0.0;
  for (int c = 0; c < 8; c++) {
    vec3 o = vec3(float(c & 1), float((c >> 1) & 1), float((c >> 2) & 1)), h = hash3(i + o);
    float a = 6.2832 * h.x + t * (0.6 + 0.8 * h.z), z = 2.0 * h.y - 1.0, r = sqrt(1.0 - z * z);
    vec3 k = mix(1.0 - w, w, o);
    n += dot(vec3(r * cos(a), r * sin(a), z), f - o) * k.x * k.y * k.z;
  }
  return n * 1.5;
}
// the cells: the nearest and second nearest of points that each circle slowly about their place, so every
// cell changes shape where it stands. Returns (distance to the nearest, the lane between the two, the cell's own number)
vec3 cells(vec3 x, float t) {
  vec3 base = floor(x - 0.5);
  float f1 = 9.0, f2 = 9.0, id = 0.0;
  for (int c = 0; c < 8; c++) {
    vec3 cell = base + vec3(float(c & 1), float((c >> 1) & 1), float((c >> 2) & 1)), h = hash3(cell);
    float a = 6.2832 * h.x + t * (0.5 + 0.9 * h.z), a2 = 6.2832 * h.y + t * (0.35 + 0.5 * h.x);
    vec3 at = cell + 0.5 + 0.3 * vec3(cos(a), sin(a) * cos(a2), sin(a2));
    float d = length(x - at);
    if (d < f1) { f2 = f1; f1 = d; id = h.z; } else if (d < f2) f2 = d;
  }
  return vec3(f1, f2 - f1, id);
}
void main() {
  vec3 ro = uCam, rd = normalize(vObj - uCam);
  float tm = -dot(ro, rd), b2 = dot(ro, ro) - tm * tm, b = sqrt(max(b2, 0.0));
  float px = uPix * max(tm, 1e-9);
  float cover = clamp(0.5 + (1.0 - b) / px, 0.0, 1.0) * step(0.0, tm) * (1.0 - uPoint);
  float th = tm - sqrt(max(1.0 - b2, 0.0));
  vec3 p = normalize(ro + rd * th);
  float mu = sqrt(max(1.0 - min(b2, 1.0), 0.0));                      // the cosine between the view and the ground's normal
  vec4 m = textureCube(uMap, p);
  float cell = 1.0 / uSurface.z, seen = smoothstep(1.3, 3.5, cell * (0.35 + 0.65 * mu) / px);   // cells smaller than a pixel or two are left out
  vec3 g = cells(p * uSurface.z + uOff + (m.rgb - 0.5) * 2.2, uTime);   // the map pushes the cells about: larger here, smaller there
  float n1 = (g.z - 0.5) * 1.2;
#ifdef FINE
  float n2 = flow(p * uSurface.z * 0.29 + uOff.zxy, uTime * 0.4);
#else
  float n2 = m.g * 1.4 - 0.7;
#endif
  float act = m.a * 2.0 - 1.0;
  float lanes = 1.0 - pow(smoothstep(0.0, 0.42 + 0.25 * g.z, g.y), 1.2);   // the dark lanes between the cells: soft, widest where three meet
  float bright = 1.0 + uSurface.y * ((0.16 * n1 + 0.08 * (1.0 - 2.2 * g.x * g.x) - 0.36 * lanes) * (0.75 + 0.5 * n2) * seen + 0.10 * n2 + 0.05 * act);
  float near = 0.0;
  for (int i = 0; i < SPOTS; i++) {
    float d = length(p - uSpots[i].xyz), r = uSpots[i].w * (1.0 + 0.32 * n2 + 0.12 * n1 * seen);
    float pen = 1.0 - smoothstep(0.82 * r, r, d), umbra = 1.0 - smoothstep(0.36 * r, 0.52 * r, d);
    bright *= mix(1.0, mix(0.6 + 0.16 * n1 * seen, 0.16, umbra), pen);
    near = max(near, (1.0 - smoothstep(r, 3.6 * r, d)) * (1.0 - pen));
  }
  // faculae: a bright net round the spots and over act ground, seen where the limb is dark
  float net = smoothstep(0.1, 0.5, abs(n2)) * (0.6 + 0.4 * smoothstep(0.0, 0.3, abs(n1)));
  bright += uSurface.w * 0.42 * max(near, smoothstep(0.25, 0.7, act)) * net * pow(1.0 - mu, 1.3);
  vec3 dark = pow(vec3(max(mu, 0.02)), uLimb);                        // the limb: darker, and redder (blue darkens most)
  vec3 col = uColor * uSurface.x * dark * pow(vec3(max(bright, 0.0)), vec3(0.8, 1.0, 1.3));
  // loops of gas: where the view ray crosses each loop's plane, how far from its circle
  vec3 prom = vec3(0.0);
  float hit = step(b2, 1.0) * step(0.0, tm);
  for (int i = 0; i < LOOPS; i++) {
    vec3 u = uLoopA[i].xyz, tg = uLoopB[i].xyz, nrm = cross(u, tg);
    float R = uLoopA[i].w, dn = dot(rd, nrm), tq = dot(u * (1.0 + R * uLoopB[i].w) - ro, nrm) / (abs(dn) > 1e-3 ? dn : 1e-3);
    vec3 at = ro + rd * tq, q = at - u * (1.0 + R * uLoopB[i].w);
    float ang = atan(dot(q, tg), dot(q, u)), wisp = 0.55 + 0.45 * sin(ang * 5.0 + uLoopC[i].x + 0.25 * uTime) * sin(ang * 13.0 - uLoopC[i].x * 3.0);
    float wide = R * (0.10 + 0.05 * wisp) / max(abs(dn), 0.35) + px, d = abs(length(q) - R);
    float glow = exp(-d * d / (wide * wide)) + 0.35 * exp(-d * d / (wide * wide * 9.0));
    glow *= step(0.0, tq) * mix(1.0, 0.25 * step(tq, th), hit) * smoothstep(1.0, 1.0 + 0.3 * wide, length(at));   // before the disc a loop is nearly lost in its light
    prom += uPromColor * uLoopC[i].y * glow * wisp * min(1.0 / max(abs(dn), 0.4), 2.5);
  }
  prom *= 1.0 - uPoint;
  // a thin red rim of low gas just over the limb
  prom += uPromColor * 0.4 * exp(-max(b - 1.0, 0.0) / (0.006 + px)) * (1.0 - cover) * step(0.0, tm) * (0.6 + 0.8 * m.b) * (1.0 - uPoint);
  if (cover <= 0.0 && dot(prom, vec3(1.0)) <= 1e-5) discard;
  gl_FragDepth = uFar > 0.5 ? 0.9999999 : depthOf(ro + rd * (cover > 0.0 ? th : tm));
  gl_FragColor = put(col * cover + prom, cover);
}`;
// the glare of a small sun: drawn last, over everything, in the frame's own axes (a lens does not turn with the world)
const GLARE_VERT = /* glsl */`
attribute vec4 aGhost;                 // 0 for the glow; a ghost: its place along the axis, its radius (half frame heights), ring, tint
uniform vec2 uSun, uAspect; uniform float uSize;
varying vec2 vQ; varying vec4 vGhost; varying float vSize;
void main() {
  vGhost = aGhost;
  float ghost = step(1e-6, abs(aGhost.x));
  vec2 centre = mix(uSun, uSun * aGhost.x, ghost);
  vSize = mix(uSize, aGhost.y, ghost);
  vQ = position.xy * vSize;
  gl_Position = vec4((centre + vQ) * uAspect, 0.0, 1.0);
}`;
const GLARE_FRAG = /* glsl */`
${SHARED}
varying vec2 vQ; varying vec4 vGhost; varying float vSize;
uniform vec3 uLight, uTint; uniform vec4 uShape;   // half the frame's height in pixels, the disc's radius (px), the spikes' length (px), flare
uniform vec2 uSpike[4]; uniform float uSpikes, uFlare;
void main() {
  float half_ = uShape.x, k = half_ / 360.0, r = length(vQ) * half_, rho = uShape.y;
  vec3 col;
  if (abs(vGhost.x) < 1e-6) {
    float sigma = max(max(0.95 * k, 0.72 * rho), 0.62), r1 = 2.6 * k + 1.1 * rho, r2 = 16.0 * k + 2.0 * rho, r3 = 90.0 * k + 3.0 * rho;
    float core = 34.0 * exp(-0.5 * r * r / (sigma * sigma));
    float halo = 2.6 / pow(1.0 + r * r / (r1 * r1), 1.5) + 0.7 / pow(1.0 + r * r / (r2 * r2), 1.25) + 0.075 / (1.0 + r * r / (r3 * r3));
    float spikes = 0.0;
    for (int i = 0; i < 4; i++) {
      float along = abs(dot(vQ, uSpike[i])) * half_, across = abs(vQ.x * uSpike[i].y - vQ.y * uSpike[i].x) * half_;
      float thin = max(0.8 * k, 0.62), w = thin + 0.5 * rho * exp(-along / (6.0 * k + 3.0 * rho));   // never thinner than a star's spot: a thinner line would break into dots
      float len = uShape.z * (i == 0 ? 1.0 : (i == 1 ? 0.78 : (i == 2 ? 0.9 : 0.7)));
      spikes += step(float(i) + 0.5, uSpikes) * exp(-0.5 * across * across / (w * w)) * (0.8 * k / thin) / (1.0 + along * along / (len * len)) * smoothstep(0.0, 2.0 * k + rho, along);
    }
    float window = 1.0 - smoothstep(0.6, 1.0, length(vQ) / vSize);
    col = (vec3(core) + mix(vec3(1.0), uTint, 0.2) * halo + 1.3 * spikes) * window;
  } else {
    // a lens ghost: a soft round patch, some a thin ring; never an aperture's hexagon
    float q = length(vQ) / vSize, body = 1.0 - smoothstep(0.45, 1.0, q), ring = smoothstep(0.35, 0.85, q) * (1.0 - smoothstep(0.85, 1.0, q));
    vec3 tint = vGhost.w < 0.5 ? vec3(0.55, 0.8, 1.0) : (vGhost.w < 1.5 ? vec3(0.78, 0.72, 1.0) : vec3(0.6, 1.0, 0.88));   // cool tints: a warm one reads as dirt on the dark
    col = mix(tint, vec3(1.0), 0.25) * mix(body * (0.55 + 0.45 * q * q), 0.45 * body + 0.55 * ring, vGhost.z) * 0.022 * uFlare;
  }
  col *= uLight;
  if (dot(col, vec3(1.0)) <= 1e-5) discard;
  gl_FragColor = put(col, 1.0);
}`;
// the ghosts: [place along the axis from the sun (1) through the middle (0), radius, ring, tint]
const GHOSTS = [[0.42, 0.045, 0, 0], [-0.28, 0.022, 0, 1], [-0.6, 0.07, 1, 2], [-0.95, 0.035, 0, 0], [-1.45, 0.16, 1, 1], [0.7, 0.014, 0, 2]];

const SHELL = {transparent: true, depthTest: true, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
  blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor, toneMapped: false, fog: false, side: THREE.BackSide};
/** How much of a spot a disc of `rho` pixels' radius is drawn as (as vidgen/space-bodies): 0 from 2.5 px up, 1 from 1.5 down. */
export const pointShare = (rho) => clamp01(2.5 - rho);
/** How much of its glare a sun of `rho` pixels' radius (at 720p) shows: all of it up to 30 px, none from 140 px (a close-up shows the surface). */
export const glareShare = (rho) => 1 - smooth(30, 140, rho);

// ---------- the star ----------
/** A star: `object` (a THREE.Group of radius 1; with `space` placed and sized, with `direction` in the sky),
 * update(t), `occluders` (what may hide it: bodies of vidgen/space-bodies), `seen` (after a draw: how much shows). */
export class Star {
  /** `renderer`: the page's; `what`: a name of STARS or options; `extra`: options over those, and `space` (a
   * vidgen/space-scale SpaceView: the star is the body of ctx.orbits called `body`, default the Sun), `orbits`. */
  constructor(renderer, what = "sun", extra = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("the first argument must be the page's THREE.WebGLRenderer");
    const o = this.options = resolveStar(what, extra);
    this.renderer = renderer;
    this.tint = starTint(o.temperature, o.saturation);
    /** The colour of this star's light on a white ground (linear, luminance 1). */
    this.lightColor = sunlightColor(o.temperature);
    this.infinite = o.direction !== null;
    /** Towards the star, for one in the sky (`direction`); the page may turn it. */
    this.direction = new THREE.Vector3(1, 0, 0);
    if (this.infinite) { if (o.direction.isVector3) this.direction.copy(o.direction); else this.direction.set(...o.direction); this.direction.normalize(); }
    /** The bodies that may stand before the star (each {object, options.air}); spaceLight sets it. */
    this.occluders = [];
    /** What every light of the star is multiplied by (an honest exposure's gain; spaceLight sets it). */
    this.gain = 1;
    /** After a draw: {fraction: [r, g, b], offset, covered, pixels: the disc's radius, inFrame}. */
    this.seen = {fraction: [1, 1, 1], offset: [0, 0], covered: 0, pixels: 0, inFrame: false};
    this._scratch = {inv: new THREE.Matrix4(), mv: new THREE.Matrix4(), view: new THREE.Vector4(), cam: new THREE.Vector3(), dir: new THREE.Vector3(), p: new THREE.Vector3(), q: new THREE.Vector3()};
    const faces = coronaFaces(o.seed, CORONA_SIZE, o.streamers).map((data) => { const t = new THREE.DataTexture(data, CORONA_SIZE, CORONA_SIZE, THREE.RGBAFormat); t.needsUpdate = true; return t; });
    this.map = new THREE.CubeTexture(faces);
    this.map.generateMipmaps = true; this.map.minFilter = THREE.LinearMipmapLinearFilter; this.map.magFilter = THREE.LinearFilter; this.map.needsUpdate = true;
    const r = rng(o.seed * 31 + 3), v3 = (a) => new THREE.Vector3(...a);
    const spots = starSpots(o.seed, o.spots, o.spotSize), loops = starLoops(o.seed, o.prominences);
    const pad = (list, n, make) => Array.from({length: Math.max(n, 1)}, (_, i) => make(list[i]));
    const display = this.display = {value: 0};
    // blue darkens most toward the limb; a hot star's limb darkens less
    // a cool star's limb reddens (blue darkens most); a hot star's is drawn the other way: white-hot middle, blue limb
    const warm = smooth(9000, 5800, o.temperature);
    const limb = [mix(1.0, 0.3, warm), mix(0.66, 0.55, warm), mix(0.3, 0.95, warm)].map((u) => u * o.limb);
    this.uniforms = {
      uDisplay: display, uCam: {value: new THREE.Vector3()}, uColor: {value: v3(this.tint)}, uLimb: {value: v3(limb)}, uOff: {value: new THREE.Vector3(r() * 50, r() * 50, r() * 50)},
      uPromColor: {value: new THREE.Vector3(1.0, 0.16, 0.2).multiplyScalar(1.15 * (0.12 + 0.88 * warm))}, uMap: {value: this.map},
      uViewZ: {value: new THREE.Vector4()}, uProj: {value: new THREE.Vector2()}, uPix: {value: 0.001}, uTime: {value: 0}, uFar: {value: this.infinite ? 1 : 0}, uPoint: {value: 0},
      uSurface: {value: new THREE.Vector4(o.light, o.granulation, o.cells, o.faculae)}, uGrow: {value: 1},
      uSpots: {value: pad(spots, o.spots, (s) => new THREE.Vector4(...(s ?? [0, 1, 0, 1e-5])))},
      uLoopA: {value: pad(loops, o.prominences, (l) => (l ? new THREE.Vector4(...l.foot, l.radius) : new THREE.Vector4(0, 1, 0, 0.01)))},
      uLoopB: {value: pad(loops, o.prominences, (l) => (l ? new THREE.Vector4(...l.along, l.sink) : new THREE.Vector4(1, 0, 0, 0)))},
      uLoopC: {value: pad(loops, o.prominences, (l) => (l ? new THREE.Vector2(l.phase, 0.7 + 0.6 * Math.abs(Math.sin(l.phase * 5))) : new THREE.Vector2(0, 0)))},
    };
    const top = 1 + (loops.length ? Math.max(...loops.map((l) => l.radius * (2.35 + l.sink))) : 0.03) + 0.02;
    this.uniforms.uGrow.value = top;
    const defines = {SPOTS: Math.max(o.spots, 1), LOOPS: Math.max(o.prominences, 1)};
    if (o.quality === "standard") defines.FINE = 1;
    this.material = new THREE.ShaderMaterial({...SHELL, uniforms: this.uniforms, defines, vertexShader: SHELL_VERT, fragmentShader: STAR_FRAG, depthWrite: true});
    this.coronaUniforms = {uDisplay: display, uCam: this.uniforms.uCam, uTint: {value: v3(this.tint)}, uMap: {value: this.map}, uCorona: {value: new THREE.Vector4(o.corona, o.reach, o.streamers, 0)}, uGrow: {value: 1 + o.reach}};
    this.coronaMaterial = new THREE.ShaderMaterial({...SHELL, uniforms: this.coronaUniforms, vertexShader: SHELL_VERT, fragmentShader: CORONA_FRAG, depthWrite: false});
    this.geometry = new THREE.SphereGeometry(1, 40, 20);
    this.geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), top);
    this.coronaGeometry = new THREE.SphereGeometry(1, 40, 20);
    this.coronaGeometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1 + o.reach);
    // drawn in the order made: the corona, then the globe over it
    this.corona = new THREE.Mesh(this.coronaGeometry, this.coronaMaterial);
    this.mesh = new THREE.Mesh(this.geometry, this.material);
    this.corona.visible = o.corona > 0;
    this.spinner = new THREE.Group(); this.spinner.add(this.corona, this.mesh);
    this.object = new THREE.Group(); this.object.name = `star ${o.name ?? o.temperature}`; this.object.add(this.spinner);
    this.mesh.onBeforeRender = (rr, scene, camera) => this._before(rr, camera);
    this.corona.onBeforeRender = (rr, scene, camera) => this._before(rr, camera);   // drawn first: it sets what both share
    this._makeGlare();
    if (this.infinite) {
      // a star in the sky: all round the camera like the sky, drawn after it and before every body
      for (const m of [this.corona, this.mesh]) { m.frustumCulled = false; m.renderOrder = -900; }
    }
    this.material.addEventListener("dispose", () => this.map.dispose());
    this.space = extra.space ?? null;
    this.orbits = extra.orbits ?? (this.space ? this.space.orbits : null);
    this.body = null;
    if (this.orbits && !this.infinite) {
      const want = String(extra.body ?? "sun").toLowerCase();
      this.body = this.orbits.names.find((n) => n.toLowerCase() === want) ?? this.orbits.names.find((n) => (this.orbits.bodies[n].key ?? "").toLowerCase() === want) ?? null;
      if (!this.body) throw fail(`the orbit data has no body "${extra.body ?? "Sun"}"${hint(want, this.orbits.names)}; it has: ${this.orbits.names.join(", ")} (give {body: name}, or {direction} for a sun in the sky)`);
      if (this.space) this.space.add(this.object, {body: this.body, spin: false});
    } else if (extra.body !== undefined || (this.space && !this.infinite)) throw fail("space / body need orbit data: a web scene with orbit_data: (ctx.orbits)");
    this.update(0);
  }

  _makeGlare() {
    const o = this.options, n = 1 + GHOSTS.length, position = new Float32Array(n * 12), ghost = new Float32Array(n * 16), index = [];
    for (let q = 0; q < n; q++) {
      [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([x, y], c) => { position.set([x, y, 0], q * 12 + c * 3); ghost.set(q === 0 ? [0, 0, 0, 0] : GHOSTS[q - 1], q * 16 + c * 4); });
      index.push(q * 4, q * 4 + 1, q * 4 + 2, q * 4, q * 4 + 2, q * 4 + 3);
    }
    this.glareGeometry = new THREE.BufferGeometry();
    this.glareGeometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
    this.glareGeometry.setAttribute("aGhost", new THREE.BufferAttribute(ghost, 4));
    this.glareGeometry.setIndex(index);
    this.glareGeometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e-3);
    const lines = o.spikes / 2, a0 = o.spikeAngle * RAD;
    this.glareUniforms = {uDisplay: this.display, uSun: {value: new THREE.Vector2()}, uAspect: {value: new THREE.Vector2(1, 1)}, uSize: {value: 0.5}, uLight: {value: new THREE.Vector3()},
      uTint: {value: new THREE.Vector3(...starTint(o.temperature, 1))}, uShape: {value: new THREE.Vector4(360, 1, 60, 0)}, uSpikes: {value: lines}, uFlare: {value: o.flare},
      uSpike: {value: Array.from({length: 4}, (_, i) => new THREE.Vector2(Math.cos(a0 + Math.PI * i / Math.max(lines, 1)), Math.sin(a0 + Math.PI * i / Math.max(lines, 1))))}};
    this.glareMaterial = new THREE.ShaderMaterial({uniforms: this.glareUniforms, vertexShader: GLARE_VERT, fragmentShader: GLARE_FRAG, transparent: true, depthTest: false, depthWrite: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, toneMapped: false, fog: false, side: THREE.DoubleSide});
    /** The glare: a mesh drawn last, over everything (vidgen/space-scale draws it after its depth slices). */
    this.glare = new THREE.Mesh(this.glareGeometry, this.glareMaterial);
    this.glare.frustumCulled = false; this.glare.renderOrder = 10000; this.glare.userData.overlay = true;
    this.glare.onBeforeRender = (rr, scene, camera) => this._beforeGlare(rr, camera);
    this.glare.visible = o.glare > 0;
    this.object.add(this.glare);
  }

  // a star in the sky stands round the camera: its group is moved there before each draw
  _place(camera) {
    if (!this.infinite) return;
    const s = this._scratch;
    const far = Math.sqrt(camera.near * camera.far), size = far * Math.tan(this.options.angularRadius * RAD);
    s.cam.setFromMatrixPosition(camera.matrixWorld);
    this.object.position.copy(s.cam).addScaledVector(s.dir.copy(this.direction).normalize(), far);
    this.object.scale.setScalar(size);
    this.object.updateMatrixWorld(true);
  }

  /** The disc's radius in pixels for `camera` and a frame `height` pixels tall. */
  pixels(camera, height) {
    const s = this._scratch;
    let alpha = this.options.angularRadius * RAD;
    if (!this.infinite) { const d = this.object.getWorldPosition(s.p).distanceTo(s.cam.setFromMatrixPosition(camera.matrixWorld)), R = this.object.getWorldScale(s.q).x; alpha = d > R ? Math.asin(R / d) : Math.PI / 2; }
    return Math.tan(alpha) / Math.tan((camera.fov ?? 40) * RAD / 2) * height / 2;
  }

  _before(renderer, camera) {
    this._place(camera);
    const s = this._scratch, u = this.uniforms, mesh = this.mesh;
    renderer.getCurrentViewport(s.view);
    s.inv.copy(mesh.matrixWorld).invert();
    u.uCam.value.copy(s.cam.setFromMatrixPosition(camera.matrixWorld)).applyMatrix4(s.inv);
    s.mv.multiplyMatrices(camera.matrixWorldInverse, mesh.matrixWorld);
    const e = s.mv.elements, pe = camera.projectionMatrix.elements;
    u.uViewZ.value.set(e[2], e[6], e[10], e[14]); u.uProj.value.set(pe[10], pe[14]);
    const pix = 2 * Math.tan((camera.fov ?? 40) * RAD / 2) / s.view.w, dist = u.uCam.value.length();
    u.uPix.value = pix;
    const rho = 1 / (pix * Math.max(dist, 1e-9));
    u.uPoint.value = pointShare(rho);
    u.uSurface.value.x = this.options.light * this.gain;
    this.coronaUniforms.uCorona.value.set(this.options.corona * this.gain, this.options.reach, this.options.streamers, smooth(1.2, 0.5, rho));
    this.display.value = this.options.display === "auto" ? (renderer.getRenderTarget() === null ? 1 : 0) : (this.options.display === "display" ? 1 : 0);
    this.material.uniformsNeedUpdate = true; this.coronaMaterial.uniformsNeedUpdate = true;
  }

  /** How much of the star `camera` sees past `occluders` (default this.occluders), as sunVisibility, the offset
   * along the camera's right and up. */
  visibility(camera, occluders = this.occluders) {
    const s = this._scratch;
    this._place(camera);
    const e = camera.matrixWorld.elements, cam = s.cam.setFromMatrixPosition(camera.matrixWorld);
    const rel = (v) => [v.x - cam.x, v.y - cam.y, v.z - cam.z];
    let toSun = rel(this.object.getWorldPosition(s.p)), R = this.object.getWorldScale(s.q).x;
    if (this.infinite) { const far = 1e15; toSun = this.direction.toArray().map((x) => x * far); R = far * Math.tan(this.options.angularRadius * RAD); }   // a star in the sky is behind everything
    const list = occluders.map((b) => ({at: rel(b.object.getWorldPosition(s.p)), radius: b.object.getWorldScale(s.q).x, air: airOf(b)}));
    return sunVisibility(toSun, R, list, [e[0], e[1], e[2]], [e[4], e[5], e[6]]);
  }

  _beforeGlare(renderer, camera) {
    const s = this._scratch, o = this.options, u = this.glareUniforms;
    renderer.getCurrentViewport(s.view);
    const H = s.view.w, W = s.view.z, tan = Math.tan((camera.fov ?? 40) * RAD / 2);
    const seen = this.visibility(camera), rho = this.pixels(camera, H), k = H / 720;
    const v = this.object.getWorldPosition(s.p).applyMatrix4(camera.matrixWorldInverse);
    const front = v.z < 0;
    // the frame's own axes: y from -1 to 1 over the height, x over the width times the aspect
    const sx = front ? v.x / -v.z / tan : 0, sy = front ? v.y / -v.z / tan : 0, aspect = W / H;
    const shift = rho / (H / 2);
    u.uSun.value.set(sx + seen.offset[0] * shift, sy + seen.offset[1] * shift);
    u.uAspect.value.set(1 / aspect, 1);
    // the glare leaves with the sun: all of it while the sun is in the frame, none a third of a frame outside
    const out = Math.max(Math.abs(sx) / aspect, Math.abs(sy)), inFrame = front ? 1 - smooth(1.0, 1.35, out) : 0;
    const share = glareShare(rho / k) * o.glare * this.gain * inFrame;
    const f = seen.fraction, visible = lum(f);
    u.uLight.value.set(f[0], f[1], f[2]).multiplyScalar(share);
    // what is left of a covered disc is a smaller light: its core narrows with it
    u.uShape.value.set(H / 2, rho * Math.sqrt(clamp01(visible)), 42 * k * o.spikeLength * Math.pow(clamp01(visible), 0.35), 0);
    u.uSize.value = Math.min(1.6, (0.5 + 0.5 * o.spikeLength) * Math.pow(clamp01(visible * share), 0.22));
    u.uFlare.value = o.flare * (front ? 1 - smooth(0.85, 1.1, out) : 0);
    const canvas = this.options.display === "auto" ? renderer.getRenderTarget() === null : this.options.display === "display";
    this.display.value = canvas ? 1 : 0;
    // into a linear picture light adds; over a finished one it is laid on as a screen
    this.glareMaterial.blendSrc = canvas ? THREE.OneMinusDstColorFactor : THREE.OneFactor;
    this.glareMaterial.uniformsNeedUpdate = true;
    this.seen = {...seen, pixels: rho, inFrame: inFrame > 0};
  }

  /** The star at scene time `t` (seconds): the boiling of its cells, its turning; with orbit data its pole. */
  update(t) {
    const o = this.options;
    this.uniforms.uTime.value = t * o.boil;
    const q = this.orbits && this.body ? this.orbits.quaternion(this.body, t) : null;
    if (q) this.object.quaternion.set(q[0], q[2], -q[1], q[3]);
    else if (!this.infinite) this.object.rotation.set(0, 0, -o.tilt * RAD);
    this.spinner.rotation.set(0, o.spin !== 0 ? TAU * t / o.spin : 0, 0);
    return this;
  }

  /** Free the map, the materials and the geometries. */
  dispose() {
    this.object.removeFromParent();
    for (const x of [this.material, this.coronaMaterial, this.glareMaterial, this.geometry, this.coronaGeometry, this.glareGeometry, this.map]) x.dispose();
  }
}
/** A star: `star(renderer, "sun")`, `star(renderer, {temperature: 9000, seed: 4})`, `star(renderer, "sun", {direction})`, `star(renderer, "Sun", {space})`. */
export const star = (renderer, what = "sun", extra = {}) => new Star(renderer, what, extra);

// ---------- the light of a scene ----------
// a body's air for sunVisibility: its scale height and zenith optical depths
function airOf(body) {
  const air = body.options && body.options.air;
  if (!air) return null;
  return {height: air.height, ext: [0, 1, 2].map((i) => air.rayleigh[i] + air.haze[i] + air.absorb[i])};
}
// the mean colour of a body's ground (linear), read once from the smallest level of its baked map
function meanAlbedo(body) {
  if (isVec(body.albedo)) return body.albedo.slice();
  const maps = body.maps, renderer = body.renderer;
  if (!maps || !maps.A || !renderer) return [0.3, 0.3, 0.3];
  const target = new THREE.WebGLRenderTarget(1, 1, {type: THREE.UnsignedByteType, depthBuffer: false});
  const material = new THREE.ShaderMaterial({uniforms: {uA: {value: maps.A.texture}}, depthTest: false, depthWrite: false, toneMapped: false,
    vertexShader: "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `uniform samplerCube uA; void main() { vec3 c = vec3(0.0);
      c += textureCube(uA, vec3(1.0, 0.0, 0.0), 20.0).rgb + textureCube(uA, vec3(-1.0, 0.0, 0.0), 20.0).rgb + textureCube(uA, vec3(0.0, 1.0, 0.0), 20.0).rgb;
      c += textureCube(uA, vec3(0.0, -1.0, 0.0), 20.0).rgb + textureCube(uA, vec3(0.0, 0.0, 1.0), 20.0).rgb + textureCube(uA, vec3(0.0, 0.0, -1.0), 20.0).rgb;
      gl_FragColor = vec4(c / 6.0, 1.0); }`});
  const scene = new THREE.Scene(), quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material), camera = new THREE.Camera();
  quad.frustumCulled = false; scene.add(quad);
  const before = renderer.getRenderTarget(), face = renderer.getActiveCubeFace(), level = renderer.getActiveMipmapLevel();
  renderer.setRenderTarget(target); renderer.render(scene, camera);
  const px = new Uint8Array(4);
  renderer.readRenderTargetPixels(target, 0, 0, 1, 1, px);
  renderer.setRenderTarget(before, face, level);
  target.dispose(); material.dispose(); quad.geometry.dispose();
  let c = [px[0], px[1], px[2]].map((v) => (v / 255) * (v / 255));          // the map keeps the albedo's square root
  const o = body.options ?? {};
  if (body.material && body.material.defines && body.material.defines.CLOUDS && body.uniforms && body.uniforms.uCloudColor) {
    const cloud = body.uniforms.uCloudColor.value, k = Math.min(0.6, 0.9 * (o.clouds ?? 0.5));
    c = [mix(c[0], 0.8 * cloud.x, k), mix(c[1], 0.8 * cloud.y, k), mix(c[2], 0.8 * cloud.z, k)];
  }
  return c;
}

export const LIGHT_DEFAULTS = Object.freeze({scene: null, camera: null, renderer: null, sun: null, bodies: Object.freeze([]), sky: null, at: null, color: null, sunSize: SUN_ANGULAR_RADIUS / RAD,
  shine: 1, ringShine: 1, eclipses: false, falloff: 0, reference: null, exposure: "film", ev: 0, auto: Object.freeze({}), ambient: 0, environment: false, shadows: false});
const SHADOW_DEFAULTS = Object.freeze({size: 10, mapSize: 2048, bias: -0.0005});
const MAX_ECLIPSES = 4;
// the light the air of a world bends into its shadow: the copper of a lunar eclipse (film: lifted; honest: as faint as it is)
const UMBRA_FILM = [0.085, 0.022, 0.007], UMBRA_HONEST = [3e-4, 7e-5, 2e-5];

/** The light of a space scene. Options: `scene`, `camera` (the page's); `sun`: a Star, an Object3D standing where
 * the sun is (its scale the sun's radius), or a direction [x, y, z] towards the sun (the scene's axes); `bodies`: the worlds of vidgen/space-bodies; `sky`: the sky of
 * vidgen/space-sky (for honest exposures and `environment`); `at`: where the light for ordinary meshes is
 * worked out (an Object3D, default the camera); `color`: the sunlight's colour (default from the Star's
 * temperature, else white); `shine`, `ringShine`: how strong planet-shine and ring-shine are drawn (1; 0 off);
 * `eclipses`: other bodies' shadows on the bodies (true, or false); `falloff`: 0 (default: every world lit
 * as if exposed for it) to 2 (the inverse-square law) from the distance `reference` (a number in the scene's
 * units, a body, default the first body); `exposure`: "film" | "camera" | "auto"; `ev`: the camera's stops
 * over a sunlit ground's exposure (a number or a function of t); `auto`: {evMax, day, dark}; `ambient`
 * (0); `environment` (true: scene.environment = sky.environment); `shadows` (true or {size, mapSize, bias}:
 * the directional light casts shadows in a box of `size` round `at`); `sunSize` (degrees: a sun given as a
 * direction is this wide in angular radius, for the penumbras). */
export class SpaceLight {
  constructor(options = {}) {
    known("spaceLight options", options, Object.keys(LIGHT_DEFAULTS));
    const o = this.options = {...LIGHT_DEFAULTS, ...options};
    if (!o.scene || !o.scene.isScene) throw fail("spaceLight needs {scene}: the page's THREE.Scene");
    if (!o.camera || !o.camera.isCamera) throw fail("spaceLight needs {camera}: the page's camera");
    this.scene = o.scene; this.camera = o.camera;
    this.star = o.sun && o.sun instanceof Star ? o.sun : null;
    /** Where the sun stands, when it is a thing in the scene: the star's group, or the Object3D given as `sun`. */
    this.sunObject = this.star && !this.star.infinite ? this.star.object : (o.sun && o.sun.isObject3D ? o.sun : null);
    if (!this.star && !this.sunObject) {
      if (!(isVec(o.sun) && len(o.sun) > 0) && !(o.sun && o.sun.isVector3)) throw fail(`sun must be a star of this module, an Object3D standing where the sun is, or a direction [x, y, z] towards it, got ${JSON.stringify(o.sun ?? null)}`);
      /** Towards the sun, when it was given as a direction; the page may turn it. */
      this.direction = o.sun.isVector3 ? o.sun.clone().normalize() : new THREE.Vector3(...o.sun).normalize();
    }
    if (!Array.isArray(o.bodies) || o.bodies.some((b) => !b || !b.object || typeof b.setSun !== "function")) throw fail("bodies must be a list of bodies of vidgen/space-bodies (planet(...))");
    this.bodies = o.bodies.slice();
    number("shine", o.shine, 0, 8); number("ringShine", o.ringShine, 0, 8); number("falloff", o.falloff, 0, 2); number("ambient", o.ambient, 0, 4); number("sunSize", o.sunSize, 0, 45);
    choice("exposure", o.exposure, EXPOSURES);
    if (typeof o.ev !== "function") number("ev", o.ev, -8, 30);
    known("auto", o.auto, ["evMax", "day", "dark"]);
    if (o.shadows !== false && o.shadows !== true) known("shadows", o.shadows, Object.keys(SHADOW_DEFAULTS));
    if (o.at !== null && !(o.at && o.at.isObject3D)) throw fail("at must be a THREE.Object3D (where the light for ordinary meshes is worked out)");
    this.color = o.color !== null ? (isVec(o.color) ? o.color.slice() : new THREE.Color(o.color).toArray()) : (this.star ? this.star.lightColor.slice() : [1, 1, 1]);
    this.albedos = this.bodies.map(meanAlbedo);
    this.sky = o.sky;
    this.skyBase = this.sky && this.sky.skyMaterial ? this.sky.skyMaterial.uniforms.uGain.value : 1;
    this.glows = this.bodies.map((b) => (b.uniforms && b.uniforms.uGlowColor ? b.uniforms.uGlowColor.value.clone() : null));
    /** The sun for ordinary meshes: a THREE.DirectionalLight in the scene (its strength: pi x the sunlight). */
    this.directional = new THREE.DirectionalLight(0xffffff, Math.PI);
    /** Planet-shine for ordinary meshes: a second, weak THREE.DirectionalLight (black when nothing shines). */
    this.fill = new THREE.DirectionalLight(0xffffff, 0);
    this.scene.add(this.directional, this.directional.target, this.fill, this.fill.target);
    this.ambient = o.ambient > 0 ? new THREE.AmbientLight(0xffffff, Math.PI * o.ambient) : null;
    if (this.ambient) this.scene.add(this.ambient);
    if (o.environment) {
      if (!this.sky) throw fail("environment needs {sky}: the sky of vidgen/space-sky");
      this.scene.environment = this.sky.environment;
    }
    if (o.shadows) {
      const sh = this.shadow = {...SHADOW_DEFAULTS, ...(o.shadows === true ? {} : o.shadows)};
      this.directional.castShadow = true;
      this.directional.shadow.mapSize.set(sh.mapSize, sh.mapSize); this.directional.shadow.bias = sh.bias;
      const c = this.directional.shadow.camera;
      c.left = -sh.size; c.right = sh.size; c.top = sh.size; c.bottom = -sh.size; c.near = sh.size * 0.1; c.far = sh.size * 8; c.updateProjectionMatrix();
      const renderer = o.renderer ?? (this.star ? this.star.renderer : null);
      if (!renderer) throw fail("shadows need {renderer}: the page's THREE.WebGLRenderer (its shadow maps are turned on)");
      renderer.shadowMap.enabled = true;
    }
    if (o.eclipses) this._prepareEclipses();
    if (this.star) this.star.occluders = this.bodies;
    /** After update(t): {exposure, ev, gains, bodies: [{sun, intensity, shine, source}], light: {...}}. */
    this.state = null;
    this._v = {a: new THREE.Vector3(), b: new THREE.Vector3(), c: new THREE.Vector3(), m: new THREE.Matrix4()};
  }

  // the bodies' shaders get the eclipse test compiled in (vidgen/space-bodies' ECLIPSE block)
  _prepareEclipses() {
    for (const b of this.bodies) {
      if (!b.material || !b.uniforms) continue;
      b.uniforms.uEclipse = {value: Array.from({length: MAX_ECLIPSES}, () => new THREE.Vector4(0, 0, 0, 0))};
      b.uniforms.uEclipseAir = {value: Array.from({length: MAX_ECLIPSES}, () => new THREE.Vector4(0, 0, 0, 0))};
      b.material.defines.ECLIPSE = MAX_ECLIPSES; b.material.needsUpdate = true;
    }
  }

  _world(object, into) { return object.getWorldPosition(into); }
  _radius(body) { return body.object.getWorldScale(this._v.c).x; }

  // where the sun is from `p` (world): the unit direction, the distance (Infinity for a sun in the sky) and the tangent of its angular radius
  _sunFrom(p) {
    if (this.sunObject) {
      const s = this.sunObject.getWorldPosition(this._v.a), d = [s.x - p.x, s.y - p.y, s.z - p.z], D = len(d), R = this.sunObject.getWorldScale(this._v.c).x;
      return {dir: unit(d), distance: D, size: R / Math.max(D, 1e-30), to: d, radius: R};
    }
    const v = this.star ? this.star.direction : this.direction, dir = unit([v.x, v.y, v.z]);
    const size = Math.tan((this.star ? this.star.options.angularRadius : this.options.sunSize) * RAD);
    // a sun given as a direction stands beyond every world of the scene (a SpaceView's metres put the Earth millions of units away)
    return {dir, distance: Infinity, size, to: dir.map((x) => x * SKY_SUN), radius: size * SKY_SUN};
  }

  _reference() {
    const r = this.options.reference;
    if (typeof r === "number") return r;
    const body = r && r.object ? r : this.bodies[0];
    if (!body) return 1;
    return this._sunFrom(this._world(body.object, this._v.b)).distance;
  }

  // the strongest second light at world point `p` (not from `self`): planet-shine from a lit world
  _shineAt(p, self, gains) {
    let best = {honest: 0, dir: [0, 1, 0], color: [0, 0, 0], source: null};
    this.bodies.forEach((src, j) => {
      if (src === self) return;
      const c = this._world(src.object, this._v.b), to = [c.x - p.x, c.y - p.y, c.z - p.z], D = len(to), R = this._radius(src);
      if (!(D > 0) || !(R > 0)) return;
      const sun = this._sunFrom(c), toward = to.map((x) => -x / D);
      const phase = Math.acos(Math.max(-1, Math.min(1, dot(sun.dir, toward))));
      const a = this.albedos[j], honest = planetShine(lum(a), R, D, phase) * this._intensity[j];
      if (honest > best.honest) {
        // from the lit side of that world rather than from its middle
        const dir = unit([to[0] + 0.5 * R * sun.dir[0], to[1] + 0.5 * R * sun.dir[1], to[2] + 0.5 * R * sun.dir[2]]), l = Math.max(lum(a), 1e-6);
        best = {honest, dir, color: [0, 1, 2].map((i) => a[i] / l * this.color[i]), source: src};
      }
    });
    const drawn = gains.film ? filmShine(best.honest) : best.honest * gains.sun;
    return {...best, drawn: drawn * this.options.shine};
  }

  // how much of the frame each lit thing covers, on a grid of view rays (soft at every edge, so it changes smoothly)
  _meter(fills) {
    const cam = this.camera, e = cam.matrixWorld.elements, tanY = Math.tan((cam.fov ?? 40) * RAD / 2), tanX = tanY * (cam.aspect ?? 16 / 9);
    const NX = 32, NY = 18, eye = this._v.a.setFromMatrixPosition(cam.matrixWorld).toArray();
    const entries = [];
    this.bodies.forEach((b, i) => {
      const c = this._world(b.object, this._v.b).toArray(), R = this._radius(b), rel = [c[0] - eye[0], c[1] - eye[1], c[2] - eye[2]], D = len(rel);
      if (!(R > 0) || D <= R) { entries.push({ev: -Math.log2(Math.max(this._intensity[i], 1e-9)), share: 1}); return; }
      const sun = this._sunFrom({x: c[0], y: c[1], z: c[2]}).dir, fill = fills[i];
      let day = 0, night = 0;
      for (let y = 0; y < NY; y++) for (let x = 0; x < NX; x++) {
        const u = ((x + 0.5) / NX * 2 - 1) * tanX, v = ((y + 0.5) / NY * 2 - 1) * tanY;
        const d = unit([e[0] * u + e[4] * v - e[8], e[1] * u + e[5] * v - e[9], e[2] * u + e[6] * v - e[10]]);
        const along = dot(rel, d);
        if (along <= 0) continue;
        const miss = Math.sqrt(Math.max(D * D - along * along, 0)) / R, soft = Math.max(2 * tanX / NX * along / R, 1e-6);
        const cover = 1 - smooth(1 - soft, 1 + soft, miss);
        if (cover <= 0) continue;
        const th = along - Math.sqrt(Math.max(R * R - Math.min(miss, 1) ** 2 * R * R, 0));
        const n = unit([d[0] * th - rel[0], d[1] * th - rel[1], d[2] * th - rel[2]]);
        const lit = smooth(-0.05, 0.25, dot(n, sun));
        day += cover * lit;
        if (fill && fill.honest > 0) night += cover * (1 - lit) * smooth(0, 0.3, dot(n, fill.dir));
      }
      const cells = NX * NY;
      entries.push({ev: -Math.log2(Math.max(this._intensity[i], 1e-9)), share: day / cells});
      if (fill && fill.honest > 0) entries.push({ev: -Math.log2(fill.honest) - 1.5, share: night / cells});
    });
    if (this.star) {
      const seen = this.star.visibility(cam), v = this.star.object.getWorldPosition(this._v.b).applyMatrix4(cam.matrixWorldInverse);
      const out = v.z < 0 ? Math.max(Math.abs(v.x / -v.z) / tanX, Math.abs(v.y / -v.z) / tanY) : 9;
      entries.push({ev: 0, share: 0.05 * lum(seen.fraction) * (1 - smooth(1.0, 1.2, out))});   // a sun in the frame counts as a twentieth of it
    }
    return autoExposure(entries, this.options.auto);
  }

  /** Set every light for scene time `t`: call it after the bodies, the star and the camera stand at `t`. */
  update(t = 0) {
    const o = this.options, V = this._v;
    this.scene.updateMatrixWorld(); this.camera.updateMatrixWorld();
    const reference = o.falloff === 0 ? 1 : this._reference();
    const suns = this.bodies.map((b) => this._sunFrom(this._world(b.object, V.b)));
    this._intensity = suns.map((s) => (o.falloff === 0 || !Number.isFinite(s.distance) ? 1 : sunlight(s.distance, reference, o.falloff)));
    // honest planet-shine first (the automatic exposure reads it), then the exposure, then what is drawn
    const honest = {sun: 1, film: false};
    const fills = this.bodies.map((b, i) => this._fillFor(b, i, suns[i], honest));
    let ev = 0;
    if (o.exposure === "camera") ev = typeof o.ev === "function" ? o.ev(t) : o.ev;
    else if (o.exposure === "auto") ev = this._meter(fills);
    const gains = exposureGains(o.exposure, ev);
    const state = {exposure: o.exposure, ev: gains.ev, gains, bodies: [], light: null};
    this.bodies.forEach((b, i) => {
      const s = suns[i], k = Math.min(BURN, this._intensity[i] * gains.sun), base = b.options && typeof b.options.light === "number" ? b.options.light : 1;
      b.setSun(s.dir, {color: this.color, intensity: base * k});
      const f = gains.film ? this._fillFor(b, i, s, gains) : {...fills[i], drawn: Math.min(BURN, fills[i].honest * gains.sun) * fills[i].scale};
      if (b.fill) { b.fill.direction.set(...f.dir); b.fill.color.setRGB(f.color[0] * f.drawn * base, f.color[1] * f.drawn * base, f.color[2] * f.drawn * base); }
      if (this.glows[i] && b.material && b.material.defines.GLOW_LIGHTS) b.uniforms.uGlowColor.value.copy(this.glows[i]).multiplyScalar(gains.lights);
      else if (this.glows[i]) b.uniforms.uGlowColor.value.copy(this.glows[i]).multiplyScalar(Math.min(BURN, gains.sun));
      if (o.eclipses && b.uniforms && b.uniforms.uEclipse) this._eclipses(b, s, gains);
      state.bodies.push({sun: s.dir, intensity: k, shine: f.drawn, honest: f.honest, source: f.source});
    });
    if (this.star) this.star.gain = Math.min(BURN, gains.sun);
    if (this.sky && typeof this.sky.set === "function") this.sky.set({brightness: Math.min(16, this.skyBase * gains.sky)});
    if (o.environment) this.scene.environmentIntensity = (typeof o.environment === "number" ? o.environment : 1) * gains.sky;
    // ordinary meshes: the sun at `at` (dimmed and reddened by what stands before it there), and planet-shine
    const at = o.at ? this._world(o.at, V.b).clone() : V.b.setFromMatrixPosition(this.camera.matrixWorld).clone();
    const s = this._sunFrom(at), I = (o.falloff === 0 || !Number.isFinite(s.distance) ? 1 : sunlight(s.distance, reference, o.falloff)) * gains.sun, shown = Math.min(BURN, I);
    const occluders = this.bodies.filter((b) => b.object !== o.at).map((b) => { const c = this._world(b.object, V.a); return {at: [c.x - at.x, c.y - at.y, c.z - at.z], radius: this._radius(b), air: airOf(b)}; })
      .filter((x) => len(x.at) > x.radius);
    const seen = sunVisibility(s.to, s.radius, occluders);
    const reach = this.shadow ? this.shadow.size * 4 : 1;
    this.directional.target.position.copy(at);
    this.directional.position.copy(at).add(V.a.set(...s.dir).multiplyScalar(reach));
    this.directional.color.setRGB(this.color[0] * seen.fraction[0], this.color[1] * seen.fraction[1], this.color[2] * seen.fraction[2]);
    this.directional.intensity = Math.PI * shown;
    const shine = this._shineAt(at, null, gains);
    this.fill.target.position.copy(at);
    this.fill.position.copy(at).add(V.a.set(...shine.dir));
    this.fill.color.setRGB(...shine.color.map((c) => Math.min(c, 4)));
    this.fill.intensity = Math.PI * Math.min(BURN, shine.drawn);
    state.light = {direction: s.dir, intensity: shown, seen: seen.fraction, shine: shine.drawn, source: shine.source};
    this.state = state;
    return this;
  }

  // a body's second light: planet-shine from another world, or ring-shine from its own rings, whichever is stronger
  _fillFor(body, i, sun, gains) {
    const o = this.options, p = this._world(body.object, this._v.b).clone();
    const shine = o.shine > 0 ? this._shineAt(p, body, gains) : {honest: 0, drawn: 0, dir: [0, 1, 0], color: [0, 0, 0], source: null};
    let out = {...shine, scale: o.shine};
    const rings = body.options && body.options.rings;
    if (rings && o.ringShine > 0) {
      const pole = this._v.a.set(0, 1, 0).transformDirection(body.object.matrixWorld).toArray(), h = dot(pole, sun.dir);
      const honest = ringShine(0.5 * (rings.opacity ?? 1), Math.asin(Math.max(-1, Math.min(1, h)))) * this._intensity[i];
      if (honest > shine.honest) {
        // from the lit face of the rings, over the night side
        const side = h >= 0 ? 1 : -1, flat = unit([sun.dir[0] - h * pole[0], sun.dir[1] - h * pole[1], sun.dir[2] - h * pole[2]]);
        const dir = unit([side * pole[0] - flat[0], side * pole[1] - flat[1], side * pole[2] - flat[2]]);
        const tint = rings.color !== undefined && rings.color !== null ? new THREE.Color(rings.color).toArray() : [0.92, 0.86, 0.76], l = Math.max(lum(tint), 1e-6);
        out = {honest, drawn: (gains.film ? filmShine(honest) : honest * gains.sun) * o.ringShine, dir, color: [0, 1, 2].map((c) => tint[c] / l * this.color[c]), source: "rings", scale: o.ringShine};
      }
    }
    return out;
  }

  // the bodies between `body` and the sun, in its own axes and radii, for its shader's soft disc test
  _eclipses(body, sun, gains) {
    const V = this._v, mesh = body.mesh ?? body.object, inv = V.m.copy(mesh.matrixWorld).invert(), p = this._world(body.object, V.b).clone(), R = this._radius(body);
    const list = [];
    for (const other of this.bodies) {
      if (other === body) continue;
      const c = this._world(other.object, V.a), rel = [c.x - p.x, c.y - p.y, c.z - p.z], along = dot(rel, sun.dir), r = this._radius(other);
      if (along <= 0) continue;
      const miss = Math.sqrt(Math.max(dot(rel, rel) - along * along, 0));
      if (miss > R + r + along * sun.size * 1.5) continue;                       // its shadow passes this body by
      list.push({centre: V.a.clone().applyMatrix4(inv), radius: r / R, air: !!airOf(other), near: along});
    }
    list.sort((a, b) => a.near - b.near);
    const umbra = gains.film ? UMBRA_FILM : UMBRA_HONEST;
    for (let k = 0; k < MAX_ECLIPSES; k++) {
      const e = list[k];
      if (e) { body.uniforms.uEclipse.value[k].set(e.centre.x, e.centre.y, e.centre.z, e.radius); body.uniforms.uEclipseAir.value[k].set(...(e.air ? umbra : [0, 0, 0]), sun.size); }
      else { body.uniforms.uEclipse.value[k].set(0, 0, 0, 0); body.uniforms.uEclipseAir.value[k].set(0, 0, 0, 0); }
    }
  }

  /** Take the lights out of the scene and give the bodies and the sky back what was theirs. */
  dispose() {
    for (const x of [this.directional, this.directional.target, this.fill, this.fill.target, this.ambient]) if (x) x.removeFromParent();
    this.bodies.forEach((b, i) => { if (this.glows[i]) b.uniforms.uGlowColor.value.copy(this.glows[i]); if (b.fill) b.fill.color.setRGB(0, 0, 0); });
    if (this.sky && typeof this.sky.set === "function") this.sky.set({brightness: this.skyBase});
    if (this.star) { this.star.gain = 1; this.star.occluders = []; }
  }
}
/** The light of a space scene: `spaceLight({scene, camera, sun, bodies, sky})`, then `light.update(t)` every frame. */
export const spaceLight = (options = {}) => new SpaceLight(options);
