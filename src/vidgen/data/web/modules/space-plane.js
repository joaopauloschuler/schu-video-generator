// vidgen/space-plane: parametrized space plane parts (DESIGN.md §123.8). Part of schu-video-generator (MIT
// licence); imported by a page as "vidgen/space-plane". It builds on the kit of vidgen/space-craft.
//
//   import {plane, planeKit, planeFleet} from "vidgen/space-plane";
//   const ship = plane("glider", {seed: 7});                // a ready-made plane (PLANES: glider, freighter, needle,
//                                                            // lifter, scout, skiff), another one per seed
//   scene.add(ship.object);                                  // metres; +z the nose, +y up, +x the left wing
//   ship.fly(ctx.flight, {flight: "Plane"});                 // a flight of flight_data: (vidgen/space-craft's fly)
//   ship.update(t, {gear: 0, bay: 0});                       // surfaces move with the flight's rates, lights blink
//   ship.controls({elevon: -6, roll: 10, rudder: 4, brake: 30});   // or set them yourself (degrees)
//   for (const m of Object.values(ship.materials)) sky.haze(m);    // the air between (vidgen/space-air)
//
// A plane of your own, from the same parts (every option a plain number or word):
//   const kit = planeKit({seed: 3, scheme: "grey", scorch: 0.6});
//   const body = kit.body({length: 24, width: 3.6, nose: "chined", belly: 0.8});
//   const wing = kit.wing({preset: "double-delta", span: 15}); wing.position.set(0, -0.9, 2); body.add(wing);
//   const mine = kit.plane(body);
// or as one description: planeFrom({body: {...}, wing: {...}, fins: {...}, engines: {...}}, {seed: 3}).
// mine.problems() names what looks wrong (a wing off the body, gear too short). A look, not aerodynamics.
//
// The designs are invented: no real and no film vehicle is copied, and the markings are stripes, number
// blocks and a registration made from the seed. Surfaces are computed: black heat tiles with a grid and tiles
// of their own tone, quilted blankets with seams, bare metal, scorch streaks behind the nose and the leading
// edges (`scorch`: 0 factory fresh, 1 many flights). Nothing is random at draw time; what a plane shows at t
// is a function of t, its seed and what update is given.
import * as THREE from "three";
import {rng} from "vidgen/music-time";
import {CraftKit, Craft, GLARE, ACCENTS, platingMaps} from "vidgen/space-craft";

export const VERSION = 1;
const PREFIX = "vidgen/space-plane";
const TAU = Math.PI * 2, RAD = Math.PI / 180;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const mix = (a, b, u) => a + (b - a) * u;
const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a)); return u * u * (3 - 2 * u); };
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const X = V3(1, 0, 0), Y = V3(0, 1, 0), Z = V3(0, 0, 1);
const fail = (message) => new Error(`${PREFIX}: ${message}`);
function distance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function hint(key, names) {
  const best = names.map((k) => [distance(String(key).toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; options: ${keys.join(", ")}`);
}
function choice(where, value, choices) {
  if (!choices.includes(value)) throw fail(`${where}: "${value}"${hint(String(value), choices)}; one of: ${choices.join(", ")}`);
  return value;
}
// a number of `where` within [lo, hi]
function number(where, value, lo, hi) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < lo || value > hi) throw fail(`${where} must be a number from ${lo} to ${hi}, got ${JSON.stringify(value)}`);
  return value;
}
const filled = (defaults, o) => { const out = {...defaults}; for (const [k, v] of Object.entries(o)) if (v !== undefined) out[k] = v; return out; };
const hash1 = (x, k = 0) => { let h = Math.imul(x | 0, 374761393) ^ Math.imul(k | 0, 1274126177); h = Math.imul(h ^ (h >>> 13), 1103515245); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
// smooth noise along a line, 0..1: the same on every machine
const noise1 = (x, k = 0) => { const i = Math.floor(x), f = x - i; return mix(hash1(i, k), hash1(i + 1, k), f * f * (3 - 2 * f)); };
const pick = (r, list) => list[Math.min(list.length - 1, Math.floor(r() * list.length))];
const range = (r, a, b) => a + (b - a) * r();
const round = (x, step = 0.01) => Math.round(x / step) * step;
const point = (p, n, u = Z) => ({p, n: n.clone().normalize(), u});

// ---------- shapes as numbers (no three.js: tested in Node) ----------
/** The nose shapes of a body. */
export const NOSES = Object.freeze(["ogive", "blunt", "pointed", "chined", "needle"]);
/** A nose's radius (a share of the body's) at `u` (0 the tip, 1 where the nose ends). "ogive": a tangent ogive
 * of `fineness` (its length over the body's radius), pointed; "blunt": half an ellipse; "pointed": nearly a
 * cone (a power curve, so that it meets the body without a corner); "needle": the slender
 * body of least wave drag for its length and width (pointed, fuller than a cone); "chined": an ogive (the
 * body builder widens and flattens it into a lens). */
export function noseProfile(nose, u, fineness = 3) {
  u = clamp(u);
  if (nose === "blunt") return Math.sqrt(1 - (1 - u) * (1 - u));
  if (nose === "pointed") return u * (1.5 - 0.5 * u * u);
  if (nose === "needle") { const a = Math.acos(1 - 2 * u); return Math.sqrt((a - Math.sin(2 * a) / 2) / Math.PI); }
  const l = Math.max(fineness, 1.01), rho = (1 + l * l) / 2;
  return Math.sqrt(Math.max(0, rho * rho - l * l * (1 - u) * (1 - u))) - (rho - 1);
}
const BODY = Object.freeze({length: 30, width: 4, height: null, diameter: null, nose: "ogive", noseLength: 0.3, droop: 0.1, belly: 0.6, tail: 0.7, tailLength: 0.2,
  upsweep: 0.4, hump: null, bay: null, cap: 0.05, waterline: 10});
/** A body's shape from its options, as functions: {length, width, height, section(s), point(s, angle, out),
 * top(s), bottom(s), half(s)}. `s` runs from 0 (the nose's tip) to 1 (the tail's end); `angle` in degrees
 * round the body: 0 the left side (+x), 90 the top, 180 the right side, 270 the belly. Options (metres and
 * shares): `length` (3 to 120), `width`, `height` (default the width; or `diameter` for both), `nose` (NOSES),
 * `noseLength` (a share of the length), `droop` (how far under the middle line the tip sits, in heights),
 * `belly` (0 round, 1 flat), `tail` (the end's size, a share of the body's), `tailLength`, `upsweep` (0: the
 * tail narrows evenly, 1: only its underside rises), `hump` ({from, to, height}: a dorsal hump between two
 * stations, its height a share of the body's), `bay` ({from, to, width}: a payload bay under two doors, `width`
 * degrees to each side of the top), `cap` (the nose cap's share of the length), `waterline` (degrees under the
 * widest line where the belly's surface begins). */
export function bodyShape(options = {}) {
  known("body options", options, Object.keys(BODY));
  const o = filled(BODY, options);
  const L = number("body length", o.length, 3, 120), W = number("body width", o.diameter ?? o.width, 0.3, 40), H = number("body height", o.diameter ?? o.height ?? W, 0.3, 40);
  choice("nose", o.nose, NOSES);
  const nl = number("noseLength", o.noseLength, 0.05, 0.7), tl = number("tailLength", o.tailLength, 0.02, 0.6), belly = number("belly", o.belly, 0, 1);
  const tail = number("tail", o.tail, 0.1, 1), up = number("upsweep", o.upsweep, 0, 1), droop = number("droop", o.droop, -0.5, 0.5);
  if (nl + tl > 0.95) throw fail(`noseLength + tailLength must leave a body between them (at most 0.95), got ${nl} + ${tl}`);
  number("cap", o.cap, 0, 0.3); number("waterline", o.waterline, -30, 60);
  if (o.hump) { known("hump", o.hump, ["from", "to", "height"]); if (!(o.hump.to > o.hump.from)) throw fail("hump: `to` must be after `from` (shares of the length from the nose)"); }
  if (o.bay) { known("bay", o.bay, ["from", "to", "width"]); if (!(o.bay.to > o.bay.from) || o.bay.from < nl * 0.6 || o.bay.to > 1 - tl * 0.5) throw fail(`bay: from < to, both between the nose and the tail (${round(nl * 0.6)} to ${round(1 - tl * 0.5)})`); }
  const under = 0.5 - 0.2 * belly, chined = o.nose === "chined", fineness = nl * L / (0.5 * Math.max(W, H));
  const section = (s) => {
    s = clamp(s);
    const u = clamp(s / nl), prof = s < nl ? noseProfile(o.nose, u, fineness) : 1, v = clamp((s - (1 - tl)) / tl), k = (1 - tail) * Math.pow(v, 1.6);
    const wide = chined ? Math.pow(prof, 0.62) : prof, high = chined ? prof * mix(0.72, 1, smooth(0, 1, u)) : prof, near = smooth(0, 1, u);
    let hump = 0;
    if (o.hump) { const e = 0.38 * (o.hump.to - o.hump.from); hump = (o.hump.height ?? 0.25) * smooth(o.hump.from, o.hump.from + e, s) * (1 - smooth(o.hump.to - e, o.hump.to, s)); }
    return {w: 0.5 * W * wide * (1 - k * 0.8), ht: H * (1 - under) * high * Math.max(0.08, 1 - k * (1 - up)) * (1 + hump / (1 - under)), hb: H * under * high * Math.max(0.08, 1 - k * (1 + up)),
      nt: chined ? mix(1.45, 2, near) : 2, nb: chined ? mix(1.45, 2 + 3.5 * belly, near) : mix(2, 2 + 3.5 * belly, smooth(0, 0.7, u)), yc: -droop * H * (1 - u) * (1 - u)};
  };
  const raw = (s, angle, c) => {
    const a = angle * RAD, cs = Math.cos(a), sn = Math.sin(a), n = sn >= 0 ? c.nt : c.nb, e = 2 / n;
    return [c.w * Math.sign(cs) * Math.pow(Math.abs(cs), e), c.yc + (sn >= 0 ? c.ht : c.hb) * Math.sign(sn) * Math.pow(Math.abs(sn), e), L * (0.5 - s)];
  };
  const shape = {options: o, length: L, width: W, height: H, noseLength: nl, tailLength: tl, section,
    /** The surface's point [x, y, z] at station `s` and `angle`, `out` metres off it. */
    point(s, angle, out = 0) {
      const p = raw(s, angle, section(s));
      if (!out) return p;
      const n = shape.normal(s, angle);
      return [p[0] + n[0] * out, p[1] + n[1] * out, p[2] + n[2] * out];
    },
    /** The outward direction there. */
    normal(s, angle) {
      const ds = 1e-3, da = 0.5, s0 = clamp(s - ds, 1e-4, 1), s1 = clamp(s + ds, 0, 1), a = raw(s0, angle, section(s0)), b = raw(s1, angle, section(s1)), c = raw(s, angle - da, section(s)), d = raw(s, angle + da, section(s));
      const ts = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], ta = [d[0] - c[0], d[1] - c[1], d[2] - c[2]];
      const n = [ts[1] * ta[2] - ts[2] * ta[1], ts[2] * ta[0] - ts[0] * ta[2], ts[0] * ta[1] - ts[1] * ta[0]], l = Math.hypot(...n) || 1;
      return [n[0] / l, n[1] / l, n[2] / l];
    },
    top: (s) => { const c = section(s); return c.yc + c.ht; }, bottom: (s) => { const c = section(s); return c.yc - c.hb; }, half: (s) => section(s).w,
    /** The belly's height at station `s`, `x` metres from the middle. */
    under(s, x) { const c = section(s), q = clamp(Math.abs(x) / Math.max(c.w, 1e-6), 0, 0.999); return c.yc - c.hb * Math.pow(1 - Math.pow(q, c.nb), 1 / c.nb); },
    /** The back's height there. */
    over(s, x) { const c = section(s), q = clamp(Math.abs(x) / Math.max(c.w, 1e-6), 0, 0.999); return c.yc + c.ht * Math.pow(1 - Math.pow(q, c.nt), 1 / c.nt); }};
  return shape;
}

/** The wing presets: parameter sets and nothing more. `chord`: the root chord as a share of the span; `taper`:
 * the tip chord over the root chord. */
export const WINGS = Object.freeze({
  delta: Object.freeze({sweep: 58, taper: 0.06, chord: 0.78, thickness: 0.05}),
  "double-delta": Object.freeze({sweep: 46, sweepInner: 76, crank: 0.32, taper: 0.14, chord: 1.0, thickness: 0.05}),
  "cranked-arrow": Object.freeze({sweep: 50, sweepInner: 70, crank: 0.55, taper: 0.12, chord: 0.85, thickness: 0.04, airfoil: "sharp"}),
  swept: Object.freeze({sweep: 38, taper: 0.35, chord: 0.3, thickness: 0.08}),
  straight: Object.freeze({sweep: 6, taper: 0.6, chord: 0.2, thickness: 0.1}),
  ogival: Object.freeze({sweep: 62, curve: 1, taper: 0.1, chord: 0.95, thickness: 0.05}),
  stub: Object.freeze({sweep: 55, taper: 0.5, chord: 1.4, thickness: 0.1, dihedral: 20}),
  blended: Object.freeze({sweep: 50, sweepInner: 74, crank: 0.25, taper: 0.3, chord: 1.0, thickness: 0.1, fillet: 1, dihedral: 7}),
  long: Object.freeze({sweep: 3, taper: 0.45, chord: 0.085, thickness: 0.13, dihedral: 4, twist: -2}),
});
export const AIRFOILS = Object.freeze(["round", "sharp", "flat"]);
/** The kinds of moving surface a wing or a tail may carry (`controls: [{name, from, to, chord}]`). */
export const CONTROLS = Object.freeze(["elevon", "flap", "rudder", "canard"]);
const WING = Object.freeze({preset: null, span: 16, rootChord: null, tipChord: null, sweep: 45, crank: 0, sweepInner: null, curve: 0, dihedral: 3, thickness: 0.06, airfoil: "round", twist: 0,
  fillet: 0.5, inboard: 0, edge: 0.07, controls: null, tip: null, allMoving: false, taper: null, chord: null});
function wingOptions(options) {
  known("wing options", options, Object.keys(WING));
  if (options.preset !== undefined && options.preset !== null) choice("wing preset", options.preset, Object.keys(WINGS));
  const o = filled(WING, {...(options.preset ? WINGS[options.preset] : {}), ...options});
  number("wing span", o.span, 0.2, 200);
  o.rootChord = number("wing rootChord", o.rootChord ?? (o.chord ?? 0.4) * o.span, 0.05, 200);
  o.tipChord = number("wing tipChord", o.tipChord ?? (o.taper ?? 0.3) * o.rootChord, 0, 200);
  number("wing sweep", o.sweep, -60, 85); number("wing crank", o.crank, 0, 0.95); number("wing curve", o.curve, 0, 1); number("wing dihedral", o.dihedral, -90, 90);
  number("wing thickness", o.thickness, 0.01, 0.3); number("wing twist", o.twist, -15, 15); number("wing fillet", o.fillet, 0, 1); number("wing inboard", o.inboard, 0, o.span / 2); number("wing edge", o.edge, 0, 0.4);
  if (o.sweepInner !== null) number("wing sweepInner", o.sweepInner, -60, 88);
  choice("airfoil", o.airfoil, AIRFOILS);
  return o;
}
/** A wing's outline from its options, as numbers: {semi (half the span), le(eta), te(eta), chord(eta) (metres
 * back from the root's leading edge, eta 0 at the middle line and 1 at the tip), sweepAt(eta) (the leading
 * edge's, degrees), area (both sides, the part inside the body too), aspect, taper, mean (the mean chord)}.
 * The leading edge runs at `sweepInner` to `crank` (a share of the half span) and at `sweep` beyond (a strake
 * or a double delta), or bends from steep to shallow with `curve` (an ogival wing); the trailing edge is straight. */
export function wingPlanform(options = {}) {
  const o = options.__checked ? options : wingOptions(options), semi = o.span / 2, t0 = Math.tan((o.sweepInner ?? o.sweep) * RAD), t1 = Math.tan(o.sweep * RAD), c = o.crank;
  const kinked = (eta) => semi * (eta < c ? eta * t0 : c * t0 + (eta - c) * t1), tipLe = kinked(1);
  const le = (eta) => mix(kinked(eta), tipLe * (1 - Math.pow(1 - eta, 1.8)), o.curve), te = (eta) => mix(o.rootChord, tipLe + o.tipChord, eta), chord = (eta) => te(eta) - le(eta);
  let area = 0, moment = 0;
  const n = 200;
  for (let i = 0; i < n; i++) { const eta = (i + 0.5) / n, ch = chord(eta); if (ch < -1e-9) throw fail(`wing: the leading edge passes the trailing edge at ${round(eta)} of the half span (chord ${round(ch)} m): a longer rootChord or tipChord, or less sweep`); area += ch * semi / n; moment += ch * ch * semi / n; }
  return {semi, le, te, chord, area: 2 * area, aspect: o.span * o.span / (2 * area), taper: o.tipChord / o.rootChord, mean: moment / area,
    sweepAt: (eta) => Math.atan((le(Math.min(1, eta + 1e-4)) - le(Math.max(0, eta - 1e-4))) / (semi * (Math.min(1, eta + 1e-4) - Math.max(0, eta - 1e-4)))) / RAD};
}
// half the thickness of an airfoil at x (0 the leading edge .. 1 the trailing edge), in chords, for a thickness ratio t
const halfThickness = (airfoil, x, t) => (airfoil === "sharp" ? 2 * t * x * (1 - x) : 5 * t * (0.2969 * Math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x * x * x - 0.1036 * x * x * x * x));

/** A registration from a seed: two letters, a hyphen, three figures (invented; it stands for nothing). */
export function registration(seed = 1) {
  const r = rng((seed * 40503 + 977) >>> 0), letters = "ACEFHJKLMPRTUVXYZ";
  return `${pick(r, [...letters])}${pick(r, [...letters])}-${1 + Math.floor(r() * 9)}${Math.floor(r() * 10)}${Math.floor(r() * 10)}`;
}
const GLYPHS = {"0": [14, 17, 19, 21, 25, 17, 14], "1": [4, 12, 4, 4, 4, 4, 14], "2": [14, 17, 1, 2, 4, 8, 31], "3": [31, 2, 4, 2, 1, 17, 14], "4": [2, 6, 10, 18, 31, 2, 2], "5": [31, 16, 30, 1, 1, 17, 14],
  "6": [6, 8, 16, 30, 17, 17, 14], "7": [31, 1, 2, 4, 8, 8, 8], "8": [14, 17, 17, 14, 17, 17, 14], "9": [14, 17, 17, 15, 1, 2, 12], "-": [0, 0, 0, 31, 0, 0, 0], " ": [0, 0, 0, 0, 0, 0, 0],
  A: [14, 17, 17, 31, 17, 17, 17], C: [14, 17, 16, 16, 16, 17, 14], E: [31, 16, 16, 30, 16, 16, 31], F: [31, 16, 16, 30, 16, 16, 16], H: [17, 17, 17, 31, 17, 17, 17], J: [7, 2, 2, 2, 2, 18, 12],
  K: [17, 18, 20, 24, 20, 18, 17], L: [16, 16, 16, 16, 16, 16, 31], M: [17, 27, 21, 21, 17, 17, 17], P: [30, 17, 17, 30, 16, 16, 16], R: [30, 17, 17, 30, 20, 18, 17], T: [31, 4, 4, 4, 4, 4, 4],
  U: [17, 17, 17, 17, 17, 17, 14], V: [17, 17, 17, 17, 17, 10, 4], X: [17, 17, 10, 4, 10, 17, 17], Y: [17, 17, 10, 4, 4, 4, 4], Z: [31, 1, 2, 4, 8, 16, 31],
  B: [30, 17, 17, 30, 17, 17, 30], D: [30, 17, 17, 17, 17, 17, 30], G: [14, 17, 16, 23, 17, 17, 15], I: [14, 4, 4, 4, 4, 4, 14], N: [17, 25, 21, 19, 17, 17, 17], O: [14, 17, 17, 17, 17, 17, 14],
  Q: [14, 17, 17, 17, 21, 18, 13], S: [15, 16, 16, 14, 1, 1, 30], W: [17, 17, 17, 21, 21, 27, 17]};
/** A line of text as a picture: {data (RGBA, white where a letter is and clear elsewhere), width, height}; block
 * letters five by seven, `scale` texels to a block: A to Z, figures, a hyphen, a space. */
export function textMap(text, scale = 8) {
  const chars = [...String(text).toUpperCase()];
  for (const c of chars) if (!GLYPHS[c]) throw fail(`a marking cannot show "${c}"; letters: ${Object.keys(GLYPHS).join("")}`);
  const width = (chars.length * 6 + 1) * scale, height = 9 * scale, data = new Uint8Array(width * height * 4);
  for (let k = 0; k < width * height; k++) data.set([255, 255, 255, 0], 4 * k);
  chars.forEach((c, n) => GLYPHS[c].forEach((bits, row) => { for (let col = 0; col < 5; col++) if (bits & (16 >> col)) for (let j = 0; j < scale; j++) for (let i = 0; i < scale; i++) data[4 * ((height - 1 - ((1 + row) * scale + j)) * width + (1 + n * 6 + col) * scale + i) + 3] = 255; }));
  return {data, width, height};
}

/** How the surfaces follow a flight (a look, stated): from the rates of bank and pitch (degrees a second), the
 * slowing (m/s²) and the bank (degrees): `roll` = 0.9 x the bank's rate (within 18), `elevon` = -1.6 x the
 * pitch's rate less a tenth of the bank's size (within 14: a turning plane pulls a little), `rudder` a quarter
 * of the roll, `brake` 9 degrees for every m/s² of slowing (to 50). */
export function controlsFromRates({bankRate = 0, pitchRate = 0, slowing = 0, bank = 0} = {}) {
  const roll = clamp(0.9 * bankRate, -18, 18);
  return {roll, elevon: clamp(-1.6 * pitchRate - 0.1 * Math.abs(bank), -14, 14), rudder: 0.25 * roll, brake: clamp(9 * slowing, 0, 50)};
}

// ---------- surfaces ----------
const TEXTURES = new Map();
function tiled(name, tile, make) {
  const key = `${name}|${tile}`;
  if (!TEXTURES.has(name)) TEXTURES.set(name, make());
  if (!TEXTURES.has(key)) {
    const m = TEXTURES.get(name), one = (data, srgb) => {
      const t = new THREE.DataTexture(data, 512, 512, THREE.RGBAFormat);
      t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.anisotropy = 2; t.repeat.set(1 / tile, 1 / tile);
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.needsUpdate = true;
      return t;
    };
    TEXTURES.set(key, {map: one(m.albedo, true), normalMap: one(m.normal, false), roughnessMap: one(m.orm, false)});
  }
  return TEXTURES.get(key);
}
// the same picture with its dark lines and tones drawn `share` as strong (a seam in white cloth is a faint line)
const faint = (m, share) => { for (let k = 0; k < m.albedo.length; k += 4) for (let n = 0; n < 3; n++) m.albedo[k + n] = 255 - (255 - m.albedo[k + n]) * share; return m; };
/** The surfaces of a plane, as numbers (vidgen/space-craft's platingMaps): heat tiles (sixteen to a side, every
 * other row moved half a tile, each of its own tone, a few much lighter or darker), a quilted blanket (eight
 * pillowed squares to a side, faint seams between) and panels (a seeded splitting, faint lines, rivets). */
export const SURFACES = Object.freeze({
  tiles: () => platingMaps(512, {seed: 21, tiles: 16, rivets: false, pillow: 0.5, tone: 0.15, specks: 60, groove: 1.2}),
  quilt: () => faint(platingMaps(512, {seed: 22, tiles: 8, rivets: false, pillow: 1.2, tone: 0.03, specks: 14, groove: 0.6}), 0.3),
  panels: () => faint(platingMaps(512, {seed: 23, pillow: 0.3, tone: 0.04, groove: 0.7}), 0.45),
});
/** The paint schemes: which surface the back, the belly and the edges take, and the back's colour. "tiles":
 * white blankets over black tiles; "grey": grey blankets over black tiles; "metal": bare metal with dark edges;
 * "dark": tiles all over; "paint": white paint with panel lines over black tiles; "plain": painted all round, no
 * heat shield (a plane that never comes back from orbit). */
export const SCHEMES = Object.freeze({
  tiles: Object.freeze({top: "blanket", belly: "heat", color: 0xdcdad3, mark: 0x26282c}),
  grey: Object.freeze({top: "blanket", belly: "heat", color: 0x8b9199, mark: 0xe8e6e0}),
  metal: Object.freeze({top: "bare", belly: "bare", color: 0xb9bdc2, mark: 0x26282c}),
  dark: Object.freeze({top: "heat", belly: "heat", color: 0x26282d, mark: 0xdedcd6}),
  paint: Object.freeze({top: "paint", belly: "heat", color: 0xdad8d2, mark: 0x26282c}),
  plain: Object.freeze({top: "paint", belly: "paint", color: 0xdad8d2, mark: 0x26282c}),
});
function capGlare(shader) {
  shader.uniforms.uGlareCap = GLARE;
  shader.fragmentShader = shader.fragmentShader.replace("void main() {", "uniform float uGlareCap;\nvoid main() {")
    .replace("#include <lights_fragment_end>", "#include <lights_fragment_end>\nreflectedLight.directSpecular = min(reflectedLight.directSpecular, vec3(uGlareCap));");
}
function planeMaterials(kit, {scheme, color, under, tile, wear, text, lit}) {
  const s = SCHEMES[scheme];
  const std = (o, maps = null, scale = 1, decal = false) => {
    const m = new THREE.MeshStandardMaterial({vertexColors: true, ...o});
    if (maps) { m.map = maps.map; m.normalMap = maps.normalMap; m.normalScale = new THREE.Vector2(scale, scale); m.roughnessMap = maps.roughnessMap; }
    if (decal) { m.polygonOffset = true; m.polygonOffsetFactor = -2; m.polygonOffsetUnits = -4; }
    m.onBeforeCompile = capGlare; m.customProgramCacheKey = () => "vidgen-plane";
    return m;
  };
  const kinds = {
    blanket: (c) => std({color: c, roughness: 1.1, metalness: 0}, tiled("quilt", 8 * 0.5, SURFACES.quilt), 0.3 * wear),
    heat: (c) => std({color: c, roughness: 1.25, metalness: 0.02}, tiled("tiles", 16 * tile, SURFACES.tiles), 1.0),
    bare: (c) => std({color: c, roughness: 0.62, metalness: 0.55}, tiled("panels", 3.2, SURFACES.panels), 0.6 * wear),
    paint: (c) => std({color: c, roughness: 0.8, metalness: 0.04}, tiled("panels", 3.2, SURFACES.panels), 0.5 * wear),
  };
  const black = under ?? 0x202125, top = kinds[s.top](color ?? s.color), belly = s.belly === s.top && s.top !== "heat" ? kinds[s.belly](new THREE.Color(color ?? s.color).multiplyScalar(0.8)) : kinds[s.belly](s.top === "heat" ? (color ?? s.color) : black);
  const t = new THREE.DataTexture(text.data, text.width, text.height, THREE.RGBAFormat);
  t.magFilter = THREE.LinearFilter; t.minFilter = THREE.LinearFilter; t.generateMipmaps = false; t.needsUpdate = true;
  const M = {"plane-top": top, "plane-belly": belly, "plane-edge": std({color: 0x34363b, roughness: 0.6, metalness: 0.12}),
    "plane-mark": std({color: s.mark, roughness: 0.8, metalness: 0, map: t, alphaTest: 0.5}, null, 1, true),
    "plane-accent": std({color: kit.accent, roughness: 0.75, metalness: 0.05}, null, 1, true),
    "plane-line": std({color: 0x17181b, roughness: 0.8, metalness: 0.1}, null, 1, true),
    "plane-glass": std({color: 0x0b0e13, roughness: 0.08, metalness: 0.9}, null, 1, true),
    "plane-canopy": std({color: 0x0b0e13, roughness: 0.08, metalness: 0.9, emissive: 0xffc98a, emissiveIntensity: 0}, null, 1, true),
    "plane-window": std({color: 0x1a130b, roughness: 0.2, metalness: 0.2, emissive: 0xffc98a, emissiveIntensity: 1.25}, null, 1, true)};
  for (const [name, m] of Object.entries(M)) { m.name = name; m.envMapIntensity = 1; }
  return {materials: M, dark: {"plane-top": s.top === "heat", "plane-belly": s.belly === "heat"}, metal: s.top === "bare"};
}

// ---------- geometry ----------
// A sheet of rows x cols points: at(row, col) -> Vector3, skinOf(row, col) -> the surface of the quad from
// (row, col) to (row + 1, col + 1) or null for a hole. The normals are those of the whole sheet (smooth over the
// borders between surfaces); `wrap`: the first and last columns are the same line. `flip`: the other winding, or
// a direction the sheet faces. `uv(row, col, p)` -> [u, v]; `tint(skin)` -> what Bins.add takes.
function sheet(b, rows, cols, at, skinOf, {flip = false, uv = null, tint = null, wrap = false} = {}) {
  const n = rows * cols, pos = new Float32Array(n * 3), uvs = new Float32Array(n * 2);
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    const k = j * cols + i, q = at(j, i);
    pos[3 * k] = q.x; pos[3 * k + 1] = q.y; pos[3 * k + 2] = q.z;
    if (uv) { const w = uv(j, i, q); uvs[2 * k] = w[0]; uvs[2 * k + 1] = w[1]; }
  }
  if (flip && flip.isVector3) {
    const P = (k) => V3(pos[3 * k], pos[3 * k + 1], pos[3 * k + 2]), sum = V3();
    for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) { const a = j * cols + i; sum.add(P(a + cols).sub(P(a)).cross(P(a + 1).sub(P(a)))); }
    flip = sum.dot(flip) < 0;
  }
  const all = [], by = new Map();
  for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
    const a = j * cols + i, c = a + cols, quad = flip ? [a, a + 1, c, c, a + 1, c + 1] : [a, c, a + 1, c, c + 1, a + 1], skin = skinOf(j, i);
    all.push(...quad);
    if (skin) { if (!by.has(skin)) by.set(skin, []); by.get(skin).push(...quad); }
  }
  const whole = new THREE.BufferGeometry();
  whole.setAttribute("position", new THREE.BufferAttribute(pos, 3)); whole.setIndex(all); whole.computeVertexNormals();
  const nor = whole.attributes.normal.array;
  if (wrap) for (let j = 0; j < rows; j++) {
    const a = 3 * j * cols, c = 3 * (j * cols + cols - 1), m = V3(nor[a] + nor[c], nor[a + 1] + nor[c + 1], nor[a + 2] + nor[c + 2]).normalize();
    nor[a] = nor[c] = m.x; nor[a + 1] = nor[c + 1] = m.y; nor[a + 2] = nor[c + 2] = m.z;
  }
  for (const [skin, index] of by) {
    const map = new Map(), order = [];
    const local = index.map((k) => { if (!map.has(k)) { map.set(k, order.length); order.push(k); } return map.get(k); });
    const p = new Float32Array(order.length * 3), q = new Float32Array(order.length * 3), w = new Float32Array(order.length * 2);
    order.forEach((k, m) => { p.set(pos.subarray(3 * k, 3 * k + 3), 3 * m); q.set(nor.subarray(3 * k, 3 * k + 3), 3 * m); w.set(uvs.subarray(2 * k, 2 * k + 2), 2 * m); });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(p, 3)); g.setAttribute("normal", new THREE.BufferAttribute(q, 3)); g.setAttribute("uv", new THREE.BufferAttribute(w, 2)); g.setIndex(local);
    b.add(skin, g, {uv: "keep", tint: typeof tint === "function" ? tint(skin) : tint});
  }
  whole.dispose();
}
// sorted numbers without near-doubles; `must` are kept exactly
function stations(list, must = [], gap = 1e-3) {
  const out = [...must].sort((a, b) => a - b).filter((x, i, a) => i === 0 || x - a[i - 1] > 1e-9);
  for (const x of list) if (!out.some((m) => Math.abs(m - x) < gap)) out.push(x);
  return out.sort((a, b) => a - b);
}
// +1 or -1: which way round `axis` an arm turns to move toward `want`
const turnTo = (axis, arm, want) => (V3().crossVectors(axis, arm).dot(want) >= 0 ? 1 : -1);
const moving = (group, pivot) => { group.position.copy(pivot); group.userData.moving = true; group.userData.sparse = true; return group; };

const KIT = Object.freeze({scheme: "tiles", color: null, belly: null, scorch: 0.3, tile: 0.35, registration: null});
const KIT_KEYS = ["seed", "accent", "foil", "detail", "wear", "lit"];
const FIN = Object.freeze({type: "single", height: 4, rootChord: 5, tipChord: null, sweep: 45, cant: null, spacing: 3, thickness: 0.05, airfoil: "sharp", rudder: true, sink: 0.3, edge: 0.08});
export const FINS = Object.freeze(["single", "twin", "vee"]);
export const LAYOUTS = Object.freeze(["row", "block", "ring"]);

/** The parts of a plane: the kit of vidgen/space-craft (its engines, lights, thrusters and surfaces) with a
 * lofted body, one wing function, tails, engine clusters and pods, landing gear. Options: the craft kit's
 * (`seed`, `accent`: the stripes' colour, `detail`, `wear`: how deep the surfaces' relief is, `lit`: the share of
 * lit windows, 0 a dark cabin, `foil`) and `scheme` (SCHEMES), `color` (the back's own colour), `belly` (the
 * underside's own colour), `scorch` (0 factory fresh .. 1 many flights: streaks behind the nose cap and the leading edges, greyed
 * tiles), `tile` (a heat tile's width in metres, 0.35: larger than real ones, so that the grid reads),
 * `registration` (text; default made from the seed). */
export class PlaneKit extends CraftKit {
  constructor(options = {}) {
    known("planeKit options", options, [...KIT_KEYS, ...Object.keys(KIT)]);
    super(Object.fromEntries(Object.entries(options).filter(([k]) => KIT_KEYS.includes(k))));
    const o = this.look = filled(KIT, Object.fromEntries(Object.entries(options).filter(([k]) => k in KIT)));
    choice("scheme", o.scheme, Object.keys(SCHEMES)); number("scorch", o.scorch, 0, 1); number("tile", o.tile, 0.05, 2);
    this.registration = o.registration ?? registration(this.seed);
    const made = planeMaterials(this, {scheme: o.scheme, color: o.color, under: o.belly, tile: o.tile, wear: this.options.wear, text: textMap(this.registration), lit: this.options.lit > 0 ? 1 : 0});
    Object.assign(this.materials, made.materials);
    this.darkSkin = made.dark; this.metal = made.metal; this.scorch = o.scorch;
  }

  // how a surface takes soot: f in 0..1 -> the tint of a vertex (white goes brown-grey, black tiles go grey, metal straw)
  _tint(skin, f) {
    if (skin === "plane-edge") return [1 + 0.5 * f, 1 + 0.45 * f, 1 + 0.4 * f];
    if (this.darkSkin[skin]) return [1 + 5 * f, 1 + 4.8 * f, 1 + 4.4 * f];
    if (this.metal) return [mix(1, 0.78, f), mix(1, 0.62, f), mix(1, 0.44, f)];
    return [mix(1, 0.2, f), mix(1, 0.165, f), mix(1, 0.14, f)];
  }

  /** A body along z, its nose at +z: bodyShape's options, and `skins` ({top, belly, cap}: other surfaces).
   * Lofted from cross-sections (a superellipse above and one below the widest line), the nose cap dark, the
   * belly's surface up to the waterline, soot behind the cap by the kit's `scorch`; with `bay`, an open trough
   * lined with foil under two doors that carry radiators inside (moving: `userData.doors`).
   * Points: fore, aft, and {angle, along (0 the tail .. 1 the nose), out} anywhere on its side. */
  body(o = {}) {
    const {skins = {}, ...rest} = o;
    known("body skins", skins, ["top", "belly", "cap"]);
    const S = bodyShape(rest), so = S.options, L = S.length, far = this.far, b = this.bins(), scorch = this.scorch, seed = this.seed;
    const top = skins.top ?? "plane-top", belly = skins.belly ?? "plane-belly", cap = skins.cap ?? "plane-edge", nl = S.noseLength, tl = S.tailLength, bay = so.bay, bw = bay ? number("bay width", bay.width ?? 35, 5, 80) : 0;
    const n1 = far ? 7 : 18, n2 = far ? 5 : 16, n3 = far ? 3 : 8, ss = [];
    for (let k = 0; k <= n1; k++) ss.push(nl * Math.pow(k / n1, so.nose === "blunt" ? 2.4 : 1.7));
    for (let k = 1; k <= n2; k++) ss.push(mix(nl, 1 - tl, k / n2));
    for (let k = 1; k <= n3; k++) ss.push(mix(1 - tl, 1, k / n3));
    const sl = stations(ss, [0, 1, ...(so.cap > 0 ? [so.cap] : []), ...(bay ? [bay.from, bay.to] : [])], 2e-4);
    const na = far ? 28 : 72, wl = so.waterline, al = stations(Array.from({length: na + 1}, (_, i) => -90 + 360 * i / na), [-90, 270, 90, -wl, 180 + wl, ...(bay ? [90 - bw, 90 + bw] : [])], 1.6);
    const rows = sl.length, cols = al.length, P = sl.map((s) => al.map((a) => V3(...S.point(s, a)))), mid = al.indexOf(90);
    const girth = P.map((ring) => { const g = [0]; for (let i = 1; i < cols; i++) g.push(g[i - 1] + ring[i].distanceTo(ring[i - 1])); return g.map((x) => x - g[mid]); });
    const soot = (x, y, z) => {
      const s = 0.5 - z / L, c = S.section(s), a = Math.atan2(y - c.yc, x) / RAD, reach = (0.05 + 0.3 * scorch) * (0.3 + 1.4 * noise1(a / 9, seed));
      const streak = s < so.cap ? 0 : Math.min(1, 1.5 * scorch) * (0.3 + 0.9 * Math.pow(noise1(a / 4 + 40, seed + 1), 1.5)) * Math.exp(-(s - so.cap) / reach);
      return clamp(streak + 0.22 * scorch * noise1(s * 23 + a / 30, seed + 2) * noise1(a / 14 + s * 3, seed + 3));
    };
    const inBay = (s, a) => bay && s > bay.from && s < bay.to && Math.abs(a - 90) < bw;
    sheet(b, rows, cols, (j, i) => P[j][i], (j, i) => {
      const s = 0.5 * (sl[j] + sl[j + 1]), a = 0.5 * (al[i] + al[i + 1]);
      return inBay(s, a) ? null : s < so.cap ? cap : a < -wl || a > 180 + wl ? belly : top;
    }, {wrap: true, uv: (j, i, p) => [girth[j][i], p.z], tint: (skin) => (x, y, z) => this._tint(skin, soot(x, y, z))});
    const end = S.section(1), ring = al.map((a) => V3(...S.point(1, a)));
    sheet(b, 2, cols, (j, i) => (j ? V3(0, end.yc + 0.5 * (end.ht - end.hb), -L / 2) : ring[i]), () => "dark", {flip: V3(0, 0, -1)});
    let ai = [], si = [], sill = null;
    if (bay) {
      ai = al.filter((a) => a >= 90 - bw - 1e-6 && a <= 90 + bw + 1e-6); si = sl.filter((s) => s >= bay.from - 1e-9 && s <= bay.to + 1e-9); sill = (s, side) => V3(...S.point(s, 90 - side * bw));
      const floor = (s) => { const c = S.section(s); return c.yc - 0.35 * c.hb; };
      const trough = (s) => { const a = sill(s, 1), c = sill(s, -1), y = floor(s); return [a, V3(a.x * 0.96, mix(a.y, y, 0.5), a.z), V3(a.x * 0.9, y, a.z), V3(0, y, a.z), V3(c.x * 0.9, y, a.z), V3(c.x * 0.96, mix(c.y, y, 0.5), a.z), c]; };
      sheet(b, si.length, 7, (j, i) => trough(si[j])[i], () => "foil-silver", {flip: Y, uv: (j, i, p) => [p.x, p.z]});
      for (const [s, face] of [[bay.from, V3(0, 0, -1)], [bay.to, Z]]) { const t = trough(s), rim = [t[2], ...ai.map((a) => V3(...S.point(s, a))), t[4]]; sheet(b, 2, rim.length, (j, i) => (j ? V3(0, floor(s), L * (0.5 - s)) : rim[i]), () => "aluminium", {flip: face}); }
      if (!far) for (let k = 1; k < 5; k++) { const t = trough(mix(bay.from, bay.to, k / 5)); for (let i = 0; i < 6; i++) b.rod("aluminium", t[i].clone().setY(t[i].y + 0.04), t[i + 1].clone().setY(t[i + 1].y + 0.04), 0.05, 5); }
    }
    const g = b.group("body");
    g.userData.doors = [];
    if (bay) for (const side of [1, -1]) {
      const as = ai.filter((a) => side * (90 - a) >= -1e-6), db = this.bins(), pivot = sill(si[0], side), axis = sill(si[si.length - 1], side).sub(pivot).normalize();
      const at = (out) => (j, i) => V3(...S.point(si[j], as[i], out)).sub(pivot);
      sheet(db, si.length, as.length, at(0), () => top, {flip: Y, uv: (j, i, p) => [p.x, p.z], tint: (skin) => this._tint(skin, 0.1 * scorch)});
      sheet(db, si.length, as.length, at(-0.07), () => "radiator", {flip: V3(0, -1, 0), uv: (j, i, p) => [p.x, p.z]});
      const ga = 0.05 / Math.max(S.section(si[0]).ht, 0.2) / RAD, gs = 0.05 / L, line = (s0, s1, a0, a1) => sheet(db, 2, 2, (j, i) => V3(...S.point(j ? s1 : s0, i ? a1 : a0, 0.012)).sub(pivot), () => "plane-line", {flip: Y});
      line(bay.from, bay.to, 90 - side * ga, 90); line(bay.from, bay.to, 90 - side * bw, 90 - side * (bw - ga)); line(bay.from, bay.from + gs, 90 - side * bw, 90); line(bay.to - gs, bay.to, 90 - side * bw, 90);
      const door = moving(db.group("bay door"), pivot), tipArm = V3(...S.point(si[0], 90)).sub(pivot);
      door.userData.door = {axis, sign: turnTo(axis, tipArm, V3(side, 0.3, 0)), side};
      g.add(door); g.userData.doors.push(door);
    }
    const surface = (angle, along, out = 0) => { const s = 1 - along; return point(V3(...S.point(s, angle, out)), V3(...S.normal(clamp(s, 0.01, 0.99), angle)), Z); };
    g.userData.points = {fore: point(V3(0, S.section(0).yc, L / 2), Z, Y), aft: point(V3(0, end.yc + 0.5 * (end.ht - end.hb), -L / 2), V3(0, 0, -1), Y), zenith: surface(90, 0.5), nadir: surface(270, 0.5), port: surface(0, 0.5), starboard: surface(180, 0.5)};
    g.userData.surface = surface; g.userData.shape = S; g.userData.size = {radius: Math.max(S.width, S.height) / 2, length: L};
    return g;
  }

  /** A thin piece lying on a body (made by body()): from station `from` to `to`, from `a0` to `a1` degrees
   * round it, `out` metres off the surface, of surface `skin`; `text`: its picture's u runs along the body
   * (true) or against it (-1). Added to the bins `b`. */
  patch(b, body, {from, to, a0, a1, skin, out = 0.012, text = 0, tint = null}) {
    const S = body.userData.shape, ns = Math.max(2, Math.ceil(Math.abs(to - from) * S.length / (this.far ? 2 : 0.5)) + 1), nc = Math.max(2, Math.ceil(Math.abs(a1 - a0) / (this.far ? 12 : 5)) + 1);
    const mid = S.normal(clamp(0.5 * (from + to), 0.01, 0.99), 0.5 * (a0 + a1));
    sheet(b, ns, nc, (j, i) => V3(...S.point(mix(from, to, j / (ns - 1)), mix(a0, a1, i / (nc - 1)), out)), () => skin,
      {flip: V3(...mid), tint, uv: (j, i, p) => (text ? [text > 0 ? j / (ns - 1) : 1 - j / (ns - 1), i / (nc - 1)] : [p.z, p.y + p.x])});
    return b;
  }

  // one side of a wing or a tail: its sheets into `b`, its moving surfaces into `into`. M: where the flat panel
  // (x the span times `side`, y its thickness, z the chord backwards) stands in the part
  _panel(b, into, o, P, side, M, {skins, controls = [], start = 0, name = "wing"}) {
    const far = this.far, semi = P.semi, seed = this.seed, scorch = this.scorch;
    const fl = (y) => o.fillet * (y <= o.inboard ? 1 : Math.exp(-Math.pow((y - o.inboard) / (0.09 * semi + 0.25), 2)));
    const local = (eta, x, up, out = 0) => {
      const y = eta * semi, f = fl(y), c = P.chord(eta) * (1 + 0.1 * f), le = P.le(eta) - 0.06 * f * P.chord(eta), h = halfThickness(o.airfoil, clamp(x), o.thickness * (1 + 1.3 * f)) * c;
      const yy = (o.airfoil === "flat" ? (up ? 1.6 * h : -0.4 * h) : (up ? h : -h)) + (0.3 - x) * c * Math.tan(o.twist * RAD * eta) + (up ? out : -out);
      return V3(side * y, yy, -(le + x * c)).applyMatrix4(M);
    };
    const ctl = controls.map((c) => ({...c, hinge: 1 - c.chord}));
    const step = far ? 0.26 : o.curve > 0 ? 0.07 : 0.1, must = [start, 1, ...(o.crank > start ? [o.crank] : []), ...ctl.flatMap((c) => [c.from, c.to])], el = [];
    for (let e = start; e < 1; e += step) el.push(e);
    const etas = stations(el, must, step * 0.4), n = far ? 6 : 12, xs = stations(Array.from({length: n + 1}, (_, i) => 0.5 * (1 - Math.cos(Math.PI * i / n))), [0, 1, o.edge, ...ctl.map((c) => c.hinge)], 0.035), m = xs.length;
    const cols = 2 * m - 1, xOf = (r) => (r < m ? xs[m - 1 - r] : xs[r - m + 1]), upOf = (r) => r < m - 1;
    const sootAt = (eta, x) => clamp(x <= o.edge ? 0 : Math.min(1, 1.5 * scorch) * (0.3 + 0.9 * Math.pow(noise1(eta * semi * 2.2 + 11 * side, seed + 5), 1.5)) * Math.exp(-(x - o.edge) / ((0.06 + 0.3 * scorch) * (0.3 + 1.4 * noise1(eta * semi * 0.9, seed + 6)))) + 0.2 * scorch * noise1(eta * semi * 0.6 + x * 5, seed + 7));
    const inv = M.clone().invert(), w = V3(), tint = (skin) => (x, y, z) => { w.set(x, y, z).applyMatrix4(inv); const eta = clamp(Math.abs(w.x) / semi), c = Math.max(P.chord(eta), 1e-6); return this._tint(skin, sootAt(eta, clamp((-w.z - P.le(eta)) / c))); };
    const skinOf = (r, xm) => (xm < o.edge ? skins.edge : r < m - 1 ? skins.upper : skins.lower);
    const cut = (em, xm) => ctl.some((c) => em > c.from && em < c.to && xm > c.hinge);
    const uv = (j, r) => [etas[j] * semi, P.le(etas[j]) + xOf(r) * P.chord(etas[j])];
    const pivotAll = o.allMoving ? local(start, 0.42, true).lerp(local(start, 0.42, false), 0.5) : null, mb = pivotAll ? this.bins() : b, shift = pivotAll ?? V3();
    const tintOf = pivotAll ? (skin) => (x, y, z) => tint(skin)(x + shift.x, y + shift.y, z + shift.z) : tint;
    sheet(mb, etas.length, cols, (j, r) => local(etas[j], xOf(r), upOf(r)).sub(shift), (j, r) => { const em = 0.5 * (etas[j] + etas[j + 1]), xm = 0.5 * (xOf(r) + xOf(r + 1)); return cut(em, xm) ? null : skinOf(r, xm); },
      {flip: side > 0, uv, tint: tintOf});
    sheet(mb, 2, m, (j, i) => local(1, xs[i], j === 0).sub(shift), () => skins.upper, {flip: local(1, 0.5, true).sub(local(0.5, 0.5, true)), tint: tintOf});
    const out = {tip: local(1, 0.5, true), tipLe: local(1, 0, true), tipTe: local(1, 1, true), edge: etas.filter((e) => e * semi >= o.inboard * 0.9).map((e) => local(e, 0, true)), at: local, surfaces: []};
    for (const c of ctl) {
      const ce = etas.filter((e) => e >= c.from - 1e-9 && e <= c.to + 1e-9), cx = xs.filter((x) => x >= c.hinge - 1e-9), q = cx.length, cb = this.bins();
      const pivot = local(c.from, c.hinge, true).lerp(local(c.from, c.hinge, false), 0.5), far2 = local(c.to, c.hinge, true).lerp(local(c.to, c.hinge, false), 0.5), axis = far2.clone().sub(pivot).normalize();
      const cxOf = (r) => (r < q ? cx[q - 1 - r] : cx[r - q]), cUp = (r) => r < q;
      sheet(cb, ce.length, 2 * q, (j, r) => local(ce[j], cxOf(r), cUp(r)).sub(pivot), (j, r) => (r < q - 1 ? skins.upper : r === q - 1 ? "dark" : skins.lower), {flip: side > 0, uv: (j, r) => [ce[j] * semi, P.le(ce[j]) + cxOf(r) * P.chord(ce[j])],
        tint: (skin) => (x, y, z) => tint(skin)(x + pivot.x, y + pivot.y, z + pivot.z)});
      const g = moving(cb.group(c.name), pivot), arm = local(0.5 * (c.from + c.to), 1, true).sub(local(0.5 * (c.from + c.to), c.hinge, true)), d = V3().crossVectors(axis, arm).normalize();
      g.userData.control = {name: c.name, role: c.role ?? c.name, axis, pitch: -d.y, yaw: d.x, side, limit: c.limit ?? 40};
      into.add(g); out.surfaces.push(g);
    }
    if (pivotAll) {
      const g = moving(mb.group(name), pivotAll), axis = local(1, 0.42, true).sub(local(start, 0.42, true)).normalize(), d = V3().crossVectors(axis, local(start, 1, true).sub(pivotAll)).normalize();
      g.userData.control = {name, role: "canard", axis, pitch: -d.y, yaw: d.x, side, limit: 30};
      into.add(g); out.surfaces.push(g);
    }
    if (o.tip) {
      known("wing tip", o.tip, ["height", "cant", "sweep", "taper", "thickness"]);
      const h = number("wing tip height", o.tip.height ?? 0.1 * semi, 0.05, 50), cant = number("wing tip cant", o.tip.cant ?? 75, -90, 90);
      const to = wingOptions({span: 2 * h, rootChord: Math.max(0.05, P.chord(1)), tipChord: Math.max(0.02, P.chord(1) * (o.tip.taper ?? 0.45)), sweep: o.tip.sweep ?? 50, thickness: o.tip.thickness ?? o.thickness, airfoil: o.airfoil, dihedral: 0, fillet: 0, edge: o.edge});
      const M2 = M.clone().multiply(new THREE.Matrix4().makeTranslation(side * semi, 0, -P.le(1))).multiply(new THREE.Matrix4().makeRotationZ(side * cant * RAD));
      const tip = this._panel(b, into, to, wingPlanform({...to, __checked: true}), side, M2, {skins: {...skins, lower: cant < 0 ? skins.lower : skins.upper}});
      out.fin = tip; out.edge.push(...tip.edge);
    }
    return out;
  }

  /** A wing, both sides: ONE function for every wing. Options: `preset` (WINGS: a parameter set to start from),
   * `span` (tip to tip, metres), `rootChord` (at the middle line), `tipChord` (larger than the root's is
   * allowed), `sweep` (the leading edge's, degrees; negative: swept forward), `crank` + `sweepInner` (the
   * leading edge runs at `sweepInner` to that share of the half span: a strake, a double delta), `curve`
   * (0..1: an ogival leading edge), `dihedral` (degrees; negative: anhedral), `thickness` (a share of the
   * chord), `airfoil` ("round": a rounded leading edge and a sharp trailing edge; "sharp": a lens; "flat": flat
   * underneath), `twist` (degrees at the tip), `fillet` (0..1: how far the root swells into the body) with
   * `inboard` (metres from the middle to the body's side), `edge` (the dark leading edge's share of the chord),
   * `controls` ([{name: "elevon" | "flap", from, to (shares of the half span), chord (its share of the
   * chord)}]; default one elevon; [] for none), `tip` ({height, cant (degrees up from the wing; negative:
   * down), sweep, taper}: winglets or tip fins), `allMoving` (the whole side turns: a canard).
   * The part's origin is the root's leading edge on the middle line; +z forward, the chord runs to -z.
   * `userData.wing`: {planform, sides: [{side, tip, tipLe, tipTe, edge (points along the leading edge), at(eta,
   * x, upper, out)}], surfaces (the moving ones)}. Points: mount, port, starboard (the tips). */
  wing(o = {}) {
    const {skins = {}, ...rest} = o;
    const w = wingOptions(rest), P = wingPlanform({...w, __checked: true}), b = this.bins(), holder = new THREE.Group();
    const controls = (w.controls ?? (w.allMoving ? [] : [{name: "elevon", from: 0.3, to: 0.94, chord: 0.2}])).map((c) => {
      known("a wing control", c, ["name", "role", "from", "to", "chord", "limit"]);
      const role = choice("control", c.role ?? c.name ?? "elevon", CONTROLS);
      if (!(c.to > c.from) || c.from < 0 || c.to > 1) throw fail(`control "${c.name ?? role}": 0 <= from < to <= 1 (shares of the half span), got ${c.from} to ${c.to}`);
      return {name: c.name ?? role, role, from: c.from, to: c.to, chord: number("control chord", c.chord ?? 0.2, 0.05, 0.6), limit: c.limit};
    });
    const sk = {upper: skins.upper ?? "plane-top", lower: skins.lower ?? "plane-belly", edge: skins.edge ?? "plane-edge"}, start = clamp(0.5 * w.inboard / P.semi, 0, 0.6);
    const sides = [1, -1].map((side) => ({side, ...this._panel(b, holder, w, P, side, new THREE.Matrix4().makeRotationZ(side * w.dihedral * RAD), {skins: sk, controls, start, name: "canard"})}));
    const g = b.group("wing");
    for (const c of [...holder.children]) g.add(c);
    g.userData.sparse = true;
    g.userData.wing = {planform: P, options: w, sides, surfaces: sides.flatMap((s) => [...s.surfaces, ...(s.fin ? s.fin.surfaces : [])])};
    g.userData.points = {mount: point(V3(), Y.clone().negate(), Z), port: point(sides[0].tip.clone(), X, Z), starboard: point(sides[1].tip.clone(), X.clone().negate(), Z)};
    g.userData.size = {radius: P.semi, length: w.rootChord};
    return g;
  }

  /** Tails: `type` "single" (one fin), "twin" (two, `spacing` metres apart, leaning out by `cant` degrees:
   * default 12) or "vee" (two, `cant` 42: they stand for fin and tailplane). `height` (metres, along the fin),
   * `rootChord`, `tipChord`, `sweep`, `thickness`, `airfoil`, `rudder` (true, false or {from, to, chord}),
   * `sink` (metres the root stands inside the body). The origin is the root's leading edge. `userData.wing`
   * as a wing's. Point: mount. */
  fin(o = {}) {
    known("fin options", o, Object.keys(FIN));
    const f = filled(FIN, o), type = choice("fin type", f.type, FINS), cant = number("fin cant", f.cant ?? {single: 0, twin: 12, vee: 42}[type], -80, 80);
    const w = wingOptions({span: 2 * number("fin height", f.height, 0.1, 60), rootChord: f.rootChord, tipChord: f.tipChord ?? 0.4 * f.rootChord, sweep: f.sweep, thickness: f.thickness, airfoil: f.airfoil, dihedral: 0, fillet: 0.35, inboard: f.sink, edge: f.edge});
    const P = wingPlanform({...w, __checked: true}), b = this.bins(), holder = new THREE.Group(), r = f.rudder === true ? {} : f.rudder;
    if (r) known("rudder", r, ["from", "to", "chord", "limit"]);
    const controls = r ? [{name: "rudder", role: "rudder", from: r.from ?? 0.14, to: r.to ?? 0.93, chord: r.chord ?? 0.3, limit: r.limit}] : [];
    const places = type === "single" ? [[1, 0]] : [[1, f.spacing / 2], [-1, -f.spacing / 2]];
    const sides = places.map(([side, x]) => ({side, ...this._panel(b, holder, w, P, side, new THREE.Matrix4().makeTranslation(x, -f.sink * Math.cos(cant * RAD), 0).multiply(new THREE.Matrix4().makeRotationZ(side * (90 - cant) * RAD)),
      {skins: {upper: "plane-top", lower: "plane-top", edge: "plane-edge"}, controls})}));
    const g = b.group("fin");
    for (const c of [...holder.children]) g.add(c);
    g.userData.sparse = true; g.userData.wing = {planform: P, options: w, sides, surfaces: sides.flatMap((s) => s.surfaces)};
    g.userData.points = {mount: point(V3(), Y.clone().negate(), Z)}; g.userData.size = {radius: f.height, length: f.rootChord};
    return g;
  }

  /** Rocket bells for a tail's end: `count`, `exit` (a bell's exit radius), `kind` (the craft kit's engines:
   * "chemical", "vacuum", "air"), `layout` ("row", "block": two rows, "ring"), `gap` (between bells, in exit
   * radii), `sunk` (the share of an engine standing inside the body). The origin is the middle of the body's
   * end; the bells fire toward -z. `userData.nozzles`: [{p, radius}] (the exits). Point: mount. */
  nozzles(o = {}) {
    known("nozzles options", o, ["count", "exit", "kind", "layout", "gap", "sunk"]);
    const count = number("nozzles count", o.count ?? 2, 1, 12), re = number("nozzles exit", o.exit ?? 0.6, 0.05, 6), layout = choice("nozzles layout", o.layout ?? "row", LAYOUTS), gap = o.gap ?? 2.3, sunk = o.sunk ?? 0.3;
    const g = this.bins().group("nozzles"), places = [];
    if (layout === "ring" && count > 2) for (let i = 0; i < count; i++) { const a = TAU * i / count + Math.PI / 2; places.push([Math.cos(a) * re * gap * 0.5 / Math.sin(Math.PI / count), Math.sin(a) * re * gap * 0.5 / Math.sin(Math.PI / count)]); }
    else { const upper = layout === "block" ? Math.ceil(count / 2) : count, rowsOf = [upper, count - upper].filter((n) => n > 0); rowsOf.forEach((n, j) => { for (let i = 0; i < n; i++) places.push([(i - (n - 1) / 2) * re * gap, rowsOf.length === 1 ? 0 : (0.5 - j) * re * gap * 0.9]); }); }
    g.userData.nozzles = [];
    for (const [x, y] of places) {
      const e = this.engine({kind: o.kind ?? "chemical", exit: re}), len = e.userData.size.length;
      e.rotation.x = Math.PI / 2; e.position.set(x, y, len * sunk); g.add(e);
      g.userData.nozzles.push({p: V3(x, y, len * sunk - len), radius: re});
    }
    g.userData.sparse = true; g.userData.points = {mount: point(V3(), Z, Y)}; g.userData.size = {radius: re * gap * Math.max(1, count / 2), length: re * 3};
    return g;
  }

  /** An air-breathing engine pod along z: `length`, `radius`, `spike` (a cone in the intake), `pylon` (metres
   * of pylon over it; 0 none), `kind` (its exhaust: "air"). A lipped intake, a fat middle, a nozzle that fires
   * toward -z. The origin is its middle. `userData.pod`: {intake, exit (points), radius}. Point: mount (on top). */
  nacelle(o = {}) {
    known("nacelle options", o, ["length", "radius", "spike", "pylon", "kind"]);
    const L = number("nacelle length", o.length ?? 6, 0.5, 40), R = number("nacelle radius", o.radius ?? 0.8, 0.1, 6), b = this.bins(), sides = this.sides(32), py = o.pylon ?? 0;
    const prof = [[0.78, 0.5], [0.84, 0.47], [0.93, 0.36], [1, 0.12], [1, -0.12], [0.93, -0.36], [0.8, -0.5]].map(([r, y]) => [r * R, y * L]).reverse();
    const lathe = (p) => new THREE.LatheGeometry(p.map(([r, y]) => new THREE.Vector2(Math.max(r, 1e-4), y)), sides).rotateX(Math.PI / 2);
    b.add("plane-top", lathe(prof), {uv: [TAU * R, L]});
    b.add("plane-edge", lathe([[0.72 * R, 0.47 * L], [0.78 * R, 0.5 * L], [0.845 * R, 0.468 * L]].reverse()), {uv: "keep"});
    b.add("dark", lathe([[0.72 * R, 0.47 * L], [0.5 * R, 0.2 * L], [0.01, 0.2 * L]]), {uv: "keep"});
    if (o.spike ?? true) b.add("aluminium", lathe([[0.4 * R, 0.24 * L], [0.01, 0.5 * L + 0.5 * R]].reverse()), {uv: "keep"});
    b.add("dark", lathe([[0.8 * R, -0.5 * L], [0.5 * R, -0.42 * L], [0.01, -0.42 * L]].reverse()), {uv: "keep"});
    if (py > 0) b.box("plane-top", 0.22 * R, py + 0.5 * R, 0.5 * L, new THREE.Matrix4().makeTranslation(0, R * 0.75 + py / 2, -0.03 * L));
    const g = b.group("nacelle"), e = this.engine({kind: o.kind ?? "air", exit: 0.6 * R, length: 1.5 * R});
    e.rotation.x = Math.PI / 2; e.position.set(0, 0, -0.5 * L + 1.2 * R); g.add(e);
    g.userData.sparse = true; g.userData.pod = {intake: V3(0, 0, 0.5 * L), exit: V3(0, 0, -0.5 * L - 0.3 * R), radius: R};
    g.userData.points = {mount: point(V3(0, R + py, 0), Y, Z)}; g.userData.size = {radius: R, length: L};
    return g;
  }

  /** An air intake under a belly (for engines inside the body): a scoop `width` x `height` at its raked mouth,
   * `length` long, narrowing into the body toward the tail; a dark mouth with a lip. The origin is the middle of
   * its top (it stands 0.35 heights inside what it hangs from); the mouth looks along +z.
   * `userData.intake`: {mouth (a point), radius}. Point: mount. */
  intake(o = {}) {
    known("intake options", o, ["width", "height", "length", "skin"]);
    const w = number("intake width", o.width ?? 2, 0.1, 30), h = number("intake height", o.height ?? 0.7, 0.05, 10), l = number("intake length", o.length ?? 5, 0.2, 60), skin = o.skin ?? "plane-belly", b = this.bins(), top = 0.35 * h;
    const zf = l / 2, zl = l / 2 - 0.55 * h, zr = -l / 2, c = (x, y, z) => V3(x, y, z);
    const F = [c(w / 2, top, zf), c(-w / 2, top, zf), c(-w / 2, -h, zl), c(w / 2, -h, zl)], R = [c(0.36 * w, top, zr), c(-0.36 * w, top, zr), c(-0.36 * w, -0.12 * h, zr), c(0.36 * w, -0.12 * h, zr)];
    const quad = (name, q, out) => { const flip = V3().crossVectors(q[1].clone().sub(q[0]), q[3].clone().sub(q[0])).dot(out) < 0, v = flip ? [q[0], q[3], q[2], q[1]] : q, g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array([v[0], v[1], v[2], v[0], v[2], v[3]].flatMap((a) => [a.x, a.y, a.z])), 3)); g.computeVertexNormals(); b.add(name, g); };
    quad(skin, [F[3], F[2], R[2], R[3]], V3(0, -1, 0)); quad(skin, [F[0], F[3], R[3], R[0]], X); quad(skin, [F[1], F[2], R[2], R[1]], V3(-1, 0, 0)); quad(skin, [R[0], R[1], R[2], R[3]], V3(0, 0, -1));
    quad("dark", F, Z);
    const r = Math.max(0.03, 0.045 * h);
    for (const [a, d] of [[F[2], F[3]], [F[0], F[3]], [F[1], F[2]]]) b.rod("plane-edge", a, d, r, 6);
    if (!this.far && w > 3 * h) b.rod("plane-edge", c(0, top, zf), c(0, -h, zl), r, 6);
    const g = b.group("intake");
    g.userData.sparse = true; g.userData.intake = {mouth: V3(0, -h / 2, 0.5 * (zf + zl)), radius: 0.5 * h};
    g.userData.points = {mount: point(V3(), Y, Z)}; g.userData.size = {radius: w / 2, length: l};
    return g;
  }

  /** A landing gear leg hanging from its origin: `length` (to the ground), `wheel` (radius), `wheels` (1 or
   * 2), `fold` (1: it folds forward, -1: backward). An oleo strut, a brace, wheels with hubs. Moving:
   * `userData.gear.leg`. Point: mount. */
  gear(o = {}) {
    known("gear options", o, ["length", "wheel", "wheels", "fold"]);
    const L = number("gear length", o.length ?? 2, 0.2, 12), wr = number("gear wheel", o.wheel ?? 0.4, 0.05, 2), n = o.wheels ?? 2, fold = o.fold ?? 1, b = this.bins(), r = Math.max(0.04, wr * 0.2);
    const axle = V3(0, -(L - wr), 0), knee = V3(0, -(L - wr) * 0.55, 0), half = n > 1 ? wr * 0.62 : 0;
    b.rod("aluminium", V3(), knee, r * 1.3, 10); b.rod("steel", knee, axle, r * 0.85, 10);
    b.rod("aluminium", V3(0, -(L - wr) * 0.12, -fold * (L - wr) * 0.3), knee.clone().lerp(axle, 0.15), r * 0.6, 6);
    b.rod("steel", axle.clone().setX(-half - wr * 0.2), axle.clone().setX(half + wr * 0.2), r * 0.7, 8);
    for (const x of n > 1 ? [-half, half] : [0]) {
      b.add("rubber", new THREE.TorusGeometry(wr * 0.68, wr * 0.32, this.sides(10), this.sides(24)).rotateY(Math.PI / 2).translate(x, axle.y, 0), {uv: "keep"});
      b.add("aluminium", new THREE.CylinderGeometry(wr * 0.42, wr * 0.42, wr * 0.36, this.sides(14)).rotateZ(Math.PI / 2).translate(x, axle.y, 0), {uv: "keep"});
    }
    const leg = moving(b.group("gear leg"), V3()), g = this.bins().group("gear");
    g.add(leg); g.userData.sparse = true; g.userData.gear = {leg, fold, length: L, wheel: wr};
    g.userData.points = {mount: point(V3(), Y, Z), foot: point(V3(0, -L, 0), Y.clone().negate(), Z)}; g.userData.size = {radius: L / 2, length: L};
    return g;
  }

  /** Finish a plane from its body (parts fixed to it by their positions): see Plane. */
  plane(body, options = {}) { return new Plane(body, this, options); }
}
/** The parts of a plane: planeKit({seed, scheme, color, scorch, tile, registration, accent, detail, wear, lit}). */
export const planeKit = (options = {}) => new PlaneKit(options);

// ---------- a finished plane ----------
const OWN_UPDATE = ["controls", "gear", "bay", "auto", "cabin"];
// what a craft's update takes (vidgen/space-craft), for one message that names both
const CRAFT_UPDATE = ["sun", "target", "velocity", "radial", "thrust", "attitude", "throttle", "rcs", "lights", "camera", "height", "deploy", "spin"];
const CONTROL_KEYS = ["elevon", "roll", "rudder", "flap", "brake", "bodyFlap", "canard"];
const Q1 = new THREE.Quaternion();

/** A plane: a Craft of vidgen/space-craft (`object`: +z the nose, +y up, +x the left wing, the origin at the
 * body's middle; `update`, `fly`, `shade`, `occluders`, `size`, `engines`, `lights`, `materials`) with
 * controls({...}), gear(k), bay(k), `anchors` (named places for effects, in the plane's own axes, metres),
 * anchor(name) (one of them in the scene now), `surfaces` (the moving ones), `spec` (what it was built from). */
export class Plane extends Craft {
  constructor(root, kit, options = {}) {
    const {anchors = {}, spec = null, ...rest} = options;
    super(root, kit, {occlusion: 0.3, name: "plane", ...rest});
    root.position.set(0, 0, 0); this.object.updateMatrixWorld(true);                 // the origin stays the body's middle, gear up or down
    this.spec = spec; this.surfaces = []; this.doors = []; this.legs = []; this.wells = []; this.registration = kit.registration;
    root.traverse((n) => { const u = n.userData; if (u.control) this.surfaces.push(n); if (u.door) this.doors.push(n); if (u.gear) this.legs.push(u.gear); if (u.well) this.wells.push(n); });
    /** Named places, in the plane's axes: nose, tail, belly ({p, n, radius | length, width}), leadingEdges and
     * finEdges ([{side, points}]), wingTips, finTips, nozzles ([{p, n, radius}]), intakes, gear, ground (the
     * height the wheels stand on, gear down). */
    this.anchors = anchors;
    this.deflection = Object.fromEntries(CONTROL_KEYS.map((k) => [k, 0])); this.gearDown = 1; this.bayOpen = 0;
  }

  /** Turn the moving surfaces (degrees): `elevon` (+ the trailing edges down, both sides: nose down), `roll`
   * (+ a roll to the right: the left elevon down, the right one up), `rudder` (+ the trailing edge to the left:
   * the nose turns left; fins that lean over 27 degrees, a vee tail, also answer `elevon`), `flap` (+ down), `brake` (the brake petals'
   * opening), `bodyFlap` (+ down), `canard` (+ the leading edge up). What is not named keeps its angle. */
  controls(c = {}) {
    known("controls", c, CONTROL_KEYS);
    for (const k of Object.keys(c)) this.deflection[k] = number(`controls ${k}`, c[k], -90, 90);
    const d = this.deflection;
    for (const s of this.surfaces) {
      const u = s.userData.control;
      const angle = u.role === "elevon" ? (d.elevon + u.side * d.roll) * u.pitch : u.role === "flap" ? d.flap * u.pitch : u.role === "rudder" ? d.rudder * u.yaw + (Math.abs(u.pitch) > 0.45 ? d.elevon * u.pitch : 0) : u.role === "canard" ? d.canard * u.pitch
        : u.role === "bodyFlap" ? d.bodyFlap * u.pitch : u.role === "brake" ? Math.max(0, d.brake) * u.open : 0;
      u.angle = clamp(angle, -u.limit, u.limit);
      s.quaternion.setFromAxisAngle(u.axis, u.angle * RAD);
    }
    return this;
  }

  /** Lower (1) or raise (0) the landing gear: the doors open over the first third, the legs swing down after. */
  gear(k = 1) {
    this.gearDown = k = clamp(k);
    const open = smooth(0, 0.35, k), down = smooth(0.25, 1, k);
    for (const g of this.legs) g.leg.rotation.x = -g.fold * (1 - down) * 96 * RAD;
    for (const n of this.doors) if (n.userData.door.gear) { const u = n.userData.door; n.quaternion.setFromAxisAngle(u.axis, u.sign * open * 88 * RAD); }
    for (const w of this.wells) w.visible = k > 0.001;
    for (const g of this.legs) g.leg.visible = k > 0.001;
    return this;
  }

  /** Open (1) or close (0) the payload bay's doors. */
  bay(k = 1) {
    this.bayOpen = k = clamp(k);
    for (const n of this.doors) if (!n.userData.door.gear) { const u = n.userData.door; n.quaternion.setFromAxisAngle(u.axis, u.sign * smooth(0, 1, k) * 112 * RAD); }
    return this;
  }

  /** Light the cockpit from inside (0 dark glass, as by day; 1 a lit cabin at night). The portholes are lit by
   * the kit's `lit`, as a craft's windows. */
  cabin(k = 1) { this.cabinLight = k = clamp(k); this.materials["plane-canopy"].emissiveIntensity = 0.4 * k; return this; }

  /** A named place of `anchors` in the scene now: a THREE.Vector3 ("nose", "tail", "belly"), or the list of a
   * group's ("nozzles", "wingTips", "finTips", "intakes", "gear"; "leadingEdges" and "finEdges": lists of lines). */
  anchor(name) {
    const a = this.anchors[name];
    if (a === undefined || typeof a === "number") throw fail(`no anchor "${name}"${hint(name, Object.keys(this.anchors))}; anchors: ${Object.keys(this.anchors).filter((k) => typeof this.anchors[k] !== "number").join(", ")}`);
    this.object.updateMatrixWorld(true);
    const world = (p) => V3(...p).applyMatrix4(this.object.matrixWorld);
    return Array.isArray(a) ? a.map((x) => (x.points ? x.points.map(world) : world(x.p))) : world(a.p);
  }

  /** What looks wrong about this plane, as sentences (an empty list: nothing): a wing or a tail that does not
   * touch the body or hangs past its ends, a span that hardly leaves the body or is absurdly long, a wing whose
   * area sits at the nose or behind the tail, landing gear that does not reach below the belly, and a layout too
   * near a well-known real vehicle. A look is checked, not aerodynamics: nothing here says the plane would fly. */
  problems() {
    const out = [], body = this.root, S = body.userData.shape;
    if (!S) return out;
    const L = S.length, H = S.height, r1 = (x) => +x.toFixed(1);
    for (const c of body.children) {
      const u = c.userData, w = u.wing;
      if (w) {
        const what = u.part === "fin" ? "the tail" : w.options.allMoving ? "the canard" : "the wing", s0 = 0.5 - c.position.z / L, s1 = s0 + w.options.rootChord / L, sm = clamp(0.5 * (s0 + s1), 0.01, 0.99);
        if (s1 < 0 || s0 > 1) out.push(`${what} stands off the body's ${s1 < 0 ? "nose" : "tail"} (its root from ${r1(s0 * L)} to ${r1(s1 * L)} m behind the nose of a ${r1(L)} m body)`);
        else if (s0 < -0.03 || s1 > 1.06) out.push(`${what}'s root hangs ${r1(Math.max(-s0, s1 - 1) * L)} m past the body's ${s0 < -0.03 ? "nose" : "tail"}`);
        else if (c.position.y > S.top(sm) + 0.05 * H || c.position.y < S.bottom(sm) - 0.05 * H) out.push(`${what} does not touch the body: its root is ${r1(c.position.y > S.top(sm) ? c.position.y - S.top(sm) : S.bottom(sm) - c.position.y)} m ${c.position.y > S.top(sm) ? "above its back" : "under its belly"}`);
        if (u.part !== "wing" || w.options.allMoving) continue;
        const P = w.planform, span = w.options.span;
        if (P.semi < 1.1 * S.half(sm)) out.push(`the wing's span (${r1(span)} m) hardly leaves the body (${r1(2 * S.half(sm))} m wide there)`);
        if (span > 3 * L) out.push(`the wing's span (${r1(span)} m) is over three times the body's length (${r1(L)} m)`);
        let area = 0, moment = 0;
        for (let i = 0; i < 40; i++) { const eta = (i + 0.5) / 40, ch = P.chord(eta); area += ch; moment += ch * (P.le(eta) + 0.5 * ch); }
        const sc = s0 + moment / Math.max(area, 1e-9) / L;
        if (sc < 0.3 || sc > 0.95) out.push(`the middle of the wing's area is ${r1(sc * L)} m behind the nose of a ${r1(L)} m body: ${sc < 0.3 ? "too far forward" : "behind the tail"}`);
      }
      if (u.gear) {
        const foot = c.position.y - u.gear.length, s = clamp(0.5 - c.position.z / L, 0, 1), low = typeof this.anchors.low === "number" ? this.anchors.low : S.bottom(s);
        if (foot > low - 0.05) out.push(`the landing gear at ${r1(s * L)} m does not reach below the belly: its wheels end ${r1(foot - low)} m above the lowest part`);
      }
    }
    const sp = this.spec;
    if (sp && sp.wing && sp.fins && sp.engines) {
      const w = wingOptions(Object.fromEntries(Object.entries(sp.wing).filter(([k]) => k !== "at" && k !== "up")));
      if (w.crank > 0 && (w.sweepInner ?? w.sweep) > w.sweep + 10 && (sp.fins.type ?? "single") === "single" && sp.engines.count === 3 && !sp.canard)
        out.push("a double delta, one tall fin and three bells: this layout is close to a well-known real vehicle; change the wing, the tail or the engines");
    }
    return out;
  }

  /** Craft.update, and: `controls` ({...} as controls()), `gear`, `bay`, `cabin` (0..1), `auto` (true: on a flight of
   * ctx.flight the surfaces follow its rates by controlsFromRates, unless `controls` is given). */
  update(t = 0, options = {}) {
    known("update options", options, [...OWN_UPDATE, ...CRAFT_UPDATE]);
    const own = {}, rest = {};
    for (const [k, v] of Object.entries(options)) (OWN_UPDATE.includes(k) ? own : rest)[k] = v;
    super.update(t, rest);
    if (own.gear !== undefined) this.gear(own.gear);
    if (own.bay !== undefined) this.bay(own.bay);
    if (own.cabin !== undefined) this.cabin(own.cabin);
    const fl = this.flight;
    if (own.controls) this.controls(own.controls);
    else if (fl && fl.air && (own.auto ?? true)) {
      const f = fl.air, dt = 1 / f.fps, name = fl.name, deg = 1 / RAD;
      this.controls(controlsFromRates({bankRate: (f.bank(name, t + dt) - f.bank(name, t - dt)) / (2 * dt) * deg, pitchRate: (f.pitch(name, t + dt) - f.pitch(name, t - dt)) / (2 * dt) * deg,
        slowing: -(f.speed(name, t + dt) - f.speed(name, t - dt)) / (2 * dt), bank: f.bank(name, t) * deg}));
    }
    return this;
  }
}

// ---------- a plane from one description ----------
const SPEC_KEYS = ["body", "wing", "fins", "canard", "engines", "nacelles", "intakes", "gear", "cockpit", "windows", "markings", "brake", "bodyFlap", "rcs", "lights"];
const arr = (v) => v.toArray().map((x) => round(x, 1e-4));

// what stands on a body: everything a description names, each part placed by plain numbers
function assemble(kit, spec) {
  known("a plane's description", spec, SPEC_KEYS);
  if (!spec.body) throw fail("a plane's description needs {body: {...}}");
  const body = kit.body(spec.body), S = body.userData.shape, L = S.length, far = kit.far, zOf = (s) => L * (0.5 - s), d = kit.bins(), anchors = {};
  const end = S.section(1), noseAt = S.options.cap || 0.03;
  anchors.nose = {p: [0, S.section(0).yc, L / 2], n: [0, 0, 1], radius: round(Math.max(S.half(noseAt), 0.5 * (S.top(noseAt) - S.bottom(noseAt))))};
  anchors.tail = {p: [0, round(end.yc + 0.5 * (end.ht - end.hb)), -L / 2], n: [0, 0, -1], width: round(2 * end.w), height: round(end.ht + end.hb)};
  anchors.belly = {p: [0, round(S.bottom(0.5)), 0], n: [0, -1, 0], length: round(L * (1 - S.noseLength * 0.5)), width: round(2 * S.half(0.5))};
  anchors.leadingEdges = []; anchors.wingTips = []; anchors.finEdges = []; anchors.finTips = []; anchors.nozzles = []; anchors.intakes = []; anchors.gear = [];
  let wing = null, wingAt = null;
  const edges = (part, lists, tips) => { for (const s of part.userData.wing.sides) { lists.push({side: s.side > 0 ? "port" : "starboard", points: s.edge.map((p) => arr(p.clone().add(part.position)))}); tips.push({side: s.side > 0 ? "port" : "starboard", p: arr((s.fin ? s.fin.tip : s.tip).clone().add(part.position))}); } };
  const placed = (o, where) => { const {at = where.at, up = where.up, ...rest} = o; return {at: number(`${where.name} at`, at, 0, 1), up: number(`${where.name} up`, up, -1, 1), rest}; };
  const heightAt = (s, up) => { const c = S.section(s); return c.yc + (up >= 0 ? up * c.ht * 0.7 : up * c.hb * 0.82); };
  if (spec.wing) {
    const w = placed(spec.wing, {at: 0.4, up: -0.8, name: "wing"}), probe = wingOptions(w.rest), s = Math.min(w.at, 0.985 - probe.rootChord / L), sm = s + 0.5 * probe.rootChord / L;
    wing = kit.wing({...w.rest, inboard: w.rest.inboard ?? round(S.half(sm) * 0.92)});
    wing.position.set(0, heightAt(sm, w.up), zOf(s)); body.add(wing); wingAt = {s, chord: probe.rootChord};
    edges(wing, anchors.leadingEdges, anchors.wingTips);
  }
  if (spec.canard) {
    const w = placed(spec.canard, {at: 0.16, up: 0.1, name: "canard"}), probe = wingOptions({controls: [], ...w.rest}), sm = w.at + 0.5 * probe.rootChord / L;
    const c = kit.wing({allMoving: true, fillet: 0.2, ...w.rest, inboard: w.rest.inboard ?? round(S.half(sm) * 0.85)});
    c.position.set(0, heightAt(sm, w.up), zOf(w.at)); body.add(c);
    edges(c, anchors.leadingEdges, []);
  }
  if (spec.fins) {
    const {at = 0.78, ...rest} = spec.fins, f = filled(FIN, rest), s = Math.min(number("fins at", at, 0, 1), 0.99 - f.rootChord / L), sm = s + 0.5 * f.rootChord / L;
    const fin = kit.fin(rest), x = f.type === "single" ? 0 : f.spacing / 2;
    fin.position.set(0, Math.min(S.over(sm, x), S.over(s + 0.1 * f.rootChord / L, x)), zOf(s)); body.add(fin);
    edges(fin, anchors.finEdges, anchors.finTips);
  }
  if (spec.engines) {
    const {count = 2, layout = "row", exit = null, kind = "chemical"} = spec.engines;
    known("engines", spec.engines, ["count", "layout", "exit", "kind"]);
    const perRow = layout === "block" ? Math.ceil(count / 2) : layout === "ring" ? Math.ceil(count / 2) : count, rowsN = layout === "row" ? 1 : 2;
    const re = exit ?? round(Math.min(0.4 * (end.ht + end.hb) / rowsN, 2 * end.w / (perRow * 2.3 + 0.3)) * 0.92), nz = kit.nozzles({count, layout, exit: re, kind});
    nz.position.set(0, anchors.tail.p[1], -L / 2); body.add(nz);
    for (const n of nz.userData.nozzles) anchors.nozzles.push({p: arr(n.p.clone().add(nz.position)), n: [0, 0, -1], radius: n.radius, kind});
  }
  if (spec.nacelles) {
    known("nacelles", spec.nacelles, ["count", "length", "radius", "mount", "at", "kind", "spike"]);
    const n = spec.nacelles, mount = choice("nacelles mount", n.mount ?? "wing", ["wing", "body", "tail"]), count = n.count ?? 2, R = n.radius ?? 0.2 * S.height, len = n.length ?? 0.18 * L;
    if (mount === "wing" && !wing) throw fail("nacelles under a wing need a wing: `mount: \"body\"`, or give the plane a wing");
    for (let i = 0; i < count / 2; i++) for (const side of [1, -1]) {
      const pod = kit.nacelle({length: len, radius: R, kind: n.kind ?? "air", spike: n.spike ?? true, pylon: mount === "wing" ? 0.45 * R : mount === "tail" ? 0.6 * R : 0.2 * R});
      if (mount === "wing") {
        const info = wing.userData.wing.sides.find((x) => x.side === side), eta = (n.at ?? 0.4) + i * 0.24, under = info.at(eta, 0.5, false).add(wing.position);
        pod.position.set(under.x, under.y - 1.42 * R, under.z + 0.12 * len);
      } else if (mount === "tail") {
        const s = n.at ?? 0.84, c = S.section(s), y = c.yc + (0.35 + 0.5 * i) * c.ht, half = c.w * Math.pow(Math.max(0, 1 - Math.pow(clamp((y - c.yc) / c.ht, 0, 0.99), c.nt)), 1 / c.nt);
        pod.rotation.z = side * Math.PI / 2; pod.position.set(side * (half + 1.45 * R), y, zOf(s));
      } else { const s = n.at ?? 0.62, x = side * (0.5 + i) * 2.4 * R; pod.position.set(x, S.under(s, x) - 1.15 * R, zOf(s)); }
      body.add(pod);
      anchors.nozzles.push({p: arr(pod.userData.pod.exit.clone().add(pod.position)), n: [0, 0, -1], radius: round(0.6 * R), kind: n.kind ?? "air"});
      anchors.intakes.push({p: arr(pod.userData.pod.intake.clone().add(pod.position)), n: [0, 0, 1], radius: round(0.78 * R)});
    }
  }
  if (spec.intakes) {
    known("intakes", spec.intakes, ["count", "at", "width", "height", "length"]);
    const n = spec.intakes, count = choice("intakes count", n.count ?? 1, [1, 2]), s = number("intakes at", n.at ?? 0.55, 0, 1), w = n.width ?? (count > 1 ? 0.3 : 0.62) * 2 * S.half(s), h = n.height ?? 0.16 * S.height, len = n.length ?? 0.14 * L;
    for (const x of count > 1 ? [0.55 * S.half(s), -0.55 * S.half(s)] : [0]) {
      const scoop = kit.intake({width: w, height: h, length: len}), y = Math.min(...[-0.5, -0.25, 0, 0.25, 0.5].flatMap((k) => [S.under(s - k * len / L, x - w / 2), S.under(s - k * len / L, x + w / 2), S.under(s - k * len / L, x)]));
      scoop.position.set(x, y, zOf(s)); body.add(scoop);
      anchors.intakes.push({p: arr(scoop.userData.intake.mouth.clone().add(scoop.position)), n: [0, 0, 1], radius: round(scoop.userData.intake.radius)});
    }
  }
  // doors on the body's own surface: a patch that turns about one of its edges
  const door = (from, to, a0, a1, hinge, skin, inner, want) => {
    const db = kit.bins(), ns = far ? 2 : 4, nc = far ? 2 : 4, P = (j, i, out) => V3(...S.point(mix(from, to, j / (ns - 1)), mix(a0, a1, i / (nc - 1)), out));
    const pivot = hinge === "front" ? P(0, 0, 0) : P(0, hinge === "a0" ? 0 : nc - 1, 0), far2 = hinge === "front" ? P(0, nc - 1, 0) : P(ns - 1, hinge === "a0" ? 0 : nc - 1, 0), axis = far2.clone().sub(pivot).normalize();
    const face = V3(...S.normal(0.5 * (from + to), 0.5 * (a0 + a1)));
    sheet(db, ns, nc, (j, i) => P(j, i, 0.015).sub(pivot), () => skin, {flip: face, uv: (j, i, p) => [p.x + p.y, p.z]});
    sheet(db, ns, nc, (j, i) => P(j, i, -0.03).sub(pivot), () => inner, {flip: face.clone().negate(), uv: (j, i, p) => [p.x + p.y, p.z]});
    const g = moving(db.group("door"), pivot), arm = P(ns - 1, hinge === "a0" ? nc - 1 : hinge === "a1" ? 0 : Math.floor(nc / 2), 0).sub(pivot);
    body.add(g);
    return {g, axis, sign: turnTo(axis, arm, want ?? face), face};
  };
  if (spec.gear ?? true) {
    const gs = spec.gear === true || spec.gear === undefined ? {} : spec.gear;
    known("gear", gs, ["nose", "main", "track", "clearance", "wheel"]);
    const sn = gs.nose ?? Math.max(0.1, S.noseLength * 0.62), sm = gs.main ?? (wingAt ? clamp(wingAt.s + 0.62 * wingAt.chord / L, 0.45, 0.8) : 0.62), track = gs.track ?? S.half(sm) * 1.3, wr = gs.wheel ?? round(clamp(0.011 * L + 0.12, 0.2, 0.9));
    const low = Math.min(S.bottom(0.5), S.bottom(sm), ...anchors.nozzles.map((n) => n.p[1] - n.radius * 1.2), ...anchors.intakes.map((n) => n.p[1] - n.radius * 1.3)), ground = low - (gs.clearance ?? 0.07 * L * 0.2 + 0.5);
    anchors.ground = round(ground); anchors.low = round(low);
    for (const [s, x, n, fold] of [[sn, 0, "nose", 1], [sm, track / 2, "port", -1], [sm, -track / 2, "starboard", -1]]) {
      const yb = S.under(s, x), top = yb + 0.12, c = S.section(s), q = clamp(Math.abs(x) / c.w, 0, 0.98), ang = 270 + Math.sign(x) * Math.asin(Math.pow(q, c.nb / 2)) / RAD;
      const leg = kit.gear({length: top - ground, wheel: n === "nose" ? wr * 0.8 : wr, wheels: 2, fold});
      leg.position.set(x, top, zOf(s)); body.add(leg);
      const hl = (1.25 * (top - ground)) / L, s0 = fold > 0 ? s - hl : s - 0.02, s1 = fold > 0 ? s + 0.02 : s + hl, da = Math.min(24, Math.max(6, (1.5 * wr / Math.max(c.w, 0.1)) / RAD * 0.6));
      const wb = kit.bins(); kit.patch(wb, body, {from: s0, to: s1, a0: ang - da, a1: ang + da, skin: "plane-line", out: 0.006});
      const well = wb.group("gear well"); well.userData.moving = true; well.userData.sparse = true; well.userData.well = true; body.add(well);
      for (const [a0, a1, hinge] of [[ang - da, ang, "a0"], [ang, ang + da, "a1"]]) { const dr = door(s0, s1, a0, a1, hinge, "plane-belly", "aluminium", V3(0, -1, 0)); dr.g.userData.door = {axis: dr.axis, sign: dr.sign, gear: true}; }
      anchors.gear.push({name: n, p: [round(x), round(ground), round(zOf(s))], n: [0, -1, 0]});
    }
  }
  if (spec.brake ?? false) {
    const bs = spec.brake === true ? {} : spec.brake;
    known("brake", bs, ["from", "to", "angle", "width"]);
    const from = bs.from ?? 1 - S.tailLength * 1.25, to = bs.to ?? from + 0.075, a = bs.angle ?? 38, wdt = bs.width ?? 20;
    for (const side of [1, -1]) {
      const mid = side > 0 ? a : 180 - a, dr = door(from, to, mid - wdt, mid + wdt, "front", "plane-top", "aluminium", null);
      dr.g.userData.control = {name: "brake", role: "brake", axis: dr.axis, open: dr.sign, side, limit: 70, pitch: 0, yaw: 0};
    }
  }
  if (spec.bodyFlap ?? false) {
    const fb = kit.bins(), wdt = 2 * end.w * 0.8, len = (spec.bodyFlap === true ? 0.07 : number("bodyFlap", spec.bodyFlap, 0.01, 0.3)) * L, y = end.yc - end.hb, pivot = V3(0, y + 0.08, -L / 2);
    fb.box("plane-belly", wdt, 0.14, len, new THREE.Matrix4().makeTranslation(0, 0, -len / 2), {tint: [1.15, 1.15, 1.15]});
    const g = moving(fb.group("body flap"), pivot);
    g.userData.control = {name: "bodyFlap", role: "bodyFlap", axis: X.clone(), pitch: -1, yaw: 0, side: 0, limit: 30};
    body.add(g);
  }
  // the cockpit's panes, portholes, stripes, the registration, number blocks
  const ck = spec.cockpit === undefined ? {} : spec.cockpit;
  if (ck) {
    known("cockpit", ck, ["style", "panes", "at", "width", "length", "lit"]);
    const style = choice("cockpit style", ck.style ?? "panes", ["panes", "band"]), s0 = ck.at ?? S.noseLength * 0.58, s1 = s0 + (ck.length ?? clamp(0.055 * L, 0.8, 2.0) / L), half = ck.width ?? 40, n = style === "band" ? 1 : (ck.panes ?? 4);
    kit.patch(d, body, {from: s0 - 0.12 / L, to: s1 + 0.12 / L, a0: 90 - half - 3, a1: 90 + half + 3, skin: "plane-line", out: 0.008});
    for (let i = 0; i < n; i++) { const a0 = 90 - half + (2 * half) * i / n + (n > 1 ? 2 : 0), a1 = 90 - half + (2 * half) * (i + 1) / n - (n > 1 ? 2 : 0); kit.patch(d, body, {from: s0, to: s1, a0, a1, skin: (ck.lit ?? true) ? "plane-canopy" : "plane-glass", out: 0.02}); }
    anchors.cockpit = {p: S.point(0.5 * (s0 + s1), 90), n: S.normal(0.5 * (s0 + s1), 90)};
  }
  if (spec.windows) {
    const m = spec.markings === undefined ? {} : spec.markings, past = m ? (m.at ?? clamp(S.noseLength + 0.05, 0.2, 0.6)) + ((m.stripes ?? 1) + 0.3) * 0.9 / L * (1 + L / 40) : 0;
    const count = number("windows", spec.windows, 1, 80), s0 = Math.max(S.noseLength + 0.03, past), s1 = 1 - S.tailLength - 0.08, size = 0.42 / L;
    for (let i = 0; i < count; i++) for (const side of [1, -1]) {
      const s = mix(s0, s1, (i + 0.5) / count), a = side > 0 ? 44 : 136, lit = hash1(i * 2 + (side > 0 ? 0 : 1), kit.seed + 77) < kit.options.lit;
      kit.patch(d, body, {from: s - size / 2, to: s + size / 2, a0: a - 2.2, a1: a + 2.2, skin: lit ? "plane-window" : "plane-glass", out: 0.014});
    }
  }
  const mk = spec.markings === undefined ? {} : spec.markings;
  if (mk) {
    known("markings", mk, ["stripes", "numbers", "registration", "at"]);
    const wl = S.options.waterline, stripes = mk.stripes ?? 1, sAt = mk.at ?? clamp(S.noseLength + 0.05, 0.2, 0.6), wd = 0.5 / L * (1 + L / 40);
    for (let i = 0; i < stripes; i++) kit.patch(d, body, {from: sAt + i * wd * 1.8, to: sAt + i * wd * 1.8 + wd * (i ? 0.5 : 1), a0: -wl + 1, a1: 180 + wl - 1, skin: "plane-accent"});
    if (mk.registration ?? true) {
      const hT = clamp(0.2 * S.height, 0.35, 1.6), len = hT * (kit.registration.length * 6 + 1) / 9 / L, sR = Math.max(sAt + (stripes + 0.5) * wd * 1.8, wingAt ? wingAt.s - len - 0.01 : 0), c = S.section(sR + len / 2), da = hT / Math.max(c.ht, 0.2) / RAD * 0.5;
      kit.patch(d, body, {from: sR, to: sR + len, a0: 26 - da, a1: 26 + da, skin: "plane-mark", text: 1, out: 0.014});
      kit.patch(d, body, {from: sR, to: sR + len, a0: 154 + da, a1: 154 - da, skin: "plane-mark", text: -1, out: 0.014});
    }
    if (wing && (mk.numbers ?? true)) {
      const info = wing.userData.wing, P = info.planform;
      for (const s of info.sides) {
        const e0 = 0.42, e1 = Math.min(0.78, e0 + 0.3), x0 = 0.3, x1 = Math.min(0.62, x0 + (e1 - e0) * P.semi * 9 / (kit.registration.length * 6 + 1) / Math.max(P.chord(0.6), 0.5));
        const at = (u, v) => s.at(s.side > 0 ? mix(e1, e0, u) : mix(e0, e1, u), mix(x1, x0, v), true, 0.02).add(wing.position);
        if (P.chord(e1) * (x1 - x0) > 0.4) sheet(d, 3, 6, (j, i) => at(i / 5, j / 2), () => "plane-mark", {flip: Y, uv: (j, i) => [i / 5, j / 2]});
        sheet(d, 2, 5, (j, i) => s.at(mix(0.9, 0.97, j), mix(0.08, 0.95, i / 4), true, 0.015).add(wing.position), () => "plane-accent", {flip: Y});
      }
    }
  }
  if (!far) {
    // blade aerials on the back and the belly, a pitot rod on the nose
    for (const [s, a] of [[0.36, 90], [0.52, 90], [0.44, 270]]) { const p = V3(...S.point(s, a)), up = a === 90 ? 1 : -1, h = 0.012 * L + 0.2; d.add("plane-edge", new THREE.BoxGeometry(0.025, h, h * 0.6).rotateX(0.45 * up).translate(p.x, p.y + up * h * 0.4, p.z)); }
    const tip = V3(0, S.section(0).yc, L / 2); d.rod("steel", tip.clone().add(V3(0, 0, -0.05)), tip.clone().add(V3(0, 0, 0.012 * L + 0.25)), 0.012 + L * 0.0002, 5);
  }
  const details = d.group("details"); details.userData.sparse = true; body.add(details);
  if (spec.rcs ?? true) for (const [s, a] of [[S.noseLength * 0.75, 40], [S.noseLength * 0.75, 140], [1 - S.tailLength * 0.5, 55], [1 - S.tailLength * 0.5, 125]]) {
    const size = clamp(0.006 * L + 0.05, 0.1, 0.4), q = kit.thrusters({size}), p = V3(...S.point(s, a, -0.55 * size)), n = V3(...S.normal(s, a));
    q.quaternion.setFromUnitVectors(Y, n); q.position.copy(p); q.userData.sparse = true; body.add(q);
  }
  if (spec.lights ?? true) {
    const size = clamp(0.004 * L, 0.05, 0.25), put = (kind, p, n) => { const l = kit.light({kind, size}); l.quaternion.setFromUnitVectors(Y, n); l.position.copy(p).addScaledVector(n, -size * 0.6); body.add(l); };
    if (wing) for (const s of wing.userData.wing.sides) put(s.side > 0 ? "port" : "starboard", (s.fin ? s.fin.tip : s.tip).clone().add(wing.position), V3(s.side, 0.2, 0).normalize());
    put("white", V3(0, anchors.tail.p[1] + end.ht * 0.9, -L / 2 + 0.05), V3(0, 0.3, -1).normalize());
    put("beacon", V3(...S.point(0.45, 90)), Y); put("beacon", V3(...S.point(0.5, 270)), Y.clone().negate()); put("strobe", V3(...S.point(1 - S.tailLength, 90)), Y);
  }
  return {body, anchors};
}

const range2 = (r, a, b, step = 0.01) => round(range(r, a, b), step);
const DESIGNS = {
  // a small crewed orbital glider: a flattened, chined nose, a plain delta low on a flat belly, two fins leaning out, a bay
  glider(r) {
    const L = range2(r, 22, 30, 0.1), W = round(L * range(r, 0.15, 0.17), 0.05), span = round(L * range(r, 0.62, 0.72), 0.1);
    return {body: {length: L, width: W, height: round(W * 0.82, 0.05), nose: "chined", noseLength: range2(r, 0.3, 0.36), droop: 0.12, belly: 0.78, tail: 0.8, tailLength: 0.14, upsweep: 0.55, bay: {from: 0.43, to: 0.74, width: 36}, cap: 0.045, waterline: 6},
      wing: {preset: pick(r, ["delta", "delta", "ogival"]), span, sweep: range2(r, 54, 60, 0.5), dihedral: 4, at: 0.4, up: -0.75, controls: [{name: "elevon", from: 0.36, to: 0.95, chord: 0.18}, {name: "flap", from: 0.16, to: 0.36, chord: 0.14}]},
      fins: {type: "twin", height: round(L * 0.15, 0.05), rootChord: round(L * 0.17, 0.05), sweep: 48, cant: range2(r, 18, 26, 1), spacing: round(W * 0.78, 0.05), at: 0.8},
      engines: {count: 2, layout: "row", kind: "vacuum"}, cockpit: {style: "panes", panes: 4}, markings: {stripes: pick(r, [1, 2])}, brake: true, bodyFlap: true, gear: {}};
  },
  // a large cargo spaceplane: a wide, low body with a blunt nose and a cabin hump, short thick wings drooping from its
  // shoulders, one tall fin, air-breathing pods under the wings, a row of bells
  freighter(r) {
    const L = range2(r, 56, 74, 0.5), W = round(L * range(r, 0.2, 0.235), 0.1), H = round(W * range(r, 0.4, 0.46), 0.1);
    return {body: {length: L, width: W, height: H, nose: "blunt", noseLength: 0.24, droop: 0.22, belly: 0.9, tail: 0.86, tailLength: 0.12, upsweep: 0.9, hump: {from: 0.05, to: 0.3, height: range2(r, 0.22, 0.32)}, bay: {from: 0.36, to: 0.8, width: 44}, cap: 0.035, waterline: 4},
      wing: {preset: "stub", span: round(W * range(r, 2.5, 2.9), 0.1), chord: 0.6, taper: 0.4, sweep: range2(r, 44, 52, 0.5), dihedral: -range2(r, 5, 9, 0.5), at: 0.42, up: 0.3, thickness: 0.08, controls: [{name: "elevon", from: 0.5, to: 0.95, chord: 0.18}, {name: "flap", from: 0.3, to: 0.5, chord: 0.18}]},
      fins: {type: pick(r, ["single", "single", "twin"]), height: round(L * 0.15, 0.1), rootChord: round(L * 0.2, 0.1), sweep: 42, spacing: round(W * 0.6, 0.1), at: 0.76},
      engines: {count: pick(r, [4, 5]), layout: "row", kind: "vacuum"}, nacelles: {count: 2, mount: "wing", at: 0.56, radius: round(H * 0.24, 0.05), length: round(L * 0.17, 0.1)},
      cockpit: {style: "band", width: 38, at: 0.075, length: 0.012}, windows: 0, markings: {stripes: 2}, bodyFlap: true, gear: {}};
  },
  // a single-stage needle: a long pointed body with a row of windows, a cranked arrow wing far back, a vee tail, its
  // engines inside the body behind one wide intake under the belly
  needle(r) {
    const L = range2(r, 60, 78, 0.5), W = round(L * range(r, 0.062, 0.072), 0.05), span = round(L * range(r, 0.36, 0.42), 0.1);
    return {body: {length: L, width: W, height: round(W * 0.96, 0.05), nose: "needle", noseLength: range2(r, 0.4, 0.46), droop: 0.04, belly: 0.5, tail: 0.74, tailLength: 0.16, upsweep: 0.25, cap: 0.03, waterline: 14},
      wing: {preset: pick(r, ["cranked-arrow", "cranked-arrow", "double-delta"]), span, at: 0.5, up: -0.55, dihedral: 0, fillet: 0.7, controls: [{name: "elevon", from: 0.6, to: 0.95, chord: 0.2}, {name: "flap", from: 0.22, to: 0.52, chord: 0.12}]},
      fins: {type: "vee", height: round(L * 0.085, 0.05), rootChord: round(L * 0.1, 0.05), sweep: 56, cant: range2(r, 38, 48, 1), spacing: round(W * 0.5, 0.05), at: 0.86},
      engines: {count: pick(r, [2, 4]), layout: "row", kind: "chemical"}, intakes: {count: 1, at: range2(r, 0.6, 0.66), width: round(W * 0.8, 0.05), height: round(W * 0.2, 0.05), length: round(L * 0.2, 0.1)},
      cockpit: {style: "band", width: 44, at: 0.2, length: 0.012}, windows: Math.round(range(r, 14, 22)), markings: {stripes: 1, at: 0.3}, gear: {}};
  },
  // a lifting-body shuttle: a wide flat-bellied body that is most of the wing, short blended wings with tall tip
  // fins, a blunt nose with a cabin hump, a block of bells
  lifter(r) {
    const L = range2(r, 16, 22, 0.1), W = round(L * range(r, 0.3, 0.35), 0.05), H = round(W * range(r, 0.5, 0.58), 0.05), centre = r() < 0.4;
    const span = round(W * range(r, 2.05, 2.35), 0.1), sweep = range2(r, 52, 60, 0.5), root = round(L * range(r, 0.56, 0.62), 0.1);
    return {body: {length: L, width: W, height: H, nose: "blunt", noseLength: range2(r, 0.3, 0.36), droop: 0.24, belly: 0.9, tail: 0.92, tailLength: 0.1, upsweep: 0.9, hump: {from: 0.08, to: 0.52, height: range2(r, 0.16, 0.26)}, cap: 0.06, waterline: 4},
      wing: {preset: "blended", crank: 0, span, sweep, rootChord: root, tipChord: round(Math.max(0.3 * root, 0.92 * (root - 0.5 * span * Math.tan(sweep * RAD))), 0.05), at: 0.35, up: -0.45, dihedral: range2(r, 5, 10, 0.5),
        tip: {height: round(L * range(r, 0.15, 0.19), 0.05), cant: range2(r, 58, 72, 1), sweep: 46, taper: 0.5}, controls: [{name: "elevon", from: 0.55, to: 0.96, chord: 0.14}]},
      fins: centre ? {type: "single", height: round(L * 0.1, 0.05), rootChord: round(L * 0.14, 0.05), sweep: 50, at: 0.82} : null,
      engines: {count: pick(r, [2, 4]), layout: "block", kind: "chemical"}, cockpit: {style: "panes", panes: 3, width: 42, at: 0.14}, markings: {stripes: 1}, bodyFlap: true, gear: {clearance: 0.9}};
  },
  // an atmospheric scout for other worlds: a slim round body, long thin wings high on its back for thin air, winglets,
  // a vee tail, one small bell, no crew
  scout(r) {
    const L = range2(r, 9, 13, 0.1), W = round(L * range(r, 0.1, 0.12), 0.05), span = round(L * range(r, 1.9, 2.5), 0.1);
    return {body: {length: L, width: W, height: round(W * 1.08, 0.05), nose: pick(r, ["ogive", "pointed"]), noseLength: range2(r, 0.24, 0.3), droop: 0.1, belly: 0.2, tail: 0.42, tailLength: 0.4, upsweep: 0.5, cap: 0.06, waterline: 30},
      wing: {preset: "long", span, sweep: range2(r, 0, 7, 0.5), at: 0.36, up: 0.62, dihedral: range2(r, 2, 5, 0.5), fillet: 0.3, tip: {height: round(span * 0.035, 0.05), cant: 70}, controls: [{name: "elevon", from: 0.55, to: 0.96, chord: 0.26}, {name: "flap", from: 0.12, to: 0.55, chord: 0.26}]},
      fins: {type: "vee", height: round(L * 0.17, 0.05), rootChord: round(L * 0.1, 0.05), sweep: 24, cant: range2(r, 36, 46, 1), spacing: round(W * 0.2, 0.05), at: 0.88, sink: 0.1},
      engines: {count: 1, kind: "chemical"}, cockpit: false, markings: {stripes: pick(r, [1, 2]), at: 0.3}, rcs: false, gear: {}};
  },
  // a small air-launched skiff: a round ogive body, swept wings with winglets, small canards, two upright fins, one bell
  skiff(r) {
    const L = range2(r, 12, 17, 0.1), W = round(L * range(r, 0.16, 0.18), 0.05), span = round(L * range(r, 0.72, 0.86), 0.1);
    return {body: {length: L, width: W, height: round(W * 1.05, 0.05), nose: "ogive", noseLength: range2(r, 0.3, 0.36), droop: 0.08, belly: 0.3, tail: 0.6, tailLength: 0.24, upsweep: 0.3, cap: 0.05, waterline: 16},
      wing: {preset: "swept", span, sweep: range2(r, 34, 42, 0.5), at: 0.44, up: -0.3, dihedral: 2, tip: {height: round(span * 0.07, 0.05), cant: 78}, controls: [{name: "elevon", from: 0.5, to: 0.95, chord: 0.24}, {name: "flap", from: 0.2, to: 0.5, chord: 0.22}]},
      canard: {span: round(span * 0.36, 0.05), preset: "swept", chord: 0.34, at: 0.2, up: 0.15, dihedral: 0},
      fins: {type: "twin", height: round(L * 0.17, 0.05), rootChord: round(L * 0.16, 0.05), sweep: 40, cant: 6, spacing: round(W * 0.7, 0.05), at: 0.8},
      engines: {count: 1, kind: "chemical"}, cockpit: {style: "panes", panes: 2, width: 34}, markings: {stripes: pick(r, [1, 2, 3])}, gear: {}};
  },
};
/** The ready-made planes: what each is and its size (metres). Each is an invented design. */
export const PLANES = Object.freeze({
  glider: Object.freeze({label: "a small crewed orbital glider: a flattened chined nose, a delta low on a flat belly, two fins leaning out, a payload bay, two bells", scale: "22 to 30 m long, 14 to 21 m span"}),
  freighter: Object.freeze({label: "a large cargo spaceplane: a wide low body with a blunt nose and a cabin hump, short thick drooping wings, a tall tail, two air-breathing pods, a row of bells, a long bay", scale: "56 to 74 m long, 11 to 17 m wide, 28 to 50 m span"}),
  needle: Object.freeze({label: "a single-stage needle: a long pointed body with a row of windows, a cranked wing far back, a vee tail, its engines inside the body behind an intake under the belly", scale: "60 to 78 m long, 4 to 5.5 m across, 22 to 33 m span"}),
  lifter: Object.freeze({label: "a lifting-body shuttle: a wide flat-bellied body, short blended wings with tall tip fins, a blunt nose with a cabin hump, a block of bells", scale: "16 to 22 m long, 5 to 7.5 m wide, 9 to 15 m span"}),
  scout: Object.freeze({label: "an atmospheric scout for other worlds, no crew: a slim body, long thin wings for thin air with winglets, a vee tail, one small bell", scale: "9 to 13 m long, 17 to 32 m span"}),
  skiff: Object.freeze({label: "a small air-launched skiff: a round ogive body, swept wings with winglets, canards, two upright fins, one bell", scale: "12 to 17 m long, 9 to 15 m span"}),
});
const kindSeed = (kind) => [...kind].reduce((s, c) => (Math.imul(s, 31) + c.charCodeAt(0)) >>> 0, 7);
const WEAR = {glider: [0.15, 0.7], freighter: [0.2, 0.8], needle: [0.05, 0.4], lifter: [0.3, 0.9], scout: [0, 0.3], skiff: [0.1, 0.6]};
const LOOKS = {glider: ["grey", "dark", "grey"], freighter: ["grey", "tiles", "paint"], needle: ["metal", "paint", "grey"], lifter: ["tiles", "grey", "paint"], scout: ["plain", "plain", "metal"], skiff: ["paint", "tiles", "metal"]};
const merged = (base, over) => { const out = {...base}; for (const [k, v] of Object.entries(over)) out[k] = v && typeof v === "object" && !Array.isArray(v) && base[k] && typeof base[k] === "object" ? {...base[k], ...v} : v; return out; };
/** The description of a ready-made plane (plain numbers and words: what planeFrom takes): `kind` (PLANES),
 * {seed (1), and any part of the description to replace: body, wing, fins, canard, engines, nacelles, gear,
 * cockpit, windows, markings, brake, bodyFlap, rcs, lights; an object is laid over the design's, `false` or
 * `null` removes the part}. Also returns `scheme` and `scorch` as the seed chose them. */
export function planeSpec(kind, options = {}) {
  if (!DESIGNS[kind]) throw fail(`no plane "${kind}"${hint(String(kind), Object.keys(PLANES))}; planes: ${Object.keys(PLANES).join(", ")}`);
  const {seed = 1, ...over} = options;
  known(`planeSpec("${kind}") options`, over, SPEC_KEYS);
  const r = rng((seed * 2654435761 + kindSeed(kind)) >>> 0), spec = DESIGNS[kind](r), scheme = pick(r, LOOKS[kind]), scorch = range2(r, ...WEAR[kind]);
  return {spec: merged(spec, over), scheme, scorch};
}
const PLANE_KEYS = ["name", "occlusion", "camera", "height", "sun", "target", "lights", "marker"];
/** A plane from one description: `spec` ({body: {...}, wing, fins, canard, engines, nacelles, gear, cockpit,
 * windows, markings, brake, bodyFlap, rcs, lights}: the options of the kit's parts, and where each stands: `at`
 * (a share of the length from the nose), `up` (-1 the belly .. 1 the back)), `options`: the plane kit's, a
 * craft's (camera, height, sun, lights, marker, name, occlusion) and `gear`, `bay` (0..1 at the start). */
export function planeFrom(spec, options = {}) {
  const kitKeys = [...KIT_KEYS, ...Object.keys(KIT)];
  known("planeFrom options", options, [...kitKeys, ...PLANE_KEYS, "gear", "bay", "kind"]);
  const sub = (keys) => Object.fromEntries(Object.entries(options).filter(([k]) => keys.includes(k)));
  const kit = new PlaneKit(sub(kitKeys)), {body, anchors} = assemble(kit, spec);
  const made = new Plane(body, kit, {...sub(PLANE_KEYS), kind: options.kind ?? null, seed: kit.seed, anchors, spec});
  return made.gear(options.gear ?? 0).bay(options.bay ?? 0).controls({});
}
/** A ready-made plane: `kind` (PLANES), options {seed (1): another plane of the kind for every seed
 * (proportions, sweep, scheme, wear, stripes, registration); the plane kit's (scheme, color, scorch, tile,
 * registration, accent, detail, wear, lit); parts of the description (planeSpec); gear, bay; a craft's}. */
export function plane(kind, options = {}) {
  known(`plane("${kind}") options`, options, [...new Set(["seed", ...SPEC_KEYS, ...KIT_KEYS, ...Object.keys(KIT), ...PLANE_KEYS, "bay"])]);
  const specOver = Object.fromEntries(Object.entries(options).filter(([k]) => SPEC_KEYS.includes(k) && !(k === "gear" && typeof options[k] === "number") && !(k === "lights" && typeof options[k] !== "boolean")));
  const rest = Object.fromEntries(Object.entries(options).filter(([k]) => !(k in specOver) && k !== "seed"));
  const seed = options.seed ?? 1, {spec, scheme, scorch} = planeSpec(kind, {seed, ...specOver});
  return planeFrom(spec, {scheme, scorch, accent: ACCENTS[(seed + kindSeed(kind)) % ACCENTS.length], registration: registration(seed * 37 + kindSeed(kind) % 1009), ...rest, seed, kind, name: rest.name ?? `${kind} ${seed}`});
}
/** A formation without designing each: `count` planes of `kind` (or of the kinds of a list, in turn) with
 * seeds seed, seed + 1, ..., in a vee `spacing` metres apart (default 1.6 times the first one's span), each a
 * little off its place by the seed. Options: count (5), seed (1), spacing, detail ("far"), and anything
 * plane() takes. Returns {object, planes, update(t, options), dispose()}. */
export function planeFleet(kind, options = {}) {
  const {count = 5, seed = 1, spacing = null, detail = "far", ...rest} = options, kinds = Array.isArray(kind) ? kind : [kind];
  const planes = Array.from({length: count}, (_, i) => plane(kinds[i % kinds.length], {...rest, detail, seed: seed + i})), r = rng(seed * 613 + 17), object = new THREE.Group();
  const step = spacing ?? 1.6 * planes[0].size.width;
  planes.forEach((c, i) => { const row = Math.floor((i + 1) / 2), side = i === 0 ? 0 : i % 2 ? 1 : -1; c.object.position.set(side * row * step * (0.92 + 0.16 * r()), (r() - 0.5) * step * 0.12 - row * step * 0.04, -row * step * (0.8 + 0.2 * r())); object.add(c.object); });
  object.name = "plane fleet";
  return {object, planes, update(t, o = {}) { for (const c of planes) c.update(t, o); return this; }, dispose() { for (const c of planes) c.dispose(); }};
}
