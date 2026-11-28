// vidgen/space-sea: water to the horizon under a vidgen/space-air sky. Part of
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
// (a spectrum for the wind, a swell beside it), a pure function of place and time; each wave's phase wanders
// by its own share of three long slow fields, so crests run roughly parallel yet vary along their length and
// no lattice and no closed ring forms (one shared warp of the whole pattern drew whorls from 100 m to a few
// km up), and the short waves' phases are shifted besides by endless noise near their own sizes (the shared
// noise of vidgen/space-clouds), so their crests bend and no weave shows close up; the gusts that ruffle them
// in patches are endless noise too (no grid from high up): the longest lift the grid near the camera, all of them tilt
// the picture's normals, each faded as it gets finer than a pixel; what is faded is not lost but widens the
// sun's glitter (the slopes a pixel no longer shows are counted as roughness), so far water does not shimmer
// and the glitter path has the width the sea state gives it.
// Light: the sun after the air (golden when low), the sky's own table mirrored with Fresnel's share, the
// water's body colour under it, foam where crests break (white now, a thinning lace where one broke a moment
// ago, its pattern read so it never repeats), and the air between (airThrough).
import * as THREE from "three";
import {baked} from "vidgen/baked";
import {AIR_GLSL, DISPLAY_GLSL, PSI_TABLE, SUN_SIZE, BURN} from "vidgen/space-air";
import {broadHash, latticeNoise, NOISE_GLSL} from "vidgen/space-clouds";

/** Bumped when the pictures change: part of the baked foam pattern's key. */
export const VERSION = 2;
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
/** The low haze the glitter is seen through (a look): its optical depth a metre and its top, metres over the sea. */
export const LOW_HAZE = Object.freeze({depth: 3e-5, top: 2500});
/** The steepness (significant height over dominant length) from which the waves' bodies are shaded more than the light alone
 * would (darker troughs, lighter crests, darker faces turned from the sun: a look), and where that is at full strength. */
export const RELIEF = Object.freeze([0.03, 0.045]);
/** At dusk in the film look the water mirrors at least this share of the sky (a look: near water stays readable). */
export const DUSK_MIRROR = 0.4;
/** How long ago a crest broke where its foam is still seen as a thinning lace, seconds. */
export const FOAM_LAG = 2.2;
/** The sizes of the gusts' patches, metres (each varied by the seed): octaves of endless gradient noise (no lattice of
 * sines, which showed as a fine grid on the glitter from 20 to 60 km up), each turned its own way, drifting with half the wind. */
export const GUSTS = Object.freeze([500, 900, 1600, 2900, 5200, 9300]);
/** Each gust octave's weight (equal: the spread of six sines of weight 0.24 that the octaves replaced). */
export const GUST_WEIGHT = 0.556;
/** How the short waves are kept from weaving (Step 396): their phases are shifted by endless noise, `fields` fields of it whose
 * cells are `size` times their reference wave's length (the first an eighth of the dominant length, each next `ratio` times
 * shorter), shifting the place by up to about `amount` of a cell (the crests turn by about that many radians); each short wave
 * takes its share from the one or two fields nearest its length (none for the long waves and the swell). */
export const FINE_WARP = Object.freeze({fields: 3, size: 6, ratio: 4.5, amount: 0.25});
// the noise's cells are counted modulo this (so a camera far out keeps exact integers in the shader: noiseHashes)
const WRAP = 65536;
// gradient noise at a place (q along the noise's two axes, in its cells): [value, d/dqx, d/dqz] (the shader's noiseFrom)
function noiseAt(qx, qz, salt, shift) {
  const cx = Math.floor(qx), cz = Math.floor(qz);
  return latticeNoise(cx, cz, qx - cx, qz - cz, salt, shift, WRAP);
}
/** How far a wave's phase wanders with each of the three long fields, radians at most (each wave its own share, from
 * the seed), and how many of the wave's own lengths a field must span for the full share (a longer wave wanders less, so
 * its crests stay roughly straight: the phase's slope stays under WOBBLE / WOBBLE_SPAN of the wave's own). */
export const WOBBLE = 1.4;
export const WOBBLE_SPAN = 8;

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
  storm: {wind: 22, height: 8, length: 170, swell: null, foam: 0.6, chop: 0.8, gusts: 0.3},
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
 * `gusts`: six octaves of endless noise, the largest first, whose sum ruffles the short ones in patches ({size, dir (its
 * axes' turn: cosine, sine), drift (m/s along +x and +z), weight, salt}); `warps`: FINE_WARP's fields of endless noise that
 * shift the short waves' phases ({size (m), dir, drift, amount, salt}; a wave's `band`: where its length lies among them, 0 to
 * fields - 1); `bends`: three long slow fields ({kx, kz, omega, phase, size}); a wave's
 * phase wanders by `wobble[j]` radians times the sine of field j (each wave its own shares: crests of different waves
 * drift apart, so the sum is short-crested and in groups, never one bent pattern). The wind sea: wavelengths from twice the dominant
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
    const size = length * (0.8 + 0.4 * rand()), e = to(360 * rand());
    return {size, dir: e, drift: [0.5 * st.wind * d[0], 0.5 * st.wind * d[1]], weight: GUST_WEIGHT, salt: Math.floor(rand() * 2 ** 24)};
  }).reverse();
  // the bends: three long slow fields; every wave's phase wanders with its own share of each, so crests are not
  // ruled lines, no lattice of sines shows, and (unlike one warp of the whole pattern) no crest closes into a ring
  const longest = Math.max(st.length, st.swell ? st.swell.length : 0);
  const bends = [1.3, 2.9, 6.1].map((factor) => {
    const size = longest * factor * (0.85 + 0.3 * rand()), e = to(360 * rand()), k = TAU / size;
    return {kx: k * e[0], kz: k * e[1], size, omega: k * 0.3 * st.wind * (e[0] * d[0] + e[1] * d[1]), phase: rand() * TAU};
  });
  // each wave's own share of each field (drawn last, so the waves, gusts and fields are the seed's as before)
  for (const w of waves) w.wobble = bends.map((b) => WOBBLE * (2 * rand() - 1) * Math.min(1, b.size / (WOBBLE_SPAN * w.length)));
  // the short waves' warp: fields of endless noise from an eighth of the dominant length down (drawn after the rest)
  const top = st.length / 8, warps = Array.from({length: FINE_WARP.fields}, (_, j) => {
    const reference = top / FINE_WARP.ratio ** j, e = to(360 * rand()), speed = Math.sqrt(g * reference / TAU);
    return Object.freeze({size: FINE_WARP.size * reference, dir: e, drift: [speed * d[0], speed * d[1]], amount: FINE_WARP.amount, salt: Math.floor(rand() * 2 ** 24)});
  });
  for (const w of waves) w.band = clamp(Math.log(top / w.length) / Math.log(FINE_WARP.ratio), 0, FINE_WARP.fields - 1);
  let n = 0;
  while (n < waves.length && n < lifted && waves[n].ruffled === 0) n++;
  return Object.freeze({waves: Object.freeze(waves.map((w) => Object.freeze(w))), lifted: n, base: Object.freeze(base), gusts: Object.freeze(gusts), warps: Object.freeze(warps), bends: Object.freeze(bends), state: st, seed});
}

/** How strongly the gusts ruffle the short waves at a place and time (1: the mean). */
export function gustAt(list, x, z, t) {
  let sum = 0;
  for (const g of list.gusts) sum += g.weight * noiseAt(...fieldPlace(g, x, z, t), g.salt, 0)[0];
  return Math.max(0.2, 1 + list.state.gusts * 2.2 * sum);
}
// a noise field's place (its cells along its own turned axes) for the sea's (x, z) at time t
function fieldPlace(f, x, z, t) {
  const px = x - f.drift[0] * t, pz = z - f.drift[1] * t;
  return [(f.dir[0] * px + f.dir[1] * pz) / f.size, (f.dir[0] * pz - f.dir[1] * px) / f.size];
}
// a wave's shares of the warp's fields: from the one or two nearest its length, as much as the gusts ruffle it (none for the long waves)
const warpShares = (w) => Array.from({length: FINE_WARP.fields}, (_, j) => w.ruffled * Math.max(0, 1 - Math.abs(j - w.band)));
// the short waves' warp fields at a place: each [shift x, shift z, and its derivatives (d shift x / dx, d shift z / dx, d shift x / dz, d shift z / dz)]
function warpsAt(list, x, z, t) {
  return (list.warps ?? []).map((f) => {
    const [qx, qz] = fieldPlace(f, x, z, t), a = noiseAt(qx, qz, f.salt, 0), b = noiseAt(qx, qz, f.salt, 4), m = f.amount, c = f.dir[0], s = f.dir[1];
    // d q / d(x, z) = [[c, s], [-s, c]] / size, so d shift / d(x, z) = amount (dn/dq) [[c, s], [-s, c]]
    return [m * f.size * a[0], m * f.size * b[0], m * (a[1] * c - a[2] * s), m * (b[1] * c - b[2] * s), m * (a[1] * s + a[2] * c), m * (b[1] * s + b[2] * c)];
  });
}
/** The water's surface at a place (metres along +x and +z from the sea's origin) and time (seconds): [height over
 * sea level (metres), the slope along +x, the slope along +z] (the gusts' own slow change of the height is left out of the slopes). A pure function of the list, the place and the time. */
export function surfaceAt(list, x, z, t) {
  const gust = gustAt(list, x, z, t), turned = list.bends.map((b) => b.kx * x + b.kz * z - b.omega * t + b.phase);
  const bs = turned.map(Math.sin), bc = turned.map(Math.cos), fields = warpsAt(list, x, z, t);
  let h = 0, sx = 0, sz = 0;
  for (const w of list.waves) {
    let th = w.kx * x + w.kz * z - w.omega * t + w.phase, kx = w.kx, kz = w.kz;
    list.bends.forEach((b, j) => { const m = w.wobble ? w.wobble[j] : 0; th += m * bs[j]; kx += m * bc[j] * b.kx; kz += m * bc[j] * b.kz; });
    const shares = warpShares(w);
    fields.forEach((f, j) => {        // the warp: the phase shifted by k . shift, its slope by the shift's derivatives
      const share = shares[j];
      if (share > 0) { th += share * (w.kx * f[0] + w.kz * f[1]); kx += share * (w.kx * f[2] + w.kz * f[3]); kz += share * (w.kx * f[4] + w.kz * f[5]); }
    });
    const s = Math.sin(th), c = Math.cos(th), a = w.amplitude * (1 + w.ruffled * (gust - 1));
    h += a * (c + w.sharp * (c * c - s * s));
    const d = -a * s * (1 + 4 * w.sharp * c);
    sx += kx * d; sz += kz * d;
  }
  return [h, sx, sz];
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
// the short waves' warp (FINE_WARP): a field (uWarp, uWarpI) at p, kept by a share `keep` (it fades where the waves that take from it
// are finer than a pixel, or its cells than the grid's): its shift of the place (m) and the shift's derivatives (d/dx, d/dz)
const WARP_GLSL = /* glsl */`
uniform vec4 uWarp[${FINE_WARP.fields}];     // a field's axes over its size (cosine, sine), the camera's place in its cell
uniform vec4 uWarpI[${FINE_WARP.fields}];    // its whole cells (modulo 65536), its salt, how far it shifts (amount x size, m)
void seaWarp(vec4 F, vec4 I, vec2 p, float keep, out vec2 d, out vec4 J) {
  d = vec2(0.0); J = vec4(0.0);
  if (keep <= 0.0) return;
  vec2 q = vec2(dot(F.xy, p), dot(vec2(-F.y, F.x), p)) + F.zw, c = floor(q);
  uvec4 h = noiseHashes(ivec2(c) + ivec2(I.xy), uint(I.z));
  vec3 a = noiseFrom(h, q - c, 0u), b = noiseFrom(h, q - c, 4u);
  d = keep * I.w * vec2(a.x, b.x);
  J = keep * I.w * vec4(a.y * F.x - a.z * F.y, b.y * F.x - b.z * F.y, a.y * F.y + a.z * F.x, b.y * F.y + b.z * F.x);
}`;
// the grid: a cell of the picture, laid on the world's sphere along its own line of sight, lifted by the long waves
const SEA_VERT = /* glsl */`
uniform vec4 uWaveA[NW], uWaveB[NW], uWaveE[NW];
uniform vec4 uBendA[3];
uniform vec4 uSeaGeo, uSeaFar, uSeaGrid;
uniform vec3 uSeaE1, uSeaE2, uSeaAhead, uAirUp;
uniform vec4 uGust[6];             // a gust octave's axes over its size (cosine, sine), the camera's place in its cell
uniform vec4 uGustI[6];            // and its whole cells (modulo 65536), its weight, its salt
varying vec3 vRel;
varying float vClamp, vGust;
varying vec2 vWarp0, vWarp1;        // the coarser two warp fields (worked out at the grid's corners: their cells span many)
varying vec4 vWarpJ0, vWarpJ1;
${NOISE_GLSL}
${WARP_GLSL}
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
  vec2 p = vec2(dot(P, uSeaE1), dot(P, uSeaE2));
  float sc = t * uSeaGrid.x, sa = sc / max(-dot(rd, upL), 1e-3);
  // the gusts: long slow patches where the short waves stand higher or lower, octaves of endless noise each faded as half the grid's
  // cell outgrows it (worked out at the grid's corners: the patches are larger than a cell wherever they show)
  vGust = 0.0;
  for (int j = 0; j < 6; j++) {
    vec4 G = uGust[j], I = uGustI[j];
    vec2 q = vec2(dot(G.xy, p), dot(vec2(-G.y, G.x), p)) + G.zw, c = floor(q);
    // what is left of an octave seen through half a cell (sc across, sa along the line of sight): the noise's patches lie every way, so
    // those across a footprint long along the sight keep some strength (a ring of wave vectors through a long Gaussian)
    float across = 9.8696044 * sc * sc * dot(G.xy, G.xy), along = 9.8696044 * max(sa * sa - sc * sc, 0.0) * dot(G.xy, G.xy);
    vGust += I.z * exp(-0.5 * across) * pow(1.0 + 3.14159265 * along, -0.25) * noiseFrom(noiseHashes(ivec2(c) + ivec2(I.xy), uint(I.w)), q - c, 0u).x;
  }
  // the coarser two fields of the short waves' warp, where the grid's cell is under a quarter to a half of theirs
  seaWarp(uWarp[0], uWarpI[0], p, 1.0 - smoothstep(0.25, 0.5, sc * length(uWarp[0].xy)), vWarp0, vWarpJ0);
  seaWarp(uWarp[1], uWarpI[1], p, 1.0 - smoothstep(0.25, 0.5, sc * length(uWarp[1].xy)), vWarp1, vWarpJ1);
  if (fade > 0.0) {
    vec2 ah = vec2(dot(rd, uSeaE1), dot(rd, uSeaE2));
    float al = length(ah); ah = al > 1e-5 ? ah / al : vec2(1.0, 0.0);
    float h = 0.0;
    vec3 bs = vec3(sin(dot(uBendA[0].xy, p) + uBendA[0].z), sin(dot(uBendA[1].xy, p) + uBendA[1].z), sin(dot(uBendA[2].xy, p) + uBendA[2].z));
    for (int i = 0; i < NG; i++) {
      vec4 A = uWaveA[i];
      float ka = dot(A.xy, ah), kc = dot(A.xy, vec2(-ah.y, ah.x)), th = dot(A.xy, p) + A.w + dot(uWaveE[i].xyz, bs), s = sin(th), c = cos(th);
      h += A.z * exp(-0.5 * (sa * sa * ka * ka + sc * sc * kc * kc)) * (c + uWaveB[i].x * (c * c - s * s));
    }
    P += upL * (h * fade);
  }
  vRel = P / uSeaGeo.z;
  gl_Position = projectionMatrix * viewMatrix * vec4(cameraPosition + vRel, 1.0);
  gl_Position.z = min(gl_Position.z, gl_Position.w * 0.999999);     // the far plane never cuts the sea
}`;
const SEA_FRAG = (depth, shade) => /* glsl */`
${AIR_GLSL}
${DISPLAY_GLSL}
uniform vec4 uWaveA[NW], uWaveB[NW], uWaveC[NW], uWaveE[NW];
uniform vec2 uWaveD[NW];          // the cosine and sine of each wave's turn in the foam's lag
uniform vec3 uWaveF[NW];          // each wave's shares of the three fields of the short waves' warp (none for the long waves)
uniform vec4 uBendA[3];          // a long field's wave vector, its phase at the camera (each wave's phase wanders by its own share of it: uWaveE)
uniform vec4 uSeaGeo;       // the world's radius (m), the camera's height (m), metres a scene unit, a pixel's angle
uniform vec4 uSeaFar;       // how far the grid is lifted (m), the horizon's distance (m), height x (2 radius + height), radius + height
uniform vec4 uSeaBase;      // the slopes finer than the list (xx, xz, zz), the gusts' strength
uniform vec4 uSeaMap;       // the sea-level sky table's rows
uniform vec4 uSeaFoam;      // the crest measure foam begins at, the whitecaps' mean cover, the foam pattern's salt, the filter (pixels)
uniform vec4 uSeaLaceAt;    // where the camera stands in the foam's two readings of its pattern (the share of a repeat)
uniform vec4 uSeaLaceI;     // and their whole repeats
uniform vec4 uSeaOptic;     // the refractive index, the glow of faces turned to the eye, the sun's angular radius (its sine), the sky's light at the camera's place
uniform vec4 uSeaRelief;    // how much steep waves' bodies are shaded (0 to 1), one over the heights' spread (1/m), one over the spread of the slope along the wind
uniform vec4 uSeaWind;      // the wind's direction (x, z), the camera's place in the sea's frame (m)
uniform vec3 uSeaE1, uSeaE2, uSeaBody, uSeaShallow, uSeaFoamColor;
uniform sampler2D uSeaSky, uSeaAmbient, uSeaLace;
uniform float uDisplay, uGrain, uSeaShoal, uSeaShow;   // uSeaShow 1: no picture, but each pixel's place (metres from the camera along the sea's +x and +z) and the water's height there, as numbers (the tests' check of the lookup)
varying vec3 vRel;
varying float vClamp, vGust;
varying vec2 vWarp0, vWarp1;
varying vec4 vWarpJ0, vWarpJ1;
${NOISE_GLSL}
${WARP_GLSL}
${depth}
${shade}
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
  // the gusts (the grid's, vGust)
  float gust = vGust;
  // from very high the patches are drawn fainter: a pixel hundreds of metres wide shows their mean, not each one
  gust = max(0.2, 1.0 + uSeaBase.w * 2.2 * gust / (1.0 + sc2 / 4e4));
  // the long fields each wave's phase wanders with (its own share of each)
  vec3 bs, bc;
  for (int j = 0; j < 3; j++) { float th = dot(uBendA[j].xy, p) + uBendA[j].z; bs[j] = sin(th); bc[j] = cos(th); }
  // the short waves' warp (FINE_WARP): each field's shift of the place (m) and its derivatives (d shift / dx, d shift / dz);
  // (the finest field here, faded where every wave that takes from it is finer than the pixel; the coarser two the grid's)
  vec2 wd0 = vWarp0, wd1 = vWarp1, wd2; vec4 wj0 = vWarpJ0, wj1 = vWarpJ1, wj2;
  seaWarp(uWarp[2], uWarpI[2], p, 1.0 - smoothstep(${(0.275 * FINE_WARP.ratio / FINE_WARP.size).toFixed(4)}, ${(0.55 * FINE_WARP.ratio / FINE_WARP.size).toFixed(4)}, sc * length(uWarp[2].xy)), wd2, wj2);
  // the waves: each fades as it gets finer than the footprint; what fades is kept as roughness
  vec2 slope = vec2(0.0); vec3 cov = uSeaBase.xyz * gust * gust; float crest = 0.0, before = 0.0, kept = 1.0, high = 0.0;
  for (int i = 0; i < NW; i++) {
    vec4 A = uWaveA[i], B = uWaveB[i], C = uWaveC[i];
    float amp = A.z * (1.0 + B.z * (gust - 1.0));
    if (dot(A.xy, A.xy) * sc2 > 12.0) { cov += C.xyz * mix(1.0, gust * gust, B.z); kept -= C.w; break; }
    float ka = dot(A.xy, ah), kc = dot(A.xy, ch), e = 0.5 * (sa2 * ka * ka + sc2 * kc * kc), g = 1.0 / (1.0 + e * (1.0 + e * (0.5 + 0.25 * e)));
    vec3 E = uWaveE[i].xyz, Ec = E * bc;
    float th = dot(A.xy, p) + A.w + dot(E, bs);
    vec2 kw = A.xy + Ec.x * uBendA[0].xy + Ec.y * uBendA[1].xy + Ec.z * uBendA[2].xy;
    vec3 share = uWaveF[i];
    vec2 shift = share.x * wd0 + share.y * wd1 + share.z * wd2; vec4 turn = share.x * wj0 + share.y * wj1 + share.z * wj2;
    th += dot(A.xy, shift); kw += vec2(dot(A.xy, turn.xy), dot(A.xy, turn.zw));
    float s = sin(th), c = cos(th);
    high += amp * g * (c + B.x * (c * c - s * s));
    slope += kw * (-amp * g * s * (1.0 + 4.0 * B.x * c));
    float lost = 0.5 * amp * amp * (1.0 - g * g);
    cov += lost * vec3(A.x * A.x, A.x * A.y, A.y * A.y);
    crest += B.y * g * c; before += B.y * g * (c * uWaveD[i].x - s * uWaveD[i].y); kept -= 0.5 * B.y * B.y * (1.0 - g * g);
  }
  if (uSeaShow > 0.5) { gl_FragColor = vec4(p, high, 1.0); return; }
  vec3 n = normalize(upL - slope.x * uSeaE1 - slope.y * uSeaE2);
  float ndv = dot(n, v);
  if (ndv < 0.03) { n = normalize(n + v * (0.03 - ndv)); ndv = dot(n, v); }
  // the mirror: Fresnel's share of the sky. Slopes a pixel no longer shows turn the faces it sees towards the
  // eye where the look is level: less is mirrored, and from higher in the sky. Two faces stand for them all: one
  // hardly turned (it mirrors much, from low in the sky: the bright horizon, the twilight arch) and one well turned
  float rough = cov.x * ah.x * ah.x + 2.0 * cov.y * ah.x * ah.y + cov.z * ah.y * ah.y;
  vec2 facing = sqrt(ndv * ndv + (FACES > 1 ? vec2(0.12, 1.5) : vec2(0.35)) * rough), Fs = vec2(seaFresnel(min(facing.x, 1.0)), seaFresnel(min(facing.y, 1.0)));
  float sunG = dot(uAirSun, upL), sunUp = max(sunG, 0.0);
  // the film look at dusk (the exposure lifted, the sun down): the water mirrors at least a fixed share, so near water keeps the zenith's and the arch's colours
  // and from lower in the sky than a mirror would (0.4 of the height): the arch's side, not the dark overhead
  float dusk = clamp(uAirDusk.x * 2.0, 0.0, 1.0) * smoothstep(0.0, -0.05, sunG);
  Fs = max(Fs, vec2(${DUSK_MIRROR.toFixed(2)} * dusk));
  float F = 0.5 * (Fs.x + Fs.y);
  vec3 Tsun = exp(-airTau(0.0, sunG)) * smoothstep(-uSeaOptic.z, uSeaOptic.z, sunG) * seaShade(p);
  vec3 amb = texture2D(uSeaAmbient, vec2(clamp((sunG - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, 0.01, 0.99), 0.5)).rgb;
  vec3 mirrored = reflect(rd, n), sky = vec3(0.0);
  for (int k = 0; k < FACES; k++) {
    vec3 R = normalize(mirrored + upL * (2.0 * (facing[k] - ndv)));
    float muR = dot(R, upL);
    if (muR < 0.0) { R -= 2.0 * muR * upL; muR = -muR; }
    R = normalize(R - upL * (0.6 * dusk * muR)); muR = dot(R, upL);
    float cosvR = dot(R, uAirSun);
    sky += Fs[k] / float(FACES) * airRead(uSeaSky, airPlace(uSeaMap, max(muR, 0.004), cosvR), cosvR);
    if (rough < 1e-5 * ndv * ndv) { sky *= float(FACES); break; }          // a mirror: one face is all
  }
  // the table is the sky over the camera's place: far water under another sun takes its sky's brightness from there
  sky *= clamp(dot(amb, LUMA) / max(uSeaOptic.w, 1e-12), 0.25, 4.0);
  // the sun's glitter: the share of the faces, resolved and not, that mirror the sun to the eye
  vec3 hv = normalize(uAirSun + v); float hz = max(dot(hv, upL), 1e-3);
  // the slope that face has, in the water's own level there (far off the world's roundness tilts it against the sea's plane)
  vec2 d = -(vec2(dot(hv, uSeaE1), dot(hv, uSeaE2)) - hz * vec2(dot(upL, uSeaE1), dot(upL, uSeaE2))) / hz - slope;
  vec3 S = cov + vec3(2e-5, 0.0, 2e-5);
  float det = max(S.x * S.z - S.y * S.y, 1e-14), sigma = sqrt(0.5 * (S.x + S.z));
  float faces = exp(-0.5 * (S.z * d.x * d.x - 2.0 * S.y * d.x * d.y + S.x * d.y * d.y) / det) / (6.2831853 * sqrt(det));
  float glint = 3.14159265 * seaFresnel(clamp(dot(v, hv), 0.0, 1.0)) * faces * seaSeen(muv, sigma) * seaSeen(sunUp, sigma) / (4.0 * muv * hz * hz * hz * hz);
  // as the sun's own disc: the redder the air leaves the sun, the less its mirror image may burn out, so a sunset's glitter keeps its colour
  float most = max(max(Tsun.r, Tsun.g), max(Tsun.b, 1e-9));
  vec3 glitter = Tsun / most * min(most * glint, mix(2.0, ${BURN.toFixed(1)}, pow(most, 1.6)));
  // a low haze over the water, which the air's model does not have, dims the glitter along its way under the haze's top:
  // from high up the path fades towards the horizon instead of ending there at full strength (a look: only the glitter takes it)
  glitter *= exp(-${LOW_HAZE.depth.toExponential(2)} * min(t, ${LOW_HAZE.top.toFixed(1)} / max(muv, sqrt(${(LOW_HAZE.top / 2).toFixed(1)} / uSeaGeo.x))));
  // the water's own colour: light that went in and came back, more of it through a face turned to the eye
  float depth = seaDepth(uSeaWind.zw + p), shoal = exp(-max(depth, 0.0) / uSeaShoal);
  float relief = 1.0 + 0.22 * uSeaRelief.x * clamp(high * uSeaRelief.y, -2.0, 2.0);          // steep seas: darker troughs, lighter crests
  vec3 body = mix(uSeaBody, uSeaShallow, shoal) * relief * (Tsun * max(sunUp + (dot(n, uAirSun) - sunUp) * (1.0 + 1.5 * uSeaRelief.x), 0.0) * (1.0 - seaFresnel(sunUp)) + amb) * (1.0 + uSeaOptic.y * clamp(2.5 * dot(slope, ah), -0.4, 1.5));
  vec3 col = uAirLight * ((1.0 - F) * body + glitter) + sky * relief;
  // foam: where the crests of many waves meet, broken up by a fine pattern, streaked along the wind
  // (read where the short waves' warp moves the place, so its streaks bend with the crests and do not stand in rows)
  vec2 pw = p + wd0 + wd1 + wd2, w = vec2(dot(pw, uSeaWind.xy), dot(pw, vec2(-uSeaWind.y, uSeaWind.x)));
  // the pattern read untiled (each cell of it at its own offset and turn: no repeat shows), with the derivatives of the place
  // (taken here: the readings are skipped where no crest is near breaking, whatever the pattern, and far off where no crest is resolved)
  vec2 lf = vec2(w.x / 28.0, w.y / 7.0) + uSeaLaceAt.xy, lw = vec2(w.x / 30.0, w.y / 110.0) + uSeaLaceAt.zw;
  vec2 lfx = dFdx(lf), lfy = dFdy(lf), lwx = dFdx(lw), lwy = dFdy(lw);
  kept = clamp(kept, 0.0, 1.0);
  float broken = 0.0, front = -dot(slope, uSeaWind.xy) * uSeaRelief.z;
  if (kept > 0.002 && max(0.55 * crest + 0.75 * front + 0.35 - uSeaFoam.x, before - uSeaFoam.x + 0.7) > 0.0) {
    vec4 laceMean = textureLod(uSeaLace, vec2(0.5), ${Math.log2(LACE_SIZE).toFixed(1)});
    float fine = untiledGrad(uSeaLace, lf, uSeaLaceI.xy, uint(uSeaFoam.z), laceMean, lfx, lfy).g;
    float wide = untiledGrad(uSeaLace, lw, uSeaLaceI.zw, uint(uSeaFoam.z) + 7u, laceMean, lwx, lwy).g;
    // a crest breaking now: white along the steep front of a high crest, a broken line across the wind; where one broke a
    // moment ago: thin streaks drawn out along the wind. Soft patches vary both (long across the wind for the one, along it
    // for the other); no pattern of cells
    float fresh = smoothstep(uSeaFoam.x, uSeaFoam.x + 0.8, 0.55 * crest + 0.75 * front + 0.7 * (wide - 0.5)) * (0.75 + 0.25 * fine);
    float old = smoothstep(uSeaFoam.x - 0.7, uSeaFoam.x + 0.5, before) * smoothstep(0.25, 0.9, fine) * 0.3;
    broken = max(fresh, old);
  }
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
const DEEP = "float seaDepth(vec2 p) { return 1e6; }", OPEN = "float seaShade(vec2 p) { return 1.0; }";
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

const OPTIONS = Object.freeze({state: "breeze", seed: 1, water: "ocean", quality: "standard", waves: null, anchor: Object.freeze([0, 1, 0]), filter: 0.8, depth: null, shoal: 4, shade: null});

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
   * depth) with `shoal` (metres of water over which the bottom's colour fades), `shade` ({glsl, uniforms}: what shades the sun's
   * light on the water, such as `clouds(...).shade` of vidgen/space-clouds: `float seaShade(vec2 p)`, the share of the sun's
   * light that reaches the water p metres from the camera along the sea's +x and +z). */
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
    if (o.shade !== null) {
      known("shade", o.shade, ["glsl", "uniforms"]);
      if (typeof o.shade.glsl !== "string" || !/float\s+seaShade\s*\(\s*vec2/.test(o.shade.glsl)) throw fail("shade.glsl must define `float seaShade(vec2 p)`: the share of the sun's light (0 to 1) that reaches the water p metres from the camera along the sea's +x and +z");
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
    this.uniforms = {...sky.uniforms, uWaveA: {value: A}, uWaveB: {value: B}, uWaveC: {value: C}, uWaveD: {value: D}, uGust: {value: this.list.gusts.map(v4)}, uGustI: {value: this.list.gusts.map(v4)},
      uWarp: {value: this.list.warps.map(v4)}, uWarpI: {value: this.list.warps.map(v4)},
      uWaveE: {value: this.list.waves.map((w) => new THREE.Vector4(...w.wobble, 0))},
      uWaveF: {value: this.list.waves.map((w) => new THREE.Vector3(...warpShares(w)))}, uBendA: {value: [v4(), v4(), v4()]}, uSeaShow: {value: 0}, uSeaRelief: {value: new THREE.Vector4(smooth(RELIEF[0], RELIEF[1], this.state.height / this.state.length), 4 / Math.hypot(this.state.height, this.state.swell ? this.state.swell.height : 0),
        1 / Math.sqrt(Math.max(this.list.waves.reduce((sum, w) => sum + (w.kx * wind[0] + w.kz * wind[1]) ** 2 * w.amplitude ** 2 / 2, 0), 1e-12)), 0)},
      uSeaGeo: {value: new THREE.Vector4(sky.model.radius, 10, sky.options.unit, 0.002)}, uSeaFar: {value: v4()}, uSeaGrid: {value: v4()},
      uSeaBase: {value: new THREE.Vector4(...this.list.base, this.state.gusts)}, uSeaMap: {value: v4()},
      uSeaFoam: {value: new THREE.Vector4(exceeded(Math.max(this.state.cover, 1e-9)), this.state.cover, broadHash(o.seed, 396, 7) & 0xffff, o.filter)},
      uSeaLaceAt: {value: v4()}, uSeaLaceI: {value: v4()}, uSeaOptic: {value: new THREE.Vector4(this.water.index, this.water.glow, Math.sin(sky.options.sunSize * RAD), 1)}, uSeaWind: {value: new THREE.Vector4(wind[0], wind[1], 0, 0)},
      uSeaE1: {value: this.frame.e1}, uSeaE2: {value: this.frame.e2}, uSeaAhead: {value: new THREE.Vector3(1, 0, 0)},
      uSeaBody: {value: new THREE.Vector3(...this.water.color)}, uSeaShallow: {value: new THREE.Vector3(...this.water.shallow)}, uSeaFoamColor: {value: new THREE.Vector3(...this.water.foam)},
      uSeaSky: {value: at.texture}, uSeaAmbient: {value: sky.ambientTexture}, uSeaLace: {value: this._lace.texture},
      uDisplay: {value: 0}, uGrain: {value: 2}, uSeaShoal: {value: o.shoal}, ...(o.depth?.uniforms ?? {}), ...(o.shade?.uniforms ?? {})};
    this.material = new THREE.ShaderMaterial({uniforms: this.uniforms, defines: {NW: n, NG: Math.max(this.list.lifted, 1), FACES: faces}, vertexShader: SEA_VERT, fragmentShader: SEA_FRAG(o.depth?.glsl ?? DEEP, o.shade?.glsl ?? OPEN),
      side: THREE.DoubleSide, depthTest: true, depthWrite: true, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    if (typeof sky.shadowsInto === "function") sky.shadowsInto(this.material);      // the air's shadows in front of the water (vidgen/space-air)
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
    // each noise field's place at the camera: the share of its cell, and its whole cells modulo 65536 (exact in the shader)
    const field = (f, at, whole, w) => {
      const [qx, qz] = fieldPlace(f, x, z, t), cx = Math.floor(qx), cz = Math.floor(qz);
      at.set(f.dir[0] / f.size, f.dir[1] / f.size, qx - cx, qz - cz); whole.set(cx & 0xffff, cz & 0xffff, ...w);
    };
    this.list.gusts.forEach((g, i) => field(g, u.uGust.value[i], u.uGustI.value[i], [g.weight, g.salt]));
    this.list.warps.forEach((f, i) => field(f, u.uWarp.value[i], u.uWarpI.value[i], [f.salt, f.amount * f.size]));
    this.list.bends.forEach((b, i) => u.uBendA.value[i].set(b.kx, b.kz, turn(b.kx * x + b.kz * z - b.omega * t + b.phase), 0));
    const wx = u.uSeaWind.value.x, wz = u.uSeaWind.value.y, along = x * wx + z * wz, across = -x * wz + z * wx, part = (x_) => x_ - Math.floor(x_);
    u.uSeaLaceAt.value.set(part(along / 28), part(across / 7), part(along / 30), part(across / 110));
    u.uSeaLaceI.value.set(Math.floor(along / 28), Math.floor(across / 7), Math.floor(along / 30), Math.floor(across / 110));
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
