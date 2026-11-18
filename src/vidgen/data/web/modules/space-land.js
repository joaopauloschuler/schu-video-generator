// vidgen/space-land: ground with relief under a vidgen/space-air sky (DESIGN.md §123.6). Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-land".
//
//   import {air, sunDirection} from "vidgen/space-air";
//   import {land} from "vidgen/space-land";
//   const sky = air(renderer, "earth", {sun: sunDirection(8, 60)});
//   const ground = land(renderer, sky, {preset: "alpine"});
//   scene.add(sky.object, ground.object);
//   function frame(t) { sky.update(t, {camera}); ground.update(t, {camera}); renderer.render(scene, camera); }
//   const y = ground.heightAt(x, z);              // metres over the world's sphere: for a path, a camera, a thing on the ground
//
// The ground is a height over the world's sphere (the air's radius), a pure function of the place:
// the large forms are the same world's of vidgen/space-bodies (its own bake code, sampled on a lattice
// round the place: the "macro"), the relief under what that map resolves is a seeded recipe (ridged
// mountains worn by a slope-damped sum, terraces, dunes, craters, rough plains). No mesh in the world:
// the heights are baked into square maps of doubling cell size round the camera (a map is baked again
// only when the camera has moved a sixteenth of its width, and a cell of the world has the same height in
// whichever map it lies), each pixel's ray is walked through them at half the picture's size, and every
// pixel of the picture then finds its own place on the ground from its neighbours' answers: an exact
// outline, nothing to pop. Light: the sun after the air, the ground's own shadow (walked through the same
// maps towards the sun, once a map and sun), clouds' shadows, the sky's light, the air between.
import * as THREE from "three";
import {baked} from "vidgen/baked";
import {AIR_GLSL, DISPLAY_GLSL, PSI_TABLE} from "vidgen/space-air";
import {resolveOptions, bakeInputs, surfaceSource, onGlobe, linearColor} from "vidgen/space-bodies";

/** Bumped when the pictures or the heights change: part of the macro's key. */
export const VERSION = 2;
const PREFIX = "vidgen/space-land";
const RAD = Math.PI / 180;
/** By quality: the height maps' cells across for a picture up to 400 rows and for a larger one, the steps of a
 * ray's walk, the share of the picture the walk is done at. */
export const QUALITIES = Object.freeze({fast: [256, 512, 64, 1 / 3], standard: [512, 1024, 96, 1 / 2], fine: [1024, 1024, 144, 1 / 2]});
/** The finest height map's width, metres: every further map is twice as wide (the same for every quality, so
 * a quality changes how fine the cells are, not where a map ends). */
export const WIDTH = 4096;
/** The most height maps (the widest is WIDTH x 2^(MAPS - 1) across, never wider than 1.6 radii). */
export const MAPS = 11;
/** The finest relief the recipe has, metres (a wavelength; under it only the shading's grain). */
export const FINEST = 16;
/** The macro: the lattice's points across and its spacing as a share of the world's radius. */
export const MACRO = Object.freeze({n: 384, spacing: 1 / 400});
/** The octaves a surface type's large forms are summed with (those of a 1024 px map of vidgen/space-bodies). */
export const OCTAVES = Object.freeze({OCT: 7, OCTM: 6});

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
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a), 0, 1); return u * u * (3 - 2 * u); };

// ---------- the noise: pure, the same numbers in JavaScript, in GLSL and in any language with 32-bit integers ----------
/** The sixteen unit gradients of the noise: at (i + 0.5) x 22.5 degrees. */
export const GRADIENTS = Object.freeze(Array.from({length: 16}, (_, i) => Object.freeze([Math.cos((i + 0.5) * Math.PI / 8), Math.sin((i + 0.5) * Math.PI / 8)])));
/** The hash of a lattice point (two integers) and a seed: an unsigned 32-bit integer (wrapping products and shifts only). */
export function hash2(ix, iz, seed) {
  let h = Math.imul(ix | 0, 0x9E3779B1) ^ Math.imul(iz | 0, 0x85EBCA77) ^ Math.imul(seed | 0, 0xC2B2AE3D);
  h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; h = Math.imul(h, 0x297A2D39); h ^= h >>> 15;
  return h >>> 0;
}
/** Gradient noise at (qx, qz) (one lattice cell a unit): [the value (about -1 to 1), its slope along qx, along qz].
 * A corner's gradient is GRADIENTS[hash2(corner, seed) & 15]; quintic fades; times the square root of 2. */
export function noised(qx, qz, seed) {
  const cx = Math.floor(qx), cz = Math.floor(qz), fx = qx - cx, fz = qz - cz;
  const a = GRADIENTS[hash2(cx, cz, seed) & 15], b = GRADIENTS[hash2(cx + 1, cz, seed) & 15], c = GRADIENTS[hash2(cx, cz + 1, seed) & 15], d = GRADIENTS[hash2(cx + 1, cz + 1, seed) & 15];
  const va = a[0] * fx + a[1] * fz, vb = b[0] * (fx - 1) + b[1] * fz, vc = c[0] * fx + c[1] * (fz - 1), vd = d[0] * (fx - 1) + d[1] * (fz - 1);
  const ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10), uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10);
  const dux = 30 * fx * fx * (fx * (fx - 2) + 1), duz = 30 * fz * fz * (fz * (fz - 2) + 1), k = va - vb - vc + vd;
  const v = va + ux * (vb - va) + uz * (vc - va) + ux * uz * k;
  const dx = a[0] + ux * (b[0] - a[0]) + uz * (c[0] - a[0]) + ux * uz * (a[0] - b[0] - c[0] + d[0]) + dux * (vb - va + uz * k);
  const dz = a[1] + ux * (b[1] - a[1]) + uz * (c[1] - a[1]) + ux * uz * (a[1] - b[1] - c[1] + d[1]) + duz * (vc - va + ux * k);
  return [Math.SQRT2 * v, Math.SQRT2 * dx, Math.SQRT2 * dz];
}
/** A crater's height across its radius (d = 1 at the rim), in radii: a bowl with a flat floor, a sharp rim, a gentle apron (vidgen/space-bodies' own). */
export const bowl = (d, floor = 0.8) => (d < 1 ? Math.max(d * d - 1, -floor) : 0) + 0.30 * Math.exp(-Math.pow(Math.abs(d - 1) * (d < 1 ? 8 : 3), 1.5));

// The recipe's readings of the noise ("slots"): each has a length (metres a lattice cell), a turn (radians) and a
// seed; the place (x, z) is read at ((cos x - sin z) / length, (sin x + cos z) / length).
const SLOT = Object.freeze({warp: 0, patch: 2, mountains: 3, rough: 15, strata: 19, dunes: 20, wander: 21, field: 22, ripples: 23, craters: 24, canyon: 29, volcano: 33, count: 34});
/** How round a ridge's crest is (the noise's value under which it is rounded): a crest with a crease would cut the worn slopes beside it apart. */
export const CREST = 0.03;
const TURN = 0.6435;                    // between a mountain octave and the next: the angle of (0.8, 0.6)
/** The crater classes' largest cell as a share of the recipe's `largest` crater's diameter, and each next class's as a share of the one before. */
export const CRATER_CELLS = Object.freeze({first: 1 / 0.6, next: 0.42, classes: 5});

const MOUNTAINS = Object.freeze({height: 4400, length: 19000, ridged: 12, gain: 0.5, erosion: 1, warp: 0.35, sharp: 1.45, mid: 0.26, from: 400, to: 2200, base: 0.05, patch: 900});
const ROUGH = Object.freeze({height: 40, length: 1800, calm: 0.5});
const STRATA = Object.freeze({step: 80, strength: 0, soft: 0.12, wobble: 0.6, length: 5000, from: -1e6, to: -1e6 + 1});
const DUNES = Object.freeze({height: 0, length: 600, direction: 70, wander: 0.9, field: 0.6, from: -1e6, to: 1e6});
const CRATERS = Object.freeze({density: 0, largest: 9000, deep: 0.4});
const CANYONS = Object.freeze({depth: 0, width: 2600, length: 24000, floor: 0.3, steps: 5, branches: 0.6, wander: 0.3});
const VOLCANOES = Object.freeze({height: 0, radius: 9000, spacing: 34000, density: 0.5, crater: 0.13, ridges: 0.1});
/** How soft a canyon wall's risers are in the heights' definition (a share of a step). */
export const RISER = 0.12;
const MATERIALS = Object.freeze({rock: null, rock2: null, snow: null, sand: null, steep: Object.freeze([0.55, 0.95]), scree: 0.5, bands: 0.25, band: 120, snowLine: null, snowSteep: Object.freeze([0.6, 1.0]),
  sandy: 0, grain: 1, rough: 0.75, glow: 0, ground: 1, wide: 8, snowOver: 300, gullies: 0});
const PARTS = {mountains: MOUNTAINS, rough: ROUGH, strata: STRATA, dunes: DUNES, craters: CRATERS, canyons: CANYONS, volcanoes: VOLCANOES, materials: MATERIALS};

/** What each surface type of vidgen/space-bodies gives the ground: `relief` (metres a unit of the type's height
 * field, as a share of the radius), the recipe's defaults for the relief under the map, and which of the bake's
 * colours are the rock, its second layer, the snow or ice and the sand. */
export const TYPES = Object.freeze({
  ocean: {relief: 0.001, sea: true, colors: {rock: 5, rock2: 7, snow: 6, sand: 2}, snowFromClimate: true,
    mountains: {gain: 0.55}, rough: {}, materials: {ground: 0.55, bands: 0.5, band: 55, gullies: 1}},
  desert: {relief: 0.11, sea: false, colors: {rock: [0, 1], rock2: 2, snow: 3, sand: 0},
    mountains: {height: 900, length: 16000, ridged: 2, from: -3000, to: 4000, base: 0.25, patch: 1500, mid: 0.35}, rough: {height: 70, length: 3000, calm: 0.3},
    craters: {density: 0.3, largest: 8000}, strata: {step: 110, strength: 0.6, from: -2500, to: -500}, materials: {steep: [0.45, 0.85], bands: 0.45, band: 160, sandy: 0.35, rough: 0.6}},
  rocky: {relief: 0.2, sea: false, colors: {rock: 0, rock2: 1, snow: 2, sand: 1},
    mountains: {height: 500, length: 11000, ridged: 1, erosion: 0.3, from: -4000, to: 4000, base: 0.5, patch: 2000, sharp: 1, mid: 0.4}, rough: {height: 25, length: 900, calm: 0},
    craters: {density: 0.75, largest: 14000, deep: 0.42}, materials: {steep: [0.5, 0.9], bands: 0, scree: 0.2, rough: 1, grain: 0.8}},
  icy: {relief: 0.2, sea: false, colors: {rock: 2, rock2: 1, snow: 0, sand: 3},
    mountains: {height: 1100, length: 9000, ridged: 4, erosion: 0.8, from: -400, to: 700, base: 0.2, patch: 400, mid: 0.3, sharp: 1.3}, rough: {height: 14, length: 700, calm: 0.2},
    craters: {density: 0.06, largest: 5000, deep: 0.3}, materials: {steep: [0.6, 1.1], bands: 0.1, scree: 0.2, snowLine: -1e5, snowSteep: [0.7, 1.2], rough: 0.5, grain: 0.3}},
  lava: {relief: 0.15, sea: false, colors: {rock: 0, rock2: 1, snow: 2, sand: 1},
    mountains: {height: 650, length: 9000, ridged: 2, erosion: 0.5, from: -1500, to: 2500, base: 0.3, patch: 800, mid: 0.35}, rough: {height: 35, length: 600, calm: 0},
    craters: {density: 0.08, largest: 3000, deep: 0.5}, strata: {step: 45, strength: 0.35, from: -1e5, to: -9e4}, materials: {steep: [0.5, 0.9], bands: 0.2, band: 45, scree: 0.3, rough: 1, grain: 0.8, glow: 1}},
});

/** Ready-made grounds: a `world` of vidgen/space-bodies, a place on it (`at`: latitude and longitude in degrees,
 * chosen for the picture), the recipe's changes, and the `air` that suits it (a name for vidgen/space-air, or
 * null: none, see vacuum()). `alpine`: an Earth-like range with snow. `mars`: a Mars-like desert of dust, craters
 * and low scarps. `canyon`: terraced walls and mesas on the invented world "ochre". `dunes`: a sand sea on the same
 * world. `snow`: the ice world "boreas". `volcanic`: the basalt of "ember", glowing where its crust is open.
 * `airless`: the grey, cratered "moon". */
export const PRESETS = Object.freeze({
  alpine: {world: "earth", at: [-34.5, 20], air: "earth"},
  mars: {world: "mars", at: [-8, 40], air: "mars"},
  canyon: {world: "ochre", at: [49, -172], air: "mars", mountains: {height: 160, length: 30000, ridged: 0, erosion: 0.3, base: 1, mid: 0.5, sharp: 1, patch: 0}, strata: {strength: 0}, craters: {density: 0}, rough: {height: 8},
    canyons: {depth: 1100, width: 2200, length: 24000, floor: 0.5, steps: 4}, materials: {rock: [0.3, 0.15, 0.08], rock2: [0.5, 0.31, 0.18], steep: [0.35, 0.7], bands: 1, band: 90, sandy: 0.3, scree: 0.8}},
  dunes: {world: "ochre", at: [-52, -150], air: "mars", mountains: {height: 250, base: 0.15, length: 30000}, strata: {strength: 0}, craters: {density: 0},
    dunes: {height: 90, length: 520, direction: 70, field: 0.9, wander: 1.3}, rough: {height: 6}, materials: {sandy: 1, steep: [0.75, 1.2], rough: 0.25, grain: 0.35}},
  snow: {world: "boreas", at: [30, 20], air: "thin"},
  volcanic: {world: "ember", at: [10, 60], air: "thin", mountains: {height: 260, base: 0.5}, craters: {density: 0}, strata: {strength: 0}, rough: {height: 22, length: 500},
    volcanoes: {height: 3000, radius: 6500, spacing: 30000, density: 0.6}, materials: {rock: [0.075, 0.07, 0.068], rock2: [0.17, 0.1, 0.075], sand: [0.19, 0.18, 0.175], ground: 0.25, sandy: 0.6, glow: 1}},
  airless: {world: "moon", at: [-30, 20], air: null},
});

const RECIPE_KEYS = ["mountains", "rough", "strata", "dunes", "craters", "canyons", "volcanoes", "materials"];
/** The recipe in full for a surface type: the type's defaults, then `changes` ({mountains, rough, strata, dunes,
 * craters, materials}: each an object of numbers), every key checked, and `slots` (the readings of the noise:
 * {length, turn, seed} each), `octaves` (the mountain octaves summed: down to FINEST), `bound` (how far the relief
 * may stand over and under the macro, metres). `seed`: the relief's own. Pure. */
export function recipeOf(type = "ocean", changes = {}, seed = 1) {
  if (!(type in TYPES)) throw fail(`a ${type} world has no ground to stand on${hint(type, Object.keys(TYPES))}; types with ground: ${Object.keys(TYPES).join(", ")}`);
  known("the recipe", changes, RECIPE_KEYS);
  number("seed", seed, 0, 2 ** 31 - 1);
  const r = {type, seed};
  for (const k of RECIPE_KEYS) {
    if (changes[k] !== undefined) known(k, changes[k], Object.keys(PARTS[k]));
    r[k] = {...PARTS[k], ...(TYPES[type][k] ?? {}), ...(changes[k] ?? {})};
  }
  const m = r.mountains, d = r.dunes, c = r.craters, s = r.strata, g = r.rough, k = r.canyons, v = r.volcanoes;
  number("mountains.height (metres)", m.height, 0, 20000); number("mountains.length (metres)", m.length, 500, 200000); number("mountains.ridged", m.ridged, 0, 12);
  number("mountains.gain", m.gain, 0.2, 0.8); number("mountains.erosion", m.erosion, 0, 3); number("mountains.warp", m.warp, 0, 1); number("mountains.sharp", m.sharp, 0.3, 4);
  number("mountains.mid", m.mid, 0, 1); number("mountains.base", m.base, 0, 1); number("mountains.patch (metres)", m.patch, 0, 20000);
  if (!(m.to > m.from)) throw fail(`mountains.to (${m.to}) must be over mountains.from (${m.from}): the macro's heights between which the mountains grow`);
  number("rough.height (metres)", g.height, 0, 2000); number("rough.length (metres)", g.length, 50, 50000); number("rough.calm", g.calm, 0, 1);
  number("strata.step (metres)", s.step, 5, 2000); number("strata.strength", s.strength, 0, 1); number("strata.soft", s.soft, 0.04, 0.5); number("strata.wobble", s.wobble, 0, 4); number("strata.length (metres)", s.length, 200, 100000);
  number("dunes.height (metres)", d.height, 0, 500); number("dunes.length (metres)", d.length, 60, 20000); number("dunes.direction (degrees)", d.direction, -360, 360); number("dunes.wander", d.wander, 0, 4); number("dunes.field", d.field, 0, 1);
  number("craters.density", c.density, 0, 1); number("craters.largest (metres)", c.largest, 200, 100000); number("craters.deep", c.deep, 0, 1);
  number("canyons.depth (metres)", k.depth, 0, 5000); number("canyons.width (metres)", k.width, 100, 50000); number("canyons.length (metres)", k.length, 2000, 300000); number("canyons.floor", k.floor, 0, 0.9);
  number("canyons.steps", k.steps, 1, 12); number("canyons.branches", k.branches, 0, 1); number("canyons.wander", k.wander, 0, 1);
  number("volcanoes.height (metres)", v.height, 0, 20000); number("volcanoes.radius (metres)", v.radius, 500, 200000); number("volcanoes.spacing (metres)", v.spacing, 3.4 * v.radius, 2e6);
  number("volcanoes.density", v.density, 0, 1); number("volcanoes.crater", v.crater, 0.03, 0.4); number("volcanoes.ridges", v.ridges, 0, 0.4);
  const slots = Array.from({length: SLOT.count}, () => ({length: 1000, turn: 0, seed: 0}));
  const set = (i, length, turn) => { slots[i] = {length, turn, seed: ((seed * 131 + i * 7919) & 0xffff) + 1}; };
  set(SLOT.warp, 2.3 * m.length, 0.3); set(SLOT.warp + 1, 2.3 * m.length, 1.9); set(SLOT.patch, 6 * m.length, 0.9);
  for (let i = 0; i < 12; i++) set(SLOT.mountains + i, m.length / 2 ** i, TURN * i);
  for (let i = 0; i < 4; i++) set(SLOT.rough + i, g.length / 2.1 ** i, 0.4 + 1.1 * i);
  set(SLOT.strata, s.length, 2.2);
  // the dunes' crests lie across the wind: the slot's first axis runs along it (direction: where the wind blows to, 0 = -z, 90 = +x)
  set(SLOT.dunes, d.length, Math.PI / 2 - d.direction * RAD); set(SLOT.wander, 5 * d.length, 0.7); set(SLOT.field, 14 * d.length, 2.6); set(SLOT.ripples, d.length / 4.3, Math.PI / 2 - (d.direction + 24) * RAD);
  for (let i = 0; i < CRATER_CELLS.classes; i++) set(SLOT.craters + i, c.largest * CRATER_CELLS.first * CRATER_CELLS.next ** i, 0.5 * i);
  set(SLOT.canyon, k.length, 0.8); set(SLOT.canyon + 1, k.length / 3.1, 2.1); set(SLOT.canyon + 2, 2.6 * k.length, 0.2); set(SLOT.canyon + 3, 2.6 * k.length, 1.4); set(SLOT.volcano, v.spacing, 0);
  r.slots = slots;
  r.octaves = clamp(Math.floor(Math.log2(m.length / FINEST)) + 1, 1, 12);
  let norm = 0;
  for (let i = 0, a = 1; i < r.octaves; i++, a *= m.gain) norm += a;
  r.norm = norm;
  const crater = c.density > 0 ? 0.3 * slots[SLOT.craters].length * c.deep : 0;
  r.bound = {over: m.height * (1 - m.mid) + 2 * g.height + 0.8 * d.height + 0.4 * crater + s.step + 1.2 * v.height, under: m.height * m.mid + 2 * g.height + 0.7 * d.height + crater + s.step + k.depth};
  return r;
}

// a slot's reading of the place: its two coordinates
const slotAt = (s, x, z) => { const c = Math.cos(s.turn), n = Math.sin(s.turn); return [(c * x - n * z) / s.length, (n * x + c * z) / s.length]; };
// the noise there: the value, and its slope turned back to the place's +x and +z (per lattice cell)
function slotNoise(s, x, z) {
  const c = Math.cos(s.turn), n = Math.sin(s.turn), v = noised((c * x - n * z) / s.length, (n * x + c * z) / s.length, s.seed);
  return [v[0], v[1] * c + v[2] * n, -v[1] * n + v[2] * c];
}
// one class of craters: at most one in each cell of the slot's lattice, read from the cell and its eight neighbours; in cells
function craterClass(s, x, z, density, deep) {
  const q = slotAt(s, x, z), cx = Math.floor(q[0]), cz = Math.floor(q[1]);
  let h = 0;
  for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++) {
    const k = hash2(cx + i, cz + j, s.seed), k2 = hash2(cx + i, cz + j, s.seed + 77);
    if ((k2 & 65535) / 65535 >= density) continue;
    const r3 = ((k >>> 20) & 1023) / 1023, radius = 0.08 + 0.22 * r3 * r3;
    const ex = cx + i + 0.25 + 0.5 * (k & 1023) / 1023, ez = cz + j + 0.25 + 0.5 * ((k >>> 10) & 1023) / 1023;
    h += radius * deep * bowl(Math.hypot(q[0] - ex, q[1] - ez) / radius);
  }
  return h;
}
// a canyon wall across its width (d: 0 the canyon's middle, 1 its rim): 0 on the floor, benches and risers up to 1 at the rim, a little talus
function wallAt(k, d, soft) {
  const u = clamp((d - k.floor) / (1 - k.floor), 0, 1), q = Math.min(u * k.steps, k.steps - 1e-6), f = Math.floor(q);
  return 0.85 * (f + smooth(0.5 - soft, 0.5 + soft, q - f)) / k.steps + 0.15 * u;
}
/** A volcano's height across its radius (d = 1 at its foot) towards the bearing `angle`, as a share of its height: a cone with hollow flanks, ridges down them, a crater at the top. */
export function coneAt(v, d, angle, turn) {
  if (d >= 1) return 0;
  const flank = Math.pow(1 - d, 1.6) * (1 + v.ridges * Math.sin(9 * angle + turn) * smooth(v.crater, 3 * v.crater, d) * (1 - d));
  return Math.min(flank, Math.pow(1 - v.crater, 1.6) - 0.5 * v.crater * smooth(v.crater, 0.55 * v.crater, d));
}
// the volcanoes near a place: at most one in each cell of the slot's lattice: [the height there as a share of `height`, the nearest one's d, its bearing, its turn]
function volcanoAt(s, v, x, z) {
  const q = slotAt(s, x, z), cx = Math.floor(q[0]), cz = Math.floor(q[1]), out = [0, 9, 0, 0];
  for (let j = -1; j <= 1; j++) for (let i = -1; i <= 1; i++) {
    const a = hash2(cx + i, cz + j, s.seed), b = hash2(cx + i, cz + j, s.seed + 77);
    if ((b & 65535) / 65535 >= v.density) continue;
    const size = 0.6 + 0.4 * ((a >>> 20) & 1023) / 1023, ex = q[0] - (cx + i + 0.3 + 0.4 * (a & 1023) / 1023), ez = q[1] - (cz + j + 0.3 + 0.4 * ((a >>> 10) & 1023) / 1023);
    const d = Math.hypot(ex, ez) * s.length / (v.radius * size), angle = Math.atan2(ez, ex), turn = 6.2831853 * ((b >>> 16) & 255) / 255;
    out[0] += size * coneAt(v, d, angle, turn);
    if (d < out[1]) { out[1] = d; out[2] = angle; out[3] = turn; }
  }
  return out;
}
/** The ground's height (metres over the world's sphere) at a place (metres along the frame's +x and +z) where the
 * macro's height is `M` (metres): the recipe's relief on it. The definition of the height; the maps the picture
 * walks through hold the same sum (each term faded as it gets finer than two of a map's cells). Pure. */
export function reliefAt(recipe, M, x, z) {
  const r = recipe, S = r.slots, m = r.mountains, g = r.rough, d = r.dunes, c = r.craters, st = r.strata, k = r.canyons, v = r.volcanoes;
  const wx = slotNoise(S[SLOT.warp], x, z)[0], wz = slotNoise(S[SLOT.warp + 1], x, z)[0], X = x + m.warp * m.length * wx, Z = z + m.warp * m.length * wz;
  const patch = slotNoise(S[SLOT.patch], x, z)[0], level = M + m.patch * patch;
  const mask = m.base + (1 - m.base) * smooth(m.from, m.to, level);
  // ridges whose flanks carry the finer ridges and whose valleys stay smooth: each octave is weighted by the one before (Musgrave's ridged multifractal)
  let sum = 0, a = 1, carry = 1;
  for (let i = 0; i < r.octaves; i++) {
    let v = slotNoise(S[SLOT.mountains + i], X, Z)[0];
    if (i < m.ridged) { const q = 1 + CREST - Math.sqrt(v * v + CREST * CREST); v = q * q; } else v = 0.5 + 0.5 * v;
    sum += a * carry * v; carry = Math.pow(clamp(1.6 * v, 1e-4, 1), m.erosion); a *= m.gain;
  }
  // the mountains' height over their foot, cut into terraces where the recipe has strata (flat benches, cliffs between: mesas)
  let hm = m.height * (Math.pow(sum / r.norm, m.sharp) - m.mid);
  if (st.strength > 0) {
    const wob = st.wobble * slotNoise(S[SLOT.strata], x, z)[0], u = hm / st.step + wob, f = Math.floor(u);
    hm += st.strength * strataShare(st, level) * (st.step * (f + smooth(0.5 - st.soft, 0.5 + st.soft, u - f)) - hm);
  }
  let h = M + mask * hm;
  for (let j = 0, b = 1; j < 4; j++, b *= 0.5) h += g.height * b * (1 - g.calm * mask) * slotNoise(S[SLOT.rough + j], x, z)[0];
  if (d.height > 0) {
    const wander = d.wander * slotNoise(S[SLOT.wander], x, z)[0];
    const field = smooth(1 - 2 * d.field, 1.4 - 2 * d.field, slotNoise(S[SLOT.field], x, z)[0]) * smooth(d.from, d.from + 200, level) * (1 - smooth(d.to - 200, d.to, level)) * (1 - mask);
    const shape = (ph) => { const t = ph - Math.floor(ph); return t < 0.7 ? t / 0.7 : (1 - t) / 0.3; };
    h += d.height * field * (Math.pow(shape(slotAt(S[SLOT.dunes], x, z)[0] + wander), 1.3) - 0.45 + 0.2 * (shape(slotAt(S[SLOT.ripples], x, z)[0] + 2.3 * wander) - 0.5));
  }
  if (c.density > 0) for (let i = 0; i < CRATER_CELLS.classes; i++) h += S[SLOT.craters + i].length * craterClass(S[SLOT.craters + i], x, z, c.density, c.deep);
  if (v.height > 0) h += v.height * volcanoAt(S[SLOT.volcano], v, x, z)[0];
  if (k.depth > 0) {
    // canyons along the lines where a slow noise is zero (a network of winding loops that leaves mesas between), finer ones beside them
    const X2 = x + k.wander * k.length * slotNoise(S[SLOT.canyon + 2], x, z)[0], Z2 = z + k.wander * k.length * slotNoise(S[SLOT.canyon + 3], x, z)[0];
    const d1 = Math.abs(slotNoise(S[SLOT.canyon], X2, Z2)[0]) * k.length / (1.6 * k.width), d2 = Math.abs(slotNoise(S[SLOT.canyon + 1], X2, Z2)[0]) * S[SLOT.canyon + 1].length / (0.72 * k.width);
    h -= k.depth * Math.max(1 - wallAt(k, d1, RISER), k.branches * (1 - wallAt(k, d2, RISER)));
  }
  return h;
}
// where the terraces are cut: everywhere when `from` is under every height, else between the macro's heights from and to (deep canyon floors and walls)
const strataShare = (st, level) => (st.from < -9e5 ? 1 : 1 - smooth(st.from, st.to, level) * 0.85);

// ---------- the macro: the world's own large forms on a lattice round the place ----------
// cubic B-spline weights at a share f of a cell
const spline = (f) => [(1 - f) ** 3 / 6, (3 * f * f * f - 6 * f * f + 4) / 6, (-3 * f * f * f + 3 * f * f + 3 * f + 1) / 6, f * f * f / 6];
/** The macro's fields at a place (metres along the frame's +x and +z): [height (metres), the type's three fields],
 * a cubic B-spline through the lattice (`macro`: {n, spacing (metres), scale (metres a unit), fields: Float32Array
 * of n x n x 4, rows along +z}). Pure. */
export function macroAt(macro, x, z) {
  const n = macro.n, u = clamp(x / macro.spacing + (n - 1) / 2, 0, n - 1), v = clamp(z / macro.spacing + (n - 1) / 2, 0, n - 1);
  const i = Math.floor(u), j = Math.floor(v), wu = spline(u - i), wv = spline(v - j), out = [0, 0, 0, 0];
  for (let b = 0; b < 4; b++) {
    const row = clamp(j - 1 + b, 0, n - 1) * n;
    for (let a = 0; a < 4; a++) {
      const at = (row + clamp(i - 1 + a, 0, n - 1)) * 4, w = wu[a] * wv[b];
      for (let k = 0; k < 4; k++) out[k] += w * macro.fields[at + k];
    }
  }
  out[0] *= macro.scale;
  return out;
}
/** The ground's height, metres over the world's sphere, at a place (metres along the frame's +x and +z): the macro's
 * height there with the recipe's relief on it. `field`: {macro, recipe}. Pure: what `Land.heightAt` answers with. */
export const heightOf = (field, x, z) => reliefAt(field.recipe, macroAt(field.macro, x, z)[0], x, z);
/** The ground's unit normal there, [x, up, z] in the frame, from the heights `reach` metres either side. */
export function normalOf(field, x, z, reach = 4) {
  const sx = (heightOf(field, x + reach, z) - heightOf(field, x - reach, z)) / (2 * reach), sz = (heightOf(field, x, z + reach) - heightOf(field, x, z - reach)) / (2 * reach), l = Math.hypot(sx, 1, sz);
  return [-sx / l, 1 / l, -sz / l];
}
/** A flat macro for a ground without a world's map (and for tests): `height` metres everywhere, the fields zero. */
export function flatMacro(radius, height = 0, scale = 1) {
  const n = 4, fields = new Float32Array(n * n * 4);
  for (let i = 0; i < n * n; i++) fields[4 * i] = height / scale;
  return {n, spacing: radius, scale, fields, colors: null, low: height, high: height};
}

// ---------- the geometry of the view: pure ----------
/** How far the horizon of a sphere `radius` metres in radius is from an eye `height` metres over it, metres along the line of sight. */
export const horizonDistance = (radius, height) => Math.sqrt(Math.max(height, 0) * (2 * radius + Math.max(height, 0)));
/** How far the horizon lies under the eye's level, degrees. */
export const horizonDip = (radius, height) => Math.acos(radius / (radius + Math.max(height, 0))) / RAD;
/** The height over the sphere, metres, of the point `t` metres along a ray from `height` metres whose cosine to the vertical is `mu`. */
export function rayHeight(radius, height, mu, t) { const r0 = radius + height, q = 2 * r0 * mu * t + t * t; return height + q / (Math.sqrt(r0 * r0 + q) + r0); }
/** How many height maps a world of `radius` metres gets, and each map's width, metres. */
export function mapWidths(radius) {
  const count = clamp(Math.floor(Math.log2(1.6 * radius / WIDTH)) + 1, 3, MAPS);
  return Array.from({length: count}, (_, k) => WIDTH * 2 ** k);
}
/** Which height map a place `distance` metres from the camera (the larger of its distances along +x and +z) is read from,
 * before the pixel's own size is counted: map k from 0.4 of map k - 1's width on, blended into the next over the last
 * third (the fraction over 0.7). */
export const mapFor = (distance) => Math.max(0, Math.log2(Math.max(distance, 1e-6) / (0.4 * WIDTH)) + 1);
/** The middle of a map of `width` metres with `cells` cells across for a camera at (x, z): moved in steps of a sixteenth of the width, so a cell stays where it is in the world. */
export function mapMiddle(width, x, z) { const step = width / 16; return [Math.round(x / step) * step, Math.round(z / step) * step]; }
/** The frame of a place on a globe: the unit vectors of the body's axes that are the place's up, east and south (`at`: [latitude, longitude] in degrees). */
export function placeFrame(at) {
  const [lat, lon] = at, a = lat * RAD, o = lon * RAD;
  return {up: onGlobe(lat, lon), east: [-Math.sin(o), 0, -Math.cos(o)], south: [Math.sin(a) * Math.cos(o), -Math.cos(a), -Math.sin(a) * Math.sin(o)]};
}
/** An air so thin that the sky is black, for a world without one (vidgen/space-air needs an air to stand in):
 * `air(renderer, vacuum(1.7374e6))` and a ground under it. `radius`: the world's, metres. */
export const vacuum = (radius = 1.7374e6) => ({air: {rayleigh: [2e-7, 4e-7, 9e-7], haze: [1e-7, 1e-7, 1e-7], absorb: [0, 0, 0], height: 0.002, forward: 0.7, twilight: 0, glow: [0, 0, 0]}, radius, ground: [0.1, 0.1, 0.1]});
/** The radii (metres) of vidgen/space-bodies' airless worlds a ground can lie on (the real ones', invented ones for the invented). */
export const RADII = Object.freeze({mercury: 2.4397e6, moon: 1.7374e6, io: 1.8216e6, europa: 1.5608e6, ganymede: 2.6341e6, callisto: 2.4103e6, cinder: 1.9e6});

// ---------- the same sums in GLSL ----------
const QUAD_VERT = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";
const NUMBERS = ["mHeight", "mLength", "mRidged", "mGain", "mErosion", "mWarp", "mSharp", "mMid", "mFrom", "mTo", "mBase", "mPatch", "norm", "octaves", "gHeight", "gCalm",
  "dHeight", "dWander", "dField", "dFrom", "dTo", "cDensity", "cDeep", "sStep", "sStrength", "sSoft", "sWobble", "sFrom", "sTo",
  "kDepth", "kWidth", "kLength", "kFloor", "kSteps", "kBranches", "kWander", "vHeight", "vRadius", "vDensity", "vCrater", "vRidges"];
// the recipe's numbers in the order the shaders name them
function numbersOf(r) {
  const m = r.mountains, g = r.rough, d = r.dunes, c = r.craters, s = r.strata, k = r.canyons, v = r.volcanoes;
  return [m.height, m.length, m.ridged, m.gain, m.erosion, m.warp, m.sharp, m.mid, m.from, m.to, m.base, m.patch, r.norm, r.octaves, g.height, g.calm,
    d.height, d.wander, d.field, d.from, d.to, c.density, c.deep, s.step, s.strength, s.soft, s.wobble, s.from, s.to,
    k.depth, k.width, k.length, k.floor, k.steps, k.branches, k.wander, v.height, v.radius, v.density, v.crater, v.ridges];
}
const HASH_GLSL = /* glsl */`
const vec2 LAND_G[16] = vec2[16](${GRADIENTS.map((g) => `vec2(${g[0].toFixed(9)}, ${g[1].toFixed(9)})`).join(", ")});
uint landHash(ivec2 c, uint s) {
  uint h = (uint(c.x) * 0x9E3779B1u) ^ (uint(c.y) * 0x85EBCA77u) ^ (s * 0xC2B2AE3Du);
  h ^= h >> 15; h *= 0x2C1B3C6Du; h ^= h >> 12; h *= 0x297A2D39u; h ^= h >> 15;
  return h;
}
// gradient noise in a lattice cell ic at the share f of it: the value, its slope along the cell's two axes
vec3 landNoise(ivec2 ic, vec2 f, uint sd) {
  vec2 g = f - 1.0, a = LAND_G[landHash(ic, sd) & 15u], b = LAND_G[landHash(ic + ivec2(1, 0), sd) & 15u], c = LAND_G[landHash(ic + ivec2(0, 1), sd) & 15u], d = LAND_G[landHash(ic + ivec2(1, 1), sd) & 15u];
  float va = dot(a, f), vb = dot(b, vec2(g.x, f.y)), vc = dot(c, vec2(f.x, g.y)), vd = dot(d, g), k = va - vb - vc + vd;
  vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0), du = 30.0 * f * f * (f * (f - 2.0) + 1.0);
  return 1.41421356 * vec3(va + u.x * (vb - va) + u.y * (vc - va) + u.x * u.y * k, a + u.x * (b - a) + u.y * (c - a) + u.x * u.y * (a - b - c + d) + du * vec2(vb - va + u.y * k, vc - va + u.x * k));
}`;
const VOLCANO_GLSL = /* glsl */`
// a volcano across its radius: the cone's height as a share of its own (as coneAt)
float coneAt(float d, float angle, float turn, float crater, float ridges) {
  if (d >= 1.0) return 0.0;
  float flank = pow(1.0 - d, 1.6) * (1.0 + ridges * sin(9.0 * angle + turn) * smoothstep(crater, 3.0 * crater, d) * (1.0 - d));
  return min(flank, pow(1.0 - crater, 1.6) - 0.5 * crater * smoothstep(crater, 0.55 * crater, d));
}
// the volcanoes near q (the lattice's cells; ic: the whole cells of the place): the summed height, the nearest one's d, its bearing, its turn; set: density, radius in cells, crater, ridges
vec4 volcanoAt(vec2 q, ivec2 ic, uint sd, vec4 set) {
  vec2 c = floor(q); vec4 o = vec4(0.0, 9.0, 0.0, 0.0);
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    uint a = landHash(ic + ivec2(i, j), sd), b = landHash(ic + ivec2(i, j), sd + 77u);
    if (float(b & 65535u) / 65535.0 >= set.x) continue;
    float size = 0.6 + 0.4 * float((a >> 20) & 1023u) / 1023.0;
    vec2 e = q - (c + vec2(float(i), float(j)) + 0.3 + 0.4 * vec2(float(a & 1023u), float((a >> 10) & 1023u)) / 1023.0);
    float d = length(e) / (set.y * size), angle = atan(e.y, e.x), turn = 6.2831853 * float((b >> 16) & 255u) / 255.0;
    o.x += size * coneAt(d, angle, turn, set.z, set.w);
    if (d < o.y) o.yzw = vec3(d, angle, turn);
  }
  return o;
}`;
// a height map: the macro through its spline, the recipe on it, each term faded as it gets finer than two cells
const MAP_FRAG = /* glsl */`
precision highp float; precision highp int;
uniform sampler2D uMacro;
uniform vec4 uMacroAt;           // the map's corner in the lattice's cells (x, z), lattice cells a metre, metres a unit of the macro's height
uniform vec4 uMap;               // a cell (m), the terraces' softness in this map, the lattice's points across, a canyon wall's risers' softness in this map
uniform vec4 uSlotA[${SLOT.count}];           // a slot's rows: (cos, -sin) and (sin, cos) over its length
uniform vec4 uSlotB[${SLOT.count}];           // the map's corner in the slot's cells (the share of a cell), the slot's weight in this map, its seed
uniform vec2 uSlotI[${SLOT.count}];           // the map's corner in the slot's cells (the whole cells)
uniform float uR[${NUMBERS.length}];
uniform vec4 uCount;             // how many of the mountain octaves, the rough octaves and the crater classes this map's cells show; the mean of the first octave not shown
uniform float uTail;             // the sum of the mountain octaves after that one, at their means
${NUMBERS.map((n, i) => `#define R_${n} uR[${i}]`).join("\n")}
${HASH_GLSL}
// the same noise's value alone
float landValue(ivec2 ic, vec2 f, uint sd) {
  vec2 g = f - 1.0, u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float va = dot(LAND_G[landHash(ic, sd) & 15u], f), vb = dot(LAND_G[landHash(ic + ivec2(1, 0), sd) & 15u], vec2(g.x, f.y)), vc = dot(LAND_G[landHash(ic + ivec2(0, 1), sd) & 15u], vec2(f.x, g.y)), vd = dot(LAND_G[landHash(ic + ivec2(1, 1), sd) & 15u], g);
  return 1.41421356 * (va + u.x * (vb - va) + u.y * (vc - va) + u.x * u.y * (va - vb - vc + vd));
}
vec2 slotAt(int s, vec2 l) { vec4 A = uSlotA[s]; return vec2(dot(A.xy, l), dot(A.zw, l)) + uSlotB[s].xy; }
// the noise of a slot at l (metres from the map's corner)
float slotNoise(int s, vec2 l) { vec2 q = slotAt(s, l), c = floor(q); return landValue(ivec2(c) + ivec2(uSlotI[s]), q - c, uint(uSlotB[s].w)); }
float bowl(float d) { return (d < 1.0 ? max(d * d - 1.0, -0.8) : 0.0) + 0.30 * exp(-pow(abs(d - 1.0) * (d < 1.0 ? 8.0 : 3.0), 1.5)); }
float craterClass(int s, vec2 l) {
  vec2 q = slotAt(s, l), c = floor(q); ivec2 ic = ivec2(c) + ivec2(uSlotI[s]); uint sd = uint(uSlotB[s].w); float h = 0.0;
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    uint k = landHash(ic + ivec2(i, j), sd), k2 = landHash(ic + ivec2(i, j), sd + 77u);
    if (float(k2 & 65535u) / 65535.0 >= R_cDensity) continue;
    float r3 = float((k >> 20) & 1023u) / 1023.0, radius = 0.08 + 0.22 * r3 * r3;
    vec2 e = c + vec2(float(i), float(j)) + 0.25 + 0.5 * vec2(float(k & 1023u), float((k >> 10) & 1023u)) / 1023.0;
    h += radius * R_cDeep * bowl(length(q - e) / radius);
  }
  return h;
}
vec4 splineW(float f) { float f2 = f * f, f3 = f2 * f; return vec4((1.0 - f) * (1.0 - f) * (1.0 - f), 3.0 * f3 - 6.0 * f2 + 4.0, -3.0 * f3 + 3.0 * f2 + 3.0 * f + 1.0, f3) / 6.0; }
float macroHeight(vec2 l) {
  float n = uMap.z; vec2 m = clamp(uMacroAt.xy + l * uMacroAt.z, 0.0, n - 1.0), i = floor(m); vec4 wu = splineW(m.x - i.x), wv = splineW(m.y - i.y); float h = 0.0;
  for (int b = 0; b < 4; b++) for (int a = 0; a < 4; a++) h += wu[a] * wv[b] * texelFetch(uMacro, ivec2(clamp(i + vec2(float(a), float(b)) - 1.0, 0.0, n - 1.0)), 0).r;
  return h * uMacroAt.w;
}
${VOLCANO_GLSL}
float wallAt(float d, float soft) {
  float u = clamp((d - R_kFloor) / (1.0 - R_kFloor), 0.0, 1.0), q = min(u * R_kSteps, R_kSteps - 1e-4), f = floor(q);
  return 0.85 * (f + smoothstep(0.5 - soft, 0.5 + soft, q - f)) / R_kSteps + 0.15 * u;
}
float duneShape(float ph) { float t = fract(ph); return t < 0.7 ? t / 0.7 : (1.0 - t) / 0.3; }
void main() {
  vec2 l = gl_FragCoord.xy * uMap.x;
  float M = macroHeight(l);
  vec2 L = l + R_mWarp * R_mLength * vec2(slotNoise(${SLOT.warp}, l), slotNoise(${SLOT.warp + 1}, l));
  float level = M + R_mPatch * slotNoise(${SLOT.patch}, l);
  float mask = R_mBase + (1.0 - R_mBase) * smoothstep(R_mFrom, R_mTo, level);
  // (a software renderer walks every branch for every cell: the loops' lengths are the map's own numbers, a recipe's unused parts are not compiled)
  float sum = 0.0, a = 1.0, carry = 1.0;
  int shown = int(uCount.x);
  for (int i = 0; i < shown; i++) {
    float x = slotNoise(${SLOT.mountains} + i, L), mean = float(i) < R_mRidged ? 0.62 : 0.5;
    if (float(i) < R_mRidged) { float q = ${(1 + CREST).toFixed(3)} - sqrt(x * x + ${(CREST * CREST).toFixed(6)}); x = q * q; } else x = 0.5 + 0.5 * x;
    float v = mix(mean, x, uSlotB[${SLOT.mountains} + i].z);
    sum += a * carry * v; carry = pow(clamp(1.6 * v, 1e-4, 1.0), R_mErosion); a *= R_mGain;
  }
  // the octaves finer than this map's cells stand at their means: the first of them carried by the last one shown, the rest a number of the map's
  sum += a * carry * uCount.w + uTail;
  float hm = R_mHeight * (pow(max(sum / R_norm, 0.0), R_mSharp) - R_mMid);
#ifdef STRATA
  {
    float wob = R_sWobble * slotNoise(${SLOT.strata}, l), u = hm / R_sStep + wob, f = floor(u), e = max(R_sSoft, uMap.y);
    hm += R_sStrength * (R_sFrom < -9e5 ? 1.0 : 1.0 - 0.85 * smoothstep(R_sFrom, R_sTo, level)) * (R_sStep * (f + smoothstep(0.5 - e, 0.5 + e, u - f)) - hm);
  }
#endif
  float h = M + mask * hm;
  float b = 1.0;
  for (int j = 0; j < int(uCount.y); j++) { h += R_gHeight * b * (1.0 - R_gCalm * mask) * uSlotB[${SLOT.rough} + j].z * slotNoise(${SLOT.rough} + j, l); b *= 0.5; }
#ifdef DUNES
  {
    float wander = R_dWander * slotNoise(${SLOT.wander}, l);
    float field = smoothstep(1.0 - 2.0 * R_dField, 1.4 - 2.0 * R_dField, slotNoise(${SLOT.field}, l)) * smoothstep(R_dFrom, R_dFrom + 200.0, level) * (1.0 - smoothstep(R_dTo - 200.0, R_dTo, level)) * (1.0 - mask);
    h += R_dHeight * field * uSlotB[${SLOT.dunes}].z * (pow(duneShape(slotAt(${SLOT.dunes}, l).x + wander), 1.3) - 0.45 + 0.2 * uSlotB[${SLOT.ripples}].z * (duneShape(slotAt(${SLOT.ripples}, l).x + 2.3 * wander) - 0.5));
  }
#endif
#ifdef CRATERS
  for (int i = 0; i < int(uCount.z); i++) h += uSlotB[${SLOT.craters} + i].z * inversesqrt(dot(uSlotA[${SLOT.craters} + i].xy, uSlotA[${SLOT.craters} + i].xy)) * craterClass(${SLOT.craters} + i, l);
#endif
#ifdef VOLCANOES
  { vec2 q = slotAt(${SLOT.volcano}, l), c = floor(q); h += R_vHeight * volcanoAt(q, ivec2(c) + ivec2(uSlotI[${SLOT.volcano}]), uint(uSlotB[${SLOT.volcano}].w), vec4(R_vDensity, R_vRadius * length(uSlotA[${SLOT.volcano}].xy), R_vCrater, R_vRidges)).x; }
#endif
#ifdef CANYONS
  {
    vec2 L2 = l + R_kWander * R_kLength * vec2(slotNoise(${SLOT.canyon + 2}, l), slotNoise(${SLOT.canyon + 3}, l));
    float d1 = abs(slotNoise(${SLOT.canyon}, L2)) * R_kLength / (1.6 * R_kWidth), d2 = abs(slotNoise(${SLOT.canyon + 1}, L2)) / (length(uSlotA[${SLOT.canyon + 1}].xy) * 0.72 * R_kWidth);
    h -= R_kDepth * uSlotB[${SLOT.canyon}].z * max(1.0 - wallAt(d1, uMap.w), R_kBranches * uSlotB[${SLOT.canyon + 1}].z * (1.0 - wallAt(d2, uMap.w)));
  }
#endif
  gl_FragColor = vec4(h, 0.0, 0.0, 1.0);
}`;

/** The uniforms and functions a shader needs to read the ground's height maps (a shadow of a thing on the ground, a
 * wake of dust): include it, give the material `ground.fieldUniforms`, define NL as `ground.maps.length` and call
 * `float landHeight(vec2 p, float foot)`: the ground's height (metres over the world's sphere) `p` metres from the
 * camera along the scene's +x and +z, read from the map whose cells are no finer than `foot` metres. */
export const LAND_GLSL = /* glsl */`
uniform highp sampler2DArray uLandH;
uniform vec4 uLandC[NL];    // a map's middle from the camera (m along +x and +z), one over its width, its cell (m)
uniform vec4 uLandLv;       // the finest map baked, the last map, 0.4 of the finest map's width (m), the finest map's cell (m)
float landLevel(vec2 p, float foot) {
  return clamp(max(log2(max(max(abs(p.x), abs(p.y)), 1e-3) / uLandLv.z) + 1.0, log2(max(foot, 1e-3) / uLandLv.w)), uLandLv.x, uLandLv.y);
}
float landRead(vec2 p, float k) { vec4 C = uLandC[int(k)]; return texture(uLandH, vec3((p - C.xy) * C.z + 0.5, k)).r; }
float landHeight(vec2 p, float foot) {
  float l = landLevel(p, foot), k = floor(l), b = smoothstep(0.7, 1.0, l - k), h = landRead(p, k);
  if (b > 0.0 && k < uLandLv.y) h = mix(h, landRead(p, k + 1.0), b);
  return h;
}`;
const RAY_GLSL = /* glsl */`
uniform vec4 uLandGeo;      // the world's radius (m), the camera's height (m), metres a scene unit, a pixel's angle
uniform vec4 uLandRange;    // the lowest and the highest the ground can be (m), the shortest step (a share of the distance; metres)
uniform vec3 uLandE1, uLandE2, uLandUp;
uniform vec4 uLandRange2;   // the sine of the air's own horizon (under it the dome draws nothing)
varying vec3 vDir;
// where a ray that meets no ground leaves the shell the ground lies in: under the lowest ground, or out through the top
float farRoot(float m, float c, float d) { float s = sqrt(max(d, 0.0)); return m > 0.0 ? -c / (m + s) : -m + s; }
float lastAt(float mu) {
  float R = uLandGeo.x, hc = uLandGeo.y, lo = uLandRange.x, hi = uLandRange.y, m = (R + hc) * mu, ca = (hc - lo) * (2.0 * R + hc + lo), cb = (hc - hi) * (2.0 * R + hc + hi), da = m * m - ca;
  return mu < 0.0 && da > 0.0 && hc > lo ? ca / (-m + sqrt(da)) : farRoot(m, cb, m * m - cb);
}
float altAt(float mu, float t) { float r0 = uLandGeo.x + uLandGeo.y, q = 2.0 * r0 * mu * t + t * t; return uLandGeo.y + q / (sqrt(r0 * r0 + q) + r0); }`;
const RAY_VERT = /* glsl */`
uniform mat4 uLandView; uniform vec4 uLandProj;
varying vec3 vDir;
void main() {
  vDir = mat3(uLandView) * vec3((position.x + uLandProj.z) * uLandProj.x, (position.y + uLandProj.w) * uLandProj.y, -1.0);
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;
// the walk: where each ray of the smaller picture meets the ground, metres along it (-1: nowhere)
const WALK_FRAG = /* glsl */`
${LAND_GLSL}
${RAY_GLSL}
void main() {
  vec3 rd = normalize(vDir);
  float mu = dot(rd, uLandUp), pix = uLandGeo.w, R = uLandGeo.x, hc = uLandGeo.y, lo = uLandRange.x, hi = uLandRange.y;
  vec2 dh = vec2(dot(rd, uLandE1), dot(rd, uLandE2));
  float m = (R + hc) * mu, ca = (hc - lo) * (2.0 * R + hc + lo), cb = (hc - hi) * (2.0 * R + hc + hi), da = m * m - ca, db = m * m - cb;
  bool down = mu < 0.0 && da > 0.0 && hc > lo;      // the ray would go under the lowest ground
  float t0 = 0.0, t1 = down ? ca / (-m + sqrt(da)) : farRoot(m, cb, db);
  if (hc > hi) { if (mu >= 0.0 || db <= 0.0) { gl_FragColor = vec4(-1.0); return; } t0 = cb / (-m + sqrt(db)); }
  float t = max(t0, 0.5), tp = t, g = 1.0, gp = 1.0; bool hit = false;
  for (int i = 0; i < STEPS; i++) {
    g = altAt(mu, t) - landHeight(dh * t, t * pix);
    if (g < 0.0) { hit = true; break; }
    tp = t; gp = g;
    t += max(0.7 * g, t * uLandRange.z + uLandRange.w);
    if (t > t1) break;
  }
  if (hit) {
    for (int i = 0; i < 5; i++) { float tm = 0.5 * (tp + t); if (altAt(mu, tm) - landHeight(dh * tm, tm * pix) < 0.0) t = tm; else tp = tm; }
  } else if (t > t1) {
    // under the lowest ground, or over the last of it but under the air's own horizon (ground lower than the world's sphere): the far ground stands in
    if (!down && mu > uLandRange2.x) { gl_FragColor = vec4(-1.0); return; }
    t = t1;
  }
  gl_FragColor = vec4(t, 0.0, 0.0, 1.0);
}`;
// a map's shadow: from each cell towards the sun through the maps, the share of the sun's light that arrives
const SHADOW_FRAG = /* glsl */`
${LAND_GLSL}
uniform vec4 uShadeSun;     // the sun's direction in the frame (+x, up, +z), one over the world's radius
uniform vec4 uShadeAt;      // the camera's place in the frame (m), the map's cell (m), the map
uniform vec4 uShadeSet;     // the penumbra's width (a tangent), the highest ground (m)
void main() {
  float k = uShadeAt.w, s = uShadeAt.z; vec4 C = uLandC[int(k)];
  vec2 p = C.xy + gl_FragCoord.xy * s - 0.5 / C.z, X = (uShadeAt.xy + p) * uShadeSun.w;
  float sinE = uShadeSun.x * X.x + uShadeSun.z * X.y + uShadeSun.y * sqrt(max(1.0 - dot(X, X), 0.0));
  if (sinE < -0.03) { gl_FragColor = vec4(0.0); return; }
  float tanE = sinE * inversesqrt(max(1.0 - sinE * sinE, 1e-6)), flat_ = length(uShadeSun.xz);
  if (flat_ < 1e-4) { gl_FragColor = vec4(1.0); return; }
  vec2 dir = uShadeSun.xz / flat_;
  float h0 = landRead(p, k), lit = 1.0, d = 1.5 * s;
  for (int i = 0; i < 32; i++) {
    vec2 q = p + dir * d;
    float l = max(k, max(log2(max(max(abs(q.x), abs(q.y)), 1e-3) / uLandLv.z) + 1.0, log2(d / (10.0 * uLandLv.w))));
    if (l > uLandLv.y + 0.45) break;
    float up = h0 + d * tanE + 0.5 * d * d * uShadeSun.w;
    lit = min(lit, 0.5 + (up - landRead(q, floor(l + 0.55))) / (d * uShadeSet.x));
    if (lit <= 0.0 || up > uShadeSet.y) break;
    d *= 1.3;
  }
  gl_FragColor = vec4(clamp(lit, 0.0, 1.0));
}`;
const NONE = "float landShade(vec2 p, float height) { return 1.0; }";
// the picture: each pixel's own place on the ground from its neighbours' answers, the materials, the light, the air between
const LAND_FRAG = (shade) => /* glsl */`
${AIR_GLSL}
${DISPLAY_GLSL}
${LAND_GLSL}
${RAY_GLSL}
${HASH_GLSL}
#ifdef VOLCANOES
${VOLCANO_GLSL}
uniform vec4 uVolc, uVolcSet, uVolcMore;     // the camera's place in the volcanoes' lattice (the share of a cell, the whole cells); density, radius in cells, crater, ridges; cells a metre, the seed
#endif
uniform highp sampler2DArray uLandS;
uniform sampler2D uLandT, uLandMacroA, uLandMacroB, uLandAmbient;
uniform vec4 uLandTSize;    // the walk's picture: its size, its share of this picture
uniform vec4 uLandMacro;    // the camera's place in the lattice's cells (x, z), lattice cells a metre, the lattice's points across
uniform vec4 uDetA[12];     // a grain octave: the camera's place in its cells (the share, the whole cells)
uniform vec4 uLandDet;      // the grain's height at 100 m (m), its roughness (the exponent), how much less on flat ground, its seed
uniform vec4 uMat0;         // the slopes between which rock shows, the scree's share, how much of the macro's colour the flat ground takes
uniform vec4 uMat1;         // the bands' strength, their height (m), the sand's share, the glow
uniform vec4 uSnow;         // the snow line (m), metres a unit of the macro's climate (0: none), the slopes between which snow slides off
uniform vec4 uLandWide;     // metres a unit of the macro's height, how much steeper the large forms are shaded from high up
uniform vec4 uLandLit;      // the hollows' shade, the light thrown back by lit ground, 1: water lies at height 0, the exposure's gain
uniform vec3 uMatRock, uMatRock2, uMatSnow, uMatSand, uMatGround;
uniform float uDisplay, uGrain, uLandShow, uLandSunSize;
uniform mat4 projectionMatrix;
${shade}
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
float gMu; vec2 gDh;
float over(float t) { return altAt(gMu, t) - landHeight(gDh * t, t * uLandGeo.w); }
float landShadow(vec2 p, float l) {
  float k = floor(l), b = smoothstep(0.7, 1.0, l - k); vec4 C = uLandC[int(k)];
  float s = texture(uLandS, vec3((p - C.xy) * C.z + 0.5, k)).r;
  if (b > 0.0 && k < uLandLv.y) { C = uLandC[int(k) + 1]; s = mix(s, texture(uLandS, vec3((p - C.xy) * C.z + 0.5, k + 1.0)).r, b); }
  return s;
}
// a lattice map read smoothly (a cubic B-spline from four readings)
vec4 landSmooth(sampler2D map, vec2 m) {
  float n = uLandMacro.w; m = clamp(m, 0.0, n - 1.0);
  vec2 i = floor(m), f = m - i, f2 = f * f, f3 = f2 * f;
  vec2 w0 = (1.0 - f) * (1.0 - f) * (1.0 - f) / 6.0, w1 = (3.0 * f3 - 6.0 * f2 + 4.0) / 6.0, w3 = f3 / 6.0, w2 = 1.0 - w0 - w1 - w3;
  vec2 g0 = w0 + w1, g1 = w2 + w3, a = (i - 0.5 + w1 / g0) / n, b = (i + 1.5 + w3 / g1) / n;
  return g0.y * (g0.x * texture2D(map, a) + g1.x * texture2D(map, vec2(b.x, a.y))) + g1.y * (g0.x * texture2D(map, vec2(a.x, b.y)) + g1.x * texture2D(map, b));
}
void main() {
  vec3 rd = normalize(vDir);
  float mu = dot(rd, uLandUp), pix = uLandGeo.w, unit = uLandGeo.z;
  gMu = mu; gDh = vec2(dot(rd, uLandE1), dot(rd, uLandE2));
  // the four answers of the walk round this pixel: the nearest and the farthest of them
  ivec2 size = ivec2(uLandTSize.xy), i0 = ivec2(floor(gl_FragCoord.xy * uLandTSize.z - 0.5));
  float tn = 1e20, tf = -1.0, skies = 0.0;
  for (int n = 0; n < 4; n++) { float c = texelFetch(uLandT, clamp(i0 + ivec2(n & 1, n >> 1), ivec2(0), size - 1), 0).r; if (c <= 0.0) skies += 1.0; else { tn = min(tn, c); tf = max(tf, c); } }
  // under the air's own horizon the dome draws nothing: a ray that meets no ground there shows the far ground
  bool under = mu <= uLandRange2.x;
  if (tf < 0.0) { if (!under) discard; tn = tf = lastAt(mu); skies = 0.0; }
  // this pixel's own ray near each: on the ground there (steps of Newton's), or how far over it
  for (int it = 0; it < 3; it++) {
    float e = max(0.003 * tn, 2.0 * tn * pix), g0 = over(tn), gp = (over(tn + e) - g0) / e;
    if (gp < -1e-4) tn += clamp(-g0 / gp, -0.12 * tn, 0.12 * tn);
  }
  for (int it = 0; it < 2; it++) { float e = max(0.003 * tf, 2.0 * tf * pix), g0 = over(tf), gp = (over(tf + e) - g0) / e; if (gp < -1e-4) tf += clamp(-g0 / gp, -0.12 * tf, 0.12 * tf); }
  float gn = over(tn), gf = over(tf), t, cover = 1.0;
  // (rough ground seen along itself: the steps may stop a little over it; only against the sky is a quarter of a pixel asked for)
  if (gn < (skies > 0.0 ? 0.25 : 1.5) * tn * pix) t = tn;
  else if (gf < 0.25 * tf * pix && tf > tn * 1.004) t = tf;
  else if (under) t = max(tf, lastAt(mu));
  else if (skies > 0.0 || mu > uLandRange2.x) {            // an outline against the sky (or a ray over the horizon that clears every answer round it): the pixel beside the ground is its soft edge
    float an = 1.0 - gn / (tn * pix), af = 1.0 - gf / (tf * pix);
    t = an >= af ? tn : tf; cover = max(an, af);
    if (cover <= 0.0) discard;
  } else t = gn / tn < gf / tf ? tn : tf;
  vec3 P = rd * t; vec2 p = gDh * t;
  float r0 = uLandGeo.x + uLandGeo.y, h = landHeight(p, t * pix);
  vec3 upL = normalize(P + uLandUp * r0);
  // a pixel's size on the ground: longer along a level look (the mean of its two sides, at most 2.5 times its width)
  float foot = t * pix * min(inversesqrt(max(-dot(rd, upL), 0.03)), 2.5);
  if (uLandShow > 0.5) { gl_FragDepth = 0.5; gl_FragColor = vec4(p, h, 1.0); return; }
  // the slope from the maps, the grain finer than their cells from the noise
  float l = landLevel(p, foot), cell = uLandLv.w * exp2(l), e = max(cell, foot);
  vec2 grad = vec2(landHeight(p + vec2(e, 0.0), foot) - landHeight(p - vec2(e, 0.0), foot), landHeight(p + vec2(0.0, e), foot) - landHeight(p - vec2(0.0, e), foot)) / (2.0 * e);
  float slope = length(grad), tone = 0.0, fine = 0.0; vec2 grain = vec2(0.0);
  // two slow octaves for the tone; then the four octaves under the map's cells, each faded as it gets finer than the pixel
  int j0 = clamp(int(ceil(9.0 - log2(cell))), 2, 11);
  float gully = uLandWide.z * smoothstep(0.25, 0.7, slope);      // on steep rock the grain is ridges and gullies
  for (int n = 0; n < 6; n++) {
    int j = n < 2 ? n : min(j0 + n - 2, 11);
    float lam = 2048.0 * exp2(-float(j)), w = clamp(lam / (2.5 * foot) - 1.0, 0.0, 1.0) * (n < 2 ? 1.0 : (1.0 - clamp(lam / (2.0 * cell) - 1.0, 0.0, 1.0)) * step(float(j0 + n - 2), 11.5));
    vec2 q = p / lam + uDetA[j].xy, qc = floor(q);
    vec3 v = landNoise(ivec2(qc) + ivec2(uDetA[j].zw), q - qc, uint(uLandDet.w) + uint(j));
    if (n < 2) tone += w * v.x;
    else { grain += w * uLandDet.x * pow(lam / 100.0, uLandDet.y) / lam * mix(v.yz, -1.8 * sign(v.x) * v.yz, gully); fine += w * mix(v.x, 1.0 - 2.4 * abs(v.x), gully); }
  }
  // the world's own colours and climate here
  vec2 mc = uLandMacro.xy + p * uLandMacro.z;
  vec4 mA = landSmooth(uLandMacroA, mc), mB = landSmooth(uLandMacroB, mc);
  float line = uSnow.x + uSnow.y * (mA.r + (mA.b - 0.13) / 0.9);
  // from high up the world's large forms are shaded as the globe of vidgen/space-bodies shades them: steeper than they are (a look, for pixels wider than 150 m on the ground)
  vec2 wide = vec2(landSmooth(uLandMacroA, mc + vec2(0.5, 0.0)).r - landSmooth(uLandMacroA, mc - vec2(0.5, 0.0)).r, landSmooth(uLandMacroA, mc + vec2(0.0, 0.5)).r - landSmooth(uLandMacroA, mc - vec2(0.0, 0.5)).r) * (uLandWide.x * uLandMacro.z);
  grain *= min(1.0, 0.45 * inversesqrt(max(dot(grain, grain), 1e-8)));      // no facet of the grain steeper than 0.45: a single pixel must not catch the sun alone
  vec2 gradD = grad + grain * mix(uLandDet.z, 1.0, smoothstep(0.08, 0.6, slope)) + wide * (uLandWide.y * smoothstep(150.0, 1500.0, foot));
  float slopeD = length(gradD);
  float snow = smoothstep(-120.0, 120.0, h - line + 260.0 * tone + mix(60.0, -140.0, gully) * fine) * (1.0 - smoothstep(uSnow.z, uSnow.w, 0.5 * (slope + slopeD)));
  gradD = mix(gradD, grad + 0.25 * (gradD - grad), snow);
  float shade_ = 1.0 + 0.16 * tone + 0.07 * fine;
  vec3 ground = mix(uMatGround, max(mB.rgb, 0.0), uMat0.w);
  ground = mix(ground, uMatSand, uMat1.z * (1.0 - smoothstep(0.5, 0.9, slope))) * shade_;
  float band = smoothstep(0.25, 0.75, 0.5 + 0.5 * sin(6.2831853 * (h / uMat1.y + 0.8 * tone))) * clamp(uMat1.y / (3.0 * foot) - 0.5, 0.0, 1.0);
  vec3 rock = mix(uMatRock, uMatRock2, uMat1.x * band) * (0.92 + 0.3 * tone + 0.12 * fine);
  vec3 albedo = mix(ground, mix(ground, rock, 0.55) * 1.08, uMat0.z * smoothstep(0.5 * uMat0.x, uMat0.x, slope));
  albedo = mix(albedo, rock, smoothstep(uMat0.x, uMat0.y, slopeD));
  albedo = mix(albedo, uMatSnow, snow);
  float lava = max(mB.a, 0.0) * (0.25 + 0.75 * smoothstep(0.55, 0.95, 1.0 - abs(tone + 0.5 * fine))), warm = 0.0;
#ifdef VOLCANOES
  {
    // a lake in each crater, channels winding down the flanks, fresh flows beside them darker than the old ground, older ones lighter
    vec2 q = p * uVolcMore.x + uVolc.xy, qc = floor(q); vec4 vo = volcanoAt(q, ivec2(qc) + ivec2(uVolc.zw), uint(uVolcMore.y), uVolcSet);
    float d = vo.y, cr = uVolcSet.z, a = vo.z + 0.3 * sin(6.0 * d + vo.w) + 0.12 * tone, run = cos(5.0 * a + vo.w);
    float reach = smoothstep(0.8 * cr, 1.1 * cr, d) * (1.0 - smoothstep(0.6, 1.25, d)), flow = smoothstep(0.8, 0.97, run) * reach;
    lava = max(smoothstep(0.62 * cr, 0.5 * cr, d), smoothstep(0.992, 0.999, run) * reach * (0.65 + 0.35 * fine));
    warm = max(smoothstep(1.6 * cr, 0.5 * cr, d), smoothstep(0.93, 1.0, run) * reach);
    albedo *= (1.0 - 0.55 * flow * (0.6 + 0.4 * tone)) * (1.0 + 0.5 * smoothstep(0.3, 0.9, cos(5.0 * a + vo.w + 2.1)) * reach);
    albedo = mix(albedo, uMatRock * shade_, smoothstep(1.15, 0.7, d) * (1.0 - 0.6 * flow));      // the cone is bare rock, the plain ash
  }
#endif
  // the light: the sun after the air, the ground's shadow and the clouds', the sky's on what is open to it, what lit ground throws back
  vec3 n = normalize(upL - gradD.x * uLandE1 - gradD.y * uLandE2);
  float sunG = dot(uAirSun, upL), ndl = max(dot(n, uAirSun), 0.0), hs = max(h, 0.0) * uAirGeo.w / unit;
  vec3 Tair = exp(-airTau(hs, sunG)) * smoothstep(-uLandSunSize, uLandSunSize, sunG);
  float lit = landShadow(p, l) * landShade(p, h);
  vec3 amb = texture2D(uLandAmbient, vec2(clamp((sunG - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, 0.01, 0.99), 0.5)).rgb;
  float k3 = min(floor(l) + 3.0, uLandLv.y), hollow = clamp(1.0 + uLandLit.x * (h - landRead(p, k3)) / (10.0 * uLandLv.w * exp2(k3)), 0.5, 1.15);
  vec3 back = uLandLit.y * 0.25 * Tair * max(sunG, 0.0) * (1.0 - 0.5 * dot(n, upL));
  vec3 col = uAirLight * albedo * (Tair * lit * ndl + 1.25 * amb * hollow * (0.55 + 0.45 * dot(n, upL)) + back * hollow);
  // lava glows (a volcano's lake and channels, or the macro's open crust broken into cracks by the grain) and lights the ground beside it faintly (a look)
  col += uMat1.w * vec3(1.0, 0.22, 0.03) * (2.5 * lava + 0.05 * warm * (1.0 - lava)) * pow(max(uLandLit.w, 1e-6), 0.8) * (1.0 - snow);
  col *= pow(max(dot(col, LUMA) / uAirDusk.y, 1.0), -uAirDusk.x);
  col = airThrough(col, P / unit);
  // the depth, for the things of the scene and the water: ground under water lies behind everything
  vec4 clip = projectionMatrix * viewMatrix * vec4(cameraPosition + P * (0.997 / unit), 1.0);
  gl_FragDepth = uLandLit.z > 0.5 && h < 0.3 ? 0.9999999 : clamp(0.5 * clip.z / clip.w + 0.5, 0.0, 0.9999999);
  float grainy = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  vec3 shown = display(col);
  float film = mix(uGrain, 1.0, smoothstep(0.45, 0.8, dot(shown, vec3(0.3333))));
  gl_FragColor = uDisplay < 0.5 ? vec4(max(col * (1.0 + grainy * 0.004), 0.0), cover) : vec4(shown + grainy * film / 255.0, cover);
}`;

// ---------- the macro's bake: the world's own code of vidgen/space-bodies, on the lattice ----------
const PLACE_GLSL = /* glsl */`
uniform vec3 uAtUp, uAtEast, uAtSouth; uniform vec4 uLattice;      // the lattice's points across, its spacing over the radius, the relief's push on the paint
uniform sampler2D uFieldsMap;
vec3 placeOf(vec2 cell) {
  if (uLattice.w > 0.5) {      // a survey: the whole globe, a row a latitude from the north, a column a longitude from -180 degrees
    float lat = 1.5707963 - (cell.y + 0.5) / uLattice.w * 3.14159265, lon = ((cell.x + 0.5) / uLattice.x * 2.0 - 1.0) * 3.14159265;
    return vec3(cos(lat) * cos(lon), sin(lat), -cos(lat) * sin(lon));
  }
  vec2 f = (cell - 0.5 * (uLattice.x - 1.0)) * uLattice.y;
  return normalize(uAtUp * sqrt(max(1.0 - dot(f, f), 0.0)) + uAtEast * f.x + uAtSouth * f.y);
}`;
const PAINT_MAIN = /* glsl */`
void main() {
  vec2 cell = floor(gl_FragCoord.xy); vec3 n = placeOf(cell); ivec2 ic = ivec2(cell), top = ivec2(int(uLattice.x) - 1);
  vec4 F = texelFetch(uFieldsMap, ic, 0);
  float hx = texelFetch(uFieldsMap, clamp(ic + ivec2(1, 0), ivec2(0), top), 0).r - texelFetch(uFieldsMap, clamp(ic - ivec2(1, 0), ivec2(0), top), 0).r;
  float hz = texelFetch(uFieldsMap, clamp(ic + ivec2(0, 1), ivec2(0), top), 0).r - texelFetch(uFieldsMap, clamp(ic - ivec2(0, 1), ivec2(0), top), 0).r;
  vec3 albedo; float gloss, glow;
  paint(n, F, length(vec2(hx, hz)) / (2.0 * uLattice.y) * uLattice.z, albedo, gloss, glow);
  gl_FragColor = vec4(clamp(albedo, 0.0, 1.0), glow);
}`;
// the bake's inputs for a ground: a globe's own, without what only a globe shows (the cloud field of an ocean world)
function groundInputs(o) {
  const inputs = bakeInputs(o);
  if (o.type === "ocean") inputs.numbers[10] = 0;
  return inputs;
}
/** The macro of a world round a place: the world's own large forms (the bake code of vidgen/space-bodies with the
 * same numbers from the same seed, its slow fields summed directly where a globe reads them from small cube maps)
 * on a lattice of MACRO.n x MACRO.n points MACRO.spacing radii apart, +x east and +z south of the place. Returns
 * {n, spacing (metres), scale (metres a unit of the type's height), fields (Float32Array, n x n x 4: the height in
 * units and the type's three fields), colors (Float32Array, n x n x 4: the globe's linear colour, its glow), low,
 * high (the heights' range, metres), at, type, targets (the two maps as textures)}. Baked once (vidgen/baked).
 * `world`: a name of vidgen/space-bodies' PRESETS or its options; `at`: [latitude, longitude]; `radius`: metres. */
export function macroOf(renderer, world, at, radius) {
  const o = resolveOptions(world);
  if (!(o.type in TYPES)) throw fail(`a ${o.type} world has no ground to stand on; types with ground: ${Object.keys(TYPES).join(", ")}`);
  if (!Array.isArray(at) || at.length !== 2) throw fail(`at must be [latitude, longitude] in degrees, got ${JSON.stringify(at)}`);
  number("at: the latitude (degrees)", at[0], -90, 90); number("at: the longitude (degrees)", at[1], -360, 360);
  const inputs = groundInputs(o), n = MACRO.n, src = surfaceSource(o.type), frame = placeFrame(at);
  const swap = (glsl) => glsl.replace(/textureCube\(uK(\d), ([^()]+)\)/g, "coarse($2, $1)");
  const kind = {type: THREE.FloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping, depthBuffer: false, generateMipmaps: false};
  const targets = () => [new THREE.WebGLRenderTarget(n, n, kind), new THREE.WebGLRenderTarget(n, n, kind)];
  const draw = ([A, B]) => {
    const uniforms = {uSize: {value: 1024}, uOff: {value: new THREE.Vector3(...inputs.offset)}, uP: {value: inputs.numbers}, uC: {value: inputs.colors.map((c) => new THREE.Vector3(...c))}, uS: {value: inputs.spots.map((s) => new THREE.Vector4(...s))},
      uRight: {value: new THREE.Vector3()}, uUp: {value: new THREE.Vector3()}, uFwd: {value: new THREE.Vector3()}, uK0: {value: null}, uK1: {value: null}, uK2: {value: null}, uRamp: {value: null},
      uAtUp: {value: new THREE.Vector3(...frame.up)}, uAtEast: {value: new THREE.Vector3(...frame.east)}, uAtSouth: {value: new THREE.Vector3(...frame.south)},
      uLattice: {value: new THREE.Vector4(n, MACRO.spacing, inputs.bump, 0)}, uFieldsMap: {value: A.texture}};
    const pass = (fragmentShader) => new THREE.ShaderMaterial({uniforms, defines: {...OCTAVES}, vertexShader: QUAD_VERT, fragmentShader, depthTest: false, depthWrite: false, toneMapped: false});
    const first = pass(`${src.noise}\n${src.coarse}\n${swap(src.fields)}\n${PLACE_GLSL}\nvoid main() { gl_FragColor = fields(placeOf(floor(gl_FragCoord.xy))); }`);
    const second = pass(`${src.noise}\n${src.coarse}\n${swap(src.paint)}\n${PLACE_GLSL}\n${PAINT_MAIN}`);
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), first), scene = new THREE.Scene(), camera = new THREE.Camera(), before = renderer.getRenderTarget(), auto = renderer.autoClear;
    quad.frustumCulled = false; scene.add(quad); renderer.autoClear = true;
    renderer.setRenderTarget(A); renderer.render(scene, camera);
    quad.material = second; renderer.setRenderTarget(B); renderer.render(scene, camera);
    renderer.setRenderTarget(before); renderer.autoClear = auto;
    first.dispose(); second.dispose(); quad.geometry.dispose();
  };
  const made = baked(renderer, "space-land/macro", {version: VERSION, type: o.type, inputs, at, n, spacing: MACRO.spacing, octaves: OCTAVES}, {targets, draw});
  const fields = new Float32Array(n * n * 4), colors = new Float32Array(n * n * 4);
  renderer.readRenderTargetPixels(made[0], 0, 0, n, n, fields); renderer.readRenderTargetPixels(made[1], 0, 0, n, n, colors);
  const scale = TYPES[o.type].relief * radius;
  let low = Infinity, high = -Infinity;
  for (let i = 0; i < n * n; i++) { const h = fields[4 * i] * scale; if (h < low) low = h; if (h > high) high = h; }
  return {n, spacing: MACRO.spacing * radius, scale, fields, colors, low, high, at: [...at], type: o.type, targets: made, inputs};
}
/** A world's large forms all round the globe, to choose a place by: {columns, rows, scale, fields (Float32Array,
 * rows x columns x 4: the height in units and the type's three fields; row 0 the northernmost, column 0 at
 * longitude -180), height(i, j) (metres), at(i, j) ([latitude, longitude] of a cell's middle)}. Not kept between pages. */
export function survey(renderer, world, {columns = 256, rows = 128, radius = 6.371e6} = {}) {
  const o = resolveOptions(world);
  if (!(o.type in TYPES)) throw fail(`a ${o.type} world has no ground to stand on; types with ground: ${Object.keys(TYPES).join(", ")}`);
  number("columns", columns, 8, 2048); number("rows", rows, 4, 1024);
  const inputs = groundInputs(o), src = surfaceSource(o.type);
  const target = new THREE.WebGLRenderTarget(columns, rows, {type: THREE.FloatType, format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false, generateMipmaps: false});
  const material = new THREE.ShaderMaterial({defines: {...OCTAVES}, vertexShader: QUAD_VERT, depthTest: false, depthWrite: false, toneMapped: false,
    fragmentShader: `${src.noise}\n${src.coarse}\n${src.fields.replace(/textureCube\(uK(\d), ([^()]+)\)/g, "coarse($2, $1)")}\n${PLACE_GLSL}\nvoid main() { gl_FragColor = fields(placeOf(floor(gl_FragCoord.xy))); }`,
    uniforms: {uSize: {value: 1024}, uOff: {value: new THREE.Vector3(...inputs.offset)}, uP: {value: inputs.numbers}, uC: {value: inputs.colors.map((c) => new THREE.Vector3(...c))}, uS: {value: inputs.spots.map((s) => new THREE.Vector4(...s))},
      uAtUp: {value: new THREE.Vector3()}, uAtEast: {value: new THREE.Vector3()}, uAtSouth: {value: new THREE.Vector3()}, uLattice: {value: new THREE.Vector4(columns, 0, 0, rows)}, uFieldsMap: {value: null}}});
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material), scene = new THREE.Scene(), before = renderer.getRenderTarget(), fields = new Float32Array(columns * rows * 4);
  quad.frustumCulled = false; scene.add(quad);
  renderer.setRenderTarget(target); renderer.render(scene, new THREE.Camera()); renderer.readRenderTargetPixels(target, 0, 0, columns, rows, fields); renderer.setRenderTarget(before);
  material.dispose(); quad.geometry.dispose(); target.dispose();
  const scale = TYPES[o.type].relief * radius;
  return {columns, rows, scale, fields, type: o.type, height: (i, j) => fields[4 * (j * columns + i)] * scale, at: (i, j) => [90 - (j + 0.5) / rows * 180, (i + 0.5) / columns * 360 - 180]};
}
// a macro given as numbers (flatMacro, or one handed on): its two maps as textures
function macroTextures(macro, ground) {
  const n = macro.n, colors = macro.colors ?? Float32Array.from({length: n * n * 4}, (_, i) => (i % 4 === 3 ? 0 : ground[i % 4]));
  return [macro.fields, colors].map((data) => {
    const t = new THREE.DataTexture(data, n, n, THREE.RGBAFormat, THREE.FloatType);
    Object.assign(t, {minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping, needsUpdate: true});
    return {texture: t, dispose: () => t.dispose()};
  });
}

const OPTIONS = Object.freeze({preset: null, world: null, at: null, seed: null, quality: "standard", macro: null, shade: null, water: null, type: null});

/** Ground with relief under an air: `object` (add it to the scene), `update(t, {camera})`, `heightAt(x, z)`,
 * `normalAt(x, z)`, `pointAt(x, z)`, `above(position)`, `field` ({macro, recipe}: the heights' definition),
 * `depth` (for vidgen/space-sea's `depth`), `behind` (for vidgen/space-clouds' `behind`), `maps`, `horizon`. */
export class Land {
  /** `renderer`: the page's; `sky`: the air of vidgen/space-air the ground lies under (its world's radius is height 0, its
   * sun and exposure light the ground; an airless world: `air(renderer, vacuum(radius))`); `options`: `preset` (a
   * name of PRESETS) or `world` (a name of vidgen/space-bodies' PRESETS or its options) with `at` ([latitude,
   * longitude] of the place under the scene's origin, degrees; +x is east, -z north), `seed` (the relief's own;
   * default the world's), the recipe's parts (`mountains`, `rough`, `strata`, `dunes`, `craters`, `materials`: see
   * recipeOf and DESIGN §123.6), `quality` (a name of QUALITIES), `water` (true: a sea lies at height 0, the ground
   * under it is drawn behind it; default: the world's type has seas), `shade` ({glsl, uniforms}: what shades the
   * sun's light, such as `clouds(...).shade` of vidgen/space-clouds), `macro` (a macro of your own in place of
   * the world's: flatMacro(...), with `type` for the recipe's defaults). */
  constructor(renderer, sky, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("land(renderer, sky, options): the first argument must be the page's THREE.WebGLRenderer");
    if (!sky || !sky.uniforms || !sky.model || typeof sky.under !== "function") throw fail("land(renderer, sky, options): the second argument must be the air the ground lies under (air(renderer, ...) of vidgen/space-air; for a world without air: air(renderer, vacuum(radius)))");
    known("the options", options, [...Object.keys(OPTIONS), ...RECIPE_KEYS]);
    let o = {...OPTIONS, ...options}, base = {};
    if (o.preset !== null) {
      const key = String(o.preset).trim().toLowerCase();
      if (!(key in PRESETS)) throw fail(`no ground "${o.preset}"${hint(key, Object.keys(PRESETS))}; ready-made: ${Object.keys(PRESETS).join(", ")}`);
      base = PRESETS[key];
      o = {...o, world: o.world ?? base.world, at: o.at ?? base.at};
    }
    if (!(o.quality in QUALITIES)) throw fail(`quality must be one of ${Object.keys(QUALITIES).join(", ")}, got ${JSON.stringify(o.quality)}${hint(o.quality, Object.keys(QUALITIES))}`);
    this.options = o; this.renderer = renderer; this.sky = sky;
    const R = sky.model.radius, unit = sky.options.unit;
    let type, world = null;
    if (o.macro !== null) {
      known("macro", o.macro, ["n", "spacing", "scale", "fields", "colors", "low", "high", "at", "type", "targets", "inputs"]);
      type = o.type ?? o.macro.type ?? "rocky";
      this.macro = o.macro;
    } else {
      if (o.world === null) throw fail(`state the ground: a preset (${Object.keys(PRESETS).join(", ")}), or a world of vidgen/space-bodies with at: [latitude, longitude]`);
      world = resolveOptions(o.world); type = world.type;
      /** The world's large forms round the place (see macroOf). */
      this.macro = macroOf(renderer, o.world, o.at ?? [0, 0], R);
    }
    const changes = {};
    for (const k of RECIPE_KEYS) if (base[k] !== undefined || options[k] !== undefined) changes[k] = {...(base[k] ?? {}), ...(options[k] ?? {})};
    /** The relief's recipe in full (see recipeOf). */
    this.recipe = recipeOf(type, changes, o.seed ?? (world ? world.seed : 1));
    /** The heights' definition: `heightOf(ground.field, x, z)` (x, z: metres in the frame). */
    this.field = {macro: this.macro, recipe: this.recipe};
    this.type = type;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2()), [small, large, steps, share] = QUALITIES[o.quality];
    this.cells = size.y <= 400 ? small : large; this.share = share;
    /** The height maps' widths, metres, the finest first. */
    this.maps = mapWidths(R);
    const nl = this.maps.length, cell0 = WIDTH / this.cells, v4 = () => new THREE.Vector4(), v3 = () => new THREE.Vector3();
    const kind = {format: THREE.RedFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping, depthBuffer: false, generateMipmaps: false};
    this.heights = new THREE.WebGLArrayRenderTarget(this.cells, this.cells, nl, {...kind, type: THREE.FloatType});
    this.shadows = new THREE.WebGLArrayRenderTarget(this.cells, this.cells, nl, {...kind, type: THREE.UnsignedByteType});
    this.walk = new THREE.WebGLRenderTarget(4, 4, {...kind, type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter});
    this._made = this.macro.targets ? null : macroTextures(this.macro, [0.2, 0.19, 0.18]);
    const maps = this.macro.targets ?? this._made;
    // the materials: the world's own colours for rock, snow and sand unless stated
    const mat = this.recipe.materials, tints = TYPES[type].colors, own = this.macro.inputs ? this.macro.inputs.colors : null;
    const pick = (which) => (Array.isArray(which) ? own[which[0]].map((x, i) => 0.5 * (x + own[which[1]][i])) : own[which]);
    const tint = (key, fallback, gain = 1) => (mat[key] !== null ? linearColor(`materials.${key}`, mat[key]) : own ? pick(tints[key]).map((x) => clamp(x * gain, 0, 1)) : fallback);
    this.colors = {rock: tint("rock", [0.16, 0.15, 0.14], type === "ocean" ? 0.9 : 0.75), rock2: tint("rock2", [0.24, 0.22, 0.2], type === "ocean" ? 1 : 0.9), snow: tint("snow", [0.85, 0.87, 0.9]), sand: tint("sand", [0.42, 0.33, 0.22])};
    const climate = TYPES[type].snowFromClimate && mat.snowLine === null && this.macro.inputs;
    const water = o.water ?? (TYPES[type].sea && o.macro === null);
    /** What a shader of another module needs to read the height maps with LAND_GLSL. */
    this.fieldUniforms = {uLandH: {value: this.heights.texture}, uLandC: {value: Array.from({length: nl}, v4)}, uLandLv: {value: new THREE.Vector4(0, nl - 1, 0.4 * WIDTH, cell0)}, uLandAt: {value: v4()}};
    const ray = {uLandGeo: {value: new THREE.Vector4(R, 10, unit, 0.002)}, uLandRange: {value: new THREE.Vector4(this.macro.low - this.recipe.bound.under - 1, this.macro.high + this.recipe.bound.over + 1, 0.01, 0.25 * cell0)},
      uLandRange2: {value: v4()}, uLandE1: {value: new THREE.Vector3(1, 0, 0)}, uLandE2: {value: new THREE.Vector3(0, 0, 1)}, uLandUp: {value: new THREE.Vector3(0, 1, 0)}, uLandView: {value: new THREE.Matrix4()}, uLandProj: {value: v4()}};
    this.uniforms = {...sky.uniforms, ...this.fieldUniforms, ...ray, uLandS: {value: this.shadows.texture}, uLandT: {value: this.walk.texture}, uLandTSize: {value: new THREE.Vector4(4, 4, share, 0)},
      uLandMacroA: {value: maps[0].texture}, uLandMacroB: {value: maps[1].texture}, uLandAmbient: {value: sky.ambientTexture}, uLandMacro: {value: new THREE.Vector4(0, 0, 1 / this.macro.spacing, this.macro.n)},
      uDetA: {value: Array.from({length: 12}, v4)}, uLandDet: {value: new THREE.Vector4(3 * mat.grain, 0.75, 1 - mat.rough * 0.8, (this.recipe.seed * 31 + 977) & 0xffff)},
      uMat0: {value: new THREE.Vector4(mat.steep[0], mat.steep[1], mat.scree, mat.ground)}, uMat1: {value: new THREE.Vector4(mat.bands, mat.band, mat.sandy, mat.glow)},
      uSnow: {value: new THREE.Vector4(climate ? mat.snowOver : (mat.snowLine ?? 1e9), climate ? this.macro.scale : 0, mat.snowSteep[0], mat.snowSteep[1])},
      uLandLit: {value: new THREE.Vector4(1.2, 1, water ? 1 : 0, 1)}, uLandWide: {value: new THREE.Vector4(this.macro.scale, mat.wide, mat.gullies, 0)}, uVolc: {value: v4()}, uVolcSet: {value: new THREE.Vector4(this.recipe.volcanoes.density, this.recipe.volcanoes.radius / this.recipe.volcanoes.spacing, this.recipe.volcanoes.crater, this.recipe.volcanoes.ridges)},
      uVolcMore: {value: new THREE.Vector4(1 / this.recipe.volcanoes.spacing, this.recipe.slots[SLOT.volcano].seed, 0, 0)}, uMatRock: {value: v3().set(...this.colors.rock)}, uMatRock2: {value: v3().set(...this.colors.rock2)}, uMatSnow: {value: v3().set(...this.colors.snow)},
      uMatSand: {value: v3().set(...this.colors.sand)}, uMatGround: {value: v3().set(...this.colors.sand)}, uDisplay: {value: 0}, uGrain: {value: 2}, uLandShow: {value: 0}, uLandSunSize: {value: Math.sin(sky.options.sunSize * RAD)},
};
    // the bake of a map, of its shadow, the walk: a quad each
    const quad = (material) => { const mesh = new THREE.Mesh(this._plane, material); mesh.frustumCulled = false; const scene = new THREE.Scene(); scene.add(mesh); return {scene, material}; };
    this._plane = new THREE.PlaneGeometry(2, 2); this._camera = new THREE.Camera();
    const slotA = this.recipe.slots.map((s) => new THREE.Vector4(Math.cos(s.turn) / s.length, -Math.sin(s.turn) / s.length, Math.sin(s.turn) / s.length, Math.cos(s.turn) / s.length));
    this._bake = quad(new THREE.ShaderMaterial({vertexShader: QUAD_VERT, fragmentShader: MAP_FRAG, depthTest: false, depthWrite: false, toneMapped: false,
      defines: {...(this.recipe.canyons.depth > 0 ? {CANYONS: 1} : {}), ...(this.recipe.volcanoes.height > 0 ? {VOLCANOES: 1} : {}), ...(this.recipe.dunes.height > 0 ? {DUNES: 1} : {}), ...(this.recipe.craters.density > 0 ? {CRATERS: 1} : {}), ...(this.recipe.strata.strength > 0 ? {STRATA: 1} : {})},
      uniforms: {uMacro: {value: maps[0].texture}, uMacroAt: {value: v4()}, uMap: {value: v4()}, uCount: {value: v4()}, uTail: {value: 0}, uSlotA: {value: slotA}, uSlotB: {value: this.recipe.slots.map(v4)}, uSlotI: {value: this.recipe.slots.map(() => new THREE.Vector2())}, uR: {value: numbersOf(this.recipe)}}}));
    this._shade = quad(new THREE.ShaderMaterial({vertexShader: QUAD_VERT, fragmentShader: SHADOW_FRAG, defines: {NL: nl}, depthTest: false, depthWrite: false, toneMapped: false,
      uniforms: {...this.fieldUniforms, uShadeSun: {value: v4()}, uShadeAt: {value: v4()}, uShadeSet: {value: new THREE.Vector4(0.06, 0, 0, 0)}}}));
    this._walk = quad(new THREE.ShaderMaterial({vertexShader: RAY_VERT, fragmentShader: WALK_FRAG, defines: {NL: nl, STEPS: steps}, depthTest: false, depthWrite: false, toneMapped: false, uniforms: {...this.fieldUniforms, ...ray}}));
    this.material = new THREE.ShaderMaterial({uniforms: this.uniforms, defines: {NL: nl, ...(this.recipe.volcanoes.height > 0 ? {VOLCANOES: 1} : {})}, vertexShader: RAY_VERT, fragmentShader: LAND_FRAG(NONE), depthTest: true, depthFunc: THREE.AlwaysDepth, depthWrite: true, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    /** The ground: drawn after the air's dome and before the sea, the clouds and the scene's other things (which it hides where they are behind it: it writes its depth). */
    this.object = new THREE.Mesh(this._plane, this.material);
    this.object.name = `land ${o.preset ?? (world ? world.name ?? type : type)}`; this.object.frustumCulled = false; this.object.renderOrder = -860;
    const view = new THREE.Vector4();
    this.object.onBeforeRender = (r) => {
      r.getCurrentViewport(view);
      this.uniforms.uDisplay.value = r.getRenderTarget() === null ? 1 : 0;
      this.uniforms.uLandTSize.value.z = this.walk.height / view.w;
      this.material.uniformsNeedUpdate = true;
    };
    if (o.shade !== null) this.shadedBy(o.shade);
    /** The water's depth for vidgen/space-sea: `sea(renderer, sky, {depth: ground.depth})` (a coast: the sea ends where the ground rises out of it). */
    this.depth = {glsl: `#define NL ${nl}\n${LAND_GLSL}\nuniform vec4 uLandAt;\nfloat seaDepth(vec2 p) { return -landHeight(p - uLandAt.xy, 8.0); }`, uniforms: this.fieldUniforms};
    /** How far the ground is on each ray of the walk's picture, for vidgen/space-clouds: `clouds(renderer, sky, {behind: ground.behind})` (a cloud behind a mountain is hidden by it). */
    this.behind = {texture: this.walk.texture};
    sky.under(true);
    /** What the last update found: the horizon's `distance` (metres) and `dip` (degrees) for a smooth world, the camera's `height` over the sphere and `over` the ground under it (metres), `finest` (the finest map in use). */
    this.horizon = {distance: 0, dip: 0, height: 0, over: 0, finest: 0};
    this._middles = this.maps.map(() => null); this._shaded = this.maps.map(() => null); this._sun = "";
    /** How many height maps and shadows the updates have baked so far. */
    this.bakes = {maps: 0, shadows: 0};
    this.material.addEventListener("dispose", () => { this.heights.dispose(); this.shadows.dispose(); this.walk.dispose(); for (const q of [this._bake, this._shade, this._walk]) q.material.dispose(); if (this._probe) { this._probe.target.dispose(); this._probe.material.dispose(); } if (this._pack) { this._pack.material.dispose(); this._unpack.material.dispose(); } if (this._made) this._made.forEach((m) => m.dispose()); });
  }

  /** Let something shade the sun's light on the ground: `shade` is {glsl, uniforms} whose GLSL defines `float landShade(vec2 p,
   * float height)` (the share of the sun's light, 0 to 1, that reaches the place p metres from the camera along +x and +z at
   * that height), or the `shade` of vidgen/space-clouds. As the option `shade`, for clouds made after the ground
   * (`clouds(renderer, sky, {behind: ground.behind})`, then `ground.shadedBy(weather.shade)`). Returns the ground. */
  shadedBy(shade) {
    known("shade", shade, ["glsl", "uniforms"]);
    if (typeof shade.glsl !== "string" || !/float\s+(landShade|cloudShade)\s*\(\s*vec2\s+\w+\s*,\s*float/.test(shade.glsl)) throw fail("shade.glsl must define `float landShade(vec2 p, float height)` (or be the `shade` of vidgen/space-clouds): the share of the sun's light (0 to 1) that reaches the place p metres from the camera along +x and +z at that height");
    Object.assign(this.uniforms, shade.uniforms ?? {});
    this.material.fragmentShader = LAND_FRAG(/float\s+landShade\s*\(/.test(shade.glsl) ? shade.glsl : `${shade.glsl}\nfloat landShade(vec2 p, float height) { return cloudShade(p, height); }`);
    this.material.needsUpdate = true;
    return this;
  }

  /** How strongly lava glows from now on (1: the recipe's own `materials.glow` of 1; 0: none): call it every frame with a level of `ctx.music` for a glow that pulses. Returns the ground. */
  setGlow(level) { this.uniforms.uMat1.value.w = number("setGlow: the level", level, 0, 20); return this; }

  // a scene place in the frame, metres
  _flat(x, z) { const c = this.sky.state.center, unit = this.sky.options.unit; return [(x - c[0]) * unit, (z - c[2]) * unit]; }
  /** The ground's height, metres over the world's sphere, at the scene's (x, z): the heights' definition (what the finest map draws). */
  heightAt(x, z) { return heightOf(this.field, ...this._flat(x, z)); }
  /** The ground's unit normal there, [x, up, z]. */
  normalAt(x, z) { return normalOf(this.field, ...this._flat(x, z)); }
  /** The point of the ground at the scene's (x, z), in scene units: its y is where the ground is there (the world's sphere drops with distance from the origin, the height lifts it). */
  pointAt(x, z) {
    const [fx, fz] = this._flat(x, z), R = this.sky.model.radius, unit = this.sky.options.unit, c = this.sky.state.center;
    if (fx * fx + fz * fz >= R * R) throw fail("pointAt: the place is beyond the world's edge as the frame sees it");
    const r = R + heightOf(this.field, fx, fz);
    return [c[0] + fx / unit, c[1] + Math.sqrt(r * r - fx * fx - fz * fz) / unit, c[2] + fz / unit];
  }
  /** How high a point of the scene ([x, y, z] or a Vector3) stands over the ground under it, metres (negative: inside the ground). */
  above(position) {
    const p = Array.isArray(position) ? position : [position.x, position.y, position.z], c = this.sky.state.center, unit = this.sky.options.unit;
    const d = [(p[0] - c[0]) * unit, (p[1] - c[1]) * unit, (p[2] - c[2]) * unit];
    return Math.hypot(...d) - this.sky.model.radius - heightOf(this.field, d[0], d[2]);
  }
  /** The heights' definition as plain data, for another program (a flight path worked out in Python): {radius, recipe
   * (its numbers and `slots`), macro: {n, spacing, scale, heights: the lattice's heights in units, row by row along +z}}. */
  definition() {
    const m = this.macro;
    return {radius: this.sky.model.radius, recipe: JSON.parse(JSON.stringify(this.recipe)), macro: {n: m.n, spacing: m.spacing, scale: m.scale, heights: Array.from({length: m.n * m.n}, (_, i) => m.fields[4 * i])}};
  }

  /** A cell of a height map as it was baked (for a check of the maps against `heightAt`): {height (metres), x, z (the cell's middle in the frame, metres)}. `map`: 0 the finest; `i`, `j`: the cell along +x and +z. */
  cell(map, i, j) {
    if (!this._middles[map]) throw fail(`cell: the map ${map} is not baked (the last update's finest was ${this.horizon.finest})`);
    if (!this._probe) {
      this._probe = {target: new THREE.WebGLRenderTarget(1, 1, {type: THREE.FloatType, format: THREE.RGBAFormat, depthBuffer: false}), scene: new THREE.Scene(),
        material: new THREE.ShaderMaterial({vertexShader: QUAD_VERT, fragmentShader: "uniform highp sampler2DArray uLandH; uniform vec3 uCell; void main() { gl_FragColor = vec4(texelFetch(uLandH, ivec3(uCell), 0).r); }", uniforms: {uLandH: {value: this.heights.texture}, uCell: {value: new THREE.Vector3()}}, depthTest: false, depthWrite: false, toneMapped: false})};
      const mesh = new THREE.Mesh(this._plane, this._probe.material); mesh.frustumCulled = false; this._probe.scene.add(mesh);
    }
    const r = this.renderer, before = r.getRenderTarget(), out = new Float32Array(4), [mx, mz] = this._middles[map].split("|").map(Number), W = this.maps[map], cell = W / this.cells;
    this._probe.material.uniforms.uCell.value.set(i, j, map); this._probe.material.uniformsNeedUpdate = true;
    r.setRenderTarget(this._probe.target); r.render(this._probe.scene, this._camera); r.readRenderTargetPixels(this._probe.target, 0, 0, 1, 1, out); r.setRenderTarget(before);
    return {height: out[0], x: mx - W / 2 + (i + 0.5) * cell, z: mz - W / 2 + (j + 0.5) * cell};
  }

  // a height map: baked, or taken from vidgen's cache of baked maps (the heights' own bits as four bytes a cell, so what comes back is what was baked).
  // Kept: every map of the first update (a still, a camera at rest, the start of a shot) and later the maps from the fourth on (32 km wide: they move rarely)
  _map(k, key, keep) {
    if (!keep || !this.macro.inputs) { this._draw(this._bake, this.heights, k); return; }
    const N = this.cells, m = this.macro, r = this.renderer;
    if (!this._pack) {
      const quad = (fragmentShader, uniforms) => { const material = new THREE.ShaderMaterial({vertexShader: QUAD_VERT, fragmentShader, uniforms, depthTest: false, depthWrite: false, toneMapped: false}), mesh = new THREE.Mesh(this._plane, material), scene = new THREE.Scene(); mesh.frustumCulled = false; scene.add(mesh); return {scene, material}; };
      this._pack = quad("uniform highp sampler2DArray uLandH; uniform float uLayer; void main() { uint b = floatBitsToUint(texelFetch(uLandH, ivec3(gl_FragCoord.xy, int(uLayer)), 0).r); gl_FragColor = vec4(float(b & 255u), float((b >> 8) & 255u), float((b >> 16) & 255u), float(b >> 24)) / 255.0; }", {uLandH: {value: this.heights.texture}, uLayer: {value: 0}});
      this._unpack = quad("uniform sampler2D uPacked; void main() { uvec4 u = uvec4(texelFetch(uPacked, ivec2(gl_FragCoord.xy), 0) * 255.0 + 0.5); gl_FragColor = vec4(uintBitsToFloat(u.x | (u.y << 8) | (u.z << 16) | (u.w << 24))); }", {uPacked: {value: null}});
    }
    let drawn = false;
    const [packed] = baked(r, "space-land/map", {version: VERSION, map: k, middle: key, cells: N, radius: this.sky.model.radius, numbers: numbersOf(this.recipe), slots: this.recipe.slots, macro: {type: m.type, inputs: m.inputs, at: m.at, n: m.n}}, {
      targets: () => [new THREE.WebGLRenderTarget(N, N, {type: THREE.UnsignedByteType, format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false, generateMipmaps: false})],
      draw: ([target]) => { this._draw(this._bake, this.heights, k); this._pack.material.uniforms.uLayer.value = k; this._pack.material.uniformsNeedUpdate = true; this._draw(this._pack, target); drawn = true; },
    });
    if (!drawn) { this._unpack.material.uniforms.uPacked.value = packed.texture; this._unpack.material.uniformsNeedUpdate = true; this._draw(this._unpack, this.heights, k); }
    packed.dispose();
  }

  _draw(pass, target, layer) { const r = this.renderer; r.setRenderTarget(target, layer); r.render(pass.scene, this._camera); }

  /** The ground for `camera` (the THREE.PerspectiveCamera the picture is drawn with): the height maps round it (baked
   * where it has moved on), their shadows for the sun now, and the walk of every ray. Call it before every draw,
   * after the air's `update` with the same camera, before the sea's and the clouds'. `t`: the scene's time (the ground does not change with it). */
  update(t = 0, {camera = null} = {}) {
    number("update: the time (seconds)", t, -1e9, 1e9);
    if (!camera || !camera.isPerspectiveCamera) throw fail("update(t, {camera}): the camera the picture is drawn with (a THREE.PerspectiveCamera)");
    const sky = this.sky, R = sky.model.radius, unit = sky.options.unit, r = this.renderer, u = this.uniforms, nl = this.maps.length, cell0 = WIDTH / this.cells;
    camera.updateMatrixWorld();
    const e = camera.matrixWorld.elements, c = sky.state.center, d = [(e[12] - c[0]) * unit, (e[13] - c[1]) * unit, (e[14] - c[2]) * unit];
    const hc = Math.hypot(...d) - R, x = d[0], z = d[2], ground = heightOf(this.field, x, z), over = hc - ground;
    const size = r.getDrawingBufferSize(new THREE.Vector2()), w = Math.max(2, Math.ceil(size.x * this.share)), hgt = Math.max(2, Math.ceil(size.y * this.share));
    if (this.walk.width !== w || this.walk.height !== hgt) this.walk.setSize(w, hgt);
    const p = camera.projectionMatrix.elements, pix = 2 / (p[5] * size.y);
    // the finest map worth baking: its cells no finer than two thirds of a pixel on the ground under the camera
    // and no finer than the nearest ground in the picture needs: under the steepest ray of the picture's corners, at half the camera's height over the ground (a camera within 300 m of the ground keeps every map)
    let mu = 1;
    for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, -1], [0, 1]]) {
      const v = [(sx + p[8]) / p[0], (sy + p[9]) / p[5], -1], w3 = [0, 1, 2].map((i) => e[i] * v[0] + e[4 + i] * v[1] + e[8 + i] * v[2]);
      mu = Math.min(mu, (w3[0] * d[0] + w3[1] * d[1] + w3[2] * d[2]) / (Math.hypot(...w3) * (R + hc)));
    }
    const near = over > 300 && mu < -0.05 ? 0.5 * over * Math.sqrt(1 - mu * mu) / -mu : 0;
    const finest = clamp(Math.max(Math.floor(Math.log2(Math.max(over, 2) * pix / (1.5 * cell0))), Math.floor(Math.log2(Math.max(near, 1) / (0.4 * WIDTH)) + 1)), 0, nl - 2);
    const before = r.getRenderTarget(), auto = r.autoClear, colour = r.getClearColor(new THREE.Color()), alpha = r.getClearAlpha();
    r.autoClear = true; r.setClearColor(0x000000, 0);
    const bake = this._bake.material.uniforms, m = this.macro, first = this.bakes.maps === 0;
    for (let k = finest; k < nl; k++) {
      const W = this.maps[k], cell = W / this.cells, mid = mapMiddle(W, x, z), key = `${mid[0]}|${mid[1]}`;
      u.uLandC.value[k].set(mid[0] - x, mid[1] - z, 1 / W, cell);
      if (key === this._middles[k]) continue;
      // every reading's place at the map's corner, worked out here in double precision: whole cells and the share of one
      const ox = mid[0] - W / 2, oz = mid[1] - W / 2;
      this.recipe.slots.forEach((s, i) => {
        const cs = Math.cos(s.turn), sn = Math.sin(s.turn), qx = (cs * ox - sn * oz) / s.length, qz = (sn * ox + cs * oz) / s.length;
        const octave = i >= SLOT.mountains && i < SLOT.mountains + 12 || i >= SLOT.rough && i < SLOT.rough + 4, feature = i === SLOT.dunes || i === SLOT.ripples ? 0.5 : i >= SLOT.craters ? 0.3 : 0;
        const kk = this.recipe.canyons, canyon = i === SLOT.canyon ? kk.width : i === SLOT.canyon + 1 ? 0.45 * kk.width : 0;
        const weight = octave ? clamp(s.length / (2 * cell) - 1, 0, 1) : feature ? clamp(feature * s.length / (2 * cell) - 1, 0, 1) : canyon ? clamp(canyon / (3 * cell) - 1, 0, 1) : 1;
        bake.uSlotB.value[i].set(qx - Math.floor(qx), qz - Math.floor(qz), weight, s.seed); bake.uSlotI.value[i].set(Math.floor(qx), Math.floor(qz));
      });
      const shown = (from, count) => { let n = 0; while (n < count && bake.uSlotB.value[from + n].z > 0) n++; return n; };
      const first = shown(SLOT.mountains, this.recipe.octaves), mm = this.recipe.mountains, mean = (i) => (i < mm.ridged ? 0.62 : 0.5);
      let tail = 0;
      for (let i = first + 1, a = mm.gain ** (first + 1); i < this.recipe.octaves; i++, a *= mm.gain) tail += a * Math.pow(clamp(1.6 * mean(i - 1), 1e-4, 1), mm.erosion) * mean(i);
      bake.uCount.value.set(first, shown(SLOT.rough, 4), shown(SLOT.craters, CRATER_CELLS.classes), first < this.recipe.octaves ? mean(first) : 0); bake.uTail.value = tail;
      bake.uMacroAt.value.set(ox / m.spacing + (m.n - 1) / 2, oz / m.spacing + (m.n - 1) / 2, 1 / m.spacing, m.scale);
      bake.uMap.value.set(cell, clamp(0.15 * cell / this.recipe.strata.step, 0, 0.5), m.n, clamp(1.5 * cell * this.recipe.canyons.steps / ((1 - this.recipe.canyons.floor) * this.recipe.canyons.width), RISER, 0.5));
      this._bake.material.uniformsNeedUpdate = true;
      this._map(k, key, first || k >= 3);
      this._middles[k] = key; this._shaded[k] = null; this.bakes.maps++;
    }
    u.uLandLv.value.set(finest, nl - 1, 0.4 * WIDTH, cell0);
    u.uLandAt.value.set(x, z, 0, 0);
    // the shadows: for the sun now, of every map baked or moved
    const sun = sky.sun, f = [sun.x, sun.y, sun.z], sunKey = f.map((v) => v.toFixed(5)).join("|"), sh = this._shade.material.uniforms;
    sh.uShadeSun.value.set(f[0], f[1], f[2], 1 / R); sh.uShadeSet.value.set(0.06, u.uLandRange.value.y, 0, 0);
    for (let k = nl - 1; k >= finest; k--) {
      if (this._shaded[k] === sunKey) continue;
      sh.uShadeAt.value.set(x, z, this.maps[k] / this.cells, k);
      this._shade.material.uniformsNeedUpdate = true;
      this._draw(this._shade, this.shadows, k);
      this._shaded[k] = sunKey; this.bakes.shadows++;
    }
    // the walk
    const up = [d[0], d[1], d[2]].map((v) => v / (R + hc));
    u.uLandGeo.value.set(R, hc, unit, pix / this.share); u.uLandUp.value.set(...up);
    u.uLandRange2.value.set(-Math.sin(horizonDip(R, Math.max(hc, 0)) * RAD) + 0.5 * pix, 0, 0, 0);
    u.uLandView.value.copy(camera.matrixWorld); u.uLandProj.value.set(1 / p[0], 1 / p[5], p[8], p[9]);
    u.uLandTSize.value.set(w, hgt, hgt / size.y, 0);
    this._walk.material.uniformsNeedUpdate = true;
    this._draw(this._walk, this.walk);
    u.uLandGeo.value.w = pix;
    // the picture's own numbers: the camera's place in the lattice and in every grain octave
    u.uLandMacro.value.set(x / m.spacing + (m.n - 1) / 2, z / m.spacing + (m.n - 1) / 2, 1 / m.spacing, m.n);
    for (let j = 0; j < 12; j++) { const lam = 2048 / 2 ** j, qx = x / lam, qz = z / lam; u.uDetA.value[j].set(qx - Math.floor(qx), qz - Math.floor(qz), Math.floor(qx), Math.floor(qz)); }
    { const len = this.recipe.volcanoes.spacing, qx = x / len, qz = z / len; u.uVolc.value.set(qx - Math.floor(qx), qz - Math.floor(qz), Math.floor(qx), Math.floor(qz)); }
    u.uLandLit.value.w = sky.state.gain;
    r.setRenderTarget(before); r.autoClear = auto; r.setClearColor(colour, alpha);
    Object.assign(this.horizon, {distance: horizonDistance(R, hc), dip: horizonDip(R, hc), height: hc, over, finest});
    this.t = t;
    return this;
  }

  /** Free the maps and the materials; the air draws under the horizon again. */
  dispose() {
    this.sky.under(false);
    this.material.dispose(); this._plane.dispose();
  }
}
/** Ground with relief under an air: `land(renderer, sky, {preset: "alpine"})`, `land(renderer, sky, {world: "mars", at: [-8, 40]})`. */
export const land = (renderer, sky, options) => new Land(renderer, sky, options);
