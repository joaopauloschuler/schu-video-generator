// vidgen/space-sea: water to the horizon under a vidgen/space-air sky (DESIGN.md §123.4). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-sea".
//
//   import {air, sunDirection} from "vidgen/space-air";
//   import {sea} from "vidgen/space-sea";
//   const sky = air(renderer, "earth", {sun: sunDirection(12, 0)});
//   const water = sea(renderer, sky, {state: "breeze", seed: 3});
//   scene.add(sky.object, water.object);
//   function frame(t) { sky.update(t, {camera}); water.update(t, {camera}); renderer.render(scene, camera); }
//   const y = water.heightAt(x, z, t);             // metres over sea level: for a hull, a shadow, a low camera
//
// The sea is the world's sphere (the air's radius), so the horizon lies where it does and drops with
// height. No mesh in the world: a grid of the picture's own cells is laid on the sphere every frame, so there
// is no edge, no tile and nothing to pop. The waves are a seeded list of sine waves with deep-water speeds
// (a spectrum for the wind, a swell beside it), a pure function of place and time, read through three long
// slow bends so that no crest is a ruled line: the longest lift the grid near the camera, all of them tilt
// the picture's normals, each faded as it gets finer than a pixel; what is faded is not lost but widens the
// sun's glitter (the slopes a pixel no longer shows are counted as roughness), so far water does not shimmer
// and the glitter path has the width the sea state gives it.
// Light: the sun after the air (golden when low), the sky's own table mirrored with Fresnel's share, the
// water's body colour under it, foam where crests break (white now, a thinning lace where one broke a moment
// ago), and the air between (airThrough).
import * as THREE from "three";
import {baked} from "vidgen/baked";
import {AIR_GLSL, DISPLAY_GLSL, PSI_TABLE, SUN_SIZE, BURN} from "vidgen/space-air";

/** Bumped when the pictures change: part of the baked foam pattern's key. */
export const VERSION = 1;
const PREFIX = "vidgen/space-sea";
const RAD = Math.PI / 180, TAU = 2 * Math.PI;
export const QUALITIES = Object.freeze(["fast", "standard", "fine"]);
/** By quality: the waves in the list, how many of them may lift the grid, the grid's cell in pixels, the faces
 * that stand for a rough far sea's mirror (two: the bright low sky and the sky higher up; one: between them). */
export const DETAIL = Object.freeze({fast: [16, 6, 16, 1], standard: [32, 10, 8, 2], fine: [48, 14, 4, 2]});
/** The lowest camera the sea is drawn for, metres over sea level (keep the camera over the crests: `heightAt`). */
export const LOWEST = 0.5;
/** The most of the sea foam may cover, whatever the wind. */
export const FOAM_MOST = 0.12;
/** How long ago a crest broke where its foam is still seen as a thinning lace, seconds. */
export const FOAM_LAG = 2.2;
/** The lengths of the gusts' patches, metres (each varied by the seed). */
export const GUSTS = Object.freeze([500, 900, 1600, 2900, 5200, 9300]);
/** How far a gust's wave moves the finer gusts' pattern sideways, as a share of its own length (so no patch is a ruled stripe). */
export const GUST_SHIFT = 0.13;
/** How far a bend moves the waves' pattern, as a share of the bend's own length. */
export const BEND = 0.04;

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
function colour(where, v) {
  if (!Array.isArray(v) || v.length !== 3) throw fail(`${where} must be [red, green, blue] (linear, 0 to 1), got ${JSON.stringify(v)}`);
  return v.map((x) => number(where, x, 0, 1));
}
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a), 0, 1); return u * u * (3 - 2 * u); };
// a seeded generator of numbers from 0 to 1 (mulberry32)
function seeded(seed) {
  let a = (Math.floor(seed) >>> 0) + 0x9e3779b9;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ---------- the geometry of a horizon, the mirror's share, the wind's statistics: pure ----------
/** How far the horizon of a sphere `radius` metres in radius is from an eye `height` metres over it, metres along the line of sight. */
export const horizonDistance = (radius, height) => Math.sqrt(Math.max(height, 0) * (2 * radius + Math.max(height, 0)));
/** How far the horizon lies under the eye's level, degrees. */
export const horizonDip = (radius, height) => Math.acos(radius / (radius + Math.max(height, 0))) / RAD;
/** The share of unpolarized light a smooth surface of refractive index `index` mirrors, the ray's cosine to the surface's normal `cos` (Fresnel's equations). */
export function fresnel(cos, index = 1.34) {
  const c = clamp(cos, 0, 1), g = Math.sqrt(index * index - 1 + c * c), a = (g - c) / (g + c), b = (c * (g + c) - 1) / (c * (g - c) + 1);
  return 0.5 * a * a * (1 + b * b);
}
/** The mean square slope of a sea under a wind of `wind` m/s (Cox and Munk, 1954: measured from the sun's glitter). */
export const slopeVariance = (wind) => 0.003 + 0.00512 * Math.max(wind, 0);
/** The share of the sea covered by whitecaps under a wind of `wind` m/s (Monahan and O'Muircheartaigh, 1980), at most FOAM_MOST after `foam` (a factor). */
export const whitecaps = (wind, foam = 1) => Math.min(FOAM_MOST, 3.84e-6 * Math.max(wind, 0) ** 3.41 * foam);
// how many standard deviations a normal value exceeds with probability `share`
function exceeded(share) {
  const tail = (z) => { const t = 1 / (1 + 0.2316419 * z); return Math.exp(-z * z / 2) / Math.sqrt(TAU) * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429)))); };
  let lo = 0, hi = 8;
  for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (tail(mid) > share) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}

/** Sea states. `wind`: m/s at mast height; `direction`: where the wind blows and its waves run to, degrees (0 =
 * towards -z, 90 = towards +x, as sunDirection's azimuth); `height`: the wind sea's significant wave height, metres,
 * and `length`: its dominant wavelength, metres (both from the wind for a fully developed sea when not stated:
 * 0.21 U^2 / g and 8.2 U^2 / g, Pierson and Moskowitz); `swell`: a second, narrow train from far away, {height,
 * length, direction}, or null; `foam`: a factor on the whitecaps' cover; `chop`: how much crests are sharpened;
 * `gusts`: how unevenly the wind ruffles the water (0 to 1); `gravity`: m/s^2.
 * `rough` and `storm` are young seas (lower, shorter and so steeper than their winds would raise given days: the
 * waves read better); the storm's foam is held back for the picture. */
export const STATES = Object.freeze({
  calm: {wind: 1.5, swell: {height: 0.25, length: 70, direction: 65}, gusts: 0.6},
  breeze: {wind: 6, swell: {height: 0.4, length: 90, direction: -15}, gusts: 0.4},
  swell: {wind: 4, swell: {height: 2.2, length: 190, direction: 45}, gusts: 0.45},
  rough: {wind: 13, height: 3.2, length: 80, swell: null, chop: 1, gusts: 0.35},
  storm: {wind: 22, height: 8, length: 170, swell: null, foam: 0.5, chop: 0.8, gusts: 0.3},
});
const STATE_OPTIONS = ["wind", "direction", "height", "length", "swell", "foam", "chop", "gusts", "gravity", "name"];
const SWELL_OPTIONS = ["height", "length", "direction"];

/** A sea state in full: `what` a name of STATES or {wind, direction, height, length, swell, foam, chop, gusts,
 * gravity}; `extra` over it. Returns those as numbers, and `cover` (the whitecaps' share of the sea), `slopes`
 * (the mean square slope the glitter shows), `period` (the dominant wave's, seconds). Pure. */
export function seaState(what = "breeze", extra = {}) {
  let base = what;
  if (typeof what === "string") {
    const key = what.trim().toLowerCase();
    if (!(key in STATES)) throw fail(`no sea state "${what}"${hint(key, Object.keys(STATES))}; ready-made: ${Object.keys(STATES).join(", ")}`);
    base = {...STATES[key], name: key};
  } else if (what === null || typeof what !== "object" || Array.isArray(what)) throw fail(`the sea state must be a name or an options object, got ${JSON.stringify(what)}`);
  known("the sea state's options", extra, STATE_OPTIONS);
  const o = {...base, ...extra};
  known("the sea state", o, STATE_OPTIONS);
  const gravity = number("gravity (m/s^2)", o.gravity ?? 9.81, 0.1, 100), wind = number("wind (m/s)", o.wind ?? 6, 0, 60);
  const height = number("height (metres)", o.height ?? Math.max(0.21 * wind * wind / gravity, 0.01), 0.001, 30);
  const length = number("length (metres)", o.length ?? Math.max(8.17 * wind * wind / gravity, 0.6), 0.3, 2000);
  if (height / length > 0.1) throw fail(`a wave ${height} m high and ${length} m long would break (the height may be a tenth of the length at most)`);
  let swell = null;
  if (o.swell !== null && o.swell !== undefined) {
    known("swell", o.swell, SWELL_OPTIONS);
    swell = {height: number("swell.height (metres)", o.swell.height ?? 1, 0.001, 30), length: number("swell.length (metres)", o.swell.length ?? 150, 1, 2000), direction: number("swell.direction (degrees)", o.swell.direction ?? 0, -360, 360)};
    if (swell.height / swell.length > 0.07) throw fail(`a swell ${swell.height} m high and ${swell.length} m long is too steep (a fourteenth of its length at most)`);
  }
  const foam = number("foam", o.foam ?? 1, 0, 10);
  return Object.freeze({name: o.name ?? null, wind, direction: number("direction (degrees)", o.direction ?? 20, -360, 360), height, length, swell: swell && Object.freeze(swell),
    foam, chop: number("chop", o.chop ?? 1, 0, 2), gusts: number("gusts", o.gusts ?? 0.4, 0, 1), gravity,
    cover: whitecaps(wind, foam), slopes: slopeVariance(wind), period: TAU / Math.sqrt(gravity * TAU / length)});
}

/** The waves of a sea state from a seed: {waves, lifted, base, gusts, bends, state, seed}. `waves`: `count` sine waves,
 * the longest first, each {kx, kz (radians a metre along +x and +z), k, length, amplitude, omega (radians a
 * second: deep water, omega^2 = g k), phase, sharp (its second harmonic's share: sharper crests, flatter
 * troughs), ruffled (how much the gusts change it, 0 to 1), crest (its part in the measure of where crests
 * meet), lag (the cosine and sine of its turn in FOAM_LAG seconds), swell}; `lifted`: how many of them may lift the picture's grid; `base`: the slopes finer than the
 * list, as a covariance [xx, xz, zz] (what Cox and Munk's mean square slope leaves after the list's own);
 * `gusts`: six long slow waves in all directions, the longest first, whose sum ruffles the short ones in patches
 * ({kx, kz, omega, phase, weight, shift}); `bends`: three long slow shears of the whole pattern
 * ({kx, kz, dx, dz, amplitude, omega, phase}: the place a wave is read at moves by amplitude x sin along (dx, dz)). The wind sea: wavelengths from twice the dominant
 * one down to its 180th (0.25 m at least), amplitudes after Pierson and Moskowitz' spectrum scaled to the
 * stated height, directions spread round the wind's (16 degrees for the long, 50 for the short). Pure. */
export function waveList(state, {seed = 1, count = 32, lifted = 10} = {}) {
  number("seed", seed, 0, 2 ** 32 - 1); number("count", count, 4, 64);
  const st = state !== null && typeof state === "object" && Object.isFrozen(state) && "cover" in state ? state : seaState(state), rand = seeded(seed), g = st.gravity, waves = [];
  const nSwell = st.swell ? clamp(Math.round(count / 5), Math.min(5, count - 2), 8) : 0, nWind = count - nSwell;
  const to = (degrees) => [Math.sin(degrees * RAD), -Math.cos(degrees * RAD)];
  const hi = 2 * st.length, lo = Math.max(st.length / 180, 0.25), omega = (length) => Math.sqrt(g * TAU / length), peak = omega(st.length);
  let energy = 0;
  for (let i = 0; i < nWind; i++) {
    const edge = (j) => hi * (lo / hi) ** (j / nWind), length = hi * (lo / hi) ** ((i + 0.5 + 0.6 * (rand() - 0.5)) / nWind), w = omega(length);
    const amplitude = Math.sqrt(2 * w ** -5 * Math.exp(-1.25 * (peak / w) ** 4) * (omega(edge(i + 1)) - omega(edge(i))));
    const spread = 16 + 34 * clamp(Math.log2(st.length / length) / 4, 0, 1), off = spread * 1.6 * (rand() + rand() + rand() - 1.5);
    const d = to(st.direction + off), k = TAU / length;
    waves.push({kx: k * d[0], kz: k * d[1], k, length, amplitude, omega: w, phase: rand() * TAU, swell: false});
    energy += amplitude * amplitude / 2;
  }
  for (const w of waves) w.amplitude *= st.height / 4 / Math.sqrt(energy);
  for (let j = 0; j < nSwell; j++) {
    const length = st.swell.length * (1 + 0.34 * ((j + rand()) / nSwell - 0.5)), d = to(st.swell.direction + 13 * (rand() + rand() - 1)), k = TAU / length;
    waves.push({kx: k * d[0], kz: k * d[1], k, length, amplitude: st.swell.height / 4 * Math.sqrt(2 / nSwell), omega: omega(length), phase: rand() * TAU, swell: true});
  }
  waves.sort((a, b) => a.k - b.k);
  let slopes = 0, crests = 0;
  for (const w of waves) {
    // sharper crests where the waves of about this length are steep together (a second harmonic, as Stokes' waves have)
    const band = Math.sqrt(waves.reduce((sum, v) => sum + (v.length > w.length / 2 && v.length < w.length * 2 ? v.amplitude * v.amplitude : 0), 0));
    w.sharp = clamp(0.5 * w.k * band * st.chop, 0, 0.2);
    w.ruffled = w.swell ? 0 : smooth(Math.log(3), Math.log(8), Math.log(st.length / w.length));
    w.crest = w.k * w.amplitude * (w.length / st.length) ** 0.3 * (w.swell ? 0.3 : smooth(Math.log(1 / 60), Math.log(1 / 25), Math.log(w.length / st.length)));
    w.lag = [Math.cos(w.omega * FOAM_LAG), Math.sin(w.omega * FOAM_LAG)];
    if (!w.swell) slopes += (w.k * w.amplitude) ** 2 / 2;
    crests += w.crest * w.crest / 2;
  }
  for (const w of waves) w.crest /= Math.sqrt(Math.max(crests, 1e-30));
  // the slopes finer than the list: Cox and Munk's total less the list's own, a little more along the wind than across
  const fine = Math.max(st.slopes - slopes, 0.25 * st.slopes), d = to(st.direction), along = 0.6 * fine, across = 0.4 * fine;
  const base = [along * d[0] * d[0] + across * d[1] * d[1], (along - across) * d[0] * d[1], along * d[1] * d[1] + across * d[0] * d[0]];
  const gusts = GUSTS.map((length) => {
    const size = length * (0.8 + 0.4 * rand()), e = to(360 * rand()), k = TAU / size;
    return {kx: k * e[0], kz: k * e[1], omega: k * 0.5 * st.wind * (e[0] * d[0] + e[1] * d[1]), phase: rand() * TAU, weight: 0.24, shift: GUST_SHIFT * size};
  }).reverse();
  // the bends: three long slow shears of the whole pattern (each moves the water's picture across its own
  // direction by a 25th of its length at most), so crests are not ruled lines and no lattice of sines shows
  const longest = Math.max(st.length, st.swell ? st.swell.length : 0);
  const bends = [1.3, 2.9, 6.1].map((factor) => {
    const size = longest * factor * (0.85 + 0.3 * rand()), e = to(360 * rand()), k = TAU / size;
    return {kx: k * e[0], kz: k * e[1], dx: -e[1], dz: e[0], amplitude: BEND * size, omega: k * 0.3 * st.wind * (e[0] * d[0] + e[1] * d[1]), phase: rand() * TAU};
  });
  let n = 0;
  while (n < waves.length && n < lifted && waves[n].ruffled === 0) n++;
  return Object.freeze({waves: Object.freeze(waves.map((w) => Object.freeze(w))), lifted: n, base: Object.freeze(base), gusts: Object.freeze(gusts), bends: Object.freeze(bends), state: st, seed});
}

/** How strongly the gusts ruffle the short waves at a place and time (1: the mean). */
export function gustAt(list, x, z, t) {
  const first = list.gusts[1], lead = 2 * first.shift * Math.sin(first.kx * x + first.kz * z - first.omega * t + first.phase + 1.7) / Math.hypot(first.kx, first.kz);
  let sum = 0, px = x - first.kz * lead, pz = z + first.kx * lead;
  for (const g of list.gusts) {       // the longest first: each moves the place the finer ones are read at, across its own direction
    const v = Math.sin(g.kx * px + g.kz * pz - g.omega * t + g.phase), k = Math.hypot(g.kx, g.kz);
    sum += g.weight * v; px -= g.kz / k * g.shift * v; pz += g.kx / k * g.shift * v;
  }
  return Math.max(0.2, 1 + list.state.gusts * 2.2 * sum);
}
/** The water's surface at a place (metres along +x and +z from the sea's origin) and time (seconds): [height over
 * sea level (metres), the slope along +x, the slope along +z] (the gusts' own slow change of the height is left out of the slopes). A pure function of the list, the place and the time. */
export function surfaceAt(list, x, z, t) {
  const gust = gustAt(list, x, z, t), turned = list.bends.map((b) => b.kx * x + b.kz * z - b.omega * t + b.phase);
  let h = 0, sx = 0, sz = 0, px = x, pz = z;
  list.bends.forEach((b, j) => { const a = b.amplitude * Math.sin(turned[j]); px += b.dx * a; pz += b.dz * a; });
  for (const w of list.waves) {
    const th = w.kx * px + w.kz * pz - w.omega * t + w.phase, s = Math.sin(th), c = Math.cos(th), a = w.amplitude * (1 + w.ruffled * (gust - 1));
    h += a * (c + w.sharp * (c * c - s * s));
    const d = -a * s * (1 + 4 * w.sharp * c);
    sx += w.kx * d; sz += w.kz * d;
  }
  // the slopes at the place itself: the bends stretch and turn the pattern a little
  let bx = 0, bz = 0;
  list.bends.forEach((b, j) => { const along = b.amplitude * Math.cos(turned[j]) * (sx * b.dx + sz * b.dz); bx += along * b.kx; bz += along * b.kz; });
  return [h, sx + bx, sz + bz];
}
/** The water's height over sea level, metres, at a place and time. */
export const heightAt = (list, x, z, t) => surfaceAt(list, x, z, t)[0];
/** The water's unit normal there, [x, up, z]. */
export function normalAt(list, x, z, t) {
  const [, sx, sz] = surfaceAt(list, x, z, t), l = Math.hypot(sx, 1, sz);
  return [-sx / l, 1 / l, -sz / l];
}

/** Waters: `color`: what comes back out of deep water, as the brightness of a matt surface (linear red, green,
 * blue); `shallow`: the same over a pale bottom a few metres down (shown only where a `depth` is given);
 * `index`: the refractive index (the mirror's share); `foam`: the foam's colour; `glow`: how much more of the
 * water's own colour a wave's face turned to the eye shows. `ocean`, `green`, `tropical`, `grey`: looks of the
 * Earth's seas (open ocean, shelf water rich in plankton, clear water over sand, a cold silty sea). `methane`:
 * an invented dark sea for an invented world (the index is liquid methane's; the colour is a guess). */
export const WATERS = Object.freeze({
  ocean: {color: [0.005, 0.027, 0.058], shallow: [0.02, 0.16, 0.17], index: 1.34, foam: [0.62, 0.64, 0.65], glow: 0.9},
  green: {color: [0.006, 0.032, 0.03], shallow: [0.05, 0.16, 0.11], index: 1.34, foam: [0.6, 0.63, 0.6], glow: 1.1},
  tropical: {color: [0.004, 0.05, 0.075], shallow: [0.04, 0.3, 0.28], index: 1.34, foam: [0.66, 0.68, 0.68], glow: 1.2},
  grey: {color: [0.014, 0.022, 0.024], shallow: [0.09, 0.11, 0.09], index: 1.34, foam: [0.55, 0.56, 0.56], glow: 0.6},
  methane: {color: [0.011, 0.006, 0.003], shallow: [0.07, 0.04, 0.02], index: 1.27, foam: [0.42, 0.36, 0.28], glow: 0.4},
});
const WATER_OPTIONS = ["color", "shallow", "index", "foam", "glow", "name"];
/** A water in full: a name of WATERS or {color, shallow, index, foam, glow}; `extra` over it. Pure. */
export function waterOf(what = "ocean", extra = {}) {
  let base = what;
  if (typeof what === "string") {
    const key = what.trim().toLowerCase();
    if (!(key in WATERS)) throw fail(`no water "${what}"${hint(key, Object.keys(WATERS))}; ready-made: ${Object.keys(WATERS).join(", ")}`);
    base = {...WATERS[key], name: key};
  } else if (what === null || typeof what !== "object" || Array.isArray(what)) throw fail(`the water must be a name or an options object, got ${JSON.stringify(what)}`);
  known("the water's options", extra, WATER_OPTIONS);
  const o = {...WATERS.ocean, ...base, ...extra};
  known("the water", o, WATER_OPTIONS);
  return Object.freeze({name: o.name ?? null, color: Object.freeze(colour("color", o.color)), shallow: Object.freeze(colour("shallow", o.shallow)), index: number("index", o.index, 1.01, 3),
    foam: Object.freeze(colour("foam", o.foam)), glow: number("glow", o.glow, 0, 4)});
}

// ---------- the picture ----------
// the grid: a cell of the picture, laid on the world's sphere along its own line of sight, lifted by the long waves
const SEA_VERT = /* glsl */`
uniform vec4 uWaveA[NW], uWaveB[NW];
uniform vec4 uBendA[3], uBendB[3];
uniform vec4 uSeaGeo, uSeaFar, uSeaGrid;
uniform vec3 uSeaE1, uSeaE2, uSeaAhead, uAirUp;
varying vec3 vRel;
varying float vClamp;
void main() {
  vec3 dv = normalize(vec3((position.x + projectionMatrix[2][0]) / projectionMatrix[0][0], (position.y + projectionMatrix[2][1]) / projectionMatrix[1][1], -1.0));
  vec3 rd = normalize(dv * mat3(viewMatrix));
  float r0 = uSeaFar.w, cc = uSeaFar.z, mu = dot(rd, uAirUp), top = uSeaGrid.z + uSeaGrid.y;
  vClamp = 0.0;
  if (mu > top) {                       // over the horizon: every such corner goes to the horizon at its own bearing
    vec3 level = rd - uAirUp * mu; float l = length(level);
    level = l > 1e-4 ? level / l : uSeaAhead;
    mu = top; rd = level * sqrt(1.0 - mu * mu) + uAirUp * mu; vClamp = 1.0;
  }
  float disc = r0 * r0 * mu * mu - cc, t = mu < 0.0 && disc > 0.0 ? cc / (-r0 * mu + sqrt(disc)) : uSeaFar.y;
  vec3 P = rd * t, upL = normalize(P + uAirUp * r0);
  float fade = 1.0 - smoothstep(0.6 * uSeaFar.x, uSeaFar.x, t);
  if (fade > 0.0) {
    vec2 p = vec2(dot(P, uSeaE1), dot(P, uSeaE2)), ah = vec2(dot(rd, uSeaE1), dot(rd, uSeaE2));
    float al = length(ah); ah = al > 1e-5 ? ah / al : vec2(1.0, 0.0);
    float sc = t * uSeaGrid.x, sa = sc / max(-dot(rd, upL), 1e-3), h = 0.0;
    for (int j = 0; j < 3; j++) p += uBendB[j].xy * (uBendA[j].w * sin(dot(uBendA[j].xy, p) + uBendA[j].z));
    for (int i = 0; i < NG; i++) {
      vec4 A = uWaveA[i];
      float ka = dot(A.xy, ah), kc = dot(A.xy, vec2(-ah.y, ah.x)), th = dot(A.xy, p) + A.w, s = sin(th), c = cos(th);
      h += A.z * exp(-0.5 * (sa * sa * ka * ka + sc * sc * kc * kc)) * (c + uWaveB[i].x * (c * c - s * s));
    }
    P += upL * (h * fade);
  }
  vRel = P / uSeaGeo.z;
  gl_Position = projectionMatrix * viewMatrix * vec4(cameraPosition + vRel, 1.0);
  gl_Position.z = min(gl_Position.z, gl_Position.w * 0.999999);     // the far plane never cuts the sea
}`;
const SEA_FRAG = (depth) => /* glsl */`
${AIR_GLSL}
${DISPLAY_GLSL}
uniform vec4 uWaveA[NW], uWaveB[NW], uWaveC[NW];
uniform vec2 uWaveD[NW];          // the cosine and sine of each wave's turn in the foam's lag
uniform vec4 uGust[6];             // a gust's wave vector, its phase at the camera, its weight
uniform vec4 uBendA[3], uBendB[3];   // a bend's wave vector, its phase at the camera, how far it moves the pattern (m); the direction it moves it in
uniform vec4 uSeaGeo;       // the world's radius (m), the camera's height (m), metres a scene unit, a pixel's angle
uniform vec4 uSeaFar;       // how far the grid is lifted (m), the horizon's distance (m), height x (2 radius + height), radius + height
uniform vec4 uSeaBase;      // the slopes finer than the list (xx, xz, zz), the gusts' strength
uniform vec4 uSeaMap;       // the sea-level sky table's rows
uniform vec4 uSeaFoam;      // the crest measure foam begins at, the whitecaps' mean cover, the streaks' stretch, the filter (pixels)
uniform vec4 uSeaLaceAt;    // where the camera stands in the foam pattern's two layers
uniform vec4 uSeaOptic;     // the refractive index, the glow of faces turned to the eye, the sun's angular radius (its sine), the sky's light at the camera's place
uniform vec4 uSeaWind;      // the wind's direction (x, z), the camera's place in the sea's frame (m)
uniform vec3 uSeaE1, uSeaE2, uSeaBody, uSeaShallow, uSeaFoamColor;
uniform sampler2D uSeaSky, uSeaAmbient, uSeaLace;
uniform float uDisplay, uGrain, uSeaShoal, uSeaShow, uSeaGust;   // uSeaShow 1: no picture, but each pixel's place (metres from the camera along the sea's +x and +z) and the water's height there, as numbers (the tests' check of the lookup)
varying vec3 vRel;
varying float vClamp;
${depth}
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
float seaFresnel(float c) {
  float n = uSeaOptic.x, g = sqrt(n * n - 1.0 + c * c), a = (g - c) / (g + c), b = (c * (g + c) - 1.0) / (c * (g - c) + 1.0);
  return 0.5 * a * a * (1.0 + b * b);
}
// how much of a rough surface (slopes of standard deviation sigma) a ray at cosine mu to the vertical sees unshadowed (Smith; Walter's fit)
float seaSeen(float mu, float sigma) {
  float a = mu / max(1.4142 * sigma * sqrt(max(1.0 - mu * mu, 1e-6)), 1e-6);
  return a < 1.6 ? (3.535 * a + 2.181 * a * a) / (1.0 + 2.276 * a + 2.577 * a * a) : 1.0;
}
void main() {
  if (vClamp > 0.9999) discard;
  float unit = uSeaGeo.z, pix = uSeaGeo.w, r0 = uSeaFar.w, cc = uSeaFar.z;
  float tGeo = length(vRel) * unit; vec3 rd = normalize(vRel);
  float mu = dot(rd, uAirUp), disc = r0 * r0 * mu * mu - cc, under = -(asin(clamp(mu, -1.0, 1.0)) + uAirMap.x);
  float near = 1.0 - smoothstep(uSeaFar.x, 1.5 * uSeaFar.x, tGeo), cover = max(clamp(under / pix, 0.0, 1.0), near);
  if (cover <= 0.0) discard;
  float t = mix(mu < 0.0 && disc > 0.0 ? cc / (-r0 * mu + sqrt(disc)) : uSeaFar.y, tGeo, near);
  vec3 P = rd * t, upL = normalize(P + uAirUp * r0), v = -rd;
  vec2 p = vec2(dot(P, uSeaE1), dot(P, uSeaE2)), ah = vec2(dot(rd, uSeaE1), dot(rd, uSeaE2));
  float al = length(ah); ah = al > 1e-5 ? ah / al : vec2(1.0, 0.0);
  vec2 ch = vec2(-ah.y, ah.x);
  // a pixel's footprint on the water: across the line of sight, and along it (long where the look is level)
  float muv = max(dot(v, upL), 1e-4), sc = t * pix * uSeaFoam.w, sa = sc / muv, sc2 = sc * sc, sa2 = sa * sa;
  // the gusts: long slow patches where the short waves stand higher or lower
  float gust = 0.0;
  vec2 gp = p + vec2(-uGust[1].y, uGust[1].x) * (2.0 * uSeaGust * sin(dot(uGust[1].xy, p) + uGust[1].z + 1.7) / dot(uGust[1].xy, uGust[1].xy));
  for (int j = 0; j < 6; j++) {
    vec4 G = uGust[j]; float ga = dot(G.xy, ah), gc = dot(G.xy, ch), gv = sin(dot(G.xy, gp) + G.z);
    gust += G.w * exp(-0.5 * (sa2 * ga * ga + sc2 * gc * gc)) * gv; gp += vec2(-G.y, G.x) * (uSeaGust * gv / dot(G.xy, G.xy));
  }
  // from very high the patches are drawn fainter: a pixel hundreds of metres wide shows their mean, not each one
  gust = max(0.2, 1.0 + uSeaBase.w * 2.2 * gust / (1.0 + sc2 / 4e4));
  // the bends: where each wave is read
  vec3 bent; vec2 q = p;
  for (int j = 0; j < 3; j++) { float th = dot(uBendA[j].xy, p) + uBendA[j].z; q += uBendB[j].xy * (uBendA[j].w * sin(th)); bent[j] = uBendA[j].w * cos(th); }
  // the waves: each fades as it gets finer than the footprint; what fades is kept as roughness
  vec2 slope = vec2(0.0); vec3 cov = uSeaBase.xyz * gust * gust; float crest = 0.0, before = 0.0, kept = 1.0, high = 0.0;
  for (int i = 0; i < NW; i++) {
    vec4 A = uWaveA[i], B = uWaveB[i], C = uWaveC[i];
    float amp = A.z * (1.0 + B.z * (gust - 1.0));
    if (dot(A.xy, A.xy) * sc2 > 12.0) { cov += C.xyz * mix(1.0, gust * gust, B.z); kept -= C.w; break; }
    float ka = dot(A.xy, ah), kc = dot(A.xy, ch), e = 0.5 * (sa2 * ka * ka + sc2 * kc * kc), g = 1.0 / (1.0 + e * (1.0 + e * (0.5 + 0.25 * e)));
    float th = dot(A.xy, q) + A.w, s = sin(th), c = cos(th);
    high += amp * g * (c + B.x * (c * c - s * s));
    slope += A.xy * (-amp * g * s * (1.0 + 4.0 * B.x * c));
    float lost = 0.5 * amp * amp * (1.0 - g * g);
    cov += lost * vec3(A.x * A.x, A.x * A.y, A.y * A.y);
    crest += B.y * g * c; before += B.y * g * (c * uWaveD[i].x - s * uWaveD[i].y); kept -= 0.5 * B.y * B.y * (1.0 - g * g);
  }
  for (int j = 0; j < 3; j++) slope += uBendA[j].xy * (bent[j] * dot(slope, uBendB[j].xy));
  if (uSeaShow > 0.5) { gl_FragColor = vec4(p, high, 1.0); return; }
  vec3 n = normalize(upL - slope.x * uSeaE1 - slope.y * uSeaE2);
  float ndv = dot(n, v);
  if (ndv < 0.03) { n = normalize(n + v * (0.03 - ndv)); ndv = dot(n, v); }
  // the mirror: Fresnel's share of the sky. Slopes a pixel no longer shows turn the faces it sees towards the
  // eye where the look is level: less is mirrored, and from higher in the sky. Two faces stand for them all: one
  // hardly turned (it mirrors much, from low in the sky: the bright horizon, the twilight arch) and one well turned
  float rough = cov.x * ah.x * ah.x + 2.0 * cov.y * ah.x * ah.y + cov.z * ah.y * ah.y;
  vec2 facing = sqrt(ndv * ndv + (FACES > 1 ? vec2(0.12, 1.5) : vec2(0.35)) * rough), Fs = vec2(seaFresnel(min(facing.x, 1.0)), seaFresnel(min(facing.y, 1.0)));
  float F = 0.5 * (Fs.x + Fs.y);
  float sunG = dot(uAirSun, upL), sunUp = max(sunG, 0.0);
  vec3 Tsun = exp(-airTau(0.0, sunG)) * smoothstep(-uSeaOptic.z, uSeaOptic.z, sunG);
  vec3 amb = texture2D(uSeaAmbient, vec2(clamp((sunG - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, 0.01, 0.99), 0.5)).rgb;
  vec3 mirrored = reflect(rd, n), sky = vec3(0.0);
  for (int k = 0; k < FACES; k++) {
    vec3 R = normalize(mirrored + upL * (2.0 * (facing[k] - ndv)));
    float muR = dot(R, upL);
    if (muR < 0.0) { R -= 2.0 * muR * upL; muR = -muR; }
    float cosvR = dot(R, uAirSun);
    sky += Fs[k] / float(FACES) * airRead(uSeaSky, airPlace(uSeaMap, max(muR, 0.004), cosvR), cosvR);
    if (rough < 1e-5 * ndv * ndv) { sky *= float(FACES); break; }          // a mirror: one face is all
  }
  // the table is the sky over the camera's place: far water under another sun takes its sky's brightness from there
  sky *= clamp(dot(amb, LUMA) / max(uSeaOptic.w, 1e-12), 0.25, 4.0);
  // the sun's glitter: the share of the faces, resolved and not, that mirror the sun to the eye
  vec3 hv = normalize(uAirSun + v); float hz = max(dot(hv, upL), 1e-3);
  vec2 d = -vec2(dot(hv, uSeaE1), dot(hv, uSeaE2)) / hz - slope;
  vec3 S = cov + vec3(2e-5, 0.0, 2e-5);
  float det = max(S.x * S.z - S.y * S.y, 1e-14), sigma = sqrt(0.5 * (S.x + S.z));
  float faces = exp(-0.5 * (S.z * d.x * d.x - 2.0 * S.y * d.x * d.y + S.x * d.y * d.y) / det) / (6.2831853 * sqrt(det));
  float glint = 3.14159265 * seaFresnel(clamp(dot(v, hv), 0.0, 1.0)) * faces * seaSeen(muv, sigma) * seaSeen(sunUp, sigma) / (4.0 * muv * hz * hz * hz * hz);
  // as the sun's own disc: the redder the air leaves the sun, the less its mirror image may burn out, so a sunset's glitter keeps its colour
  float most = max(max(Tsun.r, Tsun.g), max(Tsun.b, 1e-9));
  vec3 glitter = Tsun / most * min(most * glint, mix(2.0, ${BURN.toFixed(1)}, pow(most, 1.6)));
  // the water's own colour: light that went in and came back, more of it through a face turned to the eye
  float depth = seaDepth(uSeaWind.zw + p), shoal = exp(-max(depth, 0.0) / uSeaShoal);
  vec3 body = mix(uSeaBody, uSeaShallow, shoal) * (Tsun * max(dot(n, uAirSun), 0.0) * (1.0 - seaFresnel(sunUp)) + amb) * (1.0 + uSeaOptic.y * clamp(2.5 * dot(slope, ah), -0.4, 1.5));
  vec3 col = uAirLight * ((1.0 - F) * body + glitter) + sky;
  // foam: where the crests of many waves meet, broken up by a fine pattern, streaked along the wind
  vec2 w = vec2(dot(p, uSeaWind.xy), dot(p, vec2(-uSeaWind.y, uSeaWind.x)));
  vec4 lace = texture2D(uSeaLace, vec2(w.x, w.y) / 7.0 + uSeaLaceAt.xy), wide = texture2D(uSeaLace, vec2(w.y / 37.0, -w.x / (37.0 * uSeaFoam.z)) + uSeaLaceAt.zw);
  kept = clamp(kept, 0.0, 1.0);
  // a crest breaking now: a thick white sliver along it; where one broke a moment ago: a lace that thins, drawn out along the wind
  float fresh = smoothstep(uSeaFoam.x, uSeaFoam.x + 0.4, crest + 0.5 * (wide.b - 0.5) + 0.4 * (lace.g - 0.5)) * mix(0.75, 1.0, lace.b);
  float old = smoothstep(uSeaFoam.x - 0.5, uSeaFoam.x + 0.5, before + 1.2 * (wide.g - 0.5)) * (0.08 + 0.55 * lace.r * lace.r);
  float broken = max(fresh, old);
  float foam = (broken * kept + uSeaFoam.y * (1.0 - kept)) * step(1e-6, uSeaFoam.y);
  col = mix(col, uAirLight * uSeaFoamColor * (Tsun * sunUp + amb), clamp(foam, 0.0, 1.0));
  // the film look's dusk curve, as the sky's own light gets it
  col *= pow(max(dot(col, LUMA) / uAirDusk.y, 1.0), -uAirDusk.x);
  col = airThrough(col, rd * (t / unit));
  cover *= smoothstep(0.0, 0.25, depth);
  float grainy = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  vec3 shown = display(col);
  float grain = mix(uGrain, 1.0, smoothstep(0.45, 0.8, dot(shown, vec3(0.3333))));
  gl_FragColor = uDisplay < 0.5 ? vec4(max(col * (1.0 + grainy * 0.004), 0.0), cover) : vec4(shown + grainy * grain / 255.0, cover);
}`;
const DEEP = "float seaDepth(vec2 p) { return 1e6; }";
// the foam's fine pattern, a tile that repeats: thin walls between cells (red), soft patches (green), bubbles (blue)
const LACE_FRAG = /* glsl */`
uniform vec2 uSize;
vec2 hash2(vec2 cell, float period) {
  cell = mod(cell, period);
  vec3 q = fract(vec3(cell.xyx) * vec3(0.1031, 0.1030, 0.0973)); q += dot(q, q.yzx + 33.33);
  return fract((q.xx + q.yz) * q.zy);
}
vec2 cells(vec2 p, float period) {
  vec2 i = floor(p), f = fract(p); float f1 = 8.0, f2 = 8.0;
  for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
    vec2 o = vec2(float(x), float(y)), r = o + hash2(i + o, period) - f; float d = dot(r, r);
    if (d < f1) { f2 = f1; f1 = d; } else if (d < f2) f2 = d;
  }
  return sqrt(vec2(f1, f2));
}
void main() {
  vec2 uv = gl_FragCoord.xy / uSize, a = cells(uv * 7.0, 7.0), b = cells(uv * 19.0 + 3.7, 19.0), c = cells(uv * 3.0 + 1.3, 3.0), e = cells(uv * 5.0 + 7.1, 5.0);
  float walls = 0.6 * (1.0 - smoothstep(0.0, 0.28, a.y - a.x)) + 0.4 * (1.0 - smoothstep(0.0, 0.3, b.y - b.x));
  gl_FragColor = vec4(walls, clamp(1.15 - 0.75 * (c.x + e.x), 0.0, 1.0), clamp(1.0 - 1.4 * b.x, 0.0, 1.0), 1.0);
}`;
const LACE_SIZE = 256;

const OPTIONS = Object.freeze({state: "breeze", seed: 1, water: "ocean", quality: "standard", waves: null, anchor: Object.freeze([0, 1, 0]), filter: 0.8, depth: null, shoal: 4});

/** Water to the horizon under an air: `object` (add it to the scene), `update(t, {camera})`, `heightAt(x, z, t)`,
 * `normalAt(x, z, t)`, `pointAt(x, z, t)`, `list` (the waves), `state`, `water`, `horizon` (what the last
 * update found: {distance (m), dip (degrees), height (m)}). */
export class Sea {
  /** `renderer`: the page's; `sky`: the air of vidgen/space-air the sea lies under (its world's radius is sea level,
   * its light and its table of the sky are the sea's); `options`: `state` (a name of STATES or {wind, direction,
   * height, length, swell, foam, chop, gusts, gravity}) and any of those beside it (over the state's), `seed`,
   * `water` (a name of WATERS or {color, shallow, index, foam, glow}), `quality` ("fast", "standard", "fine"),
   * `waves` (how many, in place of the quality's), `anchor` (the unit vector from the world's middle to where
   * the waves' plane touches the sphere: default the scene's +y; state the place a far flight ends at),
   * `filter` (how early a wave finer than a pixel fades, in pixels), `depth` ({glsl, uniforms}: the water's
   * depth, see DESIGN §123.4) with `shoal` (metres of water over which the bottom's colour fades). */
  constructor(renderer, sky, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("sea(renderer, sky, options): the first argument must be the page's THREE.WebGLRenderer");
    if (!sky || !sky.uniforms || !sky.model || typeof sky.skyAt !== "function") throw fail("sea(renderer, sky, options): the second argument must be the air the sea lies under (air(renderer, ...) of vidgen/space-air)");
    known("the options", options, [...Object.keys(OPTIONS), ...STATE_OPTIONS.filter((k) => k !== "name")]);
    const mine = {}, states = {};
    for (const [k, v] of Object.entries(options)) (k in OPTIONS ? mine : states)[k] = v;
    const o = this.options = {...OPTIONS, ...mine};
    choice("quality", o.quality, QUALITIES); number("filter", o.filter, 0.3, 4); number("shoal", o.shoal, 0.01, 1000);
    const [count, lifted, cell, faces] = DETAIL[o.quality];
    this.renderer = renderer; this.sky = sky; this.cell = cell;
    this.state = seaState(o.state, states);
    this.water = waterOf(o.water);
    /** The waves drawn: what `heightAt` sums (see waveList). */
    this.list = waveList(this.state, {seed: o.seed, count: o.waves ?? count, lifted});
    const anchor = new THREE.Vector3(...(Array.isArray(o.anchor) ? o.anchor : [o.anchor.x, o.anchor.y, o.anchor.z]));
    if (anchor.lengthSq() === 0) throw fail("anchor: the vector is zero");
    anchor.normalize();
    // the waves' plane: +x and +z of the scene where the anchor is +y
    const e2 = new THREE.Vector3(0, 0, 1).addScaledVector(anchor, -anchor.z);
    if (e2.lengthSq() < 1e-6) e2.set(0, -1, 0).addScaledVector(anchor, anchor.y);
    e2.normalize();
    this.frame = {anchor, e1: new THREE.Vector3().crossVectors(anchor, e2).normalize(), e2};
    if (o.depth !== null) {
      known("depth", o.depth, ["glsl", "uniforms"]);
      if (typeof o.depth.glsl !== "string" || !/float\s+seaDepth\s*\(\s*vec2/.test(o.depth.glsl)) throw fail("depth.glsl must define `float seaDepth(vec2 p)`: the water's depth in metres at p (metres along the sea's +x and +z)");
    }
    const n = this.list.waves.length, wind = [Math.sin(this.state.direction * RAD), -Math.cos(this.state.direction * RAD)], v4 = () => new THREE.Vector4();
    const A = this.list.waves.map(v4), B = this.list.waves.map((w) => new THREE.Vector4(w.sharp, w.crest, w.ruffled, 0)), C = this.list.waves.map(v4), D = this.list.waves.map((w) => new THREE.Vector2(...w.lag));
    // what is lost when the loop stops at a wave: the slopes and the crest measure of it and all finer ones
    const tail = [0, 0, 0, 0];
    for (let i = n - 1; i >= 0; i--) {
      const w = this.list.waves[i], e = w.amplitude * w.amplitude / 2;
      tail[0] += e * w.kx * w.kx; tail[1] += e * w.kx * w.kz; tail[2] += e * w.kz * w.kz; tail[3] += w.crest * w.crest / 2;
      C[i].set(...tail);
    }
    this._lace = this._bakeLace();
    const at = sky.skyAt(0);
    this.uniforms = {...sky.uniforms, uWaveA: {value: A}, uWaveB: {value: B}, uWaveC: {value: C}, uWaveD: {value: D}, uGust: {value: this.list.gusts.map(v4)},
      uBendA: {value: [v4(), v4(), v4()]}, uBendB: {value: this.list.bends.map((b) => new THREE.Vector4(b.dx, b.dz, 0, 0))}, uSeaShow: {value: 0}, uSeaGust: {value: GUST_SHIFT * TAU},
      uSeaGeo: {value: new THREE.Vector4(sky.model.radius, 10, sky.options.unit, 0.002)}, uSeaFar: {value: v4()}, uSeaGrid: {value: v4()},
      uSeaBase: {value: new THREE.Vector4(...this.list.base, this.state.gusts)}, uSeaMap: {value: v4()},
      uSeaFoam: {value: new THREE.Vector4(exceeded(Math.max(this.state.cover, 1e-9)), this.state.cover, 1 + 2.5 * smooth(8, 20, this.state.wind), o.filter)},
      uSeaLaceAt: {value: v4()}, uSeaOptic: {value: new THREE.Vector4(this.water.index, this.water.glow, Math.sin(sky.options.sunSize * RAD), 1)}, uSeaWind: {value: new THREE.Vector4(wind[0], wind[1], 0, 0)},
      uSeaE1: {value: this.frame.e1}, uSeaE2: {value: this.frame.e2}, uSeaAhead: {value: new THREE.Vector3(1, 0, 0)},
      uSeaBody: {value: new THREE.Vector3(...this.water.color)}, uSeaShallow: {value: new THREE.Vector3(...this.water.shallow)}, uSeaFoamColor: {value: new THREE.Vector3(...this.water.foam)},
      uSeaSky: {value: at.texture}, uSeaAmbient: {value: sky.ambientTexture}, uSeaLace: {value: this._lace.texture},
      uDisplay: {value: 0}, uGrain: {value: 2}, uSeaShoal: {value: o.shoal}, ...(o.depth?.uniforms ?? {})};
    this.material = new THREE.ShaderMaterial({uniforms: this.uniforms, defines: {NW: n, NG: Math.max(this.list.lifted, 1), FACES: faces}, vertexShader: SEA_VERT, fragmentShader: SEA_FRAG(o.depth?.glsl ?? DEEP),
      side: THREE.DoubleSide, depthTest: true, depthWrite: true, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    this.geometry = null; this._gridFor = "";
    /** The water: drawn after the air's dome and before the scene's other things, which it hides where they are under it. */
    this.object = new THREE.Mesh(new THREE.BufferGeometry(), this.material);
    this.object.name = `sea ${this.state.name ?? ""}`.trim(); this.object.frustumCulled = false; this.object.renderOrder = -850;
    const view = new THREE.Vector4();
    this.object.onBeforeRender = (r, scene, camera) => {
      r.getCurrentViewport(view);
      const u = this.uniforms, p = camera.projectionMatrix.elements, cellAngle = Math.max(2 * this._over / this._cols / p[0], 2 * this._over / this._rows / p[5]);
      u.uSeaGeo.value.w = 2 / (p[5] * view.w);
      u.uDisplay.value = r.getRenderTarget() === null ? 1 : 0;
      // the long waves lift the grid as far as its cells are finer than they: about as far as a sixth of the longest wave still spans a cell
      const longest = this.list.lifted ? this.list.waves[0].length : 0, h = u.uSeaGeo.value.y;
      u.uSeaFar.value.x = Math.max(0.7 * Math.sqrt(longest * h / cellAngle), 1e-3);
      u.uSeaGrid.value.set(cellAngle, 3 * cellAngle, -u.uSeaFar.value.y / u.uSeaFar.value.w, 0);
      this.material.uniformsNeedUpdate = true;
    };
    // the air's own plain ground would show through the horizon's soft pixel: the sea takes its place
    sky.under(true);
    /** What the last update found: the horizon's `distance` (metres), its `dip` (degrees), the camera's `height` over sea level (metres). */
    this.horizon = {distance: 0, dip: 0, height: 0};
    this._center = [0, -sky.model.radius / sky.options.unit, 0];
    this.material.addEventListener("dispose", () => { this._lace.dispose(); });
    this._grid();
    this.update(0);
  }

  // the foam's pattern: baked once, kept by vidgen between pages
  _bakeLace() {
    const r = this.renderer;
    const targets = () => [new THREE.WebGLRenderTarget(LACE_SIZE, LACE_SIZE, {type: THREE.UnsignedByteType, format: THREE.RGBAFormat, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter,
      wrapS: THREE.RepeatWrapping, wrapT: THREE.RepeatWrapping, depthBuffer: false, generateMipmaps: true})];
    const draw = ([target]) => {
      const material = new THREE.ShaderMaterial({vertexShader: "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }", fragmentShader: LACE_FRAG, depthTest: false, depthWrite: false, toneMapped: false,
        uniforms: {uSize: {value: new THREE.Vector2(LACE_SIZE, LACE_SIZE)}}});
      const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material), scene = new THREE.Scene(), before = r.getRenderTarget();
      quad.frustumCulled = false; scene.add(quad);
      r.setRenderTarget(target); r.render(scene, new THREE.Camera()); r.setRenderTarget(before);
      material.dispose(); quad.geometry.dispose();
    };
    return baked(r, "space-sea/lace", {version: VERSION, size: LACE_SIZE}, {targets, draw})[0];
  }

  // the grid for the renderer's picture: cells of `cell` pixels, a little beyond every edge (lifted corners must not open the frame)
  _grid() {
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2()), key = `${size.x}x${size.y}`;
    if (key === this._gridFor) return;
    this._over = 1.18; this._cols = Math.max(8, Math.ceil(size.x * this._over / this.cell)); this._rows = Math.max(8, Math.ceil(size.y * this._over / this.cell));
    if (this.geometry) this.geometry.dispose();
    this.geometry = this.object.geometry = new THREE.PlaneGeometry(2 * this._over, 2 * this._over, this._cols, this._rows);
    this._gridFor = key;
  }

  /** The sea at scene time `t` for a camera standing where `camera` does (a THREE.Camera, or [x, y, z]; the origin
   * without one). Call it before every draw, after the air's own `update` with the same camera. */
  update(t = 0, {camera = null} = {}) {
    number("update: the time (seconds)", t, -1e9, 1e9);
    const sky = this.sky, m = sky.model, unit = sky.options.unit, u = this.uniforms, f = this.frame;
    let eye = [0, 0, 0];
    if (Array.isArray(camera)) eye = camera;
    else if (camera) { camera.updateMatrixWorld(); const e = camera.matrixWorld.elements; eye = [e[12], e[13], e[14]]; }
    const c = this._center = [...sky.state.center], d = new THREE.Vector3(eye[0] - c[0], eye[1] - c[1], eye[2] - c[2]), r = d.length() * unit;
    if (!(r > 0)) throw fail("update: the camera stands at the world's middle");
    const R = m.radius, h = Math.max(r - R, LOWEST), x = d.dot(f.e1) * unit, z = d.dot(f.e2) * unit;
    this._grid();
    u.uSeaGeo.value.set(R, h, unit, u.uSeaGeo.value.w);
    u.uSeaFar.value.set(u.uSeaFar.value.x, horizonDistance(R, h), h * (2 * R + h), R + h);
    // any level direction, for a grid corner that looks straight up
    const up = d.clone().normalize(), ahead = new THREE.Vector3(1, 0, 0).addScaledVector(up, -up.x);
    if (ahead.lengthSq() < 1e-6) ahead.set(0, 0, 1).addScaledVector(up, -up.z);
    u.uSeaAhead.value.copy(ahead.normalize());
    // every wave's phase at the camera's place: worked out here in double precision, so the picture keeps its
    // fine waves however far from the origin the camera flies
    const turn = (x_) => x_ - TAU * Math.floor(x_ / TAU);
    this.list.waves.forEach((w, i) => u.uWaveA.value[i].set(w.kx, w.kz, w.amplitude, turn(w.kx * x + w.kz * z - w.omega * t + w.phase)));
    this.list.gusts.forEach((g, i) => u.uGust.value[i].set(g.kx, g.kz, turn(g.kx * x + g.kz * z - g.omega * t + g.phase), g.weight));
    this.list.bends.forEach((b, i) => u.uBendA.value[i].set(b.kx, b.kz, turn(b.kx * x + b.kz * z - b.omega * t + b.phase), b.amplitude));
    const wx = u.uSeaWind.value.x, wz = u.uSeaWind.value.y, along = x * wx + z * wz, across = -x * wz + z * wx, part = (x_) => x_ - Math.floor(x_), stretch = u.uSeaFoam.value.z;
    u.uSeaLaceAt.value.set(part(along / 7), part(across / 7), part(across / 37), part(-along / (37 * stretch)));
    u.uSeaWind.value.z = x; u.uSeaWind.value.w = z;
    const at = sky.skyAt(0), ambient = sky.ambient.at(u.uAirMap.value.w);
    u.uSeaSky.value = at.texture; u.uSeaMap.value.copy(at.map);
    u.uSeaOptic.value.w = 0.2126 * ambient[0] + 0.7152 * ambient[1] + 0.0722 * ambient[2];
    this.t = t;
    Object.assign(this.horizon, {distance: horizonDistance(R, h), dip: horizonDip(R, h), height: h});
    return this;
  }

  // a scene place (x, z) in the sea's own frame, metres
  _flat(x, z) { const c = this._center, unit = this.sky.options.unit; return [(x - c[0]) * unit, (z - c[2]) * unit]; }
  /** The water's height over sea level, metres, at the scene's (x, z) and time `t` (seconds; default the last
   * update's): the same sum the picture draws. With an `anchor` other than +y, x and z are the scene units
   * along the sea's own axes (`frame.e1`, `frame.e2`) from the world's middle. */
  heightAt(x, z, t = this.t) { return heightAt(this.list, ...this._flat(x, z), t); }
  /** The water's unit normal there, [x, up, z] in the sea's frame. */
  normalAt(x, z, t = this.t) { return normalAt(this.list, ...this._flat(x, z), t); }
  /** The point of the water's surface over the scene's (x, z), in scene units: on the world's sphere (so it drops
   * with distance from the anchor), lifted by the waves. */
  pointAt(x, z, t = this.t) {
    const [fx, fz] = this._flat(x, z), R = this.sky.model.radius, f = this.frame, unit = this.sky.options.unit, c = this._center;
    if (fx * fx + fz * fz >= R * R) throw fail("pointAt: the place is beyond the world's edge as the sea's frame sees it");
    const up = new THREE.Vector3().addScaledVector(f.e1, fx).addScaledVector(f.e2, fz).addScaledVector(f.anchor, Math.sqrt(R * R - fx * fx - fz * fz)).normalize();
    const r = (R + heightAt(this.list, fx, fz, t)) / unit;
    return [c[0] + up.x * r, c[1] + up.y * r, c[2] + up.z * r];
  }

  /** Free the grid, the material and the foam's pattern; the air draws under the horizon again. */
  dispose() {
    this.sky.under(false);
    this.material.dispose(); if (this.geometry) this.geometry.dispose();
  }
}
/** Water to the horizon under an air: `sea(renderer, sky, {state: "breeze", seed: 3})`, `sea(renderer, sky, {state: "storm", water: "grey"})`. */
export const sea = (renderer, sky, options) => new Sea(renderer, sky, options);
