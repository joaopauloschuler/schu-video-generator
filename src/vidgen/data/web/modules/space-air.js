// vidgen/space-air: the sky seen from inside an atmosphere. Part of
// schu-video-generator (MIT licence); imported by a page as "vidgen/space-air".
//
//   import {air} from "vidgen/space-air";
//   const sky = air(renderer, "earth", {sun: [0.4, 0.3, -0.85], stars: spaceSky(renderer, {seed: 7})});
//   scene.add(sky.object);                         // the dome: sky, sun disc, a plain ground under the horizon
//   sky.haze(mountain.material);                   // aerial perspective on anything in the scene
//   scene.add(sky.light.sun, sky.light.sky);       // the sun after the air, and the sky's own light
//   function frame(t) { sky.update(t, {camera, sun}); renderer.render(scene, camera); }
//
// One model for every height, from the ground to space: the air is the one vidgen/space-bodies draws
// round the same world from outside (its AIRS: zenith optical depths of gas, haze and absorber per
// colour, one scale height, the shell's top at 8 scale heights, the same closed form for the air
// along a ray), so a planet's limb seen from orbit and its sky seen from the ground are one
// atmosphere. Light scattered once is summed along each ray with its exact share per slab; light
// scattered more often is one stated approximation: an isotropic second bounce, with the ground's,
// summed as a geometric series (a table over height and the sun's height, baked once through
// vidgen/baked). The picture reads a small table of the whole sky (all directions for this height and
// this sun, drawn again only when either changes), so a frame costs a few texture reads a pixel.
// Two things only the inside view has, both stated: a thin absorbing layer (the Earth-like air's ozone,
// which keeps the dusk blue) and the haze's forward throw per colour (the Mars-like air's blue glow).
// Shadows in the air (Step 403): what casts a shadow (cloud decks, ground: addCaster) darkens the air in it.
// Exposure as vidgen/space-light: "film" (a convention: nothing changed by day, dusk lifted, the stars
// shown once the sky is dark), "camera" (stops over a sunlit ground's: honest) and "auto" (metered).
// Scene units are metres by default, +y up, the origin on the ground (`center` and `unit` say otherwise).
import * as THREE from "three";
import {baked} from "vidgen/baked";
import {AIRS, PRESETS as WORLDS, resolveOptions as resolveWorld, linearColor} from "vidgen/space-bodies";

/** Bumped when the pictures change: part of the baked table's key. */
export const VERSION = 1;
const PREFIX = "vidgen/space-air";
const RAD = Math.PI / 180;
/** The top of the air in scale heights (as vidgen/space-bodies' shell). */
export const TOP = 8;
/** The Sun's angular radius seen from the Earth, degrees. */
export const SUN_SIZE = 0.2665;
/** How bright a sun's disc may be drawn, in whites (vidgen/space-light's BURN). */
export const BURN = 32;
/** Stops between a sunlit ground and the sky's look (vidgen/space-light's SKY_STOPS). */
export const SKY_STOPS = 20;
export const EXPOSURES = Object.freeze(["film", "camera", "auto"]);
export const QUALITIES = Object.freeze(["fast", "standard", "fine"]);
/** The sky table by quality: directions round (half the circle: the sky is the same left and right of the sun), rows above and below the horizon each, steps along a ray. */
export const VIEW_TABLES = Object.freeze({fast: [48, 48, 16], standard: [64, 96, 32], fine: [96, 160, 48]});
/** The table of light scattered more than once: the sun's heights, the observer's heights; of its sum the directions
 * round, the directions up and down (crowded towards the level, where the twilight's light lies) and the steps along each. */
export const PSI_TABLE = Object.freeze({suns: 64, heights: 32, directions: 8, elevations: 14, steps: 24, sunFrom: -0.4});

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
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a), 0, 1); return u * u * (3 - 2 * u); };
const luma = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];

/** Ready-made airs. `world`: the world of vidgen/space-bodies whose air this is (so `planet(renderer, world)`
 * shows the same air from outside) and whose radius it has; `air`: an air stated as there ({like, density,
 * rayleigh, haze, absorb, height, forward, glow}) in place of the world's own: hand the same to the body
 * (`planet(renderer, "mars", {air: PRESETS.mars.air})`) to see it from outside; `radius` in metres;
 * `forward`: how sharply the haze throws light onward, per colour (the outside view uses one number);
 * `aureole` and `aureoleForward`: a second, narrow lobe of the haze, its share of the haze's light per colour
 * and its forward throw (dust grains larger than the light's wave throw a tight cone of light onward);
 * `ozone` and `ozoneHeight`: a thin absorbing layer's zenith optical depth per colour and its height in
 * metres (the outside view has none); `ground`: the plain ground's colour under the horizon.
 * `earth`: the world's own air with an ozone layer of 300 Dobson units' absorption (physical). `mars`: a
 * dusty season, three times the world's dust with grey extinction, the two lobes chosen for the look (a
 * compact blue-white glow round a low sun in a tawny sky)
 * (`{world: "mars"}` is the world's own, clearer air). `thin`, `thick`: invented worlds. */
export const PRESETS = Object.freeze({
  earth: {world: "earth", ozone: [0.030, 0.028, 0.004], ozoneHeight: 25000, ground: [0.09, 0.10, 0.085]},
  mars: {world: "mars", air: {like: "mars", density: 3, absorb: [0, 0.013, 0.031]}, forward: [0.36, 0.42, 0.55], aureole: [0.02, 0.06, 0.35], aureoleForward: 0.93, ground: [0.30, 0.15, 0.07]},
  thin: {air: "thin", radius: 2.4e6, ground: [0.32, 0.36, 0.42]},
  thick: {air: {like: "earth", density: 4, haze: [0.05, 0.05, 0.05], height: 0.0018}, radius: 7.4e6, ground: [0.05, 0.09, 0.08]},
});
/** The radii (metres) of vidgen/space-bodies' worlds that have air: the real ones', invented ones for the invented. */
export const RADII = Object.freeze({venus: 6.0518e6, earth: 6.371e6, mars: 3.3895e6, jupiter: 6.9911e7, saturn: 5.8232e7, uranus: 2.5362e7, neptune: 2.4622e7, titan: 2.5747e6,
  ember: 3.1e6, boreas: 2.4e6, ochre: 4.2e6, tempest: 6.1e7, verdant: 6.9e6, azure: 2.3e7});
const AIR_OPTIONS = ["world", "air", "radius", "forward", "aureole", "aureoleForward", "ground", "ozone", "ozoneHeight", "name"];

/** The air in full, as numbers: `what` a name of PRESETS, a world of vidgen/space-bodies, an air of its
 * AIRS, a body made by its `planet()` (that body's air), or {world | air, radius, forward, ozone,
 * ozoneHeight, ground}; `extra` over it. Returns {name, radius (m), height (the scale height as a share
 * of the radius), H (m), X0 (the radius in scale heights), top (m), rayleigh, haze, absorb, ext (zenith
 * optical depths, linear red green blue), ozone, hz (the layer's height in scale heights), forward
 * [r, g, b], glow, ground (linear albedo)}. Pure. */
export function airOf(what = "earth", extra = {}) {
  let base = what;
  if (typeof what === "string") {
    const key = what.trim().toLowerCase();
    if (key in PRESETS) base = {...PRESETS[key], name: key};
    else if (key in WORLDS) base = {world: key, name: key};
    else if (key in AIRS) base = {air: key, name: key};
    else {
      const names = [...Object.keys(PRESETS), ...Object.keys(WORLDS).filter((w) => resolveWorld(w).air), ...Object.keys(AIRS)];
      throw fail(`no air "${what}"${hint(key, names)}; ready-made: ${Object.keys(PRESETS).join(", ")}; worlds of vidgen/space-bodies with air: ${[...new Set(names.slice(Object.keys(PRESETS).length, -Object.keys(AIRS).length))].join(", ")}; airs: ${Object.keys(AIRS).join(", ")}`);
    }
  } else if (what === null || typeof what !== "object" || Array.isArray(what)) throw fail(`the air must be a name or an options object, got ${JSON.stringify(what)}`);
  else if (what.options && what.object && typeof what.setSun === "function") {
    // a body of vidgen/space-bodies: its own air as it is drawn from outside
    if (!what.options.air) throw fail("this body has no air (it was made with air: false, or its type has none)");
    base = {air: what.options.air, name: what.options.name ?? null, ...(what.options.name in RADII ? {radius: RADII[what.options.name]} : {})};
  }
  known("the air's options", extra, AIR_OPTIONS);
  const o = {...base, ...extra};
  known("the air", o, AIR_OPTIONS);
  const world = o.world === undefined ? null : String(o.world).toLowerCase();
  if (world !== null && !(world in WORLDS)) throw fail(`no world "${o.world}" in vidgen/space-bodies${hint(world, Object.keys(WORLDS))}`);
  // the air stated here, or the world's own
  const air = o.air !== undefined ? resolveWorld({type: "rocky", air: o.air}).air : resolveWorld(world ?? "earth").air;
  if (!air) throw fail(o.air !== undefined ? "the air has no gas and no haze: nothing to draw" : `the world "${world}" has no air; worlds with air: ${Object.keys(WORLDS).filter((w) => resolveWorld(w).air).join(", ")}`);
  const radius = number("radius (metres)", o.radius ?? RADII[world] ?? 6.371e6, 1e4, 1e9);
  let forward = o.forward ?? air.forward;
  if (typeof forward === "number") forward = [forward, forward, forward];
  if (!Array.isArray(forward) || forward.length !== 3) throw fail(`forward must be a number or [red, green, blue] from 0 to 0.95, got ${JSON.stringify(o.forward)}`);
  forward.forEach((g) => number("forward", g, 0, 0.95));
  const ground = linearColor("ground", o.ground ?? [0.1, 0.1, 0.1]), ozone = linearColor("ozone", o.ozone ?? [0, 0, 0]);
  const aureole = o.aureole ?? [0, 0, 0], aureoleForward = number("aureoleForward", o.aureoleForward ?? 0.93, 0, 0.98);
  if (!Array.isArray(aureole) || aureole.length !== 3) throw fail(`aureole must be [red, green, blue], each the narrow lobe's share of the haze's light from 0 to 1, got ${JSON.stringify(o.aureole)}`);
  aureole.forEach((x) => number("aureole", x, 0, 1));
  const ext = air.rayleigh.map((x, i) => x + air.haze[i] + air.absorb[i]), H = air.height * radius;
  const ozoneHeight = number("ozoneHeight (metres)", o.ozoneHeight ?? 2.8 * H, 0.5 * H, (TOP - 1) * H);
  return Object.freeze({name: o.name ?? o.world ?? null, radius, height: air.height, H, X0: 1 / air.height, top: TOP * H,
    rayleigh: Object.freeze([...air.rayleigh]), haze: Object.freeze([...air.haze]), absorb: Object.freeze([...air.absorb]), ext: Object.freeze(ext),
    ozone: Object.freeze(ozone), hz: ozoneHeight / H, aureole: Object.freeze([...aureole]), aureoleForward,
    forward: Object.freeze([...forward]), glow: Object.freeze([...air.glow]), ground: Object.freeze(ground)});
}

// ---------- the model in JavaScript: the numbers behind the light and the exposure, and the tests' reference ----------
/** The air between a point (`h` its height in scale heights, on a world `X0` scale heights in radius) and
 * space along a direction whose cosine to the vertical is `c`, in zenith columns: vidgen/space-bodies'
 * closed form (Chapman's function after Schueler; under the horizon twice the tangent path less the path upward). */
export function column(X0, h, c) {
  const X = X0 + h, k = Math.sqrt(1.5708 * X), up = k / (k * Math.abs(c) + 1) * Math.exp(-h);
  if (c >= 0) return up;
  const s = Math.sqrt(Math.max(1 - c * c, 0)), ht = h * s - X0 * c * c / (1 + s);
  return Math.max(2 * Math.sqrt(1.5708 * X * s) * Math.exp(-Math.max(ht, -6)) - up, up);
}
/** How often, and how aslant, the line from a point (`h` scale heights up) to space along cosine `c` crosses a thin
 * layer `hz` scale heights up: 1 over the cosine at the layer per crossing, at most 41 (the layer has a depth: a ray grazing a layer 15 km deep runs 58 times its depth in it). */
export function crossings(X0, hz, h, c) {
  const r = X0 + h, Rz = X0 + hz, e = ((hz - h) * (2 * X0 + hz + h) + r * r * c * c) / (Rz * Rz), f = 1 / Math.sqrt(Math.max(e, OZONE_EDGE));
  const below = 1 - smooth(hz - 0.5, hz + 0.5, h);
  return c >= 0 ? below * f : below * f + (1 - below) * 2 * f * smooth(0, 2 * OZONE_EDGE, e);
}
const OZONE_EDGE = 0.0006;
// the optical depth from a point (h scale heights up) to space along cosine c, per colour: the air's and the layer's
const tau = (m, h, c) => { const k = column(m.X0, h, c), z = m.ozone[0] + m.ozone[1] + m.ozone[2] > 0 ? crossings(m.X0, m.hz, h, c) : 0; return [m.ext[0] * k + m.ozone[0] * z, m.ext[1] * k + m.ozone[1] * z, m.ext[2] * k + m.ozone[2] * z, k]; };
/** The optical depth (red, green, blue) from `height` metres to space along cosine `c` to the vertical. */
export const opticalDepth = (model, height, c = 1) => tau(model, height / model.H, c).slice(0, 3);
/** What is left of a ray of light from space at `height` metres, arriving along cosine `c` to the vertical. */
export const transmittance = (model, height, c = 1) => opticalDepth(model, height, c).map((x) => Math.exp(-x));
/** The phase functions the model uses, times pi (so that a unit of light is a white ground's): Rayleigh's and Henyey-Greenstein's. */
export const phaseRayleigh = (cos) => 0.1875 * (1 + cos * cos);
export const phaseHaze = (g, cos) => 0.25 * (1 - g * g) / Math.pow(1 + g * g - 2 * g * cos, 1.5);

// a ray from height hc (scale heights): where the air begins and ends on it, and whether it ends on the ground
function span(X0, hc, mu) {
  const r0 = X0 + hc, dg = -hc * (2 * X0 + hc) + r0 * r0 * mu * mu, da = (TOP - hc) * (2 * X0 + TOP + hc) + r0 * r0 * mu * mu;
  const hit = mu < 0 && dg > 0;
  if (da <= 0 || (hc > TOP && mu >= 0)) return {t0: 0, t1: 0, hit: false};
  return {t0: hc > TOP ? -r0 * mu - Math.sqrt(da) : 0, t1: hit ? -r0 * mu - Math.sqrt(dg) : -r0 * mu + Math.sqrt(da), hit};
}
// the point t along it: height, the ray's cosine to the vertical there, the sun's
function at(X0, hc, mu, cosv, mus, t) {
  const r0 = X0 + hc, q = 2 * r0 * mu * t + t * t, r = Math.sqrt(r0 * r0 + q);
  return [(hc * (2 * X0 + hc) + q) / (r + X0), (r0 * mu + t) / r, (r0 * mus + t * cosv) / r];
}
const along = (m, p, up) => tau(m, p[0], up ? p[1] : -p[1]);
// the air's share of a slab's optical depth (the rest is the absorbing layer's)
const airShare = (air, all) => (all > 1e-12 ? Math.min(1, air / all) : 1);

/** The table of light scattered more than once (see the top of the file), in JavaScript: {suns, heights,
 * data (Float32Array, rgb per cell), at(h, mus) → [r, g, b]} for heights 0..TOP scale heights (rows,
 * spaced by the square root) and the sun's cosine PSI_TABLE.sunFrom..1. Coarser than the baked one by default. */
export function psiTable(model, {suns = 24, heights = 12, directions = 6, elevations = 10, steps = 12} = {}) {
  const data = new Float32Array(suns * heights * 3), X0 = model.X0, scat = model.ext.map((e, i) => (model.rayleigh[i] + model.haze[i]) / e);
  for (let j = 0; j < heights; j++) {
    for (let i = 0; i < suns; i++) {
      const hc = TOP * ((j + 0.5) / heights) ** 2, mus = PSI_TABLE.sunFrom + (1 - PSI_TABLE.sunFrom) * (i + 0.5) / suns;
      const cell = psiCell(model, X0, scat, hc, mus, directions, elevations, steps);
      data.set(cell, (j * suns + i) * 3);
    }
  }
  const read = (h, mus) => {
    const x = clamp((mus - PSI_TABLE.sunFrom) / (1 - PSI_TABLE.sunFrom) * suns - 0.5, 0, suns - 1), y = clamp(Math.sqrt(clamp(h / TOP, 0, 1)) * heights - 0.5, 0, heights - 1);
    const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(x0 + 1, suns - 1), y1 = Math.min(y0 + 1, heights - 1), fx = x - x0, fy = y - y0, out = [0, 0, 0];
    for (let k = 0; k < 3; k++) out[k] = (data[(y0 * suns + x0) * 3 + k] * (1 - fx) + data[(y0 * suns + x1) * 3 + k] * fx) * (1 - fy) + (data[(y1 * suns + x0) * 3 + k] * (1 - fx) + data[(y1 * suns + x1) * 3 + k] * fx) * fy;
    return out;
  };
  return {suns, heights, data, at: read};
}
function psiCell(model, X0, scat, hc, mus, directions, elevations, steps) {
  const L = [0, 0, 0], F = [0, 0, 0], sx = Math.sqrt(Math.max(1 - mus * mus, 0));
  for (let a = 0; a < elevations; a++) {
    // the cosine to the vertical goes as x |x|: many directions near the level, each weighing its share of the sphere
    const x = 2 * (a + 0.5) / elevations - 1, mu = x * Math.abs(x), w = Math.abs(x) * 2 / (elevations * directions);
    for (let b = 0; b < directions; b++) {
      const phi = 2 * Math.PI * (b + 0.5) / directions, cosv = Math.sqrt(1 - mu * mu) * Math.cos(phi) * sx + mu * mus;
      const {t0, t1, hit} = span(X0, hc, mu);
      if (t1 <= t0) continue;
      const p0 = at(X0, hc, mu, cosv, mus, t0), up = p0[1] >= 0, c0 = along(model, p0, up), T = [1, 1, 1], done = [0, 0, 0];
      let last = c0[3];
      for (let i = 1; i <= steps; i++) {
        const p = at(X0, hc, mu, cosv, mus, t0 + (t1 - t0) * i / steps), m = at(X0, hc, mu, cosv, mus, t0 + (t1 - t0) * (i - 0.5) / steps);
        const d = along(model, p, up), cs = tau(model, Math.max(m[0], 0), m[2]);
        const dk = Math.max(up ? last - d[3] : d[3] - last, 0);
        last = d[3];
        for (let k = 0; k < 3; k++) {
          const now = Math.max(up ? c0[k] - d[k] : d[k] - c0[k], 0), Tn = Math.exp(-now), share = w * (T[k] - Tn) * scat[k] * airShare(model.ext[k] * dk, now - done[k]);
          done[k] = now;
          L[k] += share * 0.25 * Math.exp(-cs[k]); F[k] += share; T[k] = Tn;
        }
      }
      if (hit) {
        const g = at(X0, hc, mu, cosv, mus, t1), cs = tau(model, 0, g[2]);
        for (let k = 0; k < 3; k++) L[k] += w * T[k] * model.ground[k] * Math.max(g[2], 0) * Math.exp(-cs[k]);
      }
    }
  }
  return L.map((l, k) => l / (1 - F[k]));
}
const tables = new WeakMap();
const psiOf = (model) => { let t = tables.get(model); if (!t) { t = psiTable(model); tables.set(model, t); } return t; };

/** The sky's light towards the observer at `height` metres along a ray whose cosine to the vertical is `mu`,
 * the cosine between ray and sun `cosv`, the sun's cosine to the vertical `mus`: {light: [r, g, b] for a
 * unit of sunlight (a white ground square to the sun is 1), through: what passes from behind, hit: the
 * ray ends on the ground}. The ground's own light is not in it. */
export function skyLight(model, height, mu, cosv, mus, {steps = 32, psi = null, scattered = true} = {}) {
  const X0 = model.X0, hc = height / model.H, {t0, t1, hit} = span(X0, hc, mu), out = [0, 0, 0], T = [1, 1, 1];
  if (t1 <= t0) return {light: out, through: T, hit: false};
  const table = scattered ? psi ?? psiOf(model) : null, k = hc > TOP ? 0 : 0.5;
  const p0 = at(X0, hc, mu, cosv, mus, t0), up = p0[1] >= 0, c0 = along(model, p0, up), pr = phaseRayleigh(cosv), done = [0, 0, 0];
  let last = c0[3];
  const place = (f) => t0 + (t1 - t0) * f * (1 - k + k * f);
  for (let i = 1; i <= steps; i++) {
    const p = at(X0, hc, mu, cosv, mus, place(i / steps)), m = at(X0, hc, mu, cosv, mus, place((i - 0.5) / steps));
    const d = along(model, p, up), cs = tau(model, Math.max(m[0], 0), m[2]), more = table ? table.at(Math.max(m[0], 0), m[2]) : out;
    const dk = Math.max(up ? last - d[3] : d[3] - last, 0);
    last = d[3];
    for (let c = 0; c < 3; c++) {
      const now = Math.max(up ? c0[c] - d[c] : d[c] - c0[c], 0), Tn = Math.exp(-now), e = model.ext[c], share = airShare(e * dk, now - done[c]);
      done[c] = now;
      out[c] += share * (T[c] - Tn) * (Math.exp(-cs[c]) * (model.rayleigh[c] * pr + model.haze[c] * ((1 - model.aureole[c]) * phaseHaze(model.forward[c], cosv) + model.aureole[c] * phaseHaze(model.aureoleForward, cosv))) + (table ? more[c] * (model.rayleigh[c] + model.haze[c]) : 0)) / e;
      T[c] = Tn;
    }
  }
  return {light: out, through: T, hit};
}

/** The sun's light at `height` metres after the air, the sun's cosine to the vertical `mus`: [r, g, b] of
 * a unit of sunlight; sinking behind the horizon it is the mean over the disc (`size`: its angular radius, degrees). */
export function sunlightAt(model, height, mus, size = SUN_SIZE) {
  const hc = height / model.H, a = Math.asin(clamp(mus, -1, 1)), out = [0, 0, 0], dip = -Math.acos(model.X0 / (model.X0 + Math.max(hc, 0)));
  for (const off of [-0.75, -0.25, 0.25, 0.75]) {
    const e = a + off * size * RAD;
    if (e < dip) continue;
    const k = tau(model, hc, Math.sin(e));
    for (let c = 0; c < 3; c++) out[c] += 0.25 * Math.exp(-k[c]);
  }
  return out;
}

/** The sky's light on a level, matt, white ground at `height` metres (the sun's own left out), as the
 * brightness it gives it: [r, g, b] for a unit of sunlight. A sum over 48 directions of the upper half. */
export function skyAmbient(model, height, mus, {steps = 10, psi = null} = {}) {
  const out = [0, 0, 0], sx = Math.sqrt(Math.max(1 - mus * mus, 0)), ne = 6, na = 8;
  for (let i = 0; i < ne; i++) {
    const mu = Math.sqrt((i + 0.5) / ne);                         // cosine-weighted: equal shares of the light each
    for (let j = 0; j < na; j++) {
      const cosv = Math.sqrt(1 - mu * mu) * Math.cos(2 * Math.PI * (j + 0.5) / na) * sx + mu * mus;
      const s = skyLight(model, height, mu, cosv, mus, {steps, psi}).light;
      for (let c = 0; c < 3; c++) out[c] += s[c] / (ne * na);
    }
  }
  return out;
}

/** The ground's ambient light for the sun's cosines PSI_TABLE.sunFrom..1, `n` entries: what the dome's
 * plain ground reads, and the brightness of the zenith and of the sky low over the horizon under the sun
 * (3 degrees up: the twilight arch), which the film exposure reads.
 * {n, data (rgb per entry), zenith, arch (one per entry), at(mus), zenithAt(mus), archAt(mus)}. */
export function ambientTable(model, n = 64) {
  const data = new Float32Array(n * 3), zenith = new Float32Array(n), arch = new Float32Array(n), psi = psiOf(model), low = Math.sin(3 * RAD);
  for (let i = 0; i < n; i++) {
    const mus = PSI_TABLE.sunFrom + (1 - PSI_TABLE.sunFrom) * i / (n - 1);
    data.set(skyAmbient(model, 0, mus, {psi}), i * 3);
    zenith[i] = luma(skyLight(model, 0, 1, mus, mus, {steps: 16, psi}).light);
    arch[i] = luma(skyLight(model, 0, low, Math.sqrt((1 - low * low) * (1 - mus * mus)) + low * mus, mus, {steps: 24, psi}).light);
  }
  const where = (mus) => { const x = clamp((mus - PSI_TABLE.sunFrom) / (1 - PSI_TABLE.sunFrom) * (n - 1), 0, n - 1), i = Math.min(Math.floor(x), n - 2); return [i, x - i]; };
  const read = (mus) => { const [i, f] = where(mus); return [0, 1, 2].map((c) => data[i * 3 + c] * (1 - f) + data[i * 3 + 3 + c] * f); };
  // between entries the zenith's brightness falls by a factor, not by a step: read it in the logarithm
  const log = (list) => (mus) => { const [i, f] = where(mus); return Math.exp(Math.log(list[i] + 1e-30) * (1 - f) + Math.log(list[i + 1] + 1e-30) * f); };
  return {n, data, zenith, arch, at: read, zenithAt: log(zenith), archAt: log(arch)};
}

/** The film exposure (stops over a sunlit ground's) for a sky whose zenith is `zenith` bright, when a
 * day's is `day`: nothing by day, then nearly all a meter on the zenith would open (the blue hour stays
 * blue), at most FILM_STOPS, and never so far that the sky low under the sun (`arch`) burns out: the zenith
 * darkens over a last glow. `heightInScales`: no lift above the air. A convention. */
export function filmExposure(zenith, day, heightInScales = 0, arch = 0) {
  const x = Math.max(0, Math.log2(day / Math.max(zenith, 1e-30)));
  // the arch may be as bright before the dusk curve as that curve brings down to ARCH_WHITE; where a hazy
  // air's glow round a low sun is brighter than that by itself, the exposure closes (at most FILM_CLOSE stops)
  const lift = Math.min(FILM_STOPS, 0.93 * x * x / (x + 0.3)), most = DUSK_KNEE * Math.pow(ARCH_WHITE / DUSK_KNEE, 1 / (1 - duskCurve(lift)));
  return Math.max(-FILM_CLOSE, Math.min(lift, Math.log2(most / Math.max(arch, 1e-30)))) * (1 - smooth(3, TOP, heightInScales));
}
export const FILM_CLOSE = 3;
/** The film look's dusk curve: once the exposure is lifted (from half a stop, fully from 4), the air's light over
 * DUSK_KNEE of white is drawn as knee x (light / knee)^(1 - DUSK_CURVE), its colour kept: a negative's
 * shoulder, so the twilight arch (hundreds of times the zenith's brightness) and the zenith fit in one picture. */
export const DUSK_CURVE = 0.5, DUSK_KNEE = 0.05;
export const duskCurve = (stops) => DUSK_CURVE * smooth(0.5, 4, stops);
/** How bright the film look lets the twilight arch be drawn (1 = white): the exposure opens no further. */
export const ARCH_WHITE = 1.6;
export const FILM_STOPS = 16;
/** How much of the stars the film look shows: none until the sky is `stops` = 5 stops darker than by day, all of
 * them from 11; wherever the zenith is drawn black (`drawn`, 1 = white: high up) all of them at night and
 * DAY_STARS of them over the day side (`sunUp`: the sun's sine over the level there), so the sky's band of light
 * does not outshine a sunlit world beside it (a look). */
export const DAY_STARS = 0.35;
export const filmStars = (stops, drawn = 1, sunUp = -1) => Math.max(smooth(5, 11, stops), (1 - smooth(0.002, 0.01, drawn)) * (1 - (1 - DAY_STARS) * smooth(-0.1, 0.1, sunUp)));
/** The unit vector towards a sun `elevation` degrees over the horizon at `azimuth` degrees (0 = towards -z, 90 = towards +x), +y up. */
export const sunDirection = (elevation, azimuth = 0) => [Math.cos(elevation * RAD) * Math.sin(azimuth * RAD), Math.sin(elevation * RAD), -Math.cos(elevation * RAD) * Math.cos(azimuth * RAD)];

// ---------- the model in GLSL: the same sums ----------
/** The uniforms and functions any shader needs to put air between the camera and a point: declare
 * nothing else, set the material's uniforms from `air.uniforms`, and call
 * `vec3 airThrough(vec3 colour, vec3 toPoint)` (linear light; `toPoint` from the camera to the point in
 * the scene's axes and units) or `vec3 airLight(mu, cosv, dist, out through, out hit)`. The sky seen from
 * another height (a reflection in water, the light on a cloud): `airRead(table, airPlace(map, mu, cosv), cosv)`
 * with the table and map of `Air.skyAt(height)`. */
export const AIR_GLSL = /* glsl */`
uniform vec4 uAirGeo;      // the radius in scale heights, the camera's height, the top, scale heights a scene unit
uniform vec4 uAirMap;      // the horizon's dip (radians), the span of the rows above and below it, the sun's cosine to the vertical
uniform vec4 uAirTable;    // the sky table's half-texels across and along, the same of the table of second-hand light
uniform vec3 uAirUp, uAirSun, uAirExt, uAirScatR, uAirScatM, uAirG, uAirLight, uAirGlow;
uniform vec4 uAirOzone;    // a thin absorbing layer: its zenith optical depth per colour, its height
uniform vec4 uAirAureole;  // the haze's second, narrow lobe: its share per colour, its forward throw
uniform vec2 uAirDusk;     // the film look's dusk curve: its strength, its knee
uniform sampler2D uAirView, uAirPsi;
uniform vec4 uAirShade;    // shadows in the air: 1 when on, the casters' top and the reach (scale heights)
uniform mat4 uAirShadeView; // a direction to its place in the picture of the shadows (the camera's projection and turn)
uniform sampler2D uAirShadow;   // that picture: of a ray's whole light, the share made in the casters' shadows half and all the way along the stretch they reach (xy: the rays into the sky, zw: those to the ground)
vec3 airRay = vec3(0.0);   // the ray airLight is asked about, in the scene's axes (airThrough and the dome set it; zero: no shadows)
float airCol(float h, float c) {
  float X = uAirGeo.x + h, k = sqrt(1.5708 * X), up = k / (k * abs(c) + 1.0) * exp(-h);
  float s = sqrt(max(1.0 - c * c, 0.0)), ht = h * s - uAirGeo.x * c * c / (1.0 + s);
  return c >= 0.0 ? up : max(2.0 * sqrt(1.5708 * X * s) * exp(-max(ht, -6.0)) - up, up);
}
// a ray from height hc: where the air begins (x) and ends (y) on it, whether it ends on the ground (z)
vec3 airSpan(float hc, float mu) {
  float X0 = uAirGeo.x, top = uAirGeo.z, r0 = X0 + hc, m2 = r0 * r0 * mu * mu;
  float dg = m2 - hc * (2.0 * X0 + hc), da = m2 + (top - hc) * (2.0 * X0 + top + hc);
  float hit = step(mu, 0.0) * step(0.0, dg), none = max(step(da, 0.0), step(top, hc) * step(0.0, mu));
  float t0 = hc > top ? -r0 * mu - sqrt(max(da, 0.0)) : 0.0, t1 = -r0 * mu + mix(sqrt(max(da, 0.0)), -sqrt(max(dg, 0.0)), hit);
  return vec3(t0, mix(t1, t0, none), hit);
}
// the point t along it: its height, the ray's cosine to the vertical there, the sun's
vec3 airAt(float hc, float mu, float cosv, float mus, float t) {
  float X0 = uAirGeo.x, r0 = X0 + hc, q = 2.0 * r0 * mu * t + t * t, r = sqrt(r0 * r0 + q);
  return vec3((hc * (2.0 * X0 + hc) + q) / (r + X0), (r0 * mu + t) / r, (r0 * mus + t * cosv) / r);
}
// the optical depth from a point h up to space along cosine c: the air's, and the thin layer's (1 / its cosine there a crossing)
vec4 airTau4(float h, float c) {
  float X0 = uAirGeo.x, hz = uAirOzone.w, r = X0 + h, Rz = X0 + hz, e = ((hz - h) * (2.0 * X0 + hz + h) + r * r * c * c) / (Rz * Rz);
  float f = inversesqrt(max(e, ${OZONE_EDGE.toFixed(3)})), below = 1.0 - smoothstep(hz - 0.5, hz + 0.5, h);
  float k = airCol(h, c);
  return vec4(uAirExt * k + uAirOzone.rgb * (below * f + (c >= 0.0 ? 0.0 : (1.0 - below) * 2.0 * f * smoothstep(0.0, ${(2 * OZONE_EDGE).toFixed(3)}, e))), k);
}
vec3 airTau(float h, float c) { return airTau4(h, c).rgb; }
vec4 airAlong4(vec3 p, float up) { return airTau4(p.x, up > 0.5 ? p.y : -p.y); }
vec3 airAlong(vec3 p, float up) { return airAlong4(p, up).rgb; }
// of the light a slab takes (T - Tn), the share its air took: the rest went into the absorbing layer
vec3 airShare(float dk, vec3 dtau) { return min(uAirExt * dk / max(dtau, 1e-9), 1.0); }
vec3 airPsi(float h, float mus) {
  vec2 uv = vec2((mus - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, sqrt(clamp(h / uAirGeo.z, 0.0, 1.0)));
  return texture2D(uAirPsi, clamp(uv, uAirTable.zw, 1.0 - uAirTable.zw)).rgb;
}
// where a sky table keeps a direction: x round from the sun (0..1 over half the circle), y its row; map: the
// table's own (uAirMap for the camera's; Air.skyAt(height).map for another height's)
vec2 airPlace(vec4 map, float mu, float cosv) {
  float mus = map.w, a = asin(clamp(mu, -1.0, 1.0)) + map.x;
  float phi = acos(clamp((cosv - mu * mus) / sqrt(max((1.0 - mu * mu) * (1.0 - mus * mus), 1e-12)), -1.0, 1.0));
  float w = clamp(sqrt(min(abs(a) / (a >= 0.0 ? map.y : map.z), 1.0)), 2.0 * uAirTable.y, 1.0 - 2.0 * uAirTable.y);
  return vec2(clamp(phi / 3.14159265, 2.0 * uAirTable.x, 1.0 - 2.0 * uAirTable.x), 0.5 + (a >= 0.0 ? 0.5 : -0.5) * w);
}
vec2 airWhere(float mu, float cosv) { return airPlace(uAirMap, mu, cosv); }
// a sky table's light at a place in it, for a ray whose cosine to the sun is cosv
// the haze's phase function per colour: Henyey-Greenstein's lobes (x^-1.5 as the cube of 1 / sqrt(x))
vec3 airHaze(float cosv) {
  vec3 g = uAirG, wide = inversesqrt(1.0 + g * g - 2.0 * g * cosv), haze = 0.25 * (1.0 - g * g) * wide * wide * wide;
  float n = uAirAureole.w, thin = inversesqrt(1.0 + n * n - 2.0 * n * cosv);
  return mix(haze, vec3(0.25 * (1.0 - n * n) * thin * thin * thin), uAirAureole.rgb);
}
vec3 airRead(sampler2D table, vec2 uv, float cosv) {
  vec3 once = texture2D(table, vec2(uv.x * 0.5, uv.y)).rgb, more = texture2D(table, vec2(0.5 + uv.x * 0.5, uv.y)).rgb;
  return uAirLight * (once * (uAirScatR * 0.1875 * (1.0 + cosv * cosv) + uAirScatM * airHaze(cosv)) + more * (uAirScatR + uAirScatM));
}
vec3 airFromTable(vec2 uv, float cosv) { return airRead(uAirView, uv, cosv); }
// the film look's dusk curve (nothing by day, and nothing in the other exposures)
float airDusked;           // what the last airLight's dusk curve left of the ray's light
vec3 airDusk(vec3 light) { airDusked = pow(max(dot(light, vec3(0.2126, 0.7152, 0.0722)) / uAirDusk.y, 1.0), -uAirDusk.x); return light * airDusked; }
vec2 airUv;                // where the last airLight read the table
// the stretch of a ray from height hc (cosine mu to the vertical) where something may cast a shadow: under the
// casters' top and within the reach, from x to y scale heights along it (none when y <= x); end: where the ray's air ends
vec2 airShadeSpan(float hc, float mu, float end) {
  float X0 = uAirGeo.x, top = uAirShade.y, m = (X0 + hc) * mu, c = (hc - top) * (2.0 * X0 + hc + top), d = m * m - c;
  if (hc >= top && (mu >= 0.0 || d <= 0.0)) return vec2(0.0, -1.0);
  float ta = hc >= top ? c / (-m + sqrt(d)) : 0.0, tb = c < 0.0 && m > 0.0 ? c / (-m - sqrt(d)) : -m + sqrt(max(d, 0.0));
  return vec2(ta, min(min(tb, end), ta + uAirShade.z));
}
// what passes along a ray from its start (c0, the air from there to space) to t
vec3 airPass(float hc, float mu, float cosv, float t, vec3 c0, float up) { return exp(-max((up > 0.5 ? 1.0 : -1.0) * (c0 - airAlong(airAt(hc, mu, cosv, uAirMap.w, t), up)), 0.0)); }
// of the whole light of airRay (cosine mu to the vertical, its air ending at end, on the ground when hit), the share made
// in the casters' shadows between the camera and e (all scale heights): kept half and all the way along the stretch
// they reach (in the square root of the distance), none at its start; rays into the sky and to the ground kept apart
float airShadowed(float hc, float mu, float end, float hit, float e) {
  vec2 s = airShadeSpan(hc, mu, end);
  vec4 c = uAirShadeView * vec4(airRay, 0.0);
  if (s.y <= s.x || e <= s.x || c.w <= 1e-6) return 0.0;
  vec4 S = texture2D(uAirShadow, clamp(c.xy / c.w * 0.5 + 0.5, 0.0, 1.0));
  vec2 kept = hit > 0.5 ? S.zw : S.xy;
  float u = 2.0 * sqrt((min(e, s.y) - s.x) / (s.y - s.x));
  return u < 1.0 ? kept.x * u : mix(kept.x, kept.y, u - 1.0);
}
// the air's light towards the camera along a ray (mu its cosine to the vertical, cosv to the sun) as far as
// dist (scale heights; negative: to the ground or to space); through: what passes; hit: it ends on the ground.
// With shadows in the air (compiled in by AIR_SHADOWS: Air.shadowsInto; on by uAirShade.x) and airRay set, the light
// made in the casters' shadows is taken away.
vec3 airLight(float mu, float cosv, float dist, out vec3 through, out float hit) {
  float hc = uAirGeo.y, mus = uAirMap.w;
  vec3 sp = airSpan(hc, mu);
  hit = sp.z; through = vec3(1.0); airUv = vec2(0.5, 0.75); airDusked = 1.0;
  if (sp.y <= sp.x) return vec3(0.0);
  vec3 p0 = airAt(hc, mu, cosv, mus, sp.x), p1 = airAt(hc, mu, cosv, mus, sp.y);
  float up = step(0.0, p0.y); vec3 c0 = airAlong(p0, up);
  vec3 whole = exp(-max((up > 0.5 ? 1.0 : -1.0) * (c0 - airAlong(p1, up)), 0.0));
  airUv = airWhere(mu, cosv);
  vec3 sky = airDusk(airFromTable(airUv, cosv)), light = sky + uAirGlow * (1.0 - whole);
  through = whole;
  if (dist >= 0.0 && dist < sp.y) {
    vec3 p = airAt(hc, mu, cosv, mus, max(dist, sp.x));
    through = exp(-max((up > 0.5 ? 1.0 : -1.0) * (c0 - airAlong(p, up)), 0.0));
    light *= (1.0 - through) / max(1.0 - whole, 1e-6);       // the share of the ray's light made in front of the point
    hit = 0.0;
  }
#ifdef AIR_SHADOWS
  // of the light made in front of the point (all of the ray's for the sky), the share in shadow; the colour kept
  if (uAirShade.x > 0.5 && dot(airRay, airRay) > 0.5) {
    bool near = dist >= 0.0 && dist < sp.y;
    float made = near ? (1.0 - through.g) / max(1.0 - whole.g, 1e-6) : 1.0;
    light *= 1.0 - min(airShadowed(hc, mu, sp.y, sp.z, near ? max(dist, sp.x) : sp.y) / max(made, 1e-6), 1.0);
  }
#endif
  return light;
}
// aerial perspective: a thing's colour seen through the air between the camera and it
vec3 airThrough(vec3 colour, vec3 toPoint) {
  float d = length(toPoint), hit; vec3 through, rd = toPoint / max(d, 1e-9);
  airRay = rd;
  vec3 light = airLight(dot(rd, uAirUp), dot(rd, uAirSun), d * uAirGeo.w, through, hit);
  return colour * through + light;
}
`;
const QUAD_VERT = "void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }";
// the sky table: every direction's light for this height and this sun. Left half: light scattered once,
// without its phase function (the picture multiplies it in, so the glow round the sun stays sharp);
// right half: light scattered more often
const VIEW_FRAG = /* glsl */`
${AIR_GLSL}
uniform vec2 uSize; uniform float uSpread;
void main() {
  vec2 uv = gl_FragCoord.xy / uSize;
  float more = step(0.5, uv.x), u = fract(uv.x * 2.0), w = abs(uv.y - 0.5) * 2.0, above = step(0.5, uv.y);
  float a = (above > 0.5 ? uAirMap.y : -uAirMap.z) * w * w, mu = sin(a - uAirMap.x), mus = uAirMap.w, hc = uAirGeo.y;
  float cosv = sqrt(max((1.0 - mu * mu) * (1.0 - mus * mus), 0.0)) * cos(u * 3.14159265) + mu * mus;
  vec3 sp = airSpan(hc, mu), sum = vec3(0.0), T = vec3(1.0);
  // a ray above the horizon ends in space, one below it on the ground, whatever rounding says
  if (above > 0.5 && sp.z > 0.5) sp = airSpan(hc, max(mu, -sqrt(max(hc * (2.0 * uAirGeo.x + hc), 0.0)) / (uAirGeo.x + hc) + 1e-6));
  if (sp.y > sp.x) {
    vec3 p0 = airAt(hc, mu, cosv, mus, sp.x);
    float up = step(0.0, p0.y), sign_ = up > 0.5 ? 1.0 : -1.0; vec4 c0 = airAlong4(p0, up), was = vec4(0.0);
    for (int i = 1; i <= STEPS; i++) {
      float f1 = float(i) / float(STEPS), fm = (float(i) - 0.5) / float(STEPS);
      vec3 p = airAt(hc, mu, cosv, mus, mix(sp.x, sp.y, f1 * (1.0 - uSpread + uSpread * f1)));
      vec3 m = airAt(hc, mu, cosv, mus, mix(sp.x, sp.y, fm * (1.0 - uSpread + uSpread * fm)));
      vec4 now = max(sign_ * (c0 - airAlong4(p, up)), 0.0);
      vec3 Tn = exp(-now.rgb);
      vec3 src = more > 0.5 ? airPsi(max(m.x, 0.0), m.z) : exp(-airTau(max(m.x, 0.0), m.z));
      sum += (T - Tn) * airShare(now.a - was.a, now.rgb - was.rgb) * src; T = Tn; was = now;
    }
  }
  gl_FragColor = vec4(sum, 1.0);
}`;
// the table of light scattered more than once: for a height and a sun, the light a point gets second-hand
// from all round (one bounce in the air, or off the ground), over what a point passes on of such light
const PSI_FRAG = /* glsl */`
${AIR_GLSL}
uniform vec2 uSize; uniform vec3 uGround;
void main() {
  vec2 uv = gl_FragCoord.xy / uSize;
  float hc = uAirGeo.z * uv.y * uv.y, mus = ${PSI_TABLE.sunFrom.toFixed(2)} + ${(1 - PSI_TABLE.sunFrom).toFixed(2)} * uv.x, sx = sqrt(max(1.0 - mus * mus, 0.0));
  vec3 L = vec3(0.0), F = vec3(0.0), scat = uAirScatR + uAirScatM;
  for (int a = 0; a < ELEVS; a++) {
    // the cosine to the vertical goes as x |x|: many directions near the level, each weighing its share of the sphere
    float x = 2.0 * (float(a) + 0.5) / float(ELEVS) - 1.0, mu = x * abs(x), w = abs(x) * 2.0 / float(ELEVS * DIRS);
    for (int b = 0; b < DIRS; b++) {
      float cosv = sqrt(1.0 - mu * mu) * cos(6.2831853 * (float(b) + 0.5) / float(DIRS)) * sx + mu * mus;
      vec3 sp = airSpan(hc, mu), T = vec3(1.0);
      float live = step(sp.x, sp.y - 1e-6);
      vec3 p0 = airAt(hc, mu, cosv, mus, sp.x);
      float up = step(0.0, p0.y), sign_ = up > 0.5 ? 1.0 : -1.0; vec4 c0 = airAlong4(p0, up), was = vec4(0.0);
      for (int i = 1; i <= STEPS; i++) {
        vec3 p = airAt(hc, mu, cosv, mus, mix(sp.x, sp.y, float(i) / float(STEPS))), m = airAt(hc, mu, cosv, mus, mix(sp.x, sp.y, (float(i) - 0.5) / float(STEPS)));
        vec4 now = max(sign_ * (c0 - airAlong4(p, up)), 0.0);
        vec3 Tn = exp(-now.rgb), share = w * (T - Tn) * airShare(now.a - was.a, now.rgb - was.rgb) * scat * live;
        L += share * 0.25 * exp(-airTau(max(m.x, 0.0), m.z)); F += share; T = Tn; was = now;
      }
      vec3 g = airAt(hc, mu, cosv, mus, sp.y);
      L += w * live * sp.z * T * uGround * max(g.z, 0.0) * exp(-airTau(0.0, g.z));
    }
  }
  gl_FragColor = vec4(L / (1.0 - F), 1.0);
}`;
const TONE = THREE.ShaderChunk.tonemapping_pars_fragment.replace("uniform float toneMappingExposure;", "const float toneMappingExposure = 1.0;");
/** What a shader drawing itself straight to the canvas beside the dome needs to end up in the same picture:
 * `vec3 display(vec3 linear)` (the dome's tone curve and the display's encoding) and `float dither(vec2 pixel)`. */
export const DISPLAY_GLSL = /* glsl */`
${TONE}
float dither(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }
vec3 display(vec3 c) {
  c = clamp(ACESFilmicToneMapping(max(c, 0.0)), 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
`;
const DOME_VERT = "varying vec3 vD; void main() { vD = position; gl_Position = projectionMatrix * vec4(mat3(viewMatrix) * position, 1.0); gl_Position.z = 0.0; }";
// the picture: the air on each pixel's ray, the plain ground under the horizon, the sun's disc
const DOME_FRAG = /* glsl */`
${AIR_GLSL}
${DISPLAY_GLSL}
varying vec3 vD;
uniform sampler2D uAmbient;
uniform vec3 uGround, uLimb;
uniform vec4 uSun;          // the disc's angular radius, its brightness over the air's light (camera) or 0 (film), the cap, the film look's curve
uniform float uPix, uDisplay, uGroundOn, uGrain, uCovered;
void main() {
  vec3 rd = normalize(vD), through; float hit;
  float mu = dot(rd, uAirUp), cosv = dot(rd, uAirSun), mus = uAirMap.w, hc = uAirGeo.y;
  if (uCovered > 0.5 && asin(clamp(mu, -1.0, 1.0)) + uAirMap.x < -3.0 * uPix) discard;      // something of the scene hides all that is under the horizon
  airRay = rd;
  vec3 col = airLight(mu, cosv, -1.0, through, hit);
  float alpha = 1.0 - dot(through, vec3(0.3333));
  // the ground: a matt ball of one colour under the sun after the air and under the sky; its edge a pixel soft
  // (the pixel under the horizon is part ground, part the sky just over the horizon at its bearing)
  float a = asin(clamp(mu, -1.0, 1.0)) + uAirMap.x, cover = clamp(-a / uPix, 0.0, 1.0);
  float r0 = uAirGeo.x + hc, tg = -r0 * mu - sqrt(max(r0 * r0 * mu * mu - hc * (2.0 * uAirGeo.x + hc), 0.0));
  float sunG = airAt(hc, mu, cosv, mus, max(tg, 0.0)).z;
  vec3 ambient = texture2D(uAmbient, vec2(clamp((sunG - (${PSI_TABLE.sunFrom.toFixed(2)})) / ${(1 - PSI_TABLE.sunFrom).toFixed(2)}, 0.01, 0.99), 0.5)).rgb;
  vec3 ground = uGround * uAirLight * (exp(-airTau(0.0, sunG)) * max(sunG, 0.0) + ambient);
  vec3 over = airFromTable(vec2(airUv.x, 0.5 + uAirTable.y), cosv) * airDusked;
  col = mix(col, mix(over, col + ground * through, cover), uGroundOn * step(a, 0.0));
  alpha = mix(alpha, 1.0, cover * uGroundOn);
  // the sun: a disc darker and redder towards its limb, seen through the air on the ray
  float ang = atan(length(cross(rd, uAirSun)), cosv), rim = clamp(ang / uSun.x, 0.0, 1.0);
  float disc = (1.0 - smoothstep(uSun.x - 0.6 * uPix, uSun.x + 0.6 * uPix, ang)) * (1.0 - cover);
  float most = max(max(through.r, through.g), max(through.b, 1e-9)), tint = max(max(uAirLight.r, uAirLight.g), max(uAirLight.b, 1e-9));
  float bright = uSun.y > 0.0 ? min(uSun.y * most * tint, uSun.z) : mix(1.6, uSun.z, pow(most, uSun.w));
  vec3 sunColour = (through / most) * (uAirLight / tint);
  // the disc stands in front of the sky's glow (added to it, a low red sun would wash out to the sky's own pale orange)
  col = mix(col, max(col, vec3(0.0)) * 0.15 + sunColour * bright * (1.0 - uLimb * (1.0 - sqrt(1.0 - rim * rim))), disc);
  // a soft bloom round the disc, in its colour, never brighter than a few whites: a lens's, not the air's
  float off = max(ang - uSun.x, 0.0) / uSun.x;
  col += (1.0 - disc) * (1.0 - cover) * step(1e-6, uSun.x) * sunColour * min(bright, 4.0) * (0.3 / (1.0 + off + off * off) + 0.05 / (1.0 + off * off));
  alpha = max(alpha, disc);
  float n = dither(gl_FragCoord.xy) + dither(gl_FragCoord.xy * 1.7 + 91.0) - 1.0;
  // straight to the canvas what is behind (the stars) is added after the tone curve: it is let through as
  // much less as the curve would have flattened it over a bright sky
  float seen = 1.0 + 6.0 * dot(col, vec3(0.2126, 0.7152, 0.0722));
  // dither: two display codes, one where the picture is bright (an encoder flattens a dim gradient into steps otherwise)
  vec3 shown = display(col);
  float grain = mix(uGrain, 1.0, smoothstep(0.45, 0.8, dot(shown, vec3(0.3333))));
  gl_FragColor = uDisplay < 0.5 ? vec4(max(col * (1.0 + n * 0.004), 0.0), alpha) : vec4(shown + n * grain / 255.0, 1.0 - (1.0 - alpha) / (seen * seen));
}`;
/** How much darker the sun's limb is than its middle, per colour (red least). */
export const LIMB = Object.freeze([0.5, 0.62, 0.76]);

// ---------- shadows in the air ----------
/** Shadows in the air (`shadows` option): `reach` (metres along a ray from the camera, or from where it comes under the
 * casters' top), `share` (the picture of the shadows' size against the canvas's), `steps` along each of its rays (a
 * multiple of four). `quality` "fast" halves the steps. */
export const SHADOWS = Object.freeze({reach: 200000, share: 0.25, steps: 24});
const SHADOW_KEYS = Object.keys(SHADOWS);
/** The stretch of a ray where casters reach (the GLSL's airShadeSpan): from `height` metres, cosine `mu` to the vertical,
 * under `top` metres and within `reach` metres, ending at `end` metres (the ground, the top of the air). [from, to] in
 * metres; none when to <= from. Pure. */
export function shadeSpan(radius, height, mu, top, reach, end = Infinity) {
  const m = (radius + height) * mu, c = (height - top) * (2 * radius + height + top), d = m * m - c;
  if (height >= top && (mu >= 0 || d <= 0)) return [0, -1];
  const ta = height >= top ? c / (-m + Math.sqrt(d)) : 0, tb = c < 0 && m > 0 ? c / (-m - Math.sqrt(d)) : -m + Math.sqrt(Math.max(d, 0));
  return [ta, Math.min(tb, end, ta + reach)];
}
/** The share in shadow read from the two kept along a stretch (the GLSL's airShadowed): `S` [half way, all the way],
 * `f` how far along the stretch (0 to 1, in distance); none at its start. Pure. */
export function shadeShareAt(S, f) {
  const u = 2 * Math.sqrt(clamp(f, 0, 1));
  return u < 1 ? S[0] * u : S[0] + (S[1] - S[0]) * (u - 1);
}
/** The shadow pass's sum for one ray, in JavaScript (its twin and the tests' reference): the air's light (green) made in
 * the shadows along the stretch the casters reach, by `sun(w, h)` and `sky(w, h)` (the share of the sun's light and of
 * the sky's that reaches a point `w` metres from the camera, [x, up, z] by the vertical at the camera, `h` metres up), as
 * a share of the ray's whole light (skyLight's), at half and all of the stretch (half in the square root of the
 * distance). `ray`: {height (metres), mu, cosv, mus}; `top`, `reach` metres; `steps`; `jitter` 0 to 1; `diffuse`: the
 * share of the sun's light a shadow's caster passes on all round (a cloud's); `dir`: the ray's direction [x, up, z]
 * (default in the plane of the vertical); `psi`: a psiTable. Returns [half way, all the way]. Pure. */
export function shadowShares(model, {height, mu, cosv, mus}, {top, reach = SHADOWS.reach, steps = SHADOWS.steps, jitter = 0.5, sun = () => 1, sky = () => 1, diffuse = 0, dir = null, psi = null} = {}) {
  const X0 = model.X0, H = model.H, hc = height / H, sp = span(X0, hc, mu), out = [0, 0];
  if (sp.t1 <= sp.t0) return out;
  const [a, b] = shadeSpan(X0, hc, mu, top / H, reach / H, sp.t1);
  if (b <= a) return out;
  const table = psi ?? psiOf(model), p0 = at(X0, hc, mu, cosv, mus, sp.t0), up = p0[1] >= 0, c0 = along(model, p0, up);
  const pass = (t) => Math.exp(-Math.max((up ? 1 : -1) * (c0[1] - along(model, at(X0, hc, mu, cosv, mus, t), up)[1]), 0));
  const g = model.forward[1], n = model.aureoleForward, A = model.aureole[1], e = model.ext[1];
  const once = (model.rayleigh[1] * phaseRayleigh(cosv) + model.haze[1] * ((1 - A) * phaseHaze(g, cosv) + A * phaseHaze(n, cosv))) / e, more = (model.rayleigh[1] + model.haze[1]) / e;
  const d = dir ?? [Math.sqrt(Math.max(1 - mu * mu, 0)), mu, 0], L = b - a;
  const whole = Math.max(skyLight(model, height, mu, cosv, mus, {steps: 32, psi: table}).light[1], 1e-30);
  let prev = pass(a), lost = 0;
  for (let i = 0; i < steps; i++) {
    const u1 = (i + 1) / steps, us = (i + jitter) / steps, t1 = a + L * u1 * u1, ts = a + L * us * us, T1 = pass(t1), p = at(X0, hc, mu, cosv, mus, ts), hh = Math.max(p[0], 0);
    const dT = Math.max(prev - T1, 0); prev = T1;
    const sunT = Math.exp(-tau(model, hh, p[2])[1]), x = dT * once * sunT, y = dT * more * table.at(hh, p[2])[1];
    const w = d.map((v) => v * ts * H), vs = sun(w, hh * H), va = sky(w, hh * H);
    lost += (1 - vs) * x - diffuse * (1 - vs) * 0.25 * dT * more * sunT + (1 - va) * y;
    if (i + 1 === steps / 2) out[0] = Math.max(lost, 0) / whole;
    if (i + 1 === steps) out[1] = Math.max(lost, 0) / whole;
  }
  return out;
}
const SHADE_VERT = /* glsl */`
uniform mat4 uShadeCam; uniform vec4 uShadeProj;
varying vec3 vDir;
void main() {
  vDir = mat3(uShadeCam) * vec3((position.x + uShadeProj.z) * uShadeProj.x, (position.y + uShadeProj.w) * uShadeProj.y, -1.0);
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;
// the shadows' picture: along each of its rays, the light made in the casters' shadows in the stretch they reach, as a
// share of the ray's whole light, kept half and all the way along (in the square root of the distance).
// Four neighbouring pixels walk their steps a quarter of a step apart (the blur after it takes their mean)
const SHADE_FRAG = (casters) => /* glsl */`
${AIR_GLSL}
${casters.map((c) => c.glsl).join("\n")}
// the share of the sun's light that reaches a point (x), and of the sun's light that a caster's shadow passes on to it all round (y: a cloud's diffuse light, unless something else hides the sun)
vec2 airCastSun(vec3 w, float h) {
${casters.map((c) => `  float s_${c.name} = ${c.name}Sun(w, h);`).join("\n")}
  float all_ = 1.0${casters.map((c) => ` * s_${c.name}`).join("")};
  return vec2(all_, 0.0${casters.filter((c) => c.diffuse > 0).map((c) => ` + ${c.diffuse.toFixed(4)} * (1.0 - s_${c.name})${casters.filter((x) => x !== c).map((x) => ` * s_${x.name}`).join("")}`).join("")});
}
float airCastSky(vec3 w, float h) { return 1.0${casters.map((c) => ` * ${c.name}Sky(w, h)`).join("")}; }
uniform float uShadeH;      // metres a scale height
varying vec3 vDir;
void main() {
  vec3 rd = normalize(vDir);
  float mu = dot(rd, uAirUp), cosv = dot(rd, uAirSun), hc = uAirGeo.y, mus = uAirMap.w;
  vec3 sp = airSpan(hc, mu);
  vec2 s = airShadeSpan(hc, mu, sp.y);
  if (sp.y <= sp.x || s.y <= s.x) { gl_FragColor = vec4(0.0, 0.0, sp.z, 1.0); return; }
  vec3 p0 = airAt(hc, mu, cosv, mus, sp.x);
  float up = step(0.0, p0.y); vec3 c0 = airAlong(p0, up);
  // the phase functions (green): once-scattered light, and light scattered more often (even all round)
  float g = uAirG.g, wide = inversesqrt(1.0 + g * g - 2.0 * g * cosv), n = uAirAureole.w, thin = inversesqrt(1.0 + n * n - 2.0 * n * cosv);
  float haze = mix(0.25 * (1.0 - g * g) * wide * wide * wide, 0.25 * (1.0 - n * n) * thin * thin * thin, uAirAureole.g);
  float once = uAirScatR.g * 0.1875 * (1.0 + cosv * cosv) + uAirScatM.g * haze, more = uAirScatR.g + uAirScatM.g;
  vec2 cell = mod(floor(gl_FragCoord.xy), 2.0);
  // the whole ray's light (green, for a unit of sunlight) as the sky table has it
  float whole = max(airFromTable(airWhere(mu, cosv), cosv).g / max(uAirLight.g, 1e-30), 1e-30);
  float j = mod(2.0 * cell.x + 3.0 * cell.y, 4.0) / 4.0 + 0.125, L = s.y - s.x, prev = airPass(hc, mu, cosv, s.x, c0, up).g, lost = 0.0;
  vec2 kept = vec2(0.0);
  for (int i = 0; i < STEPS; i++) {
    float u1 = float(i + 1) / float(STEPS), us = (float(i) + j) / float(STEPS), ts = s.x + L * us * us;
    float T1 = airPass(hc, mu, cosv, s.x + L * u1 * u1, c0, up).g, dT = max(prev - T1, 0.0);
    prev = T1;
    vec3 p = airAt(hc, mu, cosv, mus, ts);
    float hh = max(p.x, 0.0), sunT = exp(-airTau(hh, p.z).g), a = dT * once * sunT, b = dT * more * airPsi(hh, p.z).g;
    vec3 w = rd * (ts * uShadeH);
    float hm = hh * uShadeH;
    vec2 v = airCastSun(w, hm);
    lost += (1.0 - v.x) * a - v.y * 0.25 * dT * more * sunT + (1.0 - airCastSky(w, hm)) * b;
    if (i + 1 == STEPS / 2) kept.x = max(lost, 0.0) / whole;
  }
  kept.y = max(lost, 0.0) / whole;
  // z: the ray ends on the ground (the blur keeps such rays apart from those into the sky)
  gl_FragColor = vec4(kept, sp.z, 1.0);
}`;
// the mean of each pixel's 3 x 3 neighbours, weighted 1-2-1 (the four walks' phases even), of the rays into the sky (xy)
// and of those to the ground (zw) apart: a pixel next to the horizon also keeps the other side's, so the picture read
// between pixels never mixes the two
const BLUR_FRAG = /* glsl */`
uniform sampler2D uShadeRaw;
void main() {
  ivec2 at = ivec2(gl_FragCoord.xy), most = textureSize(uShadeRaw, 0) - 1;
  vec4 own = texelFetch(uShadeRaw, at, 0), sum = vec4(0.0); vec2 w = vec2(0.0);
  for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
    vec4 v = texelFetch(uShadeRaw, clamp(at + ivec2(i, j), ivec2(0), most), 0);
    float k = float((2 - abs(i)) * (2 - abs(j))), g = step(0.5, v.z);
    sum += k * vec4(v.xy * (1.0 - g), v.xy * g); w += k * vec2(1.0 - g, g);
  }
  vec2 sky = w.x > 0.0 ? sum.xy / w.x : own.xy, ground = w.y > 0.0 ? sum.zw / w.y : own.xy;
  gl_FragColor = vec4(sky, ground);
}`;

const OPTIONS = Object.freeze({sun: Object.freeze([0.35, 0.5, -0.79]), color: Object.freeze([1, 1, 1]), light: 1, sunSize: SUN_SIZE, disc: true, ground: true, exposure: "film", ev: 0,
  quality: "standard", unit: 1, center: null, stars: null, scene: null, over: false, shadows: true});
const half = (data) => Uint16Array.from(data, (x) => THREE.DataUtils.toHalfFloat(x));
// the shadows' picture when there are none: nothing in shadow
const NO_SHADOW = new THREE.DataTexture(new Uint8Array(4), 1, 1, THREE.RGBAFormat);
NO_SHADOW.needsUpdate = true;
// a sky table's rows for a height (scale heights): the horizon's dip, the span from the horizon up to the zenith (or
// only to the top of the air when the height is over it) and down to the nadir, and whether the height is in the air
function rowSpans(m, hc) {
  const dip = Math.acos(m.X0 / (m.X0 + hc)), inside = hc < TOP;
  return [dip, inside ? Math.PI / 2 + dip : 1.03 * (dip - Math.acos(Math.min(1, (m.X0 + TOP) / (m.X0 + hc)))), Math.max(Math.PI / 2 - dip, 1e-3), inside];
}

/** The air round the camera: `object` (the dome: add it to the scene), `update(t, {camera, sun, center})`,
 * `haze(material)`, `uniforms` and AIR_GLSL for shaders of your own, `light` ({sun, sky}: lights for
 * ordinary meshes), `state` (height, the sun's elevation, ev, the sun's light and the sky's as colours). */
export class Air {
  /** `renderer`: the page's; `what`: a name (PRESETS, a world or an air of vidgen/space-bodies), a body
   * made by `planet()`, or {world | air, radius, forward, ozone, ozoneHeight, ground}; `extra`: those, and `sun` (the direction towards it), `color`
   * and `light` (the sunlight's colour and strength before the air), `sunSize` (degrees), `disc` (draw the
   * sun), `ground` (false: no plain ground; the dome then only lays the air over what is behind it),
   * `exposure` ("film", "camera", "auto") with `ev`, `quality`, `unit` (metres a scene unit), `center` (the
   * world's middle in the scene: [x, y, z], a Vector3 or an Object3D read at every update; default the
   * radius under the origin), `stars` (a vidgen/space-sky sky: dimmed by day), `scene` (the lights are
   * added to it), `over` (draw the dome after everything, as vidgen/space-scale's overlays), `shadows` (true: what
   * casts a shadow into the air (vidgen/space-clouds' decks, vidgen/space-land's ground; `addCaster`) darkens the air
   * in its shadow (light shafts, the dim air under a closed deck, mountains' shadows in the haze); false: none;
   * or {reach, share, steps}: see SHADOWS). */
  constructor(renderer, what = "earth", extra = {}) {
    if (!renderer || !renderer.isWebGLRenderer) throw fail("air(renderer, what, options): the first argument must be the page's THREE.WebGLRenderer");
    known("the third argument", extra, [...AIR_OPTIONS, ...Object.keys(OPTIONS)]);
    const mine = {}, airs = {};
    for (const [k, v] of Object.entries(extra)) (k in OPTIONS && !(k === "ground" && typeof v !== "boolean") ? mine : airs)[k] = v;
    const o = this.options = {...OPTIONS, ...mine}, m = this.model = airOf(what, airs);
    choice("exposure", o.exposure, EXPOSURES); choice("quality", o.quality, QUALITIES);
    number("light", o.light, 0, 100); number("sunSize", o.sunSize, 0.01, 20); number("unit", o.unit, 1e-9, 1e9);
    if (typeof o.ev !== "function") number("ev", o.ev, -30, 30);
    if (o.shadows !== true && o.shadows !== false) {
      known("shadows", o.shadows, SHADOW_KEYS);
      const sh = {...SHADOWS, ...o.shadows};
      number("shadows.reach (metres)", sh.reach, 100, 1e7); number("shadows.share", sh.share, 0.05, 1);
      if (!Number.isInteger(sh.steps) || sh.steps < 4 || sh.steps > 128 || sh.steps % 4 !== 0) throw fail(`shadows.steps must be a multiple of 4 from 4 to 128, got ${JSON.stringify(sh.steps)}`);
    }
    o.color = linearColor("color", o.color);
    this.renderer = renderer;
    this.ambient = ambientTable(m);
    this._day = this.ambient.zenithAt(Math.sin(25 * RAD));
    const [across, rows, steps] = VIEW_TABLES[o.quality], v3 = (a) => new THREE.Vector3(...a);
    const scat = (list) => v3(list.map((x, i) => x / m.ext[i]));
    this.psi = this._bakePsi();
    const kind = {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: false, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping};
    this.view = new THREE.WebGLRenderTarget(across * 2, rows * 2, kind);
    this.ambientTexture = new THREE.DataTexture(half(Array.from({length: this.ambient.n * 4}, (_, i) => (i % 4 === 3 ? 1 : this.ambient.data[(i >> 2) * 3 + (i % 4)]))), this.ambient.n, 1, THREE.RGBAFormat, THREE.HalfFloatType);
    this.ambientTexture.minFilter = this.ambientTexture.magFilter = THREE.LinearFilter; this.ambientTexture.needsUpdate = true;
    /** The uniforms AIR_GLSL declares: give these same objects to a shader of your own. */
    this.uniforms = {uAirGeo: {value: new THREE.Vector4(m.X0, 0, TOP, o.unit / m.H)}, uAirMap: {value: new THREE.Vector4(0, 1.5708, 1.5708, 0.5)},
      uAirTable: {value: new THREE.Vector4(0.25 / across, 0.25 / rows, 0.5 / PSI_TABLE.suns, 0.5 / PSI_TABLE.heights)},
      uAirUp: {value: new THREE.Vector3(0, 1, 0)}, uAirSun: {value: new THREE.Vector3(0, 1, 0)}, uAirExt: {value: v3(m.ext)}, uAirScatR: {value: scat(m.rayleigh)}, uAirScatM: {value: scat(m.haze)},
      uAirG: {value: v3(m.forward)}, uAirLight: {value: new THREE.Vector3(1, 1, 1)}, uAirGlow: {value: v3(m.glow)}, uAirOzone: {value: new THREE.Vector4(...m.ozone, m.hz)},
      uAirAureole: {value: new THREE.Vector4(...m.aureole, m.aureoleForward)}, uAirDusk: {value: new THREE.Vector2(0, DUSK_KNEE)}, uAirView: {value: this.view.texture}, uAirPsi: {value: this.psi.texture},
      uAirShade: {value: new THREE.Vector4(0, 0, 0, 0)}, uAirShadeView: {value: new THREE.Matrix4()}, uAirShadow: {value: NO_SHADOW}};
    this._quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({uniforms: {...this.uniforms, uSize: {value: new THREE.Vector2(across * 2, rows * 2)}, uSpread: {value: 0.5}},
      defines: {STEPS: steps}, vertexShader: QUAD_VERT, fragmentShader: VIEW_FRAG, depthTest: false, depthWrite: false, toneMapped: false}));
    this._quad.frustumCulled = false;
    this._scene = new THREE.Scene(); this._scene.add(this._quad); this._camera = new THREE.Camera();
    this.material = new THREE.ShaderMaterial({uniforms: {...this.uniforms, uAmbient: {value: this.ambientTexture}, uGround: {value: v3(m.ground)}, uLimb: {value: v3(LIMB)},
      uSun: {value: new THREE.Vector4(o.sunSize * RAD, 0, BURN, 1.6)}, uPix: {value: 0.002}, uDisplay: {value: 0}, uGroundOn: {value: o.ground ? 1 : 0}, uGrain: {value: 2}, uCovered: {value: 0}},
      vertexShader: DOME_VERT, fragmentShader: DOME_FRAG, side: THREE.BackSide, depthTest: false, depthWrite: false, toneMapped: false, fog: false, transparent: false,
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor});
    this.geometry = new THREE.BoxGeometry(2, 2, 2);
    /** The dome: the sky all round the camera (it follows any camera), drawn after a vidgen/space-sky sky and before the scene. */
    this.object = new THREE.Mesh(this.geometry, this.material);
    this.object.name = `air ${m.name ?? ""}`.trim(); this.object.frustumCulled = false; this.object.renderOrder = -900;
    if (o.over) { this.object.userData.overlay = true; this.object.renderOrder = 900; this.material.transparent = true; }
    const view = new THREE.Vector4();
    this.object.onBeforeRender = (r, scene, camera) => {
      r.getCurrentViewport(view);
      const u = this.material.uniforms;
      u.uPix.value = 2 * Math.tan((camera.fov ?? 40) * RAD / 2) / view.w;
      u.uDisplay.value = r.getRenderTarget() === null ? 1 : 0;
      u.uSun.value.x = Math.max(o.sunSize * RAD, 0.8 * u.uPix.value) * (o.disc ? 1 : 0);
      this.material.uniformsNeedUpdate = true;
      this.drawShadows();
    };
    /** Lights for ordinary meshes: `sun` (a THREE.DirectionalLight: the sun after the air) and `sky` (a THREE.HemisphereLight: the sky from above, the lit ground from below). */
    this.light = {sun: new THREE.DirectionalLight(0xffffff, Math.PI), sky: new THREE.HemisphereLight(0xffffff, 0x000000, Math.PI)};
    if (o.scene) o.scene.add(this.light.sun, this.light.sun.target, this.light.sky);
    this.sun = new THREE.Vector3(...(Array.isArray(o.sun) ? o.sun : [o.sun.x, o.sun.y, o.sun.z])).normalize();
    this.stars = o.stars;
    this._starBase = this.stars && this.stars.skyMaterial ? this.stars.skyMaterial.uniforms.uGain.value : 1;
    this._drawn = null; this._hazed = new Set();
    /** What casts shadows into the air (see addCaster). */
    this.casters = []; this._shade = null; this._shadeDirty = true; this._eye = null; this._into = new Set();
    this.shadowsInto(this.material);
    /** What the last update found: `height` (m), `elevation` (the sun's, degrees over the level), `ev`, `gain`, `stars` (their share), `sunlight` and `ambient` (the sun's and the sky's light on a thing at the camera, linear colours times the gain), `inside` (the camera is in the air), `up` (the vertical at the camera) and `center` (the world's middle, scene units). */
    this.state = {height: 0, elevation: 0, ev: 0, gain: 1, stars: 1, sunlight: [1, 1, 1], ambient: [0, 0, 0], inside: true, up: [0, 1, 0], center: [0, 0, 0]};
    this.material.addEventListener("dispose", () => { this.view.dispose(); this.psi.dispose(); this.ambientTexture.dispose(); this._quad.material.dispose(); this._quad.geometry.dispose(); this._freeShade(); });
    this.update(0);
  }

  // the table of light scattered more than once: baked once, kept by vidgen between pages
  _bakePsi() {
    const m = this.model, r = this.renderer, {suns, heights, directions, elevations, steps} = PSI_TABLE;
    const inputs = {version: VERSION, table: PSI_TABLE, X0: m.X0, rayleigh: m.rayleigh, haze: m.haze, absorb: m.absorb, ozone: m.ozone, hz: m.hz, ground: m.ground};
    const targets = () => [new THREE.WebGLRenderTarget(suns, heights, {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: false})];
    const draw = ([target]) => {
      const v3 = (a) => new THREE.Vector3(...a), scat = (list) => v3(list.map((x, i) => x / m.ext[i]));
      const material = new THREE.ShaderMaterial({defines: {DIRS: directions, ELEVS: elevations, STEPS: steps}, vertexShader: QUAD_VERT, fragmentShader: PSI_FRAG, depthTest: false, depthWrite: false, toneMapped: false,
        uniforms: {uAirGeo: {value: new THREE.Vector4(m.X0, 0, TOP, 1)}, uAirMap: {value: new THREE.Vector4()}, uAirTable: {value: new THREE.Vector4()}, uAirUp: {value: v3([0, 1, 0])}, uAirSun: {value: v3([0, 1, 0])},
          uAirExt: {value: v3(m.ext)}, uAirScatR: {value: scat(m.rayleigh)}, uAirScatM: {value: scat(m.haze)}, uAirG: {value: v3(m.forward)}, uAirLight: {value: v3([1, 1, 1])}, uAirGlow: {value: v3([0, 0, 0])}, uAirOzone: {value: new THREE.Vector4(...m.ozone, m.hz)},
          uAirAureole: {value: new THREE.Vector4(0, 0, 0, 0.9)}, uAirDusk: {value: new THREE.Vector2(0, DUSK_KNEE)}, uAirView: {value: null}, uAirPsi: {value: null}, uSize: {value: new THREE.Vector2(suns, heights)}, uGround: {value: v3(m.ground)}}});
      const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material), scene = new THREE.Scene(), before = r.getRenderTarget();
      quad.frustumCulled = false; scene.add(quad);
      r.setRenderTarget(target); r.render(scene, new THREE.Camera()); r.setRenderTarget(before);
      material.dispose(); quad.geometry.dispose();
    };
    return baked(r, "space-air/psi", inputs, {targets, draw})[0];
  }

  /** Lay the air between the camera and every pixel of `material` (a three.js material, or a list): far
   * things take the sky's colour and lose contrast. Call once per material; returns it. A ShaderMaterial
   * of your own includes AIR_GLSL and `air.uniforms` instead and calls airThrough itself. */
  haze(material) {
    if (Array.isArray(material)) { material.forEach((x) => this.haze(x)); return material; }
    if (!material || !material.isMaterial) throw fail("haze(material): a THREE.Material, or a list of them");
    if (material.isShaderMaterial) throw fail("haze(material): a ShaderMaterial of your own includes AIR_GLSL, takes air.uniforms and calls airThrough(colour, toPoint) itself");
    if (this._hazed.has(material)) return material;
    this._hazed.add(material);
    this.shadowsInto(material);
    const earlier = material.onBeforeCompile, key = material.customProgramCacheKey.bind(material);
    material.onBeforeCompile = (shader, renderer) => {
      if (earlier) earlier.call(material, shader, renderer);
      Object.assign(shader.uniforms, this.uniforms);
      shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vAirTo;")
        .replace("#include <project_vertex>", "#include <project_vertex>\n{ vec4 airAt4 = vec4(transformed, 1.0);\n#ifdef USE_INSTANCING\nairAt4 = instanceMatrix * airAt4;\n#endif\nvAirTo = (modelMatrix * airAt4).xyz - cameraPosition; }");
      shader.fragmentShader = shader.fragmentShader.replace("#include <common>", `#include <common>\nvarying vec3 vAirTo;\n${AIR_GLSL}`)
        .replace("#include <tonemapping_fragment>", "gl_FragColor.rgb = airThrough(gl_FragColor.rgb, vAirTo);\n#include <tonemapping_fragment>");
    };
    material.customProgramCacheKey = () => `${key()}|vidgen-air`;
    material.needsUpdate = true;
    return material;
  }

  /** Let something cast shadows into the air: `caster` is {name (a GLSL name, unique), glsl (defines `float <name>Sun(vec3 w,
   * float h)` and `float <name>Sky(vec3 w, float h)`: the share of the sun's light and of the sky's that reaches a point `w`
   * metres from the camera along the scene's axes, `h` metres over the world's sphere), uniforms, top (metres: nothing
   * casts a shadow on air above it), diffuse (the share of the sun's light it hides that it passes on all round, as a
   * cloud does: 0 to 1, default 0)}. vidgen/space-clouds and vidgen/space-land add themselves (unless `shadows: false`).
   * Returns the air. */
  addCaster(caster) {
    known("addCaster", caster, ["name", "glsl", "uniforms", "top", "diffuse"]);
    if (typeof caster.name !== "string" || !/^[a-z][A-Za-z0-9]*$/.test(caster.name) || this.casters.some((c) => c.name === caster.name)) throw fail(`addCaster: name must be a new GLSL name (letters and digits, a small letter first), got ${JSON.stringify(caster.name)}`);
    if (typeof caster.glsl !== "string" || !caster.glsl.includes(`${caster.name}Sun(`) || !caster.glsl.includes(`${caster.name}Sky(`)) throw fail(`addCaster: glsl must define float ${caster.name}Sun(vec3 w, float h) and float ${caster.name}Sky(vec3 w, float h)`);
    number("addCaster: top (metres)", caster.top, -1e5, 1e7); number("addCaster: diffuse", caster.diffuse ?? 0, 0, 1);
    this.casters.push({name: caster.name, glsl: caster.glsl, uniforms: caster.uniforms ?? {}, top: caster.top, diffuse: caster.diffuse ?? 0});
    this._freeShade(); this._shadeDirty = true;
    for (const material of this._into) material.needsUpdate = true;
    return this;
  }
  /** Whether the air draws shadows (the option `shadows` is not false). */
  get shadowsOn() { return this.options.shadows !== false; }
  /** Let the shadows in the air reach a ShaderMaterial of your own that includes AIR_GLSL and calls airThrough or
   * airLight (vidgen's modules call it for theirs; `haze` does it for you): the shadows' code is compiled into its
   * shader only while the air has shadows and something casting them (a shader without it costs nothing more).
   * Returns the material. */
  shadowsInto(material) {
    if (!material || !material.isMaterial) throw fail("shadowsInto(material): a THREE.Material");
    if (this._into.has(material)) return material;
    this._into.add(material);
    const earlier = material.onBeforeCompile, key = material.customProgramCacheKey.bind(material);
    material.onBeforeCompile = (shader, renderer) => {
      if (earlier) earlier.call(material, shader, renderer);
      if (this._live()) shader.fragmentShader = `#define AIR_SHADOWS 1\n${shader.fragmentShader}`;
    };
    material.customProgramCacheKey = () => `${key()}|vidgen-air-shadows-${this._live() ? 1 : 0}`;
    material.needsUpdate = true;
    return material;
  }
  _live() { return this.shadowsOn && this.casters.length > 0; }
  /** Say that a caster has changed (its map moved with the wind or the camera): the shadows are drawn again before the next picture. */
  shadowsChanged() { this._shadeDirty = true; return this; }

  _freeShade() {
    if (!this._shade) return;
    for (const x of [this._shade.raw, this._shade.out]) x.dispose();
    for (const q of [this._shade.march, this._shade.blur]) q.material.dispose();
    this._shade.plane.dispose(); this._shade = null;
    this.uniforms.uAirShadow.value = NO_SHADOW;
  }
  _makeShade() {
    const sh = this.options.shadows === true ? SHADOWS : {...SHADOWS, ...this.options.shadows}, size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const w = Math.max(2, Math.ceil(size.x * sh.share)), h = Math.max(2, Math.ceil(size.y * sh.share)), steps = this.options.quality === "fast" ? Math.max(4, 4 * Math.round(sh.steps / 8)) : sh.steps;
    const kind = {type: THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: false, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping};
    const raw = new THREE.WebGLRenderTarget(w, h, {...kind, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter}), out = new THREE.WebGLRenderTarget(w, h, kind), plane = new THREE.PlaneGeometry(2, 2);
    const quad = (material) => { const mesh = new THREE.Mesh(plane, material), scene = new THREE.Scene(); mesh.frustumCulled = false; scene.add(mesh); return {scene, material}; };
    const uniforms = {...this.uniforms, uShadeCam: {value: new THREE.Matrix4()}, uShadeProj: {value: new THREE.Vector4()}, uShadeH: {value: this.model.H}};
    for (const c of this.casters) Object.assign(uniforms, c.uniforms);
    const march = quad(new THREE.ShaderMaterial({uniforms, defines: {STEPS: steps}, vertexShader: SHADE_VERT, fragmentShader: SHADE_FRAG(this.casters), depthTest: false, depthWrite: false, toneMapped: false}));
    const blur = quad(new THREE.ShaderMaterial({uniforms: {uShadeRaw: {value: raw.texture}}, vertexShader: QUAD_VERT, fragmentShader: BLUR_FRAG, depthTest: false, depthWrite: false, toneMapped: false}));
    this._shade = {raw, out, plane, march, blur, size: [size.x, size.y], reach: sh.reach};
  }
  /** Draw the shadows in the air for the last update's camera, if anything changed since they were last drawn (the
   * casters' maps must be up to date: vidgen/space-clouds calls it before drawing its own picture; the dome calls it
   * before it is drawn). Returns the air. */
  drawShadows() {
    const u = this.uniforms.uAirShade.value;
    if (!this._shadeDirty) return this;
    this._shadeDirty = false;
    if (!this.shadowsOn || !this.casters.length || !this._eye) { u.x = 0; return this; }
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    if (this._shade && (this._shade.size[0] !== size.x || this._shade.size[1] !== size.y)) this._freeShade();
    if (!this._shade) this._makeShade();
    const m = this.model, top = Math.max(...this.casters.map((c) => c.top)), sh = this._shade, cam = this._eye, height = this.state.height;
    // nothing to do: the camera far over every caster's reach, or the sun well under the horizon (the air is in the world's own shadow)
    if (height > top + sh.reach || this.uniforms.uAirMap.value.w < -0.2) { u.x = 0; return this; }
    u.set(1, Math.max(top, 0) / m.H, sh.reach / m.H, 0);
    const p = cam.projectionMatrix.elements, mu = sh.march.material.uniforms;
    mu.uShadeCam.value.copy(cam.matrixWorld); mu.uShadeProj.value.set(1 / p[0], 1 / p[5], p[8], p[9]);
    this.uniforms.uAirShadeView.value.copy(cam.projectionMatrix).multiply(new THREE.Matrix4().extractRotation(cam.matrixWorldInverse));
    this.uniforms.uAirShadow.value = NO_SHADOW;
    const r = this.renderer, before = r.getRenderTarget(), auto = r.autoClear;
    sh.march.material.uniformsNeedUpdate = true;
    r.autoClear = true;
    r.setRenderTarget(sh.raw); r.render(sh.march.scene, this._camera);
    r.setRenderTarget(sh.out); r.render(sh.blur.scene, this._camera);
    r.setRenderTarget(before); r.autoClear = auto;
    this.uniforms.uAirShadow.value = sh.out.texture;
    return this;
  }

  /** Say that something of the scene hides everything under the horizon (water to the horizon, a ground of
   * your own): the dome then draws neither its plain ground nor anything else there, which saves that part
   * of its cost. `under(false)` takes it back. vidgen/space-sea calls it. */
  under(covered = true) {
    const u = this.material.uniforms;
    u.uCovered.value = covered ? 1 : 0; u.uGroundOn.value = !covered && this.options.ground ? 1 : 0;
    return this;
  }

  // the world's middle in the scene now
  _center() {
    const c = this.options.center, m = this.model;
    if (c === null) return [0, -m.radius / this.options.unit, 0];
    if (Array.isArray(c)) return c;
    const p = c.isObject3D ? c.position : c;
    return [p.x, p.y, p.z];
  }

  /** The air at scene time `t` for a camera standing where `camera` does (a THREE.Camera, or [x, y, z]; the
   * origin without one): the sky table for its height and the sun, the exposure, the stars' share, the
   * lights. `sun`: a new direction towards the sun. Call it before every draw, after the camera is placed. */
  update(t = 0, {camera = null, sun = null, center = null} = {}) {
    const o = this.options, m = this.model, u = this.uniforms;
    if (center !== null) o.center = center;
    if (sun !== null) { if (Array.isArray(sun)) this.sun.set(...sun); else this.sun.copy(sun); }
    if (this.sun.lengthSq() === 0) throw fail("update: the sun's direction is zero");
    this.sun.normalize();
    let eye = [0, 0, 0];
    if (Array.isArray(camera)) eye = camera;
    else if (camera) { camera.updateMatrixWorld(); const e = camera.matrixWorld.elements; eye = [e[12], e[13], e[14]]; }
    const c = this._center(), d = [eye[0] - c[0], eye[1] - c[1], eye[2] - c[2]], r = Math.hypot(...d), R = m.radius / o.unit;
    if (!(r > 0)) throw fail("update: the camera stands at the world's middle");
    const up = d.map((x) => x / r), height = Math.max((r - R) * o.unit, 0), hc = height / m.H, mus = clamp(up[0] * this.sun.x + up[1] * this.sun.y + up[2] * this.sun.z, -1, 1);
    const [across, rows] = VIEW_TABLES[o.quality];
    const [dip, upSpan, downSpan, inside] = rowSpans(m, hc);
    this._eye = camera && camera.isCamera ? camera : null; this._shadeDirty = true;
    u.uAirGeo.value.set(m.X0, hc, TOP, o.unit / m.H); u.uAirMap.value.set(dip, upSpan, downSpan, mus);
    u.uAirUp.value.set(...up); u.uAirSun.value.copy(this.sun);
    u.uAirTable.value.set(0.25 / across, 0.25 / rows, 0.5 / PSI_TABLE.suns, 0.5 / PSI_TABLE.heights);
    const key = `${hc}|${mus}`;
    if (key !== this._drawn) { this._drawView(this.view, inside); this._drawn = key; }
    // exposure: the film's convention, a camera's stops, or a meter on the sky ahead
    const ev = typeof o.ev === "function" ? o.ev(t) : o.ev, s = this.state;
    let stops = 0, stars = 1;
    const zenith = () => luma(skyLight(m, height, 1, mus, mus, {steps: 12}).light);
    if (o.exposure === "film") {
      const dark = filmExposure(this.ambient.zenithAt(mus), this._day, 0);
      stops = filmExposure(this.ambient.zenithAt(mus), this._day, hc, this.ambient.archAt(mus)) + ev;
      stars = filmStars(dark, zenith() * o.light * 2 ** stops, mus);
    } else {
      stops = o.exposure === "camera" ? ev : clamp(Math.log2(0.14 / Math.max(this._meter(camera, height, mus) * o.light, 1e-9)), -2, SKY_STOPS) + ev;
      stars = Math.min(1, 2 ** (stops - SKY_STOPS));
    }
    const gain = 2 ** stops, film = o.exposure === "film";
    u.uAirLight.value.set(...o.color).multiplyScalar(o.light * gain);
    u.uAirGlow.value.set(...m.glow).multiplyScalar(film ? 1 : Math.min(1, 2 ** (stops - 12)));
    u.uAirDusk.value.set(film ? duskCurve(stops - ev) : 0, DUSK_KNEE);
    // the sun's disc: in a camera its true brightness over a white ground's (1 / sin^2 of its radius), capped; in the film look a bright disc that keeps its colour as it sinks
    this.material.uniforms.uSun.value.set(o.sunSize * RAD, film ? 0 : 1 / Math.sin(o.sunSize * RAD) ** 2, BURN, 1.6);
    if (this.stars && typeof this.stars.set === "function") this.stars.set({brightness: Math.min(16, this._starBase * stars)});
    // the lights: the sun after the air, the sky from above and the lit ground from below
    const direct = sunlightAt(m, height, mus, o.sunSize).map((x, i) => x * o.color[i] * o.light * gain), sky = skyAmbient(m, height, mus, {steps: 8}).map((x, i) => x * o.color[i] * o.light * gain);
    const peak = Math.max(...direct, 1e-12), cap = Math.min(BURN, peak);
    this.light.sun.color.setRGB(direct[0] / peak, direct[1] / peak, direct[2] / peak); this.light.sun.intensity = Math.PI * cap;
    this.light.sun.position.set(eye[0] + this.sun.x * 1000, eye[1] + this.sun.y * 1000, eye[2] + this.sun.z * 1000); this.light.sun.target.position.set(...eye);
    const below = m.ground.map((g, i) => g * (direct[i] * Math.max(mus, 0) + sky[i])), top = Math.max(...sky, ...below, 1e-12);
    this.light.sky.color.setRGB(sky[0] / top, sky[1] / top, sky[2] / top); this.light.sky.groundColor.setRGB(below[0] / top, below[1] / top, below[2] / top);
    this.light.sky.intensity = Math.PI * top; this.light.sky.position.set(...up);
    Object.assign(s, {height, elevation: Math.asin(mus) / RAD, ev: stops, gain, stars, sunlight: direct, ambient: sky, inside, up, center: c});
    return this;
  }

  // the sky table for the height and sun the uniforms now state, into `target`
  _drawView(target, inside) {
    const r = this.renderer, before = r.getRenderTarget(), auto = r.autoClear;
    this._quad.material.uniforms.uSpread.value = inside ? 0.5 : 0;
    r.autoClear = true; r.setRenderTarget(target); r.render(this._scene, this._camera); r.setRenderTarget(before); r.autoClear = auto;
  }

  /** The sky as it is seen from another height over the same place (`height` metres; 0: from the ground), under
   * the sun of the last update: {texture, map}, a second sky table drawn again only when the height or the sun
   * changes. A shader reads it with `airRead(table, airPlace(map, mu, cosv), cosv)` of AIR_GLSL (mu: the
   * direction's cosine to the vertical, cosv: to the sun). Call it after `update`. One other height at a time. */
  skyAt(height = 0) {
    const m = this.model, u = this.uniforms, hc = number("skyAt: the height (metres)", height, 0, 1e9) / m.H, mus = u.uAirMap.value.w;
    const [dip, upSpan, downSpan, inside] = rowSpans(m, hc);
    if (!this._other) {
      this._other = {target: this.view.clone(), map: new THREE.Vector4(), drawn: null};
      this.material.addEventListener("dispose", () => this._other.target.dispose());
    }
    const other = this._other, key = `${hc}|${mus}`;
    other.map.set(dip, upSpan, downSpan, mus);
    if (key !== other.drawn) {
      const geo = u.uAirGeo.value.y, map = u.uAirMap.value.clone();
      u.uAirGeo.value.y = hc; u.uAirMap.value.copy(other.map);
      this._drawView(other.target, inside);
      u.uAirGeo.value.y = geo; u.uAirMap.value.copy(map);
      other.drawn = key;
    }
    return {texture: other.target.texture, map: other.map};
  }

  // the mean light of the sky and the plain ground on nine rays through the frame
  _meter(camera, height, mus) {
    const m = this.model, up = this.uniforms.uAirUp.value, sun = this.sun, dir = new THREE.Vector3();
    let sum = 0;
    for (let i = -1; i <= 1; i++) {
      for (let j = -1; j <= 1; j++) {
        if (camera && camera.isCamera) dir.set(i * 0.6, j * 0.6, 0.5).unproject(camera).sub(new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld)).normalize();
        else dir.set(i * 0.4, 0.25 + j * 0.2, -1).normalize();
        const mu = dir.dot(up), s = skyLight(m, height, mu, dir.dot(sun), mus, {steps: 12});
        let l = luma(s.light);
        if (s.hit && this.options.ground) l += luma(m.ground) * luma(s.through) * (luma(sunlightAt(m, 0, mus)) * Math.max(mus, 0) + luma(this.ambient.at(mus)));
        sum += l / 9;
      }
    }
    return sum;
  }

  /** Free the tables, the dome and the lights. */
  dispose() {
    if (this.stars && typeof this.stars.set === "function") this.stars.set({brightness: this._starBase});
    for (const l of [this.light.sun, this.light.sun.target, this.light.sky]) if (l.parent) l.parent.remove(l);
    this.light.sun.dispose(); this.light.sky.dispose();
    this.material.dispose(); this.geometry.dispose();
  }
}
/** The air round the camera: `air(renderer, "earth", {sun})`, `air(renderer, "mars")`, `air(renderer, {air: {like: "earth", density: 2}, radius: 5e6})`. */
export const air = (renderer, what, extra) => new Air(renderer, what, extra);
