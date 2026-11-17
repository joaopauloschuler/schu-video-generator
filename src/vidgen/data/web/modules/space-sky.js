// vidgen/space-sky: the sky of a space scene (DESIGN.md §122.6). Part of schu-video-generator (MIT
// licence); imported by a page as "vidgen/space-sky".
//
//   import {spaceSky} from "vidgen/space-sky";
//   const sky = spaceSky(renderer, {seed: 7});        // a sky from a seed (the default) ...
//   const sky = spaceSky(renderer, {stars: "real"});  // ... or the true bright stars, the band where it is
//   scene.add(sky.object);                            // all round the camera, drawn first, behind everything
//   camera.lookAt(sky.direction("center"));           // the galactic centre; also "pole", "nebula 1", "Vega"
//   scene.environment = sky.environment;              // reflections on metal (made on first use)
//
// What is drawn. Stars down to magnitude `limit` (8.5: about 69,000 over the whole sky) are separate
// points: each a small round spot with a steady footprint (a gaussian of sigma 0.75 px at 720p, never
// under 0.62 px, plus a halo that only the brightest show), so a star keeps its light while the camera
// turns and never flickers between pixels. Their numbers follow the real sky's counts (about three
// times as many per magnitude), their colours a star's temperature (B-V), kept pale as on a
// photograph. Everything fainter is baked once into a cube map with mipmaps: the Milky Way (a disc
// that brightens to a warm bulge, star clouds, a dust rift that reddens what it dims), a carpet of
// faint stars that thickens in the band, optional nebulae (emission, reflection, dark) and painted
// galaxies. Nothing changes after the bake: a frame costs one cube lookup per pixel and the star
// points. spiralGalaxy() is a separate thing: a galaxy of particles that stands in the scene.
//
// Frame. Directions are three.js world directions with the ecliptic's north at +y: the J2000 ecliptic
// frame of `ctx.orbits`, turned as vidgen/space-scale turns it (yUp). The real sky places its stars
// (right ascension, declination) and the galactic plane and centre in that frame, so the sky agrees
// with the planets. A seeded sky chooses its band's great circle from the seed (or `center` / `pole`).
//
// Light. Values are linear light meant for a tone-mapped picture (vidgen/three-finish: ACES): the
// faintest stars sit just above ACES's toe, the bulge near a fifth of white, stars brighter than
// magnitude 2.5 above white (they bloom a little). Drawn straight to the canvas (no render target) the
// sky applies the same curve and the sRGB encoding itself, and dithers, so both ways look alike.
// three-finish's FXAA turns small stars into crosses: give Finish `antialias: "none"` for a star field.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {yUp} from "vidgen/space-scale";
import CATALOG from "vidgen/space-sky-stars";

export const VERSION = 2;
const RAD = Math.PI / 180, TAU = Math.PI * 2;
/** The obliquity of the ecliptic at J2000.0 (degrees): equatorial to ecliptic is a turn about x by it. */
export const OBLIQUITY = 23.4392911;
/** The galactic frame in J2000 equatorial coordinates (degrees): the north pole and the centre. */
export const GALACTIC = Object.freeze({pole: Object.freeze([192.85948, 27.12825]), center: Object.freeze([266.40499, -28.93617])});
/** Stars of the whole sky brighter than a magnitude (the real sky's counts, rounded). */
export const STAR_COUNTS = Object.freeze([[-1.5, 0.5], [0, 4], [1, 15], [2, 48], [3, 171], [4, 513], [5, 1602], [6, 4800], [7, 14000], [8, 41000], [9, 117000], [10, 324000], [11, 870000]]);
export const STAR_MODES = Object.freeze(["seed", "real"]);
export const NEBULA_KINDS = Object.freeze(["emission", "reflection", "dark"]);
export const GALAXY_KINDS = Object.freeze(["spiral", "elliptical", "irregular"]);
/** Named looks: options a look sets when the page does not. */
export const LOOKS = Object.freeze({
  natural: Object.freeze({}),
  rich: Object.freeze({density: 1.5, milkyWay: 1.3, nebulae: 5, galaxies: 2}),
  sparse: Object.freeze({density: 0.3, milkyWay: 0.2, dust: 0.5, galaxies: 5}),
});
export const DEFAULTS = Object.freeze({seed: 1, stars: "seed", look: "natural", size: null, density: 1, brightness: 1, color: 1, limit: 8.5,
  starSize: 1, glare: 1, contrast: 0.8, milkyWay: 1, dust: 1, center: null, pole: null, nebulae: 0, galaxies: 0, display: "auto"});
const MAX_NEBULAE = 12, MAX_GALAXIES = 12, WHITE_MAGNITUDE = 2.5, KNEE_MAGNITUDE = 4.0, BRIGHT_CONTRAST = 0.85, SOFT_AMPLITUDE = 4.0;

// ---------- checks ----------
const fail = (message) => new Error(`vidgen/space-sky: ${message}`);
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
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x)) && Math.hypot(...v) > 0;

// ---------- directions (pure, tested in Node) ----------
const unit = (v) => { const r = Math.hypot(v[0], v[1], v[2]); return [v[0] / r, v[1] / r, v[2] / r]; };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
/** The unit vector of a right ascension and declination (degrees, J2000) in the J2000 ecliptic frame (z north). */
export function equatorialToEcliptic(raDeg, decDeg) {
  const ra = raDeg * RAD, dec = decDeg * RAD, e = OBLIQUITY * RAD;
  const x = Math.cos(dec) * Math.cos(ra), y = Math.cos(dec) * Math.sin(ra), z = Math.sin(dec);
  return [x, Math.cos(e) * y + Math.sin(e) * z, -Math.sin(e) * y + Math.cos(e) * z];
}
/** The three.js world direction (ecliptic north at +y) of a right ascension and declination (degrees, J2000). */
export const skyDirection = (raDeg, decDeg) => yUp(equatorialToEcliptic(raDeg, decDeg));
/** A galactic frame {center, side, pole} (unit world vectors, right-handed: side = pole x center, galactic
 * longitude 90 degrees) from a centre and a pole; the pole is made square to the centre. */
export function bandFrame(center, pole) {
  const c = unit(center), s = unit(cross(pole, c)), p = cross(c, s);
  return {center: c, side: s, pole: p};
}
/** The real galactic frame in three.js world directions. */
export const realBand = () => bandFrame(skyDirection(...GALACTIC.center), skyDirection(...GALACTIC.pole));
/** The world direction of galactic longitude l and latitude b (degrees) in a band frame. */
export function bandDirection(frame, l, b) {
  const cl = Math.cos(l * RAD), sl = Math.sin(l * RAD), cb = Math.cos(b * RAD), sb = Math.sin(b * RAD);
  return [0, 1, 2].map((i) => frame.center[i] * cb * cl + frame.side[i] * cb * sl + frame.pole[i] * sb);
}
/** A band frame from a seed: the pole anywhere, the centre anywhere on its great circle. */
export function seededBand(seed) {
  const r = rng(seed * 7919 + 17), z = r() * 2 - 1, a = r() * TAU, q = Math.sqrt(1 - z * z);
  const pole = [q * Math.cos(a), z, q * Math.sin(a)], any = Math.abs(pole[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  const u = unit(cross(pole, any)), v = cross(pole, u), t = r() * TAU;
  return bandFrame([0, 1, 2].map((i) => u[i] * Math.cos(t) + v[i] * Math.sin(t)), pole);
}

// ---------- stars (pure, tested in Node) ----------
/** How many stars of the whole sky are brighter than magnitude m (between the table's rows: a straight line in log N). */
export function starCount(m) {
  const T = STAR_COUNTS;
  if (m <= T[0][0]) return T[0][1] * Math.pow(10, 0.6 * (m - T[0][0]));
  for (let i = 1; i < T.length; i++) if (m <= T[i][0]) { const u = (m - T[i - 1][0]) / (T[i][0] - T[i - 1][0]); return Math.exp(Math.log(T[i - 1][1]) * (1 - u) + Math.log(T[i][1]) * u); }
  const last = T[T.length - 1]; return last[1] * Math.pow(10, 0.4 * (m - last[0]));
}
/** The magnitude of the n-th brightest star of the whole sky (the inverse of starCount). */
export function magnitudeOfRank(n) {
  let lo = -3, hi = 14;
  for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (starCount(mid) < n) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}
/** A star's temperature (K) from its colour index B-V (Ballesteros 2012). */
export const temperature = (bv) => 4600 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62));
/** The colour of a black body of temperature T (K) in linear sRGB, of luminance 1 (Kim et al.'s fit of
 * the Planckian locus, 1,667 K to 25,000 K; white near 6,500 K). */
export function blackbody(T) {
  const t = Math.min(25000, Math.max(1667, T));
  const x = t < 4000 ? -0.2661239e9 / t ** 3 - 0.2343589e6 / t ** 2 + 0.8776956e3 / t + 0.179910
    : -3.0258469e9 / t ** 3 + 2.1070379e6 / t ** 2 + 0.2226347e3 / t + 0.240390;
  const y = t < 2222 ? -1.1063814 * x ** 3 - 1.34811020 * x ** 2 + 2.18555832 * x - 0.20219683
    : t < 4000 ? -0.9549476 * x ** 3 - 1.37418593 * x ** 2 + 2.09137015 * x - 0.16748867
      : 3.0817580 * x ** 3 - 5.87338670 * x ** 2 + 3.75112997 * x - 0.37001483;
  const X = x / y, Z = (1 - x - y) / y;
  const c = [3.2406 * X - 1.5372 - 0.4986 * Z, -0.9689 * X + 1.8758 + 0.0415 * Z, 0.0557 * X - 0.2040 + 1.0570 * Z].map((v) => Math.max(0, v));
  const lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  return c.map((v) => v / lum);
}
/** A star's colour (linear sRGB, luminance 1) from B-V, `saturation` of the way from white to its black-body colour. */
export function starColor(bv, saturation = 0.5) {
  const c = blackbody(temperature(Math.min(2.2, Math.max(-0.4, bv))));
  return c.map((v) => 1 + (v - 1) * saturation);
}
/** The light of a star's middle pixel (linear; 1 = white) for a magnitude: magnitude 2.5 is white; down to
 * magnitude 4 each magnitude is 10^(-0.4 x 0.85) of the one before, fainter ones 10^(-0.4 contrast) (1 would
 * be the true ratio, 2.512): the faint end is lifted as a photograph's stretch lifts it. Above 4 the light
 * grows with the square root (Sirius about 7.7), so the brightest stars glare a little and do not flood. */
export function starAmplitude(magnitude, contrast = DEFAULTS.contrast) {
  const knee = Math.pow(10, -0.4 * BRIGHT_CONTRAST * (KNEE_MAGNITUDE - WHITE_MAGNITUDE));
  if (magnitude > KNEE_MAGNITUDE) return knee * Math.pow(10, -0.4 * contrast * (magnitude - KNEE_MAGNITUDE));
  const a = Math.pow(10, -0.4 * BRIGHT_CONTRAST * (magnitude - WHITE_MAGNITUDE));
  return a <= SOFT_AMPLITUDE ? a : SOFT_AMPLITUDE * Math.sqrt(a / SOFT_AMPLITUDE);
}
// how much of the Milky Way's disc lies in a direction (0 to 1): its stars gather there
function discShare(frame, d) {
  const gx = dot(d, frame.center), gy = dot(d, frame.side), gz = dot(d, frame.pole);
  const b = Math.asin(Math.max(-1, Math.min(1, gz))), u = 0.5 + 0.5 * gx / Math.max(1e-6, Math.hypot(gx, gy));
  const h = 0.11 + 0.08 * u * u * u, c = Math.cosh(b / h);
  return (0.35 + 0.65 * Math.pow(u, 1.5)) / (c * c);
}
// B-V of a seeded star: hot blue-white, white, yellow-white, orange giants, a few red ones
const BV_MIX = [[0.22, -0.12, 0.08], [0.47, 0.12, 0.12], [0.65, 0.48, 0.12], [0.92, 1.05, 0.15], [1.0, 1.55, 0.15]];
function seededBV(r) {
  const u = r(), g = Math.sqrt(-2 * Math.log(1 - r() * 0.999999)) * Math.cos(TAU * r());
  for (const [upTo, mean, spread] of BV_MIX) if (u <= upTo) return mean + spread * g;
  return 1.55;
}
function uniformDirection(r) { const z = r() * 2 - 1, a = r() * TAU, q = Math.sqrt(1 - z * z); return [q * Math.cos(a), z, q * Math.sin(a)]; }
/** The stars of a seeded sky as arrays {count, dir (xyz per star, world), mag, bv}: ranks spread evenly
 * over the real counts from magnitude `from` to `limit` (so every seed has its Sirius and its thousands
 * of faint stars), gathered toward the band `frame` the more the fainter (`gather` 0: evenly), plus a
 * few open clusters near the band. */
export function seededStars(seed, {limit = DEFAULTS.limit, density = 1, from = -Infinity, frame = null, gather = 1, clusters = true} = {}) {
  const r = rng(seed * 104729 + 3), first = Number.isFinite(from) ? starCount(from) * density : 0, total = starCount(limit) * density;
  const n = Math.max(0, Math.round(total - first)), dir = [], mag = [], bv = [];
  for (let i = 0; i < n; i++) {
    const m = magnitudeOfRank((first + i + r()) / density), k = frame ? gather * Math.min(6, Math.max(0, 0.8 * (m - 1))) : 0;
    let d = uniformDirection(r);
    if (k > 0) for (let tries = 0; tries < 12 && r() * (1 + k) > 1 + k * discShare(frame, d); tries++) d = uniformDirection(r);
    dir.push(d[0], d[1], d[2]); mag.push(m); bv.push(seededBV(r));
  }
  if (clusters && frame && limit > 5) {
    const groups = 4 + Math.floor(r() * 4);
    for (let g = 0; g < groups; g++) {
      const c = bandDirection(frame, r() * 360, (r() + r() - 1) * 14), radius = (0.35 + 1.3 * r() * r()) * RAD, members = 10 + Math.floor(r() * 45 * density);
      const any = Math.abs(c[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0], u = unit(cross(c, any)), v = cross(c, u), bright = 3.2 + 2.5 * r();
      for (let i = 0; i < members; i++) {
        const rr = radius * Math.sqrt(-Math.log(1 - r() * 0.98)) * 0.6, a = r() * TAU;
        const d = unit([0, 1, 2].map((j) => c[j] + (u[j] * Math.cos(a) + v[j] * Math.sin(a)) * rr));
        const m = Math.min(limit, bright + 5.5 * Math.pow(r(), 0.55));
        if (m <= from) continue;
        dir.push(d[0], d[1], d[2]); mag.push(m); bv.push(r() < 0.88 ? -0.12 + 0.1 * (r() + r() - 1) : 1.2 + 0.3 * r());
      }
    }
  }
  return {count: mag.length, dir: Float32Array.from(dir), mag: Float32Array.from(mag), bv: Float32Array.from(bv), names: new Map()};
}
/** The stars of a star file (the default: the shipped one) as arrays {count, dir, mag, bv, names}: true
 * positions in the world frame; `names` maps a lower-case name to its star's index. */
export function catalogStars(catalog = CATALOG) {
  const rows = catalog.stars, dir = new Float32Array(rows.length * 3), mag = new Float32Array(rows.length), bv = new Float32Array(rows.length), names = new Map();
  rows.forEach((s, i) => {
    dir.set(skyDirection(s[0], s[1]), i * 3); mag[i] = s[2]; bv[i] = s[3];
    if (s[4]) names.set(String(s[4]).toLowerCase(), i);
  });
  return {count: rows.length, dir, mag, bv, names};
}
function joinStars(a, b) {
  const dir = new Float32Array((a.count + b.count) * 3), mag = new Float32Array(a.count + b.count), bv = new Float32Array(a.count + b.count);
  dir.set(a.dir); dir.set(b.dir, a.count * 3); mag.set(a.mag); mag.set(b.mag, a.count); bv.set(a.bv); bv.set(b.bv, a.count);
  return {count: a.count + b.count, dir, mag, bv, names: a.names};
}

// ---------- options ----------
const NEBULA_KEYS = ["kind", "at", "size", "strength", "seed", "color", "angle", "stretch"];
const GALAXY_KEYS = ["kind", "at", "size", "tilt", "angle", "strength", "seed", "arms"];
function directionOf(where, at, frame) {
  if (isVec(at)) return unit(at);
  if (at && typeof at === "object" && !Array.isArray(at)) { known(where, at, ["l", "b"]); return bandDirection(frame, number(`${where}.l`, at.l ?? 0, -360, 360), number(`${where}.b`, at.b ?? 0, -90, 90)); }
  throw fail(`${where} must be a direction [x, y, z] or {l, b} (degrees along and above the band, 0 at its centre), got ${JSON.stringify(at)}`);
}
const hexColor = (where, v) => { try { const c = new THREE.Color(v); if ([c.r, c.g, c.b].every(Number.isFinite)) return [c.r, c.g, c.b]; } catch (e) { /* reported below */ } throw fail(`${where} must be a colour (0xrrggbb or "#rrggbb"), got ${JSON.stringify(v)}`); };
function resolveNebulae(list, frame, seed) {
  const r = rng(seed * 31 + 5);
  if (typeof list === "number") {
    const n = number("nebulae", list, 0, MAX_NEBULAE);
    if (!Number.isInteger(n)) throw fail(`nebulae must be a whole number or a list, got ${n}`);
    // seeded: mostly red emission clouds on the band, now and then a blue or a dark one
    list = Array.from({length: n}, (_, i) => {
      const u = r(), kind = u < 0.62 ? "emission" : u < 0.84 ? "reflection" : "dark";
      return {kind, at: {l: (i === 0 ? 18 + 30 * r() : r() * 360) * (r() < 0.5 ? -1 : 1), b: (r() + r() - 1) * (kind === "emission" ? 7 : 14)}, size: kind === "dark" ? 5 + 6 * r() : 2 + 7 * r() * r(), strength: kind === "dark" ? 0.45 : 1};
    });
  }
  if (!Array.isArray(list) || list.length > MAX_NEBULAE) throw fail(`nebulae must be a number or a list of at most ${MAX_NEBULAE}, got ${JSON.stringify(list)}`);
  return list.map((raw, i) => {
    const where = `nebulae[${i}]`; known(where, raw, NEBULA_KEYS);
    const kind = choice(`${where}.kind`, raw.kind ?? "emission", NEBULA_KINDS);
    return {kind, direction: directionOf(`${where}.at`, raw.at ?? {l: 0, b: 0}, frame), size: number(`${where}.size`, raw.size ?? 6, 0.2, 90),
      strength: number(`${where}.strength`, raw.strength ?? 1, 0, 20), seed: number(`${where}.seed`, raw.seed ?? Math.floor(r() * 1000), 0, 1e6),
      color: raw.color === undefined || raw.color === null ? null : hexColor(`${where}.color`, raw.color),
      angle: number(`${where}.angle`, raw.angle ?? r() * 180, -360, 360), stretch: number(`${where}.stretch`, raw.stretch ?? 1 + 0.6 * r(), 0.2, 5)};
  });
}
function resolveGalaxies(list, frame, seed) {
  const r = rng(seed * 53 + 9);
  if (typeof list === "number") {
    const n = number("galaxies", list, 0, MAX_GALAXIES);
    if (!Number.isInteger(n)) throw fail(`galaxies must be a whole number or a list, got ${n}`);
    // seeded: away from the band, most of them small
    list = Array.from({length: n}, (_, i) => ({kind: r() < 0.7 ? "spiral" : "elliptical", at: {l: r() * 360, b: (28 + 55 * r()) * (r() < 0.5 ? -1 : 1)}, size: i === 0 ? 2.2 + 1.5 * r() : 0.5 + 1.6 * r() * r()}));
  }
  if (!Array.isArray(list) || list.length > MAX_GALAXIES) throw fail(`galaxies must be a number or a list of at most ${MAX_GALAXIES}, got ${JSON.stringify(list)}`);
  return list.map((raw, i) => {
    const where = `galaxies[${i}]`; known(where, raw, GALAXY_KEYS);
    const kind = choice(`${where}.kind`, raw.kind ?? "spiral", GALAXY_KINDS);
    return {kind, direction: directionOf(`${where}.at`, raw.at ?? {l: 90, b: 60}, frame), size: number(`${where}.size`, raw.size ?? 3, 0.1, 60),
      tilt: number(`${where}.tilt`, raw.tilt ?? 25 + 55 * r(), 0, 90), angle: number(`${where}.angle`, raw.angle ?? r() * 180, -360, 360),
      strength: number(`${where}.strength`, raw.strength ?? 1, 0, 20), seed: number(`${where}.seed`, raw.seed ?? Math.floor(r() * 1000), 0, 1e6),
      arms: number(`${where}.arms`, raw.arms ?? (r() < 0.75 ? 2 : 3), 1, 6)};
  });
}
// the real sky's own galaxies: the two Magellanic Clouds and the Andromeda galaxy (J2000, sizes in degrees)
const REAL_GALAXIES = [
  {kind: "irregular", at: [80.9, -69.75], size: 5.0, tilt: 35, angle: 20, strength: 1.5, seed: 11, arms: 1},
  {kind: "irregular", at: [13.2, -72.8], size: 2.4, tilt: 50, angle: 60, strength: 1.2, seed: 12, arms: 1},
  {kind: "spiral", at: [10.68, 41.27], size: 1.7, tilt: 77, angle: 0, strength: 1.3, seed: 13, arms: 2},
];
/** The options of spaceSky with a look's and the defaults filled in and checked; `band` is the galactic
 * frame, `nebulae` and `galaxies` are lists with a `direction` each. */
export function resolveOptions(options = {}) {
  known("spaceSky options", options, Object.keys(DEFAULTS));
  const look = choice("look", options.look ?? DEFAULTS.look, Object.keys(LOOKS));
  const o = {...DEFAULTS, ...LOOKS[look], ...options, look};
  if (!Number.isInteger(o.seed) || o.seed < 0) throw fail(`seed must be a whole number from 0, got ${JSON.stringify(o.seed)}`);
  choice("stars", o.stars, STAR_MODES);
  if (o.size !== null && (!Number.isInteger(o.size) || o.size < 64 || o.size > 4096)) throw fail(`size (the cube map's faces in pixels) must be a whole number from 64 to 4096, got ${JSON.stringify(o.size)}`);
  number("density", o.density, 0, 4); number("brightness", o.brightness, 0, 16); number("color", o.color, 0, 2); number("limit", o.limit, 0, 9.5);
  number("starSize", o.starSize, 0.5, 4); number("glare", o.glare, 0, 8); number("contrast", o.contrast, 0.3, 1);
  if (o.milkyWay === true) o.milkyWay = 1; if (o.milkyWay === false) o.milkyWay = 0;
  number("milkyWay", o.milkyWay, 0, 4); number("dust", o.dust, 0, 4);
  if (o.display !== "auto" && typeof o.display !== "boolean") throw fail(`display must be "auto", true or false, got ${JSON.stringify(o.display)}`);
  for (const k of ["center", "pole"]) if (o[k] !== null && !isVec(o[k])) throw fail(`${k} must be a direction [x, y, z], got ${JSON.stringify(o[k])}`);
  const real = o.stars === "real";
  if (real && (o.center || o.pole)) throw fail(`center and pole belong to a seeded sky: the real sky's band is where it is`);
  let band = real ? realBand() : seededBand(o.seed);
  if (o.center || o.pole) {
    const center = o.center ?? band.center, pole = o.pole ?? band.pole;
    if (Math.hypot(...cross(unit(center), unit(pole))) < 1e-3) throw fail(`center and pole point the same way: ${JSON.stringify(center)}, ${JSON.stringify(pole)}`);
    // a given centre is kept exactly and the pole made square to it; a given pole alone keeps the pole
    band = o.center ? bandFrame(center, pole) : (() => { const p = unit(pole), s = unit(cross(p, center)), c = cross(s, p); return {center: c, side: s, pole: p}; })();
  }
  o.band = band;
  o.nebulae = resolveNebulae(o.nebulae, band, o.seed);
  o.galaxies = resolveGalaxies(o.galaxies, band, o.seed);
  if (real) o.galaxies = [...REAL_GALAXIES.map((g) => ({...g, direction: skyDirection(...g.at)})), ...o.galaxies].slice(0, MAX_GALAXIES);
  return o;
}

// ---------- the bake: the Milky Way, faint stars, nebulae and painted galaxies into a cube map ----------
const NOISE = /* glsl */`
float hash13(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }
float vnoise(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash13(i), hash13(i + vec3(1, 0, 0)), f.x), mix(hash13(i + vec3(0, 1, 0)), hash13(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash13(i + vec3(0, 0, 1)), hash13(i + vec3(1, 0, 1)), f.x), mix(hash13(i + vec3(0, 1, 1)), hash13(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
const mat3 TURN = mat3(0.00, 0.80, 0.60, -0.80, 0.36, -0.48, -0.60, -0.48, 0.64);
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 5; i++) { s += a * vnoise(p); p = TURN * p * 2.03 + 11.7; a *= 0.5; } return s / 0.96875; }
float fbm3(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 3; i++) { s += a * vnoise(p); p = TURN * p * 2.03 + 11.7; a *= 0.5; } return s / 0.875; }
float sfbm(vec3 p) { return smoothstep(0.28, 0.72, fbm(p)); }
float ridge(vec3 p) { float v = 1.0 - abs(2.0 * fbm(p) - 1.0); return v * v; }
`;
const BAKE_VERT = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";
// a texel's direction on the face being drawn (as OpenGL addresses a cube map), noise, colour and local coordinates
const BAKE_HEAD = /* glsl */`
uniform vec3 uRight, uUp, uFwd;
uniform float uSize, uSat;
${NOISE}
vec3 faceDirection() { vec2 uv = gl_FragCoord.xy / uSize * 2.0 - 1.0; return normalize(uFwd + uv.x * uRight + uv.y * uUp); }
vec3 tint(vec3 c, float s) { float l = dot(c, vec3(0.2126, 0.7152, 0.0722)); return max(vec3(0.0), mix(vec3(l), c, s)); }
// coordinates on the sky around a direction n: x, y in units of size, turned by angle
vec2 around(vec3 d, vec3 n, float size, float angle) {
  vec3 ex = normalize(cross(abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0), n)), ey = cross(n, ex);
  vec2 p = vec2(dot(d, ex), dot(d, ey)) / size;
  float c = cos(angle), s = sin(angle);
  return vec2(c * p.x + s * p.y, -s * p.x + c * p.y);
}

`;
// the first pass, every texel: the band and the faint stars
const BAND_FRAG = /* glsl */`
uniform vec3 uGx, uGy, uGz, uOff;
uniform float uMW, uDust, uCarpet;
${BAKE_HEAD}
// the band: light of the disc and the bulge after the dust; dens: how thick the faint stars lie
vec3 milkyWay(vec3 d, out float dens) {
  vec3 g = vec3(dot(d, uGx), dot(d, uGy), dot(d, uGz));
  float b = asin(clamp(g.z, -1.0, 1.0)), l = atan(g.y, g.x);
  float u = 0.5 + 0.5 * g.x / max(length(g.xy), 1e-4);
  vec3 q = vec3(g.xy, g.z * 2.4);
  vec3 w = q + 0.30 * (vec3(fbm3(q * 1.9 + uOff), fbm3(q * 1.9 + uOff + 19.0), fbm3(q * 1.9 + uOff + 41.0)) - 0.5);
  float mid = 0.22 * (fbm3(vec3(g.xy * 1.4, 0.0) + uOff + 7.0) - 0.5);
  float bb = b - mid, h = mix(0.062, 0.115, u * u * u);
  float ch = cosh(min(abs(bb) / h, 20.0)), disk = 1.0 / (ch * ch);
  float amp = mix(0.30, 1.0, pow(u, 2.0));
  float big = sfbm(w * 3.1 + uOff * 1.3), fine = sfbm(w * 8.7 + uOff * 2.1 + 3.0);
  float clouds = (0.42 + 1.16 * big) * (0.62 + 0.76 * fine);
  float halo = 0.08 * exp(-abs(bb) / 0.26) * (0.35 + 0.65 * u);
  float bulge = 1.2 * exp(-(l * l / 0.045 + bb * bb / 0.020)) + 0.5 * exp(-(l * l / 0.22 + bb * bb / 0.045));
  // dust: a rift that wanders along the middle of the band, widest toward the centre; threads that
  // leave it. A continuous field: its edges come from the light it swallows, not from a threshold
  float riftMid = bb - 0.010 - 0.26 * (fbm3(vec3(g.xy * 2.6, 1.0) + uOff + 13.0) - 0.5);
  float narrow = 0.014 + 0.022 * u, wide = 0.055 + 0.04 * u;
  float rift = exp(-riftMid * riftMid / (narrow * narrow)), reach = exp(-riftMid * riftMid / (wide * wide));
  float n = fbm(w * 4.6 + uOff * 3.0 + 31.0) * 0.64 + fbm(w * 14.0 + uOff + 5.0) * 0.24 + fbm3(w * 37.0 + uOff + 9.0) * 0.12;
  float inner = 0.42 + 0.58 * smoothstep(-0.3, 0.9, g.x);
  float t = clamp((n - 0.46 + 0.10 * inner) / 0.30, 0.0, 1.0), threads = ridge(w * 7.5 + uOff + 57.0);
  float tau = (3.8 * rift * t * (0.35 + 0.65 * t) + 5.0 * reach * t * threads * threads) * inner * uDust;
  vec3 ext = exp(-tau * vec3(0.78, 1.0, 1.34));
  float light = disk * amp * clouds + halo;
  // the grain of stars too faint to stand alone
  float grain = 0.84 + 0.32 * vnoise(d * uSize / 5.0 + uOff);
  vec3 c = (vec3(0.74, 0.85, 1.0) * light * 0.115 + vec3(1.0, 0.80, 0.54) * bulge * 0.19) * ext * grain;
  dens = (light + 1.6 * bulge) * ext.g;
  return tint(c, uSat) * uMW;
}

// faint stars: one to a cell of three grids, each a spot about a texel and a half wide
vec3 carpet(vec3 d, float dens) {
  float sig = 1.5 / uSize, cell = uSize / 11.0;
  vec3 acc = vec3(0.0);
  for (int k = 0; k < 3; k++) {
    float S = cell * (1.0 + 0.37 * float(k));
    vec3 q = d * S + 13.7 * float(k) + uOff, c = floor(q);
    float h = hash13(c + 1.7);
    if (h > dens) continue;
    vec3 o = 0.22 + 0.56 * vec3(hash13(c + 3.1), hash13(c + 7.7), hash13(c + 13.3));
    float r = length(q - c - o) / S, m = sqrt(hash13(c + 21.0));
    float amp = 0.045 * pow(0.14, m);
    vec3 col = mix(vec3(1.0, 0.86, 0.70), vec3(0.80, 0.88, 1.0), hash13(c + 29.0));
    acc += tint(col, uSat) * amp * exp(-r * r / (2.0 * sig * sig));
  }
  return acc * uCarpet;
}

void main() {
  vec3 d = faceDirection();
  float dens = 0.0;
  vec3 col = uMW > 0.0 ? milkyWay(d, dens) : vec3(0.0);
  dens = clamp(0.035 + 0.75 * dens * min(uMW, 1.5), 0.0, 0.95);
  gl_FragColor = vec4(col + carpet(d, dens), 1.0);
}`;
// a nebula, drawn only over the texels it covers: light to add, or (dark) the share of the light behind it to keep
const NEBULA_FRAG = /* glsl */`
uniform vec4 uA, uB, uC;
${BAKE_HEAD}
// A: direction, size (radians). B: kind (0 emission, 1 reflection, 2 dark), strength, seed, angle. C: colour (r < 0: the kind's own), stretch
void nebula(vec4 A, vec4 B, vec4 C, vec3 d, inout vec3 col) {
  if (dot(d, A.xyz) < cos(min(A.w * 1.8, 3.1))) return;
  vec2 p = around(d, A.xyz, A.w, B.w); p.x /= C.w;
  vec3 q = vec3(p, 0.0) + B.z * vec3(0.37, 0.71, 1.13) + (d - A.xyz) * 0.3 / A.w;
  vec3 w = q + 0.55 * (vec3(fbm3(q * 1.3), fbm3(q * 1.3 + 11.0), fbm3(q * 1.3 + 23.0)) - 0.5);
  float shape = smoothstep(1.1, 0.05, length(p) + 0.95 * (fbm(w * 1.5 + 2.0) - 0.5));
  float body = shape * smoothstep(0.30, 0.72, fbm(w * 2.6 + 5.0) * (0.5 + 0.95 * shape));
  float fil = ridge(w * 4.6 + 9.0);
  if (B.x > 1.5) {   // dark: it dims what lies behind and reddens it a little
    col *= exp(-3.0 * B.y * body * (0.6 + 0.6 * fil) * vec3(0.85, 1.0, 1.25));
  } else if (B.x > 0.5) {   // reflection: smooth blue dust lit by a star
    vec3 blue = C.x < 0.0 ? vec3(0.30, 0.47, 1.0) : C.rgb;
    col += tint(blue, uSat) * 0.085 * B.y * shape * shape * (0.35 + 0.9 * fbm(w * 2.1 + 15.0)) * (0.7 + 0.5 * fil);
  } else {   // emission: deep red hydrogen in wisps, pink where it is dense, a pale core, dark lanes across it
    float wide = smoothstep(1.7, 0.2, length(p) + 1.1 * (fbm(w * 1.1 + 2.0) - 0.5));
    float fine = fbm(w * 9.0 + 3.0), lanes = 1.0 - 0.9 * smoothstep(0.50, 0.64, fbm(w * 3.6 + 33.0));
    float glow = body * (0.18 + 2.3 * fil * fine) * lanes;
    float wisps = wide * wide * ridge(w * 2.3 + 21.0) * (0.3 + 1.4 * fine);
    vec3 red = C.x < 0.0 ? vec3(0.80, 0.07, 0.11) : C.rgb, pink = C.x < 0.0 ? vec3(1.0, 0.24, 0.32) : mix(C.rgb, vec3(1.0), 0.3);
    vec3 e = red * 0.035 * wisps + mix(red, pink, smoothstep(0.1, 0.8, glow)) * 0.15 * glow;
    e += vec3(1.0, 0.70, 0.76) * 0.12 * pow(body, 3.0) * glow;
    e += vec3(0.28, 0.45, 1.0) * 0.016 * shape * smoothstep(0.45, 0.75, fbm(w * 1.9 + 41.0));
    col += tint(e, uSat) * B.y;
  }
}
void main() {
  vec3 col = vec3(uB.x > 1.5 ? 1.0 : 0.0);
  nebula(uA, uB, uC, faceDirection(), col);
  gl_FragColor = vec4(col, 1.0);
}`;
// a painted galaxy, drawn only over the texels it covers: light to add
const GALAXY_FRAG = /* glsl */`
uniform vec4 uA, uB, uC;
${BAKE_HEAD}
// A: direction, size (radians). B: axis ratio, angle, seed, arms. C: kind (0 spiral, 1 elliptical, 2 irregular), strength
void galaxy(vec4 A, vec4 B, vec4 C, vec3 d, inout vec3 col) {
  if (dot(d, A.xyz) < cos(min(A.w * 1.5, 3.1))) return;
  vec2 p = around(d, A.xyz, A.w, B.y);
  vec3 warm = vec3(1.0, 0.82, 0.60), blue = vec3(0.70, 0.82, 1.0);
  if (C.x > 1.5) {   // irregular: a bar in a patchy cloud of young stars, a few pink knots
    vec2 f = vec2(p.x, p.y / max(B.x, 0.3));
    float r = length(f), n = fbm(vec3(f * 3.0, B.z)), m = fbm(vec3(f * 9.0, B.z + 5.0));
    float cloud = smoothstep(1.0, 0.0, r + 0.7 * (n - 0.5)), bar = exp(-(f.x * f.x / 0.10 + f.y * f.y / 0.012));
    float I = cloud * cloud * (0.35 + 1.1 * m) * 0.55 + bar * 0.8;
    vec3 c = mix(blue, warm, 0.35 + 0.4 * bar) * I + vec3(1.0, 0.35, 0.45) * 0.5 * cloud * smoothstep(0.66, 0.80, fbm(vec3(f * 15.0, B.z + 9.0)));
    col += tint(c, uSat) * 0.07 * C.y;
    return;
  }
  if (C.x > 0.5) {   // elliptical: a smooth warm glow, steep in the middle
    float r = length(vec2(p.x, p.y / max(B.x, 0.45)));
    col += tint(warm, uSat) * 0.5 * C.y * exp(-7.0 * pow(r, 0.42)) * smoothstep(1.2, 0.5, r);
    return;
  }
  vec2 f = vec2(p.x, p.y / max(B.x, 0.10));
  float r = length(f), th = atan(f.y, f.x);
  float n = fbm(vec3(f * 5.0, B.z)), fine = fbm(vec3(f * 16.0, B.z + 3.0));
  float ph = th * B.w - log(max(r, 0.03)) * B.w * 3.1 + B.z * 1.7 + 2.2 * (n - 0.5);
  float arm = pow(0.5 + 0.5 * cos(ph), 1.7), lane = pow(0.5 + 0.5 * cos(ph + 0.95), 5.0);
  float inDisc = smoothstep(0.05, 0.22, r), edge = smoothstep(1.1, 0.55, r);
  float rb = length(vec2(p.x, p.y / max(B.x, 0.62)));
  float bulge = 1.5 * exp(-rb / 0.055) + 0.5 * exp(-rb * rb / 0.004);
  float disc = exp(-r / 0.30) * edge * (0.30 + 1.0 * arm * inDisc) * (0.55 + 0.9 * fine);
  float tau = 1.6 * lane * inDisc * exp(-r / 0.45) * (0.4 + 1.2 * n);
  vec3 c = warm * bulge + mix(warm, blue, inDisc * (0.35 + 0.65 * arm)) * disc * 1.15;
  c += vec3(1.0, 0.34, 0.46) * 0.9 * disc * arm * smoothstep(0.62, 0.80, fbm(vec3(f * 24.0, B.z + 7.0)));
  c *= exp(-tau * vec3(0.8, 1.0, 1.3));
  col += tint(c, uSat) * 0.14 * C.y / sqrt(max(B.x, 0.25));
}
void main() {
  vec3 col = vec3(0.0);
  galaxy(uA, uB, uC, faceDirection(), col);
  gl_FragColor = vec4(col, 1.0);
}`;
// the six faces as OpenGL addresses them: direction = forward + s right + t up, s and t from -1 to 1 across the face
const FACES = [
  [[1, 0, 0], [0, 0, -1], [0, -1, 0]], [[-1, 0, 0], [0, 0, 1], [0, -1, 0]], [[0, 1, 0], [1, 0, 0], [0, 0, 1]],
  [[0, -1, 0], [1, 0, 0], [0, 0, -1]], [[0, 0, 1], [1, 0, 0], [0, -1, 0]], [[0, 0, -1], [-1, 0, 0], [0, -1, 0]],
];
const KIND_INDEX = {emission: 0, reflection: 1, dark: 2, spiral: 0, elliptical: 1, irregular: 2};
/** The part of cube face `face` (0 to 5) that a cap of `radius` (radians) around `direction` can touch, as
 * [s0, t0, s1, t1] in the face's -1..1 coordinates; null when it touches none of it. */
export function faceWindow(face, direction, radius) {
  const [fwd, right, up] = FACES[face], n = unit(direction);
  if (Math.acos(Math.max(-1, Math.min(1, dot(n, fwd)))) - radius > 0.9554) return null;   // past the face's corners (54.74 degrees)
  if (radius > 1.0) return [-1, -1, 1, 1];
  const any = Math.abs(n[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0], u = unit(cross(n, any)), v = cross(n, u);
  let s0 = Infinity, t0 = Infinity, s1 = -Infinity, t1 = -Infinity;
  for (let i = 0; i <= 48; i++) {
    const a = i * TAU / 48, k = i === 48 ? 0 : Math.sin(radius), c = i === 48 ? 1 : Math.cos(radius);
    const q = [0, 1, 2].map((j) => n[j] * c + (u[j] * Math.cos(a) + v[j] * Math.sin(a)) * k), w = dot(q, fwd);
    if (w < 0.08) return [-1, -1, 1, 1];   // the cap reaches the face's horizon: no bound
    const s = dot(q, right) / w, t = dot(q, up) / w;
    s0 = Math.min(s0, s); s1 = Math.max(s1, s); t0 = Math.min(t0, t); t1 = Math.max(t1, t);
  }
  if (s1 < -1 || s0 > 1 || t1 < -1 || t0 > 1) return null;
  return [Math.max(-1, s0), Math.max(-1, t0), Math.min(1, s1), Math.min(1, t1)];
}
function bakeSky(renderer, o, size) {
  const rt = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearMipmapLinearFilter, generateMipmaps: false, depthBuffer: false});
  const r = rng(o.seed * 613 + 1), v3 = (a) => new THREE.Vector3(...a);
  const face = {uRight: {value: new THREE.Vector3()}, uUp: {value: new THREE.Vector3()}, uFwd: {value: new THREE.Vector3()}, uSize: {value: size}, uSat: {value: o.color}};
  const pass = (fragmentShader, uniforms, blend = null) => new THREE.ShaderMaterial({uniforms: {...face, ...uniforms}, vertexShader: BAKE_VERT, fragmentShader, depthTest: false, depthWrite: false,
    ...(blend ? {blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: blend[0], blendDst: blend[1], blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor, transparent: true} : {})});
  const add = [THREE.OneFactor, THREE.OneFactor], dim = [THREE.ZeroFactor, THREE.SrcColorFactor];
  const band = pass(BAND_FRAG, {uGx: {value: v3(o.band.center)}, uGy: {value: v3(o.band.side)}, uGz: {value: v3(o.band.pole)}, uOff: {value: new THREE.Vector3(r() * 50, r() * 50, r() * 50)},
    uMW: {value: o.milkyWay}, uDust: {value: o.dust}, uCarpet: {value: o.limit >= 6 ? Math.min(1.5, o.density) : 0}});
  // the things with a place: galaxies (light), then the nebulae in their order (a dark one dims what is drawn before it)
  const things = [
    ...o.galaxies.map((g) => ({reach: Math.min(g.size * RAD * 1.5, 3.1), direction: g.direction, material: pass(GALAXY_FRAG, {uA: {value: new THREE.Vector4(...g.direction, g.size * RAD)},
      uB: {value: new THREE.Vector4(Math.cos(g.tilt * RAD), g.angle * RAD, g.seed % 997, Math.round(g.arms))}, uC: {value: new THREE.Vector4(KIND_INDEX[g.kind], g.strength, 0, 0)}}, add)})),
    ...o.nebulae.map((n) => ({reach: Math.min(n.size * RAD * 1.8, 3.1), direction: n.direction, material: pass(NEBULA_FRAG, {uA: {value: new THREE.Vector4(...n.direction, n.size * RAD)},
      uB: {value: new THREE.Vector4(KIND_INDEX[n.kind], n.strength, n.seed % 997, n.angle * RAD)}, uC: {value: new THREE.Vector4(...(n.color ?? [-1, 0, 0]), n.stretch)}}, n.kind === "dark" ? dim : add)})),
  ];
  const geometry = new THREE.PlaneGeometry(2, 2), quad = new THREE.Mesh(geometry, band), scene = new THREE.Scene(), camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  quad.frustumCulled = false; scene.add(quad);
  const target = renderer.getRenderTarget(), active = renderer.getActiveCubeFace(), level = renderer.getActiveMipmapLevel(), xr = renderer.xr.enabled, autoClear = renderer.autoClear;
  renderer.xr.enabled = false;
  for (let i = 0; i < 6; i++) {
    const [fwd, right, up] = FACES[i];
    face.uFwd.value.set(...fwd); face.uRight.value.set(...right); face.uUp.value.set(...up);
    quad.material = band; rt.scissorTest = false; renderer.autoClear = true;
    renderer.setRenderTarget(rt, i); renderer.render(scene, camera);
    renderer.autoClear = false;
    for (const thing of things) {
      const w = faceWindow(i, thing.direction, thing.reach);
      if (!w) continue;
      const x0 = Math.floor((w[0] + 1) / 2 * size), y0 = Math.floor((w[1] + 1) / 2 * size), x1 = Math.ceil((w[2] + 1) / 2 * size), y1 = Math.ceil((w[3] + 1) / 2 * size);
      rt.scissorTest = true; rt.scissor.set(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
      quad.material = thing.material;
      renderer.setRenderTarget(rt, i); renderer.render(scene, camera);
    }
  }
  // the mipmaps once, after the last face
  rt.scissorTest = false; rt.texture.generateMipmaps = true;
  renderer.setRenderTarget(rt, 5); renderer.render(new THREE.Scene(), camera);
  renderer.setRenderTarget(target, active, level);
  renderer.xr.enabled = xr; renderer.autoClear = autoClear;
  band.dispose(); geometry.dispose(); for (const thing of things) thing.material.dispose();
  return rt;
}

// ---------- drawing: the cube all round the camera, then the stars ----------
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
// to the canvas: the curve and encoding vidgen/three-finish would apply (ACES, sRGB) and half a code of dither
const DISPLAY = /* glsl */`
${TONE}
uniform float uDisplay;
float dither(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 display(vec3 c) {
  if (uDisplay < 0.5) return c;
  c = clamp(ACESFilmicToneMapping(max(c, 0.0)), 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}`;
const SKY_VERT = "varying vec3 vD; void main() { vD = position; gl_Position = projectionMatrix * vec4(mat3(viewMatrix) * (mat3(modelMatrix) * position), 1.0); gl_Position.z = 0.0; }";
/** Pixels a cube texel may span before the sky's cube is read coarser (long lenses), and how fast it coarsens. */
export const LENS_PIXELS = 2.5, LENS_SOFT = 1.5;
const SKY_FRAG = /* glsl */`
#define LENS_PIXELS ${LENS_PIXELS.toFixed(2)}
#define LENS_SOFT ${LENS_SOFT.toFixed(2)}
varying vec3 vD; uniform samplerCube uSky; uniform float uGain, uSize;
${DISPLAY}
void main() {
  // a long lens enlarges the cube's texels: past LENS_PIXELS pixels a texel its faint stars would be soft
  // blobs and the band's clouds streaks, so the cube is read coarser there (its local mean, the same light):
  // through a long lens the sky is the sharp point stars over a smooth glow
  float pixel = length(fwidth(normalize(vD))) * 0.7071, texels = 1.5708 / uSize / max(pixel, 1e-7);
  vec3 c = textureLod(uSky, vD, max(0.0, LENS_SOFT * log2(texels / LENS_PIXELS))).rgb * uGain;
  float n = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  // linear light: about one display code of noise where the picture is dark; to the canvas: one code exactly
  gl_FragColor = vec4(uDisplay < 0.5 ? max(c + n * 0.0009 * smoothstep(0.0, 0.004, c.g), 0.0) : display(c) + n / 255.0, 1.0);
}`;
// a star is a GL point (cheap: tens of thousands a frame); the few bright ones, whose halo is wider than
// a point may be, are quads (QUAD defined)
const STAR_VERT = /* glsl */`
attribute vec3 aDir; attribute vec4 aStar;
uniform vec2 uPixel; uniform float uSigma, uGlare, uGain, uThin, uSkyGain, uDisplay; uniform samplerCube uSky;
varying vec2 vP; varying vec4 vStar; varying float vHalf; varying vec3 vUnder;
void main() {
  // to the canvas the star is the step from the sky under it to the sky plus the star, after the curve
  vUnder = uDisplay > 0.5 ? textureLod(uSky, aDir, 0.0).rgb * uSkyGain : vec3(0.0);
  vec4 c = projectionMatrix * vec4(mat3(viewMatrix) * (mat3(modelMatrix) * aDir), 1.0);
  float A = aStar.a * uGain * uThin;
  // the spot ends where the middle has fallen to 1/250, the halo where it is too faint to see
  float halo = 2.0 * uSigma * sqrt(max(pow(A * uGlare * 0.14 / 0.0015, 2.0 / 3.0) - 1.0, 0.0));
  float size = min(max(3.3 * uSigma, halo), 48.0 * uSigma);
  vStar = vec4(aStar.rgb, A); vHalf = size;
#ifdef QUAD
  vP = position.xy * size;
  c.xy += position.xy * size * uPixel * c.w;
#else
  gl_PointSize = 2.0 * size;
#endif
  c.z = 0.0;
  gl_Position = c;
}`;
const STAR_FRAG = /* glsl */`
varying vec2 vP; varying vec4 vStar; varying float vHalf; varying vec3 vUnder; uniform float uSigma, uGlare;
${DISPLAY}
void main() {
#ifdef QUAD
  vec2 p = vP;
#else
  vec2 p = (gl_PointCoord - 0.5) * 2.0 * vHalf;
#endif
  float r2 = dot(p, p), a = 2.0 * uSigma, w = 1.0 + r2 / (a * a);
  float core = exp(-r2 / (2.0 * uSigma * uSigma));
  float halo = uGlare * 0.14 / (w * sqrt(w)) * smoothstep(1.0, 0.6, sqrt(r2) / vHalf);
  vec3 light = vStar.rgb * vStar.a * (core + halo);
  gl_FragColor = vec4(uDisplay < 0.5 ? light : display(vUnder + light) - display(vUnder), 1.0);
}`;
/** Stars at least this bright (the light of the middle pixel) are drawn as quads. */
const QUAD_AMPLITUDE = 1.2;
/** The narrowest a star's spot is drawn (the gaussian's sigma in pixels): narrower, its light would jump between pixels. */
export const MIN_SIGMA = 0.62;

/** The sky spaceSky returns. `object`: add it to the scene. `direction(name)`: where something is.
 * `background` / `environment`: the whole sky as a cube texture / a PMREM for reflections (made on first
 * use). `info`: what was drawn. `set({brightness})` changes the gain live. `dispose()` frees everything. */
export class SpaceSky {
  constructor(renderer, options = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("spaceSky(renderer, options): the first argument must be a THREE.WebGLRenderer");
    const o = resolveOptions(options);
    this.renderer = renderer; this.options = o; this.band = o.band;
    const height = renderer.getDrawingBufferSize(new THREE.Vector2()).y;
    this.size = o.size ?? (height >= 600 ? 1024 : 512);
    this.target = bakeSky(renderer, {...o, brightness: 1}, this.size);
    // the stars: the file's with seeded ones fainter than it is complete to, or all seeded
    const real = o.stars === "real", fromFile = real ? catalogStars() : null;
    const seeded = seededStars(o.seed, {limit: o.limit, density: o.density, from: real ? Math.min(o.limit, CATALOG.complete_to) : -Infinity, frame: o.band, gather: Math.min(1, o.milkyWay)});
    this.stars = real ? joinStars(fromFile, seeded) : seeded;
    const s = this.stars, points = {dir: [], star: []}, quads = {dir: [], star: []};
    for (let i = 0; i < s.count; i++) {
      const c = starColor(s.bv[i], 0.7 * o.color), A = starAmplitude(s.mag[i], o.contrast), to = A >= QUAD_AMPLITUDE ? quads : points;
      to.dir.push(s.dir[i * 3], s.dir[i * 3 + 1], s.dir[i * 3 + 2]); to.star.push(c[0], c[1], c[2], A);
    }
    this.info = Object.freeze({stars: s.count, mode: o.stars, catalog: real ? CATALOG.catalog : null, approximate: real ? !!CATALOG.approximate : false,
      catalogStars: real ? fromFile.count : 0, completeTo: real ? CATALOG.complete_to : null, size: this.size, nebulae: o.nebulae, galaxies: o.galaxies});
    this.pointGeometry = new THREE.BufferGeometry();
    this.pointGeometry.setAttribute("position", new THREE.Float32BufferAttribute(points.dir, 3));
    this.pointGeometry.setAttribute("aDir", this.pointGeometry.getAttribute("position"));
    this.pointGeometry.setAttribute("aStar", new THREE.Float32BufferAttribute(points.star, 4));
    const quad = new THREE.PlaneGeometry(2, 2);
    this.quadGeometry = new THREE.InstancedBufferGeometry();
    this.quadGeometry.index = quad.index; this.quadGeometry.setAttribute("position", quad.getAttribute("position"));
    this.quadGeometry.setAttribute("aDir", new THREE.InstancedBufferAttribute(Float32Array.from(quads.dir), 3));
    this.quadGeometry.setAttribute("aStar", new THREE.InstancedBufferAttribute(Float32Array.from(quads.star), 4));
    this.quadGeometry.instanceCount = quads.star.length / 4;
    this.boxGeometry = new THREE.BoxGeometry(2, 2, 2);
    this.display = {value: 0};
    const common = {depthTest: false, depthWrite: false, toneMapped: false, fog: false};
    this.skyMaterial = new THREE.ShaderMaterial({...common, side: THREE.BackSide, vertexShader: SKY_VERT, fragmentShader: SKY_FRAG,
      uniforms: {uSky: {value: this.target.texture}, uGain: {value: o.brightness}, uSize: {value: this.size}, uDisplay: this.display}});
    this.starUniforms = {uSky: {value: this.target.texture}, uSkyGain: this.skyMaterial.uniforms.uGain, uPixel: {value: new THREE.Vector2()}, uSigma: {value: 1}, uThin: {value: 1}, uGlare: {value: o.glare}, uGain: {value: o.brightness}, uDisplay: this.display};
    const star = {...common, blending: THREE.AdditiveBlending, transparent: false, vertexShader: STAR_VERT, fragmentShader: STAR_FRAG, uniforms: this.starUniforms};
    this.pointMaterial = new THREE.ShaderMaterial(star);
    this.quadMaterial = new THREE.ShaderMaterial({...star, defines: {QUAD: 1}});
    this.pointMaterial.uniforms = this.quadMaterial.uniforms = this.starUniforms;
    this.object = this._group();
    this._background = null; this._environment = null; this._disposed = false; this._baking = false;
    // whoever disposes the sky's material (a page taking its scene down) frees the baked cube with it
    this.skyMaterial.addEventListener("dispose", () => this._free());
  }

  // the cube and the stars as one group; each draw reads the size of what it is drawn into
  _group() {
    const group = new THREE.Group(), view = new THREE.Vector4();
    const sky = new THREE.Mesh(this.boxGeometry, this.skyMaterial), points = new THREE.Points(this.pointGeometry, this.pointMaterial), quads = new THREE.Mesh(this.quadGeometry, this.quadMaterial);
    const before = (renderer) => {
      renderer.getCurrentViewport(view);
      const u = this.starUniforms, o = this.options;
      u.uPixel.value.set(2 / view.z, 2 / view.w);
      // a spot is never narrower than 0.62 px: in a small frame, where it would be, its light is thinned instead
      // (as a photograph scaled down dims its stars), or a small frame would be crowded with them
      // (into the sky's own cube map: spots 0.7 texels wide, thinned for the frame that will enlarge them)
      const natural = 0.75 * view.w / 720, sigma = this._baking ? 0.7 : Math.max(MIN_SIGMA, natural);
      u.uSigma.value = sigma * o.starSize; u.uThin.value = this._baking ? 0.4 : Math.pow(natural / sigma, 1.2);
      this.display.value = (o.display === "auto" ? renderer.getRenderTarget() === null : o.display) ? 1 : 0;
      for (const m of [this.skyMaterial, this.pointMaterial, this.quadMaterial]) m.uniformsNeedUpdate = true;
    };
    for (const [mesh, order] of [[sky, -1000], [points, -999], [quads, -998]]) { mesh.frustumCulled = false; mesh.renderOrder = order; mesh.onBeforeRender = before; }
    quads.visible = this.quadGeometry.instanceCount > 0;
    group.name = "space sky"; group.frustumCulled = false; group.add(sky, points, quads);
    return group;
  }

  /** The world direction (a THREE.Vector3; the sky's own turn applied) of "center", "anticenter", "pole",
   * "nebula N" / "galaxy N" (from 1), a named star of the real sky, or {l, b} degrees along and above the band. */
  direction(name) {
    const o = this.options, out = (d) => new THREE.Vector3(...d).applyQuaternion(this.object.quaternion).normalize();
    if (name && typeof name === "object") return out(directionOf("direction", name, this.band));
    const key = String(name).trim().toLowerCase();
    if (key === "center" || key === "centre") return out(this.band.center);
    if (key === "anticenter" || key === "anticentre") return out(this.band.center.map((x) => -x));
    if (key === "pole") return out(this.band.pole);
    const numbered = /^(nebula|galaxy)\s*(\d+)$/.exec(key);
    if (numbered) {
      const list = numbered[1] === "nebula" ? o.nebulae : o.galaxies, item = list[Number(numbered[2]) - 1];
      if (!item) throw fail(`direction("${name}"): this sky has ${list.length} ${numbered[1] === "nebula" ? "nebulae" : "galaxies"}`);
      return out(item.direction);
    }
    const index = this.stars.names.get(key);
    if (index !== undefined) return out([...this.stars.dir.subarray(index * 3, index * 3 + 3)]);
    const names = ["center", "anticenter", "pole", "nebula 1", "galaxy 1", ...this.stars.names.keys()];
    throw fail(`direction("${name}"): nothing of that name${hint(key, names)}${o.stars === "real" ? "" : "; star names belong to the real sky (stars: \"real\")"}`);
  }

  /** Change the gain of the whole sky (`brightness`) or the bright stars' halo (`glare`) without baking again. */
  set({brightness = null, glare = null} = {}) {
    if (brightness !== null) { number("brightness", brightness, 0, 16); this.skyMaterial.uniforms.uGain.value = brightness; this.starUniforms.uGain.value = brightness; }
    if (glare !== null) this.starUniforms.uGlare.value = number("glare", glare, 0, 8);
    return this;
  }

  // the whole sky, stars included, drawn once into a cube of `size` (linear light)
  _cube(size) {
    const rt = new THREE.WebGLCubeRenderTarget(size, {type: THREE.HalfFloatType, magFilter: THREE.LinearFilter, minFilter: THREE.LinearMipmapLinearFilter, generateMipmaps: true});
    const scene = new THREE.Scene(), renderer = this.renderer, target = renderer.getRenderTarget(), face = renderer.getActiveCubeFace(), level = renderer.getActiveMipmapLevel();
    scene.add(this._group());
    this._baking = true;
    new THREE.CubeCamera(0.1, 10, rt).update(renderer, scene);
    this._baking = false;
    renderer.setRenderTarget(target, face, level);
    return rt;
  }
  /** The whole sky as a cube texture for `scene.background` (stars as wide as its texels; made on first use). */
  get background() { this._background ??= this._cube(this.size); return this._background.texture; }
  /** The sky as an environment map (PMREM) for reflections on metal (made on first use). */
  get environment() {
    if (!this._environment) {
      const cube = this._cube(256), pmrem = new THREE.PMREMGenerator(this.renderer);
      this._environment = pmrem.fromCubemap(cube.texture); pmrem.dispose(); cube.dispose();
    }
    return this._environment.texture;
  }

  _free() {
    if (this._disposed) return;
    this._disposed = true;
    for (const x of [this.target, this._background, this._environment, this.skyMaterial, this.pointMaterial, this.quadMaterial, this.boxGeometry, this.pointGeometry, this.quadGeometry]) if (x) x.dispose();
  }
  /** Take the sky out of its scene and free its cube maps, geometries and materials. */
  dispose() { this.object.removeFromParent(); this._free(); }
}

/** A sky for a space scene: `spaceSky(renderer, {seed})`, or `{stars: "real"}`; add `sky.object` to the scene.
 * Options (DEFAULTS): seed, stars ("seed" | "real"), look ("natural" | "rich" | "sparse"), size, density,
 * brightness, color, limit, starSize, glare, contrast, milkyWay, dust, center, pole, nebulae, galaxies, display. */
export const spaceSky = (renderer, options = {}) => new SpaceSky(renderer, options);

// ---------- a galaxy to fly past: glowing gas, dust and stars as particles ----------
const GALAXY_DEFAULTS = Object.freeze({seed: 1, radius: 1, arms: 2, wind: 2.5, stars: 40000, clouds: 1600, dust: 1, bulge: 1, thickness: 1, brightness: 1, color: 1});
const SPRITE_VERT = /* glsl */`
attribute vec3 aAt; attribute vec4 aLight; attribute float aSize;
varying vec2 vP; varying vec4 vLight;
void main() {
  vec4 mv = modelViewMatrix * vec4(aAt, 1.0);
  float size = aSize * length(modelMatrix[0].xyz);
  mv.xy += position.xy * size * 2.2;
  vP = position.xy * 2.2; vLight = aLight;
  gl_Position = projectionMatrix * mv;
}`;
const SPRITE_FRAG = /* glsl */`
varying vec2 vP; varying vec4 vLight; uniform float uGain;
void main() {
  float g = (exp(-0.5 * dot(vP, vP)) - 0.089) / 0.911;
  if (g <= 0.0) discard;
#ifdef DUST
  gl_FragColor = vec4(vLight.rgb, vLight.a * g);
#else
  gl_FragColor = vec4(vLight.rgb * vLight.a * g * uGain, 1.0);
#endif
}`;
// a star of the galaxy: a point of light whose spot never gets smaller than a pixel (its light is thinned instead)
const SPECK_VERT = /* glsl */`
attribute vec4 aLight;
uniform float uSigma, uThin, uGain, uUnit;
varying vec4 vLight;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float d = max(-mv.z, 1e-6) / (uUnit * length(modelMatrix[0].xyz));
  vLight = vec4(aLight.rgb, aLight.a * uGain * uThin * min(1.0 / (d * d), 12.0));
  gl_PointSize = 6.6 * uSigma;
  gl_Position = projectionMatrix * mv;
}`;
const SPECK_FRAG = /* glsl */`
varying vec4 vLight; uniform float uSigma;
void main() {
  vec2 p = (gl_PointCoord - 0.5) * 6.6 * uSigma;
  gl_FragColor = vec4(vLight.rgb * vLight.a * exp(-dot(p, p) / (2.0 * uSigma * uSigma)), 1.0);
}`;
/** A spiral galaxy made of particles, to stand in the scene and be flown past: `galaxy.object` is a group
 * whose disc lies in its own x-z plane (its pole +y), of `radius` scene units; place, turn and scale it
 * like any object. Glowing gas along the arms and a warm bulge (soft sprites), dust on the arms' inner
 * edges (dark sprites), stars as points whose light falls with the square of the distance. Options
 * (GALAXY_DEFAULTS): seed, radius, arms, wind (how tightly the arms wind), stars and clouds (how many
 * particles), dust, bulge, thickness, brightness, color. Its many faint sprites add up in linear light:
 * draw it through a tone-mapping chain (vidgen/three-finish), not straight to the canvas. */
export function spiralGalaxy(options = {}) {
  known("spiralGalaxy options", options, Object.keys(GALAXY_DEFAULTS));
  const o = {...GALAXY_DEFAULTS, ...options};
  if (!Number.isInteger(o.seed) || o.seed < 0) throw fail(`spiralGalaxy seed must be a whole number from 0, got ${JSON.stringify(o.seed)}`);
  number("spiralGalaxy radius", o.radius, 1e-9, 1e30); number("spiralGalaxy arms", o.arms, 1, 6); number("spiralGalaxy wind", o.wind, 0.5, 8);
  number("spiralGalaxy stars", o.stars, 0, 400000); number("spiralGalaxy clouds", o.clouds, 0, 20000); number("spiralGalaxy dust", o.dust, 0, 4);
  number("spiralGalaxy bulge", o.bulge, 0, 4); number("spiralGalaxy thickness", o.thickness, 0, 10); number("spiralGalaxy brightness", o.brightness, 0, 64); number("spiralGalaxy color", o.color, 0, 2);
  const r = rng(o.seed * 2671 + 11), arms = Math.round(o.arms), R = o.radius;
  const gauss = () => Math.sqrt(-2 * Math.log(1 - r() * 0.999999)) * Math.cos(TAU * r());
  const tintOf = (c) => { const l = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; return c.map((v) => Math.max(0, l + (v - l) * o.color)); };
  const WARM = tintOf([1.0, 0.80, 0.56]), OLD = tintOf([1.0, 0.90, 0.76]), YOUNG = tintOf([0.66, 0.80, 1.0]), PINK = tintOf([1.0, 0.30, 0.42]);
  const phase = r() * TAU;
  // a place in the disc: the radius falls off exponentially, the angle follows an arm (spread: how far from it), the height is thin
  const inDisc = (spread, lead = 0, scale = 0.24) => {
    let rr = 2; while (rr > 1) rr = 0.04 - scale * Math.log(1 - r() * 0.985);
    const arm = Math.floor(r() * arms);
    const a = phase + arm * TAU / arms + o.wind * Math.log(rr / 0.05) + lead + spread * gauss() * (0.35 + 0.65 * Math.min(1, 0.3 / rr));
    return [rr, a, gauss() * 0.012 * o.thickness * (0.6 + rr)];
  };
  const place = (rr, a, y) => [Math.cos(a) * rr * R, y * R, Math.sin(a) * rr * R];
  const mixed = (a, b, u) => a.map((v, i) => v + (b[i] - v) * u);
  // gas and unresolved stars: soft sprites
  const cloudAt = [], cloudLight = [], cloudSize = [];
  const nBulge = Math.round(o.clouds * 0.16 * Math.min(1, o.bulge));
  for (let i = 0; i < o.clouds; i++) {
    if (i < nBulge) {
      const rr = Math.abs(gauss()) * 0.075 * Math.sqrt(o.bulge), a = r() * TAU, y = gauss() * 0.045 * Math.sqrt(o.bulge);
      cloudAt.push(...place(rr, a, y)); cloudLight.push(...WARM, 0.030 * o.bulge); cloudSize.push((0.025 + 0.045 * r()) * R);
    } else {
      const knot = r() < 0.05, between = r() < 0.30, [rr, a, y] = inDisc(between ? 1.1 : 0.20, 0, 0.26);
      const c = knot ? PINK : mixed(OLD, YOUNG, Math.min(1, (between ? 0.2 : 0.75) * Math.min(1, rr / 0.25) + 0.25 * r()));
      cloudAt.push(...place(rr, a, y)); cloudLight.push(...c, knot ? 0.14 : between ? 0.006 : 0.016 * (0.5 + r()));
      cloudSize.push((knot ? 0.004 + 0.006 * r() : between ? 0.05 + 0.05 * r() : 0.018 + 0.04 * r()) * R);
    }
  }
  // dust: dark sprites a little ahead of the arms' ridge, thin
  const dustAt = [], dustLight = [], dustSize = [], nDust = Math.round(o.clouds * 0.45 * Math.min(1, o.dust));
  for (let i = 0; i < nDust; i++) {
    const [rr, a, y] = inDisc(0.16, -0.32, 0.22);
    if (rr < 0.1) continue;
    dustAt.push(...place(rr, a, y * 0.5)); dustLight.push(0.012, 0.007, 0.004, Math.min(0.9, 0.11 * o.dust * (0.3 + r()))); dustSize.push((0.016 + 0.034 * r()) * R);
  }
  // stars: points
  const starAt = [], starLight = [];
  for (let i = 0; i < o.stars; i++) {
    const u = r();
    if (u < 0.2 * Math.min(1, o.bulge)) {
      const rr = Math.abs(gauss()) * 0.085, a = r() * TAU;
      starAt.push(...place(rr, a, gauss() * 0.05)); starLight.push(...mixed(WARM, OLD, r()), 0.02 + 0.3 * r() ** 6);
    } else {
      const between = u > 0.62, [rr, a, y] = inDisc(between ? 1.6 : 0.26, 0, 0.27), young = !between && r() < 0.55;
      starAt.push(...place(rr, a, y * (young ? 0.7 : 1.6))); starLight.push(...(young ? mixed(YOUNG, [1, 1, 1], r() * 0.5) : mixed(OLD, WARM, r())), (young ? 0.03 : 0.015) + 0.7 * r() ** 9);
    }
  }
  const group = new THREE.Group(), view = new THREE.Vector4(), quad = new THREE.PlaneGeometry(2, 2);
  const sprites = (at, light, size) => {
    const g = new THREE.InstancedBufferGeometry();
    g.index = quad.index; g.setAttribute("position", quad.getAttribute("position"));
    g.setAttribute("aAt", new THREE.InstancedBufferAttribute(Float32Array.from(at), 3)); g.setAttribute("aLight", new THREE.InstancedBufferAttribute(Float32Array.from(light), 4));
    g.setAttribute("aSize", new THREE.InstancedBufferAttribute(Float32Array.from(size), 1)); g.instanceCount = size.length;
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R * 1.3);
    return g;
  };
  const gain = {value: o.brightness}, sigma = {value: 1}, thin = {value: 1};
  const glow = new THREE.Mesh(sprites(cloudAt, cloudLight, cloudSize), new THREE.ShaderMaterial({vertexShader: SPRITE_VERT, fragmentShader: SPRITE_FRAG, uniforms: {uGain: gain},
    blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, toneMapped: false}));
  const dark = new THREE.Mesh(sprites(dustAt, dustLight, dustSize), new THREE.ShaderMaterial({vertexShader: SPRITE_VERT, fragmentShader: SPRITE_FRAG, uniforms: {uGain: gain}, defines: {DUST: 1},
    blending: THREE.NormalBlending, transparent: true, depthWrite: false, toneMapped: false}));
  const starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute("position", new THREE.Float32BufferAttribute(starAt, 3)); starGeometry.setAttribute("aLight", new THREE.Float32BufferAttribute(starLight, 4));
  starGeometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R * 1.3);
  const specks = new THREE.Points(starGeometry, new THREE.ShaderMaterial({vertexShader: SPECK_VERT, fragmentShader: SPECK_FRAG, uniforms: {uSigma: sigma, uThin: thin, uGain: gain, uUnit: {value: R}},
    blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, toneMapped: false}));
  // in a small frame the stars' spots cannot shrink further: their light is thinned by the area instead
  specks.onBeforeRender = (renderer) => {
    renderer.getCurrentViewport(view);
    const natural = 0.75 * view.w / 720; sigma.value = Math.max(MIN_SIGMA, natural); thin.value = (natural / sigma.value) ** 2;
    specks.material.uniformsNeedUpdate = true;
  };
  glow.renderOrder = 0; specks.renderOrder = 1; dark.renderOrder = 2;
  dark.visible = nDust > 0; glow.visible = o.clouds > 0; specks.visible = o.stars > 0;
  group.name = "spiral galaxy"; group.add(glow, dark, specks);
  return {object: group, options: o, set({brightness}) { gain.value = number("brightness", brightness, 0, 64); return this; },
    dispose() { group.removeFromParent(); for (const m of [glow, dark, specks]) { m.geometry.dispose(); m.material.dispose(); } }};
}
