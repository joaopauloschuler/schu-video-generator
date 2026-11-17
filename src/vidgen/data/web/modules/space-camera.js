// vidgen/space-camera: camera moves for space scenes (DESIGN.md §122.11). Part of schu-video-generator
// (MIT licence); imported by a page as "vidgen/space-camera", beside "vidgen/space-scale" (which places
// the camera in double precision) and "vidgen/three-finish" (motion blur, depth of field).
//
//   const cam = spaceCamera({space, camera});                          // or {camera, up: [0, 1, 0], sun: [1, 0.2, -1]}
//   const view = (t) => cam.arc(t, {subject: "Saturn", phase: "crescent", distance: {radii: 7}});
//   const update = (t) => { cam.apply(t, view(t)); saturn.update(t); sun.update(t); light.update(t); };
//
// Every move is a function of the time it is given (and of where its subjects are at that time): nothing
// is kept between frames, so scenes render in any order, a cut between two scenes on one clock shows
// one move, and three-finish's motion blur may call it at sub-frame times. A move returns a shot:
// {from, right, up, forward, fov, aspect, focus, ...}, plain float64 arrays in the frame of its
// subjects (the orbit data's with a SpaceView: z north; three.js's without one: y up). `cam.apply(t,
// shot)` hands it to `space.update` (the camera's place subtracted in double precision) or sets a
// plain three.js camera. Moves: flyBy, pass, arc, arrive, reveal, follow, zoom; helpers: look, lens,
// loomLens, problems, check, disc, matchDisc; cuts: flashCut, warpCut.
//
// Words: `progress` is 0..1 through a move; `over: [start, end]` gives it from the time (seconds; of
// `time` when given, e.g. song time, else of t), so a move sits on bar lines: over: [8 * bar, 12 * bar].
// A distance is metres from the subject's middle, {radii: k} or {altitude: metres}. `place` is where
// the subject sits in the frame: [x, y] from -1 to 1 (x right, y up; a third is 1/3), never the middle
// by default except in the zoom. Angles are degrees. No three.js import: the mathematics runs in Node.
import {clamp, mix, smoothstep, smootherstep, hash} from "vidgen/music-time";

export const VERSION = 1;
const PREFIX = "vidgen/space-camera";
const RAD = Math.PI / 180;

/** Lenses by name: the focal length (mm) on a 36 x 24 mm frame; the vertical field of view is 2 atan(12 / mm). */
export const LENSES = Object.freeze({"ultra-wide": 16, wide: 24, "wide-normal": 35, normal: 50, portrait: 85, long: 135, tele: 300, "long-tele": 600});
/** Phase angles (sun - subject - camera, degrees): 0 is the full face with the sun behind the camera, 180 the sun behind the subject. */
export const PHASES = Object.freeze({front: 0, full: 0, gibbous: 35, "three-quarter": 55, half: 90, crescent: 135, "thin-crescent": 158, backlit: 180});
/** Ready-made framings of a craft: where the camera stands in the craft's frame ([right, up, forward], times
 * `distance` craft radii), where the craft sits in the frame, and the lens. */
export const VIEWS = Object.freeze({
  chase: Object.freeze({direction: [0.34, 0.55, -1], distance: 3.2, place: [-0.16, -0.12], lens: "wide-normal", label: "behind and a little above, looking along the flight"}),
  lead: Object.freeze({direction: [-0.4, 0.5, 1], distance: 3.4, place: [0.2, -0.06], lens: "normal", label: "ahead of the craft, looking back at it"}),
  "three-quarter": Object.freeze({direction: [0.8, 0.34, 0.62], distance: 3.4, place: [-0.2, -0.06], lens: "normal", label: "close, from the front quarter"}),
  side: Object.freeze({direction: [1, 0.3, 0.06], distance: 6.5, place: [-0.22, 0.1], lens: "portrait", label: "in profile"}),
  shoulder: Object.freeze({direction: [0.3, 0.2, -1], distance: 4, place: [-0.3, -0.26], lens: "wide-normal", label: "over the craft's shoulder toward its target (needs target)"}),
  small: Object.freeze({direction: [0.3, 0.75, -1], distance: null, size: 0.06, place: [0.24, -0.2], lens: "normal", label: "the craft small against the world it flies over (from behind and above, looking down the flight)"}),
  horizon: Object.freeze({direction: null, distance: null, size: 0.3, place: [-0.24, -0.2], lens: "tele", label: "the world's limb looming behind the craft (a long lens along the horizon; needs a world)"}),
});
/** The sun's angular radius from 1 AU (degrees). */
export const SUN_RADIUS = 0.2665;
/** Under this share of a world's radius above its ground a sphere is no ground any more (Step 368: facets, no relief). */
export const GROUND_SHARE = 1e-3;
/** A subject under this radius (px) is "too small to see" for `problems` unless `minPixels` says otherwise. */
export const MIN_PIXELS = 3;

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
function hint(key, known) {
  const best = known.map((k) => [editDistance(String(key).toLowerCase(), k.toLowerCase()), k]).sort((x, y) => x[0] - y[0])[0];
  return best && best[0] <= Math.max(2, String(key).length / 3) ? ` (did you mean "${best[1]}"?)` : "";
}
function known(where, object, keys) {
  if (object === null || typeof object !== "object" || Array.isArray(object)) throw fail(`${where} must be an object, got ${JSON.stringify(object)}`);
  for (const k of Object.keys(object)) if (!keys.includes(k)) throw fail(`${where}: unknown option "${k}"${hint(k, keys)}; known: ${keys.join(", ")}`);
}
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));
const isPair = (v) => Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && Number.isFinite(x));
const num = (where, v, lo = -Infinity, hi = Infinity) => { if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) throw fail(`${where} must be a number${lo > -Infinity ? ` from ${lo}` : ""}${hi < Infinity ? ` to ${hi}` : ""}, got ${JSON.stringify(v)}`); return v; };

// ---------- vectors (float64 arrays) ----------
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const len = (a) => Math.hypot(a[0], a[1], a[2]);
export const unit = (a) => { const l = len(a); return l > 0 ? [a[0] / l, a[1] / l, a[2] / l] : [0, 0, 0]; };
const lerp = (a, b, u) => [mix(a[0], b[0], u), mix(a[1], b[1], u), mix(a[2], b[2], u)];
const along = (a, b, k) => [a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k];
/** `v` turned by `angle` (radians) about the unit vector `axis` (right-handed). */
export function turn(v, axis, angle) {
  const c = Math.cos(angle), s = Math.sin(angle), k = dot(axis, v) * (1 - c), x = cross(axis, v);
  return [v[0] * c + x[0] * s + axis[0] * k, v[1] * c + x[1] * s + axis[1] * k, v[2] * c + x[2] * s + axis[2] * k];
}
/** The part of `v` square to the unit vector `n`, as a unit vector; `other` (then any axis) when v is along n. */
export function square(v, n, other = null) {
  let p = along(v, n, -dot(v, n));
  if (len(p) < 1e-9 * Math.max(len(v), 1e-300) && other) p = along(other, n, -dot(other, n));
  if (len(p) < 1e-12) { const a = Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0]; p = along(a, n, -dot(a, n)); }
  return unit(p);
}
const angleBetween = (a, b) => Math.atan2(len(cross(a, b)), dot(a, b));
// a quaternion [x, y, z, w] from the columns of a rotation matrix
function quaternionOf(x, y, z) {
  const m00 = x[0], m10 = x[1], m20 = x[2], m01 = y[0], m11 = y[1], m21 = y[2], m02 = z[0], m12 = z[1], m22 = z[2], tr = m00 + m11 + m22;
  if (tr > 0) { const s = 0.5 / Math.sqrt(tr + 1); return [(m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s]; }
  if (m00 > m11 && m00 > m22) { const s = 2 * Math.sqrt(1 + m00 - m11 - m22); return [0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s]; }
  if (m11 > m22) { const s = 2 * Math.sqrt(1 + m11 - m00 - m22); return [(m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s]; }
  const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
  return [(m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s];
}
const rotate = (q, v) => { const u = [q[0], q[1], q[2]], t = scale(cross(u, v), 2); return add(add(v, scale(t, q[3])), cross(u, t)); };
function slerp(a, b, u) {
  let c = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  if (c < 0) { b = b.map((x) => -x); c = -c; }
  if (c > 0.999999) return a.map((x, i) => mix(x, b[i], u));
  const w = Math.acos(c), s = Math.sin(w), p = Math.sin((1 - u) * w) / s, q = Math.sin(u * w) / s;
  return a.map((x, i) => x * p + b[i] * q);
}

// ---------- time ----------
/** A move's speed curve: e(u) = u at `ease` 0 (a steady move, right for a cut into and out of motion),
 * the quintic ease at 1 (starts and ends at rest); between, a blend (the default 0.6 slows the ends
 * to 0.4 of the mean speed). */
export const eased = (u, ease = 0.6) => { u = clamp(u); return mix(u, smootherstep(u), clamp(ease)); };
/** Progress 0..1 of `time` through `over` = [start, end] (clamped): bar lines in, progress out. */
export function progressOf(time, over) {
  if (!isPair(over) || !(over[1] > over[0])) throw fail(`over must be [start, end] in seconds with end after start, got ${JSON.stringify(over)}`);
  return clamp((time - over[0]) / (over[1] - over[0]));
}

// ---------- lenses and sizes ----------
/** A lens: a name of LENSES, a focal length in mm, or {fov: degrees} / {mm}. Returns {mm, fov (vertical,
 * degrees), name}. A long lens does not bring things nearer, it narrows the view: from far away with a
 * long lens a craft keeps its size while the world behind it grows (see loomLens). */
export function lens(what = "normal") {
  if (typeof what === "string") { if (!(what in LENSES)) throw fail(`no lens "${what}"${hint(what, Object.keys(LENSES))}; lenses: ${Object.entries(LENSES).map(([k, v]) => `${k} (${v} mm)`).join(", ")}`); return {mm: LENSES[what], fov: 2 * Math.atan(12 / LENSES[what]) / RAD, name: what}; }
  if (typeof what === "number") { num("a lens in mm", what, 4, 5000); return {mm: what, fov: 2 * Math.atan(12 / what) / RAD, name: null}; }
  if (what && typeof what === "object") {
    known("lens", what, ["fov", "mm", "name"]);
    if (what.fov !== undefined) { num("lens.fov", what.fov, 0.1, 150); return {mm: 12 / Math.tan(what.fov * RAD / 2), fov: what.fov, name: what.name ?? null}; }
    if (what.mm !== undefined) return lens(what.mm);
  }
  throw fail(`a lens is a name (${Object.keys(LENSES).join(", ")}), millimetres or {fov: degrees}, got ${JSON.stringify(what)}`);
}
/** The share of the frame's height a ball of `radius` fills (its diameter over the frame's height) seen from
 * `distance` (to its middle) with vertical field of view `fov` degrees; Infinity from inside. */
export function frameShare(radius, distance, fov) { return distance > radius ? Math.tan(Math.asin(radius / distance)) / Math.tan(fov * RAD / 2) : Infinity; }
/** The distance (to its middle) from which a ball of `radius` fills `share` of the frame's height. */
export function distanceFor(radius, share, fov) { const a = Math.atan(share * Math.tan(fov * RAD / 2)); return radius / Math.sin(a); }
/** The classic long-lens shot: a craft (radius `craft` m) before a world (radius `world` m, its middle
 * `gap` m behind the craft, on the camera's line). Returns the lens and the camera's distance from the craft that
 * make the craft fill `craftShare` and the world `worldShare` of the frame's height: {fov, mm, distance,
 * wide: the world's share with a 24 mm lens at the same craft size}. The longer the lens, the farther back
 * the camera and the larger the world behind an unchanged craft. null when no lens does it (the world too
 * small or too near for that size). */
export function loomLens({craft, world, gap, craftShare = 0.15, worldShare = 1.5} = {}) {
  for (const [k, v] of Object.entries({craft, world, gap, craftShare, worldShare})) num(`loomLens ${k}`, v, 1e-12);
  // small angles: craft / d = craftShare T, world / (gap + d) = worldShare T (T = tan(fov / 2)); refined below
  let T = (world - worldShare * craft / craftShare) / (worldShare * gap);
  if (!(T > 0)) return null;
  for (let i = 0; i < 30; i++) {
    const d = craft / Math.sin(Math.atan(craftShare * T)), a = Math.asin(Math.min(1, world / (gap + d)));
    T = Math.tan(a) / worldShare;
  }
  const fov = 2 * Math.atan(T) / RAD;
  if (!(fov > 0.05 && fov < 150)) return null;
  const distance = distanceFor(craft, craftShare, fov), wideFov = lens("wide").fov;
  return {fov, mm: 12 / T, distance, wide: frameShare(world, gap + distanceFor(craft, craftShare, wideFov), wideFov)};
}

// ---------- a shot ----------
/** A shot: the camera at `eye` showing `target` at `place` in the frame ([x, y], -1..1; [0, 0] the middle),
 * the horizon level for `up` (the camera's right is square to it), then rolled by `roll` degrees
 * (clockwise picture). Returns {from, right, up, forward (unit vectors), fov, aspect, focus (the
 * target's distance along the view: three-finish's dof.focus), target, place}. Looking straight
 * along `up` there is no level: the camera's top then points along `ahead` (default any axis). */
export function shotAt(eye, target, {up = [0, 0, 1], fov = 27, aspect = 16 / 9, place = [0, 0], roll = 0, ahead = null} = {}) {
  const to = sub(target, eye), dist = len(to);
  if (!(dist > 0)) throw fail("the camera stands on what it looks at");
  const d = scale(to, 1 / dist), U = unit(up), eh = square(d, U, ahead), re = cross(eh, U);
  const tanY = Math.tan(fov * RAD / 2), a = place[0] * tanY * aspect, b = place[1] * tanY, n = Math.hypot(1, a, b);
  const theta = Math.asin(clamp(n * dot(d, U) / Math.hypot(1, b), -1, 1)) - Math.atan(b);
  const phi = Math.atan2(a, Math.max(1e-9, Math.cos(theta) - b * Math.sin(theta)));
  const h = along(scale(eh, Math.cos(phi)), re, -Math.sin(phi));
  let right = cross(h, U), forward = along(scale(h, Math.cos(theta)), U, Math.sin(theta)), top = along(scale(U, Math.cos(theta)), h, -Math.sin(theta));
  if (roll) { const r = roll * RAD, c = Math.cos(r), s = Math.sin(r); [right, top] = [along(scale(right, c), top, s), along(scale(top, c), right, -s)]; }
  return {from: eye.slice(), right, up: top, forward, fov, aspect, focus: Math.max(dist * dot(d, forward), 1e-6), target: target.slice(), place: place.slice()};
}
// a shot from a camera frame given outright
const shotOf = (eye, right, top, forward, fov, aspect, target, place) => ({from: eye.slice(), right, up: top, forward, fov, aspect,
  focus: Math.max(dot(sub(target, eye), forward), 1e-6), target: target.slice(), place});
/** The shot's turn as a quaternion [x, y, z, w]: "data" for `space.update`'s `quaternion` (the orbit
 * data's frame: the camera looks along its +y there, +z its top), "three" for a three.js camera
 * (looks along -z, +y its top). */
export function quaternionOfShot(shot, frame = "data") {
  return frame === "three" ? quaternionOf(shot.right, shot.up, scale(shot.forward, -1)) : quaternionOf(shot.right, shot.forward, shot.up);
}
const blendShots = (a, b, w) => {
  const q = slerp(quaternionOf(a.right, a.up, scale(a.forward, -1)), quaternionOf(b.right, b.up, scale(b.forward, -1)), w);
  return {right: rotate(q, [1, 0, 0]), up: rotate(q, [0, 1, 0]), forward: rotate(q, [0, 0, -1])};
};
/** Where `point` is in the shot's frame: {x, y (-1..1 inside the frame), depth (along the view; behind the
 * camera when not positive), inFrame}. */
export function screenOf(shot, point) {
  const v = sub(point, shot.from), z = dot(v, shot.forward), tanY = Math.tan(shot.fov * RAD / 2);
  const x = dot(v, shot.right) / (Math.abs(z) * tanY * shot.aspect || 1e-300), y = dot(v, shot.up) / (Math.abs(z) * tanY || 1e-300);
  return {x, y, depth: z, inFrame: z > 0 && Math.abs(x) <= 1 && Math.abs(y) <= 1};
}
/** A ball's disc in the shot's frame: {x, y (its middle, -1..1), radius (in half frame heights: 1 fills the
 * height), depth}; `discPixels(disc, height)` is its radius in pixels. Near the frame's edge a ball is
 * drawn a little larger than this (perspective): the match is exact in the middle. */
export function discOf(shot, at, radius) {
  const s = screenOf(shot, at), d = len(sub(at, shot.from));
  return {x: s.x, y: s.y, radius: d > radius ? Math.tan(Math.asin(radius / d)) / Math.tan(shot.fov * RAD / 2) : Infinity, depth: s.depth};
}
export const discPixels = (disc, height) => disc.radius * height / 2;

// ---------- the moves' own arithmetic (pure, tested in Node) ----------
/** How far along a fly-by's line the camera is at progress u, in closest distances (0 = the closest
 * pass): from -`before` to +`after`. `linger` 0 flies the line at an even speed (the bearing to the
 * subject then whips round at the pass); 1 turns the bearing at an even rate (the camera comes in fast,
 * slows as it passes and leaves fast); between, a blend. `ease` as `eased`. */
export function flyByTravel(u, {before = 6, after = 6, linger = 0.6, ease = 0.4} = {}) {
  const e = eased(u, ease);
  return mix(mix(-before, after, e), Math.tan(mix(Math.atan(-before), Math.atan(after), e)), clamp(linger));
}
/** The direction from a subject to a camera that sees it at phase angle `phase` (degrees; 0 the sun
 * behind the camera, 180 the sun behind the subject): `toSun` turned by `phase` toward the side
 * `around` (degrees round the sun's line: 0 leaves the sun on the camera's left with `up` up, 90 goes
 * over the top, 180 leaves the sun on the right). */
export function phaseDirection(toSun, phase, around = 0, up = [0, 0, 1]) {
  const s = unit(toSun), e1 = cross(square(up, s), s), e2 = cross(s, e1), a = phase * RAD, w = around * RAD;
  return unit(add(scale(s, Math.cos(a)), scale(add(scale(e1, Math.cos(w)), scale(e2, Math.sin(w))), Math.sin(a))));
}
/** The phase angle (degrees) at which a far sun stands `off` subject radii outside the limb of a ball seen
 * from `distance` (to its middle; radius `radius`): 180 - (1 + off) x the ball's angular radius. */
export const limbPhase = (radius, distance, off = 0.1) => 180 - (1 + off) * Math.asin(Math.min(1, radius / distance)) / RAD;
/** The angle (degrees) that `heights` scale heights of a world's air (each `height` radii: 0.0013 for the
 * Earth) take up at the limb of a world of `radius` seen from `distance`: what a sunrise's `air` wants. */
export const airMargin = (radius, distance, height = 0.0013, heights = 1) => Math.atan(heights * height * radius / Math.sqrt(Math.max(distance * distance - radius * radius, 1e-300))) / RAD;
/** A slow sway so a locked shot breathes, at time t: {yaw, pitch (degrees), push (a share of the distance)}
 * from sines of periods 13, 7.3, 17 and 23 s with phases from `seed`; `amount` 1 is +-2.4 degrees, +-1.5
 * degrees and +-4 %. A function of t alone. */
export function breathe(t, amount = 1, seed = 1) {
  const p = (k) => 2 * Math.PI * hash(seed, k), s = (period, k) => Math.sin(2 * Math.PI * t / period + p(k));
  return {yaw: amount * (1.8 * s(13, 1) + 0.6 * s(7.3, 2)), pitch: amount * 1.5 * s(17, 3), push: amount * 0.04 * s(23, 4)};
}
// the integral of a speed that rises 0 -> 1 as smoothstep over `ramp` at each wanted end and is 1 between: the
// distance covered at time x of a leg lasting `length` (so a leg covers length - ramp / 2 per eased end)
function rampTravel(x, length, ramp, easeIn, easeOut) {
  const rise = (y) => ramp * (y * y * y - 0.5 * y * y * y * y);   // the integral of smoothstep(0, 1, s) ds from 0 to y, times ramp
  x = clamp(x, 0, length);
  if (!(ramp > 0)) return x;
  const a = easeIn ? ramp : 0, b = easeOut ? ramp : 0, mid = length - a - b;
  let out = 0;
  if (easeIn) out += rise(Math.min(x, a) / ramp);
  out += clamp(x - a, 0, mid);
  if (easeOut && x > a + mid) out += ramp / 2 - rise((length - x) / ramp);
  return out;
}
/** The plan of a powers-of-ten zoom through `distances` (metres, each a landing point; rising to zoom
 * out, falling to zoom in): the distance is multiplied by `rate` every second (10 ** 0.5: a power of ten
 * every two seconds) on the way, rests `hold` seconds on every landing point between the first and the
 * last (a number, or one per landing point), and eases in and out of every rest and of both ends over
 * `ease` seconds (speed, in powers of ten a second, rises as a smoothstep). With `seconds` instead of
 * `rate`, the rate that makes the whole move last that long. Returns {legs: [{start, end, from, to,
 * easeIn, easeOut}], holds, rate, ease, seconds}. */
export function zoomPlan(distances, {rate = null, seconds = null, hold = 0, ease = 0.6} = {}) {
  if (!Array.isArray(distances) || distances.length < 2 || !distances.every((d) => typeof d === "number" && d > 0)) throw fail(`a zoom needs two or more distances in metres, got ${JSON.stringify(distances)}`);
  const n = distances.length, holds = distances.map((_, i) => (i === 0 || i === n - 1 ? 0 : Array.isArray(hold) ? (hold[i] ?? 0) : hold));
  const logs = distances.map(Math.log), legs = [];
  for (let i = 0; i < n - 1; i++) {
    if (logs[i + 1] === logs[i]) throw fail(`a zoom's landing points must differ in distance, got ${distances[i]} twice`);
    legs.push({from: logs[i], to: logs[i + 1], easeIn: i === 0 || holds[i] > 0, easeOut: i === n - 2 || holds[i + 1] > 0});
  }
  const ends = legs.reduce((s, l) => s + (l.easeIn ? 1 : 0) + (l.easeOut ? 1 : 0), 0), total = legs.reduce((s, l) => s + Math.abs(l.to - l.from), 0), rest = holds.reduce((s, h) => s + h, 0);
  let k;   // natural log of the distance per second
  if (seconds !== null) {
    if (!(seconds - rest - ends * ease / 2 > 0)) throw fail(`a zoom of ${seconds} s has no time left to move after its rests (${rest} s) and eases (${ends} x ${ease / 2} s)`);
    k = total / (seconds - rest - ends * ease / 2);
  } else { k = Math.log(rate ?? Math.sqrt(10)); if (!(k > 0)) throw fail(`a zoom's rate must be above 1 (the distance is multiplied by it every second), got ${rate}`); }
  let at = 0;
  for (let i = 0; i < legs.length; i++) {
    const l = legs[i];
    l.ramp = Math.min(ease, Math.abs(l.to - l.from) / k * 2 / Math.max(1, (l.easeIn ? 1 : 0) + (l.easeOut ? 1 : 0)));
    l.length = Math.abs(l.to - l.from) / k + ((l.easeIn ? 1 : 0) + (l.easeOut ? 1 : 0)) * l.ramp / 2;
    l.start = at; l.end = at + l.length; at = l.end + holds[i + 1];
  }
  return {legs, holds, rate: Math.exp(k), ease, seconds: at, distances: distances.slice()};
}
/** Where a zoom is `time` seconds into its plan: {distance (m), power (log10 of it), leg, share (0..1 of the
 * leg in distance, linear), resting (true on a landing point), speed (powers of ten a second)}. */
export function zoomAt(plan, time) {
  const k = Math.log(plan.rate), legs = plan.legs, T = clamp(time, 0, plan.seconds);
  let i = 0;
  while (i < legs.length - 1 && T >= legs[i + 1].start) i++;
  const l = legs[i], x = clamp(T - l.start, 0, l.length), sign = Math.sign(l.to - l.from);
  const done = x >= l.length ? Math.abs(l.to - l.from) : Math.min(Math.abs(l.to - l.from), k * rampTravel(x, l.length, l.ramp, l.easeIn, l.easeOut));
  const log = x >= l.length ? l.to : l.from + sign * done, distance = Math.exp(log), d0 = Math.exp(l.from), d1 = Math.exp(l.to);
  const h = 1e-4, v = x <= 0 || x >= l.length ? 0 : k * (rampTravel(x + h, l.length, l.ramp, l.easeIn, l.easeOut) - rampTravel(x - h, l.length, l.ramp, l.easeIn, l.easeOut)) / (2 * h);
  return {distance, power: log / Math.LN10, leg: i, share: clamp((distance - d0) / (d1 - d0)), resting: T > l.end || T <= 0 || T >= plan.seconds, speed: sign * v / Math.LN10};
}

// ---------- cuts ----------
/** A cut on a flash: the amount for three-finish's `flash` at `time`, for a cut at `cut`: it rises over `rise`
 * seconds before the cut to `amount` and falls over `fall` after it. Both scenes ask with their own
 * time and the same cut (a bar line), so the light is one curve across the cut. */
export function flashCut(time, cut, {amount = 3, rise = 0.25, fall = 0.6} = {}) {
  const d = time - cut;
  return amount * (d < 0 ? Math.pow(smoothstep(-rise, 0, d), 2) : 1 - smoothstep(0, fall, d));
}
/** A warp as a cut: the progress for vidgen/space-phenomena's `warpAt` / `warp.update` at `time`, for a
 * jump lasting `seconds` whose share `split` (default half: the middle of the tunnel) falls on the cut at
 * `cut`. The leaving scene shows progress up to `split`, the arriving scene the rest; both read one curve. */
export function warpCut(time, cut, {seconds = 3, split = 0.5} = {}) { return clamp(split + (time - cut) / seconds); }
/** A match cut on a disc: the distance and the place that show a ball of `radius` exactly as `disc` (a
 * discOf: the outgoing shot's planet, sun or porthole) with a lens of `fov` degrees: {distance, place}; give
 * both to the next shot's move. */
export function matchDisc(disc, radius, fov) {
  if (!(disc && disc.radius > 0 && Number.isFinite(disc.radius))) throw fail("matchDisc needs the disc of a ball the outgoing camera is outside of (discOf)");
  return {distance: distanceFor(radius, disc.radius, fov), place: [disc.x, disc.y]};
}

// ---------- the rig ----------
const RIG_KEYS = ["space", "camera", "up", "sun", "sunRadius", "lens", "aspect", "height", "bodies"];
const COMMON = ["progress", "over", "time", "lens", "place", "roll", "up", "level", "ease"];
const three = (v) => [v.x, v.y, v.z];

export class SpaceCamera {
  /** `space`: a SpaceView of vidgen/space-scale (subjects are then names of the orbit data, the frame is the
   * data's, `up` defaults to its north [0, 0, 1], the Sun and the worlds to avoid are the data's); without
   * it the frame is three.js's (`up` [0, 1, 0]) and subjects are objects, points or {at, radius}. `camera`:
   * the page's PerspectiveCamera (its aspect; `apply` sets it). `sun`: towards the sun as [x, y, z], a
   * subject standing where it is, or a star of vidgen/space-light. `sunRadius`: its angular radius
   * (degrees) for a sun given as a direction. `lens`: the default lens. `bodies`: the worlds a camera must
   * not fly through, for scenes without orbit data (subjects with a radius). `height`: the frame's
   * height in pixels (for sizes in pixels). */
  constructor(options = {}) {
    known("spaceCamera options", options, RIG_KEYS);
    this.space = options.space ?? null;
    this.camera = options.camera ?? (this.space ? this.space.camera : null);
    this.up = unit(options.up ?? (this.space ? [0, 0, 1] : [0, 1, 0]));
    if (!isVec(this.up) || len(this.up) === 0) throw fail(`up must be [x, y, z], got ${JSON.stringify(options.up)}`);
    this.sun = options.sun ?? null;
    this.sunRadius = num("sunRadius", options.sunRadius ?? SUN_RADIUS, 0, 45);
    this.lens = lens(options.lens ?? "normal");
    this.aspect = options.aspect ?? (this.camera && this.camera.aspect) ?? 16 / 9;
    this.height = options.height ?? (this.space ? this.space.renderer.domElement.height : null) ?? 720;
    this.bodies = options.bodies ?? [];
    /** The last shot `apply` placed. */
    this.shot = null;
  }

  // ----- subjects -----
  /** What a move looks at or flies round, at time t: {at: [x, y, z], radius, name, velocity(): per second of
   * t}. `what`: a body's name (with a SpaceView), [x, y, z], {at, radius, name} (`at` a point or a function
   * of t), {body, offset, radius}, a world, star or craft of the space modules (placed by `space`, or
   * standing in a plain scene as a top-level object), a three.js Object3D, or a function of t giving
   * any of these. */
  subject(what, t = 0, where = "subject") {
    if (typeof what === "function") what = what(t);
    // the velocity: from the places a moment before and after; on the frames a scene holds after its data's end
    // (nothing moves there) the data's own velocity, so a camera locked to the flight keeps its frame
    const out = (at, radius, name, again, body = null) => ({at, radius: radius || 0, name: name ?? null,
      velocity: () => {
        const h = 1 / 240, v = scale(sub(again(t + h), again(t - h)), 1 / (2 * h)), o = body && this.space.orbits;
        return len(v) > 0 || !o || typeof o.velocity !== "function" ? v : scale(o.velocity(body, t), o.speedup ?? 1);
      }});
    if (typeof what === "string") {
      if (!this.space) throw fail(`${where} "${what}": a name needs a SpaceView (spaceCamera({space})); without one give an object, a point or {at, radius}`);
      return out(this.space.at(what, t), this.space.radius(what), what, (x) => this.space.at(what, x), what);
    }
    if (isVec(what)) return out(what.slice(), 0, null, () => what);
    if (what && typeof what === "object") {
      const flown = what.flight && typeof what.flight.body === "string" ? what.flight.body : null, named = flown ?? (typeof what.body === "string" ? what.body : null);
      if (named !== null && this.space) {
        const off = isVec(what.offset) ? what.offset : [0, 0, 0], r = what.radius ?? (what.size && what.size.radius) ?? this.space.radius(named);
        return out(add(this.space.at(named, t), off), r, what.name ?? named, (x) => add(this.space.at(named, x), off), named);
      }
      if (what.at !== undefined) { const at = (x) => (typeof what.at === "function" ? what.at(x) : what.at); if (!isVec(at(t))) throw fail(`${where}.at must be [x, y, z] or a function of t giving it`); return out(at(t).slice(), what.radius, what.name, at); }
      const o = what.isObject3D ? what : what.object && what.object.isObject3D ? what.object : null;
      if (o) {
        if (this.space) throw fail(`${where}: with a SpaceView an object's place is the camera's own; name its body ("Earth", {body: "Ship"}) or give {at, radius}`);
        const r = what.radius ?? (what.size && what.size.radius) ?? (what.isObject3D ? (what.userData && what.userData.radius) ?? 0 : o.scale.x);
        return out(three(o.position), r, what.name ?? o.name ?? null, () => three(o.position));
      }
    }
    throw fail(`${where} must be a body's name, [x, y, z], {at, radius}, {body, offset}, a world / star / craft or an Object3D, got ${JSON.stringify(what)}`);
  }

  /** Towards the sun from `from` at t (a unit vector), or null when the rig knows no sun: the `sun` option, else the data's "Sun". */
  toSun(from, t = 0, sun = this.sun) {
    let s = sun;
    if (s === null && this.space && this.space.orbits && this.space.orbits.names.includes("Sun")) s = "Sun";
    if (s === null) return null;
    if (isVec(s)) return unit(s);
    if (s.isVector3) return unit(this.space ? [s.x, -s.z, s.y] : three(s));
    if (s.infinite && s.direction && s.direction.isVector3) return unit(this.space ? [s.direction.x, -s.direction.z, s.direction.y] : three(s.direction));
    const p = this.subject(s, t, "sun").at, d = sub(p, from);
    return len(d) > 0 ? unit(d) : null;
  }
  _sun(from, t, sun, who) {
    const s = this.toSun(from, t, sun ?? this.sun);
    if (!s) throw fail(`${who} needs to know where the sun is: spaceCamera({sun: [x, y, z] towards it, a star or a subject}), or orbit data with a "Sun"`);
    return s;
  }
  // the worlds a camera must not fly through at t: [{name, at, radius}]
  _worlds(t) {
    const out = [];
    if (this.space && this.space.orbits) for (const n of this.space.orbits.names) { const r = this.space.radius(n); if (r > 0) out.push({name: n, at: this.space.at(n, t), radius: r}); }
    for (const b of this.bodies) { const s = this.subject(b, t, "bodies[]"); if (s.radius > 0) out.push({name: s.name ?? "a world", at: s.at, radius: s.radius}); }
    return out;
  }
  // the world of the orbit data a named subject goes round, when it is within three of that world's radii
  // (there the horizon is that world's): a subject, or null
  _near(s, t) {
    const o = this.space && this.space.orbits, name = o && s.name && o.names.includes(s.name) ? s.name : null, parent = name ? o.bodies[name].parent ?? null : null;
    if (!parent || !o.names.includes(parent)) return null;
    const w = this.subject(parent, t, "the parent");
    return w.radius > 0 && len(sub(s.at, w.at)) < 3 * w.radius ? w : null;
  }
  // options shared by the moves
  _common(t, o, who) {
    const time = o.time ?? t, u = o.progress !== undefined ? clamp(num(`${who} progress`, o.progress)) : o.over !== undefined ? progressOf(time, o.over) : null;
    const l = o.lens !== undefined ? lens(o.lens) : null;
    return {time, u, lens: l, fov: (l ?? this.lens).fov, aspect: this.aspect, roll: o.roll ?? 0};
  }
  _distance(what, radius, where, fallback) {
    if (what === undefined || what === null) what = fallback;
    if (typeof what === "number") return num(where, what, 1e-9);
    if (what && typeof what === "object") {
      known(where, what, ["radii", "altitude", "share", "pixels"]);
      if (what.radii !== undefined) { if (!(radius > 0)) throw fail(`${where}: {radii} needs a subject with a radius`); return num(`${where}.radii`, what.radii, 1e-9) * radius; }
      if (what.altitude !== undefined) return radius + num(`${where}.altitude`, what.altitude, 1e-9);
    }
    throw fail(`${where} must be metres from the subject's middle, {radii: k} or {altitude: metres}, got ${JSON.stringify(what)}`);
  }
  // `up` of a move: a vector, or {body}: level with that world's horizon (up is away from its middle)
  _up(o, eye, t) {
    if (o.level !== undefined) { const b = this.subject(o.level, t, "level"), r = sub(eye, b.at); if (len(r) > 0) return unit(r); }
    return o.up ? unit(o.up) : this.up;
  }
  // a place given as [x, y] or as two of them (glided through with progress)
  _place(place, u, fallback) {
    const p = place ?? fallback;
    if (isPair(p)) return p;
    if (Array.isArray(p) && p.length === 2 && isPair(p[0]) && isPair(p[1])) { const w = smootherstep(u ?? 0); return [mix(p[0][0], p[1][0], w), mix(p[0][1], p[1][1], w)]; }
    throw fail(`place must be [x, y] (-1..1, the frame's middle 0) or [[x, y], [x, y]] (from, to), got ${JSON.stringify(place)}`);
  }

  // ----- helpers -----
  /** Look from `from` at `to` (subjects) with a composed frame: `place` [x, y] puts the subject there
   * (default the left upper third's crossing, [-1/3, 1/6]); `level: body` levels that world's horizon
   * instead of `up`; `lens`, `roll`. The plainest shot, and what the moves are made of. */
  look(t, options = {}) {
    known("look options", options, ["from", "to", "place", "lens", "roll", "up", "level", "time"]);
    const c = this._common(t, options, "look"), eye = this.subject(options.from, t, "look.from").at, to = this.subject(options.to, t, "look.to");
    const shot = shotAt(eye, to.at, {up: this._up(options, eye, t), fov: c.fov, aspect: c.aspect, place: this._place(options.place, 0, [-1 / 3, 1 / 6]), roll: c.roll});
    return {...shot, move: "look", subject: to};
  }

  /** A fly-by of a subject: the camera flies a straight line past it (in the subject's own frame, so a
   * moving craft is passed as it flies), comes within `closest` of its middle (default {radii: 3}) on the
   * side `side`, and turns to keep it in the frame. `side`: where the subject passes: "left", "right",
   * "above", "below" of the camera, "sunlit" / "dark" (the camera passes over the subject's day or night
   * side), or a vector from the subject to the camera at the pass. `along`: the camera's direction of
   * flight: a vector, "prograde" / "retrograde" (along or against the subject's velocity), "sunward" /
   * "antisun"; default against the velocity when the subject moves, else across the sun's line.
   * `before`, `after`: where the line starts and ends, in closest distances (6, 6); `linger` (0.6) and
   * `ease` (0.4) as flyByTravel; `place`: [x, y] or [[x, y], [x, y]]: the subject glides from the first
   * to the second through the pass (default from the side it comes from to the third it leaves by);
   * `roll`: a bank (degrees) that peaks at the pass; the horizon is level for `up`, for `level: body`, or for
   * the world the subject flies over: `around`, or by itself the parent of a subject of the orbit data
   * within three of its radii (above and below are then away from and toward that world); `track`: false keeps the camera's turn fixed as it
   * was at progress `lockAt` (0.3): the subject flies through a locked-off frame. */
  flyBy(t, options = {}) {
    known("flyBy options", options, [...COMMON, "subject", "closest", "side", "along", "before", "after", "linger", "track", "lockAt", "sun", "around"]);
    const c = this._common(t, options, "flyBy"), s = this.subject(options.subject, t, "flyBy.subject");
    if (c.u === null) throw fail("flyBy needs progress (0..1) or over: [start, end]");
    const closest = this._distance(options.closest, s.radius, "flyBy.closest", s.radius > 0 ? {radii: 3} : undefined);
    const v = s.velocity(), moving = len(v) > 1e-9 * Math.max(1, closest), sun = this.toSun(s.at, t, options.sun ?? this.sun);
    let a = options.along ?? (moving ? "retrograde" : null);
    const needSun = (w) => { if (!sun) throw fail(`flyBy ${w} needs to know where the sun is (spaceCamera({sun}))`); return sun; };
    if (a === "prograde" || a === "retrograde") { if (!moving) throw fail(`flyBy along: "${a}" needs a subject that moves`); a = scale(unit(v), a === "prograde" ? 1 : -1); }
    else if (a === "sunward") a = needSun("along: \"sunward\"");
    else if (a === "antisun") a = scale(needSun("along: \"antisun\""), -1);
    else if (a === null) a = sun ? cross(square(this.up, sun), sun) : square([1, 0, 0], this.up);
    else if (!isVec(a)) throw fail(`flyBy along must be a vector, "prograde", "retrograde", "sunward" or "antisun", got ${JSON.stringify(a)}`);
    a = unit(a);
    const world = options.up || options.level !== undefined ? null : options.around !== undefined && options.around !== null ? this.subject(options.around, t, "flyBy.around") : this._near(s, t), upAt = (eye) => (world ? unit(sub(eye, world.at)) : this._up(options, eye, t));
    const U = square(world ? sub(s.at, world.at) : this.up, a, this.up), R = cross(a, U), side = options.side ?? "left";
    const sides = {left: R, right: scale(R, -1), above: scale(U, -1), below: U};
    let b;
    if (isVec(side)) b = square(side, a);
    else if (side in sides) b = sides[side];
    else if (side === "sunlit" || side === "dark") b = scale(square(needSun(`side: "${side}"`), a, U), side === "sunlit" ? 1 : -1);
    else throw fail(`flyBy side must be "left", "right", "above", "below", "sunlit", "dark" or a vector, got ${JSON.stringify(side)}${hint(side, [...Object.keys(sides), "sunlit", "dark"])}`);
    const travel = (u) => flyByTravel(u, {before: options.before ?? 6, after: options.after ?? 6, linger: options.linger ?? 0.6, ease: options.ease ?? 0.4});
    const eyeAt = (u) => add(s.at, add(scale(b, closest), scale(a, travel(u) * closest)));
    const eye = eyeAt(c.u), sx = Math.sign(dot(b, R)) || 0;   // +1: the subject passes on the left
    const place = this._place(options.place, c.u, [[0.3 * sx, -0.08], [-0.36 * sx || -1 / 3, 0.1]]);
    const bank = c.roll * Math.pow(Math.sin(Math.PI * c.u), 2);
    let shot = shotAt(eye, s.at, {up: upAt(eye), fov: c.fov, aspect: c.aspect, place, roll: bank, ahead: a});
    if (options.track === false) {
      const u0 = options.lockAt ?? 0.3, e0 = eyeAt(u0), fixed = shotAt(e0, s.at, {up: upAt(e0), fov: c.fov, aspect: c.aspect, place: this._place(options.place, u0, [0.3 * sx, -0.1]), roll: c.roll, ahead: a});
      shot = shotOf(eye, fixed.right, fixed.up, fixed.forward, c.fov, c.aspect, s.at, null);
    }
    return {...shot, move: "flyBy", subject: s, progress: c.u, distance: len(sub(eye, s.at)), closest, travel: travel(c.u)};
  }

  /** The craft passes the camera: a fly-by in the craft's own frame, the camera ahead of it beside its
   * path; the craft comes up, passes within `closest` (default {radii: 2.5}) and flies on. Defaults: an
   * ultra-wide lens (it holds the world's limb under the craft and stretches the pass), the craft in the
   * upper part of the frame, `linger` 0.5, `before` 10 and `after` 7 closest distances.
   * `track: false` locks the frame so the craft flies through it. Every flyBy option applies. */
  pass(t, options = {}) {
    const s = this.subject(options.subject, t, "pass.subject");
    const side = options.side ?? "left", sx = side === "left" ? 1 : side === "right" ? -1 : 0;
    return {...this.flyBy(t, {along: "retrograde", closest: s.radius > 0 ? {radii: 2.5} : undefined, before: 10, after: 7, linger: 0.5, ease: 0.2, lens: "ultra-wide", side,
      ...(sx ? {place: [[0.24 * sx, 0.22], [-0.4 * sx, 0.26]]} : {}), ...options}), move: "pass"};
  }

  /** An arc round a subject with the sun where you want it. `phase`: a name of PHASES ("front",
   * "three-quarter", "half", "crescent", "thin-crescent", "backlit"), degrees, or {limb: k}: the sun k
   * subject radii off the limb (0.1: just off it); a pair [from, to] moves through the move. `around`
   * (degrees, or a pair): which way round the sun's line the camera stands (0 the sun to the left, 90 the
   * camera over the top, 180 the sun to the right). `distance` (or a pair; default {radii: 5}); `place`
   * (default: the subject on the third away from the sun, so the light has room). Without progress it is
   * one held frame: "show me this planet as a crescent" is arc(t, {subject, phase: "crescent"}). */
  arc(t, options = {}) {
    known("arc options", options, [...COMMON, "subject", "phase", "around", "distance", "sun"]);
    const c = this._common(t, options, "arc"), s = this.subject(options.subject, t, "arc.subject"), sun = this._sun(s.at, t, options.sun, "arc");
    const e = eased(c.u ?? 0, options.ease ?? 0.6), pair = (v, f) => (Array.isArray(v) ? [f(v[0]), f(v[1])] : [f(v), f(v)]);
    const d = pair(options.distance ?? null, (x) => this._distance(x, s.radius, "arc.distance", s.radius > 0 ? {radii: 5} : undefined)), dist = Math.exp(mix(Math.log(d[0]), Math.log(d[1]), e));
    const ph = pair(options.phase ?? "three-quarter", (x) => this._phase(x, s.radius, dist)), w = pair(options.around ?? 0, (x) => num("arc.around", x));
    const phase = mix(ph[0], ph[1], e), around = mix(w[0], w[1], e), eye = add(s.at, scale(phaseDirection(sun, phase, around, this.up), dist)), up = this._up(options, eye, t);
    let place = options.place;
    if (place === undefined) {   // the subject on the third away from the sun's side of the frame
      const f0 = shotAt(eye, s.at, {up, fov: c.fov, aspect: c.aspect}), x = dot(sun, f0.right), y = dot(sun, f0.up), l = Math.hypot(x, y);
      place = l > 1e-3 ? [-0.34 * x / l, -0.2 * y / l] : [-1 / 3, 0];
    }
    const shot = shotAt(eye, s.at, {up, fov: c.fov, aspect: c.aspect, place: this._place(place, c.u), roll: c.roll, ahead: sun});
    return {...shot, move: "arc", subject: s, progress: c.u, distance: dist, phase, around};
  }
  _phase(what, radius, distance) {
    if (typeof what === "string") { if (!(what in PHASES)) throw fail(`no phase "${what}"${hint(what, Object.keys(PHASES))}; phases: ${Object.entries(PHASES).map(([k, v]) => `${k} (${v})`).join(", ")}, degrees, or {limb: k}`); return PHASES[what]; }
    if (typeof what === "number") return num("phase", what, 0, 180);
    if (what && typeof what === "object" && what.limb !== undefined) { if (!(radius > 0)) throw fail("phase {limb} needs a subject with a radius"); return limbPhase(radius, distance, num("phase.limb", what.limb, -1, 50)); }
    throw fail(`phase must be a name (${Object.keys(PHASES).join(", ")}), degrees or {limb: k}, got ${JSON.stringify(what)}`);
  }

  /** An arrival: from far out, the world small and off the middle, sweeping in round it to a low orbit's
   * view: the limb across the bottom of the frame, the horizon level, the camera looking along its
   * flight. `from` (default {radii: 14}) and `altitude` (above the ground at the end; default 0.07
   * radii, 446 km over the Earth): the height above the ground falls by a constant factor per unit of
   * eased progress. `sweep` (110): degrees flown round the world. `plane`: the orbit's normal (default
   * `up`: the camera flies toward the east of a world whose north is up). `sunAhead` (140: the day side, the sun behind the camera; 9 arrives at a sunrise): the sun's height
   * (degrees) over the limb ahead of the camera at the end (negative: behind the world, arriving in its
   * shadow toward the dawn; 180 - x puts it behind the camera). Give a wide lens to hold limb and sun. `horizon` (-0.42): where the limb
   * crosses the frame's middle column at the end (y, -1..1). `place`: the world at the start
   * ([0.3, 0.12]). `tilt` ([0.3, 0.92]): the progress over which the camera tilts from the world's middle
   * up to the horizon. */
  arrive(t, options = {}) {
    known("arrive options", options, [...COMMON, "subject", "from", "altitude", "sweep", "plane", "sunAhead", "horizon", "tilt", "sun"]);
    const c = this._common(t, options, "arrive"), s = this.subject(options.subject, t, "arrive.subject");
    if (c.u === null) throw fail("arrive needs progress (0..1) or over: [start, end]");
    if (!(s.radius > 0)) throw fail("arrive needs a subject with a radius (a world)");
    const R = s.radius, far = this._distance(options.from, R, "arrive.from", {radii: 14}), low = R + num("arrive.altitude", options.altitude ?? 0.07 * R, 1e-9);
    if (!(far > low)) throw fail(`arrive: from (${far} m) must be farther than the low orbit (${low} m)`);
    const n = unit(options.plane ?? this.up), sun = this.toSun(s.at, t, options.sun ?? this.sun), x = square(sun ?? [1, 0, 0], n), y = cross(n, x);
    const e = eased(c.u, options.ease ?? 0.6), sweep = num("arrive.sweep", options.sweep ?? 110), end = -(90 - (num("arrive.sunAhead", options.sunAhead ?? 140) - Math.acos(R / low) / RAD)) * RAD;
    const phi = end - sweep * RAD * (1 - e), r = R + Math.exp(mix(Math.log(far - R), Math.log(low - R), e));
    const rho = add(scale(x, Math.cos(phi)), scale(y, Math.sin(phi))), tau = add(scale(x, -Math.sin(phi)), scale(y, Math.cos(phi))), eye = add(s.at, scale(rho, r));
    // A: the whole world, composed; B: along the flight, the limb at `horizon`, level (the camera's right is the orbit's axis)
    const tanY = Math.tan(c.fov * RAD / 2), beta = Math.asin(R / r), gamma = beta + Math.atan(-(options.horizon ?? -0.42) * tanY);
    const A = shotAt(eye, s.at, {up: tau, fov: c.fov, aspect: c.aspect, place: this._place(options.place, c.u, [0.3, 0.12])});
    const fB = add(scale(rho, -Math.cos(gamma)), scale(tau, Math.sin(gamma))), uB = add(scale(rho, Math.sin(gamma)), scale(tau, Math.cos(gamma))), B = {right: scale(n, -1), up: uB, forward: fB};
    const tilt = options.tilt ?? [0.3, 0.92], w = smootherstep((c.u - tilt[0]) / (tilt[1] - tilt[0])), m = blendShots(A, B, w);
    const horizonPoint = add(eye, scale(add(scale(rho, -Math.cos(beta)), scale(tau, Math.sin(beta))), r * Math.cos(beta)));
    const shot = shotOf(eye, m.right, m.up, m.forward, c.fov, c.aspect, w < 0.5 ? s.at : horizonPoint, null);
    return {...shot, move: "arrive", subject: w < 0.9 ? s : {at: horizonPoint, radius: 0, name: "the horizon"}, world: s, progress: c.u, distance: r, altitude: r - R, tilt: w};
  }

  /** A reveal from behind a limb: the camera rides round the world `behind` so that `of` (default the
   * sun) comes out from behind its edge, and its first light shows exactly at `at` (seconds of `time`,
   * default of t: a bar line). `rate`: degrees a second the camera goes round the world (default 1; a real
   * low orbit does 0.07). `distance` of the camera from the world (default {altitude: 0.07 radii}: a low
   * orbit; from far away the world is a disc and a moon or a ringed planet rises over its edge). `plane`:
   * the ride's axis (default `up`). `horizon` (-0.4): where the limb crosses the frame; `place` x: where
   * along it the light appears (default 0.18). `margin`: degrees of the subject's own radius counted
   * (default: the sun's, or the subject's radius seen from the camera; 0 times the moment its middle
   * clears the limb). The shot adds {elevation (degrees of the subject's middle over the limb; negative:
   * hidden), seen (0..1 of its disc clear of the limb, by height), first: `at`}. `air` (degrees, 0): how far
   * over the hard limb the light must be to show: a world's air holds grazing light back (airMargin
   * gives the angle of its scale heights; measured on the Earth-like world from a 446 km orbit: the glare's
   * first 0.1 % at 0.1, 2 % at 0.25). */
  reveal(t, options = {}) {
    known("reveal options", options, ["time", "lens", "roll", "behind", "of", "at", "rate", "distance", "plane", "horizon", "place", "margin", "air", "sun", "follow"]);
    const c = this._common(t, options, "reveal"), b = this.subject(options.behind, t, "reveal.behind");
    if (!(b.radius > 0)) throw fail("reveal needs behind: a world with a radius");
    const R = b.radius, r = this._distance(options.distance, R, "reveal.distance", {altitude: 0.07 * R});
    if (!(r > R)) throw fail("reveal: the camera must be outside the world it looks over");
    const rate = num("reveal.rate", options.rate ?? 1) * RAD, first = num("reveal.at", options.at ?? 0), beta = Math.asin(R / r) + num("reveal.air", options.air ?? 0, 0, 10) * RAD;
    if (rate === 0) throw fail("reveal needs a rate other than 0 (degrees a second round the world)");
    // where the subject is: far away in a direction (the sun), or a point with a radius
    const of = options.of ?? null, far = of === null;
    let dirAt, sigmaAt, target = null;
    if (far) { const s = this._sun(b.at, t, options.sun, "reveal"); dirAt = () => s; sigmaAt = () => (options.margin ?? this.sunRadius) * RAD; }
    else {
      target = this.subject(of, t, "reveal.of");
      // its place at the moment of the first light fixes the camera's ride; at t the picture uses where it is now
      dirAt = (eye, now) => unit(sub(now ? target.at : this.subject(of, t + (first - c.time), "reveal.of").at, eye));
      sigmaAt = (eye) => (options.margin !== undefined ? options.margin * RAD : Math.asin(Math.min(1, target.radius / Math.max(len(sub(target.at, eye)), 1e-300))));
    }
    const bAt = far ? b.at : this.subject(options.behind, t + (first - c.time), "reveal.behind").at;
    const s0 = far ? dirAt() : unit(sub(this.subject(of, t + (first - c.time), "reveal.of").at, bAt));
    const n = unit(options.plane ?? this.up), e = cross(square(n, s0), s0);          // the ride's plane holds the subject's direction; e is where the camera goes
    const rhoAt = (theta) => add(scale(s0, -Math.cos(theta)), scale(e, Math.sin(theta)));
    const clear = (theta) => { const eye = add(bAt, scale(rhoAt(theta), r)); return angleBetween(scale(rhoAt(theta), -1), dirAt(eye, false)) - beta + sigmaAt(eye); };
    let theta0 = beta - (far ? sigmaAt() : 0);
    if (!far) { let lo = 0, hi = Math.PI; for (let i = 0; i < 60; i++) { const m = 0.5 * (lo + hi); if (clear(m) < 0) lo = m; else hi = m; } theta0 = 0.5 * (lo + hi); }
    const theta = theta0 + rate * (c.time - first), rho = rhoAt(theta), eye = add(b.at, scale(rho, r)), d = dirAt(eye, true);
    const elevation = angleBetween(scale(rho, -1), d) - beta, sigma = sigmaAt(eye);
    // the frame: level with the world, the limb point under the subject at `horizon`, the subject's column at `place` x
    const tHat = square(d, rho, e), tanY = Math.tan(c.fov * RAD / 2), hz = options.horizon ?? -0.4, px = isPair(options.place) ? options.place[0] : (options.place ?? 0.18);
    const follow = clamp(options.follow ?? 0) * Math.max(0, elevation);
    const pitch = beta + Math.atan(-hz * tanY) + follow, f0 = add(scale(rho, -Math.cos(pitch)), scale(tHat, Math.sin(pitch))), u0 = add(scale(rho, Math.sin(pitch)), scale(tHat, Math.cos(pitch)));
    const yaw = -Math.atan(px * tanY * c.aspect), right0 = cross(f0, u0), forward = turn(f0, u0, -yaw), right = turn(right0, u0, -yaw);
    const limb = add(eye, scale(add(scale(rho, -Math.cos(beta)), scale(tHat, Math.sin(beta))), r * Math.cos(beta)));
    let top = u0, rt = right;
    if (c.roll) { const q = c.roll * RAD; rt = add(scale(right, Math.cos(q)), scale(u0, Math.sin(q))); top = add(scale(u0, Math.cos(q)), scale(right, -Math.sin(q))); }
    const shot = shotOf(eye, rt, top, forward, c.fov, c.aspect, limb, [px, hz]);
    return {...shot, move: "reveal", subject: target ?? {at: add(eye, scale(d, 1e15)), radius: 0, name: "the sun"}, behind: b, elevation: elevation / RAD,
      seen: sigma > 0 ? clamp((elevation + sigma) / (2 * sigma)) : elevation >= 0 ? 1 : 0, first, distance: r, angle: theta / RAD};
  }

  /** Follow a craft (or any moving subject): the camera stands in the craft's frame and goes with it.
   * `view`: a name of VIEWS ("chase", "lead", "three-quarter", "side", "shoulder", "small", "horizon")
   * or {direction: [right, up, forward], distance, place, lens, size}. `lock`: "velocity" (default:
   * forward is the flight's direction, up is away from the world it goes round), "craft" (the craft's
   * own axes: its nose forward; needs the craft's object) or "stars" (the rig's axes: the craft turns
   * and flies under a camera that does not). `distance`: metres, {radii} of the craft, or {share}: the
   * craft's share of the frame's height. `around`: the world the flight goes round (default the data's
   * parent). `target`: what an over-the-shoulder view looks toward. `drift` (1): how much the shot
   * breathes (breathe: a slow sway of a few degrees and per cent; 0 for a locked shot); `seed`. `push`:
   * the distance at the end of `over` as a share of the start's (0.7 closes in by 30 %). */
  follow(t, options = {}) {
    known("follow options", options, [...COMMON, "subject", "view", "lock", "distance", "around", "target", "drift", "seed", "push", "direction", "size"]);
    const c = this._common(t, options, "follow"), s = this.subject(options.subject, t, "follow.subject");
    let view = options.view ?? "chase";
    if (typeof view === "string") { if (!(view in VIEWS)) throw fail(`no view "${view}"${hint(view, Object.keys(VIEWS))}; views: ${Object.keys(VIEWS).join(", ")}`); view = {...VIEWS[view], name: view}; }
    else { known("follow view", view, ["direction", "distance", "place", "lens", "size", "name", "label"]); view = {distance: 5, place: [-0.2, -0.15], lens: "normal", ...view}; }
    if (options.direction) view.direction = options.direction;
    const l = c.lens ?? lens(view.lens), fov = l.fov, rc = s.radius > 0 ? s.radius : 1;
    // the craft's frame
    const lock = options.lock ?? "velocity", name = s.name && this.space && this.space.orbits && this.space.orbits.names.includes(s.name) ? s.name : null;
    const parentName = options.around === undefined && name ? this.space.orbits.bodies[name].parent ?? null : null;
    const world = options.around !== undefined && options.around !== null ? this.subject(options.around, t, "follow.around") : parentName ? this.subject(parentName, t, "follow.around") : null;
    const away = world ? unit(sub(s.at, world.at)) : this.up;
    let f, u;
    if (lock === "velocity") {
      const v = world ? sub(s.velocity(), world.velocity()) : s.velocity();
      if (!(len(v) > 0)) throw fail('follow lock: "velocity" needs a subject that moves; give lock: "stars" or "craft"');
      f = unit(v); u = square(away, f, this.up);
    } else if (lock === "craft") {
      const o = options.subject && (options.subject.isObject3D ? options.subject : options.subject.object);
      if (!o || !o.quaternion) throw fail('follow lock: "craft" needs the craft itself as the subject (its object\'s turn)');
      const q = [o.quaternion.x, o.quaternion.y, o.quaternion.z, o.quaternion.w], conv = (p) => (this.space ? [p[0], -p[2], p[1]] : p);
      f = conv(rotate(q, [0, 0, 1])); u = conv(rotate(q, [0, 1, 0]));
    } else if (lock === "stars") { u = this.up; f = square(world ? cross(u, away) : [1, 0, 0], u); }
    else throw fail(`follow lock must be "velocity", "craft" or "stars", got ${JSON.stringify(lock)}`);
    const rgt = cross(f, u), toFrame = (d) => add(add(scale(rgt, d[0]), scale(u, d[1])), scale(f, d[2]));
    const tanY = Math.tan(fov * RAD / 2);
    // the camera's direction from the craft
    let dir, lookAt = s.at, place = view.place;
    if (view.name === "horizon" && !options.direction) {
      if (!world || !(world.radius > 0)) throw fail('view "horizon" needs the world the craft flies over (around: a subject with a radius)');
      const r = len(sub(s.at, world.at)), dip = Math.acos(Math.min(1, world.radius / r));
      const c0 = Math.cos(dip + 0.012) / Math.hypot(0.5, 1);
      dir = toFrame([0.5 * c0, Math.sin(dip + 0.012), -c0]);                  // behind and beside the craft, on the line from the horizon through it
    } else if (view.name === "shoulder" && !options.direction) {
      if (options.target === undefined) throw fail('view "shoulder" needs target: what the craft is heading for');
      const tg = this.subject(options.target, t, "follow.target"), th = unit(sub(tg.at, s.at)), tu = square(this.up, th, u), tr = cross(th, tu);
      dir = add(add(scale(tr, view.direction[0]), scale(tu, view.direction[1])), scale(th, view.direction[2]));
    } else dir = toFrame(view.direction);
    dir = unit(dir);
    const sway = breathe(c.time, options.drift ?? 1, options.seed ?? 1);
    dir = turn(turn(dir, u, sway.yaw * RAD), unit(cross(dir, u)), sway.pitch * RAD);
    let dist;
    const dOpt = options.distance;
    if (dOpt && typeof dOpt === "object" && dOpt.share !== undefined) dist = distanceFor(rc, num("follow.distance.share", dOpt.share, 1e-6, 10), fov);
    else if (dOpt !== undefined) dist = this._distance(dOpt, rc, "follow.distance");
    else dist = view.distance !== null && view.distance !== undefined ? view.distance * rc : distanceFor(rc, options.size ?? view.size ?? 0.1, fov);
    dist *= (1 + sway.push) * (c.u !== null && options.push !== undefined ? Math.exp(Math.log(num("follow.push", options.push, 1e-3, 1e3)) * eased(c.u, options.ease ?? 0.6)) : 1);
    const eye = add(s.at, scale(dir, dist));
    let up = options.level !== undefined || options.up ? this._up(options, eye, t) : world && (view.name === "horizon" || view.name === "small" || lock !== "craft") ? unit(sub(eye, world.at)) : u;
    if (view.name === "shoulder" && !options.direction) { const tg = this.subject(options.target, t, "follow.target"); lookAt = tg.at; if (!options.up && options.level === undefined) up = square(this.up, unit(sub(tg.at, eye)), u); place = this._place(options.place, c.u, [0.26, 0.2]); }
    else place = this._place(options.place, c.u, place);
    const shot = shotAt(eye, lookAt, {up, fov, aspect: c.aspect, place, roll: c.roll, ahead: f});
    return {...shot, move: "follow", view: view.name ?? null, subject: s, progress: c.u, distance: dist, focus: Math.max(dot(sub(s.at, eye), shot.forward), 1e-6), frame: {right: rgt, up: u, forward: f}};
  }

  /** A powers-of-ten zoom: the camera backs away (or comes in) in one direction while its distance is
   * multiplied by a constant every second, through landing points where it may rest. `stops`: [{subject,
   * distance, hold}, ...]: at each, the camera is `distance` from that subject, which sits in the frame's
   * middle (the zoom's axis: the one move where the middle is right); between two stops the middle
   * glides from one subject to the next in step with the distance (a smoothstep of the distance's share of
   * the leg): the camera leaves and reaches every landing point straight along `direction`, without a kink.
   * `rate` (10 ** 0.5 a second) or `over` (the rate is then what fits), `hold` (seconds on each landing
   * point between the ends; or `hold` on a stop), `ease` (seconds; 0.6). `direction`: from the subjects to
   * the camera (default: 40 degrees off `up`; over a world, on the side away from it, else toward the
   * first subject's sunlit side). The shot
   * adds {distance, power (log10 m), leg, resting, speed (powers of ten a second), seconds (the whole
   * move)}. Honest limit: closer than GROUND_SHARE of a world's radius above its ground a sphere is no
   * ground (problems says so); `space-scale` draws everything farther out from one camera. */
  zoom(t, options = {}) {
    known("zoom options", options, ["time", "over", "start", "lens", "roll", "up", "stops", "rate", "hold", "ease", "direction", "place"]);
    const c = this._common(t, {...options, over: undefined}, "zoom"), stops = options.stops;
    if (!Array.isArray(stops) || stops.length < 2) throw fail("zoom needs stops: [{subject, distance}, ...], two or more");
    const subjects = stops.map((st, i) => { known(`zoom stops[${i}]`, st, ["subject", "distance", "hold"]); return this.subject(st.subject, t, `zoom stops[${i}].subject`); });
    const distances = stops.map((st, i) => this._distance(st.distance, subjects[i].radius, `zoom stops[${i}].distance`));
    const hold = stops.map((st) => st.hold ?? (typeof options.hold === "number" ? options.hold : 0));
    const plan = zoomPlan(distances, {rate: options.over ? null : options.rate ?? null, seconds: options.over ? options.over[1] - options.over[0] : null, hold, ease: options.ease ?? 0.6});
    const z = zoomAt(plan, c.time - (options.over ? options.over[0] : options.start ?? 0));
    let dir = options.direction;
    if (!dir) {
      const first = subjects[0], name = first.name && this.space && this.space.orbits && this.space.orbits.names.includes(first.name) ? first.name : null, parent = name ? this.space.orbits.bodies[name].parent : null;
      const world = parent ? this.subject(parent, t) : null, sun = this.toSun(first.at, t);
      // over a world: away from it (the craft is never behind its world); else 50 degrees round from the sun's side (a lit face with a terminator)
      const out = world && world.radius > 0 && world.name !== "Sun" ? square(sub(first.at, world.at), this.up) : sun ? turn(square(sun, this.up), this.up, 50 * RAD) : square([0.6, -0.8, 0.1], this.up);
      dir = add(scale(this.up, Math.cos(40 * RAD)), scale(out, Math.sin(40 * RAD)));
    }
    dir = unit(dir);
    const a = subjects[z.leg], b = subjects[z.leg + 1], w = smoothstep(0, 1, z.share), middle = lerp(a.at, b.at, w), eye = add(middle, scale(dir, z.distance));
    const shot = shotAt(eye, middle, {up: options.up ? unit(options.up) : this.up, fov: c.fov, aspect: c.aspect, place: this._place(options.place, 0, [0, 0]), roll: c.roll});
    return {...shot, move: "zoom", subject: w < 0.5 ? a : b, distance: z.distance, power: z.power, leg: z.leg, resting: z.resting, speed: z.speed, seconds: plan.seconds, plan};
  }

  // ----- placing the camera -----
  /** Place the camera for `shot` at scene time t: through `space.update` (the camera's place subtracted
   * from everything in double precision) with a SpaceView, else on the three.js camera itself; sets the
   * field of view. Returns the shot (also `cam.shot`); `shot.focus` is three-finish's dof.focus. */
  apply(t, shot) {
    const cam = this.camera;
    if (cam && Math.abs(cam.fov - shot.fov) > 1e-9) { cam.fov = shot.fov; cam.updateProjectionMatrix(); }
    if (this.space) this.space.update(t, {from: {offset: shot.from}, quaternion: quaternionOfShot(shot, "data")});
    else {
      if (!cam) throw fail("apply needs a camera: spaceCamera({camera})");
      cam.position.set(...shot.from); cam.quaternion.set(...quaternionOfShot(shot, "three")); cam.updateMatrixWorld();
    }
    this.shot = shot;
    return shot;
  }

  /** The disc of a subject in a shot (discOf), for a match cut: `cam.disc(shot, "Earth")`. */
  disc(shot, what, t = 0) { const s = this.subject(what, t, "disc"); return discOf(shot, s.at, s.radius); }

  /** What is wrong with `shot` at t, as sentences (none: an empty list): the camera inside a world or so
   * near its ground that a sphere is no ground; the subject behind the camera, outside `box` (default the
   * whole frame: [-1, -1, 1, 1] as [left, bottom, right, top]), smaller than `minPixels` in radius (3; the
   * frame's `height` in pixels), or hidden behind a world. `subject` defaults to the shot's own. */
  problems(t, shot, options = {}) {
    known("problems options", options, ["subject", "box", "minPixels", "height", "ground"]);
    const out = [], worlds = this._worlds(t), s = options.subject !== undefined ? this.subject(options.subject, t, "problems.subject") : shot.subject ?? null;
    const km = (m) => (m >= 1e6 ? `${(m / 1000).toFixed(0)} km` : m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m.toFixed(0)} m`);
    for (const w of worlds) {
      const d = len(sub(shot.from, w.at)), share = options.ground ?? GROUND_SHARE;
      if (d <= w.radius) out.push(`the camera is inside ${w.name} (${km(w.radius - d)} under its surface): move it out, or give the move a larger distance`);
      else if (d - w.radius < share * w.radius) out.push(`the camera is ${km(d - w.radius)} above ${w.name}: closer than ${km(share * w.radius)} a sphere is no ground (no relief, facets); stay higher or build a ground of your own`);
    }
    if (!s) return out;
    const who = s.name ?? "the subject", p = screenOf(shot, s.at), box = options.box ?? [-1, -1, 1, 1];
    // a subject larger than the frame is in it while any of its disc is (its middle may be far outside)
    const to = sub(s.at, shot.from), dist = len(to), rho = dist > s.radius ? Math.asin(s.radius / dist) : Math.PI, big = discOf(shot, s.at, s.radius).radius > 1;
    const gone = angleBetween(shot.forward, to) - rho > Math.atan(Math.tan(shot.fov * RAD / 2) * Math.hypot(1, shot.aspect));
    if (!(p.depth > 0) && gone) out.push(`${who} is behind the camera`);
    else if (big ? gone : p.x < box[0] || p.x > box[2] || p.y < box[1] || p.y > box[3]) out.push(`${who} is outside ${options.box ? "its box" : "the frame"} (at x ${p.x.toFixed(2)}, y ${p.y.toFixed(2)}; the frame is -1 to 1)`);
    const disc = discOf(shot, s.at, s.radius), px = discPixels(disc, options.height ?? this.height), min = options.minPixels ?? MIN_PIXELS;
    if (s.radius > 0 && p.depth > 0 && px < min) out.push(`${who} is ${px.toFixed(1)} px in radius, under ${min}: come closer, use a longer lens, or mark it (a craft's marker, an enlarged body)`);
    if (p.depth > 0 && shot.move !== "reveal") for (const w of worlds) {
      if (w.name === s.name || len(sub(w.at, s.at)) < w.radius) continue;
      const v = sub(s.at, shot.from), L = len(v), k = clamp(dot(sub(w.at, shot.from), v) / (L * L)), near = len(sub(add(shot.from, scale(v, k)), w.at));
      if (k > 0 && k < 0.999 && near < w.radius * (1 - 1e-6) - s.radius) out.push(`${who} is hidden behind ${w.name}`);
    }
    return out;
  }

  /** Check a whole move: `move(t)` gives its shot; sampled at `steps` + 1 times from `from` to `to`.
   * Returns sentences with their times: everything `problems` finds, a camera path that goes through
   * a world between two samples, and a jump (the camera's place or turn changing over 8 times faster
   * between two samples than is usual for the move: a kink). */
  check(move, {from = 0, to = 1, steps = 48, ...rest} = {}) {
    const out = [], seen = new Set(), shots = [];
    for (let i = 0; i <= steps; i++) {
      const t = mix(from, to, i / steps), shot = move(t);
      shots.push([t, shot]);
      for (const p of this.problems(t, shot, rest)) { const key = p.replace(/[0-9.]+/g, "#"); if (!seen.has(key)) { seen.add(key); out.push(`at ${t.toFixed(2)} s: ${p}`); } }
      if (i > 0) for (const w of this._worlds(t)) {
        const a = sub(shots[i - 1][1].from, w.at), b = sub(shot.from, w.at), d = sub(b, a), l2 = dot(d, d), k = l2 > 0 ? clamp(-dot(a, d) / l2) : 0;
        if (len(add(a, scale(d, k))) < w.radius && len(a) > w.radius && len(b) > w.radius && !seen.has(`through ${w.name}`)) { seen.add(`through ${w.name}`); out.push(`between ${shots[i - 1][0].toFixed(2)} and ${t.toFixed(2)} s the camera's path goes through ${w.name}`); }
      }
    }
    const turns = shots.slice(1).map(([, s], i) => angleBetween(s.forward, shots[i][1].forward)), sorted = [...turns].sort((a, b) => a - b), usual = sorted[Math.floor(sorted.length / 2)];
    turns.forEach((a, i) => { if (a > 8 * Math.max(usual, 0.02 * RAD) && a > 3 * RAD && a > 3 * Math.max(turns[i - 1] ?? 0, turns[i + 1] ?? 0) && !seen.has("kink")) { seen.add("kink"); out.push(`at ${shots[i + 1][0].toFixed(2)} s the camera turns ${(a / RAD).toFixed(1)} degrees in one step (usually ${(usual / RAD).toFixed(2)}): a jump in the move`); } });
    return out;
  }
}

/** A camera rig for space scenes: `spaceCamera({space, camera})` on a SpaceView, or `spaceCamera({camera, up, sun,
 * bodies})` in a plain three.js scene. */
export function spaceCamera(options = {}) { return new SpaceCamera(options); }
