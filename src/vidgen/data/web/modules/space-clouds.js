// vidgen/space-clouds: cloud decks to fly under, through and over, cloud towers, lightning, and the decks
// of a giant of gas, under a vidgen/space-air sky (DESIGN.md §123.5). Part of schu-video-generator (MIT
// licence); imported by a page as "vidgen/space-clouds".
//
//   import {air, sunDirection} from "vidgen/space-air";
//   import {clouds} from "vidgen/space-clouds";
//   const sky = air(renderer, "earth", {sun: sunDirection(30, 20)});
//   const weather = clouds(renderer, sky, {sky: "fair", seed: 4});       // or {decks: [{type: "stratus", base: 1800, top: 3000}], towers: 3}
//   scene.add(sky.object, weather.object);
//   function frame(t) { sky.update(t, {camera}); weather.update(t, {camera}); renderer.render(scene, camera); }
//
// A deck is a shell of the world's sphere between two heights (the air's radius: the same sphere as
// vidgen/space-sea's water), so its horizon lies where the heights put it and it curves from high up. Each
// pixel's ray is cut with every shell and with the towers' cylinders, the nearest first, and a few steps are
// taken through each: the cloud there is a height field read from one small tile of noise at several sizes,
// turns and drifts (the weather's, the clouds', the puffs': each fades to its mean where a pixel or a step is
// coarser than it), every reading cut into cells that read the tile at their own offsets and turns, and the
// clouds' warped by endless noise besides (untiled(): the pattern never repeats), over an endless broad weather
// that has more say seen from high up (aloft()). Light: the sun after the air at the
// deck's own height (so a high deck is still pink when a low one is in the world's shadow), dimmed by the
// cloud the light crossed on its way (one more reading towards the sun: bright tops and sunward sides, grey
// bases), thrown onward at thin edges (the silver lining), the sky's light from above and what comes up
// from below, the decks above casting their shadows, and the air between the camera and the cloud
// (airLight). Not a simulation of scattering in the cloud: a few readings shaped to look right.
// The clouds are drawn at a share of the picture's size (QUALITIES) and laid over the dome and the sea.
import * as THREE from "three";
import {AIR_GLSL, DISPLAY_GLSL, RADII, sunlightAt, skyAmbient} from "vidgen/space-air";
import {resolveOptions as resolveWorld, bandRamp, linearColor} from "vidgen/space-bodies";

/** Bumped when the pictures change. */
export const VERSION = 2;
const PREFIX = "vidgen/space-clouds";
const RAD = Math.PI / 180;
/** By quality: the share of the picture's width and height the clouds are drawn at, the steps through a deck or a tower. */
export const QUALITIES = Object.freeze({fast: [1 / 3, 6, 3], standard: [1 / 2, 8, 4], fine: [1, 10, 5]});
/** The most decks and towers one sky may have. */
export const MOST = Object.freeze({decks: 4, towers: 6, flashes: 3});
/** The noise tile's size (texels a side). */
export const TILE = 256;

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
const part = (x) => x - Math.floor(x);
// a seeded generator of numbers from 0 to 1 (mulberry32)
function seeded(seed) {
  let a = (Math.floor(seed) >>> 0) + 0x9e3779b9;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ---------- the broad weather: gradient noise on an endless lattice (pure; the shader's own arithmetic) ----------
/** The hash of a lattice point (two integers) and a seed: an unsigned 32-bit integer (wrapping products and shifts only). */
export function broadHash(ix, iz, seed) {
  let h = Math.imul(ix | 0, 0x9E3779B1) ^ Math.imul(iz | 0, 0x85EBCA77) ^ Math.imul(seed | 0, 0xC2B2AE3D);
  h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; h = Math.imul(h, 0x297A2D39); h ^= h >>> 15;
  return h >>> 0;
}
// gradient noise whose gradients' angles are four bits of the lattice points' hashes from bit `shift` on
function gradientNoise(qx, qz, seed, shift) {
  const cx = Math.floor(qx), cz = Math.floor(qz), fx = qx - cx, fz = qz - cz, g = (i, j) => { const a = (((broadHash(i, j, seed) >>> shift) & 15) + 0.5) * Math.PI / 8; return [Math.cos(a), Math.sin(a)]; };
  const a = g(cx, cz), b = g(cx + 1, cz), c = g(cx, cz + 1), d = g(cx + 1, cz + 1);
  const va = a[0] * fx + a[1] * fz, vb = b[0] * (fx - 1) + b[1] * fz, vc = c[0] * fx + c[1] * (fz - 1), vd = d[0] * (fx - 1) + d[1] * (fz - 1);
  const ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10), uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10);
  return Math.SQRT2 * (va + ux * (vb - va) + uz * (vc - va) + ux * uz * (va - vb - vc + vd));
}
/** Gradient noise at (qx, qz), one lattice cell a unit, about -1 to 1; it never repeats (the lattice has no period). */
export function broadNoise(qx, qz, seed) { return gradientNoise(qx, qz, seed, 0); }
/** Two gradient noises at (qx, qz) from one lattice's hashes (the gradients from the hash's lowest four bits and the
 * next four): a shift [x, z], each about -1 to 1, that never repeats (the shader's own arithmetic). */
export function warpNoise(qx, qz, seed) { return [gradientNoise(qx, qz, seed, 0), gradientNoise(qx, qz, seed, 4)]; }
/** The sizes of the broad weather's octaves, in deck sizes (the last about the tile's own repeat, so its rhythm
 * never shows), their weights, and the reach round the place where it is drawn to nothing (in the second's sizes). */
export const FRONTS = Object.freeze({sizes: Object.freeze([40, 15, 5]), weights: Object.freeze([0.7, 0.45, 0.35]), middle: 0.5});
/** How a deck's weather, clouds and fine puffs are kept from repeating although they are read from one tile (Step 395), in
 * repeats of the tile: the clouds' place is first shifted by endless noise (`warp`: how far, at most about; `warpSize`:
 * the noise's cell; the others' is not: the cells below are enough where the pattern weighs less or is fine), then the plane is cut into cells one repeat wide on an endless lattice, each reading the tile at
 * its own offset and turn, the neighbours blended within `blend` of a cell's edge (keeping the pattern's contrast). */
export const UNTILE = Object.freeze({warp: 0.5, warpSize: 3, blend: 0.15});
/** How much more say the broad weather has seen from high up: none while the camera is less than `from` clouds' widths
 * over a deck's top, `boost` times more from `to` on (bands and clear patches from orbit); less for a deck nearly closed
 * or nearly empty, none for one closed or empty (an overcast stays an overcast). */
export const ALOFT = Object.freeze({from: 3, to: 15, boost: 2});
/** How much the broad weather of `deck` (deckOf()'s numbers) is multiplied by for a camera `height` metres up (ALOFT). Pure. */
export function aloft(deck, height) { return 1 + ALOFT.boost * Math.min(1, 5 * deck.cover * (1 - deck.cover)) * smooth(ALOFT.from, ALOFT.to, (height - deck.top) / deck.size); }

// ---------- the noise tile: one small picture that repeats, read at many sizes (pure) ----------
function cellHash(x, y, period, salt) {
  x = ((x % period) + period) % period; y = ((y % period) + period) % period;
  let h = Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(salt, 83492791);
  h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
function valueNoise(u, v, period, salt) {
  const x = u * period, y = v * period, i = Math.floor(x), j = Math.floor(y), a = x - i, b = y - j, fa = a * a * (3 - 2 * a), fb = b * b * (3 - 2 * b);
  return (cellHash(i, j, period, salt) * (1 - fa) + cellHash(i + 1, j, period, salt) * fa) * (1 - fb) + (cellHash(i, j + 1, period, salt) * (1 - fa) + cellHash(i + 1, j + 1, period, salt) * fa) * fb;
}
// one less the squared distance to the nearest of a grid's scattered points: round caps (their square root is a ball's top)
function puffs(u, v, period, salt) {
  const x = u * period, y = v * period, i = Math.floor(x), j = Math.floor(y);
  let best = 9;
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    const px = i + dx + cellHash(i + dx, j + dy, period, salt), py = j + dy + cellHash(i + dx, j + dy, period, salt + 7), d = (px - x) ** 2 + (py - y) ** 2;
    if (d < best) best = d;
  }
  return Math.max(0, 1 - best);
}
let tileKept = null;
/** The noise tile: {size, data (Uint8Array, four numbers a texel), at(u, v) → [r, g, b, a] from 0 to 1, mean (each channel's)}. Red: soft
 * noise in five sizes (a cloud field's shape); green: round puffs in three sizes; blue: finer puffs (what frays
 * an edge); alpha: another soft noise (streaks, the second weather). It repeats in both directions. The same
 * numbers on every machine: made in JavaScript, not by the graphics card. */
export function noiseTile() {
  if (tileKept) return tileKept;
  const n = TILE, raw = [0, 1, 2, 3].map(() => new Float32Array(n * n));
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const u = (i + 0.5) / n, v = (j + 0.5) / n, k = j * n + i;
    let r = 0, a = 0;
    for (let o = 0; o < 5; o++) { r += valueNoise(u, v, 4 << o, 11 + o) * 0.5 ** o; a += valueNoise(u, v, 3 << o, 31 + o) * 0.5 ** o; }
    raw[0][k] = r; raw[3][k] = a;
    raw[1][k] = 0.7 * puffs(u, v, 5, 51) + 0.2 * puffs(u, v, 11, 52) + 0.1 * puffs(u, v, 23, 53);
    raw[2][k] = 0.6 * puffs(u, v, 17, 61) + 0.4 * puffs(u, v, 37, 62);
  }
  const data = new Uint8Array(n * n * 4);
  raw.forEach((plane, c) => {
    let lo = Infinity, hi = -Infinity;
    for (const x of plane) { if (x < lo) lo = x; if (x > hi) hi = x; }
    for (let k = 0; k < n * n; k++) data[k * 4 + c] = Math.round(255 * (plane[k] - lo) / (hi - lo));
  });
  const at = (u, v) => {
    const x = part(u) * n - 0.5, y = part(v) * n - 0.5, i = Math.floor(x), j = Math.floor(y), a = x - i, b = y - j, w = (q) => ((q % n) + n) % n, out = [0, 0, 0, 0];
    for (let c = 0; c < 4; c++) out[c] = ((data[(w(j) * n + w(i)) * 4 + c] * (1 - a) + data[(w(j) * n + w(i + 1)) * 4 + c] * a) * (1 - b) + (data[(w(j + 1) * n + w(i)) * 4 + c] * (1 - a) + data[(w(j + 1) * n + w(i + 1)) * 4 + c] * a) * b) / 255;
    return out;
  };
  const mean = [0, 1, 2, 3].map((c) => { let sum = 0; for (let k = c; k < data.length; k += 4) sum += data[k]; return sum / (n * n * 255); });
  tileKept = Object.freeze({size: n, data, at, mean: Object.freeze(mean)});
  return tileKept;
}

/** The tile read at (u, v) (in repeats) so that it never repeats (UNTILE): the place shifted by warpNoise() (when `warp`), then each
 * cell of the endless lattice (one repeat wide) reads the tile at its own offset and turn, from `salt`'s hashes;
 * near a cell's edge the neighbours are blended, their departures from the tile's mean summed over the root of the
 * sum of the weights' squares (so the blend is as varied as one reading). Returns [r, g, b, a] (about 0 to 1). The
 * shader's own arithmetic. Pure. */
export function untiled(u, v, salt, warp = true) {
  const tile = noiseTile(), w = warp ? warpNoise(u / UNTILE.warpSize, v / UNTILE.warpSize, salt) : [0, 0], b = UNTILE.blend;
  const U = u + UNTILE.warp * w[0], V = v + UNTILE.warp * w[1], su = U - 0.5, sv = V - 0.5, iu = Math.floor(su), iv = Math.floor(sv);
  const ku = smooth(0.5 - b, 0.5 + b, su - iu), kv = smooth(0.5 - b, 0.5 + b, sv - iv), sum = [0, 0, 0, 0];
  let squares = 0;
  for (let j = 0; j < 4; j++) {
    const du = j & 1, dv = j >> 1, weight = (du ? ku : 1 - ku) * (dv ? kv : 1 - kv);
    if (weight <= 0) continue;
    const cu = iu + du, cv = iv + dv, h = broadHash(cu, cv, salt + 1), a = ((h & 15) + 0.5) * Math.PI / 8, c = Math.cos(a), s = Math.sin(a);
    const lu = U - cu - 0.5, lv = V - cv - 0.5, got = tile.at(c * lu - s * lv + ((h >>> 8) & 1023) / 1024, s * lu + c * lv + ((h >>> 18) & 1023) / 1024);
    for (let k = 0; k < 4; k++) sum[k] += weight * (got[k] - tile.mean[k]);
    squares += weight * weight;
  }
  return sum.map((x, k) => tile.mean[k] + x / Math.sqrt(squares));
}

// ---------- the geometry of a shell: pure ----------
/** The first stretch of a ray that lies in the shell between `base` and `top` metres over a sphere `radius`
 * metres in radius, for an eye `height` metres over it looking along cosine `mu` to the vertical: [from, to]
 * in metres along the ray, or null when the ray misses the shell. (The shader's own arithmetic.) */
export function shellSpan(radius, height, mu, base, top) {
  const r0 = radius + height, m = r0 * mu, ca = (height - base) * (2 * radius + height + base), cb = (height - top) * (2 * radius + height + top);
  const da = m * m - ca, db = m * m - cb, far = (c, d) => (m > 0 ? -c / (m + Math.sqrt(Math.max(d, 0))) : -m + Math.sqrt(Math.max(d, 0)));
  if (height > top) {
    if (mu >= 0 || db <= 0) return null;
    return [cb / (-m + Math.sqrt(db)), da > 0 ? ca / (-m + Math.sqrt(da)) : far(cb, db)];
  }
  if (height >= base) return [0, mu < 0 && da > 0 ? ca / (-m + Math.sqrt(da)) : far(cb, db)];
  return [far(ca, da), far(cb, db)];
}
/** Where a deck's edge lies for an eye over it: {distance (metres along the line of sight to where the look
 * touches the sphere `deck` metres up), dip (degrees under the eye's level)}; for an eye under it, the distance
 * at which a level look meets it and dip 0. */
export function deckHorizon(radius, height, deck) {
  const r0 = radius + height, rd = radius + deck;
  if (height >= deck) return {distance: Math.sqrt(Math.max(r0 * r0 - rd * rd, 0)), dip: Math.acos(Math.min(1, rd / r0)) / RAD};
  return {distance: Math.sqrt(rd * rd - r0 * r0), dip: 0};
}

// ---------- decks ----------
/** The kinds of deck, each with its character as numbers. `base`, `top`: metres over the sphere; `cover`: the
 * share of the sky the deck covers seen from straight above or below (roughly: frayed edges take a little);
 * `size`: a cloud's width, metres; `stretch`: how much longer than wide along the wind; `density`: the share of
 * light a metre of cloud takes (real cloud takes 0.02 to 0.1: these are thinner, so that edges are soft at the
 * steps the picture can afford: a look); `weather`: how much of the pattern is the weather's (clear and
 * overcast regions tens of kilometres across) and not the single clouds'; `rise`: how high the thickest cloud's
 * top stands over `floor`, as the square of its share of the deck's depth (tops are round: a square root of the pattern); `floor`: the top's height where the cloud is thinnest (0: tops grow from the base,
 * 1: the deck is filled); `soft`: how soft the pattern's edge is; `fray`: how much the fine puffs eat the
 * edges; `ragged`: how uneven the base is; `puff`: the round puffs' share of the single clouds' shape;
 * `color`: what the cloud throws back (linear; water cloud is nearly white); `beyond`: {color, at, width}: another colour for
 * the deck's cloud from `at` metres north of the origin (towards -z; negative: south) on, the change `width` metres wide; `stripes`: {colors, span}:
 * colours across the deck from `span` metres south of the origin to `span` north of it, evenly spaced [red, green, blue, lift] (lift: how much more cloud
 * the stripe has, in the pattern's units; negative: less and lower), at most 64: a giant's bands.
 * `cumulus`: a low broken field, flat bases, heaped tops. `stratus`: a closed deck with a rolling top: a cloud
 * sea from above, an overcast from below. `cirrus`: thin high streaks of ice drawn out along the wind. */
export const DECKS = Object.freeze({
  cumulus: {base: 1000, top: 2100, cover: 0.4, size: 2400, stretch: 1, density: 0.006, weather: 0.35, fronts: 0.8, rise: 1.1, floor: 0, soft: 0.035, fray: 0.13, ragged: 0.04, puff: 0.45, color: [0.93, 0.93, 0.93]},
  stratus: {base: 1800, top: 3000, cover: 1, size: 3200, stretch: 1.4, density: 0.008, weather: 0.35, fronts: 0.8, rise: 0.36, floor: 0.4, soft: 0.05, fray: 0.07, ragged: 0.25, puff: 0.6, color: [0.93, 0.93, 0.93]},
  cirrus: {base: 9500, top: 10100, cover: 0.5, size: 9000, stretch: 5, density: 0.0006, weather: 0.4, fronts: 0.8, rise: 0, floor: 1.2, soft: 0.3, fray: 0.12, ragged: 0, puff: 0.1, color: [0.95, 0.95, 0.97]},
});
const DECK_OPTIONS = ["type", "base", "top", "cover", "size", "stretch", "density", "weather", "fronts", "rise", "floor", "soft", "fray", "ragged", "puff", "color", "beyond", "stripes", "name"];
/** A deck in full: `what` a name of DECKS or {type, base, top, cover, ...}; `extra` over it. Pure. */
export function deckOf(what = "cumulus", extra = {}) {
  let base = what;
  if (typeof what === "string") base = {type: what};
  else if (what === null || typeof what !== "object" || Array.isArray(what)) throw fail(`a deck must be a name or an options object, got ${JSON.stringify(what)}`);
  known("a deck's options", extra, DECK_OPTIONS);
  const given = {...base, ...extra};
  known("a deck", given, DECK_OPTIONS);
  const type = String(given.type ?? "cumulus").trim().toLowerCase();
  if (!(type in DECKS)) throw fail(`no deck "${given.type}"${hint(type, Object.keys(DECKS))}; there are: ${Object.keys(DECKS).join(", ")}`);
  const o = {...DECKS[type], ...given, type};
  // a deck moved by its base alone keeps its depth
  if (given.base !== undefined && given.top === undefined) o.top = o.base + DECKS[type].top - DECKS[type].base;
  number("base (metres)", o.base, 0, 1e7); number("top (metres)", o.top, o.base + 1, 1e7); number("cover", o.cover, 0, 1); number("size (metres)", o.size, 10, 1e7);
  number("stretch", o.stretch, 0.2, 20); number("density (a metre)", o.density, 1e-8, 1); number("weather", o.weather, 0, 1); number("fronts", o.fronts, 0, 3); number("rise", o.rise, 0, 50); number("floor", o.floor, 0, 2);
  number("soft", o.soft, 0.005, 1); number("fray", o.fray, 0, 1); number("ragged", o.ragged, 0, 0.9); number("puff", o.puff, 0, 1);
  let beyond = null;
  if (o.beyond !== undefined && o.beyond !== null) {
    known("beyond", o.beyond, ["color", "at", "width"]);
    beyond = Object.freeze({color: Object.freeze(linearColor("beyond.color", o.beyond.color)), at: number("beyond.at (metres)", o.beyond.at ?? 0, -1e9, 1e9), width: number("beyond.width (metres)", o.beyond.width ?? 1e4, 1, 1e9)});
  }
  let stripes = null;
  if (o.stripes !== undefined && o.stripes !== null) {
    known("stripes", o.stripes, ["colors", "span"]);
    if (!Array.isArray(o.stripes.colors) || o.stripes.colors.length < 2 || o.stripes.colors.length > 64 || o.stripes.colors.some((c) => !Array.isArray(c) || c.length !== 4 || c.some((x) => typeof x !== "number" || !Number.isFinite(x))))
      throw fail("stripes.colors must be 2 to 64 entries of [red, green, blue, lift]");
    stripes = Object.freeze({colors: Object.freeze(o.stripes.colors.map((c) => Object.freeze([...c]))), span: number("stripes.span (metres)", o.stripes.span, 1, 1e9)});
  }
  return Object.freeze({...o, name: o.name ?? type, color: Object.freeze(linearColor("color", o.color)), beyond, stripes});
}

/** Ready-made skies: `decks` (the lowest first), `towers` and `lightning` as `clouds()` takes them.
 * `fair`: a field of cumulus under streaks of cirrus. `overcast`: a closed deck: grey from below, a cloud sea
 * from above. `layers`: a cloud sea, a thin broken deck 4 km over it and cirrus: fly between. `towers`: cloud
 * towers 11 km high rising through a low deck. `storm`: a dark deck, towers and lightning. */
export const SKIES = Object.freeze({
  fair: {decks: [{type: "cumulus"}, {type: "cirrus", cover: 0.45}]},
  overcast: {decks: [{type: "stratus"}]},
  layers: {decks: [{type: "stratus", base: 1600, top: 2800}, {type: "stratus", base: 6800, top: 7300, cover: 0.55, size: 2200, density: 0.003, floor: 0.6}, {type: "cirrus", base: 11000, cover: 0.4}]},
  towers: {decks: [{type: "stratus", base: 1500, top: 2600, cover: 0.85}, {type: "cirrus", base: 12500, cover: 0.35}], towers: {count: 5}},
  storm: {decks: [{type: "stratus", base: 900, top: 2600, density: 0.012}, {type: "stratus", base: 5200, top: 6000, cover: 0.7, density: 0.004}], towers: {count: 6, radius: 5200}, lightning: {rate: 14}},
});

const TOWER_OPTIONS = ["count", "seed", "spread", "radius", "base", "top", "anvil", "density", "color", "at"];
const TOWERS = Object.freeze({count: 4, seed: null, spread: 60000, radius: 4200, base: 1100, top: 11500, anvil: 2.2, density: 0.004, color: Object.freeze([0.93, 0.93, 0.93]), at: null});
/** Cloud towers from a seed: `count` of them (MOST.towers at most) scattered within `spread` metres of the
 * origin (none nearer than 0.3 of it: the camera starts clear), or at the places `at` ([[x, z], ...] metres
 * along the scene's +x and +z); each `radius` metres wide at its foot (varied by the seed), from `base` to
 * `top` metres, spreading at the top into an anvil `anvil` times as wide. Returns a list of {x, z, radius,
 * base, top, anvil, turn (where its puffs are read)}. Pure. */
export function towerList(options = {}, seed = 1) {
  if (typeof options === "number") options = {count: options};
  if (options === true) options = {};
  known("towers", options, TOWER_OPTIONS);
  const o = {...TOWERS, ...options}, rand = seeded((o.seed ?? seed) * 7919 + 13), list = [];
  const count = o.at ? o.at.length : number("towers.count", o.count, 0, MOST.towers);
  if (count > MOST.towers) throw fail(`towers: at most ${MOST.towers}, got ${count}`);
  number("towers.spread (metres)", o.spread, 100, 1e8); number("towers.radius (metres)", o.radius, 50, 1e6); number("towers.base (metres)", o.base, 0, 1e7); number("towers.top (metres)", o.top, o.base + 100, 1e7);
  number("towers.anvil", o.anvil, 1, 5); number("towers.density (a metre)", o.density, 1e-8, 1);
  for (let i = 0; i < count; i++) {
    const a = (i + 0.2 + 0.6 * rand()) / count * 2 * Math.PI, d = o.spread * (0.3 + 0.7 * Math.sqrt(rand())), size = 0.75 + 0.5 * rand(), high = 0.82 + 0.18 * rand();
    const place = o.at ? o.at[i] : [Math.sin(a) * d, -Math.cos(a) * d];
    if (!Array.isArray(place) || place.length !== 2) throw fail(`towers.at must be a list of [x, z] in metres, got ${JSON.stringify(o.at)}`);
    list.push(Object.freeze({x: place[0], z: place[1], radius: o.radius * size, base: o.base, top: o.base + (o.top - o.base) * high, anvil: o.anvil * (0.85 + 0.3 * rand()), turn: rand() * 7}));
  }
  return Object.freeze({list: Object.freeze(list), density: o.density, color: Object.freeze(linearColor("towers.color", o.color))});
}

/** A deck's pattern from a seed: the deck (deckOf()'s numbers; `d` a name or options) with `reads` (its four readings
 * of the tile: the weather twice, at two sizes and turns that never fall in step, the clouds, the fine puffs; each {u, v
 * (the rows of the matrix from metres to the tile's coordinates), at (its offset), drift (metres a second), texels (a
 * metre), salt (untiled()'s: no reading repeats; the clouds' is warped)}), `level` (the pattern's value where cloud begins: a share `cover` of 4096 places stands over it), `span` (how far
 * over the level the thickest stand), `depth` (metres), `valueAt(x, z, t, height)` (the pattern at a place, metres along +x and +z,
 * and a time, for a camera `height` metres up (aloft()): what the picture reads at full sharpness, the fine puffs left out) and `coverAt(x, z, t, height)` (0 where the sky is
 * open, towards 1 in a cloud's middle). `wind` (m/s) towards `direction` (degrees) moves the readings at their own speeds,
 * so the pattern drifts and changes; `index`: the deck's place in its sky. Pure. */
export function deckField(d, {seed = 1, wind = 12, direction = 70, index = 0} = {}) {
  const deck = d !== null && typeof d === "object" && Object.isFrozen(d) && "beyond" in d ? d : deckOf(d), rand = seeded(seed * 2654435 + 17 + index * 7001);
  const to = [Math.sin(direction * RAD), -Math.cos(direction * RAD)];
  const reading = (metres, turn, stretch, speed) => {
    const a = turn + direction * RAD, c = Math.cos(a), s = Math.sin(a), along = 1 / (metres * stretch), across = 1 / metres;
    // the first row along the wind (stretched), the second across it
    return Object.freeze({u: [s * along, -c * along], v: [c * across, s * across], at: [rand(), rand()], drift: [to[0] * wind * speed, to[1] * wind * speed], texels: TILE / metres});
  };
  // no reading repeats (untiled(), each with its own salt; the clouds' warped too)
  const salt = (k) => Math.imul((seed * 7919 + index * 104729 + 1013 * (k + 1)) | 0, 0x9E3779B1) >>> 8;
  const reads = [reading(deck.size * 31, 0.4 + 0.3 * rand(), 1, 0.9), reading(deck.size * 12.7, 1.3 + 0.4 * rand(), 1, 0.75), reading(deck.size * 4, 0.06 * (rand() - 0.5), deck.stretch, 1), reading(deck.size * 0.9, 0.5, Math.sqrt(deck.stretch), 1.2)]
    .map((r, k) => Object.freeze({...r, salt: salt(k)}));
  const read = (r, x, z, t) => { const px = x - r.drift[0] * t, pz = z - r.drift[1] * t, u = r.u[0] * px + r.u[1] * pz + r.at[0], v = r.v[0] * px + r.v[1] * pz + r.at[1]; return untiled(u, v, r.salt, r === reads[2]); };
  // the broad weather: two octaves of endless noise tens of km across (drawn last, so the tile's readings keep the seed's numbers)
  const fronts = FRONTS.sizes.map((k, j) => ({...reading(deck.size * k, 2 * Math.PI * rand(), 1.6, 0.6), seed: (((seed * 7919 + index * 104729) & 0xffffff) + j * 7919) & 0xffffff}));
  const sum = (x, z, t) => fronts.reduce((acc, r, j) => { const px = x - r.drift[0] * t, pz = z - r.drift[1] * t;
    return acc + FRONTS.weights[j] * broadNoise(r.u[0] * px + r.u[1] * pz + r.at[0] * 1000, r.v[0] * px + r.v[1] * pz + r.at[1] * 1000, r.seed); }, 0);
  // round the place (the origin) the broad weather is drawn to nothing, so the cover asked for is the cover seen there
  const middle = sum(0, 0, 0), reach = 1 / (deck.size * FRONTS.sizes[1] * FRONTS.middle) ** 2;
  const broad = (x, z, t) => sum(x, z, t) - middle * Math.exp(-(x * x + z * z) * reach);
  const local = (x, z, t) => {
    const weather = 0.5 * (read(reads[0], x, z, t)[0] + read(reads[1], x, z, t)[3]), c = read(reads[2], x, z, t);
    return (c[0] * (1 - deck.puff) + c[1] * deck.puff) * (1 - deck.weather) + weather * deck.weather;
  };
  const valueAt = (x, z, t = 0, height = 0) => local(x, z, t) + (deck.fronts > 0 ? deck.weather * deck.fronts * aloft(deck, height) * broad(x, z, t) : 0);
  // the level and the span from the deck's own pattern: where the broad weather is nothing, the cover is the one asked for
  const values = Array.from({length: 4096}, (_, k) => local((part(k * 0.6180339887) - 0.5) * deck.size * 900, (part(k * 0.7548776662) - 0.5) * deck.size * 900, 0)).sort((p, q) => p - q);
  const level = deck.cover >= 1 ? values[0] - 0.06 : deck.cover <= 0 ? values[values.length - 1] + 0.06 : values[Math.floor((1 - deck.cover) * values.length)];
  return Object.freeze({...deck, reads: Object.freeze(reads), broad: Object.freeze(fronts.map((r) => Object.freeze(r))), middle, reach, broadAt: broad, depth: deck.top - deck.base, level, span: Math.max(values[Math.floor(0.985 * values.length)] - level, 0.02),
    valueAt, coverAt: (x, z, t = 0, height = 0) => smooth(0, deck.soft, valueAt(x, z, t, height) - level)});
}

// ---------- lightning: pure ----------
const LIGHTNING_OPTIONS = ["seed", "rate", "times", "power", "color", "radius", "from", "to"];
const LIGHTNING = Object.freeze({seed: null, rate: 0, times: null, power: 1, color: Object.freeze([0.75, 0.82, 1]), radius: 2500, from: 0, to: 600});
/** How much of a lifted exposure (the film look at dusk: stops as a power of two) a flash is lifted with: all of it would turn every cloud white (a look). */
export const FLASH_LIFT = 0.8;
/** How long a flash is seen, seconds. */
export const FLASH_SECONDS = 0.55;
/** A flash's brightness `age` seconds after it began (0 before and after FLASH_SECONDS): a first stroke and
 * `strokes` (1 to 4, from the flash's own number) fainter ones after it, each rising in a hundredth of a second. */
export function flashLevel(age, strokes = 3) {
  if (!(age >= 0) || age >= FLASH_SECONDS) return 0;
  let sum = 0;
  for (let k = 0; k < strokes; k++) { const a = age - k * 0.11; if (a >= 0) sum += (k === 0 ? 1 : 0.55 / k) * Math.min(1, a / 0.01) * Math.exp(-a / 0.045); }
  return sum * smooth(FLASH_SECONDS, FLASH_SECONDS - 0.1, age);
}
/** The times of a seeded storm's flashes: `rate` a minute on average between `from` and `to` seconds, never
 * two within 0.25 s, as a sorted list. Pure: the same seed, the same storm. */
export function strikeTimes(seed, {rate = 10, from = 0, to = 60} = {}) {
  number("rate (flashes a minute)", rate, 0, 600); number("from (seconds)", from, -1e6, 1e6); number("to (seconds)", to, from, 1e6);
  const rand = seeded(seed * 104729 + 71), out = [];
  if (rate === 0) return out;
  for (let t = from + 60 / rate * rand(); t < to; t += Math.max(0.25, -60 / rate * Math.log(1 - 0.999 * rand()))) out.push(t);
  return out;
}
// times as a list of numbers from what a page may hand over: numbers, {time}, or music-time's {t: Float32Array}
function timesOf(times) {
  if (times === null || times === undefined) return [];
  const list = times.t && typeof times.t.length === "number" ? Array.from(times.t) : Array.from(times, (e) => (typeof e === "number" ? e : e && e.time));
  if (list.some((x) => typeof x !== "number" || !Number.isFinite(x))) throw fail("lightning.times must be seconds: numbers, events with `time` (ctx.music's), or a track of vidgen/music-time's trackArrays ({t})");
  return list;
}

/** A storm's flashes: `lightning` ({rate, times, power, color, radius, seed, from, to}, or true for ten a minute): the
 * seed's own flashes (strikeTimes) and those at the stated `times` (seconds: numbers, events with `time` such as
 * ctx.music's, or a track of vidgen/music-time's trackArrays, whose gains scale them), each at a place of its own: in
 * one of `towers` (towerList()'s list) when there are any, else in `deck` (a deckField) within eight clouds' widths of the
 * camera. Returns [{time, place: [x, height, z] (metres), strokes, power, color, radius, follows (the place is counted
 * from the camera, not from the origin)}] sorted by time. Pure. */
export function stormOf(lightning, {seed = 1, towers = [], deck = null} = {}) {
  if (lightning !== true) known("lightning", lightning, LIGHTNING_OPTIONS);
  const lg = {...LIGHTNING, ...(lightning === true ? {rate: 10} : lightning)}, own = lg.seed ?? seed;
  number("lightning.power", lg.power, 0, 100); number("lightning.radius (metres)", lg.radius, 10, 1e7);
  const colour = linearColor("lightning.color", lg.color), gains = lg.times && lg.times.g ? Array.from(lg.times.g) : null;
  const all = [...strikeTimes(own, {rate: lg.rate, from: lg.from, to: lg.to}).map((time) => ({time, gain: 1})), ...timesOf(lg.times).map((time, k) => ({time, gain: gains ? gains[k] ?? 1 : 1}))].sort((a, b) => a.time - b.time);
  return all.map(({time, gain}, k) => {
    const r = seeded(own * 31 + k * 977 + 5), tower = towers.length ? towers[Math.floor(r() * towers.length)] : null, a = r() * 2 * Math.PI, d = Math.sqrt(r());
    if (!tower && !deck) throw fail("stormOf: lightning needs towers or a deck to flash in");
    const place = tower ? [tower.x + Math.cos(a) * d * tower.radius * 0.5, tower.base + (tower.top - tower.base) * (0.25 + 0.5 * r()), tower.z + Math.sin(a) * d * tower.radius * 0.5]
      : [Math.cos(a) * d * deck.size * 8, deck.base + (deck.top - deck.base) * (0.3 + 0.4 * r()), Math.sin(a) * d * deck.size * 8];
    return Object.freeze({time, place, strokes: 1 + Math.floor(r() * 4), power: lg.power * (0.6 + 0.8 * r()) * gain, color: colour, radius: lg.radius * (tower ? Math.max(1, tower.radius / 4200) : 1), follows: !tower});
  });
}

// ---------- a giant of gas ----------
/** What a giant's flight takes its numbers from, in scale heights of its air over the sphere the planet is
 * drawn as from outside: the deep deck, the main deck, the high haze (base and top each), the towers' foot and
 * top, a cloud's width in the main deck. A look: no giant's real decks are this far apart in this air. */
export const GIANT = Object.freeze({deep: [0.16, 0.34], main: [0.56, 0.8], haze: [1.5, 1.56], towers: [0.3, 1.45], size: 0.42});
/** The sky of a giant of gas as `clouds()` takes it: `world` a giant of vidgen/space-bodies ("jupiter",
 * "saturn", "neptune", "tempest", ... or its options); `latitude` (degrees): the place on it, which picks the
 * band the decks take their colours from (the same ramp the planet is painted with from outside: the same
 * seed, the same bands); `scale`: metres a scale height of the air (the air's own `H`); `radius`: the world's (metres; the real or stated one of
 * vidgen/space-air's RADII by default); `squeeze`: how many times narrower than on the world the bands are drawn (40: true bands
 * are wider than the view from inside reaches, so one would see a single colour: a stated look; 1: true); `towers`: how many.
 * Returns {decks, towers, floor (the dark below: its colour), band (the colour at that latitude), next (the neighbouring band's),
 * wind, direction (the wind blows east, along the bands)}: the main deck has the ramp's bands as `stripes` to 40 scale heights
 * north and south, drawn out along the wind. Pure. */
export function giantSky(world = "jupiter", {latitude = 22, scale = 27000, radius = null, towers = 0, squeeze = 40} = {}) {
  const o = resolveWorld(world);
  if (o.type !== "gas" && o.type !== "ice-giant") throw fail(`giantSky: "${o.name ?? o.type}" is not a giant of gas (types gas and ice-giant are)`);
  number("latitude (degrees)", latitude, -90, 90); number("scale (metres)", scale, 100, 1e7); number("towers", towers, 0, MOST.towers); number("squeeze", squeeze, 1, 100);
  const R = number("radius (metres)", radius ?? RADII[o.name] ?? 6e7, 1e5, 1e9);
  const pal = o.palette, lin = (c) => linearColor("colour", c), ramp = bandRamp(o.seed, {bands: o.bands, contrast: o.contrast, zones: pal.zones.map(lin), belts: pal.belts.map(lin)});
  const at = (lat) => ramp[clamp(Math.round((Math.sin(clamp(lat, -90, 90) * RAD) + 1) / 2 * ramp.length - 0.5), 0, ramp.length - 1)].slice(0, 3);
  const band = at(latitude), light = (c, k) => c.map((x) => Math.min(1, x * k)), mean = pal.belts.map(lin).reduce((sum, c) => sum.map((x, i) => x + c[i] / pal.belts.length), [0, 0, 0]);
  // the bands north and south of the place, as the ramp has them, `squeeze` times narrower than on the world: a bright band has more and higher cloud
  const span = 12 * scale, luma = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  const colors = Array.from({length: 64}, (_, k) => light(at(latitude + ((k + 0.5) / 32 - 1) * span / R / RAD * squeeze), 1.05)), level = colors.reduce((sum, c) => sum + luma(c) / 64, 0);
  const stripes = {span, colors: colors.map((c) => [...c, 0.1 * clamp((luma(c) - level) / Math.max(level, 1e-3), -1, 1)])};
  let next = band;
  for (let k = 1; k < 32 && next === band; k++) for (const c of [colors[32 + k], colors[31 - k]]) if (next === band && Math.max(...c.map((x, i) => Math.abs(x - colors[32][i]))) > 0.07) next = c;
  const zone = lin(pal.zones[0]), oval = lin(pal.oval), h = (x) => x * scale, size = GIANT.size * scale;
  return {band, next, floor: mean.map((x) => x * 0.03), wind: 90, direction: 90,
    decks: [
      {type: "stratus", name: "deep", base: h(GIANT.deep[0]), top: h(GIANT.deep[1]), cover: 0.8, size: size * 1.6, stretch: 5, fronts: 0, density: 10 / (h(GIANT.deep[1]) - h(GIANT.deep[0])), color: light(mean, 0.5)},
      {type: "stratus", name: "main", base: h(GIANT.main[0]), top: h(GIANT.main[1]), cover: 0.78, size, stretch: 4, fronts: 0, density: 9 / (h(GIANT.main[1]) - h(GIANT.main[0])), weather: 0.4, fray: 0.12, color: light(band, 1.05), stripes},
      {type: "cirrus", name: "haze", base: h(GIANT.haze[0]), top: h(GIANT.haze[1]), cover: 0.5, size: size * 3, stretch: 6, fronts: 0, density: 0.3 / (h(GIANT.haze[1]) - h(GIANT.haze[0])), color: light(zone.map((x, i) => 0.5 * (x + oval[i])), 1)},
    ],
    towers: {count: towers, spread: 7 * scale, radius: 0.12 * scale, base: h(GIANT.towers[0]), top: h(GIANT.towers[1]), anvil: 2.4, density: 4 / (0.12 * scale), color: light(oval, 0.95)}};
}

/** The air a giant's flight happens in, as vidgen/space-air's `air(renderer, giantAir("jupiter"))` takes it: the
 * world's own air of vidgen/space-bodies (what its limb shows from outside: the thin gas over the cloud tops)
 * made `density` times as deep, so that at height 0 there is about as much gas overhead as on the Earth at sea
 * level (a giant's air at the pressure of one bar scatters about as much: hydrogen scatters less than air a
 * molecule, and there are more molecules over a square metre), with the world's radius. A stated choice: the limb
 * seen from orbit is the thinner air. */
export function giantAir(world = "jupiter", {density = 8} = {}) {
  const o = resolveWorld(world);
  if (o.type !== "gas" && o.type !== "ice-giant") throw fail(`giantAir: "${o.name ?? o.type}" is not a giant of gas (types gas and ice-giant are)`);
  number("density", density, 0.1, 50);
  const k = o.type === "ice-giant" ? density / 3 : density;
  return {world: o.name ?? undefined, air: {rayleigh: o.air.rayleigh.map((x) => x * k), haze: o.air.haze.map((x) => x * k * 0.5), absorb: o.air.absorb.map((x) => x * k), height: o.air.height, forward: o.air.forward}, ground: [0.02, 0.02, 0.02]};
}

// ---------- the picture ----------
const CLOUD_VERT = /* glsl */`
uniform mat4 uCloudView; uniform vec4 uCloudProj;
varying vec3 vDir;
void main() {
  vDir = mat3(uCloudView) * vec3((position.x + uCloudProj.z) * uCloudProj.x, (position.y + uCloudProj.w) * uCloudProj.y, -1.0);
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;
/** The deck's pattern in GLSL, as the clouds' own shader and a shadow on something else (vidgen/space-sea's
 * `shade`) read it: `float cloudShade(vec2 p, float height)`: the share of the sun's light that reaches the
 * place `p` (metres from the camera along the scene's +x and +z) at `height` metres through the decks above. */
const FIELD_GLSL = /* glsl */`
#define NB ${FRONTS.sizes.length}
uniform sampler2D uCloudNoise;
uniform vec4 uDeckA[ND];      // base (m), depth (m), the share of light a metre takes, the pattern's level where cloud begins
uniform vec4 uDeckB[ND];      // rise, floor, soft, fray
uniform vec4 uDeckC[ND];      // ragged, the weather's share, the puffs' share, 1: it casts a shadow
uniform vec4 uDeckR[ND * 8];  // four readings of the tile a deck: two rows of each one's place (x, y, the camera's offset, texels a metre)
uniform vec4 uDeckF[ND * NB];  // the broad weather's octaves a deck: the matrix from metres to lattice cells (u.x, u.y, v.x, v.y)
uniform vec4 uDeckO[ND * NB];  // and the camera's place in them: the share of its cell, the whole cells
uniform vec4 uDeckG[ND];      // the broad weather's strength (fronts, times aloft()), its first octave's seed (the next: + 7919 each), (free), its value at the place (drawn to nothing round it)
uniform vec4 uDeckH[ND];      // the camera's place (m along +x and +z from the place), one over the square of the reach of that
uniform vec4 uCloudSun;       // the sun's direction along +x and +z, its sine and cosine over the level
uniform vec4 uDeckI[ND * 4];  // each reading's whole repeats at the camera (x, y), its salt
uniform vec4 uCloudMean;      // the tile's mean
uint cloudHash(ivec2 c, uint s) {
  uint h = (uint(c.x) * 0x9E3779B1u) ^ (uint(c.y) * 0x85EBCA77u) ^ (s * 0xC2B2AE3Du);
  h ^= h >> 15; h *= 0x2C1B3C6Du; h ^= h >> 12; h *= 0x297A2D39u; h ^= h >> 15;
  return h;
}
vec2 cloudGrad(ivec2 c, uint s) { float a = (float(cloudHash(c, s) & 15u) + 0.5) * 0.39269908; return vec2(cos(a), sin(a)); }
// the sixteen directions (k + 0.5) x 22.5 degrees: the gradients' and the cells' turns
const vec2 CLOUD_DIRS[16] = vec2[16](${Array.from({length: 16}, (_, k) => `vec2(${Math.cos((k + 0.5) * Math.PI / 8).toFixed(8)}, ${Math.sin((k + 0.5) * Math.PI / 8).toFixed(8)})`).join(", ")});
vec2 gradAt(uint h, uint shift) { return CLOUD_DIRS[(h >> shift) & 15u]; }
// warpNoise(): two gradient noises from one lattice's hashes
vec2 cloudWarp(vec2 q, uint s) {
  vec2 c = floor(q), f = q - c, g = f - 1.0, u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0); ivec2 ic = ivec2(c);
  uint ha = cloudHash(ic, s), hb = cloudHash(ic + ivec2(1, 0), s), hc = cloudHash(ic + ivec2(0, 1), s), hd = cloudHash(ic + ivec2(1, 1), s);
  vec2 out2;
  for (int k = 0; k < 2; k++) {
    uint sh = uint(k * 4);
    float va = dot(gradAt(ha, sh), f), vb = dot(gradAt(hb, sh), vec2(g.x, f.y)), vc = dot(gradAt(hc, sh), vec2(f.x, g.y)), vd = dot(gradAt(hd, sh), g);
    out2[k] = 1.41421356 * (va + u.x * (vb - va) + u.y * (vc - va) + u.x * u.y * (va - vb - vc + vd));
  }
  return out2;
}
// untiled(): the tile at w (repeats from the lattice's origin, already shifted by the warp), each cell at its own offset and turn
vec4 cloudUntiled(vec2 w, uint salt, float lod) {
  vec2 sw = w - 0.5, base = floor(sw), k = smoothstep(vec2(${(0.5 - UNTILE.blend).toFixed(4)}), vec2(${(0.5 + UNTILE.blend).toFixed(4)}), sw - base);
  vec4 sum = vec4(0.0); float squares = 0.0;
  for (int j = 0; j < 4; j++) {
    ivec2 d = ivec2(j & 1, j >> 1);
    float weight = (d.x == 1 ? k.x : 1.0 - k.x) * (d.y == 1 ? k.y : 1.0 - k.y);
    if (weight <= 0.0) continue;
    vec2 cell = base + vec2(d);
    uint h = cloudHash(ivec2(cell), salt + 1u);
    vec2 turn = CLOUD_DIRS[h & 15u], l = w - cell - 0.5;
    sum += weight * (textureLod(uCloudNoise, vec2(turn.x * l.x - turn.y * l.y, turn.y * l.x + turn.x * l.y) + vec2(float((h >> 8) & 1023u), float((h >> 18) & 1023u)) / 1024.0, lod) - uCloudMean);
    squares += weight * weight;
  }
  return uCloudMean + sum * inversesqrt(squares);
}
// the warp's shift of reading r at p, in repeats
vec2 cloudShift(int r, vec2 p) {
  vec4 A = uDeckR[r], B = uDeckR[r + 1], I = uDeckI[r / 2];
  return ${UNTILE.warp.toFixed(4)} * cloudWarp((vec2(dot(A.xy, p) + A.z, dot(B.xy, p) + B.z) + I.xy) * ${(1 / UNTILE.warpSize).toFixed(8)}, uint(I.z));
}
// reading r of the tile at p (metres from the camera), a step foot metres wide, shifted by shift (the clouds' by the warp's there, the others' by none): it never repeats
vec4 cloudReadAt(int r, vec2 p, float foot, vec2 shift) {
  vec4 A = uDeckR[r], B = uDeckR[r + 1], I = uDeckI[r / 2];
  return cloudUntiled(vec2(dot(A.xy, p) + A.z, dot(B.xy, p) + B.z) + I.xy + shift, uint(I.z), log2(max(foot * A.w, 1.0)));
}
float cloudBroad(int i, vec2 p) {
  float sum = 0.0;
  for (int k = 0; k < NB; k++) {
    vec4 M = uDeckF[i * NB + k], O = uDeckO[i * NB + k];
    vec2 q = vec2(dot(M.xy, p), dot(M.zw, p)) + O.xy, c = floor(q), f = q - c; ivec2 ic = ivec2(c) + ivec2(O.zw); uint sd = (uint(uDeckG[i].y) + uint(k) * 7919u) & 0xffffffu;
    vec2 g = f - 1.0;
    float va = dot(cloudGrad(ic, sd), f), vb = dot(cloudGrad(ic + ivec2(1, 0), sd), vec2(g.x, f.y)), vc = dot(cloudGrad(ic + ivec2(0, 1), sd), vec2(f.x, g.y)), vd = dot(cloudGrad(ic + ivec2(1, 1), sd), g);
    vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
    sum += (k == 0 ? ${FRONTS.weights[0].toFixed(3)} : k == 1 ? ${FRONTS.weights[1].toFixed(3)} : ${FRONTS.weights[2].toFixed(3)}) * 1.41421356 * (va + u.x * (vb - va) + u.y * (vc - va) + u.x * u.y * (va - vb - vc + vd));
  }
  vec2 w = p + uDeckH[i].xy;
  return sum - uDeckG[i].w * exp(-dot(w, w) * uDeckH[i].z);
}
float cloudWeather(int i, vec2 p, float foot) { return 0.5 * (cloudReadAt(i * 8, p, foot, vec2(0.0)).r + cloudReadAt(i * 8 + 2, p, foot, vec2(0.0)).a) + (uDeckG[i].x > 0.0 ? uDeckG[i].x * cloudBroad(i, p) : 0.0); }
// how far the pattern stands over the level where cloud begins (x), and the puffs there (y)
vec2 cloudLevel(int i, vec2 p, float foot, float weather, vec2 shift) {
  vec4 c = cloudReadAt(i * 8 + 4, p, foot, shift);
  return vec2(mix(mix(c.r, c.g, uDeckC[i].z), weather, uDeckC[i].y) - uDeckA[i].w, c.g);
}
// a cloud's top (0 the deck's base, 1 its top) where the pattern stands v over its level
float cloudTop(int i, float v) { return min(uDeckB[i].y + sqrt(max(v, 0.0) * uDeckB[i].x), 1.0); }
float cloudShade(vec2 p, float height) {
  float lit = 1.0;
  if (uCloudSun.z < 0.03) return lit;
  for (int j = 0; j < ND; j++) {
    vec4 A = uDeckA[j];
    if (uDeckC[j].w < 0.5 || A.x < height) continue;
    float up = A.x + 0.5 * A.y - height, foot = 0.2 * A.y / uCloudSun.z + 0.02 * up;
    vec2 q = p + uCloudSun.xy * (up * uCloudSun.w / uCloudSun.z);
    vec2 lv = cloudLevel(j, q, foot, cloudWeather(j, q, foot), cloudShift(j * 8 + 4, q));
    float depth = A.z * A.y * cloudTop(j, lv.x) * smoothstep(0.0, uDeckB[j].z, lv.x);
    lit *= exp(-0.5 * depth / max(uCloudSun.z, 0.25));
  }
  return lit;
}
`;
const CLOUD_FRAG = /* glsl */`
${AIR_GLSL}
${FIELD_GLSL}
uniform vec4 uCloudGeo;       // the world's radius (m), the camera's height (m), metres a scene unit, a pixel's angle
uniform vec4 uCloudFloor;     // the dark under a giant's decks: its colour, 1 when there is one
uniform vec3 uCloudE1, uCloudE2;
uniform vec3 uDeckSun[ND], uDeckSky[ND], uDeckLow[ND], uDeckTint[ND], uDeckTint2[ND];
uniform sampler2D uCloudStripes;   // a deck's stripes: colours and lifts across it, a row a deck
uniform vec4 uDeckStripe[ND];     // north in the frame (+x, +z) over the span, the camera's place north over the span, 1 when the deck has stripes
uniform vec4 uDeckEdge[ND];   // where a deck's second colour begins: the direction (+x, +z), the camera's distance before the edge over the change's width, 1 over that width   // the sun's light at the deck, the sky's from above, what comes from below, what the cloud throws back
uniform vec4 uTowerA[NT];     // a tower's foot from the camera along +x and +z (m), its radius (m), its anvil's width over that
uniform vec4 uTowerB[NT];     // its base and top (m), where its puffs are read, the share of light a metre takes
uniform vec3 uTowerSun, uTowerSky, uTowerLow, uTowerTint;
uniform vec2 uCloudWind;      // where the wind blows to (+x, +z)
uniform vec4 uFlashA[NF];     // a flash: its place from the camera (+x, up, +z: m), its brightness now
uniform vec4 uFlashB[NF];     // its colour, its reach (m)
#ifdef BEHIND
uniform sampler2D uCloudBehind; uniform vec2 uCloudBehindSize;   // how far each ray may go before something solid (m; 0 or less: nothing), the clouds' own picture's size
#endif
varying vec3 vDir;
const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);
float farRoot(float m, float c, float d) { float s = sqrt(max(d, 0.0)); return m > 0.0 ? -c / (m + s) : -m + s; }
// the first stretch of the ray inside the shell between heights a and b: from x to y (none when y <= x)
vec2 shellSpan(float mu, float a, float b) {
  float R = uCloudGeo.x, h = uCloudGeo.y, m = (R + h) * mu, ca = (h - a) * (2.0 * R + h + a), cb = (h - b) * (2.0 * R + h + b), da = m * m - ca, db = m * m - cb;
  if (h > b) return mu >= 0.0 || db <= 0.0 ? vec2(0.0, -1.0) : vec2(cb / (-m + sqrt(db)), da > 0.0 ? ca / (-m + sqrt(da)) : farRoot(m, cb, db));
  if (h >= a) return vec2(0.0, mu < 0.0 && da > 0.0 ? ca / (-m + sqrt(da)) : farRoot(m, cb, db));
  return vec2(farRoot(m, ca, da), farRoot(m, cb, db));
}
float heightAt(float mu, float t) { float r0 = uCloudGeo.x + uCloudGeo.y, q = 2.0 * r0 * mu * t + t * t; return uCloudGeo.y + q / (sqrt(r0 * r0 + q) + r0); }
// what a bit of cloud sends to the eye: the sun's light after tau of cloud on its way (thrown onward at thin places,
// and again after many bounces, which reach deeper), the sky's on what is open to it, the light from below
vec3 cloudLit(float tau, float y, float open, float cosv, vec3 sun, vec3 sky, vec3 low) {
  float g = 0.76, fwd = (1.0 - g * g) / pow(1.0 + g * g - 2.0 * g * cosv, 1.5), phase = min(0.62 + 0.11 * fwd + 0.25 * (1.0 + cosv * cosv) * step(cosv, 0.0) * -cosv, 3.2);
  return sun * (0.5 * phase * exp(-tau) + 0.5 * exp(-0.22 * tau)) + 1.3 * sky * open * (0.45 + 0.55 * y) + low * (0.35 + 0.65 * (1.0 - y)) * (0.4 + 0.6 * exp(-0.3 * tau));
}
// a tower is a column of heaped lumps that leans and widens with height; from its seed it is still growing (a round boiling top)
// or has spread an anvil: a thin sheet drawn out downwind of its top, thinning to nothing
bool towerGrows(vec4 B) { return fract(B.z * 0.37) < 0.4; }
// the column's middle at height y (0 its foot, 1 its top), from the tower's foot (m)
vec2 towerMiddle(vec4 A, vec4 B, float y) { return uCloudWind * (A.z * 0.9 * y * y) + vec2(-uCloudWind.y, uCloudWind.x) * (A.z * 0.3 * sin(3.0 * B.z + 4.2 * y)); }
// its width there over the tower's radius, before the lumps
float towerWidth(float y, bool grows) { return (0.42 + 0.42 * pow(max(y, 0.0), 0.8)) * smoothstep(-0.02, 0.05, y) * sqrt(clamp((grows ? 1.0 - y : 0.93 - y) / (grows ? 0.22 : 0.12), 0.0, 1.0)); }
// the anvil: where its middle is from the tower's foot (xy, m), half its length along the wind (z) and across it (w)
vec4 towerAnvil(vec4 A) { float along = 1.5 * A.w * A.z; return vec4(uCloudWind * (0.75 * A.z + 0.8 * along), along, 0.7 * A.w * A.z); }
// the ray and the stretch of it now walked: its level direction, its cosine to the vertical, a pixel's angle, the stretch, the weather along it
vec2 gDh; float gMu, gCosv, gPix, gT0, gLen, gH, gPhase; vec3 gWx; vec2 gSh[3];
// what the ray has gathered: the share of light still passing, and of the thing now walked its light and its distance (each times its share)
float gT, gWay; vec3 gGot;
float deckWeather(float t) { float u = (t - gT0) / max(gLen, 1e-3) * 2.0; return u < 1.0 ? mix(gWx.x, gWx.y, u) : mix(gWx.y, gWx.z, u - 1.0); }
// the clouds' warp changes slowly too (over a few repeats): read with the weather and taken as even between
vec2 deckShift(float t) { float u = (t - gT0) / max(gLen, 1e-3) * 2.0; return u < 1.0 ? mix(gSh[0], gSh[1], u) : mix(gSh[1], gSh[2], u - 1.0); }
// a bit of cloud t metres along the ray taking the share dens x ds of the light, sending its light and the flashes' near it
void gather(float dens, float ds, float t, vec3 light) {
  vec2 p = gDh * t; float alt = heightAt(gMu, t) - gH;
  for (int f = 0; f < NF; f++) {
    vec3 d = vec3(p.x, alt, p.y) - uFlashA[f].xyz; float r2 = dot(d, d) / (uFlashB[f].w * uFlashB[f].w);
    light += uFlashB[f].rgb * (uFlashA[f].w / ((1.0 + r2) * (1.0 + r2)));
  }
  float a = 1.0 - exp(-dens * ds);
  gGot += gT * a * light; gWay += gT * a * t; gT *= 1.0 - a;
}
// the part of a step (from x to y, each 0 to 1 along it; none when y <= x) that lies in a deck's cloud, the pattern going
// evenly from v0 to v1 over the step and the height in the deck from y0 to y1: under cloud (v > 0) and under its top
vec2 cloudPart(int i, float v0, float v1, float y0, float y1) {
  float a0 = v0 < 0.0 ? v0 / (v0 - v1) : 0.0, a1 = v1 < 0.0 ? v0 / (v0 - v1) : 1.0, rise = uDeckB[i].x;
  if (uDeckB[i].y >= 1.0) return vec2(a0, a1);
  float Y0 = y0 - uDeckB[i].y, dY = y1 - y0, z = clamp(-Y0 / (abs(dY) > 1e-7 ? dY : 1e-7), 0.0, 1.0);
  // under the height every cloud of the deck reaches
  vec2 low = abs(dY) <= 1e-7 ? (Y0 <= 0.0 ? vec2(0.0, 1.0) : vec2(1.0, 0.0)) : (dY > 0.0 ? vec2(0.0, z) : vec2(z, 1.0));
  low = vec2(max(low.x, a0), min(low.y, a1));
  // over it: where the height's square is under the pattern's rise (the top is a square root of the pattern)
  float qa = dY * dY, qb = 2.0 * Y0 * dY - rise * (v1 - v0), qc = Y0 * Y0 - rise * v0, disc = qb * qb - 4.0 * qa * qc;
  vec2 high = vec2(1.0, 0.0);
  if (disc > 0.0) {
    float q = -0.5 * (qb + (qb < 0.0 ? -1.0 : 1.0) * sqrt(disc)), r1 = q / max(qa, 1e-12), r2 = abs(q) > 1e-20 ? qc / q : r1;
    high = vec2(max(min(r1, r2), a0), min(max(r1, r2), a1));
    if (abs(dY) <= 1e-7) { if (Y0 <= 0.0) high = vec2(1.0, 0.0); } else if (dY > 0.0) high.x = max(high.x, z); else high.y = min(high.y, z);
  }
  if (low.y <= low.x) return high;
  if (high.y <= high.x) return low;
  return vec2(min(low.x, high.x), max(low.y, high.y));
}
// a deck's stripe at a place: its colour and how much more cloud it has (the stripes' edges wander with the puffs)
vec4 cloudStripe(int i, vec2 p, float wander) {
  vec4 S = uDeckStripe[i];
  return texture2D(uCloudStripes, vec2(0.5 + 0.5 * (dot(p, S.xy) + S.z) + 0.03 * (wander - 0.5), (float(i) + 0.5) / float(ND)));
}
// a deck from t0 on for len metres. Coarse steps find where cloud may be (the pattern read as its mean over the step, with
// room for what the mean hides); each such step is walked in fine ones. A thin sheet takes three steps and no fine ones.
void walkDeck(int it, float t0, float len) {
  vec4 A = uDeckA[it], B = uDeckB[it];
  bool sheet = B.y >= 1.0, have = false, inside = false;
#ifdef STRIPES
  bool striped = uDeckStripe[it].w > 0.5;
#else
  const bool striped = false;
#endif
  int coarse = sheet ? 3 : COARSE, fine = sheet ? 1 : FINE;
  // even steps through a deck seen from outside; from inside it shorter ones first
  if (t0 > 0.0 && !sheet) { float shift = (gPhase - 0.5) * len / float(coarse * fine); t0 += shift; len -= shift; }
  float near = t0 > 0.0 ? 0.0 : 0.7, texels = uDeckR[it * 8 + 4].w / 64.0, cosv = gCosv;
  vec2 last = vec2(0.0);
  for (int c = 0; c < coarse; c++) {
    float u0 = float(c) / float(coarse), u1 = float(c + 1) / float(coarse), lift = 0.0;
    float Ta = t0 + len * u0 * (1.0 - near + near * u0), D = t0 + len * u1 * (1.0 - near + near * u1) - Ta;
    if (!sheet) {
      float tm = Ta + 0.5 * D, wide = max(tm * gPix, 0.6 * D);
#ifdef STRIPES
      if (striped) lift = cloudStripe(it, gDh * tm, 0.5).a;      // a stripe's lift changes slowly: read once a coarse step
#endif
      float most = cloudLevel(it, gDh * tm, wide, deckWeather(tm), deckShift(tm)).x + 0.45 * min(wide * texels, 1.0) + lift;
      // no cloud near, or the whole step passes over the highest top there may be
      if (most <= 0.0 || (min(heightAt(gMu, Ta), heightAt(gMu, Ta + D)) - A.x) / A.y > cloudTop(it, most)) { have = false; inside = false; continue; }
    }
    for (int s = 0; s < fine; s++) {
      // a fine step is a stretch of the ray: the pattern is read at its ends and taken as even between them, and so is the
      // height; the part of the step that lies in the cloud (under its top, which rises with the pattern) is then known exactly
      float ta = Ta + D * float(s) / float(fine), tb = Ta + D * float(s + 1) / float(fine), ds = tb - ta, foot = max(tb * gPix, ds);
      // where a step is coarser than the clouds, the pattern is their mean there and its edge is as much softer: a share of cloud, not a cloud
      float blur = 0.16 * min(foot * texels, 1.0), weather = deckWeather(tb);
      vec2 shift = deckShift(tb), l0 = have ? last : cloudLevel(it, gDh * ta, foot, deckWeather(ta), deckShift(ta)) + vec2(blur, 0.0), l1 = cloudLevel(it, gDh * tb, foot, weather, shift) + vec2(blur, 0.0);
      if (!have) l0.x += lift;
      l1.x += lift;
      last = l1; have = true;
      if (max(l0.x, l1.x) <= 0.0) { inside = false; continue; }
      float y0 = (heightAt(gMu, ta) - A.x) / A.y, y1 = (heightAt(gMu, tb) - A.x) / A.y;
      float fray = B.w * (1.0 - cloudReadAt(it * 8 + 6, gDh * (ta + 0.5 * ds) + (0.3 * (y0 + y1) * A.y) * vec2(0.8, -0.6), foot, vec2(0.0)).b) * (0.35 + 0.65 * clamp(0.5 * (y0 + y1), 0.0, 1.0));
      vec2 part = cloudPart(it, l0.x - fray, l1.x - fray, y0, y1);
      if (part.y <= part.x) { inside = false; continue; }
      // what is seen of the cloud is what the ray meets first
      // a face (the ray comes into cloud here): the fine caps, read as finely as a pixel shows them, push it in along the ray, more
      // at a top than at a base: lumps and frayed edges, and where the cloud is thinner than the push a hole. Far off the caps are
      // their mean and the push is even
      float lump = 0.5, lit = 0.5;
      if (!sheet && (part.x > 0.0 || !inside)) {
        float te = ta + ds * part.x, ye = mix(y0, y1, part.x), wide = te * gPix;
        vec2 pe = gDh * te + (ye * A.y) * vec2(0.5, -0.4);
        vec4 caps = cloudReadAt(it * 8 + 6, pe, wide, vec2(0.0));
        lump = smoothstep(0.15, 0.85, 0.55 * caps.g + 0.45 * caps.b);
        // a lump's crest is lit, the crease between two lumps is not
        lit = lump;
        part.x += 3.4 * B.w * A.y * (1.0 - lump) * (0.25 + 0.75 * clamp(ye, 0.0, 1.0)) / ds;
      }
      inside = part.y >= 1.0;
      if (part.y <= part.x) continue;
      float fr = mix(part.x, part.y, 0.2), v = max(mix(l0.x, l1.x, fr) - fray, 0.0), top = cloudTop(it, v), t = ta + ds * fr, y = mix(y0, y1, fr);
      vec2 p = gDh * t;
      float dens = A.z * (part.y - part.x) * smoothstep(0.0, B.z + 2.0 * blur, max(mix(l0.x, l1.x, 0.5 * (part.x + part.y)) - fray, 0.0)) * smoothstep(-0.02, 0.05, y - uDeckC[it].x * (1.0 - mix(l0.y, l1.y, fr)));
      if (dens <= 0.0) continue;
      // towards the sun: the cloud over this place, and over a place a little way along the light's path
      float reach = 0.3 * A.y, ys = y + reach * uCloudSun.z / A.y;
      vec2 ls = cloudLevel(it, p + uCloudSun.xy * (reach * uCloudSun.w), max(foot, 0.25 * reach), weather, shift);
      float topS = cloudTop(it, ls.x) * smoothstep(0.0, B.z, ls.x);
      float tau = A.z * A.y * (0.35 * max(top - y, 0.0) + 0.65 * max(topS - ys, 0.0)) / max(uCloudSun.z, 0.22);
      float open = exp(-0.35 * A.z * A.y * max(top - y, 0.0)) * (0.55 + 0.45 * top);
      // a top's slope towards the sun: the faces turned to it are bright, those turned away grey (only near the top: deeper in, the light has no direction left)
      float slope = (topS - top) * A.y / reach, facing = clamp((uCloudSun.z - slope * uCloudSun.w) * inversesqrt(1.0 + slope * slope), 0.0, 1.0);
      vec3 sun = uDeckSun[it] * cloudShade(p, A.x + A.y) * mix(1.0, clamp(0.4 + 0.75 * facing / max(uCloudSun.z, 0.3), 0.3, 1.6), exp(-2.0 * A.z * A.y * max(top - y, 0.0)) * step(B.y, 0.99));
      // the fine puffs' creases are a little darker, and so is a face the fine caps pushed far in; a thin sheet passes on the bright sky behind it besides (a look: a third more light)
      vec3 tint = mix(uDeckTint[it], uDeckTint2[it], smoothstep(-1.0, 1.0, dot(p, uDeckEdge[it].xy) * uDeckEdge[it].w - uDeckEdge[it].z));
#ifdef STRIPES
      if (striped) tint = cloudStripe(it, p, mix(l0.y, l1.y, fr)).rgb;
#endif
      gather(dens, ds, t, (sheet ? 1.3 : (1.0 - 2.2 * fray) * (0.8 + 0.2 * lump) * (0.7 + 0.6 * lit)) * tint * uAirLight * cloudLit(tau, clamp(y, 0.0, 1.0), open, cosv, sun, uDeckSky[it], uDeckLow[it]));
      if (gT < 0.015) return;
    }
  }
}
// a tower from t0 on for len metres: a step is a height and a stretch of the ray, and the tower's round body at that height is cut with that stretch exactly
void walkTower(int j, float t0, float len) {
  vec4 A = uTowerA[j], B = uTowerB[j], N = towerAnvil(A);
  bool grows = towerGrows(B);
  float a = max(dot(gDh, gDh), 1e-9), high = B.y - B.x;
  vec2 across = vec2(-uCloudWind.y, uCloudWind.x), ce = A.xy + N.xy;
  // the anvil's flat ball in the ray's own numbers (its length along the wind, its width across)
  float dw = dot(gDh, uCloudWind), dx = dot(gDh, across), cw = dot(ce, uCloudWind), cx = dot(ce, across);
  float ea = dw * dw / (N.z * N.z) + dx * dx / (N.w * N.w), eb = dw * cw / (N.z * N.z) + dx * cx / (N.w * N.w), ec = cw * cw / (N.z * N.z) + cx * cx / (N.w * N.w), av = 0.065 * high;
  for (int s = 0; s < COARSE * 3; s++) {
    float ds = len / float(COARSE * 3), ta = t0 + ds * float(s), tb = ta + ds, t = ta + 0.5 * ds, foot = max(t * gPix, 0.5 * ds);
    float alt = heightAt(gMu, t), y = (alt - B.x) / high;
    if (y <= 0.0 || y >= 1.0) continue;
    vec2 mid = A.xy + towerMiddle(A, B, y), q = gDh * t - mid;
    float lod = log2(max(foot * 256.0 / (A.z * 1.6), 1.0));
    float n1 = textureLod(uCloudNoise, q / (A.z * 1.6) + vec2(B.z + 0.9 * y, 0.37 * B.z - 0.6 * y), lod).g;
    float n2 = textureLod(uCloudNoise, vec2(dot(q, vec2(0.6, 0.8)) / (A.z * 1.3) + B.z, alt / (A.z * 1.1)), lod + 0.3).g;
    float wide = towerWidth(y, grows) * (0.6 + 0.8 * (0.5 * n1 + 0.5 * n2));
    // the column: a round body of that width round its middle at this height, cut with the step
    float b = dot(gDh, mid), d = b * b - a * (dot(mid, mid) - wide * wide * A.z * A.z), c0 = 1.0, c1 = 0.0, e0 = 1.0, e1 = 0.0, thin = 0.0;
    if (d > 0.0) { c0 = max(ta, (b - sqrt(d)) / a); c1 = min(tb, (b + sqrt(d)) / a); }
    if (!grows) {
      // the anvil, cut with the step (the height taken as even along it); its cloud thins downwind and is drawn out in streaks
      float sl = (heightAt(gMu, tb) - heightAt(gMu, ta)) / ds, e = alt - sl * t - mix(B.x, B.y, 0.9);
      float qa = ea + sl * sl / (av * av), qb = -eb + sl * e / (av * av), qc = ec + e * e / (av * av) - 1.0, qd = qb * qb - qa * qc;
      if (qd > 0.0) { e0 = max(ta, (-qb - sqrt(qd)) / qa); e1 = min(tb, (-qb + sqrt(qd)) / qa); }
      if (e1 > e0) {
        vec2 r = gDh * (0.5 * (e0 + e1)) - ce; float u = dot(r, uCloudWind) / N.z, w = dot(r, across) / N.w;
        float streak = textureLod(uCloudNoise, vec2(u * 0.35 + B.z, w * 1.6 + 0.3 * B.z), log2(max(foot * 256.0 * 1.6 / N.w, 1.0))).a;
        thin = 0.4 * (e1 - e0) / ds * smoothstep(0.25, 0.75, streak + 0.55 * (0.2 - u)) * smoothstep(1.0, 0.75, abs(w));
      }
    }
    float column = max(c1 - c0, 0.0) / ds * smoothstep(0.0, 0.1, sqrt(max(d, 0.0)) / (a * A.z)), lump = 0.5;
    bool anvil = thin > column;
    if (!anvil && column > 0.0) {
      // the fine caps push the column's face in along the ray: lumps on lumps (as a deck's face)
      vec4 caps = textureLod(uCloudNoise, (gDh * c0 - mid) / (A.z * 0.55) + vec2(alt / (A.z * 0.7), B.z), log2(max(c0 * gPix * 256.0 / (A.z * 0.55), 1.0)));
      lump = smoothstep(0.15, 0.85, 0.55 * caps.g + 0.45 * caps.b);
      c0 += 0.22 * A.z * (1.0 - lump);
      column = max(c1 - c0, 0.0) / ds * smoothstep(0.0, 0.1, sqrt(max(d, 0.0)) / (a * A.z));
    }
    float dens = B.w * max(column, thin);
    if (dens <= 0.0) continue;
    t = anvil ? mix(e0, e1, 0.25) : mix(c0, c1, 0.2); q = gDh * t - mid;
    // towards the sun: out through the column's side, or up through its top; an anvil is thin
    float rr = length(q) / A.z, xs = dot(q, uCloudSun.xy) / A.z, side = (sqrt(max(wide * wide - rr * rr + xs * xs, 0.0)) - xs) * A.z / max(uCloudSun.w, 0.15);
    float path = anvil ? 0.3 * av : (uCloudSun.z > 0.02 ? min(side, (B.y - alt) / uCloudSun.z) : side);
    float open = anvil ? 1.0 : mix(0.35 + 0.65 * smoothstep(0.3, 1.0, rr / max(wide, 1e-3)), 1.0, y * y);
    // the foot stands in its own rain and in the anvil's shade: darker
    float shaded = anvil ? 1.0 : mix(0.5, 1.0, smoothstep(0.0, 0.4, y)) * (0.75 + 0.5 * lump);
    gather(dens, ds, t, shaded * uTowerTint * uAirLight * cloudLit(0.55 * B.w * max(path, 0.0), y, open, gCosv, uTowerSun, uTowerSky, uTowerLow * (anvil ? 0.4 : 1.0)));
    if (gT < 0.015) return;
  }
}
void main() {
  vec3 rd = normalize(vDir);
  float mu = dot(rd, uAirUp), cosv = dot(rd, uAirSun), R = uCloudGeo.x, h = uCloudGeo.y, pix = uCloudGeo.w, unit = uCloudGeo.z;
  vec2 dh = vec2(dot(rd, uCloudE1), dot(rd, uCloudE2));
  gDh = dh; gMu = mu; gPix = pix; gCosv = cosv; gH = h;
  // four neighbouring pixels walk their steps a quarter of a step apart; the picture laid over the scene is their mean
  vec2 cell = mod(floor(gl_FragCoord.xy), 2.0);
  gPhase = mod(2.0 * cell.x + 3.0 * cell.y, 4.0) / 4.0 + 0.125;
  float m = (R + h) * mu, cg = h * (2.0 * R + h), dg = m * m - cg, tEnd = mu < 0.0 && dg > 0.0 ? cg / (-m + sqrt(dg)) : 1e20;
#ifdef BEHIND
  // something stands in the sky (a ground with relief): no cloud is gathered behind it
  float solid = texture2D(uCloudBehind, gl_FragCoord.xy / uCloudBehindSize).r;
  if (solid > 0.0) tEnd = min(tEnd, solid);
#endif
  float from[ND + NT], to[ND + NT];
  for (int i = 0; i < ND; i++) {
    vec2 s = shellSpan(mu, uDeckA[i].x, uDeckA[i].x + uDeckA[i].y);
    s.y = min(min(s.y, tEnd), s.x + 0.6 * s.x + 16.0 * uDeckA[i].y);
    from[i] = s.y > s.x ? s.x : 1e20; to[i] = s.y;
  }
  for (int j = 0; j < NT; j++) {
    vec4 A = uTowerA[j], B = uTowerB[j];
    // the leaning column's cylinder, and the anvil's above it downwind: the stretch from the first to the last of them
    vec4 N = towerAnvil(A);
    vec2 ct = A.xy + uCloudWind * (0.45 * A.z), ca = A.xy + N.xy;
    float a = max(dot(dh, dh), 1e-9), bt = dot(dh, ct), ba = dot(dh, ca);
    float dt = bt * bt - a * (dot(ct, ct) - A.z * A.z * 4.4), da = towerGrows(B) ? -1.0 : ba * ba - a * (dot(ca, ca) - N.z * N.z * 1.1);
    vec2 st = shellSpan(mu, B.x, B.y), sa = shellSpan(mu, mix(B.x, B.y, 0.82), mix(B.x, B.y, 0.98));
    st = vec2(max(st.x, (bt - sqrt(max(dt, 0.0))) / a), dt > 0.0 ? min(st.y, (bt + sqrt(dt)) / a) : -1.0);
    sa = vec2(max(sa.x, (ba - sqrt(max(da, 0.0))) / a), da > 0.0 ? min(sa.y, (ba + sqrt(da)) / a) : -1.0);
    bool trunk = st.y > max(st.x, 0.0), anvil = sa.y > max(sa.x, 0.0);
    float t0 = max(trunk ? (anvil ? min(st.x, sa.x) : st.x) : sa.x, 0.0), t1 = min(trunk ? (anvil ? max(st.y, sa.y) : st.y) : sa.y, tEnd);
    from[ND + j] = (trunk || anvil) && A.z > 0.0 && t1 > t0 ? t0 : 1e20; to[ND + j] = t1;
  }
  vec3 sum = vec3(0.0);
  gT = 1.0;
  for (int n = 0; n < ND + NT; n++) {
    int it = -1; float t0 = 1e19;
    for (int k = 0; k < ND + NT; k++) if (from[k] < t0) { t0 = from[k]; it = k; }
    if (it < 0 || gT < 0.015) break;
    from[it] = 1e20;
    float len = to[it] - t0, before = gT;
    gGot = vec3(0.0); gWay = 0.0;
    if (it < ND) {
      // the weather and the clouds' warp change slowly: read at three places along the stretch
      gT0 = t0; gLen = len;
      for (int k = 0; k < 3; k++) { float t = t0 + 0.5 * float(k) * len; gWx[k] = cloudWeather(it, dh * t, max(t * pix, 0.2 * len)); gSh[k] = cloudShift(it * 8 + 4, dh * t); }
      walkDeck(it, t0, len);
    } else walkTower(it - ND, t0, len);
    float w = before - gT;
    if (w > 0.0015) {
      // the film look's dusk curve, then the air between the camera and this cloud
      vec3 c = gGot / w, through; float hit;
      c *= pow(max(dot(c, LUMA) / uAirDusk.y, 1.0), -uAirDusk.x);
      vec3 air = airLight(mu, cosv, gWay / w / unit * uAirGeo.w, through, hit);
      sum += w * (c * through + air);
    } else gT = before;
  }
  float T = gT;
  // a giant: under the decks the dark, to the horizon
  if (uCloudFloor.w > 0.5 && tEnd < 1e19) {
    float under = -(asin(clamp(mu, -1.0, 1.0)) + uAirMap.x), cover = clamp(under / pix, 0.0, 1.0);
    vec3 through; float hit;
    vec3 air = airLight(mu, cosv, tEnd / unit * uAirGeo.w, through, hit);
    sum += T * cover * (uCloudFloor.rgb * uAirLight * (uDeckLow[0] + 0.3 * uDeckSky[0]) * through + air);
    T *= 1.0 - cover;
  }
  gl_FragColor = vec4(sum, 1.0 - T);
}`;
const QUAD_VERT = "varying vec2 vUv; void main() { vUv = 0.5 * position.xy + 0.5; gl_Position = vec4(position.xy, 0.0, 1.0); }";
// the clouds' picture laid over what is behind it
const OVER_FRAG = /* glsl */`
${DISPLAY_GLSL}
uniform sampler2D uCloudPicture; uniform float uDisplay, uGrain; uniform vec2 uCloudTexel;
varying vec2 vUv;
void main() {
  // four readings half a texel of the clouds' picture apart: an edge drawn at a share of the picture's size comes out soft, not in blocks
  vec4 c = 0.25 * (texture2D(uCloudPicture, vUv + uCloudTexel) + texture2D(uCloudPicture, vUv - uCloudTexel) + texture2D(uCloudPicture, vUv + uCloudTexel * vec2(1.0, -1.0)) + texture2D(uCloudPicture, vUv + uCloudTexel * vec2(-1.0, 1.0)));
  if (c.a < 0.002) discard;
  float n = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  vec3 shown = display(c.rgb / c.a);
  float grain = mix(uGrain, 1.0, smoothstep(0.45, 0.8, dot(shown, vec3(0.3333))));
  gl_FragColor = uDisplay < 0.5 ? vec4(max(c.rgb * (1.0 + n * 0.004), 0.0), c.a) : vec4((shown + n * grain / 255.0) * c.a, c.a);
}`;

const OPTIONS = Object.freeze({sky: null, decks: null, towers: null, lightning: null, seed: 1, wind: 12, direction: 70, quality: "standard", floor: null, anchor: Object.freeze([0, 1, 0]), behind: null});

/** Clouds under an air: `object` (add it to the scene), `update(t, {camera})`, `decks`, `towers`, `flashes(t)`,
 * `coverAt(deck, x, z, t)`, `shade` (the decks' shadow for vidgen/space-sea), `horizon(deck)`. */
export class Clouds {
  /** `renderer`: the page's; `sky`: the air of vidgen/space-air the clouds stand in (its world's radius is height 0,
   * its sun and exposure light them); `options`: `sky` (a name of SKIES) or `decks` (a list of names of DECKS
   * or {type, base, top, cover, ...}, at most MOST.decks), `towers` (a number, or {count, spread, radius, base,
   * top, anvil, density, color, at}), `lightning` ({rate (flashes a minute from the seed), times (seconds: numbers,
   * ctx.music's events, or a track of vidgen/music-time), power, color, radius (metres), from, to}), `seed`, `wind`
   * (m/s) and `direction` (degrees: where it blows to, as sunDirection's azimuth), `quality` (a name of
   * QUALITIES), `floor` (a giant's dark under the decks: a colour; giantSky() gives one),
   * `anchor` (as vidgen/space-sea's), `behind` ({texture}: how far each ray of the picture may go before something solid, metres, such as
   * `land(...).behind` of vidgen/space-land: a mountain then hides the cloud behind it and stands in the cloud before it; update the ground before the clouds). `clouds(renderer, sky, giantSky("jupiter", {scale: sky.model.H}))` is a giant's sky. */
  constructor(renderer, sky, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("clouds(renderer, sky, options): the first argument must be the page's THREE.WebGLRenderer");
    if (!sky || !sky.uniforms || !sky.model || typeof sky.under !== "function") throw fail("clouds(renderer, sky, options): the second argument must be the air the clouds stand in (air(renderer, ...) of vidgen/space-air)");
    known("the options", options, [...Object.keys(OPTIONS), "band", "next"]);
    let o = {...OPTIONS, ...options};
    if (o.sky !== null) {
      const key = String(o.sky).trim().toLowerCase();
      if (!(key in SKIES)) throw fail(`no sky "${o.sky}"${hint(key, Object.keys(SKIES))}; ready-made: ${Object.keys(SKIES).join(", ")}`);
      o = {...o, ...SKIES[key], ...Object.fromEntries(Object.entries(options).filter(([k]) => k !== "sky"))};
    }
    this.options = o;
    if (!(o.quality in QUALITIES)) throw fail(`quality must be one of ${Object.keys(QUALITIES).join(", ")}, got ${JSON.stringify(o.quality)}${hint(o.quality, Object.keys(QUALITIES))}`);
    number("seed", o.seed, 0, 2 ** 32 - 1); number("wind (m/s)", o.wind, 0, 400); number("direction (degrees)", o.direction, -360, 360);
    if (o.decks !== null && !Array.isArray(o.decks)) throw fail(`decks must be a list of decks, got ${JSON.stringify(o.decks)}`);
    const list = (o.decks ?? ["cumulus"]).map((d) => deckOf(d)).sort((a, b) => a.base - b.base);
    if (list.length > MOST.decks) throw fail(`at most ${MOST.decks} decks, got ${list.length}`);
    this.renderer = renderer; this.sky = sky;
    const [share, coarse, fine] = QUALITIES[o.quality];
    this.share = share;
    /** The decks, the lowest first: each deckField()'s (deckOf()'s numbers, `level`, `span`, `reads`, `valueAt`, `coverAt`). */
    this.decks = list.map((d, i) => deckField(d, {seed: o.seed, wind: o.wind, direction: o.direction, index: i}));
    const made = o.towers === null || o.towers === false || o.towers === 0 ? {list: [], density: TOWERS.density, color: TOWERS.color} : towerList(o.towers, o.seed);
    /** The towers: {x, z, radius, base, top, anvil, turn} each (metres; x and z along the scene's +x and +z). */
    this.towers = made.list; this._tower = made;
    this._flashes = o.lightning === null || o.lightning === false ? [] : stormOf(o.lightning, {seed: o.seed, towers: this.towers, deck: this.decks[0]});
    const anchor = new THREE.Vector3(...(Array.isArray(o.anchor) ? o.anchor : [o.anchor.x, o.anchor.y, o.anchor.z]));
    if (anchor.lengthSq() === 0) throw fail("anchor: the vector is zero");
    anchor.normalize();
    const e2 = new THREE.Vector3(0, 0, 1).addScaledVector(anchor, -anchor.z);
    if (e2.lengthSq() < 1e-6) e2.set(0, -1, 0).addScaledVector(anchor, anchor.y);
    e2.normalize();
    this.frame = {anchor, e1: new THREE.Vector3().crossVectors(anchor, e2).normalize(), e2};
    const nd = this.decks.length, nt = Math.max(this.towers.length, 1), nf = MOST.flashes, v4 = () => new THREE.Vector4(), v3 = () => new THREE.Vector3();
    const floor = o.floor === null ? null : linearColor("floor", o.floor);
    this.noise = new THREE.DataTexture(noiseTile().data, TILE, TILE, THREE.RGBAFormat, THREE.UnsignedByteType);
    Object.assign(this.noise, {wrapS: THREE.RepeatWrapping, wrapT: THREE.RepeatWrapping, minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, generateMipmaps: true, needsUpdate: true});
    // what the decks' pattern needs: the clouds' own shader's and a shadow's on something else
    this.fieldUniforms = {uCloudNoise: {value: this.noise}, uCloudMean: {value: new THREE.Vector4(...noiseTile().mean)}, uCloudSun: {value: v4()},
      uDeckA: {value: this.decks.map((d) => new THREE.Vector4(d.base, d.depth, d.density, d.level))}, uDeckB: {value: this.decks.map((d) => new THREE.Vector4(d.rise / d.span, d.floor, d.soft, d.fray))},
      uDeckC: {value: this.decks.map((d) => new THREE.Vector4(d.ragged, d.weather, d.puff, d.density * d.depth > 1 ? 1 : 0))}, uDeckR: {value: Array.from({length: nd * 8}, v4)}, uDeckI: {value: Array.from({length: nd * 4}, v4)},
      uDeckF: {value: this.decks.flatMap((d) => d.broad.map((r) => new THREE.Vector4(r.u[0], r.u[1], r.v[0], r.v[1])))}, uDeckO: {value: Array.from({length: nd * FRONTS.sizes.length}, v4)},
      uDeckG: {value: this.decks.map((d) => new THREE.Vector4(d.fronts, d.broad[0].seed, 0, d.middle))}, uDeckH: {value: this.decks.map((d) => new THREE.Vector4(0, 0, d.reach, 0))}};
    this.uniforms = {...sky.uniforms, ...this.fieldUniforms, uCloudGeo: {value: new THREE.Vector4(sky.model.radius, 10, sky.options.unit, 0.002)},
      uCloudFloor: {value: new THREE.Vector4(...(floor ?? [0, 0, 0]), floor ? 1 : 0)}, uCloudE1: {value: this.frame.e1}, uCloudE2: {value: this.frame.e2},
      uCloudView: {value: new THREE.Matrix4()}, uCloudWind: {value: new THREE.Vector2(Math.sin(o.direction * RAD), -Math.cos(o.direction * RAD))}, uCloudProj: {value: v4()},
      uDeckSun: {value: this.decks.map(v3)}, uDeckSky: {value: this.decks.map(v3)}, uDeckLow: {value: this.decks.map(v3)}, uDeckTint: {value: this.decks.map((d) => new THREE.Vector3(...d.color))}, uDeckTint2: {value: this.decks.map((d) => new THREE.Vector3(...(d.beyond ?? d).color))}, uDeckEdge: {value: this.decks.map(v4)}, uDeckStripe: {value: this.decks.map(v4)}, uCloudStripes: {value: null},
      uTowerA: {value: Array.from({length: nt}, v4)}, uTowerB: {value: Array.from({length: nt}, v4)}, uTowerSun: {value: v3()}, uTowerSky: {value: v3()}, uTowerLow: {value: v3()}, uTowerTint: {value: new THREE.Vector3(...made.color)},
      uFlashA: {value: Array.from({length: nf}, v4)}, uFlashB: {value: Array.from({length: nf}, v4)}};
    if (o.behind !== null) {
      if (!o.behind || !o.behind.texture || !o.behind.texture.isTexture) throw fail("behind must be {texture}: a picture of how far each ray may go (metres), such as land(...).behind of vidgen/space-land");
      this.uniforms.uCloudBehind = {value: o.behind.texture}; this.uniforms.uCloudBehindSize = {value: new THREE.Vector2(4, 4)};
    }
    // the decks' stripes: a row a deck, 64 across (a deck without stripes: its own colour, no lift)
    const rows = new Uint16Array(64 * nd * 4);
    this.decks.forEach((d, i) => { for (let k = 0; k < 64; k++) {
      const c = d.stripes ? d.stripes.colors[Math.min(d.stripes.colors.length - 1, Math.floor(k * d.stripes.colors.length / 64))] : [...d.color, 0];
      for (let j = 0; j < 4; j++) rows[(i * 64 + k) * 4 + j] = THREE.DataUtils.toHalfFloat(c[j]);
    } });
    this.stripes = new THREE.DataTexture(rows, 64, nd, THREE.RGBAFormat, THREE.HalfFloatType);
    Object.assign(this.stripes, {minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping, needsUpdate: true});
    this.uniforms.uCloudStripes.value = this.stripes;
    this._pass = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({uniforms: this.uniforms, defines: {ND: nd, NT: nt, NF: nf, COARSE: coarse, FINE: fine, ...(this.decks.some((d) => d.stripes) ? {STRIPES: 1} : {}), ...(o.behind !== null ? {BEHIND: 1} : {})}, vertexShader: CLOUD_VERT, fragmentShader: CLOUD_FRAG,
      depthTest: false, depthWrite: false, toneMapped: false, fog: false}));
    this._pass.frustumCulled = false;
    this._scene = new THREE.Scene(); this._scene.add(this._pass); this._camera = new THREE.Camera();
    this.target = new THREE.WebGLRenderTarget(4, 4, {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: false});
    this.material = new THREE.ShaderMaterial({uniforms: {uCloudPicture: {value: this.target.texture}, uDisplay: {value: 0}, uGrain: {value: 2}, uCloudTexel: {value: new THREE.Vector2()}}, vertexShader: QUAD_VERT, fragmentShader: OVER_FRAG,
      depthTest: false, depthWrite: false, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    /** The clouds: drawn after the air's dome and the sea, before the scene's other things (which stand in front of every cloud). */
    this.object = new THREE.Mesh(this._pass.geometry, this.material);
    this.object.name = "clouds"; this.object.frustumCulled = false; this.object.renderOrder = -800;
    this.object.onBeforeRender = (r) => { this.material.uniforms.uDisplay.value = r.getRenderTarget() === null ? 1 : 0; this.material.uniformsNeedUpdate = true; };
    /** The decks' shadow for vidgen/space-sea: `sea(renderer, sky, {shade: weather.shade})`. */
    this.shade = {glsl: `#define ND ${nd}\n${FIELD_GLSL}\nfloat seaShade(vec2 p) { return cloudShade(p, 0.0); }`, uniforms: this.fieldUniforms};
    // a giant has no ground: the dark under the decks covers what is under the horizon
    if (floor) sky.under(true);
    this._lights = "";
    this.material.addEventListener("dispose", () => { this.noise.dispose(); this.stripes.dispose(); this.target.dispose(); this._pass.material.dispose(); });
    this.t = 0; this.height = 0;
  }

  /** How much cloud a deck has over the scene's (x, z) at time `t` (seconds; default the last update's), as seen from
   * the last update's camera height (aloft()): 0 where the sky is open, towards 1 in a cloud's middle. `deck`: its place in `decks` or its name. */
  coverAt(deck, x, z, t = this.t) {
    const d = typeof deck === "number" ? this.decks[deck] : this.decks.find((q) => q.name === deck);
    if (!d) throw fail(`coverAt: no deck ${JSON.stringify(deck)}; there are: ${this.decks.map((q) => q.name).join(", ")}`);
    return d.coverAt(x, z, t, this.height);
  }
  /** A deck's horizon for the camera of the last update: {distance (m), dip (degrees)} to its top. */
  horizon(deck = 0) { return deckHorizon(this.sky.model.radius, this.sky.state.height, this.decks[deck].top); }
  /** The flashes seen at time `t`: [{place: [x, height, z] (metres), level, color, radius}]. */
  flashes(t = this.t) {
    return this._flashes.filter((f) => t >= f.time && t < f.time + FLASH_SECONDS).map((f) => ({place: f.place, level: f.power * flashLevel(t - f.time, f.strokes), color: f.color, radius: f.radius, follows: f.follows}));
  }

  /** The clouds at scene time `t` for `camera` (the THREE.PerspectiveCamera the picture is drawn with): the
   * wind's drift, the light at each deck, the flashes, and the clouds' own picture. Call it before every draw,
   * after the air's `update` with the same camera. */
  update(t = 0, {camera = null} = {}) {
    number("update: the time (seconds)", t, -1e9, 1e9);
    if (!camera || !camera.isPerspectiveCamera) throw fail("update(t, {camera}): the camera the picture is drawn with (a THREE.PerspectiveCamera)");
    const sky = this.sky, m = sky.model, unit = sky.options.unit, u = this.uniforms, f = this.frame, r = this.renderer;
    camera.updateMatrixWorld();
    const e = camera.matrixWorld.elements, c = sky.state.center, d = new THREE.Vector3(e[12] - c[0], e[13] - c[1], e[14] - c[2]);
    const h = Math.max(d.length() * unit - m.radius, 0.5), x = d.dot(f.e1) * unit, z = d.dot(f.e2) * unit;
    this.t = t;
    const size = r.getDrawingBufferSize(new THREE.Vector2()), w = Math.max(2, Math.ceil(size.x * this.share)), hgt = Math.max(2, Math.ceil(size.y * this.share));
    if (this.target.width !== w || this.target.height !== hgt) this.target.setSize(w, hgt);
    if (u.uCloudBehindSize) u.uCloudBehindSize.value.set(w, hgt);
    this.material.uniforms.uCloudTexel.value.set(0.5 / w, 0.5 / hgt).multiplyScalar(this.share < 1 ? 1 : 0);
    const p = camera.projectionMatrix.elements;
    u.uCloudGeo.value.set(m.radius, h, unit, 2 / (p[5] * hgt));
    u.uCloudView.value.copy(camera.matrixWorld); u.uCloudProj.value.set(1 / p[0], 1 / p[5], p[8], p[9]);
    // the sun in the decks' frame
    const sun = sky.sun, sx = sun.dot(f.e1), sz = sun.dot(f.e2), flat = Math.hypot(sx, sz), mus = sky.uniforms.uAirMap.value.w;
    u.uCloudSun.value.set(flat > 1e-6 ? sx / flat : 1, flat > 1e-6 ? sz / flat : 0, mus, Math.sqrt(Math.max(1 - mus * mus, 0)));
    // every reading's place at the camera, worked out here in double precision
    this.decks.forEach((deck, i) => deck.reads.forEach((rd, k) => {
      const px = x - rd.drift[0] * t, pz = z - rd.drift[1] * t;
      u.uDeckR.value[i * 8 + k * 2].set(rd.u[0], rd.u[1], part(rd.u[0] * px + rd.u[1] * pz + rd.at[0]), rd.texels);
      u.uDeckR.value[i * 8 + k * 2 + 1].set(rd.v[0], rd.v[1], part(rd.v[0] * px + rd.v[1] * pz + rd.at[1]), 0);
      u.uDeckI.value[i * 4 + k].set(Math.floor(rd.u[0] * px + rd.u[1] * pz + rd.at[0]), Math.floor(rd.v[0] * px + rd.v[1] * pz + rd.at[1]), rd.salt, 0);
    }));
    // seen from high up the broad weather has more say (aloft())
    this.decks.forEach((deck, i) => { u.uDeckG.value[i].x = deck.fronts * aloft(deck, h); });
    this.height = h;
    this.decks.forEach((deck, i) => deck.broad.forEach((rd, k) => {
      const px = x - rd.drift[0] * t, pz = z - rd.drift[1] * t, qx = rd.u[0] * px + rd.u[1] * pz + rd.at[0] * 1000, qz = rd.v[0] * px + rd.v[1] * pz + rd.at[1] * 1000;
      u.uDeckO.value[i * FRONTS.sizes.length + k].set(part(qx), part(qz), Math.floor(qx), Math.floor(qz));
    }));
    for (const v of u.uDeckH.value) { v.x = x; v.y = z; }
    this.decks.forEach((deck, i) => { if (deck.stripes) u.uDeckStripe.value[i].set(0, -1 / deck.stripes.span, -z / deck.stripes.span, 1); });
    // a deck's second colour: north is towards -z, so the distance north of the origin is -z
    this.decks.forEach((deck, i) => { if (deck.beyond) u.uDeckEdge.value[i].set(0, -Math.sign(deck.beyond.at || 1), (Math.abs(deck.beyond.at) - Math.sign(deck.beyond.at || 1) * -z) / deck.beyond.width, 1 / deck.beyond.width); else u.uDeckEdge.value[i].set(0, 0, 1e9, 0); });
    // the light at each deck: the sun after the air at its height, the sky from above, and from below the sky's and the ground's
    const key = `${mus.toFixed(5)}`;
    if (key !== this._lights) {
      const ground = m.ground.map((g, k) => g * (sunlightAt(m, 0, mus)[k] * Math.max(mus, 0) + sky.ambient.at(mus)[k]));
      const light = (base, top, sunTo, skyTo, lowTo) => {
        const above = skyAmbient(m, top, mus, {steps: 8}), under = skyAmbient(m, base, mus, {steps: 8});
        sunTo.set(...sunlightAt(m, 0.5 * (base + top), mus)); skyTo.set(...above); lowTo.set(...under.map((s, k) => 0.55 * s + 0.6 * ground[k]));
      };
      this.decks.forEach((deck, i) => light(deck.base, deck.top, u.uDeckSun.value[i], u.uDeckSky.value[i], u.uDeckLow.value[i]));
      if (this.towers.length) light(this.towers[0].base, 0.75 * this.towers[0].top, u.uTowerSun.value, u.uTowerSky.value, u.uTowerLow.value);
      this._lights = key;
    }
    this.towers.forEach((tw, i) => { u.uTowerA.value[i].set(tw.x - x, tw.z - z, tw.radius, tw.anvil); u.uTowerB.value[i].set(tw.base, tw.top, tw.turn, this._tower.density); });
    const seen = this.flashes(t).slice(-MOST.flashes), gain = sky.state.gain;
    for (let k = 0; k < MOST.flashes; k++) {
      const fl = seen[k];
      // a flash's light: three times a noon sun's on white at its heart for power 1, lifted with the picture's exposure, but less (FLASH_LIFT)
      if (fl) { u.uFlashA.value[k].set(fl.place[0] - (fl.follows ? 0 : x), fl.place[1] - h, fl.place[2] - (fl.follows ? 0 : z), fl.level * 3 * Math.pow(gain, FLASH_LIFT)); u.uFlashB.value[k].set(...fl.color, fl.radius); }
      else { u.uFlashA.value[k].set(0, 0, 0, 0); u.uFlashB.value[k].set(0, 0, 0, 1); }
    }
    const before = r.getRenderTarget(), auto = r.autoClear, colour = r.getClearColor(new THREE.Color()), alpha = r.getClearAlpha();
    r.autoClear = true; r.setClearColor(0x000000, 0); r.setRenderTarget(this.target); r.render(this._scene, this._camera);
    r.setRenderTarget(before); r.autoClear = auto; r.setClearColor(colour, alpha);
    return this;
  }

  /** Free the clouds' picture, the tile and the materials; the air draws under the horizon again. */
  dispose() {
    if (this.options.floor !== null) this.sky.under(false);
    this.material.dispose(); this._pass.geometry.dispose();
  }
}
/** Clouds under an air: `clouds(renderer, sky, {sky: "fair", seed: 4})`, `clouds(renderer, sky, {decks: ["stratus"], towers: 4, lightning: {rate: 12}})`. */
export const clouds = (renderer, sky, options) => new Clouds(renderer, sky, options);
