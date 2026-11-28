// vidgen/space-camera-air: camera moves inside an atmosphere and beside giant ships.
// Part of schu-video-generator (MIT licence); imported by a page as "vidgen/space-camera-air", beside
// "vidgen/space-camera" (whose rig it extends: every move of that module works on this rig too).
//
//   const cam = airCamera({camera, sky, ground, water, clouds: weather, flight: ctx.flight, music: ctx.music});
//   cam.apply(t, cam.skim(t, {over: [0, 8], from: [0, 0], heading: 300, speed: 90, clearance: 25}));
//   const cam = airCamera({space, camera, ships: {Ship: ship}});            // beside a hull flown in a SpaceView
//   cam.apply(t, cam.hullPass(t, {ship: "Ship", over: [0, 12], side: "port", standoff: 60, speed: 40}));
//
// Air moves: skim, climbThrough, descendThrough, chase, wing, flyPast, orbitPeak, rise, descend, ascend. Ship moves: hullPass,
// hullReveal, intoBay, sternBurn, scaleZoom. Every move is a function of the time it is given (and of
// where its subjects are then): nothing is kept between frames, so a still at t is frame t, scenes
// render in any order and two moves cut together on one clock. A move returns a shot as
// vidgen/space-camera's ({from, right, up, forward, fov, aspect, focus, ...}) with `notes`: sentences
// about anything it had to change (a camera lifted to keep its margin over the ground).
//
// Frames. In the air: the scene's local frame of vidgen/space-air, -sea, -land and vidgen.flight (x east, y
// up at the origin, z south, metres; the world's middle at [0, -radius, 0]). The world is a sphere: away
// from the origin +y is not up, so every move takes "up" from the local vertical at the camera and
// heights from the ground's and the water's own lookups. Beside a ship: places are metres in the hull's
// own axes (+z the bow, +y up, +x port), turned by the hull's object into the rig's frame; update the
// ship for t before asking for the move. Angles are degrees, headings compass (0 north = -z, 90 east = +x),
// speeds m/s. `over: [start, end]` is seconds, or {bar, beat} of the score with `music: ctx.music`.
// No three.js import: the mathematics runs in Node.
import {clamp, mix, smoothstep, smootherstep, hash} from "vidgen/music-time";
import {SpaceCamera, lens, shotAt, sub, add, scale, dot, cross, len, unit, turn, square, progressOf, distanceFor} from "vidgen/space-camera";
import {sceneTime} from "vidgen/space-scene";

export const VERSION = 1;
const PREFIX = "vidgen/space-camera-air";
const RAD = Math.PI / 180;
/** The gravity a banked turn is worked out with, m/s² (a look: the camera banks as a plane at that speed would). */
export const GRAVITY = 9.81;
/** The moves of this module, air first. */
export const AIR_MOVES = Object.freeze(["skim", "climbThrough", "descendThrough", "chase", "wing", "flyPast", "orbitPeak", "rise", "descend", "ascend"]);
export const SHIP_MOVES = Object.freeze(["hullPass", "hullReveal", "intoBay", "sternBurn", "scaleZoom"]);
/** Sides of a hull: degrees round its long axis from port (+x) towards the top (+y). */
export const SIDES = Object.freeze({port: 0, dorsal: 90, top: 90, starboard: 180, ventral: 270, bottom: 270});
/** Views locked to a plane's own frame: where the camera sits and the point it looks at, in the plane's axes
 * ([left wing, up, nose]) as shares: [x in spans, y in lengths, z in lengths] from the body's middle. `tip`: the
 * view looks over the wing's tip (read from the plane's anchors when it is known). */
export const WING_VIEWS = Object.freeze({
  wingtip: Object.freeze({at: [0.13, 0.08, 0], look: [0.5, 0.1, -0.37], tip: true, lens: "wide", label: "from the shoulder out along the wing: the tip, the horizon tilting as the plane banks"}),
  tail: Object.freeze({at: [0.03, 0.2, -0.56], look: [0, 0.05, 0.3], lens: "wide", label: "from behind and over the fins, forward along the back"}),
  belly: Object.freeze({at: [0.26, -0.26, 0.62], look: [0, -0.03, 0], lens: "wide-normal", label: "from under and ahead, looking back up at the belly (the tiles on a re-entry)"}),
  nose: Object.freeze({at: [0.2, 0.1, 0.9], look: [0, 0, 0.1], lens: "wide-normal", label: "from ahead of the nose, looking back along the body"}),
});
/** A hull pass faster than this share of the hull's length a second reads as a model (a 3 km ship in 12 s). */
export const TOY_SHARE = 1 / 12;

// ---------- checks ----------
const fail = (msg) => new Error(`${PREFIX}: ${msg}`);
function editDistance(a, b) {
  const d = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++) { const cur = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  }
  return d[b.length];
}
function hint(key, names) {
  const best = names.map((k) => [editDistance(String(key).toLowerCase(), String(k).toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; known: ${keys.join(", ")}`);
}
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const isPair = (v) => Array.isArray(v) && v.length === 2 && v.every(isNum);
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every(isNum);
const num = (where, v, lo = -Infinity, hi = Infinity) => { if (!isNum(v) || v < lo || v > hi) throw fail(`${where} must be a number${lo > -Infinity ? ` from ${lo}` : ""}${hi < Infinity ? ` to ${hi}` : ""}, got ${JSON.stringify(v)}`); return v; };
const pair = (where, v) => { if (!isPair(v)) throw fail(`${where} must be [x, z] in metres, got ${JSON.stringify(v)}`); return v; };
const oneOf = (where, v, names) => { if (!names.includes(v)) throw fail(`${where} must be one of ${names.join(", ")}, got ${JSON.stringify(v)}${hint(v, names)}`); return v; };
const metres = (m) => (Math.abs(m) >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m.toFixed(0)} m`);
const rotate = (q, v) => { const u = [q[0], q[1], q[2]], t = scale(cross(u, v), 2); return add(add(v, scale(t, q[3])), cross(u, t)); };
const along = (a, b, k) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];

// ---------- time ----------
/** A move's progress with its own start and end: `ease` 0 is steady (cut into and out of motion), 1 starts
 * and ends at rest (the speed rises as a smoothstep over half the move); a pair [in, out] sets each end, so
 * [1, 0] starts at rest and ends moving and two moves cut together on motion. Returns 0..1. */
export function easedEnds(u, ease = 0.6) {
  u = clamp(u);
  const [a, b] = Array.isArray(ease) ? ease : [ease, ease], ri = 0.5 * clamp(a), ro = 0.5 * clamp(b);
  const rise = (y, r) => r * (y * y * y - 0.5 * y * y * y * y);
  const travel = (x) => (ri > 0 ? rise(Math.min(x, ri) / ri, ri) : 0) + clamp(x - ri, 0, 1 - ri - ro) + (ro > 0 && x > 1 - ro ? ro / 2 - rise((1 - x) / ro, ro) : 0);
  return travel(u) / travel(1);
}
/** The speed of `easedEnds` at u as a share of its steady middle speed (0 at a resting end, 1 between). */
export function easedRate(u, ease = 0.6) {
  const [a, b] = Array.isArray(ease) ? ease : [ease, ease], ri = 0.5 * clamp(a), ro = 0.5 * clamp(b);
  u = clamp(u);
  return (ri > 0 ? smoothstep(0, ri, u) : 1) * (ro > 0 ? smoothstep(0, ro, 1 - u) : 1);
}
// the middle speed of easedEnds as a share of length over time: 1 / travel(1)
const easedPeak = (ease) => { const [a, b] = Array.isArray(ease) ? ease : [ease, ease]; return 1 / (1 - 0.25 * clamp(a) - 0.25 * clamp(b)); };

// ---------- the local frame ----------
/** The scene's local frame on a world of `radius` whose middle is `center` (default [0, -radius, 0]: the
 * origin on the sphere, +y up there): {upAt(p): the local vertical at a point, heightOf(p): metres over the
 * sphere, at(x, z, h): the point over the scene's (x, z) at height h over the sphere, northAt(p), compass(p,
 * degrees): the level direction of a compass heading at p}. */
export function localFrame({radius = 6.371e6, center = null} = {}) {
  num("radius", radius, 1);
  const c = center ?? [0, -radius, 0];
  const upAt = (p) => unit(sub(p, c));
  return {radius, center: c, upAt,
    heightOf: (p) => len(sub(p, c)) - radius,
    at: (x, z, h) => {
      const dx = x - c[0], dz = z - c[2], r = radius + h, q = r * r - dx * dx - dz * dz;
      if (!(q > 0)) throw fail(`the place (${metres(x)}, ${metres(z)}) is beyond the world's edge as the scene's frame sees it`);
      return [x, c[1] + Math.sqrt(q), z];
    },
    compass: (p, degrees) => square([Math.sin(degrees * RAD), 0, -Math.cos(degrees * RAD)], upAt(p), [1, 0, 0])};
}
/** A camera frame from a level heading: looking along `heading` (any vector; its level part counts) pitched
 * `pitch` degrees above the level for the vertical `up`, banked `roll` degrees to the right. Defined at every
 * pitch, straight down and up included: no flip. Returns {right, up, forward}. */
export function lookFrame(up, heading, pitch = 0, roll = 0) {
  const U = unit(up), h = square(heading, U, [0, 0, -1]), p = clamp(pitch, -90, 90) * RAD;
  const forward = along(scale(h, Math.cos(p)), U, Math.sin(p));
  let top = along(scale(U, Math.cos(p)), h, -Math.sin(p)), right = cross(h, U);
  if (roll) { const b = roll * RAD, c = Math.cos(b), s = Math.sin(b); [right, top] = [along(scale(right, c), top, -s), along(scale(top, c), right, s)]; }
  return {right, up: top, forward};
}
const shotOf = (eye, f, fov, aspect, target, extra) => ({from: eye.slice(), right: f.right, up: f.up, forward: f.forward, fov, aspect,
  focus: Math.max(dot(sub(target, eye), f.forward), 1e-6), target: target.slice(), place: null, notes: [], ...extra});
// a frame from a view direction and a wanted top (not parallel)
function frameOf(forward, top, roll = 0) {
  const f = unit(forward);
  let u = unit(along(top, f, -dot(top, f))), r = cross(f, u);
  if (roll) { const b = roll * RAD, c = Math.cos(b), s = Math.sin(b); [r, u] = [along(scale(r, c), u, -s), along(scale(u, c), r, s)]; }
  return {right: r, up: u, forward: f};
}

// ---------- pure arithmetic ----------
/** An exponentially weighted mean of f over the past of t (weights exp(-age / lag), ages up to 4 lags):
 * a damped follow that is still a function of t alone. f gives numbers or arrays. */
export function lagged(f, t, lag, n = 12) {
  if (!(lag > 0)) return f(t);
  let sum = null, W = 0;
  for (let i = 0; i <= n; i++) {
    const age = 4 * lag * i / n, w = Math.exp(-age / lag) * (i === 0 || i === n ? 0.5 : 1), v = f(t - age);
    sum = sum === null ? (Array.isArray(v) ? v.map((x) => x * w) : v * w) : Array.isArray(v) ? sum.map((x, k) => x + v[k] * w) : sum + v * w;
    W += w;
  }
  return Array.isArray(sum) ? sum.map((x) => x / W) : sum / W;
}
/** A camera path's height over a row of ground heights: each value becomes the highest within `reach`
 * samples of it (the look-ahead: the path rises before a ridge), then a smooth mean over the same reach.
 * Never under the value at its own sample. */
export function envelope(values, reach) {
  const n = values.length, r = Math.max(0, Math.round(reach)), high = new Array(n), out = new Array(n);
  for (let k = 0; k < n; k++) { let m = -Infinity; for (let j = Math.max(0, k - r); j <= Math.min(n - 1, k + r); j++) m = Math.max(m, values[j]); high[k] = m; }
  if (r === 0) return high;
  for (let k = 0; k < n; k++) {
    let s = 0, W = 0;
    for (let i = -r; i <= r; i++) { const w = 0.5 + 0.5 * Math.cos(Math.PI * i / (r + 1)), j = clamp(k + i, 0, n - 1); s += w * high[j]; W += w; }
    out[k] = s / W;
  }
  return out;
}
// a smooth curve through evenly spaced values that never leaves the span of the two values it runs between (a
// monotone cubic: no overshoot, so a path over an envelope never dips under it): [value, slope per sample] at x
// samples from the first
function curveAt(values, x) {
  const n = values.length, q = clamp(x, 0, n - 1), i = Math.min(Math.floor(q), n - 2), u = q - i;
  const slope = (k) => { if (k <= 0 || k >= n - 1) return 0; const a = values[k] - values[k - 1], b = values[k + 1] - values[k]; return a * b > 0 ? 2 * a * b / (a + b) : 0; };
  const p1 = values[i], p2 = values[i + 1], m1 = slope(i), m2 = slope(i + 1), u2 = u * u, u3 = u2 * u;
  return [(2 * u3 - 3 * u2 + 1) * p1 + (u3 - 2 * u2 + u) * m1 + (-2 * u3 + 3 * u2) * p2 + (u3 - u2) * m2,
    (6 * u2 - 6 * u) * p1 + (3 * u2 - 4 * u + 1) * m1 + (-6 * u2 + 6 * u) * p2 + (3 * u2 - 2 * u) * m2];
}
/** A ground track on the scene's (x, z): from `from` on the compass heading `heading`, turning by `turn`
 * degrees in all (to the right when positive) as a smooth S of the way, `length` metres long; `pad` metres
 * of straight run before and after. Returns {length, step, first (the index of the start), x, z (the nodes),
 * headingAt(s), turnAt(s): degrees per metre, pointAt(s): [x, z]} for s metres from the start. */
export function trackPlan({from = [0, 0], heading = 0, turn = 0, length, pad = 0, nodes = 96} = {}) {
  pair("from", from); num("heading", heading); num("turn", turn, -720, 720); num("length", length, 1e-6);
  const step = length / nodes, first = Math.ceil(pad / step), n = nodes + 2 * first + 1;
  const headingAt = (s) => heading + turn * smootherstep(s / length), dirAt = (s) => { const a = headingAt(s) * RAD; return [Math.sin(a), -Math.cos(a)]; };
  const x = new Array(n), z = new Array(n);
  x[first] = from[0]; z[first] = from[1];
  for (let k = first + 1; k < n; k++) { const d = dirAt((k - first - 0.5) * step); x[k] = x[k - 1] + d[0] * step; z[k] = z[k - 1] + d[1] * step; }
  for (let k = first - 1; k >= 0; k--) { const d = dirAt((k - first + 0.5) * step); x[k] = x[k + 1] - d[0] * step; z[k] = z[k + 1] - d[1] * step; }
  const pointAt = (s) => {
    const q = clamp(s / step + first, 0, n - 1), k = Math.min(Math.floor(q), n - 2), rest = (q - k) * step, d = dirAt((k - first) * step + rest / 2);
    return [x[k] + d[0] * rest, z[k] + d[1] * rest];
  };
  const turnAt = (s) => { const u = s / length; return u <= 0 || u >= 1 ? 0 : turn * 30 * u * u * (1 - u) * (1 - u) / length; };
  return {length, step, first, x, z, headingAt, turnAt, pointAt};
}
/** The bank (degrees, to the right when positive) of a coordinated turn at `speed` m/s turning `rate` degrees
 * a second, times `share`, within +-`most`. */
export const bankOf = (speed, rate, share = 1, most = 40) => clamp(Math.atan(speed * rate * RAD / GRAVITY) / RAD * share, -most, most);
/** The dip of the horizon (degrees under the level) from `height` metres over a sphere of `radius`. */
export const horizonDip = (radius, height) => Math.acos(radius / (radius + Math.max(height, 0))) / RAD;
/** A seeded camera shake at time t: {yaw, pitch, roll} in degrees, sums of sines of `rate` Hz and its
 * uneven multiples with phases from `seed`, within +-`amount`. A function of t alone. */
export function shake(t, {amount = 0.25, seed = 1, rate = 7} = {}) {
  const s = (k, f) => Math.sin(2 * Math.PI * (f * t + hash(seed, k)));
  return {yaw: amount * (0.6 * s(1, rate) + 0.4 * s(2, rate * 1.73)), pitch: amount * (0.6 * s(3, rate * 1.31) + 0.4 * s(4, rate * 2.09)), roll: 0.5 * amount * s(5, rate * 0.77)};
}
/** How far a camera has been pushed back `age` seconds after a kick of `distance` metres: 0 before, rising
 * without overshoot (a critically damped spring of time constant `settle`) to `distance`. */
export const pushBack = (age, distance = 1, settle = 0.45) => (age <= 0 ? 0 : distance * (1 - (1 + age / settle) * Math.exp(-age / settle)));

// ---------- the operator (Step 399) ----------
/** The operator's defaults. `handheld`: slow drift (`drift` degrees at `rate` Hz) that the operator corrects late
 * (`delay` seconds, then a second-order response at `correct` Hz with `damping` < 1: a little overshoot), a
 * reframe now and then (one in most spans of `reframe` seconds: the frame slips `size` degrees off over a second
 * and a half and is put back quickly, overshooting), a hand's tremor and breathing (degrees). `mounted`: only a
 * mount's vibration (`vibration` degrees at about `rate` Hz) and a slow `sway`. `mm`: the focal length the hand is
 * scaled by (default the shot's own). `exposure`: an automatic exposure: a share `strength` of each change of
 * the metered brightness taken back after `delay` seconds by a second-order response at `speed` Hz, `hunt` 0..1
 * (0: no overshoot, 1: it swings round twice), at most `most` stops, read at `samples` past times. `horizon`:
 * the horizon `degrees` off (a seeded side) at the start of every shot, held `hold` seconds, levelled in about
 * `settle` seconds with `damping` (a little overshoot). */
export const OPERATOR = Object.freeze({
  handheld: Object.freeze({amount: 1, seed: 1, drift: 1.1, rate: 0.12, delay: 0.3, correct: 0.5, damping: 0.5, tremor: 0.03, breath: 0.05, reframe: 6, size: 0.9, mm: null}),
  mounted: Object.freeze({amount: 1, seed: 1, vibration: 0.12, rate: 9, sway: 0.06, mm: null}),
  exposure: Object.freeze({strength: 0.7, delay: 0.2, speed: 0.45, hunt: 0.6, most: 2, samples: 24}),
  horizon: Object.freeze({degrees: 1, seed: 1, hold: 2.5, settle: 1.2, damping: 0.6}),
});
/** What the operator's meter counts as bright (shares of a white ground in full sun): the clear sky, the sea and the
 * land in the sun, a deck's grey base seen from under it, fog just under a deck's top (darker by exp(-`deep` x the
 * share of the deck above the camera) further in), sunlit cloud tops, the sun in the frame (with its glare) and the
 * sun's glitter on the sea. A stated estimate fitted to the rendered mean of two views. */
export const METER = Object.freeze({sky: 0.3, sea: 0.03, land: 0.12, base: 0.7, fog: 1.5, deep: 6, tops: 1.2, sun: 0.15, glint: 0.5});
const OPERATOR_KEYS = ["hand", "exposure", "horizon", "seed", "start", "cuts"];
const fade5 = (u) => u * u * u * (u * (u * 6 - 15) + 10);
/** Smooth endless noise of x (gradient noise, knots one apart, gradients from `seed`): about -1..1, mean 0, never
 * repeating. Pure. */
export function smoothNoise(x, seed = 1) {
  const i = Math.floor(x), u = x - i, g = (k) => 2 * hash(seed * 17.31 + 0.37, k) - 1;
  return 2 * mix(g(i) * u, g(i + 1) * (u - 1), fade5(u));
}
// a second-order system of natural frequency f Hz and damping z (under 1: it overshoots; 1 or more: critically damped)
const omegas = (f, z) => { const w = 2 * Math.PI * f; return z < 1 ? [w, w * Math.sqrt(1 - z * z)] : [w, 0]; };
/** Its answer `age` seconds after a unit step: 0 before, rising to 1 (overshooting by exp(-zπ/√(1-z²)) when z < 1). */
export function stepResponse(age, f, z) {
  if (!(age > 0)) return 0;
  const [w, wd] = omegas(f, z);
  if (z >= 1) return 1 - (1 + w * age) * Math.exp(-w * age);
  return 1 - Math.exp(-z * w * age) * (Math.cos(wd * age) + z / Math.sqrt(1 - z * z) * Math.sin(wd * age));
}
/** Its answer `age` seconds after a unit impulse (the weights of `responded`). */
export function impulseResponse(age, f, z) {
  if (!(age > 0)) return 0;
  const [w, wd] = omegas(f, z);
  return z >= 1 ? w * w * age * Math.exp(-w * age) : (w / Math.sqrt(1 - z * z)) * Math.exp(-z * w * age) * Math.sin(wd * age);
}
/** How a second-order follower (`rate` Hz, `damping`) `delay` seconds late answers f at time t: the weighted mean of
 * f at `n` + 1 past times over `window` seconds (default 5 / (damping x 2π rate)), weights the impulse response's;
 * no time before `since` is read (f held there: a follower settled at `since`). A function of t alone. */
export function responded(f, t, {delay = 0, rate = 1, damping = 0.6, window = null, n = 32, since = -Infinity} = {}) {
  const W = window ?? 5 / (Math.min(damping, 1) * 2 * Math.PI * rate);
  let sum = 0, total = 0;
  for (let k = 1; k <= n; k++) {
    const a = W * k / n, w = impulseResponse(a, rate, damping) * (k === n ? 0.5 : 1);
    sum += w * f(Math.max(t - delay - a, since)); total += w;
  }
  return sum / total;
}
/** How much of a hand's angles a lens of `mm` (36 x 24 mm frame) shows: a long lens is held a little steadier
 * ((50 / mm)^0.3, 0.5..1.6), but by far less than it magnifies, so it shakes more on the screen. */
export const handShare = (mm) => (isNum(mm) && mm > 0 ? clamp(Math.pow(50 / mm, 0.3), 0.5, 1.6) : 1);
/** The occasional reframe of a handheld camera at time t: {yaw, pitch} in degrees. Spans of `reframe` seconds,
 * most with one at a seeded time: the frame slips `size` degrees off (in a seeded direction, mostly sideways)
 * over 1.6 s, then the operator, `delay` late, puts it back with a quick second-order move (1.1 Hz, damping
 * 0.45: an overshoot of a fifth). Pure. */
export function reframeAt(t, {reframe = OPERATOR.handheld.reframe, size = OPERATOR.handheld.size, seed = 1, delay = OPERATOR.handheld.delay} = {}) {
  const out = {yaw: 0, pitch: 0};
  if (!(reframe > 0) || !size) return out;
  const h = (j, k) => hash(seed * 7.7 + 0.11 * k, j);
  for (let j = Math.floor((t - 6) / reframe) - 1; j <= Math.floor((t + 2) / reframe) + 1; j++) {
    if (h(j, 1) > 0.7) continue;
    const at = (j + 0.25 + 0.5 * h(j, 2)) * reframe, s = size * (0.6 + 0.4 * h(j, 3)), a = 2 * Math.PI * h(j, 4);
    const v = s * (smoothstep(at - 1.6, at, t) - stepResponse(t - at - delay, 1.1, 0.45));
    out.yaw += v * Math.cos(a); out.pitch += 0.5 * v * Math.sin(a);
  }
  return out;
}
/** A handheld camera's error at time t: {yaw, pitch, roll} in degrees (OPERATOR.handheld's options): the drift less
 * the operator's late correction of it, a reframe now and then, tremor and breath, times `amount` and the lens's
 * handShare (`mm`, the focal length). A function of t and the seed: nothing is kept between frames. */
export function handheld(t, options = {}) {
  const o = {...OPERATOR.handheld, ...options}, s = o.seed, k = o.amount * handShare(o.mm);
  const drift = (ch) => (x) => o.drift * (0.75 * smoothNoise(o.rate * x, s * 13 + ch) + 0.4 * smoothNoise(2.3 * o.rate * x + 5.1, s * 13 + ch + 0.5));
  const held = (ch) => { const d = drift(ch); return d(t) - responded(d, t, {delay: o.delay, rate: o.correct, damping: o.damping}); };
  const tremor = (ch) => o.tremor * (0.7 * smoothNoise(5.3 * t, s * 13 + ch + 0.25) + 0.5 * smoothNoise(8.9 * t + 2.7, s * 13 + ch + 0.75));
  const breath = o.breath * Math.sin(2 * Math.PI * (0.23 * t + hash(s, 9) + 0.3 * smoothNoise(0.07 * t, s * 13 + 9)));
  const r = reframeAt(t, o);
  return {yaw: k * (held(1) + tremor(1) + r.yaw), pitch: k * (held(2) + tremor(2) + breath + r.pitch), roll: k * (0.4 * held(3) + 0.5 * tremor(3))};
}
/** A mounted camera's error at time t: {yaw, pitch, roll} in degrees: vibration about `rate` Hz and a slow sway,
 * times `amount` (the same angles at every lens: a long lens shows them larger). Pure. */
export function mounted(t, options = {}) {
  const o = {...OPERATOR.mounted, ...options}, s = o.seed;
  const buzz = (ch) => o.vibration * (0.6 * smoothNoise(o.rate * t, s * 29 + ch) + 0.5 * smoothNoise(1.9 * o.rate * t + 3.3, s * 29 + ch + 0.5)) + o.sway * smoothNoise(0.6 * t, s * 29 + ch + 0.25);
  return {yaw: o.amount * buzz(1), pitch: o.amount * buzz(2), roll: o.amount * 0.5 * buzz(3)};
}
/** The horizon's error `age` seconds into a shot (degrees of roll): `degrees` to a seeded side, held `hold` seconds,
 * then levelled in about `settle` seconds with `damping` (a little overshoot). Pure. */
export function horizonRoll(age, {degrees = 1, seed = 1, hold = 2.5, settle = 1.2, damping = 0.6} = {}) {
  const z = Math.min(damping, 0.99), f = (Math.PI - Math.acos(z)) / (Math.sqrt(1 - z * z) * settle) / (2 * Math.PI);
  return (hash(seed * 5.3 + 0.7, 1) < 0.5 ? -1 : 1) * degrees * (1 - stepResponse(age - hold, f, z));
}
/** How bright the scene looks in a shot, in stops (log2 of a share of a white ground in full sun; METER's
 * values): the share of the frame over the horizon (from the view's pitch, the horizon's dip and the field of view)
 * as sky darkening with height (`scale`: the air's scale height), the rest as sea or land lit by the sun; decks
 * (lowest first, {base, top, cover, density}) put their grey base over the sky and shade what is under them, fog
 * all round inside, sunlit tops in place of the ground above them; the sun in or near the frame (its glare) and its
 * glitter on the sea. `up`: the vertical at the camera, `height` over the sphere, `sun`: towards the sun. Pure. */
export function meterStops(shot, {up = [0, 1, 0], height = 0, sun = null, radius = 6.371e6, scale = 8500, water = false, decks = []} = {}, values = METER) {
  const M = values;
  const U = unit(up), f = unit(shot.forward), v = 0.5 * shot.fov, S = sun ? unit(sun) : null;
  const mus = S ? dot(U, S) : 0.6, day = smoothstep(-0.1, 0.2, mus), lit = Math.max(mus, 0);
  const dip = horizonDip(radius, height), skyShare = clamp(0.5 + (Math.asin(clamp(dot(f, U), -1, 1)) / RAD + dip) / (2 * v));
  let sky = M.sky * day * (0.1 + 0.9 * Math.exp(-Math.max(height, 0) / scale)), ground = (water ? M.sea : M.land) * (lit + 0.25 * day), direct = 1;
  for (const d of decks) {
    const u = (height - d.base) / Math.max(d.top - d.base, 1), o = clamp(d.cover ?? 1) * Math.min(1, (d.density ?? 0.006) / 0.004);
    const under = 1 - smoothstep(-0.12, 0.12, u), over = smoothstep(0.88, 1.12, u), inside = Math.max(0, 1 - under - over), fog = M.fog * day * (0.4 + 0.6 * lit) * (Math.exp(-M.deep * (1 - clamp(u))) + 0.04);
    ground = mix(ground, M.tops * (lit + 0.2 * day), o * over);
    sky = mix(sky, M.base * day * (0.3 + 0.7 * lit), o * under);
    ground *= 1 - 0.6 * o * under;
    sky = mix(sky, fog, o * inside); ground = mix(ground, fog, o * inside);
    direct *= clamp(1 - o * (0.85 * under + inside));
  }
  let glare = 0;
  if (S) {
    const theta = Math.atan2(len(cross(f, S)), dot(f, S)) / RAD, half = Math.atan(Math.tan(v * RAD) * Math.hypot(1, shot.aspect ?? 16 / 9)) / RAD;
    glare = M.sun * direct * smoothstep(-dip - 0.5, -dip + 0.5, Math.asin(mus) / RAD) * (1 - smoothstep(0.5 * half, half + 8, theta));
    if (water) { const R = along(S, U, -2 * dot(S, U)); glare += M.glint * direct * day * (1 - skyShare) * Math.max(0, dot(f, R)) ** 6; }
  }
  return Math.log2(Math.max(skyShare * sky + (1 - skyShare) * ground + glare, 1e-4));
}
/** The automatic exposure's correction at time t (stops, added to the scene's): `meter(x)` the metered stops at
 * time x; a share `strength` of the change since `since` (the shot's start, when the camera was settled) taken
 * back late: `delay`, then a second-order response at `speed` Hz whose damping falls with `hunt` (1 - 0.8 hunt),
 * held within +-`most` stops by a soft limit. OPERATOR.exposure's options. A function of t alone. */
export function autoExposure(t, meter, options = {}, since = 0) {
  const o = {...OPERATOR.exposure, ...options}, ref = meter(since);
  const seen = responded(meter, t, {delay: o.delay, rate: o.speed, damping: 1 - 0.8 * clamp(o.hunt), n: o.samples, since});
  return o.most * Math.tanh(-o.strength * (seen - ref) / o.most);
}
// an operator group: off (absent, false, null, 0), true, a number (its main value) or an object, checked
function operatorGroup(name, value, defaults, main) {
  if (value === undefined || value === null || value === false || value === 0) return null;
  if (value === true) return {...defaults};
  if (isNum(value)) return {...defaults, [main]: value};
  if (!value || typeof value !== "object" || Array.isArray(value)) throw fail(`operator ${name} must be true, a number (${main}) or {${Object.keys(defaults).join(", ")}}, got ${JSON.stringify(value)}`);
  known(`operator ${name}`, value, Object.keys(defaults));
  return {...defaults, ...value};
}
function handGroup(value, seed) {
  if (value === undefined || value === null || value === false) return null;
  const style = value === true ? "handheld" : typeof value === "string" ? value : value && typeof value === "object" && !Array.isArray(value) ? value.style ?? "handheld" : null;
  if (style === null) throw fail(`operator hand must be "handheld", "mounted", true or {style, ...}, got ${JSON.stringify(value)}`);
  oneOf("operator hand", style, ["handheld", "mounted"]);
  const defaults = {...OPERATOR[style], seed}, o = typeof value === "object" ? value : {};
  known(`operator hand (${style})`, o, ["style", ...Object.keys(defaults)]);
  const out = {...defaults, ...o, style};
  for (const [k, x] of Object.entries(out)) if (k !== "style" && k !== "mm" && k !== "seed") num(`operator hand.${k}`, x, 0, k === "reframe" ? 600 : 100);
  if (out.style === "handheld" && out.reframe > 0 && out.reframe < 2) throw fail(`operator hand.reframe must be 0 (none) or at least 2 seconds, got ${out.reframe}`);
  if (out.mm !== null) num("operator hand.mm", out.mm, 4, 5000);
  return out;
}
/** A camera operator over `view` (a function of t giving shots, such as moveTrack's): returns the view as the
 * operator frames it, a function of t alone. `hand`: "handheld" or "mounted" (or true, or {style, ...}:
 * OPERATOR's), `exposure` (true, a strength or {...}; needs `meter(shot, t)`: the metered stops, as AirCamera's
 * `operator` gives), `horizon` (true, degrees or {...}); `seed` (1) for all three unless a group gives its own;
 * `start` (seconds: the first shot's start, 0) and `cuts` (the times of the cuts: each starts a shot with its own
 * horizon error, and the exposure, settled at the cut, reads nothing before it). The shot comes back turned by
 * the hand and the horizon, with `ev` (the shot's own, plus the exposure's) and `operator`: {yaw, pitch, roll,
 * horizon, ev}. */
export function operate(view, options = {}, meter = null) {
  known("operator", options, OPERATOR_KEYS);
  if (typeof view !== "function") throw fail("operate needs a view: a function of t giving shots (moveTrack's)");
  const seed = num("operator seed", options.seed ?? 1, 0), hand = handGroup(options.hand, seed);
  const exposure = operatorGroup("exposure", options.exposure, OPERATOR.exposure, "strength"), horizon = operatorGroup("horizon", options.horizon, {...OPERATOR.horizon, seed}, "degrees");
  if (exposure) {
    for (const [k, x] of Object.entries(exposure)) num(`operator exposure.${k}`, x, k === "speed" ? 0.01 : 0, {strength: 1, hunt: 1, most: 8, samples: 96}[k] ?? 30);
    exposure.samples = Math.max(4, Math.round(exposure.samples));
    if (typeof meter !== "function") throw fail("operator exposure needs a meter: airCamera's operator(view, options), which meters the scene's sun, decks and ground");
  }
  if (horizon) for (const [k, x] of Object.entries(horizon)) num(`operator horizon.${k}`, x, k === "degrees" ? -20 : k === "settle" ? 0.05 : 0, k === "degrees" ? 20 : 600);
  const start = num("operator start", options.start ?? 0), cuts = (options.cuts ?? []).map((c, i) => num(`operator cuts[${i}]`, c)).sort((a, b) => a - b);
  if (!hand && !exposure && !horizon) return view;
  return (t) => {
    const shot = view(t);
    let from = start, index = 0;
    for (const c of cuts) if (c <= t + 1e-9 && c > from) { from = c; index++; }
    const mm = 12 / Math.tan(shot.fov * RAD / 2);
    const h = !hand ? {yaw: 0, pitch: 0, roll: 0} : hand.style === "mounted" ? mounted(t, hand) : handheld(t, {...hand, mm: hand.mm ?? mm});
    const level = horizon ? horizonRoll(t - from, {...horizon, seed: horizon.seed + 101 * index}) : 0;
    const ev = exposure ? autoExposure(t, (x) => meter(view(x), x), exposure, from) : 0;
    const f = turn(turn(shot.forward, shot.up, h.yaw * RAD), shot.right, h.pitch * RAD), frame = frameOf(f, shot.up, h.roll + level);
    return {...shot, ...frame, ev: (isNum(shot.ev) ? shot.ev : 0) + ev, operator: {yaw: h.yaw, pitch: h.pitch, roll: h.roll + level, horizon: level, ev}};
  };
}

// ---------- hulls as boxes ----------
const corners = (b) => [0, 1, 2, 3, 4, 5, 6, 7].map((i) => [i & 1 ? b.max[0] : b.min[0], i & 2 ? b.max[1] : b.min[1], i & 4 ? b.max[2] : b.min[2]]);
const span = (b, axis) => { let lo = Infinity, hi = -Infinity; for (const c of corners(b)) { const v = dot(c, axis); lo = Math.min(lo, v); hi = Math.max(hi, v); } return [lo, hi]; };
/** The distance (metres) from a point to a box {min, max}: 0 inside. */
export function boxDistance(p, box) { return Math.hypot(...[0, 1, 2].map((i) => Math.max(box.min[i] - p[i], 0, p[i] - box.max[i]))); }
/** The distance from a point (the hull's axes) to the nearest of a hull's regions (their boxes), and its name:
 * {distance, region}; `skip(region)` leaves regions out. As true as the boxes: a box is never smaller than
 * its region, so the camera is never nearer the hull than this says. */
export function hullClearance(regions, p, skip = null) {
  let best = {distance: Infinity, region: null};
  for (const g of regions) { if (skip && skip(g)) continue; const d = boxDistance(p, g.box); if (d < best.distance) best = {distance: d, region: g.name}; }
  return best;
}
/** The side of a hull as axes: `side` a name of SIDES or degrees round the long axis from port towards the
 * top. Returns {out, across, angle}: unit vectors in the hull's axes (out x across = the bow's direction). */
export function sideAxes(side = "port") {
  const a = (typeof side === "string" ? (side in SIDES ? SIDES[side] : (() => { throw fail(`no side "${side}"${hint(side, Object.keys(SIDES))}; sides: ${Object.keys(SIDES).join(", ")}, or degrees round the long axis from port towards the top`); })()) : num("side", side)) * RAD;
  const r = (x) => Math.round(x * 1e12) / 1e12;
  return {out: [r(Math.cos(a)), r(Math.sin(a)), 0], across: [r(-Math.sin(a)), r(Math.cos(a)), 0], angle: a / RAD};
}
/** The plan of a pass along a hull: how far its regions reach out on `side` at each station along the long
 * axis, within `standoff` of the lane the camera flies (`lane` metres across the side from the axis), as a
 * smooth envelope with look-ahead (`reach` metres; default 3 stand-offs), so the path swings out round
 * towers and blocks before it meets them. `hull`: {regions: [{name, box: {min, max}}], size: {length}}.
 * Returns {out, across, zMin, zMax (the hull's ends), step, z0, raw, reach: [metres at each station], most,
 * reachAt(z): [metres, slope], pointAt(z): the camera's place `standoff` off the envelope}. */
export function passPlan(hull, {side = "port", lane = 0, standoff = 60, reach = null, stations = 160} = {}) {
  num("standoff", standoff, 1e-3); num("lane", lane);
  const regions = hull.regions.filter((g) => g.box), {out, across} = sideAxes(side), Z = [0, 0, 1];
  if (!regions.length) throw fail("a pass needs a hull with regions (hull(...) of vidgen/space-hull)");
  let zMin = Infinity, zMax = -Infinity;
  const spans = regions.map((g) => { const z = span(g.box, Z); zMin = Math.min(zMin, z[0]); zMax = Math.max(zMax, z[1]); return {z, w: span(g.box, across), o: span(g.box, out)[1]}; });
  const L = zMax - zMin, padZ = 0.3 * L, z0 = zMin - padZ, step = (L + 2 * padZ) / (stations - 1), raw = new Array(stations).fill(NaN);
  for (let k = 0; k < stations; k++) {
    const z = z0 + k * step;
    for (const s of spans) if (s.z[1] >= z - step - standoff && s.z[0] <= z + step + standoff && s.w[1] >= lane - standoff && s.w[0] <= lane + standoff) raw[k] = Number.isNaN(raw[k]) ? s.o : Math.max(raw[k], s.o);
  }
  const have = raw.map((v, k) => (Number.isNaN(v) ? -1 : k)).filter((k) => k >= 0);
  if (!have.length) throw fail(`the lane ${lane} m across the ${typeof side === "string" ? side : `${side} degree`} side misses the hull: choose a lane within its ${metres(Math.max(...spans.map((s) => s.w[1])) - Math.min(...spans.map((s) => s.w[0])))} across`);
  for (let k = 0; k < stations; k++) if (Number.isNaN(raw[k])) raw[k] = raw[have.reduce((b, j) => (Math.abs(j - k) < Math.abs(b - k) ? j : b), have[0])];
  const smooth = envelope(raw, (reach ?? 3 * standoff) / step);
  const reachAt = (z) => { const [v, d] = curveAt(smooth, (z - z0) / step); return [v, d / step]; };
  return {out, across, zMin, zMax, length: L, step, z0, raw, reach: smooth, most: Math.max(...smooth), reachAt,
    pointAt: (z, off = standoff) => add(add(scale(out, reachAt(z)[0] + off), scale(across, lane)), [0, 0, z])};
}

// ---------- the rig ----------
const OWN_KEYS = ["sky", "ground", "water", "clouds", "flight", "radius", "center", "music", "ships", "crafts", "margin"];
const TIMING = ["progress", "over", "time", "seconds", "ease", "lens", "roll"];

export class AirCamera extends SpaceCamera {
  /** A SpaceCamera (all its options and moves) that also knows the air's scene: `sky` (the air of
   * vidgen/space-air: the world's radius), `ground` (a land of vidgen/space-land, or a function (x, z, t) ->
   * metres over the sphere), `water` (a sea of vidgen/space-sea), `clouds` (vidgen/space-clouds: decks and
   * towers by name), `flight` (ctx.flight), `music` (ctx.music: times in bars), `ships` ({name: hull}) and
   * `crafts` ({flight name: plane}) so moves can name them, `margin` (metres the camera keeps over ground
   * and water unless a move states its own; default 3), `radius` / `center` for a world without a sky object. */
  constructor(options = {}) {
    const own = {}, rest = {};
    for (const [k, v] of Object.entries(options ?? {})) (OWN_KEYS.includes(k) ? own : rest)[k] = v;
    super(rest);
    const sky = own.sky ?? null;
    if (sky && sky.options && sky.options.unit !== undefined && sky.options.unit !== 1) throw fail("the air's `unit` must be 1 (a scene in metres) for the camera's moves");
    this.sky = sky; this.ground = own.ground ?? null; this.water = own.water ?? null; this.clouds = own.clouds ?? null;
    this.flight = own.flight ?? null; this.music = own.music ?? null; this.ships = own.ships ?? {}; this.crafts = own.crafts ?? {};
    this.margin = num("margin", own.margin ?? 3, 0);
    this.local = localFrame({radius: own.radius ?? (sky && sky.model ? sky.model.radius : 6.371e6), center: own.center ?? null});
  }

  // ----- time -----
  /** A time as seconds of the scene: a number, or {bar, beat} of the score (bars and beats from 1) with `music`. */
  seconds(time, where = "a time") { return sceneTime({music: this.music}, time, where); }
  _common(t, o, who) {
    if (o.over !== undefined) { if (!Array.isArray(o.over) || o.over.length !== 2) throw fail(`${who} over must be [start, end], got ${JSON.stringify(o.over)}`); o = {...o, over: [this.seconds(o.over[0], `${who} over[0]`), this.seconds(o.over[1], `${who} over[1]`)]}; }
    return {...super._common(t, o, who), over: o.over ?? null};
  }
  // progress, its eased value, the move's length in seconds, the cruise share
  _timing(t, o, who, ease = 0.6) {
    const c = this._common(t, o, who);
    if (c.u === null) throw fail(`${who} needs progress (0..1) or over: [start, end]`);
    const e = o.ease ?? ease, T = c.over ? c.over[1] - c.over[0] : num(`${who} seconds`, o.seconds ?? 8, 1e-6);
    return {...c, e: easedEnds(c.u, e), rate: easedRate(c.u, e), peak: easedPeak(e), T, ease: e};
  }

  // ----- the ground -----
  /** The surface's height over the world's sphere (metres) under the scene's (x, z) at t: the higher of the
   * ground and the water (0 with neither). `crest`: the water as high as its waves can stand (for a plan). */
  surface(x, z, t = 0, crest = false) {
    let h = -Infinity;
    const g = this.ground, w = this.water;
    if (typeof g === "function") h = Math.max(h, g(x, z, t));
    else if (g && typeof g.heightAt === "function") h = Math.max(h, g.heightAt(x, z));
    if (w && typeof w.heightAt === "function") h = Math.max(h, crest ? this._crest() : w.heightAt(x, z, t));
    return h === -Infinity ? 0 : h;
  }
  _crest() { const l = this.water && this.water.list; return l && Array.isArray(l.waves) ? l.waves.reduce((s, w) => s + Math.abs(w.amplitude ?? 0), 0) : 0; }
  /** How high a point stands over the ground and the water under it at t (metres; negative: inside). */
  clearance(p, t = 0) {
    const g = this.ground;
    let c = this.local.heightOf(p) - this.surface(p[0], p[2], t);
    if (g && typeof g.above === "function") c = Math.min(c, g.above(p));
    return c;
  }
  // never under `margin` (a move's own, else the rig's) over the surface: the point lifted along the local vertical, and a note when it was
  _clear(p, t, margin, notes, who) {
    const c = this.clearance(p, t), m = margin ?? this.margin;
    if (c >= m - 1e-6) return p;
    notes.push(`${who}: the camera was lifted ${metres(m - c)} to stay ${metres(m)} over the ground at (${metres(p[0])}, ${metres(p[2])})`);
    return along(p, this.local.upAt(p), m - c);
  }
  /** The highest ground within `reach` metres of the scene's [x, z]: {x, z, height (metres over the sphere)}. */
  peakNear(at, reach = 3000) {
    pair("peakNear at", at); num("peakNear reach", reach, 1);
    let best = {x: at[0], z: at[1], height: this.surface(at[0], at[1])}, r = reach;
    for (let pass = 0; pass < 6; pass++, r /= 6) {
      const c = best;
      for (let i = -8; i <= 8; i++) for (let j = -8; j <= 8; j++) { const x = c.x + r * i / 8, z = c.z + r * j / 8, h = this.surface(x, z); if (h > best.height) best = {x, z, height: h}; }
    }
    return best;
  }

  // ----- flights and ships -----
  // a flight as functions of t: a name of ctx.flight, or {position(t), velocity(t), quaternion(t), bank(t)}
  _flight(what, who) {
    if (what && typeof what === "object" && typeof what.position === "function" && !Array.isArray(what.names)) return {name: what.name ?? null, position: (t) => what.position(t), velocity: (t) => what.velocity(t),
      quaternion: (t) => (what.quaternion ? what.quaternion(t) : [0, 0, 0, 1]), bank: (t) => (what.bank ? what.bank(t) : 0)};
    const f = this.flight;
    if (!f || !Array.isArray(f.names)) throw fail(`${who} needs the page's flights (airCamera({flight: ctx.flight}), a web scene with flight_data:) or flight: {position(t), velocity(t)}`);
    const name = what ?? (f.names.length === 1 ? f.names[0] : null);
    if (!f.names.includes(name)) throw fail(`${who}: no flight ${JSON.stringify(name)}${hint(String(name), f.names)}; flights: ${f.names.join(", ")}`);
    return {name, position: (t) => f.position(name, t), velocity: (t) => f.velocity(name, t), quaternion: (t) => f.quaternion(name, t), bank: (t) => f.bank(name, t) / RAD};
  }
  // a plane's size for views in its own frame: {length, span}
  _planeSize(o, name) {
    const c = o.craft ?? (name !== null ? this.crafts[name] : null), s = c && c.size ? c.size : null;
    return {craft: c ?? null, length: num("length", o.length ?? (s ? s.length : 28), 1e-3), span: num("span", o.span ?? (s ? s.width : 20), 1e-3)};
  }
  // a hull at t: its regions and anchors, and its axes in the rig's frame
  _hull(what, t, who) {
    const names = Object.keys(this.ships), h = typeof what === "string" ? this.ships[what] : what ?? (names.length === 1 ? this.ships[names[0]] : null);
    if (typeof what === "string" && !h) throw fail(`${who}: no ship "${what}"${hint(what, names)}; ships of the rig: ${names.join(", ") || "none (airCamera({ships: {Ship: hull}}))"}`);
    if (!h || !Array.isArray(h.regions) || !h.anchors || !h.size) throw fail(`${who} needs ship: a hull of vidgen/space-hull, or its name in airCamera({ships})`);
    const o = h.object, q = o && o.quaternion ? [o.quaternion.x, o.quaternion.y, o.quaternion.z, o.quaternion.w] : [0, 0, 0, 1];
    const conv = this.space ? (p) => [p[0], -p[2], p[1]] : (p) => p, k = this.space || !o || !o.scale ? 1 : o.scale.x;
    const at = o ? this.subject(h, t, `${who}.ship`).at : [0, 0, 0], dir = (v) => conv(rotate(q, v));
    return {hull: h, at, k, dir, out: (p) => add(at, scale(dir(p), k)), subject: {at, radius: h.size.radius * k, name: typeof what === "string" ? what : h.flight && h.flight.body ? h.flight.body : "the ship"}};
  }
  // a shot from a place and a frame in a hull's axes
  _hullShot(H, eye, frame, c, target, extra) {
    return shotOf(H.out(eye), {right: H.dir(frame.right), up: H.dir(frame.up), forward: H.dir(frame.forward)}, c.fov, c.aspect, H.out(target), {subject: H.subject, own: {from: eye.slice(), target: target.slice()}, ...extra});
  }

  // ===== air moves =====
  /** A low pass over sea or ground: the camera flies a ground track from `from` ([x, z]) on the compass
   * `heading` at `speed` m/s (its cruise speed between the eased ends), `clearance` metres over the surface,
   * following the ground with look-ahead (`lookAhead` seconds of flight: the path rises before a ridge and
   * settles after it), turning by `turn` degrees in all through the move with a gentle bank (`bank`: the
   * share of a coordinated turn's bank shown, default 0.35, at most `maxBank` 20). `horizon`: "bank" rolls the
   * picture with the bank, "level" keeps it level. `pitch` (-4): degrees the view looks above the level, plus
   * `follow` (0.5) of the path's own slope. `margin` (default 0.4 x clearance): the camera is never nearer
   * the ground or the water than this; lifted and noted when the plan would be. The shot adds {height,
   * clearance, speed, bank, heading, travelled, lifted}. */
  skim(t, options = {}) {
    known("skim options", options, [...TIMING, "from", "heading", "speed", "clearance", "lookAhead", "turn", "bank", "maxBank", "horizon", "pitch", "follow", "margin"]);
    const c = this._timing(t, options, "skim", [0, 0]), L = this.local;
    const speed = num("skim speed (m/s)", options.speed ?? 90, 1e-3), clearance = num("skim clearance (m)", options.clearance ?? 25, 0.1), ahead = num("skim lookAhead (s)", options.lookAhead ?? 3, 0) * speed;
    const length = speed * c.T / c.peak, track = trackPlan({from: options.from ?? [0, 0], heading: options.heading ?? 0, turn: options.turn ?? 0, length, pad: ahead + 4 * length / 96});
    const reach = Math.max(1, ahead / track.step), heights = envelope(track.x.map((x, k) => this.surface(x, track.z[k], c.time, true)), reach);
    const s = length * c.e, [h, slope] = curveAt(heights, s / track.step + track.first), [x, z] = track.pointAt(s), notes = [];
    const margin = Math.max(options.margin ?? 0.4 * clearance, this.margin), wanted = L.at(x, z, h + clearance), eye = this._clear(wanted, c.time, margin, notes, "skim");
    const now = speed * c.rate, bank = bankOf(now, track.turnAt(s) * now, options.bank ?? 0.35, options.maxBank ?? 20);
    const horizon = oneOf("skim horizon", options.horizon ?? "bank", ["bank", "level"]);
    const pitch = num("skim pitch", options.pitch ?? -4, -90, 90) + (options.follow ?? 0.5) * Math.atan(slope / track.step) / RAD;
    const frame = lookFrame(L.upAt(eye), L.compass(eye, track.headingAt(s)), pitch, (horizon === "bank" ? bank : 0) + c.roll);
    return shotOf(eye, frame, c.fov, c.aspect, along(eye, frame.forward, Math.max(20 * clearance, 200)), {move: "skim", progress: c.u, notes,
      height: L.heightOf(eye), clearance: this.clearance(eye, c.time), speed: now, bank, heading: track.headingAt(s), travelled: s, lifted: len(sub(eye, wanted))});
  }

  // the deck a move goes through: {base, top} (metres over the sphere), by index or name of the rig's clouds
  _deck(deck, who) {
    if (deck && typeof deck === "object") { known(`${who} deck`, deck, ["base", "top", "name"]); num(`${who} deck.base`, deck.base); if (!(num(`${who} deck.top`, deck.top) > deck.base)) throw fail(`${who} deck: top must be above base`); return deck; }
    const decks = this.clouds && Array.isArray(this.clouds.decks) ? this.clouds.decks : null;
    if (!decks) throw fail(`${who} needs deck: {base, top} in metres, or the clouds on the rig (airCamera({clouds})) and a deck's index or name`);
    const d = typeof deck === "string" ? decks.find((q) => q.name === deck) : decks[deck ?? 0];
    if (!d) throw fail(`${who}: no deck ${JSON.stringify(deck)}${typeof deck === "string" ? hint(deck, decks.map((q) => q.name)) : ""}; decks: ${decks.map((q, i) => `${i} (${q.name})`).join(", ")}`);
    return d;
  }
  _through(t, options, who, down) {
    known(`${who} options`, options, [...TIMING, "deck", "at", "below", "above", "heading", "speed", "pitch", "adapt", "settle", "margin"]);
    const c = this._timing(t, options, who, 0.5), L = this.local, d = this._deck(options.deck, who);
    const lo = d.base - num(`${who} below (m)`, options.below ?? 500, 0), hi = d.top + num(`${who} above (m)`, options.above ?? 600, 0);
    const e = down ? 1 - c.e : c.e, h = mix(lo, hi, e), at = pair(`${who} at`, options.at ?? [0, 0]), heading = options.heading ?? 0, speed = num(`${who} speed (m/s)`, options.speed ?? 70, 0);
    const a = heading * RAD, run = speed * c.T * c.u, notes = [];
    const eye = this._clear(L.at(at[0] + Math.sin(a) * run, at[1] - Math.cos(a) * run, h), c.time, options.margin, notes, who);
    // the view: up into the deck while under it, across its top once over it
    const p = options.pitch ?? [10, -5], inside = clamp((h - d.base) / (d.top - d.base)), over = smootherstep((h - d.base + 0.5 * (d.top - d.base)) / (2 * (d.top - d.base)));
    const pitch = isPair(p) ? mix(p[0], p[1], over) : num(`${who} pitch`, p);
    // eye adaptation as a look: the exposure is pulled down as the camera nears the top and recovers over `settle` metres above it
    const adapt = num(`${who} adapt (stops)`, options.adapt ?? 0, 0, 6), settle = num(`${who} settle (m)`, options.settle ?? 500, 1);
    const ev = -adapt * smoothstep(d.base + 0.4 * (d.top - d.base), d.top, h) * (1 - smoothstep(d.top, d.top + settle, h));
    const frame = lookFrame(L.upAt(eye), L.compass(eye, heading), pitch, c.roll);
    return shotOf(eye, frame, c.fov, c.aspect, along(eye, frame.forward, 2000), {move: who, progress: c.u, notes, height: h, deck: {base: d.base, top: d.top, name: d.name ?? null},
      inside: h > d.base && h < d.top, fog: Math.sin(Math.PI * inside), ev, climb: (down ? -1 : 1) * (hi - lo) * c.rate * c.peak / c.T});
  }
  /** A climb through a cloud deck: from `below` metres under its base (500) up through the fog and out
   * `above` metres over its top (600) into the sun, flying on the compass `heading` at `speed` m/s (70) from
   * `at` ([x, z]). `deck`: its index or name in the rig's clouds (the lowest by default), or {base, top}.
   * `pitch`: degrees above the level, or [under, over]: the view turns from looking up into the deck to
   * looking across its top ([10, -5]). `adapt` (stops, 0): eye adaptation as a look: the shot's `ev` falls by
   * that much as the camera nears the top and recovers over `settle` metres (500) above it; give it to the
   * air (`air(..., {ev: (t) => view(t).ev})`) so the break-out is not a white flash. The shot adds {height,
   * deck, inside, fog (0..1 through the deck), ev, climb (m/s)}. */
  climbThrough(t, options = {}) { return this._through(t, options, "climbThrough", false); }
  /** A descent through a cloud deck: `climbThrough` flown the other way, from `above` over the top to
   * `below` under the base; `pitch` [under, over] as there (default [-4, -10] read from over to under). */
  descendThrough(t, options = {}) { return this._through(t, {pitch: [-4, -10], ...options}, "descendThrough", true); }

  /** A chase of a plane on a flight: behind and above it, following with a lag. The camera stands
   * `distance` metres behind the plane (60; a pair [from, to] closes in or falls back through the move)
   * along the flight's direction as it was a moment ago (an exponentially weighted mean over the last `lag`
   * seconds, 0.7: in a turn the camera swings wide and comes round after the plane), `height` metres above
   * it (16) and `side` metres to its right (0), and rolls with `bank` (0.5) of the plane's lagged bank.
   * `flight`: its name in ctx.flight (the only one by default) or {position(t), velocity(t), bank(t)}.
   * `place` ([0, -0.2]: the plane low in the frame, the horizon above it), `lead` (metres ahead of the plane
   * the camera aims at, 0), `climb` (0.5: how much of the flight's climb angle the camera's place follows).
   * Never nearer the ground than `margin`. The shot adds {distance, bank, lagged: the direction followed}. */
  chase(t, options = {}) {
    known("chase options", options, [...TIMING, "flight", "distance", "height", "side", "lag", "bank", "place", "lead", "climb", "margin"]);
    const c = this._common(t, options, "chase"), F = this._flight(options.flight, "chase"), L = this.local, notes = [];
    const p = F.position(t), U = L.upAt(p), lag = num("chase lag (s)", options.lag ?? 0.7, 0, 30);
    const v = unit(lagged((x) => unit(F.velocity(x)), t, lag)), level = square(v, U, [0, 0, -1]), d = unit(along(level, U, dot(v, U) * (options.climb ?? 0.5)));
    const e = c.u === null ? 0 : easedEnds(c.u, options.ease ?? 0.6), dOpt = options.distance ?? 60, dist = isPair(dOpt) ? mix(dOpt[0], dOpt[1], e) : num("chase distance (m)", dOpt, 1e-3);
    const right = cross(level, U), wanted = add(add(along(p, d, -dist), scale(U, options.height ?? 16)), scale(right, options.side ?? 0));
    const eye = this._clear(wanted, c.time, options.margin, notes, "chase"), bank = (options.bank ?? 0.5) * lagged(F.bank, t, lag);
    const shot = shotAt(eye, along(p, level, options.lead ?? 0), {up: L.upAt(eye), fov: c.fov, aspect: c.aspect, place: options.place ?? [0, -0.2], roll: -(bank + c.roll), ahead: level});
    return {...shot, move: "chase", notes, subject: {at: p, radius: 0.5 * this._planeSize(options, F.name).length, name: F.name ?? "the plane"}, progress: c.u, distance: len(sub(eye, p)), bank, lagged: v};
  }

  /** A view locked to the plane's own frame: the camera rides on it, so the plane stands still in the
   * picture and the world tilts as it banks. `view`: a name of WING_VIEWS ("wingtip": from the shoulder out
   * over the wing's tip, "tail", "belly": from under and ahead looking back up at the tiles, "nose") or {at,
   * toward}: the camera's place (metres) and its view direction in the plane's axes ([left wing, up, nose]).
   * `side`: "left" or "right" of the plane. The plane's `length` and `span` (and its wing tip) are read
   * from `craft` (a plane of vidgen/space-plane, or the rig's `crafts[flight]`) or given in metres (28 and
   * 20 without either). `lens`, `roll`. No "up" of the world is used: no flip in any attitude. */
  wing(t, options = {}) {
    known("wing options", options, ["time", "lens", "roll", "flight", "view", "side", "craft", "length", "span"]);
    const c = this._common(t, options, "wing"), F = this._flight(options.flight, "wing"), size = this._planeSize(options, F.name);
    let view = options.view ?? "wingtip", name = null;
    if (typeof view === "string") {
      if (!(view in WING_VIEWS)) throw fail(`no view "${view}"${hint(view, Object.keys(WING_VIEWS))}; views: ${Object.keys(WING_VIEWS).join(", ")}, or {at, toward} in the plane's axes`);
      name = view;
      const w = WING_VIEWS[view], own = (a) => [a[0] * size.span, a[1] * size.length, a[2] * size.length], at = own(w.at);
      const tips = w.tip && size.craft && size.craft.anchors && Array.isArray(size.craft.anchors.wingTips) ? size.craft.anchors.wingTips : null, tip = tips && tips.length ? tips.reduce((b, q) => (q.p[0] > b.p[0] ? q : b)).p : null;
      view = {at, toward: sub(tip ? [tip[0], tip[1] + w.look[1] * size.length, tip[2]] : own(w.look), at), lens: w.lens};
    }
    else { known("wing view", view, ["at", "toward", "lens"]); if (!isVec(view.at) || !isVec(view.toward)) throw fail("wing view: {at: [x, y, z] metres, toward: [x, y, z]} in the plane's axes (x the left wing, y up, z the nose)"); }
    const sx = oneOf("wing side", options.side ?? "left", ["left", "right"]) === "left" ? 1 : -1, flip = (a) => [a[0] * sx, a[1], a[2]];
    const q = F.quaternion(t), p = F.position(t), fov = (c.lens ?? lens(view.lens ?? "wide")).fov;
    const eye = add(p, rotate(q, flip(view.at))), frame = frameOf(rotate(q, flip(view.toward)), rotate(q, [0, 1, 0]), c.roll);
    return shotOf(eye, frame, fov, c.aspect, along(eye, frame.forward, size.span), {move: "wing", view: name, subject: {at: p, radius: 0.5 * size.length, name: F.name ?? "the plane"}});
  }

  /** The plane passes a camera that stands still: in the air beside its path, or on the ground. The camera
   * is where the plane will be at `at` (a time: seconds or {bar, beat}; default the middle of `over`), moved
   * `closest` metres (120) to the `side` ("left" or "right" of the flight) and `rise` metres up (-12: a
   * little under the path, the plane against the sky); `stand: "ground"` puts it `eye` metres (2) over the
   * ground under that place instead. It turns to keep the plane at `place`; the turn is fastest at the
   * pass (a whip-pan of speed / closest radians a second: the shot's `pan`, degrees a second). `lag`
   * (seconds, 0.06): the operator's reaction: the plane runs a little ahead of the frame at the pass. */
  flyPast(t, options = {}) {
    known("flyPast options", options, ["time", "over", "lens", "roll", "flight", "at", "closest", "side", "rise", "stand", "eye", "place", "lag", "margin"]);
    const c = this._common(t, options, "flyPast"), F = this._flight(options.flight, "flyPast"), L = this.local, notes = [];
    const at = options.at !== undefined ? this.seconds(options.at, "flyPast at") : c.over ? 0.5 * (c.over[0] + c.over[1]) : (() => { throw fail("flyPast needs at: the time of the pass, or over: [start, end] (the pass is in its middle)"); })();
    const p0 = F.position(at), U0 = L.upAt(p0), level = square(F.velocity(at), U0, [0, 0, -1]), right = cross(level, U0);
    const sx = oneOf("flyPast side", options.side ?? "left", ["left", "right"]) === "left" ? -1 : 1, closest = num("flyPast closest (m)", options.closest ?? 120, 1e-3);
    let eye = add(along(p0, right, sx * closest), scale(U0, options.rise ?? -12));
    const onGround = oneOf("flyPast stand", options.stand ?? "air", ["air", "ground"]) === "ground", high = num("flyPast eye (m)", options.eye ?? 2, 0), margin = options.margin ?? (onGround ? Math.min(high, this.margin) : this.margin);
    if (onGround) eye = L.at(eye[0], eye[2], this.surface(eye[0], eye[2], c.time, true) + high);
    eye = this._clear(eye, c.time, margin, notes, "flyPast");
    const lag = num("flyPast lag (s)", options.lag ?? 0.06, 0, 5), aim = (x) => lagged(F.position, x, lag, 6), p = F.position(t);
    const shotFor = (x) => shotAt(eye, aim(x), {up: L.upAt(eye), fov: c.fov, aspect: c.aspect, place: options.place ?? [0, 0.25], roll: c.roll, ahead: level});
    const shot = shotFor(t), h = 1 / 120, a = shotFor(t - h).forward, b = shotFor(t + h).forward;
    return {...shot, move: "flyPast", notes, subject: {at: p, radius: 0.5 * this._planeSize(options, F.name).length, name: F.name ?? "the plane"}, progress: c.u, distance: len(sub(p, eye)),
      pass: at, margin, pan: Math.atan2(len(cross(a, b)), dot(a, b)) / RAD / (2 * h)};
  }

  /** Circle a mountain, a volcano or a tower of cloud, keeping it in the frame. `around`: [x, z] (the
   * ground's top there), {near: [x, z], reach}: the highest ground within `reach` metres (peakNear), or
   * {tower: n}: a tower of the rig's clouds. `radius` (metres; default 3 x a tower's radius, else 2500),
   * `height` (metres over the top; default 0.12 x radius; negative: under it), `start` (the compass bearing
   * from the middle to the camera at the start, 180: south of it), `sweep` (degrees flown round, 90; negative
   * the other way), `aim` (metres over the top the camera looks at, default -0.12 x radius: into its upper
   * slopes), `place` ([0, 0.05]), default lens "wide". `top`: the top's height over the sphere, when not the ground's. The circle
   * rises smoothly over ground that stands nearer than `clearance` (150 m) under it. The shot adds {bearing,
   * height, top, speed (m/s at the middle of the move)}. */
  orbitPeak(t, options = {}) {
    known("orbitPeak options", options, [...TIMING, "around", "radius", "height", "start", "sweep", "aim", "place", "top", "clearance", "margin"]);
    const c = this._timing(t, {lens: "wide", ...options}, "orbitPeak", 0.4), L = this.local, notes = [];
    let mid, top, r0 = 2500;
    const a = options.around ?? [0, 0];
    if (isPair(a)) { mid = a; top = this.surface(a[0], a[1], c.time); }
    else if (a && typeof a === "object" && a.tower !== undefined) {
      known("orbitPeak around", a, ["tower"]);
      const list = this.clouds && Array.isArray(this.clouds.towers) ? this.clouds.towers : [], w = list[a.tower];
      if (!w) throw fail(`orbitPeak: no tower ${JSON.stringify(a.tower)}; the rig's clouds have ${list.length} (airCamera({clouds}), clouds(..., {towers}))`);
      mid = [w.x, w.z]; top = w.top; r0 = 3 * w.radius;
    } else if (a && typeof a === "object" && a.near !== undefined) { known("orbitPeak around", a, ["near", "reach"]); const pk = this.peakNear(a.near, a.reach ?? 3000); mid = [pk.x, pk.z]; top = pk.height; }
    else throw fail(`orbitPeak around must be [x, z], {near: [x, z], reach} or {tower: n}, got ${JSON.stringify(a)}`);
    if (options.top !== undefined) top = num("orbitPeak top", options.top);
    const radius = num("orbitPeak radius (m)", options.radius ?? r0, 1), height = num("orbitPeak height (m)", options.height ?? 0.12 * radius), sweep = num("orbitPeak sweep", options.sweep ?? 90, -1080, 1080);
    const start = num("orbitPeak start", options.start ?? 180), clearance = num("orbitPeak clearance (m)", options.clearance ?? 150, 0);
    // the ground under the circle, with look-ahead, and a smooth rise over it where it stands too near
    const n = 72, pad = 8, spanDeg = Math.abs(sweep) || 1, stepDeg = spanDeg / n, at = (k) => { const b = (start + Math.sign(sweep || 1) * (k - pad) * stepDeg) * RAD; return [mid[0] + radius * Math.sin(b), mid[1] - radius * Math.cos(b)]; };
    const ground = envelope(Array.from({length: n + 2 * pad + 1}, (_, k) => { const q = at(k); return this.surface(q[0], q[1], c.time, true); }), Math.max(1, 0.06 * radius / (radius * stepDeg * RAD)));
    const [g] = curveAt(ground, c.e * n + pad), safe = g + clearance, want = top + height, soft = Math.max(0.15 * clearance, 1);
    const over = (safe - want) / soft, h = want + soft * (over > 30 ? over : Math.log1p(Math.exp(Math.max(over, -50))));
    const bearing = start + sweep * c.e, b = bearing * RAD, eye = this._clear(L.at(mid[0] + radius * Math.sin(b), mid[1] - radius * Math.cos(b), h), c.time, options.margin, notes, "orbitPeak");
    const target = L.at(mid[0], mid[1], top + (options.aim ?? -0.12 * radius));
    const shot = shotAt(eye, target, {up: L.upAt(eye), fov: c.fov, aspect: c.aspect, place: options.place ?? [0, 0.05], roll: c.roll, ahead: sub(target, eye)});
    return {...shot, move: "orbitPeak", notes, subject: {at: target, radius: 0, name: "the peak"}, progress: c.u, bearing, height: h, top, radius, speed: radius * Math.abs(sweep) * RAD * c.rate * c.peak / c.T};
  }

  /** A vertical crane up from the surface to altitude, revealing the curve of the world. Over the scene's
   * `at` ([x, z]) the camera rises from `from` metres over the ground (20) to `to` (30000); the height is
   * multiplied by a constant for each step of eased progress, so the start is slow and the world falls away
   * at the end. It looks along the compass `heading` and keeps the horizon at `horizon` in the frame (y from
   * -1 to 1; 0.3: in the upper part, the world filling the frame under it) by tilting down as the horizon
   * dips. `lens`: one lens, or [from, to]: it widens with the climb (the field of view glides between them).
   * `drift` (m/s, 0): flying forward as it rises. `down: true` flies the same move from the top to the
   * surface (the end of a descent). The shot adds {height (over the sphere), aboveGround, dip, pitch, climb}. */
  rise(t, options = {}) {
    known("rise options", options, [...TIMING.filter((k) => k !== "lens"), "lens", "at", "from", "to", "heading", "horizon", "drift", "down", "margin"]);
    const pairOfLenses = Array.isArray(options.lens), c = this._timing(t, {...options, lens: pairOfLenses ? undefined : options.lens}, "rise", 0.7), L = this.local, notes = [];
    const lo = num("rise from (m)", options.from ?? 20, 1e-2), hi = num("rise to (m)", options.to ?? 30000, 1e-2), at = pair("rise at", options.at ?? [0, 0]);
    if (!(hi > lo)) throw fail(`rise: to (${hi} m) must be above from (${lo} m)`);
    const e = options.down ? 1 - c.e : c.e, above = Math.exp(mix(Math.log(lo), Math.log(hi), e)), heading = options.heading ?? 0, a = heading * RAD, run = (options.drift ?? 0) * c.T * c.u;
    const x = at[0] + Math.sin(a) * run, z = at[1] - Math.cos(a) * run, h = this.surface(x, z, c.time, true) + above;
    const eye = this._clear(L.at(x, z, h), c.time, options.margin, notes, "rise");
    const fov = pairOfLenses ? Math.exp(mix(Math.log(lens(options.lens[0]).fov), Math.log(lens(options.lens[1]).fov), e)) : c.fov;
    const dip = horizonDip(L.radius, L.heightOf(eye)), pitch = -dip - Math.atan(num("rise horizon", options.horizon ?? 0.3, -1, 1) * Math.tan(fov * RAD / 2)) / RAD;
    const frame = lookFrame(L.upAt(eye), L.compass(eye, heading), pitch, c.roll);
    return shotOf(eye, frame, fov, c.aspect, along(eye, frame.forward, Math.max(above * 4, 100)), {move: "rise", progress: c.u, notes, height: L.heightOf(eye), aboveGround: above, dip, pitch,
      climb: (options.down ? -1 : 1) * above * Math.log(hi / lo) * c.rate * c.peak / c.T});
  }

  /** From orbit to the ground in one move (the world of vidgen/space-descent draws every height): the camera
   * comes down over the scene's `at` ([x, z]) from `from` metres over the sphere (400 km) to `to` metres over
   * the surface (300), its height falling by equal factors in equal times (the logarithm of the height runs
   * steadily, so every power of ten of height gets the same time and the fall reads as steady), eased at
   * the top and settled at the bottom (`ease`: [top, bottom], default [0.3, 0.35]: it ends with no sink). The
   * view follows the horizon, which stands `horizon` (0.3) of the half frame over the middle: from orbit that
   * is down at the globe with the limb across the top, at the end along the level; `look` (degrees under
   * the level) starts it steeper and lets it rise to the horizon's rule over the first two thirds. It turns
   * by `turn` degrees in all, ending on the compass `heading`, and from `run` (0.45) of the move on it gathers
   * way along its heading up to `speed` m/s (90) at the end: it ENDS MOVING, level, so a `skim` given
   * `shot.end` ({from, heading, speed, clearance, pitch, lens}) follows in the same scene with no cut. `lens`:
   * one lens or [from, to]. `margin`: never nearer the ground or the water. This is a camera's descent, far
   * faster and steeper than any vehicle's: `shot.sink` (m/s) says how fast. The shot adds {height,
   * aboveGround, dip, pitch, heading, speed, sink, travelled, end}. */
  descend(t, options = {}) { return this._descent(t, options, "descend", false); }
  /** `descend` flown backwards: from `to` metres over the surface, moving, up to `from` metres over the
   * sphere, the same path, view and timing in reverse (it leaves the level flight of a `skim` given
   * `shot.end` and ends looking down at the globe). */
  ascend(t, options = {}) { return this._descent(t, options, "ascend", true); }
  _descent(t, options, who, upward) {
    known(`${who} options`, options, [...TIMING.filter((k) => k !== "lens"), "lens", "at", "from", "to", "heading", "turn", "horizon", "look", "speed", "run", "margin"]);
    const pairOfLenses = Array.isArray(options.lens), c = this._timing(t, {...options, lens: pairOfLenses ? undefined : options.lens, ease: 0}, who, 0), L = this.local, notes = [];
    const hi = num(`${who} from (m)`, options.from ?? 400e3, 1e-2), lo = num(`${who} to (m)`, options.to ?? 300, 1e-2), at = pair(`${who} at`, options.at ?? [0, 0]);
    if (!(hi > lo)) throw fail(`${who}: from (${hi} m, the top) must be above to (${lo} m, the bottom)`);
    const ease = options.ease ?? [0.3, 0.35], speed = num(`${who} speed (m/s)`, options.speed ?? 90, 0), run = num(`${who} run`, options.run ?? 0.45, 0, 0.95);
    const heading = num(`${who} heading`, options.heading ?? 0), swing = num(`${who} turn`, options.turn ?? 0), horizon = num(`${who} horizon`, options.horizon ?? 0.3, -1, 1);
    const look = options.look === undefined || options.look === null ? null : num(`${who} look`, options.look, 0, 90);
    const fovAt = (e) => (pairOfLenses ? Math.exp(mix(Math.log(lens(options.lens[0]).fov), Math.log(lens(options.lens[1]).fov), e)) : c.fov);
    const headAt = (u) => heading - swing * (1 - smootherstep(u)), wayAt = (u) => speed * smoothstep(run, 1, u);
    // the ground track: the way made good along the turning heading, summed in fixed steps (the same for every t)
    const place = (u) => {
      let x = at[0], z = at[1];
      if (u > run && speed > 0) {
        const n = 48, du = (u - run) / n;
        for (let i = 0; i <= n; i++) { const s = run + du * i, k = (i === 0 || i === n ? 1 : i % 2 ? 4 : 2) * du / 3 * c.T * wayAt(s), a = headAt(s) * RAD; x += Math.sin(a) * k; z -= Math.cos(a) * k; }
      }
      return [x, z];
    };
    const [ex, ez] = place(1), floor = this.surface(ex, ez, c.time, true);                         // heights are over the surface where the move ends
    const state = (u) => {
      const e = easedEnds(u, ease), above = Math.exp(mix(Math.log(hi), Math.log(lo), e)), [x, z] = place(u), fov = fovAt(e);
      const p = L.at(x, z, floor + above), dip = horizonDip(L.radius, L.heightOf(p)), level = -dip - Math.atan(horizon * Math.tan(fov * RAD / 2)) / RAD;
      return {e, above, x, z, p, fov, dip, pitch: look === null ? level : mix(-look, level, smootherstep(u / 0.67))};
    };
    const u = upward ? 1 - c.u : c.u, s = state(u), last = state(1);
    const eye = this._clear(s.p, c.time, options.margin, notes, who);
    const frame = lookFrame(L.upAt(eye), L.compass(eye, headAt(u)), s.pitch, c.roll);
    const sink = s.above * Math.log(hi / lo) * easedRate(u, ease) * easedPeak(ease) / c.T;
    return shotOf(eye, frame, s.fov, c.aspect, along(eye, frame.forward, Math.max(s.above * 2, 100)), {move: who, progress: c.u, notes, height: L.heightOf(eye), aboveGround: s.above, dip: s.dip, pitch: s.pitch,
      heading: headAt(u), speed: wayAt(u), sink: upward ? -sink : sink, travelled: len(sub([s.x, 0, s.z], [at[0], 0, at[1]])),
      end: {from: [ex, ez], heading, speed, clearance: lo, pitch: last.pitch, lens: {fov: last.fov}}});
  }

  // ===== ship moves =====
  /** A slow pass close along a hull with a wide lens, so detail streams by at several depths. The camera
   * flies along the hull's long axis `standoff` metres (60) off its `side` ("port", "starboard", "dorsal",
   * "ventral", or degrees round the axis from port towards the top), in a `lane` (metres across that side
   * from the axis). Its path comes from the hull's regions: it swings out round towers and blocks before it
   * meets them (`reach`: the look-ahead, metres; 3 stand-offs) and is never nearer a region's box than the
   * stand-off. `from` (0.1) and `to`: where along the hull it starts and ends, as shares of its length from
   * the stern (0) to the bow (1); or `speed` (m/s along the hull; 40) and `toward` ("bow" or "stern") in
   * place of `to`. It looks `ahead` metres (default the larger of 8 stand-offs and a fifth of the hull) along
   * its path, drawn `inward` (0.6) of the stand-off towards the wall and turned `yaw` degrees (8) more towards
   * it, the hull's top up (over the deck or under the keel: the hull's surface is the ground or the ceiling). Default lens
   * "ultra-wide". The shot adds {station: share of the length, speed (m/s), offset (metres off the axis),
   * clearance: {distance, region}}; a pass faster than a twelfth of the hull a second is noted (a toy). */
  hullPass(t, options = {}) {
    known("hullPass options", options, [...TIMING, "ship", "side", "lane", "standoff", "reach", "from", "to", "speed", "toward", "ahead", "inward", "yaw"]);
    const c = this._timing(t, {lens: "ultra-wide", ...options}, "hullPass", [0, 0]), H = this._hull(options.ship, t, "hullPass"), notes = [];
    const standoff = num("hullPass standoff (m)", options.standoff ?? 60, 1e-3), plan = passPlan(H.hull, {side: options.side ?? "port", lane: options.lane ?? 0, standoff, reach: options.reach ?? null});
    const from = num("hullPass from", options.from ?? 0.1, -0.3, 1.3), sign = oneOf("hullPass toward", options.toward ?? "bow", ["bow", "stern"]) === "bow" ? 1 : -1;
    const length = options.to !== undefined && options.speed === undefined ? (num("hullPass to", options.to, -0.3, 1.3) - from) * plan.length : sign * num("hullPass speed (m/s)", options.speed ?? 40, 1e-6) * c.T / c.peak;
    const z = plan.zMin + from * plan.length + length * c.e, dirn = Math.sign(length) || 1, eye = plan.pointAt(z), speed = Math.abs(length) * c.peak / c.T;
    const ahead = num("hullPass ahead (m)", options.ahead ?? Math.max(8 * standoff, 0.2 * plan.length), 1e-3), target = plan.pointAt(z + dirn * ahead, standoff * (1 - (options.inward ?? 0.6)));
    const clear = hullClearance(H.hull.regions, eye);
    if (clear.distance < 0.98 * standoff) notes.push(`hullPass: the camera is ${metres(clear.distance)} from ${clear.region}, nearer than its stand-off of ${metres(standoff)}`);
    if (speed > TOY_SHARE * plan.length) notes.push(`hullPass: ${speed.toFixed(0)} m/s passes a ${metres(plan.length)} hull in ${(plan.length / speed).toFixed(0)} s: it will read as a model; a slow pass is under ${(TOY_SHARE * plan.length).toFixed(0)} m/s`);
    const view = turn(unit(sub(target, eye)), unit(cross(plan.out, [0, 0, dirn])), num("hullPass yaw", options.yaw ?? 8, -80, 80) * RAD);
    return this._hullShot(H, eye, frameOf(view, Math.abs(plan.out[1]) > 0.9 ? scale(plan.out, 1) : [0, 1, 0], c.roll), c, target, {move: "hullPass", progress: c.u, notes, station: (z - plan.zMin) / plan.length, speed: speed * c.rate, offset: plan.reachAt(z)[0] + standoff, clearance: clear});
  }

  /** A ship revealed. `mode: "traverse"` (the default): the camera looks along the ship's own heading from
   * just under it ("under", the default `side`) or over it ("over"), the hull out of the frame behind it;
   * the bow slides into the picture at `at` (seconds or {bar, beat}) and the hull keeps coming at `speed`
   * m/s (default a thirtieth of its length a second) until the bells pass: the size is told by how long it
   * takes. The camera is `standoff` metres (default 0.03 x the length) clear of the hull's furthest reach on
   * that side, in the `lane` (metres to port of the axis), tilted `tilt` degrees (22) towards the hull.
   * Default lens "ultra-wide". The shot adds `covered` (the share of the hull that has passed over the
   * camera) and `escort`: where a small craft should be (the hull's axes: `craft.object.position.set(...)`
   * for a craft of `ship.scaleRef`) so that it comes into the frame last, after the stern, for scale
   * (`escort: {after: seconds after the stern passes (1), speed: m/s past the camera (0.4 x speed), gap:
   * metres under the camera's line (0.4 x standoff)}`).
   * `mode: "limb"`: the ship comes out from behind a world: `reveal` of vidgen/space-camera with the ship as
   * its subject (`behind`: the world; `at`, `rate`, `distance`, `horizon`, `place`, `margin`, `lens`). */
  hullReveal(t, options = {}) {
    const mode = oneOf("hullReveal mode", options.mode ?? "traverse", ["traverse", "limb"]);
    if (mode === "limb") {
      known("hullReveal options (mode: \"limb\")", options, ["mode", "ship", "behind", "at", "rate", "distance", "horizon", "place", "margin", "lens", "roll", "time", "air", "plane", "follow"]);
      const {mode: _m, ship, at, ...rest} = options, H = this._hull(ship, t, "hullReveal");
      if (rest.behind === undefined || rest.behind === null) throw fail('hullReveal mode: "limb" needs behind: the world the ship comes out from behind (a subject with a radius)');
      const of = this.space && H.hull.flight && H.hull.flight.body ? {body: H.hull.flight.body, radius: H.subject.radius, name: H.subject.name} : {at: H.at, radius: H.subject.radius, name: H.subject.name};
      return {...this.reveal(t, {lens: "long", ...rest, of, at: this.seconds(at ?? 0, "hullReveal at")}), move: "hullReveal", mode, notes: []};
    }
    known("hullReveal options", options, ["mode", "time", "lens", "roll", "ship", "side", "lane", "standoff", "speed", "at", "tilt", "escort"]);
    const c = this._common(t, {lens: "ultra-wide", ...options}, "hullReveal"), H = this._hull(options.ship, t, "hullReveal");
    const under = oneOf("hullReveal side", options.side ?? "under", ["under", "over"]) === "under", lane = options.lane ?? 0;
    const L = H.hull.size.length, standoff = num("hullReveal standoff (m)", options.standoff ?? 0.03 * L, 1e-3), plan = passPlan(H.hull, {side: under ? "ventral" : "dorsal", lane: under ? lane : -lane, standoff});
    const speed = num("hullReveal speed (m/s)", options.speed ?? L / 30, 1e-6), tilt = num("hullReveal tilt", options.tilt ?? 22, 0, 80), at = this.seconds(options.at ?? 0, "hullReveal at");
    // the camera's line: clear of the hull's furthest reach; the bow's lower edge enters at the frame's edge at `at`
    const off = plan.most + standoff, toHull = scale(plan.out, -1), edge = Math.min((tilt + c.fov / 2) * RAD, 89 * RAD);
    let zAt = -Infinity;
    plan.raw.forEach((r, k) => { const zk = plan.z0 + k * plan.step; if (zk >= plan.zMin && zk <= plan.zMax) zAt = Math.max(zAt, zk - (off - r) / Math.tan(edge)); });
    const z = zAt - speed * (c.time - at);
    const eye = add(add(scale(plan.out, off), scale(plan.across, under ? lane : -lane)), [0, 0, z]);
    const forward = along(scale([0, 0, 1], Math.cos(tilt * RAD)), toHull, Math.sin(tilt * RAD)), top = scale(along(scale(toHull, Math.cos(tilt * RAD)), [0, 0, 1], -Math.sin(tilt * RAD)), under ? 1 : -1);
    const e = options.escort ?? {};
    known("hullReveal escort", e, ["after", "speed", "gap"]);
    const tStern = at + (plan.zMax - plan.zMin) / speed, vE = num("escort speed", e.speed ?? 0.4 * speed, 1e-6), enter = tStern + (e.after ?? 1), gap = e.gap ?? 0.4 * standoff;
    // the escort: on a line `gap` towards the hull side of the camera's, passing the camera's station at `enter`
    const escort = add(add(scale(plan.out, off - gap), scale(plan.across, (under ? lane : -lane) + 0.5 * gap)), [0, 0, z + vE * (c.time - enter)]);
    const target = along(eye, forward, 0.3 * L);
    return this._hullShot(H, eye, frameOf(forward, top, c.roll), c, target, {move: "hullReveal", mode, notes: [], first: at, covered: clamp((zAt - z) / (plan.zMax - plan.zMin)), stern: tStern, speed,
      escort, escortEnters: enter, clearance: hullClearance(H.hull.regions, eye)});
  }

  /** Fly into a hangar (or pull out of one). `hangar`: its name on the hull ("hangar-2"; the first by
   * default). The camera comes from `from` metres out (default 4 mouth widths, at least 300) and `along`
   * metres to the side along the wall (default 0.7 x from: an approach at an angle, the wall and the mouth
   * growing), swings on to the mouth's axis and goes on to `deep` (0.35) of the bay's depth inside, looking
   * at the back of the bay. `rise` (-0.28): where in the mouth's height it flies, as a share of the height
   * from its middle. `out: true` flies it backwards: out of the bay, still looking in. Inside it keeps
   * within the mouth; outside, a place nearer than `clear` metres (25) to another part of the hull is noted.
   * Default lens "wide". The shot adds {distance: metres outside the mouth (negative inside), inside}. */
  intoBay(t, options = {}) {
    known("intoBay options", options, [...TIMING, "ship", "hangar", "from", "along", "deep", "rise", "out", "clear"]);
    const c = this._timing(t, {lens: "wide", ...options}, "intoBay", 0.7), H = this._hull(options.ship, t, "intoBay"), bays = H.hull.anchors.hangars ?? [], notes = [];
    const bay = options.hangar === undefined ? bays[0] : bays.find((q) => q.name === options.hangar);
    if (!bay) throw fail(`intoBay: no hangar ${JSON.stringify(options.hangar ?? null)}${options.hangar ? hint(String(options.hangar), bays.map((q) => q.name)) : ""}; hangars: ${bays.map((q) => q.name).join(", ") || "none on this hull"}`);
    const n = unit(bay.n), tan = Math.abs(n[1]) > 0.9 ? [0, 0, 1] : unit(cross([0, 1, 0], n)), upB = cross(n, tan);
    const from = num("intoBay from (m)", options.from ?? Math.max(4 * bay.width, 300), 1e-3), deep = num("intoBay deep", options.deep ?? 0.35, 0, 0.9), side = options.along ?? 0.7 * from;
    const e = options.out ? 1 - c.e : c.e, d = mix(from, -deep * bay.depth, e), w = smootherstep(clamp(d / from)), rise = num("intoBay rise", options.rise ?? -0.28, -0.45, 0.45) * bay.height;
    const eye = add(add(along(bay.p, n, d), scale(tan, side * w)), scale(upB, rise + 0.12 * from * w));
    const target = add(along(bay.p, n, -0.92 * bay.depth), scale(upB, rise - 0.1 * bay.height));
    if (d > 0) {
      const inside = along(bay.p, n, -1), clear = hullClearance(H.hull.regions, eye, (g) => boxDistance(inside, g.box) === 0), least = num("intoBay clear (m)", options.clear ?? 25, 0);
      if (clear.distance < Math.min(least, d)) notes.push(`intoBay: the camera is ${metres(clear.distance)} from ${clear.region} on its way in: come from another side (along: ${(-side).toFixed(0)}) or from further out`);
    }
    return this._hullShot(H, eye, frameOf(sub(target, eye), upB, c.roll), c, target, {move: "intoBay", progress: c.u, notes, hangar: bay.name, distance: d, inside: d < 0});
  }

  /** Behind the engine bank as it lights. The camera stands `distance` metres (default 3 x the bank's
   * radius) astern of the bells, off their axis (`off`: [port, up] as shares of the distance, [0.45, 0.22]:
   * outside the plume), looking at the bank, and creeps in by `creep` (0.06) of the distance until the bank
   * lights at `light` (seconds or {bar, beat}: a bar line); then it is pushed back `push` metres (default
   * 0.5 x the bank's radius) without overshoot (`settle` seconds, 0.45). `shake`: only when given: {amount
   * (degrees, 0.25), seed, rate (Hz, 7), decay (seconds, 1.6), hold (the share that stays while the bank
   * burns, 0.15)}: a seeded tremble that starts with the light. The shot adds `throttle` (0 before the
   * light, rising to 1 over `rise` seconds, 0.35: give it to `ship.update(t, {throttle})`), `pushed`
   * (metres) and `burning` (seconds since the light). */
  sternBurn(t, options = {}) {
    known("sternBurn options", options, [...TIMING, "ship", "light", "distance", "off", "creep", "push", "settle", "shake", "rise"]);
    const c = this._common(t, {lens: "wide-normal", ...options}, "sternBurn"), H = this._hull(options.ship, t, "sternBurn"), bells = H.hull.anchors.bells ?? [];
    if (!bells.length) throw fail("sternBurn needs a ship with bells (hull.anchors.bells)");
    const mid = scale(bells.reduce((s, b) => add(s, b.p), [0, 0, 0]), 1 / bells.length), bank = Math.max(...bells.map((b) => len(sub(b.p, mid)) + (b.radius ?? 0)));
    const light = this.seconds(options.light ?? (c.over ? 0.5 * (c.over[0] + c.over[1]) : 0), "sternBurn light"), age = c.time - light;
    const dist = num("sternBurn distance (m)", options.distance ?? 3 * bank, 1e-3), off = options.off ?? [0.45, 0.22], start = c.over ? c.over[0] : light - 4;
    const creep = (options.creep ?? 0.06) * dist * smootherstep(clamp((c.time - start) / Math.max(light - start, 1e-6))), pushed = pushBack(age, options.push ?? 0.5 * bank, options.settle ?? 0.45);
    const away = unit([off[0], off[1], -1]), eye = along(mid, away, dist - creep + pushed);
    let frame = frameOf(sub(mid, eye), [0, 1, 0], c.roll);
    if (options.shake !== undefined && options.shake !== null && options.shake !== false && age > 0) {
      const s = options.shake === true ? {} : options.shake;
      known("sternBurn shake", s, ["amount", "seed", "rate", "decay", "hold"]);
      const env = (1 - Math.exp(-age / 0.05)) * ((s.hold ?? 0.15) + (1 - (s.hold ?? 0.15)) * Math.exp(-age / (s.decay ?? 1.6))), k = shake(c.time, {amount: (s.amount ?? 0.25) * env, seed: s.seed ?? 1, rate: s.rate ?? 7});
      const f = turn(turn(frame.forward, frame.up, k.yaw * RAD), frame.right, k.pitch * RAD);
      frame = frameOf(f, frame.up, k.roll);
    }
    return this._hullShot(H, eye, frame, c, mid, {move: "sternBurn", progress: c.u, notes: [], light, burning: Math.max(age, 0), throttle: smoothstep(0, options.rise ?? 0.35, age), pushed, bank: {at: mid, radius: bank}});
  }

  /** Powers of ten from a window row to the whole ship to the ship as a speck by its world: a `zoom` of
   * vidgen/space-camera whose landing points are made from the hull. `window`: a place on the hull (an
   * anchor's or a region's name, or [x, y, z] in its axes; default its bridge, else its port side), seen
   * from `close` metres (60); the whole ship filling `fill` (0.7) of the frame's height; then `world` (a
   * subject: the world it flies round) from `far` (default {radii: 4}). The camera backs straight away
   * along the wall's outward direction lifted by `lift` degrees (20). `over` or `rate`, `hold` (seconds on
   * the whole ship), `ease`, `lens` as the zoom's. Without `world` it ends on the whole ship. */
  scaleZoom(t, options = {}) {
    known("scaleZoom options", options, ["time", "over", "start", "lens", "roll", "ship", "window", "close", "fill", "world", "far", "rate", "hold", "ease", "lift"]);
    const H = this._hull(options.ship, t, "scaleZoom"), hull = H.hull, c = this._common(t, options, "scaleZoom");
    let place = options.window ?? (hull.anchors.points.bridge ? "bridge" : "port"), n = null;
    if (typeof place === "string") {
      const a = hull.anchors.points[place], g = a ? null : hull.regions.find((q) => q.name === place);
      if (!a && !g) throw fail(`scaleZoom: no anchor or region "${place}"${hint(place, [...Object.keys(hull.anchors.points), ...hull.regions.map((q) => q.name)])} on the hull`);
      n = a ? a.n : g.normal; place = a ? a.p : g.centre;
    } else if (!isVec(place)) throw fail(`scaleZoom window must be an anchor's or a region's name or [x, y, z] in the hull's axes, got ${JSON.stringify(place)}`);
    if (!n || len(n) === 0) n = len([place[0], place[1], 0]) > 0 ? unit([place[0], place[1], 0]) : [1, 0, 0];
    const lift = num("scaleZoom lift", options.lift ?? 20, -80, 80) * RAD, dirOwn = unit(along(scale(unit(n), Math.cos(lift)), Math.abs(n[1]) > 0.9 ? [1, 0, 0] : [0, 1, 0], Math.sin(lift)));
    const whole = distanceFor(H.subject.radius, num("scaleZoom fill", options.fill ?? 0.7, 0.01, 2), c.fov);
    const stops = [{subject: {at: H.out(place), radius: 0, name: "the window"}, distance: num("scaleZoom close (m)", options.close ?? 60, 1e-3) * H.k},
      {subject: H.subject, distance: whole, hold: options.hold ?? 0}];
    if (options.world !== undefined && options.world !== null) stops.push({subject: options.world, distance: options.far ?? {radii: 4}});
    const {ship: _s, window: _w, close: _c, fill: _f, world: _o, far: _r, lift: _l, hold: _h, over, ...rest} = options;
    const shot = this.zoom(t, {...rest, ...(over ? {over: [this.seconds(over[0]), this.seconds(over[1])]} : {}), stops, direction: H.dir(dirOwn), up: H.dir([0, 1, 0])});
    return {...shot, move: "scaleZoom", notes: []};
  }

  // ----- the operator -----
  /** How bright the scene looks in `shot` (stops, meterStops): the vertical and the height at the camera, the
   * sun (the rig's sky's, else the rig's `sun`), the air's scale height, the water and the rig's cloud decks. */
  meter(shot, t = 0) {
    if (this.space) throw fail("meter is for scenes in the air (airCamera({camera, sky, ...})), not beside a ship in a SpaceView");
    const L = this.local, s = this.sky && this.sky.sun ? [this.sky.sun.x, this.sky.sun.y, this.sky.sun.z] : this.toSun(shot.from, t);
    const decks = this.clouds && Array.isArray(this.clouds.decks) ? this.clouds.decks : [];
    return meterStops(shot, {up: L.upAt(shot.from), height: L.heightOf(shot.from), sun: s, radius: L.radius, scale: this.sky && this.sky.model && this.sky.model.H ? this.sky.model.H : 8500,
      water: !!this.water, decks});
  }
  /** `operate(view, options, meter)` with this rig's meter: the view as a camera operator frames it (hand,
   * exposure, horizon). Give the shot's `ev` to the air (`air(..., {ev: () => shot.ev})`) for the exposure. */
  operator(view, options = {}) { return operate(view, options, (shot, t) => this.meter(shot, t)); }

  // ----- checks -----
  /** What is wrong with `shot` at t, as sentences: everything vidgen/space-camera's `problems` finds, the
   * shot's own notes (a camera lifted to keep its margin, a pass that reads as a model), and a camera under
   * the rig's `margin` over the ground or the water. */
  problems(t, shot, options = {}) {
    const out = [...(shot.notes ?? [])];
    if (this.ground || this.water) { const c = this.clearance(shot.from, t), m = shot.margin ?? this.margin; if (c < m - 1e-4) out.push(`the camera is ${c < 0 ? `${metres(-c)} under` : `only ${c.toFixed(1)} m over`} the ground or the water (the margin is ${m} m)`); }
    return [...out, ...super.problems(t, shot, options)];
  }
}

/** A camera rig for scenes in the air and beside giant ships: `airCamera({camera, sky, ground, water, clouds,
 * flight: ctx.flight, music: ctx.music})`, or `airCamera({space, camera, ships: {Ship: hull}})`. Every option
 * and move of `spaceCamera` works on it. */
export function airCamera(options = {}) { return new AirCamera(options); }
